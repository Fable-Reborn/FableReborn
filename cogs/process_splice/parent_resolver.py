"""Interactive picker for splice parents the automated repair cannot infer.

When a duplicate result name is disambiguated into ``X [S12]`` and ``X [S34]``,
every recipe still referencing plain ``X`` becomes unresolvable.  Creation order
settles most of them; the rest genuinely need a human to look at the two
creatures and say which one was the parent.  This view shows both side by side
and writes the answer one decision at a time.
"""

from __future__ import annotations

from typing import Any, Awaitable, Callable, Mapping, Optional, Sequence

import discord


ChoiceCallback = Callable[[int, str, int, str], Awaitable[None]]


def _stat_line(row: Mapping[str, Any]) -> str:
    parts = [
        f"HP {row.get('hp')}",
        f"ATK {row.get('attack')}",
        f"DEF {row.get('defense')}",
    ]
    element = str(row.get("element") or "").strip()
    if element:
        parts.append(element)
    return " · ".join(parts)


def _parent_line(row: Mapping[str, Any]) -> str:
    return f"{row.get('pet1_default')} + {row.get('pet2_default')}"


class CandidateButton(discord.ui.Button):
    def __init__(self, view: "ParentResolverView", position: int, splice_id: int, name: str):
        label = f"S{splice_id} · {name}"
        super().__init__(
            label=label[:80],
            style=discord.ButtonStyle.primary,
            row=position // 5,
        )
        self.resolver = view
        self.splice_id = splice_id
        self.candidate_name = name

    async def callback(self, interaction: discord.Interaction) -> None:
        await self.resolver.choose(interaction, self.splice_id, self.candidate_name)


class ParentResolverView(discord.ui.View):
    """Owner-only walkthrough of every ambiguous parent slot."""

    def __init__(
        self,
        ctx,
        slots: Sequence[Any],
        row_by_id: Mapping[int, Mapping[str, Any]],
        generations: Mapping[int, int],
        on_choose: ChoiceCallback,
        *,
        timeout: float = 600,
    ):
        super().__init__(timeout=timeout)
        if not slots:
            raise ValueError("ParentResolverView requires at least one ambiguous slot")
        self.ctx = ctx
        self.slots = list(slots)
        self.row_by_id = row_by_id
        self.generations = generations
        self.on_choose = on_choose
        self.index = 0
        self.resolved = 0
        self.skipped = 0
        self.message: Optional[discord.Message] = None
        self.allowed_user_ids = {int(ctx.author.id)}
        alt_invoker_id = getattr(ctx, "alt_invoker_id", None)
        if alt_invoker_id is not None:
            self.allowed_user_ids.add(int(alt_invoker_id))
        self._sync_components()

    @property
    def current(self):
        return self.slots[self.index]

    def _sync_components(self) -> None:
        self.clear_items()
        for position, (splice_id, name) in enumerate(self.current.candidates):
            self.add_item(CandidateButton(self, position, splice_id, name))
        skip = discord.ui.Button(
            label="Skip",
            style=discord.ButtonStyle.secondary,
            row=(len(self.current.candidates) - 1) // 5 + 1,
        )
        skip.callback = self._skip
        self.add_item(skip)
        stop = discord.ui.Button(
            label="Stop",
            style=discord.ButtonStyle.danger,
            row=(len(self.current.candidates) - 1) // 5 + 1,
        )
        stop.callback = self._stop
        self.add_item(stop)

    def _embeds(self) -> list[discord.Embed]:
        slot = self.current
        child = self.row_by_id.get(slot.splice_id, {})
        header = discord.Embed(
            title=f"Ambiguous parent {self.index + 1}/{len(self.slots)}",
            description=(
                f"**S{slot.splice_id} {child.get('result_name')}**\n"
                f"{_parent_line(child)}\n\n"
                f"`{slot.slot}` still points at **{slot.orphan_name}**, which no "
                f"longer exists. Which one was it?"
            ),
            colour=0xC27C3E,
        )
        header.add_field(name="Child stats", value=_stat_line(child), inline=False)
        child_url = str(child.get("url") or "").strip()
        if child_url:
            header.set_thumbnail(url=child_url)

        embeds = [header]
        for splice_id, name in slot.candidates:
            row = self.row_by_id.get(splice_id, {})
            generation = self.generations.get(int(splice_id))
            embed = discord.Embed(
                title=f"S{splice_id} · {name}",
                description=_parent_line(row),
                colour=0x4C7DD9,
            )
            embed.add_field(name="Stats", value=_stat_line(row), inline=True)
            embed.add_field(
                name="Generation",
                value="unresolved" if generation is None else str(generation),
                inline=True,
            )
            created_at = row.get("created_at")
            if created_at is not None:
                embed.set_footer(text=f"created {created_at}")
            url = str(row.get("url") or "").strip()
            if url:
                embed.set_image(url=url)
            embeds.append(embed)
        return embeds

    async def start(self) -> discord.Message:
        self.message = await self.ctx.send(embeds=self._embeds(), view=self)
        return self.message

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if int(interaction.user.id) in self.allowed_user_ids:
            return True
        await interaction.response.send_message(
            "This splice resolver belongs to another Game Master.", ephemeral=True
        )
        return False

    async def choose(
        self,
        interaction: discord.Interaction,
        parent_splice_id: int,
        parent_name: str,
    ) -> None:
        slot = self.current
        try:
            await self.on_choose(slot.splice_id, slot.slot, parent_splice_id, parent_name)
        except Exception as error:
            await interaction.response.send_message(
                f"Could not save that choice: {error}", ephemeral=True
            )
            return
        self.resolved += 1
        await self._advance(interaction)

    async def _skip(self, interaction: discord.Interaction) -> None:
        self.skipped += 1
        await self._advance(interaction)

    async def _stop(self, interaction: discord.Interaction) -> None:
        await interaction.response.edit_message(embeds=[self._summary()], view=None)
        self.stop()

    async def _advance(self, interaction: discord.Interaction) -> None:
        self.index += 1
        if self.index >= len(self.slots):
            await interaction.response.edit_message(embeds=[self._summary()], view=None)
            self.stop()
            return
        self._sync_components()
        await interaction.response.edit_message(embeds=self._embeds(), view=self)

    def _summary(self) -> discord.Embed:
        remaining = max(0, len(self.slots) - self.resolved - self.skipped)
        return discord.Embed(
            title="Splice parent resolver",
            description=(
                f"Resolved **{self.resolved}**, skipped **{self.skipped}**, "
                f"**{remaining}** left untouched.\n"
                "Re-run the command to pick up where you left off."
            ),
            colour=0x4CAF72,
        )

    async def on_timeout(self) -> None:
        for item in self.children:
            item.disabled = True
        if self.message is not None:
            try:
                await self.message.edit(embeds=[self._summary()], view=None)
            except discord.HTTPException:
                pass

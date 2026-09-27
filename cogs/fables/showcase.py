"""One story per page, with bundled artwork and persisted completion state."""
import asyncio
from datetime import datetime
from pathlib import Path

import discord

ASSETS = Path(__file__).resolve().parents[2] / "assets" / "fables"
COVERS = {"crownfall": "crownfall.png", "tiamat": "tiamat-cinematic.png"}
COLOURS = {"crownfall": 0xD4A94E, "tiamat": 0x8FBBD0}


def date_label(value):
    if isinstance(value, datetime):
        return discord.utils.format_dt(value, style="d")
    return "—"


def build_page(row, index, total, completed, owner_name, avatar_url=None):
    row = dict(row)
    finished = row.get("completed_at") is not None
    description = row["description"][:3500]
    if row.get("tagline"):
        description = f"*{row['tagline'][:200]}*\n\n{description}"
    embed = discord.Embed(title=row["title"][:256], description=description,
                          colour=0x71B88B if finished else COLOURS.get(row["id"], 0xD4A94E))
    author = {"name": f"{owner_name[:180]} · Fable collection"}
    if avatar_url:
        author["icon_url"] = str(avatar_url)
    embed.set_author(**author)
    custom = row.get("protagonist_type") == "custom"
    protagonist = "**Custom hero**\nYour own character" if custom else (
        "**Story protagonist**\n" + (row.get("protagonist_name") or "An established character")
    )
    status = "✅ **Completed**" if finished else "◌ **Not completed**"
    if finished:
        status += f"\nFinished {date_label(row['completed_at'])}"
    else:
        status += "\nAdventure underway" if row.get("started_at") else "Your adventure awaits"
    embed.add_field(name="Protagonist", value=protagonist, inline=True)
    embed.add_field(name="Completion", value=status, inline=True)
    embed.add_field(name="Unlocked", value=date_label(row.get("unlocked_at")), inline=True)
    embed.set_footer(text=f"Fable {index + 1} of {total}  •  {completed}/{total} stories completed  •  FableReborn")
    cover = ASSETS / COVERS[row["id"]] if row["id"] in COVERS else None
    if cover and cover.is_file():
        embed.set_image(url=f"attachment://{cover.name}")
        return embed, discord.File(cover, filename=cover.name)
    return embed, None


class FableSelect(discord.ui.Select):
    def __init__(self, view):
        self.owner_view = view
        super().__init__(placeholder="Choose a Fable…", min_values=1, max_values=1, row=0)

    async def callback(self, interaction):
        await self.owner_view.navigate(interaction, index=int(self.values[0]))


class FableShowcase(discord.ui.View):
    def __init__(self, owner_id, owner_name, rows, avatar_url=None):
        super().__init__(timeout=300)
        self.owner_id = owner_id
        self.owner_name = owner_name
        self.avatar_url = avatar_url
        self.rows = [dict(row) for row in rows]
        if not self.rows:
            raise ValueError("A showcase needs at least one Fable.")
        self.index = 0
        self.message = None
        self.lock = asyncio.Lock()
        self.selector = FableSelect(self)
        self.add_item(self.selector)
        self.update_controls()

    def update_controls(self):
        self.previous.disabled = self.index == 0
        self.next.disabled = self.index == len(self.rows) - 1
        self.counter.label = f"{self.index + 1} / {len(self.rows)}"
        start = self.index // 25 * 25
        self.selector.options = [discord.SelectOption(
            label=row["title"][:100], value=str(i), default=i == self.index,
            description="Completed" if row.get("completed_at") else "Not completed",
            emoji="✅" if row.get("completed_at") else "📖",
        ) for i, row in enumerate(self.rows[start:start + 25], start)]
        self.selector.disabled = len(self.rows) == 1

    def page(self):
        return build_page(self.rows[self.index], self.index, len(self.rows),
                          sum(row.get("completed_at") is not None for row in self.rows),
                          self.owner_name, self.avatar_url)

    async def interaction_check(self, interaction):
        if interaction.user.id == self.owner_id:
            return True
        await interaction.response.send_message("Open your own collection with `$fables` to browse it.", ephemeral=True)
        return False

    async def navigate(self, interaction, *, delta=0, index=None):
        await interaction.response.defer()
        async with self.lock:
            if self.is_finished():
                return
            self.index = max(0, min(len(self.rows) - 1, self.index + delta if index is None else index))
            self.update_controls()
            embed, file = self.page()
            try:
                await interaction.edit_original_response(embed=embed, attachments=[file] if file else [], view=self)
            finally:
                if file:
                    file.close()

    async def on_timeout(self):
        async with self.lock:
            for child in self.children:
                child.disabled = True
            if self.message:
                try:
                    await self.message.edit(view=self)
                except discord.HTTPException:
                    pass

    @discord.ui.button(label="Previous", emoji="◀", style=discord.ButtonStyle.secondary, row=1)
    async def previous(self, interaction, button):
        await self.navigate(interaction, delta=-1)

    @discord.ui.button(label="1 / 1", style=discord.ButtonStyle.secondary, disabled=True, row=1)
    async def counter(self, interaction, button):
        pass

    @discord.ui.button(label="Next", emoji="▶", style=discord.ButtonStyle.primary, row=1)
    async def next(self, interaction, button):
        await self.navigate(interaction, delta=1)

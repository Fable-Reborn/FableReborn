"""Interactive GM auction builder: one panel for classic auctions, silent auctions and raffles.

The panel is an ordinary (not ephemeral) message so it can be edited for as long as the view
lives. All drafting state is in memory (``Draft``); the text that players see comes from
``announce.build_announcement`` for the preview and the real post alike.
"""
from __future__ import annotations

import asyncio
import datetime
import logging
from typing import Optional

import discord

from utils.i18n import _

from . import announce, draft as draftlib
from .announce import EventAlreadyLive
from .draft import Draft

log = logging.getLogger(__name__)

PANEL_TIMEOUT = 15 * 60
NO_MENTIONS = discord.AllowedMentions.none()

TYPE_INFO = {
    "classic": ("🔨", "Classic Auction", "Open bids, highest wins, ends 12h after the last bid."),
    "silent": ("🔒", "Silent Auction", "Sealed bids, fixed end time."),
    "raffle": ("🎟️", "Raffle", "Buy tickets, a random ticket wins."),
}


class BuilderError(Exception):
    """A user-facing reason the post can't go ahead."""


def _preview_view(kind: str) -> Optional[discord.ui.View]:
    """Disabled copies of the real buttons so the preview looks like the post."""
    if kind == "classic":
        return None
    view = discord.ui.View(timeout=60)
    if kind == "silent":
        labels = [("🔒 Place / Raise Bid", discord.ButtonStyle.primary), ("View My Bid", discord.ButtonStyle.secondary)]
    else:
        labels = [("🎟️ Buy Tickets", discord.ButtonStyle.success), ("My Tickets", discord.ButtonStyle.secondary)]
    for label, style in labels:
        view.add_item(discord.ui.Button(label=label, style=style, disabled=True))
    return view


class DetailsModal(discord.ui.Modal):
    def __init__(self, builder: "BuilderView") -> None:
        kind = builder.draft.kind
        super().__init__(title=_(TYPE_INFO[kind][1]) + " " + _("details"), timeout=600)
        self.builder = builder
        d = builder.draft
        self._inputs: dict[str, discord.ui.TextInput] = {}

        def add(key, label, value, *, required=True, placeholder=None, max_length=100):
            item = discord.ui.TextInput(
                label=label, default=value or None, required=required,
                placeholder=placeholder, max_length=max_length,
            )
            self._inputs[key] = item
            self.add_item(item)

        if kind == "classic":
            add("name", _("Item"), d.name, max_length=200)
        elif kind == "silent":
            add("name", _("Item"), d.name, max_length=200)
            add("min_bid", _("Minimum bid"), d.min_bid, placeholder="1000, 1,000, 1k")
            add("duration", _("Duration (5m to 14d)"), d.duration, placeholder="24h, 1d12h, 90m")
        else:
            add("name", _("Prize"), d.name, max_length=200)
            add("ticket_price", _("Ticket price"), d.ticket_price, placeholder="1000, 1k")
            add(
                "max_per_user", _("Max tickets per player (blank = no cap)"),
                d.max_per_user, required=False, placeholder="1-1000",
            )
            add("duration", _("Duration, or manual"), d.duration, placeholder="24h, 3d, manual")

    async def on_submit(self, interaction: discord.Interaction) -> None:
        for key, item in self._inputs.items():
            setattr(self.builder.draft, key, item.value)
        await self.builder.after_edit(interaction)

    async def on_error(self, interaction: discord.Interaction, error: Exception) -> None:
        log.error("builder details modal failed", exc_info=error)
        await self.builder.safe_reply(interaction, _("Something went wrong."))


class AnnouncementModal(discord.ui.Modal):
    def __init__(self, builder: "BuilderView") -> None:
        super().__init__(title=_("Announcement"), timeout=600)
        self.builder = builder
        self.title_input = discord.ui.TextInput(
            label=_("Title (optional)"), default=builder.draft.title or None,
            required=False, max_length=draftlib.TITLE_LIMIT,
        )
        self.message_input = discord.ui.TextInput(
            label=_("Message (optional)"), style=discord.TextStyle.paragraph,
            default=builder.draft.message or None, required=False,
            max_length=draftlib.MESSAGE_LIMIT,
            placeholder=_("Tell players about the item, why it's special, any extra rules…"),
        )
        self.add_item(self.title_input)
        self.add_item(self.message_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        self.builder.draft.title = self.title_input.value
        self.builder.draft.message = self.message_input.value
        await self.builder.after_edit(interaction)

    async def on_error(self, interaction: discord.Interaction, error: Exception) -> None:
        log.error("builder announcement modal failed", exc_info=error)
        await self.builder.safe_reply(interaction, _("Something went wrong."))


class TypeSelect(discord.ui.Select):
    def __init__(self, builder: "BuilderView") -> None:
        options = [
            discord.SelectOption(label=_(label), value=kind, emoji=emoji, description=_(desc))
            for kind, (emoji, label, desc) in TYPE_INFO.items()
        ]
        super().__init__(placeholder=_("Choose the auction type"), options=options, row=0)
        self.builder = builder

    async def callback(self, interaction: discord.Interaction) -> None:
        self.builder.switch(self.values[0])
        await interaction.response.defer()
        await self.builder.refresh()


class ConfirmView(discord.ui.View):
    """Ephemeral "are you sure" step. Owner-locked, 60 seconds."""

    def __init__(self, builder: "BuilderView", summary: str) -> None:
        super().__init__(timeout=60)
        self.builder = builder
        self.summary = summary

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.builder.owner.id:
            return True
        await interaction.response.send_message(
            _("This builder belongs to {gm}.").format(gm=self.builder.owner.display_name),
            ephemeral=True,
        )
        return False

    @discord.ui.button(label="✅ Post", style=discord.ButtonStyle.success)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(content=_("Posting…"), view=None)
        result = await self.builder.do_post()
        try:
            await interaction.edit_original_response(content=result)
        except discord.HTTPException:
            pass
        self.stop()

    @discord.ui.button(label="↩ Back", style=discord.ButtonStyle.secondary)
    async def back(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(content=_("Not posted."), view=None)
        self.stop()


class BuilderView(discord.ui.View):
    def __init__(self, cog, ctx) -> None:
        super().__init__(timeout=PANEL_TIMEOUT)
        self.cog = cog
        self.owner = ctx.author
        self.prefix = ctx.clean_prefix
        self.draft = Draft()
        self.message: Optional[discord.Message] = None
        self.posting = False
        self.finished = False
        self.post_lock = asyncio.Lock()
        self.notes: list[str] = []
        self.errors: list[str] = []
        self.parsed = None
        self.live = {"classic": False, "silent": False, "raffle": False}
        self.channel = None
        self.role = None
        self.target_error: Optional[str] = None
        self.result_note: Optional[str] = None
        self.pings_live = False
        self.type_select = TypeSelect(self)
        self.add_item(self.type_select)

    # ------------------------------------------------------------------ state

    def switch(self, kind: str) -> None:
        old = self.draft
        had_type_fields = any([old.min_bid, old.duration, old.ticket_price, old.max_per_user])
        self.draft = draftlib.switch_kind(old, kind)
        self.notes = (
            [_("Type-specific fields were cleared; item/prize, announcement and ping were kept.")]
            if had_type_fields and kind != old.kind
            else []
        )

    async def compute(self) -> None:
        self.errors, self.parsed = draftlib.validate(self.draft)
        self.channel, self.role, self.target_error = self.cog.resolve_target(
            self.draft.kind, self.draft.ping
        )
        self.live = await self.cog.live_status()
        can_post = (
            self.parsed is not None
            and self.target_error is None
            and not self.live[self.draft.kind]
            and not self.posting
            and not self.finished
        )
        self.post_button.disabled = not can_post
        self.pings_live = announce.pings_enabled(self.cog.bot)
        self.ping_button.label = (
            (_("Ping: On") if self.draft.ping else _("Ping: Off"))
            if self.pings_live
            else _("Ping: Off (paused)")
        )
        for option in self.type_select.options:
            option.default = option.value == self.draft.kind

    def build_embed(self) -> discord.Embed:
        d = self.draft
        emoji, label, desc = TYPE_INFO[d.kind]
        embed = discord.Embed(
            title=_("GM Auction Builder"),
            description=f"{emoji} **{_(label)}**: {_(desc)}",
            colour=announce.COLOURS[d.kind],
        )
        shown = d.name.strip() or "—"
        lines = [f"**{_('Prize') if d.kind == 'raffle' else _('Item')}:** {announce.clip(shown, 200)}"]
        if d.kind == "silent":
            lines.append(f"**{_('Minimum bid')}:** {announce.clip(d.min_bid.strip() or '—', 40)}")
            lines.append(f"**{_('Duration')}:** {announce.clip(d.duration.strip() or '—', 40)}")
        elif d.kind == "raffle":
            lines.append(f"**{_('Ticket price')}:** {announce.clip(d.ticket_price.strip() or '—', 40)}")
            lines.append(
                f"**{_('Max per player')}:** {announce.clip(d.max_per_user.strip() or _('No limit'), 40)}"
            )
            lines.append(f"**{_('Duration')}:** {announce.clip(d.duration.strip() or '—', 40)}")
        embed.add_field(name=_("Details"), value="\n".join(lines), inline=False)
        title = announce.clip(d.title.strip() or announce.default_title(d.kind, d.name.strip() or "…"), 200)
        msg = announce.clip(d.message.strip() or announce.default_message(d.kind), 400)
        embed.add_field(
            name=_("Announcement"),
            value=announce.clip(f"**{title}**\n{msg}", 1000),
            inline=False,
        )
        embed.add_field(
            name=_("Ping"),
            value=(_("On") if d.ping else _("Off"))
            if self.pings_live
            else _("Paused for testing (event_pings_enabled is off)"),
            inline=True,
        )
        embed.add_field(
            name=_("Live right now"),
            value=_("Classic: {c} · Silent: {s} · Raffle: {r}").format(
                c=_("yes") if self.live["classic"] else _("no"),
                s=_("yes") if self.live["silent"] else _("no"),
                r=_("yes") if self.live["raffle"] else _("no"),
            ),
            inline=True,
        )
        problems = list(self.errors)
        if self.target_error:
            problems.append(self.target_error)
        if self.live[d.kind]:
            problems.append(_("A {kind} is already live; wait for it to finish.").format(kind=_(TYPE_INFO[d.kind][1])))
        if problems:
            embed.add_field(
                name=_("⚠️ Fix before posting:"),
                value=announce.clip("\n".join(f"• {p}" for p in problems), 1000),
                inline=False,
            )
        else:
            embed.add_field(
                name=_("Ready"),
                value=_("Press 👁️ Preview to see the exact post, then 📣 Post."),
                inline=False,
            )
        if self.notes:
            embed.add_field(name=_("Note"), value=announce.clip("\n".join(self.notes), 500), inline=False)
        if self.result_note:
            embed.add_field(name=_("Last result"), value=announce.clip(self.result_note, 500), inline=False)
        embed.set_footer(text=_("Drafts are kept in memory only; a restart loses them."))
        return embed

    async def refresh(self) -> None:
        if self.finished:
            return
        await self.compute()
        if self.message is None:
            return
        try:
            await self.message.edit(embed=self.build_embed(), view=self)
        except discord.HTTPException:
            log.warning("could not edit builder panel", exc_info=True)

    async def after_edit(self, interaction: discord.Interaction) -> None:
        """Common tail for modal submits: answer fast, redraw the panel, show errors."""
        self.notes = []
        await interaction.response.defer()
        await self.refresh()
        if self.errors:
            await interaction.followup.send(
                _("⚠️ Fix before posting:") + "\n" + "\n".join(f"• {e}" for e in self.errors),
                ephemeral=True,
            )

    async def safe_reply(self, interaction: discord.Interaction, text: str) -> None:
        try:
            if interaction.response.is_done():
                await interaction.followup.send(text, ephemeral=True)
            else:
                await interaction.response.send_message(text, ephemeral=True)
        except discord.HTTPException:
            pass

    async def start(self, ctx) -> None:
        old = self.cog._builders.get(self.owner.id)
        if old is not None and old is not self:
            await old.close_panel(_("Replaced by a newer builder."))
        self.cog._builders[self.owner.id] = self
        await self.compute()
        self.message = await ctx.send(embed=self.build_embed(), view=self)

    async def close_panel(self, text: str, *, expired: bool = False) -> None:
        self.finished = True
        for item in self.children:
            item.disabled = True
        if self.cog._builders.get(self.owner.id) is self:
            del self.cog._builders[self.owner.id]
        self.stop()
        if self.message is None:
            return
        embed = discord.Embed(
            title=_("Builder expired — run {prefix}gmab again").format(prefix=self.prefix)
            if expired
            else _("GM Auction Builder"),
            description=text,
            colour=discord.Colour.dark_grey(),
        )
        try:
            await self.message.edit(embed=embed, view=self)
        except (discord.NotFound, discord.HTTPException):
            pass

    # ----------------------------------------------------------- view plumbing

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.owner.id:
            return True
        await interaction.response.send_message(
            _("This builder belongs to {gm}.").format(gm=self.owner.display_name), ephemeral=True
        )
        return False

    async def on_timeout(self) -> None:
        if not self.finished:
            await self.close_panel(_("This panel timed out."), expired=True)

    async def on_error(self, interaction, error, item) -> None:
        log.error("builder interaction failed", exc_info=error)
        await self.safe_reply(interaction, _("Something went wrong."))

    # ------------------------------------------------------------------ buttons

    @discord.ui.button(label="✏️ Details", style=discord.ButtonStyle.primary, row=1)
    async def details_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(DetailsModal(self))

    @discord.ui.button(label="📝 Announcement", style=discord.ButtonStyle.primary, row=1)
    async def announcement_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(AnnouncementModal(self))

    @discord.ui.button(label="Ping: On", emoji="🔔", style=discord.ButtonStyle.secondary, row=1)
    async def ping_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.draft.ping = not self.draft.ping
        self.notes = []
        await interaction.response.defer()
        await self.refresh()

    @discord.ui.button(label="👁️ Preview", style=discord.ButtonStyle.secondary, row=2)
    async def preview_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True, thinking=True)
        await self.compute()
        if self.parsed is None:
            return await interaction.followup.send(
                _("⚠️ Fix before posting:") + "\n" + "\n".join(f"• {e}" for e in self.errors),
                ephemeral=True,
            )
        content, embeds = self.render(self.parsed)
        kwargs = {"view": v} if (v := _preview_view(self.parsed.kind)) else {}
        await interaction.followup.send(
            content, embeds=embeds, ephemeral=True, allowed_mentions=NO_MENTIONS, **kwargs
        )

    @discord.ui.button(label="📣 Post", style=discord.ButtonStyle.success, row=2, disabled=True)
    async def post_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True, thinking=True)
        await self.compute()
        problem = self.post_problem()
        if problem:
            await self.refresh()
            return await interaction.followup.send(problem, ephemeral=True)
        p = self.parsed
        label = _(TYPE_INFO[p.kind][1])
        text = _("Post this **{kind}** to {channel}{ping}?").format(
            kind=label,
            channel=self.channel.mention,
            ping=_(" and ping **@{role}**").format(role=self.role.name) if (p.ping and self.pings_live and self.role) else "",
        )
        await interaction.followup.send(text, view=ConfirmView(self, text), ephemeral=True)

    @discord.ui.button(label="✖ Cancel", style=discord.ButtonStyle.danger, row=2)
    async def cancel_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        await self.close_panel(_("Builder closed. Nothing was posted."))

    # ------------------------------------------------------------------ posting

    def post_problem(self) -> Optional[str]:
        if self.parsed is None:
            return _("⚠️ Fix before posting:") + "\n" + "\n".join(f"• {e}" for e in self.errors)
        if self.target_error:
            return self.target_error
        if self.live[self.draft.kind]:
            return _("A {kind} is already live.").format(kind=_(TYPE_INFO[self.draft.kind][1]))
        if self.posting or self.finished:
            return _("This builder is already posting.")
        return None

    def render(self, p):
        """Exactly what will be posted, via the shared renderer."""
        ends_at = (
            datetime.datetime.now(datetime.timezone.utc) + p.duration if p.duration else None
        )
        return announce.build_announcement(
            p.kind,
            name=p.name,
            title=p.title or None,
            message=p.message or None,
            gm_name=self.owner.display_name,
            prefix=self.prefix,
            ends_at=ends_at,
            min_bid=p.min_bid,
            ticket_price=p.ticket_price,
            max_per_user=p.max_per_user,
            commitment=_("(generated when posted)") if p.kind == "raffle" else None,
            role_mention=self.role.mention if (p.ping and self.pings_live and self.role) else None,
            tickets=0 if p.kind == "raffle" else None,
            entrants=0 if p.kind == "raffle" else None,
        )

    async def do_post(self) -> str:
        """Runs under a lock so a double click can't start two events."""
        async with self.post_lock:
            if self.posting or self.finished:
                return _("This builder is already posting.")
            await self.compute()
            problem = self.post_problem()
            if problem:
                return problem
            self.posting = True
            for item in self.children:
                item.disabled = True
            if self.message is not None:
                try:
                    await self.message.edit(embed=self.build_embed(), view=self)
                except discord.HTTPException:
                    pass
            p = self.parsed
            try:
                message = await self._start_event(p)
            except EventAlreadyLive:
                error = _("A {kind} is already live.").format(kind=_(TYPE_INFO[p.kind][1]))
            except discord.HTTPException as exc:
                error = _("Discord refused the post: {error}").format(error=exc)
            except BuilderError as exc:
                error = str(exc)
            except Exception:
                log.exception("builder post failed")
                error = _("Something went wrong while starting the event. Check it didn't start.")
            else:
                await self._finish_posted(p, message)
                return _("✅ Posted: {link}").format(link=message.jump_url)
            # failure: give the panel back to the GM with the reason
            self.posting = False
            for item in self.children:
                item.disabled = False
            self.result_note = error
            await self.refresh()
            return "❌ " + error

    async def _start_event(self, p) -> discord.Message:
        channel, role = self.channel, self.role
        common = dict(
            gm=self.owner, channel=channel, role=role, announcement=p.message or None,
            title=p.title or None, ping=p.ping, prefix=self.prefix,
        )
        if p.kind == "classic":
            gm_cog = self.cog.bot.get_cog("GameMaster")
            if gm_cog is None:
                raise BuilderError(_("The GameMaster cog isn't loaded."))
            return await gm_cog.start_classic_auction(item=p.name, **common)
        if p.kind == "silent":
            return await self.cog.start_silent_auction(
                item=p.name, min_bid=p.min_bid, duration=p.duration, **common
            )
        return await self.cog.start_raffle(
            prize=p.name, ticket_price=p.ticket_price, max_per_user=p.max_per_user,
            duration=p.duration, **common,
        )

    async def _finish_posted(self, p, message: discord.Message) -> None:
        self.finished = True
        self.stop()
        if self.cog._builders.get(self.owner.id) is self:
            del self.cog._builders[self.owner.id]
        embed = discord.Embed(
            title=_("✅ Posted"),
            description=_("[Jump to the announcement]({link})").format(link=message.jump_url),
            colour=discord.Colour.green(),
        )
        if self.message is not None:
            try:
                await self.message.edit(embed=embed, view=None)
            except discord.HTTPException:
                pass
        details = f"{p.kind}: {p.name}"
        if p.min_bid:
            details += f", min bid ${p.min_bid:,}"
        if p.ticket_price:
            details += f", ticket ${p.ticket_price:,}, cap {p.max_per_user or 'none'}"
        if p.duration:
            details += f", duration {p.duration}"
        await self.cog._gm_log(
            f"[auction builder] {self.owner} ({self.owner.id}) posted {details} {message.jump_url}"
        )

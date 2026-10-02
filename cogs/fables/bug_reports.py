"""GM review queue for in-game Fable bug reports: one report per page."""
import asyncio
import io

import discord

from utils.fable_bugs import FILTERS, MAX_NOTES

STATUS_STYLE = {
    "new": ("🆕", "New", 0xE67E22),
    "reviewing": ("🔎", "Reviewing", 0x3498DB),
    "resolved": ("✅", "Resolved", 0x2ECC71),
    "dismissed": ("🗑️", "Dismissed", 0x95A5A6),
}
FILTER_LABELS = {
    "open": "Open (new + reviewing)",
    "new": "New",
    "reviewing": "Reviewing",
    "resolved": "Resolved",
    "dismissed": "Dismissed",
    "all": "All reports",
}
FABLE_NAMES = {"tiamat": "The Tiamat Sacrament", "crownfall": "Crownfall"}


def _when(value, style="f"):
    return discord.utils.format_dt(value, style=style) if value else "—"


def _location(context):
    parts = []
    if context.get("mapId"):
        where = f"Map {context['mapId']:03d}"
        if "x" in context and "y" in context:
            where += f" at ({context['x']}, {context['y']})"
        parts.append(where)
    if context.get("troopId"):
        parts.append(f"In battle · troop {context['troopId']}")
    if context.get("scene"):
        parts.append(f"Screen: {context['scene'].removeprefix('Scene_')}")
    return "\n".join(parts) or "Not recorded"


def build_report_embed(report, index, total, filter_name, counts):
    """Embed for one report; the screenshot is attached separately."""
    emoji, label, colour = STATUS_STYLE.get(report["status"], ("•", report["status"], 0x7F8C8D))
    context = report.get("client_context") or {}
    fable = FABLE_NAMES.get(report["fable_id"], report["fable_id"].title())
    embed = discord.Embed(title=f"🐞 {fable} bug report", description=report["description"][:4000], colour=colour)
    embed.set_author(name=f"Reported by {report['game_username'][:100]}")
    status = f"{emoji} **{label}**"
    if report.get("reviewed_at") and report["status"] != "new":
        status += f" · {_when(report['reviewed_at'], 'R')}"
    embed.add_field(name="Status", value=status, inline=True)
    reporter = f"`{report['game_username'][:60]}`"
    if report.get("discord_id"):
        reporter += f" · <@{report['discord_id']}>"
    embed.add_field(name="Player", value=reporter, inline=True)
    embed.add_field(name="Submitted", value=f"{_when(report['created_at'])} ({_when(report['created_at'], 'R')})", inline=False)
    embed.add_field(name="Where", value=_location(context), inline=True)
    versions = " · ".join(filter(None, [
        f"Game {context['gameVersion']}" if context.get("gameVersion") else "",
        f"Reporter {context['reporterVersion']}" if context.get("reporterVersion") else "",
    ]))
    embed.add_field(name="Version", value=versions or "Not recorded", inline=True)
    notes = (report.get("reviewer_notes") or "").strip()
    embed.add_field(name="GM notes", value=notes[:1000] + ("…" if len(notes) > 1000 else "") if notes else "None yet", inline=False)
    summary = " · ".join(f"{STATUS_STYLE[key][1]} {counts.get(key, 0)}" for key in STATUS_STYLE)
    embed.set_footer(text=f"Report {index + 1} of {total} · {FILTER_LABELS[filter_name]} · ID {str(report['id'])[:8]}\n{summary}")
    if report.get("has_screenshot"):
        embed.set_image(url=f"attachment://bug-{str(report['id'])[:8]}.jpg")
    return embed


def build_empty_embed(fable_id, filter_name, counts):
    fable = FABLE_NAMES.get(fable_id, fable_id.title()) if fable_id else "All Fables"
    embed = discord.Embed(title="🐞 Bug reports", colour=0x2ECC71,
                          description=f"No **{FILTER_LABELS[filter_name].lower()}** reports for {fable}.")
    embed.set_footer(text=" · ".join(f"{STATUS_STYLE[key][1]} {counts.get(key, 0)}" for key in STATUS_STYLE))
    return embed


class FilterSelect(discord.ui.Select):
    def __init__(self, view):
        self.queue = view
        super().__init__(placeholder="Show reports…", min_values=1, max_values=1, row=0)

    async def callback(self, interaction):
        await self.queue.change_filter(interaction, self.values[0])


class NotesModal(discord.ui.Modal, title="GM notes"):
    def __init__(self, view, report):
        super().__init__(timeout=600)
        self.queue = view
        self.report_id = report["id"]
        self.notes = discord.ui.TextInput(
            label="Notes for this report", style=discord.TextStyle.paragraph, required=False,
            max_length=MAX_NOTES, default=(report.get("reviewer_notes") or "")[:MAX_NOTES],
            placeholder="Cause, fix, version it shipped in…",
        )
        self.add_item(self.notes)

    async def on_submit(self, interaction):
        await self.queue.save_notes(interaction, self.report_id, self.notes.value)


class BugReportQueue(discord.ui.View):
    def __init__(self, owner_id, store, reports, counts, *, fable_id=None, filter_name="open"):
        super().__init__(timeout=900)
        self.owner_id = owner_id
        self.store = store
        self.fable_id = fable_id
        self.filter_name = filter_name
        self.reports = list(reports)
        self.counts = dict(counts)
        self.index = 0
        self.message = None
        self.lock = asyncio.Lock()
        self.selector = FilterSelect(self)
        self.add_item(self.selector)
        self.update_controls()

    def current(self):
        return self.reports[self.index] if self.reports else None

    def update_controls(self):
        report = self.current()
        self.previous.disabled = self.index == 0
        self.next.disabled = not self.reports or self.index >= len(self.reports) - 1
        self.counter.label = f"{self.index + 1} / {len(self.reports)}" if self.reports else "0 / 0"
        for button, status in ((self.reviewing, "reviewing"), (self.resolve, "resolved"),
                               (self.dismiss, "dismissed"), (self.reopen, "new")):
            button.disabled = report is None or report["status"] == status
        self.notes.disabled = report is None
        open_total = self.counts.get("new", 0) + self.counts.get("reviewing", 0)
        totals = {"open": open_total, "all": sum(self.counts.values()), **self.counts}
        self.selector.options = [discord.SelectOption(
            label=label, value=key, default=key == self.filter_name, description=f"{totals.get(key, 0)} report(s)",
        ) for key, label in FILTER_LABELS.items()]

    async def render(self):
        """Embed plus the current report's screenshot (loaded on demand)."""
        report = self.current()
        if report is None:
            return build_empty_embed(self.fable_id, self.filter_name, self.counts), None
        embed = build_report_embed(report, self.index, len(self.reports), self.filter_name, self.counts)
        if not report.get("has_screenshot"):
            return embed, None
        image = await self.store.load_screenshot(report["id"])
        if not image:
            embed.set_image(url=None)
            return embed, None
        return embed, discord.File(io.BytesIO(bytes(image)), filename=f"bug-{str(report['id'])[:8]}.jpg")

    async def show(self, edit):
        self.update_controls()
        embed, file = await self.render()
        try:
            await edit(embed=embed, attachments=[file] if file else [], view=self)
        finally:
            if file:
                file.close()

    async def interaction_check(self, interaction):
        if interaction.user.id == self.owner_id:
            return True
        await interaction.response.send_message("Open your own review queue with `$bugs`.", ephemeral=True)
        return False

    async def navigate(self, interaction, delta):
        await interaction.response.defer()
        async with self.lock:
            if self.is_finished() or not self.reports:
                return
            self.index = max(0, min(len(self.reports) - 1, self.index + delta))
            await self.show(interaction.edit_original_response)

    async def reload(self, interaction, *, keep_id=None):
        """Fetch the list again for the current filter (new reports appear)."""
        self.reports = await self.store.list_reports(fable_id=self.fable_id, statuses=FILTERS[self.filter_name])
        self.counts = await self.store.status_counts(fable_id=self.fable_id)
        ids = [report["id"] for report in self.reports]
        self.index = ids.index(keep_id) if keep_id in ids else min(self.index, max(0, len(self.reports) - 1))
        await self.show(interaction.edit_original_response)

    async def change_filter(self, interaction, filter_name):
        await interaction.response.defer()
        async with self.lock:
            if self.is_finished():
                return
            self.filter_name = filter_name
            self.index = 0
            await self.reload(interaction)

    async def change_status(self, interaction, status):
        await interaction.response.defer()
        async with self.lock:
            report = self.current()
            if self.is_finished() or report is None:
                return
            updated = await self.store.set_status(report["id"], status)
            if updated is None:
                await interaction.followup.send("That report no longer exists.", ephemeral=True)
                return await self.reload(interaction)
            # Keep the report on screen so the change is visible; it leaves a
            # filtered list on the next refresh or filter change.
            self.counts[report["status"]] = max(0, self.counts.get(report["status"], 0) - 1)
            self.counts[status] = self.counts.get(status, 0) + 1
            self.reports[self.index] = updated
            await self.show(interaction.edit_original_response)

    async def save_notes(self, interaction, report_id, notes):
        await interaction.response.defer()
        async with self.lock:
            if self.is_finished():
                return
            updated = await self.store.set_notes(report_id, notes)
            if updated is None:
                await interaction.followup.send("That report no longer exists.", ephemeral=True)
                return
            for position, report in enumerate(self.reports):
                if report["id"] == report_id:
                    self.reports[position] = updated
            if self.message:
                await self.show(self.message.edit)

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
        await self.navigate(interaction, -1)

    @discord.ui.button(label="0 / 0", style=discord.ButtonStyle.secondary, disabled=True, row=1)
    async def counter(self, interaction, button):
        pass

    @discord.ui.button(label="Next", emoji="▶", style=discord.ButtonStyle.primary, row=1)
    async def next(self, interaction, button):
        await self.navigate(interaction, 1)

    @discord.ui.button(label="Refresh", emoji="🔄", style=discord.ButtonStyle.secondary, row=1)
    async def refresh(self, interaction, button):
        await interaction.response.defer()
        async with self.lock:
            if not self.is_finished():
                await self.reload(interaction, keep_id=(self.current() or {}).get("id"))

    @discord.ui.button(label="Reviewing", emoji="🔎", style=discord.ButtonStyle.primary, row=2)
    async def reviewing(self, interaction, button):
        await self.change_status(interaction, "reviewing")

    @discord.ui.button(label="Resolved", emoji="✅", style=discord.ButtonStyle.success, row=2)
    async def resolve(self, interaction, button):
        await self.change_status(interaction, "resolved")

    @discord.ui.button(label="Dismiss", emoji="🗑️", style=discord.ButtonStyle.danger, row=2)
    async def dismiss(self, interaction, button):
        await self.change_status(interaction, "dismissed")

    @discord.ui.button(label="Reopen", emoji="↩", style=discord.ButtonStyle.secondary, row=2)
    async def reopen(self, interaction, button):
        await self.change_status(interaction, "new")

    @discord.ui.button(label="Notes", emoji="📝", style=discord.ButtonStyle.secondary, row=3)
    async def notes(self, interaction, button):
        report = self.current()
        if report is None:
            return await interaction.response.defer()
        await interaction.response.send_modal(NotesModal(self, report))

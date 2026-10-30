"""GM log pagination. Prev/next buttons so older door and manor runs stay reachable."""

from __future__ import annotations

import math

import discord


class LogPages(discord.ui.View):
    def __init__(self, owner_id: int, fetcher, *, timeout: float = 300):
        super().__init__(timeout=timeout)
        self.owner_id = owner_id
        self.fetcher = fetcher
        self.page = 0
        self.total_pages = 1
        self.message = None
        self._sync()

    def _sync(self):
        self.prev_page.disabled = self.page <= 0
        self.next_page.disabled = self.page >= self.total_pages - 1
        self.marker.label = f"{self.page + 1}/{self.total_pages}"

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("This log is for the GM who opened it.", ephemeral=True)
            return False
        return True

    async def _show(self, interaction: discord.Interaction, page: int):
        embed, total_pages = await self.fetcher(page)
        self.total_pages = max(1, int(total_pages))
        self.page = max(0, min(page, self.total_pages - 1))
        if self.page != page:
            embed, total_pages = await self.fetcher(self.page)
            self.total_pages = max(1, int(total_pages))
        self._sync()
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(emoji="◀️", style=discord.ButtonStyle.secondary)
    async def prev_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        del button
        await self._show(interaction, self.page - 1)

    @discord.ui.button(label="1/1", style=discord.ButtonStyle.secondary, disabled=True)
    async def marker(self, interaction: discord.Interaction, button: discord.ui.Button):
        del button
        await interaction.response.defer()

    @discord.ui.button(emoji="▶️", style=discord.ButtonStyle.secondary)
    async def next_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        del button
        await self._show(interaction, self.page + 1)

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        if self.message is None:
            return
        try:
            await self.message.edit(view=self)
        except discord.HTTPException:
            return

    async def send(self, ctx):
        embed, total_pages = await self.fetcher(0)
        self.page = 0
        self.total_pages = max(1, int(total_pages))
        self._sync()
        kwargs = {
            "embed": embed,
            "allowed_mentions": discord.AllowedMentions.none(),
        }
        if self.total_pages > 1:
            kwargs["view"] = self
        self.message = await ctx.send(**kwargs)
        return self.message


def page_count(total: int, size: int) -> int:
    if total <= 0:
        return 1
    return max(1, math.ceil(total / size))

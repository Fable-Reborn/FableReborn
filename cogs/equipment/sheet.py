"""Buttons for the $gear chronicle. The picture stays the armory card."""
from __future__ import annotations

import io

import discord

from classes.equipment.card import render_armory
from classes.equipment.chronicle import THEMES, theme_for


class GearSheetView(discord.ui.View):
    def __init__(self, ctx, loadout: dict, weapons: list[dict], owner=None, theme: str = "chronicle"):
        super().__init__(timeout=180)
        self.ctx = ctx
        self.owner = owner or ctx.author
        self.loadout = loadout
        self.weapons = weapons
        self.focus = "chest"
        self.theme = theme
        if self.owner.id == ctx.author.id:
            self.cover = discord.ui.Select(placeholder="Armory cover", row=2, options=self._cover_options())
            self.cover.callback = self._choose_cover
            self.add_item(self.cover)
        self._paint()

    def _cover_options(self) -> list[discord.SelectOption]:
        return [
            discord.SelectOption(label=spec.label, value=key, default=key == self.theme)
            for key, spec in THEMES.items()
        ]

    async def _choose_cover(self, interaction: discord.Interaction) -> None:
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message("This sheet belongs to someone else.", ephemeral=True)
            return
        from classes.equipment.repository import set_gear_theme

        key = self.cover.values[0]
        async with self.ctx.bot.pool.acquire() as conn:
            if not await set_gear_theme(conn, self.ctx.author.id, key):
                await interaction.response.send_message("That cover is not available.", ephemeral=True)
                return
        self.theme = key
        self.cover.options = self._cover_options()
        await interaction.response.edit_message(embed=self.embed(), attachments=[self.file()], view=self)

    def _paint(self) -> None:
        chosen = {
            "totals": self.show_totals,
            "head": self.show_head,
            "chest": self.show_chest,
            "legs": self.show_legs,
            "feet": self.show_feet,
            "right": self.show_right,
            "left": self.show_left,
        }
        for key, button in chosen.items():
            button.style = discord.ButtonStyle.primary if key == self.focus else discord.ButtonStyle.secondary

    def embed(self) -> discord.Embed:
        embed = discord.Embed(
            title="Armory",
            description="The buttons open the totals, each armor slot, or either hand.",
            color=theme_for(self.theme).accent,
        )
        embed.set_image(url="attachment://armory.png")
        return embed

    def file(self) -> discord.File:
        png = render_armory(
            self.loadout,
            weapons=self.weapons,
            focus=self.focus,
            title=f"{self.owner.display_name}'s Armory",
            subtitle="Starforge and soulbound are included.",
            theme=self.theme,
        )
        return discord.File(io.BytesIO(png), filename="armory.png")

    async def _show(self, interaction: discord.Interaction, focus: str) -> None:
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message("This sheet belongs to someone else.", ephemeral=True)
            return
        self.focus = focus
        self._paint()
        await interaction.response.edit_message(embed=self.embed(), attachments=[self.file()], view=self)

    @discord.ui.button(label="Totals", style=discord.ButtonStyle.secondary, row=0)
    async def show_totals(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._show(interaction, "totals")

    @discord.ui.button(label="Helm", style=discord.ButtonStyle.secondary, row=0)
    async def show_head(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._show(interaction, "head")

    @discord.ui.button(label="Cuirass", style=discord.ButtonStyle.primary, row=0)
    async def show_chest(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._show(interaction, "chest")

    @discord.ui.button(label="Greaves", style=discord.ButtonStyle.secondary, row=0)
    async def show_legs(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._show(interaction, "legs")

    @discord.ui.button(label="Sabatons", style=discord.ButtonStyle.secondary, row=0)
    async def show_feet(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._show(interaction, "feet")

    @discord.ui.button(label="Right hand", style=discord.ButtonStyle.secondary, row=1)
    async def show_right(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._show(interaction, "right")

    @discord.ui.button(label="Left hand", style=discord.ButtonStyle.secondary, row=1)
    async def show_left(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._show(interaction, "left")

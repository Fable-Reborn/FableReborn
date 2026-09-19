"""An owner-only, illustrated collection browser with permanent unlocks."""

import asyncio
import time

import discord

from .themes import ASSET_ROOT, COLLECTIONS, THEMES
from .theme_unlocks import RULES, COLLECTIBLE_THEMES, RARITY_EMOJI, ThemeLocked, save_theme, sync_theme_unlocks


class ProfileThemePicker(discord.ui.View):
    def __init__(self, ctx, state, preview):
        super().__init__(timeout=300)
        self.ctx = ctx
        self.state = state
        self.preview_callback = preview
        self.selected = state.current if state.current != "classic" else "dragon"
        self.collection = THEMES[self.selected].collection
        self.message = None
        self._selection_lock = asyncio.Lock()
        self._last_preview = -float("inf")
        self.collection_select = discord.ui.Select(placeholder="Explore a collection", row=0)
        self.collection_select.callback = self.choose_collection
        self.select = discord.ui.Select(placeholder="Choose a theme you own", row=1)
        self.select.callback = self.choose
        self.add_item(self.collection_select)
        self.add_item(self.select)
        self.refresh_components()

    def refresh_components(self):
        if self.selected not in self.state.unlocked:
            self.selected = self.state.current
        self.collection = THEMES[self.selected].collection
        owned_collections = {THEMES[key].collection for key in self.state.unlocked}
        self.collection_select.options = [
            discord.SelectOption(label=collection, value=collection, default=collection == self.collection)
            for collection in COLLECTIONS if collection in owned_collections
        ]
        self.select.options = [discord.SelectOption(
            label=theme.name, value=theme.key, emoji=theme.emoji,
            description=self._theme_desc(theme.key)[:100],
            default=theme.key == self.selected,
        ) for theme in THEMES.values() if theme.collection == self.collection and theme.key in self.state.unlocked]
        self.equip.disabled = self.selected not in self.state.unlocked or self.selected == self.state.current
        self.preview.disabled = self.selected not in self.state.unlocked
        self.equip.label = "Equipped" if self.selected == self.state.current else "Equip theme"

    def _theme_desc(self, key):
        """Short description for select-option dropdowns (max 100 chars after truncation)."""
        drop = COLLECTIBLE_THEMES.get(key)
        if drop:
            return f"Owned / {RARITY_EMOJI[drop.rarity]} {drop.rarity}"
        return f"Owned / {RULES[key].label}"

    def embed(self):
        self.refresh_components()
        theme = THEMES[self.selected]
        drop = COLLECTIBLE_THEMES.get(self.selected)
        if drop:
            unlock_line = f"{RARITY_EMOJI[drop.rarity]} **{drop.rarity}** · {RULES[theme.key].label}"
        else:
            unlock_line = RULES[theme.key].label
        embed = discord.Embed(
            title=f"{theme.emoji} {theme.name}",
            description=(f"*{theme.epithet}*\n{theme.description}\n\n"
                         f"**{theme.collection} / {theme.rarity}** · Unlocked\n"
                         f"**Unlock:** {unlock_line}\n"
                         "Permanently owned\n\n"
                         f"Equipped: **{THEMES[self.state.current].name}** · "
                         f"Collection: **{len(self.state.unlocked)}/{len(THEMES)}**\n"
                         "Preview and equip your owned themes. Discover more through gameplay."),
            colour=int(theme.accent.lstrip("#"), 16),
        )
        for item in THEMES.values():
            if item.collection == self.collection and item.key in self.state.unlocked:
                status = "Equipped" if item.key == self.state.current else "Owned"
                embed.add_field(name=f"✓ {item.name}",
                                value=f"`{item.key}` · {status}", inline=False)
        if self.state.newly_unlocked:
            names = ", ".join(THEMES[key].name for key in self.state.newly_unlocked)
            embed.add_field(name="Newly unlocked", value=names[:1024], inline=False)
        if not theme.classic and (ASSET_ROOT / f"{theme.key}.png").is_file():
            embed.set_image(url=f"attachment://prpg_theme_{theme.key}.png")
        embed.set_footer(text="Unlocks are permanent / Previews never equip / Menu active for 5 minutes")
        return embed

    def artwork(self):
        if self.selected not in self.state.unlocked:
            return None
        theme = THEMES[self.selected]
        path = ASSET_ROOT / f"{theme.key}.png"
        if theme.classic or not path.is_file():
            return None
        return discord.File(path, filename=f"prpg_theme_{theme.key}.png")

    async def send(self):
        art = self.artwork()
        self.message = await self.ctx.send(embed=self.embed(), view=self, **({"file": art} if art else {}))

    async def edit(self, interaction):
        self.refresh_components()
        art = self.artwork()
        await interaction.message.edit(embed=self.embed(), view=self, attachments=[art] if art else [])

    async def interaction_check(self, interaction):
        if interaction.user.id == self.ctx.author.id:
            return True
        await interaction.response.send_message(
            f"Open your own wardrobe with `{self.ctx.clean_prefix}prpg themes`.", ephemeral=True,
        )
        return False

    async def choose_collection(self, interaction):
        collection = self.collection_select.values[0]
        await interaction.response.defer()
        async with self._selection_lock:
            available = [theme.key for theme in THEMES.values()
                         if theme.collection == collection and theme.key in self.state.unlocked]
            if not available:
                return
            self.collection = collection
            self.selected = available[0]
            await self.edit(interaction)

    async def choose(self, interaction):
        selected = self.select.values[0]
        await interaction.response.defer()
        async with self._selection_lock:
            if selected not in self.state.unlocked:
                return
            self.selected = selected
            self.collection = THEMES[selected].collection
            await self.edit(interaction)

    @discord.ui.button(label="Preview full card", style=discord.ButtonStyle.secondary, row=2)
    async def preview(self, interaction, button):
        selected = self.selected
        now = time.monotonic()
        if now - self._last_preview < 5:
            return await interaction.response.send_message("Give the next preview a few seconds.", ephemeral=True)
        self._last_preview = now
        await interaction.response.defer()
        async with self._selection_lock:
            state = await sync_theme_unlocks(self.ctx.bot.pool, interaction.user.id)
            if state is None:
                return await interaction.followup.send("You need a character to preview themes.", ephemeral=True)
            self.state = state
            await self.edit(interaction)
            if selected not in state.unlocked:
                return await interaction.followup.send("You can only preview themes you own.", ephemeral=True)
        await self.preview_callback(self.ctx, None, theme_key=selected)

    @discord.ui.button(label="Equip theme", style=discord.ButtonStyle.success, row=2)
    async def equip(self, interaction, button):
        selected = self.selected
        await interaction.response.defer(ephemeral=True)
        async with self._selection_lock:
            try:
                saved = await save_theme(self.ctx.bot.pool, interaction.user.id, THEMES[selected])
            except ThemeLocked as error:
                self.state = error.state
                await self.edit(interaction)
                return await interaction.followup.send(f"This theme is still locked. {error}", ephemeral=True)
            if not saved:
                return await interaction.followup.send("You need a character to equip a theme.", ephemeral=True)
            state = await sync_theme_unlocks(self.ctx.bot.pool, interaction.user.id)
            if state is not None:
                self.state = state
            await self.edit(interaction)
            await interaction.followup.send(
                f"{THEMES[selected].emoji} **{THEMES[selected].name}** equipped. View it with `{self.ctx.clean_prefix}prpg`.", ephemeral=True,
            )

    @discord.ui.button(label="Claim progress", style=discord.ButtonStyle.primary, row=2)
    async def claim(self, interaction, button):
        await interaction.response.defer(ephemeral=True)
        async with self._selection_lock:
            state = await sync_theme_unlocks(self.ctx.bot.pool, interaction.user.id)
            if state is None:
                return await interaction.followup.send("You need a character to claim themes.", ephemeral=True)
            self.state = state
            await self.edit(interaction)
            names = ", ".join(THEMES[key].name for key in state.newly_unlocked)
            await interaction.followup.send(f"Unlocked: **{names}**" if names else "Your collection is up to date.", ephemeral=True)

    async def on_timeout(self):
        async with self._selection_lock:
            for child in self.children:
                child.disabled = True
            if self.message is not None:
                try:
                    await self.message.edit(view=self)
                except discord.HTTPException:
                    pass

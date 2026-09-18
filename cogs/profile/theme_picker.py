"""Owner-only cosmetic selection; choices persist in the existing profile row."""

import asyncio

import discord

from .themes import THEMES


async def save_theme(pool, user_id, theme):
    return await pool.fetchval(
        'UPDATE profile SET prpg_theme = $1 WHERE "user" = $2 RETURNING "user";',
        theme.key, user_id,
    ) is not None


class ProfileThemePicker(discord.ui.View):
    def __init__(self, ctx, current):
        super().__init__(timeout=180)
        self.ctx = ctx
        self.message = None
        self._selection_lock = asyncio.Lock()
        select = discord.ui.Select(
            placeholder="Choose a theme to equip",
            options=[discord.SelectOption(
                label=t.name, value=t.key, emoji=t.emoji,
                description=t.description, default=t.key == current,
            ) for t in THEMES.values()],
        )
        select.callback = self.choose
        self.select = select
        self.add_item(select)

    async def interaction_check(self, interaction):
        if interaction.user.id == self.ctx.author.id:
            return True
        await interaction.response.send_message(
            f"Open your own wardrobe with `{self.ctx.clean_prefix}prpg themes`.", ephemeral=True,
        )
        return False

    async def choose(self, interaction):
        theme = THEMES[self.select.values[0]]
        await interaction.response.defer(ephemeral=True)
        async with self._selection_lock:
            if not await save_theme(self.ctx.bot.pool, interaction.user.id, theme):
                return await interaction.followup.send("You need a character to equip a theme.", ephemeral=True)
            for option in self.select.options:
                option.default = option.value == theme.key
            embed = interaction.message.embeds[0].copy()
            instructions = embed.description.split("\n", 1)[1]
            embed.description = f"Equipped: **{theme.name}**\n{instructions}"
            embed.colour = int(theme.accent.lstrip("#"), 16)
            try:
                await interaction.message.edit(embed=embed, view=self)
            except discord.HTTPException:
                pass  # The saved choice still succeeds if the menu was deleted.
            await interaction.followup.send(
                f"{theme.emoji} **{theme.name}** equipped. View it with `{self.ctx.clean_prefix}prpg`.",
                ephemeral=True,
            )

    async def on_timeout(self):
        async with self._selection_lock:
            self.select.disabled = True
            if self.message is not None:
                try:
                    await self.message.edit(view=self)
                except discord.HTTPException:
                    pass

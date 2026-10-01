"""Companions: characters from Tiamat Sacrament that players unlock and choose.

`companions` stores one row per player: the keys of the companions they have
unlocked (a text array) and the one they have selected. The roster lives in
roster.py and the select screen is drawn by card.py; locked companions show as
silhouettes named "???" with only their alignment revealed.
"""

import asyncio

import discord
from discord.ext import commands

from utils.checks import has_char, is_gm

from . import card
from .roster import COMPANIONS, GOOD, find

VIEW_SECONDS = 180
CARD_FILENAME = "companions.jpg"


class CompanionSelect(discord.ui.Select):
    def __init__(self, view):
        super().__init__(placeholder="Jump to a companion…", row=0, options=view.options())

    async def callback(self, interaction):
        await self.view.show(interaction, int(self.values[0]))


class CompanionView(discord.ui.View):
    def __init__(self, cog, author, unlocked, selected):
        super().__init__(timeout=VIEW_SECONDS)
        self.cog = cog
        self.author = author
        self.unlocked = set(unlocked)
        self.selected = selected
        self.index = next((i for i, c in enumerate(COMPANIONS) if c.key == selected), 0)
        self.message = None
        self.add_item(CompanionSelect(self))

    def options(self):
        options = []
        for i, companion in enumerate(COMPANIONS):
            known = companion.key in self.unlocked
            alignment = companion.alignment.capitalize()
            options.append(discord.SelectOption(
                label=companion.name if known else f"??? #{i + 1}",
                value=str(i),
                description=f"{alignment} · {companion.title}" if known else f"{alignment} · Locked",
                emoji=("😇" if companion.alignment == GOOD else "😈") if known else "🔒",
                default=i == self.index,
            ))
        return options

    async def render(self):
        buffer = await asyncio.to_thread(card.render_select_card, self.index, frozenset(self.unlocked), self.selected)
        return discord.File(buffer, filename=CARD_FILENAME)

    def embed(self):
        companion = COMPANIONS[self.index]
        known = companion.key in self.unlocked
        colour = discord.Colour.from_rgb(*companion.accent) if known else discord.Colour.dark_grey()
        embed = discord.Embed(colour=colour)
        embed.set_author(name=f"{self.author.display_name}'s companions", icon_url=self.author.display_avatar.url)
        embed.set_image(url=f"attachment://{CARD_FILENAME}")
        current = next((c.name for c in COMPANIONS if c.key == self.selected), None)
        embed.set_footer(text=f"Companion: {current}" if current else "No companion selected")
        return embed

    def refresh_items(self):
        for item in self.children:
            if isinstance(item, CompanionSelect):
                item.options = self.options()
            elif isinstance(item, discord.ui.Button) and item.custom_id == "companion:select":
                companion = COMPANIONS[self.index]
                item.disabled = companion.key not in self.unlocked or companion.key == self.selected
                item.label = "Selected" if companion.key == self.selected else "Select"

    async def show(self, interaction, index):
        self.index = index % len(COMPANIONS)
        self.refresh_items()
        await interaction.response.defer()
        await interaction.edit_original_response(embed=self.embed(), attachments=[await self.render()], view=self)

    async def interaction_check(self, interaction):
        if interaction.user.id != self.author.id:
            await interaction.response.send_message("These aren't your companions.", ephemeral=True)
            return False
        return True

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        if self.message is not None:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass

    @discord.ui.button(label="Previous", emoji="◀️", style=discord.ButtonStyle.secondary, row=1)
    async def previous_page(self, interaction, button):
        await self.show(interaction, self.index - 1)

    @discord.ui.button(label="Select", emoji="✅", style=discord.ButtonStyle.success, row=1,
                       custom_id="companion:select")
    async def choose(self, interaction, button):
        companion = COMPANIONS[self.index]
        if companion.key not in self.unlocked:
            return await interaction.response.send_message("That companion is still locked.", ephemeral=True)
        await self.cog.set_selected(self.author.id, companion.key)
        self.selected = companion.key
        await self.show(interaction, self.index)
        await interaction.followup.send(f"**{companion.name}** will now travel with you.", ephemeral=True)

    @discord.ui.button(label="Next", emoji="▶️", style=discord.ButtonStyle.secondary, row=1)
    async def next_page(self, interaction, button):
        await self.show(interaction, self.index + 1)


class Companions(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def cog_load(self):
        async with self.bot.pool.acquire() as conn:
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS companions (
                    user_id BIGINT PRIMARY KEY,
                    unlocked TEXT[] NOT NULL DEFAULT '{}',
                    selected TEXT
                );
                """
            )

    async def get_row(self, user_id):
        row = await self.bot.pool.fetchrow(
            "SELECT unlocked, selected FROM companions WHERE user_id = $1", user_id
        )
        return (list(row["unlocked"]), row["selected"]) if row else ([], None)

    async def set_selected(self, user_id, key):
        await self.bot.pool.execute(
            """
            INSERT INTO companions (user_id, selected) VALUES ($1, $2)
            ON CONFLICT (user_id) DO UPDATE SET selected = EXCLUDED.selected
            """,
            user_id, key,
        )

    async def unlock(self, user_id, key):
        """Add a companion to a player's unlocks. Returns False if they already had it."""
        status = await self.bot.pool.execute(
            """
            INSERT INTO companions (user_id, unlocked) VALUES ($1, ARRAY[$2::text])
            ON CONFLICT (user_id) DO UPDATE SET unlocked = array_append(companions.unlocked, $2::text)
            WHERE NOT ($2::text = ANY(companions.unlocked))
            """,
            user_id, key,
        )
        return status.endswith("1")

    @commands.command(aliases=["companion"], brief="Browse and choose your companion")
    @has_char()
    async def companions(self, ctx):
        """Browse the companion roster and pick who travels with you.

        Locked companions appear as silhouettes; only their alignment is known."""
        unlocked, selected = await self.get_row(ctx.author.id)
        view = CompanionView(self, ctx.author, unlocked, selected)
        view.refresh_items()
        async with ctx.typing():
            file = await view.render()
        view.message = await ctx.send(embed=view.embed(), file=file, view=view)

    @is_gm()
    @commands.command(hidden=True, brief="Unlock a companion for a player")
    async def companionunlock(self, ctx, member: discord.User, *, companion: str):
        """`<member>` - who receives it
        `<companion>` - azuar, ryjin or gyle

        Only Game Masters can use this command."""
        target = find(companion)
        if target is None:
            names = ", ".join(c.key for c in COMPANIONS)
            return await ctx.send(f"Unknown companion. Choose from: {names}")
        if await self.unlock(member.id, target.key):
            await ctx.send(f"Unlocked **{target.name}** for {member.mention}.")
        else:
            await ctx.send(f"{member.mention} already has **{target.name}**.")


async def setup(bot):
    await bot.add_cog(Companions(bot))

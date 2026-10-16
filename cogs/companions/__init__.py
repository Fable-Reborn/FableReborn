"""Companions: characters from Tiamat Sacrament that players unlock and choose.

`companions` stores one row per player: the keys of the companions they have
unlocked (a text array) and the one they have selected. The roster lives in
roster.py and the select screen is drawn by card.py; locked companions show as
silhouettes named "???" with only their alignment revealed, and secret ones
reveal nothing at all.
"""

import asyncio
import logging

import discord
from discord.ext import commands, tasks

from classes.badges import Badge
from utils import tiamat_unlocks
from utils.checks import has_char, is_gm

from . import card
from .roster import COMPANIONS, GOOD, find

VIEW_SECONDS = 180
CARD_FILENAME = "companions.jpg"
BADGE_SYNC_MINUTES = 10
log = logging.getLogger(__name__)


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
            alignment = "Secret" if companion.secret and not known else companion.alignment.capitalize()
            options.append(discord.SelectOption(
                label=companion.name if known else f"??? #{i + 1}",
                value=str(i),
                description=f"{alignment} · {companion.title}" if known else f"{alignment} · Locked",
                emoji=("😇" if companion.alignment == GOOD else "😈") if known else "❔" if companion.secret else "🔒",
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
            await tiamat_unlocks.ensure_table(conn)
        self.sync_tiamat_badges.start()

    async def cog_unload(self):
        self.sync_tiamat_badges.cancel()

    # The Clutch of Ilisrei badge, for everyone who has finished Tiamat and has a
    # character. Rewards land in the database from the game server at any time, so
    # this sweeps on a timer rather than waiting for a command.
    @tasks.loop(minutes=BADGE_SYNC_MINUTES)
    async def sync_tiamat_badges(self):
        try:
            await self.grant_clutch_badges()
        except Exception:
            log.exception("Tiamat badge sync failed")

    @sync_tiamat_badges.before_loop
    async def before_badge_sync(self):
        await self.bot.wait_until_ready()

    async def grant_clutch_badges(self) -> int:
        """Gives the badge to every earner who doesn't have it yet. Returns how many."""
        granted = 0
        async with self.bot.pool.acquire() as conn:
            users = await tiamat_unlocks.users_with(conn, tiamat_unlocks.CLUTCH_BADGE)
            if not users:
                return 0
            rows = await conn.fetch('SELECT "user", "badges" FROM profile WHERE "user" = ANY($1::bigint[]);', users)
            for row in rows:
                try:
                    current = Badge(0) if row["badges"] is None else Badge.from_db(row["badges"])
                except Exception:
                    current = Badge(0)
                if current & Badge.CLUTCH_OF_ILISREI:
                    continue
                await conn.execute('UPDATE profile SET "badges" = $1 WHERE "user" = $2;',
                                   (current | Badge.CLUTCH_OF_ILISREI).to_db(), row["user"])
                granted += 1
        if granted:
            log.info("Granted the Clutch of Ilisrei badge to %s player(s)", granted)
        return granted

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

        Locked companions appear as silhouettes; only their alignment is known.
        Some companions are secret and reveal nothing until found."""
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
        `<companion>` - azuar, ryjin, gyle, xandra or tiamat

        Only Game Masters can use this command."""
        target = find(companion)
        if target is None:
            names = ", ".join(c.key for c in COMPANIONS)
            return await ctx.send(f"Unknown companion. Choose from: {names}")
        if await self.unlock(member.id, target.key):
            await ctx.send(f"Unlocked **{target.name}** for {member.mention}.")
        else:
            await ctx.send(f"{member.mention} already has **{target.name}**.")


    @is_gm()
    @commands.command(hidden=True, brief="Grant a Tiamat reward in Fable")
    async def tiamatunlock(self, ctx, member: discord.User, key: str):
        """`<member>` - who receives it
        `<key>` - dragonkin, clutch_badge, penitent or breathcaller

        Normally the Tiamat server grants these. Only Game Masters can use this command."""
        key = key.lower()
        if key not in tiamat_unlocks.KEYS:
            return await ctx.send("Unknown reward. Choose from: " + ", ".join(sorted(tiamat_unlocks.KEYS)))
        status = await self.bot.pool.execute(
            """INSERT INTO tiamat_unlocks (user_id, unlock_key, source) VALUES ($1, $2, $3)
               ON CONFLICT (user_id, unlock_key) DO NOTHING""",
            member.id, key, f"gm:{ctx.author.id}",
        )
        if key == tiamat_unlocks.CLUTCH_BADGE:
            await self.grant_clutch_badges()
        await ctx.send(f"Granted **{key}** to {member.mention}." if status.endswith("1")
                       else f"{member.mention} already has **{key}**.")


async def setup(bot):
    await bot.add_cog(Companions(bot))

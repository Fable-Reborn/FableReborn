import logging
import random

import asyncpg
import discord
from discord.ext import commands

from utils.checks import is_gm
from utils.fable_bugs import FILTERS, BugReportStore
from utils.fables import (
    GAME_URL,
    HOW_TO_UNLOCK,
    TIAMAT,
    complete_fable,
    dragon_unlocks_tiamat,
    tower_unlocks_tiamat,
    unlock_fable,
    unlocked_fables,
)
from .bug_reports import BugReportQueue
from .showcase import FableShowcase

log = logging.getLogger(__name__)

PLAY_LINE = f"Play at {GAME_URL} (first time? `$link` gets you the code to make your account)."


class Fables(commands.Cog):
    """Playable stories on the web, linked to your profile."""

    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="fables", brief="See your unlocked playable stories")
    async def fables(self, ctx):
        """Your Fables: story games played on the web at https://game.fablereborn.xyz with your linked account.

        The Fables Library is open to every linked account (`{prefix}link`). The Tiamat Sacrament unlocks once you've
        reached Battle Tower prestige 5: opening the hidden Door 4 at the end of the Battle Tower always unlocks it, and each
        Ice Dragon Challenge win has a 5% chance to."""
        try:
            rows = await unlocked_fables(self.bot.pool, ctx.author.id)
            if not rows:
                return await ctx.send(
                    f"You haven't unlocked any Fables yet.\n\n{HOW_TO_UNLOCK}\n\n"
                    f"The Fables Library is open to everyone: {PLAY_LINE}"
                )
            view = FableShowcase(ctx.author.id, ctx.author.display_name, rows, ctx.author.display_avatar.url)
            embed, file = view.page()
            try:
                view.message = await ctx.send(PLAY_LINE, embed=embed, files=[file] if file else [], view=view)
            finally:
                if file:
                    file.close()
        except Exception as e:
            print(f"Error in fables command: {e}")
            await ctx.send(f"An error occurred while processing your request. {e}")

    async def grant_tiamat(self, ctx, user, source, line):
        """Unlocks The Tiamat Sacrament for `user` and says so in the channel. False if they already had it."""
        try:
            if not await unlock_fable(self.bot.pool, user.id, TIAMAT, source=source):
                return False
        except ValueError:
            log.warning("The Tiamat Sacrament is missing or disabled in `fables`; %s not unlocked", user.id)
            return False
        await ctx.send(f"🐉 {line}\n**{user.mention} has unlocked The Tiamat Sacrament!** {PLAY_LINE}")
        return True

    @commands.Cog.listener()
    async def on_battletower_ending(self, ctx, door_key, prestige):
        try:
            if tower_unlocks_tiamat(door_key, prestige):
                await self.grant_tiamat(
                    ctx, ctx.author, f"battletower:{door_key}:p{int(prestige)}",
                    "Beyond the fourth door lies a library, and a book bound in dragon scale falls open for you.",
                )
        except Exception:
            log.exception("Could not unlock Tiamat for Battle Tower ending of %s", ctx.author.id)

    @commands.Cog.listener()
    async def on_icedragon_victory(self, ctx, party_members, stage_name, dragon_level):
        for member in party_members:
            try:
                prestige = await self.bot.pool.fetchval(
                    "SELECT COALESCE(prestige, 0) FROM battletower WHERE id = $1", member.id
                ) or 0
                if not dragon_unlocks_tiamat(prestige, random.random()):
                    continue
                await self.grant_tiamat(
                    ctx, member, f"icedragon:{stage_name}",
                    "Frozen in the Ice Dragon's hoard is a book bound in dragon scale.",
                )
            except Exception:
                log.exception("Could not roll the Tiamat unlock for %s", member.id)

    @commands.command(name="unlockfable", hidden=True)
    @is_gm()
    async def unlockfable(self, ctx, user: discord.User, fable_id: str):
        try:
            try:
                created = await unlock_fable(self.bot.pool, user.id, fable_id, source=f"gm:{ctx.author.id}")
            except ValueError as error:
                return await ctx.send(str(error))
            await ctx.send(f"{user.display_name}: {fable_id} " + ("unlocked." if created else "was already unlocked."))
        except Exception as e:
            print(f"Error in unlockfable command: {e}")
            await ctx.send(f"An error occurred while processing your request. {e}")


    @commands.command(name="completefable", hidden=True)
    @is_gm()
    async def completefable(self, ctx, user: discord.User, fable_id: str):
        changed = await complete_fable(self.bot.pool, user.id, fable_id)
        await ctx.send(f"{user.display_name}: {fable_id} " + (
            "marked completed." if changed else "is already completed or has not been unlocked."
        ))


    @commands.command(name="bugs", hidden=True, brief="Review in-game Fable bug reports")
    @is_gm()
    async def bugs(self, ctx, *filters: str):
        """$bugs [fable] [open|new|reviewing|resolved|dismissed|all]  e.g. $bugs tiamat all"""
        try:
            fable_id, filter_name = None, "open"
            for value in (item.strip().lower() for item in filters):
                if value in FILTERS:
                    filter_name = value
                elif value:
                    fable_id = value
            if fable_id and not await self.bot.pool.fetchval("SELECT 1 FROM fables WHERE id=$1", fable_id):
                return await ctx.send(f"There is no Fable called `{fable_id[:40]}`.")
            store = BugReportStore(self.bot.pool)
            try:
                reports = await store.list_reports(fable_id=fable_id, statuses=FILTERS[filter_name])
                counts = await store.status_counts(fable_id=fable_id)
            except asyncpg.UndefinedTableError:
                return await ctx.send("No bug reports yet: the game server creates `fable_bug_reports` the first time it starts.")
            view = BugReportQueue(ctx.author.id, store, reports, counts, fable_id=fable_id, filter_name=filter_name)
            embed, file = await view.render()
            try:
                view.message = await ctx.send(embed=embed, files=[file] if file else [], view=view)
            finally:
                if file:
                    file.close()
        except Exception as e:
            # The global handler hides Discord HTTP errors, so report everything here.
            detail = getattr(e, "text", "") or str(e)
            await ctx.send(f"An error occurred in bugs: `{type(e).__name__}: {detail[:1500]}`")


async def setup(bot):
    await bot.add_cog(Fables(bot))

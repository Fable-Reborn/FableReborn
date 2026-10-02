import asyncpg
import discord
from discord.ext import commands

from utils.checks import is_gm
from utils.fable_bugs import FILTERS, BugReportStore
from utils.fables import complete_fable, unlock_fable, unlocked_fables
from .bug_reports import BugReportQueue
from .showcase import FableShowcase


class Fables(commands.Cog):
    """Playable stories. GM-only while the feature is being tested."""

    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="fables", brief="See your unlocked playable stories")
    @is_gm()
    async def fables(self, ctx):
        try:
            rows = await unlocked_fables(self.bot.pool, ctx.author.id)
            if not rows:
                return await ctx.send("You have not unlocked any Fables yet.")
            view = FableShowcase(ctx.author.id, ctx.author.display_name, rows, ctx.author.display_avatar.url)
            embed, file = view.page()
            try:
                view.message = await ctx.send(embed=embed, files=[file] if file else [], view=view)
            finally:
                if file:
                    file.close()
        except Exception as e:
            print(f"Error in fables command: {e}")
            await ctx.send(f"An error occurred while processing your request. {e}")

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


async def setup(bot):
    await bot.add_cog(Fables(bot))

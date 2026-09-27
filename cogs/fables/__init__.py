import discord
from discord.ext import commands

from utils.checks import is_gm
from utils.fables import unlock_fable, unlocked_fables


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
            for offset in range(0, len(rows), 20):
                embed = discord.Embed(title="Your Fables", colour=discord.Colour.gold())
                embed.description = "Stories you have unlocked and can play with your linked game account."
                for row in rows[offset:offset + 20]:
                    embed.add_field(name=row["title"][:256], value=row["description"][:1024], inline=False)
                await ctx.send(embed=embed)
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


async def setup(bot):
    await bot.add_cog(Fables(bot))

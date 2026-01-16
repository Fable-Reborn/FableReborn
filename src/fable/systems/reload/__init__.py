"""
The IdleRPG Discord Bot
Copyright (C) 2018-2021 Diniboy and Gelbpunkt
Copyright (C) 2023-2024 Lunar (PrototypeX37)

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU Affero General Public License for more details.

You should have received a copy of the GNU Affero General Public License
along with this program.  If not, see <https://www.gnu.org/licenses/>.
"""
import importlib
import sys

import discord
from discord.ext import commands

from fable.utils.checks import is_gm


class ReloadCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @is_gm()
    @commands.command(name="unload", hidden=True)
    async def unload_cog(self, ctx, cog_name: str):
        try:

            # Unload the existing cog
            await ctx.send("Unloading Cog...")
            await self.bot.unload_extension(f"fable.systems.{cog_name}")
            await ctx.send(f"{cog_name} has been unloaded.")
        except Exception as e:
            await ctx.send(f"An error occurred: {e}")

    @is_gm()
    @commands.command(name="load", hidden=True)
    async def load_cog(self, ctx, cog_name: str):
        try:

            # Unload the existing cog
            await ctx.send("Loading Cog...")
            # Reload the cog using Discord.py's reload_extension
            await self.bot.load_extension(f"fable.systems.{cog_name}")
            await ctx.send(f"{cog_name} has been loaded.")
        except Exception as e:

            await ctx.send(e)
            print(e)

    @is_gm()
    @commands.command(name="reload", hidden=True)
    async def reload(self, ctx, cog: str):
        try:
            self.bot.unload_extension(f"fable.systems.{cog}")
            importlib.reload(importlib.import_module(f"fable.systems.{cog}"))
            self.bot.load_extension(f"fable.systems.{cog}")
            await ctx.send(f"Successfully reloaded cog: {cog}")
        except Exception as e:
            await ctx.send(f"Failed to reload cog: {cog}\n{type(e).__name__}: {e}")


async def setup(bot):
    await bot.add_cog(ReloadCog(bot))

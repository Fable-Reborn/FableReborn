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
import asyncio

import discord
import io

from aiohttp import ContentTypeError
from discord.ext import commands
from asyncio import sleep

from fable.core.badges import Badge
from fable.core.bot import Bot
from fable.core.classes import from_string as class_from_string
from fable.core.context import Context
from fable.core.converters import IntFromTo, MemberWithCharacter, UserWithCharacter
from fable.core.items import ALL_ITEM_TYPES, ItemType
from fable.systems.adventure import ADVENTURE_NAMES
from fable.systems.help import chunks
from fable.systems.shard_communication import user_on_cooldown as user_cooldown
from fable.utils import checks, colors
from fable.utils.checks import has_char, is_gm, is_god
from fable.utils import misc as rpgtools
from fable.utils.i18n import _, locale_doc

"""This is ancient and never ended up being used"""

class Story(commands.Cog):
    def __init__(self, bot: Bot) -> None:
        self.bot = bot

    @is_gm()
    @commands.command(hidden=True)
    async def startstory(self, ctx):


        embed = discord.Embed(title="The War of Eldoria", color=0x2f3136)
        embed.description = ("In the realm of Eldoria, three gods have awoken from their slumber. "
                             "A clash of beliefs and desires ignites a fierce war. "
                             "Drakath, Astraea, and Sepulchure, each commanding their legions, "
                             "seek the Eldoria Nexus - a relic of power that can tip the balance. "
                             "You, as one of the chosen, embark on this quest to determine the fate of Eldoria.\n"
                             "\n"
                             "**Warning**: This is a player choice driven story. Your choices will impact your story")
        embed.set_image(url="https://i.ibb.co/Y21nKdm/image-random-Zr-T2-XQk4-1674935572041-1024.png")
        await ctx.send(embed=embed)  # Send the general prologue first.

        await asyncio.sleep(10)  # Corrected the sleep function

        await ctx.send("Getting player data ready. Please wait..")

        await asyncio.sleep(5)

        async with self.bot.pool.acquire() as conn:
            profile = await conn.fetchrow('SELECT * FROM profile WHERE "user"=$1;', ctx.author.id)

            if not profile:
                return

            god_specific_embed = discord.Embed()  # Create a new embed for god-specific message
            god = profile["god"]
            if god == "Drakath":
                god_specific_embed.color = 0x3498db
                god_specific_embed.description = (
                    "Champion of Chaos, Drakath has sensed your loyalty. As the winds of unpredictability howl, "
                    "you are called upon to harness the chaos and claim the Nexus for a world without rules.")
            elif god == "Astraea":
                god_specific_embed.color = 0xf1c40f
                god_specific_embed.description = (
                    "Disciple of Justice, Astraea beckons you. The celestial call resonates, urging you to seek "
                    "the Nexus and establish a harmonious Eldoria, pure and just.")
            elif god == "Sepulchure":
                god_specific_embed.color = 0xe74c3c
                god_specific_embed.description = (
                    "Warrior of the Shadows, Sepulchure has marked you. The whispers of the undead guide your path, "
                    "leading you to the Nexus to cast an eternal night over Eldoria.")

            god_specific_embed.add_field(name="Your Quest Begins!",
                                         value="React with ✨ to embark on your journey, or ❌ to return to your mundane life.")
            message = await ctx.send(embed=god_specific_embed)
            await message.add_reaction("✨")
            await message.add_reaction("❌")

            def check(reaction, user):
                return user == ctx.author and str(reaction.emoji) in ["✨", "❌"]

            reaction, user = await self.bot.wait_for("reaction_add", timeout=60.0, check=check)

            if str(reaction.emoji) == "✨":
                await self.start_journey(ctx, god)
            elif str(reaction.emoji) == "❌":
                await ctx.send("Perhaps another time, adventurer.")


    async def start_journey(self, ctx, god):
        # Here you'd place the logic for the beginning of the actual journey tailored to each god
        if god == "Drakath":
            await ctx.send("The winds of chaos guide your path as you embark on a journey full of unpredictability...")
        elif god == "Astraea":
            await ctx.send("With the blessings of the stars, you set forth to bring justice and harmony to Eldoria...")
        elif god == "Sepulchure":
            await ctx.send("The shadows whisper tales of power and conquest as you start your dark quest...")


async def setup(bot):
    await bot.add_cog(Story(bot))

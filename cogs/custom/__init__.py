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
import copy
import io
import re
import textwrap
import traceback

from contextlib import redirect_stdout

import discord

from discord.ext import commands

from classes.bot import Bot
from classes.context import Context
from classes.converters import MemberWithCharacter
from utils import misc as rpgtools
from utils.i18n import _, locale_doc
from utils.markdown import escape_markdown


class Custom(commands.Cog):
    def __init__(self, bot: Bot):
        self.bot = bot
        self._last_result = None
        ids_section = getattr(self.bot.config, "ids", None)
        custom_ids = getattr(ids_section, "custom", {}) if ids_section else {}
        if not isinstance(custom_ids, dict):
            custom_ids = {}
        self.givedivine_allowed_user_id = custom_ids.get("givedivine_allowed_user_id")
        self.hottest_allowed_user_id = custom_ids.get("hottest_allowed_user_id")
        self.hottest_target_user_id = custom_ids.get("hottest_target_user_id")

    @commands.command(breif=_("Gift a crate"))
    @locale_doc
    async def givedivine(self, ctx, amount: int, other: MemberWithCharacter):
        if self.givedivine_allowed_user_id and ctx.author.id == self.givedivine_allowed_user_id:
            await ctx.send(
                _("Successfully gave {amount} divine crate(s) to {other}.").format(
                    amount=amount, other=other.mention
                )
            )

    @commands.command(brief=_("Show the top 10 in horde"))
    @locale_doc
    async def hottest(self, ctx: Context) -> None:
        try:

            if not self.hottest_allowed_user_id or ctx.author.id != self.hottest_allowed_user_id:

                await ctx.send("You do not have access to this custom command.")
                return

            _("""🔥 The 10 hottest players in Fable. 🔥""")
            await ctx.typing()

            await ctx.send("pfft.. Thats no contest!")
            await asyncio.sleep(1)

            user_id = self.hottest_target_user_id
            if not user_id:
                await ctx.send("This command target user is not configured.")
                return
            guild = ctx.guild  # Assuming you have access to the guild context

            try:
                player_info = await self.bot.pool.fetchrow(
                    'SELECT "name" FROM profile WHERE "user" = $1;', user_id
                )
                user = await self.bot.fetch_user(user_id)
                username = user.name
            except discord.NotFound:
                # Handle the case when the member is not found
                username = "UnknownUser"

            result = ""
            for idx in range(10):
                text = _("{name}, a character by {username} with a score of **11/10**").format(
                    name=escape_markdown(player_info["name"]),
                    username=escape_markdown(username),
                )
                result = f"{result}{idx + 1}. {text}\n"

            result = discord.Embed(
                title=_("🔥 The Hottest Players 🔥"), description=result, colour=0xE7CA01
            )
            await ctx.send(embed=result)

        except Exception as e:
            # Handle other exceptions if needed
            await ctx.send(f"An error occurred: {e}")


async def setup(bot):
    await bot.add_cog(Custom(bot))

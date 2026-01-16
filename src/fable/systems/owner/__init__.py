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
import copy
import io
import re
import textwrap
import traceback

from contextlib import redirect_stdout

import discord

from discord.ext import commands

from fable.utils.checks import has_char, is_gm
from fable.core.badges import Badge, BadgeConverter
from fable.core.bot import Bot
from fable.core.context import Context
from fable.core.converters import UserWithCharacter
from fable.utils import shell
from fable.utils.misc import random_token


class Owner(commands.Cog):
    def __init__(self, bot: Bot):
        self.bot = bot
        self._last_result = None

    #async def cog_check(self, ctx: Context) -> bool:
       # return await self.bot.is_owner(ctx.author)



async def setup(bot):
    await bot.add_cog(Owner(bot))

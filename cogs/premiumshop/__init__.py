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
import datetime
import discord

from discord.ext import commands

from utils.checks import has_char, is_gm
from utils.i18n import _, locale_doc
from classes.converters import IntGreaterThan
from cogs.shard_communication import user_on_cooldown as user_cooldown


class PremiumShop(commands.Cog):
    def __init__(self, bot):
        self.bot = bot




async def setup(bot):
    await bot.add_cog(PremiumShop(bot)) 

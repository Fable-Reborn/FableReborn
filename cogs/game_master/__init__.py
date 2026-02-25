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
import datetime
import secrets
from asyncio import subprocess
from collections import defaultdict
import csv

import aiohttp
import discord
import discord
from discord.ext import commands
from discord.ui import View, Button
from utils import misc as rpgtools

from discord import Object, HTTPException
from PIL import Image
import io
import aiohttp
from asyncpg.exceptions import UniqueViolationError
from discord.ext import commands
from discord.http import handle_message_parameters
import json

from classes.converters import CrateRarity, IntFromTo, IntGreaterThan, UserWithCharacter
from classes.items import ItemType
from cogs.battles.extensions.elements import ElementExtension
from cogs.shard_communication import user_on_cooldown as user_cooldown
from utils import random
from utils.checks import has_char, is_gm
from utils.i18n import _, locale_doc

import copy
import io
import re
import textwrap
import traceback

from contextlib import redirect_stdout

import discord

from discord.ext import commands

from utils.checks import has_char, is_gm, is_god
from classes.badges import Badge, BadgeConverter
from classes.bot import Bot
from classes.context import Context
from classes.converters import UserWithCharacter
from utils import shell
from utils.misc import random_token
from typing import Union

CHANNEL_BLACKLIST = ['⟢super-secrets〡🤫', '⟢god-spammit〡💫', '⟢gm-logs〡📝', 'Accepted Suggestions']
CATEGORY_NAME = '╰• ☣ | ☣ FABLE RPG ☣ | ☣ •╯'


class GameMaster(commands.Cog):
    EVENT_DISPLAY_NAMES = {
        "halloween": "Halloween",
        "wintersday": "Wintersday",
        "lunar_new_year": "Lunar New Year",
        "valentine": "Valentine",
        "snowballfight": "Snowball Fight",
    }
    EVENT_DEFAULTS = {
        "halloween": False,
        "wintersday": False,
        "lunar_new_year": False,
        "valentine": False,
        "snowballfight": False,
    }
    EVENT_ALIASES = {
        "halloween": "halloween",
        "spooky": "halloween",
        "spookyshop": "halloween",
        "ss": "halloween",
        "wintersday": "wintersday",
        "winter": "wintersday",
        "christmas": "wintersday",
        "xmas": "wintersday",
        "cs": "wintersday",
        "lunar": "lunar_new_year",
        "lny": "lunar_new_year",
        "lunar_new_year": "lunar_new_year",
        "lunarnewyear": "lunar_new_year",
        "lunar new year": "lunar_new_year",
        "valentine": "valentine",
        "valentines": "valentine",
        "snowballfight": "snowballfight",
        "snowball": "snowballfight",
        "snowball_fight": "snowballfight",
        "snowball fight": "snowballfight",
        "snowball-fight": "snowballfight",
    }
    EVENT_SHOP_DEFAULTS = {
        "halloween": {
            "ssuncommon": 10,
            "ssrare": 5,
            "ssmagic": 3,
            "sslegendary": 2,
            "ssfortune": 1,
            "ssdivine": 1,
            "ssbg": 1,
            "ssclass": 1,
            "sstoken": 5,
            "sstot": 10,
        },
        "lunar_new_year": {
            "lnyuncommon": 10,
            "lnyrare": 5,
            "lnymagic": 3,
            "lnylegendary": 2,
            "lnyfortune": 1,
            "lnydivine": 1,
            "lnytoken": 5,
            "lnybag": 10,
        },
    }
    GM_CONSUMABLE_ALIASES = {
        "petage": {"consumable_type": "pet_age_potion", "display_name": "Pet Age Potion"},
        "pet age potion": {"consumable_type": "pet_age_potion", "display_name": "Pet Age Potion"},
        "pet speed growth potion": {
            "consumable_type": "pet_speed_growth_potion",
            "display_name": "Pet Speed Growth Potion",
        },
        "petspeed": {
            "consumable_type": "pet_speed_growth_potion",
            "display_name": "Pet Speed Growth Potion",
        },
        "pet xp potion": {"consumable_type": "pet_xp_potion", "display_name": "Pet XP Potion"},
        "petxp": {"consumable_type": "pet_xp_potion", "display_name": "Pet XP Potion"},
        "weapelement": {
            "consumable_type": "weapon_element_scroll",
            "display_name": "Weapon Element Scroll",
        },
        "weapon element scroll": {
            "consumable_type": "weapon_element_scroll",
            "display_name": "Weapon Element Scroll",
        },
        "elementscroll": {
            "consumable_type": "weapon_element_scroll",
            "display_name": "Weapon Element Scroll",
        },
    }

    def __init__(self, bot):
        self.bot = bot
        ids_section = getattr(self.bot.config, "ids", None)
        gm_ids = getattr(ids_section, "game_master", {}) if ids_section else {}
        gods_ids = getattr(ids_section, "gods", {}) if ids_section else {}
        if not isinstance(gm_ids, dict):
            gm_ids = {}
        if not isinstance(gods_ids, dict):
            gods_ids = {}
        self.martigive_allowed_user_id = gm_ids.get("martigive_allowed_user_id")
        self.protected_user_id = gm_ids.get("protected_user_id")
        self.auction_channel_id = gm_ids.get("auction_channel_id")
        self.auction_ping_role_id = gm_ids.get("auction_ping_role_id")
        self.gm_role_id = gm_ids.get("gm_role_id")
        self.assign_roles_role_id = gm_ids.get("assign_roles_role_id")
        self.jail_guild_id = gm_ids.get("jail_guild_id")
        self.gmunjail_special_user_id = gm_ids.get("gmunjail_special_user_id")
        self.god_admin_role_id = gm_ids.get("god_admin_role_id")
        eval_allowed_user_ids = gm_ids.get("eval_allowed_user_ids", [])
        self.eval_allowed_user_ids = eval_allowed_user_ids if isinstance(eval_allowed_user_ids, list) else []
        support_roles = gods_ids.get("support_god_role_ids", {})
        self.support_god_role_ids = support_roles if isinstance(support_roles, dict) else {}
        self.godless_role_id = gods_ids.get("godless_role_id")
        self.top_auction = None
        self._last_result = None
        self.auction_entry = None
        self.isbid = False
        self.event_flags = {}

    @staticmethod
    def _normalize_consumable_alias(alias: str) -> str:
        if not alias:
            return ""
        return " ".join(alias.lower().replace("_", " ").replace("-", " ").split())

    @is_gm()
    @commands.command(brief=_("Publish an announcement"))
    @locale_doc
    async def publish(self, ctx, message: discord.Message):
        _("Publish a message from an announement channel")
        try:
            await message.publish()
            await ctx.send(_("Message has been published!"))
        except discord.Forbidden:
            await ctx.send(_("This message is not from an announcement channel!"))

    @is_gm()
    @commands.command(
        aliases=["cleanshop", "cshop"], hidden=True, brief=_("Clean up the shop")
    )
    @locale_doc
    async def clearshop(self, ctx):
        _(
            """Remove items from the shop that have been there for more than 14 days, returning them to the owners' inventories.

            Only Game Masters can use this command."""
        )
        async with self.bot.pool.acquire() as conn:
            timed_out = await conn.fetch(
                """DELETE FROM market WHERE "published" + '14 days'::interval < NOW() RETURNING *;""",
                timeout=600,
            )
            await conn.executemany(
            )
        await ctx.send(
            _("Cleared {num} shop items which timed out.").format(num=len(timed_out))
        )

    @is_gm()
    @commands.command(
        hidden=True, aliases=["gmcdc"], brief=_("Clear donator cache for a user")
    )
    @locale_doc
    async def gmcleardonatorcache(self, ctx, *, other: discord.Member):
        _(
            """`<other>` - A server member

            Clears the cached donator rank for a user globally, allowing them to use the new commands after donating.

            Only Game Masters can use this command."""
        )
        await self.bot.clear_donator_cache(other)
        await ctx.send(_("Done"))


    @is_gm()
    @commands.command(hidden=True, brief=_("Grant Favor"))
    @locale_doc
    async def gmfavor(self, ctx, other: int | discord.User, amount: int):

        id_ = other if isinstance(other, int) else other.id
        async with self.bot.pool.acquire() as conn:
            await conn.execute(
                'UPDATE profile SET "favor"="favor"+$1 WHERE "user"=$2;',
                amount,
                id_,
            )
        await ctx.send(f"You granted **{other} {amount}** favor.")
        with handle_message_parameters(
                content="**{gm}** granted **{other}** {amount} favor.".format(
                    gm=ctx.author,
                    amount=amount,
                    other=other,
                    reason=f"<{ctx.message.jump_url}>",
                )
        ) as params:
            await self.bot.http.send_message(
                self.bot.config.game.gm_log_channel,
                params=params,
            )

    import discord
    from discord.ext import commands


    @commands.command(name="processpet")
    @is_gm()  # Using existing decorator
    async def process_pet(self, ctx, user_id: int, *, names_input: str):
        """
        Process one or more pets for a user.
        Usage: $processpet [user_id] [name1, name2, name3, ...]
        """
        try:
            # Split names by comma and strip whitespace
            names = [name.strip() for name in names_input.split(',')]

            if not names:
                return await ctx.send("Please provide at least one pet name.")

            # Load monsters.json
            try:
                with open('monsters.json', 'r') as f:
                    monsters_data = json.load(f)
            except FileNotFoundError:
                return await ctx.send("Error: monsters.json not found.")
            except json.JSONDecodeError:
                return await ctx.send("Error: monsters.json is not valid JSON.")

            # Process each name
            results = []
            for name in names:
                result = await self.process_single_pet(ctx, user_id, name, monsters_data)
                results.append(result)

            # Combine and send results
            result_message = "\n\n".join(results)
            await ctx.send(result_message)
        except Exception as e:
            await ctx.send(e)

    async def process_single_pet(self, ctx, user_id: int, name: str, monsters_data: dict) -> str:
        """Process a single pet and return the result message."""
        # First, search in monsters.json
        found_monster = None

        # Search through all levels in monsters.json
        for level, monsters in monsters_data.items():
            for monster in monsters:
                if monster.get('name', '').lower() == name.lower():
                    found_monster = monster
                    break
            if found_monster:
                break

        # If not found in JSON, search in postgres database
        if not found_monster:
            try:
                async with self.bot.pool.acquire() as conn:
                    db_monster = await conn.fetchrow(
                        """
                        SELECT result_name as name, hp, attack, defense, element, url
                        FROM splice_combinations
                        WHERE LOWER(result_name) = LOWER($1)
                        """,
                        name
                    )

                    if db_monster:
                        found_monster = dict(db_monster)
            except Exception as e:
                return f"Error searching database for {name}: {str(e)}"

        # If monster not found in either source
        if not found_monster:
            return f"❌ Monster '{name}' not found in monsters.json or database."

        # Generate IVs
        iv_percentage, hp_iv, attack_iv, defense_iv = self.generate_ivs()

        # Calculate stats
        baby_hp = round(found_monster.get('hp', 0) * 0.25) + hp_iv
        baby_attack = round(found_monster.get('attack', 0) * 0.25) + attack_iv
        baby_defense = round(found_monster.get('defense', 0) * 0.25) + defense_iv
        element = found_monster.get('element', 'Normal')
        url = found_monster.get('url', '')

        # Growth stages - setting up for baby stage
        growth_stages = {
            1: {"stage": "baby", "growth_time": 2, "stat_multiplier": 0.25, "hunger_modifier": 1.0},
            2: {"stage": "juvenile", "growth_time": 2, "stat_multiplier": 0.50, "hunger_modifier": 0.8},
            3: {"stage": "young", "growth_time": 1, "stat_multiplier": 0.75, "hunger_modifier": 0.6},
            4: {"stage": "adult", "growth_time": None, "stat_multiplier": 1.0, "hunger_modifier": 0.0},
        }

        baby_stage = growth_stages[1]
        stat_multiplier = baby_stage["stat_multiplier"]
        growth_time_interval = datetime.timedelta(days=baby_stage["growth_time"])
        growth_time = datetime.datetime.utcnow() + growth_time_interval

        # Insert into database
        try:
            new_name = name  # Using the original name
            async with self.bot.pool.acquire() as conn:
                new_pet_id = await conn.fetchval(
                    """
                    INSERT INTO monster_pets 
                    (user_id, name, hp, attack, defense, element, default_name, url, growth_stage, growth_time, "IV") 
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11) 
                    RETURNING id
                    """,
                    user_id,
                    new_name,
                    baby_hp,
                    baby_attack,
                    baby_defense,
                    element,
                    new_name,
                    url,
                    'baby',
                    growth_time,
                    iv_percentage
                )

                # Create embed to show the pet
                embed = discord.Embed(
                    title=f"New Pet: {new_name}",
                    description=f"Added to <@{user_id}>'s collection!",
                    color=0x00ff00
                )

                embed.add_field(name="HP", value=f"{baby_hp} (+{hp_iv} IV)", inline=True)
                embed.add_field(name="Attack", value=f"{baby_attack} (+{attack_iv} IV)", inline=True)
                embed.add_field(name="Defense", value=f"{baby_defense} (+{defense_iv} IV)", inline=True)
                embed.add_field(name="Element", value=element, inline=True)
                embed.add_field(name="IV Rating", value=f"{iv_percentage:.2f}%", inline=True)
                embed.add_field(name="Growth Stage", value="Baby", inline=True)
                embed.set_thumbnail(url=url)

                await ctx.send(embed=embed)

                return f"✅ Created pet '{new_name}' (ID: {new_pet_id}) for <@{user_id}> with IV: {iv_percentage:.2f}%"
        except Exception as e:
            return f"❌ Error creating pet '{name}': {str(e)}"

    def generate_ivs(self):
        """Generate IV values for a pet."""
        import random
        iv_percentage = random.uniform(10, 1000)
        if iv_percentage < 20:
            iv_percentage = random.uniform(90, 100)
        elif iv_percentage < 70:
            iv_percentage = random.uniform(80, 90)
        elif iv_percentage < 150:
            iv_percentage = random.uniform(70, 80)
        elif iv_percentage < 350:
            iv_percentage = random.uniform(60, 70)
        elif iv_percentage < 700:
            iv_percentage = random.uniform(50, 60)
        else:
            iv_percentage = random.uniform(30, 50)

        # Calculate total IV points (50 points max as per your comment about halving)
        total_iv_points = (iv_percentage / 100) * 100

        # Allocate IV points
        def allocate_iv_points(total_points):
            a = random.random()
            b = random.random()
            c = random.random()
            total = a + b + c
            hp_iv = total_points * (a / total)
            attack_iv = total_points * (b / total)
            defense_iv = total_points * (c / total)
            hp_iv = int(round(hp_iv))
            attack_iv = int(round(attack_iv))
            defense_iv = int(round(defense_iv))
            iv_sum = hp_iv + attack_iv + defense_iv
            if iv_sum != int(round(total_points)):
                diff = int(round(total_points)) - iv_sum
                max_iv = max(hp_iv, attack_iv, defense_iv)
                if hp_iv == max_iv:
                    hp_iv += diff
                elif attack_iv == max_iv:
                    attack_iv += diff
                else:
                    defense_iv += diff
            return hp_iv, attack_iv, defense_iv

        hp_iv, attack_iv, defense_iv = allocate_iv_points(total_iv_points)

        return iv_percentage, hp_iv, attack_iv, defense_iv



    @is_gm()
    @commands.command(hidden=True, brief=_("Bot-ban a user"))
    @locale_doc
    async def gmban(self, ctx, other: int | discord.User, *, reason: str = ""):
        _(
            """`<other>` - A discord User

            Bans a user from the bot, prohibiting them from using commands and reactions.

            Only Game Masters can use this command."""
        )
        id_ = other if isinstance(other, int) else other.id



        try:
            await self.bot.pool.execute(
                'INSERT INTO bans ("user_id", "reason") VALUES ($1, $2);', id_, reason
            )
            self.bot.bans.add(id_)
            await self.bot.reload_bans()

            await ctx.send(_("Banned: {other}").format(other=other))

            with handle_message_parameters(
                    content="**{gm}** banned **{other}**.\n\nReason: *{reason}*".format(
                        gm=ctx.author,
                        other=other,
                        reason=reason or f"<{ctx.message.jump_url}>",
                    )
            ) as params:
                await self.bot.http.send_message(
                    self.bot.config.game.gm_log_channel,
                    params=params,
                )
        except UniqueViolationError:
            await ctx.send(_("{other} is already banned.").format(other=other))


    @is_gm()
    @commands.command(hidden=True, aliases=["sendcust"], brief=_("none"))
    @locale_doc
    async def testcust(self, ctx):
        await ctx.send("test")
        try:
            success = True
            self.bot.dispatch("adventure_completion", ctx, success)
        except Exception as e:
            await ctx.send(e)


    @is_gm()
    @commands.command(hidden=True, brief=_("Bot-unban a user"))
    async def reloadbans(self, ctx):
        await self.bot.reload_bans()
        await ctx.send("Bans Reloaded")

    @is_gm()
    @commands.command(hidden=True, brief=_("Bot-unban a user"))
    @locale_doc
    async def gmunban(self, ctx, other: int | discord.User, *, reason: str = ""):
        _(
            """`<other>` - A discord User

            Unbans a user from the bot, allowing them to use commands and reactions again.

            Only Game Masters can use this command."""
        )
        id_ = other if isinstance(other, int) else other.id
        await self.bot.pool.execute('DELETE FROM bans WHERE "user_id"=$1;', id_)

        try:
            self.bot.bans.remove(id_)
            await self.bot.reload_bans()

            await ctx.send(_("Unbanned: {other}").format(other=other))

            with handle_message_parameters(
                    content="**{gm}** unbanned **{other}**.\n\nReason: *{reason}*".format(
                        gm=ctx.author,
                        other=other,
                        reason=reason or f"<{ctx.message.jump_url}>",
                    )
            ) as params:
                await self.bot.http.send_message(
                    self.bot.config.game.gm_log_channel,
                    params=params,
                )
        except KeyError:
            await ctx.send(_("{other} is not banned.").format(other=other))





    @is_gm()
    @has_char()
    @commands.command(hidden=True)
    async def gmtokens(self, ctx, member: UserWithCharacter, tokens: int, reason: str = None):
        # Fetch the current token value of the specified user from the database
        weapontoken_value = await self.bot.pool.fetchval(
            'SELECT weapontoken FROM profile WHERE "user"=$1;',
            member.id  # Use the specified member's Discord ID
        )

        # If the user doesn't have a token value yet, set it to 0
        if weapontoken_value is None:
            weapontoken_value = 0

        # Add the new tokens to the current value
        new_value = weapontoken_value + tokens

        # Update the database with the new token value
        await self.bot.pool.execute(
            'UPDATE profile SET weapontoken=$1 WHERE "user"=$2;',
            new_value, member.id
        )

        # Send a confirmation message to the context
        await ctx.send(f"{member.display_name} now has {new_value} weapon tokens!")

        with handle_message_parameters(
                content="**{gm}** gave **{tokens}** to **{member}**.\n\nReason: *{reason}*".format(
                    gm=ctx.author,
                    tokens=tokens,
                    member=member,
                    reason=reason or f"<{ctx.message.jump_url}>",
                )
        ) as params:
            await self.bot.http.send_message(
                self.bot.config.game.gm_log_channel,
                params=params,
            )

    @is_gm()
    @commands.command(hidden=True, brief=_("Create money"))
    @locale_doc
    async def gmgive(
            self,
            ctx,
            money: int,
            other: UserWithCharacter,
            *,
            reason: str = None,
    ):
        _(
            """`<money>` - the amount of money to generate for the user
            `<other>` - A discord User with a character
            `[reason]` - The reason this action was done, defaults to the command message link

            Gives a user money without subtracting it from the command author's balance.

            Only Game Masters can use this command."""
        )

        try:

            permissions = ctx.channel.permissions_for(ctx.guild.me)

            if permissions.read_messages and permissions.send_messages:
                await self.bot.pool.execute(
                    'UPDATE profile SET "money"="money"+$1 WHERE "user"=$2;', money, other.id
                )
                await ctx.send(
                    _(
                        "Successfully gave **${money}** without a loss for you to **{other}**."
                    ).format(money=money, other=other)
                )

                with handle_message_parameters(
                        content="**{gm}** gave **${money}** to **{other}**.\n\nReason: *{reason}*".format(
                            gm=ctx.author,
                            money=money,
                            other=other,
                            reason=reason or f"<{ctx.message.jump_url}>",
                        )
                ) as params:
                    await self.bot.http.send_message(
                        self.bot.config.game.gm_log_channel,
                        params=params,
                    )

        except Exception as e:
            await ctx.send(e)

    @is_gm()
    @commands.command(hidden=True, brief=_("Create money for multiple users"))
    @locale_doc
    async def martigive(
            self,
            ctx,
            money: int,
            others: commands.Greedy[UserWithCharacter],
            *,
            reason: str = None,
    ):
        _(
            """`<money>` - the amount of money to generate for the users
            `<others>` - One or more Discord Users with characters
            `[reason]` - The reason this action was done, defaults to the command message link

            Gives the specified amount of money to multiple users without subtracting it from the command author's balance.

            Only Game Masters can use this command."""
        )

        if not self.martigive_allowed_user_id or ctx.author.id != self.martigive_allowed_user_id:
            return

        try:
            permissions = ctx.channel.permissions_for(ctx.guild.me)

            if permissions.read_messages and permissions.send_messages:
                updated_users = []
                for other in others:
                    await self.bot.pool.execute(
                        'UPDATE profile SET "money"="money"+$1 WHERE "user"=$2;', money, other.id
                    )
                    updated_users.append(str(other))

                # Send a single summary message
                await ctx.send(
                    _(
                        "Successfully gave **${money}** to the following users without a loss for you: {users}."
                    ).format(money=money, users=", ".join(updated_users))
                )

                # Log the action
                with handle_message_parameters(
                        content="**{gm}** gave **${money}** to **{users}**.\n\nReason: *{reason}*".format(
                            gm=ctx.author,
                            money=money,
                            users=", ".join(updated_users),
                            reason=reason or f"<{ctx.message.jump_url}>",
                        )
                ) as params:
                    await self.bot.http.send_message(
                        self.bot.config.game.gm_log_channel,
                        params=params,
                    )

        except Exception as e:
            await ctx.send(e)

    @commands.is_owner()
    @commands.command(hidden=True, brief=_("Emergancy Shutdown"))
    async def shutdown(self, ctx):
        """Shuts down the bot"""
        # Check if the user invoking the command is the bot owner
        await self.bot.close()  # Gracefully close the bot


    @commands.command(name="generate_key")
    @commands.is_owner()
    async def generate_key(self, ctx, owner: str, is_admin: bool = False, expiration: str = "none",
                           rate_limit: int = 100, custom_key: str = None):
        """Generate a new API key (Owner only)"""
        try:
            # Calculate expiration date if needed
            expiration_date = None
            if expiration == "30days":
                expiration_date = datetime.datetime.now() + datetime.timedelta(days=30)
            elif expiration == "90days":
                expiration_date = datetime.datetime.now() + datetime.timedelta(days=90)
            elif expiration == "1year":
                expiration_date = datetime.datetime.now() + datetime.timedelta(days=365)

            # Use custom key or generate a new one
            new_key = custom_key if custom_key else secrets.token_hex(32)

            async with self.bot.pool.acquire() as connection:
                await connection.execute(
                    """
                    INSERT INTO api_keys (key, owner, is_admin, rate_limit, expiration_date) 
                    VALUES ($1, $2, $3, $4, $5)
                    """,
                    new_key, owner, is_admin, rate_limit, expiration_date
                )

            embed = discord.Embed(
                title="API Key Generated",
                description=f"Successfully generated API key for **{owner}**",
                color=0x00ff00
            )
            embed.add_field(name="Key", value=f"`{new_key}`", inline=False)
            embed.add_field(name="Admin", value=str(is_admin), inline=True)
            embed.add_field(name="Rate Limit", value=str(rate_limit), inline=True)
            embed.add_field(name="Expiration",
                            value=expiration_date.strftime("%Y-%m-%d %H:%M:%S") if expiration_date else "Never",
                            inline=True)

            await ctx.send(embed=embed)

        except Exception as e:
            embed = discord.Embed(
                title="Error",
                description=f"Failed to generate API key: {str(e)}",
                color=0xff0000
            )
            await ctx.send(embed=embed)


    @is_gm()
    @commands.hybrid_command()
    async def resetdragon(self, ctx, channel_id: int = None):
        """
        Reset the dragon progress and weekly contributions.
        Usage: $resetdragon [channel_id]
        """
        try:
            async with self.bot.pool.acquire() as conn:
                # Delete all rows from dragon_progress
                await conn.execute('DELETE FROM dragon_progress')

                # Insert fresh dragon_progress row
                await conn.execute('''
                    INSERT INTO dragon_progress (id, current_level, weekly_defeats, last_reset) 
                    VALUES (1, 1, 0, $1)
                ''', datetime.datetime.utcnow())

                # Reset weekly_defeats in dragon_contributions
                await conn.execute('''
                    UPDATE dragon_contributions 
                    SET weekly_defeats = 0
                ''')

                # Send confirmation to command user
                await ctx.send("✅ Dragon has been reset successfully!")

                # If channel_id is provided, send announcement
                if channel_id:
                    try:
                        channel = self.bot.get_channel(channel_id)
                        if channel:
                            embed = discord.Embed(
                                title="🐉 Dragon Reset",
                                description="The Ice Dragon has been reset to level 1!\nAll weekly progress has been cleared.",
                                color=0x87CEEB
                            )
                            embed.add_field(
                                name="New Challenge Awaits!",
                                value="The Frostbite Wyrm awaits new challengers... Will you face the dragon?",
                                inline=False
                            )
                            await channel.send(embed=embed)
                        else:
                            await ctx.send("⚠️ Warning: Could not find the specified channel.")
                    except Exception as e:
                        await ctx.send(f"⚠️ Error sending announcement: {str(e)}")

        except Exception as e:
            await ctx.send(f"❌ Error resetting dragon: {str(e)}")


    @is_gm()
    @commands.command(hidden=True, brief=_("Create money"))
    @locale_doc
    async def gmgiveeggs(
            self,
            ctx,
            eggs: int,
            other: UserWithCharacter,
            *,
            reason: str = None,
    ):
        _(
            """`<money>` - the amount of money to generate for the user
            `<other>` - A discord User with a character
            `[reason]` - The reason this action was done, defaults to the command message link

            Gives a user money without subtracting it from the command author's balance.

            Only Game Masters can use this command."""
        )

        permissions = ctx.channel.permissions_for(ctx.guild.me)

        if permissions.read_messages and permissions.send_messages:
            await self.bot.pool.execute(
                'UPDATE profile SET "eastereggs"="eastereggs"+$1 WHERE "user"=$2;', eggs, other.id
            )
            await ctx.send(
                _(
                    "Successfully gave **{money} eggs** without a loss for you to **{other}**."
                ).format(money=eggs, other=other)
            )

            with handle_message_parameters(
                    content="**{gm}** gave **{money}** to **{other}**.\n\nReason: *{reason}*".format(
                        gm=ctx.author,
                        money=eggs,
                        other=other,
                        reason=reason or f"<{ctx.message.jump_url}>",
                    )
            ) as params:
                await self.bot.http.send_message(
                    self.bot.config.game.gm_log_channel,
                    params=params,
                )

    @is_gm()
    @commands.command(hidden=True, brief=_("Remove money"))
    @locale_doc
    async def gmremove(
            self,
            ctx,
            money: int,
            other: UserWithCharacter,
            *,
            reason: str = None,
    ):
        _(
            """`<money>` - the amount of money to remove from the user
            `<other>` - a discord User with character
            `[reason]` - The reason this action was done, defaults to the command message link

            Removes money from a user without adding it to the command author's balance.

            Only Game Masters can use this command."""
        )
        await self.bot.pool.execute(
            'UPDATE profile SET "money"="money"-$1 WHERE "user"=$2;', money, other.id
        )
        await ctx.send(
            _("Successfully removed **${money}** from **{other}**.").format(
                money=money, other=other
            )
        )

        with handle_message_parameters(
                content="**{gm}** removed **${money}** from **{other}**.\n\nReason: *{reason}*".format(
                    gm=ctx.author,
                    money=money,
                    other=other,
                    reason=reason or f"<{ctx.message.jump_url}>",
                )
        ) as params:
            await self.bot.http.send_message(
                self.bot.config.game.gm_log_channel,
                params=params,
            )

    @is_gm()
    @commands.command(hidden=True, brief=_("Delete a character"))
    @locale_doc
    async def gmdelete(self, ctx, other: UserWithCharacter, *, reason: str = None):
        _(
            """`<other>` - a discord User with character
            `[reason]` - The reason this action was done, defaults to the command message link

            Delete a user's profile. The user cannot be a Game Master.

            Only Game Masters can use this command."""
        )


        if other.id in ctx.bot.config.game.game_masters:  # preserve deletion of admins
            return await ctx.send(_("Very funny..."))
        async with self.bot.pool.acquire() as conn:
            g = await conn.fetchval(
                'DELETE FROM guild WHERE "leader"=$1 RETURNING id;', other.id
            )
            if g:
                await conn.execute(
                    'UPDATE profile SET "guildrank"=$1, "guild"=$2 WHERE "guild"=$3;',
                    "Member",
                    0,
                    g,
                )
                await conn.execute('UPDATE city SET "owner"=1 WHERE "owner"=$1;', g)
            partner = await conn.fetchval(
                'UPDATE profile SET "marriage"=$1 WHERE "marriage"=$2 RETURNING'
                ' "user";',
                0,
                other.id,
            )
            await conn.execute(
                'UPDATE children SET "mother"=$1, "father"=0 WHERE ("father"=$1 AND'
                ' "mother"=$2) OR ("father"=$2 AND "mother"=$1);',
                partner,
                other.id,
            )
            await self.bot.delete_profile(other.id, conn=conn)
        await ctx.send(_("Successfully deleted the character."))

        with handle_message_parameters(
                content="**{gm}** deleted **{other}**.\n\nReason: *{reason}*".format(
                    gm=ctx.author, other=other, reason=reason or f"<{ctx.message.jump_url}>"
                )
        ) as params:
            await self.bot.http.send_message(
                self.bot.config.game.gm_log_channel,
                params=params,
            )

    @is_gm()
    @commands.command(hidden=True, brief=_("Rename a character"))
    @locale_doc
    async def gmrename(self, ctx, target: UserWithCharacter, *, reason: str = None):
        _(
            """`<target>` - a discord User with character
            `[reason]` - The reason this action was done, defaults to the command message link

            Rename a user's profile. The user cannot be a Game Master.

            Only Game Masters can use this command."""
        )
        if target.id in ctx.bot.config.game.game_masters:  # preserve renaming of admins
            return await ctx.send(_("Very funny..."))

        await ctx.send(
            _("What shall the character's name be? (min. 3 letters, max. 20)")
        )

        def mycheck(amsg):
            return (
                    amsg.author == ctx.author
                    and amsg.channel == ctx.channel
                    and len(amsg.content) < 21
                    and len(amsg.content) > 2
            )

        try:
            name = await self.bot.wait_for("message", timeout=60, check=mycheck)
        except asyncio.TimeoutError:
            return await ctx.send(_("Timeout expired."))

        await self.bot.pool.execute(
            'UPDATE profile SET "name"=$1 WHERE "user"=$2;', name.content, target.id
        )
        await ctx.send(_("Renamed."))

        with handle_message_parameters(
                content="**{gm}** renamed **{target}** to **{name}**.\n\nReason: *{reason}*".format(
                    gm=ctx.author,
                    target=target,
                    name=name.content,
                    reason=reason or f"<{ctx.message.jump_url}>",
                )
        ) as params:
            await self.bot.http.send_message(
                self.bot.config.game.gm_log_channel,
                params=params,
            )

    @is_gm()
    @commands.command(hidden=True, brief=_("Create an item"))
    @locale_doc
    async def gmitem(
            self,
            ctx,
            stat: int,
            owner: UserWithCharacter,
            item_type: str.title,
            element: str,
            value: IntFromTo(0, 100000000),
            name: str,
            *,
            reason: str = None,
    ):
        _(
            """`<stat>` - the generated item's stat, must be between 0 and 100
            `<owner>` - a discord User with character
            `<item_type>` - the generated item's type, must be either Sword, Shield, Axe, Wand, Dagger, Knife, Spear, Bow, Hammer, Scythe or Mace
            `<element> - the element type
            `<value>` - the generated item's value, a whole number from 0 to 100,000,000
            `<name>` - the generated item's name, should be in double quotes if the name has multiple words
            `[reason]` - The reason this action was done, defaults to the command message link

            Generate a custom item for a user.

            Only Game Masters can use this command."""
        )
        item_type = ItemType.from_string(item_type)
        if item_type is None:
            return await ctx.send(_("Invalid item type."))
        if not -100 <= stat <= 201:
            return await ctx.send(_("Invalid stat."))
        try:
            hand = item_type.get_hand().value
            await self.bot.create_item(
                name=name,
                value=value,
                type_=item_type.value,
                damage=stat if item_type != ItemType.Shield else 0,
                armor=stat if item_type == ItemType.Shield else 0,
                hand=hand,
                owner=owner,
                element=element,
            )
        except Exception as e:
            await ctx.send(f"Error has occured {e}")

        message = "{gm} created a {item_type} with name {name} and stat {stat}.\n\nReason: *{reason}*".format(
            gm=ctx.author,
            item_type=item_type.value,
            name=name,
            stat=stat,
            reason=reason or f"<{ctx.message.jump_url}>",
        )

        await ctx.send(_("Done."))

        with handle_message_parameters(content=message) as params:
            await self.bot.http.send_message(
                self.bot.config.game.gm_log_channel, params=params
            )

        for user in self.bot.owner_ids:
            user = await self.bot.get_user_global(user)
            await user.send(message)

    @is_gm()
    @commands.command(
        hidden=True,
        aliases=["gmconsumable", "gmgivecons"],
        brief=_("Grant premium consumables"),
    )
    @locale_doc
    async def gmgiveconsumable(
            self,
            ctx,
            target: UserWithCharacter,
            item: str,
            amount: int = 1,
            *,
            reason: str = None,
    ):
        _(
            """`<target>` - A discord User with character
            `<item>` - One of: petage, petspeed, petxp, weapelement (or long aliases)
            `[amount]` - Optional amount to grant, defaults to 1
            `[reason]` - The reason this action was done, defaults to the command message link

            Grant premium consumables directly to a user's consumable inventory.
            For multi-word item names, use quotes.

            Only Game Masters can use this command."""
        )
        normalized_item = self._normalize_consumable_alias(item)
        item_data = self.GM_CONSUMABLE_ALIASES.get(normalized_item)
        if not item_data:
            valid_items = (
                "petage, pet age potion, pet_age_potion, petspeed, "
                "pet speed growth potion, pet_speed_growth_potion, "
                "petxp, pet xp potion, pet_xp_potion, "
                "weapelement, elementscroll, weapon element scroll, weapon_element_scroll"
            )
            return await ctx.send(
                _("Invalid consumable. Valid options: {items}").format(items=valid_items)
            )

        consumable_type = item_data["consumable_type"]
        display_name = item_data["display_name"]

        async with self.bot.pool.acquire() as conn:
            existing = await conn.fetchrow(
                'SELECT id, quantity FROM user_consumables WHERE user_id = $1 AND consumable_type = $2;',
                target.id,
                consumable_type,
            )
            if existing:
                await conn.execute(
                    'UPDATE user_consumables SET quantity = quantity + $1 WHERE id = $2;',
                    amount,
                    existing["id"],
                )
            else:
                await conn.execute(
                    'INSERT INTO user_consumables (user_id, consumable_type, quantity) VALUES ($1, $2, $3);',
                    target.id,
                    consumable_type,
                    amount,
                )

            new_quantity = await conn.fetchval(
                'SELECT quantity FROM user_consumables WHERE user_id = $1 AND consumable_type = $2;',
                target.id,
                consumable_type,
            )

        await ctx.send(
            _(
                "Granted **{amount}x {item_name}** to **{target}**. New quantity: **{quantity}**."
            ).format(amount=amount, item_name=display_name, target=target, quantity=new_quantity)
        )

        with handle_message_parameters(
                content="**{gm}** gave **{amount}x {item_name}** to **{target}**.\n\nReason: *{reason}*".format(
                    gm=ctx.author,
                    amount=amount,
                    item_name=display_name,
                    target=target,
                    reason=reason or f"<{ctx.message.jump_url}>",
                )
        ) as params:
            await self.bot.http.send_message(
                self.bot.config.game.gm_log_channel,
                params=params,
            )

    @is_gm()
    @commands.command(hidden=True, brief=_("Create crates"))
    @locale_doc
    async def gmcrate(
            self,
            ctx,
            rarity: CrateRarity,
            amount: int,
            target: UserWithCharacter,
            *,
            reason: str = None,
    ):
        _(
            """`<rarity>` - the crates' rarity, can be common, uncommon, rare, magic or legendary
            `<amount>` - the amount of crates to generate for the given user, can be negative
            `<target>` - A discord User with character
            `[reason]` - The reason this action was done, defaults to the command message link

            Generate a set amount of crates of one rarity for a user.

            Only Game Masters can use this command."""
        )
        await self.bot.pool.execute(
            f'UPDATE profile SET "crates_{rarity}"="crates_{rarity}"+$1 WHERE'
            ' "user"=$2;',
            amount,
            target.id,
        )
        await ctx.send(
            _("Successfully gave **{amount}** {rarity} crates to **{target}**.").format(
                amount=amount, target=target, rarity=rarity
            )
        )

        with handle_message_parameters(
                content="**{gm}** gave **{amount}** {rarity} crates to **{target}**.\n\nReason: *{reason}*".format(
                    gm=ctx.author,
                    amount=amount,
                    rarity=rarity,
                    target=target,
                    reason=reason or f"<{ctx.message.jump_url}>",
                )
        ) as params:
            await self.bot.http.send_message(
                self.bot.config.game.gm_log_channel,
                params=params,
            )

    @is_gm()
    @commands.command(hidden=True, brief=_("Give crafting resources to a player"))
    @locale_doc
    async def gmresource(
            self,
            ctx,
            target: UserWithCharacter,
            amount: int,
            resource_type: str = None,
            *,
            reason: str = None,
    ):
        _("""Give crafting resources to a player.
        
        If no resource type is specified, a random resource will be given.
        
        **Parameters:**
        - target: The player to give resources to
        - amount: Amount of resources to give
        - resource_type: Type of resource (optional, random if not specified)
        - reason: Reason for giving resources (optional)
        
        **Examples:**
        - `gmresource @player 10 dragon_scales` - Give 10 dragon scales
        - `gmresource @player 5` - Give 5 random resources
        - `gmresource @player 3 fire_gems Testing reward` - Give 3 fire gems with reason
        """)
        
        # Get the amuletcrafting cog
        amulet_cog = self.bot.get_cog('AmuletCrafting')
        if not amulet_cog:
            await ctx.send(_("❌ AmuletCrafting cog not found!"))
            return
            
        # If no resource type specified, get a random one
        if not resource_type:
            # Get player level for level-appropriate random resource
            user_level = await amulet_cog.get_player_level(target.id)
            resource_type = amulet_cog.get_random_resource(user_level=user_level)
            
            if not resource_type:
                await ctx.send(_("❌ Failed to generate random resource!"))
                return
                
            resource_display_name = resource_type.replace('_', ' ').title()
            await ctx.send(_("🎲 No resource specified, giving random resource: **{resource}**").format(resource=resource_display_name))
        else:
            # Normalize the resource name
            resource_type = amulet_cog.normalize_resource_name(resource_type)
            if not resource_type:
                await ctx.send(_("❌ Invalid resource type! Use `amulet resources` to see available resources."))
                return
            resource_display_name = resource_type.replace('_', ' ').title()
        
        # Give the resource
        success = await amulet_cog.give_crafting_resource(target.id, resource_type, amount)
        
        if success:
            await ctx.send(_("✅ Successfully gave **{amount}x {resource}** to {target}!").format(
                amount=amount, resource=resource_display_name, target=target.mention
            ))

            # Log the action using the proper GM logging system
            with handle_message_parameters(
                    content="**{gm}** gave **{amount}x {resource}** to **{target}**.\n\nReason: *{reason}*".format(
                        gm=ctx.author,
                        amount=amount,
                        resource=resource_display_name,
                        target=target,
                        reason=reason or f"<{ctx.message.jump_url}>",
                    )
            ) as params:
                await self.bot.http.send_message(
                    self.bot.config.game.gm_log_channel,
                    params=params,
                )
        else:
            await ctx.send(_("❌ Failed to give resource to {target}!").format(target=target.mention))

    @is_gm()
    @commands.command(hidden=True, brief=_("Give crafting resources to multiple players"))
    @locale_doc
    async def gmresourcebatch(
            self,
            ctx,
            amount: int,
            resource_type: str = None,
            *,
            id_text: str,
    ):
        _("""Give crafting resources to multiple players.
        
        If no resource type is specified, a random resource will be given to each player.
        
        **Parameters:**
        - amount: Amount of resources to give to each player
        - resource_type: Type of resource (optional, random if not specified)
        - id_text: Comma-separated list of user IDs or mentions
        
        **Examples:**
        - `gmresourcebatch 10 dragon_scales 123456789,987654321` - Give 10 dragon scales to two players
        - `gmresourcebatch 5 123456789,987654321` - Give 5 random resources to two players
        """)
        
        # Get the amuletcrafting cog
        amulet_cog = self.bot.get_cog('AmuletCrafting')
        if not amulet_cog:
            await ctx.send(_("❌ AmuletCrafting cog not found!"))
            return
        
        # Parse user IDs from the text
        user_ids = []
        for item in id_text.split(','):
            item = item.strip()
            try:
                # Try to parse as user ID
                user_id = int(item)
                user_ids.append(user_id)
            except ValueError:
                # Try to parse as mention
                if item.startswith('<@') and item.endswith('>'):
                    user_id = int(item[2:-1].replace('!', ''))
                    user_ids.append(user_id)
                else:
                    await ctx.send(_("❌ Invalid user ID or mention: {item}").format(item=item))
                    return
        
        if not user_ids:
            await ctx.send(_("❌ No valid user IDs provided!"))
            return
        
        # Get user objects
        users = []
        for user_id in user_ids:
            try:
                user = await self.bot.fetch_user(user_id)
                users.append(user)
            except discord.NotFound:
                await ctx.send(_("❌ User not found: {user_id}").format(user_id=user_id))
                return
        
        success_count = 0
        failed_users = []
        
        for user in users:
            # If no resource type specified, get a random one for each user
            current_resource_type = resource_type
            if not current_resource_type:
                # Get player level for level-appropriate random resource
                user_level = await amulet_cog.get_player_level(user.id)
                current_resource_type = amulet_cog.get_random_resource(user_level=user_level)
                
                if not current_resource_type:
                    failed_users.append(f"{user} (Failed to generate random resource)")
                    continue
            else:
                # Normalize the resource name
                current_resource_type = amulet_cog.normalize_resource_name(current_resource_type)
                if not current_resource_type:
                    failed_users.append(f"{user} (Invalid resource type)")
                    continue
            
            # Give the resource
            success = await amulet_cog.give_crafting_resource(user.id, current_resource_type, amount)
            
            if success:
                success_count += 1
                resource_display_name = current_resource_type.replace('_', ' ').title()
            else:
                failed_users.append(f"{user} (Database error)")
        
        # Send summary
        if success_count > 0:
            resource_display = resource_type.replace('_', ' ').title() if resource_type else "Random Resources"
            await ctx.send(_("✅ Successfully gave **{amount}x {resource}** to **{count}** players!").format(
                amount=amount, resource=resource_display, count=success_count
            ))

            # Log the batch action using the proper GM logging system
            user_list = ", ".join([str(user) for user in users[:success_count]])
            with handle_message_parameters(
                    content="**{gm}** gave **{amount}x {resource}** to **{users}**.\n\nReason: *{reason}*".format(
                        gm=ctx.author,
                        amount=amount,
                        resource=resource_display,
                        users=user_list,
                        reason=f"<{ctx.message.jump_url}>",
                    )
            ) as params:
                await self.bot.http.send_message(
                    self.bot.config.game.gm_log_channel,
                    params=params,
                )
        
        if failed_users:
            failed_list = "\n".join(failed_users)
            await ctx.send(_("❌ Failed to give resources to:\n{failed_list}").format(failed_list=failed_list))

    @is_gm()
    @commands.command(hidden=True, brief=_("Create crates for multiple users"))
    @locale_doc
    async def gmcratebatch(
            self,
            ctx,
            rarity: CrateRarity,
            amount: int,
            *,
            id_text: str,
    ):
        _(
            """`<rarity>` - the crates' rarity, can be common, uncommon, rare, magic or legendary
            `<amount>` - the amount of crates to generate for each user, can be negative
            `<id_text>` - Comma or space separated list of Discord user IDs

            Generate a set amount of crates of one rarity for multiple users at once.

            Only Game Masters can use this command."""
        )
        # Parse the user IDs from the input text
        user_ids = []
        for id_part in id_text.replace(',', ' ').split():
            id_part = id_part.strip()
            if id_part.isdigit():
                user_ids.append(int(id_part))

        if not user_ids:
            await ctx.send(_("No valid user IDs provided."))
            return

        success_count = 0
        failed_ids = []

        # Process each user ID
        for user_id in user_ids:
            try:
                # Check if the user has a character in the game
                has_character = await self.bot.pool.fetchval(
                    'SELECT EXISTS(SELECT 1 FROM profile WHERE "user"=$1);',
                    user_id
                )

                if not has_character:
                    failed_ids.append(str(user_id))
                    continue

                # Update the user's crates
                await self.bot.pool.execute(
                    f'UPDATE profile SET "crates_{rarity}"="crates_{rarity}"+$1 WHERE "user"=$2;',
                    amount,
                    user_id
                )
                success_count += 1
            except Exception as e:
                failed_ids.append(str(user_id))
                print(f"Error giving crates to user ID {user_id}: {e}")

        # Send a summary message
        if success_count > 0:
            await ctx.send(
                _("Successfully gave **{amount}** {rarity} crates to **{count}** users.").format(
                    amount=amount, count=success_count, rarity=rarity
                )
            )

        if failed_ids:
            failed_msg = _("Failed to add crates to {count} users").format(count=len(failed_ids))
            if len(failed_ids) <= 10:
                failed_msg += _(": {ids}").format(ids=', '.join(failed_ids))
            else:
                failed_msg += _(": {ids}...").format(ids=', '.join(failed_ids[:10]))
            await ctx.send(failed_msg)

        # Log the action to the GM log channel
        with handle_message_parameters(
                content="**{gm}** gave **{amount}** {rarity} crates to **{count}** users in batch mode.\n\nReason: Batch distribution".format(
                    gm=ctx.author,
                    amount=amount,
                    rarity=rarity,
                    count=success_count,
                )
        ) as params:
            await self.bot.http.send_message(
                self.bot.config.game.gm_log_channel,
                params=params,
            )

    @is_gm()
    @commands.command(hidden=True, brief=_("Generate XP"))
    @locale_doc
    async def gmxp(
            self,
            ctx,
            target: UserWithCharacter,
            amount: int,
            *,
            reason: str = None,
    ):
        _(
            """`<target>` - A discord User with character
            `<amount>` - The amount of XP to generate, can be negative
            `[reason]` - The reason this action was done, defaults to the command message link

            Generates a set amount of XP for a user.

            Only Game Masters can use this command."""
        )
        await self.bot.pool.execute(
            'UPDATE profile SET "xp"="xp"+$1 WHERE "user"=$2;', amount, target.id
        )
        await ctx.send(
            _("Successfully gave **{amount}** XP to **{target}**.").format(
                amount=amount, target=target
            )
        )

        with handle_message_parameters(
                content="**{gm}** gave **{amount}** XP to **{target}**.\n\nReason: *{reason}*".format(
                    gm=ctx.author,
                    amount=amount,
                    target=target,
                    reason=reason or f"<{ctx.message.jump_url}>",
                )
        ) as params:
            await self.bot.http.send_message(
                self.bot.config.game.gm_log_channel,
                params=params,
            )

    import random
    @is_gm()
    @commands.command()
    async def gmiv(self, ctx, monster_id: int):
        """Generate IVs for an existing monster using its ID."""
        # Fetch the monster from the database
        try:
            await ctx.send("hi")
            async with self.bot.pool.acquire() as conn:
                monster = await conn.fetchrow(
                    """
                    SELECT * FROM monster_pets WHERE "id" = $1;
                    """,
                    monster_id
                )


            if not monster:
                await ctx.send(f"No monster found with ID {monster_id}.")
                return
            import random

            iv_percentage = random.uniform(10, 1000)

            if iv_percentage < 20:
                iv_percentage = random.uniform(90, 100)
            elif iv_percentage < 70:
                iv_percentage = random.uniform(80, 90)
            elif iv_percentage < 150:
                iv_percentage = random.uniform(70, 80)
            elif iv_percentage < 350:
                iv_percentage = random.uniform(60, 70)
            elif iv_percentage < 700:
                iv_percentage = random.uniform(50, 60)
            else:
                iv_percentage = random.uniform(30, 50)

            # Calculate total IV points (100% IV corresponds to 200 points)
            total_iv_points = (iv_percentage / 100) * 200

            def allocate_iv_points(total_points):
                # Generate three random numbers
                import random
                a = random.random()
                b = random.random()
                c = random.random()
                total = a + b + c
                # Normalize so that the sum is equal to total_points
                hp_iv = total_points * (a / total)
                attack_iv = total_points * (b / total)
                defense_iv = total_points * (c / total)
                # Round the IV points
                hp_iv = int(round(hp_iv))
                attack_iv = int(round(attack_iv))
                defense_iv = int(round(defense_iv))
                # Adjust if rounding errors cause total to deviate
                iv_sum = hp_iv + attack_iv + defense_iv
                if iv_sum != int(round(total_points)):
                    diff = int(round(total_points)) - iv_sum
                    # Adjust the largest IV by the difference
                    max_iv = max(hp_iv, attack_iv, defense_iv)
                    if hp_iv == max_iv:
                        hp_iv += diff
                    elif attack_iv == max_iv:
                        attack_iv += diff
                    else:
                        defense_iv += diff
                return hp_iv, attack_iv, defense_iv

            hp_iv, attack_iv, defense_iv = allocate_iv_points(total_iv_points)
        except Exception as e:
            await ctx.send(e)

        # Calculate the final stats
        base_hp = monster['hp']
        base_attack = monster['attack']
        base_defense = monster['defense']

        hp_total = base_hp + hp_iv
        attack_total = base_attack + attack_iv
        defense_total = base_defense + defense_iv



        # Update the monster's IVs and total stats in the database
        try:
            async with self.bot.pool.acquire() as conn:
                await conn.execute(
                    'UPDATE monster_pets SET "IV" = $1, hp = $2, attack = $3, defense = $4 WHERE "id" = $5;',
                    iv_percentage,
                    hp_total,
                    attack_total,
                    defense_total,
                    monster_id
                )


            await ctx.send(
                f"Monster with ID {monster_id} has been assigned an IV of {iv_percentage:.2f}% "
                f"(HP IV: {hp_iv}, Attack IV: {attack_iv}, Defense IV: {defense_iv}). "
                f"Total stats updated."
            )
        except Exception as e:
            await ctx.send(f"An error occurred: {e}")

    @is_gm()
    @commands.command()
    async def gmegg(self, ctx, member: discord.Member, *, monster_name: str):
        """Generate an egg for a user with a specified monster."""
        # Load monsters data from JSON file
        try:
            with open("monsters.json", "r") as f:
                monsters_data = json.load(f)
        except Exception as e:
            await ctx.send("Error loading monsters data. Please contact the admin.")
            return

        # Search for the monster by name (ignoring case)
        monster = None
        for level_str, monster_list in monsters_data.items():
            for m in monster_list:
                if m["name"].lower() == monster_name.lower():
                    monster = m
                    break
            if monster:
                break

        if not monster:
            await ctx.send(f"Monster '{monster_name}' not found.")
            return

        # Check the user's current pet and egg count
        async with self.bot.pool.acquire() as conn:
            pet_and_egg_count = await conn.fetchval(
                """
                SELECT COUNT(*) 
                FROM (
                    SELECT id FROM monster_pets WHERE user_id = $1
                    UNION ALL
                    SELECT id FROM monster_eggs WHERE user_id = $1 AND hatched = FALSE
                ) AS combined
                """,
                member.id
            )


        import random

        # Generate a random IV percentage with weighted probabilities
        iv_percentage = random.uniform(10, 1000)

        if iv_percentage < 20:
            iv_percentage = random.uniform(90, 100)
        elif iv_percentage < 70:
            iv_percentage = random.uniform(80, 90)
        elif iv_percentage < 150:
            iv_percentage = random.uniform(70, 80)
        elif iv_percentage < 350:
            iv_percentage = random.uniform(60, 70)
        elif iv_percentage < 700:
            iv_percentage = random.uniform(50, 60)
        else:
            iv_percentage = random.uniform(30, 50)

        # Calculate total IV points (100% IV corresponds to 200 points)
        total_iv_points = (iv_percentage / 100) * 200

        def allocate_iv_points(total_points):
            # Generate three random numbers
            a = random.random()
            b = random.random()
            c = random.random()
            total = a + b + c
            # Normalize so that the sum is equal to total_points
            hp_iv = total_points * (a / total)
            attack_iv = total_points * (b / total)
            defense_iv = total_points * (c / total)
            # Round the IV points
            hp_iv = int(round(hp_iv))
            attack_iv = int(round(attack_iv))
            defense_iv = int(round(defense_iv))
            # Adjust if rounding errors cause total to deviate
            iv_sum = hp_iv + attack_iv + defense_iv
            if iv_sum != int(round(total_points)):
                diff = int(round(total_points)) - iv_sum
                # Adjust the largest IV by the difference
                max_iv = max(hp_iv, attack_iv, defense_iv)
                if hp_iv == max_iv:
                    hp_iv += diff
                elif attack_iv == max_iv:
                    attack_iv += diff
                else:
                    defense_iv += diff
            return hp_iv, attack_iv, defense_iv

        hp_iv, attack_iv, defense_iv = allocate_iv_points(total_iv_points)

        # Calculate the final stats
        hp = monster["hp"] + hp_iv
        attack = monster["attack"] + attack_iv
        defense = monster["defense"] + defense_iv

        import datetime

        # Set the egg hatch time to 90 days from now
        egg_hatch_time = datetime.datetime.utcnow() + datetime.timedelta(hours=36)
        try:
            async with self.bot.pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO monster_eggs (
                        user_id, egg_type, hp, attack, defense, element, url, hatch_time,
                        "IV", hp_iv, attack_iv, defense_iv
                    )
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12);
                    """,
                    member.id,
                    monster["name"],
                    hp,
                    attack,
                    defense,
                    monster["element"],
                    monster["url"],
                    egg_hatch_time,
                    iv_percentage,
                    hp_iv,
                    attack_iv,
                    defense_iv
                )

            await ctx.send(
                f"{member.mention} has received a **{monster['name']} Egg** with an IV of {iv_percentage:.2f}%! It will hatch in 36 hours."
            )
        except Exception as e:
            await ctx.send(f"An error occurred: {e}")


    @has_char()
    @is_gm()
    @commands.command(hidden=True)
    async def adventurereset(self, ctx, profile: Union[discord.Member, int] = None):
        try:
            # If no profile provided, use the command author
            if profile is None:
                profile_id = str(ctx.author.id)
            elif isinstance(profile, discord.Member):
                profile_id = str(profile.id)
            else:
                profile_id = str(profile)   

            
            
            # Query the database to get the guild for this profile
            async with self.bot.pool.acquire() as conn:
                guild_id = await conn.fetchval(
                    "SELECT guild FROM profile WHERE profile.user = $1", 
                    int(profile_id)
                )
            
            if guild_id is None:
                await ctx.send(f"No profile found for user ID {profile_id}.")
                return
            
            # Get all cooldown keys for this guild
            keys_to_delete = await self.bot.redis.keys(f"guildcd:{guild_id}:*")
            
            # Delete each matching key
            if keys_to_delete:
                await self.bot.redis.delete(*keys_to_delete)
                await ctx.send(f"All cooldown entries for guild ID {guild_id} have been deleted.")
            else:
                await ctx.send(f"No cooldown entries found for guild ID {guild_id}.")
                
        except Exception as e:
            await ctx.send(f"An error occurred: {e}")



    @is_gm()
    @commands.command()
    async def gmeggbatch(self, ctx, monster_name: str, *, id_text: str):
        """Grant eggs to multiple users at once.
        Usage: !gmeggbatch MonsterName id1, id2, id3, ..."""
        # Parse the comma-separated IDs
        member_ids = []
        for id_part in id_text.replace(',', ' ').split():
            id_part = id_part.strip()
            if id_part.isdigit():
                member_ids.append(int(id_part))

        if not member_ids:
            await ctx.send("No valid member IDs provided.")
            return

        # Load monsters data from JSON file
        try:
            with open("monsters.json", "r") as f:
                monsters_data = json.load(f)
        except Exception as e:
            await ctx.send("Error loading monsters data. Please contact the admin.")
            return

        # Search for the monster by name (ignoring case)
        monster = None
        for level_str, monster_list in monsters_data.items():
            for m in monster_list:
                if m["name"].lower() == monster_name.lower():
                    monster = m
                    break
            if monster:
                break

        if not monster:
            await ctx.send(f"Monster '{monster_name}' not found.")
            return

        import random
        import datetime

        success_count = 0
        failed_ids = []

        # Process each member ID
        for member_id in member_ids:
            try:
                # Generate IV percentage with weighted probabilities
                iv_percentage = random.uniform(10, 1000)

                if iv_percentage < 20:
                    iv_percentage = random.uniform(90, 100)
                elif iv_percentage < 70:
                    iv_percentage = random.uniform(80, 90)
                elif iv_percentage < 150:
                    iv_percentage = random.uniform(70, 80)
                elif iv_percentage < 350:
                    iv_percentage = random.uniform(60, 70)
                elif iv_percentage < 700:
                    iv_percentage = random.uniform(50, 60)
                else:
                    iv_percentage = random.uniform(30, 50)

                # Calculate total IV points (100% IV corresponds to 200 points)
                total_iv_points = (iv_percentage / 100) * 200

                def allocate_iv_points(total_points):
                    # Generate three random numbers
                    a = random.random()
                    b = random.random()
                    c = random.random()
                    total = a + b + c
                    # Normalize so that the sum is equal to total_points
                    hp_iv = total_points * (a / total)
                    attack_iv = total_points * (b / total)
                    defense_iv = total_points * (c / total)
                    # Round the IV points
                    hp_iv = int(round(hp_iv))
                    attack_iv = int(round(attack_iv))
                    defense_iv = int(round(defense_iv))
                    # Adjust if rounding errors cause total to deviate
                    iv_sum = hp_iv + attack_iv + defense_iv
                    if iv_sum != int(round(total_points)):
                        diff = int(round(total_points)) - iv_sum
                        # Adjust the largest IV by the difference
                        max_iv = max(hp_iv, attack_iv, defense_iv)
                        if hp_iv == max_iv:
                            hp_iv += diff
                        elif attack_iv == max_iv:
                            attack_iv += diff
                        else:
                            defense_iv += diff
                    return hp_iv, attack_iv, defense_iv

                hp_iv, attack_iv, defense_iv = allocate_iv_points(total_iv_points)

                # Calculate the final stats
                hp = monster["hp"] + hp_iv
                attack = monster["attack"] + attack_iv
                defense = monster["defense"] + defense_iv

                # Set the egg hatch time to 36 hours from now
                egg_hatch_time = datetime.datetime.utcnow() + datetime.timedelta(minutes=5)

                async with self.bot.pool.acquire() as conn:
                    await conn.execute(
                        """
                        INSERT INTO monster_eggs (
                            user_id, egg_type, hp, attack, defense, element, url, hatch_time,
                            "IV", hp_iv, attack_iv, defense_iv
                        )
                        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12);
                        """,
                        member_id,
                        monster["name"],
                        hp,
                        attack,
                        defense,
                        monster["element"],
                        monster["url"],
                        egg_hatch_time,
                        iv_percentage,
                        hp_iv,
                        attack_iv,
                        defense_iv
                    )

                success_count += 1
            except Exception as e:
                failed_ids.append(str(member_id))
                print(f"Error giving egg to user ID {member_id}: {e}")

        # Send a summary message
        if success_count > 0:
            await ctx.send(f"Added **{monster['name']} Eggs** to {success_count} members!")

        if failed_ids:
            failed_msg = f"Failed to add eggs to {len(failed_ids)} members"
            if len(failed_ids) <= 10:
                failed_msg += f": {', '.join(failed_ids)}"
            else:
                failed_msg += f": {', '.join(failed_ids[:10])}..."
            await ctx.send(failed_msg)

    @is_gm()
    @commands.command(hidden=True)
    async def processlevelup(self, ctx, target: discord.Member, xp: int, conn=None):
        try:
            if conn is None:
                conn = await self.bot.pool.acquire()
                local = True
            else:
                local = False
            reward_text = ""
            stat_point_received = False

            new_level = int(rpgtools.xptolevel(int(xp)))
            await ctx.send(new_level)
            if new_level % 2 == 0 and new_level > 0:
                await ctx.send("breaker")
                # Increment statpoints directly in the database and fetch the updated value
                update_query = 'UPDATE profile SET "statpoints" = "statpoints" + 1 WHERE "user" = $1 RETURNING "statpoints";'
                new_statpoints = await conn.fetchval(update_query, target.id)
                reward_text += f"You also received **1 stat point** (total: {new_statpoints}). "
                stat_point_received = True

            if (reward := random.choice(["crates", "money", "item"])) == "crates":
                if new_level < 6:
                    column = "crates_common"
                    amount = new_level
                    reward_text = f"**{amount}** {self.bot.cogs['Crates'].emotes.common}"
                elif new_level < 10:
                    column = "crates_uncommon"
                    amount = round(new_level / 2)
                    reward_text = f"**{amount}** {self.bot.cogs['Crates'].emotes.uncommon}"
                elif new_level < 18:
                    column = "crates_rare"
                    amount = 2
                    reward_text = f"**2** {self.bot.cogs['Crates'].emotes.rare}"
                elif new_level < 27:
                    column = "crates_rare"
                    amount = 3
                    reward_text = f"**3** {self.bot.cogs['Crates'].emotes.rare}"
                else:
                    column = "crates_magic"
                    amount = 1
                    reward_text = f"**1** {self.bot.cogs['Crates'].emotes.magic}"
                await self.bot.log_transaction(
                    ctx,
                    from_=0,
                    to=ctx.author.id,
                    subject="crates",
                    data={"Rarity": column.split("_")[1], "Amount": amount},
                )
                await self.bot.pool.execute(
                    f'UPDATE profile SET {column}={column}+$1 WHERE "user"=$2;',
                    amount,
                    target.id,
                )
            elif reward == "item":
                stat = min(round(new_level * 1.5), 75)
                item = await self.bot.create_random_item(
                    minstat=stat,
                    maxstat=stat,
                    minvalue=1000,
                    maxvalue=1000,
                    owner=target,
                    insert=False,
                    conn=conn,
                )

                item["name"] = _("Level {new_level} Memorial").format(new_level=new_level)
                reward_text = _("a special weapon")
                await self.bot.create_item(**item)
                await self.bot.log_transaction(
                    ctx,
                    from_=1,
                    to=target,
                    subject="Memorial Item",
                    data={"Name": item["name"], "Value": 1000},
                    conn=conn,
                )
            elif reward == "money":
                money = new_level * 1000
                await conn.execute(
                    'UPDATE profile SET "money"="money"+$1 WHERE "user"=$2;',
                    money,
                    target.id,
                )
                await self.bot.log_transaction(
                    ctx,
                    from_=1,
                    to=target,
                    subject="Level Up!",
                    data={"Gold": money},
                    conn=conn,
                )
                reward_text = f"**${money}**"
            old_level = new_level - 1
            additional = (
                _("You can now choose your second class using `{prefix}class`!").format(
                    prefix=ctx.clean_prefix
                )
                if old_level < 12 and new_level >= 12
                else ""
            )

            if local:
                await self.bot.pool.release(conn)

            await ctx.send(
                _(
                    "You reached a new level: **{new_level}** :star:! You received {reward} "
                    "as a reward :tada:! {additional}"
                ).format(new_level=new_level, reward=reward_text, additional=additional)
            )
        except Exception as e:
            import traceback
            error_message = f"Error occurred: {e}\n"
            error_message += traceback.format_exc()
            await ctx.send(error_message)
            print(error_message)


    @is_gm()
    @commands.command(hidden=True, brief=_("Wipe someone's donation perks."))
    @locale_doc
    async def gmwipeperks(self, ctx, target: UserWithCharacter, *, reason: str = None):
        _(
            """`<target>` - A discord User with character
            `[reason]` - The reason this action was done, defaults to the command message link

            Wipe a user's donation perks. This will:
              - set their background to the default
              - set both their classes to No Class
              - reverts all items to their original type and name
              - sets their guild's member limit to 50

            Only Game Masters can use this command."""
        )
        async with self.bot.pool.acquire() as conn:
            await conn.execute(
                'UPDATE profile SET "background"=$1, "class"=$2 WHERE "user"=$3;',
                "0",
                ["No Class", "No Class"],
                target.id,
            )
            await conn.execute(
                'UPDATE allitems SET "name"=CASE WHEN "original_name" IS NULL THEN'
                ' "name" ELSE "original_name" END, "type"=CASE WHEN "original_type" IS'
                ' NULL THEN "type" ELSE "original_type" END WHERE "owner"=$1;',
                target.id,
            )
            await conn.execute(
                'UPDATE guild SET "memberlimit"=$1 WHERE "leader"=$2;', 50, target.id
            )

        await ctx.send(
            _(
                "Successfully reset {target}'s background, class, item names and guild"
                " member limit."
            ).format(target=target)
        )

        with handle_message_parameters(
                content="**{gm}** reset **{target}**'s donator perks.\n\nReason: *{reason}*".format(
                    gm=ctx.author,
                    target=target,
                    reason=reason or f"<{ctx.message.jump_url}>",
                )
        ) as params:
            await self.bot.http.send_message(
                self.bot.config.game.gm_log_channel,
                params=params,
            )

    @is_gm()
    @commands.command(hidden=True, brief=_("Reset someone's classes"))
    @locale_doc
    async def gmresetclass(self, ctx, target: UserWithCharacter, *, reason: str = None):
        _(
            """`<target>` - a discord User with character
            `[reason]` - The reason this action was done, defaults to the command message link

            Reset a user's classes to No Class. They can then choose their class again for free.

            Only Game Masters can use this command."""
        )
        await self.bot.pool.execute(
            """UPDATE profile SET "class"='{"No Class", "No Class"}' WHERE "user"=$1;""",
            target.id,
        )

        await ctx.send(_("Successfully reset {target}'s class.").format(target=target))

        with handle_message_parameters(
                content="**{gm}** reset **{target}**'s class.\n\nReason: *{reason}*".format(
                    gm=ctx.author,
                    target=target,
                    reason=reason or f"<{ctx.message.jump_url}>",
                )
        ) as params:
            await self.bot.http.send_message(
                self.bot.config.game.gm_log_channel,
                params=params,
            )

    async def fetch_image(self, url: str):
        """Fetches an image from a given URL."""
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                return await resp.read()

    async def fetch_avatar(self, user_id: int):
        """Fetches the avatar of a user given their ID."""
        user = await self.bot.fetch_user(user_id)
        avatar_url = str(user.avatar)  # Here's the change
        return await self.fetch_image(avatar_url)

    @is_gm()
    @commands.command(name='poop')
    async def poop(self, ctx, user: discord.Member = None, *, reason=None):
        """Bans a user from the server by their tag and sends their cropped avatar on an external image."""
        external_image_url = "https://i.ibb.co/T1ZW86R/ew-i-stepped-in-shit.png"  # replace with your PNG link

        if not user:
            await ctx.send("Please tag a valid user.")
            return


        try:
            # Reinitialize the user to ensure a valid Member object
            user = await ctx.guild.fetch_member(user.id)

            # Fetch the base image and user avatar
            base_image_data = await self.fetch_image(external_image_url)
            avatar_data = await self.fetch_avatar(user.id)

            with io.BytesIO(base_image_data) as base_io, io.BytesIO(avatar_data) as avatar_io:
                base_image = Image.open(base_io).convert("RGBA")  # Convert base image to RGBA mode

                # Open the avatar, convert to RGBA, and resize
                avatar_image = Image.open(avatar_io).convert("RGBA")
                avatar_resized = avatar_image.resize((200, 200))  # Adjust size as needed

                # Rotate the avatar without any fill color
                avatar_resized = avatar_resized.rotate(35, expand=True)

                # Calculate positioning
                x_center = (base_image.width - avatar_resized.width) // 2
                y_position_75_percent = int(base_image.height * 0.75)
                y_center = y_position_75_percent - (avatar_resized.height // 2)

                # Use alpha channel as mask if available
                mask = avatar_resized.split()[3] if avatar_resized.mode == 'RGBA' else None

                base_image.paste(avatar_resized, (x_center, y_center), mask)

                with io.BytesIO() as output:
                    base_image.save(output, format="PNG")
                    output.seek(0)
                    await ctx.send(file=discord.File(output, 'banned_avatar.png'))

            # Ban the user
            #await ctx.guild.ban(user, reason=reason)
            await ctx.send(f"Trash taken out!") #{user.mention} has been banned.")
        except discord.Forbidden:
            await ctx.send("I do not have permission to ban this user.")
        except discord.HTTPException as e:
            await ctx.send(f"Failed to ban the user due to an HTTP error: {e}")
        except Exception as e:
            await ctx.send(f"An error occurred: {e}")

    @commands.command(name='trash')
    async def ban_by_id(self, ctx, user: discord.Member = None, *, reason=None):
        """Bans a user from the server by their ID and sends their cropped avatar on an external image."""
        external_image_url = "https://i.ibb.co/PT7S74n/images-jpeg-111.png"  # replace with your PNG link

        if self.protected_user_id and user.id == self.protected_user_id:
            await ctx.send("What are you high?")
            return

        try:
            base_image_data = await self.fetch_image(external_image_url)
            avatar_data = await self.fetch_avatar(user.id)

            with io.BytesIO(base_image_data) as base_io, io.BytesIO(avatar_data) as avatar_io:
                base_image = Image.open(base_io).convert("RGBA")  # Convert base image to RGBA mode

                # Open the avatar, convert to RGBA, and resize
                avatar_image = Image.open(avatar_io).convert("RGBA")
                avatar_resized = avatar_image.resize((100, 100))  # Adjust size as needed

                # Rotate the avatar without any fillcolor
                avatar_resized = avatar_resized.rotate(35, expand=True)

                # Calculate the vertical shift - 10% of the avatar's height
                vertical_shift = int(avatar_resized.height * 0.20)

                x_center = (base_image.width - avatar_resized.width) // 2
                y_center = (base_image.height - avatar_resized.height) // 2 - vertical_shift

                # Check if the avatar has an alpha channel (transparency) and use it as a mask if present
                mask = avatar_resized.split()[3] if avatar_resized.mode == 'RGBA' else None

                base_image.paste(avatar_resized, (x_center, y_center), mask)

                with io.BytesIO() as output:
                    base_image.save(output, format="PNG")
                    output.seek(0)
                    await ctx.send(file=discord.File(output, 'banned_avatar.png'))

            # user = Object(id=user_id)
            # await ctx.guild.ban(user, reason=reason)

            await ctx.send(f'Trash taken out!')
            # await ctx.send(f'The trash known as <@{user_id}> was taken out in **__1 server(s)__** for the reason: {reason}')
        except HTTPException:
            await ctx.send(f'Failed to fetch user or image.')
        except Exception as e:
            await ctx.send(f'An error occurred: {e}')


    @is_gm()
    @user_cooldown(604800)  # 7 days
    @commands.command(hidden=True, brief=_("Sign an item"))
    @locale_doc
    async def gmsign(self, ctx, itemid: int, text: str, *, reason: str = None):
        _(
            """`<itemid>` - the item's ID to sign
            `<text>` - The signature to write, must be less than 50 characters combined with the Game Master's tag. This should be in double quotes if the text has multiple words.
            `[reason]` - The reason this action was done, defaults to the command message link

            Sign an item. The item's signature is visible in a user's inventory.

            Only Game Masters can use this command.
            (This command has a cooldown of 7 days.)"""
        )
        text = f"{text} (signed by {ctx.author})"
        if len(text) > 100:
            await self.bot.reset_cooldown(ctx)
            return await ctx.send(_("Text exceeds 50 characters."))
        await self.bot.pool.execute(
            'UPDATE allitems SET "signature"=$1 WHERE "id"=$2;', text, itemid
        )
        await ctx.send(_("Item successfully signed."))

        with handle_message_parameters(
                content="**{gm}** signed {itemid} with *{text}*.\n\nReason: *{reason}*".format(
                    gm=ctx.author,
                    itemid=itemid,
                    text=text,
                    reason=reason or f"<{ctx.message.jump_url}>",
                )
        ) as params:
            await self.bot.http.send_message(
                self.bot.config.game.gm_log_channel,
                params=params,
            )

    async def end_auction(self, channel):
        """Helper method to handle auction ending"""
        if self.top_auction[0]:  # If there was at least one bid
            winner, winning_bid = self.top_auction
            await channel.send(
                f"🔨 No more bids for **{self.current_item}**.\n"
                f"Auction ended! **{winner.mention}** wins with a bid of **${winning_bid:,}**!"
            )
        else:
            await channel.send(
                f"🔨 No bids were made for **{self.current_item}**.\n"
                f"Auction ended with no winner."
            )

        self.top_auction = None
        self.current_item = None
        self.isbid = False
        self.auction_entry.clear()

    @is_gm()
    @commands.command()
    async def impersonate(self, ctx, user: discord.Member, *, message):
        # Delete the command message
        try:
            await ctx.message.delete()

            # Create a webhook with the target user's name and avatar
            webhook = await ctx.channel.create_webhook(name=user.display_name)

            # Send the message through the webhook
            await webhook.send(content=message, avatar_url=user.avatar.url)

            # Delete the webhook after sending the message
            await webhook.delete()
        except Exception as e:
            await ctx.send(e)

    @is_gm()
    @commands.command(hidden=True, brief=_("Start an auction"))
    @locale_doc
    async def gmauction(self, ctx, *, item: str):
        _(
            """`<item>` - a description of what is being auctioned
            Starts an auction on the support server. Users are able to bid. The auction timeframe extends by 30 minutes if users keep betting.
            The auction ends when no user bids in a 30 minute timeframe.
            The item is not given automatically and needs to be given manually.
            Only Game Masters can use this command."""
        )
        if self.top_auction is not None:
            return await ctx.send(_("There's still an auction running."))

        # Get the auctions channel
        channel = self.bot.get_channel(self.auction_channel_id) if self.auction_channel_id else None

        if not channel:
            return await ctx.send(_("Auctions channel wasn't found."))

        role = ctx.guild.get_role(self.auction_ping_role_id) if self.auction_ping_role_id else None

        if not role:
            return await ctx.send(_("Auction role wasn't found."))

        # Initialize auction state
        self.current_item = item
        self.top_auction = (None, 0)  # Start with no bidder and 0 bid
        self.auction_entry = asyncio.Event()
        self.auction_task = None  # Store the auction task

        # Send initial auction message
        await channel.send(
            f"{ctx.author.mention} started auction on **{item}**!\n\n"
            f"Current bid: **$0**\n\n"
            f"Please use `{ctx.clean_prefix}bid amount` to raise the bid from any channel.\n\n"
            f"If no more bids are sent within 30 minutes of the highest bid, the auction will end.\n"
            f"{role.mention}", allowed_mentions=discord.AllowedMentions(roles=True)
        )

        # Create and start the auction task
        self.auction_task = asyncio.create_task(self.run_auction(channel))
        try:
            await self.auction_task
        except Exception as e:
            await channel.send(f"Error in auction: {str(e)}")
            self.cleanup_auction()

    async def run_auction(self, channel):
        """Separate method to handle the auction loop"""
        try:
            while True:
                try:
                    # Wait for a bid
                    await asyncio.wait_for(self.auction_entry.wait(), timeout=1800)  # 30 minutes
                    self.auction_entry.clear()
                except asyncio.TimeoutError:
                    # No bids received within timeout period
                    await self.end_auction(channel)
                    break
        finally:
            self.cleanup_auction()

    def cleanup_auction(self):
        """Clean up auction state"""
        self.top_auction = None
        self.current_item = None
        self.auction_entry = None
        self.auction_task = None

    async def end_auction(self, channel):
        """Handle auction ending"""
        if self.top_auction[0]:
            await channel.send(
                f"🎉 Auction ended! **{self.current_item}** sold to {self.top_auction[0].mention} "
                f"for **${self.top_auction[1]:,}**!"
            )
        else:
            await channel.send(f"Auction ended with no bids for **{self.current_item}**.")

    @has_char()
    @commands.command(hidden=True, brief=_("Bid on an auction"))
    @locale_doc
    async def bid(self, ctx, amount: IntGreaterThan(0)):
        _(
            """`<amount>` - the amount of money to bid, must be higher than the current highest bid
            Bid on an ongoing auction.
            The amount is removed from you as soon as you bid and given back if someone outbids you."""
        )
        if self.top_auction is None:
            return await ctx.send(_("No auction running."))

        if self.top_auction[0] and self.top_auction[0].id == ctx.author.id:
            return await ctx.send(_("You cannot outbid yourself."))

        if amount <= self.top_auction[1]:
            return await ctx.send(_("Bid too low. Current bid is ${:,}.".format(self.top_auction[1])))

        if ctx.character_data["money"] < amount:
            return await ctx.send(_("You are too poor."))

        async with self.bot.pool.acquire() as conn:
            # If there was a previous bidder, refund their money
            if self.top_auction[0]:
                await conn.execute(
                    'UPDATE profile SET "money"="money"+$1 WHERE "user"=$2;',
                    self.top_auction[1],
                    self.top_auction[0].id,
                )
                await self.bot.log_transaction(
                    ctx,
                    from_=1,
                    to=self.top_auction[0].id,
                    subject="bid_refund",
                    data={"Gold": self.top_auction[1]},
                    conn=conn,
                )

            # Take money from new bidder
            await conn.execute(
                'UPDATE profile SET "money"="money"-$1 WHERE "user"=$2;',
                amount,
                ctx.author.id,
            )
            await self.bot.log_transaction(
                ctx,
                from_=ctx.author.id,
                to=2,
                subject="bid",
                data={"Gold": amount},
                conn=conn,
            )

            # Update auction state
            old_top = self.top_auction[0]
            old_bid = self.top_auction[1]
            self.top_auction = (ctx.author, amount)
            self.auction_entry.set()

        # Send bid notifications
        await ctx.send(_("Bid submitted."))

        channel = self.bot.get_channel(self.auction_channel_id) if self.auction_channel_id else None

        if channel:
            await channel.send(
                f"**{ctx.author.mention}** bids **${amount:,}** on **{self.current_item}**!\n"
                + (f"Previous bidder: {old_top.mention}\n" if old_top else "")
                + f"Previous bid: **${old_bid:,}**"
            )

    @is_gm()
    @commands.command(
        aliases=["gmcd", "gmsetcd"], hidden=True, brief=_("Set a cooldown")
    )
    @locale_doc
    async def gmsetcooldown(
            self,
            ctx,
            user: discord.User | int,
            command: str,
            *,
            reason: str = None,
    ):
        _(
            """`<user>` - A discord User or their User ID
            `<command>` - the command which the cooldown is being set for (subcommands in double quotes, i.e. "guild create")
            `[reason]` - The reason this action was done, defaults to the command message link

            Reset a cooldown for a user and commmand.

            Only Game Masters can use this command."""
        )
        if not isinstance(user, int):
            user_id = user.id
        else:
            user_id = user

        result = await self.bot.redis.execute_command("DEL", f"cd:{user_id}:{command}")

        if result == 1:
            await ctx.send(_("The cooldown has been updated!"))
            if not self.protected_user_id or ctx.author.id != self.protected_user_id:
                with handle_message_parameters(
                        content="**{gm}** reset **{user}**'s cooldown for the {command} command.\n\nReason: *{reason}*".format(
                            gm=ctx.author,
                            user=user,
                            command=command,
                            reason=reason or f"<{ctx.message.jump_url}>",
                        )
                ) as params:
                    await self.bot.http.send_message(
                        self.bot.config.game.gm_log_channel,
                        params=params,
                    )
        else:
            await ctx.send(
                _(
                    "Cooldown setting unsuccessful (maybe you mistyped the command name"
                    " or there is no cooldown for the user?)."
                )
            )

    @commands.command(hidden=True, name="addgm")
    @commands.is_owner()  # Only bot owner can add GMs
    async def add_game_master(self, ctx: Context, user: discord.Member):
        """Add a user as a game master."""
        try:
            async with self.bot.pool.acquire() as conn:
                # Check if user is already a GM
                existing = await conn.fetchrow(
                    "SELECT 1 FROM game_masters WHERE user_id = $1", 
                    user.id
                )
                
                if existing:
                    await ctx.send(f"{user.mention} is already a game master.")
                    return
                
                # Create invitation embed and view
                invite_embed = discord.Embed(
                    title="🎯 Game Master Invitation",
                    description=f"{user.mention}, you have been invited to become a **Game Master**.\n\n"
                               f"**Invited by:** {ctx.author.mention}\n"
                               f"**Role:** Game Master\n\n"
                               f"Please click a button below to accept or decline this invitation.",
                    color=0x0099ff,
                    timestamp=discord.utils.utcnow()
                )
                invite_embed.set_footer(text="This invitation will expire in 2 minutes")
                
                # Create the view with buttons
                view = GMInviteView(user, timeout=120)
                
                # Send the invitation message
                message = await ctx.send(embed=invite_embed, view=view)
                
                # Wait for the user's response
                await view.wait()
                
                # Handle the response
                if view.value is None:
                    # Timeout occurred
                    timeout_embed = discord.Embed(
                        title="⏰ Invitation Expired",
                        description=f"The Game Master invitation for {user.mention} has expired.",
                        color=0xff9900
                    )
                    await message.edit(embed=timeout_embed, view=None)
                    return
                
                elif view.value is False:
                    # User declined
                    declined_embed = discord.Embed(
                        title="❌ Invitation Declined",
                        description=f"{user.mention} has declined the Game Master invitation.",
                        color=0xff0000
                    )
                    await message.edit(embed=declined_embed, view=None)
                    return
                
                # User accepted - proceed with adding GM
                await conn.execute(
                    "INSERT INTO game_masters (user_id, granted_by) VALUES ($1, $2)",
                    user.id, ctx.author.id
                )
                
                # Clear cache if it exists
                if hasattr(self.bot, '_gm_cache'):
                    self.bot._gm_cache.add(user.id)
                
                # Assign Discord role
                try:
                    gm_role = ctx.guild.get_role(self.gm_role_id) if self.gm_role_id else None
                    if gm_role:
                        await user.add_roles(gm_role)
                except:
                    pass  # Silently pass if role assignment fails
                
                # Success embed
                success_embed = discord.Embed(
                    title="✅ Game Master Access Granted",
                    description=f"**User:** {user.mention}\n**Discord ID:** Saved (hashed)\n**Status:** Access Granted",
                    color=0x00ff00,
                    timestamp=discord.utils.utcnow()
                )
                success_embed.set_footer(text=f"Granted by {ctx.author}")
                
                await message.edit(embed=success_embed, view=None)
                
        except Exception as e:
            error_embed = discord.Embed(
                title="❌ Error",
                description=f"Failed to add game master: {str(e)}",
                color=0xff0000
            )
            await ctx.send(embed=error_embed)

    @commands.command(hidden=True, name="removegm")
    @commands.is_owner()  # Only bot owner can remove GMs
    async def remove_game_master(self, ctx: Context, user: discord.Member):
        """Remove a user as a game master."""
        try:
            async with self.bot.pool.acquire() as conn:
                result = await conn.execute(
                    "DELETE FROM game_masters WHERE user_id = $1",
                    user.id
                )

                if result == "DELETE 0":
                    await ctx.send(f"{user.mention} is not a game master.")
                    return

                # Clear from cache if it exists
                if hasattr(self.bot, '_gm_cache'):
                    self.bot._gm_cache.discard(user.id)

                # Remove Discord role
                try:
                    gm_role = ctx.guild.get_role(self.gm_role_id) if self.gm_role_id else None
                    if gm_role and gm_role in user.roles:
                        await user.remove_roles(gm_role)
                except:
                    pass  # Silently pass if role removal fails

                await ctx.send(f"✅ {user.mention} has been removed as a game master.")

        except Exception as e:
            await ctx.send(f"❌ Error removing game master: {str(e)}")

    @commands.command(hidden=True, name="listgms")
    @is_gm()  # GMs can see the list
    async def list_game_masters(self, ctx: Context):
        """List all game masters."""
        try:
            async with self.bot.pool.acquire() as conn:
                gms = await conn.fetch(
                    "SELECT user_id, granted_at FROM game_masters ORDER BY granted_at"
                )

                if not gms:
                    await ctx.send("No game masters found.")
                    return

                gm_list = []
                for gm in gms:
                    user = self.bot.get_user(gm['user_id'])
                    if user:
                        gm_list.append(f"• {user.mention} (added {gm['granted_at'].strftime('%Y-%m-%d')})")
                    else:
                        gm_list.append(f"• Unknown User ({gm['user_id']})")

                embed = discord.Embed(
                    title="Game Masters",
                    description="\n".join(gm_list),
                    color=0x00ff00
                )
                await ctx.send(embed=embed)

        except Exception as e:
            await ctx.send(f"❌ Error listing game masters: {str(e)}")


    @is_gm()
    @commands.command(hidden=True)
    async def fix_sp(self, ctx):

        async with self.bot.pool.acquire() as conn:
            rows = await conn.fetch(
                'SELECT profile.user, name, xp, statpoints, stathp, statatk, statdef FROM profile ORDER BY xp DESC;')
            messages = []

            for row in rows:
                level = rpgtools.xptolevel(row['xp'])
                expected_total_statpoints = max(0, level // 2)

                original_statpoints = row['statpoints']
                original_stathp = row['stathp']
                original_statatk = row['statatk']
                original_statdef = row['statdef']

                # Clamp invalid negative allocations before recalculating totals.
                new_stathp = max(0, original_stathp)
                new_statatk = max(0, original_statatk)
                new_statdef = max(0, original_statdef)

                allocated_total = new_stathp + new_statatk + new_statdef
                overflow = max(0, allocated_total - expected_total_statpoints)

                if overflow > 0:
                    deduct_from_hp = min(new_stathp, overflow)
                    new_stathp -= deduct_from_hp
                    overflow -= deduct_from_hp

                    deduct_from_atk = min(new_statatk, overflow)
                    new_statatk -= deduct_from_atk
                    overflow -= deduct_from_atk

                    deduct_from_def = min(new_statdef, overflow)
                    new_statdef -= deduct_from_def

                new_statpoints = expected_total_statpoints - (new_stathp + new_statatk + new_statdef)

                if (
                    new_statpoints != original_statpoints
                    or new_stathp != original_stathp
                    or new_statatk != original_statatk
                    or new_statdef != original_statdef
                ):
                    await conn.execute(
                        'UPDATE profile SET statpoints = $1, stathp = $2, statatk = $3, statdef = $4 WHERE profile.user = $5;',
                        new_statpoints, new_stathp, new_statatk, new_statdef, row['user']
                    )
                    messages.append(
                        f"Fixed {row['name']} ({row['user']}): "
                        f"SP {original_statpoints}->{new_statpoints}, "
                        f"HP {original_stathp}->{new_stathp}, "
                        f"ATK {original_statatk}->{new_statatk}, "
                        f"DEF {original_statdef}->{new_statdef} (Level {level})."
                    )

                if len(messages) >= 5:
                    await ctx.send("\n".join(messages))
                    messages = []
                    await asyncio.sleep(1)

            if messages:
                await ctx.send("\n".join(messages))
            else:
                await ctx.send("All players already have valid stat allocations and stat point totals.")

    @is_gm()
    @commands.command(
        aliases=["gmml", "gmluck"],
        hidden=True,
        brief=_("Update the luck for all followers"),
    )
    @locale_doc
    async def gmmakeluck(self, ctx) -> None:
        _(
            """Sets the luck for all gods to a random value and give bonus luck to the top 25 followers.

            Only Game Masters can use this command."""
        )
        text_collection = ["**This week's luck has been decided:**\n"]
        all_ids = []
        async with self.bot.pool.acquire() as conn:
            for god in self.bot.config.gods:
                luck = (
                        random.randint(
                            god["boundary_low"] * 100, god["boundary_high"] * 100
                        )
                        / 100
                )
                ids = await conn.fetch(
                    'UPDATE profile SET "luck"=round($1, 2) WHERE "god"=$2 RETURNING'
                    ' "user";',
                    luck,
                    god["name"],
                )
                all_ids.extend([u["user"] for u in ids])
                top_followers = [
                    u["user"]
                    for u in await conn.fetch(
                        'SELECT "user" FROM profile WHERE "god"=$1 ORDER BY "favor"'
                        " DESC LIMIT 25;",
                        god["name"],
                    )
                ]
                await conn.execute(
                    'UPDATE profile SET "luck"=CASE WHEN "luck"+round($1, 2)>=2.0 THEN'
                    ' 2.0 ELSE "luck"+round($1, 2) END WHERE "user"=ANY($2);',
                    0.5,
                    top_followers[:5],
                )
                await conn.execute(
                    'UPDATE profile SET "luck"=CASE WHEN "luck"+round($1, 2)>=2.0 THEN'
                    ' 2.0 ELSE "luck"+round($1, 2) END WHERE "user"=ANY($2);',
                    0.4,
                    top_followers[5:10],
                )
                await conn.execute(
                    'UPDATE profile SET "luck"=CASE WHEN "luck"+round($1, 2)>=2.0 THEN'
                    ' 2.0 ELSE "luck"+round($1, 2) END WHERE "user"=ANY($2);',
                    0.3,
                    top_followers[10:15],
                )
                await conn.execute(
                    'UPDATE profile SET "luck"=CASE WHEN "luck"+round($1, 2)>=2.0 THEN'
                    ' 2.0 ELSE "luck"+round($1, 2) END WHERE "user"=ANY($2);',
                    0.2,
                    top_followers[15:20],
                )
                await conn.execute(
                    'UPDATE profile SET "luck"=CASE WHEN "luck"+round($1, 2)>=2.0 THEN'
                    ' 2.0 ELSE "luck"+round($1, 2) END WHERE "user"=ANY($2);',
                    0.1,
                    top_followers[20:25],
                )
                text_collection.append(f"{god['name']} set to {luck}.")
            await conn.execute('UPDATE profile SET "favor"=0 WHERE "god" IS NOT NULL;')
            text_collection.append("Godless set to 1.0")
            ids = await conn.fetch(
                'UPDATE profile SET "luck"=1.0 WHERE "god" IS NULL RETURNING "user";'
            )
            all_ids.extend([u["user"] for u in ids])
        await ctx.send("\n".join(text_collection))

        with handle_message_parameters(
                content=f"**{ctx.author}** updated the global luck"
        ) as params:
            await self.bot.http.send_message(
                self.bot.config.game.gm_log_channel,
                params=params,
            )

    def cleanup_code(self, content: str) -> str:
        """Automatically removes code blocks from the code."""
        if content.startswith("```") and content.endswith("```"):
            return "\n".join(content.split("\n")[1:-1])
        return content.strip("` \n")

    @is_gm()
    @commands.command(hidden=True, name="checkuserid")
    async def checkuserid(self, ctx, discordid):
        discord_id = discordid

        # SQL query to fetch the "user" column where discordtag = $1
        query = 'SELECT "user" FROM profile WHERE discordtag = $1'

        try:
            # Fetch data from the database
            async with self.bot.pool.acquire() as conn:
                rows = await conn.fetch(query, discord_id)

            if rows:
                users = [row["user"] for row in rows]

                # Send the users that match the discord ID
                await ctx.send(f"{', '.join(map(str, users))}")
            else:
                await ctx.send(f"No users found with Discord ID {discord_id}.")

        except Exception as e:
            await ctx.send(f"An error occurred: {e}")

    @is_gm()
    @commands.command(hidden=True, name="eval")
    async def _eval(self, ctx: Context, *, body: str) -> None:
        """Evaluates a code"""

        if ctx.author.id not in self.eval_allowed_user_ids:
            return

        env = {
            "bot": self.bot,
            "ctx": ctx,
            "channel": ctx.channel,
            "author": ctx.author,
            "guild": ctx.guild,
            "message": ctx.message,
            "__last__": self._last_result,
        }

        env.update(globals())

        body = self.cleanup_code(body)
        stdout = io.StringIO()
        token = random_token(self.bot.user.id)

        to_compile = f'async def func():\n{textwrap.indent(body, "  ")}'

        try:
            exec(to_compile, env)
        except Exception as e:
            return await ctx.send(f"```py\n{e.__class__.__name__}: {e}\n```")

        func = env["func"]
        try:
            with redirect_stdout(stdout):
                ret = await func()
            if ret is not None:
                ret = str(ret).replace(self.bot.http.token, token)
        except Exception:
            value = stdout.getvalue()
            value = value.replace(self.bot.http.token, token)
            await ctx.send(f"```py\n{value}{traceback.format_exc()}\n```")
        else:
            value = stdout.getvalue()
            value = value.replace(self.bot.http.token, token)
            try:
                await ctx.message.add_reaction("<:blackcheck:441826948919066625>")
            except discord.Forbidden:
                pass

            if ret is None:
                if value:
                    await ctx.send(f"```py\n{value}\n```")
            else:
                self._last_result = ret
                await ctx.send(f"```py\n{value}{ret}\n```")

    @is_gm()
    @commands.command(hidden=True)
    async def purge(self, ctx, amount: int):
        # Delete messages from the channel
        await ctx.channel.purge(limit=amount + 1)

    @is_gm()
    @commands.command(hidden=True)
    async def getusergod(self, ctx, god_name: str, get_names: bool = False):

        def split_message(message: str, max_length: int = 2000):
            """Splits a message into chunks that are less than max_length."""
            return [message[i:i + max_length] for i in range(0, len(message), max_length)]

        async def fetch_users_concurrently(user_ids, batch_size=5):
            """Fetch users concurrently in batches to avoid rate limits."""
            fetched_users = {}
            for i in range(0, len(user_ids), batch_size):
                batch = user_ids[i:i + batch_size]
                users = await asyncio.gather(*(self.bot.fetch_user(uid) for uid in batch))
                for uid, user in zip(batch, users):
                    fetched_users[uid] = user
            return fetched_users

        try:
            async with self.bot.pool.acquire() as conn:
                if god_name.lower() == "all":
                    query = '''
                        SELECT god, COUNT(*) AS count
                        FROM profile
                        GROUP BY god
                    '''
                    data = await conn.fetch(query)

                    if data:
                        if get_names:
                            user_ids = [row['user'] for row in data]
                            users_data = await fetch_users_concurrently(user_ids)

                            users = []
                            for row in data:
                                user = users_data.get(row['user'], None)
                                god = row['god'] if row['god'] is not None else 'Godless'
                                users.append(f"{god}: {user.name if user else 'Unknown User'}")

                            chunks = split_message("\n".join(users))
                            for chunk in chunks:
                                await ctx.send(chunk)
                        else:
                            god_counts = {row['god'] if row['god'] is not None else 'Godless': row['count'] for row in
                                          data}
                            message = "\n".join([f"{god}: {count} users" for god, count in god_counts.items()])
                            chunks = split_message(message)
                            for chunk in chunks:
                                await ctx.send(chunk)

                    else:
                        await ctx.send("No data found in the profile table")

                elif god_name.lower() == "none":
                    query = '''
                        SELECT "user"
                        FROM profile
                        WHERE god IS NULL
                    '''
                    data = await conn.fetch(query)

                    if data:
                        user_ids = [row['user'] for row in data]
                        users_data = await fetch_users_concurrently(user_ids)

                        users = [users_data.get(uid, 'Unknown User').name for uid in user_ids]

                        chunks = split_message("\n".join(users))
                        for chunk in chunks:
                            await ctx.send(chunk)
                    else:
                        await ctx.send("No godless users found")

                else:
                    if get_names:
                        query = '''
                            SELECT "user"
                            FROM profile
                            WHERE god = $1
                        '''
                        data = await conn.fetch(query, god_name)

                        if data:
                            user_ids = [row['user'] for row in data]
                            users_data = await fetch_users_concurrently(user_ids)

                            users = [users_data.get(uid, 'Unknown User').name for uid in user_ids]

                            chunks = split_message("\n".join(users))
                            for chunk in chunks:
                                await ctx.send(chunk)
                        else:
                            await ctx.send(f"No users found for {god_name}")
                    else:
                        query = '''
                            SELECT COUNT(*)
                            FROM profile
                            WHERE god = $1
                        '''
                        count = await conn.fetchval(query, god_name)
                        await ctx.send(f"{god_name} has {count} users")

        except Exception as e:
            await ctx.send(f"An error occurred: {str(e)}")

    @is_gm()
    @commands.command(hidden=True)
    async def assign_roles(self, ctx):
        async with self.bot.pool.acquire() as conn:
            data = await conn.fetch("SELECT user FROM profile")

            role_id = self.assign_roles_role_id

            for row in data:
                user_id = row['user']

                member = ctx.guild.get_member(user_id)
                role = ctx.guild.get_role(role_id)

                if member and role:
                    await member.add_roles(role)
                    await ctx.send(f"Assigned {role.name} role to {member.display_name}")

    @is_gm()
    @commands.command(hidden=True)
    async def fetch(self, ctx):
        async with self.bot.pool.acquire() as conn:
            async with conn.transaction():
                try:
                    rows = await conn.fetch('SELECT "user", discordtag FROM profile')
                    user_data = [(row['user'], row['discordtag']) for row in rows]

                    for i in range(0, len(user_data), 2):  # Fetch and update two users at a time
                        user_data_chunk = user_data[i:i + 2]  # Fetch two user data entries at a time

                        for user_id, current_tag in user_data_chunk:
                            try:
                                user = await self.bot.fetch_user(user_id)
                            except HTTPException as e:
                                await ctx.send(
                                    f"Rate limit exceeded. Waiting for retry... Retry after: {e.retry_after} seconds")
                                await asyncio.sleep(e.retry_after)  # Wait for the specified retry_after period
                                continue

                            username = user.name

                            if username == current_tag:
                                await ctx.send(f"No update needed for: {username} (ID: {user_id})")
                                continue

                            try:
                                result = await conn.execute('UPDATE profile SET discordtag = $1 WHERE "user" = $2',
                                                            username, user_id)
                                if result == "UPDATE 1":
                                    await ctx.send(f"Updated: {username} (ID: {user_id})")
                                else:
                                    await ctx.send(f"No rows updated for user ID: {user_id}")
                            except Exception as e:
                                await ctx.send(f"An error occurred during update: {e}")

                            await asyncio.sleep(1)  # Add a delay of 1 second between each update
                except Exception as e:
                    await ctx.send(f"An error occurred during transaction: {e}")

    @is_gm()
    @commands.command(hidden=True)
    async def evall(self, ctx: Context, *, code: str) -> None:
        """[Owner only] Evaluates python code on all processes."""

        if not self.protected_user_id or ctx.author.id != self.protected_user_id:
            return

        data = await self.bot.cogs["Sharding"].handler(
            "evaluate", self.bot.shard_count, {"code": code}
        )
        filtered_data = {instance: data.count(instance) for instance in data}
        pretty_data = "".join(
            f"```py\n{count}x | {instance[6:]}"
            for instance, count in filtered_data.items()
        )
        if len(pretty_data) > 2000:
            pretty_data = pretty_data[:1997] + "..."
        await ctx.send(pretty_data)

    @is_gm()
    @commands.command(hidden=True)
    async def assignroles(self, ctx):
        god_roles = self.support_god_role_ids
        godless_role_id = self.godless_role_id

        try:
            async with self.bot.pool.acquire() as conn:
                query = '''
                    SELECT "user", god
                    FROM profile
                    WHERE god IS NOT NULL
                '''

                data = await conn.fetch(query)

                guild = self.bot.get_guild(self.bot.config.game.support_server_id) or ctx.guild
                if data:
                    for row in data:
                        discord_user_id = int(row['user'])
                        god = row['god']

                        member = guild.get_member(discord_user_id)
                        if member is None:
                            try:
                                member = await guild.fetch_member(discord_user_id)
                            except (discord.NotFound, discord.Forbidden):
                                member = None

                        if member:
                            if god in god_roles:
                                role_id = god_roles[god]
                                new_role = guild.get_role(role_id)

                                # Remove old god roles if they exist and don't match the new one
                                for god_name, god_role_id in god_roles.items():
                                    role = guild.get_role(god_role_id)
                                    if role in member.roles and role != new_role:
                                        await member.remove_roles(role)
                                        await ctx.send(
                                            f"Removed the role {role.name} from {member.display_name} (Profile ID: {discord_user_id}).")

                                # Remove godless role if present
                                godless_role = guild.get_role(godless_role_id)
                                if godless_role and godless_role in member.roles:
                                    await member.remove_roles(godless_role)

                                # Assign the new god role if the member doesn't have it already
                                if new_role not in member.roles:
                                    try:
                                        await member.add_roles(new_role)
                                        await ctx.send(
                                            f"Assigned the role {new_role.name} to {member.display_name} (Profile ID: {discord_user_id}) for god {god}.")
                                    except discord.Forbidden:
                                        await ctx.send(
                                            f"Cannot assign the role {new_role.name} to {member.display_name} due to role hierarchy.")
                            else:
                                await ctx.send(
                                    f"Skipping {member.display_name} (Profile ID: {discord_user_id}) as their god '{god}' is not in the configured list.")
                else:
                    await ctx.send("No god followers found in the profile table.")

                # Assign godless role to Godless users
                godless_query = '''
                    SELECT "user"
                    FROM profile
                    WHERE god IS NULL
                '''
                godless_data = await conn.fetch(godless_query)
                if godless_data:
                    for row in godless_data:
                        discord_user_id = int(row['user'])
                        member = guild.get_member(discord_user_id)
                        if member is None:
                            try:
                                member = await guild.fetch_member(discord_user_id)
                            except (discord.NotFound, discord.Forbidden):
                                member = None
                        if member:
                            # Remove any god roles in case they linger
                            for god_role_id in god_roles.values():
                                role = guild.get_role(god_role_id)
                                if role and role in member.roles:
                                    await member.remove_roles(role)

                            godless_role = guild.get_role(godless_role_id)
                            if godless_role and godless_role not in member.roles:
                                try:
                                    await member.add_roles(godless_role)
                                    await ctx.send(
                                        f"Assigned the role {godless_role.name} to {member.display_name} (Profile ID: {discord_user_id}) for Godless.")
                                except discord.Forbidden:
                                    await ctx.send(
                                        f"Cannot assign the role {godless_role.name} to {member.display_name} due to role hierarchy.")

                await ctx.send("Roles updated based on gods.")

        except Exception as e:
            await ctx.send(f"An error occurred: {str(e)}")

    @is_gm()
    @commands.command(hidden=True)
    async def assignrolesprimary(self, ctx):
        god_roles = self.support_god_role_ids
        godless_role_id = self.godless_role_id

        try:
            async with self.bot.pool.acquire() as conn:
                query = '''
                        SELECT "user", god
                        FROM profile
                        WHERE god IS NOT NULL
                    '''

                data = await conn.fetch(query)

                guild = self.bot.get_guild(self.bot.config.game.support_server_id) or ctx.guild
                if data:
                    for row in data:
                        discord_user_id = int(row['user'])
                        god = row['god']

                        member = guild.get_member(discord_user_id)
                        if member is None:
                            try:
                                member = await guild.fetch_member(discord_user_id)
                            except (discord.NotFound, discord.Forbidden):
                                member = None

                        if member:
                            if god in god_roles:
                                role_id = god_roles[god]
                                new_role = guild.get_role(role_id)

                                # Remove old god roles if they exist and don't match the new one
                                for god_name, god_role_id in god_roles.items():
                                    role = guild.get_role(god_role_id)
                                    if role in member.roles and role != new_role:
                                        await member.remove_roles(role)
                                        await ctx.send(
                                            f"Removed the role {role.name} from {member.display_name} (Profile ID: {discord_user_id}).")

                                # Remove godless role if present
                                godless_role = guild.get_role(godless_role_id)
                                if godless_role and godless_role in member.roles:
                                    await member.remove_roles(godless_role)

                                # Assign the new god role if the member doesn't have it already
                                if new_role not in member.roles:
                                    try:
                                        await member.add_roles(new_role)
                                        await ctx.send(
                                            f"Assigned the role {new_role.name} to {member.display_name} (Profile ID: {discord_user_id}) for god {god}.")
                                    except discord.Forbidden:
                                        await ctx.send(
                                            f"Cannot assign the role {new_role.name} to {member.display_name} due to role hierarchy.")
                            else:
                                await ctx.send(
                                    f"Skipping {member.display_name} (Profile ID: {discord_user_id}) as their god '{god}' is not in the configured list.")
                else:
                    await ctx.send("No god followers found in the profile table.")

                # Assign godless role to Godless users
                godless_query = '''
                        SELECT "user"
                        FROM profile
                        WHERE god IS NULL
                    '''
                godless_data = await conn.fetch(godless_query)
                if godless_data:
                    for row in godless_data:
                        discord_user_id = int(row['user'])
                        member = guild.get_member(discord_user_id)
                        if member is None:
                            try:
                                member = await guild.fetch_member(discord_user_id)
                            except (discord.NotFound, discord.Forbidden):
                                member = None
                        if member:
                            # Remove any god roles in case they linger
                            for god_role_id in god_roles.values():
                                role = guild.get_role(god_role_id)
                                if role and role in member.roles:
                                    await member.remove_roles(role)

                            godless_role = guild.get_role(godless_role_id)
                            if godless_role and godless_role not in member.roles:
                                try:
                                    await member.add_roles(godless_role)
                                    await ctx.send(
                                        f"Assigned the role {godless_role.name} to {member.display_name} (Profile ID: {discord_user_id}) for Godless.")
                                except discord.Forbidden:
                                    await ctx.send(
                                        f"Cannot assign the role {godless_role.name} to {member.display_name} due to role hierarchy.")

                await ctx.send("Roles updated based on gods.")

        except Exception as e:
            await ctx.send(f"An error occurred: {str(e)}")

    @is_gm()
    @commands.command(hidden=True, brief=_("Look up alt links for a user"))
    @locale_doc
    async def gmalt(self, ctx, user: discord.User | int):
        """Look up whether a user is a main or alt and show the link."""
        user_id = user if isinstance(user, int) else user.id

        async with self.bot.pool.acquire() as conn:
            link = await conn.fetchrow(
                "SELECT main, alt, declared_at FROM alt_links WHERE main = $1 OR alt = $1;",
                user_id,
            )
            pending = await conn.fetchrow(
                "SELECT main, alt, requested_at FROM alt_link_requests WHERE main = $1 OR alt = $1;",
                user_id,
            )

        if link:
            main_user = await self.bot.get_user_global(int(link["main"]))
            alt_user = await self.bot.get_user_global(int(link["alt"]))
            main_name = main_user.name if main_user else str(link["main"])
            alt_name = alt_user.name if alt_user else str(link["alt"])

            role = "main" if user_id == link["main"] else "alt"
            await ctx.send(
                f"Link found: **{main_name}** (main) ↔ **{alt_name}** (alt)\n"
                f"Queried user is the **{role}**. Declared at: {link['declared_at']}"
            )
            return

        if pending:
            main_user = await self.bot.get_user_global(int(pending["main"]))
            alt_user = await self.bot.get_user_global(int(pending["alt"]))
            main_name = main_user.name if main_user else str(pending["main"])
            alt_name = alt_user.name if alt_user else str(pending["alt"])
            await ctx.send(
                f"Pending link: **{main_name}** (main) ↔ **{alt_name}** (alt)\n"
                f"Requested at: {pending['requested_at']}"
            )
            return

        await ctx.send("No alt link found for that user.")

    @is_gm()
    @commands.command(hidden=True, aliases=["gmaltunlink"], brief=_("Remove an alt link"))
    @locale_doc
    async def gmunlinkalt(self, ctx, user: discord.User | int, *, reason: str = None):
        """Remove a linked main/alt pair."""
        user_id = user if isinstance(user, int) else user.id

        async with self.bot.pool.acquire() as conn:
            link = await conn.fetchrow(
                "SELECT main, alt FROM alt_links WHERE main = $1 OR alt = $1;",
                user_id,
            )
            if not link:
                return await ctx.send("No alt link found for that user.")

            await conn.execute(
                "DELETE FROM alt_links WHERE main = $1 AND alt = $2;",
                link["main"],
                link["alt"],
            )

        main_user = await self.bot.get_user_global(int(link["main"]))
        alt_user = await self.bot.get_user_global(int(link["alt"]))
        main_name = main_user.name if main_user else str(link["main"])
        alt_name = alt_user.name if alt_user else str(link["alt"])

        await ctx.send(f"Removed alt link: **{main_name}** (main) ↔ **{alt_name}** (alt)")

        with handle_message_parameters(
                content="**{gm}** removed alt link: **{main}** ↔ **{alt}**.\n\nReason: *{reason}*".format(
                    gm=ctx.author,
                    main=main_name,
                    alt=alt_name,
                    reason=reason or f"<{ctx.message.jump_url}>",
                )
        ) as params:
            await self.bot.http.send_message(
                self.bot.config.game.gm_log_channel,
                params=params,
            )

    @is_gm()
    @commands.command(hidden=True)
    async def bash(self, ctx: Context, *, command_to_run: str) -> None:
        """[Owner Only] Run shell commands."""
        await shell.run(command_to_run, ctx)

    @is_gm()
    @commands.command(hidden=True)
    async def runas(self, ctx, member_arg: str, *, command: str):

        # Check if the command is used by GM and in the allowed channels
        try:

            if command == str("eval"):
                return

            if command == str("evall"):
                return

            if self.protected_user_id and str(member_arg) == str(self.protected_user_id):
                await ctx.send("You can't do this.")
                return

            try:
                member = await commands.MemberConverter().convert(ctx, member_arg)
            except commands.BadArgument:
                try:
                    member_id = int(member_arg)
                    member = await ctx.bot.fetch_user(member_id)
                except (ValueError, discord.NotFound):
                    await ctx.send("Member not found.")
                    return

            fake_msg = copy.copy(ctx.message)
            fake_msg._update(dict(channel=ctx.channel, content=ctx.clean_prefix + command))
            fake_msg.author = member

            new_ctx = await ctx.bot.get_context(fake_msg, cls=commands.Context)

            await ctx.bot.invoke(new_ctx)
            try:
                await ctx.message.delete()
            except Exception as e:

                return
        except Exception as e:
            await ctx.send(e)


    def replace_md(self, s):
        opening = True
        out = []
        for i in s:
            if i == "`":
                if opening is True:
                    opening = False
                    i = "<code>"
                else:
                    opening = True
                    i = "</code>"
            out.append(i)
        reg = re.compile(r'\[(.+)\]\(([^ ]+?)( "(.+)")?\)')
        text = "".join(out)
        text = re.sub(reg, r'<a href="\2">\1</a>', text)
        reg = re.compile(r"~~(.+)~~")
        text = re.sub(reg, r"<s>\1</s>", text)
        reg = re.compile(r"__(.+)__")
        text = re.sub(reg, r"<u>\1</u>", text)
        reg = re.compile(r"\*\*(.+)\*\*")
        text = re.sub(reg, r"<b>\1</b>", text)
        reg = re.compile(r"\*(.+)\*")
        text = re.sub(reg, r"<i>\1</i>", text)
        return text

    def make_signature(self, cmd):
        if cmd.aliases:
            prelude = cmd.qualified_name.replace(cmd.name, "").strip()
            if prelude:
                prelude = f"{prelude} "
            actual_names = cmd.aliases + [cmd.name]
            aliases = f"{prelude}[{'|'.join(actual_names)}]"
        else:
            aliases = cmd.qualified_name
        return f"${aliases} {cmd.signature}"

    def read_csv(self, filename):
        with open(filename, 'r', encoding='utf-8') as file:
            reader = csv.DictReader(file)
            data = [row for row in reader]
        return data

    # Function to process CSV data and calculate percentages
    def process_data(self, csv_data):
        questions = defaultdict(lambda: defaultdict(int))
        total_responses = defaultdict(int)

        # Count total responses and answer choices for each question
        for row in csv_data:
            for key, value in row.items():
                if key != 'Timestamp':  # Skip timestamp column
                    questions[key][value] += 1
                    total_responses[key] += 1

        # Calculate percentages for each answer choice
        for question, choices in questions.items():
            total_responses_for_question = total_responses[question]
            for choice, count in choices.items():
                questions[question][choice] = (count / total_responses_for_question) * 100

        return questions

    # Command to display processed CSV data
    @commands.command(hidden=True)
    async def view_results(self, ctx):
        # Read the CSV file
        try:
            csv_data = self.read_csv('results.csv')

            # Process the data
            processed_data = self.process_data(csv_data)

            # Format the data for display
            formatted_data = ""
            for question, choices in processed_data.items():
                formatted_data += f"**{question}**:\n"
                for choice, percentage in choices.items():
                    formatted_data += f"{choice}: {percentage:.2f}%\n"
                formatted_data += "\n"
            chunks = [formatted_data[i:i + 2000] for i in range(0, len(formatted_data), 2000)]

            # Send each chunk as a separate message
            for chunk in chunks:
                await ctx.send(chunk)
        except Exception as e:
            await ctx.send(e)

    @is_gm()
    @commands.command(hidden=True)
    async def makehtml(self, ctx: Context) -> None:
        """Generates HTML for commands page."""
        with open("assets/html/commands.html") as f:
            base = f.read()
        with open("assets/html/cog.html") as f:
            cog = f.read()
        with open("assets/html/command.html") as f:
            command = f.read()

        html = ""

        for cog_name, cog_ in self.bot.cogs.items():
            if cog_name in ("GameMaster", "Owner", "Custom"):
                continue
            commands = {c for c in list(cog_.walk_commands()) if not c.hidden}
            if len(commands) > 0:
                html += cog.format(name=cog_name)
                for cmd in commands:
                    html += command.format(
                        name=cmd.qualified_name,
                        usage=self.make_signature(cmd)
                        .replace("<", "&lt;")
                        .replace(">", "&gt;"),
                        checks=f"<b>Checks: {checks}</b>"
                        if (
                            checks := ", ".join(
                                [
                                    (
                                        "cooldown"
                                        if "cooldown" in name
                                        else (
                                            "has_character"
                                            if name == "has_char"
                                            else name
                                        )
                                    )
                                    for c in cmd.checks
                                    if (
                                           name := re.search(
                                               r"<function ([^.]+)\.", repr(c)
                                           ).group(1)
                                       )
                                       != "update_pet"
                                ]
                            )
                        )
                        else "",
                        description=self.replace_md(
                            (cmd.help or "No Description Set")
                            .format(prefix="$")
                            .replace("<", "&lt;")
                            .replace(">", "&gt;")
                        ).replace("\n", "<br>"),
                    )

        html = base.format(content=html)
        await ctx.send(
            file=discord.File(filename="commands.html", fp=io.StringIO(html))
        )

    # Replace 'Your Category Name' with the name of the category you want

    @is_gm()
    @commands.command(hidden=True)
    async def gmjail(self, ctx: Context, member: discord.Member):
        if not self.jail_guild_id or ctx.guild.id != self.jail_guild_id:
            return
        try:
            # Get the category by name
            target_category = discord.utils.get(ctx.guild.categories, name=CATEGORY_NAME)
            if not target_category:
                await ctx.send(f"Category '{CATEGORY_NAME}' not found!")
                return

            # Get the 'jail' channel
            jail_channel = discord.utils.get(ctx.guild.text_channels, name='⟢jail〡🚔')
            if not jail_channel:
                await ctx.send("Jail channel not found!")
                return

            # Loop through all text channels within the target category
            for channel in target_category.text_channels:
                try:
                    # Check if the channel is in the blacklist
                    if channel.name not in CHANNEL_BLACKLIST:
                        # Deny the member's permission to read messages in the channel
                        await channel.set_permissions(member, read_messages=False)
                except discord.Forbidden:
                    await ctx.send(f"Permission denied in channel: {channel.name}")

            # Allow the member to read messages in the jail channel
            await jail_channel.set_permissions(member, read_messages=True)

            await ctx.send(f"{member.mention} has been jailed!")

        except Exception as e:
            await ctx.send(f"An error occurred: {e}")

    @is_gm()
    @commands.command()
    async def gmunjail(self, ctx: Context, member: discord.Member):
        if not self.jail_guild_id or ctx.guild.id != self.jail_guild_id:
            return
        try:
            SPECIAL_USER_ID = self.gmunjail_special_user_id
            special_permissions = None

            # Check if the user has a special ID
            if SPECIAL_USER_ID and member.id == SPECIAL_USER_ID:
                special_permissions = discord.PermissionOverwrite(manage_channels=True, read_messages=True,
                                                                  send_messages=True, manage_roles=True)

            # Get the category by name
            target_category = discord.utils.get(ctx.guild.categories, name=CATEGORY_NAME)
            if not target_category:
                await ctx.send(f"Category '{CATEGORY_NAME}' not found!")
                return

            # Get the 'jail' channel
            jail_channel = discord.utils.get(ctx.guild.text_channels, name='⟢jail〡🚔')
            if not jail_channel:
                await ctx.send("Jail channel not found!")
                return

            # Loop through all text channels within the target category
            for channel in target_category.text_channels:
                # Check if the channel is in the blacklist
                if channel.name not in CHANNEL_BLACKLIST:
                    if special_permissions:
                        # Give the special permissions to the special user
                        await channel.set_permissions(member, overwrite=special_permissions)
                    else:
                        # Restore the member's permission to read messages in the channel
                        await channel.set_permissions(member, overwrite=None)

            if special_permissions:
                # Grant the special user the special permissions in the jail channel
                await jail_channel.set_permissions(member, overwrite=special_permissions)
            else:
                # Deny the member's permission to read messages in the jail channel
                await jail_channel.set_permissions(member, read_messages=False)

            await ctx.send(f"{member.mention} has been released from jail!")

        except Exception as e:
            await ctx.send(f"An error occurred: {e}")

    @is_gm()
    @commands.group(hidden=True, invoke_without_command=True)
    async def badges(self, ctx: Context, user: UserWithCharacter) -> None:
        badges = Badge.from_db(ctx.user_data["badges"])

        if badges:
            await ctx.send(badges.to_pretty())
        else:
            await ctx.send("User has no badges")

    @is_gm()
    @badges.command(hidden=True, name="add")
    async def badges_add(
            self, ctx: Context, user: UserWithCharacter, badge: BadgeConverter
    ) -> None:
        badges = Badge.from_db(ctx.user_data["badges"])
        badges |= badge

        await self.bot.pool.execute(
            'UPDATE profile SET "badges"=$1 WHERE "user"=$2;', badges.to_db(), user.id
        )

        await ctx.send("Done")

    @is_gm()
    @badges.command(hidden=True, name="rem", aliases=["remove", "delete", "del"])
    async def badges_rem(
            self, ctx: Context, user: UserWithCharacter, badge: BadgeConverter
    ) -> None:
        badges = Badge.from_db(ctx.user_data["badges"])
        badges ^= badge

        await self.bot.pool.execute(
            'UPDATE profile SET "badges"=$1 WHERE "user"=$2;', badges.to_db(), user.id
        )


    @commands.command(hidden=True, name="removegod")
    @commands.is_owner()  # Only bot owner can remove gods
    async def remove_god(self, ctx: Context, user: discord.Member):
        """Remove a user as a god."""
        try:
            async with self.bot.pool.acquire() as conn:
                result = await conn.execute(
                    "DELETE FROM gods WHERE user_id = $1",
                    user.id
                )
                
                if result == "DELETE 0":
                    await ctx.send(f"{user.mention} is not a god.")
                    return
                
                # Remove Discord role
                try:
                    god_role = ctx.guild.get_role(self.god_admin_role_id) if self.god_admin_role_id else None
                    if god_role and god_role in user.roles:
                        await user.remove_roles(god_role)
                except:
                    pass  # Silently pass if role removal fails
                
                # Success embed
                success_embed = discord.Embed(
                    title="✅ God Access Revoked",
                    description=f"**User:** {user.mention}\n**Status:** Access Revoked",
                    color=0xff6b6b,
                    timestamp=discord.utils.utcnow()
                )
                success_embed.set_footer(text=f"Revoked by {ctx.author}")
                
                await ctx.send(embed=success_embed)
                
        except Exception as e:
            error_embed = discord.Embed(
                title="❌ Error",
                description=f"Failed to remove god: {str(e)}",
                color=0xff0000
            )
            await ctx.send(embed=error_embed)


    @commands.command(hidden=True, name="addgod")
    @commands.is_owner()  # Only bot owner can add gods
    async def add_god(self, ctx: Context, user: discord.Member):
        """Add a user as a god."""
        try:
            async with self.bot.pool.acquire() as conn:
                # Check if user is already a god
                existing = await conn.fetchrow(
                    "SELECT 1 FROM gods WHERE user_id = $1", 
                    user.id
                )
                
                if existing:
                    await ctx.send(f"{user.mention} is already a god.")
                    return
                
                # Create invitation embed and view
                invite_embed = discord.Embed(
                    title="🌟 God Invitation",
                    description=f"{user.mention}, you have been invited to become a **God**.\n\n"
                               f"**Invited by:** {ctx.author.mention}\n"
                               f"**Role:** God\n\n"
                               f"Please click a button below to accept or decline this invitation.",
                    color=0xFFD700,  # Gold color
                    timestamp=discord.utils.utcnow()
                )
                invite_embed.set_footer(text="This invitation will expire in 2 minutes")
                
                # Create the view with buttons
                view = GodInviteView(user, timeout=120)
                
                # Send the invitation message
                message = await ctx.send(embed=invite_embed, view=view)
                
                # Wait for the user's response
                await view.wait()
                
                # Handle the response
                if view.value is None:
                    # Timeout occurred
                    timeout_embed = discord.Embed(
                        title="⏰ Invitation Expired",
                        description=f"The God invitation for {user.mention} has expired.",
                        color=0xff9900
                    )
                    await message.edit(embed=timeout_embed, view=None)
                    return
                
                elif view.value is False:
                    # User declined
                    declined_embed = discord.Embed(
                        title="❌ Invitation Declined",
                        description=f"{user.mention} has declined the God invitation.",
                        color=0xff0000
                    )
                    await message.edit(embed=declined_embed, view=None)
                    return
                
                # User accepted - proceed with adding god
                await conn.execute(
                    "INSERT INTO gods (user_id, granted_by) VALUES ($1, $2)",
                    user.id, ctx.author.id
                )
                
                # Assign Discord role
                try:
                    god_role = ctx.guild.get_role(self.god_admin_role_id) if self.god_admin_role_id else None
                    if god_role:
                        await user.add_roles(god_role)
                except:
                    pass  # Silently pass if role assignment fails
                
                # Success embed
                success_embed = discord.Embed(
                    title="✅ God Access Granted",
                    description=f"**User:** {user.mention}\n**Discord ID:** Saved (hashed)\n**Status:** Access Granted",
                    color=0xFFD700,  # Gold color
                    timestamp=discord.utils.utcnow()
                )
                success_embed.set_footer(text=f"Granted by {ctx.author}")
                
                await message.edit(embed=success_embed, view=None)
                
        except Exception as e:
            error_embed = discord.Embed(
                title="❌ Error",
                description=f"Failed to add god: {str(e)}",
                color=0xff0000
            )
            await ctx.send(embed=error_embed)


    @is_gm()
    @commands.command(hidden=True, brief=_("Replay a battle by ID"))
    @locale_doc
    async def gmreplaybattle(self, ctx, battle_id: str):
        _("""Replay a battle using its unique battle ID.
        
        This command allows GMs to view the complete replay of any battle that occurred,
        including all battle data, participants, logs, and any errors that may have occurred.
        
        **Usage**: `$gmreplaybattle <battle_id>`
        **Example**: `$gmreplaybattle a1b2c3d4-e5f6-7890-abcd-ef1234567890`
        """)
        
        # Import the Battle class to access the static method
        from cogs.battles.core.battle import Battle
        
        try:
            # Retrieve battle replay data
            replay_data = await Battle.get_battle_replay(self.bot, battle_id)
            
            if not replay_data:
                return await ctx.send(f"❌ **Battle Not Found**\n\nNo battle found with ID: `{battle_id}`\n\nMake sure the battle ID is correct and the battle was recorded after the replay system was implemented.")
            
            # Check if this battle has enhanced replay data
            battle_data = replay_data['battle_data']
            has_enhanced_replay = battle_data.get('has_enhanced_replay', False)
            turn_states = battle_data.get('turn_states', [])
            
            if has_enhanced_replay and turn_states:
                # Create live interactive replay
                embed = await self.create_live_battle_replay_embed(replay_data, 0, 1)  # Start with 1 action
                
                # Create the interactive controller
                view = BattleReplayController(ctx, replay_data, self)
                
                # Send the replay with controls
                message = await ctx.send(embed=embed, view=view)
                view.message = message  # Store message reference for updates
                
                await ctx.send(f"🎬 **Live Battle Replay Started!**\n\n"
                              f"Use the controls above to navigate through the battle.\n"
                              f"• **▶️ Play**: Auto-play the battle\n"
                              f"• **⏸️ Pause**: Stop auto-play\n"
                              f"• **⏪/⏩**: Step back/forward one turn\n"
                              f"• **⏮️/⏭️**: Jump to start/end\n"
                              f"• **Speed Selector**: Change playback speed\n\n"
                              f"*This replay will timeout after 5 minutes of inactivity.*")
            else:
                # Fall back to static replay for older battles
                embed = await self.create_battle_replay_embed(replay_data)
                await ctx.send(embed=embed)
                await ctx.send("ℹ️ *This battle was recorded before the live replay system was implemented. Showing static summary.*")
            
        except Exception as e:
            await ctx.send(f"❌ **Error Retrieving Battle Replay**\n\nAn error occurred while trying to retrieve the battle replay:\n```\n{str(e)}\n```")
    
    @commands.command(brief=_("Save a battle to your personal slots"))
    @locale_doc
    async def savebattle(self, ctx, name: str, slot_number: int, battle_id: str):
        _("""Save a battle to your personal battle slots.
        
        You can only save battles where you were a participant.
        Each player has 10 slots (1-10) to save their favorite battles.
        
        **Usage**: `$savebattle <name> <slot_number> <battle_id>`
        **Example**: `$savebattle "Epic Dragon Fight" 1 a1b2c3d4-e5f6-7890-abcd-ef1234567890`
        """)
        
        # Validate slot number
        if slot_number < 1 or slot_number > 10:
            return await ctx.send("❌ **Invalid Slot Number**\n\nSlot number must be between 1 and 10.")
        
        # Import the Battle class to access the static method
        from cogs.battles.core.battle import Battle
        
        try:
            # Retrieve battle replay data
            replay_data = await Battle.get_battle_replay(self.bot, battle_id)
            
            if not replay_data:
                return await ctx.send(f"❌ **Battle Not Found**\n\nNo battle found with ID: `{battle_id}`\n\nMake sure the battle ID is correct and the battle was recorded after the replay system was implemented.")
            
            # Check if user is a participant in this battle
            participants = replay_data.get('participants', [])
            if ctx.author.id not in participants:
                return await ctx.send("❌ **Not a Participant**\n\nYou can only save battles where you were a participant.\n\nIf you believe this is an error, contact a Game Master.")
            
            # Initialize saved battles table if it doesn't exist
            async with self.bot.pool.acquire() as conn:
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS saved_battles (
                        user_id BIGINT,
                        slot_number INTEGER,
                        battle_id TEXT,
                        battle_name TEXT,
                        saved_at TIMESTAMP DEFAULT NOW(),
                        PRIMARY KEY (user_id, slot_number)
                    )
                """)
                
                # Check if slot is already occupied
                existing = await conn.fetchrow(
                    "SELECT battle_name FROM saved_battles WHERE user_id = $1 AND slot_number = $2",
                    ctx.author.id, slot_number
                )
                
                if existing:
                    # Ask for confirmation to overwrite
                    confirm_msg = await ctx.send(
                        f"⚠️ **Slot Already Occupied**\n\n"
                        f"Slot {slot_number} already contains: **{existing['battle_name']}**\n\n"
                        f"Do you want to overwrite it with **{name}**?\n\n"
                        f"React with ✅ to confirm or ❌ to cancel."
                    )
                    
                    # Add reaction options
                    await confirm_msg.add_reaction("✅")
                    await confirm_msg.add_reaction("❌")
                    
                    def check(reaction, user):
                        return user == ctx.author and reaction.message.id == confirm_msg.id and str(reaction.emoji) in ["✅", "❌"]
                    
                    try:
                        reaction, user = await self.bot.wait_for('reaction_add', timeout=30.0, check=check)
                        
                        if str(reaction.emoji) == "❌":
                            await confirm_msg.delete()
                            return await ctx.send("❌ **Save Cancelled**\n\nBattle was not saved.")
                        
                    except asyncio.TimeoutError:
                        await confirm_msg.delete()
                        return await ctx.send("⏰ **Timeout**\n\nNo response received. Battle was not saved.")
                
                # Save the battle
                await conn.execute(
                    "INSERT INTO saved_battles (user_id, slot_number, battle_id, battle_name) VALUES ($1, $2, $3, $4) "
                    "ON CONFLICT (user_id, slot_number) DO UPDATE SET battle_id = $3, battle_name = $4, saved_at = NOW()",
                    ctx.author.id, slot_number, battle_id, name
                )
                
                await ctx.send(f"✅ **Battle Saved Successfully!**\n\n"
                              f"**Name**: {name}\n"
                              f"**Slot**: {slot_number}\n"
                              f"**Battle ID**: `{battle_id}`\n\n"
                              f"Use `$replaybattle {slot_number}` to replay this battle!")
                
        except Exception as e:
            await ctx.send(f"❌ **Error Saving Battle**\n\nAn error occurred while trying to save the battle:\n```\n{str(e)}\n```")
    
    @commands.command(brief=_("Replay a saved battle from your slots"))
    @locale_doc
    async def replaybattle(self, ctx, slot_number: int):
        _("""Replay a battle from your saved battle slots.
        
        Each player has 10 slots (1-10) where they can save their favorite battles.
        Use `$savebattle` to save battles first.
        
        **Usage**: `$replaybattle <slot_number>`
        **Example**: `$replaybattle 1`
        """)
        
        # Validate slot number
        if slot_number < 1 or slot_number > 10:
            return await ctx.send("❌ **Invalid Slot Number**\n\nSlot number must be between 1 and 10.")
        
        try:
            # Get saved battle data
            async with self.bot.pool.acquire() as conn:
                saved_battle = await conn.fetchrow(
                    "SELECT battle_id, battle_name FROM saved_battles WHERE user_id = $1 AND slot_number = $2",
                    ctx.author.id, slot_number
                )
                
                if not saved_battle:
                    return await ctx.send(f"❌ **No Battle Found**\n\nNo battle saved in slot {slot_number}.\n\nUse `$savebattle` to save a battle first.")
                
                battle_id = saved_battle['battle_id']
                battle_name = saved_battle['battle_name']
            
            # Import the Battle class to access the static method
            from cogs.battles.core.battle import Battle
            
            # Retrieve battle replay data
            replay_data = await Battle.get_battle_replay(self.bot, battle_id)
            
            if not replay_data:
                return await ctx.send(f"❌ **Battle Not Found**\n\nThe saved battle with ID `{battle_id}` no longer exists in the database.\n\nThis might happen if the battle data was cleaned up.")
            
            # Check if this battle has enhanced replay data
            battle_data = replay_data['battle_data']
            has_enhanced_replay = battle_data.get('has_enhanced_replay', False)
            turn_states = battle_data.get('turn_states', [])
            
            if has_enhanced_replay and turn_states:
                # Create live interactive replay
                embed = await self.create_live_battle_replay_embed(replay_data, 0, 1)  # Start with 1 action
                
                # Create the interactive controller
                view = BattleReplayController(ctx, replay_data, self)
                
                # Send the replay with controls
                message = await ctx.send(embed=embed, view=view)
                view.message = message  # Store message reference for updates
                
                await ctx.send(f"🎬 **Saved Battle Replay Started!**\n\n"
                              f"**Battle**: {battle_name}\n"
                              f"**Slot**: {slot_number}\n\n"
                              f"Use the controls above to navigate through the battle.\n"
                              f"• **▶️ Play**: Auto-play the battle\n"
                              f"• **⏸️ Pause**: Stop auto-play\n"
                              f"• **⏪/⏩**: Step back/forward one turn\n"
                              f"• **⏮️/⏭️**: Jump to start/end\n"
                              f"• **Speed Selector**: Change playback speed\n\n"
                              f"*This replay will timeout after 5 minutes of inactivity.*")
            else:
                # Fall back to static replay for older battles
                embed = await self.create_battle_replay_embed(replay_data)
                await ctx.send(embed=embed)
                await ctx.send(f"ℹ️ *This battle was recorded before the live replay system was implemented. Showing static summary.*")
            
        except Exception as e:
            await ctx.send(f"❌ **Error Retrieving Saved Battle**\n\nAn error occurred while trying to retrieve the saved battle:\n```\n{str(e)}\n```")
    
    @commands.command(brief=_("List your saved battles"))
    @locale_doc
    async def mysavedbattles(self, ctx):
        _("""List all your saved battles.
        
        Shows all battles you have saved in your 10 slots.
        
        **Usage**: `$mysavedbattles`
        """)
        
        try:
            # Get saved battles data
            async with self.bot.pool.acquire() as conn:
                saved_battles = await conn.fetch(
                    "SELECT slot_number, battle_name, saved_at FROM saved_battles WHERE user_id = $1 ORDER BY slot_number",
                    ctx.author.id
                )
                
                if not saved_battles:
                    return await ctx.send("📭 **No Saved Battles**\n\nYou haven't saved any battles yet.\n\nUse `$savebattle <name> <slot> <battle_id>` to save a battle!")
                
                # Create embed with saved battles
                embed = discord.Embed(
                    title="🎬 Your Saved Battles",
                    description=f"Showing {len(saved_battles)} saved battles for {ctx.author.display_name}",
                    color=discord.Color.blue()
                )
                
                for battle in saved_battles:
                    slot_num = battle['slot_number']
                    battle_name = battle['battle_name']
                    saved_at = battle['saved_at'].strftime("%Y-%m-%d %H:%M")
                    
                    embed.add_field(
                        name=f"Slot {slot_num}: {battle_name}",
                        value=f"Saved: {saved_at}\nUse: `$replaybattle {slot_num}`",
                        inline=False
                    )
                
                embed.set_footer(text=f"Total saved battles: {len(saved_battles)}/10")
                
                await ctx.send(embed=embed)
                
        except Exception as e:
            await ctx.send(f"❌ **Error Listing Saved Battles**\n\nAn error occurred while trying to list your saved battles:\n```\n{str(e)}\n```")
    
    @commands.command(brief=_("Delete a saved battle"))
    @locale_doc
    async def deletesavedbattle(self, ctx, slot_number: int):
        _("""Delete a saved battle from your slots.
        
        This will permanently remove the battle from the specified slot.
        
        **Usage**: `$deletesavedbattle <slot_number>`
        **Example**: `$deletesavedbattle 1`
        """)
        
        # Validate slot number
        if slot_number < 1 or slot_number > 10:
            return await ctx.send("❌ **Invalid Slot Number**\n\nSlot number must be between 1 and 10.")
        
        try:
            # Get saved battle data
            async with self.bot.pool.acquire() as conn:
                saved_battle = await conn.fetchrow(
                    "SELECT battle_name FROM saved_battles WHERE user_id = $1 AND slot_number = $2",
                    ctx.author.id, slot_number
                )
                
                if not saved_battle:
                    return await ctx.send(f"❌ **No Battle Found**\n\nNo battle saved in slot {slot_number}.")
                
                battle_name = saved_battle['battle_name']
                
                # Ask for confirmation
                confirm_msg = await ctx.send(
                    f"⚠️ **Confirm Deletion**\n\n"
                    f"Are you sure you want to delete **{battle_name}** from slot {slot_number}?\n\n"
                    f"This action cannot be undone.\n\n"
                    f"React with ✅ to confirm or ❌ to cancel."
                )
                
                # Add reaction options
                await confirm_msg.add_reaction("✅")
                await confirm_msg.add_reaction("❌")
                
                def check(reaction, user):
                    return user == ctx.author and reaction.message.id == confirm_msg.id and str(reaction.emoji) in ["✅", "❌"]
                
                try:
                    reaction, user = await self.bot.wait_for('reaction_add', timeout=30.0, check=check)
                    
                    if str(reaction.emoji) == "❌":
                        await confirm_msg.delete()
                        return await ctx.send("❌ **Deletion Cancelled**\n\nBattle was not deleted.")
                    
                except asyncio.TimeoutError:
                    await confirm_msg.delete()
                    return await ctx.send("⏰ **Timeout**\n\nNo response received. Battle was not deleted.")
                
                # Delete the battle
                await conn.execute(
                    "DELETE FROM saved_battles WHERE user_id = $1 AND slot_number = $2",
                    ctx.author.id, slot_number
                )
                
                await ctx.send(f"✅ **Battle Deleted Successfully!**\n\n"
                              f"**{battle_name}** has been removed from slot {slot_number}.")
                
        except Exception as e:
            await ctx.send(f"❌ **Error Deleting Saved Battle**\n\nAn error occurred while trying to delete the saved battle:\n```\n{str(e)}\n```")
    

    
    async def create_live_battle_replay_embed(self, replay_data, current_turn=0, action_count=1):
        """Create an embed for live battle replay at a specific turn"""
        
        # Check if this is an enhanced replay with turn states
        battle_data = replay_data['battle_data']
        has_enhanced_replay = battle_data.get('has_enhanced_replay', False)
        
        if not has_enhanced_replay or not battle_data.get('turn_states'):
            # Fall back to static replay if no enhanced data
            return await self.create_battle_replay_embed(replay_data)
        
        turn_states = battle_data['turn_states']
        
        # Use initial state if current_turn is 0, otherwise use the specified turn
        if current_turn == 0 and battle_data.get('initial_state'):
            current_state = battle_data['initial_state']
        elif current_turn < len(turn_states):
            current_state = turn_states[current_turn]
        else:
            current_state = turn_states[-1]  # Use last state if beyond range
        
        # Create embed based on current state
        battle_info = current_state.get('battle_info', {})
        battle_type = battle_info.get('battle_type', replay_data['battle_type'])
        
        # Get participants for title
        participants = replay_data.get('participants', [])
        participant_names = []
        for user_id in participants[:2]:  # Show first 2 participants
            try:
                user = self.bot.get_user(user_id) or await self.bot.fetch_user(user_id)
                participant_names.append(user.display_name)
            except:
                participant_names.append("Unknown")
        
        # Create title similar to battle format
        if len(participant_names) >= 2:
            battle_title = f"{battle_type.replace('Battle', '').strip()}: {participant_names[0]} vs {participant_names[1]}"
        elif len(participant_names) == 1:
            battle_title = f"{battle_type.replace('Battle', '').strip()}: {participant_names[0]}"
        else:
            battle_title = f"{battle_type} Replay"
        
        embed = discord.Embed(
            title=f"🎬 {battle_title}",
            color=self.bot.config.game.primary_colour,
            timestamp=replay_data['created_at']
        )
        
        # Add combatant information from current state
        teams = current_state.get('teams', [])
        
        for team_idx, team in enumerate(teams):
            # Use same team naming as actual battles
            team_name = f"**[TEAM {chr(65 + team_idx)}]**"  # A, B, C, etc.
            team_info = []
            
            for combatant in team.get('combatants', []):
                # Get proper name - use pet_name for pets, display_name for players
                is_pet = combatant.get('is_pet', False)
                if is_pet and combatant.get('pet_name'):
                    name = combatant.get('pet_name')
                    name_suffix = " 🐾"  # Pet indicator
                else:
                    name = combatant.get('display_name', combatant.get('name', 'Unknown'))
                    name_suffix = ""
                
                current_hp = combatant.get('current_hp', 0)
                max_hp = combatant.get('max_hp', 1)
                hp_percentage = combatant.get('hp_percentage', 0)
                
                # Create HP bar using the same style as battles
                hp_bar_length = 20
                filled_length = int(hp_bar_length * max(0, min(1, hp_percentage)))
                empty_length = hp_bar_length - filled_length
                hp_bar = "█" * filled_length + "░" * empty_length
                
                # Use stored element emoji from battle data
                element_emoji = combatant.get('element_emoji', "❓")
                
                # Format like actual battle display
                combatant_text = f"{name}{name_suffix} {element_emoji}\nHP: {current_hp:.1f}/{max_hp:.1f}\n{hp_bar}"
                
                # Add damage reflection if present
                damage_reflection = combatant.get('damage_reflection', 0)
                if damage_reflection > 0:
                    reflection_percent = float(damage_reflection) * 100
                    combatant_text += f"\nDamage Reflection: {reflection_percent:.1f}%"
                
                team_info.append(combatant_text)
            
            if team_info:
                embed.add_field(
                    name=team_name,
                    value="\n\n".join(team_info),
                    inline=False
                )
        
        # Add battle log section with sliding window of actions
        actions_to_show = []
        
        # Calculate which actions to show (sliding window)
        if action_count == 1:
            # Show current action only
            action_message = current_state.get('action_message', 'Battle starting...')
            action_number = current_state.get('action_number', 0)
            actions_to_show.append(f"**Action #{action_number}**\n{action_message}")
        else:
            # Show multiple actions in sliding window
            # Get the current turn's action first
            current_action_number = current_state.get('action_number', 0)
            
            # Calculate start position for sliding window
            start_turn = max(0, current_turn - action_count + 1)
            end_turn = min(len(turn_states), current_turn + 1)
            
            # Collect actions for the window
            for turn_idx in range(start_turn, end_turn):
                if turn_idx < len(turn_states):
                    turn_state = turn_states[turn_idx]
                    action_msg = turn_state.get('action_message', 'Battle action...')
                    action_num = turn_state.get('action_number', turn_idx)
                    actions_to_show.append(f"**Action #{action_num}**\n{action_msg}")
        
        # Join actions with separator
        battle_log_value = "\n\n".join(actions_to_show) if actions_to_show else "Battle starting..."
        
        embed.add_field(
            name="Battle Log",
            value=battle_log_value,
            inline=False
        )
        
        # Add replay controls info
        progress_percentage = (current_turn + 1) / len(turn_states)
        progress_bar = self.create_progress_bar(progress_percentage)
        
        embed.add_field(
            name="🎬 Replay Controls",
            value=f"{progress_bar} {progress_percentage:.1%}\nTurn {current_turn + 1}/{len(turn_states)} • Showing {action_count} action{'s' if action_count > 1 else ''}",
            inline=False
        )
        
        # Add footer with battle ID (like actual battles)
        embed.set_footer(text=f"Battle ID: {replay_data['battle_id']}")
        
        return embed
    
    def create_replay_hp_bar(self, hp_percentage, length=15):
        """Create a HP bar for replay display"""
        filled_length = int(length * max(0, min(1, hp_percentage)))
        empty_length = length - filled_length
        
        if hp_percentage > 0.6:
            bar_char = "🟢"
        elif hp_percentage > 0.3:
            bar_char = "🟡"
        else:
            bar_char = "🔴"
        
        return bar_char * filled_length + "⚫" * empty_length
    
    def create_progress_bar(self, percentage, length=20):
        """Create a progress bar for replay"""
        filled_length = int(length * max(0, min(1, percentage)))
        empty_length = length - filled_length
        return "█" * filled_length + "░" * empty_length

    async def create_battle_replay_embed(self, replay_data):
        """Create an embed displaying battle replay information"""
        
        embed = discord.Embed(
            title=f"🔍 Battle Replay: {replay_data['battle_type']}",
            description=f"**Battle ID**: `{replay_data['battle_id']}`",
            color=discord.Color.blue(),
            timestamp=replay_data['created_at']
        )
        
        # Add basic battle information
        participants_text = ""
        if replay_data['participants']:
            try:
                # Get user objects for participant names
                participant_names = []
                for user_id in replay_data['participants']:
                    try:
                        user = self.bot.get_user(user_id) or await self.bot.fetch_user(user_id)
                        participant_names.append(f"{user.display_name} ({user_id})")
                    except:
                        participant_names.append(f"Unknown User ({user_id})")
                participants_text = "\n".join(participant_names)
            except:
                participants_text = f"{len(replay_data['participants'])} participants"
        else:
            participants_text = "No participants recorded"
        
        embed.add_field(
            name="👥 **Participants**",
            value=participants_text,
            inline=False
        )
        
        # Add battle configuration
        config = replay_data['battle_data'].get('config', {})
        config_text = []
        important_settings = ['allow_pets', 'status_effects', 'simple', 'cheat_death', 'element_effects']
        for setting in important_settings:
            if setting in config:
                status = "✅" if config[setting] else "❌"
                config_text.append(f"{status} {setting.replace('_', ' ').title()}")
        
        if config_text:
            embed.add_field(
                name="⚙️ **Battle Settings**",
                value="\n".join(config_text),
                inline=True
            )
        
        # Add battle statistics
        stats_text = []
        battle_data = replay_data['battle_data']
        
        if battle_data.get('start_time'):
            stats_text.append(f"📅 **Started**: {battle_data['start_time']}")
        
        if battle_data.get('finished'):
            stats_text.append(f"🏁 **Status**: Finished")
        else:
            stats_text.append(f"⏸️ **Status**: In Progress/Interrupted")
        
        if battle_data.get('winner'):
            stats_text.append(f"🏆 **Winner**: {battle_data['winner']}")
        
        stats_text.append(f"📊 **Total Actions**: {battle_data.get('action_number', 0)}")
        
        embed.add_field(
            name="📈 **Battle Statistics**",
            value="\n".join(stats_text),
            inline=True
        )
        
        # Add battle log (truncated if too long)
        battle_log = replay_data['battle_log']
        if battle_log:
            log_text = []
            for action_num, message in battle_log:
                log_text.append(f"**Action {action_num}**: {message}")
            
            log_content = "\n\n".join(log_text)
            
            # Truncate if too long for Discord
            if len(log_content) > 1000:
                log_content = log_content[:900] + f"\n\n... *({len(battle_log) - len(log_text[:3])} more actions)*"
            
            embed.add_field(
                name="📝 **Battle Log**",
                value=log_content or "No battle log recorded",
                inline=False
            )
        else:
            embed.add_field(
                name="📝 **Battle Log**",
                value="No battle log recorded",
                inline=False
            )
        
        # Add footer with additional info
        embed.set_footer(text=f"Recorded at {replay_data['created_at'].strftime('%Y-%m-%d %H:%M:%S UTC')} • Use this replay for debugging")
        
        return embed




    def _get_element_choices(self):
        elements = [e for e in ElementExtension.element_to_emoji.keys() if e != "Unknown"]
        return sorted(set(elements))

    async def _gm_prompt(self, ctx, prompt, timeout=180, allow_blank=False):
        await ctx.send(prompt)

        def check(msg):
            return msg.author == ctx.author and msg.channel == ctx.channel

        try:
            msg = await self.bot.wait_for("message", timeout=timeout, check=check)
        except asyncio.TimeoutError:
            await ctx.send("⏱️ Timed out waiting for a response.")
            return None

        content = msg.content.strip()
        if not content and not allow_blank:
            await ctx.send("❌ Empty response. Cancelled.")
            return None
        if content.lower() in ("cancel", "stop", "exit"):
            await ctx.send("✅ Cancelled.")
            return None
        return content

    async def _gm_confirm(self, ctx, prompt):
        response = await self._gm_prompt(ctx, prompt)
        if response is None:
            return False
        if response.strip().lower() in ("yes", "y"):
            return True
        await ctx.send("❌ Cancelled.")
        return False

    async def _gm_confirm_twice(self, ctx, prompt_one, prompt_two):
        if not await self._gm_confirm(ctx, prompt_one):
            return False
        return await self._gm_confirm(ctx, prompt_two)

    def _format_percent(self, value):
        if value is None:
            return "-"
        try:
            return f"{float(value) * 100:.2f}%"
        except (TypeError, ValueError):
            return str(value)

    def _parse_percent(self, raw):
        if raw is None:
            return None
        text = str(raw).strip()
        if not text:
            return None
        if text.endswith("%"):
            text = text[:-1].strip()
        try:
            value = float(text)
        except ValueError:
            return None
        if value < 0 or value > 100:
            return None
        return value / 100.0

    async def _send_menu_embed(self, ctx, title, lines, footer=None):
        embed = discord.Embed(title=title, description="\n".join(lines), color=discord.Color.blurple())
        if footer:
            embed.set_footer(text=footer)
        await ctx.send(embed=embed)

    async def _fetch_dragon_abilities(self, ability_type: str):
        async with self.bot.pool.acquire() as conn:
            return await conn.fetch(
                "SELECT name, description, dmg, effect, chance FROM ice_dragon_abilities WHERE ability_type = $1 ORDER BY name ASC",
                ability_type,
            )

    async def _fetch_dragon_stages(self):
        async with self.bot.pool.acquire() as conn:
            return await conn.fetch(
                "SELECT id, name, min_level, max_level, base_multiplier, enabled, element, move_names, passive_names "
                "FROM ice_dragon_stages ORDER BY min_level ASC, max_level ASC, id ASC"
            )

    async def _fetch_dragon_drops(self):
        async with self.bot.pool.acquire() as conn:
            return await conn.fetch(
                "SELECT id, name, item_type, min_stat, max_stat, base_chance, max_chance, is_global, dragon_stage_id, "
                "element, min_level, max_level "
                "FROM ice_dragon_drops ORDER BY id ASC"
            )

    async def _fetch_dragon_presets(self):
        async with self.bot.pool.acquire() as conn:
            return await conn.fetch(
                "SELECT id, name, created_at FROM ice_dragon_presets ORDER BY id ASC"
            )

    async def _fetch_preset_stage_ids(self, preset_id: int):
        async with self.bot.pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT stage_id FROM ice_dragon_preset_stages WHERE preset_id = $1 ORDER BY stage_id ASC",
                preset_id,
            )
        return [row["stage_id"] for row in rows]

    async def _choose_abilities(self, ctx, ability_type: str, max_count: int | None = None):
        abilities = await self._fetch_dragon_abilities(ability_type)
        if not abilities:
            return []

        lines = []
        for idx, row in enumerate(abilities, start=1):
            desc = (row["description"] or "").strip()
            if not desc:
                desc = "No description."
            effect = row.get("effect") or "Unknown"
            dmg = row.get("dmg")
            try:
                dmg_num = float(dmg)
                dmg_display = f"{int(dmg_num)}"
            except (TypeError, ValueError):
                dmg_display = str(dmg or "0")
            chance_val = row.get("chance")
            chance_display = "0%"
            if chance_val is not None:
                try:
                    chance_num = float(chance_val)
                    chance_display = f"{chance_num * 100:.0f}%" if 0 <= chance_num <= 1 else f"{chance_num:.0f}%"
                except (TypeError, ValueError):
                    chance_display = str(chance_val)
            line = (
                f"{idx}) {row['name']} — Effect: {effect}. Damage: {dmg_display}. "
                f"Chance: {chance_display}. {desc}"
            )
            if len(line) > 200:
                line = line[:197] + "..."
            lines.append(line)
            lines.append("")

        await self._send_menu_embed(
            ctx,
            title=f"Select {ability_type.title()}s",
            lines=lines,
            footer="Reply with numbers (comma-separated). Example: 1,3"
        )
        raw = await self._gm_prompt(ctx, f"Select {ability_type}s by number:", allow_blank=True)
        if raw is None:
            return None
        if raw.strip().lower() in ("", "none", "0"):
            return []

        selected = []
        try:
            for part in raw.split(","):
                idx = int(part.strip())
                if 1 <= idx <= len(abilities):
                    selected.append(abilities[idx - 1]["name"])
        except ValueError:
            await ctx.send("❌ Invalid selection. Use numbers only.")
            return None

        if max_count is not None and len(selected) > max_count:
            await ctx.send(f"❌ Too many selected (max {max_count}).")
            return None

        return list(dict.fromkeys(selected))

    async def _choose_dragon_stages(self, ctx, allow_enabled=True):
        stages = await self._fetch_dragon_stages()
        if not stages:
            await ctx.send("❌ No dragon stages available.")
            return None

        lines = []
        for idx, row in enumerate(stages, start=1):
            status = "✅" if row["enabled"] else "❌"
            lines.append(f"{idx}) {row['name']} {status} (Lv {row['min_level']}-{row['max_level']})")

        footer = "Reply with numbers (comma-separated)."
        if allow_enabled:
            footer += " Or type 'enabled' to use currently enabled stages."
        await self._send_menu_embed(ctx, "Select Dragon Stages", lines, footer=footer)
        raw = await self._gm_prompt(ctx, "Select stages by number:", allow_blank=True)
        if raw is None:
            return None
        if raw.strip().lower() in ("", "none", "0"):
            return []
        if allow_enabled and raw.strip().lower() == "enabled":
            return [row["id"] for row in stages if row["enabled"]]

        selected = []
        try:
            for part in raw.split(","):
                idx = int(part.strip())
                if 1 <= idx <= len(stages):
                    selected.append(stages[idx - 1]["id"])
        except ValueError:
            await ctx.send("❌ Invalid selection. Use numbers only.")
            return None

        return list(dict.fromkeys(selected))

    @is_gm()
    @commands.command(name="gmicedragonsettings", aliases=["gmicedragon", "gmids"])
    async def gm_ice_dragon_settings(self, ctx):
        """GM UI to manage Ice Dragon stages and drops."""

        class IceDragonSettingsView(View):
            def __init__(self, cog, ctx):
                super().__init__(timeout=300)
                self.cog = cog
                self.ctx = ctx

            async def _guard(self, interaction: discord.Interaction):
                if interaction.user.id != self.ctx.author.id:
                    await interaction.response.send_message("❌ This menu is not for you.", ephemeral=True)
                    return False
                return True

            @discord.ui.button(label="Create Dragon", style=discord.ButtonStyle.green)
            async def create_dragon(self, interaction: discord.Interaction, button: discord.ui.Button):
                if not await self._guard(interaction):
                    return
                await interaction.response.send_message("Starting dragon creation...", ephemeral=True)
                await self.cog._gm_create_dragon(self.ctx)

            @discord.ui.button(label="List Dragons", style=discord.ButtonStyle.blurple)
            async def list_dragons(self, interaction: discord.Interaction, button: discord.ui.Button):
                if not await self._guard(interaction):
                    return
                await interaction.response.send_message("Listing dragons...", ephemeral=True)
                await self.cog._gm_list_dragons(self.ctx)

            @discord.ui.button(label="Edit Current List", style=discord.ButtonStyle.gray)
            async def edit_dragons(self, interaction: discord.Interaction, button: discord.ui.Button):
                if not await self._guard(interaction):
                    return
                await interaction.response.send_message("Editing dragon list...", ephemeral=True)
                await self.cog._gm_edit_dragons(self.ctx)

            @discord.ui.button(label="Create Drops", style=discord.ButtonStyle.green)
            async def create_drops(self, interaction: discord.Interaction, button: discord.ui.Button):
                if not await self._guard(interaction):
                    return
                await interaction.response.send_message("Starting drop creation...", ephemeral=True)
                await self.cog._gm_create_drop(self.ctx)

            @discord.ui.button(label="Edit Drops", style=discord.ButtonStyle.gray)
            async def edit_drops(self, interaction: discord.Interaction, button: discord.ui.Button):
                if not await self._guard(interaction):
                    return
                await interaction.response.send_message("Editing drops...", ephemeral=True)
                await self.cog._gm_edit_drops(self.ctx)

            @discord.ui.button(label="Reset Dragons", style=discord.ButtonStyle.red)
            async def reset_dragons(self, interaction: discord.Interaction, button: discord.ui.Button):
                if not await self._guard(interaction):
                    return
                await interaction.response.send_message("Resetting dragon stages...", ephemeral=True)
                await self.cog._gm_reset_dragons(self.ctx)

            @discord.ui.button(label="Reset Drops", style=discord.ButtonStyle.red)
            async def reset_drops(self, interaction: discord.Interaction, button: discord.ui.Button):
                if not await self._guard(interaction):
                    return
                await interaction.response.send_message("Resetting dragon drops...", ephemeral=True)
                await self.cog._gm_reset_drops(self.ctx)

            @discord.ui.button(label="List Presets", style=discord.ButtonStyle.blurple)
            async def list_presets(self, interaction: discord.Interaction, button: discord.ui.Button):
                if not await self._guard(interaction):
                    return
                await interaction.response.send_message("Listing presets...", ephemeral=True)
                await self.cog._gm_list_presets(self.ctx)

            @discord.ui.button(label="Create Preset", style=discord.ButtonStyle.green)
            async def create_preset(self, interaction: discord.Interaction, button: discord.ui.Button):
                if not await self._guard(interaction):
                    return
                await interaction.response.send_message("Creating preset...", ephemeral=True)
                await self.cog._gm_create_preset(self.ctx)

            @discord.ui.button(label="Apply Preset", style=discord.ButtonStyle.gray)
            async def apply_preset(self, interaction: discord.Interaction, button: discord.ui.Button):
                if not await self._guard(interaction):
                    return
                await interaction.response.send_message("Applying preset...", ephemeral=True)
                await self.cog._gm_apply_preset(self.ctx)

            @discord.ui.button(label="Delete Preset", style=discord.ButtonStyle.red)
            async def delete_preset(self, interaction: discord.Interaction, button: discord.ui.Button):
                if not await self._guard(interaction):
                    return
                await interaction.response.send_message("Deleting preset...", ephemeral=True)
                await self.cog._gm_delete_preset(self.ctx)

        embed = discord.Embed(
            title="GM Ice Dragon Settings",
            description="Manage Ice Dragon stages, abilities, and weapon drops.",
            color=discord.Color.blue(),
        )
        await ctx.send(embed=embed, view=IceDragonSettingsView(self, ctx))

    async def _gm_list_dragons(self, ctx):
        rows = await self._fetch_dragon_stages()
        if not rows:
            return await ctx.send("No dragon stages found.")
        embed = discord.Embed(
            title="Ice Dragon Stages",
            description="Enabled stages are eligible to spawn for matching levels.",
            color=discord.Color.blue(),
        )
        for row in rows:
            moves = ", ".join(row["move_names"] or [])
            passives = ", ".join(row["passive_names"] or [])
            status = "✅ Enabled" if row["enabled"] else "❌ Disabled"
            value = (
                f"{status}\n"
                f"Level Range: **{row['min_level']}–{row['max_level']}**\n"
                f"Multiplier: **x{row['base_multiplier']}**\n"
                f"Element: **{row['element']}**\n"
                f"Moves: {moves or 'None'}\n"
                f"Passives: {passives or 'None'}"
            )
            embed.add_field(name=row["name"], value=value, inline=False)
        await ctx.send(embed=embed)

    async def _gm_reset_dragons(self, ctx):
        confirmed = await self._gm_confirm_twice(
            ctx,
            "⚠️ This will delete ALL ice dragon stages and abilities and restore defaults. Type YES to continue.",
            "⚠️ Final confirmation. Type YES to reset dragon stages and abilities to defaults."
        )
        if not confirmed:
            return

        battles_cog = self.bot.get_cog("Battles")
        if not battles_cog:
            return await ctx.send("❌ Battles cog not found.")

        async with self.bot.pool.acquire() as conn:
            await conn.execute("DELETE FROM ice_dragon_stages")
            await conn.execute("DELETE FROM ice_dragon_abilities")

        await battles_cog.initialize_tables()
        await ctx.send("✅ Dragon stages and abilities reset to defaults.")

    async def _gm_reset_drops(self, ctx):
        confirmed = await self._gm_confirm_twice(
            ctx,
            "⚠️ This will delete ALL ice dragon drops and restore defaults. Type YES to continue.",
            "⚠️ Final confirmation. Type YES to reset dragon drops to defaults."
        )
        if not confirmed:
            return

        battles_cog = self.bot.get_cog("Battles")
        if not battles_cog:
            return await ctx.send("❌ Battles cog not found.")

        async with self.bot.pool.acquire() as conn:
            await conn.execute("DELETE FROM ice_dragon_drops")

        await battles_cog.initialize_tables()
        await ctx.send("✅ Dragon drops reset to defaults.")

    async def _gm_list_presets(self, ctx):
        presets = await self._fetch_dragon_presets()
        if not presets:
            return await ctx.send("No presets found.")

        embed = discord.Embed(
            title="Ice Dragon Presets",
            description="Use preset ID or name to apply.",
            color=discord.Color.blue(),
        )
        for preset in presets:
            stage_ids = await self._fetch_preset_stage_ids(preset["id"])
            embed.add_field(
                name=f"{preset['name']} (ID {preset['id']})",
                value=f"Stages: {len(stage_ids)}",
                inline=False,
            )
        await ctx.send(embed=embed)

    async def _gm_create_preset(self, ctx):
        name = await self._gm_prompt(ctx, "Preset name?")
        if not name:
            return

        stages = await self._choose_dragon_stages(ctx, allow_enabled=True)
        if stages is None:
            return
        if not stages:
            return await ctx.send("❌ Preset must include at least one stage.")

        async with self.bot.pool.acquire() as conn:
            exists = await conn.fetchval(
                "SELECT 1 FROM ice_dragon_presets WHERE LOWER(name) = LOWER($1)",
                name,
            )
            if exists:
                return await ctx.send("❌ A preset with that name already exists.")

            preset_id = await conn.fetchval(
                "INSERT INTO ice_dragon_presets (name) VALUES ($1) RETURNING id",
                name,
            )
            await conn.executemany(
                "INSERT INTO ice_dragon_preset_stages (preset_id, stage_id) VALUES ($1, $2) "
                "ON CONFLICT (preset_id, stage_id) DO NOTHING",
                [(preset_id, stage_id) for stage_id in stages],
            )

        await ctx.send(f"✅ Preset **{name}** created with {len(stages)} stages.")

    async def _gm_apply_preset(self, ctx):
        presets = await self._fetch_dragon_presets()
        if not presets:
            return await ctx.send("No presets found.")

        lines = [f"{p['id']}) {p['name']}" for p in presets]
        await self._send_menu_embed(ctx, "Available Presets", lines)
        raw = await self._gm_prompt(ctx, "Enter preset ID or name to apply:")
        if not raw:
            return

        preset = None
        preset_id = None
        if raw.strip().isdigit():
            preset_id = int(raw.strip())
            preset = next((p for p in presets if p["id"] == preset_id), None)
        else:
            preset = next((p for p in presets if p["name"].lower() == raw.strip().lower()), None)
            if preset:
                preset_id = preset["id"]

        if not preset:
            return await ctx.send("❌ Preset not found.")

        confirmed = await self._gm_confirm_twice(
            ctx,
            f"⚠️ This will disable ALL dragon stages and enable preset **{preset['name']}**. Type YES to continue.",
            "⚠️ Final confirmation. Type YES to apply this preset."
        )
        if not confirmed:
            return

        stage_ids = await self._fetch_preset_stage_ids(preset_id)
        if not stage_ids:
            return await ctx.send("❌ Preset has no stages.")

        async with self.bot.pool.acquire() as conn:
            await conn.execute("UPDATE ice_dragon_stages SET enabled = FALSE")
            await conn.executemany(
                "UPDATE ice_dragon_stages SET enabled = TRUE WHERE id = $1",
                [(stage_id,) for stage_id in stage_ids],
            )

        await ctx.send(f"✅ Preset **{preset['name']}** applied. Enabled {len(stage_ids)} stages.")

    async def _gm_delete_preset(self, ctx):
        presets = await self._fetch_dragon_presets()
        if not presets:
            return await ctx.send("No presets found.")

        lines = [f"{p['id']}) {p['name']}" for p in presets]
        await self._send_menu_embed(ctx, "Available Presets", lines)
        raw = await self._gm_prompt(ctx, "Enter preset ID or name to delete:")
        if not raw:
            return

        preset = None
        preset_id = None
        if raw.strip().isdigit():
            preset_id = int(raw.strip())
            preset = next((p for p in presets if p["id"] == preset_id), None)
        else:
            preset = next((p for p in presets if p["name"].lower() == raw.strip().lower()), None)
            if preset:
                preset_id = preset["id"]

        if not preset:
            return await ctx.send("❌ Preset not found.")

        if not await self._gm_confirm(
            ctx,
            f"⚠️ Delete preset **{preset['name']}**? Type YES to confirm."
        ):
            return

        async with self.bot.pool.acquire() as conn:
            await conn.execute("DELETE FROM ice_dragon_presets WHERE id = $1", preset_id)

        await ctx.send(f"✅ Preset **{preset['name']}** deleted.")

    async def _gm_create_dragon(self, ctx):
        name = await self._gm_prompt(ctx, "Dragon name?")
        if not name:
            return
        min_level_raw = await self._gm_prompt(ctx, "Min level?")
        max_level_raw = await self._gm_prompt(ctx, "Max level?")
        if not min_level_raw or not max_level_raw:
            return
        try:
            min_level = int(min_level_raw)
            max_level = int(max_level_raw)
        except ValueError:
            return await ctx.send("❌ Invalid number input.")

        def _calc_base_stats(level: int):
            level_multiplier = 1 + (0.1 * (level - 1))
            hp = 3500 * level_multiplier
            damage = 290 * level_multiplier
            armor = 220 * level_multiplier
            return hp, damage, armor

        min_hp, min_damage, min_armor = _calc_base_stats(min_level)
        max_hp, max_damage, max_armor = _calc_base_stats(max_level)
        await ctx.send(
            "Base stats before multiplier (multiplier affects HP only):\n"
            f"Lv {min_level}: HP {min_hp:.1f}, DMG {min_damage:.1f}, ARM {min_armor:.1f}\n"
            f"Lv {max_level}: HP {max_hp:.1f}, DMG {max_damage:.1f}, ARM {max_armor:.1f}"
        )

        mult_raw = await self._gm_prompt(ctx, "Base multiplier? (e.g. 1.5)")
        if not mult_raw:
            return
        try:
            base_multiplier = float(mult_raw)
        except ValueError:
            return await ctx.send("❌ Invalid number input.")

        elements = self._get_element_choices()
        elem_raw = await self._gm_prompt(
            ctx,
            f"Element? (default Water)\nAvailable: {', '.join(elements)}",
            allow_blank=True,
        )
        element = "Water"
        if elem_raw:
            if elem_raw.capitalize() not in elements:
                return await ctx.send("❌ Invalid element.")
            element = elem_raw.capitalize()

        moves = await self._choose_abilities(ctx, "move")
        if moves is None or not moves:
            return await ctx.send("❌ You must select at least one move.")

        passives = await self._choose_abilities(ctx, "passive", max_count=5)
        if passives is None:
            return

        enabled_raw = await self._gm_prompt(ctx, "Enable this stage? (yes/no, default yes)", allow_blank=True)
        enabled = True
        if enabled_raw:
            enabled = enabled_raw.strip().lower() in ("yes", "y", "true", "1")

        async with self.bot.pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO ice_dragon_stages (name, min_level, max_level, base_multiplier, enabled, element, move_names, passive_names) "
                "VALUES ($1, $2, $3, $4, $5, $6, $7, $8)",
                name,
                min_level,
                max_level,
                base_multiplier,
                enabled,
                element,
                moves,
                passives,
            )
        await ctx.send(f"✅ Dragon stage **{name}** created.")

    async def _gm_edit_dragons(self, ctx):
        rows = await self._fetch_dragon_stages()
        if not rows:
            return await ctx.send("No dragon stages found.")
        lines = [f"{idx}) {row['name']} (Lv {row['min_level']}-{row['max_level']})" for idx, row in enumerate(rows, start=1)]
        await self._send_menu_embed(ctx, "Select a Dragon Stage to Edit", lines)
        sel_raw = await self._gm_prompt(ctx, "Enter the number of the stage to edit:")
        if not sel_raw:
            return
        try:
            sel_idx = int(sel_raw) - 1
            if sel_idx < 0 or sel_idx >= len(rows):
                raise ValueError
        except ValueError:
            return await ctx.send("❌ Invalid selection.")

        stage = dict(rows[sel_idx])
        await self._send_menu_embed(
            ctx,
            f"Editing: {stage['name']}",
            [
                f"Status: {'Enabled' if stage['enabled'] else 'Disabled'}",
                f"Level Range: {stage['min_level']}–{stage['max_level']}",
                f"Multiplier: x{stage['base_multiplier']}",
                f"Element: {stage['element']}",
                f"Moves: {', '.join(stage['move_names'] or []) or 'None'}",
                f"Passives: {', '.join(stage['passive_names'] or []) or 'None'}",
            ],
            footer="Type: name, level_range, multiplier, element, moves, passives, toggle, delete, done",
        )
        menu = (
            "What do you want to edit?\n"
            "Options: name, level_range, multiplier, element, moves, passives, toggle, delete, done"
        )
        while True:
            choice = await self._gm_prompt(ctx, menu)
            if not choice:
                return
            choice = choice.lower()
            if choice == "done":
                break
            if choice == "delete":
                if not await self._gm_confirm(ctx, f"⚠️ Delete stage **{stage['name']}**? Type YES to confirm."):
                    continue
                async with self.bot.pool.acquire() as conn:
                    await conn.execute("DELETE FROM ice_dragon_stages WHERE id = $1", stage["id"])
                await ctx.send("✅ Stage deleted.")
                return
            if choice == "toggle":
                new_enabled = not stage["enabled"]
                action = "enable" if new_enabled else "disable"
                if not await ctx.confirm(f"Confirm: {action} **{stage['name']}**?"):
                    await ctx.send("❌ Toggle cancelled.")
                    continue
                async with self.bot.pool.acquire() as conn:
                    await conn.execute(
                        "UPDATE ice_dragon_stages SET enabled = $1 WHERE id = $2",
                        new_enabled, stage["id"]
                    )
                stage["enabled"] = new_enabled
                await ctx.send(f"✅ Stage {'enabled' if new_enabled else 'disabled'}.")
                continue
            if choice == "name":
                new_name = await self._gm_prompt(ctx, "New name?")
                if not new_name:
                    continue
                async with self.bot.pool.acquire() as conn:
                    await conn.execute("UPDATE ice_dragon_stages SET name = $1 WHERE id = $2", new_name, stage["id"])
                stage["name"] = new_name
            elif choice == "level_range":
                min_raw = await self._gm_prompt(ctx, "New min level?")
                max_raw = await self._gm_prompt(ctx, "New max level?")
                if not min_raw or not max_raw:
                    continue
                try:
                    min_level = int(min_raw)
                    max_level = int(max_raw)
                except ValueError:
                    await ctx.send("❌ Invalid number.")
                    continue
                async with self.bot.pool.acquire() as conn:
                    await conn.execute(
                        "UPDATE ice_dragon_stages SET min_level = $1, max_level = $2 WHERE id = $3",
                        min_level, max_level, stage["id"]
                    )
                stage["min_level"] = min_level
                stage["max_level"] = max_level
            elif choice == "multiplier":
                mult_raw = await self._gm_prompt(ctx, "New base multiplier?")
                if not mult_raw:
                    continue
                try:
                    base_multiplier = float(mult_raw)
                except ValueError:
                    await ctx.send("❌ Invalid number.")
                    continue
                async with self.bot.pool.acquire() as conn:
                    await conn.execute(
                        "UPDATE ice_dragon_stages SET base_multiplier = $1 WHERE id = $2",
                        base_multiplier, stage["id"]
                    )
                stage["base_multiplier"] = base_multiplier
            elif choice == "element":
                elements = self._get_element_choices()
                elem_raw = await self._gm_prompt(ctx, f"Element?\nAvailable: {', '.join(elements)}")
                if not elem_raw:
                    continue
                if elem_raw.capitalize() not in elements:
                    await ctx.send("❌ Invalid element.")
                    continue
                async with self.bot.pool.acquire() as conn:
                    await conn.execute(
                        "UPDATE ice_dragon_stages SET element = $1 WHERE id = $2",
                        elem_raw.capitalize(), stage["id"]
                    )
                stage["element"] = elem_raw.capitalize()
            elif choice == "moves":
                moves = await self._choose_abilities(ctx, "move")
                if moves is None or not moves:
                    continue
                async with self.bot.pool.acquire() as conn:
                    await conn.execute(
                        "UPDATE ice_dragon_stages SET move_names = $1 WHERE id = $2",
                        moves, stage["id"]
                    )
                stage["move_names"] = moves
            elif choice == "passives":
                passives = await self._choose_abilities(ctx, "passive", max_count=5)
                if passives is None:
                    continue
                async with self.bot.pool.acquire() as conn:
                    await conn.execute(
                        "UPDATE ice_dragon_stages SET passive_names = $1 WHERE id = $2",
                        passives, stage["id"]
                    )
                stage["passive_names"] = passives
            else:
                await ctx.send("❌ Unknown option.")
        await ctx.send("✅ Stage updated.")

    async def _gm_create_drop(self, ctx):
        name = await self._gm_prompt(ctx, "Drop name?")
        if not name:
            return
        item_type_raw = await self._gm_prompt(
            ctx,
            f"Item type? Options: {', '.join([i.value for i in ItemType])}"
        )
        if not item_type_raw:
            return
        item_type_raw = item_type_raw.strip().capitalize()
        if item_type_raw not in [i.value for i in ItemType]:
            return await ctx.send("❌ Invalid item type.")
        min_stat_raw = await self._gm_prompt(ctx, "Min stat?")
        max_stat_raw = await self._gm_prompt(ctx, "Max stat?")
        base_chance_raw = await self._gm_prompt(ctx, "Base chance? (percent, e.g. 0.1 or 1.5%)")
        max_chance_raw = await self._gm_prompt(ctx, "Max chance? (percent, e.g. 0.5 or 2%)")
        if not min_stat_raw or not max_stat_raw or not base_chance_raw or not max_chance_raw:
            return
        try:
            min_stat = int(min_stat_raw)
            max_stat = int(max_stat_raw)
            base_chance = self._parse_percent(base_chance_raw)
            max_chance = self._parse_percent(max_chance_raw)
        except ValueError:
            return await ctx.send("❌ Invalid number input.")
        if base_chance is None or max_chance is None:
            return await ctx.send("❌ Invalid chance. Use a percent between 0 and 100.")
        if base_chance > max_chance:
            return await ctx.send("❌ Base chance cannot exceed max chance.")

        elements = self._get_element_choices()
        elem_raw = await self._gm_prompt(
            ctx,
            f"Element? (default Water)\nAvailable: {', '.join(elements)}",
            allow_blank=True,
        )
        element = "Water"
        if elem_raw:
            if elem_raw.capitalize() not in elements:
                return await ctx.send("❌ Invalid element.")
            element = elem_raw.capitalize()

        scope_raw = await self._gm_prompt(ctx, "Drop scope? (global/specific, default global)", allow_blank=True)
        is_global = True
        dragon_stage_id = None
        if scope_raw and scope_raw.strip().lower() in ("specific", "stage", "dragon"):
            stages = await self._fetch_dragon_stages()
            if not stages:
                return await ctx.send("❌ No dragon stages available to bind this drop.")
            lines = [f"{idx}) {row['name']} (Lv {row['min_level']}-{row['max_level']})" for idx, row in enumerate(stages, start=1)]
            sel_raw = await self._gm_prompt(ctx, "Select a stage for this drop:\n" + "\n".join(lines))
            if not sel_raw:
                return
            try:
                sel_idx = int(sel_raw) - 1
                if sel_idx < 0 or sel_idx >= len(stages):
                    raise ValueError
            except ValueError:
                return await ctx.send("❌ Invalid selection.")
            is_global = False
            dragon_stage_id = stages[sel_idx]["id"]

        min_level_raw = await self._gm_prompt(ctx, "Min level filter? (blank for none)", allow_blank=True)
        max_level_raw = await self._gm_prompt(ctx, "Max level filter? (blank for none)", allow_blank=True)
        min_level = int(min_level_raw) if min_level_raw else None
        max_level = int(max_level_raw) if max_level_raw else None

        async with self.bot.pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO ice_dragon_drops (name, item_type, min_stat, max_stat, base_chance, max_chance, is_global, dragon_stage_id, element, min_level, max_level) "
                "VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)",
                name, item_type_raw, min_stat, max_stat, base_chance, max_chance, is_global, dragon_stage_id, element, min_level, max_level
            )
        await ctx.send(f"✅ Drop **{name}** created.")

    async def _gm_edit_drops(self, ctx):
        rows = await self._fetch_dragon_drops()
        if not rows:
            return await ctx.send("No drops found.")
        lines = []
        for idx, row in enumerate(rows, start=1):
            item_type = ItemType.from_string(row["item_type"])
            stat_label = "Defense" if item_type == ItemType.Shield else "Damage"
            lines.append(
                f"{idx}) {row['name']} ({row['item_type']}) - {stat_label}: {row['min_stat']}–{row['max_stat']}"
            )
        await self._send_menu_embed(ctx, "Select a Drop to Edit", lines)
        sel_raw = await self._gm_prompt(ctx, "Enter the number of the drop to edit:")
        if not sel_raw:
            return
        try:
            sel_idx = int(sel_raw) - 1
            if sel_idx < 0 or sel_idx >= len(rows):
                raise ValueError
        except ValueError:
            return await ctx.send("❌ Invalid selection.")

        drop = dict(rows[sel_idx])
        scope_text = "Global" if drop["is_global"] else f"Stage ID {drop['dragon_stage_id']}"
        await self._send_menu_embed(
            ctx,
            f"Editing Drop: {drop['name']}",
            [
                f"Type: {drop['item_type']}",
                f"Stats: {drop['min_stat']}–{drop['max_stat']}",
                f"Chance: {self._format_percent(drop['base_chance'])}–{self._format_percent(drop['max_chance'])}",
                f"Element: {drop['element']}",
                f"Scope: {scope_text}",
                f"Level Filter: {drop['min_level'] or '-'} to {drop['max_level'] or '-'}",
            ],
            footer="Type: name, item_type, stats, chance, element, level_range, scope, delete, done",
        )
        menu = "Options: name, item_type, stats, chance, element, level_range, scope, delete, done"
        while True:
            choice = await self._gm_prompt(ctx, menu)
            if not choice:
                return
            choice = choice.lower()
            if choice == "done":
                break
            if choice == "delete":
                if not await self._gm_confirm(ctx, f"⚠️ Delete drop **{drop['name']}**? Type YES to confirm."):
                    continue
                async with self.bot.pool.acquire() as conn:
                    await conn.execute("DELETE FROM ice_dragon_drops WHERE id = $1", drop["id"])
                await ctx.send("✅ Drop deleted.")
                return
            if choice == "name":
                new_name = await self._gm_prompt(ctx, "New name?")
                if not new_name:
                    continue
                async with self.bot.pool.acquire() as conn:
                    await conn.execute("UPDATE ice_dragon_drops SET name = $1 WHERE id = $2", new_name, drop["id"])
                drop["name"] = new_name
            elif choice == "item_type":
                item_type_raw = await self._gm_prompt(ctx, f"Item type? Options: {', '.join([i.value for i in ItemType])}")
                if not item_type_raw:
                    continue
                item_type_raw = item_type_raw.strip().capitalize()
                if item_type_raw not in [i.value for i in ItemType]:
                    await ctx.send("❌ Invalid item type.")
                    continue
                async with self.bot.pool.acquire() as conn:
                    await conn.execute("UPDATE ice_dragon_drops SET item_type = $1 WHERE id = $2", item_type_raw, drop["id"])
                drop["item_type"] = item_type_raw
            elif choice == "stats":
                min_stat_raw = await self._gm_prompt(ctx, "Min stat?")
                max_stat_raw = await self._gm_prompt(ctx, "Max stat?")
                if not min_stat_raw or not max_stat_raw:
                    continue
                try:
                    min_stat = int(min_stat_raw)
                    max_stat = int(max_stat_raw)
                except ValueError:
                    await ctx.send("❌ Invalid number.")
                    continue
                async with self.bot.pool.acquire() as conn:
                    await conn.execute(
                        "UPDATE ice_dragon_drops SET min_stat = $1, max_stat = $2 WHERE id = $3",
                        min_stat, max_stat, drop["id"]
                    )
                drop["min_stat"] = min_stat
                drop["max_stat"] = max_stat
            elif choice == "chance":
                base_raw = await self._gm_prompt(ctx, "Base chance? (percent)")
                max_raw = await self._gm_prompt(ctx, "Max chance? (percent)")
                if not base_raw or not max_raw:
                    continue
                try:
                    base_chance = self._parse_percent(base_raw)
                    max_chance = self._parse_percent(max_raw)
                except ValueError:
                    await ctx.send("❌ Invalid number.")
                    continue
                if base_chance is None or max_chance is None:
                    await ctx.send("❌ Invalid chance. Use a percent between 0 and 100.")
                    continue
                if base_chance > max_chance:
                    await ctx.send("❌ Base chance cannot exceed max chance.")
                    continue
                async with self.bot.pool.acquire() as conn:
                    await conn.execute(
                        "UPDATE ice_dragon_drops SET base_chance = $1, max_chance = $2 WHERE id = $3",
                        base_chance, max_chance, drop["id"]
                    )
                drop["base_chance"] = base_chance
                drop["max_chance"] = max_chance
            elif choice == "element":
                elements = self._get_element_choices()
                elem_raw = await self._gm_prompt(ctx, f"Element?\nAvailable: {', '.join(elements)}")
                if not elem_raw:
                    continue
                if elem_raw.capitalize() not in elements:
                    await ctx.send("❌ Invalid element.")
                    continue
                async with self.bot.pool.acquire() as conn:
                    await conn.execute(
                        "UPDATE ice_dragon_drops SET element = $1 WHERE id = $2",
                        elem_raw.capitalize(), drop["id"]
                    )
                drop["element"] = elem_raw.capitalize()
            elif choice == "level_range":
                min_raw = await self._gm_prompt(ctx, "Min level filter? (blank for none)", allow_blank=True)
                max_raw = await self._gm_prompt(ctx, "Max level filter? (blank for none)", allow_blank=True)
                min_level = int(min_raw) if min_raw else None
                max_level = int(max_raw) if max_raw else None
                async with self.bot.pool.acquire() as conn:
                    await conn.execute(
                        "UPDATE ice_dragon_drops SET min_level = $1, max_level = $2 WHERE id = $3",
                        min_level, max_level, drop["id"]
                    )
                drop["min_level"] = min_level
                drop["max_level"] = max_level
            elif choice == "scope":
                scope_raw = await self._gm_prompt(ctx, "Drop scope? (global/specific)")
                if not scope_raw:
                    continue
                if scope_raw.strip().lower() in ("global", "all"):
                    async with self.bot.pool.acquire() as conn:
                        await conn.execute(
                            "UPDATE ice_dragon_drops SET is_global = TRUE, dragon_stage_id = NULL WHERE id = $1",
                            drop["id"]
                        )
                    drop["is_global"] = True
                    drop["dragon_stage_id"] = None
                elif scope_raw.strip().lower() in ("specific", "stage", "dragon"):
                    stages = await self._fetch_dragon_stages()
                    if not stages:
                        await ctx.send("❌ No dragon stages available.")
                        continue
                    lines = [f"{idx}) {row['name']} (Lv {row['min_level']}-{row['max_level']})" for idx, row in enumerate(stages, start=1)]
                    sel_raw = await self._gm_prompt(ctx, "Select a stage for this drop:\n" + "\n".join(lines))
                    if not sel_raw:
                        continue
                    try:
                        sel_idx = int(sel_raw) - 1
                        if sel_idx < 0 or sel_idx >= len(stages):
                            raise ValueError
                    except ValueError:
                        await ctx.send("❌ Invalid selection.")
                        continue
                    stage_id = stages[sel_idx]["id"]
                    async with self.bot.pool.acquire() as conn:
                        await conn.execute(
                            "UPDATE ice_dragon_drops SET is_global = FALSE, dragon_stage_id = $1 WHERE id = $2",
                            stage_id, drop["id"]
                        )
                    drop["is_global"] = False
                    drop["dragon_stage_id"] = stage_id
                else:
                    await ctx.send("❌ Invalid scope.")
            else:
                await ctx.send("❌ Unknown option.")
        await ctx.send("✅ Drop updated.")


    async def cog_load(self):
        await self._init_event_settings()

    async def _init_event_settings(self):
        async with self.bot.pool.acquire() as conn:
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS event_settings (
                    event_key TEXT PRIMARY KEY,
                    enabled BOOLEAN NOT NULL,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
            for key, default in self.EVENT_DEFAULTS.items():
                await conn.execute(
                    """
                    INSERT INTO event_settings (event_key, enabled)
                    VALUES ($1, $2)
                    ON CONFLICT (event_key) DO NOTHING
                    """,
                    key,
                    default,
                )
            rows = await conn.fetch("SELECT event_key, enabled FROM event_settings")

        self.event_flags = {row["event_key"]: bool(row["enabled"]) for row in rows}
        for key, default in self.EVENT_DEFAULTS.items():
            self.event_flags.setdefault(key, default)
        self.bot.event_flags = self.event_flags

    def _normalize_event_key(self, raw: str | None) -> str | None:
        if not raw:
            return None
        return self.EVENT_ALIASES.get(raw.strip().lower())

    def _parse_bool(self, raw: str | None) -> bool | None:
        if raw is None:
            return None
        value = raw.strip().lower()
        if value in ("on", "true", "enable", "enabled", "1", "yes", "y"):
            return True
        if value in ("off", "false", "disable", "disabled", "0", "no", "n"):
            return False
        return None

    def get_event_enabled(self, event_key: str) -> bool:
        if not self.event_flags:
            return self.EVENT_DEFAULTS.get(event_key, False)
        return bool(self.event_flags.get(event_key, self.EVENT_DEFAULTS.get(event_key, False)))

    async def set_event_enabled(self, event_key: str, enabled: bool) -> None:
        async with self.bot.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO event_settings (event_key, enabled)
                VALUES ($1, $2)
                ON CONFLICT (event_key)
                DO UPDATE SET enabled = $2, updated_at = NOW()
                """,
                event_key,
                enabled,
            )

        self.event_flags[event_key] = enabled
        self.bot.event_flags = self.event_flags

        lny_cog = self.bot.get_cog("LunarNewYear")
        if lny_cog and hasattr(lny_cog, "enabled"):
            lny_cog.enabled = enabled if event_key == "lunar_new_year" else lny_cog.enabled

    def _event_status_lines(self) -> list[str]:
        lines = []
        for key, name in self.EVENT_DISPLAY_NAMES.items():
            status = "enabled" if self.get_event_enabled(key) else "disabled"
            lines.append(f"{name}: {status}")
        return lines

    @is_gm()
    @commands.group(name="gmevent", aliases=["gmevents"], invoke_without_command=True)
    async def gmevent(self, ctx, event: str | None = None, enabled: str | None = None):
        if event is None:
            lines = self._event_status_lines()
            return await ctx.send("Event status:\n" + "\n".join(lines))

        event_key = self._normalize_event_key(event)
        if not event_key:
            available = ", ".join(sorted(self.EVENT_DISPLAY_NAMES.values()))
            return await ctx.send(f"Unknown event. Available: {available}")

        parsed = self._parse_bool(enabled)
        if parsed is None:
            parsed = not self.get_event_enabled(event_key)

        await self.set_event_enabled(event_key, parsed)
        status = "enabled" if parsed else "disabled"
        await ctx.send(f"{self.EVENT_DISPLAY_NAMES[event_key]} event is now **{status}**.")

    @gmevent.command(name="list", aliases=["status"])
    async def gmevent_list(self, ctx):
        lines = self._event_status_lines()
        await ctx.send("Event status:\n" + "\n".join(lines))

    @gmevent.command(name="resetshops", aliases=["resetshop"])
    async def gmevent_resetshops(self, ctx, event: str | None = "all"):
        if event is None or event.strip().lower() == "all":
            targets = list(self.EVENT_SHOP_DEFAULTS.keys())
        else:
            event_key = self._normalize_event_key(event)
            if not event_key or event_key not in self.EVENT_SHOP_DEFAULTS:
                available = ", ".join(
                    self.EVENT_DISPLAY_NAMES[key]
                    for key in self.EVENT_SHOP_DEFAULTS.keys()
                )
                return await ctx.send(
                    f"Unknown event or no shop quantities. Available: {available}"
                )
            targets = [event_key]

        async with self.bot.pool.acquire() as conn:
            for key in targets:
                defaults = self.EVENT_SHOP_DEFAULTS[key]
                set_clause = ", ".join(f"{col} = {val}" for col, val in defaults.items())
                await conn.execute(f"UPDATE profile SET {set_clause};")

        names = ", ".join(self.EVENT_DISPLAY_NAMES[key] for key in targets)
        await ctx.send(f"Shop quantities reset for: {names}.")


class GMInviteView(discord.ui.View):
    def __init__(self, target_user: discord.Member, timeout: int = 120):
        super().__init__(timeout=timeout)
        self.target_user = target_user
        self.value = None  # Will be True (accepted) or False (declined)
        
    @discord.ui.button(label="Accept GM Role", style=discord.ButtonStyle.green, emoji="✅")
    async def accept_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.target_user.id:
            await interaction.response.send_message("❌ This invitation is not for you.", ephemeral=True)
            return
        
        self.value = True
        await interaction.response.send_message("✅ You have accepted the Game Master role!", ephemeral=True)
        self.stop()
    
    @discord.ui.button(label="Decline", style=discord.ButtonStyle.red, emoji="❌")
    async def decline_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.target_user.id:
            await interaction.response.send_message("❌ This invitation is not for you.", ephemeral=True)
            return
        
        self.value = False
        await interaction.response.send_message("❌ You have declined the Game Master role.", ephemeral=True)
        self.stop()

    async def on_timeout(self):
        # Disable all buttons when the view times out
        for item in self.children:
            item.disabled = True


class GodInviteView(discord.ui.View):
    def __init__(self, target_user: discord.Member, timeout: int = 120):
        super().__init__(timeout=timeout)
        self.target_user = target_user
        self.value = None  # Will be True (accepted) or False (declined)
        
    @discord.ui.button(label="Accept God Role", style=discord.ButtonStyle.green, emoji="🌟")
    async def accept_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.target_user.id:
            await interaction.response.send_message("❌ This invitation is not for you.", ephemeral=True)
            return
        
        self.value = True
        await interaction.response.send_message("🌟 You have accepted the God role!", ephemeral=True)
        self.stop()
    
    @discord.ui.button(label="Decline", style=discord.ButtonStyle.red, emoji="❌")
    async def decline_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.target_user.id:
            await interaction.response.send_message("❌ This invitation is not for you.", ephemeral=True)
            return
        
        self.value = False
        await interaction.response.send_message("❌ You have declined the God role.", ephemeral=True)
        self.stop()

    async def on_timeout(self):
        # Disable all buttons when the view times out
        for item in self.children:
            item.disabled = True





class BattleReplayController(discord.ui.View):
    """Interactive controller for live battle replays"""
    
    def __init__(self, ctx, replay_data, gm_cog):
        super().__init__(timeout=300)  # 5 minute timeout
        self.ctx = ctx
        self.replay_data = replay_data
        self.gm_cog = gm_cog
        self.current_turn = 0
        self.is_playing = False
        self.play_speed = 2.0  # seconds between turns
        self.action_count = 1  # number of actions to display (1-4)
        self.max_turns = len(replay_data['battle_data'].get('turn_states', []))
        
        # Update button states
        self.update_button_states()
    
    def update_button_states(self):
        """Update button enabled/disabled states based on current position"""
        # Disable rewind if at start
        self.rewind_button.disabled = (self.current_turn <= 0)
        # Disable fast forward if at end
        self.fast_forward_button.disabled = (self.current_turn >= self.max_turns - 1)
        # Update play/pause button
        self.play_pause_button.emoji = "⏸️" if self.is_playing else "▶️"
        self.play_pause_button.label = "Pause" if self.is_playing else "Play"
    
    @discord.ui.button(emoji="⏪", label="Rewind", style=discord.ButtonStyle.secondary, row=0)
    async def rewind_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.ctx.author.id:
            return await interaction.response.send_message("❌ Only the command user can control the replay.", ephemeral=True)
        
        self.is_playing = False
        self.current_turn = max(0, self.current_turn - 1)
        self.update_button_states()
        
        embed = await self.gm_cog.create_live_battle_replay_embed(self.replay_data, self.current_turn, self.action_count)
        await interaction.response.edit_message(embed=embed, view=self)
    
    @discord.ui.button(emoji="▶️", label="Play", style=discord.ButtonStyle.primary, row=0)
    async def play_pause_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.ctx.author.id:
            return await interaction.response.send_message("❌ Only the command user can control the replay.", ephemeral=True)
        
        self.is_playing = not self.is_playing
        self.update_button_states()
        
        if self.is_playing:
            # Start auto-playing
            await interaction.response.edit_message(view=self)
            await self.auto_play()
        else:
            await interaction.response.edit_message(view=self)
    
    @discord.ui.button(emoji="⏩", label="Fast Forward", style=discord.ButtonStyle.secondary, row=0)
    async def fast_forward_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.ctx.author.id:
            return await interaction.response.send_message("❌ Only the command user can control the replay.", ephemeral=True)
        
        self.is_playing = False
        self.current_turn = min(self.max_turns - 1, self.current_turn + 1)
        self.update_button_states()
        
        embed = await self.gm_cog.create_live_battle_replay_embed(self.replay_data, self.current_turn, self.action_count)
        await interaction.response.edit_message(embed=embed, view=self)
    
    @discord.ui.button(emoji="⏮️", label="Start", style=discord.ButtonStyle.secondary, row=1)
    async def start_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.ctx.author.id:
            return await interaction.response.send_message("❌ Only the command user can control the replay.", ephemeral=True)
        
        self.is_playing = False
        self.current_turn = 0
        self.update_button_states()
        
        embed = await self.gm_cog.create_live_battle_replay_embed(self.replay_data, self.current_turn, self.action_count)
        await interaction.response.edit_message(embed=embed, view=self)
    
    @discord.ui.button(emoji="⏭️", label="End", style=discord.ButtonStyle.secondary, row=1)
    async def end_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.ctx.author.id:
            return await interaction.response.send_message("❌ Only the command user can control the replay.", ephemeral=True)
        
        self.is_playing = False
        self.current_turn = self.max_turns - 1
        self.update_button_states()
        
        embed = await self.gm_cog.create_live_battle_replay_embed(self.replay_data, self.current_turn, self.action_count)
        await interaction.response.edit_message(embed=embed, view=self)
    
    @discord.ui.select(
        placeholder="⚡ Choose playback speed...",
        options=[
            discord.SelectOption(label="🐌 Slow (4s per turn)", value="4.0", emoji="🐌"),
            discord.SelectOption(label="🚶 Normal (2s per turn)", value="2.0", emoji="🚶", default=True),
            discord.SelectOption(label="🏃 Fast (1s per turn)", value="1.0", emoji="🏃"),
            discord.SelectOption(label="⚡ Lightning (0.5s per turn)", value="0.5", emoji="⚡"),
        ],
        row=2
    )
    async def speed_select(self, interaction: discord.Interaction, select: discord.ui.Select):
        if interaction.user.id != self.ctx.author.id:
            return await interaction.response.send_message("❌ Only the command user can control the replay.", ephemeral=True)
        
        self.play_speed = float(select.values[0])
        speed_name = {
            "4.0": "🐌 Slow",
            "2.0": "🚶 Normal", 
            "1.0": "🏃 Fast",
            "0.5": "⚡ Lightning"
        }.get(select.values[0], "Normal")
        
        await interaction.response.send_message(f"⚡ **Speed changed to {speed_name}**", ephemeral=True)
    
    @discord.ui.select(
        placeholder="📜 Choose number of actions to display...",
        options=[
            discord.SelectOption(label="1 Action", value="1", emoji="1️⃣", default=True),
            discord.SelectOption(label="2 Actions", value="2", emoji="2️⃣"),
            discord.SelectOption(label="3 Actions", value="3", emoji="3️⃣"),
            discord.SelectOption(label="4 Actions", value="4", emoji="4️⃣"),
        ],
        row=3
    )
    async def action_count_select(self, interaction: discord.Interaction, select: discord.ui.Select):
        if interaction.user.id != self.ctx.author.id:
            return await interaction.response.send_message("❌ Only the command user can control the replay.", ephemeral=True)
        
        self.action_count = int(select.values[0])
        action_text = f"{self.action_count} Action{'s' if self.action_count > 1 else ''}"
        
        # Update the embed with new action count
        embed = await self.gm_cog.create_live_battle_replay_embed(self.replay_data, self.current_turn, self.action_count)
        await interaction.response.edit_message(embed=embed, view=self)
        
        # Also send confirmation message
        await interaction.followup.send(f"📜 **Now displaying {action_text}**", ephemeral=True)
    
    async def auto_play(self):
        """Auto-play the replay with the current speed"""
        while self.is_playing and self.current_turn < self.max_turns - 1:
            await asyncio.sleep(self.play_speed)
            
            if not self.is_playing:  # Check if stopped during sleep
                break
                
            self.current_turn += 1
            self.update_button_states()
            
            try:
                embed = await self.gm_cog.create_live_battle_replay_embed(self.replay_data, self.current_turn, self.action_count)
                
                # Get the original message and edit it
                if hasattr(self, 'message') and self.message:
                    await self.message.edit(embed=embed, view=self)
            except discord.NotFound:
                # Message was deleted
                self.is_playing = False
                break
            except Exception as e:
                print(f"Error during auto-play: {e}")
                self.is_playing = False
                break
        
        # Auto-play finished
        if self.is_playing:
            self.is_playing = False
            self.update_button_states()
            try:
                if hasattr(self, 'message') and self.message:
                    await self.message.edit(view=self)
            except:
                pass
    
    async def on_timeout(self):
        """Handle view timeout"""
        self.is_playing = False
        
        # Disable all buttons
        for item in self.children:
            item.disabled = True
        
        try:
            if hasattr(self, 'message') and self.message:
                await self.message.edit(view=self)
        except:
            pass


async def setup(bot):
    await bot.add_cog(GameMaster(bot))


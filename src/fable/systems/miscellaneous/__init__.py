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
import json


import requests
from io import BytesIO

from discord.ext.commands import CommandError

from fable.core.classes import from_string as class_from_string

import pytesseract
import os
import platform
import re
import statistics
import sys
import time

from collections import defaultdict, deque
from functools import partial

import aiohttp
import io

from PIL import Image, ImageEnhance, ImageOps, ImageFilter
from openai import AsyncOpenAI

import discord
import distro
import humanize
import pkg_resources as pkg
import requests

from discord.ext import commands

from fable.core.converters import ImageFormat, ImageUrl
from fable.systems.help import chunks
from fable.systems.shard_communication import next_day_cooldown
from fable.systems.shard_communication import user_on_cooldown as user_cooldown
from fable.utils import random
from fable.utils.checks import ImgurUploadError, has_char, user_is_patron, is_gm
from fable.utils.i18n import _, locale_doc
from fable.utils.misc import nice_join
from fable.utils.shell import get_cpu_name

def load_whitelist():
    with open('whitelist.json', 'r') as file:
        return json.load(file)

def save_whitelist(data):
    with open('whitelist.json', 'w') as file:
        json.dump(data, file, indent=4)

class PaginatorView(discord.ui.View):
    def __init__(self, ctx, pages, start_page=0, timeout=60):
        super().__init__(timeout=timeout)
        self.ctx = ctx
        self.pages = pages
        self.current_page = start_page
        self.message = None  # we will set this after sending

    async def on_timeout(self):
        """
        Called when the View times out (no interaction for `timeout` seconds).
        We'll disable all buttons here.
        """
        for child in self.children:
            child.disabled = True
        if self.message:
            await self.message.edit(view=self)

    # --------------------------------------------------------------------------
    # Button callbacks
    # --------------------------------------------------------------------------

    @discord.ui.button(label="Previous", style=discord.ButtonStyle.blurple)
    async def previous_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Ensure only the command invoker can use buttons
        if interaction.user != self.ctx.author:
            return await interaction.response.send_message(
                "This button isn't for you!", ephemeral=True
            )

        self.current_page = (self.current_page - 1) % len(self.pages)
        await interaction.response.edit_message(embed=self.pages[self.current_page], view=self)

    @discord.ui.button(label="Close", style=discord.ButtonStyle.red)
    async def close_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Ensure only the command invoker can use buttons
        if interaction.user != self.ctx.author:
            return await interaction.response.send_message(
                "This button isn't for you!", ephemeral=True
            )

        await interaction.message.delete()
        self.stop()  # end the interaction to clean up

    @discord.ui.button(label="Next", style=discord.ButtonStyle.blurple)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Ensure only the command invoker can use buttons
        if interaction.user != self.ctx.author:
            return await interaction.response.send_message(
                "This button isn't for you!", ephemeral=True
            )

        self.current_page = (self.current_page + 1) % len(self.pages)
        await interaction.response.edit_message(embed=self.pages[self.current_page], view=self)


class Miscellaneous(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.talk_context = defaultdict(partial(deque, maxlen=3))
        self.conversations = {}
        self.ALLOWED_CHANNELS = {
            1145473586556055672,
            1152255240654045295,
            1149193023259951154
        }
        self.whitelist = load_whitelist()

    async def get_imgur_url(self, url: str):
        async with self.bot.session.post(
                "https://api.imgur.com/3/image",
                headers={
                    "Authorization": f"Client-ID {self.bot.config.external.imgur_token}"
                },
                json={"image": url, "type": "url"},
        ) as r:
            json = await r.json()
            try:
                short_url = json["data"]["link"]
            except KeyError:
                raise ImgurUploadError()
        return short_url

    @commands.command()
    async def wiki(self, ctx):
        await ctx.send("https://wiki.fablerpg.xyz")

    @has_char()
    @user_cooldown(1)
    @commands.hybrid_command()
    @locale_doc
    async def all(self, ctx):
        _("""Automatically invokes several daily commands for you.

        This command will attempt to run several of your daily or periodic commands 
        such as `vote`, `daily`, `donatordaily`, `steal`, `date`, `pray`, and 
        `familyevent` in one go, if they are not on cooldown.

        Usage:
          `$all`

        Note:
        - Commands that are on cooldown will be skipped""")

        # Check tier access
        character_data = await ctx.bot.pool.fetchrow(
            'SELECT tier, class FROM profile WHERE "user"=$1;', ctx.author.id
        )
        if not character_data or character_data["tier"] < 1:
            return await ctx.send(_("You do not have access to this command."))

        # Define commands and their cooldowns
        command_config = {
            'cratesdaily': {'cooldown': 12 * 3600},  # 12 hours
            'daily': {'cooldown': self.time_until_midnight()},
            'boosterdaily': {'cooldown': self.time_until_midnight()},
            'date': {'cooldown': 12 * 3600},  # 12 hours
            'pray': {'cooldown': self.time_until_midnight()},
            'familyevent': {'cooldown': 30 * 60}  # 30 minutes
        }

        # Get all cooldowns in one Redis pipeline
        async with ctx.bot.redis.pipeline() as pipe:
            for cmd_name in command_config:
                pipe.ttl(f"cd:{ctx.author.id}:{cmd_name}")
            cooldowns = await pipe.execute()

        # Process user classes once
        user_classes = {
            type(c).__name__
            for c in map(class_from_string, character_data["class"])
        } if character_data["class"] else set()

        tasks = []
        status_messages = []

        for (cmd_name, config), current_cooldown in zip(command_config.items(), cooldowns):
            command = self.bot.get_command(cmd_name)
            if not command:
                continue

            # Check if command is available
            if current_cooldown != -2:  # Cooldown exists
                remaining = self.format_time(current_cooldown)
                status_messages.append(f"`{cmd_name}`: {remaining} cooldown remaining")
                continue

            # Check class requirement if any
            if class_req := config.get('class_requirement'):
                if class_req not in user_classes:
                    status_messages.append(
                        f"`{cmd_name}`: Requires {class_req} class"
                    )
                    continue

            # Add command to task list and set cooldown
            tasks.append(ctx.invoke(command))
            await ctx.bot.redis.set(
                f"cd:{ctx.author.id}:{command.qualified_name}",
                command.qualified_name,
                ex=config['cooldown']
            )

        # Execute all commands concurrently
        if tasks:
            try:
                await asyncio.gather(*tasks)
            except Exception as e:
                await ctx.send(f"An error occurred: {str(e)}")
                return

        # Send status report
        if status_messages:
            status_report = "\n".join(status_messages)
            await ctx.send(
                _("Status Report:\n{status_report}").format(
                    status_report=status_report
                )
            )
        try:
            await self.bot.reset_cooldown(ctx)
        except Exception:
            pass

    def format_time(self, seconds):
        """Convert seconds to HH:MM:SS format."""
        hours, remainder = divmod(seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"{int(hours):02}:{int(minutes):02}:{int(seconds):02}"

    def time_until_midnight(self):
        """Calculate the number of seconds until the next midnight UTC."""
        return int(86400 - (time.time() % 86400))


    # Updated daily command with database streak tracking
    @has_char()
    @next_day_cooldown()
    @commands.hybrid_command(brief=_("Get your daily reward"))
    @locale_doc
    async def daily(self, ctx):
        _(
            """Get your daily reward. Depending on your streak, you will gain better rewards.

            After ten days, your rewards will reset. Day 11 and day 1 have the same rewards.
            The rewards will either be money (2/3 chance) or crates (1/3 chance).

            Special milestone rewards:
            Day 50: 1 Legendary Crate + 100,000 gold
            Day 100: 1 Fortune Crate + 150,000 gold
            Day 200: 100 Mystery Crates + 200,000 gold
            Day 300: 1 Divine Crate + 300,000 gold
            Day 400: 3 Fortune Crates + 400,000 gold
            Day 500: 2 Divine Crates + 500,000 gold

            **These milestones cycle every 500 days**

            If you don't use this command up to 48 hours after the first use, you will lose your streak.
            You can restore lost streaks using `restore` command (3 uses available).

            (This command has a cooldown until 12am UTC.)"""
        )

        try:
            # Create streaks table if it doesn't exist
            async with self.bot.pool.acquire() as conn:
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS streaks (
                        user_id BIGINT PRIMARY KEY,
                        current_streak INTEGER DEFAULT 0,
                        highest_days INTEGER DEFAULT 0,
                        restore_points INTEGER DEFAULT 3,
                        last_daily TIMESTAMP DEFAULT NOW()
                    );
                """)

            # First, try to get streak from Redis (this is the primary source)
            redis_streak = await self.bot.redis.execute_command("GET", f"idle:daily:{ctx.author.id}")

            if redis_streak is not None:
                # User has active Redis streak, increment it
                current_streak = int(redis_streak) + 1
            else:
                # No Redis streak, check if they have database data
                async with self.bot.pool.acquire() as conn:
                    user_data = await conn.fetchrow(
                        'SELECT current_streak, highest_days, restore_points, last_daily FROM streaks WHERE user_id = $1;',
                        ctx.author.id
                    )

                    if user_data is None:
                        # Brand new user
                        current_streak = 1
                    else:
                        # Check if they can continue from database or if it's been too long
                        import datetime
                        last_daily = user_data['last_daily']
                        now = datetime.datetime.now(datetime.timezone.utc)
                        time_diff = now - last_daily.replace(tzinfo=datetime.timezone.utc)

                        if time_diff.total_seconds() <= 48 * 60 * 60:  # Within 48 hours
                            current_streak = user_data['current_streak'] + 1
                        else:
                            current_streak = 1  # Reset streak

            # Update both Redis and database
            await self.bot.redis.execute_command(
                "SET", f"idle:daily:{ctx.author.id}", current_streak
            )
            await self.bot.redis.execute_command(
                "EXPIRE", f"idle:daily:{ctx.author.id}", 48 * 60 * 60
            )

            # Update database
            async with self.bot.pool.acquire() as conn:
                user_data = await conn.fetchrow(
                    'SELECT highest_days, restore_points FROM streaks WHERE user_id = $1;',
                    ctx.author.id
                )

                if user_data is None:
                    # New user
                    await conn.execute(
                        'INSERT INTO streaks (user_id, current_streak, highest_days, restore_points, last_daily) VALUES ($1, $2, $3, $4, NOW());',
                        ctx.author.id, current_streak, current_streak, 3
                    )
                else:
                    # Update existing user
                    new_highest = max(current_streak, user_data['highest_days'])
                    await conn.execute(
                        'UPDATE streaks SET current_streak = $1, highest_days = $2, last_daily = NOW() WHERE user_id = $3;',
                        current_streak, new_highest, ctx.author.id
                    )

            streak = current_streak

            # Handle milestone rewards
            milestone_rewards = {
                50: ("legendary", 1, 100000),
                100: ("fortune", 1, 150000),
                200: ("mystery", 100, 200000),
                300: ("divine", 1, 300000),
                400: ("fortune", 3, 400000),
                500: ("divine", 2, 500000),
                550: ("fortune", 2, 100000),
                600: ("divine", 1, 150000),
                700: ("mystery", 100, 200000),
                800: ("fortune", 3, 300000),
                900: ("divine", 4, 400000),
                1000: ("divine", 4, 500000),
            }

            if streak in milestone_rewards:
                crate_type, crate_amount, bonus_money = milestone_rewards[streak]
                async with self.bot.pool.acquire() as conn:
                    # Add crates
                    await conn.execute(
                        f'UPDATE profile SET "crates_{crate_type}"="crates_{crate_type}"+$1 WHERE "user"=$2;',
                        crate_amount,
                        ctx.author.id,
                    )
                    # Add bonus money
                    await conn.execute(
                        'UPDATE profile SET "money"="money"+$1 WHERE "user"=$2;',
                        bonus_money,
                        ctx.author.id,
                    )
                    # Log transactions
                    await self.bot.log_transaction(
                        ctx,
                        from_=1,
                        to=ctx.author.id,
                        subject="milestone_crates",
                        data={"Rarity": crate_type, "Amount": crate_amount},
                        conn=conn,
                    )
                    await self.bot.log_transaction(
                        ctx,
                        from_=1,
                        to=ctx.author.id,
                        subject="milestone_money",
                        data={"Gold": bonus_money},
                        conn=conn,
                    )
                txt = f"**{crate_amount}** {getattr(self.bot.cogs['Crates'].emotes, crate_type)} and **${bonus_money}**"
            else:
                # Regular daily rewards logic
                money = 2 ** ((streak + 9) % 10) * 50
                if random.randint(0, 2) > 0:
                    money = 2 ** ((streak + 9) % 10) * 50
                    # Silver = 1.5x
                    if await user_is_patron(self.bot, ctx.author, "silver"):
                        money = round(money * 1.5)

                    result = await self.bot.pool.fetchval('SELECT tier FROM profile WHERE "user" = $1;', ctx.author.id)

                    if result >= 3:
                        money = round(money * 3)

                    async with self.bot.pool.acquire() as conn:
                        await conn.execute(
                            'UPDATE profile SET "money"="money"+$1 WHERE "user"=$2;',
                            money,
                            ctx.author.id,
                        )
                        await self.bot.log_transaction(
                            ctx,
                            from_=1,
                            to=ctx.author.id,
                            subject="daily",
                            data={"Gold": money},
                            conn=conn,
                        )
                    txt = f"**${money}**"
                else:
                    num = round(((streak + 9) % 10 + 1) / 2)
                    amt = random.randint(1, 6 - num)
                    types = [
                        "common",
                        "uncommon",
                        "rare",
                        "magic",
                        "legendary",
                        "common",
                        "common",
                        "common",
                    ]  # Trick for -1
                    type_ = random.choice(
                        [types[num - 3]] * 80 + [types[num - 2]] * 19 + [types[num - 1]] * 1
                    )
                    async with self.bot.pool.acquire() as conn:
                        await conn.execute(
                            f'UPDATE profile SET "crates_{type_}"="crates_{type_}"+$1 WHERE "user"=$2;',
                            amt,
                            ctx.author.id,
                        )
                        await self.bot.log_transaction(
                            ctx,
                            from_=1,
                            to=ctx.author.id,
                            subject="crates",
                            data={"Rarity": type_, "Amount": amt},
                            conn=conn,
                        )
                    txt = f"**{amt}** {getattr(self.bot.cogs['Crates'].emotes, type_)}"

            await ctx.send(
                _(
                    "You received your daily {txt}!\nYou are on a streak of **{streak}**"
                    " days!\n*Tip: `{prefix}vote` every 12 hours to get an up to legendary"
                    " crate with possibly rare items!*"
                ).format(txt=txt, streak=streak, prefix=ctx.clean_prefix)
            )
        except Exception as e:
            import traceback
            error_message = f"Error occurred: {e}\n"
            error_message += traceback.format_exc()
            await ctx.send(error_message)
            print(error_message)

    # New restore command
    @has_char()
    @commands.hybrid_command(brief=_("Restore your lost daily streak"))
    @locale_doc
    async def restore(self, ctx):
        _(
            """Restore your lost daily streak using restore points.

            You have 3 restore points available. Each use will restore your streak
            to your previous highest streak achieved.

            This can only be used if your current streak is lower than your highest
            recorded streak and you have restore points remaining."""
        )

        try:
            async with self.bot.pool.acquire() as conn:
                # Get user streak data
                user_data = await conn.fetchrow(
                    'SELECT current_streak, highest_days, restore_points FROM streaks WHERE user_id = $1;',
                    ctx.author.id
                )

                if user_data is None:
                    await ctx.send(_("You haven't used the daily command yet! Use `{prefix}daily` first.").format(
                        prefix=ctx.clean_prefix))
                    return

                current_streak = user_data['current_streak']
                highest_days = user_data['highest_days']
                restore_points = user_data['restore_points']

                # Check if they have restore points
                if restore_points <= 0:
                    await ctx.send(_("❌ You have no restore points remaining!"))
                    return

                # Check if they need to restore (current streak is lower than highest)
                if current_streak >= highest_days:
                    await ctx.send(
                        _("❌ Your current streak (**{current}**) is already at or above your highest streak (**{highest}**)!").format(
                            current=current_streak, highest=highest_days
                        ))
                    return

                # Allow restoration regardless of Redis cooldown since that's the whole point

                # Perform the restore
                await conn.execute(
                    'UPDATE streaks SET current_streak = $1, restore_points = $2, last_daily = NOW() WHERE user_id = $3;',
                    highest_days, restore_points - 1, ctx.author.id
                )

                # Update Redis to reflect the restored streak
                await self.bot.redis.execute_command(
                    "SET", f"idle:daily:{ctx.author.id}", highest_days
                )
                await self.bot.redis.execute_command(
                    "EXPIRE", f"idle:daily:{ctx.author.id}", 48 * 60 * 60
                )

                # Log the restore
                await self.bot.log_transaction(
                    ctx,
                    from_=ctx.author.id,
                    to=1,
                    subject="streak_restore",
                    data={"From": current_streak, "To": highest_days, "Points_Remaining": restore_points - 1},
                    conn=conn,
                )

                await ctx.send(_(
                    "✅ **Streak Restored!**\n"
                    "Your streak has been restored from **{old}** to **{new}** days!\n"
                    "Restore points remaining: **{points}**/2"
                ).format(old=current_streak, new=highest_days, points=restore_points - 1))

        except Exception as e:
            import traceback
            error_message = f"Error occurred: {e}\n"
            error_message += traceback.format_exc()
            await ctx.send(error_message)
            print(error_message)


    # Command to check streak status
    @has_char()
    @commands.hybrid_command(brief=_("Check your streak status"))
    @locale_doc
    async def streaks(self, ctx):
        _(
            """Check your current streak status, highest streak achieved, and remaining restore points."""
        )

        try:
            # Get current streak from Redis
            redis_streak = await self.bot.redis.execute_command("GET", f"idle:daily:{ctx.author.id}")
            current_streak = int(redis_streak) if redis_streak else 0
            ctx.send(f"loaded from redis")
            # Get database data for highest streak and restore points
            async with self.bot.pool.acquire() as conn:
                user_data = await conn.fetchrow(
                    'SELECT highest_days, restore_points FROM streaks WHERE user_id = $1;',
                    ctx.author.id
                )

                if user_data is None:
                    # No database data - use Redis streak as highest if it exists
                    if current_streak == 0:
                        await ctx.send(_("You haven't used the daily command yet! Use `{prefix}daily` first.").format(
                            prefix=ctx.clean_prefix))
                        return
                    highest_days = current_streak
                    restore_points = 2  # Default restore points
                else:
                    highest_days = user_data['highest_days']
                    restore_points = user_data['restore_points']
                    # If no database highest but we have Redis streak, use Redis as highest
                    if highest_days == 0 and current_streak > 0:
                        highest_days = current_streak

                message = _(
                    "You are on a daily streak of **{current}** days!\n"
                    "Your highest streak is **{highest}** days.\n"
                    "You have **{points}**/2 restore points remaining."
                ).format(current=current_streak, highest=highest_days, points=restore_points)

                if current_streak < highest_days and restore_points > 0:
                    message += _("\n\n💡 *Tip: Use `{prefix}restore` to restore your streak to {highest} days!*").format(
                        prefix=ctx.clean_prefix, highest=highest_days
                    )

                await ctx.send(message)

        except Exception as e:
            import traceback
            error_message = f"Error occurred: {e}\n"
            error_message += traceback.format_exc()
            await ctx.send(error_message)
            print(error_message)

    @is_gm()
    @commands.command(name="gameusername", hidden=True)
    async def gameusername(self, ctx, *, username: str):
        """Set your game username. Can only be set once."""

        # Check if user already has a game username set
        async with self.bot.pool.acquire() as conn:
            existing = await conn.fetchval(
                "SELECT gameusername FROM profile WHERE \"user\" = $1",
                ctx.author.id
            )

            if existing is not None:
                await ctx.send("❌ You already have a game username set. Contact an admin to change this.")
                return

        # Confirm the username with the user
        confirmation_msg = f"Are you sure you want to set your game username to `{username}`?\n" \
                           f"⚠️ **This can only be set once and cannot be changed without admin help.**"

        confirmed = await ctx.confirm(confirmation_msg)
        if not confirmed:
            await ctx.send("❌ Game username setup cancelled.")
            return

        # Update the database
        try:
            async with self.bot.pool.acquire() as conn:
                # Check again in case it was set during confirmation
                double_check = await conn.fetchval(
                    "SELECT gameusername FROM profile WHERE \"user\" = $1",
                    ctx.author.id
                )

                if double_check is not None:
                    await ctx.send("❌ Someone already set your game username. Contact an admin to change this.")
                    return

                await conn.execute(
                    "UPDATE profile SET gameusername = $1 WHERE \"user\" = $2",
                    username, ctx.author.id
                )

            await ctx.send(f"✅ Successfully set your game username to `{username}`!")

        except Exception as e:
            await ctx.send(f"❌ An error occurred while setting your game username: {e}")
            # Log the error if you have logging set up
            print(f"Error setting game username for {ctx.author.id}: {e}")

    @commands.hybrid_command(brief=_("Admin: Set a user's daily streak"))
    @locale_doc
    async def setstreak(self, ctx, user_input: str, streak: int):
        _(
            """Admin command to set a user's daily streak.

            Usage: setstreak <user_id_or_mention> <streak_days>

            This command will:
            - Set the user's current streak
            - Update their highest streak if the new streak is higher
            - Update both Redis and database
            - Reset their daily cooldown

            User can be specified by ID or mention.
            Only accessible by bot owner."""
        )

        # Check if user is authorized (your user ID)
        if ctx.author.id != 295173706496475136:
            await ctx.send("❌ You don't have permission to use this command!")
            return

        # Try to resolve user from input (ID or mention)
        user = None
        try:
            # First try to convert as member mention
            user = await commands.MemberConverter().convert(ctx, user_input)
        except commands.BadArgument:
            # If that fails, try to parse as user ID
            try:
                user_id = int(user_input)
                user = await self.bot.fetch_user(user_id)
            except (ValueError, discord.NotFound):
                await ctx.send("❌ Could not find user! Please provide a valid user ID or mention.")
                return

        if user is None:
            await ctx.send("❌ Could not find user! Please provide a valid user ID or mention.")
            return

        # Validate streak value
        if streak < 0:
            await ctx.send("❌ Streak cannot be negative!")
            return

        if streak > 10000:  # Reasonable upper limit
            await ctx.send("❌ Streak cannot exceed 10,000 days!")
            return

        try:
            # Create streaks table if it doesn't exist
            async with self.bot.pool.acquire() as conn:
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS streaks (
                        user_id BIGINT PRIMARY KEY,
                        current_streak INTEGER DEFAULT 0,
                        highest_days INTEGER DEFAULT 0,
                        restore_points INTEGER DEFAULT 3,
                        last_daily TIMESTAMP DEFAULT NOW()
                    );
                """)

                # Get current user data
                user_data = await conn.fetchrow(
                    'SELECT current_streak, highest_days, restore_points FROM streaks WHERE user_id = $1;',
                    user.id
                )

                old_streak = 0
                old_highest = 0
                restore_points = 2  # Default restore points

                if user_data:
                    old_streak = user_data['current_streak']
                    old_highest = user_data['highest_days']
                    restore_points = user_data['restore_points']

                # Calculate new highest streak
                new_highest = max(streak, old_highest)

                # Update or insert user data
                if user_data:
                    await conn.execute(
                        'UPDATE streaks SET current_streak = $1, highest_days = $2, last_daily = NOW() WHERE user_id = $3;',
                        streak, new_highest, user.id
                    )
                else:
                    await conn.execute(
                        'INSERT INTO streaks (user_id, current_streak, highest_days, restore_points, last_daily) VALUES ($1, $2, $3, $4, NOW());',
                        user.id, streak, new_highest, restore_points
                    )

                # Update Redis
                if streak > 0:
                    await self.bot.redis.execute_command(
                        "SET", f"idle:daily:{user.id}", streak
                    )
                    await self.bot.redis.execute_command(
                        "EXPIRE", f"idle:daily:{user.id}", 48 * 60 * 60
                    )
                else:
                    # If streak is 0, remove from Redis
                    await self.bot.redis.execute_command("DEL", f"idle:daily:{user.id}")

                # Also clear their daily cooldown so they can use daily command immediately
                await self.bot.redis.execute_command("DEL", f"cd:{user.id}:daily")

                # Log the admin action
                await self.bot.log_transaction(
                    ctx,
                    from_=ctx.author.id,
                    to=user.id,
                    subject="admin_set_streak",
                    data={
                        "Old_Streak": old_streak,
                        "New_Streak": streak,
                        "Old_Highest": old_highest,
                        "New_Highest": new_highest,
                        "Admin": ctx.author.id
                    },
                    conn=conn,
                )

                # Create response message
                response = f"✅ **Streak Updated for {user.display_name}!**\n"
                response += f"Current streak: **{old_streak}** → **{streak}** days\n"
                response += f"Highest streak: **{old_highest}** → **{new_highest}** days\n"
                response += f"Restore points: **{restore_points}**/2\n"

                if streak == 0:
                    response += "\n🔄 Daily cooldown cleared - they can use `daily` command immediately."
                else:
                    response += f"\n🔄 Daily cooldown cleared - they can use `daily` command to get day {streak + 1} rewards."

                await ctx.send(response)

        except Exception as e:
            import traceback
            error_message = f"Error occurred: {e}\n"
            error_message += traceback.format_exc()
            await ctx.send(f"❌ An error occurred while setting the streak:\n```\n{error_message}\n```")
            print(error_message)

    def read_challenges_from_file(self, filename):
        with open(filename, 'r') as file:
            challenges = file.readlines()
        return [challenge.strip() for challenge in challenges]  # Strip newline characters

    def format_monsters(self, monsters):
        formatted = ""
        for level, monster_list in sorted(monsters.items()):
            # Assign a color based on the level
            if level == 1:
                level_color = "🟢"
            elif level == 2:
                level_color = "🟡"
            elif level == 3:
                level_color = "🔴"
            elif level == 4:
                level_color = "🔵"
            else:
                level_color = "⚪"

            # Add level heading
            formatted += f"**{level_color} Level {level}**\n\n"

            for monster in monster_list:
                name = monster["name"]
                url = monster.get("url", "")
                if url:
                    monster_entry = f"- **{name}**\n  [![{name}]({url})]({url})\n\n"
                else:
                    monster_entry = f"- **{name}**\n  *No image available.*\n\n"
                formatted += monster_entry

            # Add a separator between levels
            formatted += "---\n\n"
        return formatted

    # Function to split the formatted text into chunks <=2000 characters
    def split_into_chunks(self, text, max_length=2000):
        chunks = []
        while len(text) > max_length:
            # Find the last newline within the limit
            split_pos = text.rfind('\n', 0, max_length)
            if split_pos == -1:
                # If no newline found, force split
                split_pos = max_length
            chunks.append(text[:split_pos])
            text = text[split_pos:].lstrip('\n')
        chunks.append(text)
        return chunks


    @commands.hybrid_command()
    async def choose(self, ctx, *, args: str):
        """
        Chooses between two options provided by the user.
        Handles input like "$choose heads tails" or "$choose heads or tails".
        """
        # Split the input by "or" or whitespace
        if " or " in args:
            options = [option.strip() for option in args.split(" or ")]
        else:
            options = args.split()

        # Ensure there are exactly two options
        if len(options) != 2:
            await ctx.send("Please provide exactly two options, separated by a space or 'or'.")
            return

        # Randomly select between the two options
        result = random.choice(options)
        await ctx.send(f"{result}")




    @is_gm()
    @commands.hybrid_command(hidden=True, name="challenges")
    @locale_doc
    async def send_challenges(self, ctx):
        try:
            challenges = self.read_challenges_from_file("challenges.txt")  # Read challenges from file
            selected_challenges = random.sample(challenges, 6)  # Select 6 random challenges
            response = "\n".join(selected_challenges)

            await ctx.author.send(f"Here are 6 random challenges for you:\n{response}")
        except Exception as e:
            await ctx.send(e)


    @user_cooldown(5)
    @commands.hybrid_command(brief="Hug someone with a cute GIF!")
    @locale_doc
    async def hug(self, ctx, user: discord.Member):
        _(
            """`<user>` - The member to hug.

        Send a virtual hug to another member! This command fetches a random hug GIF and displays it along with a message mentioning both you and the user.

        Usage:
          `$hug @username`

        Note:
        - You cannot hug yourself.
        - This command has a cooldown of 5 seconds."""
        )

        try:

            if user == ctx.author:
                await ctx.send("That's.. uh.. that's pretty sad.")
                return

            async with aiohttp.ClientSession() as session:
                # Replace 'YOUR_GIPHY_API_KEY' with your Giphy API key
                async with session.get(
                        f"https://api.giphy.com/v1/gifs/search?api_key=YOURKEY&q=hug&limit=20&rating=pg") as r:
                    if r.status == 200:
                        data = await r.json()
                        gif_url = random.choice(data['data'])['images']['original']['url']
                    else:
                        gif_url = None

            if gif_url:
                embed = discord.Embed(description=f"{ctx.author.mention} hugs {user.mention} 🤗")
                embed.set_image(url=gif_url)
                await ctx.send(embed=embed)
            else:
                await ctx.send("Couldn't fetch a hug GIF at the moment!")
        except Exception as e:
            await ctx.send(e)


    @user_cooldown(5)
    @commands.hybrid_command(brief="Kiss someone with a cute GIF!")
    @locale_doc
    async def kiss(self, ctx, user: discord.Member):
        _(
            """`<user>` - The member to kiss.

        Give someone a virtual kiss! This command fetches a random kiss GIF and displays it along with a message mentioning both you and the user.

        Usage:
          `$kiss @username`

        Note:
        - You cannot kiss yourself.
        - This command has a cooldown of 5 seconds."""
        )

        try:
            if user == ctx.author:
                await ctx.send("Kissing yourself? That's interesting...")
                return

            async with aiohttp.ClientSession() as session:
                async with session.get(
                        f"https://api.giphy.com/v1/gifs/search?api_key=YOURKEY&q=kiss&limit=20&rating=pg") as r:
                    if r.status == 200:
                        data = await r.json()
                        gif_url = random.choice(data['data'])['images']['original']['url']
                    else:
                        gif_url = None

            if gif_url:
                embed = discord.Embed(description=f"{ctx.author.mention} kisses {user.mention} 😘")
                embed.set_image(url=gif_url)
                await ctx.send(embed=embed)
            else:
                await ctx.send("Couldn't fetch a kiss GIF at the moment!")
        except Exception as e:
            await ctx.send(e)


    @user_cooldown(5)
    @commands.hybrid_command(brief="Bonk someone with a funny GIF!")
    @locale_doc
    async def bonk(self, ctx, user: discord.Member):
        _(
            """`<user>` - The member to bonk.

        Give someone a virtual bonk! This command displays a random bonk GIF from a predefined list, along with a message mentioning both you and the user.

        Usage:
          `$bonk @username`

        Note:
        - You cannot bonk yourself.
        - This command has a cooldown of 5 seconds."""
        )

        try:
            if user == ctx.author:
                await ctx.send("Bonking yourself? That must hurt...")
                return

            # List of predefined bonk GIFs
            gif_urls = [
                "https://media0.giphy.com/media/HmgnQQjEMbMz0oLpqn/giphy.gif?cid=49e4d7b557ooon5bnhtiz3j1n2gp2og8b0qronyhl9njvkcg&ep=v1_gifs_search&rid=giphy.gif&ct=g",
                "https://media1.tenor.com/m/oHjfWJorYB8AAAAd/bonk.gif",
                "https://media1.tenor.com/m/tfgcD7qcy1cAAAAd/bonk.gif",
                "https://media1.tenor.com/m/wHRCrBup3JgAAAAd/bonk-piggies.gif",
                "https://media1.tenor.com/m/kWNnhhNd5WQAAAAd/bonk.gif",
                "https://media1.tenor.com/m/yGk_Te0sywsAAAAd/spongebob-meme-bonk.gif"
            ]

            # Randomly select a GIF from the list
            gif_url = random.choice(gif_urls)

            # Create and send the embed message
            embed = discord.Embed(description=f"{ctx.author.mention} bonks {user.mention} 🔨")
            embed.set_image(url=gif_url)
            await ctx.send(embed=embed)
        except Exception as e:
            await ctx.send(f"An error occurred: {e}")

    @user_cooldown(5)
    @commands.hybrid_command(brief="Pat someone with a cute GIF!")
    @locale_doc
    async def pat(self, ctx, user: discord.Member):
        _(
            """`<user>` - The member to pat.

        Pat someone on the head virtually! This command fetches a random pat GIF and displays it along with a message mentioning both you and the user.

        Usage:
          `$pat @username`

        Note:
        - You cannot pat yourself.
        - This command has a cooldown of 5 seconds."""
        )

        try:
            if user == ctx.author:
                await ctx.send("Self-pats are good for self-care!")
                return

            async with aiohttp.ClientSession() as session:
                async with session.get(
                        f"https://api.giphy.com/v1/gifs/search?api_key=YOURKEY&q=pat&limit=20&rating=pg") as r:
                    if r.status == 200:
                        data = await r.json()
                        gif_url = random.choice(data['data'])['images']['original']['url']
                    else:
                        gif_url = None

            if gif_url:
                embed = discord.Embed(description=f"{ctx.author.mention} pats {user.mention} 😊")
                embed.set_image(url=gif_url)
                await ctx.send(embed=embed)
            else:
                await ctx.send("Couldn't fetch a pat GIF at the moment!")
        except Exception as e:
            await ctx.send(e)


    @user_cooldown(5)
    @commands.hybrid_command(brief="Slap someone with a GIF!")
    @locale_doc
    async def slap(self, ctx, user: discord.Member):
        _(
            """`<user>` - The member to slap.

        Slap another member virtually! This command fetches a random slap GIF and displays it along with a message mentioning both you and the user.

        Usage:
          `$slap @username`

        Note:
        - You cannot slap yourself.
        - This command has a cooldown of 5 seconds."""
        )

        try:
            if user == ctx.author:
                await ctx.send("Slapping yourself? That doesn't seem healthy!")
                return

            async with aiohttp.ClientSession() as session:
                async with session.get(
                        f"https://api.giphy.com/v1/gifs/search?api_key=YOURKEY&q=slap&limit=20&rating=pg") as r:
                    if r.status == 200:
                        data = await r.json()
                        gif_url = random.choice(data['data'])['images']['original']['url']
                    else:
                        gif_url = None

            if gif_url:
                embed = discord.Embed(description=f"{ctx.author.mention} slaps {user.mention} 😡")
                embed.set_image(url=gif_url)
                await ctx.send(embed=embed)
            else:
                await ctx.send("Couldn't fetch a slap GIF at the moment!")
        except Exception as e:
            await ctx.send(e)


    @user_cooldown(5)
    @commands.hybrid_command(brief="Give someone a high five!")
    @locale_doc
    async def highfive(self, ctx, user: discord.Member):
        _(
            """`<user>` - The member to high-five.

        Give a virtual high-five to another member! This command fetches a random high-five GIF and displays it along with a message mentioning both you and the user.

        Usage:
          `$highfive @username`

        Note:
        - You cannot high-five yourself.
        - This command has a cooldown of 5 seconds."""
        )

        try:
            if user == ctx.author:
                await ctx.send("You can't high-five yourself... or can you?")
                return

            async with aiohttp.ClientSession() as session:
                async with session.get(
                        f"https://api.giphy.com/v1/gifs/search?api_key=YOURKEY&q=highfive&limit=20&rating=pg") as r:
                    if r.status == 200:
                        data = await r.json()
                        gif_url = random.choice(data['data'])['images']['original']['url']
                    else:
                        gif_url = None

            if gif_url:
                embed = discord.Embed(description=f"{ctx.author.mention} gives {user.mention} a high five! 🙌")
                embed.set_image(url=gif_url)
                await ctx.send(embed=embed)
            else:
                await ctx.send("Couldn't fetch a high five GIF at the moment!")
        except Exception as e:
            await ctx.send(e)


    @user_cooldown(5)
    @commands.hybrid_command(brief="Wave at someone with a GIF!")
    @locale_doc
    async def wave(self, ctx, user: discord.Member):
        _(
            """`<user>` - The member to wave at.

        Wave at someone with a friendly GIF! This command fetches a random wave GIF and displays it along with a message mentioning both you and the user.

        Usage:
          `$wave @username`

        Note:
        - You cannot wave at yourself.
        - This command has a cooldown of 5 seconds."""
        )

        try:
            if user == ctx.author:
                await ctx.send("Waving at yourself? That's a bit awkward...")
                return

            async with aiohttp.ClientSession() as session:
                async with session.get(
                        f"https://api.giphy.com/v1/gifs/search?api_key=YOURKEY&q=wave&limit=20&rating=pg") as r:
                    if r.status == 200:
                        data = await r.json()
                        gif_url = random.choice(data['data'])['images']['original']['url']
                    else:
                        gif_url = None

            if gif_url:
                embed = discord.Embed(description=f"{ctx.author.mention} waves at {user.mention} 👋")
                embed.set_image(url=gif_url)
                await ctx.send(embed=embed)
            else:
                await ctx.send("Couldn't fetch a wave GIF at the moment!")
        except Exception as e:
            await ctx.send(e)


    @user_cooldown(5)
    @commands.hybrid_command(brief="Cuddle someone with a cute GIF!")
    @locale_doc
    async def cuddle(self, ctx, user: discord.Member):
        _(
            """`<user>` - The member to cuddle.

        Give someone a warm virtual cuddle! This command fetches a random cuddle GIF and displays it along with a message mentioning both you and the user.

        Usage:
          `$cuddle @username`

        Note:
        - You cannot cuddle yourself.
        - This command has a cooldown of 5 seconds."""
        )

        try:
            if user == ctx.author:
                await ctx.send("Cuddling yourself? A warm blanket works too!")
                return

            async with aiohttp.ClientSession() as session:
                async with session.get(
                        f"https://api.giphy.com/v1/gifs/search?api_key=YOURKEY&q=cuddle&limit=20&rating=pg") as r:
                    if r.status == 200:
                        data = await r.json()
                        gif_url = random.choice(data['data'])['images']['original']['url']
                    else:
                        gif_url = None

            if gif_url:
                embed = discord.Embed(description=f"{ctx.author.mention} cuddles {user.mention} 🤗")
                embed.set_image(url=gif_url)
                await ctx.send(embed=embed)
            else:
                await ctx.send("Couldn't fetch a cuddle GIF at the moment!")
        except Exception as e:
            await ctx.send(e)


    @user_cooldown(5)
    @commands.hybrid_command(brief="Poke someone gently with a cute GIF!")
    @locale_doc
    async def poke(self, ctx, user: discord.Member):
        _(
            """`<user>` - The member to poke.

        Gently poke another member! This command fetches a random poke GIF and displays it along with a message mentioning both you and the user.

        Usage:
          `$poke @username`

        Note:
        - You cannot poke yourself.
        - This command has a cooldown of 5 seconds."""
        )

        try:
            if user == ctx.author:
                await ctx.send("Poking yourself? That’s odd!")
                return

            async with aiohttp.ClientSession() as session:
                async with session.get(
                        f"https://api.giphy.com/v1/gifs/search?api_key=YOURKEY&q=poke&limit=20&rating=pg") as r:
                    if r.status == 200:
                        data = await r.json()
                        gif_url = random.choice(data['data'])['images']['original']['url']
                    else:
                        gif_url = None

            if gif_url:
                embed = discord.Embed(description=f"{ctx.author.mention} pokes {user.mention} 👈")
                embed.set_image(url=gif_url)
                await ctx.send(embed=embed)
            else:
                await ctx.send("Couldn't fetch a poke GIF at the moment!")
        except Exception as e:
            await ctx.send(e)


    @user_cooldown(5)
    @commands.hybrid_command(brief="Bite someone gently with a playful GIF!")
    @locale_doc
    async def bite(self, ctx, user: discord.Member):
        _(
            """`<user>` - The member to bite playfully.

        Playfully bite someone! This command fetches a random bite GIF and displays it along with a message mentioning both you and the user.

        Usage:
          `$bite @username`

        Note:
        - You cannot bite yourself.
        - This command has a cooldown of 5 seconds."""
        )

        try:
            if user == ctx.author:
                await ctx.send("Biting yourself? Ouch!")
                return

            async with aiohttp.ClientSession() as session:
                async with session.get(
                        f"https://api.giphy.com/v1/gifs/search?api_key=YOURKEY&q=bite&limit=20&rating=pg") as r:
                    if r.status == 200:
                        data = await r.json()
                        gif_url = random.choice(data['data'])['images']['original']['url']
                    else:
                        gif_url = None

            if gif_url:
                embed = discord.Embed(description=f"{ctx.author.mention} bites {user.mention} playfully 😋")
                embed.set_image(url=gif_url)
                await ctx.send(embed=embed)
            else:
                await ctx.send("Couldn't fetch a bite GIF at the moment!")
        except Exception as e:
            await ctx.send(e)


    @user_cooldown(5)
    @commands.hybrid_command(brief="Tickle someone with a GIF!")
    @locale_doc
    async def tickle(self, ctx, user: discord.Member):
        _(
            """`<user>` - The member to tickle.

        Tickle someone and make them laugh! This command fetches a random tickle GIF and displays it along with a message mentioning both you and the user.

        Usage:
          `$tickle @username`

        Note:
        - You cannot tickle yourself.
        - This command has a cooldown of 5 seconds."""
        )

        try:
            if user == ctx.author:
                await ctx.send("Tickling yourself? Doesn't quite work!")
                return

            async with aiohttp.ClientSession() as session:
                async with session.get(
                        f"https://api.giphy.com/v1/gifs/search?api_key=YOURKEY&q=tickle&limit=20&rating=pg") as r:
                    if r.status == 200:
                        data = await r.json()
                        gif_url = random.choice(data['data'])['images']['original']['url']
                    else:
                        gif_url = None

            if gif_url:
                embed = discord.Embed(description=f"{ctx.author.mention} tickles {user.mention} 😂")
                embed.set_image(url=gif_url)
                await ctx.send(embed=embed)
            else:
                await ctx.send("Couldn't fetch a tickle GIF at the moment!")
        except Exception as e:
            await ctx.send(e)


    @user_cooldown(5)
    @commands.hybrid_command(brief="Nuzzle someone affectionately!")
    @locale_doc
    async def nuzzle(self, ctx, user: discord.Member):
        _(
            """`<user>` - The member to nuzzle.

        Affectionately nuzzle someone! This command fetches a random nuzzle GIF and displays it along with a message mentioning both you and the user.

        Usage:
          `$nuzzle @username`

        Note:
        - You cannot nuzzle yourself.
        - This command has a cooldown of 5 seconds."""
        )

        try:
            if user == ctx.author:
                await ctx.send("Nuzzling yourself? That's an interesting form of self-love!")
                return

            async with aiohttp.ClientSession() as session:
                async with session.get(
                        f"https://api.giphy.com/v1/gifs/search?api_key=YOURKEY&q=nuzzle&limit=20&rating=pg") as r:
                    if r.status == 200:
                        data = await r.json()
                        gif_url = random.choice(data['data'])['images']['original']['url']
                    else:
                        gif_url = None

            if gif_url:
                embed = discord.Embed(description=f"{ctx.author.mention} nuzzles {user.mention} 😽")
                embed.set_image(url=gif_url)
                await ctx.send(embed=embed)
            else:
                await ctx.send("Couldn't fetch a nuzzle GIF at the moment!")
        except Exception as e:
            await ctx.send(e)


    @user_cooldown(5)
    @commands.hybrid_command(brief="Lick someone!")
    @locale_doc
    async def lick(self, ctx, user: discord.Member):
        _(
            """`<user>` - The member to lick.

        Lick someone playfully! This command fetches a random lick GIF and displays it along with a message mentioning both you and the user.

        Usage:
          `$lick @username`

        Note:
        - You cannot lick yourself.
        - This command has a cooldown of 5 seconds."""
        )

        try:
            if user == ctx.author:
                await ctx.send("Licking yourself? Weirdo.")
                return

            async with aiohttp.ClientSession() as session:
                async with session.get(
                        f"https://api.giphy.com/v1/gifs/search?api_key=YOURKEY&q=lick-face&limit=20&rating=pg") as r:
                    if r.status == 200:
                        data = await r.json()
                        gif_url = random.choice(data['data'])['images']['original']['url']
                    else:
                        gif_url = None

            if gif_url:
                embed = discord.Embed(description=f"{ctx.author.mention} licks {user.mention} ewww.")
                embed.set_image(url=gif_url)
                await ctx.send(embed=embed)
            else:
                await ctx.send("Couldn't fetch a lick GIF at the moment!")
        except Exception as e:
            await ctx.send(e)


    @user_cooldown(5)
    @commands.hybrid_command(brief="Punch someone with a GIF!")
    @locale_doc
    async def punch(self, ctx, user: discord.Member):
        _(
            """`<user>` - The member to punch.

        Deliver a virtual punch to someone! This command fetches a random punch GIF and displays it along with a message mentioning both you and the user.

        Usage:
          `$punch @username`

        Note:
        - You cannot punch yourself.
        - This command has a cooldown of 5 seconds."""
        )

        try:
            if user == ctx.author:
                await ctx.send("Punching yourself? That's not a good idea!")
                return

            async with aiohttp.ClientSession() as session:
                async with session.get(
                        f"https://api.giphy.com/v1/gifs/search?api_key=YOURKEY&q=punch&limit=20&rating=pg") as r:
                    if r.status == 200:
                        data = await r.json()
                        gif_url = random.choice(data['data'])['images']['original']['url']
                    else:
                        gif_url = None

            if gif_url:
                embed = discord.Embed(description=f"{ctx.author.mention} punches {user.mention}! 👊")
                embed.set_image(url=gif_url)
                await ctx.send(embed=embed)
            else:
                await ctx.send("Couldn't fetch a punch GIF at the moment!")
        except Exception as e:
            await ctx.send(e)


    @has_char()
    @commands.hybrid_command(brief=_("Roll"))
    @locale_doc
    async def roll(self, ctx):
        _(
            """Send a rolling bread (🥖) emoji.

        Use this command to get a random roll (of bread)!

        Usage:
          `$roll`

        Note:
        - This is a fun command with no cooldown."""
        )

        await ctx.send("🥖")





    @commands.hybrid_command(aliases=["donate"], brief=_("Support the bot financially"))
    @locale_doc
    async def patreon(self, ctx):
        _(
            """View the Patreon page of the bot. The different tiers will grant different rewards.
            View `{prefix}help module Patreon` to find the different commands.

            Thank you for supporting Fable RPG!"""
        )
        guild_count = sum(
            await self.bot.cogs["Sharding"].handler(
                "guild_count", self.bot.cluster_count
            )
        )
        await ctx.send(
            _(
                """\
This bot has its own patreon page.

**Why should I donate?**
This bot is currently on {guild_count} servers, and it is growing fast.
Hosting this bot for all users is not easy and costs a lot of money.
If you want to continue using the bot or just help us, please donate a small amount.
Even $1 can help us.
**Thank you!**

<https://patreon.com/FableRPG>"""
            ).format(guild_count=guild_count)
        )


    @commands.hybrid_command(
        aliases=["license"], brief=_("Shows the source code and license.")
    )
    @locale_doc
    async def source(self, ctx):
        _(
            """Shows Idles GitLab page and license alongside our own source as required by AGPLv3 Licensing."""
        )
        await ctx.send("IdleRPG - AGPLv3+\nhttps://git.travitia.xyz/Kenvyra/IdleRPG")

        await ctx.send("Fable - AGPLv3+\nhttps://github.com/prototypeX37/FableRPG-")


    @commands.hybrid_command(brief=_("Invite the bot to your server."))
    @locale_doc
    async def invite(self, ctx):
        _(
            """Invite the bot to your server.

            Use this https://discord.com/api/oauth2/authorize?client_id=1136590782183264308&permissions
            =8945276537921&scope=bot"""
        )
        await ctx.send(
            _(
                "You are running version **{version}** by The Fable"
                "Developers.\nInvite me! https://discord.com/api/oauth2/authorize?client_id=1136590782183264308"
                "&permissions=8945276537921&scope=bot"
            ).format(version=self.bot.version)
        )




    async def paginate_embeds(self, ctx, pages, timeout=60):
        """
        Given a list of discord.Embed objects, paginate them in the channel with
        reaction controls: ◀️, ❌, ▶️

        :param ctx: The command context
        :param pages: A list of discord.Embed objects
        :param timeout: Timeout in seconds for reaction waiting
        """
        if not pages:
            await ctx.send("No pages to display.")
            return

        current_page = 0
        message = await ctx.send(embed=pages[current_page])

        # Add reactions for navigation
        reactions = ["◀️", "❌", "▶️"]
        for r in reactions:
            await message.add_reaction(r)

        def check(reaction, user):
            return (
                    user == ctx.author
                    and reaction.message.id == message.id
                    and str(reaction.emoji) in reactions
            )

        while True:
            try:
                reaction, user = await ctx.bot.wait_for(
                    "reaction_add",
                    timeout=timeout,
                    check=check
                )
            except:
                # Timed out, remove the reactions and break
                try:
                    await message.clear_reactions()
                except discord.Forbidden:
                    pass
                break

            # Remove the user's reaction
            try:
                await message.remove_reaction(reaction.emoji, user)
            except discord.Forbidden:
                pass

            if str(reaction.emoji) == "◀️":
                # Go to previous page
                current_page = (current_page - 1) % len(pages)
                await message.edit(embed=pages[current_page])
            elif str(reaction.emoji) == "▶️":
                # Go to next page
                current_page = (current_page + 1) % len(pages)
                await message.edit(embed=pages[current_page])
            elif str(reaction.emoji) == "❌":
                # Close the pagination
                await message.delete()
                break

    @commands.command()
    async def allcommands(self, ctx):
        """Displays all available commands categorized by their cogs, excluding @is_gm() commands."""

        loading_message = await ctx.send("Please wait while I gather that information for you...")

        try:
            cog_commands = {}
            # Gather all commands, excluding hidden commands and those with @is_gm() checks
            for cmd in self.bot.commands:
                if cmd.hidden:
                    continue
                # Exclude commands that have a `is_gm` check
                if any(pred.__name__ == "is_gm" for pred in cmd.checks):
                    continue

                cog_name = cmd.cog_name or "No Category"
                # Optionally exclude a "GameMaster" cog entirely
                if cog_name == "GameMaster":
                    continue

                if cog_name not in cog_commands:
                    cog_commands[cog_name] = []

                cog_commands[cog_name].append(cmd.name)

            # Create pages (embeds)
            pages = []
            prefix = "$"  # change as needed

            for cog_name, commands_list in cog_commands.items():
                embed = discord.Embed(
                    title=f"{cog_name} Commands",
                    description=f"Commands in **{cog_name}** category.",
                    color=discord.Color.blue()
                )

                cmd_text = "\n".join(f"`{prefix}{cmd_name}`" for cmd_name in commands_list)
                embed.add_field(name="Commands", value=cmd_text, inline=False)

                pages.append(embed)

            # If we never found any commands
            if not pages:
                return await loading_message.edit(content="No commands found.")

            # Remove "Please wait..."
            await loading_message.delete()

            # Create the PaginatorView
            view = PaginatorView(ctx, pages, start_page=0, timeout=60)
            # Send the first page with the view
            message = await ctx.send(embed=pages[0], view=view)
            # Store reference to the message in the view (so we can edit on timeout)
            view.message = message

        except Exception as e:
            await ctx.send(e)


    @commands.hybrid_command(brief=_("Shows statistics about the bot"))
    @locale_doc
    async def stats(self, ctx):
        _(
            """Show detailed stats about the bot, including hardware usage, software statistics, and in-game metrics."""
        )
        async with self.bot.pool.acquire() as conn:
            characters = await conn.fetchval("SELECT COUNT(*) FROM profile;")
            items = await conn.fetchval("SELECT COUNT(*) FROM allitems;")
            pg_version = conn.get_server_version()
        pg_version = f"{pg_version.major}.{pg_version.micro} {pg_version.releaselevel}"
        d0 = self.bot.user.created_at
        d1 = datetime.datetime.now(datetime.timezone.utc)
        delta = d1 - d0
        myhours = delta.days * 24  # Convert days to hours (accurate)
        uptime_days = delta.days
        uptime_hours = delta.seconds // 3600
        uptime_minutes = (delta.seconds % 3600) // 60
        
        # System usage stats
        try:
            import psutil
            cpu_percent = psutil.cpu_percent(interval=1)
            
            # Get CPU name
            try:
                with open('/proc/cpuinfo', 'r') as f:
                    cpuinfo = f.read()
                cpu_model = re.search(r'model name\s+:\s+(.*)', cpuinfo).group(1)
            except:
                # Fallback if we can't read cpuinfo
                cpu_model = "Unknown CPU"
            
            memory = psutil.virtual_memory()
            memory_percent = memory.percent
            memory_used_gb = memory.used / (1024 ** 3)  # Convert to GB
            memory_total_gb = memory.total / (1024 ** 3)  # Convert to GB
            
            
            boot_time = datetime.datetime.fromtimestamp(psutil.boot_time())
            system_uptime = datetime.datetime.now() - boot_time
            system_uptime_days = system_uptime.days
            system_uptime_hours = system_uptime.seconds // 3600
            system_uptime_minutes = (system_uptime.seconds % 3600) // 60
        except:
            # Fallback if psutil fails or is not available
            cpu_percent = 0
            cpu_model = "Unknown CPU"
            memory_percent = 0
            memory_used_gb = 0
            memory_total_gb = 0
            system_uptime_days = 0
            system_uptime_hours = 0
            system_uptime_minutes = 0
            
        sysinfo = distro.linux_distribution()
        if self.bot.owner_ids:
            owner = nice_join(
                [str(await self.bot.get_user_global(u)) for u in self.bot.owner_ids]
            )
        else:
            owner = str(await self.bot.get_user_global(self.bot.owner_id))
        guild_count = sum(
            await self.bot.cogs["Sharding"].handler(
                "guild_count", self.bot.cluster_count
            )
        )
        compiler = re.search(r".*\[(.*)\]", sys.version)[1]

        embed = discord.Embed(
            title=_("FableRPG Statistics"),
            colour=0xB8BBFF,
            url=self.bot.BASE_URL,
            description=_(
                "Official Support Server Invite: https://discord.com/fablerpg"
            ),
        )
        embed.set_thumbnail(url=self.bot.user.display_avatar.url)
        embed.set_footer(
            text=f"Fable {self.bot.version} | By {owner}",
            icon_url=self.bot.user.display_avatar.url,
        )
        
        # System stats with usage percentages
        embed.add_field(
            name=_("System Resources"),
            value=_(
                """\
    CPU: **{cpu_model}**
    CPU Usage: **{cpu_percent}%**
    Memory: **{memory_used:.2f} GB / {memory_total:.2f} GB ({memory_percent}%)**
    System Uptime: **{sys_days}d {sys_hours}h {sys_minutes}m**"""
            ).format(
                cpu_model=cpu_model,
                cpu_percent=cpu_percent,
                memory_used=memory_used_gb,
                memory_total=memory_total_gb,
                memory_percent=memory_percent,
                sys_days=system_uptime_days,
                sys_hours=system_uptime_hours,
                sys_minutes=system_uptime_minutes,
            ),
            inline=False,
        )
        
        # Hosting stats
        embed.add_field(
            name=_("Hosting Statistics"),
            value=_(
                """\
    Python Version: **{python}** 
    discord.py Version: **{dpy}**
    Compiler: **{compiler}**
    Operating System: **{osname} {osversion}**
    Kernel Version: **{kernel}**
    PostgreSQL Version: **{pg_version}**
    Redis Version: **{redis_version}**"""
            ).format(
                python=platform.python_version(),
                dpy=pkg.get_distribution("discord.py").version,
                compiler=compiler,
                osname=sysinfo[0].title(),
                osversion=sysinfo[1],
                kernel=os.uname().release if os.name == "posix" else "NT",
                pg_version=pg_version,
                redis_version=self.bot.redis_version,
            ),
            inline=False,
        )
        
        # Bot stats without artificially inflated numbers
        embed.add_field(
            name=_("Bot Statistics"),
            value=_(
                """\
    Code Lines: **{lines:,}**
    Shards: **{shards}**
    Servers: **{guild_count:,}**
    Bot Uptime: **{bot_days}d {bot_hours}h {bot_minutes}m**
    Total Runtime: **{total_hours:,} hours**"""
            ).format(
                lines=self.bot.linecount,
                shards=self.bot.shard_count,
                guild_count=guild_count,  # Removed artificial inflation
                bot_days=uptime_days,
                bot_hours=uptime_hours,
                bot_minutes=uptime_minutes,
                total_hours=int(myhours),
            ),
            inline=False,
        )
        
        # Game stats without artificially inflated numbers
        embed.add_field(
            name=_("Game Statistics"),
            value=_(
                """\
    Characters: **{characters:,}**
    Items: **{items:,}**
    Items per Character: **{items_per_char:.2f}**"""
            ).format(
                characters=characters,  # Removed artificial inflation
                items=items,  # Removed artificial inflation
                items_per_char=(items / characters) if characters > 0 else 0,
            ),
            inline=False,
        )
        await ctx.send(embed=embed)


    @commands.hybrid_command(brief=_("View the uptime"))
    @locale_doc
    async def uptime(self, ctx):
        _("""Shows how long the bot has been connected to Discord.""")
        await ctx.send(
            _("I am online for **{time}**.").format(
                time=str(self.bot.uptime).split(".")[0]
            )
        )

    @commands.hybrid_command()
    @locale_doc
    async def cookie(self, ctx, target_member: discord.Member):
        _(
            """`<user>` - The member to give a cookie to.

        Give a virtual cookie to another member!

        Usage:
          `$cookie @username`

        Note:
        - This is a fun command to share some sweetness."""
        )

        await ctx.send(
            f"**{target_member.display_name}**, you've been given a cookie by **{ctx.author.display_name}**. 🍪")


    @commands.hybrid_command()
    @locale_doc
    async def ice(self, ctx, target_member: discord.Member):
        _(
            """`<user>` - The member to give ice cream to.

        Share some virtual ice cream with someone!

        Usage:
          `$ice @username`

        Note:
        - This is a fun command to share some treats."""
        )

        await ctx.send(
            f"{target_member.mention}, here is your ice: 🍨!")


    @commands.hybrid_command(name='wipe', help='Clear your conversation history with the bot.')
    @locale_doc
    async def clear_memory(self, ctx):
        _(
            """Clear your conversation history with the AI assistant.

        Use this command to reset your conversation with the bot.

        Usage:
          `$wipe`

        Note:
        - This will delete your current conversation history with the `talk` command."""
        )

        user_id = ctx.author.id
        if user_id in self.conversations:
            del self.conversations[user_id]
            await ctx.send("Your conversation history has been cleared!")
        else:
            await ctx.send("You don't have any conversation history to clear.")

    def split_message(self, content, limit=1909):
        """Split a message into chunks under a specified limit without breaking words."""
        chunks = []
        while len(content) > limit:
            split_index = content.rfind(' ', 0, limit)
            if split_index == -1:
                split_index = limit
            chunk = content[:split_index]
            chunks.append(chunk)
            content = content[split_index:].strip()  # Remove leading space for next chunk
        chunks.append(content)
        return chunks

    async def get_gpt_response_async(self, conversation_history):
        url = "https://api.openai.com/v1/chat/completions"
        OPENAI_KEY = self.bot.config.external.openai
        headers = {
            "Authorization": f"Bearer {OPENAI_KEY}",
            "Content-Type": "application/json"
        }
        data = {
            "model": "gpt-4-turbo",
            "messages": conversation_history
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=headers, json=data) as response:
                    response_data = await response.json()
                    return response_data['choices'][0]['message']['content'].strip()
        except aiohttp.ClientError as e:
            return f"Error connecting to OpenAI: {str(e)}"
        except Exception as e:
            return f"Unexpected error! Is the pipeline server running? {e}"

    async def get_gpt_response_async2(self, conversation_history):
        url = "https://api.openai.com/v1/chat/completions"
        OPENAI_KEY = self.bot.config.external.openai
        headers = {
            "Authorization": f"Bearer {OPENAI_KEY}",
            "Content-Type": "application/json"
        }
        data = {
            "model": "o1-preview",
            "messages": conversation_history
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=headers, json=data) as response:
                    response_data = await response.json()
                    return response_data['choices'][0]['message']['content'].strip()
        except aiohttp.ClientError as e:
            return f"Error connecting to OpenAI: {str(e)}"
        except Exception as e:
            return f"Unexpected error! Is the pipeline server running? {e}"


    @commands.hybrid_command(
        aliases=["pages", "about"], brief=_("Info about the bot and related sites")
    )
    @locale_doc
    async def web(self, ctx):
        _("""About the bot and our websites.""")
        await ctx.send(
            _(
                # xgettext: no-python-format
                """\
**FableRPG** is Discord's most advanced medieval RPG bot.
We aim to provide the perfect experience at RPG in Discord with minimum effort for the user.

We are not collecting any data apart from your character information and our transaction logs.
The bot is 100% free to use and open source.
This bot is developed by people who love to code for a good cause and improving your gameplay experience.

**Links**
<https://git.travitia.xyz/Kenvyra/IdleRPG> - Source Code (IdleRPG)
<https://git.travitia.xyz/prototypeX37/FableRPG-> - Source Code (FableRPG)
<https://git.travitia.xyz> - GitLab (Public)
<https://wiki.fablerpg.xyz> - FableRPG wiki
<https://api.fablerpg.xyz> - Our API
<https://discord.com/terms> - Discord's ToS
<https://www.ncpgambling.org/help-treatment/national-helpline-1-800-522-4700/> - Gambling Helpline"""
            )
        )


    @commands.hybrid_command(brief=_("Show the rules again"))
    @locale_doc
    async def rules(self, ctx):
        _(
            """Shows the rules you consent to when creating a character. Don't forget them!"""
        )
        await ctx.send(
            _(
                """\
1) Only up to two characters per individual
2) No abusing or benefiting from bugs or exploits
3) Be friendly and kind to other players
4) Trading in-game content for anything outside of the game is prohibited
5) Giving or selling renamed items is forbidden

FableRPG is a global bot, your characters are valid everywhere"""
            )
        )


async def setup(bot):
    await bot.add_cog(Miscellaneous(bot))
    await bot.tree.sync()

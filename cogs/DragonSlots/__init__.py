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
along with this program.  If not, see .
"""

import asyncio
import datetime
import string
from collections import Counter

import discord
from discord.ext import commands, tasks
import random
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import io
import requests
from cogs.shard_communication import user_on_cooldown as user_cooldown
from utils.checks import has_char, is_gm
from utils.i18n import locale_doc, _


class Slots(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        ids_section = getattr(self.bot.config, "ids", None)
        dragonslot_ids = getattr(ids_section, "dragonslots", {}) if ids_section else {}
        if not isinstance(dragonslot_ids, dict):
            dragonslot_ids = {}
        self.captcha_lock_channel_id = dragonslot_ids.get("captcha_lock_channel_id")

        # -------Health Init------------
        self.player_hp = 100
        self.dragon_hp = 150

        # -------Health Events Player------------
        self.Heal = 15
        self.Shield = 0
        self.Trip = -5

        # -------Health Events Dragon------------
        self.Attack = 5
        self.Magic = 10

        # -------Health Events DragonATK------------
        self.DragonAttack = 5

        self.timeout_duration = 600  # 10 minutes

        # Create a dictionary to store user timeouts
        self.user_timeouts = {}

        # Start a task to check for timeouts
        self.check_timeouts.start()

        self.captcha_lock = {}

        # Dictionary to track each user's output mode (False = graphic, True = text-only)
        self.text_mode = {}

        self.logger = 0

    @has_char()
    @user_cooldown(6)
    @commands.group()
    @locale_doc
    async def slots(self, ctx):
        _(
            """Play the slot machine game.

            Use this command to play the slot machine.

            Subcommands:
            - `seats`: View slot machine seat information.
            - `takeseat `: Take a seat in the slot machine game.
            - `leaveseat`: Leave your current seat.
            - `toggleslottxt`: Toggle text-only mode for slot machine output.
            """
        )

        if ctx.invoked_subcommand is None:
            updated_dragon = 1
            updated_player = 1
            try:
                async with self.bot.pool.acquire() as connection:
                    result = await connection.fetchrow("SELECT seat FROM dragonslots WHERE occupant = $1", ctx.author.id)
                    if result:
                        seat = result['seat']
                        await self.update_last_activity(ctx.author.id)
                    else:
                        return await ctx.send("You are not in a slot seat.")
            except Exception as e:
                return await ctx.send(f"An error occurred: {e}")

            if self.is_user_captcha_locked(ctx.author.id):
                await ctx.send("You are captcha locked.")
                return

            verifycheck = random.randint(1, 100)
            if verifycheck <= 1:
                try:
                    captcha_text = self.generate_distorted_captcha()
                    self.captcha_lock[ctx.author.id] = captcha_text
                    await ctx.send(f"{ctx.author.mention} Enter the CAPTCHA Text below. You have 60 seconds",
                                   file=discord.File('captcha.png'))
                    try:
                        await self.bot.wait_for(
                            'message',
                            check=lambda msg: msg.author == ctx.author and msg.content.lower() == captcha_text.lower(),
                            timeout=60
                        )
                    except asyncio.TimeoutError:
                        try:
                            async with self.bot.pool.acquire() as connection:
                                seat_info = await connection.fetchrow("SELECT * FROM dragonslots WHERE occupant = $1",
                                                                      ctx.author.id)
                                if seat_info:
                                    seat_number = seat_info['seat']
                                    await connection.execute(
                                        "UPDATE dragonslots SET occupant = NULL, last_activity = NULL WHERE seat = $1",
                                        seat_number)
                                    await self.send_locked_message(ctx.author)
                                    await ctx.send("You are now CAPTCHA Locked. Use `$unlock` to unlock the CAPTCHA.")
                                else:
                                    await self.send_locked_message(ctx.author)
                        except Exception as e:
                            await ctx.send(f"An error occurred: {e}")
                        return
                    await ctx.send("CAPTCHA Verification Successful")
                    del self.captcha_lock[ctx.author.id]
                except Exception as e:
                    await ctx.send(str(e))

            # Check user balance
            try:
                async with self.bot.pool.acquire() as connection:
                    result = await connection.fetch('SELECT money FROM profile WHERE "user" = $1', ctx.author.id)
                    if result:
                        money = result[0]['money']
                    else:
                        return await ctx.send("User not found in the database.")
            except Exception as e:
                return await ctx.send(f"An error occurred: {e}")

            if money < 1500:
                return await ctx.send("You are too poor.")
            else:
                try:
                    async with self.bot.pool.acquire() as connection:
                        await connection.execute('UPDATE profile SET money = money - $1 WHERE "user" = $2', 1500,
                                                 ctx.author.id)

                        await connection.execute('UPDATE dragonslots SET jackpot = jackpot + $1 WHERE seat = $2', 250,
                                                 seat)
                        jackpot_result = await connection.fetchval('SELECT jackpot FROM dragonslots WHERE seat = $1',
                                                                     seat)
                except Exception as e:
                    return await ctx.send(f"An error occurred while deducting money: {e}")

            # ----- Emoji slots with adjusted probabilities -----
            fruit_values = {
                "🐉": 1000,
                "🍒": 1000,
                "🍎": 2000,
                "🍊": 2500,
                "🍏": 3000,
                "🍓": 4000,
                "🍍": 6500
            }
            emojis = list(fruit_values.keys())
            weights = [1, 4, 3, 2, 1, 1, 1]
            slot_results = random.choices(emojis, weights=weights, k=3)
            fruit_counts = Counter(slot_results)
            dragon_count = slot_results.count("🐉")

            if len(set(slot_results)) == 1:
                total_reward = 4 * fruit_values[slot_results[0]]
            elif len(set(slot_results)) == 2 and any(count == 2 for count in fruit_counts.values()):
                total_reward = 2 * sum(fruit_values[fruit] for fruit, count in fruit_counts.items() if count == 2)
            else:
                total_reward = 0

            # ----- Risk Event: 10% chance to modify the reward -----
            risk_message = ""
            bonus = 0
            penalty = 0
            if random.randint(1, 100) <= 10:
                bonus_type = random.choice(["bonus", "penalty"])
                if bonus_type == "bonus":
                    bonus = random.randint(500, 2000)
                    total_reward += bonus
                    risk_message = f"Risk event triggered! You got a bonus of ${bonus}."
                else:
                    penalty = random.randint(100, 2000)
                    async with self.bot.pool.acquire() as connection:
                        jackpot_result = await connection.fetchval('SELECT jackpot FROM dragonslots WHERE seat = $1',
                                                                   seat)
                        if jackpot_result < penalty:
                            await connection.execute('UPDATE dragonslots SET jackpot = $1 WHERE seat = $2',
                                                     0, seat)
                        else:
                            await connection.execute('UPDATE dragonslots SET jackpot = jackpot - $1 WHERE seat = $2',
                                                     penalty, seat)



                    risk_message = f"Risk event triggered! You suffered a penalty of ${penalty}."

            # ----- Update user money and jackpot -----
            try:
                async with self.bot.pool.acquire() as connection:
                    if total_reward != 0:
                        if total_reward > 0:
                            await connection.execute('UPDATE profile SET money = money + $1 WHERE "user" = $2',
                                                     total_reward, ctx.author.id)
                        else:
                            await connection.execute('UPDATE profile SET money = money - $1 WHERE "user" = $2',
                                                     abs(total_reward), ctx.author.id)

                        await connection.execute('UPDATE dragonslots SET jackpot = jackpot + $1 WHERE seat = $2',
                                                 250, seat)
                        jackpot_result = await connection.fetchval('SELECT jackpot FROM dragonslots WHERE seat = $1', seat)
                    else:
                        jackpot_result = await connection.fetchval('SELECT jackpot FROM dragonslots WHERE seat = $1', seat)
            except Exception as e:
                return await ctx.send(f"An error occurred while updating money: {e}")

            # Build output message
            slot_output = (
                f"Slot Machine Result\n"
                f"Slot 1: {slot_results[0]}\n"
                f"Slot 2: {slot_results[1]}\n"
                f"Slot 3: {slot_results[2]}\n"
                f"Base Reward: ${total_reward - (bonus if bonus else penalty)}\n"
                f"{risk_message if risk_message else 'Risk event: None'}\n"
                f"Jackpot: ${jackpot_result}\n"
                f"Occupant: {ctx.author.display_name}"
            )

            if self.text_mode.get(ctx.author.id, False):
                await ctx.send(f"```\n{slot_output}\n```")
            else:
                embed = discord.Embed(title="Slot Machine Result", color=discord.Color.blurple())
                embed.add_field(name="Slot 1", value=slot_results[0], inline=True)
                embed.add_field(name="Slot 2", value=slot_results[1], inline=True)
                embed.add_field(name="Slot 3", value=slot_results[2], inline=True)
                embed.add_field(name="**Reward**", value=f"${total_reward}", inline=False)
                embed.add_field(name="Risk Event", value=risk_message if risk_message else "None", inline=False)
                embed.add_field(name="Jackpot", value=f"${jackpot_result}", inline=False)
                embed.add_field(name="Occupant", value=f"{ctx.author.mention}", inline=False)
                await ctx.send(embed=embed)

            # ----- Dragon event if a dragon emoji was rolled -----
            if dragon_count > 0:
                if dragon_count == 1:
                    await ctx.send(f"{ctx.author.display_name}, you rolled a dragon! Initiating attack sequence...")
                else:
                    await ctx.send(f"You rolled {dragon_count} dragons! Initiating {dragon_count} attack sequence{'s' if dragon_count > 1 else ''}...")
                # Process each dragon roll
                for i in range(1, dragon_count + 1):
                    await asyncio.sleep(1)
                    background_url = 'https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_Picsart_24-04-13_11-36-22-184.jpg'
                    bg_image = Image.open(requests.get(background_url, stream=True).raw)
                    font_path = 'EightBitDragon-anqx.ttf'
                    dragonHP_font = ImageFont.truetype(font_path, size=38)
                    HeroHP_font = ImageFont.truetype(font_path, size=33)
                    draw = ImageDraw.Draw(bg_image)
                    random_number = random.randint(1, 5)

                    if random_number == 1:
                        async with self.bot.pool.acquire() as connection:
                            await connection.execute(
                                'UPDATE dragonslots SET dragon = dragon - $1, player = player - $2 WHERE seat = $3',
                                5, 5, seat)
                            updated_values = await connection.fetchrow('SELECT dragon, player FROM dragonslots WHERE seat = $1',
                                                                       seat)
                            updated_dragon = updated_values['dragon']
                            updated_player = updated_values['player']
                        await ctx.send(f"{ctx.author.display_name}, you attacked the dragon for **5 DMG!** It now has {updated_dragon}! You took **5 DMG** and now have {updated_player}.")
                        await asyncio.sleep(1)

                    if random_number == 2:
                        await ctx.send(f"{ctx.author.display_name}, you defended yourself. You took 0 damage!")
                        async with self.bot.pool.acquire() as connection:
                            updated_values = await connection.fetchrow('SELECT dragon, player FROM dragonslots WHERE seat = $1',
                                                                       seat)
                            updated_dragon = updated_values['dragon']
                            updated_player = updated_values['player']
                        await asyncio.sleep(1)

                    if random_number == 3:
                        triphurt = random.randint(1, 10)
                        if triphurt <= 5:
                            async with self.bot.pool.acquire() as connection:
                                await connection.execute('UPDATE dragonslots SET player = player - $1 WHERE seat = $2',
                                                         5, seat)
                                updated_values = await connection.fetchrow('SELECT dragon, player FROM dragonslots WHERE seat = $1',
                                                                           seat)
                                updated_dragon = updated_values['dragon']
                                updated_player = updated_values['player']
                            await ctx.send(f"{ctx.author.display_name}, you tripped and took **5 DMG!** Your HP is now {updated_player}!")
                            await asyncio.sleep(1)
                        else:
                            async with self.bot.pool.acquire() as connection:
                                await connection.execute('UPDATE dragonslots SET player = player - $1 WHERE seat = $2',
                                                         10, seat)
                                updated_values = await connection.fetchrow('SELECT dragon, player FROM dragonslots WHERE seat = $1',
                                                                           seat)
                                updated_dragon = updated_values['dragon']
                                updated_player = updated_values['player']
                            await ctx.send(f"Oops, {ctx.author.display_name}! You stumbled and took **10 DMG**. Your HP is now {updated_player}!")
                            await asyncio.sleep(1)

                    if random_number == 4:
                        async with self.bot.pool.acquire() as connection:
                            await connection.execute('UPDATE dragonslots SET dragon = dragon - $1, player = player - $2 WHERE seat = $3',
                                                     10, 5, seat)
                            updated_values = await connection.fetchrow('SELECT dragon, player FROM dragonslots WHERE seat = $1',
                                                                       seat)
                            updated_dragon = updated_values['dragon']
                            updated_player = updated_values['player']
                        await ctx.send(f"{ctx.author.display_name}, you cast a spell! The dragon took **10 DMG** and you took **5 DMG**. Dragon HP: {updated_dragon}; Your HP: {updated_player}.")
                        await asyncio.sleep(1)

                    if random_number == 5:
                        async with self.bot.pool.acquire() as connection:
                            await connection.execute('UPDATE dragonslots SET player = player - $1 WHERE seat = $2',
                                                     5, seat)
                            updated_values = await connection.fetchrow('SELECT dragon, player FROM dragonslots WHERE seat = $1',
                                                                       seat)
                            updated_dragon = updated_values['dragon']
                            updated_player = updated_values['player']
                        healthluck = random.randint(1, 11)
                        if healthluck <= 5:
                            if updated_player < 85:
                                async with self.bot.pool.acquire() as connection:
                                    await connection.execute('UPDATE dragonslots SET player = player + $1 WHERE seat = $2',
                                                             10, seat)
                                    updated_values = await connection.fetchrow('SELECT dragon, player FROM dragonslots WHERE seat = $1',
                                                                               seat)
                                    updated_player = updated_values['player']
                                await ctx.send(f"{ctx.author.display_name}, you healed for **10 HP!** Your HP is now {updated_player}.")
                                await asyncio.sleep(1)
                            else:
                                async with self.bot.pool.acquire() as connection:
                                    await connection.execute('UPDATE dragonslots SET player = $1 WHERE seat = $2',
                                                             95, seat)
                                    updated_values = await connection.fetchrow('SELECT dragon, player FROM dragonslots WHERE seat = $1',
                                                                               seat)
                                    updated_player = updated_values['player']
                                await ctx.send(f"{ctx.author.display_name}, you healed to **100 HP!** Your HP is now {updated_player}.")
                                await asyncio.sleep(1)
                        else:
                            if updated_player < 85:
                                async with self.bot.pool.acquire() as connection:
                                    await connection.execute('UPDATE dragonslots SET player = player + $1 WHERE seat = $2',
                                                             15, seat)
                                    updated_values = await connection.fetchrow('SELECT dragon, player FROM dragonslots WHERE seat = $1',
                                                                               seat)
                                    updated_player = updated_values['player']
                                await ctx.send(f"{ctx.author.display_name}, you healed for **15 HP!** Your HP is now {updated_player}.")
                                await asyncio.sleep(1)
                            else:
                                async with self.bot.pool.acquire() as connection:
                                    await connection.execute('UPDATE dragonslots SET player = $1 WHERE seat = $2',
                                                             95, seat)
                                    updated_values = await connection.fetchrow('SELECT dragon, player FROM dragonslots WHERE seat = $1',
                                                                               seat)
                                    updated_player = updated_values['player']
                                await ctx.send(f"{ctx.author.display_name}, you healed to **100 HP!** Your HP is now {updated_player}.")
                                await asyncio.sleep(1)

                    if updated_player < 0:
                        updated_player = 0
                    if updated_dragon < 0:
                        updated_dragon = 0

                    # Draw HP values on image
                    draw.text((80, 391), f"{updated_player}", font=HeroHP_font, fill="cyan")
                    draw.text((673, 10), f"{updated_dragon}", font=dragonHP_font, fill="white")

                    # Run special event (send updated image or text summary)
                    await self.run_special_event(ctx, bg_image, draw, i, random_number, seat)


    async def run_special_event(self, ctx, bg_image, draw, image_index, random_number, seat):
        """
        Draws a rounded rectangle on the image based on a preset location.
        If the user is in text mode, a text summary is sent instead of an image.
        """

        locations = [
            [(228, 369), (354, 402)],
            [(228, 402), (354, 437)],
            [(425, 369), (500, 402)],
            [(425, 402), (590, 437)],
            [(615, 369), (710, 402)],
        ]
        rectangle_location = locations[random_number - 1]
        corner_radius = 20
        draw.rounded_rectangle(rectangle_location, corner_radius, outline="red")

        if self.text_mode.get(ctx.author.id, False):
            pass
        else:
            image_buffer = io.BytesIO()
            bg_image.save(image_buffer, format="PNG")
            image_buffer.seek(0)
            await ctx.send(file=discord.File(image_buffer, filename=f"modified_image_{image_index}.png"))

        # Post-event: Check and update statuses if dragon or player has reached 0 HP.
        async with self.bot.pool.acquire() as connection:
            dragon_hp = await connection.fetchval('SELECT dragon FROM dragonslots WHERE seat = $1', seat)
            player_hp = await connection.fetchval('SELECT player FROM dragonslots WHERE seat = $1', seat)

            if dragon_hp <= 0:
                jackpot_value = await connection.fetchval('SELECT jackpot FROM dragonslots WHERE seat = $1', seat)
                await connection.execute('UPDATE profile SET money = money + $1 WHERE "user" = $2', jackpot_value, ctx.author.id)
                new_jackpot = random.randint(10000, 50000)
                await connection.execute('UPDATE dragonslots SET dragon = 125, player = 100, jackpot = $1 WHERE seat = $2', new_jackpot, seat)
                await ctx.send(f"💎💎💎JACKPOT!💎💎💎 {ctx.author.mention}, you defeated the dragon and earned a jackpot of **${jackpot_value}**!")
                return

            if player_hp <= 0:
                await connection.execute('UPDATE dragonslots SET dragon = 125, player = 100 WHERE seat = $1', seat)
                await ctx.send(f"💀💀💀DEFEATED!💀💀💀 {ctx.author.display_name}, you were defeated by the dragon!")

    @has_char()
    @slots.command()
    @locale_doc
    async def seats(self, ctx):
        _(
            """View information about slot machine seats.

            Displays the status of each seat, including occupant, dragon HP, player HP, and the current jackpot.
            """
        )
        try:
            embed = discord.Embed(title="Seat Information", color=discord.Color.blurple())
            async with self.bot.pool.acquire() as connection:
                for seat_number in range(1, 9):
                    seat_info = await connection.fetchrow("SELECT * FROM dragonslots WHERE seat = $1", seat_number)
                    if seat_info:
                        occupant_id = seat_info['occupant']
                        occupant_name = "Seat free" if occupant_id is None else await self.bot.fetch_user(occupant_id)
                        dragon_hp = seat_info['dragon']
                        player_hp = seat_info['player']
                        jackpot = seat_info['jackpot']
                        if occupant_name == "Seat free":
                            embed.add_field(
                                name=f"Seat #{seat_number}",
                                value=f"Occupant: Seat free \nDragon HP: {dragon_hp} 🐉 \nPlayer HP: {player_hp} 👤 \nJackpot: {jackpot} 💰",
                                inline=False
                            )
                        else:
                            embed.add_field(
                                name=f"Seat #{seat_number}",
                                value=f"Occupant: {occupant_name.display_name}\nDragon HP: {dragon_hp} 🐉 \nPlayer HP: {player_hp} 👤 \nJackpot: {jackpot} 💰",
                                inline=False
                            )
                await ctx.send(embed=embed)
        except Exception as e:
            await ctx.send(f"An error occurred: {e}")

    @has_char()
    @slots.command(name="text")
    @locale_doc
    async def toggleslottxt(self, ctx):
        _(
            """Toggle text-only mode for the slot machine game.

            When enabled, the slot machine will display results in plain text (no generated images).
            """
        )
        try:
            current = self.text_mode.get(ctx.author.id, False)
            self.text_mode[ctx.author.id] = not current
            mode = "Text-Only" if self.text_mode[ctx.author.id] else "Graphic"
            await ctx.send(f"{ctx.author.mention} Slot machine mode toggled. You are now in **{mode}** mode.")
        except Exception as e:
            await ctx.send(e)

    def cog_unload(self):
        self.check_timeouts.cancel()

    @tasks.loop(seconds=60)
    async def check_timeouts(self):
        try:
            now = datetime.datetime.utcnow()
            async with self.bot.pool.acquire() as connection:
                for seat_info in await connection.fetch("SELECT seat, occupant, last_activity FROM dragonslots"):
                    seat_number = seat_info['seat']
                    occupant_id = seat_info['occupant']
                    last_activity = seat_info['last_activity']
                    if occupant_id and (now - last_activity).total_seconds() > self.timeout_duration:
                        await connection.execute("UPDATE dragonslots SET occupant = NULL, last_activity = NULL WHERE seat = $1", seat_number)
                        user = await self.bot.fetch_user(occupant_id)
                        if user:
                            try:
                                await user.send(f"{user.mention} You have been automatically removed from seat #{seat_number} due to inactivity.")
                            except discord.Forbidden:
                                print(f"Could not send message to {user}. They might have DMs disabled.")
                            except Exception as e:
                                print(f"An error occurred: {e}")
        except Exception as e:

            raise

    async def update_last_activity(self, occupant_id):
        async with self.bot.pool.acquire() as connection:
            await connection.execute("UPDATE dragonslots SET last_activity = $1 WHERE occupant = $2",
                                     datetime.datetime.utcnow(), occupant_id)

    @slots.command()
    @user_cooldown(300)
    @has_char()
    @locale_doc
    async def takeseat(self, ctx, seat_number: int):
        _(
            """Take a seat in the slot machine game.

             - The number of the seat you wish to occupy (1-8).

            Occupy an available seat to participate in the slot machine game. You must leave your current seat before taking a new one.
            """
        )
        if ctx.author.id in self.captcha_lock:
            await ctx.send("You are currently locked by CAPTCHA verification.")
            self.bot.reset_cooldown(ctx)
            return
        try:
            async with self.bot.pool.acquire() as connection:
                current_seat = await connection.fetchrow("SELECT * FROM dragonslots WHERE occupant = $1", ctx.author.id)
                if current_seat:
                    current_seat_number = current_seat['seat']
                    await ctx.send(f"{ctx.author.display_name}, you are already occupying seat #{current_seat_number}. Please leave that seat before taking a new one.")
                    self.bot.reset_cooldown(ctx)
                    return
                else:
                    seat_info = await connection.fetchrow("SELECT * FROM dragonslots WHERE seat = $1", seat_number)
                    if seat_info:
                        occupant_id = seat_info['occupant']
                        if occupant_id is None:
                            await connection.execute("UPDATE dragonslots SET occupant = $1, last_activity = $2 WHERE seat = $3",
                                                     ctx.author.id, datetime.datetime.utcnow(), seat_number)
                            await ctx.send(f"{ctx.author.mention} has taken seat #{seat_number}! Will be kicked after 10 minutes of inactivity.")
                            await self.update_last_activity(ctx.author.id)
                        else:
                            occupant_name = await self.bot.fetch_user(occupant_id)
                            await ctx.send(f"Sorry, seat #{seat_number} is already taken by {occupant_name.display_name}.")
                            self.bot.reset_cooldown(ctx)
                    else:
                        await ctx.send(f"Seat #{seat_number} does not exist.")
                        self.bot.reset_cooldown(ctx)
        except Exception as e:
            await ctx.send(f"An error occurred: {e}")

    @is_gm()
    @commands.command(hidden=True)
    @locale_doc
    async def gmjpforce(self, ctx):
        _(
            """Forcefully increase the jackpot for all slot seats.

            (Game Master only)

            This command increases the jackpot value for all seats, simulating player contributions.
            """
        )
        try:
            async with self.bot.pool.acquire() as connection:
                seat_numbers = await connection.fetch('SELECT seat FROM dragonslots')
                for seat_info in seat_numbers:
                    seat_number = seat_info['seat']
                    occupied_seat = await connection.fetchval('SELECT seat FROM dragonslots WHERE seat = $1 AND occupant IS NOT NULL', seat_number)
                    random_value = random.randint(10000, 12000)
                    await connection.execute('UPDATE dragonslots SET jackpot = jackpot + $1 WHERE seat = $2', random_value, seat_number)
        except Exception as e:
            await ctx.send(e)

    async def increase_jackpot_periodically(self, ctx):
        while True:
            try:
                async with self.bot.pool.acquire() as connection:
                    seat_numbers = await connection.fetch('SELECT seat FROM dragonslots')
                    for seat_info in seat_numbers:
                        seat_number = seat_info['seat']
                        occupied_seat = await connection.fetchval('SELECT seat FROM dragonslots WHERE seat = $1 AND occupant IS NOT NULL', seat_number)
                        if not occupied_seat:
                            random_value = random.randint(10000, 12000)
                            await connection.execute('UPDATE dragonslots SET jackpot = jackpot + $1 WHERE seat = $2', random_value, seat_number)
                await asyncio.sleep(21600)
            except Exception as e:
                await ctx.send(f"An error occurred while increasing jackpot: {e}")
            await asyncio.sleep(3600)

    @is_gm()
    @commands.command(hidden=True)
    @locale_doc
    async def gmjptimer(self, ctx):
        _(
            """Start the periodic increase of jackpot.

            (Game Master only)

            Initiates a background task that periodically increases the jackpot for unoccupied seats.
            """
        )
        self.bot.loop.create_task(self.increase_jackpot_periodically(ctx))
        await ctx.send("Jackpot increase has been started.")

    @has_char()
    @slots.command()
    @locale_doc
    async def leaveseat(self, ctx):
        _(
            """Leave your current seat in the slot machine game.

            Use this command to vacate your seat, allowing others to occupy it.
            """
        )
        try:
            captcha_text = self.generate_distorted_captcha()
            await ctx.send(f"{ctx.author.mention} to prevent botting, enter the CAPTCHA Text as printed below. You have 60 seconds",
                           file=discord.File('captcha.png'))
            self.captcha_lock[ctx.author.id] = captcha_text
            try:
                await self.bot.wait_for(
                    'message',
                    check=lambda msg: msg.author == ctx.author and msg.content.lower() == captcha_text.lower(),
                    timeout=60
                )
            except asyncio.TimeoutError:
                try:
                    async with self.bot.pool.acquire() as connection:
                        await self.send_locked_message(ctx.author)
                except Exception as e:
                    await ctx.send(f"An error occurred: {e}")
                return
            await ctx.send("CAPTCHA Verification Successful")
            del self.captcha_lock[ctx.author.id]
        except Exception as e:
            await ctx.send(f"An error occurred: {e}")

        try:
            async with self.bot.pool.acquire() as connection:
                seat_info = await connection.fetchrow("SELECT * FROM dragonslots WHERE occupant = $1", ctx.author.id)
                if seat_info:
                    seat_number = seat_info['seat']
                    await connection.execute("UPDATE dragonslots SET occupant = NULL, last_activity = NULL WHERE seat = $1", seat_number)
                    await ctx.send(f"{ctx.author.mention} has left seat #{seat_number}!")
                else:
                    await ctx.send(f"{ctx.author.display_name}, you are not currently occupying any seat.")
        except Exception as e:
            await ctx.send(f"An error occurred: {e}")

    def add_to_captcha_lock(self, user_id, captcha_text):
        self.captcha_lock[user_id] = captcha_text

    def is_user_captcha_locked(self, user_id):
        return user_id in self.captcha_lock

    async def send_locked_message(self, user):
        locked_channel = (
            self.bot.get_channel(self.captcha_lock_channel_id)
            if self.captcha_lock_channel_id
            else None
        )
        if locked_channel:
            await locked_channel.send(f"{user.name}#{user.discriminator} failed the CAPTCHA and is now locked.")

    async def init_database(self):
        async with self.bot.pool.acquire() as connection:
            await connection.execute("DELETE FROM dragonslots")
            for seat_number in range(1, 9):
                dragon_hp = 125
                player_hp = 100
                jackpot = random.randint(10000, 12000)
                await connection.execute("INSERT INTO dragonslots(seat, dragon, player, jackpot) VALUES($1, $2, $3, $4)",
                                         seat_number, dragon_hp, player_hp, jackpot)

    @is_gm()
    @commands.command(hidden=True)
    @locale_doc
    async def gmdragonslotreset(self, ctx):
        _(
            """Reset the dragon slots to their initial state.

            (Game Master only)

            Resets all dragon slots, clearing occupants and restoring default HP and jackpot values.
            """
        )
        try:
            await self.init_database()
            await ctx.send("Dragon slots have been reset successfully!")
        except Exception as e:
            await ctx.send(f"An error occurred: {e}")

    def generate_distorted_captcha(self):
        captcha_text = ''.join(random.choices(string.ascii_letters + string.digits, k=6))
        captcha_text = captcha_text.replace('l', 'L')
        width, height = 300, 100
        background_color = 'grey'
        image = Image.new('RGB', (width, height), background_color)
        draw = ImageDraw.Draw(image)
        font_path = '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'
        font_size = 40
        font = ImageFont.truetype(font_path, font_size)
        letter_colors = ['red', 'green', 'blue', 'purple', 'orange']
        outline_thickness = 1

        for _ in range(1000):
            x = random.randint(0, width - 1)
            y = random.randint(0, height - 1)
            color = random.choice(letter_colors)
            draw.point((x, y), fill=color)

        for _ in range(50):
            x = random.uniform(0, width)
            y = random.uniform(0, height)
            shape_type = random.choice(['ellipse', 'line'])
            shape_color = random.choice(letter_colors)
            size = random.randint(2, 5)
            self.draw_random_shape(draw, x, y, shape_type, shape_color, size, outline_thickness)

        for i, char in enumerate(captcha_text):
            x = i * width / 6
            y = random.uniform(0, height / 2)
            color = random.choice(letter_colors)
            draw.text((x, y), char, font=font, fill=color)

        image = image.filter(ImageFilter.GaussianBlur(1))
        image = image.filter(ImageFilter.CONTOUR)
        image.save('captcha.png')
        return captcha_text

    def draw_random_shape(self, draw, x, y, shape_type, shape_color, size, outline_thickness):
        if shape_type == 'ellipse':
            draw.ellipse((x, y, x + size, y + size), outline=shape_color, width=outline_thickness)
        elif shape_type == 'line':
            x2, y2 = x + random.randint(10, 30), y + random.randint(10, 30)
            draw.line([(x, y), (x2, y2)], fill=shape_color, width=outline_thickness)

    @is_gm()
    @commands.command(hidden=True)
    async def captcha(self, ctx):
        _(
            """Generate a CAPTCHA image.

            (Game Master only)

            Creates and displays a CAPTCHA image for testing purposes.
            """
        )
        try:
            captcha_text = self.generate_distorted_captcha()
            await ctx.send(f"Enter the CAPTCHA Text below. You have 60 seconds", file=discord.File('captcha.png'))
        except Exception as e:
            await ctx.send(str(e))

    @is_gm()
    @commands.command(hidden=True)
    @locale_doc
    async def gmunlock(self, ctx, DiscordID: int):
        _(
            """Unlock a user from CAPTCHA lock.

             - The Discord ID of the user to unlock.

            (Game Master only)

            Removes a user from the CAPTCHA lock, allowing them to use commands again.
            """
        )
        DiscordID_str = str(DiscordID).strip()
        if DiscordID_str in map(str, self.captcha_lock.keys()):
            user = self.captcha_lock[DiscordID]
            await ctx.send(f"You have unlocked {user} ({DiscordID}).")
            del self.captcha_lock[DiscordID]
        else:
            await ctx.send("User not found.")

    @commands.command(hidden=True)
    @has_char()
    @locale_doc
    async def unlock(self, ctx):
        _(
            """Unlock yourself from CAPTCHA lock by completing a CAPTCHA.

            If you are locked due to failed CAPTCHA attempts, use this command to verify and unlock yourself.
            """
        )
        if ctx.author.id not in self.captcha_lock:
            await ctx.send("You are not currently locked by CAPTCHA verification.")
            return
        captcha_text = self.generate_distorted_captcha()
        try:
            captcha_text = self.generate_distorted_captcha()
            await ctx.send(f"{ctx.author.mention} to prevent botting, enter the CAPTCHA Text as printed below. You have 60 seconds",
                           file=discord.File('captcha.png'))
            self.captcha_lock[ctx.author.id] = captcha_text
            try:
                await self.bot.wait_for(
                    'message',
                    check=lambda msg: msg.author == ctx.author and msg.content.lower() == captcha_text.lower(),
                    timeout=60
                )
            except asyncio.TimeoutError:
                try:
                    async with self.bot.pool.acquire() as connection:
                        await self.send_locked_message(ctx.author)
                except Exception as e:
                    await ctx.send(f"An error occurred: {e}")
                return
            await ctx.send("CAPTCHA Verification Successful")
            del self.captcha_lock[ctx.author.id]
        except Exception as e:
            await ctx.send(f"An error occurred: {e}")


async def setup(bot):
    await bot.add_cog(Slots(bot))

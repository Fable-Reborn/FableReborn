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
import random as randomm

import asyncpg
import discord
from discord.ext import commands, tasks
from discord.ui.button import Button
from discord.enums import ButtonStyle

from classes import logger
from classes.converters import IntGreaterThan
from cogs.shard_communication import user_on_cooldown as user_cooldown
from utils import random
from utils.checks import has_char, has_money, is_gm
from utils.i18n import _, locale_doc
from utils.joins import SingleJoinView


class PetSelect(discord.ui.Select):
    def __init__(self, pets):
        # Create options for each pet
        options = []
        for i, pet in enumerate(pets):
            # Create stage icon based on growth stage
            if pet['growth_stage'] == "baby":
                stage_emoji = "🍼"
            elif pet['growth_stage'] == "juvenile":
                stage_emoji = "🌱"
            elif pet['growth_stage'] == "young":
                stage_emoji = "🐕"
            else:
                stage_emoji = "🦁"
                
            options.append(
                discord.SelectOption(
                    label=f"{pet['name']} (ID: {pet['id']})",
                    description=f"{pet['element']} | IV: {pet['IV']}% | {pet['growth_stage'].capitalize()}",
                    value=str(i),  # Store the index in the pets list as value
                    emoji=stage_emoji
                )
            )
        
        # Initialize the select with a placeholder and the options
        super().__init__(placeholder="Select a pet to view...", min_values=1, max_values=1, options=options)
    
    async def callback(self, interaction: discord.Interaction):
        # The callback is handled in the view class
        view = self.view
        if interaction.user.id != view.author.id:
            return await interaction.response.send_message("This is not your pet list.", ephemeral=True)
        
        view.index = int(self.values[0])
        await view.send_page(interaction)

class PetPaginator(discord.ui.View):
    def __init__(self, pets, author):
        super().__init__(timeout=60)
        self.pets = pets
        self.author = author
        self.index = 0
        self.message = None  # To store the message reference
        
        # Add the dropdown menu if there are pets
        if pets:
            self.add_item(PetSelect(pets))
            
    async def on_timeout(self):
        """Auto-close the pets box when the view times out"""
        if self.message:
            try:
                await self.message.delete()
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                # Message might have been deleted already or we lack permissions
                pass

    def get_embed(self):
        pet = self.pets[self.index]

        growth_stages = {
            1: {"stage": "baby", "growth_time": 2, "stat_multiplier": 0.25, "hunger_modifier": 1.0},
            2: {"stage": "juvenile", "growth_time": 2, "stat_multiplier": 0.50, "hunger_modifier": 0.8},
            3: {"stage": "young", "growth_time": 1, "stat_multiplier": 0.75, "hunger_modifier": 0.6},
            4: {"stage": "adult", "growth_time": None, "stat_multiplier": 1.0, "hunger_modifier": 0.0},
            # Self-sufficient
        }

        stage_data = growth_stages.get(pet["growth_index"], growth_stages[1])  # Default to 'baby' stage
        stat_multiplier = stage_data["stat_multiplier"]
        hp = round(pet["hp"])
        attack = round(pet["attack"] )
        defense = round(pet["defense"])

        # Calculate growth time left
        growth_time_left = None
        if pet["growth_stage"] != "adult":
            if pet["growth_time"]:
                time_left = pet["growth_time"] - datetime.datetime.utcnow()
                growth_time_left = str(time_left).split('.')[0] if time_left.total_seconds() > 0 else "Ready to grow!"

        petid = pet['id']
        iv = pet['IV']

        # Improved embed design
        if pet['growth_stage'] == "baby":
            stage_icon = "🍼"
        elif pet['growth_stage'] == "juvenile":
            stage_icon = "🌱"
        elif pet['growth_stage'] == "young":
            stage_icon = "🐕"
        else:
            stage_icon = "🦁"

        embed = discord.Embed(
            title=f"🐾 Your Pet: {pet['name']}",
            color=discord.Color.green(),
            description=f"**Stage:** {pet['growth_stage'].capitalize()} {stage_icon}\n**ID:** {petid}\n**Equipped:** {pet['equipped']}"
            if pet['growth_stage'] != "baby"
            else f"**Stage:** {pet['growth_stage'].capitalize()} {stage_icon}\n**ID:** {petid}\n**Equipped:** {pet['equipped']}"
        )

        embed.add_field(
            name="✨ **Stats**",
            value=(
                f"**IV** {iv}%\n"
                f"**HP:** {hp}\n"
                f"**Attack:** {attack}\n"
                f"**Defense:** {defense}"
            ),
            inline=False,
        )
        embed.add_field(
            name="🌟 **Details**",
            value=(
                f"**Element:** {pet['element']}\n"
                f"**Happiness:** {pet['happiness']}%\n"
                f"**Hunger:** {pet['hunger']}%"
            ),
            inline=False,
        )
        if growth_time_left:
            embed.add_field(
                name="⏳ **Growth Time Left**",
                value=f"{growth_time_left}",
                inline=False,
            )
        else:
            embed.add_field(
                name="🎉 **Growth**",
                value="Your pet is fully grown!",
                inline=False,
            )

        embed.set_footer(
            text=f"Viewing pet {self.index + 1} of {len(self.pets)} | Use the dropdown to navigate"
        )
        embed.set_image(url=pet["url"])

        return embed

    async def send_page(self, interaction: discord.Interaction):
        embed = self.get_embed()

        if self.message is None:
            self.message = interaction.message

        if interaction.response.is_done():
            await self.message.edit(embed=embed, view=self)
        else:
            await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Close", style=discord.ButtonStyle.red, row=1)
    async def close_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.author.id:
            return await interaction.response.send_message("This is not your pet list.", ephemeral=True)

        await interaction.message.delete()
        self.stop()


class SellConfirmationView(discord.ui.View):
    def __init__(self, initiator: discord.Member, receiver: discord.Member, price: int, timeout=120):
        super().__init__(timeout=timeout)
        self.initiator = initiator
        self.receiver = receiver
        self.price = price
        self.value = None  # Will store True (accepted) or False (declined)

    @discord.ui.button(label="Accept Sale", style=ButtonStyle.success, emoji="✅")
    async def accept(self, interaction: discord.Interaction, button: Button):
        if interaction.user != self.receiver:
            await interaction.response.send_message(
                "❌ You are not authorized to respond to this sale.", ephemeral=True
            )
            return
        self.value = True
        await interaction.response.send_message("✅ Sale accepted.", ephemeral=True)
        self.stop()

    @discord.ui.button(label="Decline Sale", style=ButtonStyle.danger, emoji="❌")
    async def decline(self, interaction: discord.Interaction, button: Button):
        if interaction.user != self.receiver:
            await interaction.response.send_message(
                "❌ You are not authorized to respond to this sale.", ephemeral=True
            )
            return
        self.value = False
        await interaction.response.send_message("❌ Sale declined.", ephemeral=True)
        self.stop()


class TradeConfirmationView(discord.ui.View):
    def __init__(self, initiator: discord.User, receiver: discord.User, timeout=120):
        super().__init__(timeout=timeout)
        self.initiator = initiator
        self.receiver = receiver
        self.value = None  # Will store True (accepted) or False (declined)

    @discord.ui.button(label="Accept Trade", style=ButtonStyle.success, emoji="✅")
    async def accept(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id != self.receiver.id:
            await interaction.response.send_message("❌ You are not authorized to respond to this trade.", ephemeral=True)
            return
        self.value = True
        await interaction.response.send_message("✅ Trade accepted.", ephemeral=True)
        self.stop()

    @discord.ui.button(label="Decline Trade", style=ButtonStyle.danger, emoji="❌")
    async def decline(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id != self.receiver.id:
            await interaction.response.send_message("❌ You are not authorized to respond to this trade.", ephemeral=True)
            return
        self.value = False
        await interaction.response.send_message("❌ Trade declined.", ephemeral=True)
        self.stop()


class Pets(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        if not self.check_egg_hatches.is_running():
            self.check_egg_hatches.start()
        if not self.check_pet_growth.is_running():
            self.check_pet_growth.start()
            
        self.emoji_to_element = {
            "<:f_corruption:1170192253256466492>": "Corrupted",
            "<:f_water:1170191321571545150>": "Water",
            "<:f_electric:1170191219926777936>": "Electric",
            "<:f_light:1170191258795376771>": "Light",
            "<:f_dark:1170191180164771920>": "Dark",
            "<:f_nature:1170191149802213526>": "Wind",
            "<:f_earth:1170191288361033806>": "Nature",
            "<:f_fire:1170192046632468564>": "Fire"
        }

    # Command to use the paginator
    @commands.group(invoke_without_command=True)
    async def pets(self, ctx):
        try:
            await self.check_pet(ctx.author.id)
        except Exception as e:
            if ctx.author.id == 295173706496475136:
                await ctx.send(e)
        async with self.bot.pool.acquire() as conn:
            pets = await conn.fetch("SELECT * FROM monster_pets WHERE user_id = $1;", ctx.author.id)
            if not pets:
                await ctx.send("You don't have any pets.")
                return

        view = PetPaginator(pets, ctx.author)
        embed = view.get_embed()
        view.message = await ctx.send(embed=embed, view=view)

    @user_cooldown(600)
    @pets.command(brief="Trade your pet or egg with another user's pet or egg")
    @has_char()  # Assuming this is a custom check
    async def trade(self, ctx,
                    your_type: str, your_item_id: int,
                    their_type: str, their_item_id: int):
        # Normalize type inputs
        your_type = your_type.lower()
        their_type = their_type.lower()

        valid_types = ['pet', 'egg']
        if your_type not in valid_types or their_type not in valid_types:
            await ctx.send("❌ Invalid type specified. Use `pet` or `egg`.")
            await self.bot.reset_cooldown(ctx)
            return

        async with self.bot.pool.acquire() as conn:
            # Fetch your item
            if your_type == 'pet':
                your_item = await conn.fetchrow(
                    "SELECT * FROM monster_pets WHERE user_id = $1 AND id = $2;",
                    ctx.author.id,
                    your_item_id
                )
                your_table = 'monster_pets'
            else:  # egg
                your_item = await conn.fetchrow(
                    "SELECT * FROM monster_eggs WHERE user_id = $1 AND id = $2;",
                    ctx.author.id,
                    your_item_id
                )
                your_table = 'monster_eggs'

            if not your_item:
                await ctx.send(f"❌ You don't have a {your_type} with ID `{your_item_id}`.")
                await self.bot.reset_cooldown(ctx)
                return

            # Fetch their item
            if their_type == 'pet':
                their_item = await conn.fetchrow(
                    "SELECT * FROM monster_pets WHERE id = $1;",
                    their_item_id
                )
                their_table = 'monster_pets'
            else:  # egg
                their_item = await conn.fetchrow(
                    "SELECT * FROM monster_eggs WHERE id = $1;",
                    their_item_id
                )
                their_table = 'monster_eggs'

            if not their_item:
                await ctx.send(f"❌ No {their_type} found with ID `{their_item_id}`.")
                await self.bot.reset_cooldown(ctx)
                return

            their_user_id = their_item['user_id']
            if their_user_id == ctx.author.id:
                await ctx.send("❌ You cannot trade with your own items.")
                await self.bot.reset_cooldown(ctx)
                return

            # Fetch the receiver user
            their_user = self.bot.get_user(their_user_id)
            if not their_user:
                await ctx.send("❌ Could not find the user who owns the item.")
                await self.bot.reset_cooldown(ctx)
                return

            # Optionally, check if the receiver has not blocked the bot here
            # Example:
            # if your_user_has_blocked_bot or their_user_has_blocked_bot:
            #     await ctx.send("❌ Trade cannot be completed because one of the users has blocked the bot.")
            #     return

            # Create embeds for both items
            your_item_embed = self.create_item_embed(ctx.author, your_type, your_item, your_item_id)
            their_item_embed = self.create_item_embed(their_user, their_type, their_item, their_item_id)

            # Create the confirmation view
            view = TradeConfirmationView(ctx.author, their_user)

            # Send the trade proposal in the channel
            trade_embed = discord.Embed(
                title="🐾 Pet/Egg Trade Proposal",
                description=f"{ctx.author.mention} wants to trade their {your_type} with {their_user.mention}'s {their_type}.",
                color=discord.Color.blue()
            )
            if your_type == "pet":
                trade_embed.add_field(
                    name=f"{ctx.author.name}'s {your_type.capitalize()}",
                    value=f"**{your_item['name']}** (ID: `{your_item_id}`)\n"
                          f"**Attack:** {your_item['attack']}\n"
                          f"**HP:** {your_item['hp']}\n"
                          f"**Defense:** {your_item['defense']}\n"
                          f"**IV:** {your_item['IV']}%",
                    inline=True
                )

                yourname = your_item['name']
            else:
                trade_embed.add_field(
                    name=f"{ctx.author.name}'s {your_type.capitalize()}",
                    value=f"**{your_item['egg_type']}** (ID: `{your_item_id}`)\n"
                          f"**Attack:** {your_item['attack']}\n"
                          f"**HP:** {your_item['hp']}\n"
                          f"**Defense:** {your_item['defense']}\n"
                          f"**IV:** {your_item['IV']}%",
                    inline=True
                )
                yourname = your_item['egg_type']
            if their_type == "pet":
                trade_embed.add_field(
                    name=f"{their_user.name}'s {their_type.capitalize()}",
                    value=f"**{their_item['name']}** (ID: `{their_item_id}`)\n"
                          f"**Attack:** {their_item['attack']}\n"
                          f"**HP:** {their_item['hp']}\n"
                          f"**Defense:** {their_item['defense']}\n"
                          f"**IV:** {their_item['IV']}%",
                    inline=True
                )
                theirname = their_item['name']
            else:
                trade_embed.add_field(
                    name=f"{their_user.name}'s {their_type.capitalize()}",
                    value=f"**{their_item['egg_type']}** (ID: `{their_item_id}`)\n"
                          f"**Attack:** {their_item['attack']}\n"
                          f"**HP:** {their_item['hp']}\n"
                          f"**Defense:** {their_item['defense']}\n"
                          f"**IV:** {their_item['IV']}%",
                    inline=True
                )
                theirname = their_item['egg_type']
            trade_embed.set_footer(text="React below to accept or decline the trade.")

            message = await ctx.send(embed=trade_embed, view=view)

            await view.wait()

            if view.value is True:
                async with self.bot.pool.acquire() as conn:
                    # Fetch your item
                    if your_type == 'pet':
                        your_item = await conn.fetchrow(
                            "SELECT * FROM monster_pets WHERE user_id = $1 AND id = $2;",
                            ctx.author.id,
                            your_item_id
                        )
                        your_table = 'monster_pets'
                    else:  # egg
                        your_item = await conn.fetchrow(
                            "SELECT * FROM monster_eggs WHERE user_id = $1 AND id = $2;",
                            ctx.author.id,
                            your_item_id
                        )
                        your_table = 'monster_eggs'

                    if not your_item:
                        await ctx.send(f"❌ You don't have a {your_type} with ID `{your_item_id}`.")
                        await self.bot.reset_cooldown(ctx)
                        return

                    # Fetch their item
                    if their_type == 'pet':
                        their_item = await conn.fetchrow(
                            "SELECT * FROM monster_pets WHERE id = $1;",
                            their_item_id
                        )
                        their_table = 'monster_pets'
                    else:  # egg
                        their_item = await conn.fetchrow(
                            "SELECT * FROM monster_eggs WHERE id = $1;",
                            their_item_id
                        )
                        their_table = 'monster_eggs'

                    if not their_item:
                        await ctx.send(f"❌ No {their_type} found with ID `{their_item_id}`.")
                        await self.bot.reset_cooldown(ctx)
                        return

                    their_user_id = their_item['user_id']

                    async with self.bot.pool.acquire() as conn:
                        # Get their tier from profile table
                        their_tier = await conn.fetchval(
                            """
                            SELECT tier 
                            FROM profile 
                            WHERE profile.user = $1
                            """,
                            their_user_id
                        )

                        # Count their pets, unhatched eggs, and pending splice requests
                        their_pet_count = await conn.fetchval(
                            """
                            SELECT 
                                (SELECT COUNT(*) FROM monster_pets WHERE user_id = $1) +
                                (SELECT COUNT(*) FROM monster_eggs WHERE user_id = $1 AND hatched = FALSE) +
                                (SELECT COUNT(*) FROM splice_requests WHERE user_id = $1 AND status = 'pending')
                            """,
                            their_user_id
                        )

                        # Get author's tier from profile table
                        author_tier = await conn.fetchval(
                            """
                            SELECT tier 
                            FROM profile 
                            WHERE profile.user = $1
                            """,
                            ctx.author.id
                        )

                        # Count author's pets, unhatched eggs, and pending splice requests
                        author_pet_count = await conn.fetchval(
                            """
                            SELECT 
                                (SELECT COUNT(*) FROM monster_pets WHERE user_id = $1) +
                                (SELECT COUNT(*) FROM monster_eggs WHERE user_id = $1 AND hatched = FALSE) +
                                (SELECT COUNT(*) FROM splice_requests WHERE user_id = $1 AND status = 'pending')
                            """,
                            ctx.author.id
                        )

                    # Calculate max pets based on tier
                    their_max_pets = 10

                    if hasattr(ctx, 'guild') and ctx.guild.id == 1199287508794626078:
                        their_member = ctx.guild.get_member(their_user_id)
                        if their_member and their_member.premium_since is not None:
                            their_max_pets = max(their_max_pets, 12)  # Ensure they get at least 12 if they're a booster

                    if their_tier == 1:
                        their_max_pets = 12
                    elif their_tier == 2:
                        their_max_pets = 14
                    elif their_tier == 3:
                        their_max_pets = 17
                    elif their_tier == 4:
                        their_max_pets = 25

                    author_max_pets = 10
                    if author_tier == 1 or (hasattr(ctx, 'guild') and ctx.guild.id == 1199287508794626078 and ctx.author.premium_since is not None):
                        author_max_pets = 12
                    elif author_tier == 2:
                        author_max_pets = 14
                    elif author_tier == 3:
                        author_max_pets = 17
                    elif author_tier == 4:
                        author_max_pets = 25

                    # Check both users' pet limits
                    if their_pet_count > their_max_pets:
                        await ctx.send(
                            _("They cannot have more than {0} pets or eggs (Including Spliced). Please ask them to release a pet or wait for an egg to hatch.").format(
                                their_max_pets))
                        return

                    if author_pet_count > author_max_pets:
                        await ctx.send(
                            _("You cannot have more than {0} pets or eggs. Please release a pet or wait for an egg to hatch.").format(
                                author_max_pets))
                        return

                    if their_user_id == ctx.author.id:
                        await ctx.send("❌ You cannot trade with your own items.")
                        await self.bot.reset_cooldown(ctx)
                        return
                # Perform the trade within a transaction
                try:
                    async with self.bot.pool.acquire() as conn:
                        # Update initiator's item to belong to the receiver
                        await conn.execute(
                            f"UPDATE {your_table} SET user_id = $1 WHERE id = $2;",
                            their_user_id,
                            your_item_id
                        )
                        # Update receiver's item to belong to the initiator
                        await conn.execute(
                            f"UPDATE {their_table} SET user_id = $1 WHERE id = $2;",
                            ctx.author.id,
                            their_item_id
                        )
                    success_embed = discord.Embed(
                        title="✅ Trade Successful!",
                        description=f"{ctx.author.mention} traded their **{your_type}** **{yourname}** with {their_user.mention}'s **{their_type}** **{theirname}**.",
                        color=discord.Color.green()
                    )
                    await ctx.send(embed=success_embed)
                except Exception as e:
                    error_embed = discord.Embed(
                        title="❌ Trade Failed",
                        description=f"An error occurred during the trade: {str(e)}",
                        color=discord.Color.red()
                    )
                    await ctx.send(embed=error_embed)
            elif view.value is False:
                decline_embed = discord.Embed(
                    title="❌ Trade Declined",
                    description=f"{their_user.mention} has declined the trade request from {ctx.author.mention}.",
                    color=discord.Color.red()
                )
                await ctx.send(embed=decline_embed)
                await self.bot.reset_cooldown(ctx)
            else:
                # Timeout
                timeout_embed = discord.Embed(
                    title="⌛ Trade Timed Out",
                    description=f"The trade request to {their_user.mention} timed out. No changes were made.",
                    color=discord.Color.orange()
                )
                await ctx.send(embed=timeout_embed)
                await self.bot.reset_cooldown(ctx)

    def create_item_embed(self, user: discord.User, item_type: str, item: asyncpg.Record, item_id: int) -> discord.Embed:
        """
        Creates an embed for the given item with its stats.
        """
        # Add debug info to the embed description
        debug_info = f"Debug - Type: {item_type} | Item Keys: {item.keys()}"

        # Normalize item type to be safe
        item_type = item_type.lower()

        try:
            # First get the name based on type
            if item_type == "pet":
                item_name = item['name']
            else:  # egg
                item_name = item['egg_type']

            # Create the embed with the determined name and debug info
            embed = discord.Embed(
                title=f"{user.name}'s {item_type.capitalize()}",
                description=f"{debug_info}\n\n**Name:** {item_name}\n**ID:** `{item_id}`",
                color=discord.Color.blue()
            )

            # Add stats
            attack = item.get('attack', 0)
            hp = item.get('hp', 0)
            defense = item.get('defense', 0)
            iv = item.get('IV', 0)

            embed.add_field(name="📊 Stats", value=(
                f"**Attack:** {attack}\n"
                f"**HP:** {hp}\n"
                f"**Defense:** {defense}\n"
                f"**IV:** {iv}%"
            ), inline=False)

            return embed

        except Exception as e:
            # If there's an error, return an embed with the error info
            error_embed = discord.Embed(
                title="Error in create_item_embed",
                description=f"Debug Info:\n{debug_info}\n\nError: {str(e)}",
                color=discord.Color.red()
            )
            return error_embed

    @user_cooldown(600)
    @pets.command(brief="Sell your pet or egg to another user for in-game money")
    @has_char()
    async def sell(self, ctx,
                   item_type: str, your_item_id: int,
                   buyer: discord.Member, price: int):
        """
        Sell your pet or egg to another user for in-game money.
        """
        # Normalize type inputs
        item_type = item_type.lower()

        valid_types = ['pet', 'egg']
        if item_type not in valid_types:
            await ctx.send("❌ Invalid type specified. Use `pet` or `egg`.")
            await self.bot.reset_cooldown(ctx)
            return

        if price <= 0:
            await ctx.send("❌ The price must be a positive integer.")
            await self.bot.reset_cooldown(ctx)
            return

        if buyer.id == ctx.author.id:
            await ctx.send("❌ You cannot sell an item to yourself.")
            await self.bot.reset_cooldown(ctx)
            return

        async with self.bot.pool.acquire() as conn:
            # Fetch your item
            if item_type == 'pet':
                your_item = await conn.fetchrow(
                    "SELECT * FROM monster_pets WHERE user_id = $1 AND id = $2;",
                    ctx.author.id,
                    your_item_id
                )
                your_table = 'monster_pets'
            else:  # egg
                your_item = await conn.fetchrow(
                    "SELECT * FROM monster_eggs WHERE user_id = $1 AND id = $2;",
                    ctx.author.id,
                    your_item_id
                )
                your_table = 'monster_eggs'

            if not your_item:
                await ctx.send(f"❌ You don't have a {item_type} with ID `{your_item_id}`.")
                await self.bot.reset_cooldown(ctx)
                return

            # Check if buyer has money
            buyer_money = await conn.fetchval(
                'SELECT "money" FROM profile WHERE "user" = $1;',
                buyer.id
            )
            if buyer_money is None:
                await ctx.send("❌ The buyer does not have a profile.")
                await self.bot.reset_cooldown(ctx)
                return
            if buyer_money < price:
                await ctx.send(f"❌ {buyer.mention} does not have enough money to buy the item.")
                await self.bot.reset_cooldown(ctx)
                return

            # Create the sale embed directly here
            sale_embed = discord.Embed(
                title="💰 Item Sale Proposal",
                description=f"{ctx.author.mention} is offering to sell their {item_type} to {buyer.mention} for **${price}**.",
                color=discord.Color.gold()
            )

            # Add item details based on type
            if item_type == "pet":
                sale_embed.add_field(
                    name=f"{ctx.author.name}'s Pet",
                    value=(
                        f"**{your_item['name']}** (ID: `{your_item_id}`)\n"
                        f"**Attack:** {your_item['attack']}\n"
                        f"**HP:** {your_item['hp']}\n"
                        f"**Defense:** {your_item['defense']}\n"
                        f"**IV:** {your_item['IV']}%"
                    ),
                    inline=True
                )
                item_name = your_item['name']
            else:
                sale_embed.add_field(
                    name=f"{ctx.author.name}'s Egg",
                    value=(
                        f"**{your_item['egg_type']}** (ID: `{your_item_id}`)\n"
                        f"**Attack:** {your_item['attack']}\n"
                        f"**HP:** {your_item['hp']}\n"
                        f"**Defense:** {your_item['defense']}\n"
                        f"**IV:** {your_item['IV']}%"
                    ),
                    inline=True
                )
                item_name = your_item['egg_type']

            sale_embed.set_footer(text="React below to accept or decline the sale.")

            # Create and send view
            view = SellConfirmationView(ctx.author, buyer, price)
            message = await ctx.send(embed=sale_embed, view=view)

            await view.wait()

            if view.value is True:
                # Check buyer's money again
                #await ctx.send(f"buyer id: {buyer.id}")
                try:
                    # Get buyer's tier from profile table
                    buyer_tier = await conn.fetchval(
                        """
                        SELECT tier 
                        FROM profile 
                        WHERE profile.user = $1
                        """,
                        buyer.id
                    )

                    pet_and_egg_count = await conn.fetchval(
                        """
                        SELECT COUNT(*) 
                        FROM (
                            SELECT id FROM monster_pets WHERE user_id = $1
                            UNION ALL
                            SELECT id FROM monster_eggs WHERE user_id = $1 AND hatched = FALSE
                        ) AS combined
                        """,
                        buyer.id
                    )
                except Exception as e:
                    await ctx.send(_("An error occurred while checking pets and eggs. Please try again later."))
                    # Optionally log the error for debugging
                    self.bot.logger.error(f"Error checking pet and egg count: {e}")
                    return

                maxslot = 10

                if (
                        hasattr(ctx, 'guild')
                        and ctx.guild.id == 1199287508794626078
                        and hasattr(buyer, 'premium_since')
                        and buyer.premium_since is not None
                ):
                    maxslot = max(maxslot, 12)

                if buyer_tier == 1:
                    maxslot = 12
                elif buyer_tier == 2:
                    maxslot = 14
                elif buyer_tier == 3:
                    maxslot = 17
                elif buyer_tier == 4:
                    maxslot = 25

                if pet_and_egg_count >= maxslot:
                    await ctx.send(
                        _("They cannot have more than the maximum pets or eggs. Please release a pet or wait for an egg to hatch."))
                    return

                buyer_money = await conn.fetchval(
                    'SELECT "money" FROM profile WHERE "user" = $1;',
                    buyer.id
                )
                if buyer_money < price:
                    await ctx.send(f"❌ {buyer.mention} does not have enough money to buy the item.")
                    await self.bot.reset_cooldown(ctx)
                    return

                try:
                    async with conn.transaction():
                        # Transfer the item
                        await conn.execute(
                            f"UPDATE {your_table} SET user_id = $1 WHERE id = $2;",
                            buyer.id,
                            your_item_id
                        )
                        # Transfer money
                        await conn.execute(
                            "UPDATE profile SET money = money - $1 WHERE \"user\" = $2;",
                            price,
                            buyer.id
                        )
                        await conn.execute(
                            "UPDATE profile SET money = money + $1 WHERE \"user\" = $2;",
                            price,
                            ctx.author.id
                        )

                    success_embed = discord.Embed(
                        title="✅ Sale Successful!",
                        description=(
                            f"**{item_name}** has been sold to {buyer.mention} for **${price}**.\n"
                            f"{ctx.author.mention} has received **${price}**."
                        ),
                        color=discord.Color.green()
                    )
                    await ctx.send(embed=success_embed)

                except Exception as e:
                    error_embed = discord.Embed(
                        title="❌ Sale Failed",
                        description=f"An error occurred during the sale: {str(e)}",
                        color=discord.Color.red()
                    )
                    await ctx.send(embed=error_embed)
                    await self.bot.reset_cooldown(ctx)

            elif view.value is False:
                decline_embed = discord.Embed(
                    title="❌ Sale Declined",
                    description=f"{buyer.mention} has declined the sale offer from {ctx.author.mention}.",
                    color=discord.Color.red()
                )
                await ctx.send(embed=decline_embed)
                await self.bot.reset_cooldown(ctx)
            else:
                timeout_embed = discord.Embed(
                    title="⌛ Sale Timed Out",
                    description=f"The sale offer to {buyer.mention} timed out. No changes were made.",
                    color=discord.Color.orange()
                )
                await ctx.send(embed=timeout_embed)
                await self.bot.reset_cooldown(ctx)

    @pets.command(brief=_("Release a pet or an egg with a sad farewell"))
    async def release(self, ctx, id: int):
        """
        Release a pet or an egg with a sad farewell story.
        """
        # Sad farewell stories for pets
        pet_stories_standard = [
            _("You whisper goodbye to **{name}** as it looks back at you with confused eyes, not understanding why it's being left behind."),
            _("With trembling hands, you release **{name}**. Their bewildered expression haunts you as they slowly wander away."),
            _("The sound of **{name}**'s hopeful chirps fades into the distance as you force yourself to turn away and leave."),
            _("As **{name}** cautiously steps into the wild, it keeps looking back, waiting for you to change your mind."),
            _("**{name}** tries to follow you as you leave, but you quicken your pace, fighting the urge to look back."),
            _("A quiet whimper escapes **{name}** as you set it free, its eyes reflecting confusion and hurt."),
            _("The bond between you and **{name}** strains and breaks as you force yourself to walk away."),
            _("**{name}** tilts its head in confusion, not understanding this is the last time it will see you."),
            _("You feel a pang of guilt as **{name}** trustingly waits for you to return, unaware of your betrayal."),
            _("The joy that once danced in **{name}**'s eyes dims as you turn your back on your loyal companion."),
            _("**{name}** watches you walk away, its excited bouncing slowly turning to stillness as reality sets in."),
            _("As you leave **{name}** behind, you can't help but wonder if it will remember you as fondly as you'll remember it."),
            _("Your footsteps feel heavy as you walk away from **{name}**, its soft cries echoing in your mind."),
            _("The warmth of **{name}**'s body against your hand fades as you release it into an uncertain future."),
        ]

        pet_stories_extra = [
            _("**{name}** paws desperately at your legs as you try to leave, its desperate eyes begging you not to abandon it."),
            _("The trust in **{name}**'s eyes slowly dims as it realizes you're not coming back, replaced by a look of betrayal."),
            _("You feel a piece of your heart crack as **{name}** calls out for you, its cries growing more desperate as you walk away."),
            _("**{name}** sits obediently where you left it, still believing you'll return, unaware of the cruel truth of abandonment."),
            _("The warmth you once felt with **{name}** turns cold as you abandon the companion who gave you nothing but loyalty."),
            _("You try to harden your heart as **{name}** howls after you, its voice breaking with each desperate cry."),
            _("**{name}**'s pained eyes follow you as you leave, silently asking what it did wrong to deserve this fate."),
            _("**{name}** races after you until it can't keep up anymore, collapsing with exhaustion as you disappear from view."),
            _("The sound of **{name}** crying for you echoes through the trees long after you've gone, a haunting melody of abandonment."),
            _("**{name}** nudges the spot where you last stood, desperately searching for any trace of your scent that remains."),
            _("Your name is the last thing **{name}** will remember as it faces the harsh wilderness alone."),
            _("**{name}** frantically searches for you in the underbrush, unable to comprehend that you've abandoned it forever."),
            _("As night falls, **{name}** curls up alone for the first time, shivering without your warmth and protection."),
            _("You glance back to see **{name}** still waiting faithfully, a small figure growing smaller as distance consumes your bond."),
        ]

        pet_stories_extra_extra = [
            _("As you abandon **{name}**, rain begins to fall, washing away your footprints - ensuring your loyal companion can never find its way back to you."),
            _("**{name}** desperately chases after you until exhaustion forces it to collapse, its broken cries fading as distance grows between you."),
            _("The light in **{name}**'s eyes dies as you walk away, replaced by a hollow emptiness that reflects the betrayal of the one it loved most."),
            _("You glimpse back once to see **{name}** shivering alone, vulnerable and confused, as predators begin to circle in the distance."),
            _("**{name}**'s final, desperate howl cuts through you like a knife as you abandon the one creature that would have died to protect you."),
            _("The sound of **{name}** scratching at invisible barriers between you haunts your thoughts as you leave it to an uncertain fate."),
            _("**{name}** tries to follow your scent long after you're gone, growing weaker each day, refusing to believe you would willingly leave it behind."),
            _("Years later, you'll still wake up hearing **{name}**'s desperate cries, wondering if it survived the night you left it all alone."),
            _("You try to forget the image of **{name}** standing in the rain, awaiting a return that will never come, until hunger and cold take their toll."),
            _("The unbreakable bond between you shatters as you abandon **{name}**, leaving a wound in both your souls that time will never heal."),
            _("**{name}**'s pleading eyes will haunt your dreams for years to come, a ghostly reminder of your betrayal."),
            _("The forest seems to go silent as you leave **{name}** behind, as if nature itself is mourning the severing of your bond."),
            _("**{name}**'s trusting heart breaks visibly as you walk away, leaving it vulnerable in a world that shows no mercy to the abandoned."),
            _("Each step you take away from **{name}** feels like walking on shards of your own broken promises."),
        ]

        # New darkest set for pets
        pet_stories_darkest = [
            _("**{name}** watches you abandon it with eyes that slowly empty of all hope, a living epitaph to your betrayal that will haunt you until your dying day."),
            _("The last sound you hear from **{name}** is the heart-wrenching snap as a predator finds your defenseless former companion, a death sentence you knowingly delivered."),
            _("**{name}** desperately follows your scent for days until starvation takes hold, its loyal heart still beating for you even as its body fails."),
            _("You feel **{name}**'s presence for weeks afterward, only to realize it followed you to the edge of death, collapsing within sight of your home, too weak to make that final cry for help."),
            _("The bond you severed with **{name}** leaves a wound so deep in its soul that should you meet again, you'll find only a hollow shell, broken beyond repair by your abandonment."),
            _("**{name}** refuses to accept your betrayal, fighting against the wilderness to find you until its paws bleed and its voice gives out, a testament to the loyalty you discarded."),
            _("Each night as you sleep, **{name}** endures the brutal reality of abandonment - hungry, cold, and facing creatures that smell its fear and vulnerability."),
            _("**{name}** catches a final glimpse of you walking away before a shadow falls over it - nature's cruelty is swift for those left defenseless by the ones they trusted."),
            _("The light in **{name}**'s eyes doesn't just dim - it shatters, leaving behind a creature that will never trust again, a broken reflection of what your betrayal has wrought."),
            _("Seasons will change as **{name}** waits by the spot you left it, its body growing thin and weak, its mind unable to comprehend the depth of your betrayal even as life slowly leaves it."),
            _("You sentenced **{name}** to a slow death of confusion and heartbreak, each beat of its loyal heart a countdown to the moment it finally gives up hope of your return."),
            _("The memory of **{name}**'s desperate cries will resurface each time you feel joy, a phantom pain reminding you of the innocent soul you condemned to suffering."),
            _("The profound betrayal **{name}** feels as you walk away forever changes it, transforming your once loving companion into a creature consumed by abandonment and fear."),
            _("As starvation sets in, **{name}** hallucinates your return again and again, a cruel final comfort as it takes its last breaths alone in the wilderness."),
            _("Your name is the last sound **{name}** tries to call out as it faces its final moments alone, abandoned by the one being it loved unconditionally."),
        ]

        # Sad farewell stories for eggs
        egg_stories_standard = [
            _("You place the **{name}** egg in the wild, knowing it will never know the warmth and safety you could have provided."),
            _("The **{name}** egg grows cold as you walk away, the life inside already missing the warmth of your care."),
            _("You leave the **{name}** egg exposed to the elements, its future now left to cruel chance rather than loving care."),
            _("As you set down the **{name}** egg, you wonder if it somehow knows it's being abandoned before it even had a chance."),
            _("The **{name}** egg sits motionless as you depart, the creature inside unaware it has already been forsaken."),
            _("You whisper an apology to the **{name}** egg that will never be heard by the life growing within."),
            _("The potential for companionship dies as you abandon the **{name}** egg to face the harsh world alone."),
            _("The **{name}** egg's surface loses its luster as you turn away, as if mourning a future that will never be."),
            _("You place the **{name}** egg under a bush, hiding it from predators but also from the love it would have known with you."),
            _("The **{name}** egg seems to dim as your shadow falls away from it one last time."),
            _("You rationalize leaving the **{name}** egg behind, but can't shake the feeling of having abandoned an unborn life."),
            _("The **{name}** egg rests where you leave it, the creature inside unaware its first experience will be abandonment."),
            _("A slight warmth still lingers on the **{name}** egg from your touch - the last comfort it will ever know."),
            _("The **{name}** egg's subtle movements seem to still as you walk away, as if sensing it's been left alone."),
        ]

        egg_stories_extra = [
            _("The **{name}** egg trembles slightly as you set it down, as if the life inside senses its abandonment."),
            _("You leave the **{name}** egg behind, denying the unborn creature inside the love and protection it would have known with you."),
            _("A small crack appears on the **{name}** egg's surface as you depart, as if it's crying out for you not to leave."),
            _("The **{name}** egg grows dim without your warmth, the life inside already struggling without your care."),
            _("You condemn the **{name}** egg to face predators and harsh elements alone, betraying its defenseless innocence."),
            _("The bond that could have formed between you and the creature in the **{name}** egg withers before it had a chance to grow."),
            _("The **{name}** egg's soft glow fades as you walk away, its silent plea for protection unanswered."),
            _("The **{name}** egg grows still without your nurturing touch, the fragile life inside feeling the first pangs of abandonment."),
            _("As night approaches, the **{name}** egg lies vulnerable to the cold and predators, your protection withdrawn forever."),
            _("The **{name}** egg's warmth dissipates rapidly as you depart, the defenseless life inside beginning to struggle."),
            _("You deny the **{name}** egg the chance to hatch into loving arms, leaving it to face a harsh welcome into the world."),
            _("The **{name}** egg seems to call to you as you leave, a silent cry from a life that will never know your care."),
            _("As you turn your back on the **{name}** egg, you also turn away from the joy and bond that might have been."),
            _("The **{name}** egg begins to cool immediately in your absence, the developing life inside sensing something is terribly wrong."),
        ]

        egg_stories_extra_extra = [
            _("The **{name}** egg pulses weakly as you abandon it, the defenseless life inside already feeling the cold grip of loneliness."),
            _("You leave the **{name}** egg to a cruel fate, knowing nocturnal predators will soon detect its vulnerable warmth."),
            _("As darkness falls, the abandoned **{name}** egg glows faintly, a beacon calling to hungry creatures seeking an easy meal."),
            _("The **{name}** egg will never know what it's like to hatch into loving arms - instead, it faces a world of immediate danger and suffering."),
            _("You condemn the innocent life in the **{name}** egg to either a quick death or a harsh life of abandonment before it even had a chance to live."),
            _("The **{name}** egg's shell thins from stress as you leave, the unborn creature inside already sensing it has been betrayed."),
            _("You walk away as a scavenger's shadow falls over the helpless **{name}** egg, its fate sealed by your decision."),
            _("The tiny heartbeat inside the **{name}** egg grows erratic with fear as you abandon it, already struggling to survive without your protection."),
            _("The life within the **{name}** egg will never understand why it was forsaken before it could even take its first breath."),
            _("The **{name}** egg cracks slightly, a silent tear from the creature inside who somehow knows it's been abandoned to die alone."),
            _("The fragile life in the **{name}** egg feels the world grow cold as you leave, its first and perhaps last experience of existence."),
            _("A shadow passes over the **{name}** egg just as you walk away, nature's cruel timing sealing the fate you've chosen for it."),
            _("The **{name}** egg's subtle glow - the sign of healthy life within - begins to flicker and fade without your nurturing presence."),
            _("As you abandon the **{name}** egg, raindrops begin to fall, slowly washing away any trace that you were ever there to protect it."),
        ]

        # New darkest set for eggs
        egg_stories_darkest = [
            _("The **{name}** egg's shell cracks from the inside in a final, desperate attempt to follow you, forcing a premature hatching that dooms the fragile life within to a painful, brief existence."),
            _("You leave the **{name}** egg alone as night falls, its warmth attracting a predator that slowly cracks it open, consuming the defenseless life that would have called you parent."),
            _("The life within the **{name}** egg senses your abandonment and its development begins to reverse, a slow cellular death that knows only betrayal as its first and final experience."),
            _("The **{name}** egg dulls and grows cold without your touch, the developing creature inside feeling every moment of your absence as its systems begin to shut down."),
            _("As you walk away, the **{name}** egg pulses one last time before its inner light extinguishes completely, the unborn life inside having spent its last energy reaching for your departed warmth."),
            _("You abandon the **{name}** egg just before a storm breaks, its fragile shell unable to withstand the elements, washing away any evidence of the life you sentenced to oblivion."),
            _("The **{name}** egg's surface becomes transparent as you leave, revealing the tiny heart inside visibly slowing with each step you take away from it."),
            _("The creature within the **{name}** egg experiences the agony of abandonment as its first sensation, its developing mind imprinted with loss before it ever knew companionship."),
            _("Your decision to abandon the **{name}** egg disrupts the delicate balance within, triggering a cascade of cellular failure that ensures it will never experience life beyond the shell."),
            _("The **{name}** egg begins to collapse inward as you depart, a physical manifestation of the void left by your absence, slowly crushing the life you've forsaken."),
            _("The unhatched creature inside the **{name}** egg reaches desperately toward your departing footsteps, expending its limited energy in a futile attempt to reclaim the protection you've withdrawn."),
            _("As night creatures begin to circle the abandoned **{name}** egg, the tiny being inside experiences terror as the first and last emotion of its existence."),
            _("Without your protective warmth, parasites quickly infiltrate the **{name}** egg's weakened shell, consuming the developing life in a slow, inexorable process."),
            _("The life within the **{name}** egg feels every second of abandonment, a timeless agony of betrayal that stretches into eternity in its limited consciousness."),
            _("You consign the **{name}** egg to a death so lonely that even the elements seem to mourn, rain falling like tears over a life that never had the chance to truly exist."),
        ]

        # Combine all stories with weights
        # Standard: 50%, Extra: 30%, Extra-Extra: 15%, Darkest: 5%
        try:
            pet_all_stories = (
                    pet_stories_standard * 9 +  # Weight 10 = 50%
                    pet_stories_extra * 6 +  # Weight 6 = 30%
                    pet_stories_extra_extra * 5 +  # Weight 3 = 15%
                    pet_stories_darkest * 4 # Weight 1 = 5%
            )

            egg_all_stories = (
                    egg_stories_standard * 9 +
                    egg_stories_extra * 6 +
                    egg_stories_extra_extra * 5 +
                    egg_stories_darkest * 4
            )

            async with self.bot.pool.acquire() as conn:
                # Check if the ID corresponds to a pet or an egg
                pet = await conn.fetchrow("SELECT * FROM monster_pets WHERE user_id = $1 AND id = $2;", ctx.author.id,
                                          id)
                egg = await conn.fetchrow("SELECT * FROM monster_eggs WHERE user_id = $1 AND id = $2;", ctx.author.id,
                                          id)

                if not pet and not egg:
                    await ctx.send(_("❌ No pet or egg with ID `{id}` found in your collection.").format(id=id))
                    return

                # Determine the name and type (pet or egg)
                item_name = pet['name'] if pet else egg['egg_type']
                # Select a random story based on type
                if pet:
                    story = random.choice(pet_all_stories)
                else:
                    story = random.choice(egg_all_stories)

                # Confirmation prompt
                confirmation_message = await ctx.send(
                    _("⚠️ Are you sure you want to release your **{item_name}**? This action cannot be undone.").format(
                        item_name=item_name)
                )

                # Add buttons for confirmation
                confirm_view = discord.ui.View()

                async def confirm_callback(interaction):
                    try:
                        if interaction.user != ctx.author:
                            await interaction.response.send_message(
                                _("❌ You are not authorized to respond to this release."),
                                ephemeral=True)
                            return
                        await interaction.response.defer()  # Acknowledge interaction to prevent timeout
                        async with self.bot.pool.acquire() as conn:
                            # Check if the ID corresponds to a pet or an egg
                            pet = await conn.fetchrow("SELECT * FROM monster_pets WHERE user_id = $1 AND id = $2;",
                                                      ctx.author.id, id)
                            egg = await conn.fetchrow("SELECT * FROM monster_eggs WHERE user_id = $1 AND id = $2;",
                                                      ctx.author.id, id)

                            if not pet and not egg:
                                await ctx.send(
                                    _("❌ No pet or egg with ID `{id}` found in your collection.").format(id=id))
                                return
                        async with self.bot.pool.acquire() as conn:
                            if pet:
                                await conn.execute("DELETE FROM monster_pets WHERE id = $1 AND user_id = $2;", id,
                                                   ctx.author.id)
                            elif egg:
                                await conn.execute("DELETE FROM monster_eggs WHERE id = $1 AND user_id = $2;", id,
                                                   ctx.author.id)

                        farewell_message = story.format(name=item_name)
                        await interaction.followup.send(farewell_message)

                        for child in confirm_view.children:
                            child.disabled = True
                        await confirmation_message.edit(view=confirm_view)
                    except Exception as e:
                        print(e)

                async def cancel_callback(interaction):
                    if interaction.user != ctx.author:
                        await interaction.response.send_message(_("❌ You are not authorized to cancel this release."),
                                                                ephemeral=True)
                        return
                    await interaction.response.send_message(_("✅ Release action cancelled."), ephemeral=True)
                    # Disable buttons after cancellation
                    for child in confirm_view.children:
                        child.disabled = True
                    await confirmation_message.edit(view=confirm_view)

                confirm_button = discord.ui.Button(label=_("Confirm Release"), style=discord.ButtonStyle.red, emoji="💔")
                confirm_button.callback = confirm_callback
                cancel_button = discord.ui.Button(label=_("Cancel"), style=discord.ButtonStyle.grey, emoji="❌")
                cancel_button.callback = cancel_callback

                confirm_view.add_item(confirm_button)
                confirm_view.add_item(cancel_button)

                await confirmation_message.edit(view=confirm_view)
        except Exception as e:
            await ctx.send(e)
            
    class EggSelect(discord.ui.Select):
        def __init__(self, eggs):
            # Create options for each egg
            options = []
            for i, egg in enumerate(eggs):
                # Choose emoji based on element
                element = egg['element'].lower() if egg['element'] else 'unknown'
                if 'fire' in element:
                    element_emoji = "🔥"
                elif 'water' in element:
                    element_emoji = "💧"
                elif 'electric' in element:
                    element_emoji = "⚡"
                elif 'light' in element:
                    element_emoji = "✨"
                elif 'dark' in element:
                    element_emoji = "🌑"
                elif 'wind' in element or 'nature' in element:
                    element_emoji = "🌿"
                elif 'corrupt' in element:
                    element_emoji = "☠️"
                else:
                    element_emoji = "🥚"
                    
                options.append(
                    discord.SelectOption(
                        label=f"{egg['egg_type']} (ID: {egg['id']})",
                        description=f"{egg['element']} | IV: {egg['IV']}%",
                        value=str(i),  # Store the index in the eggs list as value
                        emoji=element_emoji
                    )
                )
            
            # Initialize the select with a placeholder and the options
            super().__init__(placeholder="Select an egg to view...", min_values=1, max_values=1, options=options)
        
        async def callback(self, interaction: discord.Interaction):
            # The callback is handled in the view class
            view = self.view
            if interaction.user.id != view.author.id:
                return await interaction.response.send_message("These are not your eggs.", ephemeral=True)
            
            view.index = int(self.values[0])
            await view.send_page(interaction)

    class EggPaginator(discord.ui.View):
        def __init__(self, eggs, author):
            super().__init__(timeout=60)
            self.eggs = eggs
            self.author = author
            self.index = 0
            self.message = None  # To store the message reference
            
            # Add the dropdown menu if there are eggs
            if eggs:
                self.add_item(Pets.EggSelect(eggs))
                
        async def on_timeout(self):
            """Auto-close the egg viewer when the view times out"""
            if self.message:
                try:
                    await self.message.delete()
                except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                    # Message might have been deleted already or we lack permissions
                    pass

        def get_embed(self):
            egg = self.eggs[self.index]

            # Calculate time left until hatching
            time_left = egg["hatch_time"] - datetime.datetime.utcnow()
            time_left_str = str(time_left).split('.')[0]  # Remove microseconds
            if time_left.total_seconds() <= 0:
                time_left_str = "Ready to hatch!"

            # Check if egg ID is 6666 and modify stats display accordingly
            hp_display = "???" if egg['id'] == 6666 else egg['hp']
            attack_display = "???" if egg['id'] == 6666 else egg['attack']
            defense_display = "???" if egg['id'] == 6666 else egg['defense']

            # Choose background color based on egg rarity (using IV as a proxy for rarity)
            iv = egg['IV']
            if iv >= 90:
                color = discord.Color.gold()
            elif iv >= 75:
                color = discord.Color.purple()
            elif iv >= 50:
                color = discord.Color.blue()
            else:
                color = discord.Color.green()

            # Create the embed
            embed = discord.Embed(
                title=f"🥚 Your Egg: {egg['egg_type']}",
                color=color,
                description=f"**ID:** {egg['id']}\n**Element:** {egg['element']}"
            )

            embed.add_field(
                name="✨ **Stats**",
                value=(
                    f"**IV:** {egg['IV']}%\n"
                    f"**HP:** {hp_display}\n"
                    f"**Attack:** {attack_display}\n"
                    f"**Defense:** {defense_display}"
                ),
                inline=False,
            )

            embed.add_field(
                name="⏳ **Hatching Time**",
                value=f"{time_left_str}",
                inline=False,
            )

            embed.set_footer(
                text=f"Viewing egg {self.index + 1} of {len(self.eggs)} | Use the dropdown to navigate"
            )
            
            # Use the egg's URL if available, otherwise use a default egg image
            if egg.get('url'):
                embed.set_image(url=egg["url"])

            return embed

        async def send_page(self, interaction: discord.Interaction):
            embed = self.get_embed()

            if self.message is None:
                self.message = interaction.message

            if interaction.response.is_done():
                await self.message.edit(embed=embed, view=self)
            else:
                await interaction.response.edit_message(embed=embed, view=self)

        @discord.ui.button(label="Close", style=discord.ButtonStyle.red, row=1)
        async def close_button(self, interaction: discord.Interaction, button: discord.ui.Button):
            if interaction.user.id != self.author.id:
                return await interaction.response.send_message("These are not your eggs.", ephemeral=True)

            await interaction.message.delete()
            self.stop()

    @pets.command(brief=_("Check your monster eggs"))
    async def eggs(self, ctx):
        async with self.bot.pool.acquire() as conn:
            eggs = await conn.fetch(
                "SELECT * FROM monster_eggs WHERE user_id = $1 AND hatched = FALSE;",
                ctx.author.id,
            )
            if not eggs:
                await ctx.send(_("You don't have any eggs to incubate."))
                return

        view = self.EggPaginator(eggs, ctx.author)
        embed = view.get_embed()
        view.message = await ctx.send(embed=embed, view=view)

    @user_cooldown(300)
    @pets.command(brief=_("Feed your pet"))
    async def feed(self, ctx):
        growth_stages = {
            1: {"stage": "baby", "growth_time": 2, "stat_multiplier": 0.25, "hunger_modifier": 1.0},
            2: {"stage": "juvenile", "growth_time": 2, "stat_multiplier": 0.50, "hunger_modifier": 0.8},
            3: {"stage": "young", "growth_time": 1, "stat_multiplier": 0.75, "hunger_modifier": 0.6},
            4: {"stage": "adult", "growth_time": None, "stat_multiplier": 1.0, "hunger_modifier": 0.0},
            # Self-sufficient
        }

        async with self.bot.pool.acquire() as conn:
            # Fetch all pets owned by the user
            pets = await conn.fetch(
                "SELECT * FROM monster_pets WHERE user_id = $1",
                ctx.author.id
            )

            current_time = datetime.datetime.utcnow()

            if not pets:
                await ctx.send("You don't have any pets to feed.")
                await self.bot.reset_cooldown(ctx)
                return

            # Update hunger and happiness for all pets owned by the user
            await conn.execute(
                """
                UPDATE monster_pets
                SET hunger = 100, happiness = 100, last_update = $1
                WHERE user_id = $2;
                """,
                current_time,
                ctx.author.id
            )

            await ctx.send("You fed all your pets, and they look happy!")

    @pets.command(brief=_("Learn how to use the pet system"))
    async def help(self, ctx):
        """
        Provides a detailed guide on pet-related commands and how to get a pet.
        """
        embed = discord.Embed(
            title=_("Pet System Guide"),
            description=_("Learn how to care for, manage, and interact with your pets in the game!"),
            color=discord.Color.green(),
        )

        embed.add_field(
            name=_("🐾 How to Get a Pet"),
            value=_(
                "You can find **monster eggs** as rare rewards during PVE battles. Each egg hatches into a unique pet after a specific time.\n"
                "Use `$pets eggs` to check your eggs!"
            ),
            inline=False,
        )

        embed.add_field(
            name="\u200b",  # Invisible spacer field
            value="\u200b",
            inline=False,
        )

        embed.add_field(
            name=_("🔍 `$pets`"),
            value=_(
                "View all your current pets in a **paginated list**. Use the buttons to navigate through your pets.\n"
                "This command shows their stats, growth stage, and other details."
            ),
            inline=False,
        )

        embed.add_field(
            name="\u200b",  # Invisible spacer field
            value="\u200b",
            inline=False,
        )

        embed.add_field(
            name=_("🍖 `$pets feed <id>`"),
            value=_(
                "Feed a specific pet by its ID to increase its **hunger** and **happiness**.\n"
                "Pets need regular feeding to stay happy and healthy.\n"
                "⚠️ If hunger or happiness drops to zero, your pet may run away or starve!"
            ),
            inline=False,
        )

        embed.add_field(
            name="\u200b",  # Invisible spacer field
            value="\u200b",
            inline=False,
        )

        embed.add_field(
            name=_("⚔️ `$pets equip <id>`"),
            value=_(
                "Equip a pet to fight alongside you in battles and raids.\n"
                "Only pets in the **young** stage or older can be equipped.\n"
                "Equipped pets will use their stats to support you in combat."
            ),
            inline=False,
        )

        embed.add_field(
            name="\u200b",  # Invisible spacer field
            value="\u200b",
            inline=False,
        )

        embed.add_field(
            name=_("💔 `$pets release <id>`"),
            value=_(
                "Release a pet back into the wild or an egg into nature.\n"
                "⚠️ This action is permanent, so choose wisely.\n"
                "A touching farewell message will accompany their departure."
            ),
            inline=False,
        )

        embed.add_field(
            name="\u200b",  # Invisible spacer field
            value="\u200b",
            inline=False,
        )

        embed.add_field(
            name=_("🔄 `$pets trade <type> <your_pet_id> <type> <their_pet_id>`"),
            value=_(
                "Initiate a **trade** with another user by exchanging pets.\n"
                "Both users must agree to the trade within **2 minutes**, or the pets will remain with their original owners."
            ),
            inline=False,
        )

        embed.add_field(
            name="\u200b",  # Invisible spacer field
            value="\u200b",
            inline=False,
        )

        embed.add_field(
            name=_("✏️ `$pets rename <id> <name>`"),
            value=_(
                "Rename your pet. Leaving the name field blank will default it to the orignal name."
            ),
            inline=False,
        )

        embed.add_field(
            name="\u200b",  # Invisible spacer field
            value="\u200b",
            inline=False,
        )

        embed.add_field(
            name=_("💰 `$pets sell <type> <id> <@user> <amount>`"),
            value=_(
                "Sell one of your pets to another user for an agreed price.\n"
                "The transaction must be completed within **2 minutes**, or the pet and money will return to their owners."
            ),
            inline=False,
        )

        embed.add_field(
            name="\u200b",  # Invisible spacer field
            value="\u200b",
            inline=False,
        )

        embed.add_field(
            name=_("📦 `$pets eggs`"),
            value=_(
                "View all your unhatched eggs and their remaining hatch time.\n"
                "Make sure to keep track of your eggs to avoid missing out!"
            ),
            inline=False,
        )

        embed.set_footer(text=_("Take care of your pets to grow them into powerful allies!"))
        await ctx.send(embed=embed)

    @pets.command(brief=_("Unequip a pet"),
                      description="Unequip one of your pets to use in battles. Only one pet can be equipped at a time.")
    async def unequip(self, ctx, petid: int):
        async with self.bot.pool.acquire() as conn:
            # Fetch the specified pet
            pet = await conn.fetchrow(
                "SELECT * FROM monster_pets WHERE user_id = $1 AND monster_pets.id = $2;",
                ctx.author.id,
                petid,
            )
            if not pet:
                await ctx.send(f"You don't have a pet with the ID: {id}.")
                return
            petname = pet["name"]
            # Check if the pet is at least "young"
            if pet["growth_stage"] not in ["young", "adult"]:
                await ctx.send(f"{petname} must be at least in the young growth stage to be equipped.")
                return

            # Unequip the currently equipped pet, if any
            await conn.execute(
                "UPDATE monster_pets SET equipped = FALSE WHERE user_id = $1 AND equipped = TRUE;",
                ctx.author.id,
            )

            await ctx.send(f"You have unequipped {petname} successfully!")

    @pets.command(brief=_("Equip a pet"),
                      description="Equip one of your pets to use in battles. Only one pet can be equipped at a time.")
    async def equip(self, ctx, petid: int):
        async with self.bot.pool.acquire() as conn:
            # Fetch the specified pet
            pet = await conn.fetchrow(
                "SELECT * FROM monster_pets WHERE user_id = $1 AND monster_pets.id = $2;",
                ctx.author.id,
                petid,
            )
            if not pet:
                await ctx.send(f"You don't have a pet with the ID: {id}.")
                return
            petname = pet["name"]
            # Check if the pet is at least "young"
            if pet["growth_stage"] not in ["young", "adult"]:
                await ctx.send(f"{petname} must be at least in the young growth stage to be equipped.")
                return

            # Unequip the currently equipped pet, if any
            await conn.execute(
                "UPDATE monster_pets SET equipped = FALSE WHERE user_id = $1 AND equipped = TRUE;",
                ctx.author.id,
            )

            # Equip the selected pet
            await conn.execute(
                "UPDATE monster_pets SET equipped = TRUE WHERE monster_pets.id = $1;",
                petid,
            )

            await ctx.send(f"You have equipped {petname} successfully!")

    @user_cooldown(120)
    @pets.command(brief=_("Rename your pet or reset its name to the default"))
    async def rename(self, ctx, id: int, *, nickname: str = None):
        """
        Rename a pet or reset its name to the default.
        - If `nickname` is provided, sets the pet's name to the given nickname.
        - If `nickname` is omitted, resets the pet's name to the default.
        """
        try:
            async with self.bot.pool.acquire() as conn:
                # Fetch the pet from the database
                pet = await conn.fetchrow("SELECT * FROM monster_pets WHERE user_id = $1 AND id = $2;", ctx.author.id, id)

                if not pet:
                    await ctx.send(_("❌ No pet with ID `{id}` found in your collection.").format(id=id))
                    return

                # Check if resetting or renaming
                if nickname:
                    if len(nickname) > 50:  # Limit nickname length to 20 characters
                        await ctx.send(_("❌ Nickname cannot exceed 50 characters."))
                        return

                    # Update the pet's nickname in the database
                    await conn.execute("UPDATE monster_pets SET name = $1 WHERE id = $2;", nickname, id)
                    await ctx.send(_("✅ Successfully renamed your pet to **{nickname}**!").format(nickname=nickname))
                else:
                    # Reset the pet's nickname to the default name
                    default_name = pet['default_name']
                    await conn.execute("UPDATE monster_pets SET name = $1 WHERE id = $2;", default_name, id)
                    await ctx.send(_("✅ Pet's name has been reset to its default: **{default_name}**.").format(
                        default_name=default_name))
        except Exception as e:
            await ctx.send(e)

    async def check_pet(self, user_id, pet_id=None):
        """Calculate pet status on demand based on timestamps"""
        async with self.bot.pool.acquire() as conn:
            # Query to get pet(s)
            if pet_id:
                pets = await conn.fetch("SELECT * FROM monster_pets WHERE id = $1", pet_id)
            else:
                pets = await conn.fetch("SELECT * FROM monster_pets WHERE user_id = $1", user_id)

            results = []
            for pet in pets:
                # Skip adults
                if pet['growth_stage'] == 'adult':
                    results.append(pet)
                    continue

                # Calculate time passed - ensure both are naive or both are aware
                current_time = datetime.datetime.utcnow()
                last_update = pet['last_update']

                # Make last_update naive if it's aware
                if last_update.tzinfo is not None:
                    last_update = last_update.replace(tzinfo=None)

                hours_passed = (current_time - last_update).total_seconds() / 3600

                # Rate depends on growth stage
                if pet['growth_stage'] == 'baby':
                    hunger_rate = 10 / 12  # Per hour
                    happiness_rate = 5 / 12
                elif pet['growth_stage'] == 'juvenile':
                    hunger_rate = 8 / 12
                    happiness_rate = 4 / 12
                elif pet['growth_stage'] == 'young':
                    hunger_rate = 6 / 12
                    happiness_rate = 3 / 12

                # Calculate new values
                new_hunger = max(0, pet['hunger'] - int(hours_passed * hunger_rate))
                new_happiness = max(0, pet['happiness'] - int(hours_passed * happiness_rate))

                # Update database with new values and timestamp
                await conn.execute(
                    """
                    UPDATE monster_pets
                    SET hunger = $1, happiness = $2, last_update = $3
                    WHERE id = $4
                    """,
                    new_hunger, new_happiness, current_time, pet['id']
                )

                # Check for death/runaway if values hit 0
                if new_hunger == 0 and pet['user_id'] != 5:
                    await self.handle_pet_death(conn, pet['user_id'], pet['id'], pet['name'])
                elif new_happiness == 0 and pet['user_id'] != 5:
                    await self.handle_pet_runaway(conn, pet['user_id'], pet['id'], pet['name'])

                # Get updated pet info
                updated_pet = await conn.fetchrow(
                    "SELECT * FROM monster_pets WHERE id = $1",
                    pet['id']
                )
                if updated_pet:
                    results.append(updated_pet)

            return results

    async def handle_pet_death(self, conn, user_id, pet_id, pet_name):
        """Handles pet death due to starvation."""
        # Update the pet's user_id to 5 instead of deleting
        await conn.execute(
            "UPDATE monster_pets SET user_id = $1 WHERE id = $2;",
            5, pet_id
        )

        # Attempt to fetch the user
        user = self.bot.get_user(user_id)
        if user:
            try:
                await user.send(
                    f"😢 Your pet **{pet_name}** has died from starvation. Please take better care next time."
                )
            except discord.Forbidden:
                # User has DMs disabled
                pass

    async def handle_pet_runaway(self, conn, user_id, pet_id, pet_name):
        """Handles pet running away due to unhappiness."""
        # Delete the pet from the database
        await conn.execute(
            "DELETE FROM monster_pets WHERE id = $1;",
            pet_id
        )

        # Attempt to fetch the user
        user = self.bot.get_user(user_id)
        if user:
            try:
                await user.send(
                    f"😞 Your pet **{pet_name}** has run away due to unhappiness. Make sure to keep your pet happy!"
                )
            except discord.Forbidden:
                # User has DMs disabled
                pass

    @tasks.loop(minutes=1)
    async def check_egg_hatches(self):
        # Define the growth stages
        growth_stages = {
            1: {"stage": "baby", "growth_time": 2, "stat_multiplier": 0.25, "hunger_modifier": 1.0},
            2: {"stage": "juvenile", "growth_time": 2, "stat_multiplier": 0.50, "hunger_modifier": 0.8},
            3: {"stage": "young", "growth_time": 1, "stat_multiplier": 0.75, "hunger_modifier": 0.6},
            4: {"stage": "adult", "growth_time": None, "stat_multiplier": 1.0, "hunger_modifier": 0.0},
        }

        try:
            async with self.bot.pool.acquire() as conn:
                # Fetch eggs that are ready to hatch
                eggs = await conn.fetch(
                    "SELECT * FROM monster_eggs WHERE hatched = FALSE AND hatch_time <= NOW();"
                )
                for egg in eggs:
                    # Mark the egg as hatched
                    await conn.execute(
                        "UPDATE monster_eggs SET hatched = TRUE WHERE id = $1;", egg["id"]
                    )

                    # Get the baby stage data
                    baby_stage = growth_stages[1]
                    stat_multiplier = baby_stage["stat_multiplier"]
                    growth_time_interval = datetime.timedelta(days=baby_stage["growth_time"])
                    growth_time = datetime.datetime.utcnow() + growth_time_interval

                    # Adjust the stats
                    hp = round(egg["hp"] * stat_multiplier)
                    attack = round(egg["attack"] * stat_multiplier)
                    defense = round(egg["defense"] * stat_multiplier)

                    iv_value = egg.get("IV") or egg.get("iv")
                    if iv_value is None:
                        iv_value = 0  # Set a default value or handle as needed

                    # Insert the hatched egg into monster_pets
                    await conn.execute(
                        """
                        INSERT INTO monster_pets (
                            user_id, name, default_name, hp, attack, defense, element, url,
                            growth_stage, growth_index, growth_time, "IV"
                        )
                        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12);
                        """,
                        egg["user_id"],
                        egg["egg_type"],  # Set initial pet name to the default name
                        egg["egg_type"],  # Store the default species name
                        hp,
                        attack,
                        defense,
                        egg["element"],
                        egg["url"],
                        baby_stage["stage"],  # 'baby'
                        1,  # growth_index
                        growth_time,
                        iv_value,
                    )

                    # Notify the user
                    user = self.bot.get_user(egg["user_id"])
                    if user:
                        await user.send(
                            f"Your **Egg** has hatched into a pet named **{egg['egg_type']}**! Check your pet menu to see it."
                        )
        except Exception as e:
            print(f"Error in check_egg_hatches: {e}")
            user = self.bot.get_user(295173706496475136)
            if user:
                await user.send(f"Error in check_egg_hatches: {e}")

    @tasks.loop(minutes=1)
    async def check_pet_growth(self):
        growth_stages = {
            1: {"stage": "baby", "growth_time": 2, "stat_multiplier": 0.25, "hunger_modifier": 1.0},
            2: {"stage": "juvenile", "growth_time": 2, "stat_multiplier": 0.50, "hunger_modifier": 0.8},
            3: {"stage": "young", "growth_time": 1, "stat_multiplier": 0.75, "hunger_modifier": 0.6},
            4: {"stage": "adult", "growth_time": None, "stat_multiplier": 1.0, "hunger_modifier": 0.0},
            # Self-sufficient
        }

        try:
            async with self.bot.pool.acquire() as conn:
                # Fetch pets that are ready to grow
                pets = await conn.fetch(
                    "SELECT * FROM monster_pets WHERE growth_time <= NOW() AND growth_stage != 'adult';"
                )
                for pet in pets:
                    next_stage_index = pet["growth_index"] + 1
                    if next_stage_index in growth_stages:
                        stage_data = growth_stages[next_stage_index]

                        # Compute the interval as a timedelta object
                        if stage_data["growth_time"] is not None:
                            growth_time_interval = datetime.timedelta(days=stage_data["growth_time"])
                        else:
                            growth_time_interval = None

                        # Calculate the multiplier ratio
                        old_multiplier = growth_stages[pet["growth_index"]]["stat_multiplier"]
                        new_multiplier = stage_data["stat_multiplier"]
                        multiplier_ratio = new_multiplier / old_multiplier

                        newhp = pet["hp"] * multiplier_ratio
                        newattack = pet["attack"] * multiplier_ratio
                        newdefense = pet["defense"] * multiplier_ratio

                        # Execute the appropriate query
                        if growth_time_interval is not None:
                            result = await conn.fetchrow(
                                """
                                UPDATE monster_pets
                                SET 
                                    growth_stage = $1,
                                    growth_time = NOW() + $2,
                                    hp = $3,
                                    attack = $4,
                                    defense = $5,
                                    growth_index = $6
                                WHERE 
                                    "id" = $7
                                RETURNING hp, attack, defense;
                                """,
                                stage_data["stage"],
                                growth_time_interval,
                                newhp,
                                newattack,
                                newdefense,
                                next_stage_index,
                                pet["id"],
                            )
                        else:
                            result = await conn.fetchrow(
                                """
                                UPDATE monster_pets
                                SET 
                                    growth_stage = $1,
                                    growth_time = NULL,
                                    hp = $2,
                                    attack = $3,
                                    defense = $4,
                                    growth_index = $5
                                WHERE 
                                    "id" = $6
                                RETURNING hp, attack, defense;
                                """,
                                stage_data["stage"],
                                newhp,
                                newattack,
                                newdefense,
                                next_stage_index,
                                pet["id"],
                            )

                        # Notify the user about the growth
                        user = self.bot.get_user(pet["user_id"])
                        if user:
                            await user.send(
                                f"Your pet **{pet['name']}** has grown into a {stage_data['stage']}!"
                            )
        except Exception as e:
            print(f"Error in check_pet_growth: {e}")

    @is_gm()
    @commands.command(name="gmcreatemonster")
    async def gmcreatemonster(self, ctx):
        def check(m):
            return m.author == ctx.author and m.channel == ctx.channel

        # Prompt for monster name
        await ctx.send("Please enter the **name** of the monster (or type `cancel` to cancel):")
        try:
            name_msg = await ctx.bot.wait_for("message", timeout=60.0, check=check)
        except asyncio.TimeoutError:
            return await ctx.send("Timed out. Monster creation cancelled.")
        if name_msg.content.lower() == "cancel":
            return await ctx.send("Monster creation cancelled.")
        monster_name = name_msg.content.strip()

        # Prompt for monster level (1-10)
        await ctx.send("Please enter the **level** of the monster (1-10) (or type `cancel` to cancel):")
        try:
            level_msg = await ctx.bot.wait_for("message", timeout=60.0, check=check)
        except asyncio.TimeoutError:
            return await ctx.send("Timed out. Monster creation cancelled.")
        if level_msg.content.lower() == "cancel":
            return await ctx.send("Monster creation cancelled.")
        try:
            level_int = int(level_msg.content.strip())
            if level_int < 1 or level_int > 10:
                return await ctx.send("Invalid level. Must be between 1 and 10. Monster creation cancelled.")
        except ValueError:
            return await ctx.send("Invalid input for level. Monster creation cancelled.")

        # Prompt for monster element
        valid_elements = {"Corrupted", "Water", "Electric", "Light", "Dark", "Wind", "Nature", "Fire"}
        await ctx.send("Please enter the **element** of the monster (or type `cancel` to cancel):\n"
                       f"Valid elements are: {', '.join(valid_elements)}")
        try:
            element_msg = await ctx.bot.wait_for("message", timeout=60.0, check=check)
        except asyncio.TimeoutError:
            return await ctx.send("Timed out. Monster creation cancelled.")
        if element_msg.content.lower() == "cancel":
            return await ctx.send("Monster creation cancelled.")
        # Convert input to have first letter capitalized and rest lower-case
        monster_element = element_msg.content.strip().capitalize()
        if monster_element not in valid_elements:
            return await ctx.send(
                "Invalid element. Must be one of: " + ", ".join(valid_elements) + ". Monster creation cancelled."
            )

        # Prompt for stats in the format "hp, attack, defense"
        await ctx.send(
            "Please enter the **HP, Attack, and Defense** of the monster in the format:\n"
            "`hp, attack, defense` (e.g., `100, 95, 100`) (or type `cancel` to cancel):"
        )
        try:
            stats_msg = await ctx.bot.wait_for("message", timeout=60.0, check=check)
        except asyncio.TimeoutError:
            return await ctx.send("Timed out. Monster creation cancelled.")
        if stats_msg.content.lower() == "cancel":
            return await ctx.send("Monster creation cancelled.")
        try:
            parts = [part.strip() for part in stats_msg.content.split(",")]
            if len(parts) != 3:
                return await ctx.send(
                    "Invalid format. Expected format: `hp, attack, defense`. Monster creation cancelled.")
            hp_val = int(parts[0])
            attack_val = int(parts[1])
            defense_val = int(parts[2])
        except ValueError:
            return await ctx.send("Stat values must be integers. Monster creation cancelled.")

        # Prompt for image URL
        await ctx.send(
            "Please enter the **image URL** for the monster (must end with `.png`, `.jpg` or `.webp`) (or type `cancel` to cancel):"
        )
        try:
            url_msg = await ctx.bot.wait_for("message", timeout=60.0, check=check)
        except asyncio.TimeoutError:
            return await ctx.send("Timed out. Monster creation cancelled.")
        if url_msg.content.lower() == "cancel":
            return await ctx.send("Monster creation cancelled.")
        monster_url = url_msg.content.strip()
        if not (monster_url.lower().endswith(".png") or monster_url.lower().endswith(
                ".jpg") or monster_url.lower().endswith(".webp")):
            return await ctx.send(
                "Invalid image URL. Must end with `.png`, `.jpg`, or `.webp`. Monster creation cancelled.")

        # Prompt for ispublic (true/false)
        await ctx.send("Please enter whether the monster is public and found in the wild (`true` or `false`) (or type `cancel` to cancel):")
        try:
            public_msg = await ctx.bot.wait_for("message", timeout=60.0, check=check)
        except asyncio.TimeoutError:
            return await ctx.send("Timed out. Monster creation cancelled.")
        if public_msg.content.lower() == "cancel":
            return await ctx.send("Monster creation cancelled.")
        ispublic_str = public_msg.content.strip().lower()
        if ispublic_str not in ["true", "false"]:
            return await ctx.send("Invalid input for ispublic. Must be `true` or `false`. Monster creation cancelled.")
        is_public = True if ispublic_str == "true" else False

        # Build the monster entry
        new_monster = {
            "name": monster_name,
            "hp": hp_val,
            "attack": attack_val,
            "defense": defense_val,
            "element": monster_element,
            "url": monster_url,
            "ispublic": is_public
        }

        # Load the current monsters JSON data
        try:
            with open("monsters.json", "r") as f:
                data = json.load(f)
        except Exception as e:
            return await ctx.send("Error loading monsters data. Monster creation cancelled.")

        # Append the new monster to the appropriate level
        level_key = str(level_int)
        if level_key not in data:
            data[level_key] = []
        data[level_key].append(new_monster)

        # Save the updated JSON back to file
        try:
            with open("monsters.json", "w") as f:
                json.dump(data, f, indent=4)
        except Exception as e:
            return await ctx.send("Error saving monsters data. Monster creation cancelled.")

        await ctx.send(f"Monster **{monster_name}** has been successfully added to level {level_int}!")


async def setup(bot):
    await bot.add_cog(Pets(bot))
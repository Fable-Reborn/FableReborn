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
import decimal
import json
import math

import asyncpg

import utils.misc as rpgtools
from collections import deque
from collections import deque
from decimal import Decimal
from decimal import Decimal, ROUND_HALF_UP

import discord
import random as randomm
from discord.enums import ButtonStyle
from discord.ext import commands, tasks
from discord.ui.button import Button

from classes import logger
from classes.classes import Ranger, Reaper
from classes.classes import from_string as class_from_string
from classes.converters import IntGreaterThan
from cogs.shard_communication import user_on_cooldown as user_cooldown
from utils import random
from utils.checks import has_char, has_money, is_gm
from utils.i18n import _, locale_doc
from utils.joins import SingleJoinView

from discord.ui import View
from discord import Embed, Interaction

import discord
from discord.ext import commands
import datetime

from utils.random import randint


import discord
from discord.ui import View, Button
from discord import Interaction
import asyncio

class SellConfirmationView(View):
    def __init__(self, initiator: discord.Member, receiver: discord.Member, price: int, timeout=120):
        super().__init__(timeout=timeout)
        self.initiator = initiator
        self.receiver = receiver
        self.price = price
        self.value = None  # Will store True (accepted) or False (declined)

    @discord.ui.button(label="Accept Sale", style=ButtonStyle.success, emoji="✅")
    async def accept(self, interaction: Interaction, button: Button):
        if interaction.user != self.receiver:
            await interaction.response.send_message(
                "❌ You are not authorized to respond to this sale.", ephemeral=True
            )
            return
        self.value = True
        await interaction.response.send_message("✅ Sale accepted.", ephemeral=True)
        self.stop()

    @discord.ui.button(label="Decline Sale", style=ButtonStyle.danger, emoji="❌")
    async def decline(self, interaction: Interaction, button: Button):
        if interaction.user != self.receiver:
            await interaction.response.send_message(
                "❌ You are not authorized to respond to this sale.", ephemeral=True
            )
            return
        self.value = False
        await interaction.response.send_message("❌ Sale declined.", ephemeral=True)
        self.stop()


class TradeConfirmationView(View):
    def __init__(self, initiator: discord.User, receiver: discord.User, timeout=120):
        super().__init__(timeout=timeout)
        self.initiator = initiator
        self.receiver = receiver
        self.value = None  # Will store True (accepted) or False (declined)

    @discord.ui.button(label="Accept Trade", style=ButtonStyle.success, emoji="✅")
    async def accept(self, interaction: Interaction, button: Button):
        if interaction.user.id != self.receiver.id:
            await interaction.response.send_message("❌ You are not authorized to respond to this trade.", ephemeral=True)
            return
        self.value = True
        await interaction.response.send_message("✅ Trade accepted.", ephemeral=True)
        self.stop()

    @discord.ui.button(label="Decline Trade", style=ButtonStyle.danger, emoji="❌")
    async def decline(self, interaction: Interaction, button: Button):
        if interaction.user.id != self.receiver.id:
            await interaction.response.send_message("❌ You are not authorized to respond to this trade.", ephemeral=True)
            return
        self.value = False
        await interaction.response.send_message("❌ Trade declined.", ephemeral=True)
        self.stop()





class PetPaginator(View):
    def __init__(self, pets, author):
        super().__init__(timeout=60)
        self.pets = pets
        self.author = author
        self.index = 0
        self.message = None  # To store the message reference

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

        embed = Embed(
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
            text=f"Viewing pet {self.index + 1} of {len(self.pets)} | Use the buttons to navigate."
        )
        embed.set_image(url=pet["url"])

        return embed

    async def send_page(self, interaction: Interaction):
        embed = self.get_embed()

        if self.message is None:
            self.message = interaction.message

        if interaction.response.is_done():
            await self.message.edit(embed=embed, view=self)
        else:
            await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Previous", style=discord.ButtonStyle.blurple)
    async def previous_button(self, interaction: Interaction, button: discord.ui.Button):
        if interaction.user.id != self.author.id:
            return await interaction.response.send_message("This is not your pet list.", ephemeral=True)

        self.index = (self.index - 1) % len(self.pets)
        await self.send_page(interaction)

    @discord.ui.button(label="Next", style=discord.ButtonStyle.blurple)
    async def next_button(self, interaction: Interaction, button: discord.ui.Button):
        if interaction.user.id != self.author.id:
            return await interaction.response.send_message("This is not your pet list.", ephemeral=True)

        self.index = (self.index + 1) % len(self.pets)
        await self.send_page(interaction)

    @discord.ui.button(label="Close", style=discord.ButtonStyle.red)
    async def close_button(self, interaction: Interaction, button: discord.ui.Button):
        if interaction.user.id != self.author.id:
            return await interaction.response.send_message("This is not your pet list.", ephemeral=True)

        await interaction.message.delete()
        self.stop()

class DialogueView(discord.ui.View):
    def __init__(self, pages: list[discord.Embed], author: discord.User):
        super().__init__(timeout=60)
        self.pages = pages
        self.current_page = 0
        self.author = author

    async def update_message(self, interaction: discord.Interaction):
        # If the response hasn't been sent yet, use response.edit_message.
        # Otherwise, use followup.edit_message.
        if not interaction.response.is_done():
            await interaction.response.edit_message(embed=self.pages[self.current_page], view=self)
        else:
            # You must supply the message ID of the message that contains the view.
            await interaction.followup.edit_message(
                message_id=interaction.message.id,
                embed=self.pages[self.current_page],
                view=self
            )

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        # Only allow the view author to interact with these buttons.
        return interaction.user.id == self.author.id

    @discord.ui.button(label="⮜ Previous", style=discord.ButtonStyle.primary)
    async def previous_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current_page > 0:
            self.current_page -= 1
        await self.update_message(interaction)

    @discord.ui.button(label="Next ⮞", style=discord.ButtonStyle.primary)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current_page < len(self.pages) - 1:
            self.current_page += 1
        await self.update_message(interaction)

    @discord.ui.button(label="Skip Dialogue", style=discord.ButtonStyle.danger)
    async def skip_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        # End dialogue immediately
        await interaction.response.edit_message(content="Dialogue skipped. The battle begins!", embed=None, view=None)
        self.stop()




class Battles(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.forceleg = False
        self.softlanding = False
        if not self.decrease_pet_stats.is_running():
            self.decrease_pet_stats.start()
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
        self.fighting_players = {}

        self.levels = {
            1: {
                "minion1_name": "Imp",
                "minion2_name": "Shadow Spirit",
                "boss_name": "Abyssal Guardian",
                "minion1": {"hp": 65, "armor": 15, "damage": 35},
                "minion2": {"hp": 75, "armor": 20, "damage": 55},
                "boss": {"hp": 150, "armor": 30, "damage": 65}
            },
            2: {
                "minion1_name": "Wraith",
                "minion2_name": "Soul Eater",
                "boss_name": "Vile Serpent",
                "minion1": {"hp": 80, "armor": 35, "damage": 50},
                "minion2": {"hp": 90, "armor": 55, "damage": 70},
                "boss": {"hp": 250, "armor": 30, "damage": 80}
            },
            3: {
                "minion1_name": "Goblin",
                "minion2_name": "Orc",
                "boss_name": "Warlord Grakthar",
                "minion1": {"hp": 100, "armor": 5, "damage": 70},
                "minion2": {"hp": 120, "armor": 80, "damage": 50},
                "boss": {"hp": 270, "armor": 95, "damage": 95}
            },
            4: {
                "minion1_name": "Skeleton",
                "minion2_name": "Zombie",
                "boss_name": "Necromancer Voss",
                "minion1": {"hp": 130, "armor": 20, "damage": 70},
                "minion2": {"hp": 150, "armor": 30, "damage": 70},
                "boss": {"hp": 190, "armor": 110, "damage": 115}
            },
            5: {
                "minion1_name": "Bandit",
                "minion2_name": "Highwayman",
                "boss_name": "Blackblade Marauder",
                "minion1": {"hp": 130, "armor": 30, "damage": 75},
                "minion2": {"hp": 150, "armor": 30, "damage": 80},
                "boss": {"hp": 250, "armor": 117, "damage": 119}
            },
            6: {
                "minion1_name": "Spiderling",
                "minion2_name": "Venomous Arachnid",
                "boss_name": "Arachnok Queen",
                "minion1": {"hp": 150, "armor": 36, "damage": 79},
                "minion2": {"hp": 170, "armor": 37, "damage": 85},
                "boss": {"hp": 275, "armor": 122, "damage": 127}
            },
            7: {
                "minion1_name": "Wisp",
                "minion2_name": "Specter",
                "boss_name": "Lich Lord Moros",
                "minion1": {"hp": 155, "armor": 38, "damage": 83},
                "minion2": {"hp": 175, "armor": 43, "damage": 89},
                "boss": {"hp": 280, "armor": 127, "damage": 132}
            },
            8: {
                "minion1_name": "Frost Imp",
                "minion2_name": "Ice Elemental",
                "boss_name": "Frostfire Behemoth",
                "minion1": {"hp": 155, "armor": 42, "damage": 87},
                "minion2": {"hp": 175, "armor": 47, "damage": 93},
                "boss": {"hp": 285, "armor": 132, "damage": 137}
            },
            9: {
                "minion1_name": "Lizardman",
                "minion2_name": "Dragonkin",
                "boss_name": "Dragonlord Zaldrak",
                "minion1": {"hp": 160, "armor": 45, "damage": 90},
                "minion2": {"hp": 180, "armor": 52, "damage": 95},
                "boss": {"hp": 295, "armor": 138, "damage": 140}
            },
            10: {
                "minion1_name": "Haunted Spirit",
                "minion2_name": "Phantom Wraith",
                "boss_name": "Soulreaver Lurkthar",
                "minion1": {"hp": 160, "armor": 48, "damage": 93},
                "minion2": {"hp": 185, "armor": 55, "damage": 97},
                "boss": {"hp": 315, "armor": 150, "damage": 150}
            },
            11: {
                "minion1_name": "Gnoll Raider",
                "minion2_name": "Hyena Pack",
                "boss_name": "Ravengaze Alpha",
                "minion1": {"hp": 170, "armor": 52, "damage": 97},
                "minion2": {"hp": 185, "armor": 101, "damage": 70},
                "boss": {"hp": 330, "armor": 153, "damage": 155}
            },
            12: {
                "minion1_name": "Gloomhound",
                "minion2_name": "Nocturne Stalker",
                "boss_name": "Nightshade Serpentis",
                "minion1": {"hp": 170, "armor": 82, "damage": 139},
                "minion2": {"hp": 190, "armor": 87, "damage": 144},
                "boss": {"hp": 335, "armor": 157, "damage": 160}
            },
            13: {
                "minion1_name": "Magma Elemental",
                "minion2_name": "Inferno Imp",
                "boss_name": "Ignis Inferno",
                "minion1": {"hp": 175, "armor": 85, "damage": 141},
                "minion2": {"hp": 190, "armor": 90, "damage": 148},
                "boss": {"hp": 335, "armor": 160, "damage": 163}
            },
            14: {
                "minion1_name": "Cursed Banshee",
                "minion2_name": "Spectral Harbinger",
                "boss_name": "Wraithlord Maroth",
                "minion1": {"hp": 180, "armor": 89, "damage": 145},
                "minion2": {"hp": 225, "armor": 93, "damage": 152},
                "boss": {"hp": 340, "armor": 163, "damage": 166}
            },
            15: {
                "minion1_name": "Demonic Imp",
                "minion2_name": "Hellspawn Reaver",
                "boss_name": "Infernus, the Infernal",
                "minion1": {"hp": 182, "armor": 145, "damage": 89},
                "minion2": {"hp": 250, "armor": 152, "damage": 93},
                "boss": {"hp": 350, "armor": 170, "damage": 170}
            },
            16: {
                "minion1_name": "Tainted Ghoul",
                "minion2_name": "Necrotic Abomination",
                "boss_name": "Master Shapeshifter",
                "minion1": {"hp": 400, "armor": 122, "damage": 199},
                "minion2": {"hp": 400, "armor": 127, "damage": 204},
                "boss": {"hp": 360, "armor": 180, "damage": 180}
            },
            17: {
                "minion1_name": "Chaos Fiend",
                "minion2_name": "Voidborn Horror",
                "boss_name": "Eldritch Devourer",
                "minion1": {"hp": 186, "armor": 149, "damage": 92},
                "minion2": {"hp": 250, "armor": 156, "damage": 95},
                "boss": {"hp": 355, "armor": 175, "damage": 175}
            },
            18: {
                "minion1_name": "Blood Warden",
                "minion2_name": "Juzam Djinn",
                "boss_name": "Dreadlord Vortigon",
                "minion1": {"hp": 190, "armor": 153, "damage": 95},
                "minion2": {"hp": 250, "armor": 159, "damage": 99},
                "boss": {"hp": 360, "armor": 180, "damage": 175}
            },
            19: {
                "minion1_name": "Specter",
                "minion2_name": "Phantom Wraith",
                "boss_name": "Spectral Overlord",
                "minion1": {"hp": 200, "armor": 153, "damage": 95},
                "minion2": {"hp": 250, "armor": 159, "damage": 99},
                "boss": {"hp": 250, "armor": 0, "damage": 350}
            },
            20: {
                "minion1_name": "Ice Elemental",
                "minion2_name": "Frozen Horror",
                "boss_name": "Frostbite, the Ice Tyrant",
                "minion1": {"hp": 205, "armor": 155, "damage": 99},
                "minion2": {"hp": 250, "armor": 161, "damage": 102},
                "boss": {"hp": 365, "armor": 210, "damage": 140}
            },
            21: {
                "minion1_name": "Dragonkin",
                "minion2_name": "Chromatic Wyrm",
                "boss_name": "Chromaggus the Flamebrand",
                "minion1": {"hp": 210, "armor": 160, "damage": 99},
                "minion2": {"hp": 250, "armor": 161, "damage": 102},
                "boss": {"hp": 365, "armor": 210, "damage": 140}
            },
            22: {
                "minion1_name": "Phantom Banshee",
                "minion2_name": "Wailing Apparition",
                "boss_name": "Banshee Queen Shriekara",
                "minion1": {"hp": 205, "armor": 155, "damage": 99},
                "minion2": {"hp": 250, "armor": 161, "damage": 102},
                "boss": {"hp": 365, "armor": 210, "damage": 140}
            },
            23: {
                "minion1_name": "Abyssal Imp",
                "minion2_name": "Voidbringer Fiend",
                "boss_name": "Voidlord Malgros",
                "minion1": {"hp": 205, "armor": 155, "damage": 99},
                "minion2": {"hp": 250, "armor": 161, "damage": 102},
                "boss": {"hp": 370, "armor": 200, "damage": 130}
            },
            24: {
                "minion1_name": "Dreadshade Specter",
                "minion2_name": "Soulreaver Harbinger",
                "boss_name": "Soulshredder Vorath",
                "minion1": {"hp": 250, "armor": 140, "damage": 99},
                "minion2": {"hp": 250, "armor": 140, "damage": 115},
                "boss": {"hp": 360, "armor": 225, "damage": 125}
            },
            25: {
                "minion1_name": "Inferno Aberration",
                "minion2_name": "Brimstone Fiend",
                "boss_name": "Pyroclasmic Overfiend",
                "minion1": {"hp": 250, "armor": 140, "damage": 99},
                "minion2": {"hp": 250, "armor": 140, "damage": 115},
                "boss": {"hp": 360, "armor": 190, "damage": 150}
            },
            26: {
                "minion1_name": "Crimson Serpent",
                "minion2_name": "Sanguine Horror",
                "boss_name": "Sangromancer Malroth",
                "minion1": {"hp": 250, "armor": 140, "damage": 99},
                "minion2": {"hp": 250, "armor": 140, "damage": 115},
                "boss": {"hp": 360, "armor": 250, "damage": 100}
            },
            27: {
                "minion1_name": "Doombringer Abomination",
                "minion2_name": "Chaosspawn Horror",
                "boss_name": "Chaosforged Leviathan",
                "minion1": {"hp": 250, "armor": 140, "damage": 99},
                "minion2": {"hp": 250, "armor": 140, "damage": 115},
                "boss": {"hp": 360, "armor": 110, "damage": 250}
            },
            28: {
                "minion1_name": "Nethersworn Aberration",
                "minion2_name": "Eldritch Behemoth",
                "boss_name": "Abyssal Enderark",
                "minion1": {"hp": 250, "armor": 140, "damage": 99},
                "minion2": {"hp": 250, "armor": 140, "damage": 115},
                "boss": {"hp": 400, "armor": 180, "damage": 100}
            },
            29: {
                "minion1_name": "Darktide Kraken",
                "minion2_name": "Abyssal Voidlord",
                "boss_name": "Tidal Terror Abaddon",
                "minion1": {"hp": 250, "armor": 140, "damage": 99},
                "minion2": {"hp": 250, "armor": 140, "damage": 115},
                "boss": {"hp": 390, "armor": 230, "damage": 150}
            },
            30: {
                "minion1_name": "Elder Voidfiend",
                "minion2_name": "Abyssal Voidreaver",
                "boss_name": "Eldritch Archdemon",
                "minion1": {"hp": 250, "armor": 110, "damage": 110},
                "minion2": {"hp": 250, "armor": 140, "damage": 140},
                "boss": {"hp": 600, "armor": 200, "damage": 190}
            }
        }



    # Command to use the paginator
    @commands.group(invoke_without_command=True)
    async def pets(self, ctx):
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
            trade_embed = Embed(
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
                        # Count pets, unhatched eggs, and pending splice requests (each counts as 2)
                        pet_and_egg_count = await conn.fetchval(
                            """
                            SELECT 
                                (SELECT COUNT(*) FROM monster_pets WHERE user_id = $1) +
                                (SELECT COUNT(*) FROM monster_eggs WHERE user_id = $1 AND hatched = FALSE) +
                                (SELECT COUNT(*) FROM splice_requests WHERE user_id = $1 AND status = 'pending')
                            """,
                            their_user_id
                        )

                    if pet_and_egg_count >= 10:
                        await ctx.send(
                            _("They cannot have more than 10 pets or eggs (Including Spliced). Please release a pet or wait for an egg to hatch."))
                        return

                    async with self.bot.pool.acquire() as conn:
                        # Count pets, unhatched eggs, and pending splice requests (each counts as 2)
                        pet_and_egg_count = await conn.fetchval(
                            """
                            SELECT 
                                (SELECT COUNT(*) FROM monster_pets WHERE user_id = $1) +
                                (SELECT COUNT(*) FROM monster_eggs WHERE user_id = $1 AND hatched = FALSE) +
                                (SELECT COUNT(*) FROM splice_requests WHERE user_id = $1 AND status = 'pending')
                            """,
                            ctx.author.id
                        )

                    if pet_and_egg_count >= 10:
                        await ctx.send(
                            _("You cannot have more than 10 pets or eggs. Please release a pet or wait for an egg to hatch."))
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
                    success_embed = Embed(
                        title="✅ Trade Successful!",
                        description=f"{ctx.author.mention} traded their **{your_type}** **{yourname}** with {their_user.mention}'s **{their_type}** **{theirname}**.",
                        color=discord.Color.green()
                    )
                    await ctx.send(embed=success_embed)
                except Exception as e:
                    error_embed = Embed(
                        title="❌ Trade Failed",
                        description=f"An error occurred during the trade: {str(e)}",
                        color=discord.Color.red()
                    )
                    await ctx.send(embed=error_embed)
            elif view.value is False:
                decline_embed = Embed(
                    title="❌ Trade Declined",
                    description=f"{their_user.mention} has declined the trade request from {ctx.author.mention}.",
                    color=discord.Color.red()
                )
                await ctx.send(embed=decline_embed)
                await self.bot.reset_cooldown(ctx)
            else:
                # Timeout
                timeout_embed = Embed(
                    title="⌛ Trade Timed Out",
                    description=f"The trade request to {their_user.mention} timed out. No changes were made.",
                    color=discord.Color.orange()
                )
                await ctx.send(embed=timeout_embed)
                await self.bot.reset_cooldown(ctx)

    def create_item_embed(self, user: discord.User, item_type: str, item: asyncpg.Record, item_id: int) -> Embed:
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
            embed = Embed(
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
            error_embed = Embed(
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
            sale_embed = Embed(
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

                if pet_and_egg_count >= 10:
                    await ctx.send(
                        _("They cannot have more than 10 pets or eggs. Please release a pet or wait for an egg to hatch."))
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

                    success_embed = Embed(
                        title="✅ Sale Successful!",
                        description=(
                            f"**{item_name}** has been sold to {buyer.mention} for **${price}**.\n"
                            f"{ctx.author.mention} has received **${price}**."
                        ),
                        color=discord.Color.green()
                    )
                    await ctx.send(embed=success_embed)

                except Exception as e:
                    error_embed = Embed(
                        title="❌ Sale Failed",
                        description=f"An error occurred during the sale: {str(e)}",
                        color=discord.Color.red()
                    )
                    await ctx.send(embed=error_embed)
                    await self.bot.reset_cooldown(ctx)

            elif view.value is False:
                decline_embed = Embed(
                    title="❌ Sale Declined",
                    description=f"{buyer.mention} has declined the sale offer from {ctx.author.mention}.",
                    color=discord.Color.red()
                )
                await ctx.send(embed=decline_embed)
                await self.bot.reset_cooldown(ctx)
            else:
                timeout_embed = Embed(
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
        # Sad farewell stories
        pet_stories_standard = [
            _("You whisper goodbye to **{name}** as it looks back at you one last time before running off into the wild."),
            _("With a heavy heart, you release **{name}**. It hesitates for a moment before disappearing into the distance."),
            _("You watch **{name}** fade into the horizon, a bittersweet memory etched in your heart."),
            _("As **{name}** scurries away, you can't help but hope it finds happiness in its new life."),
            _("Tears fill your eyes as **{name}** takes its first steps into freedom. A part of you leaves with it."),
        ]

        pet_stories_extra = [
            _("A lump forms in your throat as you let go of **{name}**. The bond you shared feels unbreakable, yet you must part ways."),
            _("Your heart aches as **{name}** turns to face you one final time before venturing into the unknown."),
            _("**{name}** gives you a lingering gaze filled with trust and farewell, leaving you with a sorrowful heart."),
            _("The silence between you is deafening as **{name}** begins to walk away, carrying your memories into the vast wilderness."),
            _("You hold back tears as **{name}** takes the first step towards its new journey, leaving an emptiness in your soul."),
        ]

        pet_stories_extra_extra = [
            _("A profound sadness envelops you as you release **{name}**. The absence of its presence leaves a void that words cannot fill."),
            _("Your soul weeps as **{name}** slips away into the twilight, taking with it the joy and companionship you cherished."),
            _("The ground feels hollow as **{name}** disappears from sight, leaving behind only echoes of laughter and love."),
            _("You feel a deep, unrelenting sorrow as **{name}** embarks on its final journey, a piece of your heart left behind."),
            _("As **{name}** vanishes into the mist, a tear escapes your eye, mourning the loss of a beloved friend."),
        ]

        egg_stories_standard = [
            _("You carefully place the **{name}** egg in a safe spot in the wild, hoping it will find its way."),
            _("Letting go of the **{name}** egg was hard, but you know it's for the best. Farewell, little one."),
            _("You leave the **{name}** egg where the sun can keep it warm. Maybe one day it will hatch and thrive."),
            _("The **{name}** egg glimmers in the sunlight as you bid it farewell. The world feels a little emptier."),
            _("You set down the **{name}** egg gently, whispering a silent prayer for its safety."),
        ]

        egg_stories_extra = [
            _("A heavy heart weighs on you as you release the **{name}** egg, entrusting its fate to the wild."),
            _("Your eyes mist over as you place the **{name}** egg in the untouched wilderness, filled with hope and sorrow."),
            _("The **{name}** egg rests in its new home, a silent testament to your love and the farewell you must make."),
            _("With a tearful sigh, you let go of the **{name}** egg, knowing it's destined for a future you can only imagine."),
            _("The **{name}** egg lies under the canopy, carrying the dreams and wishes you hold dear."),
        ]

        egg_stories_extra_extra = [
            _("A profound sorrow fills your being as you release the **{name}** egg, its fate now beyond your reach."),
            _("Your spirit aches as you place the **{name}** egg into the wild, a piece of your heart left to wander."),
            _("The **{name}** egg shimmers briefly before being swallowed by the earth, leaving you with an indescribable emptiness."),
            _("You release the **{name}** egg with a shattered heart, mourning the loss of a future you envisioned together."),
            _("As the **{name}** egg vanishes into the foliage, your soul weeps for the dreams that will never come to fruition."),
        ]

        # Combine all stories with weights
        # Standard: 60%, Extra: 30%, Extra-Extra: 10%
        try:
            pet_all_stories = (
                    pet_stories_standard * 6 +  # 5 stories * 6 = 30
                    pet_stories_extra * 3 +  # 5 stories * 3 = 15
                    pet_stories_extra_extra * 1  # 5 stories * 1 = 5
            )

            egg_all_stories = (
                    egg_stories_standard * 6 +
                    egg_stories_extra * 3 +
                    egg_stories_extra_extra * 1
            )

            async with self.bot.pool.acquire() as conn:
                # Check if the ID corresponds to a pet or an egg
                pet = await conn.fetchrow("SELECT * FROM monster_pets WHERE user_id = $1 AND id = $2;", ctx.author.id, id)
                egg = await conn.fetchrow("SELECT * FROM monster_eggs WHERE user_id = $1 AND id = $2;", ctx.author.id, id)

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
                confirm_view = View()

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
                                await conn.execute("DELETE FROM monster_pets WHERE id = $1 AND user_id = $2;", id, ctx.author.id)
                            elif egg:
                                await conn.execute("DELETE FROM monster_eggs WHERE id = $1 AND user_id = $2;", id, ctx.author.id)

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

                confirm_button = Button(label=_("Confirm Release"), style=discord.ButtonStyle.red, emoji="💔")
                confirm_button.callback = confirm_callback
                cancel_button = Button(label=_("Cancel"), style=discord.ButtonStyle.grey, emoji="❌")
                cancel_button.callback = cancel_callback

                confirm_view.add_item(confirm_button)
                confirm_view.add_item(cancel_button)

                await confirmation_message.edit(view=confirm_view)
        except Exception as e:
            await ctx.send(e)



    @has_char()
    @user_cooldown(90)
    @commands.command(brief=_("Battle against another player"))
    @locale_doc
    async def battle(
            self, ctx, money: IntGreaterThan(-1) = 0, enemy: discord.Member = None
    ):
        _(
            """`[money]` - A whole number that can be 0 or greater; defaults to 0
            `[enemy]` - A user who has a profile; defaults to anyone

            Fight against another player while betting money.
            To decide the fight, the players' items, race and class bonuses and an additional number from 1 to 7 are evaluated, this serves as a way to give players with lower stats a chance at winning.

            The money is removed from both players at the start of the battle. Once a winner has been decided, they will receive their money, plus the enemy's money.
            The battle lasts 30 seconds, after which the winner and loser will be mentioned.

            If both players' stats + random number are the same, the winner is decided at random.
            The battle's winner will receive a PvP win, which shows on their profile.
            (This command has a cooldown of 90 seconds.)"""
        )
        if enemy == ctx.author:
            return await ctx.send(_("You can't battle yourself."))
        if ctx.character_data["money"] < money:
            return await ctx.send(_("You are too poor."))

        await self.bot.pool.execute(
            'UPDATE profile SET "money"="money"-$1 WHERE "user"=$2;',
            money,
            ctx.author.id,
        )

        if not enemy:
            text = _("{author} seeks a battle! The price is **${money}**.").format(
                author=ctx.author.mention, money=money
            )
        else:
            text = _(
                "{author} seeks a battle with {enemy}! The price is **${money}**."
            ).format(author=ctx.author.mention, enemy=enemy.mention, money=money)

        async def check(user: discord.User) -> bool:
            return await has_money(self.bot, user.id, money)

        future = asyncio.Future()
        view = SingleJoinView(
            future,
            Button(
                style=ButtonStyle.primary,
                label=_("Join the battle!"),
                emoji="\U00002694",
            ),
            allowed=enemy,
            prohibited=ctx.author,
            timeout=60,
            check=check,
            check_fail_message=_("You don't have enough money to join the battle."),
        )

        await ctx.send(text, view=view)

        try:
            enemy_ = await future
        except asyncio.TimeoutError:
            await self.bot.reset_cooldown(ctx)
            await self.bot.pool.execute(
                'UPDATE profile SET "money"="money"+$1 WHERE "user"=$2;',
                money,
                ctx.author.id,
            )
            return await ctx.send(
                _("Noone wanted to join your battle, {author}!").format(
                    author=ctx.author.mention
                )
            )

        await self.bot.pool.execute(
            'UPDATE profile SET "money"="money"-$1 WHERE "user"=$2;', money, enemy_.id
        )

        await ctx.send(
            _(
                "Battle **{author}** vs **{enemy}** started! 30 seconds of fighting"
                " will now start!"
            ).format(author=ctx.disp, enemy=enemy_.display_name)
        )

        stats = [
            sum(await self.bot.get_damage_armor_for(ctx.author)) + random.randint(1, 7),
            sum(await self.bot.get_damage_armor_for(enemy_)) + random.randint(1, 7),
        ]
        players = [ctx.author, enemy_]
        if stats[0] == stats[1]:
            winner = random.choice(players)
        else:
            winner = players[stats.index(max(stats))]
        looser = players[players.index(winner) - 1]

        await asyncio.sleep(30)

        async with self.bot.pool.acquire() as conn:
            await conn.execute(
                'UPDATE profile SET "pvpwins"="pvpwins"+1, "money"="money"+$1 WHERE'
                ' "user"=$2;',
                money * 2,
                winner.id,
            )
            await self.bot.log_transaction(
                ctx,
                from_=looser.id,
                to=winner.id,
                subject="Battle Bet",
                data={"Gold": money},
                conn=conn,
            )
        await ctx.send(
            _("{winner} won the battle vs {looser}! Congratulations!").format(
                winner=winner.mention, looser=looser.mention
            )
        )

    @commands.group(aliases=["bt"])
    async def battletower(self, ctx):
        print("hello world")
        if ctx.invoked_subcommand is None:
            await ctx.invoke(self.progress)

    @is_gm()
    @commands.command(hidden=True)
    async def setbtlevel(self, ctx, user_id: int, prestige: int, level: int):
        # Check if the user invoking the command is allowed


        try:
            async with self.bot.pool.acquire() as conn:
                await conn.execute(
                    'UPDATE battletower SET "level"=$1, prestige=$2 WHERE "id"=$3;',
                    level,
                    prestige,
                    user_id,
                )
            await ctx.send(f"Successfully updated level for user {user_id} to {level}.")
        except Exception as e:
            await ctx.send(f"An error occurred while updating the level: {e}")

    async def find_opponent(self, ctx):
        count = 0
        score = 0
        author_hp = 250  # Setting the author's initial HP
        while author_hp > 0:
            players = []

            async with self.bot.pool.acquire() as connection:
                while True:
                    query = 'SELECT "user" FROM profile WHERE "user" != $1 ORDER BY RANDOM() LIMIT 1'
                    random_opponent_id = await connection.fetchval(query, ctx.author.id)

                    if not random_opponent_id or random_opponent_id != 730276802316206202:
                        break  # Exit the loop if a suitable opponent ID is found

                if not random_opponent_id:
                    return None  # Couldn't find a suitable opponent at the moment

                enemy = await self.bot.fetch_user(random_opponent_id)

            if not enemy:
                return None  # Failed to fetch opponent information. Please try again later.

            async with self.bot.pool.acquire() as conn:
                for player in (ctx.author, enemy):
                    dmg, deff = await self.bot.get_raidstats(player, conn=conn)
                    if player == ctx.author:
                        hp_value = author_hp
                    else:
                        hp_value = 250  # Set the default hp for the enemy

                    u = {"user": player, "hp": hp_value, "armor": deff, "damage": dmg}
                    players.append(u)

            battle_log = deque(
                [
                    (
                        0,
                        _("Raidbattle {p1} vs. {p2} started!").format(
                            p1=players[0]["user"].display_name, p2=players[1]["user"].display_name
                        ),
                    )
                ],
                maxlen=3,
            )

            embed = discord.Embed(
                description=battle_log[0][1],
                color=self.bot.config.game.primary_colour
            )

            if count == 0:
                log_message = await ctx.send(embed=embed)  # To avoid spam, we'll edit this message later
            else:
                await log_message.edit(embed=embed)

            await asyncio.sleep(4)

            start = datetime.datetime.utcnow()
            attacker, defender = random.sample(players, k=2)

            # Battle logic
            while players[0]["hp"] > 0 and players[1][
                "hp"] > 0 and datetime.datetime.utcnow() < start + datetime.timedelta(minutes=5):
                dmg = attacker["damage"] + Decimal(random.randint(0, 100)) - defender["armor"]
                dmg = max(1, dmg)  # Ensure no negative damage

                defender["hp"] -= dmg
                if defender["hp"] < 0:
                    defender["hp"] = 0

                battle_log.append(
                    (
                        battle_log[-1][0] + 1,
                        _("{attacker} attacks! {defender} takes **{dmg}HP** damage.").format(
                            attacker=attacker["user"].display_name,
                            defender=defender["user"].display_name,
                            dmg=dmg,
                        ),
                    )
                )

                embed = discord.Embed(
                    description=_("{p1} - {hp1} HP left\n{p2} - {hp2} HP left").format(
                        p1=players[0]["user"].display_name,
                        hp1=players[0]["hp"],
                        p2=players[1]["user"].display_name,
                        hp2=players[1]["hp"],
                    ),
                    color=self.bot.config.game.primary_colour,
                )

                for line in battle_log:
                    embed.add_field(
                        name=_("Action #{number}").format(number=line[0]), value=line[1]
                    )

                await log_message.edit(embed=embed)
                await asyncio.sleep(4)
                attacker, defender = defender, attacker  # Switch places

            players = sorted(players, key=lambda x: x["hp"])
            winner = players[1]["user"]
            loser = players[0]["user"]

            if winner.id != ctx.author.id:
                await ctx.send(
                    _("{winner} won the raidbattle vs {loser}!").format(
                        winner=winner.display_name, loser=loser.display_name
                    )
                )
            count = 1

            if winner == ctx.author:
                author_hp = players[1]["hp"]
                score = score + 1
                # If the winner is the ctx.author, continue battling
                await asyncio.sleep(3)  # A delay before finding the next opponent
            else:
                await ctx.send(f"{ctx.author.mention}, were defeated. Your final score was {score}")

                try:

                    highscore = await self.bot.pool.fetchval('SELECT whored FROM profile WHERE "user" = $1',
                                                             ctx.author.id)

                    # Updating the highscore
                    if score > highscore:
                        async with self.bot.pool.acquire() as conn:
                            await conn.execute(
                                'UPDATE profile SET "whored"=$1 WHERE "user"=$2;',
                                score,
                                ctx.author.id,
                            )
                    break
                except Exception as e:
                    await ctx.send(f"An error occurred: {e}")

    async def find_opponentcust(self, ctx):
        count = 0
        score = 0
        player = ctx.author
        user_id = player.id
        luck_booster = await self.bot.get_booster(player, "luck")
        query_class = 'SELECT "class" FROM profile WHERE "user" = $1;'
        query_xp = 'SELECT "xp" FROM profile WHERE "user" = $1;'
        result_author = await self.bot.pool.fetch(query_class, ctx.author.id)
        auth_xp = await self.bot.pool.fetch(query_xp, ctx.author.id)
        base_health = 250
        query = 'SELECT "luck", "health", "stathp" FROM profile WHERE "user" = $1;'

        # Fetch initial stats for the author outside the loop
        async with self.bot.pool.acquire() as conn:
            result = await conn.fetchrow(query, user_id)
            health = result['health'] + base_health
            stathp = result['stathp'] * 50
            dmg_author, deff_author = await self.bot.get_raidstats(player, conn=conn)
            level = rpgtools.xptolevel(auth_xp[0]['xp'])
            total_health_author = health + (level * 5) + stathp
            author_current_hp = total_health_author  # Initialize author's current HP

        while author_current_hp > 0:
            players = []

            # Find a random opponent
            async with self.bot.pool.acquire() as connection:
                while True:
                    query = (
                        'SELECT "user" FROM profile WHERE "user" != $1 '
                        'ORDER BY RANDOM() LIMIT 1'
                    )
                    random_opponent_id = await connection.fetchval(query, ctx.author.id)
                    if random_opponent_id and random_opponent_id != 730276802316206202:
                        break

                if not random_opponent_id:
                    return None  # Couldn't find a suitable opponent

                enemy = await self.bot.fetch_user(random_opponent_id)

            if not enemy:
                return None  # Failed to fetch opponent information

            async with self.bot.pool.acquire() as conn:
                for current_player in (ctx.author, enemy):
                    try:
                        # Define class-related values
                        specified_words_values = {
                            "Deathshroud": 20,
                            "Soul Warden": 30,
                            "Reaper": 40,
                            "Phantom Scythe": 50,
                            "Soul Snatcher": 60,
                            "Deathbringer": 70,
                            "Grim Reaper": 80,
                        }

                        life_steal_values = {
                            "Little Helper": 7,
                            "Gift Gatherer": 14,
                            "Holiday Aide": 21,
                            "Joyful Jester": 28,
                            "Yuletide Guardian": 35,
                            "Festive Enforcer": 40,
                            "Festive Champion": 60,
                        }

                        mage_evolution_levels = {
                            "Witcher": 1,
                            "Enchanter": 2,
                            "Mage": 3,
                            "Warlock": 4,
                            "Dark Caster": 5,
                            "White Sorcerer": 6,
                        }

                        user_id = current_player.id
                        query_class = 'SELECT "class" FROM profile WHERE "user" = $1;'
                        query_xp = 'SELECT "xp" FROM profile WHERE "user" = $1;'

                        # Fetch class and XP data
                        result_player = await self.bot.pool.fetch(query_class, user_id)
                        xp_player = await self.bot.pool.fetch(query_xp, user_id)

                        level_player = rpgtools.xptolevel(xp_player[0]['xp'])

                        chance = 0
                        lifesteal = 0
                        mage_evolution = None

                        if result_player:
                            player_classes = result_player[0]["class"]
                            if not isinstance(player_classes, list):
                                player_classes = [player_classes]

                            def get_mage_evolution(classes):
                                max_evolution = None
                                for class_name in classes:
                                    if class_name in mage_evolution_levels:
                                        level = mage_evolution_levels[class_name]
                                        if max_evolution is None or level > max_evolution:
                                            max_evolution = level
                                return max_evolution

                            mage_evolution = get_mage_evolution(player_classes)

                            for class_name in player_classes:
                                if class_name in specified_words_values:
                                    chance += specified_words_values[class_name]
                                if class_name in life_steal_values:
                                    lifesteal += life_steal_values[class_name]
                        else:
                            await ctx.send(f"User with ID {user_id} not found in the profile table.")
                            continue

                        luck_booster = await self.bot.get_booster(current_player, "luck")
                        query = 'SELECT "luck", "health", "stathp" FROM profile WHERE "user" = $1;'
                        result = await conn.fetchrow(query, user_id)

                        if result:
                            luck_value = float(result['luck'])
                            if luck_value <= 0.3:
                                Luck = 20
                            else:
                                Luck = ((luck_value - 0.3) / (1.5 - 0.3)) * 80 + 20
                            Luck = float(round(Luck, 2))

                            if luck_booster:
                                Luck += Luck * 0.25
                                Luck = float(min(Luck, 100))

                            base_health = 250
                            health1 = result['health'] + base_health
                            stathp2 = result['stathp'] * 50

                            level = rpgtools.xptolevel(xp_player[0]['xp'])
                            total_health2 = health1 + (level * 5)
                            total_health3 = total_health2 + stathp2

                            dmg_current, deff_current = await self.bot.get_raidstats(current_player, conn=conn)

                            if current_player == ctx.author:
                                # Use author's current HP
                                u = {
                                    "user": current_player,
                                    "hp": author_current_hp,  # Persist HP across battles
                                    "armor": deff_author,
                                    "damage": dmg_author,
                                    "luck": Luck,
                                    "mage_evolution": mage_evolution
                                }
                            else:
                                # For enemy, use full health
                                u = {
                                    "user": current_player,
                                    "hp": total_health3,
                                    "armor": deff_current,
                                    "damage": dmg_current,
                                    "luck": Luck,
                                    "mage_evolution": mage_evolution
                                }

                            players.append(u)
                        else:
                            await ctx.send(f"User with ID {user_id} not found in the profile table.")
                    except Exception as e:
                        await ctx.send(f"An error occurred: {e}")


            battle_log = deque(
                [
                    (
                        0,
                        _("Raidbattle {p1} vs. {p2} started!").format(
                            p1=players[0]["user"].display_name,
                            p2=players[1]["user"].display_name
                        ),
                    )
                ],
                maxlen=3,
            )

            embed = discord.Embed(
                description=battle_log[0][1],
                color=self.bot.config.game.primary_colour
            )

            if count == 0:
                log_message = await ctx.send(embed=embed)
            else:
                await log_message.edit(embed=embed)

            await asyncio.sleep(4)

            start = datetime.datetime.utcnow()
            attacker, defender = random.sample(players, k=2)

            # Battle logic
            while players[0]["hp"] > 0 and players[1][
                "hp"] > 0 and datetime.datetime.utcnow() < start + datetime.timedelta(minutes=5):
                dmg = attacker["damage"] + Decimal(random.randint(0, 100)) - defender["armor"]
                dmg = max(1, dmg)  # Ensure no negative damage

                defender["hp"] -= dmg
                if defender["hp"] < 0:
                    defender["hp"] = 0

                battle_log.append(
                    (
                        battle_log[-1][0] + 1,
                        _("{attacker} attacks! {defender} takes **{dmg}HP** damage.").format(
                            attacker=attacker["user"].display_name,
                            defender=defender["user"].display_name,
                            dmg=dmg,
                        ),
                    )
                )

                embed = discord.Embed(
                    description=_("{p1} - {hp1} HP left\n{p2} - {hp2} HP left").format(
                        p1=players[0]["user"].display_name,
                        hp1=players[0]["hp"],
                        p2=players[1]["user"].display_name,
                        hp2=players[1]["hp"],
                    ),
                    color=self.bot.config.game.primary_colour,
                )

                for line in battle_log:
                    embed.add_field(
                        name=_("Action #{number}").format(number=line[0]), value=line[1]
                    )

                await log_message.edit(embed=embed)
                await asyncio.sleep(4)
                attacker, defender = defender, attacker  # Switch roles

            # Determine winner and loser
            players = sorted(players, key=lambda x: x["hp"])
            winner = players[1]["user"]
            loser = players[0]["user"]

            if winner.id != ctx.author.id:
                await ctx.send(
                    _("{winner} won the raidbattle vs {loser}!").format(
                        winner=winner.display_name, loser=loser.display_name
                    )
                )
            count = 1

            if winner == ctx.author:
                author_current_hp = players[1]["hp"]  # Update author's HP for next battle
                score += 1
                await asyncio.sleep(3)  # Delay before next opponent
            else:
                await ctx.send(f"{ctx.author.mention}, you were defeated. Your final score was {score}")

                try:
                    highscore = await self.bot.pool.fetchval(
                        'SELECT whored2 FROM profile WHERE "user" = $1', ctx.author.id
                    )

                    # Update the highscore if the current score is higher
                    if score > highscore:
                        async with self.bot.pool.acquire() as conn:
                            await conn.execute(
                                'UPDATE profile SET "whored2"=$1 WHERE "user"=$2;',
                                score,
                                ctx.author.id,
                            )
                    break
                except Exception as e:
                    await ctx.send(f"An error occurred: {e}")


    @commands.group(aliases=["hd"], invoke_without_command=True)
    @commands.cooldown(1, 300, commands.BucketType.user)
    async def horde(self, ctx):
        """Base 'horde' command (no direct usage)."""
        opponent = await self.find_opponent(ctx)

    # Usage within a command


    @horde.command(name="custom")
    @commands.cooldown(1, 300, commands.BucketType.user)
    async def horde_custom(self, ctx):
        """Horde in custom mode."""
        opponent = await self.find_opponentcust(ctx)

    @battletower.command()
    async def start(self, ctx):

        # Check if the user exists in the database
        try:
            async with self.bot.pool.acquire() as connection:
                user_exists = await connection.fetchval('SELECT 1 FROM battletower WHERE id = $1', ctx.author.id)

            if not user_exists:
                # User doesn't exist in the database
                prologue_embed = discord.Embed(
                    title="Welcome to the Battle Tower",
                    description=(
                        "You stand at the foot of the imposing Battle Tower, a colossal structure that pierces the heavens. "
                        "It is said that the tower was once a place of valor, but it has since fallen into darkness. "
                        "Now, it is a domain of malevolence, home to powerful bosses and their loyal minions."
                    ),
                    color=0xFF5733  # Custom color
                )

                prologue_embed.set_image(url="https://i.ibb.co/s1xx83h/download-3-1.jpg")

                await ctx.send(embed=prologue_embed)

                confirm = await ctx.confirm(
                    message="Do you want to enter the Battle Tower and face its challenges?", timeout=60)

                if confirm is not None:
                    if confirm:
                        # User confirmed to enter the tower
                        async with self.bot.pool.acquire() as connection:
                            await connection.execute('INSERT INTO battletower (id) VALUES ($1)', ctx.author.id)

                        await ctx.send("You have entered the Battle Tower. Good luck on your quest!")
                        return
                    else:
                        await ctx.send("You chose not to enter the Battle Tower. Perhaps another time.")
                        return
                else:
                    # User didn't make a choice within the specified time
                    await ctx.send("You didn't respond in time. Please try again when you're ready.")
                    return

        except Exception as e:
            await ctx.send(f"You didn't respond in time.")

    @has_char()
    @battletower.command()
    async def progress(self, ctx):
        try:
            async with self.bot.pool.acquire() as connection:
                user_exists = await connection.fetchval('SELECT 1 FROM battletower WHERE id = $1', ctx.author.id)

                if not user_exists:
                    await ctx.send("You have not started Battletower. You can start by using `$battletower start`")
                    return

                try:
                    user_level = await connection.fetchval('SELECT level FROM battletower WHERE id = $1', ctx.author.id)

                    # Create a list of levels with challenging names
                    level_names_1 = [
                        "The Tower's Foyer",
                        "Shadowy Staircase",
                        "Chamber of Whispers",
                        "Serpent's Lair",
                        "Halls of Despair",
                        "Crimson Abyss",
                        "Forgotten Abyss",
                        "Dreadlord's Domain",
                        "Gates of Twilight",
                        "Twisted Reflections",
                        "Voidforged Sanctum",
                        "Nexus of Chaos",
                        "Eternal Torment Halls",
                        "Abyssal Desolation",
                        "Cursed Citadel",
                        "The Spire of Shadows",
                        "Tempest's Descent",
                        "Roost of Doombringers",
                        "The Endless Spiral",
                        "Malevolent Apex",
                        "Apocalypse's Abyss",
                        "Chaosborne Throne",
                        "Supreme Darkness",
                        "The Tower's Heart",
                        "The Ultimate Test",
                        "Realm of Annihilation",
                        "Lord of Despair",
                        "Abyssal Overlord",
                        "The End of All",
                        "The Final Confrontation"
                    ]

                    level_names_2 = [
                        "Illusion's Prelude",
                        "Ephemeral Mirage",
                        "Whispers of Redemption",
                        "Veil of Hope",
                        "Specter's Glimmer",
                        "Echoes of Salvation",
                        "Shattered Illusions",
                        "Cacophony of Betrayal",
                        "Doomed Resurgence",
                        "Fading Luminescence",
                        "Despair's Embrace",
                        "Ill-Fated Reverie",
                        "Spectral Deception",
                        "Bittersweet Resonance",
                        "Lament of Broken Dreams",
                        "Puppeteer's Triumph",
                        "Shattered Redemption",
                        "Eternal Betrayal",
                        "Crimson Remorse",
                        "Last breath"
                    ]

                    # Function to generate the formatted level list
                    def generate_level_list(levels, start_level=1):
                        result = "```\n"
                        for level, level_name in enumerate(levels, start=start_level):
                            checkbox = "❌" if level == user_level else "✅" if level < user_level else "❌"
                            result += f"Level {level:<2} {checkbox} {level_name}\n"
                        result += "```"
                        return result

                    # Create embed for levels 1-30
                    prestige_level = await connection.fetchval('SELECT prestige FROM battletower WHERE id = $1',
                                                               ctx.author.id)

                    embed_1 = discord.Embed(
                        title="Battle Tower Progress (Levels 1-30)",
                        description=f"Level: {user_level}\nPrestige Level: {prestige_level}",
                        color=0x0000FF  # Blue color
                    )
                    embed_1.add_field(name="Level Progress", value=generate_level_list(level_names_1), inline=False)
                    embed_1.set_footer(text="**Rewards are granted every 5 levels**")

                    # Send the embeds to the current context (channel)
                    await ctx.send(embed=embed_1)


                except Exception as e:
                    # Handle the exception related to fetching user_level, print or log the error for debugging
                    print(f"Error fetching user_level: {e}")
                    await ctx.send(f"An error occurred while fetching your level {e}.")

        except Exception as e:
            # Handle any exceptions related to database connection, print or log the error for debugging
            print(f"Error accessing the database: {e}")
            await ctx.send("An error occurred while accessing the database.")

    def create_dialogue_page(self, page, level, ctx, name_value, entry_fee_dialogue, dialogue, face_image_url):
        if level == 0:
            # Define settings for level 0 dialogue
            titles = ["Guard", name_value, "Guard", name_value, "Guard"]
            # Check for the first, third, and fifth pages to show the specific avatar
            thumbnails = [
                face_image_url if p in [0, 2, 4]
                else str(ctx.author.avatar.url) if (p in [1, 3] and hasattr(ctx.author, 'avatar'))
                else None
                for p in range(len(entry_fee_dialogue))
            ]
        elif level == 1:
            # Define settings for level 1 dialogue
            titles = ["Abyssal Guardian", name_value, "Abyssal Guardian", "Imp", name_value]
            thumbnails = [face_image_url if p in [0, 2, 4] else "https://i.ibb.co/vYBdn7j/download-7.jpg" for p in
                          range(len(dialogue))]

        dialogue_embed = discord.Embed(
            title=titles[page],
            color=0x003366,
            description=entry_fee_dialogue[page] if level == 0 else dialogue[page]
        )

        if thumbnails[page]:
            dialogue_embed.set_thumbnail(url=thumbnails[page])

        return dialogue_embed

    async def is_player_in_fight(self, player_id):
        # Check if the player is in a fight based on the dictionary
        return player_id in self.fighting_players

    async def add_player_to_fight(self, player_id):
        # Add the player to the fight dictionary with a lock
        self.fighting_players[player_id] = asyncio.Lock()
        await self.fighting_players[player_id].acquire()

    async def remove_player_from_fight(self, player_id):
        # Release the lock and remove the player from the fight dictionary
        if player_id in self.fighting_players:
            self.fighting_players[player_id].release()
            del self.fighting_players[player_id]

    """
    @has_char()
    @user_cooldown(21600)
    @pets.command(brief=_("Let your pet hunt a weapon"))
    @locale_doc
    async def hunt(self, ctx, petid):
        


        query = " # Triple " here
            SELECT * 
            FROM monster_pets 
            WHERE id = $1 AND growth_stage IN ('juvenile', 'adult');
            " # Triple " here
        async with self.bot.pool.acquire() as conn:
            pet_data = await conn.fetchrow(query, petid)

        if not pet_data:
            return await ctx.send(_("Invalid pet ID or your pet is not eligible to hunt."))

        minstat = round(petlvl * 3 * luck_multiply * joy_multiply)
        maxstat = round(petlvl * 6 * luck_multiply * joy_multiply)
        if minstat < 1 or maxstat < 1:
            return await ctx.send(
                _("Your pet is not happy enough to hunt an item. Try making it joyful!")
            )
        item = await self.bot.create_random_item(
            minstat=minstat if minstat < 30 else 30,
            maxstat=maxstat if maxstat < 30 else 30,
            minvalue=1,
            maxvalue=250,
            owner=ctx.author,
        )
        embed = discord.Embed(
            title=_("You gained an item!"),
            description=_("Your pet found an item!"),
            color=0xFF0000,
        )
        embed.set_thumbnail(url=ctx.author.display_avatar.url)
        embed.add_field(name=_("ID"), value=item["id"], inline=False)
        embed.add_field(name=_("Name"), value=item["name"], inline=False)
        embed.add_field(name=_("Type"), value=item["type"], inline=False)
        if item["type"] == "Shield":
            embed.add_field(name=_("Armor"), value=item["armor"], inline=True)
        else:
            embed.add_field(name=_("Damage"), value=item["damage"], inline=True)
        embed.add_field(name=_("Value"), value=f"${item['value']}", inline=False)
        embed.set_footer(text=_("Your pet needs to recover, wait a day to retry"))
        await ctx.send(embed=embed)
        await self.bot.log_transaction(
            ctx,
            from_=1,
            to=ctx.author.id,
            subject="Pet Item Fetch",
            data={"Name": item["name"], "Value": item["value"]},
        )
    """

    @has_char()
    @user_cooldown(5)
    @commands.command(brief=_("Change preference of your Dialogue visability"))
    @locale_doc
    async def btdialogue(self, ctx):
        try:
            async with self.bot.pool.acquire() as connection:
                dialoguetoggle = await connection.fetchval('SELECT dialoguetoggle FROM battletower WHERE "id" = $1',
                                                           ctx.author.id)
                if dialoguetoggle == True:
                    await connection.execute('UPDATE battletower SET dialoguetoggle = FALSE WHERE "id" = $1',
                                             ctx.author.id)
                    await ctx.send("Starting dialogue for Batletowers is now **enabled.**")
                else:
                    await connection.execute('UPDATE battletower SET dialoguetoggle = TRUE WHERE "id" = $1',
                                             ctx.author.id)
                    await ctx.send("Starting dialogue for Batletowers is now **disabled.**")
        except Exception as e:
            await ctx.send(e)

    @has_char()
    @battletower.command()  # Replace with your @battletower.command if needed.
    @user_cooldown(600)
    async def fight(self, ctx):
        # Initial variables and mappings
        authorchance = 0
        fireball_shot = False
        enemychance = 0
        cheated = False
        level = 0  # Temporary: later retrieved from your DB
        victory_description = None

        emoji_to_element = {
            "🌟": "Light",
            "🌑": "Dark",
            "🔥": "Fire",
            "💧": "Water",
            "🌿": "Nature",
            "⚡": "Electric",
            "💨": "Wind",
            "🌀": "Corrupted"
        }
        emotes = {
            "common": "<:F_common:1139514874016309260>",
            "uncommon": "<:F_uncommon:1139514875828252702>",
            "rare": "<:F_rare:1139514880517484666>",
            "magic": "<:F_Magic:1139514865174720532>",
            "legendary": "<:F_Legendary:1139514868400132116>",
            "mystery": "<:F_mystspark:1139521536320094358>",
            "fortune": "<:f_money:1146593710516224090>",
            "divine": "<:f_divine:1169412814612471869>"
        }

        # Retrieve user's battle tower data from DB (example query)
        try:
            async with self.bot.pool.acquire() as connection:
                user_exists = await connection.fetchval('SELECT 1 FROM battletower WHERE id = $1',
                                                        ctx.author.id)
                if not user_exists:
                    await ctx.send(
                        "You have not started Battletower. You can start by using `$battletower start`")
                    await self.bot.reset_cooldown(ctx)
                    return

            async with self.bot.pool.acquire() as connection:
                level = await connection.fetchval('SELECT level FROM battletower WHERE id = $1', ctx.author.id)
                player_balance = await connection.fetchval('SELECT money FROM profile WHERE "user" = $1',
                                                           ctx.author.id)
                god_value = await connection.fetchval('SELECT god FROM profile WHERE "user" = $1',
                                                      ctx.author.id)
                name_value = await connection.fetchval('SELECT name FROM profile WHERE "user" = $1',
                                                       ctx.author.id)
                dialoguetoggle = await connection.fetchval(
                    'SELECT dialoguetoggle FROM battletower WHERE id = $1', ctx.author.id)
        except Exception as e:
            await ctx.send(f"An error occurred: {e}")
            return

        try:
            level_data = self.levels[level]
        except Exception as e:
            pass

        # Prestige logic for level 31 and higher
        if level >= 31:
            egg = True
            if egg:
                confirm_message = "Are you sure you want to prestige? This action will reset your level. Your next run rewards will be completely randomized."
                try:
                    confirm = await ctx.confirm(confirm_message)
                    if confirm:
                        async with self.bot.pool.acquire() as connection:
                            await connection.execute(
                                'UPDATE battletower SET level = 1, prestige = prestige + 1 WHERE id = $1',
                                ctx.author.id)
                        await ctx.send(
                            "You have prestiged. Your level has been reset to 1. The rewards for your next run will be completely randomized.")
                        await self.bot.reset_cooldown(ctx)
                        return
                    else:
                        await ctx.send("Prestige canceled.")
                        await self.bot.reset_cooldown(ctx)
                        return
                except asyncio.TimeoutError:
                    await ctx.send("Prestige canceled due to timeout.")
                    await self.bot.reset_cooldown(ctx)
                    return
            else:
                await self.bot.reset_cooldown(ctx)
                await ctx.send("More coming soon.")
                return

        # ------------------------ Dialogue Sections Begin ------------------------

        # Example for Level 2 dialogue using buttons.
        if dialoguetoggle == False and level == 2:
            level_data = self.levels[level]
            face_image_url = "https://i.ibb.co/G3V00YL/download-2.png"
            level_2_dialogue = [
                f"Vile Serpent: (Emerges from the shadows) You dare trespass upon the Shadowy Staircase, {name_value}? We, the Wraith and the Soul Eater, will be your tormentors.",
                f"{name_value}: (With unwavering determination) I've come to conquer this tower. What sadistic challenges do you have for me now?",
                "Wraith: (With a chilling whisper) Sadistic is an understatement. We're here to break your spirit, to watch you crumble.",
                f"Soul Eater: (With malevolence in its voice) Your bravery will be your undoing, {name_value}. We'll feast on your despair."
            ]

            def create_dialogue_page(page: int) -> discord.Embed:
                if page == 0:
                    title = "Vile Serpent"
                    thumbnail = "https://i.ibb.co/LJcM38s/download-2.png"
                elif page == 1:
                    title = name_value
                    thumbnail = ctx.author.avatar.url if ctx.author.avatar else ctx.author.default_avatar.url
                elif page == 2:
                    title = "Wraith"
                    thumbnail = "https://i.ibb.co/NC2kHpz/download-3.png"
                elif page == 3:
                    title = "Soul Eater"
                    thumbnail = "https://i.ibb.co/BchZsDh/download-7.png"
                embed = discord.Embed(title=title, color=0x003366, description=level_2_dialogue[page])
                embed.set_thumbnail(url=thumbnail)
                return embed

            pages = [create_dialogue_page(page) for page in range(len(level_2_dialogue))]
            view = DialogueView(pages, ctx.author)
            await ctx.send(embed=pages[0], view=view)
            await view.wait()
            await ctx.send("The battle begins!")

        if dialoguetoggle == False and level == 3:
            level_data = self.levels[level]
            face_image_url = "https://i.ibb.co/wLYrp17/download-8.png"
            level_3_dialogue = [
                f"Warlord Grakthar: (Roaring with fury) {name_value}, you've entered the Chamber of Whispers, but it is I, Warlord Grakthar, who commands this chamber. You will bow before me!",
                f"{name_value}: (Unyielding) I've come to conquer this tower. What twisted game are you playing, Warlord?",
                f"Goblin: (With a wicked cackle) Our game is one of torment and despair. You are our plaything, {name_value}.",
                f"Orc: (With a thunderous roar) Your strength won't save you from our might."
            ]

            def create_dialogue_page(page: int) -> discord.Embed:
                if page == 0:
                    title = "Warlord Grakthar"
                    thumbnail = "https://i.ibb.co/wLYrp17/download-8.png"
                elif page == 1:
                    title = name_value
                    thumbnail = ctx.author.avatar.url if ctx.author.avatar else ctx.author.default_avatar.url
                elif page == 2:
                    title = "Goblin"
                    thumbnail = "https://i.ibb.co/nfMcsry/download-10.png"
                elif page == 3:
                    title = "Orc"
                    thumbnail = "https://i.ibb.co/30HY5Jx/download-9.png"
                embed = discord.Embed(title=title, color=0x003366, description=level_3_dialogue[page])
                embed.set_thumbnail(url=thumbnail)
                return embed

            pages = [create_dialogue_page(page) for page in range(len(level_3_dialogue))]
            view = DialogueView(pages, ctx.author)
            await ctx.send(embed=pages[0], view=view)
            await view.wait()
            await ctx.send("The battle begins!")

        if dialoguetoggle == False and level == 4:
            level_data = self.levels[level]
            face_image_url = "https://i.ibb.co/wLYrp17/download-8.png"
            level_4_dialogue = [
                f"Necromancer Voss: (Raising his staff, emitting an eerie aura) Welcome to the Serpent's Lair, {name_value}. I am the Necromancer Voss, and this is my domain. Prepare for your doom.",
                f"{name_value}: (With unwavering resolve) I've come to conquer the tower. What relentless nightmare do you have in store, Voss?",
                f"Skeleton: (With a malevolent laugh) Nightmares are our specialty. You won't escape our grasp, {name_value}.",
                f"Zombie: (With an eerie moan) We will feast upon your despair."
            ]

            def create_dialogue_page(page: int) -> discord.Embed:
                if page == 0:
                    title = "Necromancer Voss"
                    thumbnail = "https://i.ibb.co/G5DrFfv/download-13.jpg"
                elif page == 1:
                    title = name_value
                    thumbnail = ctx.author.avatar.url if ctx.author.avatar else ctx.author.default_avatar.url
                elif page == 2:
                    title = "Skeleton"
                    thumbnail = "https://i.ibb.co/zS26jYD/download-12.jpg"
                elif page == 3:
                    title = "Zombie"
                    thumbnail = "https://i.ibb.co/5L6V446/download-11.jpg"
                embed = discord.Embed(title=title, color=0x003366, description=level_4_dialogue[page])
                embed.set_thumbnail(url=thumbnail)
                return embed

            pages = [create_dialogue_page(page) for page in range(len(level_4_dialogue))]
            view = DialogueView(pages, ctx.author)
            await ctx.send(embed=pages[0], view=view)
            await view.wait()
            await ctx.send("The battle begins!")

        if dialoguetoggle == False and level == 5:
            level_data = self.levels[level]
            face_image_url = "https://i.ibb.co/wLYrp17/download-8.png"
            level_5_dialogue = [
                f"Blackblade Marauder: (Drawing a wicked blade) You've reached the Halls of Despair, {name_value}, but it is I, the Blackblade Marauder, who governs this realm. Prepare for annihilation.",
                f"{name_value}: (Unyielding) I've come this far, and I won't be deterred. What torment do you have for me, Marauder?",
                f"Bandit: (With a sinister laugh) Torment is our art. You'll crumble under our assault, {name_value}.",
                f"Highwayman: (With malevolence in his eyes) We'll break you, one way or another."
            ]

            def create_dialogue_page(page: int) -> discord.Embed:
                if page == 0:
                    title = "Blackblade Marauder"
                    thumbnail = "https://i.ibb.co/0BdGZBn/download-14.jpg"
                elif page == 1:
                    title = name_value
                    thumbnail = ctx.author.avatar.url if ctx.author.avatar else ctx.author.default_avatar.url
                elif page == 2:
                    title = "Bandit"
                    thumbnail = "https://i.ibb.co/gzsJR55/download-15.jpg"
                elif page == 3:
                    title = "Highwayman"
                    thumbnail = "https://i.ibb.co/zX0rXsP/download-18.jpg"
                embed = discord.Embed(title=title, color=0x003366, description=level_5_dialogue[page])
                embed.set_thumbnail(url=thumbnail)
                return embed

            pages = [create_dialogue_page(page) for page in range(len(level_5_dialogue))]
            view = DialogueView(pages, ctx.author)
            await ctx.send(embed=pages[0], view=view)
            await view.wait()
            await ctx.send("The battle begins!")

        if dialoguetoggle == False and level == 6:
            level_data = self.levels[level]
            face_image_url = "https://i.ibb.co/0rGtfC9/3d-illustration-dark-purple-spider-260nw-2191752107.png"
            level_6_dialogue = [
                f"Arachnok Queen: (Emerges from a web of silk) {name_value}, you have ventured into the Crimson Abyss. I am the Arachnok Queen, and this is my web. Tremble before my fangs.",
                f"{name_value}: (With unwavering determination) Enough of your games, Arachnok Queen. My journey continues, and I'll crush your illusions beneath my heel.",
                f"Spiderling: (With skittering legs) Illusions that shroud your path in darkness.",
                f"Venomous Arachnid: (With a poisonous hiss) We'll savor the moment your courage wanes."
            ]

            def create_dialogue_page(page: int) -> discord.Embed:
                if page == 0:
                    title = "Arachnok Queen"
                    thumbnail = "https://i.ibb.co/0rGtfC9/3d-illustration-dark-purple-spider-260nw-2191752107.png"
                elif page == 1:
                    title = name_value
                    thumbnail = ctx.author.avatar.url if ctx.author.avatar else ctx.author.default_avatar.url
                elif page == 2:
                    title = "Spiderling"
                    thumbnail = "https://i.ibb.co/RDXvXcD/download-19.jpg"
                elif page == 3:
                    title = "Venomous Arachnid"
                    thumbnail = "https://i.ibb.co/XZPcqCY/download-20.jpg"
                embed = discord.Embed(title=title, color=0x003366, description=level_6_dialogue[page])
                embed.set_thumbnail(url=thumbnail)
                return embed

            pages = [create_dialogue_page(page) for page in range(len(level_6_dialogue))]
            view = DialogueView(pages, ctx.author)
            await ctx.send(embed=pages[0], view=view)
            await view.wait()
            await ctx.send("The battle begins!")

        if dialoguetoggle == False and level == 7:
            level_data = self.levels[level]
            face_image_url = "https://i.ibb.co/4jF6z29/download-22.jpg"
            level_7_dialogue = [
                f"Lich Lord Moros: (Rising from the ethereal mist) {name_value}, you stand upon the Forgotten Abyss. I am the Lich Lord Moros, and this realm is my spectral dominion. Your fate is sealed.",
                f"{name_value}: (With resolute determination) Your illusions won't deter me, Lich Lord Moros. I'll shatter your spectral veil and press on.",
                f"Wisp: (With a haunting glow) Veil of the forgotten and the lost.",
                f"Specter: (With an otherworldly presence) You'll become a forgotten memory."
            ]

            def create_dialogue_page(page: int) -> discord.Embed:
                if page == 0:
                    title = "Lich Lord Moros"
                    thumbnail = "https://i.ibb.co/4jF6z29/download-22.jpg"
                elif page == 1:
                    title = name_value
                    thumbnail = ctx.author.avatar.url if ctx.author.avatar else ctx.author.default_avatar.url
                elif page == 2:
                    title = "Wisp"
                    thumbnail = "https://i.ibb.co/J3PJzPR/download-26.jpg"
                elif page == 3:
                    title = "Specter"
                    thumbnail = "https://i.ibb.co/XZPcqCY/download-20.jpg"
                embed = discord.Embed(title=title, color=0x003366, description=level_7_dialogue[page])
                embed.set_thumbnail(url=thumbnail)
                return embed

            pages = [create_dialogue_page(page) for page in range(len(level_7_dialogue))]
            view = DialogueView(pages, ctx.author)
            await ctx.send(embed=pages[0], view=view)
            await view.wait()
            await ctx.send("The battle begins!")

        if dialoguetoggle == False and level == 8:
            level_data = self.levels[level]
            face_image_url = "https://i.ibb.co/YWSkgYx/download-27.jpg"
            level_8_dialogue = [
                f"Frostfire Behemoth: (Rising from the molten core) {name_value}, you have entered the Dreadlord's Domain, my domain. I am the Frostfire Behemoth, and I shall incinerate your hopes.",
                f"{name_value}: (With fierce determination) You will find no mercy in the heart of the dreadlord, Frostfire Behemoth. Your flames won't consume me.",
                "Frost Imp: (With icy flames) Flames that burn with unrelenting fury.",
                "Ice Elemental: (With a frigid gaze) We'll snuff out your defiance."
            ]

            def create_dialogue_page(page: int) -> discord.Embed:
                if page == 0:
                    title = "Frostfire Behemoth"
                    thumbnail = "https://i.ibb.co/YWSkgYx/download-27.jpg"
                elif page == 1:
                    title = name_value
                    thumbnail = ctx.author.avatar.url if ctx.author.avatar else ctx.author.default_avatar.url
                elif page == 2:
                    title = "Frost Imp"
                    thumbnail = "https://i.ibb.co/5M6zTB4/download-28.jpg"
                elif page == 3:
                    title = "Ice Elemental"
                    thumbnail = "https://i.ibb.co/ssLVKWv/download-29.jpg"
                embed = discord.Embed(title=title, color=0x003366, description=level_8_dialogue[page])
                embed.set_thumbnail(url=thumbnail)
                return embed

            pages = [create_dialogue_page(page) for page in range(len(level_8_dialogue))]
            view = DialogueView(pages, ctx.author)
            await ctx.send(embed=pages[0], view=view)
            await view.wait()
            await ctx.send("The battle begins!")

        if dialoguetoggle == False and level == 9:
            level_data = self.levels[level]
            face_image_url = "https://i.ibb.co/GC8V9cq/download-31.jpg"
            level_9_dialogue = [
                f"Dragonlord Zaldrak: (Emerging from the icy winds) {name_value}, you tread upon the Frozen Abyss. I am the Dragonlord Zaldrak, and your presence chills me to the bone.",
                f"{name_value}: (With steely resolve) I've come to conquer the tower. What frigid challenges lie ahead, Dragonlord Zaldrak?",
                f"Lizardman: (With reptilian cunning) Challenges as cold as the abyss itself. Will your spirit thaw in the face of despair?",
                f"Dragonkin: (With a fiery breath) We shall engulf you in frost and flame."
            ]

            def create_dialogue_page(page: int) -> discord.Embed:
                if page == 0:
                    title = "Dragonlord Zaldrak"
                    thumbnail = "https://i.ibb.co/Q7VMzD0/download-30.jpg"
                elif page == 1:
                    title = name_value
                    thumbnail = ctx.author.avatar.url if ctx.author.avatar else ctx.author.default_avatar.url
                elif page == 2:
                    title = "Lizardman"
                    thumbnail = "https://i.ibb.co/GC8V9cq/download-31.jpg"
                elif page == 3:
                    title = "Dragonkin"
                    thumbnail = "https://i.ibb.co/2ckDS1k/download-32.jpg"
                embed = discord.Embed(title=title, color=0x003366, description=level_9_dialogue[page])
                embed.set_thumbnail(url=thumbnail)
                return embed

            pages = [create_dialogue_page(page) for page in range(len(level_9_dialogue))]
            view = DialogueView(pages, ctx.author)
            await ctx.send(embed=pages[0], view=view)
            await view.wait()
            await ctx.send("The battle begins!")

        if dialoguetoggle == False and level == 10:
            level_data = self.levels[level]
            face_image_url = "https://i.ibb.co/5TYNLrc/download-33.jpg"
            level_10_dialogue = [
                f"Soulreaver Lurkthar: (Manifesting from the void) {name_value}, you have reached the Ethereal Nexus, a realm beyond your comprehension. I am Soulreaver Lurkthar, and you are insignificant.",
                f"{name_value}: (With unyielding determination) I've come this far. What secrets does this realm hold, Soulreaver Lurkthar?",
                "Haunted Spirit: (With spectral whispers) Secrets that unravel sanity and defy reality. Are you prepared for the abyss of the unknown?",
                "Phantom Wraith: (With an ethereal presence) Your mind will crumble in the presence of the enigma."
            ]

            def create_dialogue_page(page: int) -> discord.Embed:
                if page == 0:
                    title = "Soulreaver Lurkthar"
                    thumbnail = "https://i.ibb.co/5TYNLrc/download-33.jpg"
                elif page == 1:
                    title = name_value
                    thumbnail = ctx.author.avatar.url if ctx.author.avatar else ctx.author.default_avatar.url
                elif page == 2:
                    title = "Haunted Spirit"
                    thumbnail = "https://i.ibb.co/kB5ypsM/download-34.jpg"
                elif page == 3:
                    title = "Phantom Wraith"
                    thumbnail = "https://i.ibb.co/6BTRt3s/download-35.jpg"
                embed = discord.Embed(title=title, color=0x003366, description=level_10_dialogue[page])
                embed.set_thumbnail(url=thumbnail)
                return embed

            pages = [create_dialogue_page(page) for page in range(len(level_10_dialogue))]
            view = DialogueView(pages, ctx.author)
            await ctx.send(embed=pages[0], view=view)
            await view.wait()
            await ctx.send("The battle begins!")

        if dialoguetoggle == False and level == 11:
            level_data = self.levels[level]
            face_image_url = "https://i.ibb.co/5TYNLrc/download-33.jpg"
            level_11_dialogue = [
                f"Ravengaze Alpha: (Rising from the shadows) {name_value}, you have ventured into the dreaded Ravengaze Highlands. I am the Ravengaze Alpha, and this is my hunting ground. Prepare for your demise.",
                f"{name_value}: (With indomitable resolve) I've come to conquer this tower. What challenges await, Ravengaze Alpha?",
                f"Gnoll Raider: (With savage fervor) Challenges that will make you pray for mercy. Do you have what it takes to survive?",
                f"Hyena Pack: (With menacing laughter) *growls*"
            ]

            def create_dialogue_page(page: int) -> discord.Embed:
                if page == 0:
                    title = "Ravengaze Alpha"
                    thumbnail = "https://i.ibb.co/YjqfWSc/download-8.jpg"
                elif page == 1:
                    title = name_value
                    thumbnail = ctx.author.avatar.url if ctx.author.avatar else ctx.author.default_avatar.url
                elif page == 2:
                    title = "Gnoll Raider"
                    thumbnail = "https://i.ibb.co/kJyTsWL/download-11.jpg"
                elif page == 3:
                    title = "Hyena Pack"
                    thumbnail = "https://i.ibb.co/Y7w2Sy4/download-12.jpg"
                embed = discord.Embed(title=title, color=0x003366, description=level_11_dialogue[page])
                embed.set_thumbnail(url=thumbnail)
                return embed

            pages = [create_dialogue_page(page) for page in range(len(level_11_dialogue))]
            view = DialogueView(pages, ctx.author)
            await ctx.send(embed=pages[0], view=view)
            await view.wait()
            await ctx.send("The battle begins!")

        if dialoguetoggle == False and level == 12:
            level_data = self.levels[level]
            face_image_url = "https://i.ibb.co/5TYNLrc/download-33.jpg"
            level_12_dialogue = [
                f"Nightshade Serpentis: (Emerging from the shadows) {name_value}, you stand within the cursed Nocturne Domain. I am Nightshade Serpentis, and your fate is sealed.",
                f"{name_value}: (With unwavering determination) I've come to conquer the tower. What nightmares do you bring, Nightshade Serpentis?",
                f"Gloomhound: (With eerie howling) Nightmares that will haunt your every thought. Do you have the courage to face them?",
                f"Nocturne Stalker: (With a sinister grin) Your resolve will crumble under the weight of your own dread."
            ]

            def create_dialogue_page(page: int) -> discord.Embed:
                if page == 0:
                    title = "Nightshade Serpentis"
                    thumbnail = "https://i.ibb.co/4TtY6T9/download-14.jpg"
                elif page == 1:
                    title = name_value
                    thumbnail = ctx.author.avatar.url if ctx.author.avatar else ctx.author.default_avatar.url
                elif page == 2:
                    title = "Gloomhound"
                    thumbnail = "https://i.ibb.co/0BGmFXZ/download-15.jpg"
                elif page == 3:
                    title = "Nocturne Stalker"
                    thumbnail = "https://i.ibb.co/svhv2XJ/download-16.jpg"
                embed = discord.Embed(title=title, color=0x003366, description=level_12_dialogue[page])
                embed.set_thumbnail(url=thumbnail)
                return embed

            pages = [create_dialogue_page(page) for page in range(len(level_12_dialogue))]
            view = DialogueView(pages, ctx.author)
            await ctx.send(embed=pages[0], view=view)
            await view.wait()
            await ctx.send("The battle begins!")

        if dialoguetoggle == False and level == 13:
            level_data = self.levels[level]
            face_image_url = "https://i.ibb.co/5TYNLrc/download-33.jpg"
            level_13_dialogue = [
                f"Ignis Inferno: (Rising from molten flames) {name_value}, you have entered the Pyroclasmic Abyss, a realm of searing torment. I am Ignis Inferno, and your presence will fuel the flames of destruction.",
                f"{name_value}: (Unyielding) I've come to conquer this tower. What scorching challenges do you present, Ignis Inferno?",
                f"Magma Elemental: (With fiery rage) Challenges as relentless as the molten core itself. Are you prepared to endure the unending inferno?",
                f"Inferno Imp: (With malevolent glee) Your flesh will sear, and your spirit will smolder."
            ]

            def create_dialogue_page(page: int) -> discord.Embed:
                if page == 0:
                    title = "Ignis Inferno"
                    thumbnail = "https://i.ibb.co/HYcdZBy/download-17.jpg"
                elif page == 1:
                    title = name_value
                    thumbnail = ctx.author.avatar.url if ctx.author.avatar else ctx.author.default_avatar.url
                elif page == 2:
                    title = "Magma Elemental"
                    thumbnail = "https://i.ibb.co/K0tG23M/download-18.jpg"
                elif page == 3:
                    title = "Inferno Imp"
                    thumbnail = "https://i.ibb.co/2ZgBn44/download-20.jpg"
                embed = discord.Embed(title=title, color=0x003366, description=level_13_dialogue[page])
                embed.set_thumbnail(url=thumbnail)
                return embed

            pages = [create_dialogue_page(page) for page in range(len(level_13_dialogue))]
            view = DialogueView(pages, ctx.author)
            await ctx.send(embed=pages[0], view=view)
            await view.wait()
            await ctx.send("The battle begins!")

        if dialoguetoggle == False and level == 14:
            level_data = self.levels[level]
            face_image_url = "https://i.ibb.co/5TYNLrc/download-33.jpg"
            level_14_dialogue = [
                f"Wraithlord Maroth: (Emerging from the spectral mists) {name_value}, you have reached the spectral wastes, a realm of eternal torment. I am Wraithlord Maroth, and your suffering will echo through the void.",
                f"{name_value}: (With unwavering determination) I've come to conquer the tower. What spectral horrors await, Wraithlord Maroth?",
                f"Cursed Banshee: (With haunting wails) Horrors that will rend your soul asunder. Do you have the will to endure?",
                f"Spectral Harbinger: (With a malevolent whisper) Your torment shall be everlasting."
            ]

            def create_dialogue_page(page: int) -> discord.Embed:
                if page == 0:
                    title = "Wraithlord Maroth"
                    thumbnail = "https://i.ibb.co/56dsQMY/download-21.jpg"
                elif page == 1:
                    title = name_value
                    thumbnail = ctx.author.avatar.url if ctx.author.avatar else ctx.author.default_avatar.url
                elif page == 2:
                    title = "Cursed Banshee"
                    thumbnail = "https://i.ibb.co/pLP2djF/download-22.jpg"
                elif page == 3:
                    title = "Spectral Harbinger"
                    thumbnail = "https://i.ibb.co/R0PdqJ7/download-23.jpg"
                embed = discord.Embed(title=title, color=0x003366, description=level_14_dialogue[page])
                embed.set_thumbnail(url=thumbnail)
                return embed

            pages = [create_dialogue_page(page) for page in range(len(level_14_dialogue))]
            view = DialogueView(pages, ctx.author)
            await ctx.send(embed=pages[0], view=view)
            await view.wait()
            await ctx.send("The battle begins!")

        if dialoguetoggle == False and level == 15:
            level_data = self.levels[level]
            face_image_url = "https://i.ibb.co/5TYNLrc/download-33.jpg"
            level_15_dialogue = [
                f"Infernus, the Infernal: (Emerging from the depths of fire) {name_value}, you have entered the Infernal Abyss, a realm of unrelenting flames. I am Infernus, the Infernal, and your existence will be consumed by the inferno.",
                f"{name_value}: (Unyielding) I've come this far, and I won't be deterred. What blazing trials do you have in store, Infernus?",
                f"Demonic Imp: (With a malevolent grin) Trials that will scorch your very soul. Are you prepared to burn?",
                f"Hellspawn Reaver: (With fiery eyes) The flames of your doom shall be unquenchable."
            ]

            def create_dialogue_page(page: int) -> discord.Embed:
                if page == 0:
                    title = "Infernus, the Infernal"
                    thumbnail = "https://i.ibb.co/R2Nm6vY/download-24.jpg"
                elif page == 1:
                    title = name_value
                    thumbnail = ctx.author.avatar.url if ctx.author.avatar else ctx.author.default_avatar.url
                elif page == 2:
                    title = "Demonic Imp"
                    thumbnail = "https://i.ibb.co/GdhXTWN/download-25.jpg"
                elif page == 3:
                    title = "Hellspawn Reaver"
                    thumbnail = "https://i.ibb.co/ZftX1xB/download-26.jpg"
                embed = discord.Embed(title=title, color=0x003366, description=level_15_dialogue[page])
                embed.set_thumbnail(url=thumbnail)
                return embed

            pages = [create_dialogue_page(page) for page in range(len(level_15_dialogue))]
            view = DialogueView(pages, ctx.author)
            await ctx.send(embed=pages[0], view=view)
            await view.wait()
            await ctx.send("The battle begins!")

        # For level 16, which has additional random user dialogues.
        if dialoguetoggle == False and level == 16:
            async with self.bot.pool.acquire() as connection:
                query = 'SELECT "user" FROM profile WHERE "user" != $1 ORDER BY RANDOM() LIMIT 2'
                random_users = await connection.fetch(query, ctx.author.id)
                random_user_objects = []
                for user in random_users:
                    user_id = user['user']
                    fetched_user = await self.bot.fetch_user(user_id)
                    if fetched_user:
                        random_user_objects.append(fetched_user)
                if len(random_user_objects) >= 2:
                    random_user_object_1 = random_user_objects[0]
                    random_user_object_2 = random_user_objects[1]
                else:
                    return
            level_data = self.levels[level]
            face_image_url = "https://gcdnb.pbrd.co/images/ueKgTmbvB8qb.jpg"
            level_16_dialogue = [
                f"Master Shapeshifter: In the dance of shadows, I am the conductor—every face you've known, every trust betrayed, I've worn like a symphony; now, join my orchestra or become its crescendo.",
                f"{name_value}: In your game of deceit, I see only a feeble attempt to shroud the inevitable. Your illusions crumble against my unyielding will—cross me, and witness the true horror of defiance.",
                f"{random_user_object_1.display_name}: I mimic your friend's form, but within me, your worst nightmares lurk, a puppeteer of your trust, feeding on your doubt and fear, reveling in the impending doom.",
                f"{random_user_object_2.display_name}: I've assumed your confidant's guise, yet beneath this borrowed skin, your anxieties writhe, whispering your secrets; in the labyrinth of your mind, I'm the embodiment of your darkest apprehensions, ready to consume your hopes."
            ]

            def create_dialogue_page(page: int) -> discord.Embed:
                if page == 0:
                    title = "Master Shapeshifter"
                    thumbnail = "https://gcdnb.pbrd.co/images/ueKgTmbvB8qb.jpg"
                elif page == 1:
                    title = name_value
                    thumbnail = ctx.author.avatar.url if ctx.author.avatar else "https://ia803204.us.archive.org/4/items/discordprofilepictures/discordblue.png"
                elif page == 2:
                    title = random_user_object_1.display_name
                    thumbnail = random_user_object_1.avatar.url if random_user_object_1.avatar else "https://ia803204.us.archive.org/4/items/discordprofilepictures/discordblue.png"
                elif page == 3:
                    title = random_user_object_2.display_name
                    thumbnail = random_user_object_2.avatar.url if random_user_object_2.avatar else "https://ia803204.us.archive.org/4/items/discordprofilepictures/discordblue.png"
                embed = discord.Embed(title=title, color=0x003366, description=level_16_dialogue[page])
                embed.set_thumbnail(url=thumbnail)
                return embed

            pages = [create_dialogue_page(page) for page in range(len(level_16_dialogue))]
            view = DialogueView(pages, ctx.author)
            await ctx.send(embed=pages[0], view=view)
            await view.wait()
            await ctx.send("The battle begins!")

        # Levels 17 through 30 – simply send "The battle begins!" or add further dialogue as needed.
        if dialoguetoggle == False and level in [17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30]:
            # For level 17 in this example we show a dialogue block with buttons.
            if level == 17:
                level_data = self.levels[level]
                face_image_url = "https://i.ibb.co/R2v9jYs/image2.png"
                level_17_dialogue = [
                    f"Eldritch Devourer: (Rising from the cosmic abyss) {name_value}, you stand at the Convergence Nexus, a junction of cosmic forces. I am the Eldritch Devourer, and your futile resistance will be devoured by the void.",
                    f"{name_value}: (Fierce) I've carved my path through the chaos, and your cosmic feast won't satiate your hunger. Prepare for annihilation, Devourer.",
                    f"Chaos Fiend: (With malicious glee) Annihilation, you say? The chaos you face is beyond comprehension. Your defiance is merely a flicker against the impending cosmic storm.",
                    f"Voidborn Horror: (With eyes like swirling galaxies) Your essence will dissipate into the cosmic winds. Prepare for oblivion, interloper."
                ]

                def create_dialogue_page(page: int) -> discord.Embed:
                    if page == 0:
                        title = "Eldritch Devourer"
                        thumbnail = "https://i.ibb.co/R2v9jYs/image2.png"
                    elif page == 1:
                        title = name_value
                        thumbnail = ctx.author.avatar.url if ctx.author.avatar else ctx.author.default_avatar.url
                    elif page == 2:
                        title = "Chaos Fiend"
                        thumbnail = "https://i.ibb.co/c22vsWF/image.png"
                    elif page == 3:
                        title = "Voidborn Horror"
                        thumbnail = "https://i.ibb.co/kyvTszF/image3.png"
                    embed = discord.Embed(title=title, color=0x003366, description=level_17_dialogue[page])
                    embed.set_thumbnail(url=thumbnail)
                    return embed

                pages = [create_dialogue_page(page) for page in range(len(level_17_dialogue))]
                view = DialogueView(pages, ctx.author)
                await ctx.send(embed=pages[0], view=view)
                await view.wait()
                await ctx.send("The battle begins!")
            else:
                await ctx.send("The battle begins!")

        # If dialoguetoggle is True then simply send this message (and similar for level 16 if needed)
        if dialoguetoggle:
            if level != 16:
                await ctx.send("The battle begins!")
            if level == 16:
                # For level 16 in dialoguetoggle mode, re-run the random user query (if needed) and send dialogue.
                async with self.bot.pool.acquire() as connection:
                    query = 'SELECT "user" FROM profile WHERE "user" != $1 ORDER BY RANDOM() LIMIT 2'
                    random_users = await connection.fetch(query, ctx.author.id)
                    random_user_objects = []
                    for user in random_users:
                        user_id = user['user']
                        fetched_user = await self.bot.fetch_user(user_id)
                        if fetched_user:
                            random_user_objects.append(fetched_user)
                    if len(random_user_objects) >= 2:
                        random_user_object_1 = random_user_objects[0]
                        random_user_object_2 = random_user_objects[1]
                    else:
                        return
                # (You could repeat the same dialogue block as above for level 16 here if desired.)
                await ctx.send("The battle begins!")

        # -----------------------------------------------------------------------
        # Level 0 – the entry fee dialogue, with buttons.
        if level == 0:
            entry_fee = 10000
            if player_balance < entry_fee:
                await self.bot.reset_cooldown(ctx)
                return await ctx.send(
                    f"{ctx.author.mention}, you do not have enough money to pay the entry fee. Consider earning at least **$10,000** before approaching the Battle Tower.")
            else:
                confirm = await ctx.confirm(
                    message="Are you sure you want to proceed with this level? It will cost you **$10,000** This is a one time fee.",
                    timeout=10)
                try:
                    if confirm is not None:
                        await ctx.send("You chose to approach the gates.")
                    else:
                        await self.bot.reset_cooldown(ctx)
                        await ctx.send("You chose not to approach the gates.")
                        return
                except Exception as e:
                    await ctx.send(f"An error occurred: {e}")
                    await self.bot.reset_cooldown(ctx)
                    return

            entry_fee_dialogue = [
                "Guard: Halt, brave traveler! You now stand before the awe-inspiring entrance to the Battle Tower, a place where legends are forged and glory awaits. However, passage through this imposing gate comes at a price, a test of your commitment to the path of champions.",
                f"{name_value}: (Your eyes are fixed on the grand tower) How much must I offer to open this formidable gate?",
                "Guard: (The guardian, armored and stern, lowers their towering spear) The entry fee, is no trifling matter. It demands a substantial **$10,000**. Prove your dedication by paying this fee now, and the path of champions shall be unveiled before you.",
                f"{name_value}: (Resolute and unwavering) Very well, here is **$10,000**, a token of my unwavering resolve.",
                "Guard: (With a slow nod of approval) Your decision is wise, traveler. With your payment, you have taken your first step into the hallowed tower. Now, proceed to level 1, where the Abyssal Guardian awaits your challenge. Be prepared for the battles that lie ahead."
            ]

            def create_dialogue_page(page: int) -> discord.Embed:
                # Use “Guard” as title for the first and fourth dialogue; otherwise alternate with the player’s name.
                if page == 0:
                    title = "Guard"
                    thumbnail = "https://i.ibb.co/CWTp4xf/download.jpg"
                elif page == 1:
                    title = name_value
                    thumbnail = ctx.author.avatar.url if ctx.author.avatar else ctx.author.default_avatar.url
                elif page == 2:
                    title = "Guard"
                    thumbnail = "https://i.ibb.co/CWTp4xf/download.jpg"
                elif page == 3:
                    title = name_value
                    thumbnail = ctx.author.avatar.url if ctx.author.avatar else ctx.author.default_avatar.url
                elif page == 4:
                    title = "Guard"
                    thumbnail = "https://i.ibb.co/CWTp4xf/download.jpg"
                embed = discord.Embed(title=title, color=0x003366, description=entry_fee_dialogue[page])
                embed.set_thumbnail(url=thumbnail)
                return embed

            entry_fee_pages = [create_dialogue_page(page) for page in range(len(entry_fee_dialogue))]
            view = DialogueView(entry_fee_pages, ctx.author)
            await ctx.send(embed=entry_fee_pages[0], view=view)
            await view.wait()
            # Once dialogue is done, remove fee and update level.
            async with self.bot.pool.acquire() as connection:
                if player_balance < entry_fee:
                    return await ctx.send("An error has occurred: You can no longer afford this.")
                await connection.execute('UPDATE profile SET money = money - $1 WHERE "user" = $2', entry_fee,
                                         ctx.author.id)
                await connection.execute('UPDATE battletower SET level = level + 1 WHERE id = $1',
                                         ctx.author.id)
            await self.bot.reset_cooldown(ctx)
            return await ctx.send(
                f"{ctx.author.mention}, you've paid the entry fee of ${entry_fee}. You may proceed to level 1 using `$battletower fight`.")

        try:


            def select_target(targets, player_prob=0.60, pet_prob=0.40):
                """
                Selects a target from the given list based on provided probabilities.
                - player_prob: Probability of selecting the player.
                - pet_prob: Probability of selecting the pet.
                """
                # Filter out None values from the targets
                valid_targets = [target for target in targets if target]

                if not valid_targets:
                    return None  # No valid targets to select

                rand = randomm.random()
                cumulative = 0.0
                for target in valid_targets:
                    if target.get("is_pet"):
                        cumulative += pet_prob
                    else:
                        cumulative += player_prob

                    if rand < cumulative:
                        return target

                return valid_targets[-1]  # Fallback to the last target
            # Initialize variables
            max_hp_limit = 5000
            authorchance = 0
            cheated = False
            battle_log = deque(maxlen=5)
            battle_log.append("**Action #0**\nBattle Tower battle started!")
            action_number = 1

            # Fetch level data (assuming level_data is defined elsewhere)
            if level == 16:
                async with self.bot.pool.acquire() as conn:
                    minion1atk, minion1def = await self.bot.get_raidstats(random_user_object_1, conn=conn)
                    minion2atk, minion2def = await self.bot.get_raidstats(random_user_object_2, conn=conn)

                minion1_name = random_user_object_1.display_name
                minion2_name = random_user_object_2.display_name
                boss_name = level_data["boss_name"]
                boss_stats = level_data["boss"]

            else:

                minion1_name = level_data["minion1_name"]
                minion2_name = level_data["minion2_name"]
                boss_name = level_data["boss_name"]
                minion1_stats = level_data["minion1"]
                minion2_stats = level_data["minion2"]
                boss_stats = level_data["boss"]

            async with self.bot.pool.acquire() as conn:
                current_player = ctx.author  # Fixed: Assign ctx.author directly instead of iterating
                try:
                    # Define class-related values
                    specified_words_values = {
                        "Deathshroud": 20,
                        "Soul Warden": 30,
                        "Reaper": 40,
                        "Phantom Scythe": 50,
                        "Soul Snatcher": 60,
                        "Deathbringer": 70,
                        "Grim Reaper": 80,
                    }

                    life_steal_values = {
                        "Little Helper": 7,
                        "Gift Gatherer": 14,
                        "Holiday Aide": 21,
                        "Joyful Jester": 28,
                        "Yuletide Guardian": 35,
                        "Festive Enforcer": 40,
                        "Festive Champion": 60,
                    }

                    mage_evolution_levels = {
                        "Witcher": 1,
                        "Enchanter": 2,
                        "Mage": 3,
                        "Warlock": 4,
                        "Dark Caster": 5,
                        "White Sorcerer": 6,
                    }

                    evolution_damage_multiplier = {
                        1: 1.10,  # 110%
                        2: 1.20,  # 120%
                        3: 1.30,  # 130%
                        4: 1.50,  # 150%
                        5: 1.75,  # 175%
                        6: 2.00,  # 200%
                    }

                    user_id = current_player.id
                    query_class = 'SELECT "class" FROM profile WHERE "user" = $1;'
                    query_xp = 'SELECT "xp" FROM profile WHERE "user" = $1;'

                    # Fetch class and XP data using fetchrow since we expect only one record
                    result_player = await self.bot.pool.fetchrow(query_class, user_id)
                    xp_player = await self.bot.pool.fetchrow(query_xp, user_id)

                    if xp_player and 'xp' in xp_player:
                        level_player = rpgtools.xptolevel(xp_player['xp'])
                    else:
                        await ctx.send(f"XP data for user with ID {user_id} not found in the profile table.")
                        raise Exception("XP data not found in profile table.")

                    chance = 0
                    lifesteal = 0
                    mage_evolution = None

                    if result_player and 'class' in result_player:
                        player_classes = result_player["class"]
                        if not isinstance(player_classes, list):
                            player_classes = [player_classes]

                        def get_mage_evolution(classes):
                            max_evolution = None
                            for class_name in classes:
                                if class_name in mage_evolution_levels:
                                    level = mage_evolution_levels[class_name]
                                    if max_evolution is None or level > max_evolution:
                                        max_evolution = level
                            return max_evolution

                        mage_evolution = get_mage_evolution(player_classes)

                        for class_name in player_classes:
                            if class_name in specified_words_values:
                                chance += specified_words_values[class_name]
                            if class_name in life_steal_values:
                                lifesteal += life_steal_values[class_name]
                    else:
                        await ctx.send(f"User with ID {user_id} not found in the profile table.")
                        # Removed 'continue' since we're no longer in a loop
                        raise Exception("User not found in profile table.")

                    luck_booster = await self.bot.get_booster(current_player, "luck")
                    query = 'SELECT "luck", "health", "stathp" FROM profile WHERE "user" = $1;'
                    result = await conn.fetchrow(query, user_id)

                    if result:
                        luck_value = float(result['luck'])
                        if luck_value <= 0.3:
                            Luck = 20
                        else:
                            Luck = ((luck_value - 0.3) / (1.5 - 0.3)) * 80 + 20
                        Luck = float(round(Luck, 2))

                        if luck_booster:
                            Luck += Luck * 0.25
                            Luck = float(min(Luck, 100))

                        base_health = 250
                        health1 = result['health'] + base_health
                        stathp2 = result['stathp'] * 50

                        # Reuse level_player if already calculated
                        total_health2 = health1 + (level_player * 5)
                        total_health3 = total_health2 + stathp2

                        dmg_current, deff_current = await self.bot.get_raidstats(current_player, conn=conn)

                    else:
                        await ctx.send(f"User with ID {user_id} not found in the profile table.")
                        raise Exception("User not found in profile table.")
                except Exception as e:
                    await self.remove_player_from_fight(ctx.author.id)
                    await ctx.send(f"An error occurred: {e}")
                    raise  # Re-raise exception to be caught by outer try-except

            # Fetch player data and combatants
            async with self.bot.pool.acquire() as conn:
                try:
                    # Fetch highest element
                    highest_element_author = await self.fetch_highest_element(ctx.author.id)

                    # Fetch classes, XP, and other stats
                    result_author = await conn.fetchrow('SELECT "class", "xp" FROM profile WHERE "user" = $1;',
                                                        ctx.author.id)
                    if result_author and 'class' in result_author and 'xp' in result_author:
                        auth_classes = result_author["class"] if isinstance(result_author["class"], list) else [
                            result_author["class"]]
                        auth_xp = result_author["xp"]
                    else:
                        await ctx.send(f"User with ID {user_id} not found in the profile table.")
                        raise Exception("Author data not found in profile table.")

                    auth_level = rpgtools.xptolevel(auth_xp)

                    # Calculate chances and lifesteal
                    author_chance = 0
                    lifestealauth = 0
                    mage_evolution = None

                    if auth_classes:
                        mage_evolution = get_mage_evolution(auth_classes)
                        for class_name in auth_classes:
                            if class_name in specified_words_values:
                                author_chance += specified_words_values[class_name]
                            if class_name in life_steal_values:
                                lifestealauth += life_steal_values[class_name]

                    if author_chance != 0:
                        authorchance = author_chance

                    # Fetch combatants (player and pet)
                    player_combatant, pet_combatant = await self.fetch_combatants(
                        ctx, ctx.author, highest_element_author, auth_level, lifestealauth, mage_evolution, conn
                    )
                except Exception as e:
                    await self.remove_player_from_fight(ctx.author.id)
                    await ctx.send(f"An error occurred while fetching combatants: {e}")
                    raise  # Re-raise exception to be caught by outer try-except

            async with self.bot.pool.acquire() as conn:
                try:
                    prestige_level = await conn.fetchval('SELECT prestige FROM battletower WHERE id = $1',
                                                         ctx.author.id)
                    level = await conn.fetchval('SELECT level FROM battletower WHERE id = $1', ctx.author.id)
                except Exception as e:
                    await self.remove_player_from_fight(ctx.author.id)
                    await ctx.send(f"An error occurred while fetching prestige data: {e}")
                    raise Exception("Prestige data fetch failed.")

            if prestige_level and prestige_level != 0:
                prestige_multiplier = 1 + (0.25 * prestige_level)
                prestige_multiplierhp = 1 + (0.20 * prestige_level)
            else:
                prestige_multiplier = 1
                prestige_multiplierhp = 1

            # Initialize opponents with prestige multipliers
            if level == 16:
                opponents = [
                    {
                        "user": minion1_name,
                        "hp": int(round(float(250) * prestige_multiplierhp)),
                        "max_hp": int(round(float(250) * prestige_multiplierhp)),
                        "armor": int(round(float(minion1def) * prestige_multiplier)),
                        "damage": int(round(float(minion1atk) * prestige_multiplier)),
                        "is_pet": False,
                        "element": "unknown"  # Ensure 'element' key exists
                    },
                    {
                        "user": minion2_name,
                        "hp": int(round(float(150) * prestige_multiplierhp)),
                        "max_hp": int(round(float(150) * prestige_multiplierhp)),
                        "armor": int(round(float(minion2def) * prestige_multiplier)),
                        "damage": int(round(float(minion2atk) * prestige_multiplier)),
                        "is_pet": False,
                        "element": "unknown"
                    },
                    {
                        "user": boss_name,
                        "hp": int(round(float(boss_stats["hp"]) * prestige_multiplierhp)),
                        "max_hp": int(round(float(boss_stats["hp"]) * prestige_multiplierhp)),
                        "armor": int(round(float(boss_stats["armor"]) * prestige_multiplier)),
                        "damage": int(round(float(boss_stats["damage"]) * prestige_multiplier)),
                        "is_pet": False,
                        "element": boss_stats.get("element", "unknown")
                    },
                ]

            else:
                opponents = [
                    {
                        "user": minion1_name,
                        "hp": int(round(minion1_stats["hp"] * prestige_multiplierhp)),
                        "max_hp": int(round(minion1_stats["hp"] * prestige_multiplierhp)),
                        "armor": int(round(minion1_stats["armor"] * prestige_multiplier)),
                        "damage": int(round(minion1_stats["damage"] * prestige_multiplier)),
                        "is_pet": False,
                        "element": minion1_stats.get("element", "unknown")  # Ensure 'element' key exists
                    },
                    {
                        "user": minion2_name,
                        "hp": int(round(minion2_stats["hp"] * prestige_multiplierhp)),
                        "max_hp": int(round(minion2_stats["hp"] * prestige_multiplierhp)),
                        "armor": int(round(minion2_stats["armor"] * prestige_multiplier)),
                        "damage": int(round(minion2_stats["damage"] * prestige_multiplier)),
                        "is_pet": False,
                        "element": minion2_stats.get("element", "unknown")
                    },
                    {
                        "user": boss_name,
                        "hp": int(round(boss_stats["hp"] * prestige_multiplierhp)),
                        "max_hp": int(round(boss_stats["hp"] * prestige_multiplierhp)),
                        "armor": int(round(boss_stats["armor"] * prestige_multiplier)),
                        "damage": int(round(boss_stats["damage"] * prestige_multiplier)),
                        "is_pet": False,
                        "element": boss_stats.get("element", "unknown")
                    },
                ]




            # Initialize 'winner' to None
            winner = None

            # Create initial embed with the first opponent
            current_opponent = opponents[0]
            embed = discord.Embed(
                title=f"Battle Tower: {ctx.author.display_name} vs {current_opponent['user']}",
                color=self.bot.config.game.primary_colour
            )

            # Add player and pet status
            for combatant in [player_combatant, pet_combatant]:
                if not combatant:
                    continue
                current_hp = max(0, round(combatant["hp"], 1))
                max_hp = round(combatant["max_hp"], 1)
                hp_bar = self.create_hp_bar(current_hp, max_hp)
                element_emoji = "❌"  # Default emoji
                for emoji, element in emoji_to_element.items():
                    if element == combatant["element"]:
                        element_emoji = emoji
                        break
                field_name = f"**[TEAM A]** \n{combatant['user'].display_name} {element_emoji}" if not combatant.get(
                    "is_pet") else f"{combatant['pet_name']} {element_emoji}"
                field_value = f"HP: {current_hp:.1f}/{max_hp:.1f}\n{hp_bar}"
                embed.add_field(name=field_name, value=field_value, inline=False)

            # Add current opponent status
            opponent_element = current_opponent.get("element", "unknown")  # Assuming opponents have 'element'
            opponent_emoji = emoji_to_element.get(opponent_element, "❌")
            current_opponent_field = f"**[TEAM B]** \n{current_opponent['user']} {opponent_emoji}"
            current_opponent_hp = max(0, round(current_opponent["hp"], 1))
            current_opponent_max_hp = round(current_opponent["max_hp"], 1)
            current_opponent_hp_bar = self.create_hp_bar(current_opponent_hp, current_opponent_max_hp)
            embed.add_field(name=current_opponent_field,
                            value=f"HP: {current_opponent_hp:.1f}/{current_opponent_max_hp:.1f}\n{current_opponent_hp_bar}",
                            inline=False)

            # Add battle log
            battle_log = deque(maxlen=5)
            battle_log.append(f"**Action #0**\nBattle started against {current_opponent['user']}!")
            embed.add_field(name="Battle Log", value=battle_log[0], inline=False)

            # Send initial embed
            log_message = await ctx.send(embed=embed)
            await asyncio.sleep(4)

            # Start battle loop
            start_time = datetime.datetime.utcnow()
            battle_ongoing = True
            opponent_index = 0  # Track current opponent
            current_turn = 0  # Start turn tracker
            action_number = 1  # Initialize action counter.
            fireball_chance = 100

            turn_order_options = [
                [player_combatant, pet_combatant],  # Team A
                [current_opponent]  # Team B
            ]

            randomm.shuffle(turn_order_options)

            combatant_order = turn_order_options[0] + turn_order_options[1]  # Merge teams into combatant_order

            while battle_ongoing and datetime.datetime.utcnow() < start_time + datetime.timedelta(minutes=9):
                if opponent_index >= len(opponents):
                    break  # All opponents defeated

                # Ensure combatant_order always includes the current opponent
                combatant_order = [player_combatant, pet_combatant, current_opponent]

                # Determine the current combatant based on turn
                combatant = combatant_order[current_turn % len(combatant_order)]
                current_turn += 1  # Increment turn tracker

                if not combatant or combatant["hp"] <= 0:
                    continue  # Skip if combatant is invalid or dead

                # Determine target
                if combatant in [player_combatant, pet_combatant]:
                    target = current_opponent  # Player's turn: attack the current opponent
                else:
                    target = select_target(
                        [c for c in [player_combatant, pet_combatant] if c and c["hp"] > 0],
                        player_prob=0.60,
                        pet_prob=0.40
                    )  # Opponent's turn: attack player or pet

                if target is not None:
                    # Calculate base damage before armor
                    damage_variance = randomm.randint(0, 100) if not combatant.get("is_pet") else randomm.randint(0,
                                                                                                                  50)
                    fireball_shot = False

                    if not combatant.get("is_pet") and combatant["user"] == ctx.author:
                        if target["user"] != ctx.author:
                            if combatant.get("mage_evolution") is not None:
                                fireball_chance = randomm.randint(1, 100)
                                if fireball_chance <= 30:
                                    # Fireball happens
                                    evolution_level = combatant["mage_evolution"]
                                    damage_multiplier = evolution_damage_multiplier.get(evolution_level, 1.0)

                                    # Calculate damage using Decimals for precision
                                    base_damage = Decimal(combatant["damage"])
                                    random_damage = Decimal(randomm.randint(0, 100))
                                    target_armor = Decimal(target["armor"])
                                    damage_mult = Decimal(damage_multiplier)

                                    dmg_decimal = (base_damage + random_damage - target_armor) * damage_mult
                                    dmg_decimal = max(dmg_decimal, Decimal('1'))

                                    # Store blocked damage for reflection
                                    blocked_damage = min(float(base_damage + random_damage), float(target_armor))

                                    # Convert Decimal to float for compatibility with lifesteal
                                    dmg = float(round(dmg_decimal, 2))

                                    # Apply damage to target
                                    target["hp"] -= dmg

                                    # Format the Fireball message
                                    message = _(
                                        "You cast Fireball! **{monster}** takes **{dmg} HP** damage.").format(
                                        monster=target["user"],
                                        dmg=dmg
                                    )
                                    fireball_shot = True
                                else:
                                    # Regular attack calculation with reflection tracking
                                    raw_damage = combatant["damage"] + damage_variance
                                    blocked_damage = min(raw_damage, target["armor"])
                                    dmg = round(max(raw_damage - target["armor"], 1), 3)
                                    target["hp"] -= dmg
                                    target["hp"] = max(target["hp"], 0)
                            else:
                                # Regular attack calculation with reflection tracking
                                raw_damage = combatant["damage"] + damage_variance
                                blocked_damage = min(raw_damage, target["armor"])
                                dmg = round(max(raw_damage - target["armor"], 1), 3)
                                target["hp"] -= dmg
                                target["hp"] = max(target["hp"], 0)
                        else:
                            # Regular attack calculation with reflection tracking
                            raw_damage = combatant["damage"] + damage_variance
                            blocked_damage = min(raw_damage, target["armor"])
                            dmg = round(max(raw_damage - target["armor"], 1), 3)
                            target["hp"] -= dmg
                            target["hp"] = max(target["hp"], 0)
                    else:
                        # Regular attack calculation with reflection tracking
                        raw_damage = combatant["damage"] + damage_variance
                        blocked_damage = min(raw_damage, target["armor"])
                        dmg = round(max(raw_damage - target["armor"], 1), 3)
                        target["hp"] -= dmg
                        target["hp"] = max(target["hp"], 0)

                    # Build attack message
                    if combatant.get("is_pet"):
                        attacker_name = combatant['pet_name']
                    else:
                        attacker_name = combatant['user'].mention if isinstance(combatant['user'],
                                                                                discord.User) else combatant['user']

                    if target.get("is_pet"):
                        target_name = target['pet_name']
                    else:
                        target_name = target['user'].mention if isinstance(target['user'], discord.User) else \
                            target['user']

                    if not fireball_shot:
                        message = f"{attacker_name} attacks! {target_name} takes **{dmg:.1f}HP** damage."

                    # Handle damage reflection if target is a tank
                    if target.get("damage_reflection", 0) > 0:
                        reflected_damage = round(blocked_damage * target["damage_reflection"], 3)
                        if reflected_damage > 0:
                            combatant["hp"] -= reflected_damage
                            combatant["hp"] = max(combatant["hp"], 0)
                            message += f"\n{target_name}'s armor reflects **{reflected_damage:.3f}HP** damage back!"

                            # Check if attacker died from reflection
                            if combatant["hp"] <= 0:
                                message += f" {attacker_name} has been defeated by reflected damage!"

                    # Handle lifesteal if applicable
                    if not combatant.get("is_pet") and combatant["user"] == ctx.author and lifestealauth != 0:
                        lifesteal_percentage = lifestealauth / 100.0
                        heal = round(lifesteal_percentage * dmg, 1)
                        combatant["hp"] = min(combatant["hp"] + heal, combatant["max_hp"])
                        message += f" Lifesteals: **{heal:.1f}HP**"

                    # Check if target is defeated
                    if target["hp"] <= 0:

                        if target["user"] == ctx.author and not target.get("is_pet"):
                            #await ctx.send(author_chance)
                            target["hp"] = 0
                            # Handle Cheating Death for the player being attacked
                            if not cheated:
                                chance = author_chance
                                random_number = randomm.randint(1, 100)
                                #await ctx.send(random_number)
                                if random_number <= chance:
                                    target["hp"] = 75
                                    cheated = True
                                    message += _(f"\n\n{ctx.author} cheat death and survive with **75HP**")
                                else:
                                    message += f" {target_name} has been defeated!"
                        else:
                            message += f" {target_name} has been defeated!"

                        # Append the final attack message
                        battle_log.append(f"**Action #{action_number}**\n{message}")
                        action_number += 1

                        # Update embed to reflect the final attack
                        embed = discord.Embed(
                            title=f"Battle Tower: {ctx.author.display_name} vs {current_opponent['user']}",
                            color=self.bot.config.game.primary_colour
                        )

                        # Add player and pet status
                        for c in [player_combatant, pet_combatant]:
                            if not c:
                                continue
                            current_hp = max(0, round(c["hp"], 1))
                            max_hp = round(c["max_hp"], 1)
                            hp_bar = self.create_hp_bar(current_hp, max_hp)
                            element_emoji = "❌"  # Default emoji
                            for emoji, element in emoji_to_element.items():
                                if element == c["element"]:
                                    element_emoji = emoji
                                    break
                            field_name = f"**[TEAM A]** \n{c['user'].display_name} {element_emoji}" if not c.get(
                                "is_pet") else f"{c['pet_name']} {element_emoji}"
                            field_value = f"HP: {current_hp:.1f}/{max_hp:.1f}\n{hp_bar}"
                            embed.add_field(name=field_name, value=field_value, inline=False)

                        # Add current opponent status (should be 0 HP)
                        opponent_element = current_opponent.get("element", "unknown")
                        opponent_emoji = emoji_to_element.get(opponent_element, "❌")
                        current_opponent_field = f"**[TEAM B]** \n{current_opponent['user']} {opponent_emoji}"
                        current_opponent_hp = max(0, round(current_opponent["hp"], 1))
                        current_opponent_max_hp = round(current_opponent["max_hp"], 1)
                        current_opponent_hp_bar = self.create_hp_bar(current_opponent_hp, current_opponent_max_hp)
                        embed.add_field(name=current_opponent_field,
                                        value=f"HP: {current_opponent_hp:.1f}/{current_opponent_max_hp:.1f}\n{current_opponent_hp_bar}",
                                        inline=False)

                        # Add battle log
                        battle_log_text = '\n\n'.join(battle_log)
                        embed.add_field(name="Battle Log", value=battle_log_text, inline=False)

                        # Update embed with the final attack
                        await log_message.edit(embed=embed)
                        await asyncio.sleep(4)  # Allow players to see the final attack

                        if target["user"] == ctx.author and not target.get("is_pet"):
                            if target["hp"] <= 0:
                                break

                        # Transition to the next opponent
                        if target == current_opponent:
                            opponent_index += 1
                            if opponent_index < len(opponents):
                                current_opponent = opponents[opponent_index]  # Update to the next opponent

                                # Reset turn order and action counter
                                combatant_order = [player_combatant, pet_combatant, current_opponent]
                                current_turn = 0  # Reset turn tracker
                                action_number = 1  # Reset the action counter
                                battle_log = deque(maxlen=5)  # Reset battle log
                                battle_log.append(
                                    f"**Action #0**\nBattle started against {current_opponent['user']}!")

                                # Create new embed for the next opponent
                                embed = discord.Embed(
                                    title=f"Battle Tower: {ctx.author.display_name} vs {current_opponent['user']}",
                                    color=self.bot.config.game.primary_colour
                                )

                                # Add player and pet status
                                for c in [player_combatant, pet_combatant]:
                                    if not c:
                                        continue
                                    current_hp = max(0, round(c["hp"], 1))
                                    max_hp = round(c["max_hp"], 1)
                                    hp_bar = self.create_hp_bar(current_hp, max_hp)
                                    element_emoji = "❌"  # Default emoji
                                    for emoji, element in emoji_to_element.items():
                                        if element == c["element"]:
                                            element_emoji = emoji
                                            break
                                    field_name = f"**[TEAM A]** \n{c['user'].display_name} {element_emoji}" if not c.get(
                                        "is_pet") else f"{c['pet_name']} {element_emoji}"
                                    field_value = f"HP: {current_hp:.1f}/{max_hp:.1f}\n{hp_bar}"
                                    embed.add_field(name=field_name, value=field_value, inline=False)

                                # Add new opponent status
                                opponent_element = current_opponent.get("element", "unknown")
                                opponent_emoji = emoji_to_element.get(opponent_element, "❌")
                                current_opponent_field = f"**[TEAM B]** \n{current_opponent['user']} {opponent_emoji}"
                                current_opponent_hp = max(0, round(current_opponent["hp"], 1))
                                current_opponent_max_hp = round(current_opponent["max_hp"], 1)
                                current_opponent_hp_bar = self.create_hp_bar(current_opponent_hp,
                                                                             current_opponent_max_hp)
                                embed.add_field(name=current_opponent_field,
                                                value=f"HP: {current_opponent_hp:.1f}/{current_opponent_max_hp:.1f}\n{current_opponent_hp_bar}",
                                                inline=False)

                                # Add battle log
                                battle_log_text = '\n\n'.join(battle_log)
                                embed.add_field(name="Battle Log", value=battle_log_text, inline=False)

                                # Update embed for the new opponent
                                await log_message.edit(embed=embed)
                                await ctx.send(f"**Battle started with {current_opponent['user']}!**")
                                await asyncio.sleep(4)
                            else:
                                # All opponents defeated
                                battle_ongoing = False
                                winner = ctx.author
                                break

                    else:
                        # Append to battle log if target wasn't defeated
                        battle_log.append(f"**Action #{action_number}**\n{message}")
                        action_number += 1

                        # Update embed with current status
                        embed = discord.Embed(
                            title=f"Battle Tower: {ctx.author.display_name} vs {current_opponent['user']}",
                            color=self.bot.config.game.primary_colour
                        )

                        # Add player and pet status
                        for c in [player_combatant, pet_combatant]:
                            if not c:
                                continue
                            current_hp = max(0, round(c["hp"], 1))
                            max_hp = round(c["max_hp"], 1)
                            hp_bar = self.create_hp_bar(current_hp, max_hp)
                            element_emoji = "❌"  # Default emoji
                            for emoji, element in emoji_to_element.items():
                                if element == c["element"]:
                                    element_emoji = emoji
                                    break

                            # Add tank indicator if applicable
                            tank_indicator = "🛡️" if c.get("tank_evolution") and c.get("has_shield") else ""

                            field_name = f"**[TEAM A]** \n{c['user'].display_name} {element_emoji} {tank_indicator}" if not c.get(
                                "is_pet") else f"{c['pet_name']} {element_emoji}"

                            field_value = f"HP: {current_hp:.1f}/{max_hp:.1f}\n{hp_bar}"

                            # Add reflection percentage for tanks
                            if c.get("damage_reflection", 0) > 0:
                                reflection_percent = c["damage_reflection"] * 100
                                field_value += f"\nDamage Reflection: {reflection_percent:.1f}%"

                            embed.add_field(name=field_name, value=field_value, inline=False)

                        # Add current opponent status
                        opponent_element = current_opponent.get("element", "unknown")
                        opponent_emoji = emoji_to_element.get(opponent_element, "❌")
                        current_opponent_field = f"**[TEAM B]** \n{current_opponent['user']} {opponent_emoji}"
                        current_opponent_hp = max(0, round(current_opponent["hp"], 1))
                        current_opponent_max_hp = round(current_opponent["max_hp"], 1)
                        current_opponent_hp_bar = self.create_hp_bar(current_opponent_hp, current_opponent_max_hp)
                        embed.add_field(name=current_opponent_field,
                                        value=f"HP: {current_opponent_hp:.1f}/{current_opponent_max_hp:.1f}\n{current_opponent_hp_bar}",
                                        inline=False)

                        # Add battle log
                        battle_log_text = '\n\n'.join(battle_log)
                        embed.add_field(name="Battle Log", value=battle_log_text, inline=False)

                        # Edit the embed message
                        await log_message.edit(embed=embed)
                        await asyncio.sleep(4)
                # After the loop, declare the winner
            if winner == ctx.author:
                await ctx.send(
                        f"**Congratulations {ctx.author.mention}! You have defeated all opponents!**")

            else:
                await ctx.send(f"**{ctx.author.mention}**, you have been defeated. Better luck next time!")
                await self.remove_player_from_fight(ctx.author.id)
                return




        except Exception as e:
            import traceback
            await self.remove_player_from_fight(ctx.author.id)
            error_message = f"An error occurred during the battletower battle: {e}\n{traceback.format_exc()}"
            await ctx.send(error_message)
            print(error_message)
            await self.bot.reset_cooldown(ctx)
            return



        if victory_description:
            await ctx.send(victory_description)
        else:

            level_names = [
                "The Tower's Foyer",
                "Shadowy Staircase",
                "Chamber of Whispers",
                "Serpent's Lair",
                "Halls of Despair",
                "Crimson Abyss",
                "Forgotten Abyss",
                "Dreadlord's Domain",
                "Gates of Twilight",
                "Twisted Reflections",
                "Voidforged Sanctum",
                "Nexus of Chaos",
                "Eternal Torment Halls",
                "Abyssal Desolation",
                "Cursed Citadel",
                "The Spire of Shadows",
                "Tempest's Descent",
                "Roost of Doombringers",
                "The Endless Spiral",
                "Malevolent Apex",
                "Apocalypse's Abyss",
                "Chaosborne Throne",
                "Supreme Darkness",
                "The Tower's Heart",
                "The Ultimate Test",
                "Realm of Annihilation",
                "Lord of Despair",
                "Abyssal Overlord",
                "The End of All",
                "The Final Confrontation"
            ]

            level_name = level_names[level - 1]

            if level == 1:
                victory_embed = discord.Embed(
                    title="Victory!",
                    description=(
                        "As the dust settles, you stand victorious over the fallen minions and the defeated Abyssal Guardian, "
                        "its ominous form dissipating into the shadows. The floor is now free from its grasp, "
                        "and the path to treasure lies ahead."
                    ),
                    color=0x00ff00  # Green color for success
                )
                await ctx.send(embed=victory_embed)

                # Create an embed for the treasure chest options
                chest_embed = discord.Embed(
                    title="Choose Your Treasure",
                    description=(
                        "You have a choice to make: Before you lie two treasure chests, each shimmering with an otherworldly aura. "
                        "The left chest appears ancient and ornate, while the right chest is smaller but radiates a faint magical glow."
                        f"{ctx.author.mention}, Type `left` or `right` to make your decision. You have 2 minutes!"
                    ),
                    color=0x0055ff  # Blue color for options
                )
                chest_embed.set_footer(text=f"Type left or right to make your decision.")
                await ctx.send(embed=chest_embed)

                async with self.bot.pool.acquire() as connection:
                    prestige_level = await connection.fetchval('SELECT prestige FROM battletower WHERE id = $1',
                                                               ctx.author.id)
                    level = await connection.fetchval('SELECT level FROM battletower WHERE id = $1', ctx.author.id)

                def check(m):
                    return m.author == ctx.author and m.content.lower() in ['left', 'right']

                import random
                if prestige_level >= 1:
                    new_level = level + 1

                    async with self.bot.pool.acquire() as connection:
                        left_reward_type = random.choice(['crate', 'money'])
                        right_reward_type = random.choice(['crate', 'money'])

                        if left_reward_type == 'crate':
                            left_options = ['legendary', 'fortune', 'mystery', 'common', 'uncommon', 'magic',
                                            'rare']
                            left_weights = [1, 1, 80, 170, 150, 20, 75]  # Weighted values according to percentages
                            left_crate_type = random.choices(left_options, left_weights)[0]
                        else:
                            left_money_amount = random.choice(
                                [10000, 15000, 20000, 50000, 25000, 10000, 27000, 33000, 100000, 5000, 150000])

                        if right_reward_type == 'crate':
                            right_options = ['legendary', 'fortune', 'mystery', 'common', 'uncommon', 'magic',
                                             'rare']
                            right_weights = [1, 1, 80, 170, 150, 20, 75]  # Weighted values according to percentages
                            right_crate_type = random.choices(right_options, right_weights)[0]
                        else:
                            right_money_amount = random.choice(
                                [10000, 15000, 20000, 50000, 25000, 10000, 27000, 33000, 100000, 5000, 150000])

                        await ctx.send(
                            "You see two chests: one on the left and one on the right. Which one do you choose? (Type 'left' or 'right')")

                        try:
                            msg = await self.bot.wait_for('message', check=check, timeout=60.0)
                            choice = msg.content.lower()
                        except asyncio.TimeoutError:
                            choice = random.choice(["left", "right"])
                            await ctx.send('You took too long to decide. The chest will be chosen at random.')

                            try:
                                await self.remove_player_from_fight(ctx.author.id)
                            except Exception as e:
                                pass




                        if choice == 'left':
                            if left_reward_type == 'crate':
                                await ctx.send(
                                    f'You open the chest on the left and find a {emotes[left_crate_type]} crate!')
                                await connection.execute(
                                    f'UPDATE profile SET crates_{left_crate_type} = crates_{left_crate_type} + 1 WHERE "user" = $1',
                                    ctx.author.id)
                                unchosen_reward = right_reward_type
                                if unchosen_reward == 'crate':
                                    await ctx.send(
                                        f'You could have gotten a {emotes[right_crate_type]} crate if you chose the right chest.')
                                else:
                                    await ctx.send(
                                        f'You could have gotten **${right_money_amount}** if you chose the right chest.')
                            else:
                                await ctx.send(f'You open the chest on the left and find **${left_money_amount}**!')
                                await connection.execute('UPDATE profile SET money = money + $1 WHERE "user" = $2',
                                                         left_money_amount, ctx.author.id)
                                unchosen_reward = right_reward_type
                                if unchosen_reward == 'crate':
                                    await ctx.send(
                                        f'You could have gotten a {emotes[right_crate_type]} crate if you chose the right chest.')
                                else:
                                    await ctx.send(
                                        f'You could have gotten **${right_money_amount}** if you chose the right chest.')
                        else:
                            if right_reward_type == 'crate':
                                await ctx.send(
                                    f'You open the chest on the right and find a {emotes[right_crate_type]} crate!')
                                await connection.execute(
                                    f'UPDATE profile SET crates_{right_crate_type} = crates_{right_crate_type} + 1 WHERE "user" = $1',
                                    ctx.author.id)
                                unchosen_reward = left_reward_type
                                if unchosen_reward == 'crate':
                                    await ctx.send(
                                        f'You could have gotten a {emotes[left_crate_type]} crate if you chose the left chest.')
                                else:
                                    await ctx.send(
                                        f'You could have gotten **${left_money_amount}** if you chose the left chest.')
                            else:
                                await ctx.send(
                                    f'You open the chest on the right and find **${right_money_amount}**!')
                                await connection.execute('UPDATE profile SET money = money + $1 WHERE "user" = $2',
                                                         right_money_amount, ctx.author.id)
                                unchosen_reward = left_reward_type
                                if unchosen_reward == 'crate':
                                    await ctx.send(
                                        f'You could have gotten a {emotes[left_crate_type]} crate if you chose the left chest.')
                                else:
                                    await ctx.send(
                                        f'You could have gotten **${left_money_amount}** if you chose the left chest.')

                        await ctx.send(f'You have advanced to floor: {new_level}')
                        await connection.execute('UPDATE battletower SET level = level + 1 WHERE id = $1',
                                                 ctx.author.id)
                        try:
                            await self.remove_player_from_fight(ctx.author.id)
                        except Exception as e:
                            pass

                        #--------------------------
                        # --------------------------
                        # --------------------------
                else:
                    def check(m):
                        return m.author == ctx.author and m.content.lower() in ['left', 'right']

                    try:
                        msg = await self.bot.wait_for('message', check=check, timeout=120.0)
                        choice = msg.content.lower()
                    except asyncio.TimeoutError:
                        newlevel = level + 1
                        choice = random.choice(["left", "right"])
                        await ctx.send('You took too long to decide. The chest will be chosen at random.')


                    if choice is not None:
                        newlevel = level + 1
                        if choice == 'left':
                            await ctx.send(
                                'You open the chest on the left and find: <:F_rare:1139514880517484666> A '
                                'rare Crate!')
                            await ctx.send(f'You have advanced to floor: {newlevel}')
                            async with self.bot.pool.acquire() as connection:
                                await connection.execute(
                                    'UPDATE profile SET crates_rare = crates_rare + 1 WHERE "user" '
                                    '= $1', ctx.author.id)
                                await connection.execute('UPDATE battletower SET level = level + 1 WHERE id = $1',
                                                         ctx.author.id)
                        else:
                            await ctx.send('You open the chest on the right and find: Nothing, bad luck!')
                            async with self.bot.pool.acquire() as connection:
                                await connection.execute('UPDATE battletower SET level = level + 1 WHERE id = $1',
                                                         ctx.author.id)
                            await ctx.send(f'You have advanced to floor: {newlevel}')
            if level == 2:
                victory_embed = discord.Embed(
                    title="Triumphant Conquest!",
                    description=(
                        "A deafening silence falls upon the Shadowy Staircase as the lifeless forms of Wraith and Soul Eater lay shattered at your feet. "
                        "The Vile Serpent writhes in agony, its malevolent presence vanquished by your unwavering determination."
                        "\n\nThe darkness recedes, unveiling a newfound path ahead, leading you deeper into the mysterious Battle Tower."
                    ),
                    color=0x00ff00  # Green color for success
                )
                await ctx.send(embed=victory_embed)

                # Create an embed for the treasure chest options
                newlevel = level + 1
                async with self.bot.pool.acquire() as connection:
                    await connection.execute('UPDATE battletower SET level = level + 1 WHERE id = $1',
                                             ctx.author.id)
                await ctx.send(f'You have advanced to floor: {newlevel}')

            if level == 3:
                victory_embed = discord.Embed(
                    title="Triumph Over Warlord Grakthar!",
                    description=(
                        "The war drums of the Chamber of Whispers have fallen silent, and the imposing Warlord Grakthar lies defeated. "
                        "His goblin and orc minions cower in fear as your indomitable spirit overcame their darkness."
                        "\n\nThe chamber, once filled with dread, now echoes with your resounding victory, and the path ahead beckons with unknown challenges."
                    ),
                    color=0x00ff00  # Green color for success
                )

                await ctx.send(embed=victory_embed)

                newlevel = level + 1
                async with self.bot.pool.acquire() as connection:
                    await connection.execute('UPDATE battletower SET level = level + 1 WHERE id = $1',
                                             ctx.author.id)
                await ctx.send(f'You have advanced to floor: {newlevel}')

            if level == 6:
                victory_embed = discord.Embed(
                    title="Arachnok Queen Defeated!",
                    description=(
                        f"As you stand amidst the shattered webs and the defeated {minion1_name}s and {minion2_name}s, a tense silence envelops the Crimson Abyss. "
                        f"The Arachnok Queen, a monstrous ruler of arachnids, has been vanquished, her venomous web dismantled, and her reign of terror put to an end."
                        "\n\nAs you take a moment to catch your breath, you notice a peculiar artifact hidden within the queen's lair. This ancient relic begins to glow with an eerie light, and when you touch it, a vision unfolds before your eyes."
                        "\n\nIn the vision, you see the tower as it once was, a beacon of hope and valor. But it's gradually consumed by darkness, as an otherworldly entity known as the 'Eclipse Wraith' appears. This malevolent being hungers for the tower's immense power and begins to absorb the very light and life from within. In desperation, the tower's defenders created the artifacts, the only weapons capable of opposing the Eclipse Wraith's darkness."
                        "\n\nWith newfound purpose, you continue your ascent, knowing that you possess one of the artifacts, and the fate of the tower now rests in your hands."
                    ),
                    color=0x00ff00  # Green color for success
                )

                await ctx.send(embed=victory_embed)

                newlevel = level + 1
                async with self.bot.pool.acquire() as connection:
                    await connection.execute('UPDATE battletower SET level = level + 1 WHERE id = $1',
                                             ctx.author.id)
                await ctx.send(f'You have advanced to floor: {newlevel}')

            if level == 7:
                victory_embed = discord.Embed(
                    title="Lich Lord Moros Defeated!",
                    description=(
                        f"As you stand amidst the vanquished {minion1_name}s and {minion2_name}s, an eerie stillness surrounds the {level_name}. "
                        f"The Lich Lord Moros, a master of spectral dominion, has been defeated, his ethereal reign shattered, and his dark enchantments dispelled."
                        "\n\nAs you explore the aftermath, another artifact reveals a vision to you. This time, you witness a group of brave souls, the 'Order of Radiance,' who were the last defenders of the tower. They reveal their intentions to harness the power of the artifacts and use them to push back the Eclipse Wraith. But their attempts were in vain, as the Eclipse Wraith's darkness overcame them, corrupting their very souls."
                        "\n\nYour journey takes on a deeper purpose as you learn of the Eclipse Wraith's corruption and its influence over the tower. The artifacts are your only hope to stand against this malevolence."
                    ),
                    color=0x00ff00  # Green color for success
                )

                await ctx.send(embed=victory_embed)

                newlevel = level + 1
                async with self.bot.pool.acquire() as connection:
                    await connection.execute('UPDATE battletower SET level = level + 1 WHERE id = $1',
                                             ctx.author.id)
                await ctx.send(f'You have advanced to floor: {newlevel}')

            if level == 8:
                victory_embed = discord.Embed(
                    title="Frostfire Behemoth Defeated!",
                    description=(
                        f"As you stand amidst the defeated {minion1_name}s and {minion2_name}s, an oppressive heat fills the {level_name}. "
                        f"The Frostfire Behemoth, a master of fire and ice, has been vanquished, its elemental power extinguished, and its molten heart frozen."
                        "\n\nIn the scorching aftermath, you encounter an artifact that projects yet another vision. This time, you see the Eclipse Wraith's origin. It was once a powerful entity of light and balance, but it was corrupted by its insatiable thirst for power and dominion."
                        "\n\nYou realize that the Eclipse Wraith's corruption is tied to the artifacts themselves. The more you possess, the closer you come to facing the Eclipse Wraith. You continue your journey, determined to uncover the truth and put an end to the tower's darkness."
                    ),
                    color=0x00ff00  # Green color for success
                )

                await ctx.send(embed=victory_embed)

                newlevel = level + 1
                async with self.bot.pool.acquire() as connection:
                    await connection.execute('UPDATE battletower SET level = level + 1 WHERE id = $1',
                                             ctx.author.id)
                await ctx.send(f'You have advanced to floor: {newlevel}')

            if level == 9:
                victory_embed = discord.Embed(
                    title="Dragonlord Zaldrak Defeated!",
                    description=(
                        f"As you stand amidst the frozen tundra and the defeated {minion1_name}s and {minion2_name}s, an icy stillness blankets the {level_name}, the Frozen Abyss. "
                        f"The Dragonlord Zaldrak, a master of frost and flame, has been vanquished, its frigid and fiery power quelled, and its dominion shattered."
                        "\n\nAmidst the frost, you come across an artifact with a chilling vision. It reveals that the Eclipse Wraith has already absorbed the power of the other artifacts and has grown stronger. It seeks to devour the entire world, and the only way to stop it is by wielding the combined power of the remaining artifacts."
                        "\n\nWith the artifacts in your possession, your journey becomes a race against time, as you are the last hope to prevent the Eclipse Wraith's catastrophic release."
                    ),
                    color=0x00ff00  # Green color for success
                )

                await ctx.send(embed=victory_embed)

                newlevel = level + 1
                async with self.bot.pool.acquire() as connection:
                    await connection.execute('UPDATE battletower SET level = level + 1 WHERE id = $1',
                                             ctx.author.id)
                await ctx.send(f'You have advanced to floor: {newlevel}')

            if level == 10:
                victory_embed = discord.Embed(
                    title="Soulreaver Lurkthar Defeated!",
                    description=(
                        f"As you stand amidst the shattered spirits and the defeated {minion1_name}s and {minion2_name}s, an eerie sense of tranquility washes over the {level_name}, the Soulreaver's Embrace. "
                        f"Soulreaver Lurkthar, a formidable entity that consumed countless souls, has been vanquished, its malevolent grip on the spectral realm broken, and the souls it enslaved set free."
                        "\n\nYou take a moment to appreciate the artifact you acquired in the Crimson Abyss, as it once again glows with an ethereal light. This time, it offers a vision of the tower's guardians, including the bosses you have faced. They were once noble protectors of the tower, known as the 'Sentinels of Radiance.'"
                        "\n\nLong ago, the Sentinels guarded the tower against all threats, including the Eclipse Wraith. However, the power of the Eclipse Wraith corrupted them, turning them into the very foes they once fought against."
                        "\n\nThe artifact in your possession is not only a weapon but also a key to unlocking the potential within these fallen Sentinels. With it, you have the power to cleanse and restore them to their former glory. You realize that your journey is not just about defeating the Eclipse Wraith but also redeeming the defenders who lost their way."
                    ),
                    color=0x00ff00  # Green color for success
                )

                await ctx.send(embed=victory_embed)

                chest_embed = discord.Embed(
                    title="Choose Your Treasure",
                    description=(
                        "You have a choice to make: Before you lie two treasure chests, each shimmering with an otherworldly aura. "
                        "The left chest appears ancient and ornate, while the right chest is smaller but radiates a faint magical glow."
                        f"{ctx.author.mention}, Type left or right to make your decision. You have 60 seconds!"
                    ),
                    color=0x0055ff  # Blue color for options
                )
                chest_embed.set_footer(text=f"Type left or right to make your decision.")
                await ctx.send(embed=chest_embed)

                async with self.bot.pool.acquire() as connection:
                    prestige_level = await connection.fetchval('SELECT prestige FROM battletower WHERE id = $1',
                                                               ctx.author.id)
                    level = await connection.fetchval('SELECT level FROM battletower WHERE id = $1', ctx.author.id)

                def check(m):
                    return m.author == ctx.author and m.content.lower() in ['left', 'right']

                import random
                if prestige_level >= 1:
                    new_level = level + 1

                    async with self.bot.pool.acquire() as connection:
                        left_reward_type = random.choice(['crate', 'money'])
                        right_reward_type = random.choice(['crate', 'money'])

                        if left_reward_type == 'crate':
                            left_options = ['legendary', 'fortune', 'mystery', 'common', 'uncommon', 'magic',
                                            'rare']
                            left_weights = [1, 1, 80, 170, 150, 20, 75]  # Weighted values according to percentages
                            left_crate_type = random.choices(left_options, left_weights)[0]
                        else:
                            left_money_amount = random.choice(
                                [10000, 15000, 20000, 50000, 25000, 10000, 27000, 33000, 100000, 5000, 150000])

                        if right_reward_type == 'crate':
                            right_options = ['legendary', 'fortune', 'mystery', 'common', 'uncommon', 'magic',
                                             'rare']
                            right_weights = [1, 1, 80, 170, 150, 20, 75]  # Weighted values according to percentages
                            right_crate_type = random.choices(right_options, right_weights)[0]
                        else:
                            right_money_amount = random.choice(
                                [10000, 15000, 20000, 50000, 25000, 10000, 27000, 33000, 100000, 5000, 150000])

                        await ctx.send(
                            "You see two chests: one on the left and one on the right. Which one do you choose? (Type 'left' or 'right')")

                        try:
                            msg = await self.bot.wait_for('message', check=check, timeout=60.0)
                            choice = msg.content.lower()
                        except asyncio.TimeoutError:
                            choice = random.choice(["left", "right"])
                            await ctx.send('You took too long to decide. The chest will be chosen at random.')
                            await ctx.send(f'You have advanced to floor: {new_level}')
                            await connection.execute('UPDATE battletower SET level = level + 1 WHERE id = $1',
                                                     ctx.author.id)
                            try:
                                await self.remove_player_from_fight(ctx.author.id)
                            except Exception as e:
                                pass




                        if choice == 'left':
                            if left_reward_type == 'crate':
                                await ctx.send(
                                    f'You open the chest on the left and find a {emotes[left_crate_type]} crate!')
                                await connection.execute(
                                    f'UPDATE profile SET crates_{left_crate_type} = crates_{left_crate_type} + 1 WHERE "user" = $1',
                                    ctx.author.id)
                                unchosen_reward = right_reward_type
                                if unchosen_reward == 'crate':
                                    await ctx.send(
                                        f'You could have gotten a {emotes[right_crate_type]} crate if you chose the right chest.')
                                else:
                                    await ctx.send(
                                        f'You could have gotten **${right_money_amount}** if you chose the right chest.')
                            else:
                                await ctx.send(f'You open the chest on the left and find **${left_money_amount}**!')
                                await connection.execute('UPDATE profile SET money = money + $1 WHERE "user" = $2',
                                                         left_money_amount, ctx.author.id)
                                unchosen_reward = right_reward_type
                                if unchosen_reward == 'crate':
                                    await ctx.send(
                                        f'You could have gotten a {emotes[right_crate_type]} crate if you chose the right chest.')
                                else:
                                    await ctx.send(
                                        f'You could have gotten **${right_money_amount}** if you chose the right chest.')
                        else:
                            if right_reward_type == 'crate':
                                await ctx.send(
                                    f'You open the chest on the right and find a {emotes[right_crate_type]} crate!')
                                await connection.execute(
                                    f'UPDATE profile SET crates_{right_crate_type} = crates_{right_crate_type} + 1 WHERE "user" = $1',
                                    ctx.author.id)
                                unchosen_reward = left_reward_type
                                if unchosen_reward == 'crate':
                                    await ctx.send(
                                        f'You could have gotten a {emotes[left_crate_type]} crate if you chose the left chest.')
                                else:
                                    await ctx.send(
                                        f'You could have gotten **${left_money_amount}** if you chose the left chest.')
                            else:
                                await ctx.send(
                                    f'You open the chest on the right and find **${right_money_amount}**!')
                                await connection.execute('UPDATE profile SET money = money + $1 WHERE "user" = $2',
                                                         right_money_amount, ctx.author.id)
                                unchosen_reward = left_reward_type
                                if unchosen_reward == 'crate':
                                    await ctx.send(
                                        f'You could have gotten a {emotes[left_crate_type]} crate if you chose the left chest.')
                                else:
                                    await ctx.send(
                                        f'You could have gotten **${left_money_amount}** if you chose the left chest.')

                        await ctx.send(f'You have advanced to floor: {new_level}')
                        await connection.execute('UPDATE battletower SET level = level + 1 WHERE id = $1',
                                                 ctx.author.id)
                        try:
                            await self.remove_player_from_fight(ctx.author.id)
                        except Exception as e:
                            pass

                        # --------------------------
                        # --------------------------
                        # --------------------------

                else:
                    try:
                        msg = await self.bot.wait_for('message', check=check, timeout=60.0)
                        choice = msg.content.lower()
                    except asyncio.TimeoutError:
                        new_level = level + 1
                        choice = random.choice(["left", "right"])
                        await ctx.send('You took too long to decide. The chest will be chosen at random.')
                        await ctx.send(f'You have advanced to floor: {new_level}')
                        async with self.bot.pool.acquire() as connection:
                            await connection.execute('UPDATE battletower SET level = level + 1 WHERE id = $1',
                                                     ctx.author.id)
                            try:
                                await self.remove_player_from_fight(ctx.author.id)
                            except Exception as e:
                                pass

                    if choice is not None:

                        new_level = level + 1
                        if choice == 'left':
                            await ctx.send(
                                'You open the chest on the left and find: <:F_Magic:1139514865174720532> 2 '
                                'Magic Crates!')
                            await ctx.send(f'You have advanced to floor: {new_level}')
                            async with self.bot.pool.acquire() as connection:
                                await connection.execute(
                                    'UPDATE profile SET crates_magic = crates_magic + 2 WHERE "user" '
                                    '= $1', ctx.author.id)
                                await connection.execute('UPDATE battletower SET level = level + 1 WHERE id = $1',
                                                         ctx.author.id)
                        else:
                            await ctx.send('You open the chest on the right and find: **$55000**!')
                            await ctx.send(f'You have advanced to floor: {new_level}')
                            async with self.bot.pool.acquire() as connection:
                                await connection.execute(
                                    'UPDATE profile SET money = money + 55000 WHERE "user" '
                                    '= $1', ctx.author.id)
                                await connection.execute('UPDATE battletower SET level = level + 1 WHERE id = $1',
                                                         ctx.author.id)

            # ---------------------------------------------------------------------------------------------------------------------
            if level == 11:
                victory_embed = discord.Embed(
                    title="Ravengaze Alpha Defeated!",
                    description=(
                        f"As you stand amidst the fallen Gnoll Raiders and defeated Hyena Packs, the {level_name}, the Voidforged Sanctum, echoes with an eerie silence. "
                        f"Ravengaze Alpha, a once-proud leader of the hyena tribe, has been vanquished, and the dark aura surrounding them has lifted."
                        "\n\nThe artifact from the Soulreaver's Embrace pulses with newfound energy. It reveals another vision, one of a grand council chamber within the tower. Here, the Guardians of Radiance, the Sentinels of Light, forged a pact with the Eclipse Wraith to protect the tower against a greater, hidden threat."
                        "\n\nThe vision hints that the tower's fall into darkness was a last resort to prevent this hidden power from being unleashed. Your journey is now a quest to unveil this hidden threat and restore the tower to its original purpose."
                        "\n\nBut the vision holds a revelation - one of the Guardians, who stood as a beacon of light, is revealed to have orchestrated the Eclipse Wraith's corruption, becoming its greatest ally and adversary."
                    ),
                    color=0x00ff00  # Green color for success
                )

                await ctx.send(embed=victory_embed)

                newlevel = level + 1
                async with self.bot.pool.acquire() as connection:
                    await connection.execute('UPDATE battletower SET level = level + 1 WHERE id = $1',
                                             ctx.author.id)
                await ctx.send(f'You have advanced to floor: {newlevel}')

            if level == 12:
                victory_embed = discord.Embed(
                    title="Nightshade Serpentis Defeated!",
                    description=(
                        f"As you stand amidst the fallen Gloomhounds and defeated Nocturne Stalkers, the {level_name}, the Nexus of Chaos, resonates with a sense of restored equilibrium. "
                        f"Nightshade Serpentis, once a guardian of the tower, has been vanquished, and the arcane chaos that enveloped the floor dissipates."
                        "\n\nThe artifact in your possession once again shines with brilliance, revealing another vision. This vision takes you to a library within the tower, where the Guardians of Radiance researched the tower's history and its ancient purpose."
                        "\n\nYou learn that the Eclipse Wraith's curse was the result of a great betrayal by one of the Guardians, who sought to harness the tower's power for their own gain. The Eclipse Wraith was summoned as a protector, but the dark force turned against its summoners."
                        "\n\nYour journey now encompasses a quest for knowledge as you seek to understand the tower's true history and the identity of the betrayer who initiated its fall. A plot to harness ultimate power is unveiled."
                    ),
                    color=0x00ff00  # Green color for success
                )

                await ctx.send(embed=victory_embed)

                newlevel = level + 1
                async with self.bot.pool.acquire() as connection:
                    await connection.execute('UPDATE battletower SET level = level + 1 WHERE id = $1',
                                             ctx.author.id)
                await ctx.send(f'You have advanced to floor: {newlevel}')

            if level == 16:

                victory_embed = discord.Embed(
                    title="Master Puppeteer Defeated!",
                    description=(
                        f"As the Master Puppeteer falls amidst the wreckage of marionettes and severed strings, the {level_name}, the Manipulated Marionette Chamber, echoes with an eerie silence. The artifact in your possession, known for revealing visions, suddenly projects ancient symbols onto the chamber's walls."
                        "\n\nThese symbols tell the tale of an ancient weapon, the Tower, designed by a civilization known as the Forerunners. The tower's purpose was to stop a cosmic malevolence threatening galaxies."
                        "\n\nHowever, a startling revelation unfolds as the artifact translates these ancient inscriptions. It becomes evident that the tower itself, now controlled by a malevolent force, is the very threat the Forerunners built it to stop—an ominous power seeking to wreak havoc on cosmic scales."
                        "\n\nAs you delve deeper into the translated inscriptions, a fragmented history emerges. The malevolent force corrupted the tower, turning it against its intended purpose. It manipulated events through the Master Puppeteer to ensure chaos would reign, setting the stage for an imminent cosmic cataclysm."
                        "\n\nThe artifact, once deemed a mere visionary device, now pulses with untapped potential—a cosmic weapon capable of restoring the tower to its intended purpose or, if wielded incorrectly, unleashing a catastrophic cosmic upheaval."
                        "\n\nWith this newfound understanding, you brace yourself for the ultimate confrontation against the malevolent force controlling the tower—a showdown not just to liberate the tower but to prevent a cosmic disaster that threatens to engulf entire galaxies."
                        "\n\nArmed with the artifact's augmented power, you step forth, knowing that the fate of the cosmos hangs in the balance, and the final battle to reclaim the tower's purpose is the first step in averting a catastrophe of unprecedented proportions."
                    ),
                    color=0x00ff00  # Green color for success
                )

                await ctx.send(embed=victory_embed)

                newlevel = level + 1
                async with self.bot.pool.acquire() as connection:
                    await connection.execute('UPDATE battletower SET level = level + 1 WHERE id = $1',
                                             ctx.author.id)
                await ctx.send(f'You have advanced to floor: {newlevel}')

            if level == 13:
                victory_embed = discord.Embed(
                    title="Ignis Inferno Defeated!",
                    description=(
                        f"As you stand amidst the vanquished Magma Elementals and Inferno Imps, the {level_name}, the Eternal Torment Halls, ceases to tremble with searing heat. "
                        f"Ignis Inferno, a blazing entity with an unquenchable fire, has been extinguished, and the fires that consumed the floor subside."
                        "\n\nThe artifact shines with a fiery brilliance, revealing yet another vision. This time, it transports you to the heart of the tower's inner sanctum, where the ultimate secret is unveiled - the hidden threat is not an external force but a malevolent consciousness within the tower itself."
                        "\n\nThe Eclipse Wraith, now recognized as the Tower's Heart, was designed to contain and counterbalance this malevolent consciousness. Its transformation into darkness was intentional, and it's not the tower's adversary, but its guardian."
                        "\n\nYour journey has now reached its apex. You must confront the malevolent consciousness within the Tower's Heart to either save or seal the tower's fate. A shocking twist that challenges everything you knew about the tower's history."
                    ),
                    color=0x00ff00  # Green color for success
                )

                await ctx.send(embed=victory_embed)

                newlevel = level + 1
                async with self.bot.pool.acquire() as connection:
                    await connection.execute('UPDATE battletower SET level = level + 1 WHERE id = $1',
                                             ctx.author.id)
                await ctx.send(f'You have advanced to floor: {newlevel}')

            if level == 14:
                victory_embed = discord.Embed(
                    title="Wraithlord Maroth Defeated!",
                    description=(
                        f"As you stand amidst the defeated Cursed Banshees and Spectral Harbingers, the {level_name}, the Abyssal Desolation, resonates with a newfound stillness. "
                        f"Wraithlord Maroth, a sinister figure with dominion over lost souls, has been vanquished, and the lingering wails of the desolation fade."
                        "\n\nYour artifact gleams, offering a vision of a council meeting among the Guardians of Radiance. Here, the decision to summon the Eclipse Wraith was made, a desperate act to combat the hidden threat that endangered the tower."
                        "\n\nHowever, this vision reveals a shocking truth - the Eclipse Wraith's dark transformation was not due to the betrayal of a Guardian, but it was always intended to be a guardian of darkness, a necessary counterbalance to the hidden threat."
                        "\n\nYour journey now becomes a quest to understand the true purpose of the Eclipse Wraith and confront the hidden threat head-on. A twist in the narrative reveals the Eclipse Wraith as a guardian of balance."
                    ),
                    color=0x00ff00  # Green color for success
                )

                await ctx.send(embed=victory_embed)

                newlevel = level + 1
                async with self.bot.pool.acquire() as connection:
                    await connection.execute('UPDATE battletower SET level = level + 1 WHERE id = $1',
                                             ctx.author.id)
                await ctx.send(f'You have advanced to floor: {newlevel}')

            if level == 15:
                victory_embed = discord.Embed(
                    title="Infernus, the Infernal Defeated!",
                    description=(
                        f"As you stand amidst the defeated Demonic Imps and Hellspawn Reavers, the {level_name}, the Cursed Citadel, feels almost solemn. "
                        f"Infernus, the Infernal, a creature of elemental destruction, has been vanquished, and the citadel's flames subside."
                        "\n\nYour artifact radiates with power and offers a vision. This vision transports you to a chamber deep within the tower, where the ultimate secret is unveiled - the hidden threat is not an external force but a malevolent consciousness within the tower itself."
                        "\n\nThe Eclipse Wraith, now recognized as the Tower's Heart, was designed to contain and counterbalance this malevolent consciousness. Its transformation into darkness was intentional, and it's not the tower's adversary, but its guardian."
                        "\n\nYour journey has now reached its apex. You must confront the malevolent consciousness within the Tower's Heart to either save or seal the tower's fate."
                        "\n\nHowever, the vision also reveals that the remaining Guardians of Radiance are imprisoned within the tower, their power siphoned to sustain the malevolent consciousness. A plot twist that sets the stage for your most challenging battle."
                    ),
                    color=0x00ff00  # Green color for success
                )

                await ctx.send(embed=victory_embed)

                chest_embed = discord.Embed(
                    title="Choose Your Treasure",
                    description=(
                        "You have a choice to make: Before you lie two treasure chests, each shimmering with an otherworldly aura. "
                        "The left chest appears ancient and ornate, while the right chest is smaller but radiates a faint magical glow."
                        f"{ctx.author.mention}, Type left or right to make your decision. You have 60 seconds!"
                    ),
                    color=0x0055ff  # Blue color for options
                )
                chest_embed.set_footer(text=f"Type left or right to make your decision.")
                await ctx.send(embed=chest_embed)
                import random
                legran = random.randint(1, 2)

                async with self.bot.pool.acquire() as connection:
                    prestige_level = await connection.fetchval('SELECT prestige FROM battletower WHERE id = $1',
                                                               ctx.author.id)
                    level = await connection.fetchval('SELECT level FROM battletower WHERE id = $1', ctx.author.id)

                def check(m):
                    return m.author == ctx.author and m.content.lower() in ['left', 'right']

                import random
                if prestige_level >= 1:
                    new_level = level + 1

                    async with self.bot.pool.acquire() as connection:
                        left_reward_type = random.choice(['crate', 'money'])
                        right_reward_type = random.choice(['crate', 'money'])

                        if left_reward_type == 'crate':
                            left_options = ['legendary', 'fortune', 'mystery', 'common', 'uncommon', 'magic',
                                            'rare']
                            left_weights = [1, 1, 80, 170, 150, 20, 75]  # Weighted values according to percentages
                            left_crate_type = random.choices(left_options, left_weights)[0]
                        else:
                            left_money_amount = random.choice(
                                [10000, 15000, 20000, 50000, 25000, 10000, 27000, 33000, 100000, 5000, 150000])

                        if right_reward_type == 'crate':
                            right_options = ['legendary', 'fortune', 'mystery', 'common', 'uncommon', 'magic',
                                             'rare']
                            right_weights = [1, 1, 80, 170, 150, 20, 75]  # Weighted values according to percentages
                            right_crate_type = random.choices(right_options, right_weights)[0]
                        else:
                            right_money_amount = random.choice(
                                [10000, 15000, 20000, 50000, 25000, 10000, 27000, 33000, 100000, 5000, 150000])

                        await ctx.send(
                            "You see two chests: one on the left and one on the right. Which one do you choose? (Type 'left' or 'right')")

                        try:
                            msg = await self.bot.wait_for('message', check=check, timeout=60.0)
                            choice = msg.content.lower()
                        except asyncio.TimeoutError:
                            choice = random.choice(["left", "right"])
                            await ctx.send('You took too long to decide. The chest will be chosen at random.')
                            await ctx.send(f'You have advanced to floor: {new_level}')
                            await connection.execute('UPDATE battletower SET level = level + 1 WHERE id = $1',
                                                     ctx.author.id)
                            try:
                                await self.remove_player_from_fight(ctx.author.id)
                            except Exception as e:
                                pass




                        if choice == 'left':
                            if left_reward_type == 'crate':
                                await ctx.send(
                                    f'You open the chest on the left and find a {emotes[left_crate_type]} crate!')
                                await connection.execute(
                                    f'UPDATE profile SET crates_{left_crate_type} = crates_{left_crate_type} + 1 WHERE "user" = $1',
                                    ctx.author.id)
                                unchosen_reward = right_reward_type
                                if unchosen_reward == 'crate':
                                    await ctx.send(
                                        f'You could have gotten a {emotes[right_crate_type]} crate if you chose the right chest.')
                                else:
                                    await ctx.send(
                                        f'You could have gotten **${right_money_amount}** if you chose the right chest.')
                            else:
                                await ctx.send(f'You open the chest on the left and find **${left_money_amount}**!')
                                await connection.execute('UPDATE profile SET money = money + $1 WHERE "user" = $2',
                                                         left_money_amount, ctx.author.id)
                                unchosen_reward = right_reward_type
                                if unchosen_reward == 'crate':
                                    await ctx.send(
                                        f'You could have gotten a {emotes[right_crate_type]} crate if you chose the right chest.')
                                else:
                                    await ctx.send(
                                        f'You could have gotten **${right_money_amount}** if you chose the right chest.')
                        else:
                            if right_reward_type == 'crate':
                                await ctx.send(
                                    f'You open the chest on the right and find a {emotes[right_crate_type]} crate!')
                                await connection.execute(
                                    f'UPDATE profile SET crates_{right_crate_type} = crates_{right_crate_type} + 1 WHERE "user" = $1',
                                    ctx.author.id)
                                unchosen_reward = left_reward_type
                                if unchosen_reward == 'crate':
                                    await ctx.send(
                                        f'You could have gotten a {emotes[left_crate_type]} crate if you chose the left chest.')
                                else:
                                    await ctx.send(
                                        f'You could have gotten **${left_money_amount}** if you chose the left chest.')
                            else:
                                await ctx.send(
                                    f'You open the chest on the right and find **${right_money_amount}**!')
                                await connection.execute('UPDATE profile SET money = money + $1 WHERE "user" = $2',
                                                         right_money_amount, ctx.author.id)
                                unchosen_reward = left_reward_type
                                if unchosen_reward == 'crate':
                                    await ctx.send(
                                        f'You could have gotten a {emotes[left_crate_type]} crate if you chose the left chest.')
                                else:
                                    await ctx.send(
                                        f'You could have gotten **${left_money_amount}** if you chose the left chest.')

                        await ctx.send(f'You have advanced to floor: {new_level}')
                        await connection.execute('UPDATE battletower SET level = level + 1 WHERE id = $1',
                                                 ctx.author.id)
                        try:
                            await self.remove_player_from_fight(ctx.author.id)
                        except Exception as e:
                            pass

                        # --------------------------
                        # --------------------------
                        # --------------------------

                else:

                    try:
                        msg = await self.bot.wait_for('message', check=check, timeout=60.0)
                        choice = msg.content.lower()
                    except asyncio.TimeoutError:
                        newlevel = level + 1
                        choice = random.choice(["left", "right"])
                        await ctx.send('You took too long to decide. The chest will be chosen at random.')


                    if choice is not None:
                        newlevel = level + 1
                        if choice == 'left':
                            if legran == 1:
                                await ctx.send('You open the chest on the left and find: Nothing, bad luck!')
                                await ctx.send(f'You have advanced to floor: {newlevel}')
                                async with self.bot.pool.acquire() as connection:
                                    await connection.execute(
                                        'UPDATE battletower SET level = level + 1 WHERE id = $1',
                                        ctx.author.id)
                            else:

                                await ctx.send(
                                    'You open the chest on the right and find: <:F_Legendary:1139514868400132116> A Legendary Crate!')
                                await ctx.send(f'You have advanced to floor: {newlevel}')
                                async with self.bot.pool.acquire() as connection:
                                    await connection.execute(
                                        'UPDATE profile SET crates_legendary = crates_legendary + 1 WHERE "user" '
                                        '= $1', ctx.author.id)
                                    await connection.execute(
                                        'UPDATE battletower SET level = level + 1 WHERE id = $1',
                                        ctx.author.id)
                        else:

                            if legran == 2:
                                await ctx.send('You open the chest on the left and find: Nothing, bad luck!')
                                await ctx.send(f'You have advanced to floor: {newlevel}')
                                async with self.bot.pool.acquire() as connection:
                                    await connection.execute(
                                        'UPDATE battletower SET level = level + 1 WHERE id = $1',
                                        ctx.author.id)
                            else:

                                await ctx.send(
                                    'You open the chest on the right and find: <:F_Legendary:1139514868400132116> A Legendary Crate!')
                                await ctx.send(f'You have advanced to floor: {newlevel}')
                                async with self.bot.pool.acquire() as connection:
                                    await connection.execute(
                                        'UPDATE profile SET crates_legendary = crates_legendary + 1 WHERE "user" '
                                        '= $1', ctx.author.id)
                                    await connection.execute(
                                        'UPDATE battletower SET level = level + 1 WHERE id = $1',
                                        ctx.author.id)

            if level == 19:
                # Spectral Overlord's Last Stand
                victory_embed = discord.Embed(
                    title="Spectral Overlord Defeated!",
                    description=(
                        "The Ethereal Nexus trembles as the Spectral Overlord falls, its dominion shattered. Phantom Wraiths dissipate, and the once-formidable Overlord crumbles."
                        "\n\nAmidst the cosmic aftermath, the tower itself seems to whisper secrets, revealing the echoes of the Forerunners' desperation and the Guardians' self-sacrifice."
                        "\n\nA surge of cosmic energy propels you to Level 20, a realm shrouded in mysteries yet to unravel."
                    ),
                    color=0x00ff00  # Green color for success
                )

                await ctx.send(embed=victory_embed)

                newlevel = level + 1
                async with self.bot.pool.acquire() as connection:
                    await connection.execute('UPDATE battletower SET level = level + 1 WHERE id = $1',
                                             ctx.author.id)
                await ctx.send(f'You have advanced to floor: {newlevel}')

            if level == 20:
                # Frostbite, the Ice Tyrant's Frigid Domain
                victory_embed = discord.Embed(
                    title="Frostbite, the Ice Tyrant Defeated!",
                    description=(
                        "The Glacial Bastion witnesses an epic clash, Frozen Horrors crumbling under your relentless onslaught. Frostbite, the Ice Tyrant, bows before your might, and the frozen heart thaws into oblivion."
                        "\n\nVisions unfurl, unveiling an ancient alliance—a cosmic dance disrupted by betrayal. Your journey intertwines with remnants of the cosmic alliance, and the Ice Tyrant's remains hold untapped powers that could tip the cosmic balance."
                        "\n\nLevel 21 beckons, promising revelations that transcend mere artifacts."
                    ),
                    color=0x00ff00  # Green color for success
                )

                await ctx.send(embed=victory_embed)

                chest_embed = discord.Embed(
                    title="Choose Your Treasure",
                    description=(
                        "You have a choice to make: Before you lie two treasure chests, each shimmering with an otherworldly aura. "
                        "The left chest appears ancient and ornate, while the right chest is smaller but radiates a faint magical glow."
                        f"{ctx.author.mention}, Type left or right to make your decision. You have 60 seconds!"
                    ),
                    color=0x0055ff  # Blue color for options
                )
                chest_embed.set_footer(text=f"Type left or right to make your decision.")
                await ctx.send(embed=chest_embed)

                async with self.bot.pool.acquire() as connection:
                    prestige_level = await connection.fetchval('SELECT prestige FROM battletower WHERE id = $1',
                                                               ctx.author.id)
                    level = await connection.fetchval('SELECT level FROM battletower WHERE id = $1', ctx.author.id)

                def check(m):
                    return m.author == ctx.author and m.content.lower() in ['left', 'right']

                import random
                if prestige_level >= 1:
                    new_level = level + 1

                    async with self.bot.pool.acquire() as connection:
                        left_reward_type = random.choice(['crate', 'money'])
                        right_reward_type = random.choice(['crate', 'money'])

                        if left_reward_type == 'crate':
                            left_options = ['legendary', 'fortune', 'mystery', 'common', 'uncommon', 'magic',
                                            'rare']
                            left_weights = [1, 1, 80, 170, 150, 20, 75]  # Weighted values according to percentages
                            left_crate_type = random.choices(left_options, left_weights)[0]
                        else:
                            left_money_amount = random.choice(
                                [10000, 15000, 20000, 50000, 25000, 10000, 27000, 33000, 100000, 5000, 150000])

                        if right_reward_type == 'crate':
                            right_options = ['legendary', 'fortune', 'mystery', 'common', 'uncommon', 'magic',
                                             'rare']
                            right_weights = [1, 1, 80, 170, 150, 20, 75]  # Weighted values according to percentages
                            right_crate_type = random.choices(right_options, right_weights)[0]
                        else:
                            right_money_amount = random.choice(
                                [10000, 15000, 20000, 50000, 25000, 10000, 27000, 33000, 100000, 5000, 150000])

                        await ctx.send(
                            "You see two chests: one on the left and one on the right. Which one do you choose? (Type 'left' or 'right')")

                        try:
                            msg = await self.bot.wait_for('message', check=check, timeout=60.0)
                            choice = msg.content.lower()
                        except asyncio.TimeoutError:
                            choice = random.choice(["left", "right"])
                            await ctx.send('You took too long to decide. The chest will be chosen at random.')
                            await ctx.send(f'You have advanced to floor: {new_level}')
                            await connection.execute('UPDATE battletower SET level = level + 1 WHERE id = $1',
                                                     ctx.author.id)
                            try:
                                await self.remove_player_from_fight(ctx.author.id)
                            except Exception as e:
                                pass




                        if choice == 'left':
                            if left_reward_type == 'crate':
                                await ctx.send(
                                    f'You open the chest on the left and find a {emotes[left_crate_type]} crate!')
                                await connection.execute(
                                    f'UPDATE profile SET crates_{left_crate_type} = crates_{left_crate_type} + 1 WHERE "user" = $1',
                                    ctx.author.id)
                                unchosen_reward = right_reward_type
                                if unchosen_reward == 'crate':
                                    await ctx.send(
                                        f'You could have gotten a {emotes[right_crate_type]} crate if you chose the right chest.')
                                else:
                                    await ctx.send(
                                        f'You could have gotten **${right_money_amount}** if you chose the right chest.')
                            else:
                                await ctx.send(f'You open the chest on the left and find **${left_money_amount}**!')
                                await connection.execute('UPDATE profile SET money = money + $1 WHERE "user" = $2',
                                                         left_money_amount, ctx.author.id)
                                unchosen_reward = right_reward_type
                                if unchosen_reward == 'crate':
                                    await ctx.send(
                                        f'You could have gotten a {emotes[right_crate_type]} crate if you chose the right chest.')
                                else:
                                    await ctx.send(
                                        f'You could have gotten **${right_money_amount}** if you chose the right chest.')
                        else:
                            if right_reward_type == 'crate':
                                await ctx.send(
                                    f'You open the chest on the right and find a {emotes[right_crate_type]} crate!')
                                await connection.execute(
                                    f'UPDATE profile SET crates_{right_crate_type} = crates_{right_crate_type} + 1 WHERE "user" = $1',
                                    ctx.author.id)
                                unchosen_reward = left_reward_type
                                if unchosen_reward == 'crate':
                                    await ctx.send(
                                        f'You could have gotten a {emotes[left_crate_type]} crate if you chose the left chest.')
                                else:
                                    await ctx.send(
                                        f'You could have gotten **${left_money_amount}** if you chose the left chest.')
                            else:
                                await ctx.send(
                                    f'You open the chest on the right and find **${right_money_amount}**!')
                                await connection.execute('UPDATE profile SET money = money + $1 WHERE "user" = $2',
                                                         right_money_amount, ctx.author.id)
                                unchosen_reward = left_reward_type
                                if unchosen_reward == 'crate':
                                    await ctx.send(
                                        f'You could have gotten a {emotes[left_crate_type]} crate if you chose the left chest.')
                                else:
                                    await ctx.send(
                                        f'You could have gotten **${left_money_amount}** if you chose the left chest.')

                        await ctx.send(f'You have advanced to floor: {new_level}')
                        await connection.execute('UPDATE battletower SET level = level + 1 WHERE id = $1',
                                                 ctx.author.id)
                        try:
                            await self.remove_player_from_fight(ctx.author.id)
                        except Exception as e:
                            pass

                        # --------------------------
                        # --------------------------
                        # --------------------------

                else:
                    try:
                        msg = await self.bot.wait_for('message', check=check, timeout=60.0)
                        choice = msg.content.lower()
                    except asyncio.TimeoutError:
                        newlevel = level + 1
                        choice = random.choice(["left", "right"])
                        await ctx.send('You took too long to decide. The chest will be chosen at random.')


                    if choice is not None:
                        newlevel = level + 1
                        if choice == 'left':
                            await ctx.send(
                                'You open the chest on the left and find: <:F_Magic:1139514865174720532> 2 '
                                'Magic Crates!')
                            await ctx.send(f'You have advanced to floor: {newlevel}')
                            async with self.bot.pool.acquire() as connection:
                                await connection.execute(
                                    'UPDATE profile SET crates_magic = crates_magic + 2 WHERE "user" '
                                    '= $1', ctx.author.id)
                                await connection.execute('UPDATE battletower SET level = level + 1 WHERE id = $1',
                                                         ctx.author.id)
                        else:
                            await ctx.send('You open the chest on the right and find: **$120000**!')
                            await ctx.send(f'You have advanced to floor: {newlevel}')
                            async with self.bot.pool.acquire() as connection:
                                await connection.execute(
                                    'UPDATE profile SET money = money + 120000 WHERE "user" '
                                    '= $1', ctx.author.id)
                                await connection.execute('UPDATE battletower SET level = level + 1 WHERE id = $1',
                                                         ctx.author.id)

            if level == 21:
                # Chromaggus the Flamebrand's Roaring Inferno
                victory_embed = discord.Embed(
                    title="Chromaggus the Flamebrand Defeated!",
                    description=(
                        "Ember Spire roars with the clash against Dragonkin and Chromatic Wyrms. Chromaggus the Flamebrand succumbs to your relentless assault, its fiery essence extinguished into cosmic embers."
                        "\n\nThe tower itself, now a sentient force, reveals a prophecy—a chosen one, a celestial dance between light and shadow, and the impending cosmic upheaval."
                        "\n\nYour journey faces its ultimate trial, entwined with the fate of the cosmic alliance and the tower's redemption. The essence of defeated bosses pulsates within you, presenting a cosmic choice—restore balance or unleash a cataclysmic force."
                        "\n\nStanding on the precipice of destiny, you prepare for the final confrontation that will determine the fate of the tower, the Eclipse Wraith, and the entire cosmos."
                    ),
                    color=0x00ff00  # Green color for success
                )

                await ctx.send(embed=victory_embed)

                newlevel = level + 1
                async with self.bot.pool.acquire() as connection:
                    await connection.execute('UPDATE battletower SET level = level + 1 WHERE id = $1',
                                             ctx.author.id)
                await ctx.send(f'You have advanced to floor: {newlevel}')

            if level == 22:
                # Banshee Queen Shriekara's Lament
                victory_embed = discord.Embed(
                    title="Banshee Queen Shriekara Defeated!",
                    description=(
                        "The Hallowed Mausoleum echoes with the wails of Phantom Banshees and Wailing Apparitions as you triumph over the Banshee Queen Shriekara. The spectral queen dissolves into cosmic echoes, and the tower itself seems to mourn."
                        "\n\nAs the ethereal remnants of the defeated queen coalesce, the tower shares cryptic visions—an ancient pact, a melody of sorrow, and a revelation that transcends the boundaries of life and death."
                        "\n\nLevel 23 beckons, promising a dance with the void and revelations that resonate with the cosmic harmony."
                    ),
                    color=0x00ff00  # Green color for success
                )

                await ctx.send(embed=victory_embed)

                newlevel = level + 1
                async with self.bot.pool.acquire() as connection:
                    await connection.execute('UPDATE battletower SET level = level + 1 WHERE id = $1',
                                             ctx.author.id)
                await ctx.send(f'You have advanced to floor: {newlevel}')

            if level == 23:
                # Voidlord Malgros' Abyssal Dominion
                victory_embed = discord.Embed(
                    title="Voidlord Malgros Defeated!",
                    description=(
                        "Abyssal Imps and Voidbringer Fiends succumb to your might in the Chaotic Abyss. The Voidlord Malgros bows before the cosmic forces at play, his abyssal dominion shattered."
                        "\n\nAs the void dissipates, the tower pulsates with ancient energies, revealing glimpses of a forbidden prophecy—a realm between realms, the Voidlord's fall, and the imminent convergence of cosmic forces."
                        "\n\nLevel 24 awaits, promising a descent into the shadows and revelations that pierce the veil of reality."
                    ),
                    color=0x00ff00  # Green color for success
                )

                await ctx.send(embed=victory_embed)

                newlevel = level + 1
                async with self.bot.pool.acquire() as connection:
                    await connection.execute('UPDATE battletower SET level = level + 1 WHERE id = $1',
                                             ctx.author.id)
                await ctx.send(f'You have advanced to floor: {newlevel}')

            if level == 24:
                # Soulshredder Vorath's Haunting Embrace
                victory_embed = discord.Embed(
                    title="Soulshredder Vorath Defeated!",
                    description=(
                        "Dreadshade Specters and Soulreaver Harbingers fade into the shadows as you conquer the Enigmatic Sanctum. Soulshredder Vorath, a harbinger of desolation, succumbs to your unwavering resolve."
                        "\n\nIn the aftermath, the tower itself whispers of forbidden rituals, shattered soul essences, and the Soulshredder's malevolent purpose. Cosmic energies surge, guiding you towards Level 25—a realm where the line between reality and nightmare blurs."
                    ),
                    color=0x00ff00  # Green color for success
                )

                await ctx.send(embed=victory_embed)

                newlevel = level + 1
                async with self.bot.pool.acquire() as connection:
                    await connection.execute('UPDATE battletower SET level = level + 1 WHERE id = $1',
                                             ctx.author.id)
                await ctx.send(f'You have advanced to floor: {newlevel}')

            if level == 25:
                # Pyroclasmic Overfiend's Infernal Convergence
                victory_embed = discord.Embed(
                    title="Pyroclasmic Overfiend Defeated!",
                    description=(
                        "Inferno Aberrations and Brimstone Fiends bow before your might as you conquer the Blazing Abyss. The Pyroclasmic Overfiend, a creature of elemental chaos, succumbs to the cosmic flames."
                        "\n\nThe tower, now pulsating with immense energy, unfolds visions of cataclysmic convergence, a cosmic inferno, and the imminent unraveling of reality itself. As the Pyroclasmic Overfiend's essence merges with the tower, Level 26 beckons—the final threshold where destinies entwine and cosmic forces clash."
                    ),
                    color=0x00ff00  # Green color for success
                )

                await ctx.send(embed=victory_embed)

                chest_embed = discord.Embed(
                    title="Choose Your Treasure",
                    description=(
                        "You have a choice to make: Before you lie two treasure chests, each shimmering with an otherworldly aura. "
                        "The left chest appears ancient and ornate, while the right chest is smaller but radiates a faint magical glow."
                        f"{ctx.author.mention}, Type left or right to make your decision. You have 60 seconds!"
                    ),
                    color=0x0055ff  # Blue color for options
                )
                chest_embed.set_footer(text=f"Type left or right to make your decision.")
                await ctx.send(embed=chest_embed)

                async with self.bot.pool.acquire() as connection:
                    prestige_level = await connection.fetchval('SELECT prestige FROM battletower WHERE id = $1',
                                                               ctx.author.id)
                    level = await connection.fetchval('SELECT level FROM battletower WHERE id = $1', ctx.author.id)

                def check(m):
                    return m.author == ctx.author and m.content.lower() in ['left', 'right']

                import random
                if prestige_level >= 1:
                    new_level = level + 1

                    async with self.bot.pool.acquire() as connection:
                        left_reward_type = random.choice(['crate', 'money'])
                        right_reward_type = random.choice(['crate', 'money'])

                        if left_reward_type == 'crate':
                            left_options = ['legendary', 'fortune', 'mystery', 'common', 'uncommon', 'magic',
                                            'rare']
                            left_weights = [1, 1, 80, 170, 150, 20, 75]  # Weighted values according to percentages
                            left_crate_type = random.choices(left_options, left_weights)[0]
                        else:
                            left_money_amount = random.choice(
                                [10000, 15000, 20000, 50000, 25000, 10000, 27000, 33000, 100000, 5000, 150000])

                        if right_reward_type == 'crate':
                            right_options = ['legendary', 'fortune', 'mystery', 'common', 'uncommon', 'magic',
                                             'rare']
                            right_weights = [1, 1, 80, 170, 150, 20, 75]  # Weighted values according to percentages
                            right_crate_type = random.choices(right_options, right_weights)[0]
                        else:
                            right_money_amount = random.choice(
                                [10000, 15000, 20000, 50000, 25000, 10000, 27000, 33000, 100000, 5000, 150000])

                        await ctx.send(
                            "You see two chests: one on the left and one on the right. Which one do you choose? (Type 'left' or 'right')")

                        try:
                            msg = await self.bot.wait_for('message', check=check, timeout=60.0)
                            choice = msg.content.lower()

                        except asyncio.TimeoutError:
                            choice = random.choice(["left", "right"])
                            await ctx.send('You took too long to decide. The chest will be chosen at random.')
                            await ctx.send(f'You have advanced to floor: {new_level}')
                            await connection.execute('UPDATE battletower SET level = level + 1 WHERE id = $1',
                                                     ctx.author.id)
                            try:
                                await self.remove_player_from_fight(ctx.author.id)
                            except Exception as e:
                                pass



                        if choice == 'left':
                            if left_reward_type == 'crate':
                                await ctx.send(
                                    f'You open the chest on the left and find a {emotes[left_crate_type]} crate!')
                                await connection.execute(
                                    f'UPDATE profile SET crates_{left_crate_type} = crates_{left_crate_type} + 1 WHERE "user" = $1',
                                    ctx.author.id)
                                unchosen_reward = right_reward_type
                                if unchosen_reward == 'crate':
                                    await ctx.send(
                                        f'You could have gotten a {emotes[right_crate_type]} crate if you chose the right chest.')
                                else:
                                    await ctx.send(
                                        f'You could have gotten **${right_money_amount}** if you chose the right chest.')
                            else:
                                await ctx.send(f'You open the chest on the left and find **${left_money_amount}**!')
                                await connection.execute('UPDATE profile SET money = money + $1 WHERE "user" = $2',
                                                         left_money_amount, ctx.author.id)
                                unchosen_reward = right_reward_type
                                if unchosen_reward == 'crate':
                                    await ctx.send(
                                        f'You could have gotten a {emotes[right_crate_type]} crate if you chose the right chest.')
                                else:
                                    await ctx.send(
                                        f'You could have gotten **${right_money_amount}** if you chose the right chest.')
                        else:
                            if right_reward_type == 'crate':
                                await ctx.send(
                                    f'You open the chest on the right and find a {emotes[right_crate_type]} crate!')
                                await connection.execute(
                                    f'UPDATE profile SET crates_{right_crate_type} = crates_{right_crate_type} + 1 WHERE "user" = $1',
                                    ctx.author.id)
                                unchosen_reward = left_reward_type
                                if unchosen_reward == 'crate':
                                    await ctx.send(
                                        f'You could have gotten a {emotes[left_crate_type]} crate if you chose the left chest.')
                                else:
                                    await ctx.send(
                                        f'You could have gotten **${left_money_amount}** if you chose the left chest.')
                            else:
                                await ctx.send(
                                    f'You open the chest on the right and find **${right_money_amount}**!')
                                await connection.execute('UPDATE profile SET money = money + $1 WHERE "user" = $2',
                                                         right_money_amount, ctx.author.id)
                                unchosen_reward = left_reward_type
                                if unchosen_reward == 'crate':
                                    await ctx.send(
                                        f'You could have gotten a {emotes[left_crate_type]} crate if you chose the left chest.')
                                else:
                                    await ctx.send(
                                        f'You could have gotten **${left_money_amount}** if you chose the left chest.')

                        await ctx.send(f'You have advanced to floor: {new_level}')
                        await connection.execute('UPDATE battletower SET level = level + 1 WHERE id = $1',
                                                 ctx.author.id)
                        try:
                            await self.remove_player_from_fight(ctx.author.id)
                        except Exception as e:
                            pass

                        #--------------------------
                        # --------------------------
                        # --------------------------
                else:
                    try:
                        msg = await self.bot.wait_for('message', check=check, timeout=60.0)
                        choice = msg.content.lower()
                    except asyncio.TimeoutError:
                        newlevel = level + 1
                        choice = random.choice(["left", "right"])
                        await ctx.send('You took too long to decide. The chest will be chosen at random.')


                    if choice is not None:
                        newlevel = level + 1
                        if choice == 'left':
                            await ctx.send(
                                'You open the chest on the left and find: <:f_money:1146593710516224090> 1 '
                                'Fortune Crate!')
                            await ctx.send(f'You have advanced to floor: {newlevel}')
                            async with self.bot.pool.acquire() as connection:
                                await connection.execute(
                                    'UPDATE profile SET crates_fortune = crates_fortune + 1 WHERE "user" '
                                    '= $1', ctx.author.id)
                                await connection.execute('UPDATE battletower SET level = level + 1 WHERE id = $1',
                                                         ctx.author.id)
                        else:
                            await ctx.send(
                                'You open the chest on the right and find: **$2** Maybe there is a coffee shop somewhere here..')
                            await ctx.send(f'You have advanced to floor: {newlevel}')
                            async with self.bot.pool.acquire() as connection:
                                await connection.execute(
                                    'UPDATE profile SET money = money + 2 WHERE "user" '
                                    '= $1', ctx.author.id)
                                await connection.execute('UPDATE battletower SET level = level + 1 WHERE id = $1',
                                                         ctx.author.id)

            if level == 26:
                # Sangromancer Malroth's Crimson Overture
                victory_embed = discord.Embed(
                    title="Sangromancer Malroth Defeated!",
                    description=(
                        "The Crimson Serpent and Sanguine Horror writhe in defeat as you conquer the Scarlet Sanctum. Sangromancer Malroth, a master of blood magic, bows before the cosmic symphony."
                        "\n\nAs the tower resonates with arcane melodies, visions unfold—a tapestry of forbidden rituals, a symphony of despair, and the Sangromancer's malevolent dance. The tower's pulse quickens, guiding you towards Level 27—a realm where chaos forges Leviathans and destinies intertwine."
                    ),
                    color=0x00ff00  # Green color for success
                )

                await ctx.send(embed=victory_embed)

                newlevel = level + 1
                async with self.bot.pool.acquire() as connection:
                    await connection.execute('UPDATE battletower SET level = level + 1 WHERE id = $1',
                                             ctx.author.id)
                await ctx.send(f'You have advanced to floor: {newlevel}')

            if level == 27:
                # Chaosforged Leviathan's Abyssal Onslaught
                victory_embed = discord.Embed(
                    title="Chaosforged Leviathan Defeated!",
                    description=(
                        "Doombringer Abominations and Chaosspawn Horrors yield before your might in the Abyssal Abyss. The Chaosforged Leviathan, a creature born of cosmic chaos, succumbs to the relentless onslaught."
                        "\n\nAs the tower vibrates with primordial energies, visions reveal a realm of discord, a Leviathan's awakening, and the imminent clash of chaotic forces. The tower's resonance deepens, beckoning you towards Level 28—a realm where nethersworn aberrations and eldritch behemoths await."
                    ),
                    color=0x00ff00  # Green color for success
                )

                await ctx.send(embed=victory_embed)

                newlevel = level + 1
                async with self.bot.pool.acquire() as connection:
                    await connection.execute('UPDATE battletower SET level = level + 1 WHERE id = $1',
                                             ctx.author.id)
                await ctx.send(f'You have advanced to floor: {newlevel}')

            if level == 28:
                # Abyssal Enderark's Nethersworn Convergence
                victory_embed = discord.Embed(
                    title="Abyssal Enderark Defeated!",
                    description=(
                        "Nethersworn Aberrations and Eldritch Behemoths fall silent as you conquer the Netherrealm Nexus. Abyssal Enderark, a harbinger of the abyss, succumbs to your unyielding resolve."
                        "\n\nIn the aftermath, the tower pulsates with eldritch energies, revealing glimpses of a realm between realms, an Enderark's descent, and the cosmic convergence of nether forces. The tower's call grows stronger, guiding you towards Level 29—a realm where darktide krakens and abyssal voidlords await."
                    ),
                    color=0x00ff00  # Green color for success
                )

                await ctx.send(embed=victory_embed)

                newlevel = level + 1
                async with self.bot.pool.acquire() as connection:
                    await connection.execute('UPDATE battletower SET level = level + 1 WHERE id = $1',
                                             ctx.author.id)
                await ctx.send(f'You have advanced to floor: {newlevel}')

            if level == 29:
                # Tidal Terror Abaddon's Abyssal Onslaught
                victory_embed = discord.Embed(
                    title="Tidal Terror Abaddon Defeated!",
                    description=(
                        "Darktide Krakens and Abyssal Voidlords yield before your might in the Cursed Abyss. Tidal Terror Abaddon, a creature of abyssal waters, succumbs to the relentless onslaught."
                        "\n\nAs the tower resonates with aquatic energies, visions unfold—a tempest of darkness, a kraken's lament, and the imminent clash of abyssal forces. The tower's song reaches a crescendo, beckoning you towards Level 30—the final realm where destinies converge, and the tower's ultimate secret is laid bare."
                    ),
                    color=0x00ff00  # Green color for success
                )

                await ctx.send(embed=victory_embed)

                newlevel = level + 1
                async with self.bot.pool.acquire() as connection:
                    await connection.execute('UPDATE battletower SET level = level + 1 WHERE id = $1',
                                             ctx.author.id)
                await ctx.send(f'You have advanced to floor: {newlevel}')

            if level == 30:

                # The Revelation of Cosmic Tragedy
                cosmic_embed = discord.Embed(
                    title="The Cosmic Abyss: A Symphony of Despair",
                    description=(
                        "As you stand amidst the cosmic ruins, triumphant after landing a fatal blow to the Guardian, the room immediately lights back up. However, a sinister revelation unfolds—a large shadow lurks behind you. Only then do you realize the shocking truth: you were a puppet the entire time, masked by the dark magic of the Overlord."
                        "\n\nThe malevolent magic twisted your perception, making you believe you were fighting evil. In reality, you were mercilessly slaying the forces of good. Your vision was impaired by the enchantment, distorting all that was pure into sinister illusions. The growls and snarls were not manifestations of evil, but the screams of horror as you rampaged through the tower, cutting down every good essence in your path."
                        "\n\nThe room, once filled with the triumphant glow of your victory, now becomes a haunting reminder of the manipulation that led you astray. The cosmic tragedy deepens as the Overlord's dark magic reveals its insidious nature, turning your heroic journey into a nightmarish descent into despair."
                        "\n\nThe mocking laughter of the Overlord of Shadows echoes through the void, resonating with the cruel irony of your unwitting role in this cosmic play. The once-heroic Guardians, sacrificed to contain the unleashed energies, now join the chorus of sorrowful echoes, their tales entwined with your own."
                        "\n\nAs you are forcibly teleported to a desolate room, the essence of nothingness prevails—an eternal void devoid of sensation. No family, no friends, no warmth, or comforting embrace; all connections to the world you once knew severed. Time itself unravels, trapping you in perpetual stasis amid the overwhelming silence that accentuates the profound emptiness."
                        "\n\nIn this timeless abyss, the weight of regret becomes an indomitable force. You, stripped of purpose and connection, are left to grapple with the consequences of your unwitting role in the tower's demise. The laughter of the Overlord of Shadows continues to reverberate, a haunting reminder of the malevolence that exploited your journey."
                        "\n\nAs you drift aimlessly through the emptiness, the echoes of the corrupted Guardians' stories intertwine with your own. Your existence becomes a forlorn symphony of despair, a solitary melody played in the cosmic void."
                        "\n\nThere is no escape, no redemption, only an eternity of isolation and remorse. The Battle Tower, once a beacon of hope, is now a distant memory, and you, adrift in the abyss, become a forgotten soul—lost to the cosmic tragedy orchestrated by the Overlord of Shadows."
                        "\n\nAnd in this void, a cruel twist awaits. You are subjected to an unending torment—a relentless loop that replays the events of the tower. However, in this distorted reality, you witness a distorted version of yourself, a puppet dancing to the malevolent tune of the Overlord."
                        "\n\nYou, now a mere spectator of your own nightmare, see yourself slaying innocent people, mercilessly striking down the Guardians of Radiance who once fought valiantly. The tortured souls of the fallen beg you to stop, their pleas echoing in the hollow abyss."
                        "\n\nYet, you are powerless to change the course of this macabre play. The visions unfold relentlessly, each repetition etching the weight of guilt deeper into your essence. The distorted version of you, manipulated by the Overlord's dark magic, becomes a puppet of cosmic tragedy, forever ensnared in a nightmarish loop of despair."
                    ),
                    color=0xff0000  # Red color for the climax
                )

                await ctx.send(embed=cosmic_embed)

                async with self.bot.pool.acquire() as connection:
                    prestige_level = await connection.fetchval('SELECT prestige FROM battletower WHERE id = $1',
                                                               ctx.author.id)

                if prestige_level >= 1:

                    async with self.bot.pool.acquire() as connection:
                        await connection.execute('UPDATE battletower SET level = level + 1 WHERE id = $1',
                                                 ctx.author.id)

                    await ctx.send(f'This is the end for you... {ctx.author.mention}.. or is it..?')


                    success = True
                    self.bot.dispatch("raid_completion", ctx, success, ctx.author.id)

                    crate_options = ['legendary', 'divine', 'fortune']
                    weights = [0.25, 0.25, 0.25]  # Weighted values according to percentages

                    selected_crate = randomm.choices(crate_options, weights)[0]



                    async with self.bot.pool.acquire() as connection:
                        await connection.execute(
                            f'UPDATE profile SET crates_{selected_crate} = crates_{selected_crate} +1 WHERE "user" = $1',
                            ctx.author.id)

                    await ctx.send(
                        f"You have received 1 {emotes[selected_crate]} crate for completing the battletower on prestige level: {prestige_level}. Congratulations!")


                else:
                    async with self.bot.pool.acquire() as connection:
                        await connection.execute(
                            'UPDATE profile SET crates_divine = crates_divine +1 WHERE "user" '
                            '= $1', ctx.author.id)
                    async with self.bot.pool.acquire() as connection:
                        await connection.execute('UPDATE battletower SET level = level + 1 WHERE id = $1',
                                                 ctx.author.id)
                    await ctx.send(f'This is the end for you... {ctx.author.mention}.. or is it..?')

                    await ctx.send(
                        "You have received 1 <:f_divine:1169412814612471869> crate for completing the battletower, congratulations.")

            # ----------------------------------------------------------------------------------------------------------------------

            if level == 4:
                victory_embed = discord.Embed(
                    title="Necromancer Voss Defeated!",
                    description=(
                        "As you stand amidst the shattered skeletons and defeated zombies, a haunting silence fills the Serpent's Lair. "
                        "Necromancer Voss, a dark conjurer of unholy power, has been vanquished, his malevolent schemes thwarted."
                        "\n\nYet, the Necromancer's presence lingers in the air, and you can't help but wonder about the origins of this once hallowed tower. What secrets does it hold?"
                        "\n\nWith this victory, you move deeper into the tower, your journey now intertwined with the ancient mysteries it holds."
                    ),
                    color=0x00ff00  # Green color for success
                )

                await ctx.send(embed=victory_embed)

                # Create an embed for the treasure chest options
                chest_embed = discord.Embed(
                    title="Choose Your Treasure",
                    description=(
                        "You have a choice to make: Before you lie two treasure chests, each shimmering with an otherworldly aura. "
                        "The left chest appears ancient and ornate, while the right chest is smaller but radiates a faint magical glow."
                        f"{ctx.author.mention}, Type left or right to make your decision. You have 60 seconds!"
                    ),
                    color=0x0055ff  # Blue color for options
                )
                chest_embed.set_footer(text=f"Type left or right to make your decision.")
                await ctx.send(embed=chest_embed)

                async with self.bot.pool.acquire() as connection:
                    prestige_level = await connection.fetchval('SELECT prestige FROM battletower WHERE id = $1',
                                                               ctx.author.id)
                    level = await connection.fetchval('SELECT level FROM battletower WHERE id = $1', ctx.author.id)

                def check(m):
                    return m.author == ctx.author and m.content.lower() in ['left', 'right']

                import random
                if prestige_level >= 1:
                    new_level = level + 1

                    async with self.bot.pool.acquire() as connection:
                        left_reward_type = random.choice(['crate', 'money'])
                        right_reward_type = random.choice(['crate', 'money'])

                        if left_reward_type == 'crate':
                            left_options = ['legendary', 'fortune', 'mystery', 'common', 'uncommon', 'magic',
                                            'rare']
                            left_weights = [1, 1, 80, 170, 150, 20, 75]  # Weighted values according to percentages
                            left_crate_type = random.choices(left_options, left_weights)[0]
                        else:
                            left_money_amount = random.choice(
                                [10000, 15000, 20000, 50000, 25000, 10000, 27000, 33000, 100000, 5000, 150000])

                        if right_reward_type == 'crate':
                            right_options = ['legendary', 'fortune', 'mystery', 'common', 'uncommon', 'magic',
                                             'rare']
                            right_weights = [1, 1, 80, 170, 150, 20, 75]  # Weighted values according to percentages
                            right_crate_type = random.choices(right_options, right_weights)[0]
                        else:
                            right_money_amount = random.choice(
                                [10000, 15000, 20000, 50000, 25000, 10000, 27000, 33000, 100000, 5000, 150000])

                        await ctx.send(
                            "You see two chests: one on the left and one on the right. Which one do you choose? (Type 'left' or 'right')")

                        try:
                            msg = await self.bot.wait_for('message', check=check, timeout=60.0)
                            choice = msg.content.lower()
                        except asyncio.TimeoutError:
                            choice = random.choice(["left", "right"])
                            await ctx.send('You took too long to decide. The chest will be chosen at random.')
                            await ctx.send(f'You have advanced to floor: {new_level}')
                            await connection.execute('UPDATE battletower SET level = level + 1 WHERE id = $1',
                                                     ctx.author.id)
                            try:
                                await self.remove_player_from_fight(ctx.author.id)
                            except Exception as e:
                                pass




                        if choice == 'left':
                            if left_reward_type == 'crate':
                                await ctx.send(
                                    f'You open the chest on the left and find a {emotes[left_crate_type]} crate!')
                                await connection.execute(
                                    f'UPDATE profile SET crates_{left_crate_type} = crates_{left_crate_type} + 1 WHERE "user" = $1',
                                    ctx.author.id)
                                unchosen_reward = right_reward_type
                                if unchosen_reward == 'crate':
                                    await ctx.send(
                                        f'You could have gotten a {emotes[right_crate_type]} crate if you chose the right chest.')
                                else:
                                    await ctx.send(
                                        f'You could have gotten **${right_money_amount}** if you chose the right chest.')
                            else:
                                await ctx.send(f'You open the chest on the left and find **${left_money_amount}**!')
                                await connection.execute('UPDATE profile SET money = money + $1 WHERE "user" = $2',
                                                         left_money_amount, ctx.author.id)
                                unchosen_reward = right_reward_type
                                if unchosen_reward == 'crate':
                                    await ctx.send(
                                        f'You could have gotten a {emotes[right_crate_type]} crate if you chose the right chest.')
                                else:
                                    await ctx.send(
                                        f'You could have gotten **${right_money_amount}** if you chose the right chest.')
                        else:
                            if right_reward_type == 'crate':
                                await ctx.send(
                                    f'You open the chest on the right and find a {emotes[right_crate_type]} crate!')
                                await connection.execute(
                                    f'UPDATE profile SET crates_{right_crate_type} = crates_{right_crate_type} + 1 WHERE "user" = $1',
                                    ctx.author.id)
                                unchosen_reward = left_reward_type
                                if unchosen_reward == 'crate':
                                    await ctx.send(
                                        f'You could have gotten a {emotes[left_crate_type]} crate if you chose the left chest.')
                                else:
                                    await ctx.send(
                                        f'You could have gotten **${left_money_amount}** if you chose the left chest.')
                            else:
                                await ctx.send(
                                    f'You open the chest on the right and find **${right_money_amount}**!')
                                await connection.execute('UPDATE profile SET money = money + $1 WHERE "user" = $2',
                                                         right_money_amount, ctx.author.id)
                                unchosen_reward = left_reward_type
                                if unchosen_reward == 'crate':
                                    await ctx.send(
                                        f'You could have gotten a {emotes[left_crate_type]} crate if you chose the left chest.')
                                else:
                                    await ctx.send(
                                        f'You could have gotten **${left_money_amount}** if you chose the left chest.')

                        await ctx.send(f'You have advanced to floor: {new_level}')
                        await connection.execute('UPDATE battletower SET level = level + 1 WHERE id = $1',
                                                 ctx.author.id)
                        try:
                            await self.remove_player_from_fight(ctx.author.id)
                        except Exception as e:
                            pass

                        # --------------------------
                        # --------------------------
                        # --------------------------
                else:
                    try:
                        msg = await self.bot.wait_for('message', check=check, timeout=60.0)
                        choice = msg.content.lower()
                    except asyncio.TimeoutError:
                        newlevel = level + 1
                        choice = random.choice(["left", "right"])
                        await ctx.send('You took too long to decide. The chest will be chosen at random.')


                    if choice is not None:
                        newlevel = level + 1
                        if choice == 'left':
                            await ctx.send(
                                'You open the chest on the left and find: <:F_Common:1139514874016309260> 3 '
                                'Common Crates!')
                            await ctx.send(f'You have advanced to floor: {newlevel}')
                            async with self.bot.pool.acquire() as connection:
                                await connection.execute(
                                    'UPDATE profile SET crates_common = crates_common + 3 WHERE "user" '
                                    '= $1', ctx.author.id)
                                await connection.execute('UPDATE battletower SET level = level + 1 WHERE id = $1',
                                                         ctx.author.id)
                        else:
                            await ctx.send('You open the chest on the right and find: **20000**!')
                            await ctx.send(f'You have advanced to floor: {newlevel}')
                            async with self.bot.pool.acquire() as connection:
                                await connection.execute(
                                    'UPDATE profile SET money = money + 20000 WHERE "user" '
                                    '= $1', ctx.author.id)
                                await connection.execute('UPDATE battletower SET level = level + 1 WHERE id = $1',
                                                         ctx.author.id)

            if level == 17:
                victory_embed = discord.Embed(
                    title="Eldritch Devourer Defeated!",
                    description=(
                        f"The {level_name}, known as the Convergence Nexus, shudders as the last echoes of battle fade. Chaos Fiends and Voidborn Horrors lie scattered, defeated. The Eldritch Devourer, a colossal cosmic anomaly, succumbs to your relentless assault, its astral essence dissipating into the void."
                        "\n\nAs the Eldritch Devourer crumbles, the artifact in your possession vibrates with newfound energy. It projects ethereal visions, revealing the birth of the Devourer—a celestial being designed by the Forerunners as the embodiment of cosmic balance. Yet, the malevolent force, lurking in the shadows, twisted its purpose, turning it into a force of destruction."
                        "\n\nIn the cosmic aftermath, the artifact speaks in resonant whispers, hinting at latent powers within the Eldritch Devourer's remnants. With the convergence of cosmic forces, a new revelation awaits you on level 18—the Tower's inner sanctum, where the fabric of reality is interwoven with the remnants of ancient guardians and the malevolent force's sinister schemes."
                        "\n\nEmbrace the cosmic energies and ascend to level 18, for the Tower's secrets are yet to unfold, and the cosmic dance of destiny continues."
                    ),
                    color=0x00ff00  # Green color for success
                )

                await ctx.send(embed=victory_embed)

                newlevel = level + 1
                async with self.bot.pool.acquire() as connection:
                    await connection.execute('UPDATE battletower SET level = level + 1 WHERE id = $1',
                                             ctx.author.id)
                await ctx.send(
                    f'You have transcended to the next cosmic realm, where ancient revelations await: {newlevel}')

            # Let's add the altered perception and hint for the dark truth in level 18

            if level == 18:
                # Altered Perception Flash
                flash_embed = discord.Embed(
                    title="A Momentary Flash",
                    description=(
                        "In the midst of the cosmic chaos, there's a fleeting moment where everything shifts. The room bathes in an ethereal light, and for an instant, it seems as if you've just triumphed over a guardian of good, a defender of cosmic harmony."
                        "\n\nHowever, the vision is ephemeral, and the room swiftly returns to its dark and foreboding state. The artifact's glow dims, leaving you with a disquieting sense of uncertainty. Was it a glimpse of the past, a trick of the malevolent force, or a foreshadowing of darker revelations?"
                    ),
                    color=0xffd700  # Gold color for mystical elements
                )

                await ctx.send(embed=flash_embed)

                # Broodmother Arachna's Lair Victory
                victory_embed = discord.Embed(
                    title="Broodmother Arachna Defeated!",
                    description=(
                        f"The {level_name}, also known as Arachna's Abyss, bears the scars of a relentless clash. The Venomous Arachnids' hisses and the Arachnoid Aberrations' eerie silence now accompany the stillness of Broodmother Arachna's lair. The colossal arachnid queen lies vanquished, her once-daunting domain now a silent testament to your triumph."
                        "\n\nAs the aftermath settles, the artifact resonates with the remnants of the cosmic battle. It unfolds visions that transcend the linear flow of time—showcasing not only the corrupted past of Broodmother Arachna but glimpses of her potential redemption. Within her twisted essence, ancient echoes of a guardian's duty linger."
                        "\n\nWith each step deeper into the Tower, the artifact pulses with anticipation. It reveals the imminent convergence of destinies—the Tower's core, a crucible of ancient guardians and the malevolent force's relentless machinations. A cosmic alliance may await, as the Tower itself yearns for redemption."
                        "\n\nAs you ascend to level 19, the Tower's heartbeat becomes more palpable. The artifact, now an arcane compass, guides you towards the heart of the cosmic storm, where revelations and alliances await—a celestial dance that could reshape the very fabric of the cosmos."
                    ),
                    color=0x00ff00  # Green color for success
                )

                await ctx.send(embed=victory_embed)

                newlevel = level + 1
                async with self.bot.pool.acquire() as connection:
                    await connection.execute('UPDATE battletower SET level = level + 1 WHERE id = $1',
                                             ctx.author.id)
                await ctx.send(
                    f'You have transcended to the next cosmic realm, where destinies intertwine and revelations unfold: {newlevel}')

            if level == 5:
                victory_embed = discord.Embed(
                    title="Triumph Over Blackblade Marauder!",
                    description=(
                        "The Halls of Despair fall eerily silent as the notorious Blackblade Marauder lies defeated. "
                        "His bandit and highwayman accomplices now tremble before your indomitable spirit."
                        "\n\nThe Marauder's sinister map, discovered in his lair, hints at hidden treasures deeper within the tower. You're drawn further into the tower's enigmatic history, eager to uncover its secrets."
                    ),
                    color=0x00ff00  # Green color for success
                )

                await ctx.send(embed=victory_embed)

                # Create an embed for the treasure chest options
                chest_embed = discord.Embed(
                    title="Choose Your Treasure",
                    description=(
                        "You have a choice to make: Before you lie two treasure chests, each shimmering with an otherworldly aura. "
                        "The left chest appears ancient and ornate, while the right chest is smaller but radiates a faint magical glow."
                        f"{ctx.author.mention}, Type left or right to make your decision. You have 60 seconds!"
                    ),
                    color=0x0055ff  # Blue color for options
                )
                chest_embed.set_footer(text=f"Type left or right to make your decision.")
                await ctx.send(embed=chest_embed)

                async with self.bot.pool.acquire() as connection:
                    prestige_level = await connection.fetchval('SELECT prestige FROM battletower WHERE id = $1',
                                                               ctx.author.id)
                    level = await connection.fetchval('SELECT level FROM battletower WHERE id = $1', ctx.author.id)

                def check(m):
                    return m.author == ctx.author and m.content.lower() in ['left', 'right']

                import random
                if prestige_level >= 1:
                    new_level = level + 1

                    async with self.bot.pool.acquire() as connection:
                        left_reward_type = random.choice(['crate', 'money'])
                        right_reward_type = random.choice(['crate', 'money'])

                        if left_reward_type == 'crate':
                            left_options = ['legendary', 'fortune', 'mystery', 'common', 'uncommon', 'magic',
                                            'rare']
                            left_weights = [1, 1, 80, 170, 150, 20, 75]  # Weighted values according to percentages
                            left_crate_type = random.choices(left_options, left_weights)[0]
                        else:
                            left_money_amount = random.choice(
                                [10000, 15000, 20000, 50000, 25000, 10000, 27000, 33000, 100000, 5000, 150000])

                        if right_reward_type == 'crate':
                            right_options = ['legendary', 'fortune', 'mystery', 'common', 'uncommon', 'magic',
                                             'rare']
                            right_weights = [1, 1, 80, 170, 150, 20, 75]  # Weighted values according to percentages
                            right_crate_type = random.choices(right_options, right_weights)[0]
                        else:
                            right_money_amount = random.choice(
                                [10000, 15000, 20000, 50000, 25000, 10000, 27000, 33000, 100000, 5000, 150000])

                        await ctx.send(
                            "You see two chests: one on the left and one on the right. Which one do you choose? (Type 'left' or 'right')")

                        try:
                            msg = await self.bot.wait_for('message', check=check, timeout=60.0)
                            choice = msg.content.lower()
                        except asyncio.TimeoutError:
                            choice = random.choice(["left", "right"])
                            await ctx.send('You took too long to decide. The chest will be chosen at random.')
                            await ctx.send(f'You have advanced to floor: {new_level}')
                            await connection.execute('UPDATE battletower SET level = level + 1 WHERE id = $1',
                                                     ctx.author.id)
                            try:
                                await self.remove_player_from_fight(ctx.author.id)
                            except Exception as e:
                                pass




                        if choice == 'left':
                            if left_reward_type == 'crate':
                                await ctx.send(
                                    f'You open the chest on the left and find a {emotes[left_crate_type]} crate!')
                                await connection.execute(
                                    f'UPDATE profile SET crates_{left_crate_type} = crates_{left_crate_type} + 1 WHERE "user" = $1',
                                    ctx.author.id)
                                unchosen_reward = right_reward_type
                                if unchosen_reward == 'crate':
                                    await ctx.send(
                                        f'You could have gotten a {emotes[right_crate_type]} crate if you chose the right chest.')
                                else:
                                    await ctx.send(
                                        f'You could have gotten **${right_money_amount}** if you chose the right chest.')
                            else:
                                await ctx.send(f'You open the chest on the left and find **${left_money_amount}**!')
                                await connection.execute('UPDATE profile SET money = money + $1 WHERE "user" = $2',
                                                         left_money_amount, ctx.author.id)
                                unchosen_reward = right_reward_type
                                if unchosen_reward == 'crate':
                                    await ctx.send(
                                        f'You could have gotten a {emotes[right_crate_type]} crate if you chose the right chest.')
                                else:
                                    await ctx.send(
                                        f'You could have gotten **${right_money_amount}** if you chose the right chest.')
                        else:
                            if right_reward_type == 'crate':
                                await ctx.send(
                                    f'You open the chest on the right and find a {emotes[right_crate_type]} crate!')
                                await connection.execute(
                                    f'UPDATE profile SET crates_{right_crate_type} = crates_{right_crate_type} + 1 WHERE "user" = $1',
                                    ctx.author.id)
                                unchosen_reward = left_reward_type
                                if unchosen_reward == 'crate':
                                    await ctx.send(
                                        f'You could have gotten a {emotes[left_crate_type]} crate if you chose the left chest.')
                                else:
                                    await ctx.send(
                                        f'You could have gotten **${left_money_amount}** if you chose the left chest.')
                            else:
                                await ctx.send(
                                    f'You open the chest on the right and find **${right_money_amount}**!')
                                await connection.execute('UPDATE profile SET money = money + $1 WHERE "user" = $2',
                                                         right_money_amount, ctx.author.id)
                                unchosen_reward = left_reward_type
                                if unchosen_reward == 'crate':
                                    await ctx.send(
                                        f'You could have gotten a {emotes[left_crate_type]} crate if you chose the left chest.')
                                else:
                                    await ctx.send(
                                        f'You could have gotten **${left_money_amount}** if you chose the left chest.')

                        await ctx.send(f'You have advanced to floor: {new_level}')
                        await connection.execute('UPDATE battletower SET level = level + 1 WHERE id = $1',
                                                 ctx.author.id)
                        try:
                            await self.remove_player_from_fight(ctx.author.id)
                        except Exception as e:
                            pass



                else:
                    try:
                        msg = await self.bot.wait_for('message', check=check, timeout=60.0)
                        choice = msg.content.lower()
                    except asyncio.TimeoutError:
                        newlevel = level + 1
                        choice = random.choice(["left", "right"])
                        await ctx.send('You took too long to decide. The chest will be chosen at random.')
                        await ctx.send(f'You have advanced to floor: {newlevel}')
                        async with self.bot.pool.acquire() as connection:
                            await connection.execute('UPDATE battletower SET level = level + 1 WHERE id = $1',
                                                     ctx.author.id)

                            try:
                                await self.remove_player_from_fight(ctx.author.id)
                            except Exception as e:
                                pass

                    else:
                        newlevel = level + 1
                        if choice == 'left':
                            await ctx.send(
                                'You open the chest on the left and find: <:F_common:1139514874016309260> 3 '
                                'Common Crates!')
                            await ctx.send(f'You have advanced to floor: {newlevel}')
                            async with self.bot.pool.acquire() as connection:
                                await connection.execute(
                                    'UPDATE profile SET crates_common = crates_common + 3 WHERE "user" '
                                    '= $1', ctx.author.id)
                                await connection.execute('UPDATE battletower SET level = level + 1 WHERE id = $1',
                                                         ctx.author.id)
                        else:
                            await ctx.send('You open the chest on the right and find: **$20000**!')
                            await ctx.send(f'You have advanced to floor: {newlevel}')
                            async with self.bot.pool.acquire() as connection:
                                await connection.execute(
                                    'UPDATE profile SET money = money + 20000 WHERE "user" '
                                    '= $1', ctx.author.id)
                                await connection.execute('UPDATE battletower SET level = level + 1 WHERE id = $1',
                                                         ctx.author.id)
                            try:
                                await self.remove_player_from_fight(ctx.author.id)
                            except KeyError:
                                pass
            completed = True
            self.bot.dispatch("raid_completion", ctx, completed, ctx.author.id)
            try:
                await self.remove_player_from_fight(ctx.author.id)
            except Exception as e:
                pass




    import discord
    from discord.ext import commands


    @has_char()
    @user_cooldown(100)
    @commands.command(brief=_("Battle against a player (includes raidstats)"))
    @locale_doc
    async def raidbattle(
            self, ctx, money: IntGreaterThan(-1) = 0, enemy: discord.Member = None
    ):
        _(
            """`[money]` - A whole number that can be 0 or greater; defaults to 0
            `[enemy]` - A user who has a profile; defaults to anyone

            Fight against another player while betting money.
            To decide the players' stats, their items, race and class bonuses and raidstats are evaluated.

            You also have a chance of tripping depending on your luck.

            The money is removed from both players at the start of the battle. Once a winner has been decided, they will receive their money, plus the enemy's money.
            The battle is divided into turns, in which each combatant (player or pet) takes an action.

            The battle ends if one side's all combatants' HP drop to 0 (winner decided), or if 5 minutes after the battle started pass (tie).
            In case of a tie, both players will get their money back.

            The battle's winner will receive a PvP win, which shows on their profile.
            (This command has a cooldown of 5 minutes)"""
        )
        authorchance = 0
        enemychance = 0
        cheated = False
        max_hp_limit = 5000

        if enemy == ctx.author:
            await self.bot.reset_cooldown(ctx)
            return await ctx.send(_("You can't battle yourself."))

        if ctx.character_data["money"] < money:
            await self.bot.reset_cooldown(ctx)
            return await ctx.send(_("You are too poor."))

        # Deduct money from the author
        await self.bot.pool.execute(
            'UPDATE profile SET "money"="money"-$1 WHERE "user"=$2;',
            money,
            ctx.author.id,
        )

        # Prepare battle initiation message
        if not enemy:
            text = _("{author} - **LVL {level}** seeks a raidbattle! The price is **${money}**.").format(
                author=ctx.author.mention, level=rpgtools.xptolevel(ctx.character_data["xp"]), money=money
            )
        else:
            async with self.bot.pool.acquire() as conn:
                query = 'SELECT xp FROM profile WHERE "user" = $1;'
                xp_value = await conn.fetchval(query, enemy.id)
            text = _(
                "{author} - **LVL {level}** seeks a raidbattle with {enemy} - LVL **{levelen}**! The price is **${money}**."
            ).format(
                author=ctx.author.mention,
                level=rpgtools.xptolevel(ctx.character_data["xp"]),
                enemy=enemy.mention,
                levelen=rpgtools.xptolevel(xp_value) if xp_value else "Unknown",
                money=money
            )

        # Define a check for the join view
        async def check(user: discord.User) -> bool:
            return await has_money(self.bot, user.id, money)

        # Create the join view
        future = asyncio.Future()
        view = SingleJoinView(
            future,
            Button(
                style=discord.ButtonStyle.primary,
                label=_("Join the raidbattle!"),
                emoji="\U00002694",
            ),
            allowed=enemy,
            prohibited=ctx.author,
            timeout=60,
            check=check,
            check_fail_message=_("You don't have enough money to join the raidbattle."),
        )

        await ctx.send(text, view=view)

        try:
            enemy_ = await future
        except asyncio.TimeoutError:
            await self.bot.reset_cooldown(ctx)
            # Refund money to the author
            await self.bot.pool.execute(
                'UPDATE profile SET "money"="money"+$1 WHERE "user"=$2;',
                money,
                ctx.author.id,
            )
            return await ctx.send(
                _("No one wanted to join your raidbattle, {author}!").format(
                    author=ctx.author.mention
                )
            )

        # Deduct money from the enemy
        await self.bot.pool.execute(
            'UPDATE profile SET "money"="money"-$1 WHERE "user"=$2;',
            money,
            enemy_.id
        )

        # Initialize combatants
        try:
            # Fetch elements for both players
            highest_element_author = await self.fetch_highest_element(ctx.author.id)
            highest_element_enemy = await self.fetch_highest_element(enemy_.id)

            # Define element to emoji mapping
            emoji_to_element = {
                "🌟": "Light",
                "🌑": "Dark",
                "🔥": "Fire",
                "💧": "Water",
                "🌿": "Nature",
                "⚡": "Electric",
                "💨": "Wind",
                "🌀": "Corrupted"
            }

            # Define other mappings
            specified_words_values = {
                "Deathshroud": 20,
                "Soul Warden": 30,
                "Reaper": 40,
                "Phantom Scythe": 50,
                "Soul Snatcher": 60,
                "Deathbringer": 70,
                "Grim Reaper": 80,
            }

            life_steal_values = {
                "Little Helper": 7,
                "Gift Gatherer": 14,
                "Holiday Aide": 21,
                "Joyful Jester": 28,
                "Yuletide Guardian": 35,
                "Festive Enforcer": 40,
                "Festive Champion": 60,
            }

            mage_evolution_levels = {
                "Witcher": 1,
                "Enchanter": 2,
                "Mage": 3,
                "Warlock": 4,
                "Dark Caster": 5,
                "White Sorcerer": 6,
            }

            evolution_damage_multiplier = {
                1: 1.10,  # 110%
                2: 1.20,  # 120%
                3: 1.30,  # 130%
                4: 1.50,  # 150%
                5: 1.75,  # 175%
                6: 2.00,  # 200%
            }

            tank_evolution_levels = {
                "Protector": 1,
                "Guardian": 2,
                "Bulwark": 3,
                "Defender": 4,
                "Vanguard": 5,
                "Fortress": 6,
                "Titan": 7,
            }

            evolution_health_multiplier = {
                1: 1.05,  # 105%
                2: 1.10,  # 110%
                3: 1.15,  # 115%
                4: 1.20,  # 120%
                5: 1.25,  # 125%
                6: 1.30,  # 130%
                7: 1.35,  # 135%
            }

            evolution_reflection_multiplier = {
                1: 0.04,  # 4%
                2: 0.08,  # 8%
                3: 0.12,  # 12%
                4: 0.16,  # 16%
                5: 0.20,  # 20%
                6: 0.24,  # 24%
                7: 0.28,  # 28%
            }

            # Fetch classes and XP for both players
            async with self.bot.pool.acquire() as conn:
                # Fetch data for the author
                result_author = await conn.fetchrow(
                    'SELECT "class", "xp" FROM profile WHERE "user" = $1;',
                    ctx.author.id
                )
                auth_classes = result_author["class"] if result_author and "class" in result_author else []
                auth_xp = result_author["xp"] if result_author and "xp" in result_author else 0
                auth_level = rpgtools.xptolevel(auth_xp)

                # Fetch data for the enemy
                result_enemy = await conn.fetchrow(
                    'SELECT "class", "xp" FROM profile WHERE "user" = $1;',
                    enemy_.id
                )
                enemy_classes = result_enemy["class"] if result_enemy and "class" in result_enemy else []
                enemy_xp = result_enemy["xp"] if result_enemy and "xp" in result_enemy else 0
                enemy_level = rpgtools.xptolevel(enemy_xp)

            # Initialize chance variables
            author_chance = 0
            enemy_chance = 0
            lifestealauth = 0
            lifestealopp = 0


            def get_tank_evolution(classes):
                max_evolution = None
                for class_name in classes:
                    if class_name in tank_evolution_levels:
                        level = tank_evolution_levels[class_name]
                        if max_evolution is None or level > max_evolution:
                            max_evolution = level
                return max_evolution

            # Function to get Mage evolution level
            def get_mage_evolution(classes):
                max_evolution = None
                for class_name in classes:
                    if class_name in mage_evolution_levels:
                        level = mage_evolution_levels[class_name]
                        if max_evolution is None or level > max_evolution:
                            max_evolution = level
                return max_evolution

            # Calculate chances for the author
            author_mage_evolution = get_mage_evolution(auth_classes)
            for class_name in auth_classes:
                if class_name in specified_words_values:
                    author_chance += specified_words_values[class_name]
                if class_name in life_steal_values:
                    lifestealauth += life_steal_values[class_name]

            # Calculate chances for the enemy
            enemy_mage_evolution = get_mage_evolution(enemy_classes)
            for class_name in enemy_classes:
                if class_name in specified_words_values:
                    enemy_chance += specified_words_values[class_name]
                if class_name in life_steal_values:
                    lifestealopp += life_steal_values[class_name]

            # Assign chances
            if author_chance != 0:
                authorchance = author_chance

            if enemy_chance != 0:
                enemychance = enemy_chance

            # Fetch player stats and assign to sides
            async with self.bot.pool.acquire() as conn:
                author_combatant, author_pet_combatant = await self.fetch_combatants(
                    ctx, ctx.author, highest_element_author, auth_level, lifestealauth, author_mage_evolution, conn
                )
                enemy_combatant, enemy_pet_combatant = await self.fetch_combatants(
                    ctx, enemy_, highest_element_enemy, enemy_level, lifestealopp, enemy_mage_evolution, conn
                )

            # Determine elements for damage modifiers
            element_strengths = {
                "Light": "Corrupted",
                "Dark": "Light",
                "Corrupted": "Dark",
                "Nature": "Electric",
                "Electric": "Water",
                "Water": "Fire",
                "Fire": "Nature",
                "Wind": "Electric",
                "Unknown": None  # Adding 'Unknown' to handle default cases
            }

            def calculate_damage_modifier(attacker_element, defender_element):
                if attacker_element in element_strengths and element_strengths[attacker_element] == defender_element:
                    return round(randomm.uniform(0.1, 0.3), 3)  # Positive modifier
                elif defender_element in element_strengths and element_strengths[defender_element] == attacker_element:
                    return round(randomm.uniform(-0.3, -0.1), 3)  # Negative modifier
                return 0.0

            # Apply damage modifiers
            author_combatant["damage"] = round(author_combatant["damage"] * (
                    1 + calculate_damage_modifier(author_combatant["element"], enemy_combatant["element"])), 3)
            if author_pet_combatant:
                author_pet_combatant["damage"] = round(author_pet_combatant["damage"] * (
                        1 + calculate_damage_modifier(author_pet_combatant["element"], enemy_combatant["element"])),
                                                       3)

            enemy_combatant["damage"] = round(enemy_combatant["damage"] * (
                    1 + calculate_damage_modifier(enemy_combatant["element"], author_combatant["element"])), 3)
            if enemy_pet_combatant:
                enemy_pet_combatant["damage"] = round(enemy_pet_combatant["damage"] * (
                        1 + calculate_damage_modifier(enemy_pet_combatant["element"], author_combatant["element"])),
                                                      3)

            # Create initial battle log
            battle_log = deque(
                [
                    f"**Action #0**\nRaidbattle {ctx.author.mention} vs. {enemy_.mention} started!"
                ],
                maxlen=5  # Adjust as needed for log size
            )

            # Create initial embed
            embed = discord.Embed(
                title=f"Raid Battle: {ctx.author.display_name} vs {enemy_.display_name}",
                color=self.bot.config.game.primary_colour
            )

            # Initialize player and pet stats in the embed
            for combatant in [author_combatant, author_pet_combatant, enemy_combatant, enemy_pet_combatant]:
                if not combatant:
                    continue  # Skip if pet does not exist
                current_hp = max(0, round(combatant["hp"], 1))  # Rounded to .0
                max_hp = round(combatant["max_hp"], 1)
                hp_bar = self.create_hp_bar(current_hp, max_hp)
                if not combatant.get("is_pet"):
                    # Player's element emoji
                    element_emoji = "❌"  # Default emoji
                    for emoji, element in emoji_to_element.items():
                        if element == combatant["element"]:
                            element_emoji = emoji
                            break
                    if combatant['user'].id == ctx.author.id:
                        field_name = f"[TEAM A]\n{combatant['user'].display_name} {element_emoji}"
                    else:
                        field_name = f"[TEAM B]\n{combatant['user'].display_name} {element_emoji}"
                else:
                    # Pet's element emoji
                    pet_element_emoji = "❌"  # Default emoji
                    for emoji, element in emoji_to_element.items():
                        if element == combatant["element"]:
                            pet_element_emoji = emoji
                            break
                    field_name = f"{combatant['pet_name']} {pet_element_emoji}"
                # Format HP with one decimal place
                field_value = f"HP: {current_hp:.1f}/{max_hp:.1f}\n{hp_bar}"
                embed.add_field(name=field_name, value=field_value, inline=False)

            # Add initial battle log
            embed.add_field(name="Battle Log", value=battle_log[0], inline=False)

            log_message = await ctx.send(embed=embed)
            await asyncio.sleep(4)

            start_time = datetime.datetime.utcnow()

            action_number = 1  # Starting from Action #1

            battle_ongoing = True
            combatant_order_options = [
                author_combatant,
                enemy_pet_combatant,
                author_pet_combatant,
                enemy_combatant
            ]

            # Shuffle the list in place
            random.shuffle(combatant_order_options)

            # The shuffled list is now in combatant_order_options
            combatant_order = combatant_order_options

            while battle_ongoing and datetime.datetime.utcnow() < start_time + datetime.timedelta(minutes=5):
                for combatant in combatant_order:
                    if not combatant or combatant["hp"] <= 0:
                        continue  # Skip dead or non-existent combatants

                    # Determine the opponent's combatants
                    if combatant in [author_combatant, author_pet_combatant]:
                        opponent_combatant = enemy_combatant
                        opponent_pet_combatant = enemy_pet_combatant
                        opponent_user = enemy_
                    else:
                        opponent_combatant = author_combatant
                        opponent_pet_combatant = author_pet_combatant
                        opponent_user = ctx.author

                    # Combatant attacks
                    target = self.select_target(opponent_combatant, opponent_pet_combatant, player_prob=0.60,
                                                pet_prob=0.40)
                    if target is not None:
                        # Calculate base damage
                        if combatant.get("is_pet"):
                            damage_variance = random.randint(0, 50)
                        else:
                            damage_variance = random.randint(0, 100)

                        # Calculate raw damage before armor
                        raw_damage = combatant["damage"] + damage_variance

                        # Calculate how much damage was blocked by armor
                        blocked_damage = min(raw_damage, target["armor"])

                        # Calculate final damage that gets through armor
                        dmg = round(max(raw_damage - target["armor"], 1), 3)

                        # Apply damage to target
                        target["hp"] -= dmg
                        target["hp"] = max(target["hp"], 0)

                        # Build initial message
                        if combatant.get("is_pet"):
                            attacker_name = combatant['pet_name']
                        else:
                            attacker_name = combatant['user'].mention
                        if target.get("is_pet"):
                            target_name = target['pet_name']
                        else:
                            target_name = target['user'].mention

                        message = f"{attacker_name} attacks! {target_name} takes **{dmg:.3f}HP** damage."

                        # Handle damage reflection if target is a tank
                        if target.get("damage_reflection", 0) > 0:
                            # Reflect based on the total damage blocked by armor
                            reflected_damage = round(blocked_damage * target["damage_reflection"], 3)
                            if reflected_damage > 0:
                                combatant["hp"] -= reflected_damage
                                combatant["hp"] = max(combatant["hp"], 0)
                                message += f"\n{target_name}'s armor reflects **{reflected_damage:.3f}HP** damage back!"

                                # Check if attacker died from reflection
                                if combatant["hp"] <= 0:
                                    message += f" {attacker_name} has been defeated by reflected damage!"

                        # Handle lifesteal if applicable
                        if not combatant.get("is_pet"):
                            if combatant["user"] == ctx.author and lifestealauth != 0:
                                lifesteal_percentage = lifestealauth / 100.0
                                heal = round(lifesteal_percentage * dmg, 3)
                                combatant["hp"] = min(combatant["hp"] + heal, combatant["max_hp"])
                                message += f"\nLifesteals: **{heal:.3f}HP**"
                            elif combatant["user"] == enemy_ and lifestealopp != 0:
                                lifesteal_percentage = lifestealopp / 100.0
                                heal = round(lifesteal_percentage * dmg, 3)
                                combatant["hp"] = min(combatant["hp"] + heal, combatant["max_hp"])
                                message += f"\nLifesteals: **{heal:.3f}HP**"

                        # Check if target is defeated
                        if target["hp"] <= 0:
                            message += f"\n{target_name} has been defeated!"

                        # Append message to battle log
                        battle_log.append(f"**Action #{action_number}**\n{message}")
                        action_number += 1

                        # Update the embed after each action
                        embed = discord.Embed(
                            title=f"Raid Battle: {ctx.author.display_name} vs {enemy_.display_name}",
                            color=self.bot.config.game.primary_colour
                        )

                        # Update player and pet stats in the embed
                        for c in [author_combatant, author_pet_combatant, enemy_combatant, enemy_pet_combatant]:
                            if not c:
                                continue  # Skip if pet does not exist
                            current_hp = max(0, round(c["hp"], 1))  # Rounded to .1
                            max_hp = round(c["max_hp"], 1)
                            hp_bar = self.create_hp_bar(current_hp, max_hp)

                            # Add tank indicator if applicable
                            tank_indicator = "🛡️" if c.get("tank_evolution") else ""

                            if not c.get("is_pet"):
                                # Player's element emoji
                                element_emoji = "❌"  # Default emoji
                                for emoji, element in emoji_to_element.items():
                                    if element == c["element"]:
                                        element_emoji = emoji
                                        break
                                if c['user'].id == ctx.author.id:
                                    field_name = f"[TEAM A]\n{c['user'].display_name} {element_emoji} {tank_indicator}"
                                else:
                                    field_name = f"[TEAM B]\n{c['user'].display_name} {element_emoji} {tank_indicator}"
                            else:
                                # Pet's element emoji
                                pet_element_emoji = "❌"  # Default emoji
                                for emoji, element in emoji_to_element.items():
                                    if element == c["element"]:
                                        pet_element_emoji = emoji
                                        break
                                field_name = f"{c['pet_name']} {pet_element_emoji}"

                            # Format HP with one decimal place
                            field_value = f"HP: {current_hp:.1f}/{max_hp:.1f}\n{hp_bar}"

                            # Add reflection percentage for tanks
                            if c.get("damage_reflection", 0) > 0:
                                reflection_percent = c["damage_reflection"] * 100
                                field_value += f"\nDamage Reflection: {reflection_percent:.1f}%"

                            embed.add_field(name=field_name, value=field_value, inline=False)

                        # Update battle log in the embed
                        battle_log_text = '\n\n'.join(battle_log)
                        embed.add_field(name="Battle Log", value=battle_log_text, inline=False)

                        await log_message.edit(embed=embed)
                        await asyncio.sleep(4)

                        # Check win conditions including reflection deaths
                        if opponent_combatant["hp"] <= 0 and (
                                opponent_pet_combatant is None or opponent_pet_combatant["hp"] <= 0):
                            battle_ongoing = False
                            # If combatant is a pet, use its owner as winner
                            if combatant.get("is_pet"):
                                winner = combatant['user']  # This is the owner's user object
                            else:
                                winner = combatant['user']
                            loser = opponent_user
                            break
                        elif author_combatant["hp"] <= 0 and (
                                author_pet_combatant is None or author_pet_combatant["hp"] <= 0):
                            battle_ongoing = False
                            winner = enemy_
                            loser = ctx.author
                            break
                        elif enemy_combatant["hp"] <= 0 and (
                                enemy_pet_combatant is None or enemy_pet_combatant["hp"] <= 0):
                            battle_ongoing = False
                            winner = ctx.author
                            loser = enemy_
                            break

            if battle_ongoing:
                # Time limit reached, it's a tie
                # Refund money
                async with self.bot.pool.acquire() as conn:
                    await conn.execute(
                        'UPDATE profile SET "money"="money"+$1 WHERE "user"=$2;',
                        money,
                        ctx.author.id,
                    )
                    await conn.execute(
                        'UPDATE profile SET "money"="money"+$1 WHERE "user"=$2;',
                        money,
                        enemy_.id,
                    )
                await ctx.send(
                    _("The raidbattle between {p1} and {p2} ended in a tie! Money has been refunded.").format(
                        p1=ctx.author.mention, p2=enemy_.mention
                    )
                )
            else:
                # We have a winner
                if winner:
                    # Update database and send final message
                    async with self.bot.pool.acquire() as conn:
                        await conn.execute(
                            'UPDATE profile SET "money"="money"+$1, "pvpwins"="pvpwins"+1 WHERE'
                            ' "user"=$2;',
                            money * 2,
                            winner.id,
                        )
                        await self.bot.log_transaction(
                            ctx,
                            from_=loser.id,
                            to=winner.id,
                            subject="RaidBattle Bet",
                            data={"Gold": money},
                            conn=conn,
                        )
                    await ctx.send(
                        _("{p1} won the raidbattle vs {p2}! Congratulations!").format(
                            p1=winner.mention, p2=loser.mention
                        )
                    )
                else:
                    # It's a tie (should not happen here)
                    await ctx.send(
                        _("The raidbattle between {p1} and {p2} ended in a tie! Money has been refunded.").format(
                            p1=ctx.author.mention, p2=enemy_.mention
                        )
                    )
        except Exception as e:
            import traceback
            error_message = f"An error occurred while determining the winner: {e}\n"
            error_message += traceback.format_exc()
            await ctx.send(error_message)
            print(error_message)

    # Helper methods within your Cog or Bot class

    async def fetch_highest_element(self, user_id):
        try:
            highest_items = await self.bot.pool.fetch(
                "SELECT ai.element FROM profile p JOIN allitems ai ON (p.user=ai.owner) JOIN"
                " inventory i ON (ai.id=i.item) WHERE i.equipped IS TRUE AND p.user=$1"
                " ORDER BY GREATEST(ai.damage, ai.armor) DESC;",
                user_id,
            )
            highest_element = highest_items[0]["element"].capitalize() if highest_items and highest_items[0][
                "element"] else "Unknown"
            return highest_element
        except Exception as e:
            await self.bot.pool.execute(
                'UPDATE profile SET "element"="Unknown" WHERE "user"=$1;',
                user_id
            )
            return "Unknown"

    async def fetch_combatants(self, ctx, player, highest_element, level, lifesteal, mage_evolution, conn):
        try:
            # First check if player has a shield equipped
            shield_check = await conn.fetchrow(
                "SELECT ai.* FROM profile p JOIN allitems ai ON (p.user=ai.owner) "
                "JOIN inventory i ON (ai.id=i.item) WHERE p.user=$1 AND "
                "i.equipped IS TRUE AND ai.type='Shield';",
                player.id
            )
            has_shield = bool(shield_check)

            # Fetch stats
            query = 'SELECT "luck", "health", "stathp", "class" FROM profile WHERE "user" = $1;'
            result = await conn.fetchrow(query, player.id)
            if result:
                luck_value = float(result['luck'])
                if luck_value <= 0.3:
                    Luck = 20.0
                else:
                    Luck = ((luck_value - 0.3) / (1.5 - 0.3)) * 80 + 20
                Luck = round(Luck, 2)

                # Apply luck booster
                luck_booster = await self.bot.get_booster(player, "luck")
                if luck_booster:
                    Luck += Luck * 0.25
                    Luck = min(Luck, 100.0)

                base_health = 250.0
                health = float(result['health']) + base_health
                stathp = float(result['stathp']) * 50.0
                player_classes = result['class']
                dmg, deff = await self.bot.get_raidstats(player, conn=conn)

                # Ensure dmg and deff are floats
                dmg = float(dmg)
                deff = float(deff)

                total_health = health + level * 5.0 + stathp

                # Get tank evolution level from player classes
                tank_evolution = None
                tank_evolution_levels = {
                    "Protector": 1,
                    "Guardian": 2,
                    "Bulwark": 3,
                    "Defender": 4,
                    "Vanguard": 5,
                    "Fortress": 6,
                    "Titan": 7,
                }

                for class_name in player_classes:
                    if class_name in tank_evolution_levels:
                        level = tank_evolution_levels[class_name]
                        if tank_evolution is None or level > tank_evolution:
                            tank_evolution = level

                # Only apply tank bonuses if they have a shield equipped
                damage_reflection = 0.0
                if tank_evolution and has_shield:
                    # Health bonus: +5% per evolution
                    health_multiplier = 1 + (0.04 * tank_evolution)
                    total_health *= health_multiplier

                    # Damage reflection: +3% per evolution
                    damage_reflection = 0.03 * tank_evolution
                elif tank_evolution and not has_shield:
                    # If they're a tank but don't have a shield, still give them a smaller health bonus
                    # but no reflection
                    health_multiplier = 1 + (0.01 * tank_evolution)  # Half the normal bonus
                    total_health *= health_multiplier



                # Create combatant dictionary
                combatant = {
                    "user": player,
                    "hp": total_health,
                    "armor": deff,
                    "damage": dmg,
                    "luck": Luck,
                    "mage_evolution": mage_evolution,
                    "tank_evolution": tank_evolution,
                    "has_shield": has_shield,  # Add this to track shield status
                    "damage_reflection": damage_reflection,
                    "max_hp": total_health,
                    "is_pet": False,
                    "element": highest_element if highest_element else "Unknown"
                }

                # Fetch and assign equipped pet
                pet = await conn.fetchrow(
                    "SELECT * FROM monster_pets WHERE user_id = $1 AND equipped = TRUE;",
                    player.id
                )
                if pet:
                    pet_element = pet["element"].capitalize() if pet["element"] else "Unknown"
                    pet_combatant = {
                        "user": player,  # Reference to owner
                        "owner_id": player.id,  # Owner's Discord ID
                        "pet_name": pet["name"],  # Pet's name
                        "hp": float(pet["hp"]),
                        "armor": float(pet["defense"]),
                        "damage": float(pet["attack"]),
                        "luck": 50.0,  # Assuming fixed luck; adjust as needed
                        "element": pet_element,  # Already capitalized or set to "Unknown"
                        "max_hp": float(pet["hp"]),
                        "damage_reflection": 0.0,  # Pets don't have damage reflection
                        "is_pet": True
                    }
                    return combatant, pet_combatant
                else:
                    return combatant, None
            else:
                # Default combatant if no profile found
                combatant = {
                    "user": player,
                    "hp": 500.0,
                    "armor": 50.0,
                    "damage": 50.0,
                    "luck": 50.0,
                    "mage_evolution": None,
                    "tank_evolution": None,
                    "has_shield": False,
                    "damage_reflection": 0.0,
                    "max_hp": 500.0,
                    "is_pet": False,
                    "element": "Unknown"
                }
                return combatant, None
        except Exception as e:
            await ctx.send(f"An error occurred while fetching stats for {player.display_name}: {e}")
            # Return default combatant
            combatant = {
                "user": player,
                "hp": 500.0,
                "armor": 50.0,
                "damage": 50.0,
                "luck": 50.0,
                "mage_evolution": None,
                "tank_evolution": None,
                "has_shield": False,
                "damage_reflection": 0.0,
                "max_hp": 500.0,
                "is_pet": False,
                "element": "Unknown"
            }
            return combatant, None

    def create_hp_bar(self, current_hp, max_hp, length=20):
        ratio = current_hp / max_hp if max_hp > 0 else 0
        ratio = max(0, min(1, ratio))  # Ensure ratio is between 0 and 1
        filled_length = int(length * ratio)
        bar = '█' * filled_length + '░' * (length - filled_length)
        return bar

    def select_target(self, player_combatant, pet_combatant, player_prob=0.60, pet_prob=0.40):
        targets = []
        weights = []
        if player_combatant and player_combatant['hp'] > 0:
            targets.append(player_combatant)
            weights.append(player_prob)
        if pet_combatant and pet_combatant['hp'] > 0:
            targets.append(pet_combatant)
            weights.append(pet_prob)
        if targets:
            return randomm.choices(targets, weights=weights)[0]
        else:
            return None

    @is_gm()
    @has_char()
    @user_cooldown(100)
    @commands.command(brief=_("Battle in teams of two against another team (includes raidstats)"))
    @locale_doc
    async def raidbattle2v2(
            self, ctx, money: IntGreaterThan(-1) = 0, teammate: discord.Member = None,
            opponents: commands.Greedy[discord.Member] = None
    ):
        _(
            """`[money]` - A whole number that can be 0 or greater; defaults to 0
            `[teammate]` - A user who will join your team
            `[opponents]` - Two users who will be the opposing team

            Fight in teams of two against another team while betting money.
            To decide the players' stats, their items, race and class bonuses and raidstats are evaluated.

            You also have a chance of tripping depending on your luck.

            The money is removed from all players at the start of the battle. Once a winning team has been decided, they will receive their money, plus the opposing team's money.
            The battle is divided into rounds, where each team takes turns attacking.

            The battle ends if all players on a team have their HP drop to 0 (winner decided), or if 5 minutes after the battle started pass (tie).
            In case of a tie, all players will get their money back.

            Each member of the winning team will receive a PvP win, which shows on their profile.
            (This command has a cooldown of 5 minutes)"""
        )

        # Initial checks
        if teammate == ctx.author:
            await self.bot.reset_cooldown(ctx)
            return await ctx.send(_("You can't be your own teammate."))

        if not opponents or len(opponents) != 2:
            await self.bot.reset_cooldown(ctx)
            return await ctx.send(_("You must specify exactly two opponents."))

        if ctx.author in opponents or teammate in opponents or teammate == ctx.author:
            await self.bot.reset_cooldown(ctx)
            return await ctx.send(_("Invalid team configuration."))

        if ctx.character_data["money"] < money:
            await self.bot.reset_cooldown(ctx)
            return await ctx.send(_("You are too poor."))

        # Deduct money from initiating player
        await self.bot.pool.execute(
            'UPDATE profile SET "money"="money"-$1 WHERE "user"=$2;',
            money,
            ctx.author.id,
        )

        # Create the battle invitation
        text = _("{author} and {teammate} seek a 2v2 raidbattle! The price is **${money}** per player.").format(
            author=ctx.author.mention,
            teammate=teammate.mention if teammate else "an ally",
            money=money
        )

        # Function to check if a user has enough money
        async def check(user: discord.User) -> bool:
            return await has_money(self.bot, user.id, money)

        future_teammate = asyncio.Future()
        future_opponents = [asyncio.Future(), asyncio.Future()]

        # Create the join view for the teammate
        view_teammate = SingleJoinView(
            future_teammate,
            Button(
                style=ButtonStyle.primary,
                label=_("Join as Teammate"),
                emoji="🤝",
            ),
            allowed=teammate,
            prohibited=ctx.author,
            timeout=60,
            check=check,
            check_fail_message=_("You don't have enough money to join the raidbattle."),
        )

        # Send the invitation for the teammate
        await ctx.send(text, view=view_teammate)

        # Wait for teammate to join
        try:
            teammate_ = await future_teammate
        except asyncio.TimeoutError:
            await self.bot.reset_cooldown(ctx)
            await self.bot.pool.execute(
                'UPDATE profile SET "money"="money"+$1 WHERE "user"=$2;',
                money,
                ctx.author.id,
            )
            return await ctx.send(
                _("Your teammate did not join in time, {author}.").format(
                    author=ctx.author.mention
                )
            )

        # Deduct money from teammate
        await self.bot.pool.execute(
            'UPDATE profile SET "money"="money"-$1 WHERE "user"=$2;',
            money,
            teammate_.id,
        )

        # Create the join views for the opponents
        opponent_views = []
        for i, opponent in enumerate(opponents):
            view_opponent = SingleJoinView(
                future_opponents[i],
                Button(
                    style=ButtonStyle.danger,
                    label=_("Join as Opponent"),
                    emoji="⚔️",
                ),
                allowed=opponent,
                prohibited=[ctx.author, teammate_],
                timeout=60,
                check=check,
                check_fail_message=_("You don't have enough money to join the raidbattle."),
            )
            opponent_views.append(view_opponent)
            await ctx.send(
                _("{opponent}, you have been challenged to a raidbattle!").format(
                    opponent=opponent.mention
                ),
                view=view_opponent,
            )

        # Wait for opponents to join
        try:
            opponents_ = [await future for future in future_opponents]
        except asyncio.TimeoutError:
            await self.bot.reset_cooldown(ctx)
            # Refund money to initiating team
            await self.bot.pool.execute(
                'UPDATE profile SET "money"="money"+$1 WHERE "user" IN ($2, $3);',
                money,
                ctx.author.id,
                teammate_.id,
            )
            return await ctx.send(
                _("Not all opponents joined the raidbattle, {author} and {teammate}.").format(
                    author=ctx.author.mention,
                    teammate=teammate_.mention
                )
            )

        # Deduct money from opponents
        for opponent in opponents_:
            await self.bot.pool.execute(
                'UPDATE profile SET "money"="money"-$1 WHERE "user"=$2;',
                money,
                opponent.id,
            )

        # Now, set up the teams
        team_a = [ctx.author, teammate_]
        team_b = opponents_

        # Initialize players' data
        players_data = []

        # Fetch player stats for all players
        async with self.bot.pool.acquire() as conn:
            for player in team_a + team_b:
                try:
                    user_id = player.id

                    luck_booster = await self.bot.get_booster(player, "luck")

                    query = 'SELECT "luck", "health", "stathp" FROM profile WHERE "user" = $1;'
                    result = await conn.fetchrow(query, user_id)
                    if result:
                        luck_value = float(result['luck'])
                        if luck_value <= 0.3:
                            Luck = 20
                        else:
                            Luck = ((luck_value - 0.3) / (1.5 - 0.3)) * 80 + 20
                        Luck = float(round(Luck, 2))

                        if luck_booster:
                            Luck += Luck * 0.25
                            Luck = float(min(Luck, 100))

                        base_health = 250
                        health = result['health'] + base_health
                        stathp = result['stathp'] * 50
                        dmg, deff = await self.bot.get_raidstats(player, conn=conn)

                        # Get XP and level
                        xp = await conn.fetchval('SELECT "xp" FROM profile WHERE "user" = $1;', user_id)
                        level = rpgtools.xptolevel(xp)
                        total_health = health + (level * 5)
                        total_health = total_health + stathp

                        # Create player dictionary with relevant information
                        player_data = {
                            "user": player,
                            "hp": total_health,
                            "max_hp": total_health,
                            "armor": deff,
                            "damage": dmg,
                            "luck": Luck,
                            "team": "A" if player in team_a else "B"
                        }
                        players_data.append(player_data)
                    else:
                        await ctx.send(f"User with ID {user_id} not found in the profile table.")
                except Exception as e:
                    await ctx.send(f"An error occurred: {e}")

        # Begin the battle
        battle_log = deque(
            [
                (
                    0,
                    _("Raidbattle Team A vs. Team B started!")
                )
            ],
            maxlen=5,
        )

        # Function to create HP bar
        def create_hp_bar(self, current_hp, max_hp, length=20):
            ratio = current_hp / max_hp if max_hp > 0 else 0
            ratio = max(0, min(1, ratio))  # Ensure ratio is between 0 and 1
            filled_length = int(length * ratio)
            bar = '█' * filled_length + '░' * (length - filled_length)
            return bar

        # Create initial embed
        embed = discord.Embed(
            title=_("Raid Battle: Team A vs Team B"),
            color=self.bot.config.game.primary_colour
        )

        # Initialize player stats in the embed
        for team_label, team in [("Team A", team_a), ("Team B", team_b)]:
            team_players = [p for p in players_data if p["user"] in team]
            for player in team_players:
                current_hp = max(0, round(player["hp"], 2))
                max_hp = player["max_hp"]
                hp_bar = create_hp_bar(current_hp, max_hp)
                field_name = f"{player['user'].display_name} [{team_label}]"
                field_value = f"HP: {current_hp}/{max_hp}\n{hp_bar}"
                embed.add_field(name=field_name, value=field_value, inline=False)

        # Add initial battle log
        embed.add_field(name=_("Battle Log"), value=battle_log[0][1], inline=False)

        log_message = await ctx.send(embed=embed)
        await asyncio.sleep(4)

        start = datetime.datetime.utcnow()
        attacking_team = random.choice(["A", "B"])
        team_players = {"A": [p for p in players_data if p["team"] == "A"],
                        "B": [p for p in players_data if p["team"] == "B"]}

        # Main battle loop
        while (
                any(p["hp"] > 0 for p in team_players["A"])
                and any(p["hp"] > 0 for p in team_players["B"])
                and datetime.datetime.utcnow() < start + datetime.timedelta(minutes=5)
        ):
            # Attacking team attacks
            attackers = [p for p in team_players[attacking_team] if p["hp"] > 0]
            defenders = [p for p in team_players["B" if attacking_team == "A" else "A"] if p["hp"] > 0]

            for attacker in attackers:
                if not defenders:
                    break  # No defenders left
                defender = random.choice(defenders)

                trickluck = float(random.randint(1, 100))

                if float(trickluck) <= float(attacker["luck"]):
                    # Regular attack
                    dmg = (
                            attacker["damage"] + Decimal(random.randint(0, 100)) - defender["armor"]
                    )
                    dmg = max(dmg, 1)
                    defender["hp"] -= dmg

                    # Initialize message
                    message = _("{attacker} attacks! {defender} takes **{dmg}HP** damage.").format(
                        attacker=attacker["user"],
                        defender=defender["user"],
                        dmg=dmg,
                    )

                    # Check if defender is defeated
                    if defender["hp"] <= 0:
                        defender["hp"] = 0
                        message += _(" {defender} is defeated!").format(
                            defender=defender["user"]
                        )
                        defenders.remove(defender)
                else:
                    # Attacker tripped and took damage
                    dmg = Decimal('10.000')
                    attacker["hp"] -= dmg
                    attacker["hp"] = max(attacker["hp"], 0)
                    message = _("{attacker} tripped and took **{dmg}HP** damage. Bad luck!").format(
                        attacker=attacker["user"],
                        dmg=dmg,
                    )

                # Append message to battle log
                battle_log.append(
                    (
                        battle_log[-1][0] + 1,
                        message,
                    )
                )

                # Update the embed
                embed = discord.Embed(
                    title=_("Raid Battle: Team A vs Team B"),
                    color=self.bot.config.game.primary_colour
                )

                # Update player stats in the embed
                for team_label, team in [("Team A", team_a), ("Team B", team_b)]:
                    team_players_list = [p for p in players_data if p["user"] in team]
                    for player in team_players_list:
                        current_hp = max(0, round(player["hp"], 2))
                        max_hp = player["max_hp"]
                        hp_bar = create_hp_bar(current_hp, max_hp)
                        field_name = f"{player['user'].display_name} [{team_label}]"
                        field_value = f"HP: {current_hp}/{max_hp}\n{hp_bar}"
                        embed.add_field(name=field_name, value=field_value, inline=False)

                # Update battle log in the embed
                battle_log_text = ''
                for line in battle_log:
                    battle_log_text += f"**Action #{line[0]}**\n{line[1]}\n"

                embed.add_field(name=_("Battle Log"), value=battle_log_text, inline=False)

                await log_message.edit(embed=embed)
                await asyncio.sleep(2)

                # Check if defenders are defeated and break if so
                if not any(p["hp"] > 0 for p in defenders):
                    break  # Battle ends

            # Swap attacking team for the next turn
            attacking_team = "B" if attacking_team == "A" else "A"

        # Determine the winning team
        if any(p["hp"] > 0 for p in team_players["A"]):
            winning_team = team_players["A"]
            losing_team = team_players["B"]
        else:
            winning_team = team_players["B"]
            losing_team = team_players["A"]

        # Update database and send final message
        async with self.bot.pool.acquire() as conn:
            # Distribute winnings
            total_money = money * 4
            winnings_per_player = total_money / 2  # Split among two winning players
            for winner in winning_team:
                await conn.execute(
                    'UPDATE profile SET "money"="money"+$1, "pvpwins"="pvpwins"+1 WHERE "user"=$2;',
                    winnings_per_player,
                    winner["user"].id,
                )
            # Log transactions
            for loser in losing_team:
                await self.bot.log_transaction(
                    ctx,
                    from_=loser["user"].id,
                    to=None,
                    subject="RaidBattle Bet Loss",
                    data={"Gold": money},
                    conn=conn,
                )
            for winner in winning_team:
                await self.bot.log_transaction(
                    ctx,
                    from_=None,
                    to=winner["user"].id,
                    subject="RaidBattle Bet Win",
                    data={"Gold": winnings_per_player},
                    conn=conn,
                )

        # Announce the winning team
        winning_team_mentions = ", ".join([p["user"].mention for p in winning_team])
        losing_team_mentions = ", ".join([p["user"].mention for p in losing_team])
        await ctx.send(
            _("{winners} won the raidbattle against {losers}! Congratulations!").format(
                winners=winning_team_mentions,
                losers=losing_team_mentions
            )
        )

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

        embed.add_field(
            name="\u200b",  # Invisible spacer field
            value="\u200b",
            inline=False,
        )

        embed.add_field(
            name=_("🎮 `$pets mypets`"),
            value=_(
                "View and manage your current pets, including their stats, happiness, and hunger levels."
            ),
            inline=False,
        )

        embed.set_footer(text=_("Take care of your pets to grow them into powerful allies!"))
        await ctx.send(embed=embed)


    @is_gm()
    @has_char()
    @commands.command(brief=_("Force Legendary Spawn for Debug"), hidden=True)
    @locale_doc
    async def fl(self, ctx):
        if self.forceleg == False:
            self.forceleg = True
            await ctx.send("You forced leg on")
        else:
            self.forceleg = False
            await ctx.send("You forced leg off")


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

    # To add this command to your bot:
    # bot.add_command(gmcreatemonster)

    @has_char()
    @commands.command(brief=_("Battle against a monster and gain XP"), hidden=True)
    @user_cooldown(1800)  # 5-minute cooldown
    @locale_doc
    async def pve(self, ctx):
        _(
            """Battle against a monster and gain experience points.

            Fight against a monster of your level.
            To decide your stats, your items, race, and class bonuses are evaluated.

            You also have a chance of tripping depending on your luck.

            The battle is divided into rounds, where you and the monster take turns attacking.

            The battle ends if your HP or the monster's HP drops to 0 (winner decided), or if 5 minutes pass (tie).

            In case of a tie, no XP is gained.

            If you win, you gain XP based on the monster's level.

            (This command has a cooldown of 5 minutes)"""
        )

        monster_override = getattr(ctx, 'monster_override', None)
        levelchoice_override = getattr(ctx, 'levelchoice_override', None)


        # Define the elements and their strengths
        elements = ['Fire', 'Water', 'Earth', 'Wind', 'Light', 'Dark', 'Electric', 'Nature', 'Corrupted']

        # Define element strengths for damage modifiers
        element_strengths = {
            "Light": "Corrupted",
            "Dark": "Light",
            "Corrupted": "Dark",
            "Nature": "Electric",
            "Electric": "Water",
            "Water": "Fire",
            "Fire": "Nature",
            "Wind": "Electric"
        }

        # Define element to emoji mapping
        element_to_emoji = {
            "Light": "🌟",
            "Dark": "🌑",
            "Corrupted": "🌀",
            "Nature": "🌿",
            "Electric": "⚡",
            "Water": "💧",
            "Fire": "🔥",
            "Wind": "💨",
            "Earth": "🌍",
        }

        # Define class-specific values
        specified_words_values = {
            "Deathshroud": 20,
            "Soul Warden": 30,
            "Reaper": 40,
            "Phantom Scythe": 50,
            "Soul Snatcher": 60,
            "Deathbringer": 70,
            "Grim Reaper": 80,
        }

        life_steal_values = {
            "Little Helper": 7,
            "Gift Gatherer": 14,
            "Holiday Aide": 21,
            "Joyful Jester": 28,
            "Yuletide Guardian": 35,
            "Festive Enforcer": 40,
            "Festive Champion": 60,
        }

        mage_evolution_levels = {
            "Witcher": 1,
            "Enchanter": 2,
            "Mage": 3,
            "Warlock": 4,
            "Dark Caster": 5,
            "White Sorcerer": 6,
        }

        evolution_damage_multiplier = {
            1: 1.10,  # 110%
            2: 1.20,  # 120%
            3: 1.30,  # 130%
            4: 1.50,  # 150%
            5: 1.75,  # 175%
            6: 2.00,  # 200%
        }

        tank_evolution_levels = {
            "Protector": 1,
            "Guardian": 2,
            "Bulwark": 3,
            "Defender": 4,
            "Vanguard": 5,
            "Fortress": 6,
            "Titan": 7,
        }


        # Load the monsters from the JSON file
        try:
            with open("monsters.json", "r") as f:
                monsters_data = json.load(f)
        except Exception as e:
            await ctx.send(_("Error loading monsters data. Please contact the admin."))
            return

        # Convert keys from strings to integers and filter out non-public monsters
        monsters = {}
        for level_str, monster_list in monsters_data.items():
            level = int(level_str)
            # Only keep monsters where ispublic is True (defaulting to True if key is missing)
            public_monsters = [monster for monster in monster_list if monster.get("ispublic", True)]
            monsters[level] = public_monsters

        # Validate that each level has the required number of monsters
        for level in range(1, 12):
            if level not in monsters:
                await ctx.send(
                    _("Monsters for level {level} are incomplete. Please contact the admin.").format(level=level)
                )
                return
            if level < 8 and len(monsters[level]) < 20:
                await ctx.send(
                    _("Monsters for level {level} are incomplete. Please contact the admin.").format(level=level)
                )
                return
            if level >= 8 and len(monsters[level]) < 3:
                await ctx.send(
                    _("Level {level} monsters are incomplete. Please contact the admin.").format(level=level)
                )
                return

        # Fetch the player's XP and determine level
        player_xp = ctx.character_data.get("xp", 0)
        player_level = rpgtools.xptolevel(player_xp)

        # Send an embed indicating that the player is searching for a monster
        searching_embed = discord.Embed(
            title=_("Searching for a monster..."),
            description=_("Your journey begins as you venture into the unknown to find a worthy foe."),
            color=self.bot.config.game.primary_colour,
        )
        searching_message = await ctx.send(embed=searching_embed)

        # Simulate searching time
        if not monster_override:
            await asyncio.sleep(randomm.randint(3, 8))  # Adjust the sleep time as desired

        # Determine if a legendary monster (level 11) should spawn
        legendary_spawn_chance = 0.01  # 1% chance
        spawn_legendary = False

        if not monster_override:  # Only perform regular spawning if no override
            if player_level >= 5:
                if randomm.random() < legendary_spawn_chance:
                    spawn_legendary = True

            if ctx.author.id == 295173706496475136:
                if self.forceleg:
                    spawn_legendary = True

            if spawn_legendary:
                # Select one of the 3 legendary monsters from level 11
                monster = randomm.choice(monsters[11])
                legendary_embed = discord.Embed(
                    title=_("A Legendary God Appears!"),
                    description=_(
                        "Behold! **{monster}** has descended to challenge you! Prepare for an epic battle!"
                    ).format(monster=monster["name"]),
                    color=discord.Color.gold(),
                )
                await ctx.send(embed=legendary_embed)
                levelchoice = 11
                await asyncio.sleep(4)
            else:
                # Determine monster level based on player level
                if player_level <= 4:
                    levelchoice = randomm.randint(1, 2)
                elif player_level <= 8:
                    levelchoice = randomm.randint(1, 3)
                elif player_level <= 12:
                    levelchoice = randomm.randint(1, 4)
                elif player_level <= 15:
                    levelchoice = randomm.randint(1, 5)
                elif player_level <= 20:
                    levelchoice = randomm.randint(1, 6)
                elif player_level <= 25:
                    levelchoice = randomm.randint(1, 7)
                elif player_level <= 30:
                    levelchoice = randomm.randint(1, 8)
                elif player_level <= 35:
                    levelchoice = randomm.randint(1, 9)
                elif player_level <= 40:
                    levelchoice = randomm.randint(1, 10)
                else:  # player_level > 40
                    levelchoice = randomm.randint(1, 10)

                monster = randomm.choice(monsters[levelchoice])
        else:
            # Use the overridden monster and level from the scout command
            monster = monster_override
            levelchoice = levelchoice_override

        # Send an embed announcing the found monster
        found_embed = discord.Embed(
            title=_("Monster Found!"),
            description=_("A Level {level} **{monster}** has appeared! Prepare to fight..").format(
                level=levelchoice, monster=monster["name"]
            ),
            color=self.bot.config.game.primary_colour,
        )
        await searching_message.edit(embed=found_embed)
        await asyncio.sleep(4)

        try:
        # Fetch the player's stats and classes
            async with self.bot.pool.acquire() as conn:
                user_id = ctx.author.id

                luck_booster = await self.bot.get_booster(ctx.author, "luck")

                # Fetch luck, health, stathp, and class
                query = 'SELECT "luck", "health", "stathp", "class" FROM profile WHERE "user" = $1;'
                result = await conn.fetchrow(query, user_id)
                if result:
                    luck_value = float(result['luck'])
                    if luck_value <= 0.3:
                        Luck = 20
                    else:
                        Luck = ((luck_value - 0.3) / (1.5 - 0.3)) * 80 + 20
                    Luck = float(round(Luck, 2))

                    if luck_booster:
                        Luck += Luck * 0.25
                        Luck = float(min(Luck, 100))

                    base_health = 250
                    health = result['health'] + base_health
                    stathp = result['stathp'] * 50
                    dmg, deff = await self.bot.get_raidstats(ctx.author, conn=conn)

                    total_health = health + (player_level * 5)
                    total_health += stathp

                    # Fetch classes
                    player_classes = result['class']
                    if isinstance(player_classes, list):
                        player_classes = player_classes
                    else:
                        player_classes = [player_classes]

                    # Calculate class-based chances
                    author_chance = 0
                    lifestealauth = 0

                    # Function to get Mage evolution level
                    def get_mage_evolution(classes):
                        max_evolution = None
                        for class_name in classes:
                            if class_name in mage_evolution_levels:
                                level = mage_evolution_levels[class_name]
                                if max_evolution is None or level > max_evolution:
                                    max_evolution = level
                        return max_evolution

                    author_mage_evolution = get_mage_evolution(player_classes)
                    for class_name in player_classes:
                        if class_name in specified_words_values:
                            author_chance += specified_words_values[class_name]
                        if class_name in life_steal_values:
                            lifestealauth += life_steal_values[class_name]

                    shield_check = await conn.fetchrow(
                        "SELECT ai.* FROM profile p JOIN allitems ai ON (p.user=ai.owner) "
                        "JOIN inventory i ON (ai.id=i.item) WHERE p.user=$1 AND "
                        "i.equipped IS TRUE AND ai.type='Shield';",
                        user_id
                    )
                    has_shield = bool(shield_check)

                    # Get tank evolution level
                    tank_evolution = None
                    for class_name in player_classes:
                        if class_name in tank_evolution_levels:
                            level = tank_evolution_levels[class_name]
                            if tank_evolution is None or level > tank_evolution:
                                tank_evolution = level

                    # Apply tank bonuses if applicable
                    if tank_evolution and has_shield:
                        # Health bonus: +4% per evolution
                        health_multiplier = 1 + (0.04 * tank_evolution)
                        total_health *= health_multiplier
                        damage_reflection = 0.03 * tank_evolution
                    elif tank_evolution and not has_shield:
                        # Smaller health bonus without shield
                        health_multiplier = 1 + (0.01 * tank_evolution)
                        total_health *= health_multiplier
                        damage_reflection = 0.0
                    else:
                        damage_reflection = 0.0

                    try:
                        highest_element = None
                        highest_items = await conn.fetch(
                            "SELECT ai.element FROM profile p JOIN allitems ai ON (p.user=ai.owner) JOIN"
                            " inventory i ON (ai.id=i.item) WHERE i.equipped IS TRUE AND p.user=$1"
                            " ORDER BY GREATEST(ai.damage, ai.armor) DESC;",
                            user_id,
                        )

                        if highest_items:
                            highest_element = highest_items[0]["element"].capitalize()
                    except Exception as e:
                        await ctx.send(f"An error occurred while fetching player's element: {e}")
                        highest_element = None

                    # Initialize player stats
                    player_stats = {
                        "user": ctx.author,
                        "hp": total_health,
                        "max_hp": total_health,
                        "armor": deff,
                        "damage": dmg,
                        "luck": Luck,
                        "mage_evolution": author_mage_evolution,
                        "tank_evolution": tank_evolution,
                        "has_shield": has_shield,
                        "damage_reflection": damage_reflection,
                        "lifesteal": lifestealauth,
                        "element": highest_element
                    }

                    # Fetch player's equipped items to determine element
                    highest_element = None
                    try:
                        highest_items = await conn.fetch(
                            "SELECT ai.element FROM profile p JOIN allitems ai ON (p.user=ai.owner) JOIN"
                            " inventory i ON (ai.id=i.item) WHERE i.equipped IS TRUE AND p.user=$1"
                            " ORDER BY GREATEST(ai.damage, ai.armor) DESC;",
                            user_id,
                        )

                        if highest_items:
                            elements = [item["element"].capitalize() for item in highest_items]
                            highest_element = elements[0]  # Choose the highest priority element
                            player_stats["element"] = highest_element
                    except Exception as e:
                        await ctx.send(f"An error occurred while fetching player's element: {e}")

                    # Optional: If players can have multiple elements, handle accordingly here
                else:
                    await ctx.send(_("Your profile could not be found."))
                    return

            # Initialize monster stats
            monster_stats = {
                "name": monster["name"],
                "hp": monster["hp"],
                "max_hp": monster["hp"],
                "armor": monster["defense"],
                "damage": monster["attack"],
                "element": monster["element"]
            }

            # Function to calculate damage modifier based on elements
            def calculate_damage_modifier(attacker_element, defender_element):
                if attacker_element in element_strengths and element_strengths[attacker_element] == defender_element:
                    return Decimal(round(randomm.uniform(0.1, 0.3), 1))  # Increase damage by 10-30%
                elif defender_element in element_strengths and element_strengths[defender_element] == attacker_element:
                    return Decimal(round(randomm.uniform(-0.3, -0.1), 1))  # Decrease damage by 10-30%
                return Decimal('0')

            # Calculate damage modifiers
            damage_modifier_player = Decimal('0')
            if player_stats["element"]:
                damage_modifier_player = calculate_damage_modifier(player_stats["element"], monster_stats["element"])

            # Function to create HP bar
            def create_hp_bar(current_hp, max_hp, length=20):
                ratio = current_hp / max_hp if max_hp > 0 else 0
                ratio = max(0, min(1, ratio))  # Ensure ratio is between 0 and 1
                filled_length = int(length * ratio)
                bar = '█' * filled_length + '░' * (length - filled_length)
                return bar

            # Initialize cheat death flag
            cheated = False

            # Begin the battle
            battle_log = deque(
                [
                    (
                        0,
                        _("You have encountered a Level {level} **{monster}**!").format(
                            level=levelchoice, monster=monster["name"]
                        ),
                    )
                ],
                maxlen=5,
            )

            # Create initial embed
            embed = discord.Embed(
                title=_("Raid Battle PvE"),
                color=self.bot.config.game.primary_colour
            )

            # Initialize player stats in the embed
            current_hp = max(0, round(player_stats["hp"], 2))
            max_hp = max(0, round(player_stats["max_hp"], 2))
            hp_bar = create_hp_bar(current_hp, max_hp)
            element_emoji = element_to_emoji.get(player_stats["element"], "❌") if player_stats["element"] else "❌"
            field_name = f"{player_stats['user'].display_name} {element_emoji}"
            field_value = f"HP: {current_hp}/{max_hp}\n{hp_bar}"
            embed.add_field(name=field_name, value=field_value, inline=False)

            # Initialize monster stats in the embed
            monster_current_hp = max(0, round(monster_stats["hp"], 2))
            monster_max_hp = max(0, round(monster_stats["max_hp"], 2))
            monster_hp_bar = create_hp_bar(monster_current_hp, monster_max_hp)
            monster_element_emoji = element_to_emoji.get(monster_stats["element"], "❌")
            monster_field_name = f"{monster_stats['name']} {monster_element_emoji}"
            monster_field_value = f"HP: {monster_current_hp}/{monster_max_hp}\n{monster_hp_bar}"
            embed.add_field(name=monster_field_name, value=monster_field_value, inline=False)

            # Add initial battle log
            embed.add_field(name=_("Battle Log"), value=battle_log[0][1], inline=False)

            log_message = await ctx.send(embed=embed)
            await asyncio.sleep(4)

            start = datetime.datetime.utcnow()
            player_turn = random.choice([True, False])

            # Main battle loop
            # Main battle loop
            while (
                    player_stats["hp"] > 0
                    and monster_stats["hp"] > 0
                    and datetime.datetime.utcnow() < start + datetime.timedelta(minutes=5)
            ):
                if player_turn:
                    attacker = player_stats
                    defender = monster_stats
                    attacker_type = "player"
                    defender_type = "monster"
                else:
                    attacker = monster_stats
                    defender = player_stats
                    attacker_type = "monster"
                    defender_type = "player"

                trickluck = float(random.randint(1, 100))

                if player_turn:
                    attacker_luck = attacker["luck"]

                else:
                    attacker_luck = 90  # Monsters have a fixed luck of 80

                if trickluck <= attacker_luck:
                    # Attack hits
                    if player_turn:
                        # Player's turn
                        # Check for Fireball ability before normal attack
                        if attacker.get("mage_evolution") is not None:
                            fireball_chance = random.randint(1, 100)
                            if fireball_chance <= 40:
                                # Fireball happens
                                evolution_level = attacker["mage_evolution"]
                                damage_multiplier = evolution_damage_multiplier.get(evolution_level, 1.0)

                                # Convert attacker damage and defender armor to float
                                atk_damage = float(attacker["damage"])
                                def_armor = float(defender["armor"])

                                dmg = (atk_damage + float(random.randint(0, 100)) - def_armor) * float(
                                    damage_multiplier)
                                dmg = max(dmg, 1.0)
                                dmg = round(dmg, 2)

                                # Ensure defender HP is a float, then subtract
                                defender["hp"] = float(defender["hp"]) - dmg
                                defender["hp"] = round(defender["hp"], 2)

                                message = _("You cast Fireball! **{monster}** takes **{dmg} HP** damage.").format(
                                    monster=defender["name"],
                                    dmg=dmg
                                )
                            else:
                                # Normal attack
                                atk_damage = float(attacker["damage"])
                                def_armor = float(defender["armor"])

                                dmg = atk_damage + float(random.randint(0, 100)) - def_armor
                                dmg = max(dmg, 1.0)
                                dmg = round(dmg, 2)

                                # Apply damage modifiers for player attacks
                                if damage_modifier_player != 0:
                                    dmg = dmg * (1 + float(damage_modifier_player))
                                    dmg = round(dmg, 2)

                                defender["hp"] = float(defender["hp"]) - dmg
                                defender["hp"] = round(defender["hp"], 2)

                                message = _("You attack! **{monster}** takes **{dmg} HP** damage.").format(
                                    monster=defender["name"],
                                    dmg=dmg,
                                )
                        else:
                            # Normal attack if no mage evolution
                            atk_damage = float(attacker["damage"])
                            def_armor = float(defender["armor"])

                            dmg = atk_damage + float(random.randint(0, 100)) - def_armor
                            dmg = max(dmg, 1.0)
                            dmg = round(dmg, 2)

                            # Apply damage modifiers for player attacks
                            if damage_modifier_player != 0:
                                dmg = dmg * (1 + float(damage_modifier_player))
                                dmg = round(dmg, 2)

                            defender["hp"] = float(defender["hp"]) - dmg
                            defender["hp"] = round(defender["hp"], 2)

                            message = _("You attack! **{monster}** takes **{dmg} HP** damage.").format(
                                monster=defender["name"],
                                dmg=dmg,
                            )

                        # Handle lifesteal if applicable
                        if attacker.get("lifesteal", 0) > 0:
                            lifesteal_percentage = float(attacker["lifesteal"]) / 100.0
                            heal = lifesteal_percentage * dmg
                            heal = round(heal, 2)

                            # Convert attacker HP to float and add
                            attacker["hp"] = float(attacker["hp"]) + heal
                            # Cap at max_hp
                            if attacker["hp"] > float(attacker["max_hp"]):
                                attacker["hp"] = float(attacker["max_hp"])
                            attacker["hp"] = round(attacker["hp"], 2)

                            message += _(" Lifesteals: **{heal} HP**").format(heal=heal)

                        # Check if defender is defeated
                        if defender["hp"] <= 0:
                            defender["hp"] = 0.0
                            message += _(" **{monster}** is defeated!").format(
                                monster=defender["name"]
                            )
                    else:
                        # Monster's turn
                        atk_damage = float(attacker["damage"])
                        def_armor = float(defender["armor"])

                        raw_damage = atk_damage + float(random.randint(0, 100))
                        dmg = max(raw_damage - def_armor, 1.0)
                        dmg = round(dmg, 2)

                        defender["hp"] = float(defender["hp"]) - dmg
                        defender["hp"] = round(defender["hp"], 2)

                        message = _("{monster} attacks! You take **{dmg} HP** damage.").format(
                            monster=attacker["name"],
                            dmg=dmg,
                        )

                        # Add reflection damage calculation here
                        if defender.get("damage_reflection", 0) > 0:
                            blocked_damage = min(raw_damage, def_armor)
                            reflected_damage = blocked_damage * float(defender["damage_reflection"])
                            reflected_damage = round(reflected_damage, 3)  # 3 decimals for reflection detail
                            if reflected_damage > 0:
                                attacker["hp"] = float(attacker["hp"]) - reflected_damage
                                attacker["hp"] = round(attacker["hp"], 2)
                                attacker["hp"] = max(attacker["hp"], 0.0)

                                message += f"\n{defender['user'].display_name}'s armor reflects **{reflected_damage:.3f} HP** damage back!"

                                # Check if monster died from reflection
                                if attacker["hp"] <= 0:
                                    message += f" {attacker['name']} has been defeated by reflected damage!"

                        # Check if defender is defeated
                        if defender["hp"] <= 0:
                            defender["hp"] = 0.0
                            # Handle Cheating Death for the player being attacked
                            if not cheated:
                                chance = float(author_chance)
                                random_number = random.randint(1, 100)
                                if random_number <= chance:
                                    defender["hp"] = 75.0
                                    cheated = True
                                    message += _(" You cheat death and survive with **75 HP**!")
                                else:
                                    message += _(" You are defeated!")
                            else:
                                message += _(" You are defeated!")
                else:
                    # Attack misses or attacker trips
                    dmg = 10.00  # float
                    attacker["hp"] = float(attacker["hp"])  # Convert from Decimal to float if needed
                    attacker["hp"] -= dmg
                    attacker["hp"] = round(attacker["hp"], 2)
                    attacker["hp"] = max(attacker["hp"], 0.0)

                    if player_turn:
                        message = _("You tripped and took **{dmg} HP** damage. Bad luck!").format(
                            dmg=dmg,
                        )
                    else:
                        message = _("{monster} tripped and took **{dmg} HP** damage.").format(
                            monster=attacker["name"],
                            dmg=dmg,
                        )
                # Append message to battle log
                battle_log.append(
                    (
                        battle_log[-1][0] + 1,
                        message,
                    )
                )


                # Update the embed
                embed = discord.Embed(
                    title=_("Raid Battle PvE"),
                    color=self.bot.config.game.primary_colour
                )

                # Update player stats in the embed
                current_hp = max(0, round(player_stats["hp"], 2))
                max_hp = max(0, round(player_stats["max_hp"], 2))
                hp_bar = create_hp_bar(current_hp, max_hp)
                field_name = f"{player_stats['user'].display_name} {element_to_emoji.get(player_stats['element'], '❌') if player_stats['element'] else '❌'}"
                field_value = f"HP: {current_hp}/{max_hp}\n{hp_bar}"
                embed.add_field(name=field_name, value=field_value, inline=False)

                # Update monster stats in the embed
                monster_current_hp = max(0, round(monster_stats["hp"], 2))
                monster_max_hp = max(0, round(monster_stats["max_hp"], 2))
                monster_hp_bar = create_hp_bar(monster_current_hp, monster_max_hp)
                monster_field_name = f"{monster_stats['name']} {element_to_emoji.get(monster_stats['element'], '❌')}"
                monster_field_value = f"HP: {monster_current_hp}/{monster_max_hp}\n{monster_hp_bar}"
                embed.add_field(name=monster_field_name, value=monster_field_value, inline=False)

                # Update battle log in the embed
                battle_log_text = ''
                for line in battle_log:
                    battle_log_text += f"\n**Action #{line[0]}**\n{line[1]}\n"

                embed.add_field(name=_("Battle Log"), value=battle_log_text, inline=False)

                await log_message.edit(embed=embed)
                await asyncio.sleep(4)

                # Check if battle has ended
                if player_stats["hp"] <= 0 or monster_stats["hp"] <= 0:
                    break  # Battle ends

                # Swap turn for the next round
                player_turn = not player_turn

            # Define the egg drop chance
            egg_drop_chance = 0.05 # 5% chance

            # Determine the outcome
            if player_stats["hp"] > 0 and monster_stats["hp"] <= 0:
                # Player wins




                if levelchoice == 11:

                    xp_gain = random.randint(75000,125000)  # Example: higher XP for legendary monsters
                else:
                    xp_gain = randint(levelchoice * 300, levelchoice * 1000)  # Example: 100 XP per level
                async with self.bot.pool.acquire() as conn:
                    await conn.execute(
                        'UPDATE profile SET "xp" = "xp" + $1 WHERE "user" = $2;',
                        xp_gain,
                        ctx.author.id,
                    )
                await ctx.send(
                    _("You defeated the **{monster}** and gained **{xp} XP**!").format(
                        monster=monster["name"],
                        xp=xp_gain
                    )
                )
                newlevel = rpgtools.xptolevel(player_xp + xp_gain)
                if newlevel != player_level:
                    await self.bot.process_levelup(ctx, newlevel, player_level)

                ranger_egg_bonuses = {
                    "Caretaker": 0.02,  # +2% (total 7%)
                    "Tamer": 0.04,  # +4% (total 9%)
                    "Trainer": 0.06,  # +6% (total 11%)
                    "Bowman": 0.08,  # +8% (total 13%)
                    "Hunter": 0.10,  # +10% (total 15%)
                    "Warden": 0.13,  # +13% (total 18%)
                    "Ranger": 0.15,  # +15% (total 25%)
                }

                # Then modify the egg drop chance check section:
                if levelchoice < 12:
                    base_egg_chance = 0.05  # Base 5% chance
                    final_egg_chance = base_egg_chance

                    # Check if player has a Ranger class
                    async with self.bot.pool.acquire() as conn:
                        profile = await conn.fetchrow('SELECT class FROM profile WHERE "user"=$1;', ctx.author.id)
                        if profile and profile['class']:
                            # Find the highest ranger bonus
                            ranger_bonus = 0
                            for class_name in profile['class']:
                                if class_name in ranger_egg_bonuses:
                                    class_bonus = ranger_egg_bonuses[class_name]
                                    ranger_bonus = max(ranger_bonus, class_bonus)

                            # Apply the bonus
                            final_egg_chance += ranger_bonus

                    # Check for egg drop with modified chance
                    if randomm.random() < final_egg_chance:
                        async with self.bot.pool.acquire() as conn:
                            # Count pets, unhatched eggs, and pending splice requests (each counts as 2)
                            pet_and_egg_count = await conn.fetchval(
                                """
                                SELECT 
                                    (SELECT COUNT(*) FROM monster_pets WHERE user_id = $1) +
                                    (SELECT COUNT(*) FROM monster_eggs WHERE user_id = $1 AND hatched = FALSE) +
                                    (SELECT COUNT(*) FROM splice_requests WHERE user_id = $1 AND status = 'pending')
                                """,
                                ctx.author.id
                            )

                        if pet_and_egg_count >= 10:
                            # Instead of immediately rejecting the egg, allow user to release one.
                            async with self.bot.pool.acquire() as conn:
                                # Combine pets and eggs into one list; include a 'type' field for clarity.
                                pet_and_egg_list = await conn.fetch(
                                    """
                                    SELECT id, 'pet' as type, name AS display_name
                                    FROM monster_pets
                                    WHERE user_id = $1
                                    UNION ALL
                                    SELECT id, 'egg' as type, egg_type AS display_name
                                    FROM monster_eggs
                                    WHERE user_id = $1 AND hatched = FALSE
                                    ORDER BY id;
                                    """,
                                    ctx.author.id
                                )

                            if not pet_and_egg_list:
                                await ctx.send(_("Something went wrong retrieving your pets/eggs."))
                                return

                            # Build a message listing the items with a numbered index.
                            response_message = _(
                                "You already have 10 pets or eggs. Would you like to release one to make room for the new egg?\n")
                            for index, record in enumerate(pet_and_egg_list, start=1):
                                response_message += f"{index}. {record['type'].title()} - {record['display_name']}\n"
                            response_message += _(
                                "Type the ID of the pet/egg you want to release or type `cancel` to skip:")

                            await ctx.send(response_message)

                            def check(m):
                                return m.author == ctx.author and m.channel == ctx.channel

                            try:
                                reply = await self.bot.wait_for("message", check=check, timeout=120.0)
                            except asyncio.TimeoutError:
                                await ctx.send(_("Timed out. No egg awarded."))
                                return

                            if reply.content.lower() == "cancel":
                                await ctx.send(_("No egg awarded."))
                                return

                            try:
                                choice = int(reply.content.strip())
                            except ValueError:
                                await ctx.send(_("Invalid input. No egg awarded."))
                                return

                            if not 1 <= choice <= len(pet_and_egg_list):
                                await ctx.send(_("That number is not in the list. No egg awarded."))
                                return

                            # Identify the record to remove
                            record_to_remove = pet_and_egg_list[choice - 1]

                            # Remove the chosen pet/egg from its table.
                            try:
                                async with self.bot.pool.acquire() as conn:
                                    if record_to_remove["type"] == "pet":
                                        await conn.execute("DELETE FROM monster_pets WHERE id = $1;",
                                                           record_to_remove["id"])
                                    else:
                                        await conn.execute("DELETE FROM monster_eggs WHERE id = $1;",
                                                           record_to_remove["id"])
                                await ctx.send(
                                    _(f"Released {record_to_remove['type']} '{record_to_remove['display_name']}' to make room."))
                            except Exception as e:
                                await ctx.send(_("An error occurred while releasing the pet/egg: ") + str(e))
                                return

                        # Generate a random IV percentage between 50% and 100% (or other logic as needed)
                        iv_percentage = randomm.uniform(10, 1000)
                        if iv_percentage < 20:
                            iv_percentage = randomm.uniform(90, 100)
                        elif iv_percentage < 70:
                            iv_percentage = randomm.uniform(80, 90)
                        elif iv_percentage < 150:
                            iv_percentage = randomm.uniform(70, 80)
                        elif iv_percentage < 350:
                            iv_percentage = randomm.uniform(60, 70)
                        elif iv_percentage < 700:
                            iv_percentage = randomm.uniform(50, 60)
                        else:
                            iv_percentage = randomm.uniform(30, 50)

                        # Calculate total IV points (for instance, 100% IV corresponds to 200 points)
                        total_iv_points = (iv_percentage / 100) * 200

                        def allocate_iv_points(total_points):
                            a = randomm.random()
                            b = randomm.random()
                            c = randomm.random()
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

                        hp = monster["hp"] + hp_iv
                        attack = monster["attack"] + attack_iv
                        defense = monster["defense"] + defense_iv

                        # Set hatch timing for the egg (e.g., 36 hours from now)
                        egg_hatch_time = datetime.datetime.utcnow() + datetime.timedelta(minutes=2160)

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
                                    ctx.author.id,
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
                                _(f"{ctx.author.mention}! You found a **{monster['name']} Egg** with an IV of {iv_percentage:.2f}%! It will hatch in 36 hours.")
                            )


                            monster_name = monster["name"]

                            if iv_percentage > 95:
                                await self.bot.public_log(
                                    f"**{ctx.author}** obtained a {monster_name} egg with {iv_percentage:.2f}% IV!"
                                )
                        except Exception as e:
                            await ctx.send(str(e))
                    success = True
                    self.bot.dispatch("PVE_completion", ctx, success)


                elif monster_stats["hp"] > 0 and player_stats["hp"] <= 0:
                    # Player loses
                    await ctx.send(
                        _("You were defeated by the **{monster}**. Better luck next time!").format(
                            monster=monster["name"]
                        )
                    )
                

            # End of the command
        except Exception as e:
            import traceback
            error_message = f"Error occurred: {e}\n"
            error_message += traceback.format_exc()
            await ctx.send(error_message)
            print(error_message)

    @commands.command(brief="Scout ahead to see what monster you'll face")
    @has_char()
    @user_cooldown(1800)  # 30 minute cooldown between scouting attempts
    async def scout(self, ctx):



        # Define element to emoji mapping
        element_to_emoji = {
            "Light": "🌟",
            "Dark": "🌑",
            "Corrupted": "🌀",
            "Nature": "🌿",
            "Electric": "⚡",
            "Water": "💧",
            "Fire": "🔥",
            "Wind": "💨",
            "Earth": "🌍",
        }

        # Define the monsters per level
        monsters = {
            1: [
                {"name": "Sneevil", "hp": 100, "attack": 95, "defense": 100, "element": "Earth", "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_Sneevil-removebg-preview.png"},
                {"name": "Slime", "hp": 120, "attack": 100, "defense": 105, "element": "Water", "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_slime.png"},
                {"name": "Frogzard", "hp": 120, "attack": 90, "defense": 95, "element": "Nature", "url": "https://static.wikia.nocookie.net/aqwikia/images/d/d6/Frogzard.png"},
                {"name": "Rat", "hp": 90, "attack": 100, "defense": 90, "element": "Dark", "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_Rat-removebg-preview.png"},
                {"name": "Bat", "hp": 150, "attack": 95, "defense": 85, "element": "Wind", "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_Bat-removebg-preview.png"},
                {"name": "Skeleton", "hp": 190, "attack": 105, "defense": 100, "element": "Dark", "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_Skelly-removebg-preview.png"},
                {"name": "Imp", "hp": 180, "attack": 95, "defense": 85, "element": "Fire", "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_zZquzlh-removebg-preview.png"},
                {"name": "Pixie", "hp": 100, "attack": 90, "defense": 80, "element": "Light", "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_pixie-removebg-preview.png"},
                {"name": "Zombie", "hp": 170, "attack": 100, "defense": 95, "element": "Dark", "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_zombie-removebg-preview.png"},
                {"name": "Spiderling", "hp": 220, "attack": 95, "defense": 90, "element": "Nature", "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_spider-removebg-preview.png"},
                {"name": "Spiderling", "hp": 220, "attack": 95, "defense": 90, "element": "Nature", "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_spider-removebg-preview.png"},
                {"name": "Moglin", "hp": 200, "attack": 90, "defense": 85, "element": "Light", "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_Moglin.png"},
                {"name": "Red Ant", "hp": 140, "attack": 105, "defense": 100, "element": "Dark", "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_redant-removebg-preview.png"},
                {"name": "Chickencow", "hp": 300, "attack": 150, "defense": 90, "element": "Nature", "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_ChickenCow-removebg-preview.png"},
                {"name": "Tog", "hp": 380, "attack": 105, "defense": 95, "element": "Earth", "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_Tog-removebg-preview.png"},
                {"name": "Lemurphant", "hp": 340, "attack": 95, "defense": 80, "element": "Nature", "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_Lemurphant-removebg-preview.png"},
                {"name": "Fire Imp", "hp": 200, "attack": 100, "defense": 90, "element": "Fire", "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_zZquzlh-removebg-preview.png"},
                {"name": "Zardman", "hp": 300, "attack": 95, "defense": 100, "element": "Earth", "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_Zardman-removebg-preview.png"},
                {"name": "Wind Elemental", "hp": 165, "attack": 90, "defense": 85, "element": "Wind", "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_WindElemental-removebg-preview.png"},
                {"name": "Dark Wolf", "hp": 200, "attack": 100, "defense": 90, "element": "Dark", "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_DarkWolf-removebg-preview.png"},
                {"name": "Treeant", "hp": 205, "attack": 105, "defense": 95, "element": "Nature", "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_Treeant-removebg-preview.png"},
            ],
            2: [
                {"name": "Cyclops Warlord", "hp": 230, "attack": 160, "defense": 155, "element": "Earth", "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_CR-removebg-preview.png"},
                {"name": "Fishman Soldier", "hp": 200, "attack": 165, "defense": 160, "element": "Water", "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_Fisherman-removebg-preview.png"},
                {"name": "Fire Elemental", "hp": 215, "attack": 150, "defense": 145, "element": "Fire", "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_fire_elemental-removebg-preview.png"},
                {"name": "Vampire Bat", "hp": 200, "attack": 170, "defense": 160, "element": "Dark", "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_viO2oSJ-removebg-preview.png"},
                {"name": "Blood Eagle", "hp": 195, "attack": 165, "defense": 150, "element": "Wind", "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_BloodEagle-removebg-preview.png"},
                {"name": "Earth Elemental", "hp": 190, "attack": 175, "defense": 160, "element": "Earth", "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_Earth_Elemental-removebg-preview.png"},
                {"name": "Fire Mage", "hp": 200, "attack": 160, "defense": 140, "element": "Fire", "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_FireMage-removebg-preview.png"},
                {"name": "Dready Bear", "hp": 230, "attack": 155, "defense": 150, "element": "Dark", "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_dreddy-removebg-preview.png"},
                {"name": "Undead Soldier", "hp": 280, "attack": 160, "defense": 155, "element": "Dark", "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_UndeadSoldier-removebg-preview.png"},
                {"name": "Skeleton Warrior", "hp": 330, "attack": 155, "defense": 150, "element": "Dark", "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_SkeelyWarrior-removebg-preview.png"},
                {"name": "Giant Spider", "hp": 350, "attack": 160, "defense": 145, "element": "Nature", "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_DreadSpider-removebg-preview.png"},
                {"name": "Castle spider", "hp": 310, "attack": 170, "defense": 160, "element": "Nature", "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_Castle-removebg-preview.png"},
                {"name": "ConRot", "hp": 210, "attack": 165, "defense": 155, "element": "Water", "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_ConRot-removebg-preview.png"},
                {"name": "Horc Warrior", "hp": 270, "attack": 175, "defense": 170, "element": "Earth", "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_HorcWarrior-removebg-preview.png"},
                {"name": "Shadow Hound", "hp": 300, "attack": 160, "defense": 150, "element": "Dark", "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_Hound-removebg-preview.png"},
                {"name": "Fire Sprite", "hp": 290, "attack": 165, "defense": 155, "element": "Fire", "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_FireSprite-removebg-preview.png"},
                {"name": "Rock Elemental", "hp": 300, "attack": 160, "defense": 165, "element": "Earth", "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_Earth_Elemental-removebg-preview.png"},
                {"name": "Shadow Serpent", "hp": 335, "attack": 155, "defense": 150, "element": "Dark", "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_ShadowSerpant-removebg-preview.png"},
                {"name": "Dark Elemental", "hp": 340, "attack": 165, "defense": 155, "element": "Dark", "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_DarkEle-Photoroom.png"},
                {"name": "Forest Guardian", "hp": 500, "attack": 250, "defense": 250, "element": "Nature", "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_ForestGuardian-removebg-preview.png"},
            ],
            3: [
                {"name": "Mana Golem", "hp": 200, "attack": 220, "defense": 210, "element": "Corrupted", "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_managolum-removebg-preview.png"},
                {"name": "Karok the Fallen", "hp": 180, "attack": 215, "defense": 205, "element": "Ice", "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_VIMs8un-removebg-preview.png"},
                {"name": "Water Draconian", "hp": 220, "attack": 225, "defense": 200, "element": "Water", "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_waterdrag-removebg-preview.png"},
                {"name": "Shadow Creeper", "hp": 190, "attack": 220, "defense": 205, "element": "Dark", "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_shadowcreep-removebg-preview.png"},
                {"name": "Wind Djinn", "hp": 210, "attack": 225, "defense": 215, "element": "Wind", "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_djinn-removebg-preview.png"},
                {"name": "Autunm Fox", "hp": 205, "attack": 230, "defense": 220, "element": "Earth", "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_Autumn_Fox-removebg-preview.png"},
                {"name": "Dark Draconian", "hp": 195, "attack": 220, "defense": 200, "element": "Dark", "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_darkdom-removebg-preview.png"},
                {"name": "Light Elemental", "hp": 185, "attack": 215, "defense": 210, "element": "Light", "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_LightELemental-removebg-preview.png"},
                {"name": "Undead Giant", "hp": 230, "attack": 220, "defense": 210, "element": "Dark", "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_UndGiant-removebg-preview.png"},
                {"name": "Chaos Spider", "hp": 215, "attack": 215, "defense": 205, "element": "Corrupted", "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_ChaosSpider-removebg-preview.png"},
                {"name": "Seed Spitter", "hp": 225, "attack": 220, "defense": 200, "element": "Nature", "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_SeedSpitter-removebg-preview.png"},
                {"name": "Beach Werewolf", "hp": 240, "attack": 230, "defense": 220, "element": "Water", "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_BeachWerewold-removebg-preview.png"},
                {"name": "Boss Dummy", "hp": 220, "attack": 225, "defense": 210, "element": "Nature", "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_BossDummy-removebg-preview.png"},
                {"name": "Rock", "hp": 235, "attack": 225, "defense": 215, "element": "Earth", "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_Rock-removebg-preview.png"},
                {"name": "Shadow Serpent", "hp": 200, "attack": 220, "defense": 205, "element": "Dark", "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_ShadoeSerpant-removebg-preview.png"},
                {"name": "Flame Elemental", "hp": 210, "attack": 225, "defense": 210, "element": "Fire", "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_FireElemental-removebg-preview.png"},
                {"name": "Bear", "hp": 225, "attack": 215, "defense": 220, "element": "Nature", "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_Remove-bg.ai_1732611726453.png"},
                {"name": "Chair", "hp": 215, "attack": 210, "defense": 215, "element": "Nature", "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_chair-removebg-preview.png"},
                {"name": "Chaos Serpant", "hp": 230, "attack": 220, "defense": 205, "element": "Corrupted", "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_ChaosSerp-removebg-preview.png"},
                {"name": "Gorillaphant", "hp": 240, "attack": 225, "defense": 210, "element": "Nature", "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_gorillaserpant-removebg-preview.png"},
            ],
            4: [
                {"name": "Hydra Head", "hp": 300, "attack": 280, "defense": 270, "element": "Water", "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_hydra.png"},
                {"name": "Blessed Deer", "hp": 280, "attack": 275, "defense": 265, "element": "Light", "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_BlessedDeer-removebg-preview.png"},
                {"name": "Chaos Sphinx", "hp": 320, "attack": 290, "defense": 275, "element": "Corrupted", "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_ChaopsSpinx.png"},
                {"name": "Inferno Dracolion", "hp": 290, "attack": 285, "defense": 270, "element": "Dark", "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_Remove-bg.ai_1732614284328.png"},
                {"name": "Wind Cyclone", "hp": 310, "attack": 290, "defense": 280, "element": "Wind", "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_WindElemental-removebg-preview.png"},
                {"name": "Mr Cuddles", "hp": 305, "attack": 295, "defense": 285, "element": "Nature", "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_mrcuddles-removebg-preview.png"},
                {"name": "Infernal Fiend", "hp": 295, "attack": 285, "defense": 270, "element": "Fire", "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_Remove-bg.ai_1732614284328.png"},
                {"name": "Dark Mukai", "hp": 285, "attack": 275, "defense": 265, "element": "Dark", "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_Remove-bg.ai_1732614826889.png"},
                {"name": "Undead Berserker", "hp": 330, "attack": 285, "defense": 275, "element": "Dark", "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_Remove-bg.ai_1732614863579.png"},
                {"name": "Chaos Warrior", "hp": 315, "attack": 280, "defense": 270, "element": "Corrupted", "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_ChaosWarrior-removebg-preview.png"},
                {"name": "Dire Wolf", "hp": 325, "attack": 285, "defense": 275, "element": "Nature", "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_DireWolf-removebg-preview.png"},
                {"name": "Skye Warrior", "hp": 340, "attack": 295, "defense": 285, "element": "Corrupted", "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_SkyeWarrior-removebg-preview.png"},
                {"name": "Death On Wings", "hp": 320, "attack": 290, "defense": 275, "element": "Dark", "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_DeathonWings-removebg-preview.png"},
                {"name": "Chaorruption", "hp": 335, "attack": 295, "defense": 285, "element": "Corrupted", "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_Chaorruption-removebg-preview.png"},
                {"name": "Shadow Beast", "hp": 300, "attack": 285, "defense": 270, "element": "Dark", "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_ShadowBeast-removebg-preview.png"},
                {"name": "Hootbear", "hp": 310, "attack": 290, "defense": 275, "element": "Nature", "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_HootBear-removebg-preview.png"},
                {"name": "Anxiety", "hp": 325, "attack": 280, "defense": 290, "element": "Dark", "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_anxiety-removebg-preview.png"},
                {"name": "Twilly", "hp": 315, "attack": 275, "defense": 285, "element": "Nature", "url": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_Twilly-removebg-preview.png"},
                {"name": "Black Cat", "hp": 330, "attack": 285, "defense": 270, "element": "Corrupted", "url":"https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_QJsLMnk-removebg-preview.png"},
                {"name": "Forest Guardian", "hp": 340, "attack": 290, "defense": 275, "element": "Nature", "url":"https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_ForestGuardian-removebg-preview.png"},
            ],
            5: [
                {"name": "Chaos Dragon", "hp": 400, "attack": 380, "defense": 370, "element": "Corrupted", "url":"https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_ChaosDragon-removebg-preview.png"},
                {"name": "Wooden Door", "hp": 380, "attack": 375, "defense": 365, "element": "Earth", "url":"https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_WoodenDoor-removebg-preview.png"},
                {"name": "Garvodeus", "hp": 420, "attack": 390, "defense": 375, "element": "Water", "url":"https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_Garvodeus-removebg-preview.png"},
                {"name": "Shadow Lich", "hp": 390, "attack": 385, "defense": 370, "element": "Dark", "url":"https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_ShadowLich-removebg-preview.png"},
                {"name": "Zorbak", "hp": 410, "attack": 390, "defense": 380, "element": "Dark", "url":"https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_Zorbak-removebg-preview.png"},
                {"name": "Dwakel Rocketman", "hp": 405, "attack": 395, "defense": 385, "element": "Electric", "url":"https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_DwarkalRock-removebg-preview.png"},
                {"name": "Kathool", "hp": 395, "attack": 385, "defense": 370, "element": "Water", "url":"https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_Kathool-removebg-preview.png"},
                {"name": "Celestial Hound", "hp": 385, "attack": 375, "defense": 365, "element": "Light", "url":"https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_CelestialHound-removebg-preview.png"},
                {"name": "Undead Raxgore", "hp": 430, "attack": 385, "defense": 375, "element": "Dark", "url":"https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_Raxfore-removebg-preview_1.png"},
                {"name": "Droognax", "hp": 415, "attack": 380, "defense": 370, "element": "Dark", "url":"https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_Droognax-removebg-preview.png"},
                {"name": "Corrupted Boar", "hp": 425, "attack": 385, "defense": 375, "element": "Corrupted", "url":"https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_Corrupted_Bear-removebg-preview.png"},
                {"name": "Fressa", "hp": 440, "attack": 395, "defense": 385, "element": "Water", "url":"https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_Fressa-removebg-preview.png"},
                {"name": "Grimskull", "hp": 420, "attack": 390, "defense": 375, "element": "Dark", "url":"https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_Grimskull-removebg-preview.png"},
                {"name": "Chaotic Chicken", "hp": 435, "attack": 385, "defense": 380, "element": "Corrupted", "url":"https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_ChaoticChicken-removebg-preview.png"},
                {"name": "Baelgar", "hp": 400, "attack": 385, "defense": 370, "element": "Dark", "url":"https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_Baelgar-removebg-preview.png"},
                {"name": "Blood Dragon", "hp": 410, "attack": 390, "defense": 375, "element": "Fire", "url":"https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_BloodDragon-removebg-preview.png"},
                {"name": "Avatar of Desolich", "hp": 425, "attack": 380, "defense": 390, "element": "Fire", "url":"https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_Remove-bg.ai_1732696555786.png"},
                {"name": "Piggy Drake", "hp": 415, "attack": 375, "defense": 385, "element": "Wind", "url":"https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_Remove-bg.ai_1732696596976.png"},
                {"name": "Chaos Alteon", "hp": 430, "attack": 385, "defense": 370, "element": "Corrupted", "url":"https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_Chaos_Alteon-removebg-preview.png"},
                {"name": "Argo", "hp": 440, "attack": 380, "defense": 375, "element": "Dark", "url":"https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_Argo-removebg-preview.png"},
            ],
            6: [
                {"name": "Ultra Cuddles", "hp": 500, "attack": 470, "defense": 460, "element": "Corrupted", "url":"https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_ultracuddles-removebg-preview.png"},
                {"name": "General Pollution", "hp": 480, "attack": 465, "defense": 455, "element": "Earth", "url":"https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_genpol-removebg-preview.png"},
                {"name": "Manslayer Fiend", "hp": 520, "attack": 475, "defense": 460, "element": "Dark", "url":"https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_manlsayer-removebg-preview.png"},
                {"name": "The Hushed", "hp": 490, "attack": 470, "defense": 455, "element": "Light", "url":"https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_hushed-removebg-preview.png"},
                {"name": "The Jailer", "hp": 510, "attack": 475, "defense": 465, "element": "Dark", "url":"https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_jailer-removebg-preview.png"},
                {"name": "Thriller", "hp": 505, "attack": 480, "defense": 470, "element": "Electric", "url":"https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_Thriller-removebg-preview.png"},
                {"name": "Dire Razorclaw", "hp": 495, "attack": 470, "defense": 455, "element": "Fire", "url":"https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_file.png"},
                {"name": "Dollageddon", "hp": 485, "attack": 465, "defense": 455, "element": "Light", "url":"https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_Dollageddon-removebg-preview.png"},
                {"name": "Gold Werewolf", "hp": 530, "attack": 475, "defense": 460, "element": "Dark", "url":"https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_Gold_Werewolf-removebg-preview.png"},
                {"name": "FlameMane", "hp": 515, "attack": 470, "defense": 455, "element": "Fire", "url":"https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_FlameMane-removebg-preview.png"},
                {"name": "Specimen 66", "hp": 525, "attack": 475, "defense": 460, "element": "Dark", "url":"https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_Specimen_66-removebg-preview.png"},
                {"name": "Frank", "hp": 540, "attack": 480, "defense": 470, "element": "Electric", "url":"https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_Frank-removebg-preview.png"},
                {"name": "French Horned ToadDragon", "hp": 520, "attack": 475, "defense": 460, "element": "Water", "url":"https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_file__1_-removebg-preview.png"},
                {"name": "Mog Zard", "hp": 535, "attack": 475, "defense": 465, "element": "Earth", "url":"https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_MogZard-removebg-preview.png"},
                {"name": "Mo-Zard", "hp": 500, "attack": 470, "defense": 455, "element": "Dark", "url":"https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_file__2_-removebg-preview.png"},
                {"name": "Nulgath", "hp": 510, "attack": 475, "defense": 460, "element": "Dark", "url":"https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_Nulgath-removebg-preview.png"},
                {"name": "Proto Champion", "hp": 525, "attack": 465, "defense": 475, "element": "Corrupted", "url":"https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_file_3.png"},
                {"name": "Trash Can", "hp": 515, "attack": 460, "defense": 470, "element": "Light", "url":"https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_TrashCan-removebg-preview.png"},
                {"name": "Turdragon", "hp": 530, "attack": 475, "defense": 460, "element": "Nature", "url":"https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_Turagon-removebg-preview.png"},
                {"name": "Unending Avatar", "hp": 540, "attack": 470, "defense": 455, "element": "Nature", "url":" https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_file_4.png"},
            ],
            7: [
                {"name": "Astral Dragon", "hp": 600, "attack": 570, "defense": 560, "element": "Light", "url":"https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_AstralDragon.png"},
                {"name": "Eise Horror", "hp": 580, "attack": 565, "defense": 555, "element": "Dark", "url":"https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_Elise_Horror-removebg-preview.png"},
                {"name": "Asbane", "hp": 620, "attack": 575, "defense": 560, "element": "Dark", "url":"https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_Adbane.png"},
                {"name": "Apephyryx", "hp": 590, "attack": 570, "defense": 555, "element": "Dark", "url":"https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_Apephryx-removebg-preview.png"},
                {"name": "Enchantress", "hp": 610, "attack": 575, "defense": 565, "element": "Nature", "url":"https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_Enchantress-removebg-preview.png"},
                {"name": "Queen of Monsters", "hp": 605, "attack": 580, "defense": 570, "element": "Dark", "url":"https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_QueenOfMonsters-removebg-preview.png"},
                {"name": "Krykan", "hp": 595, "attack": 570, "defense": 555, "element": "Dark", "url":"https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_Remove_background_project.png"},
                {"name": "Painadin Overlord", "hp": 585, "attack": 565, "defense": 555, "element": "Dark", "url":"https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_Painadin_Overlord-removebg-preview.png"},
                {"name": "EL-Blender", "hp": 630, "attack": 575, "defense": 560, "element": "Dark", "url":"https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_EbilBlender-removebg-preview.png"},
                {"name": "Key of Sholemoh", "hp": 615, "attack": 570, "defense": 555, "element": "Corrupted", "url":"https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_Key_of_Sholemoh-removebg-preview.png"},
                {"name": "Specimen 30", "hp": 625, "attack": 575, "defense": 560, "element": "Dark", "url":"https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_Specimen_30.png"},
                {"name": "Pinky", "hp": 640, "attack": 580, "defense": 570, "element": "Electric", "url":"https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_Pinky-removebg-preview.png"},
                {"name": "Monster Cake", "hp": 620, "attack": 575, "defense": 560, "element": "Nature", "url":"https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_Monster_Cake-removebg-preview.png"},
                {"name": "Angyler Fish", "hp": 635, "attack": 575, "defense": 565, "element": "Water", "url":"https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_Angyler_Fish-removebg-preview.png"},
                {"name": "Big Bad Ancient.. Goose?", "hp": 600, "attack": 570, "defense": 555, "element": "Light", "url":"https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_BigBadAncientGoose-removebg-preview.png"},
                {"name": "Barlot Field", "hp": 610, "attack": 575, "defense": 560, "element": "Dark", "url":"https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_Barlot_Fiend-removebg-preview.png"},
                {"name": "Barghest", "hp": 625, "attack": 565, "defense": 575, "element": "Dark", "url":"https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_Barghest-removebg-preview.png"},
                {"name": "Yuzil", "hp": 615, "attack": 560, "defense": 570, "element": "Dark", "url":"https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_Yuzil.png"},
                {"name": "Azkorath", "hp": 630, "attack": 575, "defense": 560, "element": "Corrupted", "url":"https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_Azkorath-removebg-preview.png"},
                {"name": "Boto", "hp": 640, "attack": 570, "defense": 555, "element": "Water", "url":"https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_Boto.png"},
            ],
            8: [
                {"name": "Meatmongous", "hp": 1200, "attack": 450, "defense": 600, "element": "Dark", "url":"https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_Meatmongous-removebg-preview.png"},
                {"name": "Ebil Meta Dragon", "hp": 810, "attack": 770, "defense": 550, "element": "Dark", "url":"https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_MetaDragon_n_Greg-transformed.png"},
                {"name": "Shadow Nulgath", "hp": 850, "attack": 700, "defense": 700, "element": "Dark", "url":"https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_Shadow_Nulgath.png"},
                {"name": "The First Speaker", "hp": 800, "attack": 600, "defense": 700, "element": "Dark", "url":"https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_FirstSpeakerFix-Photoroom.png"},
            ],
            9: [
                {"name": "Avatar Tynfdarius", "hp": 800, "attack": 780, "defense": 770, "element": "Fire", "url":"https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_Avatar_Tynfdarius-removebg-preview-transformed-Photoroom.png"},
                {"name": "Mech-a-Knight", "hp": 780, "attack": 775, "defense": 790, "element": "Dark", "url":"https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_Mech-a-knight-removebg-preview-transformed.png"},
                {"name": "Astraea's Engineer", "hp": 820, "attack": 790, "defense": 775, "element": "Light", "url":"https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_Engineer-removebg-preview-transformed.png"},
            ],
            10: [
                {"name": "Deimos", "hp": 1200, "attack": 700, "defense": 900, "element": "Dark", "url":"https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_Deimos.png"},
                {"name": "Void Dragon", "hp": 2500, "attack": 570, "defense": 575, "element": "Dark", "url":"https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_6pnyUGr-Photoroom-Photoroom.png"},
                {"name": "End of all things", "hp": 300, "attack": 2500, "defense": 300, "element": "Dark", "url":"https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_Beast-Photoroom-transformed-Photoroom.png"},
            ],
            11: [
                {"name": "Drakath", "hp": 4000, "attack": 1022, "defense": 700, "element": "Corrupted", "url":"https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_Pngtreelightning_source_lightning_effect_purple_3916970.png"},
                {"name": "Astraea", "hp": 3500, "attack": 723, "defense": 857, "element": "Light", "url":"https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_5z90r962trs71_1-Photoroom.png"},
                {"name": "Sepulchure", "hp": 3000, "attack": 1355, "defense": 600, "element": "Dark", "url":"https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_wakai-quketsuki-sepulchuredoomknightdoomblade-Photoroom.png"},
            ]
        }
        try:
            # Check if user is a Ranger class
            async with self.bot.pool.acquire() as conn:
                profile = await conn.fetchrow('SELECT class FROM profile WHERE "user"=$1;', ctx.author.id)
                if not profile or not profile['class']:
                    await ctx.send("You need to be a Ranger to use this ability!")
                    await self.bot.reset_cooldown(ctx)
                    return

                is_ranger = False
                ranger_class = None
                ranger_classes = ["Caretaker", "Tamer", "Trainer", "Bowman", "Hunter", "Warden", "Ranger"]
                for class_name in profile['class']:
                    if class_name in ranger_classes:
                        is_ranger = True
                        ranger_class = class_name
                        break


                if not is_ranger:
                    await ctx.send("You need to be a Ranger to use this ability!")
                    await self.bot.reset_cooldown(ctx)
                    return

                pve_command = self.bot.get_command("pve")
                if pve_command is not None:
                    pve_ttl = await ctx.bot.redis.execute_command(
                        "TTL", f"cd:{ctx.author.id}:{pve_command.qualified_name}"
                    )

                    if pve_ttl != -2:  # If cooldown exists
                        hours, remainder = divmod(pve_ttl, 3600)
                        minutes, seconds = divmod(remainder, 60)
                        time_str = f"{int(hours):02}:{int(minutes):02}:{int(seconds):02}"
                        await ctx.send(f"You must wait **{time_str}** before you can scout for monsters!")
                        await self.bot.reset_cooldown(ctx)  # Reset scout cooldown since we couldn't use it
                        return

                # Define reroll chances based on ranger evolution
                reroll_chances = {
                    "Caretaker": 1,
                    "Tamer": 1,
                    "Trainer": 2,
                    "Bowman": 2,
                    "Hunter": 3,
                    "Warden": 3,
                    "Ranger": 4
                }

                max_rerolls = reroll_chances[ranger_class]
                rerolls_left = max_rerolls

                # Fetch player level for monster selection
                player_xp = ctx.character_data.get("xp", 0)
                player_level = rpgtools.xptolevel(player_xp)


            class ScoutingView(discord.ui.View):
                def __init__(self, ctx, monster_data, rerolls_left, max_rerolls):
                    super().__init__(timeout=30)
                    self.ctx = ctx
                    self.monster = monster_data
                    self.rerolls = rerolls_left
                    self.max_rerolls = max_rerolls
                    self.result = None

                    self.engage_button = discord.ui.Button(
                        label="Engage",
                        style=discord.ButtonStyle.success,
                        custom_id="engage"
                    )
                    self.engage_button.callback = self.engage_callback
                    self.add_item(self.engage_button)

                    self.reroll_button = discord.ui.Button(
                        label="Reroll",
                        style=discord.ButtonStyle.primary,
                        custom_id="reroll"
                    )
                    self.reroll_button.callback = self.reroll_callback
                    self.add_item(self.reroll_button)

                    self.retreat_button = discord.ui.Button(
                        label="Retreat",
                        style=discord.ButtonStyle.danger,
                        custom_id="retreat"
                    )
                    self.retreat_button.callback = self.retreat_callback
                    self.add_item(self.retreat_button)

                    self.update_button_states()

                async def engage_callback(self, interaction: discord.Interaction):
                    try:
                        if interaction.user.id != self.ctx.author.id:
                            await interaction.response.send_message("This isn't your battle!", ephemeral=True)
                            return

                        # First defer the response
                        await interaction.response.defer()
                        # Then set result and stop
                        self.result = "engage"
                        self.stop()

                    except Exception as e:
                        await self.ctx.send(f"Error in engage callback: {str(e)}")

                async def reroll_callback(self, interaction: discord.Interaction):
                    try:
                        if interaction.user.id != self.ctx.author.id:
                            await interaction.response.send_message("This isn't your battle!", ephemeral=True)
                            return

                        if self.rerolls > 0:
                            # First defer the response
                            await interaction.response.defer()
                            # Then update rerolls and set result
                            self.rerolls -= 1
                            self.result = "reroll"
                            self.stop()

                    except Exception as e:
                        await self.ctx.send(f"Error in reroll callback: {str(e)}")

                async def retreat_callback(self, interaction: discord.Interaction):
                    try:
                        if interaction.user.id != self.ctx.author.id:
                            await interaction.response.send_message("This isn't your battle!", ephemeral=True)
                            return

                        # First defer the response
                        await interaction.response.defer()
                        # Then set result and stop
                        self.result = "retreat"
                        self.stop()

                    except Exception as e:
                        await self.ctx.send(f"Error in retreat callback: {str(e)}")



                def update_button_states(self):
                    self.reroll_button.disabled = self.rerolls <= 0

            async def select_monster(level):
                monster = random.choice(monsters[level])
                return monster

            async def show_monster_info(monster_data, rerolls, max_rerolls):
                embed = discord.Embed(
                    title="🔍 Monster Scouting Report",
                    description=f"You spot a Level {levelchoice} **{monster_data['name']}** ahead!",
                    color=discord.Color.blue()
                )

                element_emoji = element_to_emoji.get(monster_data["element"], "❓")
                stats_text = (
                    f"**Element:** {element_emoji} {monster_data['element']}\n"
                    f"**HP:** {monster_data['hp']}\n"
                    f"**Attack:** {monster_data['attack']}\n"
                    f"**Defense:** {monster_data['defense']}"
                )
                embed.add_field(name="Stats", value=stats_text, inline=False)

                embed.add_field(
                    name="Scouting Options",
                    value=f"Rerolls remaining: {rerolls}/{max_rerolls}",
                    inline=False
                )

                return embed


            # Main scouting loop
            while True:
                # Determine monster level
                if player_level <= 4:
                    levelchoice = randomm.randint(1, 2)
                elif player_level <= 8:
                    levelchoice = randomm.randint(1, 3)
                elif player_level <= 12:
                    levelchoice = randomm.randint(1, 4)
                elif player_level <= 15:
                    levelchoice = randomm.randint(1, 5)
                elif player_level <= 20:
                    levelchoice = randomm.randint(1, 6)
                elif player_level <= 25:
                    levelchoice = randomm.randint(1, 7)
                elif player_level <= 30:
                    levelchoice = randomm.randint(1, 8)
                elif player_level <= 35:
                    levelchoice = randomm.randint(1, 9)
                elif player_level <= 40:
                    levelchoice = randomm.randint(1, 10)
                else:  # 40+
                    levelchoice = randomm.randint(1, 10)


                # Select and display monster
                monster_data = await select_monster(levelchoice)

                embed = await show_monster_info(monster_data, rerolls_left, max_rerolls)

                # Create a fresh view each time
                view = ScoutingView(ctx, monster_data, rerolls_left, max_rerolls)
                message = await ctx.send(embed=embed, view=view)

                await view.wait()

                if view.result == "engage":
                    pve_command = self.bot.get_command("pve")
                    if pve_command is not None:
                        pve_ttl = await ctx.bot.redis.execute_command(
                            "TTL", f"cd:{ctx.author.id}:{pve_command.qualified_name}"
                        )

                        if pve_ttl != -2:  # Cooldown exists
                            # Format the remaining time
                            hours, remainder = divmod(pve_ttl, 3600)
                            minutes, seconds = divmod(remainder, 60)
                            time_str = f"{int(hours):02}:{int(minutes):02}:{int(seconds):02}"

                            await message.delete()
                            await ctx.send(f"Ha! Nice try. You must wait {time_str} before engaging in combat again!")
                            break
                    await ctx.bot.redis.execute_command(
                        "SET", f"cd:{ctx.author.id}:pve",
                        "pve",
                        "EX", 60 * 30
                    )

                    await message.delete()
                    ctx.monster_override = monster_data
                    ctx.levelchoice_override = levelchoice
                    await ctx.invoke(self.bot.get_command("pve"))
                    break
                elif view.result == "reroll":
                    rerolls_left = view.rerolls
                    await message.delete()
                    continue
                elif view.result == "retreat":
                    await message.delete()
                    await ctx.send("You decide to retreat and look for another opportunity.")
                    break
                else:
                    await message.delete()
                    await ctx.send("Scouting timed out.")
                    break
        except Exception as e:
            await ctx.send(e)

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

            embed = discord.Embed(title=_("Your Monster Eggs"), color=discord.Color.blue())
            for egg in eggs:
                time_left = egg["hatch_time"] - datetime.datetime.utcnow()
                time_left_str = str(time_left).split('.')[0]  # Remove microseconds

                # Check if egg ID is 6666 and modify stats display accordingly
                hp_display = "???" if egg['id'] == 6666 else egg['hp']
                attack_display = "???" if egg['id'] == 6666 else egg['attack']
                defense_display = "???" if egg['id'] == 6666 else egg['defense']

                embed.add_field(
                    name=egg["egg_type"],
                    value=f"**ID:** {egg['id']}\n**IV:** {egg['IV']}%\n**Element:** {egg['element']}\n**HP:** {hp_display}\n**Attack:** {attack_display}\n**Defense:** {defense_display}\n**Hatches in:** {time_left_str}",
                    inline=False,
                )
            await ctx.send(embed=embed)

    import datetime

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

            if not pets:
                await ctx.send("You don't have any pets to feed.")
                await self.bot.reset_cooldown(ctx)
                return

            # Update hunger and happiness for all pets owned by the user
            await conn.execute(
                """
                UPDATE monster_pets
                SET hunger = 100, happiness = 100
                WHERE user_id = $1;
                """,
                ctx.author.id
            )

            await ctx.send("You fed all your pets, and they look happy!")

    @tasks.loop(hours=12)
    async def decrease_pet_stats(self):
        """Background task to decrease hunger and happiness every 4 hours."""
        if self.softlanding == True:
            async with self.bot.pool.acquire() as conn:
                # Fetch all pets that are not adults (since adults are self-sufficient)
                pets = await conn.fetch(
                    "SELECT * FROM monster_pets WHERE growth_stage != 'adult';"
                )

                for pet in pets:
                    user_id = pet['user_id']
                    pet_id = pet['id']
                    pet_name = pet['name']
                    growth_stage = pet['growth_stage']
                    growth_index = pet['growth_index']

                    # Define how much to decrease based on growth stage
                    # You can adjust these values as needed
                    if growth_stage == 'baby':
                        hunger_decrease = 10  # Example value
                        happiness_decrease = 5
                    elif growth_stage == 'juvenile':
                        hunger_decrease = 8
                        happiness_decrease = 4
                    elif growth_stage == 'young':
                        hunger_decrease = 6
                        happiness_decrease = 3
                    else:
                        hunger_decrease = 0
                        happiness_decrease = 0

                    # Update hunger and happiness
                    await conn.execute(
                        """
                        UPDATE monster_pets
                        SET hunger = GREATEST(hunger - $1, 0),
                            happiness = GREATEST(happiness - $2, 0)
                        WHERE id = $3;
                        """,
                        hunger_decrease,
                        happiness_decrease,
                        pet_id
                    )

                    # Check if hunger or happiness has reached 0
                    updated_pet = await conn.fetchrow(
                        "SELECT hunger, happiness FROM monster_pets WHERE id = $1;",
                        pet_id
                    )

                    if updated_pet['hunger'] == 0:
                        # Pet dies from starvation
                        await self.handle_pet_death(conn, user_id, pet_id, pet_name)
                    elif updated_pet['happiness'] == 0:
                        # Pet runs away due to unhappiness
                        await self.handle_pet_runaway(conn, user_id, pet_id, pet_name)
        else:
            self.softlanding = True

    @decrease_pet_stats.before_loop
    async def before_decrease_pet_stats(self):
        """Wait until the bot is ready before starting the task."""
        await self.bot.wait_until_ready()

    async def handle_pet_death(self, conn, user_id, pet_id, pet_name):
        """Handles pet death due to starvation."""
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

    @has_char()
    @user_cooldown(600)
    @commands.command(brief=_("Battle against a player (active)"))
    @locale_doc
    async def activebattle(
            self, ctx, money: IntGreaterThan(-1) = 0, enemy: discord.Member = None
    ):
        _(
            """`[money]` - A whole number that can be 0 or greater; defaults to 0
            `[enemy]` - A user who has a profile; defaults to anyone

            Fight against another player while betting money.
            To decide players' stats, their items, race and class bonuses are evaluated.

            The money is removed from both players at the start of the battle. Once a winner has been decided, they will receive their money, plus the enemy's money.
            The battle takes place in rounds. Each round, both players have to choose their move using the reactions.
            Players can attack (⚔️), defend (🛡️) or recover HP (❤️).

            The battle ends if one player's HP drops to 0 (winner decided), or a player does not move (forfeit).
            In case of a forfeit, neither of the players will get their money back.

            The battle's winner will receive a PvP win, which shows on their profile.
            (This command has a cooldown of 10 minutes.)"""
        )

        if enemy == ctx.author:
            return await ctx.send(_("You can't battle yourself."))
        if ctx.character_data["money"] < money:
            return await ctx.send(_("You are too poor."))

        await self.bot.pool.execute(
            'UPDATE profile SET "money"="money"-$1 WHERE "user"=$2;',
            money,
            ctx.author.id,
        )

        if not enemy:
            text = _(
                "{author} seeks an active battle! The price is **${money}**."
            ).format(author=ctx.author.mention, money=money)
        else:
            text = _(
                "{author} seeks an active battle with {enemy}! The price is **${money}**."
            ).format(author=ctx.author.mention, enemy=enemy.mention, money=money)

        async def check(user: discord.User) -> bool:
            return await has_money(self.bot, user.id, money)

        future = asyncio.Future()
        view = SingleJoinView(
            future,
            Button(
                style=ButtonStyle.primary,
                label=_("Join the activebattle!"),
                emoji="\U00002694",
            ),
            allowed=enemy,
            prohibited=ctx.author,
            timeout=60,
            check=check,
            check_fail_message=_(
                "You don't have enough money to join the activebattle."
            ),
        )

        await ctx.send(text, view=view)

        try:
            enemy_ = await future
        except asyncio.TimeoutError:
            await self.bot.reset_cooldown(ctx)
            await self.bot.pool.execute(
                'UPDATE profile SET "money"="money"+$1 WHERE "user"=$2;',
                money,
                ctx.author.id,
            )
            return await ctx.send(
                _("Noone wanted to join your activebattle, {author}!").format(
                    author=ctx.author.mention
                )
            )

        players = {
            ctx.author: {
                "hp": 0,
                "damage": 0,
                "defense": 0,
                "lastmove": "",
                "action": None,
            },
            enemy_: {
                "hp": 0,
                "damage": 0,
                "defense": 0,
                "lastmove": "",
                "action": None,
            },
        }

        async with self.bot.pool.acquire() as conn:
            await conn.execute(
                'UPDATE profile SET "money"="money"-$1 WHERE "user"=$2;',
                money,
                enemy_.id,
            )

            for p in players:
                classes = [
                    class_from_string(i)
                    for i in await conn.fetchval(
                        'SELECT class FROM profile WHERE "user"=$1;', p.id
                    )
                ]
                if any(c.in_class_line(Ranger) for c in classes if c):
                    players[p]["hp"] = 120
                else:
                    players[p]["hp"] = 100

                attack, defense = await self.bot.get_damage_armor_for(p, conn=conn)
                players[p]["damage"] = int(attack)
                players[p]["defense"] = int(defense)

        moves = {
            "\U00002694": "attack",
            "\U0001f6e1": "defend",
            "\U00002764": "recover",
        }

        msg = await ctx.send(
            _("Battle {p1} vs {p2}").format(p1=ctx.author.mention, p2=enemy_.mention),
            embed=discord.Embed(
                title=_("Let the battle begin!"),
                color=self.bot.config.game.primary_colour,
            ),
        )

        def is_valid_move(r, u):
            return str(r.emoji) in moves and u in players and r.message.id == msg.id

        for emoji in moves:
            await msg.add_reaction(emoji)

        while players[ctx.author]["hp"] > 0 and players[enemy_]["hp"] > 0:
            await msg.edit(
                embed=discord.Embed(
                    description=_(
                        "{prevaction}\n{player1}: **{hp1}** HP\n{player2}: **{hp2}**"
                        " HP\nReact to play."
                    ).format(
                        prevaction="\n".join([i["lastmove"] for i in players.values()]),
                        player1=ctx.author.mention,
                        player2=enemy_.mention,
                        hp1=players[ctx.author]["hp"],
                        hp2=players[enemy_]["hp"],
                    )
                )
            )
            players[ctx.author]["action"], players[enemy_]["action"] = None, None
            players[ctx.author]["lastmove"], players[enemy_]["lastmove"] = (
                _("{user} does nothing...").format(user=ctx.author.mention),
                _("{user} does nothing...").format(user=enemy_.mention),
            )

            while (not players[ctx.author]["action"]) or (
                    not players[enemy_]["action"]
            ):
                try:
                    r, u = await self.bot.wait_for(
                        "reaction_add", timeout=30, check=is_valid_move
                    )
                    try:
                        await msg.remove_reaction(r.emoji, u)
                    except discord.Forbidden:
                        pass
                except asyncio.TimeoutError:
                    await self.bot.reset_cooldown(ctx)
                    await self.bot.pool.execute(
                        'UPDATE profile SET "money"="money"+$1 WHERE "user"=$2 or "user"=$3;',
                        money,
                        ctx.author.id,
                        enemy_.id,
                    )
                    return await ctx.send(
                        _("Someone refused to move. Activebattle stopped.")
                    )
                if not players[u]["action"]:
                    players[u]["action"] = moves[str(r.emoji)]
                else:
                    playerlist = list(players.keys())
                    await ctx.send(
                        _(
                            "{user}, you already moved! Waiting for {other}'s move..."
                        ).format(
                            user=u.mention,
                            other=playerlist[1 - playerlist.index(u)].mention,
                        )
                    )
            plz = list(players.keys())
            for idx, user in enumerate(plz):
                other = plz[1 - idx]
                if players[user]["action"] == "recover":
                    heal_hp = round(players[user]["damage"] * 0.25) or 1
                    players[user]["hp"] += heal_hp
                    players[user]["lastmove"] = _(
                        "{user} healed themselves for **{hp} HP**."
                    ).format(user=user.mention, hp=heal_hp)
                elif (
                        players[user]["action"] == "attack"
                        and players[other]["action"] != "defend"
                ):
                    eff = random.choice(
                        [
                            players[user]["damage"],
                            int(players[user]["damage"] * 0.5),
                            int(players[user]["damage"] * 0.2),
                            int(players[user]["damage"] * 0.8),
                        ]
                    )
                    players[other]["hp"] -= eff
                    players[user]["lastmove"] = _(
                        "{user} hit {enemy} for **{eff}** damage."
                    ).format(user=user.mention, enemy=other.mention, eff=eff)
                elif (
                        players[user]["action"] == "attack"
                        and players[other]["action"] == "defend"
                ):
                    eff = random.choice(
                        [
                            int(players[user]["damage"]),
                            int(players[user]["damage"] * 0.5),
                            int(players[user]["damage"] * 0.2),
                            int(players[user]["damage"] * 0.8),
                        ]
                    )
                    eff2 = random.choice(
                        [
                            int(players[other]["defense"]),
                            int(players[other]["defense"] * 0.5),
                            int(players[other]["defense"] * 0.2),
                            int(players[other]["defense"] * 0.8),
                        ]
                    )
                    if eff - eff2 > 0:
                        players[other]["hp"] -= eff - eff2
                        players[user]["lastmove"] = _(
                            "{user} hit {enemy} for **{eff}** damage."
                        ).format(user=user.mention, enemy=other.mention, eff=eff - eff2)
                        players[other]["lastmove"] = _(
                            "{enemy} tried to defend, but failed.".format(
                                enemy=other.mention
                            )
                        )

                    else:
                        players[user]["lastmove"] = _(
                            "{user}'s attack on {enemy} failed!"
                        ).format(user=user.mention, enemy=other.mention)
                        players[other]["lastmove"] = _(
                            "{enemy} blocked {user}'s attack.".format(
                                enemy=other.mention, user=user.mention
                            )
                        )
                elif players[user]["action"] == players[other]["action"] == "defend":
                    players[ctx.author]["lastmove"] = _("You both tried to defend.")
                    players[enemy_]["lastmove"] = _("It was not very effective...")

        if players[ctx.author]["hp"] <= 0 and players[enemy_]["hp"] <= 0:
            await self.bot.pool.execute(
                'UPDATE profile SET "money"="money"+$1 WHERE "user"=$2 or "user"=$3;',
                money,
                ctx.author.id,
                enemy_.id,
            )
            return await ctx.send(_("You both died!"))
        if players[ctx.author]["hp"] > players[enemy_]["hp"]:
            winner, looser = ctx.author, enemy_
        else:
            looser, winner = ctx.author, enemy_
        async with self.bot.pool.acquire() as conn:
            await conn.execute(
                'UPDATE profile SET "pvpwins"="pvpwins"+1, "money"="money"+$1 WHERE'
                ' "user"=$2;',
                money * 2,
                winner.id,
            )
            await self.bot.log_transaction(
                ctx,
                from_=looser.id,
                to=winner.id,
                subject="Active Battle Bet",
                data={"Gold": money},
                conn=conn,
            )
        await msg.edit(
            embed=discord.Embed(
                description=_(
                    "{prevaction}\n{player1}: **{hp1}** HP\n{player2}: **{hp2}**"
                    " HP\nReact to play."
                ).format(
                    prevaction="\n".join([i["lastmove"] for i in players.values()]),
                    player1=ctx.author.mention,
                    player2=enemy_.mention,
                    hp1=players[ctx.author]["hp"],
                    hp2=players[enemy_]["hp"],
                )
            )
        )
        await ctx.send(
            _("{winner} won the active battle vs {looser}! Congratulations!").format(
                winner=winner.mention,
                looser=looser.mention,
            )
        )


async def setup(bot):
    await bot.add_cog(Battles(bot))

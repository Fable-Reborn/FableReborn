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
# cogs/achievements.py
import discord
from discord.ext import commands
import asyncio
from utils import misc as rpgtools
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Assuming ShopPaginator is defined and accessible via self.bot.paginator.ShopPaginator
# If ShopPaginator is defined within the same cog or another module, adjust the import accordingly
# from .paginator import ShopPaginator  # Example import if paginator is within the same cog

class Achievements(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # List of achievements
        self.achievement_criteria = {
            "Level": {
                5: "Novice Explorer",
                10: "Seasoned Adventurer",
                20: "Veteran Knight",
                30: "Elite Champion",
                40: "Legendary Hero",
                50: "Mythic Conqueror",
                60: "Immortal Guardian",
                100: "Eternal Sovereign"
            },
            "Loot Exchange - XP": {
                10000: "Apprentice Collector",
                20000: "Skilled Accumulator",
                50000: "Expert Hoarder",
                100000: "Master Accumulator",
                200000: "Grand Hoarder"
            },
            "Loot Exchange - Value": {
                50000: "Wealthy Trader",
                100000: "Prosperous Merchant",
                500000: "Affluent Baron",
                750000: "Opulent Duke",
                1000000: "Magnate of Fortune"
            },
            "Crates": {
                "common": [500, 1000, 2000, 5000, 10000],
                "uncommon": [500, 1000, 2000, 5000, 10000],
                "rare": [500, 1000, 2000, 5000, 10000],
                "magic": [500, 1000, 2000, 5000, 10000],
                "fortune": [5, 10],
                "divine": [1, 5, 10]
            }
        }
        self.achievements = [
            # Level Achievements
            {"name": "Novice Explorer", "description": "Reach level 5.", "category": "Level"},
            {"name": "Seasoned Adventurer", "description": "Reach level 10.", "category": "Level"},
            {"name": "Veteran Knight", "description": "Reach level 20.", "category": "Level"},
            {"name": "Elite Champion", "description": "Reach level 30.", "category": "Level"},
            {"name": "Legendary Hero", "description": "Reach level 40.", "category": "Level"},
            {"name": "Mythic Conqueror", "description": "Reach level 50.", "category": "Level"},
            {"name": "Immortal Guardian", "description": "Reach level 60.", "category": "Level"},
            {"name": "Eternal Sovereign", "description": "Reach level 100.", "category": "Level"},

            # Loot Exchange Achievements - Value
            {"name": "Wealthy Trader", "description": "Exchange loot worth $50,000.", "category": "Loot Exchange - Value"},
            {"name": "Prosperous Merchant", "description": "Exchange loot worth $100,000.", "category": "Loot Exchange - Value"},
            {"name": "Affluent Baron", "description": "Exchange loot worth $500,000.", "category": "Loot Exchange - Value"},
            {"name": "Opulent Duke", "description": "Exchange loot worth $750,000.", "category": "Loot Exchange - Value"},
            {"name": "Magnate of Fortune", "description": "Exchange loot worth $1,000,000.", "category": "Loot Exchange - Value"},

            # Loot Exchange Achievements - XP
            {"name": "Apprentice Collector", "description": "Exchange loot XP of 10,000.", "category": "Loot Exchange - XP"},
            {"name": "Skilled Accumulator", "description": "Exchange loot XP of 20,000.", "category": "Loot Exchange - XP"},
            {"name": "Expert Hoarder", "description": "Exchange loot XP of 50,000.", "category": "Loot Exchange - XP"},
            {"name": "Master Accumulator", "description": "Exchange loot XP of 100,000.", "category": "Loot Exchange - XP"},
            {"name": "Grand Hoarder", "description": "Exchange loot XP of 200,000.", "category": "Loot Exchange - XP"},

            # Battle Achievements
            {"name": "First Strike", "description": "Win 10 battles.", "category": "Battles"},
            {"name": "Warrior's Spirit", "description": "Win 25 battles.", "category": "Battles"},
            {"name": "Battle Master", "description": "Win 100 battles.", "category": "Battles"},
            {"name": "Legendary Slayer", "description": "Win 1,000 battles.", "category": "Battles"},
            {"name": "Epic Vanquisher", "description": "Win 2,500 battles.", "category": "Battles"},
            {"name": "Mythic Champion", "description": "Win 5,000 battles.", "category": "Battles"},
            {"name": "Infinite Conqueror", "description": "Win 10,000 battles.", "category": "Battles"},

            # Battle Tower Achievements
            {"name": "Tower Novice", "description": "Complete the battle tower.", "category": "Battle Tower"},
            {"name": "Tower Adept", "description": "Complete the battle tower 10 times.", "category": "Battle Tower"},
            {"name": "Tower Master", "description": "Complete the battle tower 100 times.", "category": "Battle Tower"},

            # Divine Crate Achievements
            {"name": "Rare Crate: Goblin's Greed", "description": "Accumulate 5 divine crates.", "category": "Divine Crates - Rare"},
            {"name": "Mystery Crate: Goblin's Mystery", "description": "Accumulate 10 divine crates.", "category": "Divine Crates - Mystery"},
            {"name": "Divine Crate: Hero's Legacy", "description": "Open a divine crate and obtain the highest stat weapon.", "category": "Divine Crates - Legendary"},
            {"name": "Fortune Crate: Goblin's Fortune", "description": "Accumulate 5 and 10 fortune crates.", "category": "Divine Crates - Fortune"},
            {"name": "Crate Collector", "description": "Accumulate 50 mystery crates.", "category": "Divine Crates - Misc"},
            {"name": "Crate Connoisseur", "description": "Accumulate 100, 200, and 500 mystery crates.", "category": "Divine Crates - Misc"},
            {"name": "Divine Initiate", "description": "Get your first divine crate.", "category": "Divine Crates - Misc"},
            {"name": "Divine Enthusiast", "description": "Accumulate 5 divine crates.", "category": "Divine Crates - Misc"},
            {"name": "Divine Devotee", "description": "Accumulate 10 divine crates.", "category": "Divine Crates - Misc"},
            {"name": "Divine Fortune Seeker", "description": "Accumulate 5 fortune crates.", "category": "Divine Crates - Fortune"},
            {"name": "Divine Fortune Master", "description": "Accumulate 10 fortune crates.", "category": "Divine Crates - Fortune"},

            # Goblins' Hoard Achievements
            {"name": "Goblins' Hoard - Common", "description": "Accumulate 500, 1,000, 2,000, 5,000, and 10,000 common crates.", "category": "Goblins' Hoard"},
            {"name": "Goblins' Hoard - Uncommon", "description": "Accumulate 500, 1,000, 2,000, 5,000, and 10,000 uncommon crates.", "category": "Goblins' Hoard"},
            {"name": "Goblins' Hoard - Rare", "description": "Accumulate 500, 1,000, 2,000, 5,000, and 10,000 rare crates.", "category": "Goblins' Hoard"},
            {"name": "Goblins' Hoard - Magic", "description": "Accumulate 500, 1,000, 2,000, 5,000, and 10,000 magic crates.", "category": "Goblins' Hoard"},

            # Special Event Achievements
            {"name": "Dragon Survivor", "description": "Survive a dragon raid.", "category": "Special Events"},
            {"name": "Dragon Defender", "description": "Survive dragon raid 10 times.", "category": "Special Events"},
            {"name": "Dragon Conqueror", "description": "Survive dragon raid 100 times.", "category": "Special Events"},
            {"name": "Halloween Hero 2024", "description": "Participate in the Halloween 2024 event.", "category": "Special Events"},

            # Gold Accumulation Achievements
            {"name": "Golden Apprentice", "description": "Accumulate 10,000 gold.", "category": "Gold Accumulation"},
            {"name": "Golden Adept", "description": "Accumulate 50,000 gold.", "category": "Gold Accumulation"},
            {"name": "Golden Expert", "description": "Accumulate 500,000 gold.", "category": "Gold Accumulation"},
            {"name": "Golden Master", "description": "Accumulate 750,000 gold.", "category": "Gold Accumulation"},
            {"name": "Golden Legend", "description": "Accumulate 1,000,000 gold.", "category": "Gold Accumulation"},
            {"name": "Golden Emperor", "description": "Accumulate 10,000,000 gold.", "category": "Gold Accumulation"},
            {"name": "Golden Titan", "description": "Accumulate 50,000,000 gold.", "category": "Gold Accumulation"},
            {"name": "Golden Immortal", "description": "Accumulate 100,000,000 gold.", "category": "Gold Accumulation"},
            {"name": "Golden Overlord", "description": "Accumulate 250,000,000 gold.", "category": "Gold Accumulation"},
        ]

    @commands.command(name="achievement", aliases=["achievements", "achv"])
    async def achievements_command(self, ctx):
        """Displays the list of achievements with categorization and pagination using ShopPaginator."""
        user_id = ctx.author.id

        # Fetch unlocked achievements from the database
        unlocked = await self.get_unlocked_achievements(user_id)

        # Organize achievements by category
        categories = {}
        for ach in self.achievements:
            category = ach["category"]
            if category not in categories:
                categories[category] = []
            categories[category].append(ach)

        # Create a list of category names
        category_names = list(categories.keys())
        total_pages = len(category_names)
        current_page = 0

        # Create embed entries for each category
        entries = []
        for idx, category in enumerate(category_names):
            ach_list = categories[category]
            embed = discord.Embed(
                title=f"🎯 Achievements - {category}",
                description=f"Here are the achievements you can unlock in the **{category}** category!",
                color=discord.Color.blue()
            )
            for ach in ach_list:
                status = "✅" if ach['name'] in unlocked else "🔒"
                embed.add_field(
                    name=f"{status} {ach['name']}",
                    value=ach['description'],
                    inline=False
                )
            embed.set_footer(text=f"Page {idx + 1}/{total_pages}")
            entries.append((embed, category))  # (Embed, identifier)

        if not entries:
            await ctx.send("No achievements available.")
            return

        # Initialize the paginator with the entries
        paginator = self.bot.paginator.AchievmentPaginator(entries=entries)

        try:
            # Paginate the embeds
            await paginator.paginate(ctx)
        except Exception as e:
            logger.error(f"Error during pagination: {e}")
            await ctx.send("An error occurred while displaying achievements. Please try again later.")

    @commands.command(name="unlockach", aliases=["unlockachievements"])
    async def unlock_achievements_command(self, ctx):
        """
        Unlocks achievements based on the user's current XP and crate counts.
        Usage: $unlockach
        """
        try:
            user_id = ctx.author.id

            # Fetch user profile data
            profile = await self.get_user_profile(user_id)
            if not profile:
                await ctx.send("Profile not found. Please ensure you have a profile set up.")
                return

            # Determine user level
            user_xp = profile.get("xp", 0)
            user_level = rpgtools.xptolevel(user_xp)

            # Fetch crate counts
            crates = {
                "common": profile.get("crates_common", 0),
                "uncommon": profile.get("crates_uncommon", 0),
                "rare": profile.get("crates_rare", 0),
                "magic": profile.get("crates_magic", 0),
                "fortune": profile.get("crates_fortune", 0),
                "divine": profile.get("crates_divine", 0)
            }

            # Determine eligible achievements
            eligible_achievements = set()

            # Check level-based achievements
            level_criteria = self.achievement_criteria.get("Level", {})
            for level_threshold, ach_name in level_criteria.items():
                if user_level >= level_threshold:
                    eligible_achievements.add(ach_name)

            # Check Loot Exchange - XP achievements
            xp_criteria = self.achievement_criteria.get("Loot Exchange - XP", {})
            for xp_threshold, ach_name in xp_criteria.items():
                if user_xp >= xp_threshold:
                    eligible_achievements.add(ach_name)

            # Check Loot Exchange - Value achievements
            value_criteria = self.achievement_criteria.get("Loot Exchange - Value", {})
            user_loot_value = profile.get("loot_exchange_value", 0)  # Assuming you have this in profile
            for value_threshold, ach_name in value_criteria.items():
                if user_loot_value >= value_threshold:
                    eligible_achievements.add(ach_name)

            # Check Crate-based achievements
            crate_criteria = self.achievement_criteria.get("Crates", {})
            for crate_type, thresholds in crate_criteria.items():
                user_crate_count = crates.get(crate_type, 0)
                for threshold in thresholds:
                    # Define achievement naming convention based on crate type and threshold
                    if crate_type in ["common", "uncommon", "rare", "magic"]:
                        ach_name = f"{crate_type.capitalize()} Crate Collector {threshold}"
                    elif crate_type in ["fortune", "divine"]:
                        ach_name = f"{crate_type.capitalize()} Crate Collector {threshold}"
                    else:
                        ach_name = f"{crate_type.capitalize()} Crate Collector {threshold}"

                    # Check if user meets the threshold
                    if user_crate_count >= threshold:
                        # Find the corresponding achievement name from the achievements list
                        for ach in self.achievements:
                            if ach["name"] == ach_name:
                                eligible_achievements.add(ach_name)
                                break

            # Fetch already unlocked achievements
            already_unlocked = await self.get_unlocked_achievements(user_id)

            # Determine which achievements to unlock
            new_achievements = eligible_achievements - already_unlocked

            if not new_achievements:
                await ctx.send("You have no new achievements to unlock at this time.")
                return

            # Unlock new achievements
            for ach_name in new_achievements:
                await self.unlock_achievement(user_id, ach_name)

            # Notify the user
            unlocked_list = "\n".join([f"✅ {ach}" for ach in new_achievements])
            await ctx.send(f"🎉 Congratulations! You have unlocked the following achievements:\n{unlocked_list}")
        except Exception as e:
            import traceback
            error_message = f"Error occurred: {e}\n"
            error_message += traceback.format_exc()
            await ctx.send(error_message)
            print(error_message)

    async def get_user_profile(self, user_id):
        """Fetches the user's profile data from the database."""
        query = 'SELECT * FROM profile WHERE "user" = $1'
        try:
            row = await self.bot.pool.fetchrow(query, user_id)
            if row:
                return dict(row)
            return None
        except Exception as e:
            logger.error(f"Error fetching profile for user {user_id}: {e}")
            return None

    async def get_unlocked_achievements(self, user_id):
        """Fetches the set of achievements the user has unlocked from the database."""
        query = "SELECT achievement_name FROM player_achievements WHERE player_id = $1"
        try:
            rows = await self.bot.pool.fetch(query, user_id)
            return {row['achievement_name'] for row in rows}
        except Exception as e:
            logger.error(f"Error fetching achievements for user {user_id}: {e}")
            return set()

    async def unlock_achievement(self, user_id, achievement_name):
        """Unlocks an achievement for a user."""
        query = """
            INSERT INTO player_achievements (player_id, achievement_name)
            VALUES ($1, $2)
            ON CONFLICT DO NOTHING
            """
        try:
            await self.bot.pool.execute(query, user_id, achievement_name)
            logger.info(f"User {user_id} unlocked achievement '{achievement_name}'.")
        except Exception as e:
            logger.error(f"Error unlocking achievement '{achievement_name}' for user {user_id}: {e}")

    async def cog_load(self):
        """Optional: Print a message when the cog is loaded."""
        logger.info("Achievements cog loaded successfully.")

# Setup function for discord.py 2.x
async def setup(bot):
    await bot.add_cog(Achievements(bot))

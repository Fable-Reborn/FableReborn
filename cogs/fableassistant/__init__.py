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
import discord
from discord.ext import commands
import json
import re

from utils.checks import is_gm


class FableAssistant(commands.Cog):
    # Specify the channel ID as a class attribute for easy configuration
    LISTEN_CHANNEL_ID = [1311927627803656192]

    def __init__(self, bot):
        self.bot = bot

        # Load the JSON data once when the cog is initialized
        with open('fable_data.json', 'r') as file:
            self.fable_data = json.load(file)

        # Extract monster data for easier access
        self.monster_data = self.fable_data.get("Monsters", {})

    def search_monsters(self, query):
        """
        Search monsters by name, level, or element without using AI.
        """
        query = query.lower().strip()
        results = []

        # Check for level-based search (with or without space)
        level_search = re.search(r'level\s*(\d+)', query)

        # Check for element-based search
        elements = ["earth", "water", "nature", "dark", "wind", "light", "fire", "electric", "corrupted", "ice"]
        element_search = None
        for element in elements:
            if re.search(r'\b' + element + r'\b', query):
                element_search = element
                break

        # Search logic
        for name, monster in self.monster_data.items():
            name_lower = name.lower()

            # Search by name (full or partial)
            if query in name_lower:
                results.append((name, monster))
                continue

            # Search by level
            if level_search and monster.get("level") == int(level_search.group(1)):
                results.append((name, monster))
                continue

            # Search by element
            if element_search and monster.get("element", "").lower() == element_search:
                results.append((name, monster))

        return results

    async def send_monster_results(self, message, results):
        """
        Send monster search results using Discord embeds.
        """
        if not results:
            await message.channel.send("No monsters found matching your search.")
            return

        # If there are too many results, inform the user
        if len(results) > 5:
            await message.channel.send(f"Found {len(results)} monsters. Showing the first 5:")
            results = results[:5]

        # Create an embed for each monster
        for name, monster in results:
            embed = discord.Embed(
                title=name,
                description=f"Level {monster.get('level', 'Unknown')} {monster.get('element', 'Unknown')} Monster",
                color=0x3498db
            )

            # Add monster stats
            embed.add_field(name="HP", value=monster.get('hp', 'Unknown'), inline=True)
            embed.add_field(name="Attack", value=monster.get('attack', 'Unknown'), inline=True)
            embed.add_field(name="Defense", value=monster.get('defense', 'Unknown'), inline=True)

            # Add image if available
            if monster.get('url'):
                embed.set_thumbnail(url=monster.get('url'))

            await message.channel.send(embed=embed)

        # If we limited the results, let the user know
        if len(results) == 5:
            await message.channel.send("Type a more specific search to see other results.")

    @commands.Cog.listener()
    async def on_message(self, message):
        # Ignore messages sent by bots (including itself)
        if message.author.bot:
            return

        # Check if the message is in the specified channel
        if message.channel.id not in self.LISTEN_CHANNEL_ID:
            return

        user_query = message.content.strip()

        # Ignore empty messages
        if not user_query:
            return

        # Search for monsters based on the query
        monster_results = self.search_monsters(user_query)

        # Send the results as embeds
        await self.send_monster_results(message, monster_results)


# Setup function to add the cog to the bot
async def setup(bot):
    await bot.add_cog(FableAssistant(bot))
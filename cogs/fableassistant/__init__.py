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
from discord import app_commands
import json
import re
import difflib
from typing import List, Dict, Tuple, Optional, Any, Union
import asyncio

from utils.checks import is_gm

UNKNOWN_TIER_LEVEL = 12
UNKNOWN_TIER_DISPLAY_LEVEL = "X"
UNKNOWN_TIER_DISPLAY_NAME = "???"
UNKNOWN_TIER_IMAGE_URL = "https://pub-0e7afc36364b4d5dbd1fd2bea161e4d1.r2.dev/295173706496475136_Unknown_Level12_17022026.png"


class MonsterSelect(discord.ui.Select):
    """A dropdown select menu for monsters."""
    
    def __init__(self, monsters: List[Tuple[str, Dict]], callback_func):
        self.callback_func = callback_func
        
        # Create options from monsters (limit to 25 due to Discord's limitation)
        options = []
        for idx, (name, monster) in enumerate(monsters[:25]):
            is_unknown_tier = monster.get("level") == UNKNOWN_TIER_LEVEL
            display_name = UNKNOWN_TIER_DISPLAY_NAME if is_unknown_tier else name
            display_level = UNKNOWN_TIER_DISPLAY_LEVEL if is_unknown_tier else monster.get("level", "?")
            display_element = "Unknown" if is_unknown_tier else monster.get("element", "?")

            # Create a description with basic monster info
            description = f"Level {display_level} {display_element}"
            
            options.append(discord.SelectOption(
                label=display_name[:100],  # Discord limits label to 100 chars
                description=description[:100],  # Discord limits description to 100 chars
                value=str(idx)
            ))
        
        # Initialize the select with the options
        super().__init__(
            placeholder="Select a monster...",
            min_values=1,
            max_values=1,
            options=options
        )
    
    async def callback(self, interaction: discord.Interaction):
        # Call the provided callback function with the selected monster index
        await self.callback_func(interaction, int(self.values[0]))


class MonsterFilterSelect(discord.ui.Select):
    """A dropdown for filtering monsters by category."""
    
    def __init__(self, options: List[discord.SelectOption], callback_func):
        self.callback_func = callback_func
        
        # Initialize the select with the provided options
        super().__init__(
            placeholder="Filter monsters...",
            min_values=1,
            max_values=1,
            options=options
        )
    
    async def callback(self, interaction: discord.Interaction):
        # Call the provided callback function with the selected filter
        await self.callback_func(interaction, self.values[0])


class MonsterPaginationView(discord.ui.View):
    """View for paginating through monster results."""
    
    def __init__(self, monster_data: Dict[str, Dict], filtered_monsters: List[Tuple[str, Dict]], 
                 page: int = 0, page_size: int = 25, filter_type: str = "all", timeout: float = 180.0):
        super().__init__(timeout=timeout)
        self.monster_data = monster_data
        self.filtered_monsters = filtered_monsters
        self.page = page
        self.page_size = page_size
        self.max_pages = (len(filtered_monsters) - 1) // page_size + 1
        self.filter_type = filter_type
        self.current_monster = None
        
        # Add pagination controls
        self.update_buttons()
        
        # Add monster selection dropdown
        start_idx = self.page * self.page_size
        end_idx = min(start_idx + self.page_size, len(self.filtered_monsters))
        current_page_monsters = self.filtered_monsters[start_idx:end_idx]
        
        if current_page_monsters:
            self.add_item(MonsterSelect(current_page_monsters, self.on_monster_selected))
        
        # Add filter dropdown
        filter_options = [
            discord.SelectOption(label="All Monsters", value="all", default=filter_type == "all"),
            discord.SelectOption(label="Sort: Alphabetical", value="alpha", default=filter_type == "alpha"),
            discord.SelectOption(label="Sort: By Level", value="level", default=filter_type == "level")
        ]
        
        # Add element filter options
        elements = sorted(set(monster.get("element", "").lower() 
                              for _, monster in monster_data.items() 
                              if monster.get("element")))
        
        for element in elements:
            if element:  # Only add non-empty elements
                filter_options.append(
                    discord.SelectOption(
                        label=f"Element: {element.capitalize()}", 
                        value=f"element_{element}",
                        default=filter_type == f"element_{element}"
                    )
                )
                
        self.add_item(MonsterFilterSelect(filter_options, self.on_filter_selected))
    
    def update_buttons(self):
        """Update pagination buttons based on current page."""
        # Clear existing buttons
        for item in list(self.children):
            if isinstance(item, discord.ui.Button):
                self.remove_item(item)
        
        # Add first page button
        first_button = discord.ui.Button(
            label="<<", 
            style=discord.ButtonStyle.primary,
            disabled=(self.page == 0)
        )
        first_button.callback = self.first_page
        self.add_item(first_button)
        
        # Add previous page button
        prev_button = discord.ui.Button(
            label="<", 
            style=discord.ButtonStyle.primary,
            disabled=(self.page == 0)
        )
        prev_button.callback = self.prev_page
        self.add_item(prev_button)
        
        # Add page indicator button (non-functional)
        page_indicator = discord.ui.Button(
            label=f"Page {self.page + 1}/{self.max_pages}",
            style=discord.ButtonStyle.secondary,
            disabled=True
        )
        self.add_item(page_indicator)
        
        # Add next page button
        next_button = discord.ui.Button(
            label=">", 
            style=discord.ButtonStyle.primary,
            disabled=(self.page >= self.max_pages - 1)
        )
        next_button.callback = self.next_page
        self.add_item(next_button)
        
        # Add last page button
        last_button = discord.ui.Button(
            label=">>", 
            style=discord.ButtonStyle.primary,
            disabled=(self.page >= self.max_pages - 1)
        )
        last_button.callback = self.last_page
        self.add_item(last_button)
    
    async def first_page(self, interaction: discord.Interaction):
        """Go to the first page."""
        self.page = 0
        await self.refresh_view(interaction)
    
    async def prev_page(self, interaction: discord.Interaction):
        """Go to the previous page."""
        if self.page > 0:
            self.page -= 1
            await self.refresh_view(interaction)
    
    async def next_page(self, interaction: discord.Interaction):
        """Go to the next page."""
        if self.page < self.max_pages - 1:
            self.page += 1
            await self.refresh_view(interaction)
    
    async def last_page(self, interaction: discord.Interaction):
        """Go to the last page."""
        self.page = self.max_pages - 1
        await self.refresh_view(interaction)
    
    async def refresh_view(self, interaction: discord.Interaction):
        """Refresh the entire view with updated pagination."""
        # Create a new view with the same monsters but updated page
        new_view = MonsterPaginationView(
            self.monster_data,
            self.filtered_monsters,
            self.page,
            self.page_size,
            self.filter_type
        )
        
        # Create or update the embed showing the monster list
        embed = self.create_monster_list_embed()
        
        # Update the message with the new view and embed
        await interaction.response.edit_message(embed=embed, view=new_view)
    
    async def on_monster_selected(self, interaction: discord.Interaction, monster_idx: int):
        """Show details for the selected monster."""
        start_idx = self.page * self.page_size
        selected_monster_idx = start_idx + monster_idx
        
        if 0 <= selected_monster_idx < len(self.filtered_monsters):
            name, monster = self.filtered_monsters[selected_monster_idx]
            self.current_monster = (name, monster)
            
            # Create and send the monster detail embed
            embed = self.create_monster_detail_embed(name, monster)
            await interaction.response.edit_message(embed=embed, view=self)
    
    async def on_filter_selected(self, interaction: discord.Interaction, filter_value: str):
        """Apply the selected filter to the monster list."""
        self.filter_type = filter_value
        
        # Apply the filter to get a new list of monsters
        if filter_value == "all":
            self.filtered_monsters = list(self.monster_data.items())
        elif filter_value == "alpha":
            self.filtered_monsters = sorted(self.monster_data.items(), key=lambda x: x[0])
        elif filter_value == "level":
            self.filtered_monsters = sorted(
                self.monster_data.items(), 
                key=lambda x: (x[1].get('level', 0), x[0])
            )
        elif filter_value.startswith("element_"):
            element = filter_value.split("_")[1]
            self.filtered_monsters = [
                (name, monster) for name, monster in self.monster_data.items()
                if monster.get("element", "").lower() == element
            ]
        
        # Reset to the first page and refresh the view
        self.page = 0
        self.max_pages = (len(self.filtered_monsters) - 1) // self.page_size + 1
        
        # Create a completely new view with the filtered monsters
        new_view = MonsterPaginationView(
            self.monster_data,
            self.filtered_monsters,
            self.page,
            self.page_size,
            self.filter_type
        )
        
        # Create or update the embed showing the monster list
        embed = self.create_monster_list_embed()
        
        # Update the message with the new view and embed
        await interaction.response.edit_message(embed=embed, view=new_view)
    
    def create_monster_list_embed(self) -> discord.Embed:
        """Create an embed showing the current page of monsters."""
        # Choose color based on filter type
        color = 0x3498db  # Default blue
        if self.filter_type.startswith("element_"):
            element = self.filter_type.split("_")[1].lower()
            element_colors = {
                "fire": 0xFF5733,      # Bright red
                "water": 0x3498DB,    # Blue
                "earth": 0x8B4513,    # Brown
                "wind": 0x7FFF00,     # Chartreuse
                "nature": 0x228B22,   # Forest green
                "dark": 0x36454F,     # Charcoal
                "light": 0xFFD700,    # Gold
                "electric": 0xFFFF00, # Yellow
                "corrupted": 0x800080,# Purple
                "ice": 0xADD8E6      # Light blue
            }
            color = element_colors.get(element, 0x3498db)
        
        embed = discord.Embed(
            title=f"📚 Fable Monster Encyclopedia",
            description=f"*Displaying {len(self.filtered_monsters)} monsters*",
            color=color
        )
        
        # Add filter type info with emoji
        filter_display = "🔍 All Monsters"
        if self.filter_type == "alpha":
            filter_display = "🔤 Sorted Alphabetically"
        elif self.filter_type == "level":
            filter_display = "⚔️ Sorted by Level"
        elif self.filter_type.startswith("element_"):
            element = self.filter_type.split("_")[1].capitalize()
            element_emojis = {
                "fire": "🔥",
                "water": "💧",
                "earth": "🪨",
                "wind": "💨",
                "nature": "🌿",
                "dark": "🌑",
                "light": "✨",
                "electric": "⚡",
                "corrupted": "☠️",
                "ice": "❄️"
            }
            emoji = element_emojis.get(element.lower(), "🔍")
            filter_display = f"{emoji} Element: {element}"
            
        embed.add_field(name="Current Filter", value=filter_display, inline=False)
        
        # Show monsters on the current page
        start_idx = self.page * self.page_size
        end_idx = min(start_idx + self.page_size, len(self.filtered_monsters))
        
        if self.filtered_monsters:
            # Create a table-like display of monsters
            monster_list = []
            for idx, (name, monster) in enumerate(self.filtered_monsters[start_idx:end_idx], start=1):
                is_unknown_tier = monster.get("level") == UNKNOWN_TIER_LEVEL
                display_name = UNKNOWN_TIER_DISPLAY_NAME if is_unknown_tier else name
                level = UNKNOWN_TIER_DISPLAY_LEVEL if is_unknown_tier else monster.get("level", "?")
                element = "Unknown" if is_unknown_tier else monster.get("element", "?")
                
                # Get element emoji
                element_emoji = {
                    "fire": "🔥",
                    "water": "💧",
                    "earth": "🪨",
                    "wind": "💨",
                    "nature": "🌿",
                    "dark": "🌑",
                    "light": "✨",
                    "electric": "⚡",
                    "corrupted": "☠️",
                    "ice": "❄️"
                }.get(element.lower() if element else "", "")
                
                # Format entry with level first, then name
                monster_list.append(f"`Lvl {level}` {element_emoji} **{display_name}**")
            
            # Use a single field for better display without gaps
            embed.add_field(
                name="Monsters", 
                value="\n".join(monster_list) or "No monsters found.", 
                inline=False
            )
        else:
            embed.add_field(name="Monsters", value="*No monsters found with the current filter.*", inline=False)
        
        # Add page indicator and tip
        embed.set_footer(text=f"Page {self.page + 1}/{self.max_pages} • Use the dropdown to select a monster • Use buttons to navigate")
        
        # Add thumbnail based on filter if element-specific
        if self.filter_type.startswith("element_"):
            element_icons = {
                "fire": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_fire.png",
                "water": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_water.png",
                "earth": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_earth.png",
                "nature": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_nature.png", 
                "dark": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_dark.png",
                "light": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_light.png",
                "electric": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_Electric.png",
                "corrupted": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_corrupted.png",
                "ice": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_ice.png",
                "wind": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_air.png",
                "air": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_air.png"
            }
            element = self.filter_type.split("_")[1].lower()
            if element in element_icons:
                embed.set_thumbnail(url=element_icons[element])
        #else:
            # Default thumbnail for non-element filters
            #embed.set_thumbnail(url="https://i.imgur.com/Bi8VR9k.png")  # Generic book/monster icon
            
        return embed
    
    def create_monster_detail_embed(self, name: str, monster: Dict[str, Any]) -> discord.Embed:
        """Create an embed showing detailed information about a monster."""
        is_unknown_tier = monster.get("level") == UNKNOWN_TIER_LEVEL

        if is_unknown_tier:
            embed = discord.Embed(
                title=f"❓ {UNKNOWN_TIER_DISPLAY_NAME}",
                description="*Level X ??? Monster*",
                color=0x111111
            )
            embed.add_field(name="💖 HP", value="`???`\n⭐⭐⭐", inline=False)
            embed.add_field(name="⚔️ Attack", value="`???`\n⭐⭐⭐", inline=False)
            embed.add_field(name="🛡️ Defense", value="`???`\n⭐⭐⭐", inline=False)
            embed.set_thumbnail(url=UNKNOWN_TIER_IMAGE_URL)
            embed.set_footer(text="A hidden presence beyond the known tiers.")
            return embed

        # Choose color based on element
        element = monster.get('element', '').lower()
        element_colors = {
            "fire": 0xFF5733,      # Bright red
            "water": 0x3498DB,    # Blue
            "earth": 0x8B4513,    # Brown
            "wind": 0x7FFF00,     # Chartreuse
            "nature": 0x228B22,   # Forest green
            "dark": 0x36454F,     # Charcoal
            "light": 0xFFD700,    # Gold
            "electric": 0xFFFF00, # Yellow
            "corrupted": 0x800080,# Purple
            "ice": 0xADD8E6      # Light blue
        }
        color = element_colors.get(element, 0x3498db)
        
        # Get element emoji
        element_emoji = {
            "fire": "🔥",
            "water": "💧",
            "earth": "🪨",
            "wind": "💨",
            "nature": "🌿",
            "dark": "🌑",
            "light": "✨",
            "electric": "⚡",
            "corrupted": "☠️",
            "ice": "❄️"
        }.get(element, "")
        
        level = monster.get('level', 'Unknown')
        element_display = monster.get('element', 'Unknown')
        
        embed = discord.Embed(
            title=f"{element_emoji} {name}",
            description=f"*Level {level} {element_display} Monster*",
            color=color
        )
        
        # Create a progress bar for stats using universal scale
        hp = monster.get('hp', 0)
        attack = monster.get('attack', 0)
        defense = monster.get('defense', 0)
        
        # Universal scale: 0-1200 as requested
        min_stat = 0
        max_stat = 1200
        
        # Create visual bars with universal scale
        hp_bar = self.create_stat_bar(hp, min_stat, max_stat)
        attack_bar = self.create_stat_bar(attack, min_stat, max_stat)
        defense_bar = self.create_stat_bar(defense, min_stat, max_stat)
        
        # Add monster stats with visual bars and better formatting
        embed.add_field(name="💖 HP", value=f"`{hp:,}`\n{hp_bar}", inline=False)
        embed.add_field(name="⚔️ Attack", value=f"`{attack:,}`\n{attack_bar}", inline=False)
        embed.add_field(name="🛡️ Defense", value=f"`{defense:,}`\n{defense_bar}", inline=False)
        
        # Add divider between main stats and other stats
        embed.add_field(name="\u200b", value="═════════════════", inline=False)
        
        # Add other stats if available in a more organized way
        other_stats = []
        for key, value in monster.items():
            if key not in ['level', 'hp', 'attack', 'defense', 'element', 'url', 'ispublic']:
                other_stats.append(f"**{key.capitalize()}**: {value}")
        
        if other_stats:
            embed.add_field(name="Additional Information", value="\n".join(other_stats), inline=False)
        
        # Get element icon for thumbnail if no URL provided
        if monster.get('url'):
            embed.set_thumbnail(url=monster.get('url'))
        else:
            # Use element icon if available
            element_icons = {
                "fire": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_fire.png",
                "water": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_water.png",
                "earth": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_earth.png",
                "nature": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_nature.png", 
                "dark": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_dark.png",
                "light": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_light.png",
                "electric": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_Electric.png",
                "corrupted": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_corrupted.png",
                "ice": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_ice.png",
                "wind": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_air.png",
                "air": "https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_air.png"
            }
            if element in element_icons:
                embed.set_thumbnail(url=element_icons[element])

        # Footer with navigation tip
        embed.set_footer(text="Use the filter dropdown to return to monster list")
        return embed
        
    def create_stat_bar(self, value: int, min_value: int, max_value: int, segments: int = 8) -> str:
        """Create a visual bar representation of a stat value using universal scale."""
        # Store original value for extreme indicator check
        original_value = value
        
        # Handle values below minimum
        if value < min_value:
            value = min_value
        
        # For display purposes, cap at max_value but remember if it was extreme
        is_extreme = value > 2000  # More than 2000 of stat cap is extreme
        if value > max_value:
            value = max_value
            
        # Calculate normalized value within range (0-1200)
        # Middle ground at 600 as requested
        norm_value = (value - min_value) / (max_value - min_value)
        
        # Calculate filled blocks based on normalized value
        filled_blocks = min(segments, round(norm_value * segments))
        
        # Make sure there's at least one block filled if value exceeds minimum
        if value > min_value and filled_blocks == 0:
            filled_blocks = 1
        
        # Use different block characters for a nice gradient effect
        if norm_value < 0.5:  # Below middle ground (600) - red to yellow
            if norm_value < 0.25:  # Very low - red
                filled = "🟥" * filled_blocks
            else:  # Low-medium - yellow
                filled = "🟨" * filled_blocks
        else:  # Above middle ground - green
            filled = "🟩" * filled_blocks
            
        empty = "⬜" * (segments - filled_blocks)
        
        # For extreme values, add a star at the end of the bar
        if is_extreme:
            return filled + empty + "⭐"
                
        return filled + empty


class FableAssistant(commands.Cog):
    """Cog for the Fable Monster Encyclopedia assistant."""
    
    # Specify the channel ID as a class attribute for easy configuration
    LISTEN_CHANNEL_ID = []
    
    def __init__(self, bot):
        self.bot = bot
        ids_section = getattr(self.bot.config, "ids", None)
        assistant_ids = getattr(ids_section, "fableassistant", {}) if ids_section else {}
        if not isinstance(assistant_ids, dict):
            assistant_ids = {}
        listen_channels = assistant_ids.get("listen_channel_ids", [])
        self.LISTEN_CHANNEL_ID = listen_channels if isinstance(listen_channels, list) else []
        
        # Load monster data from monsters.json
        try:
            with open('monsters.json', 'r') as file:
                self.monsters_json = json.load(file)
                
            # Process monster data into a dictionary with monster name as key
            self.monster_data = {}
            for level, monsters in self.monsters_json.items():
                for monster in monsters:
                    if 'name' in monster and monster.get('ispublic', True):
                        # Add level info to monster data
                        monster_copy = monster.copy()
                        monster_copy['level'] = int(level) if level.isdigit() else level
                        self.monster_data[monster['name']] = monster_copy
            
            # Extract all possible elements for dropdown filtering
            self.elements = sorted(set(monster.get("element", "").lower() 
                                   for monster in self.monster_data.values() 
                                   if monster.get("element")))
        except Exception as e:
            self.bot.logger.error(f"Error loading monster data: {e}")
            self.monster_data = {}
            self.elements = []
    
    @commands.command(name="monsters", aliases=["bestiary", "encyclopedia"])
    async def show_monster_encyclopedia(self, ctx):
        """Display the interactive monster encyclopedia with filtering options."""
        # Get all monsters sorted alphabetically as the default view
        all_monsters = sorted(self.monster_data.items(), key=lambda x: x[0])
        
        # Create the initial view
        view = MonsterPaginationView(self.monster_data, all_monsters)
        
        # Create the initial embed
        embed = view.create_monster_list_embed()
        
        # Send the message with the view
        await ctx.send(embed=embed, view=view)
    
    def fuzzy_search_monsters(self, query: str, threshold: float = 0.6) -> List[Tuple[str, Dict]]:
        """
        Search monsters using fuzzy matching to handle misspellings.
        
        Args:
            query: The search query
            threshold: Similarity threshold (0-1)
            
        Returns:
            List of matching (monster_name, monster_data) tuples
        """
        query = query.lower().strip()
        results = []
        
        # Check for exact matches first
        exact_matches = self.search_monsters_exact(query)
        if exact_matches:
            return exact_matches
        
        # If no exact matches, try fuzzy matching for names
        monster_names = list(self.monster_data.keys())
        matches = difflib.get_close_matches(query, monster_names, n=10, cutoff=threshold)
        
        for match in matches:
            results.append((match, self.monster_data[match]))
        
        # If we found fuzzy name matches, return them
        if results:
            return results
            
        # If still nothing, try to parse if it's a level or element query that might be misspelled
        level_match = re.search(r'l[ve][ve][le]\s*(\d+)', query)  # Handle misspellings like "lvl", "leve"
        if level_match:
            level = int(level_match.group(1))
            return [(name, monster) for name, monster in self.monster_data.items() 
                    if monster.get('level') == level]
        
        # Try fuzzy matching for elements
        for element in self.elements:
            if difflib.SequenceMatcher(None, query, element).ratio() > threshold:
                return [(name, monster) for name, monster in self.monster_data.items() 
                        if monster.get('element', '').lower() == element]
        
        return []
    
    def search_monsters_exact(self, query: str) -> List[Tuple[str, Dict]]:
        """
        Search monsters by exact name, level, or element match.
        
        Args:
            query: The search query
            
        Returns:
            List of matching (monster_name, monster_data) tuples
        """
        query = query.lower().strip()
        results = []
        
        # Check for level-based search (with or without space)
        level_search = re.search(r'level\s*(\d+)', query)
        
        # Check for element-based search
        element_search = None
        for element in self.elements:
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
    
    @commands.Cog.listener()
    async def on_message(self, message):
        """Listen for monster-related queries in the designated channel."""
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
            
        # If the message is a valid command, ignore
        ctx = await self.bot.get_context(message)
        if ctx.valid:
            return
            
        # If it looks like a monster encyclopedia command, suggest using the command
        if user_query.lower() in ["monsters", "bestiary", "encyclopedia"]:
            await message.channel.send("Use `$monsters` to open the interactive Monster Encyclopedia!")
            return
            
        # Search for monsters using fuzzy matching
        monster_results = self.fuzzy_search_monsters(user_query)
        
        if not monster_results:
            await message.channel.send(
                f"No monsters found matching '{user_query}'. Try using `$monsters` to browse the Monster Encyclopedia."
            )
            return
            
        # If only one result, show it directly
        if len(monster_results) == 1:
            name, monster = monster_results[0]
            
            # Create a temporary view to use its create_monster_detail_embed method
            temp_view = MonsterPaginationView(self.monster_data, monster_results)
            embed = temp_view.create_monster_detail_embed(name, monster)
                
            await message.channel.send(embed=embed)
        else:
            # Create a paginated view for multiple results
            view = MonsterPaginationView(self.monster_data, monster_results)
            embed = view.create_monster_list_embed()
            await message.channel.send(
                f"Found {len(monster_results)} monsters matching '{user_query}':", 
                embed=embed, 
                view=view
            )


# Setup function to add the cog to the bot
async def setup(bot):
    await bot.add_cog(FableAssistant(bot))

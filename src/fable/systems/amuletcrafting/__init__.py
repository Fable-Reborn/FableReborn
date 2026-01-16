from discord.ext import commands
import discord
from discord import ui
from fable.utils.checks import has_char
from fable.utils import misc as rpgtools
from fable.utils.i18n import _
import random
from fable.systems.shard_communication import user_on_cooldown as user_cooldown


class AmuletTypeView(ui.View):
    """Interactive view for selecting amulet types and viewing recipes"""
    
    def __init__(self, cog, ctx, player_level, max_tier, resources):
        super().__init__(timeout=60.0)
        self.cog = cog
        self.ctx = ctx
        self.player_level = player_level
        self.max_tier = max_tier
        self.resources = resources
        self.current_type = None
        self.current_page = 0
        self.tiers_per_page = 3
        
    @ui.select(
        placeholder="Choose an amulet type to view recipes...",
        options=[
            discord.SelectOption(label="⚖️ Balanced", value="balanced", description="Balanced HP, Attack, and Defense"),
            discord.SelectOption(label="⚔️ Attack", value="attack", description="High Attack, moderate HP and Defense"),
            discord.SelectOption(label="🛡️ Defense", value="defense", description="High Defense, moderate HP and Attack"),
            discord.SelectOption(label="❤️ Health", value="health", description="High HP, moderate Attack and Defense"),
        ]
    )
    async def select_amulet_type(self, interaction: discord.Interaction, select: ui.Select):
        if interaction.user != self.ctx.author:
            await interaction.response.send_message("Only the command user can interact with this menu!", ephemeral=True)
            return
            
        self.current_type = select.values[0]
        self.current_page = 0  # Reset to first page
        
        # Update the view with pagination buttons
        self.update_pagination_buttons()
        
        embed = self.create_tier_embed()
        await interaction.response.edit_message(embed=embed, view=self)
    
    def create_tier_embed(self):
        """Create the embed for the current type and page"""
        if not self.current_type:
            return None
            
        type_emoji = {
            "balanced": "<:balancedamulet:1388929966397198470>",
            "attack": "<:attackamulet:1388930099516014803>", 
            "defense": "<:defenseamulet:1388930014111727666>",
            "health": "<:healthamulet:1388930139466891265>"
        }
        
        # Get all tiers for this type
        all_tiers = []
        for tier in range(1, 11):  # All 10 tiers
            required_level = self.cog.TIER_LEVELS.get(tier, 999)
            recipe = self.cog.AMULET_RECIPES.get(self.current_type, {}).get(tier, {})
            
            if not recipe:
                continue
                
            stats = self.cog.AMULET_TYPES[self.current_type][tier]
            
            # Check resource availability
            missing_resources = []
            missing_count = 0
            
            for resource, amount_needed in recipe.items():
                player_amount = self.resources.get(resource, 0)
                if player_amount < amount_needed:
                    missing_resources.append(f"{amount_needed - player_amount}x {resource.replace('_', ' ').title()}")
                    missing_count += 1
            
            # Create recipe display
            recipe_items = []
            for resource, amount_needed in recipe.items():
                player_amount = self.resources.get(resource, 0)
                resource_name = resource.replace('_', ' ').title()
                
                if player_amount >= amount_needed:
                    recipe_items.append(f"✅ {amount_needed}x {resource_name}")
                else:
                    recipe_items.append(f"❌ {amount_needed}x {resource_name} *({player_amount} owned)*")
            
            recipe_text = "\n".join(recipe_items)
            
            tier_info = (
                f"**Tier {tier}** (Level {required_level}+)\n"
                f"*HP+{stats['health']}, ATK+{stats['attack']}, DEF+{stats['defense']}*\n"
                f"{recipe_text}"
            )
            
            if self.player_level >= required_level:
                if not missing_resources:
                    tier_info += "\n🟢 **Ready to craft!**"
                elif missing_count <= 2:
                    tier_info += f"\n🟡 **Close!** Missing: {', '.join(missing_resources)}"
                else:
                    tier_info += f"\n🔴 **Need:** {', '.join(missing_resources)}"
            else:
                tier_info += f"\n🔒 **Locked** (Need level {required_level})"
            
            all_tiers.append((tier, tier_info, self.player_level >= required_level))
        
        # Calculate pagination
        total_pages = (len(all_tiers) + self.tiers_per_page - 1) // self.tiers_per_page
        start_idx = self.current_page * self.tiers_per_page
        end_idx = start_idx + self.tiers_per_page
        current_tiers = all_tiers[start_idx:end_idx]
        
        # Create embed
        embed = discord.Embed(
            title=f"{type_emoji[self.current_type]} {self.current_type.title()} Amulet Recipes",
            description=f"**Your Level:** {self.player_level} • **Max Tier:** {self.max_tier}\n**Page {self.current_page + 1} of {total_pages}**",
            color=discord.Color.blue()
        )
        
        # Add tiers for this page
        if current_tiers:
            tier_texts = [tier_info for _, tier_info, _ in current_tiers]
            embed.add_field(
                name=f"Tiers {current_tiers[0][0]}-{current_tiers[-1][0]}",
                value="\n\n".join(tier_texts),
                inline=False
            )
        
        return embed
    
    def update_pagination_buttons(self):
        """Update the state of pagination buttons"""
        if not self.current_type:
            # Hide pagination buttons when no type selected
            self.previous_page.disabled = True
            self.next_page.disabled = True
            return
        
        # Calculate total pages
        total_tiers = 10  # Always 10 tiers
        total_pages = (total_tiers + self.tiers_per_page - 1) // self.tiers_per_page
        
        # Update button states
        self.previous_page.disabled = (self.current_page <= 0)
        self.next_page.disabled = (self.current_page >= total_pages - 1)
    
    @ui.button(label="◀️ Previous", style=discord.ButtonStyle.gray, disabled=True, row=1)
    async def previous_page(self, interaction: discord.Interaction, button: ui.Button):
        if interaction.user != self.ctx.author:
            await interaction.response.send_message("Only the command user can interact with this menu!", ephemeral=True)
            return
        
        if self.current_page > 0:
            self.current_page -= 1
            self.update_pagination_buttons()
            embed = self.create_tier_embed()
            await interaction.response.edit_message(embed=embed, view=self)
        else:
            await interaction.response.defer()
    
    @ui.button(label="Next ▶️", style=discord.ButtonStyle.gray, disabled=True, row=1)
    async def next_page(self, interaction: discord.Interaction, button: ui.Button):
        if interaction.user != self.ctx.author:
            await interaction.response.send_message("Only the command user can interact with this menu!", ephemeral=True)
            return
        
        total_tiers = 10
        total_pages = (total_tiers + self.tiers_per_page - 1) // self.tiers_per_page
        
        if self.current_page < total_pages - 1:
            self.current_page += 1
            self.update_pagination_buttons()
            embed = self.create_tier_embed()
            await interaction.response.edit_message(embed=embed, view=self)
        else:
            await interaction.response.defer()
    
    @ui.button(label="❌ Close", style=discord.ButtonStyle.red, row=1)
    async def close_button(self, interaction: discord.Interaction, button: ui.Button):
        if interaction.user != self.ctx.author:
            await interaction.response.send_message("Only the command user can close this menu!", ephemeral=True)
            return
        
        embed = discord.Embed(
            title="🔨 Amulet Crafting Menu Closed",
            description="Use `$amulet available` to open the menu again!",
            color=discord.Color.red()
        )
        
        await interaction.response.edit_message(embed=embed, view=None)
    
    async def on_timeout(self):
        # Disable all components when view times out
        for item in self.children:
            item.disabled = True
        try:
            await self.message.edit(view=self)
        except:
            pass


class AmuletCrafting(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

        # Final rebalanced amulet stats per tier
        self.AMULET_TYPES = {
            "balanced": {
                1: {"health": 100, "defense": 50, "attack": 50},
                2: {"health": 250, "defense": 150, "attack": 150},
                3: {"health": 500, "defense": 300, "attack": 300},
                4: {"health": 800, "defense": 500, "attack": 500},
                5: {"health": 1200, "defense": 700, "attack": 700},
                6: {"health": 1800, "defense": 900, "attack": 900},
                7: {"health": 2500, "defense": 1100, "attack": 1100},
                8: {"health": 3300, "defense": 1250, "attack": 1250},
                9: {"health": 5000, "defense": 1400, "attack": 1400},
                10: {"health": 7500, "defense": 1500, "attack": 1500}
            },
            "attack": {
                1: {"health": 90, "defense": 45, "attack": 60},
                2: {"health": 225, "defense": 135, "attack": 180},
                3: {"health": 450, "defense": 270, "attack": 360},
                4: {"health": 720, "defense": 450, "attack": 600},
                5: {"health": 1080, "defense": 630, "attack": 840},
                6: {"health": 1620, "defense": 810, "attack": 1080},
                7: {"health": 2250, "defense": 990, "attack": 1320},
                8: {"health": 2970, "defense": 1125, "attack": 1500},
                9: {"health": 4500, "defense": 1260, "attack": 1680},
                10: {"health": 6750, "defense": 1350, "attack": 1800}
            },
            "defense": {
                1: {"health": 90, "defense": 60, "attack": 45},
                2: {"health": 225, "defense": 180, "attack": 135},
                3: {"health": 450, "defense": 360, "attack": 270},
                4: {"health": 720, "defense": 600, "attack": 450},
                5: {"health": 1080, "defense": 840, "attack": 630},
                6: {"health": 1620, "defense": 1080, "attack": 810},
                7: {"health": 2250, "defense": 1320, "attack": 990},
                8: {"health": 2970, "defense": 1500, "attack": 1125},
                9: {"health": 4500, "defense": 1680, "attack": 1260},
                10: {"health": 6750, "defense": 1800, "attack": 1350}
            },
            "health": {
                1: {"health": 120, "defense": 45, "attack": 45},
                2: {"health": 300, "defense": 135, "attack": 135},
                3: {"health": 600, "defense": 270, "attack": 270},
                4: {"health": 960, "defense": 450, "attack": 450},
                5: {"health": 1440, "defense": 630, "attack": 630},
                6: {"health": 2160, "defense": 810, "attack": 810},
                7: {"health": 3000, "defense": 990, "attack": 990},
                8: {"health": 3960, "defense": 1125, "attack": 1125},
                9: {"health": 6000, "defense": 1260, "attack": 1260},
                10: {"health": 9000, "defense": 1350, "attack": 1350}
            }
        }

        # Level requirements per tier
        self.TIER_LEVELS = {
            1: 1,  # Anyone can craft
            2: 10,  # Starting to advance
            3: 20,  # Getting stronger
            4: 30,  # Mid-game
            5: 40,  # Experienced
            6: 50,  # Veteran
            7: 60,  # Master
            8: 70,  # Elite
            9: 80,  # Champion
            10: 90  # Ultimate
        }

        # Diversified resource types
        self.ALL_RESOURCES = {
            # Shared/Universal Resources
            "dragon_scales": "Common material from dragons",
            "mystic_dust": "Basic magical component",
            "refined_ore": "Processed metallic material",
            
            # Attack-focused Resources
            "demon_claws": "Sharp claws from defeated demons",
            "fire_gems": "Blazing gems with offensive power",
            "warrior_essence": "Essence of great warriors",
            "blood_crystals": "Crystals infused with battle fury",
            "storm_shards": "Lightning-charged crystal fragments",
            "berserker_tears": "Rare drops from frenzied warriors",
            "phoenix_feathers": "Feathers from legendary phoenix",
            
            # Defense-focused Resources
            "steel_ingots": "Refined steel for protection",
            "guardian_stones": "Blessed stones of protection",
            "protective_runes": "Ancient defensive inscriptions",
            "mountain_hearts": "Core stones from ancient mountains",
            "titan_shells": "Shells from colossal titans",
            "ward_crystals": "Crystals that repel harm",
            "sentinel_cores": "Power cores from guardian constructs",
            
            # Health-focused Resources
            "life_crystals": "Crystals pulsing with life energy",
            "healing_herbs": "Rare medicinal plants",
            "vitality_essence": "Pure life force essence",
            "phoenix_blood": "Regenerative blood of phoenix",
            "world_tree_sap": "Sap from the World Tree",
            "unicorn_tears": "Healing tears of unicorns",
            "rejuvenation_orbs": "Orbs of eternal youth",
            
            # Balance-focused Resources
            "harmony_stones": "Stones of perfect balance",
            "balance_orbs": "Orbs maintaining equilibrium",
            "equilibrium_dust": "Dust that balances all energies",
            "yin_yang_crystals": "Crystals of opposing forces",
            "neutral_essence": "Essence of perfect neutrality",
            "cosmic_fragments": "Fragments from cosmic balance",
            "void_pearls": "Pearls from the balanced void"
        }

        # Resource rarity tiers with drop chances
        self.RESOURCE_RARITY = {
            # Common (60% total chance) - Basic crafting materials
            "common": {
                "chance": 60,
                "resources": [
                    "dragon_scales", "mystic_dust", "refined_ore", "steel_ingots",
                    "healing_herbs", "life_crystals", "harmony_stones"
                ]
            },
            # Uncommon (25% total chance) - Mid-tier materials
            "uncommon": {
                "chance": 25,
                "resources": [
                    "demon_claws", "fire_gems", "guardian_stones", "protective_runes",
                    "vitality_essence", "balance_orbs", "equilibrium_dust"
                ]
            },
            # Rare (10% total chance) - High-tier materials
            "rare": {
                "chance": 10,
                "resources": [
                    "warrior_essence", "blood_crystals", "mountain_hearts", "titan_shells",
                    "phoenix_blood", "world_tree_sap", "yin_yang_crystals", "neutral_essence"
                ]
            },
            # Epic (4% total chance) - Very rare materials
            "epic": {
                "chance": 4,
                "resources": [
                    "storm_shards", "berserker_tears", "ward_crystals", "sentinel_cores",
                    "unicorn_tears", "rejuvenation_orbs", "cosmic_fragments"
                ]
            },
            # Legendary (1% total chance) - Extremely rare materials
            "legendary": {
                "chance": 1,
                "resources": [
                    "phoenix_feathers", "void_pearls"
                ]
            }
        }

        # Resource categories for targeted random selection
        self.RESOURCE_CATEGORIES = {
            "shared": ["dragon_scales", "mystic_dust", "refined_ore"],
            "attack": ["demon_claws", "fire_gems", "warrior_essence", "blood_crystals", 
                      "storm_shards", "berserker_tears", "phoenix_feathers"],
            "defense": ["steel_ingots", "guardian_stones", "protective_runes", "mountain_hearts", 
                       "titan_shells", "ward_crystals", "sentinel_cores"],
            "health": ["life_crystals", "healing_herbs", "vitality_essence", "phoenix_blood", 
                      "world_tree_sap", "unicorn_tears", "rejuvenation_orbs"],
            "balance": ["harmony_stones", "balance_orbs", "equilibrium_dust", "yin_yang_crystals", 
                       "neutral_essence", "cosmic_fragments", "void_pearls"]
        }

        # Diversified recipes per amulet type and tier
        self.AMULET_RECIPES = {
            "balanced": {
                # Tier 1-2: Mostly common materials
                1: {"dragon_scales": 15, "mystic_dust": 10, "harmony_stones": 8},
                2: {"harmony_stones": 12, "mystic_dust": 15, "balance_orbs": 6},
                
                # Tier 3-4: Common + uncommon materials
                3: {"balance_orbs": 10, "equilibrium_dust": 8, "dragon_scales": 20},
                4: {"equilibrium_dust": 12, "refined_ore": 15, "balance_orbs": 8},
                
                # Tier 5-6: Uncommon + some rare materials
                5: {"equilibrium_dust": 15, "yin_yang_crystals": 3, "harmony_stones": 18},
                6: {"yin_yang_crystals": 5, "neutral_essence": 4, "balance_orbs": 10},
                
                # Tier 7-8: Rare + some epic materials
                7: {"neutral_essence": 6, "cosmic_fragments": 2, "yin_yang_crystals": 8},
                8: {"cosmic_fragments": 3, "neutral_essence": 8, "equilibrium_dust": 25},
                
                # Tier 9-10: Epic + legendary materials
                9: {"cosmic_fragments": 5, "void_pearls": 1, "neutral_essence": 12},
                10: {"void_pearls": 2, "cosmic_fragments": 8, "yin_yang_crystals": 15}
            },
            "attack": {
                # Tier 1-2: Mostly common materials
                1: {"dragon_scales": 12, "demon_claws": 8, "mystic_dust": 10},
                2: {"demon_claws": 12, "fire_gems": 6, "refined_ore": 8},
                
                # Tier 3-4: Common + uncommon materials
                3: {"fire_gems": 10, "demon_claws": 15, "dragon_scales": 18},
                4: {"fire_gems": 12, "refined_ore": 12, "demon_claws": 18},
                
                # Tier 5-6: Uncommon + some rare materials
                5: {"warrior_essence": 4, "fire_gems": 15, "blood_crystals": 3},
                6: {"blood_crystals": 5, "warrior_essence": 6, "demon_claws": 20},
                
                # Tier 7-8: Rare + some epic materials
                7: {"warrior_essence": 8, "storm_shards": 2, "blood_crystals": 6},
                8: {"storm_shards": 3, "berserker_tears": 4, "warrior_essence": 10},
                
                # Tier 9-10: Epic + legendary materials
                9: {"berserker_tears": 6, "storm_shards": 5, "phoenix_feathers": 1},
                10: {"phoenix_feathers": 2, "berserker_tears": 8, "storm_shards": 8}
            },
            "defense": {
                # Tier 1-2: Mostly common materials
                1: {"refined_ore": 15, "steel_ingots": 10, "mystic_dust": 8},
                2: {"steel_ingots": 12, "guardian_stones": 6, "dragon_scales": 10},
                
                # Tier 3-4: Common + uncommon materials
                3: {"guardian_stones": 10, "protective_runes": 8, "refined_ore": 18},
                4: {"protective_runes": 12, "steel_ingots": 15, "guardian_stones": 8},
                
                # Tier 5-6: Uncommon + some rare materials
                5: {"mountain_hearts": 3, "protective_runes": 15, "titan_shells": 4},
                6: {"titan_shells": 6, "mountain_hearts": 5, "guardian_stones": 12},
                
                # Tier 7-8: Rare + some epic materials
                7: {"mountain_hearts": 8, "ward_crystals": 2, "titan_shells": 8},
                8: {"ward_crystals": 3, "sentinel_cores": 4, "mountain_hearts": 10},
                
                # Tier 9-10: Epic + some legendary (void_pearls can be defensive too)
                9: {"sentinel_cores": 6, "ward_crystals": 5, "titan_shells": 12},
                10: {"ward_crystals": 8, "sentinel_cores": 10, "mountain_hearts": 15}
            },
            "health": {
                # Tier 1-2: Mostly common materials
                1: {"mystic_dust": 12, "life_crystals": 10, "healing_herbs": 8},
                2: {"life_crystals": 12, "healing_herbs": 15, "dragon_scales": 8},
                
                # Tier 3-4: Common + uncommon materials
                3: {"healing_herbs": 18, "vitality_essence": 6, "life_crystals": 12},
                4: {"vitality_essence": 10, "healing_herbs": 20, "mystic_dust": 15},
                
                # Tier 5-6: Uncommon + some rare materials
                5: {"phoenix_blood": 3, "vitality_essence": 12, "world_tree_sap": 4},
                6: {"world_tree_sap": 6, "phoenix_blood": 5, "life_crystals": 15},
                
                # Tier 7-8: Rare + some epic materials
                7: {"world_tree_sap": 8, "unicorn_tears": 2, "phoenix_blood": 6},
                8: {"unicorn_tears": 3, "rejuvenation_orbs": 4, "world_tree_sap": 10},
                
                # Tier 9-10: Epic materials (no legendary for health, keeping it balanced)
                9: {"rejuvenation_orbs": 6, "unicorn_tears": 5, "phoenix_blood": 10},
                10: {"unicorn_tears": 8, "rejuvenation_orbs": 10, "world_tree_sap": 15}
            }
        }

    async def give_crafting_resource(self, user_id: int, resource_type: str, amount: int):
        """
        Helper function to give crafting resources to a player.
        Can be called from other cogs.
        
        Args:
            user_id (int): Discord user ID
            resource_type (str): Type of resource to give
            amount (int): Amount of resource to give
            
        Returns:
            bool: True if successful, False otherwise
        """
        if resource_type not in self.ALL_RESOURCES:
            return False
            
        try:
            async with self.bot.pool.acquire() as conn:
                # Check if user already has this resource
                existing = await conn.fetchrow(
                    'SELECT amount FROM crafting_resources WHERE user_id=$1 AND resource_type=$2',
                    user_id, resource_type
                )
                
                if existing:
                    # Update existing resource
                    await conn.execute(
                        'UPDATE crafting_resources SET amount = amount + $1 WHERE user_id=$2 AND resource_type=$3',
                        amount, user_id, resource_type
                    )
                else:
                    # Insert new resource
                    await conn.execute(
                        'INSERT INTO crafting_resources (user_id, resource_type, amount) VALUES ($1, $2, $3)',
                        user_id, resource_type, amount
                    )
                return True
        except Exception as e:
            print(f"Error giving crafting resource: {e}")
            return False

    async def get_player_resources(self, user_id: int):
        """
        Helper function to get all crafting resources for a player.
        
        Args:
            user_id (int): Discord user ID
            
        Returns:
            dict: Dictionary of resource_type -> amount (only resources with amount > 0)
        """
        try:
            async with self.bot.pool.acquire() as conn:
                resources = await conn.fetch(
                    'SELECT resource_type, amount FROM crafting_resources WHERE user_id=$1 AND amount > 0',
                    user_id
                )
                return {r['resource_type']: r['amount'] for r in resources}
        except Exception:
            return {}

    def get_random_resource(self, category: str = None, user_level: int = None):
        """
        Get a random crafting resource based on rarity tiers and player level.
        
        Args:
            category (str, optional): Resource category to limit selection to 
                                    ('shared', 'attack', 'defense', 'health', 'balance')
                                    If None, selects from all resources
            user_level (int, optional): Player level to restrict available resources
            
        Returns:
            str: Random resource name, or None if category is invalid
        """
        # Determine resource pool based on level if provided
        if user_level is not None:
            available_resources = self.get_available_resources_for_level(user_level, category)
        else:
            # Original behavior for backward compatibility
            if category:
                if category not in self.RESOURCE_CATEGORIES:
                    return None
                available_resources = self.RESOURCE_CATEGORIES[category]
            else:
                available_resources = list(self.ALL_RESOURCES.keys())
        
        if not available_resources:
            return None
        
        # Generate random number for rarity roll
        roll = random.randint(1, 100)
        
        # Determine rarity tier based on roll
        cumulative_chance = 0
        selected_rarity = None
        
        for rarity, data in self.RESOURCE_RARITY.items():
            cumulative_chance += data["chance"]
            if roll <= cumulative_chance:
                selected_rarity = rarity
                break
        
        if not selected_rarity:
            selected_rarity = "common"  # Fallback
        
        # Filter available resources by rarity and category/level
        rarity_resources = self.RESOURCE_RARITY[selected_rarity]["resources"]
        valid_resources = [r for r in rarity_resources if r in available_resources]
        
        # If no valid resources in this rarity for the category/level, fall back to any valid resource
        if not valid_resources:
            valid_resources = available_resources
        
        return random.choice(valid_resources)

    def get_random_resources(self, count: int, category: str = None, allow_duplicates: bool = True, user_level: int = None):
        """
        Get multiple random crafting resources.
        
        Args:
            count (int): Number of resources to generate
            category (str, optional): Resource category to limit selection
            allow_duplicates (bool): Whether to allow duplicate resources
            user_level (int, optional): Player level to restrict available resources
            
        Returns:
            list: List of random resource names
        """
        resources = []
        used_resources = set() if not allow_duplicates else None
        
        for _ in range(count):
            attempts = 0
            while attempts < 50:  # Prevent infinite loops
                resource = self.get_random_resource(category, user_level)
                if resource and (allow_duplicates or resource not in used_resources):
                    resources.append(resource)
                    if not allow_duplicates:
                        used_resources.add(resource)
                    break
                attempts += 1
            
            if attempts >= 50:
                break  # Couldn't find unique resource
        
        return resources

    async def give_random_resource(self, user_id: int, amount_range: tuple = (1, 5), category: str = None, respect_level: bool = True):
        """
        Give a random crafting resource to a player.
        
        Args:
            user_id (int): Discord user ID
            amount_range (tuple): Min and max amount to give (min, max)
            category (str, optional): Resource category to limit selection
            respect_level (bool): Whether to respect player level restrictions
            
        Returns:
            tuple: (resource_name, amount_given) if successful, (None, 0) if failed
        """
        user_level = None
        if respect_level:
            user_level = await self.get_player_level(user_id)
        
        resource = self.get_random_resource(category, user_level)
        if not resource:
            return None, 0
        
        amount = random.randint(amount_range[0], amount_range[1])
        success = await self.give_crafting_resource(user_id, resource, amount)
        
        if success:
            return resource, amount
        return None, 0

    def get_resource_rarity(self, resource_name: str):
        """
        Get the rarity tier of a specific resource.
        
        Args:
            resource_name (str): Name of the resource
            
        Returns:
            str: Rarity tier name, or None if resource not found
        """
        for rarity, data in self.RESOURCE_RARITY.items():
            if resource_name in data["resources"]:
                return rarity
        return None

    def get_resource_category(self, resource_name: str):
        """
        Get the category of a specific resource.
        
        Args:
            resource_name (str): Name of the resource
            
        Returns:
            str: Category name, or None if resource not found
        """
        for category, resources in self.RESOURCE_CATEGORIES.items():
            if resource_name in resources:
                return category
        return None

    @commands.group(invoke_without_command=True)
    @has_char()
    async def amulet(self, ctx):
        """Base command for amulet system"""
        await ctx.send("Available commands: `available`, `craft`, `equip`, `unequip`, `recipe`, `resources`, `help`, `sell`")

    @amulet.command(name="available")
    @has_char()
    async def view_available(self, ctx):
        """View amulets you can currently craft based on your level and resources"""
        async with self.bot.pool.acquire() as conn:
            player = await conn.fetchrow('SELECT xp FROM profile WHERE "user"=$1;', ctx.author.id)
            if not player:
                return await ctx.send("You need a character to view available amulets!")

            player_level = rpgtools.xptolevel(player['xp'])
            max_tier = self.get_max_tier_for_level(player_level)
            resources = await self.get_player_resources(ctx.author.id)

            # Create summary embed
            embed = discord.Embed(
                title=f"🔨 {ctx.author.display_name}'s Amulet Crafting",
                description=f"**Level:** {player_level} • **Max Tier:** {max_tier}",
                color=discord.Color.green()
            )

            # Quick summary of craftable amulets
            ready_count = 0
            close_count = 0
            
            for amulet_type in ["balanced", "attack", "defense", "health"]:
                for tier in range(1, max_tier + 1):
                    recipe = self.AMULET_RECIPES.get(amulet_type, {}).get(tier, {})
                    if not recipe:
                        continue

                    missing_count = 0
                    for resource, amount_needed in recipe.items():
                        player_amount = resources.get(resource, 0)
                        if player_amount < amount_needed:
                            missing_count += 1

                    if missing_count == 0:
                        ready_count += 1
                    elif missing_count <= 2:
                        close_count += 1

            # Add summary
            summary_lines = []
            if ready_count > 0:
                summary_lines.append(f"🟢 **{ready_count}** ready to craft")
            if close_count > 0:
                summary_lines.append(f"🟡 **{close_count}** almost ready")
            if not summary_lines:
                summary_lines.append("🔴 No amulets ready to craft")
                
            embed.add_field(
                name="📊 Quick Summary", 
                value="\n".join(summary_lines), 
                inline=False
            )
            
            embed.add_field(
                name="📋 How to Use",
                value="Select an amulet type from the dropdown below to view detailed recipes and requirements!",
                inline=False
            )

            # Create the interactive view
            view = AmuletTypeView(self, ctx, player_level, max_tier, resources)
            
            # Send message with dropdown
            message = await ctx.send(embed=embed, view=view)
            view.message = message  # Store message reference for timeout handling

    @amulet.command(name="resources")
    @has_char()
    async def view_resources(self, ctx):
        """View your crafting resources"""
        resources = await self.get_player_resources(ctx.author.id)
        
        if not resources:
            return await ctx.send("You don't have any crafting resources yet!")
        
        # Group resources by type
        shared_resources = {}
        attack_resources = {}
        defense_resources = {}
        health_resources = {}
        balance_resources = {}
        
        # Rarity emojis
        rarity_emojis = {
            "common": "⚪",
            "uncommon": "🟢", 
            "rare": "🔵",
            "epic": "🟣",
            "legendary": "🟡"
        }
        
        shared_keywords = ["dragon_scales", "mystic_dust", "refined_ore"]
        attack_keywords = ["demon_claws", "fire_gems", "warrior_essence", "blood_crystals", "storm_shards", "berserker_tears", "phoenix_feathers"]
        defense_keywords = ["steel_ingots", "guardian_stones", "protective_runes", "mountain_hearts", "titan_shells", "ward_crystals", "sentinel_cores"]
        health_keywords = ["life_crystals", "healing_herbs", "vitality_essence", "phoenix_blood", "world_tree_sap", "unicorn_tears", "rejuvenation_orbs"]
        balance_keywords = ["harmony_stones", "balance_orbs", "equilibrium_dust", "yin_yang_crystals", "neutral_essence", "cosmic_fragments", "void_pearls"]
        
        for resource, amount in resources.items():
            display_name = resource.replace('_', ' ').title()
            rarity = self.get_resource_rarity(resource)
            rarity_emoji = rarity_emojis.get(rarity, "❓")
            formatted_name = f"{rarity_emoji} {display_name}: {amount}"
            
            if resource in shared_keywords:
                shared_resources[display_name] = formatted_name
            elif resource in attack_keywords:
                attack_resources[display_name] = formatted_name
            elif resource in defense_keywords:
                defense_resources[display_name] = formatted_name
            elif resource in health_keywords:
                health_resources[display_name] = formatted_name
            elif resource in balance_keywords:
                balance_resources[display_name] = formatted_name
        
        embed = discord.Embed(title=f"{ctx.author.display_name}'s Crafting Resources", color=discord.Color.blue())
        embed.add_field(name="Rarity Legend", value="⚪ Common • 🟢 Uncommon • 🔵 Rare • 🟣 Epic • 🟡 Legendary", inline=False)
        
        if shared_resources:
            shared_text = "\n".join(shared_resources.values())
            embed.add_field(name="🔧 Shared Resources", value=shared_text, inline=False)
        
        if attack_resources:
            attack_text = "\n".join(attack_resources.values())
            embed.add_field(name="⚔️ Attack Resources", value=attack_text, inline=False)
        
        if defense_resources:
            defense_text = "\n".join(defense_resources.values())
            embed.add_field(name="🛡️ Defense Resources", value=defense_text, inline=False)
        
        if health_resources:
            health_text = "\n".join(health_resources.values())
            embed.add_field(name="❤️ Health Resources", value=health_text, inline=False)
        
        if balance_resources:
            balance_text = "\n".join(balance_resources.values())
            embed.add_field(name="⚖️ Balance Resources", value=balance_text, inline=False)
        
        await ctx.send(embed=embed)

    @amulet.command(name="craft")
    @has_char()
    async def craft_amulet(self, ctx, type_: str, tier: int):
        """Craft an amulet of a specified type (balanced, attack, defense, health) and tier."""
        try:
            type_ = type_.lower()
            if type_ not in self.AMULET_TYPES:
                valid_types = ', '.join(self.AMULET_TYPES.keys())
                return await ctx.send(f"Invalid amulet type! Choose from: `{valid_types}`")

            if tier not in range(1, 11):
                return await ctx.send("Invalid tier! Please choose a tier from 1 to 10.")

            async with self.bot.pool.acquire() as conn:
                player = await conn.fetchrow('SELECT xp FROM profile WHERE "user"=$1;', ctx.author.id)
                if not player:
                    return await ctx.send("You need a character to craft amulets!")

                player_level = rpgtools.xptolevel(player['xp'])
                required_level = self.TIER_LEVELS.get(tier, 999)
                if player_level < required_level:
                    return await ctx.send(f"You must be at least level {required_level} to craft a Tier {tier} amulet.")

                recipe = self.AMULET_RECIPES.get(type_, {}).get(tier, {})
                if not recipe:
                    return await ctx.send(f"Crafting recipe for Tier {tier} {type_.title()} amulet not found.")

                inventory = await self.get_player_resources(ctx.author.id)
                
                missing_resources = []
                for resource, amount_needed in recipe.items():
                    if inventory.get(resource, 0) < amount_needed:
                        missing_resources.append(f"{amount_needed}x {resource.replace('_', ' ').title()}")
                
                if missing_resources:
                    embed = discord.Embed(
                        title="❌ Missing Resources",
                        description="You need the following resources to craft this amulet:",
                        color=discord.Color.red()
                    )
                    embed.add_field(name="Required:", value="\n".join(missing_resources), inline=False)
                    return await ctx.send(embed=embed)

                # Double-check validation: Lock and verify resources again to prevent exploitation
                # This prevents race conditions where users might sell/trade simultaneously
                async with conn.transaction():
                    for resource, amount_needed in recipe.items():
                        current_amount = await conn.fetchval(
                            'SELECT amount FROM crafting_resources WHERE user_id=$1 AND resource_type=$2 FOR UPDATE',
                            ctx.author.id, resource
                        )
                        if not current_amount or current_amount < amount_needed:
                            return await ctx.send(
                                f"❌ **Crafting Failed**: You no longer have enough {resource.replace('_', ' ').title()}.\n"
                                f"You have: {current_amount or 0}, need: {amount_needed}"
                            )
                    
                    # Consume resources
                    for resource, amount_needed in recipe.items():
                        await conn.execute(
                            'UPDATE crafting_resources SET amount = amount - $1 WHERE user_id=$2 AND resource_type=$3',
                            amount_needed, ctx.author.id, resource
                        )

                stats = self.AMULET_TYPES[type_][tier]
                health = stats['health']
                attack = stats['attack']
                defense = stats['defense']

                await conn.execute(
                    """INSERT INTO amulets (user_id, type, tier, hp, attack, defense)
                    VALUES ($1, $2, $3, $4, $5, $6);""",
                    ctx.author.id, type_, tier, health, attack, defense
                )

                emoji_map = {
                    "balanced": "<:balancedamulet:1388929966397198470>",
                    "attack": "<:attackamulet:1388930099516014803>",
                    "defense": "<:defenseamulet:1388930014111727666>",
                    "health": "<:healthamulet:1388930139466891265>"
                }
                emoji = emoji_map.get(type_, "✨")

                embed = discord.Embed(
                    title=f"Successfully Crafted Amulet! {emoji}",
                    description=f"You crafted a **Tier {tier} {type_.title()} Amulet**.",
                    color=discord.Color.green()
                )
                embed.add_field(name="Stats", value=f"❤️ Health: +{health}\n⚔️ Attack: +{attack}\n🛡️ Defense: +{defense}")
                
                # Show resources used
                used_resources = "\n".join([f"{amount}x {resource.replace('_', ' ').title()}" for resource, amount in recipe.items()])
                embed.add_field(name="Resources Used", value=used_resources, inline=False)
                
                await ctx.send(embed=embed)
        except Exception as e:
            await ctx.send(f"Error crafting amulet: {e}")

    @amulet.command(name="recipe")
    @has_char()
    async def view_recipe(self, ctx, type_: str, tier: int):
        """View the crafting recipe for a specific amulet type and tier."""
        type_ = type_.lower()
        if type_ not in self.AMULET_TYPES:
            valid_types = ', '.join(self.AMULET_TYPES.keys())
            return await ctx.send(f"Invalid amulet type! Choose from: `{valid_types}`")

        if tier not in range(1, 11):
            return await ctx.send("Invalid tier! Please choose a tier from 1 to 10.")

        recipe = self.AMULET_RECIPES.get(type_, {}).get(tier, {})
        if not recipe:
            return await ctx.send(f"Recipe for Tier {tier} {type_.title()} amulet not found.")

        stats = self.AMULET_TYPES[type_][tier]
        required_level = self.TIER_LEVELS.get(tier, 999)

        embed = discord.Embed(
            title=f"Tier {tier} {type_.title()} Amulet Recipe",
            description=f"Required Level: {required_level}",
            color=discord.Color.blue()
        )

        # Show recipe
        recipe_text = "\n".join([f"{amount}x {resource.replace('_', ' ').title()}" for resource, amount in recipe.items()])
        embed.add_field(name="Required Resources", value=recipe_text, inline=False)

        # Show stats
        embed.add_field(name="Amulet Stats", value=f"❤️ Health: +{stats['health']}\n⚔️ Attack: +{stats['attack']}\n🛡️ Defense: +{stats['defense']}", inline=False)

        await ctx.send(embed=embed)

    @amulet.command(name="equip")
    @has_char()
    async def equip_amulet(self, ctx, amulet_id: int):
        """Equip an amulet"""
        async with self.bot.pool.acquire() as conn:
            # Check if amulet exists and belongs to user
            amulet = await conn.fetchrow(
                'SELECT * FROM amulets WHERE id=$1 AND user_id=$2;',
                amulet_id, ctx.author.id
            )

            if not amulet:
                return await ctx.send("You don't own this amulet!")

            if amulet['equipped']:
                return await ctx.send("This amulet is already equipped!")

            # Check if user has ANY amulet equipped
            existing_equipped = await conn.fetchrow(
                'SELECT * FROM amulets WHERE user_id=$1 AND equipped=true;',
                ctx.author.id
            )

            message_parts = []
            
            # If there's an equipped amulet, unequip it first
            if existing_equipped:
                await conn.execute(
                    'UPDATE amulets SET equipped=false WHERE id=$1;',
                    existing_equipped['id']
                )
                message_parts.append(f"Unequipped your Tier {existing_equipped['tier']} {existing_equipped['type'].upper()} amulet.")

            # Equip the new amulet
            await conn.execute(
                'UPDATE amulets SET equipped=true WHERE id=$1;',
                amulet_id
            )
            
            message_parts.append(f"Successfully equipped your Tier {amulet['tier']} {amulet['type'].upper()} amulet!")
            
            await ctx.send(" ".join(message_parts))

    @amulet.command(name="unequip")
    @has_char()
    async def unequip_amulet(self, ctx, amulet_id: int):
        """Unequip an amulet"""
        async with self.bot.pool.acquire() as conn:
            # Check if amulet exists and belongs to user
            amulet = await conn.fetchrow(
                'SELECT * FROM amulets WHERE id=$1 AND user_id=$2;',
                amulet_id, ctx.author.id
            )

            if not amulet:
                return await ctx.send("You don't own this amulet!")

            if not amulet['equipped']:
                return await ctx.send("This amulet is not equipped!")

            # Unequip the amulet
            await conn.execute(
                'UPDATE amulets SET equipped=false WHERE id=$1;',
                amulet_id
            )

            await ctx.send(f"Successfully unequipped your Tier {amulet['tier']} {amulet['type'].upper()} amulet!")

    @amulet.command(name="help")
    @has_char()
    async def amulet_help(self, ctx):
        """Get comprehensive help about the amulet crafting system"""
        embed = discord.Embed(
            title="🔨 Amulet Crafting System Guide",
            description="Master the art of amulet crafting to enhance your combat abilities!",
            color=discord.Color.gold()
        )
        
        # What are amulets
        embed.add_field(
            name="💎 What are Amulets?",
            value=(
                "Amulets are powerful accessories that boost your HP, Attack, and Defense stats. "
                "You can craft them using materials found in PVE battles and equip them for permanent stat bonuses!"
            ),
            inline=False
        )
        
        # Amulet types
        amulet_types = (
            f"<:balancedamulet:1388929966397198470> **Balanced** - Equal HP, Attack, Defense bonuses\n"
            f"<:attackamulet:1388930099516014803> **Attack** - High Attack, moderate HP/Defense\n"
            f"<:defenseamulet:1388930014111727666> **Defense** - High Defense, moderate HP/Attack\n"
            f"<:healthamulet:1388930139466891265> **Health** - High HP, moderate Attack/Defense"
        )
        embed.add_field(name="🎯 Amulet Types", value=amulet_types, inline=False)
        
        # Tier progression
        embed.add_field(
            name="📈 Tier Progression",
            value=(
                "Amulets come in **10 tiers** with increasing power:\n"
                "• **Tier 1-3:** Early game (Levels 1-20)\n"
                "• **Tier 4-6:** Mid game (Levels 30-50)\n"
                "• **Tier 7-9:** Late game (Levels 60-80)\n"
                "• **Tier 10:** Endgame (Level 90+)"
            ),
            inline=False
        )
        
        # Getting resources
        embed.add_field(
            name="⚔️ Getting Crafting Resources",
            value=(
                "Fight monsters in **PVE battles** to earn crafting materials!\n"
                "• Low level monsters: Basic materials\n"
                "• High level monsters: Rare materials\n"
                "• Legendary monsters: Epic/Legendary materials\n"
                "Higher player levels unlock access to rarer resources!"
            ),
            inline=False
        )
        
        # Commands part 1
        commands_1 = (
            "`$amulet available` - Interactive menu to browse all craftable amulets\n"
            "`$amulet resources` - View your crafting materials inventory\n"
            "`$amulet craft <type> <tier>` - Craft a specific amulet"
        )
        embed.add_field(name="🛠️ Commands (1/2)", value=commands_1, inline=True)
        
        # Commands part 2
        commands_2 = (
            "`$amulet equip <id>` - Equip a crafted amulet\n"
            "`$amulet unequip <id>` - Unequip an amulet\n"
            "`$amulet recipe <type> <tier>` - View specific recipe\n"
            "`$amulet sell <resource> <amount>` - Sell unwanted resources\n"
            "`$amulet sell_prices` - View resource sell prices"
        )
        embed.add_field(name="🛠️ Commands (2/2)", value=commands_2, inline=True)
        
        # Tips
        embed.add_field(
            name="💡 Pro Tips",
            value=(
                "• Start with **`$amulet available`** to see what you can craft\n"
                "• Focus on your playstyle - tank players prefer Defense amulets\n"
                "• Save rare materials for higher tier amulets\n"
                "• Fight stronger monsters for better resource drops\n"
                "• Only one amulet can be equipped at a time\n"
                "• Sell unwanted resources for money using `$amulet sell`"
            ),
            inline=False
        )
        
        # Example workflow
        embed.add_field(
            name="🔄 Getting Started",
            value=(
                "1. Fight PVE monsters to gather resources\n"
                "2. Use `$amulet available` to see craftable options\n"
                "3. Craft your first Tier 1 amulet\n"
                "4. Equip it for immediate stat bonuses\n"
                "5. Work towards higher tiers as you level up!"
            ),
            inline=False
        )
        
        embed.set_footer(text="Good luck crafting! 🔨✨")
        
        await ctx.send(embed=embed)

    @amulet.command(name="sell_prices")
    @has_char()
    async def show_sell_prices(self, ctx):
        """Show the sell prices for all crafting resources"""
        embed = discord.Embed(
            title="💰 Crafting Resource Sell Prices",
            description="Here's how much you can sell each resource for:",
            color=discord.Color.gold()
        )
        
        # Group resources by rarity
        rarity_prices = {
            "common": 750,
            "uncommon": 1500,
            "rare": 5000,
            "epic": 10000,
            "legendary": 25000
        }
        
        rarity_emojis = {
            "common": "⚪",
            "uncommon": "🟢",
            "rare": "🔵",
            "epic": "🟣",
            "legendary": "🟡"
        }
        
        # Group resources by rarity
        resources_by_rarity = {}
        for resource, description in self.ALL_RESOURCES.items():
            rarity = self.get_resource_rarity(resource)
            if rarity not in resources_by_rarity:
                resources_by_rarity[rarity] = []
            resources_by_rarity[rarity].append(resource)
        
        # Create fields for each rarity
        for rarity in ["common", "uncommon", "rare", "epic", "legendary"]:
            if rarity in resources_by_rarity:
                resources = resources_by_rarity[rarity]
                price = rarity_prices[rarity]
                emoji = rarity_emojis[rarity]
                
                # Format resource list
                resource_list = []
                for resource in sorted(resources):
                    display_name = resource.replace('_', ' ').title()
                    resource_list.append(f"• {display_name}: ${price:,}")
                
                embed.add_field(
                    name=f"{emoji} {rarity.title()} Resources (${price:,} each)",
                    value="\n".join(resource_list),
                    inline=False
                )
        
        embed.add_field(
            name="💡 How to Sell",
            value=f"Use `{ctx.clean_prefix}amulet sell <resource> <amount>` to sell your resources!",
            inline=False
        )
        
        await ctx.send(embed=embed)

    @user_cooldown(60)
    @amulet.command(name="sell")
    @has_char()
    async def sell_resources(self, ctx, *args):
        """Sell unwanted crafting resources for money"""
        if len(args) < 2:
            return await ctx.send(
                f"❌ **Usage**: `{ctx.clean_prefix}amulet sell <resource_name> <amount>`\n\n"
                f"Examples:\n"
                f"• `{ctx.clean_prefix}amulet sell fire_gems 5`\n"
                f"• `{ctx.clean_prefix}amulet sell \"fire gem\" 3`\n"
                f"• `{ctx.clean_prefix}amulet sell dragon_scales 10`\n\n"
                f"Use `{ctx.clean_prefix}amulet resources` to see what you have."
            )
        
        # Parse the arguments - last argument is amount, everything else is resource name
        amount = args[-1]
        resource_name_parts = args[:-1]
        
        try:
            amount = int(amount)
            if amount <= 0:
                return await ctx.send("❌ **Error**: Amount must be greater than 0.")
        except ValueError:
            return await ctx.send("❌ **Error**: Amount must be a valid number.")
        
        # Join the resource name parts back together
        resource_name = " ".join(resource_name_parts)
        
        # Normalize the resource name
        normalized_resource = self.normalize_resource_name(resource_name)
        
        # Validate that this is a known resource
        if normalized_resource not in self.ALL_RESOURCES:
            # Try to suggest similar resources
            suggestions = []
            for resource in self.ALL_RESOURCES.keys():
                if resource_name.lower() in resource.lower() or resource.lower() in resource_name.lower():
                    suggestions.append(resource.replace('_', ' ').title())
            
            if suggestions:
                suggestion_text = ", ".join(suggestions[:3])  # Limit to 3 suggestions
                return await ctx.send(f"❌ **Unknown Resource**: '{resource_name}' is not a valid crafting resource.\n\nDid you mean: {suggestion_text}?")
            else:
                return await ctx.send(f"❌ **Unknown Resource**: '{resource_name}' is not a valid crafting resource.\n\nUse `{ctx.clean_prefix}amulet resources` to see your available resources.")
        
        # Calculate sell price based on resource rarity
        sell_price = self.calculate_resource_sell_price(normalized_resource, amount)
        
        # Show confirmation dialog
        confirmation_message = (
            f"Are you sure you want to sell **{amount}x {normalized_resource.replace('_', ' ').title()}** "
            f"for **${sell_price:,}**?\n\n"
            f"• Resource: {normalized_resource.replace('_', ' ').title()}\n"
            f"• Amount: {amount}\n"
            f"• Price per unit: ${sell_price // amount:,}\n"
            f"• Total: ${sell_price:,}"
        )
        
        if not await ctx.confirm(confirmation_message):
            self.bot.reset_cooldown(ctx)
            return await ctx.send("❌ **Sale cancelled**. Your resources are safe!")
        
        # Double-check validation to prevent exploitation
        async with self.bot.pool.acquire() as conn:
            async with conn.transaction():
                # Lock the user's resources to prevent race conditions
                current_amount = await conn.fetchval(
                    'SELECT amount FROM crafting_resources WHERE user_id=$1 AND resource_type=$2 FOR UPDATE',
                    ctx.author.id, normalized_resource
                )
                
                if not current_amount or current_amount < amount:
                    return await ctx.send(
                        f"❌ **Sale Failed**: You no longer have enough {normalized_resource.replace('_', ' ').title()}.\n"
                        f"You have: {current_amount or 0}, trying to sell: {amount}\n\n"
                        f"This could happen if you sold or used these resources in another command."
                    )
                
                # Remove the resources
                await conn.execute(
                    'UPDATE crafting_resources SET amount = amount - $1 WHERE user_id=$2 AND resource_type=$3',
                    amount, ctx.author.id, normalized_resource
                )
                
                # Add money to the user
                await conn.execute(
                    'UPDATE profile SET "money" = "money" + $1 WHERE "user" = $2',
                    sell_price, ctx.author.id
                )
                
                # Log the transaction
                await self.bot.log_transaction(
                    ctx,
                    from_=1,
                    to=ctx.author.id,
                    subject="resource sale",
                    data={
                        "Resource": normalized_resource.replace('_', ' ').title(),
                        "Amount": amount,
                        "Price": sell_price,
                        "Price per unit": sell_price // amount
                    },
                    conn=conn
                )
        
        # Success message
        embed = discord.Embed(
            title="💰 Resources Sold Successfully!",
            description=f"You sold **{amount}x {normalized_resource.replace('_', ' ').title()}** for **${sell_price:,}**",
            color=discord.Color.green()
        )
        embed.add_field(
            name="Transaction Details",
            value=f"• Resource: {normalized_resource.replace('_', ' ').title()}\n"
                  f"• Amount Sold: {amount}\n"
                  f"• Price per unit: ${sell_price // amount:,}\n"
                  f"• Total earned: ${sell_price:,}",
            inline=False
        )
        
        await ctx.send(embed=embed)

    def normalize_resource_name(self, resource_name: str):
        """
        Normalize resource names to handle various input formats.
        Converts "fire gem" -> "fire_gems", "dragon scale" -> "dragon_scales", etc.
        """
        # Remove quotes and extra whitespace, convert to lowercase for matching
        resource_name = resource_name.strip().strip('"\'')
        resource_name_lower = resource_name.lower()
        
        # Common mappings for user-friendly names to database names
        resource_mappings = {
            # Attack resources
            "demon claw": "demon_claws",
            "demon claws": "demon_claws",
            "fire gem": "fire_gems",
            "fire gems": "fire_gems",
            "warrior essence": "warrior_essence",
            "blood crystal": "blood_crystals",
            "blood crystals": "blood_crystals",
            "storm shard": "storm_shards",
            "storm shards": "storm_shards",
            "berserker tear": "berserker_tears",
            "berserker tears": "berserker_tears",
            "phoenix feather": "phoenix_feathers",
            "phoenix feathers": "phoenix_feathers",
            
            # Defense resources
            "steel ingot": "steel_ingots",
            "steel ingots": "steel_ingots",
            "guardian stone": "guardian_stones",
            "guardian stones": "guardian_stones",
            "protective rune": "protective_runes",
            "protective runes": "protective_runes",
            "mountain heart": "mountain_hearts",
            "mountain hearts": "mountain_hearts",
            "titan shell": "titan_shells",
            "titan shells": "titan_shells",
            "ward crystal": "ward_crystals",
            "ward crystals": "ward_crystals",
            "sentinel core": "sentinel_cores",
            "sentinel cores": "sentinel_cores",
            
            # Health resources
            "life crystal": "life_crystals",
            "life crystals": "life_crystals",
            "healing herb": "healing_herbs",
            "healing herbs": "healing_herbs",
            "vitality essence": "vitality_essence",
            "phoenix blood": "phoenix_blood",
            "world tree sap": "world_tree_sap",
            "unicorn tear": "unicorn_tears",
            "unicorn tears": "unicorn_tears",
            "rejuvenation orb": "rejuvenation_orbs",
            "rejuvenation orbs": "rejuvenation_orbs",
            
            # Balance resources
            "harmony stone": "harmony_stones",
            "harmony stones": "harmony_stones",
            "balance orb": "balance_orbs",
            "balance orbs": "balance_orbs",
            "equilibrium dust": "equilibrium_dust",
            "yin yang crystal": "yin_yang_crystals",
            "yin yang crystals": "yin_yang_crystals",
            "neutral essence": "neutral_essence",
            "cosmic fragment": "cosmic_fragments",
            "cosmic fragments": "cosmic_fragments",
            "void pearl": "void_pearls",
            "void pearls": "void_pearls",
            
            # Shared resources
            "dragon scale": "dragon_scales",
            "dragon scales": "dragon_scales",
            "mystic dust": "mystic_dust",
            "refined ore": "refined_ore",
        }
        
        # Check if it's already in the correct format (case-insensitive)
        if resource_name_lower in resource_mappings:
            return resource_mappings[resource_name_lower]
        
        # If it's already in underscore format, return as is
        if '_' in resource_name:
            return resource_name
        
        # Try to convert space-separated to underscore format
        normalized = resource_name.replace(' ', '_')
        
        # Check if the normalized version exists in our mappings
        for key, value in resource_mappings.items():
            if key.replace(' ', '_') == normalized:
                return value
        
        # If all else fails, return the original (might be a valid underscore format)
        return resource_name

    def calculate_resource_sell_price(self, resource_name: str, amount: int):
        """
        Calculate the sell price for a resource based on its rarity.
        
        Args:
            resource_name (str): The normalized resource name
            amount (int): Amount being sold
            
        Returns:
            int: Total sell price
        """
        # Base prices per rarity tier
        rarity_prices = {
            "common": 750,      # 750 gold per unit
            "uncommon": 1500,   # 1500 gold per unit
            "rare": 5000,       # 5000 gold per unit
            "epic": 10000,      # 10000 gold per unit
            "legendary": 25000  # 25000 gold per unit
        }
        
        # Get the rarity of the resource
        rarity = self.get_resource_rarity(resource_name)
        if not rarity:
            rarity = "common"  # Default to common if not found
        
        # Get base price for this rarity
        base_price = rarity_prices.get(rarity, 750)
        
        # Calculate total price
        total_price = base_price * amount
        
        return total_price

    async def get_player_level(self, user_id: int):
        """
        Get the player's level from their XP.
        
        Args:
            user_id (int): Discord user ID
            
        Returns:
            int: Player level, or 0 if not found
        """
        try:
            async with self.bot.pool.acquire() as conn:
                player = await conn.fetchrow('SELECT xp FROM profile WHERE "user"=$1;', user_id)
                if player:
                    return rpgtools.xptolevel(player['xp'])
                return 0
        except Exception:
            return 0

    def get_max_tier_for_level(self, level: int):
        """
        Get the maximum tier a player can access based on their level.
        
        Args:
            level (int): Player level
            
        Returns:
            int: Maximum tier (1-10)
        """
        max_tier = 1
        for tier, required_level in self.TIER_LEVELS.items():
            if level >= required_level:
                max_tier = tier
            else:
                break
        return max_tier

    def get_available_resources_for_level(self, level: int, category: str = None):
        """
        Get resources available for a player's level.
        
        Args:
            level (int): Player level
            category (str, optional): Resource category to filter by
            
        Returns:
            list: List of available resource names
        """
        max_tier = self.get_max_tier_for_level(level)
        
        # Get base resource pool
        if category and category in self.RESOURCE_CATEGORIES:
            available_resources = self.RESOURCE_CATEGORIES[category].copy()
        else:
            available_resources = list(self.ALL_RESOURCES.keys())
        
        # Filter resources based on tier requirements
        # We'll create a mapping of resources to their minimum tier requirement
        resource_tier_requirements = {}
        
        # Analyze recipes to determine minimum tier for each resource
        for amulet_type, tiers in self.AMULET_RECIPES.items():
            for tier, recipe in tiers.items():
                for resource in recipe.keys():
                    if resource not in resource_tier_requirements:
                        resource_tier_requirements[resource] = tier
                    else:
                        # Keep the minimum tier requirement
                        resource_tier_requirements[resource] = min(resource_tier_requirements[resource], tier)
        
        # Filter out resources that require higher tiers than player can access
        level_appropriate_resources = []
        for resource in available_resources:
            required_tier = resource_tier_requirements.get(resource, 1)  # Default to tier 1 if not found
            if required_tier <= max_tier:
                level_appropriate_resources.append(resource)
        
        return level_appropriate_resources

    def get_minimum_level_for_resource(self, resource_name: str):
        """
        Get the minimum level required to access a specific resource.
        
        Args:
            resource_name (str): Name of the resource
            
        Returns:
            int: Minimum level required, or 1 if not found
        """
        # Analyze recipes to determine minimum tier for each resource
        resource_tier_requirements = {}
        
        for amulet_type, tiers in self.AMULET_RECIPES.items():
            for tier, recipe in tiers.items():
                for resource in recipe.keys():
                    if resource not in resource_tier_requirements:
                        resource_tier_requirements[resource] = tier
                    else:
                        # Keep the minimum tier requirement
                        resource_tier_requirements[resource] = min(resource_tier_requirements[resource], tier)
        
        # Get the minimum tier required for this resource
        required_tier = resource_tier_requirements.get(resource_name, 1)
        
        # Convert tier to level requirement
        for tier, level in self.TIER_LEVELS.items():
            if tier >= required_tier:
                return level
        
        return 1  # Default to level 1 if not found


async def setup(bot):
    await bot.add_cog(AmuletCrafting(bot))
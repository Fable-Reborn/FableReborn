"""Extension for Dragon mechanics in battles"""
import asyncio
import random
from decimal import Decimal
from typing import Dict, List, Any, Optional

from ..core.combatant import Combatant
from ..core.team import Team

class DragonExtension:
    """Extension for handling Ice Dragon mechanics and abilities"""
    
    def __init__(self):
        # Dragon evolution stages with abilities and stats scaling
        self.dragon_stages = {
            "Frostbite Wyrm": {
                "level_range": (1, 5),
                "moves": {
                    "Ice Breath": {"dmg": 600, "effect": "freeze", "chance": 0.3},
                    "Tail Sweep": {"dmg": 400, "effect": "aoe", "chance": 0.4},
                    "Frost Bite": {"dmg": 300, "effect": "dot", "chance": 0.3}
                },
                "passives": ["Ice Armor"],
                "base_multiplier": 1.0
            },
            "Corrupted Ice Dragon": {
                "level_range": (6, 10),
                "moves": {
                    "Frosty Ice Burst": {"dmg": 800, "effect": "random_debuff", "chance": 0.3},
                    "Minion Army": {"dmg": 200, "effect": "summon_adds", "chance": 0.3},
                    "Frost Spears": {"dmg": 500, "effect": "dot", "chance": 0.4}
                },
                "passives": ["Corruption"],
                "base_multiplier": 1.15
            },
            "Permafrost": {
                "level_range": (11, 15),
                "moves": {
                    "Soul Reaver": {"dmg": 1000, "effect": "stun", "chance": 0.3},
                    "Death Note": {"dmg": 700, "effect": "curse", "chance": 0.3},
                    "Dark Shadows": {"dmg": 900, "effect": "aoe_dot", "chance": 0.4}
                },
                "passives": ["Void Fear"],
                "base_multiplier": 1.25
            },
            "Absolute Zero": {
                "level_range": (16, 20),
                "moves": {
                    "Void Blast": {"dmg": 1200, "effect": "aoe_stun", "chance": 0.3},
                    "Soul Crusher": {"dmg": 1000, "effect": "death_mark", "chance": 0.3},
                    "Armageddon": {"dmg": 800, "effect": "global_dot", "chance": 0.4}
                },
                "passives": ["Aspect of death"],
                "base_multiplier": 1.5
            }
        }
    
    async def get_dragon_stage(self, level: int) -> Dict[str, Any]:
        """Determine the appropriate dragon stage based on level"""
        for stage_name, stage_info in self.dragon_stages.items():
            min_level, max_level = stage_info["level_range"]
            if min_level <= level <= max_level:
                return {
                    "name": stage_name,
                    "info": stage_info
                }
        
        # Default to the highest stage if level exceeds all ranges
        return {
            "name": "Absolute Zero",
            "info": self.dragon_stages["Absolute Zero"]
        }
    
    async def calculate_dragon_stats(self, level: int) -> Dict[str, Any]:
        """Calculate dragon stats based on level"""
        # Get the appropriate stage for the level
        stage = await self.get_dragon_stage(level)
        stage_name = stage["name"]
        stage_info = stage["info"]
        
        # Use the same calculation as in the icedragonchallenge cog
        base_multiplier = stage_info["base_multiplier"]
        level_multiplier = 1 + (0.1 * (level - 1))  # 10% increase per level
        
        # Calculate stats using the same formula as icedragonchallenge
        hp = 3500 * base_multiplier * level_multiplier
        damage = 290 * level_multiplier
        armor = 220 * level_multiplier
        
        # Get moves and passives from the stage
        moves = stage_info["moves"]
        passives = stage_info["passives"]
        
        return {
            "name": stage_name,
            "stage": stage_name,
            "level": level,
            "hp": hp,
            "damage": damage,
            "armor": armor,
            "moves": moves,
            "passives": passives,
            "passive_effects": passives
        }
    
    async def create_dragon_combatant(self, level: int) -> Combatant:
        """Create a combatant object for the dragon at the specified level"""
        # Calculate dragon stats
        dragon_stats = await self.calculate_dragon_stats(level)
        
        # Create combatant
        dragon = Combatant(
            user=dragon_stats["name"],  # Use dragon name as user
            hp=dragon_stats["hp"],
            max_hp=dragon_stats["hp"],
            damage=dragon_stats["damage"],
            armor=dragon_stats["armor"],
            element="Ice",  # Default element for ice dragon
            name=dragon_stats["name"],
            is_dragon=True,
            passives=dragon_stats["passives"],
            stage=dragon_stats["stage"],
            dragon_level=level
        )
        
        return dragon
    
    async def get_dragon_stats_from_database(self, bot) -> Dict[str, Any]:
        """Get current dragon level and weekly defeats from database"""
        async with bot.pool.acquire() as conn:
            result = await conn.fetchrow(
                'SELECT current_level, weekly_defeats, last_reset FROM dragon_progress WHERE id = 1'
            )
            
            if not result:
                # Default values if no record exists
                return {
                    "level": 1,
                    "weekly_defeats": 0,
                    "last_reset": None
                }
            
            return {
                "level": result["current_level"],
                "weekly_defeats": result["weekly_defeats"],
                "last_reset": result["last_reset"]
            }
    
    async def update_dragon_progress(self, bot, dragon_level: int, weekly_defeats: int, victory: bool = True) -> dict:
        """Update dragon progress in the database"""
        # If victory, increase weekly defeats and check for level up
        if victory:
            new_weekly_defeats = weekly_defeats + 1
            # Calculate threshold based on current dragon level
            level_up_threshold = self.get_level_up_threshold(dragon_level)
            # Level up when defeating the dragon enough times
            if new_weekly_defeats >= level_up_threshold:
                new_level = dragon_level + 1
                # Reset weekly defeats counter after level up
                new_weekly_defeats = 0
            else:
                new_level = dragon_level
        else:
            new_level = dragon_level
            new_weekly_defeats = weekly_defeats
        
        async with bot.pool.acquire() as conn:
            # Check if record exists
            exists = await conn.fetchval(
                'SELECT 1 FROM dragon_progress WHERE id = 1'
            )
            
            if exists:
                # Update existing record
                await conn.execute(
                    'UPDATE dragon_progress SET current_level = $1, weekly_defeats = $2, last_reset = NOW() WHERE id = 1',
                    new_level, new_weekly_defeats
                )
            else:
                # Insert new record
                await conn.execute(
                    'INSERT INTO dragon_progress (id, current_level, weekly_defeats, last_reset) VALUES (1, $1, $2, NOW())',
                    new_level, new_weekly_defeats
                )
                
        # Return the updated stats
        return {
            "level": new_level,
            "weekly_defeats": new_weekly_defeats
        }
        
    def get_level_up_threshold(self, current_level: int) -> int:
        """Get the number of defeats needed for the dragon to level up
        
        Always 40 defeats per level, regardless of dragon's current level
        """
        return 40  # Fixed threshold - 40 defeats needed per level
    
    async def check_and_perform_weekly_reset(self, bot) -> bool:
        """Check if weekly reset is needed and perform it if so"""
        async with bot.pool.acquire() as conn:
            result = await conn.fetchrow(
                'SELECT last_reset FROM dragon_progress WHERE id = 1'
            )
            
            if not result:
                # No record, no reset needed
                return False
            
            last_reset = result["last_reset"]
            
            # Check if it's been a week since last reset
            now = await conn.fetchval('SELECT NOW()')
            
            if (now - last_reset).days >= 7:
                # Reset weekly defeats and update reset time
                await conn.execute(
                    'UPDATE dragon_progress SET weekly_defeats = 0, last_reset = $1 WHERE id = 1',
                    now
                )
                return True
                
        return False
        
    async def create_dragon_team(self, level: int) -> Team:
        """Create a team with just the dragon"""
        dragon = await self.create_dragon_combatant(level)
        return Team("Dragon", [dragon])

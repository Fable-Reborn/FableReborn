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
        # Fallback defaults if DB tables are empty/unavailable
        self.default_dragon_stages = {
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
            },
            "Void Tyrant": {
                "level_range": (21, 25),
                "moves": {
                    "Reality Shatter": {"dmg": 1500, "effect": "dimension_tear", "chance": 0.3},
                    "Soul Harvest": {"dmg": 1200, "effect": "soul_drain", "chance": 0.3},
                    "Void Storm": {"dmg": 1000, "effect": "void_explosion", "chance": 0.4}
                },
                "passives": ["Void Corruption", "Soul Devourer"],
                "base_multiplier": 2.0
            },
            "Eternal Frost": {
                "level_range": (26, 30),
                "moves": {
                    "Time Freeze": {"dmg": 2000, "effect": "time_stop", "chance": 0.3},
                    "Eternal Damnation": {"dmg": 1500, "effect": "eternal_curse", "chance": 0.3},
                    "Apocalypse": {"dmg": 1200, "effect": "world_ender", "chance": 0.4}
                },
                "passives": ["Eternal Winter", "Death's Embrace", "Reality Bender"],
                "base_multiplier": 3.0
            }
        }
        self.default_passive_descriptions = {
            "Ice Armor": "Reduces all damage by 20%.",
            "Corruption": "Reduces shields/armor by 20%.",
            "Void Fear": "Reduces attack power by 20%.",
            "Aspect of death": "Reduces attack and defense by 30%.",
            "Void Corruption": "Reduces all stats by 25% and inflicts void damage.",
            "Soul Devourer": "Steals 15% of damage dealt as health.",
            "Eternal Winter": "Freezes all healing and reduces damage by 40%.",
            "Death's Embrace": "10% chance to instantly kill on any hit.",
            "Reality Bender": "Randomly negates 50% of attacks and reflects damage."
        }
    
    async def _get_abilities_map(self, bot, ability_type: str) -> Dict[str, Dict[str, Any]]:
        """Return a mapping of ability name -> ability data from DB (or fallback)."""
        try:
            async with bot.pool.acquire() as conn:
                rows = await conn.fetch(
                    "SELECT name, description, dmg, effect, chance FROM ice_dragon_abilities WHERE ability_type = $1",
                    ability_type,
                )
            if not rows:
                raise RuntimeError("No abilities in DB")
            ability_map = {}
            for row in rows:
                ability_map[row["name"]] = {
                    "description": row["description"],
                    "dmg": row["dmg"],
                    "effect": row["effect"],
                    "chance": row["chance"],
                }
            return ability_map
        except Exception:
            ability_map = {}
            for stage_info in self.default_dragon_stages.values():
                for move_name, move_info in stage_info.get("moves", {}).items():
                    ability_map[move_name] = {
                        "description": f"Effect: {move_info['effect']}, Damage: {move_info['dmg']}, Chance: {int(move_info['chance'] * 100)}%",
                        "dmg": move_info["dmg"],
                        "effect": move_info["effect"],
                        "chance": move_info["chance"],
                    }
            return ability_map

    async def get_passive_descriptions(self, bot, passive_names: List[str]) -> Dict[str, str]:
        """Get passive descriptions for the provided names."""
        descriptions = {}
        try:
            async with bot.pool.acquire() as conn:
                rows = await conn.fetch(
                    "SELECT name, description FROM ice_dragon_abilities WHERE ability_type = 'passive' AND name = ANY($1::text[])",
                    passive_names,
                )
            for row in rows:
                descriptions[row["name"]] = row["description"] or ""
        except Exception:
            pass
        for name in passive_names:
            descriptions.setdefault(name, self.default_passive_descriptions.get(name, ""))
        return descriptions

    async def get_dragon_stage(self, bot, level: int) -> Dict[str, Any]:
        """Determine the appropriate dragon stage based on level using DB stages."""
        try:
            async with bot.pool.acquire() as conn:
                rows = await conn.fetch(
                    "SELECT id, name, min_level, max_level, base_multiplier, enabled, element, move_names, passive_names "
                    "FROM ice_dragon_stages WHERE enabled IS TRUE ORDER BY min_level ASC, max_level ASC, id ASC"
                )
            if not rows:
                raise RuntimeError("No stages in DB")
            move_map = await self._get_abilities_map(bot, "move")
            eligible = [row for row in rows if row["min_level"] <= level <= row["max_level"]]
            if not eligible:
                raise RuntimeError("No stages for level")
            import random
            row = random.choice(eligible)
            moves = {}
            for move_name in row["move_names"] or []:
                if move_name in move_map:
                    moves[move_name] = {
                        "dmg": move_map[move_name]["dmg"],
                        "effect": move_map[move_name]["effect"],
                        "chance": move_map[move_name]["chance"],
                    }
            return {
                "id": row["id"],
                "name": row["name"],
                "info": {
                    "level_range": (row["min_level"], row["max_level"]),
                    "moves": moves,
                    "passives": row["passive_names"] or [],
                    "base_multiplier": row["base_multiplier"],
                    "element": row["element"] or "Water",
                },
            }
        except Exception:
            for stage_name, stage_info in self.default_dragon_stages.items():
                min_level, max_level = stage_info["level_range"]
                if min_level <= level <= max_level:
                    return {"name": stage_name, "info": stage_info | {"element": "Water"}}
        return {"name": "Eternal Frost", "info": self.default_dragon_stages["Eternal Frost"] | {"element": "Water"}}
    
    async def calculate_dragon_stats(self, bot, level: int) -> Dict[str, Any]:
        """Calculate dragon stats based on level"""
        # Get the appropriate stage for the level
        stage = await self.get_dragon_stage(bot, level)
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
            "passive_effects": passives,
            "element": stage_info.get("element", "Water"),
        }
    
    async def create_dragon_combatant(self, bot, level: int) -> Combatant:
        """Create a combatant object for the dragon at the specified level"""
        # Calculate dragon stats
        dragon_stats = await self.calculate_dragon_stats(bot, level)
        
        # Create combatant
        dragon = Combatant(
            user=dragon_stats["name"],  # Use dragon name as user
            hp=dragon_stats["hp"],
            max_hp=dragon_stats["hp"],
            damage=dragon_stats["damage"],
            armor=dragon_stats["armor"],
            element=dragon_stats.get("element", "Water"),
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
        
    async def create_dragon_team(self, bot, level: int) -> Team:
        """Create a team with just the dragon"""
        dragon = await self.create_dragon_combatant(bot, level)
        return Team("Dragon", [dragon])

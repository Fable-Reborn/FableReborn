"""
Battle settings module for managing feature toggles and configurations.
This allows enabling/disabling features like pets, elements, etc. per battle type.
"""
import asyncio
import discord
from discord.ext import commands
from typing import Dict, Any, Optional, List, Union
import json

class BattleSettings:
    """Manages battle system settings and configurations"""
    
    def __init__(self, bot):
        self.bot = bot
        self.cache = {}
        self.default_settings = {
            "global": {
                "allow_pets": True,
                "class_buffs": True,
                "element_effects": True,
                "luck_effects": True,
                "reflection_damage": True,
                "fireball_chance": 0.3,
                "cheat_death": True,
                "tripping": True,
                "status_effects": False,
                "pets_continue_battle": False  # By default, battles end if player is defeated even if pet is alive
            },
            "pve": {
                "allow_pets": False  # We default to no pets in PvE as requested
            },
            "pvp": {},
            "raid": {},
            "tower": {},
            "team": {}
        }
        
    async def initialize(self):
        """Initialize settings database table if it doesn't exist"""
        async with self.bot.pool.acquire() as conn:
            # Create the settings table if it doesn't exist
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS battle_settings (
                    id SERIAL PRIMARY KEY,
                    battle_type VARCHAR(32) NOT NULL,
                    setting_key VARCHAR(64) NOT NULL,
                    setting_value JSONB NOT NULL,
                    UNIQUE(battle_type, setting_key)
                )
            """)
            
            # Load settings into cache
            await self.load_settings()
    
    async def load_settings(self):
        """Load all settings from database into cache"""
        async with self.bot.pool.acquire() as conn:
            records = await conn.fetch("SELECT battle_type, setting_key, setting_value FROM battle_settings")
            
            # Initialize with default settings using deep copy to avoid reference issues
            self.cache = {}
            for battle_type, settings in self.default_settings.items():
                self.cache[battle_type] = settings.copy()  # Copy each settings dict
            
            # Load saved settings from database
            for record in records:
                battle_type = record["battle_type"]
                key = record["setting_key"]
                try:
                    # Parse the JSON value properly
                    value = json.loads(record["setting_value"])
                except:
                    # Fallback if parsing fails
                    value = record["setting_value"]
                
                # Create battle type entry if it doesn't exist
                if battle_type not in self.cache:
                    self.cache[battle_type] = {}
                
                # Store the setting
                self.cache[battle_type][key] = value
                
            print(f"Battle settings loaded: {self.cache}")  # Debug log
            
    async def force_refresh(self):
        """Force a reload of all settings from database"""
        await self.load_settings()
        return True
    
    async def get_setting(self, battle_type: str, key: str) -> Any:
        """Get a specific setting for a battle type"""
        # First check battle-specific settings
        if battle_type in self.cache and key in self.cache[battle_type]:
            return self.cache[battle_type][key]
        
        # Then check global settings
        if "global" in self.cache and key in self.cache["global"]:
            return self.cache["global"][key]
        
        # Then check defaults
        if battle_type in self.default_settings and key in self.default_settings[battle_type]:
            return self.default_settings[battle_type][key]
        
        if "global" in self.default_settings and key in self.default_settings["global"]:
            return self.default_settings["global"][key]
        
        # No setting found
        return None
    
    async def set_setting(self, battle_type: str, key: str, value: Any) -> bool:
        """Set a specific setting for a battle type"""
        async with self.bot.pool.acquire() as conn:
            try:
                # Ensure value is properly serialized to JSON
                json_value = json.dumps(value)
                
                await conn.execute("""
                    INSERT INTO battle_settings (battle_type, setting_key, setting_value)
                    VALUES ($1, $2, $3)
                    ON CONFLICT (battle_type, setting_key)
                    DO UPDATE SET setting_value = $3
                """, battle_type, key, json_value)
                
                # Update cache
                if battle_type not in self.cache:
                    self.cache[battle_type] = {}
                self.cache[battle_type][key] = value
                
                print(f"Set battle setting: {battle_type}.{key} = {value}")
                print(f"Current cache: {self.cache}")
                
                return True
            except Exception as e:
                print(f"Error setting battle setting: {e}")
                return False
    
    async def reset_setting(self, battle_type: str, key: str) -> bool:
        """Reset a setting to default by removing it from the database"""
        async with self.bot.pool.acquire() as conn:
            try:
                await conn.execute("""
                    DELETE FROM battle_settings 
                    WHERE battle_type = $1 AND setting_key = $2
                """, battle_type, key)
                
                # Update cache
                if battle_type in self.cache and key in self.cache[battle_type]:
                    del self.cache[battle_type][key]
                
                return True
            except Exception as e:
                print(f"Error resetting battle setting: {e}")
                return False
    
    async def get_all_settings(self, battle_type: str = None) -> Dict[str, Any]:
        """Get all settings, optionally filtered by battle type"""
        result = {}
        
        if battle_type:
            # Get specific battle type settings
            for key in self.default_settings["global"].keys():
                result[key] = await self.get_setting(battle_type, key)
        else:
            # Get all settings
            for bt in ["global", "pve", "pvp", "raid", "tower", "team"]:
                result[bt] = {}
                for key in self.default_settings["global"].keys():
                    result[bt][key] = await self.get_setting(bt, key)
        
        return result
    
    async def apply_settings_to_battle(self, battle_type: str, kwargs: Dict[str, Any]) -> Dict[str, Any]:
        """Apply the current settings to battle kwargs"""
        result = kwargs.copy()
        
        # Apply each setting from the configuration
        for key in self.default_settings["global"].keys():
            # Only override if not explicitly provided in kwargs
            if key not in kwargs:
                result[key] = await self.get_setting(battle_type, key)
        
        return result
    
    def get_configurable_settings(self) -> List[str]:
        """Get a list of all configurable settings"""
        return list(self.default_settings["global"].keys())

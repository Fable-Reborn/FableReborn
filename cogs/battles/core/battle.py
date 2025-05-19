# battles/core/battle.py
from abc import ABC, abstractmethod
import asyncio
import datetime
from collections import deque
from decimal import Decimal
import random
from typing import List, Dict, Optional, Union, Any

import discord
from discord.ext import commands

# Import the status effect registry
from .status_effect import StatusEffectRegistry

class Battle(ABC):
    """Base class for all battle types"""
    
    def __init__(self, ctx, teams=None, **kwargs):
        self.ctx = ctx
        self.bot = ctx.bot
        self.teams = teams or []
        self.log = deque(maxlen=kwargs.get("log_size", 5))
        self.action_number = 0
        self.started = False
        self.finished = False
        self.start_time = None
        self.max_duration = kwargs.get("max_duration", datetime.timedelta(minutes=5))
        self.winner = None
        self.battle_message = None
        
        # Configuration options
        self.config = {
            "allow_pets": kwargs.get("allow_pets", True),
            "class_buffs": kwargs.get("class_buffs", True),
            "element_effects": kwargs.get("element_effects", True),
            "luck_effects": kwargs.get("luck_effects", True),
            "reflection_damage": kwargs.get("reflection_damage", True),
            "fireball_chance": kwargs.get("fireball_chance", 0.3),
            "cheat_death": kwargs.get("cheat_death", True),
            "tripping": kwargs.get("tripping", True),
            "simple": kwargs.get("simple", False),  # Simple battle = classic battle format
            "status_effects": kwargs.get("status_effects", False),  # Enable status effects system
        }
    
    @abstractmethod
    async def start_battle(self):
        """Initialize and start the battle"""
        self.started = True
        self.start_time = datetime.datetime.utcnow()
        return True
    
    @abstractmethod
    async def process_turn(self):
        """Process a single turn of the battle"""
        pass
    
    @abstractmethod
    async def end_battle(self):
        """End the battle and handle rewards"""
        self.finished = True
        return None
    
    @abstractmethod
    async def update_display(self):
        """Update the battle display (embed)"""
        pass
    
    async def is_battle_over(self):
        """Check if battle has conditions to end"""
        return self.finished or await self.is_timed_out()
    
    async def is_timed_out(self):
        """Check if battle has exceeded maximum duration"""
        if not self.start_time:
            return False
        return datetime.datetime.utcnow() > self.start_time + self.max_duration
    
    async def add_to_log(self, message):
        """Add a message to the battle log"""
        self.log.append((self.action_number, message))
        self.action_number += 1
    
    def create_hp_bar(self, current_hp, max_hp, length=20):
        """Create a visual HP bar"""
        ratio = float(current_hp) / float(max_hp) if max_hp > 0 else 0
        ratio = max(0, min(1, ratio))  # Ensure ratio is between 0 and 1
        filled_length = int(length * ratio)
        bar = '█' * filled_length + '░' * (length - filled_length)
        return bar
        
    def format_number(self, number):
        """Format a number to 2 decimal places for display in battle messages"""
        if isinstance(number, Decimal):
            # Convert Decimal to float, then format to 2 decimal places
            return f"{float(number):.2f}"
        elif isinstance(number, (int, float)):
            # Format to 2 decimal places
            return f"{number:.2f}"
        # If not a number, return as is
        return str(number)
        
    # ----- Status Effect System Methods -----
    
    async def apply_status_effect(self, effect_type, target, source=None, **kwargs):
        """Apply a status effect to a target combatant"""
        try:
            # Create the effect from the registry
            effect = StatusEffectRegistry.create(effect_type, **kwargs)
            
            # Apply to the target
            effect.apply(target, source)
            
            # Add to battle log
            effect_msg = f"{effect.name} applied to {target.name}"
            if source:
                effect_msg = f"{source.name} applied {effect.name} to {target.name}"
            await self.add_to_log(effect_msg)
            
            return effect
        except ValueError as e:
            # Unknown effect type
            await self.add_to_log(f"Failed to apply effect: {str(e)}")
            return None
    
    async def process_combatant_effects(self, combatant, is_turn_start=False):
        """Process status effects for a specific combatant"""
        messages = []
        
        # First, process expiration and tick events
        status_messages = combatant.process_status_effects()
        if status_messages:
            messages.extend(status_messages)
        
        # Then process turn start/end effects
        if is_turn_start:
            turn_messages = combatant.process_turn_start_effects()
        else:
            turn_messages = combatant.process_turn_end_effects()
            
        if turn_messages:
            messages.extend(turn_messages)
            
        # Add all messages to battle log
        for message in messages:
            await self.add_to_log(message)
        
        return messages
    
    def get_effect_chance(self, source, target, base_chance):
        """Calculate if an effect should be applied based on source luck vs target luck"""
        if not self.config["luck_effects"]:
            return base_chance
            
        # Adjust effect chance based on luck difference
        luck_diff = float(source.luck - target.luck) / 100
        modified_chance = base_chance * (1 + luck_diff)
        
        # Keep within reasonable bounds
        return max(0.05, min(0.95, modified_chance))
    
    def get_effect_duration(self, base_duration, luck):
        """Calculate effect duration based on luck"""
        if not self.config["luck_effects"]:
            return base_duration
            
        # Luck affects duration (higher luck = longer effects)
        luck_modifier = (float(luck) - 50) / 100
        return max(1, base_duration + int(luck_modifier * 2))
    
    def get_combatant_status_text(self, combatant):
        """Get text showing active status effects for a combatant"""
        status_text = combatant.get_status_effects_display()
        if status_text:
            return f"Status: {status_text}"
        return ""
    
    def get_chance_to_apply_effect(self, effect_type, source=None, target=None, base_chance=0.25):
        """Determine if an effect should be applied based on chance"""
        # Check if effects are enabled
        if not self.config.get("status_effects", True):
            return False
            
        # Get modified chance based on luck
        chance = base_chance
        if source and target:
            chance = self.get_effect_chance(source, target, base_chance)
            
        # Roll for effect
        return random.random() < chance
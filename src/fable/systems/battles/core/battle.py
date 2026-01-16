# battles/core/battle.py
from abc import ABC, abstractmethod
import asyncio
import datetime
import uuid
from collections import deque
from decimal import Decimal
import random
from typing import List, Dict, Optional, Union, Any
import json

class DecimalEncoder(json.JSONEncoder):
    """Custom JSON encoder that handles Decimal objects"""
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        return super().default(obj)

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
        
        # Generate unique battle ID for replay system
        self.battle_id = str(uuid.uuid4())
        self.battle_type = self.__class__.__name__
        
        # Enhanced replay system - store turn-by-turn states
        self.turn_states = []  # List of detailed battle states per turn
        self.initial_state = None  # Store initial battle state
        
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
        
        # Capture detailed state for live replay
        await self.capture_turn_state(message)
    
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
    
    # ----- Battle Replay System Methods -----
    
    def get_participants(self):
        """Get list of participant user IDs for replay storage"""
        participants = []
        for team in self.teams:
            for combatant in team.combatants:
                # Check if combatant.user is a Discord User object with an ID
                if hasattr(combatant, 'user') and hasattr(combatant.user, 'id'):
                    participants.append(combatant.user.id)
                # Also check for direct user_id attribute (backup)
                elif hasattr(combatant, 'user_id') and combatant.user_id:
                    participants.append(combatant.user_id)
        return participants
    
    def serialize_battle_data(self):
        """Serialize battle data for storage"""
        return {
            'battle_id': self.battle_id,
            'battle_type': self.battle_type,
            'participants': self.get_participants(),
            'start_time': self.start_time.isoformat() if self.start_time else None,
            'config': self.config,
            'teams_data': [],
            'action_number': self.action_number,
            'finished': self.finished,
            'winner': self.winner
        }
    
    def serialize_battle_log(self):
        """Serialize battle log for storage"""
        return list(self.log)
    
    async def save_battle_to_database(self):
        """Save battle data to database for replay"""
        try:
            # Initialize the battle_replays table if it doesn't exist
            await self.initialize_replay_table()
            
            battle_data = await self.serialize_enhanced_battle_data()
            battle_log = self.serialize_battle_log()
            participants = self.get_participants()
            
            async with self.bot.pool.acquire() as conn:
                # Check if this battle already exists (upsert logic)
                existing = await conn.fetchrow(
                    "SELECT battle_id FROM battle_replays WHERE battle_id = $1",
                    self.battle_id
                )
                
                if existing:
                    # Update existing record
                    await conn.execute(
                        """
                        UPDATE battle_replays SET 
                            participants = $2, battle_data = $3, battle_log = $4
                        WHERE battle_id = $1
                        """,
                        self.battle_id,
                        json.dumps(participants, cls=DecimalEncoder),
                        json.dumps(battle_data, cls=DecimalEncoder),
                        json.dumps(battle_log, cls=DecimalEncoder)
                    )
                else:
                    # Insert new record
                    await conn.execute(
                        """
                        INSERT INTO battle_replays (
                            battle_id, battle_type, participants, battle_data, battle_log, created_at
                        ) VALUES ($1, $2, $3, $4, $5, $6)
                        """,
                        self.battle_id,
                        self.battle_type,
                        json.dumps(participants, cls=DecimalEncoder),
                        json.dumps(battle_data, cls=DecimalEncoder),
                        json.dumps(battle_log, cls=DecimalEncoder),
                        datetime.datetime.utcnow()
                    )
                
        except Exception as e:
            # Don't let replay saving break the battle
            print(f"Error saving battle replay {self.battle_id}: {e}")
            import traceback
            traceback.print_exc()
    
    async def initialize_replay_table(self):
        """Initialize the battle_replays table if it doesn't exist"""
        try:
            async with self.bot.pool.acquire() as conn:
                await conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS battle_replays (
                        battle_id VARCHAR(36) PRIMARY KEY,
                        battle_type VARCHAR(50) NOT NULL,
                        participants JSONB NOT NULL,
                        battle_data JSONB NOT NULL,
                        battle_log JSONB NOT NULL,
                        created_at TIMESTAMP NOT NULL,
                        CONSTRAINT unique_battle_id UNIQUE (battle_id)
                    )
                    """
                )
                
                # Create indexes for better performance
                await conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_battle_replays_type ON battle_replays (battle_type)"
                )
                await conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_battle_replays_created_at ON battle_replays (created_at)"
                )
        except Exception as e:
            print(f"Error initializing battle replay table: {e}")
    
    @staticmethod
    async def get_battle_replay(bot, battle_id):
        """Retrieve battle replay data by ID"""
        try:
            async with bot.pool.acquire() as conn:
                row = await conn.fetchrow(
                    "SELECT * FROM battle_replays WHERE battle_id = $1",
                    battle_id
                )
                
                if row:
                    return {
                        'battle_id': row['battle_id'],
                        'battle_type': row['battle_type'],
                        'participants': json.loads(row['participants']),
                        'battle_data': json.loads(row['battle_data']),
                        'battle_log': json.loads(row['battle_log']),
                        'created_at': row['created_at']
                    }
                return None
        except Exception as e:
            print(f"Error retrieving battle replay {battle_id}: {e}")
            return None
    
    # ----- Enhanced Live Replay System Methods -----
    
    async def capture_turn_state(self, action_message):
        """Capture detailed battle state for live replay"""
        try:
            # Create a snapshot of current battle state
            state = {
                'action_number': self.action_number,
                'action_message': action_message,
                'timestamp': datetime.datetime.utcnow().isoformat(),
                'teams': []
            }
            

            
            # Capture detailed state for each team and combatant
            for team_idx, team in enumerate(self.teams):
                team_state = {
                    'team_index': team_idx,
                    'combatants': []
                }
                
                for combatant in team.combatants:
                    # Get user ID properly
                    user_id = None
                    if hasattr(combatant, 'user') and hasattr(combatant.user, 'id'):
                        user_id = combatant.user.id
                    elif hasattr(combatant, 'user_id'):
                        user_id = combatant.user_id
                    
                    # Get correct name and display name for pets vs players vs dragons
                    if getattr(combatant, 'is_pet', False):
                        # For pets, use the pet's actual name
                        actual_name = combatant.name
                        display_name = combatant.name
                        pet_name = combatant.name  # This is the actual pet name
                    elif hasattr(combatant, 'user') and hasattr(combatant.user, 'display_name'):
                        # For players with Discord User objects
                        actual_name = combatant.user.display_name
                        display_name = getattr(combatant, 'display_name', actual_name)
                        pet_name = None
                    else:
                        # For dragons or other combatants without proper user objects
                        actual_name = getattr(combatant, 'name', str(combatant.user) if hasattr(combatant, 'user') else 'Unknown')
                        display_name = getattr(combatant, 'display_name', actual_name)
                        pet_name = None
                    
                    # Get element emoji for this combatant
                    element_emoji = "❓"
                    if hasattr(combatant, 'element') and combatant.element:
                        # Get element emoji mapping from Battles cog
                        if hasattr(self.ctx.bot.cogs["Battles"], "emoji_to_element"):
                            emoji_to_element = self.ctx.bot.cogs["Battles"].emoji_to_element
                            element_to_emoji = {v: k for k, v in emoji_to_element.items()}
                            element_emoji = element_to_emoji.get(combatant.element, "❓")
                    
                    combatant_state = {
                        'name': actual_name,
                        'display_name': display_name,
                        'pet_name': pet_name,  # Include pet_name for compatibility
                        'current_hp': float(combatant.hp),
                        'max_hp': float(combatant.max_hp),
                        'hp_percentage': float(combatant.hp) / float(combatant.max_hp) if combatant.max_hp > 0 else 0,
                        'element': getattr(combatant, 'element', 'none'),  # Store element as-is (capitalized)
                        'element_emoji': element_emoji,  # Store the actual emoji
                        'is_alive': combatant.is_alive(),
                        'is_pet': getattr(combatant, 'is_pet', False),
                        'damage_reflection': getattr(combatant, 'damage_reflection', 0),
                        'user_id': user_id
                    }
                    
                    # Capture status effects if available
                    if hasattr(combatant, 'status_effects'):
                        combatant_state['status_effects'] = []
                        for effect in combatant.status_effects:
                            effect_state = {
                                'name': getattr(effect, 'name', 'Unknown Effect'),
                                'duration': getattr(effect, 'duration', 0),
                                'stacks': getattr(effect, 'stacks', 1)
                            }
                            combatant_state['status_effects'].append(effect_state)
                    else:
                        combatant_state['status_effects'] = []
                    
                    team_state['combatants'].append(combatant_state)
                
                state['teams'].append(team_state)
            
            # Add battle-specific state information
            state['battle_info'] = {
                'started': self.started,
                'finished': self.finished,
                'winner': self.winner,
                'battle_type': self.battle_type,
                'config': self.config.copy()
            }
            
            # Add special state for specific battle types
            if hasattr(self, 'current_turn'):
                state['battle_info']['current_turn'] = self.current_turn
            if hasattr(self, 'level'):
                state['battle_info']['level'] = self.level
            if hasattr(self, 'current_opponent_index'):
                state['battle_info']['current_opponent_index'] = self.current_opponent_index
            
            self.turn_states.append(state)
            
            # Store initial state if this is the first capture
            if self.initial_state is None:
                self.initial_state = state.copy()
                
        except Exception as e:
            # Don't let state capture break battles
            print(f"Error capturing turn state for battle {self.battle_id}: {e}")
            import traceback
            traceback.print_exc()
    
    async def serialize_enhanced_battle_data(self):
        """Serialize enhanced battle data including turn states"""
        base_data = self.serialize_battle_data()
        base_data['turn_states'] = self.turn_states
        base_data['initial_state'] = self.initial_state
        base_data['has_enhanced_replay'] = True
        

        
        return base_data
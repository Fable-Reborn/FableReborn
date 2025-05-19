# battles/core/combatant.py
from decimal import Decimal
from typing import List, Dict, Any, Optional, Union

class Combatant:
    """Represents any entity that can fight in a battle"""
    
    def __init__(self, user, hp, max_hp, damage, armor, element=None, **kwargs):
        self.user = user  # Can be Discord User object or string name for NPCs
        self.hp = Decimal(str(hp))
        self.max_hp = Decimal(str(max_hp))
        self.damage = Decimal(str(damage))
        self.armor = Decimal(str(armor))
        self.element = element or "Unknown"
        self.is_pet = kwargs.get("is_pet", False)
        self.owner = kwargs.get("owner", None)  # For pets
        self.luck = Decimal(str(kwargs.get("luck", 50)))
        self.name = kwargs.get("name", getattr(user, "display_name", str(user)))
        
        # Class-specific abilities
        self.lifesteal_percent = Decimal(str(kwargs.get("lifesteal_percent", 0)))
        self.death_cheat_chance = Decimal(str(kwargs.get("death_cheat_chance", 0)))
        self.mage_evolution = kwargs.get("mage_evolution", None)
        self.tank_evolution = kwargs.get("tank_evolution", None)
        self.damage_reflection = Decimal(str(kwargs.get("damage_reflection", 0)))
        self.has_shield = kwargs.get("has_shield", False)
        self.has_cheated_death = False
        
        # Status effects system
        self.status_effects = []
        
        # Additional attributes
        for key, value in kwargs.items():
            if not hasattr(self, key):
                setattr(self, key, value)
    
    def is_alive(self):
        """Check if combatant has HP remaining"""
        return self.hp > 0
    
    def take_damage(self, amount):
        """Apply damage to the combatant, accounting for shields"""
        damage = Decimal(str(amount))
        
        # Check if combatant has shield attribute
        if hasattr(self, 'shield') and self.shield > 0:
            # Shield absorbs damage first
            absorbed = min(self.shield, damage)
            self.shield -= absorbed
            damage -= absorbed
            
            # If shield went negative (shouldn't happen), reset to 0
            if self.shield < 0:
                self.shield = Decimal('0')
        
        # Apply remaining damage to HP
        if damage > 0:
            self.hp -= damage
            if self.hp < 0:
                self.hp = Decimal('0')
                
        return self.hp
    
    def heal(self, amount):
        """Heal the combatant by the specified amount"""
        self.hp += Decimal(str(amount))
        if self.hp > self.max_hp:
            self.hp = self.max_hp
        return self.hp
    
    def __str__(self):
        """String representation of the combatant"""
        return f"{self.name} ({self.hp}/{self.max_hp} HP)"
        
    @property
    def display_name(self):
        """Get display name for the combatant"""
        if hasattr(self.user, "display_name"):
            return self.user.display_name
        return self.name
        
    # Status Effect Management Methods
    def add_status_effect(self, effect):
        """Add a status effect to this combatant"""
        # Check for existing effects of the same type to stack
        for existing in self.status_effects:
            if existing.can_stack_with(effect):
                existing.stack_with(effect)
                return existing
        
        # Add as a new effect
        self.status_effects.append(effect)
        effect.target = self
        return effect
    
    def remove_status_effect(self, effect):
        """Remove a specific status effect"""
        if effect in self.status_effects:
            self.status_effects.remove(effect)
            return True
        return False
    
    def remove_effects_by_tag(self, tag):
        """Remove all effects with a specific tag"""
        removed = []
        for effect in list(self.status_effects):
            if tag in effect.tags:
                self.status_effects.remove(effect)
                effect.on_remove()
                removed.append(effect)
        return removed
    
    def clear_status_effects(self):
        """Remove all status effects"""
        for effect in list(self.status_effects):
            effect.on_remove()
        self.status_effects = []
    
    def process_status_effects(self):
        """Process all status effects, removing expired ones"""
        messages = []
        for effect in list(self.status_effects):
            # Tick down duration
            if not effect.tick():
                # Effect expired
                self.status_effects.remove(effect)
                effect.on_remove()
                messages.append(f"{effect.name} has expired from {self.name}")
            else:
                # Check for on_tick events
                effect.on_tick()
        return messages
    
    def process_turn_start_effects(self):
        """Process effects that trigger at the start of a turn"""
        messages = []
        for effect in list(self.status_effects):
            result = effect.on_turn_start()
            if result:
                messages.append(result)
        return messages
    
    def process_turn_end_effects(self):
        """Process effects that trigger at the end of a turn"""
        messages = []
        for effect in list(self.status_effects):
            result = effect.on_turn_end()
            if result:
                messages.append(result)
        return messages
    
    def can_act(self):
        """Check if this combatant can take actions based on status effects"""
        for effect in self.status_effects:
            if not effect.can_act():
                return False
        return True
    
    def get_outgoing_damage(self, base_damage, target):
        """Calculate final outgoing damage after status effect modifications"""
        damage = Decimal(str(base_damage))
        for effect in self.status_effects:
            damage = effect.modify_outgoing_damage(damage, target)
        return damage
    
    def get_incoming_damage(self, damage, source):
        """Calculate final incoming damage after status effect modifications"""
        modified_damage = Decimal(str(damage))
        for effect in self.status_effects:
            modified_damage = effect.modify_incoming_damage(modified_damage, source)
        return modified_damage
    
    def on_attack(self, target):
        """Trigger effects when this combatant attacks"""
        messages = []
        for effect in list(self.status_effects):
            result = effect.on_attack(target)
            if result:
                messages.append(result)
        return messages
    
    def on_defend(self, attacker):
        """Trigger effects when this combatant is attacked"""
        messages = []
        for effect in list(self.status_effects):
            result = effect.on_defend(attacker)
            if result:
                messages.append(result)
        return messages
    
    def get_status_effects_display(self):
        """Get text displaying all active status effects"""
        if not self.status_effects:
            return ""
        
        effects = [effect.get_display_text() for effect in self.status_effects]
        return ", ".join(effects)
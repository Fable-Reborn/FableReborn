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
        base_element = self._normalize_element(element)
        self.attack_element = self._normalize_element(kwargs.get("attack_element", base_element))
        self.defense_element = self._normalize_element(
            kwargs.get("defense_element", self.attack_element)
        )
        dual_attack_elements = kwargs.get("dual_attack_elements")
        self.dual_attack_elements = None
        if dual_attack_elements:
            normalized_dual_elements = [
                self._normalize_element(dual_element) for dual_element in dual_attack_elements
            ]
            unique_dual_elements = [element for element in normalized_dual_elements if element]
            if len(unique_dual_elements) >= 2 and len(set(unique_dual_elements)) > 1:
                self.dual_attack_elements = unique_dual_elements[:2]
        self._dual_attack_index = 0
        # Keep legacy single-element access for existing systems/UI.
        self.element = self.attack_element
        self.is_pet = kwargs.get("is_pet", False)
        self.owner = kwargs.get("owner", None)  # For pets
        self.luck = Decimal(str(kwargs.get("luck", 50)))
        self.name = kwargs.get("name", getattr(user, "display_name", str(user)))
        self.passives = kwargs.get("passives", [])
        
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

    @staticmethod
    def _normalize_element(element):
        if not element:
            return "Unknown"
        return str(element).strip().capitalize()

    def get_attack_element_for_turn(self):
        if self.dual_attack_elements:
            element = self.dual_attack_elements[self._dual_attack_index % len(self.dual_attack_elements)]
            self._dual_attack_index += 1
            return element
        return self.attack_element

    def get_defense_element(self):
        return self.defense_element or self.attack_element or self.element or "Unknown"
    
    def is_alive(self):
        """Check if combatant has HP remaining"""
        return self.hp > 0
    
    def take_damage(self, amount):
        """Apply damage to the combatant, accounting for shields and immortality"""
        damage = Decimal(str(amount))

        # Consume pending true damage (from effects like Shadow Strike) first.
        pending_true_damage = Decimal('0')
        if hasattr(self, 'pending_true_damage_bypass_shield'):
            try:
                pending_true_damage = Decimal(str(self.pending_true_damage_bypass_shield))
            except Exception:
                pending_true_damage = Decimal('0')
            delattr(self, 'pending_true_damage_bypass_shield')

        if pending_true_damage > 0 and damage > 0:
            true_damage = min(damage, pending_true_damage)
            self._apply_hp_damage(true_damage)
            damage -= true_damage
            if not self.is_alive():
                return self.hp

        # Check if combatant has shield attribute.
        if hasattr(self, 'shield') and self.shield > 0:
            # Shield absorbs damage first
            absorbed = min(self.shield, damage)
            self.shield -= absorbed
            damage -= absorbed
            
            # If shield went negative (shouldn't happen), reset to 0
            if self.shield < 0:
                self.shield = Decimal('0')
        
        # Apply remaining damage to HP.
        if damage > 0:
            self._apply_hp_damage(damage)

        return self.hp

    def _apply_hp_damage(self, damage):
        """Apply direct HP damage without shield absorption."""
        self.hp -= damage
        if self.hp <= 0 and getattr(self, 'water_immortality', False):
            self.hp = Decimal('1')
        elif self.hp < 0:
            self.hp = Decimal('0')
    
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

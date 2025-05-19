# battles/core/status_effect.py
from abc import ABC, abstractmethod
from decimal import Decimal
import random

class StatusEffect(ABC):
    """Base class for all status effects in the battle system"""
    
    def __init__(self, name, description, duration, icon=None, **kwargs):
        """
        Initialize a new status effect
        
        Parameters:
        -----------
        name : str
            The name of the status effect
        description : str
            Description of what the status effect does
        duration : int
            Number of turns the effect lasts, -1 for permanent
        icon : str
            Optional emoji or icon to represent the effect
        **kwargs : dict
            Additional effect-specific parameters
        """
        self.name = name
        self.description = description
        self.duration = duration
        self.icon = icon
        self.stacks = kwargs.get("stacks", 1)
        self.max_stacks = kwargs.get("max_stacks", 1)
        self.target = None  # Will be set when applied to a combatant
        self.source = kwargs.get("source", None)  # Who applied this effect
        self.tags = kwargs.get("tags", [])  # Categories like "poison", "buff", "debuff"
        self.metadata = kwargs  # Store additional data
        
    def __str__(self):
        """String representation of the effect"""
        if self.icon:
            return f"{self.icon} {self.name} ({self.duration} turns)"
        return f"{self.name} ({self.duration} turns)"
    
    def can_stack_with(self, other):
        """Check if this effect can stack with another of the same type"""
        return (type(self) == type(other) and 
                self.stacks < self.max_stacks and 
                other.stacks < other.max_stacks)
    
    def stack_with(self, other):
        """Stack this effect with another of the same type"""
        self.stacks = min(self.stacks + other.stacks, self.max_stacks)
        # Refresh duration if the new one is longer
        if other.duration > self.duration:
            self.duration = other.duration
        return self
    
    def get_display_text(self):
        """Get text to display for this effect"""
        if self.stacks > 1:
            return f"{self.name} ({self.stacks})"
        return self.name
    
    def apply(self, target, source=None):
        """Apply this effect to a target combatant"""
        self.target = target
        if source:
            self.source = source
        
        # Try to apply to the target
        if target and hasattr(target, "add_status_effect"):
            target.add_status_effect(self)
        
        # Call the on_apply hook
        self.on_apply()
        return self
    
    def remove(self):
        """Remove this effect from its target"""
        if self.target and hasattr(self.target, "remove_status_effect"):
            self.target.remove_status_effect(self)
        
        # Call the on_remove hook
        self.on_remove()
        return True
    
    def tick(self):
        """Progress the effect's duration by one turn"""
        if self.duration > 0:
            self.duration -= 1
        return self.duration > 0 or self.duration == -1
    
    def can_act(self):
        """Check if the affected combatant can take actions"""
        return True
    
    # ---- Event hooks that can be overridden by subclasses ----
    
    def on_apply(self):
        """Called when the effect is first applied"""
        pass
    
    def on_remove(self):
        """Called when the effect is removed"""
        pass
    
    def on_tick(self):
        """Called when the duration ticks down"""
        pass
    
    def on_turn_start(self):
        """Hook called at the start of the target's turn"""
        pass
    
    def on_turn_end(self):
        """Hook called at the end of the target's turn"""
        pass
    
    def modify_outgoing_damage(self, damage, target):
        """Modify damage dealt by the target"""
        return damage
    
    def modify_incoming_damage(self, damage, source):
        """Modify damage received by the target"""
        return damage
    
    def on_attack(self, target):
        """Called when the affected combatant attacks"""
        pass
    
    def on_defend(self, attacker):
        """Called when the affected combatant is attacked"""
        pass
    
    def on_heal(self, heal_amount):
        """Called when the affected combatant is healed"""
        return heal_amount
    
    def get_chance_to_apply(self, target):
        """Calculate the chance this effect will apply to the target"""
        # Default implementation - 100% chance
        return 1.0


# ---- Common Effect Implementations ----

class DamageOverTime(StatusEffect):
    """Base class for effects that deal damage each turn"""
    
    def __init__(self, name, description, duration, damage_per_turn, **kwargs):
        super().__init__(name, description, duration, **kwargs)
        self.damage_per_turn = Decimal(str(damage_per_turn))
    
    def on_turn_start(self):
        """Apply the damage at the start of the target's turn"""
        if self.target and self.target.is_alive():
            damage = self.damage_per_turn * Decimal(str(self.stacks))
            self.target.take_damage(damage)
            return f"{self.target.name} takes {damage} damage from {self.name}"
        return None


class StatModifier(StatusEffect):
    """Effect that modifies one or more stats"""
    
    def __init__(self, name, description, duration, modifiers, **kwargs):
        super().__init__(name, description, duration, **kwargs)
        self.modifiers = modifiers  # Dict of stat_name: modifier pairs
        self.applied_mods = {}      # Track original values for cleanup
    
    def on_apply(self):
        """Apply the stat modifications"""
        if not self.target:
            return
            
        for stat, modifier in self.modifiers.items():
            if hasattr(self.target, stat):
                # Store original value for later restoration
                original = getattr(self.target, stat)
                self.applied_mods[stat] = original
                
                # Apply the modification
                if isinstance(modifier, (int, float, Decimal)):
                    # Absolute change
                    new_value = original + Decimal(str(modifier))
                elif isinstance(modifier, tuple) and len(modifier) == 2:
                    # Percentage change (multiplier, min_cap)
                    multiplier, min_cap = modifier
                    new_value = max(original * Decimal(str(multiplier)), Decimal(str(min_cap)))
                else:
                    # Direct replacement
                    new_value = Decimal(str(modifier))
                    
                setattr(self.target, stat, new_value)
    
    def on_remove(self):
        """Restore the original stat values"""
        if not self.target:
            return
            
        for stat, original in self.applied_mods.items():
            if hasattr(self.target, stat):
                setattr(self.target, stat, original)


class ControlEffect(StatusEffect):
    """Effect that controls a combatant's actions"""
    
    def __init__(self, name, description, duration, **kwargs):
        super().__init__(name, description, duration, **kwargs)
        self.can_take_actions = kwargs.get("can_take_actions", False)
    
    def can_act(self):
        """Check if the combatant can take actions"""
        return self.can_take_actions


class Poison(DamageOverTime):
    """Poison effect that deals damage over time"""
    
    def __init__(self, damage_per_turn, duration=3, **kwargs):
        super().__init__(
            name="Poison",
            description="Takes damage at the start of each turn",
            duration=duration,
            damage_per_turn=damage_per_turn,
            icon="☠️",
            tags=["poison", "debuff"],
            **kwargs
        )


class Burn(DamageOverTime):
    """Burn effect that deals damage over time and reduces defense"""
    
    def __init__(self, damage_per_turn, duration=3, **kwargs):
        super().__init__(
            name="Burn",
            description="Takes damage and reduces defense",
            duration=duration,
            damage_per_turn=damage_per_turn,
            icon="🔥",
            tags=["burn", "debuff"],
            **kwargs
        )
        # 10% defense reduction
        self.defense_reduction = kwargs.get("defense_reduction", 0.1)
        
    def on_apply(self):
        """Apply defense reduction"""
        if self.target and hasattr(self.target, "armor"):
            self.original_armor = self.target.armor
            self.target.armor = self.target.armor * (1 - Decimal(str(self.defense_reduction)))
    
    def on_remove(self):
        """Restore original defense"""
        if self.target and hasattr(self.target, "armor"):
            self.target.armor = self.original_armor


class Stun(ControlEffect):
    """Stun effect that prevents actions"""
    
    def __init__(self, duration=1, **kwargs):
        super().__init__(
            name="Stun",
            description="Cannot take actions",
            duration=duration,
            can_take_actions=False,
            icon="⚡",
            tags=["stun", "control", "debuff"],
            **kwargs
        )


class DamageBoost(StatModifier):
    """Increases damage output"""
    
    def __init__(self, percentage=0.2, duration=3, **kwargs):
        super().__init__(
            name="Damage Boost",
            description=f"Increases damage by {int(percentage*100)}%",
            duration=duration,
            modifiers={"damage": (1 + Decimal(str(percentage)), 0)},
            icon="💪",
            tags=["buff"],
            **kwargs
        )


class DefenseBoost(StatModifier):
    """Increases armor"""
    
    def __init__(self, percentage=0.2, duration=3, **kwargs):
        super().__init__(
            name="Defense Boost",
            description=f"Increases armor by {int(percentage*100)}%",
            duration=duration,
            modifiers={"armor": (1 + Decimal(str(percentage)), 0)},
            icon="🛡️",
            tags=["buff"],
            **kwargs
        )


class Regen(StatusEffect):
    """Regenerates health over time"""
    
    def __init__(self, heal_per_turn, duration=3, **kwargs):
        super().__init__(
            name="Regeneration",
            description="Regenerates health each turn",
            duration=duration,
            icon="💚",
            tags=["heal", "buff"],
            **kwargs
        )
        self.heal_per_turn = Decimal(str(heal_per_turn))
    
    def on_turn_start(self):
        """Apply healing at the start of the turn"""
        if self.target and self.target.is_alive():
            heal_amount = self.heal_per_turn * Decimal(str(self.stacks))
            self.target.heal(heal_amount)
            return f"{self.target.name} regenerates {heal_amount} HP"
        return None


class BleedingWound(DamageOverTime):
    """Causes bleeding damage that increases when the target takes more damage"""
    
    def __init__(self, damage_per_turn, duration=3, **kwargs):
        super().__init__(
            name="Bleeding Wound",
            description="Takes increasing damage when hit",
            duration=duration,
            damage_per_turn=damage_per_turn,
            icon="🩸",
            tags=["bleed", "debuff"],
            max_stacks=3,
            **kwargs
        )
    
    def on_defend(self, attacker):
        """Increase stacks when hit"""
        if self.stacks < self.max_stacks and random.random() < 0.33:
            self.stacks += 1
            return f"{self.target.name}'s bleeding wound worsens!"
        return None


class StatusEffectRegistry:
    """Registry of available status effects for easy access"""
    
    EFFECTS = {
        "poison": Poison,
        "burn": Burn,
        "stun": Stun,
        "damage_boost": DamageBoost,
        "defense_boost": DefenseBoost,
        "regen": Regen,
        "bleeding": BleedingWound
    }
    
    @classmethod
    def create(cls, effect_type, **kwargs):
        """Create a status effect of the specified type"""
        if effect_type in cls.EFFECTS:
            return cls.EFFECTS[effect_type](**kwargs)
        raise ValueError(f"Unknown effect type: {effect_type}")
    
    @classmethod
    def register(cls, effect_id, effect_class):
        """Register a new effect type"""
        cls.EFFECTS[effect_id] = effect_class
        return effect_class

# battles/extensions/pets.py
from ..core.combatant import Combatant
from decimal import Decimal
import random
import datetime

class PetExtension:
    """Extension for pet integration in battles"""
    PET_MAX_LEVEL = 100
    PET_LEVEL_STAT_BONUS = 0.01
    PASSIVE_ALLY_HEAL_CAP = Decimal('0.12')
    PASSIVE_SELF_HEAL_CAP = Decimal('0.18')
    BURST_HEAL_CAP = Decimal('0.40')
    LIGHTS_GUIDANCE_PROC_CHANCE = 0.25
    LIGHTS_GUIDANCE_OFFENSIVE_TYPES = {
        'aoe_attack',
        'apply_burn',
        'blind',
        'bypass_defenses',
        'buff_transfer',
        'chain_attack',
        'chain_critical',
        'chaos_aoe',
        'chaos_mastery',
        'conditional_passive',
        'defense_debuff',
        'delay_enemy',
        'desperation_power',
        'dispel_on_hit',
        'duplicate_attack',
        'elemental_bonus',
        'enemy_debuff',
        'execute',
        'execute_heal',
        'happiness_damage',
        'hp_based_damage',
        'ignore_armor',
        'initiative_control',
        'lifesteal',
        'lifesteal_to_owner',
        'on_attack',
        'on_critical',
        'owner_buff_on_attack',
        'owner_heal_on_attack',
        'paralyze',
        'partial_true_damage',
        'permanent_debuff',
        'persistent_aoe',
        'persistent_void',
        'push_back',
        'random_attack',
        'random_team_buff',
        'reality_control',
        'reality_manipulation',
        'spreading_debuff',
        'stacking_damage',
        'stun',
        'teleport_attack',
        'ultimate',
        'universal_bonus',
        'void_attack',
    }
    LIGHTS_GUIDANCE_OFFENSIVE_SKILLS = {
        'burning_rage',
        'corrupted_affinity',
        'dark_affinity',
        'electric_affinity',
        'fire_affinity',
        'inferno_mastery',
        'light_affinity',
        'nature_affinity',
        'natures_fury',
        'shadow_step',
        'void_affinity',
        'water_affinity',
    }
    LIGHTS_GUIDANCE_REACTIVE_TYPES = {
        'absorb_convert',
        'absorb_corrupt',
        'avoid_targeting',
        'block_attack',
        'damage_redistribution',
        'damage_reduction',
        'damage_transfer',
        'defensive_corruption',
        'dodge',
        'enhanced_vision',
        'owner_sharing',
        'phase_dodge',
        'poison_reflect',
        'positioning',
        'resistance',
        'revive',
        'sacrifice_save',
        'selective_defense',
        'shield',
    }
    LIGHTS_GUIDANCE_REACTIVE_SKILLS = {
        'lightning_rod',
        'molten_armor',
        'symbiotic_bond',
        'thorn_shield',
    }

    @staticmethod
    def _extract_user_id(entity):
        """Resolve a Discord user ID from combatant/user/raw-id values."""
        if entity is None:
            return None

        # Combatants store the discord user object in `user`.
        if hasattr(entity, 'user'):
            entity = getattr(entity, 'user', None)

        user_id = getattr(entity, 'id', None)
        if user_id is not None:
            return user_id

        if isinstance(entity, int):
            return entity

        if isinstance(entity, str):
            cleaned = entity.strip()
            if cleaned.isdigit():
                return int(cleaned)

        return None
    
    def find_owner_combatant(self, pet_combatant):
        """Find and cache the owner combatant object associated with a pet."""
        if not hasattr(pet_combatant, 'owner'):
            return None

        owner_id = self._extract_user_id(getattr(pet_combatant, 'owner', None))
        if owner_id is None:
            # Fallback to pet user id in case owner was serialized oddly.
            owner_id = self._extract_user_id(getattr(pet_combatant, 'user', None))

        teams_to_search = []
        team = getattr(pet_combatant, 'team', None)
        enemy_team = getattr(pet_combatant, 'enemy_team', None)

        if hasattr(team, 'combatants'):
            teams_to_search.append(team)
        if hasattr(enemy_team, 'combatants') and enemy_team is not team:
            teams_to_search.append(enemy_team)

        for team_ref in teams_to_search:
            for combatant in team_ref.combatants:
                if getattr(combatant, 'is_pet', False):
                    continue

                combatant_id = self._extract_user_id(combatant)
                if owner_id is not None and combatant_id == owner_id:
                    # Normalize owner reference to the runtime combatant object.
                    pet_combatant.owner = combatant
                    return combatant

        return None
    
    def get_trust_bonus(self, trust_level):
        """Calculate trust bonus based on trust level"""
        if trust_level >= 81:
            return 0.10  # Devoted: +10%
        elif trust_level >= 61:
            return 0.08  # Loyal: +8%
        elif trust_level >= 41:
            return 0.05  # Trusting: +5%
        elif trust_level >= 21:
            return 0.0   # Cautious: +0%
        else:
            return -0.10  # Distrustful: -10%

    @staticmethod
    def _format_skill_name(skill_name):
        """Convert internal skill ids into readable battle-log text."""
        return str(skill_name).replace('_', ' ')

    def _get_lights_guidance_candidates(self, skill_effects, allowed_types, allowed_skills):
        """Collect only skills that can reasonably affect the current hit exchange."""
        if not isinstance(skill_effects, dict):
            return []

        candidates = []
        for skill_name, skill_data in skill_effects.items():
            if skill_name == 'lights_guidance':
                continue

            skill_type = skill_data.get('type') if isinstance(skill_data, dict) else None
            if skill_name in allowed_skills or skill_type in allowed_types:
                candidates.append(skill_name)

        return candidates

    def _has_exchange_reflection(self, combatant):
        """Check whether the defender can reflect blocked damage on this hit."""
        if combatant is None:
            return False

        try:
            reflection_value = Decimal(str(getattr(combatant, 'damage_reflection', 0)))
        except Exception:
            reflection_value = Decimal('0')

        if reflection_value > 0:
            return True

        return bool(getattr(combatant, 'tank_evolution', None) and not getattr(combatant, 'is_pet', False))

    @staticmethod
    def _to_decimal(value, default='0'):
        try:
            return Decimal(str(value))
        except Exception:
            return Decimal(str(default))

    def _scaled_heal(self, source, target, percent, *, burst=False, self_target=False):
        source_hp = self._to_decimal(getattr(source, 'max_hp', 0))
        target_hp = self._to_decimal(getattr(target, 'max_hp', source_hp))
        heal_percent = self._to_decimal(percent)

        scale_base = source_hp if self_target else min(source_hp, target_hp)
        heal_amount = scale_base * heal_percent

        if burst:
            heal_cap = target_hp * self.BURST_HEAL_CAP
        elif self_target:
            heal_cap = target_hp * self.PASSIVE_SELF_HEAL_CAP
        else:
            heal_cap = target_hp * self.PASSIVE_ALLY_HEAL_CAP

        return max(Decimal('0'), min(heal_amount, heal_cap))

    def _apply_timed_multiplier(
        self,
        target,
        effect_key,
        duration,
        *,
        damage_mult=1,
        armor_mult=1,
        luck_mult=1,
        extra_attrs=None,
    ):
        duration_attr = f'{effect_key}_duration'
        setattr(target, duration_attr, max(int(getattr(target, duration_attr, 0) or 0), int(duration)))

        stat_multipliers = {
            'damage': self._to_decimal(damage_mult, '1'),
            'armor': self._to_decimal(armor_mult, '1'),
            'luck': self._to_decimal(luck_mult, '1'),
        }

        for stat_name, multiplier in stat_multipliers.items():
            if multiplier == Decimal('1'):
                continue
            mult_attr = f'{effect_key}_{stat_name}_mult'
            if hasattr(target, mult_attr):
                continue
            current_value = self._to_decimal(getattr(target, stat_name, 0))
            setattr(target, stat_name, current_value * multiplier)
            setattr(target, mult_attr, multiplier)

        for attr_name, attr_value in (extra_attrs or {}).items():
            setattr(target, attr_name, attr_value)

    def _clear_timed_multiplier(self, target, effect_key, extra_attrs=None):
        for stat_name in ('damage', 'armor', 'luck'):
            mult_attr = f'{effect_key}_{stat_name}_mult'
            if not hasattr(target, mult_attr):
                continue
            multiplier = self._to_decimal(getattr(target, mult_attr), '1')
            if multiplier != 0:
                current_value = self._to_decimal(getattr(target, stat_name, 0))
                setattr(target, stat_name, current_value / multiplier)
            delattr(target, mult_attr)

        duration_attr = f'{effect_key}_duration'
        if hasattr(target, duration_attr):
            delattr(target, duration_attr)

        for attr_name in extra_attrs or []:
            if hasattr(target, attr_name):
                delattr(target, attr_name)

    def _tick_timed_multiplier(self, target, effect_key, messages, *, fade_message=None, extra_attrs=None):
        duration_attr = f'{effect_key}_duration'
        turns_left = int(getattr(target, duration_attr, 0) or 0)
        if turns_left <= 0:
            return

        if turns_left <= 1:
            self._clear_timed_multiplier(target, effect_key, extra_attrs=extra_attrs)
            if fade_message:
                messages.append(fade_message)
            return

        setattr(target, duration_attr, turns_left - 1)

    def _tick_simple_duration(self, target, attr_name, messages, *, fade_message=None, clear_attrs=None):
        turns_left = int(getattr(target, attr_name, 0) or 0)
        if turns_left <= 0:
            return

        if turns_left <= 1:
            delattr(target, attr_name)
            for clear_attr in clear_attrs or []:
                if hasattr(target, clear_attr):
                    delattr(target, clear_attr)
            if fade_message:
                messages.append(fade_message)
            return

        setattr(target, attr_name, turns_left - 1)

    def _restore_barrier(self, combatant, barrier_attr, multiplier, restore_ratio=1):
        barrier_value = (
            self._to_decimal(getattr(combatant, 'armor', 0))
            * self._to_decimal(multiplier)
            * self._to_decimal(restore_ratio, '1')
        )
        setattr(combatant, barrier_attr, max(Decimal('0'), barrier_value))
        return getattr(combatant, barrier_attr)

    def _tick_barrier_recharge(
        self,
        combatant,
        barrier_attr,
        recharge_attr,
        multiplier,
        restore_ratio,
        messages,
        label,
    ):
        turns_left = int(getattr(combatant, recharge_attr, 0) or 0)
        if turns_left <= 0:
            return

        if turns_left <= 1:
            restored = self._restore_barrier(combatant, barrier_attr, multiplier, restore_ratio)
            delattr(combatant, recharge_attr)
            messages.append(
                f"{combatant.name}'s {label} recharges to **{restored:.2f} shield**!"
            )
            return

        setattr(combatant, recharge_attr, turns_left - 1)

    def process_skill_effects_on_death(self, pet_combatant):
        """Resolve pet death triggers exactly once."""
        if not hasattr(pet_combatant, 'skill_effects'):
            return []

        effects = pet_combatant.skill_effects
        messages = []

        if 'dark_shield' in effects:
            self._clear_timed_multiplier(pet_combatant, 'dark_shield')
        if 'flame_barrier' in effects:
            for attr_name in ('flame_shield', 'flame_shield_recharge'):
                if hasattr(pet_combatant, attr_name):
                    delattr(pet_combatant, attr_name)
        if 'energy_shield' in effects:
            for attr_name in ('energy_barrier', 'energy_barrier_recharge'):
                if hasattr(pet_combatant, attr_name):
                    delattr(pet_combatant, attr_name)
        if 'growth_spurt' in effects:
            self._clear_timed_multiplier(pet_combatant, 'growth_spurt')
        if 'phoenix_rebirth' in effects:
            self._clear_timed_multiplier(pet_combatant, 'phoenix_rebirth')
        if 'dark_ritual' in effects:
            self._clear_timed_multiplier(pet_combatant, 'dark_ritual', extra_attrs=['dark_ritual_lifesteal'])

        if (
            'combustion' in effects
            and not getattr(pet_combatant, 'combustion_triggered', False)
            and hasattr(pet_combatant, 'enemy_team')
        ):
            explosion_damage = pet_combatant.damage * self._to_decimal(
                effects['combustion']['damage_multiplier']
            )
            enemies_hit = 0
            for enemy in pet_combatant.enemy_team.combatants:
                if enemy.is_alive():
                    enemy.take_damage(explosion_damage)
                    enemies_hit += 1

            setattr(pet_combatant, 'combustion_triggered', True)
            if enemies_hit > 0:
                messages.append(
                    f"💥 {pet_combatant.name} detonates with Combustion! "
                    f"{enemies_hit} enemies take **{explosion_damage:.2f} damage**."
                )

        owner_combatant = self.find_owner_combatant(pet_combatant)
        if owner_combatant:
            if 'power_surge' in effects:
                self._clear_timed_multiplier(owner_combatant, 'power_surge')
            if 'overcharge' in effects:
                self._clear_timed_multiplier(owner_combatant, 'overcharge', extra_attrs=['overcharge_active'])
            if 'dark_pact' in effects:
                self._clear_timed_multiplier(owner_combatant, 'dark_pact', extra_attrs=['dark_pact_active'])
            if 'void_lord' in effects:
                self._clear_timed_multiplier(owner_combatant, 'void_lord_blessing')
            if 'void_mastery_corrupted' in effects:
                self._clear_timed_multiplier(owner_combatant, 'void_mastery_reality')
            if 'immortal_waters' in effects and hasattr(owner_combatant, 'water_immortality_duration'):
                delattr(owner_combatant, 'water_immortality_duration')
            if 'immortal_waters' in effects and hasattr(owner_combatant, 'water_immortality'):
                delattr(owner_combatant, 'water_immortality')

        for ally in getattr(getattr(pet_combatant, 'team', None), 'combatants', []):
            if 'inferno_mastery' in effects:
                self._clear_timed_multiplier(ally, 'inferno_mastery_aura')
            if 'sun_gods_blessing' in effects:
                self._clear_timed_multiplier(ally, 'sun_gods_blessing')
            if 'poseidons_call' in effects:
                self._clear_timed_multiplier(ally, 'poseidons_call')
            if 'storm_lord' in effects:
                self._clear_timed_multiplier(ally, 'storm_lord')
                for attr_name in ('storm_lord_haste',):
                    if hasattr(ally, attr_name):
                        delattr(ally, attr_name)
            if 'infinite_energy' in effects:
                self._clear_timed_multiplier(ally, 'infinite_energy', extra_attrs=['unlimited_abilities'])
            if 'zeus_wrath' in effects:
                self._clear_timed_multiplier(ally, 'zeus_wrath')
                for attr_name in ('debuff_immunity', 'zeus_protection'):
                    if hasattr(ally, attr_name):
                        delattr(ally, attr_name)
            if 'natures_blessing' in effects:
                self._clear_timed_multiplier(ally, 'natures_blessing')
            if 'world_trees_gift' in effects:
                self._clear_timed_multiplier(ally, 'world_trees_gift')
            if 'lord_of_shadows' in effects:
                self._clear_timed_multiplier(ally, 'lord_of_shadows')
            if 'air_currents' in effects:
                self._clear_timed_multiplier(ally, 'air_currents')
                for attr_name in ('air_currents_duration', 'air_currents_boost'):
                    if hasattr(ally, attr_name):
                        delattr(ally, attr_name)
            if 'freedoms_call' in effects:
                self._clear_timed_multiplier(ally, 'freedoms_call')
                for attr_name in ('freedom_boost_duration', 'freedom_boost'):
                    if hasattr(ally, attr_name):
                        delattr(ally, attr_name)
            if 'void_pact' in effects:
                self._clear_timed_multiplier(ally, 'void_pact_ally')
            if 'end_of_days' in effects:
                self._clear_timed_multiplier(
                    ally,
                    'end_of_days_blessing',
                    extra_attrs=['chaos_powers', 'chaos_damage_immunity', 'reality_break_stacks'],
                )
            if 'divine_favor' in effects:
                self._clear_timed_multiplier(ally, 'divine_favor_damage')
                self._clear_timed_multiplier(ally, 'divine_favor_armor')
                self._clear_timed_multiplier(ally, 'divine_favor_luck')
            if 'celestial_blessing' in effects:
                self._clear_timed_multiplier(ally, 'celestial_blessing', extra_attrs=['physical_immunity'])
                if hasattr(ally, 'physical_immunity'):
                    delattr(ally, 'physical_immunity')
            if 'eternal_night' in effects:
                self._clear_timed_multiplier(ally, 'eternal_night', extra_attrs=['bonus_lifesteal'])
            if 'skys_blessing' in effects:
                for attr_name in ('sky_dodge_duration', 'sky_dodge'):
                    if hasattr(ally, attr_name):
                        delattr(ally, attr_name)
                for attr_name in ('sky_haste_duration', 'sky_haste'):
                    if hasattr(ally, attr_name):
                        delattr(ally, attr_name)
            if 'zephyrs_dance' in effects:
                self._clear_timed_multiplier(ally, 'zephyrs_dance')
                for attr_name in ('zephyr_speed_duration', 'zephyr_speed'):
                    if hasattr(ally, attr_name):
                        delattr(ally, attr_name)
            if 'storm_lord_wind' in effects:
                self._clear_timed_multiplier(ally, 'storm_lord_wind_ally')
                if hasattr(ally, 'storm_lord_haste'):
                    delattr(ally, 'storm_lord_haste')
            if 'divine_protection' in effects:
                for attr_name in ('divine_invincibility', 'blessed_by_light'):
                    if hasattr(ally, attr_name):
                        delattr(ally, attr_name)
            if 'immortal_growth' in effects:
                for attr_name in ('immortal_growth_duration', 'immortal_growth_regen', 'dot_immunity'):
                    if hasattr(ally, attr_name):
                        delattr(ally, attr_name)

        for enemy in getattr(getattr(pet_combatant, 'enemy_team', None), 'combatants', []):
            if 'decay_touch' in effects:
                self._clear_timed_multiplier(enemy, 'decay_touch')
            if 'world_trees_gift' in effects:
                self._clear_timed_multiplier(enemy, 'world_trees_gift_curse')
            if 'lord_of_shadows' in effects:
                self._clear_timed_multiplier(enemy, 'lord_of_shadows_fear')
            if 'poseidons_call' in effects:
                self._clear_timed_multiplier(enemy, 'poseidons_call_curse')
            if 'electromagnetic_field' in effects:
                self._clear_timed_multiplier(enemy, 'electromagnetic_field')
            if 'gale_force' in effects:
                self._clear_timed_multiplier(enemy, 'gale_force')
            if 'light_beam' in effects:
                self._clear_timed_multiplier(enemy, 'light_beam')
            if 'vine_whip' in effects:
                self._clear_timed_multiplier(enemy, 'vine_whip')
            if 'wind_shear' in effects:
                self._clear_timed_multiplier(enemy, 'wind_shear')
            if 'void_pact' in effects:
                self._clear_timed_multiplier(enemy, 'void_pact_enemy')
            if 'storm_lord_wind' in effects:
                self._clear_timed_multiplier(enemy, 'storm_lord_wind')
                if hasattr(enemy, 'storm_dominated'):
                    delattr(enemy, 'storm_dominated')
            if 'void_mastery' in effects:
                self._clear_timed_multiplier(enemy, 'void_mastery')
            if 'end_of_days' in effects:
                self._clear_timed_multiplier(enemy, 'end_of_days_curse')
                if hasattr(enemy, 'reality_broken'):
                    delattr(enemy, 'reality_broken')
            if 'zephyrs_dance' in effects:
                self._clear_timed_multiplier(enemy, 'zephyrs_dance_slow')
                for attr_name in ('zephyr_slow_duration', 'zephyr_slow'):
                    if hasattr(enemy, attr_name):
                        delattr(enemy, attr_name)

        return messages
    
    def apply_skill_effects(self, pet_combatant, learned_skills):
        """Apply skill effects to pet combatant with actual implementations"""
        if not learned_skills:
            return
            
        # Initialize skill attributes
        pet_combatant.skill_effects = {}
        pet_combatant.passive_effects = []
        pet_combatant.active_abilities = []
        
        # Apply skill effects based on learned skills
        for skill in learned_skills:
            skill_lower = skill.lower()
            
            # 🔥 FIRE SKILLS
            if "flame burst" in skill_lower:
                pet_combatant.skill_effects['flame_burst'] = {
                    'chance': 15, 'damage_multiplier': 1.5, 'type': 'on_attack'
                }
            elif "burning rage" in skill_lower:
                pet_combatant.skill_effects['burning_rage'] = {
                    'hp_threshold': 0.35, 'damage_bonus': 0.20, 'type': 'conditional_passive'
                }
            elif "phoenix strike" in skill_lower:
                pet_combatant.skill_effects['phoenix_strike'] = {
                    'heal_percent': 0.15, 'type': 'on_critical'
                }
            elif "molten armor" in skill_lower:
                pet_combatant.skill_effects['molten_armor'] = {
                    'chance': 20, 'reflect_percent': 0.4, 'type': 'on_damage_taken'
                }
            elif "inferno mastery" in skill_lower:
                pet_combatant.skill_effects['inferno_mastery'] = {
                    'fire_effectiveness': 1.45,
                    'fire_resistance': 0.40,
                    'active_turns': 4,
                    'team_buff': 0.15,
                    'type': 'ultimate',
                }
            elif "warmth" in skill_lower:
                pet_combatant.skill_effects['warmth'] = {
                    'heal_percent': 0.04, 'type': 'owner_heal_on_attack'
                }
            elif "fire shield" in skill_lower:
                pet_combatant.skill_effects['fire_shield'] = {
                    'chance': 18, 'type': 'block_attack'
                }
            elif "combustion" in skill_lower:
                pet_combatant.skill_effects['combustion'] = {
                    'damage_multiplier': 2.0, 'type': 'on_death'
                }
            elif "eternal flame" in skill_lower:
                pet_combatant.skill_effects['eternal_flame'] = {
                    'owner_hp_threshold': 0.5, 'type': 'conditional_immortality'
                }
            elif "phoenix rebirth" in skill_lower:
                pet_combatant.skill_effects['phoenix_rebirth'] = {
                    'revive_hp_percent': 0.60,
                    'uses': 1,
                    'reborn_power': 0.30,
                    'duration': 2,
                    'type': 'revive',
                }
            elif "fire affinity" in skill_lower:
                pet_combatant.skill_effects['fire_affinity'] = {
                    'elements': ['Nature', 'Water'], 'damage_bonus': 0.2, 'type': 'elemental_bonus'
                }
            elif "heat wave" in skill_lower:
                pet_combatant.skill_effects['heat_wave'] = {
                    'aoe_damage_percent': 0.55, 'type': 'aoe_attack'
                }
            elif "flame barrier" in skill_lower:
                pet_combatant.skill_effects['flame_barrier'] = {
                    'shield_multiplier': 2.5,
                    'recharge_turns': 1,
                    'restore_ratio': 0.50,
                    'type': 'shield',
                }
                self._restore_barrier(
                    pet_combatant,
                    'flame_shield',
                    pet_combatant.skill_effects['flame_barrier']['shield_multiplier'],
                )
            elif "burning spirit" in skill_lower:
                pet_combatant.skill_effects['burning_spirit'] = {
                    'chance': 30, 'burn_percent': 0.1, 'duration': 3, 'type': 'apply_burn'
                }
            elif "sun god's blessing" in skill_lower:
                pet_combatant.skill_effects['sun_gods_blessing'] = {
                    'damage_multiplier': 2.75,
                    'team_buff': 0.30,
                    'duration': 3,
                    'burn_duration': 2,
                    'type': 'ultimate',
                }
                
            # 💧 WATER SKILLS
            elif "water jet" in skill_lower:
                pet_combatant.skill_effects['water_jet'] = {
                    'chance': 15, 'type': 'ignore_armor'
                }
            elif "tsunami strike" in skill_lower:
                pet_combatant.skill_effects['tsunami_strike'] = {
                    'hp_scaling': 0.4, 'type': 'hp_based_damage'
                }
            elif "deep pressure" in skill_lower:
                pet_combatant.skill_effects['deep_pressure'] = {
                    'hp_threshold': 0.5, 'damage_bonus': 0.25, 'type': 'execute'
                }
            elif "abyssal grip" in skill_lower:
                pet_combatant.skill_effects['abyssal_grip'] = {
                    'chance': 20, 'duration': 1, 'type': 'stun'
                }
            elif "ocean's wrath" in skill_lower:
                pet_combatant.skill_effects['oceans_wrath'] = {
                    'damage_multiplier': 2.0, 'splash_multiplier': 0.75, 'heal_percent': 0.30, 'type': 'ultimate'
                }
            elif "purify" in skill_lower:
                pet_combatant.skill_effects['purify'] = {
                    'type': 'remove_debuff'
                }
            elif "healing rain" in skill_lower:
                pet_combatant.skill_effects['healing_rain'] = {
                    'heal_percent': 0.05, 'type': 'team_heal_per_turn'
                }
            elif "life spring" in skill_lower:
                pet_combatant.skill_effects['life_spring'] = {
                    'heal_percent': 0.2, 'type': 'lifesteal_to_owner'
                }
            elif "guardian wave" in skill_lower:
                pet_combatant.skill_effects['guardian_wave'] = {
                    'chance': 35, 'damage_reduction': 0.6, 'type': 'damage_reduction'
                }
            elif "immortal waters" in skill_lower:
                pet_combatant.skill_effects['immortal_waters'] = {
                    'duration': 2, 'type': 'owner_immortality'
                }
            elif "water affinity" in skill_lower:
                pet_combatant.skill_effects['water_affinity'] = {
                    'elements': ['Fire', 'Electric'], 'damage_bonus': 0.2, 'type': 'elemental_bonus'
                }
            elif "fluid movement" in skill_lower:
                pet_combatant.skill_effects['fluid_movement'] = {
                    'chance': 20, 'type': 'dodge'
                }
            elif "tidal force" in skill_lower:
                pet_combatant.skill_effects['tidal_force'] = {
                    'turn_delay': 1, 'type': 'delay_enemy'
                }
            elif "ocean's embrace" in skill_lower:
                pet_combatant.skill_effects['oceans_embrace'] = {
                    'damage_share': 0.5, 'type': 'damage_transfer'
                }
            elif "poseidon's call" in skill_lower:
                pet_combatant.skill_effects['poseidons_call'] = {
                    'team_buff': 0.4, 'enemy_debuff': 0.3, 'duration': 6, 'type': 'ultimate'
                }
                
            # ⚡ ELECTRIC SKILLS
            elif "static shock" in skill_lower:
                pet_combatant.skill_effects['static_shock'] = {
                    'chance': 20, 'duration': 1, 'type': 'paralyze'
                }
            elif "thunder strike" in skill_lower:
                pet_combatant.skill_effects['thunder_strike'] = {
                    'chain_count': 2, 'chain_damage': [0.5, 0.5], 'type': 'chain_critical'
                }
            elif "voltage surge" in skill_lower:
                pet_combatant.skill_effects['voltage_surge'] = {
                    'stack_bonus': 0.15, 'max_stacks': 5, 'type': 'stacking_damage'
                }
            elif "lightning rod" in skill_lower:
                pet_combatant.skill_effects['lightning_rod'] = {
                    'absorb_element': 'Electric', 'attack_bonus': 0.25, 'duration': 3, 'type': 'absorb_convert'
                }
            elif "storm lord" in skill_lower:
                # "Storm Lord" exists in both Electric and Wind trees.
                # Resolve by pet element so both contracts map to a runtime effect.
                pet_element = str(getattr(pet_combatant, 'element', '')).lower()
                if pet_element == 'wind':
                    pet_combatant.skill_effects['storm_lord_wind'] = {
                        'damage_multiplier': 2.8,
                        'duration': 3,
                        'battlefield_control': True,
                        'team_buff': 0.15,
                        'storm_damage': 0.45,
                        'enemy_damage_mult': 0.70,
                        'enemy_luck_mult': 0.75,
                        'type': 'ultimate',
                    }
                else:
                    pet_combatant.skill_effects['storm_lord'] = {
                        'damage_multiplier': 3.0, 'team_speed': 0.25, 'duration': 3, 'type': 'ultimate'
                    }
            elif "power surge" in skill_lower:
                pet_combatant.skill_effects['power_surge'] = {
                    'attack_bonus': 0.10, 'duration': 3, 'type': 'owner_buff_on_attack'
                }
            elif "energy shield" in skill_lower:
                pet_combatant.skill_effects['energy_shield'] = {
                    'shield_multiplier': 2.0,
                    'recharge_turns': 1,
                    'restore_ratio': 0.60,
                    'type': 'shield',
                }
                self._restore_barrier(
                    pet_combatant,
                    'energy_barrier',
                    pet_combatant.skill_effects['energy_shield']['shield_multiplier'],
                )
            elif "battery life" in skill_lower:
                # Battery Life is now handled in the pets system for skill learning costs
                # No battle effect needed
                pass
            elif "overcharge" in skill_lower:
                pet_combatant.skill_effects['overcharge'] = {
                    'hp_sacrifice': 0.20, 'owner_buff': 0.35, 'duration': 2, 'type': 'sacrifice_buff'
                }
            elif "infinite energy" in skill_lower:
                pet_combatant.skill_effects['infinite_energy'] = {
                    'team_buff': 0.35, 'unlimited_abilities': True, 'duration': 3, 'type': 'ultimate'
                }
            elif "electric affinity" in skill_lower:
                pet_combatant.skill_effects['electric_affinity'] = {
                    'elements': ['Water', 'Nature'], 'damage_bonus': 0.2, 'type': 'elemental_bonus'
                }
            elif "quick charge" in skill_lower:
                pet_combatant.skill_effects['quick_charge'] = {
                    'speed_multiplier': 1.25, 'type': 'speed_boost'
                }
                # Strong initiative pressure without overriding true priority skills.
                setattr(pet_combatant, 'quick_charge_active', True)
            elif "chain lightning" in skill_lower:
                pet_combatant.skill_effects['chain_lightning'] = {
                    'chain_count': 3, 'chain_damage': [1.0, 0.75, 0.5], 'type': 'chain_attack'
                }
            elif "electromagnetic field" in skill_lower:
                pet_combatant.skill_effects['electromagnetic_field'] = {
                    'accuracy_reduction': 0.15, 'duration': 2, 'type': 'enemy_debuff'
                }
            elif "zeus's wrath" in skill_lower:
                pet_combatant.skill_effects['zeus_wrath'] = {
                    'damage_multiplier': 3.0, 'protection_turns': 3, 'team_protection': True, 'type': 'ultimate'
                }
                
            # 🌿 NATURE SKILLS
            elif "vine whip" in skill_lower:
                pet_combatant.skill_effects['vine_whip'] = {
                    'chance': 20, 'damage_reduction': 0.35, 'duration': 2, 'type': 'root'
                }
            elif "photosynthesis" in skill_lower:
                pet_combatant.skill_effects['photosynthesis'] = {
                    'time_based': True, 'damage_bonus': 0.15, 'type': 'time_conditional'
                }
            elif "nature's fury" in skill_lower:
                pet_combatant.skill_effects['natures_fury'] = {
                    'happiness_scaling': 0.5, 'type': 'happiness_damage'
                }
            elif "thorn shield" in skill_lower:
                pet_combatant.skill_effects['thorn_shield'] = {
                    'reflect_percent': 0.35, 'type': 'poison_reflect'
                }
            elif "gaia's wrath" in skill_lower:
                pet_combatant.skill_effects['gaias_wrath'] = {
                    'damage_multiplier': 2.0, 'team_heal_percent': 0.35, 'heal_per_turn': 0.08, 'duration': 3, 'type': 'ultimate'
                }
            elif "natural healing" in skill_lower:
                pet_combatant.skill_effects['natural_healing'] = {
                    'heal_percent': 0.05, 'type': 'regen_per_turn'
                }
            elif "growth spurt" in skill_lower:
                pet_combatant.skill_effects['growth_spurt'] = {
                    'stat_increase': 0.02, 'max_stacks': 5, 'type': 'stacking_stats'
                }
            elif "life force" in skill_lower:
                pet_combatant.skill_effects['life_force'] = {
                    'hp_sacrifice': 0.20, 'owner_heal': 0.35, 'owner_threshold': 0.60, 'uses': 1, 'type': 'hp_transfer'
                }
            elif "nature's blessing" in skill_lower:
                pet_combatant.skill_effects['natures_blessing'] = {
                    'environment': 'nature', 'team_buff': 0.10, 'duration': 2, 'type': 'environmental'
                }
            elif "immortal growth" in skill_lower:
                pet_combatant.skill_effects['immortal_growth'] = {
                    'team_regen': 0.10, 'duration': 3, 'dot_immunity': True, 'type': 'ultimate'
                }
            elif "nature affinity" in skill_lower:
                pet_combatant.skill_effects['nature_affinity'] = {
                    'elements': ['Electric', 'Wind'], 'damage_bonus': 0.2, 'type': 'elemental_bonus'
                }
            elif "forest camouflage" in skill_lower:
                pet_combatant.skill_effects['forest_camouflage'] = {
                    'chance': 25, 'type': 'avoid_targeting'
                }
            elif "symbiotic bond" in skill_lower:
                pet_combatant.skill_effects['symbiotic_bond'] = {
                    'share_percent': 0.5, 'type': 'owner_sharing'
                }
            elif "natural balance" in skill_lower:
                pet_combatant.skill_effects['natural_balance'] = {
                    'type': 'buff_transfer'
                }
            elif "world tree's gift" in skill_lower:
                pet_combatant.skill_effects['world_trees_gift'] = {
                    'control_turns': 3,
                    'shield_percent': 0.20,
                    'team_buff': 0.10,
                    'enemy_debuff': 0.15,
                    'debuff_immunity': True,
                    'type': 'ultimate',
                }
                
            # 💨 WIND SKILLS
            elif "wind slash" in skill_lower:
                pet_combatant.skill_effects['wind_slash'] = {
                    'chance': 15, 'type': 'bypass_defenses'
                }
            elif "gale force" in skill_lower:
                pet_combatant.skill_effects['gale_force'] = {
                    'accuracy_reduction': 0.30, 'damage_reduction': 0.10, 'duration': 2, 'type': 'push_back'
                }
            elif "tornado strike" in skill_lower:
                pet_combatant.skill_effects['tornado_strike'] = {
                    'damage_percent': 0.75, 'duration': 3, 'type': 'persistent_aoe'
                }
            elif "wind shear" in skill_lower:
                pet_combatant.skill_effects['wind_shear'] = {
                    'defense_reduction': 0.45, 'duration': 4, 'type': 'defense_debuff'
                }
            elif "wind walk" in skill_lower:
                pet_combatant.skill_effects['wind_walk'] = {
                    'dodge_bonus': 0.15, 'type': 'mobility_boost'
                }
            elif "air shield" in skill_lower:
                pet_combatant.skill_effects['air_shield'] = {
                    'projectile_immunity': True, 'other_reduction': 0.4, 'type': 'selective_defense'
                }
            elif "wind's guidance" in skill_lower:
                pet_combatant.skill_effects['winds_guidance'] = {
                    'chance': 40,
                    'damage_reduction': 0.55,
                    'reflect_fraction': 0.70,
                    'type': 'redirect_attack',
                }
            elif "freedom's call" in skill_lower:
                pet_combatant.skill_effects['freedoms_call'] = {
                    'team_speed': 0.35,
                    'team_buff': 0.20,
                    'duration': 3,
                    'type': 'team_speed_buff',
                }
            elif "sky's blessing" in skill_lower:
                pet_combatant.skill_effects['skys_blessing'] = {
                    'team_dodge': 0.40, 'enemy_stun': 2, 'duration': 2, 'type': 'ultimate'
                }
            elif "wind affinity" in skill_lower:
                pet_combatant.skill_effects['wind_affinity'] = {
                    'elements': ['Electric', 'Nature'], 'damage_bonus': 0.2, 'type': 'elemental_bonus'
                }
            elif "swift strike" in skill_lower:
                pet_combatant.skill_effects['swift_strike'] = {
                    'priority': True, 'damage_bonus': 0.10, 'type': 'always_first'
                }
                # Always-first attacks require persistent turn-order priority.
                setattr(pet_combatant, 'attack_priority', True)
            elif "wind tunnel" in skill_lower:
                pet_combatant.skill_effects['wind_tunnel'] = {
                    'distance_control': True,
                    'damage_bonus': 0.30,
                    'damage_reduction': 0.30,
                    'type': 'positioning',
                }
            elif "air currents" in skill_lower:
                pet_combatant.skill_effects['air_currents'] = {
                    'turn_order_control': True,
                    'luck_bonus': 0.15,
                    'team_buff': 0.10,
                    'duration': 3,
                    'type': 'initiative_control',
                }
            elif "zephyr's dance" in skill_lower:
                pet_combatant.skill_effects['zephyrs_dance'] = {
                    'team_speed': 3.5,
                    'enemy_slow': 2.5,
                    'team_buff': 0.20,
                    'enemy_damage_reduction': 0.20,
                    'duration': 4,
                    'type': 'ultimate',
                }
                
            # 🌟 LIGHT SKILLS
            elif "light beam" in skill_lower:
                pet_combatant.skill_effects['light_beam'] = {
                    'chance': 25, 'accuracy_reduction': 0.35, 'duration': 2, 'type': 'blind'
                }
            elif "holy strike" in skill_lower:
                pet_combatant.skill_effects['holy_strike'] = {
                    'elements': ['Dark', 'Undead', 'Corrupted'], 'damage_bonus': 0.4, 'type': 'elemental_bonus'
                }
            elif "divine wrath" in skill_lower:
                pet_combatant.skill_effects['divine_wrath'] = {
                    'type': 'dispel_on_hit'
                }
            elif "light burst" in skill_lower:
                pet_combatant.skill_effects['light_burst'] = {
                    'damage_multiplier': 1.2, 'type': 'aoe_attack'
                }
            elif "solar flare" in skill_lower:
                pet_combatant.skill_effects['solar_flare'] = {
                    'damage_multiplier': 3.0, 'purify_team': True, 'type': 'ultimate'
                }
            elif "divine shield" in skill_lower:
                pet_combatant.skill_effects['divine_shield'] = {
                    'dark_resistance': 0.3, 'general_resistance': 0.08, 'type': 'resistance'
                }
            elif "healing light" in skill_lower:
                pet_combatant.skill_effects['healing_light'] = {
                    'heal_percent': 0.07, 'type': 'team_heal_per_turn', 'message_shown': False
                }
            elif "purification" in skill_lower:
                pet_combatant.skill_effects['purification'] = {
                    'type': 'team_cleanse_per_turn'
                }
            elif "guardian angel" in skill_lower:
                pet_combatant.skill_effects['guardian_angel'] = {
                    'death_prevention': True, 'heal_to_full': True, 'type': 'sacrifice_save'
                }
            elif "divine protection" in skill_lower:
                pet_combatant.skill_effects['divine_protection'] = {
                    'invincibility_turns': 2, 'heal_percent': 0.45, 'type': 'ultimate'
                }
            elif "light affinity" in skill_lower:
                pet_combatant.skill_effects['light_affinity'] = {
                    'elements': ['Dark', 'Corrupted'], 'damage_bonus': 0.25, 'type': 'elemental_bonus'
                }
            elif "holy aura" in skill_lower:
                pet_combatant.skill_effects['holy_aura'] = {
                    'team_dark_resistance': 0.15, 'debuff_resistance': 0.15, 'type': 'team_protection'
                }
            elif "divine favor" in skill_lower:
                pet_combatant.skill_effects['divine_favor'] = {
                    'chance': 25, 'buff_strength': 0.15, 'duration': 2, 'type': 'random_team_buff'
                }
            elif "light's guidance" in skill_lower:
                pet_combatant.skill_effects['lights_guidance'] = {
                    'type': 'counter_abilities'
                }
            elif "celestial blessing" in skill_lower:
                pet_combatant.skill_effects['celestial_blessing'] = {
                    'team_buff': 0.25, 'physical_immunity': 2, 'type': 'ultimate'
                }
                
            # 🌑 DARK SKILLS
            elif "shadow strike" in skill_lower:
                pet_combatant.skill_effects['shadow_strike'] = {
                    'chance': 25, 'true_damage_portion': 0.4, 'type': 'partial_true_damage'
                }
            elif "dark embrace" in skill_lower:
                pet_combatant.skill_effects['dark_embrace'] = {
                    'owner_hp_threshold': 0.5, 'damage_bonus': 0.35, 'type': 'desperation_power'
                }
            elif "soul drain" in skill_lower:
                pet_combatant.skill_effects['soul_drain'] = {
                    'lifesteal_percent': 0.25, 'type': 'lifesteal'
                }
            elif "shadow clone" in skill_lower:
                pet_combatant.skill_effects['shadow_clone'] = {
                    'chance': 30, 'clone_damage': 0.75, 'type': 'duplicate_attack'
                }
            elif "void mastery" in skill_lower:
                pet_combatant.skill_effects['void_mastery'] = {
                    'damage_multiplier': 5.0, 'buff_inversion': True, 'type': 'ultimate'
                }
            elif "dark shield" in skill_lower:
                pet_combatant.skill_effects['dark_shield'] = {
                    'absorb_percent': 0.2, 'attack_bonus': 0.10, 'duration': 2, 'type': 'absorb_convert'
                }
            elif "soul bind" in skill_lower:
                pet_combatant.skill_effects['soul_bind'] = {
                    'damage_share': 0.35, 'type': 'damage_redistribution'
                }
            elif "dark pact" in skill_lower:
                pet_combatant.skill_effects['dark_pact'] = {
                    'hp_sacrifice': 0.25, 'owner_dark_boost': 0.35, 'duration': 2, 'type': 'sacrifice_buff'
                }
            elif "shadow form" in skill_lower:
                pet_combatant.skill_effects['shadow_form'] = {
                    'physical_immunity': 2, 'type': 'temporary_immunity'
                }
            elif "eternal night" in skill_lower:
                pet_combatant.skill_effects['eternal_night'] = {
                    'team_dark_power': 0.35, 'team_lifesteal': 0.15, 'duration': 3, 'type': 'ultimate'
                }
            elif "dark affinity" in skill_lower:
                pet_combatant.skill_effects['dark_affinity'] = {
                    'elements': ['Light', 'Corrupted'], 'damage_bonus': 0.25, 'type': 'elemental_bonus'
                }
            elif "night vision" in skill_lower:
                pet_combatant.skill_effects['night_vision'] = {
                    'perfect_accuracy': True, 'type': 'accuracy_enhancement'
                }
            elif "shadow step" in skill_lower:
                pet_combatant.skill_effects['shadow_step'] = {
                    'flat_damage_bonus': 100, 'type': 'teleport_attack'
                }
            elif "dark ritual" in skill_lower:
                pet_combatant.skill_effects['dark_ritual'] = {
                    'hp_sacrifice': 0.20,
                    'owner_hp_threshold': 0.75,
                    'damage_multiplier': 1.75,
                    'duration': 3,
                    'lifesteal': 0.20,
                    'type': 'sacrifice_power',
                }
            elif "lord of shadows" in skill_lower:
                pet_combatant.skill_effects['lord_of_shadows'] = {
                    'enemy_control': True,
                    'shadow_army': True,
                    'skeleton_hp': 0.75,
                    'skeleton_damage': 0.65,
                    'skeleton_armor': 0.40,
                    'team_buff': 0.15,
                    'enemy_debuff': 0.15,
                    'duration': 3,
                    'type': 'ultimate',
                }
                
            # 🌀 CORRUPTED SKILLS
            elif "chaos strike" in skill_lower:
                pet_combatant.skill_effects['chaos_strike'] = {
                    'damage_range': [0.75, 1.25], 'random_element': True, 'type': 'random_attack'
                }
            elif "corruption wave" in skill_lower:
                pet_combatant.skill_effects['corruption_wave'] = {
                    'chance': 20, 'cooldown': 2, 'stat_reduction': 0.15, 'spread': True, 'type': 'spreading_debuff'
                }
            elif "void rift" in skill_lower:
                pet_combatant.skill_effects['void_rift'] = {
                    'damage_percent': 0.3, 'duration': 4, 'type': 'persistent_void'
                }
            elif "reality warp" in skill_lower:
                pet_combatant.skill_effects['reality_warp'] = {
                    'random_conditions': True, 'chance': 0.08, 'cooldown': 4, 'type': 'chaos_field'
                }
            elif "apocalypse" in skill_lower:
                pet_combatant.skill_effects['apocalypse'] = {
                    'damage_multiplier': 7.0, 'chaos_realm': True, 'type': 'ultimate'
                }
            elif "decay touch" in skill_lower:
                pet_combatant.skill_effects['decay_touch'] = {
                    'stat_decay': 0.03, 'proximity': True, 'type': 'aura_debuff'
                }
            elif "corruption shield" in skill_lower:
                pet_combatant.skill_effects['corruption_shield'] = {
                    'corrupt_attackers': 0.25, 'type': 'defensive_corruption'
                }
            elif "soul harvest" in skill_lower:
                pet_combatant.skill_effects['soul_harvest'] = {
                    'kill_heal': 'full', 'type': 'execute_heal'
                }
            elif "eternal decay" in skill_lower:
                pet_combatant.skill_effects['eternal_decay'] = {
                    'corruption_immortality': True, 'corrupt_heal': 1, 'type': 'conditional_immortality'
                }
            elif "corruption mastery" in skill_lower:
                pet_combatant.skill_effects['corruption_mastery'] = {
                    'mind_control_all': True, 'corruption_immunity': True, 'type': 'ultimate'
                }
            elif "void affinity" in skill_lower:
                pet_combatant.skill_effects['void_affinity'] = {
                    'universal_bonus': 0.3, 'no_weaknesses': True, 'type': 'universal_advantage'
                }
            elif "void walk" in skill_lower:
                pet_combatant.skill_effects['void_walk'] = {
                    'dodge_chance': 0.4, 'reality_phase': True, 'type': 'phase_dodge'
                }
            elif "reality tear" in skill_lower:
                pet_combatant.skill_effects['reality_tear'] = {
                    'damage_multiplier': 2.0, 'ignore_all': True, 'chance': 15, 'type': 'void_attack'
                }
            elif "void mastery" in skill_lower:
                pet_combatant.skill_effects['void_mastery_corrupted'] = {
                    'reality_manipulation': True, 'type': 'reality_control'
                }
            elif "void lord" in skill_lower:
                pet_combatant.skill_effects['void_lord'] = {
                    'complete_control': True, 'rewrite_reality': True, 'duration': 3, 'owner_buff': 0.25, 'enemy_damage_mult': 0.80, 'enemy_luck_mult': 0.75, 'type': 'ultimate'
                }
            # NEW MISSING CORRUPTED SKILLS
            elif "void touch" in skill_lower:
                pet_combatant.skill_effects['void_touch'] = {
                    'stat_corruption': 0.1, 'permanent': True, 'type': 'permanent_debuff'
                }
            elif "chaos storm" in skill_lower:
                pet_combatant.skill_effects['chaos_storm'] = {
                    'chance': 15, 'cooldown': 2, 'aoe_multiplier': 0.65, 'effect_chance': 30, 'random_effects': True, 'type': 'chaos_aoe'
                }
            elif "corrupt shield" in skill_lower:
                pet_combatant.skill_effects['corrupt_shield'] = {
                    'absorb_percent': 0.20, 'corruption_chance': 0.20, 'type': 'absorb_corrupt'
                }
            elif "reality distortion" in skill_lower:
                pet_combatant.skill_effects['reality_distortion'] = {
                    'chance': 15, 'cooldown': 3, 'stat_swap': True, 'reverse_damage': True, 'type': 'reality_manipulation'
                }
            elif "void pact" in skill_lower:
                pet_combatant.skill_effects['void_pact'] = {
                    'damage_boost': 0.4, 'defense_penalty': 0.2, 'duration': 5, 'type': 'sacrifice_power'
                }
            elif "chaos form" in skill_lower:
                pet_combatant.skill_effects['chaos_form'] = {
                    'random_per_turn': True, 'unpredictable': True, 'type': 'chaos_transformation'
                }
            elif "end of days" in skill_lower:
                pet_combatant.skill_effects['end_of_days'] = {
                    'chaos_powers': True, 'reality_break': 3, 'team_damage_boost': 0.50, 'enemy_damage_reduction': 0.25, 'enemy_luck_mult': 0.70, 'type': 'ultimate'
                }
            elif "corrupted affinity" in skill_lower:
                pet_combatant.skill_effects['corrupted_affinity'] = {
                    'universal_damage': 0.15, 'no_weaknesses': True, 'type': 'universal_bonus'
                }
            elif "void sight" in skill_lower:
                pet_combatant.skill_effects['void_sight'] = {
                    'illusion_immunity': True, 'stealth_detection': True, 'dodge_bonus': 0.25, 'type': 'enhanced_vision'
                }
            elif "chaos control" in skill_lower:
                pet_combatant.skill_effects['chaos_control'] = {
                    'chance': 12, 'cooldown': 2, 'position_swap': True, 'damage_reverse': True, 'reality_control': True, 'type': 'chaos_mastery'
                }
    
    def process_skill_effects_on_attack(self, pet_combatant, target, damage):
        """Process skill effects when pet attacks"""
        from decimal import Decimal
        
        if not hasattr(pet_combatant, 'skill_effects'):
            return damage, []
            
        modified_damage = Decimal(str(damage))  # Convert to Decimal to handle all operations
        effects = pet_combatant.skill_effects
        messages = []
        countered_attacker_skill_name = None
        countered_attacker_skill_effect = None

        # Decrement internal balance cooldowns before evaluating new procs.
        for cooldown_attr in (
            'chaos_storm_cooldown',
            'chaos_control_cooldown',
            'reality_distortion_cooldown',
            'corruption_wave_cooldown',
            'reality_warp_cooldown',
        ):
            turns_left = int(getattr(pet_combatant, cooldown_attr, 0))
            if turns_left > 0:
                setattr(pet_combatant, cooldown_attr, turns_left - 1)

        # Defending Light's Guidance can blank one offensive enemy skill for this exchange.
        target_effects = getattr(target, 'skill_effects', {}) if hasattr(target, 'skill_effects') else {}
        if ('lights_guidance' in target_effects and effects and
            random.random() < self.LIGHTS_GUIDANCE_PROC_CHANCE):
            candidate_skills = self._get_lights_guidance_candidates(
                effects,
                self.LIGHTS_GUIDANCE_OFFENSIVE_TYPES,
                self.LIGHTS_GUIDANCE_OFFENSIVE_SKILLS,
            )
            if candidate_skills:
                countered_attacker_skill_name = random.choice(candidate_skills)
                countered_attacker_skill_effect = effects.pop(countered_attacker_skill_name, None)
                if countered_attacker_skill_effect is not None:
                    messages.append(
                        f"{target.name}'s Light's Guidance counters "
                        f"{pet_combatant.name}'s {self._format_skill_name(countered_attacker_skill_name)}!"
                    )
                    setattr(target, 'lights_guidance_last_counter', countered_attacker_skill_name)
        

        
        # 🔥 FIRE SKILLS
        # Flame Burst - 15% chance for 1.5x damage
        if 'flame_burst' in effects and random.randint(1, 100) <= effects['flame_burst']['chance']:
            modified_damage *= Decimal(str(effects['flame_burst']['damage_multiplier']))
            messages.append(f"{pet_combatant.name} unleashes Flame Burst! (1.5x damage)")
            
        # Phoenix Strike - heal on critical
        if 'phoenix_strike' in effects and modified_damage > damage * Decimal('1.2'):  # Critical hit
            heal_amount = self._scaled_heal(
                pet_combatant,
                pet_combatant,
                effects['phoenix_strike']['heal_percent'],
                self_target=True,
            )
            pet_combatant.heal(heal_amount)
            messages.append(f"{pet_combatant.name} heals **{heal_amount:.2f} HP** from Phoenix Strike!")
            
        # Burning Rage - low HP bonus
        if 'burning_rage' in effects:
            hp_ratio = pet_combatant.hp / pet_combatant.max_hp
            if hp_ratio < effects['burning_rage']['hp_threshold']:
                modified_damage *= (Decimal('1') + Decimal(str(effects['burning_rage']['damage_bonus'])))
                messages.append(f"{pet_combatant.name}'s Burning Rage activates! (+25% damage)")
                
        # Heat Wave - AOE damage
        if 'heat_wave' in effects and hasattr(target, 'team'):
            aoe_damage = modified_damage * Decimal(str(effects['heat_wave']['aoe_damage_percent']))
            for enemy in target.team.combatants:
                if enemy != target and enemy.is_alive():
                    enemy.take_damage(aoe_damage)
            messages.append(f"{pet_combatant.name}'s Heat Wave hits all enemies!")
            
        # Fire Affinity - elemental bonus
        if 'fire_affinity' in effects and hasattr(target, 'element'):
            if target.element in effects['fire_affinity']['elements']:
                modified_damage *= (Decimal('1') + Decimal(str(effects['fire_affinity']['damage_bonus'])))
                messages.append(f"{pet_combatant.name}'s Fire Affinity burns through {target.element}! (+20% damage)")
                
        # Inferno Mastery - fire enhancement
        if 'inferno_mastery' in effects:
            if hasattr(target, 'element') and target.element in ['Nature', 'Water']:
                fire_bonus = Decimal(str(effects['inferno_mastery']['fire_effectiveness'])) - Decimal('1')
                modified_damage *= Decimal(str(effects['inferno_mastery']['fire_effectiveness']))
                messages.append(
                    f"{pet_combatant.name}'s Inferno Mastery punishes {target.element}! "
                    f"(+{fire_bonus * Decimal('100'):.0f}% damage)"
                )
            inferno_turns = int(getattr(pet_combatant, 'inferno_mastery_turns', 0) or 0)
            if inferno_turns > 0:
                modified_damage *= Decimal('1.30')
                setattr(target, 'burning', max(int(getattr(target, 'burning', 0) or 0), 2))
                messages.append(f"{pet_combatant.name} fights in infernal overdrive!")

        if ('inferno_mastery' in effects and getattr(pet_combatant, 'ultimate_ready', False)):
            duration = int(effects['inferno_mastery'].get('active_turns', 4))
            setattr(pet_combatant, 'inferno_mastery_turns', duration)
            modified_damage *= Decimal('1.60')
            if hasattr(pet_combatant, 'team'):
                for ally in pet_combatant.team.combatants:
                    if ally.is_alive():
                        self._apply_timed_multiplier(
                            ally,
                            'inferno_mastery_aura',
                            duration,
                            damage_mult=Decimal('1') + Decimal(str(effects['inferno_mastery'].get('team_buff', 0.15))),
                            luck_mult=Decimal('1.10'),
                        )
            messages.append(
                f"{pet_combatant.name}'s Inferno Mastery erupts! "
                f"The team surges with infernal momentum for {duration} turns!"
            )
            pet_combatant.ultimate_ready = False

        if 'burning_spirit' in effects and random.randint(1, 100) <= effects['burning_spirit']['chance']:
            setattr(target, 'burning', max(int(getattr(target, 'burning', 0) or 0), effects['burning_spirit']['duration']))
            messages.append(f"{pet_combatant.name}'s Burning Spirit sets {target.name} ablaze!")
            
        # Sun God's Blessing - ULTIMATE
        if ('sun_gods_blessing' in effects and 
            getattr(pet_combatant, 'ultimate_ready', False)):
            modified_damage *= Decimal(str(effects['sun_gods_blessing']['damage_multiplier']))
            if hasattr(pet_combatant, 'team'):
                for ally in pet_combatant.team.combatants:
                    if ally.is_alive():
                        self._apply_timed_multiplier(
                            ally,
                            'sun_gods_blessing',
                            int(effects['sun_gods_blessing'].get('duration', 3)),
                            damage_mult=Decimal('1') + Decimal(str(effects['sun_gods_blessing'].get('team_buff', 0.30))),
                            armor_mult=Decimal('1.20'),
                            luck_mult=Decimal('1.10'),
                        )
            if hasattr(target, 'team'):
                splash_damage = modified_damage * Decimal('0.60')
                for enemy in target.team.combatants:
                    if enemy != target and enemy.is_alive():
                        enemy.take_damage(splash_damage)
                    if enemy.is_alive():
                        setattr(
                            enemy,
                            'burning',
                            max(
                                int(getattr(enemy, 'burning', 0) or 0),
                                int(effects['sun_gods_blessing'].get('burn_duration', 2)),
                            ),
                        )
            messages.append(f"{pet_combatant.name} channels Sun God's Blessing! Solar fire engulfs the battlefield!")
            pet_combatant.ultimate_ready = False
            
        # 💧 WATER SKILLS
        # Water Jet - ignore armor
        if 'water_jet' in effects and random.randint(1, 100) <= effects['water_jet']['chance']:
            setattr(target, 'ignore_armor_this_hit', True)
            setattr(target, 'ignore_shield_this_hit', True)
            messages.append(f"{pet_combatant.name}'s Water Jet pierces armor and shields!")
            
        # Tsunami Strike - HP based damage
        if 'tsunami_strike' in effects:
            hp_ratio = pet_combatant.hp / pet_combatant.max_hp
            modified_damage *= (Decimal('1') + hp_ratio * Decimal(str(effects['tsunami_strike']['hp_scaling'])))
            messages.append(f"{pet_combatant.name}'s Tsunami Strike scales with HP!")
            
        # Deep Pressure - execute low HP enemies
        if 'deep_pressure' in effects:
            target_hp_ratio = target.hp / target.max_hp
            if target_hp_ratio < effects['deep_pressure']['hp_threshold']:
                modified_damage *= (Decimal('1') + Decimal(str(effects['deep_pressure']['damage_bonus'])))
                messages.append(f"{pet_combatant.name}'s Deep Pressure executes weakened foe!")
                
        # Abyssal Grip - stun attack
        if 'abyssal_grip' in effects and random.randint(1, 100) <= effects['abyssal_grip']['chance']:
            setattr(target, 'stunned', effects['abyssal_grip']['duration'])
            messages.append(f"{pet_combatant.name}'s Abyssal Grip stuns {target.name} with crushing depths!")
            
        # Water Affinity - elemental bonus
        if 'water_affinity' in effects and hasattr(target, 'element'):
            if target.element in effects['water_affinity']['elements']:
                modified_damage *= (Decimal('1') + Decimal(str(effects['water_affinity']['damage_bonus'])))
                messages.append(f"{pet_combatant.name}'s Water Affinity overwhelms {target.element}! (+20% damage)")
                
        # Tidal Force - turn manipulation
        if 'tidal_force' in effects and hasattr(target, 'team'):
            # Apply turn delay to all enemies
            for enemy in target.team.combatants:
                if enemy.is_alive():
                    setattr(enemy, 'tidal_delayed', effects['tidal_force']['turn_delay'])
            messages.append(f"{pet_combatant.name}'s Tidal Force slows the enemy team's actions!")
                
        # Ocean's Wrath - ULTIMATE
        if ('oceans_wrath' in effects and 
            getattr(pet_combatant, 'ultimate_ready', False)):
            modified_damage *= Decimal(str(effects['oceans_wrath']['damage_multiplier']))
            if hasattr(target, 'team'):
                splash_damage = modified_damage * Decimal(str(effects['oceans_wrath'].get('splash_multiplier', 0.75)))
                for enemy in target.team.combatants:
                    if enemy != target and enemy.is_alive():
                        enemy.take_damage(splash_damage)
            if hasattr(pet_combatant, 'team'):
                for ally in pet_combatant.team.combatants:
                    if ally.is_alive():
                        heal_amount = self._scaled_heal(
                            pet_combatant,
                            ally,
                            effects['oceans_wrath'].get('heal_percent', 0.30),
                            burst=True,
                            self_target=(ally is pet_combatant),
                        )
                        ally.heal(heal_amount)
            messages.append(f"{pet_combatant.name} unleashes Ocean's Wrath! A crushing tide batters foes and restores allies!")
            pet_combatant.ultimate_ready = False
            
        # Poseidon's Call - ULTIMATE
        if ('poseidons_call' in effects and 
            getattr(pet_combatant, 'ultimate_ready', False)):
            if hasattr(pet_combatant, 'team'):
                for ally in pet_combatant.team.combatants:
                    if ally.is_alive():
                        self._apply_timed_multiplier(
                            ally,
                            'poseidons_call',
                            3,
                            damage_mult=Decimal('1') + Decimal(str(effects['poseidons_call']['team_buff'])),
                            armor_mult=Decimal('1.15'),
                            luck_mult=Decimal('1.10'),
                        )
            if hasattr(target, 'team'):
                for enemy in target.team.combatants:
                    if enemy.is_alive():
                        self._apply_timed_multiplier(
                            enemy,
                            'poseidons_call_curse',
                            3,
                            damage_mult=Decimal('1') - Decimal(str(effects['poseidons_call']['enemy_debuff'])),
                            armor_mult=Decimal('0.85'),
                            luck_mult=Decimal('0.90'),
                        )
            messages.append(f"{pet_combatant.name} calls upon Poseidon! Team buffed, enemies weakened!")
            pet_combatant.ultimate_ready = False
            
        # ⚡ ELECTRIC SKILLS
        if 'static_shock' in effects and random.randint(1, 100) <= effects['static_shock']['chance']:
            setattr(target, 'paralyzed', effects['static_shock']['duration'])
            messages.append(f"{pet_combatant.name}'s Static Shock paralyzes {target.name}!")

        # Thunder Strike - chain lightning on crit
        if ('thunder_strike' in effects and modified_damage > damage * Decimal('1.2') and 
            hasattr(target, 'team')):
            chain_targets = [e for e in target.team.combatants if e != target and e.is_alive()]
            if chain_targets:
                for i, chain_target in enumerate(chain_targets[:effects['thunder_strike']['chain_count']]):
                    if i < len(effects['thunder_strike']['chain_damage']):
                        chain_dmg = modified_damage * Decimal(str(effects['thunder_strike']['chain_damage'][i]))
                        chain_target.take_damage(chain_dmg)
                messages.append(f"{pet_combatant.name}'s Thunder Strike chains to {len(chain_targets)} enemies!")
                
        # Voltage Surge - stacking damage
        if 'voltage_surge' in effects:
            if not hasattr(pet_combatant, 'voltage_stacks'):
                pet_combatant.voltage_stacks = 0
            pet_combatant.voltage_stacks = min(
                pet_combatant.voltage_stacks + 1, 
                effects['voltage_surge']['max_stacks']
            )
            bonus = pet_combatant.voltage_stacks * Decimal(str(effects['voltage_surge']['stack_bonus']))
            modified_damage *= (Decimal('1') + bonus)
            messages.append(f"{pet_combatant.name} builds Voltage! Stack {pet_combatant.voltage_stacks}")
            
        # Storm Lord - ULTIMATE
        if ('storm_lord' in effects and 
            getattr(pet_combatant, 'ultimate_ready', False)):
            modified_damage *= Decimal(str(effects['storm_lord']['damage_multiplier']))
            duration = int(effects['storm_lord'].get('duration', 3))
            if hasattr(pet_combatant, 'team'):
                for ally in pet_combatant.team.combatants:
                    if ally.is_alive():
                        self._apply_timed_multiplier(
                            ally,
                            'storm_lord',
                            duration,
                            damage_mult=Decimal('1.15'),
                            luck_mult=Decimal('1.15'),
                        )
                        setattr(ally, 'storm_lord_haste', duration)
            messages.append(f"{pet_combatant.name} becomes the Storm Lord! The team surges with storm speed!")
            pet_combatant.ultimate_ready = False

        # Infinite Energy - ULTIMATE team stat boost
        if ('infinite_energy' in effects and
            getattr(pet_combatant, 'ultimate_ready', False)):
            team_buff = Decimal(str(effects['infinite_energy']['team_buff']))
            duration = int(effects['infinite_energy']['duration'])

            if hasattr(pet_combatant, 'team'):
                for ally in pet_combatant.team.combatants:
                    if ally.is_alive():
                        self._apply_timed_multiplier(
                            ally,
                            'infinite_energy',
                            duration,
                            damage_mult=Decimal('1') + team_buff,
                            armor_mult=Decimal('1') + team_buff,
                            luck_mult=Decimal('1') + team_buff,
                            extra_attrs={'unlimited_abilities': True},
                        )
                messages.append(
                    f"{pet_combatant.name} unleashes Infinite Energy! "
                    f"The team gains +{int(team_buff * Decimal('100'))}% all stats for {duration} turns!"
                )
            pet_combatant.ultimate_ready = False
            
        # Chain Lightning - multiple targets
        if ('chain_lightning' in effects and hasattr(target, 'team')):
            chain_targets = [e for e in target.team.combatants if e != target and e.is_alive()]
            for i, chain_target in enumerate(chain_targets[:effects['chain_lightning']['chain_count']]):
                if i < len(effects['chain_lightning']['chain_damage']):
                    chain_dmg = modified_damage * Decimal(str(effects['chain_lightning']['chain_damage'][i]))
                    chain_target.take_damage(chain_dmg)
            messages.append(f"{pet_combatant.name}'s Chain Lightning hits {len(chain_targets)} additional targets!")

        # Electric Affinity - elemental bonus
        if 'electric_affinity' in effects and hasattr(target, 'element'):
            if target.element in effects['electric_affinity']['elements']:
                modified_damage *= (Decimal('1') + Decimal(str(effects['electric_affinity']['damage_bonus'])))
                messages.append(f"{pet_combatant.name}'s Electric Affinity shocks {target.element} enemies! (+20% damage)")
            
        # Zeus's Wrath - ULTIMATE
        if ('zeus_wrath' in effects and 
            getattr(pet_combatant, 'ultimate_ready', False)):
            modified_damage *= Decimal(str(effects['zeus_wrath']['damage_multiplier']))
            if hasattr(pet_combatant, 'team'):
                for ally in pet_combatant.team.combatants:
                    if ally.is_alive():
                        self._apply_timed_multiplier(
                            ally,
                            'zeus_wrath',
                            int(effects['zeus_wrath'].get('protection_turns', 3)),
                            damage_mult=Decimal('1.10'),
                            armor_mult=Decimal('1.10'),
                        )
                        setattr(ally, 'zeus_protection', int(effects['zeus_wrath'].get('protection_turns', 3)))
                        setattr(ally, 'debuff_immunity', int(effects['zeus_wrath'].get('protection_turns', 3)))
            messages.append(f"{pet_combatant.name} channels Zeus's Wrath! The team is charged with divine protection!")
            pet_combatant.ultimate_ready = False
            
        # 🌿 NATURE SKILLS
        # Nature's Fury - happiness based
        if 'natures_fury' in effects:
            happiness = getattr(pet_combatant, 'happiness', 50)
            modified_damage *= (Decimal('1') + min(Decimal('0.5'), Decimal(str(happiness))/Decimal('200') * Decimal(str(effects['natures_fury']['happiness_scaling']))))
            messages.append(f"{pet_combatant.name}'s happiness fuels Nature's Fury!")

        if 'photosynthesis' in effects:
            current_hour = datetime.datetime.now().hour
            if 6 <= current_hour <= 18:
                modified_damage *= (Decimal('1') + Decimal(str(effects['photosynthesis']['damage_bonus'])))
                messages.append(f"{pet_combatant.name} draws strength from daylight!")
            
        # Vine Whip - root attack
        if 'vine_whip' in effects and random.randint(1, 100) <= effects['vine_whip']['chance']:
            damage_reduction = Decimal(str(effects['vine_whip']['damage_reduction']))
            self._apply_timed_multiplier(
                target,
                'vine_whip',
                int(effects['vine_whip']['duration']),
                damage_mult=Decimal('1') - damage_reduction,
            )
            messages.append(f"{pet_combatant.name}'s Vine Whip entangles {target.name}, sapping their damage!")
            
        # Nature Affinity - elemental bonus
        if 'nature_affinity' in effects and hasattr(target, 'element'):
            if target.element in effects['nature_affinity']['elements']:
                modified_damage *= (Decimal('1') + Decimal(str(effects['nature_affinity']['damage_bonus'])))
                messages.append(f"{pet_combatant.name}'s Nature Affinity is strong against {target.element}! (+20% damage)")
            
        # Gaia's Wrath - ULTIMATE
        if ('gaias_wrath' in effects and 
            getattr(pet_combatant, 'ultimate_ready', False)):
            modified_damage *= Decimal(str(effects['gaias_wrath']['damage_multiplier']))

            setattr(pet_combatant, 'gaias_wrath_heal', effects['gaias_wrath']['heal_per_turn'])
            setattr(pet_combatant, 'gaias_wrath_duration', effects['gaias_wrath']['duration'])

            if hasattr(pet_combatant, 'team'):
                for ally in pet_combatant.team.combatants:
                    if ally.is_alive():
                        heal_amount = self._scaled_heal(
                            pet_combatant,
                            ally,
                            effects['gaias_wrath'].get('team_heal_percent', 0.35),
                            burst=True,
                            self_target=(ally is pet_combatant),
                        )
                        ally.heal(heal_amount)

            messages.append(f"{pet_combatant.name} unleashes Gaia's Wrath! The whole team is flooded with ancient life!")
            pet_combatant.ultimate_ready = False
            
        # World Tree's Gift - ULTIMATE
        if ('world_trees_gift' in effects and 
            getattr(pet_combatant, 'ultimate_ready', False)):
            duration = int(effects['world_trees_gift'].get('control_turns', 3))
            setattr(pet_combatant, 'battlefield_control', duration)
            if hasattr(pet_combatant, 'team'):
                for ally in pet_combatant.team.combatants:
                    if ally.is_alive():
                        current_shield = self._to_decimal(getattr(ally, 'shield', 0))
                        ally.shield = current_shield + (
                            ally.max_hp * Decimal(str(effects['world_trees_gift'].get('shield_percent', 0.20)))
                        )
                        setattr(ally, 'debuff_immunity', duration)
                        self._apply_timed_multiplier(
                            ally,
                            'world_trees_gift',
                            duration,
                            damage_mult=Decimal('1') + Decimal(str(effects['world_trees_gift'].get('team_buff', 0.10))),
                            armor_mult=Decimal('1.15'),
                            luck_mult=Decimal('1.10'),
                        )
            if hasattr(target, 'team'):
                for enemy in target.team.combatants:
                    if enemy.is_alive():
                        self._apply_timed_multiplier(
                            enemy,
                            'world_trees_gift_curse',
                            duration,
                            damage_mult=Decimal('1') - Decimal(str(effects['world_trees_gift'].get('enemy_debuff', 0.15))),
                            luck_mult=Decimal('0.85'),
                        )
            messages.append(
                f"{pet_combatant.name} receives the World Tree's Gift! Roots shield allies and crush enemy momentum!"
            )
            pet_combatant.ultimate_ready = False
            
        # Immortal Growth - ULTIMATE
        if ('immortal_growth' in effects and 
            getattr(pet_combatant, 'ultimate_ready', False)):
            if hasattr(pet_combatant, 'team'):
                for ally in pet_combatant.team.combatants:
                    if ally.is_alive():
                        setattr(ally, 'immortal_growth_regen', effects['immortal_growth']['team_regen'])
                        setattr(ally, 'immortal_growth_duration', int(effects['immortal_growth'].get('duration', 3)))
                        setattr(ally, 'dot_immunity', True)
                        
                        # Remove existing DoTs
                        for dot in ['poisoned', 'burning', 'corrupted']:
                            if hasattr(ally, dot):
                                delattr(ally, dot)
                                
            messages.append(f"{pet_combatant.name} grants Immortal Growth! The team becomes one with nature!")
            pet_combatant.ultimate_ready = False
            
        # 💨 WIND SKILLS
        # Wind Slash - bypass defenses
        if 'wind_slash' in effects and random.randint(1, 100) <= effects['wind_slash']['chance']:
            setattr(target, 'bypass_defenses', True)
            setattr(target, 'ignore_shield_this_hit', True)
            messages.append(f"{pet_combatant.name}'s Wind Slash cuts through all defenses!")
            
        # Tornado Strike - persistent AOE
        if 'tornado_strike' in effects and hasattr(target, 'team'):
            tornado_damage = modified_damage * Decimal(str(effects['tornado_strike']['damage_percent']))
            duration = int(effects['tornado_strike']['duration'])
            for enemy in target.team.combatants:
                if enemy.is_alive():
                    setattr(enemy, 'tornado_damage', {
                        'damage': tornado_damage,
                        'duration': duration,
                    })
            messages.append(f"{pet_combatant.name} blankets the enemy team in a cutting tornado!")
            
        # Gale Force - pushback with accuracy reduction
        if 'gale_force' in effects and hasattr(target, 'team'):
            self._apply_timed_multiplier(
                target,
                'gale_force',
                effects['gale_force']['duration'],
                damage_mult=Decimal('1') - Decimal(str(effects['gale_force'].get('damage_reduction', 0.10))),
                luck_mult=Decimal('1') - Decimal(str(effects['gale_force']['accuracy_reduction'])),
            )
            messages.append(f"{pet_combatant.name}'s Gale Force batters {target.name}'s aim and rhythm!")
             
        # Wind Shear - defense debuff
        if 'wind_shear' in effects and hasattr(target, 'team'):
            defense_reduction = Decimal(str(effects['wind_shear']['defense_reduction']))
            for enemy in target.team.combatants:
                if enemy.is_alive():
                    self._apply_timed_multiplier(
                        enemy,
                        'wind_shear',
                        effects['wind_shear']['duration'],
                        armor_mult=Decimal('1') - defense_reduction,
                    )
            messages.append(f"{pet_combatant.name}'s Wind Shear tears through the enemy line! (-45% armor)")
            
        # Storm Lord Wind - ULTIMATE battlefield control
        if ('storm_lord_wind' in effects and 
            getattr(pet_combatant, 'ultimate_ready', False)):
            modified_damage *= Decimal(str(effects['storm_lord_wind']['damage_multiplier']))
            duration = int(effects['storm_lord_wind'].get('duration', 3))
            if hasattr(pet_combatant, 'team'):
                for ally in pet_combatant.team.combatants:
                    if ally.is_alive():
                        self._apply_timed_multiplier(
                            ally,
                            'storm_lord_wind_ally',
                            duration,
                            damage_mult=Decimal('1') + Decimal(str(effects['storm_lord_wind'].get('team_buff', 0.15))),
                            luck_mult=Decimal('1.15'),
                        )
                        setattr(ally, 'storm_lord_haste', duration)
            if hasattr(target, 'team'):
                for enemy in target.team.combatants:
                    if enemy.is_alive():
                        setattr(enemy, 'storm_dominated', duration)
                        self._apply_timed_multiplier(
                            enemy,
                            'storm_lord_wind',
                            duration,
                            damage_mult=Decimal(str(effects['storm_lord_wind'].get('enemy_damage_mult', 0.70))),
                            luck_mult=Decimal(str(effects['storm_lord_wind'].get('enemy_luck_mult', 0.75))),
                        )
                        setattr(enemy, 'tornado_damage', {
                            'damage': modified_damage * Decimal(str(effects['storm_lord_wind'].get('storm_damage', 0.45))),
                            'duration': duration,
                        })
            setattr(pet_combatant, 'storm_lord_active', duration)
            messages.append(f"{pet_combatant.name} becomes the Storm Lord! The battlefield is dragged into violent air supremacy!")
            pet_combatant.ultimate_ready = False
            
        # Wind Affinity - elemental bonus
        if 'wind_affinity' in effects and hasattr(target, 'element'):
            if target.element in effects['wind_affinity']['elements']:
                modified_damage *= (Decimal('1') + Decimal(str(effects['wind_affinity']['damage_bonus'])))
                messages.append(f"{pet_combatant.name}'s Wind Affinity devastates {target.element} enemies! (+20% damage)")
                
        # Swift Strike - priority attack (always goes first)
        if 'swift_strike' in effects:
            setattr(pet_combatant, 'attack_priority', True)
            modified_damage *= (
                Decimal('1') + Decimal(str(effects['swift_strike'].get('damage_bonus', 0.10)))
            )
            messages.append(f"{pet_combatant.name} strikes with the speed of wind!")

        # Wind Tunnel - convert positioning into offense
        if 'wind_tunnel' in effects:
            modified_damage *= (
                Decimal('1') + Decimal(str(effects['wind_tunnel'].get('damage_bonus', 0.30)))
            )
            messages.append(f"{pet_combatant.name} bends the battlefield with Wind Tunnel! (+30% damage)")
            
        # Sky's Blessing - ULTIMATE
        if ('skys_blessing' in effects and 
            getattr(pet_combatant, 'ultimate_ready', False)):
            duration = int(effects['skys_blessing'].get('duration', 2))
            if hasattr(pet_combatant, 'team'):
                for ally in pet_combatant.team.combatants:
                    if ally.is_alive():
                        setattr(ally, 'sky_dodge', effects['skys_blessing']['team_dodge'])
                        setattr(ally, 'sky_dodge_duration', duration)
                        setattr(ally, 'sky_haste', True)
                        setattr(ally, 'sky_haste_duration', duration)
            if hasattr(target, 'team'):
                stunned_targets = [e for e in target.team.combatants if e.is_alive()]
                random.shuffle(stunned_targets)
                for enemy in stunned_targets[:2]:
                    setattr(enemy, 'stunned', effects['skys_blessing']['enemy_stun'])
            messages.append(f"{pet_combatant.name} calls upon Sky's Blessing! The team surges through the heavens!")
            pet_combatant.ultimate_ready = False
            
        # Zephyr's Dance - ULTIMATE
        if ('zephyrs_dance' in effects and 
            getattr(pet_combatant, 'ultimate_ready', False)):
            duration = int(effects['zephyrs_dance'].get('duration', 4))
            if hasattr(pet_combatant, 'team'):
                for ally in pet_combatant.team.combatants:
                    if ally.is_alive():
                        setattr(ally, 'zephyr_speed', effects['zephyrs_dance']['team_speed'])
                        setattr(ally, 'zephyr_speed_duration', duration)
                        self._apply_timed_multiplier(
                            ally,
                            'zephyrs_dance',
                            duration,
                            damage_mult=Decimal('1') + Decimal(str(effects['zephyrs_dance'].get('team_buff', 0.20))),
                            luck_mult=Decimal('1.20'),
                        )
            if hasattr(target, 'team'):
                for enemy in target.team.combatants:
                    if enemy.is_alive():
                        setattr(enemy, 'zephyr_slow', effects['zephyrs_dance']['enemy_slow'])
                        setattr(enemy, 'zephyr_slow_duration', duration)
                        self._apply_timed_multiplier(
                            enemy,
                            'zephyrs_dance_slow',
                            duration,
                            damage_mult=Decimal('1') - Decimal(str(effects['zephyrs_dance'].get('enemy_damage_reduction', 0.20))),
                            luck_mult=Decimal('0.80'),
                        )
            messages.append(f"{pet_combatant.name} performs Zephyr's Dance! The team takes over the turn order completely!")
            pet_combatant.ultimate_ready = False
            
        # 🌟 LIGHT SKILLS
        # Holy Strike - bonus vs dark
        if 'holy_strike' in effects and hasattr(target, 'element'):
            if target.element in effects['holy_strike']['elements']:
                modified_damage *= (Decimal('1') + Decimal(str(effects['holy_strike']['damage_bonus'])))
                messages.append(f"{pet_combatant.name}'s Holy Strike devastates dark creatures!")

        # Light Affinity - bonus vs dark/corrupted
        if 'light_affinity' in effects and hasattr(target, 'element'):
            if target.element in effects['light_affinity']['elements']:
                damage_bonus = Decimal(str(effects['light_affinity']['damage_bonus']))
                modified_damage *= (Decimal('1') + damage_bonus)
                messages.append(
                    f"{pet_combatant.name}'s Light Affinity overwhelms darkness! "
                    f"(+{damage_bonus * Decimal('100'):.0f}% damage)"
                )
                
        # Light Burst - AOE attack
        if 'light_burst' in effects and hasattr(target, 'team'):
            modified_damage *= Decimal(str(effects['light_burst']['damage_multiplier']))
            aoe_damage = modified_damage * Decimal('0.5')
            for enemy in target.team.combatants:
                if enemy != target and enemy.is_alive():
                    enemy.take_damage(aoe_damage)
            messages.append(f"{pet_combatant.name}'s Light Burst illuminates the battlefield!")
            
        # Solar Flare - ULTIMATE
        if ('solar_flare' in effects and 
            getattr(pet_combatant, 'ultimate_ready', False)):
            modified_damage *= Decimal(str(effects['solar_flare']['damage_multiplier']))
            if hasattr(target, 'team'):
                splash_damage = modified_damage * Decimal('0.60')
                for enemy in target.team.combatants:
                    if enemy != target and enemy.is_alive():
                        enemy.take_damage(splash_damage)
            # Purify entire team
            if hasattr(pet_combatant, 'team'):
                for ally in pet_combatant.team.combatants:
                    # Remove all debuffs
                    for attr in ['stunned', 'poisoned', 'corrupted', 'slowed']:
                        if hasattr(ally, attr):
                            delattr(ally, attr)
            messages.append(f"{pet_combatant.name} unleashes Solar Flare! Purifying light cleanses all!")
            pet_combatant.ultimate_ready = False
            
        # Light Beam - blinding attack
        if 'light_beam' in effects and random.randint(1, 100) <= effects['light_beam']['chance']:
            accuracy_reduction = Decimal(str(effects['light_beam']['accuracy_reduction']))
            self._apply_timed_multiplier(
                target,
                'light_beam',
                int(effects['light_beam']['duration']),
                luck_mult=Decimal('1') - accuracy_reduction,
            )
            messages.append(
                f"{pet_combatant.name}'s Light Beam blinds {target.name}! "
                f"(-{accuracy_reduction * Decimal('100'):.0f}% accuracy)"
            )
            
        # Celestial Blessing - ULTIMATE
        if ('celestial_blessing' in effects and 
            getattr(pet_combatant, 'ultimate_ready', False)):
            if hasattr(pet_combatant, 'team'):
                for ally in pet_combatant.team.combatants:
                    if ally.is_alive():
                        self._apply_timed_multiplier(
                            ally,
                            'celestial_blessing',
                            int(effects['celestial_blessing'].get('physical_immunity', 2)),
                            damage_mult=Decimal('1') + Decimal(str(effects['celestial_blessing']['team_buff'])),
                            armor_mult=Decimal('1.15'),
                            luck_mult=Decimal('1.10'),
                        )
                        setattr(ally, 'physical_immunity', int(effects['celestial_blessing']['physical_immunity']))
            messages.append(f"{pet_combatant.name} grants Celestial Blessing! Divine power flows through the team!")
            pet_combatant.ultimate_ready = False
            
        # 🌑 DARK SKILLS
        # Dark Affinity - bonus vs Light elements
        if 'dark_affinity' in effects and hasattr(target, 'element'):
            if target.element in effects['dark_affinity']['elements']:
                damage_bonus = Decimal(str(effects['dark_affinity']['damage_bonus']))
                modified_damage *= (Decimal('1') + damage_bonus)
                messages.append(
                    f"{pet_combatant.name}'s Dark Affinity devastates light creatures! "
                    f"(+{damage_bonus * Decimal('100'):.0f}% damage)"
                )
                
        # Night Vision - perfect accuracy (handled in battle accuracy calculations)
        if 'night_vision' in effects:
            setattr(pet_combatant, 'perfect_accuracy', True)
            
        # Shadow Step - flat damage bonus before armor
        if 'shadow_step' in effects:
            modified_damage += Decimal(str(effects['shadow_step']['flat_damage_bonus']))
            messages.append(f"{pet_combatant.name} shadow steps through reality! (+100 raw damage)")
            
        # Dark Ritual - once-per-battle blood pact for sustained offense
        if ('dark_ritual' in effects and hasattr(pet_combatant, 'owner')):
            owner_combatant = self.find_owner_combatant(pet_combatant)
            if owner_combatant and hasattr(owner_combatant, 'hp') and hasattr(owner_combatant, 'max_hp'):
                owner_hp_ratio = owner_combatant.hp / owner_combatant.max_hp
                should_activate = (
                    owner_hp_ratio < Decimal(str(effects['dark_ritual'].get('owner_hp_threshold', 0.75)))
                    and not getattr(pet_combatant, 'dark_ritual_used', False)
                    and not getattr(pet_combatant, 'dark_ritual_duration', 0)
                )
                if should_activate:
                    sacrifice_hp = owner_combatant.max_hp * Decimal(str(effects['dark_ritual']['hp_sacrifice']))
                    current_owner_hp = owner_combatant.hp
                    if current_owner_hp > sacrifice_hp:
                        owner_combatant.hp = current_owner_hp - sacrifice_hp
                        power_mult = Decimal(str(effects['dark_ritual']['damage_multiplier']))
                        self._apply_timed_multiplier(
                            pet_combatant,
                            'dark_ritual',
                            int(effects['dark_ritual'].get('duration', 3)),
                            damage_mult=power_mult,
                            luck_mult=Decimal('1.15'),
                            extra_attrs={'dark_ritual_lifesteal': Decimal(str(effects['dark_ritual'].get('lifesteal', 0.20)))},
                        )
                        modified_damage *= power_mult
                        setattr(pet_combatant, 'dark_ritual_used', True)
                        messages.append(
                            f"{pet_combatant.name} performs Dark Ritual! "
                            f"Sacrifices **{sacrifice_hp:.2f} HP** from their owner for a blood-fueled rampage!"
                        )
        
        # Shadow Strike - partial true damage
        if 'shadow_strike' in effects and random.randint(1, 100) <= effects['shadow_strike']['chance']:
            true_fraction = Decimal(str(effects['shadow_strike'].get('true_damage_portion', 0.4)))
            true_damage_portion = modified_damage * true_fraction
            normal_damage_portion = modified_damage - true_damage_portion

            # Let battle types combine this with normal damage in a single hit application.
            existing_partial_true = Decimal(str(getattr(target, 'partial_true_damage', 0)))
            setattr(target, 'partial_true_damage', existing_partial_true + true_damage_portion)

            # The true portion should bypass shield absorption when final damage is applied.
            existing_bypass_shield = Decimal(str(getattr(target, 'pending_true_damage_bypass_shield', 0)))
            setattr(target, 'pending_true_damage_bypass_shield', existing_bypass_shield + true_damage_portion)

            # The normal portion will go through armor as usual.
            modified_damage = normal_damage_portion

            messages.append(
                f"{pet_combatant.name}'s Shadow Strike partially pierces defenses! "
                f"**{true_damage_portion:.2f} true damage** will bypass armor and shields!"
            )
        
        # Dark Embrace - owner low HP scaling
        if 'dark_embrace' in effects and hasattr(pet_combatant, 'owner'):
            # Find the owner combatant from the team
            owner_combatant = self.find_owner_combatant(pet_combatant)
            if owner_combatant and hasattr(owner_combatant, 'hp') and hasattr(owner_combatant, 'max_hp'):
                # Dead owners should not trigger desperation-based amplification.
                if owner_combatant.hp <= 0 or owner_combatant.max_hp <= 0:
                    pass
                else:
                    owner_hp_ratio = owner_combatant.hp / owner_combatant.max_hp
                    if owner_hp_ratio < Decimal(str(effects['dark_embrace']['owner_hp_threshold'])):
                        damage_bonus = Decimal(str(effects['dark_embrace']['damage_bonus']))
                        modified_damage *= (Decimal('1') + damage_bonus)
                        messages.append(
                            f"{pet_combatant.name} draws power from desperation! "
                            f"(+{damage_bonus * Decimal('100'):.0f}% damage)"
                        )
            
        # Shadow Clone - duplicate attack
        if 'shadow_clone' in effects and random.randint(1, 100) <= effects['shadow_clone']['chance']:
            clone_damage = modified_damage * Decimal(str(effects['shadow_clone']['clone_damage']))
            target.take_damage(clone_damage)
            messages.append(f"{pet_combatant.name}'s shadow clone attacks for **{clone_damage:.2f} damage**!")
            
        # Void Mastery - ULTIMATE
        if ('void_mastery' in effects and 
            getattr(pet_combatant, 'ultimate_ready', False)):
            modified_damage *= Decimal('2.25')
            if hasattr(target, 'team'):
                for enemy in target.team.combatants:
                    if enemy.is_alive():
                        self._apply_timed_multiplier(
                            enemy,
                            'void_mastery',
                            2,
                            damage_mult=Decimal('0.85'),
                            armor_mult=Decimal('0.85'),
                            luck_mult=Decimal('0.90'),
                        )
                        for attr in ('zeus_protection', 'sky_dodge', 'physical_immunity', 'divine_invincibility'):
                            if hasattr(enemy, attr):
                                delattr(enemy, attr)
            messages.append(f"{pet_combatant.name} masters the void! Enemy power is inverted into weakness!")
            pet_combatant.ultimate_ready = False
            
        # Eternal Night - ULTIMATE
        if ('eternal_night' in effects and 
            getattr(pet_combatant, 'ultimate_ready', False)):
            if hasattr(pet_combatant, 'team'):
                for ally in pet_combatant.team.combatants:
                    if ally.is_alive():
                        self._apply_timed_multiplier(
                            ally,
                            'eternal_night',
                            int(effects['eternal_night'].get('duration', 3)),
                            damage_mult=Decimal('1') + Decimal(str(effects['eternal_night']['team_dark_power'])),
                            armor_mult=Decimal('1.10'),
                        )
                        setattr(ally, 'bonus_lifesteal', Decimal(str(effects['eternal_night'].get('team_lifesteal', 0.15))))
            messages.append(f"{pet_combatant.name} brings Eternal Night! Darkness empowers the team!")
            pet_combatant.ultimate_ready = False
            
        # Lord of Shadows - ULTIMATE
        if ('lord_of_shadows' in effects and 
            getattr(pet_combatant, 'ultimate_ready', False)):
            current_skeletons = getattr(pet_combatant, 'skeleton_count', 0)
            max_skeletons = 2

            if current_skeletons < max_skeletons:
                skeleton_hp = pet_combatant.max_hp * Decimal(str(effects['lord_of_shadows'].get('skeleton_hp', 0.75)))
                skeleton_damage = pet_combatant.damage * Decimal(str(effects['lord_of_shadows'].get('skeleton_damage', 0.65)))
                skeleton_armor = pet_combatant.armor * Decimal(str(effects['lord_of_shadows'].get('skeleton_armor', 0.40)))
                setattr(pet_combatant, 'summon_skeleton', {
                    'hp': skeleton_hp,
                    'damage': skeleton_damage,
                    'armor': skeleton_armor,
                    'element': 'Dark'
                })
                setattr(pet_combatant, 'skeleton_count', current_skeletons + 1)
            else:
                messages.append(
                    f"{pet_combatant.name} tries to summon more skeletons, but the shadow army is at full strength! (2/2)"
                )

            duration = int(effects['lord_of_shadows'].get('duration', 3))
            if hasattr(pet_combatant, 'team'):
                for ally in pet_combatant.team.combatants:
                    if ally.is_alive():
                        self._apply_timed_multiplier(
                            ally,
                            'lord_of_shadows',
                            duration,
                            damage_mult=Decimal('1') + Decimal(str(effects['lord_of_shadows'].get('team_buff', 0.15))),
                            armor_mult=Decimal('1.10'),
                            luck_mult=Decimal('1.10'),
                        )
            if hasattr(target, 'team'):
                for enemy in target.team.combatants:
                    if enemy.is_alive():
                        self._apply_timed_multiplier(
                            enemy,
                            'lord_of_shadows_fear',
                            duration,
                            damage_mult=Decimal('1') - Decimal(str(effects['lord_of_shadows'].get('enemy_debuff', 0.15))),
                            luck_mult=Decimal('0.90'),
                        )
            messages.append(
                f"{pet_combatant.name} becomes Lord of Shadows! The shadow host rises and terror grips the battlefield!"
            )
            pet_combatant.ultimate_ready = False
            
        # 🌀 CORRUPTED SKILLS
        # Chaos Strike - random damage and element
        if 'chaos_strike' in effects:
            min_mult, max_mult = effects['chaos_strike']['damage_range']
            random_mult = random.uniform(min_mult, max_mult)
            modified_damage *= Decimal(str(random_mult))
            messages.append(f"{pet_combatant.name}'s Chaos Strike deals {random_mult:.1f}x damage!")
            
        # Reality Tear - ignore everything with 15% chance
        if 'reality_tear' in effects and random.randint(1, 100) <= int(effects['reality_tear'].get('chance', 15)):
            modified_damage *= Decimal(str(effects['reality_tear']['damage_multiplier']))
            setattr(target, 'ignore_all_defenses', True)
            setattr(target, 'ignore_shield_this_hit', True)
            messages.append(f"{pet_combatant.name} tears through reality itself!")
            
        # Apocalypse - ULTIMATE
        if ('apocalypse' in effects and 
            getattr(pet_combatant, 'ultimate_ready', False)):
            modified_damage *= Decimal(str(effects['apocalypse']['damage_multiplier']))
            # Create chaos realm
            setattr(pet_combatant, 'chaos_realm', True)
            messages.append(f"{pet_combatant.name} brings the Apocalypse! Reality crumbles!")
            pet_combatant.ultimate_ready = False
            
        # Corruption Mastery - ULTIMATE
        if ('corruption_mastery' in effects and 
            getattr(pet_combatant, 'ultimate_ready', False)):
            # Mind control all enemies
            if hasattr(target, 'team'):
                for enemy in target.team.combatants:
                    setattr(enemy, 'corrupted_mind', True)
            setattr(pet_combatant, 'corruption_immunity', True)
            messages.append(f"{pet_combatant.name} masters corruption! All minds bend to their will!")
            pet_combatant.ultimate_ready = False
            
        # VOID LORD - THE ULTIMATE ULTIMATE
        if ('void_lord' in effects and 
            getattr(pet_combatant, 'ultimate_ready', False)):
            modified_damage *= Decimal('3.0')  # 3x damage (strong but not broken)
            setattr(pet_combatant, 'void_lord_active', effects['void_lord']['duration'])
            setattr(pet_combatant, 'battlefield_control', True)
            setattr(target, 'void_marked', True)
            setattr(target, 'ignore_all_defenses', True)
            setattr(target, 'ignore_shield_this_hit', True)
            owner_combatant = self.find_owner_combatant(pet_combatant)
            if owner_combatant:
                self._apply_timed_multiplier(
                    owner_combatant,
                    'void_lord_blessing',
                    int(effects['void_lord'].get('duration', 3)),
                    damage_mult=Decimal('1') + Decimal(str(effects['void_lord'].get('owner_buff', 0.25))),
                )
            messages.append(f"{pet_combatant.name} becomes the VOID LORD! Dark power courses through them!")
            pet_combatant.ultimate_ready = False
            
        # 🌟 LIGHT ADDITIONAL SKILLS
        # Divine Wrath - dispel on hit (remove all buffs from target)
        if 'divine_wrath' in effects:
            # Remove beneficial effects from target
            for attr in ['speed_boost', 'damage_boost', 'armor_boost', 'zeus_protection', 'sky_dodge']:
                if hasattr(target, attr):
                    delattr(target, attr)
            messages.append(f"{pet_combatant.name}'s Divine Wrath dispels enemy buffs!")
            
        # 🌀 NEW CORRUPTED SKILLS - ATTACK EFFECTS
        # Void Touch - corrupt enemy stats permanently
        if 'void_touch' in effects:
            if not getattr(target, 'void_touched', False):
                stat_reduction = Decimal(str(effects['void_touch']['stat_corruption']))
                target.damage *= (Decimal('1') - stat_reduction)
                target.armor *= (Decimal('1') - stat_reduction)
                target.luck *= (Decimal('1') - stat_reduction)
                setattr(target, 'void_touched', True)
                messages.append(f"{pet_combatant.name}'s Void Touch corrupts {target.name}'s essence!")
             
        # Chaos Storm - AOE with random effects
        chaos_storm_cd = int(getattr(pet_combatant, 'chaos_storm_cooldown', 0))
        if ('chaos_storm' in effects and hasattr(target, 'team') and chaos_storm_cd <= 0 and
            random.randint(1, 100) <= effects['chaos_storm']['chance']):
            aoe_damage = modified_damage * Decimal(str(effects['chaos_storm']['aoe_multiplier']))
            for enemy in target.team.combatants:
                if enemy != target and enemy.is_alive():
                    enemy.take_damage(aoe_damage)
                    if random.randint(1, 100) <= effects['chaos_storm'].get('effect_chance', 35):
                        # Random chaos effect
                        chaos_effects = ['stunned', 'confused', 'weakened', 'slowed']
                        random_effect = random.choice(chaos_effects)
                        setattr(enemy, random_effect, 2)
            setattr(pet_combatant, 'chaos_storm_cooldown', int(effects['chaos_storm'].get('cooldown', 0)))
            messages.append(f"{pet_combatant.name}'s Chaos Storm erupts! (AOE + random chaos effects)")
             
        # Reality Distortion - swap stats or reverse damage
        reality_distortion_cd = int(getattr(pet_combatant, 'reality_distortion_cooldown', 0))
        if ('reality_distortion' in effects and reality_distortion_cd <= 0 and
            random.randint(1, 100) <= effects['reality_distortion'].get('chance', 20)):
            if random.random() < 0.5:  # 50% chance to swap stats
                target.damage, target.armor = target.armor, target.damage
                messages.append(f"{pet_combatant.name} distorts reality - {target.name}'s stats are swapped!")
            else:  # 50% chance to reverse damage (heal instead)
                heal_amount = modified_damage * Decimal('0.5')
                pet_combatant.heal(heal_amount)
                messages.append(f"Reality Distortion reverses damage into healing!")
            setattr(pet_combatant, 'reality_distortion_cooldown', int(effects['reality_distortion'].get('cooldown', 0)))
                 
        # Chaos Control - manipulate reality
        chaos_control_cd = int(getattr(pet_combatant, 'chaos_control_cooldown', 0))
        if ('chaos_control' in effects and chaos_control_cd <= 0 and
            random.randint(1, 100) <= effects['chaos_control'].get('chance', 12)):
            chaos_roll = random.randint(1, 3)
            if chaos_roll == 1 and hasattr(target, 'team'):  # Position swap
                allies = [a for a in target.team.combatants if a != target and a.is_alive()]
                if allies:
                    swap_target = random.choice(allies)
                    messages.append(f"Chaos Control swaps positions - attack hits {swap_target.name} instead!")
            elif chaos_roll == 2:  # Damage reverse
                heal_amount = modified_damage * Decimal('0.75')
                pet_combatant.heal(heal_amount)
                modified_damage *= Decimal('0.25')
                messages.append(f"Chaos Control reverses most damage into healing!")
            else:  # Reality control - double damage
                modified_damage *= Decimal('1.4')
                messages.append(f"Chaos Control amplifies reality - heavy damage!")
            setattr(pet_combatant, 'chaos_control_cooldown', int(effects['chaos_control'].get('cooldown', 0)))
                 
        # Corruption Wave - spreading stat debuff
        corruption_wave_cd = int(getattr(pet_combatant, 'corruption_wave_cooldown', 0))
        if ('corruption_wave' in effects and hasattr(target, 'team') and corruption_wave_cd <= 0 and
            random.randint(1, 100) <= effects['corruption_wave'].get('chance', 20)):
            # Primary target gets full debuff
            stat_reduction = Decimal(str(effects['corruption_wave']['stat_reduction']))
            if not getattr(target, 'corruption_wave_affected', False):
                target.damage *= (Decimal('1') - stat_reduction)
                target.armor *= (Decimal('1') - stat_reduction)
                target.luck *= (Decimal('1') - stat_reduction)
                setattr(target, 'corruption_wave_affected', True)
            
            # Spread to other enemies at half effectiveness
            corruption_spread = 0
            for enemy in target.team.combatants:
                if enemy != target and enemy.is_alive() and not getattr(enemy, 'corruption_wave_affected', False):
                    enemy.damage *= (Decimal('1') - stat_reduction * Decimal('0.5'))
                    enemy.armor *= (Decimal('1') - stat_reduction * Decimal('0.5'))
                    enemy.luck *= (Decimal('1') - stat_reduction * Decimal('0.5'))
                    setattr(enemy, 'corruption_wave_affected', True)
                    corruption_spread += 1
                    
            if corruption_spread > 0:
                messages.append(f"{pet_combatant.name}'s Corruption Wave spreads weakness to {corruption_spread + 1} enemies!")
            else:
                messages.append(f"{pet_combatant.name}'s Corruption Wave weakens {target.name}!")
            setattr(pet_combatant, 'corruption_wave_cooldown', int(effects['corruption_wave'].get('cooldown', 0)))
                
        # Corruption Mastery - mind control (ULTIMATE)
        if ('corruption_mastery' in effects and 
            getattr(pet_combatant, 'ultimate_ready', False)):
            # Mind control all enemies
            controlled_enemies = 0
            if hasattr(target, 'team'):
                for enemy in target.team.combatants:
                    if enemy.is_alive():
                        setattr(enemy, 'corrupted_mind', 3)  # 3 turns of mind control
                        setattr(enemy, 'mind_controller', pet_combatant)
                        controlled_enemies += 1
            
            # Grant corruption immunity
            setattr(pet_combatant, 'corruption_immunity', True)
            setattr(pet_combatant, 'debuff_immunity', True)
            
            messages.append(f"{pet_combatant.name} masters corruption! {controlled_enemies} minds bend to their will!")
            messages.append(f"{pet_combatant.name} becomes immune to all corruption and debuffs!")
            pet_combatant.ultimate_ready = False

        # Elemental affinities
        for effect_name, effect_data in effects.items():
            if effect_data.get('type') == 'elemental_bonus':
                if hasattr(target, 'element') and target.element in effect_data['elements']:
                    modified_damage *= (Decimal('1') + Decimal(str(effect_data['damage_bonus'])))
                    
        # Universal affinities
        if 'void_affinity' in effects:
            modified_damage *= (Decimal('1') + Decimal(str(effects['void_affinity']['universal_bonus'])))
            
        if 'corrupted_affinity' in effects:
            modified_damage *= (Decimal('1') + Decimal(str(effects['corrupted_affinity']['universal_damage'])))

        # Attacking Light's Guidance can blank one reactive defensive skill for this exchange.
        if ('lights_guidance' in effects and
            random.random() < self.LIGHTS_GUIDANCE_PROC_CHANCE):
            reactive_candidates = self._get_lights_guidance_candidates(
                target_effects,
                self.LIGHTS_GUIDANCE_REACTIVE_TYPES,
                self.LIGHTS_GUIDANCE_REACTIVE_SKILLS,
            )
            if self._has_exchange_reflection(target):
                reactive_candidates.append('armor_reflection')

            if reactive_candidates:
                countered_target_skill_name = random.choice(reactive_candidates)

                if countered_target_skill_name == 'armor_reflection':
                    setattr(pet_combatant, 'ignore_reflection_this_hit', True)
                    messages.append(
                        f"{pet_combatant.name}'s Light's Guidance counters "
                        f"{target.name}'s {self._format_skill_name(countered_target_skill_name)}!"
                    )
                    setattr(pet_combatant, 'lights_guidance_last_counter', countered_target_skill_name)
                else:
                    current_target_effects = getattr(target, 'skill_effects', None)
                    if isinstance(current_target_effects, dict) and countered_target_skill_name in current_target_effects:
                        filtered_target_effects = dict(current_target_effects)
                        filtered_target_effects.pop(countered_target_skill_name, None)

                        if not hasattr(target, 'lights_guidance_original_skill_effects'):
                            setattr(target, 'lights_guidance_original_skill_effects', current_target_effects)
                        target.skill_effects = filtered_target_effects

                        messages.append(
                            f"{pet_combatant.name}'s Light's Guidance counters "
                            f"{target.name}'s {self._format_skill_name(countered_target_skill_name)}!"
                        )
                        setattr(pet_combatant, 'lights_guidance_last_counter', countered_target_skill_name)

        # Restore any temporarily countered attacker skill for future attacks.
        if countered_attacker_skill_name and countered_attacker_skill_effect is not None:
            effects[countered_attacker_skill_name] = countered_attacker_skill_effect
            
        return modified_damage, messages
    
    def process_skill_effects_on_damage_taken(self, pet_combatant, attacker, damage):
        """Process skill effects when pet takes damage"""
        from decimal import Decimal
        
        if not hasattr(pet_combatant, 'skill_effects'):
            return damage, []
            
        modified_damage = Decimal(str(damage))  # Convert to Decimal to handle all operations
        effects = pet_combatant.skill_effects
        messages = []
        
        # Check for special immunities first
        divine_invincibility = getattr(pet_combatant, 'divine_invincibility', 0)
        if divine_invincibility > 0:
            messages.append(f"{pet_combatant.name} is protected by Divine Protection - no damage can touch them!")
            return 0, messages
            
        physical_immunity = getattr(pet_combatant, 'physical_immunity', 0)
        if physical_immunity > 0:
            setattr(pet_combatant, 'physical_immunity', physical_immunity - 1)
            messages.append(f"{pet_combatant.name} is immune to physical damage!")
            return 0, messages
            
        zeus_protection = getattr(pet_combatant, 'zeus_protection', 0)
        if zeus_protection > 0:
            modified_damage *= Decimal('0.7')  # 30% damage reduction
            setattr(pet_combatant, 'zeus_protection', zeus_protection - 1)
            messages.append(f"{pet_combatant.name} is protected by Zeus!")
            
        if getattr(pet_combatant, 'void_lord_active', 0) > 0:
            modified_damage *= Decimal('0.5')  # 50% damage reduction, not immunity
            messages.append(f"{pet_combatant.name}'s void aura reduces damage!")
        
        # 🔥 FIRE DEFENSIVE SKILLS
        # Fire Shield - chance to block
        if 'fire_shield' in effects and random.randint(1, 100) <= effects['fire_shield']['chance']:
            messages.append(f"{pet_combatant.name}'s Fire Shield blocks the attack!")
            return 0, messages
            
        # Molten Armor - reflect damage
        if 'molten_armor' in effects and random.randint(1, 100) <= effects['molten_armor']['chance']:
            reflect_damage = damage * Decimal(str(effects['molten_armor']['reflect_percent']))
            if hasattr(attacker, 'take_damage'):
                attacker.take_damage(reflect_damage)
                messages.append(f"{pet_combatant.name}'s Molten Armor reflects **{reflect_damage:.2f} damage**!")
                
        # Flame Barrier - shield
        if 'flame_barrier' in effects:
            flame_shield = self._to_decimal(getattr(pet_combatant, 'flame_shield', 0))
            if flame_shield > 0:
                absorbed = min(flame_shield, modified_damage)
                remaining_shield = flame_shield - absorbed
                setattr(pet_combatant, 'flame_shield', remaining_shield)
                if remaining_shield <= 0:
                    setattr(
                        pet_combatant,
                        'flame_shield_recharge',
                        max(
                            int(getattr(pet_combatant, 'flame_shield_recharge', 0) or 0),
                            int(effects['flame_barrier'].get('recharge_turns', 1)),
                        ),
                    )
                modified_damage -= absorbed
                messages.append(f"Flame Barrier absorbs **{absorbed:.2f} damage**!")

        # Eternal Flame - pet survives lethal hits while owner is healthy
        if 'eternal_flame' in effects and modified_damage >= pet_combatant.hp:
            owner_combatant = self.find_owner_combatant(pet_combatant)
            if owner_combatant and getattr(owner_combatant, 'max_hp', 0):
                owner_hp_ratio = self._to_decimal(owner_combatant.hp) / self._to_decimal(owner_combatant.max_hp, '1')
                threshold = Decimal(str(effects['eternal_flame'].get('owner_hp_threshold', 0.5)))
                if owner_hp_ratio >= threshold:
                    modified_damage = max(Decimal('0'), self._to_decimal(pet_combatant.hp) - Decimal('1'))
                    messages.append(
                        f"{pet_combatant.name}'s Eternal Flame refuses to go out while their owner stands strong!"
                    )
                
        # Phoenix Rebirth - death prevention with revival
        if ('phoenix_rebirth' in effects and modified_damage >= pet_combatant.hp and
            not getattr(pet_combatant, 'phoenix_used', False)):
            revival_hp = pet_combatant.max_hp * Decimal(str(effects['phoenix_rebirth']['revive_hp_percent']))
            pet_combatant.hp = revival_hp
            setattr(pet_combatant, 'phoenix_used', True)
            setattr(pet_combatant, 'phoenix_resistance', 3)  # 3 turns of enhanced resistance
            self._apply_timed_multiplier(
                pet_combatant,
                'phoenix_rebirth',
                int(effects['phoenix_rebirth'].get('duration', 2)),
                damage_mult=Decimal('1') + Decimal(str(effects['phoenix_rebirth'].get('reborn_power', 0.30))),
                armor_mult=Decimal('1.15'),
                luck_mult=Decimal('1.10'),
            )
            messages.append(
                f"🔥 {pet_combatant.name} rises from the ashes with Phoenix Rebirth! "
                f"Revived with **{revival_hp:.2f} HP** and reborn in blazing power!"
            )
            return 0, messages  # No damage taken this hit
            
        # Inferno Mastery - fire resistance
        if ('inferno_mastery' in effects and hasattr(attacker, 'element') and 
            attacker.element == 'Fire'):
            # Resist fire damage
            fire_resistance = Decimal(str(effects['inferno_mastery']['fire_resistance']))
            modified_damage *= (Decimal('1') - fire_resistance)
            messages.append(
                f"{pet_combatant.name}'s Inferno Mastery resists fire damage! "
                f"(-{fire_resistance * Decimal('100'):.0f}%)"
            )
            
        # Phoenix Resistance - enhanced resistance after revival
        phoenix_resistance = getattr(pet_combatant, 'phoenix_resistance', 0)
        if phoenix_resistance > 0:
            # Strong resistance to all damage types
            resistance_amount = Decimal('0.5')  # 50% damage reduction
            modified_damage *= (Decimal('1') - resistance_amount)
            messages.append(f"{pet_combatant.name}'s Phoenix flames provide strong resistance! (-50% damage)")

        # Wind's Guidance - once per pet turn, blow a heavy hit off course
        if (
            'winds_guidance' in effects
            and int(getattr(pet_combatant, 'winds_guidance_ready', 0) or 0) > 0
            and random.randint(1, 100) <= int(effects['winds_guidance'].get('chance', 35))
        ):
            setattr(pet_combatant, 'winds_guidance_ready', 0)
            prevented_damage = modified_damage * Decimal(str(effects['winds_guidance'].get('damage_reduction', 0.50)))
            modified_damage -= prevented_damage
            reflected_damage = prevented_damage * Decimal(str(effects['winds_guidance'].get('reflect_fraction', 0.60)))
            if attacker is not None and hasattr(attacker, 'take_damage') and getattr(attacker, 'is_alive', lambda: True)():
                attacker.take_damage(reflected_damage)
                messages.append(
                    f"{pet_combatant.name}'s Wind's Guidance diverts the blow! "
                    f"**{reflected_damage:.2f} damage** whips back into {attacker.name}."
                )
            else:
                messages.append(f"{pet_combatant.name}'s Wind's Guidance turns aside the attack!")
                
        # 💧 WATER DEFENSIVE SKILLS
        # Guardian Wave - damage reduction
        if 'guardian_wave' in effects and random.randint(1, 100) <= effects['guardian_wave']['chance']:
            reduction = Decimal(str(effects['guardian_wave']['damage_reduction']))
            modified_damage *= (Decimal('1') - reduction)
            messages.append(f"{pet_combatant.name}'s Guardian Wave reduces damage by {reduction*Decimal('100'):.0f}%!")
            
        # Fluid Movement - dodge
        if 'fluid_movement' in effects and random.randint(1, 100) <= effects['fluid_movement']['chance']:
            messages.append(f"{pet_combatant.name} flows like water, dodging the attack!")
            return 0, messages
            
        # ⚡ ELECTRIC DEFENSIVE SKILLS
        # Energy Shield - shield
        if 'energy_shield' in effects:
            energy_barrier = self._to_decimal(getattr(pet_combatant, 'energy_barrier', 0))
            if energy_barrier > 0:
                absorbed = min(energy_barrier, modified_damage)
                remaining_barrier = energy_barrier - absorbed
                setattr(pet_combatant, 'energy_barrier', remaining_barrier)
                if remaining_barrier <= 0:
                    setattr(
                        pet_combatant,
                        'energy_barrier_recharge',
                        max(
                            int(getattr(pet_combatant, 'energy_barrier_recharge', 0) or 0),
                            int(effects['energy_shield'].get('recharge_turns', 1)),
                        ),
                    )
                modified_damage -= absorbed
                messages.append(f"Energy Shield absorbs **{absorbed:.2f} damage**!")
                
        # Lightning Rod - absorb electric damage
        if ('lightning_rod' in effects and hasattr(attacker, 'element') and 
            attacker.element == effects['lightning_rod']['absorb_element']):
            # Absorb damage and gain attack bonus
            pet_combatant.damage *= (Decimal('1') + Decimal(str(effects['lightning_rod']['attack_bonus'])))
            messages.append(f"{pet_combatant.name} absorbs electric energy and grows stronger!")
            return 0, messages
            
        # 🌿 NATURE DEFENSIVE SKILLS
        # Thorn Shield - poison reflect
        if 'thorn_shield' in effects:
            poison_damage = damage * Decimal(str(effects['thorn_shield']['reflect_percent']))
            if hasattr(attacker, 'take_damage'):
                attacker.take_damage(poison_damage)
                setattr(attacker, 'poisoned', 3)  # 3 turns of poison
                messages.append(f"{pet_combatant.name}'s Thorn Shield poisons the attacker!")
                
        # 💨 WIND DEFENSIVE SKILLS
        # Air Shield - projectile immunity
        if 'air_shield' in effects:
            # Assume ranged attacks are "projectiles"
            if hasattr(attacker, 'element') and attacker.element in ['Electric', 'Fire']:
                messages.append(f"{pet_combatant.name}'s Air Shield deflects the projectile!")
                return 0, messages
            else:
                modified_damage *= (Decimal('1') - Decimal(str(effects['air_shield']['other_reduction'])))
                messages.append(f"Air Shield reduces non-projectile damage!")
                
        # Wind Walk - mobility dodge bonus
        if 'wind_walk' in effects:
            dodge_roll = random.random()
            if dodge_roll < effects['wind_walk']['dodge_bonus']:
                messages.append(f"{pet_combatant.name} dances on the wind, avoiding damage!")
                return 0, messages
                
        # 🌟 LIGHT DEFENSIVE SKILLS
        # Divine Shield - resistance
        if 'divine_shield' in effects:
            if hasattr(attacker, 'element') and attacker.element in ['Dark', 'Corrupted']:
                modified_damage *= (Decimal('1') - Decimal(str(effects['divine_shield']['dark_resistance'])))
                messages.append(f"Divine Shield provides strong protection against darkness!")
            else:
                modified_damage *= (Decimal('1') - Decimal(str(effects['divine_shield']['general_resistance'])))
                messages.append(f"Divine Shield offers minor protection!")
                
        # 🌑 DARK DEFENSIVE SKILLS
        # Dark Shield - absorb damage and briefly empower the pet
        if 'dark_shield' in effects:
            absorbed = modified_damage * Decimal(str(effects['dark_shield']['absorb_percent']))
            modified_damage -= absorbed
            self._apply_timed_multiplier(
                pet_combatant,
                'dark_shield',
                int(effects['dark_shield']['duration']),
                damage_mult=Decimal('1') + Decimal(str(effects['dark_shield']['attack_bonus'])),
            )
            messages.append(
                f"{pet_combatant.name}'s Dark Shield absorbs **{absorbed:.2f} damage** and fuels their next assaults!"
            )
            
        # Shadow Form - physical immunity
        shadow_form_turns = getattr(pet_combatant, 'shadow_form_turns', 0)
        if (shadow_form_turns > 0 and
            (not hasattr(attacker, 'element') or attacker.element != 'Light')):
            setattr(pet_combatant, 'shadow_form_turns', shadow_form_turns - 1)
            messages.append(f"{pet_combatant.name} is in Shadow Form - physical attacks pass through!")
            return 0, messages
            
        # Soul Bind - damage redistribution
        if ('soul_bind' in effects and hasattr(pet_combatant, 'team')):
            shared_damage = modified_damage * Decimal(str(effects['soul_bind']['damage_share']))
            remaining_damage = modified_damage - shared_damage
            # Distribute shared damage among team
            alive_allies = [a for a in pet_combatant.team.combatants if a != pet_combatant and a.is_alive()]
            if alive_allies:
                damage_per_ally = shared_damage / Decimal(str(len(alive_allies)))
                for ally in alive_allies:
                    ally.take_damage(damage_per_ally)
                modified_damage = remaining_damage
                messages.append(f"Soul Bind shares **{shared_damage:.2f} damage** among allies!")
                
        # 🌀 CORRUPTED DEFENSIVE SKILLS
        # Corruption Shield - corrupt attackers
        if 'corruption_shield' in effects and random.random() < effects['corruption_shield']['corrupt_attackers']:
            setattr(attacker, 'corrupted', 3)  # 3 turns of corruption
            messages.append(f"{pet_combatant.name}'s Corruption Shield infects the attacker!")
            
        # Corrupt Shield - absorb damage and corrupt
        if 'corrupt_shield' in effects:
            absorbed = modified_damage * Decimal(str(effects['corrupt_shield'].get('absorb_percent', 0.20)))
            modified_damage -= absorbed
            if random.random() < effects['corrupt_shield']['corruption_chance']:
                setattr(attacker, 'corrupted', 3)
                messages.append(f"{pet_combatant.name}'s Corrupt Shield absorbs damage and corrupts the attacker!")
            else:
                messages.append(f"{pet_combatant.name}'s Corrupt Shield absorbs **{absorbed:.2f} damage**!")
            
        # Void Walk - reality phase dodge
        if ('void_walk' in effects and 
            random.random() < effects['void_walk']['dodge_chance']):
            messages.append(f"{pet_combatant.name} phases through reality, avoiding damage!")
            return 0, messages
            
        # Void Sight - enhanced dodge from seeing through illusions
        if ('void_sight' in effects and 
            random.random() < effects['void_sight']['dodge_bonus']):
            messages.append(f"{pet_combatant.name}'s Void Sight sees through the attack, dodging perfectly!")
            return 0, messages
            
        # Eternal Decay - corruption immortality
        if ('eternal_decay' in effects and modified_damage >= pet_combatant.hp):
            # Check for corrupted enemies to feed on
            corrupted_count = 0
            if hasattr(pet_combatant, 'enemy_team'):
                for enemy in pet_combatant.enemy_team.combatants:
                    if hasattr(enemy, 'corrupted') and enemy.is_alive():
                        corrupted_count += 1
                        
            if corrupted_count > 0:
                # Prevent death and heal based on corruption
                heal_amount = corrupted_count * pet_combatant.max_hp * Decimal('0.1')  # 10% per corrupted enemy
                modified_damage = pet_combatant.hp - 1  # Stay at 1 HP
                pet_combatant.heal(heal_amount)
                setattr(pet_combatant, 'corruption_immortal', 1)  # Flag for this turn
                messages.append(f"{pet_combatant.name} feeds on corruption and refuses to die! Healed **{heal_amount:.2f} HP**!")
                
        # Corruption immunity check
        if (getattr(pet_combatant, 'corruption_immunity', False) or 
            getattr(pet_combatant, 'debuff_immunity', False)):
            # Remove status effect components from damage
            if hasattr(attacker, 'poisoned') or hasattr(attacker, 'corrupted'):
                modified_damage *= Decimal('0.8')  # 20% resistance to debuff sources
                messages.append(f"{pet_combatant.name}'s corruption immunity resists status effects!")
            
        # 🌿 NATURE DEFENSIVE SKILLS
        # Forest Camouflage - avoid targeting (chance to be completely ignored by attacks)
        if ('forest_camouflage' in effects and 
            random.randint(1, 100) <= effects['forest_camouflage']['chance']):
            messages.append(f"{pet_combatant.name} uses Forest Camouflage to avoid being targeted!")
            return 0, messages
            
        # Symbiotic Bond - share damage with owner
        if ('symbiotic_bond' in effects and hasattr(pet_combatant, 'owner')):
            share_percent = Decimal(str(effects['symbiotic_bond']['share_percent']))
            shared_damage = modified_damage * share_percent
            remaining_damage = modified_damage - shared_damage
            
            # Apply shared damage to owner (but not below 1 HP)
            owner_current_hp = Decimal(str(getattr(pet_combatant.owner, 'hp', 0)))
            owner_min_hp = Decimal('1')
            actual_shared = min(shared_damage, owner_current_hp - owner_min_hp)
            
            if actual_shared > 0:
                setattr(pet_combatant.owner, 'hp', owner_current_hp - actual_shared)
                modified_damage = remaining_damage + (shared_damage - actual_shared)  # Return unshared portion
                messages.append(f"{pet_combatant.name}'s Symbiotic Bond shares **{actual_shared:.2f} damage** with their owner!")
            else:
                messages.append(f"{pet_combatant.name}'s owner is too weak to share the burden!")
                # No damage sharing when owner is at 1 HP
            
        # 💨 WIND DEFENSIVE SKILLS  
        # Wind Tunnel - positioning (manipulate distance to reduce damage)
        if 'wind_tunnel' in effects:
            modified_damage *= (
                Decimal('1') - Decimal(str(effects['wind_tunnel'].get('damage_reduction', 0.30)))
            )
            messages.append(f"{pet_combatant.name} uses Wind Tunnel to reposition and reduce damage!")
            
        # Air Shield - enhanced version with Air Currents synergy
        if 'air_shield' in effects:
            # Assume ranged attacks are "projectiles" 
            if hasattr(attacker, 'element') and attacker.element in ['Electric', 'Fire']:
                messages.append(f"{pet_combatant.name}'s Air Shield deflects the projectile!")
                return 0, messages
            else:
                modified_damage *= (Decimal('1') - Decimal(str(effects['air_shield']['other_reduction'])))
                messages.append(f"Air Shield reduces non-projectile damage!")
            
        # Special defensive conditions
        if getattr(pet_combatant, 'sky_dodge_duration', 0) > 0:
            if random.random() < getattr(pet_combatant, 'sky_dodge', 0):
                messages.append(f"{pet_combatant.name} blessed by the sky, dodges with divine grace!")
                return 0, messages
                
        if getattr(pet_combatant, 'debuff_immunity', False):
            # Remove any negative effects from damage
            for attr in ['stunned', 'poisoned', 'corrupted', 'slowed']:
                if hasattr(pet_combatant, attr):
                    delattr(pet_combatant, attr)
                    
        return max(Decimal('0'), modified_damage), messages
    
    def apply_void_affinity_protection(self, pet_combatant, element_mod):
        """Apply Void Affinity protection - prevent negative elemental modifiers"""
        if not hasattr(pet_combatant, 'skill_effects'):
            return element_mod
            
        effects = pet_combatant.skill_effects
        
        # Check for void affinity or corrupted affinity
        if 'void_affinity' in effects or 'corrupted_affinity' in effects:
            # Prevent negative modifiers (no weaknesses)
            return max(element_mod, 0)
            
        return element_mod
    
    def process_skill_effects_per_turn(self, pet_combatant):
        """Process skill effects that trigger each turn"""
        if not hasattr(pet_combatant, 'skill_effects'):
            return []
            
        effects = pet_combatant.skill_effects
        messages = []
        
        # Check for ultimate activation
        if (hasattr(pet_combatant, 'ultimate_threshold') and 
            not getattr(pet_combatant, 'ultimate_activated', False)):
            hp_ratio = pet_combatant.hp / pet_combatant.max_hp
            if hp_ratio <= pet_combatant.ultimate_threshold:
                setattr(pet_combatant, 'ultimate_ready', True)
                setattr(pet_combatant, 'ultimate_activated', True)
                messages.append(f"{pet_combatant.name}'s ultimate power awakens!")
        
        owner_combatant = self.find_owner_combatant(pet_combatant) if hasattr(pet_combatant, 'owner') else None
        team_combatants = list(getattr(getattr(pet_combatant, 'team', None), 'combatants', []))
        enemy_combatants = list(getattr(getattr(pet_combatant, 'enemy_team', None), 'combatants', []))

        self._tick_simple_duration(
            pet_combatant,
            'void_lord_active',
            messages,
            fade_message=f"{pet_combatant.name}'s Void Lord power fades...",
            clear_attrs=['battlefield_control'],
        )
        self._tick_simple_duration(
            pet_combatant,
            'phoenix_resistance',
            messages,
            fade_message=f"{pet_combatant.name}'s phoenix resistance fades...",
        )
        self._tick_simple_duration(
            pet_combatant,
            'inferno_mastery_turns',
            messages,
            fade_message=f"{pet_combatant.name}'s infernal overdrive cools.",
        )
        self._tick_simple_duration(
            pet_combatant,
            'storm_lord_active',
            messages,
            clear_attrs=['battlefield_control'],
        )
        self._tick_simple_duration(
            pet_combatant,
            'void_pact_duration',
            messages,
            clear_attrs=['void_pact_active'],
        )
        self._tick_timed_multiplier(pet_combatant, 'dark_shield', messages)
        self._tick_timed_multiplier(pet_combatant, 'growth_spurt', messages)
        self._tick_timed_multiplier(pet_combatant, 'phoenix_rebirth', messages)
        self._tick_timed_multiplier(
            pet_combatant,
            'dark_ritual',
            messages,
            extra_attrs=['dark_ritual_lifesteal'],
        )
        if 'flame_barrier' in effects:
            self._tick_barrier_recharge(
                pet_combatant,
                'flame_shield',
                'flame_shield_recharge',
                effects['flame_barrier']['shield_multiplier'],
                effects['flame_barrier'].get('restore_ratio', 0.50),
                messages,
                'Flame Barrier',
            )
        if 'energy_shield' in effects:
            self._tick_barrier_recharge(
                pet_combatant,
                'energy_barrier',
                'energy_barrier_recharge',
                effects['energy_shield']['shield_multiplier'],
                effects['energy_shield'].get('restore_ratio', 0.60),
                messages,
                'Energy Shield',
            )

        if owner_combatant:
            self._tick_timed_multiplier(
                owner_combatant,
                'power_surge',
                messages,
                fade_message=f"{pet_combatant.name}'s Power Surge fades from their owner.",
            )
            self._tick_timed_multiplier(
                owner_combatant,
                'overcharge',
                messages,
                fade_message=f"{pet_combatant.name}'s Overcharge fades from their owner.",
                extra_attrs=['overcharge_active'],
            )
            self._tick_timed_multiplier(
                owner_combatant,
                'dark_pact',
                messages,
                fade_message=f"{pet_combatant.name}'s Dark Pact fades from their owner.",
                extra_attrs=['dark_pact_active'],
            )
            self._tick_timed_multiplier(owner_combatant, 'void_lord_blessing', messages)
            self._tick_timed_multiplier(owner_combatant, 'void_mastery_reality', messages)
            self._tick_simple_duration(
                owner_combatant,
                'water_immortality_duration',
                messages,
                fade_message=f"{owner_combatant.name}'s Immortal Waters blessing fades.",
                clear_attrs=['water_immortality'],
            )

        for ally in team_combatants:
            self._tick_timed_multiplier(ally, 'inferno_mastery_aura', messages)
            self._tick_timed_multiplier(ally, 'sun_gods_blessing', messages)
            self._tick_timed_multiplier(ally, 'poseidons_call', messages)
            self._tick_timed_multiplier(ally, 'storm_lord', messages)
            self._tick_timed_multiplier(
                ally,
                'infinite_energy',
                messages,
                extra_attrs=['unlimited_abilities'],
            )
            self._tick_timed_multiplier(ally, 'zeus_wrath', messages)
            self._tick_timed_multiplier(ally, 'natures_blessing', messages)
            self._tick_timed_multiplier(ally, 'world_trees_gift', messages)
            self._tick_timed_multiplier(ally, 'lord_of_shadows', messages)
            self._tick_timed_multiplier(ally, 'air_currents', messages)
            self._tick_timed_multiplier(ally, 'freedoms_call', messages)
            self._tick_timed_multiplier(ally, 'storm_lord_wind_ally', messages)
            self._tick_timed_multiplier(ally, 'void_pact_ally', messages)
            self._tick_timed_multiplier(
                ally,
                'end_of_days_blessing',
                messages,
                extra_attrs=['chaos_powers', 'chaos_damage_immunity', 'reality_break_stacks'],
            )
            self._tick_timed_multiplier(ally, 'divine_favor_damage', messages)
            self._tick_timed_multiplier(ally, 'divine_favor_armor', messages)
            self._tick_timed_multiplier(ally, 'divine_favor_luck', messages)
            self._tick_timed_multiplier(
                ally,
                'celestial_blessing',
                messages,
                extra_attrs=['physical_immunity'],
            )
            self._tick_timed_multiplier(
                ally,
                'eternal_night',
                messages,
                extra_attrs=['bonus_lifesteal'],
            )
            self._tick_timed_multiplier(ally, 'zephyrs_dance', messages)
            self._tick_simple_duration(ally, 'storm_lord_haste', messages)
            self._tick_simple_duration(
                ally,
                'air_currents_duration',
                messages,
                clear_attrs=['air_currents_boost'],
            )
            self._tick_simple_duration(
                ally,
                'freedom_boost_duration',
                messages,
                clear_attrs=['freedom_boost'],
            )
            self._tick_simple_duration(
                ally,
                'sky_dodge_duration',
                messages,
                clear_attrs=['sky_dodge'],
            )
            self._tick_simple_duration(
                ally,
                'sky_haste_duration',
                messages,
                clear_attrs=['sky_haste'],
            )
            self._tick_simple_duration(
                ally,
                'zephyr_speed_duration',
                messages,
                clear_attrs=['zephyr_speed'],
            )
            self._tick_simple_duration(ally, 'debuff_immunity', messages)
            self._tick_simple_duration(ally, 'zeus_protection', messages)
            self._tick_simple_duration(ally, 'physical_immunity', messages)
            self._tick_simple_duration(
                ally,
                'divine_invincibility',
                messages,
                clear_attrs=['blessed_by_light'],
            )

        for enemy in enemy_combatants:
            self._tick_timed_multiplier(enemy, 'decay_touch', messages)
            self._tick_timed_multiplier(enemy, 'poseidons_call_curse', messages)
            self._tick_timed_multiplier(enemy, 'electromagnetic_field', messages)
            self._tick_timed_multiplier(enemy, 'gale_force', messages)
            self._tick_timed_multiplier(enemy, 'light_beam', messages)
            self._tick_timed_multiplier(enemy, 'world_trees_gift_curse', messages)
            self._tick_timed_multiplier(enemy, 'lord_of_shadows_fear', messages)
            self._tick_timed_multiplier(enemy, 'vine_whip', messages)
            self._tick_timed_multiplier(enemy, 'wind_shear', messages)
            self._tick_timed_multiplier(enemy, 'void_pact_enemy', messages)
            self._tick_timed_multiplier(enemy, 'storm_lord_wind', messages)
            self._tick_timed_multiplier(enemy, 'zephyrs_dance_slow', messages)
            self._tick_timed_multiplier(enemy, 'void_mastery', messages)
            self._tick_timed_multiplier(enemy, 'end_of_days_curse', messages)
            self._tick_simple_duration(enemy, 'storm_dominated', messages)
            self._tick_simple_duration(
                enemy,
                'zephyr_slow_duration',
                messages,
                clear_attrs=['zephyr_slow'],
            )

        # 🔥 FIRE PER-TURN EFFECTS
        # Warmth - heal owner on attack
        if (
            'warmth' in effects
            and owner_combatant
            and getattr(pet_combatant, 'attacked_this_turn', False)
        ):
            heal_amount = self._scaled_heal(
                pet_combatant,
                owner_combatant,
                effects['warmth']['heal_percent'],
            )
            owner_combatant.heal(heal_amount)
            messages.append(f"{pet_combatant.name}'s Warmth restores **{heal_amount:.2f} HP** to their owner!")
        
        # 💧 WATER PER-TURN EFFECTS
        # Healing Rain - team healing
        if 'healing_rain' in effects and team_combatants:
            for ally in team_combatants:
                if ally.is_alive():
                    heal_amount = self._scaled_heal(
                        pet_combatant,
                        ally,
                        effects['healing_rain']['heal_percent'],
                    )
                    ally.heal(heal_amount)
            messages.append(f"{pet_combatant.name}'s Healing Rain restores the team.")
            
        # Life Spring - lifesteal to owner
        if ('life_spring' in effects and owner_combatant and getattr(pet_combatant, 'attacked_this_turn', False)):
            if hasattr(owner_combatant, 'heal'):
                heal_amount = pet_combatant.damage * Decimal(str(effects['life_spring']['heal_percent']))
                owner_combatant.heal(heal_amount)
                messages.append(f"Life Spring flows healing energy to {pet_combatant.name}'s owner!")
            
        # Purify - remove debuffs
        if 'purify' in effects and owner_combatant:
            removable_debuffs = [
                debuff for debuff in ['poisoned', 'stunned', 'corrupted', 'burning', 'paralyzed']
                if hasattr(owner_combatant, debuff)
            ]
            if removable_debuffs:
                removed_debuff = random.choice(removable_debuffs)
                delattr(owner_combatant, removed_debuff)
                messages.append(f"Purify cleanses {owner_combatant.name} of {removed_debuff}!")
                    
        # Immortal Waters - owner immortality
        if ('immortal_waters' in effects and owner_combatant and getattr(pet_combatant, 'ultimate_ready', False)):
            duration = int(effects['immortal_waters'].get('duration', 2))
            setattr(owner_combatant, 'water_immortality', True)
            setattr(owner_combatant, 'water_immortality_duration', duration)
            heal_amount = self._scaled_heal(
                pet_combatant,
                owner_combatant,
                Decimal('0.25'),
                burst=True,
            )
            owner_combatant.heal(heal_amount)
            messages.append(f"{pet_combatant.name} invokes Immortal Waters! {owner_combatant.name} cannot fall for {duration} turns!")
            pet_combatant.ultimate_ready = False
            
        # Tidal Force is resolved when the affected combatant attempts to act.
            
        # ⚡ ELECTRIC PER-TURN EFFECTS
        # Quick Charge - persistent initiative lock.
        if 'quick_charge' in effects:
            setattr(pet_combatant, 'quick_charge_active', True)
                        
        # Power Surge - owner attack bonus
        if ('power_surge' in effects and owner_combatant and getattr(pet_combatant, 'attacked_this_turn', False)):
            if hasattr(owner_combatant, 'damage'):
                self._apply_timed_multiplier(
                    owner_combatant,
                    'power_surge',
                    int(effects['power_surge']['duration']),
                    damage_mult=Decimal('1') + Decimal(str(effects['power_surge']['attack_bonus'])),
                )
                messages.append(f"Power Surge electrifies {pet_combatant.name}'s owner!")
            
        # Battery Life - now handled in pets system for skill learning costs
        # No battle effect needed
                    
        # Electromagnetic Field - enemy accuracy reduction
        if ('electromagnetic_field' in effects and enemy_combatants):
            for enemy in enemy_combatants:
                if enemy.is_alive():
                    self._apply_timed_multiplier(
                        enemy,
                        'electromagnetic_field',
                        int(effects['electromagnetic_field'].get('duration', 2)),
                        luck_mult=Decimal('1') - Decimal(str(effects['electromagnetic_field']['accuracy_reduction'])),
                    )
            messages.append(f"{pet_combatant.name}'s Electromagnetic Field disrupts enemy accuracy!")
            
        # Overcharge - sacrifice HP for owner damage boost
        if ('overcharge' in effects and owner_combatant):
            current_hp_ratio = pet_combatant.hp / pet_combatant.max_hp if pet_combatant.max_hp else Decimal('0')
            if (
                current_hp_ratio <= Decimal('0.60')
                and not getattr(owner_combatant, 'overcharge_active', False)
                and not getattr(pet_combatant, 'overcharge_used', False)
            ):
                sacrifice_hp = pet_combatant.max_hp * Decimal(str(effects['overcharge']['hp_sacrifice']))
                current_hp = Decimal(str(getattr(pet_combatant, 'hp', 0)))
                
                if current_hp > sacrifice_hp:
                    setattr(pet_combatant, 'hp', current_hp - sacrifice_hp)
                    setattr(owner_combatant, 'overcharge_active', True)
                    setattr(pet_combatant, 'overcharge_used', True)
                    self._apply_timed_multiplier(
                        owner_combatant,
                        'overcharge',
                        int(effects['overcharge']['duration']),
                        damage_mult=Decimal('1') + Decimal(str(effects['overcharge']['owner_buff'])),
                        armor_mult=Decimal('1') + Decimal(str(effects['overcharge']['owner_buff'])),
                        luck_mult=Decimal('1') + Decimal(str(effects['overcharge']['owner_buff'])),
                    )
                    messages.append(f"{pet_combatant.name} overcharges! Sacrifices **{sacrifice_hp:.2f} HP** to empower their owner!")
        
        # 🌿 NATURE PER-TURN EFFECTS
        # Natural Healing - regeneration
        if 'natural_healing' in effects:
            heal_amount = self._scaled_heal(
                pet_combatant,
                pet_combatant,
                effects['natural_healing']['heal_percent'],
                self_target=True,
            )
            pet_combatant.heal(heal_amount)
            messages.append(f"{pet_combatant.name} naturally heals **{heal_amount:.2f} HP**!")
            
            # Check for Symbiotic Bond healing sharing
            if ('symbiotic_bond' in effects and owner_combatant and hasattr(owner_combatant, 'heal') and hasattr(owner_combatant, 'user')):
                share_percent = Decimal(str(effects['symbiotic_bond']['share_percent']))
                shared_heal = heal_amount * share_percent
                owner_combatant.heal(shared_heal)
                messages.append(f"Symbiotic Bond shares **{shared_heal:.2f} healing** with {owner_combatant.user.display_name}!")
            
        # Growth Spurt - stacking stats
        if 'growth_spurt' in effects:
            if not hasattr(pet_combatant, 'growth_stacks'):
                pet_combatant.growth_stacks = 0
            if pet_combatant.growth_stacks < effects['growth_spurt']['max_stacks']:
                pet_combatant.growth_stacks += 1
            total_bonus = Decimal(str(effects['growth_spurt']['stat_increase'])) * Decimal(
                str(pet_combatant.growth_stacks)
            )
            self._clear_timed_multiplier(pet_combatant, 'growth_spurt')
            self._apply_timed_multiplier(
                pet_combatant,
                'growth_spurt',
                2,
                damage_mult=Decimal('1') + total_bonus,
                armor_mult=Decimal('1') + total_bonus,
                luck_mult=Decimal('1') + total_bonus,
            )
            messages.append(
                f"{pet_combatant.name} grows stronger! "
                f"(Stack {pet_combatant.growth_stacks}/{effects['growth_spurt']['max_stacks']})"
            )
                
        # Life Force - HP transfer to owner
        if ('life_force' in effects and owner_combatant and hasattr(owner_combatant, 'heal')):
            owner_hp_ratio = owner_combatant.hp / owner_combatant.max_hp if owner_combatant.max_hp else Decimal('1')
            uses_left = int(getattr(pet_combatant, 'life_force_uses_left', effects['life_force'].get('uses', 1)) or 0)
            if owner_hp_ratio <= Decimal(str(effects['life_force'].get('owner_threshold', 0.60))) and uses_left > 0:
                sacrifice_hp = pet_combatant.max_hp * Decimal(str(effects['life_force']['hp_sacrifice']))
                current_hp = Decimal(str(getattr(pet_combatant, 'hp', 0)))
                if current_hp > sacrifice_hp:
                    setattr(pet_combatant, 'hp', current_hp - sacrifice_hp)
                    heal_owner = self._scaled_heal(
                        pet_combatant,
                        owner_combatant,
                        effects['life_force']['owner_heal'],
                        burst=True,
                    )
                    owner_combatant.heal(heal_owner)
                    setattr(pet_combatant, 'life_force_uses_left', uses_left - 1)
                    messages.append(f"{pet_combatant.name} sacrifices life force to heal their owner!")
                
        # Nature's Blessing - environmental bonus
        if ('natures_blessing' in effects and team_combatants):
            for ally in team_combatants:
                if ally.is_alive():
                    self._apply_timed_multiplier(
                        ally,
                        'natures_blessing',
                        int(effects['natures_blessing'].get('duration', 2)),
                        damage_mult=Decimal('1') + Decimal(str(effects['natures_blessing']['team_buff'])),
                        armor_mult=Decimal('1') + Decimal(str(effects['natures_blessing']['team_buff'])),
                        luck_mult=Decimal('1') + Decimal(str(effects['natures_blessing']['team_buff'])),
                    )
            messages.append(f"Nature's Blessing empowers the team!")
            
        # Gaia's Wrath - healing over time
        gaias_wrath_duration = getattr(pet_combatant, 'gaias_wrath_duration', 0)
        if gaias_wrath_duration > 0:
            heal_percent = getattr(pet_combatant, 'gaias_wrath_heal', 0.07)
            heal_amount = self._scaled_heal(
                pet_combatant,
                pet_combatant,
                heal_percent,
                self_target=True,
            )
            pet_combatant.heal(heal_amount)
            messages.append(f"{pet_combatant.name} draws strength from Gaia! Healed **{heal_amount:.2f} HP** ({heal_percent*100:.0f}%)")
            
            # Check for Symbiotic Bond healing sharing
            if (
                hasattr(pet_combatant, 'skill_effects')
                and 'symbiotic_bond' in pet_combatant.skill_effects
                and owner_combatant
                and hasattr(owner_combatant, 'heal')
                and hasattr(owner_combatant, 'user')
            ):
                share_percent = Decimal(str(pet_combatant.skill_effects['symbiotic_bond']['share_percent']))
                shared_heal = heal_amount * share_percent
                owner_combatant.heal(shared_heal)
                messages.append(f"Symbiotic Bond shares **{shared_heal:.2f} Gaia healing** with {owner_combatant.user.display_name}!")
            
            if gaias_wrath_duration <= 1:
                delattr(pet_combatant, 'gaias_wrath_duration')
                if hasattr(pet_combatant, 'gaias_wrath_heal'):
                    delattr(pet_combatant, 'gaias_wrath_heal')
                messages.append(f"{pet_combatant.name}'s connection to Gaia fades...")
            else:
                setattr(pet_combatant, 'gaias_wrath_duration', gaias_wrath_duration - 1)
            
        # 🌟 LIGHT PER-TURN EFFECTS
        # Healing Light - team healing
        if 'healing_light' in effects and team_combatants:
            for ally in team_combatants:
                if ally.is_alive():
                    heal_amount = self._scaled_heal(
                        pet_combatant,
                        ally,
                        effects['healing_light']['heal_percent'],
                    )
                    ally.heal(heal_amount)
            messages.append(f"{pet_combatant.name}'s Healing Light bathes allies in restoration!")
            
        # Purification - team cleanse
        if 'purification' in effects and hasattr(pet_combatant, 'team'):
            for ally in pet_combatant.team.combatants:
                for debuff in ['poisoned', 'stunned', 'corrupted', 'burning', 'paralyzed']:
                    if hasattr(ally, debuff):
                        delattr(ally, debuff)
            messages.append(f"{pet_combatant.name}'s Purification cleanses all team debuffs!")
            
        # Holy Aura - team protection
        if ('holy_aura' in effects and hasattr(pet_combatant, 'team')):
            for ally in pet_combatant.team.combatants:
                if ally.is_alive():
                    setattr(ally, 'dark_resistance', effects['holy_aura']['team_dark_resistance'])
                    setattr(ally, 'debuff_resistance', effects['holy_aura']['debuff_resistance'])
            messages.append(f"Holy Aura protects the team from darkness and debuffs!")
            
        # Divine Favor - random team buff
        if ('divine_favor' in effects and team_combatants):
            living_allies = [a for a in team_combatants if a.is_alive()]
            if living_allies and random.randint(1, 100) <= effects['divine_favor']['chance']:
                ally = random.choice(living_allies)
                buff_type = random.choice(['damage', 'armor', 'luck'])
                buff_value = effects['divine_favor']['buff_strength']
                
                if buff_type == 'damage':
                    self._apply_timed_multiplier(
                        ally,
                        'divine_favor_damage',
                        int(effects['divine_favor']['duration']),
                        damage_mult=Decimal('1') + Decimal(str(buff_value)),
                    )
                elif buff_type == 'armor':
                    self._apply_timed_multiplier(
                        ally,
                        'divine_favor_armor',
                        int(effects['divine_favor']['duration']),
                        armor_mult=Decimal('1') + Decimal(str(buff_value)),
                    )
                else:
                    self._apply_timed_multiplier(
                        ally,
                        'divine_favor_luck',
                        int(effects['divine_favor']['duration']),
                        luck_mult=Decimal('1') + Decimal(str(buff_value)),
                    )
                messages.append(f"Divine Favor blesses {ally.name} with enhanced {buff_type}!")
                
        # Divine Protection - ULTIMATE invincibility
        if ('divine_protection' in effects and 
            getattr(pet_combatant, 'ultimate_ready', False)):
            if team_combatants:
                for ally in team_combatants:
                    if ally.is_alive():
                        turns = int(effects['divine_protection']['invincibility_turns'])
                        setattr(ally, 'divine_invincibility', turns)
                        setattr(ally, 'blessed_by_light', True)
                        heal_amount = self._scaled_heal(
                            pet_combatant,
                            ally,
                            effects['divine_protection'].get('heal_percent', 0.45),
                            burst=True,
                        )
                        ally.heal(heal_amount)
            messages.append(f"{pet_combatant.name} grants Divine Protection! The team becomes untouchable!")
            pet_combatant.ultimate_ready = False
        
        # 🌑 DARK PER-TURN EFFECTS
        # Shadow Form - activate intangibility when under pressure.
        if 'shadow_form' in effects:
            hp_ratio = pet_combatant.hp / pet_combatant.max_hp if pet_combatant.max_hp > 0 else Decimal('0')
            shadow_form_turns = getattr(pet_combatant, 'shadow_form_turns', 0)
            if (hp_ratio <= Decimal('0.5') and shadow_form_turns <= 0 and
                not getattr(pet_combatant, 'shadow_form_used', False)):
                setattr(pet_combatant, 'shadow_form_turns', effects['shadow_form']['physical_immunity'])
                setattr(pet_combatant, 'shadow_form_used', True)
                messages.append(
                    f"{pet_combatant.name} slips into Shadow Form for "
                    f"{effects['shadow_form']['physical_immunity']} turns!"
                )

        # Soul Drain - lifesteal on attack
        if ('soul_drain' in effects and getattr(pet_combatant, 'attacked_this_turn', False)):
            last_damage = Decimal(str(getattr(pet_combatant, 'last_damage_dealt', 0)))
            lifesteal = last_damage * Decimal(str(effects['soul_drain']['lifesteal_percent']))
            pet_combatant.heal(lifesteal)
            messages.append(f"{pet_combatant.name} drains **{lifesteal:.2f} life force**!")
            
        # Dark Pact - sacrifice for owner boost
        if ('dark_pact' in effects and owner_combatant and hasattr(owner_combatant, 'damage')):
            owner_hp_ratio = owner_combatant.hp / owner_combatant.max_hp if owner_combatant.max_hp else Decimal('1')
            if (
                owner_hp_ratio <= Decimal('0.70')
                and not getattr(owner_combatant, 'dark_pact_active', False)
                and not getattr(pet_combatant, 'dark_pact_used', False)
            ):
                sacrifice = pet_combatant.max_hp * Decimal(str(effects['dark_pact']['hp_sacrifice']))
                current_hp = Decimal(str(getattr(pet_combatant, 'hp', 0)))
                if current_hp > sacrifice:
                    setattr(pet_combatant, 'hp', current_hp - sacrifice)
                    setattr(owner_combatant, 'dark_pact_active', True)
                    setattr(pet_combatant, 'dark_pact_used', True)
                    self._apply_timed_multiplier(
                        owner_combatant,
                        'dark_pact',
                        int(effects['dark_pact']['duration']),
                        damage_mult=Decimal('1') + Decimal(str(effects['dark_pact']['owner_dark_boost'])),
                    )
                    messages.append(f"{pet_combatant.name} makes a Dark Pact, empowering their owner!")
        
        # 🌀 CORRUPTED PER-TURN EFFECTS
        # Decay Touch - proximity debuff
        if ('decay_touch' in effects and enemy_combatants):
            decay_mult = Decimal('1') - Decimal(str(effects['decay_touch']['stat_decay']))
            for enemy in enemy_combatants:
                if enemy.is_alive():
                    self._apply_timed_multiplier(
                        enemy,
                        'decay_touch',
                        2,
                        damage_mult=decay_mult,
                        armor_mult=decay_mult,
                    )
                    
        # Void Pact - sacrifice defense for power (5-turn duration)
        if ('void_pact' in effects and not getattr(pet_combatant, 'void_pact_active', False)):
            duration = int(effects['void_pact']['duration'])
            if team_combatants:
                for ally in team_combatants:
                    if ally.is_alive():
                        self._apply_timed_multiplier(
                            ally,
                            'void_pact_ally',
                            duration,
                            damage_mult=Decimal('1') + Decimal(str(effects['void_pact']['damage_boost'])),
                            armor_mult=Decimal('1') - Decimal(str(effects['void_pact']['defense_penalty'])),
                        )
            
            if enemy_combatants:
                for enemy in enemy_combatants:
                    if enemy.is_alive():
                        self._apply_timed_multiplier(
                            enemy,
                            'void_pact_enemy',
                            duration,
                            armor_mult=Decimal('1') - Decimal(str(effects['void_pact']['defense_penalty'])),
                        )
                    
            messages.append(f"{pet_combatant.name} makes a Void Pact - team gains power but all lose defense for 5 turns!")
            pet_combatant.void_pact_active = True
            pet_combatant.void_pact_duration = duration
                    
        # Chaos Form - random effects each turn
        if 'chaos_form' in effects:
            chaos_effects = [
                ('damage_boost', lambda: setattr(pet_combatant, 'chaos_damage', pet_combatant.damage * Decimal('1.5'))),
                ('speed_boost', lambda: setattr(pet_combatant, 'chaos_speed', True)),
                ('heal', lambda: pet_combatant.heal(pet_combatant.max_hp * Decimal('0.2'))),
                ('confusion', lambda: setattr(pet_combatant, 'chaos_confused', True)),
                ('immunity', lambda: setattr(pet_combatant, 'chaos_immunity', 1))
            ]
            effect_name, effect_func = random.choice(chaos_effects)
            effect_func()
            messages.append(f"{pet_combatant.name}'s Chaos Form manifests: {effect_name}!")
            
        # End of Days - ULTIMATE chaos powers
        if ('end_of_days' in effects and getattr(pet_combatant, 'ultimate_ready', False)):
            duration = int(effects['end_of_days'].get('reality_break', 3))
            if team_combatants:
                for ally in team_combatants:
                    if ally.is_alive():
                        self._apply_timed_multiplier(
                            ally,
                            'end_of_days_blessing',
                            duration,
                            damage_mult=Decimal('1') + Decimal(str(effects['end_of_days'].get('team_damage_boost', 0.50))),
                            armor_mult=Decimal('1.20'),
                            luck_mult=Decimal('1.10'),
                            extra_attrs={
                                'chaos_powers': effects['end_of_days']['reality_break'],
                                'chaos_damage_immunity': duration,
                                'reality_break_stacks': effects['end_of_days']['reality_break'],
                            },
                        )
                        
            if enemy_combatants:
                for enemy in enemy_combatants:
                    if enemy.is_alive():
                        self._apply_timed_multiplier(
                            enemy,
                            'end_of_days_curse',
                            duration,
                            damage_mult=Decimal('1') - Decimal(str(effects['end_of_days'].get('enemy_damage_reduction', 0.25))),
                            armor_mult=Decimal('0.85'),
                            luck_mult=Decimal(str(effects['end_of_days'].get('enemy_luck_mult', 0.70))),
                        )
                        setattr(enemy, 'reality_broken', duration)
            messages.append(f"{pet_combatant.name} brings the END OF DAYS! Reality collapses around the battlefield!")
            pet_combatant.ultimate_ready = False
            
        # Void Mastery - reality manipulation  
        if 'void_mastery_corrupted' in effects:
            if hasattr(pet_combatant, 'team') and hasattr(pet_combatant, 'enemy_team'):
                if random.random() < 0.3:  # 30% chance per turn for reality manipulation
                    manipulation_type = random.choice(['stat_scramble', 'mind_swap', 'reality_distort'])
                    
                    if manipulation_type == 'stat_scramble':
                        # Scramble enemy stats randomly
                        enemies = [e for e in pet_combatant.enemy_team.combatants if e.is_alive()]
                        if len(enemies) >= 2:
                            e1, e2 = random.sample(enemies, 2)
                            # Swap random stats
                            swap_choice = random.choice(['damage', 'armor', 'luck'])
                            if swap_choice == 'damage':
                                e1.damage, e2.damage = e2.damage, e1.damage
                            elif swap_choice == 'armor':
                                e1.armor, e2.armor = e2.armor, e1.armor
                            else:
                                e1.luck, e2.luck = e2.luck, e1.luck
                            messages.append(f"Void Mastery scrambles reality - {e1.name} and {e2.name}'s {swap_choice} swapped!")
                            
                    elif manipulation_type == 'mind_swap':
                        # Force enemies to target different enemies
                        enemies = [e for e in pet_combatant.enemy_team.combatants if e.is_alive()]
                        if len(enemies) >= 2:
                            confused_enemy = random.choice(enemies)
                            setattr(confused_enemy, 'mind_swapped', 2)  # 2 turns of confusion
                            messages.append(f"Void Mastery swaps {confused_enemy.name}'s mind - they're confused!")
                            
                    else:  # reality_distort
                        # Create beneficial reality distortion
                        setattr(pet_combatant, 'reality_master', 2)  # 2 turns of reality control
                        owner_combatant = self.find_owner_combatant(pet_combatant)
                        if owner_combatant and hasattr(owner_combatant, 'damage'):
                            self._apply_timed_multiplier(
                                owner_combatant,
                                'void_mastery_reality',
                                2,
                                damage_mult=Decimal('1.3'),
                            )
                        messages.append(f"Void Mastery bends reality to {pet_combatant.name}'s will!")
                        
        # Void Lord - enhanced battlefield control
        if getattr(pet_combatant, 'void_lord_active', 0) > 0:
            dominated_enemies = 0
            for enemy in enemy_combatants:
                if enemy.is_alive() and random.random() < 0.25:
                    setattr(enemy, 'void_dominated', 2)
                    setattr(enemy, 'domination_source', pet_combatant)
                    dominated_enemies += 1

            if dominated_enemies > 0:
                messages.append(f"Void Lord dominates {dominated_enemies} enemies - they serve the void!")
            else:
                messages.append(f"{pet_combatant.name}'s Void Lord power twists the battlefield!")
            
        # Soul Harvest - heal on kill
        if ('soul_harvest' in effects and getattr(pet_combatant, 'killed_enemy_this_turn', False)):
            pet_combatant.hp = pet_combatant.max_hp  # Full heal
            messages.append(f"{pet_combatant.name} harvests a soul and is fully restored!")
            
        # Eternal Decay - corruption immortality
        if ('eternal_decay' in effects and pet_combatant.hp <= 0):
            if getattr(pet_combatant, 'corrupted_targets', 0) > 0:
                pet_combatant.hp = 1  # Stay alive while corruption spreads
                messages.append(f"{pet_combatant.name} refuses to die while corruption remains!")
                
        # Void Rift - persistent void damage
        if ('void_rift' in effects and hasattr(pet_combatant, 'enemy_team')):
            void_damage = 0
            for enemy in pet_combatant.enemy_team.combatants:
                if enemy.is_alive():
                    rift_damage = enemy.max_hp * Decimal(str(effects['void_rift']['damage_percent']))
                    enemy.take_damage(rift_damage)
                    void_damage += rift_damage
            if void_damage > 0:
                messages.append(f"Void Rift tears at reality, dealing **{void_damage:.2f} total damage**!")
                
        # Reality Warp - chaos conditions
        if ('reality_warp' in effects and hasattr(pet_combatant, 'battle')):
            warp_cooldown = int(getattr(pet_combatant, 'reality_warp_cooldown', 0))
            warp_chance = float(effects['reality_warp'].get('chance', 0.10))
            if warp_cooldown <= 0 and random.random() < warp_chance:
                chaos_events = [
                    ('gravity_reverses', 'Gravity reverses - positioning effects doubled!'),
                    ('time_distorts', 'Time distorts - turn order becomes chaotic!'), 
                    ('elements_chaos', 'Elements become chaotic - damage types randomized!'),
                    ('damage_healing', 'Reality inverts - damage becomes healing this turn!'),
                    ('stats_flux', 'Reality flux - all stats become unstable!'),
                    ('void_tears', 'Void tears appear - random teleportation effects!'),
                    ('mind_static', 'Psychic static - mental abilities disrupted!')
                ]
                
                effect_type, effect_message = random.choice(chaos_events)
                messages.append(f"{pet_combatant.name}'s Reality Warp: {effect_message}")
                
                # Apply the reality warp effect to the battle
                setattr(pet_combatant, 'reality_warp_active', effect_type)
                setattr(pet_combatant, 'reality_warp_duration', 2)  # Lasts 2 turns
                setattr(pet_combatant, 'reality_warp_cooldown', int(effects['reality_warp'].get('cooldown', 3)))
                
                # Apply immediate effects based on the warp type
                if effect_type == 'damage_healing':
                    # Set flag that will be checked during damage processing
                    if hasattr(pet_combatant, 'team'):
                        for ally in pet_combatant.team.combatants:
                            setattr(ally, 'damage_inverted', 1)  # Next hit heals instead
                            
                elif effect_type == 'stats_flux':
                    # Randomize all combatant stats temporarily
                    all_combatants = []
                    if hasattr(pet_combatant, 'team'):
                        all_combatants.extend(pet_combatant.team.combatants)
                    if hasattr(pet_combatant, 'enemy_team'):
                        all_combatants.extend(pet_combatant.enemy_team.combatants)
                        
                    for combatant in all_combatants:
                        if combatant.is_alive():
                            # Store original stats
                            setattr(combatant, 'original_damage', combatant.damage)
                            setattr(combatant, 'original_armor', combatant.armor)
                            setattr(combatant, 'original_luck', combatant.luck)
                            # Randomize stats (±30%)
                            flux_mult = Decimal(str(random.uniform(0.7, 1.3)))
                            combatant.damage *= flux_mult
                            combatant.armor *= flux_mult
                            combatant.luck *= flux_mult
                            setattr(combatant, 'stats_flux_duration', 2)
                            
                elif effect_type == 'elements_chaos':
                    # Randomize elemental affinities temporarily
                    elements = ['Fire', 'Water', 'Electric', 'Earth', 'Wind', 'Nature', 'Light', 'Dark', 'Corrupted']
                    all_combatants = []
                    if hasattr(pet_combatant, 'team'):
                        all_combatants.extend(pet_combatant.team.combatants)
                    if hasattr(pet_combatant, 'enemy_team'):
                        all_combatants.extend(pet_combatant.enemy_team.combatants)
                        
                    for combatant in all_combatants:
                        if combatant.is_alive() and hasattr(combatant, 'element'):
                            setattr(combatant, 'original_element', combatant.element)
                            combatant.element = random.choice(elements)
                            setattr(combatant, 'element_chaos_duration', 2)
                
        # 💨 WIND PER-TURN EFFECTS
        if 'winds_guidance' in effects:
            setattr(pet_combatant, 'winds_guidance_ready', 1)

        # Air Currents - initiative control (manipulate turn order)
        if ('air_currents' in effects and hasattr(pet_combatant, 'team')):
            for ally in pet_combatant.team.combatants:
                if ally.is_alive():
                    setattr(ally, 'air_currents_boost', True)
                    setattr(ally, 'air_currents_duration', int(effects['air_currents'].get('duration', 2)))
                    self._apply_timed_multiplier(
                        ally,
                        'air_currents',
                        int(effects['air_currents'].get('duration', 2)),
                        damage_mult=Decimal('1') + Decimal(str(effects['air_currents'].get('team_buff', 0.10))),
                        luck_mult=Decimal('1') + Decimal(str(effects['air_currents'].get('luck_bonus', 0.10))),
                    )
            messages.append(f"{pet_combatant.name} controls Air Currents, accelerating and sharpening the whole team!")
             
        # Freedom's Call - team speed buff
        if ('freedoms_call' in effects and hasattr(pet_combatant, 'team')):
            for ally in pet_combatant.team.combatants:
                if ally.is_alive():
                    setattr(ally, 'freedom_boost', True)
                    setattr(ally, 'freedom_boost_duration', int(effects['freedoms_call'].get('duration', 2)))
                    self._apply_timed_multiplier(
                        ally,
                        'freedoms_call',
                        int(effects['freedoms_call'].get('duration', 2)),
                        damage_mult=Decimal('1') + Decimal(str(effects['freedoms_call'].get('team_buff', 0.15))),
                        luck_mult=Decimal('1') + Decimal(str(effects['freedoms_call'].get('team_speed', 0.25))),
                    )
            messages.append(f"{pet_combatant.name} calls for Freedom! The team feels liberated and empowered!")
            
        # 🌿 NATURE PER-TURN EFFECTS  
        # Natural Balance - buff transfer (share buffs with team)
        if ('natural_balance' in effects and hasattr(pet_combatant, 'team')):
            # Find buffs on pet_combatant and share them
            buff_attrs = ['speed_boost', 'damage_boost', 'armor_boost', 'zeus_protection']
            shared_buffs = []
            
            for buff in buff_attrs:
                if hasattr(pet_combatant, buff):
                    buff_value = getattr(pet_combatant, buff)
                    # Share with one random ally
                    alive_allies = [a for a in pet_combatant.team.combatants if a != pet_combatant and a.is_alive()]
                    if alive_allies:
                        ally = random.choice(alive_allies)
                        setattr(ally, buff, buff_value)
                        shared_buffs.append(buff)
                        
            if shared_buffs:
                messages.append(f"{pet_combatant.name} uses Natural Balance to share {', '.join(shared_buffs)} with allies!")
                
        # Immortal Growth - team regeneration
        for ally in team_combatants:
            immortal_growth_duration = int(getattr(ally, 'immortal_growth_duration', 0) or 0)
            if immortal_growth_duration <= 0 or not ally.is_alive():
                continue

            regen_percent = getattr(ally, 'immortal_growth_regen', 0.15)
            heal_amount = self._scaled_heal(
                pet_combatant,
                ally,
                regen_percent,
                self_target=(ally is pet_combatant),
            )
            ally.heal(heal_amount)
            messages.append(f"{ally.name} regenerates **{heal_amount:.2f} HP** from Immortal Growth!")

            if ally is pet_combatant and 'symbiotic_bond' in effects and owner_combatant and hasattr(owner_combatant, 'heal'):
                share_percent = Decimal(str(effects['symbiotic_bond']['share_percent']))
                shared_heal = heal_amount * share_percent
                owner_combatant.heal(shared_heal)
                owner_name = getattr(
                    getattr(owner_combatant, 'user', None),
                    'display_name',
                    getattr(owner_combatant, 'name', 'their owner')
                )
                messages.append(f"Symbiotic Bond shares **{shared_heal:.2f} regeneration** with {owner_name}!")

            if immortal_growth_duration <= 1:
                if hasattr(ally, 'dot_immunity'):
                    delattr(ally, 'dot_immunity')
                if hasattr(ally, 'immortal_growth_duration'):
                    delattr(ally, 'immortal_growth_duration')
                if hasattr(ally, 'immortal_growth_regen'):
                    delattr(ally, 'immortal_growth_regen')
                messages.append(f"{ally.name}'s Immortal Growth effect fades...")
            else:
                setattr(ally, 'immortal_growth_duration', immortal_growth_duration - 1)
        
        # Handle self-contained duration effects that are not managed by the timed buff helpers.
        for attr_name in ('stats_flux_duration', 'element_chaos_duration', 'reality_warp_duration'):
            duration = int(getattr(pet_combatant, attr_name, 0) or 0)
            if duration <= 0:
                continue

            setattr(pet_combatant, attr_name, duration - 1)
            if duration > 1:
                continue

            effect_name = attr_name.replace('_duration', '')
            messages.append(f"{pet_combatant.name}'s {effect_name} effect expires!")

            if attr_name == 'stats_flux_duration':
                if hasattr(pet_combatant, 'original_damage'):
                    pet_combatant.damage = getattr(pet_combatant, 'original_damage')
                    delattr(pet_combatant, 'original_damage')
                if hasattr(pet_combatant, 'original_armor'):
                    pet_combatant.armor = getattr(pet_combatant, 'original_armor')
                    delattr(pet_combatant, 'original_armor')
                if hasattr(pet_combatant, 'original_luck'):
                    pet_combatant.luck = getattr(pet_combatant, 'original_luck')
                    delattr(pet_combatant, 'original_luck')
            elif attr_name == 'element_chaos_duration':
                if hasattr(pet_combatant, 'original_element'):
                    pet_combatant.element = getattr(pet_combatant, 'original_element')
                    delattr(pet_combatant, 'original_element')
            elif attr_name == 'reality_warp_duration':
                if hasattr(pet_combatant, 'reality_warp_active'):
                    delattr(pet_combatant, 'reality_warp_active')
                        
        # Process tornado damage zones
        if hasattr(pet_combatant, 'enemy_team'):
            for enemy in pet_combatant.enemy_team.combatants:
                tornado_data = getattr(enemy, 'tornado_damage', None)
                if tornado_data and tornado_data['duration'] > 0:
                    tornado_dmg = tornado_data['damage']
                    enemy.take_damage(tornado_dmg)
                    tornado_data['duration'] -= 1
                    messages.append(f"{enemy.name} takes **{tornado_dmg:.2f} tornado damage**!")
                    
                    if tornado_data['duration'] <= 0:
                        delattr(enemy, 'tornado_damage')
                        messages.append(f"The tornado around {enemy.name} dissipates!")
                        
        # Handle status effects (poison, burn, etc.)
        all_statuses = ['poisoned', 'burning', 'paralyzed', 'stunned', 'corrupted', 'corrupted_mind', 'void_dominated', 'mind_swapped', 'reality_broken', 'rooted', 'storm_dominated', 'gale_force_debuff', 'wind_shear_debuff', 'blinded']
        for status in all_statuses:
            if hasattr(pet_combatant, status):
                status_duration = getattr(pet_combatant, status)
                if status_duration > 0:
                    if status in ['poisoned', 'burning']:
                        # Check for DoT immunity
                        if getattr(pet_combatant, 'dot_immunity', False):
                            messages.append(f"{pet_combatant.name} is immune to {status} effects!")
                            # Remove the DoT effect
                            delattr(pet_combatant, status)
                            continue
                        else:
                            damage = pet_combatant.max_hp * Decimal('0.05')  # 5% per turn
                            pet_combatant.take_damage(damage)
                            messages.append(f"{pet_combatant.name} takes **{damage:.2f} {status} damage**!")
                    elif status == 'paralyzed':
                        messages.append(f"{pet_combatant.name} is paralyzed and cannot act!")
                    elif status == 'stunned':
                        messages.append(f"{pet_combatant.name} is stunned!")
                    elif status == 'corrupted':
                        # Check for DoT immunity
                        if getattr(pet_combatant, 'dot_immunity', False):
                            messages.append(f"{pet_combatant.name} is immune to corruption effects!")
                            # Remove the corruption effect
                            delattr(pet_combatant, status)
                            continue
                        else:
                            # Corruption spreads and causes stat decay
                            pet_combatant.damage *= Decimal('0.98')  # 2% decay per turn
                            pet_combatant.armor *= Decimal('0.98')
                            if hasattr(pet_combatant, 'team'):
                                for ally in pet_combatant.team.combatants:
                                    if ally != pet_combatant and not hasattr(ally, 'corrupted'):
                                        if random.random() < 0.1:  # 10% spread chance
                                            setattr(ally, 'corrupted', 2)
                                            messages.append(f"Corruption spreads to {ally.name}!")
                    elif status == 'corrupted_mind':
                        # Mind controlled - will attack wrong targets (handled in battle system)
                        messages.append(f"{pet_combatant.name} is under mind control!")
                    elif status == 'void_dominated':
                        # Dominated by void lord - reduced effectiveness
                        pet_combatant.damage *= Decimal('0.9')  # 10% damage reduction
                        messages.append(f"{pet_combatant.name} serves the void against their will!")
                    elif status == 'mind_swapped':
                        # Confused targeting (handled in battle system)
                        messages.append(f"{pet_combatant.name} is confused by mind swap!")
                    elif status == 'reality_broken':
                        # Reality break effects - random penalties
                        if random.random() < 0.5:  # 50% chance for penalty each turn
                            penalty_type = random.choice(['damage', 'accuracy', 'confusion'])
                            if penalty_type == 'damage':
                                pet_combatant.damage *= Decimal('0.95')
                            elif penalty_type == 'accuracy':
                                pet_combatant.luck *= Decimal('0.9')
                            messages.append(f"{pet_combatant.name} suffers from reality breakdown!")
                    elif status == 'rooted':
                        # Rooted - reduced damage output
                        root_reduction = getattr(pet_combatant, 'root_damage_reduction', 0.5)
                        pet_combatant.damage *= (Decimal('1') - Decimal(str(root_reduction)))
                        messages.append(f"{pet_combatant.name} is entangled by roots, weakening their attacks!")
                    elif status == 'storm_dominated':
                        # Dominated by storm lord - reduced effectiveness
                        messages.append(f"{pet_combatant.name} struggles against the Storm Lord's control!")
                    elif status == 'gale_force_debuff':
                        # Affected by gale force - reduced accuracy
                        messages.append(f"{pet_combatant.name} fights against disorienting winds!")
                    elif status == 'wind_shear_debuff':
                        # Defense reduced by wind shear
                        messages.append(f"{pet_combatant.name}'s defenses remain weakened by wind shear!")
                    elif status == 'blinded':
                        # Reduced accuracy from light beam
                        messages.append(f"{pet_combatant.name} struggles with impaired vision!")
                    elif status == 'divine_invincibility':
                        # Complete immunity to damage (Ultimate Light skill)
                        messages.append(f"{pet_combatant.name} is protected by divine light and cannot be harmed!")
                    
                    setattr(pet_combatant, status, status_duration - 1)
                    if status_duration == 1:
                        delattr(pet_combatant, status)
                        if status == 'corrupted_mind':
                            messages.append(f"{pet_combatant.name} breaks free from mind control!")
                        elif status == 'void_dominated':
                            messages.append(f"{pet_combatant.name} escapes void domination!")
                        elif status == 'reality_broken':
                            messages.append(f"{pet_combatant.name} adapts to the broken reality!")
                        elif status == 'rooted':
                            messages.append(f"{pet_combatant.name} breaks free from the entangling roots!")
                        elif status == 'storm_dominated':
                            messages.append(f"{pet_combatant.name} breaks free from the Storm Lord's control!")
                        elif status == 'gale_force_debuff':
                            messages.append(f"{pet_combatant.name} recovers from the disorienting winds!")
                        elif status == 'wind_shear_debuff':
                            messages.append(f"{pet_combatant.name}'s defenses recover from wind shear!")
                        elif status == 'blinded':
                            messages.append(f"{pet_combatant.name}'s vision clears!")
                        elif status == 'divine_invincibility':
                            messages.append(f"{pet_combatant.name}'s divine protection fades!")
                            if hasattr(pet_combatant, 'blessed_by_light'):
                                delattr(pet_combatant, 'blessed_by_light')
                        else:
                            messages.append(f"{pet_combatant.name} recovers from {status}!")
        
        # Reset turn flags
        setattr(pet_combatant, 'attacked_this_turn', False)
        setattr(pet_combatant, 'killed_enemy_this_turn', False)
        
        # Reset skill flags
        if hasattr(pet_combatant, 'perfect_accuracy'):
            delattr(pet_combatant, 'perfect_accuracy')
        
        return messages
    
    async def get_pet_combatant(self, ctx, user, include_element=True):
        """Create a combatant object for a player's pet if they have one equipped"""
        if not user:
            return None
            
        async with ctx.bot.pool.acquire() as conn:
            # Check if user has an equipped pet
            pet = await conn.fetchrow(
                "SELECT * FROM monster_pets WHERE user_id = $1 AND equipped = TRUE;",
                user.id
            )
            
            if not pet:
                return None
                
            # Get pet's element
            pet_element = pet["element"].capitalize() if pet["element"] and include_element else "Unknown"
            
            # Get owner's stats
            owner_stats = await conn.fetchrow(
                "SELECT * FROM profile WHERE \"user\" = $1;",
                user.id
            )
                
            # Get owner's luck if available, or use default
            owner_luck = owner_stats["luck"] if owner_stats and "luck" in owner_stats else 0.6
            # Convert owner_luck to float to avoid decimal/float type mismatch
            owner_luck = float(owner_luck)
            
            # Apply the same luck calculation formula as the main character
            # Copy from the battle factory logic
            pet_luck = 20 if owner_luck <= 0.3 else ((owner_luck - 0.3) / (1.5 - 0.3)) * 80 + 20
            pet_luck = round(pet_luck, 2)
            pet_luck = min(pet_luck, 100.0)  # Cap at 100% like owner
            
            # Calculate trust bonus
            trust_level = pet.get('trust_level', 0)
            trust_bonus = self.get_trust_bonus(trust_level)
            pet_level = max(1, min(int(pet.get("level", 1)), self.PET_MAX_LEVEL))
            level_multiplier = 1 + (pet_level * self.PET_LEVEL_STAT_BONUS)
            
            # Apply +1% base stat scaling per level (level 100 => +100%).
            base_hp = float(pet["hp"]) * level_multiplier
            base_armor = float(pet["defense"]) * level_multiplier
            base_damage = float(pet["attack"]) * level_multiplier
            
            bonus_hp = base_hp * trust_bonus
            bonus_armor = base_armor * trust_bonus
            bonus_damage = base_damage * trust_bonus
            
            final_hp = base_hp + bonus_hp
            final_armor = base_armor + bonus_armor
            final_damage = base_damage + bonus_damage
            
            # Store additional pet data for skills
            happiness = pet.get('happiness', 50)
            
            # Create pet combatant
            pet_combatant = Combatant(
                user=user,  # Reference to owner
                hp=final_hp,
                max_hp=final_hp,
                armor=final_armor,
                damage=final_damage,
                luck=pet_luck,  # Use owner's luck instead of fixed value
                element=pet_element,
                is_pet=True,
                owner=user,
                name=pet["name"],
                pet_id=pet["id"]
            )
            
            # Store pet-specific attributes for skill calculations
            pet_combatant.happiness = happiness
            pet_combatant.trust_level = trust_level
            
            # Apply skill effects
            pets_cog = ctx.bot.get_cog("Pets")
            if pets_cog and hasattr(pets_cog, "get_effective_learned_skills"):
                learned_skills = pets_cog.get_effective_learned_skills(pet)
            else:
                learned_skills = pet.get('learned_skills', [])
                # Handle JSON string format from database
                if isinstance(learned_skills, str):
                    try:
                        import json
                        learned_skills = json.loads(learned_skills)
                    except (json.JSONDecodeError, TypeError):
                        learned_skills = []
                elif learned_skills is None:
                    learned_skills = []
            
            self.apply_skill_effects(pet_combatant, learned_skills)
            
            # Check for ultimate skills and set up activation
            ultimate_skills = [
                'inferno_mastery', 'phoenix_rebirth', 'sun_gods_blessing',
                'oceans_wrath', 'immortal_waters', 'poseidons_call',
                'storm_lord', 'infinite_energy', 'zeus_wrath',
                'gaias_wrath', 'immortal_growth', 'world_trees_gift',
                'storm_lord_wind', 'skys_blessing', 'zephyrs_dance',
                'solar_flare', 'divine_protection', 'celestial_blessing',
                'void_mastery', 'eternal_night', 'lord_of_shadows',
                'apocalypse', 'corruption_mastery', 'void_lord', 'end_of_days'
            ]
            
            has_ultimate = any(skill in getattr(pet_combatant, 'skill_effects', {}) for skill in ultimate_skills)
            if has_ultimate:
                # Ultimate skills activate when pet reaches low HP (based on trust)
                activation_threshold = 0.15 + (trust_level / 100) * 0.1  # 15-25% HP threshold
                # DEBUG LINE activation_threshold = 1.0  # DEBUG: Always trigger at full HP
                setattr(pet_combatant, 'ultimate_threshold', activation_threshold)
                setattr(pet_combatant, 'ultimate_ready', False)
                setattr(pet_combatant, 'ultimate_activated', False)
            
            return pet_combatant
    
    def apply_pet_bonuses(self, pet_combatant, owner_combatant):
        """Apply any special bonuses between pet and owner"""
        # Apply trust-based bonuses to owner
        if pet_combatant and owner_combatant:
            trust_level = getattr(pet_combatant, 'trust_level', 0)
            trust_bonus = self.get_trust_bonus(trust_level)
            
            # Apply small bonus to owner based on pet's trust
            owner_bonus = Decimal(str(trust_bonus)) * Decimal('0.1')  # 10% of pet's trust bonus
            
            owner_combatant.damage *= (Decimal('1') + owner_bonus)
            owner_combatant.armor *= (Decimal('1') + owner_bonus)
            
        return
    
    async def award_battle_experience(self, pet_id, battle_xp, trust_gain=1):
        """Award experience to a pet after participating in a battle"""
        try:
            # This would be called from the pets cog
            # Implementation depends on having access to the pets cog
            pass
        except Exception as e:
            print(f"Error awarding battle experience to pet {pet_id}: {e}")
            return None

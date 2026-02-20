from decimal import Decimal
import asyncio
import random
import discord
from datetime import datetime, timedelta
from collections import deque
from decimal import Decimal

from ..core.battle import Battle
from ..core.combatant import Combatant
from ..core.team import Team

class DragonBattle(Battle):
    """Implementation of Ice Dragon Challenge battle"""
    
    def __init__(self, ctx, teams, **kwargs):
        super().__init__(ctx, teams, **kwargs)
        
        # Dragon-specific configurations
        self.dragon_level = kwargs.get("dragon_level", 1)
        self.weekly_defeats = kwargs.get("weekly_defeats", 0)
        # Don't override action_number - let base class handle it
        
        # Load all battle settings
        settings_cog = self.ctx.bot.get_cog("BattleSettings")
        if settings_cog:
            # Ensure all settings are loaded, with defaults if not found
            self.config = {
                "allow_pets": settings_cog.get_setting("dragon", "allow_pets", default=True),
                "class_buffs": settings_cog.get_setting("dragon", "class_buffs", default=True),
                "element_effects": settings_cog.get_setting("dragon", "element_effects", default=True),
                "luck_effects": settings_cog.get_setting("dragon", "luck_effects", default=True),
                "reflection_damage": settings_cog.get_setting("dragon", "reflection_damage", default=True),
                "fireball_chance": settings_cog.get_setting("dragon", "fireball_chance", default=0.3),
                "cheat_death": settings_cog.get_setting("dragon", "cheat_death", default=True),
                "tripping": settings_cog.get_setting("dragon", "tripping", default=True),
                "status_effects": settings_cog.get_setting("dragon", "status_effects", default=False),
                "pets_continue_battle": settings_cog.get_setting("dragon", "pets_continue_battle", default=False)
            }
        else:
            # Fallback default settings if settings cog is unavailable
            self.config = {
                "allow_pets": True,
                "class_buffs": True,
                "element_effects": True,
                "luck_effects": True,
                "reflection_damage": True,
                "fireball_chance": 0.3,
                "cheat_death": True,
                "tripping": True,
                "status_effects": False,
                "pets_continue_battle": False
            }
        self.current_turn = 0  # Track turns separately from action numbers
        self.dragon_stage_info = None
        self.dragon_moves = {}
        self.dragon_passives = []
        self.dragon_element = "Water"
        self._move_cooldowns = {}
        
        # Get the dragon team and player team
        self.dragon_team = teams[0]  # Dragon is always the first team
        self.player_team = teams[1]  # Players are the second team
        
        # Reference to dragon and players for easier access
        self.dragon = self.dragon_team.combatants[0]  # Dragon is the first combatant in team
        self.players = self.player_team.combatants  # All player combatants
        
        # Track status effects
        self.status_effects = {}

        # Track which players have already used cheat death in this battle
        self.cheat_death_used = set()
        self._extra_dragon_turns = 0
        self._dominion_used = False
        self._possession_used = False
        self._damage_link_guard = False
        self._player_turn_queue = deque()
        
    def get_participants(self):
        """Get list of participant user IDs for replay storage (dragon-specific)"""
        participants = []
        # Only get unique user IDs from players (not pets to avoid duplicates)
        for combatant in self.player_team.combatants:
            if not getattr(combatant, 'is_pet', False):  # Only include non-pets
                if hasattr(combatant, 'user') and hasattr(combatant.user, 'id'):
                    participants.append(combatant.user.id)
                elif hasattr(combatant, 'user_id') and combatant.user_id:
                    participants.append(combatant.user_id)
        return list(set(participants))  # Remove any remaining duplicates
        
    async def start_battle(self):
        """Initialize and start the battle"""
        self.started = True
        self.start_time = datetime.utcnow()
        
        # Save initial battle data to database for replay
        await self.save_battle_to_database()
        
        # Reset counters to ensure we start fresh
        # Don't reset action_number - let base class handle it properly for turn states
        self.current_turn = 0
        
        # Determine which dragon stage we're fighting based on level
        dragon_ext = None
        battles_cog = self.ctx.bot.cogs.get("Battles")
        if battles_cog:
            dragon_ext = battles_cog.battle_factory.dragon_ext
        stage = None
        if dragon_ext:
            stage = await dragon_ext.get_dragon_stage(self.ctx.bot, self.dragon_level)
        if not stage:
            stage = {"name": "Eternal Frost", "info": {"moves": {}, "passives": [], "element": "Water"}}
        self.dragon_stage_id = stage.get("id")
        stage_name = stage["name"]
        self.dragon_stage_info = stage["info"]
        self.dragon_moves = self.dragon_stage_info.get("moves", {})
        self.dragon_passives = self.dragon_stage_info.get("passives", [])
        self.dragon_element = self.dragon_stage_info.get("element", "Water")
        self.dragon.stage = stage_name
        self.dragon.name = f"{stage_name} (Level {self.dragon_level})"
        self.dragon.passives = self.dragon_passives
        
        # Add the initial message to the battle log
        await self.add_to_log(f"The battle against {self.dragon.name} has begun! 🐉")
        
        # Add passive effect descriptions
        passive_descriptions = []
        passive_desc_map = {}
        if dragon_ext and self.dragon_passives:
            passive_desc_map = await dragon_ext.get_passive_descriptions(self.ctx.bot, self.dragon_passives)
        for passive in self.dragon_passives:
            desc = passive_desc_map.get(passive, "")
            if desc:
                passive_descriptions.append(f"• **{passive}**: {desc}")
            else:
                passive_descriptions.append(f"• **{passive}**")

        if passive_descriptions:
            await self.add_to_log("**Dragon's Passive Effects:**\n" + "\n".join(passive_descriptions))
            # Keep dragon as the first actor after passive log
            self.current_turn = 0
            
        # Create initial battle display
        self._refresh_player_turn_queue()
        await self.update_display()
        
        return True
        
    async def process_turn(self):
        """Process a single turn of the battle"""
        # Check if battle is over
        if await self.is_battle_over():
            return False
            
        # Get the current combatant
        current_combatant = self.get_next_combatant()
        
        # Process status effects on the current combatant
        await self.process_status_effects(current_combatant)
        if not current_combatant.is_alive():
            await self.add_to_log(f"{current_combatant.name} is defeated and cannot act!")
            self._decrement_status_effects(current_combatant)
            await self.update_display()
            return True
        
        # Skip turn if stunned
        if self.is_stunned(current_combatant):
            await self.add_to_log(f"{current_combatant.name} is stunned and cannot act!")
            self._decrement_status_effects(current_combatant)
            await self.update_display()
            return True

        # Skip turn if affected by terror panic
        panic_effect = self._get_effect(current_combatant, "turn_skip_chance")
        if panic_effect:
            chance = panic_effect.get("value", 0.5)
            if random.random() < chance:
                await self.add_to_log(f"{current_combatant.name} is overwhelmed by terror and loses their turn!")
                self._decrement_status_effects(current_combatant)
                await self.update_display()
                return True
            
        # Process turn based on combatant type
        if current_combatant == self.dragon:
            # Dragon's turn
            await self.process_dragon_turn(current_combatant)
        else:
            # Player's turn
            await self.process_player_turn(current_combatant)
            
        # Check if battle is over after processing the turn (important for cheat death)
        if await self.is_battle_over():
            return False
        
        # Process per-turn effects for player pets
        if hasattr(self.ctx.bot.cogs["Battles"], "battle_factory"):
            pet_ext = self.ctx.bot.cogs["Battles"].battle_factory.pet_ext
            for player in self.player_team.combatants:
                if player.is_pet and player.is_alive():
                    # Set team references for skills that need them
                    if self._has_effect(player, "possessed"):
                        setattr(player, 'team', self.dragon_team)
                        setattr(player, 'enemy_team', self.player_team)
                    else:
                        setattr(player, 'team', self.player_team)
                        setattr(player, 'enemy_team', self.dragon_team)
                    
                    # Process per-turn effects
                    turn_messages = pet_ext.process_skill_effects_per_turn(player)
                    if turn_messages:
                        for turn_msg in turn_messages:
                            await self.add_to_log(turn_msg)
        
        self._decrement_status_effects(current_combatant)
        # Update display after turn is processed
        await self.update_display()
        await asyncio.sleep(2)  # Delay between turns for readability
        
        # Return True to indicate turn was processed successfully
        return True
        
    async def process_dragon_turn(self, dragon):
        """Process the dragon's turn"""
        # Tick down move cooldowns
        if self._move_cooldowns:
            for effect_key in list(self._move_cooldowns.keys()):
                self._move_cooldowns[effect_key] -= 1
                if self._move_cooldowns[effect_key] <= 0:
                    del self._move_cooldowns[effect_key]

        # Get dragon stage and available moves
        available_moves = self.dragon_moves or {}

        alive_allies = self._alive_party_combatants()
        def has_ally_target(combatant):
            return any(c is not combatant and c.is_alive() for c in alive_allies)
        def _normalize_chance(value):
            try:
                chance = float(value)
            except (TypeError, ValueError):
                return 0.0
            if chance > 1:
                chance = chance / 100.0
            return max(0.0, min(1.0, chance))

        # Select a random move
        if not available_moves:
            await self.add_to_log(f"{dragon.name} hesitates, unable to find a move!")
            return
        move_pool = list(available_moves.items())
        random.shuffle(move_pool)
        move_name = None
        move_info = None
        if not self._possession_used:
            for candidate_name, candidate_info in move_pool:
                effect = candidate_info.get("effect")
                if effect not in ("possess_player", "possess_pet", "possess_player_and_pet_permanent"):
                    continue
                if effect in self._move_cooldowns:
                    continue
                if effect == "possess_player_and_pet_permanent" and self._dominion_used:
                    continue
                if effect == "possess_pet":
                    pet_targets = [c for c in alive_allies if c.is_pet and has_ally_target(c)]
                    if not pet_targets:
                        continue
                elif effect == "possess_player":
                    player_targets = [c for c in alive_allies if not c.is_pet and has_ally_target(c)]
                    if not player_targets:
                        continue
                elif effect == "possess_player_and_pet_permanent":
                    if len(alive_allies) <= 2:
                        continue
                    player_targets = [c for c in alive_allies if not c.is_pet and has_ally_target(c)]
                    pet_targets = [c for c in alive_allies if c.is_pet and has_ally_target(c)]
                    if not player_targets or not pet_targets:
                        continue
                move_name = candidate_name
                move_info = candidate_info
                break

        if not move_name:
            for candidate_name, candidate_info in move_pool:
                effect = candidate_info.get("effect")
                if self._possession_used and effect in ("possess_player", "possess_pet", "possess_player_and_pet_permanent"):
                    continue
                if effect in self._move_cooldowns:
                    continue
                if effect == "possess_player_and_pet_permanent" and self._dominion_used:
                    continue
                if effect == "possess_pet":
                    pet_targets = [c for c in alive_allies if c.is_pet and has_ally_target(c)]
                    if not pet_targets:
                        continue
                elif effect == "possess_player":
                    player_targets = [c for c in alive_allies if not c.is_pet and has_ally_target(c)]
                    if not player_targets:
                        continue
                elif effect == "possess_player_and_pet_permanent":
                    if len(alive_allies) <= 2:
                        continue
                    player_targets = [c for c in alive_allies if not c.is_pet and has_ally_target(c)]
                    pet_targets = [c for c in alive_allies if c.is_pet and has_ally_target(c)]
                    if not player_targets or not pet_targets:
                        continue
                move_name = candidate_name
                move_info = candidate_info
                break

        if not move_name:
            if not alive_allies:
                await self.add_to_log(f"{dragon.name} has no valid targets!")
                return
            target = random.choice(alive_allies)
            base_damage = 300 * (1 + (0.1 * (self.dragon_level - 1)))
            base_damage = Decimal(str(base_damage))
            target_armor = target.armor if isinstance(target.armor, Decimal) else Decimal(str(target.armor))
            damage = max(base_damage - target_armor, Decimal("10"))
            target.take_damage(damage)
            element_key = str(self.dragon_element or "Unknown").capitalize()
            element_flavor = {
                "Water": [
                    "surges forward in a crashing tide",
                    "lashes out with a freezing current",
                    "slams a wave into its foe",
                    "rends the air with glacial spray",
                    "strikes with a scalding torrent",
                ],
                "Fire": [
                    "erupts in a searing burst",
                    "swipes with ember-clad claws",
                    "breathes a blistering flare",
                    "scorches the air with a flame lash",
                    "lunges with a molten bite",
                ],
                "Earth": [
                    "slams the ground with crushing force",
                    "hammers forward with stonebound might",
                    "shatters the air with a rocky strike",
                    "surges with an earthen charge",
                    "drives a jagged blow into its foe",
                ],
                "Wind": [
                    "dives in on a razor gale",
                    "slashes with slicing air",
                    "strikes in a whirling gust",
                    "rips forward with a cyclone lash",
                    "surges with a cutting draft",
                ],
                "Electric": [
                    "crackles forward with a charged swipe",
                    "strikes with a thunderous lash",
                    "surges in a flash of static",
                    "rips the air with a sparking blow",
                    "lunges with a shock-laced bite",
                ],
                "Light": [
                    "flares in a blinding arc",
                    "strikes with a radiant lash",
                    "surges with a searing burst",
                    "rends the air with a holy glare",
                    "slashes with a prismed strike",
                ],
                "Dark": [
                    "strikes from a shadowed lunge",
                    "lashes out with a voided swipe",
                    "rips the air with a grim surge",
                    "slams down in a murky arc",
                    "lunges with a night-black bite",
                ],
                "Nature": [
                    "lashes out with thorned fury",
                    "surges forward in a wild rush",
                    "rends the air with a vine-laced strike",
                    "slams down with primal force",
                    "lunges with a feral snap",
                ],
                "Corrupted": [
                    "erupts in a warped surge",
                    "lashes out with a tainted swipe",
                    "rips the air with corrupt force",
                    "slams down in a twisted arc",
                    "lunges with a blighted bite",
                ],
                "Unknown": [
                    "lashes out with a savage strike",
                    "surges forward with brutal force",
                    "rends the air with a vicious swipe",
                    "slams its foe with crushing might",
                    "lunges with a feral bite",
                ],
            }
            fallback_flavor = element_flavor["Unknown"]
            flavor = element_flavor.get(element_key, fallback_flavor)
            attack_text = random.choice(flavor)
            await self.add_to_log(
                f"{dragon.name} {attack_text}! {target.name} takes **{self.format_number(damage)} HP** damage."
            )
            return

        # Enforce one-time ultimate use
        if move_info.get("effect") == "possess_player_and_pet_permanent" and self._dominion_used:
            alternate_moves = [
                name for name, info in available_moves.items()
                if info.get("effect") != "possess_player_and_pet_permanent"
            ]
            if alternate_moves:
                move_name = random.choice(alternate_moves)
                move_info = available_moves[move_name]
        
        # Determine targets based on move type
        if move_info["effect"] == "possess_pet":
            pet_targets = [c for c in alive_allies if c.is_pet and has_ally_target(c)]
            targets = [random.choice(pet_targets)] if pet_targets else []
        elif move_info["effect"] in ["possess_player", "possess_player_and_pet_permanent"]:
            player_targets = [c for c in alive_allies if not c.is_pet and has_ally_target(c)]
            targets = [random.choice(player_targets)] if player_targets else []
        elif move_info["effect"] in ["aoe", "aoe_stun", "aoe_dot", "global_dot"]:
            targets = alive_allies
        else:
            # Single target
            alive_players = alive_allies
            if alive_players:
                target = random.choice(alive_players)
                targets = [target]
            else:
                targets = []
                
        # If no valid targets, skip turn
        if not targets:
            await self.add_to_log(f"{dragon.name} has no valid targets!")
            return
            
        # Apply the move to targets
        base_damage = move_info["dmg"] * (1 + (0.1 * (self.dragon_level - 1)))
        effect = move_info["effect"]
        effect_chance = move_info.get("chance", 0) or 0
        effect_chance = _normalize_chance(effect_chance)
        if effect in ("possess_player", "possess_pet", "possess_player_and_pet_permanent") and not self._possession_used:
            effect_chance = 1.0
        
        for target in targets:
            # Apply element effects if enabled
            element_modifier = 1.0
            element_message = ""
            if self.config.get("element_effects", True) and hasattr(self.ctx.bot.cogs["Battles"], "element_ext"):
                dragon_element = self.dragon_element or "Water"
                target_element = self.resolve_defense_element(target)
                
                if target_element:
                    # Get element multiplier from element extension
                    try:
                        element_mod = self.ctx.bot.cogs["Battles"].element_ext.calculate_damage_modifier(
                            self.ctx,
                            dragon_element,
                            target_element,
                        )
                        element_modifier = 1.0 + element_mod
                        
                        # Element messages will be added to the attack message
                        if element_mod > 0:
                            element_message = f" ({dragon_element} is strong against {target_element}!)"
                        elif element_mod < 0:
                            element_message = f" ({dragon_element} is weak against {target_element}!)"
                    except Exception:
                        # Fallback if element extension fails
                        element_modifier = 1.0
            
            # Calculate damage using direct armor subtraction, matching Ice Dragon Challenge
            # Convert target.armor to float if it's a Decimal to avoid type errors
            if isinstance(target.armor, Decimal):
                target_armor = float(target.armor)
            else:
                target_armor = target.armor
                
            # Apply element modifier to base damage
            if isinstance(base_damage, Decimal):
                modified_base_damage = base_damage * Decimal(str(element_modifier))
            else:
                modified_base_damage = float(base_damage) * float(element_modifier)
                
            # Check for special damage types
            ignore_armor = getattr(target, 'ignore_armor_this_hit', False)
            true_damage = getattr(target, 'true_damage', False)
            bypass_defenses = getattr(target, 'bypass_defenses', False)
            ignore_all = getattr(target, 'ignore_all_defenses', False)
            partial_true_damage = getattr(target, 'partial_true_damage', 0)

            # True damage window from terror effects
            if self._has_effect(target, "true_damage_window"):
                ignore_all = True

            if ignore_all or true_damage or ignore_armor or bypass_defenses:
                damage = modified_base_damage  # No armor reduction
                blocked_damage = Decimal('0')
            elif partial_true_damage > 0:
                # Handle partial true damage: some bypasses armor, some doesn't
                normal_damage_after_armor = max(modified_base_damage - target_armor, Decimal('10'))
                damage = normal_damage_after_armor + Decimal(str(partial_true_damage))
                blocked_damage = min(modified_base_damage, target_armor)
            else:
                blocked_damage = min(modified_base_damage, target_armor)
                damage = max(modified_base_damage - target_armor, Decimal('10'))

            # Clear special damage flags
            for flag in ['ignore_armor_this_hit', 'true_damage', 'bypass_defenses', 'ignore_all_defenses', 'partial_true_damage']:
                if hasattr(target, flag):
                    delattr(target, flag)
            
            # Apply additional damage reduction from passive effects if any
            if hasattr(target, 'damage_reduction') and target.damage_reduction > 0:
                # Cap damage reduction at 90%
                if isinstance(target.damage_reduction, Decimal):
                    damage_reduction = min(Decimal('0.9'), target.damage_reduction)
                else:
                    damage_reduction = min(0.9, float(target.damage_reduction))
                
                # Apply damage reduction based on type
                if isinstance(damage, Decimal):
                    if isinstance(damage_reduction, Decimal):
                        damage = damage * (Decimal('1.0') - damage_reduction)
                    else:
                        damage = damage * (Decimal('1.0') - Decimal(str(damage_reduction)))
                else:
                    if isinstance(damage_reduction, Decimal):
                        damage = float(damage) * (1.0 - float(damage_reduction))
                    else:
                        damage *= (1.0 - damage_reduction)
                        
                damage = round(damage, 2)

            # Apply damage taken modifiers (e.g. Death Mark)
            damage = self._apply_damage_taken_modifiers(target, damage)
            
            # Track damage taken for reflection calculations
            if hasattr(target, 'damage_taken_this_turn'):
                target.damage_taken_this_turn = damage
            
            # Check for cheat death if enabled
            cheat_death_triggered = False
            if (self.config.get("class_buffs", True) and 
                self.config.get("cheat_death", True) and
                not target.is_pet and
                hasattr(target, 'death_cheat_chance') and 
                target.death_cheat_chance > 0 and
                target not in self.cheat_death_used):
                
                # Only trigger cheat death if the damage would be fatal
                # Ensure consistent types for comparison
                if isinstance(target.hp, Decimal):
                    # Convert damage to Decimal if needed
                    damage_decimal = damage if isinstance(damage, Decimal) else Decimal(str(damage))
                    fatal_damage = target.hp - damage_decimal <= Decimal('0')
                else:
                    # Both are regular numbers
                    fatal_damage = target.hp - damage <= 0
                    
                if fatal_damage:
                    cheat_death_roll = random.randint(1, 100)
                    if cheat_death_roll <= target.death_cheat_chance:
                        # Reduce damage and restore player to 75 HP
                        if isinstance(target.hp, Decimal):
                            damage = max(Decimal('0'), target.hp - Decimal('75'))
                            target.hp = Decimal('75')  # Set to 75 HP
                        else:
                            damage = max(0, target.hp - 75)
                            target.hp = 75  # Set to 75 HP
                        cheat_death_triggered = True
                        self.cheat_death_used.add(target)
            
            # PROCESS PET SKILL EFFECTS ON DAMAGE TAKEN
            defender_messages = []
            if (target.is_pet and hasattr(self.ctx.bot.cogs["Battles"], "battle_factory")):
                pet_ext = self.ctx.bot.cogs["Battles"].battle_factory.pet_ext
                damage, defender_messages = pet_ext.process_skill_effects_on_damage_taken(target, dragon, damage)
            
            # Apply Death's Embrace passive effect (10% chance to instantly kill)
            death_embrace_triggered = False
            if "Death's Embrace" in dragon.passives and random.random() < 0.1:
                death_embrace_triggered = True
                # Instantly kill the target
                if isinstance(target.hp, Decimal):
                    target.hp = Decimal('0')
                else:
                    target.hp = 0
                damage = target.max_hp  # Set damage to max HP for display purposes
            
            # Apply damage only if cheat death didn't trigger and death embrace didn't trigger
            if not cheat_death_triggered and not death_embrace_triggered:
                target.take_damage(damage)
                
                # Apply Soul Devourer passive effect (steal 15% of damage as health)
                if "Soul Devourer" in dragon.passives:
                    if isinstance(damage, Decimal):
                        stolen_health = damage * Decimal('0.15')  # 15% of damage
                    else:
                        stolen_health = float(damage) * 0.15
                    dragon.heal(stolen_health)
            
            # Apply damage link mirroring
            if not death_embrace_triggered:
                await self._apply_damage_link(target, damage)

            # Log the action
            if death_embrace_triggered:
                message = f"{dragon.name} uses **{move_name}** on {target.name}! "
                message += f"💀 **DEATH'S EMBRACE!** {target.name} is instantly slain!{element_message}"
            else:
                message = f"{dragon.name} uses **{move_name}** on {target.name}! "
                message += f"{target.name} takes **{self.format_number(damage)} HP** damage.{element_message}"
            
            # Add skill effect messages
            if defender_messages:
                message += "\n" + "\n".join(defender_messages)
            
            # Add cheat death message if triggered
            if cheat_death_triggered:
                message += f"\n⚡ **CHEAT DEATH!** {target.name} refuses to fall and is restored to 75 HP!"
                
            # Add Soul Devourer message if triggered
            if "Soul Devourer" in dragon.passives and not death_embrace_triggered:
                if isinstance(damage, Decimal):
                    stolen_health = damage * Decimal('0.15')
                else:
                    stolen_health = float(damage) * 0.15
                message += f"\n👻 **SOUL DEVOURER!** {dragon.name} steals **{self.format_number(stolen_health)} HP** from {target.name}!"
            
            # Handle tank reflection damage if class_buffs and reflection_damage are enabled
            if (self.config.get("class_buffs", True) and 
                self.config.get("reflection_damage", True) and
                not target.is_pet and
                hasattr(target, 'tank_evolution') and 
                target.tank_evolution is not None and
                hasattr(target, 'has_shield') and 
                target.has_shield):
                
                # Calculate reflection based on tank evolution level
                reflection_multiplier = 0.0
                if hasattr(self.ctx.bot.cogs["Battles"], "class_ext"):
                    level = target.tank_evolution
                    reflection_multiplier = self.ctx.bot.cogs["Battles"].class_ext.evolution_reflection_multiplier.get(level, 0.0)
                
                if reflection_multiplier > 0:
                    if isinstance(damage, Decimal):
                        reflected_damage = damage * Decimal(str(reflection_multiplier))
                    else:
                        reflected_damage = float(damage) * float(reflection_multiplier)
                    reflected_damage = round(reflected_damage, 2)
                    
                    if reflected_damage > 0:
                        dragon.take_damage(reflected_damage)
                        message += f"\n🛡️ {target.name}'s shield reflects **{self.format_number(reflected_damage)} HP** damage back to {dragon.name}!"
            
            # Apply effects if proc chance is met
            if random.random() < effect_chance:
                effect_desc = await self.apply_effect(target, effect, damage)
                if effect_desc:
                    message += f" {effect_desc}"
                    if effect in ("possess_player", "possess_pet", "possess_player_and_pet_permanent"):
                        self._move_cooldowns[effect] = 2
                    
            await self.add_to_log(message)
            
    async def process_player_turn(self, player):
        """Process a player's turn"""
        possessed = self._has_effect(player, "possessed")
        if possessed:
            party_targets = [c for c in self._alive_party_combatants() if c is not player]
            if not party_targets:
                await self.add_to_log(f"{player.name} is possessed but has no valid targets!")
                return
            target = random.choice(party_targets)
        else:
            enemy_targets = []
            if self.dragon.is_alive():
                enemy_targets.append(self.dragon)
            enemy_targets.extend(self._alive_possessed())
            if not enemy_targets:
                await self.add_to_log(f"{player.name} has no valid targets!")
                return
            target = random.choice(enemy_targets)
        is_dragon_target = target is self.dragon or getattr(target, "is_dragon", False)
        
        # Calculate damage based on player's damage stat
        base_damage = player.damage
        
        # Apply passive effects that reduce player damage
        if is_dragon_target and "Corruption" in target.passives:
            if isinstance(base_damage, Decimal):
                base_damage = base_damage * Decimal('0.8')  # 20% damage reduction
            else:
                base_damage *= 0.8
                
        if is_dragon_target and "Aspect of death" in target.passives:
            if isinstance(base_damage, Decimal):
                base_damage = base_damage * Decimal('0.7')  # 30% damage reduction
            else:
                base_damage *= 0.7
                
        if is_dragon_target and "Void Corruption" in target.passives:
            if isinstance(base_damage, Decimal):
                base_damage = base_damage * Decimal('0.75')  # 25% damage reduction
            else:
                base_damage *= 0.75
                
        if is_dragon_target and "Eternal Winter" in target.passives:
            if isinstance(base_damage, Decimal):
                base_damage = base_damage * Decimal('0.6')  # 40% damage reduction
            else:
                base_damage *= 0.6
            
        # Apply luck effects if enabled (critical hits)
        crit_message = ""
        if self.config.get("luck_effects", True) and hasattr(player, "luck") and not player.is_pet:
            # Base crit chance from luck stat, typically 5-15%
            crit_chance = min(0.2, player.luck / 1000)  # Cap at 20%
            
            # Check for critical hit
            if random.random() < crit_chance:
                if isinstance(base_damage, Decimal):
                    base_damage = base_damage * Decimal('1.5')  # 50% bonus damage
                else:
                    base_damage = float(base_damage) * 1.5
                crit_message = " **CRITICAL HIT!** "
        
        # Apply random variation (±10%)
        variation = random.uniform(0.9, 1.1)
        
        # Apply variation based on type
        if isinstance(base_damage, Decimal):
            # Convert variation to Decimal for safe multiplication
            damage = base_damage * Decimal(str(variation))
        else:
            damage = float(base_damage) * variation
        
        # Apply element effects if enabled
        element_message = ""
        if self.config.get("element_effects", True) and hasattr(self.ctx.bot.cogs["Battles"], "element_ext"):
            # Use configured dragon element for elemental modifiers (or target element if not dragon)
            dragon_element = self.dragon_element or "Water"
            defender_element = (
                dragon_element if is_dragon_target else self.resolve_defense_element(target)
            )
            player_element = self.resolve_attack_element(player)
            
            if player_element and defender_element:
                # Get element multiplier from element extension
                element_mod = self.ctx.bot.cogs["Battles"].element_ext.calculate_damage_modifier(
                    self.ctx,
                    player_element,
                    defender_element
                )
                element_multiplier = 1.0 + element_mod  # Convert from -0.3/0.3 to 0.7/1.3
                
                # Apply element multiplier
                if element_mod != 0:
                    if isinstance(damage, Decimal):
                        damage = damage * Decimal(str(element_multiplier))
                    else:
                        damage *= element_multiplier
                        
                    if element_multiplier > 1.0:
                        element_message = f" ({player_element} is strong against {defender_element}!)"
                    else:
                        element_message = f" ({player_element} is weak against {defender_element}!)"
        
        # Use canonical pet damage resolver for pet attacks.
        skill_messages = []
        defender_messages = []
        if player.is_pet:
            outcome = self.resolve_pet_attack_outcome(
                player,
                target,
                damage,
                apply_element_mod=False,  # Already applied in this method.
                damage_variance=0,
                minimum_damage=Decimal("10"),
            )
            final_damage = outcome.final_damage
            blocked_damage = outcome.blocked_damage
            skill_messages = outcome.skill_messages
            defender_messages = outcome.defender_messages
        else:
            # Standard non-pet damage path.
            ignore_armor = getattr(target, 'ignore_armor_this_hit', False) if is_dragon_target else False
            true_damage = getattr(target, 'true_damage', False) if is_dragon_target else False
            bypass_defenses = getattr(target, 'bypass_defenses', False) if is_dragon_target else False
            ignore_all = getattr(target, 'ignore_all_defenses', False) if is_dragon_target else False

            if ignore_all or true_damage or ignore_armor or bypass_defenses:
                final_damage = damage  # No armor reduction
                blocked_damage = Decimal('0')
            else:
                blocked_damage = min(damage, target.armor)
                final_damage = max(damage - target.armor, Decimal('10'))

            # Clear special damage flags for non-pet path.
            if is_dragon_target:
                for flag in ['ignore_armor_this_hit', 'true_damage', 'bypass_defenses', 'ignore_all_defenses', 'partial_true_damage']:
                    if hasattr(target, flag):
                        delattr(target, flag)
        
        # Apply damage reduction from passive effects AFTER standard damage calculation
        damage_reduction = Decimal('0.0')
        
        # Apply passive effects
        if is_dragon_target and "Ice Armor" in target.passives:
            damage_reduction += Decimal('0.2')  # 20% damage reduction from Ice Armor
        
        if damage_reduction > 0:
            if isinstance(final_damage, Decimal):
                final_damage = final_damage * (Decimal('1') - damage_reduction)
            else:
                final_damage = float(final_damage) * (1 - float(damage_reduction))
            final_damage = round(final_damage, 2)

        # Apply damage taken modifiers (e.g. Death Mark)
        final_damage = self._apply_damage_taken_modifiers(target, final_damage)
        
        # Include defender pet mitigation messages if present.
        if defender_messages:
            skill_messages.extend(defender_messages)
        
        # Apply Reality Bender passive effect (50% chance to negate attack)
        reality_bender_negated = False
        if is_dragon_target and "Reality Bender" in target.passives and random.random() < 0.5:
            reality_bender_negated = True
            # Reflect some damage back to the player
            if isinstance(final_damage, Decimal):
                reflected_damage = final_damage * Decimal('0.3')  # Reflect 30% of damage
            else:
                reflected_damage = float(final_damage) * 0.3
            player.take_damage(reflected_damage)
            message = f"{player.name} attacks!{crit_message} 🌀 **REALITY BENDER** negates the attack! {player.name} takes **{self.format_number(reflected_damage)} HP** reflected damage!"
        else:
            # Apply damage to dragon normally
            target.take_damage(final_damage)
            if possessed:
                message = f"{player.name} attacks under possession!{crit_message} {target.name} takes **{self.format_number(final_damage)} HP** damage.{element_message}"
            else:
                message = f"{player.name} attacks!{crit_message} {target.name} takes **{self.format_number(final_damage)} HP** damage.{element_message}"

        # Apply damage link mirroring
        await self._apply_damage_link(target, final_damage)
        
        # Add skill effect messages
        if skill_messages:
            message += "\n" + "\n".join(skill_messages)
        
        # Handle lifesteal if applicable for class buffs
        if (self.config.get("class_buffs", True) and 
            not player.is_pet and 
            hasattr(player, 'lifesteal_percent') and
            player.lifesteal_percent > 0):
            
            if isinstance(final_damage, Decimal):
                lifesteal_amount = (final_damage * Decimal(str(player.lifesteal_percent)) / Decimal('100'))
            else:
                lifesteal_amount = (float(final_damage) * float(player.lifesteal_percent) / 100.0)
            await self._apply_heal(player, lifesteal_amount, source="lifesteal")
            message += f" Lifesteals: **{self.format_number(lifesteal_amount)} HP**"
            
        # Handle mage fireball chance if class_buffs and fireball_chance are enabled
        if (self.config.get("class_buffs", True) and 
            self.config.get("fireball_chance", 0.3) > 0 and
            not player.is_pet and
            hasattr(player, 'mage_evolution') and 
            player.mage_evolution is not None):
            
            fireball_chance = self.config.get("fireball_chance", 0.3)
            if random.random() < fireball_chance:
                # Calculate fireball damage based on mage evolution level
                damage_multiplier = 1.0
                if hasattr(self.ctx.bot.cogs["Battles"], "class_ext"):
                    level = player.mage_evolution
                    damage_multiplier = self.ctx.bot.cogs["Battles"].class_ext.evolution_damage_multiplier.get(level, 1.0)
                
                if isinstance(final_damage, Decimal):
                    fireball_damage = round(final_damage * Decimal(str(damage_multiplier)), 2)
                else:
                    fireball_damage = round(float(final_damage) * float(damage_multiplier), 2)
                target.take_damage(fireball_damage)
                message += f"\n🔥 **FIREBALL!** {player.name} casts a fireball for **{self.format_number(fireball_damage)} HP** additional damage!"
            
        # Handle dragon's reflection damage if reflection_damage is enabled
        if is_dragon_target and self.config.get("reflection_damage", True) and "Reflective Scales" in target.passives:
            reflection_percent = Decimal('15')  # 15% reflection damage
            if isinstance(final_damage, Decimal):
                reflection_damage = final_damage * (reflection_percent / Decimal('100'))
            else:
                reflection_damage = float(final_damage) * (float(reflection_percent) / 100.0)
            reflection_damage = round(reflection_damage, 2)
            
            if reflection_damage > 0:
                player.take_damage(reflection_damage)
                message += f"\n{target.name}'s reflective scales return **{self.format_number(reflection_damage)} HP** damage!"
                
        # Handle PLAYER'S reflection damage if class_buffs and reflection_damage are enabled
        if (self.config.get("class_buffs", True) and 
            self.config.get("reflection_damage", True) and
            not player.is_pet and
            hasattr(player, 'tank_evolution') and 
            player.tank_evolution is not None and
            hasattr(player, 'has_shield') and 
            player.has_shield):
            
            # Calculate reflection based on tank evolution level
            reflection_multiplier = 0.0
            if hasattr(self.ctx.bot.cogs["Battles"], "class_ext"):
                level = player.tank_evolution
                reflection_multiplier = self.ctx.bot.cogs["Battles"].class_ext.evolution_reflection_multiplier.get(level, 0.0)
            
            if reflection_multiplier > 0:
                if isinstance(final_damage, Decimal):
                    reflection_damage = final_damage * Decimal(str(reflection_multiplier))
                else:
                    reflection_damage = float(final_damage) * float(reflection_multiplier)
                reflection_damage = round(reflection_damage, 2)
                
                if reflection_damage > 0:
                    target.take_damage(reflection_damage)
                    message += f"\n🛡️ **SHIELD REFLECTION!** {player.name}'s shield reflects **{self.format_number(reflection_damage)} HP** damage!"
        
        # Check for skeleton summoning after skill processing
        if hasattr(player, 'summon_skeleton'):
            skeleton_data = player.summon_skeleton
            
            # Create skeleton combatant
            from cogs.battles.core.combatant import Combatant
            skeleton = Combatant(
                user=f"Skeleton Warrior #{player.skeleton_count}",  # User/name
                hp=skeleton_data['hp'],
                max_hp=skeleton_data['hp'],  # Same as current HP
                damage=skeleton_data['damage'],
                armor=skeleton_data['armor'],
                element=skeleton_data['element'],
                luck=50,  # Base luck
                is_pet=True,
                name=f"Skeleton Warrior #{player.skeleton_count}"
            )
            skeleton.is_summoned = True
            skeleton.summoner = player
            
            # Add skeleton to player team (dragon battles use player_team and dragon_team)
            if player in self.player_team.combatants:
                self.player_team.combatants.append(skeleton)
                self._player_turn_queue.append(skeleton)
                message += f"\n💀 A skeleton warrior joins your side!"
            else:
                self.dragon_team.combatants.append(skeleton)
                message += f"\n💀 A skeleton warrior joins the dragon side!"
            
            # Clear the summon flag
            delattr(player, 'summon_skeleton')
        
        await self.add_to_log(message)

    def _get_effects(self, combatant):
        return self.status_effects.get(combatant.name, [])

    def _get_effect(self, combatant, effect_type):
        for effect in self._get_effects(combatant):
            if effect.get("type") == effect_type:
                return effect
        return None

    def _has_effect(self, combatant, effect_type):
        return self._get_effect(combatant, effect_type) is not None

    async def _apply_damage_link(self, target, damage):
        if self._damage_link_guard:
            return
        effect = self._get_effect(target, "damage_link")
        if not effect:
            return
        linked_name = effect.get("linked")
        if not linked_name:
            return
        linked_target = None
        for combatant in self.player_team.combatants:
            if combatant.name == linked_name and combatant.is_alive():
                linked_target = combatant
                break
        if not linked_target:
            return
        if isinstance(damage, Decimal):
            mirrored = damage * Decimal("0.5")
        else:
            mirrored = float(damage) * 0.5
        self._damage_link_guard = True
        try:
            linked_target.take_damage(mirrored)
            await self.add_to_log(
                f"🔗 **Terror Link**: {linked_target.name} takes **{self.format_number(mirrored)} HP** mirrored damage!"
            )
        finally:
            self._damage_link_guard = False

    async def _apply_heal(self, combatant, amount, source="heal"):
        if self._has_effect(combatant, "invert_healing"):
            if isinstance(amount, Decimal):
                dmg = amount
            else:
                dmg = float(amount)
            combatant.take_damage(dmg)
            await self.add_to_log(
                f"🩸 **Inverted Healing**: {combatant.name} takes **{self.format_number(dmg)} HP** instead!"
            )
            return
        curse = self._get_effect(combatant, "curse")
        if curse:
            reduction = curse.get("value", 0.5)
            if isinstance(amount, Decimal):
                amount = amount * (Decimal("1") - Decimal(str(reduction)))
            else:
                amount = float(amount) * (1.0 - float(reduction))
        combatant.heal(amount)

    def _apply_damage_taken_modifiers(self, target, damage):
        death_mark = self._get_effect(target, "death_mark")
        if not death_mark:
            return damage
        multiplier = death_mark.get("value", 1.3)
        if isinstance(damage, Decimal):
            return damage * Decimal(str(multiplier))
        return float(damage) * float(multiplier)
        
    async def initialize_player(self, player, player_data):
        """Initialize a player combatant"""
        # Set default properties
        player.max_hp = player_data.get("health", 100)
        player.hp = player.max_hp
        player.armor = player_data.get("armor", 0)
        player.damage = player_data.get("damage", 10)
        player.name = player_data.get("name", "Player")
        player.luck = player_data.get("luck", 0)
        player.damage_taken_this_turn = 0  # For tracking reflection damage
        
        # Apply class-specific buffs if enabled
        if self.config.get("class_buffs", True):
            # Set class buff attributes based on player data
            player.death_cheat_chance = player_data.get("death_cheat_chance", 0)
            player.lifesteal_percent = player_data.get("lifesteal_percent", 0)
            player.mage_evolution = player_data.get("mage_evolution", None)
            player.tank_evolution = player_data.get("tank_evolution", None)
            player.ranger_evolution = player_data.get("ranger_evolution", None)
            player.has_shield = player_data.get("has_shield", False)
            
            # Apply tank health buff if applicable
            if player.tank_evolution is not None and hasattr(self.ctx.bot.cogs["Battles"], "class_ext"):
                old_max_hp = player.max_hp
                player.max_hp, _ = self.ctx.bot.cogs["Battles"].class_ext.apply_tank_buffs(
                    player.max_hp, 
                    player.tank_evolution, 
                    player.has_shield
                )
                player.hp = player.hp * (player.max_hp / old_max_hp)  # Scale current HP too
                
    async def create_battle_embed(self):
        """Create the battle status embed"""
        # Get current stage name
        stage_name = self.dragon.stage
        
        # Get element emoji mapping from Battles cog
        emoji_to_element = {}
        element_to_emoji = {}
        if hasattr(self.ctx.bot.cogs["Battles"], "emoji_to_element"):
            emoji_to_element = self.ctx.bot.cogs["Battles"].emoji_to_element
            # Create reverse mapping for element to emoji
            element_to_emoji = {v: k for k, v in emoji_to_element.items()}
        
        # Create embed
        embed = discord.Embed(
            title=f"Ice Dragon Challenge - Level {self.dragon_level}",
            description=f"The **{stage_name}** is battling the party...",
            color=discord.Color.blue()
        )
        
        # Add dragon info
        dragon_hp = max(0, float(self.dragon.hp))
        dragon_max_hp = float(self.dragon.max_hp)
        dragon_hp_percent = (dragon_hp / dragon_max_hp) * 100 if dragon_max_hp > 0 else 0
        dragon_hp_bar = self.create_hp_bar(dragon_hp, dragon_max_hp, length=20)
        
        # Get dragon element emoji from current stage element
        dragon_element_key = self.dragon_element or "Water"
        dragon_element_emoji = element_to_emoji.get(dragon_element_key, "❓")
        
        embed.add_field(
            name=f"🐉 {self.dragon.name} {dragon_element_emoji}",
            value=f"HP: {dragon_hp:.1f}/{dragon_max_hp:.1f} ({dragon_hp_percent:.1f}%)\n{dragon_hp_bar}",
            inline=False
        )
        
        # Add player info - each on their own line (not inline)
        for player in self.get_alive_players():
            player_hp = max(0, float(player.hp))
            player_max_hp = float(player.max_hp)
            player_hp_percent = (player_hp / player_max_hp) * 100 if player_max_hp > 0 else 0
            player_hp_bar = self.create_hp_bar(player_hp, player_max_hp, length=15)

            # Get player element emoji
            player_element_emoji = "❓"
            if hasattr(player, 'element') and player.element and player.element in element_to_emoji:
                player_element_emoji = element_to_emoji[player.element]
            possession_marker = " 🌀" if self._has_effect(player, "possessed") else ""
            
            # Set name based on player type with element emoji
            if hasattr(player, 'is_pet') and player.is_pet:
                field_name = f"{player.name} {player_element_emoji}{possession_marker}"
            else:
                field_name = f"{player.name} {player_element_emoji}{possession_marker}"
                
            embed.add_field(
                name=field_name,
                value=f"HP: {player_hp:.1f}/{player_max_hp:.1f} ({player_hp_percent:.1f}%)\n{player_hp_bar}",
                inline=False  # Set to False so each combatant appears on a new line
            )
            
        # Add battle log
        log_text = ""
        max_length = 900  # Leave some room for "..." and potential formatting
        
        # Process log entries in reverse order (newest first)
        for action_num, msg in reversed(self.log):
            # Format the message with proper newlines and action number
            formatted_msg = str(msg).replace('\n', '\n    ')  # Indent wrapped lines
            new_entry = f"**Action #{action_num}**\n{formatted_msg}\n\n"
            
            # Check if adding this entry would exceed the max length
            if len(log_text) + len(new_entry) > max_length:
                log_text = "...\n\n" + log_text  # Add ellipsis for truncated messages
                break
                
            log_text = new_entry + log_text
        
        if not log_text.strip():
            log_text = "Battle starting..."
        else:
            # Ensure we don't exceed max length after all processing
            log_text = log_text[-max_length:].lstrip('\n')
            
        embed.add_field(name="Battle Log", value=log_text, inline=False)
        
        # Add battle ID to footer for GM replay functionality
        embed.set_footer(text=f"Battle ID: {self.battle_id}")
        
        return embed
        
    async def update_display(self):
        """Update the battle display"""
        embed = await self.create_battle_embed()
        if self.battle_message:
            await self.battle_message.edit(embed=embed)
        else:
            self.battle_message = await self.ctx.send(embed=embed)
            
    async def end_battle(self):
        """End the battle and determine outcome"""
        self.finished = True
        
        # Save final battle data to database for replay
        await self.save_battle_to_database()
        
        party_players_alive = [c for c in self._alive_party_combatants() if not c.is_pet]
        party_pets_alive = [c for c in self._alive_party_combatants() if c.is_pet]
        party_defeated = not party_players_alive
        if party_defeated and self.config.get("pets_continue_battle", False) and self.config.get("allow_pets", True):
            party_defeated = not party_pets_alive

        if party_defeated:
            await self.add_to_log(f"**Defeat!** The party has been wiped out by the {self.dragon.name}!")
            await self.update_display()
            return False

        if self.dragon.hp <= 0 and not self._alive_possessed():
            await self.add_to_log(f"**Victory!** The {self.dragon.name} has been defeated!")
            await self.update_display()
            return True
            
        # Check for timeout
        if await self.is_timed_out():
            await self.add_to_log("**Time's up!** The battle took too long and ended in a draw.")
            await self.update_display()
            return None
            
        return None
        
    async def is_battle_over(self):
        """Check if battle has conditions to end"""
        # Check if battle was explicitly finished
        if self.finished:
            return True
            
        # Check if dragon and any possessed enemies are defeated
        if self.dragon.hp <= 0 and not self._alive_possessed():
            return True
            
        # Check for timeout
        if await self.is_timed_out():
            return True
            
        party_players_alive = [c for c in self._alive_party_combatants() if not c.is_pet]
        party_pets_alive = [c for c in self._alive_party_combatants() if c.is_pet]
        party_defeated = not party_players_alive
        
        if party_defeated:
            if self.config.get("pets_continue_battle", False) and self.config.get("allow_pets", True):
                if party_pets_alive:
                    return False
            return True
            
        # Otherwise battle continues
        return False
    
    def get_next_combatant(self):
        """Get the next combatant in turn order"""
        # Simplified turn system - alternate between dragon and a random player
        # Use current_turn instead of action_number to determine whose turn it is
        if self._extra_dragon_turns > 0:
            self._extra_dragon_turns -= 1
            self.current_turn += 1
            return self.dragon
        if self.current_turn % 2 == 0:  # Dragon on even turns (0, 2, 4, etc.)
            self.current_turn += 1
            return self.dragon
        else:  # Players on odd turns (1, 3, 5, etc.)
            self.current_turn += 1
            if not self._player_turn_queue:
                self._refresh_player_turn_queue()
            for _ in range(len(self._player_turn_queue)):
                combatant = self._player_turn_queue[0]
                self._player_turn_queue.rotate(-1)
                if combatant.is_alive():
                    return combatant
            self._refresh_player_turn_queue()
            if self._player_turn_queue:
                combatant = self._player_turn_queue[0]
                self._player_turn_queue.rotate(-1)
                return combatant
            return self.dragon  # Fallback
    
    def get_alive_players(self):
        """Get all alive players"""
        return [player for player in self.players if player.hp > 0]

    def _refresh_player_turn_queue(self):
        alive = [c for c in self.player_team.combatants if c.is_alive()]
        alive = self.prioritize_turn_order(alive)
        self._player_turn_queue = deque(alive)

    def _is_possessed(self, combatant):
        return self._has_effect(combatant, "possessed")

    def _alive_party_combatants(self):
        return [
            c for c in self.player_team.combatants
            if c.is_alive() and not self._is_possessed(c)
        ]

    def _alive_possessed(self):
        return [
            c for c in self.player_team.combatants
            if c.is_alive() and self._is_possessed(c)
        ]
        
    def get_dragon_stage_name(self):
        """Determine which dragon stage to use based on level"""
        if self.dragon_stage_info and hasattr(self.dragon, "stage"):
            return self.dragon.stage
        return "Eternal Frost"
    
    async def process_status_effects(self, combatant):
        """Process status effects for a combatant"""
        # Use combatant's name as a key instead of id
        if combatant.name not in self.status_effects:
            return
            
        for effect in self.status_effects[combatant.name]:
            # Apply effect
            if effect["type"] == "dot":
                # Damage over time
                damage = effect["value"]
                combatant.take_damage(damage)
                await self.add_to_log(f"{combatant.name} takes **{self.format_number(damage)} HP** from {effect['name']}!")

    def _decrement_status_effects(self, combatant):
        if combatant.name not in self.status_effects:
            return
        effects_to_remove = []
        for effect in self.status_effects[combatant.name]:
            if effect.get("duration", 0) < 0:
                continue
            effect["duration"] -= 1
            if effect.get("duration", 0) <= 0:
                if effect["type"] == "shatter_armor":
                    restore = effect.get("value", None)
                    if restore is not None:
                        combatant.armor = restore
                effects_to_remove.append(effect)
        for effect in effects_to_remove:
            self.status_effects[combatant.name].remove(effect)
            self.ctx.bot.loop.create_task(
                self.add_to_log(f"{effect['name']} on {combatant.name} has worn off.")
            )
        if combatant.name in self.status_effects and not self.status_effects[combatant.name]:
            del self.status_effects[combatant.name]
    
    def is_stunned(self, combatant):
        """Check if combatant is stunned"""
        if combatant.name not in self.status_effects:
            return False
            
        for effect in self.status_effects[combatant.name]:
            if effect["type"] == "stun" and effect["duration"] > 0:
                return True
                
        return False
        
    async def apply_effect(self, target, effect_type, damage):
        """Apply a status effect to a target"""
        # Use target.name as the unique identifier
        # Every combatant should have a name
            
        # Initialize effects list if needed
        if target.name not in self.status_effects:
            self.status_effects[target.name] = []
            
        # Map legacy/unused effects to supported ones
        effect_aliases = {
            "summon_adds": "extra_dragon_turn",
            "dimension_tear": "true_damage_window",
            "time_stop": "aoe_stun",
            "eternal_curse": "curse",
            "world_ender": "global_dot",
            "soul_drain": "drain_max_hp",
            "void_explosion": "aoe_dot",
        }
        alias = effect_aliases.get(effect_type)
        if alias:
            return await self.apply_effect(target, alias, damage)

        # Define effect details
        effect_desc = ""
        
        if effect_type == "freeze":
            self.status_effects[target.name].append({
                "type": "stun",
                "name": "Freeze",
                "duration": 1,
                "value": 0
            })
            effect_desc = "🧊 **Frozen** for 1 turn!"
            
        elif effect_type == "stun":
            self.status_effects[target.name].append({
                "type": "stun",
                "name": "Stun",
                "duration": 1,
                "value": 0
            })
            effect_desc = "⚡ **Stunned** for 1 turn!"
            
        elif effect_type == "aoe_stun":
            self.status_effects[target.name].append({
                "type": "stun",
                "name": "Mass Stun",
                "duration": 1,
                "value": 0
            })
            effect_desc = "⚡ **Mass Stunned** for 1 turn!"
            
        elif effect_type == "dot":
            # Ensure type compatibility for Decimal
            if isinstance(damage, Decimal):
                dot_damage = damage * Decimal('0.2')  # 20% of initial damage per turn
            else:
                dot_damage = damage * 0.2  # 20% of initial damage per turn
                
            self.status_effects[target.name].append({
                "type": "dot",
                "name": "Damage Over Time",
                "duration": 3,
                "value": dot_damage
            })
            effect_desc = "🔥 **Damage over time** for 3 turns!"
            
        elif effect_type == "aoe_dot":
            # Ensure type compatibility for Decimal
            if isinstance(damage, Decimal):
                dot_damage = damage * Decimal('0.15')  # 15% of initial damage per turn
            else:
                dot_damage = damage * 0.15  # 15% of initial damage per turn
                
            self.status_effects[target.name].append({
                "type": "dot",
                "name": "Area DoT",
                "duration": 2,
                "value": dot_damage
            })
            effect_desc = "🔥 **Area damage over time** for 2 turns!"
            
        elif effect_type == "curse":
            # Reduce healing received
            self.status_effects[target.name].append({
                "type": "curse",
                "name": "Curse",
                "duration": 3,
                "value": 0.5  # 50% healing reduction
            })
            effect_desc = "☠️ **Cursed** for 3 turns! (Reduced healing)"
            
        elif effect_type == "death_mark":
            # Increase damage taken
            self.status_effects[target.name].append({
                "type": "death_mark",
                "name": "Death Mark",
                "duration": 3,
                "value": 1.3  # 30% increased damage taken
            })
            effect_desc = "💀 **Death Mark** for 3 turns! (Increased damage taken)"
            
        elif effect_type == "global_dot":
            # Handle global DOT (affects all targets)
            # Ensure type compatibility for Decimal
            if isinstance(damage, Decimal):
                dot_damage = damage * Decimal('0.12')  # 12% of initial damage per turn
            else:
                dot_damage = damage * 0.12  # 12% of initial damage per turn
                
            self.status_effects[target.name].append({
                "type": "dot",
                "name": "Global Affliction",
                "duration": 3,
                "value": dot_damage
            })
            effect_desc = "🔥🌎 **Global affliction** for 3 turns!"
            
        elif effect_type == "random_debuff":
            # Apply a random debuff
            debuffs = ["dot", "stun", "curse"]
            selected_debuff = random.choice(debuffs)
            # Recursively apply the selected debuff
            return await self.apply_effect(target, selected_debuff, damage)

        elif effect_type == "possess_player":
            alive_allies = self._alive_party_combatants()
            if not any(c is not target for c in alive_allies):
                return ""
            self.status_effects[target.name].append({
                "type": "possessed",
                "name": "Possessed",
                "duration": -1,
                "value": None
            })
            effect_desc = "🌀 **Possessed** for the entire battle!"
            self._possession_used = True

        elif effect_type == "possess_pet":
            pet_target = target if getattr(target, "is_pet", False) else None
            if not pet_target:
                pet_targets = [c for c in self._alive_party_combatants() if c.is_pet]
                pet_target = random.choice(pet_targets) if pet_targets else None
            if pet_target:
                alive_allies = self._alive_party_combatants()
                if not any(c is not pet_target for c in alive_allies):
                    return ""
                if pet_target.name not in self.status_effects:
                    self.status_effects[pet_target.name] = []
                self.status_effects[pet_target.name].append({
                    "type": "possessed",
                    "name": "Beastmind Override",
                    "duration": -1,
                    "value": None
                })
                effect_desc = f"🐾 **{pet_target.name}** is possessed for the entire battle!"
                self._possession_used = True

        elif effect_type == "possess_player_and_pet_permanent":
            player_target = target
            if getattr(target, "is_pet", False):
                player_candidates = [c for c in self._alive_party_combatants() if not c.is_pet]
                if player_candidates:
                    player_target = random.choice(player_candidates)

            # Possess player permanently (battle duration)
            alive_allies = self._alive_party_combatants()
            if len(alive_allies) <= 2:
                return ""
            if not any(c is not player_target for c in alive_allies):
                return ""
            self.status_effects[player_target.name].append({
                "type": "possessed",
                "name": "Dominion",
                "duration": -1,
                "value": None
            })
            # Possess a pet if available
            pet_targets = [c for c in self._alive_party_combatants() if c.is_pet]
            if pet_targets:
                pet_target = random.choice(pet_targets)
                if not any(c is not pet_target for c in alive_allies):
                    return ""
                if pet_target.name not in self.status_effects:
                    self.status_effects[pet_target.name] = []
                self.status_effects[pet_target.name].append({
                    "type": "possessed",
                    "name": "Dominion",
                    "duration": -1,
                    "value": None
                })
                effect_desc = f"🧿 **Dominion!** {player_target.name} and {pet_target.name} are possessed for the entire battle!"
            else:
                effect_desc = f"🧿 **Dominion!** {player_target.name} is possessed for the entire battle!"
            self._dominion_used = True
            self._possession_used = True

        elif effect_type == "shatter_armor":
            self.status_effects[target.name].append({
                "type": "shatter_armor",
                "name": "Armor Shatter",
                "duration": 2,
                "value": float(target.armor) if isinstance(target.armor, Decimal) else target.armor
            })
            target.armor = 0
            effect_desc = "🧊 **Armor Shattered** for 2 turns!"

        elif effect_type == "drain_max_hp":
            if isinstance(target.max_hp, Decimal):
                drain = target.max_hp * Decimal("0.10")
                target.max_hp = max(Decimal("1"), target.max_hp - drain)
            else:
                drain = float(target.max_hp) * 0.10
                target.max_hp = max(1, target.max_hp - drain)
            if target.hp > target.max_hp:
                target.hp = target.max_hp
            effect_desc = "💀 **Soul Tax** reduces max HP by 10%!"

        elif effect_type == "invert_healing":
            self.status_effects[target.name].append({
                "type": "invert_healing",
                "name": "Dread Inversion",
                "duration": 2,
                "value": None
            })
            effect_desc = "🩸 **Healing Inverted** for 2 turns!"

        elif effect_type == "damage_link":
            ally_targets = [
                c for c in self.player_team.combatants
                if c.is_alive() and c is not target
            ]
            if ally_targets:
                linked = random.choice(ally_targets)
                self.status_effects[target.name].append({
                    "type": "damage_link",
                    "name": "Terror Link",
                    "duration": 2,
                    "value": 0.5,
                    "linked": linked.name
                })
                effect_desc = f"🔗 **Terror Link** with {linked.name} for 2 turns!"

        elif effect_type == "turn_skip_chance":
            self.status_effects[target.name].append({
                "type": "turn_skip_chance",
                "name": "Panic",
                "duration": 3,
                "value": 0.5
            })
            effect_desc = "😱 **Panic**: 50% chance to lose turns!"

        elif effect_type == "true_damage_window":
            self.status_effects[target.name].append({
                "type": "true_damage_window",
                "name": "Null Phase",
                "duration": 1,
                "value": None
            })
            effect_desc = "🕳️ **Null Phase**: damage ignores armor for 1 turn!"

        elif effect_type == "extra_dragon_turn":
            self._extra_dragon_turns += 1
            effect_desc = "⏳ **Riftstep**: Dragon takes an extra action!"
            
        return effect_desc

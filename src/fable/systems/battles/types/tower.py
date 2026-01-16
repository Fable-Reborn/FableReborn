# battles/types/tower.py
import asyncio
import random
from decimal import Decimal
import discord
import datetime

from ..core.battle import Battle
from ..core.team import Team

class TowerBattle(Battle):
    """Battle tower battle implementation"""
    
    def __init__(self, ctx, teams, **kwargs):
        super().__init__(ctx, teams, **kwargs)
        self.level = kwargs.get("level", 1)
        self.level_data = kwargs.get("level_data", {})
        self.current_turn = 0
        self.turn_order = []
        self.current_opponent_index = 0  # Start with first opponent
        self.pending_enemy_transition = False  # Flag for enemy transitions
        self.transition_state = 0  # State machine for enemy transitions: 0=normal, 1=intro, 2=battle start
        self.battle_timed_out = False  # Explicit flag for timeout
        self.action_number = 1  # Initialize action counter
        
        # Separate teams for clarity
        self.player_team = teams[0]
        self.enemy_team = teams[1]
        
        # Reference to enemy combatants for easier access
        self.current_enemies = [self.enemy_team.combatants[self.current_opponent_index]]
        
        # Load all battle settings
        settings_cog = self.ctx.bot.get_cog("BattleSettings")
        if settings_cog:
            # Ensure all settings are loaded, with defaults if not found
            self.config = {
                "allow_pets": settings_cog.get_setting("tower", "allow_pets", default=True),
                "class_buffs": settings_cog.get_setting("tower", "class_buffs", default=True),
                "element_effects": settings_cog.get_setting("tower", "element_effects", default=True),
                "luck_effects": settings_cog.get_setting("tower", "luck_effects", default=True),
                "reflection_damage": settings_cog.get_setting("tower", "reflection_damage", default=True),
                "fireball_chance": settings_cog.get_setting("tower", "fireball_chance", default=0.3),
                "cheat_death": settings_cog.get_setting("tower", "cheat_death", default=True),
                "tripping": settings_cog.get_setting("tower", "tripping", default=True),
                "status_effects": settings_cog.get_setting("tower", "status_effects", default=False),
                "pets_continue_battle": settings_cog.get_setting("tower", "pets_continue_battle", default=False)
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
        
    async def add_to_log(self, message, force_new_action=True):
        """Add a message to the battle log
        
        By default, every message gets its own action number to make each combat action distinct.
        Set force_new_action=False to append to the previous action instead.
        """
        if force_new_action or not self.log:
            # Initialize action_number if not already present
            if not hasattr(self, 'action_number'):
                self.action_number = 1
                
            # Use and increment action_number, not log length
            self.log.append((self.action_number, message))
            self.action_number += 1
        else:
            # Add to the most recent action
            action_count, old_message = self.log[-1]
            self.log[-1] = (action_count, f"{old_message}\n{message}")
        
        # IMPORTANT: Call parent method to capture turn state for replay
        await self.capture_turn_state(message)

    async def start_battle(self):
        """Initialize and start the battle"""
        self.started = True
        self.start_time = datetime.datetime.utcnow()
        
        # Save initial battle data to database for replay
        await self.save_battle_to_database()
        
        # Build initial turn order with player team and first enemy
        self.update_turn_order()
        
        # Create battle log with prominent introduction
        first_enemy = self.enemy_team.combatants[self.current_opponent_index]
        intro_message = f"Prepare to face {first_enemy.name}!"
        
        # First action: Introduction
        await self.add_to_log(intro_message, force_new_action=True)
        
        # Create and send initial embed
        embed = await self.create_battle_embed()
        self.battle_message = await self.ctx.send(embed=embed)
        
        # Add a 3-second pause after the intro message for dramatic effect
        await asyncio.sleep(3)
        
        # Second action: Battle begins
        await self.add_to_log(f"Battle against {first_enemy.name} has begun!", force_new_action=True)
        await self.update_display()
        
        return True
    
    def update_turn_order(self):
        """Update turn order based on current combatants"""
        # Clear current turn order
        self.turn_order = []
        
        # Add player team
        for combatant in self.player_team.combatants:
            if combatant.is_alive():
                self.turn_order.append(combatant)
        
        # Add current enemy
        current_enemy = self.enemy_team.combatants[self.current_opponent_index]
        if current_enemy.is_alive():
            self.turn_order.append(current_enemy)
        
        # Shuffle to randomize initial order
        random.shuffle(self.turn_order)
    
    async def handle_enemy_transition(self):
        """Handle transition to the next enemy as a combined action"""
        # This function is called as a separate process_turn action
        
        # Move to the next enemy and show both transition messages in the same action
        self.current_opponent_index += 1
        current_enemy = self.enemy_team.combatants[self.current_opponent_index]
        
        # Show "Prepare to face" message
        await self.add_to_log(f"Prepare to face {current_enemy.name}!", force_new_action=True)
        await self.update_display()  # Show message with previous enemy HP at 0
        await asyncio.sleep(2)  # 2-second pause for dramatic effect
        
        # Add battle start message to the same action
        await self.add_to_log(f"Battle with {current_enemy.name} begins!", force_new_action=False)  # Add to same action
        self.update_turn_order()
        await self.update_display()  # Now show the new enemy HP bar
        
        # Reset the transition flags
        self.pending_enemy_transition = False
        self.transition_state = 0
        return True
        
    async def process_turn(self):
        """Process a single turn of the battle"""
        # Handle pending enemy transitions as a separate action
        if self.pending_enemy_transition:
            return await self.handle_enemy_transition()
            
        if await self.is_battle_over():
            return False
            
        # Get current combatant
        if not self.turn_order:
            self.update_turn_order()
            
        current_combatant = self.turn_order[self.current_turn % len(self.turn_order)]
        self.current_turn += 1
        
        # Skip dead combatants
        if not current_combatant.is_alive():
            return True
            
        # Determine which team the combatant belongs to
        if current_combatant in self.player_team.combatants:
            # Player's turn, target the current enemy
            attacker_team = self.player_team
            current_enemy = self.enemy_team.combatants[self.current_opponent_index]
            
            if not current_enemy.is_alive():
                # Current enemy is defeated, move to next one
                if self.current_opponent_index < len(self.enemy_team.combatants) - 1:
                    # First just update the display to show the defeated enemy with 0 HP
                    await self.update_display()
                    
                    # Schedule the transition to next enemy as a separate action
                    self.pending_enemy_transition = True
                    self.transition_state = 1  # Start at phase 1 (intro)
                    return True
                else:
                    # All enemies defeated
                    return False
            
            target = current_enemy
        else:
            # Enemy's turn, target a random player combatant
            attacker_team = self.enemy_team
            alive_players = [c for c in self.player_team.combatants if c.is_alive()]
            
            if not alive_players:
                return False  # All players are defeated
            
            # Target selection logic - pets have different weighting
            weighted_targets = []
            weights = []
            
            for player in alive_players:
                if player.is_pet:
                    weighted_targets.append(player)
                    weights.append(0.4)  # 40% chance to target pets
                else:
                    weighted_targets.append(player)
                    weights.append(0.6)  # 60% chance to target players
            
            # Normalize weights
            total_weight = sum(weights)
            weights = [w/total_weight for w in weights]
            
            target = random.choices(weighted_targets, weights=weights)[0]
        
        # Process attack based on luck
        luck_roll = random.randint(1, 100)
        
        # For minions/bosses in enemy team, use 10% miss chance instead of luck-based
        if current_combatant in self.enemy_team.combatants:
            hit_success = random.random() > 0.10  # 10% chance to miss
        else:
            # Check for perfect accuracy from Night Vision skill
            has_perfect_accuracy = getattr(current_combatant, 'perfect_accuracy', False)
            hit_success = has_perfect_accuracy or (luck_roll <= current_combatant.luck)
            
        # Initialize message variable
        message = ""
            
        if hit_success:
            # Attack hits
            
            # Special case for mage fireball
            used_fireball = False
            if (current_combatant.mage_evolution and 
                not current_combatant.is_pet and 
                self.config["class_buffs"] and
                random.random() < self.config["fireball_chance"]):
                
                # Calculate fireball damage
                evolution_level = current_combatant.mage_evolution
                damage_multiplier = {
                    1: 1.10,  # 110%
                    2: 1.20,  # 120%
                    3: 1.30,  # 130%
                    4: 1.50,  # 150%
                    5: 1.75,  # 175%
                    6: 2.00,  # 200%
                }.get(evolution_level, 1.0)
                
                damage = (current_combatant.damage + Decimal(random.randint(0, 100)) - target.armor) * Decimal(str(damage_multiplier))
                damage = max(damage, Decimal('1'))
                
                target.take_damage(damage)
                
                message = f"{current_combatant.name} casts Fireball! {target.name} takes **{self.format_number(damage)} HP** damage."
                used_fireball = True
            else:
                # Regular attack
                damage_variance = random.randint(0, 50) if current_combatant.is_pet else random.randint(0, 100)
                
                # Start with base damage
                raw_damage = current_combatant.damage
                
                # Apply element effects to base damage if enabled
                if self.config["element_effects"] and hasattr(self.ctx.bot.cogs["Battles"], "element_ext"):
                    element_mod = self.ctx.bot.cogs["Battles"].element_ext.calculate_damage_modifier(
                        self.ctx,
                        current_combatant.element, 
                        target.element
                    )
                    if element_mod != 0:
                        raw_damage = raw_damage * (1 + Decimal(str(element_mod)))
                
                # Add variance and apply armor
                raw_damage += Decimal(damage_variance)
                
                # PROCESS PET SKILL EFFECTS ON ATTACK
                skill_messages = []
                if (current_combatant.is_pet and hasattr(self.ctx.bot.cogs["Battles"], "battle_factory")):
                    pet_ext = self.ctx.bot.cogs["Battles"].battle_factory.pet_ext
                    raw_damage, skill_messages = pet_ext.process_skill_effects_on_attack(current_combatant, target, raw_damage)
                    # Set flag for turn processing (damage will be set after final calculation)
                    setattr(current_combatant, 'attacked_this_turn', True)
                
                # Check for special damage types
                ignore_armor = getattr(target, 'ignore_armor_this_hit', False)
                true_damage = getattr(target, 'true_damage', False)
                bypass_defenses = getattr(target, 'bypass_defenses', False)
                ignore_all = getattr(target, 'ignore_all_defenses', False)
                partial_true_damage = getattr(target, 'partial_true_damage', 0)
                
                if ignore_all or true_damage or ignore_armor or bypass_defenses:
                    damage = raw_damage  # No armor reduction
                    blocked_damage = Decimal('0')
                elif partial_true_damage > 0:
                    # Handle partial true damage: some bypasses armor, some doesn't
                    normal_damage_after_armor = max(raw_damage - target.armor, Decimal('10'))
                    damage = normal_damage_after_armor + Decimal(str(partial_true_damage))
                    blocked_damage = min(raw_damage, target.armor)
                else:
                    blocked_damage = min(raw_damage, target.armor)  # Can't block more than the armor value
                    damage = max(raw_damage - target.armor, Decimal('10'))  # Minimum 10 damage
                
                # Clear special damage flags
                for flag in ['ignore_armor_this_hit', 'true_damage', 'bypass_defenses', 'ignore_all_defenses', 'partial_true_damage']:
                    if hasattr(target, flag):
                        delattr(target, flag)
                
                # PROCESS PET SKILL EFFECTS ON DAMAGE TAKEN
                defender_messages = []
                if (target.is_pet and hasattr(self.ctx.bot.cogs["Battles"], "battle_factory")):
                    pet_ext = self.ctx.bot.cogs["Battles"].battle_factory.pet_ext
                    damage, defender_messages = pet_ext.process_skill_effects_on_damage_taken(target, current_combatant, damage)
                
                # Store the actual final damage dealt (for skills like Soul Drain)
                if current_combatant.is_pet:
                    setattr(current_combatant, 'last_damage_dealt', damage)
                
                target.take_damage(damage)
                
                message = f"{current_combatant.name} attacks! {target.name} takes **{self.format_number(damage)} HP** damage."
                
                # Add skill effect messages
                if skill_messages:
                    message += "\n" + "\n".join(skill_messages)
                if defender_messages:
                    message += "\n" + "\n".join(defender_messages)
                
                # Check for skeleton summoning after skill processing
                if hasattr(current_combatant, 'summon_skeleton'):
                    skeleton_data = current_combatant.summon_skeleton
                    
                    # Create skeleton combatant
                    from fable.systems.battles.core.combatant import Combatant
                    skeleton = Combatant(
                        user=f"Skeleton Warrior #{current_combatant.skeleton_count}",  # User/name
                        hp=skeleton_data['hp'],
                        max_hp=skeleton_data['hp'],  # Same as current HP
                        damage=skeleton_data['damage'],
                        armor=skeleton_data['armor'],
                        element=skeleton_data['element'],
                        luck=50,  # Base luck
                        is_pet=True,
                        name=f"Skeleton Warrior #{current_combatant.skeleton_count}"
                    )
                    skeleton.is_summoned = True
                    skeleton.summoner = current_combatant
                    
                    # Add skeleton to player team (tower battles use player_team and enemy_team)
                    if current_combatant in self.player_team.combatants:
                        self.player_team.combatants.append(skeleton)
                        message += f"\n💀 A skeleton warrior joins your side!"
                    else:
                        self.enemy_team.combatants.append(skeleton)
                        message += f"\n💀 A skeleton warrior joins the enemy side!"
                    
                    # Clear the summon flag
                    delattr(current_combatant, 'summon_skeleton')
            
            # Handle lifesteal if applicable
            if (self.config["class_buffs"] and 
                not current_combatant.is_pet and 
                current_combatant.lifesteal_percent > 0):
                
                lifesteal_amount = (float(damage) * float(current_combatant.lifesteal_percent) / 100.0)
                current_combatant.heal(lifesteal_amount)
                message += f" Lifesteals: **{self.format_number(lifesteal_amount)} HP**"
            
            # Handle damage reflection if applicable
            # Apply tank evolution reflection multiplier if applicable
            reflection_value = target.damage_reflection
            
            # Apply tank evolution-based reflection if target has tank evolution
            if self.config["class_buffs"] and target.tank_evolution and not target.is_pet:
                # Use the standard tank evolution reflection multiplier from classes.py
                tank_reflection = 0.03 * target.tank_evolution  # 3% per level, so 21% at level 7
                reflection_value = max(reflection_value, tank_reflection)  # Use higher of item reflection or tank reflection
            
            if (self.config["reflection_damage"] and 
                reflection_value > 0 and 
                blocked_damage > 0):
                
                # Calculate reflection as percentage of raw damage, capped at defender's armor
                reflection_base = min(raw_damage, target.armor)
                reflected = reflection_base * Decimal(str(reflection_value))
                current_combatant.take_damage(reflected)
                message += f"\n{target.name}'s armor reflects **{self.format_number(reflected)} HP** damage back!"
                
                if not current_combatant.is_alive():
                    message += f" {current_combatant.name} has been defeated by reflected damage!"
            
            # Check if target is defeated
            if not target.is_alive():
                # Check for water immortality first
                if getattr(target, 'water_immortality', False):
                    target.hp = Decimal('1')  # Stay at 1 HP
                    message += f"\n💧 {target.name} is protected by Immortal Waters and refuses to fall!"
                # Check for cheat death ability for players
                elif (self.config["class_buffs"] and 
                    self.config["cheat_death"] and
                    not target.is_pet and 
                    target in self.player_team.combatants and  # Only player can cheat death
                    target.death_cheat_chance > 0 and
                    not target.has_cheated_death):
                    
                    cheat_roll = random.randint(1, 100)
                    if cheat_roll <= target.death_cheat_chance:
                        target.hp = Decimal('75')
                        target.has_cheated_death = True
                        message += f"\n{target.name} cheats death and survives with **75 HP**!"
                    else:
                        message += f" {target.name} has been defeated!"
                else:
                    message += f" {target.name} has been defeated!"
                    
                    # If defeated enemy, check if we should move to next one
                    if target in self.enemy_team.combatants:
                        if target == self.enemy_team.combatants[self.current_opponent_index]:
                            # Schedule the transition to next enemy as a separate action
                            # (but don't increment the index here as that's done in handle_enemy_transition)
                            if self.current_opponent_index < len(self.enemy_team.combatants) - 1:
                                self.pending_enemy_transition = True
                                self.transition_state = 1  # Start at phase 1 (intro)
        else:
            # Attack misses or attacker trips (if enabled)
            if self.config.get("tripping", False):
                damage = Decimal('10')
                current_combatant.take_damage(damage)
                message = f"{current_combatant.name} tripped and took **{self.format_number(damage)} HP** damage. Bad luck!"
            else:
                message = f"{current_combatant.name}'s attack missed!"
        
        # Add message to battle log - use a new action number for each combat action
        await self.add_to_log(message, force_new_action=True)
        
        # PROCESS PET SKILL EFFECTS PER TURN
        if hasattr(self.ctx.bot.cogs["Battles"], "battle_factory"):
            pet_ext = self.ctx.bot.cogs["Battles"].battle_factory.pet_ext
            
            # Process player team pets
            for combatant in self.player_team.combatants:
                if combatant.is_pet and combatant.is_alive():
                    # Set team references for skills that need them
                    setattr(combatant, 'team', self.player_team)
                    setattr(combatant, 'enemy_team', self.enemy_team)
                    
                    # Process per-turn effects
                    turn_messages = pet_ext.process_skill_effects_per_turn(combatant)
                    if turn_messages:
                        for turn_msg in turn_messages:
                            await self.add_to_log(turn_msg)
            
            # Process enemy team pets (if any)
            for combatant in self.enemy_team.combatants:
                if combatant.is_pet and combatant.is_alive():
                    # Set team references for skills that need them
                    setattr(combatant, 'team', self.enemy_team)
                    setattr(combatant, 'enemy_team', self.player_team)
                    
                    # Process per-turn effects
                    turn_messages = pet_ext.process_skill_effects_per_turn(combatant)
                    if turn_messages:
                        for turn_msg in turn_messages:
                            await self.add_to_log(turn_msg)
        
        # Check for death from turn effects
        if hasattr(target, 'is_alive') and not target.is_alive():
            # Mark if pet killed an enemy for Soul Harvest
            if current_combatant.is_pet:
                setattr(current_combatant, 'killed_enemy_this_turn', True)
        
        # Update the battle display
        await self.update_display()
        await asyncio.sleep(1)
        
        return True
    
    async def create_battle_embed(self):
        """Create the battle status embed"""
        current_enemy = self.enemy_team.combatants[self.current_opponent_index]
        embed = discord.Embed(
            title=f"Battle Tower: Level {self.level} - {self.ctx.author.display_name} vs {current_enemy.name}",
            color=self.ctx.bot.config.game.primary_colour
        )
        
        # Get element emoji mapping
        element_emoji_map = {}
        if hasattr(self.ctx.bot.cogs["Battles"], "emoji_to_element"):
            element_emoji_map = self.ctx.bot.cogs["Battles"].emoji_to_element
            
        # Add player team info
        for combatant in self.player_team.combatants:
            current_hp = max(0, float(combatant.hp))
            max_hp = float(combatant.max_hp)
            hp_bar = self.create_hp_bar(current_hp, max_hp)
            
            # Get element emoji
            element_emoji = "❌"
            for emoji, element in element_emoji_map.items():
                if element == combatant.element:
                    element_emoji = emoji
                    break
            
            # Set field name based on type
            if combatant.is_pet:
                field_name = f"{combatant.name} {element_emoji}"
            else:
                field_name = f"**[TEAM A]** \n{combatant.display_name} {element_emoji}"
                
            # Create field value with HP bar
            field_value = f"HP: {current_hp:.1f}/{max_hp:.1f}\n{hp_bar}"
            
            # Add reflection info if applicable
            if combatant.damage_reflection > 0:
                reflection_percent = float(combatant.damage_reflection) * 100
                field_value += f"\nDamage Reflection: {reflection_percent:.1f}%"
                
            embed.add_field(name=field_name, value=field_value, inline=False)
        
        # Add current enemy info
        current_hp = max(0, float(current_enemy.hp))
        max_hp = float(current_enemy.max_hp)
        hp_bar = self.create_hp_bar(current_hp, max_hp)
        
        # Get element emoji
        element_emoji = "❌"
        for emoji, element in element_emoji_map.items():
            if element == current_enemy.element:
                element_emoji = emoji
                break
        
        field_name = f"**[TEAM B]** \n{current_enemy.name} {element_emoji}"
        field_value = f"HP: {current_hp:.1f}/{max_hp:.1f}\n{hp_bar}"
        embed.add_field(name=field_name, value=field_value, inline=False)
        
        # Add battle log
        log_text = "\n\n".join([f"**Action #{i}**\n{msg}" for i, msg in self.log])
        embed.add_field(name="Battle Log", value=log_text or "Battle starting...", inline=False)
        
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
        
        # Check victory/defeat conditions BEFORE timeout
        # This ensures that if enemies are defeated on the last turn before timeout, it's still a victory
        
        # Check if the player character (non-pet) is defeated when pets_continue_battle is false
        player_char_defeated = not any(not c.is_pet and c.is_alive() for c in self.player_team.combatants)
        if player_char_defeated and not self.config.get("pets_continue_battle", False):
            # Player lost if character is dead and pets can't continue
            # Save final battle state to database for replay
            await self.save_battle_to_database()
            return self.enemy_team
        
        # Check if player team is completely defeated
        if self.player_team.is_defeated():
            # Player lost - return the enemy team as winner
            # Save final battle state to database for replay
            await self.save_battle_to_database()
            return self.enemy_team
        
        # Check if all enemies are defeated (VICTORY)
        if all(not enemy.is_alive() for enemy in self.enemy_team.combatants):
            # Player only wins if the character is still alive or pets_continue_battle is true
            if not player_char_defeated or self.config.get("pets_continue_battle", False):
                # Save final battle state to database for replay
                await self.save_battle_to_database()
                return self.player_team
            else:
                # Both player and enemies are defeated - draw or enemy wins
                # Save final battle state to database for replay
                await self.save_battle_to_database()
                return self.enemy_team
        
        # Only check timeout AFTER victory/defeat conditions
        # This prevents timeout from overriding a legitimate victory/defeat
        if await self.is_timed_out():
            # Special case for timeout
            self.battle_timed_out = True
            # Save final battle state to database for replay
            await self.save_battle_to_database()
            return None
        
        # Compare remaining HP percentages - only if player character still alive or pets can continue
        if not player_char_defeated or self.config.get("pets_continue_battle", False):
            player_health_percent = sum(c.hp / c.max_hp for c in self.player_team.combatants) / len(self.player_team.combatants)
            enemy_health_percent = sum(c.hp / c.max_hp for c in self.enemy_team.combatants) / len(self.enemy_team.combatants)
            
            if player_health_percent > enemy_health_percent:
                # Save final battle state to database for replay
                await self.save_battle_to_database()
                return self.player_team
        
        # Default to enemy win if no other condition is met
        # Save final battle state to database for replay
        await self.save_battle_to_database()
        return self.enemy_team
    
    async def is_battle_over(self):
        """Check if the battle is over"""
        # If we're in a transition between enemies, battle is not over
        if self.pending_enemy_transition:
            return False
            
        if self.finished:
            return True
        
        # Check victory/defeat conditions BEFORE timeout
        # This ensures that if enemies are defeated on the last turn before timeout, it's still a victory
        
        # Check if all enemies are defeated (VICTORY)
        enemy_defeated = all(not c.is_alive() for c in self.enemy_team.combatants)
        if enemy_defeated:
            return True
            
        # Check if player team is defeated based on settings (DEFEAT)
        player_char_defeated = not any(not c.is_pet and c.is_alive() for c in self.player_team.combatants)
        
        # If player character is defeated but pets should continue battle
        if player_char_defeated:
            # Check if pets_continue_battle is enabled
            if self.config.get("pets_continue_battle", False) and self.config.get("allow_pets", True):
                # Only end battle if all pets are also defeated
                all_defeated = all(not c.is_alive() for c in self.player_team.combatants)
                if all_defeated:
                    return True
            else:
                # Default behavior: end battle if player character is defeated
                return True
        
        # Only check timeout AFTER victory/defeat conditions
        # This prevents timeout from overriding a legitimate victory/defeat
        if await self.is_timed_out():
            self.battle_timed_out = True
            return True
                
        return False
# battles/types/raid.py
import asyncio
import random
from decimal import Decimal
import discord
import datetime

from ..core.battle import Battle

class RaidBattle(Battle):
    """Battle with player and pets vs an enemy and their pets"""
    
    def __init__(self, ctx, teams, **kwargs):
        super().__init__(ctx, teams, **kwargs)
        self.money = kwargs.get("money", 0)
        self.current_turn = 0
        self.turn_order = []
        
        # Load all battle settings
        settings_cog = self.ctx.bot.get_cog("BattleSettings")
        hp_bar_style = kwargs.get(
            "hp_bar_style",
            "colorful" if kwargs.get("emoji_hp_bars", False) else "normal",
        )
        normalized_hp_bar_style = self.normalize_hp_bar_style(hp_bar_style)
        if settings_cog:
            # Ensure all settings are loaded, with defaults if not found
            self.config = {
                "allow_pets": settings_cog.get_setting("raid", "allow_pets", default=True),
                "class_buffs": settings_cog.get_setting("raid", "class_buffs", default=True),
                "element_effects": settings_cog.get_setting("raid", "element_effects", default=True),
                "luck_effects": settings_cog.get_setting("raid", "luck_effects", default=True),
                "reflection_damage": settings_cog.get_setting("raid", "reflection_damage", default=True),
                "hp_bar_style": normalized_hp_bar_style,
                "emoji_hp_bars": normalized_hp_bar_style != self.HP_BAR_STYLE_NORMAL,
                "fireball_chance": settings_cog.get_setting("raid", "fireball_chance", default=0.3),
                "cheat_death": settings_cog.get_setting("raid", "cheat_death", default=True),
                "tripping": settings_cog.get_setting("raid", "tripping", default=True),
                "status_effects": settings_cog.get_setting("raid", "status_effects", default=False),
                "pets_continue_battle": settings_cog.get_setting("raid", "pets_continue_battle", default=False)
            }
        else:
            # Fallback default settings if settings cog is unavailable
            self.config = {
                "allow_pets": True,
                "class_buffs": True,
                "element_effects": True,
                "luck_effects": True,
                "reflection_damage": True,
                "hp_bar_style": normalized_hp_bar_style,
                "emoji_hp_bars": normalized_hp_bar_style != self.HP_BAR_STYLE_NORMAL,
                "fireball_chance": 0.3,
                "cheat_death": True,
                "tripping": True,
                "status_effects": False,
                "pets_continue_battle": False
            }
        
    async def start_battle(self):
        """Initialize and start the battle"""
        self.started = True
        self.start_time = datetime.datetime.utcnow()
        
        # Save initial battle data to database for replay
        await self.save_battle_to_database()
        
        # Create team lists for easier access
        self.team_a = self.teams[0]
        self.team_b = self.teams[1]
        
        # Build turn order with all combatants
        self.turn_order = []
        for team in self.teams:
            for combatant in team.combatants:
                self.turn_order.append(combatant)
        
        # Shuffle turn order randomly
        random.shuffle(self.turn_order)
        self.turn_order = self.prioritize_turn_order(self.turn_order)

        # Create battle log
        await self.add_to_log(f"Raidbattle started between Team A and Team B!")
        for opening_message in await self.trigger_ascension_openings():
            await self.add_to_log(opening_message)
        

        # Create and send initial embed
        embed = await self.create_battle_embed()
        self.battle_message = await self.publish_battle_message(embed=embed)
        
        # Add a pause after battle start before first attack
        await asyncio.sleep(1)
        
        return True
    
    async def process_turn(self):
        """Process a single turn of the battle"""
        if await self.is_battle_over():
            return False
        
        # Find the next alive combatant efficiently
        turns_checked = 0
        max_turns = len(self.turn_order) * 2  # Avoid infinite loop
        
        while turns_checked < max_turns:
            # Get current combatant
            current_combatant = self.turn_order[self.current_turn % len(self.turn_order)]
            self.current_turn += 1
            turns_checked += 1
            
            # Skip dead combatants and continue to the next one
            if not current_combatant.is_alive():
                continue
                
            # Found an alive combatant, break the loop
            break
            
        # If we've checked all combatants and none are alive, end the battle
        if turns_checked >= max_turns:
            return False

        silenced_message = self.consume_ascension_action_lock(current_combatant)
        if silenced_message:
            await self.add_to_log(silenced_message)
            await self.update_display()
            await asyncio.sleep(1)
            return True

        locked_message = self.consume_pet_skill_action_lock(current_combatant)
        if locked_message:
            await self.add_to_log(locked_message)
            await self.update_display()
            await asyncio.sleep(1)
            return True
            
        # Determine which team the combatant belongs to
        combatant_team = self.team_a if current_combatant in self.team_a.combatants else self.team_b
        enemy_team = self.team_b if combatant_team == self.team_a else self.team_a
        
        # Get alive enemies
        alive_enemies = enemy_team.get_alive_combatants()
        if not alive_enemies:
            return False
        
        # Select target
        if current_combatant.is_pet:
            # Pets have slightly different targeting - more likely to target other pets
            pet_targets = [c for c in alive_enemies if c.is_pet]
            player_targets = [c for c in alive_enemies if not c.is_pet]
            
            if pet_targets and player_targets:
                # If both exist, randomly choose with bias
                if random.random() < 0.6:  # 60% chance to target players
                    target = random.choice(player_targets)
                else:
                    target = random.choice(pet_targets)
            else:
                # Otherwise use whatever we have
                target = random.choice(alive_enemies)
        else:
            # Players target weighted by probability
            weighted_targets = []
            weights = []
            
            for enemy in alive_enemies:
                if enemy.is_pet:
                    weighted_targets.append(enemy)
                    weights.append(0.4)  # 40% chance to target pets
                else:
                    weighted_targets.append(enemy)
                    weights.append(0.6)  # 60% chance to target players
            
            # Normalize weights
            total_weight = sum(weights)
            weights = [w/total_weight for w in weights]
            
            target = random.choices(weighted_targets, weights=weights)[0]
        
        # Process attack based on luck
        luck_roll = random.randint(1, 100)
        
        # Check for perfect accuracy from Night Vision skill
        has_perfect_accuracy = getattr(current_combatant, 'perfect_accuracy', False)
        hit_success = has_perfect_accuracy or (luck_roll <= current_combatant.luck)
        
        guard_source = None

        if hit_success:
            # Attack hits
            blocked_damage = Decimal("0")
            ignore_reflection_this_hit = False
            
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
                    7: 2.10,  # 210%
                }.get(evolution_level, 1.0)
                
                damage = (current_combatant.damage + Decimal(random.randint(0, 100)) - target.armor) * Decimal(str(damage_multiplier))
                damage = max(damage, Decimal('10'))

                damage, guard_messages, guard_source = self.apply_pet_owner_guard(
                    current_combatant,
                    target,
                    damage,
                )
                target.take_damage(damage)
                message = f"{current_combatant.name} casts Fireball! {target.name} takes **{self.format_number(damage)} HP** damage."
                if guard_messages:
                    message += "\n" + "\n".join(guard_messages)
                used_fireball = True
            else:
                # Regular attack
                damage_variance = random.randint(0, 50) if current_combatant.is_pet else random.randint(0, 100)
                
                # Start with base damage
                raw_damage = current_combatant.damage

                outcome = self.resolve_pet_attack_outcome(
                    current_combatant,
                    target,
                    raw_damage,
                    apply_element_mod=self.config["element_effects"],
                    damage_variance=damage_variance,
                    minimum_damage=Decimal("10"),
                )
                damage = outcome.final_damage
                blocked_damage = outcome.blocked_damage
                skill_messages = outcome.skill_messages
                defender_messages = outcome.defender_messages
                ignore_reflection_this_hit = bool(outcome.metadata.get("ignore_reflection_this_hit", False))

                damage, guard_messages, guard_source = self.apply_pet_owner_guard(
                    current_combatant,
                    target,
                    damage,
                )
                target.take_damage(damage)
                message = f"{current_combatant.name} attacks! {target.name} takes **{self.format_number(damage)} HP** damage."
                if guard_messages:
                    message += "\n" + "\n".join(guard_messages)
                
                # Add skill effect messages
                if skill_messages:
                    message += "\n" + "\n".join(skill_messages)
                if defender_messages:
                    message += "\n" + "\n".join(defender_messages)
                    
                # Check for skeleton summoning after skill processing
                queued_summons = getattr(current_combatant, 'summon_skeleton_queue', None)
                if not queued_summons and hasattr(current_combatant, 'summon_skeleton'):
                    queued_summons = [current_combatant.summon_skeleton]
                if queued_summons:
                    from cogs.battles.core.combatant import Combatant

                    for skeleton_data in list(queued_summons):
                        skeleton_serial = skeleton_data.get(
                            'serial',
                            getattr(current_combatant, 'skeleton_count', 1),
                        )
                        skeleton = Combatant(
                            user=f"Skeleton Warrior #{skeleton_serial}",
                            hp=skeleton_data['hp'],
                            max_hp=skeleton_data['hp'],
                            damage=skeleton_data['damage'],
                            armor=skeleton_data['armor'],
                            element=skeleton_data['element'],
                            luck=50,
                            is_pet=True,
                            name=f"Skeleton Warrior #{skeleton_serial}"
                        )
                        skeleton.is_summoned = True
                        skeleton.summoner = current_combatant

                        if current_combatant in self.team_a.combatants:
                            self.team_a.combatants.append(skeleton)
                            self.turn_order.append(skeleton)
                            self.turn_order = self.prioritize_turn_order(self.turn_order)
                            message += f"\n💀 Skeleton Warrior #{skeleton_serial} joins Team A!"
                        else:
                            self.team_b.combatants.append(skeleton)
                            self.turn_order.append(skeleton)
                            self.turn_order = self.prioritize_turn_order(self.turn_order)
                            message += f"\n💀 Skeleton Warrior #{skeleton_serial} joins Team B!"

                    if hasattr(current_combatant, 'summon_skeleton_queue'):
                        delattr(current_combatant, 'summon_skeleton_queue')
                    if hasattr(current_combatant, 'summon_skeleton'):
                        delattr(current_combatant, 'summon_skeleton')

            grave_message = await self.maybe_trigger_grave_sovereign(
                current_combatant,
                target,
            )
            if grave_message:
                message += "\n" + grave_message

            cycle_message = await self.maybe_trigger_cyclebreaker(
                target,
                current_combatant,
            )
            if cycle_message:
                message += "\n" + cycle_message
            
            # Handle lifesteal if applicable
            if (self.config["class_buffs"] and 
                not current_combatant.is_pet and 
                current_combatant.lifesteal_percent > 0):
                
                lifesteal_amount = (float(damage) * float(current_combatant.lifesteal_percent) / 100.0)
                current_combatant.heal(lifesteal_amount)
                message += f" Lifesteals: **{self.format_number(lifesteal_amount)} HP**"

            bonus_lifesteal = self.apply_bonus_lifesteal(current_combatant, damage)
            if bonus_lifesteal > 0:
                message += (
                    f"\n{current_combatant.name} siphons **{self.format_number(bonus_lifesteal)} HP** "
                    "from bonus lifesteal!"
                )
            
            # Handle damage reflection if applicable
            # Apply tank evolution reflection multiplier if applicable
            reflection_value = target.damage_reflection
            
            # Apply tank evolution-based reflection if target has tank evolution
            if self.config["class_buffs"] and target.tank_evolution and not target.is_pet:
                # Tank evolution reflection multiplier
                evolution_reflection_multiplier = {
                    1: 0.04,  # 4%
                    2: 0.08,  # 8%
                    3: 0.12,  # 12%
                    4: 0.16,  # 16%
                    5: 0.20,  # 20%
                    6: 0.24,  # 24%
                    7: 0.28,  # 28%
                }
                
                # Get reflection multiplier based on evolution level
                tank_reflection = evolution_reflection_multiplier.get(target.tank_evolution, 0)
                reflection_value = max(reflection_value, tank_reflection)  # Use higher of item reflection or tank reflection
            

            
            if (self.config["reflection_damage"] and 
                reflection_value > 0 and 
                blocked_damage > 0 and
                not ignore_reflection_this_hit):
                
                reflected = blocked_damage * Decimal(str(reflection_value))
                current_combatant.take_damage(reflected)
                message += f"\n{target.name}'s armor reflects **{self.format_number(reflected)} HP** damage back!"
                
                if not current_combatant.is_alive():
                    message += f" {current_combatant.name} has been defeated by reflected damage!"
            
            # Check if target is defeated
            if not target.is_alive():
                guardian_message = self.maybe_trigger_guardian_angel(target)
                if guardian_message:
                    message += f"\n{guardian_message}"
                # Check for cheat death ability
                if target.is_alive():
                    pass
                elif (self.config["class_buffs"] and 
                    self.config["cheat_death"] and
                    not target.is_pet and 
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
        else:
            # Attack misses or attacker trips (if enabled)
            if self.config.get("tripping", False):
                damage = Decimal('10')
                current_combatant.take_damage(damage)
                message = f"{current_combatant.name} tripped and took **{self.format_number(damage)} HP** damage. Bad luck!"
            else:
                message = f"{current_combatant.name}'s attack missed!"
        
        # Add message to battle log
        await self.add_to_log(message)

        if current_combatant.is_pet and not target.is_alive():
            setattr(current_combatant, 'killed_enemy_this_turn', True)

        for combatant in (target, current_combatant, guard_source):
            if combatant is None or not getattr(combatant, "is_pet", False) or combatant.is_alive():
                continue
            for death_msg in self.process_pet_death_effects(combatant):
                await self.add_to_log(death_msg)

        if current_combatant.is_pet and current_combatant.is_alive():
            for turn_msg in self.process_pet_turn_effects(current_combatant):
                await self.add_to_log(turn_msg)
        
        # Update the battle display
        await self.update_display()
        await asyncio.sleep(1)
        
        return True
    
    async def create_battle_embed(self):
        """Create the battle status embed"""
        embed = discord.Embed(
            title=f"Raid Battle",
            color=self.ctx.bot.config.game.primary_colour
        )
        
        # Get element emoji mapping
        element_emoji_map = {}
        if hasattr(self.ctx.bot.cogs["Battles"], "emoji_to_element"):
            element_emoji_map = self.ctx.bot.cogs["Battles"].emoji_to_element
            
        # Add team A info
        for combatant in self.team_a.combatants:
            current_hp = max(0, float(combatant.hp))
            max_hp = float(combatant.max_hp)
            hp_bar = self.create_hp_bar(current_hp, max_hp, combatant=combatant)
            
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
                field_name = f"[TEAM A]\n{combatant.display_name} {element_emoji}"
                
            # Create field value with HP bar
            field_value = f"HP: {current_hp:.1f}/{max_hp:.1f}\n{hp_bar}"
            
            # Add reflection info if applicable
            if combatant.damage_reflection > 0:
                reflection_percent = float(combatant.damage_reflection) * 100
                field_value += f"\nDamage Reflection: {reflection_percent:.1f}%"
                
            embed.add_field(name=field_name, value=field_value, inline=False)
        
        # Add team B info
        for combatant in self.team_b.combatants:
            current_hp = max(0, float(combatant.hp))
            max_hp = float(combatant.max_hp)
            hp_bar = self.create_hp_bar(current_hp, max_hp, combatant=combatant)
            
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
                field_name = f"[TEAM B]\n{combatant.display_name} {element_emoji}"
                
            # Create field value with HP bar
            field_value = f"HP: {current_hp:.1f}/{max_hp:.1f}\n{hp_bar}"
            
            # Add reflection info if applicable
            if combatant.damage_reflection > 0:
                reflection_percent = float(combatant.damage_reflection) * 100
                field_value += f"\nDamage Reflection: {reflection_percent:.1f}%"
                
            embed.add_field(name=field_name, value=field_value, inline=False)
        
        # Add battle log
        log_text = "\n\n".join([f"**Action #{i}**\n{msg}" for i, msg in self.log])
        embed.add_field(name="Battle Log", value=log_text or "Battle starting...", inline=False)
        
        # Add battle ID to footer for GM replay functionality
        embed.set_footer(text=f"Battle ID: {self.battle_id}")
        
        return embed
    
    async def update_display(self):
        """Update the battle display"""
        # Update after every action for better visibility
        embed = await self.create_battle_embed()
        await self.publish_battle_message(embed=embed)
    
    async def end_battle(self):
        """End the battle and determine rewards"""
        self.finished = True
        
        # Save final battle data to database for replay
        await self.save_battle_to_database()
        
        # Check if it's a timeout/tie
        if await self.is_timed_out():
            # It's a tie, refund money
            if self.money > 0:
                # Get IDs of all players (not pets)
                player_ids = []
                for team in self.teams:
                    for combatant in team.combatants:
                        if not combatant.is_pet and hasattr(combatant.user, "id"):
                            player_ids.append(combatant.user.id)
                
                # Refund money to all players
                async with self.ctx.bot.pool.acquire() as conn:
                    for player_id in player_ids:
                        await conn.execute(
                            'UPDATE profile SET "money"="money"+$1 WHERE "user"=$2;',
                            self.money,
                            player_id
                        )
            
            return None
        
        # Determine winner
        team_a_defeated = self.team_a.is_defeated()
        team_b_defeated = self.team_b.is_defeated()
        
        if team_a_defeated and not team_b_defeated:
            winning_team = self.team_b
            losing_team = self.team_a
        elif team_b_defeated and not team_a_defeated:
            winning_team = self.team_a
            losing_team = self.team_b
        else:
            # Compare remaining HP percentages
            team_a_health = sum(c.hp / c.max_hp for c in self.team_a.combatants if not c.is_pet)
            team_b_health = sum(c.hp / c.max_hp for c in self.team_b.combatants if not c.is_pet)
            
            if team_a_health > team_b_health:
                winning_team = self.team_a
                losing_team = self.team_b
            else:
                winning_team = self.team_b
                losing_team = self.team_a
        
        # Get the first non-pet combatant from each team to use as winner/loser
        # Initialize winner and loser variables first to avoid UnboundLocalError
        winner = None
        loser = None
        
        # Try to find a valid user in winning team
        for combatant in winning_team.combatants:
            if not combatant.is_pet and hasattr(combatant, "user") and hasattr(combatant.user, "id"):
                winner = combatant.user
                break
                
        # Try to find a valid user in losing team
        for combatant in losing_team.combatants:
            if not combatant.is_pet and hasattr(combatant, "user") and hasattr(combatant.user, "id"):
                loser = combatant.user
                break
        
        # Handle rewards
        if winner and loser:
            # Award PvP wins to winners (regardless of money)
            winner_ids = [c.user.id for c in winning_team.combatants if not c.is_pet and hasattr(c.user, "id")]
            
            # Skip rewards if no valid winners
            if winner_ids:
                async with self.ctx.bot.pool.acquire() as conn:
                    # Award PvP wins to all winners
                    for winner_id in winner_ids:
                        await conn.execute(
                            'UPDATE profile SET "pvpwins"="pvpwins"+1 WHERE "user"=$1;',
                            winner_id,
                        )
                    
                    # Handle money rewards if there's money involved
                    if self.money > 0:
                        for winner_id in winner_ids:
                            await conn.execute(
                                'UPDATE profile SET "money"="money"+$1 WHERE "user"=$2;',
                                self.money * 2 / len(winner_ids),  # Split the money among winners
                                winner_id,
                            )
                        
                        # Log the transaction for first player only (for simplicity)
                        await self.ctx.bot.log_transaction(
                            self.ctx,
                            from_=loser.id,
                            to=winner.id,
                            subject="RaidBattle Bet",
                            data={"Gold": self.money},
                            conn=conn,
                        )
        
        return winner, loser
    
    async def is_battle_over(self):
        """Check if the battle is over"""
        # If the battle is explicitly marked as finished or timed out, it's over
        if self.finished or await self.is_timed_out():
            return True
            
        # Check team B (normally enemy team)
        if self.team_b.is_defeated():
            return True
            
        # Check team A (normally player team) with pet continuation settings
        # First, check if all player (non-pet) characters in team A are defeated
        player_chars_defeated = not any(not c.is_pet and c.is_alive() for c in self.team_a.combatants)
        
        if player_chars_defeated:
            # If pets should continue battling after player defeat
            if self.config.get("pets_continue_battle", False) and self.config.get("allow_pets", True):
                # Only end battle if all combatants (including pets) are defeated
                return all(not c.is_alive() for c in self.team_a.combatants)
            else:
                # Default behavior: end battle if all player characters are defeated
                return True
                
        # Otherwise battle continues
        return False


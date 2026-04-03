# battles/types/team_battle.py
import asyncio
import random
from decimal import Decimal
import discord
import datetime

from ..core.battle import Battle

class TeamBattle(Battle):
    """Team vs Team battle implementation"""
    
    def __init__(self, ctx, teams, **kwargs):
        super().__init__(ctx, teams, **kwargs)
        self.money = kwargs.get("money", 0)
        self.current_turn = 0
        self.turn_order = []
        
        # Set team names
        self.teams[0].name = "A"
        self.teams[1].name = "B"
        
    async def start_battle(self):
        """Initialize and start the battle"""
        self.started = True
        self.start_time = datetime.datetime.utcnow()
        
        # Save initial battle data to database for replay
        await self.save_battle_to_database()
        
        # Build turn order with all combatants
        self.turn_order = []
        for team in self.teams:
            for combatant in team.combatants:
                self.turn_order.append(combatant)
                
        # Shuffle turn order randomly
        random.shuffle(self.turn_order)
        self.turn_order = self.prioritize_turn_order(self.turn_order)
        
        # Add battle start message to log
        team_a_members = ", ".join(c.name for c in self.teams[0].combatants)
        team_b_members = ", ".join(c.name for c in self.teams[1].combatants)
        await self.add_to_log(f"Team Battle: Team A ({team_a_members}) vs Team B ({team_b_members}) started!")
        for opening_message in await self.trigger_ascension_openings():
            await self.add_to_log(opening_message)
        
        # Create and send initial embed
        embed = await self.create_battle_embed()
        self.battle_message = await self.publish_battle_message(embed=embed)
        
        return True
    
    async def process_turn(self):
        """Process a single turn of the battle"""
        if await self.is_battle_over():
            return False
            
        # Find the next alive combatant, skipping dead ones
        turns_checked = 0
        max_turns = len(self.turn_order) * 2  # Avoid infinite loop by setting a maximum
        
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
        current_team = None
        for team in self.teams:
            if current_combatant in team.combatants:
                current_team = team
                break
                
        # Get enemy team
        enemy_team = self.teams[1] if current_team == self.teams[0] else self.teams[0]
        
        # Check if there are any alive enemies
        alive_enemies = enemy_team.get_alive_combatants()
        if not alive_enemies:
            return False
            
        # Select target using weighted probabilities
        target = self.select_target(alive_enemies)
        
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
            mage_charge_state = self.advance_mage_fireball_charge(current_combatant)
            
            used_fireball = False
            if mage_charge_state and mage_charge_state["fireball_ready"]:
                damage = self.calculate_mage_fireball_damage(
                    current_combatant,
                    target,
                    damage_variance=100,
                    minimum_damage=Decimal("10"),
                )
                ignore_reflection_this_hit = True

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

                charge_message = self.format_mage_charge_message(mage_charge_state)
                if charge_message:
                    message += "\n" + charge_message

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
                            luck=skeleton_data.get('luck', 50),
                            is_pet=True,
                            name=f"Skeleton Warrior #{skeleton_serial}"
                        )
                        skeleton.is_summoned = True

                        if current_combatant in self.team_a.combatants:
                            self.register_summoned_combatant(
                                skeleton,
                                team=self.team_a,
                                summoner=current_combatant,
                            )
                            self.team_a.combatants.append(skeleton)
                            self.turn_order.append(skeleton)
                            self.turn_order = self.prioritize_turn_order(self.turn_order)
                            message += f"\n💀 Skeleton Warrior #{skeleton_serial} joins Team A!"
                        else:
                            self.register_summoned_combatant(
                                skeleton,
                                team=self.team_b,
                                summoner=current_combatant,
                            )
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

            class_messages = self.resolve_post_hit_class_effects(current_combatant, target)
            if class_messages:
                message += "\n" + "\n".join(class_messages)
            
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
                        target.hp = self.get_cheat_death_recovery_hp(target)
                        target.has_cheated_death = True
                        message += (
                            f"\n{target.name} cheats death and survives with "
                            f"**{self.format_number(target.hp)} HP**!"
                        )
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
    
    def select_target(self, targets):
        """Select a target for attack using weighted probabilities
        
        This improved version now prioritizes targets with lower HP when possible
        to make targeting more intuitive and predictable.
        """
        if not targets:
            return None
            
        # If there's only one target, return it
        if len(targets) == 1:
            return targets[0]
            
        # Prioritize targets with lower HP (75% chance)
        # This makes targeting more consistent and intuitive
        if random.random() < 0.75:
            # Sort targets by HP (ascending)
            sorted_targets = sorted(targets, key=lambda x: x.hp)
            # Return the one with lowest HP
            return sorted_targets[0]
        else:
            # Sometimes select random target (25% chance) for variety
            return random.choice(targets)
    
    async def create_battle_embed(self):
        """Create the battle status embed"""
        embed = discord.Embed(
            title=f"Team Battle",
            color=self.ctx.bot.config.game.primary_colour
        )
        
        # Get element emoji mapping
        element_emoji_map = {}
        if hasattr(self.ctx.bot.cogs["Battles"], "emoji_to_element"):
            element_emoji_map = self.ctx.bot.cogs["Battles"].emoji_to_element
            
        # Add team info for both teams
        for team_idx, team in enumerate(self.teams):
            team_letter = team.name
            
            for combatant in team.combatants:
                current_hp = max(0, float(combatant.hp))
                max_hp = float(combatant.max_hp)
                hp_bar = self.create_hp_bar(current_hp, max_hp, combatant=combatant)
                
                # Get element emoji
                element_emoji = "❌"
                for emoji, element in element_emoji_map.items():
                    if element == combatant.element:
                        element_emoji = emoji
                        break
                
                field_name = f"{combatant.display_name} [Team {team_letter}] {element_emoji}"
                field_value = f"HP: {current_hp:.1f}/{max_hp:.1f}\n{hp_bar}"
                if hasattr(combatant, "shield") and Decimal(str(combatant.shield)) > 0:
                    field_value += f"\nShield: {self.format_number(combatant.shield)}"
                
                # Add reflection info if applicable
                if combatant.damage_reflection > 0:
                    reflection_percent = float(combatant.damage_reflection) * 100
                    field_value += f"\nDamage Reflection: {reflection_percent:.1f}%"
                    
                embed.add_field(name=field_name, value=field_value, inline=False)
        
        # Add battle log
        log_text = self.format_battle_log_field()
        embed.add_field(name="Battle Log", value=log_text, inline=False)
        
        # Add battle ID to footer for GM replay functionality
        embed.set_footer(text=f"Battle ID: {self.battle_id}")
        
        return embed
    
    async def update_display(self):
        """Update the battle display"""
        embed = await self.create_battle_embed()
        await self.publish_battle_message(embed=embed)
    
    async def end_battle(self):
        """End the battle and determine rewards"""
        self.finished = True
        
        # Check if it's a timeout/tie
        if await self.is_timed_out():
            # It's a tie, refund money
            if self.money > 0:
                # Get all player IDs
                player_ids = []
                for team in self.teams:
                    for combatant in team.combatants:
                        if hasattr(combatant.user, "id") and not combatant.is_pet:
                            player_ids.append(combatant.user.id)
                
                # Refund money to all players with proper verification
                async with self.ctx.bot.pool.acquire() as conn:
                    for player_id in player_ids:
                        # Verify this player paid for the battle
                        payment_verification = await conn.fetchval(
                            'SELECT EXISTS(SELECT 1 FROM transaction WHERE "from"=$1 AND "subject"=$2 AND "data"::json->>$3 = $4 AND "timestamp" > NOW() - INTERVAL \'1 hour\');',
                            player_id,
                            "Team Battle Entry",
                            "Gold",
                            str(self.money)
                        )
                        
                        if payment_verification:
                            await conn.execute(
                                'UPDATE profile SET "money"="money"+$1 WHERE "user"=$2;',
                                self.money,
                                player_id
                            )
                            
                            # Log the refund transaction
                            await self.ctx.bot.log_transaction(
                                self.ctx,
                                from_=0,  # System refund
                                to=player_id,
                                subject="Team Battle Refund",
                                data={"Gold": self.money},
                                conn=conn
                            )
            
            return None
        
        # Determine winning team
        if self.teams[0].is_defeated():
            winning_team = self.teams[1]
            losing_team = self.teams[0]
        elif self.teams[1].is_defeated():
            winning_team = self.teams[0]
            losing_team = self.teams[1]
        else:
            # Compare HP percentages
            team_a_health_percent = sum(c.hp / c.max_hp for c in self.teams[0].combatants) / len(self.teams[0].combatants)
            team_b_health_percent = sum(c.hp / c.max_hp for c in self.teams[1].combatants) / len(self.teams[1].combatants)
            
            if team_a_health_percent > team_b_health_percent:
                winning_team = self.teams[0]
                losing_team = self.teams[1]
            else:
                winning_team = self.teams[1]
                losing_team = self.teams[0]
        
        # Collect valid winner and loser IDs (only including real players, not pets)
        winner_ids = []
        loser_ids = []
        
        for combatant in winning_team.combatants:
            if hasattr(combatant.user, "id") and not combatant.is_pet:
                winner_ids.append(combatant.user.id)
        
        for combatant in losing_team.combatants:
            if hasattr(combatant.user, "id") and not combatant.is_pet:
                loser_ids.append(combatant.user.id)
        
        # Award PvP wins to winners (regardless of money)
        if winner_ids:
            async with self.ctx.bot.pool.acquire() as conn:
                for winner_id in winner_ids:
                    await conn.execute(
                        'UPDATE profile SET "pvpwins"="pvpwins"+1 WHERE "user"=$1;',
                        winner_id
                    )
        
        # Handle money rewards if there's money involved
        if self.money > 0:
            total_winners = len(winner_ids) or 1  # Avoid division by zero
            total_losers = len(loser_ids) or 1    # Avoid division by zero
            
            # Only count verified payments from losers
            verified_payments = 0
            
            async with self.ctx.bot.pool.acquire() as conn:
                # First verify all losers actually paid
                for loser_id in loser_ids:
                    # Check if this player actually paid the entry fee
                    payment_verification = await conn.fetchval(
                        'SELECT EXISTS(SELECT 1 FROM transaction WHERE "from"=$1 AND "subject"=$2 AND "data"::json->>$3 = $4 AND "timestamp" > NOW() - INTERVAL \'1 hour\');',
                        loser_id,
                        "Team Battle Entry",
                        "Gold",
                        str(self.money)
                    )
                    
                    if payment_verification:
                        verified_payments += 1
                
                # Calculate individual winnings based on verified payments
                if verified_payments > 0:
                    individual_winnings = (self.money * 2 * verified_payments) / total_winners
                    
                    # Award money to winners with proper logging
                    for winner_id in winner_ids:
                        await conn.execute(
                            'UPDATE profile SET "money"="money"+$1 WHERE "user"=$2;',
                            individual_winnings,
                            winner_id
                        )
                        
                        # Log the winning transaction
                        await self.ctx.bot.log_transaction(
                            self.ctx,
                            from_=0,  # System award
                            to=winner_id,
                            subject="Team Battle Win",
                            data={"Gold": individual_winnings},
                            conn=conn
                        )
        
        return winning_team.name, losing_team.name
    
    async def is_battle_over(self):
        """Check if the battle is over"""
        # Battle is over if one team is completely defeated
        return (self.teams[0].is_defeated() or 
                self.teams[1].is_defeated() or 
                await self.is_timed_out() or 
                self.finished)


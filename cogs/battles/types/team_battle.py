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
        
        # Add battle start message to log
        team_a_members = ", ".join(c.name for c in self.teams[0].combatants)
        team_b_members = ", ".join(c.name for c in self.teams[1].combatants)
        await self.add_to_log(f"Team Battle: Team A ({team_a_members}) vs Team B ({team_b_members}) started!")
        
        # Create and send initial embed
        embed = await self.create_battle_embed()
        self.battle_message = await self.ctx.send(embed=embed)
        
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
                damage = max(damage, Decimal('10'))
                
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
                        self.resolve_attack_element(current_combatant),
                        self.resolve_defense_element(target)
                    )
                    
                    # Apply void affinity protection to target
                    if hasattr(self.ctx.bot.cogs["Battles"], "battle_factory"):
                        pet_ext = self.ctx.bot.cogs["Battles"].battle_factory.pet_ext
                        element_mod = pet_ext.apply_void_affinity_protection(target, element_mod)
                    
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
                    blocked_damage = min(raw_damage, target.armor)
                    damage = max(raw_damage - target.armor, Decimal('10'))
                
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
                    from cogs.battles.core.combatant import Combatant
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
                    
                    # Add skeleton to the same team as the summoner
                    if current_combatant in self.team_a.combatants:
                        self.team_a.combatants.append(skeleton)
                        # Add to turn order as well
                        self.turn_order.append(skeleton)
                        message += f"\n💀 A skeleton warrior joins Team A!"
                    else:
                        self.team_b.combatants.append(skeleton)
                        # Add to turn order as well
                        self.turn_order.append(skeleton)
                        message += f"\n💀 A skeleton warrior joins Team B!"
                    
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
                blocked_damage > 0):
                
                reflected = blocked_damage * Decimal(str(reflection_value))
                current_combatant.take_damage(reflected)
                message += f"\n{target.name}'s armor reflects **{self.format_number(reflected)} HP** damage back!"
                
                if not current_combatant.is_alive():
                    message += f" {current_combatant.name} has been defeated by reflected damage!"
            
            # Check if target is defeated
            if not target.is_alive():
                # Check for cheat death ability
                if (self.config["class_buffs"] and 
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
        
        # PROCESS PET SKILL EFFECTS PER TURN
        if hasattr(self.ctx.bot.cogs["Battles"], "battle_factory"):
            pet_ext = self.ctx.bot.cogs["Battles"].battle_factory.pet_ext
            for team in self.teams:
                for combatant in team.combatants:
                    if combatant.is_pet and combatant.is_alive():
                        # Set team references for skills that need them
                        setattr(combatant, 'team', team)
                        enemy_team = self.teams[1] if team == self.teams[0] else self.teams[0]
                        setattr(combatant, 'enemy_team', enemy_team)
                        
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
                hp_bar = self.create_hp_bar(current_hp, max_hp)
                
                # Get element emoji
                element_emoji = "❌"
                for emoji, element in element_emoji_map.items():
                    if element == combatant.element:
                        element_emoji = emoji
                        break
                
                field_name = f"{combatant.display_name} [Team {team_letter}] {element_emoji}"
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
        embed = await self.create_battle_embed()
        if self.battle_message:
            await self.battle_message.edit(embed=embed)
        else:
            self.battle_message = await self.ctx.send(embed=embed)
    
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

# cogs/battles/types/couples_tower.py
import discord
import random
import asyncio
from .tower import TowerBattle

class CouplesTowerBattle(TowerBattle):
    """
    A battle tower battle for two married players.
    """
    def __init__(self, ctx, teams, **kwargs):
        try:
            # Special handling for Level 30 which has no enemies
            level = kwargs.get("level", 1)
            if level == 30:
                # Create a temporary dummy enemy to satisfy parent constructor
                from cogs.battles.core.combatant import Combatant
                from decimal import Decimal
                
                dummy_enemy = Combatant(
                    user=None,  # NPC
                    name="Dummy",
                    hp=Decimal('1'),
                    max_hp=Decimal('1'), 
                    damage=Decimal('1'),
                    armor=Decimal('0'),
                    luck=1,
                    element="Neutral"
                )
                teams[1].combatants.append(dummy_enemy)
                
                # Call parent constructor
                super().__init__(ctx, teams, **kwargs)
                
                # Immediately remove the dummy enemy after initialization
                teams[1].combatants.remove(dummy_enemy)
                self.enemy_team.combatants = []
                self.current_enemies = []
                self.current_opponent_index = 0
            else:
                # Normal initialization for all other levels
                super().__init__(ctx, teams, **kwargs)
                
            self.is_couple = True
            
            # Level-specific tracking variables
            self.last_target_attacked = None  # Level 1: Coordination bonus
            self.memory_fragments = 0  # Level 7: Memory shield
            self.grudge_stacks = {}  # Level 16: Track grudge stacks per combatant
            self.damage_dealt_tracking = {}  # Level 14: Pride damage tracking
            self.turn_counter = 0  # Level 20: Guardian test counter
            self.heal_actions_performed = set()  # Level 28: Growth requirement (deprecated)
            self.pain_damage_bonuses = {}  # Level 26: Pain endurance stacks
            self.final_enemy_vulnerable = False  # Level 28: Final enemy can be damaged
            self.aging_turns = 0  # Level 27: Aging effect counter
            self.growth_points = 0  # Level 28: Protective growth points
            self.growth_required = 4  # Level 28: Growth points needed to unlock final enemy
            self.forge_heat_intensity = 50  # Level 21: Forge heat damage
            self.heat_shield_choices = {}  # Level 21: Heat shield tracking
            self.forge_heat_round = 0  # Level 21: Track forge heat rounds
            
            # Level 22: Despair system
            self.despair_stacks = {}  # Track despair stacks per combatant
            self.encouragement_used = set()  # Track who has used encouragement this round
            
            # Level 23: Mirror of Truth possession system
            self.possessed_partner = None  # Which partner is possessed
            self.defender_partner = None  # Which partner must survive
            self.truth_demon = None  # The Truth Demon entity
            self.possession_turns = 0  # Track how many turns of possession
            self.possession_turn_limit = 20  # Must survive 20 turns
            
            # Level 24: Storm of Chaos system
            self.chaos_intensity = 1  # Starts low, escalates over time
            self.environmental_chaos_turn = 0  # Track environmental chaos timing
            self.chaos_effects = {}  # Track active chaos effects per combatant
            self.partner_anchoring = {}  # Track when partners anchor each other
            
            # Initialize battle state
            self.finished = False
        
            # Initialize damage tracking for each combatant
            for combatant in self.player_team.combatants:
                self.damage_dealt_tracking[combatant.name] = 0
                self.grudge_stacks[combatant.name] = 0
                self.pain_damage_bonuses[combatant.name] = 0
                self.despair_stacks[combatant.name] = 0  # Level 22: Initialize despair
                
            # Level 5: Split Combat assignments
            self.partner_assignments = {}  # Maps partner ID to enemy index
            self.split_combat_initialized = False
            
        except Exception as e:
            import traceback
            # Try to send error to context if possible
            import asyncio
            error_msg = f"🚨 **COUPLES TOWER INIT ERROR for Level {kwargs.get('level', 'UNKNOWN')}**:\n```\n{traceback.format_exc()}\n```"
            asyncio.create_task(ctx.send(error_msg[:2000]))
            raise e
    
    async def start_battle(self):
        """Override to handle Level 30 (no combat) and other special cases"""
        if self.level == 30:
            # Level 30: No combat, pure reward ceremony
            # Ensure no enemies exist to prevent index errors
            self.enemy_team.combatants = []
            self.current_opponent_index = 0
            await self.handle_level_30_ceremony()
            return True
            
        # Level 5: Split Combat - Assign partners to separate enemies
        if self.level == 5:
            await self.initialize_split_combat()
            
        # Level 21: Heat Shield Sacrifice - Initialize heat tracking
        if self.level == 21:
            await self.initialize_forge_heat()
            
        # Level 22: Valley of Despair - Initialize despair system
        if self.level == 22:
            await self.initialize_despair_system()
            
        # Level 23: Mirror of Truth - Initialize possession system
        if self.level == 23:
            try:
                await self.initialize_mirror_of_truth()
            except Exception as e:
                await self.ctx.send(f"Level 23 Initialization Error: {e}")
                import traceback
                await self.ctx.send(f"```{traceback.format_exc()}```")
        
        # Level 24: Storm of Chaos - Initialize chaos system
        if self.level == 24:
            await self.initialize_chaos_storm()
            
        # Level 28: Growth Requirement - Initialize protective growth system
        if self.level == 28:
            await self.initialize_protective_growth()
            
        # Call parent start_battle to ensure proper initialization and database saving
        result = await super().start_battle()
        
        # Ensure battle data is saved for replay
        await self.save_battle_to_database()
        
        return result
    
    async def initialize_chaos_storm(self):
        """Level 24: Initialize Storm of Chaos system"""
        self.chaos_intensity = 1
        self.environmental_chaos_turn = 0
        await self.add_to_log("⚡ **THE STORM OF CHAOS ENGULFS YOU!** ⚡")
        await self.add_to_log("🌪️ The environment shifts unpredictable! Walls crack, floors split, and reality bends!")
        await self.add_to_log("💕 In this maelstrom, you and your partner must be each other's anchor to stability...")
    
    async def initialize_protective_growth(self):
        """Level 28: Initialize Protective Growth system"""
        partners = [c for c in self.player_team.combatants if not c.is_pet]
        
        # Initialize protective growth tracking
        self.growth_points = 0
        self.growth_required = 4
        self.final_enemy_vulnerable = False
        self.vulnerability_growth_awarded = set()  # Track who has been awarded vulnerability growth
        
        await self.add_to_log("🌱 **THE GARDEN OF RENEWAL!** Beautiful flowers represent your relationship's growth!")
        await self.add_to_log("🛡️ **PROTECTIVE GROWTH:** When one partner has higher HP, they will shield the weaker one!")
        await self.add_to_log("🌸 **GROWTH REQUIREMENT:** Demonstrate 4 acts of caring to unlock the final enemy!")
        await self.add_to_log("💔 **VULNERABILITY GROWTH:** When partners become weak, love grows stronger!")
        await self.add_to_log("🤝 **TEAMWORK GROWTH:** Defeating enemies together strengthens your bond!")
        await self.add_to_log("⚠️ **BEWARE:** Stagnation Spirits whisper selfishness - resist their temptations!")
        
    async def track_healing_action(self, healer, target, heal_amount):
        """Level 28: DEPRECATED - Legacy healing action tracking (now using protective shielding)"""
        # This method is deprecated but kept for compatibility
        pass
    
    async def check_growth_requirement(self):
        """Level 28: DEPRECATED - Legacy growth checking (now using protective shielding)"""
        # This method is deprecated but kept for compatibility
        pass
    
    async def check_growth_opportunities(self):
        """Level 28: Check for additional growth opportunities beyond shielding"""
        if self.level != 28:
            return
            
        partners = [c for c in self.player_team.combatants if not c.is_pet and c.is_alive()]
        if len(partners) < 2:
            return
            
        partner1, partner2 = partners[0], partners[1]
        
        # Calculate HP percentages
        hp1_percent = float(partner1.hp) / float(partner1.max_hp)
        hp2_percent = float(partner2.hp) / float(partner2.max_hp)
        
        # Award growth for significant vulnerability (below 50% HP while partner is healthy) 
        vulnerability_threshold = 0.50
        healthy_threshold = 0.60
        
        growth_awarded = False
        
        if hp1_percent <= vulnerability_threshold and hp2_percent >= healthy_threshold:
            if not hasattr(self, 'vulnerability_growth_awarded'):
                self.vulnerability_growth_awarded = set()
            
            if partner1.name not in self.vulnerability_growth_awarded:
                self.growth_points += 1
                self.vulnerability_growth_awarded.add(partner1.name)
                growth_awarded = True
                await self.add_to_log(f"🌱 **VULNERABILITY GROWTH!** {partner1.name}'s weakness allows {partner2.name} to show protective love!")
                
        elif hp2_percent <= vulnerability_threshold and hp1_percent >= healthy_threshold:
            if not hasattr(self, 'vulnerability_growth_awarded'):
                self.vulnerability_growth_awarded = set()
                
            if partner2.name not in self.vulnerability_growth_awarded:
                self.growth_points += 1
                self.vulnerability_growth_awarded.add(partner2.name)
                growth_awarded = True
                await self.add_to_log(f"🌱 **VULNERABILITY GROWTH!** {partner2.name}'s weakness allows {partner1.name} to show protective love!")
        
        # Check if growth completed the requirement
        if growth_awarded and self.growth_points >= self.growth_required and not self.final_enemy_vulnerable:
            self.final_enemy_vulnerable = True
            await self.add_to_log(f"🌸 **GARDEN IN FULL BLOOM!** Your {self.growth_points} acts of love have unlocked the final enemy!", force_new_action=True)
    
    async def handle_level_30_ceremony(self):
        """Handle Level 30 special reward ceremony with interactive choice and prestige system"""
        self.started = True
        self.finished = True
        
        # Get the two partners
        partners = [c for c in self.player_team.combatants if not c.is_pet]
        partner1 = partners[0]
        partner2 = partners[1]
        
        # Randomly choose the divine blessing
        import random
        chosen_reward = random.choice(["<:c_divine:1328171231530188810>", "💝"])
        
        # Determine reward details
        if chosen_reward == "<:c_divine:1328171231530188810>":
            reward_type = "crates_divine"
            reward_amount = 1
            reward_name = "Divine Crate"
            reward_emoji = "<:c_divine:1328171231530188810>"
            reward_description = "A crate containing legendary treasures from the divine realm"
        else:  # Default to love score
            reward_type = "lovescore"
            reward_amount = 1500000
            reward_name = "Love Incarnate"
            reward_emoji = "💝"
            reward_description = "1,500,000 Love Score to strengthen your eternal bond"
        
        # Apply rewards to database
        try:
            async with self.ctx.bot.pool.acquire() as connection:
                # Give rewards to both partners
                for partner in [partner1, partner2]:
                    if reward_type == "crates_divine":
                        await connection.execute(
                            "UPDATE profile SET crates_divine = crates_divine + $1 WHERE profile.user = $2",
                            reward_amount, partner.user.id
                        )
                    else:  # lovescore
                        await connection.execute(
                            "UPDATE profile SET lovescore = lovescore + $1 WHERE profile.user = $2",
                            reward_amount, partner.user.id
                        )
                
                # Update prestige and reset tower for the couple
                await connection.execute(
                    "UPDATE couples_battle_tower SET prestige = prestige + 1, "
                    "current_level = 1 WHERE (partner1_id = $1 AND partner2_id = $2) OR (partner1_id = $2 AND partner2_id = $1)",
                    partner1.user.id, partner2.user.id
                )
                
                # Get new prestige levels for display
                partner1_prestige = await connection.fetchval(
                    "SELECT prestige FROM couples_battle_tower WHERE (partner1_id = $1 AND partner2_id = $2) OR (partner1_id = $2 AND partner2_id = $1)",
                    partner1.user.id, partner2.user.id
                )
                partner2_prestige = partner1_prestige  # Same record, same prestige
        except Exception as e:
            await self.ctx.send(f"🚨 **Error applying rewards**: {e}")
            partner1_prestige = 1
            partner2_prestige = 1
        
        # Create combined ceremony and reward embed
        embed = discord.Embed(
            title="🌟 THE APEX OF LOVE - DIVINE ASCENSION 🌟",
            description=f"*{partner1.display_name} and {partner2.display_name} stand before the Crystal Altar of Eternity, bathed in celestial light. The Tower of Eternal Bonds resonates with their pure love...*\n\n"
                       "**A divine voice echoes through the heavens:**\n"
                       "*'Beloved ones, you have conquered all trials through the power of your eternal bond. Your love has proven unbreakable, pure, and divine. The cosmos shall choose your blessing...'*",
            color=discord.Color.gold()
        )
        
        # Add reward section
        embed.add_field(
            name=f"🎁 **Divine Blessing Chosen** 🎁", 
            value=f"{reward_emoji} **{reward_name}**\n{reward_description}\n"
                  f"💑 **Both partners receive:** {reward_amount:,} {reward_type.replace('_', ' ').title()}\n"
                  f"🌟 *Your love transcends all material rewards*",
            inline=False
        )
        
        # Add prestige section
        embed.add_field(
            name="🏆 **PRESTIGE ASCENSION** 🏆",
            value=f"🌟 **{partner1.display_name}** - Prestige {partner1_prestige}\n"
                  f"🌟 **{partner2.display_name}** - Prestige {partner2_prestige}\n"
                  f"🗼 **Tower Reset** - Return to Level 1 with greater glory",
            inline=False
        )
        
        # Add completion section
        embed.add_field(
            name="💕 **ETERNAL BOND** 💕", 
            value="*Your love story continues beyond the stars. Until you meet again at the tower's peak, "
                  "let your bond be a beacon of hope for all who seek true love.*\n\n"
                  "**The Tower of Eternal Bonds awaits your return...**",
            inline=False
        )
        
        embed.set_footer(text="Thank you for playing the Couples Battle Tower • Your legend is eternal")
        
        # Send the combined embed
        try:
            await self.ctx.send(embed=embed)
            
            # Final celebration message
            await asyncio.sleep(2)
            await self.ctx.send("🌟✨💕 *The tower fades into starlight, but your love remains eternal* 💕✨🌟")
                
        except Exception as e:
            await self.ctx.send(f"🌟 **Congratulations!** You have completed the Couples Battle Tower! 🌟\n*Error in ceremony: {e}*")
    

    
    async def initialize_split_combat(self):
        """Level 5: Initialize split combat assignments"""
        try:
            partners = [c for c in self.player_team.combatants if not c.is_pet]
            
            if len(partners) >= 2 and len(self.enemy_team.combatants) >= 2:
                # Assign first partner to first enemy, second partner to second enemy
                self.partner_assignments[partners[0].user.id] = 0  # First enemy
                self.partner_assignments[partners[1].user.id] = 1  # Second enemy
                
                enemy1_name = self.enemy_team.combatants[0].name
                enemy2_name = self.enemy_team.combatants[1].name
                
                # Extract what's being protected (if in parentheses), otherwise use enemy name
                def extract_protected_target(enemy_name):
                    if '(' in enemy_name and ')' in enemy_name:
                        try:
                            return enemy_name.split('(')[1].replace(')', '')
                        except IndexError:
                            return enemy_name
                    else:
                        return enemy_name
                
                protected1 = extract_protected_target(enemy1_name)
                protected2 = extract_protected_target(enemy2_name)
                
                await self.add_to_log(f"🎯 **SPLIT COMBAT!** {partners[0].name} faces {protected1} while {partners[1].name} confronts {protected2}!")
                self.split_combat_initialized = True
        except Exception as e:
            await self.add_to_log(f"🚨 **Error initializing split combat**: {e}")
            import traceback
            await self.add_to_log(f"```{traceback.format_exc()[:1900]}```")
    
    async def process_split_combat_turn(self):
        """Handle Level 5 split combat turn processing"""
        import asyncio
        import random
        
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
        
        # Partner death check now handled in is_battle_over() universally
        
        # Determine target based on split combat assignments
        if current_combatant in self.player_team.combatants:
            if current_combatant.is_pet:
                # Pets can attack any alive enemy
                alive_enemies = [e for e in self.enemy_team.combatants if e.is_alive()]
                if not alive_enemies:
                    return False
                target = random.choice(alive_enemies)
            else:
                # Partners must attack their assigned enemy
                assigned_enemy_index = self.partner_assignments.get(current_combatant.user.id, 0)
                if assigned_enemy_index < len(self.enemy_team.combatants):
                    target = self.enemy_team.combatants[assigned_enemy_index]
                    if not target.is_alive():
                        # If assigned enemy is dead, partner waits for their partner to finish
                        await self.add_to_log(f"🛡️ {current_combatant.name} has defeated their assigned threat and anxiously watches their partner's battle!")
                        return True
                else:
                    return True
        else:
            # Enemies attack their assigned partner ONLY
            enemy_index = self.enemy_team.combatants.index(current_combatant)
            partners = [c for c in self.player_team.combatants if not c.is_pet]
            
            if enemy_index < len(partners):
                assigned_target = partners[enemy_index]
                if assigned_target.is_alive():
                    target = assigned_target
                else:
                    # If assigned partner is dead, enemy has no valid target (battle should end)
                    return False
            else:
                # No assigned partner, skip turn
                return True
        
        # Process the attack
        await self.process_attack(current_combatant, target)
        
        # Update display FIRST so players see the final blow
        await self.update_display()
        await asyncio.sleep(await self.get_turn_delay())
        
        # THEN check if battle should end after this attack
        if await self.is_battle_over():
            return False
        
        return True
    
    async def process_attack(self, attacker, target):
        """Process a single attack between attacker and target"""
        import random
        
        # Use similar logic to parent class but simplified for split combat
        luck_roll = random.randint(1, 100)
        
        # For enemies, use 10% miss chance instead of luck-based
        if attacker in self.enemy_team.combatants:
            hit_success = random.random() > 0.10
        else:
            # Check for perfect accuracy from Night Vision skill
            has_perfect_accuracy = getattr(attacker, 'perfect_accuracy', False)
            hit_success = has_perfect_accuracy or (luck_roll <= attacker.luck)
            
        if hit_success:
            # Calculate damage using standard method
            from decimal import Decimal
            damage_variance = random.randint(0, 50) if attacker.is_pet else random.randint(0, 100)
            raw_damage = attacker.damage + Decimal(damage_variance)
            
            # Apply armor reduction
            blocked_damage = min(raw_damage, target.armor)
            final_damage = max(raw_damage - target.armor, Decimal('10'))  # Minimum 10 damage
            
            # Apply damage
            target.take_damage(final_damage)
            
            message = f"{attacker.name} attacks! {target.name} takes **{float(final_damage):.1f} HP** damage."
            
            # Check if target is defeated
            if not target.is_alive():
                message += f" {target.name} has been defeated!"
            
        else:
            message = f"{attacker.name}'s attack missed!"
        
        await self.add_to_log(message, force_new_action=True)
        
    async def initialize_forge_heat(self):
        """Level 21: Initialize forge heat shield sacrifice system"""
        self.forge_heat_intensity = 50  # Reset in case it was modified
        self.forge_heat_round = 0  # Reset round counter
        await self.add_to_log("🔥 **THE FORGE IGNITES!** Blazing heat fills the chamber! The Greed Demons whisper: 'Save yourself! Let them burn!' But true love demands sacrifice...")
    
    async def process_forge_heat_damage(self):
        """Level 21: Apply forge heat damage with sacrifice mechanics"""
        # Add separator for cleaner log output
        await self.add_to_log("─── 🔥 **FORGE HEAT ROUND** 🔥 ───", force_new_action=True)
        
        partners = [c for c in self.player_team.combatants if not c.is_pet and c.is_alive()]
        
        if len(partners) < 2:
            await self.add_to_log("💔 Only one partner remains - the forge heat has no meaning without love to test...")
            await self.add_to_log("💔 **LOVE CONQUERS DEATH** 💔\n*The battle ends immediately. In love, you succeed together or fail together - one cannot carry on without the other.*")
            await asyncio.sleep(3)  # Give players time to see what happened
            return False  # End the battle - couples tower rule
        
        partner1, partner2 = partners[0], partners[1]
        
        # Determine who shields whom (randomly simulate sacrifice choices based on their love)
        # 75% chance to shield if true love, decreases if relationship is strained
        partner1_love_strength = 0.75  # Could be modified by other level effects
        partner2_love_strength = 0.75
        
        partner1_shields = random.random() < partner1_love_strength  
        partner2_shields = random.random() < partner2_love_strength
        
        base_heat_damage = self.forge_heat_intensity
        
        if partner1_shields and partner2_shields:
            # Both try to shield each other - mutual sacrifice cancels out
            damage1 = damage2 = base_heat_damage
            await self.add_to_log(f"💕 **PERFECT LOVE!** Both {partner1.name} and {partner2.name} try to shield each other! Your mutual sacrifice creates a protective aura - the forge heat is manageable!")
            
        elif partner1_shields and not partner2_shields:
            # Partner 1 shields partner 2
            damage1 = base_heat_damage * 2.5  # 2.5x damage for the ultimate sacrifice
            damage2 = 0  # Protected partner takes no heat damage
            await self.add_to_log(f"🛡️💖 **ULTIMATE SACRIFICE!** {partner1.name} throws themselves into the blazing heat to protect {partner2.name}! True love conquers selfish preservation!")
            
        elif partner2_shields and not partner1_shields:
            # Partner 2 shields partner 1  
            damage1 = 0  # Protected partner takes no heat damage
            damage2 = base_heat_damage * 2.5  # 2.5x damage for the ultimate sacrifice
            await self.add_to_log(f"🛡️💖 **ULTIMATE SACRIFICE!** {partner2.name} throws themselves into the blazing heat to protect {partner1.name}! True love conquers selfish preservation!")
            
        else:
            # Neither shields - both take normal heat damage + greed bonus damage
            greed_bonus = base_heat_damage * 0.5  # 50% bonus damage for being selfish
            damage1 = damage2 = base_heat_damage + greed_bonus
            await self.add_to_log(f"😈 **GREED TRIUMPHANT!** Neither partner shields the other! The Greed Demons laugh as your selfishness amplifies the forge's punishment!")
        
        # Apply the heat damage
        from decimal import Decimal
        damage_messages = []
        deaths = []
        
        # Check partner1 - apply damage and check for death
        if damage1 > 0:
            was_alive = partner1.is_alive()
            if was_alive:
                partner1.take_damage(Decimal(str(damage1)))
                damage_messages.append(f"🔥 {partner1.name} takes **{damage1:.1f} HP** heat damage!")
                
                # Check if they died from heat damage
                if not partner1.is_alive():
                    deaths.append(f"💀 {partner1.name} has been consumed by the forge's blazing heat!")
        
        # Check partner2 - apply damage and check for death  
        if damage2 > 0:
            was_alive = partner2.is_alive()
            if was_alive:
                partner2.take_damage(Decimal(str(damage2)))
                damage_messages.append(f"🔥 {partner2.name} takes **{damage2:.1f} HP** heat damage!")
                
                # Check if they died from heat damage
                if not partner2.is_alive():
                    deaths.append(f"💀 {partner2.name} has been consumed by the forge's blazing heat!")
            
        # Add damage messages in one clean log entry
        if damage_messages:
            combined_message = " | ".join(damage_messages)
            await self.add_to_log(combined_message)
            
        if deaths:
            for death_msg in deaths:
                await self.add_to_log(death_msg)
                
        # IMMEDIATE battle end check if anyone died from heat - don't do anything else
        if deaths:
            await self.add_to_log("💔 **LOVE ENDS IN FLAME** 💔\n*The forge's heat has claimed a life. In the Couples Tower, love cannot survive alone.*")
            
            # Immediately set battle as finished to prevent victory declaration
            self.finished = True
            
            # Update display to show final state with death
            await self.update_display()
            await asyncio.sleep(3)  # Give players time to see what happened
            return False  # End the battle immediately
        
        # Only continue if no one died
        # Update display after heat damage to show new HP
        await self.update_display()
        
        # Add small delay to let players see the heat damage effects
        await asyncio.sleep(1.5)
        
        # Increase heat intensity each turn - the forge grows more dangerous
        self.forge_heat_intensity += 8  # Heat builds up over time
        
        # Show heat intensity milestones
        if self.forge_heat_intensity >= 100 and self.forge_heat_intensity < 110:
            await self.add_to_log("🔥💥 **FORGE OVERHEATING!** The heat is becoming unbearable! Each sacrifice grows more costly!")
        elif self.forge_heat_intensity >= 150 and self.forge_heat_intensity < 160:
            await self.add_to_log("🌋 **INFERNAL INTENSITY!** The forge burns like the very depths of hell! Only the purest love can survive!")
        elif self.forge_heat_intensity >= 200:
            await self.add_to_log("⚡🔥 **FORGE MELTDOWN!** The heat threatens to consume everything! Will your sacrifice be enough?!")
            
        return True  # Continue battle
    
    async def initialize_despair_system(self):
        """Level 22: Initialize Valley of Despair system"""
        await self.add_to_log("🌫️ **THE VALLEY OF DESPAIR!** Dark mists fill your minds with hopelessness. The Despair Wraiths whisper: 'Give up... love is meaningless... you'll never succeed...'")
        await self.add_to_log("💕 But remember - together, you can encourage each other and rekindle hope in the darkest times!")
    
    async def apply_despair_effects(self, combatant, despair_amount, source="unknown", show_message=True):
        """Level 22: Apply despair stacks to a combatant"""
        if combatant.name not in self.despair_stacks:
            self.despair_stacks[combatant.name] = 0
            
        old_despair = self.despair_stacks[combatant.name]
        self.despair_stacks[combatant.name] = min(old_despair + despair_amount, 10)  # Max 10 stacks
        new_despair = self.despair_stacks[combatant.name]
        
        if new_despair > old_despair and show_message:
            # Only show milestone warnings, not individual despair gains
            if new_despair >= 8 and old_despair < 8:
                await self.add_to_log(f"💀 **CRUSHING DESPAIR!** {combatant.name} barely has the will to continue!")
            elif new_despair >= 5 and old_despair < 5:
                await self.add_to_log(f"⚠️ **DEEP DESPAIR!** {combatant.name} is losing all hope!")
        
        return new_despair - old_despair  # Return actual despair gained
    
    async def partner_encouragement(self, encourager, target):
        """Level 22: One partner encourages another to reduce despair"""
        if target.name not in self.despair_stacks or self.despair_stacks[target.name] <= 0:
            await self.add_to_log(f"💝 {encourager.name} tries to encourage {target.name}, but they're already hopeful!")
            return False
            
        # Remove 2-4 despair stacks through encouragement
        despair_removed = random.randint(2, 4)
        old_despair = self.despair_stacks[target.name]
        self.despair_stacks[target.name] = max(0, old_despair - despair_removed)
        actual_removed = old_despair - self.despair_stacks[target.name]
        
        encouragement_messages = [
            f"💕 {encourager.name} reminds {target.name} of their love! (-{actual_removed} despair)",
            f"🌟 {encourager.name} whispers words of hope to {target.name}! (-{actual_removed} despair)",
            f"💖 {encourager.name} encourages {target.name} with loving words! (-{actual_removed} despair)"
        ]
        
        await self.add_to_log(random.choice(encouragement_messages))
        
        if self.despair_stacks[target.name] == 0:
            await self.add_to_log(f"🌈 {target.name} feels renewed by their partner's love!")
            
        return True
    
    async def get_despair_damage_modifier(self, combatant):
        """Level 22: Calculate damage reduction based on despair stacks"""
        despair = self.despair_stacks.get(combatant.name, 0)
        # Each despair stack reduces damage by 8% (max 80% at 10 stacks)
        damage_reduction = min(despair * 0.08, 0.80)
        return 1.0 - damage_reduction
    
    async def get_despair_accuracy_modifier(self, combatant):
        """Level 22: Calculate accuracy reduction based on despair stacks"""
        despair = self.despair_stacks.get(combatant.name, 0)
        # Each despair stack reduces accuracy by 5% (max 50% at 10 stacks)
        accuracy_reduction = min(despair * 0.05, 0.50)
        return 1.0 - accuracy_reduction
    
    async def process_turn(self):
        """Override to add level-specific mechanics"""
        
        # Level 30: No combat, return immediately
        if self.level == 30:
            return False
            
        # Increment turn counter for various mechanics
        self.turn_counter += 1
        
        # Level 3: Jealousy Whispers - Mirror Demons whisper lies every 3 turns
        if self.level == 3:
            return await self.process_turn_with_jealousy_whispers()
        
        # Level 5: Split Combat - Override targeting logic
        if self.level == 5 and self.split_combat_initialized:
            return await self.process_split_combat_turn()
        
        # Level 20: Guardian's Test - every 5 turns pause for coordination
        if self.level == 20 and self.turn_counter % 5 == 0:
            if not await self.handle_guardian_test():
                return False  # Failed the test
        
        # Level 23: Mirror of Truth - Override turn processing entirely
        if self.level == 23:
            try:
                return await self.process_turn_with_possession_mechanics()
            except Exception as e:
                await self.ctx.send(f"Level 23 Error: {e}")
                import traceback
                await self.ctx.send(f"```{traceback.format_exc()}```")
                return False
        
        # Level 24: Storm of Chaos - override turn processing for chaos mechanics
        if self.level == 24:
            try:
                return await self.process_turn_with_chaos_mechanics()
            except Exception as e:
                await self.ctx.send(f"Level 24 Error: {e}")
                import traceback
                await self.ctx.send(f"```{traceback.format_exc()}```")
                return False
        
        # Level 21: Forge Heat - apply heat damage once per complete round
        if self.level == 21:
            try:
                current_round = self.turn_counter // len(self.turn_order) if self.turn_order else 0
                if current_round > self.forge_heat_round:
                    self.forge_heat_round = current_round
                    heat_result = await self.process_forge_heat_damage()
                    if heat_result is False:
                        return False  # Partner died from heat or only one partner remains, end battle
            except Exception as e:
                await self.ctx.send(f"Level 21 Forge Heat Error: {e}")
                import traceback
                await self.ctx.send(f"```{traceback.format_exc()}```")
        
        # Level 27: Aging Effect - reduce stats each turn
        if self.level == 27:
            try:
                await self.apply_aging_effect()
            except Exception as e:
                await self.ctx.send(f"Level 27 Error: {e}")
                import traceback
                await self.ctx.send(f"```{traceback.format_exc()}```")
        
        # Level 6: Intercept damage application for health sharing
        if self.level == 6:
            return await self.process_turn_with_damage_sharing()
        
        # Level 7: Memory fragments - override turn processing entirely 
        if self.level == 7:
            try:
                return await self.process_turn_with_memory_fragments()
            except Exception as e:
                await self.ctx.send(f"Level 7 Memory Error: {e}")
                import traceback
                await self.ctx.send(f"```{traceback.format_exc()}```")
                return False
        
        # Level 8: Friendly fire - override turn processing entirely
        if self.level == 8:
            return await self.process_turn_with_friendly_fire()
        
        # Level 10: Unity Mode - override turn processing entirely
        if self.level == 10:
            return await self.process_turn_with_unity_mode()
        
        # Level 11: Haunted Ballroom - use normal processing with error handling
        if self.level == 11:
            try:
                return await super().process_turn()
            except Exception as e:
                await self.ctx.send(f"Level 11 Error: {e}")
                import traceback
                await self.ctx.send(f"```{traceback.format_exc()}```")
                return False
        
        # Level 12: Frozen Wastes - override turn processing for freeze mechanics
        if self.level == 12:
            return await self.process_turn_with_freeze_mechanics()
        
        # Level 13: Maze of Misunderstanding - override turn processing for miscommunication
        if self.level == 13:
            return await self.process_turn_with_miscommunication()
        
        # Level 14: Mountain of Pride - override turn processing for damage tracking
        if self.level == 14:
            return await self.process_turn_with_pride_tracking()
        
        # Level 15: Battlefield of Loyalty - override turn processing for betrayal illusions
        if self.level == 15:
            return await self.process_turn_with_betrayal_illusions()
        
        # Level 16: Cavern of Forgiveness - override turn processing for grudge mechanics
        if self.level == 16:
            try:
                return await self.process_turn_with_grudge_mechanics()
            except Exception as e:
                await self.ctx.send(f"Level 16 Error: {e}")
                import traceback
                await self.ctx.send(f"```{traceback.format_exc()}```")
                return False
        
        # Level 18: Garden of Temptation - override turn processing for temptation mechanics
        if self.level == 18:
            return await self.process_turn_with_temptation_mechanics()
        
        # Level 19: Chamber of Vulnerability - override turn processing for critical hit mechanics
        if self.level == 19:
            return await self.process_turn_with_critical_hits()
        
        # Level 22: Valley of Despair - override turn processing for despair mechanics
        if self.level == 22:
            try:
                return await self.process_turn_with_despair_mechanics()
            except Exception as e:
                await self.ctx.send(f"Level 22 Error: {e}")
                import traceback
                await self.ctx.send(f"```{traceback.format_exc()}```")
                return False
        
        # Level 25: Abyss of Fear - override turn processing for fear paralysis mechanics
        if self.level == 25:
            try:
                return await self.process_turn_with_fear_mechanics()
            except Exception as e:
                await self.ctx.send(f"Level 25 Error: {e}")
                import traceback
                await self.ctx.send(f"```{traceback.format_exc()}```")
                return False
        
        # Level 26: Tower of Pain - override turn processing for pain fury mechanics
        if self.level == 26:
            try:
                return await self.process_turn_with_pain_mechanics()
            except Exception as e:
                await self.ctx.send(f"Level 26 Error: {e}")
                import traceback
                await self.ctx.send(f"```{traceback.format_exc()}```")
                return False
        
        # Level 28: Chamber of Growth - override turn processing for growth requirement mechanics  
        if self.level == 28:
            try:
                return await self.process_turn_with_growth_mechanics()
            except Exception as e:
                await self.ctx.send(f"Level 28 Error: {e}")
                import traceback
                await self.ctx.send(f"```{traceback.format_exc()}```")
                return False
        
        # Level 29: Threshold of Eternity - override turn processing for spirit healing mechanics
        if self.level == 29:
            try:
                return await self.process_turn_with_spirit_healing()
            except Exception as e:
                await self.ctx.send(f"Level 29 Error: {e}")
                import traceback
                await self.ctx.send(f"```{traceback.format_exc()}```")
                return False
        
        # Continue with normal turn processing
        return await super().process_turn()
            

    
    async def process_memory_fragment_generation(self):
        """Process Level 7 memory fragment generation after damage is applied"""
        for combatant in self.player_team.combatants:
            if hasattr(combatant, 'generate_memory_fragment'):
                self.memory_fragments += 1
                await self.add_to_log(f"💎 A precious memory crystallizes from your united effort!")
                delattr(combatant, 'generate_memory_fragment')
                break  # Only generate one fragment per turn even if multiple hits
    
    async def process_turn_with_memory_fragments(self):
        """Process turn with Level 7 memory fragment mechanics - full copy of tower.py logic with fragments added"""
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
            hit_success = luck_roll <= current_combatant.luck
            
        # Initialize message variable
        message = ""
            
        if hit_success:
            # Attack hits
            
            # Special case for mage fireball
            used_fireball = False
            if (hasattr(current_combatant, 'mage_evolution') and current_combatant.mage_evolution and 
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
                
                from decimal import Decimal
                damage = (current_combatant.damage + Decimal(random.randint(0, 100)) - target.armor) * Decimal(str(damage_multiplier))
                damage = max(damage, Decimal('1'))
                
                # *** LEVEL 7 MEMORY SHIELD FOR FIREBALL ***
                if target in self.player_team.combatants and self.memory_fragments > 0:
                    reduction = min(0.25 * self.memory_fragments, 1.0)  # Max 100% reduction
                    original_damage = float(damage)
                    damage *= Decimal(str(1 - reduction))
                    await self.add_to_log(f"💎 **MEMORY SHIELD!** {target.name}'s memories protect them! Damage reduced from {original_damage:.1f} to {float(damage):.1f}!")
                    self.memory_fragments = 0  # Reset after use
                
                target.take_damage(damage)
                message = f"{current_combatant.name} casts Fireball! {target.name} takes **{self.format_number(damage)} HP** damage."
                
                # *** LEVEL 7 MEMORY FRAGMENT GENERATION FOR FIREBALL ***
                if current_combatant in self.player_team.combatants and float(damage) > 0:
                    self.memory_fragments += 1
                    await self.add_to_log(f"💎 A precious memory crystallizes from your united effort!")
                
                used_fireball = True
            else:
                # Regular attack
                from decimal import Decimal
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
                    if element_mod != 0:
                        raw_damage = raw_damage * (1 + Decimal(str(element_mod)))
                
                # Add variance and apply armor
                raw_damage += Decimal(damage_variance)
                

                outcome = self.resolve_pet_attack_outcome(
                    current_combatant,
                    target,
                    raw_damage,
                    apply_element_mod=False,
                    damage_variance=0,
                    minimum_damage=Decimal('10'),
                )
                damage = outcome.final_damage
                blocked_damage = outcome.blocked_damage
                skill_messages = outcome.skill_messages
                defender_messages = outcome.defender_messages
                
                # *** LEVEL 7 MEMORY SHIELD FOR REGULAR ATTACKS ***
                if target in self.player_team.combatants and self.memory_fragments > 0:
                    reduction = min(0.25 * self.memory_fragments, 1.0)  # Max 100% reduction
                    original_damage = float(damage)
                    damage *= Decimal(str(1 - reduction))
                    await self.add_to_log(f"💎 **MEMORY SHIELD!** {target.name}'s memories protect them! Damage reduced from {original_damage:.1f} to {float(damage):.1f}!")
                    self.memory_fragments = 0  # Reset after use
                
                target.take_damage(damage)
                message = f"{current_combatant.name} attacks! {target.name} takes **{self.format_number(damage)} HP** damage."
                
                # *** LEVEL 7 MEMORY FRAGMENT GENERATION FOR REGULAR ATTACKS ***
                if current_combatant in self.player_team.combatants and float(damage) > 0:
                    self.memory_fragments += 1
                    message += f"\n💎 A precious memory crystallizes from your united effort!"
                
                # Add skill effect messages
                if skill_messages:
                    message += "\n" + "\n".join(skill_messages)
                if defender_messages:
                    message += "\n" + "\n".join(defender_messages)
            
            # Handle lifesteal if applicable
            if (self.config["class_buffs"] and 
                not current_combatant.is_pet and 
                hasattr(current_combatant, 'lifesteal_percent') and
                current_combatant.lifesteal_percent > 0):
                
                lifesteal_amount = (float(damage) * float(current_combatant.lifesteal_percent) / 100.0)
                current_combatant.heal(lifesteal_amount)
                message += f" Lifesteals: **{self.format_number(lifesteal_amount)} HP**"
            
            # Handle damage reflection if applicable
            reflection_value = float(getattr(target, 'damage_reflection', 0))
            
            # Apply tank evolution-based reflection if target has tank evolution
            if (self.config["class_buffs"] and 
                hasattr(target, 'tank_evolution') and target.tank_evolution and 
                not target.is_pet):
                # Use the standard tank evolution reflection multiplier from classes.py
                tank_reflection = 0.03 * target.tank_evolution  # 3% per level, so 21% at level 7
                reflection_value = max(float(reflection_value), tank_reflection)  # Use higher of item reflection or tank reflection
            
            if (self.config.get("reflection_damage", True) and 
                reflection_value > 0):
                # For Level 7, use damage-based reflection (simpler than armor-based)
                reflected_damage = float(damage) * float(reflection_value)
                current_combatant.take_damage(reflected_damage)
                message += f" **{target.name}** reflects **{self.format_number(reflected_damage)} HP** damage back!"
            
            # Check if target is defeated
            if not target.is_alive():
                # Check for cheat death ability for players
                if (self.config["class_buffs"] and 
                    self.config.get("cheat_death", True) and
                    not target.is_pet and 
                    target in self.player_team.combatants and  # Only player can cheat death
                    hasattr(target, 'death_cheat_chance') and target.death_cheat_chance > 0 and
                    not getattr(target, 'has_cheated_death', False)):
                    
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
            # Attack misses
            message = f"{current_combatant.name} attacks but misses {target.name}!"
        
        await self.add_to_log(message, force_new_action=True)
        await self.update_display()
        await asyncio.sleep(await self.get_turn_delay())
        
        return True
        
    async def process_turn_with_jealousy_whispers(self):
        """Process turn with Level 3 jealousy whispers - Mirror Demons whisper lies every 3 turns"""
        import random
        import asyncio
        
        # Every 3 turns: Mirror Demons whisper jealous lies
        if self.turn_counter % 3 == 0:
            # Add jealousy whispers to battle log (these are just thematic, not real gameplay effects)
            jealous_whispers = [
                "🪞 *The mirrors whisper:* \"Your partner is doing more damage than you... they think you're weak!\"",
                "🪞 *The mirrors hiss:* \"They're not trying as hard as you are... why should you struggle alone?\"",
                "🪞 *The mirrors taunt:* \"Look how they keep getting hurt... maybe they want to be saved instead of saving!\"",
                "🪞 *The mirrors mock:* \"Your love isn't equal... one always gives more than the other.\"",
                "🪞 *The mirrors sneer:* \"They're holding back their real power... don't they trust you?\"",
                "🪞 *The mirrors lie:* \"You always have to carry them in battle... when will they carry you?\"",
            ]
            whisper = random.choice(jealous_whispers)
            await self.add_to_log(whisper, force_new_action=True)
            
            # Add a brief pause for dramatic effect
            await asyncio.sleep(1)
            
            # Counter-message showing love conquers jealousy
            love_responses = [
                "💕 *Your bond remains strong against the lies...*",
                "💕 *Your love sees through the deception...*", 
                "💕 *Together, you reject the poisonous whispers...*",
                "💕 *Your trust in each other cannot be broken...*",
            ]
            response = random.choice(love_responses)
            await self.add_to_log(response)
        
        # Continue with normal turn processing
        return await super().process_turn()
        
    async def process_turn_with_friendly_fire(self):
        """Process turn with Level 8 friendly fire mechanics - full copy of tower.py logic with friendly fire added"""
        
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
            hit_success = luck_roll <= current_combatant.luck
            
        # Initialize message variable
        message = ""
            
        if hit_success:
            # Attack hits
            
            # Special case for mage fireball
            used_fireball = False
            if (hasattr(current_combatant, 'mage_evolution') and current_combatant.mage_evolution and 
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
                
                from decimal import Decimal
                damage = (current_combatant.damage + Decimal(random.randint(0, 100)) - target.armor) * Decimal(str(damage_multiplier))
                damage = max(damage, Decimal('1'))
                
                # *** LEVEL 7 MEMORY SHIELD FOR FIREBALL ***
                if target in self.player_team.combatants and self.memory_fragments > 0:
                    reduction = min(0.25 * self.memory_fragments, 1.0)  # Max 100% reduction
                    original_damage = float(damage)
                    damage *= Decimal(str(1 - reduction))
                    await self.add_to_log(f"💎 **MEMORY SHIELD!** {target.name}'s memories protect them! Damage reduced from {original_damage:.1f} to {float(damage):.1f}!")
                    self.memory_fragments = 0  # Reset after use
                
                target.take_damage(damage)
                message = f"{current_combatant.name} casts Fireball! {target.name} takes **{self.format_number(damage)} HP** damage."
                
                # *** LEVEL 7 MEMORY FRAGMENT GENERATION FOR FIREBALL ***
                if current_combatant in self.player_team.combatants and float(damage) > 0:
                    self.memory_fragments += 1
                    await self.add_to_log(f"💎 A precious memory crystallizes from your united effort!")
                
                used_fireball = True
            else:
                # Regular attack
                from decimal import Decimal
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
                    if element_mod != 0:
                        raw_damage = raw_damage * (1 + Decimal(str(element_mod)))
                
                # Add variance and apply armor
                raw_damage += Decimal(damage_variance)
                

                outcome = self.resolve_pet_attack_outcome(
                    current_combatant,
                    target,
                    raw_damage,
                    apply_element_mod=False,
                    damage_variance=0,
                    minimum_damage=Decimal('10'),
                )
                damage = outcome.final_damage
                blocked_damage = outcome.blocked_damage
                skill_messages = outcome.skill_messages
                defender_messages = outcome.defender_messages
                
                # *** LEVEL 7 MEMORY SHIELD FOR REGULAR ATTACKS ***
                if target in self.player_team.combatants and self.memory_fragments > 0:
                    reduction = min(0.25 * self.memory_fragments, 1.0)  # Max 100% reduction
                    original_damage = float(damage)
                    damage *= Decimal(str(1 - reduction))
                    await self.add_to_log(f"💎 **MEMORY SHIELD!** {target.name}'s memories protect them! Damage reduced from {original_damage:.1f} to {float(damage):.1f}!")
                    self.memory_fragments = 0  # Reset after use
                
                target.take_damage(damage)
                message = f"{current_combatant.name} attacks! {target.name} takes **{self.format_number(damage)} HP** damage."
                
                # *** LEVEL 7 MEMORY FRAGMENT GENERATION FOR REGULAR ATTACKS ***
                if current_combatant in self.player_team.combatants and float(damage) > 0:
                    self.memory_fragments += 1
                    message += f"\n💎 A precious memory crystallizes from your united effort!"
                
                # Add skill effect messages
                if skill_messages:
                    message += "\n" + "\n".join(skill_messages)
                if defender_messages:
                    message += "\n" + "\n".join(defender_messages)
            
            # Handle lifesteal if applicable
            if (self.config["class_buffs"] and 
                not current_combatant.is_pet and 
                hasattr(current_combatant, 'lifesteal_percent') and
                current_combatant.lifesteal_percent > 0):
                
                lifesteal_amount = (float(damage) * float(current_combatant.lifesteal_percent) / 100.0)
                current_combatant.heal(lifesteal_amount)
                message += f" Lifesteals: **{self.format_number(lifesteal_amount)} HP**"
            
            # Handle damage reflection if applicable
            reflection_value = float(getattr(target, 'damage_reflection', 0))
            
            # Apply tank evolution-based reflection if target has tank evolution
            if (self.config["class_buffs"] and 
                hasattr(target, 'tank_evolution') and target.tank_evolution and 
                not target.is_pet):
                # Use the standard tank evolution reflection multiplier from classes.py
                tank_reflection = 0.03 * target.tank_evolution  # 3% per level, so 21% at level 7
                reflection_value = max(float(reflection_value), tank_reflection)  # Use higher of item reflection or tank reflection
            
            if (self.config["reflection_damage"] and 
                reflection_value > 0 and 
                'blocked_damage' in locals() and blocked_damage > 0):
                
                # Calculate reflection as percentage of raw damage, capped at defender's armor
                reflection_base = min(raw_damage, target.armor)
                reflected = reflection_base * Decimal(str(reflection_value))
                current_combatant.take_damage(reflected)
                message += f"\n{target.name}'s armor reflects **{self.format_number(reflected)} HP** damage back!"
                
                if not current_combatant.is_alive():
                    message += f" {current_combatant.name} has been defeated by reflected damage!"
            
            # Check if target is defeated
            if not target.is_alive():
                # Check for cheat death ability for players
                if (self.config["class_buffs"] and 
                    self.config["cheat_death"] and
                    not target.is_pet and 
                    target in self.player_team.combatants and  # Only player can cheat death
                    hasattr(target, 'death_cheat_chance') and target.death_cheat_chance > 0 and
                    not getattr(target, 'has_cheated_death', False)):
                    
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
            try:
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
            except (AttributeError, KeyError):
                pass  # Pet extension not available
        
        # Update the battle display
        await self.update_display()
        await asyncio.sleep(await self.get_turn_delay())
        
        return True
    
    async def process_turn_with_friendly_fire(self):
        """Process turn with Level 8 friendly fire mechanics - full copy of tower.py logic with friendly fire added"""
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
        
        # *** LEVEL 8 FRIENDLY FIRE CHECK BEFORE ATTACK ***
        friendly_fire_occurred = False
        if (current_combatant in self.player_team.combatants and 
            not current_combatant.is_pet and 
            random.random() < 0.15):  # 15% chance for friendly fire
            
            partners = [c for c in self.player_team.combatants if not c.is_pet and c != current_combatant and c.is_alive()]
            if partners:
                friendly_fire_target = random.choice(partners)
                # Override the target with the friendly fire victim
                target = friendly_fire_target
                friendly_fire_occurred = True
        
        # Process attack based on luck
        luck_roll = random.randint(1, 100)
        
        # For minions/bosses in enemy team, use 10% miss chance instead of luck-based
        if current_combatant in self.enemy_team.combatants:
            hit_success = random.random() > 0.10  # 10% chance to miss
        else:
            hit_success = luck_roll <= current_combatant.luck
            
        # Initialize message variable
        message = ""
            
        if hit_success:
            # Attack hits
            
            # Special case for mage fireball
            used_fireball = False
            if (hasattr(current_combatant, 'mage_evolution') and current_combatant.mage_evolution and 
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
                
                from decimal import Decimal
                damage = (current_combatant.damage + Decimal(random.randint(0, 100)) - target.armor) * Decimal(str(damage_multiplier))
                damage = max(damage, Decimal('1'))
                
                # *** LEVEL 8 FRIENDLY FIRE DAMAGE REDUCTION FOR FIREBALL ***
                if friendly_fire_occurred:
                    damage *= Decimal('0.5')  # Reduce friendly fire damage by 50%
                
                target.take_damage(damage)
                
                if friendly_fire_occurred:
                    message = f"😠 **FRIENDLY FIRE!** {current_combatant.name}'s anger causes them to cast Fireball at {target.name}! {target.name} takes **{self.format_number(damage)} HP** damage."
                else:
                    message = f"{current_combatant.name} casts Fireball! {target.name} takes **{self.format_number(damage)} HP** damage."
                
                used_fireball = True
            else:
                # Regular attack
                from decimal import Decimal
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
                    if element_mod != 0:
                        raw_damage = raw_damage * (1 + Decimal(str(element_mod)))
                
                # Add variance and apply armor
                raw_damage += Decimal(damage_variance)
                

                outcome = self.resolve_pet_attack_outcome(
                    current_combatant,
                    target,
                    raw_damage,
                    apply_element_mod=False,
                    damage_variance=0,
                    minimum_damage=Decimal('10'),
                )
                damage = outcome.final_damage
                blocked_damage = outcome.blocked_damage
                skill_messages = outcome.skill_messages
                defender_messages = outcome.defender_messages
                
                # *** LEVEL 8 FRIENDLY FIRE DAMAGE REDUCTION FOR REGULAR ATTACKS ***
                if friendly_fire_occurred:
                    damage *= Decimal('0.5')  # Reduce friendly fire damage by 50%
                
                target.take_damage(damage)
                
                if friendly_fire_occurred:
                    message = f"😠 **FRIENDLY FIRE!** {current_combatant.name}'s anger causes them to accidentally strike {target.name}! {target.name} takes **{self.format_number(damage)} HP** damage."
                else:
                    message = f"{current_combatant.name} attacks! {target.name} takes **{self.format_number(damage)} HP** damage."
                
                # Add skill effect messages
                if skill_messages:
                    message += "\n" + "\n".join(skill_messages)
                if defender_messages:
                    message += "\n" + "\n".join(defender_messages)
            
            # Handle lifesteal if applicable
            if (self.config["class_buffs"] and 
                not current_combatant.is_pet and 
                hasattr(current_combatant, 'lifesteal_percent') and
                current_combatant.lifesteal_percent > 0):
                
                lifesteal_amount = (float(damage) * float(current_combatant.lifesteal_percent) / 100.0)
                current_combatant.heal(lifesteal_amount)
                message += f" Lifesteals: **{self.format_number(lifesteal_amount)} HP**"
            
            # Handle damage reflection if applicable
            reflection_value = float(getattr(target, 'damage_reflection', 0))
            
            # Apply tank evolution-based reflection if target has tank evolution
            if (self.config["class_buffs"] and 
                hasattr(target, 'tank_evolution') and target.tank_evolution and 
                not target.is_pet):
                # Use the standard tank evolution reflection multiplier from classes.py
                tank_reflection = 0.03 * target.tank_evolution  # 3% per level, so 21% at level 7
                reflection_value = max(float(reflection_value), tank_reflection)  # Use higher of item reflection or tank reflection
            
            if (self.config["reflection_damage"] and 
                reflection_value > 0 and 
                'blocked_damage' in locals() and blocked_damage > 0):
                
                # Calculate reflection as percentage of raw damage, capped at defender's armor
                reflection_base = min(raw_damage, target.armor)
                reflected = reflection_base * Decimal(str(reflection_value))
                current_combatant.take_damage(reflected)
                message += f"\n{target.name}'s armor reflects **{self.format_number(reflected)} HP** damage back!"
                
                if not current_combatant.is_alive():
                    message += f" {current_combatant.name} has been defeated by reflected damage!"
            
            # Check if target is defeated
            if not target.is_alive():
                # Check for cheat death ability for players
                if (self.config["class_buffs"] and 
                    self.config["cheat_death"] and
                    not target.is_pet and 
                    target in self.player_team.combatants and  # Only player can cheat death
                    hasattr(target, 'death_cheat_chance') and target.death_cheat_chance > 0 and
                    not getattr(target, 'has_cheated_death', False)):
                    
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
            try:
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
            except (AttributeError, KeyError):
                pass  # Pet extension not available
        
        # Update the battle display
        await self.update_display()
        await asyncio.sleep(await self.get_turn_delay())
        
        return True
    
    async def process_turn_with_unity_mode(self):
        """Process turn with Level 10 Unity Mode mechanics - full copy of tower.py logic with unity bonus added"""
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
            hit_success = luck_roll <= current_combatant.luck
            
        # Initialize message variable
        message = ""
            
        if hit_success:
            # Attack hits
            
            # Special case for mage fireball
            used_fireball = False
            if (hasattr(current_combatant, 'mage_evolution') and current_combatant.mage_evolution and 
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
                
                from decimal import Decimal
                damage = (current_combatant.damage + Decimal(random.randint(0, 100)) - target.armor) * Decimal(str(damage_multiplier))
                damage = max(damage, Decimal('1'))
                
                # *** LEVEL 10 UNITY MODE FOR FIREBALL ***
                if current_combatant in self.player_team.combatants and not current_combatant.is_pet:
                    partners = [c for c in self.player_team.combatants if not c.is_pet and c != current_combatant and c.is_alive()]
                    for partner in partners:
                        if partner.hp / partner.max_hp < 0.25:  # Partner critically wounded
                            damage *= Decimal('1.50')  # +50% damage
                            await self.add_to_log(f"💪 **UNITY MODE!** {current_combatant.name} fights with desperate fury to protect their wounded love!")
                            break
                
                target.take_damage(damage)
                message = f"{current_combatant.name} casts Fireball! {target.name} takes **{self.format_number(damage)} HP** damage."
                used_fireball = True
            else:
                # Regular attack
                from decimal import Decimal
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
                    if element_mod != 0:
                        raw_damage = raw_damage * (1 + Decimal(str(element_mod)))
                
                # Add variance and apply armor
                raw_damage += Decimal(damage_variance)
                

                outcome = self.resolve_pet_attack_outcome(
                    current_combatant,
                    target,
                    raw_damage,
                    apply_element_mod=False,
                    damage_variance=0,
                    minimum_damage=Decimal('10'),
                )
                damage = outcome.final_damage
                blocked_damage = outcome.blocked_damage
                skill_messages = outcome.skill_messages
                defender_messages = outcome.defender_messages
                
                # *** LEVEL 10 UNITY MODE FOR REGULAR ATTACKS ***
                if current_combatant in self.player_team.combatants and not current_combatant.is_pet:
                    partners = [c for c in self.player_team.combatants if not c.is_pet and c != current_combatant and c.is_alive()]
                    for partner in partners:
                        if partner.hp / partner.max_hp < 0.25:  # Partner critically wounded
                            damage *= Decimal('1.50')  # +50% damage
                            await self.add_to_log(f"💪 **UNITY MODE!** {current_combatant.name} fights with desperate fury to protect their wounded love!")
                            break
                
                target.take_damage(damage)
                message = f"{current_combatant.name} attacks! {target.name} takes **{self.format_number(damage)} HP** damage."
                
                # Add skill effect messages
                if skill_messages:
                    message += "\n" + "\n".join(skill_messages)
                if defender_messages:
                    message += "\n" + "\n".join(defender_messages)
            
            # Handle lifesteal if applicable
            if (self.config["class_buffs"] and 
                not current_combatant.is_pet and 
                hasattr(current_combatant, 'lifesteal_percent') and
                current_combatant.lifesteal_percent > 0):
                
                lifesteal_amount = (float(damage) * float(current_combatant.lifesteal_percent) / 100.0)
                current_combatant.heal(lifesteal_amount)
                message += f" Lifesteals: **{self.format_number(lifesteal_amount)} HP**"
            
            # Handle damage reflection if applicable
            reflection_value = float(getattr(target, 'damage_reflection', 0))
            
            # Apply tank evolution-based reflection if target has tank evolution
            if (self.config["class_buffs"] and 
                hasattr(target, 'tank_evolution') and target.tank_evolution and 
                not target.is_pet):
                # Use the standard tank evolution reflection multiplier from classes.py
                tank_reflection = 0.03 * target.tank_evolution  # 3% per level, so 21% at level 7
                reflection_value = max(float(reflection_value), tank_reflection)  # Use higher of item reflection or tank reflection
            
            if (self.config["reflection_damage"] and 
                reflection_value > 0 and 
                'blocked_damage' in locals() and blocked_damage > 0):
                
                # Calculate reflection as percentage of raw damage, capped at defender's armor
                reflection_base = min(raw_damage, target.armor)
                reflected = reflection_base * Decimal(str(reflection_value))
                current_combatant.take_damage(reflected)
                message += f"\n{target.name}'s armor reflects **{self.format_number(reflected)} HP** damage back!"
                
                if not current_combatant.is_alive():
                    message += f" {current_combatant.name} has been defeated by reflected damage!"
            
            # Check if target is defeated
            if not target.is_alive():
                # Check for cheat death ability for players
                if (self.config["class_buffs"] and 
                    self.config["cheat_death"] and
                    not target.is_pet and 
                    target in self.player_team.combatants and  # Only player can cheat death
                    hasattr(target, 'death_cheat_chance') and target.death_cheat_chance > 0 and
                    not getattr(target, 'has_cheated_death', False)):
                    
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
            try:
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
            except (AttributeError, KeyError):
                pass  # Pet extension not available
        
        # Update the battle display
        await self.update_display()
        await asyncio.sleep(await self.get_turn_delay())
        
        return True
    
    async def process_turn_with_freeze_mechanics(self):
        """Process turn with Level 12 freeze mechanics"""
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
            
        # Level 12: Freeze check - but Frost Giants are immune to cold
        if "Frost Giant" not in current_combatant.name and random.random() < 0.20:  # Back to 20% and immune giants
            await self.add_to_log(f"🧊 **FROZEN!** {current_combatant.name} is too cold to act this turn!", force_new_action=True)
            await self.update_display()
            await asyncio.sleep(await self.get_turn_delay())
            return True
            
        # If not frozen, use normal turn processing
        return await super().process_turn()

    
    async def handle_guardian_test(self):
        """Level 20: Guardian's Test coordination challenge"""
        embed = discord.Embed(
            title="🛡️ Guardian's Test of Unity 🛡️",
            description="The Guardian halts the battle!\n\n**Both partners must type 'together' within 10 seconds to continue!**",
            color=discord.Color.orange()
        )
        await self.ctx.send(embed=embed)
        
        responses = set()
        start_time = asyncio.get_event_loop().time()
        
        def check(m):
            return (m.author.id in [c.user.id for c in self.player_team.combatants if not c.is_pet] 
                   and m.content.lower() == 'together')
        
        try:
            while len(responses) < 2 and (asyncio.get_event_loop().time() - start_time) < 10:
                remaining_time = 10 - (asyncio.get_event_loop().time() - start_time)
                if remaining_time <= 0:
                    break
                    
                msg = await asyncio.wait_for(
                    self.ctx.bot.wait_for('message', check=check), 
                    timeout=remaining_time
                )
                responses.add(msg.author.id)
                
            if len(responses) >= 2:
                await self.add_to_log("💕 **SUCCESS!** Your unity impresses the Guardian! The battle continues!")
                return True
            else:
                await self.add_to_log("💔 **COORDINATION FAILURE!** The Guardian declares your love unworthy!")
                await self.execute_guardian_punishment()
                await self.ctx.send("💔 **BATTLE FAILED!** Level 20's Guardian's Test requires both partners to type 'together' within 10 seconds. Your love has been found lacking...")
                return False
                
        except asyncio.TimeoutError:
            await self.add_to_log("💔 **TIMEOUT FAILURE!** The Guardian declares your love unworthy!")
            await self.execute_guardian_punishment()
            await self.ctx.send("💔 **BATTLE FAILED!** Level 20's Guardian's Test requires both partners to type 'together' within 10 seconds. Your love has been found lacking...")
            return False
    
    async def execute_guardian_punishment(self):
        """Execute the Guardian's lethal punishment for failing the coordination test"""
        from decimal import Decimal
        
        partners = [c for c in self.player_team.combatants if not c.is_pet]
        
        await self.add_to_log("⚡ **GUARDIAN'S WRATH!** The Guardian unleashes devastating divine judgment upon the unworthy lovers!")
        
        for partner in partners:
            if partner.is_alive():
                # Deal 99999 true damage to ensure death
                lethal_damage = Decimal('99999')
                partner.take_damage(lethal_damage)
                await self.add_to_log(f"💀 **DIVINE PUNISHMENT!** {partner.name} is struck down by the Guardian's wrath for **{self.format_number(lethal_damage)} HP** true damage!")
        
        # Also kill any pets as collateral damage
        for pet in [c for c in self.player_team.combatants if c.is_pet]:
            if pet.is_alive():
                lethal_damage = Decimal('99999')
                pet.take_damage(lethal_damage)
                await self.add_to_log(f"💀 **COLLATERAL DAMAGE!** {pet.name} perishes in the Guardian's divine fury!")
    
    async def apply_aging_effect(self):
        """Level 27: Gradually reduce couple's stats (3% per turn)"""
        try:
            from decimal import Decimal
            
            self.aging_turns += 1
            
            # Only affect the couple (not pets or enemies) - Time Wraith is immune to aging
            partners = [c for c in self.player_team.combatants if not c.is_pet and c.is_alive()]
            
            if not partners:
                return  # No living partners to age
            
            aging_multiplier = Decimal('0.97')  # 97% of previous value (3% reduction)
            min_damage = Decimal('1')
            min_armor = Decimal('0')
            min_hp = Decimal('1')
            
            for partner in partners:
                # Store original stats for logging
                old_damage = float(partner.damage)
                old_armor = float(partner.armor) 
                old_max_hp = float(partner.max_hp)
                
                # Reduce stats by 3% per turn using Decimal arithmetic
                partner.damage = max(min_damage, partner.damage * aging_multiplier)
                partner.armor = max(min_armor, partner.armor * aging_multiplier)
                partner.max_hp = max(min_hp, partner.max_hp * aging_multiplier)
                
                # Ensure current HP doesn't exceed new max
                if partner.hp > partner.max_hp:
                    partner.hp = partner.max_hp
                
                # Debug: Log aging effects (only on turn 1 to avoid spam)
                if self.aging_turns == 1:
                    await self.add_to_log(f"🕰️ {partner.name} feels time's weight... (Damage: {old_damage:.1f}→{float(partner.damage):.1f}, Armor: {old_armor:.1f}→{float(partner.armor):.1f}, Max HP: {old_max_hp:.1f}→{float(partner.max_hp):.1f})")
            
            if self.aging_turns % 2 == 0:  # Every 2 turns
                await self.add_to_log(f"⏳ **TIME'S TOLL!** The years weigh heavily on your love, draining your strength...")
            
            # Show aging milestone messages
            if self.aging_turns == 5:
                await self.add_to_log(f"👴👵 You feel the first gray hairs appearing, your joints growing stiff...")
            elif self.aging_turns == 10:
                await self.add_to_log(f"🍂 Wrinkles line your faces, but your eyes still shine with love...")
            elif self.aging_turns == 15:
                await self.add_to_log(f"🌅 Though your bodies grow frail, your spirits remain intertwined...")
                
        except Exception as e:
            await self.ctx.send(f"Level 27 Aging Error: {e}")
            import traceback
            await self.ctx.send(f"```{traceback.format_exc()}```")
    
    async def process_turn_with_damage_sharing(self):
        """Process turn with Level 6 damage sharing mechanics - full copy of tower.py logic with sharing added"""
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
            hit_success = luck_roll <= current_combatant.luck
            
        # Initialize message variable
        message = ""
            
        if hit_success:
            # Attack hits
            
            # Special case for mage fireball
            used_fireball = False
            if (hasattr(current_combatant, 'mage_evolution') and current_combatant.mage_evolution and 
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
                
                from decimal import Decimal
                damage = (current_combatant.damage + Decimal(random.randint(0, 100)) - target.armor) * Decimal(str(damage_multiplier))
                damage = max(damage, Decimal('1'))
                
                # *** LEVEL 6 DAMAGE SHARING FOR FIREBALL ***
                if target in self.player_team.combatants and not target.is_pet:
                    partners = [c for c in self.player_team.combatants if not c.is_pet and c != target and c.is_alive()]
                    
                    if partners and damage > 0:
                        shared_damage = damage * Decimal('0.25')  # Share 25% of damage
                        reduced_damage = damage * Decimal('0.75')  # Reduce original damage
                        
                        # Apply shared damage to partners
                        for partner in partners:
                            partner.take_damage(shared_damage)
                            await self.add_to_log(f"💕 **SHARED BURDEN!** {partner.name} shares {target.name}'s pain ({self.format_number(shared_damage)} damage)!")
                        
                        # Apply reduced damage to original target
                        target.take_damage(reduced_damage)
                        message = f"{current_combatant.name} casts Fireball! {target.name} takes **{self.format_number(reduced_damage)} HP** damage."
                    else:
                        # No sharing, apply full damage
                        target.take_damage(damage)
                        message = f"{current_combatant.name} casts Fireball! {target.name} takes **{self.format_number(damage)} HP** damage."
                else:
                    # Not a player partner, apply damage normally
                    target.take_damage(damage)
                    message = f"{current_combatant.name} casts Fireball! {target.name} takes **{self.format_number(damage)} HP** damage."
                
                used_fireball = True
            else:
                # Regular attack
                from decimal import Decimal
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
                    if element_mod != 0:
                        raw_damage = raw_damage * (1 + Decimal(str(element_mod)))
                
                # Add variance and apply armor
                raw_damage += Decimal(damage_variance)
                

                outcome = self.resolve_pet_attack_outcome(
                    current_combatant,
                    target,
                    raw_damage,
                    apply_element_mod=False,
                    damage_variance=0,
                    minimum_damage=Decimal('10'),
                )
                damage = outcome.final_damage
                blocked_damage = outcome.blocked_damage
                skill_messages = outcome.skill_messages
                defender_messages = outcome.defender_messages
                
                # *** LEVEL 6 DAMAGE SHARING FOR REGULAR ATTACKS ***
                if target in self.player_team.combatants and not target.is_pet:
                    partners = [c for c in self.player_team.combatants if not c.is_pet and c != target and c.is_alive()]
                    
                    if partners and damage > 0:
                        shared_damage = damage * Decimal('0.25')  # Share 25% of damage
                        reduced_damage = damage * Decimal('0.75')  # Reduce original damage
                        
                        # Apply shared damage to partners
                        for partner in partners:
                            partner.take_damage(shared_damage)
                            await self.add_to_log(f"💕 **SHARED BURDEN!** {partner.name} shares {target.name}'s pain ({self.format_number(shared_damage)} damage)!")
                        
                        # Apply reduced damage to original target
                        target.take_damage(reduced_damage)
                        message = f"{current_combatant.name} attacks! {target.name} takes **{self.format_number(reduced_damage)} HP** damage."
                    else:
                        # No sharing, apply full damage
                        target.take_damage(damage)
                        message = f"{current_combatant.name} attacks! {target.name} takes **{self.format_number(damage)} HP** damage."
                else:
                    # Not a player partner, apply damage normally
                    target.take_damage(damage)
                    message = f"{current_combatant.name} attacks! {target.name} takes **{self.format_number(damage)} HP** damage."
                
                # Add skill effect messages
                if skill_messages:
                    message += "\n" + "\n".join(skill_messages)
                if defender_messages:
                    message += "\n" + "\n".join(defender_messages)
            
            # Handle lifesteal if applicable
            if (self.config["class_buffs"] and 
                not current_combatant.is_pet and 
                hasattr(current_combatant, 'lifesteal_percent') and
                current_combatant.lifesteal_percent > 0):
                
                lifesteal_amount = (float(damage) * float(current_combatant.lifesteal_percent) / 100.0)
                current_combatant.heal(lifesteal_amount)
                message += f" Lifesteals: **{self.format_number(lifesteal_amount)} HP**"
            
            # Handle damage reflection if applicable
            reflection_value = float(getattr(target, 'damage_reflection', 0))
            
            # Apply tank evolution-based reflection if target has tank evolution
            if (self.config["class_buffs"] and 
                hasattr(target, 'tank_evolution') and target.tank_evolution and 
                not target.is_pet):
                # Use the standard tank evolution reflection multiplier from classes.py
                tank_reflection = 0.03 * target.tank_evolution  # 3% per level, so 21% at level 7
                reflection_value = max(float(reflection_value), tank_reflection)  # Use higher of item reflection or tank reflection
            
            if (self.config["reflection_damage"] and 
                reflection_value > 0 and 
                'blocked_damage' in locals() and blocked_damage > 0):
                
                # Calculate reflection as percentage of raw damage, capped at defender's armor
                reflection_base = min(raw_damage, target.armor)
                reflected = reflection_base * Decimal(str(reflection_value))
                current_combatant.take_damage(reflected)
                message += f"\n{target.name}'s armor reflects **{self.format_number(reflected)} HP** damage back!"
                
                if not current_combatant.is_alive():
                    message += f" {current_combatant.name} has been defeated by reflected damage!"
            
            # Check if target is defeated
            if not target.is_alive():
                # Check for cheat death ability for players
                if (self.config["class_buffs"] and 
                    self.config.get("cheat_death", True) and
                    not target.is_pet and 
                    target in self.player_team.combatants and  # Only player can cheat death
                    hasattr(target, 'death_cheat_chance') and target.death_cheat_chance > 0 and
                    not getattr(target, 'has_cheated_death', False)):
                    
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
                from decimal import Decimal
                damage = Decimal('10')
                current_combatant.take_damage(damage)
                message = f"{current_combatant.name} tripped and took **{self.format_number(damage)} HP** damage. Bad luck!"
            else:
                message = f"{current_combatant.name}'s attack missed!"
        
        # Add message to battle log - use a new action number for each combat action
        await self.add_to_log(message, force_new_action=True)
        
        # PROCESS PET SKILL EFFECTS PER TURN
        if hasattr(self.ctx.bot.cogs["Battles"], "battle_factory"):
            try:
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
            except (AttributeError, KeyError):
                pass  # Pet extension not available
        
        # Update the battle display
        await self.update_display()
        await asyncio.sleep(await self.get_turn_delay())
        
        return True

    async def process_turn_with_miscommunication(self):
        """Process turn with Level 13 miscommunication mechanics"""
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
            # Player's turn, target any alive enemy (Level 13 has multiple active enemies)
            alive_enemies = [e for e in self.enemy_team.combatants if e.is_alive()]
            
            if not alive_enemies:
                # All enemies defeated
                return False
            
            # For Level 13, target a random alive enemy instead of using current_opponent_index
            target = random.choice(alive_enemies)
        else:
            # Enemy's turn, target a random player combatant
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
            hit_success = luck_roll <= current_combatant.luck
            
        # Initialize message variable
        message = ""
            
        if hit_success:
            # Attack hits
            
            # Special case for mage fireball
            used_fireball = False
            if (hasattr(current_combatant, 'mage_evolution') and current_combatant.mage_evolution and 
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
                
                from decimal import Decimal
                damage = (current_combatant.damage + Decimal(random.randint(0, 100)) - target.armor) * Decimal(str(damage_multiplier))
                damage = max(damage, Decimal('1'))
                
                # *** LEVEL 13 MISCOMMUNICATION FOR FIREBALL ***
                if current_combatant in self.player_team.combatants and not current_combatant.is_pet:
                    if random.random() < 0.30:  # 30% chance for miscommunication
                        available_targets = [c for c in self.enemy_team.combatants if c.is_alive()]
                        if available_targets and len(available_targets) > 1:
                            new_target = random.choice([t for t in available_targets if t != target])
                            if new_target:
                                await self.add_to_log(f"🗣️ **MISCOMMUNICATION!** {current_combatant.name} strikes {new_target.name} instead due to confusion!")
                                target = new_target
                
                target.take_damage(damage)
                message = f"{current_combatant.name} casts Fireball! {target.name} takes **{self.format_number(damage)} HP** damage."
                used_fireball = True
            else:
                # Regular attack
                from decimal import Decimal
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
                    if element_mod != 0:
                        raw_damage = raw_damage * (1 + Decimal(str(element_mod)))
                
                # Add variance and apply armor
                raw_damage += Decimal(damage_variance)
                

                outcome = self.resolve_pet_attack_outcome(
                    current_combatant,
                    target,
                    raw_damage,
                    apply_element_mod=False,
                    damage_variance=0,
                    minimum_damage=Decimal('10'),
                )
                damage = outcome.final_damage
                blocked_damage = outcome.blocked_damage
                skill_messages = outcome.skill_messages
                defender_messages = outcome.defender_messages
                
                # *** LEVEL 13 MISCOMMUNICATION FOR REGULAR ATTACKS ***
                if current_combatant in self.player_team.combatants and not current_combatant.is_pet:
                    if random.random() < 0.30:  # 30% chance for miscommunication
                        available_targets = [c for c in self.enemy_team.combatants if c.is_alive()]
                        if available_targets and len(available_targets) > 1:
                            new_target = random.choice([t for t in available_targets if t != target])
                            if new_target:
                                await self.add_to_log(f"🗣️ **MISCOMMUNICATION!** {current_combatant.name} strikes {new_target.name} instead due to confusion!")
                                target = new_target
                
                target.take_damage(damage)
                message = f"{current_combatant.name} attacks! {target.name} takes **{self.format_number(damage)} HP** damage."
                
                # Add skill effect messages
                if skill_messages:
                    message += "\n" + "\n".join(skill_messages)
                if defender_messages:
                    message += "\n" + "\n".join(defender_messages)
            
            # Handle lifesteal if applicable
            if (self.config["class_buffs"] and 
                not current_combatant.is_pet and 
                hasattr(current_combatant, 'lifesteal_percent') and
                current_combatant.lifesteal_percent > 0):
                
                lifesteal_amount = (float(damage) * float(current_combatant.lifesteal_percent) / 100.0)
                current_combatant.heal(lifesteal_amount)
                message += f" Lifesteals: **{self.format_number(lifesteal_amount)} HP**"
            
            # Handle damage reflection if applicable
            reflection_value = float(getattr(target, 'damage_reflection', 0))
            
            # Apply tank evolution-based reflection if target has tank evolution
            if (self.config["class_buffs"] and 
                hasattr(target, 'tank_evolution') and target.tank_evolution and 
                not target.is_pet):
                # Use the standard tank evolution reflection multiplier from classes.py
                tank_reflection = 0.03 * target.tank_evolution  # 3% per level, so 21% at level 7
                reflection_value = max(float(reflection_value), tank_reflection)  # Use higher of item reflection or tank reflection
            
            if (self.config["reflection_damage"] and 
                reflection_value > 0 and 
                'blocked_damage' in locals() and blocked_damage > 0):
                
                # Calculate reflection as percentage of raw damage, capped at defender's armor
                reflection_base = min(raw_damage, target.armor)
                reflected = reflection_base * Decimal(str(reflection_value))
                current_combatant.take_damage(reflected)
                message += f"\n{target.name}'s armor reflects **{self.format_number(reflected)} HP** damage back!"
                
                if not current_combatant.is_alive():
                    message += f" {current_combatant.name} has been defeated by reflected damage!"
            
            # Check if target is defeated
            if not target.is_alive():
                # Check for cheat death ability for players
                if (self.config["class_buffs"] and 
                    self.config.get("cheat_death", True) and
                    not target.is_pet and 
                    target in self.player_team.combatants and  # Only player can cheat death
                    hasattr(target, 'death_cheat_chance') and target.death_cheat_chance > 0 and
                    not getattr(target, 'has_cheated_death', False)):
                    
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
            try:
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
            except (AttributeError, KeyError):
                pass  # Pet extension not available
        
        # Update the battle display
        await self.update_display()
        await asyncio.sleep(await self.get_turn_delay())
        
        return True

    async def process_turn_with_pride_tracking(self):
        """Process turn with Level 14 pride damage tracking mechanics"""
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
            hit_success = luck_roll <= current_combatant.luck
            
        # Initialize message variable
        message = ""
            
        if hit_success:
            # Attack hits
            
            # Special case for mage fireball
            used_fireball = False
            if (hasattr(current_combatant, 'mage_evolution') and current_combatant.mage_evolution and 
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
                
                from decimal import Decimal
                damage = (current_combatant.damage + Decimal(random.randint(0, 100)) - target.armor) * Decimal(str(damage_multiplier))
                damage = max(damage, Decimal('1'))
                
                target.take_damage(damage)
                
                # *** LEVEL 14 PRIDE TRACKING FOR FIREBALL ***
                if current_combatant in self.player_team.combatants:
                    current_damage = self.damage_dealt_tracking.get(current_combatant.name, 0)
                    self.damage_dealt_tracking[current_combatant.name] = current_damage + float(damage)
                
                message = f"{current_combatant.name} casts Fireball! {target.name} takes **{self.format_number(damage)} HP** damage."
                used_fireball = True
            else:
                # Regular attack
                from decimal import Decimal
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
                    if element_mod != 0:
                        raw_damage = raw_damage * (1 + Decimal(str(element_mod)))
                
                # Add variance and apply armor
                raw_damage += Decimal(damage_variance)
                

                outcome = self.resolve_pet_attack_outcome(
                    current_combatant,
                    target,
                    raw_damage,
                    apply_element_mod=False,
                    damage_variance=0,
                    minimum_damage=Decimal('10'),
                )
                damage = outcome.final_damage
                blocked_damage = outcome.blocked_damage
                skill_messages = outcome.skill_messages
                defender_messages = outcome.defender_messages
                
                target.take_damage(damage)
                
                # *** LEVEL 14 PRIDE TRACKING FOR REGULAR ATTACKS ***
                if current_combatant in self.player_team.combatants:
                    current_damage = self.damage_dealt_tracking.get(current_combatant.name, 0)
                    self.damage_dealt_tracking[current_combatant.name] = current_damage + float(damage)
                    
                    # Check if one partner is significantly outperforming the other
                    partners = [c for c in self.player_team.combatants if not c.is_pet]
                    if len(partners) == 2:
                        partner1_damage = self.damage_dealt_tracking.get(partners[0].name, 0)
                        partner2_damage = self.damage_dealt_tracking.get(partners[1].name, 0)
                        total_damage = partner1_damage + partner2_damage
                        
                        if total_damage > 0:
                            # If one partner has done more than 70% of total damage
                            if partner1_damage / total_damage > 0.7:
                                await self.add_to_log(f"😤 **PRIDE RISING!** {partners[0].name} feels superior with {partner1_damage:.1f} damage vs {partners[1].name}'s {partner2_damage:.1f}!")
                            elif partner2_damage / total_damage > 0.7:
                                await self.add_to_log(f"😤 **PRIDE RISING!** {partners[1].name} feels superior with {partner2_damage:.1f} damage vs {partners[0].name}'s {partner1_damage:.1f}!")
                
                message = f"{current_combatant.name} attacks! {target.name} takes **{self.format_number(damage)} HP** damage."
                
                # Add skill effect messages
                if skill_messages:
                    message += "\n" + "\n".join(skill_messages)
                if defender_messages:
                    message += "\n" + "\n".join(defender_messages)
            
            # Handle lifesteal if applicable
            if (self.config["class_buffs"] and 
                not current_combatant.is_pet and 
                hasattr(current_combatant, 'lifesteal_percent') and
                current_combatant.lifesteal_percent > 0):
                
                lifesteal_amount = (float(damage) * float(current_combatant.lifesteal_percent) / 100.0)
                current_combatant.heal(lifesteal_amount)
                message += f" Lifesteals: **{self.format_number(lifesteal_amount)} HP**"
            
            # Handle damage reflection if applicable
            reflection_value = float(getattr(target, 'damage_reflection', 0))
            
            # Apply tank evolution-based reflection if target has tank evolution
            if (self.config["class_buffs"] and 
                hasattr(target, 'tank_evolution') and target.tank_evolution and 
                not target.is_pet):
                # Use the standard tank evolution reflection multiplier from classes.py
                tank_reflection = 0.03 * target.tank_evolution  # 3% per level, so 21% at level 7
                reflection_value = max(float(reflection_value), tank_reflection)  # Use higher of item reflection or tank reflection
            
            if (self.config["reflection_damage"] and 
                reflection_value > 0 and 
                'blocked_damage' in locals() and blocked_damage > 0):
                
                # Calculate reflection as percentage of raw damage, capped at defender's armor
                reflection_base = min(raw_damage, target.armor)
                reflected = reflection_base * Decimal(str(reflection_value))
                current_combatant.take_damage(reflected)
                message += f"\n{target.name}'s armor reflects **{self.format_number(reflected)} HP** damage back!"
                
                if not current_combatant.is_alive():
                    message += f" {current_combatant.name} has been defeated by reflected damage!"
            
            # Check if target is defeated
            if not target.is_alive():
                # Check for cheat death ability for players
                if (self.config["class_buffs"] and 
                    self.config.get("cheat_death", True) and
                    not target.is_pet and 
                    target in self.player_team.combatants and  # Only player can cheat death
                    hasattr(target, 'death_cheat_chance') and target.death_cheat_chance > 0 and
                    not getattr(target, 'has_cheated_death', False)):
                    
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
            try:
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
            except (AttributeError, KeyError):
                pass  # Pet extension not available
        
        # Update the battle display
        await self.update_display()
        await asyncio.sleep(await self.get_turn_delay())
        
        return True

    async def process_turn_with_betrayal_illusions(self):
        """Process turn with Level 15 betrayal illusions mechanics"""
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
            hit_success = luck_roll <= current_combatant.luck
            
        # Initialize message variable
        message = ""
            
        if hit_success:
            # Attack hits
            
            # Special case for mage fireball
            used_fireball = False
            if (hasattr(current_combatant, 'mage_evolution') and current_combatant.mage_evolution and 
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
                
                from decimal import Decimal
                damage = (current_combatant.damage + Decimal(random.randint(0, 100)) - target.armor) * Decimal(str(damage_multiplier))
                damage = max(damage, Decimal('1'))
                
                # *** LEVEL 15 BETRAYAL ILLUSIONS FOR FIREBALL ***
                if current_combatant in self.player_team.combatants and not current_combatant.is_pet:
                    if random.random() < 0.25:  # 25% chance for betrayal illusion
                        partners = [c for c in self.player_team.combatants if not c.is_pet and c != current_combatant and c.is_alive()]
                        if partners:
                            partner = partners[0]
                            betrayal_illusions = [
                                f"💔 **BETRAYAL ILLUSION!** {current_combatant.name} sees a vision of {partner.name} walking away and leaving them behind!",
                                f"👻 **FALSE VISION!** {current_combatant.name} glimpses {partner.name} choosing someone else over them!",
                                f"😱 **WRAITH'S LIE!** {current_combatant.name} watches an illusion of {partner.name} giving up on their love!",
                                f"🌫️ **PHANTOM BETRAYAL!** {current_combatant.name} sees {partner.name} abandoning them in their darkest hour!"
                            ]
                            await self.add_to_log(random.choice(betrayal_illusions))
                            damage *= Decimal('0.75')  # Reduced damage due to emotional distraction
                
                target.take_damage(damage)
                message = f"{current_combatant.name} casts Fireball! {target.name} takes **{self.format_number(damage)} HP** damage."
                used_fireball = True
            else:
                # Regular attack
                from decimal import Decimal
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
                    if element_mod != 0:
                        raw_damage = raw_damage * (1 + Decimal(str(element_mod)))
                
                # Add variance and apply armor
                raw_damage += Decimal(damage_variance)
                

                outcome = self.resolve_pet_attack_outcome(
                    current_combatant,
                    target,
                    raw_damage,
                    apply_element_mod=False,
                    damage_variance=0,
                    minimum_damage=Decimal('10'),
                )
                damage = outcome.final_damage
                blocked_damage = outcome.blocked_damage
                skill_messages = outcome.skill_messages
                defender_messages = outcome.defender_messages
                
                # *** LEVEL 15 BETRAYAL ILLUSIONS FOR REGULAR ATTACKS ***
                if current_combatant in self.player_team.combatants and not current_combatant.is_pet:
                    if random.random() < 0.25:  # 25% chance for betrayal illusion
                        partners = [c for c in self.player_team.combatants if not c.is_pet and c != current_combatant and c.is_alive()]
                        if partners:
                            partner = partners[0]
                            betrayal_illusions = [
                                f"💔 **BETRAYAL ILLUSION!** {current_combatant.name} sees a vision of {partner.name} walking away and leaving them behind!",
                                f"👻 **FALSE VISION!** {current_combatant.name} glimpses {partner.name} choosing someone else over them!",
                                f"😱 **WRAITH'S LIE!** {current_combatant.name} watches an illusion of {partner.name} giving up on their love!",
                                f"🌫️ **PHANTOM BETRAYAL!** {current_combatant.name} sees {partner.name} abandoning them in their darkest hour!"
                            ]
                            await self.add_to_log(random.choice(betrayal_illusions))
                            damage *= Decimal('0.75')  # Reduced damage due to emotional distraction
                
                target.take_damage(damage)
                message = f"{current_combatant.name} attacks! {target.name} takes **{self.format_number(damage)} HP** damage."
                
                # Add skill effect messages
                if skill_messages:
                    message += "\n" + "\n".join(skill_messages)
                if defender_messages:
                    message += "\n" + "\n".join(defender_messages)
            
            # Handle lifesteal if applicable
            if (self.config["class_buffs"] and 
                not current_combatant.is_pet and 
                hasattr(current_combatant, 'lifesteal_percent') and
                current_combatant.lifesteal_percent > 0):
                
                lifesteal_amount = (float(damage) * float(current_combatant.lifesteal_percent) / 100.0)
                current_combatant.heal(lifesteal_amount)
                message += f" Lifesteals: **{self.format_number(lifesteal_amount)} HP**"
            
            # Handle damage reflection if applicable
            reflection_value = float(getattr(target, 'damage_reflection', 0))
            
            # Apply tank evolution-based reflection if target has tank evolution
            if (self.config["class_buffs"] and 
                hasattr(target, 'tank_evolution') and target.tank_evolution and 
                not target.is_pet):
                # Use the standard tank evolution reflection multiplier from classes.py
                tank_reflection = 0.03 * target.tank_evolution  # 3% per level, so 21% at level 7
                reflection_value = max(float(reflection_value), tank_reflection)  # Use higher of item reflection or tank reflection
            
            if (self.config["reflection_damage"] and 
                reflection_value > 0 and 
                'blocked_damage' in locals() and blocked_damage > 0):
                
                # Calculate reflection as percentage of raw damage, capped at defender's armor
                reflection_base = min(raw_damage, target.armor)
                reflected = reflection_base * Decimal(str(reflection_value))
                current_combatant.take_damage(reflected)
                message += f"\n{target.name}'s armor reflects **{self.format_number(reflected)} HP** damage back!"
                
                if not current_combatant.is_alive():
                    message += f" {current_combatant.name} has been defeated by reflected damage!"
            
            # Check if target is defeated
            if not target.is_alive():
                # Check for cheat death ability for players
                if (self.config["class_buffs"] and 
                    self.config.get("cheat_death", True) and
                    not target.is_pet and 
                    target in self.player_team.combatants and  # Only player can cheat death
                    hasattr(target, 'death_cheat_chance') and target.death_cheat_chance > 0 and
                    not getattr(target, 'has_cheated_death', False)):
                    
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
            try:
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
            except (AttributeError, KeyError):
                pass  # Pet extension not available
        
        # Update the battle display
        await self.update_display()
        await asyncio.sleep(await self.get_turn_delay())
        
        return True

    async def process_turn_with_grudge_mechanics(self):
        """Process turn with Level 16 grudge mechanics - build grudges when taking damage, get damage boost + reckless friendly fire"""
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
        
        # Initialize reckless friendly fire flag for all code paths
        reckless_friendly_fire = False
            
        # Determine which team the combatant belongs to
        if current_combatant in self.player_team.combatants:
            # Player's turn, target the current enemy
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
            
            # *** LEVEL 16 GRUDGE RECKLESS CHECK BEFORE ATTACK ***
            if not current_combatant.is_pet:
                grudges = self.grudge_stacks.get(current_combatant.name, 0)
                if grudges > 0:
                    # Reckless chance: 5% per grudge (max 50% at 10 grudges)
                    reckless_chance = min(grudges * 0.05, 0.50)
                    if random.random() < reckless_chance:
                        partners = [c for c in self.player_team.combatants if not c.is_pet and c != current_combatant and c.is_alive()]
                        if partners:
                            friendly_fire_target = random.choice(partners)
                            target = friendly_fire_target
                            reckless_friendly_fire = True
                            await self.add_to_log(f"😡 **RECKLESS FURY!** {current_combatant.name}'s {grudges} grudges make them lash out at {target.name}!")
        else:
            # Enemy's turn, target a random player combatant
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
            hit_success = luck_roll <= current_combatant.luck
            
        # Initialize message variable
        message = ""
            
        if hit_success:
            # Attack hits
            
            # Special case for mage fireball
            used_fireball = False
            if (hasattr(current_combatant, 'mage_evolution') and current_combatant.mage_evolution and 
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
                
                from decimal import Decimal
                damage = (current_combatant.damage + Decimal(random.randint(0, 100)) - target.armor) * Decimal(str(damage_multiplier))
                damage = max(damage, Decimal('1'))
                
                # *** LEVEL 16 GRUDGE DAMAGE BOOST FOR FIREBALL ***
                if current_combatant in self.player_team.combatants and not current_combatant.is_pet:
                    grudges = self.grudge_stacks.get(current_combatant.name, 0)
                    if grudges > 0:
                        damage_boost = 1.0 + (grudges * 0.10)  # +10% per grudge
                        damage *= Decimal(str(damage_boost))
                        await self.add_to_log(f"😤 **GRUDGE FURY!** {current_combatant.name}'s {grudges} grudges boost their damage by {int((damage_boost - 1) * 100)}%!")
                
                target.take_damage(damage)
                
                # *** LEVEL 16 GRUDGE BUILDING WHEN TAKING DAMAGE ***
                if target in self.player_team.combatants and not target.is_pet and float(damage) > 0:
                    current_grudges = self.grudge_stacks.get(target.name, 0)
                    self.grudge_stacks[target.name] = current_grudges + 1
                    await self.add_to_log(f"🖤 {target.name} harbors another grudge! (Total: {current_grudges + 1})")
                
                if reckless_friendly_fire:
                    message = f"{current_combatant.name} casts Fireball in blind rage! {target.name} takes **{self.format_number(damage)} HP** damage from friendly fire!"
                else:
                    message = f"{current_combatant.name} casts Fireball! {target.name} takes **{self.format_number(damage)} HP** damage."
                used_fireball = True
            else:
                # Regular attack
                from decimal import Decimal
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
                    if element_mod != 0:
                        raw_damage = raw_damage * (1 + Decimal(str(element_mod)))
                
                # Add variance and apply armor
                raw_damage += Decimal(damage_variance)
                

                outcome = self.resolve_pet_attack_outcome(
                    current_combatant,
                    target,
                    raw_damage,
                    apply_element_mod=False,
                    damage_variance=0,
                    minimum_damage=Decimal('10'),
                )
                damage = outcome.final_damage
                blocked_damage = outcome.blocked_damage
                skill_messages = outcome.skill_messages
                defender_messages = outcome.defender_messages
                
                # *** LEVEL 16 GRUDGE DAMAGE BOOST FOR REGULAR ATTACKS ***
                if current_combatant in self.player_team.combatants and not current_combatant.is_pet:
                    grudges = self.grudge_stacks.get(current_combatant.name, 0)
                    if grudges > 0:
                        damage_boost = 1.0 + (grudges * 0.10)  # +10% per grudge
                        damage *= Decimal(str(damage_boost))
                        await self.add_to_log(f"😤 **GRUDGE FURY!** {current_combatant.name}'s {grudges} grudges boost their damage by {int((damage_boost - 1) * 100)}%!")
                
                target.take_damage(damage)
                
                # *** LEVEL 16 GRUDGE BUILDING WHEN TAKING DAMAGE ***
                if target in self.player_team.combatants and not target.is_pet and float(damage) > 0:
                    current_grudges = self.grudge_stacks.get(target.name, 0)
                    self.grudge_stacks[target.name] = current_grudges + 1
                    await self.add_to_log(f"🖤 {target.name} harbors another grudge! (Total: {current_grudges + 1})")
                
                if reckless_friendly_fire:
                    message = f"{current_combatant.name} attacks in blind rage! {target.name} takes **{self.format_number(damage)} HP** damage from friendly fire!"
                else:
                    message = f"{current_combatant.name} attacks! {target.name} takes **{self.format_number(damage)} HP** damage."
                
                # Add skill effect messages
                if skill_messages:
                    message += "\n" + "\n".join(skill_messages)
                if defender_messages:
                    message += "\n" + "\n".join(defender_messages)
            
            # Handle lifesteal if applicable
            if (self.config["class_buffs"] and 
                not current_combatant.is_pet and 
                hasattr(current_combatant, 'lifesteal_percent') and
                current_combatant.lifesteal_percent > 0):
                
                lifesteal_amount = (float(damage) * float(current_combatant.lifesteal_percent) / 100.0)
                current_combatant.heal(lifesteal_amount)
                message += f" Lifesteals: **{self.format_number(lifesteal_amount)} HP**"
            
            # Handle damage reflection if applicable
            reflection_value = float(getattr(target, 'damage_reflection', 0))
            
            # Apply tank evolution-based reflection if target has tank evolution
            if (self.config["class_buffs"] and 
                hasattr(target, 'tank_evolution') and target.tank_evolution and 
                not target.is_pet):
                # Use the standard tank evolution reflection multiplier from classes.py
                tank_reflection = 0.03 * target.tank_evolution  # 3% per level, so 21% at level 7
                reflection_value = max(float(reflection_value), tank_reflection)  # Use higher of item reflection or tank reflection
            
            if (self.config["reflection_damage"] and 
                reflection_value > 0 and 
                'blocked_damage' in locals() and blocked_damage > 0):
                
                # Calculate reflection as percentage of raw damage, capped at defender's armor
                reflection_base = min(raw_damage, target.armor)
                reflected = reflection_base * Decimal(str(reflection_value))
                current_combatant.take_damage(reflected)
                message += f"\n{target.name}'s armor reflects **{self.format_number(reflected)} HP** damage back!"
                
                if not current_combatant.is_alive():
                    message += f" {current_combatant.name} has been defeated by reflected damage!"
            
            # Check if target is defeated
            if not target.is_alive():
                # Check for cheat death ability for players
                if (self.config["class_buffs"] and 
                    self.config.get("cheat_death", True) and
                    not target.is_pet and 
                    target in self.player_team.combatants and  # Only player can cheat death
                    hasattr(target, 'death_cheat_chance') and target.death_cheat_chance > 0 and
                    not getattr(target, 'has_cheated_death', False)):
                    
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
            try:
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
            except (AttributeError, KeyError):
                pass  # Pet extension not available
        
        # Update the battle display
        await self.update_display()
        await asyncio.sleep(await self.get_turn_delay())
        
        return True

    async def process_turn_with_temptation_mechanics(self):
        """Process turn with Level 18 temptation mechanics - 30% chance for charm that reduces damage by 50%"""
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
        
        # Initialize temptation flag for all code paths
        is_tempted = False
            
        # Determine which team the combatant belongs to
        if current_combatant in self.player_team.combatants:
            # Player's turn, target the current enemy
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
            
            # *** LEVEL 18 TEMPTATION CHECK BEFORE ATTACK ***
            if not current_combatant.is_pet and random.random() < 0.30:  # 30% chance for temptation
                is_tempted = True
                await self.add_to_log(f"🌺 **TEMPTED!** {current_combatant.name} is lured by visions of an easier path! Their resolve wavers...")
        else:
            # Enemy's turn, target a random player combatant
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
            hit_success = luck_roll <= current_combatant.luck
            
        # Initialize message variable
        message = ""
            
        if hit_success:
            # Attack hits
            
            # Special case for mage fireball
            used_fireball = False
            if (hasattr(current_combatant, 'mage_evolution') and current_combatant.mage_evolution and 
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
                
                from decimal import Decimal
                damage = (current_combatant.damage + Decimal(random.randint(0, 100)) - target.armor) * Decimal(str(damage_multiplier))
                damage = max(damage, Decimal('1'))
                
                # *** LEVEL 18 TEMPTATION DAMAGE REDUCTION FOR FIREBALL ***
                if is_tempted:
                    original_damage = float(damage)
                    damage *= Decimal('0.5')  # 50% damage reduction when tempted
                    await self.add_to_log(f"💔 **DISTRACTED!** {current_combatant.name}'s temptation weakens their fireball! Damage reduced from {original_damage:.1f} to {float(damage):.1f}!")
                
                target.take_damage(damage)
                
                if is_tempted:
                    message = f"{current_combatant.name} casts a halfhearted Fireball while distracted by temptation! {target.name} takes **{self.format_number(damage)} HP** damage."
                else:
                    message = f"{current_combatant.name} casts Fireball! {target.name} takes **{self.format_number(damage)} HP** damage."
                used_fireball = True
            else:
                # Regular attack
                from decimal import Decimal
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
                    if element_mod != 0:
                        raw_damage = raw_damage * (1 + Decimal(str(element_mod)))
                
                # Add variance and apply armor
                raw_damage += Decimal(damage_variance)
                

                outcome = self.resolve_pet_attack_outcome(
                    current_combatant,
                    target,
                    raw_damage,
                    apply_element_mod=False,
                    damage_variance=0,
                    minimum_damage=Decimal('10'),
                )
                damage = outcome.final_damage
                blocked_damage = outcome.blocked_damage
                skill_messages = outcome.skill_messages
                defender_messages = outcome.defender_messages
                
                # *** LEVEL 18 TEMPTATION DAMAGE REDUCTION FOR REGULAR ATTACKS ***
                if is_tempted:
                    original_damage = float(damage)
                    damage *= Decimal('0.5')  # 50% damage reduction when tempted
                    await self.add_to_log(f"💔 **DISTRACTED!** {current_combatant.name}'s temptation weakens their attack! Damage reduced from {original_damage:.1f} to {float(damage):.1f}!")
                
                target.take_damage(damage)
                
                if is_tempted:
                    message = f"{current_combatant.name} attacks halfheartedly while distracted by temptation! {target.name} takes **{self.format_number(damage)} HP** damage."
                else:
                    message = f"{current_combatant.name} attacks! {target.name} takes **{self.format_number(damage)} HP** damage."
                
                # Add skill effect messages
                if skill_messages:
                    message += "\n" + "\n".join(skill_messages)
                if defender_messages:
                    message += "\n" + "\n".join(defender_messages)
            
            # Handle lifesteal if applicable
            if (self.config["class_buffs"] and 
                not current_combatant.is_pet and 
                hasattr(current_combatant, 'lifesteal_percent') and
                current_combatant.lifesteal_percent > 0):
                
                lifesteal_amount = (float(damage) * float(current_combatant.lifesteal_percent) / 100.0)
                current_combatant.heal(lifesteal_amount)
                message += f" Lifesteals: **{self.format_number(lifesteal_amount)} HP**"
            
            # Handle damage reflection if applicable
            reflection_value = float(getattr(target, 'damage_reflection', 0))
            
            # Apply tank evolution-based reflection if target has tank evolution
            if (self.config["class_buffs"] and 
                hasattr(target, 'tank_evolution') and target.tank_evolution and 
                not target.is_pet):
                # Use the standard tank evolution reflection multiplier from classes.py
                tank_reflection = 0.03 * target.tank_evolution  # 3% per level, so 21% at level 7
                reflection_value = max(float(reflection_value), tank_reflection)  # Use higher of item reflection or tank reflection
            
            if (self.config["reflection_damage"] and 
                reflection_value > 0 and 
                'blocked_damage' in locals() and blocked_damage > 0):
                
                # Calculate reflection as percentage of raw damage, capped at defender's armor
                reflection_base = min(raw_damage, target.armor)
                reflected = reflection_base * Decimal(str(reflection_value))
                current_combatant.take_damage(reflected)
                message += f"\n{target.name}'s armor reflects **{self.format_number(reflected)} HP** damage back!"
                
                if not current_combatant.is_alive():
                    message += f" {current_combatant.name} has been defeated by reflected damage!"
            
            # Check if target is defeated
            if not target.is_alive():
                # Check for cheat death ability for players
                if (self.config["class_buffs"] and 
                    self.config.get("cheat_death", True) and
                    not target.is_pet and 
                    target in self.player_team.combatants and  # Only player can cheat death
                    hasattr(target, 'death_cheat_chance') and target.death_cheat_chance > 0 and
                    not getattr(target, 'has_cheated_death', False)):
                    
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
            try:
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
            except (AttributeError, KeyError):
                pass  # Pet extension not available
        
        # Update the battle display
        await self.update_display()
        await asyncio.sleep(await self.get_turn_delay())
        
        return True

    async def process_turn_with_critical_hits(self):
        """Process turn with Level 19 critical hit mechanics - 25% chance for double damage criticals"""
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
        
        # Initialize critical hit flag for all code paths
        is_critical_hit = False
            
        # Determine which team the combatant belongs to
        if current_combatant in self.player_team.combatants:
            # Player's turn, target the current enemy
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
        
        # *** LEVEL 19 CRITICAL HIT CHECK BEFORE ATTACK ***
        if random.random() < 0.25:  # 25% chance for critical hit
            is_critical_hit = True
            await self.add_to_log(f"💥 **CRITICAL VULNERABILITY!** {current_combatant.name} strikes at {target.name}'s deepest insecurity!")
        
        # Process attack based on luck
        luck_roll = random.randint(1, 100)
        
        # For minions/bosses in enemy team, use 10% miss chance instead of luck-based
        if current_combatant in self.enemy_team.combatants:
            hit_success = random.random() > 0.10  # 10% chance to miss
        else:
            hit_success = luck_roll <= current_combatant.luck
            
        # Initialize message variable
        message = ""
            
        if hit_success:
            # Attack hits
            
            # Special case for mage fireball
            used_fireball = False
            if (hasattr(current_combatant, 'mage_evolution') and current_combatant.mage_evolution and 
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
                
                from decimal import Decimal
                damage = (current_combatant.damage + Decimal(random.randint(0, 100)) - target.armor) * Decimal(str(damage_multiplier))
                damage = max(damage, Decimal('1'))
                
                # *** LEVEL 19 CRITICAL HIT DAMAGE BOOST FOR FIREBALL ***
                if is_critical_hit:
                    original_damage = float(damage)
                    damage *= Decimal('2.0')  # Double damage on critical hit
                    await self.add_to_log(f"🎯 **DEVASTATING BLOW!** The critical fireball exploits {target.name}'s vulnerability! Damage doubled from {original_damage:.1f} to {float(damage):.1f}!")
                
                target.take_damage(damage)
                
                if is_critical_hit:
                    message = f"{current_combatant.name} casts a devastating critical Fireball that exploits {target.name}'s vulnerability! {target.name} takes **{self.format_number(damage)} HP** damage."
                else:
                    message = f"{current_combatant.name} casts Fireball! {target.name} takes **{self.format_number(damage)} HP** damage."
                used_fireball = True
            else:
                # Regular attack
                from decimal import Decimal
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
                    if element_mod != 0:
                        raw_damage = raw_damage * (1 + Decimal(str(element_mod)))
                
                # Add variance and apply armor
                raw_damage += Decimal(damage_variance)
                

                outcome = self.resolve_pet_attack_outcome(
                    current_combatant,
                    target,
                    raw_damage,
                    apply_element_mod=False,
                    damage_variance=0,
                    minimum_damage=Decimal('10'),
                )
                damage = outcome.final_damage
                blocked_damage = outcome.blocked_damage
                skill_messages = outcome.skill_messages
                defender_messages = outcome.defender_messages
                
                # *** LEVEL 19 CRITICAL HIT DAMAGE BOOST FOR REGULAR ATTACKS ***
                if is_critical_hit:
                    original_damage = float(damage)
                    damage *= Decimal('2.0')  # Double damage on critical hit
                    await self.add_to_log(f"🎯 **DEVASTATING BLOW!** The critical attack exploits {target.name}'s vulnerability! Damage doubled from {original_damage:.1f} to {float(damage):.1f}!")
                
                target.take_damage(damage)
                
                if is_critical_hit:
                    message = f"{current_combatant.name} strikes a devastating critical blow at {target.name}'s vulnerability! {target.name} takes **{self.format_number(damage)} HP** damage."
                else:
                    message = f"{current_combatant.name} attacks! {target.name} takes **{self.format_number(damage)} HP** damage."
                
                # Add skill effect messages
                if skill_messages:
                    message += "\n" + "\n".join(skill_messages)
                if defender_messages:
                    message += "\n" + "\n".join(defender_messages)
            
            # Handle lifesteal if applicable
            if (self.config["class_buffs"] and 
                not current_combatant.is_pet and 
                hasattr(current_combatant, 'lifesteal_percent') and
                current_combatant.lifesteal_percent > 0):
                
                lifesteal_amount = (float(damage) * float(current_combatant.lifesteal_percent) / 100.0)
                current_combatant.heal(lifesteal_amount)
                message += f" Lifesteals: **{self.format_number(lifesteal_amount)} HP**"
            
            # Handle damage reflection if applicable
            reflection_value = float(getattr(target, 'damage_reflection', 0))
            
            # Apply tank evolution-based reflection if target has tank evolution
            if (self.config["class_buffs"] and 
                hasattr(target, 'tank_evolution') and target.tank_evolution and 
                not target.is_pet):
                # Use the standard tank evolution reflection multiplier from classes.py
                tank_reflection = 0.03 * target.tank_evolution  # 3% per level, so 21% at level 7
                reflection_value = max(float(reflection_value), tank_reflection)  # Use higher of item reflection or tank reflection
            
            if (self.config["reflection_damage"] and 
                reflection_value > 0 and 
                'blocked_damage' in locals() and blocked_damage > 0):
                
                # Calculate reflection as percentage of raw damage, capped at defender's armor
                reflection_base = min(raw_damage, target.armor)
                reflected = reflection_base * Decimal(str(reflection_value))
                current_combatant.take_damage(reflected)
                message += f"\n{target.name}'s armor reflects **{self.format_number(reflected)} HP** damage back!"
                
                if not current_combatant.is_alive():
                    message += f" {current_combatant.name} has been defeated by reflected damage!"
            
            # Check if target is defeated
            if not target.is_alive():
                # Check for cheat death ability for players
                if (self.config["class_buffs"] and 
                    self.config.get("cheat_death", True) and
                    not target.is_pet and 
                    target in self.player_team.combatants and  # Only player can cheat death
                    hasattr(target, 'death_cheat_chance') and target.death_cheat_chance > 0 and
                    not getattr(target, 'has_cheated_death', False)):
                    
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
            try:
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
            except (AttributeError, KeyError):
                pass  # Pet extension not available
        
        # Update the battle display
        await self.update_display()
        await asyncio.sleep(await self.get_turn_delay())
        
        return True

    async def process_turn_with_despair_mechanics(self):
        """Process turn with Level 22 despair mechanics - full turn processing with despair effects"""
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
        
        # Level 22: Check for partner encouragement (only when despair is high and not used recently)
        if (current_combatant in self.player_team.combatants and not current_combatant.is_pet and
            current_combatant.user.id not in self.encouragement_used):
            
            partners = [c for c in self.player_team.combatants if not c.is_pet and c != current_combatant and c.is_alive()]
            for partner in partners:
                partner_despair = self.despair_stacks.get(partner.name, 0)
                # Only encourage when partner has significant despair (5+) and 20% chance
                if partner_despair >= 5 and random.random() < 0.20:
                    await self.partner_encouragement(current_combatant, partner)
                    self.encouragement_used.add(current_combatant.user.id)
                    await asyncio.sleep(1)  # Brief pause for encouragement
                    break
        
        # Determine which team the combatant belongs to
        if current_combatant in self.player_team.combatants:
            # Player's turn, target the current enemy
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
        
        # Process attack based on luck (modified by despair for players)
        luck_roll = random.randint(1, 100)
        
        # For minions/bosses in enemy team, use 10% miss chance instead of luck-based
        if current_combatant in self.enemy_team.combatants:
            hit_success = random.random() > 0.10  # 10% chance to miss
        else:
            # Level 22: Apply despair accuracy modifier to player attacks
            despair_accuracy_mod = await self.get_despair_accuracy_modifier(current_combatant)
            modified_luck = float(current_combatant.luck) * despair_accuracy_mod
            hit_success = luck_roll <= modified_luck
            
            if despair_accuracy_mod < 1.0:
                await self.add_to_log(f"😞 {current_combatant.name}'s despair clouds their focus... (accuracy reduced to {modified_luck:.1f})")
            
        # Initialize message variable and tracking flags
        message = ""
        hope_gained = False
            
        if hit_success:
            # Attack hits
            
            # Special case for mage fireball
            used_fireball = False
            if (hasattr(current_combatant, 'mage_evolution') and current_combatant.mage_evolution and 
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
                
                from decimal import Decimal
                damage = (current_combatant.damage + Decimal(random.randint(0, 100)) - target.armor) * Decimal(str(damage_multiplier))
                damage = max(damage, Decimal('1'))
                
                # Level 22: Apply despair damage modifier to player fireballs
                if current_combatant in self.player_team.combatants:
                    despair_damage_mod = await self.get_despair_damage_modifier(current_combatant)
                    if despair_damage_mod < 1.0:
                        original_damage = float(damage)
                        damage *= Decimal(str(despair_damage_mod))
                        await self.add_to_log(f"💔 {current_combatant.name}'s despair weakens their fireball! Damage reduced from {original_damage:.1f} to {float(damage):.1f}")
                
                target.take_damage(damage)
                message = f"{current_combatant.name} casts Fireball! {target.name} takes **{self.format_number(damage)} HP** damage."
                used_fireball = True
            else:
                # Regular attack
                from decimal import Decimal
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
                    if element_mod != 0:
                        raw_damage = raw_damage * (1 + Decimal(str(element_mod)))
                
                # Add variance and apply armor
                raw_damage += Decimal(damage_variance)
                

                outcome = self.resolve_pet_attack_outcome(
                    current_combatant,
                    target,
                    raw_damage,
                    apply_element_mod=False,
                    damage_variance=0,
                    minimum_damage=Decimal('10'),
                )
                damage = outcome.final_damage
                blocked_damage = outcome.blocked_damage
                skill_messages = outcome.skill_messages
                defender_messages = outcome.defender_messages
                
                # Level 22: Apply despair damage modifier to player attacks
                if current_combatant in self.player_team.combatants:
                    despair_damage_mod = await self.get_despair_damage_modifier(current_combatant)
                    if despair_damage_mod < 1.0:
                        original_damage = float(damage)
                        damage *= Decimal(str(despair_damage_mod))
                        await self.add_to_log(f"💔 {current_combatant.name}'s despair weakens their attack! Damage reduced from {original_damage:.1f} to {float(damage):.1f}")
                
                target.take_damage(damage)
                message = f"{current_combatant.name} attacks! {target.name} takes **{self.format_number(damage)} HP** damage."
                
                # Add skill effect messages
                if skill_messages:
                    message += "\n" + "\n".join(skill_messages)
                if defender_messages:
                    message += "\n" + "\n".join(defender_messages)
            
            # Level 22: Successful attacks reduce despair slightly (hope from success)
            if current_combatant in self.player_team.combatants and not current_combatant.is_pet:
                current_despair = self.despair_stacks.get(current_combatant.name, 0)
                if current_despair > 0 and random.random() < 0.20:  # 20% chance to reduce despair on hit
                    self.despair_stacks[current_combatant.name] = max(0, current_despair - 1)
                    hope_gained = True
            
            # Handle lifesteal if applicable
            if (self.config["class_buffs"] and 
                not current_combatant.is_pet and 
                hasattr(current_combatant, 'lifesteal_percent') and
                current_combatant.lifesteal_percent > 0):
                
                lifesteal_amount = (float(damage) * float(current_combatant.lifesteal_percent) / 100.0)
                current_combatant.heal(lifesteal_amount)
                message += f" Lifesteals: **{self.format_number(lifesteal_amount)} HP**"
            
            # Handle damage reflection if applicable
            reflection_value = float(getattr(target, 'damage_reflection', 0))
            
            # Apply tank evolution-based reflection if target has tank evolution
            if (self.config["class_buffs"] and 
                hasattr(target, 'tank_evolution') and target.tank_evolution and 
                not target.is_pet):
                # Use the standard tank evolution reflection multiplier from classes.py
                tank_reflection = 0.03 * target.tank_evolution  # 3% per level, so 21% at level 7
                reflection_value = max(float(reflection_value), tank_reflection)  # Use higher of item reflection or tank reflection
            
            if (self.config["reflection_damage"] and 
                reflection_value > 0 and 
                'blocked_damage' in locals() and blocked_damage > 0):
                
                # Calculate reflection as percentage of raw damage, capped at defender's armor
                reflection_base = min(raw_damage, target.armor)
                reflected = reflection_base * Decimal(str(reflection_value))
                current_combatant.take_damage(reflected)
                message += f"\n{target.name}'s armor reflects **{self.format_number(reflected)} HP** damage back!"
                
                if not current_combatant.is_alive():
                    message += f" {current_combatant.name} has been defeated by reflected damage!"
            
            # Check if target is defeated
            if not target.is_alive():
                # Check for cheat death ability for players
                if (self.config["class_buffs"] and 
                    self.config.get("cheat_death", True) and
                    not target.is_pet and 
                    target in self.player_team.combatants and  # Only player can cheat death
                    hasattr(target, 'death_cheat_chance') and target.death_cheat_chance > 0 and
                    not getattr(target, 'has_cheated_death', False)):
                    
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
                
                # Level 22: Missing attacks increases despair (frustration and hopelessness)
                if current_combatant in self.player_team.combatants and not current_combatant.is_pet:
                    gained = await self.apply_despair_effects(current_combatant, 1, "missed attack", show_message=False)
                    if gained > 0:
                        message += f" 😞 Frustration clouds their mind. (+{gained} despair)"
        
        # Level 22: Process all despair effects and consolidate messaging
        despair_messages = []
        total_despair_gained = 0
        
        # Taking damage increases despair
        if (hit_success and 'damage' in locals() and hasattr(target, 'is_alive') and 
            target in self.player_team.combatants and not target.is_pet):
            despair_from_damage = 1 if float(damage) < 50 else 2
            gained = await self.apply_despair_effects(target, despair_from_damage, "taking damage", show_message=False)
            total_despair_gained += gained
            
        # Despair Wraith special psychological attack
        if (current_combatant in self.enemy_team.combatants and "Despair Wraith" in current_combatant.name and 
            hit_success and target in self.player_team.combatants and not target.is_pet):
            if random.random() < 0.30:  # Reduced to 30% to be less spammy
                gained = await self.apply_despair_effects(target, 1, "wraith whispers", show_message=False)
                total_despair_gained += gained
                despair_whispers = [
                    f"👻 The wraith whispers doubts into {target.name}'s mind...",
                    f"🌫️ Dark thoughts cloud {target.name}'s spirit...",
                    f"😞 Hopelessness seeps into {target.name}'s heart..."
                ]
                despair_messages.append(random.choice(despair_whispers))
                
        # Missing attacks increases despair (handled elsewhere)
        
        # Combine attack message with any despair/hope effects
        effects = []
        if despair_messages and total_despair_gained > 0:
            effects.append(f"{despair_messages[0]} (+{total_despair_gained} despair)")
        if hope_gained:
            effects.append(f"✨ Success brings hope! (-1 despair)")
            
        if effects:
            message += f"\n{effects[0]}"
            if len(effects) > 1:
                message += f" | {effects[1]}"
        
        # Add message to battle log - use a new action number for each combat action
        await self.add_to_log(message, force_new_action=True)
        
        # PROCESS PET SKILL EFFECTS PER TURN
        if hasattr(self.ctx.bot.cogs["Battles"], "battle_factory"):
            try:
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
            except (AttributeError, KeyError):
                pass  # Pet extension not available
        
        # Reset encouragement tracking each round
        if self.current_turn % len(self.turn_order) == 0:
            self.encouragement_used.clear()
        
        # Update the battle display
        await self.update_display()
        await asyncio.sleep(await self.get_turn_delay())
        
        return True

    async def process_turn_with_fear_mechanics(self):
        """Process turn with Level 25 fear paralysis mechanics"""
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
        
        # Level 25: Fear paralysis check - 30% chance to be too terrified to act
        # Fear Incarnate is immune to fear effects (it embodies fear itself)
        if "Fear Incarnate" not in current_combatant.name and random.random() < 0.30:
            await self.add_to_log(f"😨 **PARALYZED BY FEAR!** {current_combatant.name} cowers in terror and cannot act!", force_new_action=True)
            await self.update_display()
            await asyncio.sleep(await self.get_turn_delay())
            return True
        elif "Fear Incarnate" in current_combatant.name:
            # Show immunity message occasionally (10% chance to avoid spam)
            if random.random() < 0.10:
                await self.add_to_log(f"👹 **FEAR IMMUNITY!** {current_combatant.name} embodies terror itself and cannot be frightened!")
        
        # If not paralyzed by fear, use normal turn processing
        return await super().process_turn()

    async def process_turn_with_pain_mechanics(self):
        """Process turn with Level 26 pain fury mechanics - suffering builds damage bonuses"""
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
            hit_success = luck_roll <= current_combatant.luck
            
        # Initialize message variable
        message = ""
            
        if hit_success:
            # Attack hits
            
            # Special case for mage fireball
            used_fireball = False
            if (hasattr(current_combatant, 'mage_evolution') and current_combatant.mage_evolution and 
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
                
                from decimal import Decimal
                damage = (current_combatant.damage + Decimal(random.randint(0, 100)) - target.armor) * Decimal(str(damage_multiplier))
                damage = max(damage, Decimal('1'))
                
                # *** LEVEL 26 PAIN FURY DAMAGE BOOST FOR FIREBALL ***
                pain_bonus = self.pain_damage_bonuses.get(current_combatant.name, 0)
                if pain_bonus > 0:
                    original_damage = float(damage)
                    damage_boost = 1.0 + (pain_bonus / 100.0)  # Convert percentage to multiplier
                    damage *= Decimal(str(damage_boost))
                    await self.add_to_log(f"💢 **PAIN FURY!** {current_combatant.name}'s suffering fuels their fireball! (+{pain_bonus:.0f}% damage)")
                
                # Store original damage before taking it
                damage_taken = float(damage)
                target.take_damage(damage)
                
                # *** LEVEL 26 PAIN ACCUMULATION FOR TARGET ***
                await self.apply_pain_bonuses(target, damage_taken)
                
                message = f"{current_combatant.name} casts Fireball! {target.name} takes **{self.format_number(damage)} HP** damage."
                used_fireball = True
            else:
                # Regular attack
                from decimal import Decimal
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
                    if element_mod != 0:
                        raw_damage = raw_damage * (1 + Decimal(str(element_mod)))
                
                # Add variance and apply armor
                raw_damage += Decimal(damage_variance)
                

                outcome = self.resolve_pet_attack_outcome(
                    current_combatant,
                    target,
                    raw_damage,
                    apply_element_mod=False,
                    damage_variance=0,
                    minimum_damage=Decimal('10'),
                )
                damage = outcome.final_damage
                blocked_damage = outcome.blocked_damage
                skill_messages = outcome.skill_messages
                defender_messages = outcome.defender_messages
                
                # *** LEVEL 26 PAIN FURY DAMAGE BOOST FOR REGULAR ATTACKS ***
                pain_bonus = self.pain_damage_bonuses.get(current_combatant.name, 0)
                if pain_bonus > 0:
                    original_damage = float(damage)
                    damage_boost = 1.0 + (pain_bonus / 100.0)  # Convert percentage to multiplier
                    damage *= Decimal(str(damage_boost))
                    await self.add_to_log(f"💢 **PAIN FURY!** {current_combatant.name}'s suffering fuels their rage! (+{pain_bonus:.0f}% damage)")
                
                # Store damage before taking it
                damage_taken = float(damage)
                target.take_damage(damage)
                
                # *** LEVEL 26 PAIN ACCUMULATION FOR TARGET ***
                await self.apply_pain_bonuses(target, damage_taken)
                
                message = f"{current_combatant.name} attacks! {target.name} takes **{self.format_number(damage)} HP** damage."
                
                # Add skill effect messages
                if skill_messages:
                    message += "\n" + "\n".join(skill_messages)
                if defender_messages:
                    message += "\n" + "\n".join(defender_messages)
            
            # Handle lifesteal if applicable
            if (self.config["class_buffs"] and 
                not current_combatant.is_pet and 
                hasattr(current_combatant, 'lifesteal_percent') and
                current_combatant.lifesteal_percent > 0):
                
                lifesteal_amount = (float(damage) * float(current_combatant.lifesteal_percent) / 100.0)
                current_combatant.heal(lifesteal_amount)
                message += f" Lifesteals: **{self.format_number(lifesteal_amount)} HP**"
            
            # Handle damage reflection if applicable
            reflection_value = float(getattr(target, 'damage_reflection', 0))
            
            # Apply tank evolution-based reflection if target has tank evolution
            if (self.config["class_buffs"] and 
                hasattr(target, 'tank_evolution') and target.tank_evolution and 
                not target.is_pet):
                # Use the standard tank evolution reflection multiplier from classes.py
                tank_reflection = 0.03 * target.tank_evolution  # 3% per level, so 21% at level 7
                reflection_value = max(float(reflection_value), tank_reflection)  # Use higher of item reflection or tank reflection
            
            if (self.config["reflection_damage"] and 
                reflection_value > 0 and 
                'blocked_damage' in locals() and blocked_damage > 0):
                
                # Calculate reflection as percentage of raw damage, capped at defender's armor
                reflection_base = min(raw_damage, target.armor)
                reflected = reflection_base * Decimal(str(reflection_value))
                
                # Store reflected damage for pain application
                reflected_damage = float(reflected)
                current_combatant.take_damage(reflected)
                
                # *** LEVEL 26 PAIN ACCUMULATION FOR REFLECTED DAMAGE ***
                await self.apply_pain_bonuses(current_combatant, reflected_damage)
                
                message += f"\n{target.name}'s armor reflects **{self.format_number(reflected)} HP** damage back!"
                
                if not current_combatant.is_alive():
                    message += f" {current_combatant.name} has been defeated by reflected damage!"
            
            # Check if target is defeated
            if not target.is_alive():
                # Check for cheat death ability for players
                if (self.config["class_buffs"] and 
                    self.config.get("cheat_death", True) and
                    not target.is_pet and 
                    target in self.player_team.combatants and  # Only player can cheat death
                    hasattr(target, 'death_cheat_chance') and target.death_cheat_chance > 0 and
                    not getattr(target, 'has_cheated_death', False)):
                    
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
                damage_taken = float(damage)
                current_combatant.take_damage(damage)
                
                # *** LEVEL 26 PAIN ACCUMULATION FOR TRIP DAMAGE ***
                await self.apply_pain_bonuses(current_combatant, damage_taken)
                
                message = f"{current_combatant.name} tripped and took **{self.format_number(damage)} HP** damage. Bad luck!"
            else:
                message = f"{current_combatant.name}'s attack missed!"
        
        # Add message to battle log - use a new action number for each combat action
        await self.add_to_log(message, force_new_action=True)
        
        # PROCESS PET SKILL EFFECTS PER TURN
        if hasattr(self.ctx.bot.cogs["Battles"], "battle_factory"):
            try:
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
            except (AttributeError, KeyError):
                pass  # Pet extension not available
        
        # Update the battle display
        await self.update_display()
        await asyncio.sleep(await self.get_turn_delay())
        
        return True

    async def apply_pain_bonuses(self, combatant, damage_taken):
        """Level 26: Apply pain bonuses based on damage taken"""
        if damage_taken <= 0:
            return
            
        # Calculate pain bonus based on damage taken
        # Each 25 damage = 1% damage bonus (so 250 damage = 10% bonus)
        pain_gain = damage_taken / 25.0
        
        current_pain = self.pain_damage_bonuses.get(combatant.name, 0)
        new_pain = min(current_pain + pain_gain, 50.0)  # Cap at 50% bonus
        self.pain_damage_bonuses[combatant.name] = new_pain
        
        # Show pain accumulation message for significant gains
        if pain_gain >= 1.0:  # Only show for 1%+ gains to avoid spam
            pain_gained = new_pain - current_pain
            pain_messages = [
                f"💢 {combatant.name} channels their pain into fury! (+{pain_gained:.1f}% damage)",
                f"😤 {combatant.name}'s suffering builds into rage! (+{pain_gained:.1f}% damage)",
                f"🔥 {combatant.name} transforms agony into power! (+{pain_gained:.1f}% damage)",
                f"⚡ {combatant.name}'s pain becomes their strength! (+{pain_gained:.1f}% damage)"
            ]
            
            # Show milestone messages
            if new_pain >= 40 and current_pain < 40:
                await self.add_to_log(f"🌋 **OVERWHELMING FURY!** {combatant.name} is consumed by pain-fueled rage!")
            elif new_pain >= 25 and current_pain < 25:
                await self.add_to_log(f"🔥 **BURNING RAGE!** {combatant.name}'s pain has ignited into deadly fury!")
            elif new_pain >= 10 and current_pain < 10:
                await self.add_to_log(f"💢 **RISING FURY!** {combatant.name}'s pain begins to fuel their strength!")
            elif pain_gained >= 1.0:
                await self.add_to_log(random.choice(pain_messages))

    async def process_turn_with_growth_mechanics(self):
        """Process turn with Level 28 protective growth mechanics"""
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
            
        # Level 28: Check for growth opportunities at start of turn
        await self.check_growth_opportunities()
        
        # Use normal turn processing with protective shielding (blocking logic is handled there)
        return await self.process_turn_with_protective_shielding()

    async def process_turn_with_protective_shielding(self):
        """Process turn with Level 28 HP-based protective shielding mechanics"""
        # Handle pending enemy transitions as a separate action
        if self.pending_enemy_transition:
            return await self.handle_enemy_transition()
            
        if await self.is_battle_over():
            return False
            
        # Get current combatant
        if not self.turn_order:
            self.update_turn_order()
            
        # Level 28: Find next combatant that can act
        max_attempts = len(self.turn_order)  # Prevent infinite loop
        attempts = 0
        
        while attempts < max_attempts:
            current_combatant = self.turn_order[self.current_turn % len(self.turn_order)]
            self.current_turn += 1
            attempts += 1
            
            # Skip dead combatants
            if not current_combatant.is_alive():
                continue
                
            # Level 28: Check if player attacking final enemy when not vulnerable
            if (current_combatant in self.player_team.combatants and not self.final_enemy_vulnerable):
                # Check if this is the final enemy
                if self.current_opponent_index == len(self.enemy_team.combatants) - 1:
                    await self.add_to_log(f"🛡️ **SEALED BY COMPLACENCY!** {current_combatant.name} cannot harm the final enemy until your garden blooms with {self.growth_required - self.growth_points} more flowers!", force_new_action=True)
                    await self.update_display()
                    await asyncio.sleep(await self.get_turn_delay())
                    continue  # Skip this player and try next combatant
            
            # Found a combatant that can act
            break
        
        if attempts >= max_attempts:
            # All combatants were skipped - this shouldn't happen normally
            return True
            
        # Determine which team the combatant belongs to
        if current_combatant in self.player_team.combatants:
            # Player's turn, target the current enemy
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
            hit_success = luck_roll <= current_combatant.luck
            
        # Initialize message variable
        message = ""
            
        if hit_success:
            # Attack hits - process damage with protective shielding
            from decimal import Decimal
            damage_variance = random.randint(0, 50) if current_combatant.is_pet else random.randint(0, 100)
            
            # Start with base damage
            raw_damage = current_combatant.damage + Decimal(damage_variance)
            
            # Apply armor
            damage = max(raw_damage - target.armor, Decimal('10'))  # Minimum 10 damage
            
            # Level 28: Apply protective shielding if target is a partner being attacked
            shielding_occurred = False
            if target in self.player_team.combatants and not target.is_pet:
                partners = [c for c in self.player_team.combatants if not c.is_pet and c.is_alive()]
                if len(partners) >= 2:
                    # Find the partner who isn't the target
                    shielding_partner = partners[0] if partners[1] == target else partners[1]
                    
                    # Check if shielding partner has 10% or more HP than target
                    shield_hp_percent = float(shielding_partner.hp) / float(shielding_partner.max_hp)
                    target_hp_percent = float(target.hp) / float(target.max_hp)
                    
                    if shield_hp_percent >= target_hp_percent + 0.10:  # 10% more HP
                        # Check for Stagnation Spirit interference
                        if random.random() < 0.15:  # 15% chance for selfishness
                            await self.add_to_log(f"🥀 **SELFISHNESS WHISPER!** '{shielding_partner.name}, why sacrifice for them? Save your strength!' - A flower wilts as selfish thoughts take hold...")
                        else:
                            # Successful shielding
                            shielding_occurred = True
                            shield_damage = damage * Decimal('0.75')  # Shielder takes 75%
                            target_damage = damage * Decimal('0.25')   # Target takes 25%
                            
                            # Apply damage
                            shielding_partner.take_damage(shield_damage)
                            target.take_damage(target_damage)
                            
                            # Award growth point
                            self.growth_points += 1
                            
                            message = f"🛡️ **PROTECTIVE GROWTH!** {shielding_partner.name} shields {target.name} from {current_combatant.name}'s attack! {shielding_partner.name} takes **{self.format_number(shield_damage)} HP** damage, {target.name} takes **{self.format_number(target_damage)} HP** damage."
                            
                            # Check for growth completion
                            if self.growth_points >= self.growth_required and not self.final_enemy_vulnerable:
                                self.final_enemy_vulnerable = True
                                await self.add_to_log(f"🌸 **GARDEN IN FULL BLOOM!** Your {self.growth_points} acts of protection have unlocked the final enemy!", force_new_action=True)
                            else:
                                await self.add_to_log(f"🌻 **FLOWER BLOOMS!** Your garden grows! ({self.growth_points}/{self.growth_required} flowers bloomed)")
            
            # If no shielding occurred, apply normal damage
            if not shielding_occurred:
                target.take_damage(damage)
                message = f"{current_combatant.name} attacks! {target.name} takes **{self.format_number(damage)} HP** damage."
            
            # Check if target is defeated
            if not target.is_alive():
                message += f" {target.name} has been defeated!"
                
                # Level 28: Award growth point for defeating non-final enemies together
                if (target in self.enemy_team.combatants and 
                    self.current_opponent_index < len(self.enemy_team.combatants) - 1):  # Not final enemy
                    self.growth_points += 1
                    await self.add_to_log(f"🌻 **TEAMWORK GROWTH!** Working together to defeat {target.name} strengthens your bond! ({self.growth_points}/{self.growth_required} flowers bloomed)")
                    
                    # Check for growth completion
                    if self.growth_points >= self.growth_required and not self.final_enemy_vulnerable:
                        self.final_enemy_vulnerable = True
                        await self.add_to_log(f"🌸 **GARDEN IN FULL BLOOM!** Your {self.growth_points} acts of love have unlocked the final enemy!", force_new_action=True)
                
                # If defeated enemy, check if we should move to next one
                if target in self.enemy_team.combatants:
                    if target == self.enemy_team.combatants[self.current_opponent_index]:
                        # Schedule the transition to next enemy as a separate action
                        if self.current_opponent_index < len(self.enemy_team.combatants) - 1:
                            self.pending_enemy_transition = True
                            self.transition_state = 1  # Start at phase 1 (intro)
        else:
            # Attack misses
            message = f"{current_combatant.name}'s attack missed!"
        
        # Add message to battle log
        await self.add_to_log(message, force_new_action=True)
        
        # Update the battle display
        await self.update_display()
        await asyncio.sleep(await self.get_turn_delay())
        
        return True

    async def process_turn_with_spirit_healing(self):
        """Process turn with Level 29 spirit healing mechanics - dead partners can heal living ones"""
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
        
        # Skip dead combatants (unless they're a partner who can spirit heal)
        if not current_combatant.is_alive():
            # Level 29: Dead partners can still act as spirits to heal
            partners = [c for c in self.player_team.combatants if not c.is_pet]
            if current_combatant in partners:
                # Dead partner becomes a spirit healer
                return await self.process_spirit_healing_turn(current_combatant)
            else:
                # Dead non-partners (pets, enemies) are skipped normally
                return True
            
        # Determine which team the combatant belongs to
        if current_combatant in self.player_team.combatants:
            # Player's turn, target the current enemy
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
            # Enemy's turn, target a random player combatant (including living ones only)
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
        
        # Use normal attack processing
        return await self.process_normal_attack(current_combatant, target)
    
    async def process_spirit_healing_turn(self, spirit_partner):
        """Process a spirit healing turn for a dead partner"""
        partners = [c for c in self.player_team.combatants if not c.is_pet]
        living_partner = None
        
        # Find the living partner to heal
        for partner in partners:
            if partner != spirit_partner and partner.is_alive():
                living_partner = partner
                break
        
        if not living_partner:
            # No living partner to heal
            await self.add_to_log(f"👻 {spirit_partner.name}'s spirit fades... there is no one left to heal.", force_new_action=True)
            return True
        
        # Spirit healing mechanics
        if random.random() < 0.80:  # 80% chance for spirit to successfully heal
            from decimal import Decimal
            
            # Heal based on spirit's original stats (15-25% of max HP)
            heal_percent = random.uniform(0.15, 0.25)
            heal_amount = living_partner.max_hp * Decimal(str(heal_percent))
            
            # Apply healing
            old_hp = float(living_partner.hp)
            living_partner.heal(heal_amount)
            new_hp = float(living_partner.hp)
            actual_heal = new_hp - old_hp
            
            # Spirit healing messages
            spirit_messages = [
                f"👻 **SPIRIT'S LOVE!** {spirit_partner.name}'s spirit wraps {living_partner.name} in ethereal warmth!",
                f"✨ **ETERNAL BOND!** {spirit_partner.name} channels love from beyond to heal {living_partner.name}!",
                f"💙 **GHOSTLY GRACE!** {spirit_partner.name}'s spirit whispers strength into {living_partner.name}!",
                f"🌟 **LOVE TRANSCENDENT!** {spirit_partner.name} proves love survives even death!"
            ]
            
            message = f"{random.choice(spirit_messages)} {living_partner.name} heals **{self.format_number(actual_heal)} HP**!"
            await self.add_to_log(message, force_new_action=True)
            
            # Show encouraging message occasionally
            if random.random() < 0.30:
                encouragement = [
                    f"👻 '{living_partner.name}, I'm still with you... don't give up!'",
                    f"✨ '{living_partner.name}, our love is stronger than death itself!'",
                    f"💕 '{living_partner.name}, fight on for both of us!'",
                    f"🌟 '{living_partner.name}, I'll always be by your side...'"
                ]
                await self.add_to_log(random.choice(encouragement))
        else:
            # Spirit healing failed
            fail_messages = [
                f"👻 {spirit_partner.name}'s spirit flickers weakly... the healing fails.",
                f"💨 {spirit_partner.name}'s ethereal form wavers and cannot reach {living_partner.name}.",
                f"🌫️ {spirit_partner.name}'s spirit is too faint to provide healing.",
                f"😞 {spirit_partner.name}'s spirit struggles but cannot manifest its power."
            ]
            await self.add_to_log(random.choice(fail_messages), force_new_action=True)
        
        # Update the battle display
        await self.update_display()
        await asyncio.sleep(await self.get_turn_delay())
        
        return True
    
    async def process_normal_attack(self, attacker, target):
        """Process a normal attack for Level 29"""
        # Process attack based on luck
        luck_roll = random.randint(1, 100)
        
        # For minions/bosses in enemy team, use 10% miss chance instead of luck-based
        if attacker in self.enemy_team.combatants:
            hit_success = random.random() > 0.10  # 10% chance to miss
        else:
            hit_success = luck_roll <= attacker.luck
            
        # Initialize message variable
        message = ""
            
        if hit_success:
            # Attack hits - calculate damage
            from decimal import Decimal
            damage_variance = random.randint(0, 50) if attacker.is_pet else random.randint(0, 100)
            
            # Start with base damage
            raw_damage = attacker.damage + Decimal(damage_variance)
            
            # Apply armor
            damage = max(raw_damage - target.armor, Decimal('10'))  # Minimum 10 damage
            
            target.take_damage(damage)
            message = f"{attacker.name} attacks! {target.name} takes **{self.format_number(damage)} HP** damage."
            
            # Check if target is defeated
            if not target.is_alive():
                message += f" {target.name} has been defeated!"
                
                # If partner died, they become a spirit
                partners = [c for c in self.player_team.combatants if not c.is_pet]
                if target in partners:
                    message += f"\n👻 **SPIRIT TRANSFORMATION!** {target.name} becomes a spirit and can still heal their beloved!"
                
                # If defeated enemy, check if we should move to next one
                if target in self.enemy_team.combatants:
                    if target == self.enemy_team.combatants[self.current_opponent_index]:
                        # Schedule the transition to next enemy as a separate action
                        if self.current_opponent_index < len(self.enemy_team.combatants) - 1:
                            self.pending_enemy_transition = True
                            self.transition_state = 1  # Start at phase 1 (intro)
        else:
            # Attack misses
            message = f"{attacker.name}'s attack missed!"
        
        # Add message to battle log
        await self.add_to_log(message, force_new_action=True)
        
        # Update the battle display
        await self.update_display()
        await asyncio.sleep(await self.get_turn_delay())
        
        return True

    async def process_turn_with_possession_mechanics(self):
        """Process turn with Level 23 Mirror of Truth possession mechanics"""
        if await self.is_battle_over():
            return False
            
        # Increment possession turn counter
        self.possession_turns += 1
        
        # Check if possession duration is over
        if self.possession_turns >= self.possession_turn_limit:
            # Immediately kill Truth Demon and trigger victory
            if self.truth_demon and self.truth_demon.is_alive():
                self.truth_demon.take_damage(self.truth_demon.hp)
            await self.end_possession_victory()
            return False
        
        # Get current combatant - only the possessed partner can act
        if not self.turn_order:
            # For Level 23, turn order is just the possessed partner
            self.turn_order = [self.possessed_partner]
            
        current_combatant = self.possessed_partner
        
        # Skip if possessed partner is dead
        if not current_combatant.is_alive():
            await self.add_to_log(f"💔 {self.possessed_partner.name} has fallen! The possession breaks, but love has been lost...")
            self.finished = True
            return False
            
        # Skip if defender is dead
        if not self.defender_partner.is_alive():
            await self.add_to_log(f"💔 {self.defender_partner.name} could not survive their beloved's possessed assault...")
            self.finished = True
            return False
        
        target = self.defender_partner
        
        # Show possession struggle message occasionally
        if self.possession_turns % 4 == 0:  # Every 4 turns
            struggle_messages = [
                f"😖 {self.possessed_partner.name} fights against the demon's control!",
                f"💪 {self.possessed_partner.name} struggles to break free!",
                f"😣 {self.possessed_partner.name} tries to resist the possession!",
                f"💔 {self.possessed_partner.name} fights the urge to harm their love!"
            ]
            await self.add_to_log(random.choice(struggle_messages))
        
        # Process attack based on luck
        luck_roll = random.randint(1, 100)
        hit_success = luck_roll <= current_combatant.luck
            
        # Initialize message variable
        message = ""
            
        if hit_success:
            # Attack hits
            from decimal import Decimal
            damage_variance = random.randint(0, 100)
            
            # Start with base damage
            raw_damage = current_combatant.damage + Decimal(damage_variance)
            
            # Apply armor
            damage = max(raw_damage - target.armor, Decimal('10'))  # Minimum 10 damage
            
            target.take_damage(damage)
            
            # Show possession-themed attack message
            possession_attacks = [
                f"👻 **POSSESSED STRIKE!** {current_combatant.name}'s body moves against their will!",
                f"😈 **DEMON'S CONTROL!** {current_combatant.name} attacks with unnatural fury!",
                f"💔 **FORCED ASSAULT!** {current_combatant.name} strikes their beloved unwillingly!",
                f"🪞 **TRUTH'S CRUELTY!** {current_combatant.name} attacks through tears!",
                f"👹 **POSSESSED FURY!** {current_combatant.name} fights against their own actions!"
            ]
            
            message = f"{random.choice(possession_attacks)} {target.name} takes **{self.format_number(damage)} HP** damage."
            
            # Check if target is defeated
            if not target.is_alive():
                message += f"\n💔 {target.name} has been struck down by their own beloved..."
        else:
            # Attack misses - show as internal resistance
            resistance_messages = [
                f"💪 {current_combatant.name} fights the demon's control! Their attack goes wide!",
                f"😤 {current_combatant.name}'s love breaks through momentarily! Attack misses!",
                f"💕 {current_combatant.name} resists the possession! Their strike falters!",
                f"🛡️ {current_combatant.name}'s true self fights back! Attack deflected by inner strength!"
            ]
            message = random.choice(resistance_messages)
        
        # Add message to battle log
        await self.add_to_log(message, force_new_action=True)
        
        # Show turn progress
        remaining_turns = self.possession_turn_limit - self.possession_turns
        

        if remaining_turns <= 0:
            await self.add_to_log(f"⏰ **FREEDOM ACHIEVED!** {self.possession_turns} turns completed!")
        elif remaining_turns <= 5:
            await self.add_to_log(f"⏰ **{remaining_turns} turns remaining** until the demon's hold weakens!")
        elif remaining_turns % 5 == 0:
            await self.add_to_log(f"⏳ {remaining_turns} turns until freedom...")
        
        # Update the battle display
        await self.update_display()
        await asyncio.sleep(await self.get_turn_delay())
        
        return True
    
    async def end_possession_victory(self):
        """End the possession and declare victory"""
        # Add victory messages as separate actions
        await self.add_to_log("✨ **THE DEMON'S HOLD WEAKENS!** ✨", force_new_action=True)
        await self.add_to_log(f"💪 {self.possessed_partner.name} breaks free from the Truth Demon's control!", force_new_action=True)
        await self.add_to_log(f"🏆 {self.defender_partner.name} survived the ultimate test of love!", force_new_action=True)
        
        # Kill the Truth Demon to trigger victory
        if self.truth_demon and self.truth_demon.is_alive():
            self.truth_demon.take_damage(self.truth_demon.hp)
        
        await self.add_to_log("🪞 **MIRROR OF TRUTH SHATTERED!** The demon dissolves into shadow!", force_new_action=True)
        await self.add_to_log("💕 **LOVE CONQUERS ALL!** Your bond has withstood the cruelest test!", force_new_action=True)
        
        # Update display one final time
        await self.update_display()
        await asyncio.sleep(2)
    
    async def process_turn_with_chaos_mechanics(self):
        """Process turn with Level 24 chaos mechanics - environmental chaos and partner anchoring"""
        # Handle pending enemy transitions as a separate action
        if self.pending_enemy_transition:
            return await self.handle_enemy_transition()
            
        if await self.is_battle_over():
            return False
        
        # Apply environmental chaos every few turns
        current_round = self.turn_counter // len(self.turn_order) if self.turn_order else 0
        if current_round > self.environmental_chaos_turn:
            self.environmental_chaos_turn = current_round
            await self.apply_environmental_chaos()
            
        # Randomize turn order every 3 rounds (existing mechanic)
        if self.turn_counter % 3 == 0:
            random.shuffle(self.turn_order)
            self.turn_order = self.prioritize_turn_order(self.turn_order)
            await self.add_to_log("⚡ Order scrambled!")
            
        # Get current combatant
        if not self.turn_order:
            self.update_turn_order()
            
        current_combatant = self.turn_order[self.current_turn % len(self.turn_order)]
        self.current_turn += 1
        
        # Skip dead combatants
        if not current_combatant.is_alive():
            return True
            
        # Level 24: Attempt partner anchoring before chaotic effects
        if current_combatant in self.player_team.combatants and not current_combatant.is_pet:
            await self.attempt_partner_anchoring(current_combatant)
            
        # Determine which team the combatant belongs to
        if current_combatant in self.player_team.combatants:
            # Player's turn, target the current enemy
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
            hit_success = luck_roll <= current_combatant.luck
            
        # Initialize message variable
        message = ""
            
        if hit_success:
            # Attack hits
            
            # Special case for mage fireball
            used_fireball = False
            if (hasattr(current_combatant, 'mage_evolution') and current_combatant.mage_evolution and 
                not current_combatant.is_pet and 
                self.config["class_buffs"] and
                random.random() < self.config["fireball_chance"]):
                
                # Calculate fireball damage with chaos variance
                evolution_level = current_combatant.mage_evolution
                damage_multiplier = {
                    1: 1.10,  # 110%
                    2: 1.20,  # 120%
                    3: 1.30,  # 130%
                    4: 1.50,  # 150%
                    5: 1.75,  # 175%
                    6: 2.00,  # 200%
                }.get(evolution_level, 1.0)
                
                from decimal import Decimal
                # Level 24: Extreme chaos variance for fireballs
                chaos_variance = random.randint(-200, 300)  # Much more chaotic
                damage = (current_combatant.damage + Decimal(chaos_variance) - target.armor) * Decimal(str(damage_multiplier))
                damage = max(damage, Decimal('1'))
                
                # Apply chaos effects to damage
                damage = await self.apply_chaos_effects_to_damage(current_combatant, damage)
                
                target.take_damage(damage)
                message = f"{current_combatant.name} casts a chaotic Fireball! {target.name} takes **{self.format_number(damage)} HP** damage."
                used_fireball = True
            else:
                # Regular attack with chaos
                from decimal import Decimal
                # Level 24: Extreme chaos variance
                if current_combatant.is_pet:
                    chaos_variance = random.randint(-50, 150)  # Pets less chaotic
                else:
                    chaos_variance = random.randint(-150, 250)  # Much more unpredictable
                
                # Start with base damage
                raw_damage = current_combatant.damage
                
                # Apply element effects to base damage if enabled
                if self.config["element_effects"] and hasattr(self.ctx.bot.cogs["Battles"], "element_ext"):
                    element_mod = self.ctx.bot.cogs["Battles"].element_ext.calculate_damage_modifier(
                        self.ctx,
                        self.resolve_attack_element(current_combatant),
                        self.resolve_defense_element(target)
                    )
                    if element_mod != 0:
                        raw_damage = raw_damage * (1 + Decimal(str(element_mod)))
                
                # Add chaos variance instead of normal variance
                raw_damage += Decimal(chaos_variance)
                

                outcome = self.resolve_pet_attack_outcome(
                    current_combatant,
                    target,
                    raw_damage,
                    apply_element_mod=False,
                    damage_variance=0,
                    minimum_damage=Decimal('10'),
                )
                damage = outcome.final_damage
                blocked_damage = outcome.blocked_damage
                skill_messages = outcome.skill_messages
                defender_messages = outcome.defender_messages
                
                # Apply chaos effects to damage
                damage = await self.apply_chaos_effects_to_damage(current_combatant, damage)
                
                target.take_damage(damage)
                message = f"{current_combatant.name} attacks chaotically! {target.name} takes **{self.format_number(damage)} HP** damage."
                
                # Add skill effect messages
                if skill_messages:
                    message += "\n" + "\n".join(skill_messages)
                if defender_messages:
                    message += "\n" + "\n".join(defender_messages)
            
            # Chaos Elemental special attacks
            if "Chaos Elemental" in current_combatant.name and random.random() < 0.40:
                await self.chaos_elemental_special_attack(target)
            
            # Handle lifesteal if applicable
            if (self.config["class_buffs"] and 
                not current_combatant.is_pet and 
                hasattr(current_combatant, 'lifesteal_percent') and
                current_combatant.lifesteal_percent > 0):
                
                lifesteal_amount = (float(damage) * float(current_combatant.lifesteal_percent) / 100.0)
                current_combatant.heal(lifesteal_amount)
                message += f" Lifesteals: **{self.format_number(lifesteal_amount)} HP**"
            
            # Handle damage reflection if applicable
            reflection_value = float(getattr(target, 'damage_reflection', 0))
            
            # Apply tank evolution-based reflection if target has tank evolution
            if (self.config["class_buffs"] and 
                hasattr(target, 'tank_evolution') and target.tank_evolution and 
                not target.is_pet):
                # Use the standard tank evolution reflection multiplier from classes.py
                tank_reflection = 0.03 * target.tank_evolution  # 3% per level, so 21% at level 7
                reflection_value = max(float(reflection_value), tank_reflection)  # Use higher of item reflection or tank reflection
            
            if (self.config["reflection_damage"] and 
                reflection_value > 0 and 
                'blocked_damage' in locals() and blocked_damage > 0):
                
                # Calculate reflection as percentage of raw damage, capped at defender's armor
                reflection_base = min(raw_damage, target.armor)
                reflected = reflection_base * Decimal(str(reflection_value))
                current_combatant.take_damage(reflected)
                message += f"\n{target.name}'s armor reflects **{self.format_number(reflected)} HP** damage back!"
                
                if not current_combatant.is_alive():
                    message += f" {current_combatant.name} has been defeated by reflected damage!"
            
            # Check if target is defeated
            if not target.is_alive():
                # Check for cheat death ability for players
                if (self.config["class_buffs"] and 
                    self.config.get("cheat_death", True) and
                    not target.is_pet and 
                    target in self.player_team.combatants and  # Only player can cheat death
                    hasattr(target, 'death_cheat_chance') and target.death_cheat_chance > 0 and
                    not getattr(target, 'has_cheated_death', False)):
                    
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
                message = f"{current_combatant.name} tripped in the chaos and took **{self.format_number(damage)} HP** damage!"
            else:
                message = f"{current_combatant.name}'s attack missed due to the chaotic environment!"
        
        # Add message to battle log - use a new action number for each combat action
        await self.add_to_log(message, force_new_action=True)
        
        # PROCESS PET SKILL EFFECTS PER TURN
        if hasattr(self.ctx.bot.cogs["Battles"], "battle_factory"):
            try:
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
            except (AttributeError, KeyError):
                pass  # Pet extension not available
        
        # Escalate chaos intensity over time
        if self.turn_counter % 10 == 0:  # Every 10 turns
            self.chaos_intensity = min(self.chaos_intensity + 1, 5)  # Max intensity 5
            
        # Update the battle display
        await self.update_display()
        await asyncio.sleep(await self.get_turn_delay())
        
        return True
    
    async def apply_environmental_chaos(self):
        """Apply environmental chaos effects each round"""
        chaos_events = [
            "🌪️ Walls shift wildly!",
            "💥 Floor cracks beneath you!",
            "⚡ Reality bends violently!",
            "🌊 Gravity shifts chaotically!",
            "🔥 Space tears open!",
            "❄️ Time stutters and skips!",
            "🌈 Colors invert madly!",
            "⚡ Dimensions merge!"
        ]
        
        # Combine everything into one shorter message
        chaos_msg = f"🌪️ **CHAOS!** {random.choice(chaos_events)}"
        
        # Add intensity description
        if self.chaos_intensity >= 4:
            chaos_msg += " 💀 MAXIMUM CHAOS!"
        elif self.chaos_intensity >= 3:
            chaos_msg += " 🌀 Reality fractures!"
        elif self.chaos_intensity >= 2:
            chaos_msg += " ⚡ Storm intensifies!"
            
        await self.add_to_log(chaos_msg, force_new_action=True)
            
    async def attempt_partner_anchoring(self, partner):
        """Allow partners to anchor each other against chaos"""
        other_partners = [c for c in self.player_team.combatants if not c.is_pet and c != partner and c.is_alive()]
        
        if other_partners and random.random() < 0.25:  # 25% chance to anchor
            anchor_partner = other_partners[0]
            self.partner_anchoring[partner.name] = True
            
            # Shorter anchoring message
            await self.add_to_log(f"⚓ {anchor_partner.name} anchors {partner.name}!")
            
    async def apply_chaos_effects_to_damage(self, attacker, damage):
        """Modify damage based on chaos effects and anchoring"""
        from decimal import Decimal
        
        # Check if attacker is anchored by partner
        if attacker.name in self.partner_anchoring:
            # Anchored: More stable damage
            stabilized_damage = damage * Decimal('1.0')  # No chaos modifier
            await self.add_to_log(f"⚓ {attacker.name} strikes true!")
            self.partner_anchoring.pop(attacker.name, None)  # Remove anchoring after use
            return stabilized_damage
        else:
            # Not anchored: Chaos effects apply
            chaos_modifier = random.uniform(0.3, 2.0)  # 30% to 200% damage
            chaotic_damage = damage * Decimal(str(chaos_modifier))
            
            if chaos_modifier > 1.5:
                await self.add_to_log(f"🌪️ Chaos amplifies {attacker.name}!")
            elif chaos_modifier < 0.7:
                await self.add_to_log(f"⚡ Chaos weakens {attacker.name}!")
                
            return chaotic_damage
            
    async def chaos_elemental_special_attack(self, target):
        """Chaos Elemental unleashes special chaos effects"""
        chaos_specials = [
            "🌀 Reality Warp",
            "⚡ Dimension Strike", 
            "🌪️ Chaos Vortex",
            "💥 Entropy Blast"
        ]
        
        special_name = random.choice(chaos_specials)
        
        # Apply random chaos effect
        effect_roll = random.randint(1, 4)
        from decimal import Decimal
        
        if effect_roll == 1:
            # Bonus chaos damage
            chaos_damage = Decimal(random.randint(20, 60))
            target.take_damage(chaos_damage)
            await self.add_to_log(f"{special_name}! +{chaos_damage} chaos damage!")
        elif effect_roll == 2:
            # Scramble target's next attack
            setattr(target, 'chaos_scrambled', True)
            await self.add_to_log(f"{special_name}! {target.name} scrambled!")
        elif effect_roll == 3:
            # Chaos healing (unpredictable)
            if random.random() < 0.5:
                chaos_heal = Decimal(random.randint(10, 40))
                target.heal(chaos_heal)
                await self.add_to_log(f"{special_name}! Random heal +{chaos_heal} HP!")
            else:
                await self.add_to_log(f"{special_name}! Nothing happens!")
        else:
            # Reality hiccup - miss next turn chance
            if random.random() < 0.3:
                setattr(target, 'reality_hiccup', True)
                await self.add_to_log(f"{special_name}! Reality hiccup!")

    async def initialize_mirror_of_truth(self):
        """Level 23: Initialize Mirror of Truth possession system"""
        partners = [c for c in self.player_team.combatants if not c.is_pet]
        
        if len(partners) < 2:
            await self.add_to_log("💔 Mirror of Truth requires both partners to be present!")
            return False
            
        # Randomly pick one partner to be possessed
        self.possessed_partner = random.choice(partners)
        self.defender_partner = partners[0] if partners[1] == self.possessed_partner else partners[1]
        
        # Create the Truth Demon (1 HP, can't be targeted)
        from cogs.battles.core.combatant import Combatant
        from decimal import Decimal
        
        # Create a minimal Truth Demon with None user (it's an NPC)
        self.truth_demon = Combatant(
            user=None,
            name="Truth Demon",
            hp=Decimal('1'),
            max_hp=Decimal('1'),
            damage=Decimal('1'),
            armor=Decimal('0'),
            luck=0,
            element="Dark"
        )
        
        # Add Truth Demon to enemy team
        self.enemy_team.combatants.append(self.truth_demon)
        
        await self.add_to_log("🪞 **THE MIRROR OF TRUTH AWAKENS!** 🪞")
        await self.add_to_log(f"👻 **POSSESSION!** A Truth Demon seizes control of {self.possessed_partner.name}!")
        await self.add_to_log(f"🛡️ {self.defender_partner.name} must survive for {self.possession_turn_limit} turns without killing their beloved!")
        await self.add_to_log("⚠️ **TIP:** Consider unequipping weapons to reduce damage and avoid accidentally killing your partner!")
        
        return True

    async def create_battle_embed(self):
        """Create the battle status embed for couples battles with level-specific modifications"""
        # Level 30: No combat embed - check this FIRST
        if self.level == 30:
            return await self.create_level_30_embed()
        
        # Ensure we have enemies before accessing them (for all other levels)
        if not self.enemy_team.combatants or self.current_opponent_index >= len(self.enemy_team.combatants):
            return discord.Embed(title="Battle Error", description="No enemies found!", color=discord.Color.red())
        
        # Level 5: Split Combat - Show both enemies
        if self.level == 5 and len(self.enemy_team.combatants) >= 2:
            return await self.create_split_combat_embed()
        
        # Level 13: Multiple active enemies - Show all Confusion Sprites
        if self.level == 13:
            return await self.create_multi_enemy_embed()
        
        # Level 23: Mirror of Truth - Show possession battle
        if self.level == 23:
            try:
                return await self.create_possession_embed()
            except Exception as e:
                await self.ctx.send(f"Level 23 Embed Error: {e}")
                import traceback
                await self.ctx.send(f"```{traceback.format_exc()}```")
                # Return a fallback embed
                return discord.Embed(title="Level 23 - Error", description=f"Error creating embed: {e}", color=discord.Color.red())
            
        current_enemy = self.enemy_team.combatants[self.current_opponent_index]
        embed = discord.Embed(
            title=f"Couples Battle Tower: Level {self.level} - {self.ctx.author.display_name} & Partner vs {current_enemy.name}",
            color=self.get_level_embed_color()
        )
        
        # Get element emoji mapping
        element_emoji_map = {}
        if hasattr(self.ctx.bot.cogs["Battles"], "emoji_to_element"):
            element_emoji_map = self.ctx.bot.cogs["Battles"].emoji_to_element
            
        # Add player team info (both partners) with level-specific modifications
        embed.add_field(name="💕 **LOVE TEAM** 💕", value="", inline=False)
        for combatant in self.player_team.combatants:
            current_hp = max(0, float(combatant.hp))
            max_hp = float(combatant.max_hp)
            
            # Level 2: Blind Combat - hide HP for partners
            if self.level == 2 and not combatant.is_pet:
                hp_display = "???"
                hp_bar = "▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓"  # Hidden HP bar
            else:
                hp_display = f"{current_hp:.1f}/{max_hp:.1f}"
                hp_bar = self.create_hp_bar(current_hp, max_hp)
            
            # Get element emoji
            element_emoji = "❌"
            for emoji, element in element_emoji_map.items():
                if element == combatant.element:
                    element_emoji = emoji
                    break
            
            # Set field name based on type
            if combatant.is_pet:
                field_name = f"🐾 {combatant.name} {element_emoji}"
            else:
                field_name = f"💑 {combatant.display_name} {element_emoji}"
                
            # Create field value with HP bar
            field_value = f"HP: {hp_display}\n{hp_bar}"
            
            # Level-specific additions to field value
            if self.level == 7:  # Memory Shield: Show fragments
                if not combatant.is_pet and self.memory_fragments > 0:
                    reduction = min(25 * self.memory_fragments, 100)
                    field_value += f"\n💎 Memory Shield: -{reduction}% next damage"
                    
            if self.level == 14:  # Pride: Show damage tracking
                damage_dealt = self.damage_dealt_tracking.get(combatant.name, 0)
                field_value += f"\n⚔️ Damage Dealt: {damage_dealt:.1f}"
                
            if self.level == 16:  # Forgiveness: Show grudge stacks
                grudges = self.grudge_stacks.get(combatant.name, 0)
                if grudges > 0:
                    damage_boost = grudges * 10
                    field_value += f"\n😠 Grudges: {grudges} (+{damage_boost}% damage)"
                    
            if self.level == 22:  # Despair: Show despair stacks with effects
                despair = self.despair_stacks.get(combatant.name, 0)
                if despair > 0:
                    damage_reduction = min(despair * 8, 80)
                    accuracy_reduction = min(despair * 5, 50)
                    if despair <= 3:
                        field_value += f"\n😔 Despair: {despair} (-{damage_reduction}% dmg, -{accuracy_reduction}% acc)"
                    elif despair <= 6:
                        field_value += f"\n💔 Deep Despair: {despair} (-{damage_reduction}% dmg, -{accuracy_reduction}% acc)"
                    else:
                        field_value += f"\n💀 Crushing Despair: {despair} (-{damage_reduction}% dmg, -{accuracy_reduction}% acc)"
                        
            if self.level == 24:  # Chaos: Show anchoring status
                if not combatant.is_pet:
                    if combatant.name in self.partner_anchoring:
                        field_value += f"\n⚓ Anchored: Next attack stable"
                    else:
                        field_value += f"\n🌪️ Vulnerable: Chaos effects active"
                    
            if self.level == 26:  # Pain: Show pain bonuses
                pain_bonus = self.pain_damage_bonuses.get(combatant.name, 0)
                if pain_bonus > 0:
                    field_value += f"\n💢 Pain Fury: +{pain_bonus:.0f}% damage"
                    
            if self.level == 21:  # Forge Heat: Show heat resistance 
                if not combatant.is_pet and hasattr(self, 'forge_heat_intensity'):
                    field_value += f"\n🔥 Forge Heat: {self.forge_heat_intensity} intensity"
                    
            if self.level == 23:  # Mirror of Truth: Show possession status
                if not combatant.is_pet:
                    if hasattr(self, 'possessed_partner') and combatant == self.possessed_partner:
                        remaining = self.possession_turn_limit - self.possession_turns
                        field_value += f"\n👻 Possessed: {remaining} turns to freedom"
                    elif hasattr(self, 'defender_partner') and combatant == self.defender_partner:
                        remaining = self.possession_turn_limit - self.possession_turns
                        field_value += f"\n🛡️ Defending: Survive {remaining} more turns"
                        
            if self.level == 25:  # Fear: Show fear immunity status
                if "Fear Incarnate" in combatant.name:
                    field_value += f"\n👹 Fear Immunity: Cannot be frightened"
                elif not combatant.is_pet:
                    field_value += f"\n😨 Fear Vulnerable: 30% paralysis chance"
                    
            if self.level == 27:  # Aging: Show aging progression
                if not combatant.is_pet and self.aging_turns > 0:
                    aging_percent = self.aging_turns * 3  # 3% per turn
                    field_value += f"\n⏳ Aged: -{aging_percent}% stats (Turn {self.aging_turns})"
                    
            if self.level == 28:  # Growth: Show protective shielding status
                if not combatant.is_pet:
                    hp_percent = (float(combatant.hp) / float(combatant.max_hp)) * 100
                    partners = [c for c in self.player_team.combatants if not c.is_pet and c != combatant and c.is_alive()]
                    if partners:
                        partner = partners[0]
                        partner_hp_percent = (float(partner.hp) / float(partner.max_hp)) * 100
                        hp_diff = hp_percent - partner_hp_percent
                        
                        if hp_diff >= 10:
                            field_value += f"\n🛡️ Shield Ready: Can protect {partner.name} ({hp_diff:+.0f}% HP)"
                        elif hp_diff <= -10:
                            field_value += f"\n💔 Needs Protection: {partner.name} can shield ({hp_diff:+.0f}% HP)"
                        else:
                            field_value += f"\n⚖️ HP Balanced: No shielding ({hp_diff:+.0f}% HP)"
            
            if self.level == 29:  # Spirit Healing: Show spirit/living status
                if not combatant.is_pet:
                    if not combatant.is_alive():
                        field_value += f"\n👻 Spirit Status: Can heal living partner"
                    else:
                        # Check if partner is a spirit
                        partners = [c for c in self.player_team.combatants if not c.is_pet and c != combatant]
                        if partners:
                            partner = partners[0]
                            if not partner.is_alive():
                                field_value += f"\n✨ Supported by: {partner.name}'s spirit"
                            else:
                                field_value += f"\n💕 Both partners: Living and fighting"
            
            # Add reflection info if applicable
            if combatant.damage_reflection > 0:
                reflection_percent = float(combatant.damage_reflection) * 100
                field_value += f"\nDamage Reflection: {reflection_percent:.1f}%"
                
            embed.add_field(name=field_name, value=field_value, inline=True)
        
        # Add current enemy info with level-specific modifications
        embed.add_field(name="", value="", inline=False)  # Spacer
        current_hp = max(0, float(current_enemy.hp))
        max_hp = float(current_enemy.max_hp)
        
        # Level 2: Blind Combat - hide enemy HP
        if self.level == 2:
            enemy_hp_display = "???"
            enemy_hp_bar = "▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓"
        else:
            enemy_hp_display = f"{current_hp:.1f}/{max_hp:.1f}"
            enemy_hp_bar = self.create_hp_bar(current_hp, max_hp)
        
        # Get element emoji for enemy
        element_emoji = "❌"
        for emoji, element in element_emoji_map.items():
            if element == current_enemy.element:
                element_emoji = emoji
                break
        
        field_name = f"👹 **ENEMY** 👹\n{current_enemy.name} {element_emoji}"
        field_value = f"HP: {enemy_hp_display}\n{enemy_hp_bar}"
        
        # Enemy-specific progression displays
        if self.level == 25 and "Fear Incarnate" in current_enemy.name:
            field_value += f"\n👹 Fear Embodiment: Immune to terror"
        elif self.level == 27 and "Time Wraith" in current_enemy.name:
            field_value += f"\n⚡ Temporal Being: Immune to aging"
        elif self.level == 24 and "Chaos Elemental" in current_enemy.name:
            field_value += f"\n🌪️ Chaos Master: Reality manipulation"
        elif self.level == 22 and "Despair Wraith" in current_enemy.name:
            field_value += f"\n😞 Despair Inducer: Psychological attacks"
            
        embed.add_field(name=field_name, value=field_value, inline=False)
        
        # Add battle log with level-specific modifications
        log_text = self.format_battle_log()
        embed.add_field(name="Battle Log", value=log_text or "Battle starting...", inline=False)
        
        # Level-specific embed additions
        if self.level == 7 and self.memory_fragments > 0:
            embed.add_field(name="💎 Memory Fragments", value=f"{self.memory_fragments} (Next damage reduced by {min(25 * self.memory_fragments, 100)}%)", inline=False)
            
        if self.level == 21:
            # Only show forge heat if both partners are alive
            partners = [c for c in self.player_team.combatants if not c.is_pet]
            if all(partner.is_alive() for partner in partners):
                heat_emoji = "🔥" if self.forge_heat_intensity < 100 else "🔥💥" if self.forge_heat_intensity < 150 else "🌋" if self.forge_heat_intensity < 200 else "⚡🔥"
                embed.add_field(name=f"{heat_emoji} Forge Heat", value=f"**{self.forge_heat_intensity}** intensity - Will you sacrifice for love?", inline=False)
            else:
                # Someone died from heat - show memorial message
                embed.add_field(name="💔 Love's End", value="*The forge's heat has claimed a life...*", inline=False)
            
        if self.level == 22:
            # Show total despair atmosphere
            partners = [c for c in self.player_team.combatants if not c.is_pet]
            total_despair = sum(self.despair_stacks.get(p.name, 0) for p in partners)
            if total_despair == 0:
                embed.add_field(name="🌈 Hope Shines", value="*Your love lights the way through the darkness*", inline=False)
            elif total_despair <= 5:
                embed.add_field(name="🌫️ Valley of Despair", value="*Dark mists cloud your minds, but love endures*", inline=False)
            elif total_despair <= 10:
                embed.add_field(name="😞 Deep Despair", value="*Hopelessness weighs heavy, yet you fight on together*", inline=False)
            else:
                embed.add_field(name="💀 Crushing Despair", value="*The wraiths' whispers threaten to break your spirit...*", inline=False)
            
        if self.level == 24:
            # Show chaos intensity and partner anchoring status
            chaos_emoji = "⚡" if self.chaos_intensity <= 2 else "🌪️" if self.chaos_intensity <= 3 else "🌀" if self.chaos_intensity <= 4 else "💀"
            intensity_desc = ["Mild", "Growing", "Intense", "Extreme", "MAXIMUM"][min(self.chaos_intensity - 1, 4)]
            
            chaos_info = f"{chaos_emoji} **{intensity_desc} Chaos** (Level {self.chaos_intensity})"
            
            # Show who is anchored
            anchored_partners = [name for name in self.partner_anchoring.keys()]
            if anchored_partners:
                chaos_info += f"\n⚓ Anchored: {', '.join(anchored_partners)}"
            else:
                chaos_info += f"\n💫 All partners vulnerable to chaos effects"
                
            embed.add_field(name="🌪️ Storm of Chaos", value=chaos_info, inline=False)
            
        if self.level == 28:
            # Show garden growth progress
            flowers_bloomed = "🌸" * self.growth_points
            flowers_needed = "🌱" * (self.growth_required - self.growth_points)
            garden_display = flowers_bloomed + flowers_needed
            
            if self.final_enemy_vulnerable:
                embed.add_field(name="🌸 Garden in Full Bloom!", value=f"{garden_display}\n*Your garden blooms with love! The final enemy is vulnerable!*", inline=False)
            elif self.growth_points == 0:
                embed.add_field(name="🌱 Garden of Renewal", value=f"{garden_display}\n*Show caring to make your garden bloom! Defeat enemies, protect each other, show vulnerability! ({self.growth_points}/{self.growth_required} flowers)*", inline=False)
            else:
                embed.add_field(name="🌻 Growing Garden", value=f"{garden_display}\n*Your love grows stronger with each act of caring! ({self.growth_points}/{self.growth_required} flowers)*", inline=False)
        
        # Add battle ID to footer for GM replay functionality
        embed.set_footer(text=f"Battle ID: {self.battle_id}")
        
        return embed
    
    async def create_possession_embed(self):
        """Special embed for Level 23 Mirror of Truth possession battle"""
        embed = discord.Embed(
            title=f"Couples Battle Tower: Level 23 - The Mirror of Truth",
            description=f"🪞 **{self.possessed_partner.name} is possessed! {self.defender_partner.name} must survive {self.possession_turn_limit - self.possession_turns} more turns!** 🪞",
            color=discord.Color.dark_purple()
        )
        
        # Get element emoji mapping
        element_emoji_map = {}
        if hasattr(self.ctx.bot.cogs["Battles"], "emoji_to_element"):
            element_emoji_map = self.ctx.bot.cogs["Battles"].emoji_to_element
        
        # Show defender (the one trying to survive)
        defender_hp = max(0, float(self.defender_partner.hp))
        defender_max_hp = float(self.defender_partner.max_hp)
        defender_hp_bar = self.create_hp_bar(defender_hp, defender_max_hp)
        
        defender_emoji = "❌"
        for emoji, element in element_emoji_map.items():
            if element == self.defender_partner.element:
                defender_emoji = emoji
                break
        
        embed.add_field(
            name=f"🛡️ **DEFENDER** 🛡️\n💑 {self.defender_partner.display_name} {defender_emoji}",
            value=f"HP: {defender_hp:.1f}/{defender_max_hp:.1f}\n{defender_hp_bar}\n*Must survive without killing their beloved*",
            inline=True
        )
        
        # Show possessed partner (the attacker)
        possessed_hp = max(0, float(self.possessed_partner.hp))
        possessed_max_hp = float(self.possessed_partner.max_hp)
        possessed_hp_bar = self.create_hp_bar(possessed_hp, possessed_max_hp)
        
        possessed_emoji = "❌"
        for emoji, element in element_emoji_map.items():
            if element == self.possessed_partner.element:
                possessed_emoji = emoji
                break
        
        embed.add_field(
            name=f"👻 **POSSESSED** 👻\n💔 {self.possessed_partner.display_name} {possessed_emoji}",
            value=f"HP: {possessed_hp:.1f}/{possessed_max_hp:.1f}\n{possessed_hp_bar}\n*Struggles against demonic control*",
            inline=True
        )
        
        # Show Truth Demon (untargetable)
        embed.add_field(name="", value="", inline=False)  # Spacer
        
        # Show Truth Demon HP properly (0/1 when dead)
        demon_hp = float(self.truth_demon.hp) if self.truth_demon else 0
        demon_max_hp = float(self.truth_demon.max_hp) if self.truth_demon else 1
        demon_hp_bar = self.create_hp_bar(demon_hp, demon_max_hp)
        
        embed.add_field(
            name="🪞 **TRUTH DEMON** 🪞\n👹 Truth Demon 👹",
            value=f"HP: {demon_hp:.1f}/{demon_max_hp:.1f}\n{demon_hp_bar}\n*Cannot be targeted - Dies after {self.possession_turn_limit} turns*",
            inline=False
        )
        
        # Show possession progress
        remaining_turns = self.possession_turn_limit - self.possession_turns
        progress_bar_length = 20
        progress_filled = int(progress_bar_length * (self.possession_turns / self.possession_turn_limit))
        progress_empty = progress_bar_length - progress_filled
        progress_bar = "█" * progress_filled + "░" * progress_empty
        
        embed.add_field(
            name="⏰ **POSSESSION TIMER** ⏰",
            value=f"Turn {self.possession_turns}/{self.possession_turn_limit}\n{progress_bar}\n**{remaining_turns} turns remaining**",
            inline=False
        )
        
        # Add battle log (truncate if too long for Discord)
        log_text = self.format_battle_log()
        if not log_text:
            log_text = "Battle starting..."
        elif len(log_text) > 1020:  # Leave some margin below 1024 limit
            # Keep the last few actions and add truncation notice
            lines = log_text.split('\n\n')
            truncated_lines = ["*...earlier actions truncated...*"]
            current_length = len(truncated_lines[0]) + 4  # +4 for separators
            
            # Add lines from the end until we hit the limit
            for line in reversed(lines[-5:]):  # Last 5 actions max
                if current_length + len(line) + 2 < 1020:
                    truncated_lines.append(line)
                    current_length += len(line) + 2
                else:
                    break
            
            # Reverse to get correct order (except the truncation notice)
            log_text = truncated_lines[0] + '\n\n' + '\n\n'.join(reversed(truncated_lines[1:]))
        
        embed.add_field(name="Battle Log", value=log_text, inline=False)
        
        # Add battle ID to footer for GM replay functionality
        embed.set_footer(text=f"Battle ID: {self.battle_id}")

        
        return embed
    
    def get_level_embed_color(self):
        """Get embed color based on level theme"""
        if self.level == 4:  # Storm - Dynamic color
            return discord.Color.dark_blue() if self.turn_counter % 2 == 0 else discord.Color.light_grey()
        elif self.level == 11:  # Ballroom
            return discord.Color.purple()
        elif self.level == 17:  # Secrets
            return discord.Color.dark_theme()
        elif self.level == 24:  # Chaos - Color changes with intensity
            chaos_colors = [
                discord.Color.blue(),      # Mild chaos
                discord.Color.orange(),    # Growing chaos  
                discord.Color.red(),       # Intense chaos
                discord.Color.dark_red(),  # Extreme chaos
                discord.Color.from_rgb(139, 0, 139)  # MAXIMUM chaos (dark magenta)
            ]
            return chaos_colors[min(self.chaos_intensity - 1, 4)]
        else:
            return discord.Color.magenta()  # Default couples color
    
    def format_battle_log(self):
        """Format battle log with level-specific modifications"""
        if not self.log:
            return "Battle starting..."
            
        formatted_log = []
        for i, msg in self.log:
            # Level 11: Dance transformations now happen when messages are first added
                
            # Level 17: Secrets - Hide damage numbers
            if self.level == 17:
                import re
                msg = re.sub(r'\d+\.?\d*\s*damage', 'mysterious damage', msg)
                msg = re.sub(r'\d+\.?\d*\s*HP', 'unknown HP', msg)
            
            # Level 24: Add chaos flavor to regular attacks
            if self.level == 24 and " attacks " in msg:
                import re
                # Replace "attacks" with chaotic variants
                chaos_attacks = ["strikes chaotically", "lashes out wildly", "attacks through the storm", "strikes amid the chaos", "battles through reality"]
                msg = re.sub(r' attacks ', f' {random.choice(chaos_attacks)} ', msg)
            
            formatted_log.append(f"**Action #{i}**\n{msg}")
        
        # Level 24: Aggressive truncation for chaos battles to prevent overflow
        if self.level == 24:
            result = "\n\n".join(formatted_log)
            if len(result) > 900:  # More aggressive limit for Level 24
                # Keep only the last 5 actions for chaos levels
                recent_actions = formatted_log[-5:]
                result = "*...chaos continues...*\n\n" + "\n\n".join(recent_actions)
                if len(result) > 900:  # Still too long, be even more aggressive
                    recent_actions = formatted_log[-3:]
                    result = "*...chaos...*\n\n" + "\n\n".join(recent_actions)
            return result
        
        # Level 16: Aggressive truncation for grudge mechanics to prevent overflow  
        if self.level == 16:
            result = "\n\n".join(formatted_log)
            if len(result) > 900:  # More aggressive limit for Level 16 grudge mechanics
                # Keep only the last 5 actions for grudge levels
                recent_actions = formatted_log[-5:]
                result = "*...grudges intensify...*\n\n" + "\n\n".join(recent_actions)
                if len(result) > 900:  # Still too long, be even more aggressive
                    recent_actions = formatted_log[-3:]
                    result = "*...fury builds...*\n\n" + "\n\n".join(recent_actions)
            return result
        
        # Level 18: Aggressive truncation for temptation mechanics to prevent overflow
        if self.level == 18:
            result = "\n\n".join(formatted_log)
            if len(result) > 900:  # More aggressive limit for Level 18 temptation mechanics
                # Keep only the last 5 actions for temptation levels to prevent Discord embed limit
                recent_actions = formatted_log[-5:]
                result = "*...temptations swirl...*\n\n" + "\n\n".join(recent_actions)
                if len(result) > 900:  # Still too long, be even more aggressive
                    recent_actions = formatted_log[-3:]
                    result = "*...seductive whispers...*\n\n" + "\n\n".join(recent_actions)
            return result
        
        # Level 19: Aggressive truncation for vulnerability mechanics to prevent overflow
        if self.level == 19:
            result = "\n\n".join(formatted_log)
            if len(result) > 900:  # More aggressive limit for Level 19 vulnerability mechanics
                # Keep only the last 5 actions for vulnerability levels to prevent Discord embed limit
                recent_actions = formatted_log[-5:]
                result = "*...vulnerabilities exposed...*\n\n" + "\n\n".join(recent_actions)
                if len(result) > 900:  # Still too long, be even more aggressive
                    recent_actions = formatted_log[-3:]
                    result = "*...insecurities targeted...*\n\n" + "\n\n".join(recent_actions)
            return result
        
        # Level 21: Aggressive truncation for forge heat mechanics to prevent overflow
        if self.level == 21:
            result = "\n\n".join(formatted_log)
            if len(result) > 900:  # More aggressive limit for Level 21 forge heat mechanics
                # Keep only the last 5 actions for forge heat levels to prevent Discord embed limit
                recent_actions = formatted_log[-5:]
                result = "*...forge heat intensifies...*\n\n" + "\n\n".join(recent_actions)
                if len(result) > 900:  # Still too long, be even more aggressive
                    recent_actions = formatted_log[-3:]
                    result = "*...heat rises...*\n\n" + "\n\n".join(recent_actions)
            return result
            
        # Level 22: Aggressive truncation for despair mechanics to prevent overflow
        if self.level == 22:
            result = "\n\n".join(formatted_log)
            if len(result) > 900:  # More aggressive limit for Level 22 despair mechanics
                # Keep only the last 3 actions for despair levels to prevent Discord embed limit
                recent_actions = formatted_log[-3:]
                result = "*...despair deepens...*\n\n" + "\n\n".join(recent_actions)
                if len(result) > 900:  # Still too long, be even more aggressive
                    recent_actions = formatted_log[-2:]
                    result = "*...darkness spreads...*\n\n" + "\n\n".join(recent_actions)
            return result
            
        return "\n\n".join(formatted_log)

    async def create_split_combat_embed(self):
        """Special embed for Level 5 split combat"""
        embed = discord.Embed(
            title=f"Couples Battle Tower: Level 5 - Split Combat",
            description="💔 **You must fight separately to protect what matters most!** 💔",
            color=discord.Color.red()
        )
        
        # Get element emoji mapping
        element_emoji_map = {}
        if hasattr(self.ctx.bot.cogs["Battles"], "emoji_to_element"):
            element_emoji_map = self.ctx.bot.cogs["Battles"].emoji_to_element
        
        partners = [c for c in self.player_team.combatants if not c.is_pet]
        
        # Show both combat pairs
        for i, partner in enumerate(partners):
            if i < len(self.enemy_team.combatants):
                enemy = self.enemy_team.combatants[i]
                
                # Partner info
                current_hp = max(0, float(partner.hp))
                max_hp = float(partner.max_hp)
                hp_bar = self.create_hp_bar(current_hp, max_hp)
                
                # Enemy info
                enemy_hp = max(0, float(enemy.hp))
                enemy_max_hp = float(enemy.max_hp)
                enemy_hp_bar = self.create_hp_bar(enemy_hp, enemy_max_hp)
                
                # Get element emojis
                partner_emoji = "❌"
                enemy_emoji = "❌"
                for emoji, element in element_emoji_map.items():
                    if element == partner.element:
                        partner_emoji = emoji
                    if element == enemy.element:
                        enemy_emoji = emoji
                
                field_name = f"⚔️ **BATTLEFIELD {i+1}** ⚔️"
                field_value = (f"💑 **{partner.display_name}** {partner_emoji}\n"
                             f"HP: {current_hp:.1f}/{max_hp:.1f}\n{hp_bar}\n\n"
                             f"**VS**\n\n"
                             f"👹 **{enemy.name}** {enemy_emoji}\n"
                             f"HP: {enemy_hp:.1f}/{enemy_max_hp:.1f}\n{enemy_hp_bar}")
                
                embed.add_field(name=field_name, value=field_value, inline=True)
        
        # Add pets if any
        pets = [c for c in self.player_team.combatants if c.is_pet and c.is_alive()]
        if pets:
            pet_info = []
            for pet in pets:
                current_hp = max(0, float(pet.hp))
                max_hp = float(pet.max_hp)
                hp_bar = self.create_hp_bar(current_hp, max_hp)
                pet_info.append(f"🐾 {pet.name}\nHP: {current_hp:.1f}/{max_hp:.1f}\n{hp_bar}")
            embed.add_field(name="🐾 **COMPANIONS** 🐾", value="\n\n".join(pet_info), inline=False)
        
        # Add battle log
        log_text = self.format_battle_log()
        embed.add_field(name="Battle Log", value=log_text or "Battle starting...", inline=False)
        
        # Add battle ID to footer for GM replay functionality
        embed.set_footer(text=f"Battle ID: {self.battle_id}")
        
        return embed

    async def create_level_30_embed(self):
        """Special embed for Level 30 ceremony"""
        return discord.Embed(
            title="🌟 The Apex of Love - Complete 🌟",
            description="*Your love has transcended all trials. You are eternal.*",
            color=discord.Color.gold()
        )
        
    async def add_to_log(self, message, force_new_action=False):
        """Override to customize Level 11 messages when they're first added"""
        if self.level == 11:
            # Transform attack messages into dance themes when first added
            if "attacks!" in message and "takes" in message:
                import random
                if message.startswith("Heartbreak Phantom attacks!"):
                    # Enemy attack messages
                    dance_attacks = [
                        "💃 **Heartbreak Phantom** pirouettes menacingly and strikes **{}**!",
                        "🕺 **Heartbreak Phantom** performs a deadly waltz against **{}**!", 
                        "👻 **Heartbreak Phantom** glides ominously toward **{}**!",
                        "💔 **Heartbreak Phantom** spins with malevolent grace at **{}**!",
                        "🎭 **Heartbreak Phantom** executes a haunting tango against **{}**!"
                    ]
                    # Extract target from "Heartbreak Phantom attacks! TARGET takes Y HP damage."
                    target_and_damage = message.split("attacks!")[-1].strip()
                    target_name = target_and_damage.split(" takes ")[0].strip()
                    damage_part = " takes " + target_and_damage.split(" takes ")[1]
                    message = f"{random.choice(dance_attacks).format(target_name)}{damage_part}"
                else:
                    # Player attack messages
                    player_dance_attacks = [
                        "💃 **{}** gracefully spins and strikes **{}**!",
                        "🕺 **{}** performs a passionate tango against **{}**!",
                        "💫 **{}** dances with deadly elegance toward **{}**!", 
                        "🎭 **{}** executes a fierce ballroom combo on **{}**!",
                        "💖 **{}** dances with their partner's strength against **{}**!"
                    ]
                    # Extract attacker and target from "ATTACKER attacks! TARGET takes Z HP damage."
                    if " attacks!" in message:
                        attacker = message.split(" attacks!")[0]
                        target_and_damage = message.split("attacks!")[-1].strip()
                        target_name = target_and_damage.split(" takes ")[0].strip()
                        damage_part = " takes " + target_and_damage.split(" takes ")[1]
                        message = f"{random.choice(player_dance_attacks).format(attacker, target_name)}{damage_part}"
        
        return await super().add_to_log(message, force_new_action)

    # NOTE: calculate_damage() and apply_damage() methods removed - they were never called by the tower battle system
    # All level-specific mechanics are now properly implemented in the process_turn_with_* methods

    def create_hp_bar(self, current_hp, max_hp):
        """Create a formatted HP bar"""
        bar_length = 20
        filled_length = int(bar_length * (current_hp / max_hp))
        empty_length = bar_length - filled_length
        hp_bar = "█" * filled_length + "░" * empty_length
        return hp_bar 
    
    def update_turn_order(self):
        """Override to include dead partners for Level 29 spirit healing"""
        # Clear current turn order
        self.turn_order = []
        
        # Level 30: No combat, no turn order needed
        if self.level == 30:
            self.turn_order = []  # Ensure empty turn order
            return
        
        # Add player team
        for combatant in self.player_team.combatants:
            # For Level 29, include dead partners (they can heal as spirits)
            # For all other levels, only include alive combatants
            if self.level == 29:
                # Include all partners (dead ones become spirits), but only living pets
                if not combatant.is_pet or combatant.is_alive():
                    self.turn_order.append(combatant)
            else:
                # Normal behavior: only alive combatants
                if combatant.is_alive():
                    self.turn_order.append(combatant)
        
        # Add current enemy (only if alive and enemies exist)
        if (self.enemy_team.combatants and 
            self.current_opponent_index < len(self.enemy_team.combatants)):
            current_enemy = self.enemy_team.combatants[self.current_opponent_index]
            if current_enemy.is_alive():
                self.turn_order.append(current_enemy)
        
        # Shuffle to randomize initial order
        import random
        random.shuffle(self.turn_order)
        self.turn_order = self.prioritize_turn_order(self.turn_order)

    async def can_combatant_act(self, combatant):
        """Check if combatant can act this turn with level-specific restrictions"""
        # Level 30: No combat allowed
        if self.level == 30:
            return False
            
        if not combatant.is_alive() and self.level != 29:
            return False
            
        # Level 9: Slow combat - handled by increased turn delay in main battle loop
        
        # Level 12: Freeze mechanics - handled in process_turn_with_freeze_mechanics()
        
        # Level 15: Betrayal illusions - handled in process_turn_with_betrayal_illusions()
        
        # Level 25: Fear paralysis - handled in process_turn_with_fear_mechanics()
        
        # Level 28: Final enemy immunity until growth requirement met
        if self.level == 28 and combatant in self.enemy_team.combatants:
            if self.current_opponent_index == len(self.enemy_team.combatants) - 1:  # Final enemy
                if not self.final_enemy_vulnerable:
                    await self.add_to_log(f"🛡️ **PROTECTED BY STAGNATION!** The final enemy cannot be harmed until you grow together!")
                    return False
        
        # Level 29: Allow dead spirits to heal only
        if self.level == 29 and not combatant.is_alive():
            return True  # Dead spirits can still heal
            
        return True

    async def is_battle_over(self):
        """Override to handle couples tower death conditions and level-specific victory conditions"""
        # Check if battle was already marked as finished (e.g., by forge heat death)
        if getattr(self, 'finished', False):
            return True
        
        # Level 30: No combat, battle is immediately over
        if self.level == 30:
            return True
        
        # Level 23: Special possession victory/defeat conditions
        if self.level == 23:
            try:
                # Victory: Truth Demon is dead (killed by surviving 20 turns)
                if self.truth_demon and not self.truth_demon.is_alive():
                    return True
                    
                # Victory: Survived all possession turns
                if self.possession_turns >= self.possession_turn_limit:
                    return True
                    
                # Defeat: Either partner died
                if not self.possessed_partner.is_alive() or not self.defender_partner.is_alive():
                    self.finished = True
                    return True
                    
                return False
            except Exception as e:
                await self.ctx.send(f"Level 23 Battle Over Check Error: {e}")
                import traceback
                await self.ctx.send(f"```{traceback.format_exc()}```")
                self.finished = True
                return True
        
        # UNIVERSAL COUPLES TOWER RULE: If either partner dies, battle ends immediately (except Level 29 spirit healing)
        partners = [c for c in self.player_team.combatants if not c.is_pet]
        if self.level != 29:  # Level 29 allows spirit healing of dead partners
            if any(not partner.is_alive() for partner in partners):
                # Mark battle as finished to prevent victory declaration
                self.finished = True
                await self.add_to_log(f"💔 **LOVE CONQUERS DEATH** 💔\n*The battle ends immediately. In love, you succeed together or fail together - one cannot carry on without the other.*")
                return True
        
        # Level 5: Special split combat conditions - Partner death takes priority over ALL other checks
        if self.level == 5 and self.split_combat_initialized:
            # FIRST: Check if any partner died (immediate defeat)
            if any(not partner.is_alive() for partner in partners):
                self.finished = True
                await self.add_to_log(f"💔 **SPLIT COMBAT FAILURE** 💔\n*You were meant to protect what matters most - each other. Without both partners, the mission has failed.*")
                return True
            
            # SECOND: Check victory only if ALL enemies are defeated AND both partners are alive
            if all(not e.is_alive() for e in self.enemy_team.combatants):
                await self.add_to_log(f"💕 **MISSION COMPLETE!** Together, you have protected everything precious to your love!")
                return True
                
            # THIRD: Battle continues
            return False
        
        # Level 29: Special spirit healing rules
        if self.level == 29:
            # Battle only ends if BOTH partners are dead (no spirit healing possible)
            if all(not partner.is_alive() for partner in partners):
                self.finished = True
                await self.add_to_log(f"👻 **SPIRITS FADE** 👻\n*Even in death, your spirits could not sustain each other...*")
                return True
        
        # Check if all enemies are defeated (victory condition)
        if self.enemy_team.combatants and all(not e.is_alive() for e in self.enemy_team.combatants):
            # For Level 29: Victory if enemies are defeated (spirit healing allows one dead partner)
            if self.level == 29:
                # Level 29 allows victory even with one dead partner (spirit healing)
                await self.add_to_log(f"💕 **SPIRIT VICTORY** 💕\n*Though one heart has stopped, the spirit of love endures and guides you to victory!*")
                return True
            # For other levels: Double-check partners are still alive before declaring victory
            elif all(partner.is_alive() for partner in partners):
                # Let parent class handle victory
                return True
            else:
                # Partners died at same time as enemies - defeat takes priority
                self.finished = True
                await self.add_to_log(f"💔 **PYRRHIC DEFEAT** 💔\n*Though the enemies fall, love cannot survive without both hearts beating.*")
                return True
        elif not self.enemy_team.combatants:
            # No enemies at all (like Level 30) - this is handled elsewhere
            return True
        
        # Use parent class logic for other conditions
        return await super().is_battle_over()

    async def end_battle(self):
        """Override to respect couples tower defeat logic"""
        # Special handling for Level 30 - no battle, just ceremony
        if self.level == 30:
            # Level 30 is always a victory (ceremony completion)
            await self.save_battle_to_database()
            return self.player_team
        
        # If battle was marked as finished due to defeat, return None (no winner)
        if getattr(self, 'finished', False):
            # Save final battle state to database for replay
            await self.save_battle_to_database()
            return None  # Defeat - no winning team
        
        # Otherwise use parent class logic for determining winner
        return await super().end_battle()

    async def get_turn_delay(self):
        """Get turn delay based on level"""
        if self.level == 9:  # Patience test
            return 4  # Double the normal delay
        return 2  # Normal delay 

    async def create_multi_enemy_embed(self):
        """Special embed for levels with multiple active enemies like Level 13"""
        embed = discord.Embed(
            title=f"Couples Battle Tower: Level {self.level} - The Maze of Misunderstanding",
            description="🗣️ **Multiple Confusion Sprites swirl around you, making coordination deadly!** 🗣️",
            color=discord.Color.orange()
        )
        
        # Get element emoji mapping
        element_emoji_map = {}
        if hasattr(self.ctx.bot.cogs["Battles"], "emoji_to_element"):
            element_emoji_map = self.ctx.bot.cogs["Battles"].emoji_to_element
            
        # Add player team info (both partners)
        embed.add_field(name="💕 **LOVE TEAM** 💕", value="", inline=False)
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
                field_name = f"🐾 {combatant.name} {element_emoji}"
            else:
                field_name = f"💑 {combatant.display_name} {element_emoji}"
                
            # Create field value with HP bar
            field_value = f"HP: {current_hp:.1f}/{max_hp:.1f}\n{hp_bar}"
            embed.add_field(name=field_name, value=field_value, inline=True)
        
        # Add all enemies info
        embed.add_field(name="", value="", inline=False)  # Spacer
        embed.add_field(name="👹 **CONFUSION SPRITES** 👹", value="", inline=False)
        
        alive_enemies = []
        dead_enemies = []
        
        for i, enemy in enumerate(self.enemy_team.combatants):
            current_hp = max(0, float(enemy.hp))
            max_hp = float(enemy.max_hp)
            hp_bar = self.create_hp_bar(current_hp, max_hp)
            
            # Get element emoji for enemy
            element_emoji = "❌"
            for emoji, element in element_emoji_map.items():
                if element == enemy.element:
                    element_emoji = emoji
                    break
            
            enemy_info = f"**{enemy.name} #{i+1}** {element_emoji}\nHP: {current_hp:.1f}/{max_hp:.1f}\n{hp_bar}"
            
            if enemy.is_alive():
                alive_enemies.append(enemy_info)
            else:
                dead_enemies.append(f"~~{enemy_info}~~ 💀")
        
        # Show alive enemies first, then dead ones
        all_enemy_info = alive_enemies + dead_enemies
        
        # Split into columns if there are many enemies
        if len(all_enemy_info) <= 3:
            # Show in single column
            embed.add_field(name="Active Sprites", value="\n\n".join(all_enemy_info), inline=False)
        else:
            # Split into two columns
            half = len(all_enemy_info) // 2
            left_column = all_enemy_info[:half + (len(all_enemy_info) % 2)]
            right_column = all_enemy_info[half + (len(all_enemy_info) % 2):]
            
            embed.add_field(name="Sprites (1)", value="\n\n".join(left_column), inline=True)
            embed.add_field(name="Sprites (2)", value="\n\n".join(right_column), inline=True)
        
        # Add battle log
        log_text = self.format_battle_log()
        embed.add_field(name="Battle Log", value=log_text or "Battle starting...", inline=False)
        
        # Add battle ID to footer for GM replay functionality
        embed.set_footer(text=f"Battle ID: {self.battle_id}")
        
        return embed

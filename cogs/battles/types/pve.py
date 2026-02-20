# battles/types/pve.py
import asyncio
import random
from decimal import Decimal
import discord
import datetime

from ..core.battle import Battle

class PvEBattle(Battle):
    """Player vs Environment (monster) battle implementation"""
    GOD_OF_GODS_TIER = 12
    ADAPTIVE_ELEMENTS = (
        "Light",
        "Dark",
        "Corrupted",
        "Nature",
        "Electric",
        "Water",
        "Fire",
        "Wind",
    )
    
    def __init__(self, ctx, teams, **kwargs):
        super().__init__(ctx, teams, **kwargs)
        self.player_team = teams[0]
        self.monster_team = teams[1]
        self.monster_level = kwargs.get("monster_level", 1)
        self.macro_penalty_level = kwargs.get("macro_penalty_level", 0)
        self.current_turn = 0
        self.attacker = None
        self.defender = None
        self.turn_order = []
        
        # Load all battle settings
        settings_cog = self.ctx.bot.get_cog("BattleSettings")
        if settings_cog:
            # Ensure all settings are loaded, with defaults if not found
            self.config = {
                "allow_pets": settings_cog.get_setting("pve", "allow_pets", default=True),
                "class_buffs": settings_cog.get_setting("pve", "class_buffs", default=True),
                "element_effects": settings_cog.get_setting("pve", "element_effects", default=True),
                "luck_effects": settings_cog.get_setting("pve", "luck_effects", default=True),
                "reflection_damage": settings_cog.get_setting("pve", "reflection_damage", default=True),
                "fireball_chance": settings_cog.get_setting("pve", "fireball_chance", default=0.3),
                "cheat_death": settings_cog.get_setting("pve", "cheat_death", default=True),
                "tripping": settings_cog.get_setting("pve", "tripping", default=True),
                "status_effects": settings_cog.get_setting("pve", "status_effects", default=False),
                "pets_continue_battle": settings_cog.get_setting("pve", "pets_continue_battle", default=False)
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
        
    async def start_battle(self):
        """Initialize and start the battle"""
        self.started = True
        self.start_time = datetime.datetime.utcnow()
        
        # Save initial battle data to database for replay
        await self.save_battle_to_database()
        
        monster_name = self.monster_team.combatants[0].name
        await self.add_to_log(f"Battle against {monster_name} started!")
        await self._handle_godofgods_adaptive_element()
        
        # Determine turn order (randomized)
        self.turn_order = []
        for team in self.teams:
            for combatant in team.combatants:
                self.turn_order.append(combatant)
        
        random.shuffle(self.turn_order)
        self.turn_order = self.prioritize_turn_order(self.turn_order)
        
        # Create and send initial battle embed
        embed = await self.create_battle_embed()
        self.battle_message = await self.ctx.send(embed=embed)
        await asyncio.sleep(2)
        
        return True

    def _normalize_element(self, element):
        if not element:
            return "Unknown"
        return str(element).strip().capitalize()

    def _pick_strongest_counter_element(self, enemy_elements, current_element):
        battles_cog = self.ctx.bot.get_cog("Battles")
        element_ext = getattr(battles_cog, "element_ext", None) if battles_cog else None
        strengths = getattr(element_ext, "element_strengths", {}) if element_ext else {}

        if not strengths:
            return current_element

        normalized_enemies = []
        for element in enemy_elements:
            normalized = self._normalize_element(element)
            if normalized != "Unknown":
                normalized_enemies.append(normalized)
        if not normalized_enemies:
            return current_element

        def score(candidate_element):
            total = 0
            for enemy_element in normalized_enemies:
                if strengths.get(candidate_element) == enemy_element:
                    total += 2
                if strengths.get(enemy_element) == candidate_element:
                    total -= 1
            return total

        best_element = current_element
        best_score = score(current_element)

        for candidate in self.ADAPTIVE_ELEMENTS:
            candidate_score = score(candidate)
            if candidate_score > best_score:
                best_score = candidate_score
                best_element = candidate

        return best_element

    async def _handle_godofgods_adaptive_element(self):
        if int(self.monster_level or 0) != self.GOD_OF_GODS_TIER:
            return
        if not self.monster_team.combatants:
            return

        boss = self.monster_team.combatants[0]
        old_element = self._normalize_element(
            getattr(boss, "attack_element", getattr(boss, "element", "Unknown"))
        )
        enemy_elements = [
            self._normalize_element(self.resolve_defense_element(combatant))
            for combatant in self.player_team.combatants
            if combatant.is_alive()
        ]
        new_element = self._pick_strongest_counter_element(enemy_elements, old_element)
        boss.element = new_element
        boss.attack_element = new_element
        boss.defense_element = new_element

        battles_cog = self.ctx.bot.get_cog("Battles")
        element_ext = getattr(battles_cog, "element_ext", None) if battles_cog else None
        element_to_emoji = getattr(element_ext, "element_to_emoji", {}) if element_ext else {}
        old_emoji = element_to_emoji.get(old_element, "❓")
        new_emoji = element_to_emoji.get(new_element, "❓")

        target_hint = ", ".join(sorted(set(enemy_elements))) if enemy_elements else "your team"
        if new_element != old_element:
            description = (
                f"{boss.name}'s chest crystal glows with ancient light.\n"
                f"It attunes against **{target_hint}** and shifts from "
                f"**{old_emoji} {old_element}** to **{new_emoji} {new_element}**."
            )
        else:
            description = (
                f"{boss.name}'s chest crystal glows with ancient light.\n"
                f"It attunes against **{target_hint}** and stabilizes as "
                f"**{new_emoji} {new_element}**."
            )

        embed = discord.Embed(
            title="💠 Crystal Adaptation",
            description=description,
            color=discord.Color.gold(),
        )
        await self.ctx.send(embed=embed)
        await self.add_to_log(
            f"{boss.name}'s chest crystal glowed and adapted its element to {new_element}."
        )
    
    async def process_turn(self):
        """Process a single turn of the battle"""
        if await self.is_battle_over():
            return False
        
        # Get attacker for this turn
        self.attacker = self.turn_order[self.current_turn % len(self.turn_order)]
        
        # Skip if attacker is dead
        if not self.attacker.is_alive():
            self.current_turn += 1
            return True
        
        # Determine which team the attacker is on
        attacker_team = None
        for team in self.teams:
            if self.attacker in team.combatants:
                attacker_team = team
                break
        
        # Get the opposing team
        defending_team = self.monster_team if attacker_team == self.player_team else self.player_team
        
        # Get an alive defender from the defending team
        alive_defenders = [c for c in defending_team.combatants if c.is_alive()]
        if not alive_defenders:
            return False
        
        self.defender = random.choice(alive_defenders)
        
        # No separate tripping check here - we'll handle it in the hit/miss logic below
        
        # Different hit/miss logic for monsters and players
        hits = True
        
        if self.attacker in self.monster_team.combatants:
            # Monsters: 10% chance to miss
            if random.random() < 0.10:
                hits = False
        else:
            # Players: Use luck-based system
            luck_roll = random.randint(1, 100)
            
            # Check for perfect accuracy from Night Vision skill
            has_perfect_accuracy = getattr(self.attacker, 'perfect_accuracy', False)
            if not has_perfect_accuracy and luck_roll > self.attacker.luck:
                hits = False
        
        if hits:
            # Attack hits
            blocked_damage = Decimal("0")
            
            # Special case for mage fireball
            used_fireball = False
            if (self.attacker.mage_evolution and 
                not self.attacker.is_pet and 
                self.config["class_buffs"] and
                random.random() < self.config["fireball_chance"]):
                
                # Calculate fireball damage
                evolution_level = self.attacker.mage_evolution
                damage_multiplier = {
                    1: 1.10,  # 110%
                    2: 1.20,  # 120%
                    3: 1.30,  # 130%
                    4: 1.50,  # 150%
                    5: 1.75,  # 175%
                    6: 2.00,  # 200%
                }.get(evolution_level, 1.0)
                
                damage = (self.attacker.damage + Decimal(random.randint(0, 100)) - self.defender.armor) * Decimal(str(damage_multiplier))
                damage = max(damage, Decimal('10'))
                
                self.defender.take_damage(damage)
                
                message = f"{self.attacker.name} casts Fireball! {self.defender.name} takes **{self.format_number(damage)} HP** damage."
                used_fireball = True
            else:
                # Regular attack
                damage_variance = random.randint(0, 50) if self.attacker.is_pet else random.randint(0, 100)
                
                # Start with base damage
                raw_damage = self.attacker.damage
                outcome = self.resolve_pet_attack_outcome(
                    self.attacker,
                    self.defender,
                    raw_damage,
                    apply_element_mod=self.config["element_effects"],
                    damage_variance=damage_variance,
                    minimum_damage=Decimal("10"),
                )
                damage = outcome.final_damage
                blocked_damage = outcome.blocked_damage
                skill_messages = outcome.skill_messages
                defender_messages = outcome.defender_messages
                
                self.defender.take_damage(damage)
                
                message = f"{self.attacker.name} attacks! {self.defender.name} takes **{self.format_number(damage)} HP** damage."
                
                # Add skill effect messages
                if skill_messages:
                    message += "\n" + "\n".join(skill_messages)
                if defender_messages:
                    message += "\n" + "\n".join(defender_messages)
                    
                # Check for skeleton summoning after skill processing
                if hasattr(self.attacker, 'summon_skeleton'):
                    skeleton_data = self.attacker.summon_skeleton
                    
                    # Create skeleton combatant
                    from cogs.battles.core.combatant import Combatant
                    skeleton = Combatant(
                        user=f"Skeleton Warrior #{self.attacker.skeleton_count}",  # User/name
                        hp=skeleton_data['hp'],
                        max_hp=skeleton_data['hp'],  # Same as current HP
                        damage=skeleton_data['damage'],
                        armor=skeleton_data['armor'],
                        element=skeleton_data['element'],
                        luck=50,  # Base luck
                        is_pet=True,
                        name=f"Skeleton Warrior #{self.attacker.skeleton_count}"
                    )
                    skeleton.is_summoned = True
                    skeleton.summoner = self.attacker
                    
                    # Add skeleton to player team
                    self.player_team.combatants.append(skeleton)
                    # Also add to turn order
                    self.turn_order.append(skeleton)
                    self.turn_order = self.prioritize_turn_order(self.turn_order)
                    message += f"\n💀 A skeleton warrior joins your side!"
                    
                    # Clear the summon flag
                    delattr(self.attacker, 'summon_skeleton')
            
            # Handle lifesteal if applicable
            if (self.config["class_buffs"] and 
                not self.attacker.is_pet and 
                self.attacker.lifesteal_percent > 0):
                
                lifesteal_amount = (float(damage) * float(self.attacker.lifesteal_percent) / 100.0)
                self.attacker.heal(lifesteal_amount)
                message += f" Lifesteals: **{self.format_number(lifesteal_amount)} HP**"
            
            # Handle damage reflection if applicable
            # Apply tank evolution reflection multiplier if applicable
            reflection_value = self.defender.damage_reflection
            
            # Apply tank evolution-based reflection if defender has tank evolution
            if self.config["class_buffs"] and self.defender.tank_evolution and not self.defender.is_pet:
                # Use the standard tank evolution reflection multiplier from classes.py
                tank_reflection = 0.03 * self.defender.tank_evolution  # 3% per level, so 21% at level 7
                reflection_value = max(reflection_value, tank_reflection)  # Use higher of item reflection or tank reflection
            

            
            if (self.config["reflection_damage"] and 
                reflection_value > 0 and 
                blocked_damage > 0):
                
                reflected = blocked_damage * Decimal(str(reflection_value))
                self.attacker.take_damage(reflected)
                message += f"\n{self.defender.name}'s armor reflects **{self.format_number(reflected)} HP** damage back!"
                
                if not self.attacker.is_alive():
                    message += f" {self.attacker.name} has been defeated by reflected damage!"
            
            # Check if defender is defeated
            if not self.defender.is_alive():
                # Check for cheat death ability
                if (self.config["class_buffs"] and 
                    self.config["cheat_death"] and
                    not self.defender.is_pet and 
                    self.defender.death_cheat_chance > 0 and
                    not self.defender.has_cheated_death):
                    
                    cheat_roll = random.randint(1, 100)
                    if cheat_roll <= self.defender.death_cheat_chance:
                        self.defender.hp = Decimal('75')
                        self.defender.has_cheated_death = True
                        message += f"\n{self.defender.name} cheats death and survives with **75 HP**!"
                    else:
                        message += f" {self.defender.name} has been defeated!"
                else:
                    message += f" {self.defender.name} has been defeated!"
        else:
            # Attack misses
            if self.config.get("tripping", False):
                if self.attacker in self.player_team.combatants:
                    # Players: Always trip on miss
                    damage = Decimal('10')
                    self.attacker.take_damage(damage)
                    message = f"{self.attacker.name} tripped and took **{self.format_number(damage)} HP** damage. Bad luck!"
                else:
                    # Monsters have already had their 10% miss chance applied earlier
                    # When they miss, they always trip (since total miss+trip is 10%)
                    damage = Decimal('10')
                    self.attacker.take_damage(damage)
                    message = f"{self.attacker.name} tripped and took **{self.format_number(damage)} HP** damage."
            else:
                message = f"{self.attacker.name}'s attack missed!"
        
        # Add message to battle log
        await self.add_to_log(message)
        
        # PROCESS PET SKILL EFFECTS PER TURN
        if hasattr(self.ctx.bot.cogs["Battles"], "battle_factory"):
            pet_ext = self.ctx.bot.cogs["Battles"].battle_factory.pet_ext
            
            # Process player team combatants
            for combatant in self.player_team.combatants:
                if combatant.is_pet and combatant.is_alive():
                    # Set team references for skills that need them
                    setattr(combatant, 'team', self.player_team)
                    setattr(combatant, 'enemy_team', self.monster_team)
                    
                    # Process per-turn effects
                    turn_messages = pet_ext.process_skill_effects_per_turn(combatant)
                    if turn_messages:
                        for turn_msg in turn_messages:
                            await self.add_to_log(turn_msg)
                    
            # Process monster team combatants (if any pets)
            for combatant in self.monster_team.combatants:
                if combatant.is_pet and combatant.is_alive():
                    # Set team references for skills that need them  
                    setattr(combatant, 'team', self.monster_team)
                    setattr(combatant, 'enemy_team', self.player_team)
                    
                    # Process per-turn effects
                    turn_messages = pet_ext.process_skill_effects_per_turn(combatant)
                    if turn_messages:
                        for turn_msg in turn_messages:
                            await self.add_to_log(turn_msg)
        
        # Check for death from turn effects
        if not self.defender.is_alive():
            # Mark if pet killed an enemy for Soul Harvest
            if self.attacker.is_pet:
                setattr(self.attacker, 'killed_enemy_this_turn', True)
        
        # Update the battle display
        await self.update_display()
        await asyncio.sleep(1)
        
        # Move to next turn
        self.current_turn += 1
        
        return True
    
    async def create_battle_embed(self):
        """Create the battle status embed"""
        monster_name = self.monster_team.combatants[0].name
        embed = discord.Embed(
            title=f"PvE Battle: {self.ctx.author.display_name} vs {monster_name}",
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
            
            field_name = f"**[TEAM A]** \n{combatant.name} {element_emoji}"
            field_value = f"HP: {current_hp:.1f}/{max_hp:.1f}\n{hp_bar}"
            
            # Add reflection info if applicable
            if combatant.damage_reflection > 0:
                reflection_percent = float(combatant.damage_reflection) * 100
                field_value += f"\nDamage Reflection: {reflection_percent:.1f}%"
                
            embed.add_field(name=field_name, value=field_value, inline=False)
        
        # Add monster team info
        for combatant in self.monster_team.combatants:
            current_hp = max(0, float(combatant.hp))
            max_hp = float(combatant.max_hp)
            hp_bar = self.create_hp_bar(current_hp, max_hp)
            
            # Get element emoji
            element_emoji = "❌"
            for emoji, element in element_emoji_map.items():
                if element == combatant.element:
                    element_emoji = emoji
                    break
            
            field_name = f"**[TEAM B]** \n{combatant.name} {element_emoji}"
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
        """End the battle and determine rewards"""
        self.finished = True
        
        # Check if it's a timeout/tie
        if await self.is_timed_out():
            await self.ctx.send("The battle ended in a draw due to timeout.")
            # Save final battle state to database for replay
            await self.save_battle_to_database()
            return None
        
        # Determine winner
        if all(not c.is_alive() for c in self.player_team.combatants):
            # Player lost
            await self.ctx.send(
                f"You were defeated by the **{self.monster_team.combatants[0].name}**. Better luck next time!"
            )
            # Save final battle state to database for replay
            await self.save_battle_to_database()
            return self.monster_team
        else:
            # Player won - calculate XP reward
            if self.monster_level == 11:  # Legendary monster
                xp_gain = random.randint(75000, 125000)
            else:
                xp_gain = random.randint(self.monster_level * 300, self.monster_level * 1000)
            
            # Apply macro penalty if active (count >= 12)
            if self.macro_penalty_level >= 12:
                xp_gain = xp_gain // 10  # Divide XP by 10
            
            # Award XP
            async with self.ctx.bot.pool.acquire() as conn:
                await conn.execute(
                    'UPDATE profile SET "xp" = "xp" + $1 WHERE "user" = $2;',
                    xp_gain,
                    self.ctx.author.id,
                )

            # Award pet battle XP to equipped/only pet with a daily cap.
            pet_battle_result = None
            pets_cog = self.ctx.bot.get_cog("Pets")
            if pets_cog:
                pet_tier = max(1, int(self.monster_level or 1))
                pet_battle_xp = (
                    pets_cog.PET_BATTLE_XP_BASE
                    + (pets_cog.PET_BATTLE_XP_PER_TIER * pet_tier)
                )
                if self.macro_penalty_level >= 12:
                    pet_battle_xp = max(1, pet_battle_xp // 10)
                pet_battle_result = await pets_cog.award_battle_experience_for_user(
                    self.ctx.author.id,
                    pet_battle_xp,
                    trust_gain=1,
                )
            
            # Award crafting resources based on monster level (skip if macro penalty active)
            crafting_resources_awarded = []
            if self.macro_penalty_level == 0:  # Only give materials if no macro penalty
                amulet_cog = self.ctx.bot.get_cog("AmuletCrafting")
                if amulet_cog:
                    # Determine number of resources based on monster level (reduced amounts)
                    if self.monster_level == 11:  # Legendary monster
                        resource_count = random.randint(2, 3)
                        amount_range = (1, 2)
                    elif self.monster_level >= 8:  # High level monsters
                        resource_count = random.randint(1, 2)
                        amount_range = (1, 2)
                    elif self.monster_level >= 5:  # Mid level monsters
                        resource_count = 1
                        amount_range = (1, 2)
                    else:  # Low level monsters
                        # 70% chance to get 1 resource, 30% chance to get nothing
                        if random.random() < 0.7:
                            resource_count = 1
                            amount_range = (1, 1)
                        else:
                            resource_count = 0
                            amount_range = (0, 0)
                    
                    # Award multiple random resources
                    for _ in range(resource_count):
                        resource_name, amount = await amulet_cog.give_random_resource(
                            self.ctx.author.id,
                            amount_range=amount_range,
                            category=None,  # Any category
                            respect_level=True  # Respect player level for resource rarity
                        )
                        
                        if resource_name:
                            display_name = resource_name.replace('_', ' ').title()
                            crafting_resources_awarded.append(f"{amount}x {display_name}")
            
            # Create victory message with both XP and resources
            victory_message = f"You defeated the **{self.monster_team.combatants[0].name}** and gained **{xp_gain} XP**!"
            
            if crafting_resources_awarded:
                resources_text = ", ".join(crafting_resources_awarded)
                victory_message += f"\n🔨 **Crafting Resources Found:** {resources_text}"

            if pet_battle_result:
                awarded_pet_xp = int(pet_battle_result.get("awarded_xp", 0) or 0)
                pet_name = pet_battle_result.get("pet_name", "your pet")
                if awarded_pet_xp > 0:
                    pet_line = f"\n🐾 **Pet XP:** **+{awarded_pet_xp}** to **{pet_name}**"
                    if pet_battle_result.get("leveled_up"):
                        pet_line += f" (Level {pet_battle_result.get('new_level')})"
                    if pet_battle_result.get("cap_reached"):
                        pet_line += " - daily battle XP cap reached."
                    victory_message += pet_line
                elif pet_battle_result.get("reason") == "daily_cap_reached":
                    victory_message += "\n🐾 **Pet XP:** Daily battle XP cap already reached today."
            
            await self.ctx.send(victory_message)
            
            # Check for level up
            from utils import misc as rpgtools
            player_xp = self.ctx.character_data.get("xp", 0)
            player_level = rpgtools.xptolevel(player_xp)
            new_level = rpgtools.xptolevel(player_xp + xp_gain)
            
            if new_level > player_level:
                await self.ctx.bot.process_levelup(self.ctx, new_level, player_level)
            
            # Dispatch PVE completion event
            self.ctx.bot.dispatch("PVE_completion", self.ctx, True)
            
            # Save final battle state to database for replay
            await self.save_battle_to_database()
            
            return self.player_team
    
    async def is_battle_over(self):
        """Check if the battle is over"""
        # Battle is over if one team is completely defeated
        player_defeated = all(not c.is_alive() for c in self.player_team.combatants)
        monster_defeated = all(not c.is_alive() for c in self.monster_team.combatants)
        
        return player_defeated or monster_defeated or await self.is_timed_out() or self.finished

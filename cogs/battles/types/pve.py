# battles/types/pve.py
import asyncio
import random
from decimal import Decimal
import discord
import datetime

from ..core.battle import Battle
from utils.april_fools import get_pet_display_name, is_greg_mode_enabled

class PvEBattle(Battle):
    """Player vs Environment (monster) battle implementation"""
    GOD_OF_GODS_TIER = 12
    GREG_OPENING_LINES = (
        "A black bell tolls in the distance, and every peal seems to say: Greg. Greg. Greg.",
        "The grave-wind carries a single name through the dark: Greg.",
        "Something in the wild has forgotten itself. It remembers only Greg.",
        "The road falls silent as the Gregbound stir beyond the fog, each insisting they are Greg.",
        "This creature's true name has withered. The curse leaves only Greg behind.",
        "Ash drifts through the air as if some buried ledger has turned another page and written Greg again.",
        "The creature lurches forward as though eager to introduce itself as Greg.",
        "Even the crows cry the same word tonight: Greg.",
        "A torn name-tag flutters in the mud. Upon it, in shaky ink, is written Greg.",
        "From somewhere beneath the earth comes a muffled chant: Greg... Greg... Greg...",
    )
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
        hp_bar_style = kwargs.get(
            "hp_bar_style",
            "colorful" if kwargs.get("emoji_hp_bars", False) else "normal",
        )
        normalized_hp_bar_style = self.normalize_hp_bar_style(hp_bar_style)
        if settings_cog:
            # Ensure all settings are loaded, with defaults if not found
            self.config = {
                "allow_pets": settings_cog.get_setting("pve", "allow_pets", default=True),
                "class_buffs": settings_cog.get_setting("pve", "class_buffs", default=True),
                "element_effects": settings_cog.get_setting("pve", "element_effects", default=True),
                "luck_effects": settings_cog.get_setting("pve", "luck_effects", default=True),
                "reflection_damage": settings_cog.get_setting("pve", "reflection_damage", default=True),
                "hp_bar_style": normalized_hp_bar_style,
                "emoji_hp_bars": normalized_hp_bar_style != self.HP_BAR_STYLE_NORMAL,
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
                "hp_bar_style": normalized_hp_bar_style,
                "emoji_hp_bars": normalized_hp_bar_style != self.HP_BAR_STYLE_NORMAL,
                "fireball_chance": 0.3,
                "cheat_death": True,
                "tripping": True,
                "status_effects": False,
                "pets_continue_battle": False
            }

        if int(self.monster_level or 0) == self.GOD_OF_GODS_TIER:
            self.config["tripping"] = False

    def _get_greg_opening_lines(self):
        if not is_greg_mode_enabled(self.ctx.bot):
            return []

        line_count = 2 if random.random() < 0.30 else 1
        return random.sample(self.GREG_OPENING_LINES, k=line_count)
        
    async def start_battle(self):
        """Initialize and start the battle"""
        self.started = True
        self.start_time = datetime.datetime.utcnow()
        
        # Save initial battle data to database for replay
        await self.save_battle_to_database()
        
        monster_name = self.monster_team.combatants[0].name
        await self.add_to_log(f"Battle against {monster_name} started!")
        for greg_line in self._get_greg_opening_lines():
            await self.add_to_log(greg_line)
        await self._handle_godofgods_adaptive_element()
        await self._announce_omnithrone_allies()
        
        # Determine turn order (randomized)
        self.turn_order = []
        for team in self.teams:
            for combatant in team.combatants:
                self.turn_order.append(combatant)
        
        random.shuffle(self.turn_order)
        self.turn_order = self.prioritize_turn_order(self.turn_order)

        for opening_message in await self.trigger_ascension_openings():
            await self.add_to_log(opening_message)
        
        # Create and send initial battle embed
        embed = await self.create_battle_embed()
        self.battle_message = await self.publish_battle_message(embed=embed)
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
        await self.send_with_retry(embed=embed)
        await self.add_to_log(
            f"{boss.name}'s chest crystal glowed and adapted its element to {new_element}."
        )

    def _get_omnithrone_allies(self):
        return [
            combatant
            for combatant in self.player_team.combatants
            if getattr(combatant, "is_omnithrone_ally", False)
        ]

    async def _announce_omnithrone_allies(self):
        god_allies = self._get_omnithrone_allies()
        if not god_allies:
            return

        god_names = ", ".join(combatant.name for combatant in god_allies)
        embed = discord.Embed(
            title="Oath of the Three",
            description=f"{god_names} join your side and enter the battle as allied combatants.",
            color=discord.Color.gold(),
        )
        await self.send_with_retry(embed=embed)
        await self.add_to_log(f"{god_names} join your side.")
    
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

        silenced_message = self.consume_ascension_action_lock(self.attacker)
        if silenced_message:
            await self.add_to_log(silenced_message)
            await self.update_display()
            await asyncio.sleep(1)
            self.current_turn += 1
            return True

        locked_message = self.consume_pet_skill_action_lock(self.attacker)
        if locked_message:
            await self.add_to_log(locked_message)
            await self.update_display()
            await asyncio.sleep(1)
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
        
        guard_source = None

        if hits:
            # Attack hits
            blocked_damage = Decimal("0")
            ignore_reflection_this_hit = False
            mage_charge_state = self.advance_mage_fireball_charge(self.attacker)
            
            used_fireball = False
            if mage_charge_state and mage_charge_state["fireball_ready"]:
                damage = self.calculate_mage_fireball_damage(
                    self.attacker,
                    self.defender,
                    damage_variance=100,
                    minimum_damage=Decimal("10"),
                )
                ignore_reflection_this_hit = True

                damage, guard_messages, guard_source = self.apply_pet_owner_guard(
                    self.attacker,
                    self.defender,
                    damage,
                )
                self.defender.take_damage(damage)
                message = f"{self.attacker.name} casts Fireball! {self.defender.name} takes **{self.format_number(damage)} HP** damage."
                if guard_messages:
                    message += "\n" + "\n".join(guard_messages)
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
                ignore_reflection_this_hit = bool(outcome.metadata.get("ignore_reflection_this_hit", False))

                damage, guard_messages, guard_source = self.apply_pet_owner_guard(
                    self.attacker,
                    self.defender,
                    damage,
                )
                self.defender.take_damage(damage)
                message = f"{self.attacker.name} attacks! {self.defender.name} takes **{self.format_number(damage)} HP** damage."
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
                queued_summons = getattr(self.attacker, 'summon_skeleton_queue', None)
                if not queued_summons and hasattr(self.attacker, 'summon_skeleton'):
                    queued_summons = [self.attacker.summon_skeleton]
                if queued_summons:
                    from cogs.battles.core.combatant import Combatant

                    for skeleton_data in list(queued_summons):
                        skeleton_serial = skeleton_data.get(
                            'serial',
                            getattr(self.attacker, 'skeleton_count', 1),
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
                        self.register_summoned_combatant(
                            skeleton,
                            team=self.player_team,
                            summoner=self.attacker,
                        )

                        self.player_team.combatants.append(skeleton)
                        self.turn_order.append(skeleton)
                        self.turn_order = self.prioritize_turn_order(self.turn_order)
                        message += f"\n💀 Skeleton Warrior #{skeleton_serial} joins your side!"

                    if hasattr(self.attacker, 'summon_skeleton_queue'):
                        delattr(self.attacker, 'summon_skeleton_queue')
                    if hasattr(self.attacker, 'summon_skeleton'):
                        delattr(self.attacker, 'summon_skeleton')

            grave_message = await self.maybe_trigger_grave_sovereign(
                self.attacker,
                self.defender,
            )
            if grave_message:
                message += "\n" + grave_message

            cycle_message = await self.maybe_trigger_cyclebreaker(
                self.defender,
                self.attacker,
            )
            if cycle_message:
                message += "\n" + cycle_message
            
            # Handle lifesteal if applicable
            if (self.config["class_buffs"] and 
                not self.attacker.is_pet and 
                self.attacker.lifesteal_percent > 0):
                
                lifesteal_amount = (float(damage) * float(self.attacker.lifesteal_percent) / 100.0)
                self.attacker.heal(lifesteal_amount)
                message += f" Lifesteals: **{self.format_number(lifesteal_amount)} HP**"

            bonus_lifesteal = self.apply_bonus_lifesteal(self.attacker, damage)
            if bonus_lifesteal > 0:
                message += f"\n{self.attacker.name} drains **{self.format_number(bonus_lifesteal)} HP** from empowered lifesteal!"
            
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
                blocked_damage > 0 and
                not ignore_reflection_this_hit):
                
                reflected = blocked_damage * Decimal(str(reflection_value))
                self.attacker.take_damage(reflected)
                message += f"\n{self.defender.name}'s armor reflects **{self.format_number(reflected)} HP** damage back!"
                
                if not self.attacker.is_alive():
                    message += f" {self.attacker.name} has been defeated by reflected damage!"

            class_messages = self.resolve_post_hit_class_effects(self.attacker, self.defender)
            if class_messages:
                message += "\n" + "\n".join(class_messages)
            
            # Check if defender is defeated
            if not self.defender.is_alive():
                guardian_message = self.maybe_trigger_guardian_angel(self.defender)
                if guardian_message:
                    message += f"\n{guardian_message}"
                # Check for cheat death ability
                if self.defender.is_alive():
                    pass
                elif (self.config["class_buffs"] and 
                    self.config["cheat_death"] and
                    not self.defender.is_pet and 
                    self.defender.death_cheat_chance > 0 and
                    not self.defender.has_cheated_death):
                    
                    cheat_roll = random.randint(1, 100)
                    if cheat_roll <= self.defender.death_cheat_chance:
                        self.defender.hp = self.get_cheat_death_recovery_hp(self.defender)
                        self.defender.has_cheated_death = True
                        message += (
                            f"\n{self.defender.name} cheats death and survives with "
                            f"**{self.format_number(self.defender.hp)} HP**!"
                        )
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

        if self.attacker.is_pet and not self.defender.is_alive():
            setattr(self.attacker, 'killed_enemy_this_turn', True)

        for combatant in (self.defender, self.attacker, guard_source):
            if combatant is None or not getattr(combatant, "is_pet", False) or combatant.is_alive():
                continue
            for death_msg in self.process_pet_death_effects(combatant):
                await self.add_to_log(death_msg)

        if self.attacker.is_pet and self.attacker.is_alive():
            for turn_msg in self.process_pet_turn_effects(self.attacker):
                await self.add_to_log(turn_msg)
        
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
            hp_bar = self.create_hp_bar(current_hp, max_hp, combatant=combatant)
            
            # Get element emoji
            element_emoji = "❌"
            for emoji, element in element_emoji_map.items():
                if element == combatant.element:
                    element_emoji = emoji
                    break
            
            field_name = f"**[TEAM A]** \n{combatant.name} {element_emoji}"
            field_value = f"HP: {current_hp:.1f}/{max_hp:.1f}\n{hp_bar}"
            if hasattr(combatant, "shield") and Decimal(str(combatant.shield)) > 0:
                field_value += f"\nShield: {self.format_number(combatant.shield)}"
            
            # Add reflection info if applicable
            if combatant.damage_reflection > 0:
                reflection_percent = float(combatant.damage_reflection) * 100
                field_value += f"\nDamage Reflection: {reflection_percent:.1f}%"
                
            embed.add_field(name=field_name, value=field_value, inline=False)
        
        # Add monster team info
        for combatant in self.monster_team.combatants:
            current_hp = max(0, float(combatant.hp))
            max_hp = float(combatant.max_hp)
            hp_bar = self.create_hp_bar(current_hp, max_hp, combatant=combatant)
            
            # Get element emoji
            element_emoji = "❌"
            for emoji, element in element_emoji_map.items():
                if element == combatant.element:
                    element_emoji = emoji
                    break
            
            field_name = f"**[TEAM B]** \n{combatant.name} {element_emoji}"
            field_value = f"HP: {current_hp:.1f}/{max_hp:.1f}\n{hp_bar}"
            if hasattr(combatant, "shield") and Decimal(str(combatant.shield)) > 0:
                field_value += f"\nShield: {self.format_number(combatant.shield)}"
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
            await self.send_with_retry(content="The battle ended in a draw due to timeout.")
            # Save final battle state to database for replay
            await self.save_battle_to_database()
            return None
        
        # Determine winner
        if all(not c.is_alive() for c in self.player_team.combatants):
            # Player lost
            await self.send_with_retry(
                content=f"You were defeated by the **{self.monster_team.combatants[0].name}**. Better luck next time!"
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
                await self.ctx.bot.log_xp_watch_event(
                    ctx=self.ctx,
                    user_id=self.ctx.author.id,
                    delta=int(xp_gain),
                    source="battles.pve.victory",
                    details={
                        "monster_level": int(self.monster_level),
                        "macro_penalty_level": int(self.macro_penalty_level),
                    },
                    conn=conn,
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
                pet_name = get_pet_display_name(
                    self.ctx.bot,
                    pet_battle_result.get("pet_name", "your pet"),
                )
                if awarded_pet_xp > 0:
                    pet_line = f"\n🐾 **Pet XP:** **+{awarded_pet_xp}** to **{pet_name}**"
                    if pet_battle_result.get("leveled_up"):
                        pet_line += f" (Level {pet_battle_result.get('new_level')})"
                    if pet_battle_result.get("cap_reached"):
                        pet_line += " - daily battle XP cap reached."
                    victory_message += pet_line
                elif pet_battle_result.get("reason") == "daily_cap_reached":
                    victory_message += "\n🐾 **Pet XP:** Daily battle XP cap already reached today."
            
            await self.send_with_retry(content=victory_message)
            
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


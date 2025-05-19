# battles/types/pve.py
import asyncio
import random
from decimal import Decimal
import discord
import datetime

from ..core.battle import Battle

class PvEBattle(Battle):
    """Player vs Environment (monster) battle implementation"""
    
    def __init__(self, ctx, teams, **kwargs):
        super().__init__(ctx, teams, **kwargs)
        self.player_team = teams[0]
        self.monster_team = teams[1]
        self.monster_level = kwargs.get("monster_level", 1)
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
        
        monster_name = self.monster_team.combatants[0].name
        await self.add_to_log(f"Battle against {monster_name} started!")
        
        # Determine turn order (randomized)
        self.turn_order = []
        for team in self.teams:
            for combatant in team.combatants:
                self.turn_order.append(combatant)
        
        random.shuffle(self.turn_order)
        
        # Create and send initial battle embed
        embed = await self.create_battle_embed()
        self.battle_message = await self.ctx.send(embed=embed)
        await asyncio.sleep(2)
        
        return True
    
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
            if luck_roll > self.attacker.luck:
                hits = False
        
        if hits:
            # Attack hits
            
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
                
                # Apply element effects to base damage if enabled
                if self.config["element_effects"] and hasattr(self.ctx.bot.cogs["Battles"], "element_ext"):
                    element_mod = self.ctx.bot.cogs["Battles"].element_ext.calculate_damage_modifier(
                        self.ctx,
                        self.attacker.element, 
                        self.defender.element
                    )
                    if element_mod != 0:
                        raw_damage = raw_damage * (1 + Decimal(str(element_mod)))
                
                # Add variance and apply armor
                raw_damage += Decimal(damage_variance)
                blocked_damage = min(raw_damage, self.defender.armor)
                damage = max(raw_damage - self.defender.armor, Decimal('10'))
                
                self.defender.take_damage(damage)
                
                message = f"{self.attacker.name} attacks! {self.defender.name} takes **{self.format_number(damage)} HP** damage."
            
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
            return None
        
        # Determine winner
        if all(not c.is_alive() for c in self.player_team.combatants):
            # Player lost
            await self.ctx.send(
                f"You were defeated by the **{self.monster_team.combatants[0].name}**. Better luck next time!"
            )
            return self.monster_team
        else:
            # Player won - calculate XP reward
            if self.monster_level == 11:  # Legendary monster
                xp_gain = random.randint(75000, 125000)
            else:
                xp_gain = random.randint(self.monster_level * 300, self.monster_level * 1000)
            
            # Award XP
            async with self.ctx.bot.pool.acquire() as conn:
                await conn.execute(
                    'UPDATE profile SET "xp" = "xp" + $1 WHERE "user" = $2;',
                    xp_gain,
                    self.ctx.author.id,
                )
            
            await self.ctx.send(
                f"You defeated the **{self.monster_team.combatants[0].name}** and gained **{xp_gain} XP**!"
            )
            
            # Check for level up
            from utils import misc as rpgtools
            player_xp = self.ctx.character_data.get("xp", 0)
            player_level = rpgtools.xptolevel(player_xp)
            new_level = rpgtools.xptolevel(player_xp + xp_gain)
            
            if new_level > player_level:
                await self.ctx.bot.process_levelup(self.ctx, new_level, player_level)
            
            # Dispatch PVE completion event
            self.ctx.bot.dispatch("PVE_completion", self.ctx, True)
            
            return self.player_team
    
    async def is_battle_over(self):
        """Check if the battle is over"""
        # Battle is over if one team is completely defeated
        player_defeated = all(not c.is_alive() for c in self.player_team.combatants)
        monster_defeated = all(not c.is_alive() for c in self.monster_team.combatants)
        
        return player_defeated or monster_defeated or await self.is_timed_out() or self.finished
# battles/types/pvp.py
import asyncio
import random
from decimal import Decimal
import discord
import datetime

from ..core.battle import Battle

class PvPBattle(Battle):
    """Player vs Player battle implementation"""
    
    def __init__(self, ctx, teams, **kwargs):
        super().__init__(ctx, teams, **kwargs)
        
        # Load all battle settings first before anything else
        settings_cog = self.ctx.bot.get_cog("BattleSettings")
        if settings_cog:
            # Ensure all settings are loaded, with defaults if not found
            self.config = {
                "simple": kwargs.get("simple", False),
                "allow_pets": settings_cog.get_setting("pvp", "allow_pets", default=True),
                "class_buffs": settings_cog.get_setting("pvp", "class_buffs", default=True),
                "element_effects": settings_cog.get_setting("pvp", "element_effects", default=True),
                "luck_effects": settings_cog.get_setting("pvp", "luck_effects", default=True),
                "reflection_damage": settings_cog.get_setting("pvp", "reflection_damage", default=True),
                "fireball_chance": settings_cog.get_setting("pvp", "fireball_chance", default=0.3),
                "cheat_death": settings_cog.get_setting("pvp", "cheat_death", default=True),
                "tripping": settings_cog.get_setting("pvp", "tripping", default=True),
                "status_effects": settings_cog.get_setting("pvp", "status_effects", default=False),
                "pets_continue_battle": settings_cog.get_setting("pvp", "pets_continue_battle", default=False)
            }
        else:
            # Fallback default settings if settings cog is unavailable
            self.config = {
                "simple": kwargs.get("simple", False),
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
        
        self.money = kwargs.get("money", 0)
        self.player1 = teams[0].combatants[0]
        self.player2 = teams[1].combatants[0]
        
        # For simple battles
        self.simple = self.config["simple"]
        if self.simple:
            # Simple battle uses classic battle math
            self.player1_stats = sum(kwargs.get("player1_stats", [0, 0])) + random.randint(1, 7)
            self.player2_stats = sum(kwargs.get("player2_stats", [0, 0])) + random.randint(1, 7)
    
    async def start_battle(self):
        """Start the battle"""
        self.started = True
        self.start_time = datetime.datetime.utcnow()
        
        # For simple battles, we just need to calculate stats once
        if self.simple:
            # Nothing to start - we'll just calculate in end_battle
            return True
        
        # Add battle start message to log
        await self.add_to_log(f"Battle between {self.player1.name} and {self.player2.name} started!")
        
        # Create and send initial embed
        embed = await self.create_battle_embed()
        self.battle_message = await self.ctx.send(embed=embed)
        
        return True
    
    async def process_turn(self):
        """Process a single battle turn"""
        # Simple battles don't have turns
        if self.simple:
            return False
            
        # Otherwise implement standard turn-based combat
        # This would include attack calculations, damage, etc.
        # Not fully implemented as simple battles use the old format
        return False
    
    async def create_battle_embed(self):
        """Create the battle status embed"""
        embed = discord.Embed(
            title=f"Battle: {self.player1.display_name} vs {self.player2.display_name}",
            color=self.ctx.bot.config.game.primary_colour
        )
        
        # Add player stats
        for player in [self.player1, self.player2]:
            current_hp = max(0, float(player.hp))
            max_hp = float(player.max_hp)
            hp_bar = self.create_hp_bar(current_hp, max_hp)
            
            # Get element emoji if available
            element_emoji = "❌"
            if hasattr(self.ctx.bot.cogs["Battles"], "emoji_to_element"):
                for emoji, element in self.ctx.bot.cogs["Battles"].emoji_to_element.items():
                    if element == player.element:
                        element_emoji = emoji
                        break
            
            field_name = f"{player.name} {element_emoji}"
            field_value = f"HP: {current_hp:.1f}/{max_hp:.1f}\n{hp_bar}"
            embed.add_field(name=field_name, value=field_value, inline=False)
        
        # Add battle log
        log_text = "\n\n".join([f"**Action #{i}**\n{msg}" for i, msg in self.log])
        embed.add_field(name="Battle Log", value=log_text or "Battle starting...", inline=False)
        
        return embed
    
    async def update_display(self):
        """Update the battle display"""
        if self.simple:
            return  # No display updates for simple battles
            
        embed = await self.create_battle_embed()
        if self.battle_message:
            await self.battle_message.edit(embed=embed)
        else:
            self.battle_message = await self.ctx.send(embed=embed)
    
    async def end_battle(self):
        """End the battle and determine rewards"""
        self.finished = True
        
        # For simple battles, determine winner based on player stats
        if self.simple:
            players = [self.player1.user, self.player2.user]
            stats = [self.player1_stats, self.player2_stats]
            
            if stats[0] == stats[1]:
                winner = random.choice(players)
            else:
                winner = players[stats.index(max(stats))]
            
            loser = players[1] if winner == players[0] else players[0]
            
            # Update database with win and money transfer
            async with self.ctx.bot.pool.acquire() as conn:
                await conn.execute(
                    'UPDATE profile SET "pvpwins"="pvpwins"+1, "money"="money"+$1 WHERE'
                    ' "user"=$2;',
                    self.money * 2,
                    winner.id,
                )
                await self.ctx.bot.log_transaction(
                    self.ctx,
                    from_=loser.id,
                    to=winner.id,
                    subject="Battle Bet",
                    data={"Gold": self.money},
                    conn=conn,
                )
            
            return (winner, loser)
        
        # For regular turn-based battles, check HP
        if self.player1.hp <= 0:
            winner = self.player2.user
            loser = self.player1.user
        elif self.player2.hp <= 0:
            winner = self.player1.user
            loser = self.player2.user
        elif await self.is_timed_out():
            # It's a tie - refund money
            async with self.ctx.bot.pool.acquire() as conn:
                await conn.execute(
                    'UPDATE profile SET "money"="money"+$1 WHERE "user" IN ($2, $3);',
                    self.money,
                    self.player1.user.id,
                    self.player2.user.id
                )
            return None
        else:
            # Determine winner based on remaining HP percentage
            p1_hp_percent = self.player1.hp / self.player1.max_hp
            p2_hp_percent = self.player2.hp / self.player2.max_hp
            
            if p1_hp_percent > p2_hp_percent:
                winner = self.player1.user
                loser = self.player2.user
            elif p2_hp_percent > p1_hp_percent:
                winner = self.player2.user
                loser = self.player1.user
            else:
                # Completely equal - random winner
                players = [self.player1.user, self.player2.user]
                winner = random.choice(players)
                loser = players[1] if winner == players[0] else players[0]
        
        # Update database with win and money transfer
        async with self.ctx.bot.pool.acquire() as conn:
            await conn.execute(
                'UPDATE profile SET "pvpwins"="pvpwins"+1, "money"="money"+$1 WHERE'
                ' "user"=$2;',
                self.money * 2,
                winner.id,
            )
            await self.ctx.bot.log_transaction(
                self.ctx,
                from_=loser.id,
                to=winner.id,
                subject="Battle Bet",
                data={"Gold": self.money},
                conn=conn,
            )
        
        return (winner, loser)
    
    async def is_battle_over(self):
        """Check if the battle is over"""
        if self.simple:
            return True  # Simple battles are decided immediately
            
        # Check for timeout or explicit finish
        if await self.is_timed_out() or self.finished:
            return True
            
        # Check team 2 (typically opponent)
        if self.player2.hp <= 0 and all(not c.is_alive() for c in self.teams[1].combatants):
            return True
            
        # Check team 1 (typically player) with pet continuation settings
        if self.player1.hp <= 0:
            # If player is defeated, check if pets should continue fighting
            if self.config.get("pets_continue_battle", False) and self.config.get("allow_pets", True):
                # Check if there are any alive pets in team 1
                player_pets = [c for c in self.teams[0].combatants if c.is_pet and c.is_alive()]
                if player_pets:
                    # Pets can continue fighting
                    return False
                    
            # Either pets_continue_battle is off, or no pets are alive
            return True
            
        # Otherwise battle continues
        return False
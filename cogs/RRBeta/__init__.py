"""
The IdleRPG Discord Bot
Copyright (C) 2018-2021 Diniboy and Gelbpunkt
Copyright (C) 2023-2024 Lunar (PrototypeX37)

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU Affero General Public License for more details.

You should have received a copy of the GNU Affero General Public License
along with this program.  If not, see <https://www.gnu.org/licenses/>.
"""
import discord
import asyncio
import random
from discord.ext import commands
from discord.ui import View, Select
from utils.checks import has_char, is_gm
from utils.i18n import _, locale_doc

class Player:
    def __init__(self, user):
        self.user = user
        self.items = {"vest": 0, "extra_bullet": 0, "extra_life": 0}
        self.stats = {"shots_fired": 0, "rounds_survived": 0}
        self.bet_amount = 0
        self.role = None  # Role assigned to the player
        self.changed_attack = False  # For Fortune Teller ability

class Bet:
    def __init__(self, bettor, amount, player):
        self.bettor = bettor  # User who placed the bet
        self.amount = amount  # Amount of the bet
        self.player = player  # Player the bet is placed on

class Game:
    def __init__(self, bullets=1):
        self.participants = []
        self.all_players = []
        self.is_game_running = False
        self.roundnum = 1
        self.bettotal = 0  # Total bet amount from participants
        self.bets = []  # List of Bet instances from spectators
        self.total_spectator_bets = 0  # Total amount bet by spectators
        self.joined_players = set()
        self.gamestarted = False
        self.single = False
        self.bullets = bullets
        self.chambers = []
        self.silent_round = False  # For silent chamber event
        self.narratives = [
            "The sun dips below the horizon as tension fills the air...",
            "A cold wind whispers through the arena, carrying the scent of fear...",
            "Eyes lock across the circle, each player weighing their chances...",
            "The crowd holds its breath as the next round begins...",
            "Sweat drips down foreheads as fingers tremble on triggers...",
            "An eerie silence falls, broken only by the ticking of a distant clock...",
            "Shadows lengthen as players contemplate their fate...",
            "A lone crow caws in the distance, a harbinger of what's to come...",
            "Dust swirls at your feet as you prepare to face destiny...",
            "The atmosphere is electric, charged with anticipation..."
        ]
        self.max_items_per_player = {"vest": 1, "extra_life": 1, "extra_bullet": 1}
        self.sudden_death = False  # Flag for sudden death mode

class FortuneTellerView(View):
    def __init__(self, fortune_teller, valid_targets):
        super().__init__(timeout=30)
        self.fortune_teller = fortune_teller
        self.valid_targets = valid_targets
        self.selected_target = None
        options = [
            discord.SelectOption(label=target.user.display_name, value=str(target.user.id))
            for target in valid_targets.values()
        ]
        self.select = Select(
            placeholder="Choose a player to redirect the attack to",
            options=options,
            min_values=1,
            max_values=1
        )
        self.select.callback = self.select_callback
        self.add_item(self.select)

    async def select_callback(self, interaction):
        if interaction.user != self.fortune_teller.user:
            await interaction.response.send_message("This interaction is not for you.", ephemeral=True)
            return
        target_value = interaction.data['values'][0]
        self.selected_target = self.valid_targets.get(target_value)
        if self.selected_target:
            await interaction.response.send_message(
                f"You have redirected the attack to {self.selected_target.user.display_name}.", ephemeral=True
            )
        else:
            await interaction.response.send_message("Invalid selection.", ephemeral=True)
        self.stop()

    async def on_timeout(self):
        pass  # Do nothing on timeout; we'll handle it in the main code

class PlayerTurnView(View):
    def __init__(self, timeout, player, valid_targets):
        super().__init__(timeout=timeout)
        self.player = player
        self.valid_targets = valid_targets
        self.interaction_handled = False
        self.selected_target = None

        # Create the select menu
        options = [
            discord.SelectOption(label=target.user.display_name, value=str(target.user.id))
            for target in valid_targets.values()
        ]
        self.select = Select(
            placeholder="Choose a player to target",
            options=options,
            min_values=1,
            max_values=1
        )
        self.select.callback = self.select_callback
        self.add_item(self.select)

    async def select_callback(self, interaction):
        if interaction.user != self.player.user:
            await interaction.response.send_message("You cannot choose for another player!", ephemeral=True)
            return
        target_value = interaction.data['values'][0]
        target = self.valid_targets.get(target_value)
        if not target:
            await interaction.response.send_message("Invalid target selected.", ephemeral=True)
            return
        # Set the selected target
        self.selected_target = target
        self.interaction_handled = True
        # Disable the view after interaction
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(view=self)
        # Stop the view to prevent it from timing out
        self.stop()

class RRBeta(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.games = {}  # Key: channel ID, Value: Game instance
        # Define the items (now only found through random events)
        self.items = {
            "vest": {"name": "Bulletproof Vest", "description": "50% chance to absorb one shot aimed at you."},
            "extra_life": {"name": "Extra Life", "description": "Gives you an extra life if you are shot."},
            "extra_bullet": {"name": "Extra Bullet", "description": "Adds an extra bullet when you shoot someone."}
        }
        # Define special roles and their abilities
        self.roles = {
            "Guardian": "Can protect themselves from being shot once.",
            "Assassin": "Has a 25% chance to eliminate a target instantly.",
            "Fortune Teller": "Can foresee attacks and change the target once per game."
        }

    @has_char()
    @commands.command()
    async def rrjoin(self, ctx):
        game = self.games.get(ctx.channel.id)
        if not game or not game.gamestarted:
            await ctx.send("There is no game running. You can't join now.")
            return
        if game.is_game_running:
            await ctx.send("A game is already running. You can't join now.")
            return
        if ctx.author.id in [p.user.id for p in game.participants]:
            await ctx.send(f"{ctx.author.mention}, you have already joined this game.")
            return

        player = Player(ctx.author)

        await ctx.send(f"{ctx.author.mention} has joined the game!")

        game.participants.append(player)
        game.all_players.append(player)
        game.joined_players.add(ctx.author)

    @has_char()
    @is_gm()
    @commands.command(name='rrbeta', aliases=['rrb'], brief=_("Play Russian Roulette Beta"))
    @locale_doc
    async def rrbeta(self, ctx, bet: int = 0, bullets: int = 1):
        _(
            """`<bet>` - the amount of money to bid
            `<bullets>` - number of bullets in the gun (1-6)

            Start an enhanced game of Russian Roulette.
            """
        )
        game = self.games.get(ctx.channel.id)
        if game and game.single:
            await ctx.send("A game is already running in this channel.")
            return

        if bullets < 1 or bullets > 6:
            await ctx.send("Number of bullets must be between 1 and 6.")
            return

        game = Game(bullets=bullets)
        self.games[ctx.channel.id] = game

        if bet < 0:
            await ctx.send(f"{ctx.author.mention} your bet must be above 0!")
            del self.games[ctx.channel.id]
            return

        if bet > 0:
            # Check the player's balance
            async with self.bot.pool.acquire() as conn:
                user_balance = await conn.fetchval(
                    'SELECT "money" FROM profile WHERE "user" = $1;',
                    ctx.author.id
                )
            if user_balance < bet:
                await ctx.send(f"{ctx.author.mention}, you don't have enough money to cover the bet of **${bet}**.")
                del self.games[ctx.channel.id]
                return
            else:
                game.single = True
                async with self.bot.pool.acquire() as conn:
                    await conn.execute(
                        'UPDATE profile SET "money"="money" - $1 WHERE "user"=$2;',
                        bet, ctx.author.id
                    )
                game.bettotal = bet
                game.bet_amount = bet
                game.winnings = game.bettotal

        # Send game explanation embed
        embed = discord.Embed(
            title="Russian Roulette Beta",
            description=(
                f"**Game Started by:** {ctx.author.mention}\n"
                f"**Entry Fee:** {'${}'.format(bet) if bet > 0 else 'Free to Join'}\n"
                f"**Bullets in the Gun:** {bullets}\n\n"
                "**Objective:** Survive and be the last player standing.\n"
                "Players take turns aiming at others and pulling the trigger.\n"
                "Beware of special roles and random events!"
            ),
            color=discord.Color.dark_red()
        )
        embed.set_thumbnail(url="https://media.tenor.com/fklGVnlUSFQAAAAd/russian-roulette.gif")
        await ctx.send(embed=embed)

        await ctx.send("Players have **2 minutes** to join using **$rrjoin**.")

        game.gamestarted = True
        game.joined_players.add(ctx.author)

        player = Player(ctx.author)
        game.participants.append(player)
        game.all_players.append(player)

        # Collect bets from spectators
        await ctx.send("Spectators can place bets on players using `$rrbet <amount> @player`.")
        await asyncio.sleep(120)  # Wait for 2 minutes for players to join and spectators to bet

        if len(game.participants) < 2:
            await ctx.send("Not enough players to start the game.")
            # Refund bet
            if bet > 0:
                async with self.bot.pool.acquire() as conn:
                    await conn.execute(
                        'UPDATE profile SET "money"="money"+$1 WHERE "user"=$2;',
                        bet, ctx.author.id
                    )
            del self.games[ctx.channel.id]
            return

        # Assign roles to players
        await self.assign_roles(ctx, game)

        # Send a summary of players (without revealing roles)
        player_list = "\n".join([f"- {p.user.display_name}" for p in game.participants])
        embed = discord.Embed(
            title="Players",
            description=f"There are **{len(game.participants)}** players:\n{player_list}",
            color=discord.Color.blue()
        )
        await ctx.send(embed=embed)

        game.is_game_running = True  # Set the flag

        # Initialize the chambers only once
        game.chambers = [False] * (6 - game.bullets) + [True] * game.bullets
        random.shuffle(game.chambers)

        await self.announce_round(ctx, game)

        try:
            while len(game.participants) > 1:
                if len(game.participants) == 2 and not game.sudden_death:
                    # Enter sudden death
                    await ctx.send("**Sudden Death!** The gun is now loaded with 3 bullets.")
                    game.bullets = 3
                    game.chambers = [False, False, False, True, True, True]
                    random.shuffle(game.chambers)
                    game.sudden_death = True

                for player in game.participants.copy():
                    if player not in game.participants:
                        continue
                    await self.player_turn(ctx, game, player)
                    if len(game.participants) <= 1:
                        break
                if len(game.participants) <= 1:
                    break
                game.roundnum += 1
                await self.announce_round(ctx, game)
                # Random events
                await self.check_for_random_event(ctx, game)
                # No need to reset chambers; they are retained between rounds
        except Exception as e:
            await ctx.send(f"An error occurred: {e}")
            del self.games[ctx.channel.id]
            return

        await self.end_game(ctx, game)
        del self.games[ctx.channel.id]

    @commands.command()
    async def rrbet(self, ctx, amount: int, player: discord.Member):
        """Place a bet on a player before the game starts."""
        game = self.games.get(ctx.channel.id)
        if not game or game.is_game_running:
            await ctx.send("There is no game accepting bets right now.")
            return

        # Check if the bettor is not a participant
        if ctx.author.id in [p.user.id for p in game.participants]:
            await ctx.send("Players in the game cannot place spectator bets.")
            return

        # Check if the bet is positive
        if amount <= 0:
            await ctx.send("Bet amount must be greater than zero.")
            return

        # Check if the bettor has enough money
        async with self.bot.pool.acquire() as conn:
            user_balance = await conn.fetchval(
                'SELECT "money" FROM profile WHERE "user" = $1;',
                ctx.author.id
            )
        if user_balance < amount:
            await ctx.send("You don't have enough money to place that bet.")
            return

        # Check if the bettor has already placed a bet
        if ctx.author.id in [b.bettor.id for b in game.bets]:
            await ctx.send("You have already placed a bet.")
            return

        # Check if the player is in the game
        target_player = None
        for p in game.participants:
            if p.user.id == player.id:
                target_player = p
                break
        if not target_player:
            await ctx.send("The player you are betting on is not in the game.")
            return

        # Deduct the bet amount from the bettor
        async with self.bot.pool.acquire() as conn:
            await conn.execute(
                'UPDATE profile SET "money"="money" - $1 WHERE "user"=$2;',
                amount, ctx.author.id
            )

        # Add the bet to the game's bets
        bet = Bet(ctx.author, amount, target_player)
        game.bets.append(bet)
        game.total_spectator_bets += amount

        await ctx.send(f"{ctx.author.mention} has placed a bet of **${amount}** on **{player.display_name}**.")

    async def player_turn(self, ctx, game, player):
        # Time pressure
        embed = discord.Embed(
            title="Your Turn",
            description=f"{player.user.mention}, it's your turn! You have **15 seconds** to choose your target.",
            color=discord.Color.orange()
        )
        await ctx.send(embed=embed)

        # Use Select menu to let the player choose their target
        valid_targets = {}
        for p in game.participants:
            if p != player:
                valid_targets[str(p.user.id)] = p

        if not valid_targets:
            # If there are no other players to target, the player wins by default
            await ctx.send(f"{player.user.mention} is the last player standing!")
            game.participants = [player]
            return

        # Create the View
        view = PlayerTurnView(
            timeout=15,
            player=player,
            valid_targets=valid_targets
        )

        embed = discord.Embed(
            title="Choose Your Target",
            description="Select a player from the dropdown below.",
            color=discord.Color.dark_purple()
        )
        message = await ctx.send(embed=embed, view=view)

        # Wait for the view to finish or timeout
        await view.wait()
        if view.interaction_handled:
            # The player made a selection
            target = view.selected_target

            # Fortune Teller ability to change the target once per game
            if target.role == "Fortune Teller" and not target.changed_attack:
                new_target = await self.handle_fortune_teller_ability(ctx, game, player, target)
                if new_target:
                    target = new_target  # Update the target based on Fortune Teller's choice

            await self.handle_shot(ctx, game, player, target)
            # After handling the shot, check if the game has ended
            if len(game.participants) <= 1:
                return  # The game will be ended elsewhere
        else:
            # The player didn't make a selection
            await ctx.send(f"{player.user.mention} took too long and missed their turn!")
            player.stats["rounds_survived"] += 1  # Still count as surviving the round

    async def handle_fortune_teller_ability(self, ctx, game, shooter, target):
        try:
            channel_link = f"https://discord.com/channels/{ctx.guild.id}/{ctx.channel.id}"
            dm_embed = discord.Embed(
                title="Incoming Attack!",
                description=(
                    f"{shooter.user.display_name} is about to attack you.\n"
                    "You can choose to redirect this attack to another player **once per game**."
                ),
                color=discord.Color.dark_teal()
            )
            dm_embed.add_field(
                name="Return to Game",
                value=f"[Click here to return to the game channel]({channel_link})",
                inline=False
            )
            # Prepare valid targets excluding the Fortune Teller themselves
            valid_targets = {str(p.user.id): p for p in game.participants if p != target}

            view = FortuneTellerView(target, valid_targets)
            await target.user.send(embed=dm_embed, view=view)

            await view.wait()

            target.changed_attack = True  # Mark ability as used

            if view.selected_target:
                return view.selected_target  # Return the new target
            else:
                await target.user.send("You did not select a player in time. The attack remains on you.")
                return target  # Attack remains on the original target
        except discord.Forbidden:
            # Cannot send DM to user
            pass
        return target  # Attack remains on the original target

    async def handle_shot(self, ctx, game, shooter, target):
        shooter.stats["shots_fired"] += 1
        await asyncio.sleep(2)
        extra_bullets = shooter.items.get("extra_bullet", 0)
        total_bullets = game.bullets + extra_bullets

        # If chambers are empty, reshuffle
        if not game.chambers:
            game.chambers = [False] * (6 - total_bullets) + [True] * total_bullets
            random.shuffle(game.chambers)

        embed = discord.Embed(
            title="Action",
            description=f"{shooter.user.mention} aims at {target.user.mention} and pulls the trigger...",
            color=discord.Color.dark_red()
        )
        await ctx.send(embed=embed)
        await asyncio.sleep(3)

        # Assassin role ability
        assassin_triggered = False
        if shooter.role == "Assassin" and random.random() < 0.25:
            assassin_triggered = True

        if assassin_triggered:
            # Check for protection
            protection_used = await self.check_protection(ctx, target, assassin=True)
            if protection_used:
                return  # The target survived due to protection
            # No protection, eliminate the player
            embed = discord.Embed(
                title="Assassin Strike!",
                description=f"{shooter.user.mention} eliminates {target.user.mention} instantly!",
                color=discord.Color.red()
            )
            embed.set_image(url="https://media.tenor.com/ggBL-mf1-swAAAAC/guns-anime.gif")
            await ctx.send(embed=embed)
            game.participants.remove(target)
            return
        else:
            if shooter.role == "Assassin":
                await ctx.send(f"{shooter.user.mention}'s Assassin ability did not trigger.")

            # Proceed with normal shooting
            chamber_drawn = game.chambers.pop(0)
            if chamber_drawn:
                # Check for protection
                protection_used = await self.check_protection(ctx, target)
                if protection_used:
                    return  # The target survived due to protection
                # Eliminate the player
                embed = discord.Embed(
                    title="BANG!",
                    description=f"{target.user.mention} has been shot by {shooter.user.mention}!",
                    color=discord.Color.red()
                )
                embed.set_image(url="https://media.tenor.com/ggBL-mf1-swAAAAC/guns-anime.gif")
                await ctx.send(embed=embed)
                game.participants.remove(target)
            else:
                embed = discord.Embed(
                    title="Click!",
                    description=f"The gun clicks! {target.user.mention} survives.",
                    color=discord.Color.green()
                )
                await ctx.send(embed=embed)
                target.stats["rounds_survived"] += 1

    async def check_protection(self, ctx, target, assassin=False):
        # Guardian role ability
        if target.role == "Guardian" and target.items.get("protect", 0) > 0:
            embed = discord.Embed(
                title="Guardian Shield",
                description=f"{target.user.mention}'s Guardian ability protected them from the {'Assassins strike' if assassin else 'shot'}!",
                color=discord.Color.blue()
            )
            await ctx.send(embed=embed)
            target.items["protect"] -= 1
            return True  # Protection used

        # Check for items
        if target.items.get("vest", 0) > 0:
            # 50% chance to absorb the shot
            if random.random() < 0.5:
                embed = discord.Embed(
                    title="Bulletproof Vest",
                    description=f"{target.user.mention}'s bulletproof vest absorbed the {'Assassins strike' if assassin else 'shot'}!",
                    color=discord.Color.blue()
                )
                await ctx.send(embed=embed)
                target.items["vest"] -= 1
                return True  # Protection used
            else:
                await ctx.send(f"{target.user.mention}'s bulletproof vest failed to stop the {'Assassins strike' if assassin else 'shot'}!")
                target.items["vest"] -= 1

        # Check for extra life
        if target.items.get("extra_life", 0) > 0:
            embed = discord.Embed(
                title="Extra Life Used",
                description=f"{target.user.mention} uses an extra life to survive the {'Assassins strike' if assassin else 'shot'}!",
                color=discord.Color.green()
            )
            await ctx.send(embed=embed)
            target.items["extra_life"] -= 1
            return True  # Protection used

        return False  # No protection available

    async def announce_round(self, ctx, game):
        if game.silent_round:
            embed = discord.Embed(
                title="Silent Round",
                description="An eerie silence fills the air... It's a silent round.",
                color=discord.Color.dark_gray()
            )
            await ctx.send(embed=embed)
            game.silent_round = False
            return
        narrative = random.choice(game.narratives)
        # Adjust narrative based on game state
        if game.roundnum == 3:
            narrative += "\nA mysterious fog rolls in, obscuring everyone's vision..."
        elif len(game.participants) == 2:
            narrative += "\nOnly two players remain. The tension is palpable."
        embed = discord.Embed(
            title=f"Round {game.roundnum}",
            description=narrative,
            color=discord.Color.gold()
        )
        embed.set_image(url="https://media.tenor.com/fklGVnlUSFQAAAAd/russian-roulette.gif")
        await ctx.send(embed=embed)

    async def end_game(self, ctx, game):
        if game.participants:
            winner = game.participants[0]
            # Update stats
            async with self.bot.pool.acquire() as conn:
                # Update wins, money, etc.
                if game.bettotal > 0:
                    await conn.execute(
                        'UPDATE profile SET "money"="money"+$1 WHERE "user"=$2;',
                        game.bettotal, winner.user.id
                    )
            embed = discord.Embed(
                title="Game Over!",
                description=f"**Winner:** {winner.user.mention}\n**Rounds Played:** {game.roundnum}",
                color=discord.Color.green()
            )
            embed.set_thumbnail(url="https://media.tenor.com/_jZg0fof4ZYAAAAd/medal-win.gif")
            await ctx.send(embed=embed)
            # Show statistics
            stats_msg = ""
            for p in game.all_players:
                role_info = f" (Role: {p.role})" if p.role else ""
                stats_msg += f"**{p.user.display_name}**{role_info}\n- Shots Fired: {p.stats['shots_fired']}\n- Rounds Survived: {p.stats['rounds_survived']}\n\n"
            stats_embed = discord.Embed(
                title="Game Statistics",
                description=stats_msg,
                color=discord.Color.blue()
            )
            await ctx.send(embed=stats_embed)

            # Handle spectator bets
            if game.bets:
                winners = [b for b in game.bets if b.player == winner]
                if winners:
                    total_winnings = game.total_spectator_bets
                    split_amount = total_winnings // len(winners)
                    async with self.bot.pool.acquire() as conn:
                        for bet in winners:
                            # Return original bet plus split winnings
                            payout = bet.amount + split_amount
                            await conn.execute(
                                'UPDATE profile SET "money"="money"+$1 WHERE "user"=$2;',
                                payout, bet.bettor.id
                            )
                            await bet.bettor.send(f"You won **${payout}** from your bet on **{winner.user.display_name}**!")
                    await ctx.send("Spectator bets have been paid out to the winners.")
                else:
                    await ctx.send("No spectators won their bets.")
        else:
            embed = discord.Embed(
                title="Game Over!",
                description="All players have been eliminated! No winners this time.",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
            await ctx.send("All spectator bets have been lost.")

    async def check_for_random_event(self, ctx, game):
        if random.random() < 0.3:  # 30% chance
            events = [
                self.event_add_bullet,
                self.event_remove_bullet,
                self.event_give_item,
                self.event_double_bullet,
                self.event_silent_chamber
            ]
            event = random.choice(events)
            # Notify Fortune Tellers
            await self.notify_fortune_tellers(ctx, game, event)
            # Wait a moment for Fortune Tellers to process the info
            await asyncio.sleep(2)
            await event(ctx, game)

    async def notify_fortune_tellers(self, ctx, game, event):
        fortune_tellers = [p for p in game.participants if p.role == "Fortune Teller"]
        if fortune_tellers:
            event_name = event.__name__.replace('event_', '').replace('_', ' ').title()
            channel_link = f"https://discord.com/channels/{ctx.guild.id}/{ctx.channel.id}"
            for ft in fortune_tellers:
                try:
                    dm_embed = discord.Embed(
                        title="Fortune Teller Vision",
                        description=f"The next random event is **{event_name}**.",
                        color=discord.Color.purple()
                    )
                    dm_embed.add_field(
                        name="Return to Game",
                        value=f"[Click here to return to the game channel]({channel_link})",
                        inline=False
                    )
                    await ft.user.send(embed=dm_embed)
                except discord.Forbidden:
                    pass  # Cannot send DM to user

    async def event_add_bullet(self, ctx, game):
        game.bullets = min(6, game.bullets + 1)
        embed = discord.Embed(
            title="Random Event!",
            description="An extra bullet has been added to the gun!",
            color=discord.Color.red()
        )
        await ctx.send(embed=embed)

    async def event_remove_bullet(self, ctx, game):
        game.bullets = max(1, game.bullets - 1)
        embed = discord.Embed(
            title="Random Event!",
            description="A bullet has been removed from the gun!",
            color=discord.Color.green()
        )
        await ctx.send(embed=embed)

    async def event_give_item(self, ctx, game):
        item_key = random.choice(list(self.items.keys()))
        player = random.choice(game.participants)
        item_name = self.items[item_key]['name']
        if player.items[item_key] < game.max_items_per_player[item_key]:
            player.items[item_key] += 1
            embed = discord.Embed(
                title="Random Event!",
                description=f"{player.user.mention} found a **{item_name}**!",
                color=discord.Color.blue()
            )
            await ctx.send(embed=embed)
        else:
            embed = discord.Embed(
                title="Random Event!",
                description=f"{player.user.mention} was supposed to receive a **{item_name}**, but already has the maximum number.",
                color=discord.Color.orange()
            )
            await ctx.send(embed=embed)

    async def event_double_bullet(self, ctx, game):
        game.bullets = min(6, game.bullets * 2)
        embed = discord.Embed(
            title="Random Event!",
            description="Bullets have doubled for this round!",
            color=discord.Color.dark_red()
        )
        await ctx.send(embed=embed)

    async def event_silent_chamber(self, ctx, game):
        game.silent_round = True
        embed = discord.Embed(
            title="Random Event!",
            description="This is a silent round. Outcomes will be revealed at the end!",
            color=discord.Color.dark_gray()
        )
        await ctx.send(embed=embed)

    async def assign_roles(self, ctx, game):
        available_roles = list(self.roles.keys())
        random.shuffle(available_roles)
        for player in game.participants:
            if available_roles:
                player.role = available_roles.pop()
                # Assign any role-specific items or abilities
                if player.role == "Guardian":
                    player.items["protect"] = 1  # Guardian can protect themselves once
                try:
                    channel_link = f"https://discord.com/channels/{ctx.guild.id}/{ctx.channel.id}"
                    role_embed = discord.Embed(
                        title="Your Role",
                        description=f"You have been assigned the role of **{player.role}**.\n{self.roles[player.role]}",
                        color=discord.Color.gold()
                    )
                    role_embed.add_field(
                        name="Return to Game",
                        value=f"[Click here to return to the game channel]({channel_link})",
                        inline=False
                    )
                    await player.user.send(embed=role_embed)
                except discord.Forbidden:
                    pass  # Cannot send DM to user
            else:
                player.role = None

    @commands.command()
    async def leaderboard(self, ctx):
        async with self.bot.pool.acquire() as conn:
            rows = await conn.fetch(
                'SELECT "user", "wins" FROM stats ORDER BY "wins" DESC LIMIT 10;'
            )
        embed = discord.Embed(title="Leaderboard", color=discord.Color.gold())
        for row in rows:
            user = self.bot.get_user(row["user"])
            if user:
                embed.add_field(name=user.display_name, value=f'{row["wins"]} wins', inline=False)
            else:
                embed.add_field(name=f'User ID {row["user"]}', value=f'{row["wins"]} wins', inline=False)
        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(RRBeta(bot))

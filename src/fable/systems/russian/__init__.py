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
from fable.utils.checks import has_char
from fable.utils.i18n import _, locale_doc

class Game:
    def __init__(self):
        self.participants = []
        self.is_game_running = False
        self.roundnum = 1
        self.bettotal = 0
        self.counter = 0
        self.betamount = 0
        self.joined_players = set()
        self.gamestarted = False
        self.single = False

class Russian(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.games = {}

    @has_char()
    @commands.command()
    async def join(self, ctx):
        game = self.games.get(ctx.channel.id)

        if not game or not game.gamestarted:
            await ctx.send("There is no game running. You can't join now.")
            return

        if game.is_game_running:
            await ctx.send("A game is already running. You can't join now.")
            return

        if ctx.author in game.joined_players:
            await ctx.send(f"{ctx.author.mention}, you have already joined this game.")
            return

        if game.bettotal > 0:
            if game.counter == 0:
                game.betamount = game.bettotal
                game.counter = 1
            # Check the player's balance
            async with self.bot.pool.acquire() as conn:
                user_balance = await conn.fetchval(
                    'SELECT "money" FROM profile WHERE "user" = $1;',
                    ctx.author.id
                )

            if user_balance < game.betamount:
                await ctx.send(f"{ctx.author.mention}, you are too poor.")
                return

            # Deduct the bet amount from the player's profile
            async with self.bot.pool.acquire() as conn:
                await conn.execute(
                    'UPDATE profile SET "money"="money" - $1 WHERE "user"=$2;',
                    game.betamount, ctx.author.id
                )
            await ctx.send(f"{ctx.author.mention} has joined the game and paid a bet of {game.betamount}.")
            game.bettotal += game.betamount
            game.participants.append(ctx.author)
            game.joined_players.add(ctx.author)

        else:
            await ctx.send(f"{ctx.author.mention} has joined the game!")
            game.participants.append(ctx.author)
            game.joined_players.add(ctx.author)

    @has_char()
    @commands.command(aliases=["rr", "gungame"], brief=_("Play Russian Roulette"))
    @locale_doc
    async def russianroulette(self, ctx, bet: int = 0):
        _(
            """`<amount>` - the amount of money to bid

            Start a game of Russian Roulette.

            Players take turns pulling the trigger while pointing the gun at their own head or another player's head, with the hope of avoiding the live round"""
        )
        game = self.games.get(ctx.channel.id)

        if game:
            await ctx.send("A game is already running in this channel.")
            return

        game = Game()
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
                async with self.bot.pool.acquire() as conn:
                    await conn.execute(
                        'UPDATE profile SET "money"="money" - $1 WHERE "user"=$2;',
                        bet, ctx.author.id
                    )
                game.bettotal = bet
                game.winnings = game.bettotal
                await ctx.send(
                    f"Russian Roulette game has started with an entry fee of **${bet}!** Wait for 2 minutes for players to join.")
                game.gamestarted = True
                game.joined_players.add(ctx.author)
        else:
            await ctx.send("**Russian Roulette game has started!** Players have 2 minutes to join using **$join**.")
            game.gamestarted = True
            game.joined_players.add(ctx.author)

        game.participants.append(ctx.author)
        await asyncio.sleep(120)  # Wait for 2 minutes

        if len(game.participants) < 2:
            await ctx.send("Not enough players to start the game.")
            if bet > 0:
                async with self.bot.pool.acquire() as conn:
                    await conn.execute(
                        'UPDATE profile SET "money"="money"+$1 WHERE "user"=$2;',
                        bet, ctx.author.id
                    )
            del self.games[ctx.channel.id]
            return

        random.shuffle(game.participants)
        remaining = len(game.participants)
        await ctx.send(f"There are {remaining} players!")
        game.is_game_running = True  # Set the flag
        chambers = [False] * 5 + [True]
        random.shuffle(chambers)
        await self.announce_round(ctx, game)

        try:
            while len(game.participants) > 1:
                players_to_remove = []
                player_eliminated = False
                other_player = None

                for player in game.participants.copy():
                    await asyncio.sleep(5)
                    await ctx.send(
                        f"It's {player.mention}'s turn! They pick up the gun and turn it towards their head and slowly pull the trigger...")
                    await asyncio.sleep(4)  # Simulate suspense

                    chamber_drawn = chambers.pop(0)

                    if chamber_drawn:
                        await asyncio.sleep(2)  # Simulate suspense
                        if len(game.participants) == 2 and random.random() < 0.25:
                            other_player = [p for p in game.participants if p != player][0]
                            embed = discord.Embed(
                                title="BANG!",
                                description=f"{other_player.mention} has been shot by {player.mention}!",
                                color=discord.Color.red()
                            )
                            embed.set_image(url="https://media.tenor.com/ggBL-mf1-swAAAAC/guns-anime.gif")
                            await asyncio.sleep(3)  # Simulate suspense
                            await ctx.send(embed=embed)
                            players_to_remove.append(other_player)
                            game.participants.remove(other_player)
                            player_eliminated = True
                            shotother = 1
                        else:
                            embed = discord.Embed(
                                title="BANG!",
                                description=f"{player.mention} has shot themselves in the face!",
                                color=discord.Color.red()
                            )
                            embed.set_image(url="https://i.ibb.co/kKn0zQs/ezgif-4-51fcaad25e.gif")
                            await asyncio.sleep(3)  # Simulate suspense
                            await ctx.send(embed=embed)
                            players_to_remove.append(player)
                            game.participants.remove(player)
                            player_eliminated = True
                            shotother = 0

                    else:
                        await asyncio.sleep(3)  # Simulate suspense
                        embed = discord.Embed(
                            title="The Gun Clicks!",
                            description=f"{player.mention} has survived this round and passes the gun to the next player!",
                            color=discord.Color.green()
                        )
                        await ctx.send(embed=embed)
                        await asyncio.sleep(3)  # Simulate suspense

                    if player_eliminated:
                        if shotother == 1:
                            if other_player is not None:
                                await ctx.send(f"Round over! {other_player.mention} was killed!")
                        else:
                            await ctx.send(f"Round over! {player.mention} was killed!")
                        remaining = len(game.participants)
                        if remaining > 1:
                            await ctx.send(f"There are {remaining} player(s) remaining")

                        if len(game.participants) == 1:
                            winner = game.participants[0]
                            if bet > 0:
                                async with self.bot.pool.acquire() as conn:
                                    await conn.execute(
                                        'UPDATE profile SET "money"="money"+$1 WHERE "user"=$2;',
                                        game.bettotal, winner.id
                                    )
                                winnings = game.bettotal - game.winnings
                                await ctx.send(
                                    f"Congratulations {winner.mention}! You are the last one standing and won **${winnings}**."
                                )
                            else:
                                await ctx.send(
                                    f"Congratulations {winner.mention}! You are the last one standing. **Game over!**"
                                )
                            del self.games[ctx.channel.id]
                            return
                        else:
                            game.roundnum += 1
                            await self.announce_round(ctx, game)
                            chambers = [False] * 5 + [True]
                            random.shuffle(chambers)
                            player_eliminated = False

                if not game.participants:
                    break  # If all players are eliminated
        except Exception as e:
            await ctx.send(f"An error occurred: {e}")
        finally:
            if ctx.channel.id in self.games:
                del self.games[ctx.channel.id]

    async def announce_round(self, ctx, game):
        embed = discord.Embed(
            title=f"Round {game.roundnum}",
            description="Surviving players automatically move to the next round. Round will start in 5 seconds..",
            color=discord.Color.green()
        )
        embed.set_image(url="https://media.tenor.com/fklGVnlUSFQAAAAd/russian-roulette.gif")
        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(Russian(bot))

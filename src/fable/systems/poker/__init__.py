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
from discord.ext import commands
import discord
import random
from itertools import combinations, product


class Card:
    def __init__(self, card_type):
        self.rank = card_type[0].upper()
        self.suit = card_type[1].lower()
        self.rank_number = '..23456789TJQKA'.index(self.rank)
        self.suit_number = int('cshd'.index(self.suit))
        self.suit_symbol = '♣♠♥♦'[self.suit_number]

    def __repr__(self):
        return f'{self.rank} of {self.suit_symbol}'

    def __str__(self):
        return f'{self.rank} of {self.suit_symbol}'


class Evaluator:
    def __init__(self):
        self.rank_meanings = {9: "Royal Flush", 8: "Straight Flush", 7: "Four of a Kind",
                              6: "Full House", 5: "Flush", 4: "Straight", 3: "Three of a Kind",
                              2: "Two Pair", 1: "One Pair", 0: "High Card"}

    def evaluate(self, cards):
        hand = max(combinations(cards, 5), key=self._get_evaluation_score)
        rank_evaluation = self._get_evaluation_score(hand)
        return rank_evaluation, self.rank_meanings[rank_evaluation[0]]

    def _get_evaluation_score(self, hand):
        ranks = self._ranks(hand)
        unique = list(set(ranks))
        if self._straight(ranks) and self._flush(hand):
            if max(ranks) == 14:
                return (9,)
            return (8, max(ranks))
        elif self._kind(4, ranks):
            return (7, self._kind(4, ranks), self._kind(1, ranks))
        elif self._kind(3, ranks) and self._kind(2, ranks):
            return (6, self._kind(3, ranks), self._kind(2, ranks))
        elif self._flush(hand):
            return (5, ranks)
        elif self._straight(ranks):
            return (4, max(ranks))
        elif self._kind(3, ranks):
            return (3, self._kind(3, ranks), ranks)
        elif self._two_pair(ranks):
            return (2, self._two_pair(ranks), ranks)
        elif self._kind(2, ranks):
            return (1, self._kind(2, ranks), ranks)
        else:
            return (0, ranks)

    def _ranks(self, hand):
        return sorted([card.rank_number for card in hand], reverse=True)

    def _flush(self, hand):
        return len(set(card.suit for card in hand)) == 1

    def _straight(self, ranks):
        if len(set(ranks)) == 5 and (max(ranks) - min(ranks) == 4):
            return True
        return ranks == [14, 5, 4, 3, 2]

    def _two_pair(self, ranks):
        pairs = [r for r in set(ranks) if ranks.count(r) == 2]
        if len(pairs) == 2:
            return sorted(pairs, reverse=True)
        return []

    def _kind(self, n, ranks):
        for r in set(ranks):
            if ranks.count(r) == n:
                return r
        return None


class Deck:
    def __init__(self):
        self.cards = []
        self.refill()

    def draw(self, n):
        return [self.cards.pop() for _ in range(n)]

    def refill(self):
        ranks = '23456789TJQKA'
        suits = 'cshd'  # clubs, spades, hearts, diamonds
        self.cards = [Card(r + s) for r in ranks for s in suits]
        random.shuffle(self.cards)


class Player:
    def __init__(self, name):
        self.name = name
        self.hand = []
        self.chips = 0
        self.bet = 0
        self.folded = False

    def __str__(self):
        return self.name


class Game:
    def __init__(self, players):
        self.deck = Deck()
        self.players = [Player(name) for name in players]
        self.pot = 0
        self.current_bet = 0
        self.community_cards = []
        self.evaluator = Evaluator()
        self.stage = 'preflop'  # Tracks the stage of the game

    def start_round(self):
        self.deck.refill()
        self.community_cards = []
        self.pot = 0
        self.current_bet = 0
        for player in self.players:
            player.hand = self.deck.draw(2)
            player.bet = 0
            player.chips -= self.current_bet  # Assuming blinds or ante
            player.folded = False
        self.stage = 'preflop'

    def next_stage(self):
        if self.stage == 'preflop':
            self.community_cards.extend(self.deck.draw(3))  # Deal the flop
            self.stage = 'flop'
        elif self.stage == 'flop':
            self.community_cards.extend(self.deck.draw(1))  # Deal the turn
            self.stage = 'turn'
        elif self.stage == 'turn':
            self.community_cards.extend(self.deck.draw(1))  # Deal the river
            self.stage = 'river'
        elif self.stage == 'river':
            self.showdown()

    def bet(self, player_name, amount):
        player = next(p for p in self.players if p.name == player_name)
        if player.chips < amount:
            raise ValueError("Not enough chips")
        player.chips -= amount
        player.bet += amount
        self.pot += amount
        self.current_bet = max(self.current_bet, player.bet)
        if all(p.bet >= self.current_bet or p.folded for p in self.players):
            self.next_stage()

    def fold(self, player_name):
        player = next(p for p in self.players if p.name == player_name)
        player.folded = True
        if all(p.folded or p.bet >= self.current_bet for p in self.players):
            self.next_stage()

    def showdown(self):
        # Evaluate all hands and determine the winner
        winning_score = (0,)
        winners = []
        for player in self.players:
            if not player.folded:
                hand_score, hand_name = self.evaluator.evaluate(player.hand + self.community_cards)
                if hand_score > winning_score:
                    winning_score = hand_score
                    winners = [player.name]
                elif hand_score == winning_score:
                    winners.append(player.name)
        return winners, winning_score


class Poker(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.games = {}

    @commands.command(name="startpoker")
    async def start_poker(self, ctx, *names: str):
        if ctx.channel.id in self.games:
            await ctx.send("A game is already in progress in this channel.")
            return
        if not names:
            names = [ctx.author.name]
        self.games[ctx.channel.id] = Game(names)
        game = self.games[ctx.channel.id]
        game.start_round()
        for player in game.players:
            await ctx.send(f"{player.name} starts with {player.hand}")
        await ctx.send("Game started. Players can now bet or fold.")

    @commands.command(name="bett")
    async def bett(self, ctx, amount: int):
        game = self.games.get(ctx.channel.id)
        if not game:
            await ctx.send("No game running in this channel.")
            return
        try:
            game.bet(ctx.author.name, amount)
            await ctx.send(f"{ctx.author.name} has bet {amount}. Current pot is {game.pot}.")
        except ValueError as e:
            await ctx.send(str(e))

    @commands.command(name="fold")
    async def fold(self, ctx):
        game = self.games.get(ctx.channel.id)
        if not game:
            await ctx.send("No game running in this channel.")
            return
        game.fold(ctx.author.name)
        await ctx.send(f"{ctx.author.name} has folded.")

    @commands.command(name="evaluategame")
    async def evaluate_game(self, ctx):
        game = self.games.get(ctx.channel.id)
        if not game:
            await ctx.send("No game running in this channel.")
            return
        results = list(game.evaluate_hands())
        for result in results:
            await ctx.send(f"{result[0]} has a {result[2]}.")


async def setup(bot):
    await bot.add_cog(Poker(bot))

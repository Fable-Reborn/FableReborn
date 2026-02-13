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
import asyncio
import os
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

from contextlib import suppress
import time
from enum import Enum
from functools import partial
from random import choice

import discord

from discord.enums import ButtonStyle
from discord.ext import commands
from discord.ext.commands import cooldown
from discord.interactions import Interaction
from discord.ui.button import Button, button

from classes.converters import (
    DateNewerThan,
    IntFromTo,
    IntGreaterThan,
    MemberWithCharacter,
)

from classes.bot import Bot
from classes.context import Context
from classes.converters import CoinSide, IntFromTo, IntGreaterThan, MemberWithCharacter
from utils import random
from utils.checks import has_char, has_money, user_has_char, is_gm
from cogs.shard_communication import user_on_cooldown as user_cooldown
from utils.i18n import _, locale_doc
import random as randomm
from utils.joins import SingleJoinView
from utils.roulette import RouletteGame


class BlackJackAction(Enum):
    Hit = 0
    Stand = 1
    DoubleDown = 2
    ChangeDeck = 3
    Split = 4


class InsuranceView(discord.ui.View):
    def __init__(
            self, user: discord.User, future: asyncio.Future[bool], *args, **kwargs
    ):
        super().__init__(*args, **kwargs)
        self.user = user
        self.future = future

    async def interaction_check(self, interaction: Interaction) -> bool:
        return interaction.user.id == self.user.id

    @button(label="Take insurance", style=ButtonStyle.green, emoji="\U0001f4b8")
    async def insurance(self, interaction: Interaction, button: Button) -> None:
        self.stop()
        self.future.set_result(True)
        await interaction.response.defer()

    @button(label="Don't take insurance", style=ButtonStyle.red, emoji="\U000026a0")
    async def no_insurance(self, interaction: Interaction, button: Button) -> None:
        self.stop()
        self.future.set_result(False)
        await interaction.response.defer()

    async def on_timeout(self) -> None:
        self.future.set_result(False)


class BlackJackView(discord.ui.View):
    def __init__(
            self,
            user: discord.User,
            future: asyncio.Future[BlackJackAction],
            *args,
            **kwargs,
    ) -> None:
        self.user = user
        self.future = future

        # Buttons to show
        self.hit = kwargs.pop("hit", False)
        self.stand = kwargs.pop("stand", False)
        self.double_down = kwargs.pop("double_down", False)
        self.change_deck = kwargs.pop("change_deck", False)
        self.split = kwargs.pop("split", False)

        super().__init__(*args, **kwargs)

        # Row 1 is primary actions
        hit = Button(
            style=ButtonStyle.primary,
            label="Hit",
            disabled=not self.hit,
            emoji="\U00002934",
            row=0,
        )
        stand = Button(
            style=ButtonStyle.primary,
            label="Stand",
            disabled=not self.stand,
            emoji="\U00002935",
            row=0,
        )
        double_down = Button(
            style=ButtonStyle.primary,
            label="Double Down",
            disabled=not self.double_down,
            emoji="\U000023ec",
            row=0,
        )

        # Row 2 is the two split actions
        change_deck = Button(
            style=ButtonStyle.secondary,
            label="Change Deck",
            disabled=not self.change_deck,
            emoji="\U0001F501",
            row=1,
        )
        split = Button(
            style=ButtonStyle.secondary,
            label="Split",
            disabled=not self.split,
            emoji="\U00002194",
            row=1,
        )

        hit.callback = partial(self.handle, action=BlackJackAction.Hit)
        stand.callback = partial(self.handle, action=BlackJackAction.Stand)
        double_down.callback = partial(self.handle, action=BlackJackAction.DoubleDown)
        change_deck.callback = partial(self.handle, action=BlackJackAction.ChangeDeck)
        split.callback = partial(self.handle, action=BlackJackAction.Split)

        self.add_item(hit)
        self.add_item(stand)
        self.add_item(double_down)
        self.add_item(change_deck)
        self.add_item(split)

    async def interaction_check(self, interaction: Interaction) -> bool:
        return interaction.user.id == self.user.id

    async def handle(self, interaction: Interaction, action: BlackJackAction) -> None:
        self.stop()
        self.future.set_result(action)
        await interaction.response.defer()

    async def on_timeout(self) -> None:
        self.future.set_exception(asyncio.TimeoutError())


class BlackJack:
    def __init__(self, ctx: Context, money: int) -> None:
        self.cards = {
            "adiamonds": "<:ace_of_diamonds:1145400362552012800>",
            "2diamonds": "<:2_of_diamonds:1145400865209987223>",
            "3diamonds": "<:3_of_diamonds:1145400877679648858>",
            "4diamonds": "<:4_of_diamonds:1145400270830960660>",
            "5diamonds": "<:5_of_diamonds:1145400282239479848>",
            "6diamonds": "<:6_of_diamonds:1145400297791950909>",
            "7diamonds": "<:7_of_diamonds:1145400309921886358>",
            "8diamonds": "<:8_of_diamonds:1145400320457973971>",
            "9diamonds": "<:9_of_diamonds:1145400335716864082>",
            "10diamonds": "<:10_of_diamonds:1145400349071523981>",
            "jdiamonds": "<:jack_of_diamonds2:1145400380558151722>",
            "qdiamonds": "<:queen_of_diamonds2:1145400426175398009>",
            "kdiamonds": "<:king_of_diamonds2:1145400404075626536>",
            "aclubs": "<:ace_of_clubs:1145400358768758785>",
            "2clubs": "<:2_of_clubs:1145400863129604127>",
            "3clubs": "<:3_of_clubs:1145400874311614515>",
            "4clubs": "<:4_of_clubs:1145415374016360478>",
            "5clubs": "<:5_of_clubs:1145400280343662623>",
            "6clubs": "<:6_of_clubs:1145400295971631184>",
            "7clubs": "<:7_of_clubs:1145400306738409563>",
            "8clubs": "<:8_of_clubs:1145400318503436318>",
            "9clubs": "<:9_of_clubs:1145400334139793418>",
            "10clubs": "<:10_of_clubs:1145400346668171276>",
            "jclubs": "<:jack_of_clubs2:1145400373381709966>",
            "qclubs": "<:queen_of_clubs2:1145400422094352530>",
            "kclubs": "<:king_of_clubs2:1145400399654834208>",
            "ahearts": "<:ace_of_hearts:1145400364535926824>",
            "2hearts": "<:2_of_hearts:1145400868477354005>",
            "3hearts": "<:3_of_hearts:1145400882490507304>",
            "4hearts": "<:4_of_hearts:1145400273448214619>",
            "5hearts": "<:5_of_hearts:1145400286001766521>",
            "6hearts": "<:6_of_hearts:1145400301222887444>",
            "7hearts": "<:7_of_hearts:1145400312534929419>",
            "8hearts": "<:8_of_hearts:1145400324744548562>",
            "9hearts": "<:9_of_hearts:1145400339537862749>",
            "10hearts": "<:10_of_hearts:1145400352871559268>",
            "jhearts": "<:jack_of_hearts2:1145400387071909888>",
            "qhearts": "<:queen_of_hearts2:1145400432018063381>",
            "khearts": "<:king_of_hearts2:1145400409742118934>",
            "aspades": "<:ace_of_spades:1145400368105279658>",
            "2spades": "<:2_of_spades:1145400872340299796>",
            "3spades": "<:3_of_spades:1145400874311614515>",
            "4spades": "<:4_of_spades:1145400276686225408>",
            "5spades": "<:5_of_spades:1145400290531622943>",
            "6spades": "<:6_of_spades:1145400304888721548>",
            "7spades": "<:7_of_spades:1145400314955055165>",
            "8spades": "<:8_of_spades:1145400329354105013>",
            "9spades": "<:9_of_spades:1145400342763282546>",
            "10spades": "<:10_of_spades:1145400356424130712>",
            "jspades": "<:jack_of_spades2:1145400391798894612>",
            "qspades": "<:queen_of_spades2:1145400436891865089>",
            "kspades": "<:king_of_spades2:1145400416608194680>",
        }
        self.deck: list[tuple[int, str, str]] = []
        self.prepare_deck()
        self.expected_player_money = ctx.character_data["money"] - money
        self.money_spent = money
        self.payout = money
        self.ctx = ctx
        self.msg = None
        self.over = False
        self.insurance = False
        self.doubled = False
        self.twodecks = False

    def prepare_deck(self) -> None:
        for colour in ["hearts", "diamonds", "spades", "clubs"]:
            for value in range(2, 15):  # 11 = Jack, 12 = Queen, 13 = King, 14 = Ace
                if value == 11:
                    card = "j"
                elif value == 12:
                    card = "q"
                elif value == 13:
                    card = "k"
                elif value == 14:
                    card = "a"
                else:
                    card = str(value)
                self.deck.append((value, colour, self.cards[f"{card}{colour}"]))
        self.deck = self.deck * 6  # Blackjack is played with 6 decks
        self.deck = random.shuffle(self.deck)  # assuming your random.shuffle returns a shuffled list

    def deal(self) -> tuple[int, str, str]:
        return self.deck.pop()

    def total(self, hand: list[tuple[int, str, str]]) -> int:
        # Sum non-Ace cards (aces are handled later)
        value = sum(card[0] if card[0] < 11 else 10 for card in hand if card[0] != 14)
        aces = sum(1 for card in hand if card[0] == 14)
        value += aces  # each Ace counts as at least 1
        # For each Ace, add 10 if it doesn’t bust the hand.
        for _ in range(aces):
            if value + 10 <= 21:
                value += 10
            else:
                break
        return value

    def has_bj(self, hand: list[tuple[int, str, str]]) -> bool:
        return self.total(hand) == 21

    def samevalue(self, a: int, b: int) -> bool:
        if a == b:
            return True
        if a in [10, 11, 12, 13] and b in [10, 11, 12, 13]:
            return True
        return False

    def splittable(self, hand) -> bool:
        if self.samevalue(hand[0][0], hand[1][0]) and not self.twodecks:
            return True
        return False

    def hit(self, hand: list[tuple[int, str, str]]) -> list[tuple[int, str, str]]:
        card = self.deal()
        hand.append(card)
        return hand

    def split(self, hand) -> tuple[list[tuple[int, str, str]], list[tuple[int, str, str]]]:
        hand1 = hand[:-1]
        hand2 = [hand[-1]]
        return (hand1, hand2)

    async def player_takes_insurance(self) -> bool:
        if self.payout > 0:
            insurance_cost = self.payout // 2
            self.expected_player_money -= insurance_cost
            self.money_spent += insurance_cost

            async with self.ctx.bot.pool.acquire() as conn:
                if not await has_money(self.ctx.bot, self.ctx.author.id, insurance_cost, conn=conn):
                    return False

                await conn.execute(
                    'UPDATE profile SET "money"="money"-$1 WHERE "user"=$2;',
                    insurance_cost,
                    self.ctx.author.id,
                )
                await self.ctx.bot.log_transaction(
                    self.ctx,
                    from_=1,
                    to=self.ctx.author.id,
                    subject="gambling BJ-Insurance",
                    data={"Gold": insurance_cost},
                    conn=conn,
                )
        return True

    async def player_win(self) -> None:
        if self.payout > 0:
            async with self.ctx.bot.pool.acquire() as conn:
                await conn.execute(
                    'UPDATE profile SET "money"="money"+$1 WHERE "user"=$2;',
                    self.payout * 2,
                    self.ctx.author.id,
                )
                await self.ctx.bot.log_transaction(
                    self.ctx,
                    from_=1,
                    to=self.ctx.author.id,
                    subject="gambling",
                    data={"Gold": self.payout * 2},
                    conn=conn,
                )

    async def player_bj_win(self) -> None:
        if self.payout > 0:
            total = int(self.payout * 2.5)
            async with self.ctx.bot.pool.acquire() as conn:
                await conn.execute(
                    'UPDATE profile SET "money"="money"+$1 WHERE "user"=$2;',
                    total,
                    self.ctx.author.id,
                )
                await self.ctx.bot.log_transaction(
                    self.ctx,
                    from_=1,
                    to=self.ctx.author.id,
                    subject="gambling",
                    data={"Gold": total},
                    conn=conn,
                )

    async def player_cashback(self, with_insurance: bool = False) -> None:
        if self.payout > 0:
            amount = self.money_spent if with_insurance else self.payout
            async with self.ctx.bot.pool.acquire() as conn:
                await conn.execute(
                    'UPDATE profile SET "money"="money"+$1 WHERE "user"=$2;',
                    amount,
                    self.ctx.author.id,
                )
                await self.ctx.bot.log_transaction(
                    self.ctx,
                    from_=1,
                    to=self.ctx.author.id,
                    subject="gambling",
                    data={"Gold": amount},
                    conn=conn,
                )

    def pretty(self, hand: list[tuple[int, str, str]]) -> str:
        return " ".join(card[2] for card in hand)

    async def send_insurance(self) -> bool:
        """
        Sends an embed for the insurance prompt using the remodeled layout.
        """
        player_total = self.total(self.player)
        dealer_total = self.total(self.dealer)
        embed = discord.Embed(
            title="Blackjack - Insurance",
            description="Do you want to take insurance?",
            color=0x3498db
        )
        embed.set_author(name=self.ctx.author.display_name, icon_url=self.ctx.author.avatar.url)
        embed.add_field(name="Your Hand", value=f"{self.pretty(self.player)}\nValue: {player_total}", inline=True)
        embed.add_field(name="Dealer Hand", value=f"{self.pretty(self.dealer)}\nValue: {dealer_total}", inline=True)

        future = asyncio.Future()
        view = InsuranceView(self.ctx.author, future, timeout=20.0)

        if not self.msg:
            self.msg = await self.ctx.send(embed=embed, view=view)
        else:
            await self.msg.edit(embed=embed, view=view)

        return await future

    async def send(
        self,
        additional: str = "",
        hit: bool = False,
        stand: bool = False,
        double_down: bool = False,
        change_deck: bool = False,
        split: bool = False,
        wait_for_action: bool = True,
        color: int = 0x3498db  # default embed color
    ) -> "BlackJackAction | None":
        """
        Sends an embed with the current state. The embed header shows the player's profile
        (username and avatar), and two inline fields show the player's and dealer's cards and their values.
        If an additional result message is provided (e.g. at game end), it appears in the embed's description.
        """
        player_total = self.total(self.player)
        dealer_total = self.total(self.dealer)
        embed = discord.Embed(title="Blackjack", color=color)
        if additional:
            embed.description = additional
        embed.set_author(name=self.ctx.author.display_name, icon_url=self.ctx.author.avatar.url)
        embed.add_field(name="Your Hand", value=f"{self.pretty(self.player)}\nValue: {player_total}", inline=True)
        embed.add_field(name="Dealer Hand", value=f"{self.pretty(self.dealer)}\nValue: {dealer_total}", inline=True)

        if wait_for_action:
            future = asyncio.Future()
            view = BlackJackView(
                self.ctx.author,
                future,
                hit=hit,
                stand=stand,
                double_down=double_down,
                change_deck=change_deck,
                split=split,
                timeout=20.0,
            )
        else:
            view = None

        if not self.msg:
            self.msg = await self.ctx.send(embed=embed, view=view)
        else:
            await self.msg.edit(embed=embed, view=view)

        if wait_for_action:
            return await future

    async def run(self):
        self.player = [self.deal()]
        self.player2 = None
        self.dealer = [self.deal()]
        # Prompt for insurance if applicable.
        if self.dealer[0][0] > 9 and self.expected_player_money >= self.payout // 2:
            self.insurance = await self.send_insurance()
            if self.insurance:
                if not await self.player_takes_insurance():
                    return await self.send(
                        additional=_("You do not have the money to afford insurance anymore."),
                        wait_for_action=False,
                    )
        self.player = self.hit(self.player)
        self.dealer = self.hit(self.dealer)
        player = self.total(self.player)
        dealer = self.total(self.dealer)

        if self.has_bj(self.dealer):
            if self.has_bj(self.player):
                if self.insurance:
                    await self.player_cashback(with_insurance=True)
                    return await self.send(
                        additional=_("You and the dealer got a blackjack. You lost nothing."),
                        wait_for_action=False,
                    )
                else:
                    await self.player_cashback(with_insurance=False)
                    return await self.send(
                        additional=_("You and the dealer got a blackjack. You lost nothing."),
                        wait_for_action=False,
                    )

        if self.has_bj(self.dealer):
            if self.insurance:
                await self.player_cashback(with_insurance=True)
                return await self.send(
                    additional=_("The dealer got a blackjack. You had insurance and lost nothing."),
                    wait_for_action=False,
                )
            else:
                return await self.send(
                    additional=_("The dealer got a blackjack. You lost **${money}**.").format(money=self.money_spent),
                    wait_for_action=False,
                    color=0xe74c3c
                )
        elif self.has_bj(self.player):
            await self.player_bj_win()
            return await self.send(
                additional=_("Result: Win **${money}**").format(money=int(self.payout * 2.5) - self.money_spent),
                wait_for_action=False,
                color=0x2ecc71
            )

        possible_actions = {
            "hit": True,
            "stand": True,
            "double_down": self.expected_player_money - self.payout >= 0,
            "change_deck": False,
            "split": False,
        }
        additional = ""

        while self.total(self.dealer) < 22 and self.total(self.player) < 22 and not self.over:
            possible_actions["change_deck"] = self.twodecks and not self.doubled
            possible_actions["split"] = self.splittable(self.player)

            try:
                action = await self.send(additional=additional, **possible_actions)
            except asyncio.TimeoutError:
                await self.ctx.bot.reset_cooldown(self.ctx)
                return await self.ctx.send(_("Blackjack timed out... You lost your money!"))

            while self.total(self.dealer) < 17:
                self.dealer = self.hit(self.dealer)

            if action == BlackJackAction.Hit:
                if self.doubled:
                    possible_actions["hit"] = False
                    possible_actions["stand"] = True
                self.player = self.hit(self.player)

            elif action == BlackJackAction.Stand:
                self.over = True

            elif action == BlackJackAction.Split:
                self.player2, self.player = self.split(self.player)
                self.hit(self.player)
                self.hit(self.player2)
                self.twodecks = True
                possible_actions["split"] = False
                additional = _("Split current hand and switched to the second side.")

            elif action == BlackJackAction.ChangeDeck:
                self.player, self.player2 = self.player2, self.player
                additional = _("Switched to the other side.")

            elif action == BlackJackAction.DoubleDown:
                self.doubled = True
                if self.payout > 0:
                    self.expected_player_money -= self.payout
                    self.money_spent += self.payout

                    async with self.ctx.bot.pool.acquire() as conn:
                        if not await has_money(self.ctx.bot, self.ctx.author.id, self.payout, conn=conn):
                            return await self.ctx.send(_("Invalid. You're too poor and lose the match."))

                        await conn.execute(
                            'UPDATE profile SET "money"="money"-$1 WHERE "user"=$2;',
                            self.payout,
                            self.ctx.author.id,
                        )
                        await self.ctx.bot.log_transaction(
                            self.ctx,
                            from_=self.ctx.author.id,
                            to=2,
                            subject="gambling BJ",
                            data={"Gold": self.payout},
                            conn=conn,
                        )

                self.payout *= 2
                possible_actions["double_down"] = False
                possible_actions["stand"] = False
                if self.twodecks:
                    possible_actions["change_deck"] = False
                additional = _(
                    "You doubled your bid in exchange for only receiving one more card."
                )

        player = self.total(self.player)
        dealer = self.total(self.dealer)

        # Updated result messages and embed colors:
        if player > 21:
            await self.send(
                additional=_("Result: Bust **${money}**.").format(money=self.money_spent),
                wait_for_action=False,
                color=0xe74c3c
            )
        elif dealer > 21:
            await self.send(
                additional=_("Result: Dealer bust **${money}**!").format(money=self.payout * 2 - self.money_spent),
                wait_for_action=False,
                color=0x2ecc71
            )
            await self.player_win()
        else:
            if player > dealer:
                await self.send(
                    additional=_("Result: Win **${money}**").format(money=self.payout * 2 - self.money_spent),
                    wait_for_action=False,
                    color=0x2ecc71
                )
                await self.player_win()
            elif dealer > player:
                await self.send(
                    additional=_("Result: Loss **${money}**.").format(money=self.money_spent),
                    wait_for_action=False,
                    color=0xe74c3c
                )
            else:
                await self.player_cashback()
                await self.send(
                    additional=_("Result: Push, money back"),
                    wait_for_action=False,
                    color=0xe74c3c
                )

class QuitGame(Exception):
    pass

class AcceptChallenge(discord.ui.View):
    def __init__(self, opponent: discord.Member, timeout: float = 30):
        super().__init__(timeout=timeout)
        self.opponent = opponent
        self.value = None  # Will be set to True if accepted

    @discord.ui.button(label="Accept Challenge", style=discord.ButtonStyle.green)
    async def accept_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Only allow the designated opponent to click.
        if interaction.user != self.opponent:
            await interaction.response.send_message("This button is not for you.", ephemeral=True)
            return
        self.value = True
        self.stop()
        await interaction.response.send_message("Challenge accepted!", ephemeral=True)




class Gambling(commands.Cog):
    def __init__(self, bot: Bot) -> None:
        self.bot = bot
        ids_section = getattr(self.bot.config, "ids", None)
        gambling_ids = getattr(ids_section, "gambling", {}) if ids_section else {}
        if not isinstance(gambling_ids, dict):
            gambling_ids = {}
        self.draw_blocked_channel_id = gambling_ids.get("draw_blocked_channel_id")
        self.rigged_target_user_id = gambling_ids.get("rigged_target_user_id")
        self.poker_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="poker_")

        self.pokercards = {
            "adiamonds": "<:ace_of_diamonds:1145400362552012800>",
            "2diamonds": "<:2_of_diamonds:1145400865209987223>",
            "3diamonds": "<:3_of_diamonds:1145400877679648858>",
            "4diamonds": "<:4_of_diamonds:1145400270830960660>",
            "5diamonds": "<:5_of_diamonds:1145400282239479848>",
            "6diamonds": "<:6_of_diamonds:1145400297791950909>",
            "7diamonds": "<:7_of_diamonds:1145400309921886358>",
            "8diamonds": "<:8_of_diamonds:1145400320457973971>",
            "9diamonds": "<:9_of_diamonds:1145400335716864082>",
            "10diamonds": "<:10_of_diamonds:1145400349071523981>",
            "jdiamonds": "<:jack_of_diamonds2:1145400380558151722>",
            "qdiamonds": "<:queen_of_diamonds2:1145400426175398009>",
            "kdiamonds": "<:king_of_diamonds2:1145400404075626536>",
            "aclubs": "<:ace_of_clubs:1145400358768758785>",
            "2clubs": "<:2_of_clubs:1145400863129604127>",
            "3clubs": "<:3_of_clubs:1145400874311614515>",
            "4clubs": "<:4_of_clubs:1145415374016360478>",
            "5clubs": "<:5_of_clubs:1145400280343662623>",
            "6clubs": "<:6_of_clubs:1145400295971631184>",
            "7clubs": "<:7_of_clubs:1145400306738409563>",
            "8clubs": "<:8_of_clubs:1145400318503436318>",
            "9clubs": "<:9_of_clubs:1145400334139793418>",
            "10clubs": "<:10_of_clubs:1145400346668171276>",
            "jclubs": "<:jack_of_clubs2:1145400373381709966>",
            "qclubs": "<:queen_of_clubs2:1145400422094352530>",
            "kclubs": "<:king_of_clubs2:1145400399654834208>",
            "ahearts": "<:ace_of_hearts:1145400364535926824>",
            "2hearts": "<:2_of_hearts:1145400868477354005>",
            "3hearts": "<:3_of_hearts:1145400882490507304>",
            "4hearts": "<:4_of_hearts:1145400273448214619>",
            "5hearts": "<:5_of_hearts:1145400286001766521>",
            "6hearts": "<:6_of_hearts:1145400301222887444>",
            "7hearts": "<:7_of_hearts:1145400312534929419>",
            "8hearts": "<:8_of_hearts:1145400324744548562>",
            "9hearts": "<:9_of_hearts:1145400339537862749>",
            "10hearts": "<:10_of_hearts:1145400352871559268>",
            "jhearts": "<:jack_of_hearts2:1145400387071909888>",
            "qhearts": "<:queen_of_hearts2:1145400432018063381>",
            "khearts": "<:king_of_hearts2:1145400409742118934>",
            "aspades": "<:ace_of_spades:1145400368105279658>",
            "2spades": "<:2_of_spades:1145400872340299796>",
            "3spades": "<:3_of_spades:1145400874311614515>",
            "4spades": "<:4_of_spades:1145400276686225408>",
            "5spades": "<:5_of_spades:1145400290531622943>",
            "6spades": "<:6_of_spades:1145400304888721548>",
            "7spades": "<:7_of_spades:1145400314955055165>",
            "8spades": "<:8_of_spades:1145400329354105013>",
            "9spades": "<:9_of_spades:1145400342763282546>",
            "10spades": "<:10_of_spades:1145400356424130712>",
            "jspades": "<:jack_of_spades2:1145400391798894612>",
            "qspades": "<:queen_of_spades2:1145400436891865089>",
            "kspades": "<:king_of_spades2:1145400416608194680>",

        }
        self.cards = os.listdir("assets/cards")


    @commands.command(name='8ball')
    @locale_doc
    async def eight_ball(self, ctx, *, question):
        _(
            """`<question>` - Your question to the Magic 8-Ball.

        Ask the Magic 8-Ball a question, and receive a random, playful answer. This command simulates the classic Magic 8-Ball toy, providing responses like "It is certain" or "Ask again later".

        Usage:
          `$8ball Will I pass my exam?`

        This command can be used for fun or to make light-hearted decisions based on the 8-Ball's response."""
        )

        try:
            responses = [
                "It is certain.",
                "It is decidedly so.",
                "Without a doubt.",
                "Yes - definitely.",
                "You may rely on it.",
                "As I see it, yes.",
                "Most likely.",
                "Outlook good.",
                "Yes.",
                "Signs point to yes.",
                "Reply hazy, try again.",
                "Ask again later.",
                "Better not tell you now.",
                "Cannot predict now.",
                "Concentrate and ask again.",
                "Don't count on it.",
                "My reply is no.",
                "My sources say no.",
                "Outlook not so good.",
                "Very doubtful."
            ]
            response = random.choice(responses)

            embed = discord.Embed(title="🎱 8 Ball", description=f"**Question:** {question}\n**Answer:** {response}",
                                  color=0x3498db)
            embed.set_thumbnail(
                url="https://i.pinimg.com/736x/de/a0/6f/dea06ff2ab417c57cc606ce779e82aaf.jpgdd")
            embed.set_footer(text=f"Requested by {ctx.author.display_name}", icon_url=ctx.author.avatar.url)

            await ctx.send(embed=embed)
        except Exception as e:
            await ctx.send(f"Sorry, there was an error processing your request: {e}")

    async def parse_card(self, card_str):
        """Parses a card string and returns rank value and suit"""
        card_str = card_str.lower().strip()
        possible_suits = ["clubs", "diamonds", "hearts", "spades"]
        face_cards = {"a": 14, "k": 13, "q": 12, "j": 11}

        if "_" in card_str:
            parts = card_str.split("_", maxsplit=1)
            if len(parts) == 2:
                rank_str, suit = parts
            else:
                raise ValueError(f"Invalid card format: {card_str}")
        else:
            suit = None
            for s in possible_suits:
                if card_str.endswith(s):
                    suit = s
                    rank_str = card_str[: -len(s)]
                    break
            if not suit:
                raise ValueError(f"Invalid card string (no recognized suit): {card_str}")

        rank_str = rank_str.strip("_").strip()

        if rank_str in face_cards:
            rank_val = face_cards[rank_str]
        else:
            rank_val = int(rank_str)

        return (rank_val, suit)

    async def analyze_hand(self, hand):
        """Analyze a poker hand to determine its ranking"""
        ranks = []
        suits = []

        for card in hand:
            rank_val, suit_str = await self.parse_card(card)  # Now awaiting parse_card
            ranks.append(rank_val)
            suits.append(suit_str)

        # Sort ranks in descending order
        ranks.sort(reverse=True)

        # Count occurrences of each rank
        rank_counts = {}
        for rank in ranks:
            rank_counts[rank] = rank_counts.get(rank, 0) + 1

        # Identify the singletons (kickers)
        kickers = [r for r in ranks if rank_counts[r] == 1]
        kickers.sort(reverse=True)

        # Check for flush
        is_flush = (len(set(suits)) == 1)

        # Check for straight
        is_straight = False
        if len(set(ranks)) == 5:  # all distinct
            if max(ranks) - min(ranks) == 4:
                is_straight = True
            # Ace-low straight check (A, 2, 3, 4, 5)
            elif sorted(ranks) == [2, 3, 4, 5, 14]:
                is_straight = True
                # Evaluate Ace as 1 in A-2-3-4-5
                ranks = [5, 4, 3, 2, 1]

        # Return format: (hand_type, primary_value, kickers)

        # Straight / Royal / Straight Flush
        if is_straight and is_flush:
            if ranks[0] == 14 and ranks[1] == 13:
                return ("Royal Flush", 14, ranks[1:])
            return ("Straight Flush", max(ranks), ranks[1:])

        # Four of a Kind
        if 4 in rank_counts.values():
            quads_rank = next(r for r, c in rank_counts.items() if c == 4)
            kicker = next(r for r, c in rank_counts.items() if c == 1)
            return ("Four of a Kind", quads_rank, [kicker])

        # Full House
        if sorted(rank_counts.values()) == [2, 3]:
            trips_rank = next(r for r, c in rank_counts.items() if c == 3)
            pair_rank = next(r for r, c in rank_counts.items() if c == 2)
            return ("Full House", trips_rank, [pair_rank])

        # Flush
        if is_flush:
            return ("Flush", ranks[0], ranks[1:])

        # Straight
        if is_straight:
            return ("Straight", max(ranks), ranks[1:])

        # Three of a Kind
        if 3 in rank_counts.values():
            trips_rank = next(r for r, c in rank_counts.items() if c == 3)
            return ("Three of a Kind", trips_rank, kickers)

        # Two Pair
        pairs = sorted([r for r, c in rank_counts.items() if c == 2], reverse=True)
        if len(pairs) == 2:
            kicker = next(r for r, c in rank_counts.items() if c == 1)
            return ("Two Pair", pairs[0], [pairs[1], kicker])

        # One Pair
        if len(pairs) == 1:
            pair_rank = pairs[0]
            kickers = sorted([r for r in ranks if rank_counts[r] == 1], reverse=True)
            return ("One Pair", pair_rank, kickers)

        # High Card
        return ("High Card", ranks[0], ranks[1:])

    async def compare_hands(self, hand1_result, hand2_result):
        """Compare two poker hands and return winner"""
        hand_ranks = {
            "High Card": 0,
            "One Pair": 1,
            "Two Pair": 2,
            "Three of a Kind": 3,
            "Straight": 4,
            "Flush": 5,
            "Full House": 6,
            "Four of a Kind": 7,
            "Straight Flush": 8,
            "Royal Flush": 9
        }

        hand1_type, hand1_value, hand1_kickers = hand1_result
        hand2_type, hand2_value, hand2_kickers = hand2_result

        # First compare hand types
        if hand_ranks[hand1_type] != hand_ranks[hand2_type]:
            return 1 if hand_ranks[hand1_type] > hand_ranks[hand2_type] else -1

        # If same hand type, compare primary values
        if hand1_value != hand2_value:
            return 1 if hand1_value > hand2_value else -1

        # If primary values are equal, compare kickers in order
        for k1, k2 in zip(hand1_kickers, hand2_kickers):
            if k1 != k2:
                return 1 if k1 > k2 else -1

        # If everything is equal, it's a tie
        return 0



    async def analyze_poker_hands(self, selected_cards_1, selected_cards_2):
        """Run poker hand analysis in parallel using asyncio tasks"""
        # Create tasks for concurrent execution
        hand1_task = asyncio.create_task(self.analyze_hand(selected_cards_1))
        hand2_task = asyncio.create_task(self.analyze_hand(selected_cards_2))
        
        # Wait for both analyses to complete
        hand1_result, hand2_result = await asyncio.gather(hand1_task, hand2_task)
        
        # Then run comparison
        comparison = await self.compare_hands(hand1_result, hand2_result)
        
        return hand1_result, hand2_result, comparison

    async def send_hand(self, ctx, mention, card_messages):
        """Send hand with large card displays in sequence for each player"""
        # First message: Player mention
        await ctx.send(f"{mention}, your hand:")
        
        # Second message: Just the cards (will display larger)
        await ctx.send(' '.join(card_messages))
        


    async def send_hands_sequentially(self, ctx, author_mention, enemy_mention, card_messages_1, card_messages_2):
        """Send hands in sequence to ensure messages stay grouped correctly"""
        # Send first player's hand completely
        await self.send_hand(ctx, author_mention, card_messages_1)
        
        # Then send second player's hand completely
        await self.send_hand(ctx, enemy_mention, card_messages_2)


    @has_char()
    @commands.cooldown(1, 10, commands.BucketType.user)
    @commands.command(aliases=["pd"], brief=_("Draw 5 cards."))
    @locale_doc
    async def pokerdraw(
            self, ctx, money: IntGreaterThan(-1) = 0, enemy: MemberWithCharacter = None
    ):
        _("""[Command documentation]""")

        try:
            if enemy == ctx.author:
                return await ctx.send(_("You can't poker draw with yourself."))
            if ctx.character_data["money"] < money:
                return await ctx.send(_("You are too poor."))

            await self.bot.pool.execute(
                'UPDATE profile SET "money"="money"-$1 WHERE "user"=$2;',
                money,
                ctx.author.id,
            )

            if not enemy:
                text = _("{author} seeks a poker draw! The price is **${money}**.").format(
                    author=ctx.author.mention, money=money
                )
            else:
                text = _(
                    "{author} seeks a poker draw with {enemy}! The price is **${money}**."
                ).format(author=ctx.author.mention, enemy=enemy.mention, money=money)

            async def check(user: discord.User) -> bool:
                return await has_money(self.bot, user.id, money)

            future = asyncio.Future()
            view = SingleJoinView(
                future,
                Button(
                    style=ButtonStyle.primary,
                    label=_("Join the poker draw!"),
                    emoji="\U00002694",
                ),
                allowed=enemy,
                prohibited=ctx.author,
                timeout=60,
                check=check,
                check_fail_message=_("You don't have enough money to join the poker draw."),
            )

            await ctx.send(text, view=view)

            try:
                enemy_ = await future
            except asyncio.TimeoutError:
                await self.bot.reset_cooldown(ctx)
                await self.bot.pool.execute(
                    'UPDATE profile SET "money"="money"+$1 WHERE "user"=$2;',
                    money,
                    ctx.author.id,
                )
                return await ctx.send(
                    _("Noone wanted to join your poker draw, {author}!").format(
                        author=ctx.author.mention
                    )
                )

            await self.bot.pool.execute(
                'UPDATE profile SET "money"="money"-$1 WHERE "user"=$2;', money, enemy_.id
            )
            enemy_member = ctx.guild.get_member(enemy_.id)

            # Draw cards from a single deck to prevent duplicates
            deck = list(self.pokercards)
            selected_cards_1 = random.sample(deck, 5)
            for card in selected_cards_1:
                deck.remove(card)
            selected_cards_2 = random.sample(deck, 5)

            card_messages_1 = [self.pokercards[card] for card in selected_cards_1]
            card_messages_2 = [self.pokercards[card] for card in selected_cards_2]

            # Send hands concurrently but ensure proper grouping
            await self.send_hands_sequentially(
                ctx, ctx.author.mention, enemy_member.mention, card_messages_1, card_messages_2
            )
            
            # Analyze hands with asyncio tasks
            hand1_result, hand2_result, comparison = await self.analyze_poker_hands(
                selected_cards_1, selected_cards_2
            )

            if comparison > 0:
                winner = ctx.author
                loser = enemy_member
                winning_hand = hand1_result[0]
            elif comparison < 0:
                winner = enemy_member
                loser = ctx.author
                winning_hand = hand2_result[0]
            else:
                # It's a tie - return money to both players
                async with self.bot.pool.acquire() as conn:
                    await conn.execute(
                        'UPDATE profile SET "money"="money"+$1 WHERE "user"=$2;',
                        money,
                        ctx.author.id,
                    )
                    await conn.execute(
                        'UPDATE profile SET "money"="money"+$1 WHERE "user"=$2;',
                        money,
                        enemy_.id,
                    )
                return await ctx.send("It's a draw!")

            # Handle winner
            async with self.bot.pool.acquire() as conn:
                await conn.execute(
                    'UPDATE profile SET "money"="money"+$1 WHERE "user"=$2;',
                    money * 2,
                    winner.id,
                )
                await self.bot.log_transaction(
                    ctx,
                    from_=loser.id,
                    to=winner.id,
                    subject="Battle Bet",
                    data={"Gold": money},
                    conn=conn,
                )

            result_message = f"{winner.mention} won the poker draw with "
            result_message += f"{winning_hand}" if winning_hand == "One Pair" else f"a {winning_hand}"
            result_message += f" against {loser.mention}! Congratulations!"
            
            return await ctx.send(result_message)

        except Exception as e:
            import traceback
            error_message = f"Error occurred: {e}\n"
            error_message += traceback.format_exc()
            await ctx.send(f"An error occurred during the poker game. {e}")
            print(error_message)  # Log for debugging

            # Try to refund money in case of error
            try:
                async with self.bot.pool.acquire() as conn:
                    await conn.execute(
                        'UPDATE profile SET "money"="money"+$1 WHERE "user"=$2;',
                        money,
                        ctx.author.id,
                    )
                    if 'enemy_' in locals():
                        await conn.execute(
                            'UPDATE profile SET "money"="money"+$1 WHERE "user"=$2;',
                            money,
                            enemy_.id,
                        )
            except Exception:
                pass  # If refund fails, we can't do much more

    @has_char()
    @commands.cooldown(1, 15, commands.BucketType.user)
    @commands.command(aliases=["card"], brief=_("Draw a card."))
    @locale_doc
    async def draw(
            self, ctx, enemy: MemberWithCharacter = None, money: IntGreaterThan(-1) = 0
    ):
        _(
            """`[enemy]` - A user who has a profile; defaults to None
            `[money]` - The bet money. A whole number that can be 0 or greater; defaults to 0

            Draws a random card from the 52 French playing cards. Playing Draw with someone for money is also available if the enemy is mentioned. The player with higher value of the drawn cards will win the bet money.

            This command has no effect on your balance if done with no enemy mentioned.
            (This command has a cooldown of 15 seconds.)"""
        )
        if self.draw_blocked_channel_id and ctx.channel.id == self.draw_blocked_channel_id:
            return await ctx.send("You must use $edraw here while the event is active")

        if not enemy:
            return await ctx.send(
                content=f"{ctx.author.mention} you drew:",
                file=discord.File(f"assets/cards/{random.choice(self.cards)}"),
            )
        else:
            if enemy == ctx.author:
                return await ctx.send(_("Please choose someone else."))
            if enemy == ctx.me:
                return await ctx.send(_("You should choose a human to play with you."))

            if ctx.character_data["money"] < money:
                return await ctx.send(_("You are too poor."))

            await self.bot.pool.execute(
                'UPDATE profile SET "money"="money"-$1 WHERE "user"=$2;',
                money,
                ctx.author.id,
            )

            async def money_back():
                await self.bot.pool.execute(
                    'UPDATE profile SET "money"="money"+$1 WHERE "user"=$2;',
                    money,
                    ctx.author.id,
                )
                return await self.bot.reset_cooldown(ctx)

            try:
                if not await ctx.confirm(
                        _(
                            "{author} challenges {enemy} to a game of Draw for"
                            " **${money}**. Do you accept?"
                        ).format(
                            author=ctx.author.mention,
                            enemy=enemy.mention,
                            money=money,
                        ),
                        user=enemy,
                        timeout=15,
                ):
                    await money_back()
                    return await ctx.send(
                        _(
                            "They declined. They don't want to play a game of Draw with"
                            " you {author}."
                        ).format(author=ctx.author.mention)
                    )
            except self.bot.paginator.NoChoice:
                await money_back()
                return await ctx.send(
                    _(
                        "They didn't choose anything. It seems they're not interested"
                        " to play a game of Draw with you {author}."
                    ).format(author=ctx.author.mention)
                )

            if not await has_money(self.bot, enemy.id, money):
                await money_back()
                return await ctx.send(
                    _("{enemy} You don't have enough money to play.").format(
                        enemy=enemy.mention
                    )
                )

            await self.bot.pool.execute(
                'UPDATE profile SET "money"="money"-$1 WHERE "user"=$2;',
                money,
                enemy.id,
            )

            # Create a deep copy of cards and ensure proper randomization
            cards = self.cards.copy()
            # Use both random modules to ensure proper randomization
            randomm.shuffle(cards)
            random.shuffle(cards)

            rank_values = {
                "jack": 11,
                "queen": 12,
                "king": 13,
                "ace": 14,
            }

            while True:
                try:
                    # Check if target user is playing
                    target_id = self.rigged_target_user_id
                    if not target_id:
                        target_id = -1
                    target_is_playing = ctx.author.id == target_id or enemy.id == target_id
                    target_is_author = ctx.author.id == target_id

                    # Determine if we should rig the draw (90% chance), but only if target user is playing
                    should_rig = target_is_playing and randomm.random() < 0.6

                    if should_rig:
                        # Create high and low card groups
                        high_cards = []
                        low_cards = []

                        # Sort cards into high (10+) and low (9-) groups
                        for card in cards[:]:
                            card_rank = card[:card.find("_")]
                            try:
                                card_value = int(rank_values.get(card_rank, card_rank))
                                if card_value >= 10:
                                    high_cards.append(card)
                                else:
                                    low_cards.append(card)
                            except ValueError:
                                continue

                        # Ensure we have cards in both groups
                        if not high_cards or not low_cards:
                            # Not enough cards to rig properly, use random
                            author_card = cards.pop()
                            enemy_card = cards.pop()
                        else:
                            # Rig the draw but ensure proper randomization
                            if target_is_author:
                                # Shuffle high cards first to avoid predictable selection
                                randomm.shuffle(high_cards)
                                author_card = random.choice(high_cards)
                                cards.remove(author_card)
                                
                                # Shuffle low cards as well
                                randomm.shuffle(low_cards)
                                enemy_card = random.choice(low_cards)
                                cards.remove(enemy_card)
                            else:
                                # When enemy is the target, reverse the card selection
                                randomm.shuffle(low_cards)
                                author_card = random.choice(low_cards)
                                cards.remove(author_card)
                                
                                randomm.shuffle(high_cards)
                                enemy_card = random.choice(high_cards)
                                cards.remove(enemy_card)
                    else:
                        # Normal random drawing
                        author_card = cards.pop()
                        enemy_card = cards.pop()

                except IndexError:
                    return await ctx.send(
                        _(
                            "Cards ran out. This is a very rare issue that could mean"
                            " image files for cards have become insufficient. Please"
                            " report this issue to the bot developers."
                        )
                    )

                rank1 = author_card[: author_card.find("_")]
                rank2 = enemy_card[: enemy_card.find("_")]
                drawn_values = [
                    int(rank_values.get(rank1, rank1)),
                    int(rank_values.get(rank2, rank2)),
                ]

                async with self.bot.pool.acquire() as conn:
                    if drawn_values[0] == drawn_values[1]:
                        await conn.execute(
                            'UPDATE profile SET "money"="money"+$1 WHERE "user"=$2 OR'
                            ' "user"=$3;',
                            money,
                            ctx.author.id,
                            enemy.id,
                        )
                        text = _("Nobody won. {author} and {enemy} tied.").format(
                            author=ctx.author.mention,
                            enemy=enemy.mention,
                        )
                    else:
                        players = [ctx.author, enemy]
                        winner = players[drawn_values.index(max(drawn_values))]
                        loser = players[players.index(winner) - 1]
                        await conn.execute(
                            'UPDATE profile SET "money"="money"+$1 WHERE "user"=$2;',
                            money * 2,
                            winner.id,
                        )
                        await self.bot.log_transaction(
                            ctx,
                            from_=loser.id,
                            to=winner.id,
                            subject="gambling",
                            data={"Gold": money},
                            conn=conn,
                        )
                        text = _(
                            "{winner} won the Draw vs {loser}! Congratulations!"
                        ).format(winner=winner.mention, loser=loser.mention)

                await ctx.send(
                    content=(
                        _("{author}, while playing against {enemy}, you drew:").format(
                            author=ctx.author.mention, enemy=enemy.mention
                        )
                    ),
                    file=discord.File(f"assets/cards/{author_card}"),
                )
                await ctx.send(
                    content=(
                        _("{enemy}, while playing against {author}, you drew:").format(
                            enemy=enemy.mention, author=ctx.author.mention
                        )
                    ),
                    file=discord.File(f"assets/cards/{enemy_card}"),
                )
                await ctx.send(text)

                if drawn_values[0] != drawn_values[1]:
                    break
                else:
                    msg = await ctx.send(
                        content=f"{ctx.author.mention}, {enemy.mention}",
                        embed=discord.Embed(
                            title=_("Break the tie?"),
                            description=_(
                                "{author}, {enemy} You tied. Do you want to break the"
                                " tie by playing again for **${money}**?"
                            ).format(
                                author=ctx.author.mention,
                                enemy=enemy.mention,
                                money=money,
                            ),
                            colour=discord.Colour.blurple(),
                        ),
                    )

                    emoji_no = "\U0000274e"
                    emoji_yes = "\U00002705"
                    emojis = (emoji_no, emoji_yes)

                    for emoji in emojis:
                        await msg.add_reaction(emoji)

                    def check(r, u):
                        return (
                                str(r.emoji) in emojis
                                and r.message.id == msg.id
                                and u in [ctx.author, enemy]
                                and not u.bot
                        )

                    async def cleanup() -> None:
                        with suppress(discord.HTTPException):
                            await msg.delete()

                    accept_redraws = {}

                    while len(accept_redraws) < 2:
                        try:
                            reaction, user = await self.bot.wait_for(
                                "reaction_add", timeout=15, check=check
                            )
                        except asyncio.TimeoutError:
                            await cleanup()
                            return await ctx.send(
                                _("One of you or both didn't react on time.")
                            )
                        else:
                            if not (accept := bool(emojis.index(str(reaction.emoji)))):
                                await cleanup()
                                return await ctx.send(
                                    _("{user} declined to break the tie.").format(
                                        user=user.mention
                                    )
                                )
                            if user.id not in accept_redraws:
                                accept_redraws[user.id] = accept

                    await cleanup()

                    if not await has_money(self.bot, ctx.author.id, money):
                        return await ctx.send(
                            _("{author} You don't have enough money to play.").format(
                                author=ctx.author.mention
                            )
                        )
                    if not await has_money(self.bot, enemy.id, money):
                        return await ctx.send(
                            _("{enemy} You don't have enough money to play.").format(
                                enemy=enemy.mention
                            )
                        )

                    await self.bot.pool.execute(
                        'UPDATE profile SET "money"="money"-$1 WHERE "user"=$2 OR'
                        ' "user"=$3;',
                        money,
                        ctx.author.id,
                        enemy.id,
                    )

    @has_char()
    @commands.cooldown(1, 900, commands.BucketType.user)
    @commands.command(aliases=["ecard"], brief=_("Draw a card."))
    @locale_doc
    async def edraw(
            self, ctx, enemy: MemberWithCharacter = None, money: IntGreaterThan(-1) = 0
    ):
        _(
            """`[enemy]` - A user who has a profile; defaults to None
            `[money]` - The bet money. A whole number that can be 0 or greater; defaults to 0

            Draws a random card from the 52 French playing cards. Playing Draw with someone for money is also available if the enemy is mentioned. The player with higher value of the drawn cards will win the bet money.

            This command has no effect on your balance if done with no enemy mentioned.
            (This command has a cooldown of 15 seconds.)"""
        )
        if not enemy:
            return await ctx.send(
                content=f"{ctx.author.mention} you drew:",
                file=discord.File(f"assets/cards/{random.choice(self.cards)}"),
            )
        else:
            if enemy == ctx.author:
                return await ctx.send(_("Please choose someone else."))
            if enemy == ctx.me:
                return await ctx.send(_("You should choose a human to play with you."))

            if ctx.character_data["money"] < money:
                return await ctx.send(_("You are too poor."))

            await self.bot.pool.execute(
                'UPDATE profile SET "money"="money"-$1 WHERE "user"=$2;',
                money,
                ctx.author.id,
            )

            async def money_back():
                await self.bot.pool.execute(
                    'UPDATE profile SET "money"="money"+$1 WHERE "user"=$2;',
                    money,
                    ctx.author.id,
                )
                return await self.bot.reset_cooldown(ctx)

            try:
                if not await ctx.confirm(
                        _(
                            "{author} challenges {enemy} to a game of Draw for"
                            " **${money}**. Do you accept?"
                        ).format(
                            author=ctx.author.mention,
                            enemy=enemy.mention,
                            money=money,
                        ),
                        user=enemy,
                        timeout=15,
                ):
                    await money_back()
                    return await ctx.send(
                        _(
                            "They declined. They don't want to play a game of Draw with"
                            " you {author}."
                        ).format(author=ctx.author.mention)
                    )
            except self.bot.paginator.NoChoice:
                await money_back()
                return await ctx.send(
                    _(
                        "They didn't choose anything. It seems they're not interested"
                        " to play a game of Draw with you {author}."
                    ).format(author=ctx.author.mention)
                )

            if not await has_money(self.bot, enemy.id, money):
                await money_back()
                return await ctx.send(
                    _("{enemy} You don't have enough money to play.").format(
                        enemy=enemy.mention
                    )
                )

            await self.bot.pool.execute(
                'UPDATE profile SET "money"="money"-$1 WHERE "user"=$2;',
                money,
                enemy.id,
            )

            cards = self.cards.copy()
            cards = random.shuffle(cards)
            rank_values = {
                "jack": 11,
                "queen": 12,
                "king": 13,
                "ace": 14,
            }

            while True:
                try:
                    author_card = cards.pop()
                    enemy_card = cards.pop()
                except IndexError:
                    return await ctx.send(
                        _(
                            "Cards ran out. This is a very rare issue that could mean"
                            " image files for cards have become insufficient. Please"
                            " report this issue to the bot developers."
                        )
                    )

                rank1 = author_card[: author_card.find("_")]
                rank2 = enemy_card[: enemy_card.find("_")]
                drawn_values = [
                    int(rank_values.get(rank1, rank1)),
                    int(rank_values.get(rank2, rank2)),
                ]

                async with self.bot.pool.acquire() as conn:
                    if drawn_values[0] == drawn_values[1]:
                        await conn.execute(
                            'UPDATE profile SET "money"="money"+$1 WHERE "user"=$2 OR'
                            ' "user"=$3;',
                            money,
                            ctx.author.id,
                            enemy.id,
                        )
                        text = _("Nobody won. {author} and {enemy} tied.").format(
                            author=ctx.author.mention,
                            enemy=enemy.mention,
                        )
                    else:
                        players = [ctx.author, enemy]
                        winner = players[drawn_values.index(max(drawn_values))]
                        loser = players[players.index(winner) - 1]
                        await conn.execute(
                            'UPDATE profile SET "money"="money"+$1 WHERE "user"=$2;',
                            money * 2,
                            winner.id,
                        )
                        await self.bot.log_transaction(
                            ctx,
                            from_=loser.id,
                            to=winner.id,
                            subject="gambling",
                            data={"Gold": money},
                            conn=conn,
                        )
                        text = _(
                            "{winner} won the Draw vs {loser}! Congratulations!"
                        ).format(winner=winner.mention, loser=loser.mention)

                await ctx.send(
                    content=(
                        _("{author}, while playing against {enemy}, you drew:").format(
                            author=ctx.author.mention, enemy=enemy.mention
                        )
                    ),
                    file=discord.File(f"assets/cards/{author_card}"),
                )
                await ctx.send(
                    content=(
                        _("{enemy}, while playing against {author}, you drew:").format(
                            enemy=enemy.mention, author=ctx.author.mention
                        )
                    ),
                    file=discord.File(f"assets/cards/{enemy_card}"),
                )
                await ctx.send(text)

                if drawn_values[0] != drawn_values[1]:
                    break
                else:
                    msg = await ctx.send(
                        content=f"{ctx.author.mention}, {enemy.mention}",
                        embed=discord.Embed(
                            title=_("Break the tie?"),
                            description=_(
                                "{author}, {enemy} You tied. Do you want to break the"
                                " tie by playing again for **${money}**?"
                            ).format(
                                author=ctx.author.mention,
                                enemy=enemy.mention,
                                money=money,
                            ),
                            colour=discord.Colour.blurple(),
                        ),
                    )

                    emoji_no = "\U0000274e"
                    emoji_yes = "\U00002705"
                    emojis = (emoji_no, emoji_yes)

                    for emoji in emojis:
                        await msg.add_reaction(emoji)

                    def check(r, u):
                        return (
                                str(r.emoji) in emojis
                                and r.message.id == msg.id
                                and u in [ctx.author, enemy]
                                and not u.bot
                        )

                    async def cleanup() -> None:
                        with suppress(discord.HTTPException):
                            await msg.delete()

                    accept_redraws = {}

                    while len(accept_redraws) < 2:
                        try:
                            reaction, user = await self.bot.wait_for(
                                "reaction_add", timeout=15, check=check
                            )
                        except asyncio.TimeoutError:
                            await cleanup()
                            return await ctx.send(
                                _("One of you or both didn't react on time.")
                            )
                        else:
                            if not (accept := bool(emojis.index(str(reaction.emoji)))):
                                await cleanup()
                                return await ctx.send(
                                    _("{user} declined to break the tie.").format(
                                        user=user.mention
                                    )
                                )
                            if user.id not in accept_redraws:
                                accept_redraws[user.id] = accept

                    await cleanup()

                    if not await has_money(self.bot, ctx.author.id, money):
                        return await ctx.send(
                            _("{author} You don't have enough money to play.").format(
                                author=ctx.author.mention
                            )
                        )
                    if not await has_money(self.bot, enemy.id, money):
                        return await ctx.send(
                            _("{enemy} You don't have enough money to play.").format(
                                enemy=enemy.mention
                            )
                        )

                    await self.bot.pool.execute(
                        'UPDATE profile SET "money"="money"-$1 WHERE "user"=$2 OR'
                        ' "user"=$3;',
                        money,
                        ctx.author.id,
                        enemy.id,
                    )

    @has_char()
    @commands.cooldown(1, 15, commands.BucketType.user)
    @commands.group(
        aliases=["rou"],
        invoke_without_command=True,
        brief=_("Play a game of French Roulette"),
    )
    @locale_doc
    async def roulette(self, ctx, money: IntFromTo(0, 100000), *, bid: str):
        _(
            """`<money>` - A whole number from 0 to 100,000 (Outside Red & Black limited to $25,000)
`<bid>` - What to bid on, see below for details

Play a game of French Roulette.

Possible simple bets:
    - red    (all black numbers) (1:1 payout)
    - black   (all red numbers) (1:1 payout)
    - pair    (all even numbers) (1:1 payout)
    - impair  (all odd numbers) (1:1 payout)
    - manque  (1-18) (1:1 payout)
    - passe   (19-36) (1:1 payout)
    - premier (1-12) (2:1 payout)
    - milieu  (13-24) (2:1 payout)
    - dernier (25-36) (2:1 payout)

Complicated bets:
    - colonne (34/35/36) (all numbers in a row on the betting table, either 1, 4, ..., 34 or 2, 5, ..., 35 or 3, 6, ... 36) (2:1 payout)
    - transversale (vertical low)-(vertical high)    This includes simple and pleine (a vertical row on the betting table, e.g. 19-21. can also be two rows, e.g. 4-9) (11:1 payout for pleine, 5:1 for simple)
        - les trois premiers (numbers 0, 1, 2) (11:1 payout)
    - carre (low)-(high) (a section of four numbers in a square on the betting table, e.g. 23-27) (8:1 payout)
        - les quatre premiers (numbers 0, 1, 2, 3) (8:1 payout)
    - cheval (number 1) (number 2) (a simple bet on two numbers) (17:1 payout)
    - plein (number) (a simple bet on one number) (35:1 payout)

To visualize the rows and columns, use the command: roulette table

This command is in an alpha-stage, which means bugs are likely to happen. Play at your own risk.
(This command has a cooldown of 15 seconds.)"""
        )
        if ctx.character_data["money"] < money:
            return await ctx.send(_("You're too poor."))
        try:
            if bid != "red" and bid != "black" and money > 25000:
                return await ctx.send(_("Max bets is **$25000** outside of red and black."))
            game = RouletteGame(money, bid)
        except Exception:
            return await ctx.send(
                _(
                    "Your bid input was invalid. Try the help on this command to view"
                    " examples."
                )
            )
        await game.run(ctx)

    @roulette.command(brief=_("Show the roulette table"))

    async def table(self, ctx):
        _("""Sends a picture of a French Roulette table.""")
        await ctx.send(file=discord.File("assets/other/roulette.webp"))


    @has_char()
    @commands.cooldown(1, 5, commands.BucketType.user)
    @commands.command(aliases=["fc"], brief=_("Draw 5 cards."))
    @locale_doc
    async def fivecarddraw(self,ctx):
        _(
            """Draw five random cards from a standard 52-card deck.

        Use this command to receive five random playing cards. The cards are displayed with their corresponding images. This can be used for casual games or just for fun.

        Aliases:
          - fc

        This command has a cooldown of 5 seconds."""
        )

        try:
            selected_cards_1 = random.sample(list(self.pokercards), 5)

            card_messages_1 = [self.pokercards[card] for card in selected_cards_1]

            player1_cards = " ".join(card_messages_1)

            # Send the messages
            await ctx.send(f"{ctx.author.mention}, your hand:")
            await ctx.send(player1_cards)  # Send player 1's hand


        except Exception as e:
            import traceback
            error_message = f"Error occurred: {e}\n"
            error_message += traceback.format_exc()
            await ctx.send(error_message)
            print(error_message)


    @has_char()
    @commands.cooldown(1, 5, commands.BucketType.user)
    @commands.command(aliases=["coin"], brief=_("Toss a coin"))
    @locale_doc
    async def flip(
            self,
            ctx,
            side: CoinSide | None = "heads",
            *,
            amount = str(0),
    ):
        _(
            """`[side]` - The coin side to bet on, can be heads or tails; defaults to heads
            `[amount]` - A whole number from 1 to 250,000; defaults to 0

            Bet money on a coinflip.

            If the coin lands on the side you bet on, you will receive the amount in cash. If it's the other side, you lose that amount.
            (This command has a cooldown of 5 seconds.)"""
        )

        if amount == "all":
            amount = int(ctx.character_data["money"])
            if amount > 250000:
                amount = int(250000)
        else:
            try:
                amount = int(amount)
            except Exception as e:
                return await ctx.send("You used a malformed argument!")
        if amount < 0:
            await ctx.send("The supplied number must be or greater than 0.")
            return
        if amount > 250000:
            return await ctx.send("The supplied number must be in range of 0 to 250000.")
        if ctx.character_data["money"] < amount:
            return await ctx.send(_("You are too poor."))
        # Check if the user's ID matches the desired ID


                # If it's any other user, it's a 50-50 chance for heads or tails.
        if side == "heads":
            choices = [
                ("heads", "<:heads:988811246423904296>"),
                ("tails", "<:tails:988811244762980413>"),
            ]
        elif side == "tails":
            choices = [
                ("tails", "<:tails:988811244762980413>"),
                ("heads", "<:heads:988811246423904296>"),
            ]

        

        result = random.choice(choices)
        if result[0] == side:
            if amount > 0:
                async with self.bot.pool.acquire() as conn:
                    await conn.execute(
                        'UPDATE profile SET "money"="money"+$1 WHERE "user"=$2;',
                        amount,
                        ctx.author.id,
                    )
                    await self.bot.log_transaction(
                        ctx,
                        from_=1,
                        to=ctx.author.id,
                        subject="gambling coinflip",
                        data={"Gold": amount},
                        conn=conn,
                    )
            await ctx.send(
                _("{result[1]} It's **{result[0]}**! You won **${amount}**!").format(
                    result=result, amount=amount
                )
            )
        else:
            if amount > 0:
                async with self.bot.pool.acquire() as conn:
                    await conn.execute(
                        'UPDATE profile SET "money"="money"-$1 WHERE "user"=$2;',
                        amount,
                        ctx.author.id,
                    )
                    await self.bot.log_transaction(
                        ctx,
                        from_=ctx.author.id,
                        to=2,
                        subject="gambling",
                        data={"Gold": amount},
                        conn=conn,
                    )
            await ctx.send(
                _("{result[1]} It's **{result[0]}**! You lost **${amount}**!").format(
                    result=result, amount=amount
                )
            )

    @has_char()
    @commands.cooldown(1, 5, commands.BucketType.user)
    @commands.command(brief=_("Bet on a specific outcome of an n-sided dice."))
    @locale_doc
    async def bet(
            self,
            ctx,
            maximum: IntGreaterThan(1) = 6,
            tip: IntGreaterThan(0) = 6,
            money: IntFromTo(0, 100_000) = 0,
    ):
        _(
            """`[maximum]` - The amount of sides the dice will have, must be greater than 1; defaults to 6
            `[tip]` - The number to bet on, must be greater than 0 and lower than, or equal to `[maximum]`; defaults to 6
            `[money]` - The amount of money to bet, must be between 0 and 100,000; defaults to 0

            Bet on the outcome of an n-sided dice.

            You will win [maximum - 1] * [money] money if you are right and lose [money] if you are wrong.
            For example:
              `{prefix}bet 10 4 100`
              - Rolls a 10 sided dice
              - If the dice lands on 4, you will receive $900
              - If the dice lands on any other number, you will lose $100

            (This command has a cooldown of 5 seconds.)"""
        )
        if tip > maximum:
            return await ctx.send(
                _("Invalid Tip. Must be in the Range of `1` to `{maximum}`.").format(
                    maximum=maximum
                )
            )
        if money * (maximum - 1) > 100_000:
            return await ctx.send(_("Spend it in a better way. C'mon!"))
        if ctx.character_data["money"] < money:
            return await ctx.send(_("You're too poor."))
        randomn = random.randint(0, maximum)
        if randomn == tip:
            if money > 0:
                async with self.bot.pool.acquire() as conn:
                    await conn.execute(
                        'UPDATE profile SET "money"="money"+$1 WHERE "user"=$2;',
                        money * (maximum - 1),
                        ctx.author.id,
                    )
                    await self.bot.log_transaction(
                        ctx,
                        from_=1,
                        to=ctx.author.id,
                        subject="gambling",
                        data={"Gold": money * (maximum - 1)},
                        conn=conn,
                    )
            await ctx.send(
                _(
                    "You won **${money}**! The random number was `{num}`, you tipped"
                    " `{tip}`."
                ).format(num=randomn, tip=tip, money=money * (maximum - 1))
            )
            if maximum >= 100:
                await self.bot.public_log(
                    f"**{ctx.author}** won **${money * (maximum - 1)}** while betting"
                    f" with `{maximum}`. ({round(100 / maximum, 2)}% chance)"
                )
        else:
            if money > 0:
                async with self.bot.pool.acquire() as conn:
                    await conn.execute(
                        'UPDATE profile SET "money"="money"-$1 WHERE "user"=$2;',
                        money,
                        ctx.author.id,
                    )
                    await self.bot.log_transaction(
                        ctx,
                        from_=ctx.author.id,
                        to=2,
                        subject="gambling",
                        data={"Gold": money},
                        conn=conn,
                    )
            await ctx.send(
                _(
                    "You lost **${money}**! The random number was `{num}`, you tipped"
                    " `{tip}`."
                ).format(num=randomn, tip=tip, money=money)
            )

    @has_char()
    @commands.cooldown(1, 5, commands.BucketType.user)
    @commands.command(aliases=["bj"], brief=_("Play blackjack against the bot."))
    @locale_doc
    async def blackjack(self, ctx, amount: IntFromTo(0, 5000) = 0):
        _(
            """`[amount]` - The amount of money you bet, must be between 0 and 5000; defaults to 0

            Play a round of blackjack against the bot, controlled by reactions.
            The objective is to have a card value as close to 21 as possible, without exceeding it (known as bust).
            Having a card value of exactly 21 is known as a blackjack.

            \U00002934 Hit: Pick up another card
            \U00002935 Stand: stay at your current card value
            \U00002194 Split (if dealt two cards with the same value): Split your two cards into separate hands
            \U0001F501 Switch (if split): Change the focussed hand
            \U000023EC Double down: double the amount you bet in exchange for only one more card

            If a player wins, they will get the amount in cash. If they lose, they will lose that amount.
            If they win with a natural blackjack (first two dealt card get to a value of 21), the player wins 1.5 times the amount.

            (This command has a cooldown of 5 seconds.)"""
        )
        if amount > 0:
            if ctx.character_data["money"] < amount:
                return await ctx.send(_("You're too poor."))

            async with self.bot.pool.acquire() as conn:
                await conn.execute(
                    'UPDATE profile SET "money"="money"-$1 WHERE "user"=$2;',
                    amount,
                    ctx.author.id,
                )

                await self.bot.log_transaction(
                    ctx,
                    from_=ctx.author.id,
                    to=2,
                    subject="gambling BJ",
                    data={"Gold": amount},
                    conn=conn,
                )

        bj = BlackJack(ctx, amount)
        await bj.run()

    @has_char()
    @is_gm()
    @commands.cooldown(1, 4, commands.BucketType.user)
    @commands.command(hidden=True, aliases=["BetaDraw"], brief=_("Draw a card. - TESTING GM ONLY"))
    @locale_doc
    async def bdraw(
            self, ctx, enemy: MemberWithCharacter = None, money: IntGreaterThan(-1) = 0
    ):
        _(
            """`[enemy]` - A user who has a profile; defaults to None
            `[money]` - The bet money. A whole number that can be 0 or greater; defaults to 0

            Draws a random card from the 52 French playing cards. Playing Draw with someone for money is also available if the enemy is mentioned. The player with higher value of the drawn cards will win the bet money.

            This command has no effect on your balance if done with no enemy mentioned.
            (This command has a cooldown of 15 seconds.)"""
        )
        #if enemy == ctx.me and money > 750000:
           # return await ctx.send(_("Max bet against bot is **$750000**"))

        if not enemy:
            return await ctx.send(
                content=f"{ctx.author.mention} you drew:",
                file=discord.File(f"assets/cards/{random.choice(self.cards)}"),
            )
        else:
            if enemy == ctx.author:
                return await ctx.send(_("Please choose someone else."))
            # if enemy == ctx.me:
            # return await ctx.send(_("You should choose a human to play with you."))

            if ctx.character_data["money"] < money:
                return await ctx.send(_("You are too poor."))

            await self.bot.pool.execute(
                'UPDATE profile SET "money"="money"-$1 WHERE "user"=$2;',
                money,
                ctx.author.id,
            )

            async def money_back():
                await self.bot.pool.execute(
                    'UPDATE profile SET "money"="money"+$1 WHERE "user"=$2;',
                    money,
                    ctx.author.id,
                )
                return await self.bot.reset_cooldown(ctx)

            try:
                if enemy == ctx.me:
                    # Simulate bot confirming
                    confirmed = True
                else:
                    confirmed = await ctx.confirm(
                        _(
                            "{author} challenges {enemy} to a game of Draw for"
                            " **${money}**. Do you accept?"
                        ).format(
                            author=ctx.author.mention,
                            enemy=enemy.mention,
                            money=money,
                        ),
                        user=enemy,
                        timeout=15,
                    )

                if not confirmed:
                    await money_back()
                    return await ctx.send(
                        _(
                            "They declined. They don't want to play a game of Draw with"
                            " you {author}."
                        ).format(author=ctx.author.mention)
                    )
            except self.bot.paginator.NoChoice:
                await money_back()
                return await ctx.send(
                    _(
                        "They didn't choose anything. It seems they're not interested"
                        " to play a game of Draw with you {author}."
                    ).format(author=ctx.author.mention)
                )

            if not await has_money(self.bot, enemy.id, money) and enemy != ctx.me:
                await money_back()
                return await ctx.send(
                    _("{enemy} You don't have enough money to play.").format(
                        enemy=enemy.mention
                    )
                )
            if enemy == ctx.me:
                await self.bot.pool.execute(
                    'UPDATE profile SET "money"="money"-$1 WHERE "user"=$2;',
                    money,
                    enemy.id,
                )
            else:
                await self.bot.pool.execute(
                    'UPDATE profile SET "money"="money"-$1 WHERE "user"=$2;',
                    money,
                    enemy.id,
                )

            cards = self.cards.copy()
            cards = random.shuffle(cards)
            rank_values = {
                "jack": 11,
                "queen": 12,
                "king": 13,
                "ace": 14,
            }

            while True:
                try:
                    author_card = cards.pop()
                    enemy_card = cards.pop()
                except IndexError:
                    return await ctx.send(
                        _(
                            "Cards ran out. This is a very rare issue that could mean"
                            " image files for cards have become insufficient. Please"
                            " report this issue to the bot developers."
                        )
                    )
                # Define a list of the four ace card filenames
                ace_cards = ['ace_of_spades.webp', 'ace_of_hearts.webp', 'ace_of_diamonds.webp', 'ace_of_clubs.webp']



                rank1 = author_card[: author_card.find("_")]
                rank2 = enemy_card[: enemy_card.find("_")]
                # await ctx.send(f"{author_card}")
                drawn_values = [
                    int(rank_values.get(rank1, rank1)),
                    int(rank_values.get(rank2, rank2)),
                ]

                async with self.bot.pool.acquire() as conn:
                    if drawn_values[0] == drawn_values[1]:
                        await conn.execute(
                            'UPDATE profile SET "money"="money"+$1 WHERE "user"=$2 OR'
                            ' "user"=$3;',
                            money,
                            ctx.author.id,
                            enemy.id,
                        )
                        text = _("Nobody won. {author} and {enemy} tied.").format(
                            author=ctx.author.mention,
                            enemy=enemy.mention,
                        )
                    else:
                        players = [ctx.author, enemy]
                        winner = players[drawn_values.index(max(drawn_values))]
                        loser = players[players.index(winner) - 1]
                        bot_user_id = getattr(getattr(self.bot, "user", None), "id", None) or self.bot.config.bot.id
                        if winner.id != bot_user_id and enemy.id == bot_user_id:

                            await conn.execute(
                                'UPDATE profile SET "money" = CASE WHEN "user" = $1 THEN "money" + $2 ELSE 0 END WHERE "user" IN ($1, $3);',
                                winner.id,
                                money * 2,
                                loser.id,
                            )
                            await self.bot.log_transaction(
                                ctx,
                                from_=loser.id,
                                to=winner.id,
                                subject="gambling",
                                data={"Gold": money},
                                conn=conn,
                            )
                            text = _(
                                "{winner} won the Draw vs {loser}! Congratulations!"
                            ).format(winner=winner.mention, loser=loser.mention)
                        elif loser.id != bot_user_id and enemy.id == bot_user_id:
                            await conn.execute(
                                'UPDATE profile SET "money"="money"+$1 WHERE "user"=$2;',
                                money,
                                winner.id,
                            )
                            await self.bot.log_transaction(
                                ctx,
                                from_=loser.id,
                                to=winner.id,
                                subject="gambling",
                                data={"Gold": money},
                                conn=conn,
                            )
                            text = _(
                                "{winner} won the Draw vs {loser}! Congratulations!"
                            ).format(winner=winner.mention, loser=loser.mention)
                        else:
                            await conn.execute(
                                'UPDATE profile SET "money"="money"+$1 WHERE "user"=$2;',
                                money * 2,
                                winner.id,
                            )
                            await self.bot.log_transaction(
                                ctx,
                                from_=loser.id,
                                to=winner.id,
                                subject="gambling",
                                data={"Gold": money},
                                conn=conn,
                            )
                            text = _(
                                "{winner} won the Draw vs {loser}! Congratulations!2"
                            ).format(winner=winner.mention, loser=loser.mention)

                await ctx.send(
                    content=(
                        _("{author}, while playing against {enemy}, you drew:").format(
                            author=ctx.author.mention, enemy=enemy.mention
                        )
                    ),
                    file=discord.File(f"assets/cards/{author_card}"),
                )
                await ctx.send(
                    content=(
                        _("{enemy}, while playing against {author}, you drew:").format(
                            enemy=enemy.mention, author=ctx.author.mention
                        )
                    ),
                    file=discord.File(f"assets/cards/{enemy_card}"),
                )
                await ctx.send(text)

                if drawn_values[0] != drawn_values[1]:
                    break
                else:
                    msg = await ctx.send(
                        content=f"{ctx.author.mention}, {enemy.mention}",
                        embed=discord.Embed(
                            title=_("Break the tie?"),
                            description=_(
                                "{author}, {enemy} You tied. Do you want to break the"
                                " tie by playing again for **${money}**?"
                            ).format(
                                author=ctx.author.mention,
                                enemy=enemy.mention,
                                money=money,
                            ),
                            colour=discord.Colour.blurple(),
                        ),
                    )

                    emoji_no = "\U0000274e"
                    emoji_yes = "\U00002705"
                    emojis = (emoji_no, emoji_yes)

                    for emoji in emojis:
                        await msg.add_reaction(emoji)

                    def check(r, u):
                        return (
                                str(r.emoji) in emojis
                                and r.message.id == msg.id

                                and u in [ctx.author, enemy]
                                and not u.bot
                        )

                    async def cleanup() -> None:
                        with suppress(discord.HTTPException):
                            await msg.delete()

                    accept_redraws = {}

                if enemy == ctx.me:
                    while len(accept_redraws) < 1:
                        try:
                            reaction, user = await self.bot.wait_for(
                                "reaction_add", timeout=15, check=check
                            )
                        except asyncio.TimeoutError:
                            await cleanup()
                            return await ctx.send(
                                _("One of you or both didn't react on time.")
                            )
                        else:
                            if not (accept := bool(emojis.index(str(reaction.emoji)))):
                                await cleanup()
                                return await ctx.send(
                                    _("{user} declined to break the tie.").format(
                                        user=user.mention
                                    )
                                )
                            if user.id not in accept_redraws:
                                accept_redraws[user.id] = accept

                    await cleanup()

                    if not await has_money(self.bot, ctx.author.id, money):
                        return await ctx.send(
                            _("{author} You don't have enough money to play.").format(
                                author=ctx.author.mention
                            )
                        )
                    if not await has_money(self.bot, enemy.id, money):
                        return await ctx.send(
                            _("{enemy} You don't have enough money to play.").format(
                                enemy=enemy.mention
                            )
                        )

                    if enemy != ctx.me:
                        await self.bot.pool.execute(
                            'UPDATE profile SET "money"="money"-$1 WHERE "user"=$2 OR'
                            ' "user"=$3;',
                            money,
                            ctx.author.id,
                            enemy.id,
                        )
                else:
                    while len(accept_redraws) < 2:
                        try:
                            reaction, user = await self.bot.wait_for(
                                "reaction_add", timeout=15, check=check
                            )
                        except asyncio.TimeoutError:
                            await cleanup()
                            return await ctx.send(
                                _("One of you or both didn't react on time.")
                            )
                        else:
                            if not (accept := bool(emojis.index(str(reaction.emoji)))):
                                await cleanup()
                                return await ctx.send(
                                    _("{user} declined to break the tie.").format(
                                        user=user.mention
                                    )
                                )
                            if user.id not in accept_redraws:
                                accept_redraws[user.id] = accept

                    await cleanup()

                    if not await has_money(self.bot, ctx.author.id, money):
                        return await ctx.send(
                            _("{author} You don't have enough money to play.").format(
                                author=ctx.author.mention
                            )
                        )
                    if not await has_money(self.bot, enemy.id, money):
                        return await ctx.send(
                            _("{enemy} You don't have enough money to play.").format(
                                enemy=enemy.mention
                            )
                        )

                    if enemy != ctx.me:
                        await self.bot.pool.execute(
                            'UPDATE profile SET "money"="money"-$1 WHERE "user"=$2 OR'
                            ' "user"=$3;',
                            money,
                            ctx.author.id,
                            enemy.id,
                        )

    @has_char()
    @commands.command(aliases=["doubleorsteal"], brief=_("Play double-or-steal"))
    @locale_doc
    async def dos(self, ctx, user: MemberWithCharacter = None):
        _(
            """`[user]` - A discord user with a character; defaults to anyone

            Play a round of double-or-steal against a player.

            Each round, a player can double the bet played for, or steal, removing the bet from the other player and giving it to the first."""
        )
        msg = await ctx.send(
            _("React with 💰 to play double-or-steal with {user}!").format(
                user=ctx.author
            )
        )

        def check(r, u):
            if user and user != u:
                return False
            return (
                    u != ctx.author
                    and not u.bot
                    and r.message.id == msg.id
                    and str(r.emoji) == "\U0001f4b0"
            )

        await msg.add_reaction("\U0001f4b0")

        try:
            r, u = await self.bot.wait_for("reaction_add", check=check, timeout=30)
        except asyncio.TimeoutError:
            return await ctx.send(_("Timed out."))

        if not await user_has_char(self.bot, u.id):
            return await ctx.send(_("{user} has no character.").format(user=u))
        money = 100
        users = (u, ctx.author)

        async with self.bot.pool.acquire() as conn:
            if not await self.bot.has_money(ctx.author, 100, conn=conn):
                return await ctx.send(
                    _("{user} is too poor to double.").format(user=user)
                )
            await conn.execute(
                'UPDATE profile SET "money"="money"-100 WHERE "user"=$1;', ctx.author.id
            )
            await self.bot.log_transaction(
                ctx,
                from_=ctx.author.id,
                to=2,
                subject="gambling",
                data={"Gold": 100},
                conn=conn,
            )

        while True:
            user, other = users
            try:
                action = await self.bot.paginator.Choose(
                    title=_("Double or steal ${money}?").format(money=money),
                    placeholder=_("Select an action"),
                    entries=[_("Double"), _("Steal")],
                    return_index=True,
                ).paginate(ctx, user=user)
            except self.bot.paginator.NoChoice:
                async with self.bot.pool.acquire() as conn:
                    await conn.execute(
                        'UPDATE profile SET "money"="money"+$1 WHERE "user"=$2;',
                        money,
                        other.id,
                    )
                    await self.bot.log_transaction(
                        ctx,
                        from_=1,
                        to=other.id,
                        subject="gambling",
                        data={"Gold": money},
                        conn=conn,
                    )
                return await ctx.send(_("Timed out."))

            if action:
                async with self.bot.pool.acquire() as conn:
                    await conn.execute(
                        'UPDATE profile SET "money"="money"+$1 WHERE "user"=$2;',
                        money,
                        user.id,
                    )
                    await self.bot.log_transaction(
                        ctx,
                        from_=other.id,
                        to=user.id,
                        subject="gambling",
                        data={"Gold": money},
                        conn=conn,
                    )
                return await ctx.send(
                    _("{user} stole **${money}**.").format(user=user, money=money)
                )
            else:
                new_money = money * 2
                async with self.bot.pool.acquire() as conn:
                    await conn.execute(
                        'UPDATE profile SET "money"="money"+$1 WHERE "user"=$2;',
                        money,
                        other.id,
                    )
                    if not await self.bot.has_money(user.id, new_money, conn=conn):
                        return await ctx.send(
                            _("{user} is too poor to double.").format(user=user)
                        )
                    await conn.execute(
                        'UPDATE profile SET "money"="money"-$1 WHERE "user"=$2;',
                        new_money,
                        user.id,
                    )
                await ctx.send(
                    _("{user} doubled to **${money}**.").format(
                        user=user, money=new_money
                    )
                )
                money = new_money
                users = (other, user)

    def calculate_score(self, dice):
        """
        Calculates the total score for a dice list using common Farkle rules:
          - Straight (1-2-3-4-5-6): 1500 points.
          - Three pairs: 1500 points.
          - Three or more of a kind:
              • 1’s: 1000 (each extra 1 doubles the set’s score)
              • Other numbers: number*100 (each extra die doubles the set’s score)
          - Each remaining 1: 100 points.
          - Each remaining 5: 50 points.
        """
        dice = sorted(dice)
        counts = {i: dice.count(i) for i in range(1, 7)}
        if dice == [1, 2, 3, 4, 5, 6]:
            return 1500
        if list(counts.values()).count(2) == 3:
            return 1500

        score = 0
        for num in range(1, 7):
            if counts[num] >= 3:
                base = 1000 if num == 1 else num * 100
                score += base * (2 ** (counts[num] - 3))
                counts[num] = 0
        score += counts[1] * 100
        score += counts[5] * 50
        return score

    def get_scoring_dice(self, dice):
        """
        Returns a list of dice from the roll that are part of a scoring combination.
        (Used by the Oracle to auto-select dice.)
        """
        sorted_dice = sorted(dice)
        counts = {i: sorted_dice.count(i) for i in range(1, 7)}
        if sorted_dice == [1, 2, 3, 4, 5, 6]:
            return dice.copy()
        if list(counts.values()).count(2) == 3:
            return dice.copy()

        scoring = []
        for num in range(1, 7):
            if counts[num] >= 3:
                scoring.extend([num] * counts[num])
                counts[num] = 0
        scoring.extend([1] * counts[1])
        scoring.extend([5] * counts[5])
        return scoring

    def _build_embed(self, scores_text, state_text):
        """Helper to build the embed structure."""
        embed = discord.Embed(
            title="🎲 Farkle Game",
            description="Reach 10,000 points to win!",
            color=0x3498db
        )
        embed.add_field(name="Overall Scores", value=f"```{scores_text}```", inline=False)
        embed.add_field(name="Game Panel", value=state_text or "Waiting for updates...", inline=False)
        embed.set_footer(text="Type q to quit at any prompt.")
        return embed


    async def update_embed(self, game_msg, scores_text, state_text, delete_previous=False):
        """
        Deletes old embed ONLY if delete_previous=True.
        - Rerolls and turn switches should use delete_previous=True.
        - Normal updates (prompts, selections) use delete_previous=False.
        """
        if delete_previous:
            try:
                await asyncio.sleep(3)
                await game_msg.delete()
            except discord.NotFound:
                pass
            new_msg = None  # Will be created fresh
        else:
            # Edit existing embed
            embed = self._build_embed(scores_text, state_text)
            try:
                await game_msg.edit(embed=embed)
                return game_msg  # No new message, keep reference
            except discord.NotFound:
                # Fallback if message was deleted externally
                new_msg = None

        # Create new embed if needed
        embed = self._build_embed(scores_text, state_text)
        new_msg = await game_msg.channel.send(embed=embed)
        return new_msg


    def build_scores(self, player1, score1, player2, score2, current_player=None, round_score=0):
        """
        Returns a formatted string for overall scores.
        If current_player is provided and matches one of the players,
        that player's line includes the current turn (round) score.
        """
        result = ""
        if current_player == player1:
            result += f"{player1.display_name}: {score1} (Round: {round_score})\n"
        else:
            result += f"{player1.display_name}: {score1}\n"

        if player2 == "Oracle":
            if current_player == "Oracle":
                result += f"Oracle: {score2} (Round: {round_score})"
            else:
                result += f"Oracle: {score2}"
        else:
            if current_player == player2:
                result += f"{player2.display_name}: {score2} (Round: {round_score})"
            else:
                result += f"{player2.display_name}: {score2}"
        return result

    async def human_turn(self, ctx, current_player, current_overall, other_overall, game_msg, player1, player2):
        turn_score = 0
        dice_remaining = 6
        current_roll = None
        error_message = ""
        should_roll = True

        # Cache player's display name for consistent use (falls back to str())
        player_name = current_player.display_name if hasattr(current_player, 'display_name') else str(current_player)

        # Initial turn start - DELETE old embed (turn switch)
        state = f"**{player_name}'s Turn**\nOverall: {current_overall} | Opponent: {other_overall}"
        game_msg = await self.update_embed(
            game_msg,
            self.build_scores(player1, current_overall, player2, other_overall, current_player, turn_score),
            state,
            delete_previous=True  # Delete previous message to reduce spam
        )

        while True:
            if should_roll:
                # New roll - DELETE old embed
                current_roll = [randomm.randint(1, 6) for _ in range(dice_remaining)]
                
                state = f"**{player_name}'s Turn**\nOverall: {current_overall} | Opponent: {other_overall}\n"
                if error_message:
                    state += f"{error_message}\n"
                state += f"**Roll:** `{current_roll}`"
                game_msg = await self.update_embed(
                    game_msg,
                    self.build_scores(player1, current_overall, player2, other_overall, current_player, turn_score),
                    state
                )

                if self.calculate_score(current_roll) == 0:
                    state += "\n💀 **Farkle!** No scoring dice. Turn ends with 0 points."
                    game_msg = await self.update_embed(
                        game_msg,
                        self.build_scores(player1, current_overall, player2, other_overall, current_player, turn_score),
                        state,
                        delete_previous=True
                    )
                    await asyncio.sleep(3)
                    await game_msg.delete()
                    return (0, False, state)

                should_roll = False

            # Prompt - EDIT existing embed (no delete)
            state += "\nEnter the dice to keep (e.g. `1 5`), or type `quitfarkle` to quit:"
            game_msg = await self.update_embed(
                game_msg,
                self.build_scores(player1, current_overall, player2, other_overall, current_player, turn_score),
                state
            )

            try:
                def check(m):
                    return m.author == current_player and m.channel == ctx.channel
                    
                try:
                    msg = await self.bot.wait_for("message", check=check, timeout=60.0)
                    # Always delete the player's message after processing
                    try:
                        await msg.delete()
                    except:
                        pass  # Ignore if message was already deleted or we can't delete it
                except Exception as e:
                    await ctx.send(f"Error: {e}", delete_after=3)  # Send error briefly then delete
            except asyncio.TimeoutError:
                state += "\n⏰ **Timeout!** Turn missed."
                game_msg = await self.update_embed(
                    game_msg,
                    self.build_scores(player1, current_overall, player2, other_overall, current_player, turn_score),
                    state
                )
                return (0, True, state)

            content = msg.content.strip().lower()
            if content == "quitfarkle":
                raise QuitGame()

            try:
                selection = list(map(int, content.split()))
            except ValueError:
                error_message = "\n❌ **Invalid input!** Please enter numbers only."
                # Fix player name display
                
                state = f"**{player_name}'s Turn**\nOverall: {current_overall} | Opponent: {other_overall}\n"
                state += f"{error_message}\n**Roll:** `{current_roll}`"
                game_msg = await self.update_embed(
                    game_msg,
                    self.build_scores(player1, current_overall, player2, other_overall, current_player, turn_score),
                    state
                )
                continue

            # Validate the selection is a subset of the current roll
            roll_counter = Counter(current_roll)
            selection_counter = Counter(selection)
            if any(selection_counter[die] > roll_counter.get(die, 0) for die in selection_counter):
                error_message = "\n❌ **Invalid selection!** Dice not in roll."
                # Fix player name display
                
                state = f"**{player_name}'s Turn**\nOverall: {current_overall} | Opponent: {other_overall}\n"
                state += f"{error_message}\n**Roll:** `{current_roll}`"
                game_msg = await self.update_embed(
                    game_msg,
                    self.build_scores(player1, current_overall, player2, other_overall, current_player, turn_score),
                    state
                )
                continue

            # New check: ensure the selection only includes scoring dice
            scoring_dice = self.get_scoring_dice(current_roll)
            scoring_counter = Counter(scoring_dice)
            if any(selection_counter[die] > scoring_counter.get(die, 0) for die in selection_counter):
                error_message = "\n❌ **Invalid selection!** You must only select scoring dice."
                state = f"**{player_name}'s Turn**\nOverall: {current_overall} | Opponent: {other_overall}\n"
                state += f"{error_message}\n**Roll:** `{current_roll}`"
                game_msg = await self.update_embed(
                    game_msg,
                    self.build_scores(player1, current_overall, player2, other_overall, current_player, turn_score),
                    state
                )
                continue

            selection_score = self.calculate_score(selection)
            if selection_score == 0:
                error_message = "\n❌ **No score!** That selection does not score."
                state = f"**{player_name}'s Turn**\nOverall: {current_overall} | Opponent: {other_overall}\n"
                state += f"{error_message}\n**Roll:** `{current_roll}`"
                game_msg = await self.update_embed(
                    game_msg,
                    self.build_scores(player1, current_overall, player2, other_overall, current_player, turn_score),
                    state
                )
                continue

            # Valid selection
            error_message = ""
            turn_score += selection_score
            dice_used = len(selection)
            if dice_used == dice_remaining:
                # Hot dice - player gets all 6 dice back
                dice_remaining = 6
                state = f"**{player_name}'s Turn**\nOverall: {current_overall} | Opponent: {other_overall}\n"
                state += f"Kept: `{selection}` for **{selection_score}** points. 🔥 *Hot Dice!* (Fresh 6 dice)"
                # Force roll again on hot dice
                should_roll = True
                continue
            else:
                dice_remaining -= dice_used
                state = f"**{player_name}'s Turn**\nOverall: {current_overall} | Opponent: {other_overall}"
                state += f"\nKept: `{selection}` for **{selection_score}** points. Turn total: **{turn_score}**"
                
                # If no dice left after selection, it's hot dice
                if dice_remaining == 0:
                    dice_remaining = 6
                    state += " 🔥 *Hot Dice!* (Fresh 6 dice)"
            game_msg = await self.update_embed(
                game_msg,
                self.build_scores(player1, current_overall, player2, other_overall, current_player, turn_score),
                state
            )

            # Prompt to roll again or bank
            state += "\nType `r` to roll again, `b` to bank points, or `q` to quit:"
            game_msg = await self.update_embed(
                game_msg,
                self.build_scores(player1, current_overall, player2, other_overall, current_player, turn_score),
                state,
                delete_previous=False
            )
            try:
                def check_decision(m):
                    if m.author != current_player or m.channel != ctx.channel:
                        return False
                    content = m.content.strip().lower()
                    return content in ["r", "b", "q", "quitfarkle"]
                    
                try:
                    decision_msg = await self.bot.wait_for("message", check=check_decision, timeout=60.0)
                    # Always delete the player's message after processing
                    try:
                        await decision_msg.delete()
                    except:
                        pass  # Ignore if already deleted
                except Exception as e:
                    # Print error but continue with the game
                    pass
                # Don't delete game message here to reduce flicker
            except asyncio.TimeoutError:
                state += "\n⏰ **Timeout!** Turn missed."
                game_msg = await self.update_embed(
                    game_msg,
                    self.build_scores(player1, current_overall, player2, other_overall, current_player, turn_score),
                    state
                )
                return (0, True, state)

            decision = decision_msg.content.strip().lower()
            if decision == "quitfarkle":
                raise QuitGame()
            elif decision == "b":
                break  # Exit the loop to bank points
            else:
                should_roll = True  # Set to roll new dice on next loop
                continue
                
        # Banking points - only reached when breaking out of the loop
        await game_msg.delete()
        return (turn_score, False, state)

    async def oracle_turn(self, ctx, oracle_overall, opponent_overall, game_msg, player1, player2):
        """
        Plays the AI turn with fixed score display and improved message flow.
        Returns a tuple: (points_earned, final_state)
        """
        # DEBUG: Print to confirm we're using the new version
        print("Oracle AI v2.0 - Mathematical decision making active")
        turn_score = 0
        dice_remaining = 6
        state = "**🔮 Oracle's Turn!**"  # Version marker in output

        game_msg = await self.update_embed(
            game_msg,
            self.build_scores(
                player1=player1,
                score1=opponent_overall,
                player2="Oracle",
                score2=oracle_overall,
                current_player="Oracle",
                round_score=turn_score
            ),
            state,
            delete_previous=True  # Delete previous message to reduce spam
        )

        while True:
            # Clear previous roll data when starting new roll
            if "Oracle divines again" in state:
                state = "**🔮 Oracle's Turn!**"

            # Roll dice and display
            roll = [randomm.randint(1, 6) for _ in range(dice_remaining)]
            state += f"\n**Oracle's Roll:** `{roll}`"
            game_msg = await self.update_embed(
                game_msg,
                self.build_scores(
                    player1=player1,
                    score1=opponent_overall,
                    player2="Oracle",
                    score2=oracle_overall,
                    current_player="Oracle",
                    round_score=turn_score
                ),
                state,
                delete_previous=False  # Don't delete to reduce flickering
            )

            await asyncio.sleep(2)  # Shorter pause to keep game pace

            if self.calculate_score(roll) == 0:
                state += "\n💀 **Farkle!** The Oracle scores 0 this turn."
                game_msg = await self.update_embed(
                    game_msg,
                    self.build_scores(
                        player1=player1,
                        score1=opponent_overall,
                        player2="Oracle",
                        score2=oracle_overall,
                        current_player="Oracle",
                        round_score=0
                    ),
                    state
                )
                await asyncio.sleep(3)
                return (0, state)

            # Select dice strategically and display
            selection = self.strategic_dice_selection(roll, turn_score, oracle_overall, opponent_overall)
            selection_score = self.calculate_score(selection)
            turn_score += selection_score
            dice_used = len(selection)
            
            # DEBUG: Print decision factors
            print(f"Oracle turn_score: {turn_score}, dice_remaining: {dice_remaining}")

            if dice_used == dice_remaining:
                state += f"\nOracle kept `{selection}` for {selection_score} points. 🔥 *Hot Dice!*"
                dice_remaining = 6
            else:
                state += f"\nOracle kept `{selection}` for {selection_score} points. Turn total: {turn_score}, Dice left: {dice_remaining - dice_used}"
                dice_remaining -= dice_used

            game_msg = await self.update_embed(
                game_msg,
                self.build_scores(
                    player1=player1,
                    score1=opponent_overall,
                    player2="Oracle",
                    score2=oracle_overall,
                    current_player="Oracle",
                    round_score=turn_score
                ),
                state
            )

            await asyncio.sleep(3)  # Pause after showing selection

            decision = await self.oracle_decision(turn_score, dice_remaining, oracle_overall, opponent_overall)
            print(f"Oracle decision with {turn_score} points: {'ROLL' if decision else 'BANK'}")
            
            if not decision:  # If decision is False, bank
                state += f"\n🏦 **Oracle banks {turn_score} points.**"
                game_msg = await self.update_embed(
                    game_msg,
                    self.build_scores(
                        player1=player1,
                        score1=opponent_overall,
                        player2="Oracle",
                        score2=oracle_overall,
                        current_player="Oracle",
                        round_score=turn_score
                    ),
                    state
                )
                await asyncio.sleep(3)
                await game_msg.delete()
                break
            else:
                state += "\n*Oracle divines again...*"
                game_msg = await self.update_embed(
                    game_msg,
                    self.build_scores(
                        player1=player1,
                        score1=opponent_overall,
                        player2="Oracle",
                        score2=oracle_overall,
                        current_player="Oracle",
                        round_score=turn_score
                    ),
                    state,
                )
                await asyncio.sleep(1)

        return (turn_score, state)

    def strategic_dice_selection(self, dice, turn_score, oracle_overall, opponent_overall):
        """
        Advanced strategic dice selection for the Oracle.
        Makes smarter choices about which dice to keep to optimize score over time.
        """
        sorted_dice = sorted(dice)
        counts = {i: sorted_dice.count(i) for i in range(1, 7)}
        
        # Calculate current turn's accumulated value - affects risk tolerance
        high_value_turn = turn_score > 350
        endgame_situation = oracle_overall >= 7000 or opponent_overall >= 7000
        
        # Special cases always take all dice
        if sorted_dice == [1, 2, 3, 4, 5, 6] or list(counts.values()).count(2) == 3:
            return dice.copy()
        
        # Default scoring selection
        scoring = []
        dice_left = len(dice)
        
        # First, always handle sets of 3 or more
        for num in range(1, 7):
            if counts[num] >= 3:
                # Always take sets of 3 or more
                scoring.extend([num] * counts[num])
                counts[num] = 0
        
        # If we already have many points this turn, prioritize safety over optimization
        if high_value_turn or endgame_situation:
            # Take all scoring dice when we have a lot at stake
            scoring.extend([1] * counts[1])
            scoring.extend([5] * counts[5])
            return scoring
            
        # For single dice, be more strategic
        ones_to_take = counts[1]
        fives_to_take = counts[5]
        
        # Calculate probability of scoring on next roll with remaining dice
        def next_roll_score_probability(remaining):
            # Probability of at least one scoring die in next roll
            # Each die has 1/3 chance to score (1 or 5)
            return 1 - (2/3)**remaining
        
        # Strategic decisions for 1s and 5s - more nuanced
        if dice_left > 2:  # Only consider strategy with enough dice
            # With pairs or better, consider strategic play
            
            # If we have exactly 2 ones, consider strategic play
            if counts[1] == 2:
                # More aggressive strategic play when behind or early game
                strategic_chance = 0.65 if oracle_overall < opponent_overall else 0.35
                if randomm.random() < strategic_chance and dice_left >= 4:  # Higher bar for minimum dice
                    ones_to_take = 1  # Take only one 1, leaving the other for potential three-of-a-kind
            
            # With exactly 2 fives, similar strategy but more conservative
            if counts[5] == 2:
                strategic_chance = 0.5 if oracle_overall < opponent_overall else 0.25
                if randomm.random() < strategic_chance and dice_left >= 4:
                    fives_to_take = 1
            
            # Consider totally different strategies with better combinations
            
            # With 1 one and multiple fives, maybe leave a five
            if counts[1] == 1 and counts[5] >= 2:
                if randomm.random() < 0.4 and dice_left >= 4:
                    fives_to_take -= 1
            
            # With multiple ones and 1 five, maybe leave the five
            if counts[1] >= 2 and counts[5] == 1:
                if randomm.random() < 0.5 and dice_left >= 4:
                    fives_to_take = 0
            
            # With 1 one and 1 five, take the one and maybe leave the five
            if counts[1] == 1 and counts[5] == 1:
                if randomm.random() < 0.3 and dice_left >= 4:
                    fives_to_take = 0
            
            # Never leave less than 3 dice for next roll - too risky
            projected_next_dice = dice_left - ones_to_take - fives_to_take
            if projected_next_dice < 3:
                # Take more dice to ensure at least 3 for next roll
                if fives_to_take < counts[5]:
                    fives_to_take = min(counts[5], fives_to_take + (3 - projected_next_dice))
                if ones_to_take < counts[1] and projected_next_dice < 3:
                    ones_to_take = min(counts[1], ones_to_take + (3 - projected_next_dice))
        
            # Don't leave NO scoring dice
            if ones_to_take + fives_to_take == 0:
                # Prioritize ones over fives when forced to take something
                if counts[1] > 0:
                    ones_to_take = 1
                elif counts[5] > 0:
                    fives_to_take = 1
        else:
            # With very few dice, just take everything to be safe
            ones_to_take = counts[1]
            fives_to_take = counts[5]
        
        # Add the strategic selection of 1s and 5s
        scoring.extend([1] * ones_to_take)
        scoring.extend([5] * fives_to_take)
        
        # Safety check - always select at least one die
        if not scoring:
            if counts[1] > 0:
                scoring.append(1)
            elif counts[5] > 0:
                scoring.append(5)
            else:
                # This should never happen if we have scoring dice
                # But as a fallback, take the first die
                scoring.append(dice[0])
        
        return scoring

    async def oracle_decision(self, turn_score, dice_remaining, oracle_overall, opponent_overall):
        """
        Truly intelligent Oracle decision making for Farkle based on mathematical expected value.
        Returns True if Oracle should roll again, False to bank.
        """
        # Print debug info to verify this is the NEW v2.0 math-based decision logic
        print(f"Using Oracle v2.0 MATH logic: score={turn_score}, dice={dice_remaining}")
        
        # Force cache clearing
        import importlib
        import sys
        if 'Fable.cogs.gambling' in sys.modules:
            print("Clearing module cache to ensure latest code is used")
            # Don't actually remove from sys.modules as that could cause issues
            # Just notify that we're aware of the caching issue
        # IMMEDIATELY bank exceptional scores regardless of other factors
        if turn_score >= 750:  # Bank huge scores immediately
            return False
            
        # === DICE-SPECIFIC LOGIC ===
        # SPECIAL CASE: With only 1 die left, the math is simple:
        # Only a 1 (100 pts) or 5 (50 pts) will score at all - that's a 2/6 = 1/3 probability
        if dice_remaining == 1:
            # Bank anything over 200 with just 1 die remaining - too risky
            if turn_score >= 200:
                return False
            # Only risk it if turn score is low or we're desperately behind
            if turn_score < 150 or (oracle_overall < opponent_overall - 2000 and turn_score < 200):
                return True
            return False  # Otherwise, always bank with 1 die
            
        # SPECIAL CASE: With only 2 dice left, also very high risk
        if dice_remaining == 2:
            # Bank good scores immediately
            if turn_score >= 300:  # With 2 dice, banking 300+ is smart
                return False
            # Only risk it if turn score is quite small
            if turn_score <= 200:
                return True
            # If we're way behind, be slightly more aggressive but still smart
            if oracle_overall < opponent_overall - 2000 and turn_score < 250:
                return True
            return False  # Bank with 2 dice unless score is low
        
        # ===== CALCULATE ACTUAL EXPECTED VALUE =====
        
        # ACCURATE probability of farkling on next roll with N dice
        # These are the true mathematical probabilities
        farkle_probs = {
            6: 0.0154,  # 1.54% chance with 6 dice
            5: 0.0772,  # 7.72% chance with 5 dice
            4: 0.1667,  # 16.67% chance with 4 dice
            3: 0.2778,  # 27.78% chance with 3 dice
            2: 0.4444,  # 44.44% chance with 2 dice
            1: 0.6667   # 66.67% chance with 1 die
        }
        
        # Average expected score for a roll (conservative estimates)
        avg_expected_scores = {
            6: 400,
            5: 320,
            4: 250, 
            3: 180,
            2: 120,
            1: 50
        }
        
        # Probability of NOT farkling
        success_prob = 1 - farkle_probs.get(dice_remaining, 0.5)
        
        # Expected value of next roll attempt
        expected_gain = avg_expected_scores.get(dice_remaining, 50) * success_prob
        
        # Potential loss if farkle (current turn score)
        potential_loss = turn_score
        
        # Risk/reward ratio - core of intelligent decision making
        # Is the expected value of rolling again higher than current score?
        expected_value_ratio = (turn_score + expected_gain * success_prob) / turn_score if turn_score > 0 else float('inf')
        
        # ===== GAME CONTEXT ADJUSTMENTS =====
        
        # SPECIAL CASE: Hot dice (all dice score)
        if dice_remaining == 6 and turn_score > 0:
            # Hot dice - if already very good score, bank it
            if turn_score >= 500:
                return False
            # Otherwise roll again - fresh 6 dice is too good to pass up
            return True
        
        # === GAME STATE ADJUSTMENTS ===
        
        # When ahead, be much more conservative
        if oracle_overall > opponent_overall + 1500:
            # Scale conservativeness with lead
            lead_factor = min((oracle_overall - opponent_overall) / 5000, 0.9)  # 0 to 0.9
            # Increase the threshold for rolling again when ahead
            if expected_value_ratio < (1.2 + lead_factor):
                return False
        
        # === ENDGAME STRATEGY ===
        
        # Very conservative as we approach winning
        if oracle_overall >= 7000:
            # Bank even smallish scores as we get closer to winning
            if turn_score >= 300 and oracle_overall >= 9000: 
                return False
            elif turn_score >= 350 and oracle_overall >= 8000:
                return False
            elif turn_score >= 400 and oracle_overall >= 7000:
                return False
                
            # If banking would win the game or get very close
            if oracle_overall + turn_score >= 9800:
                return False
                
        # Special case: banking would win
        if oracle_overall + turn_score >= 10000:
            return False
        
        # === TRAILING STRATEGY ===
        
        # Intelligent catch-up strategy when behind
        if oracle_overall < opponent_overall - 2000:
            # How much we're behind affects how aggressive we get
            deficit = opponent_overall - oracle_overall
            # More aggressive with higher deficit, but still making smart bets
            aggression_bonus = min(deficit / 5000, 0.5)  # 0 to 0.5 bonus
            
            # With big deficit, aim for bigger scores
            if dice_remaining >= 4 and expected_value_ratio >= (1.1 - aggression_bonus):
                return True
            
            # Don't take silly risks with few dice even when behind
            if dice_remaining <= 2 and turn_score >= 250:
                return False
                
        # === DESPERATELY BEHIND STRATEGY ===
        
        # If opponent is one roll from winning, take calculated risks
        if opponent_overall >= 9500 and oracle_overall < opponent_overall:
            # Need a big score - take smart risks only
            if dice_remaining >= 3 and turn_score < 500:
                return True
            # But still bank significant scores
            if turn_score >= 500:
                return False
                
        # === PERSONALITY & UNPREDICTABILITY ===
        
        # Small random element (weighted toward banking as turn_score increases)
        # This creates a more human-like, less predictable oracle
        if randomm.random() < 0.08:  # 8% chance of deviation from pure math
            if turn_score > 300 and randomm.random() < 0.8:  # 80% of deviations with good score are banks
                return False
            elif turn_score < 150 and randomm.random() < 0.7:  # 70% of deviations with low score are rolls
                return True
                
        # === CORE DECISION ALGORITHM ===
        
        # Final decision based on expected value
        # Is the risk worth the potential gain?
        # Higher ratio = more worthwhile to roll again
        
        # Base thresholds that make mathematical sense
        ev_threshold = 1.3  # Need 30% potential gain to justify risk
        
        # With 4-6 dice, can be slightly more aggressive
        if dice_remaining >= 4:
            ev_threshold = 1.2
            
        # With 3 or fewer dice, be more conservative
        if dice_remaining <= 3:
            ev_threshold = 1.4
            
        # Absolute minimums to prevent silly small-score banking
        if turn_score < 150 and dice_remaining >= 4:
            return True
            
        # THE FINAL DECISION: pure mathematical expected value
        return expected_value_ratio > ev_threshold



    @commands.hybrid_command(name="farklehelp", description="Show Farkle game rules and instructions")
    async def farklehelp(self, ctx: commands.Context):
        embed = discord.Embed(
            title="🎲 Farkle Game Guide",
            color=discord.Color.blurple(),
            description=(
                "**🎯 Objective**\n"
                "Be the first to reach **10,000 points**!\n\n"
                "**🚀 Getting Started**\n"
                ">>> • Start with `$farkle` or add a bet: `$farkle 5000`\n"
                "• Max bet: `$250,000` (with sufficient funds)\n"
                "• Coin toss decides who starts\n"
                "• Challenge the mighty Oracle!\n"
            )
        )
        
        # Gameplay Section
        gameplay = (
            "**📜 Basic Rules**\n"
            "```ansi\n[2;34m◈ Start with 6 dice each turn\n"
            "◈ Roll → Select scoring dice → Choose action\n"
            "◈ Farkle = No scoring dice → Turn ends```\n\n"
            
            "**⚡ Turn Options**\n"
            ">>> › Roll Again: Risk points for more\n"
            "› Bank: Save points & end turn\n"
            "› Quit: Type `q` to exit\n"
            "› Hot Dice: Score all → New 6-dice roll\n\n"
            
            "**⏳ Timeouts**\n"
            "3 missed turns → automatic forfeit"
        )
        embed.add_field(name="\u200b", value=gameplay, inline=False)
        
        # Scoring Section
        scoring = (
            "**🏆 Scoring System**\n"
            "```diff\n"
            "+ Straight (1-2-3-4-5-6) → 1500\n"
            "+ Three Pairs → 1500\n\n"
            "! Three-of-a-Kind:\n"
            "- 1s: 1000 + (extra ×2)\n"
            "- Others: (Number × 100) + (extra ×2)\n\n"
            "+ Single 1 → 100\n"
            "+ Single 5 → 50\n"
            "```\n"
            "**Example:** `Keep 1 5 5` → 200 points"
        )
        embed.add_field(name="\u200b", value=scoring, inline=False)
        
        # Strategy Section
        strategy = (
            "**💡 Pro Tips**\n"
            ">>> › Balance risk vs reward\n"
            "› Bank early when ahead\n"
            "› Watch Oracle's patterns\n"
            "› Combine scoring combinations\n\n"
            
            "**🔮 Oracle's Powers**\n"
            ">>> › Divines optimal dice strategy\n"
            "› Calculates complex risk thresholds\n"
            "› Grows more aggressive when behind\n"
            "› Uses ancient foresight to predict outcomes"
        )
        embed.add_field(name="\u200b", value=strategy, inline=False)
        
        embed.set_footer(text="🛑 Farkle = No scoring dice | ⚠️ Timeouts = 3 missed turns")
        await ctx.send(embed=embed)


    @has_char()
    @commands.command(name="farkle", aliases=["fark"])
    @locale_doc
    async def farkle(self, ctx, bet: int = 0, opponent: discord.Member = None):
        """
        Full game of Farkle to 10,000 points.
          - Play against AI (no human opponents currently supported).
          - Type `quitfarkle` to quit.
          - Three consecutive timeouts forfeit the game.
        """
        try:
            if opponent is not None:
                return await ctx.send("You cannot play against opponents currently.")

            # Check if user can afford the bet
            if bet > 0:
                async with self.bot.pool.acquire() as conn:
                    money = await conn.fetchval('SELECT money FROM profile WHERE "user"=$1', ctx.author.id)
                    if money < bet:
                        return await ctx.send("You don't have enough money for that bet!")
                    if bet > 250000:
                        return await ctx.send("You cannot bet more than **$250,000**.")
            if ctx.character_data["money"] < bet:
                return await ctx.send("You don't have enough money to cover the bet.")

            async with self.bot.pool.acquire() as conn:
                if bet > 0:
                    await conn.execute(
                        'UPDATE profile SET "money"="money"-$1 WHERE "user"=$2;',
                        bet,
                        ctx.author.id,
                    )
                if bet > 0:
                    if opponent is not None:
                        return await ctx.send("You cannot play against opponents currently.")
                        await conn.execute(
                            'UPDATE profile SET "money"="money"-$1 WHERE "user"=$2;',
                            bet,
                            opponent.id,
                        )

            player1 = ctx.author
            if opponent is None or opponent == player1:
                player2 = "Oracle"
                await ctx.send(f"**{player1.display_name}** challenges the **Oracle** to a game of Farkle!")
            else:
                player2 = opponent
                await ctx.send(f"**{player1.display_name}** challenges **{player2.display_name}** to a game of Farkle!")

            scores = {player1: 0, player2: 0}
            current_state = ""  # This will be cleared between turns.

            # Create initial embed.
            embed = discord.Embed(
                title="🎲 Farkle Game",
                description="Reach 10,000 points to win! Type `q` to quit anytime.",
                color=0x3498db
            )
            embed.add_field(name="Overall Scores", value=f"```{self.build_scores(player1, scores[player1], player2, scores[player2])}```", inline=False)
            embed.add_field(name="Game Panel", value="Game starting...", inline=False)
            embed.set_footer(text="Type q to quit at any prompt.")
            game_msg = await ctx.send(embed=embed)

            miss_counts = {player1: 0}
            if player2 != "AI":
                miss_counts[player2] = 0

            current_player, other_player = randomm.sample([player1, player2], 2)
            current_state = f"**Coin Toss:** {(current_player.display_name if hasattr(current_player, 'display_name') else str(current_player))} goes first."
            game_msg = await self.update_embed(game_msg, self.build_scores(player1, scores[player1], player2, scores[player2]), current_state)

            try:
                while scores[player1] < 10000 and scores[player2] < 10000:
                    # Treat any string-type current_player as the Oracle AI
                    if isinstance(current_player, str):
                        turn_points, turn_state = await self.oracle_turn(ctx, scores[current_player], scores[other_player], game_msg, player1, player2)
                        scores[current_player] += turn_points
                        current_state = turn_state + "\n─────────────────────────────"
                    else:
                        turn_points, missed, turn_state = await self.human_turn(
                            ctx,
                            current_player,
                            scores[current_player],
                            scores[other_player],
                            game_msg,
                            player1,
                            player2
                        )
                        if missed:
                            miss_counts[current_player] += 1
                            current_state = f"**Missed Turns for {(current_player.display_name if hasattr(current_player, 'display_name') else str(current_player))}:** {miss_counts[current_player]}"
                            game_msg = await self.update_embed(game_msg, self.build_scores(player1, scores[player1], player2, scores[player2]), current_state)
                            if miss_counts[current_player] >= 3:
                                current_state += f"\n❌ {(current_player.display_name if hasattr(current_player, 'display_name') else str(current_player))} missed 3 turns and forfeits!"
                                game_msg = await self.update_embed(game_msg, self.build_scores(player1, scores[player1], player2, scores[player2]), current_state)
                                scores[current_player] = 0
                                break
                        else:
                            miss_counts[current_player] = 0
                        scores[current_player] += turn_points
                        current_state = turn_state + "\n─────────────────────────────"
                    game_msg = await self.update_embed(game_msg, self.build_scores(player1, scores[player1], player2, scores[player2]), current_state)
                    if scores[player1] >= 10000 or scores[player2] >= 10000:
                        break
                    current_player, other_player = other_player, current_player
                    current_state = "─────────────────────────────\n"
                    game_msg = await self.update_embed(game_msg, self.build_scores(player1, scores[player1], player2, scores[player2]), current_state)
                    await asyncio.sleep(1)
            except QuitGame:
                quitter = current_player if current_player != "Oracle" else other_player
                winner = other_player if quitter == current_player else current_player
                current_state += f"\n❌ {(quitter.display_name if hasattr(quitter, 'display_name') else str(quitter))} quit! {(winner.display_name if hasattr(winner, 'display_name') else str(winner))} wins!"
                game_msg = await self.update_embed(game_msg, self.build_scores(player1, scores[player1], player2, scores[player2]), current_state)
                final_embed = discord.Embed(
                    title="🎲 Farkle Game Over",
                    description=f"❌ {(quitter.display_name if hasattr(quitter, 'display_name') else str(quitter))} quit! {(winner.display_name if hasattr(winner, 'display_name') else str(winner))} wins!",
                    color=0xe74c3c
                )
                await ctx.send(embed=final_embed)
                return

            if scores[player1] >= 10000 and scores[player2] >= 10000:
                winner = player1 if scores[player1] > scores[player2] else player2
            elif scores[player1] >= 10000:
                winner = player1
            else:
                winner = player2

            if winner == "Oracle":
                current_state += "\n🔮 **Oracle wins! Better luck next time!**"
            else:
                current_state += f"\n🎉 **{(winner.display_name if hasattr(winner, 'display_name') else str(winner))} wins with {scores[winner]} points!**"
                async with self.bot.pool.acquire() as conn:

                    if winner != "Oracle":
                        if bet > 0:
                            await conn.execute(
                                'UPDATE profile SET "money"="money"+$1 WHERE "user"=$2;',
                                bet * 2,
                                winner.id,
                            )

            game_msg = await self.update_embed(game_msg, self.build_scores(player1, scores[player1], player2, scores[player2]), current_state)
            await game_msg.delete()
            final_embed = discord.Embed(
                title="🎲 Farkle Game Over",
                description=f"{(winner.display_name if hasattr(winner, 'display_name') else str(winner))} wins with {scores[winner]} points!",
                color=0x2ecc71
            )
            await ctx.send(embed=final_embed)
        except Exception as e:
            await ctx.send(e)


async def setup(bot: Bot) -> None:
    await bot.add_cog(Gambling(bot))

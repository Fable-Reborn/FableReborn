
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
from __future__ import annotations

import asyncio
import json
import random
import re
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Optional

import discord
from discord.ext import commands
from discord.ui import Button, View

from utils.checks import is_gm

CARDS_DIR = Path(__file__).parent
WHITE_FILE = CARDS_DIR / "cah_white.txt"
BLACK_FILE = CARDS_DIR / "cah_black.txt"
SETTINGS_FILE = CARDS_DIR / "cah_settings.json"

PICK_RE = re.compile(r"\b[Pp]ick\s*(\d)\b")
BLANK_RE = re.compile(r"_+")
BLANK_TOKEN = "────"
ALLOWED_USER_MENTIONS = discord.AllowedMentions(users=True)
PHASE_LABELS = {
    "idle": "Idle",
    "lobby": "Lobby Open",
    "submitting": "Submissions",
    "judging": "Judging",
    "ended": "Show Ended",
}


@dataclass
class GameSettings:
    hand_size: int = 7
    points_to_win: int = 10
    min_players: int = 3
    lobby_timeout: int = 120
    play_timeout: int = 120
    judge_timeout: int = 90
    max_skips: int = 2
    auto_pick_on_timeout: bool = True
    allow_late_join: bool = False


@dataclass
class GameState:
    guild_id: int
    channel_id: int
    host_id: int
    settings: GameSettings
    players: dict[int, discord.Member] = field(default_factory=dict)
    turn_order: list[int] = field(default_factory=list)
    judge_index: int = 0
    hands: dict[int, list[str]] = field(default_factory=dict)
    scores: dict[int, int] = field(default_factory=dict)
    skips: dict[int, int] = field(default_factory=dict)
    submissions: dict[int, list[str]] = field(default_factory=dict)
    white_deck: list[str] = field(default_factory=list)
    black_deck: list[str] = field(default_factory=list)
    white_discard: list[str] = field(default_factory=list)
    black_discard: list[str] = field(default_factory=list)
    current_black: str = ""
    pick_count: int = 1
    lobby_open: bool = False
    active: bool = False
    phase: str = "idle"
    round_token: int = 0
    round_event: asyncio.Event = field(default_factory=asyncio.Event, repr=False)
    judge_event: asyncio.Event = field(default_factory=asyncio.Event, repr=False)
    judge_choice: Optional[int] = None
    lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False)


def read_card_file(path: Path) -> list[str]:
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8", errors="ignore")
    cards: list[str] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("#"):
            continue
        cards.append(line)
    return cards


def black_likeness(cards: list[str]) -> float:
    if not cards:
        return 0.0
    hits = 0
    for card in cards:
        if "_" in card:
            hits += 1
            continue
        if PICK_RE.search(card):
            hits += 1
    return hits / len(cards)


def infer_pick_count(black_card: str) -> int:
    blanks = black_card.count("_")
    if blanks > 0:
        return blanks
    match = PICK_RE.search(black_card)
    if match:
        try:
            return max(1, int(match.group(1)))
        except ValueError:
            return 1
    return 1


def render_submission(black_card: str, cards: list[str]) -> str:
    if "_" in black_card:
        text = black_card
        for card in cards:
            text = text.replace("_", f"**{card}**", 1)
        return text
    if len(cards) == 1:
        return f"{black_card} **{cards[0]}**"
    joined = "\n".join(f"- **{card}**" for card in cards)
    return f"{black_card}\n{joined}"


def format_black_card_display(black_card: str) -> str:
    if "_" not in black_card:
        return black_card
    return BLANK_RE.sub(BLANK_TOKEN, black_card)


def format_seconds(seconds: int) -> str:
    if seconds < 60:
        return f"{seconds}s"
    minutes = seconds // 60
    remainder = seconds % 60
    if remainder == 0:
        return f"{minutes}m"
    return f"{minutes}m {remainder}s"


def format_phase(phase: str) -> str:
    return PHASE_LABELS.get(phase, phase.replace("_", " ").title())


class CardButton(Button):
    def __init__(self, index: int, card_text: str):
        super().__init__(style=discord.ButtonStyle.primary, label=str(index))
        self.card_text = card_text

    async def callback(self, interaction: discord.Interaction):
        await self.view.handle_selection(interaction, self)


class CardSelectView(View):
    def __init__(self, cog, guild_id: int, channel_id: int, player_id: int, round_token: int,
                 hand: list[str], pick_count: int, timeout: int):
        super().__init__(timeout=timeout)
        self.cog = cog
        self.guild_id = guild_id
        self.channel_id = channel_id
        self.player_id = player_id
        self.round_token = round_token
        self.pick_count = pick_count
        self.selected: list[str] = []
        self.message: Optional[discord.Message] = None
        for index, card in enumerate(hand, 1):
            self.add_item(CardButton(index, card))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.player_id:
            await interaction.response.send_message("This is not your hand.", ephemeral=True)
            return False
        return True

    async def handle_selection(self, interaction: discord.Interaction, button: CardButton):
        game = self.cog.games.get(self.guild_id)
        if not game or not game.active or game.phase != "submitting":
            await interaction.response.send_message("That round is already over.", ephemeral=True)
            return
        if game.round_token != self.round_token:
            await interaction.response.send_message("That round is already over.", ephemeral=True)
            return

        async with game.lock:
            hand = game.hands.get(self.player_id, [])
            if button.card_text not in hand:
                await interaction.response.send_message("That card is no longer in your hand.", ephemeral=True)
                return

            submission = game.submissions.setdefault(self.player_id, [])
            if len(submission) >= game.pick_count:
                await interaction.response.send_message("You already submitted your cards.", ephemeral=True)
                return

            submission.append(button.card_text)
            hand.remove(button.card_text)
            self.selected.append(button.card_text)

            button.disabled = True
            if len(submission) >= game.pick_count:
                for item in self.children:
                    item.disabled = True

        await interaction.response.edit_message(view=self)

        links: list[str] = []
        if self.message:
            links.append(f"[Open hand]({self.message.jump_url})")
        if self.channel_id:
            game_link = f"https://discord.com/channels/{self.guild_id}/{self.channel_id}"
            links.append(f"[Back to stage]({game_link})")
        link_text = f"\n{' | '.join(links)}" if links else ""

        if len(self.selected) >= self.pick_count:
            await interaction.followup.send(
                f"Locked in ({len(self.selected)}/{self.pick_count}).{link_text}",
                ephemeral=True,
            )
            if self.cog.all_players_submitted(game):
                game.round_event.set()
        else:
            await interaction.followup.send(
                f"Selection saved ({len(self.selected)}/{self.pick_count}).{link_text}",
                ephemeral=True,
            )

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                pass


class LobbyJoinButton(Button):
    def __init__(self):
        super().__init__(style=discord.ButtonStyle.success, label="Join Show")

    async def callback(self, interaction: discord.Interaction):
        await self.view.handle_join(interaction, self)


class LobbyLeaveButton(Button):
    def __init__(self):
        super().__init__(style=discord.ButtonStyle.danger, label="Leave Show")

    async def callback(self, interaction: discord.Interaction):
        await self.view.handle_leave(interaction, self)


class LobbyView(View):
    def __init__(self, cog, guild_id: int, timeout: int):
        super().__init__(timeout=timeout)
        self.cog = cog
        self.guild_id = guild_id
        self.message: Optional[discord.Message] = None
        self.add_item(LobbyJoinButton())
        self.add_item(LobbyLeaveButton())

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.guild is None:
            await interaction.response.send_message("The show can only be used in a server.", ephemeral=True)
            return False
        if interaction.guild.id != self.guild_id:
            await interaction.response.send_message("That lobby is for a different server.", ephemeral=True)
            return False
        return True

    async def handle_join(self, interaction: discord.Interaction, _: Button):
        await self.cog.handle_lobby_join(interaction)
        await self.refresh()

    async def handle_leave(self, interaction: discord.Interaction, _: Button):
        await self.cog.handle_lobby_leave(interaction)
        await self.refresh()

    async def refresh(self):
        game = self.cog.games.get(self.guild_id)
        if not game or not game.lobby_open or not self.message:
            return
        try:
            await self.message.edit(embed=self.cog.build_lobby_embed(game), view=self)
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            pass

    async def disable(self):
        for item in self.children:
            item.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                pass

    async def on_timeout(self):
        await self.disable()


class JudgeButton(Button):
    def __init__(self, index: int):
        super().__init__(style=discord.ButtonStyle.danger, label=f"Play {index}")
        self.index = index

    async def callback(self, interaction: discord.Interaction):
        await self.view.handle_choice(interaction, self.index)


class JudgeSelectView(View):
    def __init__(self, cog, guild_id: int, judge_id: int, round_token: int, choices: int, timeout: int):
        super().__init__(timeout=timeout)
        self.cog = cog
        self.guild_id = guild_id
        self.judge_id = judge_id
        self.round_token = round_token
        self.message: Optional[discord.Message] = None
        for index in range(1, choices + 1):
            self.add_item(JudgeButton(index))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.judge_id:
            await interaction.response.send_message("Only the judge can pick a winner.", ephemeral=True)
            return False
        return True

    async def handle_choice(self, interaction: discord.Interaction, index: int):
        game = self.cog.games.get(self.guild_id)
        if not game or not game.active or game.phase != "judging":
            await interaction.response.send_message("That round is already over.", ephemeral=True)
            return
        if game.round_token != self.round_token:
            await interaction.response.send_message("That round is already over.", ephemeral=True)
            return

        async with game.lock:
            if game.judge_choice is not None:
                await interaction.response.send_message("A winner was already picked.", ephemeral=True)
                return
            game.judge_choice = index - 1
            game.judge_event.set()
            for item in self.children:
                item.disabled = True

        await interaction.response.edit_message(view=self)

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                pass


class CardsAgainstHumanity(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.games: dict[int, GameState] = {}
        self.global_settings = self.load_settings()

    def get_settings(self) -> GameSettings:
        return self.global_settings

    def load_settings(self) -> GameSettings:
        if not SETTINGS_FILE.exists():
            return GameSettings()
        try:
            payload = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return GameSettings()
        return GameSettings(**payload)

    def save_settings(self):
        SETTINGS_FILE.write_text(
            json.dumps(asdict(self.global_settings), indent=2, sort_keys=True),
            encoding="utf-8",
        )

    def build_lobby_embed(self, game: GameState) -> discord.Embed:
        settings = game.settings
        embed = discord.Embed(title="Studio Lobby", color=0x1ABC9C)
        embed.description = (
            "Welcome to the CAH Game Show!\n"
            "Click **Join Show** to get on stage or **Leave Show** to step out.\n"
            f"Showtime in **{format_seconds(settings.lobby_timeout)}**."
        )
        embed.add_field(
            name="Contestants",
            value=f"{len(game.turn_order)} / {settings.min_players} minimum",
            inline=True,
        )
        embed.add_field(
            name="Win Condition",
            value=f"First to {settings.points_to_win} points",
            inline=True,
        )
        embed.add_field(
            name="Hand Size",
            value=f"{settings.hand_size} cards",
            inline=True,
        )
        embed.add_field(
            name="Timers",
            value=(
                f"Play {format_seconds(settings.play_timeout)} | "
                f"Judge {format_seconds(settings.judge_timeout)}"
            ),
            inline=False,
        )
        embed.set_footer(text="DMs must be enabled to play. Your hand is sent privately.")
        return embed

    async def process_join(self, game: GameState, member: discord.Member) -> tuple[str, Optional[str]]:
        added = await self.add_player(game, member)
        if not added:
            return ("I couldn't DM you. Please enable DMs to play.", None)

        if game.lobby_open:
            return ("You're on the contestant list!", f"{member.mention} entered the studio!")

        if game.white_deck:
            self.deal_hand_to_player(game, member.id)
        if game.phase == "submitting":
            await self.send_hand_to_player(game, member.id)
            return (
                "You're in for this round. Check your DMs to play!",
                f"{member.mention} joined late - on stage this round!",
            )
        return ("You're in for the next round.", f"{member.mention} joined late and will play next round.")

    async def process_leave(self, game: GameState, member: discord.Member) -> tuple[str, Optional[str]]:
        self.remove_player(game, member.id)
        public_message = f"{member.mention} left the studio."

        if member.id == game.host_id:
            await self.end_game(game, "Show ended: host left the stage.")
            return ("You left the show.", public_message)

        if len(game.turn_order) < game.settings.min_players:
            await self.end_game(game, "Show ended: not enough contestants.")
            return ("You left the show.", public_message)

        return ("You left the show.", public_message)

    async def handle_lobby_join(self, interaction: discord.Interaction):
        if interaction.guild is None:
            await interaction.response.send_message("The show can only be used in a server.", ephemeral=True)
            return
        game = self.games.get(interaction.guild.id)
        if game is None or not game.active:
            await interaction.response.send_message("There is no active studio lobby.", ephemeral=True)
            return
        if not game.lobby_open and not game.settings.allow_late_join:
            await interaction.response.send_message("Studio doors are closed.", ephemeral=True)
            return
        if interaction.user.id in game.players:
            await interaction.response.send_message("You're already on the contestant list.", ephemeral=True)
            return

        user_message, public_message = await self.process_join(game, interaction.user)
        await interaction.response.send_message(user_message, ephemeral=True)
        if public_message and interaction.channel:
            await interaction.channel.send(public_message, allowed_mentions=ALLOWED_USER_MENTIONS)

    async def handle_lobby_leave(self, interaction: discord.Interaction):
        if interaction.guild is None:
            await interaction.response.send_message("The show can only be used in a server.", ephemeral=True)
            return
        game = self.games.get(interaction.guild.id)
        if game is None or not game.active:
            await interaction.response.send_message("There is no active show.", ephemeral=True)
            return
        if not game.lobby_open:
            await interaction.response.send_message(
                "Studio doors are closed. Use `cah leave` during an active show.",
                ephemeral=True,
            )
            return
        if interaction.user.id not in game.players:
            await interaction.response.send_message("You're not on the contestant list.", ephemeral=True)
            return

        user_message, public_message = await self.process_leave(game, interaction.user)
        await interaction.response.send_message(user_message, ephemeral=True)
        if public_message and interaction.channel:
            await interaction.channel.send(public_message, allowed_mentions=ALLOWED_USER_MENTIONS)

    async def get_channel(self, game: GameState) -> Optional[discord.TextChannel]:
        channel = self.bot.get_channel(game.channel_id)
        if channel is None:
            try:
                channel = await self.bot.fetch_channel(game.channel_id)
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                return None
        return channel

    async def get_member(self, game: GameState, user_id: int) -> Optional[discord.Member]:
        guild = self.bot.get_guild(game.guild_id)
        if guild is None:
            return None
        return guild.get_member(user_id)

    def all_players_submitted(self, game: GameState) -> bool:
        for player_id in game.turn_order:
            if player_id == self.current_judge_id(game):
                continue
            submission = game.submissions.get(player_id, [])
            if len(submission) < game.pick_count:
                return False
        return True

    def current_judge_id(self, game: GameState) -> Optional[int]:
        if not game.turn_order:
            return None
        return game.turn_order[game.judge_index]

    def draw_white(self, game: GameState) -> Optional[str]:
        if not game.white_deck:
            if game.white_discard:
                random.shuffle(game.white_discard)
                game.white_deck.extend(game.white_discard)
                game.white_discard.clear()
        if not game.white_deck:
            return None
        return game.white_deck.pop()

    def draw_black(self, game: GameState) -> Optional[str]:
        if not game.black_deck:
            if game.black_discard:
                random.shuffle(game.black_discard)
                game.black_deck.extend(game.black_discard)
                game.black_discard.clear()
        if not game.black_deck:
            return None
        return game.black_deck.pop()

    def remove_player(self, game: GameState, user_id: int):
        if user_id in game.players:
            del game.players[user_id]
        if user_id in game.hands:
            del game.hands[user_id]
        if user_id in game.scores:
            del game.scores[user_id]
        if user_id in game.skips:
            del game.skips[user_id]
        if user_id in game.submissions:
            del game.submissions[user_id]

        if user_id in game.turn_order:
            idx = game.turn_order.index(user_id)
            game.turn_order.remove(user_id)
            if game.turn_order:
                if idx < game.judge_index:
                    game.judge_index -= 1
                elif idx == game.judge_index:
                    game.judge_index %= len(game.turn_order)
            else:
                game.judge_index = 0

    async def add_player(self, game: GameState, member: discord.Member) -> bool:
        if member.bot:
            return False
        if member.id in game.players:
            return True
        try:
            await member.send("You're on the show! We'll DM your hand each round.")
        except (discord.Forbidden, discord.HTTPException):
            channel = await self.get_channel(game)
            if channel:
                await channel.send(
                    f"{member.mention} I couldn't DM you. Please enable DMs to play.",
                    allowed_mentions=ALLOWED_USER_MENTIONS,
                )
            return False

        game.players[member.id] = member
        game.turn_order.append(member.id)
        game.hands[member.id] = []
        game.scores[member.id] = 0
        return True

    def build_hand_embed(self, member: discord.Member, hand: list[str], pick_count: int) -> discord.Embed:
        embed = discord.Embed(
            title="Contestant Hand",
            description="\n".join(f"**{i}.** {card}" for i, card in enumerate(hand, 1)) or "(empty)",
            color=0x3498DB,
        )
        embed.set_footer(text=f"Pick {pick_count} card(s) and lock them in.")
        if member.avatar:
            embed.set_thumbnail(url=member.avatar.url)
        return embed

    def build_black_embed(self, black_card: str, pick_count: int) -> discord.Embed:
        embed = discord.Embed(title="Round Prompt", color=0x111111)
        embed.description = f"**{format_black_card_display(black_card)}**"
        embed.add_field(name="Pick", value=str(pick_count), inline=True)
        return embed

    def build_scores_embed(self, game: GameState) -> discord.Embed:
        embed = discord.Embed(title="Scoreboard", color=0x2ECC71)
        for player_id in game.turn_order:
            member = game.players.get(player_id)
            name = member.display_name if member else str(player_id)
            embed.add_field(name=name, value=str(game.scores.get(player_id, 0)), inline=False)
        return embed

    async def load_cards(self) -> tuple[list[str], list[str], bool]:
        white_cards = read_card_file(WHITE_FILE)
        black_cards = read_card_file(BLACK_FILE)

        swapped = False
        if black_likeness(white_cards) > black_likeness(black_cards):
            white_cards, black_cards = black_cards, white_cards
            swapped = True

        return white_cards, black_cards, swapped

    async def start_game(self, ctx: commands.Context, game: GameState):
        channel = await self.get_channel(game)
        if channel is None:
            await self.end_game(game, "Show ended: channel unavailable.")
            return

        white_cards, black_cards, swapped = await self.load_cards()
        if swapped:
            await channel.send("Note: Your card files looked swapped, so I corrected them on load.")

        if not white_cards or not black_cards:
            await channel.send("Card files are empty or missing. Please check `cah_white.txt` and `cah_black.txt`.")
            await self.end_game(game, "Show ended: card files missing.")
            return

        random.shuffle(white_cards)
        random.shuffle(black_cards)
        game.white_deck = white_cards
        game.black_deck = black_cards
        game.white_discard = []
        game.black_discard = []

        random.shuffle(game.turn_order)
        game.judge_index = 0

        await self.deal_initial_hands(game)

        judge_id = self.current_judge_id(game)
        if judge_id is None:
            await channel.send("Not enough contestants to start.")
            await self.end_game(game, "Show ended: not enough contestants.")
            return

        await channel.send(
            f"Showtime! First judge is <@{judge_id}>.",
            allowed_mentions=ALLOWED_USER_MENTIONS,
        )
        game.phase = "submitting"

        while game.active:
            await self.run_round(game)

    async def deal_initial_hands(self, game: GameState):
        for player_id in game.turn_order:
            self.deal_hand_to_player(game, player_id)

    def deal_hand_to_player(self, game: GameState, player_id: int):
        hand = game.hands[player_id]
        while len(hand) < game.settings.hand_size:
            card = self.draw_white(game)
            if card is None:
                break
            hand.append(card)

    async def send_hands(self, game: GameState):
        for player_id in game.turn_order:
            await self.send_hand_to_player(game, player_id)

    async def send_hand_to_player(self, game: GameState, player_id: int):
        if player_id == self.current_judge_id(game):
            return
        member = game.players.get(player_id)
        if member is None:
            return
        hand = game.hands.get(player_id, [])
        view = CardSelectView(
            self,
            game.guild_id,
            game.channel_id,
            player_id,
            game.round_token,
            hand,
            game.pick_count,
            timeout=game.settings.play_timeout,
        )
        try:
            embed = self.build_hand_embed(member, hand, game.pick_count)
            message = await member.send(embed=embed, view=view)
            view.message = message
        except (discord.Forbidden, discord.HTTPException):
            channel = await self.get_channel(game)
            if channel:
                await channel.send(
                    f"{member.mention} couldn't be DM'd and will be benched this round.",
                    allowed_mentions=ALLOWED_USER_MENTIONS,
                )
            game.skips[player_id] = game.skips.get(player_id, 0) + 1

    async def run_round(self, game: GameState):
        channel = await self.get_channel(game)
        if channel is None:
            await self.end_game(game, "Show ended: channel unavailable.")
            return

        async with game.lock:
            if not game.active:
                return
            game.phase = "submitting"
            game.round_token += 1
            game.submissions = {}
            game.round_event = asyncio.Event()
            game.judge_event = asyncio.Event()
            game.judge_choice = None

            black_card = self.draw_black(game)
            if black_card is None:
                await channel.send("No prompt cards left. Show over.")
                await self.end_game(game, "Show ended: no prompt cards left.")
                return
            game.current_black = black_card
            game.black_discard.append(black_card)
            game.pick_count = infer_pick_count(black_card)

        judge_id = self.current_judge_id(game)
        if judge_id is None:
            await channel.send("Not enough contestants to continue.")
            await self.end_game(game, "Show ended: not enough contestants.")
            return

        await channel.send(
            content=f"Judge: <@{judge_id}> | Pick {game.pick_count}",
            embed=self.build_black_embed(game.current_black, game.pick_count),
            allowed_mentions=ALLOWED_USER_MENTIONS,
        )
        await channel.send(
            f"Contestants, you have {format_seconds(game.settings.play_timeout)} to submit your cards."
        )

        await self.send_hands(game)

        try:
            await asyncio.wait_for(game.round_event.wait(), timeout=game.settings.play_timeout)
        except asyncio.TimeoutError:
            pass

        missing_players: list[int] = []
        valid_submissions: list[tuple[int, list[str]]] = []

        async with game.lock:
            for player_id in list(game.turn_order):
                if player_id == judge_id:
                    continue
                submission = game.submissions.get(player_id, [])
                if len(submission) < game.pick_count:
                    if submission:
                        game.hands[player_id].extend(submission)
                        game.submissions.pop(player_id, None)
                    missing_players.append(player_id)
                else:
                    valid_submissions.append((player_id, submission))

            if game.settings.max_skips > 0:
                for player_id in missing_players:
                    game.skips[player_id] = game.skips.get(player_id, 0) + 1
                    if game.skips[player_id] >= game.settings.max_skips:
                        member = game.players.get(player_id)
                        await channel.send(
                            f"{member.mention if member else player_id} was buzzed out for inactivity.",
                            allowed_mentions=ALLOWED_USER_MENTIONS,
                        )
                        self.remove_player(game, player_id)

        if len(game.turn_order) < game.settings.min_players:
            await channel.send("Not enough contestants remain. Show over.")
            await self.end_game(game, "Show ended: not enough contestants.")
            return

        if not valid_submissions:
            await channel.send("No valid submissions this round. Rotating the judge.")
            await self.rotate_judge(game)
            return

        await self.judging_phase(game, valid_submissions)

    async def judging_phase(self, game: GameState, submissions: list[tuple[int, list[str]]]):
        channel = await self.get_channel(game)
        if channel is None:
            await self.end_game(game, "Show ended: channel unavailable.")
            return

        random.shuffle(submissions)
        game.phase = "judging"

        embed = discord.Embed(title="Spotlight Plays", color=0xE6E6E6)
        embed.add_field(
            name="Prompt",
            value=f"**{format_black_card_display(game.current_black)}**",
            inline=False,
        )
        for index, (_, cards) in enumerate(submissions, 1):
            embed.add_field(
                name=f"Play {index}",
                value=render_submission(game.current_black, cards),
                inline=False,
            )

        view = JudgeSelectView(
            self,
            game.guild_id,
            self.current_judge_id(game),
            game.round_token,
            len(submissions),
            timeout=game.settings.judge_timeout,
        )
        message = await channel.send(embed=embed, view=view)
        view.message = message
        await channel.send(
            f"Judge <@{self.current_judge_id(game)}>, pick the winning play! "
            f"({format_seconds(game.settings.judge_timeout)})",
            allowed_mentions=ALLOWED_USER_MENTIONS,
        )

        try:
            await asyncio.wait_for(game.judge_event.wait(), timeout=game.settings.judge_timeout)
        except asyncio.TimeoutError:
            pass

        if game.judge_choice is None:
            if game.settings.auto_pick_on_timeout:
                game.judge_choice = random.randrange(len(submissions))
                await channel.send("Judge timed out - host picks a random winner.")
            else:
                await channel.send("Judge timed out - no point this round.")

        if game.judge_choice is not None:
            winner_id, winning_cards = submissions[game.judge_choice]
            game.scores[winner_id] = game.scores.get(winner_id, 0) + 1
            await channel.send(
                f"Spotlight Winner: <@{winner_id}>! {render_submission(game.current_black, winning_cards)}",
                allowed_mentions=ALLOWED_USER_MENTIONS,
            )
            await channel.send(embed=self.build_scores_embed(game))

        for _, cards in submissions:
            game.white_discard.extend(cards)

        await self.finish_round(game)

    async def finish_round(self, game: GameState):
        channel = await self.get_channel(game)
        if channel is None:
            await self.end_game(game, "Show ended: channel unavailable.")
            return

        for player_id in game.turn_order:
            hand = game.hands[player_id]
            while len(hand) < game.settings.hand_size:
                card = self.draw_white(game)
                if card is None:
                    break
                hand.append(card)

        winner = None
        for player_id, score in game.scores.items():
            if score >= game.settings.points_to_win:
                winner = player_id
                break

        if winner is not None:
            await channel.send(
                f"Show over! <@{winner}> wins with {game.scores[winner]} points.",
                allowed_mentions=ALLOWED_USER_MENTIONS,
            )
            await self.end_game(game, "Show ended: winner crowned.")
            return

        await self.rotate_judge(game)

    async def rotate_judge(self, game: GameState):
        if not game.turn_order:
            return
        game.judge_index = (game.judge_index + 1) % len(game.turn_order)
        channel = await self.get_channel(game)
        if channel:
            await channel.send(
                f"Next judge: <@{self.current_judge_id(game)}>. Step up.",
                allowed_mentions=ALLOWED_USER_MENTIONS,
            )

    async def end_game(self, game: GameState, reason: str):
        game.active = False
        game.phase = "ended"
        game.lobby_open = False
        game.round_event.set()
        game.judge_event.set()
        self.games.pop(game.guild_id, None)

        channel = await self.get_channel(game)
        if channel and reason:
            await channel.send(reason)

    @commands.group(invoke_without_command=True)
    async def cah(self, ctx: commands.Context):
        if ctx.guild is None:
            await ctx.send("The show can only be used in a server.")
            return
        settings = self.get_settings()
        embed = discord.Embed(title="CAH Game Show", color=0x1ABC9C)
        embed.description = "Start the show, then use the **Join Show/Leave Show** buttons to get on stage."
        embed.add_field(
            name="Lobby",
            value="`cah start` to open the studio\nUse **Join Show/Leave Show** buttons (or `cah join` / `cah leave`)",
            inline=False,
        )
        embed.add_field(
            name="Show Info",
            value="`cah status` | `cah scores`",
            inline=False,
        )
        embed.add_field(
            name="Controls",
            value="`cah settings`",
            inline=False,
        )
        embed.set_footer(
            text=(
                f"Hand {settings.hand_size} | Points to crown {settings.points_to_win} | "
                f"Min contestants {settings.min_players}"
            )
        )
        await ctx.send(embed=embed)

    @cah.command(name="start")
    async def cah_start(self, ctx: commands.Context):
        if ctx.guild is None:
            await ctx.send("The show can only be played in a server.")
            return
        if ctx.guild.id in self.games and self.games[ctx.guild.id].active:
            await ctx.send("The show is already running here.")
            return

        settings = replace(self.get_settings())
        game = GameState(
            guild_id=ctx.guild.id,
            channel_id=ctx.channel.id,
            host_id=ctx.author.id,
            settings=settings,
        )
        game.active = True
        game.phase = "lobby"
        game.lobby_open = True
        self.games[ctx.guild.id] = game

        host_added = await self.add_player(game, ctx.author)
        if not host_added:
            await ctx.send("You need DMs enabled to host the show.")
            await self.end_game(game, "Show ended: host has DMs disabled.")
            return

        lobby_view = LobbyView(self, ctx.guild.id, timeout=settings.lobby_timeout)
        lobby_message = await ctx.send(embed=self.build_lobby_embed(game), view=lobby_view)
        lobby_view.message = lobby_message

        await asyncio.sleep(settings.lobby_timeout)
        await lobby_view.disable()

        if not game.active:
            return
        game.lobby_open = False

        if len(game.turn_order) < settings.min_players:
            await ctx.send("Not enough contestants joined. Lobby closed.")
            await self.end_game(game, "Show ended: not enough contestants.")
            return

        await self.start_game(ctx, game)

    @cah.command(name="join")
    async def cah_join(self, ctx: commands.Context):
        if ctx.guild is None:
            await ctx.send("The show can only be used in a server.")
            return
        game = self.games.get(ctx.guild.id) if ctx.guild else None
        if game is None or not game.active:
            await ctx.send("There is no active studio lobby.")
            return
        if not game.lobby_open and not game.settings.allow_late_join:
            await ctx.send("Studio doors are closed.")
            return
        if ctx.author.id in game.players:
            await ctx.send("You're already on the contestant list.")
            return

        user_message, public_message = await self.process_join(game, ctx.author)
        if public_message:
            await ctx.send(public_message, allowed_mentions=ALLOWED_USER_MENTIONS)
        else:
            await ctx.send(user_message)

    @cah.command(name="leave")
    async def cah_leave(self, ctx: commands.Context):
        if ctx.guild is None:
            await ctx.send("The show can only be used in a server.")
            return
        game = self.games.get(ctx.guild.id) if ctx.guild else None
        if game is None or not game.active:
            await ctx.send("There is no active show.")
            return
        if ctx.author.id not in game.players:
            await ctx.send("You're not on the contestant list.")
            return

        user_message, public_message = await self.process_leave(game, ctx.author)
        if public_message:
            await ctx.send(public_message, allowed_mentions=ALLOWED_USER_MENTIONS)
        else:
            await ctx.send(user_message)

    @cah.command(name="status")
    async def cah_status(self, ctx: commands.Context):
        if ctx.guild is None:
            await ctx.send("The show can only be used in a server.")
            return
        game = self.games.get(ctx.guild.id) if ctx.guild else None
        if game is None or not game.active:
            await ctx.send("There is no active show.")
            return

        judge_id = self.current_judge_id(game)
        judge_member = game.players.get(judge_id) if judge_id else None
        judge_label = judge_member.display_name if judge_member else (f"User {judge_id}" if judge_id else "None")
        embed = discord.Embed(title="Show Status", color=0x95A5A6)
        embed.add_field(name="Segment", value=format_phase(game.phase), inline=False)
        embed.add_field(name="Judge", value=judge_label, inline=False)
        embed.add_field(name="Contestants", value=str(len(game.turn_order)), inline=False)
        embed.add_field(name="Points to Crown", value=str(game.settings.points_to_win), inline=False)
        await ctx.send(embed=embed)

    @cah.command(name="scores")
    async def cah_scores(self, ctx: commands.Context):
        if ctx.guild is None:
            await ctx.send("The show can only be used in a server.")
            return
        game = self.games.get(ctx.guild.id) if ctx.guild else None
        if game is None or not game.active:
            await ctx.send("There is no active show.")
            return
        await ctx.send(embed=self.build_scores_embed(game))

    @cah.command(name="settings")
    @is_gm()
    async def cah_settings(self, ctx: commands.Context):
        if ctx.guild is None:
            await ctx.send("The show can only be used in a server.")
            return
        settings = self.get_settings()
        embed = discord.Embed(title="Show Settings", color=0x9B59B6)
        embed.add_field(name="Hand size", value=str(settings.hand_size), inline=False)
        embed.add_field(name="Points to crown", value=str(settings.points_to_win), inline=False)
        embed.add_field(name="Min contestants", value=str(settings.min_players), inline=False)
        embed.add_field(name="Lobby timer", value=format_seconds(settings.lobby_timeout), inline=False)
        embed.add_field(name="Play timer", value=format_seconds(settings.play_timeout), inline=False)
        embed.add_field(name="Judge timer", value=format_seconds(settings.judge_timeout), inline=False)
        embed.add_field(name="Max skips", value=str(settings.max_skips), inline=False)
        embed.add_field(name="Auto pick", value=str(settings.auto_pick_on_timeout), inline=False)
        embed.add_field(name="Late join", value=str(settings.allow_late_join), inline=False)
        await ctx.send(embed=embed)

    @cah.command(name="set")
    @is_gm()
    async def cah_set(self, ctx: commands.Context, setting: str, value: str):
        if ctx.guild is None:
            await ctx.send("The show can only be used in a server.")
            return
        game = self.games.get(ctx.guild.id) if ctx.guild else None
        if game is not None and game.active and game.phase != "lobby":
            await ctx.send("Settings can only be changed when the show is off.")
            return

        settings = self.get_settings()
        setting = setting.lower()

        def parse_bool(val: str) -> Optional[bool]:
            if val.lower() in {"true", "yes", "on", "1"}:
                return True
            if val.lower() in {"false", "no", "off", "0"}:
                return False
            return None

        try:
            if setting == "hand_size":
                settings.hand_size = max(3, min(15, int(value)))
            elif setting == "points_to_win":
                settings.points_to_win = max(1, int(value))
            elif setting == "min_players":
                settings.min_players = max(2, int(value))
            elif setting == "lobby_timeout":
                settings.lobby_timeout = max(30, int(value))
            elif setting == "play_timeout":
                settings.play_timeout = max(30, int(value))
            elif setting == "judge_timeout":
                settings.judge_timeout = max(30, int(value))
            elif setting == "max_skips":
                settings.max_skips = max(0, int(value))
            elif setting == "auto_pick":
                parsed = parse_bool(value)
                if parsed is None:
                    await ctx.send("auto_pick must be true/false.")
                    return
                settings.auto_pick_on_timeout = parsed
            elif setting == "late_join":
                parsed = parse_bool(value)
                if parsed is None:
                    await ctx.send("late_join must be true/false.")
                    return
                settings.allow_late_join = parsed
            else:
                await ctx.send("Unknown setting. Try: hand_size, points_to_win, min_players, lobby_timeout, play_timeout, judge_timeout, max_skips, auto_pick, late_join")
                return
        except ValueError:
            await ctx.send("That setting requires a numeric value.")
            return

        await ctx.send(f"Setting `{setting}` updated.")
        self.save_settings()

    @cah.command(name="reset")
    @is_gm()
    async def cah_reset(self, ctx: commands.Context):
        if ctx.guild is None:
            await ctx.send("The show can only be used in a server.")
            return
        self.global_settings = GameSettings()
        self.save_settings()
        await ctx.send("Show settings reset to defaults.")

    @commands.command(name="cahjoin")
    async def cahjoin_legacy(self, ctx: commands.Context):
        await self.cah_join(ctx)

    @commands.command(name="cahleave")
    async def cahleave_legacy(self, ctx: commands.Context):
        await self.cah_leave(ctx)

    @commands.command(name="scores")
    async def scores_legacy(self, ctx: commands.Context):
        await self.cah_scores(ctx)

    @commands.command(name="cahinstructions")
    async def cahinstructions(self, ctx: commands.Context):
        embed = discord.Embed(title="How the Show Works", color=0xF1C40F)
        embed.add_field(
            name="Goal",
            value="First to the points-to-crown takes the prize. Each round, the judge picks the funniest play.",
            inline=False,
        )
        embed.add_field(
            name="Play",
            value="Contestants pick cards in DMs. The blanks on the prompt tell you how many to choose.",
            inline=False,
        )
        embed.add_field(
            name="Judge",
            value="The judge selects a winning play; that contestant scores a point. Then the judge rotates.",
            inline=False,
        )
        embed.add_field(
            name="Commands",
            value="`cah start`, use Join Show/Leave Show buttons, `cah settings`",
            inline=False,
        )
        await ctx.send(embed=embed)

    @is_gm()
    @commands.command(name="forceendcah")
    async def forceendcah(self, ctx: commands.Context):
        game = self.games.get(ctx.guild.id) if ctx.guild else None
        if game is None:
            await ctx.send("No show is running.")
            return
        await self.end_game(game, "Show ended by a GM.")


async def setup(bot):
    await bot.add_cog(CardsAgainstHumanity(bot))

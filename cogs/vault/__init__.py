"""
The IdleRPG Discord Bot
Copyright (C) 2018-2021 Diniboy and Gelbpunkt
Copyright (C) 2024 Lunar (discord itslunar.)

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
import random
import time
from dataclasses import dataclass
from typing import Optional

import discord
from discord.ext import commands
from discord.http import handle_message_parameters
from discord.ui import Button, Modal, TextInput, View

from utils.checks import is_gm
from utils.i18n import _, locale_doc

MAX_ROUNDS = 40  # Hard stop; the vault always dies long before this.
# Ceiling on a GM-generated pool, matching the prize cap on `$juggernaut`.
MAX_GM_PRIZE = 100_000_000


def money(amount: int) -> str:
    return f"${amount:,}"


def parse_prize(raw: str) -> tuple[Optional[int], Optional[str]]:
    """Read a prize pool typed into the GM modal.

    Returns (amount, error). Accepts thousands separators and a leading $ so a
    GM pasting "1,000,000" or "$250000" under time pressure isn't rejected.
    """
    cleaned = raw.strip().replace(",", "").replace("$", "").replace(" ", "")
    if not cleaned:
        return None, "Enter an amount."
    try:
        value = int(cleaned)
    except ValueError:
        return None, "That isn't a whole number."
    if value <= 0:
        return None, "The pool has to be more than nothing."
    if value > MAX_GM_PRIZE:
        return None, f"The largest pool you can generate is {money(MAX_GM_PRIZE)}."
    return value, None


@dataclass
class VaultSettings:
    join_timeout: int = 120
    min_players: int = 3
    max_players: int = 0
    allow_start_early: bool = True
    pick_timeout: int = 30
    solo_bonus_pct: int = 15
    drill_min_pct: int = 8
    drill_max_pct: int = 18
    surge_chance_pct: int = 30
    surge_mult_pct: int = 260
    vault_floor_pct: int = 55
    theme: str = "heist"


SETTING_LIMITS = {
    "join_timeout": (30, 600),
    "min_players": (2, 20),
    "max_players": (0, 50),
    "pick_timeout": (10, 120),
    "solo_bonus_pct": (0, 40),
    "drill_min_pct": (3, 30),
    "drill_max_pct": (5, 50),
    "surge_chance_pct": (0, 60),
    "surge_mult_pct": (100, 500),
    "vault_floor_pct": (20, 100),
}

# Deliberately excludes the prize pool. That is entered through a private modal
# so the amount never reaches the channel.
SETUP_TOKENS = {
    "timer": "pick_timeout",
    "pick": "pick_timeout",
    "join": "join_timeout",
    "lobby": "join_timeout",
    "min": "min_players",
    "max": "max_players",
    "solo": "solo_bonus_pct",
    "drillmin": "drill_min_pct",
    "drillmax": "drill_max_pct",
    "surge": "surge_chance_pct",
    "surgesize": "surge_mult_pct",
    "floor": "vault_floor_pct",
    "theme": "theme",
}

# Fraction of the original vault still remaining -> hint band. Players are told
# which band they are in, never the number, so judging the risk stays a feel
# rather than a calculation.
HINT_BANDS = [
    (0.70, "untouched"),
    (0.45, "dented"),
    (0.25, "thinning"),
    (0.12, "low"),
    (0.00, "empty"),
]


THEMES = {
    "heist": {
        "title": "The Vault",
        "colour": discord.Color.dark_gold(),
        "open": (
            "The drill is against the door and nobody knows how deep this vault goes."
        ),
        "drill": [
            "The drill bites.",
            "Another shelf comes free.",
            "The bit chews through another plate.",
        ],
        "surge": "**The bit punches clean through a whole rack.**",
        "walk": "**{player}** walks out with {amount}.",
        "solo": "**{player}** leaves alone and pockets an extra {bonus} on the way past.",
        "bust": [
            "The drill hits an empty shelf. The alarm goes off like a scream.",
            "Nothing behind the plate but air — and then sirens.",
            "The bit punches through into nothing. Every light in the building comes on.",
        ],
        "survive": "The crew that got out early counts its money and says nothing.",
        "winner": "**{winner}** walks away with {amount} and impeccable timing.",
        "hints": {
            "untouched": [
                "The stacks barely look touched.",
                "Shelves still packed to the back.",
            ],
            "dented": [
                "There's a visible gap in the stacks now.",
                "The shelves are looking uneven.",
            ],
            "thinning": [
                "The stacks are thinning.",
                "You're reaching further in each time.",
            ],
            "low": [
                "You can see metal at the back of the safe.",
                "Bare shelf showing through the last few bundles.",
            ],
            "empty": [
                "There's almost nothing left in here.",
                "You're scraping the floor of the vault.",
            ],
        },
    },
    "corporate": {
        "title": "The Discretionary Fund",
        "colour": discord.Color.blurple(),
        "open": (
            "Finance has opened a fund. Nobody will say how much is in it."
        ),
        "drill": [
            "A disbursement clears.",
            "Another tranche is released.",
            "Finance approves another draw.",
        ],
        "surge": "**An unusually large tranche clears all at once.**",
        "walk": "**{player}** takes the package and leaves with {amount}.",
        "solo": "**{player}** exits alone and negotiates an extra {bonus} on the way out.",
        "bust": [
            "The account is overdrawn. Every pending payment reverses at once.",
            "Audit arrives. Anything not yet paid out is clawed straight back.",
            "The fund is dry. Compliance reverses the lot.",
        ],
        "survive": "Those who took the early package are already updating their profiles.",
        "winner": "**{winner}** exits with {amount} and a glowing reference.",
        "hints": {
            "untouched": [
                "The fund looks barely drawn down.",
                "Finance isn't worried yet.",
            ],
            "dented": [
                "The balance has moved noticeably.",
                "Someone in Finance has started watching the account.",
            ],
            "thinning": [
                "Approvals are taking longer.",
                "The fund is visibly depleted.",
            ],
            "low": [
                "Finance has flagged the account.",
                "Requests are being questioned now.",
            ],
            "empty": [
                "There is almost nothing left to draw.",
                "The next request will not clear quietly.",
            ],
        },
    },
    "casino": {
        "title": "The Cage",
        "colour": discord.Color.dark_red(),
        "open": "The cage is open and the count is nobody's business but the house's.",
        "drill": [
            "Chips slide across the felt.",
            "The rack empties another row.",
            "Another tray comes out of the cage.",
        ],
        "surge": "**A whole rack goes out at once.**",
        "walk": "**{player}** colours up and cashes {amount}.",
        "solo": "**{player}** walks alone and the pit slides them an extra {bonus}.",
        "bust": [
            "The rack comes up empty. The pit boss puts a hand on the table.",
            "There's nothing left to pay with. Security closes the floor.",
            "The cage is dry. Every open bet is voided where it stands.",
        ],
        "survive": "The ones who cashed out early are already at the bar.",
        "winner": "**{winner}** leaves the floor with {amount} and a tip for the dealer.",
        "hints": {
            "untouched": ["The racks are still full.", "The cage looks deep."],
            "dented": [
                "A couple of rows are gone.",
                "The pit boss glances at the rack.",
            ],
            "thinning": [
                "The racks are noticeably lighter.",
                "They're restacking to hide the gaps.",
            ],
            "low": [
                "You can see the bottom of the tray.",
                "The pit boss has stopped smiling.",
            ],
            "empty": [
                "There's barely a stack left in the cage.",
                "The next payout might not cover.",
            ],
        },
    },
    "pirate": {
        "title": "The Hoard",
        "colour": discord.Color.dark_teal(),
        "open": "The chest is open and no soul aboard knows how deep it runs.",
        "drill": [
            "Another handful comes up from the chest.",
            "Gold is hauled out by the fistful.",
            "Another measure is dragged into the light.",
        ],
        "surge": "**A great heap comes up all at once.**",
        "walk": "**{player}** takes {amount} ashore and doesn't look back.",
        "solo": "**{player}** slips away alone with an extra {bonus} in their coat.",
        "bust": [
            "A hand closes on bare wood. The hold floods.",
            "Nothing left but splinters — and then the ship goes down.",
            "The chest is empty, and the crew turns on itself in the dark.",
        ],
        "survive": "Those who went ashore early are drinking to the ones who didn't.",
        "winner": "**{winner}** ends the voyage with {amount} and the sense to leave early.",
        "hints": {
            "untouched": ["The chest is near full.", "Gold to the brim yet."],
            "dented": [
                "The pile has sunk a little.",
                "You can see the sides of the chest now.",
            ],
            "thinning": [
                "You're reaching deeper each time.",
                "The chest is running shallow.",
            ],
            "low": ["Fingers are finding wood.", "Barely a layer left in there."],
            "empty": [
                "There's next to nothing in the chest.",
                "One more grasp and you'll find nothing at all.",
            ],
        },
    },
}

THEME_ALIASES = {
    "bank": "heist",
    "robbery": "heist",
    "office": "corporate",
    "hr": "corporate",
    "work": "corporate",
    "vegas": "casino",
    "chips": "casino",
    "cage": "casino",
    "sea": "pirate",
    "crew": "pirate",
    "ship": "pirate",
}


class VaultGame:
    def __init__(self, host_id: int, settings: VaultSettings):
        # The Game Master running the event. They set the pool, so they never
        # play — knowing the size would tell them roughly when it runs dry.
        self.host_id = host_id
        self.settings = settings
        self.participants: list[discord.User] = []
        self.joined_players: set[int] = set()
        self.join_lock = asyncio.Lock()

        self.lobby_open = True
        self.lobby_message: Optional[discord.Message] = None
        self.lobby_view: Optional[View] = None
        self.lobby_ends_at: Optional[float] = None
        self.started_early = False
        self.is_game_running = False

        # The generated prize pool, entered through a private modal and never
        # echoed to the channel: knowing it would tell players roughly how many
        # drills the vault can survive. Also the hard ceiling on payouts.
        self.pot: Optional[int] = None
        self.vault_total = 0
        self.vault_remaining = 0
        self.round = 0
        self.busted = False

        # Money taken but not yet safe. Lost entirely on a bust.
        self.hauls: dict[int, int] = {}
        # Money that has been walked out with. Safe.
        self.banked: dict[int, int] = {}
        self.inside: set[int] = set()
        # Explicit stay/walk choices for the current round.
        self.choices: dict[int, str] = {}
        self.history: list[str] = []

    @property
    def theme(self) -> dict:
        return THEMES.get(self.settings.theme, THEMES["heist"])

    def players_inside(self) -> list[discord.User]:
        return [p for p in self.participants if p.id in self.inside]

    def hint_band(self) -> str:
        if self.vault_total <= 0:
            return "empty"
        ratio = self.vault_remaining / self.vault_total
        for threshold, band in HINT_BANDS:
            if ratio >= threshold:
                return band
        return "empty"

    def hint_line(self) -> str:
        return random.choice(self.theme["hints"][self.hint_band()])


class PrizeModal(Modal):
    """Private prize entry. Only the GM ever sees this, or the number in it."""

    def __init__(self, view: "VaultJoinView"):
        super().__init__(title="Set the prize pool")
        self.join_view = view
        self.amount = TextInput(
            label="Amount to generate",
            placeholder="e.g. 250000 — players will never see this",
            required=True,
            max_length=15,
        )
        self.add_item(self.amount)

    async def on_submit(self, interaction: discord.Interaction):
        value, error = parse_prize(self.amount.value)
        if error:
            await interaction.response.send_message(error, ephemeral=True)
            return

        game = self.join_view.game
        game.pot = value
        await interaction.response.send_message(
            f"Prize pool set to **{money(value)}**.\n"
            "Nobody else can see this. Press it again to change it before the "
            "lobby closes.",
            ephemeral=True,
        )
        await self.join_view.cog.update_lobby_message(game)


class VaultJoinView(View):
    def __init__(self, cog: "Vault", game: VaultGame, host_id: int):
        super().__init__(timeout=game.settings.join_timeout)
        self.cog = cog
        self.game = game
        self.host_id = host_id
        self.message: Optional[discord.Message] = None

        join_button = Button(label="Join the Crew", style=discord.ButtonStyle.success)
        join_button.callback = self._handle_join
        self.add_item(join_button)

        prize_button = Button(
            label="Set Prize Pool",
            style=discord.ButtonStyle.secondary,
            emoji="\N{MONEY BAG}",
        )
        prize_button.callback = self._handle_prize
        self.add_item(prize_button)

        if game.settings.allow_start_early:
            start_button = Button(label="Start Early", style=discord.ButtonStyle.primary)
            start_button.callback = self._handle_start
            self.add_item(start_button)

    async def _handle_prize(self, interaction: discord.Interaction):
        if interaction.user is None:
            return
        if interaction.user.id != self.host_id:
            await interaction.response.send_message(
                "Only the Game Master running this can set the pool.", ephemeral=True
            )
            return
        await interaction.response.send_modal(PrizeModal(self))

    async def _handle_join(self, interaction: discord.Interaction):
        if interaction.user is None:
            return
        error = await self.cog.try_join_lobby(self.game, interaction.user)
        if error:
            await interaction.response.send_message(error, ephemeral=True)
            return
        await interaction.response.send_message(
            "You're in. Get out before it runs dry.", ephemeral=True
        )

    async def _handle_start(self, interaction: discord.Interaction):
        if interaction.user is None:
            return
        if interaction.user.id != self.host_id:
            await interaction.response.send_message(
                "Only the host can start early.", ephemeral=True
            )
            return
        if len(self.game.participants) < self.game.settings.min_players:
            await interaction.response.send_message(
                "Not enough players to start yet.", ephemeral=True
            )
            return
        if self.game.pot is None:
            await interaction.response.send_message(
                "Set the prize pool first.", ephemeral=True
            )
            return
        self.game.started_early = True
        self.game.lobby_open = False
        await interaction.response.send_message("Starting the job!", ephemeral=True)
        self.stop()

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        self.game.lobby_open = False
        if self.message:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass


class DecisionView(View):
    """Stay in for another drill, or walk out with your haul intact."""

    def __init__(self, game: VaultGame, timeout: int):
        super().__init__(timeout=timeout)
        self.game = game
        self.round_number = game.round
        self.closed = False

        stay = Button(label="Stay In", style=discord.ButtonStyle.danger)
        stay.callback = self._handle_stay
        self.add_item(stay)

        walk = Button(label="Walk Away", style=discord.ButtonStyle.success)
        walk.callback = self._handle_walk
        self.add_item(walk)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user is None:
            return False
        if interaction.user.id not in self.game.joined_players:
            await interaction.response.send_message(
                "You aren't in this game.", ephemeral=True
            )
            return False
        if interaction.user.id not in self.game.inside:
            await interaction.response.send_message(
                "You already walked out. Enjoy the show.", ephemeral=True
            )
            return False
        return True

    async def _record(self, interaction: discord.Interaction, choice: str) -> None:
        if self.closed or self.game.round != self.round_number:
            await interaction.response.send_message(
                "Too late — that round is already resolved.", ephemeral=True
            )
            return

        self.game.choices[interaction.user.id] = choice
        haul = self.game.hauls.get(interaction.user.id, 0)
        if choice == "stay":
            message = (
                f"You stay in. {money(haul)} still on the table.\n"
                "You can still change your mind before the timer ends."
            )
        else:
            message = (
                f"You're walking with {money(haul)}.\n"
                "You can still change your mind before the timer ends."
            )
        await interaction.response.send_message(message, ephemeral=True)

    async def _handle_stay(self, interaction: discord.Interaction):
        await self._record(interaction, "stay")

    async def _handle_walk(self, interaction: discord.Interaction):
        await self._record(interaction, "walk")


class Vault(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.games: dict[int, VaultGame] = {}

    # ------------------------------------------------------------------
    # Money helpers (mirrors the Russian Roulette cog so behaviour matches)
    # ------------------------------------------------------------------
    async def has_profile(self, user_id: int) -> bool:
        """Winnings are paid with an UPDATE on `profile`, which silently does
        nothing for a user without one. Check at the door instead of letting
        someone play a whole game they could never be paid for."""
        async with self.bot.pool.acquire() as conn:
            row = await conn.fetchrow(
                'SELECT 1 FROM profile WHERE "user"=$1;', user_id
            )
        return row is not None

    async def pay_out(self, payouts: dict[int, int]) -> None:
        records = [(amount, user_id) for user_id, amount in payouts.items() if amount > 0]
        if not records:
            return
        async with self.bot.pool.acquire() as conn:
            await conn.executemany(
                'UPDATE profile SET "money"="money"+$1 WHERE "user"=$2;',
                records,
            )

    async def gm_log(self, content: str) -> None:
        """Post to the GM log channel. Best-effort — logging must never break or
        delay a running game, and the channel may not be configured. The pool is
        generated currency, so the channel doubles as the audit trail for it.
        Sent over the raw HTTP route (like the game_master cog) so it works even
        when the channel isn't in the bot's cache."""
        channel_id = getattr(self.bot.config.game, "gm_log_channel", None)
        if not channel_id:
            return
        try:
            with handle_message_parameters(content=content) as params:
                await self.bot.http.send_message(channel_id, params=params)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Setup parsing
    # ------------------------------------------------------------------
    def parse_setup(self, tokens: tuple[str, ...]) -> tuple[VaultSettings, list[str]]:
        settings = VaultSettings()
        problems: list[str] = []

        for token in tokens:
            if "=" not in token:
                problems.append(f"Ignored `{token}` — use `name=value`.")
                continue
            raw_key, _sep, raw_value = token.partition("=")
            key = SETUP_TOKENS.get(raw_key.strip().lower())
            if key is None:
                problems.append(f"Ignored `{raw_key}` — not a known option.")
                continue

            value = raw_value.strip().lower()
            if key == "theme":
                theme = THEME_ALIASES.get(value, value)
                if theme not in THEMES:
                    problems.append(
                        f"Unknown theme `{value}`. Options: {', '.join(THEMES)}."
                    )
                    continue
                settings.theme = theme
                continue

            try:
                number = int(value)
            except ValueError:
                problems.append(f"`{raw_key}` needs a whole number.")
                continue

            low, high = SETTING_LIMITS[key]
            if not low <= number <= high:
                problems.append(f"`{raw_key}` must be between {low} and {high}.")
                continue
            setattr(settings, key, number)

        if settings.max_players and settings.max_players < settings.min_players:
            problems.append("`max` was below `min`, so the cap was dropped.")
            settings.max_players = 0
        if settings.drill_max_pct < settings.drill_min_pct:
            problems.append("`drillmax` was below `drillmin`, so both were levelled.")
            settings.drill_max_pct = settings.drill_min_pct

        return settings, problems

    # ------------------------------------------------------------------
    # Lobby
    # ------------------------------------------------------------------
    def _lobby_seconds_left(self, game: VaultGame) -> int:
        if game.lobby_ends_at is None:
            return game.settings.join_timeout
        return max(0, int(game.lobby_ends_at - time.monotonic()))

    def _players_text(self, game: VaultGame) -> str:
        if not game.participants:
            return "Nobody yet"
        preview_limit = 20
        preview = ", ".join(p.mention for p in game.participants[:preview_limit])
        extra = len(game.participants) - preview_limit
        if extra > 0:
            return f"{preview}, and {extra} more"
        return preview

    def build_lobby_embed(self, game: VaultGame) -> discord.Embed:
        theme = game.theme
        settings = game.settings
        seconds_left = self._lobby_seconds_left(game)
        minutes, seconds = divmod(seconds_left, 60)
        cap = f" / {settings.max_players}" if settings.max_players else ""

        embed = discord.Embed(
            title=f"{theme['title']} — Lobby",
            colour=theme["colour"],
            description=(
                # The rules card sits directly above this, so repeating it here
                # would only make the pair harder to read.
                "**Free to enter.** Press **Join the Crew** to get in — the rules "
                "are in the message above.\n\n"
                f"Lobby closes in **{minutes:02d}:{seconds:02d}**."
            ),
        )
        embed.add_field(
            name="Decision timer",
            value=f"**{settings.pick_timeout}s** each round",
            inline=True,
        )
        # Deliberately never the amount: knowing the pool would tell players
        # roughly how many drills the vault can survive.
        embed.add_field(
            name="Prize pool",
            value=(
                "\N{WHITE HEAVY CHECK MARK} **Set**"
                if game.pot is not None
                else "\N{HOURGLASS WITH FLOWING SAND} *Not set yet*"
            ),
            inline=True,
        )
        embed.add_field(
            name=f"Joined ({len(game.participants)}{cap})",
            value=self._players_text(game),
            inline=False,
        )
        footer = f"Minimum {settings.min_players} players."
        if settings.allow_start_early:
            footer += " The Game Master can start early."
        if game.pot is None:
            footer = "Game Master: press Set Prize Pool before this lobby closes. " + footer
        embed.set_footer(text=footer)
        return embed

    def build_howto_embed(self, game: Optional[VaultGame] = None) -> discord.Embed:
        """The rules card. Kept deliberately plain — flavour belongs in the game,
        not in the one message a first-time player has to understand."""
        embed = discord.Embed(
            title="\N{BANK} The Vault — How to Play",
            colour=game.theme["colour"] if game else discord.Color.dark_gold(),
            description=(
                "**Take as much as you dare. Get out before it runs dry.**\n"
                "Nobody is told how much is in the vault."
            ),
        )
        embed.add_field(
            name="\N{MONEY BAG} Every round",
            value=(
                "The vault is drilled, and the money splits between everyone "
                "still inside.\nThat's your **haul** — and it is *not safe yet*."
            ),
            inline=False,
        )
        embed.add_field(
            name="\N{DOOR} Then you choose, privately",
            value=(
                "**Stay In** — you get a share of the next drill too.\n"
                "**Walk Away** — your haul is banked for good, and you're out."
            ),
            inline=False,
        )
        embed.add_field(
            name="\N{POLICE CARS REVOLVING LIGHT} The catch",
            value=(
                "You only ever get **hints** about how full it looks — never a number.\n"
                "When a drill finds the vault empty, **everyone still inside loses "
                "everything.**\nEveryone who already walked keeps every penny."
            ),
            inline=False,
        )
        embed.add_field(
            name="\N{DIRECT HIT} Leaving alone",
            value=(
                "If you're the **only** one to walk in a round, you take a bonus cut "
                "on the way out — straight out of the vault, making it more dangerous "
                "for everyone you left behind."
            ),
            inline=False,
        )
        embed.set_footer(text="Most money banked wins. No answer walks you out safely.")
        return embed

    async def update_lobby_message(self, game: VaultGame) -> None:
        if game.lobby_message is None:
            return
        embed = self.build_lobby_embed(game)
        try:
            if game.lobby_view is not None:
                await game.lobby_message.edit(embed=embed, view=game.lobby_view)
            else:
                await game.lobby_message.edit(embed=embed)
        except discord.HTTPException:
            pass

    async def try_join_lobby(
        self, game: VaultGame, user: discord.User
    ) -> Optional[str]:
        async with game.join_lock:
            if game.is_game_running:
                return "The game already started."
            if not game.lobby_open:
                return "The lobby is closed."
            if user.id in game.joined_players:
                return "You already joined."
            if user.id == game.host_id:
                # The GM set the pool, so they know roughly when it runs dry.
                return "You set the prize pool, so you can't play this one."
            if (
                game.settings.max_players
                and len(game.participants) >= game.settings.max_players
            ):
                return "The lobby is full."
            if not await self.has_profile(user.id):
                return (
                    "You need a character before you can play — "
                    "there'd be nowhere to pay your winnings."
                )

            game.participants.append(user)
            game.joined_players.add(user.id)
            game.hauls[user.id] = 0
            game.banked[user.id] = 0
            await self.update_lobby_message(game)
            return None

    # ------------------------------------------------------------------
    # Game logic
    # ------------------------------------------------------------------
    def roll_vault_total(self, game: VaultGame) -> int:
        """Pick the hidden vault size, capped by the pot so payouts can't exceed it."""
        floor = game.pot * game.settings.vault_floor_pct // 100
        return random.randint(min(floor, game.pot), game.pot)

    def roll_drill(self, game: VaultGame) -> tuple[int, bool]:
        """How much this round's drill takes, as a slice of the ORIGINAL vault.

        Sizing against the original rather than the remainder keeps drills
        roughly constant while the vault shrinks, so danger climbs steadily
        instead of the vault becoming impossible to empty.

        Most drills are modest, which is what makes games last. A minority
        "surge" several times larger, and those are what make the game
        frightening: without them the hint bands would give players a
        mathematically safe exit, since a normal drill can never take more than
        the band boundary they were warned at. Returns (amount, was_surge).
        """
        settings = game.settings
        low = max(1, game.vault_total * settings.drill_min_pct // 100)
        high = max(low, game.vault_total * settings.drill_max_pct // 100)
        amount = random.randint(low, high)

        surge = random.randint(1, 100) <= settings.surge_chance_pct
        if surge:
            amount = amount * settings.surge_mult_pct // 100
        return amount, surge

    def apply_drill(self, game: VaultGame) -> tuple[bool, int, int, bool]:
        """Attempt a drill. Returns (busted, taken, share_each, was_surge)."""
        drill, surge = self.roll_drill(game)
        if drill > game.vault_remaining:
            game.busted = True
            game.history.append(f"Round {game.round}: BUST")
            return True, drill, 0, surge

        inside = game.players_inside()
        game.vault_remaining -= drill
        share = drill // len(inside)
        for player in inside:
            game.hauls[player.id] = game.hauls.get(player.id, 0) + share
        game.history.append(f"Round {game.round}: {money(drill)} out, {money(share)} each")
        return False, drill, share, surge

    def resolve_choices(self, game: VaultGame) -> tuple[list[discord.User], int]:
        """Bank the walkers. Returns (walkers, solo_bonus_paid)."""
        inside = game.players_inside()
        # Anyone who didn't answer is walked out rather than risked.
        walkers = [
            player for player in inside if game.choices.get(player.id, "walk") == "walk"
        ]

        solo_bonus = 0
        deliberate = [p for p in walkers if game.choices.get(p.id) == "walk"]
        if len(walkers) == 1 and len(deliberate) == 1 and len(inside) > 1:
            solo_bonus = (
                game.vault_remaining * game.settings.solo_bonus_pct // 100
            )
            solo_bonus = min(solo_bonus, game.vault_remaining)

        for player in walkers:
            payout = game.hauls.get(player.id, 0)
            if solo_bonus and player is walkers[0]:
                payout += solo_bonus
                game.vault_remaining -= solo_bonus
            game.banked[player.id] = game.banked.get(player.id, 0) + payout
            game.hauls[player.id] = 0
            game.inside.discard(player.id)

        return walkers, solo_bonus

    def bust_losses(self, game: VaultGame) -> dict[int, int]:
        losses = {
            player.id: game.hauls.get(player.id, 0)
            for player in game.players_inside()
            if game.hauls.get(player.id, 0) > 0
        }
        for player in game.players_inside():
            game.hauls[player.id] = 0
        return losses

    # ------------------------------------------------------------------
    # Embeds
    # ------------------------------------------------------------------
    def _haul_lines(self, game: VaultGame) -> str:
        inside = game.players_inside()
        if not inside:
            return "Nobody left inside"
        ordered = sorted(inside, key=lambda p: game.hauls.get(p.id, 0), reverse=True)
        return "\n".join(
            f"**{p.display_name}** — {money(game.hauls.get(p.id, 0))}" for p in ordered
        )

    def build_drill_embed(
        self,
        game: VaultGame,
        taken: int,
        share: int,
        seconds_left: int,
        decided: int,
        surge: bool = False,
        flavour: str | None = None,
        hint: str | None = None,
    ) -> discord.Embed:
        theme = game.theme
        inside = game.players_inside()
        opener = theme["surge"] if surge else (flavour or random.choice(theme["drill"]))
        embed = discord.Embed(
            title=f"{theme['title']} — Round {game.round}",
            colour=discord.Color.orange() if surge else theme["colour"],
            description=(
                f"{opener} **{money(taken)}** comes out — "
                f"**{money(share)}** each.\n"
                f"*{hint or game.hint_line()}*"
            ),
        )
        embed.add_field(
            name=f"Holding ({len(inside)} inside)",
            value=self._haul_lines(game),
            inline=False,
        )
        embed.add_field(
            name="Decided",
            value=f"**{decided} / {len(inside)}**",
            inline=True,
        )
        embed.add_field(
            name="Banked so far",
            value=money(sum(game.banked.values())),
            inline=True,
        )
        embed.set_footer(
            text=(
                f"{seconds_left}s to decide. "
                "No answer walks you out safely."
            )
        )
        return embed

    def build_walk_embed(
        self, game: VaultGame, walkers: list[discord.User], solo_bonus: int
    ) -> discord.Embed:
        theme = game.theme
        remaining = game.players_inside()

        if not walkers:
            # Nobody blinking is a result in its own right, so say so rather
            # than posting an otherwise empty embed.
            return discord.Embed(
                title="Nobody Moves",
                colour=theme["colour"],
                description=(
                    f"Not one of them blinked. All **{len(remaining)}** stay in.\n"
                    + ", ".join(p.display_name for p in remaining)
                ),
            )

        lines = []
        for player in walkers:
            lines.append(
                theme["walk"].format(
                    player=player.display_name,
                    amount=money(game.banked.get(player.id, 0)),
                )
            )
        if solo_bonus:
            lines.append(
                theme["solo"].format(
                    player=walkers[0].display_name, bonus=money(solo_bonus)
                )
            )

        if remaining:
            lines.append(
                f"\n**{len(remaining)}** still inside: "
                + ", ".join(p.display_name for p in remaining)
            )
        else:
            lines.append("\nThat's everyone out. The vault keeps the rest.")

        return discord.Embed(
            title="Walking Out",
            colour=theme["colour"],
            description="\n".join(lines),
        )

    def build_bust_embed(self, game: VaultGame, losses: dict[int, int]) -> discord.Embed:
        theme = game.theme
        embed = discord.Embed(
            title="THE ALARM",
            colour=discord.Color.dark_red(),
            description=random.choice(theme["bust"]),
        )
        if losses:
            ordered = sorted(losses.items(), key=lambda kv: kv[1], reverse=True)
            by_id = {p.id: p for p in game.participants}
            embed.add_field(
                name="Lost inside",
                value="\n".join(
                    f"**{by_id[user_id].display_name}** — {money(amount)} gone"
                    for user_id, amount in ordered
                ),
                inline=False,
            )
        else:
            embed.add_field(
                name="Lost inside",
                value="Nobody was left holding anything.",
                inline=False,
            )
        embed.set_footer(text=theme["survive"])
        return embed

    def build_final_embed(self, game: VaultGame) -> discord.Embed:
        theme = game.theme
        ranked = sorted(
            game.participants, key=lambda p: game.banked.get(p.id, 0), reverse=True
        )
        top = game.banked.get(ranked[0].id, 0) if ranked else 0
        winners = [p for p in ranked if game.banked.get(p.id, 0) == top]

        if top <= 0:
            description = "Nobody got out with a penny. The vault keeps everything."
        elif len(winners) == 1:
            description = theme["winner"].format(
                winner=winners[0].display_name, amount=money(top)
            )
        else:
            names = ", ".join(f"**{w.display_name}**" for w in winners)
            description = f"{names} tie on {money(top)}."

        embed = discord.Embed(
            title=f"{theme['title']} — Final Count",
            colour=theme["colour"],
            description=description,
        )
        embed.add_field(
            name="Payouts",
            value="\n".join(
                f"{i}. {p.display_name} — **{money(game.banked.get(p.id, 0))}**"
                for i, p in enumerate(ranked, start=1)
            )
            or "None",
            inline=False,
        )
        embed.add_field(
            name="The vault",
            value=(
                f"It held **{money(game.vault_total)}**.\n"
                f"Paid out: **{money(sum(game.banked.values()))}**\n"
                f"Rounds survived: **{game.round}**"
            ),
            inline=False,
        )
        embed.set_footer(text="Free to enter. The pool was put up by the Game Master.")
        return embed

    # ------------------------------------------------------------------
    # Round loop
    # ------------------------------------------------------------------
    async def collect_choices(
        self, ctx, game: VaultGame, taken: int, share: int, surge: bool
    ) -> None:
        game.choices = {}
        inside_count = len(game.players_inside())
        # Rolled once, not per refresh: this message is edited every couple of
        # seconds for the countdown, and re-rolling would make the text flicker.
        flavour = random.choice(game.theme["drill"])
        hint = game.hint_line()

        view = DecisionView(game, game.settings.pick_timeout)
        message = await ctx.send(
            embed=self.build_drill_embed(
                game, taken, share, game.settings.pick_timeout, 0, surge, flavour, hint
            ),
            view=view,
        )

        deadline = time.monotonic() + game.settings.pick_timeout
        while time.monotonic() < deadline:
            if len(game.choices) >= inside_count:
                break
            await asyncio.sleep(2)
            seconds_left = max(0, int(deadline - time.monotonic()))
            try:
                await message.edit(
                    embed=self.build_drill_embed(
                        game,
                        taken,
                        share,
                        seconds_left,
                        len(game.choices),
                        surge,
                        flavour,
                        hint,
                    ),
                    view=view,
                )
            except discord.HTTPException:
                pass

        view.closed = True
        view.stop()
        for item in view.children:
            item.disabled = True
        try:
            await message.edit(view=view)
        except discord.HTTPException:
            pass

    async def run_game(self, ctx, game: VaultGame) -> None:
        settings = game.settings
        players = len(game.participants)
        game.vault_total = self.roll_vault_total(game)
        game.vault_remaining = game.vault_total
        game.inside = {p.id for p in game.participants}

        theme = game.theme
        await ctx.send(
            embed=discord.Embed(
                title=f"{theme['title']}",
                colour=theme["colour"],
                description=(
                    f"{theme['open']}\n\n"
                    f"**{players}** of you are going in.\n\n"
                    "Every round the vault is drilled and the take splits between "
                    "everyone still inside. Then you choose in private: **stay in** "
                    "for another round, or **walk away** and keep what you're holding.\n"
                    "**Get caught inside when it runs dry and you lose everything.**"
                ),
            )
        )
        await asyncio.sleep(4)

        while game.inside and game.round < MAX_ROUNDS:
            game.round += 1

            busted, taken, share, surge = self.apply_drill(game)
            if busted:
                losses = self.bust_losses(game)
                await ctx.send(embed=self.build_bust_embed(game, losses))
                game.inside.clear()
                break

            await self.collect_choices(ctx, game, taken, share, surge)
            walkers, solo_bonus = self.resolve_choices(game)
            await ctx.send(embed=self.build_walk_embed(game, walkers, solo_bonus))

            if game.inside:
                await asyncio.sleep(3)

        await self.pay_out(
            {user_id: amount for user_id, amount in game.banked.items() if amount > 0}
        )
        await ctx.send(embed=self.build_final_embed(game))

        paid = sum(game.banked.values())
        winners = sum(1 for p in game.participants if game.banked.get(p.id, 0) > 0)
        await self.gm_log(
            f"\N{BANK} **The Vault** finished in {ctx.channel.mention} "
            f"(host **{ctx.author}**)\n"
            f"Pool **{money(game.pot)}** — vault held **{money(game.vault_total)}** "
            f"— paid out **{money(paid)}** to **{winners}/{len(game.participants)}** "
            f"over **{game.round}** round(s)."
        )

    async def settle_interrupted(self, ctx, game: VaultGame) -> None:
        """Pay out if a game dies part-way through.

        Hauls still inside the vault are paid here too: that money was never
        lost to a bust, so players shouldn't be out of pocket for a crash.
        """
        payouts: dict[int, int] = {}
        for player in game.participants:
            total = game.banked.get(player.id, 0) + game.hauls.get(player.id, 0)
            if total > 0:
                payouts[player.id] = total

        try:
            await self.pay_out(payouts)
        except Exception:
            return

        await ctx.send(
            "The job fell apart part-way through and the game was abandoned.\n"
            f"**{len(payouts)}** player(s) were paid what they were holding."
        )

    async def host_game(self, ctx, game: VaultGame, problems: list[str]) -> None:
        """Run the lobby, check it's viable, then play. The GM never joins."""
        settings = game.settings
        self.games[ctx.channel.id] = game

        try:
            if problems:
                await ctx.send("⚠️ " + "\n⚠️ ".join(problems))

            # Event lobbies pull in people who have never played, so the rules
            # go above the lobby — leaving the lobby as the bottom message, which
            # is the one with the buttons on it.
            await ctx.send(embed=self.build_howto_embed(game))

            view = VaultJoinView(self, game, ctx.author.id)
            message = await ctx.send(embed=self.build_lobby_embed(game), view=view)
            view.message = message
            game.lobby_message = message
            game.lobby_view = view
            game.lobby_ends_at = time.monotonic() + settings.join_timeout

            while not view.is_finished():
                if self._lobby_seconds_left(game) <= 0:
                    break
                await asyncio.sleep(5)
                await self.update_lobby_message(game)

            game.lobby_open = False
            view.stop()
            for item in view.children:
                item.disabled = True
            try:
                await message.edit(view=view)
            except discord.HTTPException:
                pass

            if len(game.participants) < settings.min_players:
                return await ctx.send(
                    f"Only **{len(game.participants)}** joined, and "
                    f"**{settings.min_players}** are needed."
                )

            if game.pot is None:
                return await ctx.send(
                    f"{ctx.author.mention}, no prize pool was set, so the vault "
                    "never opened. Start another and press **Set Prize Pool** "
                    "before the lobby closes."
                )

            game.is_game_running = True
            await self.gm_log(
                f"\N{BANK} **The Vault** started by **{ctx.author}** "
                f"(`{ctx.author.id}`)\n"
                f"Channel: {ctx.channel.mention} — Players: "
                f"**{len(game.participants)}** — Theme: **{game.settings.theme}**\n"
                f"Prize pool: **{money(game.pot)}**\n"
                f"Started: <{ctx.message.jump_url}>"
            )
            try:
                await self.run_game(ctx, game)
            except Exception:
                # Players may be holding money that was never lost to a bust.
                await self.settle_interrupted(ctx, game)
                raise

        finally:
            self.games.pop(ctx.channel.id, None)

    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------
    @is_gm()
    @commands.guild_only()
    @commands.command(
        name="gmvault",
        aliases=["vault", "gvault", "thevault", "eventvault"],
        brief=_("Run a game of The Vault for your players"),
    )
    @locale_doc
    async def gmvault(self, ctx, *setup_tokens: str):
        _(
            """`[setup_tokens]` - Optional `name=value` settings.

            Runs a game of The Vault for your players. Free to enter, with a
            prize pool you put up for the occasion. Built for admin-run events.

            The vault holds a hidden amount that nobody is told. Each round it is
            drilled and the take is split between everyone still inside, adding to
            a haul that is not yet safe. Players then privately choose to **stay
            in** for another round or **walk away** and bank what they hold. If a
            drill hits an empty vault, everyone still inside loses their entire
            haul. Players are told how full the vault looks, never how much is left.

            The pool is not typed into the channel. Once the lobby opens, press
            **Set Prize Pool** and enter the amount privately, so players never
            learn how deep the vault runs. You can change it any time before the
            lobby closes.

            Usage:
            `{prefix}gmvault`
            `{prefix}gmvault theme=casino timer=20 min=5`

            Options:
            - `timer` (10-120) - seconds players get to decide each round
            - `join` (30-600) - lobby countdown in seconds
            - `min` / `max` - player limits
            - `solo` (0-40) - % bonus for being the only one to walk in a round
            - `drillmin` / `drillmax` - size of each drill, as a % of the vault
            - `surge` (0-60) - % of drills that hit several times harder
            - `surgesize` (100-500) - how much bigger a surge is, as a %
            - `floor` (20-100) - smallest the hidden vault can roll, as a % of the pool
            - `theme` - heist, corporate, casino or pirate

            Notes:
            - Game Masters only, because the prize is generated rather than paid in.
            - You do not play, since you know how much is in there.
            - Nobody pays to join, and players need a character to be paid.
            - A rules card is posted above the lobby for first-time players.
            - The lobby shows only whether a pool has been set, never the amount.
            - If the lobby closes without a pool set, the game is called off.
            - The pool is the hard ceiling on payouts: the hidden vault rolls
              between the `floor` percentage of it and the whole amount."""
        )
        if ctx.channel.id in self.games:
            return await ctx.send("A vault game is already running in this channel.")

        settings, problems = self.parse_setup(setup_tokens)
        game = VaultGame(ctx.author.id, settings)
        await self.host_game(ctx, game, problems)

    @commands.guild_only()
    @commands.command(
        name="vaulthelp",
        aliases=["vaultrules"],
        brief=_("Explain how The Vault works"),
    )
    @locale_doc
    async def vaulthelp(self, ctx):
        _("""Explains the rules of The Vault.""")
        embed = self.build_howto_embed()
        embed.set_footer(
            text=(
                "Most money banked wins. "
                "Games are run by Game Masters — watch for a lobby."
            )
        )
        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(Vault(bot))

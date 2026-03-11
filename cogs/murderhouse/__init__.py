"""
The IdleRPG Discord Bot
Copyright (C) 2018-2021 Diniboy and Gelbpunkt
Copyright (C) 2026 Lunar and contributors

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
"""

from __future__ import annotations

import asyncio
import math
import re
import traceback

from collections import defaultdict
from dataclasses import dataclass, field
from io import BytesIO
from typing import Awaitable, Callable

import discord
from PIL import Image, ImageDraw, ImageOps

from discord.enums import ButtonStyle
from discord.ext import commands
from discord.ui.button import Button

from utils import random
from utils.i18n import _, locale_doc
from utils.joins import JoinView
from utils.misc import nice_join

FOYER = "Foyer"
ITEM_FLASHLIGHT = "flashlight"
ITEM_NOISEMAKER = "noisemaker"
ITEM_LABELS = {
    ITEM_FLASHLIGHT: "Flashlight",
    ITEM_NOISEMAKER: "Noisemaker",
}
LOWER_ESCAPE_ROUTES: dict[str, str] = {
    "Kitchen": "Kitchen back door",
    "Basement": "Basement bulkhead",
}
UPPER_ESCAPE_ROUTES: dict[str, str] = {
    "Attic": "Attic fire ladder",
    "Master Bedroom": "Master bedroom balcony",
}
ESCAPE_ROUTES: dict[str, str] = {**LOWER_ESCAPE_ROUTES, **UPPER_ESCAPE_ROUTES}
HOUSE_MAP: dict[str, tuple[str, ...]] = {
    "Foyer": ("Kitchen", "Study", "Upstairs Hall", "Basement"),
    "Kitchen": ("Foyer",),
    "Study": ("Foyer",),
    "Upstairs Hall": ("Foyer", "Master Bedroom", "Bathroom", "Attic"),
    "Master Bedroom": ("Upstairs Hall",),
    "Bathroom": ("Upstairs Hall",),
    "Attic": ("Upstairs Hall",),
    "Basement": ("Foyer",),
}
HIDING_SPOTS: dict[str, tuple[str, ...]] = {
    "Foyer": ("coat closet", "grandfather clock alcove", "umbrella stand"),
    "Kitchen": ("pantry", "under the table", "utility cabinet"),
    "Study": ("curtain nook", "bookshelf gap", "under the desk"),
    "Upstairs Hall": ("linen closet", "behind the banister", "display cabinet"),
    "Master Bedroom": ("wardrobe", "under the bed", "behind the vanity"),
    "Bathroom": ("shower curtain", "laundry hamper", "under the sink"),
    "Attic": ("trunk pile", "old wardrobe", "roof beam shadow"),
    "Basement": ("furnace nook", "storage shelves", "behind the water heater"),
}
START_ROOMS = [room for room in HOUSE_MAP if room != FOYER]
ESCAPE_CLUE_LINES = [
    "a rain-warped floor plan with a cellar bulkhead circled in red",
    "a fire-safety note about the attic ladder release",
    "half of a service key tagged for an exterior latch",
    "a penciled warning about keeping both escape routes clear",
    "the missing latch pin for an outside hatch buried in old junk",
    "the final release code scratched onto a dusty toolbox lid",
    "a torn maintenance receipt listing an emergency balcony release",
    "a grease-stained note warning that one escape path opens later than the other",
]
AMBIENCE_LINES = [
    "A floorboard groans somewhere upstairs.",
    "The house answers with a long, wet silence.",
    "A door clicks shut on its own.",
    "Something metallic skitters across the floor and stops.",
    "A draft snakes through the walls and carries a breath you cannot place.",
    "Every room feels one second too quiet.",
]
BLACKOUT_LINES = [
    "The blackout swallows the house. Every room becomes a rumor.",
    "Only scraps of moonlight cut through the blackout.",
    "The lights stay dead, and every sound lands harder.",
]
JUNK_DISCOVERIES = {
    "Foyer": (
        "You find a cracked family portrait and no useful way out.",
        "You shake down the entry table and only find dust and old receipts.",
    ),
    "Kitchen": (
        "You rummage through drawers and only turn up dull cutlery.",
        "A cabinet slams open, but it holds nothing except stale cans.",
    ),
    "Study": (
        "You pull books until the shelf coughs dust in your face.",
        "The desk is full of meaningless letters and broken pens.",
    ),
    "Upstairs Hall": (
        "A loose floorboard gives you splinters, not answers.",
        "The display cabinet offers porcelain eyes and nothing else.",
    ),
    "Master Bedroom": (
        "You tear through jewelry boxes and find nothing that opens the house.",
        "The wardrobe hides moth-eaten coats and no salvation.",
    ),
    "Bathroom": (
        "The medicine cabinet is empty except for expired tablets.",
        "You search every drawer and only find towels and broken razors.",
    ),
    "Attic": (
        "The trunks are packed with rotten cloth and useless keepsakes.",
        "You crack open a box and release a storm of dust, nothing more.",
    ),
    "Basement": (
        "You dig through tool bins and only find rusted junk.",
        "The shelves rattle, but the boxes hold nothing worth keeping.",
    ),
}
ROOM_DEATH_FEATURES = {
    "Foyer": ("the umbrella stand", "the staircase rail", "the grandfather clock"),
    "Kitchen": ("the pantry door", "the counters", "the hanging pots"),
    "Study": ("the writing desk", "the bookcase", "the curtained window"),
    "Upstairs Hall": ("the banister", "the display cabinet", "the wall mirror"),
    "Master Bedroom": ("the vanity mirror", "the bedframe", "the balcony doors"),
    "Bathroom": ("the porcelain sink", "the bathtub edge", "the medicine cabinet"),
    "Attic": ("the roof beams", "the trunk pile", "the ladder hatch"),
    "Basement": ("the furnace", "the concrete steps", "the water heater"),
}
TESTPILLOW_BG_URL = (
    "https://pub-0e7afc36364b4d5dbd1fd2bea161e4d1.r2.dev/"
    "295173706496475136_contentNewer.png"
)
TESTPILLOW_ROOM_COORDS = {
    "kitchen": {"x": 125, "y": 230, "w": 235, "h": 145},
    "foyer": {"x": 435, "y": 345, "w": 235, "h": 115},
    "study": {"x": 735, "y": 245, "w": 180, "h": 140},
    "staircase_hall": {"x": 455, "y": 175, "w": 195, "h": 105},
    "master_bedroom": {"x": 1020, "y": 225, "w": 155, "h": 115},
    "bathroom": {"x": 1275, "y": 225, "w": 165, "h": 85},
    "upstairs_hall": {"x": 1065, "y": 355, "w": 320, "h": 65},
    "attic_stairs": {"x": 1010, "y": 445, "w": 165, "h": 60},
    "basement": {"x": 560, "y": 620, "w": 400, "h": 155},
}
PIL_RESAMPLE = (
    Image.Resampling.LANCZOS if hasattr(Image, "Resampling") else Image.LANCZOS
)


@dataclass
class GuestState:
    member: discord.abc.User
    room: str
    alive: bool = True
    escaped: bool = False
    escape_route: str | None = None
    hidden_spot: str | None = None
    inventory: list[str] = field(default_factory=list)


class MurderHouseJoinView(JoinView):
    def __init__(
        self,
        *args,
        leave_message: str,
        refresh_lobby: Callable[[], Awaitable[None]] | None = None,
        **kwargs,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.leave_message = leave_message
        self.refresh_lobby = refresh_lobby
        leave_button = Button(
            style=ButtonStyle.secondary,
            label=_("Leave the Murder House game!"),
        )
        leave_button.callback = self.leave_button_pressed
        self.add_item(leave_button)

    async def button_pressed(self, interaction: discord.Interaction) -> None:
        await super().button_pressed(interaction)
        if self.refresh_lobby is not None:
            await self.refresh_lobby()

    async def leave_button_pressed(self, interaction: discord.Interaction) -> None:
        if interaction.user in self.joined:
            self.joined.remove(interaction.user)
            await interaction.response.send_message(
                self.leave_message, ephemeral=True
            )
        else:
            await interaction.response.send_message(
                _("You are not in the Murder House lobby."), ephemeral=True
            )
        if self.refresh_lobby is not None:
            await self.refresh_lobby()


class MurderHouseGame:
    ACTION_TIMEOUT_SECONDS = 70
    REPORT_DELAY_SECONDS = 1.0
    JOIN_TIMEOUT_SECONDS = 120
    CUT_POWER_COOLDOWN = 3
    MAX_ESCAPE_GOAL = 8
    SECONDARY_EXIT_DELAY_ROUNDS = 4

    def __init__(
        self,
        ctx,
        players: list[discord.abc.User],
        *,
        forced_killer: discord.abc.User | None = None,
    ):
        self.ctx = ctx
        self.players = list(players)
        self.round = 1
        self.escape_goal = self._escape_goal_for_player_count()
        self.escape_progress = 0
        self.blackout_rounds = 0
        self.power_cooldown = 0
        self.killer = forced_killer or random.choice(self.players)
        self.killer_room = random.choice(START_ROOMS)
        escape_rooms = self._choose_escape_rooms()
        self.primary_escape_room = escape_rooms[0]
        self.secondary_escape_room = escape_rooms[1]
        self.primary_escape_open = False
        self.secondary_escape_open = False
        self.secondary_escape_unlock_round: int | None = None
        self.final_chase_announced = False
        self.guests: dict[int, GuestState] = {}
        self.traps: dict[tuple[str, str], int] = {}
        self.barricades: dict[str, int] = {}
        self.escaped_members: list[discord.abc.User] = []
        self.casualties: list[str] = []
        self.dm_warning_sent: set[int] = set()
        self.escape_clue_queue = random.shuffle(
            ESCAPE_CLUE_LINES[: max(self.escape_goal, 4)]
        )
        self.room_stashes = self._build_room_stashes()
        self.game_channel_link = self._build_game_channel_link()
        self._assign_guest_rooms()

    def _build_game_channel_link(self) -> str:
        channel = getattr(self.ctx, "channel", None)
        jump_url = getattr(channel, "jump_url", None)
        if isinstance(jump_url, str) and jump_url:
            return jump_url
        channel_id = getattr(channel, "id", None)
        if channel_id is None:
            return ""
        guild_id = getattr(getattr(self.ctx, "guild", None), "id", None)
        if guild_id is None:
            return f"https://discord.com/channels/@me/{channel_id}"
        return f"https://discord.com/channels/{guild_id}/{channel_id}"

    def _assign_guest_rooms(self) -> None:
        available_rooms = [room for room in START_ROOMS if room != self.killer_room]
        if not available_rooms:
            available_rooms = START_ROOMS.copy()
        for player in self.players:
            if player.id == self.killer.id:
                continue
            room = random.choice(available_rooms)
            self.guests[player.id] = GuestState(member=player, room=room)

    def _build_room_stashes(self) -> dict[str, list[str]]:
        clue_count = self._clue_stash_count()
        clue_rooms = set(random.sample(list(HOUSE_MAP), clue_count))
        filler_pool = [ITEM_FLASHLIGHT] * 2 + [ITEM_NOISEMAKER] * 3
        filler_slots = len(HOUSE_MAP) * 2 - clue_count
        filler_pool += ["junk"] * max(0, filler_slots - len(filler_pool))
        filler_pool = random.shuffle(filler_pool)

        room_stashes: dict[str, list[str]] = {room: [] for room in HOUSE_MAP}
        for room in HOUSE_MAP:
            if room in clue_rooms:
                room_stashes[room].append("clue")
            while len(room_stashes[room]) < 2 and filler_pool:
                room_stashes[room].append(filler_pool.pop(0))
            room_stashes[room] = random.shuffle(room_stashes[room])
        return room_stashes

    def _escape_goal_for_player_count(self) -> int:
        return min(self.MAX_ESCAPE_GOAL, max(4, len(self.players)))

    def _clue_stash_count(self) -> int:
        spare_clues = 1 if len(self.players) <= 6 else 0
        return min(self.escape_goal + spare_clues, len(HOUSE_MAP))

    def _alive_guest_states(self) -> list[GuestState]:
        return [
            state for state in self.guests.values() if state.alive and not state.escaped
        ]

    def _survivor_mentions(self) -> str:
        alive = [state.member.mention for state in self._alive_guest_states()]
        if not alive:
            return _("None")
        return ", ".join(alive)

    def _inventory_text(self, state: GuestState) -> str:
        if not state.inventory:
            return _("none")
        labels = [ITEM_LABELS.get(item, item.title()) for item in state.inventory]
        return ", ".join(labels)

    def _house_map_text(self) -> str:
        lines = []
        for room, exits in HOUSE_MAP.items():
            lines.append(f"{room} -> {', '.join(exits)}")
        return "\n".join(lines)

    def _build_map_embed(self, *, current_room: str) -> discord.Embed:
        return (
            discord.Embed(
                title=_("Murder House Map"),
                description=f"```{self._house_map_text()}```",
                colour=self.ctx.bot.config.game.primary_colour,
            )
            .add_field(name=_("Current Room"), value=f"**{current_room}**", inline=True)
            .add_field(
                name=_("Exit Status"),
                value=self._escape_status_text(markdown=True),
                inline=False,
            )
        )

    def _build_map_button(self, *, current_room: str) -> Button:
        button = Button(style=ButtonStyle.secondary, label=_("Open Map"))

        async def send_map(interaction: discord.Interaction) -> None:
            await interaction.response.send_message(
                embed=self._build_map_embed(current_room=current_room)
            )

        button.callback = send_map
        return button

    def _choose_escape_rooms(self) -> tuple[str, str]:
        lower_room = random.choice(list(LOWER_ESCAPE_ROUTES))
        upper_room = random.choice(list(UPPER_ESCAPE_ROUTES))
        chosen_rooms = random.shuffle([lower_room, upper_room])
        return chosen_rooms[0], chosen_rooms[1]

    def _escape_route_label(self, room: str) -> str:
        return ESCAPE_ROUTES[room]

    def _escape_routes_text(
        self, rooms: list[str] | tuple[str, ...] | None = None, *, markdown: bool = False
    ) -> str:
        source_rooms = rooms if rooms is not None else tuple(ESCAPE_ROUTES)
        routes = [self._escape_route_label(room) for room in source_rooms]
        if markdown:
            routes = [f"**{route}**" for route in routes]
        return nice_join(routes)

    def _open_escape_rooms(self) -> tuple[str, ...]:
        rooms = []
        if self.primary_escape_open:
            rooms.append(self.primary_escape_room)
        if self.secondary_escape_open:
            rooms.append(self.secondary_escape_room)
        return tuple(rooms)

    def _in_final_chase(self) -> bool:
        return (
            len(self._alive_guest_states()) == 1
            and self.escape_progress < self.escape_goal
        )

    def _escape_status_text(self, *, markdown: bool = False) -> str:
        if self._in_final_chase():
            return _(
                "Final Chase: both selected exits are open, and the last houseguest cannot hide, search, or barricade."
            )
        open_rooms = self._open_escape_rooms()
        if not open_rooms:
            return _(
                "Locked. One exit opens after the final clue, and a second opens {delay} rounds later. If only one houseguest remains first, Final Chase opens both selected exits. Possible exits: {routes}."
            ).format(
                delay=self.SECONDARY_EXIT_DELAY_ROUNDS,
                routes=self._escape_routes_text(markdown=markdown),
            )
        if len(open_rooms) == 1:
            rounds_left = max(
                0,
                (self.secondary_escape_unlock_round or self.round) - self.round,
            )
            return _(
                "Open now: {route}. Another exit opens in {rounds} rounds."
            ).format(
                route=self._escape_routes_text(open_rooms, markdown=markdown),
                rounds=rounds_left,
            )
        return _("Open now: {routes}.").format(
            routes=self._escape_routes_text(open_rooms, markdown=markdown)
        )

    def _compact_escape_status_text(self) -> str:
        if self._in_final_chase():
            return _("Final Chase: both selected exits open.")
        open_rooms = self._open_escape_rooms()
        if not open_rooms:
            return _(
                "Locked. First exit at full clues, second +{delay}. Final Chase opens both if 1 guest remains."
            ).format(delay=self.SECONDARY_EXIT_DELAY_ROUNDS)
        if len(open_rooms) == 1:
            rounds_left = max(
                0,
                (self.secondary_escape_unlock_round or self.round) - self.round,
            )
            return _("Open: {route}. Next exit in {rounds}.").format(
                route=self._escape_routes_text(open_rooms),
                rounds=rounds_left,
            )
        return _("Open: {routes}.").format(
            routes=self._escape_routes_text(open_rooms)
        )

    def _unlock_primary_escape(self, public_lines: list[str]) -> None:
        if self.primary_escape_open:
            return
        self.primary_escape_open = True
        self.secondary_escape_unlock_round = (
            self.round + self.SECONDARY_EXIT_DELAY_ROUNDS
        )
        public_lines.append(
            _(
                "The final clue clicks into place. The {primary} is now open. The {secondary} will open in **{rounds}** rounds."
            ).format(
                primary=f"**{self._escape_route_label(self.primary_escape_room)}**",
                secondary=f"**{self._escape_route_label(self.secondary_escape_room)}**",
                rounds=self.SECONDARY_EXIT_DELAY_ROUNDS,
            )
        )

    def _maybe_open_secondary_escape(self, public_lines: list[str]) -> None:
        if self.secondary_escape_open or self.secondary_escape_unlock_round is None:
            return
        if self.round < self.secondary_escape_unlock_round:
            return
        self.secondary_escape_open = True
        public_lines.append(
            _("A final latch gives way. The {route} is now open.").format(
                route=f"**{self._escape_route_label(self.secondary_escape_room)}**"
            )
        )

    def _start_final_chase(self, public_lines: list[str]) -> None:
        if self.final_chase_announced:
            return
        self.final_chase_announced = True
        self.primary_escape_open = True
        self.secondary_escape_open = True
        public_lines.append(
            _(
                "Only one houseguest is left inside. **Final Chase** begins: the {primary} and {secondary} are thrown open, and the last survivor has to run."
            ).format(
                primary=f"**{self._escape_route_label(self.primary_escape_room)}**",
                secondary=f"**{self._escape_route_label(self.secondary_escape_room)}**",
            )
        )

    def _room_death_feature(self, room: str) -> str:
        return random.choice(ROOM_DEATH_FEATURES.get(room, ("the floor",)))

    def _flavored_death_text(
        self, *, mode: str, victim: discord.abc.User, room: str, spot: str | None = None
    ) -> str:
        feature = self._room_death_feature(room)
        templates = {
            "sweep": (
                _("**{victim}** is cornered in the **{room}** and left crumpled against {feature}."),
                _("**{victim}** tries to run through the **{room}**, but never gets past {feature}."),
                _("The **{room}** erupts in violence. **{victim}** drops beside {feature}."),
            ),
            "check": (
                _("The **{spot}** in the **{room}** bursts open. **{victim}** is smashed into {feature}."),
                _("**{victim}** is dragged out of the **{spot}** in the **{room}** and thrown across {feature}."),
                _("A hand tears into the **{spot}** in the **{room}**. **{victim}** never gets beyond {feature}."),
            ),
            "trap": (
                _("A trap snaps shut in the **{room}** and hurls **{victim}** into {feature}."),
                _("Metal bites down in the **{room}**. **{victim}** collapses beside {feature}."),
                _("The trap in the **{room}** goes off hard. **{victim}** is broken against {feature}."),
            ),
        }
        return random.choice(templates[mode]).format(
            victim=victim.display_name,
            room=room,
            spot=spot,
            feature=feature,
        )

    def _joined_preview(self) -> str:
        sorted_players = sorted(
            self.players,
            key=lambda player: getattr(player, "display_name", str(player)).casefold(),
        )
        return ", ".join(player.mention for player in sorted_players)

    async def _safe_send_dm(self, user: discord.abc.User, content: str) -> None:
        try:
            await user.send(content)
        except discord.Forbidden:
            if user.id not in self.dm_warning_sent:
                self.dm_warning_sent.add(user.id)
                await self.ctx.send(
                    _(
                        "{user}, your DMs are closed. The game still works, but your hidden choices will be random whenever a DM prompt fails."
                    ).format(user=user.mention),
                    delete_after=20,
                )

    async def _send_back_to_game_link(self, user: discord.abc.User) -> None:
        if not self.game_channel_link:
            return
        await self._safe_send_dm(
            user,
            _("Back to game: {link}").format(link=self.game_channel_link),
        )

    async def _send_opening_dms(self) -> None:
        tasks = []
        for state in self.guests.values():
            content = _(
                "**Murder House**\n"
                "You are a houseguest trying to survive long enough to escape.\n"
                "Start room: **{room}**\n"
                "Collect **{goal}** escape clues.\n"
                "There are **4** possible exits in the house: {routes}.\n"
                "When the final clue is found, one selected exit opens. A second selected exit opens **{delay}** rounds later.\n"
                "If you become the last houseguest before the clue track is full, **Final Chase** opens both selected exits for one last run.\n"
                "Anyone who reaches an open exit escapes for good.\n"
                "Hiding buys time, but it never counts as a win by itself.\n"
                "Map:\n```{house_map}```"
            ).format(
                room=state.room,
                goal=self.escape_goal,
                routes=self._escape_routes_text(markdown=True),
                delay=self.SECONDARY_EXIT_DELAY_ROUNDS,
                house_map=self._house_map_text(),
            )
            tasks.append(self._safe_send_dm(state.member, content))

        killer_content = _(
            "**Murder House**\n"
            "You are the **Murderer**.\n"
            "Start room: **{room}**\n"
            "The houseguests need **{goal}** clues to start opening exits.\n"
            "There are **4** possible exits: {routes}.\n"
            "One selected exit opens after the final clue, and a second selected exit opens **{delay}** rounds later.\n"
            "If only one houseguest remains before the clue track is full, **Final Chase** opens both selected exits and forces a last run.\n"
            "Sweep rooms, check hiding spots, listen for noise, set traps, and kill whoever does not make it out.\n"
            "Map:\n```{house_map}```"
        ).format(
            room=self.killer_room,
            goal=self.escape_goal,
            routes=self._escape_routes_text(markdown=True),
            delay=self.SECONDARY_EXIT_DELAY_ROUNDS,
            house_map=self._house_map_text(),
        )
        tasks.append(self._safe_send_dm(self.killer, killer_content))
        await asyncio.gather(*tasks)

    def _build_intro_embed(self) -> discord.Embed:
        description = _(
            "**{killer_count} murderer** is hidden among **{guest_count} houseguest(s)**.\n"
            "Houseguests must find **{goal}** escape clues.\n"
            "One selected exit opens first, and a second selected exit opens **{delay}** rounds later.\n"
            "The possible exits are {routes}.\n"
            "If only one houseguest remains before the clue track is full, **Final Chase** opens both selected exits.\n"
            "Anyone who reaches an open exit escapes permanently.\n"
            "Simply hiding until time runs out does not save the houseguests.\n"
            "Talk in channel. Hidden actions happen in DMs."
        ).format(
            killer_count=1,
            guest_count=len(self.guests),
            goal=self.escape_goal,
            delay=self.SECONDARY_EXIT_DELAY_ROUNDS,
            routes=self._escape_routes_text(markdown=True),
        )
        return (
            discord.Embed(
                title=_("Murder House"),
                description=description,
                colour=self.ctx.bot.config.game.primary_colour,
            )
            .add_field(name=_("Players"), value=self._joined_preview(), inline=False)
            .add_field(
                name=_("House Map"),
                value=f"```{self._house_map_text()}```",
                inline=False,
            )
        )

    def _build_round_embed(self, public_lines: list[str]) -> discord.Embed:
        description = "\n".join(public_lines) if public_lines else _("The house refuses to speak.")
        return (
            discord.Embed(
                title=_("Murder House - Round {round}").format(round=self.round),
                description=description,
                colour=self.ctx.bot.config.game.primary_colour,
            )
            .add_field(
                name=_("Alive Houseguests"),
                value=self._survivor_mentions(),
                inline=False,
            )
            .add_field(
                name=_("Escape Progress"),
                value=_("{found}/{goal} clues").format(
                    found=self.escape_progress, goal=self.escape_goal
                ),
                inline=True,
            )
            .add_field(
                name=_("Escaped"),
                value=str(len(self.escaped_members)),
                inline=True,
            )
            .add_field(
                name=_("Phase"),
                value=_("Final Chase") if self._in_final_chase() else _("Normal"),
                inline=True,
            )
            .add_field(
                name=_("Exit Status"),
                value=self._escape_status_text(markdown=True),
                inline=False,
            )
        )

    def _build_final_embed(self) -> discord.Embed:
        kill_count = sum(1 for state in self.guests.values() if not state.alive)
        if self.escaped_members:
            description = _(
                "**{escaped}** made it out of the house. The murderer leaves behind **{kills}** kill(s)."
            ).format(
                escaped=nice_join(
                    [f"**{player.display_name}**" for player in self.escaped_members]
                ),
                kills=kill_count,
            )
        else:
            description = _(
                "No houseguests escaped. The murderer kills **{kills}** and owns the ending."
            ).format(kills=kill_count)

        survivor_lines = []
        for state in self.guests.values():
            if state.escaped:
                route = state.escape_route or _("unknown exit")
                status = _("escaped through the {route}").format(route=route.lower())
            elif state.alive:
                status = _("still alive in the {room}").format(room=state.room)
            else:
                status = _("died in the house")
            survivor_lines.append(f"**{state.member.display_name}** - {status}")

        casualty_text = "\n".join(self.casualties[-8:]) if self.casualties else _("None")
        return (
            discord.Embed(
                title=_("Murder House - Game Over"),
                description=description,
                colour=self.ctx.bot.config.game.primary_colour,
            )
            .add_field(
                name=_("Murderer"),
                value=f"**{self.killer.display_name}**",
                inline=False,
            )
            .add_field(
                name=_("Kills"),
                value=str(kill_count),
                inline=False,
            )
            .add_field(
                name=_("Houseguests"),
                value="\n".join(survivor_lines) if survivor_lines else _("None"),
                inline=False,
            )
            .add_field(name=_("Last Casualties"), value=casualty_text, inline=False)
        )

    def _cleanup_expired_traps(self) -> None:
        self.traps = {
            key: expiry for key, expiry in self.traps.items() if expiry >= self.round
        }
        self.barricades = {
            room: expiry for room, expiry in self.barricades.items() if expiry >= self.round
        }

    def _movement_noise(self) -> int:
        return 2 + (1 if self.round >= 5 else 0)

    def _activity_noise(self) -> int:
        return 2 + (1 if self.round >= 6 else 0)

    def _room_states(self, room: str) -> list[GuestState]:
        return [state for state in self._alive_guest_states() if state.room == room]

    def _build_guest_options(self, state: GuestState) -> list[dict]:
        current_room = state.room
        options: list[dict] = []
        final_chase = self._in_final_chase()

        if current_room in self._open_escape_rooms():
            options.append(
                {
                    "label": _("Force open the {route} and escape").format(
                        route=self._escape_route_label(current_room)
                    ),
                    "kind": "escape",
                }
            )

        if not final_chase:
            for spot in HIDING_SPOTS[current_room]:
                options.append(
                    {
                        "label": _("Hide in the {spot}").format(spot=spot),
                        "kind": "hide",
                        "spot": spot,
                    }
                )

            options.append(
                {
                    "label": _("Search the {room} for clues").format(room=current_room),
                    "kind": "scavenge",
                }
            )
            options.append(
                {
                    "label": _("Barricade the {room}").format(room=current_room),
                    "kind": "barricade",
                }
            )

        for adjacent_room in HOUSE_MAP[current_room]:
            options.append(
                {
                    "label": _("Sneak into the {room}").format(room=adjacent_room),
                    "kind": "move",
                    "room": adjacent_room,
                }
            )
            options.append(
                {
                    "label": _("Peek toward the {room}").format(room=adjacent_room),
                    "kind": "peek",
                    "room": adjacent_room,
                }
            )

        if ITEM_FLASHLIGHT in state.inventory:
            for target_room in [current_room, *HOUSE_MAP[current_room]]:
                options.append(
                    {
                        "label": _("Use your flashlight on the {room}").format(
                            room=target_room
                        ),
                        "kind": "flashlight",
                        "room": target_room,
                    }
                )

        if ITEM_NOISEMAKER in state.inventory:
            for target_room in [current_room, *HOUSE_MAP[current_room]]:
                options.append(
                    {
                        "label": _("Wind up a noisemaker in the {room}").format(
                            room=target_room
                        ),
                        "kind": "noisemaker",
                        "room": target_room,
                    }
                )

        return options

    def _build_killer_options(self) -> list[dict]:
        current_room = self.killer_room
        options = [
            {
                "label": _("Sweep the {room}").format(room=current_room),
                "kind": "sweep",
            },
            {
                "label": _("Stand still and listen at the doors"),
                "kind": "listen",
            },
        ]

        if self.power_cooldown <= 0 and self.blackout_rounds <= 0:
            options.append({"label": _("Kill the house power"), "kind": "cut_power"})

        for spot in HIDING_SPOTS[current_room]:
            options.append(
                {
                    "label": _("Check the {spot}").format(spot=spot),
                    "kind": "check",
                    "spot": spot,
                }
            )
            if (current_room, spot) not in self.traps:
                options.append(
                    {
                        "label": _("Rig the {spot} with a trap").format(spot=spot),
                        "kind": "trap",
                        "spot": spot,
                    }
                )

        for adjacent_room in HOUSE_MAP[current_room]:
            options.append(
                {
                    "label": _("Move quietly into the {room}").format(room=adjacent_room),
                    "kind": "move",
                    "room": adjacent_room,
                }
            )
            options.append(
                {
                    "label": _("Storm into the {room} and sweep it").format(
                        room=adjacent_room
                    ),
                    "kind": "storm",
                    "room": adjacent_room,
                }
            )

        return options

    def _sense_room(
        self,
        target_room: str,
        *,
        strong: bool,
        current_blackout: bool,
        noise_by_room: dict[str, int],
        viewer_id: int,
    ) -> str:
        states = [
            state
            for state in self._room_states(target_room)
            if state.member.id != viewer_id
        ]
        killer_here = self.killer_room == target_room
        visible_count = len(states)
        hidden_count = sum(1 for state in states if state.hidden_spot is not None)

        if strong:
            if killer_here:
                return _(
                    "Your flashlight slices into the **{room}**. The murderer is there."
                ).format(room=target_room)
            if visible_count:
                return _(
                    "Your flashlight catches movement in the **{room}**. At least **{count}** other houseguest(s) are there."
                ).format(room=target_room, count=visible_count)
            if noise_by_room.get(target_room, 0) > 0:
                return _(
                    "Your flashlight finds no body in the **{room}**, but something moved through it recently."
                ).format(room=target_room)
            return _("Your flashlight finds nothing moving in the **{room}**.").format(
                room=target_room
            )

        if current_blackout and random.randint(1, 100) <= 60:
            if noise_by_room.get(target_room, 0) > 0:
                return _(
                    "The blackout kills your sight. You only hear noise from the **{room}**."
                ).format(room=target_room)
            return _(
                "The blackout makes the **{room}** unreadable. You get nothing useful."
            ).format(room=target_room)

        if killer_here and random.randint(1, 100) <= (65 if not current_blackout else 35):
            return _("You glimpse the murderer in the **{room}**.").format(
                room=target_room
            )
        if visible_count:
            if hidden_count and hidden_count == visible_count:
                return _("You catch faint breathing from the **{room}**.").format(
                    room=target_room
                )
            return _("You catch movement in the **{room}**.").format(room=target_room)
        if noise_by_room.get(target_room, 0) > 0:
            return _("You hear recent movement in the **{room}**.").format(
                room=target_room
            )
        return _("The **{room}** feels still for now.").format(room=target_room)

    async def _choose_action(
        self,
        user: discord.abc.User,
        options: list[dict],
        *,
        title: str,
        footer: str | None = None,
        extra_items: list[discord.ui.Item] | None = None,
    ) -> dict:
        try:
            index = await self.ctx.bot.paginator.Choose(
                entries=[option["label"] for option in options],
                return_index=True,
                title=title,
                footer=footer,
                timeout=self.ACTION_TIMEOUT_SECONDS,
                extra_items=extra_items,
            ).paginate(self.ctx, location=user)
            return options[index]
        except (
            self.ctx.bot.paginator.NoChoice,
            asyncio.TimeoutError,
            discord.Forbidden,
            discord.HTTPException,
            ValueError,
        ):
            await self.ctx.send(
                _(
                    "I couldn't get a DM choice from {user}. The house makes a panicked choice instead."
                ).format(user=user.mention),
                delete_after=20,
            )
            return random.choice(options)

    async def _prompt_guest_action(
        self, state: GuestState, *, current_blackout: bool
    ) -> tuple[int, dict]:
        title = _(
            "Murder House - Round {round}\n"
            "Room: {room}\n"
            "Clues: {found}/{goal}\n"
            "Exits: {exits}\n"
            "Inventory: {inventory}\n"
        ).format(
            round=self.round,
            room=state.room,
            found=self.escape_progress,
            goal=self.escape_goal,
            exits=self._compact_escape_status_text(),
            inventory=self._inventory_text(state),
        )
        footer = _(
            "Adjacent: {adjacent}. Blackout: {blackout}."
        ).format(
            adjacent=", ".join(HOUSE_MAP[state.room]),
            blackout=_("active") if current_blackout else _("off"),
        )
        await self._send_back_to_game_link(state.member)
        map_button = self._build_map_button(current_room=state.room)
        action = await self._choose_action(
            state.member,
            self._build_guest_options(state),
            title=title,
            footer=footer,
            extra_items=[map_button],
        )
        return state.member.id, action

    async def _prompt_killer_action(self) -> tuple[int, dict]:
        title = _(
            "Murder House - Round {round}\n"
            "You are the murderer.\n"
            "Current room: {room}\n"
            "Alive guests: {count}\n"
            "Exits: {exits}\n"
            "Power cooldown: {cooldown}"
        ).format(
            round=self.round,
            room=self.killer_room,
            count=len(self._alive_guest_states()),
            exits=self._compact_escape_status_text(),
            cooldown=max(0, self.power_cooldown),
        )
        await self._send_back_to_game_link(self.killer)
        map_button = self._build_map_button(current_room=self.killer_room)
        action = await self._choose_action(
            self.killer,
            self._build_killer_options(),
            title=title,
            extra_items=[map_button],
        )
        return self.killer.id, action

    def _kill_guest(
        self,
        state: GuestState,
        *,
        public_text: str,
        private_lines: defaultdict[int, list[str]],
        victim_text: str,
        killer_text: str | None = None,
    ) -> bool:
        if not state.alive or state.escaped:
            return False
        state.alive = False
        state.hidden_spot = None
        self.casualties.append(public_text)
        private_lines[state.member.id].append(victim_text)
        if killer_text is not None:
            private_lines[self.killer.id].append(killer_text)
        return True

    def _resolve_scavenge(
        self,
        state: GuestState,
        *,
        public_lines: list[str],
        private_lines: defaultdict[int, list[str]],
    ) -> None:
        stash = self.room_stashes.get(state.room, [])
        found = stash.pop(0) if stash else "junk"

        if found == "clue":
            if self.escape_progress < self.escape_goal:
                self.escape_progress += 1
                clue_text = self.escape_clue_queue[
                    min(self.escape_progress - 1, len(self.escape_clue_queue) - 1)
                ]
                private_lines[state.member.id].append(
                    _("You uncover **{clue}**.").format(clue=clue_text)
                )
                public_lines.append(
                    _("Someone finds another way out. Escape progress is now **{found}/{goal}**.").format(
                        found=self.escape_progress,
                        goal=self.escape_goal,
                    )
                )
                if self.escape_progress >= self.escape_goal:
                    self._unlock_primary_escape(public_lines)
            else:
                private_lines[state.member.id].append(
                    _("You find an old clue, but the escape route is already known.")
                )
            return

        if found == ITEM_FLASHLIGHT:
            state.inventory.append(ITEM_FLASHLIGHT)
            private_lines[state.member.id].append(
                _("You find a **Flashlight**. It can fully check one nearby room.")
            )
            return

        if found == ITEM_NOISEMAKER:
            state.inventory.append(ITEM_NOISEMAKER)
            private_lines[state.member.id].append(
                _("You find a **Noisemaker**. It can fake noise in a room next round.")
            )
            return

        private_lines[state.member.id].append(random.choice(JUNK_DISCOVERIES[state.room]))

    def _consume_barricade(
        self,
        room: str,
        *,
        public_lines: list[str],
        private_lines: defaultdict[int, list[str]],
    ) -> bool:
        if room not in self.barricades:
            return False
        self.barricades.pop(room, None)
        public_lines.append(
            _("A barricade in the **{room}** explodes apart and buys the houseguests a moment.").format(
                room=room
            )
        )
        private_lines[self.killer.id].append(
            _("A barricade in the **{room}** eats your kill window.").format(room=room)
        )
        return True

    def _resolve_sweep(
        self,
        room: str,
        *,
        public_lines: list[str],
        private_lines: defaultdict[int, list[str]],
    ) -> None:
        if self._consume_barricade(
            room, public_lines=public_lines, private_lines=private_lines
        ):
            return

        occupants = self._room_states(room)
        exposed = [state for state in occupants if state.hidden_spot is None]
        hidden = [state for state in occupants if state.hidden_spot is not None]

        if exposed:
            priority = [state for state in exposed if state.room == FOYER]
            victim = random.choice(priority or exposed)
            public_text = self._flavored_death_text(
                mode="sweep",
                victim=victim.member,
                room=room,
            )
            if self._kill_guest(
                victim,
                public_text=public_text,
                private_lines=private_lines,
                victim_text=_("You are found in the **{room}** and killed.").format(
                    room=room
                ),
                killer_text=_("You catch **{victim}** exposed in the **{room}**.").format(
                    victim=victim.member.display_name,
                    room=room,
                ),
            ):
                public_lines.append(public_text)
            return

        if hidden:
            hidden_spots = sorted(
                {
                    state.hidden_spot
                    for state in hidden
                    if state.hidden_spot is not None
                }
            )
            if hidden_spots:
                hint_count = 1 if len(hidden_spots) == 1 else min(2, len(hidden_spots))
                hint_spots = (
                    hidden_spots
                    if len(hidden_spots) <= hint_count
                    else random.sample(hidden_spots, hint_count)
                )
                hint_display = nice_join([f"`{spot}`" for spot in hint_spots])
                private_lines[self.killer.id].append(
                    _("You hear movement near {spots} in the **{room}**.").format(
                        spots=hint_display, room=room
                    )
                )
            public_lines.append(
                _("The **{room}** is torn apart, but nobody is dragged into the open.").format(
                    room=room
                )
            )
            return

        public_lines.append(
            _("The **{room}** is shredded, but it was empty.").format(room=room)
        )

    def _resolve_killer_action(
        self,
        action: dict,
        *,
        public_lines: list[str],
        private_lines: defaultdict[int, list[str]],
        noise_by_room: dict[str, int],
    ) -> None:
        kind = action["kind"]
        current_room = self.killer_room

        if kind == "move":
            self.killer_room = action["room"]
            private_lines[self.killer.id].append(
                _("You move quietly into the **{room}**.").format(room=self.killer_room)
            )
            public_lines.append(_("Slow footsteps change direction somewhere in the house."))
            return

        if kind == "storm":
            self.killer_room = action["room"]
            public_lines.append(
                _("The murderer storms into the **{room}**.").format(room=self.killer_room)
            )
            private_lines[self.killer.id].append(
                _("You crash into the **{room}** and start sweeping it.").format(
                    room=self.killer_room
                )
            )
            self._resolve_sweep(
                self.killer_room,
                public_lines=public_lines,
                private_lines=private_lines,
            )
            return

        if kind == "sweep":
            private_lines[self.killer.id].append(
                _("You sweep the **{room}**.").format(room=current_room)
            )
            self._resolve_sweep(
                current_room,
                public_lines=public_lines,
                private_lines=private_lines,
            )
            return

        if kind == "check":
            spot = action["spot"]
            if self._consume_barricade(
                current_room, public_lines=public_lines, private_lines=private_lines
            ):
                return
            victims = [
                state
                for state in self._room_states(current_room)
                if state.hidden_spot == spot
            ]
            if victims:
                victim = random.choice(victims)
                public_text = self._flavored_death_text(
                    mode="check",
                    victim=victim.member,
                    room=current_room,
                    spot=spot,
                )
                if self._kill_guest(
                    victim,
                    public_text=public_text,
                    private_lines=private_lines,
                    victim_text=_(
                        "The murderer checks the **{spot}** and finds you."
                    ).format(spot=spot),
                    killer_text=_(
                        "You check the **{spot}** in the **{room}** and kill **{victim}**."
                    ).format(
                        spot=spot,
                        room=current_room,
                        victim=victim.member.display_name,
                    ),
                ):
                    public_lines.append(public_text)
            else:
                public_lines.append(
                    _(
                        "A violent scrape comes from the **{spot}** in the **{room}**, but nobody screams."
                    ).format(spot=spot, room=current_room)
                )
                private_lines[self.killer.id].append(
                    _("The **{spot}** in the **{room}** is empty.").format(
                        spot=spot, room=current_room
                    )
                )
            return

        if kind == "trap":
            spot = action["spot"]
            self.traps[(current_room, spot)] = self.round + 2
            private_lines[self.killer.id].append(
                _("You rig the **{spot}** in the **{room}**.").format(
                    spot=spot, room=current_room
                )
            )
            public_lines.append(_("A metallic click echoes through the house."))
            return

        if kind == "listen":
            if self._in_final_chase():
                last_survivors = self._alive_guest_states()
                if last_survivors:
                    private_lines[self.killer.id].append(
                        _("Final Chase narrows to the **{room}**.").format(
                            room=last_survivors[0].room
                        )
                    )
                public_lines.append(_("The murderer stops moving and listens."))
                return

            loud_rooms = [
                room
                for room, score in noise_by_room.items()
                if score > 0 and room != current_room
            ]
            if loud_rooms:
                ordered = sorted(
                    loud_rooms,
                    key=lambda room: noise_by_room[room],
                    reverse=True,
                )
                revealed = ordered[:2]
                private_lines[self.killer.id].append(
                    _("The loudest rooms are {rooms}.").format(
                        rooms=nice_join([f"**{room}**" for room in revealed])
                    )
                )
            else:
                private_lines[self.killer.id].append(
                    _("The house holds its breath. No room gives anything away.")
                )
            active_exit_rooms = [
                room
                for room in self._open_escape_rooms()
                if noise_by_room.get(room, 0) > 0 or self._room_states(room)
            ]
            if active_exit_rooms:
                private_lines[self.killer.id].append(
                    _("You catch activity around the open exit(s): {rooms}.").format(
                        rooms=nice_join([f"**{room}**" for room in active_exit_rooms])
                    )
                )
            public_lines.append(_("The murderer stops moving and listens."))
            return

        if kind == "cut_power":
            self.blackout_rounds = max(self.blackout_rounds, 1)
            self.power_cooldown = self.CUT_POWER_COOLDOWN
            public_lines.append(
                _("The breaker dies with a hard snap. Next round is a blackout.")
            )
            private_lines[self.killer.id].append(
                _("You kill the breaker. The next round will be dark.")
            )

    async def _send_private_round_summaries(
        self, private_lines: defaultdict[int, list[str]]
    ) -> None:
        tasks = []
        for state in self.guests.values():
            lines = list(private_lines[state.member.id])
            if state.escaped:
                lines.append(_("You made it out of the house alive."))
            elif state.alive:
                lines.append(_("You end the round in the **{room}**.").format(room=state.room))
                if state.room in self.barricades:
                    lines.append(_("A barricade is still holding in your room."))
                lines.append(
                    _("Inventory: **{items}**.").format(
                        items=self._inventory_text(state)
                    )
                )
                lines.append(
                    _("Escape clues found: **{found}/{goal}**.").format(
                        found=self.escape_progress,
                        goal=self.escape_goal,
                    )
                )
                lines.append(
                    _("Exit status: {exits}.").format(exits=self._escape_status_text())
                )
            if lines:
                tasks.append(self._safe_send_dm(state.member, "\n".join(lines)))

        killer_lines = list(private_lines[self.killer.id])
        killer_lines.append(_("You end the round in the **{room}**.").format(room=self.killer_room))
        killer_lines.append(
            _("Alive houseguests remaining: **{count}**.").format(
                count=len(self._alive_guest_states())
            )
        )
        if self.traps:
            trap_labels = [
                f"{room} / {spot}" for (room, spot), _expiry in self.traps.items()
            ]
            killer_lines.append(
                _("Active traps: {traps}.").format(traps=", ".join(trap_labels))
            )
        if self.barricades:
            killer_lines.append(
                _("Barricaded rooms: {rooms}.").format(
                    rooms=", ".join(sorted(self.barricades))
                )
            )
        tasks.append(self._safe_send_dm(self.killer, "\n".join(killer_lines)))
        await asyncio.gather(*tasks)

    def _resolve_escape_attempts(
        self,
        escape_attempt_ids: set[int],
        *,
        public_lines: list[str],
        private_lines: defaultdict[int, list[str]],
    ) -> None:
        for member_id in list(escape_attempt_ids):
            state = self.guests.get(member_id)
            if state is None or not state.alive or state.escaped:
                continue
            if state.room not in self._open_escape_rooms():
                continue
            route = self._escape_route_label(state.room)
            state.escaped = True
            state.escape_route = route
            self.escaped_members.append(state.member)
            public_lines.append(
                _("**{player}** bursts out through the {route}! (**{count} escaped**)").format(
                    player=state.member.display_name,
                    route=route.lower(),
                    count=len(self.escaped_members),
                )
            )
            private_lines[state.member.id].append(
                _("You force open the {route} and make it out.").format(
                    route=route.lower()
                )
            )

    def _top_noise_line(self, noise_by_room: dict[str, int]) -> str | None:
        loud_rooms = [room for room, score in noise_by_room.items() if score >= 2]
        if not loud_rooms:
            return None
        sample_count = min(2, len(loud_rooms))
        chosen = (
            loud_rooms
            if len(loud_rooms) <= sample_count
            else random.sample(loud_rooms, sample_count)
        )
        return _("Noise ripples through the {rooms}.").format(
            rooms=nice_join([f"**{room}**" for room in chosen])
        )

    async def _run_round(self) -> None:
        self._cleanup_expired_traps()
        current_blackout = self.blackout_rounds > 0
        public_lines = [
            random.choice(BLACKOUT_LINES if current_blackout else AMBIENCE_LINES)
        ]
        self._maybe_open_secondary_escape(public_lines)
        if self._in_final_chase():
            self._start_final_chase(public_lines)
        private_lines: defaultdict[int, list[str]] = defaultdict(list)
        noise_by_room: dict[str, int] = {room: 0 for room in HOUSE_MAP}
        escape_attempt_ids: set[int] = set()
        pending_senses: list[tuple[int, str, bool]] = []

        for state in self._alive_guest_states():
            state.hidden_spot = None

        choose_tasks = [
            self._prompt_guest_action(state, current_blackout=current_blackout)
            for state in self._alive_guest_states()
        ]
        choose_tasks.append(self._prompt_killer_action())
        chosen_pairs = await asyncio.gather(*choose_tasks)
        actions = {member_id: action for member_id, action in chosen_pairs}

        guest_states = random.shuffle(self._alive_guest_states())
        for state in guest_states:
            if not state.alive:
                continue
            action = actions.get(state.member.id)
            if action is None:
                continue

            kind = action["kind"]
            if kind == "move":
                state.room = action["room"]
                noise_by_room[state.room] += self._movement_noise()
                private_lines[state.member.id].append(
                    _("You sneak into the **{room}**.").format(room=state.room)
                )
                continue

            if kind == "hide":
                spot = action["spot"]
                trap_key = (state.room, spot)
                if trap_key in self.traps:
                    del self.traps[trap_key]
                    public_text = self._flavored_death_text(
                        mode="trap",
                        victim=state.member,
                        room=state.room,
                        spot=spot,
                    )
                    if self._kill_guest(
                        state,
                        public_text=public_text,
                        private_lines=private_lines,
                        victim_text=_(
                            "You hide in the **{spot}**, and a trap kills you instantly."
                        ).format(spot=spot),
                        killer_text=_(
                            "Your trap in the **{room}** claims **{victim}**."
                        ).format(room=state.room, victim=state.member.display_name),
                    ):
                        public_lines.append(public_text)
                    continue

                state.hidden_spot = spot
                private_lines[state.member.id].append(
                    _("You keep still in the **{spot}**.").format(spot=spot)
                )
                continue

            if kind == "scavenge":
                noise_by_room[state.room] += self._activity_noise()
                self._resolve_scavenge(
                    state,
                    public_lines=public_lines,
                    private_lines=private_lines,
                )
                continue

            if kind == "barricade":
                self.barricades[state.room] = self.round + 1
                noise_by_room[state.room] += 1
                private_lines[state.member.id].append(
                    _("You drag furniture into place and barricade the **{room}**.").format(
                        room=state.room
                    )
                )
                public_lines.append(_("Heavy furniture scrapes somewhere in the house."))
                continue

            if kind == "peek":
                noise_by_room[state.room] += 1
                pending_senses.append((state.member.id, action["room"], False))
                private_lines[state.member.id].append(
                    _("You watch the doorway toward the **{room}**.").format(
                        room=action["room"]
                    )
                )
                continue

            if kind == "flashlight":
                state.inventory.remove(ITEM_FLASHLIGHT)
                pending_senses.append((state.member.id, action["room"], True))
                private_lines[state.member.id].append(
                    _("You use your flashlight on the **{room}**.").format(
                        room=action["room"]
                    )
                )
                continue

            if kind == "noisemaker":
                state.inventory.remove(ITEM_NOISEMAKER)
                noise_by_room[action["room"]] += 3
                private_lines[state.member.id].append(
                    _("You plant a noisemaker in the **{room}**.").format(
                        room=action["room"]
                    )
                )
                continue

            if kind == "escape":
                noise_by_room[state.room] += 3
                escape_attempt_ids.add(state.member.id)
                private_lines[state.member.id].append(
                    _("You commit to the {route} and pray the path stays clear.").format(
                        route=self._escape_route_label(state.room).lower()
                    )
                )

        for member_id, target_room, strong in pending_senses:
            state = self.guests.get(member_id)
            if state is None or not state.alive or state.escaped:
                continue
            private_lines[member_id].append(
                self._sense_room(
                    target_room,
                    strong=strong,
                    current_blackout=current_blackout,
                    noise_by_room=noise_by_room,
                    viewer_id=member_id,
                )
            )

        killer_action = actions[self.killer.id]
        self._resolve_killer_action(
            killer_action,
            public_lines=public_lines,
            private_lines=private_lines,
            noise_by_room=noise_by_room,
        )

        self._resolve_escape_attempts(
            escape_attempt_ids,
            public_lines=public_lines,
            private_lines=private_lines,
        )

        noise_line = self._top_noise_line(noise_by_room)
        if noise_line is not None:
            public_lines.append(noise_line)

        await self._send_private_round_summaries(private_lines)
        await self.ctx.send(embed=self._build_round_embed(public_lines))

        if current_blackout and self.blackout_rounds > 0:
            self.blackout_rounds -= 1
        if self.power_cooldown > 0:
            self.power_cooldown -= 1

    async def run(self) -> None:
        await self.ctx.send(embed=self._build_intro_embed())
        await self._send_opening_dms()

        while True:
            if not self._alive_guest_states():
                break

            await self.ctx.send(
                (
                    _(
                        "Round **{round}** begins. Check your DMs and make your choice."
                    )
                    if not self._in_final_chase()
                    else _(
                        "Round **{round}** begins. **Final Chase** is active. Check your DMs and run."
                    )
                ).format(round=self.round)
            )
            await self._run_round()
            if not self._alive_guest_states():
                break
            self.round += 1
            await asyncio.sleep(self.REPORT_DELAY_SECONDS)

        await self.ctx.send(embed=self._build_final_embed())


class MurderHouse(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.games: dict[int, MurderHouseGame | str] = {}
        self._testpillow_background: Image.Image | None = None
        self._testpillow_bg_lock = asyncio.Lock()

    async def _send_crash_traceback(self, ctx, exc: Exception) -> None:
        header = _("Murder House crashed:")
        traceback_text = "".join(
            traceback.format_exception(type(exc), exc, exc.__traceback__)
        ).rstrip()
        max_payload = 1900
        for index in range(0, len(traceback_text), max_payload):
            chunk = traceback_text[index : index + max_payload]
            prefix = f"{header}\n" if index == 0 else ""
            await ctx.send(f"{prefix}```py\n{chunk}\n```")

    def _parse_testpillow_ids(self, raw_user_ids: str) -> list[int]:
        tokens = [
            token for token in re.split(r"[,\s]+", raw_user_ids.strip()) if token
        ]
        if not tokens:
            raise ValueError("empty")

        unique_ids: list[int] = []
        seen: set[int] = set()
        for token in tokens:
            match = re.fullmatch(r"<@!?(\d+)>|(\d+)", token)
            if match is None:
                raise ValueError("invalid")
            user_id = int(match.group(1) or match.group(2))
            if user_id in seen:
                continue
            seen.add(user_id)
            unique_ids.append(user_id)
        if len(unique_ids) > 10:
            raise ValueError("too_many")
        return unique_ids

    async def _load_testpillow_background(self) -> Image.Image:
        if self._testpillow_background is not None:
            return self._testpillow_background.copy()

        async with self._testpillow_bg_lock:
            if self._testpillow_background is None:
                session = getattr(self.bot, "trusted_session", None) or self.bot.session
                async with session.get(TESTPILLOW_BG_URL) as resp:
                    resp.raise_for_status()
                    data = await resp.read()
                with Image.open(BytesIO(data)) as source:
                    self._testpillow_background = source.convert("RGBA")

        return self._testpillow_background.copy()

    async def _fetch_testpillow_user(
        self, user_id: int
    ) -> discord.User | discord.Member | None:
        user = self.bot.get_user(user_id)
        if user is not None:
            return user
        user = discord.utils.get(self.bot.get_all_members(), id=user_id)
        if user is not None:
            return user
        try:
            return await self.bot.fetch_user(user_id)
        except (discord.NotFound, discord.HTTPException):
            return None

    async def _fetch_testpillow_avatar(
        self, user: discord.abc.User, *, size: int
    ) -> Image.Image:
        asset = user.display_avatar
        try:
            avatar_url = asset.replace(format="png", size=max(128, size * 2)).url
        except Exception:
            avatar_url = asset.url

        session = getattr(self.bot, "trusted_session", None) or self.bot.session
        async with session.get(avatar_url) as resp:
            resp.raise_for_status()
            data = await resp.read()

        with Image.open(BytesIO(data)) as source:
            return source.convert("RGBA")

    def _testpillow_layout(
        self, room_key: str, count: int
    ) -> tuple[int, list[tuple[int, int]]]:
        rect = TESTPILLOW_ROOM_COORDS[room_key]
        padding = 10
        best: tuple[int, int, int, int] | None = None

        # Pick the densest grid that still keeps every avatar cleanly inside the room.
        for cols in range(1, count + 1):
            rows = math.ceil(count / cols)
            gap = 8
            usable_w = rect["w"] - (padding * 2) - (gap * (cols - 1))
            usable_h = rect["h"] - (padding * 2) - (gap * (rows - 1))
            if usable_w <= 0 or usable_h <= 0:
                continue
            size = min(usable_w // cols, usable_h // rows)
            if size <= 0:
                continue
            if best is None or size > best[0]:
                best = (size, cols, rows, gap)

        if best is None:
            size = max(24, min(rect["w"], rect["h"]) - (padding * 2))
            cols = 1
            rows = count
            gap = 6
        else:
            size, cols, rows, gap = best

        grid_w = cols * size + (cols - 1) * gap
        grid_h = rows * size + (rows - 1) * gap
        start_x = rect["x"] + max(0, (rect["w"] - grid_w) // 2)
        start_y = rect["y"] + max(0, (rect["h"] - grid_h) // 2)

        positions = []
        for index in range(count):
            row = index // cols
            col = index % cols
            positions.append(
                (start_x + col * (size + gap), start_y + row * (size + gap))
            )
        return size, positions

    def _style_testpillow_avatar(
        self,
        avatar: Image.Image,
        *,
        size: int,
        is_murderer: bool,
        is_dead: bool,
    ) -> Image.Image:
        avatar = ImageOps.fit(avatar.convert("RGBA"), (size, size), method=PIL_RESAMPLE)
        if is_dead:
            avatar = ImageOps.grayscale(avatar).convert("RGBA")
            alpha = avatar.getchannel("A").point(lambda value: int(value * 0.58))
            avatar.putalpha(alpha)

        mask = Image.new("L", (size, size), 0)
        ImageDraw.Draw(mask).ellipse((0, 0, size - 1, size - 1), fill=255)

        circular = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        circular.paste(avatar, (0, 0), mask)

        outline = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        outline_draw = ImageDraw.Draw(outline)
        outline_width = max(2, size // 16)
        outline_draw.ellipse(
            (outline_width // 2, outline_width // 2, size - 1 - outline_width // 2, size - 1 - outline_width // 2),
            outline=(245, 245, 245, 240),
            width=outline_width,
        )
        if is_murderer:
            red_width = max(3, size // 10)
            inset = outline_width + 1
            outline_draw.ellipse(
                (inset, inset, size - 1 - inset, size - 1 - inset),
                outline=(220, 40, 40, 255),
                width=red_width,
            )
            red_overlay = Image.new("RGBA", (size, size), (150, 10, 10, 45))
            circular = Image.composite(red_overlay, circular, mask)

        return Image.alpha_composite(circular, outline)

    async def _render_testpillow_overlay(
        self,
        *,
        users: list[discord.abc.User],
        murderer_id: int,
        dead_ids: set[int],
        room_assignments: dict[int, str],
    ) -> BytesIO:
        canvas = await self._load_testpillow_background()
        grouped: dict[str, list[discord.abc.User]] = defaultdict(list)
        for user in users:
            grouped[room_assignments[user.id]].append(user)

        async def load_avatar(user: discord.abc.User) -> Image.Image:
            try:
                return await self._fetch_testpillow_avatar(user, size=256)
            except Exception:
                return Image.new("RGBA", (256, 256), (90, 90, 90, 255))

        avatar_images = await asyncio.gather(
            *(load_avatar(user) for user in users)
        )
        avatar_map = {user.id: image for user, image in zip(users, avatar_images)}

        for room_key, room_users in grouped.items():
            size, positions = self._testpillow_layout(room_key, len(room_users))
            for user, (x, y) in zip(room_users, positions):
                styled = self._style_testpillow_avatar(
                    avatar_map[user.id],
                    size=size,
                    is_murderer=user.id == murderer_id,
                    is_dead=user.id in dead_ids,
                )
                canvas.alpha_composite(styled, (x, y))

        output = BytesIO()
        canvas.save(output, format="PNG")
        output.seek(0)
        return output

    def _build_tutorial_embed(self, ctx) -> discord.Embed:
        prefix = ctx.clean_prefix
        return (
            discord.Embed(
                title=_("Murder House Tutorial"),
                description=_(
                    "A fast guide to the mode. One player is the murderer; everyone else is trapped in the house."
                ),
                colour=self.bot.config.game.primary_colour,
            )
            .add_field(
                name=_("Houseguest Goal"),
                value=_(
                    "Find **escape clues**, survive the sweeps, and get out. There are **4** possible exits, but only **2** will open in a game, and anyone who reaches one escapes."
                ),
                inline=False,
            )
            .add_field(
                name=_("Murderer Goal"),
                value=_(
                    "Stop the escapes. Sweep rooms, check specific hiding spots, listen for noise, trap likely hiding places, and kill whoever does not make it out."
                ),
                inline=False,
            )
            .add_field(
                name=_("Houseguest Basics"),
                value=_(
                    "`Search` finds clues or items.\n"
                    "`Hide` protects you unless the murderer checks that exact spot.\n"
                    "`Peek` and `Flashlight` gather information.\n"
                    "`Barricade` can burn the murderer's next kill window in that room.\n"
                    "`Escape` only works from open exit rooms.\n"
                    "Each room holds at most **1** clue.\n"
                    "The first chosen exit opens when the clue track fills; the second opens **{delay} rounds later**.\n"
                    "If only one houseguest remains before the clue track fills, **Final Chase** opens both selected exits and removes hiding, searching, and barricading."
                ).format(delay=MurderHouseGame.SECONDARY_EXIT_DELAY_ROUNDS),
                inline=False,
            )
            .add_field(
                name=_("Murderer Basics"),
                value=_(
                    "`Sweep` kills exposed targets in a room.\n"
                    "`Check` kills someone in one exact hiding spot.\n"
                    "`Listen` finds loud rooms, active exits, and the last survivor during Final Chase.\n"
                    "`Trap` punishes predictable hiding.\n"
                    "`Cut power` makes the next round harder to read."
                ),
                inline=False,
            )
            .add_field(
                name=_("First-Game Tips"),
                value=_(
                    "Possible exits: **Kitchen back door**, **Basement bulkhead**, **Attic fire ladder**, **Master bedroom balcony**.\n"
                    "Houseguests: spread out early, because rooms do not stack clues anymore.\n"
                    "Pivot fast once the first exit is revealed.\n"
                    "If you are the last one left before the clues are done, **Final Chase** gives you two doors and one clean chance to run.\n"
                    "Anyone who reaches an open exit is out for good.\n"
                    "Murderer: listen for noisy rooms, trap common spots, and control the live exit while reading the setup for the delayed one.\n"
                    "Use `{prefix}murderhouse 4` to start a lighter-size test match."
                ).format(prefix=prefix),
                inline=False,
            )
        )

    def _format_joined_players(self, joined: set) -> str:
        if not joined:
            return _("None yet")
        sorted_joined = sorted(
            joined,
            key=lambda user: getattr(user, "display_name", str(user)).casefold(),
        )
        preview_limit = 20
        preview = ", ".join(user.mention for user in sorted_joined[:preview_limit])
        extra = len(sorted_joined) - preview_limit
        if extra > 0:
            return _("{players}, and {extra} more").format(players=preview, extra=extra)
        return preview

    async def _parse_murderhouse_setup(
        self, ctx, setup_tokens: tuple[str, ...]
    ) -> tuple[int, discord.Member | None]:
        min_players = 4
        forced_killer = None
        tokens = list(setup_tokens)

        if tokens and tokens[0].isdigit():
            min_players = int(tokens.pop(0))

        if tokens:
            member_query = " ".join(tokens).strip()
            forced_killer = await commands.MemberConverter().convert(ctx, member_query)

        return min_players, forced_killer

    def _build_lobby_embed(
        self,
        *,
        author: discord.Member,
        min_players: int,
        seconds_left: int,
        joined: set,
        prefix: str,
    ) -> discord.Embed:
        minutes, seconds = divmod(max(0, seconds_left), 60)
        timer = f"{minutes:02d}:{seconds:02d}"
        joined_text = self._format_joined_players(joined)
        description = _(
            "**{author}** opened the doors to **Murder House**.\n"
            "One player becomes the murderer. Everyone else searches rooms, hides, and tries to escape.\n"
            "There are **4** possible exits. One opens after the final clue, and another opens **{delay} rounds later**.\n"
            "If only one houseguest remains before the clue track is complete, **Final Chase** opens both selected exits.\n"
            "⏳ Starts in **{timer}**.\n"
            "**Minimum of {min_players} players are required.**\n"
            "👥 Joined ({count}): {players}\n"
            "Use **Join** to play or **Leave** to spectate before the timer ends."
        ).format(
            author=author.mention,
            timer=timer,
            delay=MurderHouseGame.SECONDARY_EXIT_DELAY_ROUNDS,
            min_players=min_players,
            count=len(joined),
            players=joined_text,
        )
        return discord.Embed(
            title=_("Murder House Lobby"),
            description=description,
            colour=self.bot.config.game.primary_colour,
        ).set_author(name=str(author), icon_url=author.display_avatar.url).add_field(
            name=_("Need Help?"),
            value=_("Use `{prefix}murderhouse tutorial` for a quick role guide.").format(
                prefix=prefix
            ),
            inline=False,
        )

    async def _run_lobby_countdown(
        self,
        *,
        message: discord.Message,
        view: MurderHouseJoinView,
        author: discord.Member,
        min_players: int,
        duration_seconds: int,
        clean_prefix: str,
        ends_at: float,
    ) -> None:
        update_interval = 5
        while not view.is_finished():
            remaining = max(0, math.ceil(ends_at - asyncio.get_running_loop().time()))
            if remaining <= 0:
                break
            wait_for = min(update_interval, remaining)
            await asyncio.sleep(wait_for)
            await self._refresh_lobby_message(
                message=message,
                view=view,
                author=author,
                min_players=min_players,
                clean_prefix=clean_prefix,
                ends_at=ends_at,
            )
        view.stop()

    async def _refresh_lobby_message(
        self,
        *,
        message: discord.Message,
        view: MurderHouseJoinView,
        author: discord.Member,
        min_players: int,
        clean_prefix: str,
        ends_at: float,
    ) -> None:
        seconds_left = max(0, math.ceil(ends_at - asyncio.get_running_loop().time()))
        try:
            await message.edit(
                embed=self._build_lobby_embed(
                    author=author,
                    min_players=min_players,
                    seconds_left=seconds_left,
                    joined=view.joined,
                    prefix=clean_prefix,
                ),
                view=view,
            )
        except discord.NotFound:
            return
        except discord.HTTPException:
            return

    @commands.group(
        invoke_without_command=True,
        case_insensitive=True,
        aliases=["mh"],
        brief=_("Play Murder House"),
    )
    @locale_doc
    async def murderhouse(self, ctx, *setup_tokens: str):
        _(
            """Starts a round of Murder House.

            One joined player becomes the murderer.
            Everyone else is trapped inside a creaking house and must search rooms, hide in specific spots, and escape through the house's exits before the murderer catches them.
            Hidden actions happen in DMs, while the channel sees dramatic public recaps.

            Usage:
            `{prefix}murderhouse`
            `{prefix}murderhouse 5`
            `{prefix}murderhouse @user`
            `{prefix}murderhouse 5 @user`
            `{prefix}murderhouse tutorial`

            Notes:
            - The command starter is not auto-joined.
            - Minimum players cannot be lower than 4.
            - The required clue count scales up with player count.
            - A room can hold at most 1 clue.
            - You can force a specific joined player to be the murderer.
            - There are 4 possible exits, but only 2 open in a game.
            - The first exit opens after the final clue; the second opens 4 rounds later.
            - If only one houseguest remains before the clues are done, Final Chase opens both selected exits.
            - Hiding out the clock does not count as a win.
            - The game only ends when everyone inside is either dead or escaped."""
        )
        try:
            min_players, forced_killer = await self._parse_murderhouse_setup(
                ctx, setup_tokens
            )
        except commands.BadArgument:
            return await ctx.send(
                _(
                    "I couldn't find that player. Use `{prefix}murderhouse 5 @user` or `{prefix}murderhouse @user`."
                ).format(prefix=ctx.clean_prefix)
            )

        if self.games.get(ctx.channel.id):
            return await ctx.send(_("There is already a game in here!"))

        if min_players < 4:
            return await ctx.send(_("Murder House needs at least 4 players."))

        self.games[ctx.channel.id] = "forming"
        join_timeout = MurderHouseGame.JOIN_TIMEOUT_SECONDS
        lobby_ends_at = asyncio.get_running_loop().time() + join_timeout
        view = MurderHouseJoinView(
            Button(style=ButtonStyle.primary, label=_("Join the Murder House game!")),
            message=_("You joined Murder House."),
            leave_message=_("You left Murder House."),
            timeout=join_timeout,
        )

        try:
            lobby_message = await ctx.send(
                embed=self._build_lobby_embed(
                    author=ctx.author,
                    min_players=min_players,
                    seconds_left=join_timeout,
                    joined=view.joined,
                    prefix=ctx.clean_prefix,
                ),
                view=view,
            )
        except discord.Forbidden:
            del self.games[ctx.channel.id]
            await ctx.send(
                _(
                    "An error happened during Murder House. Missing permission: `Embed Links`."
                )
            )
            return

        async def refresh_lobby() -> None:
            await self._refresh_lobby_message(
                message=lobby_message,
                view=view,
                author=ctx.author,
                min_players=min_players,
                clean_prefix=ctx.clean_prefix,
                ends_at=lobby_ends_at,
            )

        view.refresh_lobby = refresh_lobby

        await self._run_lobby_countdown(
            message=lobby_message,
            view=view,
            author=ctx.author,
            min_players=min_players,
            duration_seconds=join_timeout,
            clean_prefix=ctx.clean_prefix,
            ends_at=lobby_ends_at,
        )
        players = list(view.joined)

        if len(players) < min_players:
            del self.games[ctx.channel.id]
            await self.bot.reset_cooldown(ctx)
            await ctx.send(
                _(
                    "Not enough players joined... Murder House needs at least **{min_players}** players."
                ).format(min_players=min_players)
            )
            return

        if forced_killer is not None:
            forced_player = next(
                (player for player in players if player.id == forced_killer.id),
                None,
            )
            if forced_player is None:
                del self.games[ctx.channel.id]
                await self.bot.reset_cooldown(ctx)
                await ctx.send(
                    _(
                        "**{player}** was picked as the murderer, but they never joined the lobby."
                    ).format(player=forced_killer.display_name)
                )
                return
        else:
            forced_player = None

        try:
            game = MurderHouseGame(ctx, players, forced_killer=forced_player)
            self.games[ctx.channel.id] = game
            await game.run()
        except Exception as exc:
            await self._send_crash_traceback(ctx, exc)
        finally:
            self.games.pop(ctx.channel.id, None)

    @murderhouse.command(
        aliases=["guide", "howto"],
        brief=_("View how to play Murder House"),
    )
    @locale_doc
    async def tutorial(self, ctx):
        _(
            """View a lightweight guide to Murder House.

            Usage:
            `{prefix}murderhouse tutorial`

            Shows the core goals, main actions, and quick tips for both houseguests and the murderer."""
        )
        await ctx.send(embed=self._build_tutorial_embed(ctx))

    @murderhouse.command(
        name="pillow",
        aliases=["testpillow"],
        brief=_("Render a Murder House spectator test map"),
        hidden=True,
    )
    @locale_doc
    async def pillow(self, ctx, *, user_ids: str):
        _(
            """Render a Murder House spectator test map.

            Usage:
            `{prefix}murderhouse pillow 123456789012345678, 234567890123456789`

            Provide up to 10 user IDs or mentions. The command picks one random murderer,
            marks a couple of houseguests dead, scatters everyone into random rooms,
            and renders a spectator overlay on the mansion map."""
        )

        try:
            parsed_ids = self._parse_testpillow_ids(user_ids)
        except ValueError as exc:
            if str(exc) == "empty":
                return await ctx.send(_("Give me at least one user ID to render."))
            if str(exc) == "too_many":
                return await ctx.send(
                    _("Use up to **10** unique user IDs for the test map.")
                )
            return await ctx.send(
                _("Use raw user IDs or mentions separated by commas or spaces.")
            )

        async with ctx.typing():
            users: list[discord.abc.User] = []
            missing_ids: list[str] = []
            for user_id in parsed_ids:
                user = await self._fetch_testpillow_user(user_id)
                if user is None:
                    missing_ids.append(str(user_id))
                    continue
                users.append(user)

            if missing_ids:
                return await ctx.send(
                    _(
                        "I couldn't find these users: {users}"
                    ).format(users=", ".join(missing_ids))
                )

            room_keys = list(TESTPILLOW_ROOM_COORDS.keys())
            murderer = random.choice(users)
            non_murderers = [user for user in users if user.id != murderer.id]
            dead_count = min(2, max(0, len(non_murderers) - 1))
            dead_members = (
                random.sample(non_murderers, dead_count) if dead_count else []
            )
            dead_ids = {user.id for user in dead_members}
            room_assignments = {
                user.id: random.choice(room_keys)
                for user in users
            }

            try:
                image_buffer = await self._render_testpillow_overlay(
                    users=users,
                    murderer_id=murderer.id,
                    dead_ids=dead_ids,
                    room_assignments=room_assignments,
                )
            except Exception as exc:
                await self._send_crash_traceback(ctx, exc)
                return

        alive_members = [
            user
            for user in users
            if user.id != murderer.id and user.id not in dead_ids
        ]

        def describe_user(user: discord.abc.User) -> str:
            display_name = discord.utils.escape_markdown(
                getattr(user, "display_name", str(user))
            )
            room_name = room_assignments[user.id].replace("_", " ").title()
            return f"**{display_name}** ({room_name})"

        def format_people(users_to_format: list[discord.abc.User]) -> str:
            if not users_to_format:
                return _("None")
            return nice_join([describe_user(user) for user in users_to_format])

        await ctx.send(
            "\n".join(
                [
                    _("Murderer: {murderer}").format(
                        murderer=describe_user(murderer)
                    ),
                    _("Dead guests: {dead}").format(
                        dead=format_people(dead_members)
                    ),
                    _("Alive guests: {alive}").format(
                        alive=format_people(alive_members)
                    ),
                ]
            ),
            file=discord.File(image_buffer, filename="murderhouse_test_map.png"),
        )


async def setup(bot):
    await bot.add_cog(MurderHouse(bot))

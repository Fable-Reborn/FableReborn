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


# This is an implementation of Werewolf: The Pact
# The Pact includes the extensions:
# - New Moon
# - The Community
# - Characters
# I have left out the raven and the pyro from "The Community"
# the house part is not my favourite
# The "New Moon" cards are also not included, hence
# the shake and the gypsy are not here
# "Werewolf" is a game by Philippe des Pallières and Hervé Marly
# Thank you for making such an awesome game!
from __future__ import annotations

import asyncio
import datetime
import traceback

from enum import Enum

import discord

from discord.ext import commands

from classes.context import Context
from cogs.help import chunks
from utils import random
from utils.i18n import _


class Role(Enum):
    WEREWOLF = 1
    BIG_BAD_WOLF = 2
    CURSED_WOLF_FATHER = 3
    WOLF_SHAMAN = 4
    WOLF_NECROMANCER = 5

    VILLAGER = 6
    PURE_SOUL = 7
    SEER = 8
    AMOR = 9
    WITCH = 10
    HUNTER = 11
    HEALER = 12
    THE_OLD = 13
    SISTER = 14
    BROTHER = 15
    FOX = 16
    JUDGE = 17
    KNIGHT = 18
    MAID = 19
    CURSED = 20
    THIEF = 21
    PARAGON = 22
    RITUALIST = 23
    TROUBLEMAKER = 24
    LAWYER = 25
    WAR_VETERAN = 26

    WHITE_WOLF = 27
    WOLFHOUND = 28
    RAIDER = 29

    FLUTIST = 30
    SUPERSPREADER = 31
    JESTER = 32
    DOCTOR = 33
    HEAD_HUNTER = 34
    FLOWER_CHILD = 35
    FORTUNE_TELLER = 36
    AURA_SEER = 37
    BODYGUARD = 38
    JUNIOR_WEREWOLF = 39
    WOLF_SEER = 40
    SHERIFF = 41
    JAILER = 42
    MEDIUM = 43
    LOUDMOUTH = 44
    AVENGER = 45


class Side(Enum):
    VILLAGERS = 1
    WOLVES = 2
    WHITE_WOLF = 3
    FLUTIST = 4
    SUPERSPREADER = 5
    JESTER = 6
    HEAD_HUNTER = 7


DESCRIPTIONS = {
    Role.WEREWOLF: _(
        "Your objective is to kill all villagers together with the other Werewolves."
        " Every night, you will get to choose one villager to kill - choose carefully!"
    ),
    Role.BIG_BAD_WOLF: _(
        "Your objective is to kill all villagers together with the other Werewolves."
        " Every night, you will get to choose one villager to kill together with them."
        " After that, you will wake up once more to kill an additional villager, but as"
        " long as no Werewolf has been killed."
    ),
    Role.VILLAGER: _(
        "You are an innocent soul. Your goal is to eradicate all Werewolves that are"
        " haunting the town at nights and survive yourself. At the daily elections,"
        " your voice makes the difference."
    ),
    Role.PURE_SOUL: _(
        "Everyone knows you are not a Werewolf. Your goal is to keep the town safe from"
        " Wolves and kill them all - at the daily elections, many will hear your voice,"
        " they know you will be honest."
    ),
    Role.FLOWER_CHILD: _(
        "You are the Flower Child. Once per game, you can protect one player from"
        " being lynched by the village during the day."
    ),
    Role.SEER: _(
        "You are a villager with the special ability to view someone's identity every"
        " night - but don't tell the villagers too fast, else you will be targeted"
        " yourself."
    ),
    Role.AURA_SEER: _(
        "You are the Aura Seer. Every night, you can inspect one player and learn"
        " whether they have a Good or Evil aura."
    ),
    Role.AMOR: _(
        "You are the personification of the Greek god and get to choose two lovers at"
        " the beginning of the game - they will love each other so much that they will"
        " die once their beloved one bites the dust."
    ),
    Role.WITCH: _(
        "You are a powerful villager with two special brews: One will kill, one will"
        " heal. Use them wisely to influence the game in your favor."
    ),
    Role.HUNTER: _(
        "You are the Hunter. Do your best to protect the Community and your precise"
        " shot will trigger when you die, killing a target of your choice."
    ),
    Role.HEALER: _(
        "You are the Healer. Every night, you can protect one Villager from death to"
        " the Werewolves, but not the same person twice in a row. Make sure the"
        " Villagers stay alive..."
    ),
    Role.DOCTOR: _(
        "You are the Doctor. Every night, you may choose one player to protect from"
        " attack for that night only."
    ),
    Role.BODYGUARD: _(
        "You are the Bodyguard. Every night, you may guard one player from attacks."
        " The first time you intercept an attack (on yourself or your protected"
        " target), you survive. The second time, you die."
    ),
    Role.SHERIFF: _(
        "You are the Sheriff. Every night, you may investigate one player to learn"
        " whether they appear suspicious."
    ),
    Role.JAILER: _(
        "You are the Jailer. During the day, choose one player to jail for the next"
        " night. Jailed players cannot use abilities and are protected from werewolf"
        " attacks that night. Once per game, you may execute your prisoner."
    ),
    Role.MEDIUM: _(
        "You are the Medium. You can communicate with the dead and, once per game,"
        " resurrect one dead player from the Villagers team."
    ),
    Role.LOUDMOUTH: _(
        "You are the Loudmouth. You may select one player at any time. When you die,"
        " that player's role is revealed to everyone."
    ),
    Role.AVENGER: _(
        "You are the Avenger. After the first night, you can mark one player at any"
        " time. If you die, your marked target dies with you."
    ),
    Role.THE_OLD: _(
        "You are the oldest member of the community and the Werewolves have been"
        " hurting you for a long time. All the years have granted you a lot of"
        " resistance - you can survive one attack from the Werewolves. The Village's"
        " Vote, Witch, Hunter, and Avenger will kill you on the first time, and upon"
        " dying, all the other Villagers will lose their special powers and become normal"
        " villagers."
    ),
    Role.SISTER: _(
        "The two sisters know each other very well - together, you might be able to"
        " help the community find the Werewolves and eliminate them."
    ),
    Role.BROTHER: _(
        "The three brothers know each other very well - together, you might be able to"
        " help the community find the Werewolves and eliminate them."
    ),
    Role.FOX: _(
        "You are a clever little guy who can sense the presence of Werewolves. Every"
        " night, you get to choose a group of 3 neighboring players of which you point"
        " the center player and will be told if at least one of them is a Werewolf. If"
        " you do not find a Werewolf, you lose your ability for good."
    ),
    Role.JUDGE: _(
        "You are the Judge. You love the law and can arrange a second daily vote after"
        " the first one by mentioning the secret sign we will agree on later during the"
        " vote. Use it wisely..."
    ),
    Role.KNIGHT: _(
        "You are the Rusty Sword Knight. You will do your best to protect the"
        " Villagers. If you died from the Werewolves, a random Werewolf who caused your"
        " death becomes diseased from your rusty sword and will die the following"
        " night."
    ),
    Role.WHITE_WOLF: _(
        "You are the White Wolf. Your objective is to kill everyone else. Additionally"
        " to the nightly killing spree with the Werewolves, you may kill one of them"
        " later on in the night."
    ),
    Role.THIEF: _("You are the Thief and can choose your identity soon."),
    Role.CURSED: _(
        "You are the Cursed. You are on the Villagers team and appear Good to Aura"
        " checks. If a Werewolf attack targets you, you survive and turn into a"
        " Werewolf instead."
    ),
    Role.WOLFHOUND: _(
        "You are something between a Werewolf and a Villager. Choose your side"
        " wisely..."
    ),
    Role.MAID: _(
        "You are the Maid who raised the children. It would hurt you to see any of them"
        " die - after the daily election, you may take their identity role once."
    ),
    Role.FORTUNE_TELLER: _(
        "You are the Fortune Teller. After the first night, you can give Revelation"
        " Cards to other players at night. Card holders can reveal their own role."
    ),
    Role.FLUTIST: _(
        "You are the Flutist. Your goal is to enchant the players with your music to"
        " take revenge for being expelled many years ago. Every night, you get to"
        " enchant two of them. Gotta catch them all..."
    ),
    Role.CURSED_WOLF_FATHER: _(
        "You are the Cursed Wolf Father that has the ability to spread your curse. Your"
        " objective is to kill all villagers together with the other Werewolves. Every"
        " night, you will get to choose one villager to kill together with them. You"
        " may, once, use your special bite that will curse a villager instead of"
        " killing and devouring them. The cursed villager will then partake each night"
        " in the Werewolves' feast."
    ),
    Role.PARAGON: _(
        "You are the Paragon who has the ability to nullify all other nominations"
        " during the daily election. When you nominate one or more players, only those"
        " players will be voted for during the voting phase removing all other"
        " nominations."
    ),
    Role.RAIDER: _(
        "You're a lone Raider. As a Raider, you can loot a dead player and take their"
        " role as yours. However, only those who were recently lynched and last night's"
        " dead players are available for you to raid."
    ),
    Role.RITUALIST: _(
        "You are the Ritualist who can resurrect a Villager once per game. However,"
        " only those who were recently lynched and last night's dead players are"
        " available for you to resurrect."
    ),
    Role.TROUBLEMAKER: _(
        "You are the Troublemaker of the Village. You can exchange the roles of two"
        " other players on the first night."
    ),
    Role.LAWYER: _(
        "You are the Lawyer who can help the village stop their wrong decisions by"
        " objecting the nomination process and end the day without proceeding to any"
        ' voting phase. Just raise the powerful "Objection!" protest to use your'
        " ability once per game. (The exclamation point is optional.)"
    ),
    Role.WAR_VETERAN: _(
        "You're a War Veteran. Your past warfare has carried you through the duration"
        " of your life. Upon being lynched by the village's vote, you will randomly"
        " kill one of them as a form of your betrayal."
    ),
    Role.WOLF_SHAMAN: _(
        "Your objective is to kill all villagers together with the other Werewolves."
        " Every night, you will get to choose one villager to kill together with them."
        " Additionally, you have the ability to summon an ancient werewolf spirit that"
        " will guard and protect a fellow werewolf to block one death."
    ),
    Role.WOLF_NECROMANCER: _(
        "Your objective is to kill all villagers together with the other Werewolves."
        " Every night, you will get to choose one villager to kill together with them."
        " Since you have learned from your shape-shifting ancestors the magic of"
        " summoning the dead, you have the ability to resurrect a dead werewolf at"
        " night once per game. However, only those who were recently lynched and last"
        " night's dead players are available for you to resurrect."
    ),
    Role.JUNIOR_WEREWOLF: _(
        "Your objective is to kill all villagers together with the other Werewolves."
        " During the day, you mark a villager. If you die (any cause), your latest"
        " marked villager is dragged down with you."
    ),
    Role.WOLF_SEER: _(
        "Your objective is to kill all villagers together with the other Werewolves."
        " Every night, you may inspect one player and learn their role."
    ),
    Role.SUPERSPREADER: _(
        "Your goal is to infect all the players with your virus. Every night, you get"
        " to sneeze and cough on one of them. Each day that passes increases the"
        " players you can infect by one more. Make it Pandemic! (Note: If an infected"
        " player died and is resurrected, they are free from the virus.)"
    ),
    Role.JESTER: _(
        "You are the Jester. Your only objective is to get yourself lynched. If the"
        " village votes to execute you, the game ends immediately and you win."
    ),
    Role.HEAD_HUNTER: _(
        "You are the Head Hunter. You will be assigned a Villager target. Your goal is"
        " to get that target lynched by the Village. If they die by any other means,"
        " you become a Villager."
    ),
}


TRACEBACK_CHUNK_SIZE = 1900
WW_NIGHT_LOCK_CHANNEL_ID = 1458644607893246024
WW_ALIVE_ROLE_ID = 1474617968708161618
WW_DEAD_ROLE_ID = 1474617848071720960


def _format_traceback(exc: BaseException) -> str:
    return "".join(traceback.format_exception(type(exc), exc, exc.__traceback__)).strip()


async def send_traceback(ctx: Context, exc: BaseException) -> None:
    tb_text = _format_traceback(exc) or repr(exc)
    for i in range(0, len(tb_text), TRACEBACK_CHUNK_SIZE):
        chunk = tb_text[i : i + TRACEBACK_CHUNK_SIZE]
        try:
            await ctx.send(f"```py\n{chunk}\n```")
        except Exception:
            print(tb_text)
            break


def schedule_traceback(ctx: Context, exc: BaseException) -> None:
    try:
        asyncio.get_running_loop().create_task(send_traceback(ctx, exc))
    except RuntimeError:
        print(_format_traceback(exc) or repr(exc))


def is_wolf_team_role(role: Role) -> bool:
    return role in {
        Role.WEREWOLF,
        Role.BIG_BAD_WOLF,
        Role.CURSED_WOLF_FATHER,
        Role.WOLF_SHAMAN,
        Role.WOLF_NECROMANCER,
        Role.JUNIOR_WEREWOLF,
        Role.WOLF_SEER,
    }


def is_wolf_aligned_role(role: Role) -> bool:
    return is_wolf_team_role(role) or role == Role.WHITE_WOLF


SPECIAL_WOLF_ROLES = {
    Role.BIG_BAD_WOLF,
    Role.CURSED_WOLF_FATHER,
    Role.WOLF_SHAMAN,
    Role.WOLF_NECROMANCER,
    Role.JUNIOR_WEREWOLF,
    Role.WOLF_SEER,
    Role.WHITE_WOLF,
}

# Mapped from Wolvesville unknown aura categories and nearest equivalents used here.
UNKNOWN_AURA_ROLES = {
    # Village roles that can kill/revive.
    Role.WITCH,
    Role.JAILER,
    Role.MEDIUM,
    Role.RITUALIST,
    Role.HUNTER,
    Role.AVENGER,
    Role.WAR_VETERAN,
    # Solo/ambiguous roles that should not read as plain Good/Evil.
    Role.JESTER,
    Role.HEAD_HUNTER,
    Role.WHITE_WOLF,
    Role.FLUTIST,
    Role.SUPERSPREADER,
    Role.RAIDER,
    Role.THIEF,
    Role.WOLFHOUND,
}


def target_wolf_count_for_players(player_count: int) -> int:
    return max(1, min(6, player_count // 4))


def max_special_wolves_for_player_count(player_count: int) -> int:
    if player_count <= 6:
        return 1
    if player_count <= 9:
        return 2
    if player_count <= 12:
        return 3
    return 4


def cap_special_werewolves(roles: list[Role], requested_players: int) -> list[Role]:
    # Prevent duplicate special wolf roles and enforce a size-based cap.
    special_indices = [idx for idx, role in enumerate(roles) if role in SPECIAL_WOLF_ROLES]
    seen_special_roles: set[Role] = set()
    unique_special_indices: list[int] = []
    for idx in special_indices:
        role = roles[idx]
        if role in seen_special_roles:
            roles[idx] = Role.WEREWOLF
            continue
        seen_special_roles.add(role)
        unique_special_indices.append(idx)

    max_special = max_special_wolves_for_player_count(requested_players)
    if len(unique_special_indices) <= max_special:
        return roles

    keep = set(unique_special_indices[:max_special])
    for idx in unique_special_indices:
        if idx in keep:
            continue
        roles[idx] = Role.WEREWOLF
    return roles


def enforce_wolf_ratio(roles: list[Role], requested_players: int) -> list[Role]:
    target_wolves = target_wolf_count_for_players(requested_players)
    available_roles = roles[:-2]
    extra_roles = roles[-2:]
    wolf_indices = [
        idx for idx, role in enumerate(available_roles) if is_wolf_aligned_role(role)
    ]

    if len(wolf_indices) > target_wolves:
        shuffled_wolves = random.shuffle(wolf_indices.copy())
        keep: list[int] = []
        if target_wolves > 0:
            first_team_wolf = next(
                (
                    idx
                    for idx in shuffled_wolves
                    if is_wolf_team_role(available_roles[idx])
                ),
                None,
            )
            if first_team_wolf is not None:
                keep.append(first_team_wolf)

        for idx in shuffled_wolves:
            if idx in keep:
                continue
            keep.append(idx)
            if len(keep) >= target_wolves:
                break

        keep_set = set(keep[:target_wolves])
        for idx in wolf_indices:
            if idx not in keep_set:
                available_roles[idx] = Role.VILLAGER

    elif len(wolf_indices) < target_wolves:
        needed = target_wolves - len(wolf_indices)
        villagers = [idx for idx, role in enumerate(available_roles) if role == Role.VILLAGER]
        safe_non_wolves = [
            idx
            for idx, role in enumerate(available_roles)
            if not is_wolf_aligned_role(role)
               and role not in (Role.JESTER, Role.HEAD_HUNTER, Role.FLUTIST, Role.SUPERSPREADER)
               and idx not in villagers
        ]
        candidates = random.shuffle(villagers) + random.shuffle(safe_non_wolves)
        if len(candidates) < needed:
            emergency = [
                idx
                for idx, role in enumerate(available_roles)
                if not is_wolf_aligned_role(role) and idx not in candidates
            ]
            candidates.extend(random.shuffle(emergency))

        for idx in candidates[:needed]:
            available_roles[idx] = Role.WEREWOLF

    if any(is_wolf_aligned_role(role) for role in available_roles) and not any(
            is_wolf_team_role(role) for role in available_roles
    ):
        for idx, role in enumerate(available_roles):
            if role == Role.WHITE_WOLF:
                available_roles[idx] = Role.WEREWOLF
                break

    return available_roles + extra_roles


def get_aura_alignment(player: Player) -> str:
    # Cursed players join the wolves and should read Evil.
    if player.cursed and player.role != Role.WHITE_WOLF:
        return "Evil"
    if player.role in UNKNOWN_AURA_ROLES:
        return "Unknown"
    if player.side in (Side.WOLVES, Side.WHITE_WOLF):
        return "Evil"
    return "Good"


class EndgameIdsView(discord.ui.View):
    def __init__(self, winner_ids: list[int], all_ids: list[int], timeout: float = 900):
        super().__init__(timeout=timeout)
        self.winner_ids = winner_ids
        self.all_ids = all_ids

    @staticmethod
    def _format_ids(user_ids: list[int]) -> str:
        if not user_ids:
            return "None"
        return "\n".join(str(user_id) for user_id in user_ids)

    async def _send_ids(
            self, interaction: discord.Interaction, *, title: str, user_ids: list[int]
    ) -> None:
        payload = self._format_ids(user_ids)
        message = f"{title}\n```text\n{payload}\n```"
        if len(message) > 1900:
            lines = payload.splitlines()
            clipped = []
            current_len = 0
            for line in lines:
                if current_len + len(line) + 1 > 1650:
                    break
                clipped.append(line)
                current_len += len(line) + 1
            clipped_payload = "\n".join(clipped) or "None"
            message = (
                f"{title}\n```text\n{clipped_payload}\n```\n"
                "Output truncated due to Discord length limits."
            )
        await interaction.response.send_message(message, ephemeral=True)

    @discord.ui.button(
        label="Copy User ID Winners",
        style=discord.ButtonStyle.success,
    )
    async def copy_winner_ids(
            self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await self._send_ids(
            interaction,
            title="Copy these winner user IDs:",
            user_ids=self.winner_ids,
        )

    @discord.ui.button(
        label="Copy User ID All",
        style=discord.ButtonStyle.primary,
    )
    async def copy_all_ids(
            self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await self._send_ids(
            interaction,
            title="Copy these user IDs:",
            user_ids=self.all_ids,
        )


class Game:
    def __init__(
            self, ctx: Context, players: list[discord.Member], mode: str, speed: str
    ) -> None:
        self.ctx = ctx
        self.mode = mode
        self.task = None
        self.speed = speed
        self.timers = {"Extended": 90, "Normal": 60, "Fast": 45, "Blitz": 30}
        self.timer = self.timers.get(self.speed, 60)
        self.game_link = _("Shortcut back to {ww_channel}").format(
            ww_channel=self.ctx.channel.mention
        )
        self.winning_side = None
        self.forced_winner = None
        self.judge_spoken = False
        self.judge_symbol = None
        self.ex_maid = None
        self.rusty_sword_disease_night = None
        self.recent_deaths = []
        self.lovers = []
        self._base_everyone_send_messages = None
        self._base_ww_alive_send_messages = None
        self._everyone_chat_locked = False
        self._night_chat_locked = False
        self._chat_perm_warning_sent = False
        self._role_perm_warning_sent = False
        self.pending_jail_target: Player | None = None
        self.current_jailed_target: Player | None = None
        self.jail_relay_task: asyncio.Task | None = None
        self.medium_relay_task: asyncio.Task | None = None
        self.jailer_day_pick_task: asyncio.Task | None = None
        self.junior_day_mark_task: asyncio.Task | None = None
        self.loudmouth_mark_task: asyncio.Task | None = None
        self.loudmouth_mark_player_id: int | None = None
        self.avenger_mark_task: asyncio.Task | None = None
        self.avenger_mark_player_id: int | None = None
        self.after_first_night = False
        self.pending_night_resurrections: list[tuple[Player, Player, Role]] = []
        self.available_roles = get_roles(len(players), self.mode)
        self.available_roles, self.extra_roles = (
            self.available_roles[:-2],
            self.available_roles[-2:],
        )

        if self.mode == "Huntergame":
            # Replace all non-Werewolf to Hunters
            for idx, role in enumerate(self.available_roles):
                if is_wolf_aligned_role(role):
                    self.available_roles[idx] = Role.WEREWOLF
                elif role not in (Role.WEREWOLF, Role.JESTER, Role.HEAD_HUNTER):
                    self.available_roles[idx] = Role.HUNTER
        elif self.mode == "Villagergame":
            # Replace all non-Werewolf to Villagers
            for idx, role in enumerate(self.available_roles):
                if role in (Role.JESTER, Role.HEAD_HUNTER):
                    continue
                if not is_wolf_aligned_role(role):
                    self.available_roles[idx] = Role.VILLAGER

        self.players: list[Player] = [
            Player(role, user, self)
            for role, user in zip(self.available_roles, players)
        ]

        if self.mode == "Valentines":
            lovers = list(chunks(random.shuffle(self.players), 2))
            for couple in lovers:
                if len(couple) == 2:
                    self.lovers.append(set(couple))
        random.choice(self.players).is_sheriff = True

    @property
    def sheriff(self) -> Player:
        return discord.utils.get(self.alive_players, is_sheriff=True)

    @property
    def alive_players(self) -> list[Player]:
        return [player for player in self.players if not player.dead]

    @property
    def dead_players(self) -> list[Player]:
        return [player for player in self.players if player.dead]

    def get_role_name(self, player_or_role: Player | Role) -> str:
        role_name = ""
        if isinstance(player_or_role, Role):
            role = player_or_role
        elif isinstance(player_or_role, Player):
            role = player_or_role.role
            if player_or_role.cursed:
                if not is_wolf_aligned_role(role):
                    role_name = "Cursed "
        else:
            raise TypeError("Wrong type: player_or_role. Only Player or Role allowed")
        role_name += role.name.title().replace("_", " ")
        return role_name

    def get_players_with_role(self, role: Role) -> list[Player]:
        return [player for player in self.alive_players if player.role == role]

    def get_player_with_role(self, role: Role) -> Player | None:
        return discord.utils.get(self.alive_players, role=role)

    def _get_ww_alive_role(self) -> discord.Role | None:
        guild = getattr(self.ctx, "guild", None)
        if guild is None:
            return None
        return guild.get_role(WW_ALIVE_ROLE_ID)

    def _get_ww_dead_role(self) -> discord.Role | None:
        guild = getattr(self.ctx, "guild", None)
        if guild is None:
            return None
        return guild.get_role(WW_DEAD_ROLE_ID)

    def _can_manage_ww_roles(self) -> bool:
        return bool(
            getattr(self.ctx, "guild", None)
            and getattr(self.ctx.channel, "id", None) == WW_NIGHT_LOCK_CHANNEL_ID
            and self._get_ww_alive_role() is not None
            and self._get_ww_dead_role() is not None
        )

    async def _warn_role_permission_issue(self) -> None:
        if self._role_perm_warning_sent:
            return
        self._role_perm_warning_sent = True
        await self.ctx.send(
            _(
                "I couldn't manage WW alive/dead role assignments. Please check that"
                " role IDs are correct and grant me **Manage Roles**."
            )
        )

    async def _set_player_ww_channel_state(
            self, member: discord.Member, *, alive: bool
    ) -> None:
        if not self._can_manage_ww_roles():
            return

        alive_role = self._get_ww_alive_role()
        dead_role = self._get_ww_dead_role()
        if alive_role is None or dead_role is None:
            return

        try:
            guild_member = self.ctx.guild.get_member(member.id) if self.ctx.guild else None
            target = guild_member or member
            if alive:
                if alive_role not in target.roles:
                    await target.add_roles(
                        alive_role,
                        reason="Werewolf game: player alive",
                    )
                if dead_role in target.roles:
                    await target.remove_roles(
                        dead_role,
                        reason="Werewolf game: remove dead role on revive/cleanup",
                    )
            else:
                if alive_role in target.roles:
                    await target.remove_roles(
                        alive_role,
                        reason="Werewolf game: player eliminated",
                    )
                if dead_role not in target.roles:
                    await target.add_roles(
                        dead_role,
                        reason="Werewolf game: player eliminated",
                    )
        except discord.Forbidden:
            await self._warn_role_permission_issue()
        except discord.HTTPException:
            await self._warn_role_permission_issue()

    async def setup_ww_player_roles(self) -> None:
        if not self._can_manage_ww_roles():
            return
        for player in self.players:
            await self._set_player_ww_channel_state(player.user, alive=True)

    async def sync_player_ww_role(self, player: Player) -> None:
        if not self._can_manage_ww_roles():
            return
        await self._set_player_ww_channel_state(player.user, alive=not player.dead)

    async def cleanup_ww_player_roles(self) -> None:
        if not self._can_manage_ww_roles():
            return
        alive_role = self._get_ww_alive_role()
        dead_role = self._get_ww_dead_role()
        if alive_role is None or dead_role is None:
            return

        for player in self.players:
            try:
                guild_member = (
                    self.ctx.guild.get_member(player.user.id) if self.ctx.guild else None
                )
                target = guild_member or player.user
                removable = [role for role in (alive_role, dead_role) if role in target.roles]
                if removable:
                    await target.remove_roles(
                        *removable,
                        reason="Werewolf game: cleanup alive/dead roles",
                    )
            except discord.Forbidden:
                await self._warn_role_permission_issue()
                break
            except discord.HTTPException:
                await self._warn_role_permission_issue()
                break

    def _can_manage_everyone_chat(self) -> bool:
        return bool(
            getattr(self.ctx, "guild", None)
            and getattr(self.ctx.channel, "id", None) == WW_NIGHT_LOCK_CHANNEL_ID
            and hasattr(self.ctx.channel, "overwrites_for")
            and hasattr(self.ctx.channel, "set_permissions")
        )

    async def _set_everyone_chat_lock(self, lock: bool) -> None:
        if not self._can_manage_everyone_chat():
            return

        guild = self.ctx.guild
        channel = self.ctx.channel
        everyone = guild.default_role
        overwrite = channel.overwrites_for(everyone)

        if self._base_everyone_send_messages is None:
            self._base_everyone_send_messages = overwrite.send_messages

        target_send_messages = False if lock else self._base_everyone_send_messages
        if (
            overwrite.send_messages == target_send_messages
            and self._everyone_chat_locked == lock
        ):
            return

        overwrite.send_messages = target_send_messages
        reason = (
            "Werewolf game lock for @everyone"
            if lock
            else "Werewolf game unlock for @everyone"
        )
        try:
            await channel.set_permissions(everyone, overwrite=overwrite, reason=reason)
            self._everyone_chat_locked = lock
        except discord.Forbidden:
            if not self._chat_perm_warning_sent:
                self._chat_perm_warning_sent = True
                await self.ctx.send(
                    _(
                        "I couldn't toggle @everyone chat permissions in this channel."
                        " Please grant me **Manage Channels**."
                    )
                )
        except discord.HTTPException:
            if not self._chat_perm_warning_sent:
                self._chat_perm_warning_sent = True
                await self.ctx.send(
                    _(
                        "I couldn't toggle @everyone chat permissions due to a"
                        " Discord API error."
                    )
                )

    async def _open_postgame_everyone_chat(self, duration_seconds: int = 120) -> None:
        if (
            duration_seconds <= 0
            or not self._can_manage_everyone_chat()
            or self._base_everyone_send_messages is None
        ):
            return

        guild = self.ctx.guild
        channel = self.ctx.channel
        everyone = guild.default_role
        dead_role = self._get_ww_dead_role()
        dead_role_send_opened = False

        try:
            if dead_role is not None and self._can_manage_ww_roles():
                dead_overwrite = channel.overwrites_for(dead_role)
                if dead_overwrite.send_messages is not True:
                    dead_overwrite.send_messages = True
                    await channel.set_permissions(
                        dead_role,
                        overwrite=dead_overwrite,
                        reason="Werewolf post-game chat window open for WW Dead",
                    )
                dead_role_send_opened = True

            overwrite = channel.overwrites_for(everyone)
            if overwrite.send_messages is not True:
                overwrite.send_messages = True
                await channel.set_permissions(
                    everyone,
                    overwrite=overwrite,
                    reason="Werewolf post-game chat window open",
                )
            self._everyone_chat_locked = False
            end_at = datetime.datetime.now(
                datetime.timezone.utc
            ) + datetime.timedelta(seconds=duration_seconds)
            end_ts = int(end_at.timestamp())
            await self.ctx.send(
                _(
                    "🗣️ Post-game chat is open to **@everyone** for"
                    " **{seconds} seconds** (until <t:{end_ts}:T>, <t:{end_ts}:R>)."
                ).format(seconds=duration_seconds, end_ts=end_ts)
            )
            await asyncio.sleep(duration_seconds)
            await self.ctx.send(_("🔒 Post-game chat window ended."))
        except discord.Forbidden:
            if not self._chat_perm_warning_sent:
                self._chat_perm_warning_sent = True
                await self.ctx.send(
                    _(
                        "I couldn't open the post-game chat window. Please grant me"
                        " **Manage Channels**."
                    )
                )
        except discord.HTTPException:
            if not self._chat_perm_warning_sent:
                self._chat_perm_warning_sent = True
                await self.ctx.send(
                    _(
                        "I couldn't open the post-game chat window due to a Discord"
                        " API error."
                    )
                )
        finally:
            if dead_role_send_opened and dead_role is not None:
                try:
                    dead_overwrite = channel.overwrites_for(dead_role)
                    if dead_overwrite.send_messages is not False:
                        dead_overwrite.send_messages = False
                        await channel.set_permissions(
                            dead_role,
                            overwrite=dead_overwrite,
                            reason="Werewolf post-game chat window closed for WW Dead",
                        )
                except (discord.Forbidden, discord.HTTPException):
                    pass

    async def ensure_ww_dead_channel_lock(self) -> None:
        if not self._can_manage_ww_roles():
            return
        dead_role = self._get_ww_dead_role()
        if dead_role is None:
            return

        channel = self.ctx.channel
        overwrite = channel.overwrites_for(dead_role)
        changed = False
        if overwrite.view_channel is False:
            # Do not deny read access for WW Dead in code.
            overwrite.view_channel = None
            changed = True
        if overwrite.send_messages is not False:
            overwrite.send_messages = False
            changed = True
        if overwrite.read_message_history is False:
            # Do not deny read history for WW Dead in code.
            overwrite.read_message_history = None
            changed = True
        if not changed:
            return

        try:
            await channel.set_permissions(
                dead_role,
                overwrite=overwrite,
                reason="Werewolf game: enforce WW Dead send lock",
            )
        except discord.Forbidden:
            if not self._chat_perm_warning_sent:
                self._chat_perm_warning_sent = True
                await self.ctx.send(
                    _(
                        "I couldn't enforce **WW Dead** channel permissions. Please"
                        " grant me **Manage Channels**."
                    )
                )
        except discord.HTTPException:
            if not self._chat_perm_warning_sent:
                self._chat_perm_warning_sent = True
                await self.ctx.send(
                    _(
                        "I couldn't enforce **WW Dead** channel permissions due to a"
                        " Discord API error."
                    )
                )

    def _can_manage_night_chat(self) -> bool:
        return bool(
            getattr(self.ctx, "guild", None)
            and getattr(self.ctx.channel, "id", None) == WW_NIGHT_LOCK_CHANNEL_ID
            and self._get_ww_alive_role() is not None
            and hasattr(self.ctx.channel, "overwrites_for")
            and hasattr(self.ctx.channel, "set_permissions")
        )

    async def _set_night_chat_lock(self, lock: bool) -> None:
        if not self._can_manage_night_chat():
            return

        channel = self.ctx.channel
        ww_alive_role = self._get_ww_alive_role()
        if ww_alive_role is None:
            return
        overwrite = channel.overwrites_for(ww_alive_role)

        if self._base_ww_alive_send_messages is None:
            self._base_ww_alive_send_messages = (
                overwrite.send_messages if overwrite.send_messages is not None else True
            )

        target_send_messages = False if lock else True
        if (
            overwrite.send_messages == target_send_messages
            and self._night_chat_locked == lock
        ):
            return

        overwrite.send_messages = target_send_messages
        reason = (
            "Werewolf night chat lock (WW Alive role)"
            if lock
            else "Werewolf day/game-over chat unlock (WW Alive role)"
        )
        try:
            await channel.set_permissions(ww_alive_role, overwrite=overwrite, reason=reason)
            self._night_chat_locked = lock
        except discord.Forbidden:
            if not self._chat_perm_warning_sent:
                self._chat_perm_warning_sent = True
                await self.ctx.send(
                    _(
                        "I couldn't toggle **WW Alive** chat permissions for night/day in"
                        " this channel. Please grant me **Manage Channels**."
                    )
                )
        except discord.HTTPException:
            if not self._chat_perm_warning_sent:
                self._chat_perm_warning_sent = True
                await self.ctx.send(
                    _(
                        "I couldn't toggle **WW Alive** chat permissions for night/day due"
                        " to a Discord API error."
                    )
                )

    async def ensure_head_hunter_targets(self) -> None:
        head_hunters = [
            player for player in self.alive_players if player.role == Role.HEAD_HUNTER
        ]
        for head_hunter in head_hunters:
            if head_hunter.headhunter_target and not head_hunter.headhunter_target.dead:
                continue
            possible_targets = [
                player
                for player in self.alive_players
                if player != head_hunter and player.side == Side.VILLAGERS
            ]
            if not possible_targets:
                if head_hunter.initial_roles[-1] != head_hunter.role:
                    head_hunter.initial_roles.append(head_hunter.role)
                head_hunter.role = Role.VILLAGER
                head_hunter.headhunter_target = None
                await head_hunter.send(
                    _(
                        "No valid Villager target remained for your hunt. You are now"
                        " a **Villager**.\n{game_link}"
                    ).format(game_link=self.game_link)
                )
                await head_hunter.send_information()
                continue

            head_hunter.headhunter_target = random.choice(possible_targets)
            await head_hunter.send(
                _(
                    "🎯 Your target is **{target}**. Get them lynched by the Village"
                    " to win. If they die by any other means, you'll become a"
                    " **Villager**.\n{game_link}"
                ).format(target=head_hunter.headhunter_target.user, game_link=self.game_link)
            )

    def is_player_jailed(self, player: Player) -> bool:
        return bool(self.current_jailed_target is not None and self.current_jailed_target == player)

    async def relay_jail_messages(self, jailer: Player, jailed: Player) -> None:
        allowed = {jailer.user.id, jailed.user.id}

        def check(message: discord.Message) -> bool:
            return (
                message.author.id in allowed
                and isinstance(message.channel, discord.DMChannel)
            )

        try:
            while (
                self.current_jailed_target == jailed
                and not jailed.dead
                and not jailer.dead
            ):
                try:
                    async with asyncio.timeout(10):
                        message = await self.ctx.bot.wait_for("message", check=check)
                except asyncio.TimeoutError:
                    continue
                if message.author.id == jailer.user.id:
                    recipient = jailed.user
                    prefix = _("🧑‍⚖️ Jailer")
                else:
                    recipient = jailer.user
                    prefix = _("🔒 Prisoner")
                await recipient.send(f"{prefix}: {message.content}")
        except asyncio.CancelledError:
            return

    async def _stop_jail_relay(self) -> None:
        if self.jail_relay_task:
            self.jail_relay_task.cancel()
            self.jail_relay_task = None

    def _get_active_medium(self) -> Player | None:
        medium = self.get_player_with_role(Role.MEDIUM)
        if medium is None or medium.dead:
            return None
        return medium

    def _get_medium_relay_participants(self) -> tuple[Player | None, list[Player]]:
        medium = self._get_active_medium()
        if medium is None:
            return None, []
        dead_players = [player for player in self.dead_players if player != medium]
        return medium, dead_players

    async def relay_medium_messages(self) -> None:
        def check(message: discord.Message) -> bool:
            medium, dead_players = self._get_medium_relay_participants()
            if medium is None:
                return False
            allowed_ids = {medium.user.id, *(player.user.id for player in dead_players)}
            return (
                message.author.id in allowed_ids
                and isinstance(message.channel, discord.DMChannel)
            )

        try:
            while True:
                medium, dead_players = self._get_medium_relay_participants()
                if medium is None:
                    return
                if not dead_players:
                    await asyncio.sleep(1)
                    continue

                message = await self.ctx.bot.wait_for("message", check=check)
                body_parts: list[str] = []
                if message.content:
                    body_parts.append(message.content)
                if message.attachments:
                    body_parts.extend(attachment.url for attachment in message.attachments)
                content = "\n".join(body_parts).strip()
                if not content:
                    continue

                if message.author.id == medium.user.id:
                    prefix = _("**Medium**")
                    recipients = [player.user for player in dead_players]
                else:
                    sender = discord.utils.find(
                        lambda player: player.user.id == message.author.id,
                        dead_players,
                    )
                    if sender is None:
                        continue
                    prefix = _("**{player} - {role}**").format(
                        player=sender.user.display_name,
                        role=self.get_role_name(sender),
                    )
                    recipients = [medium.user]
                    recipients.extend(
                        player.user
                        for player in dead_players
                        if player.user.id != sender.user.id
                    )

                for recipient in recipients:
                    await recipient.send(f"{prefix}: {content}")
        except asyncio.CancelledError:
            return

    async def _ensure_medium_relay(self) -> None:
        medium = self._get_active_medium()
        if medium is None:
            await self._stop_medium_relay()
            return
        if self.medium_relay_task and self.medium_relay_task.done():
            self.medium_relay_task = None
        if self.medium_relay_task is None:
            self.medium_relay_task = asyncio.create_task(self.relay_medium_messages())

    async def _stop_medium_relay(self) -> None:
        if self.medium_relay_task:
            self.medium_relay_task.cancel()
            self.medium_relay_task = None

    async def _prompt_jailer_execution(self, jailer: Player, jailed: Player) -> None:
        if jailer.dead or jailed.dead or not jailer.has_jailer_execution_ability:
            return
        try:
            action = await self.ctx.bot.paginator.Choose(
                entries=[_("Execute"), _("Do not execute")],
                return_index=True,
                title=_(
                    "You jailed **{target}**. Execute them now? (one-time ability)"
                ).format(target=jailed.user),
                timeout=self.timer,
            ).paginate(self.ctx, location=jailer.user)
        except self.ctx.bot.paginator.NoChoice:
            return
        except (discord.Forbidden, discord.HTTPException):
            await self.ctx.send(
                _("I couldn't send a DM to someone. Too bad they missed to use their power.")
            )
            return
        if action != 0:
            return

        jailer.has_jailer_execution_ability = False
        await self.ctx.send(
            _(
                "⚖️ The **Jailer** executed **{target}** in prison. Their role will now"
                " be revealed."
            ).format(target=jailed.user.mention)
        )
        await jailed.kill()
        await self._stop_jail_relay()

    async def activate_jail_for_night(self) -> None:
        jailer = self.get_player_with_role(Role.JAILER)
        self.current_jailed_target = None
        await self._stop_jail_relay()
        if jailer is None or jailer.dead:
            self.pending_jail_target = None
            return
        if self.pending_jail_target is None:
            return

        if self.pending_jail_target.dead or self.pending_jail_target == jailer:
            await jailer.send(
                _(
                    "Your selected jail target is no longer valid, so no one was jailed"
                    " tonight.\n{game_link}"
                ).format(game_link=self.game_link)
            )
            self.pending_jail_target = None
            return

        jailed = self.pending_jail_target
        self.pending_jail_target = None
        self.current_jailed_target = jailed
        jailed.is_jailed = True
        jailed.is_protected = True
        jailed.protected_by_jailer = True

        await jailer.send(
            _(
                "🔒 You jailed {jailed_mention} for tonight. A direct private line is"
                " now open between you and {jailed_mention} until daybreak. Send any"
                " DM message here during this time to talk."
                "\n{game_link}"
            ).format(
                jailed_mention=jailed.user.mention,
                game_link=self.game_link,
            )
        )
        await jailed.send(
            _(
                "🔒 You were jailed for tonight by {jailer_mention}. You cannot use"
                " your abilities and you are protected from werewolf attacks. A direct"
                " private line is now open between you and {jailer_mention} until"
                " daybreak. Send any DM message here during this time to talk."
                "\n{game_link}"
            ).format(
                jailer_mention=jailer.user.mention,
                game_link=self.game_link,
            )
        )

        self.jail_relay_task = asyncio.create_task(self.relay_jail_messages(jailer, jailed))
        await self._prompt_jailer_execution(jailer, jailed)

    async def release_jailed_player(self) -> None:
        jailed = self.current_jailed_target
        self.current_jailed_target = None
        await self._stop_jail_relay()
        if jailed is None:
            return
        jailed.is_jailed = False
        jailed.protected_by_jailer = False
        if not jailed.dead:
            await jailed.send(
                _("🔓 You were released from jail as day begins.\n{game_link}").format(
                    game_link=self.game_link
                )
            )

    async def _collect_jailer_day_target(self, jailer: Player) -> None:
        day_timeout = 3600
        await jailer.send(
            _(
                "During the day, choose one player to jail for the next night."
                " You can choose at any time before nightfall.\n{game_link}"
            ).format(game_link=self.game_link)
        )
        try:
            picked = await jailer.choose_users(
                _("Choose a player to jail for next night."),
                list_of_users=[p for p in self.alive_players if p != jailer],
                amount=1,
                required=False,
                timeout=day_timeout,
            )
        except asyncio.CancelledError:
            return
        except Exception:
            return
        if (
            not picked
            or jailer.dead
            or self.get_player_with_role(Role.JAILER) != jailer
        ):
            return
        target = picked[0]
        if target.dead or target == jailer:
            return
        self.pending_jail_target = target
        await jailer.send(
            _("You selected **{target}** to be jailed next night.\n{game_link}").format(
                target=target.user, game_link=self.game_link
            )
        )

    async def start_jailer_day_target_selection(self) -> None:
        if self.jailer_day_pick_task:
            self.jailer_day_pick_task.cancel()
            self.jailer_day_pick_task = None
        self.pending_jail_target = None
        jailer = self.get_player_with_role(Role.JAILER)
        if jailer is None or jailer.dead:
            return
        self.jailer_day_pick_task = asyncio.create_task(self._collect_jailer_day_target(jailer))

    async def stop_jailer_day_target_selection(self) -> None:
        if self.jailer_day_pick_task:
            self.jailer_day_pick_task.cancel()
            self.jailer_day_pick_task = None

    def _junior_mark_candidates(self, junior: Player) -> list[Player]:
        return [
            player
            for player in self.alive_players
            if player != junior
               and player.side == Side.VILLAGERS
               and player not in junior.own_lovers
        ]

    async def _collect_junior_day_mark(self, junior: Player) -> None:
        prompt_timeout = max(90, self.timer)
        await junior.send(
            _(
                "During each day, mark one Villager to drag down if you die. You can"
                " update this mark repeatedly until nightfall."
                "\n{game_link}"
            ).format(game_link=self.game_link)
        )

        while (
            not junior.dead
            and self.get_player_with_role(Role.JUNIOR_WEREWOLF) == junior
        ):
            candidates = self._junior_mark_candidates(junior)
            if not candidates:
                junior.junior_mark_target = None
                return

            current_mark = (
                junior.junior_mark_target
                if junior.junior_mark_target in candidates
                else None
            )
            current_label = current_mark.user if current_mark else _("None")

            try:
                picked = await junior.choose_users(
                    _(
                        "Choose a Villager to mark. Current mark: **{current_mark}**."
                    ).format(current_mark=current_label),
                    list_of_users=candidates,
                    amount=1,
                    required=False,
                    timeout=prompt_timeout,
                )
            except asyncio.CancelledError:
                return
            except Exception:
                return

            if (
                junior.dead
                or self.get_player_with_role(Role.JUNIOR_WEREWOLF) != junior
            ):
                return

            if picked:
                junior.junior_mark_target = picked[0]
                await junior.send(
                    _(
                        "🐺 You marked **{target}**. If you die, they will be dragged"
                        " down. You can still change this mark before night."
                        "\n{game_link}"
                    ).format(
                        target=junior.junior_mark_target.user,
                        game_link=self.game_link,
                    )
                )
                await asyncio.sleep(2)
            else:
                await asyncio.sleep(10)

    async def start_junior_day_mark_selection(self) -> None:
        if self.junior_day_mark_task:
            self.junior_day_mark_task.cancel()
            self.junior_day_mark_task = None
        junior = self.get_player_with_role(Role.JUNIOR_WEREWOLF)
        if junior is None or junior.dead:
            return
        self.junior_day_mark_task = asyncio.create_task(
            self._collect_junior_day_mark(junior)
        )

    async def stop_junior_day_mark_selection(self) -> None:
        if self.junior_day_mark_task:
            self.junior_day_mark_task.cancel()
            self.junior_day_mark_task = None

    def _loudmouth_mark_candidates(self, loudmouth: Player) -> list[Player]:
        return [player for player in self.alive_players if player != loudmouth]

    async def _collect_loudmouth_target(self, loudmouth: Player) -> None:
        await loudmouth.send(
            _(
                "📣 As **Loudmouth**, pick one player. If you die, that player's role"
                " is revealed to everyone. You can change your selection at any time."
                "\n{game_link}"
            ).format(game_link=self.game_link)
        )
        prompt_timeout = 3600
        while (
                not loudmouth.dead
                and self.get_player_with_role(Role.LOUDMOUTH) == loudmouth
        ):
            if loudmouth.is_jailed:
                await asyncio.sleep(5)
                continue

            candidates = self._loudmouth_mark_candidates(loudmouth)
            if not candidates:
                await asyncio.sleep(10)
                continue

            current_mark = loudmouth.loudmouth_target
            current_label = current_mark.user if current_mark else _("None")
            try:
                picked = await loudmouth.choose_users(
                    _(
                        "Choose a player to reveal when you die. Current mark:"
                        " **{current_mark}**."
                    ).format(current_mark=current_label),
                    list_of_users=candidates,
                    amount=1,
                    required=False,
                    timeout=prompt_timeout,
                )
            except asyncio.CancelledError:
                return
            except Exception as e:
                schedule_traceback(self.ctx, e)
                return

            if (
                    loudmouth.dead
                    or self.get_player_with_role(Role.LOUDMOUTH) != loudmouth
            ):
                return

            if picked:
                loudmouth.loudmouth_target = picked[0]
                await loudmouth.send(
                    _(
                        "📣 You marked **{target}**. If you die, their role will be"
                        " revealed to everyone. You can still change this at any time."
                        "\n{game_link}"
                    ).format(
                        target=loudmouth.loudmouth_target.user,
                        game_link=self.game_link,
                    )
                )
                await asyncio.sleep(2)
            else:
                await asyncio.sleep(5)

    async def start_loudmouth_target_selection(self) -> None:
        loudmouth = self.get_player_with_role(Role.LOUDMOUTH)
        if loudmouth is None or loudmouth.dead:
            await self.stop_loudmouth_target_selection()
            return
        if (
                self.loudmouth_mark_task
                and not self.loudmouth_mark_task.done()
                and self.loudmouth_mark_player_id == loudmouth.user.id
        ):
            return
        await self.stop_loudmouth_target_selection()
        self.loudmouth_mark_player_id = loudmouth.user.id
        self.loudmouth_mark_task = asyncio.create_task(
            self._collect_loudmouth_target(loudmouth)
        )

    async def stop_loudmouth_target_selection(self) -> None:
        if self.loudmouth_mark_task:
            self.loudmouth_mark_task.cancel()
            self.loudmouth_mark_task = None
        self.loudmouth_mark_player_id = None

    def _avenger_mark_candidates(self, avenger: Player) -> list[Player]:
        return [player for player in self.alive_players if player != avenger]

    async def _collect_avenger_target(self, avenger: Player) -> None:
        await avenger.send(
            _(
                "🗡️ As **Avenger**, after the first night you can mark one player. If"
                " you die, that player dies with you. You can change your mark at any"
                " time.\n{game_link}"
            ).format(game_link=self.game_link)
        )
        prompt_timeout = 3600
        while (
                not avenger.dead
                and self.get_player_with_role(Role.AVENGER) == avenger
        ):
            if not self.after_first_night:
                await asyncio.sleep(5)
                continue
            if avenger.is_jailed:
                await asyncio.sleep(5)
                continue

            candidates = self._avenger_mark_candidates(avenger)
            if not candidates:
                await asyncio.sleep(10)
                continue

            current_mark = avenger.avenger_target
            current_label = current_mark.user if current_mark else _("None")
            try:
                picked = await avenger.choose_users(
                    _(
                        "Choose a player to die with you if you die. Current mark:"
                        " **{current_mark}**."
                    ).format(current_mark=current_label),
                    list_of_users=candidates,
                    amount=1,
                    required=False,
                    timeout=prompt_timeout,
                )
            except asyncio.CancelledError:
                return
            except Exception as e:
                schedule_traceback(self.ctx, e)
                return

            if (
                    avenger.dead
                    or self.get_player_with_role(Role.AVENGER) != avenger
            ):
                return

            if picked:
                avenger.avenger_target = picked[0]
                await avenger.send(
                    _(
                        "🗡️ You marked **{target}**. If you die, they will die with"
                        " you. You can still change this mark at any time."
                        "\n{game_link}"
                    ).format(
                        target=avenger.avenger_target.user,
                        game_link=self.game_link,
                    )
                )
                await asyncio.sleep(2)
            else:
                await asyncio.sleep(5)

    async def start_avenger_target_selection(self) -> None:
        avenger = self.get_player_with_role(Role.AVENGER)
        if avenger is None or avenger.dead:
            await self.stop_avenger_target_selection()
            return
        if (
                self.avenger_mark_task
                and not self.avenger_mark_task.done()
                and self.avenger_mark_player_id == avenger.user.id
        ):
            return
        await self.stop_avenger_target_selection()
        self.avenger_mark_player_id = avenger.user.id
        self.avenger_mark_task = asyncio.create_task(
            self._collect_avenger_target(avenger)
        )

    async def stop_avenger_target_selection(self) -> None:
        if self.avenger_mark_task:
            self.avenger_mark_task.cancel()
            self.avenger_mark_task = None
        self.avenger_mark_player_id = None

    async def handle_head_hunter_target_death(self, dead_player: Player) -> None:
        head_hunters = [
            player
            for player in self.alive_players
            if player.role == Role.HEAD_HUNTER and player.headhunter_target == dead_player
        ]
        for head_hunter in head_hunters:
            if dead_player.killed_by_lynch:
                if self.forced_winner is None:
                    self.winning_side = "Head Hunter"
                    self.forced_winner = head_hunter
                    await self.ctx.send(
                        _(
                            "🎯 **{hunter}** fulfilled the Head Hunter objective by"
                            " getting **{target}** lynched. The game ends immediately!"
                        ).format(
                            hunter=head_hunter.user.mention,
                            target=dead_player.user.mention,
                        )
                    )
            else:
                if head_hunter.initial_roles[-1] != head_hunter.role:
                    head_hunter.initial_roles.append(head_hunter.role)
                head_hunter.role = Role.VILLAGER
                head_hunter.headhunter_target = None
                await head_hunter.send(
                    _(
                        "Your target **{target}** died without being lynched. You are"
                        " now a **Villager**.\n{game_link}"
                    ).format(target=dead_player.user, game_link=self.game_link)
                )
                await head_hunter.send_information()

    async def apply_night_protection(self, targets: list[Player]) -> list[Player]:
        protected_players = [
            player for player in self.alive_players if player.is_protected
        ]
        doctor = self.get_player_with_role(Role.DOCTOR)
        bodyguards_to_kill: set[Player] = set()
        bodyguard = self.get_player_with_role(Role.BODYGUARD)

        if bodyguard and not bodyguard.dead and bodyguard in targets:
            while bodyguard in targets:
                targets.remove(bodyguard)
            if bodyguard.bodyguard_intercepts == 0:
                bodyguard.bodyguard_intercepts = 1
                await bodyguard.send(
                    _(
                        "🛡️ You were attacked tonight, but you held your ground and"
                        " survived. The next time you intercept an attack, you will die."
                        "\n{game_link}"
                    ).format(game_link=self.game_link)
                )
            else:
                bodyguard.bodyguard_intercepts += 1
                bodyguards_to_kill.add(bodyguard)
                await bodyguard.send(
                    _(
                        "🛡️ You intercepted another attack tonight. Your strength is"
                        " exhausted, and this time the blow is fatal.\n{game_link}"
                    ).format(game_link=self.game_link)
                )

        for protected in protected_players:
            was_attacked = protected in targets
            protected.is_protected = False
            while protected in targets:
                targets.remove(protected)

            if was_attacked and protected.protected_by_bodyguard:
                bodyguard = protected.protected_by_bodyguard
                if bodyguard and not bodyguard.dead:
                    if bodyguard in bodyguards_to_kill:
                        pass
                    elif bodyguard.bodyguard_intercepts == 0:
                        bodyguard.bodyguard_intercepts = 1
                        await bodyguard.send(
                            _(
                                "🛡️ You intercepted an attack on **{saved}** and"
                                " survived. The next time you intercept an attack, you"
                                " will die.\n{game_link}"
                            ).format(saved=protected.user, game_link=self.game_link)
                        )
                    else:
                        bodyguard.bodyguard_intercepts += 1
                        bodyguards_to_kill.add(bodyguard)
                        await bodyguard.send(
                            _(
                                "🛡️ You intercepted another attack on **{saved}**. This"
                                " second interception is fatal.\n{game_link}"
                            ).format(saved=protected.user, game_link=self.game_link)
                        )
                if bodyguard and bodyguard in bodyguards_to_kill:
                    await protected.send(
                        _(
                            "🛡️ You were attacked tonight, and the **Bodyguard** saved"
                            " you but died doing so.\n{game_link}"
                        ).format(game_link=self.game_link)
                    )
                else:
                    await protected.send(
                        _(
                            "🛡️ You were attacked tonight, but the **Bodyguard**"
                            " protected you.\n{game_link}"
                        ).format(game_link=self.game_link)
                    )
            elif was_attacked and protected.protected_by_doctor:
                if doctor:
                    await doctor.send(
                        _(
                            "🩺 Your protection saved **{saved}** from an attack"
                            " tonight.\n{game_link}"
                        ).format(saved=protected.user, game_link=self.game_link)
                    )
                await protected.send(
                    _(
                        "🩺 You were attacked tonight, but the **Doctor** saved you."
                        "\n{game_link}"
                    ).format(game_link=self.game_link)
                )
            elif was_attacked and protected.protected_by_jailer:
                jailer = self.get_player_with_role(Role.JAILER)
                if jailer:
                    await jailer.send(
                        _(
                            "🔒 Your prisoner **{saved}** was attacked, but your jail"
                            " protected them.\n{game_link}"
                        ).format(saved=protected.user, game_link=self.game_link)
                    )
                await protected.send(
                    _(
                        "🔒 You were attacked tonight, but your cell protected you."
                        "\n{game_link}"
                    ).format(game_link=self.game_link)
                )
            protected.protected_by_doctor = False
            protected.protected_by_bodyguard = None
            protected.protected_by_jailer = False

        for bodyguard in bodyguards_to_kill:
            if not bodyguard.dead:
                await self.ctx.send(
                    _(
                        "🛡️ **{bodyguard}** fell after intercepting a second attack."
                    ).format(bodyguard=bodyguard.user.mention)
                )
                await bodyguard.kill()
        return targets

    async def apply_cursed_conversion(self, targets: list[Player]) -> list[Player]:
        # Cursed converts only when directly targeted by the werewolves' night attack.
        for target in list(dict.fromkeys(targets)):
            if target.dead or target.role != Role.CURSED:
                continue
            while target in targets:
                targets.remove(target)
            if target.initial_roles[-1] != target.role:
                target.initial_roles.append(target.role)
            target.role = Role.WEREWOLF
            target.cursed = False
            await target.send(
                _(
                    "You were attacked by the Werewolves, but instead of dying you"
                    " transformed into a **Werewolf**.\n{game_link}"
                ).format(game_link=self.game_link)
            )
            await target.send_information()
        return targets

    async def offer_fortune_card_reveals(self) -> None:
        card_holders = [
            player
            for player in self.alive_players
            if player.fortune_cards > 0
        ]
        if not card_holders:
            return

        await self.ctx.send(
            _("🔮 Players with Revelation Cards may choose to reveal their role.")
        )
        results = await asyncio.gather(
            *(player.offer_fortune_card_reveal() for player in card_holders),
            return_exceptions=True,
        )
        for result in results:
            if isinstance(result, Exception):
                await send_traceback(self.ctx, result)

    @property
    def winner(self) -> Player | None:
        # Check if any player reached their objective
        try:
            if self.forced_winner is not None:
                return self.forced_winner
            objective_reached = discord.utils.get(self.alive_players, has_won=True)
            if objective_reached:
                return objective_reached
                
            # Check if there's only one player left
            if len(self.alive_players) == 1:
                return self.alive_players[0]
            elif len(self.alive_players) == 0:
                return _("No one")
            
            return None
        except Exception as e:
            schedule_traceback(self.ctx, e)
            return _("No one")

    @property
    def new_afk_players(self) -> list[Player]:
        return [player for player in self.alive_players if player.to_check_afk]

    async def relay_messages(self, wolves):
        def check(message):
            return message.author in [wolf.user for wolf in wolves] and isinstance(message.channel, discord.DMChannel)

        try:
            while True:
                message = await self.ctx.bot.wait_for('message', check=check)

                # Relay the message to the other wolves
                for wolf in wolves:
                    if wolf.user != message.author:
                        await wolf.user.send(f"{message.author}: {message.content}")

        except asyncio.CancelledError:
            # Handle cancellation cleanup here
            print("Task cancelled")

    async def wolves(self) -> Player | None:
        if bodyguard := self.get_player_with_role(Role.BODYGUARD):
            await bodyguard.set_bodyguard_target()
        if healer := self.get_player_with_role(Role.HEALER):
            await healer.set_healer_target()
        if doctor := self.get_player_with_role(Role.DOCTOR):
            await doctor.set_doctor_target()
        wolves = [
            p
            for p in self.alive_players
            if p.side == Side.WOLVES or p.side == Side.WHITE_WOLF
        ]
        all_wolves = wolves.copy()
        jailed_wolves = [wolf for wolf in wolves if wolf.is_jailed]
        wolves = [wolf for wolf in wolves if not wolf.is_jailed]
        for jailed_wolf in jailed_wolves:
            await jailed_wolf.send(
                _(
                    "You are jailed tonight and cannot participate in werewolf"
                    " nominations, voting, or wolf chat relay.\n{game_link}"
                ).format(game_link=self.game_link)
            )

        if len(wolves) == 0:
            if jailed_wolves:
                await self.ctx.send(
                    _(
                        "All werewolves who could attack tonight were jailed. No one was"
                        " killed by the werewolves."
                    )
                )
            return
        wolves_users = [str(p.user.id) for p in wolves]
        await self.ctx.send(_("**The Werewolves awake...**"))
        # Get target of wolves
        target_list = [p for p in self.alive_players if p not in all_wolves]
        possible_targets = {idx: p for idx, p in enumerate(target_list, 1)}
        fmt = commands.Paginator(prefix="", suffix="")
        wolf_names = _("Hey **")
        for player in wolves:
            if len(wolf_names + str(player.user) + ", ") > 1900:
                fmt.add_line(wolf_names + "**")
                wolf_names = "**"
            wolf_names += str(player.user) + ", "
            if player == wolves[-1]:
                fmt.add_line(wolf_names[:-2] + "**")
        if len(wolves) > 1:
            greet_text = _("__{count}__ Werewolves").format(count=len(wolves))
        else:
            greet_text = _("lone Werewolf")
        fmt.add_line(
            _("**🐺 Wake up {greet_text}! It is time to choose a victim**").format(
                greet_text=greet_text
            )
        )
        fmt.add_line(_("All possible victims are:"))
        for idx, p in possible_targets.items():
            fmt.add_line(
                f"{idx}. {p.user}"
                f" {p.user.mention} {p.role_name if p.role == Role.PURE_SOUL else ''}"
            )
        fmt.add_line("")
        fmt.add_line(
            _(
                "**I will relay all messages you send to the other Werewolves. Use the"
                " dropdown to nominate a victim for killing. Voting starts in {timer}"
                " seconds.**"
            ).format(timer=self.timer)
        )
        fmt.add_line(
            _(
                "**Please take it slow when messaging through me, it may cause issues!**"
            )
        )
        for user in wolves:
            for page in fmt.pages:
                await user.send(page)
        nominated = []

        try:
            async with asyncio.timeout(self.timer):
                for werewolf in wolves:
                    if werewolf.user.dm_channel is None:
                        await werewolf.user.create_dm()

                # Start the relay_messages function as a background task
                self.task = asyncio.create_task(self.relay_messages(wolves))

                try:
                    # List to store tasks for each werewolf
                    voting_tasks = []

                    # Loop through each werewolf
                    for werewolf in wolves:
                        # Define a task for each werewolf
                        async def werewolf_vote(werewolf):
                            try:
                                picked = await werewolf.choose_users(
                                    _(
                                        "Choose a victim to nominate with the dropdown."
                                    ),
                                    list_of_users=target_list,
                                    amount=1,
                                    required=False,
                                )
                            except Exception as e:
                                await send_traceback(self.ctx, e)
                                return

                            if not picked:
                                return

                            submitted_target = picked[0]
                            try:
                                if submitted_target in werewolf.own_lovers:
                                    await werewolf.send(_("❌ You cannot nominate your Lover."))
                                else:
                                    if (
                                        submitted_target not in nominated
                                        and len(set(nominated)) >= 10
                                    ):
                                        await werewolf.send(
                                            _(
                                                "Nomination cap reached (10 targets)."
                                                " Your nomination was not added."
                                            )
                                        )
                                        return
                                    nominated.append(submitted_target)
                                    text = f"**{werewolf.user}** nominated **{submitted_target.user}**"
                                    for wolf_member in wolves:
                                        await wolf_member.send(text)
                            except Exception as e:
                                await send_traceback(self.ctx, e)

                        # Append the task for the current werewolf to the list of tasks
                        voting_tasks.append(werewolf_vote(werewolf))

                    # Run all voting tasks concurrently
                    await asyncio.gather(*voting_tasks)

                except Exception as e:
                    await send_traceback(self.ctx, e)


        except asyncio.TimeoutError:
            pass

        if not nominated:
            for user in wolves:
                await user.send(
                    _(
                        "Not a single one of you wanted to attack a villager. No fresh"
                        " meat tonight 😆.\n{game_link}"
                    ).format(game_link=self.game_link)
                )
            return
        nominated = {u: 0 for u in nominated}
        nominated_users = [
            _("{player_name} Votes: {votes}").format(player_name=u.user, votes=0)
            for u in nominated
        ]
        if len(nominated) > 1:
            for werewolf in wolves:
                await werewolf.send(
                    _("The voting is starting, please wait for your turn...")
                )
            done_voting = {w: False for w in wolves}
            for werewolf in wolves:

                async def get_vote():
                    attempt = 1

                    while not done_voting[werewolf] and attempt <= 2:
                        try:
                            target = await self.ctx.bot.paginator.Choose(
                                entries=nominated_users,
                                return_index=True,
                                title=(
                                    _(
                                        "Use the dropdown to vote for a target. You"
                                        " have {timer} seconds."
                                    ).format(timer=self.timer)
                                ),
                                timeout=self.timer,
                            ).paginate(self.ctx, location=werewolf.user)
                        except (
                                self.ctx.bot.paginator.NoChoice,
                                discord.Forbidden,
                                discord.HTTPException,
                        ):
                            await werewolf.send(_("You timed out and didn't vote."))
                            return None, None
                        else:
                            voted = list(nominated.keys())[target]
                            if voted in werewolf.own_lovers:
                                await werewolf.send(
                                    _("❌ You cannot vote for your Lover to die.")
                                )
                                attempt += 1
                                continue
                            return voted, target

                    return None, None

                voted, target = await get_vote()
                done_voting[werewolf] = True

                if voted:
                    nominated[voted] += 1
                    nominated_users[target] = _("{player_name} Votes: {votes}").format(
                        player_name=voted.user, votes=nominated[voted]
                    )

            targets = sorted(list(nominated.keys()), key=lambda x: -nominated[x])
            if nominated[targets[0]] > nominated[targets[1]]:
                target = targets[0]
            else:
                target = None
                for user in wolves:
                    await user.send(
                        _(
                            "Werewolves, you are all indecisive. No fresh meat tonight"
                            " 😆.\n{game_link}"
                        ).format(game_link=self.game_link)
                    )
        else:
            target = list(nominated.keys())[0]
        if target:
            for user in wolves:
                await user.send(
                    _(
                        "Werewolves, you have decided to kill **{target}** tonight"
                        " and be your meal.\n{game_link}"
                    ).format(target=target.user, game_link=self.game_link)
                )
            if cursed_wolf_father := self.get_player_with_role(Role.CURSED_WOLF_FATHER):
                target = await cursed_wolf_father.curse_target(target)
        await asyncio.sleep(5)  # Give them time to read
        if self.task:
            self.task.cancel()
        return target

    async def announce_pure_soul(
            self, pure_soul: Player, ex_pure_soul: Player | None = None
    ) -> None:
        for p in self.players:
            if ex_pure_soul:
                try:
                    p.revealed_roles.pop(ex_pure_soul)
                except KeyError:
                    pass
            p.revealed_roles.update({pure_soul: pure_soul.role})
        await self.ctx.send(
            _("{pure_soul} is a **{role}** and an innocent villager.").format(
                pure_soul=pure_soul.user.mention, role=pure_soul.role_name
            )
        )

    async def announce_sheriff(self) -> None:
        await self.ctx.send(
            _(
                "📢 {sheriff} got randomly chosen as the new 🎖 **Sheriff**️. **The vote"
                " of the Sheriff counts as double.**"
            ).format(sheriff=self.sheriff.user.mention)
        )
        await self.dm_sheriff_info()

    async def dm_sheriff_info(self) -> None:
        await self.sheriff.send(
            _(
                "You became the 🎖 **Sheriff. Your vote counts as double. If you died or"
                " exchanged roles using Maid's ability, you must choose a new"
                " Sheriff.**"
            )
        )
        await asyncio.sleep(5)  # Give them time to read

    async def send_love_msgs(self) -> None:
        for couple in self.lovers:
            couple = list(couple)
            for lover in couple:
                await lover.send_love_msg(
                    couple[couple.index(lover) - 1], mode_effect=True
                )

    def get_chained_lovers(self, start: Player, chained: set = None) -> set:
        if chained is None:
            if len(start.own_lovers) == 0:
                return set()
            chained = {start}
        others = set(start.own_lovers) - chained
        if len(others) == 0:
            return chained
        chained = chained.union(others)
        for lover in others:
            chained = self.get_chained_lovers(lover, chained)
        return chained

    async def initial_preparation(self) -> list[Player]:
        await self._set_everyone_chat_lock(True)
        await self.ensure_ww_dead_channel_lock()
        await self.setup_ww_player_roles()
        mode_emojis = {"Huntergame": "🔫", "Valentines": "💕"}
        mode_emoji = mode_emojis.get(self.mode, "")
        paginator = commands.Paginator(prefix="", suffix="")
        paginator.add_line(
            _("**The __{num}__ inhabitants of the Village:**").format(
                num=len(self.players)
            )
        )
        players = ""
        for player in self.players:
            if len(players + player.user.mention + " ") > 1900:
                paginator.add_line(players)
                players = ""
            players += player.user.mention + " "
            if player == self.players[-1]:
                paginator.add_line(players[:-1])
        paginator.add_line(
            _(
                "**Welcome to Werewolf {mode}!\n{speed} speed activated - All action"
                " timers are limited to {timer} seconds.**"
            ).format(
                mode=mode_emoji + self.mode + mode_emoji,
                speed=self.speed,
                timer=self.timer,
            )
        )
        for page in paginator.pages:
            await self.ctx.send(page)

        role_counts: dict[Role, int] = {}
        for player in self.players:
            role_counts[player.role] = role_counts.get(player.role, 0) + 1

        roles_paginator = commands.Paginator(prefix="", suffix="")
        roles_paginator.add_line(_("**Roles in this match:**"))
        role_entries = []
        for role, count in sorted(
            role_counts.items(), key=lambda item: self.get_role_name(item[0]).lower()
        ):
            role_name = self.get_role_name(role)
            if count > 1:
                role_entries.append(_("{count}x {role}").format(count=count, role=role_name))
            else:
                role_entries.append(role_name)

        current_line = ""
        for entry in role_entries:
            segment = f"`{entry}`"
            candidate = f"{current_line}, {segment}" if current_line else segment
            if len(candidate) > 1850:
                roles_paginator.add_line(current_line)
                current_line = segment
            else:
                current_line = candidate
        if current_line:
            roles_paginator.add_line(current_line)

        if any(player.role == Role.THIEF for player in self.players) and self.extra_roles:
            reserve = ", ".join(
                self.get_role_name(role) for role in sorted(
                    self.extra_roles, key=lambda role: self.get_role_name(role).lower()
                )
            )
            roles_paginator.add_line(
                _("**Thief reserve roles:** {roles}").format(roles=reserve)
            )

        for page in roles_paginator.pages:
            await self.ctx.send(page)

        house_rules = _(
            "📜⚠️ Talking to other users privately is"
            " prohibited! Posting any screenshots of my messages"
            " containing your role is also forbidden."
        )
        await self.ctx.send(
            _(
                "**Sending game roles... You may use `{prefix}ww myrole` to check"
                " your role later.\n{house_rules}**"
            ).format(prefix=self.ctx.clean_prefix, house_rules=house_rules)
        )
        for player in self.players:
            await player.send(
                _("**Welcome to Werewolf {mode}! {house_rules}\n{game_link}**").format(
                    mode=mode_emoji + self.mode + mode_emoji,
                    house_rules=house_rules,
                    game_link=self.game_link,
                )
            )
            await player.send_information()
        if medium := self.get_player_with_role(Role.MEDIUM):
            await medium.send(
                _(
                    "🔮 You can communicate privately with dead players. Whenever a"
                    " player dies, a direct relay opens. Send any DM message here to"
                    " speak with the dead.\n{game_link}"
                ).format(game_link=self.game_link)
            )
        await self._ensure_medium_relay()
        await self.start_loudmouth_target_selection()
        await self.start_avenger_target_selection()
        await self.announce_sheriff()
        await self._set_night_chat_lock(True)
        await self.ctx.send(_("🌘 💤 **Night falls, the town is asleep...**"))
        await asyncio.sleep(5)  # Give them time to read the rules and their roles
        await self.send_love_msgs()  # Send to lovers used on Valentines mode
        if thief := self.get_player_with_role(Role.THIEF):
            await thief.choose_thief_role()
        if wolfhound := self.get_player_with_role(Role.WOLFHOUND):
            await wolfhound.choose_wolfhound_role([Role.VILLAGER, Role.WEREWOLF])
        if amor := self.get_player_with_role(Role.AMOR):
            await amor.choose_lovers()
        if pure_soul := self.get_player_with_role(Role.PURE_SOUL):
            await self.announce_pure_soul(pure_soul)
        if medium := self.get_player_with_role(Role.MEDIUM):
            await medium.medium_resurrect()
        if seer := self.get_player_with_role(Role.SEER):
            await seer.check_player_card()
        if aura_seer := self.get_player_with_role(Role.AURA_SEER):
            await aura_seer.check_player_aura()
        if sheriff_role := self.get_player_with_role(Role.SHERIFF):
            await sheriff_role.check_sheriff_target()
        if fox := self.get_player_with_role(Role.FOX):
            await fox.check_3_werewolves()
        if judge := self.get_player_with_role(Role.JUDGE):
            await judge.get_judge_symbol()
        if sisters := self.get_players_with_role(Role.SISTER):
            await self.ctx.send(_("**The Sisters awake...**"))
            for player in sisters:
                await player.send_family_msg("sister", sisters)
        if brothers := self.get_players_with_role(Role.BROTHER):
            await self.ctx.send(_("**The Brothers awake...**"))
            for player in brothers:
                await player.send_family_msg("brother", brothers)
        if troublemaker := self.get_player_with_role(Role.TROUBLEMAKER):
            await troublemaker.choose_2_to_exchange()
        await self.ensure_head_hunter_targets()
        if wolf_seer := self.get_player_with_role(Role.WOLF_SEER):
            await wolf_seer.check_wolf_seer_target()
        target = await self.wolves()
        targets = [target] if target is not None else []
        if (
                sum(
                    1
                    for player in self.players
                    if player.dead and player.side in (Side.WOLVES, Side.WHITE_WOLF)
                )
                == 0
        ):
            if big_bad_wolf := self.get_player_with_role(Role.BIG_BAD_WOLF):
                if target := await big_bad_wolf.choose_villager_to_kill(targets):
                    targets.append(target)
        if wolf_shaman := self.get_player_with_role(Role.WOLF_SHAMAN):
            await wolf_shaman.protect_werewolf()
        targets = await self.apply_cursed_conversion(targets)
        targets = await self.apply_night_protection(targets)
        if knight := discord.utils.get(targets, role=Role.KNIGHT):
            knight.attacked_by_the_pact = True
        if witch := self.get_player_with_role(Role.WITCH):
            targets = await witch.witch_actions(targets)
        if flutist := self.get_player_with_role(Role.FLUTIST):
            await flutist.enchant()
        if superspreader := self.get_player_with_role(Role.SUPERSPREADER):
            await superspreader.infect_virus()
        return targets

    async def night(self, white_wolf_ability: bool) -> list[Player]:
        moon = "🌕" if white_wolf_ability else "🌘"
        await self._set_night_chat_lock(True)
        await self.ctx.send(moon + _(" 💤 **Night falls, the town is asleep...**"))
        fortune_teller_acted = False
        if self.ex_maid and self.ex_maid.dead:
            self.ex_maid = None
        elif self.ex_maid:
            # Call ex-maid's new role like it's the first night
            if self.ex_maid.role == Role.THIEF:
                await self.ex_maid.choose_thief_role()
            elif self.ex_maid.role == Role.LOUDMOUTH:
                await self.start_loudmouth_target_selection()
            elif self.ex_maid.role == Role.AVENGER:
                await self.start_avenger_target_selection()
            if self.ex_maid.role == Role.WOLFHOUND:
                await self.ex_maid.choose_wolfhound_role([Role.VILLAGER, Role.WEREWOLF])
            elif self.ex_maid.role == Role.AMOR:
                await self.ex_maid.choose_lovers()
            elif self.ex_maid.role == Role.PURE_SOUL:
                await self.announce_pure_soul(self.ex_maid)
            elif self.ex_maid.role == Role.TROUBLEMAKER:
                await self.ex_maid.choose_2_to_exchange()
            elif self.ex_maid.role == Role.JUDGE:
                await self.ex_maid.get_judge_symbol()
            elif self.ex_maid.role == Role.SISTER:
                sisters = self.get_players_with_role(Role.SISTER)
                for player in sisters:
                    if player == self.ex_maid:
                        continue
                    await player.send_family_member_msg("sister", self.ex_maid)
            elif self.ex_maid.role == Role.BROTHER:
                brothers = self.get_players_with_role(Role.BROTHER)
                for player in brothers:
                    if player == self.ex_maid:
                        continue
                    await player.send_family_member_msg("brother", self.ex_maid)
            elif self.ex_maid.role == Role.FORTUNE_TELLER:
                await self.ex_maid.give_fortune_card()
                fortune_teller_acted = True
            self.ex_maid = None
        if ritualist := self.get_player_with_role(Role.RITUALIST):
            await ritualist.resurrect()
        if medium := self.get_player_with_role(Role.MEDIUM):
            await medium.medium_resurrect()
        if wolf_necro := self.get_player_with_role(Role.WOLF_NECROMANCER):
            await wolf_necro.resurrect_werewolf()
        if raider := self.get_player_with_role(Role.RAIDER):
            await raider.choose_to_raid()
        if (
            not fortune_teller_acted
            and (fortune_teller := self.get_player_with_role(Role.FORTUNE_TELLER))
        ):
            await fortune_teller.give_fortune_card()
        await self.ensure_head_hunter_targets()
        await self.activate_jail_for_night()
        if seer := self.get_player_with_role(Role.SEER):
            await seer.check_player_card()
        if aura_seer := self.get_player_with_role(Role.AURA_SEER):
            await aura_seer.check_player_aura()
        if sheriff_role := self.get_player_with_role(Role.SHERIFF):
            await sheriff_role.check_sheriff_target()
        if fox := self.get_player_with_role(Role.FOX):
            await fox.check_3_werewolves()
        if wolf_seer := self.get_player_with_role(Role.WOLF_SEER):
            await wolf_seer.check_wolf_seer_target()
        target = await self.wolves()
        targets = [target] if target is not None else []
        if white_wolf_ability:
            if white_wolf := self.get_player_with_role(Role.WHITE_WOLF):
                target = await white_wolf.choose_werewolf()
                if target:
                    targets.append(target)
        if (
                sum(
                    1
                    for player in self.players
                    if player.dead and player.side in (Side.WOLVES, Side.WHITE_WOLF)
                )
                == 0
        ):
            if big_bad_wolf := self.get_player_with_role(Role.BIG_BAD_WOLF):
                if target := await big_bad_wolf.choose_villager_to_kill(targets):
                    targets.append(target)
        if wolf_shaman := self.get_player_with_role(Role.WOLF_SHAMAN):
            await wolf_shaman.protect_werewolf()
        targets = await self.apply_cursed_conversion(targets)
        targets = await self.apply_night_protection(targets)
        if knight := discord.utils.get(targets, role=Role.KNIGHT):
            knight.attacked_by_the_pact = True
        if witch := self.get_player_with_role(Role.WITCH):
            targets = await witch.witch_actions(targets)
        if flutist := self.get_player_with_role(Role.FLUTIST):
            await flutist.enchant()
        if superspreader := self.get_player_with_role(Role.SUPERSPREADER):
            await superspreader.infect_virus()
        return targets

    async def election(self) -> discord.Member | None:
        paginator = commands.Paginator(prefix="", suffix="")
        players = ""
        eligible_players_lines = []
        election_players = [player for player in self.alive_players if not player.is_jailed]
        for player in election_players:
            if len(players + player.user.mention + " ") > 1900:
                paginator.add_line(players)
                eligible_players_lines.append(players)
                players = ""
            players += player.user.mention + " "
            if player == election_players[-1]:
                paginator.add_line(players[:-1])
                eligible_players_lines.append(players[:-1])
        paginator.add_line(
            _(
                "You may now submit someone (up to 10 total) for the election who to"
                " lynch by mentioning their name below. You have {timer} seconds of"
                " discussion during this time."
            ).format(timer=self.timer)
        )
        for page in paginator.pages:
            await self.ctx.send(page)
        nominated_by_paragon = []
        nominated = []
        second_election = False
        eligible_players = [player.user for player in election_players]
        eligible_player_by_user = {player.user: player for player in election_players}
        if not eligible_players:
            return None, second_election
        try:
            async with asyncio.timeout(self.timer) as cm:
                sneaky = False
                start = datetime.datetime.utcnow()
                while len(nominated) < 10:
                    msg = await self.ctx.bot.wait_for(
                        "message",
                        check=lambda x: x.author in eligible_players
                                        and x.channel.id == self.ctx.channel.id
                                        and (
                                                len(x.mentions) > 0
                                                or (
                                                        x.content == self.judge_symbol and not self.judge_spoken
                                                )
                                                or ("objection" in x.content.lower())
                                        ),
                    )
                    if "objection" in msg.content.lower() and discord.utils.get(
                            self.alive_players,
                            role=Role.LAWYER,
                            user=msg.author,
                            has_objected=False,
                    ):
                        lawyer = self.get_player_with_role(Role.LAWYER)
                        lawyer.has_objected = True
                        await self.ctx.send(
                            _(
                                "**OBJECTION!!!** the **{role}** {user} protested."
                                " Nomination ends."
                            ).format(role=lawyer.role_name, user=lawyer.user.mention)
                        )
                        nominated_by_paragon.clear()
                        nominated.clear()
                        raise asyncio.TimeoutError()
                    if msg.content == self.judge_symbol and discord.utils.get(
                            self.alive_players, role=Role.JUDGE, user=msg.author
                    ):
                        second_election = True
                        self.judge_spoken = True
                        judge = self.get_player_with_role(Role.JUDGE)
                        await judge.send(
                            _(
                                "I received your secret phrase. We will hold another"
                                " election after this."
                            )
                        )
                    paragon = discord.utils.get(
                        self.alive_players, role=Role.PARAGON, user=msg.author
                    )
                    for user in msg.mentions:
                        if user in eligible_players and (
                                (user not in nominated and len(nominated) < 10)
                                or (
                                        user not in nominated_by_paragon
                                        and len(nominated_by_paragon) < 10
                                        and paragon
                                )
                        ):
                            if paragon:
                                nominated_by_paragon.append(user)
                                announce = _(
                                    "**{role} {player}** nominated **{nominee}**."
                                ).format(
                                    role=paragon.role_name,
                                    player=msg.author,
                                    nominee=user,
                                )
                                if user not in nominated:
                                    nominated.append(user)
                            else:
                                nominated.append(user)
                                announce = _(
                                    "**{player}** nominated **{nominee}**."
                                ).format(player=msg.author, nominee=user)
                            if len(nominated) == 1:
                                mention_time = datetime.datetime.utcnow()
                                if (mention_time - start) >= datetime.timedelta(
                                        seconds=self.timer - 10
                                ):
                                    # Seems sneaky, extend talk time when there's only 10 seconds left
                                    time_to_add = int(self.timer / 2)
                                    finaltime = self.timer + time_to_add
                                    await self.ctx.send(
                                        _(
                                            "{finaltime}"
                                        ).format(finaltime=finaltime)
                                    )
                                    sneaky = True

                                    await self.ctx.send(
                                        _(
                                            _(
                                                "Seems sneaky, I added {time_to_add}"
                                                " seconds talk time."
                                            ).format(time_to_add=time_to_add)
                                        ))
                            await self.ctx.send(announce)
        except asyncio.TimeoutError:

            pass
        if sneaky == True:
            try:
                async with asyncio.timeout(time_to_add) as cm:

                    start = datetime.datetime.utcnow()
                    while len(nominated) < 10:
                        msg = await self.ctx.bot.wait_for(
                            "message",
                            check=lambda x: x.author in eligible_players
                                            and x.channel.id == self.ctx.channel.id
                                            and (
                                                    len(x.mentions) > 0
                                                    or (
                                                            x.content == self.judge_symbol and not self.judge_spoken
                                                    )
                                                    or ("objection" in x.content.lower())
                                            ),
                        )
                        if "objection" in msg.content.lower() and discord.utils.get(
                                self.alive_players,
                                role=Role.LAWYER,
                                user=msg.author,
                                has_objected=False,
                        ):
                            lawyer = self.get_player_with_role(Role.LAWYER)
                            lawyer.has_objected = True
                            await self.ctx.send(
                                _(
                                    "**OBJECTION!!!** the **{role}** {user} protested."
                                    " Nomination ends."
                                ).format(role=lawyer.role_name, user=lawyer.user.mention)
                            )
                            nominated_by_paragon.clear()
                            nominated.clear()
                            raise asyncio.TimeoutError()
                        if msg.content == self.judge_symbol and discord.utils.get(
                                self.alive_players, role=Role.JUDGE, user=msg.author
                        ):
                            second_election = True
                            self.judge_spoken = True
                            judge = self.get_player_with_role(Role.JUDGE)
                            await judge.send(
                                _(
                                    "I received your secret phrase. We will hold another"
                                    " election after this."
                                )
                            )
                        paragon = discord.utils.get(
                            self.alive_players, role=Role.PARAGON, user=msg.author
                        )
                        for user in msg.mentions:
                            if user in eligible_players and (
                                    (user not in nominated and len(nominated) < 10)
                                    or (
                                            user not in nominated_by_paragon
                                            and len(nominated_by_paragon) < 10
                                            and paragon
                                    )
                            ):
                                if paragon:
                                    nominated_by_paragon.append(user)
                                    announce = _(
                                        "**{role} {player}** nominated **{nominee}**."
                                    ).format(
                                        role=paragon.role_name,
                                        player=msg.author,
                                        nominee=user,
                                    )
                                    if user not in nominated:
                                        nominated.append(user)
                                else:
                                    nominated.append(user)
                                    announce = _(
                                        "**{player}** nominated **{nominee}**."
                                    ).format(player=msg.author, nominee=user)

                                await self.ctx.send(announce)
            except asyncio.TimeoutError:

                pass
        sneaky = False
        if len(nominated_by_paragon) > 0:
            nominated = nominated_by_paragon
        if not nominated:
            return None, second_election
        if len(nominated) == 1:
            return nominated[0], second_election
        emojis = ([f"{index + 1}\u20e3" for index in range(9)] + ["\U0001f51f"])[
                 : len(nominated)
                 ]
        texts = "\n".join(
            [f"{emoji} - {user.mention}" for emoji, user in zip(emojis, nominated)]
        )
        paginator.clear()
        for line in eligible_players_lines:
            paginator.add_line(line)
        paginator.add_line(
            _(
                "**React to vote for killing someone. You have {timer} seconds"
                ".**\n{texts}"
            ).format(timer=self.timer, texts=texts)
        )
        for page in paginator.pages:
            msg = await self.ctx.send(page)
        for emoji in emojis:
            await msg.add_reaction(emoji)
        # Check for nuisance voters twice, first at half of action timer, and lastly just before counting votes
        await self.check_nuisances(msg, eligible_players, emojis, repeat=2)
        msg = await self.ctx.channel.fetch_message(msg.id)
        nominated = {u: 0 for u in nominated}
        mapping = {emoji: user for emoji, user in zip(emojis, nominated)}
        voters = []
        for reaction in msg.reactions:
            if str(reaction.emoji) in emojis:
                nominated[mapping[str(reaction.emoji)]] = sum(
                    [
                        2
                        if eligible_player_by_user[user].is_sheriff
                        else 1
                        async for user in reaction.users()
                        if user in eligible_players
                    ]
                )
                voters += [
                    user
                    async for user in reaction.users()
                    if user in eligible_players and user not in voters
                ]
        failed_voters = set(eligible_players) - set(voters)
        for player in self.alive_players:
            if player.user in failed_voters:
                player.to_check_afk = True
        new_mapping = sorted(list(mapping.values()), key=lambda x: -nominated[x])
        return (
            (
                new_mapping[0]
                if len(new_mapping) == 1
                   or nominated[new_mapping[0]] > nominated[new_mapping[1]]
                else None
            ),
            second_election,
        )

    async def check_nuisances(self, msg, eligible_players, emojis, repeat: int) -> None:
        for i in range(repeat):
            await asyncio.sleep(int(self.timer / repeat))
            msg = await self.ctx.channel.fetch_message(msg.id)
            nuisance_voters = set()
            is_lacking_permission = None
            for reaction in msg.reactions:
                if str(reaction.emoji) in emojis:
                    nuisance_users = [
                        user
                        async for user in reaction.users()
                        if user not in eligible_players and user != self.ctx.me
                    ]
                    nuisance_voters.update(nuisance_users)
                    for to_remove in nuisance_users:
                        try:
                            await msg.remove_reaction(reaction.emoji, to_remove)
                        except discord.Forbidden:
                            is_lacking_permission = True
                            continue
                        except Exception as e:
                            await send_traceback(self.ctx, e)
                            raise
            if len(nuisance_voters):
                paginator = commands.Paginator(prefix="", suffix="")
                for nuisance_voter in nuisance_voters:
                    paginator.add_line(nuisance_voter.mention)
                paginator.add_line(
                    _(
                        "**You should not vote since you're not in the game. Please do"
                        " not try to influence the game by voting unnecessarily. I will"
                        " remove your reactions.**"
                    )
                )
                if is_lacking_permission:
                    paginator.add_line(
                        _(
                            "**{author} I couldn't remove reactions. Please give me the"
                            " proper permissions to remove reactions.**"
                        ).format(author=self.ctx.author.mention)
                    )
                for page in paginator.pages:
                    await self.ctx.send(page)

    async def handle_afk(self) -> None:
        if self.winner is not None:
            return
        if len(self.new_afk_players) < 1:
            return

        await self.ctx.send(
            _(
                "Checking AFK players if they're still in the game... Should be done in"
                " {timer} seconds."
            ).format(timer=self.timer)
        )

        afk_players_to_kill = []

        async def prompt_player(player):
            try:
                await player.send(f"AFK CHECK {player.user.mention}!")
                result = await self.ctx.bot.paginator.Choose(
                    entries=["Not AFK"],
                    return_index=True,
                    title=("Please use the dropdown"
                           " so I can acknowledge that you're not AFK. You have {timer}"
                           " seconds."),
                    timeout=self.timer,
                ).paginate(self.ctx, player.user)

                # Check if the player selected "Not AFK" and send the message
                if result == 0:  # 0 indicates "Not AFK"
                    await player.send(_("You have been verified as not AFK."))
                    return True  # Return True indicating the player responded

            except self.ctx.bot.paginator.NoChoice:
                pass  # Player didn't respond, no need to increment strikes

            # If the function reaches here, it means player didn't respond
            return False  # Return False indicating the player didn't respond

        # Gather results of the prompt_player function
        results = await asyncio.gather(*[prompt_player(player) for player in self.new_afk_players])

        for player, result in zip(self.new_afk_players, results):
            if not result:
                # Player didn't choose anything
                player.afk_strikes += 1
                if player.afk_strikes >= 3:
                    if not player.dead:
                        await player.send(
                            _("**Strike 3!** You will now be killed by"
                              " the game for having 3 strikes of being AFK. Goodbye!")
                        )
                        afk_players_to_kill.append(player)
                else:
                    await player.send(
                        _("⚠️ **Strike {strikes}!** You have been"
                          " marked as AFK. __You'll be killed after 3 strikes.__"
                          ).format(strikes=player.afk_strikes)
                    )

        # Kill the AFK players if needed
        for afk_player in afk_players_to_kill:
            await self.ctx.send(
                _("**{afk_player}** has been killed by"
                  " the game due to having 3 strikes of AFK."
                  ).format(afk_player=afk_player.user.mention)
            )
            await afk_player.kill()

    async def handle_lynching(self, to_kill: discord.Member) -> None:
        await self.ctx.send(
            _("The community has decided to kill {to_kill}.").format(
                to_kill=to_kill.mention
            )
        )
        to_kill = discord.utils.get(self.alive_players, user=to_kill)
        if to_kill is None:
            return

        flower_child = self.get_player_with_role(Role.FLOWER_CHILD)
        if (
            flower_child
            and not flower_child.dead
            and flower_child.can_use_flower_child
        ):
            used_save = await flower_child.try_flower_child_save(to_kill)
            if used_save:
                flower_child.used_once_abilities.add(Role.FLOWER_CHILD)
                to_kill.killed_by_lynch = False
                await self.ctx.send(
                    _(
                        "🌸 A mystical bloom saved {target} from being lynched."
                    ).format(target=to_kill.user.mention)
                )
                return

        to_kill.killed_by_lynch = True
        # Handle maid here
        if maid := self.get_player_with_role(Role.MAID):
            if maid != to_kill:
                if to_kill.lives == 1 or to_kill.role == Role.THE_OLD:
                    await maid.handle_maid(to_kill)
        if to_kill.role in [Role.THE_OLD, Role.WAR_VETERAN]:
            to_kill.died_from_villagers = True
            to_kill.lives = 1
        await to_kill.kill()

    async def handle_rusty_sword_effect(self) -> None:
        possible_werewolves = [
            p for p in self.alive_players if p.side in (Side.WOLVES, Side.WHITE_WOLF)
        ]
        to_die = random.choice(possible_werewolves)
        await self.ctx.send(
            _(
                "{to_die} died from the disease caused by the Knight's rusty sword."
            ).format(to_die=to_die.user.mention)
        )
        self.rusty_sword_disease_night = None
        await to_die.kill()

    async def handle_resurrection(self, to_resurrect: Player) -> None:
        to_resurrect.lives = 1 if to_resurrect.role != Role.THE_OLD else 2
        to_resurrect.died_from_villagers = False
        to_resurrect.killed_by_lynch = False
        if to_resurrect.role == Role.BODYGUARD:
            to_resurrect.bodyguard_intercepts = 0
        await self.sync_player_ww_role(to_resurrect)
        await self._ensure_medium_relay()

    async def queue_night_resurrection(
            self, caster: Player, to_resurrect: Player
    ) -> bool:
        if to_resurrect.dead is False:
            return False
        if any(target == to_resurrect for _, target, _ in self.pending_night_resurrections):
            return False
        self.pending_night_resurrections.append((caster, to_resurrect, caster.role))
        return True

    async def resolve_night_resurrections(self) -> None:
        if not self.pending_night_resurrections:
            return

        queued = self.pending_night_resurrections.copy()
        self.pending_night_resurrections.clear()
        for caster, to_resurrect, source_role in queued:
            if not to_resurrect.dead:
                continue

            await self.handle_resurrection(to_resurrect)
            if source_role == Role.RITUALIST:
                await self.ctx.send(
                    _("{player} has been resurrected!").format(
                        player=to_resurrect.user.mention
                    )
                )
                await to_resurrect.send(
                    _("You have been resurrected as **{role}!**\n{game_link}").format(
                        role=to_resurrect.role_name, game_link=self.game_link
                    )
                )
            elif source_role == Role.WOLF_NECROMANCER:
                await self.ctx.send(
                    _("**{player}** came back to life!").format(
                        player=to_resurrect.user.mention
                    )
                )
                await to_resurrect.send(
                    _("You came back to life as **{role}!**\n{game_link}").format(
                        role=self.get_role_name(to_resurrect),
                        game_link=self.game_link,
                    )
                )
            elif source_role == Role.MEDIUM:
                await self.ctx.send(
                    _("🔮 **{player}** was resurrected by the **Medium**!").format(
                        player=to_resurrect.user.mention
                    )
                )
                await to_resurrect.send(
                    _(
                        "You have been resurrected by the **Medium** as **{role}**."
                        "\n{game_link}"
                    ).format(
                        role=to_resurrect.role_name,
                        game_link=self.game_link,
                    )
                )
            else:
                await self.ctx.send(
                    _("{player} has been resurrected!").format(
                        player=to_resurrect.user.mention
                    )
                )

    async def day(self, deaths: list[Player]) -> None:
        await self._set_night_chat_lock(False)
        await self.release_jailed_player()
        await self.ctx.send(_("🌤️ **The sun rises...**"))
        if self.task:
            self.task.cancel()
        await self.start_jailer_day_target_selection()
        await self.start_junior_day_mark_selection()
        await self.start_loudmouth_target_selection()
        await self.start_avenger_target_selection()
        try:
            for death in deaths:
                await death.kill()
            if not self.after_first_night and self.night_no == 1:
                self.after_first_night = True
            await self.resolve_night_resurrections()
            if self.rusty_sword_disease_night is not None:
                if self.rusty_sword_disease_night == 0:
                    self.rusty_sword_disease_night += 1
                elif self.rusty_sword_disease_night == 1:
                    await self.handle_rusty_sword_effect()
            if len(self.alive_players) < 2:
                return
            if self.winner is not None:
                return
            await self.offer_fortune_card_reveals()
            to_kill, second_election = await self.election()
            if to_kill is not None:
                await self.handle_lynching(to_kill)
                if self.winner is not None:
                    return
            else:
                await self.ctx.send(
                    _("Indecisively, the community has killed noone.")
                )
            await self.handle_afk()
            if second_election:
                await self.ctx.send(
                    _(
                        "📢 **The Judge used the secret phrase to hold another election to"
                        " lynch someone. The Judge's decision cannot be debated.**"
                    )
                )
                to_kill, second_election = await self.election()
                if to_kill is not None:
                    await self.handle_lynching(to_kill)
                    if self.winner is not None:
                        return
                else:
                    await self.ctx.send(
                        _("Indecisively, the community has not lynched anyone.")
                    )
                await self.handle_afk()
        finally:
            await self.stop_jailer_day_target_selection()
            await self.stop_junior_day_mark_selection()

    async def run(self):
        try:
            # Handle thief etc and first night
            round_no = 1
            self.night_no = 1
            deaths = await self.initial_preparation()
            while True:
                if round_no % 2 == 1:
                    if self.speed in ("Fast", "Blitz"):
                        day_count = _("**Day {day_count:.0f} of {days_limit}**").format(
                            day_count=self.night_no, days_limit=len(self.players) + 3
                        )
                    else:
                        day_count = _("**Day {day_count:.0f}**").format(
                            day_count=self.night_no
                        )
                    await self.ctx.send(day_count)
                    await self.day(deaths)
                    if self.winner is not None:
                        break
                    if self.speed in ("Fast", "Blitz"):
                        if self.night_no == len(self.players) + 3:
                            await self.ctx.send(
                                _(
                                    "{day_count:.0f} days have already passed. Stopping"
                                    " game..."
                                ).format(day_count=self.night_no)
                            )
                            if self.task:
                                self.task.cancel()
                            break
                else:
                    self.night_no += 1
                    deaths = await self.night(white_wolf_ability=self.night_no % 2 == 0)
                    self.recent_deaths = []
                round_no += 1

            winner = self.winner
            if self.task:
                self.task.cancel()
            results_pretext = _("Werewolf {mode} results:").format(mode=self.mode)

            try:
                if isinstance(winner, Player):
                    if not self.winning_side:
                        self.winning_side = winner.role_name
                    paginator = commands.Paginator(prefix="", suffix="")
                    paginator.add_line(
                        _(
                            "{results_pretext} **The {winning_side} won!** 🎉 Congratulations:"
                        ).format(
                            results_pretext=results_pretext, winning_side=self.winning_side
                        )
                    )
                    for page in paginator.pages:
                        await self.ctx.send(page)
                    await self.send_endgame_team_embed(winner)
                else:
                    # Display winner information
                    await self.ctx.send(
                        _("{results_pretext} **{winner} won!**").format(
                            results_pretext=results_pretext, winner=winner
                        )
                    )
                    await self.send_endgame_team_embed(winner)
            except Exception as e:
                await send_traceback(self.ctx, e)
                if self.task:
                    self.task.cancel()
        finally:
            try:
                await self.stop_jailer_day_target_selection()
            except Exception:
                pass
            try:
                await self.stop_junior_day_mark_selection()
            except Exception:
                pass
            try:
                await self.stop_loudmouth_target_selection()
            except Exception:
                pass
            try:
                await self.stop_avenger_target_selection()
            except Exception:
                pass
            try:
                await self.release_jailed_player()
            except Exception:
                pass
            try:
                await self._stop_medium_relay()
            except Exception:
                pass
            try:
                await self._set_night_chat_lock(False)
            except Exception:
                pass
            try:
                await self._open_postgame_everyone_chat(120)
            except Exception:
                pass
            try:
                await self._set_everyone_chat_lock(False)
            except Exception:
                pass
            try:
                await self.cleanup_ww_player_roles()
            except Exception:
                pass

    def get_players_roles(self, has_won: bool = False) -> list[str]:
        if len(self.alive_players) < 1:
            return ""
        else:
            players_to_reveal = []
            for player in self.alive_players:
                if player.has_won == has_won:
                    if (
                            player.role != player.initial_roles[0]
                            or len(player.initial_roles) > 1
                    ):
                        initial_role_info = _(
                            " A **{initial_roles}** initially."
                        ).format(
                            initial_roles=", ".join(
                                [
                                    self.get_role_name(initial_role)
                                    for initial_role in player.initial_roles
                                ]
                            )
                        )
                    else:
                        initial_role_info = ""
                    players_to_reveal.append(
                        _("{player} is a **{role}**!{initial_role_info}").format(
                            player=player.user.mention,
                            role=self.get_role_name(player),
                            initial_role_info=initial_role_info,
                        )
                    )
            return players_to_reveal

    async def reveal_others(self) -> None:
        if len([p for p in self.alive_players if p.has_won is False]) < 1:
            return
        paginator = commands.Paginator(prefix="", suffix="")
        paginator.add_line(
            _("The game has ended. I will now reveal the other living players' roles:")
        )
        non_winners = self.get_players_roles(has_won=False)
        for non_winner in non_winners:
            paginator.add_line(non_winner)
        for page in paginator.pages:
            await self.ctx.send(page)

    def _winning_team_bucket(self, winner: Player | str | None) -> str | None:
        if isinstance(winner, Player):
            if winner.side == Side.VILLAGERS:
                return "Villagers"
            if winner.side == Side.WOLVES:
                return "Werewolves"
            return "Loners"

        candidates = [self.winning_side, winner]
        normalized = " ".join(
            str(value).strip().lower() for value in candidates if value is not None
        )
        if not normalized or normalized == "no one":
            return None
        if "villager" in normalized:
            return "Villagers"
        if "werewolf" in normalized:
            return "Werewolves"
        if any(
            key in normalized
            for key in (
                "white wolf",
                "flutist",
                "superspreader",
                "jester",
                "head hunter",
                "lover",
            )
        ):
            return "Loners"
        return None

    async def send_endgame_team_embed(self, winner: Player | str | None) -> None:
        teams: dict[str, list[str]] = {
            "Villagers": [],
            "Werewolves": [],
            "Loners": [],
        }

        for player in self.players:
            if player.side == Side.VILLAGERS:
                bucket = "Villagers"
            elif player.side == Side.WOLVES:
                bucket = "Werewolves"
            else:
                bucket = "Loners"

            player_name = getattr(player.user, "display_name", str(player.user))
            teams[bucket].append(f"{player_name} - {self.get_role_name(player)}")

        for team in teams:
            teams[team].sort(key=str.casefold)

        winning_bucket = self._winning_team_bucket(winner)
        title = _("Final Teams")
        colour = getattr(
            self.ctx.bot.config.game,
            "primary_colour",
            discord.Colour.blurple(),
        )
        embed = discord.Embed(title=title, colour=colour)

        for team_name in ("Villagers", "Werewolves", "Loners"):
            heading = team_name
            if winning_bucket == team_name:
                heading = f"{team_name} (WIN)"
            entries = teams[team_name]
            value = "\n".join(entries) if entries else _("None")
            embed.add_field(name=heading, value=value[:1024], inline=False)

        winner_ids = [player.user.id for player in self.players if player.has_won]
        if not winner_ids and isinstance(winner, Player):
            winner_ids = [winner.user.id]
        winner_ids = list(dict.fromkeys(winner_ids))
        all_ids = list(dict.fromkeys(player.user.id for player in self.players))

        await self.ctx.send(
            embed=embed,
            view=EndgameIdsView(winner_ids=winner_ids, all_ids=all_ids),
        )


class Player:
    def __init__(self, role: Role, user: discord.Member, game: Game) -> None:
        self.role = role
        self.initial_roles = [role]
        self.user = user
        self.game = game
        self.is_sheriff = False
        self.enchanted = False
        self.infected_with_virus = False
        self.idol = None
        self.headhunter_target = None
        self.is_jailed = False
        self.is_protected = False
        self.protected_by_doctor = False
        self.protected_by_bodyguard: Player | None = None
        self.protected_by_jailer = False
        self.bodyguard_intercepts = 0
        self.fortune_cards = 0
        self.fortune_cards_remaining = None
        self.used_once_abilities: set[Role] = set()
        self.cursed = False
        self.revealed_roles = {}
        self.loudmouth_target: Player | None = None
        self.avenger_target: Player | None = None

        # Witch
        self.can_heal = True
        self.can_kill = True

        # Healer
        self.last_target = None

        # Fox
        self.has_fox_ability = True

        # Maid
        self.exchanged_with_maid = False

        # The Old
        self.died_from_villagers = False
        self.killed_by_lynch = False
        if role == Role.THE_OLD:
            self.lives = 2
        else:
            self.lives = 1

        # Rusty Sword Knight
        self.attacked_by_the_pact = False

        # Cursed Wolf Father
        self.has_cursed_wolf_father_ability = True

        # Raider
        self.has_raided = False

        # Ritualist
        self.has_ritualist_ability = True

        # lawyer
        self.has_objected = False

        # Wolf Shaman
        self.has_wolf_shaman_ability = True

        # Wolf Necromancer
        self.has_wolf_necro_ability = True

        # Jailer
        self.has_jailer_execution_ability = True

        # Medium
        self.has_medium_revive_ability = True

        # Junior Werewolf
        self.junior_mark_target: Player | None = None

        # AFK check
        self.afk_strikes = 0
        self.to_check_afk = False

    def __repr__(self):
        return (
            f"<Player role={self.role} initial_role={self.initial_roles}"
            f" is_sheriff={self.is_sheriff} lives={self.lives} side={self.side}"
            f" dead={self.dead} won={self.has_won}>"
        )

    async def send(self, *args, **kwargs) -> discord.Message | None:
        try:
            return await self.user.send(*args, **kwargs)
        except (discord.Forbidden, discord.HTTPException):
            pass

    @property
    def can_use_flower_child(self) -> bool:
        return (
            self.role == Role.FLOWER_CHILD
            and Role.FLOWER_CHILD not in self.used_once_abilities
        )

    def ensure_fortune_teller_cards(self) -> None:
        if self.role != Role.FORTUNE_TELLER:
            return
        if self.fortune_cards_remaining is None:
            self.fortune_cards_remaining = 1 if len(self.game.players) <= 7 else 2

    async def choose_users(
            self,
            title: str,
            list_of_users: list[Player],
            amount: int,
            required: bool = True,
            timeout: int | None = None,
    ) -> list[Player]:
        if self.is_jailed:
            await self.send(
                _(
                    "🔒 You are jailed and cannot use your abilities right now."
                    "\n{game_link}"
                ).format(game_link=self.game.game_link)
            )
            return []
        if not list_of_users or amount <= 0:
            return []

        def build_entries(players: list[Player]) -> list[str]:
            return [
                f"{player.user} {player.user.mention} "
                f"{self.game.get_role_name(self.revealed_roles[player]) if player in self.revealed_roles else ''}".strip()
                for player in players
            ]

        def build_choices(players: list[Player]) -> list[str]:
            # Discord select labels are max 100 chars.
            return [str(player.user)[:100] for player in players]

        async def select_from_dropdown(
            candidates: list[Player], *, can_dismiss: bool, header: str
        ) -> Player | None:
            if not candidates:
                return None
            menu_title = header[:250]

            if len(candidates) == 1 and not can_dismiss:
                return candidates[0]

            max_players_per_menu = 24 if can_dismiss else 25
            selected_pool = candidates

            if len(candidates) > max_players_per_menu:
                chunks = [
                    candidates[i : i + max_players_per_menu]
                    for i in range(0, len(candidates), max_players_per_menu)
                ]
                chunk_entries = [
                    _("Players {start}-{end}").format(
                        start=(index * max_players_per_menu) + 1,
                        end=(index * max_players_per_menu) + len(chunk),
                    )
                    for index, chunk in enumerate(chunks)
                ]
                chunk_choices = [
                    _("Group {num}").format(num=index + 1)
                    for index in range(len(chunks))
                ]

                if can_dismiss:
                    chunk_entries.insert(0, _("Dismiss"))
                    chunk_choices.insert(0, _("Dismiss"))

                chunk_index = await self.game.ctx.bot.paginator.Choose(
                    entries=chunk_entries,
                    choices=chunk_choices,
                    return_index=True,
                    title=menu_title,
                    timeout=timeout if timeout is not None else self.game.timer,
                ).paginate(self.game.ctx, location=self.user)

                if can_dismiss and chunk_index == 0:
                    return None

                selected_pool = chunks[chunk_index - 1 if can_dismiss else chunk_index]

            menu_entries = build_entries(selected_pool)
            menu_choices = build_choices(selected_pool)
            if can_dismiss:
                menu_entries.insert(0, _("Dismiss"))
                menu_choices.insert(0, _("Dismiss"))

            selection_index = await self.game.ctx.bot.paginator.Choose(
                entries=menu_entries,
                choices=menu_choices,
                return_index=True,
                title=menu_title,
                timeout=timeout if timeout is not None else self.game.timer,
            ).paginate(self.game.ctx, location=self.user)

            if can_dismiss and selection_index == 0:
                return None
            return selected_pool[selection_index - 1 if can_dismiss else selection_index]

        chosen: list[Player] = []
        while len(chosen) < amount:
            remaining = amount - len(chosen)
            candidates = [user for user in list_of_users if user not in chosen]
            if not candidates:
                break

            try:
                selected_player = await select_from_dropdown(
                    candidates,
                    can_dismiss=not required,
                    header=_("{title} ({remaining} choice(s) left)").format(
                        title=title, remaining=remaining
                    ),
                )
            except self.game.ctx.bot.paginator.NoChoice:
                await self.send(_("Selection timed out."))
                break
            except discord.Forbidden:
                await self.send(
                    _(
                        "I couldn't DM you the selection menu. Please enable direct"
                        " messages from server members."
                    )
                )
                break
            except discord.HTTPException:
                await self.send(
                    _(
                        "The selection menu failed due to a Discord API error. Please"
                        " try again."
                    )
                )
                break

            if selected_player is None:
                if not required and not chosen:
                    return []
                break

            if selected_player in chosen:
                await self.send(
                    _("🚫 You've chosen **{player}** already.").format(
                        player=selected_player.user
                    )
                )
                continue

            chosen.append(selected_player)
            if amount > 1:
                await self.send(
                    _("**{player}** has been selected.").format(
                        player=selected_player.user
                    )
                )

        return chosen

    async def send_information(self) -> None:
        await self.send(
            _("You are a **{role}**\n\n{description}").format(
                role=self.role_name, description=DESCRIPTIONS[self.role]
            )
        )

    async def send_love_msg(self, lover: Player, mode_effect: bool = False) -> None:
        if mode_effect:
            love_msg = _(
                "It's 💕Valentines💕! You fell in love with **{lover}**!"
                " You can eliminate all others and survive as **Lovers**."
                " Try to protect your lover as best as you can. You will immediately"
                " commit suicide once they die. May the best Lovers win!\n{game_link}"
            ).format(lover=lover.user, game_link=self.game.game_link)
        else:
            love_msg = _(
                "💕 You fell in love with **{lover}**! 💘 Amor really knew you had an eye"
                " on them... You can eliminate all others and survive as **Lovers**."
                " Try to protect your lover as best as you can. You will immediately"
                " commit suicide once they die.\n{game_link}"
            ).format(lover=lover.user, game_link=self.game.game_link)
        await self.send(love_msg)

    async def try_flower_child_save(self, to_save: Player) -> bool:
        if not self.can_use_flower_child or to_save.dead:
            return False
        await self.send(
            _(
                "🌸 You may protect **{target}** from this lynch once per game."
            ).format(target=to_save.user)
        )
        try:
            choice = await self.choose_users(
                _("Use Flower Child protection on this lynch?"),
                list_of_users=[to_save],
                amount=1,
                required=False,
            )
        except asyncio.TimeoutError:
            return False
        if choice:
            await self.send(
                _(
                    "You used your Flower Child protection to save **{target}**."
                ).format(target=to_save.user)
            )
            return True
        return False

    async def give_fortune_card(self) -> None:
        if self.role != Role.FORTUNE_TELLER or self.dead:
            return
        self.ensure_fortune_teller_cards()
        if not self.fortune_cards_remaining or self.fortune_cards_remaining <= 0:
            return

        await self.game.ctx.send(
            _("**The {role} awakes...**").format(role=self.role_name)
        )
        possible_targets = [p for p in self.game.alive_players if p != self]
        if not possible_targets:
            await self.send(
                _("No valid target to receive a Revelation Card.\n{game_link}").format(
                    game_link=self.game.game_link
                )
            )
            return

        try:
            chosen = await self.choose_users(
                _(
                    "Choose a player to receive a Revelation Card. They can use it to"
                    " reveal their role."
                ),
                list_of_users=possible_targets,
                amount=1,
                required=False,
            )
        except asyncio.TimeoutError:
            chosen = []

        if not chosen:
            await self.send(
                _(
                    "You decided not to give a Revelation Card tonight.\n{game_link}"
                ).format(game_link=self.game.game_link)
            )
            return

        target = chosen[0]
        target.fortune_cards += 1
        self.fortune_cards_remaining = max(0, self.fortune_cards_remaining - 1)
        await self.send(
            _(
                "You gave a Revelation Card to **{target}**. Remaining cards: {left}."
            ).format(target=target.user, left=self.fortune_cards_remaining)
        )
        await target.send(
            _(
                "🔮 You received a Revelation Card from the **Fortune Teller**. At"
                " dawn, you may choose to reveal your role.\n{game_link}"
            ).format(game_link=self.game.game_link)
        )

    async def offer_fortune_card_reveal(self) -> bool:
        if self.dead or self.fortune_cards <= 0:
            return False
        timeout = max(10, min(20, int(self.game.timer / 2)))
        try:
            choice = await self.game.ctx.bot.paginator.Choose(
                entries=[
                    _("Reveal your role now"),
                    _("Keep card for later"),
                ],
                return_index=True,
                title=_(
                    "Use a Revelation Card? You currently have {cards}."
                ).format(cards=self.fortune_cards),
                timeout=timeout,
            ).paginate(self.game.ctx, location=self.user)
        except (
            self.game.ctx.bot.paginator.NoChoice,
            discord.Forbidden,
            discord.HTTPException,
        ):
            return False

        if choice != 0:
            return False

        self.fortune_cards -= 1
        for player in self.game.players:
            player.revealed_roles.update({self: self.role})
        await self.game.ctx.send(
            _(
                "🔮 {player} used a Revelation Card and is revealed as a"
                " **{role}**!"
            ).format(player=self.user.mention, role=self.role_name)
        )
        await self.send(
            _(
                "Your role was revealed. Revelation Cards left: {cards}."
            ).format(cards=self.fortune_cards)
        )
        return True

    async def choose_idol(self) -> None:
        await self.game.ctx.send(
            _("**The {role} awakes and chooses its idol...**").format(
                role=self.role_name
            )
        )
        # Prefer alive players, but fall back to the game roster if state gets
        # desynced during reloads/interrupted interactions.
        possible_idols = [p for p in self.game.alive_players if p != self]
        if not possible_idols:
            possible_idols = [p for p in self.game.players if p != self and not p.dead]
        if not possible_idols:
            possible_idols = [p for p in self.game.players if p != self]
        if not possible_idols:
            await self.send(
                _("No valid idol could be chosen.\n{game_link}").format(
                    game_link=self.game.game_link
                )
            )
            return
        try:
            idol_choices = await self.choose_users(
                _("Choose your Idol. You will turn into a Werewolf if they die."),
                list_of_users=possible_idols,
                amount=1,
                required=True,
            )
            if idol_choices:
                idol = idol_choices[0]
            else:
                idol = random.choice(possible_idols)
                await self.send(
                    _(
                        "You didn't choose anyone. A random player will be chosen for"
                        " you."
                    )
                )
        except asyncio.TimeoutError:
            idol = random.choice(possible_idols)
            await self.send(
                _("You didn't choose anyone. A random player will be chosen for you.")
            )
        self.idol = idol
        await self.send(
            _("**{idol}** became your Idol.\n{game_link}").format(
                idol=self.idol.user, game_link=self.game.game_link
            )
        )

    async def get_judge_symbol(self) -> None:
        await self.game.ctx.send(
            _("**The {role} awakes...**").format(role=self.role_name)
        )
        self.game.judge_spoken = False
        await self.send(
            _(
                "🧑‍⚖️ Please enter a secret phrase that will trigger a second election."
                " It is case sensitive."
            )
        )
        try:
            msg = await self.game.ctx.bot.wait_for_dms(
                check={
                    "author": {"id": str(self.user.id)},
                    "channel_id": [
                        str(
                            self.user.dm_channel.id
                            if self.user.dm_channel is not None
                            else ""
                        )
                    ],
                },
                timeout=self.game.timer,
            )
            symbol = msg.content
        except asyncio.TimeoutError:
            symbol = "hahayes"
        await self.send(
            _(
                "The phrase is **{symbol}**. Enter it right during an"
                " election to trigger another one.\n{game_link}"
            ).format(symbol=symbol, game_link=self.game.game_link)
        )
        self.game.judge_symbol = symbol

    async def handle_maid(self, death: Player) -> None:
        if self.in_love and death in self.own_lovers:
            return
        try:
            action = await self.game.ctx.bot.paginator.Choose(
                entries=["Yes", "No"],
                return_index=True,
                title=_(
                    "Would you like to swap roles with {dying_one}? You will learn"
                    " their role once you accept."
                ).format(dying_one=death.user),
                timeout=self.game.timer,
            ).paginate(self.game.ctx, location=self.user)
        except self.game.ctx.bot.paginator.NoChoice:
            await self.send(_("You didn't choose anything."))
            return
        except (discord.Forbidden, discord.HTTPException):
            await self.game.ctx.send(
                _(
                    "I couldn't send a DM to someone. Too bad they missed to use their"
                    " power."
                )
            )
            return
        if action == 1:
            return
        if Role.WOLFHOUND in death.initial_roles or death.role == Role.WOLFHOUND:
            role_to_get = Role.WOLFHOUND
        else:
            role_to_get = death.role
        if death.initial_roles[-1] != death.role:
            death.initial_roles.append(death.role)
        death.role = self.role
        if self.initial_roles[-1] != self.role:
            self.initial_roles.append(self.role)
        self.role = role_to_get
        if self.role == Role.THE_OLD:
            self.lives = 2
            death.lives = 1
        self.game.ex_maid = self
        death.exchanged_with_maid = True
        await self.send(
            _("Your new role is now **{new_role}**.\n").format(new_role=self.role_name)
        )
        await self.send_information()
        await self.game.start_loudmouth_target_selection()
        await self.game.start_avenger_target_selection()
        if self.enchanted:
            self.enchanted = False
            await self.send(
                _("You're no longer enchanted by the {flutist}.").format(
                    flutist=self.game.get_role_name(Role.FLUTIST)
                )
            )
        await self.game.ctx.send(
            _(
                "**{maid}** reveals themselves as the **{role}** and exchanged"
                " roles with {dying_one}."
            ).format(maid=self.user, role=death.role_name, dying_one=death.user.mention)
        )
        if self.is_sheriff:
            await self.choose_new_sheriff(exclude=death)
        await self.send(self.game.game_link)

    async def set_healer_target(self) -> Player:
        await self.game.ctx.send(
            _("**The {role} awakes...**").format(role=self.role_name)
        )
        available = [
            player for player in self.game.alive_players if player != self.last_target
        ]
        self.last_target = None
        try:
            target = await self.choose_users(
                _("Choose a player to protect from Werewolves."),
                list_of_users=available,
                amount=1,
                required=False,
            )
            if target:
                target = target[0]
            else:
                await self.send(
                    _(
                        "You didn't choose to heal anyone. No one will be protected"
                        " from the werewolves tonight.\n{game_link}"
                    ).format(game_link=self.game.game_link)
                )
                return
        except asyncio.TimeoutError:
            await self.send(
                _(
                    "You didn't choose anyone, slowpoke. No one will be protected from"
                    " the werewolves tonight.\n{game_link}"
                ).format(game_link=self.game.game_link)
            )
            return
        self.last_target = target
        self.last_target.is_protected = True
        await self.send(
            _(
                "**{protected}** won't die from the werewolves tonight.\n{game_link}"
            ).format(protected=self.last_target.user, game_link=self.game.game_link)
        )

    async def set_doctor_target(self) -> None:
        await self.game.ctx.send(
            _("**The {role} awakes...**").format(role=self.role_name)
        )
        available = [player for player in self.game.alive_players]
        try:
            target = await self.choose_users(
                _("Choose a player to protect from attacks tonight."),
                list_of_users=available,
                amount=1,
                required=False,
            )
            if target:
                target = target[0]
            else:
                await self.send(
                    _(
                        "You didn't choose anyone to protect. No one is protected"
                        " tonight.\n{game_link}"
                    ).format(game_link=self.game.game_link)
                )
                return
        except asyncio.TimeoutError:
            await self.send(
                _(
                    "You didn't choose anyone, slowpoke. No one is protected"
                    " tonight.\n{game_link}"
                ).format(game_link=self.game.game_link)
            )
            return

        target.is_protected = True
        target.protected_by_doctor = True
        await self.send(
            _(
                "**{protected}** is protected from attacks tonight.\n{game_link}"
            ).format(protected=target.user, game_link=self.game.game_link)
        )

    async def choose_werewolf(self) -> Player | None:
        await self.game.ctx.send(
            _("**The {role} awakes...**").format(role=self.role_name)
        )
        possible_targets = [
            p
            for p in self.game.alive_players
            if p.side == Side.WOLVES and p not in self.own_lovers
        ]
        if not possible_targets:
            await self.send(
                _("There's no other werewolf left to kill.\n{game_link}").format(
                    game_link=self.game.game_link
                )
            )
            return
        else:
            try:
                target = await self.choose_users(
                    _("Choose a Werewolf to kill."),
                    list_of_users=possible_targets,
                    amount=1,
                    required=False,
                )
                if target:
                    target = target[0]
                else:
                    await self.send(
                        _(
                            "You didn't choose any werewolf to kill.\n{game_link}"
                        ).format(game_link=self.game.game_link)
                    )
                    return
            except asyncio.TimeoutError:
                await self.send(
                    _(
                        "You didn't choose any werewolf to kill, slowpoke.\n{game_link}"
                    ).format(game_link=self.game.game_link)
                )
                return
            await self.send(
                _("You chose to kill **{werewolf}**.\n{game_link}").format(
                    werewolf=target.user, game_link=self.game.game_link
                )
            )
            return target

    async def choose_villager_to_kill(self, targets: list[Player]) -> Player | None:
        await self.game.ctx.send(
            _("**The {role} awakes...**").format(role=self.role_name)
        )
        if not targets:
            await self.game.ctx.send(
                embed=discord.Embed(
                    title=_("Skipped Wolves Night"),
                    description=_("No one was killed during the night."),
                    color=discord.Color.blue(),
                )
            )
            return None
        possible_targets = [
            p
            for p in self.game.alive_players
            if p.side not in (Side.WOLVES, Side.WHITE_WOLF)
               and p not in targets + self.own_lovers
        ]
        if not possible_targets:
            await self.send(
                _(
                    "There's no other possible villagers left to kill.\n{game_link}"
                ).format(game_link=self.game.game_link)
            )
            return
        else:
            try:
                target = await self.choose_users(
                    _("Choose a Villager to kill."),
                    list_of_users=possible_targets,
                    amount=1,
                    required=False,
                )
                if target:
                    target = target[0]
                else:
                    await self.send(
                        _(
                            "You didn't choose any villager to kill.\n{game_link}"
                        ).format(game_link=self.game.game_link)
                    )
                    return
            except asyncio.TimeoutError:
                await self.send(
                    _(
                        "You didn't choose any villager to kill, slowpoke.\n{game_link}"
                    ).format(game_link=self.game.game_link)
                )
                return
            await self.send(
                _("You've decided to kill **{villager}**.\n{game_link}").format(
                    villager=target.user, game_link=self.game.game_link
                )
            )
            return target

    async def witch_actions(self, targets: list[Player]) -> Player:
        await self.game.ctx.send(
            _("**The {role} awakes...**").format(role=self.role_name)
        )
        if not self.can_heal and not self.can_kill:
            # Delay is given here so that the Witch will not be accused of using up all the abilities already
            await asyncio.sleep(random.randint(5, int(self.game.timer / 2)))
            return targets
        if any(targets) and self.can_heal:
            try:
                to_heal = await self.choose_users(
                    _(
                        "Choose someone to heal 🧪. You can rescue a player attacked by"
                        " the wolves once throughout the game. You can opt not to use"
                        " this ability for now."
                    ),
                    list_of_users=targets,
                    amount=1,
                    required=False,
                )
                if to_heal:
                    to_heal = to_heal[0]
                    targets.remove(to_heal)
                    self.can_heal = False
                    if to_heal.role == Role.KNIGHT:
                        to_heal.attacked_by_the_pact = False
                    await self.send(
                        _("You chose to heal **{healed}**.").format(healed=to_heal.user)
                    )
                else:
                    await self.send(_("You didn't choose to heal anyone."))
            except asyncio.TimeoutError:
                await self.send(
                    _(
                        "You didn't choose to heal anyone from the list, slowpoke."
                        " They're likely to die."
                    )
                )
        if self.can_kill:
            possible_targets = [
                p
                for p in self.game.alive_players
                if p != self and p not in targets + self.own_lovers
            ]
            try:
                to_kill = await self.choose_users(
                    _(
                        "Choose someone to poison ☠️. You can kill a"
                        " player once throughout the game. You can opt not to use this"
                        " ability for now."
                    ),
                    list_of_users=possible_targets,
                    amount=1,
                    required=False,
                )
                if to_kill:
                    to_kill = to_kill[0]
                    if to_kill.role == Role.THE_OLD:
                        # Bad choice
                        to_kill.died_from_villagers = True
                        to_kill.lives = 1
                    targets.append(to_kill)
                    self.can_kill = False
                    await self.send(
                        _("You've decided to poison **{poisoned}**.").format(
                            poisoned=to_kill.user
                        )
                    )
                else:
                    await self.send(_("You didn't choose to poison anyone."))
            except asyncio.TimeoutError:
                await self.send(
                    _("You've ran out of time and missed to poison anyone, slowpoke.")
                )
        else:
            # Delay is given here so that the Witch will not be accused of using up all the abilities already
            await asyncio.sleep(random.randint(5, int(self.game.timer / 2)))
            return targets
        await self.send(self.game.game_link)
        return targets

    async def enchant(self) -> None:
        await self.game.ctx.send(
            _("**The {role} awakes...**").format(role=self.role_name)
        )
        possible_targets = [
            p for p in self.game.alive_players if not p.enchanted and p != self
        ]
        if not possible_targets:
            await self.send(
                _(
                    "There's no other possible players left to enchant.\n{game_link}"
                ).format(game_link=self.game.game_link)
            )
            return
        if len(possible_targets) > 2:
            try:
                to_enchant = await self.choose_users(
                    _("Choose 2 people to enchant."),
                    list_of_users=possible_targets,
                    amount=2,
                    required=False,
                )
                if not to_enchant:
                    await self.send(
                        _("You didn't want to use your ability.\n{game_link}").format(
                            game_link=self.game.game_link
                        )
                    )
            except asyncio.TimeoutError:
                to_enchant = []
                await self.send(
                    _(
                        "You didn't choose enough players to enchant,"
                        " slowpoke.\n{game_link}"
                    ).format(game_link=self.game.game_link)
                )
                return
        else:
            await self.send(
                _(
                    "The last {count} possible targets have been"
                    " automatically enchanted for you."
                ).format(count=len(possible_targets))
            )
            to_enchant = possible_targets
        for p in to_enchant:
            p.enchanted = True
            await self.send(
                _("You have enchanted **{enchanted}**.").format(enchanted=p.user)
            )
            await p.send(
                _(
                    "You have been enchanted by the Flutist. Claim being enchanted to"
                    " narrow him down.\n{game_link}"
                ).format(game_link=self.game.game_link)
            )
        await self.send(self.game.game_link)

    async def send_family_msg(self, relationship: str, family: list[Player]) -> None:
        await self.send(
            _("Your {relationship}(s) are/is: {members}").format(
                relationship=relationship,
                members=" and ".join(["**" + str(u.user) + "**" for u in family]),
            )
        )

    async def send_family_member_msg(
            self, relationship: str, new_member: Player
    ) -> None:
        await self.send(
            _(
                "Your new {relationship} is: **{new_member}**. They don't know yet"
                " the other members of the family."
            ).format(relationship=relationship, new_member=new_member.user)
        )

    async def check_player_card(self) -> None:
        await self.game.ctx.send(
            _("**The {role} awakes...**").format(role=self.role_name)
        )
        try:
            to_inspect = await self.choose_users(
                _("👁️ Choose someone whose identity you would like to see."),
                list_of_users=[p for p in self.game.alive_players if p != self],
                amount=1,
                required=False,
            )
            if to_inspect:
                to_inspect = to_inspect[0]
            else:
                await self.send(
                    _(
                        "You didn't want to use your ability to see anyone's"
                        " role.\n{game_link}"
                    ).format(game_link=self.game.game_link)
                )
                return
        except asyncio.TimeoutError:
            await self.send(
                _(
                    "You've ran out of time and missed to see someone's role,"
                    " slowpoke.\n{game_link}"
                ).format(game_link=self.game.game_link)
            )
            return
        self.revealed_roles.update({to_inspect: to_inspect.role})
        await self.send(
            _("**{player}** is a **{role}**.\n{game_link}").format(
                player=to_inspect.user,
                role=to_inspect.role_name,
                game_link=self.game.game_link,
            )
        )

    async def check_player_aura(self) -> None:
        await self.game.ctx.send(
            _("**The {role} awakes...**").format(role=self.role_name)
        )
        try:
            to_inspect = await self.choose_users(
                _("🌗 Choose someone whose aura you would like to inspect."),
                list_of_users=[p for p in self.game.alive_players if p != self],
                amount=1,
                required=False,
            )
            if to_inspect:
                to_inspect = to_inspect[0]
            else:
                await self.send(
                    _(
                        "You didn't want to inspect anyone's aura.\n{game_link}"
                    ).format(game_link=self.game.game_link)
                )
                return
        except asyncio.TimeoutError:
            await self.send(
                _(
                    "You've ran out of time and missed to inspect someone's aura,"
                    " slowpoke.\n{game_link}"
                ).format(game_link=self.game.game_link)
            )
            return
        aura = _(get_aura_alignment(to_inspect))
        await self.send(
            _("**{player}** has a **{aura} aura**.\n{game_link}").format(
                player=to_inspect.user,
                aura=aura,
                game_link=self.game.game_link,
            )
        )

    async def check_sheriff_target(self) -> None:
        await self.game.ctx.send(
            _("**The {role} awakes...**").format(role=self.role_name)
        )
        try:
            to_inspect = await self.choose_users(
                _("🕵️ Choose someone to investigate."),
                list_of_users=[p for p in self.game.alive_players if p != self],
                amount=1,
                required=False,
            )
            if to_inspect:
                to_inspect = to_inspect[0]
            else:
                await self.send(
                    _(
                        "You didn't want to investigate anyone.\n{game_link}"
                    ).format(game_link=self.game.game_link)
                )
                return
        except asyncio.TimeoutError:
            await self.send(
                _(
                    "You've ran out of time and missed your investigation,"
                    " slowpoke.\n{game_link}"
                ).format(game_link=self.game.game_link)
            )
            return
        suspicious = to_inspect.side in (Side.WOLVES, Side.WHITE_WOLF)
        verdict = _("Suspicious") if suspicious else _("Not suspicious")
        await self.send(
            _("**{player}** is **{verdict}**.\n{game_link}").format(
                player=to_inspect.user,
                verdict=verdict,
                game_link=self.game.game_link,
            )
        )

    async def check_wolf_seer_target(self) -> None:
        await self.game.ctx.send(
            _("**The {role} awakes...**").format(role=self.role_name)
        )
        possible_targets = [
            p
            for p in self.game.alive_players
            if p != self and p.side not in (Side.WOLVES, Side.WHITE_WOLF)
        ]
        if not possible_targets:
            await self.send(
                _("There is no non-wolf target to inspect.\n{game_link}").format(
                    game_link=self.game.game_link
                )
            )
            return
        try:
            to_inspect = await self.choose_users(
                _("🐺👁️ Choose someone whose role you would like to inspect."),
                list_of_users=possible_targets,
                amount=1,
                required=False,
            )
            if to_inspect:
                to_inspect = to_inspect[0]
            else:
                await self.send(
                    _(
                        "You didn't want to inspect anyone.\n{game_link}"
                    ).format(game_link=self.game.game_link)
                )
                return
        except asyncio.TimeoutError:
            await self.send(
                _(
                    "You've ran out of time and missed to inspect someone's role,"
                    " slowpoke.\n{game_link}"
                ).format(game_link=self.game.game_link)
            )
            return
        self.revealed_roles.update({to_inspect: to_inspect.role})
        await self.send(
            _("**{player}** is a **{role}**.\n{game_link}").format(
                player=to_inspect.user,
                role=to_inspect.role_name,
                game_link=self.game.game_link,
            )
        )

    async def set_bodyguard_target(self) -> None:
        await self.game.ctx.send(
            _("**The {role} awakes...**").format(role=self.role_name)
        )
        available = [player for player in self.game.alive_players if player != self]
        try:
            target = await self.choose_users(
                _("Choose someone to guard tonight."),
                list_of_users=available,
                amount=1,
                required=False,
            )
            if target:
                target = target[0]
            else:
                await self.send(
                    _(
                        "You didn't choose anyone to guard.\n{game_link}"
                    ).format(game_link=self.game.game_link)
                )
                return
        except asyncio.TimeoutError:
            await self.send(
                _(
                    "You didn't choose anyone, slowpoke.\n{game_link}"
                ).format(game_link=self.game.game_link)
            )
            return

        target.is_protected = True
        target.protected_by_bodyguard = self
        await self.send(
            _(
                "**{protected}** is under your protection tonight.\n{game_link}"
            ).format(protected=target.user, game_link=self.game.game_link)
        )

    async def set_jailer_target(self) -> None:
        await self.game.ctx.send(
            _("**The {role} awakes...**").format(role=self.role_name)
        )
        available = [player for player in self.game.alive_players if player != self]
        try:
            target = await self.choose_users(
                _("Choose someone to jail tonight."),
                list_of_users=available,
                amount=1,
                required=False,
            )
            if target:
                target = target[0]
            else:
                await self.send(
                    _(
                        "You didn't choose anyone to jail.\n{game_link}"
                    ).format(game_link=self.game.game_link)
                )
                return
        except asyncio.TimeoutError:
            await self.send(
                _(
                    "You didn't choose anyone, slowpoke.\n{game_link}"
                ).format(game_link=self.game.game_link)
            )
            return

        target.is_protected = True
        target.protected_by_jailer = True
        await self.send(
            _("You jailed **{jailed}** for tonight.\n{game_link}").format(
                jailed=target.user, game_link=self.game.game_link
            )
        )
        await target.send(
            _(
                "🔒 You were jailed tonight and are protected from werewolf attacks."
                "\n{game_link}"
            ).format(game_link=self.game.game_link)
        )

    async def choose_thief_role(self) -> None:
        current_identity_role = self.role
        identity_role_name = self.role_name
        await self.game.ctx.send(
            _("**The {role} awakes...**").format(role=self.role_name)
        )
        entries = [self.game.get_role_name(role) for role in self.game.extra_roles]
        await self.send(
            _(
                "You will be asked to choose a new role from these:\n**{choices}**"
            ).format(choices=", ".join(entries))
        )
        if entries[0] == entries[1] == "Werewolf":
            await self.send(
                _(
                    "But it seems you don't have a choice. Whether you choose or not,"
                    " you will become a Werewolf."
                )
            )
        else:
            entries.append(
                _("Choose nothing and stay as {role}.").format(role=identity_role_name)
            )
        try:
            choice = await self.game.ctx.bot.paginator.Choose(
                entries=entries,
                return_index=True,
                title=_("Choose a new role"),
                timeout=self.game.timer,
            ).paginate(self.game.ctx, location=self.user)
            if choice < 2:
                self.role = self.game.extra_roles[choice]
            else:
                await self.send(
                    _("You chose to stay as {role}.\n{game_link}").format(
                        role=identity_role_name,
                        game_link=self.game.game_link
                    )
                )
        except self.game.ctx.bot.paginator.NoChoice:
            await self.send(
                _(
                    "You didn't choose anything. You will stay as {role}.\n{game_link}"
                ).format(role=identity_role_name, game_link=self.game.game_link)
            )
        except (discord.Forbidden, discord.HTTPException):
            if not (entries[0] == entries[1] == "Werewolf"):
                await self.game.ctx.send(
                    _(
                        "I couldn't send a DM to this player. They will stay as"
                        " {role}."
                    ).format(role=identity_role_name)
                )
                return
        if entries[0] == entries[1] == "Werewolf":
            self.role = Role.WEREWOLF
        if self.role != current_identity_role:
            if self.initial_roles[-1] != current_identity_role:
                self.initial_roles.append(current_identity_role)
            if self.role == Role.THE_OLD:
                self.lives = 2
            await self.send(
                _("Your new role is now **{new_role}**.\n{game_link}").format(
                    new_role=self.role_name, game_link=self.game.game_link
                )
            )
            await self.send_information()

    async def choose_wolfhound_role(self, roles: list[Role]) -> None:
        await self.game.ctx.send(
            _("**The {role} awakes...**").format(role=self.role_name)
        )
        entries = [self.game.get_role_name(role) for role in roles]
        await self.send(
            _(
                "You will be asked to choose a new role from these:\n**{choices}**"
            ).format(choices=", ".join(entries))
        )
        try:
            can_dm = True
            choice = await self.game.ctx.bot.paginator.Choose(
                entries=entries,
                return_index=True,
                title=_("Choose a new role"),
                timeout=self.game.timer,
            ).paginate(self.game.ctx, location=self.user)
            role = roles[choice]
        except self.game.ctx.bot.paginator.NoChoice:
            role = random.choice(roles)
            await self.send(
                _(
                    "You didn't choose anything. A random role was chosen for"
                    " you.\n{game_link}"
                ).format(game_link=self.game.game_link)
            )
        except (discord.Forbidden, discord.HTTPException):
            can_dm = False
            role = random.choice(roles)
            await self.game.ctx.send(
                _("I couldn't send a DM. A random role was chosen for them.")
            )
        if self.initial_roles[-1] != self.role:
            self.initial_roles.append(self.role)
        self.role = role
        if can_dm:
            await self.send(
                _("Your new role is now **{new_role}**.\n{game_link}").format(
                    new_role=self.role_name, game_link=self.game.game_link
                )
            )
            await self.send_information()
            if self.role == Role.LOUDMOUTH:
                await self.game.start_loudmouth_target_selection()
            elif self.role == Role.AVENGER:
                await self.game.start_avenger_target_selection()

    async def check_3_werewolves(self) -> None:
        await self.game.ctx.send(
            _("**The {role} awakes...**").format(role=self.role_name)
        )
        if not self.has_fox_ability:
            # Delay is given here so that the Fox will not be accused of losing the ability already
            await asyncio.sleep(random.randint(5, int(self.game.timer / 2)))
            return
        possible_targets = [p for p in self.game.alive_players if p != self]
        if len(possible_targets) > 3:
            try:
                target = await self.choose_users(
                    _(
                        "🦊 Choose the center player of the group of 3 neighboring"
                        " players who you want to see if any of them is a"
                        " werewolf.\n__Note: The First and Last players in the list are"
                        " neighbors.__"
                    ),
                    list_of_users=[u for u in self.game.alive_players if u != self],
                    amount=1,
                    required=False,
                )
                if not target:
                    await self.send(
                        _("You didn't want to use your ability.\n{game_link}").format(
                            game_link=self.game.game_link
                        )
                    )
                    return
                else:
                    target = target[0]
            except asyncio.TimeoutError:
                await self.send(
                    _("You didn't choose a player, slowpoke.\n{game_link}").format(
                        game_link=self.game.game_link
                    )
                )
                return
            idx = possible_targets.index(target)
            size = len(possible_targets)
            group = [
                possible_targets[(idx - 1) % size],
                target,
                possible_targets[(idx + 1) % size],
            ]
        else:
            group = possible_targets
            await self.send(
                _(
                    "The last {count} possible targets have been"
                    " automatically selected for you."
                ).format(count=len(possible_targets))
            )
        names = ", ".join([str(p.user) for p in group])
        if not any([target.side in (Side.WOLVES, Side.WHITE_WOLF) for target in group]):
            self.has_fox_ability = False
            await self.send(
                _(
                    "You chose the group of **{names}**. You found no Werewolf so you"
                    " lost your ability.\n{game_link}"
                ).format(
                    names=names,
                    game_link=self.game.game_link,
                )
            )
        else:
            await self.send(
                _(
                    "You chose the group of **{names}**. One of them is a"
                    " **Werewolf**.\n{game_link}"
                ).format(
                    names=names,
                    game_link=self.game.game_link,
                )
            )
        await asyncio.sleep(3)  # Give time to read

    async def choose_lovers(self) -> None:
        await self.game.ctx.send(
            _("**{role} awakes and shoots their arrows...**").format(
                role=self.role_name
            )
        )
        if len(self.game.alive_players) < 2:
            await self.send(
                _("Not enough players to choose lovers.\n{game_link}").format(
                    game_link=self.game.game_link
                )
            )
            return
        try:
            lovers = await self.choose_users(
                _(
                    "💘 Choose 2 lovers 💕. You should not tell the town who the lovers"
                    " are."
                ),
                list_of_users=self.game.alive_players,
                amount=2,
            )
        except asyncio.TimeoutError:
            await self.send(
                _("You've ran out of time, slowpoke. Lovers will be chosen randomly.")
            )
            lovers = random.sample(self.game.alive_players, 2)
        # Check if lovers list is valid before proceeding
        if not lovers or len(lovers) < 2:
            await self.send(_("Error selecting lovers. Using random selection."))
            lovers = random.sample(self.game.alive_players, 2)
            
        # Ensure each lover has a valid user attribute
        try:
            await self.send(
                _("You've made **{lover1}** and **{lover2}** lovers\n{game_link}").format(
                    lover1=lovers[0].user if hasattr(lovers[0], 'user') else "Unknown Player",
                    lover2=lovers[1].user if hasattr(lovers[1], 'user') else "Unknown Player",
                    game_link=self.game.game_link,
                )
            )
        except (IndexError, AttributeError) as e:
            await send_traceback(self.game.ctx, e)
            # Safely continue the game
        try:
            # Safely add lovers to the game if they are not already lovers
            if len(lovers) >= 2 and hasattr(lovers[0], 'own_lovers') and hasattr(lovers[1], 'own_lovers'):
                if lovers[0] not in lovers[1].own_lovers:
                    self.game.lovers.append(
                        set(lovers)
                    )  # Add if they're not yet already lovers.
                
                # Send love messages to both lovers
                await lovers[0].send_love_msg(lovers[1])
                await lovers[1].send_love_msg(lovers[0])
            else:
                await self.send(_("Failed to set up lovers properly. The game will continue."))
        except (IndexError, AttributeError) as e:
            await send_traceback(self.game.ctx, e)

    async def choose_to_raid(self) -> None:
        self.game.recent_deaths = list(
            set(self.game.recent_deaths) - set(self.game.alive_players)
        )
        if self.has_raided or len(self.game.recent_deaths) == 0:
            return
        await self.game.ctx.send(
            _("**The {role} awakes...**").format(role=self.role_name)
        )
        possible_targets = [p for p in self.game.recent_deaths]
        try:
            to_raid = await self.choose_users(
                _("Choose a dead player to raid and take their role."),
                list_of_users=possible_targets,
                amount=1,
                required=False,
            )
            if not to_raid:
                await self.send(
                    _("You didn't want to use your ability.\n{game_link}").format(
                        game_link=self.game.game_link
                    )
                )
                return
        except asyncio.TimeoutError:
            await self.send(
                _("You've ran out of time, slowpoke.\n{game_link}").format(
                    game_link=self.game.game_link
                )
            )
            return
        to_raid = to_raid[0]
        if self.initial_roles[-1] != self.role:
            self.initial_roles.append(self.role)
        self.role = to_raid.role
        self.has_raided = True
        await self.send(
            _(
                "You've raided **{to_raid}** to take their loots and their role. You're"
                " now a **{new_role}**.\n{game_link}"
            ).format(
                to_raid=to_raid.user,
                new_role=to_raid.role_name,
                game_link=self.game.game_link,
            )
        )
        await self.send_information()
        if self.role == Role.THIEF:
            await self.choose_thief_role()
        elif self.role == Role.LOUDMOUTH:
            await self.game.start_loudmouth_target_selection()
        elif self.role == Role.AVENGER:
            await self.game.start_avenger_target_selection()
        if self.role == Role.WOLFHOUND:
            await self.choose_wolfhound_role([Role.VILLAGER, Role.WEREWOLF])
        elif self.role == Role.AMOR:
            await self.choose_lovers()
        elif self.role == Role.PURE_SOUL:
            await self.game.announce_pure_soul(self)
        elif self.role == Role.TROUBLEMAKER:
            await self.choose_2_to_exchange()
        elif self.role == Role.JUDGE:
            await self.get_judge_symbol()
        elif self.role == Role.SISTER:
            sisters = self.game.get_players_with_role(Role.SISTER)
            for player in sisters:
                if player == self:
                    continue
                await player.send_family_member_msg("sister", self)
        elif self.role == Role.BROTHER:
            brothers = self.game.get_players_with_role(Role.BROTHER)
            for player in brothers:
                if player == self:
                    continue
                await player.send_family_member_msg("brother", self)
        elif self.role == Role.THE_OLD:
            self.lives = 2

    async def resurrect(self) -> None:
        if not self.has_ritualist_ability or len(self.game.recent_deaths) == 0:
            return
        dead_non_wolves = [
            p
            for p in self.game.recent_deaths
            if p.dead and p.side != Side.WOLVES and p.side != Side.WHITE_WOLF
        ]
        if len(dead_non_wolves) == 0:
            return
        await self.game.ctx.send(
            _("**The {role} awakes...**").format(role=self.role_name)
        )
        try:
            to_resurrect = await self.choose_users(
                _("Choose a villager to resurrect."),
                list_of_users=dead_non_wolves,
                amount=1,
                required=False,
            )
            if not to_resurrect:
                await self.send(
                    _("You didn't want to use your ability.\n{game_link}").format(
                        game_link=self.game.game_link
                    )
                )
                return
            else:
                to_resurrect = to_resurrect[0]
        except asyncio.TimeoutError:
            await self.send(
                _("You've ran out of time, slowpoke.\n{game_link}").format(
                    game_link=self.game.game_link
                )
            )
            return
        queued = await self.game.queue_night_resurrection(self, to_resurrect)
        if not queued:
            await self.send(
                _(
                    "That player is already set to be resurrected at dawn."
                    "\n{game_link}"
                ).format(game_link=self.game.game_link)
            )
            return
        self.has_ritualist_ability = False
        await self.send(
            _(
                "You're trying to resurrect **{to_resurrect}** by performing series of"
                " rituals and prayers of ancient languages. If successful, they will"
                " return at dawn.\n{game_link}"
            ).format(to_resurrect=to_resurrect.user, game_link=self.game.game_link)
        )

    async def medium_resurrect(self) -> None:
        if self.dead or self.role != Role.MEDIUM or not self.has_medium_revive_ability:
            return

        dead_villagers = [
            player for player in self.game.dead_players if player.side == Side.VILLAGERS
        ]
        if not dead_villagers:
            return

        await self.game.ctx.send(
            _("**The {role} communes with the dead...**").format(role=self.role_name)
        )
        try:
            to_resurrect = await self.choose_users(
                _("Choose one dead Villager-team player to resurrect (one-time)."),
                list_of_users=dead_villagers,
                amount=1,
                required=False,
            )
            if not to_resurrect:
                await self.send(
                    _(
                        "You chose not to resurrect anyone tonight.\n{game_link}"
                    ).format(game_link=self.game.game_link)
                )
                return
            to_resurrect = to_resurrect[0]
        except asyncio.TimeoutError:
            await self.send(
                _("You've ran out of time, slowpoke.\n{game_link}").format(
                    game_link=self.game.game_link
                )
            )
            return

        queued = await self.game.queue_night_resurrection(self, to_resurrect)
        if not queued:
            await self.send(
                _(
                    "That player is already set to be resurrected at dawn."
                    "\n{game_link}"
                ).format(game_link=self.game.game_link)
            )
            return
        self.has_medium_revive_ability = False
        await self.send(
            _(
                "You chose to revive **{player}**. They will return at dawn if"
                " successful. You cannot use your resurrection again this game."
                "\n{game_link}"
            ).format(player=to_resurrect.user, game_link=self.game.game_link)
        )

    async def resurrect_werewolf(self) -> None:
        if not self.has_wolf_necro_ability or len(self.game.recent_deaths) == 0:
            return
        dead_wolves = [
            p
            for p in self.game.recent_deaths
            if p.dead and (p.side == Side.WOLVES or p.side == Side.WHITE_WOLF)
        ]
        if len(dead_wolves) == 0:
            return
        await self.game.ctx.send(
            _("**The {role} awakes...**").format(role=self.role_name)
        )
        try:
            to_resurrect = await self.choose_users(
                _("Choose a werewolf to resurrect."),
                list_of_users=dead_wolves,
                amount=1,
                required=False,
            )
            if not to_resurrect:
                await self.send(
                    _("You didn't want to use your ability.\n{game_link}").format(
                        game_link=self.game.game_link
                    )
                )
                return
            else:
                to_resurrect = to_resurrect[0]
        except asyncio.TimeoutError:
            await self.send(
                _("You've ran out of time, slowpoke.\n{game_link}").format(
                    game_link=self.game.game_link
                )
            )
            return
        queued = await self.game.queue_night_resurrection(self, to_resurrect)
        if not queued:
            await self.send(
                _(
                    "That player is already set to be resurrected at dawn."
                    "\n{game_link}"
                ).format(game_link=self.game.game_link)
            )
            return
        self.has_wolf_necro_ability = False
        await self.send(
            _(
                "You used necromancy to bring **{to_resurrect}** back to"
                " life. If successful, they will return at dawn.\n{game_link}"
            ).format(to_resurrect=to_resurrect.user, game_link=self.game.game_link)
        )

    async def choose_2_to_exchange(self) -> None:
        await self.game.ctx.send(
            _("**The {role} awakes...**").format(role=self.role_name)
        )
        possible_targets = [p for p in self.game.alive_players if p != self]
        try:
            exchanged = await self.choose_users(
                _("Choose 2 players that will exchange their roles with each other."),
                list_of_users=possible_targets,
                amount=2,
                required=False,
            )
            if not exchanged:
                await self.send(
                    _("You didn't want to use your ability.\n{game_link}").format(
                        game_link=self.game.game_link
                    )
                )
                return
        except asyncio.TimeoutError:
            await self.send(
                _("You've ran out of time, slowpoke.\n{game_link}").format(
                    game_link=self.game.game_link
                )
            )
            return
        ex_pure_soul = discord.utils.get(exchanged, role=Role.PURE_SOUL)
        try:
            # Ensure we have valid players to exchange
            if len(exchanged) < 2 or not hasattr(exchanged[0], 'role') or not hasattr(exchanged[1], 'role'):
                await self.send(_("Failed to exchange roles. The game will continue."))
                return
                
            role = exchanged[0].role
            # Safely handle initial_roles access
            if hasattr(exchanged[0], 'initial_roles') and len(exchanged[0].initial_roles) > 0:
                if exchanged[0].initial_roles[-1] != exchanged[0].role:
                    exchanged[0].initial_roles.append(exchanged[0].role)
            else:
                # Initialize if missing
                exchanged[0].initial_roles = [exchanged[0].role]
                
            exchanged[0].role = exchanged[1].role
            
            # Safely handle initial_roles access for second player
            if hasattr(exchanged[1], 'initial_roles') and len(exchanged[1].initial_roles) > 0:
                if exchanged[1].initial_roles[-1] != exchanged[1].role:
                    exchanged[1].initial_roles.append(exchanged[1].role)
            else:
                # Initialize if missing
                exchanged[1].initial_roles = [exchanged[1].role]
                
            exchanged[1].role = role
            exchanged[0].lives, exchanged[1].lives = exchanged[1].lives, exchanged[0].lives
        except (IndexError, AttributeError) as e:
            await send_traceback(self.game.ctx, e)
            return
        await self.send(
            _(
                "You've exchanged **{exchange1}'s** and **{exchange2}'s** roles with"
                " each other.\n{game_link}"
            ).format(
                exchange1=exchanged[0].user,
                exchange2=exchanged[1].user,
                game_link=self.game.game_link,
            )
        )
        await exchanged[0].send(
            _(
                "The **{troublemaker}** exchanged your role with someone. You are now a"
                " **{new_role}**.\n{game_link}"
            ).format(
                troublemaker=self.role_name,
                new_role=exchanged[0].role_name,
                game_link=self.game.game_link,
            )
        )
        await exchanged[0].send_information()
        await exchanged[1].send(
            _(
                "The **{troublemaker}** exchanged your role with someone. You are now a"
                " **{new_role}**.\n{game_link}"
            ).format(
                troublemaker=self.role_name,
                new_role=exchanged[1].role_name,
                game_link=self.game.game_link,
            )
        )
        await exchanged[1].send_information()
        if ex_pure_soul:
            new_pure_soul = exchanged[exchanged.index(ex_pure_soul) - 1]
            await self.game.announce_pure_soul(new_pure_soul, ex_pure_soul)
        await self.game.start_loudmouth_target_selection()
        await self.game.start_avenger_target_selection()

    async def protect_werewolf(self) -> None:
        if not self.has_wolf_shaman_ability:
            return
        await self.game.ctx.send(
            _("**The {role} awakes...**").format(role=self.role_name)
        )
        wolves = [
            p
            for p in self.game.alive_players
            if p.side == Side.WOLVES or p.side == Side.WHITE_WOLF
        ]
        try:
            protected = await self.choose_users(
                _(
                    "Choose a Werewolf to send a spiritual protection to block death"
                    " for one time."
                ),
                list_of_users=wolves,
                amount=1,
                required=False,
            )
            if protected:
                protected = protected[0]
            else:
                await self.send(
                    _("You didn't want to use your ability.\n{game_link}").format(
                        game_link=self.game.game_link
                    )
                )
                return
        except asyncio.TimeoutError:
            await self.send(
                _("You didn't choose anyone, slowpoke.\n{game_link}").format(
                    game_link=self.game.game_link
                )
            )
            return
        protected.lives = 2
        self.has_wolf_shaman_ability = False
        await self.send(
            _(
                "**{protected}** is now protected to block one death.\n{game_link}"
            ).format(protected=protected.user, game_link=self.game.game_link)
        )
        await protected.send(
            _(
                "The **{role}** sent you a spiritual protection to block one"
                " death.\n{game_link}"
            ).format(role=self.role_name, game_link=self.game.game_link)
        )

    async def curse_target(self, target: Player) -> None:
        if self.is_jailed:
            return target
        if not self.has_cursed_wolf_father_ability or discord.utils.get(
                self.game.players, cursed=True
        ):
            return target
        # This one's commented out as we want Cursed Wolf Father infects someone secretly
        # await self.game.ctx.send(_("**The {role} awakes...**").format(role=self.role_name))
        try:
            action = await self.game.ctx.bot.paginator.Choose(
                entries=["Yes", "No"],
                return_index=True,
                title=_(
                    "Would you like to infect **{target}** with your curse to join your"
                    " nightly killings?"
                ).format(target=target.user),
                timeout=self.game.timer,
            ).paginate(self.game.ctx, location=self.user)
        except self.game.ctx.bot.paginator.NoChoice:
            await self.send(_("You didn't choose anything."))
            return target
        except (discord.Forbidden, discord.HTTPException):
            await self.game.ctx.send(
                _(
                    "I couldn't send a DM to someone. Too bad they missed to use their"
                    " power."
                )
            )
            return target
        if action == 1:
            return target
        target.cursed = True
        self.has_cursed_wolf_father_ability = False
        await self.send(
            _(
                "You have successfully **Cursed {target}**. They will now join each"
                " night in the Werewolves' feast.\n"
            ).format(target=target.user)
        )
        await target.send(
            _(
                "You have been cursed by the **{role}**. You will now join in the"
                " Werewolves' nightly killings and feast.\n{game_link}"
            ).format(role=self.role_name, game_link=self.game.game_link)
        )
        if target.role in (Role.FLUTIST, Role.SUPERSPREADER):
            if target.initial_roles[-1] != target.role:
                target.initial_roles.append(target.role)
            target.role = Role.WEREWOLF
            await target.send(
                _("You became a **{role}** and lost your nocturnal powers.").format(
                    role=target.role_name
                )
            )
            await target.send_information()
        else:
            await target.send(
                _("You still have your powers as **{role}**.").format(
                    role=target.role_name
                )
            )
        return

    async def infect_virus(self) -> None:
        await self.game.ctx.send(
            _("**The {role} awakes...**").format(role=self.role_name)
        )
        possible_targets = [
            p
            for p in self.game.alive_players
            if not p.infected_with_virus and p != self
        ]
        if not possible_targets:
            await self.send(
                _(
                    "There's no other possible players left to infect.\n{game_link}"
                ).format(game_link=self.game.game_link)
            )
            return
        if len(possible_targets) > self.game.night_no:
            try:
                to_infect = await self.choose_users(
                    _("Choose {num} player(s) to infect with your virus.").format(
                        num=self.game.night_no
                    ),
                    list_of_users=possible_targets,
                    amount=self.game.night_no,
                    required=False,
                )
                if not to_infect:
                    await self.send(
                        _("You didn't want to use your ability.\n{game_link}").format(
                            game_link=self.game.game_link
                        )
                    )
            except asyncio.TimeoutError:
                to_infect = []
                await self.send(
                    _(
                        "You didn't choose enough players to infect,"
                        " slowpoke.\n{game_link}"
                    ).format(game_link=self.game.game_link)
                )
                return
        else:
            await self.send(
                _(
                    "The last {count} possible targets have been"
                    " automatically infected for you."
                ).format(count=len(possible_targets))
            )
            to_infect = possible_targets
        for p in to_infect:
            p.infected_with_virus = True
            await self.send(
                _("You have infected **{infected}**.").format(infected=p.user)
            )
            await p.send(
                _("You have been infected by the {role}.\n{game_link}").format(
                    role=self.role_name, game_link=self.game.game_link
                )
            )
        await self.send(self.game.game_link)

    @property
    def role_name(self) -> str:
        return self.game.get_role_name(self.role)

    @property
    def own_lovers(self) -> list[Player]:
        own_lovers = []
        for couple in self.game.lovers:
            couple = list(couple)
            if self in couple:
                own_lovers.append(couple[couple.index(self) - 1])
        return own_lovers

    @property
    def in_love(self) -> bool:
        for couple in self.game.lovers:
            if self in couple:
                return True
        return False

    @property
    def dead(self) -> bool:
        return self.lives < 1

    async def kill(self) -> None:
        if self.dead:
            return
        self.lives -= 1
        if self.dead:
            if self.role != self.initial_roles[0] or len(self.initial_roles) > 1:
                if self.exchanged_with_maid:
                    initial_role_info = _(" Initial roles hidden.")
                else:
                    initial_role_info = _(" A **{initial_roles}** initially.").format(
                        initial_roles=", ".join(
                            [
                                self.game.get_role_name(initial_role)
                                for initial_role in self.initial_roles
                            ]
                        )
                    )
            else:
                initial_role_info = ""
            if self.is_sheriff:
                await self.choose_new_sheriff()
            self.game.recent_deaths.append(self)
            await self.game.sync_player_ww_role(self)
            medium = self.game.get_player_with_role(Role.MEDIUM)
            if self.role == Role.MEDIUM:
                for dead_player in [player for player in self.game.dead_players if player != self]:
                    await dead_player.send(
                        _(
                            "🔮 The **Medium** has died. The dead whisper line is now"
                            " closed.\n{game_link}"
                        ).format(game_link=self.game.game_link)
                    )
            elif medium and not medium.dead:
                await self.send(
                    _(
                        "🔮 A **Medium** is alive. Send any DM message here and it will"
                        " be relayed to the Medium while they are alive."
                        "\n{game_link}"
                    ).format(game_link=self.game.game_link)
                )
                await medium.send(
                    _(
                        "🔮 **{player}** joined the dead whisper line. Send any DM"
                        " message here to talk.\n{game_link}"
                    ).format(player=self.user, game_link=self.game.game_link)
                )
            await self.game._ensure_medium_relay()
            # Reveal role in death list
            for p in self.game.players:
                p.revealed_roles.update({self: self.role})
            await self.game.ctx.send(
                _("{user} has died. They were a **{role}**!{initial_role_info}").format(
                    user=self.user.mention,
                    role=self.game.get_role_name(self),
                    initial_role_info=initial_role_info,
                )
            )
            if self.role == Role.LOUDMOUTH:
                await self.game.stop_loudmouth_target_selection()
                if self.loudmouth_target and self.loudmouth_target != self:
                    for player in self.game.players:
                        player.revealed_roles.update(
                            {self.loudmouth_target: self.loudmouth_target.role}
                        )
                    await self.game.ctx.send(
                        _(
                            "📣 The **Loudmouth** died and revealed **{target}** as a"
                            " **{role}**."
                        ).format(
                            target=self.loudmouth_target.user.mention,
                            role=self.game.get_role_name(self.loudmouth_target),
                        )
                    )
                else:
                    await self.game.ctx.send(
                        _("📣 The **Loudmouth** died without marking anyone.")
                    )
            if self.role == Role.AVENGER:
                await self.game.stop_avenger_target_selection()
            if (
                self.role == Role.JESTER
                and self.killed_by_lynch
                and self.game.forced_winner is None
            ):
                self.game.winning_side = "Jester"
                self.game.forced_winner = self
                await self.game.ctx.send(
                    _(
                        "🎭 The **Jester** was lynched and achieved their goal. The game"
                        " ends immediately!"
                    )
                )
            await self.game.handle_head_hunter_target_death(self)
            if self.infected_with_virus:
                self.infected_with_virus = False
                await self.game.ctx.send(
                    _("**{user}** lost the disease from viral infection.").format(
                        user=self.user,
                    )
                )
            additional_deaths = []
            if self.role == Role.HUNTER:
                try:
                    await self.game.ctx.send(_("The Hunter grabs their gun."))
                    target = await self.choose_users(
                        _("Choose someone who shall die with you. 🔫"),
                        list_of_users=[
                            p
                            for p in self.game.alive_players
                            if p not in self.own_lovers
                        ],
                        amount=1,
                        required=False,
                    )
                except asyncio.TimeoutError:
                    await self.game.ctx.send(
                        _("The Hunter couldn't find the trigger 😆.")
                    )
                else:
                    if not target:
                        await self.game.ctx.send(
                            _("The Hunter refused to shoot anyone.")
                        )
                    else:
                        target = target[0]
                        await self.send(
                            _("You chose to shoot **{target}**").format(
                                target=target.user
                            )
                        )
                        await self.game.ctx.send(
                            _("The Hunter is firing. **{target}** got hit!").format(
                                target=target.user
                            )
                        )
                        if target.role == Role.THE_OLD:
                            target.died_from_villagers = True
                            target.lives = 1
                        additional_deaths.append(target)
            elif self.role == Role.AVENGER:
                if self.game.after_first_night:
                    target = self.avenger_target
                    if target and not target.dead and target != self:
                        await self.game.ctx.send(
                            _(
                                "🗡️ The **Avenger** died and dragged **{target}** down."
                            ).format(target=target.user.mention)
                        )
                        if target.role == Role.THE_OLD:
                            target.died_from_villagers = True
                            target.lives = 1
                        additional_deaths.append(target)
                    else:
                        await self.game.ctx.send(
                            _(
                                "🗡️ The **Avenger** died but had no valid marked target."
                            )
                        )
            elif self.role == Role.KNIGHT:
                if self.attacked_by_the_pact:
                    self.game.rusty_sword_disease_night = 0
                    await self.game.ctx.send(
                        _(
                            "The **{role}** wounded one of the werewolves with their"
                            " Rusty Sword before dying."
                        ).format(role=self.role_name)
                    )
            elif self.role == Role.JUNIOR_WEREWOLF:
                possible_targets = [
                    player
                    for player in self.game.alive_players
                    if player.side == Side.VILLAGERS and player not in self.own_lovers
                ]
                if possible_targets:
                    target = (
                        self.junior_mark_target
                        if self.junior_mark_target in possible_targets
                        else random.choice(possible_targets)
                    )
                    await self.game.ctx.send(
                        _(
                            "The **Junior Werewolf** died and dragged"
                            " **{target}** down in revenge."
                        ).format(target=target.user.mention)
                    )
                    if target.role == Role.THE_OLD:
                        target.died_from_villagers = True
                        target.lives = 1
                    additional_deaths.append(target)
            elif self.role == Role.WAR_VETERAN:
                if self.died_from_villagers:
                    target = random.choice(
                        [p for p in self.game.alive_players if p not in self.own_lovers]
                    )
                    await self.game.ctx.send(
                        _(
                            "The **{role}** was lynched by the Village, a random"
                            " villager **{target}** was shot."
                        ).format(role=self.role_name, target=target.user)
                    )
                    if target.role == Role.THE_OLD:
                        target.died_from_villagers = True
                        target.lives = 1
                    additional_deaths.append(target)
            elif self.role == Role.THE_OLD and self.died_from_villagers:
                if cursed_one := discord.utils.get(
                        self.game.alive_players, cursed=True
                ):
                    cursed_one.cursed = False  # set temporarily to False
                for p in self.game.alive_players:
                    if p.side not in [Side.WOLVES, Side.WHITE_WOLF]:
                        if p.initial_roles[-1] != p.role:
                            p.initial_roles.append(p.role)
                        if p.role != Role.VILLAGER:
                            p.role = Role.VILLAGER
                if cursed_one:
                    cursed_one.cursed = True  # set it back
                await self.game.ctx.send(
                    _(
                        "The villagers killed **{role}**. The villagers lost all"
                        " their special powers and became normal villagers."
                    ).format(role=self.role_name)
                )
            await self.send(
                _(
                    "💀 You have been eliminated. Please do not communicate with the"
                    " other players until the end of the game.💀\n{game_link}"
                ).format(game_link=self.game.game_link)
            )
            for for_killing in additional_deaths:
                await for_killing.kill()
            if self.in_love and len(self.own_lovers) > 0:
                lovers_to_kill = self.own_lovers
                for lover in lovers_to_kill:
                    if {self, lover} in self.game.lovers:
                        self.game.lovers.remove({self, lover})
                    if not lover.dead:
                        await self.game.ctx.send(
                            _(
                                "{dead_player}'s lover, {lover}, will die of sorrow."
                            ).format(
                                dead_player=self.user.mention, lover=lover.user.mention
                            )
                        )
                        if lover.role == Role.THE_OLD:
                            lover.lives = 1
                        await asyncio.sleep(3)
                        await lover.kill()

    @property
    def side(self) -> Side:
        if is_wolf_team_role(self.role):
            return Side.WOLVES
        if self.cursed and self.role != Role.WHITE_WOLF:
            return Side.WOLVES
        if self.role == Role.DOCTOR:
            return Side.VILLAGERS
        if self.role == Role.FLOWER_CHILD:
            return Side.VILLAGERS
        if self.role == Role.FORTUNE_TELLER:
            return Side.VILLAGERS
        if self.role == Role.AURA_SEER:
            return Side.VILLAGERS
        if self.role == Role.BODYGUARD:
            return Side.VILLAGERS
        if self.role == Role.SHERIFF:
            return Side.VILLAGERS
        if self.role == Role.JAILER:
            return Side.VILLAGERS
        if self.role == Role.MEDIUM:
            return Side.VILLAGERS
        if self.role == Role.LOUDMOUTH:
            return Side.VILLAGERS
        if self.role == Role.AVENGER:
            return Side.VILLAGERS
        if self.role == Role.HEAD_HUNTER:
            return Side.HEAD_HUNTER
        if 6 <= self.role.value <= 26:
            return Side.VILLAGERS
        else:
            return getattr(Side, self.role.name, "NAN")

    @property
    def has_won(self) -> bool:
        # Returns whether the player has reached their goal or not
        if self.in_love:
            # Special objective for Lovers: The pair must eliminate all other players
            # if one of the lovers is in the Villagers side and the other is in the
            # Wolves or Flutist side.
            # This also checks chain of lovers
            if len(self.game.get_chained_lovers(self)) == len(self.game.alive_players):
                self.game.winning_side = _("Lovers")
                return True
        if self.side == Side.FLUTIST:
            # The win stealer: If the Flutist would win at the same time as another
            # side, the Flutist takes precedence
            if all([p.enchanted or p == self for p in self.game.alive_players]):
                self.game.winning_side = self.role_name
                return True
        if self.side == Side.SUPERSPREADER:
            # Another win stealer but loses to Flutist as it's later called on wake order
            if (
                    all(
                        [
                            p.infected_with_virus or p == self
                            for p in self.game.alive_players
                        ]
                    )
                    and self.game.winning_side != "Flutist"
            ):
                self.game.winning_side = self.role_name
                return True
        elif self.side == Side.VILLAGERS:
            if (
                    not any(
                        [
                            player.side in (Side.WOLVES, Side.WHITE_WOLF)
                            for player in self.game.alive_players
                        ]
                    )
                    and self.game.winning_side != "Flutist"
            ):
                self.game.winning_side = "Villagers"
                return True
        elif self.side == Side.WHITE_WOLF:
            if len(self.game.alive_players) == 1 and not self.dead:
                self.game.winning_side = "White Wolf"
                return True
        elif self.side == Side.WOLVES:
            alive_players = self.game.alive_players
            wolf_count = sum(
                1
                for player in alive_players
                if player.side in (Side.WOLVES, Side.WHITE_WOLF)
            )
            villager_count = sum(
                1
                for player in alive_players
                if player.side in (Side.VILLAGERS, Side.JESTER, Side.HEAD_HUNTER)
            )
            # Overrun victory: wolves control the vote once they meet or exceed villagers.
            if (
                wolf_count >= villager_count
                and self.game.winning_side != "Flutist"
            ):
                self.game.winning_side = "Werewolves"
                return True
        return False

    async def choose_new_sheriff(self, exclude: Player = None) -> None:
        possible_sheriff = [
            p for p in self.game.alive_players if p != self and p != exclude
        ]
        if not len(possible_sheriff):
            return
        if self.dead:
            await self.send(
                _("You are going to die. Use your last breath to choose a new Sheriff.")
            )
        elif exclude is not None:
            await self.send(
                _(
                    "You exchanged roles with **{dying_user}**. You should choose the"
                    " new Sheriff."
                ).format(dying_user=exclude.user)
            )
        self.is_sheriff = False
        await self.game.ctx.send(
            _("The **Sheriff {sheriff}** should choose their successor.").format(
                sheriff=self.user
            )
        )
        msg = None
        randomize = False
        try:
            sheriff = await self.choose_users(
                _("Choose the new 🎖 Sheriff️."),
                list_of_users=possible_sheriff,
                amount=1,
                required=False,
            )
            if sheriff:
                sheriff = sheriff[0]
            else:
                randomize = True
        except asyncio.TimeoutError:
            randomize = True
        if randomize:
            await self.send(
                _(
                    "You didn't choose anyone. A random player will be chosen to be"
                    " your successor."
                )
            )
            sheriff = random.choice(possible_sheriff)
            msg = _(
                "📢 **{ex_sheriff}** didn't choose anyone. {sheriff} got randomly chosen"
                " to be the new 🎖️ **Sheriff**. **The vote of the Sheriff counts as"
                " double.**"
            ).format(ex_sheriff=self.user, sheriff=sheriff.user.mention)
        sheriff.is_sheriff = True
        await self.send(
            _("**{sheriff}** became the new Sheriff.").format(
                sheriff=sheriff.user.mention
            )
        )
        if not msg:
            msg = _(
                "📢 {sheriff} got chosen to be the new 🎖️ **Sheriff**. **The vote of the"
                " Sheriff counts as double.**"
            ).format(sheriff=sheriff.user.mention)
        await self.game.ctx.send(msg)
        await self.game.dm_sheriff_info()


# A list of roles to give depending on the number of total players
# Rule of thumb is to have 50+% of villagers, whereas thief etc count
# as wolves as there is a good chance they might become some
# This is the main subject to change for game balance
ROLES_FOR_PLAYERS: list[Role] = [
    Role.VILLAGER,
    Role.VILLAGER,
    Role.WEREWOLF,
    Role.SEER,
    Role.WITCH,
    Role.AVENGER,
    Role.THIEF,
    Role.WEREWOLF,
    Role.CURSED,
    Role.PURE_SOUL,
    Role.MAID,
    Role.VILLAGER,
    Role.WHITE_WOLF,
    Role.HEALER,
    Role.AMOR,
    Role.KNIGHT,
    Role.SISTER,
    Role.SISTER,
    Role.BIG_BAD_WOLF,
    Role.THE_OLD,
    Role.WEREWOLF,
    Role.WOLFHOUND,
    Role.WEREWOLF,
    Role.FOX,
    Role.BROTHER,
    Role.BROTHER,
    Role.BROTHER,
    Role.JUDGE,
    Role.FLUTIST,
    Role.WEREWOLF,
    Role.VILLAGER,
    Role.CURSED_WOLF_FATHER,
]


def get_roles(number_of_players: int, mode: str = None) -> list[Role]:
    requested_players = number_of_players
    number_of_players += 2  # Thief is in play
    roles_to_give = ROLES_FOR_PLAYERS.copy()
    if mode == "Imbalanced":
        roles_to_give = random.shuffle(roles_to_give)
    if mode == "IdleRPG":
        roles_to_give.extend(
            [
                Role.PARAGON,
                Role.RAIDER,
                Role.RITUALIST,
                Role.TROUBLEMAKER,
                Role.LAWYER,
                Role.WAR_VETERAN,
                Role.WOLF_SHAMAN,
                Role.WOLF_NECROMANCER,
                Role.SUPERSPREADER,
            ]
        )
        roles_to_give = random.shuffle(roles_to_give)
    if number_of_players > len(roles_to_give):
        roles = roles_to_give
        # Fill up with villagers and wolves as all special roles are taken
        for i in range(number_of_players - len(roles)):
            if i % 2 == 0:
                roles.append(Role.WEREWOLF)
            else:
                roles.append(Role.VILLAGER)
    else:
        roles = roles_to_give[:number_of_players]
    roles = random.shuffle(roles)
    roles = [
        random.choice([Role.SEER, Role.AURA_SEER]) if role == Role.SEER else role
        for role in roles
    ]
    roles = [
        random.choice([Role.WITCH, Role.DOCTOR, Role.BODYGUARD])
        if role == Role.WITCH
        else role
        for role in roles
    ]
    roles = [
        random.choice([Role.PURE_SOUL, Role.FLOWER_CHILD, Role.SHERIFF])
        if role == Role.PURE_SOUL
        else role
        for role in roles
    ]
    # Enable Maid-family utility roles from 7+ players even when the base slice
    # would otherwise miss the Maid slot.
    if requested_players >= 7 and Role.MAID not in roles[:-2]:
        roles = force_role(roles, Role.MAID)
    maid_choices = [Role.MAID, Role.FORTUNE_TELLER, Role.MEDIUM]
    if requested_players >= 9:
        maid_choices.append(Role.JAILER)
    roles = [
        random.choice(maid_choices)
        if role == Role.MAID
        else role
        for role in roles
    ]
    available_roles = roles[:-2]
    extra_roles = roles[-2:]
    if requested_players >= 7:
        wolf_slots = [
            idx for idx, role in enumerate(available_roles) if role == Role.WEREWOLF
        ]
        if wolf_slots:
            upgrade_options = [Role.JUNIOR_WEREWOLF]
            if requested_players >= 8:
                upgrade_options.append(Role.WOLF_SEER)
            upgrade_idx = random.choice(wolf_slots)
            available_roles[upgrade_idx] = random.choice(upgrade_options)
            roles = available_roles + extra_roles
    if not any([is_wolf_team_role(role) for role in roles[:-2]]):
        roles = force_role(roles, Role.WEREWOLF)
    if requested_players > 5:
        roles = force_role(roles, random.choice([Role.JESTER, Role.HEAD_HUNTER]))
    available_roles = roles[:-2]
    if roles.count(Role.SISTER) > 0 and available_roles.count(Role.SISTER) < 2:
        for idx, role in enumerate(roles):
            if role == Role.SISTER:
                roles[idx] = Role.VILLAGER
    if roles.count(Role.BROTHER) > 0 and available_roles.count(Role.BROTHER) < 2:
        for idx, role in enumerate(roles):
            if role == Role.BROTHER:
                roles[idx] = Role.VILLAGER
    available_roles = roles[:-2]
    extra_roles = roles[-2:]
    for idx, role in enumerate(available_roles):
        # Loudmouth variant: 90% Loudmouth, 10% Thief on the Thief slot.
        if role == Role.THIEF and random.randint(1, 100) <= 90:
            available_roles[idx] = Role.LOUDMOUTH
    roles = available_roles + extra_roles
    roles = cap_special_werewolves(roles, requested_players=requested_players)
    roles = enforce_wolf_ratio(roles, requested_players=requested_players)
    return roles


def force_role(roles: list[Role], role_to_force: Role) -> Role | None:
    # Make sure a role is to be played, force it otherwise
    # Warning: This can replace previously forced role
    available_roles = roles[:-2]
    extra_roles = roles[-2:]
    if role_to_force in available_roles:
        return roles
    else:
        idx = 0  # Let's replace the first role in available_roles
        if role_to_force in extra_roles:
            # Get it by swapping with extra_roles's
            swap_idx = extra_roles.index(role_to_force)
            available_roles[idx], extra_roles[swap_idx] = (
                extra_roles[swap_idx],
                available_roles[idx],
            )
        else:
            # Or just force it manually
            available_roles[idx] = role_to_force
    return random.shuffle(available_roles) + random.shuffle(extra_roles)


if __name__ == "__main__":
    game = Game(50)
    game.run()

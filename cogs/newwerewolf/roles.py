from __future__ import annotations

import re

from dataclasses import dataclass
from enum import Enum


class Team(str, Enum):
    VILLAGERS = "villagers"
    WOLVES = "wolves"
    LONERS = "loners"


class RoleId(str, Enum):
    WEREWOLF = "werewolf"
    BIG_BAD_WOLF = "big_bad_wolf"
    CURSED_WOLF_FATHER = "cursed_wolf_father"
    WOLF_SHAMAN = "wolf_shaman"
    WOLF_NECROMANCER = "wolf_necromancer"

    VILLAGER = "villager"
    PURE_SOUL = "pure_soul"
    SEER = "seer"
    AMOR = "amor"
    WITCH = "witch"
    HUNTER = "hunter"
    HEALER = "healer"
    THE_OLD = "the_old"
    SISTER = "sister"
    BROTHER = "brother"
    FOX = "fox"
    JUDGE = "judge"
    KNIGHT = "knight"
    MAID = "maid"
    CURSED = "cursed"
    THIEF = "thief"
    PARAGON = "paragon"
    RITUALIST = "ritualist"
    TROUBLEMAKER = "troublemaker"
    LAWYER = "lawyer"
    WAR_VETERAN = "war_veteran"

    WHITE_WOLF = "white_wolf"
    WOLFHOUND = "wolfhound"
    RAIDER = "raider"

    FLUTIST = "flutist"
    SUPERSPREADER = "superspreader"
    JESTER = "jester"
    DOCTOR = "doctor"
    HEAD_HUNTER = "head_hunter"
    FLOWER_CHILD = "flower_child"
    FORTUNE_TELLER = "fortune_teller"
    AURA_SEER = "aura_seer"
    BODYGUARD = "bodyguard"
    JUNIOR_WEREWOLF = "junior_werewolf"
    WOLF_SEER = "wolf_seer"
    SHERIFF = "sheriff"
    JAILER = "jailer"
    MEDIUM = "medium"
    LOUDMOUTH = "loudmouth"
    AVENGER = "avenger"


@dataclass(frozen=True, slots=True)
class RoleDef:
    role: RoleId
    display_name: str
    team: Team
    description: str
    implemented: bool


def _display(name: str) -> str:
    return name.replace("_", " ").title()


def _villager_def(role: RoleId, *, implemented: bool = False, description: str | None = None) -> RoleDef:
    return RoleDef(
        role=role,
        display_name=_display(role.value),
        team=Team.VILLAGERS,
        description=description or "A villager-side role.",
        implemented=implemented,
    )


ROLE_DEFS: dict[RoleId, RoleDef] = {
    RoleId.WEREWOLF: RoleDef(
        role=RoleId.WEREWOLF,
        display_name="Werewolf",
        team=Team.WOLVES,
        description="Works with wolf team to eliminate non-wolves.",
        implemented=True,
    ),
    RoleId.BIG_BAD_WOLF: RoleDef(
        role=RoleId.BIG_BAD_WOLF,
        display_name="Big Bad Wolf",
        team=Team.WOLVES,
        description=(
            "Joins wolf attack and may perform an additional villager kill while no"
            " wolf-aligned player has died."
        ),
        implemented=True,
    ),
    RoleId.CURSED_WOLF_FATHER: RoleDef(
        role=RoleId.CURSED_WOLF_FATHER,
        display_name="Cursed Wolf Father",
        team=Team.WOLVES,
        description=(
            "Once per game can curse the wolves' target instead of killing them,"
            " turning that target into a Werewolf."
        ),
        implemented=True,
    ),
    RoleId.WOLF_SHAMAN: RoleDef(
        role=RoleId.WOLF_SHAMAN,
        display_name="Wolf Shaman",
        team=Team.WOLVES,
        description="Can shield one wolf from one death once per game.",
        implemented=True,
    ),
    RoleId.WOLF_NECROMANCER: RoleDef(
        role=RoleId.WOLF_NECROMANCER,
        display_name="Wolf Necromancer",
        team=Team.WOLVES,
        description="Can resurrect one recently dead wolf once per game.",
        implemented=True,
    ),
    RoleId.VILLAGER: _villager_def(
        RoleId.VILLAGER,
        implemented=True,
        description="A basic villager with no night action.",
    ),
    RoleId.PURE_SOUL: _villager_def(
        RoleId.PURE_SOUL,
        implemented=True,
        description="Revealed publicly as innocent at game start.",
    ),
    RoleId.SEER: _villager_def(
        RoleId.SEER,
        implemented=True,
        description="Inspects one player each night to learn exact role.",
    ),
    RoleId.AMOR: _villager_def(
        RoleId.AMOR,
        implemented=True,
        description=(
            "Chooses two lovers. If one lover dies, their linked lover dies of sorrow."
            " Lovers can win together if they are the only chained survivors."
        ),
    ),
    RoleId.WITCH: _villager_def(
        RoleId.WITCH,
        implemented=True,
        description=(
            "Has one protection potion and one poison potion. Protection is consumed only"
            " when the chosen target is attacked. Poison cannot be used on night one."
        ),
    ),
    RoleId.HUNTER: _villager_def(
        RoleId.HUNTER,
        implemented=True,
        description="May shoot one target when killed.",
    ),
    RoleId.HEALER: _villager_def(
        RoleId.HEALER,
        implemented=True,
        description="Protects one villager-side player each night, but not the same target twice in a row.",
    ),
    RoleId.THE_OLD: _villager_def(
        RoleId.THE_OLD,
        implemented=True,
        description="Survives the first wolf attack; if killed by villagers, villager special roles lose powers.",
    ),
    RoleId.SISTER: _villager_def(
        RoleId.SISTER,
        implemented=True,
        description="Sisters know each other.",
    ),
    RoleId.BROTHER: _villager_def(
        RoleId.BROTHER,
        implemented=True,
        description="Brothers know each other.",
    ),
    RoleId.FOX: _villager_def(
        RoleId.FOX,
        implemented=True,
        description="Inspects groups for wolves and loses ability after a miss.",
    ),
    RoleId.JUDGE: _villager_def(
        RoleId.JUDGE,
        implemented=True,
        description="Can force one extra election during a day.",
    ),
    RoleId.KNIGHT: _villager_def(
        RoleId.KNIGHT,
        implemented=True,
        description="If killed by wolves, infects one wolf with rusty sword disease to die next night.",
    ),
    RoleId.MAID: _villager_def(
        RoleId.MAID,
        implemented=True,
        description="Can take the role of a lynched player once.",
    ),
    RoleId.CURSED: _villager_def(
        RoleId.CURSED,
        implemented=True,
        description="Transforms into Werewolf when attacked by wolves.",
    ),
    RoleId.THIEF: _villager_def(
        RoleId.THIEF,
        implemented=True,
        description="Chooses one of two reserve roles at game start.",
    ),
    RoleId.PARAGON: _villager_def(
        RoleId.PARAGON,
        implemented=True,
        description="May restrict daily lynch voting candidates.",
    ),
    RoleId.RITUALIST: _villager_def(
        RoleId.RITUALIST,
        implemented=True,
        description="Can resurrect one recently dead villager-side player once.",
    ),
    RoleId.TROUBLEMAKER: _villager_def(
        RoleId.TROUBLEMAKER,
        implemented=True,
        description="Can swap two players' roles on the first night.",
    ),
    RoleId.LAWYER: _villager_def(
        RoleId.LAWYER,
        implemented=True,
        description="Can cancel one day's lynch vote with an objection.",
    ),
    RoleId.WAR_VETERAN: _villager_def(
        RoleId.WAR_VETERAN,
        implemented=True,
        description="If lynched, shoots a random living player.",
    ),
    RoleId.WHITE_WOLF: RoleDef(
        role=RoleId.WHITE_WOLF,
        display_name="White Wolf",
        team=Team.WOLVES,
        description=(
            "Joins wolf attacks and, on even nights, may kill a wolf-team player."
            " Wins alone if they are the last survivor."
        ),
        implemented=True,
    ),
    RoleId.WOLFHOUND: _villager_def(
        RoleId.WOLFHOUND,
        implemented=True,
        description="Chooses villager or werewolf side at game start.",
    ),
    RoleId.RAIDER: _villager_def(
        RoleId.RAIDER,
        implemented=True,
        description="Can steal the role of one recently dead player once.",
    ),
    RoleId.FLUTIST: RoleDef(
        role=RoleId.FLUTIST,
        display_name="Flutist",
        team=Team.LONERS,
        description="Wins by enchanting all other living players.",
        implemented=True,
    ),
    RoleId.SUPERSPREADER: RoleDef(
        role=RoleId.SUPERSPREADER,
        display_name="Superspreader",
        team=Team.LONERS,
        description=(
            "Infects players at night (up to current night number). Wins if all other"
            " living players are infected."
        ),
        implemented=True,
    ),
    RoleId.JESTER: RoleDef(
        role=RoleId.JESTER,
        display_name="Jester",
        team=Team.LONERS,
        description="Wins by being lynched during the day.",
        implemented=True,
    ),
    RoleId.DOCTOR: _villager_def(
        RoleId.DOCTOR,
        implemented=True,
        description="Protects one player from night attacks.",
    ),
    RoleId.HEAD_HUNTER: RoleDef(
        role=RoleId.HEAD_HUNTER,
        display_name="Head Hunter",
        team=Team.LONERS,
        description=(
            "Gets a villager target. Wins if that target is lynched. If the target dies"
            " any other way, Head Hunter becomes a Villager."
        ),
        implemented=True,
    ),
    RoleId.FLOWER_CHILD: _villager_def(
        RoleId.FLOWER_CHILD,
        implemented=True,
        description="Can save a lynch target once.",
    ),
    RoleId.FORTUNE_TELLER: _villager_def(
        RoleId.FORTUNE_TELLER,
        implemented=True,
        description="Distributes fortune cards that can be used to reveal a role.",
    ),
    RoleId.AURA_SEER: _villager_def(
        RoleId.AURA_SEER,
        implemented=True,
        description="Inspects one player each night to learn team aura.",
    ),
    RoleId.BODYGUARD: _villager_def(
        RoleId.BODYGUARD,
        implemented=True,
        description="Guards one player and may die intercepting attacks.",
    ),
    RoleId.JUNIOR_WEREWOLF: RoleDef(
        role=RoleId.JUNIOR_WEREWOLF,
        display_name="Junior Werewolf",
        team=Team.WOLVES,
        description="Marks a villager during day; marked target dies when Junior Werewolf dies.",
        implemented=True,
    ),
    RoleId.WOLF_SEER: RoleDef(
        role=RoleId.WOLF_SEER,
        display_name="Wolf Seer",
        team=Team.WOLVES,
        description="Inspects one non-wolf player each night to learn role.",
        implemented=True,
    ),
    RoleId.SHERIFF: _villager_def(
        RoleId.SHERIFF,
        implemented=True,
        description="Investigates one player each night as suspicious or not suspicious.",
    ),
    RoleId.JAILER: _villager_def(
        RoleId.JAILER,
        implemented=True,
        description=(
            "Chooses a daytime jail target for the next night. Jailed players are"
            " ability-blocked and protected from werewolf attacks. Can execute one"
            " jailed player once per game."
        ),
    ),
    RoleId.MEDIUM: _villager_def(
        RoleId.MEDIUM,
        implemented=True,
        description="Can resurrect one dead Villager-team player once per game.",
    ),
    RoleId.LOUDMOUTH: _villager_def(
        RoleId.LOUDMOUTH,
        implemented=True,
        description=(
            "Marks a player. If Loudmouth dies, the marked player's role is publicly"
            " revealed."
        ),
    ),
    RoleId.AVENGER: _villager_def(
        RoleId.AVENGER,
        implemented=True,
        description=(
            "After the first night, marks a player. If Avenger dies, the marked target"
            " dies too."
        ),
    ),
}


def _normalize_role_token(token: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", token.casefold())


ROLE_TOKEN_TO_ROLE: dict[str, RoleId] = {
    _normalize_role_token(role.name): role for role in RoleId
}
ROLE_TOKEN_TO_ROLE.update(
    {
        _normalize_role_token(role.name.replace("_", " ")): role
        for role in RoleId
    }
)
ROLE_TOKEN_TO_ROLE.update(
    {
        "ww": RoleId.WEREWOLF,
        "wolfnecro": RoleId.WOLF_NECROMANCER,
        "juniorwolf": RoleId.JUNIOR_WEREWOLF,
        "old": RoleId.THE_OLD,
    }
)


def parse_requested_roles(raw_roles: str) -> tuple[list[RoleId], list[str]]:
    tokens = [token.strip() for token in raw_roles.replace(";", ",").split(",")]
    tokens = [token for token in tokens if token]
    parsed: list[RoleId] = []
    invalid: list[str] = []
    for token in tokens:
        role = ROLE_TOKEN_TO_ROLE.get(_normalize_role_token(token))
        if role is None:
            invalid.append(token)
            continue
        parsed.append(role)
    return parsed, invalid


def role_display_name(role: RoleId) -> str:
    return ROLE_DEFS[role].display_name


def role_description(role: RoleId) -> str:
    return ROLE_DEFS[role].description


def supported_role_names() -> list[str]:
    return sorted(role_def.display_name for role_def in ROLE_DEFS.values())


def is_wolf_team(role: RoleId) -> bool:
    return ROLE_DEFS[role].team == Team.WOLVES


def is_villager_team(role: RoleId) -> bool:
    return ROLE_DEFS[role].team == Team.VILLAGERS


def is_loner_team(role: RoleId) -> bool:
    return ROLE_DEFS[role].team == Team.LONERS

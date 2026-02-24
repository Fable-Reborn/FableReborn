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
    ALPHA_WEREWOLF = "alpha_werewolf"
    GUARDIAN_WOLF = "guardian_wolf"
    WOLF_SUMMONER = "wolf_summoner"
    WOLF_TRICKSTER = "wolf_trickster"
    NIGHTMARE_WEREWOLF = "nightmare_werewolf"
    VOODOO_WEREWOLF = "voodoo_werewolf"

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
    SERIAL_KILLER = "serial_killer"
    CANNIBAL = "cannibal"
    DOCTOR = "doctor"
    HEAD_HUNTER = "head_hunter"
    FLOWER_CHILD = "flower_child"
    FORTUNE_TELLER = "fortune_teller"
    AURA_SEER = "aura_seer"
    GAMBLER = "gambler"
    BODYGUARD = "bodyguard"
    JUNIOR_WEREWOLF = "junior_werewolf"
    WOLF_SEER = "wolf_seer"
    SORCERER = "sorcerer"
    SHERIFF = "sheriff"
    JAILER = "jailer"
    MEDIUM = "medium"
    LOUDMOUTH = "loudmouth"
    AVENGER = "avenger"
    RED_LADY = "red_lady"
    GHOST_LADY = "ghost_lady"
    PRIEST = "priest"
    MARKSMAN = "marksman"
    FORGER = "forger"
    PACIFIST = "pacifist"
    GRUMPY_GRANDMA = "grumpy_grandma"
    WARDEN = "warden"
    DETECTIVE = "detective"
    MORTICIAN = "mortician"
    SEER_APPRENTICE = "seer_apprentice"
    TOUGH_GUY = "tough_guy"
    GRAVE_ROBBER = "grave_robber"
    WOLF_PACIFIST = "wolf_pacifist"


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
        description=(
            "Can shield one wolf from one death once per game and make that wolf"
            " appear as Villager to checks for that night."
        ),
        implemented=True,
    ),
    RoleId.WOLF_NECROMANCER: RoleDef(
        role=RoleId.WOLF_NECROMANCER,
        display_name="Wolf Necromancer",
        team=Team.WOLVES,
        description="Can resurrect one recently dead wolf once per game.",
        implemented=True,
    ),
    RoleId.ALPHA_WEREWOLF: RoleDef(
        role=RoleId.ALPHA_WEREWOLF,
        display_name="Alpha Werewolf",
        team=Team.WOLVES,
        description=(
            "Votes and chats with the wolves at night. Its wolf-kill vote counts as"
            " two votes. During the day, can send unlimited private messages that are"
            " relayed only to the werewolf team."
        ),
        implemented=True,
    ),
    RoleId.WOLF_SUMMONER: RoleDef(
        role=RoleId.WOLF_SUMMONER,
        display_name="Wolf Summoner",
        team=Team.WOLVES,
        description=(
            "Advanced Alpha Werewolf role. Once per game at night, can instantly"
            " revive one dead wolf as a regular Werewolf for the rest of the game."
        ),
        implemented=True,
    ),
    RoleId.GUARDIAN_WOLF: RoleDef(
        role=RoleId.GUARDIAN_WOLF,
        display_name="Guardian Wolf",
        team=Team.WOLVES,
        description=(
            "Votes and chats with the wolves at night. Once per game during the day,"
            " can protect a player from being lynched by the village."
        ),
        implemented=True,
    ),
    RoleId.WOLF_TRICKSTER: RoleDef(
        role=RoleId.WOLF_TRICKSTER,
        display_name="Wolf Trickster",
        team=Team.WOLVES,
        description=(
            "Advanced Wolf Shaman role. During the day marks one player. If that"
            " player dies by any non-werewolf means, the dead player is seen as Wolf"
            " Trickster and the Wolf Trickster is seen as the dead player's role by"
            " checks. Can trigger once per game."
        ),
        implemented=True,
    ),
    RoleId.NIGHTMARE_WEREWOLF: RoleDef(
        role=RoleId.NIGHTMARE_WEREWOLF,
        display_name="Nightmare Werewolf",
        team=Team.WOLVES,
        description=(
            "Votes and chats with the wolves at night. Twice per game during the day,"
            " can put one player to sleep for the next night so they cannot use role"
            " abilities that night."
        ),
        implemented=True,
    ),
    RoleId.VOODOO_WEREWOLF: RoleDef(
        role=RoleId.VOODOO_WEREWOLF,
        display_name="Voodoo Werewolf",
        team=Team.WOLVES,
        description=(
            "Advanced Nightmare Werewolf role. Twice per game at night can mute one"
            " player for the next day (no same player on consecutive uses). Also has"
            " a one-time day nightmare to block one player's abilities for the next"
            " night."
        ),
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
    RoleId.FORGER: _villager_def(
        RoleId.FORGER,
        implemented=True,
        description=(
            "Advanced Witch role. Can forge 2 shields and 1 sword. Forging takes one"
            " day and each forged item must be given away before forging another."
            " Shields save one night attack; a sword holder may use it to kill."
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
    RoleId.GRAVE_ROBBER: _villager_def(
        RoleId.GRAVE_ROBBER,
        implemented=True,
        description=(
            "Advanced Cursed role. At game start, receives one target."
            " If that target dies, Grave Robber steals their role abilities at the"
            " start of the next day and may switch teams."
        ),
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
        description=(
            "Advanced Medium role. Talks anonymously with dead players at night and"
            " can cast a one-time delayed resurrection spell on a dead teammate."
        ),
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
    RoleId.SERIAL_KILLER: RoleDef(
        role=RoleId.SERIAL_KILLER,
        display_name="Serial Killer",
        team=Team.LONERS,
        description=(
            "Advanced Head Hunter role. Kills one player each night and is immune to"
            " the regular werewolf night attack."
        ),
        implemented=True,
    ),
    RoleId.CANNIBAL: RoleDef(
        role=RoleId.CANNIBAL,
        display_name="Cannibal",
        team=Team.LONERS,
        description=(
            "Advanced Fool role. Gains hunger each night (up to 5) and spends hunger"
            " to eat players. Can eat multiple players at once and is immune to the"
            " regular werewolf night attack."
        ),
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
        description=(
            "Advanced Loudmouth role. Distributes fortune cards that can be used to"
            " reveal a role."
        ),
    ),
    RoleId.AURA_SEER: _villager_def(
        RoleId.AURA_SEER,
        implemented=True,
        description="Inspects one player each night to learn team aura.",
    ),
    RoleId.GAMBLER: _villager_def(
        RoleId.GAMBLER,
        implemented=True,
        description=(
            "Advanced Aura Seer role. Each night, guesses one player's team."
            " Village-team guesses can only be attempted twice per game."
        ),
    ),
    RoleId.BODYGUARD: _villager_def(
        RoleId.BODYGUARD,
        implemented=True,
        description="Guards one player and may die intercepting attacks.",
    ),
    RoleId.SEER_APPRENTICE: _villager_def(
        RoleId.SEER_APPRENTICE,
        implemented=True,
        description=(
            "Advanced Bodyguard role. Starts as a normal villager. When an"
            " information-role villager dies, inherits that role and their gathered"
            " information. If that source is revived, reverts back to Seer Apprentice."
        ),
    ),
    RoleId.TOUGH_GUY: _villager_def(
        RoleId.TOUGH_GUY,
        implemented=True,
        description=(
            "Advanced Bodyguard role. Protects one player each night. If Tough Guy or"
            " their protected target is attacked, both survive the attack, Tough Guy"
            " and attacker learn each other's roles, and Tough Guy dies at the end of"
            " the following day."
        ),
    ),
    RoleId.WOLF_PACIFIST: RoleDef(
        role=RoleId.WOLF_PACIFIST,
        display_name="Wolf Pacifist",
        team=Team.WOLVES,
        description=(
            "Advanced Guardian Wolf role. Once per game during the day, may reveal one"
            " player's role privately to wolf-aligned players. If used, village voting"
            " is canceled for that day."
        ),
        implemented=True,
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
    RoleId.SORCERER: RoleDef(
        role=RoleId.SORCERER,
        display_name="Sorcerer",
        team=Team.WOLVES,
        description=(
            "Advanced Wolf Seer role. Cannot vote/chat with wolves at night but can"
            " read wolf messages. Each night privately inspects one role, may reveal"
            " checked targets to wolves twice per game, and can resign to become a"
            " regular Werewolf."
        ),
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
    RoleId.RED_LADY: _villager_def(
        RoleId.RED_LADY,
        implemented=True,
        description=(
            "Visits one player each night. If attacked while visiting, survives."
            " Dies if the host is attacked that night or is a werewolf/solo killer."
        ),
    ),
    RoleId.GHOST_LADY: _villager_def(
        RoleId.GHOST_LADY,
        implemented=True,
        description=(
            "Advanced Red Lady role. Visits one player at night and survives if"
            " attacked while visiting. If the visited player is attacked, both survive,"
            " the visited player learns Ghost Lady's role, and Ghost Lady becomes bound"
            " to that player. A bound Ghost Lady can no longer visit; if the bound"
            " player dies, Ghost Lady dies too."
        ),
    ),
    RoleId.PRIEST: _villager_def(
        RoleId.PRIEST,
        implemented=True,
        description=(
            "Once during the day, may throw Holy Water at one player."
            " If that player is werewolf-aligned, they die; otherwise the Priest dies."
        ),
    ),
    RoleId.MARKSMAN: _villager_def(
        RoleId.MARKSMAN,
        implemented=True,
        description=(
            "Advanced Priest role. Marks one target at night. During the day may"
            " spend an arrow to kill the marked target or change target. If they shoot"
            " a villager-team target, the Marksman dies instead. Has 2 arrows."
        ),
    ),
    RoleId.PACIFIST: _villager_def(
        RoleId.PACIFIST,
        implemented=True,
        description=(
            "Once during the day, may privately reveal one player's role."
            " If used, village voting is canceled for that day."
        ),
    ),
    RoleId.GRUMPY_GRANDMA: _villager_def(
        RoleId.GRUMPY_GRANDMA,
        implemented=True,
        description=(
            "Starting from night two, chooses one player each night who cannot"
            " talk or vote during the next day."
        ),
    ),
    RoleId.WARDEN: _villager_def(
        RoleId.WARDEN,
        implemented=True,
        description=(
            "Advanced Jailer role. Chooses up to two players to jail for the next"
            " night (no consecutive jailing). Jailed players can talk to each other"
            " while Warden listens. Two jailed werewolves may break out and kill the"
            " Warden. Warden may also provide a jail weapon."
        ),
    ),
    RoleId.DETECTIVE: _villager_def(
        RoleId.DETECTIVE,
        implemented=True,
        description=(
            "Each night compares two players and learns whether they are on the same"
            " team."
        ),
    ),
    RoleId.MORTICIAN: _villager_def(
        RoleId.MORTICIAN,
        implemented=True,
        description=(
            "Advanced Detective role. Each night autopsies one dead player killed by"
            " a non-villager to get suspect clues: 2 suspects for werewolf kills, 3"
            " suspects for solo-killer kills."
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
        "preist": RoleId.PRIEST,
        "grandma": RoleId.GRUMPY_GRANDMA,
        "guardian": RoleId.GUARDIAN_WOLF,
        "wolfpacifist": RoleId.WOLF_PACIFIST,
        "wolftrickster": RoleId.WOLF_TRICKSTER,
        "sorc": RoleId.SORCERER,
        "nightmare": RoleId.NIGHTMARE_WEREWOLF,
        "nightmarewolf": RoleId.NIGHTMARE_WEREWOLF,
        "voodoo": RoleId.VOODOO_WEREWOLF,
        "voodoowolf": RoleId.VOODOO_WEREWOLF,
        "graverobber": RoleId.GRAVE_ROBBER,
        "alpha": RoleId.ALPHA_WEREWOLF,
        "summoner": RoleId.WOLF_SUMMONER,
        "forger": RoleId.FORGER,
        "sk": RoleId.SERIAL_KILLER,
        "fool": RoleId.JESTER,
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

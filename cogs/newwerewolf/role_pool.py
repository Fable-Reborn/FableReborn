from __future__ import annotations

from collections.abc import Sequence

from utils import random

from .roles import RoleId, is_villager_team, is_wolf_team

_CLASSIC_FILL_SEQUENCE: list[RoleId] = [
    RoleId.VILLAGER,
    RoleId.WEREWOLF,
    RoleId.VILLAGER,
    RoleId.SEER,
    RoleId.VILLAGER,
    RoleId.DOCTOR,
    RoleId.VILLAGER,
    RoleId.HUNTER,
    RoleId.VILLAGER,
    RoleId.WITCH,
    RoleId.VILLAGER,
    RoleId.BODYGUARD,
    RoleId.JESTER,
    RoleId.AURA_SEER,
    RoleId.FLUTIST,
]

_IMBALANCED_FILL_SEQUENCE: list[RoleId] = [
    RoleId.WEREWOLF,
    RoleId.VILLAGER,
    RoleId.WHITE_WOLF,
    RoleId.VILLAGER,
    RoleId.WITCH,
    RoleId.HUNTER,
    RoleId.SEER,
    RoleId.BODYGUARD,
    RoleId.JESTER,
    RoleId.DOCTOR,
]

_HUNTERGAME_FILL_SEQUENCE: list[RoleId] = [
    RoleId.HUNTER,
    RoleId.WEREWOLF,
    RoleId.HUNTER,
    RoleId.WEREWOLF,
    RoleId.HUNTER,
    RoleId.WEREWOLF,
]

_VILLAGERGAME_FILL_SEQUENCE: list[RoleId] = [
    RoleId.VILLAGER,
    RoleId.WEREWOLF,
]

_VALENTINES_FILL_SEQUENCE: list[RoleId] = [
    RoleId.VILLAGER,
    RoleId.WEREWOLF,
    RoleId.AMOR,
    RoleId.VILLAGER,
    RoleId.WITCH,
    RoleId.SEER,
    RoleId.VILLAGER,
    RoleId.JESTER,
]


def _base_sequence_for_mode(mode: str) -> list[RoleId]:
    normalized = str(mode).strip().casefold()
    if normalized == "huntergame":
        return _HUNTERGAME_FILL_SEQUENCE
    if normalized == "villagergame":
        return _VILLAGERGAME_FILL_SEQUENCE
    if normalized == "valentines":
        return _VALENTINES_FILL_SEQUENCE
    if normalized in {"imbalanced", "idlerpg"}:
        return _IMBALANCED_FILL_SEQUENCE
    return _CLASSIC_FILL_SEQUENCE


def _ensure_required_teams(roles: list[RoleId]) -> list[RoleId]:
    has_wolf = any(is_wolf_team(role) for role in roles)
    has_villager = any(is_villager_team(role) for role in roles)

    if not roles:
        return roles

    if not has_wolf:
        replace_idx = next(
            (idx for idx, role in enumerate(roles) if not is_villager_team(role)),
            0,
        )
        roles[replace_idx] = RoleId.WEREWOLF

    if not has_villager:
        replace_idx = next(
            (idx for idx, role in enumerate(roles) if not is_wolf_team(role)),
            len(roles) - 1,
        )
        roles[replace_idx] = RoleId.VILLAGER
    return roles


def build_roles(
    *,
    player_count: int,
    mode: str,
    seeded_roles: Sequence[RoleId] | None = None,
) -> list[RoleId]:
    if player_count < 3:
        raise ValueError("NewWerewolf requires at least 3 players.")

    # Seat roles only; if caller passes > player_count seeds, truncate.
    roles = list(seeded_roles or [])[:player_count]
    sequence = _base_sequence_for_mode(mode)
    fill_index = 0
    while len(roles) < player_count:
        roles.append(sequence[fill_index % len(sequence)])
        fill_index += 1

    roles = _ensure_required_teams(roles)
    return random.shuffle(roles)

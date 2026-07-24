"""Shared formulas for endgame item progression.

This module is intentionally import-safe: no Discord, cog, or database imports.
"""
from __future__ import annotations

import math
import re
from decimal import Decimal


# Cumulative XP for level n is 100 * n^2  ->  level = floor(sqrt(xp / 100)).
def soulbound_level_from_xp(xp: int) -> int:
    return int(math.isqrt(max(0, int(xp)) // 100))


def soulbound_xp_for_level(level: int) -> int:
    return 100 * int(level) * int(level)


SOULBOUND_RANKS = [
    (1, "Awakened", "The weapon stirs. It knows your grip now.", Decimal("0.005")),
    (5, "Attuned", "It hums when danger is near.", Decimal("0.010")),
    (10, "Resonant", "It swings a heartbeat before you do.", Decimal("0.015")),
    (20, "Ascendant", "Enemies recognize it before they recognize you.", Decimal("0.020")),
    (30, "Mythic", "Songs are sung about this blade in taverns you've never visited.", Decimal("0.025")),
    (50, "Eternal", "The weapon will remember you long after the world forgets.", Decimal("0.030")),
]


def soulbound_rank_for_level(level: int):
    """Highest soulbound rank reached, or None below level 1."""
    current = None
    for threshold, title, flavor, bonus_pct in SOULBOUND_RANKS:
        if int(level) >= threshold:
            current = (title, flavor, bonus_pct)
    return current


def soulbound_bonus_pct_for_level(level: int) -> Decimal:
    rank = soulbound_rank_for_level(level)
    return rank[2] if rank else Decimal("0")


STARFORGE_MAX_STARS = 10
STARFORGE_STAT_PCT_PER_STAR = Decimal("0.04")
STARFORGE_STAR_SUFFIX_RE = re.compile(r"\s+★\d{1,2}$")
STARFORGE_ONE_HAND_MAX_STAT = 100
STARFORGE_TWO_HAND_MAX_STAT = 200
STARFORGE_NEAR_MAX_WINDOW = 5

STARFORGE_ESSENCE_COSTS = {
    1: 10,
    2: 15,
    3: 25,
    4: 40,
    5: 60,
    6: 85,
    7: 115,
    8: 150,
    9: 195,
    10: 250,
}

STARFORGE_GOLD_COSTS = {
    star: star * 250_000 for star in range(1, STARFORGE_MAX_STARS + 1)
}

STARFORGE_SUCCESS_CHANCES = {
    1: Decimal("0.85"),
    2: Decimal("0.75"),
    3: Decimal("0.65"),
    4: Decimal("0.55"),
    5: Decimal("0.45"),
    6: Decimal("0.35"),
    7: Decimal("0.30"),
    8: Decimal("0.25"),
    9: Decimal("0.20"),
    10: Decimal("0.15"),
}

STARFORGE_PITY_FAILS = {
    1: 2,
    2: 2,
    3: 3,
    4: 3,
    5: 4,
    6: 5,
    7: 5,
    8: 6,
    9: 7,
    10: 8,
}


def strip_star_suffix(name: str) -> str:
    return STARFORGE_STAR_SUFFIX_RE.sub("", str(name or "")).strip()


def starforged_name(name: str, stars: int) -> str:
    base_name = strip_star_suffix(name)
    stars = max(0, min(STARFORGE_MAX_STARS, int(stars or 0)))
    return f"{base_name} ★{stars}" if stars else base_name


def starforge_bonus_pct(stars: int) -> Decimal:
    stars = max(0, min(STARFORGE_MAX_STARS, int(stars or 0)))
    return STARFORGE_STAT_PCT_PER_STAR * stars


def starforge_next_star(stars: int) -> int | None:
    stars = int(stars or 0)
    if stars >= STARFORGE_MAX_STARS:
        return None
    return stars + 1


def starforge_cost(next_star: int) -> tuple[int, int]:
    next_star = int(next_star)
    return STARFORGE_ESSENCE_COSTS[next_star], STARFORGE_GOLD_COSTS[next_star]


def starforge_success_chance(next_star: int) -> Decimal:
    return STARFORGE_SUCCESS_CHANCES[int(next_star)]


def starforge_pity_fails(next_star: int) -> int:
    return STARFORGE_PITY_FAILS[int(next_star)]


def item_primary_stat(item: dict) -> Decimal:
    damage = Decimal(str(item.get("damage") or 0))
    armor = Decimal(str(item.get("armor") or 0))
    return max(damage, armor)


def item_max_stat(item: dict) -> int:
    return (
        STARFORGE_TWO_HAND_MAX_STAT
        if str(item.get("hand")) == "both"
        else STARFORGE_ONE_HAND_MAX_STAT
    )


def is_starforge_max_item(item: dict) -> bool:
    return item_primary_stat(item) >= Decimal(item_max_stat(item))


def is_starforge_salvage_eligible(item: dict) -> bool:
    return item_primary_stat(item) >= Decimal(
        item_max_stat(item) - STARFORGE_NEAR_MAX_WINDOW
    )


def starforge_essence_yield(item: dict) -> int:
    """Essence from salvaging near-max or max gear.

    Two-handed items yield more because their stat budget is roughly doubled.
    Being closer to max increases yield, but the range stays conservative.
    """
    if not is_starforge_salvage_eligible(item):
        return 0

    max_stat = item_max_stat(item)
    stat = int(item_primary_stat(item))
    deficit = max(0, max_stat - stat)
    closeness = STARFORGE_NEAR_MAX_WINDOW - min(deficit, STARFORGE_NEAR_MAX_WINDOW)
    if str(item.get("hand")) == "both":
        return 70 + closeness * 26
    return 35 + closeness * 13


def apply_item_progression_bonus(
    damage,
    armor,
    *,
    stars: int = 0,
    soulbound_level: int = 0,
) -> tuple[Decimal, Decimal, Decimal]:
    """Return damage, armor, and total pct after additive item-only bonuses."""
    bonus_pct = starforge_bonus_pct(stars) + soulbound_bonus_pct_for_level(soulbound_level)
    multiplier = Decimal("1") + bonus_pct
    return (
        Decimal(str(damage or 0)) * multiplier,
        Decimal(str(armor or 0)) * multiplier,
        bonus_pct,
    )

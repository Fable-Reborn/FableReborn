"""Payout math for the Hollow Manor. Kept pure so the numbers can be tuned and tested."""

import math
from dataclasses import dataclass


PASSIVE_BONES = 38
ACTIVE_BASE_BONES = 38
BONES_PER_ROOM = 50
CLEAR_BONUS = 25
OWNED_THEME_BONUS = 25
SEARCH_ROOMS = 3
# Same pool and even odds as an automatic Ragnarok spawn (cogs/raid).
CRATE_TYPES = ("divine", "fortune", "legendary", "materials")
# Halloween 2026 event themes. Manor search can grant any the player does not own.
HALLOWEEN_THEMES = (
    ("hallowmanor", "The Last Lantern"),
    ("headlesshorseman", "Hollow Rider"),
    ("ghostship", "Wraithwake"),
    ("dancingskeletons", "Bonecourt Revel"),
)
THEME_KEYS = tuple(key for key, _name in HALLOWEEN_THEMES)
THEME_NAMES = dict(HALLOWEEN_THEMES)


def theme_name(key: str | None) -> str:
    if not key:
        return THEME_NAMES[THEME_KEYS[0]]
    return THEME_NAMES.get(key, key)


@dataclass(frozen=True)
class RewardSpec:
    role: str
    bones: int
    bag_chance: float
    extra_bag_chance: float
    crate_chance: float
    theme_chance: float
    summary: str


def search_goal(investigators: int) -> int:
    """About 70% of the investigators need to search every room for a clear."""
    if investigators <= 0:
        return 1
    return max(1, math.ceil(investigators * SEARCH_ROOMS * 0.7))


def community_cleared(progress: int, goal: int, investigators: int) -> bool:
    return investigators > 0 and goal > 0 and progress >= goal


def community_struggling(progress: int, goal: int) -> bool:
    if goal <= 0:
        return True
    return (progress / goal) < 0.5


def reward_for(*, joined_as: str, rooms: int, cleared: bool, struggling: bool, owns_theme: bool) -> RewardSpec:
    """Active searchers earn more bones and better chances. Watchers get a smaller bone payout."""
    rooms = max(0, min(int(rooms), SEARCH_ROOMS))
    active = joined_as == "active" and rooms > 0
    if not active:
        bones = PASSIVE_BONES + (CLEAR_BONUS if cleared else 0)
        bag_chance = 0.04 if struggling else 0.08
        return RewardSpec(
            role="passive",
            bones=bones,
            bag_chance=bag_chance,
            extra_bag_chance=0.0,
            crate_chance=0.0,
            theme_chance=0.0,
            summary="You kept watch at the gate.",
        )

    bones = ACTIVE_BASE_BONES + (BONES_PER_ROOM * rooms)
    if cleared:
        bones += CLEAR_BONUS
    bag_chance = 0.40 + (0.15 * rooms)
    extra_bag_chance = 0.25 if rooms == SEARCH_ROOMS else 0.0
    crate_chance = 0.20 if rooms == SEARCH_ROOMS else 0.0
    if rooms == 2:
        theme_chance = 0.12
    elif rooms == SEARCH_ROOMS:
        theme_chance = 0.25
    else:
        theme_chance = 0.0
    if cleared and theme_chance:
        theme_chance = min(0.50, theme_chance * 2)
    if struggling:
        bag_chance *= 0.5
        extra_bag_chance = 0.0
        crate_chance = 0.0
        theme_chance = 0.0
    if owns_theme:
        if rooms == SEARCH_ROOMS and not struggling:
            bones += OWNED_THEME_BONUS
        theme_chance = 0.0
    room_word = "room" if rooms == 1 else "rooms"
    return RewardSpec(
        role="active",
        bones=bones,
        bag_chance=bag_chance,
        extra_bag_chance=extra_bag_chance,
        crate_chance=crate_chance,
        theme_chance=theme_chance,
        summary=f"You searched {rooms} {room_word} inside the house.",
    )

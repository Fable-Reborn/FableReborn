"""Pure progression rules for the Soulforge Frontiers update.

This module intentionally has no Discord or database imports.  The gameplay cog
uses it to decide when the weekly boss and reward become available, while tests
can validate the rules without starting the bot.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


REGULAR_DEFEATS_REQUIRED = 5
DISTINCT_SPECIES_REQUIRED = 3
ELITE_DEFEATS_REQUIRED = 1
BOSS_DEFEATS_REQUIRED = 1

WEEKLY_MONEY_REWARD = 15_000
WEEKLY_MATERIAL_CRATES = 1
WEEKLY_FORGE_REPAIR = 5


@dataclass(frozen=True)
class WeeklyProgress:
    """A normalized snapshot of one player's active Frontier week."""

    regular_defeats: int = 0
    elite_defeats: int = 0
    boss_defeats: int = 0
    distinct_species: int = 0
    reward_claimed: bool = False

    @classmethod
    def from_mapping(cls, value: Mapping[str, object] | None) -> "WeeklyProgress":
        value = value or {}
        return cls(
            regular_defeats=max(0, int(value.get("regular_defeats", 0) or 0)),
            elite_defeats=max(0, int(value.get("elite_defeats", 0) or 0)),
            boss_defeats=max(0, int(value.get("boss_defeats", 0) or 0)),
            distinct_species=max(0, int(value.get("distinct_species", 0) or 0)),
            reward_claimed=bool(value.get("reward_claimed", False)),
        )


def boss_requirements(progress: WeeklyProgress) -> dict[str, tuple[int, int]]:
    """Return current/required values for each boss-unlock objective."""

    return {
        "Regular victories": (
            progress.regular_defeats,
            REGULAR_DEFEATS_REQUIRED,
        ),
        "Different featured species": (
            progress.distinct_species,
            DISTINCT_SPECIES_REQUIRED,
        ),
        "Elite victories": (
            progress.elite_defeats,
            ELITE_DEFEATS_REQUIRED,
        ),
    }


def boss_is_unlocked(progress: WeeklyProgress) -> bool:
    """Whether all three research objectives have been completed."""

    return all(current >= required for current, required in boss_requirements(progress).values())


def weekly_reward_is_available(progress: WeeklyProgress) -> bool:
    """Whether the player beat the boss and has not claimed this week."""

    return progress.boss_defeats >= BOSS_DEFEATS_REQUIRED and not progress.reward_claimed


def objective_lines(progress: WeeklyProgress) -> list[str]:
    """Human-readable weekly objective lines suitable for a Discord embed."""

    lines = []
    for label, (current, required) in boss_requirements(progress).items():
        icon = "✅" if current >= required else "⬜"
        lines.append(f"{icon} {label}: **{min(current, required)}/{required}**")

    boss_current = min(progress.boss_defeats, BOSS_DEFEATS_REQUIRED)
    boss_icon = "✅" if boss_current >= BOSS_DEFEATS_REQUIRED else "🔒"
    lines.append(
        f"{boss_icon} Regional boss: **{boss_current}/{BOSS_DEFEATS_REQUIRED}**"
    )
    return lines


def collection_state(
    *,
    sighted: bool = False,
    defeated: bool = False,
    egg_obtained: bool = False,
    created: bool = False,
    owned: bool = False,
    mastered: bool = False,
) -> str:
    """Return the highest personal discovery state reached for a species."""

    if mastered:
        return "Mastered"
    if owned:
        return "Owned"
    if created:
        return "Personally Created"
    if egg_obtained:
        return "Egg Obtained"
    if defeated:
        return "Defeated"
    if sighted:
        return "Sighted"
    return "Unknown"


def earned_milestones(metrics: Mapping[str, int]) -> set[str]:
    """Return milestone keys earned from lifetime Frontier metrics."""

    values = {key: max(0, int(value or 0)) for key, value in metrics.items()}
    earned: set[str] = set()

    ladders = {
        "splice_sightings": ((10, "splice_scout_10"), (25, "splice_scout_25"), (50, "splice_scout_50")),
        "splice_creations": ((5, "splice_creator_5"), (15, "splice_creator_15"), (30, "splice_creator_30")),
        "max_generation": ((1, "lineage_gen_1"), (3, "lineage_gen_3"), (5, "lineage_gen_5"), (10, "lineage_gen_10")),
        "completed_lineages": ((1, "lineage_completed"),),
        "frontier_bosses": ((1, "frontier_boss_1"), (4, "frontier_boss_4"), (20, "frontier_boss_20")),
    }
    for metric, thresholds in ladders.items():
        current = values.get(metric, 0)
        for threshold, key in thresholds:
            if current >= threshold:
                earned.add(key)
    return earned


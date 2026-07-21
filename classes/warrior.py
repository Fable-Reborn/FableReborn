"""Shared Warrior Momentum rules for every combat engine."""

from __future__ import annotations

from decimal import Decimal
from functools import lru_cache


WARRIOR_EVOLUTION_LEVELS = {
    "Grunt": 1,
    "Mercenary": 2,
    "Berserker": 3,
    "Vanguard": 4,
    "Warlord": 5,
    "Champion": 6,
    "Battle Master": 7,
}

WARRIOR_MOMENTUM_CAP = 4
WARRIOR_SPLASH_RATIO = Decimal("0.35")


def _decimal(value) -> Decimal:
    return Decimal(str(value or 0))


def clamp_warrior_grade(grade: int | None) -> int:
    return max(0, min(7, int(grade or 0)))


def warrior_grade_for_classes(classes) -> int:
    raw_classes = classes if isinstance(classes, (list, tuple)) else [classes]
    return max(
        (WARRIOR_EVOLUTION_LEVELS.get(str(class_name), 0) for class_name in raw_classes or []),
        default=0,
    )


def warrior_stack_bonus_pct(grade: int) -> Decimal:
    grade = clamp_warrior_grade(grade)
    if grade <= 0:
        return Decimal("0")
    return Decimal("1") + Decimal("0.4") * Decimal(grade)


def warrior_crushing_bonus_pct(grade: int) -> Decimal:
    grade = clamp_warrior_grade(grade)
    if grade <= 0:
        return Decimal("0")
    return Decimal("25") + Decimal("4") * Decimal(grade)


def resolve_warrior_attack(
    grade: int,
    momentum: int,
    spec_effects: dict | None = None,
    *,
    roll: float | Decimal | None = None,
) -> dict:
    """Resolve one successful normal attack without mutating combat state."""
    grade = clamp_warrior_grade(grade)
    momentum = max(0, min(WARRIOR_MOMENTUM_CAP, int(momentum or 0)))
    if grade <= 0:
        return {
            "multiplier": Decimal("1"),
            "bonus_pct": Decimal("0"),
            "next_momentum": momentum,
            "crushing_blow": False,
            "extra_stack": False,
            "brace_stacks": 0,
        }

    effects = spec_effects if isinstance(spec_effects, dict) else {}
    relentless = effects.get("warrior_relentless_pct") or {}
    discipline = effects.get("warrior_discipline_pct") or {}

    if momentum >= WARRIOR_MOMENTUM_CAP:
        bonus_pct = warrior_crushing_bonus_pct(grade) + _decimal(
            relentless.get("finisher_value", 0)
        )
        return {
            "multiplier": Decimal("1") + bonus_pct / Decimal("100"),
            "bonus_pct": bonus_pct,
            "next_momentum": 0,
            "crushing_blow": True,
            "extra_stack": False,
            "brace_stacks": WARRIOR_MOMENTUM_CAP if discipline else 0,
        }

    bonus_pct = warrior_stack_bonus_pct(grade) * Decimal(momentum)
    extra_stack = False
    if relentless:
        chance = max(Decimal("0"), min(Decimal("100"), _decimal(relentless.get("value", 0))))
        roll_value = Decimal(str(roll if roll is not None else 1))
        extra_stack = roll_value < chance / Decimal("100")

    gain = 2 if extra_stack else 1
    return {
        "multiplier": Decimal("1") + bonus_pct / Decimal("100"),
        "bonus_pct": bonus_pct,
        "next_momentum": min(WARRIOR_MOMENTUM_CAP, momentum + gain),
        "crushing_blow": False,
        "extra_stack": extra_stack,
        "brace_stacks": 0,
    }


def warrior_damage_reduction_pct(
    spec_effects: dict | None,
    momentum: int,
    brace_stacks: int = 0,
) -> Decimal:
    effects = spec_effects if isinstance(spec_effects, dict) else {}
    discipline = effects.get("warrior_discipline_pct")
    if not discipline:
        return Decimal("0")

    active_stacks = max(
        0,
        min(
            WARRIOR_MOMENTUM_CAP,
            max(int(momentum or 0), int(brace_stacks or 0)),
        ),
    )
    reduction = _decimal(discipline.get("value", 0))
    reduction += _decimal(discipline.get("momentum_value", 0)) * Decimal(active_stacks)
    return max(Decimal("0"), min(Decimal("40"), reduction))


def warrior_average_damage_multiplier(grade: int, spec_effects: dict | None = None) -> Decimal:
    """Long-run expected multiplier for non-turn-based combat modes."""
    grade = clamp_warrior_grade(grade)
    if grade <= 0:
        return Decimal("1")

    effects = spec_effects if isinstance(spec_effects, dict) else {}
    relentless = effects.get("warrior_relentless_pct") or {}
    extra_chance = max(
        Decimal("0"),
        min(Decimal("1"), _decimal(relentless.get("value", 0)) / Decimal("100")),
    )
    finisher_bonus = _decimal(relentless.get("finisher_value", 0))
    return _warrior_average_damage_multiplier_cached(grade, extra_chance, finisher_bonus)


@lru_cache(maxsize=128)
def _warrior_average_damage_multiplier_cached(
    grade: int,
    extra_chance: Decimal,
    finisher_bonus: Decimal,
) -> Decimal:

    # Average the five-state Markov chain over complete cycles. A deterministic
    # non-Warlord chain is periodic, so sampling one final distribution would
    # report whichever Momentum state happened to land last.
    distribution = [Decimal("1"), Decimal("0"), Decimal("0"), Decimal("0"), Decimal("0")]
    expected_total = Decimal("0")
    sample_turns = 5000
    per_stack = warrior_stack_bonus_pct(grade)
    crushing = warrior_crushing_bonus_pct(grade) + finisher_bonus
    for _ in range(sample_turns):
        for state, probability in enumerate(distribution):
            bonus_pct = crushing if state >= WARRIOR_MOMENTUM_CAP else per_stack * Decimal(state)
            expected_total += probability * (Decimal("1") + bonus_pct / Decimal("100"))
        next_distribution = [Decimal("0") for _ in range(WARRIOR_MOMENTUM_CAP + 1)]
        for state, probability in enumerate(distribution):
            if state >= WARRIOR_MOMENTUM_CAP:
                next_distribution[0] += probability
                continue
            normal_state = min(WARRIOR_MOMENTUM_CAP, state + 1)
            extra_state = min(WARRIOR_MOMENTUM_CAP, state + 2)
            next_distribution[normal_state] += probability * (Decimal("1") - extra_chance)
            next_distribution[extra_state] += probability * extra_chance
        distribution = next_distribution
    return expected_total / Decimal(sample_turns)


def warrior_average_reduction_pct(spec_effects: dict | None) -> Decimal:
    """Expected Sentinel mitigation for stat-roll combat (two Momentum stacks)."""
    return warrior_damage_reduction_pct(spec_effects, momentum=2)

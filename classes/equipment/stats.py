"""Pure stat math for equipment. No Discord and no database imports."""
from __future__ import annotations

from decimal import Decimal

from classes.equipment.definitions import (
    ARCHETYPE_BUDGET,
    ARCHETYPES,
    MAX_REFINEMENT,
    RARITIES,
    RARITY_BUDGET,
    REFINEMENT_STEP,
    SLOT_BUDGET_SHARE,
)


def quality_scale(quality: int) -> Decimal:
    """Quality 1 keeps 55% of the budget. Quality 100 keeps all of it."""
    quality = int(quality)
    if quality < 1 or quality > 100:
        raise ValueError("quality must be from 1 to 100")
    return Decimal("0.55") + (Decimal("0.45") * Decimal(quality - 1) / Decimal(99))


def contribution(
    rarity: str,
    archetype: str,
    quality: int,
    refinement: int = 0,
    slot: str = "chest",
) -> tuple[Decimal, Decimal]:
    """Return (weapon bonus fraction, flat armor) before raid multipliers.

    Refinement scales the whole piece. It does not move an archetype's
    offense/defense ratio.
    """
    rarity = str(rarity).lower()
    archetype = str(archetype).lower()
    if rarity not in RARITIES:
        raise ValueError(f"unsupported equipment rarity: {rarity}")
    if archetype not in ARCHETYPES:
        raise ValueError(f"unsupported equipment archetype: {archetype}")
    refinement = int(refinement)
    if refinement < 0 or refinement > MAX_REFINEMENT:
        raise ValueError(f"refinement must be from 0 to {MAX_REFINEMENT}")
    slot = str(slot).lower()
    if slot not in SLOT_BUDGET_SHARE:
        raise ValueError(f"unsupported equipment slot: {slot}")

    scale = (
        RARITY_BUDGET[rarity]
        * quality_scale(quality)
        * (Decimal("1") + REFINEMENT_STEP * Decimal(refinement))
        * SLOT_BUDGET_SHARE[slot]
    )
    budget = ARCHETYPE_BUDGET[archetype]
    return budget["weapon_pct"] * scale, budget["armor"] * scale


def apply_component_bonus(
    weapon,
    armor,
    bonus_damage,
    bonus_armor,
    weapon_bonus_pct,
    gear_armor,
):
    """Scale the weapon component, then add gear armor and class/race flats.

    A zero bonus returns the same totals the combat code produced before
    equipment existed.
    """
    pct = Decimal(str(weapon_bonus_pct or 0))
    scaled_weapon = Decimal(str(weapon or 0)) * (Decimal("1") + pct)
    total_damage = scaled_weapon + Decimal(str(bonus_damage or 0))
    total_armor = (
        Decimal(str(armor or 0))
        + Decimal(str(gear_armor or 0))
        + Decimal(str(bonus_armor or 0))
    )
    return total_damage, total_armor

"""One-hit armor penetration and breakthrough.

The reflection percentage tables are not changed. This only reduces the armor
a normal hit has to cross, and the existing reflection code multiplies whatever
armor that hit actually stopped. Reflected damage is applied directly, so it
does not enter this function and cannot trigger another breakthrough.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from classes.equipment.definitions import (
    MAX_BREAKTHROUGH_BYPASS,
    MAX_BREAKTHROUGH_CHANCE,
    MAX_IGNORED_FRACTION,
    MAX_IGNORED_OF_ATTACK,
    MAX_PENETRATION,
)


@dataclass(frozen=True)
class ArmorResolution:
    armor: Decimal
    ignored: Decimal
    breakthrough: bool


def resolve_effective_armor(
    attack,
    armor,
    penetration=0,
    breakthrough_chance=0,
    breakthrough_bypass=0,
    rng=None,
    *,
    ignore_armor: bool = False,
) -> ArmorResolution:
    """Return the armor a normal hit still has to cross.

    Armor-ignoring hits, including Fireball, pass ignore_armor=True and leave
    the armor value untouched. A zero chance does not roll.
    """
    attack = Decimal(str(attack or 0))
    armor = max(Decimal("0"), Decimal(str(armor or 0)))
    if ignore_armor or attack <= 0 or armor <= 0:
        return ArmorResolution(armor, Decimal("0"), False)

    penetration = min(MAX_PENETRATION, max(Decimal("0"), Decimal(str(penetration or 0))))
    chance = min(
        MAX_BREAKTHROUGH_CHANCE,
        max(Decimal("0"), Decimal(str(breakthrough_chance or 0))),
    )
    bypass = min(
        MAX_BREAKTHROUGH_BYPASS,
        max(Decimal("0"), Decimal(str(breakthrough_bypass or 0))),
    )
    fraction = penetration
    breakthrough = False
    if chance > 0 and bypass > 0 and rng is not None and rng.random() < float(chance):
        fraction += bypass
        breakthrough = True
    fraction = min(MAX_IGNORED_FRACTION, fraction)
    if fraction <= 0:
        return ArmorResolution(armor, Decimal("0"), False)

    ignored = min(armor * fraction, attack * MAX_IGNORED_OF_ATTACK)
    effective = max(Decimal("0"), armor - ignored)
    return ArmorResolution(effective, ignored, breakthrough)

"""The Penitent class line: earned by sparing Gyle in The Tiamat Sacrament.

An order inspired by Gyle, who took wounds meant for others:

- Penance: losing HP builds Penance (max 100). Every 10 Penance held adds
  0.2% damage per evolution (Zeal), so a wounded Penitent hits harder.
- Take the Blow: when an ally is hit hard enough to fall below 35% HP, a
  Penitent holding 50 Penance steps in front of it, takes the hit instead
  (reduced by 10% + 3% per evolution) and spends the Penance.

Specs (classes/specs.py):
- Bloodlust (aggressive): up to +value% damage as your HP falls, in full at 25% HP.
- Last Shield (defensive): take value% less damage while holding 50+ Penance,
  and once per battle take an ally's killing blow for free and survive it at 1 HP.

Discord-free and works on Combatant objects (modern engine) and on the dict
combatants of the simple engines (Ice Dragon, raids).
"""
from __future__ import annotations

import math

PENANCE_CAP = 100
INTERCEPT_COST = 50
INTERCEPT_BELOW = 0.35  # an ally left under this share of max HP is worth saving
PENANCE_PER_PCT_LOST = 1.5  # losing a third of your HP fills half the meter
ZEAL_PER_10_PENANCE = 0.2  # % damage per 10 Penance, per evolution
BLOODLUST_FULL_AT = 0.25

BLOODLUST = "bloodlust_pct"
LAST_SHIELD = "last_shield_pct"


def _get(entity, key, default=None):
    if isinstance(entity, dict):
        return entity.get(key, default)
    return getattr(entity, key, default)


def _set(entity, key, value):
    if isinstance(entity, dict):
        entity[key] = value
    else:
        setattr(entity, key, value)


def _num(value) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def level(entity) -> int:
    return int(_num(_get(entity, "penitent_evolution", 0)))


def penance(entity) -> int:
    return int(_num(_get(entity, "penitent_penance", 0)))


def spec_value(entity, effect_type) -> float:
    effects = _get(entity, "spec_effects", None) or {}
    effect = effects.get(effect_type) if isinstance(effects, dict) else None
    return _num(effect.get("value")) if isinstance(effect, dict) else 0.0


def _alive(entity) -> bool:
    return _num(_get(entity, "hp", 0)) > 0


def gain_penance(entity, hp_lost) -> int:
    """Build Penance from HP lost. Returns the Penance gained."""
    if level(entity) <= 0 or _num(hp_lost) <= 0:
        return 0
    max_hp = _num(_get(entity, "max_hp", 0))
    if max_hp <= 0:
        return 0
    gained = max(1, math.ceil(_num(hp_lost) / max_hp * 100 * PENANCE_PER_PCT_LOST))
    before = penance(entity)
    after = min(PENANCE_CAP, before + gained)
    _set(entity, "penitent_penance", after)
    return after - before


def zeal_pct(entity) -> float:
    lvl = level(entity)
    return (penance(entity) // 10) * ZEAL_PER_10_PENANCE * lvl if lvl > 0 else 0.0


def bloodlust_pct(entity) -> float:
    value = spec_value(entity, BLOODLUST)
    max_hp = _num(_get(entity, "max_hp", 0))
    if value <= 0 or max_hp <= 0:
        return 0.0
    missing = 1 - max(0.0, _num(_get(entity, "hp", 0))) / max_hp
    return value * max(0.0, min(1.0, missing / (1 - BLOODLUST_FULL_AT)))


def offense_multiplier(entity) -> float:
    """Zeal plus Bloodlust, as a damage multiplier for the Penitent's own hits."""
    if level(entity) <= 0:
        return 1.0
    return 1 + (zeal_pct(entity) + bloodlust_pct(entity)) / 100


def defense_multiplier(entity) -> float:
    """Last Shield's steady guard while 50+ Penance is held."""
    value = spec_value(entity, LAST_SHIELD)
    if level(entity) <= 0 or value <= 0 or penance(entity) < INTERCEPT_COST:
        return 1.0
    return 1 - value / 100


def intercept_reduction_pct(entity) -> float:
    return 10 + 3 * level(entity)


def _can_last_shield(entity) -> bool:
    return spec_value(entity, LAST_SHIELD) > 0 and not _get(entity, "penitent_last_shield_used", False)


def find_interceptor(allies, target, damage):
    """The Penitent who steps in front of `damage` aimed at `target`, and whether it is Last Shield.

    Returns (penitent, last_shield) or (None, False).
    """
    damage = _num(damage)
    if damage <= 0 or target is None or _get(target, "is_pet", False):
        return None, False
    target_hp = _num(_get(target, "hp", 0))
    target_max = _num(_get(target, "max_hp", 0)) or target_hp
    killing = damage >= target_hp
    worth_saving = killing or (target_hp - damage) < target_max * INTERCEPT_BELOW
    if not worth_saving:
        return None, False
    best = None
    for ally in allies or ():
        if ally is target or _get(ally, "is_pet", False) or level(ally) <= 0 or not _alive(ally):
            continue
        if killing and _can_last_shield(ally):
            return ally, True
        if penance(ally) >= INTERCEPT_COST and (best is None or penance(ally) > penance(best)):
            best = ally
    return best, False


def take_the_blow(penitent, damage, last_shield=False) -> float:
    """Pay for an intercept and return the damage the Penitent takes instead.

    Last Shield costs no Penance and is capped so the Penitent survives at 1 HP;
    the caller applies the returned damage to the Penitent and 0 to the ally.
    """
    taken = _num(damage) * (1 - intercept_reduction_pct(penitent) / 100)
    if last_shield:
        _set(penitent, "penitent_last_shield_used", True)
        taken = min(taken, max(0.0, _num(_get(penitent, "hp", 0)) - 1))
    else:
        _set(penitent, "penitent_penance", max(0, penance(penitent) - INTERCEPT_COST))
    _set(penitent, "penitent_intercepts", int(_num(_get(penitent, "penitent_intercepts", 0))) + 1)
    return max(0.0, taken)


def intercept_message(penitent_name, ally_name, taken, last_shield=False) -> str:
    if last_shield:
        return (f"🛡️ **{penitent_name}** throws themself before **{ally_name}**'s killing blow: "
                f"**Last Shield**! They take **{taken:,.0f} HP** and stand at 1 HP.")
    return (f"⛓️ **{penitent_name}** takes the blow meant for **{ally_name}**, "
            f"suffering **{taken:,.0f} HP** in their place.")


def status_line(entity) -> str:
    if level(entity) <= 0:
        return ""
    line = f"⛓️ Penance: {penance(entity)}/{PENANCE_CAP}"
    if spec_value(entity, LAST_SHIELD) > 0:
        line += " · Last Shield: " + ("Spent" if _get(entity, "penitent_last_shield_used", False) else "Ready")
    return line

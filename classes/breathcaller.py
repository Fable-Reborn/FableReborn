"""The Breathcaller class line: secret, earned by holding all seven Soul Gems in Tiamat.

The power of Az'uar, who inhales elemental runes and breathes them back out:

- Inhale: an elemental attack that hits you is partly drawn in (3% + 2% per
  evolution less damage) and stored as Breath of that element. Each of your own
  attacks that doesn't exhale also draws 1 Breath from the air. Max 3 Breath.
- Exhale: at 3 Breath your next attack spends it all. It strikes as the element
  that beats the target (your strongest inhaled element if nothing does), for
  +8% + 2% per evolution damage per Breath spent.

Specs (classes/specs.py):
- Tempest Maw (aggressive): Exhale deals +value% more damage and splashes
  half of its damage onto every other enemy.
- Scaleward (defensive): take value% less damage for each Breath you hold.

Discord-free and works on Combatant objects and simple-engine dicts.
"""
from __future__ import annotations

from collections import Counter

from utils.elements import ELEMENT_STRENGTHS, normalize_element

BREATH_CAP = 3
AIR = "Unknown"  # Breath drawn from the air has no element
TEMPEST_SPLASH = 0.5

TEMPEST_MAW = "tempest_maw_pct"
SCALEWARD = "scaleward_pct"

ELEMENT_EMOJI = {
    "Fire": "🔥", "Water": "💧", "Wind": "🌪️", "Earth": "🪨", "Nature": "🌿",
    "Electric": "⚡", "Light": "✨", "Dark": "🌑", "Corrupted": "☣️", AIR: "💨",
}


def _get(entity, key, default=None):
    if isinstance(entity, dict):
        return entity.get(key, default)
    return getattr(entity, key, default)


def _set(entity, key, value):
    if isinstance(entity, dict):
        entity[key] = value
    else:
        setattr(entity, key, value)


def level(entity) -> int:
    try:
        return int(_get(entity, "breathcaller_evolution", 0) or 0)
    except (TypeError, ValueError):
        return 0


def breath(entity) -> list[str]:
    held = _get(entity, "breathcaller_breath", None)
    return list(held) if isinstance(held, (list, tuple)) else []


def spec_value(entity, effect_type) -> float:
    effects = _get(entity, "spec_effects", None) or {}
    effect = effects.get(effect_type) if isinstance(effects, dict) else None
    try:
        return float(effect.get("value", 0)) if isinstance(effect, dict) else 0.0
    except (TypeError, ValueError):
        return 0.0


def is_element(element) -> bool:
    return normalize_element(element) in ELEMENT_STRENGTHS and normalize_element(element) != AIR


def inhale_hit(entity, element) -> bool:
    """Inhale an elemental hit taken. Element-less hits give no Breath."""
    return is_element(element) and inhale(entity, element)


def inhale(entity, element=None) -> bool:
    """Store one Breath (of `element`, or from the air). False when full or not a Breathcaller."""
    if level(entity) <= 0:
        return False
    held = breath(entity)
    if len(held) >= BREATH_CAP:
        return False
    held.append(normalize_element(element) if is_element(element) else AIR)
    _set(entity, "breathcaller_breath", held)
    return True


def absorb_pct(entity) -> float:
    return 3 + 2 * level(entity) if level(entity) > 0 else 0.0


def defense_multiplier(entity, attack_element) -> float:
    """Damage multiplier on a hit the Breathcaller takes (before it inhales that hit)."""
    if level(entity) <= 0:
        return 1.0
    reduction = len(breath(entity)) * spec_value(entity, SCALEWARD)
    if is_element(attack_element):
        reduction += absorb_pct(entity)
    return max(0.0, 1 - min(reduction, 60) / 100)


def ready(entity) -> bool:
    return level(entity) > 0 and len(breath(entity)) >= BREATH_CAP


def counter_element(defense_element):
    """The element that is strong against `defense_element`, or None."""
    defense = normalize_element(defense_element)
    for attacker, beaten in ELEMENT_STRENGTHS.items():
        if beaten == defense and attacker != AIR:
            return attacker
    return None


def exhale_element(entity, defense_element):
    counter = counter_element(defense_element)
    if counter:
        return counter
    inhaled = [e for e in breath(entity) if e != AIR]
    if inhaled:
        return Counter(inhaled).most_common(1)[0][0]
    return normalize_element(_get(entity, "attack_element", None) or _get(entity, "element", None))


def exhale_bonus_pct(entity, spent) -> float:
    return (8 + 2 * level(entity)) * spent + spec_value(entity, TEMPEST_MAW)


def exhale(entity, defense_element):
    """Spend all Breath. Returns (element, damage multiplier, Breath spent)."""
    spent = len(breath(entity))
    element = exhale_element(entity, defense_element)
    _set(entity, "breathcaller_breath", [])
    _set(entity, "breathcaller_exhales", int(_get(entity, "breathcaller_exhales", 0) or 0) + 1)
    return element, 1 + exhale_bonus_pct(entity, spent) / 100, spent


def splash_share(entity) -> float:
    return TEMPEST_SPLASH if spec_value(entity, TEMPEST_MAW) > 0 else 0.0


def exhale_message(name, element, spent, bonus_pct) -> str:
    emoji = ELEMENT_EMOJI.get(element, "🐉")
    return (f"{emoji} **{name}** exhales **{spent} Breath** as **{element}** "
            f"for **+{bonus_pct:.0f}%** damage!")


def status_line(entity) -> str:
    if level(entity) <= 0:
        return ""
    held = breath(entity)
    icons = "".join(ELEMENT_EMOJI.get(e, "💨") for e in held) or "—"
    state = "Exhale ready" if len(held) >= BREATH_CAP else f"{len(held)}/{BREATH_CAP}"
    return f"🐉 Breath: {icons} ({state})"

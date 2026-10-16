"""The Dragonkin race: earned by finishing The Tiamat Sacrament (utils/tiamat_unlocks.py).

Dragonkin keep the races' balance (+2 damage, +2 armor, like Humans) and add:

- Breath Attunement: the race's personal question picks a breath (Fire, Water,
  Wind or Earth). With no element on the weapon, attacks carry it; with none on
  the armor, it defends as it. Attacks of that element hurt them 20% less.
- Blood of the Seven: against dragons they deal 10% more damage and take 10% less.

Discord-free so every battle engine can share these rules.
"""
from __future__ import annotations

from decimal import Decimal

RACE = "Dragonkin"
BREATHS = ("Fire", "Water", "Wind", "Earth")
BREATH_RESISTANCE = Decimal("0.20")
DRAGON_BONUS = Decimal("0.10")

QUESTION = "Which breath stirs in your blood?"
ANSWERS = (
    "...fire, that never goes out.",
    "...water, deep and patient.",
    "...wind, that no wall can hold.",
    "...earth, slow and unbreakable.",
)


def breath_for(cv) -> str | None:
    """The breath chosen at the race's question (stored in profile.cv)."""
    try:
        index = int(cv)
    except (TypeError, ValueError):
        return None
    return BREATHS[index] if 0 <= index < len(BREATHS) else None


def _unknown(element) -> bool:
    return not element or str(element).strip().lower() in ("unknown", "none", "")


def attuned_elements(race, cv, attack_element, defense_element):
    """(attack, defense, breath): gear elements win; the breath fills in where gear has none."""
    breath = breath_for(cv) if race == RACE else None
    if breath is None:
        return attack_element, defense_element, None
    attack = breath if _unknown(attack_element) else attack_element
    defense = breath if _unknown(defense_element) else defense_element
    return attack, defense, breath


DRAGON_WORDS = ("dragon", "drake", "wyrm", "wyvern")


def is_dragon(combatant) -> bool:
    """The Ice Dragon (flagged), or a monster whose name says it is one. Players and pets never are."""
    if combatant is None:
        return False
    if getattr(combatant, "is_dragon", False):
        return True
    if getattr(combatant, "is_pet", False):
        return False
    user = getattr(combatant, "user", None)
    if user is not None and not isinstance(user, str):  # a Discord member: a player
        return False
    name = str(getattr(combatant, "name", "") or user or "").lower()
    return any(word in name for word in DRAGON_WORDS)


def damage_multiplier(attacker, defender, attack_element) -> Decimal:
    """How Dragonkin change one hit (1 when no Dragonkin is involved)."""
    multiplier = Decimal("1")
    if getattr(attacker, "dragonkin", False) and is_dragon(defender):
        multiplier *= Decimal("1") + DRAGON_BONUS
    if getattr(defender, "dragonkin", False):
        if is_dragon(attacker):
            multiplier *= Decimal("1") - DRAGON_BONUS
        breath = getattr(defender, "dragonkin_breath", None)
        if breath and attack_element and str(attack_element).capitalize() == breath:
            multiplier *= Decimal("1") - BREATH_RESISTANCE
    return multiplier


# Profile cards: the race line reads "Dragonkin, Fire Breath" beside a small crest.
BREATH_COLOURS = {"Fire": "#ff7a3d", "Water": "#4fb3ff", "Wind": "#bfe9d2", "Earth": "#c9a050"}
CREST_GOLD = "#e8c46a"


def race_label(race, cv) -> str:
    breath = breath_for(cv) if race == RACE else None
    return f"{race}, {breath} Breath" if breath else str(race or "Unknown")


def draw_crest(draw, x, y, size, cv=None) -> None:
    """A dragon crest: gold horned shield holding a gem in the breath's colour. (x, y) is its centre."""
    s = float(size) / 2
    gem = BREATH_COLOURS.get(breath_for(cv), CREST_GOLD)
    # Horns sweep back from the top corners.
    draw.polygon([(x - s * .55, y - s * .55), (x - s * .95, y - s * 1.15), (x - s * .30, y - s * .70)], fill=CREST_GOLD)
    draw.polygon([(x + s * .55, y - s * .55), (x + s * .95, y - s * 1.15), (x + s * .30, y - s * .70)], fill=CREST_GOLD)
    shield = [(x - s * .70, y - s * .70), (x + s * .70, y - s * .70), (x + s * .70, y),
              (x, y + s), (x - s * .70, y)]
    draw.polygon(shield, fill="#2a1d10", outline=CREST_GOLD, width=max(1, int(size // 12)))
    g = s * .32
    draw.polygon([(x, y - g * 1.3), (x + g, y), (x, y + g * 1.3), (x - g, y)], fill=gem)

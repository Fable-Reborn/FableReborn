"""Deterministic game knowledge used to constrain the autonomous player."""

from __future__ import annotations

from itertools import combinations
from typing import Any, Iterable

from classes.classes import (
    Bard,
    Beastmaster,
    Mage,
    Paladin,
    Paragon,
    Raider,
    Ranger,
    Reaper,
    Ritualist,
    SantasHelper,
    Tank,
    Thief,
    Warrior,
    from_string as class_from_string,
)


CLASS_KNOWLEDGE = {
    "bard": {
        "role": "party support and sustain",
        "favored_weapons": ["Dagger", "Knife"],
        "synergy": "Best in group modes; its songs heal or empower allies.",
    },
    "beastmaster": {
        "role": "pet-focused combat",
        "favored_weapons": ["Spear"],
        "synergy": "Choose when a strong pet is available; Pack Bond raises pet stats.",
    },
    "mage": {
        "role": "high magical damage and shields",
        "favored_weapons": ["Wand"],
        "synergy": "Builds arcane charge, shields, and large fireball attacks.",
    },
    "paladin": {
        "role": "durable holy offense",
        "favored_weapons": ["Hammer"],
        "synergy": "Builds Faith for Divine Smite and Holy Shield.",
    },
    "raider": {
        "role": "sustained boss damage",
        "favored_weapons": ["Axe"],
        "synergy": "Raid Marks detonate during longer fights.",
    },
    "ranger": {
        "role": "pet utility, scouting, and egg collection",
        "favored_weapons": ["Bow"],
        "synergy": "Improves egg drops, unlocks scouting, and supports pets.",
    },
    "ritualist": {
        "role": "loot, favor, wards, and curses",
        "favored_weapons": ["Wand"],
        "synergy": "Doubles adventure loot chance and builds Doom Sigils.",
    },
    "tank": {
        "role": "maximum defense and protection",
        "favored_weapons": ["Shield"],
        "synergy": "Shields gain armor, health, reflection, and target priority.",
    },
    "thief": {
        "role": "agile offense and stealing",
        "favored_weapons": ["Dagger", "Knife"],
        "synergy": "Unlocks stealing and gains success chance with evolution.",
    },
    "warrior": {
        "role": "reliable weapon damage",
        "favored_weapons": ["Sword"],
        "synergy": "Builds Momentum and spends it on Crushing Blow.",
    },
}


FAVORED_WEAPON_BONUSES = (
    ((Paragon, Beastmaster), {"Spear": (5, 0)}),
    ((Bard, Thief), {"Dagger": (5, 0), "Knife": (5, 0)}),
    ((Warrior,), {"Sword": (5, 0)}),
    ((Ranger,), {"Bow": (10, 0)}),
    ((Mage, Ritualist), {"Wand": (5, 0)}),
    ((Raider,), {"Axe": (5, 0)}),
    ((Paladin,), {"Hammer": (5, 0)}),
    ((Reaper,), {"Scythe": (10, 0)}),
    ((SantasHelper,), {"Mace": (5, 0)}),
    ((Tank,), {"Shield": (0, 7)}),
)


def _class_lines(class_names: Iterable[str]) -> set[type]:
    lines = set()
    for class_name in class_names:
        resolved = class_from_string(class_name)
        if resolved is not None:
            lines.add(resolved.get_class_line())
    return lines


def favored_item_bonus(
    item_type: str, class_names: Iterable[str]
) -> tuple[float, float]:
    lines = _class_lines(class_names)
    damage = 0.0
    armor = 0.0
    for class_lines, bonuses in FAVORED_WEAPON_BONUSES:
        if any(class_line in lines for class_line in class_lines) and item_type in bonuses:
            item_damage, item_armor = bonuses[item_type]
            damage += item_damage
            armor += item_armor
    return damage, armor


def is_valid_loadout(items: Iterable[dict[str, Any]]) -> bool:
    items = list(items)
    if not 1 <= len(items) <= 2:
        return False
    hands = [str(item.get("hand") or "any").lower() for item in items]
    if len(items) == 1:
        return True
    if "both" in hands:
        return False
    fixed_hands = [hand for hand in hands if hand in {"left", "right"}]
    return len(fixed_hands) == len(set(fixed_hands))


def score_loadout(
    items: Iterable[dict[str, Any]], class_names: Iterable[str]
) -> dict[str, Any]:
    damage = 0.0
    armor = 0.0
    item_ids = []
    for item in items:
        item_ids.append(int(item["id"]))
        damage += float(item.get("effective_damage", item.get("damage", 0)) or 0)
        armor += float(item.get("effective_armor", item.get("armor", 0)) or 0)
        bonus_damage, bonus_armor = favored_item_bonus(
            str(item.get("type") or ""), class_names
        )
        damage += bonus_damage
        armor += bonus_armor
    return {
        "item_ids": sorted(item_ids),
        "effective_damage": round(damage, 2),
        "effective_armor": round(armor, 2),
        "score": round(damage + armor, 2),
    }


def choose_best_equipment(
    items: Iterable[dict[str, Any]],
    class_names: Iterable[str],
    current_item_ids: Iterable[int],
) -> dict[str, Any] | None:
    items = [dict(item) for item in items]
    if not items:
        return None
    current_ids = {int(item_id) for item_id in current_item_ids}

    # Keep the best few items of each type plus anything currently equipped.
    # This prevents a huge inventory from producing thousands of combinations.
    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in items:
        grouped.setdefault(str(item.get("type") or "Unknown"), []).append(item)
    candidates_by_id: dict[int, dict[str, Any]] = {}
    for group in grouped.values():
        ranked = sorted(
            group,
            key=lambda item: score_loadout([item], class_names)["score"],
            reverse=True,
        )
        for item in ranked[:4]:
            candidates_by_id[int(item["id"])] = item
    for item in items:
        if int(item["id"]) in current_ids:
            candidates_by_id[int(item["id"])] = item

    candidates = list(candidates_by_id.values())
    loadouts = [(item,) for item in candidates]
    loadouts.extend(
        pair for pair in combinations(candidates, 2) if is_valid_loadout(pair)
    )

    def rank(loadout):
        result = score_loadout(loadout, class_names)
        is_current = set(result["item_ids"]) == current_ids
        return (
            result["score"],
            is_current,
            result["effective_damage"],
            result["effective_armor"],
        )

    best = max(loadouts, key=rank)
    return score_loadout(best, class_names)


def pet_combat_score(pet: dict[str, Any]) -> float:
    stage_multiplier = {
        "baby": 0.25,
        "juvenile": 0.50,
        "young": 0.75,
        "adult": 1.0,
    }.get(str(pet.get("growth_stage") or "baby").lower(), 0.25)
    base = (
        float(pet.get("hp") or 0) * 0.1
        + float(pet.get("attack") or 0) * 2
        + float(pet.get("defense") or 0)
    )
    level_multiplier = 1 + max(1, min(int(pet.get("level") or 1), 100)) / 100
    trust_multiplier = 0.9 + max(0, min(int(pet.get("trust_level") or 0), 100)) / 500
    return round(base * stage_multiplier * level_multiplier * trust_multiplier, 2)


def choose_best_pet(pets: Iterable[dict[str, Any]]) -> int | None:
    equippable = [
        pet
        for pet in pets
        if not pet.get("daycare_boarding_id")
        and str(pet.get("growth_stage") or "").lower() in {"young", "adult"}
    ]
    if not equippable:
        return None
    return int(max(equippable, key=pet_combat_score)["id"])


def combat_health_state(
    *,
    level: int,
    profile_health_bonus: float,
    allocated_health_points: float,
    amulet_hp: float = 0,
) -> dict[str, Any]:
    """Describe Fable's battle HP without treating profile.health as current HP."""
    base_hp = 200.0
    level_hp = max(1, int(level)) * 15.0
    allocated_hp = float(allocated_health_points or 0) * 50.0
    profile_bonus = float(profile_health_bonus or 0)
    amulet_bonus = float(amulet_hp or 0)
    baseline_max_hp = base_hp + level_hp + allocated_hp + profile_bonus + amulet_bonus
    return {
        "uses_persistent_current_hp": False,
        "current_hp": None,
        "is_dead": False,
        "profile_health_bonus": round(profile_bonus, 2),
        "profile_health_bonus_is_current_hp": False,
        "allocated_health_points": round(float(allocated_health_points or 0), 2),
        "hp_per_allocated_point": 50,
        "base_hp": int(base_hp),
        "level_hp": round(level_hp, 2),
        "amulet_hp": round(amulet_bonus, 2),
        "baseline_combat_max_hp": round(baseline_max_hp, 2),
        "explanation": (
            "Battles initialize HP from these stats. A profile health bonus of 0 "
            "is normal and never means the character is dead. Class and encounter "
            "effects may further change final battle HP."
        ),
    }

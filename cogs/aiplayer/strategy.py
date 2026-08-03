"""Deterministic game knowledge used to constrain the autonomous player."""

from __future__ import annotations

from itertools import combinations
from math import sqrt
from random import Random
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
from utils.elements import calculate_element_modifier


CLASS_KNOWLEDGE = {
    "bard": {
        "role": "party support and sustain",
        "favored_weapons": ["Dagger", "Knife"],
        "favored_weapon_bonus": "+5 damage for each equipped Dagger or Knife",
        "combat_mechanics": (
            "Bardic Refrain heals the whole Battle Tower party for 0.5% maximum "
            "HP per class grade at the end of the Bard's turn. In Ice Dragon, only "
            "the strongest Bard song applies and grants 1.7% party damage per grade."
        ),
        "evolution_scaling": (
            "Grade 1-7 scales party healing from 0.5% to 3.5% and party damage "
            "from 1.7% to 11.9%."
        ),
        "best_for": "group battles, party survival, and improving every ally",
        "limitations": "Less valuable alone; duplicate Bard songs do not stack.",
        "synergy": "Pairs well with a personal damage or tank class in slot two.",
        "availability": "standard",
    },
    "beastmaster": {
        "role": "pet-focused combat",
        "favored_weapons": ["Spear"],
        "favored_weapon_bonus": "+5 damage for each equipped Spear",
        "combat_mechanics": (
            "Pack Bond increases the equipped pet's HP, attack, and defense in "
            "Battle Tower and Ice Dragon fights."
        ),
        "evolution_scaling": "+3% to every equipped-pet combat stat per grade, from +3% to +21%.",
        "best_for": "a developed, regularly equipped combat pet",
        "limitations": "Provides little value without an eligible equipped pet.",
        "synergy": "Combines especially well with Ranger's pet utility.",
        "availability": "standard",
    },
    "mage": {
        "role": "high magical damage and shields",
        "favored_weapons": ["Wand"],
        "favored_weapon_bonus": "+5 damage for each equipped Wand",
        "combat_mechanics": (
            "Each grade adds +1 flat equipment damage. Successful normal hits "
            "build arcane charge and Arcane Shield until a Fireball is released."
        ),
        "evolution_scaling": (
            "Grade 1-7 raises Fireball damage from 110% to 210%, shield gain per "
            "charging hit from 3.5% to 6.5% max HP, and the Arcane Shield cap "
            "from 15% to 26% max HP."
        ),
        "best_for": "burst damage with self-shielding",
        "limitations": "Fireball timing depends on the battle mode's charge rate.",
        "synergy": "Wands also suit Ritualist, making that an equipment-efficient pairing.",
        "availability": "standard",
    },
    "paladin": {
        "role": "durable holy offense",
        "favored_weapons": ["Hammer"],
        "favored_weapon_bonus": "+5 damage for each equipped Hammer",
        "combat_mechanics": (
            "Every third successful hit consumes Faith for Divine Smite bonus "
            "damage and grants Holy Shield. Also unlocks bless for granting "
            "another player a temporary adventure XP bonus."
        ),
        "evolution_scaling": (
            "Grade 1-7 raises Smite from 20% to 50% of attack, shield gain from "
            "4% to 10% max HP, and the Holy Shield cap from 12% to 24% max HP."
        ),
        "best_for": "balanced offense, durability, and helping another player's XP gain",
        "limitations": "Smite requires three successful hits.",
        "synergy": "Pairs well with another sustained class or a defensive Tank.",
        "availability": "standard",
    },
    "raider": {
        "role": "sustained boss damage",
        "favored_weapons": ["Axe"],
        "favored_weapon_bonus": "+5 damage for each equipped Axe",
        "combat_mechanics": (
            "Successful hits mark the current target; every third mark detonates "
            "for bonus damage based on attack and the target's maximum HP."
        ),
        "evolution_scaling": (
            "Grade 1-7 raises the attack-based detonation component from 15% to "
            "35% and the max-HP component from 1% to 2.5%."
        ),
        "best_for": "long boss fights against high-HP targets",
        "limitations": "Marks are less useful when targets die or change before the third hit.",
        "synergy": "Pairs with survivability or support that keeps it attacking one target.",
        "availability": "standard",
    },
    "ranger": {
        "role": "pet utility, scouting, and egg collection",
        "favored_weapons": ["Bow"],
        "favored_weapon_bonus": "+10 damage for each equipped Bow",
        "combat_mechanics": (
            "Unlocks scouting/rerolls for PvE preparation, Ranger pet hunting, "
            "and an increased chance to find eggs."
        ),
        "evolution_scaling": (
            "Grade 1-7 raises the base egg bonus through 2%, 4%, 6%, 8%, 10%, "
            "13%, and 15%; some encounters apply an additional multiplier."
        ),
        "best_for": "pet collection, egg acquisition, scouting, and Bow damage",
        "limitations": "Much of its value is utility rather than direct class-trigger damage.",
        "synergy": "Beastmaster converts a strong collected pet into more combat power.",
        "availability": "standard",
    },
    "ritualist": {
        "role": "loot, favor, wards, and curses",
        "favored_weapons": ["Wand"],
        "favored_weapon_bonus": "+5 damage for each equipped Wand",
        "combat_mechanics": (
            "Doubles the chance of adventure loot, improves sacrifices by 5% "
            "per grade, and builds Doom Sigils that burst, echo on later hits, "
            "and grant Favor Ward when a doomed enemy dies."
        ),
        "evolution_scaling": (
            "Grade 1-7 raises Doom burst from 12% to 30% of attack, Doom Echo "
            "from 6% to 12%, ward gain from 4% to 10% max HP, and its cap from "
            "12% to 24%."
        ),
        "best_for": "adventure loot, sacrifice/favor progression, and ramping curse damage",
        "limitations": "Its combat effects need repeated hits and target persistence.",
        "synergy": "Shares Wand equipment with Mage and benefits players who actively use gods/favor.",
        "availability": "standard",
    },
    "tank": {
        "role": "maximum defense and protection",
        "favored_weapons": ["Shield"],
        "favored_weapon_bonus": "+7 armor for each equipped Shield",
        "combat_mechanics": (
            "With a Shield, gains substantially more maximum HP and reflects "
            "damage using a finite reflective plate. It also has 60% target "
            "priority in Ice Dragon to protect allies."
        ),
        "evolution_scaling": (
            "Grade 1-7 scales shielded maximum HP from +5% to +35% and reflected "
            "damage from 3% to 21%. Without a Shield, only the much smaller "
            "unshielded health scaling applies."
        ),
        "best_for": "survival, protecting groups, and defensive builds",
        "limitations": "Requires an equipped Shield for its full health, armor, and reflection value.",
        "synergy": "Pairs with support or damage while covering their survivability.",
        "availability": "standard",
    },
    "thief": {
        "role": "agile offense and stealing",
        "favored_weapons": ["Dagger", "Knife"],
        "favored_weapon_bonus": "+5 damage for each equipped Dagger or Knife",
        "combat_mechanics": "Unlocks steal, which attempts to take 10% of a random player's money.",
        "evolution_scaling": "+8 percentage points to steal success chance per grade.",
        "best_for": "active money stealing and Dagger/Knife equipment",
        "limitations": "Its distinctive progression benefit is economic and the steal attempt can fail.",
        "synergy": "Shares favored weapons with Bard.",
        "availability": "standard",
    },
    "warrior": {
        "role": "reliable weapon damage",
        "favored_weapons": ["Sword"],
        "favored_weapon_bonus": "+5 damage for each equipped Sword",
        "combat_mechanics": (
            "Successful normal attacks build Momentum up to four stacks. Existing "
            "stacks strengthen the next hit; attacking at four consumes them for "
            "Crushing Blow, which also cleaves nearby enemies for 35% of the hit."
        ),
        "evolution_scaling": (
            "Momentum and Crushing Blow improve every grade. At grade 7 each stack "
            "adds 3.8% damage (15.2% at four), and Crushing Blow adds 53% damage."
        ),
        "best_for": "dependable general combat, multi-target cleave, and Sword loadouts",
        "limitations": "Needs repeated successful attacks to reach its strongest hit.",
        "synergy": "A broadly useful damage class that pairs with defense, support, or utility.",
        "availability": "standard",
    },
    "paragon": {
        "role": "adaptive premium offense and defense",
        "favored_weapons": ["Spear"],
        "favored_weapon_bonus": "+5 damage for each equipped Spear",
        "combat_mechanics": (
            "Each grade adds +1 flat damage and +1 flat defense. Adaptive Mastery "
            "adds damage against armored targets, barriers against dangerous attackers, "
            "or a smaller balanced mixture."
        ),
        "evolution_scaling": (
            "Grade 1-7 raises armor-breaking bonus damage from 8% to 20%, defensive "
            "shield gain from 2% to 5% max HP, balanced damage from 4% to 10%, "
            "and balanced shield gain from 1% to 2.5%."
        ),
        "best_for": "an all-purpose adaptive build with both flat offense and defense",
        "limitations": "Premium/donator availability; not offered unless actually unlocked.",
        "synergy": "Shares Spear equipment with Beastmaster.",
        "availability": "donator/unlock restricted",
    },
    "reaper": {
        "role": "high-risk soul damage, sustain, and death prevention",
        "favored_weapons": ["Scythe"],
        "favored_weapon_bonus": "+10 damage for each equipped Scythe",
        "combat_mechanics": (
            "Successful attacks harvest Souls and kills grant two. At five Souls it "
            "becomes Avatar of Death for three attacks, gaining damage and life drain; "
            "a fatal hit during Avatar is prevented and returns it under Death Shroud."
        ),
        "evolution_scaling": "Higher grades strengthen its damage, sustain, and non-Avatar death-cheat chance.",
        "best_for": "aggressive combat with self-healing and protection from a fatal blow",
        "limitations": "Seasonal/unlock restricted and must build Souls during combat.",
        "synergy": "Pairs well with steady defense that gives time to reach Avatar.",
        "availability": "Halloween unlock or qualifying premium tier",
    },
    "santashelper": {
        "role": "seasonal damage, healing, shielding, and gifting",
        "favored_weapons": ["Mace"],
        "favored_weapon_bonus": "+5 damage for each equipped Mace",
        "combat_mechanics": (
            "Successful attacks build Cheer. Every third hit opens a random Combat "
            "Present for damage, weakest-ally healing, or party shielding; every third "
            "present becomes a Golden Gift that triggers all three. Unlocks gift."
        ),
        "evolution_scaling": "Higher grades improve combat effects, lifesteal, and gift quality.",
        "best_for": "flexible party combat with sustain and seasonal utility",
        "limitations": "Seasonal/unlock restricted and its presents are partly random.",
        "synergy": "Complements either damage or tank classes with mixed party support.",
        "availability": "Christmas unlock or qualifying premium tier",
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


def favored_weapon_bonus_rules() -> list[dict[str, Any]]:
    """Return the live class/weapon bonus table in JSON-safe form."""
    rules = []
    for class_lines, bonuses in FAVORED_WEAPON_BONUSES:
        for weapon_type, (damage, armor) in bonuses.items():
            rules.append(
                {
                    "class_lines": [line.__name__ for line in class_lines],
                    "weapon_type": weapon_type,
                    "damage_per_matching_item": damage,
                    "armor_per_matching_item": armor,
                }
            )
    return rules


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
    base_damage = 0.0
    base_armor = 0.0
    class_bonus_damage = 0.0
    class_bonus_armor = 0.0
    item_ids = []
    for item in items:
        item_ids.append(int(item["id"]))
        base_damage += float(
            item.get("effective_damage", item.get("damage", 0)) or 0
        )
        base_armor += float(
            item.get("effective_armor", item.get("armor", 0)) or 0
        )
        bonus_damage, bonus_armor = favored_item_bonus(
            str(item.get("type") or ""), class_names
        )
        class_bonus_damage += bonus_damage
        class_bonus_armor += bonus_armor
    damage = base_damage + class_bonus_damage
    armor = base_armor + class_bonus_armor
    return {
        "item_ids": sorted(item_ids),
        "base_effective_damage": round(base_damage, 2),
        "base_effective_armor": round(base_armor, 2),
        "class_weapon_bonus_damage": round(class_bonus_damage, 2),
        "class_weapon_bonus_armor": round(class_bonus_armor, 2),
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


def egg_combat_score(egg: dict[str, Any]) -> float:
    """Score an unhatched egg by the pet it will actually become.

    An egg row's hp/attack/defense are already the monster species' base stats
    plus its rolled IV points, so this captures both species quality and roll
    quality. IV percent alone does not: a 95% roll on a weak species is worse
    than a 60% roll on a strong one. The weighting matches pet_combat_score's
    base term so egg and pet scores stay comparable; growth, level, and trust
    multipliers are omitted because an egg has none of them yet.
    """
    return round(
        float(egg.get("hp") or 0) * 0.1
        + float(egg.get("attack") or 0) * 2
        + float(egg.get("defense") or 0),
        2,
    )


def choose_weakest_egg(eggs: Iterable[dict[str, Any]]) -> dict[str, Any] | None:
    """Return the owned egg that costs the least to give up, or None."""
    candidates = [egg for egg in eggs if egg.get("id") is not None]
    if not candidates:
        return None
    # Ties break toward the lower id, so repeated drops stay deterministic
    # instead of churning between two identically scored eggs.
    return min(
        candidates,
        key=lambda egg: (egg_combat_score(egg), int(egg["id"])),
    )


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


RAID_MATCHUP_SIMULATIONS = 800


def _raid_number(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if number != number or number in (float("inf"), float("-inf")):
        return default
    return max(0.0, number)


def _raid_probability(value: Any) -> float:
    probability = _raid_number(value)
    if probability > 1:
        probability /= 100
    return min(1.0, probability)


def _pet_skill_estimates(skill_effects: Any, defense: float) -> dict[str, float]:
    """Approximate the common numerical pet-skill effects used by raid battles.

    The battle engine still has many stateful skills whose exact timing depends on
    targets and prior turns. These estimates intentionally cover only effects that
    can be represented safely without mutating a real combatant.
    """
    result = {
        "attack_multiplier": 1.0,
        "armor_bypass_chance": 0.0,
        "block_chance": 0.0,
        "reflection": 0.0,
        "starting_shield": 0.0,
    }
    if not isinstance(skill_effects, dict):
        return result

    for effect in skill_effects.values():
        if not isinstance(effect, dict):
            continue
        effect_type = str(effect.get("type") or "").lower()
        chance = _raid_probability(effect.get("chance", 0))

        if effect_type == "on_attack" and "damage_multiplier" in effect:
            multiplier = max(1.0, _raid_number(effect.get("damage_multiplier"), 1.0))
            result["attack_multiplier"] *= 1 + chance * (multiplier - 1)
        elif effect_type in {"conditional_passive", "execute"}:
            result["attack_multiplier"] *= 1 + _raid_number(
                effect.get("damage_bonus"), 0
            ) * 0.35
        elif effect_type == "ultimate" and "damage_multiplier" in effect:
            # Ultimates are powerful but intermittent; model roughly one proc in
            # six pet actions rather than treating them as permanent damage.
            multiplier = max(1.0, _raid_number(effect.get("damage_multiplier"), 1.0))
            result["attack_multiplier"] *= 1 + (multiplier - 1) / 6

        if effect_type == "ignore_armor":
            result["armor_bypass_chance"] = max(
                result["armor_bypass_chance"], chance
            )
        elif effect_type == "block_attack":
            result["block_chance"] = max(result["block_chance"], chance)
        elif effect_type == "on_damage_taken" and "reflect_percent" in effect:
            result["reflection"] = max(
                result["reflection"],
                chance * _raid_probability(effect.get("reflect_percent")),
            )
        elif effect_type == "shield":
            result["starting_shield"] += defense * _raid_number(
                effect.get("shield_multiplier"), 0
            )

    # Keep incomplete skill approximations from overpowering the observed stats.
    result["attack_multiplier"] = min(1.75, result["attack_multiplier"])
    result["armor_bypass_chance"] = min(0.75, result["armor_bypass_chance"])
    result["block_chance"] = min(0.50, result["block_chance"])
    result["reflection"] = min(0.75, result["reflection"])
    return result


def _raid_actor(
    source: dict[str, Any],
    *,
    is_pet: bool,
    class_effects: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    if not isinstance(source, dict) or not source:
        return None
    hp = _raid_number(source.get("max_hp"))
    if hp <= 0:
        return None
    attack = _raid_number(source.get("attack"))
    defense = _raid_number(source.get("defense"))
    effects = class_effects if isinstance(class_effects, dict) else {}
    skill_estimates = _pet_skill_estimates(source.get("skill_effects"), defense)
    dual_elements = source.get("dual_attack_elements")
    if not isinstance(dual_elements, list) or not dual_elements:
        dual_elements = [
            source.get("element") if is_pet else source.get("attack_element")
        ]
    attack_elements = [str(element or "Unknown") for element in dual_elements]
    reflection = _raid_probability(effects.get("damage_reflection", 0))
    if is_pet:
        reflection = max(reflection, skill_estimates["reflection"])
    return {
        "is_pet": is_pet,
        "max_hp": hp,
        "attack": attack,
        "armor": defense,
        "luck": min(100.0, _raid_number(source.get("luck_percent"), 50.0)),
        "attack_elements": attack_elements,
        "defense_element": str(
            source.get("element")
            if is_pet
            else source.get("defense_element")
            or "Unknown"
        ),
        "lifesteal": _raid_probability(effects.get("lifesteal_percent", 0)),
        "death_cheat": _raid_probability(effects.get("death_cheat_chance", 0)),
        "reaper_evolution": int(_raid_number(effects.get("reaper_evolution", 0))),
        "reflection": reflection,
        "attack_multiplier": skill_estimates["attack_multiplier"],
        "armor_bypass_chance": skill_estimates["armor_bypass_chance"],
        "block_chance": skill_estimates["block_chance"],
        "starting_shield": _raid_number(source.get("shield", 0))
        + skill_estimates["starting_shield"],
        "pet_skill_count": len(source.get("skill_effects") or {})
        if isinstance(source.get("skill_effects"), dict)
        else 0,
    }


def _raid_team(
    stats: dict[str, Any], *, class_buffs_enabled: bool = True
) -> list[dict[str, Any]] | None:
    if not isinstance(stats, dict) or not stats.get("available"):
        return None
    effects = (stats.get("class_combat_effects") or {}) if class_buffs_enabled else {}
    player = _raid_actor(
        stats.get("final_raidbattle_stats") or {},
        is_pet=False,
        class_effects=effects,
    )
    if player is None:
        return None
    team = [player]
    pet = _raid_actor(stats.get("raidbattle_pet") or {}, is_pet=True)
    if pet is not None:
        team.append(pet)
    return team


def _copy_raid_team(team: list[dict[str, Any]]) -> list[dict[str, Any]]:
    copied = []
    for template in team:
        actor = dict(template)
        actor["hp"] = actor["max_hp"]
        actor["shield"] = actor["starting_shield"]
        actor["death_cheat_used"] = False
        actor["element_index"] = 0
        copied.append(actor)
    return copied


def _choose_raid_target(
    rng: Random, defenders: list[dict[str, Any]]
) -> dict[str, Any]:
    alive = [actor for actor in defenders if actor["hp"] > 0]
    if len(alive) == 1:
        return alive[0]
    weights = [0.4 if actor["is_pet"] else 0.6 for actor in alive]
    pick = rng.random() * sum(weights)
    for actor, weight in zip(alive, weights):
        pick -= weight
        if pick <= 0:
            return actor
    return alive[-1]


def _raid_team_lost(
    team: list[dict[str, Any]],
    *,
    challenger_side: bool,
    challenger_pets_continue: bool = False,
) -> bool:
    if challenger_side and not challenger_pets_continue:
        # The real RaidBattle currently ends Team A's fight when its player is
        # down unless the server enables pets_continue_battle.
        return not any(not actor["is_pet"] and actor["hp"] > 0 for actor in team)
    return not any(actor["hp"] > 0 for actor in team)


def _simulate_raid_once(
    ours_template: list[dict[str, Any]],
    theirs_template: list[dict[str, Any]],
    rng: Random,
    *,
    element_effects: bool,
    reflection_damage: bool,
    cheat_death: bool,
    tripping: bool,
    challenger_pets_continue: bool,
) -> bool:
    ours = _copy_raid_team(ours_template)
    theirs = _copy_raid_team(theirs_template)
    turn_order = [("ours", actor) for actor in ours] + [
        ("theirs", actor) for actor in theirs
    ]
    rng.shuffle(turn_order)

    for _ in range(320):
        side, attacker = turn_order[_ % len(turn_order)]
        if attacker["hp"] <= 0:
            continue
        defenders = theirs if side == "ours" else ours
        target = _choose_raid_target(rng, defenders)

        if rng.random() * 100 > attacker["luck"]:
            if tripping:
                attacker["hp"] -= 10
        elif rng.random() >= target["block_chance"]:
            attack_element = attacker["attack_elements"][
                attacker["element_index"] % len(attacker["attack_elements"])
            ]
            attacker["element_index"] += 1
            element_multiplier = 1.0
            if element_effects:
                element_multiplier += calculate_element_modifier(
                    attack_element, target["defense_element"]
                )
            variance = rng.randint(0, 50 if attacker["is_pet"] else 100)
            raw_damage = (
                attacker["attack"]
                * attacker["attack_multiplier"]
                * element_multiplier
                + variance
            )
            bypass_armor = rng.random() < attacker["armor_bypass_chance"]
            blocked_damage = 0.0 if bypass_armor else min(raw_damage, target["armor"])
            damage = raw_damage if bypass_armor else max(10.0, raw_damage - target["armor"])
            if target["shield"] > 0:
                absorbed = min(target["shield"], damage)
                target["shield"] -= absorbed
                damage -= absorbed
            target["hp"] -= damage
            if attacker["lifesteal"] > 0:
                attacker["hp"] = min(
                    attacker["max_hp"],
                    attacker["hp"] + damage * attacker["lifesteal"],
                )
            if reflection_damage and target["reflection"] > 0 and blocked_damage > 0:
                attacker["hp"] -= blocked_damage * target["reflection"]

            if (
                cheat_death
                and target["hp"] <= 0
                and not target["is_pet"]
                and not target["death_cheat_used"]
                and rng.random() < target["death_cheat"]
            ):
                target["death_cheat_used"] = True
                if target["reaper_evolution"] > 0:
                    recovery = 0.12 + 0.025 * target["reaper_evolution"]
                    target["hp"] = max(1.0, target["max_hp"] * recovery)
                else:
                    target["hp"] = min(
                        target["max_hp"], max(75.0, target["max_hp"] * 0.5)
                    )

        if _raid_team_lost(
            theirs,
            challenger_side=True,
            challenger_pets_continue=challenger_pets_continue,
        ):
            return True
        if _raid_team_lost(ours, challenger_side=False):
            return False

    # This mirrors the real timeout tiebreaker, which compares player HP ratios
    # and awards Team B (Densetsu for incoming offers) an exact tie.
    ours_player = next(actor for actor in ours if not actor["is_pet"])
    theirs_player = next(actor for actor in theirs if not actor["is_pet"])
    ours_ratio = max(0.0, ours_player["hp"]) / ours_player["max_hp"]
    theirs_ratio = max(0.0, theirs_player["hp"]) / theirs_player["max_hp"]
    return ours_ratio >= theirs_ratio


def required_raid_win_probability(*, wager: int, bankroll: int) -> float:
    """Return the conservative win probability needed for an even-money wager."""
    wager = max(0, int(wager))
    bankroll = max(0, int(bankroll))
    if wager == 0:
        return 0.35
    if bankroll <= 0:
        return 1.0
    exposure = min(1.0, wager / bankroll)
    # A bet needs a real edge. The required edge grows from 52% for negligible
    # exposure to 75% at the normal 10%-of-bankroll wager ceiling.
    return min(0.95, 0.52 + 2.3 * exposure)


def evaluate_raid_matchup(
    ours: dict[str, Any],
    theirs: dict[str, Any],
    *,
    wager: int,
    bankroll: int,
    simulations: int = RAID_MATCHUP_SIMULATIONS,
) -> dict[str, Any]:
    """Estimate whether Densetsu can safely accept an incoming raidbattle."""
    raid_settings = ours.get("raidbattle_settings") or {}

    def setting(name: str, default: bool) -> bool:
        value = raid_settings.get(name)
        return default if value is None else bool(value)

    class_buffs_enabled = setting("class_buffs", True)
    ours_team = _raid_team(ours, class_buffs_enabled=class_buffs_enabled)
    theirs_team = _raid_team(theirs, class_buffs_enabled=class_buffs_enabled)
    required = required_raid_win_probability(wager=wager, bankroll=bankroll)
    exposure = 0.0 if bankroll <= 0 else min(1.0, max(0, wager) / bankroll)
    if ours_team is None or theirs_team is None:
        return {
            "available": False,
            "acceptance_allowed": False,
            "reason": "Complete battle-start stats were not available for both sides.",
            "minimum_required_win_probability_percent": round(required * 100, 1),
            "wager_percent_of_bankroll": round(exposure * 100, 2),
        }

    simulations = max(100, min(5_000, int(simulations)))
    rng = Random(0xD3E75A)
    wins = sum(
        _simulate_raid_once(
            ours_team,
            theirs_team,
            rng,
            element_effects=setting("element_effects", True),
            reflection_damage=setting("reflection_damage", True),
            cheat_death=setting("cheat_death", True),
            tripping=setting("tripping", True),
            challenger_pets_continue=setting("pets_continue_battle", False),
        )
        for _ in range(simulations)
    )
    estimate = wins / simulations

    # One-sided 90% Wilson lower bound: acceptance uses the conservative value,
    # not a lucky point estimate from the simulations.
    z = 1.644854
    z2 = z * z
    denominator = 1 + z2 / simulations
    center = estimate + z2 / (2 * simulations)
    margin = z * sqrt(
        (estimate * (1 - estimate) + z2 / (4 * simulations)) / simulations
    )
    conservative = max(0.0, (center - margin) / denominator)

    ours_attack = sum(actor["attack"] for actor in ours_team)
    theirs_attack = sum(actor["attack"] for actor in theirs_team)
    ours_hp = sum(actor["max_hp"] + actor["starting_shield"] for actor in ours_team)
    theirs_hp = sum(actor["max_hp"] + actor["starting_shield"] for actor in theirs_team)
    ours_pet = next((actor for actor in ours_team if actor["is_pet"]), None)
    theirs_pet = next((actor for actor in theirs_team if actor["is_pet"]), None)
    factors = [
        f"Team attack ratio is {ours_attack / max(0.0001, theirs_attack):.3f}x for Densetsu.",
        f"Team HP-plus-barrier ratio is {ours_hp / max(0.0001, theirs_hp):.3f}x for Densetsu.",
    ]
    if ours_pet and theirs_pet:
        factors.append(
            "Pet attack ratio is "
            f"{ours_pet['attack'] / max(0.0001, theirs_pet['attack']):.3f}x for Densetsu."
        )
    elif ours_pet:
        factors.append("Only Densetsu has an active raidbattle pet.")
    elif theirs_pet:
        factors.append("Only the opponent has an active raidbattle pet.")

    allowed = conservative >= required
    return {
        "available": True,
        "acceptance_allowed": allowed,
        "estimated_win_probability_percent": round(estimate * 100, 1),
        "conservative_win_probability_percent": round(conservative * 100, 1),
        "minimum_required_win_probability_percent": round(required * 100, 1),
        "wager_percent_of_bankroll": round(exposure * 100, 2),
        "simulations": simulations,
        "combatants_assessed": {
            "densetsu": {
                "player": True,
                "pet": ours_pet is not None,
                "pet_skill_effects": ours_pet["pet_skill_count"] if ours_pet else 0,
            },
            "opponent": {
                "player": True,
                "pet": theirs_pet is not None,
                "pet_skill_effects": theirs_pet["pet_skill_count"] if theirs_pet else 0,
            },
        },
        "decisive_factors": factors,
        "method": (
            "Deterministic Monte Carlo using both players' battle-start attack, defense, "
            "HP, luck, elements, key class effects, and both pets' stats and common skill "
            "effects. It mirrors raid target weights, turn order, armor, minimum damage, "
            "tripping, lifesteal, reflection, death-cheat, and Team A/Team B end rules."
        ),
        "decision_rule": (
            "Accept is exposed only when the conservative win estimate meets the "
            "bankroll-adjusted minimum."
        ),
    }

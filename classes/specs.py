"""
Class specialization catalog.

Each of the 13 class lines forks into two specs after the line reaches the
level, evolution, and Class Mastery gates: one passive (always on) and one
signature effect resolved by the battle engines. This module is import-safe
for both cogs and the battle engine and has no Discord dependency.

Design doc: docs/class_specializations.md

Effect values scale with class grade G (1-7): value = base + per_grade * G.
`engines` tags which battle systems can honor the effect:
  - "modern": cogs/battles core engine (tower, trials, GM battles)
  - "simple": legacy loops (ice dragon, raids) with a flat damage model
"""
from __future__ import annotations

from classes.class_mastery import MASTERY_UNLOCK_LEVEL


# Kept as a compatibility alias for callers that already import this name.
SPEC_UNLOCK_LEVEL = MASTERY_UNLOCK_LEVEL
RESPEC_COST = 250_000

SPECS: dict[str, dict] = {
    # --- Tank ---------------------------------------------------------------
    "juggernaut": {
        "name": "Juggernaut", "line": "Tank", "kind": "aggressive", "emoji": "💢",
        "passive": "Retaliation",
        "description": "Reflect {value}% of damage taken back at the attacker. Your reflection plate has durability equal to {value}% of max HP each battle.",
        "effect": {"type": "reflect_pct", "base": 4, "per_grade": 1},
        "engines": ["modern", "simple"],
    },
    "bulwark": {
        "name": "Bulwark", "line": "Tank", "kind": "defensive", "emoji": "🛡️",
        "passive": "Aegis",
        "description": "At battle start, shield yourself and allies for {value}% of max HP.",
        "effect": {"type": "start_shield_pct", "base": 3, "per_grade": 1},
        "engines": ["modern"],
    },
    # --- Warrior ------------------------------------------------------------
    "warlord": {
        "name": "Warlord", "line": "Warrior", "kind": "aggressive", "emoji": "⚔️",
        "passive": "Relentless Assault",
        "description": (
            "Successful attacks have a {value}% chance to gain 2 Momentum instead of 1. "
            "Crushing Blow gains another {finisher_value}% damage, and a Crushing Blow kill "
            "carries 2 Momentum into the next target."
        ),
        "effect": {
            "type": "warrior_relentless_pct", "base": 15, "per_grade": 3,
            "finisher_base": 6, "finisher_per_grade": 2,
        },
        "engines": ["modern", "simple"],
    },
    "sentinel": {
        "name": "Sentinel", "line": "Warrior", "kind": "defensive", "emoji": "🪖",
        "passive": "Combat Discipline",
        "description": (
            "Take {value}% less damage from all sources, plus {momentum_value}% per Momentum. "
            "After Crushing Blow spends Momentum, that stack-based protection braces the next hit."
        ),
        "effect": {
            "type": "warrior_discipline_pct", "base": 2, "per_grade": 0.8,
            "momentum_base": 0.5, "momentum_per_grade": 0.2,
        },
        "engines": ["modern", "simple"],
    },
    # --- Thief --------------------------------------------------------------
    "nightblade": {
        "name": "Nightblade", "line": "Thief", "kind": "aggressive", "emoji": "🗡️",
        "passive": "Ambush",
        "description": "Your first strike each battle crits for {value}% extra damage.",
        "effect": {"type": "first_strike_bonus_pct", "base": 20, "per_grade": 3},
        "engines": ["modern", "simple"],
    },
    "trickster": {
        "name": "Trickster", "line": "Thief", "kind": "defensive", "emoji": "💨",
        "passive": "Smoke Step",
        "description": "{value}% chance to dodge attacks entirely.",
        "effect": {"type": "dodge_pct", "base": 4, "per_grade": 1},
        "engines": ["modern", "simple"],
    },
    # --- Mage ---------------------------------------------------------------
    # DB key stays "stormcaller" for backward-compat with existing picks; players
    # see and type "Overload" (the spec cog name-matches on the display name).
    "stormcaller": {
        "name": "Overload", "line": "Mage", "kind": "aggressive", "emoji": "⚡",
        "passive": "Arcane Surge",
        "description": (
            "Each spell hit builds an Arcane charge — **+{value}% spell damage per "
            "stack** (max {max_stacks}). Your Fireball consumes every charge, "
            "detonating for **+{detonate_per_stack}% per stack**, then resets."
        ),
        "effect": {
            "type": "arcane_ramp_pct", "base": 3, "per_grade": 0.5,
            "max_stacks": 5, "detonate_per_stack": 20,
        },
        "engines": ["modern", "simple"],
    },
    # DB key stays "runeweaver" for backward-compat with existing picks; players
    # see and type "Bloodweaver" (the spec cog name-matches on the display name).
    "runeweaver": {
        "name": "Bloodweaver", "line": "Mage", "kind": "defensive", "emoji": "🩸",
        "passive": "Blood Pact",
        "description": (
            "Bank **{bank_pct}% of the damage you take** into a Blood Reservoir "
            "(max **{value}% of your max HP**). Once per battle a killing blow "
            "instead leaves you at 1 HP and empties the reservoir back as healing."
        ),
        "effect": {"type": "bloodpact_reservoir_pct", "base": 20, "per_grade": 2, "bank_pct": 25},
        "engines": ["modern", "simple"],
    },
    # --- Paragon ------------------------------------------------------------
    # DB keys stay "exemplar"/"aspirant" for backward compatibility with
    # existing picks; players see and choose the new names.
    "exemplar": {
        "name": "Ascendant", "line": "Paragon", "kind": "aggressive", "emoji": "✨",
        "passive": "Perfect Form",
        "description": (
            "Adapt each hit: bosses take **+{value}%** damage, armored enemies lose "
            "**{value}% armor value**, wounded enemies take **+{execute_value}%** damage, "
            "and ordinary foes take half value."
        ),
        "effect": {"type": "perfect_form_pct", "base": 4, "per_grade": 2, "execute_bonus": 6, "threshold": 0.25},
        "engines": ["modern", "simple"],
    },
    "aspirant": {
        "name": "Vanguard", "line": "Paragon", "kind": "defensive", "emoji": "🛡️",
        "passive": "Unbroken Will",
        "description": (
            "Once per battle below 40% HP, gain a **{shield_value}% max HP shield** "
            "and **+{value}% damage** for {duration} hits."
        ),
        "effect": {"type": "unbroken_will_pct", "base": 8, "per_grade": 1.7, "shield_bonus": 4, "threshold": 0.40, "duration": 3},
        "engines": ["modern", "simple"],
    },
    # --- Paladin ------------------------------------------------------------
    "inquisitor": {
        "name": "Inquisitor", "line": "Paladin", "kind": "aggressive", "emoji": "⚖️",
        "passive": "Judgement",
        "description": "Deal {value}% more damage to enemies above 70% HP.",
        "effect": {"type": "high_hp_bonus_pct", "base": 8, "per_grade": 2, "threshold": 0.70},
        "engines": ["modern", "simple"],
    },
    "lightwarden": {
        "name": "Lightwarden", "line": "Paladin", "kind": "defensive", "emoji": "🕯️",
        "passive": "Sanctuary",
        "description": "In party content, allies take {value}% less damage.",
        "effect": {"type": "party_damage_reduction_pct", "base": 2, "per_grade": 0.7},
        "engines": ["modern", "simple"],
    },
    # --- Ranger -------------------------------------------------------------
    "sharpshooter": {
        "name": "Sharpshooter", "line": "Ranger", "kind": "aggressive", "emoji": "🎯",
        "passive": "Deadeye",
        "description": "{value}% chance to ignore ALL enemy armor.",
        "effect": {"type": "armor_ignore_chance_pct", "base": 6, "per_grade": 1},
        "engines": ["modern", "simple"],
    },
    "beastcaller": {
        "name": "Beastcaller", "line": "Ranger", "kind": "defensive", "emoji": "🐺",
        "passive": "Pack Bond",
        "description": "Your pet gains {value}% to all stats.",
        "effect": {"type": "pet_stat_pct", "base": 5, "per_grade": 2},
        "engines": ["modern", "simple"],
    },
    # --- Raider -------------------------------------------------------------
    "dragonheart": {
        "name": "Dragonheart", "line": "Raider", "kind": "aggressive", "emoji": "🐉",
        "passive": "Slayer",
        "description": "Deal {value}% more damage to bosses — raid bosses, the Ice Dragon, and Battle Tower floor/Boss Rush bosses.",
        "effect": {"type": "boss_damage_pct", "base": 7, "per_grade": 3},
        "engines": ["modern", "simple"],
    },
    "freebooter": {
        "name": "Freebooter", "line": "Raider", "kind": "utility", "emoji": "💰",
        "passive": "Plunder",
        "description": "Earn {value}% more money from victories.",
        "effect": {"type": "money_bonus_pct", "base": 4, "per_grade": 2},
        "engines": ["modern", "simple"],
    },
    # --- Ritualist ----------------------------------------------------------
    # DB keys stay "hexweaver"/"soothsayer" for backward compatibility with
    # existing picks; players see and choose the new names.
    "hexweaver": {
        "name": "Maleficar", "line": "Ritualist", "kind": "aggressive", "emoji": "🔮",
        "passive": "Doom Circle",
        "description": (
            "Every {threshold} hits detonate Doom Sigils for **{value}% damage** "
            "plus up to **{hp_value}% enemy max HP**."
        ),
        "effect": {
            "type": "doom_circle_pct", "base": 30, "per_grade": 5,
            "threshold": 3, "hp_base": 0.4, "hp_per_grade": 0.1,
            "hp_damage_cap": 0.75,
        },
        "engines": ["modern", "simple"],
    },
    "soothsayer": {
        "name": "Soulkeeper", "line": "Ritualist", "kind": "defensive", "emoji": "🕯️",
        "passive": "Sacred Offering",
        "description": (
            "Store **{value}% of damage taken** by you or your pet. At "
            "**{release_pct}% max HP** stored, release it as healing and shields."
        ),
        "effect": {"type": "soulkeeper_store_pct", "base": 10, "per_grade": 2, "release_pct": 20},
        "engines": ["modern", "simple"],
    },
    # --- Reaper -------------------------------------------------------------
    "harbinger": {
        "name": "Harbinger", "line": "Reaper", "kind": "aggressive", "emoji": "☠️",
        "passive": "Death's Verdict",
        "description": (
            "The first strike against each enemy below {threshold_pct}% HP invokes "
            "Death's Verdict for **{value}% weapon damage** plus up to "
            "**{hp_value}% enemy max HP**. Boss vitality damage is capped."
        ),
        "effect": {
            "type": "death_verdict_pct", "base": 30, "per_grade": 10,
            "threshold": 0.20, "hp_base": 0.4, "hp_per_grade": 0.15,
            "hp_damage_cap": 1.0,
        },
        "engines": ["modern", "simple"],
    },
    "soulbinder": {
        "name": "Soulbinder", "line": "Reaper", "kind": "defensive", "emoji": "🌑",
        "passive": "Dominion of Souls",
        "description": (
            "Heal for **{value}% of your weapon damage** on every hit. Overhealing "
            "becomes Soul Ward, absorbing up to **{ward_value}% max HP**."
        ),
        "effect": {
            "type": "soul_ward_lifesteal_pct", "base": 6, "per_grade": 1.7,
            "ward_base": 18, "ward_per_grade": 2.4,
        },
        "engines": ["modern", "simple"],
    },
    # --- SantasHelper ---------------------------------------------------------
    "krampus": {
        "name": "Krampus", "line": "SantasHelper", "kind": "aggressive", "emoji": "😈",
        "passive": "Chains of the Naughty",
        "description": (
            "Each hit adds a Naughty stack. At {stacks} stacks, Krampus deals "
            "**{value}% weapon damage**, weakens the enemy by **{reduction_value}%** "
            "for {duration} attacks, and guarantees a Crimson Present."
        ),
        "effect": {
            "type": "naughty_chain_pct", "base": 20, "per_grade": 5.7,
            "stacks": 3, "duration": 2,
            "reduction_base": 5, "reduction_per_grade": 1,
        },
        "engines": ["modern", "simple"],
    },
    "winterlight": {
        "name": "Winterlight", "line": "SantasHelper", "kind": "defensive", "emoji": "🕊️",
        "passive": "Christmas Miracle",
        "description": (
            "Once per battle, the first ally who would fall instead returns at "
            "**{value}% HP** with a **{miracle_shield_value}% max HP shield**. "
            "Your presents also favor wounded allies and stronger protection."
        ),
        "effect": {
            "type": "christmas_miracle_pct", "base": 7, "per_grade": 1.15,
            "shield_base": 3, "shield_per_grade": 1,
            "gift_multiplier": 1.25,
        },
        "engines": ["modern", "simple"],
    },
    # --- Bard ---------------------------------------------------------------
    "warchanter": {
        "name": "Warchanter", "line": "Bard", "kind": "aggressive", "emoji": "🎺",
        "passive": "Battle Hymn",
        "description": "At battle start, your party gains {value}% damage.",
        "effect": {"type": "party_damage_pct", "base": 2, "per_grade": 0.8},
        "engines": ["modern"],
    },
    "lifesinger": {
        "name": "Lifesinger", "line": "Bard", "kind": "defensive", "emoji": "🎶",
        "passive": "Restorative Chorus",
        "description": "Your party heals {value}% max HP at the end of each round.",
        "effect": {"type": "party_round_heal_pct", "base": 1, "per_grade": 0.6},
        "engines": ["modern"],
    },
    # --- Beastmaster --------------------------------------------------------
    "packleader": {
        "name": "Packleader", "line": "Beastmaster", "kind": "aggressive", "emoji": "🐾",
        "passive": "Alpha's Command",
        "description": "Your pet gains {value}% to all stats.",
        "effect": {"type": "pet_stat_pct", "base": 1, "per_grade": 1},
        "engines": ["modern", "simple"],
    },
    "denfather": {
        "name": "Denfather", "line": "Beastmaster", "kind": "defensive", "emoji": "🏕️",
        "passive": "Den's Bulwark",
        "description": "In party content, allies take {value}% less damage.",
        "effect": {"type": "party_damage_reduction_pct", "base": 2, "per_grade": 0.7},
        "engines": ["modern", "simple"],
    },
}


def spec_value(spec: dict, grade: int) -> float:
    """Scaled effect value for a class grade (1-7)."""
    effect = spec["effect"]
    return round(effect["base"] + effect["per_grade"] * grade, 1)


def specs_for_line(line: str) -> dict[str, dict]:
    """The two specs available to a class line, keyed by spec key."""
    return {key: spec for key, spec in SPECS.items() if spec["line"] == line}


KIND_LABELS = {
    "aggressive": "offense",
    "defensive": "defense",
    "utility": "utility",
}


def spec_kind_label(key: str) -> str:
    return KIND_LABELS.get(SPECS[key].get("kind", ""), "")


def describe_spec(key: str, grade: int) -> str:
    """Two-line spec card with the grade-scaled value filled in.

    Extra effect params (max_stacks, detonate_per_stack, ...) are exposed to the
    description template too, so multi-number cards format cleanly.
    """
    spec = SPECS[key]
    kind = spec_kind_label(key)
    header = f"**{spec['name']}** — {spec['passive']}" + (f" · *{kind}*" if kind else "")
    fmt = {k: v for k, v in spec["effect"].items() if k not in ("type", "base", "per_grade")}
    value = spec_value(spec, grade)
    fmt["value"] = value
    if "execute_bonus" in spec["effect"]:
        fmt["execute_value"] = round(value + spec["effect"]["execute_bonus"], 1)
    if "shield_bonus" in spec["effect"]:
        fmt["shield_value"] = round(value + spec["effect"]["shield_bonus"], 1)
    if "hp_base" in spec["effect"] and "hp_per_grade" in spec["effect"]:
        fmt["hp_value"] = round(
            spec["effect"]["hp_base"] + spec["effect"]["hp_per_grade"] * grade,
            1,
        )
    if "ward_base" in spec["effect"] and "ward_per_grade" in spec["effect"]:
        fmt["ward_value"] = round(
            spec["effect"]["ward_base"] + spec["effect"]["ward_per_grade"] * grade,
            1,
        )
    if "reduction_base" in spec["effect"] and "reduction_per_grade" in spec["effect"]:
        fmt["reduction_value"] = round(
            spec["effect"]["reduction_base"] + spec["effect"]["reduction_per_grade"] * grade,
            1,
        )
    if "shield_base" in spec["effect"] and "shield_per_grade" in spec["effect"]:
        fmt["miracle_shield_value"] = round(
            spec["effect"]["shield_base"] + spec["effect"]["shield_per_grade"] * grade,
            1,
        )
    if "finisher_base" in spec["effect"] and "finisher_per_grade" in spec["effect"]:
        fmt["finisher_value"] = round(
            spec["effect"]["finisher_base"] + spec["effect"]["finisher_per_grade"] * grade,
            1,
        )
    if "momentum_base" in spec["effect"] and "momentum_per_grade" in spec["effect"]:
        fmt["momentum_value"] = round(
            spec["effect"]["momentum_base"] + spec["effect"]["momentum_per_grade"] * grade,
            1,
        )
    if "threshold" in spec["effect"]:
        fmt["threshold_pct"] = round(spec["effect"]["threshold"] * 100, 1)
    return f"{header}\n{spec['description'].format(**fmt)}"

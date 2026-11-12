"""Static equipment definitions.

The chest budget is the approved baseline for one cuirass. Helm, greaves,
and sabatons share one extra budget of that same size.
"""
from __future__ import annotations

from decimal import Decimal

DEV_DATABASE = "FableDev"

# Worn slots. Helm, cuirass, greaves, and sabatons can be equipped.
# Bracers and the belt stay closed.
PAPER_DOLL_SLOTS = ("head", "chest", "legs", "feet")
OPEN_SLOTS = PAPER_DOLL_SLOTS
FUTURE_SLOTS = ("bracers", "belt")
ALL_SLOTS = PAPER_DOLL_SLOTS + FUTURE_SLOTS

RARITIES = ("common", "uncommon", "rare", "magic", "legendary")
ARCHETYPES = ("guardian", "slayer", "vanguard")

MAX_REFINEMENT = 7
REFINEMENT_STEP = Decimal("0.04")

# Share of the legendary quality-100 budget.
RARITY_BUDGET = {
    "common": Decimal("0.25"),
    "uncommon": Decimal("0.40"),
    "rare": Decimal("0.55"),
    "magic": Decimal("0.75"),
    "legendary": Decimal("1"),
}

# Legendary chest at quality 100 and refinement +0, before raid multipliers.
ARCHETYPE_BUDGET = {
    "guardian": {"armor": Decimal("18"), "weapon_pct": Decimal("0.03")},
    "vanguard": {"armor": Decimal("10"), "weapon_pct": Decimal("0.08")},
    "slayer": {"armor": Decimal("4"), "weapon_pct": Decimal("0.16")},
}
# Chest keeps the whole baseline. The other three open slots share one more
# baseline between them: greaves 42%, helm 34%, sabatons 24%.
SLOT_BUDGET_SHARE = {
    "chest": Decimal("1"),
    "legs": Decimal("0.42"),
    "head": Decimal("0.34"),
    "feet": Decimal("0.24"),
}
SLOT_ALIASES = {
    "head": "head",
    "helm": "head",
    "chest": "chest",
    "cuirass": "chest",
    "legs": "legs",
    "greaves": "legs",
    "feet": "feet",
    "sabaton": "feet",
    "sabatons": "feet",
}

# Affix sizes are the Phase 4 and Phase 5 baselines. One copy of each affix
# is allowed on a piece. Penetration and breakthrough are capped again when
# several pieces are worn, so later slots cannot stack without a limit.
MAX_PENETRATION = Decimal("0.55")
MAX_BREAKTHROUGH_CHANCE = Decimal("0.15")
MAX_BREAKTHROUGH_BYPASS = Decimal("0.15")
MAX_IGNORED_FRACTION = Decimal("0.70")
MAX_IGNORED_OF_ATTACK = Decimal("0.62")

MODIFIERS = {
    "weapon_amplification": {
        "name": "Weapon Amplification",
        "glow": (255, 96, 72),
        "weapon_pct": "0.04",
        "armor_pct": "0",
        "health": 0,
        "penetration": "0",
        "breakthrough_chance": "0",
        "breakthrough_bypass": "0",
    },
    "fortified": {
        "name": "Fortified",
        "glow": (96, 170, 255),
        "weapon_pct": "0",
        "armor_pct": "0.06",
        "health": 0,
        "penetration": "0",
        "breakthrough_chance": "0",
        "breakthrough_bypass": "0",
    },
    "vitality": {
        "name": "Vitality",
        "glow": (88, 214, 140),
        "weapon_pct": "0",
        "armor_pct": "0",
        "health": 75,
        "penetration": "0",
        "breakthrough_chance": "0",
        "breakthrough_bypass": "0",
    },
    "sunder": {
        "name": "Sunder",
        "glow": (214, 92, 48),
        "weapon_pct": "0",
        "armor_pct": "0",
        "health": 0,
        "penetration": "0.55",
        "breakthrough_chance": "0",
        "breakthrough_bypass": "0",
    },
    "breakthrough": {
        "name": "Breakthrough",
        "glow": (232, 184, 74),
        "weapon_pct": "0",
        "armor_pct": "0",
        "health": 0,
        "penetration": "0",
        "breakthrough_chance": "0.10",
        "breakthrough_bypass": "0.15",
    },
}
MODIFIER_LINES = {
    "guardian": ("fortified", "vitality"),
    "slayer": ("weapon_amplification", "vitality", "sunder", "breakthrough"),
    "vanguard": ("weapon_amplification", "fortified", "vitality", "breakthrough"),
}

RARITY_ADJECTIVE = {
    "common": "Rough-spun",
    "uncommon": "Sturdy",
    "rare": "Tempered",
    "magic": "Arcane",
    "legendary": "Mythic",
}

ARCHETYPE_NOUN = {
    "guardian": "Aegis",
    "slayer": "Razor",
    "vanguard": "Oath",
}

SLOT_NOUN = {
    "head": "Helm",
    "chest": "Cuirass",
    "legs": "Greaves",
    "feet": "Sabatons",
    "bracers": "Bracers",
    "belt": "Belt",
}

# Provisional crate rates. These are the approved simulation baseline.
ELIGIBLE_CRATE_RARITIES = ("common", "uncommon", "rare", "magic", "legendary")
EXCLUDED_CRATE_RARITIES = ("divine", "fortune", "mystery", "materials")
GEAR_CHANCE = {
    "common": 0.08,
    "uncommon": 0.12,
    "rare": 0.16,
    "magic": 0.22,
    "legendary": 0.30,
}
FULLY_ROLLED_CHANCE = 0.004
# Armory rolls per rarity in any 24 hours. Normal income stays far below these;
# a large stockpile still opens, but only this many crates a day also roll armor.
ARMORY_DAILY_ROLLS = {
    "common": 60,
    "uncommon": 30,
    "rare": 20,
    "magic": 8,
    "legendary": 4,
}
# Thorne's Anvil. Every attempt pays its materials and gold; a failure changes
# nothing else. Pity is the number of failures in a row after which the next
# attempt succeeds.
#
# Refining raises quality by 1. (highest quality in band, rough, worked,
# relic, gold, success chance, pity)
REFINE_QUALITY_BANDS = (
    (69, 4, 0, 0, 2_000, 1.00, 0),
    (84, 6, 1, 0, 5_000, 0.85, 2),
    (94, 8, 2, 0, 10_000, 0.65, 3),
    (99, 10, 3, 1, 25_000, 0.50, 3),
)
# Tempering adds a star, +1 to +7. Materials are TEMPER_STAR_COSTS in economy.py.
TEMPER_STAR_CHANCE = {1: 0.90, 2: 0.80, 3: 0.70, 4: 0.60, 5: 0.50, 6: 0.40, 7: 0.30}
TEMPER_STAR_PITY = {1: 1, 2: 2, 3: 2, 4: 3, 5: 3, 6: 4, 7: 5}
TEMPER_STAR_GOLD = {star: star * 60_000 for star in range(1, 8)}
# Inscribing sets one enchantment from the piece's line on a Magic or Legendary
# piece. Two enchantments only come from a fully rolled Legendary crate drop.
# (rough, worked, relic, gold, success chance, pity)
INSCRIBE_COST = (20, 12, 3, 150_000, 0.35, 3)
INSCRIBE_RARITIES = ("magic", "legendary")
# Garron's trade: this many of one line's material buys one of another line's
# material of the same tier.
TRADE_RATIO = 3
# Party dragon kills pay smithing goods by dragon level. The line follows the
# armor the player wears most. (highest level, stage, rough low, rough high,
# worked chance, worked amount, relic chance)
DRAGON_MATERIAL_TIERS = (
    (5, "Frostbite Wyrm", 1, 2, 0.0, 0, 0.0),
    (10, "Corrupted Ice Dragon", 2, 3, 0.0, 0, 0.0),
    (15, "Permafrost", 2, 3, 0.20, 1, 0.0),
    (20, "Absolute Zero", 3, 3, 1.0, 1, 0.0),
    (34, "Void Tyrant", 3, 3, 1.0, 1, 0.15),
    (None, "The Abyssal Maw", 4, 4, 1.0, 2, 0.35),
)
QUALITY_MODE = {
    "common": 45,
    "uncommon": 50,
    "rare": 54,
    "magic": 58,
    "legendary": 62,
}

# Nine smithing goods: one rough, worked, and relic material for each armor line.
# Dots match $amulet resources. Rough is common, worked is rare, relic is legendary.
MATERIALS = {
    "bog_iron": "Bog Iron",
    "wardsteel": "Wardsteel",
    "aegisheart": "Aegisheart",
    "cinder_ore": "Cinder Ore",
    "razorsteel": "Razorsteel",
    "wyrmglass": "Wyrmglass",
    "river_bronze": "River Bronze",
    "oathsteel": "Oathsteel",
    "sunstone": "Sunstone",
}
MATERIAL_LINES = {
    "guardian": ("bog_iron", "wardsteel", "aegisheart"),
    "slayer": ("cinder_ore", "razorsteel", "wyrmglass"),
    "vanguard": ("river_bronze", "oathsteel", "sunstone"),
}
MATERIAL_TIERS = {
    "bog_iron": "rough",
    "cinder_ore": "rough",
    "river_bronze": "rough",
    "wardsteel": "worked",
    "razorsteel": "worked",
    "oathsteel": "worked",
    "aegisheart": "relic",
    "wyrmglass": "relic",
    "sunstone": "relic",
}
MATERIAL_RARITY = {
    "rough": "common",
    "worked": "rare",
    "relic": "legendary",
}
RARITY_DOTS = {
    "common": "⚪",
    "uncommon": "🟢",
    "rare": "🔵",
    "epic": "🟣",
    "magic": "🟣",
    "legendary": "🟡",
}
MATERIAL_ORDER = tuple(
    material_id
    for line in ("guardian", "slayer", "vanguard")
    for material_id in MATERIAL_LINES[line]
)


def material_rarity(material_id: str) -> str:
    return MATERIAL_RARITY[MATERIAL_TIERS[material_id]]


def material_dot(material_id: str) -> str:
    return RARITY_DOTS[material_rarity(material_id)]


def resolve_material(name: str) -> str | None:
    """Accept `bog_iron` or `Bog Iron`."""
    text = " ".join(str(name or "").strip().lower().split())
    if not text:
        return None
    key = text.replace(" ", "_")
    if key in MATERIALS:
        return key
    for material_id, label in MATERIALS.items():
        if label.lower() == text:
            return material_id
    return None


def material_line(material_id: str) -> str:
    for line, material_ids in MATERIAL_LINES.items():
        if material_id in material_ids:
            return line
    raise KeyError(material_id)

QUALITY_BANDS = (
    (39, "Rough"),
    (69, "Standard"),
    (84, "Fine"),
    (94, "Exceptional"),
    (100, "Masterwork"),
)


def quality_band(quality: int) -> str:
    quality = int(quality)
    for ceiling, label in QUALITY_BANDS:
        if quality <= ceiling:
            return label
    return "Masterwork"


def resolve_slot(name: str) -> str | None:
    """Accept a slot id or its piece name, such as helm or cuirass."""
    return SLOT_ALIASES.get(" ".join(str(name or "").strip().lower().split()))


def display_name(rarity: str, archetype: str, slot: str) -> str:
    return (
        f"{RARITY_ADJECTIVE[rarity]} {ARCHETYPE_NOUN[archetype]} {SLOT_NOUN[slot]}"
    )

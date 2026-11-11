"""Raid-stat calculator.

The live total in get_raidstats and battle health is:

    weapon listed stat
        × (1 + star percent + soulbound percent)
        + class fit
        + the same for the other pieces
        + race
        + class grade
    = gear

    gear × (profile multiplier + attack-or-defense points × 0.20 + raid hall × 0.10)
        + amulet
    = raid attack or raid defense

    200 + profile HP + level × 15 + health points × 200 + amulet HP
    = health

Stars multiply one weapon. The class fit is added after that percent, then the
single raid multiplier hits the whole gear total. The amulet is added on last.
Health is only addition. The health number sold beside the attack multiplier
adds +5 profile HP per purchase.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from classes.classes import Mage, Paragon
from classes.classes import from_string as class_from_string
from classes.endgame import (
    STARFORGE_MAX_STARS,
    apply_item_progression_bonus,
    soulbound_bonus_pct_for_level,
    soulbound_rank_for_level,
    starforge_bonus_pct,
)
from utils.misc import STAT_ATTACK_DEFENSE_PER_POINT, STAT_HEALTH_PER_POINT

BASE_HP = 200
HP_PER_LEVEL = 15
HP_PER_PURCHASE = 5
PAID_STEP = Decimal("0.1")
CITY_STEP = Decimal("0.1")

# (damage, armor, label). Index is what the class-fit slider stores.
FITS = (
    (Decimal(0), Decimal(0), "No class fit"),
    (Decimal(5), Decimal(0), "+5 class fit"),
    (Decimal(10), Decimal(0), "+10 class fit"),
    (Decimal(0), Decimal(7), "+7 shield fit"),
)

# Weapon type → (class lines that receive the fit, FITS index).
# Same pairs and amounts as get_damage_armor_for, and the flat is added
# after the star percent there too.
CLASS_FIT = {
    "Spear": ({"Paragon", "Beastmaster"}, 1),
    "Dagger": ({"Thief", "Bard"}, 1),
    "Knife": ({"Thief", "Bard"}, 1),
    "Sword": ({"Warrior", "Penitent"}, 1),
    "Bow": ({"Ranger"}, 2),
    "Wand": ({"Mage", "Ritualist", "Breathcaller"}, 1),
    "Axe": ({"Raider"}, 1),
    "Hammer": ({"Paladin"}, 1),
    "Scythe": ({"Reaper"}, 2),
    "Mace": ({"SantasHelper"}, 1),
    "Shield": ({"Tank"}, 3),
}

RACES = (
    ("None", Decimal(0), Decimal(0)),
    ("Human", Decimal(2), Decimal(2)),
    ("Dragonkin", Decimal(2), Decimal(2)),
    ("Dwarf", Decimal(1), Decimal(3)),
    ("Elf", Decimal(3), Decimal(1)),
    ("Orc", Decimal(0), Decimal(4)),
    ("Jikill", Decimal(4), Decimal(0)),
    ("Djinn", Decimal(5), Decimal(-1)),
    ("Shadeborn", Decimal(-1), Decimal(5)),
)
RACE_NAMES = {name for name, _, _ in RACES}

# Crafted amulet stats. Tiers match AmuletCrafting.AMULET_TYPES.
AMULET_PRESETS = {
    "balanced": {
        1: {"hp": 100, "defense": 50, "attack": 50},
        2: {"hp": 250, "defense": 150, "attack": 150},
        3: {"hp": 500, "defense": 300, "attack": 300},
        4: {"hp": 800, "defense": 500, "attack": 500},
        5: {"hp": 1200, "defense": 700, "attack": 700},
        6: {"hp": 1800, "defense": 900, "attack": 900},
        7: {"hp": 2500, "defense": 1100, "attack": 1100},
        8: {"hp": 3300, "defense": 1250, "attack": 1250},
        9: {"hp": 5000, "defense": 1400, "attack": 1400},
        10: {"hp": 7500, "defense": 1500, "attack": 1500},
    },
    "attack": {
        1: {"hp": 90, "defense": 45, "attack": 60},
        2: {"hp": 225, "defense": 135, "attack": 180},
        3: {"hp": 450, "defense": 270, "attack": 360},
        4: {"hp": 720, "defense": 450, "attack": 600},
        5: {"hp": 1080, "defense": 630, "attack": 840},
        6: {"hp": 1620, "defense": 810, "attack": 1080},
        7: {"hp": 2250, "defense": 990, "attack": 1320},
        8: {"hp": 2970, "defense": 1125, "attack": 1500},
        9: {"hp": 4500, "defense": 1260, "attack": 1680},
        10: {"hp": 6750, "defense": 1350, "attack": 1800},
    },
    "defense": {
        1: {"hp": 90, "defense": 60, "attack": 45},
        2: {"hp": 225, "defense": 180, "attack": 135},
        3: {"hp": 450, "defense": 360, "attack": 270},
        4: {"hp": 720, "defense": 600, "attack": 450},
        5: {"hp": 1080, "defense": 840, "attack": 630},
        6: {"hp": 1620, "defense": 1080, "attack": 810},
        7: {"hp": 2250, "defense": 1320, "attack": 990},
        8: {"hp": 2970, "defense": 1500, "attack": 1125},
        9: {"hp": 4500, "defense": 1680, "attack": 1260},
        10: {"hp": 6750, "defense": 1800, "attack": 1350},
    },
    "health": {
        1: {"hp": 120, "defense": 45, "attack": 45},
        2: {"hp": 300, "defense": 135, "attack": 135},
        3: {"hp": 600, "defense": 270, "attack": 270},
        4: {"hp": 960, "defense": 450, "attack": 450},
        5: {"hp": 1440, "defense": 630, "attack": 630},
        6: {"hp": 2160, "defense": 810, "attack": 810},
        7: {"hp": 3000, "defense": 990, "attack": 990},
        8: {"hp": 3960, "defense": 1125, "attack": 1125},
        9: {"hp": 6000, "defense": 1260, "attack": 1260},
        10: {"hp": 9000, "defense": 1350, "attack": 1350},
    },
}
PRESET_KINDS = ("attack", "defense", "health", "balanced")
PRESET_TIERS = (1, 3, 5, 7, 10)


def D(value) -> Decimal:
    if isinstance(value, Decimal):
        return value
    if value is None or value is False:
        return Decimal(0)
    return Decimal(str(value))


def clamp(value: Decimal, low: Decimal, high: Decimal) -> Decimal:
    if value < low:
        return low
    if value > high:
        return high
    return value


def fmt(number) -> str:
    try:
        value = D(number)
        if not value.is_finite():
            return "0"
        quantized = value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError, ArithmeticError):
        return "0"
    text = f"{quantized:,.2f}"
    if text.endswith(".00"):
        return text[:-3]
    return text


def fmt_mult(number) -> str:
    return f"{D(number).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP):.2f}"


def fmt_pct(number) -> str:
    percent = (D(number) * 100).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
    if percent == percent.to_integral_value():
        return f"{int(percent)}%"
    return f"{percent}%"


def signed(number) -> str:
    number = D(number)
    if number > 0:
        return f"+{fmt(number)}"
    return fmt(number)


def profile_round(number) -> int:
    return int(round(float(number)))


def whole(number) -> str:
    return f"{profile_round(number):,}"


def clean(text, limit: int = 32, fallback: str = "") -> str:
    kept = []
    for char in str(text or ""):
        if char in "*_`@\\~|<>":
            kept.append(" ")
        elif char.isspace():
            kept.append(" ")
        else:
            kept.append(char)
    squashed = " ".join("".join(kept).split())
    return squashed[:limit] or fallback


def bar(value, low, high, width: int = 18) -> str:
    value, low, high = D(value), D(low), D(high)
    if high <= low:
        filled = width
    else:
        ratio = (value - low) / (high - low)
        filled = int((ratio * width).to_integral_value(rounding=ROUND_HALF_UP))
    filled = max(0, min(width, filled))
    return "█" * filled + "░" * (width - filled)


@dataclass(frozen=True)
class Field:
    key: str
    label: str
    page: str
    kind: str
    minimum: Decimal
    maximum: Decimal
    steps: tuple
    bar_cap: Decimal
    blurb: str


def _field(key, label, page, kind, low, high, steps, bar_cap, blurb) -> Field:
    return Field(
        key, label, page, kind, D(low), D(high),
        tuple(D(step) for step in steps), D(bar_cap), blurb,
    )


_DAMAGE = (
    "Listed damage on this weapon, before stars. The attack multiplier is applied "
    "after the star percent and the class fit."
)
_ARMOR = (
    "Listed armor on this weapon, before stars. The defense multiplier is applied "
    "after the star percent and the shield fit."
)
_STARS = "Each star adds 4% to this weapon's listed damage and armor. The class fit is added after that percent."
_SOUL = "Soulbound percent is added to the star percent. That total then multiplies this weapon."
_FIT = (
    "A matching class adds flat damage, or flat armor for a tank shield. "
    "The raid multiplier then scales that flat amount."
)


FIELD_LIST = (
    _field("right_damage", "Right weapon damage", "weapons", "number", 0, 100000, (1, 10, 100, 1000), 200, _DAMAGE),
    _field("right_armor", "Right weapon armor", "weapons", "number", 0, 100000, (1, 10, 100, 1000), 200, _ARMOR),
    _field("right_stars", "Right weapon stars", "weapons", "int", 0, STARFORGE_MAX_STARS, (1, 1, 1, 1), STARFORGE_MAX_STARS, _STARS),
    _field("right_soul", "Right weapon soulbound", "weapons", "int", 0, 500, (1, 5, 10, 20), 50, _SOUL),
    _field("right_fit", "Right class fit", "weapons", "fit", 0, 3, (1, 1, 1, 1), 3, _FIT),
    _field("left_damage", "Left weapon damage", "weapons", "number", 0, 100000, (1, 10, 100, 1000), 200, _DAMAGE),
    _field("left_armor", "Left weapon armor", "weapons", "number", 0, 100000, (1, 10, 100, 1000), 200, _ARMOR),
    _field("left_stars", "Left weapon stars", "weapons", "int", 0, STARFORGE_MAX_STARS, (1, 1, 1, 1), STARFORGE_MAX_STARS, _STARS),
    _field("left_soul", "Left weapon soulbound", "weapons", "int", 0, 500, (1, 5, 10, 20), 50, _SOUL),
    _field("left_fit", "Left class fit", "weapons", "fit", 0, 3, (1, 1, 1, 1), 3, _FIT),
    _field(
        "other_damage", "Other gear damage", "weapons", "number", 0, 100000, (1, 10, 100, 1000), 200,
        "Finished damage from every equipped piece outside the two hands, stars and class fit included. The attack multiplier still applies. Amulets stay on the amulet slider.",
    ),
    _field(
        "other_armor", "Other gear armor", "weapons", "number", 0, 100000, (1, 10, 100, 1000), 200,
        "Finished armor from the other pieces. The defense multiplier applies to it.",
    ),
    _field(
        "race", "Race", "hero", "race", 0, len(RACES) - 1, (1, 1, 2, 3), len(RACES) - 1,
        "A flat add onto gear, so the multiplier scales it. Djinn and Shadeborn include a negative.",
    ),
    _field(
        "class_damage", "Class grade attack", "hero", "int", 0, 30, (1, 1, 1, 1), 6,
        "Mage and Paragon grades add this much attack onto gear, so the multiplier scales it.",
    ),
    _field(
        "class_armor", "Class grade armor", "hero", "int", 0, 30, (1, 1, 1, 1), 6,
        "Paragon grade adds this much armor onto gear.",
    ),
    _field(
        "profile_atk", "Profile attack multiplier", "hero", "mult", 0, 500, ("0.01", "0.10", "1", "5"), 3,
        "The paid raid attack upgrade. Each purchase adds 0.10 to this multiplier.",
    ),
    _field(
        "profile_def", "Profile defense multiplier", "hero", "mult", 0, 500, ("0.01", "0.10", "1", "5"), 3,
        "The paid raid defense upgrade. Each purchase adds 0.10 to this multiplier.",
    ),
    _field(
        "stat_atk", "Attack points", "hero", "int", 0, 5000, (1, 5, 10, 25), 40,
        "Each attack point adds 0.20 to the attack multiplier.",
    ),
    _field(
        "stat_def", "Defense points", "hero", "int", 0, 5000, (1, 5, 10, 25), 40,
        "Each defense point adds 0.20 to the defense multiplier.",
    ),
    _field(
        "stat_hp", "Health points", "hero", "int", 0, 5000, (1, 5, 10, 25), 40,
        "Each health point adds 200 health.",
    ),
    _field(
        "city", "Raid hall level", "hero", "int", 0, 100, (1, 1, 5, 10), 10,
        "Each alliance raid hall level adds 0.10 to both multipliers.",
    ),
    _field("level", "Level", "hero", "int", 1, 500, (1, 5, 10, 25), 100, "Each level adds 15 health."),
    _field(
        "profile_hp", "Profile HP", "hero", "number", 0, 1000000, (5, 50, 200, 1000), 2000,
        "Flat health on the profile. One purchased health upgrade adds 5 here.",
    ),
    _field(
        "amulet_atk", "Amulet attack", "hero", "number", 0, 100000, (1, 10, 50, 100), 1800,
        "Added onto raid attack after the multiplier.",
    ),
    _field(
        "amulet_def", "Amulet defense", "hero", "number", 0, 100000, (1, 10, 50, 100), 1800,
        "Added onto raid defense after the multiplier.",
    ),
    _field(
        "amulet_hp", "Amulet HP", "hero", "number", 0, 100000, (1, 10, 50, 100), 9000,
        "Added onto health with the other flat health.",
    ),
)
FIELDS = {field.key: field for field in FIELD_LIST}
FIELD_KEYS = {
    "weapons": [field.key for field in FIELD_LIST if field.page == "weapons"],
    "hero": [field.key for field in FIELD_LIST if field.page == "hero"],
}


@dataclass
class Sheet:
    hero_name: str = "Example"
    origin: str = "example"
    right_name: str = "Empty"
    right_damage: Decimal = Decimal(0)
    right_armor: Decimal = Decimal(0)
    right_stars: int = 0
    right_soul: int = 0
    right_fit: int = 0
    right_two_handed: bool = False
    left_name: str = "Empty"
    left_damage: Decimal = Decimal(0)
    left_armor: Decimal = Decimal(0)
    left_stars: int = 0
    left_soul: int = 0
    left_fit: int = 0
    other_damage: Decimal = Decimal(0)
    other_armor: Decimal = Decimal(0)
    race: str = "None"
    class_damage: int = 0
    class_armor: int = 0
    profile_atk: Decimal = Decimal(1)
    profile_def: Decimal = Decimal(1)
    stat_atk: int = 0
    stat_def: int = 0
    stat_hp: int = 0
    city: int = 0
    level: int = 1
    profile_hp: Decimal = Decimal(0)
    amulet_atk: Decimal = Decimal(0)
    amulet_def: Decimal = Decimal(0)
    amulet_hp: Decimal = Decimal(0)


@dataclass(frozen=True)
class Result:
    right_damage: Decimal
    right_armor: Decimal
    right_pct: Decimal
    left_damage: Decimal
    left_armor: Decimal
    left_pct: Decimal
    gear_attack: Decimal
    gear_defense: Decimal
    profile_attack: Decimal
    profile_defense: Decimal
    point_attack: Decimal
    point_defense: Decimal
    city_bonus: Decimal
    attack_multiplier: Decimal
    defense_multiplier: Decimal
    multiplied_attack: Decimal
    multiplied_defense: Decimal
    amulet_attack: Decimal
    amulet_defense: Decimal
    amulet_hp: Decimal
    raid_attack: Decimal
    raid_defense: Decimal
    health: Decimal
    profile_hp: Decimal
    level_hp: Decimal
    stat_hp_bonus: Decimal


def example_sheet() -> Sheet:
    """A small build where each kind of bonus is visible."""
    sheet = Sheet(
        hero_name="Example",
        origin="example",
        right_name="Longsword",
        right_damage=Decimal(80),
        right_armor=Decimal(10),
        right_stars=2,
        right_fit=1,
        left_name="Shield",
        left_armor=Decimal(40),
        left_fit=3,
        other_damage=Decimal(15),
        other_armor=Decimal(25),
        race="Elf",
        stat_atk=5,
        stat_def=5,
        stat_hp=2,
        city=1,
        level=20,
        profile_hp=Decimal(100),
        amulet_atk=Decimal(360),
        amulet_def=Decimal(270),
        amulet_hp=Decimal(450),
    )
    return sheet


def race_bonus(name: str) -> tuple[Decimal, Decimal]:
    for race, damage, armor in RACES:
        if race == name:
            return damage, armor
    return Decimal(0), Decimal(0)


def fit_for(item_type, lines: set[str]) -> int:
    spec = CLASS_FIT.get(str(item_type or ""))
    if not spec:
        return 0
    needed, index = spec
    if lines & needed:
        return index
    return 0


def class_grades(classes) -> tuple[int, int, set[str]]:
    """Mage grade adds attack. Paragon grade adds attack and armor. Returns the lines too."""
    damage = 0
    armor = 0
    lines: set[str] = set()
    for name in classes or []:
        obj = class_from_string(str(name))
        if obj is None:
            continue
        line = obj.get_class_line()
        lines.add(line.__name__)
        grade = obj.class_grade()
        if line is Mage:
            damage += grade
        elif line is Paragon:
            damage += grade
            armor += grade
    return damage, armor, lines


def _contribute(raw_damage, raw_armor, stars, soul, fit):
    progressed_damage, progressed_armor, pct = apply_item_progression_bonus(
        raw_damage, raw_armor, stars=int(stars or 0), soulbound_level=int(soul or 0),
    )
    fit_damage, fit_armor, _label = FITS[int(fit)]
    return progressed_damage + fit_damage, progressed_armor + fit_armor, pct


def compute(sheet: Sheet) -> Result:
    right_damage, right_armor, right_pct = _contribute(
        sheet.right_damage, sheet.right_armor, sheet.right_stars, sheet.right_soul, sheet.right_fit,
    )
    left_damage, left_armor, left_pct = _contribute(
        sheet.left_damage, sheet.left_armor, sheet.left_stars, sheet.left_soul, sheet.left_fit,
    )
    race_damage, race_armor = race_bonus(sheet.race)
    gear_attack = right_damage + left_damage + D(sheet.other_damage) + race_damage + D(sheet.class_damage)
    gear_defense = right_armor + left_armor + D(sheet.other_armor) + race_armor + D(sheet.class_armor)
    point_attack = D(sheet.stat_atk) * STAT_ATTACK_DEFENSE_PER_POINT
    point_defense = D(sheet.stat_def) * STAT_ATTACK_DEFENSE_PER_POINT
    city_bonus = D(sheet.city) * CITY_STEP
    attack_multiplier = D(sheet.profile_atk) + point_attack + city_bonus
    defense_multiplier = D(sheet.profile_def) + point_defense + city_bonus
    multiplied_attack = gear_attack * attack_multiplier
    multiplied_defense = gear_defense * defense_multiplier
    amulet_attack = D(sheet.amulet_atk)
    amulet_defense = D(sheet.amulet_def)
    amulet_hp = D(sheet.amulet_hp)
    level_hp = D(sheet.level) * HP_PER_LEVEL
    stat_hp_bonus = D(sheet.stat_hp) * D(STAT_HEALTH_PER_POINT)
    profile_hp = D(sheet.profile_hp)
    health = D(BASE_HP) + profile_hp + level_hp + stat_hp_bonus + amulet_hp
    return Result(
        right_damage=right_damage,
        right_armor=right_armor,
        right_pct=right_pct,
        left_damage=left_damage,
        left_armor=left_armor,
        left_pct=left_pct,
        gear_attack=gear_attack,
        gear_defense=gear_defense,
        profile_attack=D(sheet.profile_atk),
        profile_defense=D(sheet.profile_def),
        point_attack=point_attack,
        point_defense=point_defense,
        city_bonus=city_bonus,
        attack_multiplier=attack_multiplier,
        defense_multiplier=defense_multiplier,
        multiplied_attack=multiplied_attack,
        multiplied_defense=multiplied_defense,
        amulet_attack=amulet_attack,
        amulet_defense=amulet_defense,
        amulet_hp=amulet_hp,
        raid_attack=multiplied_attack + amulet_attack,
        raid_defense=multiplied_defense + amulet_defense,
        health=health,
        profile_hp=profile_hp,
        level_hp=level_hp,
        stat_hp_bonus=stat_hp_bonus,
    )


def _item_value(item, key, default=None):
    try:
        value = item[key]
    except (KeyError, IndexError, TypeError):
        return default
    return default if value is None else value


def _hand_from_item(item, lines: set[str], two_handed: bool) -> dict:
    stars = max(0, min(STARFORGE_MAX_STARS, int(D(_item_value(item, "stars", 0)))))
    soul = max(0, int(D(_item_value(item, "soul", 0))))
    raw_damage = D(_item_value(item, "damage", 0))
    raw_armor = D(_item_value(item, "armor", 0))
    fit = fit_for(_item_value(item, "type", ""), lines)
    finished_damage, finished_armor, _pct = _contribute(raw_damage, raw_armor, stars, soul, fit)
    name = clean(_item_value(item, "name", "") or _item_value(item, "type", ""), 32, "Weapon")
    return {
        "name": name,
        "damage": raw_damage,
        "armor": raw_armor,
        "stars": stars,
        "soul": soul,
        "fit": fit,
        "two_handed": two_handed,
        "finished_damage": finished_damage,
        "finished_armor": finished_armor,
    }


def _blank_hand(name: str) -> dict:
    return {
        "name": name, "damage": Decimal(0), "armor": Decimal(0), "stars": 0,
        "soul": 0, "fit": 0, "two_handed": False,
    }


def sheet_from_equipped(
    *,
    hero_name: str = "Hero",
    race: str = "None",
    classes=None,
    profile_atk=1,
    profile_def=1,
    stat_atk=0,
    stat_def=0,
    stat_hp=0,
    city=0,
    level=1,
    profile_hp=0,
    amulet_attack=0,
    amulet_defense=0,
    amulet_hp=0,
    items=None,
) -> Sheet:
    """Split equipped rows into the two hands plus a finished pile for the rest."""
    grade_damage, grade_armor, lines = class_grades(classes)
    right = None
    left = None
    other_damage = Decimal(0)
    other_armor = Decimal(0)
    for item in items or []:
        hand = str(_item_value(item, "hand", "any") or "any").strip().lower()
        state = _hand_from_item(item, lines, two_handed=(hand == "both"))
        overflow = False
        if hand == "left":
            if left is None:
                state["two_handed"] = False
                left = state
            else:
                overflow = True
        elif hand == "right":
            if right is None:
                state["two_handed"] = False
                right = state
            else:
                overflow = True
        elif hand == "both":
            if right is None:
                right = state
            else:
                overflow = True
        elif right is None:
            state["two_handed"] = False
            right = state
        elif left is None:
            state["two_handed"] = False
            left = state
        else:
            overflow = True
        if overflow:
            other_damage += state["finished_damage"]
            other_armor += state["finished_armor"]
    right = right or _blank_hand("Empty")
    left = left or _blank_hand("Empty")
    known_race = race if race in RACE_NAMES else "None"
    return Sheet(
        hero_name=clean(hero_name, 32, "Hero"),
        origin="loaded",
        right_name=right["name"],
        right_damage=right["damage"],
        right_armor=right["armor"],
        right_stars=right["stars"],
        right_soul=right["soul"],
        right_fit=right["fit"],
        right_two_handed=right["two_handed"],
        left_name=left["name"],
        left_damage=left["damage"],
        left_armor=left["armor"],
        left_stars=left["stars"],
        left_soul=left["soul"],
        left_fit=left["fit"],
        other_damage=other_damage,
        other_armor=other_armor,
        race=known_race,
        class_damage=grade_damage,
        class_armor=grade_armor,
        profile_atk=D(profile_atk),
        profile_def=D(profile_def),
        stat_atk=int(D(stat_atk)),
        stat_def=int(D(stat_def)),
        stat_hp=int(D(stat_hp)),
        city=int(D(city)),
        level=max(1, int(D(level))),
        profile_hp=D(profile_hp),
        amulet_atk=D(amulet_attack),
        amulet_def=D(amulet_defense),
        amulet_hp=D(amulet_hp),
    )


def move(sheet: Sheet, key: str, amount) -> None:
    field = FIELDS[key]
    if field.kind == "race":
        names = [name for name, _, _ in RACES]
        index = names.index(sheet.race) if sheet.race in names else 0
        index = int(clamp(Decimal(index) + D(amount), Decimal(0), Decimal(len(names) - 1)))
        sheet.race = names[index]
        return
    updated = clamp(D(getattr(sheet, key)) + D(amount), field.minimum, field.maximum)
    if field.kind in {"int", "fit"}:
        updated = int(updated.to_integral_value(rounding=ROUND_HALF_UP))
    setattr(sheet, key, updated)


def can_move(sheet: Sheet, key: str, amount) -> bool:
    if D(amount) == 0:
        return False
    trial = copy.copy(sheet)
    move(trial, key, amount)
    return getattr(trial, key) != getattr(sheet, key)


def restore_field(sheet: Sheet, baseline: Sheet, key: str) -> None:
    setattr(sheet, key, getattr(baseline, key))


def step_label(amount, sign: str) -> str:
    amount = D(amount)
    if amount >= 1000 and amount == amount.to_integral_value() and int(amount) % 1000 == 0:
        text = f"{int(amount) // 1000}k"
    elif amount == amount.to_integral_value():
        text = str(int(amount))
    else:
        text = f"{amount:.2f}"
    return f"{sign}{text}"


def control_state(sheet: Sheet, key: str, index: int, sign: int) -> tuple[str, bool]:
    """Button label, and whether it is disabled."""
    field = FIELDS[key]
    amount = field.steps[index]
    if amount in field.steps[:index]:
        return "·", True
    label = step_label(amount, "-" if sign < 0 else "+")
    return label, not can_move(sheet, key, amount * sign)


def shown_value(sheet: Sheet, key: str) -> str:
    field = FIELDS[key]
    if field.kind == "race":
        damage, armor = race_bonus(sheet.race)
        return f"{sheet.race} ({signed(damage)} attack, {signed(armor)} armor)"
    if field.kind == "fit":
        return FITS[int(getattr(sheet, key))][2]
    if field.kind == "mult":
        return f"×{fmt_mult(getattr(sheet, key))}"
    if key.endswith("_stars"):
        stars = int(getattr(sheet, key))
        return f"★{stars} +{fmt_pct(starforge_bonus_pct(stars))}"
    if key.endswith("_soul"):
        level = int(getattr(sheet, key))
        rank = soulbound_rank_for_level(level)
        percent = f"+{fmt_pct(soulbound_bonus_pct_for_level(level))}"
        if rank:
            return f"level {level} {rank[0]} {percent}"
        return f"level {level} {percent}"
    return fmt(getattr(sheet, key))


def editable_value(sheet: Sheet, key: str) -> str:
    field = FIELDS[key]
    if field.kind == "race":
        return sheet.race
    if field.kind == "fit":
        return ("0", "5", "10", "shield")[int(getattr(sheet, key))]
    value = D(getattr(sheet, key))
    if field.kind == "int":
        return str(int(value))
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def apply_text(sheet: Sheet, key: str, text: str) -> str | None:
    """Put a typed value on the sheet. Returns an error sentence, or None."""
    raw = str(text or "").strip().replace(",", "")
    field = FIELDS[key]
    if not raw:
        return "Enter a number."
    if field.kind == "race":
        match = next((name for name, _, _ in RACES if name.lower() == raw.lower()), None)
        if match is None:
            names = ", ".join(name for name, _, _ in RACES)
            return f"Use one of: {names}."
        sheet.race = match
        return None
    if field.kind == "fit":
        token = raw.lower().replace("+", "").strip()
        indexes = {"0": 0, "none": 0, "no": 0, "5": 1, "10": 2, "7": 3, "shield": 3}
        if token not in indexes:
            return "Use 0, 5, 10, or shield."
        setattr(sheet, key, indexes[token])
        return None
    if key in {"profile_atk", "profile_def"}:
        return _apply_full_rs(sheet, key, raw)
    if field.kind == "mult":
        raw = raw.lower().strip("x")
    try:
        number = D(raw)
    except (InvalidOperation, ValueError):
        return "Enter a number."
    if not number.is_finite():
        return "Enter a finite number."
    step = Decimal("1") if field.kind == "int" else Decimal("0.001")
    number = number.quantize(step, rounding=ROUND_HALF_UP)
    number = clamp(number, field.minimum, field.maximum)
    if field.kind == "int":
        number = int(number)
    setattr(sheet, key, number)
    return None


def _apply_full_rs(sheet: Sheet, key: str, raw: str) -> str | None:
    """The typed number is the multiplier `$rs` shows, including stat points and the raid hall."""
    raw = raw.lower().strip().lstrip("x").rstrip("x")
    try:
        number = D(raw)
    except (InvalidOperation, ValueError):
        return "Enter a number."
    if not number.is_finite():
        return "Enter a finite number."
    number = number.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    points = sheet.stat_atk if key == "profile_atk" else sheet.stat_def
    extra = D(points) * STAT_ATTACK_DEFENSE_PER_POINT + D(sheet.city) * CITY_STEP
    field = FIELDS[key]
    setattr(sheet, key, clamp(number - extra, field.minimum, field.maximum))
    return None


def full_multiplier(sheet: Sheet, key: str) -> Decimal:
    """The attack or defense multiplier `$rs` shows: profile upgrade + stat points + raid hall."""
    points = sheet.stat_atk if key == "profile_atk" else sheet.stat_def
    return D(getattr(sheet, key)) + D(points) * STAT_ATTACK_DEFENSE_PER_POINT + D(sheet.city) * CITY_STEP


def knob_text(sheet: Sheet, key: str) -> str:
    if key in {"profile_atk", "profile_def"}:
        return fmt_mult(full_multiplier(sheet, key))
    return editable_value(sheet, key)


def apply_preset(sheet: Sheet, token: str) -> None:
    if token == "clear":
        sheet.amulet_atk = Decimal(0)
        sheet.amulet_def = Decimal(0)
        sheet.amulet_hp = Decimal(0)
        return
    kind, _, tier_text = token.partition(":")
    stats = AMULET_PRESETS[kind][int(tier_text)]
    sheet.amulet_atk = Decimal(stats["attack"])
    sheet.amulet_def = Decimal(stats["defense"])
    sheet.amulet_hp = Decimal(stats["hp"])


def matching_preset(sheet: Sheet) -> str | None:
    attack, defense, hp = int(D(sheet.amulet_atk)), int(D(sheet.amulet_def)), int(D(sheet.amulet_hp))
    if attack == defense == hp == 0:
        return "clear"
    for kind, tiers in AMULET_PRESETS.items():
        for tier, stats in tiers.items():
            if stats["attack"] == attack and stats["defense"] == defense and stats["hp"] == hp:
                return f"{kind}:{tier}"
    return None


def preset_choices() -> list[tuple[str, str, str]]:
    """(value, label, description) for the crafted-amulet menu. At most 25."""
    choices = [("clear", "No amulet", "ATK 0, DEF 0, HP 0")]
    labels = {"attack": "Attack", "defense": "Defense", "health": "Health", "balanced": "Balanced"}
    for kind in PRESET_KINDS:
        for tier in PRESET_TIERS:
            stats = AMULET_PRESETS[kind][tier]
            choices.append((
                f"{kind}:{tier}",
                f"Tier {tier} {labels[kind]}",
                f"ATK {stats['attack']:,}, DEF {stats['defense']:,}, HP {stats['hp']:,}",
            ))
    return choices


def _hand_shown(sheet: Sheet, side: str) -> bool:
    name = getattr(sheet, f"{side}_name")
    return name not in {"", "Empty"} or D(getattr(sheet, f"{side}_damage")) != 0 or D(getattr(sheet, f"{side}_armor")) != 0


def _hand_knob(sheet: Sheet, side: str) -> tuple[str, str]:
    """The one number on this hand a player would type: damage, or armor when that is all it has."""
    name = clean(getattr(sheet, f"{side}_name"), 40, side.title())
    damage = D(getattr(sheet, f"{side}_damage"))
    armor = D(getattr(sheet, f"{side}_armor"))
    if damage > 0 or armor == 0:
        return f"{side}_damage", f"{name} damage"[:100]
    return f"{side}_armor", f"{name} armor"[:100]


def knobs(sheet: Sheet) -> list[tuple[str, str]]:
    """(field, menu label) for weapon damage and the two $rs multipliers."""
    found = [_hand_knob(sheet, side) for side in ("right", "left") if _hand_shown(sheet, side)]
    if not found:
        found.append(("right_damage", "Weapon damage"))
    found.append(("profile_atk", "$rs attack"))
    found.append(("profile_def", "$rs defense"))
    return found


def knob_steps(key: str) -> tuple[Decimal, Decimal]:
    """Small step, then the larger step. $rs moves by one upgrade (0.10)."""
    if FIELDS[key].kind == "mult":
        return Decimal("0.1"), Decimal("1")
    return Decimal(1), Decimal(10)


def _fit_tag(fit: int) -> str:
    damage, armor, _label = FITS[int(fit)]
    if damage:
        return f"+{fmt(damage)}"
    if armor:
        return f"+{fmt(armor)} shield"
    return ""


def _weapon_line(sheet: Sheet, side: str) -> str | None:
    if not _hand_shown(sheet, side):
        return None
    name = clean(getattr(sheet, f"{side}_name"), 24, side.title())
    raw_damage = D(getattr(sheet, f"{side}_damage"))
    raw_armor = D(getattr(sheet, f"{side}_armor"))
    stars = int(getattr(sheet, f"{side}_stars"))
    soul = int(getattr(sheet, f"{side}_soul"))
    fit = int(getattr(sheet, f"{side}_fit"))
    dealt, blocked, _pct = _contribute(raw_damage, raw_armor, stars, soul, fit)
    parts = [f"**{name}**", f"{fmt(raw_damage)} dmg" if raw_damage else "", f"{fmt(raw_armor)} armor" if raw_armor else ""]
    if stars:
        parts.append(f"★{stars}")
    if soul:
        parts.append(f"soul {soul}")
    tag = _fit_tag(fit)
    if tag:
        parts.append(tag)
    if side == "right" and sheet.right_two_handed:
        parts.append("two-handed")
    parts = [part for part in parts if part]
    line = " · ".join(parts)
    outcome = []
    fit_damage, fit_armor, _label = FITS[fit]
    if raw_damage or fit_damage:
        outcome.append(f"{fmt(dealt)} dmg")
    if raw_armor or fit_armor:
        outcome.append(f"{fmt(blocked)} armor")
    changed = bool(stars or soul or tag or (raw_damage and dealt != raw_damage) or (raw_armor and blocked != raw_armor))
    if changed and outcome:
        line += " → " + ", ".join(outcome)
    return line


def _modifier_lines(sheet: Sheet) -> list[str]:
    lines = []
    race_damage, race_armor = race_bonus(sheet.race)
    if race_damage or race_armor:
        lines.append(f"{sheet.race} {signed(race_damage)} atk, {signed(race_armor)} def")
    if sheet.class_damage or sheet.class_armor:
        lines.append(f"Class grade {signed(sheet.class_damage)} atk, {signed(sheet.class_armor)} def")
    points = []
    if sheet.stat_atk:
        points.append(f"{fmt(sheet.stat_atk)} atk pts")
    if sheet.stat_def:
        points.append(f"{fmt(sheet.stat_def)} def pts")
    if sheet.stat_hp:
        points.append(f"{fmt(sheet.stat_hp)} hp pts")
    if points:
        lines.append(", ".join(points))
    if sheet.city:
        lines.append(f"Raid hall {fmt(sheet.city)}")
    if D(sheet.other_damage) or D(sheet.other_armor):
        lines.append(f"Other gear {fmt(sheet.other_damage)} dmg, {fmt(sheet.other_armor)} armor")
    if D(sheet.amulet_atk) or D(sheet.amulet_def) or D(sheet.amulet_hp):
        lines.append(
            f"Amulet {signed(sheet.amulet_atk)} atk, {signed(sheet.amulet_def)} def, {signed(sheet.amulet_hp)} hp"
        )
    return lines


def _hint(sheet: Sheet, result: Result, active: str) -> str:
    if active in {"right_damage", "left_damage"}:
        pct = result.right_pct if active.startswith("right") else result.left_pct
        worth = (Decimal(1) + pct) * result.attack_multiplier
        return f"+1 damage adds {signed(worth)} attack"
    if active in {"right_armor", "left_armor"}:
        pct = result.right_pct if active.startswith("right") else result.left_pct
        worth = (Decimal(1) + pct) * result.defense_multiplier
        return f"+1 armor adds {signed(worth)} defense"
    if active == "profile_atk":
        return f"One $rs attack upgrade (+0.10) adds {signed(result.gear_attack * PAID_STEP)} attack"
    if active == "profile_def":
        return f"One $rs defense upgrade (+0.10) adds {signed(result.gear_defense * PAID_STEP)} defense"
    return ""


def card(sheet: Sheet, active: str = "right_damage", baseline: Sheet | None = None) -> str:
    """Short phone-sized card: totals, the weapons, and the modifiers already equipped."""
    result = compute(sheet)
    lines = []
    if sheet.origin == "example":
        lines.append("Example gear. **My gear** loads yours.")
    elif sheet.origin == "missing":
        lines.append(f"No character for {clean(sheet.hero_name, 32, 'them')}. Example numbers.")
    lines.append(f"**Attack** {fmt(result.raid_attack)}")
    lines.append(f"**Defense** {fmt(result.raid_defense)}")
    lines.append(f"**Health** {fmt(result.health)}")
    hint = _hint(sheet, result, active)
    if hint:
        lines.append(hint)
    if baseline is not None:
        previous = compute(baseline)
        if (
            previous.raid_attack != result.raid_attack
            or previous.raid_defense != result.raid_defense
            or previous.health != result.health
        ):
            lines.append(
                f"Was {fmt(previous.raid_attack)} attack, {fmt(previous.raid_defense)} defense, {fmt(previous.health)} hp"
            )
    lines.append("")
    lines.append("**Weapons**")
    weapon_lines = [line for side in ("right", "left") if (line := _weapon_line(sheet, side))]
    lines.extend(weapon_lines or ["Nothing equipped"])
    lines.append("")
    lines.append("**On you**")
    lines.extend(_modifier_lines(sheet) or ["No extra modifiers"])
    lines.append("")
    lines.append(f"**$rs** ×{fmt_mult(result.attack_multiplier)} attack · ×{fmt_mult(result.defense_multiplier)} defense")
    return "\n".join(lines)

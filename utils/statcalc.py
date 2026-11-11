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
    STARFORGE_STAT_PCT_PER_STAR,
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
    quantized = D(number).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
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


def exact(number) -> str:
    shown = fmt(number)
    rounded = f"{profile_round(number):,}"
    if shown == rounded:
        return shown
    return f"{shown} (profile card {rounded})"


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


def _pct_sources(stars, soul) -> str:
    parts = []
    if int(stars):
        parts.append(f"★{int(stars)} +{fmt_pct(starforge_bonus_pct(int(stars)))}")
    if int(soul):
        parts.append(f"soulbound +{fmt_pct(soulbound_bonus_pct_for_level(int(soul)))}")
    return ", ".join(parts)


def _side_line(slot: str, name: str, raw, stars, soul, fit, side: str) -> str:
    fit_damage, fit_armor, _label = FITS[int(fit)]
    flat = fit_damage if side == "damage" else fit_armor
    pct = starforge_bonus_pct(int(stars)) + soulbound_bonus_pct_for_level(int(soul))
    total = D(raw) * (Decimal(1) + pct) + flat
    if D(raw) == 0 and flat == 0:
        return f"{slot} · {name}: 0 {side}"
    expr = fmt(raw)
    if pct:
        expr += f" × {fmt_mult(Decimal(1) + pct)} ({_pct_sources(stars, soul)})"
    if flat:
        expr += f" + {fmt(flat)} class fit"
    return f"{slot} · {name}: {expr} = **{fmt(total)}**"


def _slider_block(sheet: Sheet, field: Field) -> str:
    if sheet.origin == "loaded":
        origin = f"Loaded from {clean(sheet.hero_name, 32, 'Hero')}'s equipped gear."
    elif sheet.origin == "missing":
        origin = f"No character for {clean(sheet.hero_name, 32, 'them')}. These are example numbers."
    else:
        origin = "Example hero, so the buttons work before you have gear. Load my hero fills your weapons."
    title = field.label
    if field.key.startswith("right"):
        title = f"{field.label} · {sheet.right_name}"
    elif field.key.startswith("left"):
        title = f"{field.label} · {sheet.left_name}"
    if field.kind == "race":
        names = [name for name, _, _ in RACES]
        index = names.index(sheet.race) if sheet.race in names else 0
        slider = bar(index, 0, len(names) - 1)
    elif field.kind == "fit":
        slider = bar(getattr(sheet, field.key), 0, 3)
    else:
        value = D(getattr(sheet, field.key))
        high = field.bar_cap if value <= field.bar_cap else value
        slider = bar(value, field.minimum, high)
    return "\n".join((
        origin,
        f"**{title}**  {shown_value(sheet, field.key)}",
        f"`{slider}`",
        field.blurb,
        "The bar is the slider. The buttons move it. Type number sets it exactly.",
    ))


def _multiplier_line(sheet: Sheet, result: Result, kind: str) -> str:
    if kind == "attack":
        profile = result.profile_attack
        points = sheet.stat_atk
        point_name = "attack points"
        point_total = result.point_attack
        multiplier = result.attack_multiplier
    else:
        profile = result.profile_defense
        points = sheet.stat_def
        point_name = "defense points"
        point_total = result.point_defense
        multiplier = result.defense_multiplier
    return (
        f"Multiplier **×{fmt_mult(multiplier)}**, added up from "
        f"{fmt_mult(profile)} profile + "
        f"{fmt(points)} {point_name} × {fmt_mult(STAT_ATTACK_DEFENSE_PER_POINT)} (= {fmt_mult(point_total)}) + "
        f"raid hall {fmt(sheet.city)} × {fmt_mult(CITY_STEP)} (= {fmt_mult(result.city_bonus)})"
    )


def _attack_block(sheet: Sheet, result: Result) -> str:
    lines = [
        "**Attack**",
        _side_line("Right", sheet.right_name, sheet.right_damage, sheet.right_stars, sheet.right_soul, sheet.right_fit, "damage"),
    ]
    if sheet.right_two_handed:
        lines.append("This weapon is two-handed, so those stats are counted once.")
    lines.extend((
        _side_line("Left", sheet.left_name, sheet.left_damage, sheet.left_stars, sheet.left_soul, sheet.left_fit, "damage"),
        f"Other gear **{fmt(sheet.other_damage)}** (its stars and class fit are already inside)",
        f"{sheet.race} **{signed(race_bonus(sheet.race)[0])}** attack, **{signed(race_bonus(sheet.race)[1])}** armor",
        f"Class grade **{signed(sheet.class_damage)}** attack, **{signed(sheet.class_armor)}** armor",
        f"**Gear attack {fmt(result.gear_attack)}**",
        _multiplier_line(sheet, result, "attack"),
        f"{fmt(result.gear_attack)} × {fmt_mult(result.attack_multiplier)} = **{fmt(result.multiplied_attack)}**",
        f"Amulet **{signed(result.amulet_attack)}** is added onto that.",
        f"**Raid attack {exact(result.raid_attack)}**",
    ))
    if result.gear_attack == 0:
        lines.append("Gear attack is 0, so this multiplier leaves raid attack equal to the amulet.")
    if result.raid_attack < 0:
        lines.append("The profile card shows 0 here.")
    return "\n".join(lines)


def _defense_block(sheet: Sheet, result: Result) -> str:
    lines = [
        "**Defense**",
        _side_line("Right", sheet.right_name, sheet.right_armor, sheet.right_stars, sheet.right_soul, sheet.right_fit, "armor"),
        _side_line("Left", sheet.left_name, sheet.left_armor, sheet.left_stars, sheet.left_soul, sheet.left_fit, "armor"),
        f"Other gear **{fmt(sheet.other_armor)}**",
        f"**Gear defense {fmt(result.gear_defense)}**",
        _multiplier_line(sheet, result, "defense"),
        f"{fmt(result.gear_defense)} × {fmt_mult(result.defense_multiplier)} = **{fmt(result.multiplied_defense)}**",
        f"Amulet **{signed(result.amulet_defense)}** is added onto that.",
        f"**Raid defense {exact(result.raid_defense)}**",
    ]
    if result.raid_defense < 0:
        lines.append("The profile card shows 0 here.")
    return "\n".join(lines)


def _health_block(sheet: Sheet, result: Result, prefix: str) -> str:
    return "\n".join((
        "**Health**",
        "Health is a sum. Each step is added to the others.",
        (
            f"{BASE_HP} base + {fmt(result.profile_hp)} profile + "
            f"level {fmt(sheet.level)} × {HP_PER_LEVEL} (= {fmt(result.level_hp)}) + "
            f"{fmt(sheet.stat_hp)} health points × {STAT_HEALTH_PER_POINT} (= {fmt(result.stat_hp_bonus)}) + "
            f"{fmt(result.amulet_hp)} amulet"
        ),
        f"**Health {exact(result.health)}**",
        (
            f"A purchased health upgrade adds +{HP_PER_PURCHASE} profile HP. "
            f"The Health Multiplier on `{prefix}raidstats` is the price ladder for that purchase."
        ),
    ))


def _worth_block(sheet: Sheet, result: Result, active: str) -> str:
    side = "left" if active.startswith("left") else "right"
    if side == "left":
        raw, stars, pct = sheet.left_damage, sheet.left_stars, result.left_pct
    else:
        raw, stars, pct = sheet.right_damage, sheet.right_stars, result.right_pct
    per_damage = (Decimal(1) + pct) * result.attack_multiplier
    per_star = D(raw) * STARFORGE_STAT_PCT_PER_STAR * result.attack_multiplier
    lines = [
        "**What one more is worth**",
        f"1 attack point → **{signed(result.gear_attack * STAT_ATTACK_DEFENSE_PER_POINT)}** raid attack",
        f"1 defense point → **{signed(result.gear_defense * STAT_ATTACK_DEFENSE_PER_POINT)}** raid defense",
        f"1 health point → **+{STAT_HEALTH_PER_POINT}** health",
        f"1 paid attack upgrade (+0.10) → **{signed(result.gear_attack * PAID_STEP)}** raid attack",
        f"1 paid defense upgrade (+0.10) → **{signed(result.gear_defense * PAID_STEP)}** raid defense",
        f"1 paid health upgrade → **+{HP_PER_PURCHASE}** health",
        f"1 more {side}-weapon damage → **{signed(per_damage)}** raid attack",
    ]
    if int(stars) >= STARFORGE_MAX_STARS:
        lines.append(f"The {side} weapon is at {STARFORGE_MAX_STARS} stars, the cap.")
    elif D(raw) == 0:
        lines.append(
            f"1 more star on the {side} weapon → **+0** raid attack, because stars percent-multiply listed damage."
        )
    else:
        lines.append(f"1 more star on the {side} weapon → **{signed(per_star)}** raid attack")
    lines.append("1 amulet attack → **+1** raid attack")
    return "\n".join(lines)


def _since_block(current: Result, previous: Result) -> str:
    if (
        current.raid_attack == previous.raid_attack
        and current.raid_defense == previous.raid_defense
        and current.health == previous.health
    ):
        return ""
    return "\n".join((
        "**Since you opened this**",
        f"Attack {fmt(previous.raid_attack)} → {fmt(current.raid_attack)} ({signed(current.raid_attack - previous.raid_attack)})",
        f"Defense {fmt(previous.raid_defense)} → {fmt(current.raid_defense)} ({signed(current.raid_defense - previous.raid_defense)})",
        f"Health {fmt(previous.health)} → {fmt(current.health)} ({signed(current.health - previous.health)})",
    ))


_ORDER = "\n".join((
    "**What multiplies what**",
    "1. Star percent and soulbound percent are added together, then that percent multiplies the weapon.",
    "2. Class fit, race, and class grade are added after the star percent.",
    "3. Profile multiplier, stat points, and raid hall levels are added into one multiplier.",
    "4. That multiplier is applied to all of the gear.",
    "5. Amulet attack and defense are added onto the result.",
    "Defense follows the same five steps with armor. Health is a sum.",
))


def explain(sheet: Sheet, active: str = "right_damage", baseline: Sheet | None = None, prefix: str = "$") -> str:
    result = compute(sheet)
    field = FIELDS.get(active) or FIELDS["right_damage"]
    parts = [
        _slider_block(sheet, field),
        _ORDER,
        _attack_block(sheet, result),
        _defense_block(sheet, result),
        _health_block(sheet, result, prefix),
        _worth_block(sheet, result, field.key),
    ]
    if baseline is not None:
        parts.append(_since_block(result, compute(baseline)))
    return "\n\n".join(part for part in parts if part)

# battles/extensions/pet_species.py
"""Skill trees for the exclusive Fables Library species.

These pets come from the Library hatchery (and the Fables events) rather than
the wild. Each species replaces its element's tree with one of its own, built
around one idea - marks, Stillness, Harvest, Chill, Embers, night and day, or
critical hits - so its three branches feed each other. Ultimates fire once per
battle on their own condition instead of the element trees' shared low-HP one.

The trees keep the element trees' shape: five skills per branch at levels
1/3/5/7/10 costing 1-5 SP. Every number a description promises lives in
SKILL_PARAMS (tests/test_pet_species_skills.py checks the two agree), and the
battle behaviour for all of them is in SpeciesSkills below. PetExtension calls
into it from its usual hooks; Battle.apply_pet_owner_guard calls `guard`.

Durations count the pet's own turns: "for 2 turns" means until its second
turn from now begins.
"""

import datetime
import random
from decimal import Decimal

from classes import dragonkin


def D(value):
    return Decimal(str(value))


# The Great Seven's whelps share one tree; their element is the species' own.
WHELP_SPECIES = (
    "Ilisrei's Whelp", "Knoas's Whelp", "Unoquil's Whelp", "Xetoa's Whelp",
    "Tamanir's Whelp", "Kadelej's Whelp", "Saphira's Whelp",
)

# monsters.json species name (monster_pets.default_name) -> skill tree.
SPECIES_TREE_OF = {
    "Inkwyrm": "Inkwyrm",
    "Reedling": "Reedling",
    "Lanternling": "Lanternling",
    "Gourdling": "Gourdling",
    "Frostfawn": "Frostfawn",
    "Hearthkit": "Hearthkit",
    **{name: "Soulgem" for name in WHELP_SPECIES},
}

TREE_EMOJIS = {
    "Inkwyrm": "🖋️", "Reedling": "🪷", "Soulgem": "💎", "Lanternling": "🏮",
    "Gourdling": "🎃", "Frostfawn": "❄️", "Hearthkit": "🔥",
}

# Library-born: every species pet's innate gift, free of skill points. Hatched from a Fables
# egg rather than found in the wild, it fights a little above its stats, more with each
# evolution Chapter (utils/library_pets.py).
LIBRARY_BORN_PER_CHAPTER = 1
LIBRARY_BORN_BONUS = 10  # at Chapter X
LIBRARY_BORN = (f"Library-born: +{LIBRARY_BORN_PER_CHAPTER}% HP, attack and defense in battle per evolution Chapter "
                f"(+{LIBRARY_BORN_BONUS}% at Chapter X). Ultimates open at Chapter V.")

# How every pet heal scales (PetExtension._scaled_heal), said once on the species trees' pages.
HEAL_RULE = "Heals are a share of the lower max HP between the pet and whoever it heals, like every pet heal."

TREE_IDEAS = {
    "Inkwyrm": "Marks: the Inkwyrm annotates enemies, and everything it does hits marked foes harder.",
    "Reedling": "Stillness: +1 at the start of each of its turns if nothing hit it since its last one (up to 5). Being hit costs 2.",
    "Soulgem": "Critical hits: Gemfire gives it its own chance to crit for 1.75x damage, and the Great Seven answer.",
    "Lanternling": "Night and day: night battles are 6 PM to 6 AM server time, and its light burns brighter then.",
    "Gourdling": "Harvest: +1 at the start of each of its turns and +1 the first time it is hit each turn (up to 5).",
    "Frostfawn": "Chill: 3 Chill freezes an enemy for its next turn, and the Chill starts again.",
    "Hearthkit": "Embers: +1 at the start of each of its turns (up to 5).",
}


def _skill(name, cost, description):
    return {"name": name, "cost": cost, "description": description}


SPECIES_SKILL_TREES = {
    "Inkwyrm": {
        "Quill": {
            1: _skill("Ink Blot", 1, "50% chance its attacks mark the target for 4 turns. Marked enemies have 20% less armor"),
            3: _skill("Underline", 2, "+35% damage against marked enemies"),
            5: _skill("Footnote", 3, "Hitting a marked enemy adds a follow-up strike for 60% of the hit"),
            7: _skill("Redact", 4, "Marked enemies deal 25% less damage"),
            10: _skill("Final Chapter", 5, "ULTIMATE (after 2 marks this battle): strikes every marked enemy for 3x its attack, then each mark bursts for 100% of its attack"),
        },
        "Margin": {
            1: _skill("Margin Notes", 1, "Whenever it marks an enemy, its owner gains +20% damage for 2 turns"),
            3: _skill("Errata", 2, "Hits that would leave its owner below 50% HP deal 35% less"),
            5: _skill("Bookmark", 3, "Once per battle, 2 turns after its owner first drops below 30% HP, they recover 25%"),
            7: _skill("Annotated Edition", 4, "While any enemy is marked, the team has +15% damage and armor"),
            10: _skill("Rewrite", 5, "ULTIMATE (owner drops below 25% HP): the next 2 hits on its owner heal them instead"),
        },
        "Archive": {
            1: _skill("Inkshadow", 1, "20% chance to dodge attacks, and an attacker it dodges is marked"),
            3: _skill("Smudge", 2, "Marked enemies have 20% less accuracy"),
            5: _skill("Blotted Page", 3, "20% chance that hitting a marked enemy makes it lose its next turn"),
            7: _skill("Late Reading", 4, "+6% damage for each marked enemy (max +30%)"),
            10: _skill("Library Lock", 5, "ULTIMATE (drops below 40% HP): marks every enemy for 4 turns and every enemy loses its next turn"),
        },
    },
    "Reedling": {
        "Current": {
            1: _skill("Undertow", 1, "+6% damage per Stillness (max +30%)"),
            3: _skill("Reed Lance", 2, "Its first attack each battle ignores armor"),
            5: _skill("Drag Under", 3, "25% chance its target loses its next turn. With 3+ Stillness it is certain and spends 3 Stillness"),
            7: _skill("Riptide", 4, "Attacks splash 60% of the hit onto another enemy (90% at 5 Stillness)"),
            10: _skill("Floodgate", 5, "ULTIMATE (at 5 Stillness): spends all Stillness on a 3x strike, and every enemy loses its next turn"),
        },
        "Shallows": {
            1: _skill("Still Water", 1, "The first hit on its owner each battle is absorbed, up to 20% of their max HP"),
            3: _skill("Clear Pool", 2, "With 2+ Stillness, its owner heals 5% at the start of each of its turns"),
            5: _skill("Ripple Ward", 3, "The first time its owner is hit between its turns, 40% of that damage returns as a shield on them"),
            7: _skill("Deep Calm", 4, "Being hit only costs 1 Stillness instead of 2"),
            10: _skill("Mirror Lake", 5, "ULTIMATE (owner drops below 30% HP): for 2 turns its owner takes 50% less damage and attackers take 50% of the original hit"),
        },
        "Marsh": {
            1: _skill("Reed Cover", 1, "20% chance to dodge attacks"),
            3: _skill("Murk", 2, "After it dodges, the attacker has 15% less accuracy for 2 turns"),
            5: _skill("Lurk", 3, "Dodges every attack until its 2nd turn ends"),
            7: _skill("Marsh Mist", 4, "During its first 3 turns, the team dodges 10% of attacks"),
            10: _skill("Old One of the Reeds", 5, "ULTIMATE (after 3 dodges): its next attack strikes for 2.5x and stuns the target for 1 turn"),
        },
    },
    "Soulgem": {
        "Gemfire": {
            1: _skill("Glint", 1, "35% chance for a critical hit (1.75x damage)"),
            3: _skill("Facet Strike", 2, "Critical hits deal +40% more"),
            5: _skill("Dragonbane", 3, "+30% damage against dragons"),
            7: _skill("Prism Split", 4, "Critical hits splash 60% onto another enemy"),
            10: _skill("Echo of the Seven", 5, "ULTIMATE (after 4 critical hits): its Great Seven's echo strikes every enemy for 3.5x its attack, plus its element's gift: Fire burns, Water heals the team 20%, Nature entangles, Light cleanses the team, Dark drains, Wind and Electric stop enemies' turns, Corrupted cracks armor"),
        },
        "Hoard": {
            1: _skill("Gem Ward", 1, "Takes 20% less damage from its own element and 12% less from others"),
            3: _skill("Clutch Instinct", 2, "When its owner is below 50% HP, they gain a shield of 25% of max HP (at most once every 5 of its turns)"),
            5: _skill("Facet Armor", 3, "+4% armor each time it is hit (max +20%)"),
            7: _skill("Bloodline", 4, "If its owner is Dragonkin or a Breathcaller, the team takes 12% less damage"),
            10: _skill("Sacrament", 5, "ULTIMATE (a hit would defeat its owner): they survive at 1 HP, heal 40% and can't be hurt for 1 turn"),
        },
        "Resonance": {
            1: _skill("Hum", 1, "The team has +12% damage"),
            3: _skill("Harmonic", 2, "Allies sharing its element have +15% damage"),
            5: _skill("Seven Lights", 3, "At the start of each of its turns, clears a stun, paralysis or burn from one ally"),
            7: _skill("Chorus", 4, "The team gains +6% damage and armor for each different Great Seven whelp element on it (max +42%)"),
            10: _skill("The Hall Awakens", 5, "ULTIMATE (its 7th turn): the team gains +25% damage, armor and luck for 3 turns"),
        },
    },
    "Lanternling": {
        "Wick": {
            1: _skill("Kindle", 1, "+18% damage at night, +10% by day"),
            3: _skill("Lure", 2, "Its first attack each battle blinds the target: 25% less accuracy for 2 turns"),
            5: _skill("Will-o'-Wisp", 3, "30% chance a wisp strikes another enemy for 60% of the hit and burns it"),
            7: _skill("Burns Late", 4, "At night its attacks burn the target for 3 turns (20% of its attack each turn)"),
            10: _skill("Hallow's Flame", 5, "ULTIMATE (its 6th turn at night, or below 25% HP by day): strikes every enemy for 2.5x its attack and blinds them all"),
        },
        "Ward": {
            1: _skill("Nightlight", 1, "Its owner dodges 15% of attacks at night, 8% by day"),
            3: _skill("Safe Path", 2, "While it is above 40% HP, its owner takes 20% less damage"),
            5: _skill("Lantern Shell", 3, "On its first turn it gains a shield of 200% of its armor (250% at night)"),
            7: _skill("Last Light", 4, "Once per battle, survives a defeating hit at 1 HP"),
            10: _skill("Vigil", 5, "ULTIMATE (owner drops below 25% HP): it takes the next 2 hits aimed at its owner, at 50% damage"),
        },
        "Haunt": {
            1: _skill("Flicker", 1, "18% chance to dodge attacks"),
            3: _skill("Shadow Play", 2, "At night, enemies deal 20% less damage"),
            5: _skill("Ghostlight", 3, "+20% damage against blinded enemies"),
            7: _skill("Candle Count", 4, "Every 2nd turn, a free strike on a random enemy for 80% of its attack"),
            10: _skill("Hallowed Halls", 5, "ULTIMATE (its 5th turn): the team gains +25% damage and enemies lose 25% accuracy for 3 turns"),
        },
    },
    "Gourdling": {
        "Vine": {
            1: _skill("Tendril", 1, "35% chance to entangle the target: it deals 25% less damage for 2 turns"),
            3: _skill("Ripening", 2, "+6% damage per Harvest (max +30%)"),
            5: _skill("Gourd Toss", 3, "Every 3rd attack throws a gourd: 200% damage, with 50% of it splashing onto every other enemy"),
            7: _skill("Overgrowth", 4, "Entangled enemies take 30% of its attack at the start of each of its turns"),
            10: _skill("Great Pumpkin", 5, "ULTIMATE (at 5 Harvest): spends all Harvest on a 3.5x strike and entangles every enemy for 2 turns"),
        },
        "Feast": {
            1: _skill("Snack", 1, "Its owner heals 4% at the start of each of its turns"),
            3: _skill("Harvest Feast", 2, "Once per battle, when its owner drops below 40% HP, heals them 25% and clears a stun, paralysis or burn"),
            5: _skill("Compost", 3, "The first time it is hit each turn, it heals 4% of its max HP"),
            7: _skill("Cornucopia", 4, "When its owner is below 50% HP and it has 3+ Harvest, spends 3 Harvest to heal the team 15%"),
            10: _skill("Bountiful", 5, "ULTIMATE (owner drops below 30% HP): heals the team 35%, then 10% more at the start of each of its next 3 turns"),
        },
        "Patch": {
            1: _skill("Thick Rind", 1, "Takes 15% less damage"),
            3: _skill("Scarecrow", 2, "20% chance an attack on its owner hits the Gourdling instead"),
            5: _skill("Root Down", 3, "+20% armor while it has 3+ Harvest"),
            7: _skill("Hollow Grin", 4, "Enemies that hit it have 10% less accuracy for 2 turns"),
            10: _skill("Harvest Moon", 5, "ULTIMATE (drops below 25% HP): regrows to 50% HP; at night it also entangles every enemy for 2 turns"),
        },
    },
    "Frostfawn": {
        "Frostbite": {
            1: _skill("Frost Chime", 1, "50% chance its attacks add 1 Chill"),
            3: _skill("Cold Snap", 2, "+45% damage against chilled or frozen enemies"),
            5: _skill("Hoarfrost", 3, "Each Chill on an enemy lowers its accuracy by 5% (max 15%)"),
            7: _skill("Shatter", 4, "Hitting a frozen enemy deals +80% and ends the freeze"),
            10: _skill("Midwinter", 5, "ULTIMATE (after 2 freezes, or below 20% HP): strikes every enemy for 2.5x its attack and adds 2 Chill to each"),
        },
        "Snowfall": {
            1: _skill("Soft Snow", 1, "Its owner takes 24% less damage"),
            3: _skill("Snow Veil", 2, "Its owner dodges 22% of attacks"),
            5: _skill("Ice Glaze", 3, "On its first turn it gains a shield of 200% of its armor, and enemies that hit it gain 1 Chill"),
            7: _skill("Winter Coat", 4, "During its first 2 turns, clears stuns, paralysis and burns from its owner at the start of its turn"),
            10: _skill("Silent Night", 5, "ULTIMATE (owner drops below 25% HP): freezes every enemy for 1 turn and heals its owner 25%"),
        },
        "Antler": {
            1: _skill("Bell", 1, "The team has +5% accuracy"),
            3: _skill("Fawn's Leap", 2, "Acts first in the turn order until its first attack"),
            5: _skill("Crystal Chime", 3, "Whenever an enemy freezes, the team heals 5%"),
            7: _skill("Northern Lights", 4, "After a freeze, the team gains +10% damage, armor and luck for 2 turns"),
            10: _skill("Feast Bells", 5, "ULTIMATE (its 6th turn): clears stuns, paralysis and burns from the team, gives +20% damage for 3 turns and adds 1 Chill to every enemy"),
        },
    },
    "Hearthkit": {
        "Coal": {
            1: _skill("Spark Pounce", 1, "30% chance to strike for 1.5x damage"),
            3: _skill("Stoke", 2, "+7% damage per Ember (max +35%)"),
            5: _skill("Flare-up", 3, "30% chance its attacks add 2 Embers"),
            7: _skill("Cinder Swipe", 4, "Its attacks burn the target for 3 turns (25% of its attack each turn)"),
            10: _skill("Yule Blaze", 5, "ULTIMATE (at 5 Embers): spends all Embers on a 3.5x strike and burns every enemy for 3 turns"),
        },
        "Hearth": {
            1: _skill("Banked Embers", 1, "On its first turn, the team gains a shield of 6% of max HP"),
            3: _skill("Warm Lap", 2, "Its owner heals 1% per Ember (max 3%) at the start of each of its turns"),
            5: _skill("Rekindle", 3, "On its 4th turn, team shields are topped back up to 8% of max HP"),
            7: _skill("Kept Warm", 4, "Once per battle, with 3+ Embers, spends 3 to keep its owner from falling (left at 1 HP)"),
            10: _skill("Home Fires", 5, "ULTIMATE (owner drops below 25% HP): the team gains a shield of 30% of max HP and heals 20%"),
        },
        "Curl": {
            1: _skill("Snug", 1, "Takes 15% less damage"),
            3: _skill("Catnap", 2, "Gains 2 extra Embers on a turn after one where it didn't attack"),
            5: _skill("Purr", 3, "While it has 3+ Embers, the team has +5% damage, armor and luck"),
            7: _skill("Ember Gift", 4, "At the start of each of its turns, the most hurt ally gains a shield of 3% of max HP"),
            10: _skill("Midwinter Hearth", 5, "ULTIMATE (its 6th turn): the team gains +20% damage, armor and luck for 3 turns, and every enemy burns for 3 turns"),
        },
    },
}

# Every number a description promises, by skill. Percentages are whole numbers.
SKILL_PARAMS = {
    # Inkwyrm
    "Ink Blot": {"chance": 50, "turns": 4, "armor_cut": 20},
    "Underline": {"bonus": 35},
    "Footnote": {"share": 60},
    "Redact": {"damage_cut": 25},
    "Final Chapter": {"marks": 2, "strike": 3, "burst": 100},
    "Margin Notes": {"bonus": 20, "turns": 2},
    "Errata": {"threshold": 50, "reduction": 35},
    "Bookmark": {"threshold": 30, "delay": 2, "heal": 25},
    "Annotated Edition": {"bonus": 15},
    "Rewrite": {"threshold": 25, "hits": 2},
    "Inkshadow": {"dodge": 20},
    "Smudge": {"accuracy_cut": 20},
    "Blotted Page": {"chance": 20},
    "Late Reading": {"per_mark": 6, "max": 30},
    "Library Lock": {"threshold": 40, "turns": 4},
    # Reedling
    "Undertow": {"per_stack": 6, "max": 30},
    "Reed Lance": {},
    "Drag Under": {"chance": 25, "stacks": 3},
    "Riptide": {"share": 60, "full_share": 90, "full_stacks": 5},
    "Floodgate": {"stacks": 5, "strike": 3},
    "Still Water": {"cap": 20},
    "Clear Pool": {"stacks": 2, "heal": 5},
    "Ripple Ward": {"share": 40},
    "Deep Calm": {"loss": 1, "normal_loss": 2},
    "Mirror Lake": {"threshold": 30, "turns": 2, "reduction": 50, "reflect": 50},
    "Reed Cover": {"dodge": 20},
    "Murk": {"accuracy_cut": 15, "turns": 2},
    "Lurk": {"turns": 2},
    "Marsh Mist": {"turns": 3, "dodge": 10},
    "Old One of the Reeds": {"dodges": 3, "strike": 2.5, "stun": 1},
    # Soulgem whelps
    "Glint": {"chance": 35, "crit": 1.75},
    "Facet Strike": {"bonus": 40},
    "Dragonbane": {"bonus": 30},
    "Prism Split": {"share": 60},
    "Echo of the Seven": {"crits": 4, "strike": 3.5, "heal": 20},
    "Gem Ward": {"own": 20, "other": 12},
    "Clutch Instinct": {"threshold": 50, "shield": 25, "cooldown": 5},
    "Facet Armor": {"per_hit": 4, "max": 20},
    "Bloodline": {"reduction": 12},
    "Sacrament": {"hp": 1, "heal": 40, "turns": 1},
    "Hum": {"bonus": 12},
    "Harmonic": {"bonus": 15},
    "Seven Lights": {},
    "Chorus": {"per_element": 6, "max": 42},
    "The Hall Awakens": {"turn": 7, "bonus": 25, "turns": 3},
    # Lanternling
    "Kindle": {"night": 18, "day": 10},
    "Lure": {"accuracy_cut": 25, "turns": 2},
    "Will-o'-Wisp": {"chance": 30, "share": 60},
    "Burns Late": {"turns": 3, "burn": 20},
    "Hallow's Flame": {"turn": 6, "threshold": 25, "strike": 2.5},
    "Nightlight": {"dodge": 15, "day_dodge": 8},
    "Safe Path": {"threshold": 40, "reduction": 20},
    "Lantern Shell": {"shield": 200, "night_shield": 250},
    "Last Light": {"hp": 1},
    "Vigil": {"threshold": 25, "hits": 2, "share": 50},
    "Flicker": {"dodge": 18},
    "Shadow Play": {"damage_cut": 20},
    "Ghostlight": {"bonus": 20},
    "Candle Count": {"every": 2, "strike": 80},
    "Hallowed Halls": {"turn": 5, "bonus": 25, "accuracy_cut": 25, "turns": 3},
    # Gourdling
    "Tendril": {"chance": 35, "damage_cut": 25, "turns": 2},
    "Ripening": {"per_stack": 6, "max": 30},
    "Gourd Toss": {"every": 3, "strike": 200, "splash": 50},
    "Overgrowth": {"damage": 30},
    "Great Pumpkin": {"stacks": 5, "strike": 3.5, "turns": 2},
    "Snack": {"heal": 4},
    "Harvest Feast": {"threshold": 40, "heal": 25},
    "Compost": {"heal": 4},
    "Cornucopia": {"threshold": 50, "stacks": 3, "heal": 15},
    "Bountiful": {"threshold": 30, "heal": 35, "regen": 10, "turns": 3},
    "Thick Rind": {"reduction": 15},
    "Scarecrow": {"chance": 20},
    "Root Down": {"bonus": 20, "stacks": 3},
    "Hollow Grin": {"accuracy_cut": 10, "turns": 2},
    "Harvest Moon": {"threshold": 25, "hp": 50, "turns": 2},
    # Frostfawn
    "Frost Chime": {"chance": 50, "chill": 1},
    "Cold Snap": {"bonus": 45},
    "Hoarfrost": {"per_stack": 5, "max": 15},
    "Shatter": {"bonus": 80},
    "Midwinter": {"freezes": 2, "threshold": 20, "strike": 2.5, "chill": 2},
    "Soft Snow": {"reduction": 24},
    "Snow Veil": {"dodge": 22},
    "Ice Glaze": {"shield": 200, "chill": 1},
    "Winter Coat": {"turns": 2},
    "Silent Night": {"threshold": 25, "turns": 1, "heal": 25},
    "Bell": {"bonus": 5},
    "Fawn's Leap": {},
    "Crystal Chime": {"heal": 5},
    "Northern Lights": {"bonus": 10, "turns": 2},
    "Feast Bells": {"turn": 6, "bonus": 20, "turns": 3, "chill": 1},
    # Hearthkit
    "Spark Pounce": {"chance": 30, "strike": 1.5},
    "Stoke": {"per_stack": 7, "max": 35},
    "Flare-up": {"chance": 30, "embers": 2},
    "Cinder Swipe": {"turns": 3, "burn": 25},
    "Yule Blaze": {"stacks": 5, "strike": 3.5, "turns": 3},
    "Banked Embers": {"shield": 6},
    "Warm Lap": {"heal": 1, "max": 3},
    "Rekindle": {"turn": 4, "shield": 8},
    "Kept Warm": {"stacks": 3, "hp": 1},
    "Home Fires": {"threshold": 25, "shield": 30, "heal": 20},
    "Snug": {"reduction": 15},
    "Catnap": {"embers": 2},
    "Purr": {"stacks": 3, "bonus": 5},
    "Ember Gift": {"shield": 3},
    "Midwinter Hearth": {"turn": 6, "bonus": 20, "turns": 3},
}

# Counters a tree keeps on the pet, with their cap.
ULTIMATE_CHAPTER = 5  # utils/library_pets.ULTIMATE_CHAPTER

COUNTER_CAP = {"Reedling": 5, "Gourdling": 5, "Hearthkit": 5}
COUNTER_NAME = {"Reedling": "Stillness", "Gourdling": "Harvest", "Hearthkit": "Embers"}

STANDARD_BURN_PCT = 15  # the Lanternling/Hearthkit/Echo burn: 15% of the pet's attack per turn
CHILL_TO_FREEZE = 3
CLEANSABLE = ("stunned", "paralyzed", "tidal_delayed", "burning")


def tree_for_species(species):
    return SPECIES_TREE_OF.get(str(species or "").strip())


def all_species_skill_names(tree_key):
    return [skill["name"] for branch in SPECIES_SKILL_TREES.get(tree_key, {}).values() for skill in branch.values()]


def is_night(now=None):
    """Night battles: 6 PM to 6 AM server time (Photosynthesis's day is 6 AM - 6 PM)."""
    hour = (now or datetime.datetime.now()).hour
    return hour < 6 or hour >= 18


def pct(value):
    return D(value) / D(100)


class SpeciesSkills:
    """Battle behaviour for the species trees. Stateless: all state lives on the combatants."""

    def __init__(self, ext):
        self.ext = ext

    # ------------------------------------------------------------------ setup / state
    def setup(self, pet, learned_skills):
        tree_key = getattr(pet, "species_tree", None)
        names = {name.lower(): name for name in all_species_skill_names(tree_key)}
        known = []
        for skill in learned_skills or []:
            name = names.get(str(skill).strip().lower())
            if name and name not in known:
                known.append(name)
        # Ultimates (level 10) open at evolution Chapter V; a pet built without a Chapter (tests, previews) keeps them.
        chapter = getattr(pet, "library_chapter", None)
        if chapter is not None and int(chapter) < ULTIMATE_CHAPTER:
            ultimates = {branch[10]["name"] for branch in SPECIES_SKILL_TREES.get(tree_key, {}).values()}
            known = [name for name in known if name not in ultimates]
        pet.species_skills = known
        pet.skill_effects = {self.slug(name): {"type": "species", "tree": tree_key, **SKILL_PARAMS[name]} for name in known}
        pet.passive_effects = []
        pet.active_abilities = []
        pet.sp_counter = 0
        pet.sp_turn = 0
        pet.sp_timed = []
        pet.sp_dots = []
        pet.sp_used = set()
        if self.has(pet, "Fawn's Leap"):
            pet.attack_priority = True

    @staticmethod
    def slug(name):
        return "species_" + "".join(c if c.isalnum() else "_" for c in name.lower()).strip("_")

    @staticmethod
    def has(pet, name):
        return name in (getattr(pet, "species_skills", None) or ())

    @staticmethod
    def p(name, key):
        return SKILL_PARAMS[name][key]

    def tree(self, pet):
        return getattr(pet, "species_tree", None)

    def owner(self, pet):
        return self.ext.find_owner_combatant(pet)

    @staticmethod
    def alive(team):
        return [c for c in getattr(team, "combatants", []) if c.is_alive()]

    def allies(self, pet):
        return self.alive(getattr(pet, "team", None))

    def enemies(self, pet):
        return self.alive(getattr(pet, "enemy_team", None))

    def once(self, pet, key):
        """True the first time `key` is claimed this battle."""
        if key in pet.sp_used:
            return False
        pet.sp_used.add(key)
        return True

    def tag(self, pet):
        return f"{getattr(pet, 'pet_id', None) or id(pet)}"

    def gain(self, pet, amount):
        cap = COUNTER_CAP.get(self.tree(pet))
        if cap:
            pet.sp_counter = max(0, min(cap, int(pet.sp_counter) + int(amount)))

    # ------------------------------------------------------------------ shared effects
    def timed(self, pet, target, key, turns, *, damage=1, armor=1, luck=1):
        """A stat multiplier this pet ticks down on its own turns (and clears if it falls)."""
        full_key = f"sp_{key}_{self.tag(pet)}"
        self.ext._apply_timed_multiplier(target, full_key, turns, damage_mult=damage, armor_mult=armor, luck_mult=luck)
        if not any(t is target and k == full_key for t, k in pet.sp_timed):
            pet.sp_timed.append((target, full_key))

    def has_timed(self, pet, target, key):
        return int(getattr(target, f"sp_{key}_{self.tag(pet)}_duration", 0) or 0) > 0

    def clear_timed(self, pet, target, key):
        full_key = f"sp_{key}_{self.tag(pet)}"
        self.ext._clear_timed_multiplier(target, full_key)
        pet.sp_timed = [(t, k) for t, k in pet.sp_timed if not (t is target and k == full_key)]

    def aura(self, pet, targets, key, *, damage=1, armor=1, luck=1):
        """A buff that lasts while its condition holds: refreshed each turn, gone a turn after it stops."""
        for target in targets:
            self.timed(pet, target, key, 2, damage=damage, armor=armor, luck=luck)

    def burn(self, pet, target, turns, share=STANDARD_BURN_PCT, label="burns"):
        per_turn = D(pet.damage) * pct(share)
        for dot in pet.sp_dots:
            if dot["target"] is target and dot["label"] == label:
                dot["turns"] = max(dot["turns"], int(turns))
                dot["per_turn"] = max(dot["per_turn"], per_turn)
                return
        pet.sp_dots.append({"target": target, "turns": int(turns), "per_turn": per_turn, "label": label})

    def heal(self, pet, target, share, *, burst=False):
        if not self.ext._can_heal(target):
            return D(0)
        amount = self.ext._scaled_heal(pet, target, pct(share), burst=burst, self_target=target is pet)
        target.heal(amount)
        return amount

    def shield(self, target, amount):
        target.shield = D(getattr(target, "shield", 0) or 0) + D(amount)

    def strike(self, pet, target, amount):
        return self.ext._deal_damage(pet, target, D(amount))

    @staticmethod
    def lose_turn(target, turns=1):
        target.tidal_delayed = max(int(getattr(target, "tidal_delayed", 0) or 0), int(turns))

    @staticmethod
    def stun(target, turns=1):
        target.stunned = max(int(getattr(target, "stunned", 0) or 0), int(turns))

    @staticmethod
    def cleanse(target):
        cleared = [name for name in CLEANSABLE if int(getattr(target, name, 0) or 0) > 0]
        for name in cleared:
            delattr(target, name)
        return cleared

    @staticmethod
    def hp_ratio(combatant):
        max_hp = D(getattr(combatant, "max_hp", 0) or 0)
        return D(combatant.hp) / max_hp if max_hp > 0 else D(0)

    # ------------------------------------------------------------------ marks (Inkwyrm)
    def marked(self, pet, target):
        return int(getattr(target, f"sp_mark_{self.tag(pet)}", 0) or 0) > 0

    def mark(self, pet, target, turns, messages):
        key = f"sp_mark_{self.tag(pet)}"
        fresh = not self.marked(pet, target)
        setattr(target, key, max(int(getattr(target, key, 0) or 0), int(turns)))
        if fresh:
            pet.sp_marks_made = int(getattr(pet, "sp_marks_made", 0) or 0) + 1
            messages.append(f"🖋️ {pet.name} marks **{target.name}**!")
            owner = self.owner(pet)
            if self.has(pet, "Margin Notes") and owner is not None and owner.is_alive():
                self.timed(pet, owner, "margin_notes", self.p("Margin Notes", "turns"),
                           damage=1 + pct(self.p("Margin Notes", "bonus")))
        self.timed(pet, target, "mark_armor", turns, armor=1 - pct(self.p("Ink Blot", "armor_cut")))
        if self.has(pet, "Redact"):
            self.timed(pet, target, "redact", turns, damage=1 - pct(self.p("Redact", "damage_cut")))
        if self.has(pet, "Smudge"):
            self.timed(pet, target, "smudge", turns, luck=1 - pct(self.p("Smudge", "accuracy_cut")))

    def marked_enemies(self, pet):
        return [e for e in self.enemies(pet) if self.marked(pet, e)]

    # ------------------------------------------------------------------ chill (Frostfawn)
    def chill(self, pet, target, amount, messages):
        key = f"sp_chill_{self.tag(pet)}"
        stacks = int(getattr(target, key, 0) or 0) + int(amount)
        if stacks >= CHILL_TO_FREEZE:
            setattr(target, key, 0)
            self.clear_timed(pet, target, "hoarfrost")
            self.freeze(pet, target, messages)
            return
        setattr(target, key, stacks)
        if self.has(pet, "Hoarfrost"):
            cut = min(D(self.p("Hoarfrost", "max")), D(self.p("Hoarfrost", "per_stack")) * stacks)
            self.clear_timed(pet, target, "hoarfrost")
            self.timed(pet, target, "hoarfrost", 99, luck=1 - pct(cut))
        messages.append(f"❄️ **{target.name}** is chilled ({stacks}/{CHILL_TO_FREEZE}).")

    def chill_of(self, pet, target):
        return int(getattr(target, f"sp_chill_{self.tag(pet)}", 0) or 0)

    def frozen(self, pet, target):
        return bool(getattr(target, f"sp_frozen_{self.tag(pet)}", False)) and int(getattr(target, "stunned", 0) or 0) > 0

    def freeze(self, pet, target, messages):
        self.stun(target, 1)
        setattr(target, f"sp_frozen_{self.tag(pet)}", True)
        pet.sp_freezes = int(getattr(pet, "sp_freezes", 0) or 0) + 1
        messages.append(f"🧊 **{target.name}** freezes solid!")
        if self.has(pet, "Crystal Chime"):
            for ally in self.allies(pet):
                self.heal(pet, ally, self.p("Crystal Chime", "heal"))
            messages.append(f"🔔 {pet.name}'s Crystal Chime heals the team!")
        if self.has(pet, "Northern Lights"):
            bonus = 1 + pct(self.p("Northern Lights", "bonus"))
            for ally in self.allies(pet):
                self.timed(pet, ally, "northern_lights", self.p("Northern Lights", "turns"), damage=bonus, armor=bonus, luck=bonus)
            messages.append(f"🌌 Northern Lights shimmer over {pet.name}'s team!")

    # ------------------------------------------------------------------ hooks
    def on_attack(self, pet, target, damage):
        damage = D(damage)
        messages = []
        handler = getattr(self, f"_attack_{(self.tree(pet) or '').lower()}", None)
        if handler:
            damage = handler(pet, target, damage, messages)
        pet.sp_attacks = int(getattr(pet, "sp_attacks", 0) or 0) + 1
        if getattr(pet, "attack_priority", False) and self.has(pet, "Fawn's Leap"):
            delattr(pet, "attack_priority")
        return damage, messages

    def on_damage_taken(self, pet, attacker, damage):
        damage = D(damage)
        messages = []
        if int(getattr(pet, "divine_invincibility", 0) or 0) > 0:
            return D(0), [f"{pet.name} cannot be harmed right now!"]
        handler = getattr(self, f"_hit_{(self.tree(pet) or '').lower()}", None)
        if handler:
            damage = handler(pet, attacker, damage, messages)
        if damage > 0 and self.has(pet, "Last Light") and damage >= D(pet.hp) and self.once(pet, "last_light"):
            damage = max(D(0), D(pet.hp) - D(1))
            messages.append(f"🏮 {pet.name}'s Last Light flickers but holds!")
        return damage, messages

    def per_turn(self, pet):
        messages = []
        pet.sp_turn = int(getattr(pet, "sp_turn", 0) or 0) + 1
        self._tick(pet, messages)
        handler = getattr(self, f"_turn_{(self.tree(pet) or '').lower()}", None)
        if handler:
            handler(pet, messages)
        return messages

    def guard(self, pet, attacker, target, damage):
        """An attack is about to land on a non-pet ally. Returns (damage, messages, redirected_to)."""
        damage = D(damage)
        handler = getattr(self, f"_guard_{(self.tree(pet) or '').lower()}", None)
        if damage <= 0 or handler is None or not pet.is_alive():
            return damage, [], None
        messages = []
        result = handler(pet, attacker, target, damage, messages)
        if isinstance(result, tuple):
            return result[0], messages, result[1]
        return result, messages, None

    def on_death(self, pet):
        for target, key in list(getattr(pet, "sp_timed", [])):
            self.ext._clear_timed_multiplier(target, key)
        pet.sp_timed = []
        pet.sp_dots = []
        for enemy in getattr(getattr(pet, "enemy_team", None), "combatants", []) or []:
            for attr in (f"sp_mark_{self.tag(pet)}", f"sp_chill_{self.tag(pet)}", f"sp_frozen_{self.tag(pet)}"):
                if hasattr(enemy, attr):
                    delattr(enemy, attr)
        return []

    def _tick(self, pet, messages):
        """Turn start: timed effects, burns, marks and freezes this pet put on others."""
        for target, key in list(pet.sp_timed):
            self.ext._tick_timed_multiplier(target, key, messages)
            if not hasattr(target, f"{key}_duration"):
                pet.sp_timed = [(t, k) for t, k in pet.sp_timed if not (t is target and k == key)]
        for dot in list(pet.sp_dots):
            target = dot["target"]
            if dot["turns"] <= 0 or not target.is_alive():
                pet.sp_dots.remove(dot)
                continue
            dealt = self.strike(pet, target, dot["per_turn"])
            messages.append(f"🔥 **{target.name}** {dot['label']} for **{D(dealt or dot['per_turn']):.2f}** damage!")
            dot["turns"] -= 1
            if dot["turns"] <= 0:
                pet.sp_dots.remove(dot)
        tag = self.tag(pet)
        for enemy in getattr(getattr(pet, "enemy_team", None), "combatants", []) or []:
            mark_key = f"sp_mark_{tag}"
            turns = int(getattr(enemy, mark_key, 0) or 0)
            if turns > 1:
                setattr(enemy, mark_key, turns - 1)
            elif turns == 1:
                delattr(enemy, mark_key)
            frozen_key = f"sp_frozen_{tag}"
            if getattr(enemy, frozen_key, False) and int(getattr(enemy, "stunned", 0) or 0) <= 0:
                delattr(enemy, frozen_key)
        owner = self.owner(pet)
        for combatant in [owner] if owner is not None else []:
            if getattr(combatant, "sp_invincible_by", None) == tag:
                left = int(getattr(combatant, "divine_invincibility", 0) or 0) - 1
                if left > 0:
                    combatant.divine_invincibility = left
                else:
                    for attr in ("divine_invincibility", "sp_invincible_by"):
                        if hasattr(combatant, attr):
                            delattr(combatant, attr)
                    messages.append(f"{combatant.name} can be hurt again.")

    def _dodge(self, pet, attacker, damage, chance, label, messages):
        if chance > 0 and random.random() * 100 < chance:
            pet.sp_dodges = int(getattr(pet, "sp_dodges", 0) or 0) + 1
            messages.append(f"💨 {pet.name} dodges with {label}!")
            return True
        return False

    def _other_enemy(self, pet, target):
        others = [e for e in self.enemies(pet) if e is not target]
        return random.choice(others) if others else None

    # ================================================================== Inkwyrm
    def _attack_inkwyrm(self, pet, target, damage, messages):
        if self.has(pet, "Ink Blot") and random.random() * 100 < self.p("Ink Blot", "chance"):
            self.mark(pet, target, self.p("Ink Blot", "turns"), messages)
        marked = self.marked(pet, target)
        if marked and self.has(pet, "Underline"):
            damage *= 1 + pct(self.p("Underline", "bonus"))
        if self.has(pet, "Late Reading"):
            bonus = min(self.p("Late Reading", "max"), self.p("Late Reading", "per_mark") * len(self.marked_enemies(pet)))
            if bonus:
                damage *= 1 + pct(bonus)
        if marked and self.has(pet, "Footnote"):
            follow = damage * pct(self.p("Footnote", "share"))
            self.strike(pet, target, follow)
            messages.append(f"🖋️ Footnote! {pet.name} strikes **{target.name}** again for **{follow:.2f}**.")
        if marked and self.has(pet, "Blotted Page") and random.random() * 100 < self.p("Blotted Page", "chance"):
            self.lose_turn(target)
            messages.append(f"📄 Blotted Page! **{target.name}** loses its next turn.")
        return damage

    def _hit_inkwyrm(self, pet, attacker, damage, messages):
        if self.has(pet, "Inkshadow") and self._dodge(pet, attacker, damage, self.p("Inkshadow", "dodge"), "Inkshadow", messages):
            if attacker is not None and attacker.is_alive() and attacker in self.enemies(pet):
                self.mark(pet, attacker, self.p("Ink Blot", "turns"), messages)
            return D(0)
        return damage

    def _turn_inkwyrm(self, pet, messages):
        owner = self.owner(pet)
        marked = self.marked_enemies(pet)
        if self.has(pet, "Annotated Edition") and marked:
            bonus = 1 + pct(self.p("Annotated Edition", "bonus"))
            self.aura(pet, self.allies(pet), "annotated", damage=bonus, armor=bonus)
        if owner is not None and owner.is_alive() and self.has(pet, "Bookmark"):
            if self.hp_ratio(owner) < pct(self.p("Bookmark", "threshold")) and self.once(pet, "bookmark_set"):
                pet.sp_bookmark = self.p("Bookmark", "delay") + 1
            if int(getattr(pet, "sp_bookmark", 0) or 0) > 0:
                pet.sp_bookmark -= 1
                if pet.sp_bookmark == 0:
                    healed = self.heal(pet, owner, self.p("Bookmark", "heal"), burst=True)
                    messages.append(f"🔖 Bookmark! **{owner.name}** recovers **{healed:.2f} HP**.")
        if self.has(pet, "Final Chapter") and int(getattr(pet, "sp_marks_made", 0) or 0) >= self.p("Final Chapter", "marks") and marked \
                and self.once(pet, "Final Chapter"):
            for enemy in marked:
                self.strike(pet, enemy, D(pet.damage) * D(self.p("Final Chapter", "strike")))
                self.strike(pet, enemy, D(pet.damage) * pct(self.p("Final Chapter", "burst")))
            messages.append(f"📕 **Final Chapter!** {pet.name} writes the ending: {len(marked)} marked enemies are struck and their marks burst!")
        if self.has(pet, "Library Lock") and self.hp_ratio(pet) < pct(self.p("Library Lock", "threshold")) and self.once(pet, "Library Lock"):
            for enemy in self.enemies(pet):
                self.mark(pet, enemy, self.p("Library Lock", "turns"), messages)
                self.lose_turn(enemy)
            messages.append(f"🔒 **Library Lock!** {pet.name} shuts the book: every enemy is marked and loses its next turn!")

    def _guard_inkwyrm(self, pet, attacker, target, damage, messages):
        owner = self.owner(pet)
        if target is not owner:
            return damage
        after = D(target.hp) - damage
        if self.has(pet, "Rewrite") and after < D(target.max_hp) * pct(self.p("Rewrite", "threshold")) \
                and self.once(pet, "Rewrite"):
            target.damage_inverted = max(int(getattr(target, "damage_inverted", 0) or 0), self.p("Rewrite", "hits"))
            messages.append(f"✒️ **Rewrite!** {pet.name} rewrites the page: the next {self.p('Rewrite', 'hits')} hits on **{target.name}** heal them instead!")
            return damage
        if self.has(pet, "Errata") and after < D(target.max_hp) * pct(self.p("Errata", "threshold")):
            damage = damage * (1 - pct(self.p("Errata", "reduction")))
            messages.append(f"📝 Errata! {pet.name} corrects the blow on **{target.name}**.")
        return damage

    # ================================================================== Reedling
    def _attack_reedling(self, pet, target, damage, messages):
        stacks = int(pet.sp_counter)
        if self.has(pet, "Old One of the Reeds") and getattr(pet, "sp_reeds_ready", False):
            pet.sp_reeds_ready = False
            damage *= D(self.p("Old One of the Reeds", "strike"))
            self.stun(target, self.p("Old One of the Reeds", "stun"))
            messages.append(f"🐊 **The Old One of the Reeds** rises! **{target.name}** is struck and stunned!")
        if self.has(pet, "Floodgate") and stacks >= self.p("Floodgate", "stacks") and self.once(pet, "Floodgate"):
            pet.sp_counter = 0
            damage *= D(self.p("Floodgate", "strike"))
            for enemy in self.enemies(pet):
                self.lose_turn(enemy)
            messages.append(f"🌊 **Floodgate!** {pet.name} releases its Stillness: every enemy is swept off its feet!")
            return damage
        if self.has(pet, "Undertow") and stacks:
            damage *= 1 + pct(min(self.p("Undertow", "max"), self.p("Undertow", "per_stack") * stacks))
        if self.has(pet, "Reed Lance") and self.once(pet, "reed_lance"):
            target.ignore_armor_this_hit = True
            messages.append(f"🎋 Reed Lance slips past **{target.name}**'s armor!")
        if self.has(pet, "Drag Under"):
            if pet.sp_counter >= self.p("Drag Under", "stacks"):
                pet.sp_counter -= self.p("Drag Under", "stacks")
                self.lose_turn(target)
                messages.append(f"🌀 Drag Under! **{target.name}** is pulled down and loses its next turn.")
            elif random.random() * 100 < self.p("Drag Under", "chance"):
                self.lose_turn(target)
                messages.append(f"🌀 Drag Under! **{target.name}** loses its next turn.")
        if self.has(pet, "Riptide"):
            other = self._other_enemy(pet, target)
            if other is not None:
                share = self.p("Riptide", "full_share") if pet.sp_counter >= self.p("Riptide", "full_stacks") else self.p("Riptide", "share")
                self.strike(pet, other, damage * pct(share))
                messages.append(f"🌊 Riptide drags **{other.name}** in for {share}% of the hit.")
        return damage

    def _hit_reedling(self, pet, attacker, damage, messages):
        lurking = self.has(pet, "Lurk") and pet.sp_turn <= self.p("Lurk", "turns")
        chance = 100 if lurking else (self.p("Reed Cover", "dodge") if self.has(pet, "Reed Cover") else 0)
        if self._dodge(pet, attacker, damage, chance, "Lurk" if lurking else "Reed Cover", messages):
            if self.has(pet, "Murk") and attacker is not None and attacker.is_alive():
                self.timed(pet, attacker, "murk", self.p("Murk", "turns"), luck=1 - pct(self.p("Murk", "accuracy_cut")))
            if self.has(pet, "Old One of the Reeds") and int(getattr(pet, "sp_dodges", 0) or 0) >= self.p("Old One of the Reeds", "dodges") \
                    and self.once(pet, "Old One of the Reeds"):
                pet.sp_reeds_ready = True
                messages.append(f"🐊 Something ancient stirs in the reeds around {pet.name}...")
            return D(0)
        if damage > 0:
            pet.sp_hit_since_turn = True
            loss = self.p("Deep Calm", "loss") if self.has(pet, "Deep Calm") else self.p("Deep Calm", "normal_loss")
            pet.sp_counter = max(0, int(pet.sp_counter) - loss)
        return damage

    def _turn_reedling(self, pet, messages):
        before = int(pet.sp_counter)
        if not getattr(pet, "sp_hit_since_turn", False) and pet.sp_turn > 1:
            self.gain(pet, 1)
        pet.sp_hit_since_turn = False
        pet.sp_ripple_used = False
        owner = self.owner(pet)
        if owner is not None and owner.is_alive():
            if self.has(pet, "Clear Pool") and pet.sp_counter >= self.p("Clear Pool", "stacks"):
                healed = self.heal(pet, owner, self.p("Clear Pool", "heal"))
                if healed:
                    messages.append(f"🪷 Clear Pool soothes **{owner.name}** for **{healed:.2f} HP**.")
            if self.has(pet, "Mirror Lake") and self.hp_ratio(owner) < pct(self.p("Mirror Lake", "threshold")) and self.once(pet, "Mirror Lake"):
                pet.sp_mirror = self.p("Mirror Lake", "turns") + 1
                messages.append(f"🪞 **Mirror Lake!** The water around **{owner.name}** turns to glass.")
        if int(getattr(pet, "sp_mirror", 0) or 0) > 0:
            pet.sp_mirror -= 1
        if pet.sp_counter > before:
            messages.append(f"🪷 {pet.name} grows still ({pet.sp_counter}/5 Stillness).")

    def _guard_reedling(self, pet, attacker, target, damage, messages):
        owner = self.owner(pet)
        if self.has(pet, "Marsh Mist") and pet.sp_turn <= self.p("Marsh Mist", "turns") \
                and random.random() * 100 < self.p("Marsh Mist", "dodge"):
            messages.append(f"🌫️ Marsh Mist hides **{target.name}** from the blow!")
            return D(0)
        if target is not owner:
            return damage
        if int(getattr(pet, "sp_mirror", 0) or 0) > 0:
            reflected = damage * pct(self.p("Mirror Lake", "reflect"))
            damage = damage * (1 - pct(self.p("Mirror Lake", "reduction")))
            if attacker is not None and attacker.is_alive():
                self.strike(pet, attacker, reflected)
            messages.append(f"🪞 Mirror Lake halves the blow and throws **{reflected:.2f}** back!")
        if self.has(pet, "Still Water") and self.once(pet, "still_water"):
            absorbed = min(damage, D(target.max_hp) * pct(self.p("Still Water", "cap")))
            damage -= absorbed
            messages.append(f"💧 Still Water absorbs **{absorbed:.2f}** of the hit on **{target.name}**.")
        if self.has(pet, "Ripple Ward") and not getattr(pet, "sp_ripple_used", False) and damage > 0:
            pet.sp_ripple_used = True
            ward = damage * pct(self.p("Ripple Ward", "share"))
            self.shield(target, ward)
            messages.append(f"〰️ Ripple Ward turns the blow into a **{ward:.2f}** shield on **{target.name}**.")
        return damage

    # ================================================================== Soulgem whelps
    def _attack_soulgem(self, pet, target, damage, messages):
        if self.has(pet, "Dragonbane") and dragonkin.is_dragon(target):
            damage *= 1 + pct(self.p("Dragonbane", "bonus"))
        if self.has(pet, "Glint") and random.random() * 100 < self.p("Glint", "chance"):
            damage *= D(self.p("Glint", "crit"))
            if self.has(pet, "Facet Strike"):
                damage *= 1 + pct(self.p("Facet Strike", "bonus"))
            pet.sp_crits = int(getattr(pet, "sp_crits", 0) or 0) + 1
            messages.append(f"💎 {pet.name} glints: a critical hit!")
            if self.has(pet, "Prism Split"):
                other = self._other_enemy(pet, target)
                if other is not None:
                    self.strike(pet, other, damage * pct(self.p("Prism Split", "share")))
                    messages.append(f"🌈 Prism Split refracts onto **{other.name}**!")
        return damage

    def _hit_soulgem(self, pet, attacker, damage, messages):
        if self.has(pet, "Gem Ward"):
            element = getattr(attacker, "attack_element", None) or getattr(attacker, "element", None)
            own = str(element or "").lower() == str(getattr(pet, "element", "")).lower()
            damage *= 1 - pct(self.p("Gem Ward", "own" if own else "other"))
        if self.has(pet, "Facet Armor") and damage > 0:
            stacks = int(getattr(pet, "sp_facets", 0) or 0)
            cap = self.p("Facet Armor", "max") // self.p("Facet Armor", "per_hit")
            if stacks < cap:
                before = 1 + pct(self.p("Facet Armor", "per_hit") * stacks)
                after = 1 + pct(self.p("Facet Armor", "per_hit") * (stacks + 1))
                pet.armor = D(pet.armor) / before * after
                pet.sp_facets = stacks + 1
        return damage

    def _turn_soulgem(self, pet, messages):
        allies = self.allies(pet)
        if pet.sp_turn == 1:
            if self.has(pet, "Hum"):
                for ally in allies:
                    self.timed(pet, ally, "hum", 999, damage=1 + pct(self.p("Hum", "bonus")))
            if self.has(pet, "Harmonic"):
                element = str(getattr(pet, "element", "")).lower()
                for ally in allies:
                    if ally is not pet and str(getattr(ally, "element", "")).lower() == element:
                        self.timed(pet, ally, "harmonic", 999, damage=1 + pct(self.p("Harmonic", "bonus")))
        if self.has(pet, "Chorus"):
            elements = {
                str(getattr(ally, "element", "")).lower() for ally in allies
                if getattr(ally, "species_tree", None) == "Soulgem"
            }
            bonus = 1 + pct(min(self.p("Chorus", "max"), self.p("Chorus", "per_element") * len(elements)))
            self.aura(pet, allies, "chorus", damage=bonus, armor=bonus)
        if self.has(pet, "Seven Lights"):
            for ally in allies:
                cleared = self.cleanse(ally)
                if cleared:
                    messages.append(f"✨ Seven Lights clear {', '.join(cleared)} from **{ally.name}**.")
                    break
        owner = self.owner(pet)
        clutch_ready = pet.sp_turn >= int(getattr(pet, "sp_clutch_ready", 0) or 0)
        if owner is not None and owner.is_alive() and self.has(pet, "Clutch Instinct") and clutch_ready \
                and self.hp_ratio(owner) < pct(self.p("Clutch Instinct", "threshold")):
            pet.sp_clutch_ready = pet.sp_turn + self.p("Clutch Instinct", "cooldown")
            amount = D(owner.max_hp) * pct(self.p("Clutch Instinct", "shield"))
            self.shield(owner, amount)
            messages.append(f"🥚 Clutch Instinct! {pet.name} shields **{owner.name}** for **{amount:.2f}**.")
        if self.has(pet, "The Hall Awakens") and pet.sp_turn == self.p("The Hall Awakens", "turn") and self.once(pet, "The Hall Awakens"):
            bonus = 1 + pct(self.p("The Hall Awakens", "bonus"))
            for ally in allies:
                self.timed(pet, ally, "hall_awakens", self.p("The Hall Awakens", "turns"), damage=bonus, armor=bonus, luck=bonus)
            messages.append(f"🏛️ **The Hall Awakens!** The Great Seven's statues glow behind {pet.name}'s team!")
        if self.has(pet, "Echo of the Seven") and int(getattr(pet, "sp_crits", 0) or 0) >= self.p("Echo of the Seven", "crits") \
                and self.once(pet, "Echo of the Seven"):
            self._echo(pet, messages)

    def _echo(self, pet, messages):
        element = str(getattr(pet, "element", "") or "").capitalize()
        enemies = self.enemies(pet)
        total = D(0)
        for enemy in enemies:
            total += D(self.strike(pet, enemy, D(pet.damage) * D(self.p("Echo of the Seven", "strike"))) or 0)
        gift = ""
        if element == "Fire":
            for enemy in enemies:
                self.burn(pet, enemy, 3)
            gift = "the foes burn"
        elif element == "Water":
            for ally in self.allies(pet):
                self.heal(pet, ally, self.p("Echo of the Seven", "heal"), burst=True)
            gift = "the team is healed"
        elif element == "Nature":
            for enemy in enemies:
                self.timed(pet, enemy, "echo_entangle", 2, damage=1 - pct(self.p("Tendril", "damage_cut")))
            gift = "the foes are entangled"
        elif element == "Light":
            for ally in self.allies(pet):
                self.cleanse(ally)
            gift = "the team is cleansed"
        elif element == "Dark":
            self.heal(pet, pet, D(30), burst=True)
            gift = "it drinks in the darkness"
        elif element in ("Wind", "Electric"):
            for enemy in enemies:
                self.lose_turn(enemy)
            gift = "every foe loses its next turn"
        elif element == "Corrupted":
            for enemy in enemies:
                self.timed(pet, enemy, "echo_crack", 3, armor=D("0.85"))
            gift = "the foes' armor cracks"
        messages.append(f"🐉 **Echo of the Seven!** A Great Seven's echo answers {pet.name}" + (f", and {gift}!" if gift else "!"))

    def _guard_soulgem(self, pet, attacker, target, damage, messages):
        owner = self.owner(pet)
        if self.has(pet, "Bloodline") and owner is not None and (
            getattr(owner, "dragonkin", False) or int(getattr(owner, "breathcaller_evolution", 0) or 0) > 0
        ):
            damage *= 1 - pct(self.p("Bloodline", "reduction"))
        if target is owner and self.has(pet, "Sacrament") and damage >= D(target.hp) + D(getattr(target, "shield", 0) or 0) \
                and self.once(pet, "Sacrament"):
            target.hp = D(self.p("Sacrament", "hp"))
            healed = self.heal(pet, target, self.p("Sacrament", "heal"), burst=True)
            target.divine_invincibility = max(int(getattr(target, "divine_invincibility", 0) or 0), self.p("Sacrament", "turns") + 1)
            target.sp_invincible_by = self.tag(pet)
            messages.append(f"🕊️ **Sacrament!** {pet.name}'s soul gem blazes: **{target.name}** survives, heals **{healed:.2f} HP** and cannot be hurt this turn!")
            return D(0)
        return damage

    # ================================================================== Lanternling
    def _attack_lanternling(self, pet, target, damage, messages):
        night = is_night()
        if self.has(pet, "Kindle"):
            damage *= 1 + pct(self.p("Kindle", "night" if night else "day"))
        blinded = self.has_timed(pet, target, "blind")
        if self.has(pet, "Ghostlight") and blinded:
            damage *= 1 + pct(self.p("Ghostlight", "bonus"))
        if self.has(pet, "Lure") and self.once(pet, "lure"):
            self.timed(pet, target, "blind", self.p("Lure", "turns"), luck=1 - pct(self.p("Lure", "accuracy_cut")))
            messages.append(f"🏮 {pet.name}'s Lure dazzles **{target.name}**!")
        if self.has(pet, "Burns Late") and night:
            self.burn(pet, target, self.p("Burns Late", "turns"), self.p("Burns Late", "burn"))
        if self.has(pet, "Will-o'-Wisp") and random.random() * 100 < self.p("Will-o'-Wisp", "chance"):
            other = self._other_enemy(pet, target) or target
            self.strike(pet, other, damage * pct(self.p("Will-o'-Wisp", "share")))
            self.burn(pet, other, 3)
            messages.append(f"👻 A will-o'-wisp drifts into **{other.name}** and sets it alight!")
        return damage

    def _hit_lanternling(self, pet, attacker, damage, messages):
        if self.has(pet, "Flicker") and self._dodge(pet, attacker, damage, self.p("Flicker", "dodge"), "Flicker", messages):
            return D(0)
        return damage

    def _turn_lanternling(self, pet, messages):
        night = is_night()
        enemies = self.enemies(pet)
        allies = self.allies(pet)
        if pet.sp_turn == 1 and self.has(pet, "Lantern Shell"):
            amount = D(pet.armor) * pct(self.p("Lantern Shell", "night_shield" if night else "shield"))
            self.shield(pet, amount)
            messages.append(f"🏮 {pet.name} glows inside a Lantern Shell (**{amount:.2f}** shield).")
        if self.has(pet, "Shadow Play") and night:
            self.aura(pet, enemies, "shadow_play", damage=1 - pct(self.p("Shadow Play", "damage_cut")))
        if self.has(pet, "Candle Count") and pet.sp_turn % self.p("Candle Count", "every") == 0 and enemies:
            target = random.choice(enemies)
            self.strike(pet, target, D(pet.damage) * pct(self.p("Candle Count", "strike")))
            messages.append(f"🕯️ Candle Count! A spare flame strikes **{target.name}**.")
        if self.has(pet, "Hallowed Halls") and pet.sp_turn == self.p("Hallowed Halls", "turn") and self.once(pet, "Hallowed Halls"):
            for ally in allies:
                self.timed(pet, ally, "hallowed_halls", self.p("Hallowed Halls", "turns"), damage=1 + pct(self.p("Hallowed Halls", "bonus")))
            for enemy in enemies:
                self.timed(pet, enemy, "hallowed_halls_dim", self.p("Hallowed Halls", "turns"),
                           luck=1 - pct(self.p("Hallowed Halls", "accuracy_cut")))
            messages.append(f"🎃 **Hallowed Halls!** Lanterns light along the walls around {pet.name}'s team!")
        flame_ready = (night and pet.sp_turn >= self.p("Hallow's Flame", "turn")) or \
            (not night and self.hp_ratio(pet) < pct(self.p("Hallow's Flame", "threshold")))
        if self.has(pet, "Hallow's Flame") and flame_ready and enemies and self.once(pet, "Hallow's Flame"):
            for enemy in enemies:
                self.strike(pet, enemy, D(pet.damage) * D(self.p("Hallow's Flame", "strike")))
                self.timed(pet, enemy, "blind", self.p("Lure", "turns"), luck=1 - pct(self.p("Lure", "accuracy_cut")))
            messages.append(f"🔥 **Hallow's Flame!** {pet.name} flares and every enemy is scorched and dazzled!")
        owner = self.owner(pet)
        if self.has(pet, "Vigil") and owner is not None and owner.is_alive() \
                and self.hp_ratio(owner) < pct(self.p("Vigil", "threshold")) and self.once(pet, "Vigil"):
            pet.sp_vigil = self.p("Vigil", "hits")
            messages.append(f"🏮 **Vigil!** {pet.name} stands watch over **{owner.name}**.")

    def _guard_lanternling(self, pet, attacker, target, damage, messages):
        owner = self.owner(pet)
        if target is not owner:
            return damage
        if int(getattr(pet, "sp_vigil", 0) or 0) > 0:
            pet.sp_vigil -= 1
            taken = damage * pct(self.p("Vigil", "share"))
            self.ext._deal_damage(attacker, pet, taken)
            messages.append(f"🏮 {pet.name} takes the blow for **{target.name}** (**{taken:.2f}**)!")
            return D(0), pet
        nightlight = self.p("Nightlight", "dodge" if is_night() else "day_dodge")
        if self.has(pet, "Nightlight") and random.random() * 100 < nightlight:
            messages.append(f"🌙 Nightlight guides **{target.name}** out of the way!")
            return D(0)
        if self.has(pet, "Safe Path") and self.hp_ratio(pet) > pct(self.p("Safe Path", "threshold")):
            damage *= 1 - pct(self.p("Safe Path", "reduction"))
        return damage

    # ================================================================== Gourdling
    def _entangle(self, pet, target, turns):
        self.timed(pet, target, "entangle", turns, damage=1 - pct(self.p("Tendril", "damage_cut")))

    def _attack_gourdling(self, pet, target, damage, messages):
        if self.has(pet, "Great Pumpkin") and pet.sp_counter >= self.p("Great Pumpkin", "stacks") and self.once(pet, "Great Pumpkin"):
            pet.sp_counter = 0
            damage *= D(self.p("Great Pumpkin", "strike"))
            for enemy in self.enemies(pet):
                self._entangle(pet, enemy, self.p("Great Pumpkin", "turns"))
            messages.append(f"🎃 **Great Pumpkin!** {pet.name} brings down the harvest and vines take every enemy!")
            return damage
        if self.has(pet, "Ripening") and pet.sp_counter:
            damage *= 1 + pct(min(self.p("Ripening", "max"), self.p("Ripening", "per_stack") * pet.sp_counter))
        if self.has(pet, "Gourd Toss") and (int(getattr(pet, "sp_attacks", 0) or 0) + 1) % self.p("Gourd Toss", "every") == 0:
            damage *= pct(self.p("Gourd Toss", "strike"))
            splash = damage * pct(self.p("Gourd Toss", "splash"))
            for enemy in self.enemies(pet):
                if enemy is not target:
                    self.strike(pet, enemy, splash)
            messages.append(f"🎃 Gourd Toss! The gourd bursts over **{target.name}** and splashes the rest.")
        if self.has(pet, "Tendril") and random.random() * 100 < self.p("Tendril", "chance"):
            self._entangle(pet, target, self.p("Tendril", "turns"))
            messages.append(f"🌿 Tendrils wrap **{target.name}**!")
        return damage

    def _hit_gourdling(self, pet, attacker, damage, messages):
        if self.has(pet, "Thick Rind"):
            damage *= 1 - pct(self.p("Thick Rind", "reduction"))
        if damage > 0 and not getattr(pet, "sp_hit_this_turn", False):
            pet.sp_hit_this_turn = True
            self.gain(pet, 1)
            if self.has(pet, "Compost"):
                healed = self.heal(pet, pet, self.p("Compost", "heal"))
                if healed:
                    messages.append(f"🍂 Compost: {pet.name} heals **{healed:.2f} HP**.")
        if self.has(pet, "Hollow Grin") and attacker is not None and attacker.is_alive():
            self.timed(pet, attacker, "hollow_grin", self.p("Hollow Grin", "turns"), luck=1 - pct(self.p("Hollow Grin", "accuracy_cut")))
        return damage

    def _turn_gourdling(self, pet, messages):
        self.gain(pet, 1)
        pet.sp_hit_this_turn = False
        allies = self.allies(pet)
        if self.has(pet, "Root Down"):
            if pet.sp_counter >= self.p("Root Down", "stacks"):
                self.aura(pet, [pet], "root_down", armor=1 + pct(self.p("Root Down", "bonus")))
        if self.has(pet, "Overgrowth"):
            for enemy in self.enemies(pet):
                if self.has_timed(pet, enemy, "entangle"):
                    self.strike(pet, enemy, D(pet.damage) * pct(self.p("Overgrowth", "damage")))
                    messages.append(f"🌱 Overgrowth chokes **{enemy.name}**.")
        owner = self.owner(pet)
        if owner is not None and owner.is_alive():
            if self.has(pet, "Snack"):
                self.heal(pet, owner, self.p("Snack", "heal"))
            ratio = self.hp_ratio(owner)
            if self.has(pet, "Harvest Feast") and ratio < pct(self.p("Harvest Feast", "threshold")) and self.once(pet, "harvest_feast"):
                healed = self.heal(pet, owner, self.p("Harvest Feast", "heal"), burst=True)
                self.cleanse(owner)
                messages.append(f"🥧 Harvest Feast! **{owner.name}** eats well: **{healed:.2f} HP**.")
            if self.has(pet, "Cornucopia") and ratio < pct(self.p("Cornucopia", "threshold")) \
                    and pet.sp_counter >= self.p("Cornucopia", "stacks"):
                pet.sp_counter -= self.p("Cornucopia", "stacks")
                for ally in allies:
                    self.heal(pet, ally, self.p("Cornucopia", "heal"), burst=True)
                messages.append(f"🧺 Cornucopia! {pet.name} shares the harvest with the team.")
        if int(getattr(pet, "sp_bountiful", 0) or 0) > 0:
            pet.sp_bountiful -= 1
            for ally in allies:
                self.heal(pet, ally, self.p("Bountiful", "regen"))
            messages.append(f"🌾 The bounty keeps {pet.name}'s team going.")
        if owner is not None and owner.is_alive() and self.has(pet, "Bountiful") \
                and self.hp_ratio(owner) < pct(self.p("Bountiful", "threshold")) and self.once(pet, "Bountiful"):
            for ally in allies:
                self.heal(pet, ally, self.p("Bountiful", "heal"), burst=True)
            pet.sp_bountiful = self.p("Bountiful", "turns")
            messages.append(f"🌾 **Bountiful!** {pet.name} feeds the whole team!")
        if self.has(pet, "Harvest Moon") and self.hp_ratio(pet) < pct(self.p("Harvest Moon", "threshold")) and self.once(pet, "Harvest Moon"):
            pet.hp = max(D(pet.hp), D(pet.max_hp) * pct(self.p("Harvest Moon", "hp")))
            if is_night():
                for enemy in self.enemies(pet):
                    self._entangle(pet, enemy, self.p("Harvest Moon", "turns"))
            messages.append(f"🌕 **Harvest Moon!** {pet.name} regrows under the moon" + (" and vines rise everywhere!" if is_night() else "!"))

    def _guard_gourdling(self, pet, attacker, target, damage, messages):
        if target is self.owner(pet) and self.has(pet, "Scarecrow") and random.random() * 100 < self.p("Scarecrow", "chance"):
            self.ext._deal_damage(attacker, pet, damage)
            messages.append(f"🎃 Scarecrow! The blow meant for **{target.name}** hits {pet.name} instead.")
            return D(0), pet
        return damage

    # ================================================================== Frostfawn
    def _attack_frostfawn(self, pet, target, damage, messages):
        frozen = self.frozen(pet, target)
        if self.has(pet, "Cold Snap") and (frozen or self.chill_of(pet, target) > 0):
            damage *= 1 + pct(self.p("Cold Snap", "bonus"))
        if frozen and self.has(pet, "Shatter"):
            damage *= 1 + pct(self.p("Shatter", "bonus"))
            if hasattr(target, "stunned"):
                delattr(target, "stunned")
            delattr(target, f"sp_frozen_{self.tag(pet)}")
            messages.append(f"💥 Shatter! **{target.name}**'s ice breaks apart.")
        elif self.has(pet, "Frost Chime") and random.random() * 100 < self.p("Frost Chime", "chance"):
            self.chill(pet, target, self.p("Frost Chime", "chill"), messages)
        return damage

    def _hit_frostfawn(self, pet, attacker, damage, messages):
        if self.has(pet, "Ice Glaze") and attacker is not None and attacker.is_alive() and attacker in self.enemies(pet):
            self.chill(pet, attacker, self.p("Ice Glaze", "chill"), messages)
        return damage

    def _turn_frostfawn(self, pet, messages):
        allies = self.allies(pet)
        enemies = self.enemies(pet)
        owner = self.owner(pet)
        if pet.sp_turn == 1:
            if self.has(pet, "Bell"):
                for ally in allies:
                    self.timed(pet, ally, "bell", 999, luck=1 + pct(self.p("Bell", "bonus")))
            if self.has(pet, "Ice Glaze"):
                amount = D(pet.armor) * pct(self.p("Ice Glaze", "shield"))
                self.shield(pet, amount)
                messages.append(f"🧊 {pet.name} glazes itself in ice (**{amount:.2f}** shield).")
        if owner is not None and owner.is_alive():
            if self.has(pet, "Winter Coat") and pet.sp_turn <= self.p("Winter Coat", "turns"):
                cleared = self.cleanse(owner)
                if cleared:
                    messages.append(f"🧥 Winter Coat shakes {', '.join(cleared)} off **{owner.name}**.")
            if self.has(pet, "Silent Night") and self.hp_ratio(owner) < pct(self.p("Silent Night", "threshold")) and self.once(pet, "Silent Night"):
                for enemy in enemies:
                    self.freeze(pet, enemy, messages)
                healed = self.heal(pet, owner, self.p("Silent Night", "heal"), burst=True)
                messages.append(f"🌨️ **Silent Night!** Everything goes still, and **{owner.name}** recovers **{healed:.2f} HP**.")
        if self.has(pet, "Feast Bells") and pet.sp_turn == self.p("Feast Bells", "turn") and self.once(pet, "Feast Bells"):
            for ally in allies:
                self.cleanse(ally)
                self.timed(pet, ally, "feast_bells", self.p("Feast Bells", "turns"), damage=1 + pct(self.p("Feast Bells", "bonus")))
            for enemy in enemies:
                self.chill(pet, enemy, self.p("Feast Bells", "chill"), messages)
            messages.append(f"🔔 **Feast Bells!** {pet.name}'s bells ring out across the battlefield!")
        midwinter_ready = int(getattr(pet, "sp_freezes", 0) or 0) >= self.p("Midwinter", "freezes") \
            or self.hp_ratio(pet) < pct(self.p("Midwinter", "threshold"))
        if self.has(pet, "Midwinter") and midwinter_ready and enemies and self.once(pet, "Midwinter"):
            for enemy in enemies:
                self.strike(pet, enemy, D(pet.damage) * D(self.p("Midwinter", "strike")))
                if enemy.is_alive():
                    self.chill(pet, enemy, self.p("Midwinter", "chill"), messages)
            messages.append(f"❄️ **Midwinter!** {pet.name} calls down the deep cold!")

    def _guard_frostfawn(self, pet, attacker, target, damage, messages):
        if target is not self.owner(pet):
            return damage
        if self.has(pet, "Snow Veil") and random.random() * 100 < self.p("Snow Veil", "dodge"):
            messages.append(f"🌨️ Snow Veil hides **{target.name}** from the blow!")
            return D(0)
        if self.has(pet, "Soft Snow"):
            damage *= 1 - pct(self.p("Soft Snow", "reduction"))
        return damage

    # ================================================================== Hearthkit
    def _attack_hearthkit(self, pet, target, damage, messages):
        if self.has(pet, "Yule Blaze") and pet.sp_counter >= self.p("Yule Blaze", "stacks") and self.once(pet, "Yule Blaze"):
            pet.sp_counter = 0
            damage *= D(self.p("Yule Blaze", "strike"))
            for enemy in self.enemies(pet):
                self.burn(pet, enemy, self.p("Yule Blaze", "turns"))
            messages.append(f"🔥 **Yule Blaze!** {pet.name} pours out every Ember and the room catches fire!")
            return damage
        if self.has(pet, "Stoke") and pet.sp_counter:
            damage *= 1 + pct(min(self.p("Stoke", "max"), self.p("Stoke", "per_stack") * pet.sp_counter))
        if self.has(pet, "Spark Pounce") and random.random() * 100 < self.p("Spark Pounce", "chance"):
            damage *= D(self.p("Spark Pounce", "strike"))
            messages.append(f"✨ {pet.name} pounces in a shower of sparks!")
        if self.has(pet, "Flare-up") and random.random() * 100 < self.p("Flare-up", "chance"):
            self.gain(pet, self.p("Flare-up", "embers"))
            messages.append(f"🔥 Flare-up! {pet.name} gains Embers ({pet.sp_counter}/5).")
        if self.has(pet, "Cinder Swipe"):
            self.burn(pet, target, self.p("Cinder Swipe", "turns"), self.p("Cinder Swipe", "burn"))
        return damage

    def _hit_hearthkit(self, pet, attacker, damage, messages):
        if self.has(pet, "Snug"):
            damage *= 1 - pct(self.p("Snug", "reduction"))
        return damage

    def _turn_hearthkit(self, pet, messages):
        self.gain(pet, 1)
        if self.has(pet, "Catnap") and pet.sp_turn > 1 and not getattr(pet, "attacked_this_turn", False):
            self.gain(pet, self.p("Catnap", "embers"))
            messages.append(f"😴 Catnap: {pet.name} wakes up warmer ({pet.sp_counter}/5 Embers).")
        allies = self.allies(pet)
        if pet.sp_turn == 1 and self.has(pet, "Banked Embers"):
            for ally in allies:
                self.shield(ally, D(ally.max_hp) * pct(self.p("Banked Embers", "shield")))
            messages.append(f"🔥 Banked Embers warm {pet.name}'s team with shields.")
        if pet.sp_turn == self.p("Rekindle", "turn") and self.has(pet, "Rekindle"):
            for ally in allies:
                want = D(ally.max_hp) * pct(self.p("Rekindle", "shield"))
                have = D(getattr(ally, "shield", 0) or 0)
                if have < want:
                    ally.shield = want
            messages.append(f"🔥 Rekindle: {pet.name} tops the team's shields back up.")
        if self.has(pet, "Purr") and pet.sp_counter >= self.p("Purr", "stacks"):
            bonus = 1 + pct(self.p("Purr", "bonus"))
            self.aura(pet, allies, "purr", damage=bonus, armor=bonus, luck=bonus)
        if self.has(pet, "Ember Gift") and allies:
            hurt = min(allies, key=lambda ally: self.hp_ratio(ally))
            self.shield(hurt, D(hurt.max_hp) * pct(self.p("Ember Gift", "shield")))
        owner = self.owner(pet)
        if owner is not None and owner.is_alive():
            if self.has(pet, "Warm Lap") and pet.sp_counter:
                self.heal(pet, owner, min(self.p("Warm Lap", "max"), self.p("Warm Lap", "heal") * pet.sp_counter))
            if self.has(pet, "Home Fires") and self.hp_ratio(owner) < pct(self.p("Home Fires", "threshold")) and self.once(pet, "Home Fires"):
                for ally in allies:
                    self.shield(ally, D(ally.max_hp) * pct(self.p("Home Fires", "shield")))
                    self.heal(pet, ally, self.p("Home Fires", "heal"), burst=True)
                messages.append(f"🏠 **Home Fires!** {pet.name} gathers the team around the hearth!")
        if self.has(pet, "Midwinter Hearth") and pet.sp_turn == self.p("Midwinter Hearth", "turn") and self.once(pet, "Midwinter Hearth"):
            bonus = 1 + pct(self.p("Midwinter Hearth", "bonus"))
            for ally in allies:
                self.timed(pet, ally, "midwinter_hearth", self.p("Midwinter Hearth", "turns"), damage=bonus, armor=bonus, luck=bonus)
            for enemy in self.enemies(pet):
                self.burn(pet, enemy, self.p("Midwinter Hearth", "turns"))
            messages.append(f"🎄 **Midwinter Hearth!** {pet.name} lights the feast fire!")

    def _guard_hearthkit(self, pet, attacker, target, damage, messages):
        if target is not self.owner(pet) or not self.has(pet, "Kept Warm"):
            return damage
        lethal = damage >= D(target.hp) + D(getattr(target, "shield", 0) or 0)
        if lethal and pet.sp_counter >= self.p("Kept Warm", "stacks") and self.once(pet, "kept_warm"):
            pet.sp_counter -= self.p("Kept Warm", "stacks")
            target.hp = D(self.p("Kept Warm", "hp"))
            messages.append(f"🔥 Kept Warm! {pet.name} curls around **{target.name}** and keeps them going.")
            return D(0)
        return damage

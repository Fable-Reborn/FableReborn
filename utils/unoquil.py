"""The Ice Dragon's words: rarely, as a fight starts or as it falls, it says something.

Canon (Library Hall plaques, Tower story):
- Tiamat made the world, turned her body to stone, and the first dragons rose from her pool.
  The Great Seven kept that old world. In 742 BR the Tiamat Sacrament freed the stolen eggs
  (Unoquil's among them) and dragons came back for a while.
- Year 0, the Reckoning: the three gods fought the world and Tiamat and barely won. They count
  their years from that day and have spent every year since burning what was left.
- The Ice Dragon is the last guardian of that age, of Unoquil's line. The gods could not kill
  the mind it shares with Tiamat, so they freeze it. The weekly reset is them freezing it again;
  each stage is a little more of the gods and a little less of it.

Used by the dragon party fight in cogs/battles. Discord-free so the tests can use it.
"""
import random

SPEAK_CHANCE = 0.07
SPEAKER = "The Ice Dragon"

# stage name -> (as a fight starts, as it falls); each has its own SPEAK_CHANCE roll.
# Names and level bands match the seeded ice_dragon_stages rows.
ICE_DRAGON_WORDS = {
    "Frostbite Wyrm": (
        "Climbers. The three send you every winter. Do they still call it a Rite?",
        "Seven kept the old world. The three unmade it in a single day. "
        "You count your years from that day and don't even know it.",
    ),
    "Corrupted Ice Dragon": (
        "Their cold is in my blood. More each week. Strike while I still know what I am.",
        "We were born from her pool to guard this world. We fought them. We nearly won.",
    ),
    "Permafrost": (
        "I don't remember my name. I remember hers. Tiamat.",
        "Unoquil kept the old world beside her. I am all that is left of his line.",
    ),
    "Absolute Zero": (
        "The skull speaks through me now. Do you hear it? It sounds pleased.",
        "Her realm fell in a single day. Your gods have spent every year since burning what was left.",
    ),
    "Void Tyrant": (
        "Less of me each time you come. Do you even notice?",
        "I had a name. I had it a moment ago.",
    ),
    "The Abyssal Maw": (
        "HUNGRY.",
        "...cold...",
    ),
}

# A stage renamed or added by a GM still speaks by its level band.
LEVEL_BANDS = (
    (5, "Frostbite Wyrm"),
    (10, "Corrupted Ice Dragon"),
    (15, "Permafrost"),
    (20, "Absolute Zero"),
    (34, "Void Tyrant"),
)

# Added to its opening words for Dragonkin (Tiamat finishers) while it still remembers.
KIN_LINE = "You carry the old blood. They missed one. Good."
KIN_STAGES = ("Frostbite Wyrm", "Corrupted Ice Dragon", "Permafrost")


def stage_key(stage: str | None, level: int) -> str:
    if stage in ICE_DRAGON_WORDS:
        return stage
    level = int(level or 1)
    for top, name in LEVEL_BANDS:
        if level <= top:
            return name
    return "The Abyssal Maw"


def opening_words(stage: str | None, level: int, *, kin_present: bool = False, rng=random) -> list[str]:
    """Lines as a fight starts: usually none (SPEAK_CHANCE per fight)."""
    if rng.random() >= SPEAK_CHANCE:
        return []
    key = stage_key(stage, level)
    lines = [ICE_DRAGON_WORDS[key][0]]
    if kin_present and key in KIN_STAGES:
        lines.append(KIN_LINE)
    return lines


def falling_words(stage: str | None, level: int, *, rng=random) -> list[str]:
    """Lines as it falls: usually none (SPEAK_CHANCE per kill)."""
    if rng.random() >= SPEAK_CHANCE:
        return []
    return [ICE_DRAGON_WORDS[stage_key(stage, level)][1]]

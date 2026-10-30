"""The Ice Dragon's words: rarely, after it falls, it says something.

Canon (Library Hall plaques, Tower story):
- Tiamat made the world, turned her body to stone, and the first dragons rose from her pool.
  The Great Seven kept that old world. In 742 BR the Tiamat Sacrament freed the stolen eggs
  (Unoquil's among them) and dragons came back for a while.
- Year 0, the Reckoning: the three gods fought the world and Tiamat and barely won. They count
  their years from that day and have spent every year since burning what was left.
- The Ice Dragon is the last guardian of that age, of Unoquil's line. The gods could not kill
  the mind it shares with Tiamat, so they freeze it. The weekly reset is them freezing it again;
  each stage is a little more of the gods and a little less of it.

Discord-free so the cog and the tests can use it.
"""
import random

SPEAK_CHANCE = 0.07
SPEAKER = "The Ice Dragon"

# stage name -> what it might say as it falls (one is picked)
ICE_DRAGON_WORDS = {
    "Frostbite Wyrm": (
        "Climbers. The three send you every winter, and every winter I fall.",
        "Seven kept the old world. The three unmade it in a single day. "
        "You count your years from that day and don't even know it.",
    ),
    "Corrupted Ice Dragon": (
        "Their cold is in my blood. More each week. Soon I won't know what I am.",
        "We were born from her pool to guard this world. We fought them. We nearly won.",
    ),
    "Permafrost": (
        "I don't remember my name. I remember hers. Tiamat.",
        "Unoquil kept the old world beside her. I am all that is left of his line.",
    ),
    "Deathwing": (
        "The skull speaks through me now. Do you hear it? It sounds pleased.",
        "Her realm fell in a single day. Your gods have spent every year since burning what was left.",
    ),
    "The Abyssal Maw": (
        "HUNGRY.",
        "...cold...",
    ),
}

# Added for Dragonkin (Tiamat finishers) while it still remembers.
KIN_LINE = "You carry the old blood. They missed one. Good."
KIN_STAGES = ("Frostbite Wyrm", "Corrupted Ice Dragon", "Permafrost")


def falling_words(stage: str, *, kin_present: bool = False, rng=random) -> list[str]:
    """Lines it says this time it falls: usually none (SPEAK_CHANCE per kill)."""
    words = ICE_DRAGON_WORDS.get(stage)
    if not words or rng.random() >= SPEAK_CHANCE:
        return []
    lines = [rng.choice(words)]
    if kin_present and stage in KIN_STAGES:
        lines.append(KIN_LINE)
    return lines

"""Fables Library pets: species, evolution Chapters and Story.

Library pets come from Fables eggs (the Library hatchery, events and rewards), never the
wild. They hatch and grow to adult like any pet (about 2,000 base stats), then evolve
through ten Chapters. Each Chapter costs Story and needs a pet level, multiplies the
pet's stats by CHAPTER_STAT_STEP (so Chapter X sits near the god pets, about 22,000 base,
and below the top splices), adds 1% Library-born, and Chapters IV and VIII change its form.
Ultimates in the species' skill trees open at Chapter V.

Story is earned in both games and stored as events in `library_pet_story`, written by the
Fables game server (fishing, gardens, table games, Library visits) and by the bot (battle
wins with a Library pet). Each source counts up to a daily share; Story spent on Chapters
is kept in `library_pet_story_wallet`. Eggs queued by the game server wait in
`library_pet_eggs` until the owner has room.

Discord-free so the pets cog, battles and tests can share it.
"""
from __future__ import annotations

import datetime
import math
import random
from dataclasses import dataclass

STORY_EVENTS_SQL = """CREATE TABLE IF NOT EXISTS library_pet_story (
  id BIGSERIAL PRIMARY KEY,
  user_id BIGINT NOT NULL,
  source TEXT NOT NULL,
  amount INTEGER NOT NULL,
  day DATE NOT NULL DEFAULT (now() AT TIME ZONE 'utc')::date,
  request_id TEXT UNIQUE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS library_pet_story_user_day ON library_pet_story (user_id, day)"""

STORY_WALLET_SQL = """CREATE TABLE IF NOT EXISTS library_pet_story_wallet (
  user_id BIGINT PRIMARY KEY,
  spent INTEGER NOT NULL DEFAULT 0
)"""

LIBRARY_EGGS_SQL = """CREATE TABLE IF NOT EXISTS library_pet_eggs (
  id BIGSERIAL PRIMARY KEY,
  user_id BIGINT NOT NULL,
  species TEXT NOT NULL,
  source TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  delivered_at TIMESTAMPTZ,
  egg_id BIGINT
)"""

PET_CHAPTER_SQL = "ALTER TABLE monster_pets ADD COLUMN IF NOT EXISTS library_chapter INTEGER NOT NULL DEFAULT 0"


@dataclass(frozen=True)
class Species:
    name: str           # monsters.json / monster_pets.default_name
    element: str
    hp: int
    attack: int
    defense: int
    forms: tuple        # display names at Chapter 0, IV and VIII


WHELP_FORMS = ("Whelp", "Drake", "Wyrm")


def _whelp(seven, element):
    return Species(f"{seven}'s Whelp", element, 600, 600, 600,
                   tuple(f"{seven}'s {form}" for form in WHELP_FORMS))


# Base stats total 1,800; an egg's IV adds up to 200 more (the bot's usual egg roll).
SPECIES = {s.name: s for s in (
    Species("Inkwyrm", "Dark", 520, 720, 560, ("Inkwyrm", "Quillwyrm", "Codexwyrm")),
    Species("Reedling", "Water", 600, 520, 680, ("Reedling", "Marshdrake", "Lakewarden")),
    Species("Lanternling", "Fire", 560, 700, 540, ("Lanternling", "Lanternwisp", "Hallowflame")),
    Species("Gourdling", "Nature", 680, 540, 580, ("Gourdling", "Gourdhound", "Great Gourd")),
    Species("Frostfawn", "Water", 600, 560, 640, ("Frostfawn", "Rimestag", "Winterhorn")),
    Species("Hearthkit", "Fire", 700, 560, 540, ("Hearthkit", "Hearthcat", "Emberlynx")),
    _whelp("Ilisrei", "Fire"),
    _whelp("Knoas", "Dark"),
    _whelp("Unoquil", "Wind"),
    _whelp("Xetoa", "Water"),
    _whelp("Tamanir", "Electric"),
    _whelp("Kadelej", "Nature"),
    _whelp("Saphira", "Light"),
)}

# Library pets and their eggs live on their own Library shelf, not in the normal pet slots (10-25 by tier).
LIBRARY_SLOTS = 13


def _sql_names():
    return "(" + ", ".join("'" + name.replace("'", "''") + "'" for name in sorted(SPECIES)) + ")"


# For counting slots: the normal slots leave Library pets and eggs out; the shelf counts only them.
NOT_LIBRARY_PET_SQL = f"default_name NOT IN {_sql_names()}"
NOT_LIBRARY_EGG_SQL = f"egg_type NOT IN {_sql_names()}"
LIBRARY_PET_SQL = f"default_name IN {_sql_names()}"
LIBRARY_EGG_SQL = f"egg_type IN {_sql_names()}"


def is_library_egg(egg) -> bool:
    return species(_get(egg, "egg_type")) is not None


MAX_CHAPTER = 10
# 1.271^10 ~= 11: an adult of ~2,000 base reaches ~22,000 at Chapter X.
CHAPTER_STAT_STEP = 1.271
FORM_CHAPTERS = (0, 4, 8)
ULTIMATE_CHAPTER = 5
LIBRARY_BORN_PER_CHAPTER = 1  # percent

# Chapter -> (Story cost, pet level needed). About 4,500 Story in all.
CHAPTERS = {
    1: (60, 10), 2: (120, 20), 3: (180, 30), 4: (260, 40), 5: (340, 50),
    6: (450, 60), 7: (560, 70), 8: (680, 80), 9: (820, 90), 10: (1000, 100),
}

# Story by source, and how much of each counts per day (UTC).
STORY_SOURCES = {
    "battle": {"amount": 2, "daily": 30, "label": "Battle wins with a Library pet"},
    "fishing": {"amount": 1, "daily": 15, "label": "Fish caught in the Library homes"},
    "garden": {"amount": 2, "daily": 15, "label": "Crops harvested in the Library homes"},
    "games": {"amount": 2, "daily": 10, "label": "Table games won in the Library"},
    "visit": {"amount": 5, "daily": 5, "label": "Visiting the Library"},
    "reward": {"amount": 0, "daily": 10_000, "label": "Event and staff rewards"},
}


def species(name) -> Species | None:
    return SPECIES.get(str(name or "").strip())


def is_library_pet(pet) -> bool:
    return species(_get(pet, "default_name")) is not None


def is_account_bound(pet_or_egg) -> bool:
    """Library pets and their eggs stay with the reader who earned them: one of each kind per reader, never traded or
    sold (a pet by species, an egg by egg_type)."""
    return species(_get(pet_or_egg, "default_name")) is not None or species(_get(pet_or_egg, "egg_type")) is not None


def bound_message(pet_or_egg, action) -> str:
    """'... cannot be <action>.' for a Library pet or egg, or ""."""
    if not is_account_bound(pet_or_egg):
        return ""
    return f"Fables Library pets and eggs stay with the reader who earned them and cannot be {action}."


def chapter_of(pet) -> int:
    try:
        return max(0, min(MAX_CHAPTER, int(_get(pet, "library_chapter", 0) or 0)))
    except (TypeError, ValueError):
        return 0


def library_born_pct(chapter) -> int:
    return LIBRARY_BORN_PER_CHAPTER * max(0, min(MAX_CHAPTER, int(chapter or 0)))


def form_index(chapter) -> int:
    return sum(1 for start in FORM_CHAPTERS[1:] if int(chapter or 0) >= start)


def form_name(pet_or_species, chapter=None) -> str:
    spec = pet_or_species if isinstance(pet_or_species, Species) else species(_get(pet_or_species, "default_name"))
    if spec is None:
        return ""
    if chapter is None:
        chapter = chapter_of(pet_or_species)
    return spec.forms[form_index(chapter)]


# Portraits (Astera) are hosted with the Library site; a form's picture appears as soon as
# its file is uploaded, without touching the pets that use it.
ART_BASE = "https://game.fablereborn.xyz/assets/library-pets/"


def art_slug(spec: Species, chapter=0) -> str:
    name = spec.forms[form_index(chapter)].lower().replace("'", "")
    return "".join(c if c.isalnum() else "-" for c in name).strip("-").replace("--", "-")


def art_url(spec: Species, chapter=0) -> str:
    return f"{ART_BASE}{art_slug(spec, chapter)}.jpg"


def hatch_moment_url(spec: Species) -> str:
    """The egg cracking open into its hatchling (Astera; a GIF so Discord plays it)."""
    return f"{ART_BASE}moments/{art_slug(spec, 0)}-hatch.gif"


def evolve_moment_url(spec: Species, chapter) -> str | None:
    """The old form rewritten into the new one, for the Chapters that change form (IV and VIII); None otherwise."""
    if int(chapter or 0) not in FORM_CHAPTERS[1:]:
        return None
    return f"{ART_BASE}moments/{art_slug(spec, chapter)}-evolve.gif"


def egg_art_url(spec: Species) -> str:
    return f"{ART_BASE}eggs/{art_slug(spec, 0)}-egg.jpg"


def hatched_url(egg) -> str:
    """A hatched pet's picture: a Library egg hatches into its hatchling form, not the egg picture."""
    spec = species(_get(egg, "egg_type"))
    return art_url(spec, 0) if spec else _get(egg, "url")


def roman(number) -> str:
    return ["0", "I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X"][max(0, min(10, int(number)))]


def story_balance(daily_rows, spent) -> int:
    """`daily_rows`: (source, day, total) sums. Each source counts up to its daily share."""
    earned = 0
    for source, _day, total in daily_rows:
        cap = STORY_SOURCES.get(str(source), {}).get("daily", 0)
        earned += min(int(cap), max(0, int(total or 0)))
    return max(0, earned - int(spent or 0))


def today_progress(daily_rows, today=None):
    """{source: (counted today, daily share)} for today's rows."""
    today = today or datetime.datetime.utcnow().date()
    counted = {source: 0 for source in STORY_SOURCES if source != "reward"}
    for source, day, total in daily_rows:
        if day == today and source in counted:
            counted[source] = min(STORY_SOURCES[source]["daily"], int(total or 0))
    return {source: (value, STORY_SOURCES[source]["daily"]) for source, value in counted.items()}


@dataclass(frozen=True)
class EvolveCheck:
    ok: bool
    reason: str = ""
    next_chapter: int = 0
    cost: int = 0
    level_needed: int = 0


def can_evolve(pet, balance) -> EvolveCheck:
    if not is_library_pet(pet):
        return EvolveCheck(False, "not_library")
    if str(_get(pet, "growth_stage", "") or "").lower() != "adult":
        return EvolveCheck(False, "not_adult")
    chapter = chapter_of(pet)
    if chapter >= MAX_CHAPTER:
        return EvolveCheck(False, "max_chapter", chapter)
    cost, level_needed = CHAPTERS[chapter + 1]
    level = int(_get(pet, "level", 1) or 1)
    if level < level_needed:
        return EvolveCheck(False, "level", chapter + 1, cost, level_needed)
    if int(balance or 0) < cost:
        return EvolveCheck(False, "story", chapter + 1, cost, level_needed)
    return EvolveCheck(True, "", chapter + 1, cost, level_needed)


def evolved_stats(pet) -> dict:
    """The pet's stored stats after one more Chapter."""
    return {stat: int(round(float(_get(pet, stat, 0) or 0) * CHAPTER_STAT_STEP)) for stat in ("hp", "attack", "defense")}


def roll_egg(spec: Species, rng=random) -> dict:
    """An egg's IV and stats, with the same IV odds as the bot's wild eggs (Battles._roll_egg_stats)."""
    roll = rng.uniform(10, 1000)
    for threshold, low, high in ((20, 90, 100), (70, 80, 90), (150, 70, 80), (350, 60, 70), (700, 50, 60)):
        if roll < threshold:
            iv = rng.uniform(low, high)
            break
    else:
        iv = rng.uniform(30, 50)
    points = iv / 100 * 200
    a, b, c = rng.random(), rng.random(), rng.random()
    total = a + b + c
    hp_iv, attack_iv = int(points * a / total), int(points * b / total)  # floors, so defense never goes negative
    defense_iv = int(round(points)) - hp_iv - attack_iv
    return {"IV": iv, "hp_iv": hp_iv, "attack_iv": attack_iv, "defense_iv": defense_iv,
            "hp": spec.hp + hp_iv, "attack": spec.attack + attack_iv, "defense": spec.defense + defense_iv}


def chapter_total_multiplier(chapter) -> float:
    return CHAPTER_STAT_STEP ** max(0, min(MAX_CHAPTER, int(chapter or 0)))


def _get(record, key, default=None):
    if record is None:
        return default
    if isinstance(record, dict):
        return record.get(key, default)
    try:
        return record[key]
    except (KeyError, IndexError, TypeError):
        return getattr(record, key, default)


assert math.isclose(chapter_total_multiplier(MAX_CHAPTER), 11.0, rel_tol=0.02)

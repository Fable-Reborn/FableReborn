"""Pet art requests: readers ask for one of their pets to get a walking sprite in the Fables Library.

Every pet already follows its reader in the Library as its portrait. A request puts its species in the
drawing queue; once its sprite is live, everyone who owns that species sees it walk. One request every
four weeks, and the clock only starts on a request that's accepted: cancelling one, or having it
turned down, gives the turn back.

Sprites are keyed like the Library keys them (Server/CrownFallServer/src/pets.js speciesKey/petView), so a
sprite drawn for a request is the one the Library shows. The Library lists its sprites in
data/PetSprites.json; a request finishes when its key appears there, or when a GM marks it complete.

Used by cogs/petart. Discord-free so the tests can use it.
"""
from __future__ import annotations

import datetime
import re
import unicodedata

from utils import library_pets

COOLDOWN = datetime.timedelta(days=28)
SPRITES_URL = "https://game.fablereborn.xyz/games/hub/data/PetSprites.json"
ART_PROMPT = "reports/Pets-Sprite-ArtPrompt.md"

OPEN = ("queued", "drawing")
# Requests that used up their reader's turn; cancelled and rejected ones don't.
COUNTED = ("queued", "drawing", "done")

TABLE_SQL = """
CREATE TABLE IF NOT EXISTS pet_art_requests (
    id SERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    pet_id BIGINT NOT NULL,
    pet_name TEXT NOT NULL,
    species TEXT NOT NULL,
    species_key TEXT NOT NULL,
    element TEXT,
    portrait TEXT,
    status TEXT NOT NULL DEFAULT 'queued',
    reason TEXT,
    batch TEXT,
    waived BOOLEAN NOT NULL DEFAULT FALSE,
    requested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at TIMESTAMPTZ,
    finished_by BIGINT
);
CREATE UNIQUE INDEX IF NOT EXISTS pet_art_requests_open_species
    ON pet_art_requests (species_key) WHERE status IN ('queued', 'drawing');
CREATE INDEX IF NOT EXISTS pet_art_requests_user ON pet_art_requests (user_id, requested_at DESC);
"""

_CONTROL = re.compile(r"[\u0000-\u001f<>]")


def _clean(value, limit=50) -> str:
    return _CONTROL.sub("", str(value or "")).strip()[:limit]


def species_key(name) -> str:
    """The Library's key for a species name (pets.js speciesKey)."""
    text = unicodedata.normalize("NFKD", _clean(name, 80).lower())
    text = "".join(ch for ch in text if not 0x300 <= ord(ch) <= 0x36F)
    return re.sub(r"[^a-z0-9]+", "_", text).strip("_")[:64] or "pet"


def _get(pet, key, default=None):
    try:
        value = pet[key]
    except (KeyError, IndexError, TypeError):
        return getattr(pet, key, default)
    return default if value is None else value


def species_of(pet) -> str:
    """The species the Library shows for a monster_pets row: a Library pet's current form, else its species."""
    default = _clean(_get(pet, "default_name"))
    if library_pets.species(default) is not None:
        form = library_pets.form_name(pet)
        if form:
            return form
    return _clean(_get(pet, "default_name") or _get(pet, "name")) or "Pet"


def pet_details(pet) -> dict:
    species = species_of(pet)
    return {
        "pet_id": int(_get(pet, "id")),
        "pet_name": _clean(_get(pet, "name")) or species,
        "species": species,
        "species_key": species_key(species),
        "element": _clean(_get(pet, "element"), 20) or None,
        "portrait": _get(pet, "url") or None,
    }


def next_request_at(last_counted_at: datetime.datetime | None) -> datetime.datetime | None:
    """When a reader may ask again, given their last request that counted (None = now)."""
    return None if last_counted_at is None else last_counted_at + COOLDOWN


def drawn_keys(sprites_json) -> set[str]:
    """Species keys with a walking sprite in the Library's PetSprites.json."""
    sprites = (sprites_json or {}).get("sprites") if isinstance(sprites_json, dict) else None
    return set(sprites) if isinstance(sprites, dict) else set()


def batch_file(rows, batch: str, made: datetime.datetime) -> dict:
    """A batch in the shape tools/pets/requests.py writes (reports/hub-art/pets/<batch>/requests.json)."""
    return {
        "batch": batch,
        "made": made.replace(microsecond=0).isoformat(),
        "instructions": ART_PROMPT,
        "species": [
            {"key": r["species_key"], "name": r["species"], "element": r["element"], "owners": 1,
             "portrait": r["portrait"], "request": r["id"]}
            for r in rows
        ],
    }

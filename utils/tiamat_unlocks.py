"""Fable rewards earned by playing The Tiamat Sacrament.

The Tiamat game server writes one row per earned unlock into `tiamat_unlocks`
(keyed by Discord ID, so a reward waits for a character made later):

    dragonkin     finish the story              -> the Dragonkin race
    clutch_badge  finish the story              -> the Clutch of Ilisrei profile badge
    penitent      spare Gyle                    -> the Penitent class
    breathcaller  hold all seven Soul Gems      -> the Breathcaller class (secret)
    founding_reader  sign in during the Fables Library's Founding Week
                                                -> The Founding Reader profile theme

Players who finished before the table existed are covered by the companion
unlocks the server already wrote: Az'uar is given for finishing the story and the
goddess Tiamat for all seven Soul Gems. Sparing Gyle has no such proof (Gyle is a
companion on every route), so Penitent waits for the player's next Tiamat sign-in,
when the server's catch-up writes it.

Discord-free so cogs, battle code and tests can share it.
"""
from __future__ import annotations

TABLE_SQL = """CREATE TABLE IF NOT EXISTS tiamat_unlocks (
  user_id BIGINT NOT NULL,
  unlock_key TEXT NOT NULL,
  source TEXT,
  granted_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (user_id, unlock_key)
)"""

DRAGONKIN = "dragonkin"
CLUTCH_BADGE = "clutch_badge"
PENITENT = "penitent"
BREATHCALLER = "breathcaller"
FOUNDING_READER = "founding_reader"
KEYS = frozenset({DRAGONKIN, CLUTCH_BADGE, PENITENT, BREATHCALLER, FOUNDING_READER})

# Unlock -> the Tiamat companion that already proves it.
COMPANION_PROOF = {DRAGONKIN: "azuar", CLUTCH_BADGE: "azuar", BREATHCALLER: "tiamat"}

# How each unlock is described where a locked option is teased.
HINTS = {
    DRAGONKIN: "Finish the story of The Tiamat Sacrament.",
    CLUTCH_BADGE: "Finish the story of The Tiamat Sacrament.",
    PENITENT: "Show mercy to Gyle in The Tiamat Sacrament.",
    BREATHCALLER: "???",
    FOUNDING_READER: "Sign in to the Fables Library during its Founding Week.",
}


# The three gods' names as players' profiles may spell them ($follow), by the name the Fables use.
GOD_NAMES = {"elysia": "Elysia", "asterea": "Elysia", "astraea": "Elysia",
             "sepulchure": "Sepulchure", "drakath": "Drakath"}


def carries_tiamat(character) -> bool:
    """Whether this character carries Tiamat's power, which the three gods have spent every year
    since her realm fell trying to destroy: Dragonkin (finished the story) and the Breathcaller line
    (all seven Soul Gems). `character` is a profile row with "race" and "class"."""
    from classes.classes import Breathcaller, from_string
    from classes.dragonkin import RACE

    if not character:
        return False
    if character.get("race") == RACE:
        return True
    return any((line := from_string(name)) is not None and line.in_class_line(Breathcaller)
               for name in (character.get("class") or []))


def god_name(god) -> str | None:
    """One of the three by its Fables name, or None for anything else."""
    return GOD_NAMES.get(str(god or "").strip().lower())


def unlocks_from(rows, companions) -> set[str]:
    """The unlocks shown by `tiamat_unlocks` rows plus companion proof."""
    unlocked = {str(row) for row in rows or [] if str(row) in KEYS}
    owned = {str(key) for key in companions or []}
    unlocked.update(key for key, companion in COMPANION_PROOF.items() if companion in owned)
    return unlocked


def _missing_table(error) -> bool:
    return getattr(error, "sqlstate", None) == "42P01" or type(error).__name__ == "UndefinedTableError"


async def ensure_table(conn) -> None:
    await conn.execute(TABLE_SQL)


async def unlocks_for(conn, user_id: int) -> set[str]:
    """Everything this player has earned in Tiamat (an empty set if nothing is set up yet)."""
    rows, companions = [], []
    try:
        rows = [r["unlock_key"] for r in await conn.fetch(
            "SELECT unlock_key FROM tiamat_unlocks WHERE user_id = $1;", user_id)]
    except Exception as error:
        if not _missing_table(error):
            raise
    try:
        companions = await conn.fetchval("SELECT unlocked FROM companions WHERE user_id = $1;", user_id) or []
    except Exception as error:
        if not _missing_table(error):
            raise
    return unlocks_from(rows, companions)


async def has_unlock(conn, user_id: int, key: str) -> bool:
    return key in await unlocks_for(conn, user_id)


async def users_with(conn, key: str) -> list[int]:
    """Every Discord ID holding `key`, from the table and from companion proof."""
    users: set[int] = set()
    try:
        users.update(r["user_id"] for r in await conn.fetch(
            "SELECT user_id FROM tiamat_unlocks WHERE unlock_key = $1;", key))
    except Exception as error:
        if not _missing_table(error):
            raise
    companion = COMPANION_PROOF.get(key)
    if companion:
        try:
            users.update(r["user_id"] for r in await conn.fetch(
                "SELECT user_id FROM companions WHERE $1 = ANY(unlocked);", companion))
        except Exception as error:
            if not _missing_table(error):
                raise
    return sorted(users)

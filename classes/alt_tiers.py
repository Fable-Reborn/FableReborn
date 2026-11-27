"""Legendary Hero (tier 4) perks reach the donator's linked alt.

Many perks read `profile.tier` directly, so the alt's profile is set to 4 while
its main is tier 4. The alt's own tier is remembered in `alt_tier_grants` and
put back as soon as the main drops below 4 or the link is gone. Only tier 4
is shared; Adventurer, Warrior and Hero stay with the main account.

The Patreon sync never lowers a tier for someone who is not a patron, which is
why the grant must be tracked here and never written as a plain tier.
"""
from __future__ import annotations

LEGENDARY = 4

SCHEMA = """
CREATE TABLE IF NOT EXISTS alt_tier_grants (
    alt BIGINT PRIMARY KEY,
    main BIGINT NOT NULL,
    previous_tier INTEGER NOT NULL DEFAULT 0,
    granted_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
)
"""

# Give back the alt's own tier when its main is no longer Legendary or the link
# is gone. A tier someone else changed since (a Patreon sync) is left alone.
REVOKE_SQL = """
WITH gone AS (
    DELETE FROM alt_tier_grants g
    WHERE NOT EXISTS (
        SELECT 1
          FROM alt_links l
          JOIN profile m ON m."user" = l.main
         WHERE l.alt = g.alt AND l.main = g.main AND COALESCE(m."tier", 0) >= $1
    )
    RETURNING g.alt, g.previous_tier
)
UPDATE profile p
   SET "tier" = gone.previous_tier
  FROM gone
 WHERE p."user" = gone.alt AND COALESCE(p."tier", 0) = $1
RETURNING p."user"
"""

# Raise alts of Legendary mains to 4. `previous_tier` is refreshed on every run,
# so if the alt's own tier changed (a Patreon sync reset it), the newest one is
# what comes back later.
GRANT_SQL = """
WITH eligible AS (
    SELECT l.alt, l.main, COALESCE(a."tier", 0) AS own
      FROM alt_links l
      JOIN profile m ON m."user" = l.main
      JOIN profile a ON a."user" = l.alt
     WHERE COALESCE(m."tier", 0) >= $1 AND COALESCE(a."tier", 0) < $1
), saved AS (
    INSERT INTO alt_tier_grants (alt, main, previous_tier)
    SELECT alt, main, own FROM eligible
    ON CONFLICT (alt) DO UPDATE
       SET main = EXCLUDED.main, previous_tier = EXCLUDED.previous_tier, granted_at = NOW()
    RETURNING alt
)
UPDATE profile p
   SET "tier" = $1
  FROM saved
 WHERE p."user" = saved.alt
RETURNING p."user"
"""


async def ensure_schema(conn) -> None:
    await conn.execute(SCHEMA)


MAINS_BELOW_LEGENDARY_SQL = """
SELECT l.main
  FROM alt_links l
  JOIN profile p ON p."user" = l.main
 WHERE COALESCE(p."tier", 0) < $1
"""


async def refresh_main_tiers(bot) -> list[int]:
    """Save the real tier of every main that is not saved as Legendary yet.

    A Legendary Hero whose tier comes from a Discord role (Ko-fi, or a Patreon
    role the Patreon sync has not written yet) only gets tier 4 saved when they
    run a donor command. Until then their alt would get nothing. This checks
    their roles now and saves the tier, the same way a donor command would.
    Returns the mains that are now Legendary.
    """
    rows = await bot.pool.fetch(MAINS_BELOW_LEGENDARY_SQL, LEGENDARY)
    promoted = []
    for row in rows:
        main = int(row["main"])
        try:
            tier = int(await bot.get_effective_donator_tier(main, sync_profile=True) or 0)
        except Exception:
            continue
        if tier >= LEGENDARY:
            promoted.append(main)
    return promoted


async def sync_alt_tiers(pool) -> tuple[list[int], list[int]]:
    """(granted alt ids, revoked alt ids). Safe to run from every cluster at once."""
    async with pool.acquire() as conn:
        await ensure_schema(conn)
        async with conn.transaction():
            await conn.execute("SELECT pg_advisory_xact_lock(hashtext('alt_tier_grants'))")
            revoked = [int(r["user"]) for r in await conn.fetch(REVOKE_SQL, LEGENDARY)]
            granted = [int(r["user"]) for r in await conn.fetch(GRANT_SQL, LEGENDARY)]
    return granted, revoked

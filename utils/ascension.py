"""Persistent reset-potion inventory and atomic ascension resets."""
import asyncio

from classes.ascension import ASCENSION_TABLE_NAME, ASCENSION_UNLOCK_LEVEL
from utils.misc import xp_for_level


async def ensure_ascension_potions(bot):
    if getattr(bot, "_ascension_potions_ready", False):
        return
    if not hasattr(bot, "_ascension_potions_lock"):
        bot._ascension_potions_lock = asyncio.Lock()
    async with bot._ascension_potions_lock:
        if getattr(bot, "_ascension_potions_ready", False):
            return
        async with bot.pool.acquire() as conn:
            await conn.execute(f"""
                CREATE TABLE IF NOT EXISTS {ASCENSION_TABLE_NAME} (
                    user_id bigint PRIMARY KEY,
                    mantle text NOT NULL,
                    enabled boolean NOT NULL DEFAULT true,
                    chosen_at timestamptz NOT NULL DEFAULT now()
                );
                CREATE TABLE IF NOT EXISTS ascension_reset_potions (
                    user_id bigint PRIMARY KEY,
                    quantity integer NOT NULL DEFAULT 0 CHECK (quantity >= 0)
                );
            """)
        bot._ascension_potions_ready = True


async def grant_ascension_potions(bot, user_id=None):
    """Give one potion per eligible profile; None means every level-100+ profile."""
    await ensure_ascension_potions(bot)
    async with bot.pool.acquire() as conn:
        count = await conn.fetchval("""
            WITH granted AS (
                INSERT INTO ascension_reset_potions (user_id, quantity)
                SELECT "user", 1 FROM profile
                WHERE xp >= $1 AND ($2::bigint IS NULL OR "user" = $2)
                ORDER BY "user"
                ON CONFLICT (user_id) DO UPDATE
                SET quantity = ascension_reset_potions.quantity + 1
                RETURNING user_id
            )
            SELECT COUNT(*) FROM granted;
        """, xp_for_level(ASCENSION_UNLOCK_LEVEL), user_id)
    return int(count or 0)


async def consume_ascension_potion(bot, user_id):
    """Reset only the mantle, spending exactly one potion in the same transaction."""
    await ensure_ascension_potions(bot)
    async with bot.pool.acquire() as conn:
        async with conn.transaction():
            profile = await conn.fetchrow(
                'SELECT xp FROM profile WHERE "user" = $1 FOR UPDATE;', user_id
            )
            if profile is None:
                return False, "You need a character to consume an Ascension Reset Potion."
            if profile["xp"] < xp_for_level(ASCENSION_UNLOCK_LEVEL):
                return False, "You must be level 100 or higher to reset your ascension."
            quantity = await conn.fetchval(
                "SELECT quantity FROM ascension_reset_potions WHERE user_id = $1 FOR UPDATE;",
                user_id,
            )
            if not quantity:
                return False, "You don't have an Ascension Reset Potion."
            mantle = await conn.fetchval(
                f"DELETE FROM {ASCENSION_TABLE_NAME} WHERE user_id = $1 RETURNING mantle;",
                user_id,
            )
            if mantle is None:
                return False, "You have no ascension to reset. Your potion was kept."
            await conn.execute(
                "UPDATE ascension_reset_potions SET quantity = quantity - 1 WHERE user_id = $1;",
                user_id,
            )
    return True, "Your ascension has been reset. One Ascension Reset Potion was consumed."

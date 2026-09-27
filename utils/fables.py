"""Fable rewards: accepts an asyncpg pool OR an existing transaction connection."""

async def unlock_fable(db, discord_id: int, fable_id: str, *, source: str = "reward") -> bool:
    """Grant once; return True for a new unlock, False if already owned.

    Example: await unlock_fable(ctx.bot.pool, ctx.author.id, "crownfall", source="quest:42")
    Pass your transaction connection to make the unlock atomic with other rewards.
    The caller decides reward eligibility; this helper never sends Discord messages.
    """
    fable_id = str(fable_id).strip().lower()
    if not await db.fetchval("SELECT id FROM fables WHERE id=$1 AND enabled", fable_id):
        raise ValueError("Unknown or disabled Fable.")
    result = await db.fetchval(
        "INSERT INTO fable_unlocks (discord_id, fable_id, source) VALUES ($1,$2,$3) "
        "ON CONFLICT (discord_id, fable_id) DO NOTHING RETURNING fable_id",
        int(discord_id), fable_id, str(source)[:200],
    )
    return result is not None


async def unlocked_fables(db, discord_id: int):
    return await db.fetch(
        "SELECT f.id, f.title, f.description, f.tagline, f.protagonist_type, "
        "f.protagonist_name, u.unlocked_at, u.started_at, u.completed_at FROM fable_unlocks u "
        "JOIN fables f ON f.id=u.fable_id WHERE u.discord_id=$1 AND f.enabled "
        "ORDER BY u.unlocked_at, f.id", int(discord_id),
    )


async def complete_fable(db, discord_id: int, fable_id: str) -> bool:
    """Record a verified story ending. Does not unlock stories or grant rewards.

    Returns True only on the first completion. Call from a trusted ending/reward
    handler (or pass an existing transaction connection); never from a public
    player command. The Fable must already be unlocked.
    """
    result = await db.fetchval(
        "UPDATE fable_unlocks SET started_at=COALESCE(started_at, now()), completed_at=now() "
        "WHERE discord_id=$1 AND fable_id=$2 AND completed_at IS NULL RETURNING fable_id",
        int(discord_id), str(fable_id).strip().lower(),
    )
    return result is not None

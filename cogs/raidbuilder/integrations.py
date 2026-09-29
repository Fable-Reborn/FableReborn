"""Explicit, read-only Fable adapters. Node files never specify SQL or commands."""

SYSTEM_SOURCES = {
    "party_level_total": "Total character levels",
    "party_level_average": "Average character level (rounded down)",
    "party_guild_members": "Players who belong to a guild",
    "party_guild_count": "Distinct party guilds",
}


async def load_system_values(pool, player_ids):
    """One snapshot of joined characters, taken before the encounter starts.

    Database errors propagate: a live encounter must not invent game data.
    Missing character rows are also a failure rather than a partial aggregate.
    """
    from utils.misc import xptolevel

    ids = sorted(set(int(user) for user in player_ids))
    rows = await pool.fetch(
        'SELECT "user", "xp", "guild" FROM profile WHERE "user" = ANY($1::bigint[])',
        ids,
    )
    if {row["user"] for row in rows} != set(ids) or not ids:
        raise ValueError(
            "Could not load every joined character for Fable System nodes."
        )
    levels = [int(xptolevel(row["xp"])) for row in rows]
    guilds = [row["guild"] for row in rows if row["guild"]]
    return {
        "party_level_total": sum(levels),
        "party_level_average": sum(levels) // len(levels),
        "party_guild_members": len(guilds),
        "party_guild_count": len(set(guilds)),
    }

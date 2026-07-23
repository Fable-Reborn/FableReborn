"""Persistent, per-class-line mastery used to unlock specializations.

The module is intentionally Discord-free so reward listeners, commands, and tests
can share the same progression rules without importing a cog.
"""
from __future__ import annotations

import asyncio
from collections.abc import Iterable

from classes.classes import from_string as class_from_string
from utils import misc as rpgtools


MASTERY_UNLOCK_LEVEL = 40
MASTERY_UNLOCK_POINTS = 100
ICE_DRAGON_MASTERY_DAILY_CAP = 25
MASTERY_TIMEZONE = "Australia/Sydney"

MASTERY_AWARDS = {
    "adventure": 1,
    "pve": 1,
    "battle_tower_floor": 1,
    "battle_tower_boss": 2,
    "jury_tower_floor": 1,
    "jury_tower_boss": 2,
    "gauntlet": 2,
    "ice_dragon": 3,
    "scheduled_raid": 5,
    "boss_rush": 5,
    "ironman_milestone": 1,
}
IRONMAN_MASTERY_FLOORS = frozenset({5, 10, 15, 20, 25})

_TABLES_READY = False
_TABLE_LOCK = asyncio.Lock()
_GRANDFATHER_MARKER = "class_mastery_grandfather_v1"
_ICE_DRAGON_CAP_MARKER = "class_mastery_ice_dragon_cap_v1"


def class_lines_from_names(class_names: Iterable[str] | None) -> dict[str, int]:
    """Return the highest equipped grade for each valid class line."""
    lines: dict[str, int] = {}
    for class_name in class_names or []:
        if not class_name:
            continue
        game_class = class_from_string(str(class_name))
        if game_class is None:
            continue
        line = game_class.get_class_line_name()
        lines[line] = max(lines.get(line, 0), game_class.class_grade())
    return lines


def specialization_is_unlocked(*, level: int, grade: int, points: int) -> bool:
    return (
        int(level) >= MASTERY_UNLOCK_LEVEL
        and int(grade) >= 7
        and int(points) >= MASTERY_UNLOCK_POINTS
    )


def rift_mastery_points(rooms_cleared: int, full_clear: bool) -> int:
    rooms = max(0, min(7, int(rooms_cleared or 0)))
    return rooms + (3 if full_clear and rooms == 7 else 0)


async def ensure_mastery_tables(bot) -> None:
    """Create mastery storage and grandfather players eligible before rollout."""
    global _TABLES_READY
    if _TABLES_READY:
        return

    async with _TABLE_LOCK:
        if _TABLES_READY:
            return
        async with bot.pool.acquire() as conn:
            await conn.execute(
                f"""
                CREATE TABLE IF NOT EXISTS class_mastery (
                    user_id BIGINT NOT NULL,
                    class_line TEXT NOT NULL,
                    points INTEGER NOT NULL DEFAULT 0,
                    daily_points INTEGER NOT NULL DEFAULT 0,
                    daily_date DATE NOT NULL DEFAULT
                        ((CURRENT_TIMESTAMP AT TIME ZONE '{MASTERY_TIMEZONE}')::date),
                    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
                    PRIMARY KEY (user_id, class_line),
                    CHECK (points >= 0),
                    CHECK (daily_points >= 0)
                );

                CREATE TABLE IF NOT EXISTS class_mastery_events (
                    user_id BIGINT NOT NULL,
                    event_key TEXT NOT NULL,
                    source TEXT NOT NULL,
                    awarded_at TIMESTAMP NOT NULL DEFAULT NOW(),
                    PRIMARY KEY (user_id, event_key)
                );

                CREATE TABLE IF NOT EXISTS class_mastery_meta (
                    key TEXT PRIMARY KEY,
                    created_at TIMESTAMP NOT NULL DEFAULT NOW()
                );
                """
            )

            # This transaction makes the one-time migrations safe across shards. If
            # either fails, its marker rolls back so the next startup can retry.
            async with conn.transaction():
                should_reset_daily_points = await conn.fetchval(
                    """
                    INSERT INTO class_mastery_meta (key)
                    VALUES ($1)
                    ON CONFLICT (key) DO NOTHING
                    RETURNING TRUE
                    """,
                    _ICE_DRAGON_CAP_MARKER,
                )
                if should_reset_daily_points:
                    # This counter used to include every repeatable source. Reset it
                    # once so old activity cannot consume the new Ice Dragon cap.
                    await conn.execute(
                        f"""
                        UPDATE class_mastery
                        SET daily_points = 0,
                            daily_date = ((CURRENT_TIMESTAMP AT TIME ZONE '{MASTERY_TIMEZONE}')::date),
                            updated_at = NOW()
                        WHERE daily_points <> 0
                        """
                    )

                should_seed = await conn.fetchval(
                    """
                    INSERT INTO class_mastery_meta (key)
                    VALUES ($1)
                    ON CONFLICT (key) DO NOTHING
                    RETURNING TRUE
                    """,
                    _GRANDFATHER_MARKER,
                )
                if should_seed:
                    seed_rows: set[tuple[int, str]] = set()
                    profiles = await conn.fetch(
                        'SELECT "user", class FROM profile WHERE xp >= $1',
                        int(rpgtools.levels[50]),
                    )
                    for profile in profiles:
                        for line, grade in class_lines_from_names(profile["class"]).items():
                            if grade >= 7:
                                seed_rows.add((int(profile["user"]), line))

                    if await conn.fetchval(
                        "SELECT to_regclass('public.class_specs') IS NOT NULL"
                    ):
                        chosen = await conn.fetch(
                            "SELECT user_id, class_line FROM class_specs"
                        )
                        seed_rows.update(
                            (int(row["user_id"]), str(row["class_line"]))
                            for row in chosen
                        )

                    if seed_rows:
                        await conn.executemany(
                            """
                            INSERT INTO class_mastery (
                                user_id, class_line, points, daily_points
                            )
                            VALUES ($1, $2, $3, 0)
                            ON CONFLICT (user_id, class_line) DO UPDATE
                            SET points = GREATEST(class_mastery.points, EXCLUDED.points),
                                updated_at = NOW()
                            """,
                            [
                                (user_id, line, MASTERY_UNLOCK_POINTS)
                                for user_id, line in sorted(seed_rows)
                            ],
                        )

        _TABLES_READY = True


async def get_class_mastery(bot, user_id: int, *, conn=None) -> dict:
    """Return equipped lines and today's Ice Dragon cap usage."""
    await ensure_mastery_tables(bot)
    if conn is None:
        async with bot.pool.acquire() as acquired:
            return await get_class_mastery(bot, user_id, conn=acquired)

    profile = await conn.fetchrow(
        'SELECT class, xp FROM profile WHERE "user" = $1', int(user_id)
    )
    if not profile:
        return {"level": 0, "lines": {}}

    rows = await conn.fetch(
        f"""
        SELECT class_line, points,
               CASE
                   WHEN daily_date = ((CURRENT_TIMESTAMP AT TIME ZONE '{MASTERY_TIMEZONE}')::date)
                   THEN daily_points
                   ELSE 0
               END AS daily_points
        FROM class_mastery
        WHERE user_id = $1
        """,
        int(user_id),
    )
    stored = {str(row["class_line"]): row for row in rows}
    level = int(rpgtools.xptolevel(profile["xp"]))
    equipped_lines = class_lines_from_names(profile["class"])
    lines = {}
    for line in sorted(set(equipped_lines) | set(stored)):
        grade = int(equipped_lines.get(line, 0))
        row = stored.get(line)
        points = int(row["points"] if row else 0)
        daily_points = int(row["daily_points"] if row else 0)
        lines[line] = {
            "grade": grade,
            "equipped": line in equipped_lines,
            "points": points,
            "daily_points": daily_points,
            "unlocked": specialization_is_unlocked(
                level=level,
                grade=grade,
                points=points,
            ),
        }
    return {"level": level, "lines": lines}


async def award_class_mastery(
    bot,
    user_id: int,
    points: int,
    *,
    source: str,
    event_key: str | None = None,
    conn=None,
) -> list[dict]:
    """Award mastery to both equipped Grade 7 lines.

    Only Ice Dragon awards respect the Sydney-day cap. Every other source is
    uncapped. Results contain only lines that actually received points.
    """
    requested = max(0, int(points))
    if requested <= 0:
        return []

    await ensure_mastery_tables(bot)
    if conn is None:
        async with bot.pool.acquire() as acquired:
            return await award_class_mastery(
                bot,
                user_id,
                requested,
                source=source,
                event_key=event_key,
                conn=acquired,
            )

    user_id = int(user_id)
    async with conn.transaction():
        profile = await conn.fetchrow(
            'SELECT class FROM profile WHERE "user" = $1', user_id
        )
        if not profile:
            return []
        eligible_lines = {
            line: grade
            for line, grade in class_lines_from_names(profile["class"]).items()
            if grade >= 7
        }
        if not eligible_lines:
            return []

        if event_key:
            inserted = await conn.fetchval(
                """
                INSERT INTO class_mastery_events (user_id, event_key, source)
                VALUES ($1, $2, $3)
                ON CONFLICT (user_id, event_key) DO NOTHING
                RETURNING TRUE
                """,
                user_id,
                str(event_key),
                str(source),
            )
            if not inserted:
                return []

        results = []
        counts_toward_daily_cap = str(source).strip().casefold() == "ice_dragon"
        for line in eligible_lines:
            await conn.execute(
                """
                INSERT INTO class_mastery (user_id, class_line)
                VALUES ($1, $2)
                ON CONFLICT (user_id, class_line) DO NOTHING
                """,
                user_id,
                line,
            )
            row = await conn.fetchrow(
                f"""
                SELECT points,
                       CASE
                           WHEN daily_date = ((CURRENT_TIMESTAMP AT TIME ZONE '{MASTERY_TIMEZONE}')::date)
                           THEN daily_points
                           ELSE 0
                       END AS daily_points,
                       daily_date = ((CURRENT_TIMESTAMP AT TIME ZONE '{MASTERY_TIMEZONE}')::date)
                           AS is_today
                FROM class_mastery
                WHERE user_id = $1 AND class_line = $2
                FOR UPDATE
                """,
                user_id,
                line,
            )
            current = int(row["points"] or 0)
            daily = int(row["daily_points"] or 0)
            if current >= MASTERY_UNLOCK_POINTS:
                continue

            allowed = min(requested, MASTERY_UNLOCK_POINTS - current)
            if counts_toward_daily_cap:
                allowed = min(
                    allowed,
                    max(0, ICE_DRAGON_MASTERY_DAILY_CAP - daily),
                )

            if allowed <= 0:
                if not row["is_today"]:
                    await conn.execute(
                        f"""
                        UPDATE class_mastery
                        SET daily_points = 0,
                            daily_date = ((CURRENT_TIMESTAMP AT TIME ZONE '{MASTERY_TIMEZONE}')::date),
                            updated_at = NOW()
                        WHERE user_id = $1 AND class_line = $2
                        """,
                        user_id,
                        line,
                    )
                continue

            new_points = current + allowed
            new_daily = daily + allowed if counts_toward_daily_cap else daily
            await conn.execute(
                f"""
                UPDATE class_mastery
                SET points = $3,
                    daily_points = $4,
                    daily_date = ((CURRENT_TIMESTAMP AT TIME ZONE '{MASTERY_TIMEZONE}')::date),
                    updated_at = NOW()
                WHERE user_id = $1 AND class_line = $2
                """,
                user_id,
                line,
                new_points,
                new_daily,
            )
            results.append(
                {
                    "line": line,
                    "awarded": allowed,
                    "points": new_points,
                    "daily_points": new_daily,
                    "newly_mastered": (
                        current < MASTERY_UNLOCK_POINTS <= new_points
                    ),
                }
            )

        return results

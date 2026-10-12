"""Who is online in the RPG (Tiamat and Crownfall), for GM commands.

The game server rewrites the ``fable_online`` table every ~10 seconds with the
players connected right now: map, tile, what they are doing and so on. Rows
older than ``STALE_AFTER`` mean the server stopped reporting (stopped, crashed
or not restarted since this feature was added).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import asyncpg
import discord


STALE_AFTER = timedelta(seconds=45)
FABLE_NAMES = {"tiamat": "The Tiamat Sacrament", "crownfall": "Crownfall"}
ACTIVITY = {
    "exploring": "🧭 exploring",
    "battle": "⚔️ in battle",
    "cutscene": "🎬 in a cutscene",
    "talking": "💬 talking",
    "menu": "📜 in a menu",
    "resting": "💤 resting",
    "transferring": "🌀 travelling",
    "connecting": "⏳ connecting",
}
ROLE_BADGE = {"owner": "👑", "admin": "🛡️", "moderator": "🔨"}
FIELD_LIMIT = 1024
FIELDS_PER_EMBED = 25

ONLINE_QUERY = """
    SELECT fable_id, username, display_name, discord_id, role, map_id, map_name, x, y,
           activity, hidden, in_party, muted, level, current_hp, max_hp,
           playtime_seconds, connected_at, updated_at
    FROM fable_online
    ORDER BY fable_id, lower(coalesce(display_name, username))
"""


async def fetch_online(pool) -> list[dict] | None:
    """Every row the game servers published, or None if the table doesn't exist yet."""
    try:
        async with pool.acquire() as connection:
            return [dict(row) for row in await connection.fetch(ONLINE_QUERY)]
    except asyncpg.UndefinedTableError:
        return None


async def find_player(pool, query: str, discord_id: int | None = None) -> dict:
    """Live rows plus the linked account for a username, display name or Discord user."""
    needle = query.strip().lower()
    async with pool.acquire() as connection:
        try:
            online = [dict(row) for row in await connection.fetch(
                """
                SELECT fable_id, username, display_name, discord_id, role, map_id, map_name, x, y,
                       activity, hidden, in_party, muted, level, current_hp, max_hp,
                       playtime_seconds, connected_at, updated_at
                FROM fable_online
                WHERE lower(username)=$1 OR lower(display_name)=$1 OR discord_id=$2
                ORDER BY updated_at DESC
                """,
                needle,
                discord_id,
            )]
        except asyncpg.UndefinedTableError:
            online = []
        account = await connection.fetchrow(
            """
            SELECT profile_user, game_username, display_name, crowns, last_map_id, last_map_name,
                   actor_level, current_hp, max_hp, playtime_seconds, linked_at, last_seen_at
            FROM tiamat_players
            WHERE lower(game_username)=$1 OR lower(display_name)=$1 OR profile_user=$2
            ORDER BY last_seen_at DESC NULLS LAST
            LIMIT 1
            """,
            needle,
            discord_id,
        )
    return {"online": online, "account": dict(account) if account else None}


def split_fresh(rows: list[dict], now: datetime) -> tuple[list[dict], list[dict]]:
    """Rows from servers still reporting, and rows a stopped server left behind."""
    fresh, stale = [], []
    for row in rows:
        (fresh if row["updated_at"] and now - row["updated_at"] <= STALE_AFTER else stale).append(row)
    return fresh, stale


def format_duration(since: datetime | None, now: datetime) -> str:
    if since is None:
        return "—"
    minutes = max(0, int((now - since).total_seconds() // 60))
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes:02d}m" if hours else f"{minutes}m"


def format_place(row: dict) -> str:
    if not row.get("map_id"):
        return "loading in"
    name = " ".join(str(row.get("map_name") or "").split()) or "Unknown map"
    tile = f" ({row['x']}, {row['y']})" if row.get("x") is not None and row.get("y") is not None else ""
    return f"{name} · map {row['map_id']}{tile}"


def format_name(row: dict) -> str:
    badge = ROLE_BADGE.get(row.get("role") or "", "")
    display = row.get("display_name") or row["username"]
    name = f"**{display}**" if display.lower() == row["username"].lower() else f"**{display}** ({row['username']})"
    linked = f" · <@{row['discord_id']}>" if row.get("discord_id") else " · not linked"
    return f"{badge}{' ' if badge else ''}{name}{linked}"


def format_flags(row: dict) -> str:
    flags = []
    if row.get("in_party"):
        flags.append("👥 party")
    if row.get("muted"):
        flags.append("🔇 muted")
    if row.get("hidden"):
        flags.append("👻 hidden")
    return " · ".join(flags)


def player_line(row: dict, now: datetime) -> str:
    activity = ACTIVITY.get(row.get("activity") or "", row.get("activity") or "—")
    stats = []
    if row.get("level") is not None:
        stats.append(f"Lv {row['level']}")
    if row.get("current_hp") is not None and row.get("max_hp"):
        stats.append(f"HP {row['current_hp']:,}/{row['max_hp']:,}")
    stats.append(f"on {format_duration(row.get('connected_at'), now)}")
    flags = format_flags(row)
    return (f"{format_name(row)}\n📍 {format_place(row)} · {activity}\n"
            f"{' · '.join(stats)}{' · ' + flags if flags else ''}")


def chunk_lines(lines: list[str], limit: int = FIELD_LIMIT) -> list[str]:
    """Join lines into field values that each stay under Discord's 1024 characters."""
    chunks, current = [], ""
    for line in lines:
        line = line[:limit]
        candidate = f"{current}\n\n{line}" if current else line
        if len(candidate) > limit:
            chunks.append(current)
            current = line
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks


def build_online_embeds(rows: list[dict] | None, now: datetime | None = None) -> list[discord.Embed]:
    now = now or datetime.now(timezone.utc)
    embed = discord.Embed(title="RPG — who's online", colour=discord.Colour.blue(), timestamp=now)
    if rows is None:
        embed.description = ("The game server hasn't published an online list yet. "
                             "It starts once the server is restarted with this feature.")
        return [embed]
    fresh, stale = split_fresh(rows, now)
    if not fresh:
        embed.description = "Nobody is online right now."
        if stale:
            last = max(row["updated_at"] for row in stale)
            embed.description += (f"\n⚠️ The game server stopped reporting {format_duration(last, now)} ago "
                                  "— it may be down.")
        return [embed]
    embeds = [embed]
    by_fable: dict[str, list[dict]] = {}
    for row in fresh:
        by_fable.setdefault(row["fable_id"], []).append(row)
    embed.description = " · ".join(f"**{len(players)}** in {FABLE_NAMES.get(fable, fable)}"
                                   for fable, players in by_fable.items())
    for fable, players in by_fable.items():
        chunks = chunk_lines([player_line(row, now) for row in players])
        for index, chunk in enumerate(chunks):
            title = FABLE_NAMES.get(fable, fable) + (f" (cont. {index + 1})" if index else "")
            if len(embeds[-1].fields) >= FIELDS_PER_EMBED or len(embeds[-1]) + len(chunk) + len(title) > 5800:
                embeds.append(discord.Embed(colour=discord.Colour.blue()))
            embeds[-1].add_field(name=title, value=chunk, inline=False)
    embeds[-1].set_footer(text="Live from the game server · refreshed every ~10 seconds")
    return embeds


def build_player_embed(query: str, found: dict, now: datetime | None = None) -> discord.Embed:
    now = now or datetime.now(timezone.utc)
    fresh, _stale = split_fresh(found["online"], now)
    account = found["account"]
    if not fresh and not account:
        return discord.Embed(title="Player not found", colour=discord.Colour.red(),
                             description=f"No RPG player matches **{discord.utils.escape_markdown(query)}**. "
                                         "Use their game username, display name or Discord mention.")
    if fresh:
        row = fresh[0]
        embed = discord.Embed(title=f"🟢 {row.get('display_name') or row['username']} — online",
                              colour=discord.Colour.green(), timestamp=now)
        for other in fresh:
            embed.add_field(name=FABLE_NAMES.get(other["fable_id"], other["fable_id"]),
                            value=player_line(other, now), inline=False)
    else:
        embed = discord.Embed(title=f"⚫ {account.get('display_name') or account['game_username']} — offline",
                              colour=discord.Colour.dark_grey(), timestamp=now)
        last_seen = account.get("last_seen_at")
        place = " ".join(str(account.get("last_map_name") or "").split()) or "Unknown"
        embed.add_field(name="Last seen",
                        value=f"{discord.utils.format_dt(last_seen, 'R') if last_seen else 'Never'}\n📍 {place}"
                              f"{' · map ' + str(account['last_map_id']) if account.get('last_map_id') else ''}",
                        inline=False)
    if account:
        stats = []
        if account.get("actor_level") is not None:
            stats.append(f"Lv {account['actor_level']}")
        if account.get("current_hp") is not None and account.get("max_hp"):
            stats.append(f"HP {account['current_hp']:,}/{account['max_hp']:,}")
        embed.add_field(name="Account",
                        value=(f"Game username **{account['game_username']}** · linked to <@{account['profile_user']}>\n"
                               f"👑 {int(account.get('crowns') or 0):,} crowns"
                               f"{' · ' + ' · '.join(stats) if stats else ''}"),
                        inline=False)
    else:
        embed.add_field(name="Account", value="Not linked to a Discord profile.", inline=False)
    return embed

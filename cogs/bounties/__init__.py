"""Versioned daily and weekly Bounty contracts.

Every board contains two evergreen contracts and one specialist contract with
three distinct metrics. Everyone receives the same deterministic v2 board.
Historical v1 rows remain untouched and rewards are paid atomically with the
claim transition.
"""
from __future__ import annotations

import asyncio
import logging
import random
from datetime import datetime, time, timedelta, timezone

import discord
from discord.ext import commands

from utils.checks import has_char


logger = logging.getLogger(__name__)

BOARD_VERSION = "v2"
DAILY = "daily"
WEEKLY = "weekly"
EVERGREEN = "evergreen"
SPECIALIST = "specialist"


def _contract(
    key: str,
    *,
    period: str,
    slot: str,
    name: str,
    icon: str,
    metric: str,
    target: int,
    reward: int,
    requirement: str,
    difficulty: str,
) -> dict:
    """Create one immutable-by-convention catalog record."""
    return {
        "key": key,
        "period": period,
        "slot": slot,
        "name": name,
        "icon": icon,
        "emoji": icon,  # compatibility with the original catalog shape
        "metric": metric,
        "target": int(target),
        "reward": int(reward),
        "requirement": requirement,
        "text": requirement,
        "difficulty": difficulty,
    }


# Stable IDs are never repurposed. A future balance/catalog rewrite should use v3 IDs.
BOUNTY_DEFINITIONS = {
    bounty["key"]: bounty
    for bounty in (
        # Daily evergreen: median and active-player bands supplied by live data.
        _contract(
            "v2_d_tower_3", period=DAILY, slot=EVERGREEN, name="Tower Patrol",
            icon="🗼", metric="tower_floor", target=3, reward=14,
            requirement="Clear 3 Battle Tower floors", difficulty="Routine",
        ),
        _contract(
            "v2_d_tower_8", period=DAILY, slot=EVERGREEN, name="Spire Circuit",
            icon="🗼", metric="tower_floor", target=8, reward=24,
            requirement="Clear 8 Battle Tower floors", difficulty="Seasoned",
        ),
        _contract(
            "v2_d_dragon_3", period=DAILY, slot=EVERGREEN, name="Frost Watch",
            icon="🐉", metric="dragon_kill", target=3, reward=18,
            requirement="Defeat 3 Ice Dragons", difficulty="Routine",
        ),
        _contract(
            "v2_d_dragon_8", period=DAILY, slot=EVERGREEN, name="Wyrm Hunt",
            icon="🐉", metric="dragon_kill", target=8, reward=30,
            requirement="Defeat 8 Ice Dragons", difficulty="Seasoned",
        ),
        _contract(
            "v2_d_adventure_2", period=DAILY, slot=EVERGREEN, name="Roadwork",
            icon="🧭", metric="adventure", target=2, reward=16,
            requirement="Complete 2 adventures", difficulty="Routine",
        ),
        _contract(
            "v2_d_adventure_4", period=DAILY, slot=EVERGREEN, name="Long Road",
            icon="🧭", metric="adventure", target=4, reward=24,
            requirement="Complete 4 adventures", difficulty="Seasoned",
        ),
        # Daily specialists: p90 core bands plus focused mode goals.
        _contract(
            "v2_d_tower_15", period=DAILY, slot=SPECIALIST, name="High Ascent",
            icon="🗼", metric="tower_floor", target=15, reward=38,
            requirement="Clear 15 Battle Tower floors", difficulty="Expert",
        ),
        _contract(
            "v2_d_dragon_15", period=DAILY, slot=SPECIALIST, name="Frostbreaker",
            icon="🐉", metric="dragon_kill", target=15, reward=42,
            requirement="Defeat 15 Ice Dragons", difficulty="Expert",
        ),
        _contract(
            "v2_d_adventure_6", period=DAILY, slot=SPECIALIST, name="Forced March",
            icon="🧭", metric="adventure", target=6, reward=38,
            requirement="Complete 6 adventures", difficulty="Expert",
        ),
        _contract(
            "v2_d_raid_1", period=DAILY, slot=SPECIALIST, name="Raid Standard",
            icon="⚔️", metric="raid_win", target=1, reward=34,
            requirement="Win 1 raid", difficulty="Hard",
        ),
        _contract(
            "v2_d_bossrush_1", period=DAILY, slot=SPECIALIST, name="Crown Contract",
            icon="👑", metric="bossrush_win", target=1, reward=38,
            requirement="Clear 1 full Boss Rush", difficulty="Elite",
        ),
        _contract(
            "v2_d_corruption_3", period=DAILY, slot=SPECIALIST, name="Blight Detail",
            icon="✦", metric="corrupted_clear", target=3, reward=32,
            requirement="Cleanse 3 corrupted floors", difficulty="Hard",
        ),
        _contract(
            "v2_d_gauntlet_3", period=DAILY, slot=SPECIALIST, name="Gauntlet Orders",
            icon="🛡️", metric="gauntlet_match", target=3, reward=30,
            requirement="Complete 3 Defense Gauntlet clashes", difficulty="Hard",
        ),
        # Weekly evergreen: median/p75 live user-week bands.
        _contract(
            "v2_w_tower_15", period=WEEKLY, slot=EVERGREEN, name="Tower Detail",
            icon="🗼", metric="tower_floor", target=15, reward=55,
            requirement="Clear 15 Battle Tower floors", difficulty="Routine",
        ),
        _contract(
            "v2_w_tower_35", period=WEEKLY, slot=EVERGREEN, name="Spire Campaign",
            icon="🗼", metric="tower_floor", target=35, reward=85,
            requirement="Clear 35 Battle Tower floors", difficulty="Seasoned",
        ),
        _contract(
            "v2_w_dragon_15", period=WEEKLY, slot=EVERGREEN, name="Dragon Detail",
            icon="🐉", metric="dragon_kill", target=15, reward=65,
            requirement="Defeat 15 Ice Dragons", difficulty="Routine",
        ),
        _contract(
            "v2_w_dragon_50", period=WEEKLY, slot=EVERGREEN, name="Wyrm Campaign",
            icon="🐉", metric="dragon_kill", target=50, reward=110,
            requirement="Defeat 50 Ice Dragons", difficulty="Elite",
        ),
        _contract(
            "v2_w_adventure_8", period=WEEKLY, slot=EVERGREEN, name="Trail Ledger",
            icon="🧭", metric="adventure", target=8, reward=55,
            requirement="Complete 8 adventures", difficulty="Routine",
        ),
        _contract(
            "v2_w_adventure_15", period=WEEKLY, slot=EVERGREEN, name="Wayfarer's Week",
            icon="🧭", metric="adventure", target=15, reward=80,
            requirement="Complete 15 adventures", difficulty="Seasoned",
        ),
        # Weekly specialists: p90 core bands and deeper mode contracts.
        _contract(
            "v2_w_tower_75", period=WEEKLY, slot=SPECIALIST, name="Endless Stair",
            icon="🗼", metric="tower_floor", target=75, reward=150,
            requirement="Clear 75 Battle Tower floors", difficulty="Mythic",
        ),
        _contract(
            "v2_w_dragon_100", period=WEEKLY, slot=SPECIALIST, name="Century of Frost",
            icon="🐉", metric="dragon_kill", target=100, reward=170,
            requirement="Defeat 100 Ice Dragons", difficulty="Mythic",
        ),
        _contract(
            "v2_w_adventure_25", period=WEEKLY, slot=SPECIALIST, name="Realm Circuit",
            icon="🧭", metric="adventure", target=25, reward=130,
            requirement="Complete 25 adventures", difficulty="Elite",
        ),
        _contract(
            "v2_w_raid_5", period=WEEKLY, slot=SPECIALIST, name="Warhost Writ",
            icon="⚔️", metric="raid_win", target=5, reward=120,
            requirement="Win 5 raids", difficulty="Elite",
        ),
        _contract(
            "v2_w_rift_1", period=WEEKLY, slot=SPECIALIST, name="Seal the Breach",
            icon="🌀", metric="rift_clear", target=1, reward=110,
            requirement="Fully clear 1 weekly Rift", difficulty="Elite",
        ),
        _contract(
            "v2_w_bossrush_3", period=WEEKLY, slot=SPECIALIST, name="Three Crowns",
            icon="👑", metric="bossrush_win", target=3, reward=120,
            requirement="Clear 3 full Boss Rushes", difficulty="Elite",
        ),
        _contract(
            "v2_w_corruption_10", period=WEEKLY, slot=SPECIALIST, name="Purge Order",
            icon="✦", metric="corrupted_clear", target=10, reward=100,
            requirement="Cleanse 10 corrupted floors", difficulty="Elite",
        ),
        _contract(
            "v2_w_gauntlet_12", period=WEEKLY, slot=SPECIALIST, name="Shield Circuit",
            icon="🛡️", metric="gauntlet_match", target=12, reward=95,
            requirement="Complete 12 Defense Gauntlet clashes", difficulty="Hard",
        ),
        _contract(
            "v2_w_hunt_1", period=WEEKLY, slot=SPECIALIST, name="Apex Writ",
            icon="🐾", metric="hunt_kill", target=1, reward=120,
            requirement="Help slay 1 Hunt beast", difficulty="Elite",
        ),
    )
}

DAILY_POOL = tuple(
    bounty for bounty in BOUNTY_DEFINITIONS.values() if bounty["period"] == DAILY
)
WEEKLY_POOL = tuple(
    bounty for bounty in BOUNTY_DEFINITIONS.values() if bounty["period"] == WEEKLY
)


def coerce_utc(now: datetime | None = None) -> datetime:
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        return now.replace(tzinfo=timezone.utc)
    return now.astimezone(timezone.utc)


def bounty_reset_times(now: datetime | None = None) -> dict[str, datetime]:
    """Return exact next daily and ISO-week reset instants."""
    now = coerce_utc(now)
    next_day = datetime.combine(now.date() + timedelta(days=1), time.min, tzinfo=timezone.utc)
    days_until_monday = 7 - now.weekday()
    next_week = datetime.combine(
        now.date() + timedelta(days=days_until_monday), time.min, tzinfo=timezone.utc
    )
    return {DAILY: next_day, WEEKLY: next_week}


def progress_bar(current: int, total: int, width: int = 8) -> str:
    if total <= 0:
        return "▱" * width
    filled = int(width * max(0, min(int(current), int(total))) / int(total))
    return "▰" * filled + "▱" * (width - filled)


def _select_distinct(
    rng: random.Random,
    pool: tuple[dict, ...] | list[dict],
    count: int,
    excluded_metrics=(),
) -> list[dict]:
    """Deterministically sample contracts while enforcing unique metrics."""
    candidates = list(pool)
    rng.shuffle(candidates)
    used = set(excluded_metrics)
    selected = []
    for bounty in candidates:
        if bounty["metric"] in used:
            continue
        selected.append(dict(bounty))
        used.add(bounty["metric"])
        if len(selected) == count:
            break
    if len(selected) != count:
        raise RuntimeError("Bounty catalog cannot satisfy distinct-metric board constraints")
    return selected


def generate_bounty_boards(now: datetime | None = None):
    """Pure board generator with an injectable clock for deterministic tests."""
    now = coerce_utc(now)
    day_token = now.strftime("%Y-%m-%d")
    iso = now.isocalendar()
    week_token = f"{iso.year}-W{iso.week:02d}"

    boards = []
    for period, token, pool, label in (
        (DAILY, day_token, DAILY_POOL, "Daily Contracts"),
        (WEEKLY, week_token, WEEKLY_POOL, "Weekly Contracts"),
    ):
        rng = random.Random(f"bounty-{BOARD_VERSION}-{period}-{token}")
        evergreen_pool = tuple(b for b in pool if b["slot"] == EVERGREEN)
        specialist_pool = tuple(b for b in pool if b["slot"] == SPECIALIST)
        evergreen = _select_distinct(rng, evergreen_pool, 2)
        specialist = _select_distinct(
            rng, specialist_pool, 1, {bounty["metric"] for bounty in evergreen}
        )
        bounties = evergreen + specialist
        if len({bounty["metric"] for bounty in bounties}) != 3:
            raise RuntimeError("Generated Bounty board contains duplicate metrics")
        boards.append((f"{period}-{BOARD_VERSION}-{token}", label, bounties))
    return boards


def _record_value(row, key: str, default=None):
    if row is None:
        return default
    try:
        value = row[key]
    except (KeyError, TypeError):
        value = getattr(row, key, default)
    return default if value is None else value


def build_bounty_completion_embed(user_id: int, completions: list[dict]) -> discord.Embed:
    total_reward = sum(int(bounty["reward"]) for bounty in completions)
    embed = discord.Embed(
        title="Contracts Fulfilled",
        description=(
            f"<@{int(user_id)}> completed **{len(completions)}** "
            f"contract{'s' if len(completions) != 1 else ''}."
        ),
        color=0x2E8B57,
    )
    embed.add_field(
        name="Claimed Automatically",
        value="\n".join(
            f"✓ {bounty['icon']} **{bounty['name']}** · **+{int(bounty['reward']):,} LP**"
            for bounty in completions
        ),
        inline=False,
    )
    embed.set_footer(text=f"Total paid · +{total_reward:,} Legacy Points")
    return embed


def build_bounty_board_embed(
    display_name: str,
    boards,
    progress_map: dict,
    now: datetime | None = None,
) -> discord.Embed:
    """Build the mobile-first board embed (safe to snapshot-test)."""
    resets = bounty_reset_times(now)
    total_contracts = sum(len(bounties) for _key, _label, bounties in boards)
    completed_total = 0
    claimed_lp = 0
    purse = sum(
        int(bounty["reward"])
        for _board_key, _label, bounties in boards
        for bounty in bounties
    )

    rendered_boards = []
    for board_key, label, bounties in boards:
        period = DAILY if board_key.startswith(f"{DAILY}-") else WEEKLY
        lines = []
        complete_here = 0
        for bounty in bounties:
            row = progress_map.get((board_key, bounty["key"]))
            progress = min(
                int(_record_value(row, "progress", 0)), int(bounty["target"])
            )
            done = bool(_record_value(row, "claimed", False))
            if done:
                complete_here += 1
                completed_total += 1
                claimed_lp += int(bounty["reward"])
                progress = int(bounty["target"])
            state = "✓" if done else "○"
            state_text = "Claimed" if done else "In progress"
            lines.append(
                f"{state} {bounty['icon']} **{bounty['name']}** · **{bounty['difficulty']}**\n"
                f"{bounty['requirement']}\n"
                f"{progress_bar(progress, bounty['target'])}  `{progress:,}/{int(bounty['target']):,}` "
                f"· **+{int(bounty['reward']):,} LP** · {state_text}"
            )
        reset_ts = int(resets[period].timestamp())
        heading = f"{label} · {complete_here}/{len(bounties)}"
        reset_line = f"Resets <t:{reset_ts}:R> · <t:{reset_ts}:f>"
        rendered_boards.append((heading, reset_line + "\n\n" + "\n\n".join(lines)))

    embed = discord.Embed(
        title=f"Bounty Board · {display_name}",
        description=(
            "Shared realm contracts · rewards are claimed automatically\n"
            f"**{completed_total}/{total_contracts} complete** · "
            f"**{claimed_lp:,}/{purse:,} LP** secured"
        ),
        color=0x7A5230,
    )
    for heading, value in rendered_boards:
        embed.add_field(name=heading, value=value, inline=False)

    embed.set_footer(
        text="Shared v2 board · Dailies reset 00:00 UTC · Weeklies reset Monday 00:00 UTC"
    )
    return embed


class Bounties(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self._tables_ready = False
        self._table_lock = asyncio.Lock()

    async def ensure_tables(self):
        if self._tables_ready:
            return
        async with self._table_lock:
            if self._tables_ready:
                return
            async with self.bot.pool.acquire() as conn:
                await conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS bounty_progress (
                        user_id BIGINT NOT NULL,
                        board_key TEXT NOT NULL,
                        bounty_key TEXT NOT NULL,
                        progress BIGINT NOT NULL DEFAULT 0,
                        claimed BOOLEAN NOT NULL DEFAULT FALSE,
                        completed_at TIMESTAMP,
                        PRIMARY KEY (user_id, board_key, bounty_key)
                    );
                    """
                )
                await conn.execute(
                    "ALTER TABLE bounty_progress "
                    "ADD COLUMN IF NOT EXISTS completed_at TIMESTAMP;"
                )
            self._tables_ready = True

    async def cog_load(self):
        await self.ensure_tables()

    def current_boards(self, now: datetime | None = None):
        return generate_bounty_boards(now)

    async def bump(self, user_id: int, metric: str, amount: int, channel=None):
        """Advance matching v2 contracts and atomically pay newly completed work."""
        amount = int(amount)
        if amount <= 0:
            raise ValueError("Bounty progress amount must be positive")
        await self.ensure_tables()

        matches = [
            (board_key, bounty)
            for board_key, _label, bounties in self.current_boards()
            for bounty in bounties
            if bounty["metric"] == metric
        ]
        if not matches:
            return []

        completions = []
        async with self.bot.pool.acquire() as conn:
            async with conn.transaction():
                for board_key, bounty in matches:
                    row = await conn.fetchrow(
                        """
                        INSERT INTO bounty_progress
                            (user_id, board_key, bounty_key, progress)
                        VALUES ($1, $2, $3, $4)
                        ON CONFLICT (user_id, board_key, bounty_key)
                        DO UPDATE SET progress = LEAST(
                            bounty_progress.progress + EXCLUDED.progress, $5
                        )
                        WHERE bounty_progress.claimed = FALSE
                        RETURNING progress, claimed
                        """,
                        int(user_id),
                        board_key,
                        bounty["key"],
                        min(amount, int(bounty["target"])),
                        int(bounty["target"]),
                    )
                    if not row or row["claimed"] or int(row["progress"]) < int(bounty["target"]):
                        continue

                    claimed_now = await conn.fetchval(
                        """
                        UPDATE bounty_progress
                        SET claimed = TRUE,
                            completed_at = COALESCE(completed_at, NOW())
                        WHERE user_id = $1 AND board_key = $2 AND bounty_key = $3
                              AND claimed = FALSE
                        RETURNING TRUE
                        """,
                        int(user_id),
                        board_key,
                        bounty["key"],
                    )
                    if not claimed_now:
                        continue

                    legacy = self.bot.get_cog("Legacy")
                    if legacy is None:
                        raise RuntimeError("Legacy cog unavailable during Bounty payout")
                    await legacy.award_points(
                        int(user_id), int(bounty["reward"]), conn=conn
                    )
                    completions.append(dict(bounty))

        if completions and channel is not None:
            try:
                await channel.send(
                    embed=build_bounty_completion_embed(int(user_id), completions)
                )
            except Exception:
                logger.warning(
                    "Failed to announce %s Bounty completions for user %s",
                    len(completions),
                    user_id,
                    exc_info=True,
                )
        return completions

    async def _bump_users(self, user_ids, metric: str, channel=None):
        for user_id in dict.fromkeys(int(value) for value in user_ids):
            try:
                await self.bump(user_id, metric, 1, channel)
            except Exception:
                logger.exception("Bounty tracking failed for metric %s, user %s", metric, user_id)

    @commands.Cog.listener()
    async def on_battletower_completion(
        self, ctx, success, level=None, level_name=None,
        name_value=None, minion1_name=None, minion2_name=None,
    ):
        if not success:
            return
        await self._bump_users([ctx.author.id], "tower_floor", getattr(ctx, "channel", None))

    @commands.Cog.listener()
    async def on_adventure_completion(self, ctx, iscompleted):
        if not iscompleted:
            return
        await self._bump_users([ctx.author.id], "adventure", getattr(ctx, "channel", None))

    @commands.Cog.listener()
    async def on_bounty_adventure_completion(self, ctx, iscompleted):
        """Count successful low-level adventures without broadening other reward hooks."""
        if not iscompleted:
            return
        await self._bump_users([ctx.author.id], "adventure", getattr(ctx, "channel", None))

    @commands.Cog.listener()
    async def on_icedragon_victory(self, ctx, party_members, stage_name, dragon_level):
        await self._bump_users(
            [member.id for member in party_members],
            "dragon_kill",
            getattr(ctx, "channel", None),
        )

    @commands.Cog.listener()
    async def on_raid_favor(self, ctx, participant_ids, success):
        if not success:
            return
        await self._bump_users(participant_ids, "raid_win", getattr(ctx, "channel", None))

    @commands.Cog.listener()
    async def on_rift_completion(
        self, ctx, rooms_cleared, score, full_clear, difficulty="normal"
    ):
        if not full_clear:
            return
        await self._bump_users([ctx.author.id], "rift_clear", getattr(ctx, "channel", None))

    @commands.Cog.listener()
    async def on_bossrush_completion(self, ctx, success):
        if not success:
            return
        await self._bump_users([ctx.author.id], "bossrush_win", getattr(ctx, "channel", None))

    @commands.Cog.listener()
    async def on_corrupted_floor_cleansed(self, ctx):
        await self._bump_users(
            [ctx.author.id], "corrupted_clear", getattr(ctx, "channel", None)
        )

    @commands.Cog.listener()
    async def on_gauntlet_completion(self, ctx, attacker_id, defender_id, attacker_won):
        await self._bump_users(
            [attacker_id, defender_id], "gauntlet_match", getattr(ctx, "channel", None)
        )

    @commands.Cog.listener()
    async def on_hunt_beast_slain(
        self, ctx, participant_ids, survivor_ids, top_tracker_id
    ):
        await self._bump_users(
            participant_ids, "hunt_kill", getattr(ctx, "channel", None)
        )

    @commands.command(aliases=["bounty", "bountyboard"])
    @has_char()
    async def bounties(self, ctx):
        """View the current Bounty Board and your progress."""
        await self.ensure_tables()
        now = datetime.now(timezone.utc)
        boards = self.current_boards(now)
        board_keys = [board_key for board_key, _label, _bounties in boards]
        async with self.bot.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT board_key, bounty_key, progress, claimed, completed_at
                FROM bounty_progress
                WHERE user_id = $1 AND board_key = ANY($2::TEXT[])
                """,
                ctx.author.id,
                board_keys,
            )
        progress_map = {
            (row["board_key"], row["bounty_key"]): row for row in rows
        }
        embed = build_bounty_board_embed(
            ctx.author.display_name, boards, progress_map, now
        )
        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(Bounties(bot))

"""
Legacy Points — the account-bound endgame currency.

Every endgame mode drips into one bar that never stops moving:
- Battle Tower floor clears (bonus on milestone floors and the finale)
- Battle Tower prestige
- Ice Dragon Challenge kills (scaled by dragon stage)

Points are spent in the Legacy Shop on crates, gold and the Living Legend badge.
Other cogs award points by dispatching events (see the listeners below) or by
calling `bot.get_cog("Legacy").award_points(...)` directly.
"""
import asyncio
import math
from datetime import datetime, timedelta, timezone

import discord
from discord.ext import commands

from classes.badges import Badge
from utils.checks import has_char


# Points per Ice Dragon stage, per party member
DRAGON_STAGE_POINTS = {
    "Frostbite Wyrm": 3,
    "Corrupted Ice Dragon": 5,
    "Permafrost": 8,
    "Absolute Zero": 12,
    "Deathwing": 12,
    "Void Tyrant": 12,
    "The Abyssal Maw": 12,
}

TOWER_FLOOR_POINTS = 2
TOWER_MILESTONE_BONUS = 5   # floors 5, 10, 15, ...
TOWER_FINALE_BONUS = 25     # floor 30
TOWER_PRESTIGE_POINTS = 50

LIVING_LEGEND_MIN_LIFETIME = 50_000
LIVING_LEGEND_FEAT_RATIO = 0.82
LIVING_LEGEND_RELIC_MILESTONE = "exalted"

LEGACY_SHOP = {
    "mystery5": {
        "name": "5x Mystery Crates",
        "cost": 300,
        "description": "Five mystery crates, straight from the vault.",
        "type": "crate",
        "crate": "mystery",
        "amount": 5,
        "weekly_limit": 2,
    },
    "goldpouch": {
        "name": "Legacy Gold Pouch",
        "cost": 500,
        "description": "A heavy pouch holding $250,000.",
        "type": "money",
        "amount": 250_000,
        "weekly_limit": 2,
    },
    "fortune": {
        "name": "Fortune Crate",
        "cost": 1_000,
        "description": "One fortune crate.",
        "type": "crate",
        "crate": "fortune",
        "amount": 1,
        "weekly_limit": 1,
    },
    "divine": {
        "name": "Divine Crate",
        "cost": 2_500,
        "description": "One divine crate.",
        "type": "crate",
        "crate": "divine",
        "amount": 1,
        "weekly_limit": 1,
    },
    "badge": {
        "name": "Living Legend Badge",
        "cost": 25_000,
        "description": "A permanent profile badge for masters of the realm. One per player.",
        "type": "badge",
        "badge": "LIVING_LEGEND",
    },
}


def living_legend_required_feat_count(total_feats: int) -> int:
    """Feat count required for the catalog's Living Legend rank."""
    return math.ceil(max(0, int(total_feats)) * LIVING_LEGEND_FEAT_RATIO)


def legacy_week_start(now: datetime | None = None) -> datetime:
    """Return Monday 00:00 UTC for weekly shop stock."""

    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    current = current.astimezone(timezone.utc)
    return (current - timedelta(days=current.weekday())).replace(
        hour=0, minute=0, second=0, microsecond=0
    )


def living_legend_gate_failures(progress: dict) -> tuple[str, ...]:
    """Human-readable unmet capstone requirements, without database access."""
    required_feats = living_legend_required_feat_count(progress.get("feat_total", 0))
    required_sets = max(0, int(progress.get("relic_total", 0)))
    failures = []
    if int(progress.get("lifetime", 0)) < LIVING_LEGEND_MIN_LIFETIME:
        failures.append(
            f"Lifetime LP: {int(progress.get('lifetime', 0)):,}/{LIVING_LEGEND_MIN_LIFETIME:,}"
        )
    if int(progress.get("feat_count", 0)) < required_feats:
        failures.append(
            f"Active Feats: {int(progress.get('feat_count', 0)):,}/{required_feats:,}"
        )
    if int(progress.get("relic_count", 0)) < required_sets:
        failures.append(
            f"Exalted Relic sets: {int(progress.get('relic_count', 0)):,}/{required_sets:,}"
        )
    return tuple(failures)


def living_legend_progress_lines(progress: dict) -> list[str]:
    required_feats = living_legend_required_feat_count(progress.get("feat_total", 0))
    rows = (
        (int(progress.get("lifetime", 0)), LIVING_LEGEND_MIN_LIFETIME, "lifetime LP"),
        (int(progress.get("feat_count", 0)), required_feats, "active Feats"),
        (
            int(progress.get("relic_count", 0)),
            int(progress.get("relic_total", 0)),
            "Exalted Relic sets",
        ),
    )
    return [
        f"{'✓' if current >= required else '○'} **{current:,}/{required:,}** {label}"
        for current, required, label in rows
    ]


def build_legacy_shop_embed(
    points: int,
    lifetime: int,
    weekly_purchases: dict[str, int],
    living_legend_progress: dict,
) -> discord.Embed:
    """Build the compact shop card without database or Discord I/O."""

    embed = discord.Embed(
        title="🏛️ Legacy Shop",
        description=(
            f"Balance **{int(points):,} LP**  ·  Lifetime **{int(lifetime):,} LP**\n"
            "Account rewards earned through long-term mastery."
        ),
        color=0xD4B95E,
    )
    for key, item in LEGACY_SHOP.items():
        if item["type"] == "badge":
            requirements = "\n".join(
                living_legend_progress_lines(living_legend_progress)
            )
            value = (
                f"{item['description']}\n{requirements}\n"
                f"`$legacy buy {key}`"
            )
        else:
            used = max(0, int(weekly_purchases.get(key, 0)))
            limit = int(item["weekly_limit"])
            stock_marker = "✓" if used < limit else "—"
            value = (
                f"{item['description']}\n"
                f"{stock_marker} Weekly stock **{min(used, limit)}/{limit}**  ·  "
                f"`$legacy buy {key}`"
            )
        embed.add_field(
            name=f"{item['name']} — {item['cost']:,} LP",
            value=value,
            inline=False,
        )
    embed.set_footer(text="Weekly stock resets Monday at 00:00 UTC")
    return embed


class Legacy(commands.Cog):
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
                async with conn.transaction():
                    await conn.execute(
                        """
                        CREATE TABLE IF NOT EXISTS legacy (
                            user_id BIGINT PRIMARY KEY,
                            points BIGINT NOT NULL DEFAULT 0,
                            lifetime BIGINT NOT NULL DEFAULT 0
                        );
                        """
                    )
                    await conn.execute(
                        """
                        CREATE TABLE IF NOT EXISTS legacy_purchases (
                            id SERIAL PRIMARY KEY,
                            user_id BIGINT NOT NULL,
                            item_key TEXT NOT NULL,
                            cost BIGINT NOT NULL,
                            purchased_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                        );
                        """
                    )

                    # The original table stored server-local wall time. Convert
                    # it once so Monday UTC stays exact in non-UTC databases.
                    await conn.execute(
                        "LOCK TABLE legacy_purchases IN ACCESS EXCLUSIVE MODE"
                    )
                    timestamp_type = await conn.fetchval(
                        """
                        SELECT data_type
                        FROM information_schema.columns
                        WHERE table_schema = 'public'
                          AND table_name = 'legacy_purchases'
                          AND column_name = 'purchased_at'
                        """
                    )
                    if timestamp_type == "timestamp without time zone":
                        await conn.execute(
                            """
                            ALTER TABLE legacy_purchases
                            ALTER COLUMN purchased_at TYPE TIMESTAMPTZ
                            USING purchased_at AT TIME ZONE current_setting('TIMEZONE')
                            """
                        )

                    await conn.execute(
                        """
                        CREATE INDEX IF NOT EXISTS legacy_purchases_user_item_time_idx
                        ON legacy_purchases (user_id, item_key, purchased_at);
                        """
                    )
            self._tables_ready = True

    async def cog_load(self):
        await self.ensure_tables()

    async def _living_legend_progress(self, conn, user_id: int, lifetime=None) -> dict:
        """Return the player's capstone progress without coupling cog lifecycles.

        Imports stay local because Feats and Relics both award LP through this cog.
        Missing tables simply report zero progress while the relevant cog starts.
        """

        from cogs.feats import ACTIVE_FEAT_KEYS
        from cogs.relics import RELIC_SETS

        user_id = int(user_id)
        if lifetime is None:
            lifetime = await conn.fetchval(
                "SELECT lifetime FROM legacy WHERE user_id = $1", user_id
            )

        active_feat_keys = sorted(ACTIVE_FEAT_KEYS)
        relic_set_keys = sorted(RELIC_SETS)
        feat_count = 0
        relic_count = 0

        if await conn.fetchval("SELECT to_regclass('public.feats') IS NOT NULL"):
            feat_count = await conn.fetchval(
                """
                SELECT COUNT(*)
                FROM feats
                WHERE user_id = $1 AND feat_key = ANY($2::TEXT[])
                """,
                user_id,
                active_feat_keys,
            )
        if await conn.fetchval(
            "SELECT to_regclass('public.relic_milestone_claims') IS NOT NULL"
        ):
            relic_count = await conn.fetchval(
                """
                SELECT COUNT(DISTINCT set_key)
                FROM relic_milestone_claims
                WHERE user_id = $1
                  AND milestone_key = $2
                  AND set_key = ANY($3::TEXT[])
                """,
                user_id,
                LIVING_LEGEND_RELIC_MILESTONE,
                relic_set_keys,
            )

        return {
            "lifetime": int(lifetime or 0),
            "feat_count": int(feat_count or 0),
            "feat_total": len(active_feat_keys),
            "relic_count": int(relic_count or 0),
            "relic_total": len(relic_set_keys),
        }

    # --- Award API ---------------------------------------------------------

    async def award_points(self, user_id: int, amount: int, conn=None):
        """Award legacy points to a user. Safe to call from any cog."""
        if amount <= 0:
            return
        await self.ensure_tables()
        query = """
            INSERT INTO legacy (user_id, points, lifetime)
            VALUES ($1, $2, $2)
            ON CONFLICT (user_id) DO UPDATE
            SET points = legacy.points + EXCLUDED.points,
                lifetime = legacy.lifetime + EXCLUDED.lifetime
        """
        if conn is not None:
            await conn.execute(query, user_id, amount)
        else:
            async with self.bot.pool.acquire() as conn2:
                await conn2.execute(query, user_id, amount)

    # --- Earn listeners ----------------------------------------------------

    @commands.Cog.listener()
    async def on_battletower_completion(
        self, ctx, success, level, level_name, name_value, minion1_name, minion2_name
    ):
        """Tower floor clears drip points; milestone floors pay extra."""
        if not success:
            return
        try:
            points = TOWER_FLOOR_POINTS
            milestone = False
            if level % 5 == 0:
                points += TOWER_MILESTONE_BONUS
                milestone = True
            if level == 30:
                points += TOWER_FINALE_BONUS
                milestone = True
            await self.award_points(ctx.author.id, points)
            if milestone:
                await ctx.send(
                    f"🏛️ **+{points} Legacy Points** for conquering floor {level}! "
                    "(`$legacy` to view)"
                )
        except Exception:
            pass  # never let reward bookkeeping break a battle flow

    @commands.Cog.listener()
    async def on_battletower_prestige(self, ctx, new_prestige):
        try:
            await self.award_points(ctx.author.id, TOWER_PRESTIGE_POINTS)
            await ctx.send(
                f"🏛️ **+{TOWER_PRESTIGE_POINTS} Legacy Points** for reaching "
                f"Prestige {new_prestige}!"
            )
        except Exception:
            pass

    @commands.Cog.listener()
    async def on_icedragon_victory(self, ctx, party_members, stage_name, dragon_level):
        try:
            points = DRAGON_STAGE_POINTS.get(stage_name, 3)
            for member in party_members:
                await self.award_points(member.id, points)
            await ctx.send(
                f"🏛️ Each party member earns **+{points} Legacy Points** "
                f"for slaying the {stage_name}!"
            )
        except Exception:
            pass

    # --- Commands ----------------------------------------------------------

    @commands.group(invoke_without_command=True)
    @has_char()
    async def legacy(self, ctx):
        """Your Legacy Points balance and how to earn more."""
        await self.ensure_tables()
        async with self.bot.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT points, lifetime FROM legacy WHERE user_id = $1", ctx.author.id
            )
        points = row["points"] if row else 0
        lifetime = row["lifetime"] if row else 0

        embed = discord.Embed(
            title="🏛️ Legacy",
            description=(
                f"**Balance:** {points:,} Legacy Points\n"
                f"**Lifetime earned:** {lifetime:,}"
            ),
            color=0xD4B95E,
        )
        embed.add_field(
            name="How to earn",
            value=(
                f"• Battle Tower floor clear: **+{TOWER_FLOOR_POINTS}** "
                f"(milestone floors **+{TOWER_MILESTONE_BONUS}**, "
                f"floor 30 **+{TOWER_FINALE_BONUS}**)\n"
                f"• Battle Tower prestige: **+{TOWER_PRESTIGE_POINTS}**\n"
                "• Ice Dragon kills: **+3 to +12** per party member, by stage"
            ),
            inline=False,
        )
        embed.set_footer(text="Spend them with $legacy shop")
        await ctx.send(embed=embed)

    @legacy.command(name="shop")
    @has_char()
    async def legacy_shop(self, ctx):
        """Browse the Legacy Shop."""
        await self.ensure_tables()
        week_start = legacy_week_start()
        async with self.bot.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT points, lifetime FROM legacy WHERE user_id = $1", ctx.author.id
            )
            points = int(row["points"] or 0) if row else 0
            lifetime = int(row["lifetime"] or 0) if row else 0
            purchase_rows = await conn.fetch(
                """
                SELECT item_key, COUNT(*)::INTEGER AS purchases
                FROM legacy_purchases
                WHERE user_id = $1
                  AND purchased_at >= $2
                GROUP BY item_key
                """,
                ctx.author.id,
                week_start,
            )
            living_legend_progress = await self._living_legend_progress(
                conn, ctx.author.id, lifetime=lifetime
            )
        weekly_purchases = {
            purchase["item_key"]: int(purchase["purchases"])
            for purchase in purchase_rows
        }

        embed = build_legacy_shop_embed(
            points,
            lifetime,
            weekly_purchases,
            living_legend_progress,
        )
        await ctx.send(embed=embed)

    @legacy.command(name="buy")
    @has_char()
    async def legacy_buy(self, ctx, item_key: str):
        """Buy an item from the Legacy Shop."""
        await self.ensure_tables()
        item_key = item_key.lower()
        item = LEGACY_SHOP.get(item_key)
        if not item:
            keys = ", ".join(f"`{k}`" for k in LEGACY_SHOP)
            return await ctx.send(f"Unknown item. Available: {keys}")

        async with self.bot.pool.acquire() as conn:
            async with conn.transaction():
                # Lock the row so concurrent purchases can't double-spend
                legacy_row = await conn.fetchrow(
                    "SELECT points, lifetime FROM legacy WHERE user_id = $1 FOR UPDATE",
                    ctx.author.id,
                )
                points = int(legacy_row["points"] or 0) if legacy_row else 0
                lifetime = int(legacy_row["lifetime"] or 0) if legacy_row else 0

                weekly_limit = item.get("weekly_limit")
                if weekly_limit is not None:
                    week_start = legacy_week_start()
                    weekly_purchases = await conn.fetchval(
                        """
                        SELECT COUNT(*)
                        FROM legacy_purchases
                        WHERE user_id = $1
                          AND item_key = $2
                          AND purchased_at >= $3
                        """,
                        ctx.author.id,
                        item_key,
                        week_start,
                    )
                    if int(weekly_purchases or 0) >= int(weekly_limit):
                        return await ctx.send(
                            f"You have used this week's **{weekly_limit}/{weekly_limit}** "
                            f"stock for {item['name']}. It resets Monday at 00:00 UTC."
                        )

                if item["type"] == "badge":
                    badge = Badge.from_string(item["badge"])
                    profile_row = await conn.fetchrow(
                        'SELECT "badges" FROM profile WHERE "user" = $1 FOR UPDATE;',
                        ctx.author.id,
                    )
                    if profile_row is None:
                        return await ctx.send("Profile not found.")
                    raw_badges = profile_row["badges"]
                    try:
                        current = Badge(0) if raw_badges is None else Badge.from_db(raw_badges)
                    except Exception:
                        current = Badge(0)
                    if current & badge:
                        return await ctx.send("You already own the Living Legend badge!")

                    progress = await self._living_legend_progress(
                        conn, ctx.author.id, lifetime=lifetime
                    )
                    failures = living_legend_gate_failures(progress)
                    if failures:
                        requirements = "\n".join(f"○ {failure}" for failure in failures)
                        return await ctx.send(
                            "**Living Legend is still locked.**\n" + requirements
                        )

                if points < item["cost"]:
                    return await ctx.send(
                        f"You need **{item['cost']:,} LP** for {item['name']}, "
                        f"but you only have **{points:,} LP**."
                    )

                if item["type"] == "badge":
                    badge = Badge.from_string(item["badge"])
                    await conn.execute(
                        'UPDATE profile SET "badges" = $1 WHERE "user" = $2;',
                        (current | badge).to_db(),
                        ctx.author.id,
                    )
                elif item["type"] == "crate":
                    crate = item["crate"]
                    await conn.execute(
                        f"UPDATE profile SET crates_{crate} = crates_{crate} + $1 "
                        'WHERE "user" = $2;',
                        item["amount"],
                        ctx.author.id,
                    )
                elif item["type"] == "money":
                    await conn.execute(
                        'UPDATE profile SET money = money + $1 WHERE "user" = $2;',
                        item["amount"],
                        ctx.author.id,
                    )

                await conn.execute(
                    "UPDATE legacy SET points = points - $1 WHERE user_id = $2",
                    item["cost"],
                    ctx.author.id,
                )
                await conn.execute(
                    "INSERT INTO legacy_purchases (user_id, item_key, cost) VALUES ($1, $2, $3)",
                    ctx.author.id,
                    item_key,
                    item["cost"],
                )

        await ctx.send(
            f"🏛️ You bought **{item['name']}** for **{item['cost']:,} Legacy Points**!"
        )

    @legacy.command(name="top", aliases=["leaderboard", "board"])
    async def legacy_top(self, ctx):
        """The all-time Legacy leaderboard."""
        await self.ensure_tables()
        async with self.bot.pool.acquire() as conn:
            top = await conn.fetch(
                """
                SELECT user_id, lifetime,
                       RANK() OVER (ORDER BY lifetime DESC) AS rank
                FROM legacy
                ORDER BY lifetime DESC
                LIMIT 10
                """
            )
            user_rank = await conn.fetchrow(
                """
                WITH rankings AS (
                    SELECT user_id, lifetime,
                           RANK() OVER (ORDER BY lifetime DESC) AS rank
                    FROM legacy
                )
                SELECT * FROM rankings WHERE user_id = $1
                """,
                ctx.author.id,
            )

        embed = discord.Embed(title="🏛️ Legacy Leaderboard", color=0xD4B95E)
        if top:
            embed.description = "\n".join(
                f"{entry['rank']}. <@{entry['user_id']}> — {entry['lifetime']:,} lifetime LP"
                for entry in top
            )
        else:
            embed.description = "Nobody has earned Legacy Points yet. Be the first!"
        if user_rank and not any(e["user_id"] == ctx.author.id for e in top):
            embed.add_field(
                name="Your Rank",
                value=f"#{user_rank['rank']} — {user_rank['lifetime']:,} lifetime LP",
                inline=False,
            )
        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(Legacy(bot))

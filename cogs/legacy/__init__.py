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
import logging

import discord
from discord.ext import commands

from classes.badges import Badge
from cogs.legacy.shop import (
    LEGACY_SHOP,
    LIVING_LEGEND_RELIC_MILESTONE,
    build_legacy_shop_embed,
    legacy_week_start,
    living_legend_gate_failures,
)
from utils.checks import has_char


logger = logging.getLogger(__name__)


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

CRATE_REWARD_COLUMNS = {
    "mystery": "crates_mystery",
    "fortune": "crates_fortune",
    "divine": "crates_divine",
}


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

                    # Older installations stored server-local wall time. Avoid
                    # taking an exclusive table lock on every normal startup.
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
                            "LOCK TABLE legacy_purchases IN ACCESS EXCLUSIVE MODE"
                        )
                        # Another shard may have completed the migration while
                        # this connection waited for the lock.
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

    async def _purchase_shop_item(self, conn, user_id: int, item) -> tuple[bool, str]:
        """Validate and apply one shop purchase in a single transaction."""

        user_id = int(user_id)
        async with conn.transaction():
            # Profile -> legacy is the lock order used by milestone rewards too.
            # Keeping it consistent prevents a badge purchase and a reward grant
            # from deadlocking one another.
            profile_row = await conn.fetchrow(
                'SELECT "badges" FROM profile WHERE "user" = $1 FOR UPDATE;',
                user_id,
            )
            if profile_row is None:
                return False, "Profile not found."

            legacy_row = await conn.fetchrow(
                "SELECT points, lifetime FROM legacy WHERE user_id = $1 FOR UPDATE",
                user_id,
            )
            points = int(legacy_row["points"] or 0) if legacy_row else 0
            lifetime = int(legacy_row["lifetime"] or 0) if legacy_row else 0

            if item.weekly_limit is not None:
                weekly_purchases = await conn.fetchval(
                    """
                    SELECT COUNT(*)
                    FROM legacy_purchases
                    WHERE user_id = $1
                      AND item_key = $2
                      AND purchased_at >= $3
                    """,
                    user_id,
                    item.key,
                    legacy_week_start(),
                )
                if int(weekly_purchases or 0) >= item.weekly_limit:
                    return (
                        False,
                        f"This week's stock for **{item.name}** is sold out. "
                        "It resets Monday at 00:00 UTC.",
                    )

            current_badges = None
            badge = None
            if item.reward_type == "badge":
                badge = Badge.from_string(item.badge)
                if badge is None:
                    logger.error("Legacy Shop has an invalid badge reward: %s", item.badge)
                    return False, "That reward is temporarily unavailable."
                raw_badges = profile_row["badges"]
                try:
                    current_badges = (
                        Badge(0) if raw_badges is None else Badge.from_db(raw_badges)
                    )
                except (AttributeError, TypeError, ValueError):
                    logger.exception("Could not decode badges for user %s", user_id)
                    return (
                        False,
                        "Your badge data could not be read. No Legacy Points were spent.",
                    )
                if current_badges & badge:
                    return False, "You already own the Living Legend badge!"

                progress = await self._living_legend_progress(
                    conn, user_id, lifetime=lifetime
                )
                failures = living_legend_gate_failures(progress)
                if failures:
                    requirements = "\n".join(f"○ {failure}" for failure in failures)
                    return (
                        False,
                        "**Living Legend is still locked.**\n" + requirements,
                    )

            if points < item.cost:
                return (
                    False,
                    f"You need **{item.cost:,} LP** for {item.name}, "
                    f"but you only have **{points:,} LP**.",
                )

            remaining_points = await conn.fetchval(
                """
                UPDATE legacy
                SET points = points - $1
                WHERE user_id = $2 AND points >= $1
                RETURNING points
                """,
                item.cost,
                user_id,
            )
            if remaining_points is None:
                return False, "Your Legacy Point balance changed. Please try again."

            if item.reward_type == "badge":
                await conn.execute(
                    'UPDATE profile SET "badges" = $1 WHERE "user" = $2;',
                    (current_badges | badge).to_db(),
                    user_id,
                )
            elif item.reward_type == "crate":
                column = CRATE_REWARD_COLUMNS.get(item.crate)
                if column is None:
                    raise RuntimeError(f"Unsupported Legacy Shop crate: {item.crate}")
                await conn.execute(
                    f"UPDATE profile SET {column} = {column} + $1 "
                    'WHERE "user" = $2;',
                    item.amount,
                    user_id,
                )
            elif item.reward_type == "money":
                await conn.execute(
                    'UPDATE profile SET money = money + $1 WHERE "user" = $2;',
                    item.amount,
                    user_id,
                )
            else:
                raise RuntimeError(
                    f"Unsupported Legacy Shop reward type: {item.reward_type}"
                )

            await conn.execute(
                """
                INSERT INTO legacy_purchases (user_id, item_key, cost)
                VALUES ($1, $2, $3)
                """,
                user_id,
                item.key,
                item.cost,
            )

        return (
            True,
            f"🏛️ You bought **{item.name}** for **{item.cost:,} Legacy Points**! "
            f"You have **{int(remaining_points):,} LP** left.",
        )

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
                    f"(`{ctx.clean_prefix}legacy` to view)"
                )
        except Exception:
            logger.exception("Legacy reward failed for Battle Tower completion")

    @commands.Cog.listener()
    async def on_battletower_prestige(self, ctx, new_prestige):
        try:
            await self.award_points(ctx.author.id, TOWER_PRESTIGE_POINTS)
            await ctx.send(
                f"🏛️ **+{TOWER_PRESTIGE_POINTS} Legacy Points** for reaching "
                f"Prestige {new_prestige}!"
            )
        except Exception:
            logger.exception("Legacy reward failed for Battle Tower prestige")

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
            logger.exception("Legacy reward failed for Ice Dragon victory")

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
        embed.set_footer(text=f"Spend them with {ctx.clean_prefix}legacy shop")
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
            prefix=ctx.clean_prefix,
        )
        await ctx.send(embed=embed)

    @legacy.command(name="buy")
    @has_char()
    async def legacy_buy(self, ctx, item_key: str):
        """Buy an item from the Legacy Shop."""
        await self.ensure_tables()
        item_key = item_key.strip().lower()
        item = LEGACY_SHOP.get(item_key)
        if not item:
            keys = ", ".join(f"`{k}`" for k in LEGACY_SHOP)
            return await ctx.send(f"Unknown item. Available: {keys}")

        async with self.bot.pool.acquire() as conn:
            _, message = await self._purchase_shop_item(conn, ctx.author.id, item)
        await ctx.send(message)

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

"""Starforging — salvage endgame gear into Essence and add item stars."""
from __future__ import annotations

import asyncio
import random
from datetime import datetime
from decimal import Decimal

import discord
from discord.ext import commands

from classes.endgame import (
    STARFORGE_MAX_STARS,
    is_starforge_max_item,
    is_starforge_salvage_eligible,
    item_max_stat,
    starforge_bonus_pct,
    starforge_cost,
    starforge_essence_yield,
    starforge_next_star,
    starforge_pity_fails,
    starforge_success_chance,
    starforged_name,
)
from utils.checks import has_char


class Starforge(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self._tables_ready = False
        self._table_lock = asyncio.Lock()
        self._pending_confirms = set()

    async def _confirm_exclusive(self, ctx, prompt):
        """One pending confirm dialog per user — blocks dialog-stacking spam.

        Returns True/False like ctx.confirm, or None if a dialog is already open
        (in which case the caller should simply return; the user was told).
        """
        if ctx.author.id in self._pending_confirms:
            await ctx.send(
                "You already have a pending Starforge confirmation — answer that one first."
            )
            return None
        self._pending_confirms.add(ctx.author.id)
        try:
            return await ctx.confirm(prompt)
        finally:
            self._pending_confirms.discard(ctx.author.id)

    async def ensure_tables(self):
        if self._tables_ready:
            return
        async with self._table_lock:
            if self._tables_ready:
                return
            async with self.bot.pool.acquire() as conn:
                await conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS starforge_essence (
                        user_id BIGINT PRIMARY KEY,
                        essence BIGINT NOT NULL DEFAULT 0,
                        updated_at TIMESTAMP NOT NULL DEFAULT NOW()
                    );
                    """
                )
                await conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS starforged_items (
                        item_id BIGINT PRIMARY KEY,
                        stars INT NOT NULL DEFAULT 0,
                        fail_count INT NOT NULL DEFAULT 0,
                        essence_spent BIGINT NOT NULL DEFAULT 0,
                        gold_spent BIGINT NOT NULL DEFAULT 0,
                        forged_at TIMESTAMP NOT NULL DEFAULT NOW(),
                        updated_at TIMESTAMP NOT NULL DEFAULT NOW()
                    );
                    """
                )
                await conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS starforge_salvage_log (
                        id SERIAL PRIMARY KEY,
                        user_id BIGINT NOT NULL,
                        item_id BIGINT NOT NULL,
                        item_name TEXT NOT NULL,
                        essence BIGINT NOT NULL,
                        salvaged_at TIMESTAMP NOT NULL DEFAULT NOW()
                    );
                    """
                )
            self._tables_ready = True

    async def cog_load(self):
        await self.ensure_tables()

    async def _essence_balance(self, user_id: int, conn=None) -> int:
        await self.ensure_tables()
        query = "SELECT essence FROM starforge_essence WHERE user_id = $1"
        if conn is not None:
            return int(await conn.fetchval(query, user_id) or 0)
        async with self.bot.pool.acquire() as conn2:
            return int(await conn2.fetchval(query, user_id) or 0)

    async def _soulbound_item_exists(self, item_id: int, conn) -> bool:
        table_exists = await conn.fetchval(
            "SELECT to_regclass('public.soulbound') IS NOT NULL;"
        )
        if not table_exists:
            return False
        return bool(
            await conn.fetchval(
                """
                SELECT 1
                FROM soulbound AS s
                JOIN allitems AS i
                  ON i."id" = s.item_id
                 AND i."owner" = s.user_id
                WHERE s.item_id = $1
                """,
                item_id,
            )
        )

    async def _fetch_owned_inventory_item(self, conn, user_id: int, item_id: int, *, lock=False):
        suffix = " FOR UPDATE OF ai, i" if lock else ""
        return await conn.fetchrow(
            """
            SELECT ai.*, i.equipped, i.locked,
                   COALESCE(sf.stars, 0) AS stars,
                   COALESCE(sf.fail_count, 0) AS fail_count
            FROM allitems ai
            JOIN inventory i ON i.item = ai.id
            LEFT JOIN starforged_items sf ON sf.item_id = ai.id
            WHERE ai.owner = $1 AND ai.id = $2
            """ + suffix,
            user_id,
            item_id,
        )

    def _primary_stat_label(self, item) -> tuple[str, int]:
        if str(item["type"]) == "Shield":
            return "armor", int(item["armor"] or 0)
        return "damage", int(item["damage"] or 0)

    def _item_summary(self, item) -> str:
        stat_name, stat_value = self._primary_stat_label(item)
        stars = int(item["stars"] or 0)
        bonus_pct = starforge_bonus_pct(stars)
        return (
            f"**{item['name']}** (`{item['id']}`)\n"
            f"{item['type']} · {stat_value} {stat_name} · {item['hand']} hand · "
            f"★{stars}/{STARFORGE_MAX_STARS} "
            f"(+{float(bonus_pct * 100):.1f}% item stats)"
        )

    @commands.group(name="starforge", aliases=["sf"], invoke_without_command=True)
    @has_char()
    async def starforge(self, ctx):
        """View Starforge balance and help."""
        await self.ensure_tables()
        balance = await self._essence_balance(ctx.author.id)
        embed = discord.Embed(
            title="★ Starforge",
            description=(
                "Turn max or near-max gear into **Essence**, then spend Essence and gold "
                "to forge stars onto max gear. Stars are item-only stat bonuses."
            ),
            color=0xF39C12,
        )
        embed.add_field(name="Essence", value=f"**{balance:,}**", inline=True)
        embed.add_field(
            name="Commands",
            value=(
                "`$starforge balance` — view your Essence\n"
                "`$starforge item <item_id>` — inspect forge status\n"
                "`$starforge salvage <item_id>` — destroy eligible gear for Essence\n"
                "`$starforge upgrade <item_id>` — attempt the next star"
            ),
            inline=False,
        )
        embed.add_field(
            name="Rules",
            value=(
                "Salvage consumes the fuel item forever. Upgrade attempts never destroy "
                "or downgrade the target item. Failed attempts build pity."
            ),
            inline=False,
        )
        await ctx.send(embed=embed)

    @starforge.command(name="balance", aliases=["bal", "essence", "essense"])
    @has_char()
    async def starforge_balance(self, ctx):
        """View your Starforge Essence balance."""
        await self.ensure_tables()
        balance = await self._essence_balance(ctx.author.id)
        await ctx.send(f"★ {ctx.author.mention} has **{balance:,} Essence**.")

    @starforge.command(name="item")
    @has_char()
    async def starforge_item(self, ctx, item_id: int):
        await self.ensure_tables()
        async with self.bot.pool.acquire() as conn:
            item = await self._fetch_owned_inventory_item(conn, ctx.author.id, item_id)
            if not item:
                return await ctx.send("You do not own an inventory item with that ID.")
            is_soulbound = await self._soulbound_item_exists(item_id, conn)
            balance = await self._essence_balance(ctx.author.id, conn=conn)

        stars = int(item["stars"] or 0)
        next_star = starforge_next_star(stars)
        embed = discord.Embed(title="★ Starforge Item", color=0xF39C12)
        embed.description = self._item_summary(item)
        embed.add_field(
            name="Status",
            value=(
                f"Equipped: **{'yes' if item['equipped'] else 'no'}**\n"
                f"Locked: **{'yes' if item['locked'] else 'no'}**\n"
                f"Soulbound: **{'yes' if is_soulbound else 'no'}**"
            ),
            inline=False,
        )
        stat_name, stat_value = self._primary_stat_label(item)
        max_stat = item_max_stat(dict(item))
        embed.add_field(
            name="Stat Gate",
            value=(
                f"Current: **{stat_value} {stat_name}**\n"
                f"Salvage starts at: **{max_stat - 5} {stat_name}**\n"
                f"Starforge upgrade needs: **{max_stat} {stat_name}**"
            ),
            inline=False,
        )
        embed.add_field(
            name="Salvage",
            value=(
                f"Eligible for **{starforge_essence_yield(dict(item))} Essence**"
                if is_starforge_salvage_eligible(dict(item)) and not stars
                else "Not eligible. Salvage needs near-max unstarred gear."
            ),
            inline=False,
        )
        if next_star is None:
            embed.add_field(name="Next Star", value="Fully starforged.", inline=False)
        else:
            essence_cost, gold_cost = starforge_cost(next_star)
            chance = starforge_success_chance(next_star)
            pity = starforge_pity_fails(next_star)
            embed.add_field(
                name="Next Star",
                value=(
                    f"★{next_star}: **{essence_cost:,} Essence** + **${gold_cost:,}**\n"
                    f"Chance: **{float(chance * 100):.0f}%** · "
                    f"Pity: guaranteed after **{pity}** failed attempt(s)\n"
                    f"Your Essence: **{balance:,}**"
                ),
                inline=False,
            )
        await ctx.send(embed=embed)

    @starforge.command(name="salvage")
    @has_char()
    async def starforge_salvage(self, ctx, item_id: int):
        """Destroy max or near-max gear for Essence."""
        await self.ensure_tables()
        async with self.bot.pool.acquire() as conn:
            item = await self._fetch_owned_inventory_item(conn, ctx.author.id, item_id)
            if not item:
                return await ctx.send("You do not own an inventory item with that ID.")
            if item["equipped"]:
                return await ctx.send("Unequip that item before salvaging it.")
            if item["locked"]:
                return await ctx.send("Unlock that item before salvaging it.")
            if int(item["stars"] or 0) > 0:
                return await ctx.send("Starforged items cannot be salvaged.")
            if await self._soulbound_item_exists(item_id, conn):
                return await ctx.send("Soulbound items cannot be salvaged.")
            if not is_starforge_salvage_eligible(dict(item)):
                stat_name, stat_value = self._primary_stat_label(item)
                max_stat = item_max_stat(dict(item))
                return await ctx.send(
                    f"Only max or near-max gear can be salvaged into Essence. "
                    f"That item is **{stat_value}/{max_stat} {stat_name}**; "
                    f"salvage starts at **{max_stat - 5}**."
                )
            essence = starforge_essence_yield(dict(item))

        confirmed = await self._confirm_exclusive(
            ctx,
            f"Salvage **{item['name']}** for **{essence:,} Essence**?\n"
            "This destroys the item forever.",
        )
        if confirmed is None:
            return
        if not confirmed:
            return await ctx.send("Salvage cancelled.")

        async with self.bot.pool.acquire() as conn:
            async with conn.transaction():
                locked = await self._fetch_owned_inventory_item(
                    conn, ctx.author.id, item_id, lock=True
                )
                if not locked:
                    return await ctx.send("That item is no longer in your inventory.")
                if locked["equipped"] or locked["locked"]:
                    return await ctx.send("That item became equipped or locked. Salvage cancelled.")
                if int(locked["stars"] or 0) > 0:
                    return await ctx.send("That item is now starforged. Salvage cancelled.")
                if await self._soulbound_item_exists(item_id, conn):
                    return await ctx.send("That item is now soulbound. Salvage cancelled.")
                if not is_starforge_salvage_eligible(dict(locked)):
                    stat_name, stat_value = self._primary_stat_label(locked)
                    max_stat = item_max_stat(dict(locked))
                    return await ctx.send(
                        f"That item is no longer eligible for salvage "
                        f"({stat_value}/{max_stat} {stat_name})."
                    )

                essence = starforge_essence_yield(dict(locked))
                await conn.execute(
                    """
                    INSERT INTO starforge_essence (user_id, essence, updated_at)
                    VALUES ($1, $2, NOW())
                    ON CONFLICT (user_id) DO UPDATE
                    SET essence = starforge_essence.essence + EXCLUDED.essence,
                        updated_at = NOW()
                    """,
                    ctx.author.id,
                    essence,
                )
                await conn.execute(
                    """
                    INSERT INTO starforge_salvage_log (user_id, item_id, item_name, essence)
                    VALUES ($1, $2, $3, $4)
                    """,
                    ctx.author.id,
                    item_id,
                    locked["name"],
                    essence,
                )
                await conn.execute("DELETE FROM starforged_items WHERE item_id = $1", item_id)
                await self.bot.delete_items([item_id], conn=conn)

        await ctx.send(f"★ Salvaged **{item['name']}** for **{essence:,} Essence**.")

    @starforge.command(name="upgrade", aliases=["forge"])
    @has_char()
    async def starforge_upgrade(self, ctx, item_id: int):
        """Attempt to add the next star to a max item."""
        await self.ensure_tables()
        async with self.bot.pool.acquire() as conn:
            item = await self._fetch_owned_inventory_item(conn, ctx.author.id, item_id)
            if not item:
                return await ctx.send("You do not own an inventory item with that ID.")
            if not is_starforge_max_item(dict(item)):
                stat_name, stat_value = self._primary_stat_label(item)
                max_stat = item_max_stat(dict(item))
                return await ctx.send(
                    f"Only maxed gear can be starforged. "
                    f"That item is **{stat_value}/{max_stat} {stat_name}**."
                )
            stars = int(item["stars"] or 0)
            next_star = starforge_next_star(stars)
            if next_star is None:
                return await ctx.send("That item is already ★10.")
            essence_cost, gold_cost = starforge_cost(next_star)
            balance = await self._essence_balance(ctx.author.id, conn=conn)
            money = int(
                await conn.fetchval(
                    'SELECT money FROM profile WHERE "user" = $1',
                    ctx.author.id,
                )
                or 0
            )
            if balance < essence_cost:
                return await ctx.send(
                    f"You need **{essence_cost:,} Essence** for ★{next_star}, "
                    f"but you only have **{balance:,}**."
                )
            if money < gold_cost:
                return await ctx.send(
                    f"You need **${gold_cost:,}** for ★{next_star}, "
                    f"but you only have **${money:,}**."
                )

        chance = starforge_success_chance(next_star)
        pity = starforge_pity_fails(next_star)
        confirmed = await self._confirm_exclusive(
            ctx,
            f"Attempt ★{next_star} on **{item['name']}**?\n"
            f"Cost: **{essence_cost:,} Essence** and **${gold_cost:,}**.\n"
            f"Success chance: **{float(chance * 100):.0f}%**. "
            f"Pity guarantees after **{pity}** failed attempt(s).",
        )
        if confirmed is None:
            return
        if not confirmed:
            return await ctx.send("Forge attempt cancelled.")

        now = datetime.utcnow()
        async with self.bot.pool.acquire() as conn:
            async with conn.transaction():
                locked = await self._fetch_owned_inventory_item(
                    conn, ctx.author.id, item_id, lock=True
                )
                if not locked:
                    return await ctx.send("That item is no longer in your inventory.")
                if not is_starforge_max_item(dict(locked)):
                    stat_name, stat_value = self._primary_stat_label(locked)
                    max_stat = item_max_stat(dict(locked))
                    return await ctx.send(
                        f"That item is no longer maxed "
                        f"({stat_value}/{max_stat} {stat_name})."
                    )
                stars = int(locked["stars"] or 0)
                fail_count = int(locked["fail_count"] or 0)
                next_star = starforge_next_star(stars)
                if next_star is None:
                    return await ctx.send("That item is already ★10.")
                essence_cost, gold_cost = starforge_cost(next_star)
                balance = await conn.fetchval(
                    "SELECT essence FROM starforge_essence WHERE user_id = $1 FOR UPDATE",
                    ctx.author.id,
                )
                balance = int(balance or 0)
                money = int(
                    await conn.fetchval(
                        'SELECT money FROM profile WHERE "user" = $1 FOR UPDATE',
                        ctx.author.id,
                    )
                    or 0
                )
                if balance < essence_cost:
                    return await ctx.send("Your Essence balance changed. Try again.")
                if money < gold_cost:
                    return await ctx.send("Your gold balance changed. Try again.")

                forced = fail_count + 1 >= starforge_pity_fails(next_star)
                roll = Decimal(str(random.random()))
                success = forced or roll < starforge_success_chance(next_star)
                await conn.execute(
                    """
                    UPDATE starforge_essence
                    SET essence = essence - $1, updated_at = NOW()
                    WHERE user_id = $2
                    """,
                    essence_cost,
                    ctx.author.id,
                )
                await conn.execute(
                    'UPDATE profile SET money = money - $1 WHERE "user" = $2',
                    gold_cost,
                    ctx.author.id,
                )

                if success:
                    new_stars = next_star
                    new_name = starforged_name(locked["name"], new_stars)
                    await conn.execute(
                        """
                        INSERT INTO starforged_items
                            (item_id, stars, fail_count, essence_spent, gold_spent, forged_at, updated_at)
                        VALUES ($1, $2, 0, $3, $4, $5, NOW())
                        ON CONFLICT (item_id) DO UPDATE
                        SET stars = EXCLUDED.stars,
                            fail_count = 0,
                            essence_spent = starforged_items.essence_spent + EXCLUDED.essence_spent,
                            gold_spent = starforged_items.gold_spent + EXCLUDED.gold_spent,
                            updated_at = NOW()
                        """,
                        item_id,
                        new_stars,
                        essence_cost,
                        gold_cost,
                        now,
                    )
                    await conn.execute(
                        'UPDATE allitems SET "name" = $1 WHERE "id" = $2',
                        new_name,
                        item_id,
                    )
                else:
                    new_stars = stars
                    await conn.execute(
                        """
                        INSERT INTO starforged_items
                            (item_id, stars, fail_count, essence_spent, gold_spent, forged_at, updated_at)
                        VALUES ($1, $2, 1, $3, $4, $5, NOW())
                        ON CONFLICT (item_id) DO UPDATE
                        SET fail_count = starforged_items.fail_count + 1,
                            essence_spent = starforged_items.essence_spent + EXCLUDED.essence_spent,
                            gold_spent = starforged_items.gold_spent + EXCLUDED.gold_spent,
                            updated_at = NOW()
                        """,
                        item_id,
                        stars,
                        essence_cost,
                        gold_cost,
                        now,
                    )
                    fail_count += 1

        if success:
            self.bot.dispatch(
                "starforge_success",
                ctx,
                int(item_id),
                int(new_stars),
            )
            await ctx.send(
                f"★ **Starforge success!** {ctx.author.mention}'s item is now "
                f"**★{new_stars}** (+{float(starforge_bonus_pct(new_stars) * 100):.1f}% item stats)."
            )
        else:
            remaining = max(0, starforge_pity_fails(next_star) - fail_count)
            await ctx.send(
                f"☆ The forge cools. **★{next_star}** failed, but pity grew. "
                f"Guaranteed after **{remaining}** more failed attempt(s)."
            )


async def setup(bot):
    await bot.add_cog(Starforge(bot))

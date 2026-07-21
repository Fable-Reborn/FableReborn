"""
Soulbound Weapons — bind one item and let it grow with you.

A bound weapon earns XP from your victories (tower floors, dragon kills,
adventures, raid wins) and awakens through title ranks. One bond per player;
rebinding to a different item resets the bond's XP — your weapon's legend is
not transferable.

Awakening ranks now grant tiny item-only stat bonuses. The bonus applies only
when the bound item is still owned and equipped.
"""
import asyncio
from datetime import datetime

import discord
from discord.ext import commands

from classes.endgame import (
    SOULBOUND_RANKS,
    soulbound_bonus_pct_for_level,
    soulbound_level_from_xp,
    soulbound_rank_for_level,
    soulbound_xp_for_level,
)
from utils.checks import has_char


XP_TOWER_FLOOR = 15
XP_DRAGON_KILL = 25
XP_ADVENTURE = 10
XP_RAID_WIN = 20


class Soulbound(commands.Cog):
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
                "You already have a pending soulbind confirmation — answer that one first."
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
                    CREATE TABLE IF NOT EXISTS soulbound (
                        user_id BIGINT PRIMARY KEY,
                        item_id BIGINT NOT NULL,
                        xp BIGINT NOT NULL DEFAULT 0,
                        bonded_at TIMESTAMP NOT NULL DEFAULT NOW()
                    );
                    """
                )
            self._tables_ready = True

    async def cog_load(self):
        await self.ensure_tables()

    # --- XP awarding ------------------------------------------------------------

    async def award_xp(self, user_id: int, amount: int, channel=None):
        """Add XP to the user's bond, announcing new awakening ranks."""
        if amount <= 0:
            return
        await self.ensure_tables()
        async with self.bot.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                UPDATE soulbound AS s SET xp = s.xp + $1
                WHERE s.user_id = $2
                  AND EXISTS (
                      SELECT 1 FROM allitems AS i
                      WHERE i."id" = s.item_id
                        AND i."owner" = s.user_id
                  )
                RETURNING s.item_id, s.xp
                """,
                amount,
                user_id,
            )
            if not row:
                return  # no bond
            old_level = soulbound_level_from_xp(row["xp"] - amount)
            new_level = soulbound_level_from_xp(row["xp"])
            if new_level <= old_level:
                return
            # Let other systems (feats, ...) react to the level-up
            self.bot.dispatch("soulbound_awakened", user_id, new_level, channel)
            crossed = [r for r in SOULBOUND_RANKS if old_level < r[0] <= new_level]
            if not crossed or channel is None:
                return
            item = await conn.fetchrow(
                'SELECT "name" FROM allitems WHERE "id" = $1;', row["item_id"]
            )
        weapon_name = item["name"] if item else "The lost weapon"
        _, title, flavor, bonus_pct = crossed[-1]
        try:
            await channel.send(
                f"⚡ <@{user_id}>'s **{weapon_name}** awakens to a new rank: "
                f"**{title}** (level {new_level})!\n*{flavor}*\n"
                f"Equipped soulbound bonus: **+{float(bonus_pct * 100):.1f}%** item stats."
            )
        except Exception:
            pass

    # --- XP listeners --------------------------------------------------------------

    @commands.Cog.listener()
    async def on_battletower_completion(
        self, ctx, success, level=None, level_name=None,
        name_value=None, minion1_name=None, minion2_name=None,
    ):
        if not success:
            return
        try:
            await self.award_xp(ctx.author.id, XP_TOWER_FLOOR, ctx.channel)
        except Exception:
            pass

    @commands.Cog.listener()
    async def on_icedragon_victory(self, ctx, party_members, stage_name, dragon_level):
        try:
            for member in party_members:
                await self.award_xp(member.id, XP_DRAGON_KILL, ctx.channel)
        except Exception:
            pass

    @commands.Cog.listener()
    async def on_adventure_completion(self, ctx, iscompleted):
        if not iscompleted:
            return
        try:
            await self.award_xp(ctx.author.id, XP_ADVENTURE, ctx.channel)
        except Exception:
            pass

    @commands.Cog.listener()
    async def on_raid_favor(self, ctx, participant_ids, success):
        if not success:
            return
        try:
            channel = getattr(ctx, "channel", None)
            for user_id in dict.fromkeys(participant_ids):
                await self.award_xp(user_id, XP_RAID_WIN, channel)
        except Exception:
            pass

    # --- Commands ---------------------------------------------------------------------

    @commands.command()
    @has_char()
    async def soulbind(self, ctx, item_id: int):
        """Bind your soul to one of your items. Rebinding resets the bond's XP."""
        await self.ensure_tables()
        async with self.bot.pool.acquire() as conn:
            item = await conn.fetchrow(
                'SELECT "id", "name", "type" FROM allitems WHERE "id" = $1 AND "owner" = $2;',
                item_id,
                ctx.author.id,
            )
            if not item:
                return await ctx.send(
                    "You don't own an item with that ID. Check `$inventory` for your item IDs."
                )
            existing = await conn.fetchrow(
                "SELECT item_id, xp FROM soulbound WHERE user_id = $1", ctx.author.id
            )

        if existing and existing["item_id"] == item_id:
            return await ctx.send("Your soul is already bound to that weapon.")

        if existing:
            old_level = soulbound_level_from_xp(existing["xp"])
            confirmed = await self._confirm_exclusive(
                ctx,
                f"You already have a soulbound weapon at level **{old_level}**. "
                f"Binding **{item['name']}** will sever that bond and its legend "
                "is lost forever (XP resets to 0). Proceed?",
            )
            if confirmed is None:
                return
            if not confirmed:
                return await ctx.send("The bond remains unbroken.")

        async with self.bot.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO soulbound (user_id, item_id, xp, bonded_at)
                VALUES ($1, $2, 0, $3)
                ON CONFLICT (user_id) DO UPDATE
                SET item_id = EXCLUDED.item_id, xp = 0, bonded_at = EXCLUDED.bonded_at
                """,
                ctx.author.id,
                item_id,
                datetime.utcnow(),
            )
        await ctx.send(
            f"🔗 **The bond is forged.** {ctx.author.mention}, your soul is now bound to "
            f"**{item['name']}**. It will grow with every victory — tower floors, dragon "
            "kills, adventures, and raids all feed its legend. View it with `$soulbound`."
        )

    @commands.command(aliases=["sb", "bond"])
    @has_char()
    async def soulbound(self, ctx):
        """View your soulbound weapon's legend."""
        await self.ensure_tables()
        async with self.bot.pool.acquire() as conn:
            bond = await conn.fetchrow(
                "SELECT item_id, xp, bonded_at FROM soulbound WHERE user_id = $1",
                ctx.author.id,
            )
            if not bond:
                return await ctx.send(
                    "You have no soulbound weapon. Choose one with `$soulbind <item id>`."
                )
            item = await conn.fetchrow(
                'SELECT "name", "type", "damage", "armor", "element" FROM allitems '
                'WHERE "id" = $1 AND "owner" = $2;',
                bond["item_id"],
                ctx.author.id,
            )

        if not item:
            return await ctx.send(
                "💔 **The bond is severed** — the weapon has left your possession. "
                "Its legend is lost. Forge a new bond with `$soulbind <item id>`."
            )

        xp = bond["xp"]
        level = soulbound_level_from_xp(xp)
        next_level_xp = soulbound_xp_for_level(level + 1)
        prev_level_xp = soulbound_xp_for_level(level)
        span = max(1, next_level_xp - prev_level_xp)
        progress = int(((xp - prev_level_xp) / span) * 14)
        bar = "█" * progress + "░" * (14 - progress)

        rank = soulbound_rank_for_level(level)
        title = rank[0] if rank else "Dormant"
        flavor = rank[1] if rank else "The weapon sleeps. Win battles to wake it."
        bonus_pct = soulbound_bonus_pct_for_level(level)
        next_rank = next((r for r in SOULBOUND_RANKS if r[0] > level), None)

        stat = (
            f"{float(item['damage']):,.0f} damage"
            if float(item["damage"]) > 0
            else f"{float(item['armor']):,.0f} armor"
        )
        embed = discord.Embed(
            title=f"🔗 {item['name']} — {title}",
            description=f"*{flavor}*",
            color=0x71368A,
        )
        embed.add_field(
            name="Legend",
            value=(
                f"**Level {level}** · {xp:,} XP\n"
                f"`{bar}` {xp - prev_level_xp:,}/{span:,} to level {level + 1}"
            ),
            inline=False,
        )
        embed.add_field(
            name="Weapon",
            value=f"{item['type']} · {stat} · {item['element'] or 'no element'}",
            inline=False,
        )
        embed.add_field(
            name="Equipped Bonus",
            value=(
                f"**+{float(bonus_pct * 100):.1f}%** item stats while this weapon is equipped."
                if bonus_pct
                else "No stat bonus yet. Reach **Awakened** at level 1."
            ),
            inline=False,
        )
        if next_rank:
            embed.add_field(
                name="Next Awakening",
                value=(
                    f"**{next_rank[1]}** at level {next_rank[0]} "
                    f"(+{float(next_rank[3] * 100):.1f}% item stats)"
                ),
                inline=False,
            )
        embed.set_footer(
            text=(
                f"Bonded {bond['bonded_at'].strftime('%Y-%m-%d')} · XP: tower {XP_TOWER_FLOOR}, "
                f"dragon {XP_DRAGON_KILL}, raid win {XP_RAID_WIN}, adventure {XP_ADVENTURE}"
            )
        )
        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(Soulbound(bot))

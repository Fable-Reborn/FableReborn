"""Hall of Supporters: one post that lists every patron and server booster, kept up to date.

`$supporters setup #channel` (GM) posts it. Every hour the bot edits that same
message, so it never goes stale and nobody is pinged. Players can leave the
list with `$supporters hide`.

Only the cluster that can see the board's channel edits it. Supporters are read
from the Patreon and booster roles in servers this cluster has cached, plus any
saved Patreon tier of 2 or more (key redemptions).
"""
from __future__ import annotations

import logging

import discord
from discord.ext import commands, tasks

from classes import alt_tiers
from utils.checks import is_gm

from .board import build_board_embeds

log = logging.getLogger(__name__)

SCHEMA = (
    """
    CREATE TABLE IF NOT EXISTS supporter_board (
        id INTEGER PRIMARY KEY DEFAULT 1 CHECK (id = 1),
        guild_id BIGINT NOT NULL,
        channel_id BIGINT NOT NULL,
        message_id BIGINT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS supporter_board_hidden (
        user_id BIGINT PRIMARY KEY
    )
    """,
)


def collect_from_members(bot, member_roles_by_guild: dict[int, dict[int, set[int]]], boosters_by_guild: dict[int, set[int]]):
    """(tiers, boosters) from cached member roles.

    member_roles_by_guild: guild_id -> {user_id: role ids}. boosters_by_guild:
    guild_id -> Discord's own booster list, used when no booster role is set.
    """
    tier_of: dict[int, int] = {}
    for guild_id, role_mapping in bot._get_numeric_patreon_role_sources():
        for user_id, roles in (member_roles_by_guild.get(int(guild_id)) or {}).items():
            tier = max((int(t) for role_id, t in role_mapping.items() if int(role_id) in roles), default=0)
            if tier:
                tier_of[user_id] = max(tier_of.get(user_id, 0), min(tier, 4))

    booster_guild_id, booster_role_id = bot._get_patreon_booster_membership_config()
    boosters: set[int] = set()
    if booster_guild_id:
        members = member_roles_by_guild.get(int(booster_guild_id)) or {}
        if booster_role_id:
            boosters = {user_id for user_id, roles in members.items() if int(booster_role_id) in roles}
        else:
            boosters = set(boosters_by_guild.get(int(booster_guild_id)) or ())
    return tier_of, boosters


def group_tiers(tier_of: dict[int, int], hidden: set[int]) -> dict[int, list[int]]:
    grouped: dict[int, list[int]] = {}
    for user_id, tier in tier_of.items():
        if user_id in hidden or tier < 1:
            continue
        grouped.setdefault(min(int(tier), 4), []).append(int(user_id))
    return grouped


class SupporterBoard(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def cog_load(self):
        try:
            async with self.bot.pool.acquire() as conn:
                for statement in SCHEMA:
                    await conn.execute(statement)
                await alt_tiers.ensure_schema(conn)
        except Exception:
            log.exception("Supporter board tables could not be created")
            return
        self.refresh_loop.start()

    async def cog_unload(self):
        if self.refresh_loop.is_running():
            self.refresh_loop.cancel()

    def _prefix(self) -> str:
        try:
            return str(self.bot.config.bot.global_prefix) or "$"
        except Exception:
            return "$"

    async def _board_row(self):
        return await self.bot.pool.fetchrow("SELECT guild_id, channel_id, message_id FROM supporter_board WHERE id = 1")

    async def _collect(self) -> tuple[dict[int, list[int]], list[int]]:
        guild_ids = set(self.bot._get_patreon_tier_lookup_guild_ids())
        member_roles: dict[int, dict[int, set[int]]] = {}
        native_boosters: dict[int, set[int]] = {}
        for guild_id in guild_ids:
            guild = self.bot.get_guild(int(guild_id))
            if guild is None:
                continue
            member_roles[int(guild_id)] = {
                member.id: {role.id for role in member.roles} for member in guild.members if not member.bot
            }
            native_boosters[int(guild_id)] = {member.id for member in guild.premium_subscribers if not member.bot}
        tier_of, boosters = collect_from_members(self.bot, member_roles, native_boosters)

        # A Legendary Hero's alt borrows tier 4; list it at its own tier, not as a donor.
        rows = await self.bot.pool.fetch(
            'SELECT p."user", COALESCE(g.previous_tier, p."tier") AS "tier" FROM profile p '
            'LEFT JOIN alt_tier_grants g ON g.alt = p."user" '
            'WHERE COALESCE(g.previous_tier, p."tier") >= 2'
        )
        for row in rows:
            user_id = int(row["user"])
            tier_of[user_id] = max(tier_of.get(user_id, 0), min(int(row["tier"]), 4))
        hidden = {int(r["user_id"]) for r in await self.bot.pool.fetch("SELECT user_id FROM supporter_board_hidden")}
        return group_tiers(tier_of, hidden), sorted(user for user in boosters if user not in hidden)

    async def refresh(self) -> str:
        """Edit the board on this cluster. Returns what happened, for GMs and logs."""
        row = await self._board_row()
        if row is None:
            return "not_set_up"
        channel = self.bot.get_channel(int(row["channel_id"]))
        if channel is None:
            return "other_cluster"
        tiers, boosters = await self._collect()
        embeds = build_board_embeds(tiers, boosters, prefix=self._prefix())
        try:
            await channel.get_partial_message(int(row["message_id"])).edit(
                content=None, embeds=embeds, allowed_mentions=discord.AllowedMentions.none()
            )
        except discord.NotFound:
            log.warning("Supporter board message %s is gone; run supporters setup again", row["message_id"])
            await self.bot.pool.execute("DELETE FROM supporter_board WHERE id = 1")
            return "message_gone"
        except discord.HTTPException:
            log.exception("Supporter board edit failed")
            return "edit_failed"
        return "updated"

    @tasks.loop(hours=1)
    async def refresh_loop(self):
        try:
            await self.refresh()
        except Exception:
            log.exception("Supporter board refresh failed")

    @refresh_loop.before_loop
    async def _before_refresh(self):
        await self.bot.wait_until_ready()

    @commands.group(name="supporters", aliases=["supporterboard", "hallofsupporters"], invoke_without_command=True)
    async def supporters(self, ctx):
        """The Hall of Supporters. `hide` or `show` yourself on it."""
        prefix = ctx.clean_prefix
        await ctx.send(
            "The **Hall of Supporters** thanks every patron and server booster by name and updates every hour.\n"
            f"`{prefix}supporters hide` takes you off it, `{prefix}supporters show` puts you back. "
            f"Want to support Fable? `{prefix}donate`"
        )

    @supporters.command(name="hide")
    async def supporters_hide(self, ctx):
        """Leave the Hall of Supporters. Your perks are not affected."""
        await self.bot.pool.execute(
            "INSERT INTO supporter_board_hidden (user_id) VALUES ($1) ON CONFLICT DO NOTHING", ctx.author.id
        )
        await ctx.send("You are hidden from the Hall of Supporters. Your perks are unchanged. It updates within the hour.")

    @supporters.command(name="show")
    async def supporters_show(self, ctx):
        """Show yourself on the Hall of Supporters again."""
        await self.bot.pool.execute("DELETE FROM supporter_board_hidden WHERE user_id = $1", ctx.author.id)
        await ctx.send("You will appear on the Hall of Supporters again within the hour, if you are a supporter.")

    @is_gm()
    @supporters.command(name="setup", hidden=True)
    async def supporters_setup(self, ctx, channel: discord.TextChannel = None):
        """GM: post the Hall of Supporters in a channel (here by default). Moving it posts a new one."""
        channel = channel or ctx.channel
        tiers, boosters = await self._collect()
        embeds = build_board_embeds(tiers, boosters, prefix=self._prefix())
        try:
            message = await channel.send(embeds=embeds, allowed_mentions=discord.AllowedMentions.none())
        except discord.HTTPException as exc:
            return await ctx.send(f"I could not post in {channel.mention}: {exc}")
        await self.bot.pool.execute(
            """
            INSERT INTO supporter_board (id, guild_id, channel_id, message_id)
            VALUES (1, $1, $2, $3)
            ON CONFLICT (id) DO UPDATE
               SET guild_id = EXCLUDED.guild_id, channel_id = EXCLUDED.channel_id, message_id = EXCLUDED.message_id
            """,
            channel.guild.id,
            channel.id,
            message.id,
        )
        if channel.id != ctx.channel.id:
            await ctx.send(f"Hall of Supporters posted in {channel.mention}. It updates every hour.")

    @is_gm()
    @supporters.command(name="refresh", hidden=True)
    async def supporters_refresh(self, ctx):
        """GM: update the Hall of Supporters now."""
        result = await self.refresh()
        messages = {
            "updated": "Hall of Supporters updated.",
            "not_set_up": f"No board yet. Use `{ctx.clean_prefix}supporters setup #channel`.",
            "other_cluster": "That board lives on another cluster; it refreshes there every hour.",
            "message_gone": f"The board message was deleted. Post it again with `{ctx.clean_prefix}supporters setup`.",
            "edit_failed": "Discord refused the edit. Check the bot can still send and embed in that channel.",
        }
        await ctx.send(messages.get(result, result))


async def setup(bot):
    await bot.add_cog(SupporterBoard(bot))

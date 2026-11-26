"""GM-run silent (sealed-bid) auctions and raffles.

The database is the only source of truth. Every gold movement happens in one transaction that
first locks the parent auction/raffle row (lock order: parent -> bid/purchase -> profile), so a
bid or purchase racing a close either commits before it or is rejected. Closing is claimed
atomically (``open -> closing`` / ``open -> drawing``) under a Redis lock and can be resumed
after a crash, because refunds are tracked per row with a ``refunded`` flag.
"""
from __future__ import annotations

import datetime
import logging
import secrets
from typing import Optional

import discord

from asyncpg.exceptions import UniqueViolationError
from discord.ext import commands, tasks

from classes.converters import IntGreaterThan
from utils.checks import has_char, is_gm
from utils.i18n import _, locale_doc

from . import announce, builder, logic, views
from .announce import EventAlreadyLive

log = logging.getLogger(__name__)

NO_PINGS = discord.AllowedMentions.none()
STATUS_USER_ID = 273652235588599808  # the only user who may run $eventstatus
EMBED_REFRESH_SECONDS = 15
# Channel for silent auctions and raffles unless ids.game_master sets silent_auction_channel_id /
# raffle_channel_id.
DEFAULT_EVENT_CHANNEL_ID = 1408182582360936580

SCHEMA = """
CREATE TABLE IF NOT EXISTS silent_auctions (
    id            BIGSERIAL PRIMARY KEY,
    item          TEXT NOT NULL,
    min_bid       BIGINT NOT NULL CHECK (min_bid >= 1),
    created_by    BIGINT NOT NULL,
    channel_id    BIGINT NOT NULL,
    message_id    BIGINT,
    status        TEXT NOT NULL DEFAULT 'open',
    starts_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ends_at       TIMESTAMPTZ NOT NULL,
    winner_id     BIGINT,
    winning_bid   BIGINT,
    closed_at     TIMESTAMPTZ
);
CREATE UNIQUE INDEX IF NOT EXISTS silent_auctions_one_live
    ON silent_auctions ((true)) WHERE status IN ('open', 'closing');
CREATE TABLE IF NOT EXISTS silent_auction_bids (
    auction_id    BIGINT NOT NULL REFERENCES silent_auctions(id),
    user_id       BIGINT NOT NULL,
    amount        BIGINT NOT NULL CHECK (amount > 0),
    amount_set_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    refunded      BOOLEAN NOT NULL DEFAULT FALSE,
    PRIMARY KEY (auction_id, user_id)
);
CREATE TABLE IF NOT EXISTS raffles (
    id              BIGSERIAL PRIMARY KEY,
    prize           TEXT NOT NULL,
    ticket_price    BIGINT NOT NULL CHECK (ticket_price >= 1),
    max_per_user    INTEGER,
    created_by      BIGINT NOT NULL,
    channel_id      BIGINT NOT NULL,
    message_id      BIGINT,
    status          TEXT NOT NULL DEFAULT 'open',
    ends_at         TIMESTAMPTZ,
    seed_secret     TEXT NOT NULL,
    seed_commitment TEXT NOT NULL,
    ticket_digest   TEXT,
    winning_ticket  INTEGER,
    winner_id       BIGINT,
    drawn_at        TIMESTAMPTZ
);
CREATE UNIQUE INDEX IF NOT EXISTS raffles_one_live
    ON raffles ((true)) WHERE status IN ('open', 'drawing');
CREATE TABLE IF NOT EXISTS raffle_purchases (
    id          BIGSERIAL PRIMARY KEY,
    raffle_id   BIGINT NOT NULL REFERENCES raffles(id),
    user_id     BIGINT NOT NULL,
    quantity    INTEGER NOT NULL CHECK (quantity > 0),
    paid        BIGINT NOT NULL,
    refunded    BOOLEAN NOT NULL DEFAULT FALSE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS raffle_purchases_by_raffle ON raffle_purchases (raffle_id, id);
"""


# The GM's announcement text is stored so that every later edit rebuilds the full post.
MIGRATIONS = """
ALTER TABLE silent_auctions ADD COLUMN IF NOT EXISTS announcement TEXT;
ALTER TABLE silent_auctions ADD COLUMN IF NOT EXISTS announcement_title TEXT;
ALTER TABLE raffles ADD COLUMN IF NOT EXISTS announcement TEXT;
ALTER TABLE raffles ADD COLUMN IF NOT EXISTS announcement_title TEXT;
"""


class _Abort(Exception):
    """Raised inside a transaction to roll it back with a user-facing message."""


class GMEvents(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        ids_section = getattr(bot.config, "ids", None)
        gm_ids = getattr(ids_section, "game_master", {}) if ids_section else {}
        if not isinstance(gm_ids, dict):
            gm_ids = {}
        auction_role = gm_ids.get("auction_ping_role_id")
        self.silent_channel_id = gm_ids.get("silent_auction_channel_id") or DEFAULT_EVENT_CHANNEL_ID
        self.silent_role_id = auction_role
        self.raffle_channel_id = gm_ids.get("raffle_channel_id") or DEFAULT_EVENT_CHANNEL_ID
        self.raffle_role_id = auction_role
        self._builders: dict[int, builder.BuilderView] = {}  # one open builder per GM
        self._dirty_raffles: set[int] = set()  # throwaway cache: which embeds need a refresh

    # ------------------------------------------------------------------ lifecycle

    async def cog_load(self):
        async with self.bot.pool.acquire() as conn:
            await conn.execute(SCHEMA)
            await conn.execute(MIGRATIONS)
        self.bot.add_dynamic_items(*views.DYNAMIC_ITEMS)
        self.close_due.start()
        self.refresh_raffle_embeds.start()

    async def cog_unload(self):
        self.close_due.cancel()
        self.refresh_raffle_embeds.cancel()
        self.bot.remove_dynamic_items(*views.DYNAMIC_ITEMS)

    @commands.Cog.listener()
    async def on_gm_events_error(self, error: Exception):
        log.error("gm_events interaction error", exc_info=error)

    # --------------------------------------------------------------- shared helpers

    @staticmethod
    async def _debit(conn, user_id: int, amount: int) -> str:
        """Guarded debit. Returns 'ok', 'poor' or 'nochar'."""
        result = await conn.execute(
            'UPDATE profile SET money = money - $1 WHERE "user" = $2 AND money >= $1',
            amount,
            user_id,
        )
        if result == "UPDATE 1":
            return "ok"
        exists = await conn.fetchval('SELECT 1 FROM profile WHERE "user" = $1', user_id)
        return "poor" if exists else "nochar"

    @staticmethod
    async def _credit(conn, user_id: int, amount: int) -> bool:
        result = await conn.execute(
            'UPDATE profile SET money = money + $1 WHERE "user" = $2', amount, user_id
        )
        return result == "UPDATE 1"

    async def _log(self, conn, from_, to, subject, data, command_name):
        await self.bot.log_transaction(
            None, from_=from_, to=to, subject=subject, data=data, conn=conn,
            command_name=command_name,
        )

    async def _gm_log(self, text: str) -> None:
        channel_id = getattr(getattr(self.bot.config, "game", None), "gm_log_channel", None)
        channel = self.bot.get_channel(int(channel_id)) if channel_id else None
        if channel is None:
            return
        try:
            await channel.send(text[:1900], allowed_mentions=NO_PINGS)
        except discord.HTTPException:
            pass

    async def _lock(self, key: str) -> bool:
        """Cross-cluster lock. True if we now hold it."""
        return bool(await self.bot.redis.set(key, "1", nx=True, ex=120))

    async def _unlock(self, key: str) -> None:
        try:
            await self.bot.redis.delete(key)
        except Exception:  # the lock expires on its own after 120s
            pass

    @staticmethod
    def _ts(dt: datetime.datetime) -> str:
        unix = int(dt.timestamp())
        return f"<t:{unix}:F> (<t:{unix}:R>)"

    def _channel_for(self, channel_id):
        return self.bot.get_channel(int(channel_id)) if channel_id else None

    @staticmethod
    async def _strip_buttons(channel, message_id) -> None:
        if not channel or not message_id:
            return
        try:
            await channel.get_partial_message(message_id).edit(view=None)
        except discord.HTTPException:
            pass

    # ============================================================== BUILDER SUPPORT

    def resolve_target(self, kind: str, ping: bool):
        """``(channel, role, error)`` for an event type, from the same config the commands use."""
        if kind == "classic":
            gm_cog = self.bot.get_cog("GameMaster")
            if gm_cog is None:
                return None, None, _("The GameMaster cog isn't loaded.")
            channel_id = gm_cog.auction_channel_id or DEFAULT_EVENT_CHANNEL_ID
            role_id = gm_cog.auction_ping_role_id
        elif kind == "silent":
            channel_id, role_id = self.silent_channel_id, self.silent_role_id
        else:
            channel_id, role_id = self.raffle_channel_id, self.raffle_role_id
        channel = self._channel_for(channel_id)
        if channel is None:
            return None, None, _(
                "The auction channel isn't configured or isn't visible to this cluster."
            )
        role = channel.guild.get_role(int(role_id)) if role_id else None
        if ping and announce.pings_enabled(self.bot) and role is None:
            return channel, None, _(
                "The ping role wasn't found. Turn the ping off or set `auction_ping_role_id`."
            )
        return channel, role, None

    async def live_status(self) -> dict:
        gm_cog = self.bot.get_cog("GameMaster")
        silent = await self.bot.pool.fetchval(
            "SELECT EXISTS (SELECT 1 FROM silent_auctions WHERE status IN ('open', 'closing'))"
        )
        raffle = await self.bot.pool.fetchval(
            "SELECT EXISTS (SELECT 1 FROM raffles WHERE status IN ('open', 'drawing'))"
        )
        return {
            "classic": bool(gm_cog is not None and gm_cog.top_auction is not None),
            "silent": bool(silent),
            "raffle": bool(raffle),
        }

    @is_gm()
    @commands.command(
        name="gmauctionbuilder", aliases=["gmab", "auctionbuilder"], hidden=True,
        brief=_("Build and post an auction or raffle"),
    )
    @locale_doc
    async def gmauctionbuilder(self, ctx):
        _(
            """Opens an interactive panel to build and post a classic auction, a silent auction
            or a raffle: pick the type, fill in the details, write your own announcement,
            preview the exact post, then press Post.

            Only you can use your panel. It is a normal message, so run it in a staff channel.
            Drafts live in memory only: a bot restart or 15 minutes of inactivity ends the panel.
            The "How to take part" section is written automatically and can't be edited.
            Only Game Masters can use this command."""
        )
        await builder.BuilderView(self, ctx).start(ctx)

    # ================================================================ OWNER STATUS

    @staticmethod
    def _chunks(lines: list[str], limit: int = 1900):
        out, cur = [], ""
        for line in lines:
            if len(cur) + len(line) + 1 > limit:
                out.append(cur)
                cur = ""
            cur += line + "\n"
        if cur:
            out.append(cur)
        return out

    @commands.command(
        name="eventstatus", aliases=["auctionstatus", "aucstatus"], hidden=True,
        brief=_("Owner only: details of every live auction and raffle"),
    )
    @commands.check(lambda ctx: ctx.author.id == STATUS_USER_ID)
    async def eventstatus(self, ctx):
        """Owner only. DMs you every live auction/raffle with full details (including sealed bids)."""
        lines: list[str] = [
            f"**Event status** (pings {'ON' if announce.pings_enabled(self.bot) else 'OFF'})"
        ]
        now = datetime.datetime.now(datetime.timezone.utc)

        gm_cog = self.bot.get_cog("GameMaster")
        lines.append("\n**Classic auction**")
        if gm_cog is not None and gm_cog.top_auction is not None:
            top, amount = gm_cog.top_auction
            last = getattr(gm_cog, "_classic_last_activity", None)
            lines.append(f"Item: {gm_cog.current_item}")
            lines.append(
                f"Top bid: ${amount:,} by {top} (`{top.id}`)" if top else "Top bid: none yet"
            )
            if last:
                end = last + datetime.timedelta(hours=announce.CLASSIC_IDLE_HOURS)
                lines.append(f"Last activity: <t:{int(last.timestamp())}:R>, ends <t:{int(end.timestamp())}:R> if no more bids")
            lines.append(f"Timer task running: {gm_cog.auction_task is not None and not gm_cog.auction_task.done()}")
        else:
            lines.append("none")

        lines.append("\n**Silent auction**")
        row = await self._live_silent()
        if row:
            bids = await self.bot.pool.fetch(
                "SELECT user_id, amount, amount_set_at, refunded FROM silent_auction_bids "
                "WHERE auction_id = $1 ORDER BY amount DESC, amount_set_at ASC, user_id ASC",
                row["id"],
            )
            held = sum(b["amount"] for b in bids if not b["refunded"])
            lines.append(
                f"#{row['id']} {row['item']!r}, status `{row['status']}`, min ${row['min_bid']:,}, "
                f"ends <t:{int(row['ends_at'].timestamp())}:R>, by <@{row['created_by']}>"
            )
            msg_channel = self.bot.get_channel(row["channel_id"])
            if msg_channel is not None and row["message_id"]:
                lines.append(f"Message: {msg_channel.get_partial_message(row['message_id']).jump_url}")
            lines.append(f"Bidders: {len(bids)}, gold held: ${held:,}")
            for i, b in enumerate(bids[:25], 1):
                lines.append(
                    f"{i}. <@{b['user_id']}> `{b['user_id']}` ${b['amount']:,} (set <t:{int(b['amount_set_at'].timestamp())}:R>)"
                )
            if len(bids) > 25:
                lines.append(f"... and {len(bids) - 25} more")
        else:
            lines.append("none")

        lines.append("\n**Raffle**")
        raffle = await self._live_raffle()
        if raffle:
            stats = await self.bot.pool.fetchrow(
                "SELECT COUNT(DISTINCT user_id) AS entrants, COALESCE(SUM(quantity), 0) AS tickets, "
                "COALESCE(SUM(paid), 0) AS gold FROM raffle_purchases "
                "WHERE raffle_id = $1 AND NOT refunded",
                raffle["id"],
            )
            top = await self.bot.pool.fetch(
                "SELECT user_id, SUM(quantity) AS tickets FROM raffle_purchases "
                "WHERE raffle_id = $1 AND NOT refunded GROUP BY user_id ORDER BY tickets DESC LIMIT 15",
                raffle["id"],
            )
            ends = f"<t:{int(raffle['ends_at'].timestamp())}:R>" if raffle["ends_at"] else "manual draw"
            lines.append(
                f"#{raffle['id']} {raffle['prize']!r}, status `{raffle['status']}`, ${raffle['ticket_price']:,}/ticket, "
                f"cap {raffle['max_per_user'] or 'none'}, ends {ends}, by <@{raffle['created_by']}>"
            )
            lines.append(
                f"Entrants: {stats['entrants']}, tickets: {stats['tickets']}, gold collected: ${stats['gold']:,}"
            )
            lines.append(f"Commitment: `{raffle['seed_commitment']}` (seed stays secret until the draw)")
            for b in top:
                lines.append(f"<@{b['user_id']}> `{b['user_id']}`: {b['tickets']} tickets")
        else:
            lines.append("none")

        try:
            for chunk in self._chunks(lines):
                await ctx.author.send(chunk, allowed_mentions=NO_PINGS)
        except discord.HTTPException:
            return await ctx.send("I couldn't DM you. Open your DMs; sealed bids are never posted in channels.")
        if ctx.guild is not None:
            await ctx.send("Sent to your DMs.")

    # ============================================================== SILENT AUCTION

    def _gm_name(self, user_id) -> str:
        user = self.bot.get_user(int(user_id)) if user_id else None
        return user.display_name if user else _("a Game Master")

    def _row_embeds(self, kind: str, row, *, tickets=None, entrants=None):
        """Rebuild the full post from a stored row (keeps the GM's announcement)."""
        _content, embeds = announce.build_announcement(
            kind,
            name=row["item"] if kind == "silent" else row["prize"],
            title=row["announcement_title"],
            message=row["announcement"],
            gm_name=self._gm_name(row["created_by"]),
            prefix=self.bot.config.bot.global_prefix,
            ends_at=row["ends_at"],
            min_bid=row["min_bid"] if kind == "silent" else None,
            ticket_price=row["ticket_price"] if kind == "raffle" else None,
            max_per_user=row["max_per_user"] if kind == "raffle" else None,
            commitment=row["seed_commitment"] if kind == "raffle" else None,
            tickets=tickets,
            entrants=entrants,
        )
        return embeds

    async def start_silent_auction(
        self, *, gm, channel, role, item, min_bid, duration, announcement=None,
        title=None, ping=True, prefix="$",
    ) -> discord.Message:
        """The one place a silent auction is started (text command and builder).

        Raises ``EventAlreadyLive`` or ``discord.HTTPException``; never leaves a live row
        behind when the message could not be sent.
        """
        ping = announce.pings_enabled(self.bot) and ping
        ends_at = datetime.datetime.now(datetime.timezone.utc) + duration
        try:
            auction_id = await self.bot.pool.fetchval(
                "INSERT INTO silent_auctions (item, min_bid, created_by, channel_id, ends_at, "
                "announcement, announcement_title) VALUES ($1, $2, $3, $4, $5, $6, $7) "
                "RETURNING id",
                item, min_bid, gm.id, channel.id, ends_at, announcement or None, title or None,
            )
        except UniqueViolationError:
            raise EventAlreadyLive("A silent auction is already live.") from None
        content, embeds = announce.build_announcement(
            "silent", name=item, title=title, message=announcement, gm_name=gm.display_name,
            prefix=prefix, ends_at=ends_at, min_bid=min_bid,
            role_mention=role.mention if (ping and role is not None) else None,
        )
        try:
            message = await channel.send(
                content, embeds=embeds, view=views.silent_view(auction_id),
                allowed_mentions=announce.allowed_mentions_for(role, ping),
            )
        except Exception:
            await self.bot.pool.execute(
                "UPDATE silent_auctions SET status = 'cancelled', closed_at = NOW() WHERE id = $1",
                auction_id,
            )
            raise
        await self.bot.pool.execute(
            "UPDATE silent_auctions SET message_id = $2 WHERE id = $1", auction_id, message.id
        )
        return message

    def silent_role(self, channel):
        return channel.guild.get_role(int(self.silent_role_id)) if self.silent_role_id else None

    def raffle_role(self, channel):
        return channel.guild.get_role(int(self.raffle_role_id)) if self.raffle_role_id else None

    async def place_silent_bid(self, user_id: int, auction_id: int, amount: int):
        """Core bid logic, used by the modal. Returns ``(ok, message)``."""
        try:
            async with self.bot.pool.acquire() as conn:
                async with conn.transaction():
                    # parent row first, then the bid row, then the profile row
                    auction = await conn.fetchrow(
                        "SELECT id, item, min_bid, (status = 'open' AND ends_at > NOW()) AS live "
                        "FROM silent_auctions WHERE id = $1 FOR UPDATE",
                        auction_id,
                    )
                    if auction is None or not auction["live"]:
                        raise _Abort(_("This auction is no longer open."))
                    own = await conn.fetchrow(
                        "SELECT amount FROM silent_auction_bids "
                        "WHERE auction_id = $1 AND user_id = $2 FOR UPDATE",
                        auction_id,
                        user_id,
                    )
                    if own is None:
                        if amount < auction["min_bid"]:
                            raise _Abort(
                                _("The minimum bid is ${min_bid:,}.").format(
                                    min_bid=auction["min_bid"]
                                )
                            )
                        diff = amount
                    else:
                        if amount <= own["amount"]:
                            raise _Abort(
                                _(
                                    "You can only raise your bid. Your current bid is ${amount:,}."
                                ).format(amount=own["amount"])
                            )
                        diff = amount - own["amount"]
                    status = await self._debit(conn, user_id, diff)
                    if status == "nochar":
                        raise _Abort(_("You need a character to bid."))
                    if status == "poor":
                        raise _Abort(_("You don't have enough gold to place that bid."))
                    await conn.execute(
                        "INSERT INTO silent_auction_bids (auction_id, user_id, amount, amount_set_at) "
                        "VALUES ($1, $2, $3, NOW()) "
                        "ON CONFLICT (auction_id, user_id) DO UPDATE "
                        "SET amount = EXCLUDED.amount, amount_set_at = NOW()",
                        auction_id,
                        user_id,
                        amount,
                    )
                    await self._log(
                        conn, user_id, 2, "bid",
                        {"Gold": diff, "Auction": auction_id, "Total bid": amount},
                        "silent auction bid",
                    )
        except _Abort as abort:
            return False, str(abort)
        return True, _(
            "🔒 Your sealed bid on **{item}** is now **${amount:,}**. Only you can see this."
        ).format(item=auction["item"], amount=amount)

    async def silent_bid_summary(self, user_id: int, auction_id: int) -> str:
        row = await self.bot.pool.fetchrow(
            "SELECT b.amount, a.item FROM silent_auctions a LEFT JOIN silent_auction_bids b "
            "ON b.auction_id = a.id AND b.user_id = $2 WHERE a.id = $1",
            auction_id,
            user_id,
        )
        if row is None:
            return _("This auction no longer exists.")
        if row["amount"] is None:
            return _("You haven't bid on **{item}**.").format(item=row["item"])
        return _("🔒 Your sealed bid on **{item}** is **${amount:,}**. Only you can see this.").format(
            item=row["item"], amount=row["amount"]
        )

    async def finalize_silent_auction(
        self, auction_id: int, *, cancel: bool = False, reason: Optional[str] = None
    ) -> bool:
        """Close (or cancel) an auction. Safe to call repeatedly from any cluster.

        Returns True only if this call performed the close and therefore announced it.
        """
        key = f"gm_events:silent:{auction_id}"
        if not await self._lock(key):
            return False
        try:
            async with self.bot.pool.acquire() as conn:
                row = await conn.fetchrow(
                    "UPDATE silent_auctions SET status = 'closing' "
                    "WHERE id = $1 AND status = 'open' RETURNING *",
                    auction_id,
                )
                if row is None:  # resume a close that crashed half way
                    row = await conn.fetchrow(
                        "SELECT * FROM silent_auctions WHERE id = $1 AND status = 'closing'",
                        auction_id,
                    )
                if row is None:
                    return False
                refunds: list[tuple[int, int]] = []
                failed: list[tuple[int, int]] = []
                async with conn.transaction():
                    await conn.fetchrow(
                        "SELECT id FROM silent_auctions WHERE id = $1 FOR UPDATE", auction_id
                    )
                    bids = await conn.fetch(
                        "SELECT user_id, amount, amount_set_at, refunded "
                        "FROM silent_auction_bids WHERE auction_id = $1 ORDER BY user_id FOR UPDATE",
                        auction_id,
                    )
                    winner = None
                    if not cancel:
                        winner = logic.pick_silent_winner(
                            logic.Bid(b["user_id"], b["amount"], b["amount_set_at"]) for b in bids
                        )
                    for bid in bids:
                        if bid["refunded"] or (winner and bid["user_id"] == winner.user_id):
                            continue
                        if await self._credit(conn, bid["user_id"], bid["amount"]):
                            await conn.execute(
                                "UPDATE silent_auction_bids SET refunded = TRUE "
                                "WHERE auction_id = $1 AND user_id = $2",
                                auction_id,
                                bid["user_id"],
                            )
                            await self._log(
                                conn, 1, bid["user_id"], "bid",
                                {"Gold": bid["amount"], "Auction": auction_id, "Refund": True},
                                "silent auction refund",
                            )
                            refunds.append((bid["user_id"], bid["amount"]))
                        else:  # profile is gone: leave it unrefunded so the record keeps the debt
                            failed.append((bid["user_id"], bid["amount"]))
                    await conn.execute(
                        "UPDATE silent_auctions SET status = $2, winner_id = $3, winning_bid = $4, "
                        "closed_at = NOW() WHERE id = $1",
                        auction_id,
                        "cancelled" if cancel else "closed",
                        winner.user_id if winner else None,
                        winner.amount if winner else None,
                    )
            channel = self.bot.get_channel(row["channel_id"])
            await self._strip_buttons(channel, row["message_id"])
            item = row["item"]
            if cancel:
                text = _(
                    "🚫 The silent auction for **{item}** was cancelled. All bids have been refunded."
                ).format(item=item)
                if reason:
                    text += "\n" + _("Reason: {reason}").format(reason=reason)
            elif winner:
                text = _(
                    "🔨 Silent auction for **{item}** has closed.\n"
                    "Winner: <@{winner}> with **${amount:,}**. All other bids have been refunded.\n"
                    "The prize will be handed out by a Game Master."
                ).format(item=item, winner=winner.user_id, amount=winner.amount)
            else:
                text = _("🔨 Silent auction for **{item}** has closed with no bids.").format(
                    item=item
                )
            if channel:
                try:
                    await channel.send(
                        text,
                        allowed_mentions=discord.AllowedMentions(
                            users=[discord.Object(winner.user_id)] if winner else False
                        ),
                    )
                except discord.HTTPException:
                    pass
            for user_id, amount in refunds:
                try:
                    user = self.bot.get_user(user_id) or await self.bot.fetch_user(user_id)
                    await user.send(
                        _("Your bid of ${amount:,} on **{item}** was refunded.").format(
                            amount=amount, item=item
                        )
                    )
                except (discord.HTTPException, AttributeError):
                    pass
            gm_text = f"[silent auction #{auction_id}] {text}"
            if failed:
                gm_text += "\nCould not refund (no profile): " + ", ".join(
                    f"<@{u}> ${a:,}" for u, a in failed
                )
            await self._gm_log(gm_text)
            return True
        finally:
            await self._unlock(key)

    async def _live_silent(self):
        return await self.bot.pool.fetchrow(
            "SELECT * FROM silent_auctions WHERE status IN ('open', 'closing') "
            "ORDER BY id DESC LIMIT 1"
        )

    @is_gm()
    @commands.group(
        name="gmsilent", hidden=True, invoke_without_command=True,
        brief=_("Silent (sealed-bid) auctions"),
    )
    @locale_doc
    async def gmsilent(self, ctx):
        _(
            """Silent auctions. Subcommands: `start`, `end`, `cancel`, `status`.
            Only Game Masters can use this command."""
        )
        await ctx.send(
            _("Use `{prefix}gmsilent start|end|cancel|status`.").format(prefix=ctx.clean_prefix)
        )

    @is_gm()
    @gmsilent.command(name="start", hidden=True, brief=_("Start a silent auction"))
    @locale_doc
    async def gmsilent_start(self, ctx, duration: str, min_bid: IntGreaterThan(0), *, item: str):
        _(
            """`<duration>` - e.g. `24h`, `1d12h`, `90m` (5 minutes to 14 days)
            `<min_bid>` - the minimum first bid
            `<item>` - what is being auctioned

            Starts a sealed-bid auction. Players bid with a button; nobody can see the bids.
            The highest bid wins, ties go to whoever reached the amount first, everyone else is
            refunded automatically. The item is not given automatically.
            Only Game Masters can use this command."""
        )
        try:
            delta = logic.parse_duration(
                duration, logic.SILENT_MIN_DURATION, logic.SILENT_MAX_DURATION
            )
        except ValueError as exc:
            return await ctx.send(_(str(exc)))
        if min_bid > logic.MAX_AMOUNT:
            return await ctx.send(_("That minimum bid is too large."))
        item = item.strip()[:200]
        channel = self._channel_for(self.silent_channel_id)
        if channel is None:
            return await ctx.send(
                _(
                    "The auction channel isn't configured or isn't visible to this cluster "
                    "(`silent_auction_channel_id` or `auction_channel_id`)."
                )
            )
        try:
            message = await self.start_silent_auction(
                gm=ctx.author, channel=channel, role=self.silent_role(channel), item=item,
                min_bid=min_bid, duration=delta, prefix=ctx.clean_prefix,
            )
        except EventAlreadyLive:
            return await ctx.send(_("A silent auction is already live."))
        except discord.HTTPException as exc:
            return await ctx.send(_("Couldn't post the auction: {error}").format(error=exc))
        await ctx.send(_("Silent auction started: {link}").format(link=message.jump_url))

    @is_gm()
    @gmsilent.command(name="end", hidden=True, brief=_("Close the silent auction now"))
    @locale_doc
    async def gmsilent_end(self, ctx):
        _("""Closes the live silent auction now and announces the winner.""")
        row = await self._live_silent()
        if row is None:
            return await ctx.send(_("There is no live silent auction."))
        if await self.finalize_silent_auction(row["id"]):
            await ctx.send(_("Silent auction closed."))
        else:
            await ctx.send(_("It is already being closed by another process."))

    @is_gm()
    @gmsilent.command(name="cancel", hidden=True, brief=_("Cancel the silent auction"))
    @locale_doc
    async def gmsilent_cancel(self, ctx, *, reason: str = None):
        _(
            """`[reason]` - shown in the announcement
            Cancels the live silent auction and refunds every bid."""
        )
        row = await self._live_silent()
        if row is None:
            return await ctx.send(_("There is no live silent auction."))
        if await self.finalize_silent_auction(row["id"], cancel=True, reason=reason):
            await ctx.send(_("Silent auction cancelled and bids refunded."))
        else:
            await ctx.send(_("It is already being closed by another process."))

    @is_gm()
    @gmsilent.command(name="status", hidden=True, brief=_("Silent auction status"))
    @locale_doc
    async def gmsilent_status(self, ctx):
        _("""Shows the time left and how many players have bid. Never amounts or names.""")
        row = await self._live_silent()
        if row is None:
            return await ctx.send(_("There is no live silent auction."))
        count = await self.bot.pool.fetchval(
            "SELECT COUNT(*) FROM silent_auction_bids WHERE auction_id = $1", row["id"]
        )
        await ctx.send(
            _(
                "Silent auction #{id} (**{item}**), status `{status}`, ends {ends}.\n"
                "Players who have bid: **{count}**."
            ).format(
                id=row["id"], item=row["item"], status=row["status"],
                ends=self._ts(row["ends_at"]), count=count,
            ),
            allowed_mentions=NO_PINGS,
        )

    @commands.command(name="silentbid", hidden=True, brief=_("Place a sealed bid"))
    @locale_doc
    async def silentbid(self, ctx, amount: str):
        _(
            """`<amount>` - your bid, e.g. `5000`, `5,000`, `5k`, `1.5m`
            Places or raises your sealed bid on the live silent auction.
            Your message is deleted straight away and the confirmation is sent to your DMs.
            For full privacy, use this command in a DM with the bot or use the auction's button."""
        )
        deleted = True
        if ctx.guild is not None:
            try:
                await ctx.message.delete()
            except discord.HTTPException:
                deleted = False
        try:
            parsed = logic.parse_amount(amount)
        except ValueError as exc:
            message = _(str(exc))
        else:
            auction_id = await self.bot.pool.fetchval(
                "SELECT id FROM silent_auctions WHERE status = 'open' ORDER BY id DESC LIMIT 1"
            )
            if auction_id is None:
                message = _("There is no live silent auction.")
            else:
                _ok, message = await self.place_silent_bid(ctx.author.id, auction_id, parsed)
        if not deleted:
            message += "\n" + _(
                "⚠️ I couldn't delete your command, so your bid may have been visible. "
                "Use the auction's button or DM me next time."
            )
        try:
            await ctx.author.send(message)
        except discord.HTTPException:
            if ctx.guild is not None:  # no amounts in the public reply
                await ctx.send(
                    _("{user}, I couldn't DM you the result. Open your DMs and use the auction's button to check your bid.").format(
                        user=ctx.author.mention
                    ),
                    delete_after=15,
                    allowed_mentions=discord.AllowedMentions(users=[ctx.author]),
                )

    # ==================================================================== RAFFLE

    async def start_raffle(
        self, *, gm, channel, role, prize, ticket_price, max_per_user, duration,
        announcement=None, title=None, ping=True, prefix="$",
    ) -> discord.Message:
        """The one place a raffle is started. ``duration`` None means GM draws manually."""
        ping = announce.pings_enabled(self.bot) and ping
        ends_at = (
            datetime.datetime.now(datetime.timezone.utc) + duration if duration else None
        )
        seed_secret = secrets.token_hex(32)
        try:
            row = await self.bot.pool.fetchrow(
                "INSERT INTO raffles (prize, ticket_price, max_per_user, created_by, channel_id, "
                "ends_at, seed_secret, seed_commitment, announcement, announcement_title) "
                "VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10) RETURNING *",
                prize, ticket_price, max_per_user or None, gm.id, channel.id, ends_at,
                seed_secret, logic.commitment(seed_secret), announcement or None, title or None,
            )
        except UniqueViolationError:
            raise EventAlreadyLive("A raffle is already live.") from None
        content, embeds = announce.build_announcement(
            "raffle", name=prize, title=title, message=announcement, gm_name=gm.display_name,
            prefix=prefix, ends_at=ends_at, ticket_price=ticket_price,
            max_per_user=max_per_user or None, commitment=row["seed_commitment"],
            role_mention=role.mention if (ping and role is not None) else None,
            tickets=0, entrants=0,
        )
        try:
            message = await channel.send(
                content, embeds=embeds, view=views.raffle_view(row["id"]),
                allowed_mentions=announce.allowed_mentions_for(role, ping),
            )
        except Exception:
            await self.bot.pool.execute(
                "UPDATE raffles SET status = 'cancelled', drawn_at = NOW() WHERE id = $1",
                row["id"],
            )
            raise
        await self.bot.pool.execute(
            "UPDATE raffles SET message_id = $2 WHERE id = $1", row["id"], message.id
        )
        return message

    async def buy_raffle_tickets(self, user_id: int, raffle_id: Optional[int], qty: int):
        """Core purchase logic for the modal and ``$raffle buy``. Returns ``(ok, message)``."""
        try:
            async with self.bot.pool.acquire() as conn:
                async with conn.transaction():
                    if raffle_id is None:
                        raffle_id = await conn.fetchval(
                            "SELECT id FROM raffles WHERE status = 'open' ORDER BY id DESC LIMIT 1"
                        )
                    raffle = await conn.fetchrow(
                        "SELECT id, prize, ticket_price, max_per_user, "
                        "(status = 'open' AND (ends_at IS NULL OR ends_at > NOW())) AS live "
                        "FROM raffles WHERE id = $1 FOR UPDATE",
                        raffle_id,
                    )
                    if raffle is None or not raffle["live"]:
                        raise _Abort(_("This raffle is no longer open."))
                    held = await conn.fetchval(
                        "SELECT COALESCE(SUM(quantity), 0) FROM raffle_purchases "
                        "WHERE raffle_id = $1 AND user_id = $2 AND NOT refunded",
                        raffle["id"],
                        user_id,
                    )
                    cap = raffle["max_per_user"]
                    if cap and held + qty > cap:
                        raise _Abort(
                            _("The limit is {cap} tickets per player. You hold {held}.").format(
                                cap=cap, held=held
                            )
                        )
                    cost = qty * raffle["ticket_price"]
                    status = await self._debit(conn, user_id, cost)
                    if status == "nochar":
                        raise _Abort(_("You need a character to buy tickets."))
                    if status == "poor":
                        raise _Abort(
                            _("You don't have enough gold (${cost:,} needed).").format(cost=cost)
                        )
                    await conn.execute(
                        "INSERT INTO raffle_purchases (raffle_id, user_id, quantity, paid) "
                        "VALUES ($1, $2, $3, $4)",
                        raffle["id"], user_id, qty, cost,
                    )
                    await self._log(
                        conn, user_id, 2, "raffle",
                        {"Gold": cost, "Raffle": raffle["id"], "Tickets": qty},
                        "raffle ticket purchase",
                    )
        except _Abort as abort:
            return False, str(abort)
        self._dirty_raffles.add(raffle["id"])
        return True, _("🎟️ You bought {qty} tickets (you now hold {held}) for **{prize}**.").format(
            qty=qty, held=held + qty, prize=raffle["prize"]
        )

    async def raffle_ticket_summary(self, user_id: int, raffle_id: int) -> str:
        raffle = await self.bot.pool.fetchrow("SELECT prize FROM raffles WHERE id = $1", raffle_id)
        held = await self.bot.pool.fetchval(
            "SELECT COALESCE(SUM(quantity), 0) FROM raffle_purchases "
            "WHERE raffle_id = $1 AND user_id = $2 AND NOT refunded",
            raffle_id, user_id,
        )
        if raffle is None:
            return _("This raffle no longer exists.")
        return _("🎟️ You hold {held} tickets for **{prize}**.").format(
            held=held, prize=raffle["prize"]
        )

    async def finalize_raffle(
        self, raffle_id: int, *, cancel: bool = False, reason: Optional[str] = None
    ) -> bool:
        """Draw (or cancel) a raffle. Idempotent; True only if this call did it."""
        key = f"gm_events:raffle:{raffle_id}"
        if not await self._lock(key):
            return False
        try:
            async with self.bot.pool.acquire() as conn:
                row = await conn.fetchrow(
                    "UPDATE raffles SET status = 'drawing' "
                    "WHERE id = $1 AND status = 'open' RETURNING *",
                    raffle_id,
                )
                if row is None:  # resume a draw that crashed half way
                    row = await conn.fetchrow(
                        "SELECT * FROM raffles WHERE id = $1 AND status = 'drawing'", raffle_id
                    )
                if row is None:
                    return False
                refunds: list[tuple[int, int]] = []
                failed: list[tuple[int, int]] = []
                result = None
                total_tickets = entrants = 0
                async with conn.transaction():
                    await conn.fetchrow("SELECT id FROM raffles WHERE id = $1 FOR UPDATE", raffle_id)
                    purchases = await conn.fetch(
                        "SELECT id, user_id, quantity, paid, refunded FROM raffle_purchases "
                        "WHERE raffle_id = $1 ORDER BY id FOR UPDATE",
                        raffle_id,
                    )
                    if cancel:
                        for p in purchases:
                            if p["refunded"]:
                                continue
                            if await self._credit(conn, p["user_id"], p["paid"]):
                                await conn.execute(
                                    "UPDATE raffle_purchases SET refunded = TRUE WHERE id = $1",
                                    p["id"],
                                )
                                await self._log(
                                    conn, 1, p["user_id"], "raffle",
                                    {"Gold": p["paid"], "Raffle": raffle_id, "Refund": True},
                                    "raffle refund",
                                )
                                refunds.append((p["user_id"], p["paid"]))
                            else:
                                failed.append((p["user_id"], p["paid"]))
                        await conn.execute(
                            "UPDATE raffles SET status = 'cancelled', drawn_at = NOW() WHERE id = $1",
                            raffle_id,
                        )
                    else:
                        live = [
                            (p["user_id"], p["quantity"]) for p in purchases if not p["refunded"]
                        ]
                        tickets = logic.build_tickets(live)
                        total_tickets = len(tickets)
                        entrants = len({user for user, _qty in live})
                        result = logic.draw_winner(row["seed_secret"], tickets)
                        digest = result[2] if result else logic.ticket_digest(tickets)
                        await conn.execute(
                            "UPDATE raffles SET status = 'drawn', winner_id = $2, "
                            "winning_ticket = $3, ticket_digest = $4, drawn_at = NOW() "
                            "WHERE id = $1",
                            raffle_id,
                            result[1] if result else None,
                            result[0] if result else None,
                            digest,
                        )
            channel = self.bot.get_channel(row["channel_id"])
            await self._strip_buttons(channel, row["message_id"])
            prize = row["prize"]
            if cancel:
                text = _(
                    "🚫 The raffle for **{prize}** was cancelled. All tickets have been refunded."
                ).format(prize=prize)
                if reason:
                    text += "\n" + _("Reason: {reason}").format(reason=reason)
            elif result:
                text = _(
                    "🎉 The raffle for **{prize}** has been drawn!\n"
                    "Winner: <@{winner}> with ticket **#{ticket}** "
                    "({total} tickets, {entrants} players).\n"
                    "The prize will be handed out by a Game Master.\n"
                    "Verification: seed `{seed}` (SHA-256 = the commitment above), "
                    "ticket digest `{digest}`."
                ).format(
                    prize=prize, winner=result[1], ticket=result[0], total=total_tickets,
                    entrants=entrants, seed=row["seed_secret"], digest=result[2],
                )
            else:
                text = _(
                    "🎟️ The raffle for **{prize}** ended with no tickets sold, so there is no winner."
                ).format(prize=prize)
            if channel:
                try:
                    await channel.send(
                        text,
                        allowed_mentions=discord.AllowedMentions(
                            users=[discord.Object(result[1])] if result else False
                        ),
                    )
                except discord.HTTPException:
                    pass
            gm_text = f"[raffle #{raffle_id}] {text}"
            if failed:
                gm_text += "\nCould not refund (no profile): " + ", ".join(
                    f"<@{u}> ${a:,}" for u, a in failed
                )
            await self._gm_log(gm_text)
            self._dirty_raffles.discard(raffle_id)
            return True
        finally:
            await self._unlock(key)

    async def _live_raffle(self):
        return await self.bot.pool.fetchrow(
            "SELECT * FROM raffles WHERE status IN ('open', 'drawing') ORDER BY id DESC LIMIT 1"
        )

    @is_gm()
    @commands.group(
        name="gmraffle", hidden=True, invoke_without_command=True, brief=_("Run a raffle")
    )
    @locale_doc
    async def gmraffle(self, ctx):
        _(
            """Raffles. Subcommands: `start`, `draw`, `cancel`, `status`.
            Only Game Masters can use this command."""
        )
        await ctx.send(
            _("Use `{prefix}gmraffle start|draw|cancel|status`.").format(prefix=ctx.clean_prefix)
        )

    @is_gm()
    @gmraffle.command(name="start", hidden=True, brief=_("Start a raffle"))
    @locale_doc
    async def gmraffle_start(
        self, ctx, duration: str, ticket_price: IntGreaterThan(0),
        max_per_user: Optional[int] = None, *, prize: str,
    ):
        _(
            """`<duration>` - e.g. `24h`, `3d`, or `manual` to end only when a GM runs `draw`
            `<ticket_price>` - gold per ticket
            `[max_per_user]` - optional ticket cap per player, a number right after the price
            (if the prize itself starts with a number, put a word first)
            `<prize>` - what is being raffled

            Players buy tickets with gold (the gold is removed from the economy). When the raffle
            ends, every ticket is shuffled with a seed committed at the start and one is drawn.
            The prize is not given automatically.
            Only Game Masters can use this command."""
        )
        delta = None
        if duration.lower() != "manual":
            try:
                delta = logic.parse_duration(
                    duration, logic.RAFFLE_MIN_DURATION, logic.RAFFLE_MAX_DURATION
                )
            except ValueError as exc:
                return await ctx.send(_(str(exc)))
        if ticket_price > logic.MAX_TICKET_PRICE:
            return await ctx.send(_("That ticket price is too large."))
        if max_per_user is not None and not 0 <= max_per_user <= 1_000_000:
            return await ctx.send(_("Invalid per-player ticket limit."))
        prize = prize.strip()[:200]
        channel = self._channel_for(self.raffle_channel_id)
        if channel is None:
            return await ctx.send(
                _(
                    "The raffle channel isn't configured or isn't visible to this cluster "
                    "(`raffle_channel_id` or `auction_channel_id`)."
                )
            )
        try:
            message = await self.start_raffle(
                gm=ctx.author, channel=channel, role=self.raffle_role(channel), prize=prize,
                ticket_price=ticket_price, max_per_user=max_per_user or None, duration=delta,
                prefix=ctx.clean_prefix,
            )
        except EventAlreadyLive:
            return await ctx.send(_("A raffle is already live."))
        except discord.HTTPException as exc:
            return await ctx.send(_("Couldn't post the raffle: {error}").format(error=exc))
        await ctx.send(_("Raffle started: {link}").format(link=message.jump_url))

    @is_gm()
    @gmraffle.command(name="draw", hidden=True, brief=_("Draw the raffle now"))
    @locale_doc
    async def gmraffle_draw(self, ctx):
        _("""Ends the live raffle now and draws the winner.""")
        row = await self._live_raffle()
        if row is None:
            return await ctx.send(_("There is no live raffle."))
        if await self.finalize_raffle(row["id"]):
            await ctx.send(_("Raffle drawn."))
        else:
            await ctx.send(_("It is already being drawn by another process."))

    @is_gm()
    @gmraffle.command(name="cancel", hidden=True, brief=_("Cancel the raffle"))
    @locale_doc
    async def gmraffle_cancel(self, ctx, *, reason: str = None):
        _(
            """`[reason]` - shown in the announcement
            Cancels the live raffle and refunds every ticket."""
        )
        row = await self._live_raffle()
        if row is None:
            return await ctx.send(_("There is no live raffle."))
        if await self.finalize_raffle(row["id"], cancel=True, reason=reason):
            await ctx.send(_("Raffle cancelled and tickets refunded."))
        else:
            await ctx.send(_("It is already being closed by another process."))

    @is_gm()
    @gmraffle.command(name="status", hidden=True, brief=_("Raffle status"))
    @locale_doc
    async def gmraffle_status(self, ctx):
        _("""Shows entrants, total tickets and gold collected.""")
        row = await self._live_raffle()
        if row is None:
            return await ctx.send(_("There is no live raffle."))
        stats = await self.bot.pool.fetchrow(
            "SELECT COUNT(DISTINCT user_id) AS entrants, COALESCE(SUM(quantity), 0) AS tickets, "
            "COALESCE(SUM(paid), 0) AS gold FROM raffle_purchases "
            "WHERE raffle_id = $1 AND NOT refunded",
            row["id"],
        )
        await ctx.send(
            _(
                "Raffle #{id} (**{prize}**), status `{status}`.\n"
                "Entrants: **{entrants}**, tickets: **{tickets}**, gold collected: **${gold:,}**."
            ).format(
                id=row["id"], prize=row["prize"], status=row["status"],
                entrants=stats["entrants"], tickets=stats["tickets"], gold=stats["gold"],
            ),
            allowed_mentions=NO_PINGS,
        )

    @commands.group(
        name="raffle", hidden=True, invoke_without_command=True, brief=_("Raffle tickets")
    )
    @locale_doc
    async def raffle(self, ctx):
        _("""Use `raffle buy <quantity>` to buy tickets in the live raffle.""")
        await ctx.send(_("Use `{prefix}raffle buy <quantity>`.").format(prefix=ctx.clean_prefix))

    @has_char()
    @raffle.command(name="buy", hidden=True, brief=_("Buy raffle tickets"))
    @locale_doc
    async def raffle_buy(self, ctx, quantity: int):
        _(
            """`<quantity>` - how many tickets to buy (1 to 1000)
            Buys tickets in the live raffle with your gold."""
        )
        try:
            qty = logic.parse_quantity(str(quantity))
        except ValueError as exc:
            return await ctx.send(_(str(exc)))
        _ok, message = await self.buy_raffle_tickets(ctx.author.id, None, qty)
        await ctx.send(message, allowed_mentions=NO_PINGS)

    # ======================================================================= LOOPS

    @tasks.loop(seconds=30)
    async def close_due(self):
        try:
            silent = await self.bot.pool.fetch(
                "SELECT id, channel_id FROM silent_auctions "
                "WHERE status IN ('open', 'closing') AND ends_at <= NOW()"
            )
            for row in silent:
                if self.bot.get_channel(row["channel_id"]) is None:
                    continue  # another cluster owns this guild
                try:
                    await self.finalize_silent_auction(row["id"])
                except Exception:
                    log.exception("closing silent auction %s failed", row["id"])
            raffles = await self.bot.pool.fetch(
                "SELECT id, channel_id FROM raffles "
                "WHERE status IN ('open', 'drawing') AND ends_at IS NOT NULL AND ends_at <= NOW()"
            )
            for row in raffles:
                if self.bot.get_channel(row["channel_id"]) is None:
                    continue
                try:
                    await self.finalize_raffle(row["id"])
                except Exception:
                    log.exception("drawing raffle %s failed", row["id"])
        except Exception:
            log.exception("gm_events close loop failed")

    @tasks.loop(seconds=EMBED_REFRESH_SECONDS)
    async def refresh_raffle_embeds(self):
        """Debounced public ticket counter: at most one edit per raffle per tick."""
        for raffle_id in list(self._dirty_raffles):
            self._dirty_raffles.discard(raffle_id)
            try:
                row = await self.bot.pool.fetchrow(
                    "SELECT * FROM raffles WHERE id = $1 AND status = 'open'", raffle_id
                )
                channel = self.bot.get_channel(row["channel_id"]) if row else None
                if not row or channel is None or not row["message_id"]:
                    continue
                stats = await self.bot.pool.fetchrow(
                    "SELECT COUNT(DISTINCT user_id) AS entrants, "
                    "COALESCE(SUM(quantity), 0) AS tickets "
                    "FROM raffle_purchases WHERE raffle_id = $1 AND NOT refunded",
                    raffle_id,
                )
                await channel.get_partial_message(row["message_id"]).edit(
                    embeds=self._row_embeds(
                        "raffle", row, tickets=stats["tickets"], entrants=stats["entrants"]
                    )
                )
            except discord.HTTPException:
                pass
            except Exception:
                log.exception("raffle embed refresh failed")

    @close_due.before_loop
    async def _close_due_ready(self):
        await self.bot.wait_until_ready()

    @refresh_raffle_embeds.before_loop
    async def _refresh_ready(self):
        await self.bot.wait_until_ready()


async def setup(bot):
    await bot.add_cog(GMEvents(bot))

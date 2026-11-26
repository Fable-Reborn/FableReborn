"""The single renderer for every auction/raffle announcement.

The text commands, the builder's preview, the builder's post and every later re-render from a
stored database row all call :func:`build_announcement`, so what the GM previews is exactly what
players get. The "How to take part" embed is written here from the real rules and is not GM
editable. No database or bot state is used.
"""
from __future__ import annotations

import datetime
from typing import Optional

import discord

from utils.i18n import _

KINDS = ("classic", "silent", "raffle")
ICONS = {"classic": "🔨", "silent": "🔒", "raffle": "🎟️"}
COLOURS = {
    "classic": discord.Colour.gold(),
    "silent": discord.Colour.dark_gold(),
    "raffle": discord.Colour.green(),
}

TITLE_LIMIT = 256
DESCRIPTION_LIMIT = 4096
FIELD_LIMIT = 1024
EMBED_TOTAL_LIMIT = 6000
HOWTO_LIMIT = 1000
CLASSIC_IDLE_HOURS = 12  # run_auction waits 43200 seconds for the next bid


class EventAlreadyLive(Exception):
    """Another auction/raffle of this type is already running."""


def clip(text: Optional[str], limit: int) -> str:
    text = str(text or "")
    return text if len(text) <= limit else text[: limit - 1] + "…"


def pings_enabled(bot) -> bool:
    """Role pings for auctions/raffles are paused unless ``event_pings_enabled = true`` is set
    under ``[ids.game_master]`` in config.toml (read at call time, so ``$reloadconfig`` works)."""
    ids = getattr(getattr(bot, "config", None), "ids", None)
    gm_ids = getattr(ids, "game_master", None) if ids is not None else None
    return bool(gm_ids.get("event_pings_enabled", False)) if isinstance(gm_ids, dict) else False


def allowed_mentions_for(role, ping: bool) -> discord.AllowedMentions:
    """Only the chosen role can ping, and only when ping is on. GM text pings nobody."""
    return discord.AllowedMentions(
        everyone=False, users=False, roles=[role] if (ping and role is not None) else False
    )


def ts(dt: datetime.datetime) -> str:
    unix = int(dt.timestamp())
    return f"<t:{unix}:F> (<t:{unix}:R>)"


def default_title(kind: str, name: str) -> str:
    label = {
        "classic": _("Auction"),
        "silent": _("Silent Auction"),
        "raffle": _("Raffle"),
    }[kind]
    return f"{ICONS[kind]} {label}: {name}"


def default_message(kind: str) -> str:
    return {
        "classic": _("A new auction has started! Place your bids."),
        "silent": _("A silent auction has started! Place your sealed bid."),
        "raffle": _("A new raffle has started! Grab your tickets."),
    }[kind]


def _ends_text(kind: str, ends_at) -> str:
    if kind == "classic":
        return _("{hours} hours after the last bid").format(hours=CLASSIC_IDLE_HOURS)
    if ends_at is None:
        return _("When a GM draws")
    return ts(ends_at)


def how_to_take_part(
    kind: str, *, prefix: str, ends_at=None, min_bid=None, ticket_price=None, max_per_user=None
) -> str:
    """Rules text. Every number and rule here mirrors the code that enforces it."""
    if kind == "classic":
        lines = [
            _("Type `{prefix}bid <amount>` in any channel.").format(prefix=prefix),
            _("Your bid must be higher than the current top bid, and you can't outbid yourself."),
            _("Your gold is taken when you bid and refunded automatically if someone outbids you."),
            _(
                "The auction ends when {hours} hours pass without a new bid; "
                "the highest bidder then wins."
            ).format(hours=CLASSIC_IDLE_HOURS),
        ]
    elif kind == "silent":
        lines = [
            _(
                "Press **🔒 Place / Raise Bid** below and enter an amount (minimum ${min_bid:,})."
            ).format(min_bid=min_bid or 0),
            _(
                "Or type `{prefix}silentbid <amount>`. Your message is deleted and the result is "
                "sent to your DMs, so it's safest to use it in a DM with the bot."
            ).format(prefix=prefix),
            _("Only you can see your bid; nobody can see who is winning."),
            _(
                "You can raise your bid any time, but you can't lower or withdraw it. "
                "Only the difference is taken."
            ),
            _("Press **View My Bid** to check it."),
            _(
                "Ends {ends}. The highest bid wins; if two bids are equal, "
                "whoever reached that amount first wins."
            ).format(ends=ts(ends_at) if ends_at else "-"),
            _("Everyone else is refunded automatically."),
        ]
    else:
        cap = (
            _("max {cap} per player").format(cap=max_per_user)
            if max_per_user
            else _("no limit per player")
        )
        lines = [
            _("Press **🎟️ Buy Tickets** below, or type `{prefix}raffle buy <amount>`.").format(
                prefix=prefix
            ),
            _("Each ticket costs ${price:,} ({cap}).").format(price=ticket_price or 0, cap=cap),
            _("More tickets means better odds."),
            _(
                "When the raffle ends ({ends}), all tickets are shuffled and one is drawn "
                "at random."
            ).format(ends=ts(ends_at) if ends_at else _("when a GM draws")),
            _("The fairness code above lets anyone check the draw afterwards."),
            _("Ticket gold isn't refunded unless the raffle is cancelled."),
        ]
    return clip("\n".join(f"• {line}" for line in lines), HOWTO_LIMIT)


def build_announcement(
    kind: str,
    *,
    name: str,
    title: Optional[str] = None,
    message: Optional[str] = None,
    gm_name: str,
    prefix: str = "$",
    ends_at: Optional[datetime.datetime] = None,
    min_bid: Optional[int] = None,
    ticket_price: Optional[int] = None,
    max_per_user: Optional[int] = None,
    commitment: Optional[str] = None,
    role_mention: Optional[str] = None,
    tickets: Optional[int] = None,
    entrants: Optional[int] = None,
) -> tuple[Optional[str], list[discord.Embed]]:
    """Returns ``(content, [announcement_embed, how_to_embed])``.

    ``role_mention`` is the only thing that goes in ``content`` (pass ``None`` for ping off).
    GM-typed ``title``/``message`` are used verbatim (clipped) and never go through ``_()``.
    """
    if kind not in KINDS:
        raise ValueError(kind)
    name = clip(name, 200)
    embed = discord.Embed(
        title=clip((title or "").strip() or default_title(kind, name), TITLE_LIMIT),
        description=clip((message or "").strip() or default_message(kind), DESCRIPTION_LIMIT),
        colour=COLOURS[kind],
    )
    embed.add_field(
        name=_("Prize") if kind == "raffle" else _("Item"),
        value=clip(name, FIELD_LIMIT),
    )
    if kind == "silent":
        embed.add_field(name=_("Minimum bid"), value=f"${min_bid or 0:,}")
    if kind == "raffle":
        embed.add_field(name=_("Ticket price"), value=f"${ticket_price or 0:,}")
        embed.add_field(
            name=_("Max per player"), value=str(max_per_user) if max_per_user else _("No limit")
        )
    embed.add_field(name=_("Ends"), value=clip(_ends_text(kind, ends_at), FIELD_LIMIT))
    if kind == "raffle":
        if tickets is not None:
            embed.add_field(
                name=_("Tickets sold"),
                value=_("{tickets} tickets, {entrants} players").format(
                    tickets=tickets, entrants=entrants or 0
                ),
                inline=False,
            )
        embed.add_field(
            name=_("Fairness commitment"),
            value=clip(f"`{commitment or '-'}`", FIELD_LIMIT),
            inline=False,
        )
    embed.set_footer(text=clip(_("Hosted by {gm}").format(gm=gm_name), 2048))

    howto = discord.Embed(
        title=_("How to take part"),
        description=how_to_take_part(
            kind,
            prefix=prefix,
            ends_at=ends_at,
            min_bid=min_bid,
            ticket_price=ticket_price,
            max_per_user=max_per_user,
        ),
        colour=COLOURS[kind],
    )
    # Discord rejects a message whose embeds total more than 6000 characters.
    overflow = len(embed) + len(howto) - EMBED_TOTAL_LIMIT
    if overflow > 0 and embed.description:
        embed.description = clip(embed.description, max(1, len(embed.description) - overflow))
    return (role_mention or None), [embed, howto]

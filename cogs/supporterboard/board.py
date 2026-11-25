"""Builds the Hall of Supporters post: who supports Fable, grouped by tier.

Pure apart from discord.Embed, so it can be tested without a bot.
Mentions in embeds show the player's name but never ping them.
"""
from __future__ import annotations

import datetime as dt

import discord

# Highest tier first. Same names, colors, and icons as the $prpg pills.
TIERS = (
    (4, "Legendary Hero", "✦", 0xFFD666),
    (3, "Hero", "✦", 0xC496FF),
    (2, "Warrior", "✦", 0x80B0FF),
    (1, "Adventurer", "✦", 0x78D6A0),
)
BOOSTER_TITLE = "💎 Server Boosters"
GOLD = 0xF5B942
FIELD_LIMIT = 1024
EMBED_FIELDS = 25
MESSAGE_CHARS = 5800  # Discord allows 6000 across every embed in one message.
MAX_EMBEDS = 10


def _chunks(mentions: list[str], limit: int = FIELD_LIMIT) -> list[str]:
    """Join mentions with ' • ' into values that each fit one embed field."""
    values, current = [], ""
    for mention in mentions:
        piece = mention if not current else f" • {mention}"
        if len(current) + len(piece) > limit:
            values.append(current)
            current = mention
        else:
            current += piece
    if current:
        values.append(current)
    return values


def board_fields(tiers: dict[int, list[int]], boosters: list[int]) -> list[tuple[str, str]]:
    """(name, value) fields in display order: tiers high to low, then boosters."""
    fields = []
    for tier, name, icon, _color in TIERS:
        ids = sorted(set(tiers.get(tier) or []))
        if not ids:
            continue
        values = _chunks([f"<@{user_id}>" for user_id in ids])
        for index, value in enumerate(values):
            title = f"{icon} {name} · {len(ids)}" if index == 0 else f"{icon} {name} (cont.)"
            fields.append((title, value))
    booster_ids = sorted(set(boosters or []))
    if booster_ids:
        values = _chunks([f"<@{user_id}>" for user_id in booster_ids])
        for index, value in enumerate(values):
            title = f"{BOOSTER_TITLE} · {len(booster_ids)}" if index == 0 else f"{BOOSTER_TITLE} (cont.)"
            fields.append((title, value))
    return fields


def build_board_embeds(
    tiers: dict[int, list[int]],
    boosters: list[int],
    *,
    prefix: str = "$",
    updated_at: dt.datetime | None = None,
) -> list[discord.Embed]:
    """The whole post as up to 10 embeds that together stay under Discord's limits."""
    updated_at = updated_at or dt.datetime.now(dt.timezone.utc)
    supporter_count = len({uid for ids in tiers.values() for uid in ids} | set(boosters or []))
    header = discord.Embed(
        title="💎 Hall of Supporters 💎",
        description=(
            "Fable runs on the generosity of these heroes. Every Patreon pledge and "
            "every server boost keeps the servers on, pays for new content, and keeps "
            "the realm free for everyone.\n\n"
            f"**{supporter_count}** {'supporter' if supporter_count == 1 else 'supporters'} "
            "and counting. **Thank you.** ✨"
        ),
        colour=GOLD,
    )
    footer = (
        f"Want to join them? {prefix}donate · Prefer not to be listed? {prefix}supporters hide · Updated hourly"
    )

    fields = board_fields(tiers, boosters)
    if not fields:
        header.add_field(
            name="✦ Be the first",
            value=f"No supporters yet. Use `{prefix}donate` to be the first name on this wall.",
            inline=False,
        )
        header.set_footer(text=footer)
        header.timestamp = updated_at
        return [header]

    embeds = [header]
    total = len(header.title) + len(header.description) + len(footer)
    current = header
    shown = 0
    for name, value in fields:
        size = len(name) + len(value)
        if total + size > MESSAGE_CHARS:
            break
        if len(current.fields) >= EMBED_FIELDS:
            if len(embeds) >= MAX_EMBEDS:
                break
            current = discord.Embed(colour=GOLD)
            embeds.append(current)
        current.add_field(name=name, value=value, inline=False)
        total += size
        shown += 1
    if shown < len(fields):
        hidden = sum(value.count("<@") for _name, value in fields[shown:])
        current.add_field(name="…and more", value=f"+{hidden} more supporters. Thank you all!", inline=False)
    embeds[-1].set_footer(text=footer)
    embeds[-1].timestamp = updated_at
    return embeds

"""Bot-log announcements for natural top crate rolls: Masterwork (95+) and Flawless (100).

Posted through the REST API, so any cluster can post no matter where the
channel lives. Mentions inside embeds show the name but never ping.
"""
from __future__ import annotations

import logging

import discord
from discord.http import handle_message_parameters

from classes.equipment.definitions import (
    MODIFIERS,
    QUALITY_TIER_BONUS,
    QUALITY_TIER_NAME,
    REFINE_QUALITY_CAP,
    SLOT_NOUN,
    item_tier,
    quality_band,
)
from classes.equipment.protection import line_label

log = logging.getLogger(__name__)

ROLL_ANNOUNCE_CHANNEL_ID = 1406296535443963935
MAX_EMBEDS = 10

STYLE = {
    "masterwork": {"title": "✦ MASTERWORK ROLL ✦", "color": 0xE2B040},
    "flawless": {"title": "🌟 FLAWLESS ROLL 🌟", "color": 0xFFE8A0},
    "discovery": {"title": "🌟 LEGENDARY DISCOVERY 🌟", "color": 0xFFD666},
}


def _trim(value: float) -> str:
    return f"{value:.2f}".rstrip("0").rstrip(".") or "0"


def _bonus_text(tier: str) -> str:
    percent = int(round((float(QUALITY_TIER_BONUS[tier]) - 1) * 100))
    return f"+{percent}% to every stat on the piece"


def roll_announcement_embed(user_id: int, display_name: str, avatar_url: str | None, crate_rarity: str, item: dict):
    """The embed for one top roll, or None when the piece is not Masterwork or better."""
    tier = item_tier(item)
    if tier is None:
        return None
    discovery = bool(item.get("fully_rolled"))
    style = STYLE["discovery" if discovery else tier]
    quality = int(item.get("rolled_quality") or item.get("quality") or 0)
    rarity = str(item.get("rarity") or crate_rarity).title()
    slot = SLOT_NOUN.get(str(item.get("slot") or "chest"), "Armor")
    crate = str(crate_rarity).title()

    if discovery:
        opener = (
            f"<@{user_id}> opened a **{crate} crate** and uncovered a fully rolled discovery: "
            f"quality **{quality}** with both enchantments. It counts as **Flawless**."
        )
    elif tier == "flawless":
        opener = f"<@{user_id}> opened a **{crate} crate** and pulled a perfect natural **100**."
    else:
        opener = f"<@{user_id}> opened a **{crate} crate** and pulled a natural **{quality}**."

    embed = discord.Embed(
        title=style["title"],
        description=(
            f"{opener}\n\n"
            f"### {item.get('name') or slot}\n"
            f"{line_label(str(item.get('archetype') or ''))} · {slot} · {rarity}"
        ),
        colour=style["color"],
    )
    embed.add_field(name="Quality", value=f"**{quality}** · {quality_band(quality)}", inline=True)
    embed.add_field(name=QUALITY_TIER_NAME[tier], value=_bonus_text(tier), inline=True)
    embed.add_field(name="​", value="​", inline=True)
    embed.add_field(name="Blessing", value=f"+{_trim(float(item.get('offense_value') or 0) * 100)}%", inline=True)
    embed.add_field(name="Ward", value=f"+{_trim(float(item.get('defense_value') or 0))}", inline=True)
    enchants = [
        MODIFIERS[str(m.get("modifier_id") if isinstance(m, dict) else m)]["name"]
        for m in item.get("modifiers") or []
        if str(m.get("modifier_id") if isinstance(m, dict) else m) in MODIFIERS
    ]
    embed.add_field(name="Enchantments", value=", ".join(enchants) or "None", inline=True)
    if avatar_url:
        embed.set_author(name=display_name, icon_url=avatar_url)
    else:
        embed.set_author(name=display_name)
    embed.set_footer(text=f"The forge stops at {REFINE_QUALITY_CAP}. Only a crate roll reaches this high.")
    return embed


async def announce_top_rolls(bot, user, crate_rarity: str, rewards: list[dict]) -> int:
    """Post every Masterwork/Flawless piece in these crate rewards. Never raises."""
    try:
        avatar = getattr(getattr(user, "display_avatar", None), "url", None)
        name = getattr(user, "display_name", None) or str(user)
        embeds = []
        for reward in rewards or []:
            item = (reward or {}).get("item")
            if not item:
                continue
            embed = roll_announcement_embed(int(user.id), name, avatar, crate_rarity, item)
            if embed is not None:
                embeds.append(embed)
        if not embeds:
            return 0
        for start in range(0, len(embeds), MAX_EMBEDS):
            with handle_message_parameters(
                embeds=embeds[start : start + MAX_EMBEDS],
                allowed_mentions=discord.AllowedMentions.none(),
            ) as params:
                await bot.http.send_message(ROLL_ANNOUNCE_CHANNEL_ID, params=params)
        return len(embeds)
    except Exception:
        log.warning("Top roll announcement could not be posted", exc_info=True)
        return 0

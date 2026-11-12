"""Separate themed gear screen for testing.

This is not $gear. It posts the same chronicle card inside one Discord box,
with the slot buttons and the Void, Royal, Frost, and Dusk covers in that box.
discord.py 2.4 cannot build the box, so the payload is sent directly.
"""
from __future__ import annotations

import io
import json

import discord
from discord.http import Route

from classes.equipment.card import render_armory
from classes.equipment.character_card import weapon_armor, weapon_damage, worn_totals
from classes.equipment.character_card_v2 import THEMES, theme_named
from classes.equipment.definitions import SLOT_NOUN

V2_FLAG = 1 << 15
PREFIX = "glb"
FOCUSES = ("totals", "head", "chest", "legs", "feet", "right", "left")


def _num(value) -> str:
    text = f"{float(value or 0):.1f}"
    return text[:-2] if text.endswith(".0") else text


def _button(label: str, custom_id: str, style: int) -> dict:
    return {"type": 2, "style": style, "label": label[:80], "custom_id": custom_id[:100]}


def _piece_line(title: str, item: dict | None, *, weapon: bool) -> str:
    if item is None:
        return f"**{title}:** empty"
    if weapon:
        return f"**{title}:** {item['name']} · {_num(weapon_damage(item))} damage · {_num(weapon_armor(item))} armor"
    return (
        f"**{title}:** {item['name']} · "
        f"+{_num(float(item.get('offense_value') or 0) * 100)}% blessing · "
        f"+{_num(item.get('defense_value'))} ward"
    )


def parse_layout_id(custom_id: str, user_id: int) -> tuple[str, str] | None:
    parts = str(custom_id or "").split(":")
    if len(parts) != 5 or parts[0] != PREFIX or parts[1] != str(user_id):
        return None
    _prefix, _owner, kind, value, other = parts
    if kind == "focus" and value in FOCUSES and other in THEMES:
        return value, other
    if kind == "theme" and value in THEMES and other in FOCUSES:
        return other, value
    return None


def build_layout(user_id: int, loadout: dict, weapons: list[dict], *, focus: str, theme: str, title: str) -> list[dict]:
    theme_key, colors = theme_named(theme)
    if focus not in FOCUSES:
        focus = "totals"
    totals = worn_totals(loadout, weapons)
    hands = totals["hands"]

    def cid(kind: str, value: str) -> str:
        other = focus if kind == "theme" else theme_key
        return f"{PREFIX}:{user_id}:{kind}:{value}:{other}"[:100]

    armor_row = {
        "type": 1,
        "components": [
            _button("Totals", cid("focus", "totals"), 1 if focus == "totals" else 2),
            _button("Helm", cid("focus", "head"), 1 if focus == "head" else 2),
            _button("Cuirass", cid("focus", "chest"), 1 if focus == "chest" else 2),
            _button("Greaves", cid("focus", "legs"), 1 if focus == "legs" else 2),
            _button("Sabatons", cid("focus", "feet"), 1 if focus == "feet" else 2),
        ],
    }
    hand_row = {
        "type": 1,
        "components": [
            _button("Right hand", cid("focus", "right"), 1 if focus == "right" else 2),
            _button("Left hand", cid("focus", "left"), 1 if focus == "left" else 2),
        ],
    }
    theme_row = {
        "type": 1,
        "components": [
            _button(spec["label"], cid("theme", key), 1 if key == theme_key else 2)
            for key, spec in THEMES.items()
        ],
    }
    worn = [
        _piece_line("Right hand", hands["right"], weapon=True),
        _piece_line("Left hand", hands["left"], weapon=True),
    ]
    worn.extend(
        _piece_line(SLOT_NOUN[slot], loadout.get(slot), weapon=False)
        for slot in ("head", "chest", "legs", "feet")
    )
    summary = (
        f"**Together** · {theme_key.title()}\n"
        f"Damage {_num(totals['weapon_damage'])} · Armor {_num(totals['weapon_armor'])}\n"
        f"Blessing +{_num(totals['blessing'] * 100)}% · Ward +{_num(totals['ward'])} · "
        f"Vitality +{int(totals['health'])}\n"
        + "\n".join(worn)
    )
    return [
        {
            "type": 17,
            "accent_color": colors["accent"],
            "components": [
                {"type": 10, "content": f"### {title}\nGear lab. This screen is separate from `$gear`."},
                {"type": 12, "items": [{"media": {"url": "attachment://character.png"}}]},
                {"type": 14, "divider": True, "spacing": 1},
                {"type": 10, "content": summary[:4000]},
                armor_row,
                hand_row,
                theme_row,
            ],
        }
    ]


def render_lab(loadout: dict, weapons: list[dict], *, focus: str, theme: str, title: str) -> bytes:
    if focus not in FOCUSES:
        focus = "totals"
    theme_key, _colors = theme_named(theme)
    return render_armory(
        loadout,
        weapons=weapons,
        focus=focus,
        theme=theme_key,
        title=title,
        subtitle="Gear lab. The buttons and the cover are the test.",
    )


def _file(png: bytes) -> discord.File:
    return discord.File(io.BytesIO(png), filename="character.png")


def _form(payload: dict, file: discord.File) -> list[dict]:
    return [
        {"name": "payload_json", "value": json.dumps(payload)},
        {
            "name": "files[0]",
            "value": file.fp,
            "filename": file.filename,
            "content_type": "application/octet-stream",
        },
    ]


async def send_layout(bot, channel_id: int, png: bytes, components: list[dict]):
    file = _file(png)
    payload = {
        "flags": V2_FLAG,
        "components": components,
        "attachments": [{"id": 0, "filename": "character.png"}],
        "allowed_mentions": {"parse": []},
    }
    route = Route("POST", "/channels/{channel_id}/messages", channel_id=channel_id)
    try:
        return await bot.http.request(route, files=[file], form=_form(payload, file))
    finally:
        file.close()


async def edit_layout(bot, interaction: discord.Interaction, png: bytes, components: list[dict]):
    file = _file(png)
    payload = {
        "type": 7,
        "data": {
            "flags": V2_FLAG,
            "components": components,
            "attachments": [{"id": 0, "filename": "character.png"}],
            "allowed_mentions": {"parse": []},
        },
    }
    route = Route(
        "POST",
        "/interactions/{interaction_id}/{interaction_token}/callback",
        interaction_id=interaction.id,
        interaction_token=interaction.token,
    )
    try:
        return await bot.http.request(route, files=[file], form=_form(payload, file))
    finally:
        file.close()

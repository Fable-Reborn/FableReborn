"""Gear balance telemetry: event rows in Postgres, review markdown on export.

Live clusters all write the same `equipment_events` table. At the end of a
balance window a GM runs `$gear balance` (default 7 days) and gets a markdown
file to hand the next review pass.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

log = logging.getLogger(__name__)

REVIEW_DIR = Path("logs")
REVIEW_NAME = "gear_balance_review.md"
DEFAULT_DAYS = 7
MAX_DAYS = 60


def _jsonable(value):
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    return value


async def log_event(
    conn,
    user_id: int,
    action: str,
    *,
    equipment_id: int | None = None,
    rarity: str | None = None,
    archetype: str | None = None,
    slot: str | None = None,
    payload: dict | None = None,
) -> None:
    """Append one gear event. Never raises into gameplay."""
    try:
        await conn.execute(
            """
            INSERT INTO equipment_events (
                user_id, action, equipment_id, rarity, archetype, slot, payload
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb)
            """,
            int(user_id),
            str(action),
            int(equipment_id) if equipment_id is not None else None,
            str(rarity).lower() if rarity else None,
            str(archetype).lower() if archetype else None,
            str(slot).lower() if slot else None,
            json.dumps(_jsonable(payload or {})),
        )
    except Exception:
        log.exception("equipment balance log failed for %s", action)


def review_path() -> Path:
    REVIEW_DIR.mkdir(parents=True, exist_ok=True)
    return REVIEW_DIR / REVIEW_NAME


async def fetch_review_rows(conn, days: int = DEFAULT_DAYS) -> list:
    days = max(1, min(int(days), MAX_DAYS))
    return await conn.fetch(
        """
        SELECT created_at, user_id, action, equipment_id, rarity, archetype, slot, payload
          FROM equipment_events
         WHERE created_at > NOW() - ($1::text || ' days')::interval
         ORDER BY created_at
        """,
        str(days),
    )


def _pct(part: int, whole: int) -> str:
    if whole <= 0:
        return "n/a"
    return f"{(100.0 * part / whole):.1f}%"


def build_review_markdown(rows: list, *, days: int, database: str = "") -> str:
    """Turn raw event rows into a short balance review for next week's pass."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    by_action: dict[str, int] = {}
    players: set[int] = set()
    craft_quality: dict[str, list[int]] = {}
    craft_line: dict[str, int] = {}
    forge: dict[str, dict[str, int]] = {
        "refine": {"ok": 0, "miss": 0, "pity": 0},
        "temper": {"ok": 0, "miss": 0, "pity": 0},
        "inscribe": {"ok": 0, "miss": 0, "pity": 0},
    }
    temper_star: dict[int, dict[str, int]] = {}
    crate_piece = 0
    crate_material_only = 0
    crate_by_rarity: dict[str, int] = {}
    salvage = 0
    market_buy = 0
    market_list = 0
    give = 0
    equip = 0
    attune_binds = 0
    dragon_payouts = 0
    trade_mats = 0
    origins: dict[str, int] = {}

    for row in rows:
        action = str(row["action"])
        by_action[action] = by_action.get(action, 0) + 1
        players.add(int(row["user_id"]))
        payload = row["payload"] or {}
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except json.JSONDecodeError:
                payload = {}

        if action == "craft":
            rarity = str(row["rarity"] or payload.get("rarity") or "?")
            craft_quality.setdefault(rarity, []).append(int(payload.get("quality") or 0))
            line = str(row["archetype"] or "?")
            craft_line[line] = craft_line.get(line, 0) + 1
        elif action in forge:
            bucket = forge[action]
            if payload.get("success"):
                bucket["ok"] += 1
            else:
                bucket["miss"] += 1
            if payload.get("pity_used"):
                bucket["pity"] += 1
            if action == "temper":
                star = int(payload.get("star") or payload.get("refinement") or 0)
                temper_star.setdefault(star, {"ok": 0, "miss": 0})
                temper_star[star]["ok" if payload.get("success") else "miss"] += 1
        elif action == "crate":
            rarity = str(row["rarity"] or payload.get("rarity") or "?")
            crate_by_rarity[rarity] = crate_by_rarity.get(rarity, 0) + 1
            if payload.get("piece_id") or payload.get("has_piece"):
                crate_piece += 1
            else:
                crate_material_only += 1
        elif action == "salvage":
            salvage += 1
        elif action == "market_buy":
            market_buy += 1
        elif action == "market_list":
            market_list += 1
        elif action == "give":
            give += 1
        elif action == "equip":
            equip += 1
        elif action == "attune":
            if payload.get("binds"):
                attune_binds += 1
        elif action == "dragon_materials":
            dragon_payouts += 1
        elif action == "material_trade":
            trade_mats += 1
        elif action == "grant":
            origins["grant"] = origins.get("grant", 0) + 1

    lines = [
        f"# Gear balance review",
        "",
        f"- Exported: **{now}**",
        f"- Window: last **{days}** day(s)",
        f"- Database: **{database or 'unknown'}**",
        f"- Events: **{len(rows)}**",
        f"- Unique players: **{len(players)}**",
        "",
        "## Event counts",
        "",
    ]
    if by_action:
        for action, count in sorted(by_action.items(), key=lambda item: (-item[1], item[0])):
            lines.append(f"- `{action}`: {count}")
    else:
        lines.append("- No gear events in this window.")

    lines.extend(["", "## Crafting", ""])
    if craft_quality:
        for rarity in ("common", "uncommon", "rare", "magic", "legendary"):
            samples = craft_quality.get(rarity) or []
            if not samples:
                continue
            avg = sum(samples) / len(samples)
            lines.append(
                f"- **{rarity}**: {len(samples)} crafts, quality avg {avg:.1f}, "
                f"min {min(samples)}, max {max(samples)}"
            )
        lines.append("- By line: " + ", ".join(f"{name} {count}" for name, count in sorted(craft_line.items())))
    else:
        lines.append("- No crafts.")

    lines.extend(["", "## Forge", ""])
    for action, bucket in forge.items():
        total = bucket["ok"] + bucket["miss"]
        lines.append(
            f"- **{action}**: {total} attempts, success {_pct(bucket['ok'], total)}, "
            f"pity used {bucket['pity']}"
        )
    if temper_star:
        lines.append("- Temper by star reached:")
        for star in sorted(temper_star):
            bucket = temper_star[star]
            total = bucket["ok"] + bucket["miss"]
            lines.append(f"  - +{star}: {total} ({_pct(bucket['ok'], total)} success)")

    lines.extend(["", "## Crates", ""])
    crate_total = crate_piece + crate_material_only
    if crate_total:
        lines.append(
            f"- Armory crate rolls: {crate_total} "
            f"(piece {_pct(crate_piece, crate_total)}, materials-only {_pct(crate_material_only, crate_total)})"
        )
        for rarity, count in sorted(crate_by_rarity.items(), key=lambda item: -item[1]):
            lines.append(f"  - {rarity}: {count}")
    else:
        lines.append("- No crate armory rolls.")

    lines.extend(
        [
            "",
            "## Economy / wear",
            "",
            f"- Salvage: {salvage}",
            f"- Market list / buy: {market_list} / {market_buy}",
            f"- Player give/move: {give}",
            f"- Equip: {equip}",
            f"- First-bind attunements logged: {attune_binds}",
            f"- Dragon material payouts: {dragon_payouts}",
            f"- Garron material trades: {trade_mats}",
            "",
            "## Notes for the next pass",
            "",
            "- Compare craft quality averages to the intended triangular modes.",
            "- Check temper/refine success and pity usage against the published chances.",
            "- Watch whether Magic/Legendary crafts or crate pieces dominate wear.",
            "- Look for salvage or market volume that suggests dead rarities.",
            "",
            "## Raw action tally JSON",
            "",
            "```json",
            json.dumps(by_action, indent=2, sort_keys=True),
            "```",
            "",
        ]
    )
    return "\n".join(lines)


async def write_review(conn, *, days: int = DEFAULT_DAYS, database: str = "") -> Path:
    rows = await fetch_review_rows(conn, days)
    text = build_review_markdown(rows, days=days, database=database)
    path = review_path()
    path.write_text(text, encoding="utf-8")
    return path

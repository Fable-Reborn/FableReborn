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
    """Append one gear event. Never raises into gameplay.

    The insert runs in its own savepoint. Without it, a failed insert inside
    the caller's transaction aborts that transaction, and the lock, listing,
    or salvage the player was told about silently rolls back at COMMIT.
    """
    try:
        transaction = getattr(conn, "transaction", None)
        if transaction is None:
            await _insert_event(conn, user_id, action, equipment_id, rarity, archetype, slot, payload)
            return
        async with transaction():
            await _insert_event(conn, user_id, action, equipment_id, rarity, archetype, slot, payload)
    except Exception:
        log.exception("equipment balance log failed for %s", action)


async def _insert_event(conn, user_id, action, equipment_id, rarity, archetype, slot, payload) -> None:
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


def temper_target_star(payload: dict) -> int:
    """The star an attempt was trying for.

    Newer rows log `target_star`. Older rows log `star` as the star the piece
    ended on, so a failure there means it was trying for the next one.
    """
    if payload.get("target_star") is not None:
        return int(payload["target_star"])
    star = int(payload.get("star") or payload.get("refinement") or 0)
    return star if payload.get("success") else star + 1


def _refine_band_pity(quality_before) -> int | None:
    from classes.equipment.definitions import REFINE_QUALITY_BANDS

    if quality_before is None:
        return None
    for band in REFINE_QUALITY_BANDS:
        if int(quality_before) <= band[0]:
            return int(band[-1])
    return None


def real_pity_used(action: str, payload: dict) -> bool:
    """Pity that changed the outcome. A band with pity 0 always succeeds, so it is not pity.

    Newer rows log `pity_threshold`. For older refine rows the band is read
    from `quality_before`.
    """
    if not payload.get("pity_used"):
        return False
    threshold = payload.get("pity_threshold")
    if threshold is None and action == "refine":
        threshold = _refine_band_pity(payload.get("quality_before"))
    return threshold is None or int(threshold) > 0


def is_guaranteed_refine(payload: dict) -> bool:
    threshold = payload.get("pity_threshold")
    if threshold is None:
        threshold = _refine_band_pity(payload.get("quality_before"))
    return threshold == 0


TIERS = ("common", "uncommon", "rare", "magic", "legendary")
LINE_LABEL = {"guardian": "Aegis (Guardian)", "slayer": "Razor (Slayer)", "vanguard": "Oath (Vanguard)"}


def _payload(row) -> dict:
    payload = row["payload"] or {}
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except json.JSONDecodeError:
            payload = {}
    return payload if isinstance(payload, dict) else {}


def _tier(material_id: str) -> str:
    from classes.equipment.definitions import material_rarity

    try:
        return material_rarity(str(material_id))
    except Exception:
        return "?"


def _add_tiers(target: dict, materials) -> None:
    for material_id, amount in (materials or {}).items():
        if int(amount or 0) > 0:
            tier = _tier(material_id)
            target[tier] = target.get(tier, 0) + int(amount)


def _tier_text(by_tier: dict) -> str:
    parts = [f"{tier} {by_tier[tier]:,}" for tier in (*TIERS, "?") if by_tier.get(tier)]
    return ", ".join(parts) or "none"


def expected_quality_mean(rarity: str) -> float | None:
    """Mean of triangular(1, 100, mode): what crate and craft quality should average."""
    from classes.equipment.definitions import QUALITY_MODE

    mode = QUALITY_MODE.get(str(rarity).lower())
    return None if mode is None else (1 + 100 + mode) / 3


def forge_cost(action: str, row, payload: dict) -> tuple[dict, int, bool]:
    """(materials, gold, estimated) one forge attempt cost. Gold and goods are spent hit or miss.

    Newer rows log the cost. Older rows are priced from today's cost tables.
    """
    if "cost" in payload or "gold" in payload:
        return dict(payload.get("cost") or {}), int(payload.get("gold") or 0), False
    from classes.equipment.economy import inscribe_step, refine_step, temper_step

    archetype = str(row["archetype"] or "")
    try:
        if action == "temper":
            step = temper_step(archetype, temper_target_star(payload))
        elif action == "refine":
            step = refine_step(archetype, int(payload.get("quality_before") or 0))
        else:
            step = inscribe_step(archetype)
    except Exception:
        step = None
    if not step:
        return {}, 0, True
    return dict(step.get("cost") or {}), int(step.get("gold") or 0), True


def build_extra_sections(rows: list, snapshot: dict | None = None) -> list[str]:
    """Crate quality, salvage by rarity, material flow, and the worn-gear snapshot."""
    crate_quality: dict[str, list[int]] = {}
    fully_rolled = 0
    salvage_rarity: dict[str, dict[str, int]] = {}
    earned: dict[str, dict[str, int]] = {"crates": {}, "dragons": {}, "salvage": {}}
    spent: dict[str, dict[str, int]] = {"craft": {}, "refine": {}, "temper": {}, "inscribe": {}}
    forge_gold: dict[str, int] = {"refine": 0, "temper": 0, "inscribe": 0}
    estimated = 0
    market_gold = 0
    equip_line: dict[str, int] = {}
    equip_rarity: dict[str, int] = {}

    for row in rows:
        action = str(row["action"])
        payload = _payload(row)
        rarity = str(row["rarity"] or payload.get("rarity") or "?").lower()
        if action == "crate":
            _add_tiers(earned["crates"], payload.get("materials"))
            if payload.get("has_piece") or payload.get("piece_id"):
                if payload.get("fully_rolled"):
                    fully_rolled += 1
                elif payload.get("quality") is not None:
                    crate_quality.setdefault(rarity, []).append(int(payload["quality"]))
        elif action == "dragon_materials":
            _add_tiers(earned["dragons"], payload.get("materials"))
        elif action == "salvage":
            bucket = salvage_rarity.setdefault(rarity, {"single": 0, "bulk": 0})
            bucket["bulk" if payload.get("bulk") else "single"] += 1
            _add_tiers(earned["salvage"], payload.get("materials"))
        elif action == "craft":
            _add_tiers(spent["craft"], payload.get("cost"))
        elif action in forge_gold:
            materials, gold, guessed = forge_cost(action, row, payload)
            _add_tiers(spent[action], materials)
            forge_gold[action] += gold
            estimated += 1 if guessed else 0
        elif action == "market_buy":
            market_gold += int(payload.get("price") or 0)
        elif action == "equip":
            line = str(row["archetype"] or "?").lower()
            equip_line[line] = equip_line.get(line, 0) + 1
            equip_rarity[rarity] = equip_rarity.get(rarity, 0) + 1

    lines = ["", "## Crate pieces", ""]
    if crate_quality or fully_rolled:
        for rarity in TIERS:
            samples = crate_quality.get(rarity) or []
            if not samples:
                continue
            expected = expected_quality_mean(rarity)
            target = f" (expected about {expected:.1f})" if expected else ""
            lines.append(
                f"- **{rarity}**: {len(samples)} pieces, quality avg {sum(samples) / len(samples):.1f}{target}, "
                f"min {min(samples)}, max {max(samples)}"
            )
        lines.append(f"- Fully rolled discoveries: {fully_rolled}")
        top = {rarity: sum(1 for q in samples if q >= 95) for rarity, samples in crate_quality.items()}
        perfect = sum(1 for samples in crate_quality.values() for q in samples if q >= 100)
        top_text = ", ".join(f"{rarity} {top[rarity]}" for rarity in TIERS if top.get(rarity))
        lines.append(f"- Natural 95+ (Masterwork or better): {sum(top.values())}" + (f" ({top_text})" if top_text else ""))
        lines.append(f"- Natural 100 (Flawless): {perfect}")
    else:
        lines.append("- No crate pieces.")
    craft_targets = ", ".join(f"{rarity} {expected_quality_mean(rarity):.1f}" for rarity in TIERS)
    lines.append(f"- Expected craft and crate quality averages: {craft_targets}")

    lines.extend(["", "## Salvage by rarity", ""])
    if salvage_rarity:
        for rarity in (*TIERS, "?"):
            bucket = salvage_rarity.get(rarity)
            if bucket:
                lines.append(
                    f"- **{rarity}**: {bucket['single'] + bucket['bulk']} "
                    f"({bucket['single']} single, {bucket['bulk']} Salvage All)"
                )
    else:
        lines.append("- No salvage.")

    lines.extend(["", "## Material flow (by material tier)", ""])
    total_in: dict[str, int] = {}
    total_out: dict[str, int] = {}
    for source, by_tier in earned.items():
        lines.append(f"- Earned from {source}: {_tier_text(by_tier)}")
        for tier, amount in by_tier.items():
            total_in[tier] = total_in.get(tier, 0) + amount
    for sink, by_tier in spent.items():
        lines.append(f"- Spent on {sink}: {_tier_text(by_tier)}")
        for tier, amount in by_tier.items():
            total_out[tier] = total_out.get(tier, 0) + amount
    net = []
    for tier in TIERS:
        if total_in.get(tier) or total_out.get(tier):
            gained, used = total_in.get(tier, 0), total_out.get(tier, 0)
            ratio = f" ({used / gained:.0%} of earned spent)" if gained else ""
            net.append(f"{tier} {gained - used:+,}{ratio}")
    lines.append(f"- **Net**: {', '.join(net) or 'none'}")
    lines.append(
        "- Forge gold spent: "
        + ", ".join(f"{action} ${gold:,}" for action, gold in forge_gold.items())
        + f" (total ${sum(forge_gold.values()):,})"
    )
    if estimated:
        lines.append(f"  - {estimated} older forge rows were priced from today's cost tables.")
    lines.append(f"- Gear shop gold traded: ${market_gold:,}")

    lines.extend(["", "## Equips this window", ""])
    if equip_line:
        lines.append(
            "- By line: "
            + ", ".join(f"{LINE_LABEL.get(line, line)} {count}" for line, count in sorted(equip_line.items()))
        )
        lines.append(
            "- By rarity: "
            + ", ".join(f"{rarity} {equip_rarity[rarity]}" for rarity in (*TIERS, "?") if equip_rarity.get(rarity))
        )
    else:
        lines.append("- No equips.")

    lines.extend(_snapshot_lines(snapshot))
    return lines


def _snapshot_lines(snapshot: dict | None) -> list[str]:
    lines = ["", "## Worn right now (snapshot at export)", ""]
    if snapshot is None:
        return lines + ["- Snapshot not available."]
    worn = snapshot.get("worn") or []
    if not worn:
        lines.append("- Nobody is wearing armor.")
    else:
        wearers: dict[int, dict[str, int]] = {}
        by_line: dict[str, int] = {}
        by_rarity: dict[str, list] = {}
        for piece in worn:
            line = str(piece["archetype"]).lower()
            rarity = str(piece["rarity"]).lower()
            by_line[line] = by_line.get(line, 0) + 1
            by_rarity.setdefault(rarity, []).append(piece)
            counts = wearers.setdefault(int(piece["user_id"]), {})
            counts[line] = counts.get(line, 0) + 1
        main_line: dict[str, int] = {}
        for counts in wearers.values():
            top = max(sorted(counts), key=lambda name: counts[name])
            main_line[top] = main_line.get(top, 0) + 1
        lines.append(f"- Players wearing armor: {len(wearers)}, pieces worn: {len(worn)}")
        lines.append(
            "- Pieces by line: "
            + ", ".join(f"{LINE_LABEL.get(line, line)} {count} ({count / len(worn):.0%})" for line, count in sorted(by_line.items()))
        )
        lines.append(
            "- Players by main line: "
            + ", ".join(f"{LINE_LABEL.get(line, line)} {count}" for line, count in sorted(main_line.items()))
        )
        for rarity in TIERS:
            pieces = by_rarity.get(rarity)
            if not pieces:
                continue
            quality = sum(int(p["quality"]) for p in pieces) / len(pieces)
            temper = sum(int(p["refinement"] or 0) for p in pieces) / len(pieces)
            lines.append(
                f"  - {rarity}: {len(pieces)} worn, quality avg {quality:.1f}, temper avg +{temper:.1f}"
            )
    held = snapshot.get("materials") or []
    lines.extend(["", "## Materials held right now", ""])
    if not held:
        lines.append("- Nobody holds armor materials.")
    else:
        by_tier: dict[str, int] = {}
        holders: dict[str, int] = {}
        for entry in held:
            tier = _tier(entry["material_id"])
            by_tier[tier] = by_tier.get(tier, 0) + int(entry["total"])
            holders[tier] = max(holders.get(tier, 0), int(entry["holders"]))
        for tier in (*TIERS, "?"):
            if by_tier.get(tier):
                lines.append(f"- **{tier}**: {by_tier[tier]:,} held (largest single good held by {holders[tier]} players)")
    return lines


async def fetch_snapshot(conn) -> dict:
    """What is worn and held at export time. Not limited to the window."""
    worn = await conn.fetch(
        """
        SELECT l.user_id, i.archetype, i.rarity, i.slot, i.quality, i.refinement
          FROM equipment_loadout l
          JOIN equipment_items i ON i.id = l.equipment_id AND i.owner_id = l.user_id
        """
    )
    materials = await conn.fetch(
        """
        SELECT material_id, SUM(amount) AS total, COUNT(DISTINCT user_id) AS holders
          FROM equipment_materials
         WHERE amount > 0
         GROUP BY material_id
        """
    )
    return {"worn": [dict(row) for row in worn], "materials": [dict(row) for row in materials]}


def build_review_markdown(rows: list, *, days: int, database: str = "", snapshot: dict | None = None) -> str:
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
    guaranteed_refines = 0
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
            if real_pity_used(action, payload):
                bucket["pity"] += 1
            if action == "refine" and is_guaranteed_refine(payload):
                guaranteed_refines += 1
            if action == "temper":
                star = temper_target_star(payload)
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
    from classes.equipment.definitions import TEMPER_STAR_CHANCE

    for action, bucket in forge.items():
        total = bucket["ok"] + bucket["miss"]
        lines.append(
            f"- **{action}**: {total} attempts, success {_pct(bucket['ok'], total)}, "
            f"pity used {bucket['pity']}"
        )
        if action == "refine" and guaranteed_refines:
            chance_total = total - guaranteed_refines
            chance_ok = bucket["ok"] - guaranteed_refines
            lines.append(
                f"  - {guaranteed_refines} were guaranteed (quality 39 or lower). "
                f"The other {chance_total}: success {_pct(chance_ok, chance_total)}"
            )
    if temper_star:
        lines.append("- Temper by star attempted (published chance in brackets):")
        for star in sorted(temper_star):
            bucket = temper_star[star]
            total = bucket["ok"] + bucket["miss"]
            published = TEMPER_STAR_CHANCE.get(star)
            note = f" [{published:.0%}]" if published is not None else ""
            lines.append(
                f"  - +{star}: {bucket['ok']}/{total} ({_pct(bucket['ok'], total)} success){note}"
            )

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
        ]
    )
    lines.extend(build_extra_sections(rows, snapshot))
    lines.extend(
        [
            "",
            "## Notes for the next pass",
            "",
            "- Compare craft quality averages to the intended triangular modes.",
            "- Check temper/refine success and pity usage against the published chances.",
            "- Watch whether Magic/Legendary crafts or crate pieces dominate wear.",
            "- Look for salvage or market volume that suggests dead rarities.",
            "- Compare crate piece quality to the expected averages; a gap means the roll is off.",
            "- Net material: a tier that keeps growing with little used is piling up.",
            "- Worn by line: one line far above a third of wearers is the one to look at.",
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
    try:
        snapshot = await fetch_snapshot(conn)
    except Exception:
        log.exception("gear balance snapshot failed")
        snapshot = None
    text = build_review_markdown(rows, days=days, database=database, snapshot=snapshot)
    path = review_path()
    path.write_text(text, encoding="utf-8")
    return path

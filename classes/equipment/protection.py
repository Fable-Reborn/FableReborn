"""Armor locks and Salvage All: filter parsing, planning, and player messages.

Pure functions only. The database checks live in `repository.py`
(`piece_protection`, `set_piece_lock`, `salvage_many`), which re-check every
piece under FOR UPDATE, so a stale plan can never destroy a protected piece.
"""
from __future__ import annotations

from classes.equipment.definitions import ARCHETYPE_NOUN, RARITIES, SLOT_NOUN, resolve_slot
from classes.equipment.economy import salvage_yield

PROTECTED_MESSAGES = {
    "locked": "That piece is locked. Use `{prefix}armorunlock <id>` first if you really want to {verb} it.",
    "equipped": "You are wearing that piece. Take it off before you {verb} it.",
    "listed": "That piece is listed in the gear shop. Take it down before you {verb} it.",
}

SKIP_LABELS = {
    "locked": "locked",
    "equipped": "worn",
    "listed": "listed in the gear shop",
    "tempered": "tempered",
    "discovery": "fully rolled discoveries",
    "missing": "no longer yours",
}

def mass_salvage_skip_reason(row, *, equipped: bool, listed: bool) -> str | None:
    """Salvage All never touches these. Single salvage can still take tempered or discovery pieces."""
    if row.get("locked"):
        return "locked"
    if equipped:
        return "equipped"
    if listed:
        return "listed"
    if int(row.get("refinement") or 0) > 0:
        return "tempered"
    if row.get("fully_rolled"):
        return "discovery"
    return None


MASS_SALVAGE_LIMIT = 200


_LINE_WORDS = {}
for _line, _noun in ARCHETYPE_NOUN.items():
    _LINE_WORDS[_line] = _line
    _LINE_WORDS[_noun.lower()] = _line


def line_label(archetype: str) -> str:
    """`Razor (Slayer)` for the menus and messages."""
    archetype = str(archetype or "").lower()
    noun = ARCHETYPE_NOUN.get(archetype)
    return f"{noun} ({archetype.title()})" if noun else archetype.title()


def parse_salvage_filters(text: str) -> tuple[dict[str, set[str]], list[str]]:
    """Turn `common razor helm` into {rarity, archetype, slot} sets plus unknown words."""
    wanted = {"rarity": set(), "archetype": set(), "slot": set()}
    unknown = []
    for raw in str(text or "").replace(",", " ").split():
        word = raw.strip().lower()
        if not word:
            continue
        if word in RARITIES:
            wanted["rarity"].add(word)
        elif word in _LINE_WORDS:
            wanted["archetype"].add(_LINE_WORDS[word])
        elif (slot := resolve_slot(word)) is not None:
            wanted["slot"].add(slot)
        elif word.endswith("s") and (slot := resolve_slot(word[:-1])) is not None:
            wanted["slot"].add(slot)
        else:
            unknown.append(raw)
    return wanted, unknown


def matches_wanted(item, wanted) -> bool:
    """AND across groups, OR within a group. Empty groups match everything."""
    for key in ("rarity", "archetype", "slot"):
        chosen = (wanted or {}).get(key) or set()
        if chosen and str(item.get(key) or "").lower() not in chosen:
            return False
    return True


def plan_mass_salvage(rows, wanted=None) -> dict:
    """Pick the pieces Salvage All would break down and preview the materials.

    `rows` need id, rarity, archetype, slot, quality, locked, refinement,
    fully_rolled, equipped, and listed. The database re-checks all of it.
    """
    ids, skipped, materials, by_rarity = [], {}, {}, {}
    for row in rows:
        if not matches_wanted(row, wanted):
            continue
        reason = mass_salvage_skip_reason(
            row, equipped=bool(row.get("equipped")), listed=bool(row.get("listed"))
        )
        if reason:
            skipped[reason] = skipped.get(reason, 0) + 1
            continue
        if len(ids) >= MASS_SALVAGE_LIMIT:
            skipped["over_limit"] = skipped.get("over_limit", 0) + 1
            continue
        ids.append(int(row["id"]))
        rarity = str(row["rarity"]).lower()
        by_rarity[rarity] = by_rarity.get(rarity, 0) + 1
        for material_id, amount in salvage_yield(
            rarity, str(row["archetype"]).lower(), int(row["quality"])
        ).items():
            materials[material_id] = materials.get(material_id, 0) + int(amount)
    return {"ids": ids, "skipped": skipped, "materials": materials, "by_rarity": by_rarity}


def rarity_breakdown(by_rarity: dict) -> str:
    """`2 Common, 1 Legendary` in rarity order."""
    return ", ".join(
        f"{by_rarity[rarity]} {rarity.title()}" for rarity in RARITIES if by_rarity.get(rarity)
    )


def skipped_text(skipped: dict) -> str:
    parts = []
    for reason, count in (skipped or {}).items():
        if not count:
            continue
        if reason == "over_limit":
            parts.append(f"{count} over the {MASS_SALVAGE_LIMIT} per run limit (run it again)")
        else:
            parts.append(f"{count} {SKIP_LABELS.get(reason, reason)}")
    return ", ".join(parts)


def mass_salvage_confirm_text(plan: dict, materials_text: str) -> str:
    count = len(plan["ids"])
    lines = [
        f"**Salvage {count} piece{'s' if count != 1 else ''}?** They are destroyed. This cannot be undone.",
    ]
    breakdown = rarity_breakdown(plan.get("by_rarity") or {})
    if breakdown:
        lines.append(f"Pieces: {breakdown}.")
    lines.append(f"You will recover about: {materials_text}.")
    skipped = skipped_text(plan.get("skipped"))
    if skipped:
        lines.append(f"Kept safe: {skipped}.")
    return "\n".join(lines)


def mass_salvage_nothing_text(skipped: dict, prefix: str = "$") -> str:
    kept = skipped_text(skipped)
    if kept:
        return f"Nothing to salvage. Kept safe: {kept}."
    return f"Nothing matches. Check `{prefix}armory armor` for your pieces."


def mass_salvage_result_text(summary: dict, materials_text: str) -> str:
    count = len(summary.get("salvaged") or [])
    skipped = skipped_text(summary.get("skipped"))
    if not count:
        return f"Nothing was salvaged.{f' Kept safe: {skipped}.' if skipped else ''}"
    text = f"You break down **{count}** piece{'s' if count != 1 else ''} and recover {materials_text}."
    if skipped:
        text += f"\nKept safe: {skipped}."
    return text


def lock_result_text(status: str, item, equipment_id: int, prefix: str = "$") -> str:
    name = f"**{item['name']}**" if item else f"piece `{equipment_id}`"
    if status == "missing":
        return "You do not own that piece."
    if status == "listed":
        return f"{name} is listed in the gear shop. Take it down with `{prefix}gear unsell {equipment_id}` first."
    if status == "already":
        return f"{name} is already {'locked' if item and item.get('locked') else 'unlocked'}."
    if status == "locked":
        return f"🔒 {name} is locked. It cannot be salvaged, sold, given, or traded until you unlock it."
    if status == "unlocked":
        return f"🔓 {name} is unlocked."
    return "That did not work."


def slot_label(slot: str) -> str:
    return SLOT_NOUN.get(str(slot or ""), str(slot or "").title())

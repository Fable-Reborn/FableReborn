"""Character sheet for $gear.

Same layout as the armory card in card.py: every slot down the left, and the
open page on the right for whichever piece is chosen. The totals of everything
worn sit in the header, so they stay in view on every page.
"""
from __future__ import annotations

from classes.equipment.attunement import refinement_cap
from classes.equipment.card import (
    FULL,
    draw_piece_detail,
    glow_colors,
    medallion,
    modifier_ids,
    piece_numbers,
    section,
    slot_picture,
    stat,
)
from classes.equipment.chronicle import (
    ELEMENT_TINT,
    GOLD,
    GOLD_DEEP,
    INK,
    INK_FAINT,
    INK_MUTED,
    RARITY_GEM,
    RARITY_INK,
    Canvas,
    draw_header,
    header_stats,
    BRONZE_INK,
    PAGE_RULE,
    mix,
    number,
)
from classes.equipment.definitions import PAPER_DOLL_SLOTS, SLOT_NOUN, quality_band
from classes.equipment.economy import modifier_adjustments

WIDTH = 1120
HEIGHT = 780

HAND_NAMES = {"right": "Right hand", "left": "Left hand"}
HAND_RULES = {"any": "Either hand", "left": "Left hand", "right": "Right hand", "both": "Both hands"}


def assign_hands(weapons: list[dict]) -> dict[str, dict | None]:
    """Place equipped weapons into the right and left hands. A two-handed weapon fills both."""
    items = list(weapons or [])
    any_count = sum(1 for item in items if item.get("hand") == "any")
    if len(items) == 2 and any_count == 1 and items[0].get("hand") == "any":
        items = [items[1], items[0]]
    right = left = None
    for item in items:
        hand = item.get("hand")
        if hand == "both":
            right = left = item
        elif hand == "left":
            left = item
        elif hand == "right":
            right = item
        elif right is None:
            right = item
        else:
            left = item
    return {"right": right, "left": left}


def weapon_damage(item: dict) -> float:
    if item.get("effective_damage") is not None:
        return float(item["effective_damage"])
    return float(item.get("damage") or 0)


def weapon_armor(item: dict) -> float:
    if item.get("effective_armor") is not None:
        return float(item["effective_armor"])
    return float(item.get("armor") or 0)


def worn_totals(loadout: dict, weapons: list[dict]) -> dict:
    """Item stats on the worn weapons, counted once, plus every worn armor piece.

    Blessing and ward include Weapon Amplification and Fortified, so the
    sheet shows the same numbers battle uses.
    """
    hands = assign_hands(weapons)
    damage = 0.0
    armor = 0.0
    pieces = []
    for item in (hands["right"], hands["left"]):
        if item is None or any(item is counted for counted in pieces):
            continue
        damage += weapon_damage(item)
        armor += weapon_armor(item)
        pieces.append(item)
    blessing = 0.0
    ward = 0.0
    health = 0
    for slot in PAPER_DOLL_SLOTS:
        item = (loadout or {}).get(slot) or {}
        if not item:
            continue
        extra_weapon, extra_armor, extra_health = modifier_adjustments(item.get("defense_value"), modifier_ids(item))
        blessing += float(item.get("offense_value") or 0) + float(extra_weapon)
        ward += float(item.get("defense_value") or 0) + float(extra_armor)
        health += int(extra_health)
    return {
        "weapon_damage": damage,
        "weapon_armor": armor,
        "blessing": blessing,
        "ward": ward,
        "health": health,
        "weapons": pieces,
        "hands": hands,
    }


def render_character(loadout: dict | None, weapons: list[dict] | None, *, focus: str, title: str, theme=None) -> bytes:
    """Draw the sheet. `focus` is chest, right, or left; anything else shows everything worn."""
    loadout = loadout or {}
    weapons = weapons or []
    canvas = Canvas.tome(WIDTH, HEIGHT, theme)
    totals = worn_totals(loadout, weapons)
    hands = totals["hands"]

    stats_left = header_stats(
        canvas,
        [
            ("Damage", number(totals["weapon_damage"])),
            ("Armor", number(totals["weapon_armor"])),
            ("Blessing", f"+{number(totals['blessing'] * 100)}%"),
            ("Ward", f"+{number(totals['ward'])}"),
            ("Vitality", f"+{int(totals['health'])}"),
        ],
        size=25,
        least=58,
        gap=17,
    )
    draw_header(
        canvas,
        "Character",
        title,
        "Starforge and soulbound are included.",
        title_width=max(220, stats_left - 58 - 30),
    )

    top, bottom = 178, HEIGHT - 42
    slots = [("right", hands["right"]), ("left", hands["left"])]
    slots += [(slot, loadout.get(slot)) for slot in PAPER_DOLL_SLOTS]
    gap = 10
    tile_height = (bottom - top - gap * (len(slots) - 1)) / len(slots)
    for index, (key, item) in enumerate(slots):
        y = top + index * (tile_height + gap)
        _draw_slot(canvas, key, (48, y, 378, y + tile_height), item, selected=focus == key)

    page = (400, top, WIDTH - 48, bottom)
    canvas.page(page)
    if focus == "chest":
        draw_piece_detail(canvas, page, loadout.get("chest"), FULL)
    elif focus in HAND_NAMES:
        _weapon_detail(canvas, page, hands.get(focus), focus)
    else:
        _overview(canvas, page, loadout, hands)
    canvas.text(page[0] + FULL["pad"], page[3] - 26, "Raid multipliers are applied in battle.", "text", 13.5, INK_FAINT)
    return canvas.png()


def _draw_slot(canvas: Canvas, key: str, box, item: dict | None, *, selected: bool) -> None:
    """One slot in the rail on the left."""
    x0, y0, x1, y1 = box
    t = canvas.t
    armor = key in PAPER_DOLL_SLOTS
    open_slot = key in {"right", "left", *PAPER_DOLL_SLOTS}
    rarity = RARITY_GEM.get((item or {}).get("rarity"), t.trim) if armor else t.trim
    colors = glow_colors(item.get("modifiers")) if item and armor else []
    canvas.shadow(box, 12, blur=7, dy=4, alpha=130)
    if selected:
        canvas.glow(box, 12, [t.trim], blur=10, alpha=90, grow=2)
        canvas.panel(box, 12, gradient=t.tile_selected, outline=t.trim, width=2)
    elif item:
        canvas.glow(box, 12, colors, blur=11, alpha=100)
        canvas.panel(box, 12, gradient=t.tile_item, outline=mix(rarity, (0, 0, 0), 0.35) if armor else t.trim_dim, width=1.3)
    else:
        canvas.panel(box, 12, gradient=t.tile_empty, outline=t.trim_dim if open_slot else t.tile_edge, width=1.2)
    canvas.line([(x0 + 14, y0 + 2), (x1 - 14, y0 + 2)], (255, 236, 200, 26), 1)

    inset = 11
    side = (y1 - y0) - 2 * inset
    socket = (x0 + inset, y0 + inset, x0 + inset + side, y1 - inset)
    canvas.socket(socket, 10, border=rarity if item and armor else (t.trim_deep if item else t.trim_dim), glows=colors)
    slot_picture(canvas, key, item, (socket[0] + socket[2]) / 2, (socket[1] + socket[3]) / 2, side * 0.84)

    tx = socket[2] + 14
    right = x1 - 14
    canvas.kicker(tx, y0 + 28, HAND_NAMES.get(key) or SLOT_NOUN.get(key, key), t.kicker, size=10.5, tracking=2.2)
    if item is None:
        canvas.text(tx, y0 + 53, "Empty" if open_slot else "Not forged yet", "strong", 16.5, t.muted if open_slot else t.dim)
    else:
        canvas.text(tx, y0 + 51, canvas.fit(item.get("name") or "", "strong", 16.5, right - tx), "strong", 16.5, t.ivory)
        if armor:
            width = canvas.kicker(tx + 13, y0 + 72, str(item.get("rarity") or ""), rarity, size=10, tracking=1.6)
            canvas.gem(tx + 4, y0 + 68, 4, rarity, dark=True)
            if tx + 13 + width + 14 + Canvas.temper_width(step=13, r=5) <= right:
                canvas.temper(
                    right - Canvas.temper_width(step=13, r=5), y0 + 68,
                    item.get("refinement"), refinement_cap(item.get("attunement")), step=13, r=5, dark=True,
                )
        else:
            line = f"{number(weapon_damage(item))} damage  ·  {number(weapon_armor(item))} armor"
            if key == "left" and item.get("hand") == "both":
                line = "Held in both hands"
            canvas.text(tx, y0 + 72, canvas.fit(line, "text", 13.5, right - tx), "text", 13.5, t.muted)
    if selected:
        mid = (y0 + y1) / 2
        canvas.poly([(x1 + 3, mid - 9), (x1 + 13, mid), (x1 + 3, mid + 9)], fill=t.trim)


def _page_head(canvas: Canvas, box, key: str, item: dict | None, kicker: str, name: str, *, glows=()) -> tuple[float, float, float]:
    """Kicker, name, and medallion, laid out as on the armory page.

    Returns the left margin, the right margin, and where text must stop for the medallion.
    """
    m = FULL
    x0, y0, x1, _y1 = box
    left, right = x0 + m["pad"], x1 - m["pad"]
    hero = m["hero"]
    hx, hy = right - hero / 2, y0 + m["pad"] + hero / 2
    text_right = right - hero - 26
    medallion(canvas, hx, hy, hero, glows=glows)
    slot_picture(canvas, key, item, hx, hy, hero * 0.70)
    canvas.kicker(left, y0 + m["kicker"], kicker)
    size = float(m["name_size"])
    while size > 22 and canvas.text_width(name, "display", size) > text_right - left:
        size -= 2
    canvas.text(left, y0 + m["name"], canvas.fit(name, "display", size, text_right - left), "display", size, INK)
    return left, right, text_right


def _weapon_detail(canvas: Canvas, box, item: dict | None, key: str) -> None:
    m = FULL
    y0 = box[1]
    hand_name = HAND_NAMES[key]
    if item is None:
        left, _right, text_right = _page_head(canvas, box, key, None, hand_name, "Nothing is held")
        canvas.line([(left, y0 + m["rule"] - 30), (text_right, y0 + m["rule"] - 30)], PAGE_RULE, 1)
        canvas.text(left, y0 + m["rule"] + 6, "This hand is free for a weapon or a shield.", "text", 17, INK_MUTED)
        return
    left, right, text_right = _page_head(canvas, box, key, item, hand_name, str(item.get("name") or "Weapon"))
    hero_bottom = y0 + m["pad"] + m["hero"]
    hx = right - m["hero"] / 2
    canvas.kicker(hx, hero_bottom + 30, str(item.get("type") or "Weapon"), INK_MUTED, size=10, anchor="ms", tracking=1.6)

    px, py = left, y0 + m["pills"]
    px += canvas.pill(px, py, item.get("type") or "Weapon", fill=BRONZE_INK) + 8
    element = str(item.get("element") or "").strip()
    if element and element.lower() != "none":
        px += canvas.pill(px, py, element, outline=INK_MUTED, ink=INK_MUTED, dot=ELEMENT_TINT.get(element.lower(), GOLD_DEEP)) + 8
    rule = HAND_RULES.get(str(item.get("hand") or "any"), "Either hand")
    if px + canvas.text_width(rule.upper(), "label", 11, 1.6) + 24 <= text_right:
        px += canvas.pill(px, py, rule, outline=INK_MUTED, ink=INK_MUTED) + 8
    if item.get("id") is not None and px + canvas.text_width(f"ID {item['id']}", "label", 11, 1.6) + 24 <= text_right:
        canvas.pill(px, py, f"ID {item['id']}", outline=INK_FAINT, ink=INK_MUTED)

    canvas.line([(left, y0 + m["rule"]), (text_right, y0 + m["rule"])], PAGE_RULE, 1)
    column = (text_right - left) / 3
    bonus = float(item.get("progression_bonus_pct") or 0)
    figures = [
        ("Damage", number(weapon_damage(item)), f"base {number(item.get('base_damage', item.get('damage')))}" if bonus else "per strike"),
        ("Armor", number(weapon_armor(item)), f"base {number(item.get('base_armor', item.get('armor')))}" if bonus else "while held"),
    ]
    if bonus:
        figures.append(("Bonus", f"+{number(bonus * 100)}%", "forged and bound"))
    for index, (label, value, note) in enumerate(figures):
        stat(canvas, left + index * column, y0, m, column, label, value, note)

    y = y0 + 300
    stars = int(item.get("starforge_stars") or 0)
    soulbound = int(item.get("soulbound_level") or 0)
    if bonus or stars or soulbound:
        section(canvas, left, right, y, "Progression")
        canvas.star(left + 9, y + 29, 8.5, fill=GOLD if stars else None, outline=mix(GOLD_DEEP, (0, 0, 0), 0.2), width=1.2)
        canvas.text(left + 26, y + 35, f"Starforge {stars}" if stars else "Not starforged", "strong", 16.5, INK if stars else INK_MUTED)
        half = left + (right - left) / 2
        canvas.gem(half + 8, y + 29, 7.5, (188, 96, 255), lit=bool(soulbound))
        canvas.text(half + 26, y + 35, f"Soulbound rank {soulbound}" if soulbound else "Not soulbound", "strong", 16.5, INK if soulbound else INK_MUTED)
        y += 76
    if item.get("hand") == "both":
        canvas.diamond(left + 4, y - 6, 3.5, BRONZE_INK)
        canvas.text(left + 20, y, "This weapon fills both hands and is counted once.", "text", 16.5, INK_MUTED)


def _overview(canvas: Canvas, box, loadout: dict, hands: dict) -> None:
    """Everything worn, one row a piece."""
    m = FULL
    y0 = box[1]
    chest = loadout.get("chest")
    two_handed = hands["right"] is not None and hands["right"] is hands["left"]
    lead_key, lead = next(
        ((key, item) for key, item in (("right", hands["right"]), ("left", hands["left"]), ("chest", chest)) if item),
        ("right", None),
    )
    left, right, text_right = _page_head(
        canvas, box, lead_key, lead, "Everything worn", "Arms and Armor",
        glows=glow_colors(chest.get("modifiers")) if lead_key == "chest" and chest else (),
    )

    held = [item for item in (hands["right"], hands["left"]) if item is not None]
    if two_handed:
        weapons_label = "Two-handed"
    elif len(held) == 2:
        weapons_label = "Both hands full"
    elif len(held) == 1:
        weapons_label = "One hand free"
    else:
        weapons_label = "Unarmed"
    px, py = left, y0 + m["pills"]
    px += canvas.pill(px, py, weapons_label, fill=BRONZE_INK) + 8
    if chest:
        canvas.pill(px, py, f"{chest.get('rarity') or 'worn'} armor", fill=RARITY_INK.get(str(chest.get("rarity")), INK_MUTED))
    else:
        canvas.pill(px, py, "No armor", outline=INK_MUTED, ink=INK_MUTED)
    canvas.line([(left, y0 + m["rule"]), (text_right, y0 + m["rule"])], PAGE_RULE, 1)

    rows = []
    if two_handed:
        rows.append(("right", "Both hands", hands["right"]))
    else:
        rows.append(("right", "Right hand", hands["right"]))
        rows.append(("left", "Left hand", hands["left"]))
    rows.append(("chest", SLOT_NOUN["chest"], chest))

    y = y0 + 212
    height = 88
    for key, label, item in rows:
        row = (left, y, right, y + height)
        canvas.panel(row, 10, fill=(*BRONZE_INK, 36), outline=(*BRONZE_INK, 110), width=1)
        socket = (left + 10, y + 10, left + 10 + height - 20, y + height - 10)
        colors = glow_colors(item.get("modifiers")) if item and key == "chest" else []
        canvas.socket(socket, 9, border=RARITY_GEM.get(str(item.get("rarity")), GOLD_DEEP) if item and key == "chest" else None, border_width=1.2, glows=colors)
        slot_picture(canvas, key, item, (socket[0] + socket[2]) / 2, (socket[1] + socket[3]) / 2, (height - 20) * 0.84)
        tx = socket[2] + 16
        canvas.kicker(tx, y + 28, label, INK_MUTED, size=10.5, tracking=2.2)
        if item is None:
            canvas.text(tx, y + 55, "Empty", "strong", 19, INK_FAINT)
            canvas.text(tx, y + 75, "Nothing is worn here." if key == "chest" else "Nothing is held.", "text", 13.5, INK_FAINT)
        else:
            room = right - tx - 200
            canvas.text(tx, y + 55, canvas.fit(item.get("name") or "", "strong", 19, room), "strong", 19, INK)
            if key == "chest":
                numbers = piece_numbers(item)
                quality = int(item.get("quality") or 0)
                detail = "  ·  ".join(
                    part for part in (
                        str(item.get("rarity") or "").title(),
                        str(item.get("archetype") or "").title(),
                        f"{quality_band(quality)} {quality}",
                    ) if part
                )
                _row_numbers(canvas, right - 16, y, f"+{number(numbers['blessing'] * 100)}%", "blessing", f"+{number(numbers['ward'])}", "ward")
            else:
                detail = "  ·  ".join(
                    part for part in (
                        str(item.get("type") or "Weapon"),
                        "" if str(item.get("element") or "").lower() in ("", "none") else str(item.get("element")),
                        HAND_RULES.get(str(item.get("hand") or "any"), ""),
                    ) if part
                )
                _row_numbers(canvas, right - 16, y, number(weapon_damage(item)), "damage", number(weapon_armor(item)), "armor")
            canvas.text(tx, y + 75, canvas.fit(detail, "text", 13.5, room), "text", 13.5, INK_MUTED)
        y += height + 10

    if chest is None and y + 70 < box[3] - 40:
        y += 26
        canvas.diamond(left + 4, y - 6, 3.5, BRONZE_INK)
        for line in ("Helm, cuirass, greaves, and sabatons can all be worn.", "Wearing a piece does not bind it."):
            canvas.text(left + 20, y, line, "text", 16.5, INK_MUTED)
            y += 26


def _row_numbers(canvas: Canvas, right: float, y: float, first: str, first_label: str, second: str, second_label: str) -> None:
    """Two right-aligned figures at the end of an overview row."""
    canvas.figure(right, y + 48, second, 23, 84, anchor="rs")
    canvas.kicker(right, y + 67, second_label, INK_MUTED, size=9.5, anchor="rs", tracking=1.8)
    canvas.figure(right - 96, y + 48, first, 23, 84, anchor="rs")
    canvas.kicker(right - 96, y + 67, first_label, INK_MUTED, size=9.5, anchor="rs", tracking=1.8)

"""Pillow armory card.

A leather-bound chronicle: worn pieces sit in dark niches down the left, and
the open page beside them describes the selected piece. Enchantment glow is a color
list on the piece, so new modifiers only need a glow color.

Slot art is drawn in code. Dropping `<slot>_<rarity>.png` or `<slot>.png`
into assets/equipment replaces that drawing.
"""
from __future__ import annotations

from classes.equipment.attunement import ATTUNEMENT_CAP, refinement_cap
from classes.equipment.chronicle import (
    ARCHETYPE_TINT,
    ASTRAL,
    BRONZE_INK,
    PAGE_RULE,
    ELEMENT_TINT,
    INK,
    INK_FAINT,
    INK_MUTED,
    RARITY_GEM,
    RARITY_INK,
    STEEL,
    UNKNOWN_GLOW,
    Canvas,
    draw_header,
    header_stats,
    load_art,
    mix,
    number,
    weapon_glyph,
)
from classes.equipment.definitions import (
    MODIFIERS,
    OPEN_SLOTS,
    PAPER_DOLL_SLOTS,
    SLOT_NOUN,
    quality_band,
)
from classes.equipment.economy import is_tradable, modifier_adjustments

WIDTH = 1120
HEIGHT = 720
# The weapon row sits under the header. The page below it keeps the same height as the plain card.
_HAND_ROW = 108
_BODY_TOP = 178 + _HAND_ROW + 14
_BODY_SPAN = (HEIGHT - 42) - 178
ARMED_HEIGHT = _BODY_TOP + _BODY_SPAN + 42

HAND_NAMES = {"right": "Right hand", "left": "Left hand"}
HAND_RULES = {"any": "Either hand", "left": "Left hand", "right": "Right hand", "both": "Both hands"}

# Kept for callers that tint their embeds to match the card.
RARITY_COLOR = {rarity: (*color, 255) for rarity, color in RARITY_GEM.items()}
ARCHETYPE_COLOR = {archetype: (*color, 255) for archetype, color in ARCHETYPE_TINT.items()}

QUALITY_TICKS = (0.39, 0.69, 0.84, 0.94)
ATTUNEMENT_TICKS = (0.2, 0.4, 0.6, 0.8)

# Vertical positions inside the page, measured from its top edge.
FULL = {
    "pad": 34, "hero": 148, "kicker": 50, "name": 92, "name_size": 32, "pills": 108,
    "rule": 160, "stat_label": 188, "stat_value": 230, "stat_size": 36, "stat_note": 250,
    "gauges": (286, 334), "split": False, "ench": 388, "chips": (412, 452),
}
COMPACT = {
    "pad": 32, "hero": 116, "kicker": 46, "name": 84, "name_size": 28, "pills": 98,
    "rule": 142, "stat_label": 168, "stat_value": 204, "stat_size": 30, "stat_note": 222,
    "gauges": (252, 252), "split": True, "ench": 302, "chips": (326, 366),
}


def modifier_ids(item: dict | None) -> list[str]:
    ids = []
    for modifier in (item or {}).get("modifiers") or []:
        ids.append(str(modifier.get("modifier_id") if isinstance(modifier, dict) else modifier))
    return ids


def glow_colors(modifiers: list[dict] | None) -> list[tuple[int, int, int]]:
    """Colors used for enchantment bloom. Unknown ids still glow violet."""
    colors = []
    for modifier in modifiers or []:
        modifier_id = modifier.get("modifier_id") if isinstance(modifier, dict) else str(modifier)
        defined = MODIFIERS.get(str(modifier_id))
        colors.append(tuple(defined["glow"]) if defined else UNKNOWN_GLOW)
    return colors


def piece_numbers(item: dict | None) -> dict:
    """What the piece gives in battle: its own stats plus its enchantments."""
    item = item or {}
    base_blessing = float(item.get("offense_value") or 0)
    base_ward = float(item.get("defense_value") or 0)
    extra_weapon, extra_armor, health = modifier_adjustments(item.get("defense_value"), modifier_ids(item))
    return {
        "base_blessing": base_blessing,
        "base_ward": base_ward,
        "extra_blessing": float(extra_weapon),
        "extra_ward": float(extra_armor),
        "blessing": base_blessing + float(extra_weapon),
        "ward": base_ward + float(extra_armor),
        "health": int(health),
    }


def modifier_effect(modifier_id: str) -> str:
    """A short plain reading of one enchantment, built from its definition."""
    spec = MODIFIERS.get(str(modifier_id))
    if not spec:
        return ""
    parts = []
    if float(spec.get("weapon_pct") or 0):
        parts.append(f"+{number(float(spec['weapon_pct']) * 100)}% weapon damage")
    if float(spec.get("armor_pct") or 0):
        parts.append(f"+{number(float(spec['armor_pct']) * 100)}% ward")
    if int(spec.get("health") or 0):
        parts.append(f"+{int(spec['health'])} health")
    if float(spec.get("penetration") or 0):
        parts.append(f"pierces {number(float(spec['penetration']) * 100)}% armor")
    if float(spec.get("breakthrough_chance") or 0):
        parts.append(
            f"{number(float(spec['breakthrough_chance']) * 100)}% to pierce "
            f"{number(float(spec.get('breakthrough_bypass') or 0) * 100)}% more"
        )
    return ", ".join(parts)


def slot_picture(canvas: Canvas, key: str, item: dict | None, cx: float, cy: float, size: float) -> None:
    """The picture for one slot: your PNG when there is one, the drawn piece when there is not.

    Armor looks for `<slot>_<set>_<rarity>.png`, then `<slot>_<set>.png`, then
    `<slot>_<rarity>.png`, then `<slot>.png`. A weapon looks for
    `weapons/<type>.png`, then `weapon_<type>.png`. All under assets/equipment.
    """
    theme = canvas.t
    if key in PAPER_DOLL_SLOTS:
        names = []
        if item:
            archetype = str(item.get("archetype") or "").strip().lower()
            rarity = str(item.get("rarity") or "").strip().lower()
            if archetype and rarity:
                names.append(f"{key}_{archetype}_{rarity}.png")
            if archetype:
                names.append(f"{key}_{archetype}.png")
            if rarity:
                names.append(f"{key}_{rarity}.png")
        art = load_art(*names, f"{key}.png")
        if art is not None:
            canvas.art(art, cx, cy, size, dim=item is None)
        elif item:
            canvas.plate(key, cx, cy, size * 0.9, item.get("archetype"))
        else:
            canvas.icon(key, cx, cy, size * 0.9, theme.trim_deep if key == "chest" else theme.sketch, sketch=True)
        return
    if item is None:
        canvas.icon("shield" if key == "left" else "sword", cx, cy, size * 0.9, theme.trim_deep, sketch=True)
        return
    kind = str(item.get("type") or "").strip().lower()
    art = load_art(f"weapons/{kind}.png", f"weapon_{kind}.png") if kind else None
    if art is not None:
        canvas.art(art, cx, cy, size)
        return
    element = ELEMENT_TINT.get(str(item.get("element") or "").lower())
    canvas.icon(weapon_glyph(kind), cx, cy, size * 0.9, mix(STEEL, element, 0.45) if element else STEEL)


def render_armory(
    loadout: dict[str, dict] | None,
    *,
    title: str = "Armory",
    subtitle: str = "",
    theme=None,
    weapons: list[dict] | None = None,
    focus: str = "chest",
) -> bytes:
    """Render the paper doll. Unimplemented slots stay visible as sketches.

    Passing `weapons` adds the two hands above that doll and lets `focus`
    open the totals, the cuirass, or one hand on the same page.
    """
    if weapons is not None:
        return _render_armed(loadout, weapons, title=title, subtitle=subtitle, theme=theme, focus=focus)
    loadout = loadout or {}
    canvas = Canvas.tome(WIDTH, HEIGHT, theme)
    chest = loadout.get("chest")
    title_width = WIDTH - 116
    if chest:
        numbers = piece_numbers(chest)
        stats = [("Blessing", f"+{number(numbers['blessing'] * 100)}%"), ("Ward", f"+{number(numbers['ward'])}")]
        if numbers["health"]:
            stats.append(("Vitality", f"+{numbers['health']}"))
        header_stats(canvas, stats)
        title_width = 560 if len(stats) == 3 else 680
    draw_header(canvas, "The Chronicle of Arms", title, subtitle, title_width=title_width)

    top, bottom = 178, HEIGHT - 42
    gap = 12
    tile_height = (bottom - top - gap * (len(PAPER_DOLL_SLOTS) - 1)) / len(PAPER_DOLL_SLOTS)
    for index, slot in enumerate(PAPER_DOLL_SLOTS):
        y = top + index * (tile_height + gap)
        _draw_tile(canvas, slot, (48, y, 378, y + tile_height), loadout.get(slot), focus=slot == "chest" and bool(loadout.get(slot)))

    page = (400, top, WIDTH - 48, bottom)
    canvas.page(page)
    draw_piece_detail(canvas, page, chest, FULL)
    return canvas.png()


def _draw_tile(canvas: Canvas, slot: str, box, item: dict | None, *, focus: bool, label: str | None = None, detail: str | None = None) -> None:
    x0, y0, x1, y1 = box
    t = canvas.t
    weapon = detail is not None
    open_slot = slot in OPEN_SLOTS or weapon
    rarity = RARITY_GEM.get((item or {}).get("rarity"), t.trim)
    colors = glow_colors(item.get("modifiers")) if item else []
    canvas.shadow(box, 14, blur=8, dy=5, alpha=130)
    canvas.glow(box, 14, colors, blur=13, alpha=120)
    if item:
        canvas.panel(box, 14, gradient=t.tile_item, outline=mix(rarity, (0, 0, 0), 0.25), width=1.5)
    else:
        canvas.panel(box, 14, gradient=t.tile_empty, outline=t.trim_dim if open_slot else t.tile_edge, width=1.2)
    canvas.line([(x0 + 16, y0 + 2), (x1 - 16, y0 + 2)], (255, 236, 200, 26), 1)

    inset = 16
    side = (y1 - y0) - 2 * inset
    socket = (x0 + inset, y0 + inset, x0 + inset + side, y1 - inset)
    canvas.socket(socket, 12, border=rarity if item else t.trim_dim, glows=colors)
    slot_picture(canvas, slot, item, (socket[0] + socket[2]) / 2, (socket[1] + socket[3]) / 2, side * 0.84)

    tx = socket[2] + 16
    right = x1 - 16
    canvas.kicker(tx, y0 + 33, label or SLOT_NOUN[slot], t.kicker, size=11, tracking=2.4)
    if item and weapon:
        canvas.text(tx, y0 + 58, canvas.fit(item.get("name") or label or "Weapon", "strong", 17, right - tx), "strong", 17, t.ivory)
        canvas.text(tx, y0 + 82, canvas.fit(detail, "text", 14, right - tx), "text", 14, t.muted)
    elif item:
        rarity_label = str(item.get("rarity") or "").upper()
        width = canvas.kicker(right, y0 + 33, rarity_label, rarity, size=10.5, anchor="rs", tracking=1.8)
        canvas.gem(right - width - 10, y0 + 29, 4.5, rarity, dark=True)
        for line_index, line in enumerate(canvas.wrap(item.get("name") or SLOT_NOUN[slot], "strong", 17, right - tx)):
            canvas.text(tx, y0 + 58 + line_index * 21, line, "strong", 17, t.ivory)
        canvas.temper(
            tx, y1 - 18, item.get("refinement"), refinement_cap(item.get("attunement")),
            step=17, r=6.5, dark=True,
        )
    else:
        canvas.text(tx, y0 + 58, "Empty" if open_slot else "Not forged yet", "strong", 17, t.muted if open_slot else t.dim)
        if not weapon:
            canvas.temper(tx, y1 - 18, 0, 5, step=17, r=6.5, dark=True)
    if focus:
        mid = (y0 + y1) / 2
        canvas.poly([(x1 + 3, mid - 9), (x1 + 13, mid), (x1 + 3, mid + 9)], fill=t.trim)


def medallion(canvas: Canvas, cx: float, cy: float, diameter: float, *, glows=()) -> None:
    """The round medallion at the head of a page."""
    t = canvas.t
    r = diameter / 2
    box = (cx - r, cy - r, cx + r, cy + r)
    canvas.shadow(box, r, blur=9, dy=5, alpha=150)
    canvas.glow(box, r, glows, blur=12, alpha=150, grow=2)
    canvas.socket(box, r, border=t.trim_deep, border_width=1, glows=glows)
    canvas.circle(cx, cy, r + 1.5, outline=t.trim, width=3)
    canvas.circle(cx, cy, r + 5.5, outline=mix(t.trim_deep, (0, 0, 0), 0.2), width=1)
    canvas.circle(cx, cy, r - 6, outline=(*t.trim, 70), width=1)


def stat(canvas: Canvas, x: float, y0: float, m: dict, width: float, label: str, value: str, note: str, *, faint: bool = False) -> None:
    """Label, large figure, and a note beneath, in one column of the page."""
    canvas.kicker(x, y0 + m["stat_label"], label, INK_MUTED, size=10.5, tracking=2.2)
    canvas.figure(x, y0 + m["stat_value"], value, m["stat_size"], width - 12, INK_FAINT if faint else INK)
    canvas.text(x, y0 + m["stat_note"], canvas.fit(note, "text", 13, width - 8), "text", 13, INK_MUTED)


def _gauge(canvas: Canvas, x0: float, x1: float, y: float, label: str, reading: str, fraction: float, color, ticks) -> None:
    canvas.kicker(x0, y, label, INK_MUTED, size=10.5, tracking=2.2)
    canvas.text(x1, y, reading, "strong", 14.5, INK, anchor="rs")
    canvas.gauge((x0, y + 9, x1, y + 20), fraction, color, ticks)


def section(canvas: Canvas, x0: float, x1: float, y: float, label: str) -> None:
    """A small-capitals heading with a rule running to the margin."""
    width = canvas.kicker(x0, y, label, BRONZE_INK, size=11.5, tracking=2.8)
    canvas.line([(x0 + width + 14, y - 4), (x1 - 8, y - 4)], PAGE_RULE, 1)
    canvas.diamond(x1 - 3, y - 4, 3, BRONZE_INK)


def draw_piece_detail(canvas: Canvas, box, item: dict | None, m: dict = FULL, *, slot: str = "chest") -> None:
    """Describe one worn piece on a page. `m` picks the full or the compact spacing."""
    x0, y0, x1, y1 = box
    left, right = x0 + m["pad"], x1 - m["pad"]
    hero = m["hero"]
    hx, hy = right - hero / 2, y0 + m["pad"] + hero / 2
    text_right = right - hero - 26
    noun = SLOT_NOUN[slot]

    if item is None:
        medallion(canvas, hx, hy, hero)
        slot_picture(canvas, slot, None, hx, hy, hero * 0.68)
        canvas.kicker(left, y0 + m["kicker"], noun)
        canvas.text(left, y0 + m["name"], f"No {noun.lower()} worn", "display", m["name_size"], INK)
        canvas.line([(left, y0 + m["rule"] - 30), (text_right, y0 + m["rule"] - 30)], PAGE_RULE, 1)
        stanzas = [
            ("This slot is empty.", "Wearing a piece does not bind it."),
            ("Stars mark the temper of a piece, to five.", "An enchantment kindles behind the steel.", "An empty socket stays dark."),
        ]
        if m["split"]:
            stanzas = stanzas[1:]
        y = y0 + m["rule"] + 6
        for stanza in stanzas:
            canvas.diamond(left + 4, y - 6, 3.5, BRONZE_INK)
            for line in stanza:
                canvas.text(left + 20, y, line, "text", 17, INK_MUTED)
                y += 27
            y += 16
        return

    rarity_key = str(item.get("rarity") or "")
    archetype_key = str(item.get("archetype") or "")
    rarity_ink = RARITY_INK.get(rarity_key, INK_MUTED)
    colors = glow_colors(item.get("modifiers"))
    numbers = piece_numbers(item)
    refinement = int(item.get("refinement") or 0)
    attunement = int(item.get("attunement") or 0)
    cap = refinement_cap(attunement)
    quality = int(item.get("quality") or 0)

    # Medallion, with the temper stars beneath it.
    medallion(canvas, hx, hy, hero, glows=colors)
    slot_picture(canvas, slot, item, hx, hy, hero * 0.70)
    stars_y = y0 + m["pad"] + hero + (24 if not m["split"] else 20)
    canvas.temper(hx - Canvas.temper_width(step=19, r=7.5) / 2, stars_y, refinement, cap, step=19, r=7.5)
    caption = f"Tempered +{refinement} of {cap}" if refinement else f"Untempered · to +{cap}"
    canvas.kicker(hx, stars_y + 26, caption, INK_MUTED, size=10, anchor="ms", tracking=1.6)

    # Name and standing.
    canvas.kicker(left, y0 + m["kicker"], f"{noun}  ·  {archetype_key}" if archetype_key else noun)
    size = float(m["name_size"])
    name = str(item.get("name") or noun)
    while size > 22 and canvas.text_width(name, "display", size) > text_right - left:
        size -= 2
    canvas.text(left, y0 + m["name"], canvas.fit(name, "display", size, text_right - left), "display", size, INK)
    px, py = left, y0 + m["pills"]
    px += canvas.pill(px, py, rarity_key or "unknown", fill=rarity_ink) + 8
    if item.get("fully_rolled"):
        px += canvas.pill(px, py, "Bound discovery", fill=(150, 100, 20)) + 8
    elif not is_tradable(item):
        px += canvas.pill(px, py, "Bound", fill=(128, 40, 30)) + 8
    else:
        px += canvas.pill(px, py, "Tradable", outline=INK_MUTED, ink=INK_MUTED) + 8

    # What it gives in battle.
    canvas.line([(left, y0 + m["rule"]), (text_right, y0 + m["rule"])], PAGE_RULE, 1)
    column = (text_right - left) / 3
    blessing_note = "to weapon damage"
    if numbers["extra_blessing"]:
        blessing_note = f"{number(numbers['base_blessing'] * 100)}% base · +{number(numbers['extra_blessing'] * 100)}%"
    ward_note = "flat armor"
    if numbers["extra_ward"]:
        ward_note = f"{number(numbers['base_ward'])} base · +{number(numbers['extra_ward'])}"
    stat(canvas, left, y0, m, column, "Blessing", f"+{number(numbers['blessing'] * 100)}%", blessing_note)
    stat(canvas, left + column, y0, m, column, "Ward", f"+{number(numbers['ward'])}", ward_note)
    if numbers["health"]:
        stat(canvas, left + 2 * column, y0, m, column, "Vitality", f"+{numbers['health']}", "flat health")
    else:
        stat(canvas, left + 2 * column, y0, m, column, "Vitality", "–", "no enchantment", faint=True)

    # Quality and attunement.
    quality_reading = f"{quality_band(quality)} · {quality}"
    if attunement >= ATTUNEMENT_CAP:
        attunement_reading = "Fully attuned"
    else:
        attunement_reading = f"{attunement:,} / {ATTUNEMENT_CAP:,}"
    g1, g2 = m["gauges"]
    if m["split"]:
        half = (right - left - 28) / 2
        _gauge(canvas, left, left + half, y0 + g1, "Quality", quality_reading, quality / 100, rarity_ink, QUALITY_TICKS)
        _gauge(canvas, right - half, right, y0 + g2, "Attunement", attunement_reading, attunement / ATTUNEMENT_CAP, mix(ASTRAL, (20, 60, 120), 0.5), ATTUNEMENT_TICKS)
    else:
        _gauge(canvas, left, right, y0 + g1, "Quality", quality_reading, quality / 100, rarity_ink, QUALITY_TICKS)
        _gauge(canvas, left, right, y0 + g2, "Attunement", attunement_reading, attunement / ATTUNEMENT_CAP, mix(ASTRAL, (20, 60, 120), 0.5), ATTUNEMENT_TICKS)

    # Enchantments, two to a row.
    section(canvas, left, right, y0 + m["ench"], "Enchantments")
    ids = modifier_ids(item)
    first_row = y0 + m["chips"][0] + 4
    if not ids:
        canvas.gem(left + 8, first_row, 7.5, None, lit=False)
        canvas.text(left + 26, first_row + 6, "No enchantment yet. An empty socket stays dark.", "text", 15.5, INK_MUTED)
        return
    half = (right - left) / 2
    for index, modifier_id in enumerate(ids[:4]):
        defined = MODIFIERS.get(modifier_id, {})
        cx = left + (index % 2) * half
        cy = y0 + m["chips"][index // 2]
        canvas.gem(cx + 8, cy, 7.5, defined.get("glow", UNKNOWN_GLOW))
        label = defined.get("name", modifier_id.replace("_", " ").title())
        canvas.text(cx + 26, cy + 6, canvas.fit(label, "strong", 16, half - 40), "strong", 16, INK)
        effect = modifier_effect(modifier_id)
        if effect:
            canvas.text(cx + 26, cy + 24, canvas.fit(effect, "text", 13.5, half - 40), "text", 13.5, INK_MUTED)


def _weapon_detail_line(item: dict, slot: str) -> str:
    if slot == "left" and item.get("hand") == "both":
        return "Held in both hands"
    from classes.equipment.character_card import weapon_armor, weapon_damage

    return f"{number(weapon_damage(item))} damage  ·  {number(weapon_armor(item))} armor"


def _render_armed(loadout, weapons, *, title, subtitle, theme, focus) -> bytes:
    """The chronicle, with the two hands above the armor and one page open."""
    from classes.equipment.character_card import assign_hands, worn_totals

    loadout = loadout or {}
    hands = assign_hands(weapons)
    totals = worn_totals(loadout, weapons)
    canvas = Canvas.tome(WIDTH, ARMED_HEIGHT, theme)
    chest = loadout.get("chest")
    stats = [
        ("Damage", number(totals["weapon_damage"])),
        ("Armor", number(totals["weapon_armor"])),
        ("Blessing", f"+{number(totals['blessing'] * 100)}%"),
        ("Ward", f"+{number(totals['ward'])}"),
        ("Vitality", f"+{int(totals['health'])}"),
    ]
    stats_left = header_stats(canvas, stats, size=25, least=58, gap=17)
    draw_header(canvas, "The Chronicle of Arms", title, subtitle, title_width=max(220, stats_left - 58 - 30))

    row_top = 178
    gap = 36
    half = (WIDTH - 96 - gap) / 2
    for index, key in enumerate(("right", "left")):
        x = 48 + index * (half + gap)
        item = hands[key]
        detail = _weapon_detail_line(item, key) if item else ""
        _draw_tile(
            canvas, key, (x, row_top, x + half, row_top + _HAND_ROW), item,
            focus=focus == key, label=HAND_NAMES[key], detail=detail,
        )

    top = _BODY_TOP
    bottom = ARMED_HEIGHT - 42
    tile_gap = 12
    tile_height = (bottom - top - tile_gap * (len(PAPER_DOLL_SLOTS) - 1)) / len(PAPER_DOLL_SLOTS)
    for index, slot in enumerate(PAPER_DOLL_SLOTS):
        y = top + index * (tile_height + tile_gap)
        _draw_tile(canvas, slot, (48, y, 378, y + tile_height), loadout.get(slot), focus=focus == slot)

    page = (400, top, WIDTH - 48, bottom)
    canvas.page(page)
    if focus in HAND_NAMES:
        _draw_weapon_page(canvas, page, hands.get(focus), focus)
    elif focus in PAPER_DOLL_SLOTS:
        draw_piece_detail(canvas, page, loadout.get(focus), FULL, slot=focus)
    else:
        _draw_together(canvas, page, loadout, hands, totals)
    return canvas.png()


def _draw_weapon_page(canvas: Canvas, box, item: dict | None, key: str) -> None:
    """One held weapon, set in the same page as a piece of armor."""
    from classes.equipment.character_card import weapon_armor, weapon_damage

    m = FULL
    x0, y0, x1, _y1 = box
    left, right = x0 + m["pad"], x1 - m["pad"]
    hero = m["hero"]
    hx, hy = right - hero / 2, y0 + m["pad"] + hero / 2
    text_right = right - hero - 26
    noun = HAND_NAMES[key]
    medallion(canvas, hx, hy, hero)
    slot_picture(canvas, key, item, hx, hy, hero * 0.70)
    if item is None:
        canvas.kicker(left, y0 + m["kicker"], noun)
        canvas.text(left, y0 + m["name"], "Nothing is held", "display", m["name_size"], INK)
        canvas.line([(left, y0 + m["rule"] - 30), (text_right, y0 + m["rule"] - 30)], PAGE_RULE, 1)
        y = y0 + m["rule"] + 6
        for line in ("This hand is free for a weapon or a shield.", "A two-handed weapon fills both hands and is counted once."):
            canvas.diamond(left + 4, y - 6, 3.5, BRONZE_INK)
            canvas.text(left + 20, y, line, "text", 17, INK_MUTED)
            y += 36
        return

    kind = str(item.get("type") or "Weapon")
    canvas.kicker(left, y0 + m["kicker"], f"{noun}  ·  {kind}")
    size = float(m["name_size"])
    name = str(item.get("name") or kind)
    while size > 22 and canvas.text_width(name, "display", size) > text_right - left:
        size -= 2
    canvas.text(left, y0 + m["name"], canvas.fit(name, "display", size, text_right - left), "display", size, INK)
    px, py = left, y0 + m["pills"]
    px += canvas.pill(px, py, kind, fill=BRONZE_INK) + 8
    element = str(item.get("element") or "").strip()
    if element and element.lower() != "none":
        tint = ELEMENT_TINT.get(element.lower(), INK_MUTED)
        px += canvas.pill(px, py, element, outline=INK_MUTED, ink=INK_MUTED, dot=tint) + 8
    rule = HAND_RULES.get(str(item.get("hand") or "any"), "Either hand")
    canvas.pill(px, py, rule, outline=INK_MUTED, ink=INK_MUTED)

    canvas.line([(left, y0 + m["rule"]), (text_right, y0 + m["rule"])], PAGE_RULE, 1)
    column = (text_right - left) / 3
    bonus = float(item.get("progression_bonus_pct") or 0)
    stat(canvas, left, y0, m, column, "Damage", number(weapon_damage(item)), f"base {number(item.get('base_damage', item.get('damage')))}" if bonus else "per strike")
    stat(canvas, left + column, y0, m, column, "Armor", number(weapon_armor(item)), f"base {number(item.get('base_armor', item.get('armor')))}" if bonus else "while held")
    if bonus:
        stat(canvas, left + 2 * column, y0, m, column, "Bonus", f"+{number(bonus * 100)}%", "forged and bound")
    else:
        stat(canvas, left + 2 * column, y0, m, column, "Bonus", "–", "no starforge yet", faint=True)

    section(canvas, left, right, y0 + m["ench"], "Progression")
    y = y0 + m["chips"][0]
    stars = int(item.get("starforge_stars") or 0)
    soulbound = int(item.get("soulbound_level") or 0)
    canvas.temper(left, y + 8, stars, 10, base=10, top=10, step=16, r=6.5)
    canvas.text(left + Canvas.temper_width(top=10, step=16, r=6.5) + 12, y + 14, f"Starforge {stars}" if stars else "Not starforged", "strong", 16, INK if stars else INK_MUTED)
    canvas.text(left, y + 42, f"Soulbound rank {soulbound}" if soulbound else "Not soulbound", "text", 15.5, INK if soulbound else INK_MUTED)
    if item.get("hand") == "both":
        canvas.text(left, y + 70, "This weapon fills both hands and is counted once.", "text", 15.5, INK_MUTED)


def _draw_together(canvas: Canvas, box, loadout: dict, hands: dict, totals: dict) -> None:
    """Every worn weapon and the armor, on the chronicle page."""
    m = FULL
    x0, y0, x1, _y1 = box
    left, right = x0 + m["pad"], x1 - m["pad"]
    hero = m["hero"]
    chest = loadout.get("chest")
    lead_key, lead = next(
        ((key, item) for key, item in (("chest", chest), ("right", hands["right"]), ("left", hands["left"])) if item),
        ("chest", None),
    )
    hx, hy = right - hero / 2, y0 + m["pad"] + hero / 2
    text_right = right - hero - 26
    medallion(canvas, hx, hy, hero, glows=glow_colors(chest.get("modifiers")) if chest else ())
    slot_picture(canvas, lead_key, lead, hx, hy, hero * 0.70)
    canvas.kicker(left, y0 + m["kicker"], "Everything worn")
    canvas.text(left, y0 + m["name"], "Arms and Armor", "display", m["name_size"], INK)

    held = [item for item in (hands["right"], hands["left"]) if item is not None]
    two_handed = hands["right"] is not None and hands["right"] is hands["left"]
    if two_handed:
        hands_label = "Two-handed"
    elif len(held) == 2:
        hands_label = "Both hands full"
    elif len(held) == 1:
        hands_label = "One hand free"
    else:
        hands_label = "Unarmed"
    px, py = left, y0 + m["pills"]
    px += canvas.pill(px, py, hands_label, fill=BRONZE_INK) + 8
    if chest:
        canvas.pill(px, py, f"{chest.get('rarity') or 'worn'} armor", fill=RARITY_INK.get(str(chest.get("rarity")), INK_MUTED))
    else:
        canvas.pill(px, py, "No armor", outline=INK_MUTED, ink=INK_MUTED)

    canvas.line([(left, y0 + m["rule"]), (text_right, y0 + m["rule"])], PAGE_RULE, 1)
    column = (text_right - left) / 3
    stat(canvas, left, y0, m, column, "Damage", number(totals["weapon_damage"]), "weapons, once")
    stat(canvas, left + column, y0, m, column, "Armor", number(totals["weapon_armor"]), "weapons, once")
    stat(canvas, left + 2 * column, y0, m, column, "Blessing", f"+{number(totals['blessing'] * 100)}%", "from worn armor")

    section(canvas, left, right, y0 + m["ench"], "Carried")
    rows = []
    if two_handed:
        rows.append(("Both hands", hands["right"]))
    else:
        rows.append(("Right hand", hands["right"]))
        rows.append(("Left hand", hands["left"]))
    worn_names = [
        str(item.get("name"))
        for slot in PAPER_DOLL_SLOTS
        if (item := (loadout or {}).get(slot))
    ]
    rows.append(("Armor", {"name": ", ".join(worn_names)} if worn_names else None))
    y = y0 + m["chips"][0] + 4
    for label, item in rows:
        canvas.kicker(left, y, label, INK_MUTED, size=10.5, tracking=2.0)
        if item is None:
            canvas.text(right, y, "Empty", "strong", 16, INK_FAINT, anchor="rs")
        elif label == "Armor":
            canvas.text(left + 150, y, canvas.fit(str(item.get("name") or ""), "strong", 16, right - left - 320), "strong", 16, INK)
            canvas.text(right, y, f"+{number(totals['blessing'] * 100)}%  ·  +{number(totals['ward'])}", "strong", 16, INK, anchor="rs")
        else:
            from classes.equipment.character_card import weapon_armor, weapon_damage

            canvas.text(left + 150, y, canvas.fit(str(item.get("name") or ""), "strong", 16, right - left - 320), "strong", 16, INK)
            canvas.text(right, y, f"{number(weapon_damage(item))}  ·  {number(weapon_armor(item))}", "strong", 16, INK, anchor="rs")
        y += 32


def preview_loadout() -> dict[str, dict]:
    """Sample card: a refined glowing cuirass. The other slots are empty."""
    return {
        "chest": {
            "name": "Mythic Aegis Cuirass",
            "slot": "chest",
            "rarity": "legendary",
            "archetype": "guardian",
            "quality": 92,
            "refinement": 3,
            "offense_value": 0.036,
            "defense_value": 18.4,
            "bound": False,
            "fully_rolled": False,
            "modifiers": [
                {"modifier_id": "fortified"},
                {"modifier_id": "vitality"},
            ],
        }
    }

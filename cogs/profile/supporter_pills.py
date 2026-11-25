"""Supporter and Server Booster pills for the `$prpg` card.

Drawn next to the level rank pill, in the same rounded style. Nothing is
drawn for players who are neither a patron nor a booster.
"""
from __future__ import annotations

# Patreon tier number -> (name, short name, fill, outline). Matches the donation page.
SUPPORTER_TIERS = {
    1: ("Adventurer", "Adv.", (46, 125, 82, 238), (120, 214, 160, 255)),
    2: ("Warrior", "Warrior", (40, 86, 160, 238), (128, 176, 255, 255)),
    3: ("Hero", "Hero", (98, 52, 156, 238), (196, 150, 255, 255)),
    4: ("Legendary Hero", "Legend", (150, 104, 22, 242), (255, 214, 102, 255)),
}
BOOSTER = ("Booster", "Boost", (176, 58, 160, 238), (255, 140, 240, 255))
TEXT = (255, 250, 240, 255)
GAP = 12
PAD = 14
ICON = 18


def pills_for(status) -> list[dict]:
    """Pills to draw for {"tier", "booster"}. Empty means draw nothing."""
    status = status or {}
    pills = []
    try:
        tier = int(status.get("tier") or 0)
    except (TypeError, ValueError):
        tier = 0
    tier = min(tier, max(SUPPORTER_TIERS))
    if tier >= 1:
        name, short, fill, outline = SUPPORTER_TIERS[tier]
        pills.append({"kind": "tier", "label": name, "short": short, "fill": fill, "outline": outline})
    if status.get("booster"):
        name, short, fill, outline = BOOSTER
        pills.append({"kind": "booster", "label": name, "short": short, "fill": fill, "outline": outline})
    return pills


def _text_width(draw, text, font) -> int:
    box = draw.textbbox((0, 0), text, font=font)
    return int(box[2] - box[0])


def _pill_width(draw, text, font) -> int:
    return PAD + ICON + 8 + _text_width(draw, text, font) + PAD


def _draw_icon(draw, kind, cx, cy, color):
    """A boost gem for boosters, a four-point star for patron tiers. Drawn, no logo files."""
    r = ICON // 2
    if kind == "booster":
        # Faceted gem: flat top, point at the bottom.
        top = cy - r + 2
        points = [
            (cx - r, top + 4),
            (cx - r + 4, top),
            (cx + r - 4, top),
            (cx + r, top + 4),
            (cx, cy + r),
        ]
        draw.polygon(points, fill=color)
        draw.line([(cx - r, top + 4), (cx + r, top + 4)], fill=(255, 255, 255, 170), width=1)
        draw.line([(cx, top + 4), (cx, cy + r - 2)], fill=(255, 255, 255, 120), width=1)
    else:
        inner = max(2, r // 3)
        points = [
            (cx, cy - r),
            (cx + inner, cy - inner),
            (cx + r, cy),
            (cx + inner, cy + inner),
            (cx, cy + r),
            (cx - inner, cy + inner),
            (cx - r, cy),
            (cx - inner, cy - inner),
        ]
        draw.polygon(points, fill=color)


def layout(draw, pills, x, max_x, font) -> tuple[str, list[int]]:
    """Choose "full" or "short" labels so the pills fit before `max_x`.

    Returns the mode and the width of each pill. "none" means even short
    labels do not fit, so nothing is drawn rather than overlapping the card.
    """
    for mode in ("full", "short"):
        key = "label" if mode == "full" else "short"
        widths = [_pill_width(draw, pill[key], font) for pill in pills]
        total = sum(widths) + GAP * len(widths)
        if x + total <= max_x:
            return mode, widths
    return "none", []


def draw_supporter_pills(draw, pills, x, y, height, max_x, font, radius=16) -> int:
    """Draw the pills starting at `x`. Returns the width used (0 when nothing drew)."""
    if not pills:
        return 0
    mode, widths = layout(draw, pills, x + GAP, max_x, font)
    if mode == "none":
        return 0
    key = "label" if mode == "full" else "short"
    cursor = x + GAP
    for pill, w in zip(pills, widths):
        draw.rounded_rectangle(
            (cursor, y, cursor + w, y + height),
            radius=radius,
            fill=pill["fill"],
            outline=pill["outline"],
            width=2,
        )
        cy = y + height // 2
        _draw_icon(draw, pill["kind"], cursor + PAD + ICON // 2, cy, pill["outline"])
        text = pill[key]
        box = draw.textbbox((0, 0), text, font=font)
        text_h = box[3] - box[1]
        draw.text(
            (cursor + PAD + ICON + 8, cy - text_h // 2 - box[1]),
            text,
            font=font,
            fill=TEXT,
        )
        cursor += w + GAP
    return cursor - x

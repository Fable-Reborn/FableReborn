"""Deterministic Pillow cards for the Hunger Games region modes."""

from __future__ import annotations

import math
import random as stdlib_random
from functools import lru_cache
from io import BytesIO
from typing import Mapping, Sequence

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps


W, H = 1800, 1600
HEADER_H = 170
FOOTER_Y = 1360

FIELD = (43, 38, 28, 255)
FIELD_DARK = (27, 25, 20, 255)
PANEL = (40, 35, 27, 255)
PANEL_DEEP = (25, 23, 19, 255)
PARCHMENT = (222, 211, 180, 255)
PARCHMENT_DIM = (172, 162, 136, 255)
BRONZE = (171, 128, 57, 255)
GOLD = (216, 170, 60, 255)
MOSS = (80, 100, 55, 255)
RIVER = (72, 103, 111, 255)
MILL = (131, 86, 49, 255)
STONE = (126, 121, 108, 255)
TUNNEL = (90, 75, 93, 255)
TOXIC = (103, 124, 54, 255)
TOXIC_NEXT = (190, 149, 41, 255)
MUTTS = (130, 45, 38, 255)
MUTTS_NEXT = (173, 87, 38, 255)
DROP = (202, 155, 48, 255)
SEAL_RED = (150, 43, 34, 255)

REGIONS = (
    "Cornucopia",
    "Forest Ridge",
    "Riverbank",
    "Stone Quarry",
    "Underground Tunnels",
    "Ruined Mill",
)

REGION_COLOURS = {
    "Forest Ridge": MOSS,
    "Riverbank": RIVER,
    "Cornucopia": GOLD,
    "Ruined Mill": MILL,
    "Stone Quarry": STONE,
    "Underground Tunnels": TUNNEL,
}

REGION_ICONS = {
    "Forest Ridge": "tree",
    "Riverbank": "river",
    "Cornucopia": "horn",
    "Ruined Mill": "mill",
    "Stone Quarry": "quarry",
    "Underground Tunnels": "tunnel",
}

POSITIONS = {
    "Cornucopia": (650, 220, 1150, 480),
    "Forest Ridge": (70, 330, 540, 575),
    "Riverbank": (1260, 330, 1730, 575),
    "Stone Quarry": (70, 790, 540, 1035),
    "Underground Tunnels": (1260, 790, 1730, 1035),
    "Ruined Mill": (650, 905, 1150, 1165),
}

TRAIL_CURVES = {
    frozenset(("Cornucopia", "Forest Ridge")): ((705, 330), (620, 360), (570, 425), (490, 500)),
    frozenset(("Forest Ridge", "Stone Quarry")): ((335, 525), (270, 650), (270, 720), (335, 840)),
    frozenset(("Stone Quarry", "Ruined Mill")): ((490, 885), (575, 940), (620, 1010), (705, 1070)),
    frozenset(("Cornucopia", "Ruined Mill")): ((900, 425), (850, 635), (950, 760), (900, 960)),
    frozenset(("Cornucopia", "Riverbank")): ((1095, 330), (1180, 360), (1230, 425), (1310, 500)),
    frozenset(("Riverbank", "Underground Tunnels")): ((1465, 525), (1530, 650), (1530, 720), (1465, 840)),
    frozenset(("Underground Tunnels", "Ruined Mill")): ((1310, 885), (1225, 940), (1180, 1010), (1095, 1070)),
}

EVENT_STYLES = {
    "drop": (DROP, "drop"),
    "toxic": (TOXIC, "toxic"),
    "mutts": (MUTTS, "paw"),
    "wildfire": ((177, 78, 38, 255), "fire"),
    "mutt_migration": (MUTTS_NEXT, "paw"),
    "tracker_jackers": ((190, 149, 41, 255), "swarm"),
    "hazard": (TOXIC_NEXT, "warning"),
}


def _mix(base, accent, amount):
    return tuple(round(base[i] + (accent[i] - base[i]) * amount) for i in range(3)) + (255,)


@lru_cache(maxsize=128)
def _font(size: int, bold: bool = False):
    candidates = []
    if bold:
        candidates.extend((
            "C:/Windows/Fonts/arialbd.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        ))
    candidates.extend((
        "C:/Windows/Fonts/arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ))
    for path in candidates:
        try:
            return ImageFont.truetype(path, size=size)
        except OSError:
            continue
    return ImageFont.load_default()


@lru_cache(maxsize=64)
def _serif(size: int):
    candidates = (
        "C:/Windows/Fonts/georgiab.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf",
    )
    for path in candidates:
        try:
            return ImageFont.truetype(path, size=size)
        except OSError:
            continue
    return _font(size, bold=True)


def _fit_font(draw, text, max_width, start, minimum=12, serif=False):
    text = str(text)
    for size in range(start, minimum - 1, -2):
        candidate = _serif(size) if serif else _font(size, bold=True)
        bounds = draw.textbbox((0, 0), text, font=candidate)
        if bounds[2] - bounds[0] <= max_width:
            return candidate
    return _serif(minimum) if serif else _font(minimum, bold=True)


def _fit_text(draw, text, max_width, start, minimum=12, serif=False):
    text = str(text)
    font = _fit_font(draw, text, max_width, start, minimum, serif)
    if draw.textbbox((0, 0), text, font=font)[2] <= max_width:
        return text, font
    shortened = text
    while shortened:
        shortened = shortened[:-1].rstrip()
        candidate = f"{shortened}…"
        if draw.textbbox((0, 0), candidate, font=font)[2] <= max_width:
            return candidate, font
    return "…", font


def _draw_tracking(draw, xy, text, font, fill, tracking=3, anchor="la"):
    x, y = xy
    widths = [draw.textlength(char, font=font) for char in text]
    total = sum(widths) + max(0, len(text) - 1) * tracking
    if anchor.endswith("m"):
        x -= total / 2
    elif anchor.endswith("r"):
        x -= total
    for char, width in zip(text, widths):
        draw.text((x, y), char, font=font, fill=fill, anchor="lm")
        x += width + tracking


def _chamfer(box, cut=16):
    x1, y1, x2, y2 = box
    return [
        (x1 + cut, y1), (x2 - cut, y1), (x2, y1 + cut), (x2, y2 - cut),
        (x2 - cut, y2), (x1 + cut, y2), (x1, y2 - cut), (x1, y1 + cut),
    ]


def _draw_icon(draw, kind, center, size, colour):
    cx, cy = center
    width = max(2, round(size * 0.10))
    colour = tuple(colour)
    if kind == "tree":
        draw.polygon((cx, cy - size * .52, cx - size * .38, cy, cx + size * .38, cy), fill=colour)
        draw.polygon((cx, cy - size * .25, cx - size * .48, cy + size * .28, cx + size * .48, cy + size * .28), fill=colour)
        draw.rectangle((cx - size * .08, cy + size * .18, cx + size * .08, cy + size * .48), fill=colour)
    elif kind == "river":
        for offset in (-.22, 0, .22):
            points = []
            for index in range(7):
                x = cx - size * .48 + index * size * .16
                y = cy + size * offset + math.sin(index * math.pi / 2) * size * .08
                points.append((x, y))
            draw.line(points, fill=colour, width=width, joint="curve")
    elif kind == "horn":
        draw.arc((cx - size * .48, cy - size * .44, cx + size * .42, cy + size * .42), 95, 250, fill=colour, width=width + 1)
        draw.polygon((cx - size * .28, cy + size * .10, cx + size * .30, cy + size * .38, cx - size * .05, cy + size * .42), fill=colour)
    elif kind == "mill":
        draw.rectangle((cx - size * .18, cy - size * .12, cx + size * .18, cy + size * .46), fill=colour)
        draw.ellipse((cx - size * .18, cy - size * .28, cx + size * .18, cy + size * .08), fill=colour)
        for angle in (45, 135, 225, 315):
            dx = math.cos(math.radians(angle)) * size * .43
            dy = math.sin(math.radians(angle)) * size * .43
            draw.line((cx, cy - size * .10, cx + dx, cy - size * .10 + dy), fill=colour, width=width + 2)
    elif kind == "quarry":
        draw.polygon((cx - size * .50, cy + size * .34, cx - size * .24, cy - size * .35, cx, cy + size * .18), fill=colour)
        draw.polygon((cx - size * .06, cy + size * .30, cx + size * .20, cy - size * .30, cx + size * .50, cy + size * .34), fill=colour)
    elif kind == "tunnel":
        draw.arc((cx - size * .44, cy - size * .38, cx + size * .44, cy + size * .50), 180, 360, fill=colour, width=width + 3)
        draw.rectangle((cx - size * .44, cy, cx + size * .44, cy + size * .40), fill=colour)
        draw.rectangle((cx - size * .25, cy - size * .03, cx + size * .25, cy + size * .40), fill=PANEL)
    elif kind == "tribute":
        draw.ellipse((cx - size * .13, cy - size * .44, cx + size * .13, cy - size * .18), fill=colour)
        draw.polygon((cx - size * .34, cy + size * .38, cx - size * .23, cy - size * .10, cx + size * .23, cy - size * .10, cx + size * .34, cy + size * .38), fill=colour)
    elif kind == "toxic":
        radius = size * .12
        for ox, oy in ((0, -.22), (-.20, .14), (.20, .14)):
            draw.ellipse((cx + size * ox - radius, cy + size * oy - radius, cx + size * ox + radius, cy + size * oy + radius), outline=colour, width=width)
        draw.ellipse((cx - size * .08, cy - size * .08, cx + size * .08, cy + size * .08), fill=colour)
    elif kind == "paw":
        draw.ellipse((cx - size * .22, cy, cx + size * .22, cy + size * .34), fill=colour)
        for ox, oy in ((-.29, -.22), (-.1, -.34), (.12, -.34), (.3, -.2)):
            radius = size * .10
            draw.ellipse((cx + size * ox - radius, cy + size * oy - radius, cx + size * ox + radius, cy + size * oy + radius), fill=colour)
    elif kind == "drop":
        draw.arc((cx - size * .42, cy - size * .40, cx + size * .42, cy + size * .16), 180, 360, fill=colour, width=width)
        draw.line((cx - size * .40, cy - size * .10, cx - size * .20, cy + size * .20), fill=colour, width=width)
        draw.line((cx + size * .40, cy - size * .10, cx + size * .20, cy + size * .20), fill=colour, width=width)
        draw.rectangle((cx - size * .23, cy + size * .18, cx + size * .23, cy + size * .45), outline=colour, width=width)
    elif kind == "fire":
        draw.polygon((cx, cy - size * .48, cx - size * .32, cy, cx - size * .15, cy + size * .42, cx + size * .20, cy + size * .30, cx + size * .35, cy - size * .05), fill=colour)
    elif kind == "swarm":
        for ox, oy in ((-.24, -.14), (.08, -.24), (.26, .08), (-.08, .18)):
            draw.ellipse((cx + size * ox - 3, cy + size * oy - 3, cx + size * ox + 3, cy + size * oy + 3), fill=colour)
    elif kind == "warning":
        draw.polygon((cx, cy - size * .45, cx - size * .42, cy + size * .36, cx + size * .42, cy + size * .36), outline=colour, fill=None)
        draw.line((cx, cy - size * .18, cx, cy + size * .12), fill=colour, width=width)
        draw.ellipse((cx - width, cy + size * .22 - width, cx + width, cy + size * .22 + width), fill=colour)


def _apply_wash(canvas, center, radius, colour, alpha):
    mask = Image.new("L", canvas.size, 0)
    md = ImageDraw.Draw(mask)
    cx, cy = center
    rx, ry = radius
    md.ellipse((cx - rx, cy - ry, cx + rx, cy + ry), fill=alpha)
    mask = mask.filter(ImageFilter.GaussianBlur(min(rx, ry) // 3))
    layer = Image.new("RGBA", canvas.size, tuple(colour[:3]) + (0,))
    layer.putalpha(mask)
    canvas.alpha_composite(layer)


@lru_cache(maxsize=1)
def _background():
    canvas = Image.new("RGBA", (W, H), FIELD)
    draw = ImageDraw.Draw(canvas)
    rng = stdlib_random.Random(2026)
    noise = Image.new("L", (300, 267))
    noise.putdata([rng.randint(72, 178) for _ in range(300 * 267)])
    noise = noise.resize((W, H), Image.Resampling.BICUBIC).filter(ImageFilter.GaussianBlur(1.4))
    texture = ImageOps.colorize(noise, black=(25, 22, 16), white=(73, 65, 44)).convert("RGBA")
    texture.putalpha(95)
    canvas.alpha_composite(texture)

    _apply_wash(canvas, (900, 350), (430, 250), GOLD, 55)
    _apply_wash(canvas, (300, 455), (400, 330), MOSS, 92)
    _apply_wash(canvas, (1500, 455), (400, 330), RIVER, 76)
    _apply_wash(canvas, (300, 910), (420, 330), STONE, 58)
    _apply_wash(canvas, (1500, 910), (420, 330), TUNNEL, 70)
    _apply_wash(canvas, (900, 1040), (390, 260), MILL, 62)

    draw = ImageDraw.Draw(canvas)
    contour = _mix(FIELD, PARCHMENT, .13)
    for _ in range(22):
        cx, cy = rng.randint(-80, W + 80), rng.randint(190, 1300)
        rx, ry = rng.randint(100, 340), rng.randint(55, 190)
        for ring in range(rng.randint(1, 3)):
            inset = ring * 24
            if ry > inset:
                draw.ellipse((cx - rx + inset, cy - ry + inset, cx + rx - inset, cy + ry - inset), outline=contour, width=2)

    river_points = []
    for y in range(210, 1240, 18):
        x = 1620 + math.sin(y / 105) * 68
        river_points.append((round(x), y))
    draw.line(river_points, fill=_mix(FIELD_DARK, RIVER, .55), width=78, joint="curve")
    draw.line(river_points, fill=_mix(RIVER, PARCHMENT, .28), width=50, joint="curve")
    draw.line(river_points, fill=_mix(RIVER, PARCHMENT, .62), width=4, joint="curve")

    for _ in range(46):
        _draw_icon(draw, "tree", (rng.randint(70, 610), rng.randint(180, 690)), rng.randint(14, 28), _mix(FIELD, MOSS, rng.uniform(.52, .85)))
    for _ in range(26):
        x, y = rng.randint(30, 650), rng.randint(700, 1240)
        radius = rng.randint(12, 32)
        draw.polygon(((x - radius, y + radius), (x - radius // 2, y - radius), (x + radius, y - radius // 3), (x + radius // 2, y + radius)), fill=_mix(FIELD, STONE, rng.uniform(.35, .62)))

    _draw_icon(draw, "mill", (900, 790), 130, _mix(FIELD, MILL, .55))
    for x in (1320, 1440, 1560, 1680):
        draw.arc((x - 100, 890, x + 100, 1190), 180, 360, fill=_mix(FIELD, TUNNEL, .72), width=10)
    for radius in (170, 215, 260):
        draw.ellipse((900 - radius, 350 - radius, 900 + radius, 350 + radius), outline=_mix(FIELD, GOLD, .22), width=3)
    for angle in range(0, 360, 30):
        dx, dy = math.cos(math.radians(angle)) * 280, math.sin(math.radians(angle)) * 280
        draw.line((900, 350, 900 + dx, 350 + dy), fill=_mix(FIELD, GOLD, .14), width=2)

    mask = Image.new("L", canvas.size, 255)
    md = ImageDraw.Draw(mask)
    md.ellipse((-250, -180, W + 250, H + 180), fill=0)
    mask = mask.filter(ImageFilter.GaussianBlur(180)).point(lambda value: round(value * .7))
    vignette = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    vignette.putalpha(mask)
    canvas.alpha_composite(vignette)
    return canvas.convert("RGB")


def _cubic_curve(controls, steps=64):
    p0, p1, p2, p3 = controls
    points = []
    for index in range(steps + 1):
        t = index / steps
        mt = 1 - t
        x = mt ** 3 * p0[0] + 3 * mt ** 2 * t * p1[0] + 3 * mt * t ** 2 * p2[0] + t ** 3 * p3[0]
        y = mt ** 3 * p0[1] + 3 * mt ** 2 * t * p1[1] + 3 * mt * t ** 2 * p2[1] + t ** 3 * p3[1]
        points.append((round(x), round(y)))
    return points


def _draw_routes(canvas, current_region=None):
    draw = ImageDraw.Draw(canvas)
    for edge, controls in TRAIL_CURVES.items():
        points = _cubic_curve(controls)
        highlighted = bool(current_region and current_region in edge)
        trail = GOLD if highlighted else _mix(FIELD, PARCHMENT, .54)
        draw.line(points, fill=(20, 17, 12, 255), width=34 if highlighted else 30, joint="curve")
        draw.line(points, fill=_mix(FIELD_DARK, trail, .52), width=23 if highlighted else 20, joint="curve")
        draw.line(points, fill=trail, width=12 if highlighted else 10, joint="curve")
        marker = _mix(trail, PARCHMENT, .38)
        for index in range(7, len(points) - 5, 11):
            x, y = points[index]
            radius = 3 if highlighted else 2
            draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=marker)


def _draw_header(canvas, round_number, alive, personal):
    draw = ImageDraw.Draw(canvas)
    draw.rectangle((0, 0, W, HEADER_H), fill=(24, 21, 17, 255))
    draw.line((0, HEADER_H - 2, W, HEADER_H - 2), fill=BRONZE, width=3)
    _draw_tracking(draw, (42, 45), "FABLE REBORN", _font(18, True), GOLD, 4)
    draw.text((42, 82), "HUNGER GAMES · REGIONS", font=_font(24, True), fill=PARCHMENT)
    title = "YOUR ARENA MAP" if personal else "THE ARENA"
    draw.text((900, 68), title, font=_fit_font(draw, title, 620, 64, 30, True), fill=PARCHMENT, anchor="mm")
    _draw_tracking(draw, (900, 124), "ARENA FIELD REPORT", _font(15, True), PARCHMENT_DIM, 4, "mm")
    for x, label, value in ((1430, "ROUND", round_number), (1600, "ALIVE", alive)):
        draw.rounded_rectangle((x, 24, x + 145, 142), radius=8, fill=PANEL_DEEP, outline=BRONZE, width=2)
        draw.text((x + 72, 48), label, font=_font(15, True), fill=PARCHMENT_DIM, anchor="mm")
        value_text = str(value)
        draw.text((x + 72, 94), value_text, font=_fit_font(draw, value_text, 115, 48, 28, True), fill=GOLD, anchor="mm")


def _coerce_events(events):
    normalized = []
    for raw in events or ():
        event = dict(raw)
        event["kind"] = str(event.get("kind") or "hazard")
        event["label"] = str(event.get("label") or "ARENA EVENT").upper()
        event["timing"] = str(event.get("timing") or "ACTIVE").upper()
        normalized.append(event)
    if len(normalized) <= 3:
        return normalized
    hidden = len(normalized) - 2
    return normalized[:2] + [{"kind": "hazard", "label": f"+{hidden} MORE EVENTS", "timing": "DETAILS"}]


def _event_row_boxes(box, count):
    """Return non-overlapping row rectangles for one, two or three events."""
    if count <= 0:
        return []
    count = min(3, int(count))
    x1, y1, x2, y2 = box
    sx1, sx2 = x1 + 176, x2 - 22
    if count == 1:
        return [(sx1, y1 + 112, sx2, y1 + 178)]
    sy1, sy2 = y1 + 105, y2 - 18
    gap = 4
    row_height = (sy2 - sy1 - gap * (count - 1)) // count
    return [
        (sx1, sy1 + index * (row_height + gap), sx2, sy1 + index * (row_height + gap) + row_height)
        for index in range(count)
    ]


def _event_style(event):
    kind = str(event.get("kind") or "hazard")
    colour, icon = EVENT_STYLES.get(kind, EVENT_STYLES["hazard"])
    timing = str(event.get("timing") or "ACTIVE").upper()
    if timing == "NEXT":
        if kind == "mutts":
            colour = MUTTS_NEXT
        elif kind == "toxic":
            colour = TOXIC_NEXT
    return colour, icon


def _draw_events(draw, box, events):
    events = _coerce_events(events)
    if not events:
        x1, y1, x2, _ = box
        panel = (x1 + 176, y1 + 112, x2 - 22, y1 + 178)
        draw.rounded_rectangle(panel, radius=8, fill=_mix(PANEL, PARCHMENT, .06), outline=_mix(PANEL, PARCHMENT, .27), width=2)
        cx = (panel[0] + panel[2]) // 2
        draw.text((cx, panel[1] + 24), "NO ARENA EVENT", font=_font(18, True), fill=PARCHMENT_DIM, anchor="mm")
        draw.text((cx, panel[1] + 47), "REGION CLEAR", font=_font(11, True), fill=_mix(PANEL, PARCHMENT, .45), anchor="mm")
        return

    boxes = _event_row_boxes(box, len(events))
    for event, row in zip(events, boxes):
        colour, icon = _event_style(event)
        x1, y1, x2, y2 = row
        draw.rounded_rectangle(row, radius=6 if len(events) > 1 else 8, fill=_mix(PANEL, colour, .15), outline=colour, width=2 if len(events) > 1 else 3)
        cy = (y1 + y2) // 2
        icon_size = 19 if len(events) > 1 else 28
        icon_x = x1 + (22 if len(events) > 1 else 33)
        _draw_icon(draw, icon, (icon_x, cy), icon_size, colour)
        timing = str(event["timing"])
        timing_font = _font(10 if len(events) > 1 else 11, True)
        timing_width = round(draw.textlength(timing, font=timing_font)) + 18
        label_start = x1 + (42 if len(events) > 1 else 61)
        label_width = x2 - label_start - timing_width - 8
        label, label_font = _fit_text(draw, event["label"], label_width, 16 if len(events) > 1 else 20, 11)
        draw.text((label_start, cy), label, font=label_font, fill=_mix(PARCHMENT, colour, .15), anchor="lm")
        draw.text((x2 - 9, cy), timing, font=timing_font, fill=colour, anchor="rm")


def _draw_region_card(
    canvas,
    name,
    count,
    events,
    current_region=None,
    ally_region=None,
):
    box = POSITIONS[name]
    x1, y1, x2, y2 = box
    colour = REGION_COLOURS[name]
    points = _chamfer(box, 17)
    draw = ImageDraw.Draw(canvas)
    draw.polygon([(x + 10, y + 12) for x, y in points], fill=(12, 10, 8, 220))
    draw.polygon(points, fill=PANEL)
    draw.line(points + [points[0]], fill=_mix(PARCHMENT, colour, .38), width=4, joint="curve")
    inner = _chamfer((x1 + 8, y1 + 8, x2 - 8, y2 - 8), 11)
    draw.line(inner + [inner[0]], fill=_mix(PANEL, PARCHMENT, .2), width=2, joint="curve")
    draw.rectangle((x1 + 12, y1 + 14, x1 + 21, y2 - 14), fill=colour)

    _draw_icon(draw, REGION_ICONS[name], (x1 + 58, y1 + 49), 40, _mix(PARCHMENT, colour, .22))
    is_current = name == current_region
    is_ally = bool(ally_region and name == ally_region)
    location_marked = is_current or is_ally
    name_space = x2 - x1 - (245 if location_marked else 150)
    if name == "Underground Tunnels" and location_marked:
        split_font = _fit_font(draw, "UNDERGROUND", name_space, 23, 18, True)
        draw.text((x1 + 96, y1 + 38), "UNDERGROUND", font=split_font, fill=PARCHMENT, anchor="lm")
        draw.text((x1 + 96, y1 + 64), "TUNNELS", font=split_font, fill=PARCHMENT, anchor="lm")
    else:
        name_font = _fit_font(
            draw,
            name.upper(),
            name_space,
            34,
            16 if location_marked else 22,
            True,
        )
        draw.text((x1 + 96, y1 + 50), name.upper(), font=name_font, fill=PARCHMENT, anchor="lm")
    draw.line((x1 + 30, y1 + 88, x2 - 30, y1 + 88), fill=_mix(PANEL, colour, .68), width=2)

    _draw_icon(draw, "tribute", (x1 + 58, y1 + 144), 41, PARCHMENT)
    draw.text((x1 + 98, y1 + 136), str(count), font=_serif(45), fill=PARCHMENT, anchor="lm")
    draw.text((x1 + 99, y1 + 169), "TRIBUTE" if count == 1 else "TRIBUTES", font=_font(11, True), fill=PARCHMENT_DIM, anchor="lm")
    _draw_events(draw, box, events)

    if is_current and is_ally:
        marker = (x2 - 154, y1 + 20, x2 - 20, y1 + 78)
        draw.rounded_rectangle(
            marker,
            radius=12,
            fill=_mix(PANEL, GOLD, .18),
            outline=GOLD,
            width=3,
        )
        cx = (marker[0] + marker[2]) // 2
        draw.text(
            (cx, marker[1] + 22),
            "YOU + ALLY",
            font=_font(13, True),
            fill=PARCHMENT,
            anchor="mm",
        )
        draw.text(
            (cx, marker[1] + 43),
            "TOGETHER",
            font=_font(8, True),
            fill=GOLD,
            anchor="mm",
        )
    elif is_current or is_ally:
        cx, cy = x2 - 48, y1 + 49
        radius = 29
        accent = GOLD if is_current else RIVER
        fill = SEAL_RED if is_current else _mix(PANEL, RIVER, .36)
        draw.ellipse(
            (cx - radius, cy - radius, cx + radius, cy + radius),
            fill=fill,
            outline=accent,
            width=3,
        )
        draw.text(
            (cx, cy - 4),
            "YOU" if is_current else "ALLY",
            font=_font(14 if is_current else 11, True),
            fill=PARCHMENT,
            anchor="mm",
        )
        draw.text(
            (cx, cy + 13),
            "HERE",
            font=_font(8, True),
            fill=_mix(PARCHMENT, accent, .25),
            anchor="mm",
        )


def _draw_footer(canvas, personal):
    draw = ImageDraw.Draw(canvas)
    draw.rectangle((0, FOOTER_Y, W, H), fill=(24, 21, 17, 255))
    draw.line((0, FOOTER_Y, W, FOOTER_Y), fill=BRONZE, width=3)
    _draw_tracking(draw, (42, 1404), "ARENA LEGEND", _font(16, True), GOLD, 4)
    items = (
        ("tribute", "TRIBUTES", PARCHMENT),
        ("drop", "SPONSOR DROP", DROP),
        ("toxic", "TOXIC ACTIVE", TOXIC),
        ("toxic", "TOXIC NEXT", TOXIC_NEXT),
        ("paw", "MUTTS ACTIVE", MUTTS),
        ("paw", "MUTTS NEXT", MUTTS_NEXT),
    )
    x = 42
    for icon, label, colour in items:
        _draw_icon(draw, icon, (x + 20, 1476), 28, colour)
        draw.text((x + 45, 1476), label, font=_font(16, True), fill=colour, anchor="lm")
        x += round(draw.textlength(label, font=_font(16, True))) + 82
    note = (
        "YOUR LOCATION · ALLY LOCATION · LEGAL ROUTES"
        if personal
        else "PUBLIC MAP · REGION COUNTS AND ARENA EVENTS"
    )
    draw.text((1752, 1408), note, font=_fit_font(draw, note, 760, 17, 12), fill=PARCHMENT_DIM, anchor="ra")
    draw.text((900, 1555), "MOVE BETWEEN CONNECTED REGIONS · CLAIM DROPS · SURVIVE THE ARENA", font=_font(16, True), fill=_mix(FIELD, PARCHMENT, .52), anchor="mm")


def render_region_board(
    *,
    round_number: int,
    alive: int,
    region_counts: Mapping[str, int],
    events_by_region: Mapping[str, Sequence[Mapping]],
    adjacency: Mapping[str, Sequence[str]],
    current_region: str | None = None,
    ally_region: str | None = None,
):
    """Render a public or personal arena board to a seeked PNG BytesIO."""
    canvas = _background().convert("RGBA")
    _draw_header(canvas, round_number, alive, current_region is not None)
    _draw_routes(canvas, current_region)
    for name in REGIONS:
        _draw_region_card(
            canvas,
            name,
            max(0, int(region_counts.get(name, 0))),
            events_by_region.get(name, ()),
            current_region,
            ally_region,
        )
    _draw_footer(canvas, current_region is not None)
    output = BytesIO()
    canvas.convert("RGB").save(output, format="PNG", optimize=False)
    output.seek(0)
    return output


def _avatar_or_initial(avatar_bytes, size, initial, accent, grayscale=False):
    if avatar_bytes:
        try:
            with Image.open(BytesIO(avatar_bytes)) as avatar:
                avatar = avatar.convert("RGB")
                avatar = ImageOps.fit(avatar, (size, size), method=Image.Resampling.LANCZOS)
                if grayscale:
                    avatar = ImageOps.grayscale(avatar).convert("RGB")
                return avatar
        except (OSError, ValueError):
            pass
    fallback = Image.new("RGB", (size, size), _mix(FIELD, accent, .35)[:3])
    draw = ImageDraw.Draw(fallback)
    draw.text((size // 2, size // 2), initial[:1].upper() or "?", font=_serif(round(size * .58)), fill=PARCHMENT[:3], anchor="mm")
    return fallback


def _paste_round_avatar(canvas, center, radius, avatar_bytes, name, accent, grayscale=False):
    size = radius * 2
    avatar = _avatar_or_initial(avatar_bytes, size, name, accent, grayscale)
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, size - 1, size - 1), fill=255)
    canvas.paste(avatar, (center[0] - radius, center[1] - radius), mask)
    draw = ImageDraw.Draw(canvas)
    draw.ellipse((center[0] - radius - 7, center[1] - radius - 7, center[0] + radius + 7, center[1] + radius + 7), outline=accent, width=7)
    draw.ellipse((center[0] - radius, center[1] - radius, center[0] + radius, center[1] + radius), outline=PARCHMENT, width=3)


def _wrap(draw, text, font, max_width, max_lines=2):
    words = str(text).replace("**", "").split()
    lines = []
    current = []
    for word in words:
        candidate = " ".join(current + [word])
        if current and draw.textbbox((0, 0), candidate, font=font)[2] > max_width:
            lines.append(" ".join(current))
            current = [word]
            if len(lines) == max_lines:
                break
        else:
            current.append(word)
    if len(lines) < max_lines and current:
        lines.append(" ".join(current))
    if len(lines) == max_lines and len(" ".join(lines).split()) < len(words):
        lines[-1] = lines[-1].rstrip(".,") + "…"
    return lines


def render_fallen_card(
    *,
    victim_name: str,
    district: str,
    cause: str,
    killer_name: str,
    region: str,
    round_number: int,
    alive: int,
    fallen_index: int,
    fallen_total: int,
    avatar_bytes: bytes | None = None,
):
    width, height = 1600, 560
    canvas = Image.new("RGBA", (width, height), (50, 28, 24, 255))
    draw = ImageDraw.Draw(canvas)
    rng = stdlib_random.Random(14)
    for _ in range(180):
        x, y = rng.randrange(width), rng.randrange(height)
        draw.line((x, y, x + rng.randint(8, 40), y), fill=_mix((50, 28, 24), PARCHMENT, .08), width=1)
    draw.polygon(_chamfer((8, 8, width - 8, height - 8), 24), outline=MUTTS, fill=(48, 27, 24, 255))
    draw.rectangle((8, 38, 20, height - 38), fill=MUTTS)
    _paste_round_avatar(canvas, (225, 280), 174, avatar_bytes, victim_name, MUTTS, True)

    draw.rounded_rectangle((420, 52, 650, 100), radius=8, fill=_mix(PANEL, MUTTS, .17), outline=MUTTS, width=2)
    draw.text((535, 76), "CANNON FIRED", font=_font(20, True), fill=_mix(PARCHMENT, MUTTS, .22), anchor="mm")
    heading = f"{victim_name.upper()} HAS FALLEN"
    heading, heading_font = _fit_text(draw, heading, 800, 62, 30, True)
    draw.text((416, 132), heading, font=heading_font, fill=PARCHMENT)
    draw.line((416, 212, 1235, 212), fill=MUTTS, width=3)
    draw.text((418, 246), district.upper(), font=_font(24, True), fill=_mix(PARCHMENT, MUTTS, .26))
    draw.text((418, 304), "Felled by", font=_font(27), fill=PARCHMENT_DIM)
    killer, killer_font = _fit_text(draw, killer_name.upper(), 550, 28, 18)
    draw.text((568, 304), killer, font=killer_font, fill=PARCHMENT)
    cause_lines = _wrap(draw, cause, _font(18, True), 790, 2)
    for index, line in enumerate(cause_lines):
        draw.text((418, 355 + index * 24), line, font=_font(18, True), fill=PARCHMENT_DIM)
    draw.text((418, 410), f"{region.upper()} · ROUND {round_number}", font=_font(20, True), fill=PARCHMENT_DIM)
    draw.rounded_rectangle((416, 449, 870, 512), radius=9, fill=PANEL_DEEP, outline=MUTTS, width=2)
    draw.text((643, 480), f"{fallen_index} OF {fallen_total} FALLEN THIS ROUND", font=_font(21, True), fill=_mix(PARCHMENT, MUTTS, .16), anchor="mm")

    draw.rounded_rectangle((1280, 62, 1560, 498), radius=14, fill=PANEL_DEEP, outline=BRONZE, width=2)
    _draw_tracking(draw, (1420, 108), "ARENA STATUS", _font(15, True), GOLD, 2, "mm")
    draw.text((1420, 246), str(alive), font=_fit_font(draw, str(alive), 190, 116, 54, True), fill=PARCHMENT, anchor="mm")
    draw.text((1420, 326), "ALIVE", font=_serif(35), fill=GOLD, anchor="mm")
    shown = min(12, max(0, alive))
    columns = 4
    for index in range(shown):
        _draw_icon(draw, "tribute", (1335 + (index % columns) * 56, 390 + (index // columns) * 45), 28, GOLD)

    output = BytesIO()
    canvas.convert("RGB").save(output, format="PNG", optimize=False)
    output.seek(0)
    return output


def _draw_crown(draw, center_x, top_y, width, height, colour):
    half = width / 2
    peak_x = (-.42, -.21, 0, .21, .42)
    peak_y = (.24, .10, 0, .10, .24)
    points = [(center_x - half, top_y + height)]
    for index, (px, py) in enumerate(zip(peak_x, peak_y)):
        points.append((center_x + px * width, top_y + py * height))
        if index < 4:
            valley_x = (peak_x[index] + peak_x[index + 1]) / 2
            points.append((center_x + valley_x * width, top_y + height * .68))
    points.append((center_x + half, top_y + height))
    draw.polygon(points, fill=colour)
    draw.rectangle((center_x - half, top_y + height * .82, center_x + half, top_y + height + 16), fill=colour)
    for px, py in zip(peak_x, peak_y):
        x, y = center_x + px * width, top_y + py * height
        draw.ellipse((x - 6, y - 6, x + 6, y + 6), fill=PARCHMENT)


def render_victor_card(
    *,
    winner_name: str,
    district: str,
    eliminations: int,
    gear: str,
    outlasted: int,
    rounds_survived: int,
    started: int,
    avatar_bytes: bytes | None = None,
):
    width, height = 1600, 620
    canvas = Image.new("RGBA", (width, height), (38, 35, 23, 255))
    draw = ImageDraw.Draw(canvas)
    draw.polygon(_chamfer((8, 8, width - 8, height - 8), 26), fill=(38, 35, 23, 255), outline=GOLD)
    _paste_round_avatar(canvas, (230, 360), 160, avatar_bytes, winner_name, GOLD)
    _draw_crown(draw, 230, 48, 220, 105, GOLD)

    draw.rounded_rectangle((455, 52, 780, 103), radius=9, fill=_mix(PANEL, GOLD, .12), outline=GOLD, width=2)
    draw.text((617, 78), "VICTOR OF THE ARENA", font=_serif(22), fill=GOLD, anchor="mm")
    heading, heading_font = _fit_text(draw, winner_name.upper(), 820, 82, 38, True)
    draw.text((451, 136), heading, font=heading_font, fill=PARCHMENT)
    draw.line((453, 235, 1262, 235), fill=GOLD, width=3)
    stats = (("DISTRICT", district.replace("District", "").strip() or "?", 235), ("ELIMINATIONS", eliminations, 235), ("GEAR", gear.upper(), 290))
    sx = 453
    for label, value, box_width in stats:
        draw.rounded_rectangle((sx, 270, sx + box_width, 370), radius=10, fill=PANEL_DEEP, outline=BRONZE, width=2)
        draw.text((sx + 17, 290), label, font=_font(16, True), fill=PARCHMENT_DIM)
        value_text, value_font = _fit_text(draw, str(value), box_width - 34, 34, 18)
        draw.text((sx + 17, 326), value_text, font=value_font, fill=PARCHMENT)
        sx += box_width + 16
    stat_colour = _mix(PARCHMENT, GOLD, .2)
    draw.text((455, 430), str(outlasted), font=_serif(32), fill=stat_colour, anchor="lm")
    draw.text((500, 430), "TRIBUTES OUTLASTED", font=_serif(25), fill=stat_colour, anchor="lm")
    draw.text((455, 476), str(rounds_survived), font=_serif(32), fill=stat_colour, anchor="lm")
    draw.text((500, 479), "ROUNDS SURVIVED", font=_serif(25), fill=stat_colour, anchor="lm")
    _draw_tracking(draw, (455, 548), "THE ARENA REMEMBERS", _font(20, True), GOLD, 3)

    draw.rounded_rectangle((1310, 70, 1560, 550), radius=15, fill=PANEL_DEEP, outline=GOLD, width=3)
    _draw_icon(draw, "tribute", (1435, 182), 86, GOLD)
    draw.text((1435, 316), "#1", font=_serif(90), fill=PARCHMENT, anchor="mm")
    draw.text((1435, 390), "VICTOR", font=_serif(29), fill=GOLD, anchor="mm")
    draw.line((1352, 430, 1518, 430), fill=BRONZE, width=2)
    draw.text((1435, 474), f"{started} STARTED", font=_font(19, True), fill=PARCHMENT_DIM, anchor="mm")
    draw.text((1435, 510), "1 REMAINS", font=_font(19, True), fill=PARCHMENT, anchor="mm")

    output = BytesIO()
    canvas.convert("RGB").save(output, format="PNG", optimize=False)
    output.seek(0)
    return output


def render_district_victor_card(
    *,
    winners: Sequence[Mapping],
    district: str,
    outlasted: int,
    rounds_survived: int,
):
    """Render an equal two-tribute victory for the last surviving district."""
    winner_list = [dict(winner) for winner in winners]
    if len(winner_list) != 2:
        raise ValueError("A district victory card requires exactly two winners")

    width, height = 1800, 900
    canvas = Image.new("RGBA", (width, height), (38, 35, 23, 255))
    draw = ImageDraw.Draw(canvas)
    draw.polygon(
        _chamfer((8, 8, width - 8, height - 8), 26),
        fill=(38, 35, 23, 255),
        outline=GOLD,
    )

    draw.rounded_rectangle(
        (650, 46, 1150, 108),
        radius=9,
        fill=_mix(PANEL, GOLD, .12),
        outline=GOLD,
        width=2,
    )
    draw.text((900, 77), "DISTRICT VICTORY", font=_serif(27), fill=GOLD, anchor="mm")
    heading = str(district).upper()
    heading, heading_font = _fit_text(draw, heading, 900, 76, 42, True)
    draw.text((900, 172), heading, font=heading_font, fill=PARCHMENT, anchor="mm")
    draw.text((900, 235), "TWO VICTORS · ONE DISTRICT", font=_font(22, True), fill=GOLD, anchor="mm")
    draw.line((70, 278, 1730, 278), fill=GOLD, width=3)

    panel_specs = ((70, 250, 430), (940, 1120, 1300))
    for winner, (panel_x, avatar_x, content_x) in zip(winner_list, panel_specs):
        panel_box = (panel_x, 312, panel_x + 790, 688)
        draw.rounded_rectangle(
            panel_box,
            radius=14,
            fill=PANEL_DEEP,
            outline=BRONZE,
            width=3,
        )
        _draw_crown(draw, avatar_x, 325, 200, 48, GOLD)
        name = str(winner.get("name") or "Victor")
        _paste_round_avatar(
            canvas,
            (avatar_x, 530),
            130,
            winner.get("avatar_bytes"),
            name,
            GOLD,
        )
        name = str(winner.get("name") or "Victor").upper()
        name, name_font = _fit_text(draw, name, 390, 44, 22, True)
        draw.text((content_x, 365), name, font=name_font, fill=PARCHMENT)
        draw.rounded_rectangle(
            (content_x, 420, content_x + 180, 461),
            radius=8,
            fill=_mix(PANEL, GOLD, .12),
            outline=GOLD,
            width=2,
        )
        draw.text((content_x + 90, 441), "CO-VICTOR", font=_font(16, True), fill=GOLD, anchor="mm")
        eliminations = max(0, int(winner.get("eliminations") or 0))
        draw.rounded_rectangle(
            (content_x, 490, content_x + 380, 550),
            radius=9,
            fill=_mix(PANEL, GOLD, .05),
            outline=BRONZE,
            width=2,
        )
        draw.text(
            (content_x + 18, 520),
            f"{eliminations} ELIMINATION{'S' if eliminations != 1 else ''}",
            font=_font(20, True),
            fill=GOLD,
            anchor="lm",
        )
        draw.rounded_rectangle(
            (content_x, 570, content_x + 380, 630),
            radius=9,
            fill=_mix(PANEL, PARCHMENT, .04),
            outline=_mix(PANEL, PARCHMENT, .25),
            width=2,
        )
        gear = str(winner.get("gear") or "No gear").upper()
        gear, gear_font = _fit_text(draw, gear, 344, 19, 12)
        draw.text((content_x + 18, 600), gear, font=gear_font, fill=PARCHMENT_DIM, anchor="lm")

    stats_box = (70, 720, 1730, 840)
    draw.rounded_rectangle(stats_box, radius=13, fill=PANEL_DEEP, outline=GOLD, width=3)
    stats = (
        ("#1", "DISTRICT"),
        (str(outlasted), "TRIBUTES OUTLASTED"),
        (str(rounds_survived), "ROUNDS SURVIVED"),
    )
    segment_width = (stats_box[2] - stats_box[0]) // len(stats)
    for index, (value, label) in enumerate(stats):
        x1 = stats_box[0] + index * segment_width
        x2 = stats_box[0] + (index + 1) * segment_width
        if index:
            draw.line((x1, 742, x1, 818), fill=BRONZE, width=2)
        value, value_font = _fit_text(draw, value, segment_width - 40, 38, 24, True)
        draw.text(((x1 + x2) // 2, 760), value, font=value_font, fill=PARCHMENT, anchor="mm")
        draw.text(((x1 + x2) // 2, 809), label, font=_font(16, True), fill=GOLD, anchor="mm")

    _draw_tracking(draw, (900, 873), "THE DISTRICT STANDS TOGETHER", _font(18, True), GOLD, 4, "mm")

    output = BytesIO()
    canvas.convert("RGB").save(output, format="PNG", optimize=False)
    output.seek(0)
    return output

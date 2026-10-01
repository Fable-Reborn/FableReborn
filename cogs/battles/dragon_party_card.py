"""Procedurally drawn Ice Dragon party card.

Everything except the dragon artwork is drawn in code. The card is rendered at
``SS`` times its output size and downscaled once at the end, which gives every
shape, ring and bar clean anti-aliased edges. Data-independent layers (sky,
artwork, aurora, snow, frosted glass) are built once and cached.
"""

import math
import random
from decimal import Decimal
from functools import lru_cache
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps


PROJECT_ROOT = Path(__file__).resolve().parents[2]
ART_PATH = PROJECT_ROOT / "dragonbattle.png"
ART_CROP = (850, 0, 1672, 390)
FONT_DIR = PROJECT_ROOT / "assets" / "profile_themes" / "fonts"
DISPLAY_FONT_PATH = FONT_DIR / "Cinzel.ttf"
BODY_FONT_PATH = FONT_DIR / "Lato-Bold.ttf"
BODY_REGULAR_FONT_PATH = FONT_DIR / "Lato-Regular.ttf"

WIDTH, HEIGHT = 1600, 900
SS = 2

NIGHT = (4, 9, 20)
FROST = (238, 247, 255)
ICE = (127, 227, 255)
ICE_DEEP = (52, 132, 230)
MUTED = (146, 172, 200)
DIM = (82, 104, 132)
GOLD = (255, 207, 112)
GOLD_DEEP = (205, 132, 38)
VIOLET = (186, 160, 255)
ATK_COLOR = (255, 146, 118)
DEF_COLOR = ICE
HP_COLOR = (118, 236, 168)

BOSS_LEFT, BOSS_RIGHT = 56, 720
ART_SIZE = (986, 468)
TILE_BOXES = (
    (56, 288, 246, 352),
    (258, 288, 448, 352),
    (460, 288, 720, 352),
)
HEADER_Y = 392
CARD_TOP, CARD_BOTTOM = 434, 862
CARD_LEFT, CARD_RIGHT, CARD_GAP = 56, 1544, 20
CARD_WIDTH = (CARD_RIGHT - CARD_LEFT - CARD_GAP * 3) / 4
CARD_BOXES = tuple(
    (
        CARD_LEFT + i * (CARD_WIDTH + CARD_GAP),
        CARD_TOP,
        CARD_LEFT + i * (CARD_WIDTH + CARD_GAP) + CARD_WIDTH,
        CARD_BOTTOM,
    )
    for i in range(4)
)
ROMAN = ("I", "II", "III", "IV")
# Text-heavy regions where sharp foreground snowflakes would hurt legibility.
SNOW_FREE_ZONES = (
    (40, 30, 740, 420),
    (1080, 370, 1560, 416),
)


# ---------------------------------------------------------------------------
# Primitives
# ---------------------------------------------------------------------------


def _s(value):
    return int(round(value * SS))


def _box(x0, y0, x1, y1):
    return (_s(x0), _s(y0), _s(x1), _s(y1))


def _rgba(color, alpha):
    return (*color[:3], int(alpha))


def _num(value):
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _format_stat(value):
    return f"{Decimal(str(value)):,.0f}"


@lru_cache(maxsize=128)
def _font(size, display=False, weight="Bold"):
    """Return a font sized in logical pixels (scaled for supersampling)."""
    pixels = max(1, _s(size))
    if display and DISPLAY_FONT_PATH.exists():
        font = ImageFont.truetype(str(DISPLAY_FONT_PATH), size=pixels)
        try:
            font.set_variation_by_name(weight)
        except (OSError, ValueError):
            pass
        return font

    primary = BODY_REGULAR_FONT_PATH if weight == "Regular" else BODY_FONT_PATH
    candidates = (
        str(primary),
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "C:/Windows/Fonts/arialbd.ttf",
    )
    for path in candidates:
        try:
            return ImageFont.truetype(path, size=pixels)
        except OSError:
            continue
    return ImageFont.load_default(size=pixels)


def _text_width(draw, text, font):
    return draw.textlength(str(text), font=font) / SS


def _fit_text(draw, text, max_width, start_size, min_size, display=False, weight="Bold"):
    """Shrink text toward ``min_size`` and ellipsize if it still overflows."""
    text = str(text)
    for size in range(start_size, min_size - 1, -1):
        font = _font(size, display, weight)
        if _text_width(draw, text, font) <= max_width:
            return text, font

    font = _font(min_size, display, weight)
    suffix = "..."
    if _text_width(draw, suffix, font) > max_width:
        return "", font

    shortened = text
    while shortened:
        shortened = shortened[:-1].rstrip()
        candidate = f"{shortened}{suffix}"
        if _text_width(draw, candidate, font) <= max_width:
            return candidate, font
    return suffix, font


def _clean_name(value, fallback):
    """Drop characters the Latin display fonts cannot draw (emoji, CJK, ...)."""
    cleaned = "".join(ch for ch in str(value or "") if ord(ch) < 0x0250).strip()
    return " ".join(cleaned.split()) or fallback


def _ramp_mask(size, axis, stops):
    """L mask that eases between ``(position, value)`` stops along one axis."""
    width, height = size
    length = width if axis == "x" else height
    values = []
    for i in range(length):
        t = i / max(1, length - 1)
        if t <= stops[0][0]:
            values.append(stops[0][1])
            continue
        if t >= stops[-1][0]:
            values.append(stops[-1][1])
            continue
        for (p0, v0), (p1, v1) in zip(stops, stops[1:]):
            if p0 <= t <= p1:
                k = (t - p0) / max(1e-6, p1 - p0)
                k = k * k * (3 - 2 * k)
                values.append(int(v0 + (v1 - v0) * k))
                break
    strip = Image.new("L", (length, 1))
    strip.putdata(values)
    if axis == "x":
        return strip.resize((width, height), Image.NEAREST)
    return strip.transpose(Image.Transpose.ROTATE_270).resize((width, height), Image.NEAREST)


def _gradient(size, stops, axis="x"):
    """RGB image blending ``(position, color)`` stops along one axis."""
    width, height = size
    length = width if axis == "x" else height
    colors = []
    for i in range(length):
        t = i / max(1, length - 1)
        color = stops[-1][1]
        for (p0, c0), (p1, c1) in zip(stops, stops[1:]):
            if p0 <= t <= p1:
                k = (t - p0) / max(1e-6, p1 - p0)
                color = tuple(int(a + (b - a) * k) for a, b in zip(c0, c1))
                break
        if t < stops[0][0]:
            color = stops[0][1]
        colors.append(color[:3])
    strip = Image.new("RGB", (length, 1))
    strip.putdata(colors)
    if axis == "x":
        return strip.resize((width, height), Image.NEAREST)
    return strip.transpose(Image.Transpose.ROTATE_270).resize((width, height), Image.NEAREST)


def _rounded_mask(size, radius):
    mask = Image.new("L", size, 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        (0, 0, size[0] - 1, size[1] - 1), radius=radius, fill=255
    )
    return mask


def _glow(img, bounds, color, blur, paint):
    """Paint a shape into a padded mask, blur it and tint it onto ``img``.

    ``bounds`` is in canvas pixels; ``paint(draw, ox, oy)`` must subtract the
    offsets from every coordinate it draws.
    """
    left, top, right, bottom = (int(v) for v in bounds)
    pad = int(blur * 3)
    origin_x, origin_y = left - pad, top - pad
    mask = Image.new("L", (right - left + pad * 2, bottom - top + pad * 2), 0)
    paint(ImageDraw.Draw(mask), origin_x, origin_y)
    mask = mask.filter(ImageFilter.GaussianBlur(blur))
    img.paste(Image.new("RGB", mask.size, color[:3]), (origin_x, origin_y), mask)


def _glow_text(img, draw, xy, text, font, color, strength=200, blur=12, anchor="la"):
    x, y = _s(xy[0]), _s(xy[1])
    bounds = draw.textbbox((x, y), text, font=font, anchor=anchor)
    _glow(
        img,
        bounds,
        color,
        _s(blur),
        lambda d, ox, oy: d.text(
            (x - ox, y - oy), text, font=font, fill=strength, anchor=anchor,
            stroke_width=_s(2), stroke_fill=strength,
        ),
    )


def _gradient_text(img, draw, xy, text, font, top, bottom, anchor="la"):
    x, y = _s(xy[0]), _s(xy[1])
    left, upper, right, lower = draw.textbbox((x, y), text, font=font, anchor=anchor)
    if right <= left or lower <= upper:
        return
    mask = Image.new("L", (right - left, lower - upper), 0)
    ImageDraw.Draw(mask).text((x - left, y - upper), text, font=font, fill=255, anchor=anchor)
    fill = _gradient(mask.size, ((0.0, top), (1.0, bottom)), axis="y")
    img.paste(fill, (left, upper), mask)


def _tracked(draw, xy, text, font, fill, tracking, anchor="lm"):
    """Draw letter-spaced text; returns its logical width."""
    text = str(text)
    spacing = _s(tracking)
    width = sum(draw.textlength(ch, font=font) for ch in text) + spacing * max(0, len(text) - 1)
    x, y = _s(xy[0]), _s(xy[1])
    if anchor[0] == "m":
        x -= width / 2
    elif anchor[0] == "r":
        x -= width
    for ch in text:
        draw.text((x, y), ch, font=font, fill=fill, anchor="l" + anchor[1])
        x += draw.textlength(ch, font=font) + spacing
    return width / SS


def _fade_line(img, x0, y0, length, color, alpha, thickness=1.0, profile="center", vertical=False):
    span = max(2, _s(length))
    thick = max(1, _s(thickness))
    stops = {
        "center": ((0.0, 0), (0.5, alpha), (1.0, 0)),
        "left": ((0.0, alpha), (1.0, 0)),
        "right": ((0.0, 0), (1.0, alpha)),
    }[profile]
    mask = _ramp_mask((span, 1), "x", stops).resize((span, thick), Image.NEAREST)
    if vertical:
        mask = mask.transpose(Image.Transpose.ROTATE_270)
    img.paste(Image.new("RGB", mask.size, color[:3]), (_s(x0), _s(y0) - thick // 2), mask)


# ---------------------------------------------------------------------------
# Icons (centered on cx, cy; ``size`` is the half-extent in logical pixels)
# ---------------------------------------------------------------------------


def _poly(cx, cy, size, points, angle=0.0):
    cos_a, sin_a = math.cos(angle), math.sin(angle)
    return [
        (_s(cx + (x * cos_a - y * sin_a) * size), _s(cy + (x * sin_a + y * cos_a) * size))
        for x, y in points
    ]


def _icon_sword(draw, cx, cy, size, color):
    angle = math.radians(45)
    blade = ((-0.21, 0.2), (-0.21, -0.68), (0, -1.0), (0.21, -0.68), (0.21, 0.2))
    guard = ((-0.56, 0.18), (0.56, 0.18), (0.56, 0.38), (-0.56, 0.38))
    grip = ((-0.12, 0.38), (0.12, 0.38), (0.12, 0.74), (-0.12, 0.74))
    pommel = ((-0.22, 0.72), (0.22, 0.72), (0.22, 0.98), (-0.22, 0.98))
    for shape in (blade, guard, grip, pommel):
        draw.polygon(_poly(cx, cy, size, shape, angle), fill=color)


def _icon_shield(draw, cx, cy, size, color):
    outline = (
        (-0.82, -0.78), (0, -0.98), (0.82, -0.78), (0.78, 0.12),
        (0.45, 0.62), (0, 0.98), (-0.45, 0.62), (-0.78, 0.12),
    )
    draw.polygon(_poly(cx, cy, size, outline), fill=color)
    inner = ((0, -0.72), (0.56, -0.58), (0.52, 0.08), (0.28, 0.46), (0, 0.72))
    draw.polygon(_poly(cx, cy, size, inner), fill=_rgba(NIGHT, 70))


def _icon_heart(draw, cx, cy, size, color):
    r = 0.5 * size
    for ox in (-0.46, 0.46):
        x, y = cx + ox * size, cy - 0.28 * size
        draw.ellipse(_box(x - r, y - r, x + r, y + r), fill=color)
    draw.polygon(_poly(cx, cy, size, ((-0.94, -0.12), (0.94, -0.12), (0, 0.95))), fill=color)


def _icon_paw(draw, cx, cy, size, color):
    draw.ellipse(_box(cx - 0.52 * size, cy - 0.02 * size, cx + 0.52 * size, cy + 0.82 * size), fill=color)
    for ox, oy, r in ((-0.68, -0.18, 0.2), (-0.26, -0.62, 0.22), (0.26, -0.62, 0.22), (0.68, -0.18, 0.2)):
        x, y = cx + ox * size, cy + oy * size
        draw.ellipse(_box(x - r * size, y - r * size, x + r * size, y + r * size), fill=color)


def _icon_crown(draw, cx, cy, size, color):
    points = (
        (-0.95, 0.6), (-0.95, -0.5), (-0.48, 0.02), (0, -0.78),
        (0.48, 0.02), (0.95, -0.5), (0.95, 0.6),
    )
    draw.polygon(_poly(cx, cy, size, points), fill=color)


def _icon_diamond(draw, cx, cy, size, fill=None, outline=None, width=1.0):
    points = _poly(cx, cy, size, ((0, -1), (0.68, 0), (0, 1), (-0.68, 0)))
    draw.polygon(points, fill=fill, outline=outline, width=max(1, _s(width)) if outline else 0)


def _icon_snowflake(draw, cx, cy, size, color, width=1.6):
    line_width = max(1, _s(width))
    for k in range(3):
        angle = math.pi / 3 * k
        dx, dy = math.cos(angle) * size, math.sin(angle) * size
        draw.line((_s(cx - dx), _s(cy - dy), _s(cx + dx), _s(cy + dy)), fill=color, width=line_width)
        for sign in (-1, 1):
            bx, by = cx + sign * dx * 0.58, cy + sign * dy * 0.58
            for turn in (-0.6, 0.6):
                tip = angle + (0 if sign > 0 else math.pi) + turn
                ex, ey = bx + math.cos(tip) * size * 0.32, by + math.sin(tip) * size * 0.32
                draw.line((_s(bx), _s(by), _s(ex), _s(ey)), fill=color, width=line_width)


def _icon_claw(draw, cx, cy, size, color):
    for offset in (-0.55, 0, 0.55):
        points = ((-0.16 + offset, 0.9), (0.42 + offset, -0.95), (0.12 + offset, 0.9))
        draw.polygon(_poly(cx, cy, size, points, math.radians(12)), fill=color)


STAT_ICONS = {"atk": _icon_sword, "def": _icon_shield, "hp": _icon_heart}
STAT_COLORS = {"atk": ATK_COLOR, "def": DEF_COLOR, "hp": HP_COLOR}


# ---------------------------------------------------------------------------
# Static background (cached)
# ---------------------------------------------------------------------------


def _paint_radial(img, center, radii, color, alpha):
    rx, ry = _s(radii[0]), _s(radii[1])
    mask = ImageOps.invert(Image.radial_gradient("L")).resize((rx * 2, ry * 2), Image.BILINEAR)
    mask = mask.point(lambda v: int(alpha * (v / 255) ** 2.2))
    img.paste(Image.new("RGB", mask.size, color), (_s(center[0]) - rx, _s(center[1]) - ry), mask)


def _paint_hero_art(base):
    if not ART_PATH.exists():
        return
    with Image.open(ART_PATH) as source:
        art = source.convert("RGB").crop(ART_CROP)
    size = (_s(ART_SIZE[0]), _s(ART_SIZE[1]))
    art = art.resize(size, Image.LANCZOS)
    art = ImageEnhance.Contrast(art).enhance(1.12)
    art = Image.blend(art, Image.new("RGB", size, (14, 36, 84)), 0.14)
    mask = ImageChops.multiply(
        _ramp_mask(size, "x", ((0.0, 0), (0.34, 255))),
        _ramp_mask(size, "y", ((0.5, 255), (0.98, 0))),
    )
    base.paste(art, (_s(WIDTH) - size[0], 0), mask)


def _paint_aurora(base):
    small = (WIDTH // 4, HEIGHT // 4)
    bands = (
        ((70, 230, 205), 130, 64, 26, 0.0045, 0.4),
        ((120, 96, 255), 115, 104, 22, 0.006, 2.1),
        ((70, 170, 255), 90, 40, 30, 0.0035, 4.0),
    )
    for color, alpha, base_y, amplitude, frequency, phase in bands:
        mask = Image.new("L", small, 0)
        points = [
            (x / 4, (base_y + amplitude * math.sin(x * frequency + phase)
                     + amplitude * 0.4 * math.sin(x * frequency * 2.7 + phase * 1.3)) / 4)
            for x in range(-40, WIDTH + 40, 16)
        ]
        ImageDraw.Draw(mask).line(points, fill=alpha, width=9, joint="curve")
        mask = mask.filter(ImageFilter.GaussianBlur(7))
        mask = mask.resize((_s(WIDTH), _s(HEIGHT)), Image.BILINEAR)
        mask = ImageChops.multiply(
            mask, _ramp_mask(mask.size, "x", ((0.0, 255), (0.55, 200), (0.85, 60)))
        )
        base.paste(Image.new("RGB", mask.size, color), (0, 0), mask)


def _paint_snow(base, seed=1337):
    rng = random.Random(seed)
    bokeh = Image.new("L", (WIDTH // 2, HEIGHT // 2), 0)
    bokeh_draw = ImageDraw.Draw(bokeh)
    for _ in range(26):
        x, y = rng.uniform(0, WIDTH / 2), rng.uniform(0, HEIGHT / 2)
        r = rng.uniform(3, 9)
        bokeh_draw.ellipse((x - r, y - r, x + r, y + r), fill=rng.randint(30, 70))
    bokeh = bokeh.filter(ImageFilter.GaussianBlur(3)).resize((_s(WIDTH), _s(HEIGHT)), Image.BILINEAR)
    base.paste(Image.new("RGB", bokeh.size, (190, 225, 255)), (0, 0), bokeh)

    draw = ImageDraw.Draw(base, "RGBA")
    for _ in range(300):
        x, y = rng.uniform(0, WIDTH), rng.uniform(0, HEIGHT)
        r = rng.choice((0.7, 0.9, 1.1, 1.4, 1.8, 2.3))
        alpha = rng.randint(70, 220) if r > 1 else rng.randint(40, 140)
        if any(x0 <= x <= x1 and y0 <= y <= y1 for x0, y0, x1, y1 in SNOW_FREE_ZONES):
            continue
        draw.ellipse(_box(x - r, y - r, x + r, y + r), fill=(225, 240, 255, alpha))


def _frost_glass(base, box, radius, tint=(7, 16, 34), opacity=0.66):
    left, top, right, bottom = _box(*box)
    size = (right - left, bottom - top)
    region = base.crop((left, top, right, bottom)).filter(ImageFilter.GaussianBlur(_s(12)))
    region = Image.blend(region, Image.new("RGB", size, tint), opacity)
    sheen = _ramp_mask(size, "y", ((0.0, 34), (0.4, 6), (1.0, 0)))
    region.paste(Image.new("RGB", size, (190, 225, 255)), (0, 0), sheen)
    base.paste(region, (left, top), _rounded_mask(size, _s(radius)))


def _paint_vignette(base):
    mask = Image.radial_gradient("L").resize(base.size, Image.BILINEAR)
    mask = mask.point(lambda v: int(min(200, max(0, (v - 110) * 1.5))))
    base.paste(Image.new("RGB", base.size, (1, 3, 8)), (0, 0), mask)


def _paint_frame(base):
    draw = ImageDraw.Draw(base, "RGBA")
    inset = 14
    draw.rounded_rectangle(
        _box(inset, inset, WIDTH - inset, HEIGHT - inset),
        radius=_s(8),
        outline=(120, 180, 235, 60),
        width=_s(1),
    )
    for x, y, h_profile, v_profile in (
        (inset, inset, "left", "left"),
        (WIDTH - inset, inset, "right", "left"),
        (inset, HEIGHT - inset, "left", "right"),
        (WIDTH - inset, HEIGHT - inset, "right", "right"),
    ):
        hx = x if h_profile == "left" else x - 160
        vy = y if v_profile == "left" else y - 110
        _fade_line(base, hx, y, 160, ICE, 200, 1.4, h_profile)
        _fade_line(base, x, vy, 110, ICE, 200, 1.4, v_profile, vertical=True)
        _icon_diamond(draw, x, y, 7, fill=_rgba(NIGHT, 255), outline=_rgba(ICE, 230), width=1.2)
        _icon_diamond(draw, x, y, 2.6, fill=_rgba(FROST, 255))
    for y in (inset, HEIGHT - inset):
        _fade_line(base, WIDTH / 2 - 220, y, 440, ICE, 230, 1.4)
        _glow(
            base, _box(WIDTH / 2 - 14, y - 14, WIDTH / 2 + 14, y + 14), ICE, _s(6),
            lambda d, ox, oy, y=y: d.polygon(
                [(px - ox, py - oy) for px, py in _poly(WIDTH / 2, y, 11, ((0, -1), (0.68, 0), (0, 1), (-0.68, 0)))],
                fill=220,
            ),
        )
        _icon_diamond(draw, WIDTH / 2, y, 10, fill=_rgba(NIGHT, 255), outline=_rgba(ICE, 255), width=1.4)
        _icon_diamond(draw, WIDTH / 2, y, 4, fill=_rgba(FROST, 255))


@lru_cache(maxsize=1)
def _static_base():
    """Build the data-independent backdrop once; renders draw on a copy."""
    size = (_s(WIDTH), _s(HEIGHT))
    base = _gradient(size, ((0.0, (12, 27, 56)), (0.5, (6, 14, 31)), (1.0, (2, 5, 12))), axis="y")
    _paint_radial(base, (1180, 200), (760, 440), (38, 104, 200), 120)
    _paint_hero_art(base)
    _paint_aurora(base)
    scrim = _ramp_mask(size, "x", ((0.0, 210), (0.3, 150), (0.5, 0)))
    scrim = ImageChops.multiply(scrim, _ramp_mask(size, "y", ((0.0, 255), (0.44, 255), (0.52, 90))))
    base.paste(Image.new("RGB", size, NIGHT), (0, 0), scrim)
    _paint_radial(base, (800, 930), (980, 300), (26, 84, 168), 80)
    _paint_snow(base)
    for box in CARD_BOXES:
        _frost_glass(base, box, 18)
    for box in TILE_BOXES:
        _frost_glass(base, box, 14, opacity=0.6)
    _paint_vignette(base)
    _paint_frame(base)
    return base


# ---------------------------------------------------------------------------
# Components
# ---------------------------------------------------------------------------


def _chip_width(draw, text, font, icon):
    return _text_width(draw, text, font) + 28 + (20 if icon else 0)


def _chip(draw, x, cy, text, font, color, icon=None, height=30):
    width = _chip_width(draw, text, font, icon)
    draw.rounded_rectangle(
        _box(x, cy - height / 2, x + width, cy + height / 2),
        radius=_s(height / 2),
        fill=_rgba(color, 26),
        outline=_rgba(color, 150),
        width=_s(1),
    )
    text_x = x + 14
    if icon:
        icon(draw, x + 20, cy, 7, _rgba(color, 255))
        text_x += 20
    draw.text((_s(text_x), _s(cy)), text, font=font, fill=_rgba(color, 255), anchor="lm")
    return width


def _bar(img, draw, box, ratio, stops, radius, glow_color=None, ticks=0):
    left, top, right, bottom = _box(*box)
    corner = _s(radius)
    fill_width = int((right - left) * max(0.0, min(1.0, ratio)))
    if glow_color and fill_width > 0:
        _glow(
            img, (left, top, left + fill_width, bottom), glow_color, _s(7),
            lambda d, ox, oy: d.rounded_rectangle(
                (left - ox, top - oy, left + fill_width - ox, bottom - oy), radius=corner, fill=150
            ),
        )
    draw.rounded_rectangle((left, top, right, bottom), radius=corner, fill=(200, 225, 255, 20))
    if fill_width > 0:
        height = bottom - top
        fill = _gradient((right - left, height), stops).crop((0, 0, fill_width, height))
        gloss = _ramp_mask(fill.size, "y", ((0.0, 90), (0.45, 18), (1.0, 0)))
        fill.paste(Image.new("RGB", fill.size, (255, 255, 255)), (0, 0), gloss)
        img.paste(fill, (left, top), _rounded_mask(fill.size, corner))
    for i in range(1, ticks):
        x = left + (right - left) * i / ticks
        draw.line((x, top + _s(3), x, bottom - _s(3)), fill=(3, 10, 26, 120), width=_s(1))


def _icon_badge(draw, cx, cy, radius, icon, color, icon_size):
    draw.ellipse(
        _box(cx - radius, cy - radius, cx + radius, cy + radius),
        fill=_rgba(color, 30),
        outline=_rgba(color, 170),
        width=_s(1.2),
    )
    icon(draw, cx, cy, icon_size, _rgba(color, 255))


def _signature_move(moves):
    best_name, best_damage = None, -1
    if isinstance(moves, dict):
        for name, info in moves.items():
            damage = _num(info.get("dmg")) if isinstance(info, dict) else 0
            if damage > best_damage:
                best_name, best_damage = name, damage
    return best_name, max(0, best_damage)


def _draw_boss(img, draw, dragon):
    x, right = BOSS_LEFT, BOSS_RIGHT

    _icon_diamond(draw, x + 5, 52, 6, fill=_rgba(ICE, 255))
    kicker_width = _tracked(draw, (x + 20, 52), "ICE DRAGON CHALLENGE", _font(14), _rgba(ICE, 255), 3.6)
    _fade_line(img, x + 34 + kicker_width, 52, 180, ICE, 140, 1.2, "left")

    name = _clean_name(dragon.get("name"), "Ice Dragon").upper()
    name, name_font = _fit_text(draw, name, right - x, 74, 36, display=True, weight="Black")
    _glow_text(img, draw, (x, 112), name, name_font, (40, 140, 255), 170, blur=16, anchor="lm")
    _gradient_text(img, draw, (x, 112), name, name_font, (255, 255, 255), (150, 214, 255), anchor="lm")

    cy = 172
    level_text = f"LV {int(_num(dragon.get('level', 1)))}"
    level_font = _font(17)
    badge_width = _text_width(draw, level_text, level_font) + 38
    hexagon = [
        (_s(px), _s(py))
        for px, py in (
            (x, cy), (x + 12, cy - 15), (x + badge_width - 12, cy - 15),
            (x + badge_width, cy), (x + badge_width - 12, cy + 15), (x + 12, cy + 15),
        )
    ]
    _glow(
        img, _box(x, cy - 15, x + badge_width, cy + 15), ICE, _s(8),
        lambda d, ox, oy: d.polygon([(px - ox, py - oy) for px, py in hexagon], fill=170),
    )
    hex_fill = _gradient((_s(badge_width), _s(30)), ((0.0, (190, 242, 255)), (1.0, ICE_DEEP)))
    hex_mask = Image.new("L", hex_fill.size, 0)
    ImageDraw.Draw(hex_mask).polygon([(px - _s(x), py - _s(cy - 15)) for px, py in hexagon], fill=255)
    img.paste(hex_fill, (_s(x), _s(cy - 15)), hex_mask)
    draw.text((_s(x + badge_width / 2), _s(cy)), level_text, font=level_font, fill=_rgba(NIGHT, 255), anchor="mm")

    chip_font = _font(13)
    cursor = x + badge_width + 12
    element = _clean_name(dragon.get("element"), "Water").upper()
    cursor += _chip(draw, cursor, cy, element, chip_font, ICE, icon=_icon_snowflake) + 10

    passives = [
        _clean_name(p, "").upper()
        for p in (dragon.get("passives") or [])
        if isinstance(p, str) and _clean_name(p, "")
    ]
    for index, passive in enumerate(passives):
        remaining = len(passives) - index - 1
        reserve = _chip_width(draw, f"+{remaining}", chip_font, None) + 10 if remaining else 0
        if cursor + _chip_width(draw, passive, chip_font, None) + reserve > right:
            _chip(draw, cursor, cy, f"+{remaining + 1}", chip_font, VIOLET)
            break
        cursor += _chip(draw, cursor, cy, passive, chip_font, VIOLET) + 10

    hp = _num(dragon.get("hp", 0))
    _icon_heart(draw, x + 8, 218, 8, _rgba(ICE, 255))
    _tracked(draw, (x + 26, 218), "HEALTH", _font(13), _rgba(MUTED, 255), 3.2)
    hp_text, hp_font = _fit_text(draw, _format_stat(hp), 300, 28, 18)
    draw.text((_s(right), _s(228)), hp_text, font=hp_font, fill=_rgba(FROST, 255), anchor="rs")
    _bar(
        img, draw, (x, 238, right, 266), 1.0,
        ((0.0, (98, 70, 230)), (0.5, (64, 170, 255)), (0.88, (150, 236, 255)), (1.0, (236, 252, 255))),
        radius=7, glow_color=(70, 160, 255), ticks=10,
    )

    for box, key, label in (
        (TILE_BOXES[0], "atk", "ATTACK"),
        (TILE_BOXES[1], "def", "DEFENSE"),
    ):
        value = dragon.get("damage" if key == "atk" else "armor", 0)
        left, top, tile_right, bottom = box
        mid = (top + bottom) / 2
        draw.rounded_rectangle(_box(*box), radius=_s(14), outline=(150, 205, 255, 50), width=_s(1))
        _icon_badge(draw, left + 34, mid, 19, STAT_ICONS[key], STAT_COLORS[key], 10)
        _tracked(draw, (left + 64, top + 21), label, _font(11), _rgba(MUTED, 255), 2.6)
        text, font = _fit_text(draw, _format_stat(value), tile_right - left - 80, 25, 15)
        draw.text((_s(left + 64), _s(top + 46)), text, font=font, fill=_rgba(FROST, 255), anchor="lm")

    left, top, tile_right, bottom = TILE_BOXES[2]
    mid = (top + bottom) / 2
    draw.rounded_rectangle(_box(*TILE_BOXES[2]), radius=_s(14), outline=(150, 205, 255, 50), width=_s(1))
    _icon_badge(draw, left + 34, mid, 19, _icon_claw, VIOLET, 10)
    _tracked(draw, (left + 64, top + 21), "SIGNATURE MOVE", _font(11), _rgba(MUTED, 255), 2.6)
    move_name, move_damage = _signature_move(dragon.get("moves"))
    damage_width = 0
    if move_name:
        damage_text = _format_stat(move_damage)
        damage_font = _font(18)
        damage_width = _text_width(draw, damage_text, damage_font)
        draw.text(
            (_s(tile_right - 16), _s(top + 46)), damage_text,
            font=damage_font, fill=_rgba(VIOLET, 255), anchor="rm",
        )
        _tracked(draw, (tile_right - 16, top + 21), "DMG", _font(10), _rgba(MUTED, 255), 2.4, anchor="rm")
    move_text, move_font = _fit_text(
        draw,
        _clean_name(move_name, "Unknown"),
        tile_right - left - 64 - 16 - damage_width - 12,
        19, 12, display=True, weight="Bold",
    )
    draw.text((_s(left + 64), _s(top + 46)), move_text, font=move_font, fill=_rgba(FROST, 255), anchor="lm")


def _party_totals(party):
    totals = {"atk": 0.0, "def": 0.0, "hp": 0.0}
    for member in party:
        for source in (member, member.get("pet") or {}):
            totals["atk"] += _num(source.get("attack"))
            totals["def"] += _num(source.get("defense"))
            totals["hp"] += _num(source.get("hp"))
    return totals


def _draw_party_header(img, draw, party):
    y = HEADER_Y
    title_font = _font(25, display=True, weight="Black")
    title = "THE HUNTING PARTY"
    _gradient_text(img, draw, (CARD_LEFT, y), title, title_font, (255, 255, 255), (160, 214, 255), anchor="lm")
    cursor = CARD_LEFT + _text_width(draw, title, title_font) + 24

    for index in range(4):
        cx = cursor + index * 22
        if index < len(party):
            _glow(
                img, _box(cx - 8, y - 9, cx + 8, y + 9), ICE, _s(5),
                lambda d, ox, oy, cx=cx: d.ellipse(
                    (_s(cx - 6) - ox, _s(y - 6) - oy, _s(cx + 6) - ox, _s(y + 6) - oy), fill=200
                ),
            )
            _icon_diamond(draw, cx, y, 8, fill=_rgba(ICE, 255))
        else:
            _icon_diamond(draw, cx, y, 8, outline=_rgba(DIM, 255), width=1.2)
    cursor += 4 * 22 + 4
    ready_color = ICE if party else MUTED
    _tracked(draw, (cursor, y), f"{len(party)}/4 READY", _font(13), _rgba(ready_color, 255), 2.6)

    totals = _party_totals(party)
    value_font = _font(18)
    x = CARD_RIGHT
    for key in ("hp", "def", "atk"):
        text = _format_stat(totals[key])
        draw.text((_s(x), _s(y)), text, font=value_font, fill=_rgba(FROST, 255), anchor="rm")
        x -= _text_width(draw, text, value_font) + 10
        STAT_ICONS[key](draw, x - 7, y, 8, _rgba(STAT_COLORS[key], 255))
        x -= 14 + 24
    _tracked(draw, (x + 8, y), "PARTY POWER", _font(11), _rgba(MUTED, 255), 2.8, anchor="rm")

    _fade_line(img, CARD_LEFT, y + 24, CARD_RIGHT - CARD_LEFT, ICE, 120, 1.2, "left")


def _decode_avatar(data, diameter):
    if not data:
        return None
    try:
        with Image.open(BytesIO(data)) as source:
            source.seek(0)
            return ImageOps.fit(source.convert("RGBA"), (diameter, diameter), Image.LANCZOS)
    except Exception:
        return None


def _monogram(name, diameter, accent):
    shade = ImageOps.invert(Image.radial_gradient("L")).resize((diameter, diameter), Image.BILINEAR)
    avatar = ImageOps.colorize(ImageOps.invert(shade), black=accent, white=(10, 24, 52), mid=ICE_DEEP)
    letter = next((ch for ch in name if ch.isalnum()), "?").upper()
    font = _font(diameter / SS * 0.5, display=True, weight="Black")
    draw = ImageDraw.Draw(avatar)
    center = (diameter / 2, diameter / 2 + diameter * 0.02)
    draw.text(center, letter, font=font, fill=(4, 12, 28), anchor="mm")
    return avatar.convert("RGBA")


def _draw_avatar(img, draw, cx, cy, radius, name, data, accent, leader):
    ring = radius + 5
    _glow(
        img, _box(cx - ring, cy - ring, cx + ring, cy + ring), accent, _s(8),
        lambda d, ox, oy: d.ellipse(
            (_s(cx - ring) - ox, _s(cy - ring) - oy, _s(cx + ring) - ox, _s(cy + ring) - oy),
            outline=210, width=_s(4),
        ),
    )
    draw.ellipse(_box(cx - ring, cy - ring, cx + ring, cy + ring), outline=_rgba(accent, 240), width=_s(2.2))
    draw.ellipse(_box(cx - radius - 1, cy - radius - 1, cx + radius + 1, cy + radius + 1), fill=_rgba(NIGHT, 255))

    diameter = _s(radius * 2)
    avatar = _decode_avatar(data, diameter) or _monogram(name, diameter, accent)
    mask = Image.new("L", (diameter, diameter), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, diameter - 1, diameter - 1), fill=255)
    mask = ImageChops.multiply(mask, avatar.getchannel("A"))
    img.paste(avatar.convert("RGB"), (_s(cx - radius), _s(cy - radius)), mask)

    if leader:
        top = cy - ring
        draw.ellipse(_box(cx - 13, top - 13, cx + 13, top + 13), fill=_rgba(NIGHT, 255), outline=_rgba(GOLD, 255), width=_s(1.5))
        _icon_crown(draw, cx, top, 8, _rgba(GOLD, 255))


def _card_frame(img, draw, box, accent, strength):
    left, top, right, bottom = box
    corner = _s(18)
    scaled = _box(*box)
    _glow(
        img, scaled, accent, _s(9),
        lambda d, ox, oy: d.rounded_rectangle(
            (scaled[0] - ox, scaled[1] - oy, scaled[2] - ox, scaled[3] - oy),
            radius=corner, outline=strength, width=_s(2),
        ),
    )
    draw.rounded_rectangle(scaled, radius=corner, outline=_rgba(accent, 170), width=_s(1.4))
    _fade_line(img, left + 30, top + 1, right - left - 60, FROST, 230, 2.0)


def _draw_hunter(img, draw, box, player, index, maxima):
    left, top, right, bottom = box
    leader = bool(player.get("leader"))
    accent = GOLD if leader else ICE
    _card_frame(img, draw, box, accent, 120 if leader else 90)

    _tracked(draw, (left + 20, top + 26), f"HUNTER {ROMAN[index]}", _font(11), _rgba(MUTED, 255), 3)
    if leader:
        pill_font = _font(11)
        pill_width = _text_width(draw, "LEADER", pill_font) + 3 * 5 + 40
        draw.rounded_rectangle(
            _box(right - 18 - pill_width, top + 14, right - 18, top + 38),
            radius=_s(12), fill=_rgba(GOLD, 34), outline=_rgba(GOLD, 190), width=_s(1),
        )
        _icon_crown(draw, right - pill_width - 2, top + 26, 6, _rgba(GOLD, 255))
        _tracked(draw, (right - 30, top + 26), "LEADER", pill_font, _rgba(GOLD, 255), 3, anchor="rm")

    name = _clean_name(player.get("name"), "Unknown Hunter")
    _draw_avatar(img, draw, left + 62, top + 98, 38, name, player.get("avatar"), accent, leader)

    text_left = left + 122
    name_text, name_font = _fit_text(draw, name, right - text_left - 18, 26, 14, display=True, weight="Bold")
    draw.text((_s(text_left), _s(top + 86)), name_text, font=name_font, fill=_rgba(FROST, 255), anchor="lm")

    level_text = f"LV {int(_num(player.get('level', 1)))}"
    level_font = _font(12)
    pill_width = _text_width(draw, level_text, level_font) + 18
    draw.rounded_rectangle(
        _box(text_left, top + 106, text_left + pill_width, top + 128),
        radius=_s(11), fill=_rgba(accent, 40), outline=_rgba(accent, 170), width=_s(1),
    )
    draw.text((_s(text_left + pill_width / 2), _s(top + 117)), level_text, font=level_font, fill=_rgba(accent, 255), anchor="mm")
    class_text, class_font = _fit_text(
        draw, _clean_name(player.get("class"), "Adventurer"), right - text_left - pill_width - 28, 14, 10
    )
    draw.text((_s(text_left + pill_width + 10), _s(top + 117)), class_text, font=class_font, fill=_rgba(MUTED, 255), anchor="lm")

    _fade_line(img, left + 20, top + 158, right - left - 40, ICE, 90, 1.0)

    for row, (key, label, field) in enumerate((("atk", "ATK", "attack"), ("def", "DEF", "defense"), ("hp", "HP", "hp"))):
        ry = top + 180 + row * 42
        color = STAT_COLORS[key]
        value = _num(player.get(field))
        STAT_ICONS[key](draw, left + 29, ry, 8, _rgba(color, 255))
        _tracked(draw, (left + 46, ry), label, _font(12), _rgba(MUTED, 255), 2.6)
        text, font = _fit_text(draw, _format_stat(value), 170, 21, 13)
        draw.text((_s(right - 20), _s(ry)), text, font=font, fill=_rgba(FROST, 255), anchor="rm")
        _bar(
            img, draw, (left + 20, ry + 15, right - 20, ry + 20),
            value / maxima[key] if maxima[key] else 0,
            ((0.0, tuple(int(c * 0.55) for c in color)), (1.0, color)),
            radius=2.5,
        )

    _draw_pet_panel(img, draw, (left + 14, top + 304, right - 14, bottom - 14), player.get("pet"))


def _draw_pet_panel(img, draw, box, pet):
    left, top, right, bottom = box
    draw.rounded_rectangle(
        _box(*box), radius=_s(14), fill=(2, 7, 18, 150), outline=(170, 160, 255, 46), width=_s(1)
    )
    if not pet:
        cx, cy = (left + right) / 2, (top + bottom) / 2
        _icon_paw(draw, cx, cy - 14, 14, _rgba(DIM, 160))
        _tracked(draw, (cx, cy + 22), "NO COMPANION", _font(12), _rgba(DIM, 255), 3, anchor="mm")
        return

    _icon_badge(draw, left + 32, top + 34, 19, _icon_paw, VIOLET, 10)
    _tracked(draw, (left + 62, top + 22), "COMPANION", _font(10), _rgba(MUTED, 255), 2.8)

    level_text = f"LV {int(_num(pet.get('level', 1)))}"
    level_font = _font(11)
    pill_width = _text_width(draw, level_text, level_font) + 16
    draw.rounded_rectangle(
        _box(right - 14 - pill_width, top + 12, right - 14, top + 32),
        radius=_s(10), fill=_rgba(VIOLET, 36), outline=_rgba(VIOLET, 170), width=_s(1),
    )
    draw.text((_s(right - 14 - pill_width / 2), _s(top + 22)), level_text, font=level_font, fill=_rgba(VIOLET, 255), anchor="mm")

    pet_name, pet_font = _fit_text(
        draw, _clean_name(pet.get("name"), "Unknown"), right - left - 62 - 14, 18, 11, display=True, weight="Bold"
    )
    draw.text((_s(left + 62), _s(top + 46)), pet_name, font=pet_font, fill=_rgba(FROST, 255), anchor="lm")

    column_width = (right - left - 24) / 3
    for column, (key, field) in enumerate((("atk", "attack"), ("def", "defense"), ("hp", "hp"))):
        cx = left + 12 + column * column_width
        cy = bottom - 26
        STAT_ICONS[key](draw, cx + 10, cy, 7, _rgba(STAT_COLORS[key], 255))
        text, font = _fit_text(draw, _format_stat(_num(pet.get(field))), column_width - 28, 16, 10)
        draw.text((_s(cx + 22), _s(cy)), text, font=font, fill=_rgba(FROST, 255), anchor="lm")
        if column:
            draw.line(_box(cx - 2, cy - 12, cx - 2, cy + 12), fill=(150, 190, 240, 40), width=_s(1))


def _dashed_rounded_rect(draw, box, radius, color, dash=10, gap=8, width=1.4):
    left, top, right, bottom = box
    line_width = max(1, _s(width))
    for x0, y0, x1, y1 in (
        (left + radius, top, right - radius, top),
        (left + radius, bottom, right - radius, bottom),
        (left, top + radius, left, bottom - radius),
        (right, top + radius, right, bottom - radius),
    ):
        length = math.hypot(x1 - x0, y1 - y0)
        position = 0.0
        while position < length:
            end = min(length, position + dash)
            a, b = position / length, end / length
            draw.line(
                _box(x0 + (x1 - x0) * a, y0 + (y1 - y0) * a, x0 + (x1 - x0) * b, y0 + (y1 - y0) * b),
                fill=color, width=line_width,
            )
            position += dash + gap
    for (cx, cy), start in (
        ((left + radius, top + radius), 180),
        ((right - radius, top + radius), 270),
        ((right - radius, bottom - radius), 0),
        ((left + radius, bottom - radius), 90),
    ):
        draw.arc(_box(cx - radius, cy - radius, cx + radius, cy + radius), start, start + 90, fill=color, width=line_width)


def _draw_open_slot(img, draw, box, index):
    left, top, right, bottom = box
    cx = (left + right) / 2
    _dashed_rounded_rect(draw, box, 18, (120, 160, 210, 110))
    _tracked(draw, (left + 20, top + 26), f"HUNTER {ROMAN[index]}", _font(11), _rgba(DIM, 255), 3)

    cy = top + 150
    for k in range(18):
        start = k * 20
        draw.arc(_box(cx - 46, cy - 46, cx + 46, cy + 46), start, start + 11, fill=(127, 227, 255, 120), width=_s(1.6))
    _glow(
        img, _box(cx - 20, cy - 20, cx + 20, cy + 20), ICE, _s(6),
        lambda d, ox, oy: d.ellipse((_s(cx - 16) - ox, _s(cy - 16) - oy, _s(cx + 16) - ox, _s(cy + 16) - oy), fill=90),
    )
    draw.rounded_rectangle(_box(cx - 15, cy - 2.5, cx + 15, cy + 2.5), radius=_s(2.5), fill=_rgba(ICE, 220))
    draw.rounded_rectangle(_box(cx - 2.5, cy - 15, cx + 2.5, cy + 15), radius=_s(2.5), fill=_rgba(ICE, 220))

    draw.text(
        (_s(cx), _s(top + 236)), "OPEN SLOT",
        font=_font(24, display=True, weight="Black"), fill=(196, 214, 236, 255), anchor="mm",
    )
    draw.text(
        (_s(cx), _s(top + 268)), "Press Join to claim this spot",
        font=_font(14, weight="Regular"), fill=_rgba(MUTED, 255), anchor="mm",
    )

    pet_box = (left + 14, top + 304, right - 14, bottom - 14)
    _dashed_rounded_rect(draw, pet_box, 14, (150, 140, 230, 70), dash=6, gap=6, width=1.1)
    pcx, pcy = (pet_box[0] + pet_box[2]) / 2, (pet_box[1] + pet_box[3]) / 2
    _icon_paw(draw, pcx, pcy - 14, 13, _rgba(DIM, 120))
    _tracked(draw, (pcx, pcy + 22), "COMPANION SLOT", _font(11), _rgba(DIM, 255), 3, anchor="mm")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def render_dragon_party_card(dragon, party_members):
    """Render the party card and return it as an in-memory JPEG."""
    party = list(party_members)[:4]
    image = _static_base().copy()
    draw = ImageDraw.Draw(image, "RGBA")

    _draw_boss(image, draw, dragon)
    _draw_party_header(image, draw, party)

    maxima = {
        key: max((_num(member.get(field)) for member in party), default=0)
        for key, field in (("atk", "attack"), ("def", "defense"), ("hp", "hp"))
    }
    for index, box in enumerate(CARD_BOXES):
        if index < len(party):
            _draw_hunter(image, draw, box, party[index], index, maxima)
        else:
            _draw_open_slot(image, draw, box, index)

    image = image.resize((WIDTH, HEIGHT), Image.LANCZOS)
    output = BytesIO()
    image.save(output, format="JPEG", quality=92, subsampling=0)
    output.seek(0)
    return output

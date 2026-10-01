"""Procedurally drawn Ice Dragon party card.

Everything except the dragon artwork is drawn in code. Layout coordinates are
logical pixels on a 1600x900 canvas; the card is rendered ``SS`` times larger
and downscaled once to ``OUTPUT_SIZE``, which gives every shape, ring and bar
clean anti-aliased edges. Data-independent layers (sky, artwork, light rays,
snow, crystals, frosted glass) are built once and cached.
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
OUTPUT_SIZE = (1920, 1080)
SS = 2.4

NIGHT = (4, 9, 20)
FROST = (238, 247, 255)
ICE = (127, 227, 255)
ICE_DEEP = (52, 132, 230)
MUTED = (146, 172, 200)
DIM = (82, 104, 132)
GOLD = (255, 207, 112)
VIOLET = (186, 160, 255)
CRIMSON = (255, 82, 108)
ATK_COLOR = (255, 146, 118)
DEF_COLOR = ICE
HP_COLOR = (118, 236, 168)

ICE_METAL = ((0.0, (222, 246, 255)), (0.3, (126, 196, 244)), (1.0, (34, 66, 116)))
GOLD_METAL = ((0.0, (255, 242, 196)), (0.3, (238, 178, 76)), (1.0, (108, 64, 20)))
DIM_METAL = ((0.0, (120, 150, 190)), (1.0, (40, 56, 84)))

ART_LEFT, ART_TOP, ART_HEIGHT = 430, -10, 580
MOUTH = (752, 250)

BOSS_LEFT, BOSS_RIGHT = 56, 600
TILE_BOXES = (
    (1270, 92, 1544, 160),
    (1270, 172, 1544, 240),
    (1270, 252, 1544, 320),
)
BAR_TOP, BAR_BOTTOM = 448, 480
HEADER_Y = 522
CARD_TOP, CARD_BOTTOM = 556, 866
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
CARD_CUT = 16
ROMAN = ("I", "II", "III", "IV")

# Text-heavy regions where sharp foreground snowflakes would hurt legibility.
SNOW_FREE_ZONES = (
    (40, 30, 620, 360),
    (1260, 84, 1552, 328),
    (40, 416, 1560, 540),
)

THREAT_TIERS = ("MENACING", "DANGEROUS", "DEADLY", "LETHAL", "CATASTROPHIC", "APOCALYPTIC")
TAGLINES = {
    "frostbite wyrm": "The first bite of winter.",
    "corrupted ice dragon": "Rot sleeps beneath the rime.",
    "permafrost": "Nothing thaws. Nothing escapes.",
    "absolute zero": "Where even breath stands still.",
    "void tyrant": "The cold between the stars.",
    "eternal frost": "Winter without end.",
}
DEFAULT_TAGLINE = "The glacier stirs. Steel yourselves."


# ---------------------------------------------------------------------------
# Primitives
# ---------------------------------------------------------------------------


def _s(value):
    return int(round(value * SS))


def _box(x0, y0, x1, y1):
    return (_s(x0), _s(y0), _s(x1), _s(y1))


def _pts(points):
    return [(_s(x), _s(y)) for x, y in points]


def _rgba(color, alpha):
    return (*color[:3], int(alpha))


def _num(value):
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _format_stat(value):
    return f"{Decimal(str(value)):,.0f}"


@lru_cache(maxsize=160)
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
        color = stops[0][1] if t < stops[0][0] else stops[-1][1]
        for (p0, c0), (p1, c1) in zip(stops, stops[1:]):
            if p0 <= t <= p1:
                k = (t - p0) / max(1e-6, p1 - p0)
                color = tuple(int(a + (b - a) * k) for a, b in zip(c0, c1))
                break
        colors.append(color[:3])
    strip = Image.new("RGB", (length, 1))
    strip.putdata(colors)
    if axis == "x":
        return strip.resize((width, height), Image.NEAREST)
    return strip.transpose(Image.Transpose.ROTATE_270).resize((width, height), Image.NEAREST)


def _chamfer(box, cut):
    left, top, right, bottom = box
    return [
        (left + cut, top), (right - cut, top), (right, top + cut), (right, bottom - cut),
        (right - cut, bottom), (left + cut, bottom), (left, bottom - cut), (left, top + cut),
    ]


def _shape_mask(size, points, origin):
    mask = Image.new("L", size, 0)
    ImageDraw.Draw(mask).polygon([(x - origin[0], y - origin[1]) for x, y in points], fill=255)
    return mask


def _rounded_mask(size, radius):
    mask = Image.new("L", size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, size[0] - 1, size[1] - 1), radius=radius, fill=255)
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


def _glow_points(img, points, color, blur, strength, width=None):
    """Glow along a closed outline (``width``) or a filled polygon (``None``)."""
    xs, ys = [p[0] for p in points], [p[1] for p in points]

    def paint(d, ox, oy):
        shifted = [(x - ox, y - oy) for x, y in points]
        if width:
            d.line(shifted + [shifted[0]], fill=strength, width=width, joint="curve")
        else:
            d.polygon(shifted, fill=strength)

    _glow(img, (min(xs), min(ys), max(xs), max(ys)), color, blur, paint)


def _glow_text(img, draw, xy, text, font, color, strength=200, blur=12, anchor="la", offset=(0, 0)):
    x, y = _s(xy[0] + offset[0]), _s(xy[1] + offset[1])
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


def _gradient_text(img, draw, xy, text, font, stops, anchor="la"):
    x, y = _s(xy[0]), _s(xy[1])
    left, upper, right, lower = draw.textbbox((x, y), text, font=font, anchor=anchor)
    if right <= left or lower <= upper:
        return
    mask = Image.new("L", (right - left, lower - upper), 0)
    ImageDraw.Draw(mask).text((x - left, y - upper), text, font=font, fill=255, anchor=anchor)
    img.paste(_gradient(mask.size, stops, axis="y"), (left, upper), mask)


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


def _tracked_width(draw, text, font, tracking):
    return (sum(draw.textlength(ch, font=font) for ch in text) + _s(tracking) * max(0, len(text) - 1)) / SS


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
        img.paste(Image.new("RGB", mask.size, color[:3]), (_s(x0) - thick // 2, _s(y0)), mask)
        return
    img.paste(Image.new("RGB", mask.size, color[:3]), (_s(x0), _s(y0) - thick // 2), mask)


def _metal_stroke(img, points, stops, width):
    """Stroke a closed outline (canvas pixels) with a vertical metallic gradient."""
    pad = width + 2
    xs, ys = [p[0] for p in points], [p[1] for p in points]
    left, top = int(min(xs)) - pad, int(min(ys)) - pad
    size = (int(max(xs)) - left + pad, int(max(ys)) - top + pad)
    mask = Image.new("L", size, 0)
    shifted = [(x - left, y - top) for x, y in points]
    ImageDraw.Draw(mask).line(shifted + [shifted[0]], fill=255, width=width, joint="curve")
    img.paste(_gradient(size, stops, axis="y"), (left, top), mask)


def _dashed_path(draw, points, color, dash, gap, width):
    """Dash a closed logical-pixel outline, carrying the pattern around corners."""
    line_width = max(1, _s(width))
    closed = list(points) + [points[0]]
    drawing, remaining = True, dash
    for (x0, y0), (x1, y1) in zip(closed, closed[1:]):
        length = math.hypot(x1 - x0, y1 - y0)
        position = 0.0
        while position < length - 1e-6:
            step = min(remaining, length - position)
            if drawing:
                a, b = position / length, (position + step) / length
                draw.line(
                    _box(x0 + (x1 - x0) * a, y0 + (y1 - y0) * a, x0 + (x1 - x0) * b, y0 + (y1 - y0) * b),
                    fill=color, width=line_width,
                )
            position += step
            remaining -= step
            if remaining <= 1e-6:
                drawing = not drawing
                remaining = dash if drawing else gap


# ---------------------------------------------------------------------------
# Icons (centered on cx, cy; ``size`` is the half-extent in logical pixels)
# ---------------------------------------------------------------------------


def _poly(cx, cy, size, points, angle=0.0):
    cos_a, sin_a = math.cos(angle), math.sin(angle)
    return [
        (_s(cx + (x * cos_a - y * sin_a) * size), _s(cy + (x * sin_a + y * cos_a) * size))
        for x, y in points
    ]


def _icon_sword(draw, cx, cy, size, color, angle=45):
    radians = math.radians(angle)
    blade = ((-0.21, 0.2), (-0.21, -0.68), (0, -1.0), (0.21, -0.68), (0.21, 0.2))
    guard = ((-0.56, 0.18), (0.56, 0.18), (0.56, 0.38), (-0.56, 0.38))
    grip = ((-0.12, 0.38), (0.12, 0.38), (0.12, 0.74), (-0.12, 0.74))
    pommel = ((-0.22, 0.72), (0.22, 0.72), (0.22, 0.98), (-0.22, 0.98))
    for shape in (blade, guard, grip, pommel):
        draw.polygon(_poly(cx, cy, size, shape, radians), fill=color)


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


def _icon_skull(draw, cx, cy, size, color, hole=(6, 12, 26, 255)):
    draw.ellipse(_box(cx - 0.8 * size, cy - 0.92 * size, cx + 0.8 * size, cy + 0.5 * size), fill=color)
    draw.rounded_rectangle(
        _box(cx - 0.46 * size, cy + 0.1 * size, cx + 0.46 * size, cy + 0.92 * size),
        radius=_s(0.16 * size), fill=color,
    )
    for ox in (-0.33, 0.33):
        x = cx + ox * size
        draw.ellipse(_box(x - 0.22 * size, cy - 0.34 * size, x + 0.22 * size, cy + 0.1 * size), fill=hole)
    draw.polygon(_poly(cx, cy, size, ((0, 0.16), (-0.11, 0.4), (0.11, 0.4))), fill=hole)
    for ox in (-0.15, 0.15):
        draw.line(_box(cx + ox * size, cy + 0.6 * size, cx + ox * size, cy + 0.92 * size), fill=hole, width=max(1, _s(0.08 * size)))


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


def _gem(img, draw, cx, cy, size, color):
    """A faceted diamond gem with a soft halo."""
    _glow_points(img, _poly(cx, cy, size * 1.1, ((0, -1), (0.68, 0), (0, 1), (-0.68, 0))), color, _s(size * 0.7), 230)
    _icon_diamond(draw, cx, cy, size, fill=_rgba((6, 14, 30), 255), outline=_rgba(color, 255), width=1.3)
    draw.polygon(_poly(cx, cy, size * 0.55, ((0, -1), (0.68, 0), (0, 0))), fill=_rgba(FROST, 255))
    draw.polygon(_poly(cx, cy, size * 0.55, ((0, -1), (-0.68, 0), (0, 0))), fill=_rgba(color, 255))
    draw.polygon(_poly(cx, cy, size * 0.55, ((-0.68, 0), (0, 1), (0.68, 0))), fill=_rgba(color, 150))


STAT_ICONS = {"atk": _icon_sword, "def": _icon_shield, "hp": _icon_heart}
STAT_COLORS = {"atk": ATK_COLOR, "def": DEF_COLOR, "hp": HP_COLOR}


# ---------------------------------------------------------------------------
# Static background (cached)
# ---------------------------------------------------------------------------


def _paint_radial(img, center, radii, color, alpha, power=2.2):
    rx, ry = _s(radii[0]), _s(radii[1])
    mask = ImageOps.invert(Image.radial_gradient("L")).resize((rx * 2, ry * 2), Image.BILINEAR)
    mask = mask.point(lambda v: int(alpha * (v / 255) ** power))
    img.paste(Image.new("RGB", mask.size, color), (_s(center[0]) - rx, _s(center[1]) - ry), mask)


def _paint_light_rays(base):
    rng = random.Random(4)
    small = (WIDTH // 4, HEIGHT // 4)
    mask = Image.new("L", small, 0)
    draw = ImageDraw.Draw(mask)
    mx, my = MOUTH[0] / 4, MOUTH[1] / 4
    for _ in range(22):
        angle = rng.uniform(0, math.tau)
        spread = rng.uniform(0.012, 0.05)
        reach = 600
        draw.polygon(
            [
                (mx, my),
                (mx + math.cos(angle - spread) * reach, my + math.sin(angle - spread) * reach),
                (mx + math.cos(angle + spread) * reach, my + math.sin(angle + spread) * reach),
            ],
            fill=rng.randint(18, 52),
        )
    mask = mask.filter(ImageFilter.GaussianBlur(2.5)).resize(base.size, Image.BILINEAR)
    falloff = ImageOps.invert(Image.radial_gradient("L")).resize((_s(1500), _s(1100)), Image.BILINEAR)
    canvas = Image.new("L", base.size, 0)
    canvas.paste(falloff, (_s(MOUTH[0] - 750), _s(MOUTH[1] - 550)))
    base.paste(Image.new("RGB", base.size, (150, 215, 255)), (0, 0), ImageChops.multiply(mask, canvas))


def _paint_hero_art(base):
    if not ART_PATH.exists():
        return
    with Image.open(ART_PATH) as source:
        art = source.convert("RGB").crop(ART_CROP)
    width = ART_HEIGHT * art.width / art.height
    size = (_s(width), _s(ART_HEIGHT))
    art = art.resize(size, Image.LANCZOS)
    art = art.filter(ImageFilter.UnsharpMask(radius=_s(1.2), percent=70, threshold=2))
    art = ImageEnhance.Contrast(art).enhance(1.15)
    art = Image.blend(art, Image.new("RGB", size, (14, 36, 84)), 0.12)

    # Bloom: lift the already-glowing eye, throat and crystals into light.
    highlights = art.convert("L").point(lambda v: max(0, v - 120) * 2)
    bloom = highlights.filter(ImageFilter.GaussianBlur(_s(14)))
    art.paste(Image.new("RGB", size, (150, 220, 255)), (0, 0), bloom.point(lambda v: min(200, int(v * 1.1))))
    art.paste(Image.new("RGB", size, (235, 250, 255)), (0, 0), highlights.filter(ImageFilter.GaussianBlur(_s(3))).point(lambda v: v // 3))

    mask = ImageChops.multiply(
        _ramp_mask(size, "x", ((0.0, 0), (0.24, 255))),
        _ramp_mask(size, "y", ((0.56, 255), (0.98, 0))),
    )
    base.paste(art, (_s(ART_LEFT), _s(ART_TOP)), mask)


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
        mask = mask.filter(ImageFilter.GaussianBlur(7)).resize(base.size, Image.BILINEAR)
        mask = ImageChops.multiply(mask, _ramp_mask(mask.size, "x", ((0.0, 255), (0.45, 170), (0.7, 30))))
        base.paste(Image.new("RGB", mask.size, color), (0, 0), mask)


def _in_quiet_zone(x, y):
    return any(x0 <= x <= x1 and y0 <= y <= y1 for x0, y0, x1, y1 in SNOW_FREE_ZONES)


def _paint_snow(base, seed=1337):
    rng = random.Random(seed)
    bokeh = Image.new("L", (WIDTH // 2, HEIGHT // 2), 0)
    bokeh_draw = ImageDraw.Draw(bokeh)
    for _ in range(26):
        x, y = rng.uniform(0, WIDTH / 2), rng.uniform(0, HEIGHT / 2)
        r = rng.uniform(3, 9)
        bokeh_draw.ellipse((x - r, y - r, x + r, y + r), fill=rng.randint(30, 70))
    bokeh = bokeh.filter(ImageFilter.GaussianBlur(3)).resize(base.size, Image.BILINEAR)
    base.paste(Image.new("RGB", bokeh.size, (190, 225, 255)), (0, 0), bokeh)

    # Wind-driven streaks sell the blizzard around the dragon.
    streaks = Image.new("L", base.size, 0)
    streak_draw = ImageDraw.Draw(streaks)
    angle = math.radians(158)
    for _ in range(150):
        x, y = rng.uniform(560, WIDTH), rng.uniform(0, 460)
        if _in_quiet_zone(x, y):
            continue
        length = rng.uniform(14, 46)
        streak_draw.line(
            _box(x, y, x + math.cos(angle) * length, y + math.sin(angle) * length),
            fill=rng.randint(40, 120), width=max(1, _s(rng.choice((0.8, 1.0, 1.4)))),
        )
    streaks = streaks.filter(ImageFilter.GaussianBlur(_s(0.8)))
    base.paste(Image.new("RGB", base.size, (215, 236, 255)), (0, 0), streaks)

    draw = ImageDraw.Draw(base, "RGBA")
    for _ in range(320):
        x, y = rng.uniform(0, WIDTH), rng.uniform(0, HEIGHT)
        r = rng.choice((0.7, 0.9, 1.1, 1.4, 1.8, 2.3))
        alpha = rng.randint(70, 220) if r > 1 else rng.randint(40, 140)
        if _in_quiet_zone(x, y):
            continue
        draw.ellipse(_box(x - r, y - r, x + r, y + r), fill=(225, 240, 255, alpha))

    # Frost motes drifting out of the dragon's open jaws.
    for _ in range(18):
        x = MOUTH[0] + rng.uniform(-150, 30)
        y = MOUTH[1] + rng.uniform(-60, 90)
        r = rng.uniform(1.4, 3.2)
        _glow(base, _box(x - r, y - r, x + r, y + r), ICE, _s(r * 2.2),
              lambda d, ox, oy, x=x, y=y, r=r: d.ellipse(
                  (_s(x - r) - ox, _s(y - r) - oy, _s(x + r) - ox, _s(y + r) - oy), fill=230))
        draw.ellipse(_box(x - r * 0.5, y - r * 0.5, x + r * 0.5, y + r * 0.5), fill=(245, 252, 255, 240))


def _frost_glass(base, points, tint=(7, 16, 34), opacity=0.66):
    """Blur and tint the backdrop inside a logical-pixel polygon."""
    scaled = _pts(points)
    xs, ys = [p[0] for p in scaled], [p[1] for p in scaled]
    left, top, right, bottom = min(xs), min(ys), max(xs), max(ys)
    size = (right - left, bottom - top)
    region = base.crop((left, top, right, bottom)).filter(ImageFilter.GaussianBlur(_s(12)))
    region = Image.blend(region, Image.new("RGB", size, tint), opacity)
    sheen = _ramp_mask(size, "y", ((0.0, 34), (0.4, 6), (1.0, 0)))
    region.paste(Image.new("RGB", size, (190, 225, 255)), (0, 0), sheen)
    base.paste(region, (left, top), _shape_mask(size, scaled, (left, top)))


def _crystal(draw, x, y, length, width, angle):
    """One two-faced ice shard rising from (x, y), tilted by ``angle`` degrees."""
    radians = math.radians(angle)
    left_face = ((-0.5, 0), (-0.42, -0.7), (0, -1), (0, 0))
    right_face = ((0, 0), (0, -1), (0.42, -0.7), (0.5, 0))

    def shape(points):
        cos_a, sin_a = math.cos(radians), math.sin(radians)
        return [
            (_s(x + (px * width) * cos_a - (py * length) * sin_a), _s(y + (px * width) * sin_a + (py * length) * cos_a))
            for px, py in points
        ]

    draw.polygon(shape(left_face), fill=(170, 222, 255, 235))
    draw.polygon(shape(right_face), fill=(44, 100, 186, 240))
    outline = shape(((-0.5, 0), (-0.42, -0.7), (0, -1), (0.42, -0.7), (0.5, 0)))
    draw.line(outline, fill=(225, 246, 255, 230), width=_s(1), joint="curve")
    draw.line(shape(((0, -1), (0, -0.1))), fill=(235, 250, 255, 170), width=_s(1))


def _paint_crystals(base):
    clusters = (
        (14, 904, ((0, 168, 30, 6), (-12, 112, 24, -18), (22, 84, 18, 20), (-4, 60, 16, -40))),
        (WIDTH - 14, 904, ((0, 168, 30, -6), (12, 112, 24, 18), (-22, 84, 18, -20), (4, 60, 16, 40))),
    )
    for anchor_x, anchor_y, shards in clusters:
        _paint_radial(base, (anchor_x, anchor_y - 70), (80, 150), (70, 170, 255), 150)
        draw = ImageDraw.Draw(base, "RGBA")
        for dx, length, width, angle in sorted(shards, key=lambda s: -s[1]):
            _crystal(draw, anchor_x + dx, anchor_y, length, width, angle)


def _paint_vignette(base):
    mask = Image.radial_gradient("L").resize(base.size, Image.BILINEAR)
    mask = mask.point(lambda v: int(min(210, max(0, (v - 105) * 1.6))))
    base.paste(Image.new("RGB", base.size, (1, 3, 8)), (0, 0), mask)


def _paint_grain(base):
    small = (base.width // 2, base.height // 2)
    noise = Image.effect_noise(small, 22).resize(base.size, Image.BILINEAR).convert("RGB")
    return Image.blend(base, ImageChops.overlay(base, noise), 0.35)


def _paint_frame(base):
    draw = ImageDraw.Draw(base, "RGBA")
    inset = 14
    draw.rectangle(_box(inset, inset, WIDTH - inset, HEIGHT - inset), outline=(120, 180, 235, 70), width=_s(1))
    draw.rectangle(_box(inset + 6, inset + 6, WIDTH - inset - 6, HEIGHT - inset - 6), outline=(120, 180, 235, 26), width=_s(1))
    for x, y, sx, sy in (
        (inset, inset, 1, 1), (WIDTH - inset, inset, -1, 1),
        (inset, HEIGHT - inset, 1, -1), (WIDTH - inset, HEIGHT - inset, -1, -1),
    ):
        _fade_line(base, x if sx > 0 else x - 200, y, 200, ICE, 210, 1.4, "left" if sx > 0 else "right")
        _fade_line(base, x, y if sy > 0 else y - 130, 130, ICE, 210, 1.4, "left" if sy > 0 else "right", vertical=True)
        bracket = [(x + sx * 10, y + sy * 34), (x + sx * 10, y + sy * 10), (x + sx * 34, y + sy * 10)]
        draw.line(_pts(bracket), fill=(200, 240, 255, 200), width=_s(1.6), joint="curve")
        _gem(base, draw, x, y, 7, ICE)
    for y in (inset, HEIGHT - inset):
        _fade_line(base, WIDTH / 2 - 260, y, 520, ICE, 235, 1.6)
        for dx in (-34, 34):
            _icon_diamond(draw, WIDTH / 2 + dx, y, 4, fill=_rgba(ICE, 230))
        _gem(base, draw, WIDTH / 2, y, 12, ICE)


@lru_cache(maxsize=1)
def _static_base():
    """Build the data-independent backdrop once; renders draw on a copy."""
    size = (_s(WIDTH), _s(HEIGHT))
    base = _gradient(size, ((0.0, (12, 27, 58)), (0.5, (6, 14, 31)), (1.0, (2, 5, 12))), axis="y")
    _paint_radial(base, (900, 220), (820, 470), (38, 104, 200), 130)
    _paint_light_rays(base)
    _paint_hero_art(base)
    _paint_aurora(base)
    _paint_radial(base, MOUTH, (140, 110), (120, 210, 255), 90)

    scrim = _ramp_mask(size, "x", ((0.0, 215), (0.24, 165), (0.42, 0)))
    scrim = ImageChops.multiply(scrim, _ramp_mask(size, "y", ((0.0, 255), (0.42, 255), (0.5, 60))))
    base.paste(Image.new("RGB", size, NIGHT), (0, 0), scrim)
    lower = _ramp_mask(size, "y", ((0.5, 0), (0.64, 120), (1.0, 170)))
    base.paste(Image.new("RGB", size, (2, 6, 14)), (0, 0), lower)
    _paint_radial(base, (800, 940), (1000, 320), (26, 84, 168), 90)

    _paint_snow(base)
    for box in CARD_BOXES:
        _frost_glass(base, _chamfer(box, CARD_CUT))
    for box in TILE_BOXES:
        _frost_glass(base, _chamfer(box, 10), opacity=0.62)
    base = _paint_grain(base)
    _paint_vignette(base)
    _paint_crystals(base)
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


def _bar(img, draw, box, ratio, stops, radius, glow_color=None, ticks=0, shimmer=False):
    left, top, right, bottom = _box(*box)
    corner = _s(radius)
    fill_width = int((right - left) * max(0.0, min(1.0, ratio)))
    if glow_color and fill_width > 0:
        _glow(
            img, (left, top, left + fill_width, bottom), glow_color, _s(8),
            lambda d, ox, oy: d.rounded_rectangle(
                (left - ox, top - oy, left + fill_width - ox, bottom - oy), radius=corner, fill=160
            ),
        )
    draw.rounded_rectangle((left, top, right, bottom), radius=corner, fill=(200, 225, 255, 20))
    if fill_width > 0:
        height = bottom - top
        fill = _gradient((right - left, height), stops).crop((0, 0, fill_width, height))
        gloss = _ramp_mask(fill.size, "y", ((0.0, 110), (0.42, 20), (0.6, 0), (1.0, 0)))
        fill.paste(Image.new("RGB", fill.size, (255, 255, 255)), (0, 0), gloss)
        if shimmer:
            stripes = Image.new("L", fill.size, 0)
            stripe_draw = ImageDraw.Draw(stripes)
            step = _s(46)
            for x in range(-height, fill_width + height, step):
                stripe_draw.polygon(
                    [(x, height), (x + height, 0), (x + height + _s(14), 0), (x + _s(14), height)], fill=34
                )
            fill.paste(Image.new("RGB", fill.size, (255, 255, 255)), (0, 0), stripes)
            shade = _ramp_mask(fill.size, "y", ((0.55, 0), (1.0, 80)))
            fill.paste(Image.new("RGB", fill.size, (10, 20, 60)), (0, 0), shade)
        img.paste(fill, (left, top), _rounded_mask(fill.size, corner))
    for i in range(1, ticks):
        x = left + (right - left) * i / ticks
        major = ticks % 4 == 0 and i % (ticks // 4) == 0
        draw.line(
            (x, top + (_s(2) if major else _s(6)), x, bottom - (_s(2) if major else _s(6))),
            fill=(3, 10, 26, 170 if major else 110), width=_s(1.4 if major else 1),
        )


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


def _threat_tier(level):
    return max(1, min(len(THREAT_TIERS), (int(level) - 1) // 5 + 1))


def _title_layout(draw, name, max_width):
    """Pick one huge line, or two balanced stacked lines for long names."""
    for size in range(100, 75, -2):
        font = _font(size, True, "Black")
        if _text_width(draw, name, font) <= max_width:
            return [name], font

    words = name.split()
    if len(words) > 1:
        probe = _font(60, True, "Black")
        split = min(
            range(1, len(words)),
            key=lambda i: max(
                _text_width(draw, " ".join(words[:i]), probe),
                _text_width(draw, " ".join(words[i:]), probe),
            ),
        )
        lines = [" ".join(words[:split]), " ".join(words[split:])]
        for size in range(92, 47, -2):
            font = _font(size, True, "Black")
            if all(_text_width(draw, line, font) <= max_width for line in lines):
                return lines, font

    text, font = _fit_text(draw, name, max_width, 76, 40, display=True, weight="Black")
    return [text], font


def _draw_title(img, draw, dragon):
    x = BOSS_LEFT
    name = _clean_name(dragon.get("name"), "Ice Dragon").upper()
    lines, font = _title_layout(draw, name, BOSS_RIGHT - x)
    line_height = font.size / SS * 0.98
    center = 156
    first = center - line_height * (len(lines) - 1) / 2
    stops = ((0.0, (255, 255, 255)), (0.5, (196, 234, 255)), (1.0, (96, 166, 246)))
    for index, line in enumerate(lines):
        y = first + index * line_height
        _glow_text(img, draw, (x, y), line, font, (0, 2, 8), 255, blur=10, anchor="lm", offset=(0, 7))
        _glow_text(img, draw, (x, y), line, font, (40, 140, 255), 175, blur=20, anchor="lm")
        draw.text(
            (_s(x), _s(y)), line, font=font, fill=(8, 20, 46, 255), anchor="lm",
            stroke_width=_s(1.6), stroke_fill=(8, 20, 46, 255),
        )
        _gradient_text(img, draw, (x, y), line, font, stops, anchor="lm")

    stage_key = str(dragon.get("stage") or dragon.get("name") or "").strip().lower()
    tagline = TAGLINES.get(stage_key, DEFAULT_TAGLINE)
    _fade_line(img, x, 256, 40, ICE, 200, 1.4, "right")
    tagline_text, tagline_font = _fit_text(draw, tagline, BOSS_RIGHT - x - 52, 18, 12, display=True, weight="Regular")
    draw.text((_s(x + 52), _s(256)), tagline_text, font=tagline_font, fill=(176, 206, 236, 255), anchor="lm")


def _draw_boss(img, draw, dragon):
    x, right = BOSS_LEFT, BOSS_RIGHT

    tag_font = _font(12)
    tag_text = "WORLD BOSS"
    tag_width = _tracked_width(draw, tag_text, tag_font, 3) + 30
    slant = [(x + 8, 38), (x + tag_width + 8, 38), (x + tag_width, 62), (x, 62)]
    _glow_points(img, _pts(slant), CRIMSON, _s(8), 150)
    tag_fill = _gradient(_box(0, 0, tag_width + 8, 24)[2:], ((0.0, (255, 112, 132)), (1.0, (178, 28, 60))))
    img.paste(tag_fill, (_s(x), _s(38)), _shape_mask(tag_fill.size, _pts(slant), (_s(x), _s(38))))
    _tracked(draw, (x + 4 + tag_width / 2, 50), tag_text, tag_font, (255, 255, 255, 255), 3, anchor="mm")
    kicker_width = _tracked(draw, (x + tag_width + 24, 50), "ICE DRAGON CHALLENGE", _font(14), _rgba(ICE, 255), 3.6)
    _fade_line(img, x + tag_width + 38 + kicker_width, 50, 140, ICE, 140, 1.2, "left")

    _draw_title(img, draw, dragon)

    cy = 298
    level = int(_num(dragon.get("level", 1)))
    level_text = f"LV {level}"
    level_font = _font(17)
    badge_width = _text_width(draw, level_text, level_font) + 38
    hexagon = _pts((
        (x, cy), (x + 12, cy - 15), (x + badge_width - 12, cy - 15),
        (x + badge_width, cy), (x + badge_width - 12, cy + 15), (x + 12, cy + 15),
    ))
    _glow_points(img, hexagon, ICE, _s(8), 170)
    hex_fill = _gradient((_s(badge_width), _s(30)), ((0.0, (200, 245, 255)), (1.0, ICE_DEEP)))
    img.paste(hex_fill, (_s(x), _s(cy - 15)), _shape_mask(hex_fill.size, hexagon, (_s(x), _s(cy - 15))))
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

    tier = _threat_tier(level)
    ty = 342
    label_width = _tracked(draw, (x, ty), "THREAT", _font(12), _rgba(MUTED, 255), 3.2)
    px = x + label_width + 24
    for index in range(len(THREAT_TIERS)):
        cx = px + index * 26
        if index < tier:
            _glow(
                img, _box(cx - 10, ty - 10, cx + 10, ty + 10), CRIMSON, _s(6),
                lambda d, ox, oy, cx=cx: d.ellipse(
                    (_s(cx - 8) - ox, _s(ty - 8) - oy, _s(cx + 8) - ox, _s(ty + 8) - oy), fill=150
                ),
            )
            _icon_skull(draw, cx, ty, 10, _rgba((255, 196, 204), 255))
        else:
            _icon_skull(draw, cx, ty, 10, _rgba(DIM, 150))
    _tracked(
        draw, (px + len(THREAT_TIERS) * 26 + 6, ty), THREAT_TIERS[tier - 1],
        _font(14), _rgba(CRIMSON, 255), 3.4,
    )

    _draw_boss_tiles(img, draw, dragon)
    _draw_boss_bar(img, draw, dragon)


def _tile_frame(img, draw, box):
    points = _pts(_chamfer(box, 10))
    _metal_stroke(img, points, ((0.0, (170, 220, 255)), (1.0, (40, 76, 128))), _s(1.2))


def _draw_boss_tiles(img, draw, dragon):
    for box, key, label, field in (
        (TILE_BOXES[0], "atk", "ATTACK", "damage"),
        (TILE_BOXES[1], "def", "DEFENSE", "armor"),
    ):
        left, top, right, bottom = box
        mid = (top + bottom) / 2
        _tile_frame(img, draw, box)
        _icon_badge(draw, left + 36, mid, 20, STAT_ICONS[key], STAT_COLORS[key], 11)
        _tracked(draw, (left + 68, top + 22), label, _font(11), _rgba(MUTED, 255), 2.8)
        text, font = _fit_text(draw, _format_stat(dragon.get(field, 0)), right - left - 84, 27, 15)
        draw.text((_s(left + 68), _s(top + 47)), text, font=font, fill=_rgba(FROST, 255), anchor="lm")

    left, top, right, bottom = TILE_BOXES[2]
    mid = (top + bottom) / 2
    _tile_frame(img, draw, TILE_BOXES[2])
    _icon_badge(draw, left + 36, mid, 20, _icon_claw, VIOLET, 11)
    _tracked(draw, (left + 68, top + 22), "SIGNATURE", _font(11), _rgba(MUTED, 255), 2.8)
    move_name, move_damage = _signature_move(dragon.get("moves"))
    if move_name:
        _tracked(
            draw, (right - 16, top + 22), f"{_format_stat(move_damage)} DMG",
            _font(11), _rgba(VIOLET, 255), 1.6, anchor="rm",
        )
    move_text, move_font = _fit_text(
        draw, _clean_name(move_name, "Unknown"), right - left - 68 - 16, 20, 12, display=True, weight="Bold"
    )
    draw.text((_s(left + 68), _s(top + 47)), move_text, font=move_font, fill=_rgba(FROST, 255), anchor="lm")


def _draw_boss_bar(img, draw, dragon):
    left, right = CARD_LEFT, CARD_RIGHT
    hp = _num(dragon.get("hp", 0))

    label_y = BAR_TOP - 20
    _icon_heart(draw, left + 8, label_y, 8, _rgba(CRIMSON, 255))
    _tracked(draw, (left + 26, label_y), "DRAGON HEALTH", _font(13), _rgba(MUTED, 255), 3.4)
    hp_text, hp_font = _fit_text(draw, _format_stat(hp), 360, 24, 14)
    draw.text((_s(right - 34), _s(label_y + 8)), hp_text, font=hp_font, fill=_rgba(FROST, 255), anchor="rs")
    draw.text((_s(right), _s(label_y + 8)), "HP", font=_font(13), fill=_rgba(MUTED, 255), anchor="rs")
    hp_width = _text_width(draw, hp_text, hp_font)
    _tracked(draw, (right - 46 - hp_width, label_y), "100%", _font(12), _rgba(ICE, 255), 2.4, anchor="rm")

    plate = _pts(_chamfer((left - 8, BAR_TOP - 7, right + 8, BAR_BOTTOM + 7), 10))
    draw.polygon(plate, fill=(2, 7, 18, 235))
    _metal_stroke(img, plate, ICE_METAL, _s(1.6))
    _bar(
        img, draw, (left, BAR_TOP, right, BAR_BOTTOM), 1.0,
        ((0.0, (104, 64, 236)), (0.45, (58, 156, 255)), (0.85, (140, 232, 255)), (1.0, (240, 252, 255))),
        radius=4, glow_color=(70, 160, 255), ticks=20, shimmer=True,
    )
    mid = (BAR_TOP + BAR_BOTTOM) / 2
    for x in (left - 8, right + 8):
        _gem(img, draw, x, mid, 15, ICE)


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
    _gradient_text(
        img, draw, (CARD_LEFT, y), title, title_font,
        ((0.0, (255, 255, 255)), (1.0, (160, 214, 255))), anchor="lm",
    )
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
    cursor += _tracked(draw, (cursor, y), f"{len(party)}/4 READY", _font(13), _rgba(ready_color, 255), 2.6)

    totals = _party_totals(party)
    value_font = _font(18)
    x = CARD_RIGHT
    for key in ("hp", "def", "atk"):
        text = _format_stat(totals[key])
        draw.text((_s(x), _s(y)), text, font=value_font, fill=_rgba(FROST, 255), anchor="rm")
        x -= _text_width(draw, text, value_font) + 10
        STAT_ICONS[key](draw, x - 7, y, 8, _rgba(STAT_COLORS[key], 255))
        x -= 14 + 24
    x += 8
    x -= _tracked(draw, (x, y), "PARTY POWER", _font(11), _rgba(MUTED, 255), 2.8, anchor="rm")

    medallion_x = WIDTH / 2
    _fade_line(img, cursor + 20, y, medallion_x - 34 - cursor - 20, ICE, 170, 1.2, "right")
    _fade_line(img, medallion_x + 34, y, x - 20 - medallion_x - 34, ICE, 170, 1.2, "left")
    _draw_medallion(img, draw, medallion_x, y)


def _draw_medallion(img, draw, cx, cy):
    """Crossed swords between the boss and the party."""
    radius = 27
    _glow(
        img, _box(cx - radius, cy - radius, cx + radius, cy + radius), ICE, _s(12),
        lambda d, ox, oy: d.ellipse(
            (_s(cx - radius) - ox, _s(cy - radius) - oy, _s(cx + radius) - ox, _s(cy + radius) - oy), fill=170
        ),
    )
    diamond = _poly(cx, cy, radius + 8, ((0, -1), (1, 0), (0, 1), (-1, 0)))
    draw.polygon(diamond, fill=(4, 10, 24, 255))
    _metal_stroke(img, diamond, ICE_METAL, _s(1.8))
    inner = _poly(cx, cy, radius + 2, ((0, -1), (1, 0), (0, 1), (-1, 0)))
    draw.line(inner + [inner[0]], fill=(127, 227, 255, 70), width=_s(1))
    _icon_sword(draw, cx, cy, 19, _rgba(FROST, 255), angle=45)
    _icon_sword(draw, cx, cy, 19, _rgba(ICE, 255), angle=-45)


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
    shade = Image.radial_gradient("L").resize((diameter, diameter), Image.BILINEAR)
    avatar = ImageOps.colorize(shade, black=accent, white=(10, 24, 52), mid=ICE_DEEP)
    letter = next((ch for ch in name if ch.isalnum()), "?").upper()
    font = _font(diameter / SS * 0.5, display=True, weight="Black")
    draw = ImageDraw.Draw(avatar)
    draw.text((diameter / 2, diameter / 2 + diameter * 0.02), letter, font=font, fill=(4, 12, 28), anchor="mm")
    return avatar.convert("RGBA")


def _draw_avatar(img, draw, cx, cy, radius, name, data, accent, leader):
    ring = radius + 5
    _glow(
        img, _box(cx - ring, cy - ring, cx + ring, cy + ring), accent, _s(9),
        lambda d, ox, oy: d.ellipse(
            (_s(cx - ring) - ox, _s(cy - ring) - oy, _s(cx + ring) - ox, _s(cy + ring) - oy),
            outline=220, width=_s(4),
        ),
    )
    ring_box = _box(cx - ring, cy - ring, cx + ring, cy + ring)
    ring_mask = Image.new("L", (ring_box[2] - ring_box[0] + 1, ring_box[3] - ring_box[1] + 1), 0)
    ImageDraw.Draw(ring_mask).ellipse((0, 0, ring_mask.width - 1, ring_mask.height - 1), outline=255, width=_s(2.6))
    metal = GOLD_METAL if leader else ICE_METAL
    img.paste(_gradient(ring_mask.size, metal, axis="y"), ring_box[:2], ring_mask)
    draw.ellipse(_box(cx - radius - 1, cy - radius - 1, cx + radius + 1, cy + radius + 1), fill=_rgba(NIGHT, 255))

    diameter = _s(radius * 2)
    avatar = _decode_avatar(data, diameter) or _monogram(name, diameter, accent)
    mask = Image.new("L", (diameter, diameter), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, diameter - 1, diameter - 1), fill=255)
    mask = ImageChops.multiply(mask, avatar.getchannel("A"))
    img.paste(avatar.convert("RGB"), (_s(cx - radius), _s(cy - radius)), mask)
    inner_shade = _ramp_mask((diameter, diameter), "y", ((0.55, 0), (1.0, 90)))
    img.paste(Image.new("RGB", (diameter, diameter), (2, 6, 16)), (_s(cx - radius), _s(cy - radius)), ImageChops.multiply(inner_shade, mask))

    if leader:
        top = cy - ring
        draw.ellipse(_box(cx - 12, top - 12, cx + 12, top + 12), fill=_rgba(NIGHT, 255), outline=_rgba(GOLD, 255), width=_s(1.5))
        _icon_crown(draw, cx, top, 7.5, _rgba(GOLD, 255))


def _card_frame(img, draw, box, accent, leader):
    left, top, right, bottom = box
    outline = _pts(_chamfer(box, CARD_CUT))
    _glow_points(img, outline, accent, _s(10), 150 if leader else 110, width=_s(3))
    _metal_stroke(img, outline, GOLD_METAL if leader else ICE_METAL, _s(1.8))
    inner = _pts(_chamfer((left + 6, top + 6, right - 6, bottom - 6), CARD_CUT - 3))
    draw.line(inner + [inner[0]], fill=_rgba(accent, 40), width=_s(1), joint="curve")
    _fade_line(img, left + 40, top + 1, right - left - 80, FROST, 220, 1.6)
    _gem(img, draw, (left + right) / 2, top, 9, accent)


def _draw_hunter(img, draw, box, player, index, maxima):
    left, top, right, bottom = box
    leader = bool(player.get("leader"))
    accent = GOLD if leader else ICE
    _card_frame(img, draw, box, accent, leader)

    _tracked(draw, (left + 22, top + 24), f"HUNTER {ROMAN[index]}", _font(11), _rgba(MUTED, 255), 3)
    if leader:
        pill_font = _font(11)
        pill_width = _tracked_width(draw, "LEADER", pill_font, 3) + 40
        draw.rounded_rectangle(
            _box(right - 20 - pill_width, top + 13, right - 20, top + 35),
            radius=_s(11), fill=_rgba(GOLD, 34), outline=_rgba(GOLD, 190), width=_s(1),
        )
        _icon_crown(draw, right - pill_width - 4, top + 24, 6, _rgba(GOLD, 255))
        _tracked(draw, (right - 32, top + 24), "LEADER", pill_font, _rgba(GOLD, 255), 3, anchor="rm")

    name = _clean_name(player.get("name"), "Unknown Hunter")
    _draw_avatar(img, draw, left + 58, top + 84, 34, name, player.get("avatar"), accent, leader)

    text_left = left + 108
    name_text, name_font = _fit_text(draw, name, right - text_left - 18, 25, 13, display=True, weight="Bold")
    _glow_text(img, draw, (text_left, top + 72), name_text, name_font, accent, 70, blur=8, anchor="lm")
    draw.text((_s(text_left), _s(top + 72)), name_text, font=name_font, fill=_rgba(FROST, 255), anchor="lm")

    level_text = f"LV {int(_num(player.get('level', 1)))}"
    level_font = _font(12)
    pill_width = _text_width(draw, level_text, level_font) + 18
    pill_y = top + 103
    draw.rounded_rectangle(
        _box(text_left, pill_y - 11, text_left + pill_width, pill_y + 11),
        radius=_s(11), fill=_rgba(accent, 40), outline=_rgba(accent, 170), width=_s(1),
    )
    draw.text((_s(text_left + pill_width / 2), _s(pill_y)), level_text, font=level_font, fill=_rgba(accent, 255), anchor="mm")
    class_text, class_font = _fit_text(
        draw, _clean_name(player.get("class"), "Adventurer"), right - text_left - pill_width - 28, 14, 10
    )
    draw.text((_s(text_left + pill_width + 10), _s(pill_y)), class_text, font=class_font, fill=_rgba(MUTED, 255), anchor="lm")

    _fade_line(img, left + 20, top + 134, right - left - 40, ICE, 90, 1.0)

    column_width = (right - left - 40) / 3
    for column, (key, field) in enumerate((("atk", "attack"), ("def", "defense"), ("hp", "hp"))):
        cx = left + 20 + column * column_width
        cy = top + 156
        color = STAT_COLORS[key]
        value = _num(player.get(field))
        STAT_ICONS[key](draw, cx + 8, cy, 8, _rgba(color, 255))
        text, font = _fit_text(draw, _format_stat(value), column_width - 34, 19, 11)
        draw.text((_s(cx + 22), _s(cy)), text, font=font, fill=_rgba(FROST, 255), anchor="lm")
        _bar(
            img, draw, (cx, cy + 15, cx + column_width - 12, cy + 19),
            value / maxima[key] if maxima[key] else 0,
            ((0.0, tuple(int(c * 0.5) for c in color)), (1.0, color)),
            radius=2,
        )

    _draw_pet_panel(img, draw, (left + 14, top + 192, right - 14, bottom - 14), player.get("pet"))


def _draw_pet_panel(img, draw, box, pet):
    left, top, right, bottom = box
    outline = _pts(_chamfer(box, 10))
    draw.polygon(outline, fill=(2, 7, 18, 160))
    draw.line(outline + [outline[0]], fill=(170, 160, 255, 54), width=_s(1), joint="curve")
    if not pet:
        cx, cy = (left + right) / 2, (top + bottom) / 2
        _icon_paw(draw, cx, cy - 13, 13, _rgba(DIM, 160))
        _tracked(draw, (cx, cy + 20), "NO COMPANION", _font(12), _rgba(DIM, 255), 3, anchor="mm")
        return

    _icon_badge(draw, left + 30, top + 31, 18, _icon_paw, VIOLET, 9.5)
    _tracked(draw, (left + 58, top + 20), "COMPANION", _font(10), _rgba(MUTED, 255), 2.8)

    level_text = f"LV {int(_num(pet.get('level', 1)))}"
    level_font = _font(11)
    pill_width = _text_width(draw, level_text, level_font) + 16
    draw.rounded_rectangle(
        _box(right - 14 - pill_width, top + 11, right - 14, top + 31),
        radius=_s(10), fill=_rgba(VIOLET, 36), outline=_rgba(VIOLET, 170), width=_s(1),
    )
    draw.text((_s(right - 14 - pill_width / 2), _s(top + 21)), level_text, font=level_font, fill=_rgba(VIOLET, 255), anchor="mm")

    pet_name, pet_font = _fit_text(
        draw, _clean_name(pet.get("name"), "Unknown"), right - left - 58 - 14, 18, 11, display=True, weight="Bold"
    )
    draw.text((_s(left + 58), _s(top + 42)), pet_name, font=pet_font, fill=_rgba(FROST, 255), anchor="lm")

    column_width = (right - left - 24) / 3
    for column, (key, field) in enumerate((("atk", "attack"), ("def", "defense"), ("hp", "hp"))):
        cx = left + 12 + column * column_width
        cy = bottom - 22
        STAT_ICONS[key](draw, cx + 10, cy, 7, _rgba(STAT_COLORS[key], 255))
        text, font = _fit_text(draw, _format_stat(_num(pet.get(field))), column_width - 28, 16, 10)
        draw.text((_s(cx + 22), _s(cy)), text, font=font, fill=_rgba(FROST, 255), anchor="lm")
        if column:
            draw.line(_box(cx - 2, cy - 11, cx - 2, cy + 11), fill=(150, 190, 240, 40), width=_s(1))


def _draw_open_slot(img, draw, box, index):
    left, top, right, bottom = box
    cx = (left + right) / 2
    _dashed_path(draw, _chamfer(box, CARD_CUT), (120, 160, 210, 120), 10, 8, 1.4)
    _icon_diamond(draw, cx, top, 7, fill=_rgba((6, 14, 30), 255), outline=_rgba(DIM, 255), width=1.2)
    _tracked(draw, (left + 22, top + 24), f"HUNTER {ROMAN[index]}", _font(11), _rgba(DIM, 255), 3)

    cy = top + 86
    for k in range(18):
        start = k * 20
        draw.arc(_box(cx - 38, cy - 38, cx + 38, cy + 38), start, start + 11, fill=(127, 227, 255, 120), width=_s(1.6))
    _glow(
        img, _box(cx - 18, cy - 18, cx + 18, cy + 18), ICE, _s(6),
        lambda d, ox, oy: d.ellipse((_s(cx - 14) - ox, _s(cy - 14) - oy, _s(cx + 14) - ox, _s(cy + 14) - oy), fill=90),
    )
    draw.rounded_rectangle(_box(cx - 13, cy - 2.2, cx + 13, cy + 2.2), radius=_s(2.2), fill=_rgba(ICE, 220))
    draw.rounded_rectangle(_box(cx - 2.2, cy - 13, cx + 2.2, cy + 13), radius=_s(2.2), fill=_rgba(ICE, 220))

    draw.text(
        (_s(cx), _s(top + 148)), "OPEN SLOT",
        font=_font(23, display=True, weight="Black"), fill=(196, 214, 236, 255), anchor="mm",
    )
    draw.text(
        (_s(cx), _s(top + 174)), "Press Join to answer the call",
        font=_font(14, weight="Regular"), fill=_rgba(MUTED, 255), anchor="mm",
    )

    pet_box = (left + 14, top + 192, right - 14, bottom - 14)
    _dashed_path(draw, _chamfer(pet_box, 10), (150, 140, 230, 80), 6, 6, 1.1)
    pcx, pcy = (pet_box[0] + pet_box[2]) / 2, (pet_box[1] + pet_box[3]) / 2
    _icon_paw(draw, pcx, pcy - 13, 12, _rgba(DIM, 120))
    _tracked(draw, (pcx, pcy + 20), "COMPANION SLOT", _font(11), _rgba(DIM, 255), 3, anchor="mm")


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

    image = image.resize(OUTPUT_SIZE, Image.LANCZOS)
    output = BytesIO()
    image.save(output, format="JPEG", quality=93, subsampling=0)
    output.seek(0)
    return output

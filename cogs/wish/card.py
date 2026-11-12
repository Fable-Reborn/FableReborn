"""The birthday wish card: every approved wish on one picture, under a sky of wish lanterns.

`render_cards(recipient, wishes)` returns one image per PER_PAGE wishes (bytes and a filename
each). A wish is a dict with "name", "message" and optionally "avatar" (image bytes); a wish
without a usable avatar gets a coloured initial instead.

Everything is drawn at twice the final size and scaled down, so edges and small text stay
smooth. PIL and numpy only (no Discord), so tests and the sample script can share it.
"""
from __future__ import annotations

import io
import random
from functools import lru_cache
from pathlib import Path

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parents[2]
FONT_DIR = ROOT / "assets" / "profile_themes" / "fonts"
FONT_FILES = {
    "title": FONT_DIR / "Cinzel.ttf",
    "bold": FONT_DIR / "Lato-Bold.ttf",
    "body": FONT_DIR / "Lato-Regular.ttf",
    "emoji": ROOT / "assets" / "okapi" / "fonts" / "OpenSansEmoji.ttf",
}

S = 2                    # drawn at S times the final size
W = 1800                 # final width
MARGIN = 84
GAP = 30
COLUMNS = 3
COLUMN_W = (W - 2 * MARGIN - (COLUMNS - 1) * GAP) // COLUMNS
PAD = 28
AVATAR = 62
BODY_SIZE = 27
LINE_H = 39
NAME_SIZE = 27
HEADER_H = 600           # first page; later pages get SHORT_HEADER_H
SHORT_HEADER_H = 250
FOOTER_H = 250
PER_PAGE = 30
MAX_BYTES = 8_000_000    # Discord takes 10 MB; over this the card goes out as a JPEG instead

GOLD = (246, 205, 124)
CREAM = (246, 238, 224)
MUTED = (190, 176, 205)
ACCENTS = (
    (246, 205, 124),   # gold
    (247, 156, 178),   # rose
    (196, 168, 255),   # lavender
    (134, 218, 222),   # aqua
    (255, 184, 134),   # peach
    (168, 228, 176),   # mint
)
FOIL = ((255, 247, 214), (248, 208, 120), (201, 141, 60))   # top, middle, bottom of the gold lettering


# ---- fonts and text --------------------------------------------------------------------------

@lru_cache(maxsize=64)
def _font(role: str, size: float) -> ImageFont.FreeTypeFont:
    font = ImageFont.truetype(str(FONT_FILES[role]), round(size * S))
    if role == "title":
        try:   # Cinzel ships as a variable font; the heavy cut carries the foil better
            font.set_variation_by_name("Bold")
        except Exception:
            pass
    return font


@lru_cache(maxsize=8192)
def _has_glyph(role: str, ch: str) -> bool:
    """Whether the font draws ch as itself rather than as its missing-glyph box."""
    probe = _font(role, 20)
    mask, missing = probe.getmask(ch), probe.getmask("\U0010FFFF")
    return mask.size != missing.size or bytes(mask) != bytes(missing)


# Common symbols neither font has, drawn as the nearest one they do have. The emoji font is an
# old one, so the newer faces and gestures go to their older relatives.
STAND_INS = {"⭐": "★", "✨": "★", "✦": "★", "\U0001F31F": "★",
             "\U0001F970": "\U0001F60D", "\U0001F973": "\U0001F389", "\U0001FAF6": "\U0001F495"}

# Hearts keep their colour. The emoji font draws in one colour and has none of the newer hearts
# (pink, orange, white...), so every heart is drawn as a heart the font does have, in the colour
# the wisher chose.
HEARTS = {
    "❤": (240, 84, 96), "❣": (240, 84, 96), "♥": (240, 84, 96),
    "\U0001FA77": (255, 150, 192), "\U0001F9E1": (255, 158, 72), "\U0001F49B": (255, 214, 92), "\U0001F49A": (118, 220, 140),
    "\U0001F499": (112, 164, 255), "\U0001FA75": (140, 208, 255), "\U0001F49C": (190, 142, 255), "\U0001F90E": (176, 116, 84),
    "\U0001F5A4": (132, 132, 148), "\U0001FA76": (176, 180, 192), "\U0001F90D": (255, 255, 255),
    "\U0001F496": (255, 150, 192), "\U0001F497": (255, 150, 192), "\U0001F493": (255, 120, 150), "\U0001F495": (255, 150, 192),
    "\U0001F49E": (255, 150, 192), "\U0001F498": (255, 120, 150), "\U0001F49D": (255, 150, 192),
}


# The font fills these four with a pattern (hatched, dotted) to tell them apart in one colour.
# With real colour that isn't needed, so they are drawn solid like the rest.
PLAIN_HEARTS = "\U0001F49B\U0001F49A\U0001F499\U0001F49C"


def _runs(text: str, role: str) -> list[tuple[str, str, tuple | None]]:
    """text split into (font role, characters, colour): the given font where it has the glyph,
    the emoji font where only that does, and nothing for characters neither can draw. colour is
    None for ordinary text and the heart's own colour for a heart."""
    runs: list[tuple[str, str, tuple | None]] = []
    for ch in text:
        if ch in STAND_INS and not _has_glyph(role, ch) and not _has_glyph("emoji", ch):
            ch = STAND_INS[ch]
        colour = HEARTS.get(ch)
        if colour and (ch in PLAIN_HEARTS or not _has_glyph("emoji", ch)):
            ch = "♥"
        if ch.isspace():
            use, colour = (runs[-1][0] if runs else role), (runs[-1][2] if runs else None)
            ch = " "
        elif _has_glyph(role, ch):
            use = role
        elif _has_glyph("emoji", ch):
            use = "emoji"
        else:
            continue   # variation selectors, joiners, scripts neither font covers
        if runs and runs[-1][0] == use and runs[-1][2] == colour:
            runs[-1] = (use, runs[-1][1] + ch, colour)
        else:
            runs.append((use, ch, colour))
    return runs


def _width(text: str, role: str, size: float) -> float:
    return sum(_font(r, size).getlength(part) for r, part, _colour in _runs(text, role))


def _draw_text(draw, x: float, baseline: float, text: str, role: str, size: float, fill) -> float:
    """Draws text from x on the baseline (both already multiplied by S). Returns where it ended."""
    for r, part, colour in _runs(text, role):
        font = _font(r, size)
        draw.text((x, baseline), part, font=font, fill=(*colour, *fill[3:]) if colour else fill, anchor="ls")
        x += font.getlength(part)
    return x


def _wrap(text: str, role: str, size: float, width: float) -> list[str]:
    """text in lines no wider than width (final pixels). A word longer than a line is cut."""
    limit = width * S
    lines: list[str] = []
    for paragraph in text.split("\n"):
        line = ""
        for word in paragraph.split():
            trial = f"{line} {word}" if line else word
            if _width(trial, role, size) <= limit:
                line = trial
                continue
            if line:
                lines.append(line)
            line = word
            while _width(line, role, size) > limit:
                cut = len(line) - 1
                while cut > 1 and _width(line[:cut], role, size) > limit:
                    cut -= 1
                lines.append(line[:cut])
                line = line[cut:]
        if line:
            lines.append(line)
    return lines or [""]


def _fit(text: str, role: str, size: float, width: float) -> str:
    """text, cut with an ellipsis if it is wider than width (final pixels)."""
    if _width(text, role, size) <= width * S:
        return text
    while text and _width(text + "…", role, size) > width * S:
        text = text[:-1]
    return text.rstrip() + "…"


# ---- the sky -----------------------------------------------------------------------------------

def _sky(height: int, header_h: int, rng: random.Random) -> Image.Image:
    """The night behind everything, at final size: a violet dusk, a warm glow behind the title
    and the sign-off, soft lights, darker edges."""
    ys = np.linspace(0, 1, height, dtype=np.float32)[:, None]
    xs = np.linspace(0, 1, W, dtype=np.float32)[None, :]
    stops = np.array([[9, 8, 28], [25, 14, 60], [50, 20, 70], [30, 13, 46]], dtype=np.float32)
    at = np.array([0.0, 0.32, 0.72, 1.0], dtype=np.float32)
    sky = np.stack([np.interp(ys[:, 0], at, stops[:, c]) for c in range(3)], axis=1)[:, None, :]
    sky = np.repeat(sky, W, axis=1)

    def glow(cx, cy, rx, ry, colour, power=1.6):
        dist = ((xs * W - cx) / rx) ** 2 + ((ys * height - cy) / ry) ** 2
        return np.clip(1 - dist, 0, 1)[..., None] ** power * np.array(colour, dtype=np.float32)

    sky += glow(W / 2, header_h * 0.48, 980, header_h * 0.95, (110, 58, 44))
    sky += glow(W / 2, header_h * 0.50, 520, header_h * 0.55, (70, 44, 20), 2.2)
    sky += glow(W / 2, height - FOOTER_H * 0.55, 900, FOOTER_H * 1.25, (92, 40, 52))
    edge = np.clip(np.abs(xs - 0.5) * 2, 0, 1) ** 3
    sky *= (1 - 0.34 * edge)[..., None]
    sky += np.random.default_rng(rng.randrange(1 << 30)).uniform(-1.3, 1.3, sky.shape)   # hides banding
    image = Image.fromarray(np.clip(sky, 0, 255).astype(np.uint8), "RGB")

    lights = Image.new("RGBA", (W, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(lights)
    for _ in range(max(26, height // 90)):
        r = rng.randint(34, 150)
        x, y = rng.randint(-60, W + 60), rng.randint(-60, height + 60)
        draw.ellipse((x - r, y - r, x + r, y + r), fill=(*rng.choice(ACCENTS), rng.randint(9, 24)))
    image.paste(lights.filter(ImageFilter.GaussianBlur(26)), (0, 0), lights.filter(ImageFilter.GaussianBlur(26)))
    return image


def _stars(canvas: Image.Image, header_h: int, rng: random.Random) -> None:
    draw = ImageDraw.Draw(canvas, "RGBA")
    width, height = canvas.size
    for _ in range(height // 9):
        # thicker towards the top, where the sky is darkest
        y = int(height * rng.random() ** 1.7)
        x = rng.randrange(width)
        r = rng.choice((1, 1, 1, 2, 2, 3))
        tint = rng.choice(((255, 255, 255), (255, 236, 200), (214, 208, 255)))
        draw.ellipse((x - r, y - r, x + r, y + r), fill=(*tint, rng.randint(50, 215)))
    for _ in range(max(26, height // 360)):
        y = int(height * rng.random() ** 1.4)
        x = rng.randrange(width)
        _sparkle(draw, x, y, rng.randint(9, 24), (255, 240, 205, rng.randint(120, 230)))


def _sparkle(draw, x: float, y: float, r: float, fill) -> None:
    t = max(1.5, r * 0.14)
    draw.polygon(((x, y - r), (x + t, y), (x, y + r), (x - t, y)), fill=fill)
    draw.polygon(((x - r, y), (x, y - t), (x + r, y), (x, y + t)), fill=fill)
    draw.ellipse((x - t * 1.3, y - t * 1.3, x + t * 1.3, y + t * 1.3), fill=fill)


@lru_cache(maxsize=32)
def _lantern(h: int) -> tuple[Image.Image, Image.Image]:
    """A lit paper wish lantern h pixels tall: the light it throws (an RGB tile, black where
    there is none) and the lantern itself."""
    w = round(h * 0.74)
    tile = h * 5
    c = tile // 2
    light = Image.new("RGB", (tile, tile), (0, 0, 0))
    ld = ImageDraw.Draw(light)
    ld.ellipse((c - h * 1.5, c - h * 1.35, c + h * 1.5, c + h * 1.65), fill=(92, 44, 16))
    ld.ellipse((c - h * 0.8, c - h * 0.65, c + h * 0.8, c + h * 0.95), fill=(150, 84, 34))
    light = light.filter(ImageFilter.GaussianBlur(h * 0.42))

    mask = Image.new("L", (w, h), 0)
    md = ImageDraw.Draw(mask)
    md.ellipse((0, 0, w - 1, h * 0.74), fill=255)
    md.polygon(((w * 0.02, h * 0.37), (w * 0.98, h * 0.37), (w * 0.76, h * 0.93), (w * 0.24, h * 0.93)), fill=255)
    ys = np.linspace(0, 1, h, dtype=np.float32)[:, None]
    xs = np.linspace(-1, 1, w, dtype=np.float32)[None, :]
    top, bottom = np.array([222, 92, 56], np.float32), np.array([255, 216, 124], np.float32)
    body = top + (bottom - top) * (ys ** 1.25)[..., None]
    body = np.repeat(body, w, axis=1)
    core = np.clip(1 - (xs ** 2 * 1.8 + ((ys - 0.82) / 0.42) ** 2), 0, 1)[..., None]
    body += core ** 1.4 * np.array([40, 60, 110], np.float32)       # the flame showing through the paper
    body *= (1 - 0.30 * np.abs(xs) ** 2.2)[..., None]                 # rounder at the sides
    paper = Image.fromarray(np.clip(body, 0, 255).astype(np.uint8), "RGB").convert("RGBA")
    pd = ImageDraw.Draw(paper)
    for rib in (-0.42, 0, 0.42):                                       # faint paper ribs
        pd.line((w / 2 + rib * w * 0.9, h * 0.06, w / 2 + rib * w * 0.62, h * 0.92), fill=(150, 60, 36, 60), width=max(1, h // 70))
    pd.rounded_rectangle((w * 0.24, h * 0.90, w * 0.76, h * 0.96), radius=h * 0.02, fill=(96, 44, 30, 255))
    paper.putalpha(mask)
    return light, paper


def _float_lantern(canvas: Image.Image, x: float, y: float, h: float, strength: float, rng: random.Random) -> None:
    """Draws a lantern centred on x, y (final pixels), h tall, tilted a little, at strength 0-1."""
    light, paper = _lantern(max(12, round(h * S / 4) * 4))
    if strength < 1:
        light = light.point(lambda v: int(v * strength))
    box = (round(x * S - light.width / 2), round(y * S - light.height / 2))
    box += (box[0] + light.width, box[1] + light.height)
    canvas.paste(ImageChops.screen(canvas.crop(box), light), box)
    paper = paper.rotate(rng.uniform(-9, 9), resample=Image.Resampling.BICUBIC, expand=True)
    if strength < 1:
        paper.putalpha(paper.getchannel("A").point(lambda a: int(a * (0.35 + 0.65 * strength))))
    canvas.paste(paper, (round(x * S - paper.width / 2), round(y * S - paper.height / 2)), paper)


def _scatter(rng: random.Random, count: int, place, apart: float = 1.5) -> list[tuple[float, float, float]]:
    """count lanterns as (x, y, depth) from place(), none crowding another."""
    placed: list[tuple[float, float, float]] = []
    for _ in range(count * 30):
        if len(placed) == count:
            break
        x, y, depth = place()
        h = 34 + depth * 86
        if all((x - px) ** 2 + (y - py) ** 2 > (apart * max(h, 34 + pd * 86)) ** 2 for px, py, pd in placed):
            placed.append((x, y, depth))
    return sorted(placed, key=lambda item: item[2])   # far ones first, near ones over them


def _lanterns(canvas: Image.Image, height: int, header_h: int, rng: random.Random) -> None:
    # Two rising flocks either side of the title, far ones small and faint.
    count = 8 if header_h >= HEADER_H else 3
    for side in (-1, 1):
        flock = _scatter(rng, count, lambda: (W / 2 + side * rng.uniform(575, 850), rng.uniform(46, header_h - 70), rng.random()))
        for x, y, depth in flock:
            _float_lantern(canvas, x, y, 34 + depth * 86, 0.4 + depth * 0.6, rng)
    # A few drifting up the margins beside the wishes, and a last flock at the sign-off.
    y = header_h + 120
    while y < height - FOOTER_H:
        side = rng.choice((-1, 1))
        _float_lantern(canvas, W / 2 + side * (W / 2 - rng.uniform(26, 52)), y, rng.uniform(26, 44), rng.uniform(0.5, 0.85), rng)
        y += rng.uniform(260, 520)
    for side in (-1, 1):
        flock = _scatter(rng, 4, lambda: (W / 2 + side * rng.uniform(600, 840), height - rng.uniform(56, FOOTER_H - 40), rng.random() * 0.6))
        for x, y, depth in flock:
            _float_lantern(canvas, x, y, 34 + depth * 86, 0.4 + depth * 0.6, rng)


# ---- lettering and ornaments -------------------------------------------------------------------

def _foil(canvas: Image.Image, cx: float, baseline: float, text: str, size: float, *, tracking: float = 0,
          colours=FOIL, glow=(255, 170, 92), glow_strength: float = 0.55) -> None:
    """Gold-foil lettering centred on cx with its baseline at baseline (final pixels)."""
    font = _font("title", size)
    gap = tracking * S
    widths = [font.getlength(ch) for ch in text]
    total = sum(widths) + gap * (len(text) - 1)
    ascent, descent = font.getmetrics()
    pad = round(size * S * 0.5)
    tile = (round(total) + 2 * pad, ascent + descent + 2 * pad)
    mask = Image.new("L", tile, 0)
    draw = ImageDraw.Draw(mask)
    x = pad
    for ch, w in zip(text, widths):
        draw.text((x, pad + ascent), ch, font=font, fill=255, anchor="ls")
        x += w + gap

    cap = size * S * 0.74   # Cinzel's capitals
    ys = np.clip((np.arange(tile[1], dtype=np.float32) - (pad + ascent - cap)) / cap, 0, 1)
    stops = np.array(colours, dtype=np.float32)
    ramp = np.stack([np.interp(ys, [0, 0.52, 1], stops[:, c]) for c in range(3)], axis=1)
    fill = Image.fromarray(np.repeat(ramp[:, None, :], tile[0], axis=1).astype(np.uint8), "RGB")

    left, top = round(cx * S - total / 2) - pad, round(baseline * S) - ascent - pad
    shadow = mask.filter(ImageFilter.GaussianBlur(size * S * 0.05))
    canvas.paste((6, 3, 16), (left, top + round(size * S * 0.05)), shadow.point(lambda a: int(a * 0.75)))
    halo = mask.filter(ImageFilter.GaussianBlur(size * S * 0.16))
    canvas.paste(glow, (left, top), halo.point(lambda a: int(a * glow_strength)))
    canvas.paste(fill, (left, top), mask)


def _spaced(draw, cx: float, baseline: float, text: str, role: str, size: float, fill, tracking: float,
            sparks: bool = False) -> None:
    """Letter-spaced small text centred on cx (final pixels), with a spark either side if asked."""
    gap = tracking * S
    glyphs = [(_font(r, size), ch) for r, part, _colour in _runs(text, role) for ch in part]
    total = sum(font.getlength(ch) for font, ch in glyphs) + gap * (len(glyphs) - 1)
    x = cx * S - total / 2
    if sparks:
        for side in (-1, 1):
            _sparkle(draw, cx * S + side * (total / 2 + size * S * 1.3), (baseline - size * 0.36) * S, size * S * 0.42, fill)
    for font, ch in glyphs:
        draw.text((x, baseline * S), ch, font=font, fill=fill, anchor="ls")
        x += font.getlength(ch) + gap


def _flourish(draw, cx: float, y: float, half: float, colour=GOLD) -> None:
    """A rule that fades out either side of three small diamonds."""
    cx, y, half = cx * S, y * S, half * S
    start, steps = 44 * S, 48
    for i in range(steps):
        a, b = start + (half - start) * i / steps, start + (half - start) * (i + 1) / steps
        alpha = int(210 * (1 - i / steps) ** 1.6)
        for side in (-1, 1):
            draw.line((cx + side * a, y, cx + side * b, y), fill=(*colour, alpha), width=S + 1)
    for dx, r in ((0, 9 * S), (-26 * S, 4.5 * S), (26 * S, 4.5 * S)):
        draw.polygon(((cx + dx, y - r), (cx + dx + r, y), (cx + dx, y + r), (cx + dx - r, y)), fill=(*colour, 235))


# ---- the wishes ----------------------------------------------------------------------------------

def _avatar(wish: dict, accent, size: int) -> Image.Image:
    """The wisher's avatar as a circle, or their initial on their accent colour."""
    picture = None
    if wish.get("avatar"):
        try:
            with Image.open(io.BytesIO(wish["avatar"])) as source:
                picture = source.convert("RGB").resize((size, size), Image.Resampling.LANCZOS)
        except Exception:
            picture = None
    if picture is None:
        ys = np.linspace(0, 1, size, dtype=np.float32)[:, None, None]
        light, dark = np.array(accent, np.float32), np.array(accent, np.float32) * 0.45
        picture = Image.fromarray(np.repeat(light + (dark - light) * ys, size, axis=1).astype(np.uint8), "RGB")
        initial = next((ch for ch in str(wish.get("name") or "") if ch.isalnum()), "♥").upper()
        role = "bold" if _has_glyph("bold", initial) else "emoji"
        ImageDraw.Draw(picture).text((size / 2, size / 2), initial, font=_font(role, size / S * 0.5),
                                     fill=(20, 12, 40), anchor="mm")
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, size - 1, size - 1), fill=255)
    picture = picture.convert("RGBA")
    picture.putalpha(mask)
    return picture


def _layout(wishes: list[dict], top: int) -> tuple[list[dict], int]:
    """Where each wish goes: always the shortest column, so they read across in the order they came."""
    text_w = COLUMN_W - 2 * PAD
    bottoms = [top] * COLUMNS
    notes = []
    for i, wish in enumerate(wishes):
        lines = _wrap(str(wish.get("message") or ""), "body", BODY_SIZE, text_w)
        h = PAD + AVATAR + 22 + len(lines) * LINE_H + PAD - 8
        column = min(range(COLUMNS), key=lambda c: bottoms[c])
        notes.append(dict(wish=wish, lines=lines, x=MARGIN + column * (COLUMN_W + GAP), y=bottoms[column], h=h,
                          accent=ACCENTS[i % len(ACCENTS)]))
        bottoms[column] += h + GAP
    return notes, max(bottoms) - GAP


def _notes(canvas: Image.Image, notes: list[dict]) -> None:
    shadow = Image.new("L", (canvas.width // S, canvas.height // S), 0)
    sd = ImageDraw.Draw(shadow)
    for n in notes:
        sd.rounded_rectangle((n["x"] - 2, n["y"] + 10, n["x"] + COLUMN_W + 2, n["y"] + n["h"] + 16), radius=26, fill=255)
    shadow = shadow.filter(ImageFilter.GaussianBlur(16)).resize(canvas.size, Image.Resampling.BILINEAR)
    canvas.paste((4, 2, 14), (0, 0), shadow.point(lambda a: int(a * 0.62)))

    draw = ImageDraw.Draw(canvas, "RGBA")
    for n in notes:
        x, y, h, accent = n["x"] * S, n["y"] * S, n["h"] * S, n["accent"]
        w = COLUMN_W * S
        draw.rounded_rectangle((x, y, x + w, y + h), radius=24 * S, fill=(26, 19, 54, 196))
        draw.rounded_rectangle((x, y, x + w, y + h), radius=24 * S, outline=(*accent, 120), width=S + 1)
        draw.rounded_rectangle((x + 5 * S, y + 5 * S, x + w - 5 * S, y + h - 5 * S), radius=20 * S,
                               outline=(255, 255, 255, 16), width=S)
        # a big faint closing quote in the corner, and a spark on the rim
        draw.text((x + w - 22 * S, y + 4 * S), "”", font=_font("title", 120), fill=(*accent, 38), anchor="ra")
        _sparkle(draw, x + w - 30 * S, y, 9 * S, (*accent, 235))

        ax, ay, size = x + PAD * S, y + PAD * S, AVATAR * S
        draw.ellipse((ax - 5 * S, ay - 5 * S, ax + size + 5 * S, ay + size + 5 * S), outline=(*accent, 230), width=S + 1)
        canvas.paste(avatar := _avatar(n["wish"], accent, size), (ax, ay), avatar)

        name_x = ax + size + 18 * S
        name = _fit(str(n["wish"].get("name") or "A friend"), "bold", NAME_SIZE, COLUMN_W - 2 * PAD - AVATAR - 18 - 40)
        light = tuple(round(c + (255 - c) * 0.25) for c in accent)
        _draw_text(draw, name_x, ay + size / 2 + NAME_SIZE * S * 0.34, name, "bold", NAME_SIZE, (*light, 255))

        baseline = ay + size + 22 * S + BODY_SIZE * S
        for line in n["lines"]:
            _draw_text(draw, x + PAD * S, baseline, line, "body", BODY_SIZE, (*CREAM, 255))
            baseline += LINE_H * S


# ---- the card ------------------------------------------------------------------------------------

def _possessive_free(name: str) -> str:
    return " ".join(str(name or "").split()) or "You"


def render_card(recipient: str, wishes: list[dict], *, total: int | None = None, page: int = 1, pages: int = 1,
                signature: str = "With love, from all of us at Fable") -> Image.Image:
    """One page of the card as an RGB image."""
    recipient = _possessive_free(recipient)
    total = len(wishes) if total is None else total
    header_h = HEADER_H if page == 1 else SHORT_HEADER_H
    notes, bottom = _layout(wishes, header_h)
    height = bottom + FOOTER_H
    rng = random.Random(f"{recipient}:{total}:{page}")

    canvas = _sky(height, header_h, rng).resize((W * S, height * S), Image.Resampling.BICUBIC)
    _stars(canvas, header_h, rng)
    _lanterns(canvas, height, header_h, rng)
    draw = ImageDraw.Draw(canvas, "RGBA")

    if page == 1:
        _spaced(draw, W / 2, 104, "THE REALM OF FABLE CELEBRATES", "bold", 24, (*GOLD, 215), 7, sparks=True)
        _foil(canvas, W / 2, 218, "HAPPY BIRTHDAY", 88, tracking=9)
        size = 168
        while size > 70 and _font("title", size).getlength(recipient) > (W - 520) * S:
            size -= 6
        _foil(canvas, W / 2, 232 + size * 0.98, recipient, size, tracking=2,
              colours=((255, 250, 232), (255, 214, 150), (236, 138, 120)), glow=(255, 138, 110), glow_strength=0.7)
        _flourish(draw, W / 2, 458, 330)
        wishes_line = f"{total} wishes, sent across the realm just for you" if total != 1 else "A wish, sent across the realm just for you"
        _spaced(draw, W / 2, 516, wishes_line, "body", 30, (*CREAM, 235), 1.5)
    else:
        _foil(canvas, W / 2, 128, f"More wishes for {recipient}", 66, tracking=3)
        _flourish(draw, W / 2, 176, 300)

    _notes(canvas, notes)

    draw = ImageDraw.Draw(canvas, "RGBA")
    foot = height - FOOTER_H
    _flourish(draw, W / 2, foot + 78, 330)
    _foil(canvas, W / 2, foot + 152, signature, 50, tracking=2, glow_strength=0.4)
    tail = f"{total} wishes" if total != 1 else "1 wish"
    if pages > 1:
        tail += f"  ·  page {page} of {pages}"
    _spaced(draw, W / 2, foot + 204, tail.upper(), "bold", 20, (*MUTED, 220), 5, sparks=True)

    return canvas.resize((W, height), Image.Resampling.LANCZOS)


def encode(image: Image.Image) -> tuple[bytes, str]:
    """The image as PNG, or as a high-quality JPEG when the PNG would be too big for Discord."""
    out = io.BytesIO()
    image.save(out, "PNG", optimize=True)
    if out.tell() <= MAX_BYTES:
        return out.getvalue(), "png"
    out = io.BytesIO()
    image.save(out, "JPEG", quality=94, subsampling=0, optimize=True)
    return out.getvalue(), "jpg"


def render_cards(recipient: str, wishes: list[dict], *, per_page: int = PER_PAGE,
                 signature: str = "With love, from all of us at Fable") -> list[tuple[bytes, str]]:
    """Every page of the card: (image bytes, filename) each, PER_PAGE wishes a page."""
    chunks = [wishes[i:i + per_page] for i in range(0, len(wishes), per_page)] or [[]]
    out = []
    for i, chunk in enumerate(chunks, start=1):
        data, ext = encode(render_card(recipient, chunk, total=len(wishes), page=i, pages=len(chunks), signature=signature))
        out.append((data, f"birthday-wishes-{i}.{ext}" if len(chunks) > 1 else f"birthday-wishes.{ext}"))
    return out

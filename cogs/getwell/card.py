"""The get-well card: every approved wish on one picture, under a sunrise with drifting petals.

`render_cards(recipient, wishes)` returns one image per PER_PAGE wishes (bytes and a filename
each), the same contract as the birthday card in cogs/wish/card.py. A wish is a dict with "name",
"message" and optionally "avatar" (image bytes); a wish without a usable avatar gets a coloured
initial instead.

The text, emoji, avatar, wrapping, column layout and PNG/JPEG handling are the birthday card's,
imported from there. Only the picture is new: a sky that goes from deep rose to peach and gold,
petals and motes of light instead of lanterns, and warm plum tiles. Everything is drawn at twice
the final size and scaled down. PIL and numpy only (no Discord), so tests and the sample script
can share it.
"""
from __future__ import annotations

import math
import random
from functools import lru_cache

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from cogs.wish.card import (  # noqa: F401  (MAX_BYTES and PER_PAGE are re-exported for the tests)
    ACCENTS, AVATAR, BODY_SIZE, COLUMN_W, CREAM, FOOTER_H, GAP, HEADER_H, LINE_H, MARGIN, MAX_BYTES, NAME_SIZE,
    PAD, PER_PAGE, S, SHORT_HEADER_H, W, _avatar, _draw_text, _fit, _flourish, _foil, _font, _layout, _sparkle,
    _spaced, encode,
)

PLUM = (88, 34, 70)                      # the ink used on the bright part of the sky
PETAL_LIGHT, PETAL_DEEP = (255, 228, 232), (238, 128, 158)
WARM_FOIL = ((255, 250, 232), (255, 214, 150), (236, 138, 120))   # the recipient's name, as on the birthday card
SIGNATURE = "Rest up. We're all rooting for you."


# ---- the sky -----------------------------------------------------------------------------------

def _dawn(height: int, header_h: int, rng: random.Random) -> Image.Image:
    """The sky behind everything, at final size: deep plum-rose at the top, rose through the middle,
    peach and then gold at the horizon, with a sun glow behind the sign-off and a warm glow
    behind the title. Darker at the edges."""
    ys = np.linspace(0, 1, height, dtype=np.float32)[:, None]
    xs = np.linspace(0, 1, W, dtype=np.float32)[None, :]
    stops = np.array([[46, 20, 60], [104, 40, 84], [180, 78, 100], [232, 134, 116], [250, 196, 130]], dtype=np.float32)
    at = np.array([0.0, 0.30, 0.62, 0.86, 1.0], dtype=np.float32)
    sky = np.stack([np.interp(ys[:, 0], at, stops[:, c]) for c in range(3)], axis=1)[:, None, :]
    sky = np.repeat(sky, W, axis=1)

    def glow(cx, cy, rx, ry, colour, power=1.6):
        dist = ((xs * W - cx) / rx) ** 2 + ((ys * height - cy) / ry) ** 2
        return np.clip(1 - dist, 0, 1)[..., None] ** power * np.array(colour, dtype=np.float32)

    sky += glow(W / 2, header_h * 0.50, 980, header_h * 0.95, (96, 44, 52))
    sky += glow(W / 2, header_h * 0.52, 520, header_h * 0.55, (70, 40, 26), 2.2)
    sky += glow(W / 2, height - FOOTER_H * 0.35, 1100, FOOTER_H * 1.7, (70, 54, 30), 1.4)   # the sun, just below the sign-off
    edge = np.clip(np.abs(xs - 0.5) * 2, 0, 1) ** 3
    sky *= (1 - 0.26 * edge)[..., None]
    sky += np.random.default_rng(rng.randrange(1 << 30)).uniform(-1.3, 1.3, sky.shape)   # hides banding
    image = Image.fromarray(np.clip(sky, 0, 255).astype(np.uint8), "RGB")

    clouds = Image.new("RGBA", (W, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(clouds)
    for _ in range(max(22, height // 100)):
        r = rng.randint(50, 190)
        x, y = rng.randint(-60, W + 60), rng.randint(-60, height + 60)
        draw.ellipse((x - r, y - r, x + r, y + r), fill=(*rng.choice(ACCENTS), rng.randint(8, 20)))
    blurred = clouds.filter(ImageFilter.GaussianBlur(30))
    image.paste(blurred, (0, 0), blurred)
    return image


def _rays(canvas: Image.Image, height: int, rng: random.Random) -> None:
    """Faint beams of light fanning up from the horizon behind the sign-off."""
    layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    cx, cy = W / 2 * S, (height - FOOTER_H * 0.2) * S
    reach = height * S * 1.25
    for i in range(11):
        angle = math.radians(-84 + i * 16.8 + rng.uniform(-3, 3))
        spread = math.radians(rng.uniform(2.2, 4.6))
        draw.polygon(((cx, cy),
                      (cx + reach * math.sin(angle - spread), cy - reach * math.cos(angle - spread)),
                      (cx + reach * math.sin(angle + spread), cy - reach * math.cos(angle + spread))),
                     fill=(255, 226, 170, rng.randint(9, 17)))
    layer = layer.filter(ImageFilter.GaussianBlur(12 * S))
    canvas.paste(layer, (0, 0), layer)


def _motes(canvas: Image.Image, rng: random.Random) -> None:
    """Soft points of light, thicker towards the horizon where the sun is."""
    draw = ImageDraw.Draw(canvas, "RGBA")
    width, height = canvas.size
    for _ in range(height // (S * 16)):
        y = int(height * (1 - rng.random() ** 1.5))
        x = rng.randrange(width)
        r = rng.choice((2, 2, 3, 3, 4, 6)) * S
        tint = rng.choice(((255, 244, 214), (255, 226, 190), (255, 214, 214)))
        for ring, alpha in ((3.0, 14), (1.9, 34), (1.0, rng.randint(110, 215))):
            rr = r * ring / 2
            draw.ellipse((x - rr, y - rr, x + rr, y + rr), fill=(*tint, alpha))
    for _ in range(max(14, height // (S * 300))):
        _sparkle(draw, rng.randrange(width), int(height * rng.random() ** 1.3), rng.randint(9, 20) * S, (255, 242, 214, rng.randint(120, 220)))


@lru_cache(maxsize=48)
def _petal(h: int) -> Image.Image:
    """A petal h pixels tall (at the drawing scale): a teardrop, pointed at the top, pale pink
    fading to a deeper rose, with a faint rib down the middle."""
    w = max(8, round(h * 0.62))
    pad = 2
    t = np.linspace(0, 2 * math.pi, 96)
    xs = np.sin(t) * np.sin(t / 2) / 0.75
    points = [(pad + w / 2 + (w / 2) * x, pad + h / 2 - (h / 2) * math.cos(a)) for x, a in zip(xs, t)]
    mask = Image.new("L", (w + 2 * pad, h + 2 * pad), 0)
    ImageDraw.Draw(mask).polygon(points, fill=255)
    ys = np.clip((np.arange(h + 2 * pad, dtype=np.float32) - pad) / h, 0, 1)[:, None, None]
    light, deep = np.array(PETAL_LIGHT, np.float32), np.array(PETAL_DEEP, np.float32)
    body = np.repeat(light + (deep - light) * ys ** 1.3, w + 2 * pad, axis=1)
    petal = Image.fromarray(body.astype(np.uint8), "RGB").convert("RGBA")
    rib = ImageDraw.Draw(petal)
    rib.line((pad + w / 2, pad + h * 0.12, pad + w / 2, pad + h * 0.84), fill=(210, 92, 128, 70), width=max(1, h // 28))
    petal.putalpha(mask.filter(ImageFilter.GaussianBlur(0.6)))
    return petal


def _petals(canvas: Image.Image, height: int, header_h: int, rng: random.Random) -> None:
    """Petals drifting across the whole page. Most are drawn before the wish tiles, so they slip
    between and behind them; a few small ones are added in the margins afterwards (see _margin_petals)."""
    for _ in range(max(40, height // 34)):
        x = rng.uniform(-20, W + 20)
        y = rng.uniform(-20, height + 20)
        size = rng.uniform(15, 46)
        if abs(x - W / 2) < 620 and y < header_h - 40:
            continue   # keep the lettering clear
        _lay_petal(canvas, x, y, size, rng)


def _margin_petals(canvas: Image.Image, height: int, rng: random.Random) -> None:
    for _ in range(max(10, height // 150)):
        side = rng.choice((-1, 1))
        _lay_petal(canvas, W / 2 + side * (W / 2 - rng.uniform(8, 44)), rng.uniform(0, height), rng.uniform(14, 30), rng)


def _lay_petal(canvas: Image.Image, x: float, y: float, size: float, rng: random.Random) -> None:
    petal = _petal(max(12, round(size * S / 2) * 2)).rotate(rng.uniform(0, 360), resample=Image.Resampling.BICUBIC, expand=True)
    strength = rng.uniform(0.35, 0.85)
    petal.putalpha(petal.getchannel("A").point(lambda a: int(a * strength)))
    canvas.paste(petal, (round(x * S - petal.width / 2), round(y * S - petal.height / 2)), petal)


# ---- lettering -----------------------------------------------------------------------------------

def _ink(canvas: Image.Image, cx: float, baseline: float, text: str, size: float, *, tracking: float = 0) -> None:
    """Deep plum lettering with a soft light halo, for the bright part of the sky (final pixels)."""
    font = _font("title", size)
    gap = tracking * S
    widths = [font.getlength(ch) for ch in text]
    total = sum(widths) + gap * (len(text) - 1)
    ascent, descent = font.getmetrics()
    pad = round(size * S * 0.5)
    mask = Image.new("L", (round(total) + 2 * pad, ascent + descent + 2 * pad), 0)
    draw = ImageDraw.Draw(mask)
    x = pad
    for ch, w in zip(text, widths):
        draw.text((x, pad + ascent), ch, font=font, fill=255, anchor="ls")
        x += w + gap
    left, top = round(cx * S - total / 2) - pad, round(baseline * S) - ascent - pad
    halo = mask.filter(ImageFilter.GaussianBlur(size * S * 0.2))
    canvas.paste((255, 236, 198), (left, top), halo.point(lambda a: int(a * 0.8)))
    canvas.paste(PLUM, (left, top), mask)


# ---- the wishes ----------------------------------------------------------------------------------

def _notes(canvas: Image.Image, notes: list[dict]) -> None:
    shadow = Image.new("L", (canvas.width // S, canvas.height // S), 0)
    sd = ImageDraw.Draw(shadow)
    for n in notes:
        sd.rounded_rectangle((n["x"] - 2, n["y"] + 10, n["x"] + COLUMN_W + 2, n["y"] + n["h"] + 16), radius=26, fill=255)
    shadow = shadow.filter(ImageFilter.GaussianBlur(16)).resize(canvas.size, Image.Resampling.BILINEAR)
    canvas.paste((40, 10, 30), (0, 0), shadow.point(lambda a: int(a * 0.5)))

    draw = ImageDraw.Draw(canvas, "RGBA")
    for n in notes:
        x, y, h, accent = n["x"] * S, n["y"] * S, n["h"] * S, n["accent"]
        w = COLUMN_W * S
        draw.rounded_rectangle((x, y, x + w, y + h), radius=24 * S, fill=(50, 21, 52, 206))
        draw.rounded_rectangle((x, y, x + w, y + h), radius=24 * S, outline=(*accent, 130), width=S + 1)
        draw.rounded_rectangle((x + 5 * S, y + 5 * S, x + w - 5 * S, y + h - 5 * S), radius=20 * S,
                               outline=(255, 255, 255, 18), width=S)
        # a big faint closing quote in the corner, and a spark on the rim
        draw.text((x + w - 22 * S, y + 4 * S), "”", font=_font("title", 120), fill=(*accent, 40), anchor="ra")
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

def _clean_name(name: str) -> str:
    return " ".join(str(name or "").split()) or "Friend"


def render_card(recipient: str, wishes: list[dict], *, total: int | None = None, page: int = 1, pages: int = 1,
                signature: str = SIGNATURE) -> Image.Image:
    """One page of the card as an RGB image."""
    recipient = _clean_name(recipient)
    total = len(wishes) if total is None else total
    header_h = HEADER_H if page == 1 else SHORT_HEADER_H
    notes, bottom = _layout(wishes, header_h)
    height = bottom + FOOTER_H
    rng = random.Random(f"getwell:{recipient}:{total}:{page}")

    canvas = _dawn(height, header_h, rng).resize((W * S, height * S), Image.Resampling.BICUBIC)
    _rays(canvas, height, rng)
    _motes(canvas, rng)
    _petals(canvas, height, header_h, rng)
    draw = ImageDraw.Draw(canvas, "RGBA")

    if page == 1:
        _spaced(draw, W / 2, 104, "THE REALM OF FABLE SENDS ITS LOVE", "bold", 24, (255, 232, 196, 225), 7, sparks=True)
        _foil(canvas, W / 2, 218, "GET WELL SOON", 88, tracking=9)
        size = 168
        while size > 70 and _font("title", size).getlength(recipient) > (W - 520) * S:
            size -= 6
        _foil(canvas, W / 2, 232 + size * 0.98, recipient, size, tracking=2, colours=WARM_FOIL, glow=(255, 150, 120), glow_strength=0.7)
        _flourish(draw, W / 2, 458, 330, colour=(255, 226, 170))
        line = f"{total} wishes from your friends across Fable" if total != 1 else "A wish from your friends across Fable"
        _spaced(draw, W / 2, 516, line, "body", 30, (*CREAM, 240), 1.5)
    else:
        _foil(canvas, W / 2, 128, f"More wishes for {recipient}", 66, tracking=3)
        _flourish(draw, W / 2, 176, 300, colour=(255, 226, 170))

    _notes(canvas, notes)
    _margin_petals(canvas, height, rng)

    draw = ImageDraw.Draw(canvas, "RGBA")
    foot = height - FOOTER_H
    _flourish(draw, W / 2, foot + 78, 330, colour=PLUM)
    _ink(canvas, W / 2, foot + 152, signature, 50, tracking=2)
    tail = f"{total} wishes" if total != 1 else "1 wish"
    if pages > 1:
        tail += f"  ·  page {page} of {pages}"
    _spaced(draw, W / 2, foot + 204, tail.upper(), "bold", 20, (*PLUM, 235), 5, sparks=True)

    return canvas.resize((W, height), Image.Resampling.LANCZOS)


def render_cards(recipient: str, wishes: list[dict], *, per_page: int = PER_PAGE,
                 signature: str = SIGNATURE) -> list[tuple[bytes, str]]:
    """Every page of the card: (image bytes, filename) each, PER_PAGE wishes a page."""
    chunks = [wishes[i:i + per_page] for i in range(0, len(wishes), per_page)] or [[]]
    out = []
    for i, chunk in enumerate(chunks, start=1):
        data, ext = encode(render_card(recipient, chunk, total=len(wishes), page=i, pages=len(chunks), signature=signature))
        out.append((data, f"getwell_card_{i}.{ext}" if len(chunks) > 1 else f"getwell_card.{ext}"))
    return out

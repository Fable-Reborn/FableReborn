"""Pillow renderer for the companion select screen.

The focused companion fills the right side (its silhouette with a rim of
alignment light while locked) with its details on the left, and the whole
roster runs along a diagonal band of slanted tiles at the bottom. Rendering is
pure and cached per state, so it can run in a worker thread.
"""

from functools import lru_cache
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont, ImageOps

from .roster import BY_KEY, COMPANIONS, EVIL, GOOD

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ART_DIR = PROJECT_ROOT / "assets" / "companions"
FONT_DIR = PROJECT_ROOT / "assets" / "profile_themes" / "fonts"

WIDTH, HEIGHT = 1600, 900
MARGIN = 64
TEXT = (240, 234, 224)
MUTED = (152, 148, 162)
INK = (10, 10, 15)
GOLD = (236, 190, 92)
ALIGNMENT_COLOURS = {GOOD: (96, 178, 255), EVIL: (222, 58, 70)}

PORTRAIT_H = 1010
TILE_W, TILE_H, TILE_SKEW, TILE_GAP = 132, 206, 46, 14
FOCUS_W, FOCUS_H, FOCUS_PAD = 168, 262, 26
STRIP_CENTRE = 742
MAX_TILES = 9


# ---- assets ------------------------------------------------------------------
@lru_cache(maxsize=32)
def _font(name, size):
    for candidate in (FONT_DIR / name, Path("C:/Windows/Fonts/arialbd.ttf"),
                      Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")):
        try:
            return ImageFont.truetype(str(candidate), size=size)
        except OSError:
            continue
    return ImageFont.load_default()


def display(size):
    return _font("Cinzel.ttf", size)


def bold(size):
    return _font("Lato-Bold.ttf", size)


def regular(size):
    return _font("Lato-Regular.ttf", size)


@lru_cache(maxsize=16)
def _art(key, kind):
    """The companion's portrait or silhouette as RGBA, or None if it's missing."""
    path = ART_DIR / key / f"{kind}.png"
    try:
        with Image.open(path) as source:
            return source.convert("RGBA")
    except (OSError, ValueError):
        return None


@lru_cache(maxsize=16)
def _scaled(key, kind, height):
    art = _art(key, kind)
    if art is None:
        return None
    width = round(art.width * height / art.height)
    return art.resize((width, height), Image.LANCZOS)


# ---- drawing helpers ---------------------------------------------------------
def _mix(colour, other, amount):
    return tuple(round(a + (b - a) * amount) for a, b in zip(colour, other))


def _wrap(draw, text, font, max_width):
    lines, current = [], ""
    for word in text.split():
        trial = f"{current} {word}".strip()
        if current and draw.textlength(trial, font=font) > max_width:
            lines.append(current)
            current = word
        else:
            current = trial
    if current:
        lines.append(current)
    return lines


def _slant(width, height, skew):
    return [(skew, 0), (width + skew, 0), (width, height), (0, height)]


def _crop_focus(art, focus, zoom, size):
    """Crop `art` around its focus point to the aspect of `size`, then resize."""
    width, height = size
    crop_h = art.height * zoom
    crop_w = crop_h * width / height
    if crop_w > art.width:
        crop_w, crop_h = art.width, art.width * height / width
    cx, cy = focus[0] * art.width, focus[1] * art.height
    left = min(max(0, cx - crop_w / 2), art.width - crop_w)
    top = min(max(0, cy - crop_h / 2), art.height - crop_h)
    return art.crop((round(left), round(top), round(left + crop_w), round(top + crop_h))).resize(size, Image.LANCZOS)


def _layer(canvas, paint, *args):
    """Run `paint(draw, *args)` on a clear layer and composite it, so translucent fills blend.

    Drawing straight onto an RGBA image replaces pixels (alpha included) instead of blending.
    """
    layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    paint(ImageDraw.Draw(layer), *args)
    canvas.alpha_composite(layer)


def _glow(art, colour, blur, strength=2.0, body=None):
    """`art` (or a flat `body` colour in its shape) over a soft glow of `colour` around its outline."""
    alpha = art.getchannel("A")
    out = Image.new("RGBA", art.size, colour + (0,))
    out.putalpha(alpha.filter(ImageFilter.GaussianBlur(blur)).point(lambda v: min(255, round(v * strength))))
    if body is None:
        out.alpha_composite(art)
    else:
        shape = Image.new("RGBA", art.size, body + (0,))
        shape.putalpha(alpha)
        out.alpha_composite(shape)
    return out


def _gradient(size, top, bottom):
    ramp = Image.linear_gradient("L").resize(size)
    return Image.composite(Image.new("RGBA", size, bottom + (255,)), Image.new("RGBA", size, top + (255,)), ramp)


def _padlock(draw, centre, size, colour):
    x, y = centre
    half = size // 2
    shackle = size // 3
    draw.arc((x - shackle, y - half - shackle, x + shackle, y - half + shackle + 4), 180, 360,
             fill=colour, width=max(3, size // 9))
    draw.rounded_rectangle((x - half, y - half + 4, x + half, y + half), radius=size // 7, fill=colour)
    draw.ellipse((x - size // 10, y - size // 12, x + size // 10, y + size // 12 + 2), fill=INK)


def _pill(draw, xy, label, fill, text_colour=INK):
    font = bold(17)
    x, y = xy
    width = round(draw.textlength(label, font=font)) + 32
    draw.rounded_rectangle((x, y, x + width, y + 34), radius=17, fill=fill)
    draw.text((x + width // 2, y + 17), label, font=font, fill=text_colour, anchor="mm")
    return x + width + 10


# ---- layers --------------------------------------------------------------------
def _background(accent):
    fade = Image.linear_gradient("L").rotate(90).resize((WIDTH, HEIGHT))
    canvas = Image.composite(Image.new("RGBA", (WIDTH, HEIGHT), _mix(accent, INK, 0.78) + (255,)),
                             Image.new("RGBA", (WIDTH, HEIGHT), INK + (255,)), fade)

    glow = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow)
    glow_draw.ellipse((880, -160, 1720, 760), fill=accent + (120,))
    glow_draw.ellipse((-260, 120, 520, 760), fill=_mix(accent, INK, 0.4) + (60,))
    canvas.alpha_composite(glow.filter(ImageFilter.GaussianBlur(120)))

    def slashes(draw):
        draw.polygon([(1010, 0), (1150, 0), (790, HEIGHT), (650, HEIGHT)], fill=accent + (46,))
        draw.polygon([(1172, 0), (1192, 0), (832, HEIGHT), (812, HEIGHT)], fill=accent + (70,))

    _layer(canvas, slashes)
    return canvas


@lru_cache(maxsize=4)
def _edge_fade(size):
    """A mask that softens the portrait's cut-off left and bottom edges into the scene."""
    width, height = size
    left = Image.new("L", size, 255)
    left.paste(Image.linear_gradient("L").rotate(90).resize((round(width * 0.2), height)), (0, 0))
    bottom = Image.new("L", size, 255)
    bottom.paste(ImageOps.invert(Image.linear_gradient("L").resize((width, 260))), (0, height - 260))
    return ImageChops.multiply(left, bottom)


@lru_cache(maxsize=8)
def _hero_art(key, unlocked, colour):
    if unlocked:
        art = _scaled(key, "portrait", PORTRAIT_H)
        art = _glow(art, colour, 22, 0.9) if art is not None else None
    else:
        silhouette = _scaled(key, "silhouette", PORTRAIT_H)
        art = _glow(silhouette, colour, 14, body=(6, 6, 10)) if silhouette is not None else None
    if art is not None:
        art.putalpha(ImageChops.multiply(art.getchannel("A"), _edge_fade(art.size)))
    return art


def _hero(canvas, companion, unlocked, colour):
    art = _hero_art(companion.key, unlocked, companion.accent if unlocked else colour)
    if art is not None:
        canvas.alpha_composite(art, (WIDTH - art.width + 40, -60))


def _header(draw, accent, unlocked_count):
    draw.text((MARGIN, 40), "SELECT COMPANION", font=display(46), fill=TEXT)
    draw.line((0, 104, 900, 104), fill=accent + (230,), width=3)
    draw.line((900, 104, 1010, 84), fill=accent + (230,), width=3)
    label = f"{unlocked_count} / {len(COMPANIONS)} UNLOCKED"
    font = bold(18)
    width = round(draw.textlength(label, font=font)) + 36
    x = WIDTH - MARGIN - width
    draw.rounded_rectangle((x, 44, x + width, 82), radius=19, fill=INK + (200,), outline=accent + (200,), width=2)
    draw.text((x + width // 2, 63), label, font=font, fill=TEXT, anchor="mm")


def _details(draw, companion, unlocked, selected, colour):
    top = 150
    for x in range(0, 980, 4):
        draw.rectangle((x, top, x + 3, top + 128), fill=(255, 255, 255, round(30 * (1 - x / 980))))
    draw.rectangle((0, top, 10, top + 128), fill=colour)

    name = companion.name if unlocked else "???"
    draw.text((MARGIN, top + 64), name, font=display(92), fill=TEXT, anchor="lm", stroke_width=2, stroke_fill=INK)

    y = top + 150
    title = companion.title if unlocked else "Unknown companion"
    draw.text((MARGIN, y), title.upper(), font=bold(24), fill=_mix(colour, TEXT, 0.45))

    y += 48
    x = _pill(draw, (MARGIN, y), companion.alignment.upper(), colour)
    if selected:
        x = _pill(draw, (x, y), "SELECTED", GOLD)
    if not unlocked:
        _pill(draw, (x, y), "LOCKED", (60, 58, 70), TEXT)

    y += 62
    font = regular(25)
    text = companion.description if unlocked else f"\u201c{companion.hint}\u201d"
    for line in _wrap(draw, text, font, 720):
        draw.text((MARGIN, y), line, font=font, fill=_mix(TEXT, MUTED, 0.25) if unlocked else MUTED)
        y += 36
    if not unlocked:
        draw.text((MARGIN, y + 10), "Unlock this companion to learn their story.", font=bold(19),
                  fill=_mix(MUTED, INK, 0.25))


@lru_cache(maxsize=32)
def _tile(key, unlocked, size, focused):
    companion = BY_KEY[key]
    width, height = size
    box = (width + TILE_SKEW, height)
    outline = _slant(width, height, TILE_SKEW)
    if unlocked:
        fill = _gradient(box, _mix(companion.accent, (255, 255, 255), 0.15), _mix(companion.accent, INK, 0.75))
        art = _art(key, "portrait")
    else:
        light = _mix(ALIGNMENT_COLOURS[companion.alignment], (200, 200, 210), 0.55)
        fill = _gradient(box, light, _mix(light, INK, 0.65))
        art = _art(key, "silhouette")
    if art is not None:
        fill.alpha_composite(_crop_focus(art, companion.focus, companion.zoom, box))
    if not focused:
        _layer(fill, lambda draw: draw.rectangle((0, 0) + box, fill=(8, 8, 12, 96)))
    if not unlocked:
        _layer(fill, _padlock, (box[0] // 2, height - 34), 30 if focused else 24, (236, 232, 226, 235))

    mask = Image.new("L", box, 0)
    ImageDraw.Draw(mask).polygon(outline, fill=255)
    tile = Image.new("RGBA", box, (0, 0, 0, 0))
    tile.paste(fill, (0, 0), mask)
    ImageDraw.Draw(tile).polygon(outline, outline=GOLD if focused else (196, 192, 202), width=5 if focused else 3)
    return tile


def _strip(canvas, states, index):
    band_top, band_bottom = STRIP_CENTRE - 112, STRIP_CENTRE + 112

    def band(draw):
        draw.polygon([(0, band_top + 40), (WIDTH, band_top - 30), (WIDTH, band_bottom - 30), (0, band_bottom + 40)],
                     fill=(26, 26, 34, 220))
        draw.line((0, band_top + 40, WIDTH, band_top - 30), fill=(255, 255, 255, 60), width=2)
        draw.line((0, band_bottom + 40, WIDTH, band_bottom - 30), fill=(255, 255, 255, 60), width=2)

    _layer(canvas, band)

    count = len(COMPANIONS)
    shown = min(count, MAX_TILES)
    first = min(max(0, index - shown // 2), count - shown)
    # The focused tile gets extra room on each side for its arrows.
    widths = [FOCUS_W + 2 * FOCUS_PAD if i == index else TILE_W for i in range(first, first + shown)]
    x = (WIDTH - sum(widths) - TILE_GAP * (shown - 1) - TILE_SKEW) // 2
    arrows = None
    for offset, i in enumerate(range(first, first + shown)):
        focused = i == index
        size = (FOCUS_W, FOCUS_H) if focused else (TILE_W, TILE_H)
        left = x + FOCUS_PAD if focused else x
        # Follow the band's slope so the row reads as a diagonal line.
        y = STRIP_CENTRE - size[1] // 2 + round(35 - 70 * (left + size[0] / 2) / WIDTH)
        if focused:
            shadow = Image.new("RGBA", (size[0] + TILE_SKEW + 60, size[1] + 60), (0, 0, 0, 0))
            ImageDraw.Draw(shadow).polygon([(px + 30, py + 30) for px, py in _slant(*size, TILE_SKEW)],
                                           fill=GOLD + (170,))
            canvas.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(16)), (left - 30, y - 30))
            arrows = (left + TILE_SKEW // 2, left + size[0] + TILE_SKEW // 2, y + size[1] // 2)
        canvas.alpha_composite(_tile(COMPANIONS[i].key, states[i], size, focused), (left, y))
        x += widths[offset] + TILE_GAP

    draw = ImageDraw.Draw(canvas)
    left_edge, right_edge, mid = arrows
    draw.polygon([(left_edge - 34, mid), (left_edge - 12, mid - 18), (left_edge - 12, mid + 18)], fill=GOLD)
    draw.polygon([(right_edge + 34, mid), (right_edge + 12, mid - 18), (right_edge + 12, mid + 18)], fill=GOLD)


def _footer(draw, index):
    count = len(COMPANIONS)
    y = HEIGHT - 44
    dot_gap = 26
    start = WIDTH - MARGIN - (count - 1) * dot_gap
    for i in range(count):
        cx = start + i * dot_gap
        if i == index:
            draw.rounded_rectangle((cx - 11, y - 6, cx + 11, y + 6), radius=6, fill=GOLD)
        else:
            draw.ellipse((cx - 5, y - 5, cx + 5, y + 5), fill=(255, 255, 255, 110))
    draw.text((start - 30, y), f"{index + 1} / {count}", font=bold(18), fill=MUTED, anchor="rm")


# ---- entry point ---------------------------------------------------------------
@lru_cache(maxsize=64)
def _render(index, states, selected_key):
    companion = COMPANIONS[index]
    unlocked = states[index]
    colour = ALIGNMENT_COLOURS[companion.alignment]
    accent = companion.accent if unlocked else _mix(colour, (60, 60, 70), 0.45)

    canvas = _background(accent)
    _hero(canvas, companion, unlocked, colour)
    _layer(canvas, _header, accent, sum(states))
    _layer(canvas, _details, companion, unlocked, selected_key == companion.key, colour)
    _strip(canvas, states, index)
    _layer(canvas, _footer, index)

    output = BytesIO()
    canvas.convert("RGB").save(output, format="JPEG", quality=90, subsampling=0)
    return output.getvalue()


def render_select_card(index, unlocked_keys, selected_key=None):
    """Render the select screen focused on COMPANIONS[index]. Returns a BytesIO of a JPEG."""
    states = tuple(companion.key in unlocked_keys for companion in COMPANIONS)
    return BytesIO(_render(index, states, selected_key))

"""Drawing kit for the Chronicle cards: the armory and the character sheet.

Everything is laid out in logical pixels and drawn at SS times that size, then
scaled down once at the end. That is what smooths the edges, because Pillow's
shape drawing has no antialiasing of its own.

The base image is RGB and the pen blends, so a translucent fill can never
punch a see-through hole in the finished card.

Fonts are looked up by role. Drop any of these into assets/fonts to restyle
the cards without touching code:

    chronicle-display.ttf    titles and item names
    chronicle-text.ttf       body copy
    chronicle-text-bold.ttf  emphasised body copy
    chronicle-label.ttf      small capitals and captions

Without them the cards use DejaVu, then whatever serif the host has.
"""
from __future__ import annotations

import io
import math
import random
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps

SS = 2

_ROOT = Path(__file__).resolve().parents[2]
ASSET_DIR = _ROOT / "assets" / "equipment"
FONT_DIRS = [
    _ROOT / "assets" / "fonts",
    Path("/usr/share/fonts/truetype/dejavu"),
    Path("/usr/share/fonts/dejavu"),
    Path("/usr/share/fonts/ttf-dejavu"),
    Path("/usr/share/fonts/TTF"),
]

# Ice leather, silver-blue metal, and a cold page. The names stay, because the
# card still talks about gilt and bronze; the hues are what changed.
LEATHER_TOP = (38, 72, 108)
LEATHER_BOTTOM = (12, 28, 48)
GOLD_HI = (232, 248, 255)
GOLD = (118, 196, 228)
GOLD_DEEP = (58, 112, 148)
GOLD_DIM = (40, 78, 108)
IVORY = (232, 244, 250)
ON_DARK_MUTED = (176, 210, 228)
ON_DARK_DIM = (112, 148, 172)
PAPER = (220, 236, 244)
PAPER_EDGE = (118, 164, 196)
INK = (22, 48, 70)
INK_MUTED = (58, 96, 124)
INK_FAINT = (108, 146, 172)
BRONZE_INK = (40, 86, 120)
NICHE_TOP = (26, 50, 74)
NICHE_BOTTOM = (8, 20, 34)
PAGE_RULE = (*BRONZE_INK, 150)
STEEL = (184, 192, 204)
ASTRAL = (150, 214, 255)

# Bright on leather.
RARITY_GEM = {
    "common": (198, 198, 204),
    "uncommon": (92, 208, 132),
    "rare": (98, 160, 255),
    "magic": (196, 124, 255),
    "legendary": (255, 184, 62),
}
# The same hues, dark enough to read on paper.
RARITY_INK = {
    "common": (92, 88, 86),
    "uncommon": (28, 116, 62),
    "rare": (34, 84, 184),
    "magic": (118, 52, 182),
    "legendary": (172, 98, 6),
}
ARCHETYPE_TINT = {
    "guardian": (126, 182, 255),
    "slayer": (255, 107, 90),
    "vanguard": (230, 195, 106),
}
# How each line is forged: the body of the plate, then its trim.
ARCHETYPE_METAL = {
    "guardian": ((126, 182, 255), None),
    "slayer": ((86, 76, 84), (226, 78, 60)),
    "vanguard": ((230, 195, 106), (250, 240, 214)),
}
ELEMENT_TINT = {
    "light": (236, 200, 96),
    "dark": (112, 84, 168),
    "corrupted": (158, 64, 160),
    "nature": (84, 168, 92),
    "wind": (96, 186, 176),
    "water": (70, 136, 232),
    "fire": (232, 98, 52),
    "earth": (150, 112, 68),
    "electric": (226, 186, 40),
}
UNKNOWN_GLOW = (176, 120, 255)

def mix(a, b, t: float) -> tuple[int, int, int]:
    return tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(3))


# Dropped-in PNG art is lifted by this much before it is drawn, because dark
# bronze and leather vanish inside a dark niche. 1.0 draws the file as it is.
ART_BRIGHTNESS = 1.55
# How solid the art of an empty slot stays.
ART_EMPTY_ALPHA = 0.62


def _scale(color, factor: float) -> tuple[int, int, int]:
    return tuple(min(255, round(value * factor)) for value in color[:3])


@dataclass(frozen=True)
class Theme:
    """The cover a card is bound in. The page keeps its ink in every theme."""

    key: str
    label: str
    accent: int
    leather_top: tuple
    leather_bottom: tuple
    lattice: tuple
    vignette: tuple
    trim_hi: tuple
    trim: tuple
    trim_deep: tuple
    trim_dim: tuple
    ivory: tuple
    muted: tuple
    dim: tuple
    kicker: tuple
    paper: tuple
    paper_edge: tuple
    niche_top: tuple
    niche_bottom: tuple
    tile_item: tuple
    tile_empty: tuple
    tile_selected: tuple
    tile_edge: tuple
    sketch: tuple


def _bind(key, label, accent, leather_top, leather_bottom, trim, paper, paper_edge) -> Theme:
    """Work out a whole cover from its leather, its metal, and its paper."""
    ivory = mix((255, 255, 255), trim, 0.10)
    return Theme(
        key=key,
        label=label,
        accent=accent,
        leather_top=leather_top,
        leather_bottom=leather_bottom,
        lattice=_scale(leather_top, 2.0),
        vignette=_scale(leather_bottom, 0.25),
        trim_hi=mix(trim, (255, 255, 255), 0.45),
        trim=trim,
        trim_deep=mix(trim, (0, 0, 0), 0.30),
        trim_dim=mix(trim, leather_top, 0.62),
        ivory=ivory,
        muted=mix(mix(trim, ivory, 0.40), leather_top, 0.14),
        dim=mix(trim, leather_top, 0.50),
        kicker=mix(trim, (0, 0, 0), 0.12),
        paper=paper,
        paper_edge=paper_edge,
        niche_top=_scale(leather_top, 0.83),
        niche_bottom=_scale(leather_bottom, 0.60),
        tile_item=(_scale(leather_top, 1.35), _scale(leather_top, 0.83)),
        tile_empty=(leather_top, _scale(leather_top, 0.70)),
        tile_selected=(_scale(leather_top, 1.65), _scale(leather_top, 0.96)),
        tile_edge=_scale(leather_top, 1.60),
        sketch=mix(trim, leather_top, 0.55),
    )


CHRONICLE = _bind(
    "chronicle",
    "Chronicle",
    0x7EB6D6,
    LEATHER_TOP,
    LEATHER_BOTTOM,
    GOLD,
    PAPER,
    PAPER_EDGE,
)
THEMES = {
    "chronicle": CHRONICLE,
    "void": _bind("void", "Void", 0x7C5CFF, (30, 22, 48), (9, 7, 16), (170, 148, 255), (236, 231, 246), (150, 132, 196)),
    "royal": _bind("royal", "Royal", 0xC084FC, (64, 26, 96), (26, 9, 44), (236, 194, 116), (247, 238, 228), (184, 138, 150)),
    "frost": _bind("frost", "Frost", 0x7DD3FC, (34, 60, 84), (11, 23, 36), (178, 224, 246), (238, 246, 250), (136, 178, 204)),
    "dusk": _bind("dusk", "Dusk", 0x818CF8, (26, 32, 54), (7, 9, 17), (150, 162, 250), (233, 235, 245), (128, 140, 190)),
    "anvil": _bind("anvil", "Thorne's Anvil", 0xE8743C, (46, 28, 20), (13, 8, 6), (234, 146, 78), (241, 229, 212), (178, 112, 72)),
    "wyrmscale": _bind("wyrmscale", "Wyrmscale", 0x5EEAD4, (16, 50, 54), (5, 16, 18), (146, 230, 212), (233, 245, 241), (120, 172, 162)),
    "maw": _bind("maw", "Abyssal Maw", 0xF0567A, (44, 10, 26), (11, 2, 8), (242, 98, 128), (243, 229, 233), (172, 92, 112)),
    "oathbound": _bind("oathbound", "Oathbound", 0xD6C478, (22, 32, 24), (6, 10, 7), (216, 198, 124), (241, 237, 221), (162, 152, 102)),
}


def theme_for(theme) -> Theme:
    """Accept a Theme, a key, or nothing."""
    if isinstance(theme, Theme):
        return theme
    return THEMES.get(str(theme or "chronicle").lower(), CHRONICLE)


def number(value) -> str:
    """One decimal place, dropped when it is zero."""
    text = f"{float(value or 0):.1f}"
    if text.endswith(".0"):
        text = text[:-2]
    return "0" if text == "-0" else text


# ---------------------------------------------------------------- fonts

_ROLE_FILES = {
    "display": ("chronicle-display.ttf", "DejaVuSerif-Bold.ttf", "georgiab.ttf", "timesbd.ttf"),
    "text": ("chronicle-text.ttf", "DejaVuSerif.ttf", "georgia.ttf", "times.ttf"),
    "strong": ("chronicle-text-bold.ttf", "DejaVuSerif-Bold.ttf", "georgiab.ttf", "timesbd.ttf"),
    "label": ("chronicle-label.ttf", "DejaVuSans-Bold.ttf", "arialbd.ttf"),
    "sans": ("DejaVuSans.ttf", "arial.ttf"),
    # Symbola, George Douros. Bundled so emoji in names can be drawn.
    "symbols": ("Symbola.ttf", "seguisym.ttf", "DejaVuSans.ttf"),
}
_FALLBACK_ROLES = ("text", "sans", "symbols")
# The layout was drawn for DejaVu. Any other face is scaled until its letters
# stand as tall: capitals for titles and labels, lowercase for body copy.
_REFERENCE_HEIGHT = {
    "display": ("H", 0.729),
    "label": ("H", 0.729),
    "text": ("x", 0.519),
    "strong": ("x", 0.519),
}
_SKIP_CODEPOINTS = {0xFE0E, 0xFE0F, 0x200D}


@lru_cache(maxsize=None)
def _font_file(role: str) -> str | None:
    for name in _ROLE_FILES[role]:
        for folder in FONT_DIRS:
            path = folder / name
            if path.is_file():
                return str(path)
        try:
            return ImageFont.truetype(name, 12).path
        except OSError:
            continue
    return None


@lru_cache(maxsize=None)
def _optical_scale(role: str) -> float:
    path = _font_file(role)
    probe = _REFERENCE_HEIGHT.get(role)
    if path is None or probe is None or Path(path).name.startswith("DejaVu"):
        return 1.0
    letter, target = probe
    try:
        height = -ImageFont.truetype(path, 400).getbbox(letter, anchor="ls")[1] / 400
    except Exception:
        return 1.0
    if height <= 0:
        return 1.0
    return max(0.85, min(1.30, target / height))


@lru_cache(maxsize=256)
def font(role: str, px: int) -> ImageFont.ImageFont:
    """Cached, so a face is read from disk once and keeps one identity."""
    path = _font_file(role)
    if path is None:
        try:
            return ImageFont.load_default(px)
        except TypeError:
            return ImageFont.load_default()
    return ImageFont.truetype(path, max(1, round(px * _optical_scale(role))))


@lru_cache(maxsize=None)
def _notdef(role: str) -> bytes:
    return bytes(font(role, 24).getmask("￿", mode="1"))


@lru_cache(maxsize=8192)
def _has_glyph(role: str, character: str) -> bool:
    try:
        return bytes(font(role, 24).getmask(character, mode="1")) != _notdef(role)
    except Exception:
        return True


def _runs(text: str, role: str) -> list[tuple[str, str]]:
    """Split text into stretches that share a face, borrowing symbols where needed."""
    runs: list[list[str]] = []
    for character in str(text):
        if ord(character) in _SKIP_CODEPOINTS:
            continue
        face = role
        if not character.isascii() and not _has_glyph(role, character):
            face = next((other for other in _FALLBACK_ROLES if _has_glyph(other, character)), role)
        if runs and runs[-1][0] == face:
            runs[-1][1] += character
        else:
            runs.append([face, character])
    return [(face, chunk) for face, chunk in runs]


# ------------------------------------------------------------- textures

def _vgrad(size: tuple[int, int], top, bottom) -> Image.Image:
    ramp = Image.linear_gradient("L").resize((max(1, size[0]), max(1, size[1])))
    return ImageOps.colorize(ramp, top, bottom)


def _noise(width: int, height: int, seed: int) -> Image.Image:
    return Image.frombytes("L", (width, height), random.Random(seed).randbytes(width * height))


def _mottle(width: int, height: int, cell: int, seed: int, strength: float) -> Image.Image:
    small = _noise(width // cell + 2, height // cell + 2, seed)
    big = small.resize((width, height), Image.Resampling.BICUBIC)
    return Image.blend(Image.new("L", (width, height), 128), big, strength)


def _grey(image: Image.Image) -> Image.Image:
    return Image.merge("RGB", (image, image, image))


def _leather(width: int, height: int, theme: Theme) -> Image.Image:
    image = _vgrad((width, height), theme.leather_top, theme.leather_bottom)
    blotch = Image.blend(_mottle(width, height, 44, 11, 0.55), _mottle(width, height, 5, 12, 0.5), 0.4)
    image = ImageChops.soft_light(image, _grey(blotch))
    lattice = Image.new("L", (width, height), 0)
    pen = ImageDraw.Draw(lattice)
    step = 34
    for offset in range(-height, width + height, step):
        pen.line((offset, 0, offset + height, height), fill=255, width=1)
        pen.line((offset, height, offset + height, 0), fill=255, width=1)
    image.paste(theme.lattice, mask=lattice.point(lambda value: value * 16 // 255))
    edges = Image.radial_gradient("L").resize((width, height))
    image.paste(theme.vignette, mask=edges.point(lambda value: max(0, value - 96) * 190 // 159))
    return image


@lru_cache(maxsize=4)
def _sheet(width: int, height: int, theme: Theme) -> Image.Image:
    """A page at canvas scale. Kept, because scaling it up is slower than drawing on it."""
    return _parchment(width, height, theme).resize((width * SS, height * SS), Image.Resampling.BICUBIC)


def _parchment(width: int, height: int, theme: Theme) -> Image.Image:
    image = Image.new("RGB", (width, height), theme.paper)
    blotch = Image.blend(_mottle(width, height, 60, 21, 0.6), _mottle(width, height, 7, 22, 0.35), 0.35)
    image = ImageChops.soft_light(image, _grey(blotch))
    burn = Image.new("L", (width, height), 255)
    ImageDraw.Draw(burn).rounded_rectangle((16, 16, width - 17, height - 17), radius=34, fill=0)
    burn = burn.filter(ImageFilter.GaussianBlur(24)).point(lambda value: value * 150 // 255)
    image.paste(theme.paper_edge, mask=burn)
    return image


# ---------------------------------------------------------------- icons

class _Glyph:
    """Three stencils on a 100 by 100 grid: steel, gilt trim, and etched lines."""

    def __init__(self, px: int) -> None:
        self.px = px
        self.k = px / 100
        self.layers = {name: Image.new("L", (px, px), 0) for name in ("metal", "trim", "etch")}
        self.pens = {name: ImageDraw.Draw(layer) for name, layer in self.layers.items()}

    def _pts(self, points):
        return [(x * self.k, y * self.k) for x, y in points]

    def poly(self, points, layer="metal", fill=255, mirror=False) -> None:
        self.pens[layer].polygon(self._pts(points), fill=fill)
        if mirror:
            self.pens[layer].polygon(self._pts([(100 - x, y) for x, y in points]), fill=fill)

    def oval(self, box, layer="metal", fill=255, mirror=False) -> None:
        x0, y0, x1, y1 = box
        self.pens[layer].ellipse([v * self.k for v in box], fill=fill)
        if mirror:
            self.pens[layer].ellipse([v * self.k for v in (100 - x1, y0, 100 - x0, y1)], fill=fill)

    def cut(self, points) -> None:
        for layer in ("metal", "trim"):
            self.pens[layer].polygon(self._pts(points), fill=0)

    def line(self, points, width=2.0, layer="etch", mirror=False) -> None:
        stroke = max(1, round(width * self.k))
        self.pens[layer].line(self._pts(points), fill=255, width=stroke, joint="curve")
        if mirror:
            self.pens[layer].line(self._pts([(100 - x, y) for x, y in points]), fill=255, width=stroke, joint="curve")

    def arc(self, box, start, end, width=5.0, layer="metal") -> None:
        self.pens[layer].arc([v * self.k for v in box], start, end, fill=255, width=max(1, round(width * self.k)))

    def turn(self, degrees: float) -> None:
        for name, layer in self.layers.items():
            self.layers[name] = layer.rotate(degrees, resample=Image.Resampling.BICUBIC)
            self.pens[name] = ImageDraw.Draw(self.layers[name])


def _helm(g: _Glyph) -> None:
    g.oval((19, 8, 81, 78))
    g.poly([(19, 42), (81, 42), (80, 68), (70, 94), (30, 94), (20, 68)])
    g.cut([(30, 47), (70, 47), (67, 58), (55, 59), (55, 95), (45, 95), (45, 59), (33, 58)])
    g.poly([(17, 37), (83, 37), (83, 44), (17, 44)], layer="trim")
    g.poly([(47, 3), (53, 3), (54, 38), (46, 38)], layer="trim")
    for x in (25, 37, 63, 75):
        g.oval((x - 1.6, 39, x + 1.6, 42.2), layer="etch")
    g.line([(28, 62), (36, 90)], width=1.4, mirror=True)


def _cuirass(g: _Glyph) -> None:
    # Fauld first, so the breastplate overlaps it.
    g.poly([(29, 64), (71, 64), (80, 90), (50, 98), (20, 90)])
    g.poly([
        (37, 8), (43, 16), (50, 18), (57, 16), (63, 8), (75, 13), (79, 30),
        (75, 48), (71, 66), (29, 66), (25, 48), (21, 30), (25, 13),
    ])
    g.oval((3, 9, 35, 37), mirror=True)
    g.poly([(37, 8), (43, 16), (50, 18), (57, 16), (63, 8), (60, 5), (56, 11), (50, 13), (44, 11), (40, 5)], layer="trim")
    g.poly([(28, 61), (72, 61), (73, 69), (27, 69)], layer="trim")
    g.arc((3, 9, 35, 37), 300, 110, width=2.2, layer="etch")
    g.arc((65, 9, 97, 37), 70, 240, width=2.2, layer="etch")
    g.arc((7, 16, 31, 40), 200, 340, width=1.6, layer="etch")
    g.arc((69, 16, 93, 40), 200, 340, width=1.6, layer="etch")
    g.line([(50, 19), (50, 61)], width=1.8)
    g.line([(29, 40), (38, 48), (50, 50)], width=1.8, mirror=True)
    g.line([(36, 70), (33, 93)], width=1.6, mirror=True)
    g.line([(50, 70), (50, 97)], width=1.6)
    g.line([(23, 80), (50, 86), (77, 80)], width=1.4)


def _greaves(g: _Glyph) -> None:
    g.poly([(17, 5), (45, 5), (45, 34), (18, 34)], mirror=True)
    g.poly([(20, 44), (44, 44), (42, 88), (46, 96), (18, 96), (23, 88)], mirror=True)
    g.oval((13, 27, 49, 51), mirror=True)
    g.oval((22, 32, 40, 46), layer="trim", mirror=True)
    g.line([(18, 14), (45, 14)], width=1.3, mirror=True)
    g.line([(18, 22), (45, 22)], width=1.3, mirror=True)
    g.line([(32, 54), (32, 88)], width=1.5, mirror=True)
    g.line([(23, 88), (42, 88)], width=1.3, mirror=True)


def _sabatons(g: _Glyph) -> None:
    g.poly([(26, 8), (54, 8), (54, 44), (64, 53), (84, 61), (95, 76), (97, 87), (22, 87), (22, 50), (26, 40)])
    g.poly([(24, 6), (56, 6), (56, 16), (24, 16)], layer="trim")
    g.poly([(20, 86), (98, 86), (98, 93), (20, 93)], layer="trim")
    g.line([(26, 42), (54, 44)], width=1.5)
    g.line([(60, 51), (55, 86)], width=1.4)
    g.line([(71, 56), (68, 86)], width=1.4)
    g.line([(82, 61), (81, 86)], width=1.4)
    g.line([(26, 28), (54, 28)], width=1.3)


def _sword(g: _Glyph, blade_top: float = 2) -> None:
    g.poly([(50, blade_top), (57, blade_top + 13), (55.5, 66), (44.5, 66), (43, blade_top + 13)])
    g.line([(50, blade_top + 13), (50, 64)], width=1.4)
    g.poly([(26, 64), (74, 64), (77, 71), (23, 71)], layer="trim")
    g.poly([(46, 71), (54, 71), (54, 88), (46, 88)])
    for y in (75, 79, 83):
        g.line([(46, y), (54, y + 2)], width=1.1)
    g.oval((43, 86, 57, 99), layer="trim")
    g.turn(-45)


def _dagger(g: _Glyph) -> None:
    _sword(g, blade_top=26)


def _shield(g: _Glyph) -> None:
    outline = [
        (15, 13), (33, 8), (50, 13), (67, 8), (85, 13), (85, 44), (79, 63),
        (67, 80), (50, 95), (33, 80), (21, 63), (15, 44),
    ]
    g.poly(outline, layer="trim")
    inner = [(50 + (x - 50) * 0.84, 51 + (y - 51) * 0.86) for x, y in outline]
    g.poly(inner, layer="metal")
    g.poly(inner, layer="trim", fill=0)
    g.line([(50, 17), (50, 88)], width=1.5)
    g.line([(22, 40), (78, 40)], width=1.5)
    g.oval((40, 30, 60, 50), layer="trim")
    g.oval((40, 30, 60, 50), layer="metal", fill=0)


def _axe(g: _Glyph) -> None:
    g.poly([(47, 6), (53, 6), (53, 97), (47, 97)], layer="trim")
    g.poly([(53, 12), (68, 6), (84, 13), (92, 34), (86, 56), (70, 48), (53, 44)])
    g.line([(72, 10), (80, 30), (74, 48)], width=1.5)
    g.poly([(47, 16), (36, 20), (36, 38), (47, 42)])
    g.turn(-28)


def _hammer(g: _Glyph) -> None:
    g.poly([(47, 30), (53, 30), (53, 97), (47, 97)], layer="trim")
    g.poly([(22, 8), (78, 8), (82, 14), (82, 30), (78, 36), (22, 36), (18, 30), (18, 14)])
    g.poly([(44, 6), (56, 6), (56, 38), (44, 38)], layer="trim")
    g.line([(30, 10), (30, 34)], width=1.4, mirror=True)
    g.turn(-28)


def _spear(g: _Glyph) -> None:
    g.poly([(48, 26), (52, 26), (52, 99), (48, 99)], layer="trim")
    g.poly([(50, 1), (59, 19), (50, 33), (41, 19)])
    g.line([(50, 6), (50, 30)], width=1.3)
    g.poly([(45, 31), (55, 31), (55, 36), (45, 36)], layer="trim")
    g.turn(-45)


def _wand(g: _Glyph) -> None:
    g.poly([(47.5, 30), (52.5, 30), (53, 98), (47, 98)], layer="trim")
    g.oval((37, 6, 63, 32))
    g.arc((31, 4, 69, 42), 20, 160, width=4, layer="trim")
    g.oval((43, 11, 51, 19), layer="etch", fill=0)
    g.turn(-30)


def _bow(g: _Glyph) -> None:
    g.arc((34, 4, 108, 96), 112, 248, width=6)
    g.line([(57, 7), (57, 93)], width=1.2, layer="trim")
    g.line([(20, 50), (84, 50)], width=1.8, layer="trim")
    g.poly([(84, 44), (96, 50), (84, 56)])
    g.poly([(36, 46), (45, 46), (45, 54), (36, 54)], layer="trim")
    g.turn(-45)


def _scythe(g: _Glyph) -> None:
    g.poly([(47, 8), (53, 8), (53, 98), (47, 98)], layer="trim")
    g.poly([(50, 6), (66, 3), (84, 8), (96, 22), (99, 36), (88, 24), (72, 17), (52, 18)])
    g.line([(54, 12), (72, 11), (90, 22)], width=1.3)
    g.turn(24)


_GLYPHS = {
    "head": _helm,
    "chest": _cuirass,
    "legs": _greaves,
    "feet": _sabatons,
    "sword": _sword,
    "dagger": _dagger,
    "knife": _dagger,
    "shield": _shield,
    "axe": _axe,
    "hammer": _hammer,
    "mace": _hammer,
    "spear": _spear,
    "wand": _wand,
    "staff": _wand,
    "bow": _bow,
    "scythe": _scythe,
}


def weapon_glyph(kind) -> str:
    key = str(kind or "").strip().lower()
    return key if key in _GLYPHS else "sword"


@lru_cache(maxsize=256)
def _icon(kind: str, px: int, tint: tuple[int, int, int], style: str, trim_tint=None) -> Image.Image:
    glyph = _Glyph(px * 2)
    _GLYPHS[kind](glyph)
    metal, trim, etch = (
        glyph.layers[name].resize((px, px), Image.Resampling.LANCZOS) for name in ("metal", "trim", "etch")
    )
    shape = ImageChops.lighter(metal, trim)
    if style == "sketch":
        thin = shape.filter(ImageFilter.MinFilter(2 * max(1, px // 44) + 1))
        ring = ImageChops.subtract(shape, thin)
        alpha = ImageChops.lighter(ring.point(lambda value: value * 200 // 255), shape.point(lambda value: value * 30 // 255))
        image = Image.new("RGB", (px, px), tint)
        image.putalpha(alpha)
        return image
    steel = mix(tint, STEEL, 0.30)
    image = Image.new("RGB", (px, px), (0, 0, 0))
    image.paste(_vgrad((px, px), mix(steel, (255, 255, 255), 0.42), mix(steel, (0, 0, 0), 0.52)), mask=metal)
    if trim_tint is None:
        image.paste(_vgrad((px, px), GOLD_HI, mix(GOLD_DEEP, (0, 0, 0), 0.25)), mask=trim)
    else:
        image.paste(_vgrad((px, px), mix(trim_tint, (255, 255, 255), 0.35), mix(trim_tint, (0, 0, 0), 0.45)), mask=trim)
    sheen = Image.linear_gradient("L").rotate(55, resample=Image.Resampling.BICUBIC).resize((px, px))
    sheen = sheen.point(lambda value: max(0, 70 - abs(value - 104) * 3))
    image.paste((255, 255, 255), mask=ImageChops.multiply(sheen, metal))
    image.paste(mix(steel, (0, 0, 0), 0.78), mask=ImageChops.multiply(etch, shape).point(lambda value: value * 235 // 255))
    edge = max(1, px // 52)
    lit = ImageChops.subtract(shape, ImageChops.offset(shape, edge, edge))
    shaded = ImageChops.subtract(shape, ImageChops.offset(shape, -edge, -edge))
    image.paste((0, 0, 0), mask=shaded.point(lambda value: value * 150 // 255))
    image.paste((255, 255, 255), mask=lit.point(lambda value: value * 150 // 255))
    image.putalpha(shape)
    return image


@lru_cache(maxsize=64)
def _art(path: str, stamp: float, brightness: float) -> Image.Image:
    with Image.open(path) as source:
        art = source.convert("RGBA")
    if brightness != 1.0:
        lifted = ImageEnhance.Brightness(art.convert("RGB")).enhance(brightness)
        lifted.putalpha(art.getchannel("A"))
        art = lifted
    return art


def load_art(*names: str) -> Image.Image | None:
    """First PNG in assets/equipment that exists. Re-read when the file changes."""
    for name in names:
        path = ASSET_DIR / name
        try:
            stamp = path.stat().st_mtime
        except OSError:
            continue
        try:
            return _art(str(path), stamp, float(ART_BRIGHTNESS))
        except OSError:
            continue
    return None


# --------------------------------------------------------------- canvas

class Canvas:
    def __init__(self, width: int, height: int, base: Image.Image | None = None, theme=None) -> None:
        self.w = width
        self.h = height
        self.t = theme_for(theme)
        self.im = base if base is not None else Image.new("RGB", (width * SS, height * SS), self.t.leather_bottom)
        self.d = ImageDraw.Draw(self.im, "RGBA")

    @classmethod
    def tome(cls, width: int, height: int, theme=None) -> "Canvas":
        """A leather cover with a gilt frame, ready for a page."""
        theme = theme_for(theme)
        return cls(width, height, _cover(width, height, theme).copy(), theme)

    # -- geometry helpers
    @staticmethod
    def _b(box) -> tuple[int, int, int, int]:
        return tuple(round(value * SS) for value in box)

    @staticmethod
    def _p(points):
        return [(x * SS, y * SS) for x, y in points]

    @staticmethod
    def _shape(width: int, height: int, radius: float, fill: int = 255) -> Image.Image:
        shape = Image.new("L", (width, height), 0)
        ImageDraw.Draw(shape).rounded_rectangle((0, 0, width - 1, height - 1), radius=radius, fill=fill)
        return shape

    def _soft(self, box, radius, blur, alpha, grow=0.0):
        """A blurred rounded rectangle, built at quarter size because blur is the slow part."""
        x0, y0, x1, y1 = self._b(box)
        pad = round(blur * SS * 3)
        width, height = x1 - x0 + 2 * pad, y1 - y0 + 2 * pad
        q = 4
        small = Image.new("L", (width // q + 1, height // q + 1), 0)
        g = grow * SS
        ImageDraw.Draw(small).rounded_rectangle(
            ((pad - g) / q, (pad - g) / q, (width - pad + g) / q, (height - pad + g) / q),
            radius=max(0, (radius * SS + g) / q),
            fill=alpha,
        )
        small = small.filter(ImageFilter.GaussianBlur(max(0.5, blur * SS / q)))
        return small.resize((width, height), Image.Resampling.BILINEAR), (x0 - pad, y0 - pad)

    # -- frame and surfaces
    def _notched(self, inset: float, reach: float, color, width: float) -> None:
        """A border whose corners curve inward around the point (corner, corner)."""
        corner = 16
        x0, y0, x1, y1 = inset, inset, self.w - inset, self.h - inset
        gap = corner - inset
        run = math.sqrt(max(0.0, reach * reach - gap * gap)) + gap
        stroke = max(1, round(width * SS))
        for a, b in (
            ((x0 + run, y0), (x1 - run, y0)),
            ((x0 + run, y1), (x1 - run, y1)),
            ((x0, y0 + run), (x0, y1 - run)),
            ((x1, y0 + run), (x1, y1 - run)),
        ):
            self.d.line(self._p([a, b]), fill=color, width=stroke)
        far_x, far_y = self.w - corner, self.h - corner
        half = width / 2
        for (cx, cy), start in (((corner, corner), 0), ((far_x, corner), 90), ((far_x, far_y), 180), ((corner, far_y), 270)):
            r = reach + half
            self.d.arc(self._b((cx - r, cy - r, cx + r, cy + r)), start, start + 90, fill=color, width=stroke)

    def _frame(self) -> None:
        t = self.t
        self._notched(16, 20, t.trim, 2)
        self._notched(23, 27, t.trim_deep, 1)
        for cx, cy in ((28, 28), (self.w - 28, 28), (28, self.h - 28), (self.w - 28, self.h - 28)):
            self.diamond(cx, cy, 4.5, t.trim)
        for cy in (16, self.h - 16):
            self.diamond(self.w / 2, cy, 9, t.leather_bottom)
            self.diamond(self.w / 2, cy, 6, t.trim)
            self.diamond(self.w / 2, cy, 2.5, t.leather_bottom)

    def shadow(self, box, radius=0.0, blur=12.0, dy=6.0, alpha=150) -> None:
        mask, (x, y) = self._soft(box, radius, blur, alpha)
        self.im.paste((0, 0, 0), (x, y + round(dy * SS)), mask)

    def glow(self, box, radius, colors, blur=14.0, alpha=150, grow=4.0) -> None:
        """Bloom behind a box. Several colors share the width, left to right."""
        if not colors:
            return
        x0, y0, x1, y1 = box
        span = (x1 - x0) / len(colors)
        for index, color in enumerate(colors):
            part = (x0 + span * index, y0, x0 + span * (index + 1), y1)
            mask, origin = self._soft(part, radius, blur, alpha, grow)
            self.im.paste(tuple(color[:3]), origin, mask)

    def panel(self, box, radius=0.0, fill=None, gradient=None, outline=None, width=1.0) -> None:
        x0, y0, x1, y1 = self._b(box)
        r = radius * SS
        if gradient is not None:
            size = (x1 - x0, y1 - y0)
            self.im.paste(_vgrad(size, *gradient), (x0, y0), self._shape(*size, r))
        elif fill is not None:
            self.d.rounded_rectangle((x0, y0, x1, y1), radius=r, fill=fill)
        if outline is not None:
            self.d.rounded_rectangle((x0, y0, x1, y1), radius=r, outline=outline, width=max(1, round(width * SS)))

    def page(self, box, radius=10.0) -> None:
        """An aged sheet lying on the cover."""
        x0, y0, x1, y1 = box
        self.shadow(box, radius, blur=14, dy=8, alpha=175)
        width, height = round(x1 - x0), round(y1 - y0)
        self.im.paste(_sheet(width, height, self.t), (round(x0 * SS), round(y0 * SS)), self._shape(width * SS, height * SS, radius * SS))
        edge = mix(self.t.trim_deep, (0, 0, 0), 0.18)
        self.panel(box, radius, outline=(*edge, 255), width=1)
        self.panel((x0 + 9, y0 + 9, x1 - 9, y1 - 9), max(0, radius - 4), outline=(*self.t.trim, 130), width=1)
        for cx, cy, sx, sy in ((x0, y0, 1, 1), (x1, y0, -1, 1), (x0, y1, 1, -1), (x1, y1, -1, -1)):
            px, py = cx + 15 * sx, cy + 15 * sy
            self.line([(px, py + 11 * sy), (px, py), (px + 11 * sx, py)], (*edge, 210), 1.5)
            self.diamond(px, py, 2.6, edge)

    def socket(self, box, radius, border=None, border_width=1.5, glows=()) -> None:
        """A dark niche. Enchantment light kindles inside it, behind the steel."""
        x0, y0, x1, y1 = self._b(box)
        width, height = x1 - x0, y1 - y0
        r = radius * SS
        shape = self._shape(width, height, r)
        if border is None:
            border = self.t.trim_deep
        self.im.paste(_vgrad((width, height), self.t.niche_top, self.t.niche_bottom), (x0, y0), shape)
        q = 4
        count = len(glows)
        for index, color in enumerate(glows):
            small = Image.new("L", (width // q + 1, height // q + 1), 0)
            cx = (index + 0.5) / count * width / q
            rx = width / q * (0.30 if count == 1 else 0.22)
            ImageDraw.Draw(small).ellipse((cx - rx, height / q * 0.24, cx + rx, height / q * 0.84), fill=205)
            small = small.filter(ImageFilter.GaussianBlur(max(1.0, width / q * 0.15)))
            bloom = small.resize((width, height), Image.Resampling.BILINEAR)
            self.im.paste(tuple(color[:3]), (x0, y0), ImageChops.multiply(bloom, shape))
        drop = round(height * 0.09)
        hollow = Image.new("L", (width, height), 200)
        ImageDraw.Draw(hollow).rounded_rectangle((0, drop, width - 1, height - 1 + drop), radius=r, fill=0)
        hollow = hollow.filter(ImageFilter.GaussianBlur(max(1.0, height * 0.06)))
        self.im.paste((0, 0, 0), (x0, y0), ImageChops.multiply(hollow, shape))
        self.d.rounded_rectangle((x0, y0, x1, y1), radius=r, outline=border, width=max(1, round(border_width * SS)))

    # -- marks
    def line(self, points, fill, width=1.0) -> None:
        self.d.line(self._p(points), fill=fill, width=max(1, round(width * SS)), joint="curve")

    def poly(self, points, fill=None, outline=None, width=1.0) -> None:
        self.d.polygon(self._p(points), fill=fill, outline=outline, width=max(1, round(width * SS)))

    def circle(self, cx, cy, r, fill=None, outline=None, width=1.0) -> None:
        self.d.ellipse(self._b((cx - r, cy - r, cx + r, cy + r)), fill=fill, outline=outline, width=max(1, round(width * SS)))

    def diamond(self, cx, cy, r, fill) -> None:
        self.poly([(cx, cy - r), (cx + r, cy), (cx, cy + r), (cx - r, cy)], fill=fill)

    def rule(self, x0, x1, y, color=None, gem=None) -> None:
        """A ruled line with a lozenge at its middle."""
        color = color or self.t.trim_deep
        gem = gem or self.t.trim
        mid = (x0 + x1) / 2
        self.line([(x0, y), (mid - 16, y)], color, 1)
        self.line([(mid + 16, y), (x1, y)], color, 1)
        self.diamond(mid, y, 5, gem)
        self.diamond(mid - 11, y, 2, color)
        self.diamond(mid + 11, y, 2, color)

    def star(self, cx, cy, r, fill=None, outline=None, width=1.2) -> None:
        points = []
        for index in range(10):
            angle = -math.pi / 2 + index * math.pi / 5
            reach = r if index % 2 == 0 else r * 0.44
            points.append((cx + reach * math.cos(angle), cy + reach * math.sin(angle)))
        self.poly(points, fill=fill, outline=outline, width=width)

    def temper(self, x, cy, refinement, cap, *, base=5, top=7, step=20.0, r=7.5, dark=False) -> float:
        """Five forge stars, then the two that full attunement opens. Returns the row width."""
        refinement = max(0, min(top, int(refinement or 0)))
        hollow = self.t.trim_dim if dark else INK_FAINT
        for index in range(top):
            cx = x + r + index * step + (6 if index >= base else 0)
            if index < base:
                if index < refinement:
                    self.star(cx, cy, r, fill=self.t.trim, outline=mix(self.t.trim_deep, (0, 0, 0), 0.25), width=1)
                else:
                    self.star(cx, cy, r, outline=hollow, width=1.2)
            elif index < refinement:
                self.star(cx, cy, r, fill=ASTRAL, outline=(60, 120, 180), width=1)
            elif cap > base:
                self.star(cx, cy, r, outline=(96, 150, 200), width=1.2)
            else:
                self.diamond(cx, cy, 2.4, hollow)
        return 2 * r + (top - 1) * step + 6

    @staticmethod
    def temper_width(*, top=7, step=20.0, r=7.5) -> float:
        return 2 * r + (top - 1) * step + 6

    def gem(self, cx, cy, r, color, lit=True, dark=False) -> None:
        if not lit:
            self.circle(cx, cy, r, fill=mix(self.t.leather_bottom, (0, 0, 0), 0.15), outline=self.t.trim_dim if dark else INK_FAINT, width=1.2)
            return
        color = tuple(color[:3])
        if dark:
            mask, origin = self._soft((cx - r, cy - r, cx + r, cy + r), r, r * 0.9, 150)
            self.im.paste(color, origin, mask)
        self.circle(cx, cy, r, fill=mix(color, (0, 0, 0), 0.45))
        self.circle(cx, cy, r - 1.3, fill=color)
        self.circle(cx - r * 0.28, cy - r * 0.30, r * 0.34, fill=(255, 255, 255, 190))

    def gauge(self, box, fraction, color, ticks=(), dark=False) -> None:
        x0, y0, x1, y1 = box
        radius = (y1 - y0) / 2
        track = self.t.leather_bottom if dark else (*mix(self.t.trim_deep, self.t.paper, 0.35), 90)
        self.panel(box, radius, fill=track)
        fraction = max(0.0, min(1.0, float(fraction)))
        if fraction > 0:
            end = max(x0 + (y1 - y0), x0 + (x1 - x0) * fraction)
            self.panel((x0, y0, end, y1), radius, gradient=(mix(color, (255, 255, 255), 0.30), mix(color, (0, 0, 0), 0.22)))
            self.line([(x0 + radius, y0 + 2), (end - radius, y0 + 2)], (255, 255, 255, 70), 1)
        for tick in ticks:
            tx = x0 + (x1 - x0) * tick
            self.line([(tx, y0 + 1), (tx, y1 - 1)], (*mix(self.t.trim_deep, (0, 0, 0), 0.35), 150), 1)
        self.panel(box, radius, outline=(*mix(self.t.trim_deep, (0, 0, 0), 0.2), 255) if not dark else self.t.trim_dim, width=1)

    # -- pictures
    def paste(self, image: Image.Image, cx, cy, *, shadow=0.0) -> None:
        """Paste an image already sized in canvas pixels, centred on a logical point."""
        left = round(cx * SS - image.width / 2)
        top = round(cy * SS - image.height / 2)
        alpha = image.getchannel("A")
        if shadow:
            soft = alpha.filter(ImageFilter.GaussianBlur(shadow * SS)).point(lambda value: value * 170 // 255)
            self.im.paste((0, 0, 0), (left, top + round(shadow * SS)), soft)
        self.im.paste(image, (left, top), alpha)

    def icon(self, kind, cx, cy, size, tint=STEEL, *, trim=None, sketch=False, shadow=True) -> None:
        px = round(size * SS)
        image = _icon(kind, px, tuple(tint[:3]), "sketch" if sketch else "forged", tuple(trim[:3]) if trim else None)
        self.paste(image, cx, cy, shadow=0 if sketch or not shadow else max(1.0, size / 28))

    def plate(self, slot, cx, cy, size, archetype) -> None:
        """An armor piece forged in its archetype's metal."""
        tint, trim = ARCHETYPE_METAL.get(str(archetype or "").lower(), (STEEL, None))
        self.icon(slot, cx, cy, size, tint, trim=trim)

    def art(self, image: Image.Image, cx, cy, size, *, dim=False) -> None:
        """Fit a dropped-in PNG inside a square of the given size."""
        limit = size * SS
        scale = min(limit / image.width, limit / image.height)
        fitted = image.resize(
            (max(1, round(image.width * scale)), max(1, round(image.height * scale))),
            Image.Resampling.LANCZOS,
        )
        if dim:
            keep = round(ART_EMPTY_ALPHA * 100)
            fitted.putalpha(fitted.getchannel("A").point(lambda value: value * keep // 100))
        # A little lamplight behind the piece, so a dark picture still has an edge.
        reach = size * 0.27
        light, origin = self._soft((cx - reach, cy - reach, cx + reach, cy + reach), reach, size * 0.11, 70 if dim else 110)
        self.im.paste(mix(self.t.trim, self.t.leather_top, 0.45), origin, light)
        self.paste(fitted, cx, cy, shadow=0 if dim else max(1.0, size / 28))

    # -- text
    def text_width(self, text, role="text", size=18.0, tracking=0.0) -> float:
        px = round(size * SS)
        total = 0.0
        count = 0
        for face, chunk in _runs(text, role):
            face_font = font(face, px)
            if tracking:
                total += sum(face_font.getlength(character) for character in chunk)
                count += len(chunk)
            else:
                total += face_font.getlength(chunk)
        if tracking and count:
            total += tracking * SS * (count - 1)
        return total / SS

    def _write(self, pen, x, y, text, role, size, fill, vertical, tracking) -> None:
        px = round(size * SS)
        anchor = "l" + vertical
        for face, chunk in _runs(text, role):
            face_font = font(face, px)
            if tracking:
                for character in chunk:
                    pen.text((x, y), character, font=face_font, fill=fill, anchor=anchor)
                    x += face_font.getlength(character) + tracking * SS
            else:
                pen.text((x, y), chunk, font=face_font, fill=fill, anchor=anchor)
                x += face_font.getlength(chunk)

    def text(self, x, y, text, role="text", size=18.0, fill=INK, anchor="ls", tracking=0.0, shadow=None) -> float:
        """Draw one line. Anchors are Pillow's: l, m, r then a, m, s, d. Returns the width."""
        text = str(text)
        width = self.text_width(text, role, size, tracking)
        left = x * SS - {"l": 0.0, "m": width * SS / 2, "r": width * SS}[anchor[0]]
        if shadow is not None:
            self._write(self.d, left, y * SS + 1.5 * SS, text, role, size, shadow, anchor[1], tracking)
        self._write(self.d, left, y * SS, text, role, size, fill, anchor[1], tracking)
        return width

    def gilt_text(self, x, y, text, role="display", size=40.0, top=None, bottom=None, anchor="ls") -> float:
        """Baseline-anchored text filled with a top-to-bottom gradient and a soft shadow."""
        top = top or self.t.ivory
        bottom = bottom or self.t.trim
        text = str(text)
        width = self.text_width(text, role, size)
        ascent, descent = font(role, round(size * SS)).getmetrics()
        pad = 4 * SS
        mask = Image.new("L", (math.ceil(width * SS) + 2 * pad, ascent + descent + 2 * pad), 0)
        self._write(ImageDraw.Draw(mask), pad, pad + ascent, text, role, size, 255, "s", 0)
        left = round(x * SS - {"l": 0.0, "m": width * SS / 2, "r": width * SS}[anchor[0]]) - pad
        top_y = round(y * SS) - ascent - pad
        soft = mask.filter(ImageFilter.GaussianBlur(1.5 * SS)).point(lambda value: value * 200 // 255)
        self.im.paste((0, 0, 0), (left, top_y + 2 * SS), soft)
        self.im.paste(_vgrad(mask.size, top, bottom), (left, top_y), mask)
        return width

    def figure(self, x, y, text, size, width, fill=INK, anchor="ls", floor=14.0) -> None:
        """A display numeral, stepped down until it fits its column."""
        size = float(size)
        while size > floor and self.text_width(text, "display", size) > width:
            size -= 1
        self.text(x, y, text, "display", size, fill, anchor=anchor)

    def fit(self, text, role, size, width, tracking=0.0) -> str:
        text = str(text)
        if self.text_width(text, role, size, tracking) <= width:
            return text
        trimmed = text
        while trimmed and self.text_width(trimmed.rstrip() + "…", role, size, tracking) > width:
            trimmed = trimmed[:-1]
        return trimmed.rstrip() + "…"

    def wrap(self, text, role, size, width, max_lines=2) -> list[str]:
        """Greedy wrap. Anything cut off is marked with an ellipsis, never dropped silently."""
        lines: list[str] = []
        current = ""
        for word in str(text).split():
            candidate = word if not current else f"{current} {word}"
            if self.text_width(candidate, role, size) <= width:
                current = candidate
                continue
            if current:
                lines.append(current)
            current = word
        if current:
            lines.append(current)
        if len(lines) > max_lines:
            lines = lines[: max_lines - 1] + [" ".join(lines[max_lines - 1:])]
        return [self.fit(line, role, size, width) for line in lines] or [""]

    def pill(self, x, y, text, *, fill=None, outline=None, ink=IVORY, height=24.0, dot=None, size=11.0) -> float:
        """A small capsule label. Returns its width so pills can sit in a row."""
        text = str(text).upper()
        tracking = 1.6
        pad = 12
        lead = 14 if dot is not None else 0
        width = self.text_width(text, "label", size, tracking) + 2 * pad + lead
        box = (x, y, x + width, y + height)
        self.panel(box, height / 2, fill=fill, outline=outline, width=1.2)
        if dot is not None:
            self.gem(x + pad + 3, y + height / 2, 4.5, dot)
        self.text(x + pad + lead, y + height / 2 + 0.5, text, "label", size, ink, anchor="lm", tracking=tracking)
        return width

    def kicker(self, x, y, text, fill=BRONZE_INK, size=12.0, anchor="ls", tracking=2.6) -> float:
        return self.text(x, y, str(text).upper(), "label", size, fill, anchor=anchor, tracking=tracking)

    # -- finishing
    def png(self, corner=20.0) -> bytes:
        out = self.im.reduce(SS)
        out.putalpha(_card_mask(self.w, self.h, corner))
        buffer = io.BytesIO()
        out.save(buffer, format="PNG", compress_level=4)
        return buffer.getvalue()


@lru_cache(maxsize=3)
def _cover(width: int, height: int, theme: Theme) -> Image.Image:
    """Leather and frame at canvas scale. About 10 MB each; the last three are kept."""
    base = _leather(width, height, theme).resize((width * SS, height * SS), Image.Resampling.BICUBIC)
    Canvas(width, height, base, theme)._frame()
    return base


@lru_cache(maxsize=4)
def _card_mask(width: int, height: int, corner: float) -> Image.Image:
    return Canvas._shape(width * SS, height * SS, corner * SS).reduce(SS)


def draw_header(canvas: Canvas, kicker: str, title: str, subtitle: str = "", *, title_width: float = 640) -> None:
    left = 58
    canvas.kicker(left, 62, kicker, canvas.t.trim, size=12.5, tracking=3.4)
    size = 40.0
    while size > 24 and canvas.text_width(title, "display", size) > title_width:
        size -= 2
    canvas.gilt_text(left, 108, canvas.fit(title, "display", size, title_width), "display", size)
    if subtitle:
        canvas.text(left, 137, canvas.fit(subtitle, "text", 17, title_width), "text", 17, canvas.t.muted)
    canvas.rule(left, canvas.w - left, 156)


def header_stats(canvas: Canvas, stats: list[tuple[str, str]], *, size: float = 28, least: float = 84, gap: float = 22) -> float:
    """Label over value, in columns that end at the right margin. Returns where they begin."""
    x = canvas.w - 58
    left = x
    for index, (label, value) in enumerate(reversed(stats)):
        width = max(canvas.text_width(value, "display", size), canvas.text_width(label, "label", 10.5, 2.2), least)
        canvas.kicker(x, 84, label, canvas.t.muted, size=10.5, anchor="rs", tracking=2.2)
        canvas.text(x, 122, value, "display", size, canvas.t.ivory, anchor="rs", shadow=(0, 0, 0, 150))
        left = x - width
        x -= width + gap
        if index < len(stats) - 1:
            canvas.line([(x, 72), (x, 126)], canvas.t.trim_dim, 1)
            x -= gap
    return left

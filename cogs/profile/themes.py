"""PRPG cosmetics: local artwork, portable fonts and deterministic card chrome."""

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps


ASSET_ROOT = Path(__file__).resolve().parents[2] / "assets" / "profile_themes"


@dataclass(frozen=True)
class ProfileTheme:
    key: str
    name: str
    epithet: str
    description: str
    accent: str
    secondary: str
    background: str
    panel: str
    text: str
    muted: str
    emoji: str

    @property
    def classic(self):
        return self.key == "classic"

    @property
    def palette(self):
        return {
            "panel": self.panel,
            "panel_inner": self.background,
            "border": self.accent,
            "border_dim": self.secondary,
            "text": self.text,
            "muted": self.muted,
            "bar_bg": self.background,
        }


THEMES = {
    t.key: t for t in (
        ProfileTheme("classic", "Original Chronicle", "Your story begins here.",
                     "The original parchment-and-bronze profile card.",
                     "#c69c5a", "#846236", "#27180e", "#4a311e", "#f7e7c4", "#d6ba8c", "📜"),
        ProfileTheme("dragon", "Ashen Sovereign", "FROM ASH, AN EMPIRE.",
                     "An obsidian wyrm, molten gold and a citadel forged in fire.",
                     "#f6bb68", "#8c5935", "#120e0c", "#251b15", "#fff1db", "#d3bda4", "🐉"),
        ProfileTheme("evil", "The Hollow Crown", "LET THE LIGHT KNEEL.",
                     "A blood eclipse, a skeletal throne and blackened steel.",
                     "#f48591", "#83414c", "#100b10", "#25141d", "#fbe8ec", "#c9aab7", "💀"),
        ProfileTheme("chaos", "Violet Rupture", "REALITY IS A SUGGESTION.",
                     "Shattered dimensions, amethyst lightning and an eldritch eye.",
                     "#d0a1ff", "#7950ac", "#110d20", "#211733", "#f5eaff", "#c8b3e4", "🌀"),
        ProfileTheme("good", "Dawnward", "THE DAWN STANDS WITH YOU.",
                     "A winged celestial guardian in pearl, sun gold and azure.",
                     "#f2d58b", "#827454", "#101c2a", "#1c2c3c", "#fff8e7", "#bfceda", "☀️"),
        ProfileTheme("forest", "Verdant Oath", "THE OLD WORLD REMEMBERS.",
                     "A sacred antlered spirit beneath an emerald forest cathedral.",
                     "#ade0a5", "#4e8266", "#0b1916", "#142d25", "#edf7df", "#b0cebb", "🌿"),
        ProfileTheme("frost", "Winterveil", "EVEN ETERNITY CAN FREEZE.",
                     "An ice-crowned sovereign, silver spires and midnight auroras.",
                     "#afe7ff", "#4e7d9e", "#0b1421", "#17283a", "#edf9ff", "#b5ccdf", "❄️"),
    )
}

ALIASES = {
    "normal": "classic", "plain": "classic", "default": "classic", "reset": "classic",
    "fire": "dragon", "sinister": "evil", "dark": "evil", "purple": "chaos",
    "light": "good", "angel": "good", "nature": "forest", "ice": "frost",
    **{theme.name.lower(): theme.key for theme in THEMES.values()},
}


def resolve_theme(value):
    """Strict for user input; callers explicitly decide when to fall back."""
    key = str(value or "").strip().lower()
    return THEMES.get(ALIASES.get(key, key))


@lru_cache(maxsize=32)
def theme_font(size, role="body"):
    filename = {"title": "Cinzel.ttf", "heading": "Lato-Bold.ttf"}.get(role, "Lato-Regular.ttf")
    try:
        return ImageFont.truetype(str(ASSET_ROOT / "fonts" / filename), size)
    except OSError:
        return ImageFont.truetype(str(ASSET_ROOT.parents[1] / "EightBitDragon-anqx.ttf"), size)


@lru_cache(maxsize=6)
def _banner(key):
    """Cache only decoded source banners, never a user's composed card."""
    with Image.open(ASSET_ROOT / f"{key}.png") as source:
        return ImageOps.fit(source.convert("RGB"), (1660, 554), method=Image.Resampling.LANCZOS)


def theme_background(theme, size):
    canvas = Image.new("RGBA", size, theme.background)
    draw = ImageDraw.Draw(canvas)
    width, height = size
    # Engraved diagonals and a double metal rim; all decoration stays in the gutters.
    for x in range(-height, width, 70):
        draw.line((x, 0, x + height, height), fill=theme.panel, width=1)
    draw.rounded_rectangle((24, 24, width - 24, height - 24), 24,
                           fill=theme.background, outline=theme.secondary, width=2)
    draw.rounded_rectangle((35, 35, width - 35, height - 35), 19,
                           outline=theme.panel, width=2)
    for x in (24, width - 24):
        for y in (24, height - 24):
            draw.polygon([(x, y - 9), (x + 9, y), (x, y + 9), (x - 9, y)], fill=theme.accent)
    return canvas


def add_theme_banner(card, theme):
    """A full-width painted banner above the existing readable stat layout."""
    result = Image.new("RGB", (1660, 1460), theme.background)
    try:
        result.paste(_banner(theme.key), (0, 0))
    except (OSError, ValueError):
        # Missing optional artwork must never prevent someone viewing their stats.
        pass
    overlay = Image.new("RGBA", (1660, 554))
    shade = ImageDraw.Draw(overlay)
    for x in range(850):
        shade.line((x, 0, x, 554), fill=(4, 6, 12, int(125 * (1 - x / 850))))
    result.paste(overlay, (0, 0), overlay)
    overlay = Image.new("RGBA", (1660, 554))
    shade = ImageDraw.Draw(overlay)
    rgb = Image.new("RGB", (1, 1), theme.background).getpixel((0, 0))
    for y in range(414, 520):
        shade.line((0, y, 1660, y), fill=(*rgb, int(255 * (y - 414) / 105)))
    result.paste(overlay, (0, 0), overlay)
    result.paste(card.convert("RGB"), (0, 520))
    draw = ImageDraw.Draw(result)
    draw.text((64, 68), "F A B L E   /   R E B O R N", font=theme_font(22, "heading"), fill=theme.accent)
    draw.line((64, 118, 280, 118), fill=theme.accent, width=2)
    words = theme.name.upper().split()
    lines = [theme.name.upper()] if len(words) == 1 else [" ".join(words[:-1]), words[-1]]
    y = 160
    for line in lines:
        size = 70
        while draw.textlength(line, font=theme_font(size, "title")) > 730 and size > 32:
            size -= 2
        draw.text((60, y), line, font=theme_font(size, "title"), fill="#fff7ea",
                  stroke_width=1, stroke_fill="#19202a")
        y += 90
    draw.text((64, y + 20), theme.epithet, font=theme_font(23, "heading"), fill=theme.accent)
    draw.text((64, 465), "H E R O   C H R O N I C L E", font=theme_font(18), fill=theme.muted)
    draw.line((64, 510, 1596, 510), fill=theme.secondary, width=1)
    draw.polygon([(821, 510), (830, 501), (839, 510), (830, 519)], fill=theme.accent)
    return result

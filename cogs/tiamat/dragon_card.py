"""Pillow renderer for the shareable Tiamat dragon card ($dragon).

Everyone in Tiamat plays Az'uar, renamed and recoloured, so the art is Az'uar's
idle battle pose hue-shifted exactly as the game does (TiamatOnline.js
shiftPixelsHue). Nothing players upload ever reaches the card. Rendering is pure
and runs in a worker thread.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from io import BytesIO
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from cogs.companions.card import (
    GOLD, INK, MUTED, TEXT, _art, _crop_focus, _gradient, _layer, _mix, _pill, bold, display, regular,
)
from cogs.companions.roster import BY_KEY as COMPANIONS

ART = Path(__file__).resolve().parents[2] / "assets" / "tiamat" / "dragonbat2.png"
WIDTH, HEIGHT = 1200, 700
MARGIN = 56
CELL = 144            # dragonbat2 is 3 frames x 8 poses of 144px
IDLE = (1, 2)         # middle frame of pose row 2, the "Idle Stance"
DRAGON_SCALE = 3
BASE_BLUE = (52, 120, 232)  # Az'uar's body colour before the player's hue shift

# Mirrors TiamatProgression.js FORMS: display name, tier, elements.
E, F, A, W = "Earth", "Fire", "Air", "Water"
FORMS = {
    "whelp": ("Whelp", 0, ()),
    "earth": ("Earth Dragon", 1, (E,)), "fire": ("Fire Dragon", 1, (F,)), "air": ("Air Dragon", 1, (A,)), "water": ("Water Dragon", 1, (W,)),
    "onix": ("Onix Dragon", 2, (E,)), "volcanic": ("Volcanic Dragon", 2, (E, F)), "desert": ("Desert Dragon", 2, (E, A)),
    "forest": ("Forest Dragon", 2, (E, W)), "flare": ("Flare Dragon", 2, (F,)), "storm": ("Storm Dragon", 2, (F, A)),
    "vapor": ("Vapor Dragon", 2, (F, W)), "sky": ("Sky Dragon", 2, (A,)), "tundra": ("Tundra Dragon", 2, (A, W)),
    "crystal": ("Crystal Dragon", 2, (W,)),
    "titan": ("Titan Dragon", 3, (E,)), "fusion": ("Fusion Dragon", 3, (E, F)), "pharaoh": ("Pharaoh Dragon", 3, (E, A)),
    "sacred": ("Sacred Dragon", 3, (E, W)), "demon": ("Demon Dragon", 3, (E, F)), "cursed": ("Cursed Dragon", 3, (E, F, A)),
    "saint": ("Saint Dragon", 3, (E, F, W)), "meteor": ("Meteor Dragon", 3, (E, A)), "gaia": ("Gaia Dragon", 3, (E, A, W)),
    "diamond": ("Diamond Dragon", 3, (E, W)), "inferno": ("Inferno Dragon", 3, (F,)), "torment": ("Torment Dragon", 3, (A, F)),
    "phantom": ("Phantom Dragon", 3, (F, W)), "nova": ("Nova Dragon", 3, (F, A)), "chaos": ("Chaos Dragon", 3, (F, A, W)),
    "ruby": ("Ruby Dragon", 3, (F, W)), "zephyr": ("Zephyr Dragon", 3, (A,)), "comet": ("Comet Dragon", 3, (A, W)),
    "emerald": ("Emerald Dragon", 3, (A, W)), "sapphire": ("Sapphire Dragon", 3, (W,)),
}
# Mirrors the server's progression.js TITLES.
TITLES = {
    "firstborn": "Firstborn", "remembers_jardan": "Remembers Jardan", "fought_bravely": "Fought Bravely",
    "freed_blades": "Freed the Blades", "ring_champion": "Ring of Fire Champion",
    "tiamats_blessed": "Tiamat's Blessed", "only_hope": "Only Hope",
}
ELEMENT_COLOURS = {E: (196, 154, 90), F: (255, 154, 46), A: (158, 240, 207), W: (127, 212, 255)}
RUNE_ORDER = (E, F, A, W)
SOUL_GEMS = 7
FIRSTBORN_LIMIT = 100


@dataclass(frozen=True)
class DragonCard:
    name: str
    hue: int = 0
    form: str = "whelp"
    title: str | None = None
    hatched_on: str | None = None       # already formatted, e.g. "4 Oct 2026"
    hatch_rank: int | None = None
    level: int | None = None
    playtime_seconds: int | None = None
    battles_won: int | None = None
    runes: tuple | None = None          # (earth, fire, air, water); None until the game reports a journey
    runes_sealed: int = 0
    soul_gems: int = 0
    story: str = "journey"              # "journey", "complete" or "true_ending"
    companion: str | None = None
    companions_unlocked: int = 0
    titles_earned: int = 0


# ---- art -----------------------------------------------------------------------
def shift_hue(image, hue):
    """TiamatOnline.js shiftPixelsHue: rotate every coloured pixel's hue in HSL, keeping S and L."""
    if not hue % 360:
        return image
    pixels = np.asarray(image.convert("RGBA"), dtype=np.float64)
    rgb = pixels[..., :3] / 255
    red, green, blue = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    maximum, minimum = rgb.max(axis=2), rgb.min(axis=2)
    chroma = maximum - minimum
    mask = (pixels[..., 3] > 0) & (chroma > 0)
    safe = np.where(chroma > 0, chroma, 1)
    source = np.where(maximum == red, ((green - blue) / safe + 6) % 6,
                      np.where(maximum == green, (blue - red) / safe + 2, (red - green) / safe + 4))
    section = ((source / 6 + hue / 360) % 1) * 6
    secondary = chroma * (1 - np.abs(section % 2 - 1))
    zero = np.zeros_like(chroma)
    band = np.floor(section).clip(0, 5)
    choices = [
        (chroma, secondary, zero), (secondary, chroma, zero), (zero, chroma, secondary),
        (zero, secondary, chroma), (secondary, zero, chroma), (chroma, zero, secondary),
    ]
    match = (maximum + minimum) / 2 - chroma / 2
    for channel in range(3):
        value = np.select([band == index for index in range(6)], [choice[channel] for choice in choices])
        pixels[..., channel] = np.where(mask, np.round((value + match) * 255), pixels[..., channel])
    return Image.fromarray(pixels.astype(np.uint8), "RGBA")


def accent_for(hue):
    swatch = Image.new("RGBA", (1, 1), BASE_BLUE + (255,))
    return shift_hue(swatch, hue).getpixel((0, 0))[:3]


@lru_cache(maxsize=64)
def _dragon(hue):
    with Image.open(ART) as sheet:
        column, row = IDLE
        frame = sheet.convert("RGBA").crop((column * CELL, row * CELL, (column + 1) * CELL, (row + 1) * CELL))
    frame = frame.crop(frame.getbbox() or (0, 0, CELL, CELL))
    frame = shift_hue(frame, hue)
    return frame.resize((frame.width * DRAGON_SCALE, frame.height * DRAGON_SCALE), Image.NEAREST)


AURA_PAD = 120


def _aura(dragon, colours, tier):
    """A soft halo in the form's element colours, AURA_PAD larger on every side; stronger for higher tiers."""
    size = (dragon.width + 2 * AURA_PAD, dragon.height + 2 * AURA_PAD)
    alpha = Image.new("L", size, 0)
    alpha.paste(dragon.getchannel("A"), (AURA_PAD, AURA_PAD))
    halo = Image.new("RGBA", size, (0, 0, 0, 0))
    strength = 0.9 + 0.35 * tier
    for index, colour in enumerate(colours):
        layer = Image.new("RGBA", size, colour + (0,))
        blur = 22 + 8 * tier + 10 * index
        layer.putalpha(alpha.filter(ImageFilter.GaussianBlur(blur)).point(lambda v: min(200, round(v * strength))))
        halo.alpha_composite(layer)
    return halo


# ---- layout --------------------------------------------------------------------
def _playtime(seconds):
    hours, remainder = divmod(max(0, int(seconds or 0)), 3600)
    return f"{hours:,}h {remainder // 60:02d}m"


def _number(value):
    return "—" if value is None else f"{int(value):,}"


def _background(accent):
    canvas = _gradient((WIDTH, HEIGHT), _mix(accent, INK, 0.72), INK)
    glow = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    draw = ImageDraw.Draw(glow)
    draw.ellipse((640, 40, 1220, 640), fill=accent + (120,))
    draw.ellipse((-200, 420, 500, 900), fill=_mix(accent, INK, 0.4) + (70,))
    canvas.alpha_composite(glow.filter(ImageFilter.GaussianBlur(110)))

    def slashes(draw):
        draw.polygon([(700, 0), (790, 0), (560, HEIGHT), (470, HEIGHT)], fill=accent + (34,))
        draw.polygon([(812, 0), (826, 0), (596, HEIGHT), (582, HEIGHT)], fill=accent + (60,))

    _layer(canvas, slashes)
    return canvas


def _stat(draw, x, y, label, value, accent):
    draw.rounded_rectangle((x, y, x + 196, y + 76), radius=14, fill=(16, 16, 22), outline=_mix(accent, INK, 0.3), width=2)
    draw.text((x + 16, y + 12), label, font=bold(14), fill=MUTED)
    draw.text((x + 16, y + 34), value, font=bold(28), fill=TEXT)


def _runes(draw, card, x, y):
    draw.text((x, y), "RUNES INHALED", font=bold(16), fill=MUTED)
    y += 30
    if card.runes is None:
        draw.text((x, y + 4), "Play Tiamat online to record this dragon's journey.", font=regular(20), fill=MUTED)
        return
    largest = max(1, *card.runes)
    for element, count in zip(RUNE_ORDER, card.runes):
        colour = ELEMENT_COLOURS[element]
        draw.ellipse((x, y + 4, x + 14, y + 18), fill=colour)
        draw.text((x + 24, y + 11), element, font=bold(18), fill=TEXT, anchor="lm")
        left, right = x + 100, x + 520
        draw.rounded_rectangle((left, y + 4, right, y + 18), radius=7, fill=(46, 46, 58))
        filled = left + round((right - left) * count / largest)
        if count:
            draw.rounded_rectangle((left, y + 4, max(left + 14, filled), y + 18), radius=7, fill=colour)
        draw.text((right + 14, y + 11), f"{count:,}", font=bold(18), fill=TEXT, anchor="lm")
        y += 30
    draw.text((x, y + 4), f"{card.runes_sealed:,} Runes sealed", font=regular(18), fill=MUTED)


def _gems(draw, card, x, y):
    draw.text((x, y), "SOUL GEMS", font=bold(16), fill=MUTED)
    draw.text((x + 112, y), f"{card.soul_gems} / {SOUL_GEMS}", font=bold(16), fill=GOLD if card.soul_gems == SOUL_GEMS else TEXT)
    y += 28
    for index in range(SOUL_GEMS):
        cx, cy, r = x + 14 + index * 40, y + 16, 14
        shape = [(cx, cy - r), (cx + r * 0.8, cy), (cx, cy + r), (cx - r * 0.8, cy)]
        if index < card.soul_gems:
            draw.polygon(shape, fill=_mix(GOLD, (255, 255, 255), 0.25), outline=GOLD)
        else:
            draw.polygon(shape, outline=(110, 110, 124))


def _footer(canvas, card, accent):
    def strip(draw):
        draw.rectangle((0, HEIGHT - 84, WIDTH, HEIGHT), fill=INK + (215,))
        draw.line((0, HEIGHT - 84, WIDTH, HEIGHT - 84), fill=accent + (160,), width=2)

    _layer(canvas, strip)
    draw = ImageDraw.Draw(canvas)
    y = HEIGHT - 59
    labels = {"journey": ("ON THE JOURNEY", (70, 74, 90), TEXT), "complete": ("STORY COMPLETE", accent, INK),
              "true_ending": ("TRUE ENDING", GOLD, INK)}
    label, fill, text = labels.get(card.story, labels["journey"])
    x = _pill(draw, (MARGIN, y), label, fill, text) + 18

    companion = COMPANIONS.get(card.companion or "")
    if companion is not None:
        portrait = _art(companion.key, "portrait")
        if portrait is not None:
            face = _crop_focus(portrait, companion.focus, companion.zoom, (44, 44))
            mask = Image.new("L", (44, 44), 0)
            ImageDraw.Draw(mask).ellipse((0, 0, 43, 43), fill=255)
            canvas.paste(face, (x, y - 5), mask)
            draw.ellipse((x - 1, y - 6, x + 44, y + 39), outline=companion.accent, width=2)
            x += 54
        draw.text((x, y + 2), f"With {companion.name}", font=bold(18), fill=TEXT)
        draw.text((x, y + 24), f"{card.companions_unlocked} companion{'s' if card.companions_unlocked != 1 else ''}", font=regular(14), fill=MUTED)
    else:
        draw.text((x, y + 2), f"{card.companions_unlocked} companion{'s' if card.companions_unlocked != 1 else ''}", font=bold(18), fill=TEXT)
        draw.text((x, y + 24), "Use $companions to choose one", font=regular(14), fill=MUTED)
    x += 240
    draw.text((x, y + 2), f"{card.titles_earned} / {len(TITLES)} titles", font=bold(18), fill=TEXT)
    draw.text((x, y + 24), "Earned in the story", font=regular(14), fill=MUTED)
    draw.text((WIDTH - MARGIN, y + 17), "THE TIAMAT SACRAMENT", font=display(20), fill=_mix(accent, TEXT, 0.55), anchor="rm")


def _render(card):
    accent = accent_for(card.hue)
    form_name, tier, elements = FORMS.get(card.form, FORMS["whelp"])
    canvas = _background(accent)

    dragon = _dragon(card.hue % 360)
    halo_colours = [ELEMENT_COLOURS[element] for element in elements] or [_mix(accent, (255, 255, 255), 0.3)]
    position = (WIDTH - dragon.width - 40, HEIGHT - 84 - dragon.height - 10)

    def shadow(draw):
        cx, cy = position[0] + dragon.width // 2, position[1] + dragon.height - 6
        draw.ellipse((cx - 170, cy - 18, cx + 170, cy + 18), fill=(0, 0, 0, 120))

    _layer(canvas, shadow)
    canvas.alpha_composite(_aura(dragon, halo_colours, tier), (position[0] - AURA_PAD, position[1] - AURA_PAD))
    canvas.alpha_composite(dragon, position)

    draw = ImageDraw.Draw(canvas)
    draw.text((MARGIN, 38), "DRAGON OF THE CLUTCH", font=bold(16), fill=_mix(accent, TEXT, 0.5))
    draw.text((MARGIN, 60), card.name, font=display(68), fill=TEXT, stroke_width=2, stroke_fill=INK)
    y = 150
    x = _pill(draw, (MARGIN, y), form_name.upper(), accent if tier else (70, 74, 90), INK if tier else TEXT)
    if card.title in TITLES:
        _pill(draw, (x, y), TITLES[card.title].upper(), GOLD)
    y += 50
    hatched = f"Hatched {card.hatched_on}" if card.hatched_on else "Not yet hatched"
    if card.hatch_rank and card.hatch_rank <= FIRSTBORN_LIMIT:
        hatched += f"  ·  Firstborn #{card.hatch_rank}"
    elif card.hatch_rank:
        hatched += f"  ·  Dragon #{card.hatch_rank:,}"
    draw.text((MARGIN, y), hatched, font=regular(20), fill=MUTED)

    y += 44
    _stat(draw, MARGIN, y, "LEVEL", _number(card.level), accent)
    _stat(draw, MARGIN + 212, y, "PLAYTIME", _playtime(card.playtime_seconds) if card.playtime_seconds is not None else "—", accent)
    _stat(draw, MARGIN + 424, y, "BATTLES WON", _number(card.battles_won), accent)

    _runes(draw, card, MARGIN, y + 104)
    _gems(draw, card, MARGIN, HEIGHT - 84 - 78)
    _footer(canvas, card, accent)

    output = BytesIO()
    canvas.convert("RGB").save(output, format="PNG", optimize=True)
    return output.getvalue()


def render_dragon_card(card: DragonCard) -> BytesIO:
    return BytesIO(_render(card))

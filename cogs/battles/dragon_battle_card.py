"""Fast Pillow renderer for the optional Ice Dragon live battle card."""

import re
import unicodedata
from functools import lru_cache
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


PROJECT_ROOT = Path(__file__).resolve().parents[2]
TEMPLATE_PATH = PROJECT_ROOT / "dragonbattle.png"
DISPLAY_FONT_PATH = PROJECT_ROOT / "EightBitDragon-anqx.ttf"

WHITE = (238, 247, 255, 255)
ICE = (94, 218, 255, 255)
MUTED = (155, 184, 205, 255)
DARK = (2, 8, 16, 255)

PLAYER_CARDS = (
    (20, 565, 415, 764),
    (432, 565, 823, 764),
    (841, 565, 1232, 764),
    (1248, 565, 1644, 764),
)
PET_CARDS = (
    (20, 778, 415, 931),
    (432, 778, 823, 931),
    (841, 778, 1232, 931),
    (1248, 778, 1644, 931),
)


@lru_cache(maxsize=1)
def _load_template():
    if not TEMPLATE_PATH.exists():
        raise FileNotFoundError(f"Missing Ice Dragon battle template: {TEMPLATE_PATH}")
    with Image.open(TEMPLATE_PATH) as template:
        return template.convert("RGB")


@lru_cache(maxsize=64)
def _font(size, display=False):
    candidates = []
    if display:
        candidates.append(DISPLAY_FONT_PATH)
    candidates.extend(
        (
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
            Path("C:/Windows/Fonts/arialbd.ttf"),
            DISPLAY_FONT_PATH,
        )
    )
    for candidate in candidates:
        try:
            return ImageFont.truetype(str(candidate), size=size)
        except OSError:
            continue
    return ImageFont.load_default()


def _clean_text(value):
    text = str(value or "")
    text = re.sub(r"<a?:[^:>]+:\d+>", "", text)
    text = text.replace("**", "").replace("__", "").replace("`", "")
    text = " ".join(text.replace("\n", " ").split())
    return "".join(
        character
        for character in text
        if unicodedata.category(character) not in {"So", "Cs", "Cc"}
    ).strip()


def _fit_text(draw, text, max_width, start_size, min_size=12, display=False):
    text = _clean_text(text)
    for size in range(start_size, min_size - 1, -1):
        candidate_font = _font(size, display=display)
        if draw.textlength(text, font=candidate_font) <= max_width:
            return text, candidate_font

    candidate_font = _font(min_size, display=display)
    shortened = text
    while shortened:
        shortened = shortened[:-1].rstrip()
        candidate = f"{shortened}..."
        if draw.textlength(candidate, font=candidate_font) <= max_width:
            return candidate, candidate_font
    return "...", candidate_font


def _draw_text(draw, xy, text, text_font, fill=WHITE, anchor="la", stroke=2):
    draw.text(
        xy,
        str(text),
        font=text_font,
        fill=fill,
        anchor=anchor,
        stroke_width=stroke,
        stroke_fill=DARK,
    )


def _stat(value):
    return f"{float(value or 0):,.0f}"


def _hp_ratio(current, maximum):
    maximum = float(maximum or 0)
    if maximum <= 0:
        return 0.0
    return max(0.0, min(float(current or 0) / maximum, 1.0))


def _hp_color(ratio):
    if ratio > 0.60:
        return (42, 194, 238, 235)
    if ratio > 0.30:
        return (245, 178, 67, 235)
    return (225, 66, 82, 235)


def _draw_hp_bar(draw, box, current, maximum, font_size):
    left, top, right, bottom = box
    ratio = _hp_ratio(current, maximum)
    radius = max(4, (bottom - top) // 3)
    draw.rounded_rectangle(box, radius=radius, fill=(3, 12, 23, 225))
    fill_right = left + int((right - left) * ratio)
    if fill_right > left:
        draw.rounded_rectangle(
            (left, top, fill_right, bottom),
            radius=radius,
            fill=_hp_color(ratio),
        )
    draw.rounded_rectangle(
        box,
        radius=radius,
        outline=(116, 204, 238, 220),
        width=2,
    )
    _draw_text(
        draw,
        ((left + right) // 2, (top + bottom) // 2),
        f"{_stat(current)} / {_stat(maximum)}",
        _font(font_size),
        anchor="mm",
    )
    return ratio


def _draw_boss(draw, boss):
    title, title_font = _fit_text(
        draw,
        f"{boss['name']}  |  LV. {boss['level']}",
        440,
        28,
        18,
        display=True,
    )
    _draw_text(draw, (318, 101), title, title_font, fill=ICE, anchor="mm")
    ratio = _draw_hp_bar(
        draw,
        (90, 168, 785, 207),
        boss["hp"],
        boss["max_hp"],
        21,
    )
    _draw_text(draw, (701, 251), f"{ratio:.0%}", _font(24, display=True), anchor="mm")
    _draw_text(draw, (196, 315), f"ATK  {_stat(boss['attack'])}", _font(22), anchor="mm")
    _draw_text(draw, (433, 315), f"DEF  {_stat(boss['defense'])}", _font(22), anchor="mm")
    statuses = " | ".join(boss.get("statuses") or ["No effects"])
    statuses, status_font = _fit_text(draw, statuses, 190, 19, 12)
    _draw_text(draw, (689, 315), statuses, status_font, fill=MUTED, anchor="mm")


def _draw_battle_log(draw, turn, entries):
    _draw_text(
        draw,
        (85, 427),
        f"BATTLE LOG  |  TURN {turn}",
        _font(24, display=True),
        fill=ICE,
    )
    colors = (WHITE, (200, 225, 240, 255), MUTED)
    for index, entry in enumerate(entries[-3:]):
        entry, entry_font = _fit_text(draw, entry, 1450, 20, 14)
        _draw_text(draw, (85, 464 + index * 26), entry, entry_font, fill=colors[index])


def _draw_statuses(draw, card, statuses):
    left, _, _, _ = card
    centers = (left + 73, left + 111, left + 149, left + 187, left + 225, left + 263)
    for center, status_name in zip(centers, statuses[:6]):
        short = _clean_text(status_name)[:2].upper()
        _draw_text(draw, (center, 734), short, _font(12), fill=ICE, anchor="mm", stroke=1)


def _draw_player(draw, card, player):
    left, top, right, _ = card
    name, name_font = _fit_text(
        draw,
        f"{player['name']}  |  LV. {player['level']}  |  {player['class']}",
        right - left - 65,
        21,
        13,
        display=True,
    )
    _draw_text(draw, (left + 34, top + 34), name, name_font, fill=ICE)
    ratio = _draw_hp_bar(
        draw,
        (left + 47, top + 70, left + 282, top + 91),
        player["hp"],
        player["max_hp"],
        13,
    )
    _draw_text(draw, (right - 62, top + 80), f"{ratio:.0%}", _font(16), anchor="mm")
    _draw_text(draw, (left + 130, top + 126), f"ATK  {_stat(player['attack'])}", _font(17), anchor="mm")
    _draw_text(draw, (left + 303, top + 126), f"DEF  {_stat(player['defense'])}", _font(17), anchor="mm")
    _draw_statuses(draw, card, player.get("statuses") or [])


def _draw_pet(draw, card, pet):
    left, top, right, _ = card
    if not pet:
        _draw_text(
            draw,
            ((left + right) // 2, top + 39),
            "NO PET EQUIPPED",
            _font(19, display=True),
            fill=MUTED,
            anchor="mm",
        )
        return

    name, name_font = _fit_text(
        draw,
        f"{pet['name']}  |  LV. {pet['level']}",
        right - left - 90,
        19,
        12,
        display=True,
    )
    _draw_text(draw, (left + 70, top + 34), name, name_font, fill=ICE)
    ratio = _draw_hp_bar(
        draw,
        (left + 47, top + 75, left + 282, top + 94),
        pet["hp"],
        pet["max_hp"],
        12,
    )
    _draw_text(draw, (right - 62, top + 84), f"{ratio:.0%}", _font(15), anchor="mm")
    _draw_text(draw, (left + 130, top + 127), f"ATK  {_stat(pet['attack'])}", _font(16), anchor="mm")
    _draw_text(draw, (left + 303, top + 127), f"DEF  {_stat(pet['defense'])}", _font(16), anchor="mm")


def render_dragon_battle_card(data):
    image = _load_template().copy()
    draw = ImageDraw.Draw(image, "RGBA")
    _draw_boss(draw, data["boss"])
    _draw_battle_log(draw, data.get("turn", 0), data.get("log", []))

    players = list(data.get("players", []))[:4]
    for card, player in zip(PLAYER_CARDS, players):
        _draw_player(draw, card, player)
    for card, player in zip(PET_CARDS, players):
        _draw_pet(draw, card, player.get("pet"))

    output = BytesIO()
    image.save(
        output,
        format="JPEG",
        quality=90,
        subsampling=0,
        optimize=False,
        progressive=False,
    )
    output.seek(0)
    return output

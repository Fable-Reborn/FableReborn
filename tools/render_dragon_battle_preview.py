"""Render a standalone Ice Dragon battle-card preview.

Run from the repository root:
    python tools/render_dragon_battle_preview.py
"""

import argparse
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TEMPLATE = ROOT / "dragonbattle.png"
DEFAULT_OUTPUT = ROOT / "dragonbattle_preview.jpg"
DISPLAY_FONT = ROOT / "EightBitDragon-anqx.ttf"

WHITE = (238, 247, 255, 255)
ICE = (94, 218, 255, 255)
MUTED = (155, 184, 205, 255)
GOLD = (255, 216, 120, 255)
DANGER = (255, 91, 103, 255)
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


@lru_cache(maxsize=64)
def font(size, display=False):
    candidates = []
    if display:
        candidates.append(DISPLAY_FONT)
    candidates.extend(
        (
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
            Path("C:/Windows/Fonts/arialbd.ttf"),
            DISPLAY_FONT,
        )
    )
    for candidate in candidates:
        try:
            return ImageFont.truetype(str(candidate), size=size)
        except OSError:
            continue
    return ImageFont.load_default()


def fit_text(draw, text, max_width, start_size, min_size=12, display=False):
    text = str(text)
    for size in range(start_size, min_size - 1, -1):
        candidate_font = font(size, display=display)
        if draw.textlength(text, font=candidate_font) <= max_width:
            return text, candidate_font

    candidate_font = font(min_size, display=display)
    shortened = text
    while shortened:
        shortened = shortened[:-1].rstrip()
        candidate = f"{shortened}..."
        if draw.textlength(candidate, font=candidate_font) <= max_width:
            return candidate, candidate_font
    return "...", candidate_font


def draw_text(draw, xy, text, text_font, fill=WHITE, anchor="la", stroke=2):
    draw.text(
        xy,
        str(text),
        font=text_font,
        fill=fill,
        anchor=anchor,
        stroke_width=stroke,
        stroke_fill=DARK,
    )


def stat(value):
    return f"{float(value):,.0f}"


def hp_ratio(current, maximum):
    if maximum <= 0:
        return 0.0
    return max(0.0, min(float(current) / float(maximum), 1.0))


def hp_color(ratio):
    if ratio > 0.60:
        return (42, 194, 238, 235)
    if ratio > 0.30:
        return (245, 178, 67, 235)
    return (225, 66, 82, 235)


def draw_hp_bar(draw, box, current, maximum, font_size, show_values=True):
    left, top, right, bottom = box
    ratio = hp_ratio(current, maximum)
    radius = max(4, (bottom - top) // 3)
    draw.rounded_rectangle(box, radius=radius, fill=(3, 12, 23, 225))
    fill_right = left + int((right - left) * ratio)
    if fill_right > left:
        draw.rounded_rectangle(
            (left, top, fill_right, bottom),
            radius=radius,
            fill=hp_color(ratio),
        )
    draw.rounded_rectangle(
        box,
        radius=radius,
        outline=(116, 204, 238, 220),
        width=2,
    )
    if show_values:
        label = f"{stat(current)} / {stat(maximum)}"
        draw_text(
            draw,
            ((left + right) // 2, (top + bottom) // 2),
            label,
            font(font_size),
            anchor="mm",
            stroke=2,
        )
    return ratio


def draw_boss(draw, boss):
    title = f"{boss['name']}  |  LV. {boss['level']}"
    title, title_font = fit_text(draw, title, 440, 28, 18, display=True)
    draw_text(draw, (318, 101), title, title_font, fill=ICE, anchor="mm")

    ratio = draw_hp_bar(
        draw,
        (90, 168, 785, 207),
        boss["hp"],
        boss["max_hp"],
        font_size=21,
    )
    draw_text(draw, (701, 251), f"{ratio:.0%}", font(24, display=True), anchor="mm")

    draw_text(draw, (196, 315), f"ATK  {stat(boss['attack'])}", font(22), anchor="mm")
    draw_text(draw, (433, 315), f"DEF  {stat(boss['defense'])}", font(22), anchor="mm")
    status = " | ".join(boss.get("statuses") or ["No effects"])
    status, status_font = fit_text(draw, status, 190, 19, 12)
    draw_text(draw, (689, 315), status, status_font, fill=MUTED, anchor="mm")


def draw_battle_log(draw, turn, entries):
    draw_text(draw, (85, 427), f"BATTLE LOG  |  TURN {turn}", font(24, display=True), fill=ICE)
    colors = (WHITE, (200, 225, 240, 255), MUTED)
    for index, entry in enumerate(entries[-3:]):
        entry, entry_font = fit_text(draw, entry, 1450, 20, 14)
        draw_text(draw, (85, 464 + index * 26), entry, entry_font, fill=colors[index])


def draw_statuses(draw, card, statuses):
    left, _, _, _ = card
    centers = (left + 73, left + 111, left + 149, left + 187, left + 225, left + 263)
    for center, status_name in zip(centers, statuses[:6]):
        short = str(status_name).strip()[:2].upper()
        draw_text(draw, (center, 734), short, font(12), fill=ICE, anchor="mm", stroke=1)


def draw_player(draw, card, player):
    left, top, right, _ = card
    name = f"{player['name']}  |  LV. {player['level']}  |  {player['class']}"
    name, name_font = fit_text(draw, name, right - left - 65, 21, 13, display=True)
    draw_text(draw, (left + 34, top + 34), name, name_font, fill=ICE)

    ratio = draw_hp_bar(
        draw,
        (left + 47, top + 70, left + 282, top + 91),
        player["hp"],
        player["max_hp"],
        font_size=13,
    )
    draw_text(draw, (right - 62, top + 80), f"{ratio:.0%}", font(16), anchor="mm")
    draw_text(draw, (left + 130, top + 126), f"ATK  {stat(player['attack'])}", font(17), anchor="mm")
    draw_text(draw, (left + 303, top + 126), f"DEF  {stat(player['defense'])}", font(17), anchor="mm")
    draw_statuses(draw, card, player.get("statuses") or [])


def draw_pet(draw, card, pet):
    left, top, right, _ = card
    if not pet:
        draw_text(
            draw,
            ((left + right) // 2, top + 39),
            "NO PET EQUIPPED",
            font(19, display=True),
            fill=MUTED,
            anchor="mm",
        )
        return

    name = f"{pet['name']}  |  LV. {pet['level']}"
    name, name_font = fit_text(draw, name, right - left - 90, 19, 12, display=True)
    draw_text(draw, (left + 70, top + 34), name, name_font, fill=ICE)

    ratio = draw_hp_bar(
        draw,
        (left + 47, top + 75, left + 282, top + 94),
        pet["hp"],
        pet["max_hp"],
        font_size=12,
    )
    draw_text(draw, (right - 62, top + 84), f"{ratio:.0%}", font(15), anchor="mm")
    draw_text(draw, (left + 130, top + 127), f"ATK  {stat(pet['attack'])}", font(16), anchor="mm")
    draw_text(draw, (left + 303, top + 127), f"DEF  {stat(pet['defense'])}", font(16), anchor="mm")


def sample_battle():
    return {
        "turn": 55,
        "boss": {
            "name": "Polar Vortex",
            "level": 32,
            "hp": 18420,
            "max_hp": 43050,
            "attack": 1189,
            "defense": 902,
            "statuses": ["Armor Broken", "Poisoned"],
        },
        "log": [
            "Noctridium [FINAL] tears through Polar Vortex for 3,842 damage.",
            "Polar Vortex casts Frozen Cataclysm across the hunting party.",
            "Lunar blocks 1,205 damage. Frostwarden is frozen for 1 turn.",
        ],
        "players": [
            {
                "name": "Lunar",
                "level": 71,
                "class": "Tank / Mage",
                "hp": 4627,
                "max_hp": 6900,
                "attack": 1589,
                "defense": 2253,
                "statuses": ["Shield", "Regen"],
                "pet": {
                    "name": "Noctridium [FINAL]",
                    "level": 100,
                    "hp": 13240,
                    "max_hp": 19316,
                    "attack": 19527,
                    "defense": 14388,
                },
            },
            {
                "name": "Frostwarden",
                "level": 64,
                "class": "Warrior",
                "hp": 1940,
                "max_hp": 6130,
                "attack": 2880,
                "defense": 1710,
                "statuses": ["Frozen", "Bleed"],
                "pet": {
                    "name": "Glacial Hound",
                    "level": 82,
                    "hp": 7820,
                    "max_hp": 8960,
                    "attack": 7420,
                    "defense": 5100,
                },
            },
            {
                "name": "Astra",
                "level": 77,
                "class": "Ritualist",
                "hp": 7010,
                "max_hp": 7210,
                "attack": 3210,
                "defense": 1350,
                "statuses": ["Blessed"],
                "pet": {
                    "name": "Aurora",
                    "level": 91,
                    "hp": 4100,
                    "max_hp": 8200,
                    "attack": 6900,
                    "defense": 4700,
                },
            },
            {
                "name": "Voidwalker",
                "level": 69,
                "class": "Reaper",
                "hp": 720,
                "max_hp": 5480,
                "attack": 4100,
                "defense": 980,
                "statuses": ["Poison", "Doom"],
                "pet": None,
            },
        ],
    }


def render_preview(template_path, output_path):
    data = sample_battle()
    with Image.open(template_path) as template:
        image = template.convert("RGB")

    draw = ImageDraw.Draw(image, "RGBA")
    draw_boss(draw, data["boss"])
    draw_battle_log(draw, data["turn"], data["log"])

    for card, player in zip(PLAYER_CARDS, data["players"]):
        draw_player(draw, card, player)
    for card, player in zip(PET_CARDS, data["players"]):
        draw_pet(draw, card, player.get("pet"))

    image.save(
        output_path,
        format="JPEG",
        quality=90,
        subsampling=0,
        optimize=False,
    )
    return output_path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--template", type=Path, default=DEFAULT_TEMPLATE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    if not args.template.exists():
        raise SystemExit(f"Template not found: {args.template}")
    output = render_preview(args.template, args.output)
    print(f"Rendered preview: {output}")


if __name__ == "__main__":
    main()

from decimal import Decimal
from functools import lru_cache
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


PROJECT_ROOT = Path(__file__).resolve().parents[2]
TEMPLATE_PATH = PROJECT_ROOT / "idctemplate.png"
DISPLAY_FONT_PATH = PROJECT_ROOT / "EightBitDragon-anqx.ttf"

PLAYER_PANELS = (
    (74, 523, 419, 773),
    (451, 523, 798, 773),
    (832, 523, 1180, 773),
    (1219, 523, 1568, 773),
)
PET_PANELS = (
    (74, 787, 419, 873),
    (451, 787, 798, 873),
    (832, 787, 1180, 873),
    (1219, 787, 1568, 873),
)

ICE = (105, 214, 255, 255)
WHITE = (235, 246, 255, 255)
MUTED = (154, 184, 205, 255)
GOLD = (255, 218, 132, 255)
DARK = (2, 10, 20, 255)


@lru_cache(maxsize=128)
def _font(size, display=False):
    if display and DISPLAY_FONT_PATH.exists():
        return ImageFont.truetype(str(DISPLAY_FONT_PATH), size=size)

    candidates = (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "C:/Windows/Fonts/arialbd.ttf",
        str(DISPLAY_FONT_PATH),
    )
    for path in candidates:
        try:
            return ImageFont.truetype(path, size=size)
        except OSError:
            continue
    return ImageFont.load_default()


def _fit_text(draw, text, max_width, start_size, min_size, display=False):
    text = str(text)
    for size in range(start_size, min_size - 1, -1):
        font = _font(size, display=display)
        bounds = draw.textbbox((0, 0), text, font=font)
        if bounds[2] - bounds[0] <= max_width:
            return text, font

    font = _font(min_size, display=display)
    suffix = "..."
    if draw.textbbox((0, 0), suffix, font=font)[2] > max_width:
        return "", font

    shortened = text
    while shortened:
        shortened = shortened[:-1].rstrip()
        candidate = f"{shortened}{suffix}"
        bounds = draw.textbbox((0, 0), candidate, font=font)
        if bounds[2] - bounds[0] <= max_width:
            return candidate, font
    return suffix, font


def _draw_text(draw, position, text, font, fill=WHITE, anchor="la", stroke=2):
    draw.text(
        position,
        str(text),
        font=font,
        fill=fill,
        anchor=anchor,
        stroke_width=stroke,
        stroke_fill=DARK,
    )


def _format_stat(value):
    return f"{Decimal(str(value)):,.0f}"


def _draw_stat_triplet(draw, panel, stats, label_y, value_y):
    left, _, right, _ = panel
    width = right - left
    centers = tuple(left + int(width * ratio) for ratio in (0.18, 0.50, 0.82))
    labels = ("ATK", "DEF", "HP")

    for x, label, value in zip(centers, labels, stats):
        _draw_text(
            draw,
            (x, label_y),
            label,
            _font(19, display=True),
            fill=ICE,
            anchor="ma",
        )
        value_text = _format_stat(value)
        value_text, value_font = _fit_text(
            draw,
            value_text,
            94,
            29,
            19,
            display=False,
        )
        _draw_text(
            draw,
            (x, value_y),
            value_text,
            value_font,
            anchor="ma",
        )


def _draw_boss_panel(draw, dragon):
    left, top, right, _ = (78, 84, 992, 459)
    _draw_text(
        draw,
        (left + 46, top + 42),
        "ICE DRAGON CHALLENGE",
        _font(25, display=True),
        fill=ICE,
    )

    dragon_name = str(dragon.get("name") or "Ice Dragon").upper()
    dragon_name, name_font = _fit_text(
        draw,
        dragon_name,
        right - left - 92,
        58,
        34,
        display=True,
    )
    _draw_text(draw, (left + 46, top + 93), dragon_name, name_font)

    level_text = f"LEVEL {int(dragon.get('level', 1))}"
    _draw_text(
        draw,
        (left + 48, top + 172),
        level_text,
        _font(30, display=True),
        fill=MUTED,
    )

    line_y = top + 235
    draw.line((left + 46, line_y, right - 46, line_y), fill=(74, 149, 190, 180), width=2)
    _draw_stat_triplet(
        draw,
        (left + 25, top, right - 25, top + 340),
        (dragon.get("damage", 0), dragon.get("armor", 0), dragon.get("hp", 0)),
        label_y=top + 270,
        value_y=top + 307,
    )


def _draw_hunters_header(draw, ready_count):
    text = f"HUNTERS  {ready_count}/4  READY"
    font = _font(28, display=True)
    bounds = draw.textbbox((0, 0), text, font=font)
    width = bounds[2] - bounds[0]
    center_x = 836
    draw.rounded_rectangle(
        (center_x - width // 2 - 32, 475, center_x + width // 2 + 32, 516),
        radius=12,
        fill=(2, 12, 25, 235),
        outline=(73, 157, 205, 210),
        width=2,
    )
    _draw_text(draw, (center_x, 496), text, font, fill=ICE, anchor="mm")


def _draw_open_slot(draw, player_panel, pet_panel, index):
    left, top, right, bottom = player_panel
    center_x = (left + right) // 2
    center_y = (top + bottom) // 2
    _draw_text(
        draw,
        (left + 24, top + 25),
        f"HUNTER {index}",
        _font(18, display=True),
        fill=MUTED,
    )
    _draw_text(
        draw,
        (center_x, center_y - 10),
        "OPEN SLOT",
        _font(32, display=True),
        fill=MUTED,
        anchor="mm",
    )
    _draw_text(
        draw,
        (center_x, center_y + 34),
        "JOIN THE PARTY",
        _font(17, display=True),
        fill=(102, 151, 180, 255),
        anchor="mm",
    )

    pet_center_x = (pet_panel[0] + pet_panel[2]) // 2
    pet_center_y = (pet_panel[1] + pet_panel[3]) // 2
    _draw_text(
        draw,
        (pet_center_x, pet_center_y),
        "PET SLOT",
        _font(18, display=True),
        fill=(92, 127, 151, 255),
        anchor="mm",
    )


def _draw_player(draw, player_panel, pet_panel, player, index):
    left, top, right, _ = player_panel
    inner_left = left + 24
    inner_right = right - 24

    _draw_text(
        draw,
        (inner_left, top + 24),
        f"HUNTER {index}",
        _font(18, display=True),
        fill=ICE,
    )
    if player.get("leader"):
        _draw_text(
            draw,
            (inner_right, top + 24),
            "LEADER",
            _font(17, display=True),
            fill=GOLD,
            anchor="ra",
        )

    name = str(player.get("name") or "Unknown Hunter")
    name, name_font = _fit_text(
        draw,
        name,
        inner_right - inner_left,
        34,
        21,
        display=True,
    )
    _draw_text(draw, (inner_left, top + 60), name, name_font)

    detail = f"LV. {int(player.get('level', 1))}  |  {player.get('class') or 'Adventurer'}"
    detail, detail_font = _fit_text(
        draw,
        detail,
        inner_right - inner_left,
        20,
        14,
    )
    _draw_text(draw, (inner_left, top + 108), detail, detail_font, fill=MUTED)

    draw.line(
        (inner_left, top + 143, inner_right, top + 143),
        fill=(63, 132, 170, 170),
        width=2,
    )
    _draw_stat_triplet(
        draw,
        player_panel,
        (
            player.get("attack", 0),
            player.get("defense", 0),
            player.get("hp", 0),
        ),
        label_y=top + 166,
        value_y=top + 202,
    )

    pet = player.get("pet")
    pet_left, pet_top, pet_right, pet_bottom = pet_panel
    pet_inner_left = pet_left + 17
    pet_inner_right = pet_right - 17
    if not pet:
        _draw_text(
            draw,
            ((pet_left + pet_right) // 2, (pet_top + pet_bottom) // 2),
            "NO PET EQUIPPED",
            _font(17, display=True),
            fill=MUTED,
            anchor="mm",
        )
        return

    pet_name = f"PET  |  {pet.get('name') or 'Unknown'}"
    pet_name, pet_name_font = _fit_text(
        draw,
        pet_name,
        pet_inner_right - pet_inner_left - 100,
        18,
        12,
        display=True,
    )
    _draw_text(draw, (pet_inner_left, pet_top + 14), pet_name, pet_name_font, fill=ICE)
    _draw_text(
        draw,
        (pet_inner_right, pet_top + 14),
        f"LV. {int(pet.get('level', 1))}",
        _font(14, display=True),
        fill=MUTED,
        anchor="ra",
    )

    pet_stats = (
        f"ATK {_format_stat(pet.get('attack', 0))}   "
        f"DEF {_format_stat(pet.get('defense', 0))}   "
        f"HP {_format_stat(pet.get('hp', 0))}"
    )
    pet_stats, stats_font = _fit_text(
        draw,
        pet_stats,
        pet_inner_right - pet_inner_left,
        16,
        11,
    )
    _draw_text(
        draw,
        ((pet_left + pet_right) // 2, pet_bottom - 19),
        pet_stats,
        stats_font,
        anchor="mm",
    )


def render_dragon_party_card(dragon, party_members):
    if not TEMPLATE_PATH.exists():
        raise FileNotFoundError(f"Missing Ice Dragon template: {TEMPLATE_PATH}")

    with Image.open(TEMPLATE_PATH) as template:
        image = template.convert("RGBA")

    draw = ImageDraw.Draw(image, "RGBA")
    _draw_boss_panel(draw, dragon)
    _draw_hunters_header(draw, len(party_members))

    for index, (player_panel, pet_panel) in enumerate(
        zip(PLAYER_PANELS, PET_PANELS),
        start=1,
    ):
        if index <= len(party_members):
            _draw_player(
                draw,
                player_panel,
                pet_panel,
                party_members[index - 1],
                index,
            )
        else:
            _draw_open_slot(draw, player_panel, pet_panel, index)

    output = BytesIO()
    image.convert("RGB").save(output, format="PNG", optimize=True)
    output.seek(0)
    return output

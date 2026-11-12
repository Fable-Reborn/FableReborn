"""Pixel-art loop of Garron Thorne hammering at Thorne's Anvil."""
from __future__ import annotations

import io
from functools import lru_cache

from PIL import Image, ImageDraw

W, H, SCALE = 128, 72, 4

STONE = (44, 40, 46)
STONE_HI = (58, 53, 60)
MORTAR = (30, 27, 32)
FLOOR = (36, 30, 28)
FLOOR_HI = (50, 42, 38)
FORGE = (70, 52, 44)
FORGE_DARK = (40, 30, 26)
EMBER = (255, 132, 40)
EMBER_HI = (255, 214, 102)
IRON = (74, 78, 88)
IRON_HI = (122, 128, 140)
IRON_DARK = (40, 42, 50)
SKIN = (176, 116, 76)
SKIN_SHADE = (132, 82, 54)
SOOT = (92, 62, 46)
HAIR = (150, 154, 160)
BEARD = (196, 196, 198)
BEARD_SHADE = (40, 40, 44)
EYE = (92, 168, 232)
BRACER = (150, 156, 168)
BRACER_HI = (214, 196, 128)
OBSIDIAN = (24, 20, 30)
OBSIDIAN_HI = (70, 62, 84)
CREST = (124, 116, 104)
RUNE = (150, 74, 36)
APRON = (98, 64, 40)
APRON_SHADE = (72, 46, 28)
SHIRT = (64, 84, 104)
BOOT = (34, 26, 22)
HAMMER_HEAD = (96, 100, 110)
HANDLE = (110, 74, 42)
BLADE_HOT = (255, 170, 70)
BLADE_GLOW = (255, 236, 160)
SIGN = (92, 60, 34)
SIGN_INK = (232, 200, 120)


def backdrop(draw, glow):
    draw.rectangle((0, 0, W, H), fill=STONE)
    for row, y in enumerate(range(0, 52, 6)):
        draw.line((0, y, W, y), fill=MORTAR)
        offset = 0 if row % 2 else 8
        for x in range(offset, W, 16):
            draw.line((x, y, x, y + 5), fill=MORTAR)
            draw.point((x + 2, y + 2), fill=STONE_HI)
    draw.rectangle((0, 52, W, H), fill=FLOOR)
    for x in range(0, W, 9):
        draw.line((x, 52, x + 3, 52), fill=FLOOR_HI)
    # Forge mouth on the left.
    draw.rectangle((4, 22, 34, 52), fill=FORGE)
    draw.rectangle((8, 30, 30, 48), fill=FORGE_DARK)
    coal = EMBER_HI if glow else EMBER
    for x in range(10, 29, 3):
        draw.rectangle((x, 43 - (x * 7 + glow) % 3, x + 2, 47), fill=coal if x % 2 else EMBER)
    draw.rectangle((12, 4, 26, 22), fill=FORGE)
    # Sign.
    draw.rectangle((32, 3, 90, 13), fill=SIGN)
    draw.rectangle((32, 3, 90, 3), fill=SIGN_INK)
    draw.rectangle((32, 13, 90, 13), fill=SIGN_INK)
    _text(draw, 35, 6, "THORNE'S ANVIL", SIGN_INK)
    # The broken Iron Accord plate on its hook.
    draw.line((46, 14, 46, 17), fill=IRON_DARK)
    draw.polygon([(40, 18), (52, 18), (53, 22), (51, 31), (45, 33), (41, 30), (39, 22)], fill=OBSIDIAN, outline=OBSIDIAN_HI)
    draw.line((40, 18, 52, 18), fill=OBSIDIAN_HI)
    draw.line((49, 26, 53, 30), fill=STONE)
    draw.line((50, 27, 52, 33), fill=STONE)
    draw.rectangle((44, 22, 47, 25), outline=CREST)
    draw.point((45, 23), fill=CREST)


FONT = {
    "T": ["111", "010", "010", "010", "010"],
    "H": ["101", "101", "111", "101", "101"],
    "O": ["111", "101", "101", "101", "111"],
    "R": ["110", "101", "110", "101", "101"],
    "N": ["1001", "1101", "1011", "1001", "1001"],
    "E": ["111", "100", "110", "100", "111"],
    "S": ["111", "100", "111", "001", "111"],
    "A": ["010", "101", "111", "101", "101"],
    "V": ["101", "101", "101", "101", "010"],
    "I": ["111", "010", "010", "010", "111"],
    "L": ["100", "100", "100", "100", "111"],
    "'": ["1", "1", "0", "0", "0"],
    " ": ["0", "0", "0", "0", "0"],
}


def _text(draw, x, y, text, color):
    for char in text:
        glyph = FONT[char]
        for dy, row in enumerate(glyph):
            for dx, bit in enumerate(row):
                if bit == "1":
                    draw.point((x + dx, y + dy), fill=color)
        x += len(glyph[0]) + 1


def anvil(draw, hot):
    draw.rectangle((70, 40, 96, 44), fill=IRON)
    draw.rectangle((64, 40, 70, 42), fill=IRON)
    draw.rectangle((70, 40, 96, 40), fill=IRON_HI)
    draw.rectangle((76, 45, 90, 49), fill=IRON_DARK)
    for rune_x in range(78, 90, 3):
        draw.point((rune_x, 46 + rune_x % 2), fill=RUNE)
        draw.point((rune_x, 48), fill=RUNE)
    draw.rectangle((72, 50, 94, 53), fill=IRON)
    blade = BLADE_GLOW if hot else BLADE_HOT
    draw.rectangle((74, 38, 92, 39), fill=blade)


def smith(draw, pose):
    # Body stands right of the anvil, facing left.
    x = 100
    draw.rectangle((x - 2, 46, x + 2, 53), fill=BOOT)
    draw.rectangle((x + 4, 46, x + 8, 53), fill=BOOT)
    draw.rectangle((x - 4, 26, x + 10, 46), fill=SHIRT)
    draw.rectangle((x - 3, 29, x + 9, 47), fill=APRON)
    draw.rectangle((x + 6, 29, x + 9, 47), fill=APRON_SHADE)
    # Head: cropped steel-gray hair, storm-blue eye, beard streaked black and white.
    draw.rectangle((x - 2, 15, x + 7, 24), fill=SKIN)
    draw.rectangle((x + 5, 15, x + 7, 24), fill=SKIN_SHADE)
    draw.rectangle((x - 2, 13, x + 7, 15), fill=HAIR)
    draw.point((x + 3, 20), fill=SOOT)
    draw.point((x, 18), fill=EYE)
    draw.rectangle((x - 3, 21, x + 6, 30), fill=BEARD)
    for streak in (x - 2, x + 1, x + 4):
        draw.line((streak, 22, streak, 29), fill=BEARD_SHADE)
    draw.rectangle((x - 1, 30, x + 3, 33), fill=BEARD)
    draw.line((x + 1, 30, x + 1, 33), fill=BEARD_SHADE)
    # Hammer arm. Shoulder near (x - 2, 28).
    shoulder = (x - 2, 28)
    hands = {
        "raised": (x - 6, 12),
        "high": (x - 10, 20),
        "strike": (x - 12, 34),
        "recoil": (x - 10, 28),
    }
    hand = hands[pose]
    draw.line((shoulder, hand), fill=SKIN, width=3)
    cuff = ((shoulder[0] + hand[0] * 2) // 3, (shoulder[1] + hand[1] * 2) // 3)
    draw.rectangle((cuff[0] - 1, cuff[1] - 1, cuff[0] + 1, cuff[1] + 1), fill=BRACER)
    draw.point(cuff, fill=BRACER_HI)
    heads = {
        "raised": ((hand[0] - 2, hand[1] - 10), (hand[0] + 4, hand[1] - 6)),
        "high": ((hand[0] - 10, hand[1] - 5), (hand[0] - 5, hand[1] + 1)),
        "strike": ((hand[0] - 7, hand[1] - 1), (hand[0] - 1, hand[1] + 4)),
        "recoil": ((hand[0] - 8, hand[1] - 6), (hand[0] - 2, hand[1] - 1)),
    }
    head = heads[pose]
    center = ((head[0][0] + head[1][0]) // 2, (head[0][1] + head[1][1]) // 2)
    draw.line((hand, center), fill=HANDLE, width=2)
    draw.rectangle(head, fill=HAMMER_HEAD)
    draw.rectangle((head[0], (head[1][0], head[0][1])), fill=IRON_HI)
    # Off hand holds tongs on the blade.
    draw.line(((x - 3, 34), (90, 39)), fill=IRON_DARK, width=1)
    draw.rectangle((x - 5, 33, x - 3, 35), fill=SKIN)
    draw.rectangle((x - 3, 32, x - 1, 36), fill=BRACER)
    draw.point((x - 2, 34), fill=BRACER_HI)


def sparks(draw, burst):
    if not burst:
        return
    origin = (87, 37)
    spread = [(-9, -8), (-4, -12), (2, -10), (7, -7), (10, -3), (-12, -3), (5, -14), (-7, -15)]
    for index, (dx, dy) in enumerate(spread):
        scale = burst
        point = (origin[0] + dx * scale // 2, origin[1] + dy * scale // 2)
        color = EMBER_HI if index % 2 else EMBER
        draw.point(point, fill=color)
        if burst == 1:
            draw.point((point[0] + 1, point[1]), fill=color)


def frame(pose, burst, glow, hot):
    image = Image.new("RGB", (W, H))
    draw = ImageDraw.Draw(image)
    backdrop(draw, glow)
    anvil(draw, hot)
    smith(draw, pose)
    sparks(draw, burst)
    return image.resize((W * SCALE, H * SCALE), Image.NEAREST)


SEQUENCE = (
    ("raised", 0, 0, False, 260),
    ("high", 0, 1, False, 90),
    ("strike", 1, 1, True, 110),
    ("strike", 2, 0, True, 110),
    ("recoil", 3, 0, False, 160),
    ("raised", 0, 1, False, 220),
)


@lru_cache(maxsize=1)
def anvil_gif() -> bytes:
    """The looping forge animation as GIF bytes. Drawn once per process."""
    frames = [frame(pose, burst, glow, hot) for pose, burst, glow, hot, _ in SEQUENCE]
    buffer = io.BytesIO()
    frames[0].save(
        buffer,
        format="GIF",
        save_all=True,
        append_images=frames[1:],
        duration=[duration for *_, duration in SEQUENCE],
        loop=0,
        optimize=True,
        disposal=2,
    )
    return buffer.getvalue()

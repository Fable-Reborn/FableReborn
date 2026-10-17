"""
The IdleRPG Discord Bot
Copyright (C) 2018-2021 Diniboy and Gelbpunkt
Copyright (C) 2023-2024 Lunar (PrototypeX37)

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU Affero General Public License for more details.

You should have received a copy of the GNU Affero General Public License
along with this program.  If not, see <https://www.gnu.org/licenses/>.
"""

# In-process Pillow port of the okapi image service (the Rust build that served
# /api/gen* on :3000 and the old Node canvas build that served the second
# profile style on :3010). Layout numbers are copied from those renderers so
# the cards come out the same; only the transport changed.

from __future__ import annotations

import asyncio
import struct

from functools import lru_cache
from io import BytesIO
from pathlib import Path

import aiohttp
import numpy as np

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ASSET_ROOT = Path(__file__).resolve().parents[1] / "assets" / "okapi"

MAX_DOWNLOAD_BYTES = 3 * 1024 * 1024
MAX_SOURCE_SIDE = 2000
DOWNLOAD_TIMEOUT = aiohttp.ClientTimeout(total=10)

# Fallback chain of the Node build's CSS font stack; the Rust build used these
# merged into one 25 MB file, which shares TravMedium's metrics.
FONT_FILES = ("TravMedium.otf", "CaviarDreams.ttf", "KGothic.ttf", "OpenSansEmoji.ttf")
# TravMedium: ascent 700 of a 1000-unit em, so ab_glyph's px scale equals the em.
FONT_ASCENT = 0.7


class RenderError(Exception):
    """Mirrors okapi's JSON error body so callers can show reason and detail."""

    def __init__(self, reason: str, detail: str = ""):
        super().__init__(f"{reason}: {detail}")
        self.reason = reason
        self.detail = detail


# --------------------------------------------------------------------------
# Assets
# --------------------------------------------------------------------------

RACES = ("human", "elf", "dwarf", "orc", "jikill", "djinn", "shadeborn", "dragonkin")
CLASSES = {
    "thief": "thief",
    "Novice Planter": "novice_planter",
    "paragon": "paragon",
    "ranger": "ranger",
    "warrior": "warrior",
    "mage": "mage",
    "raider": "raider",
    "ritualist": "ritualist",
    "paladin": "paladin",
    "reaper": "reaper",
    "santashelper": "santashelper",
    "tank": "tank",
    "bard": "bard",
    "beastmaster": "beastmaster",
    "penitent": "penitent",
    "breathcaller": "breathcaller",
}
# Both profile styles use the same cast assets, including new class lines.
V2_CLASSES = frozenset(CLASSES)
GUILD_RANKS = ("leader", "officer", "member")
ITEM_TYPES = {
    "sword": "sword",
    "shield": "shield",
    "knife": "knife",
    "dagger": "dagger",
    "spear": "spear",
    "hammer": "hammer",
    "axe": "axe",
    "bow": "bow",
    "mace": "howlet",
    "scythe": "scythe",
    "wand": "wand",
}
BADGES = (
    "contributor", "designer", "developer", "gamedesigner",
    "gamemaster", "support", "tester", "veteran",
)


@lru_cache(maxsize=None)
def _asset(name: str) -> Image.Image:
    with Image.open(ASSET_ROOT / name) as image:
        return image.convert("RGBA")


def _cast(name: str) -> Image.Image:
    return _asset(f"casts/{name}.png")


# --------------------------------------------------------------------------
# Text
# --------------------------------------------------------------------------


def _sfnt_codepoints(path: Path) -> frozenset[int]:
    """Codepoints a font maps, read from its cmap (formats 4 and 12)."""
    data = path.read_bytes()
    num_tables = struct.unpack(">H", data[4:6])[0]
    cmap = None
    for i in range(num_tables):
        tag, _, offset, length = struct.unpack(">4sIII", data[12 + 16 * i : 28 + 16 * i])
        if tag == b"cmap":
            cmap = data[offset : offset + length]
    if cmap is None:
        return frozenset()

    codepoints: set[int] = set()
    for i in range(struct.unpack(">H", cmap[2:4])[0]):
        _, _, sub = struct.unpack(">HHI", cmap[4 + 8 * i : 12 + 8 * i])
        fmt = struct.unpack(">H", cmap[sub : sub + 2])[0]
        if fmt == 4:
            seg_x2 = struct.unpack(">H", cmap[sub + 6 : sub + 8])[0]
            ends = struct.unpack(f">{seg_x2 // 2}H", cmap[sub + 14 : sub + 14 + seg_x2])
            base = sub + 16 + seg_x2
            starts = struct.unpack(f">{seg_x2 // 2}H", cmap[base : base + seg_x2])
            deltas = struct.unpack(f">{seg_x2 // 2}h", cmap[base + seg_x2 : base + 2 * seg_x2])
            range_base = base + 2 * seg_x2
            range_offsets = struct.unpack(f">{seg_x2 // 2}H", cmap[range_base : range_base + seg_x2])
            for seg, (start, end) in enumerate(zip(starts, ends)):
                for cp in range(start, min(end, 0xFFFE) + 1):
                    if range_offsets[seg] == 0:
                        glyph = (cp + deltas[seg]) & 0xFFFF
                    else:
                        at = range_base + 2 * seg + range_offsets[seg] + 2 * (cp - start)
                        glyph = struct.unpack(">H", cmap[at : at + 2])[0]
                        if glyph:
                            glyph = (glyph + deltas[seg]) & 0xFFFF
                    if glyph:
                        codepoints.add(cp)
        elif fmt == 12:
            groups = struct.unpack(">I", cmap[sub + 12 : sub + 16])[0]
            for g in range(groups):
                start, end, glyph = struct.unpack(">III", cmap[sub + 16 + 12 * g : sub + 28 + 12 * g])
                codepoints.update(range(start, end + 1))
    return frozenset(codepoints)


@lru_cache(maxsize=None)
def _coverage() -> tuple[frozenset[int], ...]:
    return tuple(_sfnt_codepoints(ASSET_ROOT / "fonts" / name) for name in FONT_FILES)


@lru_cache(maxsize=128)
def _font(index: int, size: float) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(ASSET_ROOT / "fonts" / FONT_FILES[index]), size)


def _font_index(char: str) -> int:
    cp = ord(char)
    for index, codepoints in enumerate(_coverage()):
        if cp in codepoints:
            return index
    return 0


def _runs(text: str) -> list[tuple[int, str]]:
    runs: list[tuple[int, str]] = []
    for char in text:
        index = _font_index(char) if not char.isspace() else 0
        if runs and runs[-1][0] == index:
            runs[-1] = (index, runs[-1][1] + char)
        else:
            runs.append((index, char))
    return runs


def _line_width(text: str, size: float) -> float:
    return sum(_font(i, size).getlength(run) for i, run in _runs(text))


def _line_mask(text: str, size: float) -> tuple[Image.Image, int, int]:
    """Coverage mask of one line, the baseline's y and the pen's x inside it."""
    runs = _runs(text)
    ascent = max((_font(i, size).getmetrics()[0] for i, _ in runs), default=1)
    descent = max((_font(i, size).getmetrics()[1] for i, _ in runs), default=0)
    pad = int(size * 0.25) + 1  # room for glyphs that overhang their advance
    width = max(1, int(_line_width(text, size)) + 2 * pad)
    mask = Image.new("L", (width, ascent + descent + 2), 0)
    draw = ImageDraw.Draw(mask)
    x = float(pad)
    for index, run in runs:
        font = _font(index, size)
        draw.text((x, ascent), run, fill=255, font=font, anchor="ls")
        x += font.getlength(run)
    return mask, ascent, pad


def _paint(canvas: Image.Image, mask: Image.Image, x: int, y: int, color: tuple[int, int, int, int]) -> None:
    r, g, b, a = color
    layer = Image.new("RGBA", mask.size, (r, g, b, 0))
    layer.putalpha(mask if a >= 255 else mask.point(lambda v: v * a // 255))
    _overlay(canvas, layer, x, y)


def _draw_condensed(
    canvas: Image.Image,
    text: str,
    x: float,
    baseline: float,
    size: float,
    color: tuple[int, int, int, int],
    *,
    max_width: float | None,
    measured: float | None = None,
    line_height: float | None = None,
) -> None:
    """Draw text (newlines allowed), squeezing it horizontally past max_width.

    Both okapi builds handled an over-long field this way rather than
    wrapping or clipping: canvas fillText's maxWidth and the imageproc fork's
    width argument each shrink only the horizontal scale.
    """
    if not text or size <= 0:
        return
    lines = text.split("\n")
    line_height = line_height or size
    masks = [_line_mask(line, size) for line in lines]
    natural = max(_line_width(line, size) for line in lines)
    width_basis = measured if measured is not None else natural
    squeeze = max_width / width_basis if max_width and width_basis > max_width else 1.0

    for row, (mask, ascent, pad) in enumerate(masks):
        if squeeze < 1.0:
            mask = mask.resize((max(1, round(mask.width * squeeze)), mask.height), Image.LANCZOS)
        line_baseline = baseline + row * line_height
        _paint(canvas, mask, round(x - pad * squeeze), round(line_baseline) - ascent, color)


def _overlay(canvas: Image.Image, image: Image.Image, x: int, y: int) -> None:
    """Alpha-composite image at (x, y), clipping whatever falls off the canvas."""
    left, top = max(0, -x), max(0, -y)
    right = min(image.width, canvas.width - x)
    bottom = min(image.height, canvas.height - y)
    if right <= left or bottom <= top:
        return
    if image.mode != "RGBA":
        image = image.convert("RGBA")
    canvas.alpha_composite(image.crop((left, top, right, bottom)), (x + left, y + top))


def _overlay_scaled(canvas: Image.Image, icon: Image.Image, x: int, y: int, scale: float) -> None:
    if abs(scale - 1.0) >= 0.001:
        icon = icon.resize(
            (max(1, round(icon.width * scale)), max(1, round(icon.height * scale))),
            Image.LANCZOS,
        )
    _overlay(canvas, icon, x, y)


def _png(image: Image.Image) -> bytes:
    out = BytesIO()
    # okapi encoded with the fast deflate preset; these images go straight to Discord.
    image.save(out, format="PNG", compress_level=1)
    return out.getvalue()


# --------------------------------------------------------------------------
# Downloads
# --------------------------------------------------------------------------


async def fetch_bytes(session, url: str, *, limit: int = MAX_DOWNLOAD_BYTES) -> bytes:
    """Download an image the way okapi's fetcher did: https only, size capped."""
    if not isinstance(url, str) or not url.lower().startswith("https://"):
        raise RenderError("download error", "only https URLs are supported")
    try:
        async with session.get(url, timeout=DOWNLOAD_TIMEOUT) as resp:
            if resp.status != 200:
                raise RenderError("download error", f"server answered {resp.status}")
            if resp.content_length is not None and resp.content_length > limit:
                raise RenderError("payload too big", "image must be smaller than 3 MiB")
            data = bytearray()
            async for chunk in resp.content.iter_chunked(64 * 1024):
                data.extend(chunk)
                if len(data) > limit:
                    raise RenderError("payload too big", "image must be smaller than 3 MiB")
            return bytes(data)
    except RenderError:
        raise
    except Exception as e:
        raise RenderError("download error", str(e) or type(e).__name__) from e


def decode_image(data: bytes, *, max_side: int | None = MAX_SOURCE_SIDE) -> Image.Image:
    try:
        image = Image.open(BytesIO(data))
        if max_side and (image.width > max_side or image.height > max_side):
            raise RenderError(
                "invalid image data",
                f"image is {image.width}x{image.height}, the limit is {max_side}x{max_side}",
            )
        image.load()
    except RenderError:
        raise
    except Exception as e:
        raise RenderError("invalid image data", str(e) or type(e).__name__) from e
    return image


# --------------------------------------------------------------------------
# Classic profile (Rust okapi /api/genprofile)
# --------------------------------------------------------------------------

CLASSIC_W, CLASSIC_H = 800, 533
CLASSIC_POSITIONS = {
    "character_name": (12, 12),
    "level": (720, 16),
    "marriage": (180, 76),
    "race": (70, 168),
    "class1": (70, 263),
    "class2": (70, 320),
    "profession": (70, 379),
    "money": (650, 283),
    "pvp_wins": (650, 332),
    "god": (650, 381),
    "adventure_name": (345, 298),
    "adventure_time": (345, 369),
    "right_hand_item_name": (345, 135),
    "right_hand_item_stat": (720, 135),
    "left_hand_item_name": (345, 206),
    "left_hand_item_stat": (720, 206),
    "race_icon": (6, 150),
    "class_icon_1": (6, 244),
    "class_icon_2": (6, 300),
    "profession_icon": (6, 359),
    "guild_rank_icon": (610, 3),
    "right_hand_item_icon": (262, 117),
    "left_hand_item_icon": (262, 188),
    "badges": (0, 482),  # only Y is used; badge X values are fixed
}
BADGE_X_VALUES = (50, 144, 234, 327, 422, 513, 616, 712)


def _pos(positions: dict, key: str, default_key: str | None = None) -> tuple[int, int]:
    value = positions.get(key)
    try:
        return int(value[0]), int(value[1])
    except (TypeError, ValueError, IndexError):
        return CLASSIC_POSITIONS[default_key or key]


def _scale(scales: dict | None, key: str) -> float:
    try:
        value = float((scales or {}).get(key, 1.0))
    except (TypeError, ValueError):
        return 1.0
    if value != value or value in (float("inf"), float("-inf")) or value <= 0:
        return 1.0
    return min(max(value, 0.25), 4.0)


def _classic_text(canvas, text, x, y, base_px, base_w, scale, color) -> None:
    """okapi's safe_text guard plus draw_text_mut's layout."""
    if not text or x < 0 or y < 0 or x >= CLASSIC_W - 1 or y >= CLASSIC_H - 1:
        return
    s = max(scale, 0.05)
    room_y = CLASSIC_H - 1 - y
    if base_px * s > room_y:
        s = room_y / base_px
    if s <= 0.05:
        return
    width = min(max(1, round(base_w * s)), CLASSIC_W - 1 - x)
    px = base_px * s
    # The imageproc fork measured to the last glyph's origin plus one em.
    measured = _line_width(text[:-1], px) + px
    _draw_condensed(canvas, text, x, y + FONT_ASCENT * px, px, color, max_width=width, measured=measured)


def _rgba(color) -> tuple[int, int, int, int]:
    r, g, b, a = (list(color) + [1.0])[:4]
    return int(r), int(g), int(b), max(0, min(255, int(float(a) * 255)))


def _render_profile_classic(background: Image.Image, body: dict) -> bytes:
    img = background.convert("RGBA")
    positions = body.get("positions") or CLASSIC_POSITIONS
    scales = body.get("scales")

    race = str(body.get("race") or "").lower()
    if race in RACES:
        x, y = _pos(positions, "race_icon")
        _overlay_scaled(img, _cast(race), x, y, _scale(scales, "race_icon"))

    icons = list(body.get("class_icons") or []) + ["none", "none"]
    for slot, icon in enumerate(icons[:2], start=1):
        if icon in CLASSES:
            x, y = _pos(positions, f"class_icon_{slot}")
            _overlay_scaled(img, _cast(CLASSES[icon]), x, y, _scale(scales, f"class_icon_{slot}"))

    profession = body.get("profession") or "None"
    if profession != "None" and profession in CLASSES:
        x, y = _pos(positions, "profession_icon")
        _overlay_scaled(img, _cast(CLASSES[profession]), x, y, _scale(scales, "profession_icon"))

    rank = str(body.get("guild_rank") or "").lower()
    if rank in GUILD_RANKS:
        x, y = _pos(positions, "guild_rank_icon")
        _overlay_scaled(img, _cast(rank), x, y, _scale(scales, "guild_rank_icon"))

    for hand in ("right_hand_item", "left_hand_item"):
        item = body.get(hand)
        if item and str(item[0] or "").lower() in ITEM_TYPES:
            x, y = _pos(positions, f"{hand}_icon")
            icon = _cast(ITEM_TYPES[str(item[0]).lower()])
            _overlay_scaled(img, icon, x, y, _scale(scales, f"{hand}_icon"))

    badges_y = _pos(positions, "badges")[1]
    for x, badge in zip(BADGE_X_VALUES, body.get("badges") or []):
        if badge in BADGES:
            _overlay_scaled(img, _cast(badge), x, badges_y, _scale(scales, "badges"))

    color = _rgba(body.get("color") or (0, 0, 0, 1.0))

    def text(key, value, base_px, base_w, scale_key=None):
        x, y = _pos(positions, key)
        _classic_text(img, value, x, y, base_px, base_w, _scale(scales, scale_key or key), color)

    name = str(body.get("name") or "")
    if body.get("guild_name"):
        name = f"{name} of {body['guild_name']}"
    text("character_name", name, 52.0, 550)
    text("level", str(body.get("level") or ""), 52.0, 70)
    if body.get("marriage"):
        text("marriage", f"♥ {body['marriage']}", 22.0, 500)
    text("race", str(body.get("race") or ""), 34.0, 160)

    classes = list(body.get("classes") or [])
    if len(classes) > 0:
        text("class1", str(classes[0]), 34.0, 160)
    if len(classes) > 1:
        text("class2", str(classes[1]), 34.0, 160)

    if profession != "None":
        # The bot names this element "profession_text"; older payloads say "profession".
        key = "profession_text" if positions.get("profession_text") else "profession"
        x, y = _pos(positions, key, "profession")
        _classic_text(img, profession, x, y, 34.0, 160, _scale(scales, "profession_text"), color)

    text("money", str(body.get("money") or ""), 30.0, 140)
    text("pvp_wins", str(body.get("pvp_wins") or ""), 30.0, 140)
    text("god", str(body.get("god") or ""), 30.0, 140)
    text("adventure_name", body.get("adventure_name") or "No Adventure", 34.0, 210)
    if body.get("adventure_time"):
        text("adventure_time", str(body["adventure_time"]), 34.0, 190)

    for hand in ("right_hand_item", "left_hand_item"):
        item = body.get(hand)
        if item:
            text(f"{hand}_name", str(item[1] or ""), 52.0, 325)
            text(f"{hand}_stat", str(item[2] or ""), 52.0, 85)

    return _png(img)


async def render_profile_classic(session, body: dict) -> bytes:
    """Render the classic profile card. Raises RenderError for a bad background."""
    image_url = str(body.get("image") or "0")
    if image_url == "0":
        background = _asset("profile_classic.png")
    else:
        background = decode_image(await fetch_bytes(session, image_url))
        if background.width < CLASSIC_W or background.height < CLASSIC_H:
            raise RenderError(
                "background image too small",
                "background image must be at least 800x533 in size",
            )
    return await asyncio.to_thread(_render_profile_classic, background, body)


# --------------------------------------------------------------------------
# Second profile style (Node okapi /api/genprofile on :3010)
# --------------------------------------------------------------------------

V2_W, V2_H = 800, 650


def _wrap(text: str, n: int) -> str:
    """Port of the Node build's wrap(): break at the last space within n chars."""
    slices = []
    while text:
        last_space = 0
        for i in range(min(len(text), n)):
            if text[i] == " ":
                last_space = i
            if i == len(text) - 1:
                last_space = len(text)
        if last_space == 0:  # no break point; the Node loop spun forever here
            last_space = min(len(text), n)
        slices.append(text[:last_space].strip())
        text = text[last_space:]
    return "\n".join(slices)


def _v2_str(value) -> str:
    return "" if value is None else str(value)


def _render_profile_v2(background: Image.Image, body: dict) -> bytes:
    img = Image.new("RGBA", (V2_W, V2_H), (0, 0, 0, 0))
    _overlay(img, background.convert("RGBA"), 0, 0)
    color = _rgba(body.get("color") or (0, 0, 0, 1.0))

    def fill(value, x, y, max_width, size):
        _draw_condensed(img, _v2_str(value), x, y, size, color, max_width=max_width)

    fill(body.get("name"), 221, 161, 133, 26)
    fill(body.get("race"), 228, 203, 133, 26)
    fill("\n".join(_v2_str(c) for c in body.get("classes") or []), 228, 250, 133, 23)

    fill(body.get("damage"), 111, 310, 101, 22)
    fill(body.get("defense"), 111, 352, 101, 22)
    fill(body.get("level"), 284, 310, 63, 22)
    fill(body.get("BT"), 284, 352, 63, 22)

    for key, short_y, long_y in (("swordName", 526, 506), ("shieldName", 607, 589)):
        name = _v2_str(body.get(key))
        if len(name) < 18:
            fill(name, 165, short_y, 194, 45)
        else:
            fill(_wrap(name, 26), 165, long_y, 194, 19)

    for key, y in (
        ("money", 89),
        ("adventure_time", 161),
        ("god", 244),
        ("guild", 328),
        ("marriage", 414),
        ("pvpWins", 499),
    ):
        fill(body.get(key), 519, y, 252, 52)

    adventure = _v2_str(body.get("adventure"))
    if len(adventure.split("\n")) == 2:
        fill(adventure, 519, 562, 252, 34)
    else:
        fill(adventure, 519, 583, 252, 52)

    race = _v2_str(body.get("race")).lower()
    if race in RACES:
        _overlay(img, _cast(race).resize((22, 22), Image.LANCZOS), 205, 184)
    icons = body.get("icons")
    if isinstance(icons, list):
        for icon, y in zip(icons, (232, 254)):
            if icon in V2_CLASSES:
                _overlay(img, _cast(CLASSES[icon]).resize((22, 22), Image.LANCZOS), 205, y)

    return _png(img)


async def render_profile_v2(session, body: dict) -> bytes:
    """Render the second profile style. A broken background falls back to the default."""
    image_url = str(body.get("image") or "0")
    background = _asset("profile_v2.png")
    if image_url != "0":
        try:
            background = decode_image(await fetch_bytes(session, image_url))
        except RenderError:
            pass
    return await asyncio.to_thread(_render_profile_v2, background, body)


# --------------------------------------------------------------------------
# Background overlay (/api/genoverlay)
# --------------------------------------------------------------------------


def _render_overlay(source: Image.Image, style: str) -> bytes:
    img = source.convert("RGBA").resize((CLASSIC_W, CLASSIC_H), Image.LANCZOS)
    if style in ("dark", "light"):
        img.alpha_composite(_asset(f"overlay_{style}.png"))
    return _png(img)


async def render_overlay(session, url: str, style: str) -> bytes:
    source = decode_image(await fetch_bytes(session, url))
    return await asyncio.to_thread(_render_overlay, source, style)


# --------------------------------------------------------------------------
# Chess board (/api/genchess, which rasterised python-chess's SVG)
# --------------------------------------------------------------------------

# Sprites in assets/okapi/chess were rasterised from chess.svg at 4x; the
# board is composed at that size and reduced to okapi's 390px.
CHESS_SUPERSAMPLE = 4
CHESS_SIZE = 390
CHESS_SQUARE = 45
CHESS_MARGIN = 15
LASTMOVE_LIGHT = (0xCD, 0xD1, 0x6A, 255)
LASTMOVE_DARK = (0xAA, 0xA2, 0x3B, 255)


@lru_cache(maxsize=1)
def _check_gradient() -> Image.Image:
    """chess.svg's radial check_gradient, rendered at one supersampled square."""
    side = CHESS_SQUARE * CHESS_SUPERSAMPLE
    coords = (np.arange(side, dtype=np.float32) + 0.5) / side - 0.5
    t = np.hypot(coords[None, :], coords[:, None]) / 0.5
    inner = np.clip(t / 0.5, 0, 1)
    outer = np.clip((t - 0.5) / 0.5, 0, 1)
    r = np.where(t <= 0.5, 0xFF + (0xE7 - 0xFF) * inner, 0xE7 + (0x9E - 0xE7) * outer)
    a = np.where(t <= 0.5, 1.0, 1.0 - outer)
    rgba = np.zeros((side, side, 4), dtype=np.uint8)
    rgba[..., 0] = np.round(r).astype(np.uint8)
    rgba[..., 3] = np.round(a * 255).astype(np.uint8)
    return Image.fromarray(rgba, "RGBA")


def _render_chess(board) -> bytes:
    import chess

    k = CHESS_SUPERSAMPLE
    flipped = board.turn == chess.BLACK
    img = _asset(f"chess/frame_{'black' if flipped else 'white'}.png").copy()
    lastmove = board.peek() if board.move_stack else None
    check = board.king(board.turn) if board.is_check() else None

    def origin(square: int) -> tuple[int, int]:
        file, rank = chess.square_file(square), chess.square_rank(square)
        x = (7 - file if flipped else file) * CHESS_SQUARE + CHESS_MARGIN
        y = (rank if flipped else 7 - rank) * CHESS_SQUARE + CHESS_MARGIN
        return x * k, y * k

    side = CHESS_SQUARE * k
    draw = ImageDraw.Draw(img)
    if lastmove:
        for square in (lastmove.from_square, lastmove.to_square):
            x, y = origin(square)
            light = (chess.square_file(square) + chess.square_rank(square)) % 2 == 1
            draw.rectangle((x, y, x + side - 1, y + side - 1), fill=LASTMOVE_LIGHT if light else LASTMOVE_DARK)

    if check is not None:
        img.alpha_composite(_check_gradient(), origin(check))

    for square, piece in board.piece_map().items():
        name = ("w" if piece.color == chess.WHITE else "b") + piece.symbol().lower()
        img.alpha_composite(_asset(f"chess/{name}.png"), origin(square))

    return _png(img.resize((CHESS_SIZE, CHESS_SIZE), Image.LANCZOS).convert("RGB"))


async def render_chess(board) -> bytes:
    """Render a python-chess board the way ChessGame.get_board drew it via SVG."""
    return await asyncio.to_thread(_render_chess, board.copy())


# --------------------------------------------------------------------------
# Avatar effects (/api/imageops/*)
# --------------------------------------------------------------------------


def _fit_2000(image: Image.Image) -> Image.Image:
    longest = max(image.width, image.height)
    if longest <= 2000:
        return image
    scale = 2000 / longest
    return image.resize((int(image.width * scale), int(image.height * scale)), Image.BILINEAR)


def _pixelate(data: bytes) -> bytes:
    image = decode_image(data, max_side=None).convert("RGBA")
    return _png(image.resize((1024, 1024), Image.NEAREST))


def _invert(data: bytes) -> bytes:
    image = decode_image(data, max_side=None).convert("RGBA")
    r, g, b, a = image.split()
    rgb = Image.merge("RGB", (r, g, b)).point(lambda v: 255 - v)
    return _png(Image.merge("RGBA", (*rgb.split(), a)))


def _canny(gray: np.ndarray, low: float, high: float) -> np.ndarray:
    """Canny edges as imageproc computes them: blur, Sobel, thin, hysteresis."""
    blurred = np.asarray(
        Image.fromarray(gray).filter(ImageFilter.GaussianBlur(1.4)), dtype=np.float32
    )
    p = np.pad(blurred, 1, mode="edge")
    gx = (p[:-2, 2:] + 2 * p[1:-1, 2:] + p[2:, 2:]) - (p[:-2, :-2] + 2 * p[1:-1, :-2] + p[2:, :-2])
    gy = (p[2:, :-2] + 2 * p[2:, 1:-1] + p[2:, 2:]) - (p[:-2, :-2] + 2 * p[:-2, 1:-1] + p[:-2, 2:])
    mag = np.hypot(gx, gy)

    # Non-maximum suppression along the quantised gradient direction.
    angle = (np.degrees(np.arctan2(gy, gx)) + 180.0) % 180.0
    m = np.pad(mag, 1)
    h, w = mag.shape
    neighbours = {
        0: (m[1:-1, 2:], m[1:-1, :-2]),
        45: (m[2:, 2:], m[:-2, :-2]),
        90: (m[2:, 1:-1], m[:-2, 1:-1]),
        135: (m[2:, :-2], m[:-2, 2:]),
    }
    bins = np.select(
        [(angle < 22.5) | (angle >= 157.5), angle < 67.5, angle < 112.5],
        [0, 45, 90],
        default=135,
    )
    thin = np.zeros_like(mag)
    for direction, (a, b) in neighbours.items():
        keep = (bins == direction) & (mag >= a) & (mag >= b)
        thin[keep] = mag[keep]

    strong = thin >= high
    weak = thin >= low
    # Hysteresis: grow strong edges through 8-connected weak pixels until stable.
    edges = Image.fromarray(strong.astype(np.uint8) * 255)
    weak_mask = Image.fromarray(weak.astype(np.uint8) * 255)
    while True:
        grown = Image.fromarray(
            np.minimum(
                np.asarray(edges.filter(ImageFilter.MaxFilter(3))), np.asarray(weak_mask)
            )
        )
        if grown.tobytes() == edges.tobytes():
            break
        edges = grown
    return np.asarray(edges)


def _edges(data: bytes) -> bytes:
    image = _fit_2000(decode_image(data, max_side=None).convert("RGBA")).convert("L")
    edges = _canny(np.asarray(image), 25.0, 80.0)
    return _png(Image.fromarray(edges, "L"))


def _box_sum(values: np.ndarray, radius: int) -> np.ndarray:
    """Sum over a (2r+1)^2 window, treating pixels outside the image as absent."""
    h, w = values.shape
    padded = np.zeros((h + 2 * radius + 1, w + 2 * radius + 1), dtype=np.int64)
    padded[radius + 1 : radius + 1 + h, radius + 1 : radius + 1 + w] = values
    integral = padded.cumsum(0).cumsum(1)
    size = 2 * radius + 1
    return (
        integral[size:, size:]
        - integral[:-size, size:]
        - integral[size:, :-size]
        + integral[:-size, :-size]
    )


def _oil(data: bytes) -> bytes:
    image = _fit_2000(decode_image(data, max_side=None).convert("RGBA"))
    rgb = np.asarray(image, dtype=np.int64)[..., :3]
    radius, levels = 4, 55
    level = np.round(rgb.sum(axis=2) / 3.0 * levels / 255.0).astype(np.int64)

    h, w = level.shape
    best_count = np.zeros((h, w), dtype=np.int64)
    best_sum = np.zeros((h, w, 3), dtype=np.int64)
    # okapi kept the lowest intensity bucket on ties, hence the strict ">".
    for value in range(levels + 1):
        bucket = level == value
        if not bucket.any():
            continue
        count = _box_sum(bucket, radius)
        better = count > best_count
        if not better.any():
            continue
        best_count[better] = count[better]
        for channel in range(3):
            best_sum[..., channel][better] = _box_sum(rgb[..., channel] * bucket, radius)[better]

    out = np.zeros((h, w, 4), dtype=np.uint8)
    out[..., :3] = (best_sum // np.maximum(best_count, 1)[..., None]).astype(np.uint8)
    out[..., 3] = 255
    return _png(Image.fromarray(out, "RGBA"))


IMAGE_OPS = {"pixel": _pixelate, "invert": _invert, "edges": _edges, "oil": _oil}


async def image_op(session, op: str, url: str) -> bytes:
    """Apply one of the avatar effects to the image at url."""
    data = await fetch_bytes(session, url, limit=8 * 1024 * 1024)
    return await asyncio.to_thread(IMAGE_OPS[op], data)

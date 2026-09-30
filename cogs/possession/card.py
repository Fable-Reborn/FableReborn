"""Pillow renderer for the Possession turn card and the speaking portraits.

The card is built from plain data (see PossessionSession.card_data) so it can
run in a worker thread. Portraits are optional: a missing file draws a
placeholder, so the event works before any art is added.
"""

from functools import lru_cache
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ART_DIR = PROJECT_ROOT / "assets" / "possession"
CLASS_ART_DIR = PROJECT_ROOT / "assets" / "classes" / "ClassesNew"
FONT_DIR = PROJECT_ROOT / "assets" / "profile_themes" / "fonts"
CLASS_ART_NAMES = {"SantasHelper": "Santa's Helper"}
IMAGE_SUFFIXES = (".png", ".webp", ".jpg", ".jpeg")

EMOTIONS = ("sinister", "anger", "laugh")
DEFAULT_EMOTION = "sinister"

WIDTH = 1200
MARGIN = 32
TEXT = (238, 232, 222)
MUTED = (150, 146, 160)
PANEL = (22, 22, 30)
TRACK = (12, 12, 18)
EDGE = (58, 56, 72)
GOLD = (232, 186, 84)
VIOLET = (156, 96, 214)
RED = (214, 58, 66)
BLUE = (88, 134, 240)


# ---- assets ------------------------------------------------------------------
def _find(directory, stem):
    for suffix in IMAGE_SUFFIXES:
        path = directory / f"{stem}{suffix}"
        if path.exists():
            return path
    return None


def portrait_path(vessel_key, emotion=DEFAULT_EMOTION):
    """assets/possession/<vessel>/<emotion>.png, falling back to the sinister face."""
    folder = ART_DIR / vessel_key
    return _find(folder, emotion) or _find(folder, DEFAULT_EMOTION)


def underling_path(vessel_key):
    return _find(ART_DIR / vessel_key, "underling")


def class_art_path(class_line):
    if not class_line:
        return None
    return _find(CLASS_ART_DIR, CLASS_ART_NAMES.get(class_line, class_line))


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


@lru_cache(maxsize=64)
def _square(path, size):
    """A square crop of an image, cached; None if it can't be read."""
    try:
        with Image.open(path) as source:
            return ImageOps.fit(source.convert("RGBA"), (size, size), Image.LANCZOS, centering=(0.5, 0.35))
    except (OSError, ValueError):
        return None


@lru_cache(maxsize=64)
def _head(path, size):
    """A square around the head of a tall full-body portrait, like the class art."""
    try:
        with Image.open(path) as source:
            source = source.convert("RGBA")
            width, height = source.size
            side = round(width * 0.56)
            left = (width - side) // 2
            top = round(height * 0.03)
            return source.crop((left, top, left + side, top + side)).resize((size, size), Image.LANCZOS)
    except (OSError, ValueError):
        return None


@lru_cache(maxsize=16)
def portrait_png(path_text, size=256):
    """PNG bytes of a portrait for an embed thumbnail, or None if unreadable."""
    image = _square(Path(path_text), size)
    if image is None:
        return None
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


# ---- drawing helpers ---------------------------------------------------------
def _mix(colour, other, amount):
    return tuple(round(a + (b - a) * amount) for a, b in zip(colour, other))


def _fit(draw, text, font_factory, size, max_width, min_size=12):
    for candidate in range(size, min_size - 1, -1):
        font = font_factory(candidate)
        if draw.textlength(text, font=font) <= max_width:
            return text, font
    font = font_factory(min_size)
    while text and draw.textlength(text + "…", font=font) > max_width:
        text = text[:-1]
    return text + "…", font


def _bar(draw, box, ratio, colour, radius=None):
    left, top, right, bottom = box
    radius = radius if radius is not None else (bottom - top) // 2
    draw.rounded_rectangle(box, radius=radius, fill=TRACK, outline=EDGE, width=1)
    ratio = max(0.0, min(1.0, ratio))
    fill_right = left + round((right - left) * ratio)
    if fill_right - left >= radius:
        top_colour = _mix(colour, (255, 255, 255), 0.18)
        draw.rounded_rectangle((left, top, fill_right, bottom), radius=radius, fill=colour)
        draw.rounded_rectangle((left + 2, top + 2, fill_right - 2, top + (bottom - top) // 2),
                               radius=max(1, radius - 2), fill=top_colour + (40,))


def _rounded_image(image, radius):
    mask = Image.new("L", image.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, image.size[0] - 1, image.size[1] - 1), radius=radius, fill=255)
    out = image.copy()
    out.putalpha(mask)
    return out


def _circle_image(image):
    mask = Image.new("L", image.size, 0)
    ImageDraw.Draw(mask).ellipse((0, 0, image.size[0] - 1, image.size[1] - 1), fill=255)
    out = image.copy()
    out.putalpha(mask)
    return out


def _background(height, accent):
    top = _mix(accent, (10, 10, 14), 0.72)
    base = Image.new("RGB", (WIDTH, height), (10, 10, 14))
    gradient = Image.linear_gradient("L").resize((WIDTH, height))
    tint = Image.new("RGB", (WIDTH, height), top)
    base = Image.composite(base, tint, gradient)
    glow = Image.new("RGBA", (WIDTH, height), (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse((-160, -220, 620, 420), fill=accent + (90,))
    glow = glow.filter(ImageFilter.GaussianBlur(90))
    base = base.convert("RGBA")
    base.alpha_composite(glow)
    return base


# ---- the turn card -----------------------------------------------------------
def _header(canvas, draw, data, accent):
    vessel = data["vessel"]
    size = 236
    frame = (MARGIN, MARGIN, MARGIN + size, MARGIN + size)
    art = _square(str(vessel["portrait"]), size) if vessel.get("portrait") else None
    if art is not None:
        canvas.alpha_composite(_rounded_image(art, 20), (MARGIN, MARGIN))
    else:
        draw.rounded_rectangle(frame, radius=20, fill=_mix(accent, PANEL, 0.6))
        initial = vessel["name"].removeprefix("the ").removeprefix("The ")[:1] or "?"
        draw.text(((frame[0] + frame[2]) // 2, (frame[1] + frame[3]) // 2), initial,
                  font=display(120), fill=_mix(accent, TEXT, 0.55), anchor="mm")
    draw.rounded_rectangle(frame, radius=20, outline=_mix(accent, TEXT, 0.35), width=4)

    left = MARGIN + size + 32
    right = WIDTH - MARGIN
    name, font = _fit(draw, vessel["name"].upper(), display, 46, right - left)
    draw.text((left, MARGIN + 4), name, font=font, fill=TEXT)
    phase = f"   ·   PHASE {vessel['phase']}" if vessel["phase"] != "I" else ""
    draw.text((left, MARGIN + 66), f"TURN {data['turn']} / {data['max_turns']}{phase}",
              font=bold(21), fill=_mix(accent, TEXT, 0.55))

    hp_top = MARGIN + 108
    _bar(draw, (left, hp_top, right, hp_top + 46), vessel["hp"] / vessel["max_hp"], RED, radius=12)
    draw.text((left + 18, hp_top + 23), f"{vessel['hp']:,.0f} / {vessel['max_hp']:,.0f}",
              font=bold(22), fill=TEXT, anchor="lm", stroke_width=1, stroke_fill=(40, 8, 10))
    draw.text((right - 18, hp_top + 23), f"{vessel['hp'] / vessel['max_hp']:.0%}",
              font=bold(22), fill=TEXT, anchor="rm", stroke_width=1, stroke_fill=(40, 8, 10))

    stat_top = hp_top + 70
    gap = 16
    width = (right - left - 2 * gap) // 3
    stats = (
        ("SEVERANCE", f"{data['rite']} / {data['rite_goal']}", data["rite"] / max(1, data["rite_goal"]), GOLD),
        ("DREAD", f"{data['dread']} / {data['dread_max']}", data["dread"] / data["dread_max"], VIOLET),
        ("DAMAGE BONUS", f"+{data['bonus']:.0%}", None, None),
    )
    for index, (label, value, ratio, colour) in enumerate(stats):
        x = left + index * (width + gap)
        draw.rounded_rectangle((x, stat_top, x + width, stat_top + 58), radius=12, fill=PANEL + (225,),
                               outline=EDGE, width=1)
        draw.text((x + 16, stat_top + 10), label, font=bold(14), fill=MUTED)
        draw.text((x + width - 16, stat_top + 8), value, font=bold(18), fill=TEXT, anchor="ra")
        if ratio is not None:
            _bar(draw, (x + 16, stat_top + 36, x + width - 16, stat_top + 46), ratio, colour)
        else:
            draw.text((x + 16, stat_top + 32), "from the Severance and signatures", font=regular(13), fill=MUTED)
    return MARGIN + size


def _raider_card(canvas, draw, box, raider, accent):
    left, top, right, bottom = box
    alive = raider["alive"]
    draw.rounded_rectangle(box, radius=14, fill=(PANEL if alive else (16, 16, 20)) + (235,), outline=EDGE, width=1)
    avatar = 64
    ax, ay = left + 14, top + (bottom - top - avatar) // 2
    art = _head(str(raider["portrait"]), avatar) if raider.get("portrait") else None
    if art is not None:
        if not alive:
            art = ImageOps.grayscale(art.convert("RGB")).convert("RGBA")
        canvas.alpha_composite(_circle_image(art), (ax, ay))
    else:
        draw.ellipse((ax, ay, ax + avatar, ay + avatar), fill=_mix(accent, PANEL, 0.5))
        draw.text((ax + avatar // 2, ay + avatar // 2), raider["name"][:1].upper(), font=bold(28), fill=TEXT,
                  anchor="mm")
    ratio = raider["hp"] / raider["max_hp"] if raider["max_hp"] else 0
    ring = (GOLD if ratio > 0.6 else (230, 140, 60) if ratio > 0.3 else RED) if alive else (70, 70, 80)
    draw.ellipse((ax - 2, ay - 2, ax + avatar + 2, ay + avatar + 2), outline=ring, width=3)

    text_left = ax + avatar + 16
    name, font = _fit(draw, raider["name"], bold, 22, right - text_left - 150, 14)
    draw.text((text_left, top + 14), name, font=font, fill=TEXT if alive else MUTED)
    if not alive:
        draw.text((right - 14, top + 16), "FALLEN", font=bold(15), fill=RED, anchor="ra")
        draw.text((text_left, top + 46), "Fights on as a spirit", font=regular(16), fill=MUTED)
        return
    draw.text((right - 14, top + 18), f"{raider['hp']:,.0f} / {raider['max_hp']:,.0f}  ·  {ratio:.0%}",
              font=bold(15), fill=MUTED, anchor="ra")
    sig_text = f"{raider['signature']} {'ready' if raider['signature_ready'] else 'used'}"
    sig, sig_font = _fit(draw, sig_text, regular, 15, right - text_left - 14, 11)
    draw.text((text_left, top + 42), sig, font=sig_font, fill=GOLD if raider["signature_ready"] else MUTED)
    _bar(draw, (text_left, bottom - 24, right - 14, bottom - 12), ratio, BLUE)


def render_turn_card(data):
    """Render the public turn card. Returns a BytesIO holding a JPEG."""
    accent = tuple(data["accent"])
    raiders = data["raiders"]
    columns = 2 if len(raiders) <= 4 else 3
    rows = -(-len(raiders) // columns)
    card_h, gap = 96, 14
    warning_h = 58 if data.get("warning") else 0
    header_bottom = MARGIN + 236
    roster_top = header_bottom + 28 + (warning_h + 16 if warning_h else 0)
    height = roster_top + 44 + rows * (card_h + gap) + MARGIN - gap

    canvas = _background(height, accent)
    draw = ImageDraw.Draw(canvas, "RGBA")
    _header(canvas, draw, data, accent)

    if warning_h:
        top = header_bottom + 24
        draw.rounded_rectangle((MARGIN, top, WIDTH - MARGIN, top + warning_h), radius=14,
                               fill=(96, 18, 24, 235), outline=RED, width=2)
        text, font = _fit(draw, data["warning"], bold, 22, WIDTH - 2 * MARGIN - 40, 14)
        draw.text((WIDTH // 2, top + warning_h // 2), text, font=font, fill=TEXT, anchor="mm")

    living = sum(1 for r in raiders if r["alive"])
    fallen = len(raiders) - living
    draw.text((MARGIN, roster_top), "RAIDERS", font=display(26), fill=TEXT)
    summary = f"{living} standing" + (f"  ·  {fallen} fallen" if fallen else "")
    draw.text((WIDTH - MARGIN, roster_top + 6), summary, font=bold(17), fill=MUTED, anchor="ra")
    width = (WIDTH - 2 * MARGIN - (columns - 1) * gap) // columns
    for index, raider in enumerate(raiders):
        row, column = divmod(index, columns)
        x = MARGIN + column * (width + gap)
        y = roster_top + 44 + row * (card_h + gap)
        _raider_card(canvas, draw, (x, y, x + width, y + card_h), raider, accent)

    output = BytesIO()
    canvas.convert("RGB").save(output, format="JPEG", quality=90, subsampling=0)
    output.seek(0)
    return output

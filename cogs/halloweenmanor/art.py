"""Stand-in Hollow Manor paintings. Replace the PNGs in assets/halloween/manor to use finished art."""

from pathlib import Path

from PIL import Image, ImageDraw


WIDTH = 1200
HEIGHT = 675
BAR_TOP = 568

ROOT = Path(__file__).resolve().parents[2]
MANOR_DIR = ROOT / "assets" / "halloween" / "manor"
THEME_BANNER = ROOT / "assets" / "halloween" / "hollowmanor.png"

PHASES = ("gate", "hall", "cellar", "heart", "cleared")


def _gradient(size, top, bottom):
    width, height = size
    mask = Image.new("L", (1, height))
    for y in range(height):
        mask.putpixel((0, y), int(255 * y / max(height - 1, 1)))
    mask = mask.resize(size)
    return Image.composite(Image.new("RGB", size, bottom), Image.new("RGB", size, top), mask)


def _moon(draw, x, y, radius, glow):
    draw.ellipse((x - radius * 3, y - radius * 3, x + radius * 3, y + radius * 3), fill=glow)
    draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=(244, 226, 176))
    draw.ellipse((x - radius + 10, y - radius + 6, x + radius - 18, y + radius - 14), fill=(232, 208, 150))


def _window(draw, box, lit):
    draw.rectangle(box, fill=(255, 138, 42) if lit else (28, 22, 34), outline=(70, 48, 32))
    left, top, right, bottom = box
    mid_x = (left + right) // 2
    mid_y = (top + bottom) // 2
    draw.line((mid_x, top, mid_x, bottom), fill=(50, 30, 18))
    draw.line((left, mid_y, right, mid_y), fill=(50, 30, 18))


def _house(draw, origin, scale=1.0, windows=1):
    x, y = origin
    body = (x, y, x + int(220 * scale), y + int(160 * scale))
    draw.rectangle(body, fill=(22, 16, 28), outline=(48, 36, 42))
    roof = [
        (x - int(16 * scale), y + int(8 * scale)),
        (x + int(110 * scale), y - int(70 * scale)),
        (x + int(236 * scale), y + int(8 * scale)),
    ]
    draw.polygon(roof, fill=(14, 10, 18))
    draw.rectangle((x + int(92 * scale), y - int(110 * scale), x + int(116 * scale), y - int(40 * scale)), fill=(18, 14, 22))
    if windows >= 1:
        _window(draw, (x + int(150 * scale), y + int(36 * scale), x + int(188 * scale), y + int(78 * scale)), True)
    if windows >= 3:
        _window(draw, (x + int(36 * scale), y + int(36 * scale), x + int(74 * scale), y + int(78 * scale)), True)
        _window(draw, (x + int(36 * scale), y + int(96 * scale), x + int(74 * scale), y + int(138 * scale)), True)
    door = (x + int(96 * scale), y + int(90 * scale), x + int(132 * scale), y + int(160 * scale))
    draw.rectangle(door, fill=(12, 8, 14), outline=(90, 58, 36))


def _bar_gutter(draw):
    draw.rectangle((0, BAR_TOP, WIDTH, HEIGHT), fill=(16, 12, 16))
    draw.rectangle((64, BAR_TOP + 16, WIDTH - 64, HEIGHT - 18), outline=(90, 62, 40), width=3)
    draw.line((0, BAR_TOP, WIDTH, BAR_TOP), fill=(120, 72, 40), width=2)


def _finish(image, draw):
    _bar_gutter(draw)
    fog = Image.new("RGBA", image.size, (0, 0, 0, 0))
    fog_draw = ImageDraw.Draw(fog)
    for y in range(430, BAR_TOP):
        alpha = int(90 * (y - 430) / max(BAR_TOP - 430, 1))
        fog_draw.line((0, y, WIDTH, y), fill=(18, 12, 24, alpha))
    return Image.alpha_composite(image.convert("RGBA"), fog).convert("RGB")


def paint_phase(phase: str) -> Image.Image:
    if phase == "hall":
        image = _gradient((WIDTH, HEIGHT), (28, 18, 24), (10, 8, 12))
    elif phase == "cellar":
        image = _gradient((WIDTH, HEIGHT), (16, 14, 18), (6, 6, 8))
    elif phase == "heart":
        image = _gradient((WIDTH, HEIGHT), (24, 10, 16), (6, 4, 8))
    elif phase == "cleared":
        image = _gradient((WIDTH, HEIGHT), (48, 28, 24), (18, 14, 16))
    else:
        image = _gradient((WIDTH, HEIGHT), (10, 14, 28), (20, 12, 24))
    draw = ImageDraw.Draw(image)
    if phase in {"gate", "cleared"}:
        _moon(draw, 980, 120, 46, (48, 40, 64))
        draw.polygon([(0, 470), (280, 390), (520, 450), (780, 360), (1200, 470), (1200, BAR_TOP), (0, BAR_TOP)], fill=(18, 16, 22))
    if phase == "gate":
        _house(draw, (760, 300), scale=1.15, windows=1)
        draw.rectangle((180, 300, 196, 520), fill=(40, 36, 44))
        draw.rectangle((430, 300, 446, 520), fill=(40, 36, 44))
        for y in range(320, 510, 28):
            draw.line((180, y, 446, y + 8), fill=(70, 64, 78), width=4)
        draw.ellipse((300, 400, 318, 418), fill=(180, 140, 70))
    elif phase == "hall":
        draw.rectangle((160, 80, 1040, 540), fill=(32, 22, 28), outline=(70, 48, 40), width=6)
        draw.polygon([(600, 80), (1040, 300), (600, 520), (160, 300)], outline=(90, 60, 44))
        for x in (260, 860):
            draw.rectangle((x, 150, x + 90, 250), fill=(48, 28, 32), outline=(120, 80, 48))
        for x, y in ((340, 430), (600, 400), (860, 430)):
            draw.ellipse((x - 10, y - 28, x + 10, y), fill=(255, 170, 70))
            draw.rectangle((x - 3, y, x + 3, y + 36), fill=(70, 48, 28))
    elif phase == "cellar":
        draw.rectangle((80, 60, 1120, 540), fill=(14, 12, 16))
        for step in range(8):
            top = 120 + step * 48
            draw.polygon([(180 + step * 70, top + 40), (1120, top), (1120, top + 48), (180 + step * 70, top + 88)], fill=(28 + step, 22, 26))
        draw.ellipse((140, 360, 200, 430), fill=(255, 120, 40))
    elif phase == "heart":
        draw.ellipse((360, 80, 840, 520), fill=(12, 6, 10), outline=(90, 30, 24), width=4)
        _window(draw, (560, 220, 640, 320), True)
        draw.ellipse((588, 250, 612, 274), fill=(20, 8, 8))
    elif phase == "cleared":
        _house(draw, (490, 250), scale=1.6, windows=3)
        for x in (180, 980):
            draw.ellipse((x, 390, x + 36, 430), fill=(255, 150, 50))
    return _finish(image, ImageDraw.Draw(image))


def paint_theme_banner() -> Image.Image:
    image = _gradient((1660, 554), (12, 10, 22), (36, 16, 24))
    draw = ImageDraw.Draw(image)
    _moon(draw, 1280, 150, 70, (64, 40, 48))
    draw.polygon([(0, 430), (260, 340), (540, 410), (900, 300), (1280, 390), (1660, 300), (1660, 554), (0, 554)], fill=(16, 12, 18))
    _house(draw, (980, 230), scale=1.35, windows=1)
    for x in range(0, 1660, 90):
        draw.line((x, 470, x + 30, 500), fill=(48, 32, 28), width=2)
    draw.rectangle((0, 520, 1660, 554), fill=(18, 10, 14))
    return image


def write_assets() -> None:
    """Write stand-in paintings only where a file is missing. Finished art is left in place."""
    MANOR_DIR.mkdir(parents=True, exist_ok=True)
    THEME_BANNER.parent.mkdir(parents=True, exist_ok=True)
    for phase in PHASES:
        path = MANOR_DIR / f"{phase}.png"
        if not path.is_file():
            paint_phase(phase).save(path, format="PNG", optimize=True)
    if not THEME_BANNER.is_file():
        paint_theme_banner().save(THEME_BANNER, format="PNG", optimize=True)

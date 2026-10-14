"""Paint the Hollow Manor progress bar onto the current phase art."""

from functools import lru_cache
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .art import HEIGHT, MANOR_DIR, WIDTH, paint_phase


BAR_BOX = (88, 596, 1112, 652)
FONT_PATH = Path(__file__).resolve().parents[2] / "EightBitDragon-anqx.ttf"

PHASE_TITLES = {
    "gate": "THE GATE",
    "hall": "THE HALL",
    "cellar": "THE CELLAR",
    "heart": "THE HEART",
    "cleared": "THE WINDOW GOES DARK",
}


@lru_cache(maxsize=8)
def _font(size: int):
    candidates = (
        FONT_PATH,
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
    )
    for candidate in candidates:
        try:
            return ImageFont.truetype(str(candidate), size=size)
        except OSError:
            continue
    return ImageFont.load_default()


@lru_cache(maxsize=8)
def _base(phase: str) -> Image.Image:
    path = MANOR_DIR / f"{phase}.png"
    if path.is_file():
        with Image.open(path) as source:
            image = source.convert("RGB")
            if image.size != (WIDTH, HEIGHT):
                image = image.resize((WIDTH, HEIGHT), Image.Resampling.LANCZOS)
            return image
    return paint_phase(phase).resize((WIDTH, HEIGHT), Image.Resampling.LANCZOS)


def _ratio(current: int, goal: int) -> float:
    if goal <= 0:
        return 0.0
    return max(0.0, min(float(current) / float(goal), 1.0))


def _fill_color(ratio: float):
    if ratio < 0.35:
        return (140, 58, 28)
    if ratio < 0.70:
        return (214, 104, 36)
    return (255, 176, 74)


def render_manor_card(phase: str, current: int, goal: int) -> BytesIO:
    image = _base(phase if phase in PHASE_TITLES else "gate").copy()
    draw = ImageDraw.Draw(image)
    ratio = _ratio(current, goal)
    left, top, right, bottom = BAR_BOX
    draw.rounded_rectangle(BAR_BOX, radius=12, fill=(22, 14, 18))
    fill_right = left + int((right - left) * ratio)
    if fill_right > left + 8:
        draw.rounded_rectangle((left, top, fill_right, bottom), radius=12, fill=_fill_color(ratio))
    draw.rounded_rectangle(BAR_BOX, radius=12, outline=(214, 154, 86), width=3)
    if goal <= 0 or (current <= 0 and phase == "gate"):
        label = "The gate is open"
    elif current <= 0:
        label = "No one has crossed the threshold"
    else:
        label = f"The house is listening  ·  {ratio:.0%}"
    title = PHASE_TITLES.get(phase, "THE MANOR")
    draw.text((64, 36), title, font=_font(42), fill=(255, 236, 214), stroke_width=3, stroke_fill=(12, 8, 10))
    draw.text(
        ((left + right) // 2, (top + bottom) // 2),
        label,
        font=_font(22),
        fill=(255, 244, 230),
        anchor="mm",
        stroke_width=2,
        stroke_fill=(12, 8, 10),
    )
    output = BytesIO()
    image.save(output, format="PNG", compress_level=6)
    output.seek(0)
    return output

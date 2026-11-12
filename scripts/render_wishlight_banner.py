"""Paints the night behind the Wishlight profile card: wish lanterns rising over a mountain lake at dusk.

    python scripts/render_wishlight_banner.py

Writes assets/profile_themes/wishlight.png (2000x2000, the size of the card). The picture is drawn
by this script, so it can be repainted or tuned at any time; to use a hand-painted night instead,
save it over that file (any size; it is fitted to the card).

The card draws its own big lanterns over this (the hero's, one for each stat, four on the water),
so the lanterns painted here stay small and far away, and none drift where the name is written.
"""
import random
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from cogs.wish import card  # noqa: E402  (the lanterns are the ones on the wish card)

W, H, SS = 2000, 2000, 2
w, h = W * SS, H * SS
HORIZON = round(h * 0.595)
rng = random.Random(598004694)
noise = np.random.default_rng(598004694)


def fractal(width: int, height: int, octaves=((5, 9), (10, 22), (20, 50), (40, 110), (80, 240))) -> np.ndarray:
    """Soft cloud-like noise in 0-1, stretched wide."""
    total = np.zeros((height, width), dtype=np.float32)
    weight = 1.0
    for rows, cols in octaves:
        layer = Image.fromarray((noise.random((rows, cols)) * 255).astype(np.uint8), "L")
        total += np.asarray(layer.resize((width, height), Image.Resampling.BICUBIC), dtype=np.float32) / 255 * weight
        weight *= 0.5
    return (total - total.min()) / (total.max() - total.min())


def ridge(base: float, height: float, rough: int) -> np.ndarray:
    """A mountain skyline: the y of the ridge at every x."""
    line = np.zeros(w, dtype=np.float32)
    weight = 1.0
    for points in (rough, rough * 2, rough * 4, rough * 9, rough * 20):
        knots = noise.random(points + 2)
        line += np.interp(np.linspace(0, points + 1, w), np.arange(points + 2), knots) * weight
        weight *= 0.5
    line = (line - line.min()) / (line.max() - line.min())
    return base - line * height


def sky() -> Image.Image:
    ys = np.linspace(0, 1, HORIZON, dtype=np.float32)
    at = [0.0, 0.42, 0.78, 0.94, 1.0]
    stops = np.array([[8, 8, 30], [34, 18, 80], [112, 54, 110], [214, 122, 110], [246, 176, 120]], dtype=np.float32)
    column = np.stack([np.interp(ys, at, stops[:, c]) for c in range(3)], axis=1)
    image = np.repeat(column[:, None, :], w, axis=1)
    # the last light sits behind the mountains, right of centre
    xs = np.linspace(0, 1, w, dtype=np.float32)[None, :]
    afterglow = np.clip(1 - ((xs - 0.5) / 0.6) ** 2 - ((ys[:, None] - 1.0) / 0.5) ** 2, 0, 1) ** 1.5
    image += afterglow[..., None] * np.array([70, 34, 10], dtype=np.float32)
    clouds = np.clip((fractal(w, HORIZON) - 0.52) * 3.2, 0, 1) * np.clip(1.25 - np.abs(ys[:, None] - 0.62) * 2.6, 0, 1)
    lit = np.array([196, 110, 132], dtype=np.float32)
    image = image * (1 - clouds[..., None] * 0.5) + lit * clouds[..., None] * 0.5
    image += noise.uniform(-1.2, 1.2, image.shape)
    return Image.fromarray(np.clip(image, 0, 255).astype(np.uint8), "RGB")


def stars(image: Image.Image) -> None:
    draw = ImageDraw.Draw(image, "RGBA")
    for _ in range(2600):
        y = int(HORIZON * 0.8 * rng.random() ** 1.8)
        x = rng.randrange(w)
        r = rng.choice((1, 1, 1, 2, 2, 3))
        tint = rng.choice(((255, 255, 255), (255, 236, 200), (214, 208, 255)))
        draw.ellipse((x - r, y - r, x + r, y + r), fill=(*tint, rng.randint(60, 220)))
    for _ in range(60):
        y = int(HORIZON * 0.7 * rng.random() ** 1.5)
        card._sparkle(draw, rng.randrange(w), y, rng.randint(8, 20), (255, 242, 214, rng.randint(120, 220)))


def moon(image: Image.Image) -> None:
    cx, cy, r = round(w * 0.735), round(h * 0.105), round(h * 0.031)
    halo = Image.new("RGB", (r * 12, r * 12), (0, 0, 0))
    hd = ImageDraw.Draw(halo)
    hd.ellipse((r * 2, r * 2, r * 10, r * 10), fill=(52, 40, 74))
    hd.ellipse((r * 4, r * 4, r * 8, r * 8), fill=(120, 100, 128))
    halo = halo.filter(ImageFilter.GaussianBlur(r * 1.1))
    box = (cx - r * 6, cy - r * 6, cx + r * 6, cy + r * 6)
    image.paste(ImageChops.screen(image.crop(box), halo), box)
    disc = np.full((r * 2, r * 2, 3), (255, 246, 226), dtype=np.float32)
    seas = fractal(r * 2, r * 2, octaves=((3, 3), (6, 6), (12, 12), (24, 24)))[..., None]
    disc *= 1 - np.clip(seas - 0.45, 0, 1) * 0.34
    ys, xs = np.mgrid[0:r * 2, 0:r * 2]
    disc *= (1 - 0.16 * np.clip(((xs - r * 0.7) ** 2 + (ys - r * 0.7) ** 2) / (r * 1.6) ** 2, 0, 1))[..., None]
    mask = Image.new("L", (r * 8, r * 8), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, r * 8 - 1, r * 8 - 1), fill=255)
    image.paste(Image.fromarray(np.clip(disc, 0, 255).astype(np.uint8), "RGB"), (cx - r, cy - r),
                mask.resize((r * 2, r * 2), Image.Resampling.LANCZOS))


def mountains(image: Image.Image) -> None:
    layers = (
        (HORIZON - h * 0.012, h * 0.085, 6, (104, 60, 116), 70),
        (HORIZON - h * 0.005, h * 0.062, 9, (64, 38, 96), 55),
        (HORIZON + h * 0.002, h * 0.040, 12, (30, 19, 58), 0),
    )
    for base, height, rough, colour, mist in layers:
        line = ridge(base, height, rough)
        shape = Image.new("L", (w, HORIZON), 0)
        ImageDraw.Draw(shape).polygon([(0, HORIZON), *((x, float(line[x])) for x in range(0, w, 3)), (w, float(line[-1])), (w, HORIZON)], fill=255)
        image.paste(colour, (0, 0), shape)
        if mist:   # haze pooling at the foot of the far ranges
            band = np.clip((np.arange(HORIZON, dtype=np.float32) - (HORIZON - h * 0.045)) / (h * 0.045), 0, 1) * mist
            haze = Image.fromarray(np.repeat(band[:, None], w, axis=1).astype(np.uint8), "L")
            image.paste((226, 140, 126), (0, 0), ImageChops.multiply(haze, shape))


def water(image: Image.Image) -> None:
    depth = h - HORIZON
    mirror = image.crop((0, HORIZON - depth, w, HORIZON)).transpose(Image.Transpose.FLIP_TOP_BOTTOM)
    mirror = mirror.resize((w // 10, depth), Image.Resampling.BILINEAR).resize((w, depth), Image.Resampling.BILINEAR)
    mirror = mirror.filter(ImageFilter.GaussianBlur(5))
    pixels = np.asarray(mirror, dtype=np.float32)
    fall = np.linspace(0, 1, depth, dtype=np.float32)[:, None, None]
    pixels = pixels * (0.62 - 0.34 * fall) + np.array([12, 9, 34], dtype=np.float32) * (0.38 + 0.34 * fall)
    image.paste(Image.fromarray(np.clip(pixels, 0, 255).astype(np.uint8), "RGB"), (0, HORIZON))
    draw = ImageDraw.Draw(image, "RGBA")
    for _ in range(1500):   # ripples catching the light, longer and brighter near the shore
        t = rng.random() ** 2
        y = HORIZON + 4 + t * (depth - 8)
        x = rng.randrange(w)
        length = rng.uniform(20, 150) * (1 - t * 0.4)
        draw.line((x, y, x + length, y), fill=(255, 196, 150, int(rng.uniform(10, 46) * (1 - t * 0.6))), width=rng.choice((1, 2, 2, 3)))
    draw.line((0, HORIZON, w, HORIZON), fill=(20, 12, 40, 150), width=3)


def lanterns(image: Image.Image) -> None:
    placed: list[tuple[float, float, float]] = []
    for _ in range(420):
        depth = rng.random() ** 2.2                        # mostly far away
        size = 12 + depth * 84
        x = rng.uniform(0, w)
        y = rng.uniform(h * 0.015, HORIZON - size * 0.4)
        if 0.2 * w < x < 0.8 * w and 0.375 * h < y < 0.525 * h:   # the name is written here
            continue
        if all((x - px) ** 2 + (y - py) ** 2 > (1.5 * max(size, ps)) ** 2 for px, py, ps in placed):
            placed.append((x, y, size))
    placed.sort(key=lambda item: item[2])

    glints = Image.new("RGB", (w, h - HORIZON), (0, 0, 0))
    gd = ImageDraw.Draw(glints)
    for x, y, size in placed:   # each lantern's light, smeared down the water beneath it
        reach = (HORIZON - y) / HORIZON
        strength = max(0.0, 1 - reach * 1.15)
        if strength <= 0:
            continue
        top = reach * (h - HORIZON) * 0.75
        colour = tuple(int(c * strength * 0.62) for c in (255, 168, 96))
        gd.ellipse((x - size * 0.2, top, x + size * 0.2, top + size * 2.4), fill=colour)
    glints = glints.filter(ImageFilter.GaussianBlur(7))
    # the water breaks each reflection into bright and dark bands
    bands = noise.random(((h - HORIZON) // 3, 1)).astype(np.float32)
    bands = np.asarray(Image.fromarray((bands * 255).astype(np.uint8), "L").resize((w, h - HORIZON), Image.Resampling.BICUBIC), dtype=np.float32) / 255
    streaked = np.asarray(glints, dtype=np.float32) * (0.25 + 0.95 * bands[..., None])
    glints = Image.fromarray(np.clip(streaked, 0, 255).astype(np.uint8), "RGB")
    box = (0, HORIZON, w, h)
    image.paste(ImageChops.screen(image.crop(box), glints), box)

    for x, y, size in placed:
        depth = (size - 12) / 84
        card._float_lantern(image, x / card.S, y / card.S, size / card.S, 0.32 + 0.6 * depth, rng)


def main():
    image = sky()
    stars(image)
    moon(image)
    mountains(image)
    canvas = Image.new("RGB", (w, h), (12, 9, 34))
    canvas.paste(image, (0, 0))
    water(canvas)
    lanterns(canvas)
    out = ROOT / "assets" / "profile_themes" / "wishlight.png"
    canvas.resize((W, H), Image.Resampling.LANCZOS).save(out, optimize=True)
    print(out, f"{out.stat().st_size / 1e6:.1f} MB")


if __name__ == "__main__":
    main()

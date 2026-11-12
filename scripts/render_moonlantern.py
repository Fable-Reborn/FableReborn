"""Renders the night behind the Moonlight Lantern profile card and finishes it.

    python scripts/render_moonlantern.py [percent] [samples] [out.png] [raw.png]

Runs Blender (Cycles, on the GPU when there is one) on scripts/moonlantern_scene_blender.py, then
gives the raw render what a lens and the night air would: bloom round every light, a little mist
on the far shore, darker corners, a touch of grain. Writes assets/profile_themes/moonlantern.png.

Needs Blender 4.x. It is looked for on PATH, in BLENDER (an environment variable holding the path
to blender.exe) and in the usual Windows install folder. A full-size render takes about a minute
on a recent GPU.
"""
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

ROOT = Path(__file__).resolve().parents[1]
SCENE = ROOT / "scripts" / "moonlantern_scene_blender.py"
OUT = ROOT / "assets" / "profile_themes" / "moonlantern.png"
HORIZON = 1040   # the row of the far shore at full size, as in the scene


def find_blender() -> str:
    named = os.environ.get("BLENDER") or shutil.which("blender")
    if named:
        return named
    installs = sorted(Path(os.environ.get("ProgramFiles", r"C:\Program Files"), "Blender Foundation").glob("Blender 4.*/blender.exe"))
    if not installs:
        raise SystemExit("Blender 4.x not found. Install it, or set BLENDER to the path of blender.exe.")
    return str(installs[-1])


def blur(image: np.ndarray, radius: float) -> np.ndarray:
    picture = Image.fromarray(np.clip(image * 255, 0, 255).astype(np.uint8), "RGB").filter(ImageFilter.GaussianBlur(radius))
    return np.asarray(picture, dtype=np.float32) / 255


def finish(raw: Path, out: Path) -> None:
    with Image.open(raw) as source:
        image = np.asarray(source.convert("RGB"), dtype=np.float32) / 255
    h, w = image.shape[:2]
    scale = w / 2000

    # Bloom: whatever is bright spills light, a tight glow and a wide one.
    bright = image * np.clip((image.max(axis=2, keepdims=True) - 0.66) / 0.34, 0, 1)
    bloom = blur(bright, 5 * scale) * 0.18 + blur(bright, 18 * scale) * 0.20 + blur(bright, 60 * scale) * 0.22
    # blossom glows softly even where it is not bright: a second, gentler bloom for the pinks
    pink = image * np.clip((image[..., :1] - image[..., 1:2] - 0.08) / 0.25, 0, 1)
    bloom += blur(pink, 10 * scale) * 0.22 + blur(pink, 34 * scale) * 0.18
    image = 1 - (1 - image) * (1 - np.clip(bloom, 0, 1))

    # Mist lying on the far shore.
    rows = np.arange(h, dtype=np.float32)[:, None, None]
    mist = np.exp(-((rows - HORIZON * scale) / (30 * scale)) ** 2) * 0.05   # the render has real mist; this only softens the shoreline
    image = image * (1 - mist) + np.array([0.60, 0.72, 0.95], dtype=np.float32) * mist

    # A gentle S-curve and a little more colour, then the corners fall away.
    image = image + 0.10 * (image - 0.5) * (1 - np.abs(image - 0.5) * 2) * 2
    grey = image.mean(axis=2, keepdims=True)
    image = grey + (image - grey) * 1.16
    image *= np.array([0.93, 0.98, 1.07], dtype=np.float32)        # a night seen through blue
    ys, xs = np.mgrid[0:h, 0:w].astype(np.float32)
    corner = ((xs / w - 0.5) ** 2 + (ys / h - 0.5) ** 2) / 0.5
    image *= (1 - 0.42 * np.clip(corner, 0, 1) ** 1.5)[..., None]
    image += np.random.default_rng(7).normal(0, 0.006, image.shape)

    out.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(np.clip(image * 255, 0, 255).astype(np.uint8), "RGB").save(out, optimize=True)


def main():
    percent = sys.argv[1] if len(sys.argv) > 1 else "100"
    samples = sys.argv[2] if len(sys.argv) > 2 else "400"
    out = Path(sys.argv[3]) if len(sys.argv) > 3 else OUT
    with tempfile.TemporaryDirectory() as folder:
        raw = Path(sys.argv[4]) if len(sys.argv) > 4 else Path(folder) / "moonlantern_raw.png"   # name a path to keep the raw render
        done = subprocess.run([find_blender(), "-b", "-P", str(SCENE), "--", str(raw), percent, samples],
                              capture_output=True, text=True)
        if not raw.exists():
            raise SystemExit("Blender did not write a picture:\n" + (done.stdout + done.stderr)[-3000:])
        finish(raw, out)
    print(out, f"{out.stat().st_size / 1e6:.1f} MB")


if __name__ == "__main__":
    main()

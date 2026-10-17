"""Every playable class line and Dragonkin must draw an icon in both profiles."""

import ast
from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image, ImageChops

from classes.classes import ALL_CLASSES_TYPES
from utils import okapi


def profile_icon_mapper():
    # Exercise the cog's real mapping without loading its Discord/database tree.
    source = Path(__file__).resolve().parents[1] / "cogs/profile/__init__.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    nodes = [
        node for node in tree.body
        if (isinstance(node, ast.FunctionDef) and node.name == "okapi_class_icons")
        or (isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "OKAPI_CLASS_ICONS"
            for target in node.targets
        ))
    ]
    namespace = {"OKAPI_CLASS_ASSETS": okapi.CLASSES}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(source), "exec"), namespace)
    return namespace["okapi_class_icons"]


def test_every_evolution_keeps_its_class_line_icon():
    mapper = profile_icon_mapper()
    for name, class_type in ALL_CLASSES_TYPES.items():
        for evolution in class_type:
            assert mapper([evolution]) == [name.lower(), "none"]
    assert mapper(None) == ["none", "none"]
    assert mapper([None]) == ["none", "none"]


@pytest.mark.parametrize("name", [name.lower() for name in ALL_CLASSES_TYPES])
@pytest.mark.parametrize("style", ["classic", "v2"])
def test_every_class_draws_in_both_slots(name, style):
    background = Image.new("RGBA", (800, 650), "#20252c")
    if style == "classic":
        render = okapi._render_profile_classic
        body = {"class_icons": [name, name]}
        boxes = [(6, 244, 66, 304), (6, 300, 66, 360)]
    else:
        render = okapi._render_profile_v2
        body = {"icons": [name, name]}
        boxes = [(205, 232, 227, 254), (205, 254, 227, 276)]
    baseline = Image.open(BytesIO(render(background.copy(), {}))).convert("RGB")
    actual = Image.open(BytesIO(render(background.copy(), body))).convert("RGB")
    for box in boxes:
        assert ImageChops.difference(baseline.crop(box), actual.crop(box)).getbbox(), (name, style, box)


@pytest.mark.parametrize("style", ["classic", "v2"])
def test_dragonkin_race_draws_an_icon(style):
    background = Image.new("RGBA", (800, 650), "#20252c")
    if style == "classic":
        render, box = okapi._render_profile_classic, (6, 150, 66, 210)
    else:
        render, box = okapi._render_profile_v2, (205, 184, 227, 206)
    baseline = Image.open(BytesIO(render(background.copy(), {}))).convert("RGB")
    actual = Image.open(BytesIO(render(background.copy(), {"race": "Dragonkin"}))).convert("RGB")
    assert ImageChops.difference(baseline.crop(box), actual.crop(box)).getbbox()


@pytest.mark.parametrize("name", ["bard", "beastmaster", "penitent", "breathcaller", "dragonkin"])
def test_new_casts_have_transparent_margins_and_visible_small_silhouettes(name):
    icon = okapi._cast(name)
    assert icon.size == (60, 60)
    assert icon.mode == "RGBA"
    assert icon.getpixel((0, 0))[3] == 0
    small = icon.resize((22, 22), Image.Resampling.LANCZOS)
    assert small.getchannel("A").getbbox()
    assert small.getchannel("A").getextrema() == (0, 255)

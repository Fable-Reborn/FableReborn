"""Render the production PRPG method offline, without starting the Discord bot."""

import ast
import asyncio
import importlib.util
import math
import sys
from decimal import Decimal, ROUND_HALF_UP
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from typing import Optional
from unittest.mock import AsyncMock

import discord
from discord.ext import commands
from PIL import Image, ImageChops, ImageDraw, ImageFont, ImageOps
import pytest

ROOT = Path(__file__).resolve().parents[1]


def load_themes():
    name = "prpg_theme_test_module"
    if name not in sys.modules:
        spec = importlib.util.spec_from_file_location(name, ROOT / "cogs/profile/themes.py")
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
    return sys.modules[name]


def profile_renderer():
    """Extract unchanged production methods, replacing only remote collaborators."""
    themes = load_themes()
    source = ROOT / "cogs/profile/__init__.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    profile = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "Profile")
    names = {
        "_build_profile_rpg_card", "_safe_int", "_safe_float", "_decimal_or_zero",
        "_format_stat_value", "_effective_item_damage", "_effective_item_armor",
        "_effective_item_primary_stat", "_compact_number", "_profile_font",
        "_find_element_icon",
    }
    profile.body = [node for node in profile.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in names]
    profile.bases = []
    namespace = dict(
        math=math, Decimal=Decimal, ROUND_HALF_UP=ROUND_HALF_UP,
        BytesIO=BytesIO, Path=Path, Optional=Optional, discord=discord,
        Image=Image, ImageChops=ImageChops, ImageDraw=ImageDraw,
        ImageFont=ImageFont, ImageOps=ImageOps,
        # Deterministic level curve and badge fixture; neither is modified by themes.
        rpgtools=SimpleNamespace(xptolevel=lambda xp: max(1, int(xp // 1000)), xp_for_level=lambda level: level * 1000),
        get_ascension_mantle=lambda key: None, ADVENTURE_NAMES={1: "The Ashen Citadel"},
        **{name: getattr(themes, name) for name in ("THEMES", "resolve_theme", "theme_font", "theme_background", "add_theme_banner", "draw_ornament", "render_transcendent")},
    )
    exec(compile(ast.Module(body=[profile], type_ignores=[]), str(source), "exec"), namespace)
    instance = namespace["Profile"]()
    instance._profile_font_cache = {}
    instance._badge_from_db_value = lambda raw: SimpleNamespace(to_profile_display_items=lambda limit: ["Veteran", "Eternal Sovereign", "Dragon Slayer"])
    avatar = Image.new("RGBA", (512, 512), "#29384b")
    d = ImageDraw.Draw(avatar)
    d.polygon([(256, 60), (416, 150), (395, 345), (256, 455), (117, 345), (96, 150)], fill="#c7ab75")
    d.text((191, 161), "F", font=themes.theme_font(170, "title"), fill="#29384b")
    instance._fetch_avatar_image = AsyncMock(return_value=avatar)
    instance.bot = SimpleNamespace(get_cog=lambda name: None)
    return instance


def render(theme, *, pet=False, long_names=False):
    renderer = profile_renderer()
    name = "Aurelia Stormborn" if not long_names else "An impossibly long character name " * 8
    data = dict(
        user=SimpleNamespace(id=123456789012345678, display_name=name),
        profile={"name": name, "race": "High Elf", "class": ["Paragon", "Archmage"],
                 "xp": 92500, "money": 8732140, "luck": 1.2, "health": 18420, "pvpwins": 128,
                 "god": "Elysia", "prpg_theme": theme},
        items=[{"name": "Dawnbreaker" if not long_names else name, "type": "Sword", "hand": "right", "damage": 430, "element": "fire"},
               {"name": "Oathkeeper", "type": "Shield", "hand": "left", "armor": 390, "element": "light"}],
        rank_money=14, rank_xp=3, guild_name="The First Flame", mission=[1],
        pet_name="Nyx" if pet else "None", marriage_name="Alaric",
        raid_attack=3240, raid_defense=2780, total_health=18420,
        amulet_data={"tier": 5, "type": "balanced"},
        pet_data={"name": "Nyx", "level": 100, "growth_stage": "final", "element": "dark",
                  "happiness": 96, "hunger": 82, "trust_level": 100, "hp": 8500,
                  "attack": 1600, "defense": 1200, "IV": 98} if pet else None,
    )
    return asyncio.run(renderer._build_profile_rpg_card(**data))


@pytest.mark.parametrize("key", list(load_themes().THEMES))
def test_all_themes_render_real_card(key):
    output = render(key, pet=True, long_names=True)
    with Image.open(output) as image:
        assert image.size == load_themes().THEMES[key].card_size
        assert image.format == "PNG"
    assert output.getbuffer().nbytes < 8_000_000


def test_unknown_saved_theme_falls_back_and_input_is_strict():
    assert Image.open(render("removed_theme")).size == (1660, 940)
    themes = load_themes()
    assert themes.resolve_theme("../dragon") is None
    assert themes.resolve_theme("  PuRpLe ").key == "chaos"
    assert themes.resolve_theme("The Hollow Crown").key == "evil"
    assert themes.resolve_theme("reset").key == "classic"


def test_banner_cache_never_contains_player_pixels():
    themes = load_themes()
    original = themes._banner("dragon").copy()
    themes.add_theme_banner(Image.new("RGB", (1660, 940), "red"), themes.THEMES["dragon"])
    assert ImageChops.difference(original, themes._banner("dragon")).getbbox() is None


@pytest.mark.parametrize("key", ["chaos", "allworlds"])
def test_missing_art_keeps_card_available(monkeypatch, key):
    themes = load_themes()
    def missing(key):
        raise OSError("asset not installed")
    monkeypatch.setattr(themes, "_banner", missing)
    assert Image.open(render(key)).size == (1660, 1460)


def test_prismatic_finish_preserves_stat_panels_avatar_and_input_card():
    themes = load_themes()
    card = Image.new("RGB", (1660, 940), "#526479")
    original = card.copy()
    result = themes.add_theme_banner(card, themes.THEMES["allworlds"])
    assert ImageChops.difference(card, original).getbbox() is None
    # All live profile text, bars, pet data and avatar pixels remain untouched.
    for x1, y1, x2, y2 in ((412, 66, 1268, 884), (1286, 66, 1604, 884),
                           (56, 404, 390, 884)):
        expected = original.crop((x1, y1, x2, y2))
        actual = result.crop((x1, y1+520, x2, y2+520))
        assert ImageChops.difference(expected, actual).getbbox() is None
    # The avatar uses a circular mask; the square's corners belong to the halo.
    expected = original.crop((115, 159, 327, 371))
    actual = result.crop((115, 679, 327, 891))
    visible = Image.new("L", (212, 212))
    ImageDraw.Draw(visible).ellipse((0, 0, 211, 211), fill=255)
    difference = ImageChops.difference(expected, actual)
    assert Image.composite(difference, Image.new("RGB", difference.size), visible).getbbox() is None


@pytest.mark.parametrize("key", ["sunweaver", "nightpalace", "worldtreeheart"])
@pytest.mark.parametrize("pet", [False, True])
def test_transcendent_uses_new_data_renderer_and_preserves_values(key, pet, monkeypatch):
    themes = load_themes()
    actual_render = themes.render_transcendent
    captured = {}
    def capture(theme, data):
        captured.update(data)
        return actual_render(theme, data)
    def old_panel_path(*args):
        pytest.fail("Transcendent must not use the standard panel/banner compositor")
    monkeypatch.setattr(themes, "render_transcendent", capture)
    monkeypatch.setattr(themes, "add_theme_banner", old_panel_path)
    with Image.open(render(key, pet=pet, long_names=True)) as result:
        assert result.size == (1800, 2400)
    assert captured["health"] == 18420
    assert captured["attack"] == 3240
    assert captured["defense"] == 2780
    assert captured["power"] == 25960
    assert captured["level"] == 92
    assert captured["xp_progress"] == .5
    assert captured["equipment"][0]["name"].startswith("An impossibly long")
    assert captured["equipment"][1]["name"] == "Oathkeeper"
    assert captured["mission"] == "The Ashen Citadel"
    assert dict(captured["ledger"])["Guild"] == "The First Flame"
    if pet:
        assert captured["companion"]["hp"] == 18700
        assert captured["companion"]["attack"] == 3520
        assert captured["companion"]["defense"] == 2640
        assert captured["companion"]["trust"] == 100
    else:
        assert captured["companion"] is None


def test_transcendent_missing_art_and_cache_are_safe(monkeypatch):
    themes = load_themes()
    before = themes._poster_art("sunweaver", (1800, 900)).copy()
    render("sunweaver")
    assert ImageChops.difference(before, themes._poster_art("sunweaver", (1800, 900))).getbbox() is None
    def missing(*args):
        raise OSError("not installed")
    monkeypatch.setattr(themes, "_poster_art", missing)
    assert Image.open(render("sunweaver")).size == (1800, 2400)


@pytest.mark.parametrize("key", ["sunweaver", "nightpalace", "worldtreeheart"])
def test_transcendent_edition_cache_never_contains_player_pixels(key):
    themes = load_themes()
    before = themes._transcendent_base(key).copy()
    render(key, pet=True, long_names=True)
    assert ImageChops.difference(before, themes._transcendent_base(key)).getbbox() is None


def test_transcendent_optional_portraits_and_zero_stats(monkeypatch):
    themes = load_themes()
    actual_render = themes.render_transcendent
    def extreme(theme, data):
        data.update(level=1, xp_progress=0, health=0, attack=0, defense=0, power=1,
                    sprite=Image.new("RGBA", (132, 150), (255, 0, 0, 255)),
                    sprite_name="A long in-game character name " * 20,
                    jury_title="A long jury title " * 30, badges=["Badge " * 40]*6)
        data["companion"]["image"] = Image.new("RGBA", (320, 320), (0, 255, 0, 0))
        result = actual_render(theme, data)
        assert result.getpixel((110, 900)) == (255, 0, 0)
        # Transparent pet pixels must reveal the folio beneath, never become green.
        assert result.getpixel((1251, 1691)) != (0, 255, 0)
        return result
    monkeypatch.setattr(themes, "render_transcendent", extreme)
    assert Image.open(render("nightpalace", pet=True)).size == (1800, 2400)


def test_preview_does_not_save():
    tree = ast.parse((ROOT / "cogs/profile/__init__.py").read_text(encoding="utf-8"))
    profile = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "Profile")
    preview = next(node for node in profile.body if isinstance(node, ast.AsyncFunctionDef) and node.name == "prpg_preview")
    preview.decorator_list = []
    ns = {"resolve_theme": load_themes().resolve_theme, "THEMES": load_themes().THEMES}
    exec(compile(ast.Module(body=[preview], type_ignores=[]), "preview", "exec"), ns)
    cog = SimpleNamespace(_send_profile_rpg=AsyncMock())
    ctx = SimpleNamespace(send=AsyncMock(), clean_prefix="$")
    asyncio.run(ns["prpg_preview"](cog, ctx, name="purple"))
    cog._send_profile_rpg.assert_awaited_once_with(ctx, None, theme_key="chaos")
    cog._send_profile_rpg.reset_mock()
    asyncio.run(ns["prpg_preview"](cog, ctx, name="invalid"))
    cog._send_profile_rpg.assert_not_awaited()
    ctx.send.assert_awaited_once()


def test_real_discord_group_routes_profiles_and_subcommands():
    async def scenario():
        tree = ast.parse((ROOT / "cogs/profile/__init__.py").read_text(encoding="utf-8"))
        profile = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "Profile")
        profile.body = [node for node in profile.body if isinstance(node, ast.AsyncFunctionDef)
                        and node.name in {"profilerpg", "prpg_theme", "prpg_themes", "prpg_preview"}]
        async def has_character(ctx):
            return True
        save = AsyncMock(return_value=True)
        ns = {"commands": commands, "discord": discord, "_": lambda x: x,
              "locale_doc": lambda fn: fn,
              "checks": SimpleNamespace(has_char=lambda: commands.check(has_character)),
              "THEMES": load_themes().THEMES, "resolve_theme": load_themes().resolve_theme,
              "save_theme": save}
        exec(compile(ast.Module(body=[profile], type_ignores=[]), "profile_commands", "exec"), ns)
        async with commands.Bot(command_prefix="$", intents=discord.Intents.none()) as bot:
            bot._connection.user = SimpleNamespace(id=99, display_name="Fable")
            bot.pool = SimpleNamespace()
            cog = ns["Profile"]()
            cog.bot = bot
            cog._send_profile_rpg = AsyncMock()
            await bot.add_cog(cog)
            for content, target in (("$prpg", None), ("$prpg <@123456789012345678>", "<@123456789012345678>"),
                                    ("$rpgprofile 123456789012345678", "123456789012345678")):
                msg = SimpleNamespace(content=content, author=SimpleNamespace(id=123, bot=False),
                                      channel=SimpleNamespace(id=1), guild=None, attachments=[], _state=bot._connection)
                ctx = await bot.get_context(msg)
                ctx.send = AsyncMock()
                await ctx.command.invoke(ctx)
                cog._send_profile_rpg.assert_awaited_with(ctx, target)
            for content in ("$prpg preview chaos", "$prpg theme evil"):
                msg.content = content
                # Cooldowns read the creation timestamp from the message.
                msg.created_at = discord.utils.utcnow()
                msg.edited_at = None
                ctx = await bot.get_context(msg)
                ctx.send = AsyncMock()
                await ctx.command.invoke(ctx)
                if "preview" in content:
                    cog._send_profile_rpg.assert_awaited_with(ctx, None, theme_key="chaos")
                    save.assert_not_awaited()
                else:
                    save.assert_awaited_once_with(bot.pool, 123, load_themes().THEMES["evil"])
    asyncio.run(scenario())

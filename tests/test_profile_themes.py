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
        **{name: getattr(themes, name) for name in ("THEMES", "resolve_theme", "theme_font", "theme_background", "add_theme_banner")},
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
        user=SimpleNamespace(id=295173706496475136, display_name=name),
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
        assert image.size == ((1660, 940) if key == "classic" else (1660, 1460))
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


def test_missing_art_keeps_card_available(monkeypatch):
    themes = load_themes()
    def missing(key):
        raise OSError("asset not installed")
    monkeypatch.setattr(themes, "_banner", missing)
    assert Image.open(render("chaos")).size == (1660, 1460)


def test_theme_save_is_scoped_to_player():
    tree = ast.parse((ROOT / "cogs/profile/theme_picker.py").read_text())
    method = next(node for node in tree.body if isinstance(node, ast.AsyncFunctionDef) and node.name == "save_theme")
    ns = {}
    exec(compile(ast.Module(body=[method], type_ignores=[]), "theme_picker", "exec"), ns)
    pool = SimpleNamespace(fetchval=AsyncMock(return_value=123))
    assert asyncio.run(ns["save_theme"](pool, 123, load_themes().THEMES["evil"]))
    pool.fetchval.assert_awaited_once_with(
        'UPDATE profile SET prpg_theme = $1 WHERE "user" = $2 RETURNING "user";', "evil", 123,
    )
    pool.fetchval.return_value = None
    assert not asyncio.run(ns["save_theme"](pool, 123, load_themes().THEMES["evil"]))


def test_preview_does_not_save():
    tree = ast.parse((ROOT / "cogs/profile/__init__.py").read_text(encoding="utf-8"))
    profile = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "Profile")
    preview = next(node for node in profile.body if isinstance(node, ast.AsyncFunctionDef) and node.name == "prpg_preview")
    preview.decorator_list = []
    ns = {"resolve_theme": load_themes().resolve_theme, "THEMES": load_themes().THEMES}
    exec(compile(ast.Module(body=[preview], type_ignores=[]), "preview", "exec"), ns)
    cog = SimpleNamespace(_send_profile_rpg=AsyncMock())
    ctx = SimpleNamespace(send=AsyncMock())
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


def test_picker_rejects_other_players():
    tree = ast.parse((ROOT / "cogs/profile/theme_picker.py").read_text(encoding="utf-8"))
    tree.body = [node for node in tree.body if isinstance(node, (ast.ClassDef, ast.AsyncFunctionDef))]
    ns = {"asyncio": asyncio, "discord": discord, "THEMES": load_themes().THEMES}
    exec(compile(tree, "theme_picker", "exec"), ns)
    async def scenario():
        pool = SimpleNamespace(fetchval=AsyncMock(return_value=123))
        ctx = SimpleNamespace(author=SimpleNamespace(id=123), clean_prefix="$", bot=SimpleNamespace(pool=pool))
        picker = ns["ProfileThemePicker"](ctx, "classic")
        interaction = SimpleNamespace(user=SimpleNamespace(id=456), response=SimpleNamespace(send_message=AsyncMock()))
        assert not await picker.interaction_check(interaction)
        pool.fetchval.assert_not_awaited()
        interaction.user.id = 123
        assert await picker.interaction_check(interaction)
        interaction.response.defer = AsyncMock()
        interaction.followup = SimpleNamespace(send=AsyncMock())
        interaction.message = SimpleNamespace(
            embeds=[discord.Embed(description="Equipped: **Original Chronicle**\nPreview before equipping.")],
            edit=AsyncMock(),
        )
        picker.select._values = ["chaos"]
        await picker.choose(interaction)
        assert interaction.message.edit.call_args.kwargs["embed"].description.startswith("Equipped: **Violet Rupture**")
        assert next(option for option in picker.select.options if option.default).value == "chaos"
        picker.message = interaction.message
        await picker.on_timeout()
        assert picker.select.disabled
        picker.stop()
    asyncio.run(scenario())

import ast
import asyncio
import importlib.util
import time
import types
import unittest
from pathlib import Path

from PIL import Image, ImageChops


PROJECT_ROOT = Path(__file__).parents[1]
RENDERER_PATH = PROJECT_ROOT / "cogs" / "battles" / "dragon_battle_card.py"
DRAGON_PATH = PROJECT_ROOT / "cogs" / "battles" / "types" / "dragon.py"
SETTINGS_PATH = PROJECT_ROOT / "cogs" / "battles" / "settings.py"


def _load_renderer():
    spec = importlib.util.spec_from_file_location("dragon_battle_card", RENDERER_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_dragon_method(name, namespace):
    tree = ast.parse(DRAGON_PATH.read_text(encoding="utf-8"))
    dragon_class = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "DragonBattle"
    )
    method = next(
        node
        for node in dragon_class.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == name
    )
    method.decorator_list = []
    exec(compile(ast.Module(body=[method], type_ignores=[]), DRAGON_PATH, "exec"), namespace)
    return namespace[name]


class TestDragonBattleCard(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.renderer = _load_renderer()

    @staticmethod
    def battle_data():
        return {
            "turn": 55,
            "boss": {
                "name": "Polar Vortex",
                "level": 32,
                "hp": 18420,
                "max_hp": 43050,
                "attack": 1189,
                "defense": 902,
                "statuses": ["Armor Broken", "Poisoned"],
            },
            "log": [
                "Lunar blocks 1,205 damage.",
                "Polar Vortex casts Frozen Cataclysm.",
            ],
            "players": [
                {
                    "name": "Lunar",
                    "level": 71,
                    "class": "Tank / Mage",
                    "hp": 4627,
                    "max_hp": 6900,
                    "attack": 1589,
                    "defense": 2253,
                    "statuses": ["Shield", "Regen"],
                    "pet": {
                        "name": "Noctridium [FINAL]",
                        "level": 100,
                        "hp": 13240,
                        "max_hp": 19316,
                        "attack": 19527,
                        "defense": 14388,
                    },
                }
            ],
        }

    def test_renders_jpeg_at_template_size(self):
        rendered_buffer = self.renderer.render_dragon_battle_card(self.battle_data())
        rendered = Image.open(rendered_buffer)
        template = Image.open(self.renderer.TEMPLATE_PATH).convert("RGB")

        self.assertEqual("JPEG", rendered.format)
        self.assertEqual((1672, 941), rendered.size)
        self.assertIsNotNone(
            ImageChops.difference(template, rendered.convert("RGB")).getbbox()
        )
        self.assertLess(len(rendered_buffer.getvalue()), 1_000_000)

    def test_template_decode_is_cached(self):
        self.renderer._load_template.cache_clear()
        self.renderer.render_dragon_battle_card(self.battle_data())
        self.renderer.render_dragon_battle_card(self.battle_data())

        cache_info = self.renderer._load_template.cache_info()
        self.assertEqual(1, cache_info.misses)
        self.assertEqual(1, cache_info.hits)

    def test_image_mode_defaults_off(self):
        source = SETTINGS_PATH.read_text(encoding="utf-8")
        self.assertIn('"image_battle_card": False', source)

    def test_turn_timer_and_display_run_concurrently(self):
        real_asyncio = asyncio

        class FastAsyncio:
            create_task = staticmethod(real_asyncio.create_task)
            gather = staticmethod(real_asyncio.gather)

            @staticmethod
            async def sleep(_seconds):
                await real_asyncio.sleep(0.05)

        update_display = _load_dragon_method(
            "update_display",
            {"asyncio": FastAsyncio, "logger": None},
        )

        class FakeBattle:
            config = {"image_battle_card": False}

            async def _publish_embed_fallback(self):
                await real_asyncio.sleep(0.10)
                return object()

        battle = FakeBattle()
        battle.update_display = types.MethodType(update_display, battle)

        started = time.perf_counter()
        result = real_asyncio.run(battle.update_display(wait_for_turn_delay=True))
        elapsed = time.perf_counter() - started

        self.assertTrue(result)
        self.assertGreaterEqual(elapsed, 0.09)
        self.assertLess(elapsed, 0.14)

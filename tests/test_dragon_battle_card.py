import ast
import asyncio
import importlib.util
import time
import types
import unittest
from io import BytesIO
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

    def test_image_card_publishes_once_per_full_round_and_at_finish(self):
        should_publish = _load_dragon_method("_should_publish_battle_card", {})

        battle = types.SimpleNamespace(
            battle_message=object(),
            finished=False,
            current_turn=1,
            _last_image_card_turn=0,
        )
        self.assertFalse(should_publish(battle))

        battle.current_turn = 2
        self.assertTrue(should_publish(battle))

        battle._last_image_card_turn = 2
        self.assertFalse(should_publish(battle))

        battle.current_turn = 3
        battle.finished = True
        self.assertTrue(should_publish(battle))

    def test_mobile_summary_contains_hp_and_latest_log(self):
        summary_builder = _load_dragon_method("_battle_card_mobile_summary", {})
        summary = summary_builder(self.battle_data())

        self.assertIn("Turn 55", summary)
        self.assertIn("Dragon: **43%**", summary)
        self.assertIn("Lunar 67%", summary)
        self.assertIn("Frozen Cataclysm", summary)

    def test_new_card_is_sent_before_previous_card_is_deleted(self):
        real_asyncio = asyncio

        class OldMessage:
            def __init__(self):
                self.deleted = False

            async def delete(self):
                self.deleted = True

        class FakeFile:
            def __init__(self, fp, filename):
                self.fp = fp
                self.filename = filename

        class FakeDiscord:
            File = FakeFile

            class NotFound(Exception):
                pass

            class Forbidden(Exception):
                pass

            class HTTPException(Exception):
                pass

        async def to_thread(function, *args):
            return function(*args)

        fake_asyncio = types.SimpleNamespace(to_thread=to_thread)
        publish = _load_dragon_method(
            "_publish_battle_card",
            {
                "asyncio": fake_asyncio,
                "render_dragon_battle_card": lambda _data: BytesIO(b"jpeg"),
                "discord": FakeDiscord,
                "BytesIO": BytesIO,
                "logger": types.SimpleNamespace(exception=lambda *args, **kwargs: None),
            },
        )
        old_message = OldMessage()
        new_message = object()

        class FakeBattle:
            battle_message = old_message
            battle_id = "test-battle-id"
            current_turn = 2
            _last_image_card_turn = 0

            def _should_publish_battle_card(self):
                return True

            def _build_battle_card_data(self):
                return TestDragonBattleCard.battle_data()

            def _battle_card_mobile_summary(self, _data):
                return "mobile summary"

            async def send_with_retry(self, **kwargs):
                self.sent_kwargs = kwargs
                self.old_was_deleted_at_send = old_message.deleted
                return new_message

        battle = FakeBattle()
        result = real_asyncio.run(publish(battle))

        self.assertIs(new_message, result)
        self.assertFalse(battle.old_was_deleted_at_send)
        self.assertTrue(old_message.deleted)
        self.assertIn("mobile summary", battle.sent_kwargs["content"])
        self.assertIn("Battle ID:", battle.sent_kwargs["content"])
        self.assertNotIn("embed", battle.sent_kwargs)

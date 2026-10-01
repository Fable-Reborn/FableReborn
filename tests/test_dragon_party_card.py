import importlib.util
import unittest
from decimal import Decimal
from io import BytesIO
from pathlib import Path

from PIL import Image


PROJECT_ROOT = Path(__file__).parents[1]
MODULE_PATH = PROJECT_ROOT / "cogs" / "battles" / "dragon_party_card.py"


def _load_renderer_module():
    spec = importlib.util.spec_from_file_location("dragon_party_card", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestDragonPartyCard(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.renderer = _load_renderer_module()

    def test_renders_full_and_empty_parties(self):
        dragon = {
            "name": "Polar Vortex",
            "level": 32,
            "hp": 43050,
            "damage": 1189,
            "armor": 902,
            "element": "Water",
            "passives": ["Eternal Winter", "Death's Embrace", "Reality Bender"],
            "moves": {"Time Freeze": {"dmg": 2000}, "Apocalypse": {"dmg": 1200}},
        }
        avatar = BytesIO()
        Image.new("RGB", (64, 64), (200, 40, 40)).save(avatar, format="PNG")
        member = {
            "name": "Lunar 🌙",
            "leader": True,
            "level": 71,
            "class": "Tank / Mage",
            "attack": Decimal("1589.5"),
            "defense": 2253.25,
            "hp": 4627,
            "avatar": avatar.getvalue(),
            "pet": {
                "name": "Noctridium [FINAL]",
                "level": 100,
                "attack": 19527,
                "defense": 14388,
                "hp": 19316,
            },
        }
        party = [member, dict(member, leader=False, avatar=b"not an image", pet=None)] * 2

        for members in ([], party):
            rendered_buffer = self.renderer.render_dragon_party_card(dragon, members)
            rendered = Image.open(rendered_buffer)
            self.assertEqual("JPEG", rendered.format)
            self.assertEqual(self.renderer.OUTPUT_SIZE, rendered.size)
            self.assertLess(len(rendered_buffer.getvalue()), 1_000_000)

    def test_static_background_is_cached_between_renders(self):
        self.renderer._static_base.cache_clear()
        dragon = {
            "name": "Polar Vortex",
            "level": 32,
            "hp": 43050,
            "damage": 1189,
            "armor": 902,
        }

        self.renderer.render_dragon_party_card(dragon, [])
        self.renderer.render_dragon_party_card(dragon, [])

        cache_info = self.renderer._static_base.cache_info()
        self.assertEqual(1, cache_info.misses)
        self.assertEqual(1, cache_info.hits)

    def test_long_text_is_ellipsized_to_the_requested_width(self):
        canvas = Image.new("RGB", (400, 100))
        draw = self.renderer.ImageDraw.Draw(canvas)
        fitted, font = self.renderer._fit_text(
            draw,
            "An Extremely Long Hunter Name That Cannot Fit In The Card",
            max_width=180,
            start_size=34,
            min_size=21,
            display=True,
        )

        self.assertLessEqual(self.renderer._text_width(draw, fitted, font), 180)
        self.assertTrue(fitted.endswith("..."))

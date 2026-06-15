import importlib.util
import unittest
from pathlib import Path

from PIL import Image, ImageChops


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

    def test_renders_expected_template_size_and_dynamic_content(self):
        dragon = {
            "name": "Polar Vortex",
            "level": 32,
            "hp": 43050,
            "damage": 1189,
            "armor": 902,
        }
        party = [
            {
                "name": "Lunar",
                "leader": True,
                "level": 71,
                "class": "Tank / Mage",
                "attack": 1589,
                "defense": 2253,
                "hp": 4627,
                "pet": {
                    "name": "Noctridium [FINAL]",
                    "level": 100,
                    "attack": 19527,
                    "defense": 14388,
                    "hp": 19316,
                },
            }
        ]

        rendered_buffer = self.renderer.render_dragon_party_card(dragon, party)
        rendered = Image.open(rendered_buffer).convert("RGB")
        template = Image.open(self.renderer.TEMPLATE_PATH).convert("RGB")

        self.assertEqual((1672, 941), rendered.size)
        self.assertIsNotNone(ImageChops.difference(template, rendered).getbbox())
        self.assertGreater(len(rendered_buffer.getvalue()), 500_000)

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

        bounds = draw.textbbox((0, 0), fitted, font=font)
        self.assertLessEqual(bounds[2] - bounds[0], 180)
        self.assertTrue(fitted.endswith("..."))

"""$prpg supporter and booster pills, and telling a paid tier from a booster."""
from __future__ import annotations

import sys
import types
import unittest

try:  # Optional name generator the bot imports; not needed here.
    import fantasy_names  # noqa: F401
except ImportError:
    sys.modules["fantasy_names"] = types.ModuleType("fantasy_names")

from PIL import Image, ImageDraw, ImageFont

from cogs.profile.supporter_pills import draw_supporter_pills, layout, pills_for
from tests.test_patreon_rank_resolution import BOOSTER_ROLE_ID, SUPPORT_GUILD_ID, LookupBot

PAID_ROLE = 777  # "Legendary Hero" in the test config (tier 4 via Ko-fi names)


def canvas():
    img = Image.new("RGBA", (1300, 120), (0, 0, 0, 0))
    return img, ImageDraw.Draw(img)


class PillTests(unittest.TestCase):
    def test_nothing_for_free_players(self):
        self.assertEqual([], pills_for({"tier": 0, "booster": False}))
        self.assertEqual([], pills_for(None))
        img, draw = canvas()
        self.assertEqual(0, draw_supporter_pills(draw, [], 100, 10, 44, 1200, ImageFont.load_default()))
        self.assertIsNone(img.getbbox())

    def test_pills_by_status(self):
        self.assertEqual(["Booster"], [p["label"] for p in pills_for({"tier": 0, "booster": True})])
        self.assertEqual(["Hero"], [p["label"] for p in pills_for({"tier": 3, "booster": False})])
        self.assertEqual(
            ["Legendary Hero", "Booster"],
            [p["label"] for p in pills_for({"tier": 4, "booster": True})],
        )
        self.assertEqual(["Legendary Hero"], [p["label"] for p in pills_for({"tier": 9})])
        self.assertEqual([], pills_for({"tier": "x"}))

    def test_short_labels_when_tight_and_nothing_when_no_room(self):
        img, draw = canvas()
        font = ImageFont.load_default()
        pills = pills_for({"tier": 4, "booster": True})
        self.assertEqual("full", layout(draw, pills, 100, 1200, font)[0])
        full_width = sum(layout(draw, pills, 100, 1200, font)[1])
        mode, _ = layout(draw, pills, 100, 100 + full_width, font)
        self.assertEqual("short", mode)
        self.assertEqual("none", layout(draw, pills, 100, 120, font)[0])
        self.assertEqual(0, draw_supporter_pills(draw, pills, 100, 10, 44, 120, font))
        self.assertIsNone(img.getbbox())

    def test_pills_stay_inside_the_limit(self):
        img, draw = canvas()
        font = ImageFont.load_default()
        used = draw_supporter_pills(draw, pills_for({"tier": 2, "booster": True}), 200, 10, 44, 900, font)
        self.assertGreater(used, 0)
        left, _top, right, _bottom = img.getbbox()
        self.assertGreaterEqual(left, 200)
        self.assertLessEqual(right, 900)


class SupporterStatusTests(unittest.IsolatedAsyncioTestCase):
    def bot(self, roles, stored=0):
        from classes.bot import Bot

        class StatusBot(LookupBot):
            get_supporter_status = Bot.get_supporter_status
            _lookup_supporter_status = Bot._lookup_supporter_status
            SUPPORTER_STATUS_TTL = Bot.SUPPORTER_STATUS_TTL

        bot = StatusBot({SUPPORT_GUILD_ID: roles}, tier=stored)

        async def fetchval(sql, *args):
            return stored

        bot.pool.fetchval = fetchval
        bot._get_patreon_tier_lookup_guild_ids = lambda: [SUPPORT_GUILD_ID]
        return bot

    async def test_booster_only_even_with_saved_tier_one(self):
        for stored in (0, 1):
            status = await self.bot([BOOSTER_ROLE_ID], stored).get_supporter_status(1)
            self.assertEqual({"tier": 0, "booster": True}, status, stored)

    async def test_patron_and_booster(self):
        status = await self.bot([BOOSTER_ROLE_ID, 333], 0).get_supporter_status(1)
        self.assertTrue(status["booster"])
        self.assertEqual(4, status["tier"])

    async def test_saved_paid_tier_without_role(self):
        self.assertEqual({"tier": 3, "booster": False}, await self.bot([], 3).get_supporter_status(1))

    async def test_saved_tier_two_on_a_booster_is_still_paid(self):
        self.assertEqual({"tier": 2, "booster": True}, await self.bot([BOOSTER_ROLE_ID], 2).get_supporter_status(1))

    async def test_former_booster_with_saved_tier_one_shows_nothing(self):
        self.assertEqual({"tier": 0, "booster": False}, await self.bot([], 1).get_supporter_status(1))

    async def test_paid_role_backs_a_saved_tier_one(self):
        self.assertEqual({"tier": 4, "booster": False}, await self.bot([333], 1).get_supporter_status(1))

    async def test_status_is_cached_for_a_while(self):
        bot = self.bot([BOOSTER_ROLE_ID], 0)
        await bot.get_supporter_status(1)
        calls = len(bot.http.calls)
        await bot.get_supporter_status(1)
        self.assertEqual(calls, len(bot.http.calls))
        bot._supporter_status_cache[1] = (0, {"tier": 0, "booster": True})
        await bot.get_supporter_status(1)
        self.assertGreater(len(bot.http.calls), calls)

    async def test_neither(self):
        self.assertEqual({"tier": 0, "booster": False}, await self.bot([], 0).get_supporter_status(1))


class CardWiringTests(unittest.TestCase):
    def test_card_draws_pills_and_hides_them_for_everyone_else(self):
        from pathlib import Path

        source = Path("cogs/profile/__init__.py").read_text(encoding="utf-8")
        self.assertIn('pills_for(profile.get("supporter"))', source)
        self.assertIn("if supporter_pills:", source)
        self.assertIn('profile_data["supporter"] = await self.bot.get_supporter_status(user.id)', source)


if __name__ == "__main__":
    unittest.main()

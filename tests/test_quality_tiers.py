"""Refine cap, crafted cap, Masterwork/Flawless natural rolls, and their bot-log announcement."""
from __future__ import annotations

import random
import sys
import types
import unittest
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

try:  # Optional name generator the bot imports; not needed here.
    import fantasy_names  # noqa: F401
except ImportError:
    sys.modules["fantasy_names"] = types.ModuleType("fantasy_names")

import discord

from classes.equipment import announce, repository
from classes.equipment.definitions import (
    CRAFT_QUALITY_CAP,
    REFINE_QUALITY_CAP,
    item_tier,
    quality_band,
    quality_tier,
)
from classes.equipment.economy import refine_step
from classes.equipment.generation import describe_reward
from classes.equipment.protection import mass_salvage_skip_reason
from classes.equipment.stats import contribution


def piece(**extra):
    base = {
        "id": 5,
        "name": "Mythic Razor Cuirass",
        "rarity": "legendary",
        "archetype": "slayer",
        "slot": "chest",
        "quality": 97,
        "rolled_quality": 97,
        "fully_rolled": False,
        "refinement": 0,
        "offense_value": Decimal("0.1720"),
        "defense_value": Decimal("4.3"),
        "modifiers": [],
    }
    base.update(extra)
    return base


class TierRuleTests(unittest.TestCase):
    def test_tier_comes_from_the_natural_roll(self):
        self.assertIsNone(quality_tier(94))
        self.assertEqual("masterwork", quality_tier(95))
        self.assertEqual("masterwork", quality_tier(99))
        self.assertEqual("flawless", quality_tier(100))
        self.assertEqual("flawless", quality_tier(70, fully_rolled=True))
        self.assertIsNone(quality_tier(None))

    def test_refining_up_never_earns_a_tier(self):
        self.assertIsNone(item_tier(piece(quality=97, rolled_quality=60)))
        self.assertEqual("masterwork", item_tier(piece(quality=97, rolled_quality=97)))

    def test_tier_multiplies_the_whole_piece(self):
        plain = contribution("legendary", "slayer", 97, 3, "chest")
        master = contribution("legendary", "slayer", 97, 3, "chest", tier="masterwork")
        flawless = contribution("legendary", "slayer", 97, 3, "chest", tier="flawless")
        self.assertAlmostEqual(plain[0] * Decimal("1.10"), master[0], places=12)
        self.assertAlmostEqual(plain[1] * Decimal("1.20"), flawless[1], places=12)
        self.assertEqual(plain, contribution("legendary", "slayer", 97, 3, "chest", tier=None))

    def test_band_label_no_longer_says_masterwork(self):
        self.assertEqual("Superior", quality_band(97))
        self.assertEqual("Exceptional", quality_band(85))


class CapTests(unittest.TestCase):
    def test_refine_stops_at_85(self):
        self.assertEqual(85, REFINE_QUALITY_CAP)
        self.assertIsNotNone(refine_step("guardian", 84))
        self.assertIsNone(refine_step("guardian", 85))
        self.assertIsNone(refine_step("guardian", 92))

    def test_crafting_is_capped(self):
        self.assertEqual(85, CRAFT_QUALITY_CAP)


class CraftConn:
    from contextlib import asynccontextmanager as _acm

    @_acm
    async def transaction(self):
        yield

    async def fetchval(self, sql, *args):
        return 999  # knows every recipe and holds plenty of every material


class CraftCapTests(unittest.IsolatedAsyncioTestCase):
    async def test_a_lucky_craft_roll_lands_on_the_cap(self):
        created = {}

        async def fake_create(conn, owner_id, rolled, *, origin):
            created["quality"] = rolled.quality
            return {"id": 1, "rarity": rolled.rarity, "archetype": rolled.archetype, "slot": rolled.slot, "quality": rolled.quality}

        originals = (repository.roll_quality, repository.create_piece, repository.spend_materials, repository.log_event)
        repository.roll_quality = lambda rng, rarity: 99
        repository.create_piece = fake_create
        repository.spend_materials = AsyncMock(return_value=True)
        repository.log_event = AsyncMock()
        try:
            status, _item = await repository.craft_chest(CraftConn(), 1, "legendary", "slayer", random.Random(1), "head")
        finally:
            repository.roll_quality, repository.create_piece, repository.spend_materials, repository.log_event = originals
        self.assertEqual("crafted", status)
        self.assertEqual(CRAFT_QUALITY_CAP, created["quality"])


class SalvageAllTests(unittest.TestCase):
    def test_salvage_all_keeps_masterwork_and_flawless(self):
        self.assertEqual("masterwork", mass_salvage_skip_reason(piece(), equipped=False, listed=False))
        self.assertEqual("masterwork", mass_salvage_skip_reason(piece(rolled_quality=100), equipped=False, listed=False))
        self.assertIsNone(mass_salvage_skip_reason(piece(rolled_quality=80, quality=80), equipped=False, listed=False))


class DisplayTests(unittest.TestCase):
    def test_crate_reward_line_names_the_tier(self):
        self.assertIn("✦ Masterwork", describe_reward({"item": piece(), "materials": {}}))
        self.assertNotIn("✦", describe_reward({"item": piece(rolled_quality=60, quality=60), "materials": {}}))


class FakeConn:
    def __init__(self, rows):
        self.rows = rows
        self.updates = []

    async def fetch(self, sql, *args):
        return self.rows

    async def execute(self, sql, *args):
        self.updates.append(args)


class BackfillTests(unittest.IsolatedAsyncioTestCase):
    async def test_stored_stats_pick_up_the_bonus_once(self):
        plain = contribution("legendary", "slayer", 97, 2, "chest")
        row = piece(refinement=2, offense_value=plain[0], defense_value=plain[1])
        conn = FakeConn([row])
        self.assertEqual(1, await repository._apply_quality_tiers(conn))
        _id, offense, defense = conn.updates[0]
        self.assertAlmostEqual(plain[0] * Decimal("1.10"), offense, places=12)
        # Running again with the stored bonus changes nothing.
        row.update(offense_value=offense, defense_value=defense)
        conn.updates.clear()
        self.assertEqual(0, await repository._apply_quality_tiers(conn))


class AnnounceTests(unittest.IsolatedAsyncioTestCase):
    def test_only_masterwork_or_better_is_announced(self):
        self.assertIsNone(announce.roll_announcement_embed(1, "Pat", None, "legendary", piece(rolled_quality=94, quality=94)))
        master = announce.roll_announcement_embed(1, "Pat", None, "legendary", piece())
        self.assertIn("MASTERWORK", master.title)
        self.assertIn("natural **97**", master.description)
        flawless = announce.roll_announcement_embed(1, "Pat", None, "legendary", piece(rolled_quality=100, quality=100))
        self.assertIn("FLAWLESS", flawless.title)
        discovery = announce.roll_announcement_embed(1, "Pat", None, "legendary", piece(fully_rolled=True, rolled_quality=88, quality=88))
        self.assertIn("DISCOVERY", discovery.title)

    async def test_posts_to_bot_logs_without_pinging(self):
        sent = []

        async def send_message(channel_id, *, params):
            sent.append((channel_id, params))

        bot = SimpleNamespace(http=SimpleNamespace(send_message=send_message))
        user = SimpleNamespace(id=42, display_name="Pat", display_avatar=SimpleNamespace(url="https://a/b.png"))
        rewards = [{"item": piece()}, {"item": piece(rolled_quality=50, quality=50)}, {"item": None}]
        self.assertEqual(1, await announce.announce_top_rolls(bot, user, "legendary", rewards))
        channel_id, params = sent[0]
        self.assertEqual(1406296535443963935, channel_id)
        self.assertEqual({"parse": []}, params.payload["allowed_mentions"])
        self.assertEqual(1, len(params.payload["embeds"]))

    async def test_nothing_to_post_and_failures_never_raise(self):
        bot = SimpleNamespace(http=SimpleNamespace(send_message=AsyncMock(side_effect=discord.HTTPException(SimpleNamespace(status=403, reason="x"), "no"))))
        user = SimpleNamespace(id=42, display_name="Pat", display_avatar=None)
        self.assertEqual(0, await announce.announce_top_rolls(bot, user, "common", [{"item": piece(rolled_quality=10, quality=10)}]))
        with self.assertLogs(announce.log.name, level="WARNING"):
            self.assertEqual(0, await announce.announce_top_rolls(bot, user, "legendary", [{"item": piece()}]))


if __name__ == "__main__":
    unittest.main()

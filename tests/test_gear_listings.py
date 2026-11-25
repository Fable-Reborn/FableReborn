"""Gear shop stall size and listing length by donator tier, expiry, and seller DMs."""
from __future__ import annotations

import datetime as dt
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from tests.equipment_fakes import FakeArmoryDB, piece

from classes.equipment.economy import LISTING_RULES, listing_rules
from classes.equipment.repository import SCHEMA_STATEMENTS, buy_listing, list_piece

OWNER = 111
BUYER = 222


class ListingRuleTests(unittest.TestCase):
    def test_everyone_starts_at_a_week_and_tiers_only_go_up(self):
        self.assertEqual({"slots": 8, "days": 7}, listing_rules(0))
        previous = listing_rules(0)
        for tier in range(1, 5):
            rules = listing_rules(tier)
            self.assertGreater(rules["slots"], previous["slots"], tier)
            self.assertGreater(rules["days"], previous["days"], tier)
            previous = rules
        self.assertEqual({"slots": 20, "days": 30}, listing_rules(4))

    def test_odd_tiers_are_safe(self):
        self.assertEqual(listing_rules(0), listing_rules(None))
        self.assertEqual(listing_rules(0), listing_rules(-3))
        self.assertEqual(listing_rules(0), listing_rules("nope"))
        self.assertEqual(listing_rules(4), listing_rules(7))

    def test_schema_adds_expiry_and_gives_old_listings_a_week(self):
        joined = "\n".join(SCHEMA_STATEMENTS)
        self.assertIn("ADD COLUMN IF NOT EXISTS expires_at TIMESTAMPTZ", joined)
        self.assertIn("SET expires_at = NOW() + INTERVAL '7 days' WHERE expires_at IS NULL", joined)

    def test_rules_table_is_ordered(self):
        self.assertEqual([0, 1, 2, 3, 4], sorted(LISTING_RULES))


class StallLimitTests(unittest.IsolatedAsyncioTestCase):
    async def test_listing_uses_the_tier_length(self):
        db = FakeArmoryDB([piece(1)])
        status, item = await list_piece(db, OWNER, 1, 500, max_listings=8, duration_days=14)
        self.assertEqual("listed", status)
        self.assertEqual(14, db.listing_days[1])
        self.assertEqual((1, 8, 14), (item["used"], item["max"], item["days"]))
        self.assertFalse(item["relist"])

    async def test_full_stall_refuses_a_new_listing(self):
        db = FakeArmoryDB([piece(1), piece(2), piece(3)])
        await list_piece(db, OWNER, 1, 100, max_listings=2)
        await list_piece(db, OWNER, 2, 100, max_listings=2)
        status, info = await list_piece(db, OWNER, 3, 100, max_listings=2)
        self.assertEqual("full", status)
        self.assertEqual({"used": 2, "max": 2}, info)
        self.assertNotIn(3, db.market)

    async def test_relisting_changes_price_and_needs_no_free_slot(self):
        db = FakeArmoryDB([piece(1), piece(2)])
        await list_piece(db, OWNER, 1, 100, max_listings=2)
        await list_piece(db, OWNER, 2, 100, max_listings=2)
        status, item = await list_piece(db, OWNER, 1, 900, max_listings=2, duration_days=10)
        self.assertEqual("listed", status)
        self.assertTrue(item["relist"])
        self.assertEqual(900, db.market[1][1])
        self.assertEqual(10, db.listing_days[1])
        self.assertEqual(2, item["used"])

    async def test_other_sellers_and_expired_rows_do_not_use_your_slots(self):
        db = FakeArmoryDB(
            [piece(1), piece(9, owner=BUYER)],
            market={9: (BUYER, 50), 8: (OWNER, 50, True)},
        )
        status, item = await list_piece(db, OWNER, 1, 100, max_listings=1)
        self.assertEqual("listed", status)
        self.assertEqual(1, item["used"])

    async def test_no_limit_when_not_given(self):
        db = FakeArmoryDB([piece(i) for i in range(1, 30)])
        for i in range(1, 30):
            self.assertEqual("listed", (await list_piece(db, OWNER, i, 10))[0])

    async def test_protected_pieces_still_refused_before_slots(self):
        db = FakeArmoryDB([piece(1, locked=True)])
        self.assertEqual("locked", (await list_piece(db, OWNER, 1, 10, max_listings=0))[0])


class ExpiredPurchaseTests(unittest.IsolatedAsyncioTestCase):
    async def test_expired_listing_cannot_be_bought(self):
        db = FakeArmoryDB([piece(1)], market={1: (OWNER, 500, True)}, money={BUYER: 1000, OWNER: 0})
        status, _ = await buy_listing(db, BUYER, 1, expected_price=500)
        self.assertEqual("expired", status)
        self.assertEqual({BUYER: 1000, OWNER: 0}, db.money)
        self.assertEqual(OWNER, db.items[1]["owner_id"])
        self.assertNotIn(1, db.market)

    async def test_live_listing_still_sells(self):
        db = FakeArmoryDB([piece(1)], market={1: (OWNER, 500, False)}, money={BUYER: 1000, OWNER: 0})
        self.assertEqual("bought", (await buy_listing(db, BUYER, 1, expected_price=500))[0])


class ExpiryTextTests(unittest.TestCase):
    def test_time_left(self):
        from cogs.equipment.shop import expires_text

        now = dt.datetime(2026, 11, 25, 12, tzinfo=dt.timezone.utc)
        self.assertEqual("Expires in 2d 5h", expires_text(now + dt.timedelta(days=2, hours=5, minutes=20), now))
        self.assertEqual("Expires in 3h", expires_text(now + dt.timedelta(hours=3, minutes=5), now))
        self.assertEqual("Expires soon", expires_text(now + dt.timedelta(minutes=30), now))
        self.assertEqual("Expires soon", expires_text(now - dt.timedelta(minutes=5), now))
        self.assertEqual("No expiry", expires_text(None, now))
        naive = dt.datetime(2026, 11, 26, 12)
        self.assertEqual("Expires in 1d 0h", expires_text(naive, now))


class ExpiryDMTests(unittest.IsolatedAsyncioTestCase):
    def bot(self, *, fail=None):
        http = SimpleNamespace(
            start_private_message=AsyncMock(return_value={"id": 555}),
            send_message=AsyncMock(side_effect=fail),
        )
        return SimpleNamespace(http=http)

    async def test_seller_is_told_and_pinged(self):
        from cogs.equipment.shop import notify_listing_expired

        bot = self.bot()
        row = {"equipment_id": 42, "seller_id": OWNER, "price": 900, "name": "Razor Helm"}
        self.assertTrue(await notify_listing_expired(bot, row))
        params = bot.http.send_message.await_args.kwargs["params"]
        content = str(params.payload["content"] if params.payload else params.multipart)
        self.assertIn(f"<@{OWNER}>", content)
        self.assertIn("Razor Helm", content)
        self.assertIn("$gear sell 42 <price>", content)
        self.assertIn("still in your armory", content)

    async def test_dm_uses_the_configured_prefix(self):
        from cogs.equipment.shop import notify_listing_expired

        bot = self.bot()
        bot.config = SimpleNamespace(bot=SimpleNamespace(global_prefix="!"))
        await notify_listing_expired(bot, {"equipment_id": 7, "seller_id": OWNER, "price": 1, "name": "x"})
        params = bot.http.send_message.await_args.kwargs["params"]
        content = str(params.payload["content"] if params.payload else params.multipart)
        self.assertIn("`!gear sell 7 <price>`", content)

    async def test_closed_dms_and_bad_rows_never_raise(self):
        import discord
        from cogs.equipment.shop import notify_listing_expired

        forbidden = discord.Forbidden(SimpleNamespace(status=403, reason="no"), "closed")
        row = {"equipment_id": 1, "seller_id": OWNER, "price": 1, "name": None}
        self.assertFalse(await notify_listing_expired(self.bot(fail=forbidden), row))
        self.assertFalse(await notify_listing_expired(self.bot(), None))
        self.assertFalse(await notify_listing_expired(self.bot(), {"seller_id": None}))


class SweepWiringTests(unittest.TestCase):
    def test_cog_runs_the_sweep_and_sell_uses_tier_rules(self):
        import cogs.equipment as equipment

        self.assertTrue(hasattr(equipment.Equipment, "expire_listing_sweep"))
        self.assertEqual(600, equipment.Equipment.expire_listing_sweep.minutes * 60)
        from pathlib import Path

        source = Path("cogs/equipment/__init__.py").read_text(encoding="utf-8")
        self.assertIn("max_listings=rules[\"slots\"]", source)
        self.assertIn("duration_days=rules[\"days\"]", source)

    def test_expire_query_hands_each_row_to_one_cluster(self):
        from pathlib import Path

        source = Path("classes/equipment/repository.py").read_text(encoding="utf-8")
        self.assertIn("FOR UPDATE SKIP LOCKED", source)
        self.assertIn("DELETE FROM equipment_market", source)


if __name__ == "__main__":
    unittest.main()

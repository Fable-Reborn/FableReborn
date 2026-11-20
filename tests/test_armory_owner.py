"""Owner-only $armory / $inventory menus.

A second player must not be able to drive filters, item actions, loadouts,
or inventory consume from someone else's open menu.
"""
from __future__ import annotations

import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from classes.equipment.repository import listing_price_changed

ROOT = Path(__file__).resolve().parents[1]
PROFILE = (ROOT / "cogs" / "profile" / "__init__.py").read_text(encoding="utf-8")
_helper_src = PROFILE[PROFILE.index("ARMORY_OWNER_ONLY") : PROFILE.index("class ArmoryFilterModal")]
HELPERS: dict = {}
exec(compile("from __future__ import annotations\n" + _helper_src, "armory_helpers", "exec"), HELPERS)
ARMORY_OWNER_ONLY = HELPERS["ARMORY_OWNER_ONLY"]
_require_armory_owner = HELPERS["_require_armory_owner"]
_armory_owner_ids = HELPERS["_armory_owner_ids"]


class FakeResponse:
    def __init__(self):
        self.sent = []
        self._done = False

    def is_done(self):
        return self._done

    async def send_message(self, content, **kwargs):
        self._done = True
        self.sent.append(content)


class FakeInteraction:
    def __init__(self, user_id: int):
        self.user = SimpleNamespace(id=user_id)
        self.response = FakeResponse()


def owner_ctx(owner_id: int = 111):
    return SimpleNamespace(author=SimpleNamespace(id=owner_id), alt_invoker_id=None)


async def _run_if_owner(ctx, interaction, action):
    if not await _require_armory_owner(ctx, interaction):
        return False
    await action()
    return True


class ArmoryOwnerTests(unittest.IsolatedAsyncioTestCase):
    async def test_stranger_is_rejected_and_owner_is_allowed(self):
        ctx = owner_ctx(111)
        stranger = FakeInteraction(222)
        self.assertFalse(await _require_armory_owner(ctx, stranger))
        self.assertEqual(stranger.response.sent, [ARMORY_OWNER_ONLY])

        owner = FakeInteraction(111)
        self.assertTrue(await _require_armory_owner(ctx, owner))
        self.assertEqual(owner.response.sent, [])
        self.assertEqual(_armory_owner_ids(ctx), {111})

    async def test_stranger_cannot_submit_filter_market_or_equip(self):
        ctx = owner_ctx(111)
        invoked = MagicMock()
        equipped = MagicMock()

        async def open_filter():
            invoked("filter")

        async def list_on_market():
            invoked("market")

        async def equip():
            equipped()

        self.assertFalse(await _run_if_owner(ctx, FakeInteraction(222), open_filter))
        self.assertFalse(await _run_if_owner(ctx, FakeInteraction(222), list_on_market))
        self.assertFalse(await _run_if_owner(ctx, FakeInteraction(222), equip))
        invoked.assert_not_called()
        equipped.assert_not_called()

        owner = FakeInteraction(111)
        self.assertTrue(await _run_if_owner(ctx, owner, open_filter))
        invoked.assert_called_once_with("filter")

    async def test_stranger_cannot_open_filters_inventory_or_loadouts(self):
        ctx = owner_ctx(111)
        opened = MagicMock()

        async def open_inventory():
            opened("inventory")

        async def open_loadouts():
            opened("loadouts")

        async def open_filters():
            opened("filters")

        stranger = FakeInteraction(222)
        for action in (open_filters, open_inventory, open_loadouts):
            self.assertFalse(await _run_if_owner(ctx, stranger, action))
        opened.assert_not_called()
        self.assertEqual(stranger.response.sent, [ARMORY_OWNER_ONLY])

    async def test_stranger_cannot_drive_inventory_or_loadout_submenus(self):
        ctx = owner_ctx(111)
        consume = AsyncMock()
        selected = {"key": "home"}
        loadout = {"id": "raid"}

        async def pick_category():
            selected["key"] = "amulets"

        async def drink_potion():
            await consume()

        async def pick_loadout():
            loadout["id"] = "stolen"

        async def rename_loadout():
            loadout["id"] = "stolen"

        for action in (pick_category, drink_potion, pick_loadout, rename_loadout):
            click = FakeInteraction(222)
            self.assertFalse(await _run_if_owner(ctx, click, action))
            self.assertEqual(click.response.sent, [ARMORY_OWNER_ONLY])
        consume.assert_not_called()
        self.assertEqual(selected["key"], "home")
        self.assertEqual(loadout["id"], "raid")

    async def test_alt_invoker_can_use_the_menu(self):
        ctx = owner_ctx(111)
        ctx.alt_invoker_id = 333
        helper = FakeInteraction(333)
        self.assertTrue(await _require_armory_owner(ctx, helper))

    def test_shop_will_not_charge_the_old_price(self):
        self.assertTrue(listing_price_changed(9000, 5000))
        self.assertFalse(listing_price_changed(5000, 5000))
        self.assertFalse(listing_price_changed(5000, None))


if __name__ == "__main__":
    unittest.main()

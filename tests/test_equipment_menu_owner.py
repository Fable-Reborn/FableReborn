"""Mains may click gear menus opened via `$alt`; strangers may not.

Gold and inventory still belong to `ctx.author` (the linked alt).
"""
from __future__ import annotations

import unittest
from types import SimpleNamespace

from classes.equipment.access import (
    actor_may_use_character,
    is_menu_actor,
    menu_actor_ids,
    require_menu_actor,
)
from cogs.equipment.available import GearCraftView
from cogs.equipment.forge import BindConfirm, ForgeView
from cogs.equipment.layout import parse_layout_id
from cogs.equipment.sheet import GearSheetView
from cogs.equipment.shop import GearShopView, ShopBuyConfirm, ShopUnlistConfirm


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


def command_ctx(author_id: int, alt_invoker_id=None):
    return SimpleNamespace(author=SimpleNamespace(id=author_id), alt_invoker_id=alt_invoker_id)


class FakePool:
    def __init__(self, linked: set[tuple[int, int]]):
        self.linked = linked

    async def fetchval(self, query, main, alt):
        return 1 if (int(main), int(alt)) in self.linked else None


class GearMenuOwnerTests(unittest.IsolatedAsyncioTestCase):
    def test_plain_command_only_the_author(self):
        ctx = command_ctx(111)
        self.assertEqual(menu_actor_ids(ctx), {111})
        self.assertTrue(is_menu_actor(ctx, 111))
        self.assertFalse(is_menu_actor(ctx, 222))

    def test_alt_command_allows_main_and_character(self):
        ctx = command_ctx(111, alt_invoker_id=333)
        self.assertEqual(menu_actor_ids(ctx), {111, 333})
        self.assertTrue(is_menu_actor(ctx, 111))
        self.assertTrue(is_menu_actor(ctx, 333))
        self.assertFalse(is_menu_actor(ctx, 222))

    async def test_stranger_gets_the_refusal(self):
        ctx = command_ctx(111, alt_invoker_id=333)
        stranger = FakeInteraction(222)
        self.assertFalse(await require_menu_actor(ctx, stranger, "This stall is not yours."))
        self.assertEqual(stranger.response.sent, ["This stall is not yours."])

        main = FakeInteraction(333)
        self.assertTrue(await require_menu_actor(ctx, main, "This stall is not yours."))
        self.assertEqual(main.response.sent, [])

    async def test_linked_main_may_use_the_alts_gear_lab(self):
        conn = FakePool({(333, 111)})
        self.assertTrue(await actor_may_use_character(conn, 111, 111))
        self.assertTrue(await actor_may_use_character(conn, 333, 111))
        self.assertFalse(await actor_may_use_character(conn, 222, 111))
        self.assertFalse(await actor_may_use_character(conn, 111, 333))

    def test_gear_lab_id_keeps_the_character_owner(self):
        parsed = parse_layout_id("glb:111:focus:chest:void")
        self.assertEqual(parsed, (111, "chest", "void"))
        self.assertIsNone(parse_layout_id("glb:111:focus:chest:void", user_id=222))
        self.assertEqual(parse_layout_id("glb:111:focus:chest:void", user_id=111), (111, "chest", "void"))

    def _alt_shop(self):
        ctx = command_ctx(111, alt_invoker_id=333)
        shop = GearShopView.__new__(GearShopView)
        shop.ctx = ctx
        shop.author_id = 111
        shop.allowed_ids = menu_actor_ids(ctx)
        return shop

    async def test_forge_shop_craft_sheet_allow_main_refuse_stranger(self):
        ctx = command_ctx(111, alt_invoker_id=333)
        forge = ForgeView.__new__(ForgeView)
        forge.allowed_ids = menu_actor_ids(ctx)
        bind = BindConfirm.__new__(BindConfirm)
        bind.forge = forge
        shop = self._alt_shop()
        buy = ShopBuyConfirm.__new__(ShopBuyConfirm)
        buy.shop = shop
        unlist = ShopUnlistConfirm.__new__(ShopUnlistConfirm)
        unlist.shop = shop
        craft = GearCraftView.__new__(GearCraftView)
        craft.ctx = ctx
        sheet = GearSheetView.__new__(GearSheetView)
        sheet.ctx = ctx

        views = (forge, bind, shop, buy, unlist, craft, sheet)
        for view in views:
            stranger = FakeInteraction(222)
            self.assertFalse(await view.interaction_check(stranger), msg=type(view).__name__)
            self.assertTrue(stranger.response.sent)
            main = FakeInteraction(333)
            self.assertTrue(await view.interaction_check(main), msg=type(view).__name__)
            alt = FakeInteraction(111)
            self.assertTrue(await view.interaction_check(alt), msg=type(view).__name__)

    async def test_shop_buy_and_unlist_still_use_the_alts_character(self):
        shop = self._alt_shop()
        self.assertEqual(shop.author_id, 111)
        self.assertEqual(shop.allowed_ids, {111, 333})
        self.assertNotIn(222, shop.allowed_ids)

    async def test_unlinked_account_cannot_drive_gear_lab(self):
        conn = FakePool({(333, 111)})
        self.assertFalse(await actor_may_use_character(conn, 444, 111))

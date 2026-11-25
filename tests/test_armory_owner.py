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
armory_item_still_listed = HELPERS["armory_item_still_listed"]
resolve_armory_invoke_outcome = HELPERS["resolve_armory_invoke_outcome"]
invoke_callback_succeeded = HELPERS["invoke_callback_succeeded"]
armory_item_matches_gear_filters = HELPERS["armory_item_matches_gear_filters"]
armory_gear_filter_labels = HELPERS["armory_gear_filter_labels"]
ARMORY_GEAR_FILTER_OPTIONS = HELPERS["ARMORY_GEAR_FILTER_OPTIONS"]
armory_name_matches = HELPERS["armory_name_matches"]
armory_clean_search = HELPERS["armory_clean_search"]


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

    async def test_alt_invoker_can_use_loadout_manager_stranger_cannot(self):
        ctx = owner_ctx(111)
        ctx.alt_invoker_id = 333
        main = FakeInteraction(333)
        self.assertTrue(
            await _require_armory_owner(ctx, main, "This loadout manager is not yours.")
        )
        stranger = FakeInteraction(222)
        self.assertFalse(
            await _require_armory_owner(ctx, stranger, "This loadout manager is not yours.")
        )
        self.assertEqual(stranger.response.sent, ["This loadout manager is not yours."])
        self.assertEqual(_armory_owner_ids(ctx), {111, 333})

    def test_shop_will_not_charge_the_old_price(self):
        self.assertTrue(listing_price_changed(9000, 5000))
        self.assertFalse(listing_price_changed(5000, 5000))
        self.assertFalse(listing_price_changed(5000, None))

    def test_stale_armory_cache_is_treated_as_sold_when_item_is_gone(self):
        pages = [[{"id": 2, "armory_key": "weapon:2"}]]
        self.assertFalse(armory_item_still_listed(pages, "weapon:1"))
        self.assertTrue(armory_item_still_listed(pages, "weapon:2"))
        self.assertTrue(
            resolve_armory_invoke_outcome(succeeded=False, still_owned=False)
        )
        self.assertFalse(
            resolve_armory_invoke_outcome(succeeded=False, still_owned=True)
        )
        self.assertTrue(
            resolve_armory_invoke_outcome(succeeded=True, still_owned=True)
        )

    def test_command_callback_none_is_success_false_is_failure(self):
        self.assertTrue(invoke_callback_succeeded(None))
        self.assertTrue(invoke_callback_succeeded("ok"))
        self.assertFalse(invoke_callback_succeeded(False))

    def test_gear_tab_filters_match_shop_style_with_has_enchantment(self):
        helm = {
            "archetype": "guardian",
            "slot": "head",
            "rarity": "Rare",
            "enchantments": "Fortified",
        }
        cuirass = {"archetype": "slayer", "slot": "chest", "rarity": "legendary"}
        self.assertTrue(armory_item_matches_gear_filters(helm, set()))
        self.assertTrue(armory_item_matches_gear_filters(helm, {"line:guardian", "slot:head"}))
        self.assertFalse(armory_item_matches_gear_filters(helm, {"line:slayer"}))
        self.assertTrue(armory_item_matches_gear_filters(helm, {"rarity:rare", "rarity:legendary"}))
        self.assertTrue(armory_item_matches_gear_filters(cuirass, {"rarity:rare", "rarity:legendary"}))
        self.assertFalse(armory_item_matches_gear_filters(helm, {"line:guardian", "slot:chest"}))
        self.assertTrue(armory_item_matches_gear_filters(helm, {"enchant:any"}))
        self.assertFalse(armory_item_matches_gear_filters(cuirass, {"enchant:any"}))
        enchant_values = [value for value, _label, _emoji in ARMORY_GEAR_FILTER_OPTIONS if value.startswith("enchant")]
        self.assertEqual(["enchant:any"], enchant_values)
        self.assertEqual(armory_gear_filter_labels({"line:guardian", "slot:head"}), "Aegis (Guardian) · Helm")


class ArmoryNameSearchTests(unittest.TestCase):
    sword = {"name": "Dragonbone Blade", "type": "Sword", "element": "Fire"}
    axe = {"name": "Frost Cleaver", "type": "Axe", "element": "Water"}
    renamed = {"name": "Mr Pointy", "original_name": "Ancient Spear", "type": "Spear"}

    def test_plain_text_matches_anywhere_ignoring_case(self):
        self.assertTrue(armory_name_matches(self.sword, "dragon"))
        self.assertTrue(armory_name_matches(self.sword, "BONE"))
        self.assertTrue(armory_name_matches(self.sword, "sword"))
        self.assertTrue(armory_name_matches(self.sword, "fire"))
        self.assertFalse(armory_name_matches(self.axe, "dragon"))

    def test_wildcards(self):
        self.assertTrue(armory_name_matches(self.sword, "*blade"))
        self.assertFalse(armory_name_matches(self.sword, "blade*"))
        self.assertTrue(armory_name_matches(self.sword, "dragon*"))
        self.assertTrue(armory_name_matches(self.axe, "fr?st*"))
        self.assertTrue(armory_name_matches(self.axe, "*clea*"))
        self.assertFalse(armory_name_matches(self.axe, "*blade"))

    def test_renamed_weapons_still_found_by_original_name(self):
        self.assertTrue(armory_name_matches(self.renamed, "pointy"))
        self.assertTrue(armory_name_matches(self.renamed, "ancient"))

    def test_empty_search_matches_everything_and_input_is_tidied(self):
        self.assertTrue(armory_name_matches(self.axe, ""))
        self.assertTrue(armory_name_matches(self.axe, None))
        self.assertEqual("frost cleaver", armory_clean_search("  Frost   CLEAVER "))
        self.assertEqual(40, len(armory_clean_search("x" * 99)))

    def test_brackets_are_literal_not_patterns(self):
        odd = {"name": "Blade [Old]", "type": "Sword"}
        self.assertTrue(armory_name_matches(odd, "*[old]"))
        self.assertTrue(armory_name_matches(odd, "[old"))


if __name__ == "__main__":
    unittest.main()

import asyncio
import datetime
import unittest
from types import SimpleNamespace
from unittest import mock

import cogs.profile as profile
from utils import elixirs


def _categories(active=()):
    """The inventory as the builder makes it, from fake rows (no database)."""
    cog = profile.Profile.__new__(profile.Profile)
    amulets = [{"id": 7, "type": "health", "tier": 3, "equipped": True, "hp": 120, "defense": 10, "attack": 5, "value": 900}]
    consumables = [
        {"consumable_type": "pet_xp_potion", "quantity": 2},
        {"consumable_type": "elixir_giants_stew_gold", "quantity": 3},
        {"consumable_type": "elixir_fire_ward_plain", "quantity": 1},
    ]
    with mock.patch.object(profile.Profile, "_get_amulet_recycle_refund", return_value=None, create=True), \
         mock.patch.object(profile.Profile, "_format_amulet_recycle_refund", return_value="", create=True):
        return cog._build_inventory_categories(amulets, {"resetpotion": 1}, consumables, [], [], list(active))


class Author(SimpleNamespace):
    display_avatar = SimpleNamespace(url="https://example.invalid/a.png")


def _view(categories):
    ctx = SimpleNamespace(author=Author(id=1, display_name="Lunar"), bot=SimpleNamespace(get_cog=lambda name: None))
    return profile.InventoryCategoryView(ctx, SimpleNamespace(), categories)


def _labels(view):
    return [getattr(c, "label", None) or getattr(c, "placeholder", None) for c in view.children]


class TestInventory(unittest.TestCase):
    def run_async(self, coro):
        return asyncio.new_event_loop().run_until_complete(coro)

    def test_categories_have_icons_counts_and_elixir_details(self):
        cats = {c["key"]: c for c in _categories()}
        self.assertEqual(cats["amulets"]["overview"], "1 amulet · 1 equipped")
        self.assertEqual(cats["elixirs"]["overview"], "4 bottles · 0 working")
        self.assertEqual(cats["elixirs"]["emoji"], profile.INVENTORY_EMOJI["category:elixirs"])
        stew = next(e for e in cats["elixirs"]["entries"] if e["elixir_id"] == "giants_stew")
        self.assertEqual((stew["quality"], stew["quantity"], stew["emoji"]), (2, 3, elixirs.emoji("giants_stew")))
        # The game's own emotes where it has them: the amulet's type, the potion's picture.
        self.assertEqual(cats["amulets"]["entries"][0]["emoji"], profile.INVENTORY_EMOJI["amulet:health"])
        xp = next(e for e in cats["potions"]["entries"] if e["entry_key"] == "potion:pet_xp_potion")
        self.assertEqual(xp["emoji"], profile.INVENTORY_EMOJI["potion:pet_xp_potion"])

    def test_the_buttons_follow_the_category(self):
        async def go():
            view = _view(_categories())
            self.assertEqual(view.build_embed().title, "Inventory")
            self.assertNotIn("Drink", _labels(view))
            # Elixirs: open the Gold Giant's Stew, it can be drunk; Drink asks first.
            view.selected_key = "elixirs"
            view.selected_entry_key = "elixir:elixir_giants_stew_gold"
            view.detail_mode = True
            view.sync_controls()
            self.assertIn("Drink", _labels(view))
            self.assertNotIn("Equip", _labels(view))
            view.confirm = {"action": "drink", "entry_key": view.selected_entry_key}
            view.sync_controls()
            self.assertEqual(_labels(view)[1:], ["Drink it", "Cancel"])
            embed = view.build_embed()
            self.assertIn("2 hours", embed.description)
            self.assertIn("1 of 2 working", embed.fields[0].name)
            # Amulets: Unequip (it's on) and Recycle, no Drink.
            view.confirm = None
            view.selected_key, view.selected_entry_key = "amulets", "amulet:7"
            view.sync_controls()
            self.assertIn("Unequip", _labels(view))
            self.assertIn("Recycle", _labels(view))
            self.assertNotIn("Drink", _labels(view))
        self.run_async(go())

    def test_drink_is_off_when_the_same_one_or_two_are_working(self):
        later = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=1)

        async def go():
            view = _view(_categories([{"elixir": "giants_stew", "quality": 1, "expires_at": later}]))
            view.selected_key, view.selected_entry_key, view.detail_mode = "elixirs", "elixir:elixir_giants_stew_gold", True
            view.sync_controls()
            drink = next(c for c in view.children if getattr(c, "label", "") == "Drink")
            self.assertTrue(drink.disabled)
            self.assertIn("already working", view.build_embed().fields[-1].value)
            # A different elixir can still go in the second slot.
            view.selected_entry_key = "elixir:elixir_fire_ward_plain"
            view.sync_controls()
            self.assertFalse(next(c for c in view.children if getattr(c, "label", "") == "Drink").disabled)
            # Two working: no more.
            view = _view(_categories([{"elixir": "giants_stew", "quality": 1, "expires_at": later},
                                      {"elixir": "thornwine", "quality": 0, "expires_at": later}]))
            view.selected_key, view.selected_entry_key, view.detail_mode = "elixirs", "elixir:elixir_fire_ward_plain", True
            view.sync_controls()
            self.assertTrue(next(c for c in view.children if getattr(c, "label", "") == "Drink").disabled)
            self.assertIn("Working now (2 of 2)", view.build_home_embed().fields[1].name)
        self.run_async(go())


class TestInventoryEmotes(unittest.TestCase):
    def test_every_picture_is_a_custom_emote_and_every_potion_has_one(self):
        import re
        for key, markup in profile.INVENTORY_EMOJI.items():
            self.assertRegex(markup, r"^<:[A-Za-z0-9_]{2,32}:\d{17,20}>$", key)
            self.assertIsNotNone(profile._inventory_emoji(markup), key)
        source = open(profile.__file__, encoding="utf-8").read()
        for key in re.findall(r'"entry_key": "(potion:[a-z_]+)"', source):
            self.assertIn(key, profile.INVENTORY_EMOJI, key)

    def test_buttons_carry_their_emotes(self):
        async def go():
            view = _view(_categories())
            view.selected_key, view.selected_entry_key, view.detail_mode = "elixirs", "elixir:elixir_giants_stew_gold", True
            view.sync_controls()
            drink = next(c for c in view.children if getattr(c, "label", "") == "Drink")
            refresh = next(c for c in view.children if getattr(c, "label", "") == "Refresh")
            self.assertEqual(drink.emoji.name, "inv_drink")
            self.assertEqual(refresh.emoji.name, "inv_refresh")
        asyncio.new_event_loop().run_until_complete(go())


class FakeResponse:
    def __init__(self):
        self.edits, self.deferred, self.messages = [], False, []

    async def edit_message(self, **kwargs):
        self.edits.append(kwargs)

    async def defer(self, **kwargs):
        self.deferred = True

    async def send_message(self, text, **kwargs):
        self.messages.append(text)


class TestInventoryDrinking(unittest.TestCase):
    def test_drink_then_confirm_drinks_it_and_refreshes(self):
        drunk = []
        later = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=2)

        async def drink_elixir(user_id, elixir_id, quality):
            drunk.append((user_id, elixir_id, quality))
            return True, "Gold Giant's Stew uncorked!"

        async def fetch(user_id):
            return _categories([{"elixir": "giants_stew", "quality": 2, "expires_at": later}])

        async def go():
            elixir_cog = SimpleNamespace(drink_elixir=drink_elixir)
            ctx = SimpleNamespace(author=Author(id=1, display_name="Lunar"), bot=SimpleNamespace(get_cog=lambda name: elixir_cog))
            view = profile.InventoryCategoryView(ctx, SimpleNamespace(_fetch_inventory_categories=fetch), _categories())
            view.selected_key, view.selected_entry_key, view.detail_mode = "elixirs", "elixir:elixir_giants_stew_gold", True
            view.sync_controls()
            sent, edited = [], []

            async def followup_send(text, **kwargs):
                sent.append((text, kwargs.get("ephemeral")))

            async def message_edit(**kwargs):
                edited.append(kwargs)

            interaction = SimpleNamespace(response=FakeResponse(), followup=SimpleNamespace(send=followup_send),
                                          message=SimpleNamespace(edit=message_edit))
            await view.ask_drink(interaction)
            self.assertEqual(view.confirm["action"], "drink")
            self.assertEqual(drunk, [])                       # nothing yet: it asked first
            await view.confirm_action(interaction)
            self.assertEqual(drunk, [(1, "giants_stew", 2)])
            self.assertEqual(sent, [("Gold Giant's Stew uncorked!", True)])
            self.assertIsNone(view.confirm)
            # Back on the elixir, now shown as working, Drink off.
            self.assertIn("already working", edited[-1]["embed"].fields[-1].value)
            self.assertTrue(next(c for c in view.children if getattr(c, "label", "") == "Drink").disabled)
            # Cancel goes back without drinking.
            view.selected_entry_key = "elixir:elixir_fire_ward_plain"
            view.sync_controls()
            await view.ask_drink(interaction)
            await view.cancel_action(interaction)
            self.assertEqual(len(drunk), 1)
        asyncio.new_event_loop().run_until_complete(go())


if __name__ == "__main__":
    unittest.main()

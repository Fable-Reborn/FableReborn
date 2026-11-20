import unittest

from classes.equipment.repository import listing_price_changed
from cogs.equipment.shop import (
    GearShopView,
    _gold,
    _short_label,
    _slot_name,
    filtered_listings,
)


class GearShopFormatTests(unittest.TestCase):
    def test_short_label_fits_select(self):
        label = _short_label(
            {"rarity": "legendary", "slot": "chest", "price": 45000, "name": "Mythic Razor Cuirass"}
        )
        self.assertLessEqual(len(label), 100)
        self.assertIn("$45,000", label)
        self.assertIn("Cuirass", label)

    def test_stall_windows_around_selection(self):
        listings = [
            {
                "id": index,
                "name": f"Piece {index}",
                "slot": "head",
                "rarity": "common",
                "archetype": "guardian",
                "quality": 40,
                "refinement": 0,
                "offense_value": 0.01,
                "defense_value": 1,
                "price": 1000 * index,
                "seller_id": 1,
                "modifiers": [],
            }
            for index in range(1, 10)
        ]
        shop = GearShopView.__new__(GearShopView)
        shop.listings = listings
        shop.selected_id = 8
        shop.author_id = 2
        shop.filters = set()
        shop.sort_mode = "newest"
        text = GearShopView.stall_lines(shop)
        self.assertIn("Showing 1–6 of 9", text)
        self.assertIn("▶", text)

    def test_selected_text_flags_short_gold_and_own_listing(self):
        item = {
            "id": 12,
            "name": "Mythic Razor Cuirass",
            "slot": "chest",
            "rarity": "legendary",
            "archetype": "slayer",
            "quality": 88,
            "refinement": 2,
            "offense_value": 0.14,
            "defense_value": 3.5,
            "price": 45000,
            "seller_id": 99,
            "modifiers": [],
        }
        shop = GearShopView.__new__(GearShopView)
        shop.listings = [item]
        shop.selected_id = 12
        shop.author_id = 1
        shop.gold = 12000
        shop.filters = set()
        shop.sort_mode = "newest"
        text = GearShopView.selected_text(shop)
        self.assertIn("Short $33,000", text)
        self.assertIn("Blessing", text)
        self.assertIn("Ward", text)
        shop.author_id = 99
        self.assertIn("your listing", GearShopView.selected_text(shop))

    def test_stale_confirm_price_is_rejected(self):
        self.assertFalse(listing_price_changed(5000, None))
        self.assertFalse(listing_price_changed(5000, 5000))
        self.assertTrue(listing_price_changed(9000, 5000))

    def test_gold_and_slot_helpers(self):
        self.assertEqual(_gold(1500), "$1,500")
        self.assertEqual(_slot_name({"slot": "feet"}), "Sabatons")

    def test_filter_and_sort_combine(self):
        listings = [
            {
                "id": 1,
                "name": "Cheap Helm",
                "slot": "head",
                "rarity": "common",
                "archetype": "guardian",
                "quality": 20,
                "refinement": 0,
                "offense_value": 0.01,
                "defense_value": 8,
                "price": 100,
                "seller_id": 1,
                "modifiers": [],
            },
            {
                "id": 2,
                "name": "Strong Cuirass",
                "slot": "chest",
                "rarity": "legendary",
                "archetype": "slayer",
                "quality": 90,
                "refinement": 3,
                "offense_value": 0.2,
                "defense_value": 2,
                "price": 9000,
                "seller_id": 2,
                "modifiers": [],
            },
            {
                "id": 3,
                "name": "Ward Cuirass",
                "slot": "chest",
                "rarity": "legendary",
                "archetype": "guardian",
                "quality": 80,
                "refinement": 1,
                "offense_value": 0.03,
                "defense_value": 20,
                "price": 5000,
                "seller_id": 2,
                "modifiers": [],
            },
        ]
        legendary = filtered_listings(listings, {"rarity:legendary"}, 1, "ward")
        self.assertEqual([item["id"] for item in legendary], [3, 2])
        guardian_chest = filtered_listings(
            listings, {"line:guardian", "slot:chest"}, 1, "blessing"
        )
        self.assertEqual([item["id"] for item in guardian_chest], [3])
        mine = filtered_listings(listings, {"mine"}, 1, "price_high")
        self.assertEqual([item["id"] for item in mine], [1])


if __name__ == "__main__":
    unittest.main()

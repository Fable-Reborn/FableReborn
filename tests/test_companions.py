"""Companion roster data and the select-screen renderer."""

import unittest
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import patch

from PIL import Image

from cogs.companions import card
from cogs.companions import CompanionView
from cogs.companions.roster import BY_KEY, COMPANIONS, EVIL, GOOD, find


class CompanionRosterTestCase(unittest.TestCase):
    def test_keys_are_unique_and_art_exists(self):
        self.assertEqual(len(BY_KEY), len(COMPANIONS))
        for companion in COMPANIONS:
            self.assertIn(companion.alignment, (GOOD, EVIL))
            for kind in ("portrait", "silhouette"):
                self.assertTrue((card.ART_DIR / companion.key / f"{kind}.png").exists(), (companion.key, kind))

    def test_alignments(self):
        self.assertEqual(BY_KEY["azuar"].alignment, GOOD)
        self.assertEqual(BY_KEY["ryjin"].alignment, EVIL)
        self.assertEqual(BY_KEY["gyle"].alignment, EVIL)

    def test_find_ignores_case_and_apostrophes(self):
        self.assertIs(find("Az'uar"), BY_KEY["azuar"])
        self.assertIs(find("RYJIN"), BY_KEY["ryjin"])
        self.assertIsNone(find("nobody"))


class CompanionCardTestCase(unittest.TestCase):
    def render(self, index, unlocked, selected=None):
        with Image.open(BytesIO(card.render_select_card(index, unlocked, selected).getvalue())) as image:
            image.load()
            return image

    def test_renders_every_companion_locked_and_unlocked(self):
        everyone = {companion.key for companion in COMPANIONS}
        for index in range(len(COMPANIONS)):
            for unlocked in (set(), everyone):
                image = self.render(index, unlocked, COMPANIONS[index].key if unlocked else None)
                self.assertEqual(image.size, (card.WIDTH, card.HEIGHT))
                self.assertEqual(image.format, "JPEG")

    def test_locked_and_unlocked_cards_differ(self):
        locked = self.render(0, set())
        unlocked = self.render(0, {COMPANIONS[0].key})
        self.assertNotEqual(locked.tobytes(), unlocked.tobytes())

    def test_locked_tiamat_never_loads_identifying_art(self):
        card._render.cache_clear()
        card._hero_art.cache_clear()
        card._tile.cache_clear()
        original = card._art

        def guarded_art(key, kind):
            self.assertNotEqual(key, "tiamat", "Locked Tiamat must not load her portrait or silhouette")
            return original(key, kind)

        index = COMPANIONS.index(BY_KEY["tiamat"])
        with patch.object(card, "_art", side_effect=guarded_art):
            self.render(index, set())


class SecretCompanionViewTestCase(unittest.IsolatedAsyncioTestCase):
    async def test_tiamat_identity_is_revealed_only_after_unlock(self):
        index = COMPANIONS.index(BY_KEY["tiamat"])
        for unlocked in (set(), {"tiamat"}):
            view = CompanionView(None, SimpleNamespace(id=1), unlocked, None)
            view.index = index
            view.refresh_items()
            option = view.options()[index]
            select = next(item for item in view.children if item.custom_id == "companion:select")
            if unlocked:
                self.assertEqual(option.label, "Tiamat")
                self.assertIn("Goddess of Creation", option.description)
                self.assertFalse(select.disabled)
            else:
                self.assertEqual(option.label, f"??? #{index + 1}")
                self.assertEqual(option.description, "Secret · Locked")
                self.assertTrue(select.disabled)
            view.stop()


if __name__ == "__main__":
    unittest.main()

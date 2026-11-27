import io
import unittest
from unittest import mock

from PIL import Image

from cogs.getwell import card
from utils import boot_cogs
from utils import getwell as lib

BIRTHDAY_BUTTON_IDS = {"birthdaywish:approve", "birthdaywish:reject"}



class TestRules(unittest.TestCase):
    def test_eligibility(self):
        self.assertEqual(lib.not_eligible(None), "not_member")
        self.assertEqual(lib.not_eligible({"roles": ["1", str(lib.ALT_ROLE_ID)]}), "alt")
        self.assertIsNone(lib.not_eligible({"roles": ["1", "2"]}))
        self.assertIsNone(lib.not_eligible({}))

    def test_message_rules_are_the_birthday_ones(self):
        self.assertEqual(lib.check_message("  Get   well **soon**  "), "Get well soon")
        for text, code in (("see https://example.com", "link"), ("hi", "short"), ("x" * 201, "long"), ("   ", "empty")):
            with self.assertRaises(lib.WishProblem) as caught:
                lib.check_message(text)
            self.assertEqual(caught.exception.args[0], code)

    def test_picks_are_checked(self):
        self.assertEqual(len(lib.check_picks([("tonic", 0)] * 0)), 0)
        with self.assertRaises(ValueError):
            lib.check_picks([("not-an-elixir", 0)])
        with self.assertRaises(ValueError):
            lib.check_picks([("x", 9)])

    def test_unset_ids_are_listed(self):
        self.assertEqual(lib.REVIEW_CHANNEL_ID, 1570410119508787363)
        with mock.patch.multiple(lib, GUILD_ID=1, REVIEW_CHANNEL_ID=3):
            self.assertEqual(lib.unset_ids(), [])
        with mock.patch.multiple(lib, GUILD_ID=1, REVIEW_CHANNEL_ID=0):
            self.assertEqual(lib.unset_ids(), ["REVIEW_CHANNEL_ID"])


class TestSeparation(unittest.TestCase):
    def test_sql_only_touches_getwell_tables(self):
        self.assertNotIn("birthday_", lib.TABLE_SQL)
        self.assertIn("getwell_wishes", lib.TABLE_SQL)
        self.assertIn("getwell_event", lib.TABLE_SQL)
        self.assertIn("getwell_wishes_one_open", lib.TABLE_SQL)

    def test_button_ids_do_not_collide_with_the_birthday_ones(self):
        ids = {lib.APPROVE_ID, lib.REJECT_ID}
        self.assertEqual(len(ids), 2)
        self.assertFalse(ids & BIRTHDAY_BUTTON_IDS)
        self.assertTrue(all(i.startswith("getwell:") for i in ids))

    def test_cog_is_registered(self):
        self.assertIn("cogs.getwell", boot_cogs.EXTRA_COGS)


class TestCard(unittest.TestCase):
    @staticmethod
    def wishes(n, message="Get well soon!"):
        return [dict(name=f"Friend {i}", message=message) for i in range(n)]

    def test_one_wish_is_one_page(self):
        pages = card.render_cards("Sam", self.wishes(1))
        self.assertEqual(len(pages), 1)
        self.assertTrue(pages[0][1].startswith("getwell_card"))

    def test_paging(self):
        pages = card.render_cards("Sam", self.wishes(card.PER_PAGE + 1))
        self.assertEqual(len(pages), 2)
        self.assertEqual([name for _data, name in pages], ["getwell_card_1.png", "getwell_card_2.png"])
        self.assertEqual(len(card.render_cards("Sam", self.wishes(card.PER_PAGE))), 1)

    def test_size_and_hard_cases(self):
        hard = "Rest up 🤗 ♥ 💜 ⭐ " + "wonderfully long words " * 8
        pages = card.render_cards("A Very Long Recipient Name Indeed", self.wishes(4, hard[:200]) + [dict(name="", message="ok!")])
        for data, _name in pages:
            self.assertLessEqual(len(data), card.MAX_BYTES)
            with Image.open(io.BytesIO(data)) as image:
                self.assertEqual(image.width, card.W)

    def test_empty_card_still_renders(self):
        self.assertEqual(len(card.render_cards("Sam", [])), 1)


if __name__ == "__main__":
    unittest.main()

import datetime
import hashlib
import unittest

from cogs.gm_events import logic
from cogs.gm_events.logic import Bid

T0 = datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone.utc)


def at(seconds):
    return T0 + datetime.timedelta(seconds=seconds)


class SilentWinnerTests(unittest.TestCase):
    def test_no_bids(self):
        self.assertIsNone(logic.pick_silent_winner([]))

    def test_highest_wins(self):
        bids = [Bid(1, 100, at(0)), Bid(2, 300, at(5)), Bid(3, 200, at(1))]
        self.assertEqual(logic.pick_silent_winner(bids).user_id, 2)

    def test_tie_goes_to_earliest_amount_set_at(self):
        bids = [Bid(1, 300, at(10)), Bid(2, 300, at(3)), Bid(3, 100, at(0))]
        self.assertEqual(logic.pick_silent_winner(bids).user_id, 2)

    def test_full_tie_uses_lowest_user_id(self):
        bids = [Bid(9, 300, at(3)), Bid(4, 300, at(3))]
        self.assertEqual(logic.pick_silent_winner(bids).user_id, 4)

    def test_order_independent(self):
        bids = [Bid(1, 50, at(1)), Bid(2, 50, at(0)), Bid(3, 10, at(0))]
        self.assertEqual(
            logic.pick_silent_winner(bids), logic.pick_silent_winner(list(reversed(bids)))
        )


class RaffleTests(unittest.TestCase):
    SECRET = "ab" * 32

    def tickets(self):
        return logic.build_tickets([(1, 2), (2, 3), (1, 1)])

    def test_build_tickets_numbering(self):
        self.assertEqual(
            self.tickets(), [(1, 1), (2, 1), (3, 2), (4, 2), (5, 2), (6, 1)]
        )

    def test_empty(self):
        self.assertIsNone(logic.draw_winner(self.SECRET, []))

    def test_single_entrant_wins(self):
        no, user, _digest = logic.draw_winner(self.SECRET, logic.build_tickets([(7, 1)]))
        self.assertEqual((no, user), (1, 7))

    def test_deterministic(self):
        self.assertEqual(
            logic.draw_winner(self.SECRET, self.tickets()),
            logic.draw_winner(self.SECRET, self.tickets()),
        )

    def test_changes_when_a_ticket_changes(self):
        base = self.tickets()
        changed = list(base)
        changed[0] = (1, 99)
        self.assertNotEqual(logic.ticket_digest(base), logic.ticket_digest(changed))
        # across many secrets the outcome must differ somewhere
        diffs = sum(
            logic.draw_winner(f"{i:064x}", base) != logic.draw_winner(f"{i:064x}", changed)
            for i in range(50)
        )
        self.assertGreater(diffs, 0)

    def test_commitment_verifies(self):
        self.assertEqual(
            logic.commitment(self.SECRET), hashlib.sha256(self.SECRET.encode()).hexdigest()
        )
        self.assertNotEqual(logic.commitment(self.SECRET), logic.commitment("cd" * 32))

    def test_every_ticket_can_win(self):
        tickets = logic.build_tickets([(1, 1), (2, 1), (3, 1), (4, 1)])
        winners = {logic.draw_winner(f"{i:064x}", tickets)[0] for i in range(300)}
        self.assertEqual(winners, {1, 2, 3, 4})

    def test_distribution_is_proportional(self):
        tickets = logic.build_tickets([(1, 1), (2, 3)])
        runs = 4000
        wins = sum(logic.draw_winner(f"{i:064x}", tickets)[1] == 2 for i in range(runs))
        self.assertAlmostEqual(wins / runs, 0.75, delta=0.04)


class ParsingTests(unittest.TestCase):
    def test_amounts(self):
        cases = {"1000": 1000, "1,000": 1000, " 5k ": 5000, "1.5m": 1_500_000, "2B": 2 * 10**9, "$7": 7}
        for text, expected in cases.items():
            self.assertEqual(logic.parse_amount(text), expected, text)

    def test_bad_amounts(self):
        for text in ["", "0", "-5", "abc", "1.5", "1.2.3", "1e5", "10**15", "0k", "1 000",
                     str(10**15 + 1), "2000000000000k", "١٢٣"]:
            with self.assertRaises(ValueError, msg=text):
                logic.parse_amount(text)

    def test_cap_boundary(self):
        self.assertEqual(logic.parse_amount(str(10**15)), 10**15)

    def test_quantity(self):
        self.assertEqual(logic.parse_quantity("1,000"), 1000)
        for text in ["0", "1001", "-1", "x", "1.5", ""]:
            with self.assertRaises(ValueError, msg=text):
                logic.parse_quantity(text)

    def test_duration_bounds(self):
        lo, hi = logic.SILENT_MIN_DURATION, logic.SILENT_MAX_DURATION
        self.assertEqual(logic.parse_duration("5m", lo, hi), datetime.timedelta(minutes=5))
        self.assertEqual(logic.parse_duration("1d12h", lo, hi), datetime.timedelta(hours=36))
        self.assertEqual(logic.parse_duration("14d", lo, hi), datetime.timedelta(days=14))
        for text in ["4m", "15d", "31d", "0h", "", "soon", "10"]:
            with self.assertRaises(ValueError, msg=text):
                logic.parse_duration(text, lo, hi)

    def test_long_duration_message_is_not_about_birthdays(self):
        with self.assertRaises(ValueError) as ctx:
            logic.parse_duration("40d", logic.SILENT_MIN_DURATION, logic.SILENT_MAX_DURATION)
        self.assertNotIn("Birthday", str(ctx.exception))


class CogImportTests(unittest.TestCase):
    def test_cog_module_imports_and_is_registered(self):
        import importlib

        from utils import boot_cogs

        module = importlib.import_module("cogs.gm_events")
        self.assertTrue(hasattr(module, "setup"))
        self.assertIn("cogs.gm_events", boot_cogs.EXTRA_COGS)


if __name__ == "__main__":
    unittest.main()

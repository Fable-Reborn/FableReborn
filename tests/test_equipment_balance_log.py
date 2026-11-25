import unittest
from datetime import datetime, timezone

from classes.equipment.balance_log import build_review_markdown


class EquipmentBalanceLogTests(unittest.TestCase):
    def test_review_markdown_summarizes_actions(self):
        rows = [
            {
                "created_at": datetime.now(timezone.utc),
                "user_id": 1,
                "action": "craft",
                "equipment_id": 10,
                "rarity": "common",
                "archetype": "guardian",
                "slot": "chest",
                "payload": {"quality": 55},
            },
            {
                "created_at": datetime.now(timezone.utc),
                "user_id": 1,
                "action": "temper",
                "equipment_id": 10,
                "rarity": "common",
                "archetype": "guardian",
                "slot": "chest",
                "payload": {"success": True, "pity_used": False, "star": 1, "refinement": 1},
            },
            {
                "created_at": datetime.now(timezone.utc),
                "user_id": 2,
                "action": "crate",
                "equipment_id": None,
                "rarity": "rare",
                "archetype": None,
                "slot": None,
                "payload": {"has_piece": False, "materials": {"bog_iron": 2}},
            },
        ]
        text = build_review_markdown(rows, days=7, database="FableDev")
        self.assertIn("Unique players: **2**", text)
        self.assertIn("`craft`: 1", text)
        self.assertIn("common**: 1 crafts", text)
        self.assertIn("temper**: 1 attempts", text)
        self.assertIn("materials-only", text)


def _row(action, payload, user_id=1):
    return {
        "created_at": datetime.now(timezone.utc),
        "user_id": user_id,
        "action": action,
        "equipment_id": 1,
        "rarity": "rare",
        "archetype": "guardian",
        "slot": "chest",
        "payload": payload,
    }


def _old_temper(star, success):
    """Rows as the forge wrote them before the fix: `star` is where the piece ended up."""
    return _row("temper", {"success": success, "pity_used": False, "star": star, "refinement": star})


class TemperAndPityCountingTests(unittest.TestCase):
    def last_week_tempers(self):
        # The 2026-11-25 export: star reached -> (attempts, successes).
        buckets = {0: (4, 0), 1: (14, 12), 2: (12, 8), 3: (8, 6), 4: (8, 6), 5: (2, 2)}
        rows = []
        for star, (total, ok) in buckets.items():
            rows += [_old_temper(star, True) for _ in range(ok)]
            rows += [_old_temper(star, False) for _ in range(total - ok)]
        return rows

    def test_old_rows_are_counted_by_the_star_attempted(self):
        text = build_review_markdown(self.last_week_tempers(), days=7)
        self.assertIn("temper**: 48 attempts, success 70.8%", text)
        self.assertIn("Temper by star attempted", text)
        self.assertIn("+1: 12/16 (75.0% success) [90%]", text)
        self.assertIn("+2: 8/10 (80.0% success) [80%]", text)
        self.assertIn("+3: 6/10 (60.0% success) [70%]", text)
        self.assertIn("+4: 6/8 (75.0% success) [60%]", text)
        self.assertIn("+5: 2/4 (50.0% success) [50%]", text)
        self.assertNotIn("+0:", text)

    def test_new_rows_use_target_star(self):
        rows = [
            _row("temper", {"success": False, "star": 2, "target_star": 3, "pity_threshold": 2}),
            _row("temper", {"success": True, "star": 3, "target_star": 3, "pity_threshold": 2}),
        ]
        self.assertIn("+3: 1/2 (50.0% success) [70%]", build_review_markdown(rows, days=7))

    def test_guaranteed_refines_are_not_pity(self):
        rows = [
            # Old rows: quality 39 or lower always succeeds and was logged as pity.
            *[_row("refine", {"success": True, "pity_used": True, "quality_before": 20}) for _ in range(3)],
            # A real pity save in the 90% band (pity 2).
            _row("refine", {"success": True, "pity_used": True, "quality_before": 50}),
            _row("refine", {"success": False, "pity_used": False, "quality_before": 50}),
            # New rows carry the threshold.
            _row("refine", {"success": True, "pity_used": False, "quality_before": 10, "pity_threshold": 0}),
        ]
        text = build_review_markdown(rows, days=7)
        self.assertIn("refine**: 6 attempts, success 83.3%, pity used 1", text)
        self.assertIn("4 were guaranteed (quality 39 or lower). The other 2: success 50.0%", text)


class ExtraReportTests(unittest.TestCase):
    def rows(self):
        return [
            _row("crate", {"has_piece": True, "piece_id": 5, "quality": 40, "materials": {"bog_iron": 2}}),
            _row("crate", {"has_piece": True, "piece_id": 6, "quality": 70, "materials": {"bog_iron": 1}}),
            _row("crate", {"has_piece": True, "piece_id": 7, "quality": 95, "fully_rolled": True, "materials": {}}),
            _row("crate", {"has_piece": False, "materials": {"fen_iron": 3}}),
            _row("dragon_materials", {"materials": {"bog_iron": 4}}),
            _row("salvage", {"materials": {"bog_iron": 2}}),
            _row("salvage", {"materials": {"bog_iron": 1}, "bulk": True}),
            _row("craft", {"quality": 50, "cost": {"bog_iron": 5, "fen_iron": 1}}),
            _row("refine", {"success": True, "quality_before": 50, "cost": {"bog_iron": 2}, "gold": 4000}),
            # An older temper row with no cost: priced from the cost table.
            _row("temper", {"success": True, "star": 1}),
            _row("market_buy", {"price": 2500}),
            _row("equip", {}),
        ]

    def test_new_sections(self):
        text = build_review_markdown(self.rows(), days=7)
        self.assertIn("## Crate pieces", text)
        self.assertIn("**rare**: 2 pieces, quality avg 55.0 (expected about 51.7), min 40, max 70", text)
        self.assertIn("Fully rolled discoveries: 1", text)
        self.assertIn("## Salvage by rarity", text)
        self.assertIn("**rare**: 2 (1 single, 1 Salvage All)", text)
        self.assertIn("Earned from crates: common 3, uncommon 3", text)
        self.assertIn("Earned from dragons: common 4", text)
        self.assertIn("Earned from salvage: common 3", text)
        self.assertIn("Spent on craft: common 5, uncommon 1", text)
        self.assertIn("Spent on refine: common 2", text)
        self.assertIn("refine $4,000", text)
        self.assertIn("temper $60,000", text)
        self.assertIn("1 older forge rows were priced from today's cost tables.", text)
        self.assertIn("Gear shop gold traded: $2,500", text)
        self.assertIn("By line: Aegis (Guardian) 1", text)
        self.assertIn("Snapshot not available.", text)

    def test_snapshot_sections(self):
        snapshot = {
            "worn": [
                {"user_id": 1, "archetype": "guardian", "rarity": "rare", "slot": "head", "quality": 60, "refinement": 2},
                {"user_id": 1, "archetype": "guardian", "rarity": "rare", "slot": "chest", "quality": 40, "refinement": 0},
                {"user_id": 1, "archetype": "slayer", "rarity": "legendary", "slot": "legs", "quality": 80, "refinement": 1},
                {"user_id": 2, "archetype": "slayer", "rarity": "common", "slot": "feet", "quality": 30, "refinement": 0},
            ],
            "materials": [
                {"material_id": "bog_iron", "total": 120, "holders": 9},
                {"material_id": "cinder_ore", "total": 30, "holders": 4},
                {"material_id": "aegisheart", "total": 2, "holders": 1},
            ],
        }
        text = build_review_markdown([], days=7, snapshot=snapshot)
        self.assertIn("Players wearing armor: 2, pieces worn: 4", text)
        self.assertIn("Pieces by line: Aegis (Guardian) 2 (50%), Razor (Slayer) 2 (50%)", text)
        self.assertIn("Players by main line: Aegis (Guardian) 1, Razor (Slayer) 1", text)
        self.assertIn("rare: 2 worn, quality avg 50.0, temper avg +1.0", text)
        self.assertIn("**common**: 150 held (largest single good held by 9 players)", text)
        self.assertIn("**legendary**: 2 held", text)

    def test_empty_report_still_renders(self):
        text = build_review_markdown([], days=7, snapshot={"worn": [], "materials": []})
        self.assertIn("No crate pieces.", text)
        self.assertIn("Nobody is wearing armor.", text)
        self.assertIn("Nobody holds armor materials.", text)
        self.assertIn("**Net**: none", text)


class SalvageAllLogTests(unittest.IsolatedAsyncioTestCase):
    async def test_one_event_per_piece_with_rarity(self):
        from tests.equipment_fakes import FakeArmoryDB, piece
        from classes.equipment.repository import salvage_many

        db = FakeArmoryDB([piece(1, rarity="common", archetype="guardian"), piece(2)])
        logged = []
        original = db.execute

        async def capture(sql, *args):
            if "INSERT INTO equipment_events" in sql:
                logged.append(args)
            return await original(sql, *args)

        db.execute = capture
        await salvage_many(db, 111, [1, 2])
        self.assertEqual(2, len(logged))
        self.assertEqual({"common", "rare"}, {args[3] for args in logged})
        self.assertTrue(all(args[1] == "salvage" for args in logged))


class LogSavepointTests(unittest.IsolatedAsyncioTestCase):
    async def test_failed_insert_is_contained_in_a_savepoint(self):
        from contextlib import asynccontextmanager
        from classes.equipment.balance_log import log_event

        entered = []

        class Conn:
            @asynccontextmanager
            async def transaction(self):
                entered.append("savepoint")
                yield

            async def execute(self, sql, *args):
                raise RuntimeError("events table locked")

        with self.assertLogs("classes.equipment.balance_log", level="ERROR"):
            await log_event(Conn(), 1, "lock")
        self.assertEqual(["savepoint"], entered)

    async def test_conn_without_transactions_still_logs(self):
        from classes.equipment.balance_log import log_event

        seen = []

        class Bare:
            async def execute(self, sql, *args):
                seen.append(args[1])

        await log_event(Bare(), 1, "salvage")
        self.assertEqual(["salvage"], seen)


class ForgePityFlagTests(unittest.TestCase):
    def test_writer_no_longer_flags_pity_zero_bands(self):
        from pathlib import Path

        source = Path("classes/equipment/repository.py").read_text(encoding="utf-8")
        self.assertEqual(3, source.count('success and step["pity"] > 0 and fails >= step["pity"]'))
        self.assertIn('"target_star": next_star', source)


if __name__ == "__main__":
    unittest.main()

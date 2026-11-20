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


if __name__ == "__main__":
    unittest.main()

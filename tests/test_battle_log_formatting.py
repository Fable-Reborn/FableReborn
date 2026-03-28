import unittest
from types import SimpleNamespace

from tests.pet_test_loader import load_battle_runtime_type


class TestBattleLogFormatting(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.Battle = load_battle_runtime_type()

    def _new_battle(self):
        battle_cls = self.Battle

        class DummyBattle(battle_cls):
            async def start_battle(self):
                return True

            async def process_turn(self):
                return True

            async def end_battle(self):
                return None

            async def update_display(self):
                return None

        ctx = SimpleNamespace(bot=SimpleNamespace(), send=None)
        return DummyBattle(ctx, teams=[])

    def test_format_battle_log_fields_preserves_all_entries(self):
        battle = self._new_battle()
        battle.log.clear()
        battle.log.extend(
            [
                (1, "A" * 700),
                (2, "B" * 700),
                (3, "C" * 700),
            ]
        )

        chunks = battle.format_battle_log_fields(max_length=1020)

        self.assertGreater(len(chunks), 1)
        for chunk in chunks:
            self.assertLessEqual(len(chunk), 1020)

        self.assertEqual(
            "\n\n".join(
                [
                    f"**Action #1**\n{'A' * 700}",
                    f"**Action #2**\n{'B' * 700}",
                    f"**Action #3**\n{'C' * 700}",
                ]
            ),
            "\n\n".join(chunks),
        )

    def test_format_battle_log_fields_splits_single_oversized_entry(self):
        battle = self._new_battle()
        battle.log.clear()
        battle.log.append((9, "X" * 2200))

        chunks = battle.format_battle_log_fields(max_length=1020)

        self.assertGreater(len(chunks), 2)
        for chunk in chunks:
            self.assertLessEqual(len(chunk), 1020)

        reconstructed = "".join(
            chunk.replace("**Action #9**\n", "", 1) for chunk in chunks
        )
        self.assertEqual("X" * 2200, reconstructed)


if __name__ == "__main__":
    unittest.main()

import unittest
from decimal import Decimal
from types import SimpleNamespace

from tests.pet_test_loader import load_battle_runtime_type


class TestBattleClassBuffHelpers(unittest.TestCase):
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

        ctx = SimpleNamespace(bot=SimpleNamespace(cogs={}), send=None)
        return DummyBattle(ctx, teams=[])

    def test_mage_charge_builds_shield(self):
        battle = self._new_battle()
        mage = SimpleNamespace(
            mage_evolution=4,
            is_pet=False,
            max_hp=Decimal("1000"),
            shield=Decimal("0"),
        )

        state = battle.advance_mage_fireball_charge(mage)

        self.assertFalse(state["fireball_ready"])
        self.assertEqual(Decimal("0.3"), state["charge"])
        self.assertEqual(Decimal("30.000"), state["shield_gained"])
        self.assertEqual(Decimal("30.000"), mage.shield)
        self.assertEqual(Decimal("0.3"), mage.fireball_charge)

    def test_mage_charge_uses_overflow_when_fireball_triggers(self):
        battle = self._new_battle()
        mage = SimpleNamespace(
            mage_evolution=4,
            is_pet=False,
            max_hp=Decimal("1000"),
            shield=Decimal("0"),
            fireball_charge=Decimal("0.8"),
        )

        state = battle.advance_mage_fireball_charge(mage)

        self.assertTrue(state["fireball_ready"])
        self.assertEqual(Decimal("0.1"), state["charge"])
        self.assertEqual(Decimal("0"), state["shield_gained"])
        self.assertEqual(Decimal("0.1"), mage.fireball_charge)

    def test_mage_arcane_shield_respects_cap(self):
        battle = self._new_battle()
        mage = SimpleNamespace(
            mage_evolution=4,
            is_pet=False,
            max_hp=Decimal("1000"),
            shield=Decimal("110"),
        )

        state = battle.advance_mage_fireball_charge(mage)

        self.assertFalse(state["fireball_ready"])
        self.assertEqual(Decimal("10.00"), state["shield_gained"])
        self.assertEqual(Decimal("120"), mage.shield)

    def test_cheat_death_recovery_hp_uses_half_max_hp(self):
        battle = self._new_battle()
        reaper = SimpleNamespace(max_hp=Decimal("600"))

        revive_hp = battle.get_cheat_death_recovery_hp(reaper)

        self.assertEqual(Decimal("300.00"), revive_hp)


if __name__ == "__main__":
    unittest.main()

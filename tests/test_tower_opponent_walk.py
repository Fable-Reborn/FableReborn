"""Regression tests for the sequential opponent walk used by tower battles.

A gauntlet fight hung until timeout after the attacker killed the last enemy:
the defender's pet had healed its already-defeated owner back above 0 HP, and
because the battle had moved past that opponent it could never be faced again.
`process_turn` reported "all enemies defeated" while `is_battle_over` still saw
a living enemy, so the driving loop spun silently until `max_duration` expired.
"""

import asyncio
import unittest
from decimal import Decimal
from types import SimpleNamespace

from tests.pet_test_loader import load_tower_runtime_types


class TestTowerOpponentWalk(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.TowerBattle, cls.Team, cls.Combatant = load_tower_runtime_types()

    def _new_combatant(self, name, hp=100):
        return self.Combatant(
            user=name,
            hp=hp,
            max_hp=100,
            damage=10,
            armor=5,
            element="Fire",
            name=name,
        )

    def _new_battle(self, enemy_names):
        ctx = SimpleNamespace(
            bot=SimpleNamespace(
                cogs={"Battles": SimpleNamespace()},
                get_cog=lambda name: None,
            ),
            send=None,
        )
        player_team = self.Team("Player", [self._new_combatant("Attacker")])
        enemy_team = self.Team(
            "Enemy", [self._new_combatant(name) for name in enemy_names]
        )
        return self.TowerBattle(ctx, [player_team, enemy_team])

    def test_next_opponent_moves_forward_through_the_list(self):
        battle = self._new_battle(["Defender", "Defender Pet", "Echo"])
        battle.enemy_team.combatants[0].hp = Decimal("0")

        self.assertEqual(1, battle.find_next_opponent_index())

    def test_next_opponent_skips_enemies_that_are_already_down(self):
        battle = self._new_battle(["Defender", "Defender Pet", "Echo"])
        battle.enemy_team.combatants[0].hp = Decimal("0")
        battle.enemy_team.combatants[1].hp = Decimal("0")

        self.assertEqual(2, battle.find_next_opponent_index())

    def test_revived_earlier_enemy_is_faced_again_instead_of_stranded(self):
        battle = self._new_battle(["Defender", "Defender Pet", "Echo"])
        battle.current_opponent_index = 2
        battle.enemy_team.combatants[1].hp = Decimal("0")
        battle.enemy_team.combatants[2].hp = Decimal("0")
        # The defender was resurrected after the battle already walked past it.
        battle.enemy_team.combatants[0].hp = Decimal("25")

        self.assertEqual(0, battle.find_next_opponent_index())

    def test_no_next_opponent_when_every_enemy_is_down(self):
        battle = self._new_battle(["Defender", "Echo"])
        battle.current_opponent_index = 1
        for enemy in battle.enemy_team.combatants:
            enemy.hp = Decimal("0")

        # None here has to agree with is_battle_over(), otherwise the driving
        # loop spins with nothing left to resolve.
        self.assertIsNone(battle.find_next_opponent_index())
        self.assertTrue(asyncio.run(battle.is_battle_over()))

    def test_transition_walks_back_to_the_revived_enemy(self):
        battle = self._new_battle(["Defender", "Echo"])
        battle.current_opponent_index = 1
        battle.enemy_team.combatants[1].hp = Decimal("0")
        battle.enemy_team.combatants[0].hp = Decimal("25")
        battle.pending_enemy_transition = True

        async def noop_display():
            return None

        battle.update_display = noop_display

        self.assertTrue(asyncio.run(battle.handle_enemy_transition()))
        self.assertEqual(0, battle.current_opponent_index)
        self.assertFalse(battle.pending_enemy_transition)

    def test_transition_with_no_survivors_reports_the_battle_is_finished(self):
        battle = self._new_battle(["Defender", "Echo"])
        battle.current_opponent_index = 1
        for enemy in battle.enemy_team.combatants:
            enemy.hp = Decimal("0")
        battle.pending_enemy_transition = True

        self.assertFalse(asyncio.run(battle.handle_enemy_transition()))
        self.assertFalse(battle.pending_enemy_transition)
        self.assertEqual(1, battle.current_opponent_index)


class TestHealCannotResurrect(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _, _, cls.Combatant = load_tower_runtime_types()

    def _new_combatant(self, hp):
        return self.Combatant(
            user="Defender",
            hp=hp,
            max_hp=100,
            damage=10,
            armor=5,
            element="Fire",
            name="Defender",
        )

    def test_heal_leaves_a_defeated_combatant_defeated(self):
        defender = self._new_combatant(0)

        defender.heal(Decimal("50"))

        self.assertEqual(Decimal("0"), defender.hp)
        self.assertFalse(defender.is_alive())

    def test_heal_still_restores_a_living_combatant(self):
        defender = self._new_combatant(40)

        defender.heal(Decimal("35"))

        self.assertEqual(Decimal("75"), defender.hp)

    def test_heal_is_capped_at_max_hp(self):
        defender = self._new_combatant(90)

        defender.heal(Decimal("500"))

        self.assertEqual(Decimal("100"), defender.hp)


if __name__ == "__main__":
    unittest.main()

import unittest
from decimal import Decimal
from types import SimpleNamespace

from tests.pet_test_loader import (
    load_city_war_runtime_type,
    load_pet_runtime_types,
)


class DummyTeam:
    def __init__(self, combatants):
        self.combatants = list(combatants)

    def get_alive_combatants(self):
        return [combatant for combatant in self.combatants if combatant.is_alive()]


class TestCityWarBalance(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.CityWarBattle = load_city_war_runtime_type()
        cls.Combatant, cls.PetExtension = load_pet_runtime_types()

    def _new_ctx(self):
        return SimpleNamespace(
            bot=SimpleNamespace(
                config=SimpleNamespace(game=SimpleNamespace(primary_colour=0)),
                cogs={},
            ),
            send=None,
        )

    def _new_city_war_battle(self, attackers, defenders, **kwargs):
        return self.CityWarBattle(
            self._new_ctx(),
            [DummyTeam(attackers), DummyTeam(defenders)],
            city="Vopnafjor",
            attacking_guild_name="Attackers",
            defending_guild_name="Defenders",
            **kwargs,
        )

    def test_focus_fire_targets_support_pet_before_enemy_players(self):
        attacker = self.Combatant("Attacker", 1200, 1200, 250, 120, element="Fire")
        support_pet = self.Combatant(
            "Support Pet",
            900,
            900,
            120,
            80,
            element="Water",
            is_pet=True,
        )
        support_pet.skill_effects = {
            "healing_light": {"type": "team_heal_per_turn", "heal_percent": 0.07}
        }
        enemy_carry = self.Combatant("Carry", 1600, 1600, 320, 170, element="Electric")
        enemy_extra = self.Combatant("Extra", 1400, 1400, 140, 90, element="Nature")

        battle = self._new_city_war_battle([attacker], [enemy_carry, enemy_extra, support_pet])
        battle.guard_phase_started = True

        target = battle.select_target(attacker, battle.defender_team.get_alive_combatants())

        self.assertIs(target, support_pet)

    def test_focus_fire_secures_low_hp_kill_before_support_pet(self):
        attacker = self.Combatant("Attacker", 1200, 1200, 250, 120, element="Fire")
        support_pet = self.Combatant(
            "Support Pet",
            900,
            900,
            120,
            80,
            element="Water",
            is_pet=True,
        )
        support_pet.skill_effects = {
            "healing_light": {"type": "team_heal_per_turn", "heal_percent": 0.07}
        }
        enemy_carry = self.Combatant("Carry", 160, 1600, 320, 170, element="Electric")
        enemy_extra = self.Combatant("Extra", 1400, 1400, 140, 90, element="Nature")

        battle = self._new_city_war_battle([attacker], [enemy_carry, enemy_extra, support_pet])
        battle.guard_phase_started = True

        target = battle.select_target(attacker, battle.defender_team.get_alive_combatants())

        self.assertIs(target, enemy_carry)

    def test_city_war_pet_heal_multiplier_reduces_healing(self):
        pet_ext = self.PetExtension()
        owner = self.Combatant("Owner", 1800, 1800, 260, 120, element="Light")
        healer_pet = self.Combatant(
            "Healer Pet",
            1000,
            1000,
            120,
            80,
            element="Water",
            is_pet=True,
        )

        battle = self._new_city_war_battle([owner, healer_pet], [])
        heal_amount = pet_ext._scaled_heal(
            healer_pet,
            owner,
            Decimal("0.10"),
        )

        self.assertEqual(Decimal("60.00"), heal_amount.quantize(Decimal("0.01")))


if __name__ == "__main__":
    unittest.main()

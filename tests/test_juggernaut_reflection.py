"""Juggernaut's Retaliation stacks on top of the innate Tank plating.

The combatant factory folds the spec value into `damage_reflection`, and the
battle engines then took `max(gear_reflection, tank_plating)`. For the class
line that actually unlocks Juggernaut that meant the spec was worth nothing:
an 11% spec loses outright to a grade 7 Tank's innate 21%.
"""

import unittest
from decimal import Decimal
from types import SimpleNamespace

from tests.pet_test_loader import load_gauntlet_runtime_types


JUGGERNAUT_GRADE_7 = 4 + 1 * 7  # classes/specs.py: base 4, per_grade 1


class TestJuggernautReflection(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.GauntletBattle, cls.Team, cls.Combatant = load_gauntlet_runtime_types()

    def _battle(self):
        ctx = SimpleNamespace(
            bot=SimpleNamespace(
                cogs={"Battles": SimpleNamespace()},
                get_cog=lambda name: None,
            ),
            send=None,
        )
        return self.GauntletBattle(
            ctx, [self.Team("P", [self._tank()]), self.Team("E", [self._tank()])]
        )

    def _tank(self, tank_evolution=0, gear_reflection=0.0, juggernaut_value=None):
        combatant = self.Combatant(
            user="Tank",
            hp=1000,
            max_hp=1000,
            damage=10,
            armor=5,
            element="Fire",
            name="Tank",
        )
        combatant.tank_evolution = tank_evolution
        combatant.damage_reflection = Decimal(str(gear_reflection))
        if juggernaut_value is not None:
            combatant.spec_effects = {"reflect_pct": {"value": juggernaut_value}}
            # Mirror the factory, which merges the spec into damage_reflection
            combatant.damage_reflection = Decimal(str(gear_reflection)) + (
                Decimal(str(juggernaut_value)) / Decimal("100")
            )
        return combatant

    def test_retaliation_adds_on_top_of_max_tank_plating(self):
        battle = self._battle()
        plain = battle.resolve_damage_reflection(self._tank(tank_evolution=7))
        specced = battle.resolve_damage_reflection(
            self._tank(tank_evolution=7, juggernaut_value=JUGGERNAUT_GRADE_7)
        )

        self.assertEqual(Decimal("0.21"), plain)
        self.assertEqual(Decimal("0.32"), specced)

    def test_spec_is_never_a_downgrade_at_any_evolution(self):
        battle = self._battle()
        for evolution in range(0, 8):
            for gear in (0.0, 0.05, 0.10, 0.15):
                plain = battle.resolve_damage_reflection(
                    self._tank(tank_evolution=evolution, gear_reflection=gear)
                )
                specced = battle.resolve_damage_reflection(
                    self._tank(
                        tank_evolution=evolution,
                        gear_reflection=gear,
                        juggernaut_value=JUGGERNAUT_GRADE_7,
                    )
                )
                with self.subTest(evolution=evolution, gear=gear):
                    self.assertEqual(
                        Decimal(str(JUGGERNAUT_GRADE_7)) / Decimal("100"),
                        specced - plain,
                    )

    def test_gear_and_innate_plating_still_do_not_stack_with_each_other(self):
        battle = self._battle()

        # Gear beats a low evolution
        self.assertEqual(
            Decimal("0.15"),
            battle.resolve_damage_reflection(
                self._tank(tank_evolution=2, gear_reflection=0.15)
            ),
        )
        # Innate plating beats weak gear
        self.assertEqual(
            Decimal("0.21"),
            battle.resolve_damage_reflection(
                self._tank(tank_evolution=7, gear_reflection=0.05)
            ),
        )

    def test_pets_keep_their_plain_gear_reflection(self):
        battle = self._battle()
        pet = self._tank(tank_evolution=7, gear_reflection=0.08)
        pet.is_pet = True

        self.assertEqual(Decimal("0.08"), battle.resolve_damage_reflection(pet))

    def test_class_buffs_disabled_falls_back_to_raw_reflection(self):
        battle = self._battle()
        battle.config["class_buffs"] = False
        tank = self._tank(tank_evolution=7, juggernaut_value=JUGGERNAUT_GRADE_7)

        self.assertEqual(Decimal("0.11"), battle.resolve_damage_reflection(tank))


if __name__ == "__main__":
    unittest.main()

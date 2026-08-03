import unittest
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from cogs.battles.types.tower import TowerBattle
from cogs.rift import RIFT_DIFFICULTIES, generate_weekly_rift, scale_rift_rooms


class TestRiftTargetPressure(unittest.TestCase):
    def test_existing_battles_are_unchanged_without_rift_pressure(self):
        attacker = SimpleNamespace()
        target = SimpleNamespace(armor=Decimal("16538.5"), max_hp=Decimal("16335.7"))

        damage = TowerBattle.apply_rift_target_hp_pressure(
            attacker,
            target,
            Decimal("2959"),
        )

        self.assertEqual(Decimal("2959"), damage)

    def test_pressure_uses_the_selected_targets_own_hp_and_armor(self):
        pressure = Decimal("0.1295")
        attacker = SimpleNamespace(rift_target_hp_pressure=pressure)
        player = SimpleNamespace(armor=Decimal("1850.5"), max_hp=Decimal("8560"))
        pet = SimpleNamespace(armor=Decimal("16538.5"), max_hp=Decimal("16335.7"))

        player_damage = TowerBattle.apply_rift_target_hp_pressure(
            attacker,
            player,
            Decimal("2959"),
        )
        pet_damage = TowerBattle.apply_rift_target_hp_pressure(
            attacker,
            pet,
            Decimal("2959"),
        )

        self.assertEqual(player.armor + player.max_hp * pressure, player_damage)
        self.assertEqual(player.max_hp * pressure, player_damage - player.armor)
        self.assertEqual(pet.armor + pet.max_hp * pressure, pet_damage)
        self.assertEqual(pet.max_hp * pressure, pet_damage - pet.armor)

    def test_pressure_never_reduces_an_enemys_existing_attack(self):
        attacker = SimpleNamespace(rift_target_hp_pressure=Decimal("0.126"))
        target = SimpleNamespace(armor=Decimal("100"), max_hp=Decimal("1000"))

        damage = TowerBattle.apply_rift_target_hp_pressure(
            attacker,
            target,
            Decimal("1000"),
        )

        self.assertEqual(Decimal("1000"), damage)

    def test_only_ascendant_rooms_receive_target_relative_pressure(self):
        weekly_rift = generate_weekly_rift("2099-W42")
        stats = (2700.4, 8560, 1850.5, 13929)

        mythic = scale_rift_rooms(weekly_rift, *stats, "mythic")
        ascendant = scale_rift_rooms(weekly_rift, *stats, "ascendant")

        for mythic_room, ascendant_room in zip(
            mythic["rooms"],
            ascendant["rooms"],
        ):
            self.assertNotIn("target_hp_pressure", mythic_room)
            pressure = ascendant_room["target_hp_pressure"]
            self.assertGreaterEqual(pressure, 0.09 * 1.40)
            self.assertLessEqual(pressure, 0.18 * 1.65)

    def test_mythic_has_smart_targeting_without_escalating_pressure(self):
        self.assertNotIn("smart_targeting", RIFT_DIFFICULTIES["normal"])
        self.assertNotIn("smart_targeting", RIFT_DIFFICULTIES["heroic"])
        self.assertTrue(RIFT_DIFFICULTIES["mythic"]["smart_targeting"])
        self.assertNotIn(
            "attack_pressure_growth_range",
            RIFT_DIFFICULTIES["mythic"],
        )
        self.assertTrue(RIFT_DIFFICULTIES["ascendant"]["smart_targeting"])
        self.assertEqual(
            (0.03, 0.05),
            RIFT_DIFFICULTIES["ascendant"]["attack_pressure_growth_range"],
        )

    def test_smart_targeting_focuses_the_strongest_healer(self):
        player = SimpleNamespace(
            is_pet=False,
            max_hp=Decimal("8560"),
            hp=Decimal("8560"),
            damage=Decimal("2700"),
            lifesteal_percent=Decimal("5"),
            bard_evolution=0,
            spec_effects={},
        )
        pet = SimpleNamespace(
            is_pet=True,
            max_hp=Decimal("16335.7"),
            hp=Decimal("16335.7"),
            damage=Decimal("13929"),
            skill_effects={
                "healing_rain": {
                    "heal_percent": 0.05,
                    "type": "team_heal_per_turn",
                }
            },
        )
        enemy = SimpleNamespace(rift_smart_targeting=True)

        target = TowerBattle.select_rift_smart_target(enemy, [player, pet])

        self.assertIs(pet, target)

    def test_smart_targeting_compares_healing_when_both_can_heal(self):
        player = SimpleNamespace(
            is_pet=False,
            max_hp=Decimal("8560"),
            damage=Decimal("2700"),
            lifesteal_percent=Decimal("0"),
            bard_evolution=0,
            spec_effects={"party_round_heal_pct": {"value": 10}},
        )
        pet = SimpleNamespace(
            is_pet=True,
            max_hp=Decimal("16335.7"),
            damage=Decimal("13929"),
            skill_effects={
                "healing_rain": {
                    "heal_percent": 0.05,
                    "type": "team_heal_per_turn",
                }
            },
        )
        enemy = SimpleNamespace(rift_smart_targeting=True)

        target = TowerBattle.select_rift_smart_target(enemy, [player, pet])

        self.assertIs(player, target)

    def test_smart_targeting_falls_back_when_neither_target_can_heal(self):
        player = SimpleNamespace(
            is_pet=False,
            max_hp=Decimal("8560"),
            damage=Decimal("2700"),
            lifesteal_percent=0,
            bard_evolution=0,
            spec_effects={},
        )
        pet = SimpleNamespace(
            is_pet=True,
            max_hp=Decimal("16335.7"),
            damage=Decimal("13929"),
            skill_effects={},
        )
        enemy = SimpleNamespace(rift_smart_targeting=True)

        target = TowerBattle.select_rift_smart_target(enemy, [player, pet])

        self.assertIsNone(target)

    def test_ascendant_pressure_stacks_and_changes_future_damage(self):
        enemy = SimpleNamespace(
            rift_target_hp_pressure=Decimal("0.20"),
            rift_pressure_growth_range=(0.03, 0.05),
            rift_pressure_bonus=Decimal("0"),
            is_alive=lambda: True,
        )
        target = SimpleNamespace(armor=Decimal("100"), max_hp=Decimal("1000"))

        with patch(
            "cogs.battles.types.tower.random.uniform",
            side_effect=[0.03, 0.05],
        ):
            self.assertEqual(
                Decimal("0.03"),
                TowerBattle.advance_rift_attack_pressure(enemy),
            )
            self.assertEqual(
                Decimal("0.08"),
                TowerBattle.advance_rift_attack_pressure(enemy),
            )

        damage = TowerBattle.apply_rift_target_hp_pressure(
            enemy,
            target,
            Decimal("0"),
        )
        self.assertEqual(Decimal("316.0000"), damage)

        TowerBattle.reset_rift_attack_pressure(enemy)
        self.assertEqual(Decimal("0"), enemy.rift_pressure_bonus)


if __name__ == "__main__":
    unittest.main()

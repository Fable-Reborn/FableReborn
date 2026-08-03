import unittest
from decimal import Decimal
from types import SimpleNamespace

from cogs.battles.types.tower import TowerBattle
from cogs.rift import generate_weekly_rift, scale_rift_rooms


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


if __name__ == "__main__":
    unittest.main()

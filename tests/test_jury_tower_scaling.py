import importlib
import sys
import types
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_battle_runtime_types():
    for module_name, path in (
        ("cogs", ROOT / "cogs"),
        ("cogs.battles", ROOT / "cogs" / "battles"),
        ("cogs.battles.core", ROOT / "cogs" / "battles" / "core"),
        ("cogs.battles.types", ROOT / "cogs" / "battles" / "types"),
        ("cogs.battles.extensions", ROOT / "cogs" / "battles" / "extensions"),
        ("classes", ROOT / "classes"),
    ):
        if module_name in sys.modules:
            continue
        module = types.ModuleType(module_name)
        module.__path__ = [str(path)]  # type: ignore[attr-defined]
        sys.modules[module_name] = module

    factory_mod = importlib.import_module("cogs.battles.factory")
    combatant_mod = importlib.import_module("cogs.battles.core.combatant")
    return factory_mod.BattleFactory, combatant_mod.Combatant


class TestJuryTowerScaling(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.BattleFactory, cls.Combatant = load_battle_runtime_types()

    def setUp(self):
        self.factory = self.BattleFactory(None)

    def _combatant(self, *, hp: int, damage: int, armor: int, is_pet: bool = False):
        return self.Combatant(
            user="Pet" if is_pet else "Player",
            hp=hp,
            max_hp=hp,
            damage=damage,
            armor=armor,
            element="Fire",
            is_pet=is_pet,
            name="Pet" if is_pet else "Player",
        )

    def test_snapshot_without_pet_uses_player_stats(self):
        player = self._combatant(hp=4200, damage=1500, armor=1100)

        snapshot = self.factory._build_jury_scale_snapshot_from_combatants(player)

        self.assertEqual(
            {"attack_base": 1500, "hp_base": 4200, "defense_base": 1100},
            snapshot,
        )

    def test_snapshot_anchors_to_stronger_combatant_with_support_from_weaker(self):
        player = self._combatant(hp=1200, damage=300, armor=150)
        pet = self._combatant(hp=900, damage=600, armor=300, is_pet=True)

        snapshot = self.factory._build_jury_scale_snapshot_from_combatants(player, pet)

        self.assertEqual(
            {"attack_base": 690, "hp_base": 1470, "defense_base": 345},
            snapshot,
        )

    def test_snapshot_is_symmetric_when_player_or_pet_is_stronger(self):
        stronger_player = self._combatant(hp=1200, damage=600, armor=300)
        weaker_pet = self._combatant(hp=900, damage=300, armor=150, is_pet=True)
        weaker_player = self._combatant(hp=900, damage=300, armor=150)
        stronger_pet = self._combatant(hp=1200, damage=600, armor=300, is_pet=True)

        player_led_snapshot = self.factory._build_jury_scale_snapshot_from_combatants(
            stronger_player,
            weaker_pet,
        )
        pet_led_snapshot = self.factory._build_jury_scale_snapshot_from_combatants(
            weaker_player,
            stronger_pet,
        )

        self.assertEqual(player_led_snapshot, pet_led_snapshot)


if __name__ == "__main__":
    unittest.main()

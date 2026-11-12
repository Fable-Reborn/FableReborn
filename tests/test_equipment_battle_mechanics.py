"""Gear numbers through each battle mechanic.

Turn-based fights share resolve_pet_attack_outcome, so Sunder and Breakthrough
apply there. World raids, adventures, $battle, and brawls keep their own math.
"""

from __future__ import annotations

import random
import unittest
from decimal import Decimal
from pathlib import Path

from classes.equipment.economy import modifier_adjustments, offensive_properties
from classes.equipment.offense import resolve_effective_armor
from classes.equipment.stats import apply_component_bonus, contribution
from tests.test_element_procs import ElementProcTestCase

ROOT = Path(__file__).resolve().parents[1]
TYPES = ROOT / "cogs" / "battles" / "types"

RESOLVER_BATTLES = {
    "pve.py": "resolve_pet_attack_outcome(",
    "raid.py": "resolve_pet_attack_outcome(",
    "tower.py": "resolve_pet_attack_outcome(",
    "team_battle.py": "resolve_pet_attack_outcome(",
    "dragon.py": "resolve_pet_attack_outcome(",
    "couples_tower.py": "resolve_pet_attack_outcome(",
}


class GearBattleMechanicsTests(ElementProcTestCase):
    def attack(self, battle, attacker, defender, raw=Decimal("5000")):
        return battle.resolve_pet_attack_outcome(
            attacker, defender, raw, damage_variance=0, minimum_damage=Decimal("10")
        )

    def test_turn_based_modes_share_the_armor_resolver(self):
        for filename, needle in RESOLVER_BATTLES.items():
            source = (TYPES / filename).read_text(encoding="utf-8")
            self.assertIn(needle, source, filename)
        self.assertIn("RaidBattle.process_turn", (TYPES / "city_war.py").read_text(encoding="utf-8"))
        self.assertIn("class OmnithroneSealBattle(PvEBattle)", (TYPES / "omnithrone.py").read_text(encoding="utf-8"))
        self.assertIn("class GauntletBattle(TeamBattle)", (TYPES / "gauntlet.py").read_text(encoding="utf-8"))
        self.assertIn("class FreeForAllBattle(TeamBattle)", (TYPES / "ffa.py").read_text(encoding="utf-8"))

    def test_sunder_lowers_armor_before_the_hit_and_the_reflection_base(self):
        attacker = self.player(1, damage=5000, armor=100, gear_penetration=Decimal("0.55"))
        defender = self.player(2, damage=1000, armor=2000, damage_reflection=0.28)
        plain = self.attack(self.battle([], []), self.player(3, damage=5000), defender)
        defender.hp = defender.max_hp
        sundered = self.attack(self.battle([], []), attacker, defender)
        self.assertGreater(sundered.final_damage, plain.final_damage)
        self.assertLess(sundered.blocked_damage, plain.blocked_damage)
        self.assertEqual(Decimal("3000"), plain.final_damage)
        self.assertEqual(Decimal("4100"), sundered.final_damage)
        self.assertEqual(Decimal("900"), sundered.blocked_damage)
        reflected = sundered.blocked_damage * Decimal("0.28")
        self.assertEqual(Decimal("252.00"), reflected.quantize(Decimal("0.01")))

    def test_breakthrough_adds_one_extra_ignore_and_fireball_skips_it(self):
        attacker = self.player(
            1,
            damage=5000,
            gear_penetration=Decimal("0.55"),
            gear_breakthrough_chance=Decimal("0.10"),
            gear_breakthrough_bypass=Decimal("0.15"),
        )
        defender = self.player(2, armor=2000)
        battle = self.battle([], [])
        original = random.random
        random.random = lambda: 0.0
        try:
            outcome = self.attack(battle, attacker, defender)
        finally:
            random.random = original
        self.assertTrue(outcome.metadata["breakthrough"])
        self.assertEqual(Decimal("4400"), outcome.final_damage)
        fireball = battle.calculate_mage_fireball_damage(
            attacker, defender, damage_variance=0, apply_armor=False
        )
        self.assertEqual(Decimal("5000"), fireball)

    def test_a_second_sunder_does_not_stack_and_vitality_does(self):
        one = offensive_properties(["sunder", "breakthrough"])
        two = offensive_properties(["sunder", "sunder", "breakthrough", "breakthrough"])
        self.assertEqual(one, two)
        self.assertEqual(Decimal("0.55"), one[0])
        chest = contribution("legendary", "guardian", 100, 0, "chest")[1]
        _pct, _armor, health = modifier_adjustments(chest, ["vitality"])
        self.assertEqual(75, health)
        self.assertEqual(150, health + health)

    def test_modes_that_keep_their_own_math_do_not_call_the_resolver(self):
        pvp = (TYPES / "pvp.py").read_text(encoding="utf-8")
        brawl = (TYPES / "brawl.py").read_text(encoding="utf-8")
        adventure = (ROOT / "cogs" / "adventure" / "__init__.py").read_text(encoding="utf-8")
        raid = (ROOT / "cogs" / "raid" / "__init__.py").read_text(encoding="utf-8")
        self.assertNotIn("resolve_pet_attack_outcome(", pvp)
        self.assertNotIn("resolve_pet_attack_outcome(", brawl)
        self.assertNotIn("include_equipment=True", adventure)
        self.assertIn("def getfinaldmg(damage, defense):", raid)
        self.assertNotIn("resolve_effective_armor", raid)
        naked_weapon, naked_armor = apply_component_bonus(550, 320, 0, 0, 0, 0)
        geared_weapon, geared_armor = apply_component_bonus(
            550, 320, 0, 0, Decimal("0.16"), Decimal("4")
        )
        multiplier = Decimal("6.4")
        defense_multiplier = Decimal("3.9")
        self.assertLess(naked_weapon * multiplier, geared_weapon * multiplier)
        boss_hit = max(0.0, 1500 - float(geared_armor * defense_multiplier))
        self.assertLess(boss_hit, 1500)


if __name__ == "__main__":
    unittest.main()

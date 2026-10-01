"""Opt-in element procs: starforge gating, consent, and the shared damage resolver."""

import importlib
import unittest
from decimal import Decimal
from types import SimpleNamespace

from tests.pet_test_loader import load_tower_runtime_types


class ElementProcTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _tower, cls.Team, cls.Combatant = load_tower_runtime_types()
        cls.Battle = importlib.import_module("cogs.battles.core.battle").Battle
        cls.procs = importlib.import_module("cogs.battles.extensions.element_procs")
        cls.ElementExtension = importlib.import_module("cogs.battles.extensions.elements").ElementExtension

    def player(self, user_id, element="Light", stars=10, opted_in=True, **kwargs):
        kwargs.setdefault("hp", 1000)
        kwargs.setdefault("damage", 200)
        kwargs.setdefault("armor", 50)
        return self.Combatant(
            user=SimpleNamespace(id=user_id, display_name=f"P{user_id}"),
            max_hp=kwargs["hp"],
            element=element,
            name=f"P{user_id}",
            element_procs_enabled=opted_in,
            element_proc_stars={element: stars} if stars else {},
            **kwargs,
        )

    def monster(self, element="Corrupted", **kwargs):
        kwargs.setdefault("hp", 1000)
        kwargs.setdefault("damage", 100)
        kwargs.setdefault("armor", 50)
        return self.Combatant(user="Imp", max_hp=kwargs["hp"], element=element, name="Imp", **kwargs)

    def battle(self, team_a, team_b, rng=0.0, **config):
        class DummyBattle(self.Battle):
            async def start_battle(self):
                return True

            async def process_turn(self):
                return True

            async def end_battle(self):
                return None

            async def update_display(self):
                return None

        battles_cog = SimpleNamespace(element_ext=self.ElementExtension())
        ctx = SimpleNamespace(bot=SimpleNamespace(cogs={"Battles": battles_cog}), send=None)
        battle = DummyBattle(
            ctx,
            teams=[self.Team("A", list(team_a)), self.Team("B", list(team_b))],
            class_buffs=False,
            **config,
        )
        rolls = rng if callable(rng) else (lambda: rng)
        battle.element_procs = self.procs.ElementProcExtension(rng=rolls)
        return battle

    def attack(self, battle, attacker, defender, raw=Decimal("200")):
        return battle.resolve_pet_attack_outcome(attacker, defender, raw, damage_variance=0)


class TestChances(ElementProcTestCase):
    def test_common_scales_from_one_to_ten_stars(self):
        ext = self.procs.ElementProcExtension
        self.assertEqual(Decimal("0"), ext.common_chance(0))
        self.assertEqual(Decimal("0.02"), ext.common_chance(1))
        self.assertEqual(Decimal("0.03"), ext.common_chance(10))

    def test_mythics_unlock_at_five_and_power_word_only_at_ten(self):
        ext = self.procs.ElementProcExtension
        self.assertEqual(Decimal("0"), ext.mythic_chance("Fire", 4))
        self.assertEqual(Decimal("0.0005"), ext.mythic_chance("Fire", 5))
        self.assertEqual(Decimal("0.001"), ext.mythic_chance("Fire", 10))
        self.assertEqual(Decimal("0"), ext.mythic_chance("Light", 9))
        self.assertEqual(Decimal("0.0001"), ext.mythic_chance("Light", 10))
        self.assertLess(ext.mythic_chance("Light", 10), ext.mythic_chance("Dark", 10))

    def test_weapon_stars_ignore_shields_and_keep_the_best_weapon(self):
        stars = self.procs.ElementProcExtension.weapon_stars_by_element(
            [
                {"type": "Sword", "element": "fire", "stars": 3},
                {"type": "Axe", "element": "Fire", "stars": 7},
                {"type": "Shield", "element": "Water", "stars": 10},
                {"type": "Bow", "element": None, "stars": 9},
            ]
        )
        self.assertEqual({"Fire": 7}, stars)

    def test_every_element_has_both_procs(self):
        ext = self.procs.ElementProcExtension()
        for element in self.procs.PROC_NAMES:
            for tier in (self.procs.COMMON, self.procs.MYTHIC):
                self.assertTrue(callable(getattr(ext, f"_{tier}_{element.lower()}")))


class TestEligibility(ElementProcTestCase):
    def roll(self, attacker, defender, battle=None, attack="Light", defense="Corrupted"):
        battle = battle or self.battle([attacker], [defender])
        return battle.element_procs.roll(battle, attacker, defender, attack, defense)

    def test_needs_elemental_advantage(self):
        hero, imp = self.player(1), self.monster()
        self.assertEqual(("Light", "mythic"), self.roll(hero, imp))
        self.assertIsNone(self.roll(hero, imp, defense="Dark"))
        self.assertIsNone(self.roll(hero, imp, defense="Unknown"))

    def test_needs_opt_in_and_stars(self):
        self.assertIsNone(self.roll(self.player(1, opted_in=False), self.monster()))
        self.assertIsNone(self.roll(self.player(1, stars=0), self.monster()))

    def test_pets_never_proc(self):
        pet = self.player(1, is_pet=True)
        self.assertIsNone(self.roll(pet, self.monster()))

    def test_pvp_needs_both_players(self):
        hero = self.player(1)
        self.assertIsNone(self.roll(hero, self.player(2, element="Corrupted", opted_in=False)))
        self.assertIsNotNone(self.roll(hero, self.player(2, element="Corrupted")))

    def test_opted_out_owner_protects_their_pet(self):
        hero = self.player(1)
        owner = self.player(2, element="Corrupted", opted_in=False)
        pet = self.Combatant(
            user=owner.user, hp=500, max_hp=500, damage=50, armor=10,
            element="Corrupted", name="Pet", is_pet=True, owner=owner.user,
        )
        battle = self.battle([hero], [owner, pet])
        self.assertIsNone(self.roll(hero, pet, battle=battle))
        owner.element_procs_enabled = True
        self.assertIsNotNone(self.roll(hero, pet, battle=battle))

    def test_no_procs_on_teammates(self):
        hero, ally = self.player(1), self.player(2, element="Corrupted")
        battle = self.battle([hero, ally], [self.monster()])
        self.assertIsNone(self.roll(hero, ally, battle=battle))

    def test_admin_switch_and_element_effects_gate_procs(self):
        hero, imp = self.player(1), self.monster()
        self.assertIsNone(self.roll(hero, imp, battle=self.battle([hero], [imp], element_procs=False)))
        self.assertIsNone(self.roll(hero, imp, battle=self.battle([hero], [imp], element_effects=False)))

    def test_bosses_ignore_mythics_but_take_commons(self):
        hero, boss = self.player(1), self.monster(is_boss=True)
        self.assertEqual(("Light", "common"), self.roll(hero, boss))


class TestResolverIntegration(ElementProcTestCase):
    def test_power_word_die_goes_through_the_normal_death_path(self):
        hero, imp = self.player(1), self.monster()
        battle = self.battle([hero], [imp])
        outcome = self.attack(battle, hero, imp)
        self.assertGreaterEqual(outcome.final_damage, self.procs.POWER_WORD_DAMAGE)
        self.assertTrue(any("POWER WORD: DIE" in m for m in outcome.skill_messages))
        imp.take_damage(outcome.final_damage)
        self.assertFalse(imp.is_alive())

    def test_no_roll_means_plain_type_chart_damage(self):
        hero, imp = self.player(1), self.monster()
        battle = self.battle([hero], [imp], rng=0.99)
        outcome = self.attack(battle, hero, imp)
        self.assertEqual(Decimal("250"), outcome.final_damage)  # 200 * 1.5 - 50 armor
        self.assertEqual([], outcome.skill_messages)

    def test_gust_dodge_zeroes_the_hit_and_blocks_reflection(self):
        hero = self.player(1, element="Wind", stars=1)
        imp = self.monster(element="Earth")
        battle = self.battle([hero], [imp])
        self.attack(battle, hero, imp)  # Gust: common roll succeeds at rng 0, no mythic below ★5
        self.assertEqual(1, hero.element_proc_dodge)
        outcome = self.attack(battle, imp, hero)
        self.assertEqual(Decimal("0"), outcome.final_damage)
        self.assertEqual(Decimal("0"), outcome.blocked_damage)
        self.assertTrue(outcome.metadata["ignore_reflection_this_hit"])
        self.assertEqual(0, hero.element_proc_dodge)

    def test_hex_strips_the_targets_element_for_two_attacks(self):
        hero = self.player(1, element="Corrupted", stars=1)
        imp = self.monster(element="Dark")
        battle = self.battle([hero], [imp])
        self.attack(battle, hero, imp)
        self.assertEqual(2, imp.element_proc_hex)
        self.assertEqual("Unknown", battle.resolve_attack_element(imp))
        self.assertEqual("Unknown", battle.resolve_attack_element(imp))
        self.assertEqual("Dark", battle.resolve_attack_element(imp))

    def test_eclipse_locks_turns_and_falls_back_inside_the_resolver(self):
        hero = self.player(1, element="Dark", stars=10)
        imp = self.monster(element="Light")
        battle = self.battle([hero], [imp])
        self.attack(battle, hero, imp)
        self.assertEqual(2, imp.element_proc_eclipse)
        self.assertIn("Eclipse", battle.consume_pet_skill_action_lock(imp))
        outcome = self.attack(battle, imp, hero)  # mode without a lock hook
        self.assertEqual(Decimal("0"), outcome.final_damage)
        self.assertEqual(0, imp.element_proc_eclipse)

    def test_erosion_and_drown_reduce_armor_for_everyone(self):
        ext = self.procs.ElementProcExtension
        imp = self.monster(armor=100)
        imp.element_proc_erosion = 5
        self.assertEqual(Decimal("85"), ext.effective_armor(imp))
        imp.element_proc_drowned = True
        self.assertEqual(Decimal("0"), ext.effective_armor(imp))

    def test_ignite_burns_on_the_next_two_hits(self):
        hero = self.player(1, element="Fire", stars=1)
        imp = self.monster(element="Nature")
        battle = self.battle([hero], [imp])
        self.attack(battle, hero, imp)
        self.assertEqual(Decimal("15"), imp.element_proc_burn_tick)  # 1.5% of 1000 max HP
        battle.element_procs = self.procs.ElementProcExtension(rng=lambda: 0.99)
        first = self.attack(battle, hero, imp)
        self.assertEqual(Decimal("265"), first.final_damage)  # 250 + 15 burn
        self.attack(battle, hero, imp)
        self.assertEqual(Decimal("250"), self.attack(battle, hero, imp).final_damage)

    def test_dread_weakens_the_targets_next_attack(self):
        hero = self.player(1, element="Dark", stars=1)
        imp = self.monster(element="Light", damage=200)
        battle = self.battle([hero], [imp])
        self.attack(battle, hero, imp)
        self.assertEqual(1, imp.element_proc_dread)
        outcome = self.attack(battle, imp, hero, raw=Decimal("200"))
        self.assertEqual(Decimal("55"), outcome.final_damage)  # 200 * 0.75 * 0.7 (weak) - 50 armor
        self.assertEqual(0, imp.element_proc_dread)

    def test_cataclysm_splashes_every_other_enemy(self):
        hero = self.player(1, element="Earth", stars=10)
        target = self.monster(element="Electric")
        bystander = self.monster(element="Fire")
        battle = self.battle([hero], [target, bystander])
        outcome = self.attack(battle, hero, target)
        self.assertEqual(Decimal("500"), outcome.final_damage)  # (300 - 50) doubled
        self.assertEqual(Decimal("500"), bystander.hp)

    def test_couples_style_paths_use_the_stashed_element(self):
        hero, imp = self.player(1), self.monster()
        battle = self.battle([hero], [imp])
        element = battle.resolve_attack_element(hero)
        self.assertEqual("Light", element)
        outcome = battle.resolve_pet_attack_outcome(
            hero, imp, Decimal("300"), apply_element_mod=False, damage_variance=0
        )
        self.assertGreaterEqual(outcome.final_damage, self.procs.POWER_WORD_DAMAGE)
        self.assertFalse(hasattr(hero, "element_proc_last_attack"))

    def test_dual_element_rotation_advances_once_per_attack(self):
        hero = self.player(1, element="Light", stars=0, dual_attack_elements=["Light", "Fire"])
        imp = self.monster()
        battle = self.battle([hero], [imp], rng=0.99)
        self.attack(battle, hero, imp)
        self.assertEqual(1, hero._dual_attack_index)
        self.attack(battle, hero, imp)
        self.assertEqual(2, hero._dual_attack_index)


if __name__ == "__main__":
    unittest.main()

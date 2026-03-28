import random
import unittest
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from tools.pet_skill_audit_lib import build_skill_runtime_map, iter_skill_records, load_skill_trees
from tests.pet_test_loader import load_pet_runtime_types


class TestPetSkillContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.Combatant, cls.PetExtension = load_pet_runtime_types()

    def setUp(self):
        random.seed(1337)
        self.pet_ext = self.PetExtension()

    def _new_user(self, user_id: int, name: str):
        return SimpleNamespace(id=user_id, display_name=name)

    def test_skill_tree_entries_have_runtime_mapping_or_non_battle_exception(self):
        records = iter_skill_records(load_skill_trees())
        runtime_map = build_skill_runtime_map(records)

        missing = []
        for record in records:
            effect_keys = runtime_map[(record.element, record.skill_name)]["effect_keys"]
            if not effect_keys and record.skill_name.lower() != "battery life":
                missing.append(f"{record.element}:{record.skill_name}")

        self.assertEqual([], missing, f"Missing runtime mappings: {missing}")

    def test_shadow_strike_single_hit_split_behavior(self):
        attacker_user = self._new_user(1, "Attacker")
        attacker = self.Combatant(
            user=attacker_user,
            hp=3000,
            max_hp=3000,
            damage=500,
            armor=100,
            element="Dark",
            is_pet=True,
            name="Shadow Pet",
        )
        target = self.Combatant(
            user=self._new_user(2, "Defender"),
            hp=5000,
            max_hp=5000,
            damage=300,
            armor=200,
            element="Light",
            is_pet=False,
            name="Target",
        )
        target.shield = Decimal("300")

        self.pet_ext.apply_skill_effects(attacker, ["Shadow Strike"])

        with patch("cogs.battles.extensions.pets.random.randint", return_value=1):
            modified_damage, messages = self.pet_ext.process_skill_effects_on_attack(
                attacker, target, Decimal("1000")
            )

        self.assertEqual(Decimal("500"), modified_damage)
        self.assertTrue(hasattr(target, "partial_true_damage"))
        self.assertEqual(Decimal("500"), Decimal(str(target.partial_true_damage)))
        self.assertTrue(hasattr(target, "pending_true_damage_bypass_shield"))
        self.assertEqual(Decimal("500"), Decimal(str(target.pending_true_damage_bypass_shield)))
        self.assertTrue(any("Shadow Strike" in msg for msg in messages))

        # Mirror canonical resolver math for this deterministic case.
        normal_after_armor = max(modified_damage - target.armor, Decimal("10"))
        final_damage = normal_after_armor + Decimal(str(target.partial_true_damage))
        self.assertEqual(Decimal("800"), final_damage)

        hp_before = target.hp
        target.take_damage(final_damage)

        # Single hit application: 500 bypasses shield, 300 is absorbed by shield.
        self.assertEqual(hp_before - Decimal("500"), target.hp)
        self.assertEqual(Decimal("0"), target.shield)
        self.assertFalse(hasattr(target, "pending_true_damage_bypass_shield"))

    def test_dark_embrace_only_below_half_owner_hp(self):
        owner_user = self._new_user(10, "Owner")
        owner = self.Combatant(
            user=owner_user,
            hp=2000,
            max_hp=2000,
            damage=400,
            armor=150,
            element="Dark",
            is_pet=False,
            name="Owner",
        )
        pet = self.Combatant(
            user=self._new_user(11, "Pet"),
            hp=1500,
            max_hp=1500,
            damage=300,
            armor=120,
            element="Dark",
            is_pet=True,
            owner=owner_user,
            name="Dark Pet",
        )
        enemy = self.Combatant(
            user=self._new_user(12, "Enemy"),
            hp=2000,
            max_hp=2000,
            damage=250,
            armor=100,
            element="Light",
            is_pet=False,
            name="Enemy",
        )

        team = SimpleNamespace(combatants=[owner, pet])
        pet.team = team

        self.pet_ext.apply_skill_effects(pet, ["Dark Embrace"])

        owner.hp = Decimal("1200")  # 60%
        damage_high_owner, msgs_high_owner = self.pet_ext.process_skill_effects_on_attack(
            pet, enemy, Decimal("100")
        )
        self.assertEqual(Decimal("100"), damage_high_owner)
        self.assertFalse(any("desperation" in msg.lower() for msg in msgs_high_owner))

        owner.hp = Decimal("900")  # 45%
        damage_low_owner, msgs_low_owner = self.pet_ext.process_skill_effects_on_attack(
            pet, enemy, Decimal("100")
        )
        self.assertEqual(Decimal("150"), damage_low_owner)
        self.assertTrue(any("desperation" in msg.lower() for msg in msgs_low_owner))

    def test_lord_of_shadows_uses_owner_luck_and_refreshes_without_stacking(self):
        owner_user = self._new_user(20, "Owner")
        owner = self.Combatant(
            user=owner_user,
            hp=2400,
            max_hp=2400,
            damage=350,
            armor=120,
            element="Dark",
            is_pet=False,
            name="Owner",
            luck=77,
        )
        pet = self.Combatant(
            user=self._new_user(21, "Shadow Lord"),
            hp=2000,
            max_hp=2000,
            damage=300,
            armor=100,
            element="Dark",
            is_pet=True,
            owner=owner_user,
            name="Shadow Lord",
        )
        ally = self.Combatant(
            user=self._new_user(22, "Ally"),
            hp=1800,
            max_hp=1800,
            damage=250,
            armor=80,
            element="Dark",
            is_pet=False,
            name="Ally",
            luck=50,
        )
        enemy = self.Combatant(
            user=self._new_user(23, "Enemy"),
            hp=2200,
            max_hp=2200,
            damage=240,
            armor=90,
            element="Light",
            is_pet=False,
            name="Enemy",
            luck=50,
        )
        enemy_ally = self.Combatant(
            user=self._new_user(24, "Enemy Ally"),
            hp=2100,
            max_hp=2100,
            damage=230,
            armor=85,
            element="Light",
            is_pet=False,
            name="Enemy Ally",
            luck=50,
        )

        friendly_team = SimpleNamespace(combatants=[owner, pet, ally])
        enemy_team = SimpleNamespace(combatants=[enemy, enemy_ally])
        owner.team = friendly_team
        pet.team = friendly_team
        ally.team = friendly_team
        enemy.team = enemy_team
        enemy_ally.team = enemy_team

        self.pet_ext.apply_skill_effects(pet, ["Lord of Shadows"])
        pet.hp = Decimal("1600")

        with patch("cogs.battles.extensions.pets.random.random", return_value=0.0):
            damage_1, messages_1 = self.pet_ext.process_skill_effects_on_attack(
                pet, enemy, Decimal("250")
            )

        self.assertEqual(Decimal("250"), damage_1)
        self.assertTrue(any("Two skeleton warriors" in msg for msg in messages_1))
        first_queue = getattr(pet, "summon_skeleton_queue", [])
        self.assertEqual(2, len(first_queue))
        self.assertEqual(Decimal("77"), Decimal(str(first_queue[0]["luck"])))
        self.assertEqual(Decimal("1500.00"), Decimal(str(first_queue[0]["hp"])))
        self.assertEqual(Decimal("270.00"), Decimal(str(first_queue[0]["damage"])))
        self.assertEqual(Decimal("40.00"), Decimal(str(first_queue[0]["armor"])))

        self.assertEqual(Decimal("287.50"), ally.damage)
        self.assertEqual(Decimal("88.00"), ally.armor)
        self.assertEqual(Decimal("55.00"), ally.luck)
        self.assertEqual(3, getattr(ally, "lord_of_shadows_duration", 0))
        self.assertEqual(Decimal("204.00"), enemy.damage)
        self.assertEqual(Decimal("45.00"), enemy.luck)
        self.assertEqual(3, getattr(enemy, "lord_of_shadows_fear_duration", 0))

        for skeleton_data in list(first_queue):
            skeleton = self.Combatant(
                user=f"Skeleton Warrior #{skeleton_data['serial']}",
                hp=skeleton_data["hp"],
                max_hp=skeleton_data["hp"],
                damage=skeleton_data["damage"],
                armor=skeleton_data["armor"],
                element=skeleton_data["element"],
                luck=skeleton_data["luck"],
                is_pet=True,
                name=f"Skeleton Warrior #{skeleton_data['serial']}",
            )
            skeleton.is_summoned = True
            skeleton.summoner = pet
            friendly_team.combatants.append(skeleton)
        delattr(pet, "summon_skeleton_queue")

        with patch("cogs.battles.extensions.pets.random.random", return_value=0.0):
            damage_2, messages_2 = self.pet_ext.process_skill_effects_on_attack(
                pet, enemy, Decimal("250")
            )

        self.assertEqual(Decimal("250"), damage_2)
        self.assertTrue(any("A skeleton warrior rises" in msg for msg in messages_2))
        second_queue = getattr(pet, "summon_skeleton_queue", [])
        self.assertEqual(1, len(second_queue))
        self.assertEqual(owner.luck, second_queue[0]["luck"])
        self.assertEqual(Decimal("287.50"), ally.damage)
        self.assertEqual(Decimal("88.00"), ally.armor)
        self.assertEqual(Decimal("55.00"), ally.luck)
        self.assertEqual(3, getattr(ally, "lord_of_shadows_duration", 0))
        self.assertEqual(Decimal("204.00"), enemy.damage)
        self.assertEqual(Decimal("45.00"), enemy.luck)
        self.assertEqual(3, getattr(enemy, "lord_of_shadows_fear_duration", 0))

    def test_corrupted_balance_chances(self):
        pet = self.Combatant(
            user=self._new_user(30, "Corruptor"),
            hp=1800,
            max_hp=1800,
            damage=420,
            armor=140,
            element="Corrupted",
            is_pet=True,
            name="Corruptor",
        )

        self.pet_ext.apply_skill_effects(
            pet,
            ["Chaos Storm", "Chaos Control", "Corruption Wave", "Reality Distortion", "Reality Warp"],
        )

        self.assertEqual(15, pet.skill_effects["chaos_storm"]["chance"])
        self.assertEqual(2, pet.skill_effects["chaos_storm"]["cooldown"])
        self.assertEqual(30, pet.skill_effects["chaos_storm"]["effect_chance"])
        self.assertEqual(12, pet.skill_effects["chaos_control"]["chance"])
        self.assertEqual(2, pet.skill_effects["chaos_control"]["cooldown"])
        self.assertEqual(20, pet.skill_effects["corruption_wave"]["chance"])
        self.assertEqual(2, pet.skill_effects["corruption_wave"]["cooldown"])
        self.assertEqual(20, pet.skill_effects["reality_distortion"]["chance"])
        self.assertEqual(2, pet.skill_effects["reality_distortion"]["cooldown"])
        self.assertEqual(0.10, pet.skill_effects["reality_warp"]["chance"])
        self.assertEqual(3, pet.skill_effects["reality_warp"]["cooldown"])

    def test_corrupted_skill_cooldowns_apply(self):
        pet = self.Combatant(
            user=self._new_user(40, "Cooldown Pet"),
            hp=1800,
            max_hp=1800,
            damage=300,
            armor=120,
            element="Corrupted",
            is_pet=True,
            name="Cooldown Pet",
        )
        target = self.Combatant(
            user=self._new_user(41, "Target"),
            hp=2500,
            max_hp=2500,
            damage=220,
            armor=110,
            element="Fire",
            is_pet=False,
            name="Target",
        )
        target.team = SimpleNamespace(combatants=[target])
        pet.battle = object()

        self.pet_ext.apply_skill_effects(pet, ["Chaos Control", "Reality Warp"])

        # First attack: force Chaos Control proc and 1.4x branch.
        with patch("cogs.battles.extensions.pets.random.randint", side_effect=[1, 3]):
            dmg1, msgs1 = self.pet_ext.process_skill_effects_on_attack(pet, target, Decimal("100"))
        self.assertEqual(Decimal("140"), dmg1)
        self.assertTrue(any("Chaos Control" in msg for msg in msgs1))
        self.assertEqual(2, getattr(pet, "chaos_control_cooldown", 0))

        # Immediate second attack: even with proc roll, cooldown prevents activation.
        with patch("cogs.battles.extensions.pets.random.randint", return_value=1):
            dmg2, msgs2 = self.pet_ext.process_skill_effects_on_attack(pet, target, Decimal("100"))
        self.assertEqual(Decimal("100"), dmg2)
        self.assertFalse(any("Chaos Control" in msg for msg in msgs2))

        # Tick two turns, then Chaos Control can trigger again.
        self.pet_ext.process_skill_effects_per_turn(pet)
        self.pet_ext.process_skill_effects_per_turn(pet)
        with patch("cogs.battles.extensions.pets.random.randint", side_effect=[1, 3]):
            dmg3, msgs3 = self.pet_ext.process_skill_effects_on_attack(pet, target, Decimal("100"))
        self.assertEqual(Decimal("140"), dmg3)
        self.assertTrue(any("Chaos Control" in msg for msg in msgs3))

        # Reality Warp also has cooldown; force one proc then ensure immediate re-proc is blocked.
        with patch("cogs.battles.extensions.pets.random.random", return_value=0.0):
            turn_msgs_1 = self.pet_ext.process_skill_effects_per_turn(pet)
        self.assertTrue(any("Reality Warp" in msg for msg in turn_msgs_1))
        self.assertEqual(3, getattr(pet, "reality_warp_cooldown", 0))

        with patch("cogs.battles.extensions.pets.random.random", return_value=0.0):
            turn_msgs_2 = self.pet_ext.process_skill_effects_per_turn(pet)
        self.assertFalse(any("Reality Warp" in msg for msg in turn_msgs_2))


if __name__ == "__main__":
    unittest.main()

import unittest

from tools.pet_skill_audit_lib import MODE_FILES, evaluate_mode_resolver_parity


class TestPetSkillModeParity(unittest.TestCase):
    def test_all_modes_route_pet_damage_through_shared_resolver(self):
        parity = evaluate_mode_resolver_parity()
        missing = [mode for mode, data in parity.items() if data["resolver_calls"] < 1]
        self.assertEqual([], missing, f"Missing resolver wiring: {missing}")

    def test_no_mode_uses_legacy_special_damage_block(self):
        parity = evaluate_mode_resolver_parity()
        legacy = [mode for mode, data in parity.items() if data["contains_legacy_special_damage_block"]]
        self.assertEqual([], legacy, f"Legacy pet damage block still present: {legacy}")

    def test_turn_priority_support_present_in_all_modes(self):
        parity = evaluate_mode_resolver_parity()
        missing = [mode for mode, data in parity.items() if not data["has_turn_priority_sort"]]
        self.assertEqual([], missing, f"Missing turn-priority sorting: {missing}")

    def test_couples_tower_uses_resolver_in_all_duplicated_sections(self):
        parity = evaluate_mode_resolver_parity()
        # Couples tower has many repeated attack sections; enforce multiple callsites.
        self.assertGreaterEqual(parity["couples_tower"]["resolver_calls"], 10)

    def test_all_expected_mode_files_exist(self):
        missing_paths = [name for name, path in MODE_FILES.items() if not path.exists()]
        self.assertEqual([], missing_paths, f"Missing mode source files: {missing_paths}")


if __name__ == "__main__":
    unittest.main()

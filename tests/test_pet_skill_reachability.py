import unittest

from tools.pet_skill_audit import build_audit
from tools.pet_skill_audit_lib import (
    build_skill_runtime_map,
    collect_set_only_attrs,
    extract_effect_contexts,
    iter_skill_records,
    load_skill_trees,
)


class TestPetSkillReachability(unittest.TestCase):
    def test_every_skill_has_runtime_path(self):
        records = iter_skill_records(load_skill_trees())
        runtime_map = build_skill_runtime_map(records)

        missing = []
        for record in records:
            effect_keys = runtime_map[(record.element, record.skill_name)]["effect_keys"]
            if not effect_keys and record.skill_name.lower() != "battery life":
                missing.append(f"{record.element}:{record.skill_name}")

        self.assertEqual([], missing, f"Missing runtime path: {missing}")

    def test_mapped_effect_keys_are_consumed(self):
        records = iter_skill_records(load_skill_trees())
        runtime_map = build_skill_runtime_map(records)
        contexts = extract_effect_contexts()

        unconsumed = []
        for record in records:
            mapping = runtime_map[(record.element, record.skill_name)]
            for key in mapping["effect_keys"]:
                if key not in contexts:
                    unconsumed.append(f"{record.element}:{record.skill_name}:{key}")

        self.assertEqual([], unconsumed, f"Unconsumed effect keys: {unconsumed}")

    def test_no_set_only_contract_flags(self):
        contract_flags = {
            "attack_priority",
            "quick_charge_active",
            "air_currents_boost",
            "freedom_boost",
            "zephyr_speed",
            "zephyr_slow",
            "shadow_form_turns",
            "infinite_energy_turns",
            "infinite_energy_active",
        }
        set_only = collect_set_only_attrs()
        broken = sorted(contract_flags.intersection(set_only.keys()))
        self.assertEqual([], broken, f"Set-only contract flags: {broken}")

    def test_audit_report_has_no_bug_no_op_or_drift(self):
        report = build_audit()
        counts = report["summary"]["mismatch_counts"]
        self.assertEqual(0, counts["BUG"])
        self.assertEqual(0, counts["NO_OP"])
        self.assertEqual(0, counts["DRIFT"])


if __name__ == "__main__":
    unittest.main()

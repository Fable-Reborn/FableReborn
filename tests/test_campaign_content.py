import json
import importlib.util
import unittest
from pathlib import Path


MODULE_PATH = Path("cogs/quests/campaign_content.py")
SPEC = importlib.util.spec_from_file_location("campaign_content_contract", MODULE_PATH)
campaign_content = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(campaign_content)

CampaignPackageError = campaign_content.CampaignPackageError
quest_record_from_node = campaign_content.quest_record_from_node
validate_package = campaign_content.validate_package


EXAMPLE_PATH = Path("assets/data/campaign_package_example.json")


class TestCampaignContent(unittest.TestCase):
    def load_example(self):
        return json.loads(EXAMPLE_PATH.read_text(encoding="utf-8"))

    def test_example_package_is_valid(self):
        package = validate_package(self.load_example())
        self.assertEqual("ashen_road", package["campaigns"][0]["key"])
        self.assertEqual(2, len(package["monsters"]))

    def test_quest_conversion_adds_campaign_gate_and_conditions(self):
        package = validate_package(self.load_example())
        campaign = package["campaigns"][0]
        node = campaign["nodes"][2]
        record = quest_record_from_node(campaign, node)

        self.assertEqual("ashen_road_mercy_path", record["quest_key"])
        self.assertEqual("ashen_road", record["access"]["campaign_key"])
        self.assertEqual("mercy_path", record["access"]["campaign_node_key"])
        self.assertEqual(2, len(record["access"]["conditions"]))

    def test_missing_branch_target_is_rejected(self):
        package = self.load_example()
        package["campaigns"][0]["nodes"][0]["next"][0]["target"] = "missing"
        with self.assertRaises(CampaignPackageError) as raised:
            validate_package(package)
        self.assertTrue(any("missing node" in error for error in raised.exception.errors))

    def test_unknown_condition_is_rejected(self):
        package = self.load_example()
        package["campaigns"][0]["requirements"] = [
            {"type": "has_a_cool_hat", "key": "yes"}
        ]
        with self.assertRaises(CampaignPackageError):
            validate_package(package)

    def test_invalid_party_range_is_rejected(self):
        package = self.load_example()
        encounter = package["campaigns"][0]["nodes"][4]["encounter"]
        encounter["party"] = {"min": 5, "max": 2}
        with self.assertRaises(CampaignPackageError):
            validate_package(package)


if __name__ == "__main__":
    unittest.main()

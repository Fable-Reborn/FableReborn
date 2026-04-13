import unittest

from cogs.raidbuilder import RaidBuilder, RaidBuilderPanelView


class DummyRaidBuilderCog:
    _get_active_definition_id = RaidBuilder._get_active_definition_id
    _get_definition = RaidBuilder._get_definition
    _definition_skeleton_key = RaidBuilder._definition_skeleton_key
    _definition_active_modes = RaidBuilder._definition_active_modes
    _can_delete_definition = RaidBuilder._can_delete_definition
    _delete_definition = RaidBuilder._delete_definition
    _builder_page_specs = RaidBuilder._builder_page_specs
    _builder_item_options = RaidBuilder._builder_item_options
    _reward_page_payload = RaidBuilder._reward_page_payload
    _good_builder_page_payload = RaidBuilder._good_builder_page_payload
    _evil_builder_page_payload = RaidBuilder._evil_builder_page_payload
    _chaos_builder_page_payload = RaidBuilder._chaos_builder_page_payload
    _normalize_reward_amount_spec = staticmethod(RaidBuilder._normalize_reward_amount_spec)
    _parse_reward_amount_spec = staticmethod(RaidBuilder._parse_reward_amount_spec)
    _roll_reward_amount_spec = staticmethod(RaidBuilder._roll_reward_amount_spec)
    _format_reward_amount_spec = staticmethod(RaidBuilder._format_reward_amount_spec)
    _format_weighted_crate_pool = staticmethod(RaidBuilder._format_weighted_crate_pool)
    _parse_weighted_crate_pool = staticmethod(RaidBuilder._parse_weighted_crate_pool)

    def __init__(self, registry):
        self.registry = registry
        self.saved = False

    def _save_registry(self, registry=None):
        self.saved = True


class DummyRaidBuilderView:
    _definitions_for_selected_mode = RaidBuilderPanelView._definitions_for_selected_mode
    _default_definition_id = RaidBuilderPanelView._default_definition_id
    _page_specs = RaidBuilderPanelView._page_specs
    current_definition = RaidBuilderPanelView.current_definition

    def __init__(self, cog, selected_mode, selected_definition_id=None):
        self.cog = cog
        self.selected_mode = selected_mode
        self.selected_definition_id = selected_definition_id


class TestRaidBuilderDefaultSelection(unittest.TestCase):
    def test_prefers_custom_definition_over_starter_template(self):
        registry = RaidBuilder.default_registry()
        registry["definitions"]["sep_custom"] = RaidBuilder.build_draft_from_starter(
            "evil",
            "sep_custom",
        )
        view = DummyRaidBuilderView(DummyRaidBuilderCog(registry), "evil")

        self.assertEqual(view._default_definition_id(), "sep_custom")

    def test_ignores_stale_active_definition_from_another_mode(self):
        registry = RaidBuilder.default_registry()
        registry["definitions"]["sep_custom"] = RaidBuilder.build_draft_from_starter(
            "evil",
            "sep_custom",
        )
        registry["modes"]["evil"]["active_definition_id"] = "good_trial_remaster"
        view = DummyRaidBuilderView(DummyRaidBuilderCog(registry), "evil")

        self.assertEqual(view._default_definition_id(), "sep_custom")

    def test_active_definition_still_wins_when_valid(self):
        registry = RaidBuilder.default_registry()
        active_definition = RaidBuilder.build_draft_from_starter("evil", "sep_custom")
        active_definition["status"] = "published"
        registry["definitions"]["sep_custom"] = active_definition
        registry["modes"]["evil"]["active_definition_id"] = "sep_custom"
        view = DummyRaidBuilderView(DummyRaidBuilderCog(registry), "evil")

        self.assertEqual(view._default_definition_id(), "sep_custom")


class TestRaidBuilderSkeletonVariants(unittest.TestCase):
    def test_cross_mode_starter_preserves_mode_and_changes_skeleton(self):
        definition = RaidBuilder.build_draft_from_starter(
            "evil",
            "sep_trial",
            skeleton_key="good",
        )

        self.assertEqual(definition["mode"], "evil")
        self.assertEqual(definition["skeleton"], "trial")
        self.assertEqual(definition["source_definition_id"], "good_trial_remaster")

    def test_builder_pages_follow_definition_skeleton_not_owner_mode(self):
        registry = RaidBuilder.default_registry()
        registry["definitions"]["sep_trial"] = RaidBuilder.build_draft_from_starter(
            "evil",
            "sep_trial",
            skeleton_key="trial",
        )
        view = DummyRaidBuilderView(
            DummyRaidBuilderCog(registry),
            "evil",
            selected_definition_id="sep_trial",
        )

        page_keys = [page["key"] for page in view._page_specs()]
        self.assertIn("timings", page_keys)
        self.assertNotIn("ritual_core", page_keys)

    def test_ritual_starter_includes_countdown_copy_defaults(self):
        definition = RaidBuilder.build_draft_from_starter("evil", "sep_custom")
        announce = definition["config"]["announce"]

        self.assertIn("countdown_messages", announce)
        self.assertEqual(announce["countdown_messages"][0]["key"], "ten_minutes")
        self.assertIn("start_message", announce)
        self.assertIn("eligibility_message", announce)

    def test_ritual_builder_exposes_countdown_page_and_items(self):
        registry = RaidBuilder.default_registry()
        registry["definitions"]["sep_custom"] = RaidBuilder.build_draft_from_starter(
            "evil",
            "sep_custom",
        )
        cog = DummyRaidBuilderCog(registry)
        view = DummyRaidBuilderView(
            cog,
            "evil",
            selected_definition_id="sep_custom",
        )

        page_keys = [page["key"] for page in view._page_specs()]
        item_keys = [
            item["key"]
            for item in cog._builder_item_options(registry["definitions"]["sep_custom"], "countdown_copy")
        ]

        self.assertIn("countdown_copy", page_keys)
        self.assertIn("countdown:ten_minutes", item_keys)
        self.assertIn("start_message", item_keys)
        self.assertIn("eligibility_message", item_keys)

    def test_trial_starter_includes_countdown_defaults_and_transition_delay(self):
        definition = RaidBuilder.build_draft_from_starter("good", "ely_custom")
        announce = definition["config"]["announce"]

        self.assertIn("countdown_messages", announce)
        self.assertEqual(announce["countdown_messages"][0]["key"], "ten_minutes")
        self.assertIn("start_message", announce)
        self.assertEqual(definition["config"]["transition_delay"], 5)

    def test_trial_builder_exposes_countdown_page_and_items(self):
        registry = RaidBuilder.default_registry()
        registry["definitions"]["ely_custom"] = RaidBuilder.build_draft_from_starter(
            "good",
            "ely_custom",
        )
        cog = DummyRaidBuilderCog(registry)
        view = DummyRaidBuilderView(
            cog,
            "good",
            selected_definition_id="ely_custom",
        )

        page_keys = [page["key"] for page in view._page_specs()]
        item_keys = [
            item["key"]
            for item in cog._builder_item_options(registry["definitions"]["ely_custom"], "countdown_copy")
        ]

        self.assertIn("countdown_copy", page_keys)
        self.assertIn("countdown:ten_minutes", item_keys)
        self.assertIn("start_message", item_keys)

    def test_outcome_copy_defaults_exist_for_all_skeletons(self):
        good_definition = RaidBuilder.build_draft_from_starter("good", "ely_custom")
        evil_definition = RaidBuilder.build_draft_from_starter("evil", "sep_custom")
        chaos_definition = RaidBuilder.build_draft_from_starter("chaos", "dra_custom")

        self.assertIn("no_valid_text", good_definition["config"])
        self.assertIn("defeat_text", good_definition["config"])
        self.assertIn("no_valid", evil_definition["config"]["presentation"]["texts"])
        self.assertIn("no_valid", chaos_definition["config"]["messages"])

    def test_outcome_copy_builder_items_exist(self):
        registry = RaidBuilder.default_registry()
        registry["definitions"]["sep_custom"] = RaidBuilder.build_draft_from_starter(
            "evil",
            "sep_custom",
        )
        cog = DummyRaidBuilderCog(registry)

        good_items = [
            item["key"]
            for item in cog._builder_item_options(registry["definitions"]["good_trial_remaster"], "outcome_copy")
        ]
        evil_items = [
            item["key"]
            for item in cog._builder_item_options(registry["definitions"]["sep_custom"], "outcome_copy")
        ]
        chaos_items = [
            item["key"]
            for item in cog._builder_item_options(registry["definitions"]["chaos_attrition_remaster"], "outcome_copy")
        ]

        self.assertEqual(good_items, ["no_valid", "victory", "defeat"])
        self.assertIn("success", evil_items)
        self.assertIn("stall", evil_items)
        self.assertEqual(chaos_items, ["no_valid", "victory", "defeat", "retreat"])

    def test_reward_defaults_exist_for_all_skeletons(self):
        good_definition = RaidBuilder.build_draft_from_starter("good", "ely_rewards")
        evil_definition = RaidBuilder.build_draft_from_starter("evil", "sep_rewards")
        chaos_definition = RaidBuilder.build_draft_from_starter("chaos", "dra_rewards")

        self.assertIn("rewards", good_definition["config"])
        self.assertEqual(good_definition["config"]["rewards"]["participant_gold"], 0)
        self.assertIn("crate_pool", good_definition["config"]["rewards"])
        self.assertEqual(evil_definition["config"]["rewards"]["participant_gold"], 35000)
        self.assertIn("crate_pool", evil_definition["config"]["rewards"])
        self.assertIn("winner_gold_bonus", chaos_definition["config"]["rewards"])
        self.assertIn("crate_pool", chaos_definition["config"]["rewards"])

    def test_builder_pages_expose_rewards_page_for_all_skeletons(self):
        cog = DummyRaidBuilderCog(RaidBuilder.default_registry())
        trial_pages = [page["key"] for page in cog._builder_page_specs("trial")]
        ritual_pages = [page["key"] for page in cog._builder_page_specs("ritual")]
        attrition_pages = [page["key"] for page in cog._builder_page_specs("attrition")]

        self.assertIn("rewards", trial_pages)
        self.assertIn("rewards", ritual_pages)
        self.assertIn("rewards", attrition_pages)

    def test_parse_weighted_crate_pool_supports_disable_and_merges_duplicates(self):
        self.assertEqual(
            RaidBuilder._parse_weighted_crate_pool("none", "Crate pool"),
            [],
        )
        self.assertEqual(
            RaidBuilder._parse_weighted_crate_pool(
                "legendary=40, fortune=10, legendary=5",
                "Crate pool",
            ),
            [
                {"rarity": "legendary", "weight": 45},
                {"rarity": "fortune", "weight": 10},
            ],
        )

    def test_reward_amount_spec_supports_fixed_values_and_ranges(self):
        self.assertEqual(
            RaidBuilder._parse_reward_amount_spec("0", "Dragon coins"),
            0,
        )
        self.assertEqual(
            RaidBuilder._parse_reward_amount_spec("20000-50000", "Participant gold"),
            {"min": 20000, "max": 50000},
        )
        self.assertEqual(
            RaidBuilder._normalize_reward_amount_spec("5-1", default=0),
            {"min": 1, "max": 5},
        )
        self.assertEqual(
            RaidBuilder._format_reward_amount_spec({"min": 2, "max": 5}),
            "2-5",
        )
        self.assertEqual(
            RaidBuilder._format_reward_amount_spec({"min": 20000, "max": 50000}, currency=True),
            "$20,000-$50,000",
        )

    def test_reward_page_payload_displays_range_defaults(self):
        registry = RaidBuilder.default_registry()
        definition = registry["definitions"]["evil_ritual_remaster"]
        definition["config"]["rewards"]["participant_gold"] = {"min": 20000, "max": 50000}
        definition["config"]["rewards"]["dragon_coins"] = 0
        cog = DummyRaidBuilderCog(registry)

        payload = cog._reward_page_payload(
            definition,
            description="Set success payouts for this ritual.",
            bonus_label=None,
            dragon_coin_label="Participant",
            crate_recipient_label="participant",
            submit_message="Updated ritual rewards.",
        )

        self.assertEqual(payload["fields"][0]["value"], "$20,000-$50,000")
        self.assertEqual(payload["form_fields"][0]["default"], "20000-50000")
        self.assertEqual(payload["form_fields"][1]["default"], "0")
        self.assertIn("20000-50000", payload["description"])
        self.assertIn("weights", payload["description"])
        self.assertEqual(payload["fields"][2]["name"], "Crate Pool Weights")
        self.assertEqual(payload["fields"][3]["name"], "Format Help")


class TestRaidBuilderDeletion(unittest.TestCase):
    def test_delete_definition_removes_custom_entry_and_clears_active_modes(self):
        registry = RaidBuilder.default_registry()
        registry["definitions"]["sep_trial"] = RaidBuilder.build_draft_from_starter(
            "evil",
            "sep_trial",
            skeleton_key="trial",
        )
        registry["modes"]["evil"]["active_definition_id"] = "sep_trial"
        cog = DummyRaidBuilderCog(registry)

        cleared_modes = cog._delete_definition("sep_trial")

        self.assertEqual(cleared_modes, ["evil"])
        self.assertNotIn("sep_trial", registry["definitions"])
        self.assertIsNone(registry["modes"]["evil"]["active_definition_id"])
        self.assertTrue(cog.saved)

    def test_delete_definition_rejects_starter_templates(self):
        registry = RaidBuilder.default_registry()
        cog = DummyRaidBuilderCog(registry)

        with self.assertRaisesRegex(ValueError, "Starter templates cannot be deleted"):
            cog._delete_definition("evil_ritual_remaster")


if __name__ == "__main__":
    unittest.main()

import unittest

from cogs.raidbuilder import RaidBuilder, RaidBuilderPanelView


class DummyRaidBuilderCog:
    _get_active_definition_id = RaidBuilder._get_active_definition_id
    _get_definition = RaidBuilder._get_definition
    _definition_skeleton_key = RaidBuilder._definition_skeleton_key
    _builder_page_specs = RaidBuilder._builder_page_specs

    def __init__(self, registry):
        self.registry = registry


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


if __name__ == "__main__":
    unittest.main()

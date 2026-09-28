import copy
import logging
import tempfile
import unittest

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from cogs.raidbuilder import (
    RaidBuilder,
    RaidBuilderDeleteDefinitionView,
    RaidBuilderFormModal,
    RaidBuilderItemSelect,
    RaidBuilderPanelView,
    RaidBuilderStructureView,
)
from cogs.raidbuilder.advanced import AdvancedOptionsView, DecisionView
from cogs.raidbuilder.storage import StaleEdit, StorageError, library_counts


class MemoryDatabase:
    """Shared fake database, exercising the store's actual SQL call boundaries."""

    def __init__(self):
        self.row = None
        self.prefs = {}
        self.fail = False
        self.seed_calls = 0

    def acquire(self):
        return self

    def transaction(self):
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    async def execute(self, sql, *args):
        if self.fail:
            raise OSError("database unavailable")
        if "INSERT INTO raid_builder_registry" in sql:
            self.seed_calls += 1
            self.row = {"revision": 1, "content": args[0]}
        elif "INSERT INTO raid_builder_preferences" in sql:
            self.prefs[args[:2]] = args[2]

    async def fetchrow(self, sql, *args):
        if self.fail:
            raise OSError("database unavailable")
        return dict(self.row) if self.row else None

    async def fetchval(self, sql, *args):
        if self.fail:
            raise OSError("database unavailable")
        if "UPDATE raid_builder_registry" in sql:
            content, expected = args
            if expected != self.row["revision"]:
                return None
            self.row = {"content": content, "revision": expected + 1}
            return expected + 1
        if "raid_builder_preferences" in sql:
            return self.prefs.get(args)
        return self.row["revision"] if self.row else None


def context(user=123, guild=456):
    ctx = SimpleNamespace(
        author=SimpleNamespace(id=user),
        guild=SimpleNamespace(id=guild),
        send=AsyncMock(),
    )
    ctx.send.return_value = SimpleNamespace(edit=AsyncMock())
    return ctx


def interaction(user=123):
    response = SimpleNamespace(
        send_message=AsyncMock(),
        defer=AsyncMock(),
        edit_message=AsyncMock(),
        send_modal=AsyncMock(),
        is_done=lambda: False,
    )
    return SimpleNamespace(
        user=SimpleNamespace(id=user),
        response=response,
        followup=SimpleNamespace(send=AsyncMock()),
    )


class PersistenceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.db = MemoryDatabase()
        self.bot = SimpleNamespace(pool=self.db, logger=logging.getLogger("raidtests"))
        self.cog = RaidBuilder(self.bot)
        # Never read/write the real runtime JSON in tests.
        self.cog._load_registry = self.cog.default_registry
        await self.cog.cog_load()

    async def draft(self, name="my_raid", skeleton="encounter", user=123):
        result = self.cog._new_personal_draft("evil", name, skeleton, user)
        await self.cog._save_registry()
        return result

    async def test_import_runs_once_and_preserves_source(self):
        second = RaidBuilder(self.bot)
        second._load_registry = lambda: self.fail(
            "Existing database must not reimport JSON"
        )
        await second.cog_load()
        self.assertEqual(self.db.seed_calls, 1)

    async def test_deleted_actions_and_order_survive_database_reload(self):
        draft = await self.draft(skeleton="ritual")
        actions = draft["config"]["champion"]["actions"]
        removed = next(iter(actions))
        del actions[removed]
        draft["config"]["champion"]["actions"] = dict(reversed(list(actions.items())))
        expected = list(draft["config"]["champion"]["actions"])
        await self.cog._save_registry()
        second = RaidBuilder(self.bot)
        await second.cog_load()
        restored = second.registry["definitions"]["my_raid"]["config"]["champion"][
            "actions"
        ]
        self.assertEqual(list(restored), expected)
        self.assertNotIn(removed, restored)

    async def test_bad_legacy_json_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as temp:
            cog = RaidBuilder(self.bot)
            cog.registry_path = Path(temp) / "registry.json"
            cog.registry_path.write_text("{broken", encoding="utf-8")
            with self.assertRaises(ValueError):
                cog._load_registry()
            self.assertEqual(cog.registry_path.read_text(), "{broken")

    async def test_combined_draft_quota_and_personal_isolation(self):
        for i in range(10):
            await self.draft(f"raid_{i}", "encounter" if i % 2 else "ritual")
        with self.assertRaisesRegex(ValueError, "10 drafts"):
            await self.draft("overflow", "trial")
        await self.draft("other_gm", user=999)
        self.assertEqual(
            library_counts(self.cog.registry, 123), {"saved": 0, "drafts": 10}
        )

    async def test_five_saved_and_revision_replacement_does_not_consume_sixth_slot(
        self,
    ):
        for i in range(5):
            draft = await self.draft(f"raid_{i}", "encounter" if i % 2 else "ritual")
            self.cog._publish_personal(draft, 123)
            await self.cog._save_registry()
        sixth = await self.draft("sixth")
        with self.assertRaisesRegex(ValueError, "5 saved"):
            self.cog._publish_personal(sixth, 123)
        original = self.cog._get_definition("raid_1")
        revision = self.cog._new_personal_draft(
            "evil", "revision", "encounter", 123, source=original
        )
        revision["name"] = "Revised"
        self.assertEqual(original["name"], "New Advanced Raid")
        self.cog.registry["modes"]["evil"]["active_definition_id"] = "raid_1"
        self.assertEqual(self.cog._publish_personal(revision, 123), "raid_1")
        self.assertEqual(self.cog._get_active_definition("evil")["name"], "Revised")
        self.assertEqual(
            library_counts(self.cog.registry, 123), {"saved": 5, "drafts": 1}
        )

    async def test_outdated_revision_cannot_replace_newer_saved_raid(self):
        draft = await self.draft()
        self.cog._publish_personal(draft, 123)
        original = self.cog._get_definition("my_raid")
        a = self.cog._new_personal_draft(
            "evil", "rev_a", "encounter", 123, source=original
        )
        b = self.cog._new_personal_draft(
            "evil", "rev_b", "encounter", 123, source=original
        )
        self.cog._publish_personal(a, 123)
        with self.assertRaisesRegex(ValueError, "changed since"):
            self.cog._publish_personal(b, 123)

    async def test_stale_cross_cluster_save_preserves_winner(self):
        second = RaidBuilder(self.bot)
        await second.cog_load()
        await self.draft("cluster_one")
        second._new_personal_draft("evil", "cluster_two", "trial", 123)
        with self.assertRaises(StaleEdit):
            await second._save_registry()
        contents, _ = await self.cog.store.load()
        self.assertIn("cluster_one", contents["definitions"])
        self.assertNotIn("cluster_two", contents["definitions"])

    async def test_database_outage_never_replaces_data(self):
        await self.draft()
        before = copy.deepcopy(self.db.row)
        self.db.fail = True
        with self.assertRaises(StorageError):
            await self.cog.store.load()
        with self.assertRaises(StorageError):
            await self.cog._save_registry()
        self.assertEqual(self.db.row, before)

    async def test_preferences_resume_and_explicit_arguments_override(self):
        await self.draft()
        ctx = context()
        panel = RaidBuilderPanelView(
            cog=self.cog, ctx=ctx, initial_mode="evil", initial_definition_id="my_raid"
        )
        panel.current_page_key = "battle"
        panel.current_item_key = "guardian"
        await panel._remember()
        reopened = RaidBuilderPanelView(cog=self.cog, ctx=ctx)
        await reopened.start()
        self.assertEqual(
            (
                reopened.selected_mode,
                reopened.selected_definition_id,
                reopened.current_page_key,
                reopened.current_item_key,
            ),
            ("evil", "my_raid", "battle", "guardian"),
        )
        explicit = RaidBuilderPanelView(cog=self.cog, ctx=ctx, initial_mode="good")
        await explicit.start()
        self.assertEqual(explicit.selected_mode, "good")
        self.assertEqual(await self.cog.store.preferences(999, 456), {})

    async def test_publishing_button_actually_awaits_storage(self):
        await self.draft()
        panel = RaidBuilderPanelView(
            cog=self.cog,
            ctx=context(),
            initial_mode="evil",
            initial_definition_id="my_raid",
        )
        await panel.state_button.callback(interaction())
        contents, _ = await self.cog.store.load()
        self.assertEqual(contents["definitions"]["my_raid"]["status"], "published")
        await panel.state_button.callback(interaction())
        contents, _ = await self.cog.store.load()
        self.assertEqual(contents["modes"]["evil"]["active_definition_id"], "my_raid")

    async def test_rejected_form_rolls_back_partial_normal_edits(self):
        await self.draft(skeleton="trial")
        panel = RaidBuilderPanelView(
            cog=self.cog,
            ctx=context(),
            initial_mode="evil",
            initial_definition_id="my_raid",
        )
        payload = panel._current_payload()
        modal = RaidBuilderFormModal(
            panel,
            title="Edit",
            fields=payload["form_fields"],
            submit_handler=payload["submit_handler"],
        )
        old = copy.deepcopy(self.cog.registry)
        for key, widget in modal.inputs.items():
            widget._value = "Changed" if key in {"name", "description"} else "invalid"
        await modal.on_submit(interaction())
        self.assertEqual(self.cog.registry, old)

    async def test_stale_modal_rejected_even_after_panel_navigates(self):
        await self.draft()
        panel = RaidBuilderPanelView(
            cog=self.cog,
            ctx=context(),
            initial_mode="evil",
            initial_definition_id="my_raid",
        )
        payload = panel._current_payload()
        modal = RaidBuilderFormModal(
            panel,
            title="Edit",
            fields=payload["form_fields"],
            submit_handler=payload["submit_handler"],
        )
        await self.draft("another")
        await panel.refresh_message()
        result = interaction()
        await modal.on_submit(result)
        self.assertIn("out of date", result.response.send_message.call_args.args[0])

    async def test_unauthorized_edit_and_delete_are_rejected(self):
        await self.draft(user=999)
        panel = RaidBuilderPanelView(
            cog=self.cog,
            ctx=context(),
            initial_mode="evil",
            initial_definition_id="my_raid",
        )
        delete = RaidBuilderDeleteDefinitionView(panel)
        result = interaction()
        await delete.confirm_button.callback(result)
        self.assertIn("my_raid", self.cog.registry["definitions"])
        self.assertIn("Copy", result.response.send_message.call_args.args[0])

    async def test_advanced_options_and_large_item_lists_fit_discord(self):
        draft = await self.draft()
        panel = RaidBuilderPanelView(
            cog=self.cog,
            ctx=context(),
            initial_mode="evil",
            initial_definition_id="my_raid",
        )
        panel.current_page_key = "actions"
        panel.current_item_key = "strike"
        view = AdvancedOptionsView(panel)
        self.assertEqual(len(view.children), 5)
        await panel.edit_page_button.callback(interaction())
        for i in range(30):
            await self.cog._advanced_structure_action(draft, "steps", "arrival", "add")
        panel.current_page_key = "steps"
        panel.current_item_key = "arrival"
        selector = RaidBuilderItemSelect(panel)
        self.assertLessEqual(len(selector.options), 25)
        self.assertIn("__next__", [o.value for o in selector.options])

    async def test_normal_and_advanced_simulation_pages_render(self):
        for skeleton in ("trial", "ritual", "attrition", "encounter"):
            await self.draft(skeleton, skeleton)
            panel = RaidBuilderPanelView(
                cog=self.cog,
                ctx=context(),
                initial_mode="evil",
                initial_definition_id=skeleton,
            )
            for page in panel._page_specs():
                panel.current_page_key = page["key"]
                panel.current_item_key = None
                panel._sync_controls()
                embed = panel._build_embed()
                self.assertLessEqual(len(embed), 6000)
                self.assertLessEqual(len(panel.children), 25)
                self.assertLessEqual(
                    len(panel._current_payload().get("form_fields", [])), 5
                )

    async def test_structural_dialog_keeps_its_original_target(self):
        first = await self.draft("first", "trial")
        await self.draft("second", "trial")
        panel = RaidBuilderPanelView(
            cog=self.cog,
            ctx=context(),
            initial_mode="evil",
            initial_definition_id="first",
        )
        panel.current_page_key, panel.current_item_key = "phase", "day"
        dialog = RaidBuilderStructureView(panel)
        panel.selected_definition_id = "second"
        await dialog.add_button.callback(interaction())
        self.assertEqual(
            len(self.cog._get_definition("first")["config"]["phases"]),
            len(first["config"]["phases"]),
        )
        self.assertEqual(len(self.cog._get_definition("second")["config"]["phases"]), 2)
        self.assertEqual(len(self.cog._get_definition("first")["config"]["phases"]), 3)

    async def test_options_save_and_details_form_use_captured_target(self):
        await self.draft()
        panel = RaidBuilderPanelView(
            cog=self.cog,
            ctx=context(),
            initial_mode="evil",
            initial_definition_id="my_raid",
        )
        panel.current_page_key, panel.current_item_key = "steps", "arrival"
        view = AdvancedOptionsView(panel)
        select = view.children[0]
        select._values = ["choice"]
        panel.current_item_key = "guardian"
        await select.callback(interaction())
        stored, _ = await self.cog.store.load()
        self.assertEqual(
            stored["definitions"]["my_raid"]["config"]["encounter"]["nodes"][0]["kind"],
            "choice",
        )
        result = interaction()
        await view.details(result)
        modal = result.response.send_modal.call_args.args[0]
        self.assertEqual(modal.item_key, "arrival")

    async def test_live_adapter_uses_engine_and_rewards_only_victory(self):
        draft = await self.draft()
        fake_join = SimpleNamespace(joined=[SimpleNamespace(id=1)], wait=AsyncMock())
        self.cog._filter_eligible_users = AsyncMock(
            side_effect=lambda users, god: users
        )
        self.cog._award_definition_rewards = AsyncMock()
        for outcome in ("victory", "defeat"):
            draft["config"]["encounter"]["start"] = outcome
            with patch("cogs.raidbuilder.advanced.JoinView", return_value=fake_join):
                await self.cog._run_encounter_definition(context(), draft)
        self.cog._award_definition_rewards.assert_awaited_once()

    async def test_simulation_does_not_mutate_or_award_rewards(self):
        draft = await self.draft()
        before = copy.deepcopy(self.cog.registry)
        self.cog._award_definition_rewards = AsyncMock()
        payload = self.cog._advanced_page_payload(draft, "simulate", None)
        result = await payload["submit_handler"]({"players": "5", "seed": "42"})
        self.assertIn("Simulation:", result)
        self.assertEqual(self.cog.registry, before)
        self.cog._award_definition_rewards.assert_not_awaited()

    async def test_commands_enforce_draft_limit_and_unpublish_limit(self):
        saved = await self.draft("saved")
        self.cog._publish_personal(saved, 123)
        await self.cog._save_registry()
        for i in range(10):
            await self.draft(f"draft_{i}")
        ctx = context()
        await self.cog.raidmode_create.callback(
            self.cog, ctx, "evil", "overflow", "advanced"
        )
        self.assertIn("10 drafts", ctx.send.call_args.args[0])
        await self.cog.raidmode_unpublish.callback(self.cog, ctx, "saved")
        self.assertIn("10 drafts", ctx.send.call_args.args[0])
        self.assertEqual(self.cog._get_definition("saved")["status"], "published")

    async def test_failed_button_save_restores_registry_and_can_retry(self):
        await self.draft()
        panel = RaidBuilderPanelView(
            cog=self.cog,
            ctx=context(),
            initial_mode="evil",
            initial_definition_id="my_raid",
        )
        original = self.cog.store.save
        self.cog.store.save = AsyncMock(side_effect=StorageError("save failed"))
        await panel.state_button.callback(interaction())
        self.assertEqual(self.cog._get_definition("my_raid")["status"], "draft")
        self.cog.store.save = original
        await panel.state_button.callback(interaction())
        self.assertEqual(self.cog._get_definition("my_raid")["status"], "published")

    async def test_dead_and_outsider_players_cannot_submit_choices(self):
        view = DecisionView([("strike", "Strike")], ["123"], 10)
        view.selector._values = ["strike"]
        await view.choose(interaction(999))
        self.assertEqual(view.decisions, {})
        await view.choose(interaction(123))
        self.assertEqual(view.decisions, {"123": "strike"})

    async def test_full_draft_slot_race_between_clusters_rejects_second_writer(self):
        for i in range(9):
            await self.draft(f"draft_{i}")
        other = RaidBuilder(self.bot)
        await other.cog_load()
        self.cog._new_personal_draft("evil", "last_one", "trial", 123)
        other._new_personal_draft("evil", "last_two", "encounter", 123)
        await self.cog._save_registry()
        with self.assertRaises(StaleEdit):
            await other._save_registry()
        registry, _ = await self.cog.store.load()
        self.assertEqual(library_counts(registry, 123)["drafts"], 10)


if __name__ == "__main__":
    unittest.main()

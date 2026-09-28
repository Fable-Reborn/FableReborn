import copy
import json
import unittest

from cogs.raidbuilder.engine import EncounterEngine, advanced_starter, default_rule, validate_encounter
from cogs.raidbuilder.mechanics import enemy_default, role_default, status_default, team_default, upgrade_encounter
from cogs.raidbuilder.canvas import editor_html, export_package, import_package
from cogs.raidbuilder.runtime_ui import BattleDecisionView, PlayerActionView, RoleAssignmentView
from tests.test_raidbuilder_persistence import interaction


def sample():
    raid = advanced_starter("evil", "advanced_raid")
    raid["creator_id"] = 123
    spec = raid["config"]["encounter"]
    spec["teams"].append(team_default("wardens"))
    spec["roles"].append(dict(role_default("warden"), team="wardens", slots=1, hp=200))
    spec["statuses"] = [status_default("burn"), dict(status_default("stun"), stun=True, duration=1, damage_per_round=0)]
    spec["nodes"][1]["enemies"] = [dict(enemy_default("guardian"), hp=200, damage=10), dict(enemy_default("shade"), hp=40, damage=5)]
    spec["actions"].append(dict(spec["actions"][0], id="warden_strike", label="Warden Strike", amount=50, roles=["warden"], target="enemy"))
    return raid


class MechanicsTests(unittest.TestCase):
    def setUp(self):
        self.spec = sample()["config"]["encounter"]

    def engine(self, players=(1, 2), **kwargs):
        engine = EncounterEngine(self.spec, players, seed=10, **kwargs)
        engine.advance()
        return engine

    def test_legacy_upgrade_preserves_content_and_adds_catalogues(self):
        old = advanced_starter("evil", "legacy")["config"]["encounter"]
        old["version"] = 1
        for key in ("teams", "roles", "statuses", "layout"):
            old.pop(key)
        before = copy.deepcopy(old)
        upgraded = upgrade_encounter(old)
        self.assertEqual(old, before)
        self.assertEqual(upgraded["nodes"], old["nodes"])
        self.assertEqual(upgraded["version"], 2)
        validate_encounter(upgraded)

    def test_role_slots_team_and_health_with_unselected_fallback(self):
        engine = self.engine(role_choices={2: "warden", 3: "warden"}, players=(1, 2, 3))
        self.assertEqual(engine.players["2"].role, "warden")
        self.assertEqual(engine.players["2"].hp, 200)
        self.assertEqual(engine.players["2"].team, "wardens")
        self.assertEqual(engine.players["3"].role, "adventurer")

    def test_role_restrictions_cannot_be_bypassed_by_action_id(self):
        engine = self.engine(players=(1,))
        engine.advance({1: {"action": "warden_strike", "target": "guardian"}})
        self.assertEqual(engine.enemies["guardian"].hp, 180)
        self.assertNotIn("warden_strike", {k for k, _ in engine.prompt(1)})

    def test_multiple_enemies_attack_independently_and_selected_enemy_dies(self):
        engine = self.engine(players=(1,), role_choices={1: "warden"})
        engine.advance({1: {"action": "warden_strike", "target": "shade"}})
        self.assertEqual(engine.enemies["shade"].hp, 0)
        self.assertEqual(engine.enemies["guardian"].hp, 200)
        self.assertEqual(engine.players["1"].hp, 190)
        self.assertEqual(engine.node_id, "guardian")

    def test_both_living_enemies_deal_damage(self):
        engine = self.engine(players=(1,))
        engine.advance({1: "mend"})
        self.assertEqual(engine.players["1"].hp, 85)

    def test_role_and_team_targets(self):
        rule = dict(default_rule("support"), trigger="enter", effect="shield", amount=30, target="team:wardens")
        self.spec["nodes"][1]["rules"] = [rule]
        engine = self.engine(role_choices={2: "warden"})
        engine.advance({1: "mend", 2: "mend"})
        self.assertEqual(engine.players["1"].shield, 0)
        self.assertGreater(engine.players["2"].shield, 0)

    def test_compound_and_or_not_condition_triggers_phase_change(self):
        rule = dict(default_rule("branch"), effect="transition", destination="victory", condition={"all": [
            {"subject": "role_alive:warden", "operator": ">=", "value": 1},
            {"any": [{"subject": "enemies_alive", "operator": "==", "value": 1},
                     {"not": {"subject": "corruption", "operator": ">", "value": 0}}]},
        ]})
        self.spec["nodes"][1]["rules"] = [rule]
        engine = self.engine(role_choices={2: "warden"})
        engine.advance()
        self.assertEqual(engine.node_id, "victory")

    def test_compound_false_condition_does_not_fire(self):
        rule = dict(default_rule("branch"), effect="transition", destination="victory",
                    condition={"all": [{"subject": "alive", "operator": ">", "value": 99}, {"operator": "always"}]})
        self.spec["nodes"][1]["rules"] = [rule]
        engine = self.engine()
        engine.advance()
        self.assertEqual(engine.node_id, "guardian")

    def test_status_stacking_caps_and_ticks_then_expires(self):
        self.spec["statuses"][0].update(duration=1, max_stacks=2)
        self.spec["actions"].append(dict(self.spec["actions"][0], id="burn", label="Burn", effect="apply_status", status="burn", amount=2, target="enemy"))
        engine = self.engine(players=(1,))
        engine.advance({1: {"action": "burn", "target": "guardian"}})
        self.assertEqual(engine.enemies["guardian"].hp, 200)
        self.assertEqual(engine.enemies["guardian"].statuses["burn"]["stacks"], 2)
        engine.advance({1: "mend"})
        self.assertEqual(engine.enemies["guardian"].hp, 190)
        self.assertNotIn("burn", engine.enemies["guardian"].statuses)

    def test_enemy_one_round_stun_prevents_next_player_turn(self):
        self.spec["nodes"][1]["enemies"][0]["on_hit_status"] = "stun"
        engine = self.engine(players=(1,))
        engine.advance()
        hp = engine.boss_hp
        engine.advance()
        self.assertEqual(engine.boss_hp, hp)

    def test_status_damage_modifier_and_cleanse(self):
        self.spec["statuses"].append(dict(status_default("power"), damage_per_round=0, damage_dealt_pct=200))
        self.spec["nodes"][1]["rules"] = [dict(default_rule("powerup"), trigger="enter", effect="apply_status", status="power", target="all", amount=1)]
        engine = self.engine(players=(1,))
        engine.advance()
        self.assertEqual(engine.enemies["guardian"].hp, 160)
        engine._effect({"effect": "remove_status", "status": "power", "amount": 0, "target": "all"}, [])
        self.assertNotIn("power", engine.players["1"].statuses)

    def test_status_healing_never_revives_dead_actor(self):
        self.spec["statuses"][0].update(damage_per_round=1000, heal_per_round=1000)
        engine = self.engine(players=(1,))
        engine.advance()
        engine._apply_status(engine.players["1"], "burn", 1)
        engine.advance()
        self.assertEqual(engine.players["1"].hp, 0)

    def test_invalid_catalogues_and_condition_depth_rejected(self):
        cases = []
        for modifier in (
            lambda s: s["roles"][0].update(team="missing"),
            lambda s: s["roles"][0].update(slots=1),
            lambda s: s["statuses"][0].update(duration=0),
            lambda s: s["nodes"][1]["enemies"][0].update(target="enemies"),
            lambda s: s["actions"][0].update(roles=["missing"]),
        ):
            candidate = copy.deepcopy(self.spec)
            modifier(candidate)
            cases.append(candidate)
        for candidate in cases:
            with self.assertRaises(ValueError):
                validate_encounter(candidate)
        condition = {"operator": "always"}
        for _ in range(10):
            condition = {"not": condition}
        self.spec["nodes"][1]["rules"] = [dict(default_rule("bad"), condition=condition)]
        with self.assertRaisesRegex(ValueError, "8 levels"):
            validate_encounter(self.spec)


class CanvasTests(unittest.TestCase):
    def test_roundtrip_preserves_graph_and_ignores_owner_rewards_status(self):
        original = sample()
        package = export_package(original)
        package["definition"].update(name="Edited in canvas", creator_id=999, status="published", mode="good")
        package["definition"]["config"]["rewards"]["participant_gold"] = 999999
        result = import_package(json.dumps(package).encode(), original)
        self.assertEqual(result["name"], "Edited in canvas")
        for key in ("creator_id", "status", "mode"):
            self.assertEqual(result[key], original[key])
        self.assertEqual(result["config"]["rewards"], original["config"]["rewards"])
        self.assertEqual(result["config"]["encounter"], original["config"]["encounter"])

    def test_stale_and_wrong_draft_files_rejected(self):
        original = sample()
        package = export_package(original)
        updated = dict(original, name="Someone edited this")
        with self.assertRaisesRegex(ValueError, "changed"):
            import_package(json.dumps(package).encode(), updated)
        package["definition_id"] = "other"
        with self.assertRaisesRegex(ValueError, "different draft"):
            import_package(json.dumps(package).encode(), original)

    def test_export_html_does_not_interpolate_user_markup(self):
        original = sample()
        original["name"] = '</script><script>window.injected=true</script>'
        output = editor_html(original).decode()
        self.assertNotIn(original["name"], output)
        self.assertIn("Content-Security-Policy", output)
        self.assertNotIn("__RAID_PACKAGE_BASE64__", output)

    def test_invalid_compound_condition_cannot_be_imported(self):
        original = sample()
        package = export_package(original)
        package["definition"]["config"]["encounter"]["nodes"][1]["rules"] = [dict(default_rule("bad"), condition={"all": []})]
        with self.assertRaises(ValueError):
            import_package(json.dumps(package).encode(), original)

    def test_oversized_package_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "1 MB"):
            import_package(b" " * 1000001, sample())


class NewInteractionTests(unittest.IsolatedAsyncioTestCase):
    async def test_role_capacity_and_nonparticipant_checks(self):
        roles = sample()["config"]["encounter"]["roles"]
        view = RoleAssignmentView(roles, [123, 456, 789], 30)
        view.selector._values = ["warden"]
        await view.choose(interaction(999))
        self.assertEqual(view.choices, {})
        await view.choose(interaction(123))
        rejected = interaction(456)
        await view.choose(rejected)
        self.assertNotIn("456", view.choices)
        self.assertIn("full", rejected.response.send_message.call_args.args[0])

    async def test_private_action_picker_filters_roles_and_records_enemy(self):
        engine = EncounterEngine(sample()["config"]["encounter"], [123, 456], role_choices={456: "warden"})
        engine.advance()
        parent = BattleDecisionView(engine, 30)
        view = PlayerActionView(parent, 123)
        self.assertNotIn("warden_strike", {o.value for o in view.action_select.options})
        view.action, view.target = "strike", "shade"
        await view.confirm(interaction(123))
        self.assertEqual(parent.decisions["123"]["target"], "shade")
        view2 = PlayerActionView(parent, 456)
        self.assertIn("warden_strike", {o.value for o in view2.action_select.options})

    async def test_closed_action_picker_cannot_change_decisions(self):
        engine = EncounterEngine(sample()["config"]["encounter"], [123])
        engine.advance()
        parent = BattleDecisionView(engine, 30)
        child = PlayerActionView(parent, 123)
        parent.stop()
        await child.confirm(interaction(123))
        self.assertEqual(parent.decisions, {})

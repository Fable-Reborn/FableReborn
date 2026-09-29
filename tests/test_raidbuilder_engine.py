import copy
import unittest

from cogs.raidbuilder.engine import (
    EncounterEngine,
    advanced_starter,
    default_node,
    default_rule,
    validate_encounter,
)


class EncounterTests(unittest.TestCase):
    def setUp(self):
        self.spec = advanced_starter("evil", "test_raid")["config"]["encounter"]

    def test_starter_simulates_deterministically_without_mutating_definition(self):
        original = copy.deepcopy(self.spec)
        a = EncounterEngine(self.spec, [1, 2, 3, 4, 5], seed=20)
        b = EncounterEngine(self.spec, [1, 2, 3, 4, 5], seed=20)
        self.assertEqual(a.simulate(), b.simulate())
        self.assertEqual(self.spec, original)
        self.assertEqual(a.outcome, "victory")

    def test_missing_player_decisions_fall_back_to_free_action(self):
        engine = EncounterEngine(self.spec, [1])
        engine.advance()
        engine.advance()
        self.assertEqual(engine.boss_hp, 280)
        self.assertEqual(engine.players["1"].hp, 90)

    def test_rules_conditions_repeat_limits_and_resources(self):
        rule = default_rule("corrupt")
        rule.update(
            subject="boss_hp_percent",
            operator="<=",
            value=95,
            effect="resource",
            resource="corruption",
            amount=15,
            limit=2,
        )
        self.spec["nodes"][1]["rules"].append(rule)
        engine = EncounterEngine(self.spec, [1])
        engine.advance()
        for _ in range(4):
            engine.advance()
        self.assertEqual(engine.resources["corruption"], 30)

    def test_unaffordable_action_does_not_spend_and_uses_free_fallback(self):
        self.spec["actions"].append(
            dict(
                self.spec["actions"][0],
                id="costly",
                amount=100,
                cost_resource="corruption",
                cost=20,
            )
        )
        engine = EncounterEngine(self.spec, [1])
        engine.advance()
        result = engine.advance({1: "costly"})
        self.assertEqual(engine.resources["corruption"], 0)
        self.assertEqual(engine.boss_hp, 280)
        self.assertIn("fallback", " ".join(result.events))

    def test_vote_majority_and_tie_timeout_branch(self):
        vote = default_node("vote", "choice")
        vote["choices"] = [
            {"id": "save", "label": "Save", "next": "victory"},
            {"id": "leave", "label": "Leave", "next": "defeat"},
        ]
        self.spec["nodes"].append(vote)
        self.spec["start"] = "vote"
        for decisions, target in (
            ({1: "save", 2: "save", 3: "leave"}, "victory"),
            ({1: "save", 2: "leave"}, "defeat"),
            ({}, "defeat"),
        ):
            engine = EncounterEngine(self.spec, [1, 2, 3])
            engine.advance(decisions)
            self.assertEqual(engine.node_id, target)

    def test_invalid_and_outsider_votes_do_not_count(self):
        vote = default_node("vote", "choice")
        vote["choices"] = [
            {"id": "yes", "label": "Yes", "next": "victory"},
            {"id": "no", "label": "No", "next": "defeat"},
        ]
        self.spec["nodes"].append(vote)
        self.spec["start"] = "vote"
        engine = EncounterEngine(self.spec, [1, 2])
        engine.advance({999: "yes", 1: "bad"})
        self.assertEqual(engine.node_id, "defeat")

    def test_loop_with_exit_is_bounded_even_if_exit_never_taken(self):
        node = default_node("loop", "check")
        node.update(subject="alive", operator=">=", value=1, next="loop")
        self.spec["nodes"].append(node)
        self.spec.update(start="loop", max_steps=5)
        engine = EncounterEngine(self.spec, [1])
        frames = engine.simulate()
        self.assertEqual(engine.outcome, "defeat")
        self.assertEqual(len(frames), 6)

    def test_invalid_references_and_unescapable_cycles_rejected(self):
        self.spec["nodes"][0]["next"] = "missing"
        with self.assertRaisesRegex(ValueError, "missing destination"):
            validate_encounter(self.spec)
        self.spec["nodes"][0]["next"] = "arrival"
        with self.assertRaisesRegex(ValueError, "path to an ending"):
            validate_encounter(self.spec)

    def test_unknown_effect_cost_and_condition_rejected(self):
        action = self.spec["actions"][0]
        action["effect"] = "python"
        with self.assertRaisesRegex(ValueError, "supported effect"):
            validate_encounter(self.spec)
        action.update(effect="boss_damage", cost=1, cost_resource="missing")
        with self.assertRaisesRegex(ValueError, "costs"):
            validate_encounter(self.spec)
        action.update(cost=0)
        rule = default_rule("rule")
        rule.update(operator="==", subject="missing")
        self.spec["nodes"][1]["rules"] = [rule]
        with self.assertRaisesRegex(ValueError, "Unknown condition"):
            validate_encounter(self.spec)

    def test_round_limit_takes_failure_route(self):
        self.spec["nodes"][1]["max_rounds"] = 1
        engine = EncounterEngine(self.spec, [1])
        engine.advance()
        engine.advance()
        self.assertEqual(engine.node_id, "defeat")

    def test_enter_damage_cannot_produce_victory_with_no_survivors(self):
        rule = default_rule("wipe")
        rule.update(trigger="enter", effect="damage", target="all", amount=1000)
        self.spec["nodes"][2]["rules"] = [rule]
        self.spec["start"] = "victory"
        engine = EncounterEngine(self.spec, [1, 2])
        self.assertEqual(engine.advance().outcome, "defeat")

    def test_health_shield_and_resource_bounds(self):
        rule = default_rule("shield")
        rule.update(trigger="enter", effect="shield", target="all", amount=100)
        self.spec["nodes"][1]["rules"] = [rule]
        engine = EncounterEngine(self.spec, [1])
        engine.advance()
        engine.advance()
        self.assertEqual(engine.players["1"].hp, 100)
        self.assertEqual(engine.players["1"].shield, 90)

    def test_invalid_ranges_and_negative_damage_rejected(self):
        self.spec["actions"][0]["amount"] = -1
        with self.assertRaises(ValueError):
            validate_encounter(self.spec)

        self.spec["actions"][0]["amount"] = 1
        self.spec["resources"][0]["initial"] = 9999
        with self.assertRaises(ValueError):
            validate_encounter(self.spec)

    def test_health_threshold_rule_can_start_another_encounter_phase(self):
        phase = default_node("eclipse", "battle")
        phase.update(boss_hp=50, title="Eclipse")
        self.spec["nodes"].append(phase)
        rule = default_rule("phase_change")
        rule.update(
            subject="boss_hp_percent",
            operator="<=",
            value=95,
            effect="transition",
            destination="eclipse",
        )
        self.spec["nodes"][1]["rules"] = [rule]
        engine = EncounterEngine(self.spec, [1])
        engine.advance()
        engine.advance()
        self.assertEqual(engine.node_id, "eclipse")
        engine.advance()
        self.assertEqual(engine.boss_hp, 30)

    def test_players_killed_by_prior_action_do_not_act(self):
        self.spec["actions"].append(
            dict(
                self.spec["actions"][0],
                id="wipe",
                effect="damage",
                target="all",
                amount=100,
            )
        )
        engine = EncounterEngine(self.spec, [1, 2])
        engine.advance()
        engine.advance({1: "wipe", 2: "strike"})
        self.assertEqual(engine.boss_hp, 300)
        self.assertEqual(engine.outcome, "defeat")

    def test_choice_rules_scale_by_each_options_votes(self):
        council = default_node("council", "choice")
        council.update(
            choices=[
                {"id": "soldiers", "label": "Soldiers", "next": "guardian"},
                {"id": "walls", "label": "Walls", "next": "guardian"},
            ],
            failure="guardian",
        )
        allocate = default_rule("allocate")
        allocate.update(trigger="choice", effect="resource", resource="corruption",
                        amount=10, scale="votes:soldiers")
        council["rules"] = [allocate]
        self.spec["nodes"].append(council)
        self.spec["nodes"][0]["next"] = "council"
        validate_encounter(self.spec)
        engine = EncounterEngine(self.spec, [1, 2, 3])
        engine.advance()
        # The minority vote still allocates: 2 votes for soldiers -> 20.
        engine.advance({1: "soldiers", 2: "soldiers", 3: "walls"})
        self.assertEqual(engine.resources["corruption"], 20)
        self.assertEqual(engine.node_id, "guardian")

    def test_effects_scale_by_meters_and_skip_zero_status_stacks(self):
        self.spec["resources"][0]["initial"] = 3
        self.spec["statuses"] = [{"id": "hex", "label": "Hex", "duration": 3, "max_stacks": 5,
                                  "damage_per_round": 0, "heal_per_round": 0, "damage_dealt_pct": 100,
                                  "damage_taken_pct": 100, "stun": False}]
        volley = default_rule("volley")
        volley.update(trigger="round_start", effect="boss_damage", target="enemies", amount=10,
                      scale="corruption", limit=100)
        curse = default_rule("curse")
        curse.update(trigger="round_start", effect="apply_status", target="all", amount=1,
                     status="hex", scale="alive", limit=100)
        self.spec["nodes"][1]["rules"] = [volley, curse]
        engine = EncounterEngine(self.spec, [1, 2])
        engine.advance()
        engine.advance()
        # 30 volley + 2 player strikes of 20.
        self.assertEqual(engine.boss_hp, 300 - 30 - 40)
        self.assertEqual(engine.players["1"].statuses["hex"]["stacks"], 2)
        engine.resources["corruption"] = 0
        before = engine.boss_hp
        engine.advance()
        self.assertEqual(engine.boss_hp, before - 40)

    def test_invalid_scaling_subjects_rejected(self):
        self.spec["actions"][0]["scale"] = "votes:nowhere"
        with self.assertRaises(ValueError):
            validate_encounter(self.spec)
        self.spec["actions"][0]["scale"] = "enemy_hp:boss"
        with self.assertRaises(ValueError):
            validate_encounter(self.spec)


if __name__ == "__main__":
    unittest.main()

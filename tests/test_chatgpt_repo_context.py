import tempfile
import unittest

from pathlib import Path

from cogs.chatgpt import build_repo_context, iter_repo_source_paths, wants_technical_answer


class TestChatGPTRepoContext(unittest.TestCase):
    def test_iter_repo_source_paths_limits_to_supported_locations(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "cogs" / "raidbuilder").mkdir(parents=True)
            (root / "locales").mkdir(parents=True)
            (root / "assets").mkdir(parents=True)

            (root / "README.md").write_text("# Test\n", encoding="utf-8")
            (root / "cogs" / "raidbuilder" / "__init__.py").write_text("pass\n", encoding="utf-8")
            (root / "locales" / "ignored.py").write_text("print('ignored')\n", encoding="utf-8")
            (root / "assets" / "ignored.md").write_text("ignored\n", encoding="utf-8")

            discovered = [
                path.relative_to(root).as_posix()
                for path in iter_repo_source_paths(root)
            ]

            self.assertEqual(
                discovered,
                ["README.md", "cogs/raidbuilder/__init__.py"],
            )

    def test_build_repo_context_prioritizes_relevant_snippets(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "cogs" / "raidbuilder").mkdir(parents=True)
            (root / "utils").mkdir(parents=True)

            (root / "cogs" / "raidbuilder" / "__init__.py").write_text(
                "\n".join(
                    [
                        "class RaidBuilder:",
                        "    async def raidmode_activate(self, ctx, mode, definition_id):",
                        '        """Activate a published raid definition for a mode."""',
                        "        if definition_id is None:",
                        "            return False",
                        "        return True",
                    ]
                ),
                encoding="utf-8",
            )
            (root / "utils" / "misc.py").write_text(
                "\n".join(
                    [
                        "def unrelated_helper():",
                        "    return 'raid tokens are counted here'",
                    ]
                ),
                encoding="utf-8",
            )

            snippets = build_repo_context(
                "How do I activate a raid definition?",
                root,
                max_snippets=2,
                max_context_chars=4000,
            )

            self.assertTrue(snippets)
            self.assertEqual(snippets[0].path, "cogs/raidbuilder/__init__.py")
            self.assertIn("raidmode_activate", snippets[0].text)

    def test_build_repo_context_prefers_runtime_skill_matches_over_tests(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "cogs" / "pets").mkdir(parents=True)
            (root / "cogs" / "battles" / "extensions").mkdir(parents=True)
            (root / "cogs" / "battles" / "core").mkdir(parents=True)
            (root / "cogs" / "slayspire").mkdir(parents=True)
            (root / "tests").mkdir(parents=True)

            (root / "cogs" / "pets" / "__init__.py").write_text(
                "\n".join(
                    [
                        'skill = {"name": "Quick Charge", "description": "Pet gains a major initiative boost."}',
                        'more = "On its first attack each battle, it guarantees Static Shock."',
                    ]
                ),
                encoding="utf-8",
            )
            (root / "cogs" / "battles" / "extensions" / "pets.py").write_text(
                "\n".join(
                    [
                        "def _consume_quick_charge_opener(pet, target):",
                        '    """Resolve Quick Charge opener."""',
                        "    if 'static_shock' in pet.skill_effects:",
                        "        return 'static_shock'",
                        "",
                        "def process_skill_effects_on_attack(pet, target):",
                        "    opener = _consume_quick_charge_opener(pet, target)",
                        "    if opener:",
                        "        return opener",
                        "    return 'none'",
                        "",
                        "def process_skill_effects_per_turn(pet):",
                        "    if getattr(pet, 'quick_charge_active', False):",
                        "        return 'quick_charge_active'",
                        "    return None",
                    ]
                ),
                encoding="utf-8",
            )
            (root / "cogs" / "battles" / "core" / "battle.py").write_text(
                "\n".join(
                    [
                        "def get_turn_priority(combatant):",
                        "    if getattr(combatant, 'quick_charge_active', False):",
                        "        return 999",
                        "    return 0",
                    ]
                ),
                encoding="utf-8",
            )
            (root / "cogs" / "slayspire" / "content.py").write_text(
                "\n".join(
                    [
                        "def attack_bonus_if_enemy_status(value, status, *, bonus):",
                        "    return {'bonus': bonus, 'status': status}",
                    ]
                ),
                encoding="utf-8",
            )
            (root / "tests" / "test_pet_skill_reachability.py").write_text(
                "\n".join(
                    [
                        "def test_contract_flags():",
                        "    contract_flags = {'quick_charge_active'}",
                    ]
                ),
                encoding="utf-8",
            )

            snippets = build_repo_context(
                "What does Quick Charge do?",
                root,
                max_snippets=6,
                max_context_chars=6000,
            )

            self.assertGreaterEqual(len(snippets), 3)
            paths = [snippet.path for snippet in snippets]
            self.assertIn("cogs/pets/__init__.py", paths)
            self.assertIn("cogs/battles/extensions/pets.py", paths)
            self.assertIn("cogs/battles/core/battle.py", paths)
            self.assertNotIn("cogs/slayspire/content.py", paths)
            self.assertTrue(all(not path.startswith("tests/") for path in paths))

    def test_wants_technical_answer_only_for_explicitly_technical_prompts(self):
        self.assertFalse(wants_technical_answer("What does Quick Charge do?"))
        self.assertFalse(wants_technical_answer("Explain this for a player."))
        self.assertTrue(wants_technical_answer("What does Quick Charge do internally?"))
        self.assertTrue(wants_technical_answer("Show the code references for Quick Charge."))

    def test_build_repo_context_follows_called_helper_methods(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "cogs" / "battles").mkdir(parents=True)

            (root / "cogs" / "battles" / "__init__.py").write_text(
                "\n".join(
                    [
                        "class Battles:",
                        "    async def jurytower_score(self, ctx, target):",
                        "        if not self._ensure_jury_tower_dev_access(ctx):",
                        "            return None",
                        '        """Show Jury Tower score breakdown and ranking."""',
                        "        snapshot = {'attack_base': 100, 'hp_base': 250, 'defense_base': 90}",
                        "        score = self._jury_scale_snapshot_score(snapshot)",
                        "        summary = self._jury_rank_summary(score)",
                        "        return summary",
                        "",
                        "    def _ensure_jury_tower_dev_access(self, ctx):",
                        "        return True",
                        "",
                        "    def _jury_scale_snapshot_score(self, snapshot):",
                        "        return snapshot['attack_base'] + snapshot['defense_base'] + (snapshot['hp_base'] * 0.4)",
                        "",
                        "    def _jury_rank_summary(self, power_score):",
                        "        payload = self._jury_bracket_payload_from_score(power_score)",
                        "        return self._jury_render_rank(payload)",
                        "",
                        "    def _jury_bracket_payload_from_score(self, power_score):",
                        "        return self._jury_power_bracket_for_score(power_score)",
                        "",
                        "    def _jury_power_bracket_for_score(self, power_score):",
                        "        if power_score >= 250:",
                        "            return {'bracket_label': 'Iron III'}",
                        "        return {'bracket_label': 'Iron I'}",
                        "",
                        "    def _jury_render_rank(self, payload):",
                        "        return f\"Rank: {payload['bracket_label']}\"",
                    ]
                ),
                encoding="utf-8",
            )
            (root / "cogs" / "battles" / "factory.py").write_text(
                "\n".join(
                    [
                        "def create_jury_tower_battle(ctx, floor_data):",
                        "    return {'jury_tower': True, 'ranking': 'not here', 'score': floor_data.get('score')}",
                    ]
                ),
                encoding="utf-8",
            )

            snippets = build_repo_context(
                "How does Jury Tower ranking work?",
                root,
                max_snippets=4,
                max_context_chars=5000,
            )

            joined_text = "\n".join(snippet.text for snippet in snippets)
            self.assertIn("jurytower_score", joined_text)
            self.assertIn("_jury_scale_snapshot_score", joined_text)
            self.assertIn("_jury_rank_summary", joined_text)
            self.assertIn("_jury_bracket_payload_from_score", joined_text)
            self.assertIn("_jury_power_bracket_for_score", joined_text)
            self.assertIn("_jury_render_rank", joined_text)
            self.assertFalse(
                any(
                    snippet.text.lstrip().startswith("def _ensure_jury_tower_dev_access")
                    for snippet in snippets
                )
            )
            self.assertFalse(any(snippet.path == "cogs/battles/factory.py" for snippet in snippets))


if __name__ == "__main__":
    unittest.main()

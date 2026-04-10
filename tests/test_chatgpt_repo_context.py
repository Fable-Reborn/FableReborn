import tempfile
import unittest

from pathlib import Path
from types import SimpleNamespace

from cogs.chatgpt import (
    _build_query_variants,
    _expand_terms_with_repo_vocabulary,
    _extract_compound_phrases_from_terms,
    _normalize_query_text,
    answer_looks_partial,
    build_repo_context,
    build_system_instructions,
    iter_repo_source_paths,
    join_answer_segments,
    response_hit_output_limit,
    wants_technical_answer,
)


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

    def test_build_repo_context_matches_joined_terms_against_spaced_skill_names(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "cogs" / "pets").mkdir(parents=True)
            (root / "cogs" / "battles" / "extensions").mkdir(parents=True)
            (root / "cogs" / "battles" / "core").mkdir(parents=True)

            (root / "cogs" / "pets" / "__init__.py").write_text(
                '\n'.join(
                    [
                        'skill = {"name": "Quick Charge", "description": "Pet gains a major initiative boost."}',
                        'more = "On its first attack each battle, it guarantees Static Shock."',
                    ]
                ),
                encoding="utf-8",
            )
            (root / "cogs" / "battles" / "extensions" / "pets.py").write_text(
                '\n'.join(
                    [
                        "def _consume_quick_charge_opener(pet, target):",
                        '    """Resolve Quick Charge opener."""',
                        "    return 'static_shock'",
                    ]
                ),
                encoding="utf-8",
            )
            (root / "cogs" / "battles" / "core" / "battle.py").write_text(
                '\n'.join(
                    [
                        "def get_turn_priority(combatant):",
                        "    if getattr(combatant, 'quick_charge_active', False):",
                        "        return 999",
                        "    return 0",
                    ]
                ),
                encoding="utf-8",
            )

            snippets = build_repo_context(
                "What does quickcharge do?",
                root,
                max_snippets=6,
                max_context_chars=6000,
            )

            joined_text = "\n".join(snippet.text for snippet in snippets)
            self.assertIn("Quick Charge", joined_text)
            self.assertTrue(any(snippet.path == "cogs/pets/__init__.py" for snippet in snippets))
            self.assertTrue(any(snippet.path == "cogs/battles/extensions/pets.py" for snippet in snippets))
            self.assertTrue(any(snippet.path == "cogs/battles/core/battle.py" for snippet in snippets))

    def test_expand_terms_with_repo_vocabulary_splits_joined_compound_terms(self):
        expanded = _expand_terms_with_repo_vocabulary(
            ["quickcharge"],
            {"quick", "charge", "quick_charge_active", "consume", "opener"},
        )

        self.assertIn("quick", expanded)
        self.assertIn("charge", expanded)

    def test_extract_compound_phrases_from_terms_builds_spaced_phrase(self):
        phrases = _extract_compound_phrases_from_terms(
            ["quickcharge"],
            {"quick", "charge", "quick_charge_active"},
        )

        self.assertEqual(phrases, ["quick charge"])

    def test_normalize_query_text_recovers_aliases_and_typos(self):
        normalized = _normalize_query_text(
            "what are the jurt tower ranks in jt",
            {"jury", "tower", "rank", "ranks"},
            {"jury tower"},
        )

        self.assertEqual(normalized, "what are the jury tower ranks in jury tower")

    def test_normalize_query_text_does_not_corrupt_common_words(self):
        normalized = _normalize_query_text(
            "what are the jury tower ranks and how are they calculated?",
            {"jury", "tower", "rank", "ranks", "calculate"},
            {"jury tower"},
        )

        self.assertNotIn("they jury tower", normalized or "")
        self.assertNotIn("what are they", normalized or "")

    def test_build_query_variants_skips_low_value_normalization_only_changes(self):
        variants = _build_query_variants(
            "what are the jury tower ranks and how are they calculated?",
            {"jury", "tower", "rank", "ranks", "calculate"},
            {"jury tower"},
        )

        self.assertEqual(
            variants,
            ["what are the jury tower ranks and how are they calculated?"],
        )

    def test_wants_technical_answer_only_for_explicitly_technical_prompts(self):
        self.assertFalse(wants_technical_answer("What does Quick Charge do?"))
        self.assertFalse(wants_technical_answer("Explain this for a player."))
        self.assertTrue(wants_technical_answer("What does Quick Charge do internally?"))
        self.assertTrue(wants_technical_answer("Show the code references for Quick Charge."))

    def test_build_system_instructions_prioritize_direct_player_answers(self):
        instructions = build_system_instructions("what are the ranks in jury tower and their thresholds?")

        self.assertIn("Answer the user's exact question first", instructions)
        self.assertIn("Prefer the minimum detail needed", instructions)
        self.assertIn("Do not add formulas, multipliers, edge cases", instructions)
        self.assertIn("If the user asks a two-part question", instructions)
        self.assertIn("answer the rank list and the calculation", instructions)

    def test_response_hit_output_limit_detects_max_output_token_cutoff(self):
        response = SimpleNamespace(
            status="incomplete",
            incomplete_details=SimpleNamespace(reason="max_output_tokens"),
        )

        self.assertTrue(response_hit_output_limit(response))
        self.assertFalse(
            response_hit_output_limit(
                SimpleNamespace(
                    status="completed",
                    incomplete_details=SimpleNamespace(reason=None),
                )
            )
        )

    def test_answer_looks_partial_detects_insufficient_answer_language(self):
        self.assertTrue(answer_looks_partial("From the snippets you shared, I can only give a partial answer."))
        self.assertFalse(answer_looks_partial("Quick Charge gives a speed boost and opener effect."))

    def test_join_answer_segments_trims_overlap_and_keeps_continuation(self):
        merged = join_answer_segments(
            [
                "Maul Ring IX: up to 18,000\nMaul Ring X: above 18,000",
                "Maul Ring X: above 18,000\nThe score is based on attack, defense, and weighted HP.",
            ]
        )

        self.assertEqual(
            merged,
            "Maul Ring IX: up to 18,000\nMaul Ring X: above 18,000\n\nThe score is based on attack, defense, and weighted HP.",
        )

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

    def test_build_repo_context_follows_imported_constant_definitions(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "cogs" / "battles").mkdir(parents=True)

            (root / "cogs" / "battles" / "__init__.py").write_text(
                "\n".join(
                    [
                        "from .jury_tower_data import JURY_POWER_BRACKETS",
                        "",
                        "class Battles:",
                        "    async def jurytower_score(self, ctx, target):",
                        "        score = self._jury_scale_snapshot_score({'attack_base': 1000, 'hp_base': 2000, 'defense_base': 1000})",
                        "        return self._jury_bracket_payload_from_score(score)",
                        "",
                        "    def _jury_scale_snapshot_score(self, snapshot):",
                        "        return snapshot['attack_base'] + snapshot['defense_base'] + (snapshot['hp_base'] * 0.4)",
                        "",
                        "    def _jury_bracket_payload_from_score(self, power_score):",
                        "        bracket = self._jury_power_bracket_for_score(power_score)",
                        "        return {'bracket_label': bracket['label'], 'power_score': int(power_score)}",
                        "",
                        "    def _jury_power_bracket_for_score(self, power_score):",
                        "        selected = JURY_POWER_BRACKETS[-1]",
                        "        for bracket in JURY_POWER_BRACKETS:",
                        "            if bracket['max_score'] is None or power_score <= bracket['max_score']:",
                        "                selected = bracket",
                        "                break",
                        "        return selected",
                    ]
                ),
                encoding="utf-8",
            )
            (root / "cogs" / "battles" / "jury_tower_data.py").write_text(
                "\n".join(
                    [
                        "JURY_POWER_BRACKETS = (",
                        '    {"key": "court_tier_i", "label": "Maul Ring I", "max_score": 2000},',
                        '    {"key": "court_tier_ii", "label": "Maul Ring II", "max_score": 4000},',
                        '    {"key": "court_tier_x", "label": "Maul Ring X", "max_score": None},',
                        ")",
                    ]
                ),
                encoding="utf-8",
            )

            snippets = build_repo_context(
                "How does Jury Tower ranking work?",
                root,
                max_snippets=6,
                max_context_chars=6000,
            )

            joined_text = "\n".join(snippet.text for snippet in snippets)
            self.assertIn("JURY_POWER_BRACKETS", joined_text)
            self.assertIn("Maul Ring I", joined_text)
            self.assertIn("max_score", joined_text)
            self.assertTrue(any(snippet.path == "cogs/battles/jury_tower_data.py" for snippet in snippets))

    def test_build_repo_context_handles_close_typos_for_jury_tower_ranks(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "cogs" / "battles").mkdir(parents=True)

            (root / "cogs" / "battles" / "__init__.py").write_text(
                "\n".join(
                    [
                        "from .jury_tower_data import JURY_POWER_BRACKETS",
                        "",
                        "class Battles:",
                        "    async def jurytower_help(self, ctx):",
                        "        tier_lines = []",
                        "        for bracket in JURY_POWER_BRACKETS:",
                        "            tier_lines.append(f\"{bracket['label']}: {bracket['max_score']}\")",
                        "        return \"\\n\".join(tier_lines)",
                        "",
                        "    def _jury_power_bracket_for_score(self, power_score):",
                        "        selected = JURY_POWER_BRACKETS[-1]",
                        "        for bracket in JURY_POWER_BRACKETS:",
                        "            if bracket['max_score'] is None or power_score <= bracket['max_score']:",
                        "                selected = bracket",
                        "                break",
                        "        return selected",
                    ]
                ),
                encoding="utf-8",
            )
            (root / "cogs" / "battles" / "jury_tower_data.py").write_text(
                "\n".join(
                    [
                        "JURY_POWER_BRACKETS = (",
                        '    {"label": "Maul Ring I", "max_score": 2000},',
                        '    {"label": "Maul Ring II", "max_score": 4000},',
                        '    {"label": "Maul Ring X", "max_score": None},',
                        ")",
                    ]
                ),
                encoding="utf-8",
            )

            snippets = build_repo_context(
                "what are the ranks in jurt tower and their thresholds?",
                root,
                max_snippets=6,
                max_context_chars=7000,
            )

            joined_text = "\n".join(snippet.text for snippet in snippets)
            self.assertIn("JURY_POWER_BRACKETS", joined_text)
            self.assertIn("Maul Ring I", joined_text)
            self.assertIn("max_score", joined_text)
            self.assertTrue(any(snippet.path == "cogs/battles/jury_tower_data.py" for snippet in snippets))

    def test_build_repo_context_prefers_rank_tables_and_formula_over_wrappers(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "cogs" / "battles").mkdir(parents=True)

            (root / "cogs" / "battles" / "__init__.py").write_text(
                "\n".join(
                    [
                        "from .jury_tower_data import JURY_POWER_BRACKETS",
                        "",
                        "class Battles:",
                        "    async def jurytower_help(self, ctx):",
                        "        embed = discord.Embed(title='Jury Tower Rewards')",
                        "        embed.add_field(name='Ranks', value='See the Jury Tower rank list here.')",
                        "        await ctx.send(embed=embed)",
                        "",
                        "    @is_gm()",
                        "    async def jurytower_score(self, ctx, target):",
                        "        snapshot = {'attack_base': 1200, 'hp_base': 3000, 'defense_base': 900}",
                        "        score = self._jury_scale_snapshot_score(snapshot)",
                        "        return self._jury_bracket_payload_from_score(score)",
                        "",
                        "    def _jury_scale_snapshot_score(self, snapshot):",
                        "        return snapshot['attack_base'] + snapshot['defense_base'] + (snapshot['hp_base'] * 0.4)",
                        "",
                        "    def _jury_bracket_payload_from_score(self, power_score):",
                        "        bracket = self._jury_power_bracket_for_score(power_score)",
                        "        return {'bracket_label': bracket['label'], 'power_score': int(power_score)}",
                        "",
                        "    def _jury_power_bracket_for_score(self, power_score):",
                        "        selected = JURY_POWER_BRACKETS[-1]",
                        "        for bracket in JURY_POWER_BRACKETS:",
                        "            if bracket['max_score'] is None or power_score <= bracket['max_score']:",
                        "                selected = bracket",
                        "                break",
                        "        return selected",
                    ]
                ),
                encoding="utf-8",
            )
            (root / "cogs" / "battles" / "jury_tower_data.py").write_text(
                "\n".join(
                    [
                        "JURY_POWER_BRACKETS = (",
                        '    {"label": "Maul Ring I", "max_score": 2000},',
                        '    {"label": "Maul Ring II", "max_score": 4000},',
                        '    {"label": "Maul Ring X", "max_score": None},',
                        ")",
                    ]
                ),
                encoding="utf-8",
            )
            (root / "cogs" / "battles" / "factory.py").write_text(
                "\n".join(
                    [
                        "def create_jury_tower_battle(ctx, floor_data):",
                        "    return {'jury_tower': True, 'score': floor_data.get('score', 0)}",
                    ]
                ),
                encoding="utf-8",
            )

            snippets = build_repo_context(
                "What are the Jury Tower ranks and how are they calculated?",
                root,
                max_snippets=5,
                max_context_chars=7000,
            )

            self.assertTrue(snippets)
            top_joined_text = "\n".join(snippet.text for snippet in snippets[:3])
            self.assertIn("JURY_POWER_BRACKETS", top_joined_text)
            self.assertIn("_jury_scale_snapshot_score", top_joined_text)
            self.assertNotIn("create_jury_tower_battle", top_joined_text)
            self.assertFalse(snippets[0].text.lstrip().startswith("@is_gm()"))

    def test_build_repo_context_follows_json_backing_data_from_python_usage(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "cogs" / "battles").mkdir(parents=True)

            (root / "cogs" / "battles" / "__init__.py").write_text(
                "\n".join(
                    [
                        "class Battles:",
                        "    def __init__(self):",
                        '        with open("cogs/battles/couples_game_levels.json", "r", encoding="utf-8") as f:',
                        "            self.couples_game_levels = json.load(f)",
                        "",
                        "    async def cbt_preview(self, level):",
                        '        level_info = self.couples_game_levels["levels"][level - 1]',
                        '        return f\"{level_info[\'title\']}: {level_info[\'story\']}\"',
                    ]
                ),
                encoding="utf-8",
            )
            (root / "cogs" / "battles" / "couples_game_levels.json").write_text(
                "\n".join(
                    [
                        "{",
                        '  "levels": [',
                        "    {",
                        '      "level": 6,',
                        '      "title": "The Bridge of Sacrifice",',
                        '      "story": "Shared suffering tests both partners."',
                        "    },",
                        "    {",
                        '      "level": 7,',
                        '      "title": "The Memory Garden",',
                        '      "story": "Memory thieves attack your shared history."',
                        "    }",
                        "  ]",
                        "}",
                    ]
                ),
                encoding="utf-8",
            )

            snippets = build_repo_context(
                "What happens on CBT level 7?",
                root,
                max_snippets=6,
                max_context_chars=7000,
            )

            joined_text = "\n".join(snippet.text for snippet in snippets)
            self.assertIn("Memory Garden", joined_text)
            self.assertIn("Memory thieves", joined_text)
            self.assertTrue(any(snippet.path == "cogs/battles/couples_game_levels.json" for snippet in snippets))

    def test_build_repo_context_prefers_exact_json_level_match(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "cogs" / "battles").mkdir(parents=True)

            (root / "cogs" / "battles" / "__init__.py").write_text(
                "\n".join(
                    [
                        "class Battles:",
                        "    def __init__(self):",
                        '        with open("cogs/battles/couples_game_levels.json", "r", encoding="utf-8") as f:',
                        "            self.couples_game_levels = json.load(f)",
                        "",
                        "    async def cbt_preview(self, level):",
                        '        level_info = self.couples_game_levels["levels"][level - 1]',
                        '        return f\"{level_info[\'title\']}: {level_info[\'story\']}\"',
                    ]
                ),
                encoding="utf-8",
            )
            (root / "cogs" / "battles" / "couples_game_levels.json").write_text(
                "\n".join(
                    [
                        "{",
                        '  "levels": [',
                        "    {",
                        '      "level": 1,',
                        '      "title": "First Steps Together",',
                        '      "story": "An easy intro floor."',
                        "    },",
                        "    {",
                        '      "level": 7,',
                        '      "title": "The Memory Garden",',
                        '      "story": "Memory thieves attack your shared history."',
                        "    }",
                        "  ],",
                        '  "victories": {',
                        '    "7": {"reward": "Moon Pet Shard"}',
                        "  }",
                        "}",
                    ]
                ),
                encoding="utf-8",
            )

            snippets = build_repo_context(
                "What happens on CBT level 7?",
                root,
                max_snippets=4,
                max_context_chars=7000,
            )

            self.assertTrue(snippets)
            self.assertEqual(snippets[0].path, "cogs/battles/couples_game_levels.json")
            self.assertIn("JSON path: levels[7]", snippets[0].text)
            self.assertIn("Memory Garden", snippets[0].text)
            self.assertNotIn("First Steps Together", snippets[0].text)

    def test_build_repo_context_chunks_markdown_by_heading_section(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "cogs" / "alliance").mkdir(parents=True)

            (root / "cogs" / "alliance" / "CITY_WARS_HELP.md").write_text(
                "\n".join(
                    [
                        "# City Wars",
                        "Intro text.",
                        "",
                        "## Units",
                        "- tower: 5,000 HP and 100 retaliation",
                        "- cannon: ranged siege weapon",
                        "",
                        "## Rewards",
                        "Winning cities gain tax bonuses.",
                    ]
                ),
                encoding="utf-8",
            )

            snippets = build_repo_context(
                "How much HP does the tower have in city wars?",
                root,
                max_snippets=4,
                max_context_chars=5000,
            )

            joined_text = "\n".join(snippet.text for snippet in snippets)
            self.assertIn("Markdown section: Units", joined_text)
            self.assertIn("5,000 HP", joined_text)
            self.assertTrue(any(snippet.path == "cogs/alliance/CITY_WARS_HELP.md" for snippet in snippets))

    def test_build_repo_context_chunks_sql_by_statement(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "scripts").mkdir(parents=True)
            (root / "cogs" / "battles").mkdir(parents=True)

            (root / "cogs" / "battles" / "__init__.py").write_text(
                "\n".join(
                    [
                        "class Battles:",
                        "    async def initialize_tables(self, conn):",
                        '        await conn.execute("""',
                        "            CREATE TABLE IF NOT EXISTS jurytower (",
                        "                id BIGINT PRIMARY KEY",
                        "            )",
                        '        """)',
                        '        await conn.execute("ALTER TABLE jurytower ADD COLUMN IF NOT EXISTS scale_power_score BIGINT NOT NULL DEFAULT 0;")',
                    ]
                ),
                encoding="utf-8",
            )

            (root / "scripts" / "schema.sql").write_text(
                "\n".join(
                    [
                        "CREATE TABLE profile (",
                        "    user_id BIGINT PRIMARY KEY,",
                        "    money BIGINT NOT NULL",
                        ");",
                        "",
                        "CREATE TABLE jurytower (",
                        "    id BIGINT PRIMARY KEY,",
                        "    scale_power_score BIGINT NOT NULL,",
                        "    scale_bracket TEXT NOT NULL,",
                        "    prestige INTEGER NOT NULL DEFAULT 0",
                        ");",
                    ]
                ),
                encoding="utf-8",
            )

            snippets = build_repo_context(
                "What columns are in the jurytower table?",
                root,
                max_snippets=4,
                max_context_chars=5000,
            )

            joined_text = "\n".join(snippet.text for snippet in snippets)
            self.assertEqual(snippets[0].path, "scripts/schema.sql")
            self.assertIn("CREATE TABLE jurytower", joined_text)
            self.assertIn("scale_power_score", joined_text)
            self.assertIn("scale_bracket", joined_text)
            self.assertTrue(any(snippet.path == "scripts/schema.sql" for snippet in snippets))


if __name__ == "__main__":
    unittest.main()

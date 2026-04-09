import tempfile
import unittest

from pathlib import Path

from cogs.chatgpt import build_repo_context, iter_repo_source_paths


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
                max_snippets=3,
                max_context_chars=4000,
            )

            self.assertGreaterEqual(len(snippets), 2)
            top_paths = [snippet.path for snippet in snippets[:2]]
            self.assertIn("cogs/pets/__init__.py", top_paths)
            self.assertIn("cogs/battles/extensions/pets.py", top_paths)
            self.assertTrue(all(not path.startswith("tests/") for path in top_paths))


if __name__ == "__main__":
    unittest.main()

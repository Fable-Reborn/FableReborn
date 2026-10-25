import tempfile
import unittest
from pathlib import Path

import tomli

from utils import boot_cogs

SAMPLE = (
    '[bot]\r\n'
    'version = "1.0"\r\n'
    'token = "secret"\r\n'
    'initial_extensions = [\r\n'
    '    "cogs.locale",\r\n'
    '    "cogs.game_master",\r\n'
    '    #"cogs.vote",\r\n'
    '    "cogs.pets",\r\n'
    '    "cogs.pets",\r\n'
    '    # "cogs.halloween",\r\n'
    '    "cogs.quests"\r\n'
    ']\r\n'
    'is_beta = false\r\n'
    '\r\n'
    '[database]\r\n'
    'postgres_password = "hunter2"\r\n'
)


class TestBootCogs(unittest.TestCase):
    def test_reads_the_list_with_switched_off_cogs_and_no_repeats(self):
        entries = boot_cogs.read(SAMPLE)
        self.assertEqual(
            [(e.name, e.enabled) for e in entries],
            [("cogs.locale", True), ("cogs.game_master", True), ("cogs.vote", False),
             ("cogs.pets", True), ("cogs.halloween", False), ("cogs.quests", True)],
        )

    def test_rewrites_only_the_list(self):
        entries = boot_cogs.apply(boot_cogs.read(SAMPLE), {"cogs.vote", "cogs.newthing"}, {"cogs.quests"})
        out = boot_cogs.render(SAMPLE, entries)
        data = tomli.loads(out)
        self.assertEqual(data["bot"]["initial_extensions"],
                         ["cogs.locale", "cogs.game_master", "cogs.vote", "cogs.pets", "cogs.newthing"])
        # Everything outside the list is untouched, line endings included.
        self.assertTrue(out.startswith('[bot]\r\nversion = "1.0"\r\ntoken = "secret"\r\ninitial_extensions = [\r\n'))
        self.assertTrue(out.endswith(']\r\nis_beta = false\r\n\r\n[database]\r\npostgres_password = "hunter2"\r\n'))
        self.assertIn('    #"cogs.quests",\r\n', out)
        self.assertIn('    #"cogs.halloween",\r\n', out)
        self.assertNotIn("\n\n    ", out.replace("\r\n", "\n").split("[database]")[0])

    def test_gm_tools_cannot_be_switched_off(self):
        entries = boot_cogs.apply(boot_cogs.read(SAMPLE), set(), {"cogs.game_master", "cogs.pets"})
        states = {e.name: e.enabled for e in entries}
        self.assertTrue(states["cogs.game_master"])
        self.assertFalse(states["cogs.pets"])

    def test_save_keeps_a_backup_and_writes_atomically(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "config.toml"
            path.write_bytes(SAMPLE.encode("utf-8"))
            backup = boot_cogs.save(path, boot_cogs.apply(boot_cogs.read(SAMPLE), set(), {"cogs.pets"}))
            self.assertEqual(backup.read_bytes(), SAMPLE.encode("utf-8"))
            self.assertEqual(tomli.loads(path.read_text(encoding="utf-8"))["bot"]["initial_extensions"],
                             ["cogs.locale", "cogs.game_master", "cogs.quests"])
            self.assertFalse((Path(folder) / "config.toml.tmp").exists())

    def test_a_broken_list_is_refused(self):
        with self.assertRaises(ValueError):
            boot_cogs.read('[bot]\ninitial_extensions = ["cogs.a", "cogs.b"]\n')
        with self.assertRaises(ValueError):
            boot_cogs.read('[bot]\nversion = "1"\n')

    def test_the_cogs_folder_lists_real_cogs(self):
        names = boot_cogs.available(Path(__file__).resolve().parents[1] / "cogs")
        self.assertIn("cogs.pets", names)
        self.assertIn("cogs.reload", names)
        self.assertNotIn("cogs.__pycache__", names)

    def test_the_real_config_round_trips(self):
        config = Path(__file__).resolve().parents[1] / "config.toml"
        if not config.exists():
            self.skipTest("no config.toml here")
        text = config.read_text(encoding="utf-8")
        before = tomli.loads(text)["bot"]["initial_extensions"]
        entries = boot_cogs.read(text)
        out = boot_cogs.render(text, entries)
        after = tomli.loads(out)["bot"]["initial_extensions"]
        # Same cogs in the same order, only the repeats gone.
        self.assertEqual(after, list(dict.fromkeys(before)))
        self.assertEqual(tomli.loads(out)["database"] if "database" in tomli.loads(text) else None,
                         tomli.loads(text).get("database"))


if __name__ == "__main__":
    unittest.main()

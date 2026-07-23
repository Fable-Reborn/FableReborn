import asyncio
import json
import unittest
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MONSTERS_PATH = PROJECT_ROOT / "monsters.json"
STAGING_PATH = (
    PROJECT_ROOT
    / "cogs"
    / "soulforge_frontiers"
    / "data"
    / "new_monsters_staging.json"
)

BASELINES = {
    "Bloomback Tortoise": (220, 90, 115),
    "Tidereef Kelpie": (260, 220, 230),
    "Galecrest Lynx": (235, 230, 195),
    "Voltscale Pangolin": (230, 225, 215),
    "Cloudray": (430, 410, 370),
    "Arcglass Mantis": (390, 445, 345),
    "Cinderhorn Ram": (420, 420, 360),
    "Dawnveil Moth": (590, 600, 580),
    "Gloamspine Jackal": (600, 595, 555),
    "Riftmolt Scarab": (900, 610, 720),
    "Umbracrown Basilisk": (790, 815, 775),
    "Nullstar Behemoth": (1200, 850, 950),
}


def boosted_stats(values):
    return tuple(
        int(
            (Decimal(value) * Decimal("1.66")).quantize(
                Decimal("1"),
                rounding=ROUND_HALF_UP,
            )
        )
        for value in values
    )


class TestFrontierNewWilds(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        monsters = json.loads(MONSTERS_PATH.read_text(encoding="utf-8"))
        staging = json.loads(STAGING_PATH.read_text(encoding="utf-8"))
        cls.monsters = monsters
        cls.staging = staging

        cls.live = {}
        for tier, rows in monsters.items():
            for row in rows:
                if row.get("name") not in BASELINES:
                    continue
                if row["name"] in cls.live:
                    raise AssertionError(f"duplicate runtime name: {row['name']}")
                cls.live[row["name"]] = (int(tier), row)

        cls.staged = {row["name"]: row for row in staging["monsters"]}
        cls.staging_rows = staging["monsters"]

    def test_all_twelve_runtime_and_staging_records_match(self):
        self.assertEqual(set(BASELINES), set(self.live))
        self.assertEqual(set(BASELINES), set(self.staged))
        self.assertEqual(12, len(self.staging_rows))

        for name, baseline in BASELINES.items():
            tier, live = self.live[name]
            staged = self.staged[name]
            expected = boosted_stats(baseline)
            live_stats = (live["hp"], live["attack"], live["defense"])
            staged_stats = (staged["hp"], staged["attack"], staged["defense"])

            self.assertEqual(expected, live_stats, name)
            self.assertEqual(expected, staged_stats, name)
            self.assertEqual(tier, staged["tier"], name)
            self.assertEqual(live["element"], staged["element"], name)
            self.assertEqual(live["url"], staged["url"], name)
            self.assertTrue(live["ispublic"], name)
            self.assertTrue(live["frontier_only"], name)
            self.assertEqual(staged["region_id"], live["frontier_region_id"], name)
            self.assertTrue(staged["enabled"], name)

        self.assertTrue(self.staging["exclusive_to_frontiers"])

    def test_fractured_verge_has_one_new_wild_per_tier(self):
        fractured = [
            row
            for row in self.staging_rows
            if row["region_id"] == "fractured_verge"
        ]
        self.assertEqual({7, 8, 9, 10}, {row["tier"] for row in fractured})
        self.assertEqual(
            {"Dark", "Corrupted"},
            {row["element"] for row in fractured},
        )
        self.assertTrue(all(row["url"].endswith(".png") for row in fractured))

    def test_normal_pve_excludes_all_frontier_only_wilds(self):
        from cogs.battles import Battles

        async def load_pools():
            battles = object.__new__(Battles)
            battles.monsters_data = self.monsters

            async def no_tier_twelve():
                return None

            battles._get_godofgods_monster_data = no_tier_twelve
            normal = await battles._get_public_monsters_by_level()
            frontier_source = await battles._get_public_monsters_by_level(
                include_frontier_only=True
            )
            return normal, frontier_source

        normal, frontier_source = asyncio.run(load_pools())
        normal_names = {row["name"] for rows in normal.values() for row in rows}
        frontier_names = {
            row["name"] for rows in frontier_source.values() for row in rows
        }
        self.assertTrue(set(BASELINES).isdisjoint(normal_names))
        self.assertTrue(set(BASELINES).issubset(frontier_names))

    def test_each_frontier_receives_only_its_assigned_exclusives(self):
        from cogs.soulforge_frontiers.frontier_pve import (
            build_frontier_pool,
            load_frontier_config,
        )

        config = load_frontier_config()
        public_pool = {
            int(tier): rows for tier, rows in self.monsters.items()
        }
        expected_by_region = {}
        for row in self.staging_rows:
            expected_by_region.setdefault(row["region_id"], set()).add(row["name"])

        for region in config["regions"]:
            build = build_frontier_pool(
                config,
                region["id"],
                public_pool,
                (),
                require_active=False,
            )
            pool_names = {
                row["name"] for rows in build.pool.values() for row in rows
            }
            exclusive_names = pool_names & set(BASELINES)
            self.assertEqual(expected_by_region[region["id"]], exclusive_names)


if __name__ == "__main__":
    unittest.main()

import asyncio
import unittest

import classes.class_mastery as mastery


class _Transaction:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False


class _MasteryConnection:
    def __init__(self, *, points=0, daily_points=0):
        self.points = int(points)
        self.daily_points = int(daily_points)

    def transaction(self):
        return _Transaction()

    async def fetchrow(self, query, *args):
        if "SELECT class FROM profile" in query:
            return {"class": ["Battle Master"]}
        if "SELECT points" in query:
            return {
                "points": self.points,
                "daily_points": self.daily_points,
                "is_today": True,
            }
        raise AssertionError(f"unexpected fetchrow query: {query}")

    async def fetchval(self, query, *args):
        return True

    async def execute(self, query, *args):
        if "SET points = $3" in query:
            self.points = int(args[2])
            self.daily_points = int(args[3])
        return "OK"


class TestClassMasteryCaps(unittest.TestCase):
    def setUp(self):
        self._tables_ready = mastery._TABLES_READY
        mastery._TABLES_READY = True

    def tearDown(self):
        mastery._TABLES_READY = self._tables_ready

    def test_gauntlet_and_ice_dragon_share_the_25_point_cap(self):
        async def exercise_cap():
            conn = _MasteryConnection(daily_points=24)
            gauntlet = await mastery.award_class_mastery(
                object(),
                1,
                2,
                source="gauntlet",
                conn=conn,
            )
            ice_dragon = await mastery.award_class_mastery(
                object(),
                1,
                3,
                source="ice_dragon",
                conn=conn,
            )
            return conn, gauntlet, ice_dragon

        conn, gauntlet, ice_dragon = asyncio.run(exercise_cap())
        self.assertEqual(25, mastery.GAUNTLET_ICE_DRAGON_MASTERY_DAILY_CAP)
        self.assertEqual(1, gauntlet[0]["awarded"])
        self.assertEqual(25, conn.daily_points)
        self.assertEqual([], ice_dragon)

    def test_every_other_source_remains_uncapped(self):
        async def exercise_uncapped_source():
            conn = _MasteryConnection(daily_points=25)
            result = await mastery.award_class_mastery(
                object(),
                1,
                50,
                source="pve",
                conn=conn,
            )
            return conn, result

        conn, result = asyncio.run(exercise_uncapped_source())
        self.assertEqual(50, result[0]["awarded"])
        self.assertEqual(50, conn.points)
        self.assertEqual(25, conn.daily_points)


if __name__ == "__main__":
    unittest.main()

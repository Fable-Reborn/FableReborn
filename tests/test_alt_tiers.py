"""Legendary Hero perks reach the linked alt: sync order and wiring (the SQL needs a real Postgres)."""
from __future__ import annotations

import sys
import types
import unittest
from contextlib import asynccontextmanager

try:  # Optional name generator the bot imports; not needed here.
    import fantasy_names  # noqa: F401
except ImportError:
    sys.modules["fantasy_names"] = types.ModuleType("fantasy_names")

from classes import alt_tiers


class FakeConn:
    def __init__(self):
        self.calls = []
        self.in_transaction = False

    @asynccontextmanager
    async def transaction(self):
        self.in_transaction = True
        yield
        self.in_transaction = False

    async def execute(self, sql, *args):
        self.calls.append(("execute", sql.strip().split()[0], self.in_transaction))

    async def fetch(self, sql, *args):
        self.calls.append(("fetch", sql, self.in_transaction))
        self.assertTier(args)
        if sql is alt_tiers.REVOKE_SQL:
            return [{"user": 7}]
        if sql is alt_tiers.GRANT_SQL:
            return [{"user": 8}, {"user": 9}]
        raise AssertionError(sql)

    @staticmethod
    def assertTier(args):
        assert args == (4,), args


class FakePool:
    def __init__(self, conn):
        self.conn = conn

    @asynccontextmanager
    async def acquire(self):
        yield self.conn


class SyncTests(unittest.IsolatedAsyncioTestCase):
    async def test_revokes_then_grants_under_one_lock(self):
        conn = FakeConn()
        granted, revoked = await alt_tiers.sync_alt_tiers(FakePool(conn))
        self.assertEqual(([8, 9], [7]), (granted, revoked))
        kinds = [c[1] if c[0] == "execute" else c[1] for c in conn.calls]
        self.assertEqual("CREATE", kinds[0])
        self.assertEqual(("execute", "SELECT", True), conn.calls[1])  # advisory lock inside the transaction
        self.assertIs(alt_tiers.REVOKE_SQL, conn.calls[2][1])
        self.assertIs(alt_tiers.GRANT_SQL, conn.calls[3][1])
        self.assertTrue(all(c[2] for c in conn.calls[1:]))

    def test_only_legendary_is_shared(self):
        self.assertEqual(4, alt_tiers.LEGENDARY)
        self.assertIn('COALESCE(m."tier", 0) >= $1', alt_tiers.GRANT_SQL)
        # Revoke only undoes our own grant, never a tier something else set since.
        self.assertIn('COALESCE(p."tier", 0) = $1', alt_tiers.REVOKE_SQL)


class WiringTests(unittest.TestCase):
    def test_alt_cog_runs_the_sync_hourly(self):
        import cogs.alt as alt

        self.assertEqual(1, alt.Alt.legendary_alt_sync.hours)


if __name__ == "__main__":
    unittest.main()

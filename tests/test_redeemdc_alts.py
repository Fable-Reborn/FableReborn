"""$redeemdc: an alt borrowing Legendary from its main redeems only at its own tier."""
from __future__ import annotations

import sys
import types
import unittest
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

try:  # Optional name generator the bot imports; not needed here.
    import fantasy_names  # noqa: F401
except ImportError:
    sys.modules["fantasy_names"] = types.ModuleType("fantasy_names")

import discord

from classes import alt_tiers
from cogs.premiumshop import PremiumShop

USER = 77


class FakePool:
    def __init__(self, *, saved_tier, coins=100, previous_tier=None):
        self.saved_tier = saved_tier
        self.coins = coins
        self.previous_tier = previous_tier
        self.sql = []

    @asynccontextmanager
    async def acquire(self):
        yield self

    async def fetchrow(self, sql, *args):
        return {"tier": self.saved_tier, "dragoncoins": self.coins}

    async def fetchval(self, sql, *args):
        self.sql.append(sql)
        if "alt_tier_grants" in sql:
            return self.previous_tier
        if sql.startswith("UPDATE profile SET dragoncoins"):
            assert "dragoncoins + $1" in sql.replace("COALESCE(dragoncoins, 0)", "dragoncoins")
            self.coins += args[0]
            return self.coins
        raise AssertionError(sql)


def make(*, saved_tier, previous_tier=None, paid_role_tier=0, booster=False):
    pool = FakePool(saved_tier=saved_tier, previous_tier=previous_tier)
    bot = SimpleNamespace(
        pool=pool,
        reset_cooldown=AsyncMock(),
        get_supporter_status=AsyncMock(return_value={"tier": paid_role_tier, "booster": booster}),
        get_effective_donator_tier=AsyncMock(return_value=saved_tier),
    )
    cog = PremiumShop.__new__(PremiumShop)
    cog.bot = bot
    sent = []

    async def send(content=None, **kwargs):
        sent.append(content if content is not None else kwargs.get("embed"))

    ctx = SimpleNamespace(author=SimpleNamespace(id=USER), send=send, clean_prefix="$")
    return cog, ctx, sent, pool


async def run(cog, ctx):
    await PremiumShop.redeemdc.callback(cog, ctx)


class RedeemDcAltTests(unittest.IsolatedAsyncioTestCase):
    async def test_alt_borrowing_legendary_gets_nothing(self):
        cog, ctx, sent, pool = make(saved_tier=4, previous_tier=0)
        await run(cog, ctx)
        self.assertIn("not shared", sent[-1])
        self.assertEqual(100, pool.coins)
        cog.bot.reset_cooldown.assert_awaited_once()

    async def test_alt_redeems_at_what_it_bought_itself(self):
        cog, ctx, sent, pool = make(saved_tier=4, previous_tier=2)
        await run(cog, ctx)
        self.assertEqual(100 + 800, pool.coins)  # its own Warrior tier, not the borrowed 4
        self.assertIsInstance(sent[-1], discord.Embed)

    async def test_alt_that_boosts_on_its_own_gets_tier_one(self):
        cog, ctx, sent, pool = make(saved_tier=4, previous_tier=0, booster=True)
        await run(cog, ctx)
        self.assertEqual(100 + 350, pool.coins)

    async def test_alt_with_its_own_paid_role_uses_it(self):
        cog, ctx, sent, pool = make(saved_tier=4, previous_tier=0, paid_role_tier=3)
        await run(cog, ctx)
        self.assertEqual(100 + 1600, pool.coins)

    async def test_main_and_normal_donors_unchanged(self):
        cog, ctx, sent, pool = make(saved_tier=4)
        await run(cog, ctx)
        self.assertEqual(100 + 3500, pool.coins)
        cog.bot.get_supporter_status.assert_not_awaited()

    async def test_uncapped_tier_counts_as_legendary(self):
        cog, ctx, sent, pool = make(saved_tier=6)
        await run(cog, ctx)
        self.assertEqual(100 + 3500, pool.coins)


class OwnTierTests(unittest.IsolatedAsyncioTestCase):
    async def test_none_when_not_borrowing(self):
        cog, ctx, sent, pool = make(saved_tier=4)
        self.assertIsNone(await alt_tiers.own_tier(cog.bot, USER))


if __name__ == "__main__":
    unittest.main()

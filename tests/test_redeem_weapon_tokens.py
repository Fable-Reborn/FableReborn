"""$redeemweapontokens always replies, counts boosters, and never refunds the cooldown after paying."""
from __future__ import annotations

import sys
import types
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

try:  # Optional name generator the bot imports; not needed here.
    import fantasy_names  # noqa: F401
except ImportError:
    sys.modules["fantasy_names"] = types.ModuleType("fantasy_names")

import discord

from cogs.PatreonCore import PatreonCore

USER = 4242


def forbidden():
    return discord.Forbidden(MagicMock(status=403, reason="Forbidden"), "Missing Permissions")


class FakePool:
    def __init__(self, *, has_profile=True, tokens=10):
        self.has_profile = has_profile
        self.tokens = tokens

    async def fetchval(self, sql, *args):
        if sql.startswith("SELECT 1 FROM profile"):
            return 1 if self.has_profile else None
        if sql.startswith("UPDATE profile"):
            self.tokens += 5
            return self.tokens
        raise AssertionError(sql)


def make(tier=1, *, tier_error=None, has_profile=True, log_channel=None, send_error=None):
    pool = FakePool(has_profile=has_profile)
    bot = SimpleNamespace(pool=pool, reset_cooldown=AsyncMock(), get_channel=lambda _id: log_channel)
    bot.get_effective_donator_tier = AsyncMock(return_value=tier, side_effect=tier_error)
    cog = PatreonCore.__new__(PatreonCore)
    cog.bot = bot
    cog.log_channel_id = 1 if log_channel else None
    sent = []

    async def send(content=None, **kwargs):
        if send_error and "embed" in kwargs:
            raise send_error
        sent.append(content if content is not None else kwargs.get("embed"))

    ctx = SimpleNamespace(
        author=SimpleNamespace(id=USER, mention=f"<@{USER}>", send=AsyncMock()),
        send=send,
        clean_prefix="$",
    )
    return cog, ctx, sent


async def run(cog, ctx):
    await PatreonCore.redeemweapontokens.callback(cog, ctx)


class RedeemTests(unittest.IsolatedAsyncioTestCase):
    async def test_booster_tier_one_gets_tokens(self):
        cog, ctx, sent = make(tier=1)
        await run(cog, ctx)
        self.assertEqual(15, cog.bot.pool.tokens)
        self.assertIsInstance(sent[-1], discord.Embed)
        cog.bot.reset_cooldown.assert_not_awaited()
        cog.bot.get_effective_donator_tier.assert_awaited_once_with(USER, sync_profile=True)

    async def test_non_supporter_is_told_and_keeps_cooldown(self):
        cog, ctx, sent = make(tier=0)
        await run(cog, ctx)
        self.assertIn("server booster", sent[-1])
        self.assertEqual(10, cog.bot.pool.tokens)
        cog.bot.reset_cooldown.assert_awaited_once()

    async def test_lookup_failure_still_replies(self):
        cog, ctx, sent = make(tier_error=forbidden())
        with self.assertLogs("cogs.PatreonCore", level="ERROR"):
            await run(cog, ctx)
        self.assertIn("try again", sent[-1])
        self.assertEqual(10, cog.bot.pool.tokens)
        cog.bot.reset_cooldown.assert_awaited_once()

    async def test_no_character(self):
        cog, ctx, sent = make(has_profile=False)
        await run(cog, ctx)
        self.assertIn("$create", sent[-1])
        cog.bot.get_effective_donator_tier.assert_not_awaited()

    async def test_broken_log_channel_does_not_refund_the_cooldown(self):
        channel = SimpleNamespace(send=AsyncMock(side_effect=forbidden()))
        cog, ctx, sent = make(log_channel=channel)
        await run(cog, ctx)
        self.assertEqual(15, cog.bot.pool.tokens)
        self.assertIsInstance(sent[-1], discord.Embed)
        cog.bot.reset_cooldown.assert_not_awaited()

    async def test_no_embed_permission_falls_back_to_text(self):
        cog, ctx, sent = make(send_error=forbidden())
        await run(cog, ctx)
        self.assertIn("Redeemed **5** weapon tokens", sent[-1])
        cog.bot.reset_cooldown.assert_not_awaited()


class WiringTests(unittest.TestCase):
    def test_singular_spelling_works(self):
        self.assertIn("redeemweapontoken", PatreonCore.redeemweapontokens.aliases)


if __name__ == "__main__":
    unittest.main()

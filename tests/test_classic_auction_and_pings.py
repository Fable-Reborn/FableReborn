import asyncio
import datetime
import re
import sys
import types
import unittest
from pathlib import Path
from unittest import mock

sys.modules.setdefault("fantasy_names", types.ModuleType("fantasy_names"))  # optional dep, not under test

from cogs.game_master import GameMaster  # noqa: E402
from cogs.gm_events import GMEvents, announce  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
ALLOWED_SUBJECTS = set(
    re.findall(r'"([^"]+)"', re.search(r"assert subject in \[(.*?)\]", (ROOT / "classes" / "bot.py").read_text(encoding="utf-8"), re.S).group(1))
)


class FakeConn:
    def __init__(self, bank):
        self.bank = bank

    def transaction(self):
        bank = self.bank

        class Tx:
            async def __aenter__(self_inner):
                self_inner.snapshot = dict(bank.balances)

            async def __aexit__(self_inner, exc_type, exc, tb):
                if exc_type is not None:
                    bank.balances = self_inner.snapshot
                return False

        return Tx()

    async def execute(self, sql, amount, user):
        await asyncio.sleep(0)  # let other tasks interleave, like a real round trip
        balances = self.bank.balances
        if user not in balances:
            return "UPDATE 0"
        if '"money"-$1' in sql:
            if '"money">=$1' in sql and balances[user] < amount:
                return "UPDATE 0"
            balances[user] -= amount
        else:
            balances[user] += amount
        return "UPDATE 1"


class FakeBank:
    def __init__(self, balances):
        self.balances = dict(balances)
        self.logged = []

    def acquire(self):
        conn = FakeConn(self)

        class Ctx:
            async def __aenter__(self_inner):
                return conn

            async def __aexit__(self_inner, *exc):
                return False

        return Ctx()


class FakeChannel:
    def __init__(self):
        self.sent = []

    async def send(self, *args, **kwargs):
        self.sent.append((args, kwargs))


class FakeBot:
    def __init__(self, bank, channel):
        self.pool = bank
        self.channel = channel
        self.config = types.SimpleNamespace(ids=types.SimpleNamespace(game_master={}))

    def get_channel(self, _id):
        return self.channel

    async def log_transaction(self, ctx, from_, to, subject, data, conn=None, command_name=None):
        assert subject in ALLOWED_SUBJECTS, subject  # the real function asserts this too
        self.pool.logged.append(subject)


def make_ctx(user_id):
    sent = []

    async def send(*args, **kwargs):
        sent.append(args[0] if args else "")

    author = types.SimpleNamespace(id=user_id, mention=f"<@{user_id}>", display_name=f"u{user_id}")
    return types.SimpleNamespace(author=author, send=send, sent=sent, clean_prefix="$")


def make_cog(balances):
    bank = FakeBank(balances)
    channel = FakeChannel()
    cog = GameMaster.__new__(GameMaster)
    cog.bot = FakeBot(bank, channel)
    cog.auction_channel_id = 1
    cog.current_item = "Egg"
    cog.top_auction = (None, 0)
    cog.auction_entry = asyncio.Event()
    cog.auction_task = None
    cog._classic_bid_lock = asyncio.Lock()
    cog._classic_last_activity = None
    cog._classic_task_ref = None
    return cog, bank, channel


async def bid(cog, user_id, amount):
    ctx = make_ctx(user_id)
    await GameMaster.bid.callback(cog, ctx, amount)
    return ctx


class ClassicBidTests(unittest.IsolatedAsyncioTestCase):
    async def test_refund_subject_is_accepted_by_log_transaction(self):
        self.assertIn("bid", ALLOWED_SUBJECTS)
        self.assertIn("bid_refund", ALLOWED_SUBJECTS)

    async def test_outbid_refunds_previous_bidder_exactly_once(self):
        cog, bank, _channel = make_cog({1: 1000, 2: 1000})
        await bid(cog, 1, 100)
        ctx = await bid(cog, 2, 200)
        self.assertEqual(bank.balances, {1: 1000, 2: 800})
        self.assertEqual(cog.top_auction[0].id, 2)
        self.assertEqual(cog.top_auction[1], 200)
        self.assertEqual(ctx.sent, ["Bid submitted."])
        self.assertEqual(bank.logged, ["bid", "bid_refund", "bid"])

    async def test_too_poor_changes_nothing(self):
        cog, bank, _channel = make_cog({1: 50})
        ctx = await bid(cog, 1, 100)
        self.assertEqual(ctx.sent, ["You are too poor."])
        self.assertEqual(bank.balances, {1: 50})
        self.assertEqual(cog.top_auction, (None, 0))
        self.assertFalse(cog.auction_entry.is_set())

    async def test_stale_balance_cannot_overdraw(self):
        cog, bank, _channel = make_cog({1: 100, 2: 100})
        await bid(cog, 1, 90)
        await bid(cog, 2, 95)  # 1 is refunded to 100
        await bid(cog, 1, 100)  # needs all of 1's gold
        self.assertTrue(all(v >= 0 for v in bank.balances.values()))

    async def test_concurrent_bids_conserve_gold_and_never_go_negative(self):
        cog, bank, _channel = make_cog({1: 100, 2: 100, 3: 100})
        await asyncio.gather(bid(cog, 1, 80), bid(cog, 2, 90), bid(cog, 3, 95))
        top, amount = cog.top_auction
        self.assertTrue(all(v >= 0 for v in bank.balances.values()))
        self.assertEqual(sum(bank.balances.values()) + amount, 300)  # only the top bid is held

    async def test_cannot_outbid_yourself_or_bid_low(self):
        cog, bank, _channel = make_cog({1: 1000, 2: 1000})
        await bid(cog, 1, 100)
        self.assertEqual((await bid(cog, 1, 200)).sent, ["You cannot outbid yourself."])
        self.assertIn("Bid too low", (await bid(cog, 2, 100)).sent[0])
        self.assertEqual(bank.balances, {1: 900, 2: 1000})

    async def test_failed_log_rolls_back_the_gold(self):
        cog, bank, _channel = make_cog({1: 1000, 2: 1000})
        await bid(cog, 1, 100)
        calls = {"n": 0}
        original = cog.bot.log_transaction

        async def flaky(*args, **kwargs):
            calls["n"] += 1
            if calls["n"] == 2:
                raise RuntimeError("db down")
            return await original(*args, **kwargs)

        cog.bot.log_transaction = flaky
        with self.assertRaises(RuntimeError):
            await bid(cog, 2, 200)
        self.assertEqual(bank.balances, {1: 900, 2: 1000})  # nothing moved
        self.assertEqual(cog.top_auction[0].id, 1)  # state unchanged

    async def test_no_auction(self):
        cog, _bank, _channel = make_cog({1: 100})
        cog.top_auction = None
        self.assertEqual((await bid(cog, 1, 5)).sent, ["No auction running."])

    async def test_end_is_defined_once_and_cleans_up_inside_the_lock(self):
        source = (ROOT / "cogs" / "game_master" / "__init__.py").read_text(encoding="utf-8")
        self.assertEqual(source.count("async def end_auction("), 1)
        cog, bank, channel = make_cog({1: 1000})
        await bid(cog, 1, 100)
        cog.auction_task = asyncio.current_task()
        with mock.patch("cogs.game_master.asyncio.wait_for", side_effect=asyncio.TimeoutError):
            cog.auction_entry.clear()
            await cog.run_auction(channel)
        self.assertIsNone(cog.top_auction)
        self.assertTrue(any("sold to" in str(a) for a, _k in channel.sent))

    async def test_a_bid_that_slips_in_before_the_ending_is_honoured(self):
        cog, bank, channel = make_cog({1: 1000})
        await bid(cog, 1, 100)  # sets the entry event
        calls = {"n": 0}

        async def fake_wait_for(coro, timeout):
            coro.close()
            calls["n"] += 1
            if calls["n"] == 1:
                raise asyncio.TimeoutError  # timer fires although a bid is pending
            raise asyncio.TimeoutError

        cog.auction_task = asyncio.current_task()
        with mock.patch("cogs.game_master.asyncio.wait_for", side_effect=fake_wait_for):
            await cog.run_auction(channel)
        self.assertEqual(calls["n"], 2)  # first timeout saw the pending bid and kept going
        self.assertIsNone(cog.top_auction)


class PingTests(unittest.TestCase):
    def bot(self, **ids):
        return types.SimpleNamespace(config=types.SimpleNamespace(ids=types.SimpleNamespace(game_master=ids)))

    def test_pings_are_off_by_default_and_switchable(self):
        self.assertFalse(announce.pings_enabled(self.bot()))
        self.assertFalse(announce.pings_enabled(self.bot(event_pings_enabled=False)))
        self.assertTrue(announce.pings_enabled(self.bot(event_pings_enabled=True)))

    def test_raffle_uses_the_auction_role_only(self):
        bot = types.SimpleNamespace(
            config=types.SimpleNamespace(
                ids=types.SimpleNamespace(
                    game_master={"auction_ping_role_id": 5, "raffle_ping_role_id": 9}
                )
            )
        )
        cog = GMEvents(bot)
        self.assertEqual((cog.silent_role_id, cog.raffle_role_id), (5, 5))

    def test_status_command_is_locked_to_one_user(self):
        command = GMEvents.eventstatus
        self.assertEqual(len(command.checks), 1)
        check = command.checks[0]
        ok = types.SimpleNamespace(author=types.SimpleNamespace(id=273652235588599808))
        other = types.SimpleNamespace(author=types.SimpleNamespace(id=1))
        self.assertTrue(check(ok))
        self.assertFalse(check(other))


class ClassicStartPingTests(unittest.IsolatedAsyncioTestCase):
    async def run_start(self, enabled):
        cog, _bank, channel = make_cog({})
        cog.top_auction = None
        cog.bot.config.ids.game_master = {"event_pings_enabled": enabled}
        role = types.SimpleNamespace(mention="<@&7>", id=7)
        gm = types.SimpleNamespace(display_name="Gm")
        sent = {}

        async def send(content=None, **kwargs):
            sent.update(content=content, **kwargs)
            return types.SimpleNamespace(jump_url="x")

        channel.send = send

        async def forever(_channel):
            await asyncio.sleep(3600)

        cog.run_auction = forever
        await cog.start_classic_auction(gm=gm, channel=channel, role=role, item="Egg", ping=True)
        cog.auction_task.cancel()
        return sent

    async def test_ping_paused(self):
        sent = await self.run_start(False)
        self.assertIsNone(sent["content"])
        self.assertIs(sent["allowed_mentions"].roles, False)

    async def test_ping_on_when_enabled(self):
        sent = await self.run_start(True)
        self.assertEqual(sent["content"], "<@&7>")
        self.assertEqual(len(sent["allowed_mentions"].roles), 1)


if __name__ == "__main__":
    unittest.main()

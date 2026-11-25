import unittest

import discord

from types import SimpleNamespace

from classes.bot import Bot
from classes.enums import DonatorRank
from utils.checks import user_is_patron


BOOSTER_ROLE_ID = 1404858099268849816
SUPPORT_GUILD_ID = 1402911850802315336


class DummyGuildRole:
    def __init__(self, role_id, name):
        self.id = role_id
        self.name = name


class DummyGuild:
    def __init__(self):
        self.roles = [
            DummyGuildRole(666, "Adventurer"),
            DummyGuildRole(777, "Legendary Hero"),
        ]


class DummyConfigBot:
    _get_patreon_booster_membership_config = Bot._get_patreon_booster_membership_config
    _resolve_donator_rank_from_role_ids = Bot._resolve_donator_rank_from_role_ids
    _coerce_positive_int = staticmethod(Bot._coerce_positive_int)
    _get_numeric_patreon_role_sources = Bot._get_numeric_patreon_role_sources
    _resolve_numeric_patreon_tier_from_role_ids = Bot._resolve_numeric_patreon_tier_from_role_ids

    def __init__(self):
        self.support_server_id = SUPPORT_GUILD_ID
        self.config = SimpleNamespace(
            external=SimpleNamespace(
                donator_roles=[
                    SimpleNamespace(id=111, tier="basic"),
                    SimpleNamespace(id=222, tier="bronze"),
                    SimpleNamespace(id=333, tier="gold"),
                ],
                kofi_donator_roles=[
                    SimpleNamespace(id=444, tier="silver", guild_id=SUPPORT_GUILD_ID),
                    SimpleNamespace(id=555, tier="gold", guild_id=None),
                    SimpleNamespace(id=0, name="Adventurer", tier="basic", guild_id=None),
                    SimpleNamespace(id=0, name="Legendary Hero", tier="gold", guild_id=None),
                ],
            ),
            ids=SimpleNamespace(
                raid={
                    "booster_role_id": BOOSTER_ROLE_ID,
                    "booster_guild_id": SUPPORT_GUILD_ID,
                }
            ),
        )

    def get_guild(self, guild_id):
        return DummyGuild() if guild_id == SUPPORT_GUILD_ID else None


class DummyRankBot:
    def __init__(self, rank):
        self.rank = rank

    async def get_donator_rank(self, _user_id):
        return self.rank

    async def get_effective_donator_tier(self, _user_id, *, sync_profile=False):
        return int(self.rank.value) if self.rank else 0


class DummyUser:
    def __init__(self, user_id=1):
        self.id = user_id


class TestPatreonRankResolution(unittest.TestCase):
    def setUp(self):
        self.bot = DummyConfigBot()

    def test_booster_role_counts_as_basic_rank(self):
        self.assertEqual(
            self.bot._resolve_donator_rank_from_role_ids([BOOSTER_ROLE_ID]),
            DonatorRank.basic,
        )

    def test_real_donator_role_beats_booster_equivalent(self):
        self.assertEqual(
            self.bot._resolve_donator_rank_from_role_ids([BOOSTER_ROLE_ID, 333]),
            DonatorRank.gold,
        )

    def test_kofi_role_counts_toward_numeric_donator_tier(self):
        self.assertEqual(
            self.bot._resolve_numeric_patreon_tier_from_role_ids([444]),
            DonatorRank.silver.value,
        )

    def test_kofi_role_without_guild_defaults_to_support_server(self):
        self.assertEqual(
            self.bot._resolve_numeric_patreon_tier_from_role_ids([555]),
            DonatorRank.gold.value,
        )

    def test_kofi_role_name_counts_toward_numeric_donator_tier(self):
        self.assertEqual(
            self.bot._resolve_numeric_patreon_tier_from_role_ids([777]),
            DonatorRank.gold.value,
        )


class TestUserIsPatron(unittest.IsolatedAsyncioTestCase):
    async def test_basic_rank_satisfies_basic_but_not_bronze(self):
        bot = DummyRankBot(DonatorRank.basic)
        user = DummyUser()

        self.assertTrue(await user_is_patron(bot, user, "basic"))
        self.assertFalse(await user_is_patron(bot, user, "bronze"))


class FakeHTTP:
    """Discord member lookups: one guild refuses, one answers with roles."""

    def __init__(self, answers):
        self.answers = answers
        self.calls = []

    async def get_member(self, guild_id, user_id):
        self.calls.append(guild_id)
        answer = self.answers.get(guild_id)
        if isinstance(answer, Exception):
            raise answer
        if answer is None:
            raise discord.NotFound(SimpleNamespace(status=404, reason="Not Found"), "Unknown Member")
        return {"roles": [str(role) for role in answer]}


class FakePool:
    def __init__(self, tier=0):
        self.tier = tier
        self.saved = None

    async def fetchrow(self, sql, *args):
        return {"tier": self.tier}

    async def execute(self, sql, *args):
        self.saved = args[0]


class LookupBot(DummyConfigBot):
    _fetch_member_for_tier_lookup = Bot._fetch_member_for_tier_lookup
    _get_patreon_tier_lookup_guild_ids = Bot._get_patreon_tier_lookup_guild_ids
    _coerce_user_id = staticmethod(Bot._coerce_user_id)
    get_effective_donator_tier = Bot.get_effective_donator_tier
    get_donator_rank_safe = Bot.get_donator_rank_safe

    def __init__(self, answers, tier=0):
        super().__init__()
        self.http = FakeHTTP(answers)
        self.pool = FakePool(tier)

    async def get_donator_rank(self, user_id):
        return None


REFUSED_GUILD_ID = 999


class TestBoosterLookupSurvivesRefusedGuild(unittest.IsolatedAsyncioTestCase):
    def forbidden(self):
        return discord.Forbidden(SimpleNamespace(status=403, reason="Forbidden"), "Missing Access")

    async def test_booster_gets_tier_one_when_another_guild_refuses(self):
        bot = LookupBot({REFUSED_GUILD_ID: self.forbidden(), SUPPORT_GUILD_ID: [BOOSTER_ROLE_ID]})
        bot._get_patreon_tier_lookup_guild_ids = lambda: [REFUSED_GUILD_ID, SUPPORT_GUILD_ID]
        with self.assertLogs("classes.bot", level="WARNING") as logs:
            tier = await bot.get_effective_donator_tier(1, sync_profile=True)
        self.assertEqual(1, tier)
        self.assertEqual(1, bot.pool.saved)
        self.assertIn(str(REFUSED_GUILD_ID), logs.output[0])
        self.assertTrue(await user_is_patron(bot, DummyUser(), "basic"))

    async def test_refused_guild_is_logged_once(self):
        bot = LookupBot({REFUSED_GUILD_ID: self.forbidden()})
        bot._get_patreon_tier_lookup_guild_ids = lambda: [REFUSED_GUILD_ID]
        with self.assertLogs("classes.bot", level="WARNING") as logs:
            self.assertEqual(0, await bot.get_effective_donator_tier(1))
            self.assertEqual(0, await bot.get_effective_donator_tier(2))
        self.assertEqual(1, len(logs.output))

    async def test_other_discord_errors_are_skipped_too(self):
        error = discord.HTTPException(SimpleNamespace(status=500, reason="Server Error"), "oops")
        bot = LookupBot({REFUSED_GUILD_ID: error, SUPPORT_GUILD_ID: [BOOSTER_ROLE_ID]})
        bot._get_patreon_tier_lookup_guild_ids = lambda: [REFUSED_GUILD_ID, SUPPORT_GUILD_ID]
        with self.assertLogs("classes.bot", level="WARNING"):
            self.assertEqual(1, await bot.get_effective_donator_tier(1))

    async def test_saved_patron_tier_still_wins(self):
        bot = LookupBot({SUPPORT_GUILD_ID: []}, tier=3)
        bot._get_patreon_tier_lookup_guild_ids = lambda: [SUPPORT_GUILD_ID]
        self.assertEqual(3, await bot.get_effective_donator_tier(1))


class TestRefusedRankLookupIsNotCached(unittest.IsolatedAsyncioTestCase):
    async def test_blip_is_not_remembered(self):
        class RankBot(LookupBot):
            get_donator_rank = Bot.get_donator_rank
            get_donator_rank_safe = Bot.get_donator_rank_safe

        forbidden = discord.HTTPException(SimpleNamespace(status=503, reason="Unavailable"), "down")
        bot = RankBot({SUPPORT_GUILD_ID: forbidden})
        with self.assertLogs("classes.bot", level="WARNING"):
            self.assertFalse(await bot.get_donator_rank_safe(42))
        bot.http.answers[SUPPORT_GUILD_ID] = [BOOSTER_ROLE_ID]
        self.assertEqual(DonatorRank.basic, await bot.get_donator_rank_safe(42))


if __name__ == "__main__":
    unittest.main()

import unittest

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
    _coerce_positive_int = Bot._coerce_positive_int
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


if __name__ == "__main__":
    unittest.main()

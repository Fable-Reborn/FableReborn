import unittest

from types import SimpleNamespace

from classes.bot import Bot
from classes.enums import DonatorRank
from utils.checks import user_is_patron


BOOSTER_ROLE_ID = 1404858099268849816
SUPPORT_GUILD_ID = 1402911850802315336


class DummyConfigBot:
    _get_patreon_booster_membership_config = Bot._get_patreon_booster_membership_config
    _resolve_donator_rank_from_role_ids = Bot._resolve_donator_rank_from_role_ids

    def __init__(self):
        self.support_server_id = SUPPORT_GUILD_ID
        self.config = SimpleNamespace(
            external=SimpleNamespace(
                donator_roles=[
                    SimpleNamespace(id=111, tier="basic"),
                    SimpleNamespace(id=222, tier="bronze"),
                    SimpleNamespace(id=333, tier="gold"),
                ]
            ),
            ids=SimpleNamespace(
                raid={
                    "booster_role_id": BOOSTER_ROLE_ID,
                    "booster_guild_id": SUPPORT_GUILD_ID,
                }
            ),
        )


class DummyRankBot:
    def __init__(self, rank):
        self.rank = rank

    async def get_donator_rank(self, _user_id):
        return self.rank


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


class TestUserIsPatron(unittest.IsolatedAsyncioTestCase):
    async def test_basic_rank_satisfies_basic_but_not_bronze(self):
        bot = DummyRankBot(DonatorRank.basic)
        user = DummyUser()

        self.assertTrue(await user_is_patron(bot, user, "basic"))
        self.assertFalse(await user_is_patron(bot, user, "bronze"))


if __name__ == "__main__":
    unittest.main()

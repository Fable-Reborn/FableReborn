"""Hall of Supporters: who is listed, how it is grouped, and Discord's size limits."""
from __future__ import annotations

import datetime as dt
import sys
import types
import unittest

try:  # Optional name generator the bot imports; not needed here.
    import fantasy_names  # noqa: F401
except ImportError:
    sys.modules["fantasy_names"] = types.ModuleType("fantasy_names")

from cogs.supporterboard import collect_from_members, group_tiers
from cogs.supporterboard.board import MAX_EMBEDS, build_board_embeds
from tests.test_patreon_rank_resolution import BOOSTER_ROLE_ID, SUPPORT_GUILD_ID, DummyConfigBot

NOW = dt.datetime(2026, 11, 25, 12, tzinfo=dt.timezone.utc)


def total_chars(embeds) -> int:
    count = 0
    for embed in embeds:
        count += len(embed.title or "") + len(embed.description or "")
        count += len(embed.footer.text or "") if embed.footer else 0
        count += sum(len(f.name) + len(f.value) for f in embed.fields)
    return count


class BoardEmbedTests(unittest.TestCase):
    def test_tiers_high_to_low_then_boosters(self):
        embeds = build_board_embeds({1: [5], 4: [1, 2], 3: [3]}, [9], updated_at=NOW)
        names = [f.name for f in embeds[0].fields]
        self.assertEqual(
            ["✦ Legendary Hero · 2", "✦ Hero · 1", "✦ Adventurer · 1", "💎 Server Boosters · 1"],
            names,
        )
        self.assertEqual("<@1> • <@2>", embeds[0].fields[0].value)
        self.assertIn("**5** supporters", embeds[0].description)
        self.assertEqual(NOW, embeds[-1].timestamp)
        self.assertIn("$supporters hide", embeds[-1].footer.text)

    def test_supporter_count_counts_patron_boosters_once(self):
        embeds = build_board_embeds({2: [1]}, [1, 2], updated_at=NOW)
        self.assertIn("**2** supporters", embeds[0].description)

    def test_empty_board_invites_the_first_supporter(self):
        embeds = build_board_embeds({}, [], prefix="!", updated_at=NOW)
        self.assertEqual(1, len(embeds))
        self.assertIn("`!donate`", embeds[0].fields[0].value)

    def test_huge_lists_stay_inside_discord_limits(self):
        tiers = {tier: list(range(tier * 10**6, tier * 10**6 + 400)) for tier in (1, 2, 3, 4)}
        boosters = list(range(9 * 10**6, 9 * 10**6 + 400))
        embeds = build_board_embeds(tiers, boosters, updated_at=NOW)
        self.assertLessEqual(len(embeds), MAX_EMBEDS)
        self.assertLessEqual(total_chars(embeds), 6000)
        for embed in embeds:
            self.assertLessEqual(len(embed.fields), 25)
            for field in embed.fields:
                self.assertLessEqual(len(field.value), 1024)
        self.assertEqual("…and more", embeds[-1].fields[-1].name)
        self.assertIn("more supporters", embeds[-1].fields[-1].value)

    def test_long_tier_splits_into_continued_fields(self):
        embeds = build_board_embeds({4: list(range(10**17, 10**17 + 60))}, [], updated_at=NOW)
        names = [f.name for e in embeds for f in e.fields]
        self.assertEqual("✦ Legendary Hero · 60", names[0])
        self.assertIn("✦ Legendary Hero (cont.)", names)


class CollectTests(unittest.TestCase):
    def test_roles_give_tiers_and_booster_role_gives_boosters(self):
        bot = DummyConfigBot()
        members = {SUPPORT_GUILD_ID: {1: {333}, 2: {BOOSTER_ROLE_ID}, 3: {111, BOOSTER_ROLE_ID}, 4: set()}}
        tier_of, boosters = collect_from_members(bot, members, {})
        self.assertEqual(4, tier_of[1])  # role 333 is gold
        self.assertNotIn(2, tier_of)  # boosting alone is not a paid tier
        self.assertEqual(1, tier_of[3])
        self.assertEqual({2, 3}, boosters)
        self.assertNotIn(4, tier_of)

    def test_native_boosters_when_no_booster_role_is_set(self):
        bot = DummyConfigBot()
        bot.config.ids.raid = {"booster_guild_id": SUPPORT_GUILD_ID}
        _tiers, boosters = collect_from_members(bot, {SUPPORT_GUILD_ID: {7: set()}}, {SUPPORT_GUILD_ID: {7}})
        self.assertEqual({7}, boosters)

    def test_hidden_players_and_tier_caps(self):
        grouped = group_tiers({1: 4, 2: 7, 3: 2, 4: 0}, hidden={3})
        self.assertEqual({4: [1, 2]}, grouped)


if __name__ == "__main__":
    unittest.main()

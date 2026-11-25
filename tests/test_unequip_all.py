"""$unequipall and the loadout menu's Unequip All button."""
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

import cogs.profile as profile

OWNER = 111


class FakeConn:
    """Worn weapons in `inventory`, worn armor in `equipment_loadout`."""

    def __init__(self, weapons=(), armor=(), others_weapons=(), amulets=()):
        self.weapons = set(weapons)
        self.amulets = set(amulets)
        self.others_weapons = set(others_weapons)
        self.armor = set(armor)
        self.transactions = 0

    @asynccontextmanager
    async def transaction(self):
        self.transactions += 1
        yield

    async def fetch(self, sql, *args):
        if "UPDATE inventory" in sql:
            assert int(args[0]) == OWNER
            taken = [{"item": item} for item in sorted(self.weapons)]
            self.weapons.clear()
            return taken
        if "UPDATE amulets" in sql:
            assert int(args[0]) == OWNER
            taken = [{"id": item} for item in sorted(self.amulets)]
            self.amulets.clear()
            return taken
        if "DELETE FROM equipment_loadout" in sql:
            taken = [{"equipment_id": item} for item in sorted(self.armor)]
            self.armor.clear()
            return taken
        raise AssertionError(f"unexpected fetch: {sql}")


class FakePool:
    def __init__(self, conn):
        self.conn = conn

    @asynccontextmanager
    async def acquire(self):
        yield self.conn


def fake_cog(conn, *, armory_open=True):
    cog = SimpleNamespace(bot=SimpleNamespace(pool=FakePool(conn)))
    cog._armory_open = lambda: armory_open
    cog.unequip_everything = lambda user_id: profile.Profile.unequip_everything(cog, user_id)
    cog.unequip_everything_text = profile.Profile.unequip_everything_text
    return cog


class UnequipEverythingTests(unittest.IsolatedAsyncioTestCase):
    async def test_takes_off_weapons_and_armor_together(self):
        conn = FakeConn(weapons={1, 2}, armor={10, 11, 12}, others_weapons={99}, amulets={7})
        result = await fake_cog(conn).unequip_everything(OWNER)
        self.assertEqual({"weapons": 2, "amulets": 1, "armor": 3}, result)
        self.assertEqual(set(), conn.amulets)
        self.assertEqual(set(), conn.weapons)
        self.assertEqual(set(), conn.armor)
        self.assertEqual({99}, conn.others_weapons)
        self.assertGreaterEqual(conn.transactions, 1)

    async def test_armor_left_alone_when_armory_is_closed(self):
        conn = FakeConn(weapons={1}, armor={10})
        result = await fake_cog(conn, armory_open=False).unequip_everything(OWNER)
        self.assertEqual({"weapons": 1, "amulets": 0, "armor": 0}, result)
        self.assertEqual({10}, conn.armor)

    async def test_nothing_worn(self):
        result = await fake_cog(FakeConn()).unequip_everything(OWNER)
        self.assertEqual({"weapons": 0, "amulets": 0, "armor": 0}, result)

    def test_messages(self):
        text = profile.Profile.unequip_everything_text
        self.assertEqual("You are not wearing anything to take off.", text({"weapons": 0, "armor": 0}))
        self.assertIn("2 weapons/shields and 1 armor piece", text({"weapons": 2, "armor": 1}))
        self.assertIn("1 weapon/shield", text({"weapons": 1, "armor": 0}))
        self.assertIn("4 armor pieces", text({"weapons": 0, "armor": 4}))
        self.assertIn("1 amulet", text({"amulets": 1}))
        self.assertIn(
            "2 weapons/shields, 1 amulet and 3 armor pieces",
            text({"weapons": 2, "amulets": 1, "armor": 3}),
        )


class LoadoutButtonTests(unittest.IsolatedAsyncioTestCase):
    def view(self, cog):
        ctx = SimpleNamespace(author=SimpleNamespace(id=OWNER), alt_invoker_id=None)
        return profile.PresetManagerView(cog, ctx, rows=[], max_slots=6)

    async def test_button_is_in_the_menu_and_always_enabled(self):
        cog = fake_cog(FakeConn())
        cog._split_preset_saved_ids = lambda ids: (list(ids), False, None)
        view = self.view(cog)
        buttons = {child.label: child for child in view.children if isinstance(child, profile.discord.ui.Button)}
        self.assertIn("Unequip All", buttons)
        self.assertFalse(buttons["Unequip All"].disabled)

    async def test_button_unequips_and_replies_privately(self):
        conn = FakeConn(weapons={1}, armor={10}, amulets={5})
        cog = fake_cog(conn)
        cog._split_preset_saved_ids = lambda ids: (list(ids), False, None)
        view = self.view(cog)
        interaction = SimpleNamespace(
            response=SimpleNamespace(defer=AsyncMock()),
            followup=SimpleNamespace(send=AsyncMock()),
        )
        await view.unequip_all(interaction)
        interaction.response.defer.assert_awaited_once_with(ephemeral=True, thinking=True)
        message = interaction.followup.send.await_args.args[0]
        self.assertIn("1 weapon/shield, 1 amulet and 1 armor piece", message)
        self.assertTrue(interaction.followup.send.await_args.kwargs["ephemeral"])
        self.assertEqual(set(), conn.weapons | conn.armor | conn.amulets)

    async def test_button_failure_is_reported(self):
        cog = fake_cog(FakeConn())
        cog._split_preset_saved_ids = lambda ids: (list(ids), False, None)
        cog.unequip_everything = AsyncMock(side_effect=RuntimeError("db down"))
        view = self.view(cog)
        interaction = SimpleNamespace(
            response=SimpleNamespace(defer=AsyncMock()),
            followup=SimpleNamespace(send=AsyncMock()),
        )
        with self.assertLogs(profile._log.name, level="ERROR"):
            await view.unequip_all(interaction)
        self.assertEqual("Unequip All failed. Nothing was changed.", interaction.followup.send.await_args.args[0])


class CommandWiringTests(unittest.TestCase):
    def test_command_and_loadout_aliases(self):
        self.assertEqual("unequipall", profile.Profile.unequipall.name)
        self.assertIn("unequip_all", profile.Profile.unequipall.aliases)
        self.assertIn("loadout", profile.Profile.preset_cmd.aliases)


if __name__ == "__main__":
    unittest.main()

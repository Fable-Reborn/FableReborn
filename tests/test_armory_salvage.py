"""Salvage from the $armory Gear tab action menu.

The menu offers Salvage only for armor, always asks first, is owner-only,
runs once per prompt, and uses the same `salvage_piece` as `$gear salvage`.
"""
from __future__ import annotations

import sys
import types
import unittest
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

try:  # Optional name generator the bot imports; not needed for these tests.
    import fantasy_names  # noqa: F401
except ImportError:
    sys.modules["fantasy_names"] = types.ModuleType("fantasy_names")

import cogs.profile as profile
from classes.equipment.economy import salvage_yield
from classes.equipment.repository import salvage_piece

OWNER = 111
STRANGER = 222


class FakeConn:
    """Just enough of asyncpg for `salvage_piece`."""

    def __init__(self, items=None, listed=(), loadout=()):
        self.items = {int(item["id"]): dict(item) for item in (items or [])}
        self.listed = set(listed)
        self.loadout = set(loadout)
        self.materials: dict[tuple[int, str], int] = {}
        self.events: list[str] = []

    @asynccontextmanager
    async def transaction(self):
        yield

    async def fetchrow(self, sql, *args):
        if "FROM equipment_items" in sql:
            item = self.items.get(int(args[0]))
            if item and int(item["owner_id"]) == int(args[1]):
                return item
            return None
        raise AssertionError(f"unexpected fetchrow: {sql}")

    async def fetchval(self, sql, *args):
        if "FROM equipment_loadout WHERE equipment_id" in sql:
            return 1 if int(args[0]) in self.loadout else None
        if "FROM equipment_market" in sql:
            return 1 if int(args[0]) in self.listed else None
        if "DELETE FROM equipment_items" in sql:
            item = self.items.get(int(args[0]))
            if item and int(item["owner_id"]) == int(args[1]):
                del self.items[int(args[0])]
                return int(args[0])
            return None
        raise AssertionError(f"unexpected fetchval: {sql}")

    async def execute(self, sql, *args):
        if "DELETE FROM equipment_loadout" in sql:
            self.loadout.discard(int(args[0]))
        elif "INSERT INTO equipment_materials" in sql:
            key = (int(args[0]), args[1])
            self.materials[key] = self.materials.get(key, 0) + int(args[2])
        elif "INSERT INTO equipment_events" in sql:
            self.events.append(args[1])
        else:
            raise AssertionError(f"unexpected execute: {sql}")
        return "OK"


class FakePool:
    def __init__(self, conn):
        self.conn = conn

    @asynccontextmanager
    async def acquire(self):
        yield self.conn


def piece(item_id=7, owner=OWNER, **extra):
    row = {
        "id": item_id,
        "owner_id": owner,
        "name": "Razor Helm",
        "slot": "head",
        "rarity": "rare",
        "archetype": "slayer",
        "quality": 60,
        "refinement": 0,
    }
    row.update(extra)
    return row


def armor_menu_item(**extra):
    item = {
        "armory_kind": "armor",
        "armory_key": "armor:7",
        "id": 7,
        "name": "Razor Helm",
        "equipped": False,
        "fully_rolled": False,
        "refinement": 0,
        "rarity": "Rare",
        "archetype": "slayer",
        "slot": "head",
        "value": 60,
    }
    item.update(extra)
    return item


class FakeResponse:
    def __init__(self):
        self.sent = []
        self.edits = []
        self._done = False

    def is_done(self):
        return self._done

    async def send_message(self, content=None, **kwargs):
        self._done = True
        self.sent.append((content, kwargs))

    async def edit_message(self, **kwargs):
        self._done = True
        self.edits.append(kwargs)


class FakeInteraction:
    def __init__(self, user_id=OWNER):
        self.user = SimpleNamespace(id=user_id)
        self.response = FakeResponse()
        self.original_edits = []

    async def edit_original_response(self, **kwargs):
        self.original_edits.append(kwargs)


def fake_armory(conn, *, open_=True):
    """A stand-in for ArmoryPaginatorView with the real salvage methods."""
    cog = SimpleNamespace(available=open_)
    bot = SimpleNamespace(pool=FakePool(conn), get_cog=lambda name: cog if name == "Equipment" else None)
    view = SimpleNamespace(
        ctx=SimpleNamespace(author=SimpleNamespace(id=OWNER), alt_invoker_id=None, bot=bot),
        refresh_from_db=AsyncMock(),
        redraw_message=AsyncMock(),
    )
    view._equipment_open = lambda: profile.ArmoryPaginatorView._equipment_open(view)
    view.salvage_armor = lambda item_id: profile.ArmoryPaginatorView.salvage_armor(view, item_id)
    return view


class SalvageRepositoryTests(unittest.IsolatedAsyncioTestCase):
    async def test_worn_piece_is_refused_and_kept(self):
        conn = FakeConn(items=[piece()], loadout={7})
        self.assertEqual(("equipped", None), await salvage_piece(conn, OWNER, 7))
        self.assertIn(7, conn.items)
        self.assertIn(7, conn.loadout)
        self.assertEqual({}, conn.materials)

    async def test_salvage_destroys_piece_and_pays_materials(self):
        conn = FakeConn(items=[piece()])
        status, result = await salvage_piece(conn, OWNER, 7)
        self.assertEqual("salvaged", status)
        expected = salvage_yield("rare", "slayer", 60)
        self.assertTrue(expected)
        self.assertEqual(expected, result["materials"])
        self.assertNotIn(7, conn.items)
        self.assertEqual({(OWNER, k): v for k, v in expected.items()}, conn.materials)
        self.assertEqual(["salvage"], conn.events)

    async def test_second_salvage_of_same_piece_pays_nothing(self):
        conn = FakeConn(items=[piece()])
        await salvage_piece(conn, OWNER, 7)
        paid = dict(conn.materials)
        status, result = await salvage_piece(conn, OWNER, 7)
        self.assertEqual(("missing", None), (status, result))
        self.assertEqual(paid, conn.materials)

    async def test_cannot_salvage_someone_elses_or_a_listed_piece(self):
        conn = FakeConn(items=[piece(owner=STRANGER), piece(item_id=8)], listed={8})
        self.assertEqual("missing", (await salvage_piece(conn, OWNER, 7))[0])
        self.assertEqual("listed", (await salvage_piece(conn, OWNER, 8))[0])
        self.assertIn(7, conn.items)
        self.assertIn(8, conn.items)
        self.assertEqual({}, conn.materials)


class SalvageMenuTests(unittest.IsolatedAsyncioTestCase):
    def options(self, item, catalog="armor"):
        view = SimpleNamespace(selected_item=lambda: item, catalog=catalog)
        return [option.value for option in profile.ArmoryActionSelect(view).options]

    async def test_salvage_only_offered_for_armor(self):
        self.assertIn("salvage", self.options(armor_menu_item()))
        weapon = {"id": 3, "armory_key": "weapon:3", "name": "Sword", "equipped": False}
        self.assertNotIn("salvage", self.options(weapon, catalog="weapons"))

    def test_prompt_warns_about_what_is_lost(self):
        plain = profile.armory_salvage_prompt(armor_menu_item(), "stuff")
        self.assertIn("cannot be undone", plain)
        self.assertNotIn("wearing", plain)
        self.assertNotIn("temper", plain)
        risky = profile.armory_salvage_prompt(
            armor_menu_item(refinement=3, fully_rolled=True), "stuff"
        )
        self.assertIn("+3 temper is lost", risky)
        self.assertIn("fully rolled discovery", risky)

    async def test_menu_opens_a_confirmation_and_destroys_nothing_yet(self):
        conn = FakeConn(items=[piece()])
        armory = fake_armory(conn)
        click = FakeInteraction()
        await profile.ArmoryPaginatorView.handle_armor_action(armory, click, armor_menu_item(), "salvage")
        content, kwargs = click.response.sent[0]
        self.assertIn("Salvage Razor Helm", content)
        self.assertTrue(kwargs["ephemeral"])
        self.assertIsInstance(kwargs["view"], profile.ArmorySalvageConfirmView)
        self.assertIn(7, conn.items)

    async def test_closed_armory_refuses_without_prompt(self):
        conn = FakeConn(items=[piece()])
        armory = fake_armory(conn, open_=False)
        click = FakeInteraction()
        await profile.ArmoryPaginatorView.handle_armor_action(armory, click, armor_menu_item(), "salvage")
        content, kwargs = click.response.sent[0]
        self.assertIn("closed", content)
        self.assertNotIn("view", kwargs)
        self.assertIn("closed", await armory.salvage_armor(7))
        self.assertIn(7, conn.items)

    async def test_confirm_salvages_once_and_refreshes(self):
        conn = FakeConn(items=[piece()])
        armory = fake_armory(conn)
        confirm = profile.ArmorySalvageConfirmView(armory, 7)
        first = FakeInteraction()
        await confirm.confirm.callback(first)
        self.assertEqual([{"content": "Salvaging…", "view": None}], first.response.edits)
        self.assertIn("You break down **Razor Helm**", first.original_edits[-1]["content"])
        self.assertNotIn(7, conn.items)
        armory.refresh_from_db.assert_awaited_once()
        armory.redraw_message.assert_awaited_once()
        paid = dict(conn.materials)

        second = FakeInteraction()
        await confirm.confirm.callback(second)
        self.assertEqual("Already handled.", second.response.sent[0][0])
        self.assertEqual(paid, conn.materials)

    async def test_cancel_keeps_the_piece(self):
        conn = FakeConn(items=[piece()])
        confirm = profile.ArmorySalvageConfirmView(fake_armory(conn), 7)
        click = FakeInteraction()
        await confirm.cancel.callback(click)
        self.assertEqual("Salvage cancelled.", click.response.edits[0]["content"])
        await confirm.confirm.callback(FakeInteraction())
        self.assertIn(7, conn.items)
        self.assertEqual({}, conn.materials)

    async def test_stranger_cannot_press_salvage(self):
        conn = FakeConn(items=[piece()])
        confirm = profile.ArmorySalvageConfirmView(fake_armory(conn), 7)
        stranger = FakeInteraction(STRANGER)
        self.assertFalse(await confirm.interaction_check(stranger))
        self.assertEqual("This confirmation is not yours.", stranger.response.sent[0][0])
        self.assertTrue(await confirm.interaction_check(FakeInteraction(OWNER)))

    async def test_piece_gone_since_prompt_reports_missing(self):
        conn = FakeConn(items=[])
        confirm = profile.ArmorySalvageConfirmView(fake_armory(conn), 7)
        click = FakeInteraction()
        await confirm.confirm.callback(click)
        self.assertIn("no longer own", click.original_edits[-1]["content"])

    async def test_listed_piece_is_refused_at_confirm_time(self):
        conn = FakeConn(items=[piece()], listed={7})
        confirm = profile.ArmorySalvageConfirmView(fake_armory(conn), 7)
        click = FakeInteraction()
        await confirm.confirm.callback(click)
        self.assertIn("gear shop", click.original_edits[-1]["content"])
        self.assertIn(7, conn.items)

    async def test_database_error_reports_failure(self):
        conn = FakeConn(items=[piece()])
        conn.fetchrow = AsyncMock(side_effect=RuntimeError("db down"))
        confirm = profile.ArmorySalvageConfirmView(fake_armory(conn), 7)
        click = FakeInteraction()
        with self.assertLogs(profile._log.name, level="ERROR"):
            await confirm.confirm.callback(click)
        self.assertEqual("Salvage failed. Nothing was changed.", click.original_edits[-1]["content"])


if __name__ == "__main__":
    unittest.main()

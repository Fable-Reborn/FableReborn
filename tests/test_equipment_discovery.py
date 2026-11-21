"""Armor discovery is per piece: slot + line + rarity."""
import asyncio
import random
import unittest
from contextlib import asynccontextmanager

from classes.equipment.economy import STARTER_RECIPES, craft_cost, extra_discovery_keys, recipe_key
from classes.equipment.generation import RolledPiece
from classes.equipment.repository import (
    SCHEMA_STATEMENTS,
    craft_chest,
    create_piece,
    record_discovery,
)


class FakeConn:
    """Just enough of asyncpg for discovery, crafting, and piece inserts."""

    def __init__(self):
        self.discoveries: set[tuple[int, str]] = set()
        self.materials: dict[tuple[int, str], int] = {}
        self.items: list[dict] = []

    @asynccontextmanager
    async def transaction(self):
        yield

    async def execute(self, sql, *args):
        if "INSERT INTO equipment_discoveries" in sql:
            user_id, key = args
            self.discoveries.add((int(user_id), key))
        return "OK"

    async def fetchval(self, sql, *args):
        if "FROM equipment_discoveries" in sql:
            return 1 if (int(args[0]), args[1]) in self.discoveries else None
        if "UPDATE equipment_materials" in sql:
            user_id, material_id, amount = args
            have = self.materials.get((user_id, material_id), 0)
            if have < amount:
                return None
            self.materials[(user_id, material_id)] = have - amount
            return have - amount
        if "FROM equipment_materials" in sql:
            return self.materials.get((int(args[0]), args[1]))
        raise AssertionError(f"unexpected fetchval: {sql}")

    async def fetchrow(self, sql, *args):
        if "INSERT INTO equipment_items" in sql:
            row = {
                "id": len(self.items) + 1,
                "owner_id": args[0],
                "slot": args[1],
                "rarity": args[2],
                "archetype": args[3],
                "quality": args[4],
                "origin": args[9],
                "name": args[10],
            }
            self.items.append(row)
            return row
        raise AssertionError(f"unexpected fetchrow: {sql}")

    def keys(self, user_id):
        return {key for uid, key in self.discoveries if uid == user_id}


def run(coro):
    return asyncio.run(coro)


USER = 42


class DiscoveryTests(unittest.TestCase):
    def fund(self, conn, rarity, archetype):
        for material_id, amount in craft_cost(rarity, archetype).items():
            conn.materials[(USER, material_id)] = amount * 10

    def test_helm_find_teaches_only_the_helm(self):
        conn = FakeConn()
        piece = RolledPiece(rarity="legendary", archetype="slayer", quality=90, fully_rolled=True, slot="head")
        run(create_piece(conn, USER, piece, origin="legendary_discovery"))
        self.assertEqual({"head:slayer:legendary"}, conn.keys(USER))
        for slot in ("chest", "legs", "feet"):
            self.assertNotIn(recipe_key("slayer", "legendary", slot), conn.keys(USER))

    def test_crate_find_teaches_its_own_slot(self):
        conn = FakeConn()
        piece = RolledPiece(rarity="rare", archetype="guardian", quality=50, fully_rolled=False, slot="feet")
        run(create_piece(conn, USER, piece, origin="crate"))
        self.assertEqual({"feet:guardian:rare"}, conn.keys(USER))

    def test_common_finds_and_bad_slots_add_nothing(self):
        conn = FakeConn()
        run(record_discovery(conn, USER, "vanguard", "common", piece_slot="legs"))
        run(record_discovery(conn, USER, "vanguard", "rare", piece_slot="belt"))
        run(record_discovery(conn, USER, "vanguard", "rare", piece_slot=""))
        self.assertEqual(set(), conn.keys(USER))

    def test_starters_craft_without_discovery_rows(self):
        self.assertEqual(12, len(STARTER_RECIPES))
        for key in STARTER_RECIPES:
            slot, archetype, rarity = key.split(":")
            conn = FakeConn()
            self.fund(conn, rarity, archetype)
            status, item = run(craft_chest(conn, USER, rarity, archetype, rng=random.Random(1), slot=slot))
            self.assertEqual("crafted", status, key)
            self.assertEqual(slot, item["slot"])
            self.assertEqual(set(), conn.keys(USER))

    def test_sibling_slot_is_unknown_after_a_helm_find(self):
        conn = FakeConn()
        self.fund(conn, "legendary", "slayer")
        piece = RolledPiece(rarity="legendary", archetype="slayer", quality=90, fully_rolled=True, slot="head")
        run(create_piece(conn, USER, piece, origin="legendary_discovery"))
        before = dict(conn.materials)
        for slot in ("chest", "legs", "feet"):
            status, item = run(craft_chest(conn, USER, "legendary", "slayer", rng=random.Random(1), slot=slot))
            self.assertEqual("unknown", status, slot)
            self.assertIsNone(item)
        # The default slot is the cuirass, which is also unknown.
        status, _ = run(craft_chest(conn, USER, "legendary", "slayer", rng=random.Random(1)))
        self.assertEqual("unknown", status)
        self.assertEqual(before, conn.materials)
        status, item = run(craft_chest(conn, USER, "legendary", "slayer", rng=random.Random(1), slot="head"))
        self.assertEqual("crafted", status)
        self.assertEqual("head", item["slot"])

    def test_crafting_never_teaches(self):
        conn = FakeConn()
        conn.discoveries.add((USER, "head:slayer:rare"))
        self.fund(conn, "rare", "slayer")
        status, _ = run(craft_chest(conn, USER, "rare", "slayer", rng=random.Random(1), slot="head"))
        self.assertEqual("crafted", status)
        self.assertEqual({"head:slayer:rare"}, conn.keys(USER))
        conn2 = FakeConn()
        piece = RolledPiece(rarity="magic", archetype="vanguard", quality=40, fully_rolled=False, slot="legs")
        run(create_piece(conn2, USER, piece, origin="craft"))
        self.assertEqual(set(), conn2.keys(USER))

    def test_extra_discovery_keys_keep_finds_drop_siblings(self):
        stored = {
            "head:slayer:legendary",
            "chest:slayer:legendary",
            "legs:slayer:legendary",
            "feet:slayer:legendary",
            "chest:guardian:common",
        }
        found = {"head:slayer:legendary"}
        extras = extra_discovery_keys(stored, found)
        self.assertEqual(
            {"chest:slayer:legendary", "legs:slayer:legendary", "feet:slayer:legendary"},
            extras,
        )
        self.assertNotIn("head:slayer:legendary", extras)
        self.assertNotIn("chest:guardian:common", extras)

    def test_schema_never_fans_discoveries_out(self):
        for statement in SCHEMA_STATEMENTS:
            if "equipment_discoveries" in statement:
                self.assertNotIn("INSERT INTO", statement.upper())
                self.assertNotIn("CROSS JOIN", statement.upper())


if __name__ == "__main__":
    unittest.main()

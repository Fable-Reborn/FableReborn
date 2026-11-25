"""In-memory stand-in for the armor tables, just enough for repository tests.

Every query the lock, salvage, list, give, and buy paths send is matched by
a substring. An unexpected query fails the test, so new SQL cannot slip by.
"""
from __future__ import annotations

import sys
import types
from contextlib import asynccontextmanager

try:  # Optional name generator the bot imports; not needed for tests.
    import fantasy_names  # noqa: F401
except ImportError:
    sys.modules["fantasy_names"] = types.ModuleType("fantasy_names")


def piece(item_id=7, owner=111, **extra):
    row = {
        "id": item_id,
        "owner_id": owner,
        "name": f"Razor Helm {item_id}",
        "slot": "head",
        "rarity": "rare",
        "archetype": "slayer",
        "quality": 60,
        "refinement": 0,
        "bound": False,
        "fully_rolled": False,
        "modification_state": "pristine",
        "locked": False,
    }
    row.update(extra)
    return row


class FakeArmoryDB:
    def __init__(self, items=(), *, worn=(), market=None, money=None):
        self.items = {int(item["id"]): dict(item) for item in items}
        self.worn = set(worn)
        self.market = dict(market or {})  # equipment_id -> (seller_id, price)
        self.money = dict(money or {})
        self.materials: dict[tuple[int, str], int] = {}
        self.events: list[str] = []

    @asynccontextmanager
    async def transaction(self):
        yield

    def _owned(self, item_id, owner):
        item = self.items.get(int(item_id))
        if item and (owner is None or int(item["owner_id"]) == int(owner)):
            return item
        return None

    async def fetchrow(self, sql, *args):
        if "FROM equipment_market m" in sql:
            entry = self.market.get(int(args[0]))
            item = self.items.get(int(args[0]))
            if entry is None or item is None:
                return None
            return {**item, "seller_id": entry[0], "price": entry[1]}
        if "FROM equipment_items" in sql:
            item = self._owned(args[0], args[1] if len(args) > 1 else None)
            return dict(item) if item else None
        raise AssertionError(f"unexpected fetchrow: {sql}")

    async def fetchval(self, sql, *args):
        if "FROM equipment_loadout WHERE equipment_id" in sql:
            return 1 if int(args[0]) in self.worn else None
        if "FROM equipment_market WHERE equipment_id" in sql:
            return 1 if int(args[0]) in self.market else None
        if "DELETE FROM equipment_items" in sql:
            if self._owned(args[0], args[1]):
                del self.items[int(args[0])]
                return int(args[0])
            return None
        if "UPDATE profile" in sql and "money - $1" in sql:
            price, user = int(args[0]), int(args[1])
            if self.money.get(user, 0) < price:
                return None
            self.money[user] -= price
            return self.money[user]
        raise AssertionError(f"unexpected fetchval: {sql}")

    async def fetch(self, sql, *args):
        if "FROM equipment_items" in sql and "DELETE" not in sql:
            ids, owner = [int(v) for v in args[0]], int(args[1])
            return [dict(self.items[i]) for i in sorted(ids) if self._owned(i, owner)]
        if "FROM equipment_loadout" in sql:
            return [{"equipment_id": i} for i in args[0] if int(i) in self.worn]
        if "FROM equipment_market" in sql:
            return [{"equipment_id": i} for i in args[0] if int(i) in self.market]
        if "DELETE FROM equipment_items" in sql:
            gone = []
            for i in args[0]:
                if self._owned(i, args[1]):
                    del self.items[int(i)]
                    gone.append({"id": int(i)})
            return gone
        raise AssertionError(f"unexpected fetch: {sql}")

    async def execute(self, sql, *args):
        if "INSERT INTO equipment_events" in sql:
            self.events.append(args[1])
        elif "INSERT INTO equipment_materials" in sql:
            key = (int(args[0]), args[1])
            self.materials[key] = self.materials.get(key, 0) + int(args[2])
        elif "UPDATE equipment_items SET locked" in sql:
            self.items[int(args[0])]["locked"] = bool(args[1])
        elif "INSERT INTO equipment_market" in sql:
            self.market[int(args[0])] = (int(args[1]), int(args[2]))
        elif "DELETE FROM equipment_market" in sql:
            self.market.pop(int(args[0]), None)
        elif "SET owner_id" in sql:
            self.items[int(args[0])]["owner_id"] = int(args[1])
        elif "UPDATE profile SET money = money + $1" in sql:
            self.money[int(args[1])] = self.money.get(int(args[1]), 0) + int(args[0])
        else:
            raise AssertionError(f"unexpected execute: {sql}")
        return "OK"


class FakePool:
    def __init__(self, conn):
        self.conn = conn

    @asynccontextmanager
    async def acquire(self):
        yield self.conn

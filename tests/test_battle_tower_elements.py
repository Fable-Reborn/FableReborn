"""Battle Tower floor elements: one per floor, rolled per prestige, gods fixed on 30."""

import ast
import asyncio
from contextlib import asynccontextmanager
import json
import random
from pathlib import Path
from types import SimpleNamespace

from utils.elements import ELEMENT_STRENGTHS

ROOT = Path(__file__).resolve().parents[1]
BATTLES = ROOT / "cogs/battles"
METHODS = {"_roll_tower_floor_elements", "_valid_tower_floor_elements", "_tower_floor_elements",
           "_apply_tower_floor_element", "_tower_floor_element_label"}
CONSTANTS = {"TOWER_ELEMENT_FLOORS", "TOWER_FLOOR_ELEMENT_POOL", "TOWER_FINAL_FLOOR_ELEMENTS"}
EMOJI = {"Light": "🌟", "Dark": "🌑", "Corrupted": "🌀", "Nature": "🌿", "Electric": "⚡",
         "Water": "💧", "Fire": "🔥", "Wind": "💨", "Earth": "🌍", "Unknown": "❓"}


class Pool:
    """battletower row store honouring the conditional regenerate UPDATE."""

    def __init__(self, rows):
        self.rows, self.rolls = rows, 0

    @asynccontextmanager
    async def acquire(self):
        yield self

    async def fetchrow(self, sql, user_id):
        row = self.rows.get(user_id)
        return None if row is None else dict(row)

    async def fetchval(self, sql, user_id):
        return self.rows[user_id]["floor_elements"]

    async def execute(self, sql, elements, prestige, user_id, floors):
        row = self.rows[user_id]
        current = row["floor_elements"]
        if row["floor_elements_prestige"] != prestige or current is None or len(current) != floors:
            row.update(floor_elements=list(elements), floor_elements_prestige=prestige)
            self.rolls += 1


def tower(rows=None):
    tree = ast.parse((BATTLES / "__init__.py").read_text(encoding="utf-8"))
    battles = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "Battles")
    constants = [node for node in battles.body if isinstance(node, ast.Assign)
                 and any(getattr(t, "id", "") in CONSTANTS for t in node.targets)]
    methods = [node for node in battles.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
               and node.name in METHODS]
    assert {m.name for m in methods} == METHODS
    battles.body, battles.bases, battles.decorator_list = constants + methods, [], []
    namespace = {"ELEMENT_STRENGTHS": ELEMENT_STRENGTHS, "random": random}
    exec(compile(ast.Module(body=[battles], type_ignores=[]), "battles", "exec"), namespace)
    instance = namespace["Battles"]()
    instance.bot = SimpleNamespace(pool=Pool(rows or {}))
    instance.element_ext = SimpleNamespace(element_to_emoji=EMOJI)
    return instance


def row(prestige=0, elements=None, rolled_for=None):
    return {"prestige": prestige, "floor_elements": elements, "floor_elements_prestige": rolled_for}


LEVEL = {"minion1_name": "Imp", "minion2_name": "Shadow Spirit", "boss_name": "Abyssal Guardian",
         "minion1": {"hp": 65}, "minion2": {"hp": 75}, "boss": {"hp": 150}}


def test_pool_is_every_real_combat_element():
    t = tower()
    assert set(t.TOWER_FLOOR_ELEMENT_POOL) == set(ELEMENT_STRENGTHS) - {"Unknown"}
    rolled = t._roll_tower_floor_elements(random.Random(1))
    assert len(rolled) == 29 and t._valid_tower_floor_elements(rolled)


def test_existing_runs_are_generated_once_and_then_stable():
    t = tower({1: row(prestige=4)})  # a run that predates floor elements
    first = asyncio.run(t._tower_floor_elements(1))
    assert t._valid_tower_floor_elements(first)
    assert t.bot.pool.rows[1]["floor_elements_prestige"] == 4
    assert asyncio.run(t._tower_floor_elements(1)) == first
    assert t.bot.pool.rolls == 1


def test_prestige_rerolls_and_bad_data_is_repaired():
    stale = ["Fire"] * 29
    t = tower({1: row(prestige=3, elements=stale, rolled_for=2), 2: row(prestige=1, elements=["Fire"] * 5, rolled_for=1)})
    random.seed(7)
    fresh = asyncio.run(t._tower_floor_elements(1))
    assert t.bot.pool.rows[1]["floor_elements_prestige"] == 3 and fresh != stale
    assert len(asyncio.run(t._tower_floor_elements(2))) == 29
    assert asyncio.run(t._tower_floor_elements(99)) is None


def test_concurrent_first_use_agrees_on_one_roll():
    t = tower({1: row(prestige=0)})

    async def race():
        return await asyncio.gather(*(t._tower_floor_elements(1) for _ in range(5)))

    results = asyncio.run(race())
    assert all(result == results[0] for result in results)
    assert t.bot.pool.rolls == 1


def test_floor_element_governs_every_enemy_without_mutating_source():
    t = tower()
    elements = ["Water"] * 29
    elements[6] = "Fire"
    governed = t._apply_tower_floor_element(LEVEL, 7, elements)
    assert {governed[s]["element"] for s in ("minion1", "minion2", "boss")} == {"Fire"}
    assert "element" not in LEVEL["boss"]
    assert governed["boss_name"] == "Abyssal Guardian"


def test_summit_gods_always_use_their_own_elements():
    t = tower()
    summit = {"minion1_name": "Elysia", "minion2_name": "Sepulchure", "boss_name": "Drakath",
              "minion1": {}, "minion2": {}, "boss": {}}
    for elements in (["Fire"] * 29, None):
        governed = t._apply_tower_floor_element(summit, 30, elements)
        assert (governed["minion1"]["element"], governed["minion2"]["element"], governed["boss"]["element"]) == \
            ("Light", "Dark", "Corrupted")
    assert t._tower_floor_element_label(30, None) == ("🌟🌑🌀", "Gods")


def test_levels_json_summit_is_the_three_gods():
    level = json.loads((BATTLES / "game_levels.json").read_text(encoding="utf-8"))["levels"]["30"]
    assert (level["minion1_name"], level["minion2_name"], level["boss_name"]) == ("Elysia", "Sepulchure", "Drakath")


def test_progress_fields_fit_discord_limit_with_longest_elements():
    t = tower()
    names = json.loads((BATTLES / "battle_tower_data_remastered.json").read_text(encoding="utf-8"))["level_names"]
    widest = ["Corrupted"] * 29
    for start, chunk in ((1, names[:15]), (16, names[15:30])):
        text = "```\n"
        for level, name in enumerate(chunk, start=start):
            emoji, element = t._tower_floor_element_label(level, widest)
            text += f"{level:>2} ✅ {emoji} {element:<9} {name}\n"
        text += "```"
        assert len(text) <= 1024, (start, len(text))

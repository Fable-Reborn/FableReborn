"""The Draslin rebuild's numbers: materials, what each project needs, supply runs, caps and bonuses.

Discord-free and database-free, so the cog, the service and the tests share it. Tune the game here.
"""
from __future__ import annotations

import json
import random
from dataclasses import dataclass
from pathlib import Path

TOWN = "draslin"
ASSETS = Path(__file__).resolve().parents[2] / "assets" / "draslin_rebuild"

MATERIALS = ("timber", "stone", "iron", "glass", "cloth")
MATERIAL_NAMES = {"timber": "Timber", "stone": "Stone", "iron": "Iron", "glass": "Glass", "cloth": "Cloth"}
MATERIAL_EMOJI = {"timber": "🪵", "stone": "🪨", "iron": "⛓️", "glass": "🔷", "cloth": "🧵"}

# Each project's mix of materials and its size relative to the others. The real amounts are set when a project
# starts, by `paced_needs`, so the whole town takes about TARGET_TOWN_DAYS however many people are building.
RECIPES = {
    "crater":     {"stone": 450, "timber": 200, "iron": 100, "cloth": 50},
    "inn":        {"timber": 300, "stone": 250, "glass": 60, "cloth": 90},
    "armory":     {"timber": 220, "stone": 260, "iron": 180},
    "apothecary": {"timber": 220, "stone": 200, "glass": 160, "cloth": 40},
    "library":    {"timber": 450, "stone": 450, "glass": 150, "cloth": 150},
    "art":        {"timber": 200, "stone": 180, "glass": 120, "cloth": 100},
    "kitchen":    {"timber": 220, "stone": 220, "iron": 100, "cloth": 40},
    "tel":        {"timber": 280, "stone": 220, "iron": 40, "glass": 40},
    "milo":       {"timber": 260, "stone": 230, "glass": 40, "cloth": 50},
    "corner":     {"timber": 260, "stone": 230, "glass": 40, "cloth": 50},
    "dreamers":   {"timber": 400, "stone": 300, "glass": 80, "cloth": 80},
    "school":     {"timber": 380, "stone": 380, "glass": 120, "cloth": 120},
    "walls":      {"stone": 1100, "iron": 200, "timber": 200},
    "streets":    {"stone": 1100, "timber": 500},
}
DEFAULT_RECIPE = {"timber": 250, "stone": 250, "glass": 50, "cloth": 50}

# Supply runs: where you can send your character, and what comes back (share of the haul per material).
@dataclass(frozen=True)
class Destination:
    key: str
    name: str
    blurb: str
    yields: dict


DESTINATIONS = {
    "logging": Destination("logging", "Borderlands Logging Camp", "Fell and haul timber from the border woods.",
                           {"timber": 1.0}),
    "quarry": Destination("quarry", "Mythra Quarry", "Cut stone from the foot of Mythra Peak.", {"stone": 1.0}),
    "labs": Destination("labs", "Ry'jin's Labs", "Salvage iron and glass from the empty laboratories.",
                        {"iron": 0.6, "glass": 0.4}),
    "weavers": Destination("weavers", "Ildrian Weavers", "Trade work for bolts of cloth beyond Ildria.",
                           {"cloth": 1.0}),
}
# Run length in hours -> base haul. Short runs pay a little better per hour, long ones suit busy people.
RUN_HAULS = {1: 8, 4: 26, 8: 44}

DAILY_GATHER_CAP = 90          # materials one person can bring in per UTC day, Discord and Tiamat together
TIAMAT_ONLY = 30               # the part of that only playing Tiamat can fill (Discord runs stop 30 short)
CROWNS_PER_UNIT = 1            # Tiamat crowns for one unit of materials bought for the town (1 crown = 1,000 Fable gold)
DAILY_DONATE_CAP = 25          # units one person can buy per UTC day

# Pacing. A project's needs come from what the town has really brought in lately (the last PACE_WINDOW_DAYS,
# from opening day), so 10 builders and 40 both finish the town in about TARGET_TOWN_DAYS. Until there's a day
# of history the guess is ESTIMATED_BUILDERS. The window is clamped so a quiet week or a rush can't swing it far.
TARGET_TOWN_DAYS = 35
PACE_WINDOW_DAYS = 7
PER_BUILDER_DAY = 65           # what an active player brings in on a normal day (runs plus a few purchases)
ESTIMATED_BUILDERS = 20
MIN_BUILDERS, MAX_BUILDERS = 8, 50
OWNER_ID = 295173706496475136  # opens, pauses, resets and sets up the rebuild

# Restored Draslin only exists after the story's ending, so the rebuild is for players who have finished it.
# They get this role automatically (it opens the rebuild channel); everyone else sees nothing of it.
CREW_ROLE_ID = 1560988133691228181   # Rolan's Crew
CHANNEL_NAME = "「🔨」rolans-crew"          # says nothing about the ending to anyone browsing the channel list

# The missing in The Tiamat Sacrament (the server's src/rebuild/rescues.js MISSING, in the order they're found):
# each comes home once for the whole town, credited to whoever found them first.
MISSING_NAMES = {"brin": "Brin", "bastian": "Bastian", "pell": "Pell", "ida": "Ida", "tomas": "Tomas", "marlo": "Marlo",
                 "senna": "Senna", "fen": "Old Fen"}
NOT_YET = "Finish **The Tiamat Sacrament** to join this."
LUCKY_CHANCE = 0.10            # a run that finds extra
LUCKY_MULTIPLIER = 1.5
SPREAD = 0.15                  # a haul is the base +/- this share

# Fable classes and races from The Tiamat Sacrament help in their own way.
DRAGONKIN_BONUS = 1.10                   # every haul
CLASS_BONUSES = {"Breathcaller": {"glass": 1.5},   # dragon breath for a kiln
                 "Penitent": {"stone": 1.25}}      # the heaviest loads, carried as penance

# Perks: each finished building helps every builder from then on, in its own way, so the vote is about which
# help the town wants first. The crater is always first and the streets always last, so they have none.
# (The pacing still aims the whole town at TARGET_TOWN_DAYS: perks make each run feel bigger and change the order
# that suits the crowd, not the finishing date.)
@dataclass(frozen=True)
class Perk:
    name: str
    text: str                       # one sentence, said to the builders
    short: str                      # a few words, for the board and menus
    hours: int | None = None        # only runs of this length
    destination: str | None = None  # only runs to this place
    material: str | None = None     # only this material
    multiplier: float = 1.0
    lucky: float = 1.0              # multiplies the lucky-haul chance
    cap: int = 0                    # added to everyone's daily cart space (the daily limit)


PERKS = {
    "inn": Perk("Garrick's beds", "Crews sleep well at the Inn: 8-hour runs bring back 15% more.",
                "+15% on 8-hour runs", hours=8, multiplier=1.15),
    "armory": Perk("Hesk's forge", "Hesk smelts the scrap: runs to Ry'jin's Labs bring back 25% more iron.",
                   "+25% iron from the Labs", destination="labs", material="iron", multiplier=1.25),
    "apothecary": Perk("Mirren's tonics", "Mirren's tonics keep the crews sharp: lucky hauls happen twice as often.",
                       "Twice the lucky hauls", lucky=2.0),
    "library": Perk("Corvin's maps", "Corvin's old maps show the shortcuts: 1-hour runs bring back 25% more.",
                    "+25% on 1-hour runs", hours=1, multiplier=1.25),
    "art": Perk("Odette's patterns", "Odette sketches what the weavers should make: Weavers runs bring back 25% more cloth.",
                "+25% cloth from the Weavers", destination="weavers", material="cloth", multiplier=1.25),
    "kitchen": Perk("Rosalind's lunches", "Nobody works hungry any more: 4-hour runs bring back 15% more.",
                    "+15% on 4-hour runs", hours=4, multiplier=1.15),
    "school": Perk("Aldine's pupils", "The older pupils help at the logging camp: Borderlands runs bring back 15% more timber.",
                   "+15% timber from the Borderlands", destination="logging", material="timber", multiplier=1.15),
    "tel": Perk("Another home", "Another home is lived in again, and its people lend a cart: +5 cart space for everyone each day.",
                "+5 daily cart space", cap=5),
    "milo": Perk("Another home", "Another home is lived in again, and its people lend a cart: +5 cart space for everyone each day.",
                 "+5 daily cart space", cap=5),
    "corner": Perk("Another home", "Another home is lived in again, and its people lend a cart: +5 cart space for everyone each day.",
                   "+5 daily cart space", cap=5),
    "dreamers": Perk("Two families home", "Two families are home again and both lend carts: +10 cart space for everyone each day.",
                     "+10 daily cart space", cap=10),
    "walls": Perk("The masons stay on", "The masons who raised the walls stay on: Quarry runs bring back 15% more stone.",
                  "+15% stone from the Quarry", destination="quarry", material="stone", multiplier=1.15),
}


def perks_for(done) -> list[tuple[str, Perk]]:
    """The perks of the finished projects in `done`, in the order given."""
    return [(pid, PERKS[pid]) for pid in done if pid in PERKS]


def daily_cap(done=()) -> int:
    """Everything one person can bring in today, from both games (finished homes raise it)."""
    return DAILY_GATHER_CAP + sum(perk.cap for _pid, perk in perks_for(done))


def discord_cap(done=()) -> int:
    """What Discord supply runs alone can fill today; the last TIAMAT_ONLY comes only from playing Tiamat."""
    return daily_cap(done) - TIAMAT_ONLY


def run_room(source: str, discord_used: int, total_used: int, done=()) -> int:
    """How much more one person can bring in today from `source` ('discord' or 'tiamat')."""
    room = daily_cap(done) - total_used
    if source == "discord":
        room = min(room, discord_cap(done) - discord_used)
    return max(0, room)


def perk_applies(perk: Perk, destination: str, hours: int) -> bool:
    if perk.cap:
        return False
    if perk.hours is not None and perk.hours != hours:
        return False
    if perk.destination is not None and perk.destination != destination:
        return False
    return True


def run_perks(done, destination: str, hours: int) -> list[Perk]:
    """The perks that change a run like this one (shown with the haul)."""
    return [perk for _pid, perk in perks_for(done) if perk_applies(perk, destination, hours)]


def expected_haul(destination: str, hours: int, done=()) -> int:
    """About what a run brings back with the town's perks, before luck and personal bonuses (for menus)."""
    total = 0.0
    for material, share in DESTINATIONS[destination].yields.items():
        amount = RUN_HAULS[hours] * share
        for perk in run_perks(done, destination, hours):
            if perk.material in (None, material):
                amount *= perk.multiplier
        total += amount
    return round(total)


STAGE_NAMES = {0: "Rubble", 25: "Foundations", 50: "Walls", 75: "Finishing"}
STEPS = {0: "clear the rubble", 25: "lay the foundations", 50: "raise the walls and the roof",
         75: "finish it and move in"}
STAGE_LINES = {25: "We've cleared the rubble off {called}. Now we can start building.",
               50: "The foundations for {called} are down. Mind the scaffolding.",
               75: "{Called} is standing! Walls, roof, the lot. A little longer and it's done."}


def load_projects() -> dict:
    """The project list and picture boxes, made by the game's tools/build-rebuild-board-assets.py."""
    return json.loads((ASSETS / "projects.json").read_text(encoding="utf-8"))


RECIPE_TOTAL = sum(sum(recipe.values()) for recipe in RECIPES.values())


def paced_daily(total: float | None, days: float | None) -> float:
    """Materials a day the town brings in, from a recent total over `days` (None: no history yet), clamped."""
    daily = total / days if total is not None and days and days >= 1 else ESTIMATED_BUILDERS * PER_BUILDER_DAY
    return max(MIN_BUILDERS * PER_BUILDER_DAY, min(MAX_BUILDERS * PER_BUILDER_DAY, daily))


def paced_needs(project_id: str, daily: float, scale: float = 1) -> dict[str, int]:
    """What a project needs if the town keeps bringing in `daily`: its share of TARGET_TOWN_DAYS, in its mix,
    rounded to fives. `scale` is the GM's extra multiplier."""
    recipe = RECIPES.get(project_id, DEFAULT_RECIPE)
    size = sum(recipe.values())
    total = daily * TARGET_TOWN_DAYS * size / RECIPE_TOTAL * float(scale)
    return {material: max(5, round(total * amount / size / 5) * 5) for material, amount in recipe.items()}


def progress_of(needs) -> int:
    """Whole percent of everything needed that has been delivered. 100 only when every material is in."""
    needed = sum(int(row["needed"]) for row in needs)
    delivered = sum(min(int(row["delivered"]), int(row["needed"])) for row in needs)
    if needed <= 0:
        return 100
    if delivered >= needed:
        return 100
    return min(99, delivered * 100 // needed)


def stage_of(progress: int) -> int:
    return max((at for at in (0, 25, 50, 75, 100) if at <= progress), default=0)


def roll_haul(destination: str, hours: int, *, race: str | None = None, class_lines=(), done=(),
              rng: random.Random | None = None) -> tuple[dict[str, int], bool]:
    """The materials a finished supply run brings back, and whether it was a lucky one.
    `done` is the finished projects, whose perks apply."""
    rng = rng or random.SystemRandom()
    place = DESTINATIONS[destination]
    perks = run_perks(done, destination, hours)
    total = RUN_HAULS[hours] * rng.uniform(1 - SPREAD, 1 + SPREAD)
    chance = LUCKY_CHANCE
    for perk in perks:
        chance *= perk.lucky
    lucky = rng.random() < chance
    if lucky:
        total *= LUCKY_MULTIPLIER
    if race == "Dragonkin":
        total *= DRAGONKIN_BONUS
    haul = {}
    for material, share in place.yields.items():
        amount = total * share
        for line in class_lines:
            amount *= CLASS_BONUSES.get(line, {}).get(material, 1.0)
        for perk in perks:
            if perk.material in (None, material):
                amount *= perk.multiplier
        if round(amount) > 0:
            haul[material] = round(amount)
    return haul, lucky


def cap_haul(haul: dict[str, int], room: int) -> dict[str, int]:
    """Trim a haul to the room left under the daily cap, keeping its mix."""
    total = sum(haul.values())
    if total <= room:
        return dict(haul)
    if room <= 0:
        return {}
    trimmed, given = {}, 0
    items = sorted(haul.items(), key=lambda item: -item[1])
    for n, (material, amount) in enumerate(items):
        share = room - given if n == len(items) - 1 else min(room - given, amount * room // total)
        if share > 0:
            trimmed[material] = share
            given += share
    return trimmed


def split_purchase(units: int, remaining: dict[str, int]) -> dict[str, int]:
    """Spread bought units over what the project still needs, most-needed first."""
    open_needs = {m: r for m, r in remaining.items() if r > 0}
    if units <= 0 or not open_needs:
        return {}
    total = sum(open_needs.values())
    order = sorted(open_needs, key=lambda m: -open_needs[m])
    split = {m: min(open_needs[m], units * open_needs[m] // total) for m in order}
    left = units - sum(split.values())
    for m in order:                    # round-off goes where the most is still missing
        if left <= 0:
            break
        extra = min(left, open_needs[m] - split[m])
        split[m] += extra
        left -= extra
    if left > 0:                       # more than the project needs: the rest is stockpiled as its main material
        split[order[0]] += left
    return {m: n for m, n in split.items() if n > 0}


def ballot_winner(ballot_ids, tallies: dict[str, int], order: dict[str, int]) -> str | None:
    """Most votes wins; a tie (or no votes at all) goes to the place earliest in the town's queue."""
    ballot_ids = list(ballot_ids)
    if not ballot_ids:
        return None
    return min(ballot_ids, key=lambda pid: (-int(tallies.get(pid, 0)), order.get(pid, 10**6)))

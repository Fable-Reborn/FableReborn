"""The Draslin rebuild's database side. Discord-free: the cog, the tests and (later) the game share these rules.

Every change to the town goes through `deliver`, inside one transaction that first locks the town's row, so
deliveries, finishing a project and starting the next one never race each other.
"""
from __future__ import annotations

import datetime
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from . import rules

SCHEMA = Path(__file__).resolve().parents[2] / "scripts" / "draslin_rebuild.sql"
TODAY = "date_trunc('day', now() AT TIME ZONE 'UTC') AT TIME ZONE 'UTC'"


class RebuildError(Exception):
    """Something the player should be told, in plain words."""


@dataclass
class Finished:
    project_id: str
    next_id: str | None
    round: int


@dataclass
class Delivery:
    applied: dict = field(default_factory=dict)      # material -> into the project being built
    stockpiled: dict = field(default_factory=dict)   # material -> kept for later projects
    project_id: str | None = None
    progress_before: int = 0
    progress_after: int = 0
    finished: list = field(default_factory=list)     # Finished, in order

    @property
    def total(self) -> int:
        return sum(self.applied.values()) + sum(self.stockpiled.values())


# ---- schema and seeding ----------------------------------------------------------------------------------
async def ensure_schema(conn) -> None:
    await conn.execute(SCHEMA.read_text(encoding="utf-8"))


async def ensure_town(conn, data: dict, town: str = rules.TOWN) -> None:
    """Create the town on first run: its first project building, the first ballot open, the rest queued.
    Projects added to the asset list later join the end of the queue."""
    async with conn.transaction():
        created = await conn.fetchval(
            "INSERT INTO rebuild_towns (town) VALUES ($1) ON CONFLICT DO NOTHING RETURNING town", town)
        order = data["order"]
        last = await conn.fetchval("SELECT coalesce(max(ord), -1) FROM rebuild_projects WHERE town=$1", town)
        for n, pid in enumerate(order):
            status = "queued"
            if created:
                status = "building" if pid == data["first"] else "ballot" if pid in data["ballot"] else "queued"
            await conn.execute(
                """INSERT INTO rebuild_projects (town, id, ord, status) VALUES ($1, $2, $3, $4)
                   ON CONFLICT (town, id) DO NOTHING""", town, pid, n if created else last + 1 + n, status)
        if created:
            await _start_project(conn, town, data["first"], 1)
        await sync_daily_cap(conn, town)


async def _start_project(conn, town, pid, round_no) -> None:
    scale = await conn.fetchval("SELECT scale FROM rebuild_towns WHERE town=$1", town)
    await conn.execute(
        "UPDATE rebuild_projects SET status='building', round=$3, started_at=now(), progress=0 WHERE town=$1 AND id=$2",
        town, pid, round_no)
    await _set_needs(conn, town, pid, rules.paced_needs(pid, await recent_daily(conn, town), scale))


async def _set_needs(conn, town, pid, needs: dict) -> None:
    await conn.execute("DELETE FROM rebuild_needs WHERE town=$1 AND project_id=$2", town, pid)
    for material, needed in needs.items():
        await conn.execute(
            "INSERT INTO rebuild_needs (town, project_id, material, needed) VALUES ($1, $2, $3, $4)",
            town, pid, material, needed)


async def recent_daily(conn, town=rules.TOWN) -> float:
    """Materials a day the town has brought in over the pacing window since opening day (GM grants left out)."""
    row = await conn.fetchrow(
        f"""SELECT activated_at, greatest(activated_at, now() - INTERVAL '{rules.PACE_WINDOW_DAYS} days') AS since
            FROM rebuild_towns WHERE town=$1""", town)
    if not row or row["activated_at"] is None:
        return rules.paced_daily(None, None)
    total = await conn.fetchval(
        """SELECT coalesce(sum(amount), 0) FROM rebuild_contributions
           WHERE town=$1 AND kind <> 'grant' AND created_at >= $2""", town, row["since"])
    days = (datetime.datetime.now(datetime.timezone.utc) - row["since"]).total_seconds() / 86400
    return rules.paced_daily(float(total), days)


# ---- opening, pausing and starting over (the owner only; the cog checks who) ----------------------------
async def open_town(pool, town=rules.TOWN) -> bool:
    """Open the rebuild. The first opening is Day 1, and the first project's needs are set for opening day.
    Returns True on the first opening, False when it reopens after a pause."""
    async with pool.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow("SELECT active, activated_at, scale FROM rebuild_towns WHERE town=$1 FOR UPDATE", town)
            if row["active"]:
                raise RebuildError("The rebuild is already open.")
            first = row["activated_at"] is None
            await conn.execute(
                """UPDATE rebuild_towns SET active=true, activated_at=coalesce(activated_at, now()),
                   started_at=CASE WHEN activated_at IS NULL THEN now() ELSE started_at END WHERE town=$1""", town)
            current = await building(conn, town)
            if first and current:
                delivered = await conn.fetchval(
                    "SELECT coalesce(sum(delivered), 0) FROM rebuild_needs WHERE town=$1 AND project_id=$2",
                    town, current["id"])
                if not delivered:   # sized now, with the scale the owner settled on, rather than at setup
                    await _set_needs(conn, town, current["id"],
                                     rules.paced_needs(current["id"], rules.paced_daily(None, None), row["scale"]))
                    await conn.execute("UPDATE rebuild_projects SET started_at=now() WHERE town=$1 AND id=$2",
                                       town, current["id"])
            return first


async def pause_town(pool, town=rules.TOWN) -> None:
    async with pool.acquire() as conn:
        async with conn.transaction():
            if not await conn.fetchval("SELECT active FROM rebuild_towns WHERE town=$1 FOR UPDATE", town):
                raise RebuildError("The rebuild isn't open.")
            await conn.execute("UPDATE rebuild_towns SET active=false WHERE town=$1", town)


async def reset_town(pool, data: dict, town=rules.TOWN) -> None:
    """Back to the ruins, for setting up and testing before opening day. Refused once the rebuild has opened.
    The board stays where it was posted."""
    async with pool.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow("SELECT * FROM rebuild_towns WHERE town=$1 FOR UPDATE", town)
            if row and row["activated_at"] is not None:
                raise RebuildError("The rebuild has opened; it can't be reset any more.")
            for table in ("rebuild_events", "rebuild_inbox", "rebuild_votes", "rebuild_expeditions", "rebuild_contributions", "rebuild_stockpile",
                          "rebuild_needs", "rebuild_projects", "rebuild_towns"):
                await conn.execute(f"DELETE FROM {table} WHERE town=$1", town)
            await ensure_town(conn, data, town)
            if row:
                await conn.execute(
                    "UPDATE rebuild_towns SET board_channel_id=$2, board_message_id=$3, scale=$4 WHERE town=$1",
                    town, row["board_channel_id"], row["board_message_id"], row["scale"])


async def require_open(conn, town=rules.TOWN) -> None:
    row = await conn.fetchrow("SELECT active, activated_at, finished_at FROM rebuild_towns WHERE town=$1", town)
    if not row:
        raise RebuildError("Draslin's rebuild hasn't been set up yet.")
    if row["finished_at"]:
        raise RebuildError("Draslin is whole again. There's nothing left to build.")
    if not row["active"]:
        raise RebuildError("The rebuild hasn't opened yet. Watch the board!" if row["activated_at"] is None
                           else "The rebuild is paused for now. Rolan's crews are resting.")


# ---- small reads -----------------------------------------------------------------------------------------
async def is_declared_alt(conn, discord_id: int) -> bool:
    # Checked first rather than caught: a failed query would abort the caller's transaction.
    if not await conn.fetchval("SELECT to_regclass('alt_links') IS NOT NULL"):
        return False
    return bool(await conn.fetchval("SELECT 1 FROM alt_links WHERE alt=$1", discord_id))


async def building(conn, town=rules.TOWN):
    return await conn.fetchrow(
        "SELECT * FROM rebuild_projects WHERE town=$1 AND status='building'", town)


async def done_projects(conn, town=rules.TOWN) -> list[str]:
    """Finished projects, in the order they were finished (their perks apply)."""
    return [r["id"] for r in await conn.fetch(
        "SELECT id FROM rebuild_projects WHERE town=$1 AND status='done' ORDER BY finished_at, ord", town)]


async def gathered_today(conn, discord_id: int, kind: str, town=rules.TOWN, source: str | None = None) -> int:
    return int(await conn.fetchval(
        f"""SELECT coalesce(sum(amount), 0) FROM rebuild_contributions
            WHERE town=$1 AND discord_id=$2 AND kind=$3 AND created_at >= {TODAY} AND ($4::text IS NULL OR source=$4)""",
        town, discord_id, kind, source))


async def run_room(conn, discord_id: int, source: str = "discord", town=rules.TOWN, done=None) -> int:
    """Room left today for runs from `source`, under both the shared limit and Discord's share of it."""
    done = await done_projects(conn, town) if done is None else done
    return rules.run_room(source, await gathered_today(conn, discord_id, "gather", town, "discord"),
                          await gathered_today(conn, discord_id, "gather", town), done)


def next_reset() -> int:
    """When the carts head out again (the next UTC midnight), for Discord's <t:...:R> countdown."""
    now = datetime.datetime.now(datetime.timezone.utc)
    return int((now.replace(hour=0, minute=0, second=0, microsecond=0) + datetime.timedelta(days=1)).timestamp())


def full_message(tiamat_left: int) -> str:
    """Said when Discord runs can't bring in any more today. Kept in the story's words: Rolan's carts are full."""
    if tiamat_left > 0:
        return (f"The supply carts leaving Rolan's camp are full for today. There's still room for **{tiamat_left}** "
                f"more if you head out yourself in The Tiamat Sacrament.")
    return f"Rolan's carts are full for today. The crews head out again <t:{next_reset()}:R>."


# ---- the one way materials enter the town ----------------------------------------------------------------
async def deliver(conn, discord_id: int, materials: dict, *, kind: str, source: str = "discord",
                  crowns_spent: int = 0, metadata: dict | None = None, town: str = rules.TOWN) -> Delivery:
    """Put materials into the project being built (the rest into the stockpile), log who brought them,
    and finish and start projects as they fill. Call inside a transaction."""
    await _lock(conn, town)
    current = await building(conn, town)
    result = Delivery(project_id=current["id"] if current else None,
                      progress_before=current["progress"] if current else 100)
    request_id = uuid.uuid4()
    first = True
    for material, amount in materials.items():
        amount = int(amount)
        if amount <= 0:
            continue
        applied = 0
        if current:
            row = await conn.fetchrow(
                "SELECT needed, delivered FROM rebuild_needs WHERE town=$1 AND project_id=$2 AND material=$3",
                town, current["id"], material)
            if row:
                applied = min(amount, row["needed"] - row["delivered"])
                if applied:
                    await conn.execute(
                        """UPDATE rebuild_needs SET delivered=delivered+$4
                           WHERE town=$1 AND project_id=$2 AND material=$3""", town, current["id"], material, applied)
        if applied:
            result.applied[material] = result.applied.get(material, 0) + applied
        if amount - applied:
            await _stock(conn, town, material, amount - applied)
            result.stockpiled[material] = result.stockpiled.get(material, 0) + amount - applied
        await conn.execute(
            """INSERT INTO rebuild_contributions (town, discord_id, source, kind, project_id, material, amount, applied,
                                                 crowns_spent, request_id, metadata)
               VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11::jsonb)""",
            town, discord_id, source, kind, result.project_id, material, amount, applied,
            crowns_spent if first else 0, request_id, _json(metadata or {}))
        first = False
    if current:
        result.progress_after = await _settle(conn, town, current["id"], result.finished)
    else:
        result.progress_after = 100
    return result


async def _lock(conn, town):
    await conn.execute("SELECT 1 FROM rebuild_towns WHERE town=$1 FOR UPDATE", town)


async def _stock(conn, town, material, amount):
    await conn.execute(
        """INSERT INTO rebuild_stockpile (town, material, amount) VALUES ($1, $2, $3)
           ON CONFLICT (town, material) DO UPDATE SET amount=rebuild_stockpile.amount+EXCLUDED.amount""",
        town, material, amount)


async def _settle(conn, town, pid, finished: list) -> int:
    """Recompute a project's progress; when it's full, finish it, start the vote's winner and feed it from the
    stockpile (which can finish that one too). Returns the progress of the project first given."""
    needs = await conn.fetch("SELECT needed, delivered FROM rebuild_needs WHERE town=$1 AND project_id=$2", town, pid)
    progress = rules.progress_of(needs)
    await conn.execute("UPDATE rebuild_projects SET progress=$3 WHERE town=$1 AND id=$2", town, pid, progress)
    if progress < 100:
        return progress
    next_id = await _finish(conn, town, pid, finished)
    while next_id:
        await _drain_stockpile(conn, town, next_id)
        needs = await conn.fetch("SELECT needed, delivered FROM rebuild_needs WHERE town=$1 AND project_id=$2",
                                 town, next_id)
        next_progress = rules.progress_of(needs)
        await conn.execute("UPDATE rebuild_projects SET progress=$3 WHERE town=$1 AND id=$2", town, next_id, next_progress)
        if next_progress < 100:
            break
        next_id = await _finish(conn, town, next_id, finished)
    return progress


async def sync_daily_cap(conn, town=rules.TOWN) -> int:
    """Store today's per-person limit (homes raise it) where the game server reads it."""
    cap = rules.daily_cap(await done_projects(conn, town))
    await conn.execute("UPDATE rebuild_towns SET daily_cap=$2 WHERE town=$1", town, cap)
    return cap


async def _finish(conn, town, pid, finished: list) -> str | None:
    round_no = await conn.fetchval("SELECT round FROM rebuild_towns WHERE town=$1", town)
    await conn.execute(
        "UPDATE rebuild_projects SET status='done', progress=100, finished_at=now() WHERE town=$1 AND id=$2", town, pid)
    await sync_daily_cap(conn, town)
    ballot = await conn.fetch("SELECT id, ord FROM rebuild_projects WHERE town=$1 AND status='ballot'", town)
    tallies = {r["project_id"]: r["votes"] for r in await conn.fetch(
        """SELECT project_id, count(*) AS votes FROM rebuild_votes WHERE town=$1 AND round=$2 GROUP BY project_id""",
        town, round_no)}
    winner = rules.ballot_winner([r["id"] for r in ballot], tallies, {r["id"]: r["ord"] for r in ballot})
    if winner is None:  # the ballot ran dry: take the queue in order (normally only the last project)
        winner = await conn.fetchval(
            "SELECT id FROM rebuild_projects WHERE town=$1 AND status='queued' ORDER BY ord LIMIT 1", town)
    finished.append(Finished(pid, winner, round_no))
    if winner is None:
        await conn.execute("UPDATE rebuild_towns SET finished_at=now() WHERE town=$1", town)
        return None
    await conn.execute("UPDATE rebuild_towns SET round=round+1 WHERE town=$1", town)
    await _start_project(conn, town, winner, round_no + 1)
    await _fill_ballot(conn, town)
    return winner


async def _fill_ballot(conn, town) -> None:
    open_places = 3 - await conn.fetchval(
        "SELECT count(*) FROM rebuild_projects WHERE town=$1 AND status='ballot'", town)
    if open_places > 0:
        await conn.execute(
            """UPDATE rebuild_projects SET status='ballot' WHERE town=$1 AND id IN (
                   SELECT id FROM rebuild_projects WHERE town=$1 AND status='queued' ORDER BY ord LIMIT $2)""",
            town, open_places)


async def _drain_stockpile(conn, town, pid) -> None:
    rows = await conn.fetch(
        """SELECT n.material, n.needed - n.delivered AS missing, s.amount
           FROM rebuild_needs n JOIN rebuild_stockpile s ON s.town=n.town AND s.material=n.material
           WHERE n.town=$1 AND n.project_id=$2 AND s.amount > 0 AND n.delivered < n.needed""", town, pid)
    for row in rows:
        take = min(row["missing"], row["amount"])
        await conn.execute("UPDATE rebuild_stockpile SET amount=amount-$3 WHERE town=$1 AND material=$2",
                           town, row["material"], take)
        await conn.execute("UPDATE rebuild_needs SET delivered=delivered+$4 WHERE town=$1 AND project_id=$2 AND material=$3",
                           town, pid, row["material"], take)


def _json(value) -> str:
    import json
    return json.dumps(value, default=str)


# ---- finds from The Tiamat Sacrament ----------------------------------------------------------------------
@dataclass
class Applied:
    discord_id: int
    activity: str
    material: str
    amount: int
    result: str
    delivery: Delivery | None


async def apply_inbox(pool, limit: int = 50, town=rules.TOWN) -> list[Applied]:
    """Deliver what the game server has checked and queued, oldest first. Each row is applied once, under the
    town's lock, with the shared daily limit (the Tiamat side may fill all of it). Finds that arrive while the
    rebuild is paused wait for it to reopen."""
    done: list[Applied] = []
    async with pool.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow("SELECT active, finished_at FROM rebuild_towns WHERE town=$1", town)
            if not row or not row["active"]:
                return done
            rows = await conn.fetch(
                """SELECT * FROM rebuild_inbox WHERE town=$1 AND applied_at IS NULL ORDER BY id LIMIT $2
                   FOR UPDATE SKIP LOCKED""", town, limit)
            for item in rows:
                await _lock(conn, town)
                result, delivery, amount = "delivered", None, 0
                if await is_declared_alt(conn, item["discord_id"]):
                    result = "alt"
                else:
                    room = await run_room(conn, item["discord_id"], "tiamat", town)
                    amount = min(item["amount"], room)
                    if amount <= 0:
                        result = "limit"
                    else:
                        delivery = await deliver(conn, item["discord_id"], {item["material"]: amount}, kind="gather",
                                                 source="tiamat", town=town,
                                                 metadata={"activity": item["activity"], "ref": item["ref"], "inbox": item["id"],
                                                           **_jsonb(item["metadata"])})
                await conn.execute("UPDATE rebuild_inbox SET applied_at=now(), applied=$2, result=$3 WHERE id=$1",
                                   item["id"], amount, result)
                done.append(Applied(item["discord_id"], item["activity"], item["material"], amount, result, delivery))
    return done


def _jsonb(value) -> dict:
    import json
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            return {}
    return {k: v for k, v in (value or {}).items() if k in ("mapId", "x", "y", "spot", "username")}


# ---- supply runs -----------------------------------------------------------------------------------------
@dataclass
class Haul:
    destination: str
    hours: int
    rolled: dict
    haul: dict
    lucky: bool
    capped: bool
    delivery: Delivery | None
    perks: list = field(default_factory=list)   # names of the perks that helped this run


async def expedition(conn, discord_id: int):
    return await conn.fetchrow("SELECT * FROM rebuild_expeditions WHERE discord_id=$1", discord_id)


async def start_expedition(pool, discord_id: int, destination: str, hours: int, town=rules.TOWN):
    if destination not in rules.DESTINATIONS:
        raise RebuildError("That place isn't on the map.")
    if hours not in rules.RUN_HAULS:
        raise RebuildError(f"A supply run takes {', '.join(f'{h}h' for h in rules.RUN_HAULS)}.")
    async with pool.acquire() as conn:
        async with conn.transaction():
            if await is_declared_alt(conn, discord_id):
                raise RebuildError("Alt accounts can't haul for Draslin. Your main account builds for you.")
            await require_open(conn, town)
            current = await expedition(conn, discord_id)
            if current:
                raise RebuildError("You're already out on a supply run.")
            if await run_room(conn, discord_id, "discord", town) <= 0:
                raise RebuildError(full_message(await run_room(conn, discord_id, "tiamat", town)))
            return await conn.fetchrow(
                """INSERT INTO rebuild_expeditions (discord_id, town, destination, hours, returns_at)
                   VALUES ($1, $2, $3, $4::int, now() + ($4::int * INTERVAL '1 hour')) RETURNING *""",
                discord_id, town, destination, hours)


async def collect_expedition(pool, discord_id: int, *, race=None, class_lines=(), rng=None, town=rules.TOWN) -> Haul | None:
    """Bring a finished run home and deliver its haul. None if no run is out; raises if it isn't back yet."""
    async with pool.acquire() as conn:
        async with conn.transaction():
            run = await conn.fetchrow(
                "SELECT * FROM rebuild_expeditions WHERE discord_id=$1 FOR UPDATE", discord_id)
            if not run:
                return None
            if run["returns_at"] > datetime.datetime.now(datetime.timezone.utc):
                raise NotBack(run)
            await require_open(conn, run["town"])   # a run that's back during a pause waits at the camp
            await conn.execute("DELETE FROM rebuild_expeditions WHERE discord_id=$1", discord_id)
            await _lock(conn, run["town"])  # the daily cap is checked and used under the town's lock
            done = await done_projects(conn, run["town"])
            rolled, lucky = rules.roll_haul(run["destination"], run["hours"], race=race, class_lines=class_lines,
                                            done=done, rng=rng)
            perks = [perk.name for perk in rules.run_perks(done, run["destination"], run["hours"])]
            room = await run_room(conn, discord_id, "discord", run["town"], done)
            haul = rules.cap_haul(rolled, room)
            delivery = None
            if haul:
                delivery = await deliver(conn, discord_id, haul, kind="gather", town=run["town"],
                                         metadata={"destination": run["destination"], "hours": run["hours"], "lucky": lucky,
                                                   "perks": perks})
            return Haul(run["destination"], run["hours"], rolled, haul, lucky, haul != rolled, delivery, perks)


class NotBack(RebuildError):
    def __init__(self, run):
        super().__init__("Your supply run isn't back yet.")
        self.run = run


# ---- buying materials with Fable gold --------------------------------------------------------------------
async def donate(pool, discord_id: int, crowns: int, town=rules.TOWN) -> tuple[Delivery, int]:
    """Spend Tiamat crowns on materials for the project being built. The crowns come out of the linked wallet
    with a ledger row, the same way the game's own shop spends them."""
    if isinstance(crowns, bool) or not isinstance(crowns, int) or crowns < rules.CROWNS_PER_UNIT:
        raise RebuildError(f"One unit of materials costs **{rules.CROWNS_PER_UNIT} crown{'s' * (rules.CROWNS_PER_UNIT != 1)}**.")
    async with pool.acquire() as conn:
        async with conn.transaction():
            if await is_declared_alt(conn, discord_id):
                raise RebuildError("Alt accounts can't donate to Draslin. Your main account builds for you.")
            await require_open(conn, town)
            await _lock(conn, town)
            current = await building(conn, town)
            if not current:
                raise RebuildError("Draslin is whole again. There's nothing left to build.")
            room = rules.DAILY_DONATE_CAP - await gathered_today(conn, discord_id, "donate", town)
            if room <= 0:
                raise RebuildError(f"Rolan's carts for bought goods are full for today. Try again <t:{next_reset()}:R>.")
            units = min(crowns // rules.CROWNS_PER_UNIT, room)
            cost = units * rules.CROWNS_PER_UNIT
            wallet = await conn.fetchval(
                "SELECT crowns FROM tiamat_players WHERE profile_user=$1 FOR UPDATE", discord_id) \
                if await conn.fetchval("SELECT to_regclass('tiamat_players') IS NOT NULL") else None
            if wallet is None:
                raise RebuildError("Donations are paid in Tiamat crowns. Link your Tiamat account with `$link` first.")
            if wallet < cost:
                raise RebuildError(f"You have **{int(wallet):,}** crowns; that buys {int(wallet) // rules.CROWNS_PER_UNIT} "
                                   f"units. Fable gold can become crowns from `$rpg`.")
            remaining = {r["material"]: r["needed"] - r["delivered"] for r in await conn.fetch(
                "SELECT material, needed, delivered FROM rebuild_needs WHERE town=$1 AND project_id=$2", town, current["id"])}
            split = rules.split_purchase(units, remaining)
            balance = await conn.fetchval(
                "UPDATE tiamat_players SET crowns=crowns-$1 WHERE profile_user=$2 RETURNING crowns", cost, discord_id)
            delivery = await deliver(conn, discord_id, split, kind="donate", crowns_spent=cost, town=town)
            await conn.execute(
                """INSERT INTO tiamat_crown_ledger (profile_user, kind, gold_delta, crown_delta, crown_balance_after,
                                                    request_id, metadata)
                   VALUES ($1, 'game_purchase', 0, $2, $3, $4, $5::jsonb)""",
                discord_id, -cost, balance, uuid.uuid4(),
                _json({"source": "draslin_rebuild", "town": town, "project": delivery.project_id, "units": units,
                       "materials": {**delivery.applied, **{f"stockpiled_{m}": n for m, n in delivery.stockpiled.items()}}}))
            return delivery, cost


async def grant(pool, discord_id: int, material: str, amount: int, *, by: int, town=rules.TOWN) -> Delivery:
    if material not in rules.MATERIALS:
        raise RebuildError(f"Materials are: {', '.join(rules.MATERIALS)}.")
    async with pool.acquire() as conn:
        async with conn.transaction():
            return await deliver(conn, discord_id, {material: amount}, kind="grant", town=town, metadata={"by": by})


# ---- voting ----------------------------------------------------------------------------------------------
async def cast_vote(pool, discord_id: int, project_id: str, source="discord", town=rules.TOWN) -> int:
    async with pool.acquire() as conn:
        async with conn.transaction():
            if await is_declared_alt(conn, discord_id):
                raise RebuildError("Alt accounts don't get a vote. Your main account votes for you.")
            await require_open(conn, town)
            round_no = await conn.fetchval("SELECT round FROM rebuild_towns WHERE town=$1 FOR SHARE", town)
            status = await conn.fetchval("SELECT status FROM rebuild_projects WHERE town=$1 AND id=$2", town, project_id)
            if status != "ballot":
                raise RebuildError("That place isn't on the ballot right now.")
            await conn.execute(
                """INSERT INTO rebuild_votes (town, round, discord_id, project_id, source) VALUES ($1, $2, $3, $4, $5)
                   ON CONFLICT (town, round, discord_id) DO UPDATE
                   SET project_id=EXCLUDED.project_id, source=EXCLUDED.source, voted_at=now()""",
                town, round_no, discord_id, project_id, source)
            return round_no


# ---- what the board shows --------------------------------------------------------------------------------
async def snapshot(pool, town=rules.TOWN) -> dict:
    async with pool.acquire() as conn:
        town_row = await conn.fetchrow("SELECT * FROM rebuild_towns WHERE town=$1", town)
        projects = await conn.fetch("SELECT id, ord, status, progress FROM rebuild_projects WHERE town=$1 ORDER BY ord", town)
        current = next((p for p in projects if p["status"] == "building"), None)
        needs = await conn.fetch(
            "SELECT material, needed, delivered FROM rebuild_needs WHERE town=$1 AND project_id=$2 ORDER BY needed DESC",
            town, current["id"]) if current else []
        tallies = {r["project_id"]: r["votes"] for r in await conn.fetch(
            "SELECT project_id, count(*) AS votes FROM rebuild_votes WHERE town=$1 AND round=$2 GROUP BY project_id",
            town, town_row["round"])}
        top = await conn.fetch(
            """SELECT c.discord_id, sum(c.amount) AS amount, array_agg(DISTINCT c.source) AS sources, p.name
               FROM rebuild_contributions c LEFT JOIN profile p ON p."user"=c.discord_id
               WHERE c.town=$1 AND c.created_at >= now() - INTERVAL '7 days' AND c.kind <> 'grant'
               GROUP BY c.discord_id, p.name ORDER BY amount DESC LIMIT 5""", town)
        builders = await conn.fetchval(
            """SELECT count(DISTINCT discord_id) FROM rebuild_contributions
               WHERE town=$1 AND created_at >= now() - INTERVAL '7 days' AND kind <> 'grant'""", town)
    return {
        "round": town_row["round"],
        "day": ((datetime.datetime.now(datetime.timezone.utc) - town_row["activated_at"]).days + 1
                if town_row["activated_at"] else None),
        "active": town_row["active"], "opened": town_row["activated_at"] is not None,
        "finished": town_row["finished_at"] is not None,
        "projects": [dict(p) for p in projects], "current": dict(current) if current else None,
        "needs": [dict(n) for n in needs],
        "ballot": [{"id": p["id"], "votes": int(tallies.get(p["id"], 0))} for p in projects if p["status"] == "ballot"],
        "top": [{"discord_id": r["discord_id"], "name": r["name"], "amount": int(r["amount"]), "sources": list(r["sources"])}
                for r in top],
        "builders_week": int(builders or 0),
        "board": (town_row["board_channel_id"], town_row["board_message_id"]),
    }


async def finish_stats(pool, project_id: str, town=rules.TOWN) -> dict:
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM rebuild_projects WHERE town=$1 AND id=$2", town, project_id)
        builders = await conn.fetchval(
            "SELECT count(DISTINCT discord_id) FROM rebuild_contributions WHERE town=$1 AND project_id=$2 AND kind <> 'grant'",
            town, project_id)
        materials = await conn.fetchval(
            "SELECT coalesce(sum(needed), 0) FROM rebuild_needs WHERE town=$1 AND project_id=$2", town, project_id)
        helpers = await conn.fetch(
            """SELECT c.discord_id, p.name, sum(c.applied) AS amount FROM rebuild_contributions c
               LEFT JOIN profile p ON p."user"=c.discord_id
               WHERE c.town=$1 AND c.project_id=$2 AND c.kind <> 'grant'
               GROUP BY c.discord_id, p.name ORDER BY amount DESC LIMIT 3""", town, project_id)
        tallies = await conn.fetch(
            "SELECT project_id, count(*) AS votes FROM rebuild_votes WHERE town=$1 AND round=$2 GROUP BY project_id ORDER BY votes DESC",
            town, row["round"])
        next_row = await conn.fetchrow(
            "SELECT id FROM rebuild_projects WHERE town=$1 AND round=$2", town, (row["round"] or 0) + 1)
    took = (row["finished_at"] - row["started_at"]) if row["finished_at"] and row["started_at"] else None
    return {"builders": int(builders or 0), "materials": int(materials or 0), "took": took,
            "helpers": [{"discord_id": h["discord_id"], "name": h["name"]} for h in helpers],
            "votes": [int(t["votes"]) for t in tallies], "next_id": next_row["id"] if next_row else None}


async def unannounced(pool, town=rules.TOWN) -> list[str]:
    async with pool.acquire() as conn:
        return [r["id"] for r in await conn.fetch(
            """SELECT id FROM rebuild_projects WHERE town=$1 AND status='done' AND announced_at IS NULL
               ORDER BY finished_at""", town)]


async def mark_announced(pool, project_id: str, town=rules.TOWN) -> None:
    async with pool.acquire() as conn:
        await conn.execute("UPDATE rebuild_projects SET announced_at=now() WHERE town=$1 AND id=$2", town, project_id)


async def board_location(pool, town=rules.TOWN) -> tuple[int | None, int | None]:
    row = await pool.fetchrow("SELECT board_channel_id, board_message_id FROM rebuild_towns WHERE town=$1", town)
    return (row["board_channel_id"], row["board_message_id"]) if row else (None, None)


# ---- what the game tells Discord ------------------------------------------------------------------------
async def pending_events(pool, town=rules.TOWN, limit: int = 10) -> list[dict]:
    """Things the Tiamat server wants posted in Rolan's camp (someone brought home, a gold haul), oldest first."""
    rows = await pool.fetch(
        "SELECT id, kind, payload, created_at FROM rebuild_events WHERE town=$1 AND posted_at IS NULL ORDER BY id LIMIT $2",
        town, limit)
    return [{"id": r["id"], "kind": r["kind"], "payload": _jsonb_all(r["payload"]), "created_at": r["created_at"]} for r in rows]


async def mark_event_posted(pool, event_id: int) -> None:
    await pool.execute("UPDATE rebuild_events SET posted_at=now() WHERE id=$1", event_id)


def _jsonb_all(value) -> dict:
    import json
    if isinstance(value, str):
        try:
            return json.loads(value) or {}
        except ValueError:
            return {}
    return dict(value or {})


async def haulers(pool, limit: int = 10) -> list[dict]:
    """The week's fastest haul from the Mythra trail to Draslin, per player."""
    rows = await pool.fetch(
        """SELECT DISTINCT ON (h.discord_id) h.discord_id, h.seconds, h.medal, coalesce(p.name, h.name) AS name
           FROM rebuild_haul_runs h LEFT JOIN profile p ON p."user"=h.discord_id
           WHERE h.finished_at >= now() - INTERVAL '7 days'
           ORDER BY h.discord_id, h.seconds""")
    return sorted(({"discord_id": r["discord_id"], "seconds": float(r["seconds"]), "medal": r["medal"], "name": r["name"]}
                   for r in rows), key=lambda r: r["seconds"])[:limit]


async def set_board(pool, channel_id: int | None, message_id: int | None, town=rules.TOWN) -> None:
    async with pool.acquire() as conn:
        await conn.execute("UPDATE rebuild_towns SET board_channel_id=$2, board_message_id=$3 WHERE town=$1",
                           town, channel_id, message_id)


async def set_scale(pool, scale: float, town=rules.TOWN) -> None:
    if not 0 < scale <= 20:
        raise RebuildError("Scale goes from just above 0 to 20.")
    async with pool.acquire() as conn:
        await conn.execute("UPDATE rebuild_towns SET scale=$2 WHERE town=$1", town, scale)


async def homecomings(pool, discord_ids) -> dict[int, list[tuple[str, bool]]]:
    """Who each player brought home in The Tiamat Sacrament, in order, and whether they were first (for everyone)."""
    rows = await pool.fetch(
        """SELECT r.discord_id, r.person, r.discord_id = f.discord_id AS first FROM rebuild_rescues r
           JOIN (SELECT DISTINCT ON (person) person, discord_id FROM rebuild_rescues
                 ORDER BY person, rescued_at, discord_id) f USING (person)
           WHERE r.discord_id = ANY($1::bigint[]) ORDER BY r.rescued_at""", [int(i) for i in discord_ids])
    out: dict[int, list[tuple[str, bool]]] = {}
    for row in rows:
        out.setdefault(row["discord_id"], []).append((row["person"], row["first"]))
    return out


async def personal(pool, discord_id: int, town=rules.TOWN) -> dict:
    async with pool.acquire() as conn:
        totals = await conn.fetchrow(
            f"""SELECT coalesce(sum(amount), 0) AS total,
                       coalesce(sum(amount) FILTER (WHERE kind='gather' AND created_at >= {TODAY}), 0) AS gathered_today,
                       coalesce(sum(amount) FILTER (WHERE kind='gather' AND source='discord' AND created_at >= {TODAY}), 0)
                           AS gathered_discord_today,
                       coalesce(sum(amount) FILTER (WHERE kind='donate' AND created_at >= {TODAY}), 0) AS donated_today,
                       coalesce(sum(amount) FILTER (WHERE created_at >= now() - INTERVAL '7 days'), 0) AS week
                FROM rebuild_contributions WHERE town=$1 AND discord_id=$2 AND kind <> 'grant'""", town, discord_id)
        rank = await conn.fetchval(
            """SELECT r FROM (SELECT discord_id, rank() OVER (ORDER BY sum(amount) DESC) AS r
                              FROM rebuild_contributions WHERE town=$1 AND kind <> 'grant' GROUP BY discord_id) ranked
               WHERE discord_id=$2""", town, discord_id)
        run = await expedition(conn, discord_id)
        round_no = await conn.fetchval("SELECT round FROM rebuild_towns WHERE town=$1", town)
        vote = await conn.fetchval("SELECT project_id FROM rebuild_votes WHERE town=$1 AND round=$2 AND discord_id=$3",
                                   town, round_no, discord_id)
        done = await done_projects(conn, town)
    return {**{k: int(v) for k, v in dict(totals).items()}, "rank": rank, "run": dict(run) if run else None, "vote": vote,
            "cap": rules.daily_cap(done), "discord_cap": rules.discord_cap(done)}

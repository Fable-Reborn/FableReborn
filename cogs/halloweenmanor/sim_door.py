"""Odds and fairness checks for the phantom door. No Discord required.

Run from the repo root:

    python -m cogs.halloweenmanor.sim_door
"""

from __future__ import annotations

import random
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:
    from .door_logic import (
        DOOR_DIR,
        EST,
        ETHEREAL_CHANCE,
        LAUNCH_DOORS,
        MIN_GAP_SECONDS,
        STEADY_DOORS,
        TREAT_CHANCE,
        TRICK_CHANCE,
        image_key,
        image_path,
        plan_night,
        settle_door,
        two_hand_stat,
    )
except ImportError:
    ROOT = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(ROOT))
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from door_logic import (
        DOOR_DIR,
        EST,
        ETHEREAL_CHANCE,
        LAUNCH_DOORS,
        MIN_GAP_SECONDS,
        STEADY_DOORS,
        TREAT_CHANCE,
        TRICK_CHANCE,
        image_key,
        image_path,
        plan_night,
        settle_door,
        two_hand_stat,
    )


CHECKS = []


def check(name: str, ok: bool, detail: str = ""):
    CHECKS.append((name, ok, detail))
    mark = "OK" if ok else "FAIL"
    extra = f" — {detail}" if detail else ""
    print(f"[{mark}] {name}{extra}")


def simulate_night(rng, started_at, hours, players, knock_fn):
    ends_at = started_at + timedelta(hours=hours)
    spawns = plan_night(started_at, ends_at, rng)
    pity = {}
    records = []
    for when in spawns:
        knockers = [player for player, _kind in players if knock_fn(player, when, rng)]
        names = {player: f"P{player}" for player in knockers}
        result = settle_door(knockers, pity, rng, visitor_name="{visitor}")
        records.append((when, knockers, result, dict(pity)))
        _ = names
    return spawns, records


def main():
    rng = random.Random(20261018)
    required = (
        "closed",
        "ajar",
        "ajar-ethereal",
        "ethereal",
        "trick-goblin",
        "trick-bag",
        "trick-chimney",
        "trick-stick",
        "treat-hostess",
        "treat-host",
        "treat-spirit",
        "treat-table",
    )
    missing = [key for key in required if not image_path(key).is_file()]
    check("all door art present", not missing, ", ".join(missing) if missing else f"{len(required)} files in {DOOR_DIR}")
    check("trick image keys", image_key("trick", "stick") == "trick-stick")
    check("ethereal ajar key", image_key("ajar", "ethereal") == "ajar-ethereal")

    start = datetime(2026, 10, 18, 16, 0, tzinfo=EST).astimezone(timezone.utc)
    launch_spawns = plan_night(start, start + timedelta(hours=24), rng)
    hours = Counter(stamp.astimezone(EST).hour for stamp in launch_spawns)
    gaps = [ (b - a).total_seconds() for a, b in zip(launch_spawns, launch_spawns[1:]) ]
    check(
        "launch 24h door count",
        LAUNCH_DOORS[0] * 0.4 <= len(launch_spawns) <= LAUNCH_DOORS[1],
        f"{len(launch_spawns)} doors, hours={dict(sorted(hours.items()))}",
    )
    check("doors can land any hour", len(hours) >= 8, f"{len(hours)} distinct hours")
    check("minimum gap", all(gap >= MIN_GAP_SECONDS - 1 for gap in gaps), f"min gap {min(gaps) if gaps else 0:.0f}s")

    night_start = start
    long_rng = random.Random(99)
    long_night = plan_night(night_start, night_start + timedelta(days=5), long_rng)
    day5_start = night_start + timedelta(days=4)
    day5 = [stamp for stamp in long_night if day5_start <= stamp < day5_start + timedelta(hours=24)]
    check(
        "steady day after launch window",
        STEADY_DOORS[0] * 0.4 <= len(day5) <= STEADY_DOORS[1] + 2,
        f"{len(day5)} doors on day 5",
    )

    always = list(range(1, 6))
    casual = list(range(10, 18))
    owl = list(range(20, 23))
    players = [(pid, "always") for pid in always] + [(pid, "casual") for pid in casual] + [(pid, "owl") for pid in owl]

    def will_knock(player, when, roll_rng):
        hour = when.astimezone(EST).hour
        if player in always:
            return True
        if player in owl:
            return hour >= 22 or hour < 1
        if 16 <= hour < 23:
            return roll_rng.random() < 0.55
        return roll_rng.random() < 0.15

    outcomes = Counter()
    variants = Counter()
    visits = Counter()
    knocks = Counter()
    crumbs = 0
    sticks = 0
    ethereal_stats = Counter()
    ethereal_hands = Counter()
    solo_ethereal = 0
    solo_doors = 0
    bags = 0
    nights = 40
    bad_stats = []
    for seed in range(nights):
        night_rng = random.Random(1000 + seed)
        _spawns, records = simulate_night(
            night_rng,
            start + timedelta(days=seed % 3),
            24,
            players,
            will_knock,
        )
        for when, knockers, result, _pity in records:
            outcomes[result.outcome] += 1
            variants[result.variant] += 1
            if len(knockers) == 1:
                solo_doors += 1
                if result.outcome == "ethereal":
                    solo_ethereal += 1
            for user_id in knockers:
                knocks[user_id] += 1
            if result.visitor_id is not None:
                visits[result.visitor_id] += 1
            for receipt in result.receipts:
                if not receipt.visitor:
                    crumbs += 1
                if receipt.bags:
                    bags += 1
                if receipt.item and receipt.item.name == "Stick of Shame":
                    sticks += 1
                    check_once = receipt.item.damage == 1
                    if not check_once:
                        check("stick is 1 stat", False, str(receipt.item.damage))
                if receipt.item and receipt.item.name != "Stick of Shame":
                    two_hand = receipt.item.hand == "both"
                    ethereal_hands["2h" if two_hand else "1h"] += 1
                    stat = receipt.item.armor or receipt.item.damage
                    ethereal_stats[stat] += 1
                    if two_hand and (stat % 2 == 0 or stat < two_hand_stat(81)):
                        bad_stats.append(("2h", receipt.item.name, stat))
                    if not two_hand and (stat % 2 == 0 or stat < 81):
                        bad_stats.append(("1h", receipt.item.name, stat))

    total = sum(outcomes.values())
    trick_rate = outcomes["trick"] / total if total else 0
    treat_rate = outcomes["treat"] / total if total else 0
    ether_rate = outcomes["ethereal"] / total if total else 0
    empty_rate = outcomes["empty"] / total if total else 0
    check("sim ran doors", total > 200, f"{total} doors across {nights} nights")
    check("trick near 45%", abs(trick_rate - TRICK_CHANCE) < 0.12, f"{trick_rate:.1%}")
    check("treat near 50%", abs(treat_rate - TREAT_CHANCE) < 0.12, f"{treat_rate:.1%}")
    check("ethereal under 8%", ether_rate < 0.08, f"{ether_rate:.1%} (target {ETHEREAL_CHANCE:.0%} of 2+ doors)")
    check("no solo ethereal", solo_ethereal == 0, f"{solo_ethereal} of {solo_doors} solo doors")
    check("crumbs exist", crumbs > 0, f"{crumbs} neighbor crumbs, {bags} bags, {sticks} sticks")

    always_visits = sum(visits[pid] for pid in always)
    casual_visits = sum(visits[pid] for pid in casual)
    always_knocks = sum(knocks[pid] for pid in always)
    casual_knocks = sum(knocks[pid] for pid in casual)
    always_rate = always_visits / always_knocks if always_knocks else 0
    casual_rate = casual_visits / casual_knocks if casual_knocks else 0
    check(
        "always-online do not take every door",
        always_rate < 0.55,
        f"always win {always_rate:.1%} of their knocks, casual {casual_rate:.1%}",
    )
    check(
        "casual players still get visits",
        casual_visits > 0,
        f"{casual_visits} visits from {casual_knocks} casual knocks",
    )
    spread = [visits[pid] for pid in always]
    check(
        "always-online visits are spread",
        (max(spread) - min(spread)) <= max(spread) * 0.75 if spread else False,
        f"always visits {spread}",
    )

    odd_ok = all(stat % 2 == 1 for stat in ethereal_stats) and not bad_stats
    check("ethereal stats all odd high", odd_ok, f"{dict(sorted(ethereal_stats.items()))} bad={bad_stats[:5]}")
    check("ethereal includes 2h", ethereal_hands["2h"] > 0, f"{dict(ethereal_hands)}")

    failed = [name for name, ok, _detail in CHECKS if not ok]
    print()
    print(f"Outcomes: {dict(outcomes)}")
    print(f"Variants: {dict(variants)}")
    print(f"RESULT: {len(CHECKS) - len(failed)} checks passed, {len(failed)} failed")
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

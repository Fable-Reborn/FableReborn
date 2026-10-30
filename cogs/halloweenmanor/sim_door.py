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
        CHAOS_BURST,
        CHAOS_WAVE_GAP_SECONDS,
        DOOR_DIR,
        EST,
        ETHEREAL_CHANCE,
        LAUNCH_DOORS,
        MIN_GAP_SECONDS,
        STEADY_DOORS,
        TREAT_CHANCE,
        TRICK_CHANCE,
        Pity,
        image_key,
        image_path,
        parse_window,
        plan_chaos,
        plan_night,
        settle_door,
        two_hand_stat,
    )
    from .rewards import THEME_KEYS, OWNED_THEME_BONUS, reward_for, theme_name
except ImportError:
    ROOT = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(ROOT))
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from door_logic import (
        CHAOS_BURST,
        CHAOS_WAVE_GAP_SECONDS,
        DOOR_DIR,
        EST,
        ETHEREAL_CHANCE,
        LAUNCH_DOORS,
        MIN_GAP_SECONDS,
        STEADY_DOORS,
        TREAT_CHANCE,
        TRICK_CHANCE,
        Pity,
        image_key,
        image_path,
        parse_window,
        plan_chaos,
        plan_night,
        settle_door,
        two_hand_stat,
    )
    from rewards import THEME_KEYS, OWNED_THEME_BONUS, reward_for, theme_name


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
                    expected = two_hand_stat(99) if two_hand else 99
                    if stat != expected:
                        bad_stats.append(("2h" if two_hand else "1h", receipt.item.name, stat))

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

    odd_ok = ethereal_stats.keys() <= {99, two_hand_stat(99)} and not bad_stats
    check("ethereal stats are the top window", odd_ok, f"{dict(sorted(ethereal_stats.items()))} bad={bad_stats[:5]}")
    check("ethereal includes 2h", ethereal_hands["2h"] > 0, f"{dict(ethereal_hands)}")

    check("chaos window 8h", parse_window("8h") == 8 * 3600, str(parse_window("8h")))
    chaos_rng = random.Random(7)
    chaos_start = start
    chaos_end = chaos_start + timedelta(hours=8)
    chaos_spawns = plan_chaos(chaos_start, chaos_end, chaos_rng)
    leads = [stamp for stamp, lead in chaos_spawns if lead]
    extras = [stamp for stamp, lead in chaos_spawns if not lead]
    lead_gaps = [(b - a).total_seconds() for a, b in zip(leads, leads[1:])]
    check("chaos 8h has many doors", 80 <= len(chaos_spawns) <= 500, f"{len(chaos_spawns)} doors, {len(leads)} clusters")
    check("chaos clusters exist", 20 <= len(leads) <= 80, f"{len(leads)} leads")
    check(
        "chaos wave gap 8-15 min",
        all(CHAOS_WAVE_GAP_SECONDS[0] - 1 <= gap <= CHAOS_WAVE_GAP_SECONDS[1] + 1 for gap in lead_gaps),
        f"min {min(lead_gaps) if lead_gaps else 0:.0f}s max {max(lead_gaps) if lead_gaps else 0:.0f}s",
    )
    burst_ok = True
    burst_sizes = []
    extra_delays = []
    for lead in leads[:-1]:
        cluster = [stamp for stamp, _lead in chaos_spawns if stamp >= lead and (stamp - lead).total_seconds() <= 12]
        extras_in = [stamp for stamp in cluster if stamp != lead]
        burst_sizes.append(len(extras_in))
        extra_delays.extend((stamp - lead).total_seconds() for stamp in extras_in)
        if not (CHAOS_BURST[0] <= len(extras_in) <= CHAOS_BURST[1]):
            burst_ok = False
    check("chaos burst is 3-8 extras", burst_ok and burst_sizes, f"sizes {Counter(burst_sizes)}")
    check(
        "chaos extras land within seconds",
        extra_delays and max(extra_delays) <= 12 and min(extra_delays) > 0,
        f"delay {min(extra_delays):.2f}-{max(extra_delays):.2f}s" if extra_delays else "none",
    )

    sitout_wins = Counter()
    chaos_wins = Counter()
    for seed in range(40):
        blocked = settle_door(
            [1, 2],
            {1: Pity(extra_tickets=4, sitout_left=2), 2: Pity()},
            random.Random(seed),
            chaos=False,
        )
        sitout_wins[blocked.visitor_id] += 1
        allowed = settle_door(
            [1, 2],
            {1: Pity(extra_tickets=4, sitout_left=2), 2: Pity()},
            random.Random(seed),
            chaos=True,
        )
        chaos_wins[allowed.visitor_id] += 1
    check("sitout benches on a normal door", sitout_wins.get(1, 0) == 0, str(dict(sitout_wins)))
    check("chaos ignores sitout", chaos_wins.get(1, 0) > 10, str(dict(chaos_wins)))

    two = reward_for(joined_as="active", rooms=2, cleared=False, struggling=False, owns_theme=False)
    two_clear = reward_for(joined_as="active", rooms=2, cleared=True, struggling=False, owns_theme=False)
    three = reward_for(joined_as="active", rooms=3, cleared=False, struggling=False, owns_theme=False)
    three_clear = reward_for(joined_as="active", rooms=3, cleared=True, struggling=False, owns_theme=False)
    watch = reward_for(joined_as="passive", rooms=0, cleared=True, struggling=False, owns_theme=False)
    struggle = reward_for(joined_as="active", rooms=3, cleared=False, struggling=True, owns_theme=False)
    owned = reward_for(joined_as="active", rooms=3, cleared=True, struggling=False, owns_theme=True)
    check("two-room theme 12%", two.theme_chance == 0.12, str(two.theme_chance))
    check("two-room clear theme 24%", two_clear.theme_chance == 0.24, str(two_clear.theme_chance))
    check("three-room theme 25%", three.theme_chance == 0.25, str(three.theme_chance))
    check("three-room clear theme 50%", three_clear.theme_chance == 0.50, str(three_clear.theme_chance))
    check("watchers get no theme", watch.theme_chance == 0.0)
    check("struggling raid gets no theme", struggle.theme_chance == 0.0)
    check(
        "owned-all pays bones instead",
        owned.theme_chance == 0.0 and owned.bones == three_clear.bones + OWNED_THEME_BONUS,
        f"bones {owned.bones} vs {three_clear.bones}",
    )
    check("theme names resolve", all(theme_name(key) for key in THEME_KEYS), ", ".join(THEME_KEYS))

    theme_rng = random.Random(42)
    grants = Counter()
    trials = 8000
    for _ in range(trials):
        spec = reward_for(joined_as="active", rooms=3, cleared=True, struggling=False, owns_theme=False)
        if theme_rng.random() < spec.theme_chance:
            grants[theme_rng.choice(THEME_KEYS)] += 1
    rate = sum(grants.values()) / trials
    check("sim full-clear theme rate ~50%", 0.47 <= rate <= 0.53, f"{rate:.1%} {dict(grants)}")
    check("all four Halloween themes drop", set(grants) == set(THEME_KEYS), str(dict(grants)))

    failed = [name for name, ok, _detail in CHECKS if not ok]
    print()
    print(f"Outcomes: {dict(outcomes)}")
    print(f"Variants: {dict(variants)}")
    print(f"RESULT: {len(CHECKS) - len(failed)} checks passed, {len(failed)} failed")
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

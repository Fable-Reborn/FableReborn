"""Pure phantom-door math: schedule, pity tickets, outcomes, and payouts."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

from classes.items import ItemType

try:
    from zoneinfo import ZoneInfo

    EST = ZoneInfo("America/New_York")
except Exception:
    # Windows hosts without tzdata still run the sim. The cluster has zoneinfo.
    EST = timezone(timedelta(hours=-4), name="EDT")
DOOR_DIR = Path(__file__).resolve().parents[2] / "assets" / "halloween" / "door"

KNOCK_SECONDS = 90
REVEAL_SECONDS = 2.5
LINGER_SECONDS = 30
MIN_GAP_SECONDS = 45 * 60
LAUNCH_HOURS = 72
LAUNCH_DOORS = (18, 22)
STEADY_DOORS = (12, 15)
SLOT_SECONDS = 5 * 60
MAX_WINDOW_SECONDS = 14 * 24 * 3600
CHAOS_FIRST_SECONDS = (20, 45)
CHAOS_WAVE_GAP_SECONDS = (8 * 60, 15 * 60)
CHAOS_BURST = (3, 8)
CHAOS_BURST_STEP = (0.45, 1.15)
CHAOS_MAX_LIVE = 10

TRICK_CHANCE = 0.45
TREAT_CHANCE = 0.50
ETHEREAL_CHANCE = 0.05
MIN_KNOCKERS_FOR_ETHEREAL = 2

CRUMB_BONES = (15, 25)
CRUMB_BAG_CHANCE = 0.15
TRICK_BONES = (20, 40)
TREAT_BONES = (50, 90)
TREAT_BAG_CHANCE = 0.40

MAX_EXTRA_TICKETS = 4
SITOUT_DOORS = 2
PITY_GUARANTEE_AFTER = 5

# Ethereal weapons always use the top window (99 one-hand / 197 two-hand).
ONE_HAND_BANDS = (
    (0.60, (81, 83, 85, 87, 89)),
    (0.30, (91, 93, 95, 97)),
    (0.10, (99,)),
)
ETHEREAL_STAT_BAND = ONE_HAND_BANDS[-1][1]

TRICK_VARIANTS = ("goblin", "bag", "chimney", "stick")
TREAT_VARIANTS = ("hostess", "host", "spirit", "table")

ETHEREAL_WEAPONS = (
    ("The Last Latch", ItemType.Sword),
    ("Widow's Lantern", ItemType.Wand),
    ("Cailleach's Nail", ItemType.Dagger),
    ("Harvest Debt", ItemType.Scythe),
    ("Frost-Latch Spear", ItemType.Spear),
    ("Bonewick", ItemType.Hammer),
    ("Threshold", ItemType.Shield),
    ("Moon-String", ItemType.Bow),
    ("Night Bell", ItemType.Mace),
)

STICK_NAME = "Stick of Shame"
STICK_TYPE = ItemType.Knife

TRICK_LINES = {
    "goblin": (
        "{visitor} knocks. A goblin lunges out of the smoke, all teeth and no manners. **It's a trick.**",
        "The door spits a goblin at {visitor}. It cackles, empty-handed except for the insult. **It's a trick.**",
    ),
    "bag": (
        "{visitor} knocks. A goblin upends a sack of coal, rocks, and one sad pumpkin. **It's a trick.**",
        "A sack hits the leaves at {visitor}'s feet. Coal. A skull. No candy. **It's a trick.**",
    ),
    "chimney": (
        "{visitor} knocks. Something comes out of the door the wrong way up and lands grinning. **It's a trick.**",
        "The threshold burps. A goblin hits the dirt in front of {visitor} upside down, delighted. **It's a trick.**",
    ),
    "stick": (
        "{visitor} knocks. A jester leans out and presses a sad little stick into their hands. **It's a trick.**",
        "Bells jingle. {visitor} has been given the **Stick of Shame**. The forest thinks this is very funny. **It's a trick.**",
    ),
}

TREAT_LINES = {
    "hostess": (
        "{visitor} knocks. A woman in a crown steps out of the smoke with a tray. **It's a treat.**",
        "The door opens for {visitor} like a guest of honor. She already knew their name. **It's a treat.**",
    ),
    "host": (
        "{visitor} knocks. A man in velvet offers the bowl as if this forest were a ballroom. **It's a treat.**",
        "Lantern light catches a smile. {visitor} is handed candy from a door that has no house. **It's a treat.**",
    ),
    "spirit": (
        "{visitor} knocks. A candy-witch spills out of the firelight, tossing sweets like sparks. **It's a treat.**",
        "The smoke turns orange and cheerful. {visitor} gets a handful of impossible candy. **It's a treat.**",
    ),
    "table": (
        "{visitor} knocks. The door dumps a whole porch-worth of sweets onto the leaves. **It's a treat.**",
        "Cupcakes and candy corn pour through the threshold at {visitor}'s feet. **It's a treat.**",
    ),
}

ETHEREAL_LINES = (
    "The door goes pale and opens before {visitor}'s hand. Something older than the woods is already waiting. **A blessing.**",
)

QUEUE_LINES = (
    "A door is standing in the woods. It should not be. Press **Knock** if you will wait on the leaves.",
)


@dataclass
class Pity:
    extra_tickets: int = 0
    consecutive_misses: int = 0
    sitout_left: int = 0


@dataclass
class ItemGrant:
    name: str
    type_: str
    hand: str
    damage: int
    armor: int
    element: str
    value: int


@dataclass
class Receipt:
    user_id: int
    visitor: bool
    outcome: str
    variant: str
    bones: int
    bags: int
    item: ItemGrant | None = None
    summary: str = ""


@dataclass
class DoorResult:
    outcome: str
    variant: str
    visitor_id: int | None
    story: str
    ajar_key: str
    reveal_key: str
    receipts: list[Receipt] = field(default_factory=list)


def parse_window(text: str | None) -> int | None:
    if text is None:
        return 24 * 3600
    raw = text.strip().lower().replace(" ", "")
    if not raw:
        return 24 * 3600
    unit = raw[-1]
    try:
        amount = int(raw[:-1])
    except ValueError:
        return None
    if amount <= 0:
        return None
    seconds = {"m": 60, "h": 3600, "d": 86400}.get(unit)
    if seconds is None:
        return None
    total = amount * seconds
    if total > MAX_WINDOW_SECONDS:
        return None
    return total


def doors_for_day(night_started: datetime, day_start: datetime) -> tuple[int, int]:
    elapsed = (day_start - night_started).total_seconds()
    if elapsed < LAUNCH_HOURS * 3600:
        return LAUNCH_DOORS
    return STEADY_DOORS


def slot_weight(moment: datetime) -> float:
    del moment
    return 1.0


def _eligible_slots(start: datetime, end: datetime) -> list[datetime]:
    slots = []
    cursor = start.replace(microsecond=0)
    remainder = cursor.timestamp() % SLOT_SECONDS
    if remainder:
        cursor += timedelta(seconds=SLOT_SECONDS - remainder)
    while cursor < end:
        slots.append(cursor)
        cursor += timedelta(seconds=SLOT_SECONDS)
    return slots


def plan_spawns(start: datetime, end: datetime, count: int, rng) -> list[datetime]:
    """Pick `count` times in the window, any hour, with a minimum gap between doors."""
    slots = _eligible_slots(start, end)
    if not slots or count <= 0:
        return []
    chosen: list[datetime] = []
    remaining = list(slots)
    for _ in range(count):
        weighted = []
        weights = []
        for slot in remaining:
            if any(abs((slot - taken).total_seconds()) < MIN_GAP_SECONDS for taken in chosen):
                continue
            weight = slot_weight(slot)
            if weight <= 0:
                continue
            weighted.append(slot)
            weights.append(weight)
        if not weighted:
            break
        pick = rng.choices(weighted, weights=weights, k=1)[0]
        chosen.append(pick)
        remaining = [slot for slot in remaining if slot != pick]
    chosen.sort()
    return chosen


def plan_night(started_at: datetime, ends_at: datetime, rng) -> list[datetime]:
    """Fill each 24-hour slice of the night. Launch density applies to the first 72 hours."""
    if ends_at <= started_at:
        return []
    spawns: list[datetime] = []
    cursor = started_at
    while cursor < ends_at:
        chunk_end = min(ends_at, cursor + timedelta(hours=24))
        low, high = doors_for_day(started_at, cursor)
        count = rng.randint(low, high)
        span = max(1.0, (chunk_end - cursor).total_seconds())
        if span < 20 * 3600:
            count = max(1, round(count * span / 86400))
        spawns.extend(plan_spawns(cursor, chunk_end, count, rng))
        cursor = chunk_end
    return sorted(spawns)


def plan_chaos(started_at: datetime, ends_at: datetime, rng) -> list[tuple[datetime, bool]]:
    """Random waves: one lead door, then 3–8 more within seconds, repeating through the window."""
    if ends_at <= started_at:
        return []
    spawns: list[tuple[datetime, bool]] = []
    cursor = started_at + timedelta(seconds=rng.randint(*CHAOS_FIRST_SECONDS))
    while cursor < ends_at:
        spawns.append((cursor, True))
        delay = 0.0
        for _ in range(rng.randint(*CHAOS_BURST)):
            delay += rng.uniform(*CHAOS_BURST_STEP)
            when = cursor + timedelta(seconds=delay)
            if when < ends_at:
                spawns.append((when, False))
        cursor = cursor + timedelta(seconds=rng.randint(*CHAOS_WAVE_GAP_SECONDS))
    return spawns


def tickets_for(pity: Pity, *, ignore_sitout: bool = False) -> int:
    if not ignore_sitout and pity.sitout_left > 0:
        return 0
    return 1 + max(0, min(pity.extra_tickets, MAX_EXTRA_TICKETS))


def pick_visitor(
    knockers: list[int],
    pity_map: dict[int, Pity],
    rng,
    *,
    ignore_sitout: bool = False,
) -> int | None:
    if not knockers:
        return None
    guaranteed = [
        user_id
        for user_id in knockers
        if pity_map.get(user_id, Pity()).consecutive_misses >= PITY_GUARANTEE_AFTER
        and (ignore_sitout or pity_map.get(user_id, Pity()).sitout_left <= 0)
    ]
    if guaranteed:
        return rng.choice(guaranteed)
    eligible = []
    weights = []
    for user_id in knockers:
        tickets = tickets_for(pity_map.get(user_id, Pity()), ignore_sitout=ignore_sitout)
        if tickets <= 0:
            continue
        eligible.append(user_id)
        weights.append(tickets)
    if not eligible:
        return rng.choice(knockers)
    return rng.choices(eligible, weights=weights, k=1)[0]


def update_pity(
    knockers: list[int],
    visitor_id: int | None,
    pity_map: dict[int, Pity],
    *,
    apply_sitout: bool = True,
) -> dict[int, Pity]:
    for user_id in knockers:
        pity = pity_map.setdefault(user_id, Pity())
        if pity.sitout_left > 0:
            pity.sitout_left -= 1
        if visitor_id is not None and user_id == visitor_id:
            pity.extra_tickets = 0
            pity.consecutive_misses = 0
            pity.sitout_left = SITOUT_DOORS if apply_sitout else 0
        else:
            pity.consecutive_misses += 1
            pity.extra_tickets = min(MAX_EXTRA_TICKETS, pity.extra_tickets + 1)
    return pity_map


def pick_outcome(knocker_count: int, rng) -> str:
    roll = rng.random()
    if knocker_count >= MIN_KNOCKERS_FOR_ETHEREAL and roll >= (1.0 - ETHEREAL_CHANCE):
        return "ethereal"
    cutoff = TRICK_CHANCE / (TRICK_CHANCE + TREAT_CHANCE)
    # When ethereal is impossible, keep the trick/treat ratio the same.
    if knocker_count < MIN_KNOCKERS_FOR_ETHEREAL:
        return "trick" if roll < cutoff else "treat"
    if roll < TRICK_CHANCE:
        return "trick"
    return "treat"


def pick_variant(outcome: str, rng) -> str:
    if outcome == "trick":
        return rng.choice(TRICK_VARIANTS)
    if outcome == "treat":
        return rng.choice(TREAT_VARIANTS)
    return "ethereal"


def image_key(kind: str, variant: str | None = None) -> str:
    if kind == "closed":
        return "closed"
    if kind == "ajar":
        return "ajar-ethereal" if variant == "ethereal" else "ajar"
    if kind == "ethereal":
        return "ethereal"
    if kind in ("trick", "treat") and variant:
        return f"{kind}-{variant}"
    return "closed"


def image_path(key: str) -> Path:
    jpg = DOOR_DIR / f"{key}.jpg"
    png = DOOR_DIR / f"{key}.png"
    if jpg.is_file():
        return jpg
    return png


def two_hand_stat(one_hand: int) -> int:
    return one_hand * 2 - 1


def roll_ethereal_stat(two_handed: bool, rng) -> int:
    del rng
    stat = ETHEREAL_STAT_BAND[-1]
    return two_hand_stat(stat) if two_handed else stat


def make_ethereal_item(rng) -> ItemGrant:
    name, type_ = rng.choice(ETHEREAL_WEAPONS)
    two_handed = type_.get_hand().value == "both"
    stat = roll_ethereal_stat(two_handed, rng)
    if type_ is ItemType.Shield:
        damage, armor = 0, stat
    else:
        damage, armor = stat, 0
    element = rng.choice(("Dark", "Light", "Corrupted", "Nature", "Wind"))
    return ItemGrant(
        name=name,
        type_=type_.value,
        hand=type_.get_hand().value,
        damage=damage,
        armor=armor,
        element=element,
        value=rng.randint(180, 420),
    )


def make_stick(rng) -> ItemGrant:
    return ItemGrant(
        name=STICK_NAME,
        type_=STICK_TYPE.value,
        hand=STICK_TYPE.get_hand().value,
        damage=1,
        armor=0,
        element="Dark",
        value=1,
    )


def _line(pool, visitor: str, rng) -> str:
    if isinstance(pool, tuple) and pool and isinstance(pool[0], str):
        template = rng.choice(pool)
    else:
        template = pool
    return template.format(visitor=visitor)


def settle_door(
    knockers: list[int],
    pity_map: dict[int, Pity],
    rng,
    visitor_name: str = "{visitor}",
    *,
    chaos: bool = False,
) -> DoorResult:
    visitor_id = pick_visitor(knockers, pity_map, rng, ignore_sitout=chaos)
    if visitor_id is None:
        return DoorResult(
            outcome="empty",
            variant="closed",
            visitor_id=None,
            story="The door waited. Nobody knocked. The smoke closed over the path.",
            ajar_key="ajar",
            reveal_key="closed",
        )
    outcome = pick_outcome(len(knockers), rng)
    variant = pick_variant(outcome, rng)
    if outcome == "trick":
        story = _line(TRICK_LINES[variant], visitor_name, rng)
        ajar_key = "ajar"
        reveal_key = image_key("trick", variant)
    elif outcome == "treat":
        story = _line(TREAT_LINES[variant], visitor_name, rng)
        ajar_key = "ajar"
        reveal_key = image_key("treat", variant)
    else:
        story = _line(ETHEREAL_LINES, visitor_name, rng)
        ajar_key = "ajar-ethereal"
        reveal_key = "ethereal"

    receipts = []
    for user_id in knockers:
        visitor = user_id == visitor_id
        bags = 0
        item = None
        if visitor and outcome == "trick":
            bones = rng.randint(*TRICK_BONES)
            if variant == "stick":
                item = make_stick(rng)
            summary = "The door tricked you."
        elif visitor and outcome == "treat":
            bones = rng.randint(*TREAT_BONES)
            bags = 1 if rng.random() < TREAT_BAG_CHANCE else 0
            summary = "The door treated you."
        elif visitor and outcome == "ethereal":
            bones = rng.randint(*CRUMB_BONES)
            item = make_ethereal_item(rng)
            summary = "The door opened before you knocked."
        else:
            bones = rng.randint(*CRUMB_BONES)
            bags = 1 if rng.random() < CRUMB_BAG_CHANCE else 0
            summary = "You waited on the leaves while someone else knocked."
        receipts.append(
            Receipt(
                user_id=user_id,
                visitor=visitor,
                outcome=outcome,
                variant=variant,
                bones=bones,
                bags=bags,
                item=item,
                summary=summary,
            )
        )
    update_pity(knockers, visitor_id, pity_map, apply_sitout=not chaos)
    return DoorResult(
        outcome=outcome,
        variant=variant,
        visitor_id=visitor_id,
        story=story,
        ajar_key=ajar_key,
        reveal_key=reveal_key,
        receipts=receipts,
    )

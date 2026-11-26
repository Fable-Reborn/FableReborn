"""Pure logic for silent auctions and raffles: no Discord, no database.

Everything here is deterministic and unit-tested (tests/test_gm_events_logic.py).
"""
from __future__ import annotations

import datetime
import hashlib
import random
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Iterable, Optional, Sequence

from utils.birthday import parse_birthday_duration

MAX_AMOUNT = 10**15  # keeps every sum comfortably inside BIGINT
MAX_TICKET_PRICE = 10**12  # price * 1000 tickets stays <= MAX_AMOUNT
MAX_TICKETS_PER_PURCHASE = 1000

SILENT_MIN_DURATION = datetime.timedelta(minutes=5)
SILENT_MAX_DURATION = datetime.timedelta(days=14)
RAFFLE_MIN_DURATION = datetime.timedelta(minutes=5)
RAFFLE_MAX_DURATION = datetime.timedelta(days=30)

_SUFFIXES = {"k": 10**3, "m": 10**6, "b": 10**9}
_AMOUNT_RE = re.compile(r"^([0-9]+(?:\.[0-9]+)?)([kmb]?)$")


def parse_amount(text: str, *, cap: int = MAX_AMOUNT) -> int:
    """Strictly parse ``1000``, ``1,000``, ``1k``, ``1.5m``. Raises ValueError."""
    raw = str(text or "").strip().lower().replace(",", "").replace("_", "").lstrip("$")
    raw = raw.strip()
    match = _AMOUNT_RE.match(raw)
    if not match:
        raise ValueError("Enter a whole number such as `1000`, `1,000`, `5k` or `1.5m`.")
    number, suffix = match.groups()
    try:
        value = Decimal(number) * _SUFFIXES.get(suffix, 1)
    except InvalidOperation:  # pragma: no cover - regex already guards this
        raise ValueError("Enter a whole number.")
    if value != value.to_integral_value():
        raise ValueError("The amount must be a whole number.")
    amount = int(value)
    if amount <= 0:
        raise ValueError("The amount must be greater than zero.")
    if amount > cap:
        raise ValueError("That amount is too large.")
    return amount


def parse_quantity(text: str) -> int:
    raw = str(text or "").strip().replace(",", "")
    if not raw.isdigit() or not raw.isascii():
        raise ValueError("Enter a whole number of tickets.")
    qty = int(raw)
    if not 1 <= qty <= MAX_TICKETS_PER_PURCHASE:
        raise ValueError(f"You can buy 1 to {MAX_TICKETS_PER_PURCHASE} tickets at a time.")
    return qty


def parse_duration(
    value: str, minimum: datetime.timedelta, maximum: datetime.timedelta
) -> datetime.timedelta:
    """Reuses the shared ``24h`` / ``1d12h`` / ``90m`` parser, then applies our bounds."""
    try:
        duration = parse_birthday_duration(value)
    except ValueError as exc:
        if "30 days" in str(exc):  # shared parser's birthday-specific cap
            raise ValueError(f"Duration cannot be longer than {_fmt(maximum)}.") from None
        raise
    if duration < minimum:
        raise ValueError(f"Duration must be at least {_fmt(minimum)}.")
    if duration > maximum:
        raise ValueError(f"Duration cannot be longer than {_fmt(maximum)}.")
    return duration


def _fmt(delta: datetime.timedelta) -> str:
    seconds = int(delta.total_seconds())
    if seconds % 86400 == 0:
        return f"{seconds // 86400}d"
    if seconds % 3600 == 0:
        return f"{seconds // 3600}h"
    return f"{seconds // 60}m"


# ---------------------------------------------------------------- silent auction


@dataclass(frozen=True)
class Bid:
    user_id: int
    amount: int
    amount_set_at: datetime.datetime


def pick_silent_winner(bids: Iterable[Bid]) -> Optional[Bid]:
    """Highest amount; ties go to whoever reached it first; then lowest user id."""
    bids = list(bids)
    if not bids:
        return None
    return min(bids, key=lambda b: (-b.amount, b.amount_set_at, b.user_id))


# ---------------------------------------------------------------------- raffle


def make_seed_secret(rng_bytes: bytes) -> str:
    return rng_bytes.hex()


def commitment(seed_secret: str) -> str:
    return hashlib.sha256(seed_secret.encode()).hexdigest()


def build_tickets(purchases: Iterable[tuple[int, int]]) -> list[tuple[int, int]]:
    """``purchases`` is ``(user_id, quantity)`` in purchase order.

    Returns ``(ticket_no, user_id)`` numbered 1..N.
    """
    tickets: list[tuple[int, int]] = []
    for user_id, quantity in purchases:
        for _ in range(quantity):
            tickets.append((len(tickets) + 1, user_id))
    return tickets


def ticket_digest(tickets: Sequence[tuple[int, int]]) -> str:
    canonical = ",".join(f"{no}:{user}" for no, user in tickets)
    return hashlib.sha256(canonical.encode()).hexdigest()


def draw_winner(
    seed_secret: str, tickets: Sequence[tuple[int, int]]
) -> Optional[tuple[int, int, str]]:
    """Shuffle every ticket (Fisher-Yates via ``random.Random``), then pick one.

    Returns ``(winning_ticket_no, user_id, ticket_digest)`` or ``None`` with no tickets.
    Anyone holding the revealed seed and the ticket list can reproduce this.
    """
    digest = ticket_digest(tickets)
    if not tickets:
        return None
    seed = hashlib.sha256(f"{seed_secret}:{digest}".encode()).digest()
    rng = random.Random(int.from_bytes(seed, "big"))
    shuffled = list(tickets)
    rng.shuffle(shuffled)
    ticket_no, user_id = shuffled[rng.randrange(len(shuffled))]
    return ticket_no, user_id, digest

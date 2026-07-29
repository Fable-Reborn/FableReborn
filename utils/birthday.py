"""Shared state helpers for the temporary Game Master birthday assistant."""

from __future__ import annotations

import datetime
import re
from dataclasses import dataclass


UTC = datetime.timezone.utc
MAX_BIRTHDAY_DURATION = datetime.timedelta(days=30)
_DURATION_PART = re.compile(r"(?P<amount>\d+)\s*(?P<unit>[smhdw])", re.IGNORECASE)


def ensure_utc(value: datetime.datetime) -> datetime.datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


@dataclass(frozen=True)
class BirthdayAssistantState:
    user_id: int
    character_name: str
    ends_at: datetime.datetime

    def is_active(self, *, now: datetime.datetime | None = None) -> bool:
        current = ensure_utc(now or datetime.datetime.now(UTC))
        return current < ensure_utc(self.ends_at)


@dataclass(frozen=True)
class BirthdayAssistantIdentity:
    """Minimal Discord-user shape used to build an independent combat clone."""

    id: int
    display_name: str

    @property
    def mention(self) -> str:
        return f"<@{self.id}>"

    def __str__(self) -> str:
        return self.display_name


def parse_birthday_duration(value: str) -> datetime.timedelta:
    """Parse compact durations such as ``24h``, ``1d12h``, or ``30m``."""

    raw = str(value or "").strip().lower()
    if not raw:
        raise ValueError("Provide a duration such as `24h`, `1d`, or `90m`.")

    seconds_per_unit = {
        "s": 1,
        "m": 60,
        "h": 60 * 60,
        "d": 24 * 60 * 60,
        "w": 7 * 24 * 60 * 60,
    }
    total_seconds = 0
    position = 0
    matched = False
    for match in _DURATION_PART.finditer(raw):
        if raw[position : match.start()].strip():
            raise ValueError("Use a duration such as `24h`, `1d12h`, or `90m`.")
        matched = True
        total_seconds += int(match.group("amount")) * seconds_per_unit[match.group("unit")]
        position = match.end()

    if not matched or raw[position:].strip():
        raise ValueError("Use a duration such as `24h`, `1d12h`, or `90m`.")
    if total_seconds <= 0:
        raise ValueError("Duration must be greater than zero.")

    duration = datetime.timedelta(seconds=total_seconds)
    if duration > MAX_BIRTHDAY_DURATION:
        raise ValueError("Birthday assistance cannot be enabled for more than 30 days.")
    return duration


def get_active_birthday_assistant(
    bot,
    *,
    now: datetime.datetime | None = None,
) -> BirthdayAssistantState | None:
    state = getattr(bot, "birthday_assistant_state", None)
    if not isinstance(state, BirthdayAssistantState):
        return None
    if state.is_active(now=now):
        return state

    # Expired state is disabled in memory immediately. The persisted row may
    # remain until the next command/restart, but it can no longer affect fights.
    bot.birthday_assistant_state = None
    return None

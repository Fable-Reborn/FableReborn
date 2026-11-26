"""The builder's draft and its validation. Pure: no Discord, no database."""
from __future__ import annotations

import datetime
from dataclasses import dataclass
from typing import Optional

from utils.i18n import _

from . import logic
from .announce import KINDS

NAME_LIMIT = 200
TITLE_LIMIT = 100
MESSAGE_LIMIT = 1500
RAFFLE_CAP_LIMIT = 1000


@dataclass
class Draft:
    """Raw text exactly as the GM typed it, so a bad value can be corrected, not lost."""

    kind: str = "silent"
    name: str = ""  # item or prize
    min_bid: str = ""  # silent
    duration: str = ""  # silent, raffle
    ticket_price: str = ""  # raffle
    max_per_user: str = ""  # raffle
    title: str = ""
    message: str = ""
    ping: bool = True


@dataclass(frozen=True)
class Parsed:
    kind: str
    name: str
    title: str
    message: str
    ping: bool
    min_bid: Optional[int] = None
    duration: Optional[datetime.timedelta] = None  # None = no timer (classic / manual raffle)
    ticket_price: Optional[int] = None
    max_per_user: Optional[int] = None


def switch_kind(draft: Draft, kind: str) -> Draft:
    """Keep the shared fields (name, title, message, ping); clear everything type-specific."""
    if kind not in KINDS:
        raise ValueError(kind)
    return Draft(
        kind=kind, name=draft.name, title=draft.title, message=draft.message, ping=draft.ping
    )


def validate(draft: Draft) -> tuple[list[str], Optional[Parsed]]:
    errors: list[str] = []
    label = _("Prize") if draft.kind == "raffle" else _("Item")
    name = draft.name.strip()
    if not name:
        errors.append(_("{label} is required.").format(label=label))
    elif len(name) > NAME_LIMIT:
        errors.append(
            _("{label} must be at most {n} characters.").format(label=label, n=NAME_LIMIT)
        )
    if len(draft.title.strip()) > TITLE_LIMIT:
        errors.append(_("Title must be at most {n} characters.").format(n=TITLE_LIMIT))
    if len(draft.message.strip()) > MESSAGE_LIMIT:
        errors.append(_("Message must be at most {n} characters.").format(n=MESSAGE_LIMIT))

    min_bid = duration = ticket_price = max_per_user = None
    if draft.kind == "silent":
        try:
            min_bid = logic.parse_amount(draft.min_bid)
        except ValueError as exc:
            errors.append(_("Minimum bid: {error}").format(error=_(str(exc))))
        try:
            duration = logic.parse_duration(
                draft.duration, logic.SILENT_MIN_DURATION, logic.SILENT_MAX_DURATION
            )
        except ValueError as exc:
            errors.append(_("Duration: {error}").format(error=_(str(exc))))
    elif draft.kind == "raffle":
        try:
            ticket_price = logic.parse_amount(draft.ticket_price, cap=logic.MAX_TICKET_PRICE)
        except ValueError as exc:
            errors.append(_("Ticket price: {error}").format(error=_(str(exc))))
        raw_cap = draft.max_per_user.strip()
        if raw_cap:
            if (
                not (raw_cap.isascii() and raw_cap.isdigit())
                or not 1 <= int(raw_cap) <= RAFFLE_CAP_LIMIT
            ):
                errors.append(
                    _("Max tickets per player must be blank or 1-{n}.").format(n=RAFFLE_CAP_LIMIT)
                )
            else:
                max_per_user = int(raw_cap)
        if draft.duration.strip().lower() != "manual":
            try:
                duration = logic.parse_duration(
                    draft.duration, logic.RAFFLE_MIN_DURATION, logic.RAFFLE_MAX_DURATION
                )
            except ValueError as exc:
                errors.append(_("Duration: {error}").format(error=_(str(exc))))
    if errors:
        return errors, None
    return [], Parsed(
        kind=draft.kind,
        name=name,
        title=draft.title.strip(),
        message=draft.message.strip(),
        ping=draft.ping,
        min_bid=min_bid,
        duration=duration,
        ticket_price=ticket_price,
        max_per_user=max_per_user,
    )

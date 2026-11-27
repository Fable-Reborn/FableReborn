"""Get-well wishes: the rules for `$getwell`, a sibling of the birthday `$wish` event.

Players send a short message, staff approve it, each approved wisher picks
one thank-you, and a GM sends one card of every approved wish to the recipient with
`$gmgetwell send`. Wishes can be typed in any channel of the Fable server and are deleted at
once, so the recipient never sees them.

Nothing here touches the birthday event: it has its own tables and its own button ids. The
message rules are the birthday ones, imported from utils/wish.py rather than copied.

Discord-free so the cog and tests can share it.
"""
from __future__ import annotations

from utils import wish as base
from utils.wish import (  # noqa: F401  (re-exported: the cog and the tests use them from here)
    APPROVED, PENDING, REJECTED, WITHDRAWN, WishProblem, check_message, check_picks, clean_message,
    display_name, elixir_type,
)

# ---- settings ----------------------------------------------------------------------------------
GUILD_ID = base.GUILD_ID                  # wishers must be a member of this server
ALT_ROLE_ID = base.ALT_ROLE_ID            # ... and must not have this role (alt accounts)
REVIEW_CHANNEL_ID = 1570410119508787363   # where staff approve wishes, and the only place the card can be previewed
# Who the card goes to is set in chat with `$gmgetwell for @player` (kept in the database). These two
# are only the fallback if that was never done.
RECIPIENT_ID = 0
RECIPIENT_NAME = ""
# `$gmgetwell open` with no length stays open until `$gmgetwell close`: this many days is the "until".
OPEN_ENDED_DAYS = 90

# ---- rewards -----------------------------------------------------------------------------------
REWARD_CRATES = {"divine": 3, "fortune": 3}
REWARD_ELIXIRS = 8                        # any kind, any quality, repeats allowed
DEFAULT_QUALITY = 2                       # the quality the picker starts on (elixirs.QUALITIES: 0 plain, 1 silver, 2 gold)
REWARDS = ("crates", "elixirs")             # a player takes exactly one

MIN_LENGTH = base.MIN_LENGTH
MAX_LENGTH = base.MAX_LENGTH

# Persistent button ids. They must never equal the birthday ones ("birthdaywish:approve", ...).
APPROVE_ID = "getwell:approve"
REJECT_ID = "getwell:reject"

TABLE_SQL = """CREATE TABLE IF NOT EXISTS getwell_wishes (
  id SERIAL PRIMARY KEY,
  user_id BIGINT NOT NULL,
  author_name TEXT NOT NULL,
  message TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  review_message_id BIGINT,
  reviewed_by BIGINT,
  reviewed_at TIMESTAMPTZ,
  reason TEXT,
  reward TEXT,
  redeemed_at TIMESTAMPTZ
);
CREATE UNIQUE INDEX IF NOT EXISTS getwell_wishes_one_open
  ON getwell_wishes (user_id) WHERE status IN ('pending', 'approved');
CREATE INDEX IF NOT EXISTS getwell_wishes_review_message ON getwell_wishes (review_message_id);
CREATE TABLE IF NOT EXISTS getwell_event (
  id SMALLINT PRIMARY KEY CHECK (id = 1),
  closes_at TIMESTAMPTZ,
  recipient_id BIGINT,
  recipient_name TEXT,
  delivered_at TIMESTAMPTZ
)"""


def unset_ids() -> list[str]:
    """The names of the IDs above that are still 0 (empty when the event is ready to open)."""
    ids = {"GUILD_ID": GUILD_ID, "REVIEW_CHANNEL_ID": REVIEW_CHANNEL_ID}
    return [name for name, value in ids.items() if not value]


def not_eligible(member: dict | None) -> str | None:
    """Why this server member can't wish ("not_member", "alt"), or None if they can.

    member is Discord's member object for GUILD_ID (as bot.http.get_member returns it), or None
    when they aren't in the server. Same rule as the birthday event, with this module's alt role.
    """
    if member is None:
        return "not_member"
    if ALT_ROLE_ID in {int(role) for role in member.get("roles", [])}:
        return "alt"
    return None

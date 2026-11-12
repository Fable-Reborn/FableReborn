"""Birthday wishes: players write a short message for the birthday card.

`$wish <message>` puts a wish in front of staff in the review channel. Once it's approved, the
player picks one thank-you with `$wish redeem`: crates, or elixirs of their choosing, or the
two wish profile backgrounds (Wishlight and Moonlight Lantern). Every approved wish goes on one card (cogs/wish/card.py) that a GM sends to the
birthday person with `$gmwish send`.

Who can wish: anyone with a character who is in the Fable server and doesn't carry the alt role,
once each, while the event is open (`$gmwish open 24h`). A wish has to be sent in that server,
and the message is deleted at once so the birthday person never sees it.

Discord-free so the cog and tests can share it.
"""
from __future__ import annotations

import re

from utils import elixirs

GUILD_ID = 1402911850802315336            # wishers must be a member of this server
ALT_ROLE_ID = 1470792499789430917         # ... and must not have this role (alt accounts)
REVIEW_CHANNEL_ID = 1570410119508787363   # where staff approve or turn down wishes
RECIPIENT_ID = 598004694060892183         # who the finished card is sent to
RECIPIENT_NAME = "Manic"                  # the name on the card, unless a GM sets another

MIN_LENGTH = 3
MAX_LENGTH = 200
NAME_LENGTH = 32

# The background reward is both of these event themes (cogs/profile/themes.py), given together.
# Anyone who holds one is given the rest when the cog loads, so a background added later reaches
# the players who had already redeemed.
THEME_KEYS = ("wishlight", "moonlantern")
THEME_NAMES = ("Wishlight", "Moonlight Lantern")
REWARD_CRATES = {"divine": 3, "fortune": 3}
REWARD_ELIXIRS = 8                        # elixirs in the elixir reward: any kind, any quality, repeats allowed
DEFAULT_QUALITY = 2                       # the quality the picker starts on (elixirs.QUALITIES: 0 plain, 1 silver, 2 gold)
REWARDS = ("crates", "elixirs", "background")   # a player takes exactly one

PENDING, APPROVED, REJECTED, WITHDRAWN = "pending", "approved", "rejected", "withdrawn"

TABLE_SQL = """CREATE TABLE IF NOT EXISTS birthday_wishes (
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
CREATE UNIQUE INDEX IF NOT EXISTS birthday_wishes_one_open
  ON birthday_wishes (user_id) WHERE status IN ('pending', 'approved');
CREATE INDEX IF NOT EXISTS birthday_wishes_review_message ON birthday_wishes (review_message_id);
CREATE TABLE IF NOT EXISTS birthday_wish_event (
  id SMALLINT PRIMARY KEY CHECK (id = 1),
  closes_at TIMESTAMPTZ,
  recipient_name TEXT,
  delivered_at TIMESTAMPTZ
)"""

_CUSTOM_EMOJI = re.compile(r"<a?:\w+:\d+>")
_MENTION = re.compile(r"<(?:@[!&]?|#)\d+>")
_MARKDOWN = re.compile(r"\*\*|__|~~|\|\||`+")
_LINK = re.compile(r"(?:https?://|www\.|discord\.gg/)\S*", re.IGNORECASE)
# Invisible and direction-changing characters, which only make a card harder to read.
_INVISIBLE = re.compile(r"[​-‏‪-‮⁠-⁤﻿]")


class WishProblem(ValueError):
    """Why a wish can't be taken as written. args[0] is one of the codes below."""

    EMPTY, SHORT, LONG, LINK = "empty", "short", "long", "link"


def clean_message(text: str) -> str:
    """What goes on the card: one line, without Discord markup the picture can't show."""
    text = _INVISIBLE.sub("", str(text or ""))
    text = _CUSTOM_EMOJI.sub("", text)
    text = _MENTION.sub("", text)
    text = _MARKDOWN.sub("", text)
    return " ".join(text.split())


def check_message(text: str) -> str:
    """The cleaned wish, or WishProblem saying what's wrong with it."""
    if _LINK.search(str(text or "")):
        raise WishProblem(WishProblem.LINK)
    cleaned = clean_message(text)
    if not cleaned:
        raise WishProblem(WishProblem.EMPTY)
    if len(cleaned) < MIN_LENGTH:
        raise WishProblem(WishProblem.SHORT)
    if len(cleaned) > MAX_LENGTH:
        raise WishProblem(WishProblem.LONG, len(cleaned) - MAX_LENGTH)
    return cleaned


def not_eligible(member: dict | None) -> str | None:
    """Why this server member can't wish ("not_member", "alt"), or None if they can.

    member is Discord's member object for GUILD_ID (as bot.http.get_member returns it), or None
    when they aren't in the server.
    """
    if member is None:
        return "not_member"
    if ALT_ROLE_ID in {int(role) for role in member.get("roles", [])}:
        return "alt"
    return None


def display_name(member: dict | None, fallback: str = "A friend") -> str:
    """The name signed under the wish: server nickname, else display name, else username."""
    member = member or {}
    user = member.get("user") or {}
    name = member.get("nick") or user.get("global_name") or user.get("username") or fallback
    name = " ".join(_INVISIBLE.sub("", str(name)).split())
    return (name or fallback)[:NAME_LENGTH]


def check_picks(picks) -> list[tuple[str, int]]:
    """The (elixir id, quality) pairs a player chose, in order, or ValueError when there are too
    many of them, one isn't an elixir, or a quality doesn't exist."""
    try:
        picks = [(str(elixir_id), int(quality)) for elixir_id, quality in picks or ()]
    except (TypeError, ValueError):
        raise ValueError("Each pick is an elixir and a quality.") from None
    if len(picks) > REWARD_ELIXIRS:
        raise ValueError(f"At most {REWARD_ELIXIRS} elixirs.")
    for elixir_id, quality in picks:
        if elixir_id not in elixirs.ELIXIRS:
            raise ValueError(f"Not an elixir: {elixir_id}")
        if not 0 <= quality < len(elixirs.QUALITIES):
            raise ValueError(f"Not a quality: {quality}")
    return picks


def elixir_type(elixir_id: str, quality: int) -> str:
    """The consumable type a chosen elixir is given as."""
    return elixirs.type_for(elixir_id, quality)

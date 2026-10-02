"""GM review of in-game Fable bug reports.

The game server creates and fills ``fable_bug_reports`` (see the server's
scripts/bug_reports.sql). Players submit; GMs only change ``status`` and
``reviewer_notes`` here. Accepts an asyncpg pool or connection.
"""
import json

STATUSES = ("new", "reviewing", "resolved", "dismissed")
FILTERS = {
    "open": ("new", "reviewing"),
    "new": ("new",),
    "reviewing": ("reviewing",),
    "resolved": ("resolved",),
    "dismissed": ("dismissed",),
    "all": STATUSES,
}
MAX_NOTES = 1500

# Everything but the screenshot bytes, which load one report at a time.
_COLUMNS = (
    "id, fable_id, game_username, discord_id, description, client_context, created_at, "
    "status, reviewer_notes, reviewed_at, screenshot IS NOT NULL AS has_screenshot"
)


def parse_context(value) -> dict:
    """jsonb arrives as text unless the pool registers a codec."""
    if isinstance(value, dict):
        return value
    try:
        parsed = json.loads(value or "{}")
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _report(row) -> dict:
    report = dict(row)
    report["client_context"] = parse_context(report.get("client_context"))
    return report


async def list_reports(db, *, fable_id=None, statuses=FILTERS["open"], limit=200):
    rows = await db.fetch(
        f"SELECT {_COLUMNS} FROM fable_bug_reports "
        "WHERE ($1::text IS NULL OR fable_id=$1) AND status = ANY($2::text[]) "
        "ORDER BY created_at DESC LIMIT $3",
        fable_id, list(statuses), int(limit),
    )
    return [_report(row) for row in rows]


async def status_counts(db, *, fable_id=None) -> dict:
    rows = await db.fetch(
        "SELECT status, count(*) AS total FROM fable_bug_reports "
        "WHERE ($1::text IS NULL OR fable_id=$1) GROUP BY status",
        fable_id,
    )
    counts = dict.fromkeys(STATUSES, 0)
    counts.update({row["status"]: int(row["total"]) for row in rows})
    return counts


async def load_screenshot(db, report_id):
    return await db.fetchval("SELECT screenshot FROM fable_bug_reports WHERE id=$1", report_id)


async def set_status(db, report_id, status):
    """Return the updated report, or None if it no longer exists."""
    if status not in STATUSES:
        raise ValueError(f"Unknown bug report status: {status}")
    # Reopening clears the review time; any other decision records it.
    row = await db.fetchrow(
        f"UPDATE fable_bug_reports SET status=$2, "
        "reviewed_at = CASE WHEN $2 = 'new' THEN NULL ELSE now() END "
        f"WHERE id=$1 RETURNING {_COLUMNS}",
        report_id, status,
    )
    return _report(row) if row else None


async def set_notes(db, report_id, notes: str):
    row = await db.fetchrow(
        f"UPDATE fable_bug_reports SET reviewer_notes=$2 WHERE id=$1 RETURNING {_COLUMNS}",
        report_id, str(notes or "").strip()[:MAX_NOTES],
    )
    return _report(row) if row else None


class BugReportStore:
    """Binds the helpers to a pool so the review view can be tested with a fake."""

    def __init__(self, db):
        self.db = db

    async def list_reports(self, **filters):
        return await list_reports(self.db, **filters)

    async def status_counts(self, **filters):
        return await status_counts(self.db, **filters)

    async def load_screenshot(self, report_id):
        return await load_screenshot(self.db, report_id)

    async def set_status(self, report_id, status):
        return await set_status(self.db, report_id, status)

    async def set_notes(self, report_id, notes):
        return await set_notes(self.db, report_id, notes)

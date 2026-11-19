"""The outcome of one strike at Thorne's Anvil, written so it can be read at a glance.

A banner names the stat it changed. The forge card prints that stat's line as
the before and after, so each number appears once.
"""
from __future__ import annotations

from classes.equipment.definitions import quality_band

MARKS = {"success": "✅", "pity": "✨", "miss": "❌", "blocked": "⛔"}
STAT = {"temper": "temper", "refine": "quality", "inscribe": "enchant"}
BOUND_NOTE = "🔒 This attempt bound it to you. It can no longer be traded."


def stars(count: int) -> str:
    """Filled stars up to the temper, empty stars out to +7."""
    count = max(0, min(7, int(count)))
    return "★" * count + "☆" * (7 - count)


def banner_text(banner: dict) -> str:
    """A short copy for the confirmation message. The forge card holds the rest."""
    lines = [f"{banner['mark']} **{banner['title']}**"]
    if banner.get("delta"):
        lines.append(banner["delta"])
    if banner.get("note"):
        lines.append(banner["note"])
    return "\n".join(lines)


def plain_banner(tone: str, title: str, note: str, quote: str) -> dict:
    return {"tone": tone, "mark": MARKS[tone], "title": title, "stat": None, "delta": "", "note": note, "quote": quote}


def strike_banner(action: str, status: str, result: dict | None, before: dict, *, quote: str, enchant: str | None = None) -> dict:
    """Build the banner for an attempt that reached the anvil. Refusals use plain_banner instead."""
    result = result or {}
    if status == "poor":
        title = "Not enough gold" if result.get("short") == "gold" else "Short on goods"
        return plain_banner("blocked", title, "Nothing was spent.", quote)

    success = bool(result.get("success"))
    tone = ("pity" if result.get("pity_used") else "success") if success else "miss"
    if action == "temper":
        was, now = int(before["stars"]), int(result.get("refinement") or before["stars"])
        title = "Tempered" if success else "Temper held"
        delta = (
            f"Temper **+{was} → +{now}** {stars(now)}"
            if success
            else f"Temper +{now} {stars(now)} · held"
        )
    elif action == "refine":
        was, now = int(before["quality"]), int(result.get("quality") or before["quality"])
        title = "Refined" if success else "Refine held"
        delta = (
            f"Quality **{was} → {now}** · {quality_band(now)}"
            if success
            else f"Quality {now} · {quality_band(now)} · held"
        )
    else:
        held = ", ".join(before.get("enchants") or []) or "None"
        title = "Inscribed" if success else "Inscription held"
        delta = (
            f"Enchant **{held} → {enchant}**"
            if success
            else f"Enchant {held} · {enchant or 'it'} did not take"
        )
    return {
        "tone": tone,
        "mark": MARKS[tone],
        "title": title,
        "stat": STAT[action],
        "delta": delta,
        "note": BOUND_NOTE if result.get("newly_bound") else "",
        "quote": quote,
    }

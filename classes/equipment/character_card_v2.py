"""Themed character card for the Components V2 gear screen.

It is the same sheet as character_card.py, bound in a different cover. Void,
Royal, Frost, and Dusk change the leather, the metal trim, and the tint of the
page. The covers themselves are defined in chronicle.py.
"""
from __future__ import annotations

from classes.equipment import chronicle
from classes.equipment.character_card import HEIGHT, WIDTH, render_character

__all__ = ["HEIGHT", "THEMES", "WIDTH", "render_themed", "theme_named"]

# What the layout needs from each theme: a button label and the container's accent color.
THEMES = {
    key: {"label": chronicle.THEMES[key].label, "accent": chronicle.THEMES[key].accent}
    for key in ("void", "royal", "frost", "dusk")
}


def theme_named(name: str) -> tuple[str, dict]:
    key = name if name in THEMES else "void"
    return key, THEMES[key]


def render_themed(loadout: dict, weapons: list[dict], *, focus: str, title: str, theme: str) -> bytes:
    key, _colors = theme_named(theme)
    return render_character(loadout, weapons, focus=focus, title=title, theme=key)

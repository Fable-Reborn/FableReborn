from __future__ import annotations

from dataclasses import dataclass


ASCENSION_UNLOCK_LEVEL = 100
ASCENSION_TABLE_NAME = "ascension_mantles"


@dataclass(frozen=True)
class AscensionMantle:
    key: str
    title: str
    god: str
    color: int
    lore: str
    signature_name: str
    signature_summary: str
    passive_lines: tuple[str, ...]


ASCENSION_MANTLES: dict[str, AscensionMantle] = {
    "thronekeeper": AscensionMantle(
        key="thronekeeper",
        title="Thronekeeper",
        god="Elysia",
        color=0xD4B95E,
        lore=(
            "Elysia offered you service beneath her light. You took her authority "
            "instead. The battlefield now answers to your decree."
        ),
        signature_name="Edict of Silence",
        signature_summary=(
            "At battle start, you cast a divine decree that shields your allies "
            "and binds the enemy's first action."
        ),
        passive_lines=(
            "Opens battle with a radiant team barrier.",
            "The enemy's first action is sealed by throne-law.",
        ),
    ),
    "grave_sovereign": AscensionMantle(
        key="grave_sovereign",
        title="Grave Sovereign",
        god="Sepulchure",
        color=0x6A1F2B,
        lore=(
            "Sepulchure offered you godhood through slaughter. You claimed "
            "something colder: dominion over endings themselves."
        ),
        signature_name="Usurp the Fallen",
        signature_summary=(
            "When an enemy weakens, you rip a Grave Echo from its soul, deal a "
            "burst of finishing damage, and force the echo to fight for you."
        ),
        passive_lines=(
            "Consumes weakened enemies with burst true damage.",
            "Raises a Grave Echo to fight at your side once per battle.",
        ),
    ),
    "cyclebreaker": AscensionMantle(
        key="cyclebreaker",
        title="Cyclebreaker",
        god="Drakath",
        color=0x5B50D6,
        lore=(
            "Drakath offered you paradox instead of freedom. You became the one "
            "who remembers the failed timeline and walks out of it alive."
        ),
        signature_name="I Reject This Timeline",
        signature_summary=(
            "At battle start, your element adapts to the enemy. On your first "
            "death, reality tears open, you return, and a Paradox Echo joins the fight."
        ),
        passive_lines=(
            "Adapts your element to counter the enemy at battle start.",
            "Once per battle, fatal damage is rejected and a Paradox Echo appears.",
        ),
    ),
}

ASCENSION_MANTLE_ORDER: tuple[str, ...] = tuple(ASCENSION_MANTLES.keys())


def normalize_ascension_key(value: str | None) -> str | None:
    if not value:
        return None
    normalized = "".join(ch for ch in str(value).lower() if ch.isalnum())
    for key, mantle in ASCENSION_MANTLES.items():
        key_normalized = "".join(ch for ch in key.lower() if ch.isalnum())
        title_normalized = "".join(ch for ch in mantle.title.lower() if ch.isalnum())
        god_normalized = "".join(ch for ch in mantle.god.lower() if ch.isalnum())
        if normalized in {key_normalized, title_normalized, god_normalized}:
            return key
    return None


def get_ascension_mantle(value: str | None) -> AscensionMantle | None:
    normalized = normalize_ascension_key(value)
    if normalized is None:
        return None
    return ASCENSION_MANTLES.get(normalized)

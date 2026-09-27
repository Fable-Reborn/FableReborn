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
        signature_name="Radiant Covenant",
        signature_summary=(
            "Protect your party with renewing wards. When a ward breaks, expires, "
            "or renews, half its absorbed damage empowers the protected ally's next hit."
        ),
        passive_lines=(
            "Opening ward: 15% of each ally's max HP; renews to at least 8% every 3 personal turns.",
            "Wards last 3 recipient turns and do not stack with other Elysia wards.",
            "Radiance stores up to 10% of the recipient's max HP; normal shields do not charge it.",
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
        signature_name="Doom and Reap",
        signature_summary=(
            "Successful attacks build Doom. Below 25% HP, an enemy with at least "
            "3 stacks suffers Reap, consuming the stacks for a finishing burst."
        ),
        passive_lines=(
            "One stack per successful turn, maximum 5; expires after 3 target turns without refresh.",
            "Each stack ticks for 6% of your attack, capped at 1.5% of the target's max HP, at their turn start.",
            "Reap deals 4 ticks at once, capped at 10% target max HP; shields still protect against Doom and Reap.",
            "Killing a marked enemy carries half its stacks to your next target. No clone or instant boss kill.",
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
            "Open with a targetable Paradox Echo that mirrors your attacks. "
            "Reject one fatal hit by sacrificing your surviving echo."
        ),
        passive_lines=(
            "Chaos Surge adds 30% damage on turns 1, 3, 5...; intervening turns are recovery turns.",
            "Echo: 25% of your max HP, 50% armor; mirrors 20% of one resolved hit per turn without its own action.",
            "Once per battle, a living echo is sacrificed to revive you at 30% HP. Destroying it prevents the revive.",
            "Your chosen attack and defense elements stay unchanged.",
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

from __future__ import annotations

from dataclasses import dataclass, fields, replace


@dataclass(frozen=True)
class RaidSettings:
    boss_name: str = "The Hollow Sovereign"
    boss_hp: int = 150_000
    boss_attack: int = 900
    boss_defense: int = 250
    traitor_heal_pct: float = 50.0
    traitor_death_damage_pct: float = 15.0
    innocent_death_enrage_pct: float = 5.0
    wrong_exile_enrage_pct: float = 10.0
    max_rounds: int = 12
    vote_every: int = 3
    min_players: int = 6
    max_players: int = 16
    boss_targets: int = 2
    join_seconds: int = 120
    action_seconds: int = 30
    vote_seconds: int = 25
    investigate_accuracy_pct: float = 78.0
    clue_suspects: int = 3
    guard_reduction_pct: float = 60.0
    guard_damage_pct: float = 45.0
    investigate_damage_pct: float = 60.0
    rally_damage_pct: float = 35.0
    rally_heal_pct: float = 8.0


SETTING_RULES = {
    "boss_hp": (10_000, 50_000_000, True),
    "boss_attack": (1, 5_000_000, True),
    "boss_defense": (0, 5_000_000, True),
    "traitor_heal_pct": (0, 300, False),
    "traitor_death_damage_pct": (0, 100, False),
    "innocent_death_enrage_pct": (0, 100, False),
    "wrong_exile_enrage_pct": (0, 100, False),
    "max_rounds": (3, 30, True),
    "vote_every": (1, 10, True),
    "min_players": (2, 16, True),
    "max_players": (3, 16, True),
    "boss_targets": (1, 5, True),
    "join_seconds": (15, 900, True),
    "action_seconds": (10, 120, True),
    "vote_seconds": (10, 120, True),
    "investigate_accuracy_pct": (50, 100, False),
    "clue_suspects": (2, 5, True),
    "guard_reduction_pct": (0, 90, False),
    "guard_damage_pct": (0, 100, False),
    "investigate_damage_pct": (0, 100, False),
    "rally_damage_pct": (0, 100, False),
    "rally_heal_pct": (0, 50, False),
}

SETTING_ALIASES = {
    "hp": "boss_hp",
    "attack": "boss_attack",
    "atk": "boss_attack",
    "defense": "boss_defense",
    "defence": "boss_defense",
    "def": "boss_defense",
    "traitor_contribution": "traitor_heal_pct",
    "traitor_heal": "traitor_heal_pct",
    "traitor_death": "traitor_death_damage_pct",
    "innocent_death": "innocent_death_enrage_pct",
    "wrong_exile": "wrong_exile_enrage_pct",
    "rounds": "max_rounds",
    "vote": "vote_every",
    "targets": "boss_targets",
    "join_time": "join_seconds",
    "action_time": "action_seconds",
    "vote_time": "vote_seconds",
    "investigation_accuracy": "investigate_accuracy_pct",
}


PRESETS = {
    "balanced": RaidSettings(),
    "quick": RaidSettings(
        boss_hp=90_000,
        boss_attack=825,
        max_rounds=8,
        vote_every=2,
        join_seconds=60,
        action_seconds=20,
        vote_seconds=20,
    ),
    "brutal": RaidSettings(
        boss_hp=250_000,
        boss_attack=1_250,
        boss_defense=375,
        traitor_heal_pct=75,
        innocent_death_enrage_pct=8,
        wrong_exile_enrage_pct=15,
        max_rounds=14,
    ),
    "chaos": RaidSettings(
        boss_hp=180_000,
        boss_attack=1_050,
        traitor_heal_pct=100,
        traitor_death_damage_pct=25,
        innocent_death_enrage_pct=10,
        wrong_exile_enrage_pct=20,
        investigate_accuracy_pct=65,
        max_rounds=10,
        vote_every=2,
    ),
}


def normalize_setting_key(key: str) -> str:
    normalized = str(key).strip().lower().replace("-", "_")
    return SETTING_ALIASES.get(normalized, normalized)


def validate_settings(settings: RaidSettings) -> None:
    if settings.min_players > settings.max_players:
        raise ValueError("min_players cannot be greater than max_players.")
    if settings.boss_targets > settings.max_players:
        raise ValueError("boss_targets cannot be greater than max_players.")
    if settings.vote_every > settings.max_rounds:
        raise ValueError("vote_every cannot be greater than max_rounds.")
    if settings.clue_suspects > settings.max_players:
        raise ValueError("clue_suspects cannot be greater than max_players.")
    if not settings.boss_name.strip():
        raise ValueError("boss_name cannot be empty.")


def update_setting(settings: RaidSettings, key: str, raw_value: str) -> RaidSettings:
    key = normalize_setting_key(key)
    if key not in SETTING_RULES:
        valid = ", ".join(SETTING_RULES)
        raise ValueError(f"Unknown setting `{key}`. Valid settings: {valid}")

    minimum, maximum, integer = SETTING_RULES[key]
    try:
        number = float(str(raw_value).replace(",", "").strip())
    except ValueError as exc:
        raise ValueError(f"{key} must be a number.") from exc
    if integer and not number.is_integer():
        raise ValueError(f"{key} must be a whole number.")
    if not minimum <= number <= maximum:
        raise ValueError(f"{key} must be between {minimum:g} and {maximum:g}.")

    value = int(number) if integer else float(number)
    updated = replace(settings, **{key: value})
    validate_settings(updated)
    return updated


def update_boss_name(settings: RaidSettings, name: str) -> RaidSettings:
    name = " ".join(str(name).split()).strip()
    if not 2 <= len(name) <= 60:
        raise ValueError("The boss name must be between 2 and 60 characters.")
    updated = replace(settings, boss_name=name)
    validate_settings(updated)
    return updated


def settings_dict(settings: RaidSettings) -> dict[str, object]:
    return {item.name: getattr(settings, item.name) for item in fields(settings)}

SPEED_SECONDS: dict[str, int] = {
    "Normal": 60,
    "Extended": 90,
    "Fast": 45,
    "Blitz": 30,
}

_SPEED_ALIASES: dict[str, str] = {
    "normal": "Normal",
    "extended": "Extended",
    "fast": "Fast",
    "blitz": "Blitz",
}


def resolve_speed_label(speed: str | None) -> str | None:
    if speed is None:
        return "Normal"
    return _SPEED_ALIASES.get(str(speed).strip().lower())

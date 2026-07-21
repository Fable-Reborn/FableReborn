from __future__ import annotations


def hp_bar(current: float, maximum: float, width: int = 18) -> str:
    if maximum <= 0:
        ratio = 0.0
    else:
        ratio = max(0.0, min(1.0, float(current) / float(maximum)))
    filled = int(round(ratio * width))
    if maximum > 0 and current > 0 and filled == 0:
        filled = 1
    return "█" * filled + "░" * (width - filled)


def hp_color(current: float, maximum: float) -> int:
    ratio = 0 if maximum <= 0 else max(0.0, float(current) / float(maximum))
    if ratio > 0.60:
        return 0x2ECC71
    if ratio > 0.30:
        return 0xF1C40F
    return 0xE74C3C


def compact_number(value: float) -> str:
    value = float(value)
    if abs(value) >= 1_000_000:
        number = f"{value / 1_000_000:.2f}".rstrip("0").rstrip(".")
        return f"{number}M"
    if abs(value) >= 1_000:
        number = f"{value / 1_000:.1f}".rstrip("0").rstrip(".")
        return f"{number}K"
    return f"{value:,.0f}"

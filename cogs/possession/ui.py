"""Visual building blocks for Possession embeds: bars and numbers.

HP bars reuse the battle cog's emoji tiles so the event matches the rest of
the bot. If the battle cog cannot be imported, bars fall back to text.
"""

_TILES = None
_TILE_NAMES = {
    "red": ("HP_BAR_FULL_{}", "HP_BAR_HALF_{}"),
    "blue": ("HP_BAR_BLUE_FULL_{}", "HP_BAR_BLUE_HALF_{}"),
    "yellow": ("HP_BAR_YELLOW_FULL_{}", "HP_BAR_YELLOW_HALF_{}"),
}
_EDGES = ("LEFT", "MIDDLE", "RIGHT")


def _tiles():
    global _TILES
    if _TILES is None:
        try:
            from cogs.battles.core.battle import Battle
        except Exception:
            _TILES = {}
        else:
            _TILES = {"empty": tuple(getattr(Battle, f"HP_BAR_EMPTY_{edge}") for edge in _EDGES)}
            for colour, (full, half) in _TILE_NAMES.items():
                _TILES[colour] = (
                    tuple(getattr(Battle, full.format(edge)) for edge in _EDGES),
                    tuple(getattr(Battle, half.format(edge)) for edge in _EDGES),
                )
    return _TILES


def ratio(current, total):
    return max(0.0, min(1.0, float(current) / float(total))) if total else 0.0


def text_bar(current, total, length=10):
    filled = round(length * ratio(current, total))
    return "▰" * filled + "▱" * (length - filled)


def bar(current, total, length=10, colour="red"):
    """An emoji HP bar in half-tile steps, or a text bar if tiles are unavailable."""
    tiles = _tiles()
    if not tiles:
        return text_bar(current, total, length)
    length = max(3, length)
    full, half = tiles[colour]
    empty = tiles["empty"]
    halves = round(ratio(current, total) * length * 2)
    out = []
    for index in range(length):
        edge = 0 if index == 0 else 2 if index == length - 1 else 1
        units = max(0, min(2, halves - index * 2))
        out.append((empty, half, full)[units][edge])
    return "".join(out)


def compact(number):
    number = float(number)
    for limit, suffix in ((1e9, "B"), (1e6, "M"), (1e3, "k")):
        if abs(number) >= limit:
            text = f"{number / limit:.2f}".rstrip("0").rstrip(".")
            return f"{text}{suffix}"
    return f"{number:,.0f}"


def percent(current, total):
    return round(100 * ratio(current, total))


def roman(number):
    return {1: "I", 2: "II", 3: "III"}.get(number, str(number))

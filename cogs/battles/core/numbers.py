from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


def to_decimal(value=0, default=0) -> Decimal:
    """Safely convert ints, floats, strings, Decimals, or None into Decimal."""
    if isinstance(value, Decimal):
        return value

    if value is None:
        value = default

    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return Decimal(str(default))


def decimal_int(value, default=0) -> int:
    """Convert a value to a rounded int using Decimal-safe logic."""
    return int(to_decimal(value, default).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def scaled_int(value, scale=1, minimum=0) -> int:
    """Safely multiply value * scale, then round to int with a minimum."""
    result = to_decimal(value) * to_decimal(scale, 1)
    return max(int(minimum), decimal_int(result))
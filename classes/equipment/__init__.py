"""Equipment rules shared by commands, combat, and tests."""

from classes.equipment.definitions import (
    ALL_SLOTS,
    DEV_DATABASE,
    FUTURE_SLOTS,
    OPEN_SLOTS,
    PAPER_DOLL_SLOTS,
)
from classes.equipment.stats import apply_component_bonus, contribution, quality_scale

__all__ = [
    "ALL_SLOTS",
    "DEV_DATABASE",
    "FUTURE_SLOTS",
    "OPEN_SLOTS",
    "PAPER_DOLL_SLOTS",
    "apply_component_bonus",
    "contribution",
    "quality_scale",
]

"""
The IdleRPG Discord Bot
Copyright (C) 2018-2021 Diniboy and Gelbpunkt
Copyright (C) 2024 Lunar (discord itslunar.)

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU Affero General Public License for more details.

You should have received a copy of the GNU Affero General Public License
along with this program.  If not, see <https://www.gnu.org/licenses/>.
"""

from __future__ import annotations

ALL_EFFECTS = (
    "weakened",
    "blind",
    "dazed",
    "bleeding",
    "poisoned",
    "marked",
    "shattered_armor",
)


class Effects:
    __slots__ = ALL_EFFECTS

    def __init__(
        self,
        weakened: int = 0,
        blind: int = 0,
        dazed: int = 0,
        bleeding: int = 0,
        poisoned: int = 0,
        marked: int = 0,
        shattered_armor: int = 0,
    ) -> None:
        # Deals 30% less damage
        self.weakened = weakened
        # Has a 50% chance to fail spells
        self.blind = blind
        # Cannot cast spells
        self.dazed = dazed
        # Takes 15 damage per tick
        self.bleeding = bleeding
        # Takes 30 damage per tick
        self.poisoned = poisoned
        # Healing is 80% less efficient on this target
        self.marked = marked
        # Armor is 50% less effective
        self.shattered_armor = shattered_armor

    def all(self):
        return [effect for effect in ALL_EFFECTS if getattr(self, effect) > 0]

    def merge_with(self, other: Effects) -> None:
        for effect in ALL_EFFECTS:
            setattr(self, effect, getattr(other, effect) + getattr(self, effect))

    def substract(self, other: Effects) -> None:
        for effect in ALL_EFFECTS:
            setattr(
                self,
                effect,
                val
                if (val := getattr(self, effect) - getattr(other, effect)) >= 0
                else 0,
            )

    def tick(self) -> None:
        for effect in ALL_EFFECTS:
            setattr(self, effect, val if (val := getattr(self, effect) - 1) >= 0 else 0)

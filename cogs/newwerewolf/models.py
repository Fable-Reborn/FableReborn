from __future__ import annotations

from dataclasses import dataclass, field

import discord

from .roles import RoleId


@dataclass(slots=True)
class NewWerewolfOptions:
    mode: str = "Classic"
    speed: str = "Normal"
    timer_seconds: int = 60
    min_players: int = 5
    requested_roles: list[RoleId] = field(default_factory=list)


@dataclass(slots=True)
class PlayerState:
    user: discord.abc.User
    role: RoleId
    initial_roles: list[RoleId] = field(default_factory=list)
    alive: bool = True
    enchanted: bool = False
    infected: bool = False

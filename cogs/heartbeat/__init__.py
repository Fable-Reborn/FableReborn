"""
The IdleRPG Discord Bot
Copyright (C) 2018-2021 Diniboy and Gelbpunkt

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

import logging
import os
import socket
import time

from discord.ext import commands, tasks


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return float(value)
    except ValueError:
        return default


class Heartbeat(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.logger = logging.getLogger(__name__)
        self._socket: socket.socket | None = None

        self.enabled = _env_bool("HEARTBEAT_ENABLED", True)
        self.host = os.getenv("HEARTBEAT_HOST", "127.0.0.1")
        self.port = _env_int("HEARTBEAT_PORT", 5555)
        self.name = os.getenv("HEARTBEAT_NAME", "Fable")
        self.interval = _env_float("HEARTBEAT_INTERVAL_SECONDS", 60.0)
        self.only_shard_zero = _env_bool("HEARTBEAT_ONLY_SHARD_0", True)

        if self.enabled and self._should_run():
            self.heartbeat_loop.change_interval(seconds=self.interval)
            self.heartbeat_loop.start()

    def cog_unload(self) -> None:
        if self.heartbeat_loop.is_running():
            self.heartbeat_loop.cancel()
        if self._socket is not None:
            self._socket.close()
            self._socket = None

    def _should_run(self) -> bool:
        if not self.only_shard_zero:
            return True
        return 0 in getattr(self.bot, "shard_ids", [])

    def _get_socket(self) -> socket.socket:
        if self._socket is None:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setblocking(False)
            self._socket = sock
        return self._socket

    @tasks.loop(seconds=60.0)
    async def heartbeat_loop(self) -> None:
        payload = f"{self.name}|{self.bot.cluster_id}|{self.bot.cluster_name}|{int(time.time())}"
        try:
            self._get_socket().sendto(payload.encode("utf-8"), (self.host, self.port))
        except OSError as exc:
            self.logger.debug("Heartbeat send failed: %s", exc)

    @heartbeat_loop.before_loop
    async def before_heartbeat_loop(self) -> None:
        await self.bot.wait_until_ready()


async def setup(bot):
    await bot.add_cog(Heartbeat(bot))

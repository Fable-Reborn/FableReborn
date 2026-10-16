"""
Cluster-wide single active instance guard.

Enabled only when the FABLE_SINGLETON_LOCK environment variable is "1" (set on
the k3s deployment). The launcher holds a PostgreSQL advisory lock on the
primary database for its whole lifetime. A second launcher waits for the lock
instead of logging in to Discord, so two copies of the bot can never run at the
same time.

The lock connection is checked every few seconds. If it fails, or the database
it is connected to stops being the primary, the launcher stops its clusters and
exits. The server side drops a silent session after IDLE_SESSION_TIMEOUT, which
releases the lock if the holder's node disappears from the network.
"""

from __future__ import annotations

import asyncio
import os
from typing import Any, Callable

import asyncpg

LOCK_KEY = 0x4641424C45  # "FABLE"
CHECK_INTERVAL = 5
QUERY_TIMEOUT = 5
IDLE_SESSION_TIMEOUT_MS = 30_000


def enabled() -> bool:
    return os.environ.get("FABLE_SINGLETON_LOCK") == "1"


async def _connect(db: Any) -> asyncpg.Connection:
    return await asyncpg.connect(
        host=db.postgres_host,
        port=db.postgres_port,
        user=db.postgres_user,
        password=db.postgres_password,
        database=db.postgres_name,
        timeout=QUERY_TIMEOUT,
        server_settings={
            "application_name": "fable-singleton-lock",
            "idle_session_timeout": str(IDLE_SESSION_TIMEOUT_MS),
            "tcp_keepalives_idle": "10",
            "tcp_keepalives_interval": "5",
            "tcp_keepalives_count": "3",
        },
    )


async def acquire(db: Any) -> asyncpg.Connection:
    while True:
        conn = None
        try:
            conn = await _connect(db)
            in_recovery = await conn.fetchval(
                "SELECT pg_is_in_recovery()", timeout=QUERY_TIMEOUT
            )
            if not in_recovery and await conn.fetchval(
                "SELECT pg_try_advisory_lock($1)", LOCK_KEY, timeout=QUERY_TIMEOUT
            ):
                print("[LOCK] Acquired. This is the active Fable instance.", flush=True)
                return conn
            print(
                "[LOCK] Another Fable instance holds the lock. Waiting.", flush=True
            )
        except Exception as e:
            print(
                f"[LOCK] Database not reachable ({type(e).__name__}: {e}). Retrying.",
                flush=True,
            )
        if conn is not None:
            conn.terminate()
        await asyncio.sleep(CHECK_INTERVAL)


async def hold(conn: asyncpg.Connection, on_lost: Callable[[], None]) -> None:
    while True:
        await asyncio.sleep(CHECK_INTERVAL)
        try:
            in_recovery = await conn.fetchval(
                "SELECT pg_is_in_recovery()", timeout=QUERY_TIMEOUT
            )
            if in_recovery:
                raise RuntimeError("database is no longer the primary")
        except Exception as e:
            print(
                f"[LOCK] Lost the lock ({type(e).__name__}: {e}). Shutting down.",
                flush=True,
            )
            on_lost()
            os._exit(1)

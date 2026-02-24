# NewWerewolf (Legacy-Parity Runtime)

## Overview
- `nww` uses a local port of the legacy multiplayer Werewolf runtime.
- Canonical gameplay logic for this cog lives in `cogs/newwerewolf/core.py`.
- This avoids runtime dependency on `utils/werewolf.py` while preserving 1:1 behavior.

## Module Layout
- `__init__.py`: `nww` command surface and lobby/start flow.
- `core.py`: ported legacy multiplayer engine (`Game`, `Player`, role logic, day/night loop).
- `engine.py`: compatibility shim exporting `NewWerewolfGame` as an alias to `core.Game`.
- `lobby.py`, `models.py`, `roles.py`, `role_pool.py`, `settings.py`: retained for compatibility/history.

## Scope
- Multiplayer parity only.
- Single-player is intentionally not wired through `nww`.

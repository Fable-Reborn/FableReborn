# Miscellaneous cog changelog

## 2025-03-21 — `$stats` / `stats` command refactor

**Backup:** Full pre-change `__init__.py` is saved as `__init__.py.pre_stats_refactor.bak` (snapshot of the last committed version before this refactor).

### Goals

- Make **`stats`** reliable when the **Sharding** cog or Redis cross-cluster **`handler`** is unavailable or slow.
- Avoid blocking the async event loop during **`psutil.cpu_percent`** sampling.
- Reduce **host fingerprinting** in the public embed (no `/proc/cpuinfo` model string, kernel, compiler, or distro details; shorter Postgres/Redis version display; footer without owner names).

### Behaviour changes

| Area | Before | After |
|------|--------|--------|
| Guild total | `self.bot.cogs["Sharding"]` only | `get("Sharding")` + `handler` with timeout; fallback to `len(self.bot.guilds)` |
| CPU / RAM / uptime | In-loop `psutil`, 1s CPU sample | `asyncio.to_thread` + short CPU sample; UTC-safe uptime math |
| discord.py version | `pkg_resources.get_distribution` | `importlib.metadata` with `discord.__version__` fallback |
| Postgres version string | `major.micro` + releaselevel | `major.minor` (sanitized) |
| Embed “System Resources” | CPU model name + usage | Logical CPU count + usage (no model string) |
| Embed “Hosting” | Python, dpy, compiler, OS+distro, kernel, PG, Redis | Python, dpy, `platform.system()` only, PG, Redis (trimmed) |
| Footer | `Fable {version} \| By {owners}` | `Fable {version}` |

### Imports

- Removed from this cog (only used by old `stats`): `distro`, `pkg_resources`, `sys`, `nice_join` import tied to stats footer.

Restore the old behaviour by replacing `__init__.py` with `__init__.py.pre_stats_refactor.bak` and re-adding any removed top-level imports if something else in the file still needed them (the backup file is self-contained).

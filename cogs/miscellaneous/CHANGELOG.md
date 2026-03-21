# Miscellaneous cog changelog

All **dates and times are UTC** unless stated otherwise. Use `YYYY-MM-DD` and `HH:MM` (24-hour), or the combined ISO form where noted.

---

## `$stats` user-visible diagnostics & embed hardening

| | |
|---|---|
| **Date** | 2025-03-21 |
| **Time (UTC)** | 23:45 |
| **ISO** | `2025-03-21T23:45:00Z` |

- Adds an embed field **“Why some data may be missing”** when any subsection uses fallbacks (database error, `psutil` failure, cross-cluster guild count unavailable, invalid `base_url`).
- Omits embed `url` unless `BASE_URL` is a valid `http://` or `https://` string (avoids Discord rejecting the whole message).
- On embed send failure, sends a **plain-text** fallback explaining Discord may have rejected the embed, plus any collected notes.
- On unexpected errors before/during build, sends a **short channel message** and logs the full traceback server-side.

---

## `$stats` / `stats` command refactor

| | |
|---|---|
| **Date** | 2025-03-21 |
| **Time (UTC)** | 16:00 |
| **ISO** | `2025-03-21T16:00:00Z` |

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

---

## Deployment & troubleshooting (`$stats` / cog reload)

| | |
|---|---|
| **Date** | 2025-03-21 |
| **Time (UTC)** | 22:30 |
| **ISO** | `2025-03-21T22:30:00Z` |

- **`$unload` / `$load` or `$reload` on `miscellaneous`** is enough to pick up **`stats` code changes** as long as the extension reloads without errors and the process is using the **same on-disk files** you edited.
- A **full bot restart** is not required for cog-only edits, but it is **reasonable** if you run **multiple clusters or processes**: each instance must load the updated cog (or restart so they all do).
- If **`$stats` still produces no message**, check the console: the global error handler often **does not reply** for some `CommandInvokeError` cases (it may only log). The **pre-refactor** `stats` could also fail on fragile lines (e.g. `re.search(..., sys.version)[1]` when the pattern did not match, or hard `self.bot.cogs["Sharding"]`), which looked like “nothing happened.”
- **`CommandNotFound`** is handled with **no user-visible message** anywhere in the bot; if the cog failed to load, the command may not exist and Discord will stay silent.

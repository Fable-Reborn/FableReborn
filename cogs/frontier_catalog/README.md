# Frontier Catalog

This infrastructure cog gives Soulforge Frontiers stable database identities
without replacing the game's legacy name-based pet and splice systems.

## Public API

```python
from cogs.frontier_catalog import get_frontier_catalog

catalog = get_frontier_catalog(bot)
if catalog is None:
    return

await catalog.ensure_ready()
species = await catalog.resolve_species("Sneevil", prefer_origin="wild")
variants = await catalog.get_recipe_variants("Sneevil", "Slime")

inserted = await catalog.record_discovery(
    user_id,
    "sighted",
    species_id=species["species_id"],
    source="frontier_battle",
    dedupe_key=f"battle:{battle_id}:sighted",
)

summary = await catalog.get_player_summary(user_id)
archive_rows = await catalog.list_player_species(user_id, origin="splice")
```

Discovery event types are `sighted`, `defeated`, `egg_obtained`,
`ownership_gained`, `ownership_lost`, `created`, and `mastered`. Supplying a
per-player `dedupe_key` makes a retried battle or reward callback safe.

## Storage rules

- `frontier_species` owns stable identity and structured catalog/PvE metadata.
- `frontier_recipes` stores one row per legacy splice row. Parent order is
  canonicalised, while conflicting outcomes remain separate variants.
- `frontier_discovery_ledger` is append-only; `frontier_discoveries` is its
  efficient per-player projection.
- Nullable Frontier IDs are backfilled onto `monster_pets`, `monster_eggs`, and
  `splice_combinations`. Legacy names and rows are never rewritten or deleted.
- Schema creation and synchronisation run in one transaction under a PostgreSQL
  advisory lock, so startup, reloads, and multiple bot processes are idempotent.

Newly created legacy rows are synchronised immediately by the
`frontier_splice_created` listener through `refresh_legacy()`. A later catalog
cog load remains an idempotent safety net and backfills anything created while
the player-facing Frontiers cog was unavailable. Encounter code should retain
stable species/recipe IDs and record discoveries through this API instead of
matching display names itself.

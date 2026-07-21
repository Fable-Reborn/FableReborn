"""PostgreSQL storage and compatibility import for the Frontier catalog."""

from __future__ import annotations

import asyncio
import json

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Optional

from .legacy import (
    CatalogSeed,
    build_catalog_seed,
    classify_stability,
    clean_name,
    load_monsters_json,
    make_pair_key,
    make_species_key,
    normalize_name,
)


CATALOG_SCHEMA_VERSION = "frontier-catalog-v1"
DISCOVERY_EVENT_TYPES = frozenset(
    {
        "sighted",
        "defeated",
        "egg_obtained",
        "ownership_gained",
        "ownership_lost",
        "created",
        "mastered",
    }
)


SCHEMA_STATEMENTS = (
    """
    CREATE TABLE IF NOT EXISTS frontier_catalog_migrations (
        migration_key TEXT PRIMARY KEY,
        applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        details JSONB NOT NULL DEFAULT '{}'::JSONB
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS frontier_species (
        species_id BIGSERIAL PRIMARY KEY,
        stable_key TEXT NOT NULL UNIQUE,
        canonical_name TEXT NOT NULL,
        normalized_name TEXT NOT NULL,
        origin TEXT NOT NULL CHECK (
            origin IN ('wild', 'splice', 'legacy_reference')
        ),
        generation SMALLINT CHECK (generation IS NULL OR generation >= 0),
        stability TEXT NOT NULL DEFAULT 'stable' CHECK (
            stability IN (
                'stable', 'special', 'unstable', 'destabilised', 'final', 'unknown'
            )
        ),
        publication_status TEXT NOT NULL DEFAULT 'draft' CHECK (
            publication_status IN ('hidden', 'draft', 'approved', 'retired')
        ),
        element TEXT,
        base_hp INTEGER CHECK (base_hp IS NULL OR base_hp >= 0),
        base_attack INTEGER CHECK (base_attack IS NULL OR base_attack >= 0),
        base_defense INTEGER CHECK (base_defense IS NULL OR base_defense >= 0),
        image_url TEXT,
        legacy_tier INTEGER,
        pve_enabled BOOLEAN NOT NULL DEFAULT FALSE,
        pve_region TEXT,
        pve_tier SMALLINT CHECK (pve_tier IS NULL OR pve_tier >= 1),
        pve_role TEXT CHECK (pve_role IS NULL OR pve_role IN ('regular', 'elite', 'boss')),
        metadata JSONB NOT NULL DEFAULT '{}'::JSONB,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        UNIQUE (origin, normalized_name)
    );
    """,
    """
    CREATE INDEX IF NOT EXISTS frontier_species_name_idx
    ON frontier_species(normalized_name, origin);
    """,
    """
    CREATE INDEX IF NOT EXISTS frontier_species_pve_idx
    ON frontier_species(pve_region, pve_tier, pve_role)
    WHERE pve_enabled = TRUE AND publication_status = 'approved';
    """,
    """
    CREATE TABLE IF NOT EXISTS frontier_species_sources (
        source_id BIGSERIAL PRIMARY KEY,
        source_key TEXT NOT NULL UNIQUE,
        species_id BIGINT NOT NULL REFERENCES frontier_species(species_id),
        source_type TEXT NOT NULL CHECK (
            source_type IN ('monster_json', 'splice_result', 'manual')
        ),
        legacy_row_id INTEGER,
        legacy_name TEXT NOT NULL,
        snapshot JSONB NOT NULL DEFAULT '{}'::JSONB,
        first_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        last_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    """,
    """
    CREATE INDEX IF NOT EXISTS frontier_species_sources_species_idx
    ON frontier_species_sources(species_id, source_type);
    """,
    """
    CREATE TABLE IF NOT EXISTS frontier_recipes (
        recipe_id BIGSERIAL PRIMARY KEY,
        stable_key TEXT NOT NULL UNIQUE,
        legacy_splice_id INTEGER UNIQUE,
        parent_low_species_id BIGINT NOT NULL REFERENCES frontier_species(species_id),
        parent_high_species_id BIGINT NOT NULL REFERENCES frontier_species(species_id),
        result_species_id BIGINT NOT NULL REFERENCES frontier_species(species_id),
        canonical_parent_key TEXT NOT NULL,
        variant_rank INTEGER NOT NULL DEFAULT 1 CHECK (variant_rank >= 1),
        is_primary BOOLEAN NOT NULL DEFAULT FALSE,
        generation SMALLINT CHECK (generation IS NULL OR generation >= 0),
        stability TEXT NOT NULL DEFAULT 'stable' CHECK (
            stability IN (
                'stable', 'special', 'unstable', 'destabilised', 'final', 'unknown'
            )
        ),
        publication_status TEXT NOT NULL DEFAULT 'draft' CHECK (
            publication_status IN ('hidden', 'draft', 'approved', 'retired')
        ),
        legacy_parent_a_name TEXT,
        legacy_parent_b_name TEXT,
        legacy_result_name TEXT,
        legacy_hp INTEGER,
        legacy_attack INTEGER,
        legacy_defense INTEGER,
        legacy_element TEXT,
        legacy_image_url TEXT,
        legacy_created_at TIMESTAMP,
        imported_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        CHECK (parent_low_species_id <= parent_high_species_id)
    );
    """,
    """
    CREATE INDEX IF NOT EXISTS frontier_recipes_parent_pair_idx
    ON frontier_recipes(canonical_parent_key, is_primary DESC, variant_rank, recipe_id);
    """,
    """
    CREATE UNIQUE INDEX IF NOT EXISTS frontier_recipes_one_primary_pair_idx
    ON frontier_recipes(canonical_parent_key)
    WHERE is_primary = TRUE;
    """,
    """
    CREATE TABLE IF NOT EXISTS frontier_discovery_ledger (
        event_id BIGSERIAL PRIMARY KEY,
        user_id BIGINT NOT NULL,
        species_id BIGINT NOT NULL REFERENCES frontier_species(species_id),
        event_type TEXT NOT NULL CHECK (
            event_type IN (
                'sighted', 'defeated', 'egg_obtained', 'ownership_gained',
                'ownership_lost', 'created', 'mastered'
            )
        ),
        source TEXT NOT NULL DEFAULT 'frontier',
        recipe_id BIGINT REFERENCES frontier_recipes(recipe_id),
        quantity INTEGER NOT NULL DEFAULT 1 CHECK (quantity >= 1),
        dedupe_key TEXT,
        metadata JSONB NOT NULL DEFAULT '{}'::JSONB,
        occurred_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    """,
    """
    CREATE UNIQUE INDEX IF NOT EXISTS frontier_discovery_ledger_dedupe_idx
    ON frontier_discovery_ledger(user_id, dedupe_key)
    WHERE dedupe_key IS NOT NULL;
    """,
    """
    CREATE INDEX IF NOT EXISTS frontier_discovery_ledger_user_idx
    ON frontier_discovery_ledger(user_id, occurred_at DESC, event_id DESC);
    """,
    """
    CREATE INDEX IF NOT EXISTS frontier_discovery_ledger_species_idx
    ON frontier_discovery_ledger(species_id, event_type, occurred_at DESC);
    """,
    """
    CREATE TABLE IF NOT EXISTS frontier_discoveries (
        user_id BIGINT NOT NULL,
        species_id BIGINT NOT NULL REFERENCES frontier_species(species_id),
        first_sighted_at TIMESTAMPTZ,
        last_sighted_at TIMESTAMPTZ,
        first_defeated_at TIMESTAMPTZ,
        last_defeated_at TIMESTAMPTZ,
        first_egg_at TIMESTAMPTZ,
        first_owned_at TIMESTAMPTZ,
        last_ownership_change_at TIMESTAMPTZ,
        first_created_at TIMESTAMPTZ,
        mastered_at TIMESTAMPTZ,
        sightings INTEGER NOT NULL DEFAULT 0 CHECK (sightings >= 0),
        defeats INTEGER NOT NULL DEFAULT 0 CHECK (defeats >= 0),
        eggs_obtained INTEGER NOT NULL DEFAULT 0 CHECK (eggs_obtained >= 0),
        creations INTEGER NOT NULL DEFAULT 0 CHECK (creations >= 0),
        current_owned_count INTEGER NOT NULL DEFAULT 0 CHECK (current_owned_count >= 0),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        PRIMARY KEY (user_id, species_id)
    );
    """,
    """
    CREATE INDEX IF NOT EXISTS frontier_discoveries_user_updated_idx
    ON frontier_discoveries(user_id, updated_at DESC, species_id);
    """,
)


LEGACY_LINK_COLUMNS = {
    "monster_pets": (
        """
        ALTER TABLE monster_pets
        ADD COLUMN IF NOT EXISTS frontier_species_id BIGINT
        REFERENCES frontier_species(species_id) ON DELETE SET NULL;
        """,
    ),
    "monster_eggs": (
        """
        ALTER TABLE monster_eggs
        ADD COLUMN IF NOT EXISTS frontier_species_id BIGINT
        REFERENCES frontier_species(species_id) ON DELETE SET NULL;
        """,
    ),
    "splice_combinations": (
        """
        ALTER TABLE splice_combinations
        ADD COLUMN IF NOT EXISTS frontier_recipe_id BIGINT
        REFERENCES frontier_recipes(recipe_id) ON DELETE SET NULL;
        """,
        """
        ALTER TABLE splice_combinations
        ADD COLUMN IF NOT EXISTS frontier_parent1_species_id BIGINT
        REFERENCES frontier_species(species_id) ON DELETE SET NULL;
        """,
        """
        ALTER TABLE splice_combinations
        ADD COLUMN IF NOT EXISTS frontier_parent2_species_id BIGINT
        REFERENCES frontier_species(species_id) ON DELETE SET NULL;
        """,
        """
        ALTER TABLE splice_combinations
        ADD COLUMN IF NOT EXISTS frontier_result_species_id BIGINT
        REFERENCES frontier_species(species_id) ON DELETE SET NULL;
        """,
    ),
}


def _json_value(value: Optional[Mapping[str, Any]]) -> str:
    return json.dumps(dict(value or {}), ensure_ascii=False, default=str)


class FrontierCatalogStore:
    """Public catalog API shared by Frontier encounters and archive commands."""

    def __init__(self, pool, monsters_path: Path):
        self.pool = pool
        self.monsters_path = monsters_path
        self._ready = False
        self._ready_lock = asyncio.Lock()

    async def ensure_ready(self) -> None:
        if self._ready:
            return
        async with self._ready_lock:
            if self._ready:
                return
            monsters_data = await asyncio.to_thread(
                load_monsters_json, self.monsters_path
            )
            async with self.pool.acquire() as conn:
                async with conn.transaction():
                    # Serialises extension reloads and multiple bot processes.  All
                    # DDL/import work is transactional, so a failed startup leaves
                    # neither a partial schema nor a false migration marker.
                    await conn.execute(
                        "SELECT pg_advisory_xact_lock(hashtext($1));",
                        CATALOG_SCHEMA_VERSION,
                    )
                    for statement in SCHEMA_STATEMENTS:
                        await conn.execute(statement)

                    legacy_tables = {}
                    for table_name, statements in LEGACY_LINK_COLUMNS.items():
                        table_exists = await conn.fetchval(
                            "SELECT to_regclass($1) IS NOT NULL;",
                            f"public.{table_name}",
                        )
                        legacy_tables[table_name] = bool(table_exists)
                        if table_exists:
                            for statement in statements:
                                await conn.execute(statement)

                    legacy_rows = []
                    if legacy_tables["splice_combinations"]:
                        legacy_rows = await conn.fetch(
                            """
                            SELECT id, pet1_default, pet2_default, result_name,
                                   hp, attack, defense, element, url, created_at
                            FROM splice_combinations
                            ORDER BY id ASC;
                            """
                        )
                    seed = build_catalog_seed(monsters_data, legacy_rows)
                    await self._synchronise_seed(conn, seed)
                    await self._ensure_inventory_reference_species(
                        conn, legacy_tables
                    )
                    await self._backfill_legacy_links(conn, legacy_tables)
                    await conn.execute(
                        """
                        INSERT INTO frontier_catalog_migrations (
                            migration_key, details
                        ) VALUES ($1, $2::JSONB)
                        ON CONFLICT (migration_key) DO UPDATE SET
                            details = EXCLUDED.details;
                        """,
                        CATALOG_SCHEMA_VERSION,
                        _json_value(
                            {
                                "species": len(seed.species),
                                "sources": len(seed.sources),
                                "recipes": len(seed.recipes),
                            }
                        ),
                    )
            self._ready = True

    async def refresh_legacy(self) -> None:
        """Re-import newly created legacy recipes and inventory links.

        Normal reads use the cached :meth:`ensure_ready` path.  Splice creation
        is comparatively rare, so its event listener can call this method after
        the legacy transaction commits and make the new stable identities
        available immediately.  The same lock/advisory-lock migration remains
        responsible for concurrency and idempotence.
        """

        async with self._ready_lock:
            self._ready = False
        await self.ensure_ready()

    async def _ensure_inventory_reference_species(self, conn, legacy_tables) -> None:
        """Represent legacy-only pets/eggs without pretending they are wild."""
        inventory_rows = []
        if legacy_tables.get("monster_pets"):
            inventory_rows.extend(
                await conn.fetch(
                    """
                    SELECT DISTINCT ON (default_name)
                           default_name AS legacy_name, element, url
                    FROM monster_pets
                    WHERE default_name IS NOT NULL AND btrim(default_name) <> ''
                    ORDER BY default_name, id ASC;
                    """
                )
            )
        if legacy_tables.get("monster_eggs"):
            inventory_rows.extend(
                await conn.fetch(
                    """
                    SELECT DISTINCT ON (egg_type)
                           egg_type AS legacy_name, element, url
                    FROM monster_eggs
                    WHERE egg_type IS NOT NULL AND btrim(egg_type) <> ''
                    ORDER BY egg_type, id ASC;
                    """
                )
            )
        if not inventory_rows:
            return

        known_rows = await conn.fetch(
            "SELECT DISTINCT normalized_name FROM frontier_species;"
        )
        known_names = {row["normalized_name"] for row in known_rows}
        references = {}
        for row in inventory_rows:
            name = clean_name(row["legacy_name"])
            normalized = normalize_name(name)
            if not name or not normalized or normalized in known_names:
                continue
            references.setdefault(
                normalized,
                (
                    make_species_key("legacy_reference", name),
                    name,
                    normalized,
                    classify_stability(name, default="unknown"),
                    clean_name(row["element"]),
                    clean_name(row["url"]),
                    _json_value({"inventory_only_reference": True}),
                ),
            )
        if references:
            await conn.executemany(
                """
                INSERT INTO frontier_species (
                    stable_key, canonical_name, normalized_name, origin,
                    stability, publication_status, element, image_url, metadata
                ) VALUES (
                    $1, $2, $3, 'legacy_reference', $4, 'hidden', $5, $6,
                    $7::JSONB
                )
                ON CONFLICT (stable_key) DO NOTHING;
                """,
                list(references.values()),
            )

    async def _backfill_legacy_links(self, conn, legacy_tables) -> None:
        """Attach nullable IDs without rewriting any legacy names or payloads."""
        if legacy_tables.get("splice_combinations"):
            link_rows = await conn.fetch(
                """
                SELECT sc.id, sc.pet1_default, sc.pet2_default,
                       r.recipe_id, r.result_species_id,
                       low_species.species_id AS low_species_id,
                       low_species.normalized_name AS low_name,
                       high_species.species_id AS high_species_id,
                       high_species.normalized_name AS high_name
                FROM splice_combinations sc
                JOIN frontier_recipes r ON r.legacy_splice_id = sc.id
                JOIN frontier_species low_species
                    ON low_species.species_id = r.parent_low_species_id
                JOIN frontier_species high_species
                    ON high_species.species_id = r.parent_high_species_id
                WHERE sc.frontier_recipe_id IS NULL
                   OR sc.frontier_parent1_species_id IS NULL
                   OR sc.frontier_parent2_species_id IS NULL
                   OR sc.frontier_result_species_id IS NULL;
                """
            )
            link_updates = []
            for row in link_rows:
                parent1_name = normalize_name(row["pet1_default"])
                parent2_name = normalize_name(row["pet2_default"])
                parent_by_name = {
                    row["low_name"]: int(row["low_species_id"]),
                    row["high_name"]: int(row["high_species_id"]),
                }
                parent1_id = parent_by_name.get(
                    parent1_name, int(row["low_species_id"])
                )
                parent2_id = parent_by_name.get(
                    parent2_name, int(row["high_species_id"])
                )
                link_updates.append(
                    (
                        int(row["recipe_id"]),
                        parent1_id,
                        parent2_id,
                        int(row["result_species_id"]),
                        int(row["id"]),
                    )
                )
            if link_updates:
                await conn.executemany(
                    """
                    UPDATE splice_combinations
                    SET frontier_recipe_id = $1,
                        frontier_parent1_species_id = $2,
                        frontier_parent2_species_id = $3,
                        frontier_result_species_id = $4
                    WHERE id = $5;
                    """,
                    link_updates,
                )

        species_rows = await conn.fetch(
            """
            SELECT species_id, normalized_name, origin, publication_status
            FROM frontier_species
            ORDER BY
                CASE
                    WHEN origin = 'wild' AND publication_status = 'approved' THEN 0
                    WHEN origin = 'splice' THEN 1
                    WHEN origin = 'wild' THEN 2
                    ELSE 3
                END,
                species_id;
            """
        )
        preferred_species_by_name = {}
        for row in species_rows:
            preferred_species_by_name.setdefault(
                row["normalized_name"], int(row["species_id"])
            )

        for table_name, name_column in (
            ("monster_pets", "default_name"),
            ("monster_eggs", "egg_type"),
        ):
            if not legacy_tables.get(table_name):
                continue
            rows = await conn.fetch(
                f"""
                SELECT id, {name_column} AS legacy_name
                FROM {table_name}
                WHERE frontier_species_id IS NULL;
                """
            )
            updates = []
            for row in rows:
                normalized = normalize_name(row["legacy_name"])
                species_id = preferred_species_by_name.get(normalized)
                if species_id is not None:
                    updates.append((species_id, int(row["id"])))
            if updates:
                await conn.executemany(
                    f"""
                    UPDATE {table_name}
                    SET frontier_species_id = $1
                    WHERE id = $2 AND frontier_species_id IS NULL;
                    """,
                    updates,
                )

    async def _synchronise_seed(self, conn, seed: CatalogSeed) -> None:
        if seed.species:
            await conn.executemany(
                """
                INSERT INTO frontier_species (
                    stable_key, canonical_name, normalized_name, origin,
                    generation, stability, publication_status, element,
                    base_hp, base_attack, base_defense, image_url, legacy_tier,
                    metadata
                ) VALUES (
                    $1, $2, $3, $4, $5, $6, $7, $8,
                    $9, $10, $11, $12, $13, $14::JSONB
                )
                ON CONFLICT (stable_key) DO UPDATE SET
                    generation = CASE
                        WHEN EXCLUDED.generation IS NULL THEN frontier_species.generation
                        WHEN frontier_species.generation IS NULL THEN EXCLUDED.generation
                        ELSE LEAST(frontier_species.generation, EXCLUDED.generation)
                    END,
                    element = COALESCE(EXCLUDED.element, frontier_species.element),
                    base_hp = COALESCE(EXCLUDED.base_hp, frontier_species.base_hp),
                    base_attack = COALESCE(EXCLUDED.base_attack, frontier_species.base_attack),
                    base_defense = COALESCE(EXCLUDED.base_defense, frontier_species.base_defense),
                    image_url = COALESCE(EXCLUDED.image_url, frontier_species.image_url),
                    legacy_tier = COALESCE(EXCLUDED.legacy_tier, frontier_species.legacy_tier),
                    metadata = frontier_species.metadata || EXCLUDED.metadata,
                    updated_at = NOW();
                """,
                [
                    (
                        species.stable_key,
                        species.canonical_name,
                        species.normalized_name,
                        species.origin,
                        species.generation,
                        species.stability,
                        species.publication_status,
                        species.element,
                        species.hp,
                        species.attack,
                        species.defense,
                        species.image_url,
                        species.legacy_tier,
                        _json_value(species.metadata),
                    )
                    for species in seed.species
                ],
            )

        species_rows = await conn.fetch(
            "SELECT species_id, stable_key FROM frontier_species;"
        )
        species_id_by_key = {
            row["stable_key"]: int(row["species_id"]) for row in species_rows
        }

        if seed.sources:
            await conn.executemany(
                """
                INSERT INTO frontier_species_sources (
                    source_key, species_id, source_type, legacy_row_id,
                    legacy_name, snapshot
                ) VALUES ($1, $2, $3, $4, $5, $6::JSONB)
                ON CONFLICT (source_key) DO UPDATE SET
                    legacy_name = EXCLUDED.legacy_name,
                    snapshot = EXCLUDED.snapshot,
                    last_seen_at = NOW();
                """,
                [
                    (
                        source.source_key,
                        species_id_by_key[source.species_key],
                        source.source_type,
                        source.legacy_row_id,
                        source.legacy_name,
                        _json_value(source.snapshot),
                    )
                    for source in seed.sources
                ],
            )

        primary_pair_rows = await conn.fetch(
            """
            SELECT canonical_parent_key
            FROM frontier_recipes
            WHERE is_primary = TRUE;
            """
        )
        primary_pairs = {row["canonical_parent_key"] for row in primary_pair_rows}
        recipe_arguments = []
        for recipe in seed.recipes:
            parent_a_id = species_id_by_key[recipe.parent_a_key]
            parent_b_id = species_id_by_key[recipe.parent_b_key]
            parent_low_id, parent_high_id = sorted((parent_a_id, parent_b_id))
            is_primary = (
                recipe.canonical_parent_key not in primary_pairs
                and recipe.is_primary
            )
            if is_primary:
                primary_pairs.add(recipe.canonical_parent_key)
            recipe_arguments.append(
                (
                    recipe.stable_key,
                    recipe.legacy_splice_id,
                    parent_low_id,
                    parent_high_id,
                    species_id_by_key[recipe.result_key],
                    recipe.canonical_parent_key,
                    recipe.variant_rank,
                    is_primary,
                    recipe.generation,
                    recipe.stability,
                    recipe.legacy_parent_a_name,
                    recipe.legacy_parent_b_name,
                    recipe.legacy_result_name,
                    recipe.hp,
                    recipe.attack,
                    recipe.defense,
                    recipe.element,
                    recipe.image_url,
                    recipe.legacy_created_at,
                )
            )

        if recipe_arguments:
            await conn.executemany(
                """
                INSERT INTO frontier_recipes (
                    stable_key, legacy_splice_id, parent_low_species_id,
                    parent_high_species_id, result_species_id,
                    canonical_parent_key, variant_rank, is_primary, generation,
                    stability, legacy_parent_a_name, legacy_parent_b_name,
                    legacy_result_name, legacy_hp, legacy_attack, legacy_defense,
                    legacy_element, legacy_image_url, legacy_created_at
                ) VALUES (
                    $1, $2, $3, $4, $5, $6, $7, $8, $9,
                    $10, $11, $12, $13, $14, $15, $16, $17, $18, $19
                )
                ON CONFLICT (legacy_splice_id) DO UPDATE SET
                    generation = CASE
                        WHEN EXCLUDED.generation IS NULL THEN frontier_recipes.generation
                        WHEN frontier_recipes.generation IS NULL THEN EXCLUDED.generation
                        ELSE LEAST(frontier_recipes.generation, EXCLUDED.generation)
                    END,
                    legacy_parent_a_name = EXCLUDED.legacy_parent_a_name,
                    legacy_parent_b_name = EXCLUDED.legacy_parent_b_name,
                    legacy_result_name = EXCLUDED.legacy_result_name,
                    legacy_hp = EXCLUDED.legacy_hp,
                    legacy_attack = EXCLUDED.legacy_attack,
                    legacy_defense = EXCLUDED.legacy_defense,
                    legacy_element = EXCLUDED.legacy_element,
                    legacy_image_url = EXCLUDED.legacy_image_url,
                    legacy_created_at = EXCLUDED.legacy_created_at,
                    updated_at = NOW();
                """,
                recipe_arguments,
            )
            # A manually selected primary is retained.  If a primary legacy row
            # was removed, the lowest remaining variant becomes the deterministic
            # fallback rather than leaving name-based callers with no answer.
            await conn.execute(
                """
                WITH ranked_missing AS (
                    SELECT r.recipe_id,
                           ROW_NUMBER() OVER (
                               PARTITION BY r.canonical_parent_key
                               ORDER BY r.variant_rank ASC, r.recipe_id ASC
                           ) AS position
                    FROM frontier_recipes r
                    WHERE NOT EXISTS (
                        SELECT 1
                        FROM frontier_recipes primary_recipe
                        WHERE primary_recipe.canonical_parent_key = r.canonical_parent_key
                          AND primary_recipe.is_primary = TRUE
                    )
                )
                UPDATE frontier_recipes r
                SET is_primary = TRUE, updated_at = NOW()
                FROM ranked_missing candidate
                WHERE candidate.recipe_id = r.recipe_id
                  AND candidate.position = 1;
                """
            )

    async def _resolve_species_conn(
        self,
        conn,
        *,
        species_id: Optional[int] = None,
        stable_key: Optional[str] = None,
        legacy_name: Optional[str] = None,
        prefer_origin: Optional[str] = None,
    ) -> Optional[dict[str, Any]]:
        if species_id is not None:
            row = await conn.fetchrow(
                "SELECT * FROM frontier_species WHERE species_id = $1;",
                int(species_id),
            )
        elif stable_key is not None:
            row = await conn.fetchrow(
                "SELECT * FROM frontier_species WHERE stable_key = $1;",
                str(stable_key),
            )
        elif legacy_name is not None:
            normalized = normalize_name(legacy_name)
            if not normalized:
                return None
            row = await conn.fetchrow(
                """
                SELECT *
                FROM frontier_species
                WHERE normalized_name = $1
                ORDER BY
                    CASE WHEN origin = $2 THEN 0 ELSE 1 END,
                    CASE origin
                        WHEN 'wild' THEN 0
                        WHEN 'splice' THEN 1
                        ELSE 2
                    END,
                    species_id
                LIMIT 1;
                """,
                normalized,
                prefer_origin or "",
            )
        else:
            raise ValueError(
                "species_id, stable_key, or legacy_name is required"
            )
        return dict(row) if row else None

    async def resolve_species(
        self,
        legacy_name: Optional[str] = None,
        *,
        species_id: Optional[int] = None,
        stable_key: Optional[str] = None,
        prefer_origin: Optional[str] = None,
    ) -> Optional[dict[str, Any]]:
        await self.ensure_ready()
        async with self.pool.acquire() as conn:
            return await self._resolve_species_conn(
                conn,
                species_id=species_id,
                stable_key=stable_key,
                legacy_name=legacy_name,
                prefer_origin=prefer_origin,
            )

    async def get_recipe_variants(
        self, parent_a_name: str, parent_b_name: str
    ) -> list[dict[str, Any]]:
        """Return every legacy outcome for an unordered parent pair."""
        await self.ensure_ready()
        async with self.pool.acquire() as conn:
            parent_a = await self._resolve_species_conn(
                conn, legacy_name=parent_a_name
            )
            parent_b = await self._resolve_species_conn(
                conn, legacy_name=parent_b_name
            )
            if parent_a is None or parent_b is None:
                return []
            pair_key = make_pair_key(parent_a["stable_key"], parent_b["stable_key"])
            rows = await conn.fetch(
                """
                SELECT r.*, s.stable_key AS result_stable_key,
                       s.canonical_name AS result_name,
                       s.element AS result_element,
                       s.image_url AS result_image_url
                FROM frontier_recipes r
                JOIN frontier_species s ON s.species_id = r.result_species_id
                WHERE r.canonical_parent_key = $1
                ORDER BY r.is_primary DESC, r.variant_rank ASC, r.recipe_id ASC;
                """,
                pair_key,
            )
            return [dict(row) for row in rows]

    async def get_player_summary(self, user_id: int) -> dict[str, int]:
        """Return lightweight Archive totals, including mapped legacy inventory."""
        await self.ensure_ready()
        user_id = int(user_id)
        async with self.pool.acquire() as conn:
            discovery = await conn.fetchrow(
                """
                SELECT
                    COUNT(*)::INTEGER AS archive_species,
                    COUNT(*) FILTER (WHERE first_sighted_at IS NOT NULL)::INTEGER
                        AS sighted_species,
                    COUNT(*) FILTER (WHERE first_defeated_at IS NOT NULL)::INTEGER
                        AS defeated_species,
                    COUNT(*) FILTER (WHERE first_egg_at IS NOT NULL)::INTEGER
                        AS egg_species,
                    COUNT(*) FILTER (WHERE first_created_at IS NOT NULL)::INTEGER
                        AS created_species,
                    COUNT(*) FILTER (WHERE mastered_at IS NOT NULL)::INTEGER
                        AS mastered_species
                FROM frontier_discoveries
                WHERE user_id = $1;
                """,
                user_id,
            )
            inventory = await conn.fetchrow(
                """
                SELECT
                    (
                        SELECT COUNT(*)::INTEGER
                        FROM monster_pets
                        WHERE user_id = $1 AND frontier_species_id IS NOT NULL
                    ) AS current_pets,
                    (
                        SELECT COUNT(DISTINCT frontier_species_id)::INTEGER
                        FROM monster_pets
                        WHERE user_id = $1 AND frontier_species_id IS NOT NULL
                    ) AS current_pet_species,
                    (
                        SELECT COUNT(*)::INTEGER
                        FROM monster_eggs
                        WHERE user_id = $1
                          AND frontier_species_id IS NOT NULL
                          AND hatched = FALSE
                    ) AS current_eggs,
                    (
                        SELECT COUNT(DISTINCT frontier_species_id)::INTEGER
                        FROM monster_eggs
                        WHERE user_id = $1
                          AND frontier_species_id IS NOT NULL
                          AND hatched = FALSE
                    ) AS current_egg_species;
                """,
                user_id,
            )
            catalog = await conn.fetchrow(
                """
                SELECT
                    COUNT(*) FILTER (WHERE origin = 'wild')::INTEGER
                        AS total_wild_species,
                    COUNT(*) FILTER (WHERE origin = 'splice')::INTEGER
                        AS total_splice_species,
                    COUNT(*) FILTER (
                        WHERE origin = 'wild' AND publication_status = 'approved'
                    )::INTEGER AS public_wild_species,
                    COUNT(*) FILTER (
                        WHERE origin = 'splice' AND publication_status = 'approved'
                    )::INTEGER AS published_splice_species
                FROM frontier_species;
                """
            )
        summary = {}
        for row in (discovery, inventory, catalog):
            if row:
                summary.update(
                    {key: int(value or 0) for key, value in dict(row).items()}
                )
        return summary

    async def list_player_species(
        self,
        user_id: int,
        *,
        origin: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """List discovered or currently held species for Bestiary/Archive UIs."""
        await self.ensure_ready()
        if origin is not None and origin not in {
            "wild",
            "splice",
            "legacy_reference",
        }:
            raise ValueError(f"Unsupported species origin: {origin}")
        limit = max(1, min(int(limit), 200))
        offset = max(0, int(offset))
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                WITH pet_counts AS (
                    SELECT frontier_species_id AS species_id, COUNT(*)::INTEGER AS pet_count
                    FROM monster_pets
                    WHERE user_id = $1 AND frontier_species_id IS NOT NULL
                    GROUP BY frontier_species_id
                ),
                egg_counts AS (
                    SELECT frontier_species_id AS species_id, COUNT(*)::INTEGER AS egg_count
                    FROM monster_eggs
                    WHERE user_id = $1
                      AND frontier_species_id IS NOT NULL
                      AND hatched = FALSE
                    GROUP BY frontier_species_id
                )
                SELECT
                    s.species_id, s.stable_key, s.canonical_name, s.origin,
                    s.generation, s.stability, s.publication_status, s.element,
                    s.image_url, s.legacy_tier, s.pve_enabled, s.pve_region,
                    s.pve_tier, s.pve_role,
                    d.first_sighted_at, d.last_sighted_at,
                    d.first_defeated_at, d.last_defeated_at, d.first_egg_at,
                    d.first_owned_at, d.first_created_at, d.mastered_at,
                    COALESCE(d.sightings, 0) AS sightings,
                    COALESCE(d.defeats, 0) AS defeats,
                    COALESCE(d.eggs_obtained, 0) AS eggs_obtained,
                    COALESCE(d.creations, 0) AS creations,
                    COALESCE(p.pet_count, 0) AS current_pet_count,
                    COALESCE(e.egg_count, 0) AS current_egg_count
                FROM frontier_species s
                LEFT JOIN frontier_discoveries d
                    ON d.species_id = s.species_id AND d.user_id = $1
                LEFT JOIN pet_counts p ON p.species_id = s.species_id
                LEFT JOIN egg_counts e ON e.species_id = s.species_id
                WHERE ($2::TEXT IS NULL OR s.origin = $2)
                  AND (
                      d.user_id IS NOT NULL
                      OR COALESCE(p.pet_count, 0) > 0
                      OR COALESCE(e.egg_count, 0) > 0
                  )
                ORDER BY
                    COALESCE(d.updated_at, '-infinity'::TIMESTAMPTZ) DESC,
                    s.canonical_name ASC,
                    s.species_id ASC
                LIMIT $3 OFFSET $4;
                """,
                int(user_id),
                origin,
                limit,
                offset,
            )
            return [dict(row) for row in rows]

    async def set_primary_recipe(self, recipe_id: int) -> None:
        """Atomically choose the canonical outcome while preserving variants."""
        await self.ensure_ready()
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                recipe = await conn.fetchrow(
                    """
                    SELECT recipe_id, canonical_parent_key
                    FROM frontier_recipes
                    WHERE recipe_id = $1
                    FOR UPDATE;
                    """,
                    int(recipe_id),
                )
                if recipe is None:
                    raise LookupError(f"Unknown Frontier recipe ID: {recipe_id}")
                await conn.execute(
                    """
                    UPDATE frontier_recipes
                    SET is_primary = FALSE, updated_at = NOW()
                    WHERE canonical_parent_key = $1 AND is_primary = TRUE;
                    """,
                    recipe["canonical_parent_key"],
                )
                await conn.execute(
                    """
                    UPDATE frontier_recipes
                    SET is_primary = TRUE, updated_at = NOW()
                    WHERE recipe_id = $1;
                    """,
                    int(recipe_id),
                )

    async def record_discovery(
        self,
        user_id: int,
        event_type: str,
        *,
        species_id: Optional[int] = None,
        stable_key: Optional[str] = None,
        legacy_name: Optional[str] = None,
        prefer_origin: Optional[str] = None,
        source: str = "frontier",
        recipe_id: Optional[int] = None,
        quantity: int = 1,
        dedupe_key: Optional[str] = None,
        metadata: Optional[Mapping[str, Any]] = None,
        occurred_at: Optional[datetime] = None,
    ) -> bool:
        """Append one discovery event and update its per-player projection.

        Returns ``False`` only when a supplied ``dedupe_key`` already exists for
        that player.  This makes battle/reward retries safe.
        """
        await self.ensure_ready()
        event_type = str(event_type).strip().lower()
        if event_type not in DISCOVERY_EVENT_TYPES:
            raise ValueError(f"Unsupported discovery event: {event_type}")
        quantity = int(quantity)
        if quantity < 1:
            raise ValueError("Discovery quantity must be at least one")
        user_id = int(user_id)
        if user_id <= 0:
            raise ValueError("Discovery user_id must be positive")
        occurred_at = occurred_at or datetime.now(timezone.utc)

        async with self.pool.acquire() as conn:
            async with conn.transaction():
                species = await self._resolve_species_conn(
                    conn,
                    species_id=species_id,
                    stable_key=stable_key,
                    legacy_name=legacy_name,
                    prefer_origin=prefer_origin,
                )
                if species is None:
                    raise LookupError("The requested species is not in the Frontier catalog")
                event_id = await conn.fetchval(
                    """
                    INSERT INTO frontier_discovery_ledger (
                        user_id, species_id, event_type, source, recipe_id,
                        quantity, dedupe_key, metadata, occurred_at
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8::JSONB, $9)
                    ON CONFLICT (user_id, dedupe_key)
                        WHERE dedupe_key IS NOT NULL
                    DO NOTHING
                    RETURNING event_id;
                    """,
                    user_id,
                    species["species_id"],
                    event_type,
                    str(source or "frontier"),
                    recipe_id,
                    quantity,
                    dedupe_key,
                    _json_value(metadata),
                    occurred_at,
                )
                if event_id is None:
                    return False

                timestamp_values = {
                    "first_sighted_at": occurred_at if event_type == "sighted" else None,
                    "last_sighted_at": occurred_at if event_type == "sighted" else None,
                    "first_defeated_at": occurred_at if event_type == "defeated" else None,
                    "last_defeated_at": occurred_at if event_type == "defeated" else None,
                    "first_egg_at": occurred_at if event_type == "egg_obtained" else None,
                    "first_owned_at": occurred_at if event_type == "ownership_gained" else None,
                    "last_ownership_change_at": (
                        occurred_at
                        if event_type in {"ownership_gained", "ownership_lost"}
                        else None
                    ),
                    "first_created_at": occurred_at if event_type == "created" else None,
                    "mastered_at": occurred_at if event_type == "mastered" else None,
                }
                owned_delta = (
                    quantity
                    if event_type == "ownership_gained"
                    else -quantity if event_type == "ownership_lost" else 0
                )
                await conn.execute(
                    """
                    INSERT INTO frontier_discoveries (
                        user_id, species_id, first_sighted_at, last_sighted_at,
                        first_defeated_at, last_defeated_at, first_egg_at,
                        first_owned_at, last_ownership_change_at, first_created_at,
                        mastered_at, sightings, defeats, eggs_obtained, creations,
                        current_owned_count, updated_at
                    ) VALUES (
                        $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11,
                        $12, $13, $14, $15, GREATEST(0, $16), $17
                    )
                    ON CONFLICT (user_id, species_id) DO UPDATE SET
                        first_sighted_at = COALESCE(
                            frontier_discoveries.first_sighted_at,
                            EXCLUDED.first_sighted_at
                        ),
                        last_sighted_at = COALESCE(
                            GREATEST(
                                frontier_discoveries.last_sighted_at,
                                EXCLUDED.last_sighted_at
                            ),
                            frontier_discoveries.last_sighted_at,
                            EXCLUDED.last_sighted_at
                        ),
                        first_defeated_at = COALESCE(
                            frontier_discoveries.first_defeated_at,
                            EXCLUDED.first_defeated_at
                        ),
                        last_defeated_at = COALESCE(
                            GREATEST(
                                frontier_discoveries.last_defeated_at,
                                EXCLUDED.last_defeated_at
                            ),
                            frontier_discoveries.last_defeated_at,
                            EXCLUDED.last_defeated_at
                        ),
                        first_egg_at = COALESCE(
                            frontier_discoveries.first_egg_at,
                            EXCLUDED.first_egg_at
                        ),
                        first_owned_at = COALESCE(
                            frontier_discoveries.first_owned_at,
                            EXCLUDED.first_owned_at
                        ),
                        last_ownership_change_at = COALESCE(
                            GREATEST(
                                frontier_discoveries.last_ownership_change_at,
                                EXCLUDED.last_ownership_change_at
                            ),
                            frontier_discoveries.last_ownership_change_at,
                            EXCLUDED.last_ownership_change_at
                        ),
                        first_created_at = COALESCE(
                            frontier_discoveries.first_created_at,
                            EXCLUDED.first_created_at
                        ),
                        mastered_at = COALESCE(
                            frontier_discoveries.mastered_at,
                            EXCLUDED.mastered_at
                        ),
                        sightings = frontier_discoveries.sightings + EXCLUDED.sightings,
                        defeats = frontier_discoveries.defeats + EXCLUDED.defeats,
                        eggs_obtained = frontier_discoveries.eggs_obtained + EXCLUDED.eggs_obtained,
                        creations = frontier_discoveries.creations + EXCLUDED.creations,
                        current_owned_count = GREATEST(
                            0,
                            frontier_discoveries.current_owned_count + $16
                        ),
                        updated_at = EXCLUDED.updated_at;
                    """,
                    user_id,
                    species["species_id"],
                    timestamp_values["first_sighted_at"],
                    timestamp_values["last_sighted_at"],
                    timestamp_values["first_defeated_at"],
                    timestamp_values["last_defeated_at"],
                    timestamp_values["first_egg_at"],
                    timestamp_values["first_owned_at"],
                    timestamp_values["last_ownership_change_at"],
                    timestamp_values["first_created_at"],
                    timestamp_values["mastered_at"],
                    quantity if event_type == "sighted" else 0,
                    quantity if event_type == "defeated" else 0,
                    quantity if event_type == "egg_obtained" else 0,
                    quantity if event_type == "created" else 0,
                    owned_delta,
                    occurred_at,
                )
                return True

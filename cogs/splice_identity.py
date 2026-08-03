"""Stable identity helpers for legacy Soulforge splice records.

Historically a splice result was identified by ``result_name``.  Generated
names are not unique, so two unrelated parent pairs could silently resolve to
the same creature.  This module keeps the legacy display name while making the
recipe ID and canonical parent pair the authoritative identity.
"""

from __future__ import annotations

import hashlib
import json
import re

from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Optional

from cogs.frontier_catalog.legacy import clean_name, normalize_name


_STABILITY_SUFFIX_RE = re.compile(
    r"\s*(\[(?:FINAL|SPECIAL|DESTABILISED|DESTABILIZED|UNSTABLE|EVENT)\])\s*$",
    re.IGNORECASE,
)
_RECIPE_SUFFIX_RE = re.compile(r"\s*\[S\d+(?:-\d+)?\]\s*")
_UNIQUE_VIOLATION = "23505"
MAX_SPLICE_RESULT_NAME_LENGTH = 100


def _row_value(row: Mapping[str, Any], key: str, default=None):
    try:
        return row[key]
    except (KeyError, TypeError):
        return default


def canonical_parent_pair_key(parent_a: Any, parent_b: Any) -> Optional[str]:
    """Return an order-independent, normalized identity for a parent pair."""
    normalized = [normalize_name(parent_a), normalize_name(parent_b)]
    if any(name is None for name in normalized):
        return None
    normalized.sort()
    payload = json.dumps(normalized, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _name_with_recipe_suffix(base_name: str, recipe_id: int, variant: int = 1) -> str:
    suffix = f"[S{int(recipe_id)}]"
    if variant > 1:
        suffix = f"[S{int(recipe_id)}-{variant}]"

    marker_match = _STABILITY_SUFFIX_RE.search(base_name)
    marker = marker_match.group(1) if marker_match else ""
    stem = base_name[: marker_match.start()].rstrip() if marker_match else base_name
    reserved = len(suffix) + (len(marker) + 2 if marker else 1)
    stem = stem[: max(1, MAX_SPLICE_RESULT_NAME_LENGTH - reserved)].rstrip()
    if marker:
        return f"{stem} {suffix} {marker}"
    return f"{stem} {suffix}"


def disambiguated_splice_name(
    base_name: Any,
    recipe_id: int,
    reserved_keys: Iterable[str] = (),
) -> str:
    """Build a deterministic unique display name tied to a recipe ID."""
    cleaned = clean_name(base_name) or "Unnamed Splice"
    reserved = set(reserved_keys)
    variant = 1
    while True:
        candidate = _name_with_recipe_suffix(cleaned, recipe_id, variant)
        if normalize_name(candidate) not in reserved:
            return candidate
        variant += 1


@dataclass(frozen=True)
class SpliceNameRepair:
    splice_id: int
    old_name: str
    base_name: str
    new_name: str
    normalized_base_name: str


def plan_duplicate_splice_names(rows: Iterable[Mapping[str, Any]]) -> list[SpliceNameRepair]:
    """Plan idempotent recipe-ID suffixes for every row in a duplicate group."""
    parsed_rows = []
    groups: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        splice_id = int(_row_value(row, "id") or 0)
        current_name = clean_name(_row_value(row, "result_name"))
        base_name = clean_name(_row_value(row, "base_result_name")) or current_name
        base_key = normalize_name(base_name)
        if splice_id <= 0 or current_name is None or base_name is None or base_key is None:
            continue
        parsed = {
            "id": splice_id,
            "current_name": current_name,
            "base_name": base_name,
            "base_key": base_key,
        }
        parsed_rows.append(parsed)
        groups.setdefault(base_key, []).append(parsed)

    duplicate_keys = {key for key, entries in groups.items() if len(entries) > 1}
    reserved_keys = {
        normalize_name(entry["current_name"])
        for entry in parsed_rows
        if entry["base_key"] not in duplicate_keys
    }
    reserved_keys.discard(None)

    repairs = []
    for base_key in sorted(duplicate_keys):
        for entry in sorted(groups[base_key], key=lambda item: item["id"]):
            new_name = disambiguated_splice_name(
                entry["base_name"],
                entry["id"],
                reserved_keys,
            )
            reserved_keys.add(normalize_name(new_name))
            repairs.append(
                SpliceNameRepair(
                    splice_id=entry["id"],
                    old_name=entry["current_name"],
                    base_name=entry["base_name"],
                    new_name=new_name,
                    normalized_base_name=base_key,
                )
            )
    return repairs


@dataclass(frozen=True)
class SpliceParentRepair:
    splice_id: int
    slot: str
    orphan_name: str
    new_name: str
    parent_splice_id: int


@dataclass(frozen=True)
class OrphanParentGroup:
    orphan_name: str
    children: tuple[int, ...]
    candidates: tuple[tuple[int, str], ...]


def _pre_repair_name(row: Mapping[str, Any]) -> Optional[str]:
    """Recover the name a recipe carried before it was disambiguated."""
    stored = clean_name(_row_value(row, "base_result_name"))
    if stored:
        return stored
    current = clean_name(_row_value(row, "result_name"))
    if not current or "[S" not in current:
        return None
    return clean_name(_RECIPE_SUFFIX_RE.sub(" ", current))


def plan_orphan_parent_repairs(
    rows: Iterable[Mapping[str, Any]],
    base_monster_names: Iterable[Any],
) -> tuple[list[SpliceParentRepair], list[OrphanParentGroup], list[OrphanParentGroup]]:
    """Repoint parent names left dangling when a duplicate result was renamed.

    Legacy lineage is stored as parent *names*, so renaming ``X`` to ``X [S12]``
    orphans every recipe still referencing ``X``.  Returns the unambiguous
    repairs plus the orphans that need a human: ``ambiguous`` ones have several
    rename candidates, ``unresolved`` ones have none at all.
    """
    parsed: list[tuple[int, Mapping[str, Any], Optional[str]]] = []
    known: set[str] = {
        cleaned for name in base_monster_names if (cleaned := clean_name(name))
    }
    for row in rows:
        try:
            splice_id = int(_row_value(row, "id"))
        except (TypeError, ValueError):
            continue
        name = clean_name(_row_value(row, "result_name"))
        if name:
            known.add(name)
        parsed.append((splice_id, row, name))

    candidates: dict[str, list[tuple[int, str]]] = {}
    for splice_id, row, name in parsed:
        if not name:
            continue
        previous = _pre_repair_name(row)
        if previous and previous != name:
            candidates.setdefault(previous, []).append((splice_id, name))

    repairs: list[SpliceParentRepair] = []
    children_by_orphan: dict[str, list[int]] = {}
    for splice_id, row, _name in parsed:
        for slot in ("pet1_default", "pet2_default"):
            parent = clean_name(_row_value(row, slot))
            if not parent or parent in known:
                continue
            children_by_orphan.setdefault(parent, []).append(splice_id)
            options = candidates.get(parent, ())
            if len(options) == 1:
                parent_splice_id, new_name = options[0]
                repairs.append(
                    SpliceParentRepair(
                        splice_id=splice_id,
                        slot=slot,
                        orphan_name=parent,
                        new_name=new_name,
                        parent_splice_id=parent_splice_id,
                    )
                )

    ambiguous: list[OrphanParentGroup] = []
    unresolved: list[OrphanParentGroup] = []
    for orphan_name in sorted(children_by_orphan):
        options = tuple(sorted(candidates.get(orphan_name, ())))
        if len(options) == 1:
            continue
        group = OrphanParentGroup(
            orphan_name=orphan_name,
            children=tuple(sorted(set(children_by_orphan[orphan_name]))),
            candidates=options,
        )
        (ambiguous if options else unresolved).append(group)

    repairs.sort(key=lambda repair: (repair.splice_id, repair.slot))
    return repairs, ambiguous, unresolved


async def ensure_splice_identity_schema(conn) -> None:
    """Add nullable identity links without rewriting legacy splice data."""
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS splice_combinations (
            id SERIAL PRIMARY KEY,
            pet1_default TEXT,
            pet2_default TEXT,
            result_name TEXT,
            hp INTEGER,
            attack INTEGER,
            defense INTEGER,
            element TEXT,
            url TEXT,
            created_at TIMESTAMP DEFAULT NOW()
        );
        ALTER TABLE splice_combinations
            ADD COLUMN IF NOT EXISTS base_result_name TEXT,
            ADD COLUMN IF NOT EXISTS result_name_key TEXT,
            ADD COLUMN IF NOT EXISTS parent_pair_key TEXT,
            ADD COLUMN IF NOT EXISTS parent1_splice_combination_id INTEGER,
            ADD COLUMN IF NOT EXISTS parent2_splice_combination_id INTEGER;
        UPDATE splice_combinations
        SET base_result_name = result_name
        WHERE base_result_name IS NULL;
        CREATE UNIQUE INDEX IF NOT EXISTS splice_combinations_result_name_key_uidx
            ON splice_combinations(result_name_key)
            WHERE result_name_key IS NOT NULL;
        CREATE UNIQUE INDEX IF NOT EXISTS splice_combinations_parent_pair_key_uidx
            ON splice_combinations(parent_pair_key)
            WHERE parent_pair_key IS NOT NULL;
        CREATE INDEX IF NOT EXISTS splice_combinations_parent_recipe_idx
            ON splice_combinations(
                parent1_splice_combination_id,
                parent2_splice_combination_id
            );
        ALTER TABLE monster_pets
            ADD COLUMN IF NOT EXISTS splice_combination_id INTEGER;
        CREATE INDEX IF NOT EXISTS monster_pets_splice_combination_idx
            ON monster_pets(splice_combination_id)
            WHERE splice_combination_id IS NOT NULL;
        """
    )

    requests_exist = await conn.fetchval(
        "SELECT to_regclass('public.splice_requests') IS NOT NULL;"
    )
    if requests_exist:
        await conn.execute(
            """
            ALTER TABLE splice_requests
                ADD COLUMN IF NOT EXISTS result_pet_id INTEGER,
                ADD COLUMN IF NOT EXISTS result_splice_combination_id INTEGER,
                ADD COLUMN IF NOT EXISTS result_name TEXT;
            CREATE INDEX IF NOT EXISTS splice_requests_result_splice_idx
                ON splice_requests(result_splice_combination_id)
                WHERE result_splice_combination_id IS NOT NULL;
            """
        )


async def _parent_recipe_ids(conn, parent_pet_ids: tuple[Optional[int], Optional[int]]):
    valid_ids = sorted({int(pet_id) for pet_id in parent_pet_ids if pet_id})
    if not valid_ids:
        return None, None
    rows = await conn.fetch(
        """
        SELECT id, splice_combination_id
        FROM monster_pets
        WHERE id = ANY($1::int[]);
        """,
        valid_ids,
    )
    recipe_by_pet = {
        int(row["id"]): (
            int(row["splice_combination_id"])
            if row["splice_combination_id"] is not None
            else None
        )
        for row in rows
    }
    return tuple(
        recipe_by_pet.get(int(pet_id)) if pet_id else None
        for pet_id in parent_pet_ids
    )


@dataclass(frozen=True)
class SpliceCombinationReservation:
    row: Mapping[str, Any]
    created: bool


async def reserve_splice_combination(
    conn,
    *,
    parent1_name: Any,
    parent2_name: Any,
    proposed_result_name: Any,
    hp: Any,
    attack: Any,
    defense: Any,
    element: Any,
    url: Any,
    parent1_pet_id: Optional[int] = None,
    parent2_pet_id: Optional[int] = None,
) -> SpliceCombinationReservation:
    """Get an existing parent-pair recipe or atomically reserve a unique one."""
    await ensure_splice_identity_schema(conn)

    parent1 = clean_name(parent1_name)
    parent2 = clean_name(parent2_name)
    base_name = clean_name(proposed_result_name) or "Unnamed Splice"
    pair_key = canonical_parent_pair_key(parent1, parent2)
    if parent1 is None or parent2 is None or pair_key is None:
        raise ValueError("A splice recipe requires two usable parent names.")

    parent1_recipe_id, parent2_recipe_id = await _parent_recipe_ids(
        conn,
        (parent1_pet_id, parent2_pet_id),
    )
    legacy_names = await conn.fetch(
        "SELECT COALESCE(base_result_name, result_name) AS base_name FROM splice_combinations;"
    )
    legacy_name_counts: dict[str, int] = {}
    for row in legacy_names:
        name_key = normalize_name(row["base_name"])
        if name_key:
            legacy_name_counts[name_key] = legacy_name_counts.get(name_key, 0) + 1
    for parent_name, parent_pet_id, parent_recipe_id in (
        (parent1, parent1_pet_id, parent1_recipe_id),
        (parent2, parent2_pet_id, parent2_recipe_id),
    ):
        if (
            parent_pet_id is not None
            and parent_recipe_id is None
            and legacy_name_counts.get(normalize_name(parent_name), 0) > 1
        ):
            raise ValueError(
                f"Parent pet {int(parent_pet_id)} has an ambiguous legacy splice identity. "
                "Run the splice-name repair before processing this request."
            )

    for _ in range(4):
        existing = await conn.fetchrow(
            """
            SELECT *
            FROM splice_combinations
            WHERE parent_pair_key = $1
            ORDER BY id ASC
            LIMIT 1;
            """,
            pair_key,
        )
        if existing is None:
            legacy_rows = await conn.fetch(
                """
                SELECT *
                FROM splice_combinations
                WHERE parent_pair_key IS NULL
                ORDER BY id ASC;
                """
            )
            existing = next(
                (
                    row
                    for row in legacy_rows
                    if canonical_parent_pair_key(
                        row["pet1_default"], row["pet2_default"]
                    )
                    == pair_key
                ),
                None,
            )
        if existing is not None:
            return SpliceCombinationReservation(dict(existing), False)

        existing_names = await conn.fetch(
            "SELECT result_name, base_result_name FROM splice_combinations;"
        )
        reserved_keys = {
            normalized
            for row in existing_names
            for normalized in (
                normalize_name(row["result_name"]),
                normalize_name(row["base_result_name"]),
            )
            if normalized is not None
        }
        new_id = int(
            await conn.fetchval(
                "SELECT nextval(pg_get_serial_sequence('splice_combinations', 'id'));"
            )
        )
        result_name = base_name
        if normalize_name(result_name) in reserved_keys:
            result_name = disambiguated_splice_name(base_name, new_id, reserved_keys)

        try:
            async with conn.transaction():
                row = await conn.fetchrow(
                    """
                    INSERT INTO splice_combinations (
                        id, pet1_default, pet2_default, result_name,
                        base_result_name, result_name_key, parent_pair_key,
                        parent1_splice_combination_id,
                        parent2_splice_combination_id,
                        hp, attack, defense, element, url
                    ) VALUES (
                        $1, $2, $3, $4, $5, $6, $7,
                        $8, $9, $10, $11, $12, $13, $14
                    )
                    RETURNING *;
                    """,
                    new_id,
                    parent1,
                    parent2,
                    result_name,
                    base_name,
                    normalize_name(result_name),
                    pair_key,
                    parent1_recipe_id,
                    parent2_recipe_id,
                    int(hp),
                    int(attack),
                    int(defense),
                    clean_name(element),
                    clean_name(url),
                )
            return SpliceCombinationReservation(dict(row), True)
        except Exception as error:
            if getattr(error, "sqlstate", None) != _UNIQUE_VIOLATION:
                raise

    raise RuntimeError("Could not reserve a unique splice recipe after four attempts.")


async def link_created_splice_result(
    conn,
    *,
    request_id: Optional[int],
    pet_id: int,
    splice_id: int,
    result_name: str,
) -> None:
    """Persist direct result links after a splice pet has been created."""
    await conn.execute(
        """
        UPDATE monster_pets
        SET splice_combination_id = $1
        WHERE id = $2;
        """,
        int(splice_id),
        int(pet_id),
    )
    if request_id is not None:
        await conn.execute(
            """
            UPDATE splice_requests
            SET status = 'completed',
                result_pet_id = $1,
                result_splice_combination_id = $2,
                result_name = $3
            WHERE id = $4;
            """,
            int(pet_id),
            int(splice_id),
            result_name,
            int(request_id),
        )

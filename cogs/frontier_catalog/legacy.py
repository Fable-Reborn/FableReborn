"""Pure legacy-to-catalog conversion helpers for Soulforge Frontiers.

This module intentionally has no Discord or database imports.  Keeping the
normalisation and generation rules pure makes the compatibility layer easy to
test, and prevents the new catalog from changing legacy pet or splice rows.
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional


_SPACE_RE = re.compile(r"\s+")
_SLUG_RE = re.compile(r"[^a-z0-9]+")

STABILITY_MARKERS = (
    ("[FINAL]", "final"),
    ("[SPECIAL]", "special"),
    ("[DESTABILISED]", "destabilised"),
    ("[DESTABILIZED]", "destabilised"),
    ("[UNSTABLE]", "unstable"),
)


def clean_name(value: Any) -> Optional[str]:
    """Return a display-safe legacy name, or ``None`` for unusable values."""
    if not isinstance(value, str):
        return None
    cleaned = _SPACE_RE.sub(" ", unicodedata.normalize("NFKC", value).strip())
    return cleaned or None


def normalize_name(value: Any) -> Optional[str]:
    """Canonical case-insensitive identity used by the catalog.

    Legacy gameplay remains name based and case sensitive.  This value is only
    used to link those names to a stable catalog identity.
    """
    cleaned = clean_name(value)
    return cleaned.casefold() if cleaned else None


def classify_stability(name: Any, *, default: str = "stable") -> str:
    cleaned = clean_name(name)
    if not cleaned:
        return "unknown"
    upper_name = cleaned.upper()
    for marker, stability in STABILITY_MARKERS:
        if marker in upper_name:
            return stability
    return default


def make_species_key(origin: str, name: str) -> str:
    """Build a deterministic key without relying on a mutable display name."""
    normalized = normalize_name(name)
    if not normalized:
        raise ValueError("A species key requires a non-empty name")
    if origin not in {"wild", "splice", "legacy_reference"}:
        raise ValueError(f"Unsupported species origin: {origin}")
    slug = _SLUG_RE.sub("-", normalized).strip("-")[:48] or "unnamed"
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]
    return f"{origin}:{slug}:{digest}"


def make_pair_key(parent_a_key: str, parent_b_key: str) -> str:
    """Return one key for A+B and B+A while retaining both variants in DB."""
    low, high = sorted((str(parent_a_key), str(parent_b_key)))
    digest = hashlib.sha256(f"{low}\0{high}".encode("utf-8")).hexdigest()
    return f"pair:{digest}"


@dataclass(frozen=True)
class SpeciesSeed:
    stable_key: str
    canonical_name: str
    normalized_name: str
    origin: str
    generation: Optional[int]
    stability: str
    publication_status: str
    element: Optional[str]
    hp: Optional[int]
    attack: Optional[int]
    defense: Optional[int]
    image_url: Optional[str]
    legacy_tier: Optional[int]
    metadata: Mapping[str, Any]


@dataclass(frozen=True)
class SpeciesSourceSeed:
    source_key: str
    species_key: str
    source_type: str
    legacy_row_id: Optional[int]
    legacy_name: str
    snapshot: Mapping[str, Any]


@dataclass(frozen=True)
class RecipeSeed:
    stable_key: str
    legacy_splice_id: int
    parent_a_key: str
    parent_b_key: str
    result_key: str
    canonical_parent_key: str
    variant_rank: int
    is_primary: bool
    generation: Optional[int]
    stability: str
    legacy_parent_a_name: str
    legacy_parent_b_name: str
    legacy_result_name: str
    hp: Optional[int]
    attack: Optional[int]
    defense: Optional[int]
    element: Optional[str]
    image_url: Optional[str]
    legacy_created_at: Any


@dataclass(frozen=True)
class CatalogSeed:
    species: tuple[SpeciesSeed, ...]
    sources: tuple[SpeciesSourceSeed, ...]
    recipes: tuple[RecipeSeed, ...]


def load_monsters_json(path: Path) -> Mapping[str, Any]:
    with path.open("r", encoding="utf-8") as monsters_file:
        data = json.load(monsters_file)
    if not isinstance(data, dict):
        raise ValueError("monsters.json must contain an object keyed by tier")
    return data


def _as_positive_int(value: Any) -> Optional[int]:
    try:
        converted = int(value)
    except (TypeError, ValueError):
        return None
    return converted if converted >= 0 else None


def _row_value(row: Any, key: str, default: Any = None) -> Any:
    try:
        return row[key]
    except (KeyError, TypeError, IndexError):
        return default


def resolve_legacy_generations(
    base_names: Iterable[str], rows: Iterable[Any]
) -> tuple[dict[str, int], dict[int, int]]:
    """Reproduce the existing exact-name Soulforge generation rules.

    Base creatures are internal generation ``-1``; their direct children are
    generation 0.  The returned recipe mapping is keyed by legacy splice ID.
    """
    generation_by_name = {
        cleaned: -1
        for name in base_names
        if (cleaned := clean_name(name)) is not None
    }
    completed_rows = tuple(rows)

    for _ in range(max(1, len(completed_rows) + 1)):
        changed = False
        for row in completed_rows:
            parent_a = clean_name(_row_value(row, "pet1_default"))
            parent_b = clean_name(_row_value(row, "pet2_default"))
            result = clean_name(_row_value(row, "result_name"))
            if not parent_a or not parent_b or not result:
                continue
            parent_a_gen = generation_by_name.get(parent_a)
            parent_b_gen = generation_by_name.get(parent_b)
            if parent_a_gen is None or parent_b_gen is None:
                continue
            child_generation = max(parent_a_gen, parent_b_gen) + 1
            existing_generation = generation_by_name.get(result)
            if existing_generation == -1:
                continue
            if existing_generation is None or child_generation < existing_generation:
                generation_by_name[result] = child_generation
                changed = True
        if not changed:
            break

    recipe_generations: dict[int, int] = {}
    for row in completed_rows:
        legacy_id = _as_positive_int(_row_value(row, "id"))
        parent_a = clean_name(_row_value(row, "pet1_default"))
        parent_b = clean_name(_row_value(row, "pet2_default"))
        if legacy_id is None or not parent_a or not parent_b:
            continue
        parent_a_gen = generation_by_name.get(parent_a)
        parent_b_gen = generation_by_name.get(parent_b)
        if parent_a_gen is not None and parent_b_gen is not None:
            recipe_generations[legacy_id] = max(parent_a_gen, parent_b_gen) + 1

    return generation_by_name, recipe_generations


def build_catalog_seed(
    monsters_data: Mapping[str, Any], legacy_rows: Iterable[Any]
) -> CatalogSeed:
    """Convert legacy JSON and rows into deterministic, non-destructive seeds."""
    rows = sorted(
        tuple(legacy_rows), key=lambda row: int(_row_value(row, "id", 0) or 0)
    )
    wild_by_name: dict[str, dict[str, Any]] = {}
    wild_sources: list[SpeciesSourceSeed] = []
    base_names: list[str] = []

    for tier_key, monster_list in monsters_data.items():
        if not isinstance(monster_list, list):
            continue
        try:
            tier = int(tier_key)
        except (TypeError, ValueError):
            tier = None
        for occurrence, monster in enumerate(monster_list):
            if not isinstance(monster, dict):
                continue
            name = clean_name(monster.get("name"))
            normalized = normalize_name(name)
            if not name or not normalized:
                continue
            base_names.append(name)
            species_key = make_species_key("wild", name)
            public = bool(monster.get("ispublic", True))
            candidate = {
                "stable_key": species_key,
                "canonical_name": name,
                "normalized_name": normalized,
                "origin": "wild",
                "generation": None,
                "stability": "stable",
                "publication_status": "approved" if public else "hidden",
                "element": clean_name(monster.get("element")),
                "hp": _as_positive_int(monster.get("hp")),
                "attack": _as_positive_int(monster.get("attack")),
                "defense": _as_positive_int(monster.get("defense")),
                "image_url": clean_name(monster.get("url")),
                "legacy_tier": tier,
                "metadata": {"legacy_public": public},
            }
            current = wild_by_name.get(normalized)
            if current is None:
                wild_by_name[normalized] = candidate
            else:
                # Duplicate JSON entries remain one species.  Public visibility
                # wins, while the first (lowest file-order) combat row is kept.
                current["publication_status"] = (
                    "approved"
                    if public or current["publication_status"] == "approved"
                    else "hidden"
                )
                current["metadata"] = {
                    "legacy_public": current["publication_status"] == "approved",
                    "duplicate_json_entries": int(
                        current["metadata"].get("duplicate_json_entries", 1)
                    )
                    + 1,
                }

            source_suffix = f":{occurrence}" if occurrence else ""
            wild_sources.append(
                SpeciesSourceSeed(
                    source_key=f"monster-json:{tier_key}:{species_key}{source_suffix}",
                    species_key=species_key,
                    source_type="monster_json",
                    legacy_row_id=None,
                    legacy_name=name,
                    snapshot=dict(monster),
                )
            )

    generation_by_name, recipe_generations = resolve_legacy_generations(
        base_names, rows
    )

    splice_by_name: dict[str, dict[str, Any]] = {}
    splice_sources: list[SpeciesSourceSeed] = []
    parent_display_by_normalized: dict[str, str] = {}
    for row in rows:
        legacy_id = _as_positive_int(_row_value(row, "id"))
        result_name = clean_name(_row_value(row, "result_name"))
        result_normalized = normalize_name(result_name)
        if legacy_id is None or not result_name or not result_normalized:
            continue
        result_key = make_species_key("splice", result_name)
        generation = generation_by_name.get(result_name)
        candidate = {
            "stable_key": result_key,
            "canonical_name": result_name,
            "normalized_name": result_normalized,
            "origin": "splice",
            "generation": generation if generation is not None and generation >= 0 else None,
            "stability": classify_stability(result_name),
            "publication_status": "draft",
            "element": clean_name(_row_value(row, "element")),
            "hp": _as_positive_int(_row_value(row, "hp")),
            "attack": _as_positive_int(_row_value(row, "attack")),
            "defense": _as_positive_int(_row_value(row, "defense")),
            "image_url": clean_name(_row_value(row, "url")),
            "legacy_tier": None,
            "metadata": {"first_legacy_splice_id": legacy_id},
        }
        current = splice_by_name.get(result_normalized)
        if current is None:
            splice_by_name[result_normalized] = candidate
        elif generation is not None and generation >= 0:
            current_generation = current["generation"]
            if current_generation is None or generation < current_generation:
                current["generation"] = generation

        snapshot = {
            key: _row_value(row, key)
            for key in (
                "id",
                "pet1_default",
                "pet2_default",
                "result_name",
                "hp",
                "attack",
                "defense",
                "element",
                "url",
                "created_at",
            )
        }
        splice_sources.append(
            SpeciesSourceSeed(
                source_key=f"splice-result:{legacy_id}",
                species_key=result_key,
                source_type="splice_result",
                legacy_row_id=legacy_id,
                legacy_name=result_name,
                snapshot=snapshot,
            )
        )
        for parent_field in ("pet1_default", "pet2_default"):
            parent_name = clean_name(_row_value(row, parent_field))
            parent_normalized = normalize_name(parent_name)
            if parent_name and parent_normalized:
                parent_display_by_normalized.setdefault(parent_normalized, parent_name)

    reference_by_name: dict[str, dict[str, Any]] = {}
    for normalized, name in parent_display_by_normalized.items():
        if normalized in wild_by_name or normalized in splice_by_name:
            continue
        reference_by_name[normalized] = {
            "stable_key": make_species_key("legacy_reference", name),
            "canonical_name": name,
            "normalized_name": normalized,
            "origin": "legacy_reference",
            "generation": None,
            "stability": classify_stability(name, default="unknown"),
            "publication_status": "hidden",
            "element": None,
            "hp": None,
            "attack": None,
            "defense": None,
            "image_url": None,
            "legacy_tier": None,
            "metadata": {"unresolved_parent_reference": True},
        }

    all_species_dicts = (
        list(wild_by_name.values())
        + list(splice_by_name.values())
        + list(reference_by_name.values())
    )
    species = tuple(
        SpeciesSeed(**values)
        for values in sorted(all_species_dicts, key=lambda item: item["stable_key"])
    )

    def parent_species_key(parent_name: str) -> str:
        normalized = normalize_name(parent_name)
        if normalized in wild_by_name:
            return wild_by_name[normalized]["stable_key"]
        if normalized in splice_by_name:
            return splice_by_name[normalized]["stable_key"]
        return reference_by_name[normalized]["stable_key"]

    pair_counts: dict[str, int] = {}
    recipes: list[RecipeSeed] = []
    for row in rows:
        legacy_id = _as_positive_int(_row_value(row, "id"))
        parent_a_name = clean_name(_row_value(row, "pet1_default"))
        parent_b_name = clean_name(_row_value(row, "pet2_default"))
        result_name = clean_name(_row_value(row, "result_name"))
        if legacy_id is None or not parent_a_name or not parent_b_name or not result_name:
            continue
        parent_a_key = parent_species_key(parent_a_name)
        parent_b_key = parent_species_key(parent_b_name)
        result_key = make_species_key("splice", result_name)
        pair_key = make_pair_key(parent_a_key, parent_b_key)
        variant_rank = pair_counts.get(pair_key, 0) + 1
        pair_counts[pair_key] = variant_rank
        recipes.append(
            RecipeSeed(
                stable_key=f"legacy-splice:{legacy_id}",
                legacy_splice_id=legacy_id,
                parent_a_key=parent_a_key,
                parent_b_key=parent_b_key,
                result_key=result_key,
                canonical_parent_key=pair_key,
                variant_rank=variant_rank,
                is_primary=variant_rank == 1,
                generation=recipe_generations.get(legacy_id),
                stability=classify_stability(result_name),
                legacy_parent_a_name=parent_a_name,
                legacy_parent_b_name=parent_b_name,
                legacy_result_name=result_name,
                hp=_as_positive_int(_row_value(row, "hp")),
                attack=_as_positive_int(_row_value(row, "attack")),
                defense=_as_positive_int(_row_value(row, "defense")),
                element=clean_name(_row_value(row, "element")),
                image_url=clean_name(_row_value(row, "url")),
                legacy_created_at=_row_value(row, "created_at"),
            )
        )

    return CatalogSeed(
        species=species,
        sources=tuple(wild_sources + splice_sources),
        recipes=tuple(recipes),
    )

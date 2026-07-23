"""Pure PvE content helpers for the Soulforge Frontiers update.

This module deliberately has no Discord or database dependency.  The Battles cog
can load rows from ``splice_combinations`` and hand them to these helpers without
letting mutable database stats, random sampling, or name markers decide combat
balance.
"""

from __future__ import annotations

import copy
import datetime as dt
import json
import math
import random
import re
import statistics
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Iterable, Mapping, Sequence


DEFAULT_ROSTER_PATH = Path(__file__).resolve().parent / "data" / "frontier_roster.json"
SCHEMA_VERSION = 1
ROTATION_WEEK = dt.timedelta(days=7)
VALID_ELEMENTS = frozenset(
    {
        "Corrupted",
        "Dark",
        "Electric",
        "Fire",
        "Light",
        "Nature",
        "Water",
        "Wind",
    }
)
VALID_ROLES = frozenset({"regular", "elite", "boss"})
ROLE_COUNTS_PER_REGION = {"regular": 9, "elite": 2, "boss": 1}
_REGION_ID_PATTERN = re.compile(r"^[a-z0-9]+(?:_[a-z0-9]+)*$")

# These are only used if the supplied public pool has no valid rows for a tier.
# They mirror the current public roster medians and keep the helper safe in tests,
# migrations, and partial development databases.
FALLBACK_TIER_STATS = {
    1: {"hp": 190, "attack": 95, "defense": 90},
    2: {"hp": 275, "attack": 162, "defense": 155},
    3: {"hp": 215, "attack": 220, "defense": 210},
    4: {"hp": 315, "attack": 285, "defense": 275},
    5: {"hp": 415, "attack": 385, "defense": 375},
    6: {"hp": 515, "attack": 472, "defense": 460},
    7: {"hp": 615, "attack": 572, "defense": 560},
    8: {"hp": 830, "attack": 650, "defense": 650},
    9: {"hp": 800, "attack": 780, "defense": 775},
    10: {"hp": 1100, "attack": 780, "defense": 900},
}

# Raw splice stats are first rescaled to the public tier baseline and clamped to
# +/- 25% per stat.  Role multipliers are applied only after that normalization.
ROLE_STAT_MULTIPLIERS = {
    "regular": {"hp": Decimal("1.00"), "attack": Decimal("1.00"), "defense": Decimal("1.00")},
    "elite": {"hp": Decimal("1.35"), "attack": Decimal("1.10"), "defense": Decimal("1.10")},
    "boss": {"hp": Decimal("2.25"), "attack": Decimal("1.20"), "defense": Decimal("1.20")},
}


class FrontierConfigError(ValueError):
    """Raised when the checked-in Frontier roster is unsafe or incomplete."""

    def __init__(self, errors: Sequence[str]):
        self.errors = tuple(str(error) for error in errors)
        super().__init__("Invalid Frontier roster: " + "; ".join(self.errors))


@dataclass(frozen=True)
class FrontierRotationState:
    """The deterministic active region for one UTC rotation week."""

    absolute_week: int
    cycle_week: int
    cycle_number: int
    region_id: str
    starts_at: dt.datetime
    ends_at: dt.datetime


@dataclass(frozen=True)
class FrontierPoolBuild:
    """A location pool plus non-fatal content drift diagnostics."""

    pool: dict[int, list[dict]]
    rotation: FrontierRotationState
    region_id: str
    is_featured: bool
    included_legacy_splice_ids: tuple[int, ...] = ()
    missing_legacy_splice_ids: tuple[int, ...] = ()
    name_mismatches: tuple[int, ...] = ()
    generation_mismatches: tuple[int, ...] = ()


def _canonical_element(value) -> str:
    text = str(value or "").strip()
    if not text:
        return "Unknown"
    for element in VALID_ELEMENTS:
        if text.casefold() == element.casefold():
            return element
    return text


def _parse_utc_anchor(value) -> dt.datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("rotation.anchor_monday_utc must be an ISO-8601 string")
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    parsed = dt.datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        raise ValueError("rotation.anchor_monday_utc must include a timezone")
    parsed = parsed.astimezone(dt.timezone.utc)
    if parsed.weekday() != 0 or parsed.time() != dt.time(0, 0):
        raise ValueError("rotation.anchor_monday_utc must be Monday 00:00:00 UTC")
    return parsed


def validate_frontier_config(data: Mapping) -> dict:
    """Validate and normalize a Frontier roster document.

    Validation is intentionally strict: a bad recipe id or unreachable tier must
    fail at startup/test time instead of silently changing a live weekly pool.
    """

    errors: list[str] = []
    if not isinstance(data, Mapping):
        raise FrontierConfigError(("document must be a JSON object",))

    normalized = copy.deepcopy(dict(data))
    if normalized.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION}")

    rotation = normalized.get("rotation")
    if not isinstance(rotation, Mapping):
        errors.append("rotation must be an object")
        rotation = {}

    try:
        anchor = _parse_utc_anchor(rotation.get("anchor_monday_utc"))
    except (TypeError, ValueError) as exc:
        errors.append(str(exc))
        anchor = dt.datetime(2026, 7, 20, tzinfo=dt.timezone.utc)

    region_order = rotation.get("region_order")
    if not isinstance(region_order, list):
        errors.append("rotation.region_order must be a list")
        region_order = []
    region_order = [str(region_id).strip() for region_id in region_order]
    if len(region_order) != 4 or len(set(region_order)) != 4:
        errors.append("rotation.region_order must contain four unique region ids")

    regions = normalized.get("regions")
    if not isinstance(regions, list):
        errors.append("regions must be a list")
        regions = []
    if len(regions) != 4:
        errors.append("regions must contain exactly four regions")

    normalized_regions: list[dict] = []
    region_by_id: dict[str, dict] = {}
    for index, raw_region in enumerate(regions):
        label = f"regions[{index}]"
        if not isinstance(raw_region, Mapping):
            errors.append(f"{label} must be an object")
            continue
        region = dict(raw_region)
        region_id = str(region.get("id") or "").strip()
        if not _REGION_ID_PATTERN.fullmatch(region_id):
            errors.append(f"{label}.id must be a lowercase snake_case id")
        elif region_id in region_by_id:
            errors.append(f"duplicate region id {region_id!r}")

        name = str(region.get("name") or "").strip()
        description = str(region.get("description") or "").strip()
        if not name:
            errors.append(f"{label}.name must not be blank")
        if not description:
            errors.append(f"{label}.description must not be blank")

        try:
            unlock_level = int(region.get("unlock_level"))
        except (TypeError, ValueError):
            unlock_level = 0
        if not 1 <= unlock_level <= 100:
            errors.append(f"{label}.unlock_level must be between 1 and 100")

        elements = region.get("elements")
        if not isinstance(elements, list) or not elements:
            errors.append(f"{label}.elements must be a non-empty list")
            elements = []
        normalized_elements = [_canonical_element(element) for element in elements]
        if len(set(normalized_elements)) != len(normalized_elements):
            errors.append(f"{label}.elements contains duplicates")
        for element in normalized_elements:
            if element not in VALID_ELEMENTS:
                errors.append(f"{label}.elements contains unknown element {element!r}")

        raw_tier_weights = region.get("tier_weights")
        if not isinstance(raw_tier_weights, Mapping) or not raw_tier_weights:
            errors.append(f"{label}.tier_weights must be a non-empty object")
            raw_tier_weights = {}
        tier_weights: dict[int, float] = {}
        for raw_tier, raw_weight in raw_tier_weights.items():
            try:
                tier = int(raw_tier)
                weight = float(raw_weight)
            except (TypeError, ValueError):
                errors.append(f"{label}.tier_weights contains a non-numeric tier/weight")
                continue
            if not 1 <= tier <= 10:
                errors.append(f"{label}.tier_weights tier {tier} is outside 1..10")
                continue
            if not math.isfinite(weight) or weight <= 0:
                errors.append(f"{label}.tier_weights[{tier}] must be positive")
                continue
            tier_weights[tier] = weight

        normalized_region = {
            **region,
            "id": region_id,
            "name": name,
            "description": description,
            "unlock_level": unlock_level,
            "elements": normalized_elements,
            "tier_weights": tier_weights,
        }
        normalized_regions.append(normalized_region)
        if region_id:
            region_by_id[region_id] = normalized_region

    if set(region_order) != set(region_by_id):
        errors.append("rotation.region_order must contain every configured region exactly once")

    entries = normalized.get("entries")
    if not isinstance(entries, list):
        errors.append("entries must be a list")
        entries = []
    expected_entry_count = len(region_by_id) * sum(ROLE_COUNTS_PER_REGION.values())
    if len(entries) != expected_entry_count:
        errors.append(f"entries must contain exactly {expected_entry_count} curated recipes")

    normalized_entries: list[dict] = []
    seen_legacy_splice_ids: set[int] = set()
    seen_recipe_ids: set[str] = set()
    role_counts = {
        region_id: {role: 0 for role in VALID_ROLES} for region_id in region_by_id
    }
    for index, raw_entry in enumerate(entries):
        label = f"entries[{index}]"
        if not isinstance(raw_entry, Mapping):
            errors.append(f"{label} must be an object")
            continue
        entry = dict(raw_entry)
        try:
            legacy_splice_id = int(entry.get("legacy_splice_id"))
        except (TypeError, ValueError):
            legacy_splice_id = 0
        if legacy_splice_id <= 0:
            errors.append(f"{label}.legacy_splice_id must be a positive integer")
        elif legacy_splice_id in seen_legacy_splice_ids:
            errors.append(f"duplicate legacy_splice_id {legacy_splice_id}")
        seen_legacy_splice_ids.add(legacy_splice_id)

        stable_recipe_id = entry.get("recipe_id")
        if stable_recipe_id is not None:
            stable_recipe_id = str(stable_recipe_id).strip()
            if not stable_recipe_id:
                errors.append(f"{label}.recipe_id must not be blank when supplied")
            elif stable_recipe_id in seen_recipe_ids:
                errors.append(f"duplicate stable recipe_id {stable_recipe_id!r}")
            seen_recipe_ids.add(stable_recipe_id)

        expected_name = str(entry.get("expected_name") or "").strip()
        if not expected_name:
            errors.append(f"{label}.expected_name must not be blank")

        region_id = str(entry.get("region_id") or "").strip()
        if region_id not in region_by_id:
            errors.append(f"{label}.region_id references unknown region {region_id!r}")

        role = str(entry.get("role") or "").strip().casefold()
        if role not in VALID_ROLES:
            errors.append(f"{label}.role must be regular, elite, or boss")
        elif region_id in role_counts:
            role_counts[region_id][role] += 1

        try:
            tier = int(entry.get("tier"))
        except (TypeError, ValueError):
            tier = 0
        if not 1 <= tier <= 10:
            errors.append(f"{label}.tier must be between 1 and 10")
        elif region_id in region_by_id and tier not in region_by_id[region_id]["tier_weights"]:
            errors.append(f"{label}.tier {tier} is unreachable in region {region_id!r}")

        try:
            expected_generation = int(entry.get("expected_generation"))
        except (TypeError, ValueError):
            expected_generation = -1
        if expected_generation < 0:
            errors.append(f"{label}.expected_generation must be zero or greater")
        if role == "regular" and expected_generation != 0:
            errors.append(f"{label}: regular entries must be generation 0")
        if role == "elite" and expected_generation not in {1, 2, 3}:
            errors.append(f"{label}: elite entries must be generation 1, 2, or 3")

        egg_eligible = entry.get("egg_eligible")
        if not isinstance(egg_eligible, bool):
            errors.append(f"{label}.egg_eligible must be true or false")
            egg_eligible = False
        if egg_eligible and (role != "regular" or expected_generation != 0):
            errors.append(f"{label}: only regular generation-0 entries may drop eggs")

        try:
            weight = float(entry.get("weight"))
        except (TypeError, ValueError):
            weight = 0.0
        if not math.isfinite(weight) or weight <= 0:
            errors.append(f"{label}.weight must be positive")

        if role == "boss" and "[FINAL]" not in expected_name.upper():
            errors.append(f"{label}: boss expected_name must include [FINAL]")

        normalized_entries.append(
            {
                **entry,
                "legacy_splice_id": legacy_splice_id,
                **(
                    {"recipe_id": stable_recipe_id}
                    if stable_recipe_id is not None
                    else {}
                ),
                "expected_name": expected_name,
                "region_id": region_id,
                "role": role,
                "tier": tier,
                "expected_generation": expected_generation,
                "egg_eligible": bool(egg_eligible),
                "weight": weight,
            }
        )

    for region_id, counts in role_counts.items():
        for role, expected_count in ROLE_COUNTS_PER_REGION.items():
            if counts[role] != expected_count:
                errors.append(
                    f"region {region_id!r} must have {expected_count} {role} entries "
                    f"(found {counts[role]})"
                )

    if errors:
        raise FrontierConfigError(errors)

    normalized["rotation"] = {
        **dict(rotation),
        "anchor_monday_utc": anchor.isoformat().replace("+00:00", "Z"),
        "region_order": region_order,
    }
    normalized["regions"] = normalized_regions
    normalized["entries"] = normalized_entries
    return normalized


def load_frontier_config(path: str | Path = DEFAULT_ROSTER_PATH) -> dict:
    """Read and strictly validate the checked-in Frontier roster."""

    roster_path = Path(path)
    try:
        payload = json.loads(roster_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise FrontierConfigError((f"could not load {roster_path}: {exc}",)) from exc
    return validate_frontier_config(payload)


def get_rotation_state(
    config: Mapping,
    when: dt.datetime | None = None,
) -> FrontierRotationState:
    """Return the deterministic four-week rotation state for ``when``."""

    anchor = _parse_utc_anchor(config["rotation"]["anchor_monday_utc"])
    region_order = tuple(config["rotation"]["region_order"])
    if not region_order:
        raise FrontierConfigError(("rotation.region_order must not be empty",))

    current = when or dt.datetime.now(dt.timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=dt.timezone.utc)
    current = current.astimezone(dt.timezone.utc)

    absolute_week = math.floor((current - anchor) / ROTATION_WEEK)
    cycle_week = absolute_week % len(region_order)
    starts_at = anchor + (ROTATION_WEEK * absolute_week)
    return FrontierRotationState(
        absolute_week=absolute_week,
        cycle_week=cycle_week,
        cycle_number=math.floor(absolute_week / len(region_order)),
        region_id=region_order[cycle_week],
        starts_at=starts_at,
        ends_at=starts_at + ROTATION_WEEK,
    )


def get_region(config: Mapping, region_id: str) -> dict:
    """Return a defensive copy of one configured region."""

    normalized_id = str(region_id or "").strip().casefold()
    for region in config.get("regions", ()):  # type: ignore[union-attr]
        if str(region.get("id", "")).casefold() == normalized_id:
            return copy.deepcopy(dict(region))
    raise KeyError(f"Unknown Frontier region: {region_id}")


def build_frontier_locations(
    config: Mapping,
    when: dt.datetime | None = None,
) -> tuple[dict, ...]:
    """Build location records compatible with ``Battles.PVE_LOCATIONS``."""

    state = get_rotation_state(config, when)
    locations = []
    for region in config.get("regions", ()):  # type: ignore[union-attr]
        location = copy.deepcopy(dict(region))
        location["god_chance"] = 0
        location["tier_weights"] = {
            int(tier): float(weight)
            for tier, weight in location.get("tier_weights", {}).items()
        }
        location["frontier_region_id"] = location["id"]
        location["frontier_active"] = location["id"] == state.region_id
        location["frontier_rotation_week"] = state.absolute_week
        location["location_type"] = "soulforge_frontier"
        locations.append(location)
    return tuple(locations)


def _row_value(row, key, default=None):
    try:
        value = row[key]
    except (KeyError, TypeError, IndexError):
        return default
    return default if value is None else value


def _clean_name(value) -> str:
    return str(value or "").strip()


def resolve_recipe_generations(
    base_monster_names: Iterable[str],
    splice_rows: Iterable[Mapping],
) -> dict[int, int]:
    """Resolve each recipe generation using the existing Soulforge convention.

    Base species are generation -1 and a recipe is one generation above its
    highest-generation parent.  Exact stored names are retained so this function
    also exposes disconnected legacy data rather than silently joining it.
    """

    rows = tuple(splice_rows)
    generation_by_name = {
        cleaned: -1
        for name in base_monster_names
        if (cleaned := _clean_name(name))
    }

    for _ in range(max(1, len(rows) + 1)):
        changed = False
        for row in rows:
            parent1 = _clean_name(_row_value(row, "pet1_default"))
            parent2 = _clean_name(_row_value(row, "pet2_default"))
            result = _clean_name(_row_value(row, "result_name"))
            if not parent1 or not parent2 or not result:
                continue
            if parent1 not in generation_by_name or parent2 not in generation_by_name:
                continue
            child_generation = max(
                generation_by_name[parent1], generation_by_name[parent2]
            ) + 1
            existing = generation_by_name.get(result)
            if existing == -1:
                continue
            if existing is None or child_generation < existing:
                generation_by_name[result] = child_generation
                changed = True
        if not changed:
            break

    generation_by_recipe: dict[int, int] = {}
    for row in rows:
        try:
            recipe_id = int(_row_value(row, "id"))
        except (TypeError, ValueError):
            continue
        parent1 = _clean_name(_row_value(row, "pet1_default"))
        parent2 = _clean_name(_row_value(row, "pet2_default"))
        if parent1 in generation_by_name and parent2 in generation_by_name:
            generation_by_recipe[recipe_id] = max(
                generation_by_name[parent1], generation_by_name[parent2]
            ) + 1
    return generation_by_recipe


def _positive_int(value) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _tier_baseline(public_pool: Mapping[int, Sequence[Mapping]], tier: int) -> dict[str, int]:
    rows = public_pool.get(int(tier), ()) or public_pool.get(str(int(tier)), ())
    medians: dict[str, int] = {}
    for stat in ("hp", "attack", "defense"):
        values = [
            parsed
            for row in rows
            if (parsed := _positive_int(_row_value(row, stat))) is not None
        ]
        if values:
            medians[stat] = max(1, int(statistics.median(values)))
        else:
            medians[stat] = FALLBACK_TIER_STATS[int(tier)][stat]
    return medians


def normalize_frontier_stats(
    raw_monster: Mapping,
    tier: int,
    role: str,
    public_pool: Mapping[int, Sequence[Mapping]],
) -> dict[str, int]:
    """Normalize arbitrary stored splice stats into a bounded tier/role profile."""

    normalized_role = str(role).casefold()
    if normalized_role not in ROLE_STAT_MULTIPLIERS:
        raise ValueError(f"Unknown Frontier role: {role}")
    normalized_tier = int(tier)
    if normalized_tier not in FALLBACK_TIER_STATS:
        raise ValueError("Frontier tier must be between 1 and 10")

    baseline = _tier_baseline(public_pool, normalized_tier)
    raw = {
        stat: _positive_int(_row_value(raw_monster, stat))
        for stat in ("hp", "attack", "defense")
    }
    if any(value is None for value in raw.values()):
        profiled = {stat: Decimal(value) for stat, value in baseline.items()}
    else:
        raw_total = sum(int(value) for value in raw.values() if value is not None)
        baseline_total = sum(baseline.values())
        scale = Decimal(baseline_total) / Decimal(raw_total)
        profiled = {}
        for stat, baseline_value in baseline.items():
            scaled = Decimal(int(raw[stat])) * scale  # type: ignore[arg-type]
            lower = Decimal(baseline_value) * Decimal("0.75")
            upper = Decimal(baseline_value) * Decimal("1.25")
            profiled[stat] = min(upper, max(lower, scaled))

    multipliers = ROLE_STAT_MULTIPLIERS[normalized_role]
    return {
        stat: max(
            1,
            int(
                (profiled[stat] * multipliers[stat]).to_integral_value(
                    rounding=ROUND_HALF_UP
                )
            ),
        )
        for stat in ("hp", "attack", "defense")
    }


def _stability_from_name(name: str) -> str:
    upper_name = name.upper()
    for marker, stability in (
        ("[FINAL]", "final"),
        ("[DESTABILISED]", "destabilised"),
        ("[UNSTABLE]", "unstable"),
        ("[SPECIAL]", "special"),
    ):
        if marker in upper_name:
            return stability
    return "stable"


def _curated_monster(
    row: Mapping,
    entry: Mapping,
    public_pool: Mapping[int, Sequence[Mapping]],
    state: FrontierRotationState,
) -> dict:
    name = _clean_name(_row_value(row, "result_name"))
    tier = int(entry["tier"])
    role = str(entry["role"])
    stats = normalize_frontier_stats(row, tier, role, public_pool)
    stable_recipe_id = entry.get("recipe_id")
    if stable_recipe_id is None:
        stable_recipe_id = _row_value(row, "frontier_recipe_id")

    return {
        "name": name,
        **stats,
        "element": _canonical_element(_row_value(row, "element", "Unknown")),
        "url": str(_row_value(row, "url", "") or ""),
        "ispublic": True,
        "pve_pool": "frontier",
        "pve_tier": tier,
        "splice_source_id": int(entry["legacy_splice_id"]),
        "legacy_splice_id": int(entry["legacy_splice_id"]),
        "splice_generation": int(entry["expected_generation"]),
        "frontier_region_id": str(entry["region_id"]),
        "frontier_role": role,
        "frontier_stability": _stability_from_name(name),
        "frontier_featured": True,
        "frontier_rotation_week": state.absolute_week,
        "frontier_normalized_stats": True,
        "encounter_weight": float(entry["weight"]),
        "egg_eligible": bool(entry["egg_eligible"]),
        **(
            {"frontier_recipe_id": stable_recipe_id}
            if stable_recipe_id is not None
            else {}
        ),
    }


def _wild_pool_for_region(
    config: Mapping,
    region_id: str,
    public_pool: Mapping[int, Sequence[Mapping]],
    state: FrontierRotationState,
) -> dict[int, list[dict]]:
    region = get_region(config, region_id)
    elements = {str(element).casefold() for element in region["elements"]}
    pool: dict[int, list[dict]] = {}
    for tier in sorted(int(value) for value in region["tier_weights"]):
        rows = public_pool.get(tier, ()) or public_pool.get(str(tier), ())
        regional_rows = [
            row
            for row in rows
            if bool(_row_value(row, "ispublic", True))
            and _canonical_element(_row_value(row, "element")).casefold() in elements
            and (
                not _row_value(row, "frontier_only", False)
                or str(_row_value(row, "frontier_region_id") or "") == region_id
            )
        ]
        pool[tier] = []
        for row in regional_rows:
            monster = copy.deepcopy(dict(row))
            monster.update(
                {
                    "pve_pool": "frontier_wild",
                    "pve_tier": tier,
                    "frontier_region_id": region_id,
                    "frontier_role": "wild",
                    "frontier_featured": False,
                    "frontier_rotation_week": state.absolute_week,
                    "encounter_weight": 1.0,
                    "egg_eligible": True,
                }
            )
            pool[tier].append(monster)
    return pool


def validate_public_pool_coverage(
    config: Mapping,
    public_pool: Mapping[int, Sequence[Mapping]],
) -> tuple[str, ...]:
    """Report region/tier combinations that lack a matching permanent wild."""

    errors = []
    state = get_rotation_state(config)
    for region in config.get("regions", ()):  # type: ignore[union-attr]
        regional_pool = _wild_pool_for_region(config, region["id"], public_pool, state)
        for tier, rows in regional_pool.items():
            if not rows:
                errors.append(
                    f"region {region['id']!r} has no public {region['elements']} wild at tier {tier}"
                )
    return tuple(errors)


def _rows_by_legacy_splice_id(splice_rows: Iterable[Mapping]) -> dict[int, Mapping]:
    indexed: dict[int, Mapping] = {}
    for row in splice_rows:
        try:
            recipe_id = int(_row_value(row, "id"))
        except (TypeError, ValueError):
            continue
        indexed[recipe_id] = row
    return indexed


def _resolve_entry(
    entry: Mapping,
    rows_by_id: Mapping[int, Mapping],
    generation_by_recipe_id: Mapping[int, int] | None,
    public_pool: Mapping[int, Sequence[Mapping]],
    state: FrontierRotationState,
) -> tuple[dict | None, str | None]:
    legacy_splice_id = int(entry["legacy_splice_id"])
    row = rows_by_id.get(legacy_splice_id)
    if row is None:
        return None, "missing"
    actual_name = _clean_name(_row_value(row, "result_name"))
    if actual_name.casefold() != str(entry["expected_name"]).casefold():
        return None, "name"
    if generation_by_recipe_id is not None:
        actual_generation = generation_by_recipe_id.get(legacy_splice_id)
        if actual_generation != int(entry["expected_generation"]):
            return None, "generation"
    return _curated_monster(row, entry, public_pool, state), None


def build_frontier_pool(
    config: Mapping,
    region_id: str,
    public_pool: Mapping[int, Sequence[Mapping]],
    splice_rows: Iterable[Mapping],
    *,
    when: dt.datetime | None = None,
    generation_by_recipe_id: Mapping[int, int] | None = None,
    require_active: bool = True,
) -> FrontierPoolBuild:
    """Build one region's permanent wild + active regular/elite encounter pool.

    Bosses are intentionally never returned here.  Use
    :func:`build_frontier_boss_encounter` only after gameplay has verified the
    player's weekly boss unlock.
    """

    region = get_region(config, region_id)
    state = get_rotation_state(config, when)
    is_featured = state.region_id == region["id"]
    pool = _wild_pool_for_region(config, region["id"], public_pool, state)
    if require_active and not is_featured:
        return FrontierPoolBuild(
            pool=pool,
            rotation=state,
            region_id=region["id"],
            is_featured=False,
        )

    rows_by_id = _rows_by_legacy_splice_id(splice_rows)
    included: list[int] = []
    missing: list[int] = []
    name_mismatches: list[int] = []
    generation_mismatches: list[int] = []
    entries = [
        entry
        for entry in config.get("entries", ())  # type: ignore[union-attr]
        if entry["region_id"] == region["id"] and entry["role"] in {"regular", "elite"}
    ]
    for entry in entries:
        legacy_splice_id = int(entry["legacy_splice_id"])
        monster, error = _resolve_entry(
            entry,
            rows_by_id,
            generation_by_recipe_id,
            public_pool,
            state,
        )
        if error == "missing":
            missing.append(legacy_splice_id)
        elif error == "name":
            name_mismatches.append(legacy_splice_id)
        elif error == "generation":
            generation_mismatches.append(legacy_splice_id)
        elif monster is not None:
            pool.setdefault(int(entry["tier"]), []).append(monster)
            included.append(legacy_splice_id)

    return FrontierPoolBuild(
        pool=pool,
        rotation=state,
        region_id=region["id"],
        is_featured=is_featured,
        included_legacy_splice_ids=tuple(included),
        missing_legacy_splice_ids=tuple(missing),
        name_mismatches=tuple(name_mismatches),
        generation_mismatches=tuple(generation_mismatches),
    )


def build_frontier_boss_encounter(
    config: Mapping,
    region_id: str,
    public_pool: Mapping[int, Sequence[Mapping]],
    splice_rows: Iterable[Mapping],
    *,
    when: dt.datetime | None = None,
    generation_by_recipe_id: Mapping[int, int] | None = None,
    require_active: bool = True,
) -> dict | None:
    """Resolve the region's single curated boss for an already-authorized fight."""

    region = get_region(config, region_id)
    state = get_rotation_state(config, when)
    if require_active and state.region_id != region["id"]:
        return None
    entries = [
        entry
        for entry in config.get("entries", ())  # type: ignore[union-attr]
        if entry["region_id"] == region["id"] and entry["role"] == "boss"
    ]
    if len(entries) != 1:
        return None
    monster, error = _resolve_entry(
        entries[0],
        _rows_by_legacy_splice_id(splice_rows),
        generation_by_recipe_id,
        public_pool,
        state,
    )
    return monster if error is None else None


def choose_weighted_monster(
    candidates: Sequence[Mapping],
    *,
    rng: random.Random | None = None,
) -> dict:
    """Choose one candidate using its positive ``encounter_weight`` metadata."""

    if not candidates:
        raise ValueError("Cannot choose from an empty Frontier monster pool")
    weights = []
    for candidate in candidates:
        try:
            weight = float(candidate.get("encounter_weight", 1.0))
        except (TypeError, ValueError):
            weight = 1.0
        weights.append(weight if math.isfinite(weight) and weight > 0 else 1.0)
    chooser = rng or random
    return copy.deepcopy(chooser.choices(list(candidates), weights=weights, k=1)[0])

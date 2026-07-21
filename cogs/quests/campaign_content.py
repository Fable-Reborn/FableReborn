"""Portable campaign package validation and conversion helpers."""

from __future__ import annotations

import copy
import re
from collections.abc import Mapping
from datetime import datetime, timezone


SCHEMA_NAME = "fablereborn.campaign-package"
SCHEMA_VERSION = 1

NODE_TYPES = {"quest", "choice", "ending"}
OBJECTIVE_SOURCES = {
    "none",
    "pve",
    "adventure",
    "battletower",
    "dragonparty",
    "cbt",
    "raidbattle",
    "jurytower",
    "scripted",
    "frontier_boss",
    "divine_victory",
    "omnithrone_phase",
    "omnithrone_completion",
}
OBJECTIVE_MODES = {"progress", "key_item"}
REWARD_TYPES = {"none", "money", "crate", "item", "egg", "bundle"}
TURNIN_TYPES = {"progress", "key_item", "crate", "egg", "money"}
CONDITION_TYPES = {
    "quest_completed",
    "campaign_completed",
    "campaign_choice",
    "reputation",
    "level",
    "class",
    "god",
    "race",
    "money",
    "guild_member",
    "item_owned",
    "item_equipped",
    "pet_owned",
    "pet_equipped",
    "badge",
    "unlock",
    "system_unlock",
    "god_pet_lock",
    "ascension_mantle",
    "frontier_boss_regions",
}
ENCOUNTER_KINDS = {
    "none",
    "pve",
    "battle_tower",
    "dragon_party",
    "raid_battle",
    "jury_tower",
    "external_command",
}

ENDGAME_EVENT_TYPES = {
    "frontier_boss_clear",
    "divine_victory",
    "omnithrone_phase",
    "omnithrone_completion",
}
DIVINE_GODS = ("Elysia", "Sepulchure", "Drakath")


class CampaignPackageError(ValueError):
    """Raised when a campaign package cannot be safely imported."""

    def __init__(self, errors: list[str]):
        super().__init__("\n".join(errors))
        self.errors = errors


def normalize_key(value: object) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "_", str(value or "").strip().lower())
    return cleaned.strip("_")


def normalize_system_unlock_key(value: object) -> str:
    """Return the canonical storage form for durable, cross-system unlocks."""
    return normalize_key(value)


def _required_event_text(payload: Mapping, key: str) -> str:
    value = str(payload.get(key) or "").strip()
    if not value:
        raise ValueError(f"Endgame event payload needs `{key}`.")
    return value


def _positive_event_int(payload: Mapping, key: str, default: int = 1) -> int:
    raw = payload.get(key, default)
    try:
        return max(1, int(raw))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Endgame event payload `{key}` must be a positive number.") from exc


def normalize_endgame_event(event_type: object, payload: object) -> dict:
    """Validate an endgame dispatch and derive its quest/unlock projection.

    The returned ``event_id`` is stable and is used to make quest progress
    idempotent. Callers should dispatch only after the underlying battle or
    phase transaction has committed.
    """
    event_key = normalize_key(event_type)
    if event_key not in ENDGAME_EVENT_TYPES:
        raise ValueError(f"Unsupported endgame event `{event_key or event_type}`.")
    if not isinstance(payload, Mapping):
        raise ValueError("Endgame event payload must be an object.")

    party_size = _positive_event_int(payload, "party_size", 1)
    if event_key == "frontier_boss_clear":
        battle_id = _required_event_text(payload, "battle_id")
        region_id = normalize_key(_required_event_text(payload, "region_id"))
        boss_name = _required_event_text(payload, "boss_name")
        absolute_week = payload.get("absolute_week")
        return {
            "event_type": event_key,
            "source": "frontier_boss",
            "candidate_names": (boss_name, region_id, "frontier_boss"),
            "metadata": {
                "event_id": f"frontier_boss:{battle_id}",
                "battle_id": battle_id,
                "region_id": region_id,
                "target_key": region_id,
                "absolute_week": absolute_week,
                "party_size": party_size,
            },
            "unlock_keys": (f"frontier_boss_{region_id}",),
        }

    if event_key == "divine_victory":
        battle_id = _required_event_text(payload, "battle_id")
        requested_god = _required_event_text(payload, "god_name")
        god_name = next(
            (name for name in DIVINE_GODS if name.casefold() == requested_god.casefold()),
            None,
        )
        if god_name is None:
            raise ValueError("Divine victory must name Elysia, Sepulchure, or Drakath.")
        tier = _positive_event_int(payload, "tier", 11)
        if tier != 11:
            raise ValueError("Divine victory events only accept Tier 11 encounters.")
        god_key = normalize_key(god_name)
        return {
            "event_type": event_key,
            "source": "divine_victory",
            "candidate_names": (god_name, god_key, "tier_11"),
            "metadata": {
                "event_id": f"divine_victory:{battle_id}",
                "battle_id": battle_id,
                "god_name": god_name,
                "target_key": god_key,
                "tier": 11,
                "party_size": party_size,
            },
            "unlock_keys": (f"divine_victory_{god_key}",),
        }

    attempt_id = _required_event_text(payload, "attempt_id")
    if event_key == "omnithrone_phase":
        phase_key = normalize_key(_required_event_text(payload, "phase_key"))
        phase_number = _positive_event_int(payload, "phase_number")
        return {
            "event_type": event_key,
            "source": "omnithrone_phase",
            "candidate_names": (phase_key, f"phase_{phase_number}", "omnithrone"),
            "metadata": {
                "event_id": f"omnithrone:{attempt_id}:phase:{phase_key}",
                "attempt_id": attempt_id,
                "phase_key": phase_key,
                "phase_number": phase_number,
                "target_key": phase_key,
                "party_size": party_size,
            },
            "unlock_keys": (f"omnithrone_phase_{phase_key}",),
        }

    outcome = normalize_key(_required_event_text(payload, "outcome"))
    if outcome != "sealed":
        raise ValueError("Omnithrone completion must record the `sealed` outcome.")
    return {
        "event_type": event_key,
        "source": "omnithrone_completion",
        "candidate_names": ("sealed", "complete", "omnithrone"),
        "metadata": {
            "event_id": f"omnithrone:{attempt_id}:completion",
            "attempt_id": attempt_id,
            "outcome": "sealed",
            "target_key": "sealed",
            "party_size": party_size,
        },
        "unlock_keys": ("omnithrone_sealed",),
    }


def validate_builtin_package(raw: object) -> dict:
    """Validate a bundled package using the monotonic version contract.

    Bundled JSON must include a stable ``package_key`` and a positive integer
    ``content_version``. A running bot installs a package once, skips the same
    or an older version, and installs a higher version as an explicit content
    migration. This lets GMs edit installed content safely between releases.
    """
    package = validate_package(raw)
    errors: list[str] = []
    package_key = normalize_key(package.get("package_key"))
    if not package_key:
        errors.append("Bundled campaign packages need a stable `package_key`.")
    try:
        content_version = int(package.get("content_version"))
    except (TypeError, ValueError):
        content_version = 0
    if content_version < 1:
        errors.append("Bundled campaign packages need `content_version` >= 1.")
    if errors:
        raise CampaignPackageError(errors)
    package["package_key"] = package_key
    package["content_version"] = content_version
    return package


def builtin_install_decision(
    installed_version: int | None,
    bundled_version: int,
    *,
    has_unmanaged_conflicts: bool = False,
) -> str:
    """Return ``install``, ``upgrade``, ``skip``, or ``conflict``."""
    bundled_version = int(bundled_version)
    if installed_version is None:
        return "conflict" if has_unmanaged_conflicts else "install"
    return "upgrade" if bundled_version > int(installed_version) else "skip"


def _as_dict(value: object) -> dict:
    return copy.deepcopy(value) if isinstance(value, dict) else {}


def _as_list(value: object) -> list:
    return copy.deepcopy(value) if isinstance(value, list) else []


def _positive_int(value: object, default: int = 1) -> int:
    try:
        return max(1, int(value))
    except (TypeError, ValueError):
        return default


def new_package() -> dict:
    return {
        "schema": SCHEMA_NAME,
        "schema_version": SCHEMA_VERSION,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "campaigns": [],
        "standalone_quests": [],
        "cutscenes": [],
        "monsters": [],
        "reference": build_reference_catalog([]),
    }


def build_reference_catalog(monsters: list[dict]) -> dict:
    monster_names = sorted(
        {
            str(monster.get("name") or "").strip()
            for monster in monsters
            if isinstance(monster, dict) and str(monster.get("name") or "").strip()
        },
        key=str.casefold,
    )
    return {
        "node_types": sorted(NODE_TYPES),
        "objective_sources": sorted(OBJECTIVE_SOURCES),
        "objective_modes": sorted(OBJECTIVE_MODES),
        "turnin_types": sorted(TURNIN_TYPES),
        "reward_types": sorted(REWARD_TYPES),
        "condition_types": sorted(CONDITION_TYPES),
        "encounter_kinds": sorted(ENCOUNTER_KINDS),
        "monster_names": monster_names,
        "notes": {
            "launch_command": (
                "Discord command shown to players for an encounter. Existing battle "
                "commands enforce their own lobby and party rules."
            ),
            "battle_settings": (
                "Stored with the campaign now and reserved for a generic campaign "
                "battle runner."
            ),
            "builtin_versioning": (
                "Files in cogs/quests/data/builtin_campaigns need package_key and "
                "content_version >= 1. Equal or older versions are skipped; only a "
                "higher content_version replaces an installed package."
            ),
            "distinct_objectives": (
                "Set objective.distinct_targets=true to count each event target once."
            ),
        },
    }


def normalize_package(raw: object) -> dict:
    if not isinstance(raw, dict):
        raise CampaignPackageError(["The uploaded JSON must contain one object."])

    package = copy.deepcopy(raw)
    package.setdefault("schema", SCHEMA_NAME)
    package.setdefault("schema_version", SCHEMA_VERSION)
    package["campaigns"] = _as_list(package.get("campaigns"))
    package["standalone_quests"] = _as_list(package.get("standalone_quests"))
    package["cutscenes"] = _as_list(package.get("cutscenes"))
    package["monsters"] = _as_list(package.get("monsters"))
    package["reference"] = _as_dict(package.get("reference"))
    package.setdefault("exported_at", datetime.now(timezone.utc).isoformat())

    for campaign in package["campaigns"]:
        if not isinstance(campaign, dict):
            continue
        campaign["key"] = normalize_key(campaign.get("key"))
        campaign["title"] = str(campaign.get("title") or campaign["key"].replace("_", " ").title())
        campaign["description"] = str(campaign.get("description") or "")
        campaign["start_node"] = normalize_key(campaign.get("start_node"))
        campaign["is_active"] = bool(campaign.get("is_active", False))
        campaign["nodes"] = _as_list(campaign.get("nodes"))
        campaign["requirements"] = _normalize_conditions(campaign.get("requirements"))

        for node in campaign["nodes"]:
            if not isinstance(node, dict):
                continue
            node["id"] = normalize_key(node.get("id"))
            node["type"] = str(node.get("type") or "quest").strip().lower()
            node["title"] = str(node.get("title") or node["id"].replace("_", " ").title())
            node["description"] = str(node.get("description") or "")
            node["next"] = _normalize_edges(node.get("next"))
            node["options"] = _normalize_edges(node.get("options"))
            node["quest"] = _as_dict(node.get("quest"))
            node["cutscenes"] = _as_dict(node.get("cutscenes"))
            node["encounter"] = _as_dict(node.get("encounter"))
            node["unlocks"] = _as_list(node.get("unlocks"))
            node["requirements"] = _normalize_conditions(node.get("requirements"))
            node["quest"]["requirements"] = _normalize_conditions(
                node["quest"].get("requirements")
            )

    for monster in package["monsters"]:
        if not isinstance(monster, dict):
            continue
        monster["key"] = normalize_key(monster.get("key") or monster.get("name"))
        monster["name"] = str(monster.get("name") or "").strip()
        monster["tier"] = _positive_int(monster.get("tier"), 1)
        monster["hp"] = _positive_int(monster.get("hp"), 100)
        monster["attack"] = _positive_int(monster.get("attack"), 10)
        monster["defense"] = max(0, int(monster.get("defense") or 0))
        monster["element"] = str(monster.get("element") or "Nature").strip()
        monster["url"] = str(monster.get("url") or "").strip()
        monster["tags"] = [str(tag).strip() for tag in _as_list(monster.get("tags")) if str(tag).strip()]

    return package


def _normalize_edges(raw: object) -> list[dict]:
    if isinstance(raw, str):
        raw = [{"target": raw}]
    edges = []
    for edge in _as_list(raw):
        if isinstance(edge, str):
            edge = {"target": edge}
        if not isinstance(edge, dict):
            continue
        target = normalize_key(edge.get("target"))
        edges.append(
            {
                "label": str(edge.get("label") or "Continue").strip(),
                "target": target,
                "description": str(edge.get("description") or "").strip(),
                "effects": _as_list(edge.get("effects")),
                "unlocks": _as_list(edge.get("unlocks")),
                "conditions": _normalize_conditions(edge.get("conditions")),
            }
        )
    return edges


def _normalize_conditions(raw: object) -> list[dict]:
    conditions = []
    for condition in _as_list(raw):
        if not isinstance(condition, dict):
            continue
        conditions.append(
            {
                "type": str(condition.get("type") or "").strip().lower(),
                "key": str(condition.get("key") or "").strip(),
                "operator": str(condition.get("operator") or ">=").strip(),
                "value": condition.get("value", 1),
                "equipped": bool(condition.get("equipped", False)),
                "field": str(condition.get("field") or "").strip().lower(),
                "description": str(condition.get("description") or "").strip(),
            }
        )
    return conditions


def validate_package(raw: object) -> dict:
    package = normalize_package(raw)
    errors: list[str] = []

    if package.get("schema") != SCHEMA_NAME:
        errors.append(f"schema must be `{SCHEMA_NAME}`.")
    if package.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION}.")

    campaign_keys: set[str] = set()
    quest_keys: set[str] = set()
    for campaign_index, campaign in enumerate(package["campaigns"], start=1):
        prefix = f"campaigns[{campaign_index}]"
        if not isinstance(campaign, dict):
            errors.append(f"{prefix} must be an object.")
            continue
        campaign_key = campaign.get("key")
        if not campaign_key:
            errors.append(f"{prefix}.key is required.")
        elif campaign_key in campaign_keys:
            errors.append(f"Duplicate campaign key `{campaign_key}`.")
        campaign_keys.add(campaign_key)

        nodes = campaign.get("nodes") or []
        if not nodes:
            errors.append(f"Campaign `{campaign_key or campaign_index}` needs at least one node.")
            continue
        node_ids = [node.get("id") for node in nodes if isinstance(node, dict)]
        known_nodes = set(node_ids)
        _validate_conditions(
            campaign.get("requirements"),
            f"Campaign `{campaign_key}`",
            errors,
        )
        if not campaign.get("start_node"):
            errors.append(f"Campaign `{campaign_key}` needs a start_node.")
        elif campaign["start_node"] not in known_nodes:
            errors.append(
                f"Campaign `{campaign_key}` start_node `{campaign['start_node']}` does not exist."
            )

        seen_nodes: set[str] = set()
        for node_index, node in enumerate(nodes, start=1):
            node_prefix = f"campaign `{campaign_key}` node {node_index}"
            if not isinstance(node, dict):
                errors.append(f"{node_prefix} must be an object.")
                continue
            node_id = node.get("id")
            if not node_id:
                errors.append(f"{node_prefix} needs an id.")
            elif node_id in seen_nodes:
                errors.append(f"Campaign `{campaign_key}` has duplicate node `{node_id}`.")
            seen_nodes.add(node_id)

            node_type = node.get("type")
            if node_type not in NODE_TYPES:
                errors.append(f"Node `{node_id}` has unsupported type `{node_type}`.")

            edges = node.get("options") if node_type == "choice" else node.get("next")
            if node_type == "choice" and len(edges or []) < 2:
                errors.append(f"Choice node `{node_id}` needs at least two options.")
            for edge in edges or []:
                if not edge.get("target"):
                    errors.append(f"Node `{node_id}` has a transition without a target.")
                elif edge["target"] not in known_nodes:
                    errors.append(
                        f"Node `{node_id}` points to missing node `{edge['target']}`."
                    )
                _validate_conditions(
                    edge.get("conditions"),
                    f"Node `{node_id}` transition to `{edge.get('target')}`",
                    errors,
                )

            _validate_conditions(node.get("requirements"), f"Node `{node_id}`", errors)

            if node_type == "quest":
                _validate_quest_node(campaign_key, node, quest_keys, errors)

    monster_keys: set[str] = set()
    monster_names: set[str] = set()
    for monster in package["monsters"]:
        if not isinstance(monster, dict):
            errors.append("Every monster entry must be an object.")
            continue
        if not monster.get("key") or not monster.get("name"):
            errors.append("Every monster needs a key and name.")
            continue
        if monster["key"] in monster_keys:
            errors.append(f"Duplicate monster key `{monster['key']}`.")
        if monster["name"].casefold() in monster_names:
            errors.append(f"Duplicate monster name `{monster['name']}`.")
        monster_keys.add(monster["key"])
        monster_names.add(monster["name"].casefold())

    if errors:
        raise CampaignPackageError(errors)

    package["reference"] = build_reference_catalog(package["monsters"])
    return package


def _validate_quest_node(
    campaign_key: str,
    node: dict,
    quest_keys: set[str],
    errors: list[str],
) -> None:
    node_id = node.get("id")
    quest = node.get("quest") or {}
    quest_key = normalize_key(quest.get("quest_key") or f"{campaign_key}_{node_id}")
    quest["quest_key"] = quest_key
    if quest_key in quest_keys:
        errors.append(f"Duplicate generated quest key `{quest_key}`.")
    quest_keys.add(quest_key)

    objective = _as_dict(quest.get("objective"))
    source = str(objective.get("source") or "none").lower()
    mode = str(objective.get("mode") or "progress").lower()
    if source not in OBJECTIVE_SOURCES:
        errors.append(f"Quest `{quest_key}` has unsupported source `{source}`.")
    if mode not in OBJECTIVE_MODES:
        errors.append(f"Quest `{quest_key}` has unsupported objective mode `{mode}`.")

    turnin_type = str((_as_dict(quest.get("turnin"))).get("type") or "progress").lower()
    reward_type = str((_as_dict(quest.get("reward"))).get("type") or "none").lower()
    if turnin_type not in TURNIN_TYPES:
        errors.append(f"Quest `{quest_key}` has unsupported turn-in type `{turnin_type}`.")
    if reward_type not in REWARD_TYPES:
        errors.append(f"Quest `{quest_key}` has unsupported reward type `{reward_type}`.")
    _validate_conditions(
        quest.get("requirements"),
        f"Quest `{quest_key}`",
        errors,
    )
    if reward_type == "bundle":
        rewards = _as_list((_as_dict(quest.get("reward"))).get("rewards"))
        if not rewards:
            errors.append(f"Quest `{quest_key}` reward bundle is empty.")
        for bundled_reward in rewards:
            bundled_type = str((_as_dict(bundled_reward)).get("type") or "none").lower()
            if bundled_type not in REWARD_TYPES - {"bundle"}:
                errors.append(
                    f"Quest `{quest_key}` has unsupported bundled reward `{bundled_type}`."
                )

    encounter = node.get("encounter") or {}
    if encounter:
        kind = str(encounter.get("kind") or "none").lower()
        if kind not in ENCOUNTER_KINDS:
            errors.append(f"Quest `{quest_key}` has unsupported encounter kind `{kind}`.")
        party = _as_dict(encounter.get("party"))
        minimum = _positive_int(party.get("min"), 1)
        maximum = _positive_int(party.get("max"), minimum)
        if minimum > maximum:
            errors.append(f"Quest `{quest_key}` party minimum cannot exceed its maximum.")


def _validate_conditions(raw: object, owner: str, errors: list[str]) -> None:
    for condition in _as_list(raw):
        if not isinstance(condition, dict):
            errors.append(f"{owner} contains a condition that is not an object.")
            continue
        condition_type = str(condition.get("type") or "").lower()
        if condition_type not in CONDITION_TYPES:
            errors.append(f"{owner} has unsupported condition `{condition_type}`.")
        if condition_type not in {
            "level",
            "money",
            "guild_member",
            "frontier_boss_regions",
        } and not str(
            condition.get("key") or ""
        ).strip():
            errors.append(f"{owner} condition `{condition_type}` needs a key.")


def quest_record_from_node(campaign: dict, node: dict) -> dict:
    """Convert a validated quest node to the existing custom_quests shape."""
    quest = _as_dict(node.get("quest"))
    quest_key = normalize_key(quest.get("quest_key") or f"{campaign['key']}_{node['id']}")
    objective = _as_dict(quest.get("objective"))
    objective.setdefault("source", "none")
    objective.setdefault("mode", "progress")
    objective.setdefault("required_count", 0)
    objective.setdefault("target_name", "")

    turnin = _as_dict(quest.get("turnin"))
    turnin.setdefault("type", "progress")
    reward = _as_dict(quest.get("reward"))
    reward.setdefault("type", "none")
    access = _as_dict(quest.get("access"))
    access.update(
        {
            "campaign_key": campaign["key"],
            "campaign_node_key": node["id"],
            "conditions": _as_list(node.get("requirements"))
            + _as_list(quest.get("requirements")),
        }
    )

    return {
        "quest_key": quest_key,
        "name": str(quest.get("name") or node.get("title") or quest_key),
        "category": str(quest.get("category") or campaign.get("title") or "Campaign"),
        "short_description": str(quest.get("short_description") or node.get("description") or ""),
        "offer_text": str(quest.get("offer_text") or node.get("description") or ""),
        "turnin_text": str(quest.get("turnin_text") or ""),
        "objective": objective,
        "turnin": turnin,
        "reward": reward,
        "access": access,
        "prerequisites": _as_list(quest.get("prerequisites")),
        "repeatable": bool(quest.get("repeatable", False)),
        "is_active": bool(campaign.get("is_active", False) and quest.get("is_active", True)),
    }


def node_by_id(campaign: dict, node_id: str) -> dict | None:
    normalized = normalize_key(node_id)
    for node in campaign.get("nodes") or []:
        if node.get("id") == normalized:
            return node
    return None

"""Portable, declarative node packs and personal/shared library policy.

Packs compile into ordinary encounter steps. No executable plugins, SQL, URLs or
reward mutations are dispatched from their contents. Published packs are snapshots.
"""

import copy
import json

from .engine import advanced_starter, default_node, validate_encounter
from .mechanics import safe_id, upgrade_encounter

SCHEMA = "fablereborn.raid-node"
MAX_BYTES = 250_000
MAX_PACK_NODES = 30
LIBRARY_LIMIT = 100
CATALOGUES = ("teams", "roles", "statuses", "resources", "actions")
PORTS = {"$next": "pack_success", "$failure": "pack_failure"}


def links(node):
    """Yield editable flow references (including rule-driven transitions)."""
    if node["kind"] not in {"choice", "ending"}:
        yield node, "next"
    if node["kind"] in {"battle", "choice", "trial", "check", "system"}:
        yield node, "failure"
    if node["kind"] == "choice":
        for choice in node.get("choices", []):
            yield choice, "next"
    for rule in node.get("rules", []):
        if rule.get("effect") == "transition":
            yield rule, "destination"


def _bounded_json(value):
    try:
        data = json.dumps(value, ensure_ascii=False, allow_nan=False).encode()
    except (TypeError, ValueError, RecursionError) as exc:
        raise ValueError("Node packs must contain plain JSON data.") from exc
    if len(data) > MAX_BYTES:
        raise ValueError("Node packs must be smaller than 250 KB.")


def validate_pack(package):
    """Return an independent, normalized pack after full engine validation."""
    _bounded_json(package)
    try:
        if (
            not isinstance(package, dict)
            or package.get("schema") != SCHEMA
            or package.get("version") != 1
        ):
            raise ValueError("Choose a Fable node pack (.node.json), version 1.")
        for key, minimum, maximum in (("name", 1, 100), ("description", 0, 1000)):
            value = package.get(key, "")
            if (
                not isinstance(value, str)
                or not minimum <= len(value.strip()) <= maximum
            ):
                raise ValueError(
                    f"Node pack {key} must contain {minimum}-{maximum} characters."
                )
        raw = package.get("nodes")
        if not isinstance(raw, list) or not 1 <= len(raw) <= MAX_PACK_NODES:
            raise ValueError("A node pack needs 1-30 steps.")
        nodes = []
        for item in raw:
            if not isinstance(item, dict) or not safe_id(item.get("id")):
                raise ValueError("Each node needs a valid lowercase ID.")
            node = default_node(item["id"])
            node.update(copy.deepcopy(item))
            nodes.append(node)
        keys = {n["id"] for n in nodes}
        if keys & set(PORTS.values()):
            raise ValueError("pack_success and pack_failure are reserved node IDs.")
        if package.get("entry") not in keys:
            raise ValueError("Choose the pack's entry step.")
        base = advanced_starter("evil", "pack_validation")["config"]["encounter"]
        catalogues = package.get("catalogues", {})
        if not isinstance(catalogues, dict):
            raise ValueError("Node catalogues must be an object.")
        # Minimal AI-authored packs may omit catalogues and use standard actors/actions.
        base.update({k: copy.deepcopy(catalogues.get(k, base[k])) for k in CATALOGUES})
        base["start"] = package["entry"]
        base["nodes"] = copy.deepcopy(nodes)
        for node in base["nodes"]:
            for obj, key in links(node):
                value = obj.get(key)
                if value not in keys and value not in PORTS:
                    raise ValueError(
                        f"{node['id']} must link within its pack, to $next, or to $failure."
                    )
                obj[key] = PORTS.get(value, value)
        for port, key in PORTS.items():
            ending = default_node(key, "ending")
            ending["outcome"] = "victory" if port == "$next" else "defeat"
            base["nodes"].append(ending)
        result = validate_encounter(base)
        if set(result["unreachable"]) & keys:
            raise ValueError("Every pack step must be reachable from its entry.")
        # Return only the supported envelope; owner/publishing/rewards never import.
        return {
            "schema": SCHEMA,
            "version": 1,
            "name": package["name"].strip(),
            "description": package.get("description", "").strip(),
            "entry": package["entry"],
            "nodes": nodes,
            "catalogues": {k: base[k] for k in CATALOGUES},
        }
    except (TypeError, KeyError, AttributeError, RecursionError) as exc:
        raise ValueError(
            "Malformed node settings. Use the node prompt/example and retry."
        ) from exc


def read_pack(data):
    if len(data) > MAX_BYTES:
        raise ValueError("Node packs must be smaller than 250 KB.")
    try:
        package = json.loads(data)
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise ValueError("This file is not valid node JSON.") from exc
    return validate_pack(package)


def extract_pack(spec, step_ids, name, description=""):
    spec = upgrade_encounter(spec)
    chosen = list(dict.fromkeys(step_ids))
    available = {n["id"]: n for n in spec["nodes"]}
    if not chosen or any(key not in available for key in chosen):
        raise ValueError("Choose existing step IDs; the first is the pack entry.")
    nodes = [copy.deepcopy(available[key]) for key in chosen]
    for node in nodes:
        for obj, key in links(node):
            destination = obj.get(key)
            if destination not in chosen:
                if destination not in available:
                    raise ValueError(
                        "Fix missing step links before saving this node pack."
                    )
                failed = (
                    key == "failure"
                    or available[destination].get("outcome") == "defeat"
                    and available[destination]["kind"] == "ending"
                )
                obj[key] = "$failure" if failed else "$next"
    return validate_pack(
        {
            "schema": SCHEMA,
            "version": 1,
            "name": name,
            "description": description,
            "entry": chosen[0],
            "nodes": nodes,
            "catalogues": {k: spec[k] for k in CATALOGUES},
        }
    )


def _unique(key, used):
    candidate = key[:64]
    number = 1
    while candidate in used:
        suffix = f"_{number}"
        candidate = key[: 64 - len(suffix)] + suffix
        number += 1
    used.add(candidate)
    return candidate


def insert_pack(spec, package, after=None):
    """Copy on insertion, remap IDs, connect exits, then validate atomically.

    Identical teams/roles are shared. Meters, actions, statuses and steps are
    isolated per insertion so two puzzles cannot change each other's state.
    """
    pack = validate_pack(package)
    result = upgrade_encounter(spec)
    if not result["nodes"] and not after:
        # An empty canvas has no host destinations for the pack's exit ports.
        result["nodes"] = [default_node("victory", "ending"),
                           dict(default_node("defeat", "ending"), outcome="defeat")]
        result["start"] = "victory"
    nodes = {n["id"]: n for n in result["nodes"]}
    anchor = nodes.get(after) if after else None
    if after and (anchor is None or anchor["kind"] in {"ending", "choice"}):
        raise ValueError(
            "Insert after a step with a Next output, or before the raid start."
        )
    success = anchor["next"] if anchor else result["start"]
    failure = (
        anchor.get("failure")
        if anchor and anchor["kind"] in {"battle", "trial", "check", "system"}
        else None
    )
    failure = failure or next(
        (
            n["id"]
            for n in nodes.values()
            if n["kind"] == "ending" and n["outcome"] == "defeat"
        ),
        success,
    )
    node_map = {}
    used = set(nodes)
    for node in pack["nodes"]:
        node_map[node["id"]] = _unique("custom_" + node["id"], used)
    maps = {}
    for collection in CATALOGUES:
        used = {item["id"] for item in result[collection]}
        mapping = maps[collection] = {}
        for item in pack["catalogues"][collection]:
            adjusted = copy.deepcopy(item)
            if collection == "roles":
                adjusted["team"] = maps["teams"][item["team"]]
            same = next((i for i in result[collection] if i == adjusted), None)
            mapping[item["id"]] = (
                same["id"]
                if same and collection in {"teams", "roles"}
                else _unique("custom_" + item["id"], used)
            )
    enemy_map = {}
    used = {e["id"] for n in nodes.values() for e in n.get("enemies", [])} | {"boss"}
    for node in pack["nodes"]:
        for enemy in node.get("enemies", []):
            if enemy["id"] not in enemy_map:
                # The built-in boss alias also addresses legacy single-boss steps.
                enemy_map[enemy["id"]] = (
                    "boss" if enemy["id"] == "boss"
                    else _unique("custom_" + enemy["id"], used)
                )

    def remap(obj):
        if isinstance(obj, list):
            return [remap(v) for v in obj]
        if not isinstance(obj, dict):
            return obj
        out = {k: remap(v) for k, v in obj.items()}
        for key, collection in (
            ("resource", "resources"),
            ("cost_resource", "resources"),
            ("output_resource", "resources"),
            ("status", "statuses"),
            ("on_hit_status", "statuses"),
            ("team", "teams"),
        ):
            if key in out:
                out[key] = maps[collection].get(out[key], out[key])
        if "roles" in out:
            out["roles"] = [maps["roles"].get(r, r) for r in out["roles"]]
        for key in ("target", "subject"):
            value = out.get(key)
            if not isinstance(value, str):
                continue
            if key == "subject" and value in maps["resources"]:
                out[key] = maps["resources"][value]
            elif ":" in value:
                prefix, ident = value.split(":", 1)
                mapping = {
                    "team": maps["teams"],
                    "team_alive": maps["teams"],
                    "role": maps["roles"],
                    "role_alive": maps["roles"],
                    "status_count": maps["statuses"],
                    "enemy": enemy_map,
                    "enemy_hp": enemy_map,
                }.get(prefix, {})
                out[key] = prefix + ":" + mapping.get(ident, ident)
        return out

    for collection in CATALOGUES:
        for item in pack["catalogues"][collection]:
            new_id = maps[collection][item["id"]]
            if any(i["id"] == new_id for i in result[collection]):
                continue
            item = remap(item)
            item["id"] = new_id
            result[collection].append(item)
    for index, node in enumerate(pack["nodes"]):
        node = remap(node)
        node["id"] = node_map[node["id"]]
        for enemy in node.get("enemies", []):
            enemy["id"] = enemy_map[enemy["id"]]
        for obj, key in links(node):
            obj[key] = {"$next": success, "$failure": failure, **node_map}[obj[key]]
        node["pack_name"] = pack["name"]
        result["nodes"].append(node)
        position = len(nodes) + index
        result["layout"][node["id"]] = {
            "x": 50 + position % 4 * 285,
            "y": 50 + position // 4 * 250,
        }
    entry = node_map[pack["entry"]]
    if anchor:
        anchor["next"] = entry
    else:
        result["start"] = entry
    validate_encounter(result)
    return result, entry


def save_node(registry, user_id, node_id, package):
    if not safe_id(node_id):
        raise ValueError(
            "Node IDs must start with a lowercase letter and use at most 64 letters, digits, _ or -."
        )
    library = registry.setdefault("node_library", {})
    existing = library.get(node_id)
    if existing and existing["creator_id"] != user_id:
        raise ValueError("That node ID belongs to another GM. Choose a different ID.")
    if (
        not existing
        and sum(n["creator_id"] == user_id for n in library.values()) >= LIBRARY_LIMIT
    ):
        raise ValueError(
            "Your node library has 100 packs. Delete one before saving another."
        )
    package = validate_pack(package)
    entry = (
        copy.deepcopy(existing)
        if existing
        else {
            "id": node_id,
            "creator_id": user_id,
            "revision": 0,
            "published_version": 0,
        }
    )
    entry["package"] = package
    entry["revision"] += 1
    library[node_id] = entry
    return entry


def get_node(registry, user_id, node_id, *, owned=False):
    entry = registry.get("node_library", {}).get(node_id)
    if entry is None or (
        entry["creator_id"] != user_id and (owned or not entry.get("published_package"))
    ):
        raise ValueError(
            "Node unavailable. Choose your own node or a published community node."
        )
    return entry


def visible_nodes(registry, user_id):
    result = []
    for entry in registry.get("node_library", {}).values():
        own = entry["creator_id"] == user_id
        package = entry["package"] if own else entry.get("published_package")
        if package:
            result.append(
                {
                    "id": entry["id"],
                    "creator_id": entry["creator_id"],
                    "version": entry["revision"] if own else entry["published_version"],
                    "visibility": (
                        "published" if entry.get("published_package") else "private"
                    ),
                    "has_unpublished_changes": bool(
                        own
                        and entry.get("published_package")
                        and entry["revision"] != entry["published_version"]
                    ),
                    "package": copy.deepcopy(package),
                }
            )
    return sorted(result, key=lambda n: (n["creator_id"] != user_id, n["id"]))


def set_published(registry, user_id, node_id, published):
    entry = get_node(registry, user_id, node_id, owned=True)
    if published:
        entry["published_package"] = validate_pack(entry["package"])
        entry["published_version"] = entry["revision"]
    else:
        entry.pop("published_package", None)
    return entry


def example_pack():
    return validate_pack(
        {
            "schema": SCHEMA,
            "version": 1,
            "name": "Guild Beacon",
            "description": "Read the party's guild membership, then branch on whether a guild member joined.",
            "entry": "guild_beacon",
            "catalogues": {
                "resources": [
                    {
                        "id": "guild_members",
                        "label": "Guild members",
                        "initial": 0,
                        "min": 0,
                        "max": 1000,
                    }
                ]
            },
            "nodes": [
                dict(
                    default_node("guild_beacon", "system"),
                    source="party_guild_members",
                    output_resource="guild_members",
                    simulation_value=2,
                    next="guild_check",
                    failure="$failure",
                ),
                dict(
                    default_node("guild_check", "check"),
                    subject="guild_members",
                    operator=">=",
                    value=1,
                    next="$next",
                    failure="$failure",
                ),
            ],
        }
    )

"""Portable visual editor packages. Imports update only an owned existing draft."""

import base64
import copy
import hashlib
import json
from pathlib import Path

from .engine import validate_encounter
from .mechanics import upgrade_encounter


MAX_PACKAGE_BYTES = 1_000_000
SCHEMA = "fablereborn.raid-canvas"


def definition_digest(definition):
    return hashlib.sha256(json.dumps(definition, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def export_package(definition):
    if definition.get("skeleton") != "encounter":
        raise ValueError("The canvas edits Advanced raids. Create an Advanced draft first.")
    editable = copy.deepcopy(definition)
    editable["config"]["encounter"] = upgrade_encounter(editable["config"]["encounter"])
    return {"schema": SCHEMA, "version": 1, "definition_id": definition["id"],
            "base_digest": definition_digest(definition), "definition": editable}


def editor_html(definition):
    package = json.dumps(export_package(definition), ensure_ascii=False, allow_nan=False).encode()
    encoded = base64.b64encode(package).decode("ascii")
    template = Path(__file__).with_name("canvas.html").read_text(encoding="utf-8")
    return template.replace("__RAID_PACKAGE_BASE64__", encoded).encode("utf-8")


def import_package(data, existing):
    if len(data) > MAX_PACKAGE_BYTES:
        raise ValueError("Canvas files must be smaller than 1 MB.")
    try:
        package = json.loads(data)
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise ValueError("This is not a valid raid canvas save file.") from exc
    if not isinstance(package, dict) or package.get("schema") != SCHEMA or package.get("version") != 1:
        raise ValueError("Upload a save exported by the raid canvas.")
    if package.get("definition_id") != existing["id"]:
        raise ValueError("This file belongs to a different draft. Use its original draft ID.")
    if package.get("base_digest") != definition_digest(existing):
        raise ValueError("This draft changed after the canvas was opened. Export a fresh canvas before importing; existing edits were preserved.")
    incoming = package.get("definition")
    if not isinstance(incoming, dict) or not isinstance(incoming.get("config"), dict):
        raise ValueError("The canvas file has no raid configuration.")
    result = copy.deepcopy(existing)
    # Never import owner/status/mode/revision/limits or arbitrary top-level metadata.
    for key, maximum in (("name", 100), ("description", 3500)):
        value = incoming.get(key)
        if not isinstance(value, str) or len(value) > maximum or (key == "name" and not value.strip()):
            raise ValueError(f"Invalid raid {key}.")
        result[key] = value
    config = incoming["config"]
    for key, low, high in (("join_timeout", 30, 900), ("decision_timeout", 10, 180), ("step_delay", 1, 30)):
        value = config.get(key)
        if type(value) is not int or not low <= value <= high:
            raise ValueError(f"{key} must be between {low} and {high}.")
        result["config"][key] = value
    try:
        encounter = upgrade_encounter(config.get("encounter"))
        validate_encounter(encounter)
    except (TypeError, KeyError, AttributeError, RecursionError) as exc:
        raise ValueError("The encounter contains malformed settings. Validate it in the canvas and retry.") from exc
    result["config"]["encounter"] = encounter
    result["config"]["announce"].update(title=result["name"], description=result["description"])
    # Rewards stay in the existing server-side reward editor.
    return result

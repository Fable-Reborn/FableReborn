"""Shared helpers for pet skill contract auditing and tests."""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple


ROOT = Path(__file__).resolve().parents[1]
SKILL_TREES_FILE = ROOT / "cogs" / "pets" / "__init__.py"
PETS_EXTENSION_FILE = ROOT / "cogs" / "battles" / "extensions" / "pets.py"


MODE_FILES: Dict[str, Path] = {
    "raid": ROOT / "cogs" / "battles" / "types" / "raid.py",
    "pve": ROOT / "cogs" / "battles" / "types" / "pve.py",
    "team_battle": ROOT / "cogs" / "battles" / "types" / "team_battle.py",
    "tower": ROOT / "cogs" / "battles" / "types" / "tower.py",
    "dragon": ROOT / "cogs" / "battles" / "types" / "dragon.py",
    "couples_tower": ROOT / "cogs" / "battles" / "types" / "couples_tower.py",
}


@dataclass(frozen=True)
class SkillRecord:
    element: str
    branch: str
    tier: int
    skill_name: str
    description: str
    cost: int


def load_skill_trees(path: Path = SKILL_TREES_FILE) -> Dict[str, Any]:
    """Load `self.SKILL_TREES` via AST without importing discord-heavy modules."""
    module = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(module):
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if (
                isinstance(target, ast.Attribute)
                and isinstance(target.value, ast.Name)
                and target.value.id == "self"
                and target.attr == "SKILL_TREES"
            ):
                return ast.literal_eval(node.value)
    raise RuntimeError("Could not find self.SKILL_TREES assignment in cogs/pets/__init__.py")


def iter_skill_records(skill_trees: Dict[str, Any]) -> List[SkillRecord]:
    records: List[SkillRecord] = []
    for element, branches in skill_trees.items():
        for branch, tier_map in branches.items():
            for tier, data in tier_map.items():
                records.append(
                    SkillRecord(
                        element=element,
                        branch=branch,
                        tier=int(tier),
                        skill_name=str(data["name"]),
                        description=str(data["description"]),
                        cost=int(data["cost"]),
                    )
                )
    return records


def classify_trigger(description: str) -> str:
    text = description.lower()
    if "ultimate" in text:
        return "ultimate"
    if "start of each turn" in text or "each turn" in text or "per turn" in text:
        return "per_turn"
    if any(kw in text for kw in ("incoming damage", "when pet takes", "when attacked", "reduce incoming", "dodge")):
        return "on_damage_taken"
    if any(kw in text for kw in ("when pet attacks", "on attacks", "attacks", "critical hits", "attacks hit")):
        return "on_attack"
    return "passive"


def extract_contract(description: str) -> Tuple[List[Dict[str, Any]], List[str]]:
    claims: List[Dict[str, Any]] = []
    text = description.lower()

    for match in re.finditer(r"(\d+(?:\.\d+)?)%", text):
        claims.append({"kind": "percent", "value": float(match.group(1)), "raw": match.group(0)})
    for match in re.finditer(r"(\d+(?:\.\d+)?)x", text):
        claims.append({"kind": "multiplier", "value": float(match.group(1)), "raw": match.group(0)})
    for match in re.finditer(r"(\d+)\s*turns?", text):
        claims.append({"kind": "duration_turns", "value": int(match.group(1)), "raw": match.group(0)})
    for match in re.finditer(r"below\s+(\d+(?:\.\d+)?)%\s*hp", text):
        claims.append({"kind": "threshold_below_hp", "value": float(match.group(1)), "raw": match.group(0)})
    for match in re.finditer(r"max\s+(\d+)", text):
        claims.append({"kind": "max_cap", "value": int(match.group(1)), "raw": match.group(0)})

    # De-duplicate while preserving order.
    seen: Set[Tuple[str, float, str]] = set()
    deduped: List[Dict[str, Any]] = []
    for claim in claims:
        key = (claim["kind"], float(claim["value"]), claim["raw"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(claim)

    clauses = re.split(r"\s*\+\s*|,\s*|\s+and\s+", description)
    ambiguous_keywords = {
        "can",
        "random",
        "nearby",
        "massive",
        "control",
        "rewrite",
        "manipulate",
        "enhanced",
        "unlimited",
        "predict",
        "different target",
    }
    ambiguous: List[str] = []
    for clause in clauses:
        clause_l = clause.lower().strip()
        if not clause_l:
            continue
        if re.search(r"\d", clause_l):
            continue
        if any(word in clause_l for word in ambiguous_keywords):
            ambiguous.append(clause.strip())

    return deduped, ambiguous


def _slug_skill_name(skill_name: str) -> str:
    cleaned = skill_name.lower()
    # Handle possessives while preserving words ending in "s" (e.g., Zeus's -> zeus).
    cleaned = re.sub(r"s's\b", "s", cleaned)
    cleaned = cleaned.replace("'s", "s").replace("'", "")
    cleaned = re.sub(r"[^a-z0-9]+", "_", cleaned)
    return cleaned.strip("_")


def _extract_apply_payloads(path: Path = PETS_EXTENSION_FILE) -> Dict[str, Any]:
    """
    Parse `apply_skill_effects` assignments:
    `pet_combatant.skill_effects['effect_key'] = {...}`
    """
    source = path.read_text(encoding="utf-8")
    module = ast.parse(source)
    payloads: Dict[str, Any] = {}

    for node in ast.walk(module):
        if not isinstance(node, ast.Assign):
            continue
        if len(node.targets) != 1:
            continue
        target = node.targets[0]
        if not (
            isinstance(target, ast.Subscript)
            and isinstance(target.value, ast.Attribute)
            and isinstance(target.value.value, ast.Name)
            and target.value.value.id == "pet_combatant"
            and target.value.attr == "skill_effects"
        ):
            continue

        key_node = target.slice
        if isinstance(key_node, ast.Constant) and isinstance(key_node.value, str):
            effect_key = key_node.value
        elif isinstance(key_node, ast.Index) and isinstance(key_node.value, ast.Constant):
            effect_key = key_node.value.value
        else:
            continue

        try:
            payload = ast.literal_eval(node.value)
        except Exception:
            payload = {}

        # Keep first assignment per key in apply_skill_effects.
        payloads.setdefault(effect_key, payload)

    return payloads


def build_skill_runtime_map(records: Iterable[SkillRecord]) -> Dict[Tuple[str, str], Dict[str, Any]]:
    """
    Map `(element, skill_name)` to expected runtime effect keys/payload from `apply_skill_effects`.
    Uses static parsing to avoid importing battle package dependencies.
    """
    payloads = _extract_apply_payloads()
    mapping: Dict[Tuple[str, str], Dict[str, Any]] = {}

    for record in records:
        skill_l = record.skill_name.lower()
        effect_keys: List[str] = []
        payload: Dict[str, Any] = {}

        if skill_l == "battery life":
            effect_keys = []
        else:
            guessed_key = _slug_skill_name(record.skill_name)
            if guessed_key == "storm_lord" and record.element.lower() == "wind":
                guessed_key = "storm_lord_wind"

            if guessed_key in payloads:
                effect_keys = [guessed_key]
                payload = {guessed_key: payloads[guessed_key]}

        mapping[(record.element, record.skill_name)] = {"effect_keys": effect_keys, "payload": payload}

    return mapping


def _extract_function_source(path: Path, function_name: str) -> str:
    text = path.read_text(encoding="utf-8")
    module = ast.parse(text)
    for node in ast.walk(module):
        if isinstance(node, ast.FunctionDef) and node.name == function_name:
            start = node.lineno - 1
            end = node.end_lineno or node.lineno
            return "\n".join(text.splitlines()[start:end])
    raise RuntimeError(f"Function {function_name!r} not found in {path}")


def extract_effect_contexts(path: Path = PETS_EXTENSION_FILE) -> Dict[str, Set[str]]:
    """Return map: `effect_key -> {on_attack,on_damage_taken,per_turn}`."""
    contexts = {
        "on_attack": _extract_function_source(path, "process_skill_effects_on_attack"),
        "on_damage_taken": _extract_function_source(path, "process_skill_effects_on_damage_taken"),
        "per_turn": _extract_function_source(path, "process_skill_effects_per_turn"),
    }
    key_contexts: Dict[str, Set[str]] = {}
    key_pattern = re.compile(
        r"['\"]([a-z0-9_]+)['\"]\s+in\s+(?:effects|pet_combatant\.skill_effects)"
    )

    for context_name, source in contexts.items():
        for key in key_pattern.findall(source):
            key_contexts.setdefault(key, set()).add(context_name)

    return key_contexts


def collect_set_only_attrs() -> Dict[str, List[Tuple[str, int]]]:
    """
    Collect attrs set via `setattr(..., \"name\", ...)` in battles code where no getter/checker path exists.

    This is a conservative static signal used by the audit report.
    """
    set_locs: Dict[str, List[Tuple[str, int]]] = {}
    read_locs: Dict[str, List[Tuple[str, int]]] = {}
    code_files = list((ROOT / "cogs" / "battles").rglob("*.py"))

    for path in code_files:
        rel = str(path.relative_to(ROOT))
        try:
            module = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:
            continue

        for node in ast.walk(module):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
                continue
            func = node.func.id
            if func not in {"setattr", "getattr", "hasattr", "delattr"}:
                continue
            if len(node.args) < 2:
                continue
            key = node.args[1]
            if not isinstance(key, ast.Constant) or not isinstance(key.value, str):
                continue
            attr_name = key.value
            if func == "setattr":
                set_locs.setdefault(attr_name, []).append((rel, node.lineno))
            else:
                read_locs.setdefault(attr_name, []).append((rel, node.lineno))

    set_only: Dict[str, List[Tuple[str, int]]] = {}
    for attr_name, locs in set_locs.items():
        if attr_name not in read_locs:
            set_only[attr_name] = locs
    return set_only


def evaluate_mode_resolver_parity() -> Dict[str, Dict[str, Any]]:
    """Static checks for mode parity on canonical pet resolver + turn priority wiring."""
    report: Dict[str, Dict[str, Any]] = {}
    for mode, path in MODE_FILES.items():
        source = path.read_text(encoding="utf-8")
        report[mode] = {
            "resolver_calls": source.count("resolve_pet_attack_outcome("),
            "has_turn_priority_sort": "prioritize_turn_order(" in source,
            "contains_legacy_special_damage_block": "check_special_damage_types(" in source,
        }
    return report


def normalize_numeric_tokens(payload: Dict[str, Any]) -> Set[str]:
    """Flatten numeric payload values into comparable tokens."""
    tokens: Set[str] = set()

    def visit(value: Any) -> None:
        if isinstance(value, bool):
            return
        if isinstance(value, (int, float)):
            number = float(value)
            tokens.add(f"num:{number:g}")
            if 0 <= number <= 1:
                tokens.add(f"pct:{number * 100:g}")
        elif isinstance(value, dict):
            for nested in value.values():
                visit(nested)
        elif isinstance(value, (list, tuple, set)):
            for nested in value:
                visit(nested)

    visit(payload)
    return tokens


def normalize_claim_tokens(claims: List[Dict[str, Any]]) -> Set[str]:
    tokens: Set[str] = set()
    for claim in claims:
        kind = claim["kind"]
        value = claim["value"]
        if kind == "percent":
            tokens.add(f"pct:{float(value):g}")
        elif kind == "multiplier":
            tokens.add(f"num:{float(value):g}")
        elif kind in {"duration_turns", "max_cap"}:
            tokens.add(f"num:{int(value):g}")
        elif kind == "threshold_below_hp":
            tokens.add(f"pct:{float(value):g}")
    return tokens

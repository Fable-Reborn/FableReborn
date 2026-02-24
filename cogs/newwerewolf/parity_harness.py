from __future__ import annotations

import ast
import difflib
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
LEGACY_FILE = REPO_ROOT / "utils" / "werewolf.py"
NEW_FILE = REPO_ROOT / "cogs" / "newwerewolf" / "core.py"

MODULE_FUNCTIONS = [
    "target_wolf_count_for_players",
    "max_special_wolves_for_player_count",
    "cap_special_werewolves",
    "enforce_wolf_ratio",
    "force_role",
]

CONFIG_EXTENDED_FUNCTIONS = [
    "get_roles",
    "get_custom_roles",
]

GAME_METHODS = [
    "wolves",
    "election",
    "handle_afk",
    "apply_night_protection",
    "initial_preparation",
    "night",
    "day",
    "run",
]


def _load_source(path: Path) -> tuple[str, ast.Module]:
    source = path.read_text(encoding="utf-8")
    return source, ast.parse(source)


def _normalize(segment: str | None) -> str:
    if not segment:
        return ""
    lines = [line.rstrip() for line in segment.strip().splitlines()]
    while lines and not lines[0]:
        lines.pop(0)
    while lines and not lines[-1]:
        lines.pop()
    return "\n".join(lines)


def _get_module_function_source(
    tree: ast.Module, source: str, name: str
) -> str | None:
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return _normalize(ast.get_source_segment(source, node))
    return None


def _get_class_method_source(
    tree: ast.Module, source: str, class_name: str, method_name: str
) -> str | None:
    for node in tree.body:
        if not isinstance(node, ast.ClassDef) or node.name != class_name:
            continue
        for item in node.body:
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name == method_name:
                return _normalize(ast.get_source_segment(source, item))
    return None


def _compare_and_report(name: str, expected: str, actual: str) -> bool:
    if expected == actual:
        print(f"[OK] {name}")
        return True
    print(f"[DIFF] {name}")
    diff = difflib.unified_diff(
        expected.splitlines(),
        actual.splitlines(),
        fromfile="legacy",
        tofile="new",
        lineterm="",
    )
    for line in diff:
        print(line)
    return False


def main() -> int:
    legacy_source, legacy_tree = _load_source(LEGACY_FILE)
    new_source, new_tree = _load_source(NEW_FILE)

    all_ok = True

    for function_name in MODULE_FUNCTIONS:
        legacy_fn = _get_module_function_source(
            legacy_tree, legacy_source, function_name
        )
        new_fn = _get_module_function_source(new_tree, new_source, function_name)
        if legacy_fn is None or new_fn is None:
            print(f"[MISSING] function {function_name}")
            all_ok = False
            continue
        all_ok = _compare_and_report(
            f"function::{function_name}", legacy_fn, new_fn
        ) and all_ok

    for function_name in CONFIG_EXTENDED_FUNCTIONS:
        legacy_fn = _get_module_function_source(
            legacy_tree, legacy_source, function_name
        )
        new_fn = _get_module_function_source(new_tree, new_source, function_name)
        if legacy_fn is None or new_fn is None:
            print(f"[MISSING] function {function_name}")
            all_ok = False
            continue
        if "_apply_role_availability(" in new_fn:
            print(f"[OK] function::{function_name} (config-extended)")
        else:
            print(f"[DIFF] function::{function_name} missing config extension")
            all_ok = False

    for method_name in GAME_METHODS:
        legacy_method = _get_class_method_source(
            legacy_tree, legacy_source, "Game", method_name
        )
        new_method = _get_class_method_source(new_tree, new_source, "Game", method_name)
        if legacy_method is None or new_method is None:
            print(f"[MISSING] Game.{method_name}")
            all_ok = False
            continue
        all_ok = _compare_and_report(
            f"Game::{method_name}", legacy_method, new_method
        ) and all_ok

    if all_ok:
        print("Parity harness passed.")
        return 0
    print("Parity harness failed.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

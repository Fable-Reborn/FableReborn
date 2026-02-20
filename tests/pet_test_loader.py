"""Utilities for loading battle modules in isolation for unit tests."""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path
from typing import Tuple, Type


ROOT = Path(__file__).resolve().parents[1]


def _ensure_namespace(module_name: str, path: Path) -> None:
    if module_name in sys.modules:
        return
    module = types.ModuleType(module_name)
    module.__path__ = [str(path)]  # type: ignore[attr-defined]
    sys.modules[module_name] = module


def _load_module(module_name: str, file_path: Path):
    if module_name in sys.modules:
        return sys.modules[module_name]
    spec = importlib.util.spec_from_file_location(module_name, str(file_path))
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not create module spec for {module_name} ({file_path})")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def load_pet_runtime_types() -> Tuple[Type[object], Type[object]]:
    """
    Return `(Combatant, PetExtension)` from battle runtime modules without importing
    `cogs.battles.__init__`.
    """
    _ensure_namespace("cogs", ROOT / "cogs")
    _ensure_namespace("cogs.battles", ROOT / "cogs" / "battles")
    _ensure_namespace("cogs.battles.core", ROOT / "cogs" / "battles" / "core")
    _ensure_namespace("cogs.battles.extensions", ROOT / "cogs" / "battles" / "extensions")

    combatant_mod = _load_module(
        "cogs.battles.core.combatant",
        ROOT / "cogs" / "battles" / "core" / "combatant.py",
    )
    pets_mod = _load_module(
        "cogs.battles.extensions.pets",
        ROOT / "cogs" / "battles" / "extensions" / "pets.py",
    )
    return combatant_mod.Combatant, pets_mod.PetExtension

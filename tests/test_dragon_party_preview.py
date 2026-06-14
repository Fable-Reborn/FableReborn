import ast
import unittest
from decimal import Decimal
from pathlib import Path

from classes.classes import from_string as class_from_string


MODULE_PATH = Path(__file__).parents[1] / "cogs" / "battles" / "__init__.py"


def _load_method(name):
    tree = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))
    battles = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "Battles"
    )
    method = next(
        node
        for node in battles.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == name
    )
    method.decorator_list = []
    namespace = {
        "Decimal": Decimal,
        "class_from_string": class_from_string,
    }
    exec(compile(ast.Module(body=[method], type_ignores=[]), MODULE_PATH, "exec"), namespace)
    return namespace[name]


class TestDragonPartyPreview(unittest.TestCase):
    def test_stat_format_handles_float_and_decimal(self):
        format_stat = _load_method("_format_dragon_party_stat")

        self.assertEqual("1,234", format_stat(1234.5))
        self.assertEqual("9,876", format_stat(Decimal("9876.5")))

    def test_class_label_uses_base_class_lines(self):
        class_label = _load_method("_dragon_party_class_label")

        self.assertEqual("Tank", class_label(["Protector"]))
        self.assertEqual("Warrior / Mage", class_label(["Grunt", "Juggler"]))
        self.assertEqual("Adventurer", class_label([]))

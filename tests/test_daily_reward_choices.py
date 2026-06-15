import ast
import asyncio
import unittest
from pathlib import Path
from types import SimpleNamespace


DAILY_SOURCE = Path("cogs/miscellaneous/__init__.py")


class FakeRandom:
    def __init__(self, randint_values, choice_index=0):
        self.randint_values = iter(randint_values)
        self.choice_index = choice_index

    def randint(self, _minimum, _maximum):
        return next(self.randint_values)

    def choice(self, values):
        return values[self.choice_index]


def load_roll_daily_reward(fake_random):
    tree = ast.parse(DAILY_SOURCE.read_text(encoding="utf-8"))
    cog = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "Miscellaneous"
    )
    method = next(
        node
        for node in cog.body
        if isinstance(node, ast.FunctionDef) and node.name == "_roll_daily_reward"
    )
    module = ast.fix_missing_locations(ast.Module(body=[method], type_ignores=[]))
    namespace = {"random": fake_random}
    exec(compile(module, str(DAILY_SOURCE), "exec"), namespace)
    return namespace["_roll_daily_reward"]


def load_daily_interaction_check():
    tree = ast.parse(DAILY_SOURCE.read_text(encoding="utf-8"))
    view = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "DailyRewardChoiceView"
    )
    method = next(
        node
        for node in view.body
        if isinstance(node, ast.AsyncFunctionDef)
        and node.name == "interaction_check"
    )
    for argument in method.args.args:
        argument.annotation = None
    method.returns = None
    namespace = {}
    exec(
        compile(ast.Module(body=[method], type_ignores=[]), str(DAILY_SOURCE), "exec"),
        namespace,
    )
    return namespace["interaction_check"]


class TestDailyRewardChoices(unittest.TestCase):
    def test_two_rolls_are_independent(self):
        roller = load_roll_daily_reward(FakeRandom([1, 0, 2]))

        first = roller(None, 7, 1.0)
        second = roller(None, 7, 1.0)

        self.assertEqual({"kind": "money", "amount": 3200}, first)
        self.assertEqual(
            {"kind": "crate", "rarity": "uncommon", "amount": 2},
            second,
        )

    def test_money_multiplier_is_applied_to_each_gold_roll(self):
        roller = load_roll_daily_reward(FakeRandom([2]))
        reward = roller(None, 1, 4.5)
        self.assertEqual({"kind": "money", "amount": 225}, reward)

    def test_day_seven_crate_roll_keeps_existing_quantity_range(self):
        roller = load_roll_daily_reward(FakeRandom([0, 1]))
        reward = roller(None, 7, 1.0)
        self.assertEqual(1, reward["amount"])
        self.assertEqual("uncommon", reward["rarity"])

    def test_linked_main_can_choose_reward_for_alt_context(self):
        interaction_check = load_daily_interaction_check()
        view = SimpleNamespace(
            ctx=SimpleNamespace(
                author=SimpleNamespace(id=200),
                alt_invoker_id=100,
            )
        )
        interaction = SimpleNamespace(user=SimpleNamespace(id=100))

        self.assertTrue(asyncio.run(interaction_check(view, interaction)))

    def test_unrelated_user_cannot_choose_alt_reward(self):
        interaction_check = load_daily_interaction_check()

        class Response:
            def __init__(self):
                self.messages = []

            async def send_message(self, message, **kwargs):
                self.messages.append((message, kwargs))

        response = Response()
        view = SimpleNamespace(
            ctx=SimpleNamespace(
                author=SimpleNamespace(id=200),
                alt_invoker_id=100,
            )
        )
        interaction = SimpleNamespace(
            user=SimpleNamespace(id=300),
            response=response,
        )

        self.assertFalse(asyncio.run(interaction_check(view, interaction)))
        self.assertTrue(response.messages[0][1]["ephemeral"])


if __name__ == "__main__":
    unittest.main()

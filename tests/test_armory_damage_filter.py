import asyncio
import sys
import types
import unittest
from decimal import Decimal
from types import SimpleNamespace

import discord
from discord.ext.commands.errors import BadArgument
from discord.ext.commands.view import StringView

try:
    import fantasy_names  # noqa: F401
except ModuleNotFoundError:
    _fantasy_names = types.ModuleType("fantasy_names")
    _fantasy_names.weapon_name = lambda *args, **kwargs: "Blade"
    sys.modules["fantasy_names"] = _fantasy_names

import cogs.profile as profile
from classes.endgame import apply_item_progression_bonus


def _weapon(**overrides):
    item = {
        "id": 1,
        "name": "Blade",
        "type": "Sword",
        "hand": "both",
        "element": "Fire",
        "damage": 180,
        "armor": 0,
        "value": 10,
        "signature": None,
        "equipped": False,
        "locked": False,
        "effective_damage": 180,
        "effective_armor": 0,
    }
    item.update(overrides)
    return item


def _cog():
    return profile.Profile.__new__(profile.Profile)


def _names(items):
    return [item["name"] for item in items]


class _Response:
    def __init__(self):
        self.messages = []
        self.deferred = False

    async def send_message(self, content, **kwargs):
        self.messages.append(content)

    async def defer(self, **kwargs):
        self.deferred = True


class _Ctx:
    def __init__(self):
        self.calls = []
        self.bot = SimpleNamespace(get_command=lambda name: "armory")

    async def invoke(self, command, **kwargs):
        self.calls.append((command, kwargs))


def _modal(**view):
    state = dict(itemtype="All", lowest=0, highest=201, min_damage=None)
    state.update(view)
    ctx = _Ctx()
    modal = profile.ArmoryFilterModal(SimpleNamespace(ctx=ctx, **state))
    return modal, ctx


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


class ArmoryDamageFilterTest(unittest.TestCase):
    def setUp(self):
        self.cog = _cog()
        self.two_hand = _weapon(id=1, name="Greatsword", hand="both", damage=179, effective_damage=179)
        self.low_two_hand = _weapon(id=2, name="Shortspear", hand="both", damage=178, effective_damage=178)
        self.high_one_hand = _weapon(
            id=3, name="Rapier", type="Sword", hand="left", damage=200, effective_damage=200, equipped=True,
        )
        self.shield = _weapon(
            id=4, name="Tower", type="Shield", hand="any", damage=0, armor=200,
            effective_damage=0, effective_armor=200, equipped=True,
        )
        self.armory = [
            self.two_hand,
            self.low_two_hand,
            self.high_one_hand,
            self.shield,
        ]

    def _keep(self, items=None, **kwargs):
        params = dict(itemtype="All", lowest=0, highest=201, min_damage=None)
        params.update(kwargs)
        return self.cog._filter_armory_items(self.armory if items is None else items, **params)

    def test_blank_damage_does_not_filter(self):
        self.assertEqual(_names(self._keep(min_damage=None)), _names(self.armory))
        self.assertIsNone(profile.parse_armory_min_damage("   "))
        self.assertIsNone(profile.parse_armory_min_damage(None))

    def test_damage_floor_is_inclusive_and_ignores_armor(self):
        self.assertEqual(_names(self._keep(min_damage=179)), ["Greatsword", "Rapier"])
        bulky = _weapon(name="Bulky", hand="both", damage=100, armor=90, effective_damage=100)
        self.assertEqual(self._keep([bulky], itemtype="2h", min_damage=179), [])
        exact = _weapon(name="Exact", hand="both", damage=95, effective_damage=95)
        self.assertEqual(_names(self._keep([exact], min_damage=95)), ["Exact"])

    def test_two_hand_and_damage_floor_stack(self):
        kept = self._keep(itemtype="2h", min_damage=179)
        self.assertEqual(_names(kept), ["Greatsword"])
        one_hand = self._keep(itemtype="1h", min_damage=179)
        self.assertEqual(_names(one_hand), ["Rapier"])
        swords = self._keep(
            [
                _weapon(name="Saber", type="Sword", hand="any", damage=180, effective_damage=180),
                _weapon(name="Woodaxe", type="Axe", hand="both", damage=190, effective_damage=190),
            ],
            itemtype="Sword",
            min_damage=179,
        )
        self.assertEqual(_names(swords), ["Saber"])

    def test_floor_uses_the_printed_damage_including_progression(self):
        boosted, _, _ = apply_item_progression_bonus(150, 0, stars=10)
        self.assertGreaterEqual(boosted, 179)
        starforged = _weapon(name="Starred", hand="both", damage=150, effective_damage=boosted)
        self.assertEqual(
            _names(self._keep([starforged], itemtype="2h", min_damage=179)),
            ["Starred"],
        )
        # The total-stat boxes still use the base damage + armor, matching the query.
        self.assertEqual(
            self._keep([starforged], itemtype="2h", lowest=0, highest=140, min_damage=179),
            [],
        )
        shown_high = _weapon(name="Rounds Up", hand="both", damage=170, effective_damage=Decimal("178.96"))
        shown_low = _weapon(name="Rounds Down", hand="both", damage=170, effective_damage=Decimal("178.94"))
        ctx = SimpleNamespace(disp="Tester")
        high_line = self.cog.invembed(ctx, [shown_high], 0, 0).fields[0].value
        low_line = self.cog.invembed(ctx, [shown_low], 0, 0).fields[0].value
        self.assertIn("179.0", high_line)
        self.assertIn("178.9", low_line)
        self.assertEqual(_names(self._keep([shown_high], min_damage=179)), ["Rounds Up"])
        self.assertEqual(self._keep([shown_low], min_damage=179), [])
        plain = _weapon(name="Plain", damage=95)
        plain.pop("effective_damage")
        self.assertEqual(_names(self._keep([plain], min_damage=95)), ["Plain"])

    def test_modal_damage_field_is_optional_and_stacks_with_type(self):
        async def go():
            modal, ctx = _modal(itemtype="2h", lowest=10, highest=180, min_damage=179)
            labels = [child.label for child in modal.children]
            self.assertEqual(
                labels,
                ["Item type", "Minimum total stat", "Maximum total stat", "Minimum weapon damage"],
            )
            self.assertFalse(modal.min_damage.required)
            self.assertEqual(modal.item_type.to_component_dict()["value"], "2h")
            self.assertEqual(modal.min_damage.to_component_dict()["value"], "179")
            self.assertEqual(modal.lowest.to_component_dict()["value"], "10")

            fresh, _ = _modal()
            self.assertEqual(fresh.item_type.to_component_dict()["value"], "All")
            self.assertFalse(fresh.min_damage.to_component_dict().get("value"))
            # A later modal must not keep the previous player's prefilled damage.
            self.assertEqual(modal.min_damage.to_component_dict()["value"], "179")

            async def submit(target, **values):
                target.item_type._value = values.get("item_type", "2h")
                target.lowest._value = values.get("lowest", "0")
                target.highest._value = values.get("highest", "201")
                target.min_damage._value = values.get("min_damage", "")
                await target.on_submit(SimpleNamespace(response=_Response()))

            await submit(modal, item_type="2h", min_damage="")
            self.assertEqual(ctx.calls[-1][1]["min_damage"], None)
            self.assertEqual(ctx.calls[-1][1]["itemtype"], "2h")

            await submit(modal, item_type="2h", min_damage="   ")
            self.assertIsNone(ctx.calls[-1][1]["min_damage"])

            await submit(modal, item_type="2h", min_damage="179")
            self.assertEqual(
                ctx.calls[-1][1],
                {"itemtype": "2h", "lowest": 0, "highest": 201, "min_damage": 179},
            )

            response = _Response()
            modal.min_damage._value = "nope"
            await modal.on_submit(SimpleNamespace(response=response))
            self.assertEqual(response.messages, ["Weapon damage must be a whole number, or left blank."])
            self.assertEqual(len(ctx.calls), 3)

            response = _Response()
            modal.min_damage._value = "-1"
            await modal.on_submit(SimpleNamespace(response=response))
            self.assertIn("0 to 99999", response.messages[0])

            response = _Response()
            modal.lowest._value = "nope"
            modal.min_damage._value = "179"
            await modal.on_submit(SimpleNamespace(response=response))
            self.assertEqual(response.messages, ["Stat limits must be whole numbers."])

        _run(go())

    def test_armory_command_accepts_the_damage_argument(self):
        command = profile.Profile.armory

        async def parse(text):
            ctx = SimpleNamespace(
                message=SimpleNamespace(attachments=[]),
                view=StringView(text),
                current_argument=None,
                current_parameter=None,
            )
            await command._parse_arguments(ctx)
            return ctx.args[-4:]

        self.assertEqual(_run(parse("")), ["All", 0, 201, None])
        self.assertEqual(_run(parse("2h")), ["2h", 0, 201, None])
        self.assertEqual(_run(parse("2h 50 201")), ["2h", 50, 201, None])
        self.assertEqual(_run(parse("2h 0 201 179")), ["2h", 0, 201, 179])
        self.assertEqual(_run(parse("Sword 10 180 95")), ["Sword", 10, 180, 95])

        async def rejected(text):
            with self.assertRaises(BadArgument):
                await parse(text)

        _run(rejected("2h 0 201 nope"))
        _run(rejected("2h 0 201 -3"))
        _run(rejected("2h 0 201 100000"))

    def test_open_filter_remembers_type_and_damage(self):
        async def go():
            item = _weapon()
            embed = discord.Embed(title="Armory")
            embed.set_footer(text="Page 1 of 1")
            ctx = SimpleNamespace(author=SimpleNamespace(id=5), disp="Tester")
            view = profile.ArmoryPaginatorView(
                ctx,
                self.cog,
                [[item]],
                [embed],
                itemtype="2h",
                lowest=0,
                highest=201,
                min_damage=179,
            )
            self.assertIn("2h weapons with damage 179+", view.embeds[0].footer.text)
            view.apply_sort("name")
            self.assertIn("2h weapons with damage 179+", view.embeds[0].footer.text)
            modal = profile.ArmoryFilterModal(view)
            self.assertEqual(modal.item_type.to_component_dict()["value"], "2h")
            self.assertEqual(modal.min_damage.to_component_dict()["value"], "179")

            plain = discord.Embed(title="Armory")
            plain.set_footer(text="Page 1 of 1")
            unfiltered = profile.ArmoryPaginatorView(
                ctx, self.cog, [[item]], [plain],
            )
            self.assertEqual(unfiltered.embeds[0].footer.text, "Page 1 of 1")
            self.assertFalse(profile.ArmoryFilterModal(unfiltered).min_damage.to_component_dict().get("value"))

        _run(go())


if __name__ == "__main__":
    unittest.main()

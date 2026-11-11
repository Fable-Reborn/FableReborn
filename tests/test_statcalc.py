import copy
import unittest
from decimal import Decimal

from utils import statcalc


def _blade(**overrides) -> statcalc.Sheet:
    sheet = statcalc.Sheet(
        hero_name="Test",
        origin="loaded",
        right_name="Blade",
        right_damage=Decimal(100),
        right_stars=5,
        right_fit=1,
        level=1,
        amulet_atk=Decimal(10),
    )
    for key, value in overrides.items():
        setattr(sheet, key, value)
    return sheet


class TestStatMath(unittest.TestCase):
    def test_stars_then_class_fit_then_multiplier_then_amulet(self):
        sheet = _blade()
        result = statcalc.compute(sheet)

        # 100 × 1.20 stars, then +5 class fit. The fit is outside the star percent.
        self.assertEqual(result.right_pct, Decimal("0.20"))
        self.assertEqual(result.right_damage, Decimal("125"))
        self.assertEqual(result.gear_attack, Decimal("125"))
        self.assertEqual(result.attack_multiplier, Decimal("1"))
        self.assertEqual(result.multiplied_attack, Decimal("125"))
        self.assertEqual(result.raid_attack, Decimal("135"))
        self.assertEqual(
            result.raid_attack,
            result.gear_attack * result.attack_multiplier + result.amulet_attack,
        )
        self.assertEqual(result.health, Decimal(215))

    def test_star_and_soulbound_percents_add(self):
        sheet = _blade(right_fit=0, right_soul=20, amulet_atk=Decimal(0))
        result = statcalc.compute(sheet)
        # 20% stars + 2% soulbound = 22%. 100 × 1.20 × 1.02 would be 122.4.
        self.assertEqual(result.right_pct, Decimal("0.220"))
        self.assertEqual(result.right_damage, Decimal("122"))

    def test_attack_points_city_and_profile_add_into_one_multiplier(self):
        sheet = _blade(profile_atk=Decimal("1.5"), stat_atk=4, city=3, amulet_atk=Decimal(100))
        result = statcalc.compute(sheet)
        self.assertEqual(result.point_attack, Decimal("0.8"))
        self.assertEqual(result.city_bonus, Decimal("0.3"))
        self.assertEqual(result.attack_multiplier, Decimal("2.6"))
        self.assertEqual(result.defense_multiplier, Decimal("1.3"))
        self.assertEqual(result.raid_attack, Decimal("125") * Decimal("2.6") + Decimal(100))

    def test_card_shows_the_weapon_and_what_one_damage_adds(self):
        sheet = _blade()
        text = statcalc.card(sheet, "right_damage")
        self.assertIn("**Attack** 135", text)
        self.assertIn("★5", text)
        self.assertIn("+5", text)
        self.assertIn("+1 damage adds +1.20 attack", text)
        self.assertIn("Amulet +10 atk", text)
        self.assertLess(len(text), 1200)
        self.assertNotIn("What multiplies what", text)

    def test_example_card_only_edits_weapons_and_rs(self):
        sheet = statcalc.example_sheet()
        self.assertEqual(
            [key for key, _label in statcalc.knobs(sheet)],
            ["right_damage", "left_armor", "profile_atk", "profile_def"],
        )
        text = statcalc.card(sheet, "profile_atk")
        self.assertIn("Elf", text)
        self.assertIn("One $rs attack upgrade", text)
        self.assertLess(len(text), 1200)

    def test_health_ignores_the_attack_multiplier(self):
        sheet = statcalc.example_sheet()
        before = statcalc.compute(sheet).health
        sheet.profile_atk = Decimal(9)
        sheet.stat_atk = 40
        sheet.amulet_atk = Decimal(9999)
        after = statcalc.compute(sheet)
        self.assertEqual(after.health, before)
        self.assertNotEqual(after.raid_attack, statcalc.compute(statcalc.example_sheet()).raid_attack)

    def test_shadeborn_negative_is_visible_and_the_card_clamps_it(self):
        sheet = statcalc.Sheet(race="Shadeborn")
        result = statcalc.compute(sheet)
        self.assertEqual(result.gear_attack, Decimal(-1))
        self.assertEqual(result.gear_defense, Decimal(5))
        self.assertEqual(result.raid_attack, Decimal(-1))
        text = statcalc.card(sheet, "right_damage")
        self.assertIn("**Attack** -1", text)
        self.assertIn("Shadeborn", text)

    def test_zero_gear_leaves_the_amulet(self):
        sheet = statcalc.Sheet(amulet_atk=Decimal(50), stat_atk=10)
        result = statcalc.compute(sheet)
        self.assertEqual(result.gear_attack, Decimal(0))
        self.assertEqual(result.raid_attack, Decimal(50))
        self.assertEqual(result.gear_attack * result.attack_multiplier, Decimal(0))

    def test_sliders_clamp_and_accept_typed_numbers(self):
        sheet = statcalc.Sheet(right_stars=9, race="Elf")
        statcalc.move(sheet, "right_stars", 100)
        self.assertEqual(sheet.right_stars, 10)
        statcalc.move(sheet, "race", 1)
        self.assertEqual(sheet.race, "Orc")
        self.assertIsNone(statcalc.apply_text(sheet, "right_damage", "1,080"))
        self.assertEqual(sheet.right_damage, Decimal(1080))
        self.assertIsNone(statcalc.apply_text(sheet, "race", "djinn"))
        self.assertEqual(sheet.race, "Djinn")
        self.assertIsNone(statcalc.apply_text(sheet, "right_fit", "shield"))
        self.assertEqual(sheet.right_fit, 3)
        self.assertIsNotNone(statcalc.apply_text(sheet, "profile_atk", "lots"))
        self.assertFalse(statcalc.can_move(sheet, "right_stars", 1))

    def test_since_you_opened_reports_the_delta(self):
        start = _blade()
        moved = copy.copy(start)
        statcalc.move(moved, "amulet_atk", 5)
        text = statcalc.card(moved, "profile_atk", baseline=start)
        self.assertIn("Was 135 attack", text)

    def test_crafted_amulet_preset(self):
        sheet = statcalc.Sheet()
        statcalc.apply_preset(sheet, "attack:3")
        self.assertEqual(sheet.amulet_atk, Decimal(360))
        self.assertEqual(sheet.amulet_def, Decimal(270))
        self.assertEqual(sheet.amulet_hp, Decimal(450))
        self.assertEqual(statcalc.matching_preset(sheet), "attack:3")
        statcalc.apply_preset(sheet, "clear")
        self.assertEqual(statcalc.matching_preset(sheet), "clear")
        self.assertLessEqual(len(statcalc.preset_choices()), 25)

    def test_amulet_presets_match_crafting(self):
        import ast
        from pathlib import Path

        source = (Path(__file__).resolve().parents[1] / "cogs" / "amuletcrafting" / "__init__.py").read_text(encoding="utf-8")
        found = None
        for node in ast.walk(ast.parse(source)):
            if not isinstance(node, ast.Assign):
                continue
            for target in node.targets:
                if isinstance(target, ast.Attribute) and target.attr == "AMULET_TYPES":
                    found = ast.literal_eval(node.value)
        self.assertIsNotNone(found)
        self.assertEqual(set(found), set(statcalc.AMULET_PRESETS))
        for kind, tiers in found.items():
            for tier, stats in tiers.items():
                preset = statcalc.AMULET_PRESETS[kind][tier]
                self.assertEqual(preset["attack"], stats["attack"], f"{kind} {tier}")
                self.assertEqual(preset["defense"], stats["defense"], f"{kind} {tier}")
                self.assertEqual(preset["hp"], stats["health"], f"{kind} {tier}")


class TestEquippedGear(unittest.TestCase):
    def test_sword_stars_and_warrior_fit(self):
        sheet = statcalc.sheet_from_equipped(
            classes=["Grunt"],
            items=[{"name": "Blade", "type": "Sword", "hand": "right", "damage": 100, "armor": 0, "stars": 5, "soul": 0}],
        )
        result = statcalc.compute(sheet)
        self.assertEqual(sheet.right_fit, 1)
        self.assertEqual(result.right_damage, Decimal("125"))
        self.assertEqual(result.gear_attack, Decimal("125"))
        self.assertEqual(sheet.class_damage, 0)

    def test_bow_stars_do_not_multiply_the_ranger_fit(self):
        sheet = statcalc.sheet_from_equipped(
            classes=["Caretaker"],
            items=[{"name": "Bow", "type": "Bow", "hand": "both", "damage": 100, "stars": 5}],
        )
        result = statcalc.compute(sheet)
        self.assertTrue(sheet.right_two_handed)
        self.assertEqual(sheet.left_damage, 0)
        self.assertEqual(result.right_damage, Decimal("130"))
        self.assertEqual(result.gear_attack, Decimal("130"))

    def test_scythe_reaper_is_plus_ten_and_shield_tank_is_plus_seven(self):
        scythe = statcalc.sheet_from_equipped(
            classes=["Deathshroud"],
            items=[{"type": "Scythe", "hand": "both", "damage": 0}],
        )
        self.assertEqual(statcalc.compute(scythe).gear_attack, Decimal(10))
        shield = statcalc.sheet_from_equipped(
            classes=["Protector"],
            items=[{"type": "Shield", "hand": "left", "armor": 40}],
        )
        self.assertEqual(shield.left_fit, 3)
        self.assertEqual(statcalc.compute(shield).gear_defense, Decimal(47))

    def test_mage_grade_and_wand_fit_stack_as_flats(self):
        sheet = statcalc.sheet_from_equipped(
            classes=["Witcher"],
            items=[{"type": "Wand", "hand": "any", "damage": 10}],
        )
        # Witcher is grade 2. Wand fit is +5. Neither is a percent.
        self.assertEqual(sheet.class_damage, 2)
        self.assertEqual(sheet.right_fit, 1)
        self.assertEqual(statcalc.compute(sheet).gear_attack, Decimal(17))

    def test_paragon_spear_adds_grade_and_fit(self):
        sheet = statcalc.sheet_from_equipped(
            classes=["Novice"],
            items=[{"type": "Spear", "hand": "right", "damage": 0, "armor": 0}],
        )
        result = statcalc.compute(sheet)
        self.assertEqual(result.gear_attack, Decimal(6))
        self.assertEqual(result.gear_defense, Decimal(1))

    def test_extra_weapon_keeps_its_own_stars_inside_other_gear(self):
        sheet = statcalc.sheet_from_equipped(
            classes=["Grunt", "Adventurer"],
            items=[
                {"type": "Sword", "hand": "right", "damage": 10, "stars": 0},
                {"type": "Shield", "hand": "left", "armor": 10},
                {"type": "Axe", "hand": "any", "damage": 10, "stars": 2},
            ],
        )
        # Sword 10 + 5 fit. Axe 10 × 1.08 + 5 fit, parked in other gear.
        self.assertEqual(sheet.right_damage, Decimal(10))
        self.assertEqual(sheet.other_damage, Decimal("15.8"))
        self.assertEqual(statcalc.compute(sheet).gear_attack, Decimal("30.8"))

    def test_raider_grade_does_not_change_the_multiplier(self):
        sheet = statcalc.sheet_from_equipped(classes=["Adventurer"], race="Djinn", profile_atk=Decimal(1))
        result = statcalc.compute(sheet)
        self.assertEqual(result.attack_multiplier, Decimal(1))
        self.assertEqual(result.gear_attack, Decimal(5))
        self.assertEqual(result.gear_defense, Decimal(-1))

    def test_two_handed_weapon_is_not_counted_twice(self):
        sheet = statcalc.sheet_from_equipped(
            classes=["Caretaker"],
            items=[{"type": "Bow", "hand": "both", "damage": 100}],
        )
        self.assertEqual(statcalc.compute(sheet).gear_attack, Decimal(110))
        text = statcalc.card(sheet, "right_damage")
        self.assertIn("two-handed", text)
        self.assertLess(len(text), 1200)


class TestCogSurface(unittest.TestCase):
    def test_view_fits_in_one_message(self):
        import asyncio

        import discord

        from cogs.statcalc import StatCalcView

        async def build():
            view = StatCalcView(
                cog=None,
                author_id=1,
                target_id=1,
                hero_name="Example",
                sheet=statcalc.example_sheet(),
            )
            self.assertLessEqual(len(view.embed().description), 1200)
            self.assertEqual(
                [option.label for option in view.pick.options],
                ["Longsword damage", "Shield armor", "$rs attack", "$rs defense"],
            )
            buttons = [child for child in view.children if isinstance(child, discord.ui.Button)]
            self.assertEqual(len(buttons), 7)
            self.assertEqual([button.label for button in buttons[:4]], ["-10", "-1", "+1", "+10"])
            view.stop()

        asyncio.run(build())

    def test_command_is_registered_with_its_help(self):
        from cogs.statcalc import StatCalc

        command = StatCalc.statcalc
        self.assertEqual(command.name, "statcalc")
        self.assertIn("scalc", command.aliases)
        self.assertIn("$rs", command.help)
        self.assertIn("{prefix}statcalc", command.help)


if __name__ == "__main__":
    unittest.main()

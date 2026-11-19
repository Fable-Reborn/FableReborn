import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from PIL import Image

import random

from classes.equipment.definitions import (
    MATERIAL_LINES,
    MAX_IGNORED_OF_ATTACK,
    RARITIES,
)
from classes.equipment.economy import (
    craft_cost,
    is_tradable,
    all_recipe_keys,
    known_recipe_keys,
    modifier_adjustments,
    offensive_properties,
    preview_balances,
    recipe_progress,
    temper_cost,
    salvage_yield,
)
from classes.equipment.offense import resolve_effective_armor
from classes.equipment.generation import roll_crate, simulate, summarize_rewards
from classes.equipment.stats import (
    apply_component_bonus,
    contribution,
    quality_scale,
)
from classes.items import TWO_HANDED_ITEM_TYPES, ItemType
from classes.equipment.attunement import (
    ATTUNEMENT_CAP,
    XP_ADVENTURE,
    XP_BATTLE,
    XP_DRAGON_KILL,
    XP_RAID_WIN,
    XP_TOWER_FLOOR,
    refinement_cap,
    victory_award,
)
from classes.equipment.card import glow_colors, preview_loadout, render_armory
from classes.equipment.character_card import assign_hands, render_character, worn_totals
from classes.equipment.character_card_v2 import THEMES


class EquipmentBudgetTests(unittest.TestCase):
    def test_quality_ends_are_the_approved_band(self):
        self.assertEqual(Decimal("0.55"), quality_scale(1))
        self.assertEqual(Decimal("1"), quality_scale(100))

    def test_divine_is_rejected(self):
        with self.assertRaises(ValueError):
            contribution("divine", "guardian", 100)

    def test_offense_follows_archetype(self):
        guardian = contribution("legendary", "guardian", 100, 0)
        vanguard = contribution("legendary", "vanguard", 100, 0)
        slayer = contribution("legendary", "slayer", 100, 0)
        self.assertGreater(slayer[0], vanguard[0])
        self.assertGreater(vanguard[0], guardian[0])
        self.assertGreater(guardian[1], vanguard[1])
        self.assertGreater(vanguard[1], slayer[1])

    def test_refinement_keeps_the_archetype_ratio(self):
        base_offense, base_armor = contribution("magic", "guardian", 80, 0)
        refined_offense, refined_armor = contribution("magic", "guardian", 80, 5)
        self.assertEqual(
            base_offense / base_armor,
            refined_offense / refined_armor,
        )
        self.assertEqual(
            (refined_offense / base_offense).quantize(Decimal("0.0001")),
            Decimal("1.2000"),
        )

    def test_common_is_a_quarter_of_legendary(self):
        common = contribution("common", "slayer", 100, 0)
        legendary = contribution("legendary", "slayer", 100, 0)
        self.assertEqual(legendary[0] * Decimal("0.25"), common[0])

    def test_zero_gear_matches_the_old_total(self):
        damage, armor = apply_component_bonus(100, 40, 7, 9, 0, 0)
        self.assertEqual(Decimal("107"), damage)
        self.assertEqual(Decimal("49"), armor)

    def test_weapon_percent_does_not_scale_class_flats(self):
        damage, armor = apply_component_bonus(100, 40, 10, 7, Decimal("0.16"), 4)
        self.assertEqual(Decimal("126"), damage)
        self.assertEqual(Decimal("51"), armor)

    def test_weapon_hands_are_unchanged(self):
        self.assertEqual(
            {ItemType.Bow, ItemType.Scythe, ItemType.Mace},
            set(TWO_HANDED_ITEM_TYPES),
        )
        self.assertEqual("left", ItemType.Shield.get_hand().value)
        self.assertNotIn("divine", RARITIES)


class CrateRollTests(unittest.TestCase):
    def test_excluded_crates_award_nothing(self):
        rng = random.Random(1)
        for rarity in ("divine", "fortune", "mystery", "materials"):
            for _ in range(1000):
                self.assertIsNone(roll_crate(rarity, rng))

    def test_ordinary_pieces_are_unbound_and_unmodified(self):
        rng = random.Random(2)
        for rarity in ("common", "uncommon", "rare", "magic", "legendary"):
            for _ in range(400):
                roll = roll_crate(rarity, rng)
                self.assertIsNotNone(roll)
                self.assertGreaterEqual(sum(roll.materials.values()), 1)
                if roll.piece is None or roll.piece.fully_rolled:
                    continue
                self.assertLessEqual(len(roll.piece.modifier_ids), 1)
                self.assertFalse("fortified" in roll.piece.modifier_ids and roll.piece.archetype == "slayer")
                self.assertFalse(
                    "weapon_amplification" in roll.piece.modifier_ids and roll.piece.archetype == "guardian"
                )
                if roll.piece.archetype == "guardian":
                    self.assertFalse(set(roll.piece.modifier_ids) & {"sunder", "breakthrough"})
                self.assertFalse(roll.piece.fully_rolled)
                self.assertEqual(rarity, roll.piece.rarity)
                self.assertIn(roll.piece.archetype, ("guardian", "slayer", "vanguard"))
                self.assertTrue(set(roll.materials) <= set(MATERIAL_LINES[roll.piece.archetype]))
                self.assertTrue(1 <= roll.piece.quality <= 100)

    def test_bulk_summary_lists_quality_and_sets(self):
        text = summarize_rewards(
            [
                {"item": {"quality": 40, "archetype": "guardian", "fully_rolled": False}, "materials": {}},
                {"item": {"quality": 90, "archetype": "slayer", "fully_rolled": False}, "materials": {}},
                {"item": {"quality": 40, "archetype": "vanguard", "fully_rolled": False}, "materials": {}},
            ]
        )
        self.assertIn("Armory: 3 piece(s)", text)
        self.assertIn("- 40 (x2)", text)
        self.assertIn("- 90", text)
        self.assertIn("- Guardian (x1)", text)
        self.assertIn("- Slayer (x1)", text)
        self.assertIn("- Vanguard (x1)", text)

    def test_discoveries_follow_the_archetype_limits(self):
        rng = random.Random(3)
        seen = set()
        for _ in range(40000):
            roll = roll_crate("legendary", rng)
            piece = roll.piece
            if piece is None or not piece.fully_rolled:
                continue
            seen.add(piece.archetype)
            self.assertGreaterEqual(piece.quality, 70)
            self.assertEqual(2, len(piece.modifier_ids))
            self.assertEqual(len(piece.modifier_ids), len(set(piece.modifier_ids)))
            if piece.archetype == "guardian":
                self.assertEqual(("fortified", "vitality"), piece.modifier_ids)
                self.assertFalse(set(piece.modifier_ids) & {"sunder", "breakthrough"})
            if piece.archetype == "slayer":
                self.assertNotIn("fortified", piece.modifier_ids)
                self.assertFalse(set(piece.modifier_ids) & {"fortified"})
        self.assertEqual({"guardian", "slayer", "vanguard"}, seen)

    def test_rates_stay_near_the_baseline(self):
        report = simulate("legendary", 20000, random.Random(4))
        self.assertGreater(report["discoveries"], 40)
        self.assertLess(report["discoveries"], 140)
        self.assertGreater(report["pieces"], 5400)
        self.assertLess(report["pieces"], 6800)
        common = simulate("common", 20000, random.Random(5))
        self.assertGreater(common["pieces"], 1400)
        self.assertLess(common["pieces"], 1800)
        self.assertEqual(0, common["discoveries"])
        rough = {"bog_iron", "cinder_ore", "river_bronze"}
        self.assertTrue(set(common["materials"]) <= rough | {"wardsteel", "razorsteel", "oathsteel", "aegisheart", "wyrmglass", "sunstone"})
        for material_id, amount in common["materials"].items():
            if material_id not in rough:
                self.assertEqual(0, amount)
            else:
                self.assertGreater(amount, 0)
        self.assertGreater(common["quality_mean"], 35)
        self.assertLess(common["quality_mean"], 55)


class EconomyTests(unittest.TestCase):
    def test_salvage_is_always_a_loss(self):
        for rarity in ("common", "uncommon", "rare", "magic", "legendary"):
            for archetype in ("guardian", "slayer", "vanguard"):
                cost = craft_cost(rarity, archetype)
                for quality in (1, 50, 100):
                    gained = salvage_yield(rarity, archetype, quality)
                    for material_id, amount in gained.items():
                        self.assertLess(amount, cost[material_id])
                    self.assertTrue(gained)

    def test_discovered_recipes_hide_unknown_patterns(self):
        known = known_recipe_keys()
        self.assertEqual("head:guardian:common", known[0])
        self.assertIn("chest:guardian:common", known)
        self.assertIn("feet:vanguard:common", known)
        self.assertEqual(12, len(known))
        found = known_recipe_keys({"chest:guardian:rare"})
        self.assertIn("chest:guardian:rare", found)
        self.assertNotIn("chest:guardian:legendary", found)
        progress = recipe_progress({"bog_iron": 12}, {"bog_iron": 4})
        self.assertEqual("ready", recipe_progress({"bog_iron": 12}, {"bog_iron": 12})["state"])
        self.assertEqual("close", progress["state"])
        self.assertEqual("short", recipe_progress({"bog_iron": 12, "wardsteel": 8, "aegisheart": 2}, {})["state"])
        self.assertEqual(60, len(all_recipe_keys()))
        sample = preview_balances()
        self.assertEqual("ready", recipe_progress(craft_cost("common", "slayer"), sample)["state"])
        self.assertEqual("close", recipe_progress(craft_cost("rare", "slayer"), sample)["state"])
        self.assertEqual("short", recipe_progress(craft_cost("legendary", "slayer"), sample)["state"])

    def test_binding_rules(self):
        self.assertTrue(is_tradable({"bound": False, "fully_rolled": False, "refinement": 0}))
        self.assertFalse(is_tradable({"bound": True, "fully_rolled": False, "refinement": 0}))
        self.assertFalse(is_tradable({"bound": False, "fully_rolled": True, "refinement": 0}))
        self.assertFalse(is_tradable({"bound": False, "fully_rolled": False, "refinement": 1}))

    def test_refinement_cannot_make_guardian_a_slayer(self):
        chest_armor = contribution("legendary", "guardian", 100)[1]
        shared = sum(
            contribution("legendary", "guardian", 100, 0, slot)[1]
            for slot in ("head", "legs", "feet")
        )
        self.assertEqual(chest_armor, shared)
        self.assertLess(contribution("legendary", "guardian", 100, 0, "head")[1], chest_armor)
        guardian = contribution("legendary", "guardian", 100, 5)[0]
        slayer = contribution("legendary", "slayer", 100, 0)[0]
        weapon_pct, armor, health = modifier_adjustments(18, ["weapon_amplification", "fortified", "vitality"])
        self.assertLess(guardian + weapon_pct, slayer)
        self.assertEqual(Decimal("1.08"), armor)
        self.assertEqual(75, health)
        self.assertIn("aegisheart", temper_cost("guardian", 5))


class OffenseTests(unittest.TestCase):
    def test_properties_cap_and_ignore_duplicates(self):
        penetration, chance, bypass = offensive_properties(
            ["sunder", "sunder", "breakthrough", "breakthrough"]
        )
        self.assertEqual(Decimal("0.55"), penetration)
        self.assertEqual(Decimal("0.10"), chance)
        self.assertEqual(Decimal("0.15"), bypass)
        stacked = offensive_properties(["sunder", "sunder"])
        self.assertEqual(Decimal("0.55"), stacked[0])
        self.assertLessEqual(
            offensive_properties(["sunder"] * 5)[0],
            Decimal("0.55"),
        )

    def test_ignored_armor_cannot_grow_with_the_defender(self):
        attack = Decimal("3509")
        huge = resolve_effective_armor(attack, Decimal("20000"), Decimal("0.55"))
        modest = resolve_effective_armor(attack, Decimal("3900"), Decimal("0.55"))
        self.assertEqual(huge.ignored, attack * MAX_IGNORED_OF_ATTACK)
        self.assertEqual(modest.ignored, Decimal("3900") * Decimal("0.55"))
        self.assertFalse(huge.breakthrough)

    def test_armor_ignoring_hits_do_not_break_through(self):
        class Always:
            def random(self):
                return 0.0

        result = resolve_effective_armor(
            5000,
            3900,
            Decimal("0.55"),
            Decimal("0.10"),
            Decimal("0.15"),
            Always(),
            ignore_armor=True,
        )
        self.assertEqual(Decimal("3900"), result.armor)
        self.assertFalse(result.breakthrough)

    def test_breakthrough_is_uncommon_and_one_shot(self):
        procs = 0
        trials = 5000
        rng = random.Random(11)
        for _ in range(trials):
            result = resolve_effective_armor(
                3509,
                3900,
                Decimal("0.55"),
                Decimal("0.10"),
                Decimal("0.15"),
                rng,
            )
            procs += result.breakthrough
            if result.breakthrough:
                self.assertEqual(result.ignored, Decimal("3509") * MAX_IGNORED_OF_ATTACK)
        rate = procs / trials
        self.assertGreater(rate, 0.08)
        self.assertLess(rate, 0.12)

    def test_penetration_leaves_the_reflection_percent_and_shrinks_its_base(self):
        attack = Decimal("3509")
        armor = Decimal("3900")
        reflection = Decimal("0.28")
        plain_blocked = min(attack, armor)
        pierced = resolve_effective_armor(attack, armor, Decimal("0.55"))
        pierced_blocked = min(attack, pierced.armor)
        self.assertLess(pierced_blocked, plain_blocked)
        self.assertLess(pierced_blocked * reflection, plain_blocked * reflection)
        self.assertEqual(reflection, Decimal("0.28"))
        self.assertGreater(max(attack - pierced.armor, Decimal("10")), Decimal("10"))

    def test_sunder_wins_against_a_reflect_tank_and_loses_to_a_wall(self):
        def exchange(attacker, defender, reflect, trials=4000):
            rng = random.Random(11)
            dealt = taken = Decimal("0")
            for _ in range(trials):
                raw = Decimal(attacker[0]) + Decimal(rng.randint(0, 100))
                result = resolve_effective_armor(
                    raw, defender[1], Decimal("0.55"), Decimal("0.10"), Decimal("0.15"), rng
                )
                dealt += max(raw - result.armor, Decimal("10"))
                taken += min(raw, result.armor) * reflect
                reply = Decimal(defender[0]) + Decimal(rng.randint(0, 100))
                taken += max(reply - Decimal(attacker[1]), Decimal("10"))
            return dealt, taken

        reflect_dealt, reflect_taken = exchange((5000, 1600), (2800, 5200), Decimal("0.28"))
        self.assertGreater(reflect_dealt, reflect_taken)
        wall_dealt, wall_taken = exchange((5000, 1600), (2200, 7000), Decimal("0.28"))
        self.assertGreater(wall_taken, wall_dealt)


class AttunementTests(unittest.TestCase):
    def test_one_victory_matches_a_soulbound_battle(self):
        first = victory_award(0, 8000, 10000)
        self.assertEqual(XP_BATTLE, first["gain"])
        self.assertTrue(first["binds"])
        second = victory_award(first["level"], 8000, 10000)
        self.assertEqual(XP_BATTLE, second["gain"])
        self.assertFalse(second["binds"])

    def test_soulbound_deeds_use_the_weapon_point_values(self):
        self.assertEqual(10, XP_ADVENTURE)
        self.assertEqual(15, XP_TOWER_FLOOR)
        self.assertEqual(20, XP_RAID_WIN)
        self.assertEqual(25, XP_DRAGON_KILL)
        self.assertEqual(XP_ADVENTURE, victory_award(0, amount=XP_ADVENTURE)["gain"])
        self.assertEqual(XP_DRAGON_KILL, victory_award(40, amount=XP_DRAGON_KILL)["gain"])
        self.assertGreater(XP_DRAGON_KILL, XP_RAID_WIN)
        self.assertGreater(XP_RAID_WIN, XP_TOWER_FLOOR)
        self.assertGreater(XP_TOWER_FLOOR, XP_ADVENTURE)

    def test_trivial_and_unfinished_fights_grant_nothing(self):
        self.assertEqual(0, victory_award(0, 1000, 10000)["gain"])
        self.assertEqual(0, victory_award(0, 0, 10000)["gain"])
        self.assertEqual("trivial", victory_award(2, 4999, 10000)["reason"])
        self.assertEqual(XP_BATTLE, victory_award(2, 5000, 10000)["gain"])

    def test_the_cap_stops_further_victories(self):
        self.assertEqual(2500, ATTUNEMENT_CAP)
        almost = victory_award(2490, amount=XP_DRAGON_KILL)
        self.assertEqual(10, almost["gain"])
        self.assertEqual(ATTUNEMENT_CAP, almost["level"])
        done = victory_award(ATTUNEMENT_CAP, 20000, 10000)
        self.assertEqual(0, done["gain"])
        self.assertEqual("complete", done["reason"])

    def test_attunement_opens_two_refinement_levels(self):
        self.assertEqual(5, refinement_cap(0))
        self.assertEqual(5, refinement_cap(ATTUNEMENT_CAP - 1))
        self.assertEqual(7, refinement_cap(ATTUNEMENT_CAP))
        offense, armor = contribution("legendary", "slayer", 100, 7)
        capped = contribution("legendary", "slayer", 100, 5)
        self.assertGreater(offense, capped[0])
        self.assertGreater(armor, capped[1])
        self.assertIn("wyrmglass", temper_cost("slayer", 7))


class CharacterSheetTests(unittest.TestCase):
    def test_starforge_and_soulbound_raise_the_shown_weapon(self):
        bow = {
            "id": 4,
            "name": "Longbow",
            "type": "Bow",
            "hand": "both",
            "damage": 200,
            "armor": 0,
            "base_damage": 200,
            "base_armor": 0,
            "effective_damage": 280,
            "effective_armor": 0,
            "progression_bonus_pct": 0.40,
            "starforge_stars": 10,
            "soulbound_level": 0,
        }
        totals = worn_totals({}, [bow])
        self.assertEqual(280, totals["weapon_damage"])

    def test_a_two_handed_weapon_is_counted_once(self):
        bow = {"id": 4, "name": "Longbow", "type": "Bow", "hand": "both", "damage": 80, "armor": 0}
        hands = assign_hands([bow])
        self.assertIs(hands["right"], hands["left"])
        totals = worn_totals({"chest": {"offense_value": 0.16, "defense_value": 4, "modifiers": []}}, [bow])
        self.assertEqual(80, totals["weapon_damage"])
        self.assertEqual(0.16, totals["blessing"])

    def test_sword_and_shield_add_together(self):
        sword = {"id": 1, "name": "Blade", "type": "Sword", "hand": "right", "damage": 50, "armor": 0}
        shield = {"id": 2, "name": "Guard", "type": "Shield", "hand": "left", "damage": 0, "armor": 40}
        totals = worn_totals({}, [sword, shield])
        self.assertEqual(50, totals["weapon_damage"])
        self.assertEqual(40, totals["weapon_armor"])

    def test_layout_themes_are_available(self):
        self.assertEqual({"void", "royal", "frost", "dusk"}, set(THEMES))

    def test_character_sheet_is_a_png(self):
        png = render_character(preview_loadout(), [], focus="totals", title="Preview")
        self.assertTrue(png.startswith(b"\x89PNG"))


class ArmoryCardTests(unittest.TestCase):
    def test_empty_armory_is_a_png(self):
        png = render_armory({})
        self.assertTrue(png.startswith(b"\x89PNG"))
        image = Image.open(__import__("io").BytesIO(png))
        self.assertEqual((1120, 720), image.size)

    def test_weapons_extend_the_same_card(self):
        spear = {"id": 1, "name": "Ashen Spear", "type": "Spear", "hand": "right", "damage": 40, "armor": 0}
        png = render_armory(preview_loadout(), weapons=[spear], focus="right", title="Armory")
        self.assertTrue(png.startswith(b"\x89PNG"))
        image = Image.open(__import__("io").BytesIO(png))
        self.assertEqual(1120, image.size[0])
        self.assertGreater(image.size[1], 720)

    def test_enchantment_glow_changes_the_card(self):
        plain = render_armory(preview_loadout())
        glowing = dict(preview_loadout())
        glowing["chest"] = dict(glowing["chest"])
        glowing["chest"]["modifiers"] = [{"modifier_id": "fortified"}]
        self.assertNotEqual(plain, render_armory(glowing))

    def test_unknown_modifier_still_has_a_glow(self):
        colors = glow_colors([{"modifier_id": "future_enchantment"}])
        self.assertEqual([(176, 120, 255)], colors)

    def test_preview_image_can_be_written(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "fable-armory-preview.png"
            path.write_bytes(render_armory(preview_loadout(), title="Armory preview"))
            self.assertGreater(path.stat().st_size, 1000)


class ForgeTests(unittest.TestCase):
    def test_refine_cost_rises_and_chance_falls_with_quality(self):
        from classes.equipment.economy import refine_step

        low = refine_step("slayer", 50)
        high = refine_step("slayer", 97)
        self.assertEqual(low["cost"], {"cinder_ore": 4})
        self.assertEqual(low["chance"], 1.0)
        self.assertEqual(high["cost"], {"cinder_ore": 10, "razorsteel": 3, "wyrmglass": 1})
        self.assertEqual(high["chance"], 0.5)
        self.assertGreater(high["gold"], low["gold"])
        self.assertGreater(high["pity"], 0)
        self.assertIsNone(refine_step("slayer", 100))

    def test_temper_stars_work_like_starforge(self):
        from classes.equipment.economy import temper_step

        first = temper_step("guardian", 1)
        last = temper_step("guardian", 7)
        self.assertGreater(first["chance"], last["chance"])
        self.assertGreater(last["gold"], first["gold"])
        self.assertGreater(last["pity"], first["pity"])
        self.assertIn("aegisheart", last["cost"])

    def test_inscribe_is_hard_with_pity(self):
        from classes.equipment.economy import inscribe_step

        step = inscribe_step("vanguard")
        self.assertEqual(step["chance"], 0.35)
        self.assertEqual(step["pity"], 3)
        self.assertIn("sunstone", step["cost"])

    def test_trade_is_three_for_one_within_a_tier(self):
        from classes.equipment.economy import trade_result

        self.assertEqual(trade_result("bog_iron", "slayer", 10), ("cinder_ore", 3, 9))
        self.assertEqual(trade_result("aegisheart", "vanguard", 3), ("sunstone", 1, 3))
        self.assertIsNone(trade_result("bog_iron", "guardian", 9))
        self.assertIsNone(trade_result("bog_iron", "slayer", 2))

    def test_every_armory_cover_is_registered(self):
        from classes.equipment.chronicle import THEMES, theme_for

        self.assertTrue({"chronicle", "anvil", "wyrmscale", "maw", "oathbound"} <= set(THEMES))
        self.assertEqual(theme_for("anvil").label, "Thorne's Anvil")
        self.assertEqual(theme_for("missing").key, "chronicle")

    def test_forge_result_shows_each_change_once(self):
        from classes.equipment.forge_result import banner_text, stars, strike_banner

        before = {"name": "Razor Cuirass", "quality": 62, "stars": 3, "enchants": ["Fortified"]}
        refined = strike_banner(
            "refine", "refined",
            {"success": True, "pity_used": True, "quality": 63},
            before, quote="\"Enough.\"",
        )
        self.assertEqual((refined["tone"], refined["title"], refined["stat"]), ("pity", "Refined", "quality"))
        self.assertEqual(refined["delta"], "Quality **62 → 63** · Standard")
        self.assertEqual(banner_text(refined).count("62 → 63"), 1)

        tempered = strike_banner(
            "temper", "tempered",
            {"success": True, "pity_used": False, "refinement": 4, "newly_bound": True},
            before, quote="\"It took.\"",
        )
        self.assertEqual(tempered["delta"], f"Temper **+3 → +4** {stars(4)}")
        self.assertIn("bound it to you", tempered["note"])

        held = strike_banner(
            "temper", "tempered",
            {"success": False, "refinement": 6, "temper_fails": 4, "pity": 4},
            {"name": "Razor Cuirass", "quality": 90, "stars": 6, "enchants": []},
            quote="\"Again.\"",
        )
        self.assertEqual(held["tone"], "miss")
        self.assertEqual(held["delta"], f"Temper +6 {stars(6)} · held")

        inscribed = strike_banner(
            "inscribe", "inscribed",
            {"success": False, "fails": 1, "pity": 3},
            before, quote="\"Not today.\"", enchant="Sunder",
        )
        self.assertEqual(inscribed["delta"], "Enchant Fortified · Sunder did not take")

        poor = strike_banner("refine", "poor", {"short": "gold", "gold": 10000}, before, quote="\"Coal isn't free.\"")
        self.assertEqual((poor["tone"], poor["stat"], poor["note"]), ("blocked", None, "Nothing was spent."))

    def test_dragon_tiers_follow_stage_levels(self):
        from classes.equipment.economy import dragon_tier, roll_dragon_materials

        self.assertEqual(dragon_tier(1)[1], "Frostbite Wyrm")
        self.assertEqual(dragon_tier(20)[1], "Absolute Zero")
        self.assertEqual(dragon_tier(34)[1], "Void Tyrant")
        self.assertEqual(dragon_tier(50)[1], "The Abyssal Maw")
        low = roll_dragon_materials(3, "guardian", random.Random(1))
        self.assertEqual(set(low), {"bog_iron"})
        high = roll_dragon_materials(40, "vanguard", random.Random(1))
        self.assertEqual(high["river_bronze"], 4)
        self.assertEqual(high["oathsteel"], 2)

    def test_forge_animation_is_a_looping_gif(self):
        import io

        from classes.equipment.forge_art import anvil_gif

        image = Image.open(io.BytesIO(anvil_gif()))
        self.assertEqual(image.format, "GIF")
        self.assertGreater(image.n_frames, 3)


if __name__ == "__main__":
    unittest.main()

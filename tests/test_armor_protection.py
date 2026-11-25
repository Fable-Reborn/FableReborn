"""Armor locks, worn-piece protection, Salvage All, armory filters, sale DMs, trade materials."""
from __future__ import annotations

import unittest
from collections import defaultdict
from types import SimpleNamespace
from unittest.mock import AsyncMock

import discord

from tests.equipment_fakes import FakeArmoryDB, FakePool, piece

import cogs.profile as profile
from classes.equipment import protection
from classes.equipment.economy import salvage_yield
from classes.equipment.repository import (
    MASS_SALVAGE_LIMIT,
    SCHEMA_STATEMENTS,
    buy_listing,
    list_piece,
    move_piece,
    salvage_many,
    salvage_piece,
    set_piece_lock,
)

OWNER = 111
OTHER = 222


class LockTests(unittest.IsolatedAsyncioTestCase):
    def test_schema_adds_lock_column_safely(self):
        self.assertTrue(
            any("ADD COLUMN IF NOT EXISTS locked BOOLEAN NOT NULL DEFAULT FALSE" in s for s in SCHEMA_STATEMENTS)
        )

    async def test_lock_and_unlock(self):
        db = FakeArmoryDB([piece()])
        status, item = await set_piece_lock(db, OWNER, 7, True)
        self.assertEqual("locked", status)
        self.assertTrue(db.items[7]["locked"])
        self.assertEqual("already", (await set_piece_lock(db, OWNER, 7, True))[0])
        self.assertEqual("unlocked", (await set_piece_lock(db, OWNER, 7, False))[0])
        self.assertFalse(db.items[7]["locked"])
        self.assertEqual(["lock", "unlock"], db.events)

    async def test_cannot_lock_someone_elses_piece(self):
        db = FakeArmoryDB([piece(owner=OTHER)])
        self.assertEqual("missing", (await set_piece_lock(db, OWNER, 7, True))[0])
        self.assertFalse(db.items[7]["locked"])

    async def test_listed_piece_must_come_down_before_locking(self):
        db = FakeArmoryDB([piece()], market={7: (OWNER, 500)})
        self.assertEqual("listed", (await set_piece_lock(db, OWNER, 7, True))[0])
        self.assertFalse(db.items[7]["locked"])

    async def test_worn_piece_can_be_locked(self):
        db = FakeArmoryDB([piece()], worn={7})
        self.assertEqual("locked", (await set_piece_lock(db, OWNER, 7, True))[0])


class ProtectionTests(unittest.IsolatedAsyncioTestCase):
    async def test_locked_or_worn_piece_cannot_be_salvaged(self):
        for kwargs, expected in (({"items": [piece(locked=True)]}, "locked"), ({"items": [piece()], "worn": {7}}, "equipped")):
            db = FakeArmoryDB(kwargs["items"], worn=kwargs.get("worn", ()))
            self.assertEqual((expected, None), await salvage_piece(db, OWNER, 7))
            self.assertIn(7, db.items)
            self.assertEqual({}, db.materials)

    async def test_unprotected_piece_salvages(self):
        db = FakeArmoryDB([piece()])
        status, result = await salvage_piece(db, OWNER, 7)
        self.assertEqual("salvaged", status)
        self.assertEqual(salvage_yield("rare", "slayer", 60), result["materials"])
        self.assertNotIn(7, db.items)

    async def test_locked_or_worn_piece_cannot_be_listed(self):
        db = FakeArmoryDB([piece(locked=True), piece(item_id=8)], worn={8})
        self.assertEqual("locked", (await list_piece(db, OWNER, 7, 100))[0])
        self.assertEqual("equipped", (await list_piece(db, OWNER, 8, 100))[0])
        self.assertEqual({}, db.market)
        self.assertIn(8, db.worn)

    async def test_locked_or_worn_piece_cannot_be_given(self):
        db = FakeArmoryDB([piece(locked=True), piece(item_id=8)], worn={8})
        self.assertEqual("locked", await move_piece(db, 7, OWNER, OTHER))
        self.assertEqual("equipped", await move_piece(db, 8, OWNER, OTHER))
        self.assertEqual(OWNER, db.items[7]["owner_id"])
        self.assertEqual(OWNER, db.items[8]["owner_id"])

    async def test_unprotected_piece_can_be_given(self):
        db = FakeArmoryDB([piece()])
        self.assertEqual("moved", await move_piece(db, 7, OWNER, OTHER))
        self.assertEqual(OTHER, db.items[7]["owner_id"])

    async def test_buying_a_listing_the_seller_locked_or_wore_charges_nothing(self):
        for setup in ("locked", "worn"):
            db = FakeArmoryDB(
                [piece(locked=setup == "locked")],
                worn={7} if setup == "worn" else (),
                market={7: (OWNER, 500)},
                money={OTHER: 1000, OWNER: 0},
            )
            status, _ = await buy_listing(db, OTHER, 7, expected_price=500)
            self.assertEqual("bound", status, setup)
            self.assertEqual({OTHER: 1000, OWNER: 0}, db.money, setup)
            self.assertEqual(OWNER, db.items[7]["owner_id"], setup)
            self.assertNotIn(7, db.market, setup)

    async def test_normal_purchase_still_works_and_reports_seller(self):
        db = FakeArmoryDB([piece()], market={7: (OWNER, 500)}, money={OTHER: 1000, OWNER: 0})
        status, result = await buy_listing(db, OTHER, 7, expected_price=500)
        self.assertEqual("bought", status)
        self.assertEqual(OWNER, result["seller_id"])
        self.assertEqual({OTHER: 500, OWNER: 500}, db.money)
        self.assertEqual(OTHER, db.items[7]["owner_id"])


class SalvageAllTests(unittest.IsolatedAsyncioTestCase):
    def pieces(self):
        return [
            piece(1),
            piece(2, rarity="common", archetype="guardian", slot="chest"),
            piece(3, locked=True),
            piece(4),  # worn
            piece(5),  # listed
            piece(6, refinement=2),
            piece(7, fully_rolled=True, rarity="legendary"),
            piece(8, owner=OTHER),
        ]

    async def test_skips_every_protected_piece(self):
        db = FakeArmoryDB(self.pieces(), worn={4}, market={5: (OWNER, 10)})
        summary = await salvage_many(db, OWNER, [1, 2, 3, 4, 5, 6, 7, 8, 999])
        self.assertEqual(2, len(summary["salvaged"]))
        self.assertEqual({3, 4, 5, 6, 7, 8}, set(db.items))
        self.assertEqual(
            {"locked": 1, "equipped": 1, "listed": 1, "tempered": 1, "discovery": 1, "missing": 2},
            summary["skipped"],
        )
        expected = {}
        for row in (piece(1), piece(2, rarity="common", archetype="guardian")):
            for material_id, amount in salvage_yield(row["rarity"], row["archetype"], row["quality"]).items():
                expected[material_id] = expected.get(material_id, 0) + amount
        self.assertEqual(expected, summary["materials"])
        self.assertEqual({(OWNER, k): v for k, v in expected.items()}, db.materials)

    async def test_running_twice_pays_once(self):
        db = FakeArmoryDB([piece(1), piece(2)])
        await salvage_many(db, OWNER, [1, 2])
        paid = dict(db.materials)
        again = await salvage_many(db, OWNER, [1, 2])
        self.assertEqual([], again["salvaged"])
        self.assertEqual({"missing": 2}, again["skipped"])
        self.assertEqual(paid, db.materials)

    async def test_duplicate_ids_count_once_and_limit_applies(self):
        db = FakeArmoryDB([piece(1)])
        summary = await salvage_many(db, OWNER, [1, 1, 1])
        self.assertEqual(1, len(summary["salvaged"]))
        db = FakeArmoryDB([piece(i) for i in range(1, MASS_SALVAGE_LIMIT + 6)])
        summary = await salvage_many(db, OWNER, list(range(1, MASS_SALVAGE_LIMIT + 6)))
        self.assertEqual(MASS_SALVAGE_LIMIT, len(summary["salvaged"]))
        self.assertEqual(5, len(db.items))

    async def test_empty_list_does_nothing(self):
        db = FakeArmoryDB([piece(1)])
        self.assertEqual({"salvaged": [], "materials": {}, "skipped": {}}, await salvage_many(db, OWNER, []))

    def test_plan_matches_database_rules_and_filters(self):
        rows = [
            {**piece(1), "equipped": False, "listed": False},
            {**piece(2, rarity="common"), "equipped": False, "listed": False},
            {**piece(3), "equipped": True, "listed": False},
            {**piece(4, locked=True), "equipped": False, "listed": False},
        ]
        plan = protection.plan_mass_salvage(rows)
        self.assertEqual([1, 2], plan["ids"])
        self.assertEqual({"rare": 1, "common": 1}, plan["by_rarity"])
        self.assertIn("Pieces: 1 Common, 1 Rare.", protection.mass_salvage_confirm_text(plan, "x"))
        self.assertEqual({"equipped": 1, "locked": 1}, plan["skipped"])
        wanted, unknown = protection.parse_salvage_filters("common")
        self.assertEqual([], unknown)
        self.assertEqual([2], protection.plan_mass_salvage(rows, wanted)["ids"])

    def test_filter_words(self):
        wanted, unknown = protection.parse_salvage_filters("Common, razor helms Guardian sabatons wat")
        self.assertEqual({"common"}, wanted["rarity"])
        self.assertEqual({"slayer", "guardian"}, wanted["archetype"])
        self.assertEqual({"head", "feet"}, wanted["slot"])
        self.assertEqual(["wat"], unknown)

    def test_messages(self):
        plan = {"ids": [1, 2], "skipped": {"locked": 1, "equipped": 2}, "materials": {}}
        text = protection.mass_salvage_confirm_text(plan, "stuff")
        self.assertIn("Salvage 2 pieces?", text)
        self.assertIn("cannot be undone", text)
        self.assertIn("1 locked", text)
        self.assertIn("2 worn", text)
        self.assertIn("Nothing to salvage", protection.mass_salvage_nothing_text({"locked": 3}))
        self.assertIn("Nothing matches", protection.mass_salvage_nothing_text({}))
        done = protection.mass_salvage_result_text({"salvaged": ["a"], "skipped": {}, "materials": {}}, "x")
        self.assertIn("**1** piece and recover x", done)


class ArmoryMenuTests(unittest.IsolatedAsyncioTestCase):
    def options(self, item):
        view = SimpleNamespace(selected_item=lambda: item, catalog="armor")
        return {option.value: option for option in profile.ArmoryActionSelect(view).options}

    def menu_item(self, **extra):
        item = {
            "armory_kind": "armor", "armory_key": "armor:7", "id": 7, "name": "Razor Helm",
            "equipped": False, "locked": False, "rarity": "Rare", "archetype": "slayer",
            "slot": "head", "value": 60, "refinement": 0, "fully_rolled": False,
        }
        item.update(extra)
        return item

    async def test_lock_option_flips_with_state(self):
        self.assertIn("armor_lock", self.options(self.menu_item()))
        unlocked_menu = self.options(self.menu_item(locked=True))
        self.assertIn("armor_unlock", unlocked_menu)
        self.assertIn("unlock it first", unlocked_menu["salvage"].description)

    def test_filter_labels_name_the_class(self):
        labels = {value: label for value, label, _ in profile.ARMORY_GEAR_FILTER_OPTIONS}
        self.assertEqual("Razor (Slayer)", labels["line:slayer"])
        self.assertEqual("Aegis (Guardian)", labels["line:guardian"])
        self.assertEqual("Oath (Vanguard)", labels["line:vanguard"])
        self.assertEqual("Has enchantment", labels["enchant:any"])
        self.assertLessEqual(len(profile.ARMORY_GEAR_FILTER_OPTIONS), 25)

    def test_has_enchantment_filter(self):
        plain = {"archetype": "slayer", "slot": "head", "rarity": "rare", "enchantments": "None", "has_enchantment": False}
        fancy = {**plain, "enchantments": "Sunder", "has_enchantment": True}
        self.assertFalse(profile.armory_item_matches_gear_filters(plain, {"enchant:any"}))
        self.assertTrue(profile.armory_item_matches_gear_filters(fancy, {"enchant:any"}))
        self.assertTrue(profile.armory_item_matches_gear_filters(fancy, {"enchant:any", "line:slayer"}))
        self.assertFalse(profile.armory_item_matches_gear_filters(fancy, {"enchant:any", "line:guardian"}))
        # Rows without the flag fall back to the text.
        self.assertTrue(profile.armory_item_has_enchantment({"enchantments": "Fortified"}))
        self.assertFalse(profile.armory_item_has_enchantment({"enchantments": "None"}))

    def test_equipped_first_only_without_filters(self):
        items = [{"id": 1, "equipped": False}, {"id": 2, "equipped": True}, {"id": 3, "equipped": False}, {"id": 4, "equipped": True}]
        first = profile.armory_sort_equipped_first(items, catalog="armor", filters=set())
        self.assertEqual([2, 4, 1, 3], [item["id"] for item in first])
        kept = profile.armory_sort_equipped_first(items, catalog="armor", filters={"rarity:rare"})
        self.assertEqual([1, 2, 3, 4], [item["id"] for item in kept])
        weapons = profile.armory_sort_equipped_first(items, catalog="weapons", filters=set())
        self.assertEqual([1, 2, 3, 4], [item["id"] for item in weapons])

    def test_menu_refuses_salvage_of_locked_or_worn_before_asking(self):
        self.assertEqual("locked", profile.armory_salvage_blocker({"locked": True, "equipped": True}))
        self.assertEqual("equipped", profile.armory_salvage_blocker({"equipped": True}))
        self.assertIsNone(profile.armory_salvage_blocker({}))
        self.assertIn("locked", profile.armory_salvage_result("locked", None))
        self.assertIn("wearing", profile.armory_salvage_result("equipped", None))


def fake_armory(db, *, open_=True):
    cog = SimpleNamespace(available=open_)
    bot = SimpleNamespace(pool=FakePool(db), get_cog=lambda name: cog if name == "Equipment" else None)
    view = SimpleNamespace(
        ctx=SimpleNamespace(author=SimpleNamespace(id=OWNER), alt_invoker_id=None, bot=bot),
        refresh_from_db=AsyncMock(),
        redraw_message=AsyncMock(),
    )
    view._equipment_open = lambda: profile.ArmoryPaginatorView._equipment_open(view)
    view.salvage_all_armor = lambda ids: profile.ArmoryPaginatorView.salvage_all_armor(view, ids)
    return view


class FakeInteraction:
    def __init__(self, user_id=OWNER):
        self.user = SimpleNamespace(id=user_id)
        self.sent, self.edits, self.original = [], [], []
        outer = self

        class Response:
            def is_done(self):
                return bool(outer.sent or outer.edits)

            async def send_message(self, content=None, **kwargs):
                outer.sent.append(content)

            async def edit_message(self, **kwargs):
                outer.edits.append(kwargs)

        self.response = Response()

    async def edit_original_response(self, **kwargs):
        self.original.append(kwargs)


class SalvageAllViewTests(unittest.IsolatedAsyncioTestCase):
    async def test_confirm_runs_once_and_refreshes(self):
        db = FakeArmoryDB([piece(1), piece(2, locked=True)])
        armory = fake_armory(db)
        view = profile.ArmorySalvageAllConfirmView(armory, [1, 2])
        click = FakeInteraction()
        await view.confirm.callback(click)
        self.assertEqual({2}, set(db.items))
        self.assertIn("break down **1** piece", click.original[-1]["content"])
        self.assertIn("1 locked", click.original[-1]["content"])
        armory.refresh_from_db.assert_awaited_once()
        again = FakeInteraction()
        await view.confirm.callback(again)
        self.assertEqual(["Already handled."], again.sent)

    async def test_cancel_and_strangers(self):
        db = FakeArmoryDB([piece(1)])
        view = profile.ArmorySalvageAllConfirmView(fake_armory(db), [1])
        stranger = FakeInteraction(OTHER)
        self.assertFalse(await view.interaction_check(stranger))
        await view.cancel.callback(FakeInteraction())
        await view.confirm.callback(FakeInteraction())
        self.assertIn(1, db.items)

    async def test_closed_armory_salvages_nothing(self):
        db = FakeArmoryDB([piece(1)])
        view = profile.ArmorySalvageAllConfirmView(fake_armory(db, open_=False), [1])
        click = FakeInteraction()
        await view.confirm.callback(click)
        self.assertIn("closed", click.original[-1]["content"])
        self.assertIn(1, db.items)


class SaleNotificationTests(unittest.IsolatedAsyncioTestCase):
    def bot(self, *, fail=None):
        http = SimpleNamespace(
            start_private_message=AsyncMock(return_value={"id": 555}),
            send_message=AsyncMock(side_effect=fail),
        )
        return SimpleNamespace(http=http)

    async def test_seller_gets_a_ping(self):
        from cogs.equipment.shop import notify_gear_sale

        bot = self.bot()
        self.assertTrue(await notify_gear_sale(bot, {"seller_id": OWNER, "name": "Razor Helm", "price": 1500}))
        bot.http.start_private_message.assert_awaited_once_with(OWNER)
        params = bot.http.send_message.await_args.kwargs["params"]
        content = params.payload["content"] if params.payload else params.multipart
        self.assertIn(f"<@{OWNER}>", str(content))
        self.assertIn("Razor Helm", str(content))
        self.assertIn("$1,500", str(content))

    async def test_closed_dms_never_break_the_sale(self):
        from cogs.equipment.shop import notify_gear_sale

        forbidden = discord.Forbidden(SimpleNamespace(status=403, reason="no"), "closed")
        self.assertFalse(await notify_gear_sale(self.bot(fail=forbidden), {"seller_id": OWNER, "name": "x", "price": 1}))
        with self.assertLogs("cogs.equipment.shop", level="ERROR"):
            self.assertFalse(await notify_gear_sale(self.bot(fail=RuntimeError("boom")), {"seller_id": OWNER, "name": "x", "price": 1}))
        self.assertFalse(await notify_gear_sale(self.bot(), None))


class TradeMaterialTests(unittest.IsolatedAsyncioTestCase):
    def cog(self, owned, *, open_=True):
        import cogs.transaction as transaction

        cog = transaction.Transaction.__new__(transaction.Transaction)
        db = FakeArmoryDB()
        db.materials = {(OWNER, key): value for key, value in owned.items()}

        async def fetch(sql, *args):
            return [
                {"material_id": key, "amount": value}
                for (user, key), value in db.materials.items()
                if user == int(args[0])
            ]

        db.fetch = fetch
        cog.bot = SimpleNamespace(pool=FakePool(db), equipment_combat_enabled=open_)
        return cog

    def offer(self):
        return {"armory": defaultdict(lambda: 0)}

    async def test_set_materials(self):
        cog = self.cog({"bog_iron": 10})
        offer = self.offer()
        ok, _ = await cog._set_offer_materials(offer, OWNER, "Bog Iron", 4)
        self.assertTrue(ok)
        self.assertEqual(4, offer["armory"]["bog_iron"])
        ok, message = await cog._set_offer_materials(offer, OWNER, "bog_iron", 11)
        self.assertFalse(ok)
        self.assertIn("only own 10", message)
        self.assertEqual(4, offer["armory"]["bog_iron"])
        ok, _ = await cog._set_offer_materials(offer, OWNER, "bog iron", 0)
        self.assertTrue(ok)
        self.assertEqual(0, offer["armory"]["bog_iron"])

    async def test_unknown_material_or_closed_armory(self):
        cog = self.cog({"bog_iron": 10})
        ok, message = await cog._set_offer_materials(self.offer(), OWNER, "gold bars", 1)
        self.assertFalse(ok)
        self.assertIn("not an armor material", message)
        ok, message = await self.cog({}, open_=False)._set_offer_materials(self.offer(), OWNER, "bog iron", 1)
        self.assertFalse(ok)
        self.assertIn("closed", message)

    async def test_amulet_material_names_point_to_resources(self):
        import cogs.amuletcrafting as amulet

        cog = self.cog({"bog_iron": 10})
        amulet_cog = amulet.AmuletCrafting.__new__(amulet.AmuletCrafting)
        amulet_cog.ALL_RESOURCES = {"dragon_scales": "x", "fire_gems": "y"}
        cog.bot.get_cog = lambda name: amulet_cog if name == "AmuletCrafting" else None
        for typed in ("dragon scales", "Dragon Scale", "dragon_scales"):
            ok, message = await cog._set_offer_materials(self.offer(), OWNER, typed, 1)
            self.assertFalse(ok, typed)
            self.assertIn("amulet crafting material", message, typed)
            self.assertIn("Resources", message, typed)
        self.assertIn("`$trade add resources`", cog._not_armor_material_text("fire gems", "$"))
        self.assertIn("not an armor material", cog._not_armor_material_text("gold bars", "$"))
        ok, _ = await cog._set_offer_materials(self.offer(), OWNER, "bog iron", 1)
        self.assertTrue(ok)

    def test_trade_aliases_do_not_say_plain_materials(self):
        import cogs.transaction as transaction

        for command in (transaction.Transaction.add_armory, transaction.Transaction.remove_armory):
            self.assertNotIn("materials", command.aliases)
            self.assertIn("armormaterials", command.aliases)
            self.assertIn("gearmaterials", command.aliases)

    def test_editor_has_a_materials_button(self):
        import cogs.transaction as transaction

        self.assertTrue(hasattr(transaction.TradeOfferEditorView, "armor_materials"))


if __name__ == "__main__":
    unittest.main()

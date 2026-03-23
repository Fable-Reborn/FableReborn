import unittest

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from cogs.newwerewolf.core import (
    Game,
    Player,
    Role,
    Side,
    enforce_role_min_player_requirements,
    side_from_role,
)


class DummyUser(SimpleNamespace):
    def __str__(self) -> str:
        return self.name


class DummyPlayer:
    def __init__(self, user_id: int, name: str, role: Role):
        self.user = DummyUser(id=user_id, name=name, mention=f"<@{user_id}>")
        self.role = role
        self.dead = False
        self.cursed = False
        self.revealed_roles = {}
        self.sorcerer_disguise_role = None
        self.sorcerer_has_resigned = False
        self.wolf_shaman_mask_active = False
        self.wolf_trickster_disguise_role = None
        self.send = AsyncMock()

    @property
    def side(self) -> Side:
        if self.cursed and self.role != Role.WHITE_WOLF:
            return Side.WOLVES
        return side_from_role(self.role)


class ChooseResult:
    def __init__(self, result: int):
        self.result = result

    async def paginate(self, ctx, location):
        return self.result


class MultiChooseResult:
    def __init__(self, result):
        self.result = result

    async def paginate(self, ctx, location):
        return self.result


class TestNewWerewolfRoleBehaviors(unittest.IsolatedAsyncioTestCase):
    def test_cursed_is_removed_from_small_lobbies(self):
        roles = [
            Role.WEREWOLF,
            Role.CURSED,
            Role.SEER,
            Role.VILLAGER,
            Role.DOCTOR,
            Role.VILLAGER,
            Role.VILLAGER,
            Role.VILLAGER,
        ]

        adjusted = enforce_role_min_player_requirements(
            roles,
            requested_players=6,
            mode="Classic",
        )

        self.assertNotIn(Role.CURSED, adjusted)
        self.assertEqual(len(roles), len(adjusted))
        self.assertIn(
            Role.CURSED,
            enforce_role_min_player_requirements(
                roles,
                requested_players=7,
                mode="Classic",
            ),
        )

    def test_talisman_guarantees_role_for_single_claimant(self):
        claimant = DummyPlayer(1, "Claimant", Role.VILLAGER)
        outsider = DummyPlayer(2, "Outsider", Role.VILLAGER)
        game = SimpleNamespace()
        game._pick_talisman_player_for_role = (
            Game._pick_talisman_player_for_role.__get__(game, Game)
        )

        chosen = game._pick_talisman_player_for_role(
            [outsider, claimant],
            Role.SEER,
            {claimant.user.id: {Role.SEER}},
        )

        self.assertIs(claimant, chosen)

    def test_talisman_contest_only_rolls_among_matching_claimants(self):
        claimant_one = DummyPlayer(1, "Claimant One", Role.VILLAGER)
        claimant_two = DummyPlayer(2, "Claimant Two", Role.VILLAGER)
        outsider = DummyPlayer(3, "Outsider", Role.VILLAGER)
        game = SimpleNamespace()
        game._pick_talisman_player_for_role = (
            Game._pick_talisman_player_for_role.__get__(game, Game)
        )

        with patch(
            "cogs.newwerewolf.core.random.choice",
            return_value=claimant_two,
        ) as random_choice:
            chosen = game._pick_talisman_player_for_role(
                [outsider, claimant_one, claimant_two],
                Role.SEER,
                {
                    claimant_one.user.id: {Role.SEER},
                    claimant_two.user.id: {Role.SEER},
                },
            )

        self.assertIs(claimant_two, chosen)
        random_choice.assert_called_once_with([claimant_one, claimant_two])

    async def test_choose_users_prefers_multi_select_for_multi_target_prompts(self):
        first = DummyPlayer(2, "First", Role.VILLAGER)
        second = DummyPlayer(3, "Second", Role.VILLAGER)
        third = DummyPlayer(4, "Third", Role.VILLAGER)
        multi_choose = Mock(return_value=MultiChooseResult([0, 2]))
        paginator = SimpleNamespace(
            MultiChoose=multi_choose,
            NoChoice=RuntimeError,
        )
        game = SimpleNamespace(
            ctx=SimpleNamespace(
                bot=SimpleNamespace(paginator=paginator),
            ),
            timer=60,
            game_link="https://example.invalid/game",
            get_role_name=lambda role: role.name.title(),
        )
        chooser = SimpleNamespace(
            is_jailed=False,
            is_sleeping_tonight=False,
            revealed_roles={},
            game=game,
            user=DummyUser(id=1, name="Chooser", mention="<@1>"),
            send=AsyncMock(),
        )

        chosen = await Player.choose_users(
            chooser,
            "Pick targets",
            [first, second, third],
            amount=2,
            required=False,
            prefer_multi_select=True,
        )

        self.assertEqual([first, third], chosen)
        multi_choose.assert_called_once()
        kwargs = multi_choose.call_args.kwargs
        self.assertEqual(2, kwargs["max_values"])
        self.assertTrue(kwargs["allow_empty"])

    async def test_butcher_can_target_self(self):
        ally = SimpleNamespace(
            user=DummyUser(id=2, name="Ally", mention="<@2>"),
            is_protected=False,
            protected_by_doctor=None,
        )
        other = SimpleNamespace(
            user=DummyUser(id=3, name="Other", mention="<@3>"),
            is_protected=False,
            protected_by_doctor=None,
        )
        game = SimpleNamespace(
            alive_players=[],
            game_link="https://example.invalid/game",
        )
        captured = {}
        butcher = SimpleNamespace(
            user=DummyUser(id=1, name="Butcher", mention="<@1>"),
            butcher_meat_left=6,
            game=game,
            send=AsyncMock(),
            announce_awake=AsyncMock(),
        )

        async def choose_users(*args, **kwargs):
            captured.update(kwargs)
            return [butcher, ally]

        butcher.choose_users = AsyncMock(side_effect=choose_users)
        butcher.is_protected = False
        butcher.protected_by_doctor = None
        game.alive_players = [butcher, ally, other]

        await Player.set_butcher_targets(butcher)

        butcher.announce_awake.assert_awaited_once()
        butcher.choose_users.assert_awaited_once()
        self.assertEqual(game.alive_players, captured["list_of_users"])
        self.assertTrue(captured["prefer_multi_select"])
        self.assertTrue(butcher.is_protected)
        self.assertTrue(ally.is_protected)
        self.assertIs(butcher, butcher.protected_by_doctor)
        self.assertIs(butcher, ally.protected_by_doctor)
        self.assertEqual(4, butcher.butcher_meat_left)
        butcher.send.assert_awaited_once()
        self.assertIn("<@1>", butcher.send.await_args.args[0])
        self.assertIn("<@2>", butcher.send.await_args.args[0])

    async def test_marksman_cannot_mark_without_arrows(self):
        target = DummyPlayer(2, "Target", Role.VILLAGER)
        game = SimpleNamespace(
            ctx=SimpleNamespace(send=AsyncMock()),
            alive_players=[],
            game_link="https://example.invalid/game",
        )
        marksman = SimpleNamespace(
            role=Role.MARKSMAN,
            dead=False,
            marksman_arrows=0,
            marksman_target=None,
            game=game,
            send=AsyncMock(),
            choose_users=AsyncMock(),
        )
        game.alive_players = [marksman, target]

        await Player.set_marksman_target(marksman)

        game.ctx.send.assert_not_awaited()
        marksman.send.assert_not_awaited()
        marksman.choose_users.assert_not_awaited()
        self.assertIsNone(marksman.marksman_target)

    async def test_marksman_retarget_does_not_spend_arrow(self):
        current_target = DummyPlayer(2, "Current", Role.VILLAGER)
        new_target = DummyPlayer(3, "New", Role.WEREWOLF)
        paginator = SimpleNamespace(
            Choose=lambda **kwargs: ChooseResult(1),
            NoChoice=RuntimeError,
        )
        game = SimpleNamespace(
            ctx=SimpleNamespace(
                send=AsyncMock(),
                bot=SimpleNamespace(paginator=paginator),
            ),
            game_link="https://example.invalid/game",
            timer=60,
            alive_players=[],
        )
        marksman = SimpleNamespace(
            role=Role.MARKSMAN,
            role_name="Marksman",
            dead=False,
            marksman_arrows=2,
            marksman_target=current_target,
            user=DummyUser(id=1, name="Marksman", mention="<@1>"),
            choose_users=AsyncMock(return_value=[new_target]),
            send=AsyncMock(),
        )
        game.alive_players = [marksman, current_target, new_target]
        game.get_players_with_role = lambda role: [marksman] if role == Role.MARKSMAN else []

        await Game.handle_marksman_day_action(game)

        self.assertEqual(2, marksman.marksman_arrows)
        self.assertIs(new_target, marksman.marksman_target)
        marksman.choose_users.assert_awaited_once()
        marksman.send.assert_awaited_once()

    async def test_sorcerer_disguise_uses_present_non_seer_informers(self):
        sorcerer = DummyPlayer(1, "Sorcerer", Role.SORCERER)
        seer = DummyPlayer(2, "Seer", Role.SEER)
        aura_seer = DummyPlayer(3, "Aura", Role.AURA_SEER)
        detective = DummyPlayer(4, "Detective", Role.DETECTIVE)
        villager = DummyPlayer(5, "Villager", Role.VILLAGER)
        game = SimpleNamespace(
            players=[sorcerer, seer, aura_seer, detective, villager],
            game_link="https://example.invalid/game",
        )
        game.get_role_name = Game.get_role_name.__get__(game, Game)

        captured_choices = []

        def pick_detective(choices):
            captured_choices.append(tuple(choices))
            return Role.DETECTIVE

        with patch("cogs.newwerewolf.core.random.choice", side_effect=pick_detective):
            await Game.assign_sorcerer_disguises(game)

        self.assertEqual({Role.AURA_SEER, Role.DETECTIVE}, set(captured_choices[0]))
        self.assertEqual(Role.DETECTIVE, sorcerer.sorcerer_disguise_role)
        sorcerer.send.assert_awaited_once()
        self.assertIn("Detective", sorcerer.send.await_args.args[0])

    async def test_sorcerer_has_no_seer_fallback_disguise(self):
        sorcerer = DummyPlayer(1, "Sorcerer", Role.SORCERER)
        seer = DummyPlayer(2, "Seer", Role.SEER)
        villager = DummyPlayer(3, "Villager", Role.VILLAGER)
        game = SimpleNamespace(
            players=[sorcerer, seer, villager],
            game_link="https://example.invalid/game",
        )
        game.get_role_name = Game.get_role_name.__get__(game, Game)

        with patch("cogs.newwerewolf.core.random.choice") as random_choice:
            await Game.assign_sorcerer_disguises(game)

        random_choice.assert_not_called()
        self.assertIsNone(sorcerer.sorcerer_disguise_role)
        sorcerer.send.assert_awaited_once()
        self.assertIn("without a disguise", sorcerer.send.await_args.args[0])

    async def test_sorcerer_disguise_is_visible_to_informer_checks(self):
        sorcerer = DummyPlayer(1, "Sorcerer", Role.SORCERER)
        sorcerer.sorcerer_disguise_role = Role.DETECTIVE
        aura_seer = DummyPlayer(2, "Aura", Role.AURA_SEER)
        detective = DummyPlayer(3, "Detective", Role.DETECTIVE)
        villager = DummyPlayer(4, "Villager", Role.VILLAGER)
        game = SimpleNamespace()
        game._observer_can_see_sorcerer_disguise = (
            Game._observer_can_see_sorcerer_disguise.__get__(game, Game)
        )
        game._observer_can_see_wolf_shaman_enchant = (
            Game._observer_can_see_wolf_shaman_enchant.__get__(game, Game)
        )
        game.get_observed_role = Game.get_observed_role.__get__(game, Game)
        game.get_observed_side = Game.get_observed_side.__get__(game, Game)

        self.assertEqual(
            Role.DETECTIVE,
            game.get_observed_role(sorcerer, observer=aura_seer),
        )
        self.assertEqual(
            Side.VILLAGERS,
            game.get_observed_side(sorcerer, observer=detective),
        )
        self.assertEqual(
            Role.SORCERER,
            game.get_observed_role(sorcerer, observer=villager),
        )

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from cogs.newwerewolf.core import (
    Game,
    NIGHT_KILLER_GROUP_WOLVES,
    Role,
    Side,
    side_from_role,
)


class DummyUser(SimpleNamespace):
    def __str__(self) -> str:
        return self.name


class DummyPlayer:
    def __init__(self, user_id: int, name: str, role: Role):
        self.user = DummyUser(id=user_id, name=name, mention=f"<@{user_id}>")
        self.role = role
        self.initial_roles = [role]
        self.cursed = False
        self.dead = False
        self.sorcerer_has_resigned = False
        self.send = AsyncMock()
        self.send_information = AsyncMock()

    @property
    def side(self) -> Side:
        if self.cursed and self.role != Role.WHITE_WOLF:
            return Side.WOLVES
        return side_from_role(self.role)


class TestKittenWolfConversion(unittest.IsolatedAsyncioTestCase):
    def _build_game(self, *alive_players: DummyPlayer) -> SimpleNamespace:
        game = SimpleNamespace(
            alive_players=list(alive_players),
            pending_night_killer_group_by_player_id={},
            ctx=SimpleNamespace(send=AsyncMock()),
            game_link="https://example.invalid/game",
        )
        game._send_kitten_wolf_team_notice = Game._send_kitten_wolf_team_notice.__get__(
            game, Game
        )
        return game

    async def test_successful_conversion_stays_private(self):
        wolf = DummyPlayer(1, "Wolf", Role.WEREWOLF)
        target = DummyPlayer(2, "Target", Role.VILLAGER)
        game = self._build_game(wolf, target)
        game.pending_night_killer_group_by_player_id[target.user.id] = (
            NIGHT_KILLER_GROUP_WOLVES
        )

        result = await Game.apply_kitten_wolf_conversion(
            game,
            [target],
            conversion_target=target,
            conversion_mode=True,
        )

        self.assertEqual([], result)
        self.assertEqual(Role.WEREWOLF, target.role)
        self.assertFalse(target.cursed)
        self.assertNotIn(target.user.id, game.pending_night_killer_group_by_player_id)
        game.ctx.send.assert_not_awaited()
        wolf.send.assert_awaited_once()
        target.send.assert_awaited_once()
        target.send_information.assert_awaited_once()

    async def test_blocked_conversion_does_not_announce_publicly(self):
        wolf = DummyPlayer(1, "Wolf", Role.WEREWOLF)
        target = DummyPlayer(2, "Target", Role.VILLAGER)
        game = self._build_game(wolf, target)
        game.pending_night_killer_group_by_player_id[target.user.id] = (
            NIGHT_KILLER_GROUP_WOLVES
        )

        result = await Game.apply_kitten_wolf_conversion(
            game,
            [],
            conversion_target=target,
            conversion_mode=True,
        )

        self.assertEqual([], result)
        self.assertEqual(Role.VILLAGER, target.role)
        self.assertNotIn(target.user.id, game.pending_night_killer_group_by_player_id)
        game.ctx.send.assert_not_awaited()
        wolf.send.assert_awaited_once()
        target.send.assert_not_awaited()
        target.send_information.assert_not_awaited()

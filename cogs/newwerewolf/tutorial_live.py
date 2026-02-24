from __future__ import annotations

import asyncio
import types

from utils import random
from utils.i18n import _
from .core import Game
from .core import Role


TRACK_ROLES: dict[str, list[Role]] = {
    "generic": [
        Role.SEER,
        Role.WEREWOLF,
        Role.DOCTOR,
        Role.VILLAGER,
        Role.VILLAGER,
    ],
    "village": [
        Role.DOCTOR,
        Role.WEREWOLF,
        Role.SEER,
        Role.VILLAGER,
        Role.VILLAGER,
    ],
    "werewolf": [
        Role.WEREWOLF,
        Role.SEER,
        Role.DOCTOR,
        Role.VILLAGER,
        Role.VILLAGER,
    ],
    "solo": [
        Role.SERIAL_KILLER,
        Role.WEREWOLF,
        Role.DOCTOR,
        Role.VILLAGER,
        Role.VILLAGER,
    ],
}

TRACK_BOT_NAMES: dict[str, list[str]] = {
    "generic": ["Ivy", "Noah", "Rowan", "Luna"],
    "village": ["Mira", "Cole", "Nyx", "Tara"],
    "werewolf": ["Fang", "Theo", "Iris", "Mila"],
    "solo": ["Kade", "Mira", "Aria", "Dax"],
}


class _TutorialDMChannel:
    def __init__(self, channel_id: int) -> None:
        self.id = channel_id


class TutorialUser:
    def __init__(self, user_id: int, name: str) -> None:
        self.id = user_id
        self.name = name
        self.display_name = name
        self.mention = f"<@{user_id}>"
        self.dm_channel: _TutorialDMChannel | None = None
        self.roles: list[object] = []
        self.bot = True

    def __str__(self) -> str:
        return self.display_name

    def __repr__(self) -> str:
        return f"<TutorialUser id={self.id} name={self.display_name!r}>"

    def __hash__(self) -> int:
        return hash(self.id)

    def __eq__(self, other: object) -> bool:
        return getattr(other, "id", None) == self.id

    async def create_dm(self):
        if self.dm_channel is None:
            self.dm_channel = _TutorialDMChannel((self.id % 1_000_000_000) + 91_000_000)
        return self.dm_channel

    async def send(self, *args, **kwargs):
        return None


async def _tutorial_npc_choose_users(
    self,
    title: str,
    list_of_users: list,
    amount: int,
    required: bool = True,
    timeout: int | None = None,
    traceback_on_http_error: bool = False,
):
    if self.dead or self.is_jailed or self.is_sleeping_tonight:
        return []
    if not list_of_users or amount <= 0:
        return []

    candidates = [player for player in list_of_users if not player.dead]
    if not candidates:
        candidates = list(list_of_users)
    if not candidates:
        return []

    if not required and random.randint(1, 100) <= 20:
        return []

    pick_count = min(amount, len(candidates))
    if pick_count <= 1:
        return [random.choice(candidates)]
    return random.sample(candidates, pick_count)


class TutorialGame(Game):
    def __init__(self, ctx, *, track: str, learner) -> None:
        normalized_track = track if track in TRACK_ROLES else "generic"
        self.tutorial_track = normalized_track
        self.tutorial_learner_id = learner.id
        self.tutorial_bot_ids: set[int] = set()

        bot_names = TRACK_BOT_NAMES.get(normalized_track, TRACK_BOT_NAMES["generic"])
        bot_players = [
            TutorialUser(90_000_000_000_000_000 + idx, f"{name} (Bot)")
            for idx, name in enumerate(bot_names, start=1)
        ]
        players = [learner, *bot_players]

        super().__init__(
            ctx,
            players,
            mode="Custom",
            speed="Blitz",
            custom_roles=[Role.VILLAGER] * (len(players) + 2),
        )
        self.mode = "Tutorial"
        self._force_track_roles(normalized_track)
        self._bind_tutorial_npc_autoplay()

    def _force_track_roles(self, track: str) -> None:
        role_plan = TRACK_ROLES.get(track, TRACK_ROLES["generic"])
        for player, role in zip(self.players, role_plan):
            player.role = role
            player.initial_roles = [role]
            player.lives = 2 if role == Role.THE_OLD else 1
            player.dead = False
            player.has_won = False
            player.non_villager_killer_group = None
            player.to_check_afk = False
            player.afk_strikes = 0
            player.revealed_roles = {}
            if player.user.id != self.tutorial_learner_id:
                self.tutorial_bot_ids.add(player.user.id)

        self.available_roles = role_plan.copy()
        self.extra_roles = [Role.VILLAGER, Role.VILLAGER]

    def _bind_tutorial_npc_autoplay(self) -> None:
        for player in self.players:
            if player.user.id in self.tutorial_bot_ids:
                player.choose_users = types.MethodType(_tutorial_npc_choose_users, player)

    def _is_tutorial_npc(self, player) -> bool:
        return player.user.id in self.tutorial_bot_ids

    def _learner_player(self):
        for player in self.alive_players:
            if player.user.id == self.tutorial_learner_id:
                return player
        return None

    async def _send_tutorial_day_chatter(self) -> None:
        speakers = [p for p in self.alive_players if self._is_tutorial_npc(p)]
        if len(speakers) < 2:
            return
        speaker_one = random.choice(speakers)
        speaker_two_pool = [p for p in speakers if p != speaker_one]
        if not speaker_two_pool:
            return
        speaker_two = random.choice(speaker_two_pool)
        if self.tutorial_track == "werewolf":
            lines = [
                _("{speaker}: We should focus who was quiet last night.").format(
                    speaker=speaker_one.user
                ),
                _("{speaker}: Agreed, but we still need a clean vote.").format(
                    speaker=speaker_two.user
                ),
            ]
        elif self.tutorial_track == "village":
            lines = [
                _("{speaker}: Share your night info before we vote.").format(
                    speaker=speaker_one.user
                ),
                _("{speaker}: Don't rush. Compare claim timing first.").format(
                    speaker=speaker_two.user
                ),
            ]
        elif self.tutorial_track == "solo":
            lines = [
                _("{speaker}: Too many quiet players this day.").format(
                    speaker=speaker_one.user
                ),
                _("{speaker}: Let's make sure we don't split votes.").format(
                    speaker=speaker_two.user
                ),
            ]
        else:
            lines = [
                _("{speaker}: Let's hear every claim before nominations.").format(
                    speaker=speaker_one.user
                ),
                _("{speaker}: Note contradictions before committing.").format(
                    speaker=speaker_two.user
                ),
            ]
        for line in lines:
            await self.ctx.send(line)

    @staticmethod
    def _top_vote_target(votes_by_user: dict[object, int]) -> object | None:
        if not votes_by_user:
            return None
        ordered = sorted(votes_by_user, key=lambda user: -votes_by_user[user])
        if len(ordered) == 1:
            return ordered[0]
        if votes_by_user[ordered[0]] > votes_by_user[ordered[1]]:
            return ordered[0]
        return None

    async def election(self):
        election_players = [
            player
            for player in self.alive_players
            if not player.is_jailed and not player.is_grumpy_silenced_today
        ]
        if not election_players:
            return None, False

        mentions = " ".join(player.user.mention for player in election_players)
        await self.ctx.send(mentions)
        await self.ctx.send(
            _(
                "You may now submit someone (up to 10 total) for the election who to"
                " lynch. Discussion and nominations start now ({timer}s)."
            ).format(timer=self.timer)
        )
        await self._send_tutorial_day_chatter()

        nominated_users: list[object] = []

        async def add_nomination(nominator, nominee_player) -> None:
            nominee = nominee_player.user
            if nominee in nominated_users or len(nominated_users) >= 10:
                return
            nominated_users.append(nominee)
            await self.ctx.send(
                _("**{player}** nominated **{nominee}**.").format(
                    player=nominator.user,
                    nominee=nominee,
                )
            )

        learner = self._learner_player()
        if learner is not None and not learner.dead:
            learner_nominees = [p for p in election_players if p != learner]
            if learner_nominees:
                try:
                    chosen = await learner.choose_users(
                        _(
                            "Choose one player to nominate for lynch this day. You can"
                            " dismiss to skip nominating."
                        ),
                        list_of_users=learner_nominees,
                        amount=1,
                        required=False,
                    )
                except Exception:
                    chosen = []
                if chosen:
                    await add_nomination(learner, chosen[0])

        for npc in [player for player in election_players if self._is_tutorial_npc(player)]:
            if len(nominated_users) >= 3:
                break
            if random.randint(1, 100) > 55:
                continue
            possible_targets = [p for p in election_players if p != npc]
            if not possible_targets:
                continue
            target = random.choice(possible_targets)
            await add_nomination(npc, target)

        if not nominated_users:
            return None, False
        if len(nominated_users) == 1:
            return nominated_users[0], False

        votes_by_user = {candidate: 0 for candidate in nominated_users}

        if learner is not None and learner in election_players:
            nominee_players = [
                player for player in election_players if player.user in nominated_users
            ]
            if nominee_players:
                try:
                    choice = await learner.choose_users(
                        _(
                            "Vote who to lynch. Your vote is final once selected."
                        ),
                        list_of_users=nominee_players,
                        amount=1,
                        required=False,
                    )
                except Exception:
                    choice = []
                if choice:
                    learner.to_check_afk = False
                    weight = 2 if learner.is_sheriff else 1
                    votes_by_user[choice[0].user] += weight
                else:
                    learner.to_check_afk = True

        for npc in [player for player in election_players if self._is_tutorial_npc(player)]:
            npc.to_check_afk = False
            candidates = [candidate for candidate in nominated_users if candidate != npc.user]
            if not candidates:
                candidates = nominated_users.copy()
            if not candidates:
                continue
            target = random.choice(candidates)
            weight = 2 if npc.is_sheriff else 1
            votes_by_user[target] += weight

        winner = self._top_vote_target(votes_by_user)
        if winner is None:
            await self.ctx.send(_("The vote tied. No one was lynched."))
        else:
            await self.ctx.send(
                _("Voting ended. **{target}** received the most votes.").format(
                    target=winner.mention
                )
            )
        return winner, False

    async def handle_afk(self) -> None:
        if self.winner is not None:
            return

        learner = self._learner_player()
        if learner is None or not learner.to_check_afk:
            for player in self.alive_players:
                if self._is_tutorial_npc(player):
                    player.to_check_afk = False
            return

        await self.ctx.send(
            _(
                "AFK check: use your DM dropdown to confirm you're still in the game"
                " ({timer}s)."
            ).format(timer=self.timer)
        )
        try:
            await learner.send(f"AFK CHECK {learner.user.mention}!")
            result = await self.ctx.bot.paginator.Choose(
                entries=[_("Not AFK")],
                return_index=True,
                title=_("Confirm you're active to avoid an AFK strike."),
                timeout=self.timer,
            ).paginate(self.ctx, learner.user)
            if result == 0:
                learner.to_check_afk = False
                await learner.send(_("You have been verified as not AFK."))
                return
        except asyncio.TimeoutError:
            pass
        except Exception:
            pass

        learner.to_check_afk = False
        learner.afk_strikes += 1
        if learner.afk_strikes >= 3:
            await self.ctx.send(
                _(
                    "**{player}** has been killed by the game due to having 3 AFK"
                    " strikes."
                ).format(player=learner.user.mention)
            )
            await learner.kill()
            return
        await learner.send(
            _(
                "⚠️ **Strike {strikes}!** You were marked AFK. You'll be removed after"
                " 3 strikes."
            ).format(strikes=learner.afk_strikes)
        )

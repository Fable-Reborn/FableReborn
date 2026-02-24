from __future__ import annotations

import asyncio
import re
import types

import discord

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

TUTORIAL_VARIANT_VILLAGE_SEER = "village_seer"
TUTORIAL_VARIANT_WEREWOLF_GUIDED = "werewolf_guided"
TUTORIAL_VARIANT_SOLO_JESTER = "solo_jester"


class _TutorialDMChannel:
    def __init__(self, channel_id: int) -> None:
        self.id = channel_id


class TutorialUser:
    def __init__(self, user_id: int, name: str) -> None:
        self.id = user_id
        self.name = name
        self.display_name = name
        # Bots in tutorial are simulated and should not look like real @mentions.
        self.mention = name
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

    async def add_roles(self, *roles, **kwargs):
        for role in roles:
            if role not in self.roles:
                self.roles.append(role)

    async def remove_roles(self, *roles, **kwargs):
        for role in roles:
            if role in self.roles:
                self.roles.remove(role)


def _normalize_token(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.casefold())


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

    game = getattr(self, "game", None)
    if (
        game is not None
        and getattr(game, "tutorial_track", None) == "village"
        and getattr(game, "night_no", 0) == 1
        and getattr(self, "role", None) == Role.WEREWOLF
    ):
        villager_targets = [player for player in candidates if player.role == Role.VILLAGER]
        if villager_targets:
            candidates = villager_targets
    if (
        game is not None
        and getattr(game, "tutorial_variant", "") == TUTORIAL_VARIANT_SOLO_JESTER
        and getattr(game, "night_no", 0) == 1
        and getattr(self, "role", None) == Role.WEREWOLF
    ):
        safe_targets = [player for player in candidates if player.role == Role.VILLAGER]
        if safe_targets:
            candidates = safe_targets

    pick_count = min(amount, len(candidates))
    if pick_count <= 1:
        return [random.choice(candidates)]
    return random.sample(candidates, pick_count)


async def _tutorial_learner_choose_users(
    self,
    title: str,
    list_of_users: list,
    amount: int,
    required: bool = True,
    timeout: int | None = None,
    traceback_on_http_error: bool = False,
):
    original = getattr(self, "_tutorial_original_choose_users", None)
    if original is None:
        return []

    candidates = list(list_of_users or [])
    lowered_title = str(title or "").casefold()
    dead_target_hints = (
        "dead",
        "corpse",
        "autopsy",
        "resurrect",
        "revive",
        "grave",
    )
    allow_dead_targets = any(hint in lowered_title for hint in dead_target_hints)
    if not allow_dead_targets:
        candidates = [player for player in candidates if not player.dead]

    game = getattr(self, "game", None)
    if (
        game is not None
        and getattr(game, "tutorial_variant", "") == TUTORIAL_VARIANT_VILLAGE_SEER
        and getattr(game, "tutorial_track", "") == "village"
        and getattr(game, "night_no", 0) == 1
        and getattr(self, "role", None) == Role.SEER
        and "check" in lowered_title
    ):
        forced_target = game._alive_player_with_role(Role.WEREWOLF)  # type: ignore[attr-defined]
        if forced_target is not None:
            return [forced_target]
    if (
        game is not None
        and getattr(game, "tutorial_variant", "") == TUTORIAL_VARIANT_WEREWOLF_GUIDED
        and getattr(game, "tutorial_track", "") == "werewolf"
        and getattr(game, "night_no", 0) == 1
        and getattr(self, "role", None) == Role.WEREWOLF
        and ("kill" in lowered_title or "victim" in lowered_title)
    ):
        forced_target = game._alive_player_with_role(Role.SEER)  # type: ignore[attr-defined]
        if forced_target is not None:
            return [forced_target]

    return await original(
        title,
        candidates,
        amount,
        required,
        timeout,
        traceback_on_http_error,
    )


class TutorialGame(Game):
    def __init__(self, ctx, *, track: str, learner, tutorial_variant: str | None = None) -> None:
        normalized_track = track if track in TRACK_ROLES else "generic"
        self.tutorial_track = normalized_track
        self.tutorial_variant = tutorial_variant or normalized_track
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
        if self.tutorial_variant == TUTORIAL_VARIANT_VILLAGE_SEER:
            role_plan = [
                Role.SEER,
                Role.WEREWOLF,
                Role.DOCTOR,
                Role.VILLAGER,
                Role.VILLAGER,
            ]
        elif self.tutorial_variant == TUTORIAL_VARIANT_WEREWOLF_GUIDED:
            role_plan = [
                Role.WEREWOLF,
                Role.SEER,
                Role.DOCTOR,
                Role.VILLAGER,
                Role.VILLAGER,
            ]
        elif self.tutorial_variant == TUTORIAL_VARIANT_SOLO_JESTER:
            role_plan = [
                Role.JESTER,
                Role.WEREWOLF,
                Role.DOCTOR,
                Role.VILLAGER,
                Role.VILLAGER,
            ]
        else:
            role_plan = TRACK_ROLES.get(track, TRACK_ROLES["generic"])
        for player, role in zip(self.players, role_plan):
            player.role = role
            player.initial_roles = [role]
            player.lives = 2 if role == Role.THE_OLD else 1
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
            elif player.user.id == self.tutorial_learner_id:
                player._tutorial_original_choose_users = player.choose_users
                player.choose_users = types.MethodType(
                    _tutorial_learner_choose_users, player
                )

    def _is_tutorial_npc(self, player) -> bool:
        return player.user.id in self.tutorial_bot_ids

    def _player_label(self, player) -> str:
        if self._is_tutorial_npc(player):
            return str(player.user)
        return player.user.mention

    def _learner_player(self):
        for player in self.alive_players:
            if player.user.id == self.tutorial_learner_id:
                return player
        return None

    def _alive_player_with_role(self, role: Role):
        for player in self.alive_players:
            if player.role == role:
                return player
        return None

    def _is_village_day1_script(self) -> bool:
        return (
            self.tutorial_track == "village"
            and self.tutorial_variant != TUTORIAL_VARIANT_VILLAGE_SEER
            and self.night_no == 1
        )

    def _is_village_seer_day1_script(self) -> bool:
        return (
            self.tutorial_track == "village"
            and self.tutorial_variant == TUTORIAL_VARIANT_VILLAGE_SEER
            and self.night_no == 1
        )

    def _is_werewolf_guided_day1_script(self) -> bool:
        return (
            self.tutorial_track == "werewolf"
            and self.tutorial_variant == TUTORIAL_VARIANT_WEREWOLF_GUIDED
            and self.night_no == 1
        )

    def _is_solo_jester_day1_script(self) -> bool:
        return (
            self.tutorial_track == "solo"
            and self.tutorial_variant == TUTORIAL_VARIANT_SOLO_JESTER
            and self.night_no == 1
        )

    async def _send_coach(
        self,
        *,
        title: str,
        description: str,
    ) -> None:
        embed = discord.Embed(
            title=f"Tutorial Coach: {title}",
            description=description,
            colour=self.ctx.bot.config.game.primary_colour,
        )
        await self.ctx.send(embed=embed)

    async def initial_preparation(self) -> list:
        track_guides = {
            "generic": _(
                "This tutorial uses the real game loop. Read the public day log, act in"
                " DMs at night, and use public nomination/voting during elections."
            ),
            "village": _(
                "Village focus: protect information roles, compare claims publicly, and"
                " avoid rushed votes."
            ),
            "werewolf": _(
                "Werewolf focus: control day narrative and coordinate kills at night."
            ),
            "solo": _(
                "Solo focus: survive while steering day outcomes toward your own win."
            ),
        }
        await self._send_coach(
            title=_("How This Tutorial Works"),
            description=track_guides.get(self.tutorial_track, track_guides["generic"]),
        )
        if self.tutorial_variant == TUTORIAL_VARIANT_VILLAGE_SEER:
            await self._send_coach(
                title=_("Round Goal"),
                description=_(
                    "Second village round: you are **Seer**. Check the Werewolf at"
                    " night, then publicly call them out during the day."
                ),
            )
        elif self.tutorial_variant == TUTORIAL_VARIANT_WEREWOLF_GUIDED:
            await self._send_coach(
                title=_("Round Goal"),
                description=_(
                    "Second werewolf round: you are **Werewolf**. Kill the Seer at"
                    " night, then push a day suspect to control the vote."
                ),
            )
        elif self.tutorial_variant == TUTORIAL_VARIANT_SOLO_JESTER:
            await self._send_coach(
                title=_("Round Goal"),
                description=_(
                    "Second solo round: you are **Jester**. Get lynched during the day"
                    " to win instantly."
                ),
            )
        return await super().initial_preparation()

    async def send_night_announcement(self, moon: str = "🌘") -> None:
        await super().send_night_announcement(moon)
        if self._is_village_seer_day1_script():
            wolf = self._alive_player_with_role(Role.WEREWOLF)
            if wolf is not None:
                await self._send_coach(
                    title=_("Seer Action"),
                    description=_(
                        "You are Seer this round. In DM, check **{wolf}** tonight."
                        " Your Seer result tells you who is bad."
                    ).format(wolf=wolf.user),
                )
        elif self._is_werewolf_guided_day1_script():
            seer = self._alive_player_with_role(Role.SEER)
            if seer is not None:
                await self._send_coach(
                    title=_("Werewolf Action"),
                    description=_(
                        "Night objective: kill **{seer}** (information role priority)."
                    ).format(seer=seer.user),
                )
        elif self._is_solo_jester_day1_script():
            await self._send_coach(
                title=_("Jester Night"),
                description=_(
                    "As Jester, you have no night action. Prepare a day message that"
                    " gets you lynched."
                ),
            )
        await self._send_coach(
            title=_("Night Phase"),
            description=_(
                "Night actions are private. Check your DMs and complete your role action"
                " before the timer ends."
            ),
        )

    async def send_day_announcement(self) -> None:
        await super().send_day_announcement()
        await self._send_coach(
            title=_("Day Phase"),
            description=_(
                "Use public discussion to compare claims and voting logic. Track who"
                " changes stories."
            ),
        )

    async def _send_tutorial_day_chatter(self) -> None:
        if self._is_village_day1_script():
            seer = self._alive_player_with_role(Role.SEER)
            werewolf = self._alive_player_with_role(Role.WEREWOLF)
            villager = next(
                (
                    player
                    for player in self.alive_players
                    if self._is_tutorial_npc(player) and player.role == Role.VILLAGER
                ),
                None,
            )
            if seer is not None and werewolf is not None:
                await self.ctx.send(
                    _("{seer}: I checked {wolf} last night. They are a Werewolf.").format(
                        seer=seer.user,
                        wolf=werewolf.user,
                    )
                )
                if villager is not None:
                    await self.ctx.send(
                        _("{villager}: Then we should vote {wolf} today.").format(
                            villager=villager.user,
                            wolf=werewolf.user,
                        )
                    )
                await self._send_coach(
                    title=_("Seer Claim Priority"),
                    description=_(
                        "Seer is a very important role. Treat a Seer claim as high-value"
                        " info, but always watch for counter-claims and consistency."
                    ),
                )
                return

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

    async def _wait_for_seer_public_callout(self, *, werewolf_player) -> bool:
        learner = self._learner_player()
        if learner is None:
            return False

        wolf_name = str(werewolf_player.user)
        wolf_base = wolf_name.replace("(Bot)", "").strip()
        wolf_first = wolf_base.split()[0] if wolf_base else wolf_name
        wolf_tokens = {
            _normalize_token(wolf_name),
            _normalize_token(wolf_base),
            _normalize_token(wolf_first),
        }
        wolf_tokens = {token for token in wolf_tokens if token}

        await self._send_coach(
            title=_("Public Callout"),
            description=_(
                "Now call out the wolf in this channel. Include all parts in one"
                " message:\n"
                "1) say you're Seer (`I'm Seer`)\n"
                "2) include the wolf name\n"
                "3) include `werewolf`\n"
                "4) ask Doctor to protect you."
            ),
        )

        end_time = asyncio.get_running_loop().time() + self.timer
        while asyncio.get_running_loop().time() < end_time:
            remaining = max(1, int(end_time - asyncio.get_running_loop().time()))
            try:
                msg = await self.ctx.bot.wait_for(
                    "message",
                    timeout=remaining,
                    check=lambda m: m.author.id == learner.user.id
                    and m.channel.id == self.ctx.channel.id,
                )
            except asyncio.TimeoutError:
                break

            text = str(msg.content or "")
            lower = text.casefold()
            normalized = _normalize_token(text)
            has_werewolf_word = "werewolf" in lower
            mentions_wolf = any(token in normalized for token in wolf_tokens)
            has_seer_word = "seer" in lower
            has_self_claim = has_seer_word and (
                "i am" in lower
                or "i'm" in lower
                or "im " in lower
                or lower.startswith("seer")
            )
            has_doctor_protect = (
                "doctor" in lower and "protect" in lower
            )
            if (
                has_werewolf_word
                and mentions_wolf
                and has_self_claim
                and has_doctor_protect
            ):
                return True

            missing_parts = []
            if not has_self_claim:
                missing_parts.append(_("`I'm Seer`"))
            if not mentions_wolf:
                missing_parts.append(_("wolf name"))
            if not has_werewolf_word:
                missing_parts.append(_("`werewolf`"))
            if not has_doctor_protect:
                missing_parts.append(_("ask Doctor to protect you"))
            await self.ctx.send(
                _(
                    "Coach: missing {parts}. Try again in one message."
                ).format(parts=", ".join(missing_parts))
            )

        return False

    async def _wait_for_named_day_push(self, *, target_player, coach_title: str) -> bool:
        learner = self._learner_player()
        if learner is None:
            return False

        target_name = str(target_player.user)
        target_base = target_name.replace("(Bot)", "").strip()
        target_first = target_base.split()[0] if target_base else target_name
        target_tokens = {
            _normalize_token(target_name),
            _normalize_token(target_base),
            _normalize_token(target_first),
        }
        target_tokens = {token for token in target_tokens if token}

        await self._send_coach(
            title=coach_title,
            description=_(
                "Send one public message that names **{target}** as your day suspect."
            ).format(target=target_player.user),
        )

        end_time = asyncio.get_running_loop().time() + self.timer
        while asyncio.get_running_loop().time() < end_time:
            remaining = max(1, int(end_time - asyncio.get_running_loop().time()))
            try:
                msg = await self.ctx.bot.wait_for(
                    "message",
                    timeout=remaining,
                    check=lambda m: m.author.id == learner.user.id
                    and m.channel.id == self.ctx.channel.id,
                )
            except asyncio.TimeoutError:
                break

            normalized = _normalize_token(str(msg.content or ""))
            mentions_target = any(token in normalized for token in target_tokens)
            if mentions_target:
                return True
            await self.ctx.send(
                _("Coach: include the target's name in your push message.")
            )
        return False

    async def _wait_for_jester_bait_message(self) -> str | None:
        learner = self._learner_player()
        if learner is None:
            return None

        await self._send_coach(
            title=_("Jester Bait"),
            description=_(
                "Best pattern: fake-claim an important role (example `I'm Seer`) so"
                " someone counter-claims and you look suspicious.\n"
                "Alternative: directly bait with `lynch me`/`werewolf`."
            ),
        )
        end_time = asyncio.get_running_loop().time() + self.timer
        while asyncio.get_running_loop().time() < end_time:
            remaining = max(1, int(end_time - asyncio.get_running_loop().time()))
            try:
                msg = await self.ctx.bot.wait_for(
                    "message",
                    timeout=remaining,
                    check=lambda m: m.author.id == learner.user.id
                    and m.channel.id == self.ctx.channel.id,
                )
            except asyncio.TimeoutError:
                break

            text = str(msg.content or "")
            lower = text.casefold()
            role_claim_words = ("seer", "doctor", "sheriff", "bodyguard", "medium")
            has_fake_claim = (
                any(role_word in lower for role_word in role_claim_words)
                and (
                    "i am" in lower
                    or "i'm" in lower
                    or "im " in lower
                    or "claim" in lower
                )
            )
            has_direct_bait = "werewolf" in lower or "lynch" in lower
            if has_fake_claim or has_direct_bait:
                return text

            await self.ctx.send(
                _(
                    "Coach: fake-claim an important role (like `I'm Seer`) or include"
                    " `lynch`/`werewolf`."
                )
            )
        return None

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

        await self.ctx.send(
            _("Eligible players: {players}").format(
                players=", ".join(self._player_label(player) for player in election_players)
            )
        )
        await self.ctx.send(
            _(
                "You may now submit someone (up to 10 total) for the election who to"
                " lynch. Discussion and nominations start now ({timer}s)."
            ).format(timer=self.timer)
        )
        await self._send_coach(
            title=_("Public Nomination"),
            description=_(
                "Type your nomination in this channel (name or number). Do not use @"
                " for tutorial bots. Example: `1` or `Ivy`."
            ),
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
        learner_nominees = [p for p in election_players if learner is not None and p != learner]

        token_map: dict[str, object] = {}
        for idx, nominee in enumerate(learner_nominees, start=1):
            token_map[str(idx)] = nominee
            display = str(nominee.user)
            token_map[_normalize_token(display)] = nominee
            base_name = display.replace("(Bot)", "").strip()
            if base_name:
                token_map[_normalize_token(base_name)] = nominee
                first_word = base_name.split()[0]
                token_map[_normalize_token(first_word)] = nominee

        if (
            learner is not None
            and not learner.dead
            and learner_nominees
            and not self._is_village_seer_day1_script()
            and not self._is_werewolf_guided_day1_script()
            and not self._is_solo_jester_day1_script()
        ):
            options_text = "\n".join(
                f"{index}. {self._player_label(player)}"
                for index, player in enumerate(learner_nominees, start=1)
            )
            await self.ctx.send(
                _("Nomination options:\n{options}").format(options=options_text)
            )
            try:
                msg = await self.ctx.bot.wait_for(
                    "message",
                    timeout=self.timer,
                    check=lambda m: m.author.id == learner.user.id
                    and m.channel.id == self.ctx.channel.id,
                )
                raw = str(msg.content or "").strip()
                if raw.casefold() not in {"skip", "none", "pass"}:
                    chosen_nominee = token_map.get(_normalize_token(raw))
                    if chosen_nominee is not None:
                        await add_nomination(learner, chosen_nominee)
                    else:
                        await self.ctx.send(
                            _("Nomination not recognized. Skipping your nomination.")
                        )
                else:
                    await self.ctx.send(_("You skipped nomination this day."))
            except asyncio.TimeoutError:
                await self.ctx.send(_("You timed out for nomination this day."))

        for npc in [player for player in election_players if self._is_tutorial_npc(player)]:
            if self._is_village_day1_script():
                continue
            if len(nominated_users) >= 3:
                break
            if random.randint(1, 100) > 55:
                continue
            possible_targets = [p for p in election_players if p != npc]
            if not possible_targets:
                continue
            target = random.choice(possible_targets)
            await add_nomination(npc, target)

        forced_vote_nominee = None
        if self._is_village_day1_script():
            scripted_wolf_player = self._alive_player_with_role(Role.WEREWOLF)
            forced_vote_nominee = (
                scripted_wolf_player.user if scripted_wolf_player is not None else None
            )
            scripted_seer = self._alive_player_with_role(Role.SEER)
            if scripted_wolf_player is not None and scripted_seer is not None:
                if forced_vote_nominee not in nominated_users:
                    await add_nomination(scripted_seer, scripted_wolf_player)
                decoy = next(
                    (
                        player
                        for player in election_players
                        if player != scripted_wolf_player and player != scripted_seer
                    ),
                    None,
                )
                if decoy is not None and decoy.user not in nominated_users:
                    await add_nomination(scripted_wolf_player, decoy)
        elif self._is_village_seer_day1_script():
            scripted_wolf_player = self._alive_player_with_role(Role.WEREWOLF)
            forced_vote_nominee = (
                scripted_wolf_player.user if scripted_wolf_player is not None else None
            )
            scripted_seer = self._learner_player()
            if scripted_wolf_player is not None and scripted_seer is not None:
                valid_callout = await self._wait_for_seer_public_callout(
                    werewolf_player=scripted_wolf_player
                )
                if not valid_callout:
                    await self.ctx.send(
                        _(
                            "Coach: time ran out, moving on with the evidence already"
                            " available."
                        )
                    )
                doctor = self._alive_player_with_role(Role.DOCTOR)
                if doctor is not None and doctor != scripted_wolf_player:
                    await self.ctx.send(
                        _(
                            "{doctor}: Good claim. Seer is important, I'll protect you"
                            " tonight."
                        ).format(doctor=doctor.user)
                    )
                await self.ctx.send(
                    _("{wolf}: No wait please, I'm innocent!").format(
                        wolf=scripted_wolf_player.user
                    )
                )
                supporter = next(
                    (
                        player
                        for player in election_players
                        if player != scripted_wolf_player and player != scripted_seer
                    ),
                    None,
                )
                if supporter is not None:
                    await self.ctx.send(
                        _("{supporter}: Yeah, kill {wolf}.").format(
                            supporter=supporter.user,
                            wolf=scripted_wolf_player.user,
                        )
                    )
                    await add_nomination(supporter, scripted_wolf_player)
                else:
                    await add_nomination(scripted_seer, scripted_wolf_player)

                decoy = next(
                    (
                        player
                        for player in election_players
                        if player != scripted_wolf_player
                        and player != scripted_seer
                        and player.role == Role.VILLAGER
                    ),
                    None,
                )
                if decoy is not None and decoy.user not in nominated_users:
                    await add_nomination(scripted_wolf_player, decoy)
        elif self._is_werewolf_guided_day1_script():
            scripted_target = next(
                (
                    player
                    for player in election_players
                    if player.role == Role.VILLAGER and player != learner
                ),
                None,
            )
            if scripted_target is not None:
                forced_vote_nominee = scripted_target.user
                pushed = await self._wait_for_named_day_push(
                    target_player=scripted_target,
                    coach_title=_("Wolf Day Push"),
                )
                if not pushed:
                    await self.ctx.send(
                        _("Coach: moving forward with your implied push.")
                    )
                witness = next(
                    (
                        player
                        for player in election_players
                        if player != scripted_target and player != learner
                    ),
                    None,
                )
                if witness is not None:
                    await self.ctx.send(
                        _("{witness}: Yeah, {target} looks suspicious.").format(
                            witness=witness.user,
                            target=scripted_target.user,
                        )
                    )
                    await add_nomination(witness, scripted_target)
                elif learner is not None:
                    await add_nomination(learner, scripted_target)

                counter = self._alive_player_with_role(Role.DOCTOR)
                if (
                    counter is not None
                    and counter != scripted_target
                    and counter.user not in nominated_users
                ):
                    await add_nomination(scripted_target, counter)
        elif self._is_solo_jester_day1_script():
            if learner is not None:
                forced_vote_nominee = learner.user
                bait_message = await self._wait_for_jester_bait_message()
                if bait_message is None:
                    await self.ctx.send(
                        _("Coach: no bait detected in time, proceeding with suspicion.")
                    )
                claimed_role = None
                if bait_message:
                    lowered_bait = bait_message.casefold()
                    claimed_role = next(
                        (
                            role_name
                            for role_name in (
                                "seer",
                                "doctor",
                                "sheriff",
                                "bodyguard",
                                "medium",
                            )
                            if role_name in lowered_bait
                        ),
                        None,
                    )
                wolf = self._alive_player_with_role(Role.WEREWOLF)
                villager = next(
                    (
                        player
                        for player in election_players
                        if player.role == Role.VILLAGER
                    ),
                    None,
                )
                counterclaimer = next(
                    (
                        player
                        for player in election_players
                        if player != learner and player != wolf
                    ),
                    None,
                )
                if claimed_role is not None and counterclaimer is not None:
                    await self.ctx.send(
                        _(
                            "{counter}: No, **I** am the {role}. That's a fake claim."
                        ).format(
                            counter=counterclaimer.user,
                            role=claimed_role.title(),
                        )
                    )
                    await self._send_coach(
                        title=_("Counter-Claim Pressure"),
                        description=_(
                            "Good. Counter-claims make your Jester play look suspicious,"
                            " which helps get you lynched."
                        ),
                    )
                if wolf is not None:
                    await self.ctx.send(
                        _("{wolf}: They are acting weird. Lynch them.").format(
                            wolf=wolf.user
                        )
                    )
                    await add_nomination(wolf, learner)
                if villager is not None:
                    await self.ctx.send(
                        _("{villager}: Yeah, let's kill {target}.").format(
                            villager=villager.user,
                            target=learner.user,
                        )
                    )
                decoy = next(
                    (
                        player
                        for player in election_players
                        if player != learner and player.role == Role.VILLAGER
                    ),
                    None,
                )
                if decoy is not None and decoy.user not in nominated_users:
                    await add_nomination(learner, decoy)

        if not nominated_users:
            return None, False
        if len(nominated_users) == 1:
            return nominated_users[0], False

        votes_by_user = {candidate: 0 for candidate in nominated_users}

        emojis = ([f"{index + 1}\u20e3" for index in range(9)] + ["\U0001f51f"])[
            : len(nominated_users)
        ]
        mapping = {emoji: user for emoji, user in zip(emojis, nominated_users)}
        vote_lines = "\n".join(
            f"{emoji} - {candidate.mention if hasattr(candidate, 'mention') else str(candidate)}"
            for emoji, candidate in mapping.items()
        )
        vote_message = await self.ctx.send(
            _(
                "**React to vote for killing someone. You have {timer} seconds.**\n"
                "{lines}"
            ).format(timer=self.timer, lines=vote_lines)
        )
        for emoji in emojis:
            await vote_message.add_reaction(emoji)

        await self._send_coach(
            title=_("Public Voting"),
            description=_(
                "React on the vote message to cast your vote. Bots vote automatically"
                " in tutorial mode."
            ),
        )
        await asyncio.sleep(self.timer)

        if learner is not None and learner in election_players:
            try:
                refreshed = await self.ctx.channel.fetch_message(vote_message.id)
            except Exception:
                refreshed = vote_message
            learner_vote_registered = False
            for reaction in refreshed.reactions:
                emoji_key = str(reaction.emoji)
                if emoji_key not in mapping:
                    continue
                users = [user async for user in reaction.users() if user.id == learner.user.id]
                if not users:
                    continue
                learner_vote_registered = True
                learner.to_check_afk = False
                weight = 2 if learner.is_sheriff else 1
                votes_by_user[mapping[emoji_key]] += weight
                break
            if not learner_vote_registered:
                learner.to_check_afk = True

        for npc in [player for player in election_players if self._is_tutorial_npc(player)]:
            npc.to_check_afk = False
            if forced_vote_nominee is not None and forced_vote_nominee in nominated_users:
                target = forced_vote_nominee
                weight = 2 if npc.is_sheriff else 1
                votes_by_user[target] += weight
                continue

            candidates = [candidate for candidate in nominated_users if candidate != npc.user]
            if not candidates:
                candidates = nominated_users.copy()
            if not candidates:
                continue
            target = random.choice(candidates)
            weight = 2 if npc.is_sheriff else 1
            votes_by_user[target] += weight

        winner = self._top_vote_target(votes_by_user)
        tally_lines = "\n".join(
            _("{candidate}: {votes} vote(s)").format(
                candidate=candidate.mention
                if hasattr(candidate, "mention")
                else str(candidate),
                votes=votes,
            )
            for candidate, votes in sorted(
                votes_by_user.items(),
                key=lambda item: -item[1],
            )
        )
        await self.ctx.send(_("Vote tally:\n{tally}").format(tally=tally_lines))
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

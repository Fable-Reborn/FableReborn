"""
The IdleRPG Discord Bot
Copyright (C) 2018-2021 Diniboy and Gelbpunkt
Copyright (C) 2023-2024 Lunar (PrototypeX37)

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU Affero General Public License for more details.

You should have received a copy of the GNU Affero General Public License
along with this program.  If not, see <https://www.gnu.org/licenses/>.
"""
import asyncio

import discord

from discord.enums import ButtonStyle
from discord.ext import commands
from discord.ui.button import Button

from cogs.help import chunks
from utils import random
from utils.checks import is_gm
from utils.i18n import _, locale_doc
from utils.joins import JoinView
from utils.misc import nice_join


class GameBase:
    ALLIANCE_LOCK_ROUNDS = 3
    PLAYER_CONTROL_CHANCE = 30
    ACTION_TIMEOUT_SECONDS = 60
    REPORT_SECTION_DELAY_SECONDS = 3
    REPORT_TRIBUTE_DELAY_SECONDS = 2

    def __init__(self, ctx, players: list):
        self.ctx = ctx
        self.players = list(players)
        self.round = 1
        self.cast = []
        self.member_by_id = {p.id: p for p in self.players}
        self.team_by_player_id: dict[int, int] = {}
        self.allies_by_player_id: dict[int, set[int]] = {
            p.id: set() for p in self.players
        }
        self.gear_score: dict[int, int] = {p.id: 0 for p in self.players}
        self.kills: dict[int, int] = {p.id: 0 for p in self.players}
        self.traps: dict[int, int] = {p.id: 0 for p in self.players}
        self.hidden_ids: set[int] = set()
        self.game_channel_link = self._build_game_channel_link()

    def _build_game_channel_link(self) -> str:
        channel = getattr(self.ctx, "channel", None)
        jump_url = getattr(channel, "jump_url", None)
        if isinstance(jump_url, str) and jump_url:
            return jump_url
        channel_id = getattr(channel, "id", None)
        if channel_id is None:
            return ""
        guild_id = getattr(getattr(self.ctx, "guild", None), "id", None)
        if guild_id is None:
            return f"https://discord.com/channels/@me/{channel_id}"
        return f"https://discord.com/channels/{guild_id}/{channel_id}"

    def _alive_target(self, target_id: int | None, killed_this_round: set) -> discord.Member | None:
        if target_id is None:
            return None
        target = self.member_by_id.get(target_id)
        if target is None:
            return None
        if target not in self.players or target in killed_this_round:
            return None
        return target

    def _weapon_name(self, score: int) -> str:
        if score >= 8:
            return _("legendary war gear")
        if score >= 6:
            return _("a deadly rifle setup")
        if score >= 4:
            return _("solid mid-tier weapons")
        if score >= 2:
            return _("basic combat gear")
        return _("bare hands and panic")

    def _eligible_targets(
        self,
        actor: discord.Member,
        killed_this_round: set,
        *,
        allow_allies: bool = False,
    ) -> list[discord.Member]:
        alive_targets = [
            p
            for p in self.players
            if p != actor and p not in killed_this_round
        ]
        if allow_allies or self.round > self.ALLIANCE_LOCK_ROUNDS:
            return alive_targets
        allies = self.allies_by_player_id.get(actor.id, set())
        return [p for p in alive_targets if p.id not in allies]

    def _alive_allies(
        self,
        actor: discord.Member,
        killed_this_round: set,
    ) -> list[discord.Member]:
        ally_ids = self.allies_by_player_id.get(actor.id, set())
        return [
            self.member_by_id[ally_id]
            for ally_id in ally_ids
            if ally_id in self.member_by_id
            and self.member_by_id[ally_id] in self.players
            and self.member_by_id[ally_id] not in killed_this_round
        ]

    def _build_action_choices(
        self,
        actor: discord.Member,
        killed_this_round: set,
    ) -> list[dict]:
        choices = [
            {"label": _("Scavenge for weapons and food"), "kind": "scavenge"},
            {"label": _("Hide and wait for chaos"), "kind": "hide"},
            {"label": _("Set a trap on a common path"), "kind": "trap"},
        ]

        targets = self._eligible_targets(actor, killed_this_round)
        if targets:
            hunt_target = random.choice(targets)
            rush_target = random.choice(targets)
            choices.append(
                {
                    "label": _("Hunt down {target}").format(target=hunt_target.display_name),
                    "kind": "hunt",
                    "target_id": hunt_target.id,
                }
            )
            choices.append(
                {
                    "label": _("Rush {target} in a reckless brawl").format(
                        target=rush_target.display_name
                    ),
                    "kind": "rush",
                    "target_id": rush_target.id,
                }
            )

        allies = self._alive_allies(actor, killed_this_round)
        if allies:
            ally = random.choice(allies)
            choices.append(
                {
                    "label": _("Team with {ally} and raid supplies").format(
                        ally=ally.display_name
                    ),
                    "kind": "teamup",
                    "target_id": ally.id,
                }
            )
            if self.round > self.ALLIANCE_LOCK_ROUNDS:
                choices.append(
                    {
                        "label": _("Betray {ally} and steal their gear").format(
                            ally=ally.display_name
                        ),
                        "kind": "betray",
                        "target_id": ally.id,
                    }
                )

        sample_size = min(3, len(choices))
        return random.sample(choices, sample_size)

    async def _choose_action(self, actor: discord.Member, choices: list[dict]) -> dict:
        use_player_choice = random.randint(1, 100) <= self.PLAYER_CONTROL_CHANCE
        if not use_player_choice:
            return random.choice(choices)

        try:
            idx = await self.ctx.bot.paginator.Choose(
                entries=[choice["label"] for choice in choices],
                return_index=True,
                title=_("Choose your action\nBack to game: {link}").format(
                    link=self.game_channel_link
                ),
                timeout=self.ACTION_TIMEOUT_SECONDS,
            ).paginate(self.ctx, location=actor)
            return choices[idx]
        except (
            self.ctx.bot.paginator.NoChoice,
            discord.Forbidden,
            asyncio.TimeoutError,
        ):
            await self.ctx.send(
                _(
                    "I couldn't get a DM action from {user}. Choosing a random move."
                ).format(user=actor.mention),
                delete_after=20,
            )
            return random.choice(choices)

    def _mark_kill(
        self,
        killer: discord.Member | None,
        victim: discord.Member,
        killed_this_round: set,
        *,
        elimination_log: dict[int, dict] | None = None,
        cause: str | None = None,
    ) -> bool:
        if victim not in self.players or victim in killed_this_round:
            return False
        killed_this_round.add(victim)
        if killer is not None and killer.id in self.kills:
            self.kills[killer.id] += 1
        if elimination_log is not None:
            elimination_log[victim.id] = {
                "victim": victim,
                "killer": killer,
                "cause": cause or _("eliminated in the chaos"),
            }
        return True

    def _check_trap_trigger(
        self,
        attacker: discord.Member,
        defender: discord.Member,
        killed_this_round: set,
        elimination_log: dict[int, dict],
        *,
        bonus_chance: int = 0,
    ) -> bool:
        trap_count = self.traps.get(defender.id, 0)
        if trap_count <= 0:
            return False
        trigger_chance = min(70, 12 + trap_count * 14 + bonus_chance)
        if random.randint(1, 100) > trigger_chance:
            return False
        self.traps[defender.id] = max(0, trap_count - 1)
        self._mark_kill(
            defender,
            attacker,
            killed_this_round,
            elimination_log=elimination_log,
            cause=_("triggered a trap set by **{killer}**").format(
                killer=defender.display_name
            ),
        )
        return True

    def _mutt_lethality_chance(
        self,
        victim: discord.Member,
        *,
        base_chance: int = 72,
        min_chance: int = 20,
    ) -> int:
        gear = self.gear_score.get(victim.id, 0)
        chance = base_chance - min(40, gear * 4)
        if victim.id in self.hidden_ids:
            chance -= 8
        return max(min_chance, min(95, chance))

    def _apply_mutt_gear_loss(self, victim: discord.Member) -> int:
        current_gear = self.gear_score.get(victim.id, 0)
        loss = 2 if current_gear >= 6 and random.randint(1, 100) <= 45 else 1
        self.gear_score[victim.id] = max(0, current_gear - loss)
        return loss

    def _resolve_action(
        self,
        actor: discord.Member,
        action: dict,
        killed_this_round: set,
        elimination_log: dict[int, dict],
    ) -> str:
        kind = action["kind"]

        if kind == "scavenge":
            gain = random.randint(1, 2)
            if self.round == 1 and random.randint(1, 100) <= 30:
                gain += 1
            self.gear_score[actor.id] = min(10, self.gear_score[actor.id] + gain)
            return _("scavenges and upgrades to {gear}.").format(
                gear=self._weapon_name(self.gear_score[actor.id])
            )

        if kind == "hide":
            self.hidden_ids.add(actor.id)
            return _("vanishes into cover and stays hidden.")

        if kind == "trap":
            self.traps[actor.id] = min(4, self.traps[actor.id] + 1)
            return _("sets a trap. ({count} trap(s) active)").format(
                count=self.traps[actor.id]
            )

        target = self._alive_target(action.get("target_id"), killed_this_round)
        if target is None:
            return _("finds no valid target and wastes the move.")

        if kind == "teamup":
            self.gear_score[actor.id] = min(10, self.gear_score[actor.id] + 1)
            self.gear_score[target.id] = min(10, self.gear_score[target.id] + 1)
            self.hidden_ids.discard(target.id)
            return _("teams up with **{ally}** and both leave stronger.").format(
                ally=target.display_name
            )

        if kind == "betray":
            if self.round <= self.ALLIANCE_LOCK_ROUNDS:
                return _("hesitates. Alliances are still locked this round.")
            success_chance = min(90, 45 + self.gear_score[actor.id] * 7)
            if random.randint(1, 100) <= success_chance:
                self._mark_kill(
                    actor,
                    target,
                    killed_this_round,
                    elimination_log=elimination_log,
                    cause=_("was betrayed by **{killer}**").format(
                        killer=actor.display_name
                    ),
                )
                self.gear_score[actor.id] = min(10, self.gear_score[actor.id] + 1)
                return _("betrays **{ally}** and takes their loot.").format(
                    ally=target.display_name
                )
            if random.randint(1, 100) <= 50:
                self._mark_kill(
                    target,
                    actor,
                    killed_this_round,
                    elimination_log=elimination_log,
                    cause=_("was executed by **{killer}** during a failed betrayal").format(
                        killer=target.display_name
                    ),
                )
                return _("tries to betray **{ally}**, but gets executed first.").format(
                    ally=target.display_name
                )
            return _("tries to betray **{ally}**, but the moment passes.").format(
                ally=target.display_name
            )

        if kind == "hunt" and target.id in self.hidden_ids:
            return _("tries to hunt **{target}**, but they stay hidden.").format(
                target=target.display_name
            )

        if kind == "hunt" and self._check_trap_trigger(
            actor,
            target,
            killed_this_round,
            elimination_log,
            bonus_chance=20,
        ):
            return _("tracks **{target}** but triggers their trap and dies.").format(
                target=target.display_name
            )

        attacker_gear = self.gear_score[actor.id]
        target_gear = self.gear_score[target.id]
        target_traps = self.traps.get(target.id, 0)

        if kind == "hunt":
            chance = 32 + attacker_gear * 5 + min(14, self.round * 2)
            chance -= min(18, target_gear * 2)
            chance -= target_traps * 10
            if target.id in self.hidden_ids:
                chance -= 20
            chance = max(8, min(82, chance))
            if random.randint(1, 100) <= chance:
                self._mark_kill(
                    actor,
                    target,
                    killed_this_round,
                    elimination_log=elimination_log,
                    cause=_("was hunted down by **{killer}**").format(
                        killer=actor.display_name
                    ),
                )
                return _("hunts down **{target}** cleanly.").format(
                    target=target.display_name
                )
            counter_chance = min(72, 22 + target_gear * 4 + target_traps * 8)
            if random.randint(1, 100) <= counter_chance:
                self._mark_kill(
                    target,
                    actor,
                    killed_this_round,
                    elimination_log=elimination_log,
                    cause=_("was counter-killed by **{killer}**").format(
                        killer=target.display_name
                    ),
                )
                return _("misses **{target}** and gets counter-killed.").format(
                    target=target.display_name
                )
            return _("tracks **{target}** but loses them in the terrain.").format(
                target=target.display_name
            )

        if kind == "rush":
            chance = 36 + attacker_gear * 8 + min(10, self.round)
            chance -= min(24, target_gear * 3)
            if target.id in self.hidden_ids:
                chance -= 12
            chance = max(10, min(90, chance))
            if random.randint(1, 100) <= chance:
                self._mark_kill(
                    actor,
                    target,
                    killed_this_round,
                    elimination_log=elimination_log,
                    cause=_("was killed in a brawl by **{killer}**").format(
                        killer=actor.display_name
                    ),
                )
                if random.randint(1, 100) <= 35:
                    self._mark_kill(
                        None,
                        actor,
                        killed_this_round,
                        elimination_log=elimination_log,
                        cause=_("bled out after a reckless brawl"),
                    )
                    return _("rushes **{target}**, kills them, then bleeds out.").format(
                        target=target.display_name
                    )
                return _("rushes **{target}** and wins the brawl.").format(
                    target=target.display_name
                )
            counter_chance = 30 + target_gear * 3 - attacker_gear * 2
            counter_chance = max(18, min(62, counter_chance))
            if random.randint(1, 100) <= counter_chance:
                self._mark_kill(
                    target,
                    actor,
                    killed_this_round,
                    elimination_log=elimination_log,
                    cause=_("was dropped by **{killer}** in a rush attempt").format(
                        killer=target.display_name
                    ),
                )
                return _("rushes **{target}** and gets dropped instantly.").format(
                    target=target.display_name
                )
            return _("rushes **{target}** but neither can finish it.").format(
                target=target.display_name
            )

        return _("does something chaotic but pointless.")

    async def _resolve_arena_event(
        self,
        killed_this_round: set,
        round_lines: list[str],
        elimination_log: dict[int, dict],
    ) -> None:
        survivors = [p for p in self.players if p not in killed_this_round]
        if len(survivors) <= 1:
            return

        roll = random.randint(1, 100)
        if roll <= 30:
            loot_count = min(len(survivors), random.randint(1, min(3, len(survivors))))
            looters = random.sample(survivors, loot_count)
            for looter in looters:
                self.gear_score[looter.id] = min(10, self.gear_score[looter.id] + 1)
            round_lines.append(
                _("📦 A supply pod crashes down. {players} loot upgrades.").format(
                    players=nice_join([f"**{p.display_name}**" for p in looters])
                )
            )
            return

        if roll <= 58:
            candidates = [p for p in survivors if p.id not in self.hidden_ids] or survivors
            victim = random.choice(candidates)
            lethality = self._mutt_lethality_chance(
                victim, base_chance=72, min_chance=22
            )
            if random.randint(1, 100) <= lethality:
                self._mark_kill(
                    None,
                    victim,
                    killed_this_round,
                    elimination_log=elimination_log,
                    cause=_("was torn apart by mutts"),
                )
                round_lines.append(
                    _("🐺 Mutts swarm **{victim}** in the dark.").format(
                        victim=victim.display_name
                    )
                )
            else:
                loss = self._apply_mutt_gear_loss(victim)
                round_lines.append(
                    _(
                        "🐺 Mutts swarm **{victim}**, but they fight them off and lose {loss} gear level(s)."
                    ).format(victim=victim.display_name, loss=loss)
                )
            return

        if roll <= 82:
            vulnerable = [p for p in survivors if self.gear_score[p.id] <= 1]
            if vulnerable and random.randint(1, 100) <= 55:
                victim = random.choice(vulnerable)
                self._mark_kill(
                    None,
                    victim,
                    killed_this_round,
                    elimination_log=elimination_log,
                    cause=_("was consumed by toxic fog"),
                )
                round_lines.append(
                    _("☣️ Toxic fog rolls in. **{victim}** doesn't make it out.").format(
                        victim=victim.display_name
                    )
                )
            else:
                victim = random.choice(survivors)
                self.gear_score[victim.id] = max(0, self.gear_score[victim.id] - 1)
                round_lines.append(
                    _("🌧️ Acid rain shreds **{victim}**'s gear.").format(
                        victim=victim.display_name
                    )
                )
            return

        if len(survivors) >= 2:
            left, right = random.sample(survivors, 2)
            left_roll = self.gear_score[left.id] + random.randint(0, 3)
            right_roll = self.gear_score[right.id] + random.randint(0, 3)
            winner, loser = (left, right) if left_roll >= right_roll else (right, left)
            self._mark_kill(
                winner,
                loser,
                killed_this_round,
                elimination_log=elimination_log,
                cause=_("fell in an arena-event duel to **{killer}**").format(
                    killer=winner.display_name
                ),
            )
            round_lines.append(
                _("⚔️ Arena event: **{winner}** wins a sudden duel against **{loser}**.").format(
                    winner=winner.display_name,
                    loser=loser.display_name,
                )
            )

    def _force_showdown(
        self,
        killed_this_round: set,
        round_lines: list[str],
        elimination_log: dict[int, dict],
    ) -> None:
        survivors = [p for p in self.players if p not in killed_this_round]
        if len(survivors) < 2:
            return
        cross_team_pairs: list[tuple[discord.Member, discord.Member]] = []
        for idx, left in enumerate(survivors):
            left_team = self.team_by_player_id.get(left.id)
            for right in survivors[idx + 1 :]:
                right_team = self.team_by_player_id.get(right.id)
                if left_team == right_team:
                    continue
                cross_team_pairs.append((left, right))
        if not cross_team_pairs:
            return
        left, right = random.choice(cross_team_pairs)
        left_roll = self.gear_score[left.id] + random.randint(1, 4)
        right_roll = self.gear_score[right.id] + random.randint(1, 4)
        winner, loser = (left, right) if left_roll >= right_roll else (right, left)
        self._mark_kill(
            winner,
            loser,
            killed_this_round,
            elimination_log=elimination_log,
            cause=_("lost a forced showdown to **{killer}**").format(
                killer=winner.display_name
            ),
        )
        round_lines.append(
            _("💥 The silence breaks. **{winner}** wins a forced showdown against **{loser}**.").format(
                winner=winner.display_name,
                loser=loser.display_name,
            )
        )

    def _split_report(self, lines: list[str], max_chars: int = 3800) -> list[str]:
        if not lines:
            return [_("No major events this round.")]

        pages = []
        current = []
        current_len = 0
        for line in lines:
            projected = current_len + len(line) + 1
            if current and projected > max_chars:
                pages.append("\n".join(current))
                current = [line]
                current_len = len(line)
            else:
                current.append(line)
                current_len = projected
        if current:
            pages.append("\n".join(current))
        return pages

    def _top_killers_text(self) -> str:
        leaders = [
            (player_id, kills)
            for player_id, kills in self.kills.items()
            if kills > 0 and player_id in self.member_by_id
        ]
        if not leaders:
            return _("No kills yet")
        leaders.sort(key=lambda item: item[1], reverse=True)
        top = leaders[:3]
        return ", ".join(
            f"{self.member_by_id[player_id].display_name} ({kills})"
            for player_id, kills in top
        )

    def _single_team_left(self, killed_this_round: set | None = None) -> bool:
        if killed_this_round is None:
            survivors = list(self.players)
        else:
            survivors = [p for p in self.players if p not in killed_this_round]
        if len(survivors) < 2:
            return False
        team_ids = {self.team_by_player_id.get(player.id) for player in survivors}
        return len(team_ids) == 1

    def _district_name(self, player: discord.Member) -> str:
        district = self.team_by_player_id.get(player.id)
        if district is None:
            return _("Unknown District")
        return _("District {district}").format(district=district)

    def _alive_districts_text(self) -> str:
        districts = sorted(
            {
                self.team_by_player_id.get(player.id)
                for player in self.players
                if self.team_by_player_id.get(player.id) is not None
            }
        )
        if not districts:
            return _("None")
        return ", ".join(f"#{district}" for district in districts)

    async def _send_round_report(
        self,
        round_lines: list[str],
        killed_this_round: set,
        elimination_log: dict[int, dict],
    ) -> None:
        lock_state = (
            _("active until round {round}").format(round=self.ALLIANCE_LOCK_ROUNDS + 1)
            if self.round <= self.ALLIANCE_LOCK_ROUNDS
            else _("broken")
        )

        event_lines = [f"{idx}. {line}" for idx, line in enumerate(round_lines, start=1)]
        event_pages = self._split_report(event_lines)
        for idx, page in enumerate(event_pages, start=1):
            title = _("Hunger Games - Round {round} Arena Log").format(round=self.round)
            if len(event_pages) > 1:
                title = f"{title} ({idx}/{len(event_pages)})"
            await self.ctx.send(
                embed=discord.Embed(
                    title=title,
                    description=page,
                    color=discord.Color.orange(),
                )
            )
            if idx < len(event_pages):
                await asyncio.sleep(self.REPORT_SECTION_DELAY_SECONDS)

        await asyncio.sleep(self.REPORT_SECTION_DELAY_SECONDS)

        if killed_this_round:
            cannon_intro = _(
                "💥 **{shots} cannon shot(s)** were heard in the arena."
            ).format(shots=len(killed_this_round))
            await self.ctx.send(
                embed=discord.Embed(
                    title=_("🔔 Cannon Shots - Round {round}").format(round=self.round),
                    description=cannon_intro,
                    color=discord.Color.red(),
                )
            )
            await asyncio.sleep(self.REPORT_SECTION_DELAY_SECONDS)

            fallen_entries = [
                data
                for data in elimination_log.values()
                if isinstance(data.get("victim"), discord.Member)
            ]
            total_fallen = len(fallen_entries)
            for idx, data in enumerate(fallen_entries, start=1):
                victim = data["victim"]
                killer = data.get("killer")
                cause = str(data.get("cause", _("eliminated in the chaos")))
                killer_text = (
                    killer.display_name
                    if isinstance(killer, discord.Member)
                    else _("the arena")
                )

                tribute_embed = discord.Embed(
                    title=_("☠️ {victim} has fallen").format(
                        victim=victim.display_name
                    ),
                    description=_(
                        "**{district}**\n"
                        "**Cause:** {cause}\n"
                        "**Felled by:** {killer}"
                    ).format(
                        district=self._district_name(victim),
                        cause=cause,
                        killer=killer_text,
                    ),
                    color=discord.Color.dark_red(),
                )
                tribute_embed.set_thumbnail(url=victim.display_avatar.url)
                tribute_embed.set_footer(
                    text=_("Round {round} • Tribute {idx}/{total}").format(
                        round=self.round,
                        idx=idx,
                        total=total_fallen,
                    )
                )
                await self.ctx.send(
                    embed=tribute_embed
                )
                if idx < total_fallen:
                    await asyncio.sleep(self.REPORT_TRIBUTE_DELAY_SECONDS)
        else:
            await self.ctx.send(
                embed=discord.Embed(
                    title=_("🔔 Cannon Shots - Round {round}").format(round=self.round),
                    description=_("No cannon shots tonight. No one fell."),
                    color=discord.Color.red(),
                )
            )

        await asyncio.sleep(self.REPORT_SECTION_DELAY_SECONDS)

        status_lines = [
            _("🧍 Alive now: **{alive}**").format(alive=len(self.players)),
            _("🏙️ Districts still standing: {districts}").format(
                districts=self._alive_districts_text()
            ),
            _("🤝 Alliance lock: **{state}**").format(state=lock_state),
        ]
        await self.ctx.send(
            embed=discord.Embed(
                title=_("Round {round} Status").format(round=self.round),
                description="\n".join(status_lines),
                color=discord.Color.blurple(),
            )
        )

    async def get_inputs(self):
        status = await self.ctx.send(
            _("🔥 **Round {round}** begins...").format(round=self.round),
            delete_after=45,
        )
        self.hidden_ids = set()
        killed_this_round: set[discord.Member] = set()
        round_lines: list[str] = []
        elimination_log: dict[int, dict] = {}

        turn_order = self.players.copy()
        turn_order = random.shuffle(turn_order)
        for actor in turn_order:
            if actor not in self.players or actor in killed_this_round:
                continue
            choices = self._build_action_choices(actor, killed_this_round)
            if not choices:
                continue
            action = await self._choose_action(actor, choices)
            summary = self._resolve_action(actor, action, killed_this_round, elimination_log)
            round_lines.append(f"**{actor.display_name}** {summary}")

        await self._resolve_arena_event(killed_this_round, round_lines, elimination_log)

        for dead in list(killed_this_round):
            try:
                self.players.remove(dead)
            except ValueError:
                pass

        try:
            await status.delete()
        except discord.NotFound:
            pass
        await self._send_round_report(round_lines, killed_this_round, elimination_log)
        self.round += 1

    async def send_cast(self):
        cast = self.players.copy()
        cast = random.shuffle(cast)
        self.cast = list(chunks(cast, 2))

        self.team_by_player_id.clear()
        for idx, team in enumerate(self.cast, start=1):
            team_ids = {member.id for member in team}
            for member in team:
                self.team_by_player_id[member.id] = idx
                self.allies_by_player_id[member.id] = team_ids - {member.id}

        lines = []
        for idx, team in enumerate(self.cast, start=1):
            mentions = " ".join(member.mention for member in team)
            lines.append(f"**District #{idx}:** {mentions}")

        pages = self._split_report(lines)
        for idx, page in enumerate(pages, start=1):
            title = _("The Cast")
            if len(pages) > 1:
                title = f"{title} ({idx}/{len(pages)})"
            embed = discord.Embed(
                title=title,
                description=page,
                color=discord.Color.blue(),
            )
            if idx == 1:
                embed.set_footer(
                    text=_(
                        "District alliances are protected until round {round}. Betrayals unlock after that. DM the bot to relay messages to your living district teammate."
                    ).format(round=self.ALLIANCE_LOCK_ROUNDS)
                )
            await self.ctx.send(embed=embed)
        await self._send_team_relay_opening_dms()

    async def _send_team_relay_opening_dms(self) -> None:
        for team in self.cast:
            if len(team) < 2:
                continue
            for member in team:
                teammates = [ally for ally in team if ally.id != member.id]
                if not teammates:
                    continue

                teammate_text = nice_join([ally.display_name for ally in teammates])
                lines = [
                    _("🤝 District relay is now open."),
                    _("Teammate: {teammates}").format(teammates=teammate_text),
                    _(
                        "DM this bot anytime and your message will be forwarded to your living district teammate."
                    ),
                ]

                # Region modes include teammate region intel in the opening DM.
                if hasattr(self, "_region_for"):
                    try:
                        teammate_regions = ", ".join(
                            _("{name}: {region}").format(
                                name=ally.display_name,
                                region=self._region_for(ally),  # type: ignore[attr-defined]
                            )
                            for ally in teammates
                        )
                    except Exception:
                        teammate_regions = ""
                    if teammate_regions:
                        lines.append(
                            _("Current teammate location: {info}").format(
                                info=teammate_regions
                            )
                        )

                try:
                    await member.send("\n".join(lines))
                except (discord.Forbidden, discord.HTTPException):
                    continue

    def _final_leaderboard_lines(self) -> list[str]:
        leaders = [
            (player_id, kills)
            for player_id, kills in self.kills.items()
            if player_id in self.member_by_id
        ]
        leaders.sort(key=lambda item: item[1], reverse=True)
        top = leaders[:5]
        return [
            f"#{idx}. {self.member_by_id[player_id].mention} - {kills} kill(s)"
            for idx, (player_id, kills) in enumerate(top, start=1)
        ]

    async def main(self):
        self.round = 1
        await self.send_cast()
        while len(self.players) > 1 and not self._single_team_left():
            await self.get_inputs()
            await asyncio.sleep(2)

        if len(self.players) > 1 and self._single_team_left():
            team_id = self.team_by_player_id.get(self.players[0].id)
            winners = list(self.players)
            embed = discord.Embed(
                title=_("Hunger Games Results"),
                color=discord.Color.blurple(),
                description=_("District #{team} wins together!").format(team=team_id),
            )
            embed.add_field(
                name=_("Survivors"),
                value=nice_join([winner.mention for winner in winners]),
                inline=False,
            )
            embed.set_thumbnail(url=winners[0].display_avatar.url)
        elif len(self.players) == 1:
            winner = self.players[0]
            embed = discord.Embed(
                title=_("Hunger Games Results"),
                color=discord.Color.green(),
                description=_("This Hunger Games winner is {winner}!").format(
                    winner=winner.mention
                ),
            )
            embed.set_thumbnail(url=winner.display_avatar.url)
            embed.add_field(
                name=_("Winner Loadout"),
                value=self._weapon_name(self.gear_score.get(winner.id, 0)),
                inline=False,
            )
        else:
            embed = discord.Embed(
                title=_("Hunger Games Results"),
                color=discord.Color.red(),
                description=_("Everyone died!"),
            )
            embed.set_thumbnail(
                url=(
                    "https://64.media.tumblr.com/688393f27c7e1bf442a5a0edc81d41b5/"
                    "ee1cd685d21520b0-f9/s500x750/4237c55e0f8b85cb943f6e7adb5562866a54ff2a.gif"
                )
            )

        leaderboard = self._final_leaderboard_lines()
        if leaderboard:
            embed.add_field(
                name=_("Kill Leaderboard"),
                value="\n".join(leaderboard),
                inline=False,
            )
        await self.ctx.send(embed=embed)


class RegionGame(GameBase):
    PLAYER_CONTROL_CHANCE = 100
    REPORT_SECTION_DELAY_SECONDS = 1.0
    REPORT_TRIBUTE_DELAY_SECONDS = 0.75
    STALEMATE_ROUNDS = 3
    REGIONS: tuple[str, ...] = (
        "Cornucopia",
        "Forest Ridge",
        "Riverbank",
        "Ruined Mill",
        "Stone Quarry",
        "Underground Tunnels",
    )
    REGION_ADJACENCY: dict[str, tuple[str, ...]] = {
        "Cornucopia": ("Forest Ridge", "Riverbank", "Ruined Mill"),
        "Forest Ridge": ("Cornucopia", "Stone Quarry"),
        "Riverbank": ("Cornucopia", "Underground Tunnels"),
        "Ruined Mill": ("Cornucopia", "Stone Quarry", "Underground Tunnels"),
        "Stone Quarry": ("Forest Ridge", "Ruined Mill"),
        "Underground Tunnels": ("Riverbank", "Ruined Mill"),
    }

    def __init__(self, ctx, players: list):
        super().__init__(ctx, players)
        self.player_region: dict[int, str] = {}
        self.region_drops: dict[str, int] = {}
        self.active_toxic_regions: set[str] = set()
        self.next_toxic_regions: set[str] = set()
        self.active_mutt_regions: set[str] = set()
        self.next_mutt_regions: set[str] = set()
        self.fog_stage = 1
        self.no_kill_rounds = 0
        self._assign_initial_regions()

    def _assign_initial_regions(self) -> None:
        pool = list(self.REGIONS)
        for player in self.players:
            if not pool:
                pool = list(self.REGIONS)
            region = random.choice(pool)
            pool.remove(region)
            self.player_region[player.id] = region

    def _region_for(self, player: discord.Member) -> str:
        if player.id not in self.player_region:
            self.player_region[player.id] = random.choice(list(self.REGIONS))
        return self.player_region[player.id]

    def _players_in_region(
        self, region: str, *, killed_this_round: set | None = None
    ) -> list[discord.Member]:
        killed_this_round = killed_this_round or set()
        return [
            player
            for player in self.players
            if player not in killed_this_round and self._region_for(player) == region
        ]

    def _eligible_targets(
        self,
        actor: discord.Member,
        killed_this_round: set,
        *,
        allow_allies: bool = False,
    ) -> list[discord.Member]:
        actor_region = self._region_for(actor)
        base_targets = super()._eligible_targets(
            actor, killed_this_round, allow_allies=allow_allies
        )
        return [target for target in base_targets if self._region_for(target) == actor_region]

    def _alive_allies(
        self,
        actor: discord.Member,
        killed_this_round: set,
    ) -> list[discord.Member]:
        actor_region = self._region_for(actor)
        allies = super()._alive_allies(actor, killed_this_round)
        return [ally for ally in allies if self._region_for(ally) == actor_region]

    def _is_under_escape_pressure(self, region: str) -> bool:
        return (
            region in self.active_toxic_regions
            or region in self.next_toxic_regions
            or region in self.active_mutt_regions
            or region in self.next_mutt_regions
        )

    def _escape_move_choices(
        self,
        actor: discord.Member,
        killed_this_round: set,
    ) -> list[dict]:
        current_region = self._region_for(actor)
        if not self._is_under_escape_pressure(current_region):
            return []

        neighbors = list(self.REGION_ADJACENCY.get(current_region, ()))
        if not neighbors:
            return []

        def region_risk(region: str) -> tuple[int, int, str]:
            risk = 0
            if region in self.active_toxic_regions:
                risk += 6
            if region in self.active_mutt_regions:
                risk += 4
            if region in self.next_toxic_regions:
                risk += 2
            if region in self.next_mutt_regions:
                risk += 1
            crowd = len(self._players_in_region(region, killed_this_round=killed_this_round))
            return (risk, crowd, region)

        ordered_regions = sorted(neighbors, key=region_risk)
        return [
            {
                "label": _("Move to {region}").format(region=region),
                "kind": "move",
                "region": region,
            }
            for region in ordered_regions
        ]

    def _ensure_escape_route_choices(
        self,
        actor: discord.Member,
        killed_this_round: set,
        selected: list[dict],
    ) -> list[dict]:
        if any(choice.get("kind") == "move" for choice in selected):
            return selected

        emergency_moves = self._escape_move_choices(actor, killed_this_round)
        if not emergency_moves:
            return selected

        existing_regions = {
            str(choice.get("region"))
            for choice in selected
            if choice.get("kind") == "move"
        }
        for move_choice in emergency_moves:
            region = str(move_choice.get("region"))
            if region in existing_regions:
                continue
            selected.append(move_choice)
            existing_regions.add(region)
        return selected

    def _spawn_region_drops(self) -> None:
        self.region_drops.clear()
        available_regions = [
            region for region in self.REGIONS if region not in self.active_toxic_regions
        ]
        if not available_regions:
            return
        alive = len(self.players)
        if alive >= 10:
            base_drop_count = 3
        elif alive >= 6:
            base_drop_count = 2
        else:
            base_drop_count = 1
        pressure_penalty = 1 if len(self.active_toxic_regions) >= 2 else 0
        drop_count = max(1, base_drop_count - pressure_penalty)
        picked = random.sample(
            available_regions, k=min(drop_count, len(available_regions))
        )
        early_round = self.round <= 3
        for region in picked:
            self.region_drops[region] = random.randint(1, 2) if early_round else random.randint(2, 3)

    def _pick_next_toxic_regions(self) -> set[str]:
        safe_regions = [
            region for region in self.REGIONS if region not in self.active_toxic_regions
        ]
        if len(safe_regions) <= 1:
            return set()
        alive = len(self.players)
        if self.round <= 2:
            toxic_count = 1
        elif alive >= 9:
            toxic_count = 2
        elif alive >= 5:
            toxic_count = 1
        else:
            toxic_count = 2
        toxic_count = min(toxic_count, len(safe_regions) - 1)
        return set(random.sample(safe_regions, toxic_count))

    async def _send_region_brief(self) -> None:
        lines = []
        for region in self.REGIONS:
            alive_count = len(self._players_in_region(region))
            status_bits = [f"👥 {alive_count}"]
            if region in self.region_drops:
                status_bits.append("📦 Drop")
            if region in self.active_toxic_regions:
                status_bits.append("☣️ Toxic Now")
            elif region in self.next_toxic_regions:
                status_bits.append("⚠️ Toxic Next")
            if region in self.active_mutt_regions:
                status_bits.append("🐺 Mutts Now")
            elif region in self.next_mutt_regions:
                status_bits.append("🐾 Mutts Next")
            status = " • ".join(status_bits)
            lines.append(f"**{region}**: {status}")

        active_toxic = (
            ", ".join(sorted(self.active_toxic_regions))
            if self.active_toxic_regions
            else _("None")
        )
        next_toxic = (
            ", ".join(sorted(self.next_toxic_regions))
            if self.next_toxic_regions
            else _("None")
        )
        active_mutts = (
            ", ".join(sorted(self.active_mutt_regions))
            if self.active_mutt_regions
            else _("None")
        )
        next_mutts = (
            ", ".join(sorted(self.next_mutt_regions))
            if self.next_mutt_regions
            else _("None")
        )

        embed = discord.Embed(
            title=_("🗺️ Arena Regions - Round {round}").format(round=self.round),
            description="\n".join(lines),
            color=discord.Color.dark_gold(),
        )
        embed.add_field(name=_("Toxic Now"), value=active_toxic, inline=False)
        embed.add_field(name=_("Prewarned Next Round"), value=next_toxic, inline=False)
        embed.add_field(name=_("Mutts This Round"), value=active_mutts, inline=False)
        embed.add_field(name=_("Mutt Warning Next"), value=next_mutts, inline=False)
        embed.set_footer(
            text=_(
                "Move between connected regions, loot drops, and survive the advancing fog."
            )
        )
        await self.ctx.send(embed=embed)
        await self._send_region_brief_dms(embed)

    async def _send_region_brief_dms(self, embed: discord.Embed) -> None:
        cog = self.ctx.bot.get_cog("HungerGames")
        if cog is None or not hasattr(cog, "region_board_dm_enabled"):
            return
        for player in list(self.players):
            try:
                enabled = await cog.region_board_dm_enabled(player.id)
            except Exception:
                enabled = True
            if not enabled:
                continue
            try:
                await player.send(embed=embed)
            except (discord.Forbidden, discord.HTTPException):
                continue

    def _build_action_choices(
        self,
        actor: discord.Member,
        killed_this_round: set,
    ) -> list[dict]:
        current_region = self._region_for(actor)
        choices: list[dict] = [
            {"label": _("Scavenge for weapons in {region}").format(region=current_region), "kind": "scavenge"},
            {"label": _("Hide in {region}").format(region=current_region), "kind": "hide"},
            {"label": _("Set a trap in {region}").format(region=current_region), "kind": "trap"},
        ]

        neighbors = list(self.REGION_ADJACENCY.get(current_region, ()))
        for region in neighbors:
            choices.append(
                {
                    "label": _("Move to {region}").format(region=region),
                    "kind": "move",
                    "region": region,
                }
            )

        if current_region in self.region_drops:
            choices.append(
                {
                    "label": _("Loot the supply drop in {region}").format(
                        region=current_region
                    ),
                    "kind": "lootdrop",
                }
            )

        targets = self._eligible_targets(actor, killed_this_round)
        if targets:
            hunt_target = random.choice(targets)
            rush_target = random.choice(targets)
            choices.append(
                {
                    "label": _("Hunt down {target} in {region}").format(
                        target=hunt_target.display_name, region=current_region
                    ),
                    "kind": "hunt",
                    "target_id": hunt_target.id,
                }
            )
            choices.append(
                {
                    "label": _("Rush {target} in {region}").format(
                        target=rush_target.display_name, region=current_region
                    ),
                    "kind": "rush",
                    "target_id": rush_target.id,
                }
            )

        allies = self._alive_allies(actor, killed_this_round)
        if allies:
            ally = random.choice(allies)
            choices.append(
                {
                    "label": _("Coordinate with {ally} in {region}").format(
                        ally=ally.display_name,
                        region=current_region,
                    ),
                    "kind": "teamup",
                    "target_id": ally.id,
                }
            )
            if self.round > self.ALLIANCE_LOCK_ROUNDS:
                choices.append(
                    {
                        "label": _("Betray {ally} in {region}").format(
                            ally=ally.display_name,
                            region=current_region,
                        ),
                        "kind": "betray",
                        "target_id": ally.id,
                    }
                )

        sample_size = min(4, len(choices))
        picked = random.sample(choices, sample_size)
        return self._ensure_escape_route_choices(actor, killed_this_round, picked)

    def _teammate_intel_prompt(self, actor: discord.Member) -> str:
        ally_ids = self.allies_by_player_id.get(actor.id, set())
        if not ally_ids:
            return _("No district teammate.")

        alive_allies = []
        for ally_id in sorted(ally_ids):
            ally = self.member_by_id.get(ally_id)
            if ally is None or ally not in self.players:
                continue
            alive_allies.append(ally)
        if not alive_allies:
            return _("No district teammate alive.")

        return ", ".join(
            _("{ally}: {region}").format(
                ally=ally.display_name,
                region=self._region_for(ally),
            )
            for ally in alive_allies
        )

    async def _choose_action(self, actor: discord.Member, choices: list[dict]) -> dict:
        teammate_intel = self._teammate_intel_prompt(actor)
        try:
            idx = await self.ctx.bot.paginator.Choose(
                entries=[choice["label"] for choice in choices],
                return_index=True,
                title=_(
                    "Choose your arena action\nTeammate intel: {intel}\nBack to game: {link}"
                ).format(
                    intel=teammate_intel,
                    link=self.game_channel_link
                ),
                timeout=self.ACTION_TIMEOUT_SECONDS,
            ).paginate(self.ctx, location=actor)
            return choices[idx]
        except (
            self.ctx.bot.paginator.NoChoice,
            discord.Forbidden,
            asyncio.TimeoutError,
        ):
            await self.ctx.send(
                _(
                    "{user} didn't choose in time. The arena decides their move."
                ).format(user=actor.mention),
                delete_after=20,
            )
            return random.choice(choices)

    def _resolve_action(
        self,
        actor: discord.Member,
        action: dict,
        killed_this_round: set,
        elimination_log: dict[int, dict],
    ) -> str:
        kind = action["kind"]
        actor_region = self._region_for(actor)

        if kind == "move":
            new_region = str(action.get("region") or "")
            if new_region not in self.REGION_ADJACENCY.get(actor_region, ()):
                return _("tries to move, but gets turned around in the arena.")
            abandoned = self.traps.get(actor.id, 0)
            if abandoned > 0:
                self.traps[actor.id] = 0
            self.player_region[actor.id] = new_region
            if abandoned > 0:
                return _(
                    "moves from **{old}** to **{new}**, abandoning {count} trap(s)."
                ).format(
                    old=actor_region,
                    new=new_region,
                    count=abandoned,
                )
            return _("moves from **{old}** to **{new}**.").format(
                old=actor_region,
                new=new_region,
            )

        if kind == "lootdrop":
            if actor_region not in self.region_drops:
                return _("searches for a drop in **{region}**, but it's gone.").format(
                    region=actor_region
                )
            gain = self.region_drops.pop(actor_region)
            self.gear_score[actor.id] = min(10, self.gear_score[actor.id] + gain)
            return _("claims the supply drop in **{region}** and upgrades gear.").format(
                region=actor_region
            )

        if kind in {"hunt", "rush", "teamup", "betray"}:
            target = self._alive_target(action.get("target_id"), killed_this_round)
            if target is None:
                return _("finds no valid target and wastes the move.")
            if self._region_for(target) != actor_region:
                return _("targets **{target}**, but they already moved away from **{region}**.").format(
                    target=target.display_name,
                    region=actor_region,
                )

        return super()._resolve_action(actor, action, killed_this_round, elimination_log)

    async def _resolve_arena_event(
        self,
        killed_this_round: set,
        round_lines: list[str],
        elimination_log: dict[int, dict],
    ) -> None:
        survivors = [p for p in self.players if p not in killed_this_round]
        if len(survivors) <= 1:
            return

        if self.active_mutt_regions:
            active_candidates = [
                region
                for region in sorted(self.active_mutt_regions)
                if len(
                    self._players_in_region(
                        region, killed_this_round=killed_this_round
                    )
                )
                >= 2
            ]
            if active_candidates:
                region = random.choice(active_candidates)
                candidates = self._players_in_region(
                    region, killed_this_round=killed_this_round
                )
                victim = random.choice(candidates)
                lethality = self._mutt_lethality_chance(
                    victim, base_chance=76, min_chance=24
                )
                self.active_mutt_regions.clear()
                if random.randint(1, 100) <= lethality:
                    self._mark_kill(
                        None,
                        victim,
                        killed_this_round,
                        elimination_log=elimination_log,
                        cause=_("was torn apart by mutts in **{region}**").format(
                            region=region
                        ),
                    )
                    round_lines.append(
                        _("🐺 Mutts ambush **{victim}** in **{region}**.").format(
                            victim=victim.display_name,
                            region=region,
                        )
                    )
                else:
                    loss = self._apply_mutt_gear_loss(victim)
                    round_lines.append(
                        _(
                            "🐺 Mutts ambush **{victim}** in **{region}**, but they escape and lose {loss} gear level(s)."
                        ).format(
                            victim=victim.display_name,
                            region=region,
                            loss=loss,
                        )
                    )
                return

            faded_regions = sorted(self.active_mutt_regions)
            self.active_mutt_regions.clear()
            round_lines.append(
                _(
                    "🐾 Mutt warning fades in {regions}. No crowded targets remain."
                ).format(
                    regions=nice_join([f"**{region}**" for region in faded_regions])
                )
            )
            return

        roll = random.randint(1, 100)
        if roll <= 45:
            candidate_regions = [
                region for region in self.REGIONS if self._players_in_region(region, killed_this_round=killed_this_round)
            ]
            if not candidate_regions:
                return
            region = random.choice(candidate_regions)
            existing = self.region_drops.get(region, 0)
            self.region_drops[region] = max(existing, random.randint(2, 3))
            round_lines.append(
                _("🎁 A sponsor drone drops fresh supplies in **{region}**.").format(
                    region=region
                )
            )
            return

        if roll <= 78:
            crowded_regions = [
                region
                for region in self.REGIONS
                if len(self._players_in_region(region, killed_this_round=killed_this_round)) >= 2
            ]
            if not crowded_regions:
                return
            region = random.choice(crowded_regions)
            self.next_mutt_regions = {region}
            round_lines.append(
                _(
                    "🐾 Growls echo from **{region}**. Mutts are gathering and may strike there next round if two or more tributes stay."
                ).format(region=region)
            )
            return

        region = random.choice(list(self.REGIONS))
        impacted = self._players_in_region(region, killed_this_round=killed_this_round)
        if not impacted:
            return
        victim = random.choice(impacted)
        self.gear_score[victim.id] = max(0, self.gear_score[victim.id] - 1)
        round_lines.append(
            _("🌧️ Acid rain lashes **{region}**. **{victim}** loses gear.").format(
                region=region,
                victim=victim.display_name,
            )
        )

    def _force_showdown(
        self,
        killed_this_round: set,
        round_lines: list[str],
        elimination_log: dict[int, dict],
    ) -> None:
        # In region mode, forced showdowns only happen between tributes in the
        # same region and never between district teammates.
        cross_team_pairs: list[tuple[str, discord.Member, discord.Member]] = []
        for region in self.REGIONS:
            contenders = self._players_in_region(region, killed_this_round=killed_this_round)
            if len(contenders) < 2:
                continue
            for idx, left in enumerate(contenders):
                left_team = self.team_by_player_id.get(left.id)
                for right in contenders[idx + 1 :]:
                    right_team = self.team_by_player_id.get(right.id)
                    if left_team == right_team:
                        continue
                    cross_team_pairs.append((region, left, right))
        if not cross_team_pairs:
            return
        region, left, right = random.choice(cross_team_pairs)
        left_roll = self.gear_score[left.id] + random.randint(1, 4)
        right_roll = self.gear_score[right.id] + random.randint(1, 4)
        winner, loser = (left, right) if left_roll >= right_roll else (right, left)
        self._mark_kill(
            winner,
            loser,
            killed_this_round,
            elimination_log=elimination_log,
            cause=_("lost a forced showdown in **{region}** to **{killer}**").format(
                region=region,
                killer=winner.display_name,
            ),
        )
        round_lines.append(
            _(
                "💥 The silence breaks in **{region}**. **{winner}** wins a forced"
                " showdown against **{loser}**."
            ).format(
                region=region,
                winner=winner.display_name,
                loser=loser.display_name,
            )
        )

    def _resolve_stalemate(
        self,
        killed_this_round: set,
        round_lines: list[str],
        elimination_log: dict[int, dict],
    ) -> None:
        if self.no_kill_rounds < self.STALEMATE_ROUNDS:
            return
        survivors = [p for p in self.players if p not in killed_this_round]
        if len(survivors) <= 1:
            return

        round_lines.append(
            _(
                "🕛 {rounds} bloodless rounds. The Gamemakers trigger Sudden Death."
            ).format(rounds=self.no_kill_rounds)
        )
        for survivor in survivors:
            self.player_region[survivor.id] = "Cornucopia"
        round_lines.append(
            _(
                "🚨 Sirens blare. Remaining tributes are forced into **Cornucopia**."
            )
        )
        self._force_showdown(killed_this_round, round_lines, elimination_log)

    def _apply_toxic_fog(
        self,
        killed_this_round: set,
        round_lines: list[str],
        elimination_log: dict[int, dict],
    ) -> None:
        if not self.active_toxic_regions:
            return
        for player in list(self.players):
            if player in killed_this_round:
                continue
            region = self._region_for(player)
            if region not in self.active_toxic_regions:
                continue
            alive = len(self.players)
            chance = 10 + self.fog_stage * 8
            if alive <= 4:
                chance += 14
            elif alive <= 6:
                chance += 8
            elif alive <= 8:
                chance += 4
            if player.id in self.hidden_ids:
                chance = max(5, chance - 8)
            chance = max(5, chance - min(14, self.gear_score[player.id] * 2))
            chance = min(88, chance)

            if random.randint(1, 100) <= chance:
                self._mark_kill(
                    None,
                    player,
                    killed_this_round,
                    elimination_log=elimination_log,
                    cause=_("succumbed to toxic fog in **{region}**").format(
                        region=region
                    ),
                )
                round_lines.append(
                    _("☣️ Toxic fog engulfs **{victim}** in **{region}**.").format(
                        victim=player.display_name,
                        region=region,
                    )
                )
            else:
                self.gear_score[player.id] = max(0, self.gear_score[player.id] - 1)
                round_lines.append(
                    _("☣️ **{survivor}** escapes the fog in **{region}**, but loses gear.").format(
                        survivor=player.display_name,
                        region=region,
                    )
                )

    async def _send_round_report(
        self,
        round_lines: list[str],
        killed_this_round: set,
        elimination_log: dict[int, dict],
    ) -> None:
        await super()._send_round_report(round_lines, killed_this_round, elimination_log)
        extra = discord.Embed(
            title=_("Next Round Hazard Preview"),
            description=_(
                "☣️ Toxic at round start: {next_regions}\n"
                "🐺 Mutt pressure at round start: {next_mutts}\n"
                "📦 Sponsor drops reroll at round start."
            ).format(
                next_regions=", ".join(sorted(self.next_toxic_regions))
                if self.next_toxic_regions
                else _("None"),
                next_mutts=", ".join(sorted(self.next_mutt_regions))
                if self.next_mutt_regions
                else _("None"),
            ),
            color=discord.Color.dark_teal(),
        )
        await self.ctx.send(embed=extra)

    async def send_cast(self):
        await super().send_cast()
        await self.ctx.send(
            embed=discord.Embed(
                title=_("Region Rules"),
                description=_(
                    "Each tribute starts in a region. You can move only to connected"
                    " regions, fight only in your current region, and race for sponsor"
                    " drops. Toxic fog zones are prewarned one round early."
                ),
                color=discord.Color.gold(),
            )
        )

    async def get_inputs(self):
        status = await self.ctx.send(
            _("🔥 **Round {round}** begins...").format(round=self.round),
            delete_after=45,
        )
        self.hidden_ids = set()
        killed_this_round: set[discord.Member] = set()
        round_lines: list[str] = []
        elimination_log: dict[int, dict] = {}

        self.active_toxic_regions = set(self.next_toxic_regions)
        self.active_mutt_regions = set(self.next_mutt_regions)
        self.fog_stage = max(1, min(6, 1 + (self.round - 1) // 2))
        self._spawn_region_drops()
        self.next_toxic_regions = self._pick_next_toxic_regions()
        self.next_mutt_regions = set()
        await self._send_region_brief()

        # Everyone receives action choices at once, then we resolve in random initiative.
        actors = [actor for actor in self.players if actor not in killed_this_round]
        choices_by_actor_id: dict[int, list[dict]] = {}
        for actor in actors:
            choices = self._build_action_choices(actor, killed_this_round)
            if choices:
                choices_by_actor_id[actor.id] = choices

        async def choose_for_actor(
            actor: discord.Member, choices: list[dict]
        ) -> tuple[discord.Member, dict | None]:
            if not choices:
                return actor, None
            action = await self._choose_action(actor, choices)
            return actor, action

        selected_actions_by_actor_id: dict[int, dict] = {}
        choose_tasks = [
            choose_for_actor(actor, choices_by_actor_id.get(actor.id, []))
            for actor in actors
            if actor.id in choices_by_actor_id
        ]
        if choose_tasks:
            await self.ctx.send(
                _("📩 Action prompts sent to all tributes. Choices lock together.")
            )
            for actor, action in await asyncio.gather(*choose_tasks):
                if action is not None:
                    selected_actions_by_actor_id[actor.id] = action
            await self.ctx.send(_("⏳ Action phase closed. Resolving round..."))

        turn_order = actors.copy()
        turn_order = random.shuffle(turn_order)
        for actor in turn_order:
            if actor not in self.players or actor in killed_this_round:
                continue
            action = selected_actions_by_actor_id.get(actor.id)
            if action is None:
                fallback_choices = choices_by_actor_id.get(actor.id, [])
                if not fallback_choices:
                    continue
                action = random.choice(fallback_choices)
            summary = self._resolve_action(actor, action, killed_this_round, elimination_log)
            round_lines.append(f"**{actor.display_name}** {summary}")

        await self._resolve_arena_event(killed_this_round, round_lines, elimination_log)
        self._apply_toxic_fog(killed_this_round, round_lines, elimination_log)

        if killed_this_round:
            self.no_kill_rounds = 0
        else:
            self.no_kill_rounds += 1
            await self._resolve_stalemate_with_gm(
                killed_this_round,
                round_lines,
                elimination_log,
            )
            if killed_this_round:
                self.no_kill_rounds = 0

        for dead in list(killed_this_round):
            try:
                self.players.remove(dead)
            except ValueError:
                pass

        try:
            await status.delete()
        except discord.NotFound:
            pass
        await self._send_round_report(round_lines, killed_this_round, elimination_log)
        self.round += 1


class RegionGMRegionSelect(discord.ui.Select):
    def __init__(
        self,
        panel,
        *,
        selection_key: str,
        placeholder: str,
        max_allowed: int,
        row: int,
    ) -> None:
        self.panel = panel
        self.selection_key = selection_key
        self.max_allowed = max_allowed
        super().__init__(
            placeholder=placeholder,
            min_values=1,
            max_values=max_allowed,
            options=[discord.SelectOption(label="...", value="...")],
            row=row,
        )
        self.refresh_options()

    def refresh_options(self) -> None:
        available_regions = self.panel.available_regions(self.selection_key)
        selected_regions = self.panel.selected_regions(self.selection_key)
        if not available_regions:
            self.disabled = True
            self.max_values = 1
            self.options = [
                discord.SelectOption(
                    label=_("No valid regions available"),
                    value="none",
                )
            ]
            return

        self.disabled = False
        self.max_values = min(self.max_allowed, len(available_regions))
        self.options = [
            discord.SelectOption(
                label=region,
                value=region,
                description=self.panel.region_option_description(region)[:100],
                default=region in selected_regions,
            )
            for region in available_regions
        ]

    async def callback(self, interaction: discord.Interaction) -> None:
        self.panel.set_selection(self.selection_key, self.values)
        self.panel.refresh_components()
        await self.panel.refresh_message(interaction)


class RegionGMPanelView(discord.ui.View):
    def __init__(self, game, defaults: dict[str, set[str]], *, timeout: int) -> None:
        super().__init__(timeout=timeout)
        self.game = game
        self.owner_id = game.gm_player.id
        self.message: discord.Message | None = None
        self.locked_in = False
        self.drop_regions = set(defaults.get("drops", set()))
        self.toxic_regions = set(defaults.get("toxic", set()))
        self.mutt_regions = set(defaults.get("mutts", set()))
        self.drop_select = RegionGMRegionSelect(
            self,
            selection_key="drops",
            placeholder=_("Pick current-round drop regions"),
            max_allowed=max(1, self.game._gm_drop_region_limit()),
            row=0,
        )
        self.toxic_select = RegionGMRegionSelect(
            self,
            selection_key="toxic",
            placeholder=_("Pick next-round toxic regions"),
            max_allowed=2,
            row=1,
        )
        self.mutt_select = RegionGMRegionSelect(
            self,
            selection_key="mutts",
            placeholder=_("Pick next-round mutt warning"),
            max_allowed=1,
            row=2,
        )
        self.add_item(self.drop_select)
        self.add_item(self.toxic_select)
        self.add_item(self.mutt_select)

    def available_regions(self, selection_key: str) -> list[str]:
        if selection_key == "drops":
            return self.game._gm_available_drop_regions()
        if selection_key == "toxic":
            return self.game._gm_available_toxic_regions()
        if selection_key == "mutts":
            return self.game._gm_available_mutt_regions()
        return []

    def selected_regions(self, selection_key: str) -> set[str]:
        if selection_key == "drops":
            return set(self.drop_regions)
        if selection_key == "toxic":
            return set(self.toxic_regions)
        if selection_key == "mutts":
            return set(self.mutt_regions)
        return set()

    def set_selection(self, selection_key: str, values: list[str]) -> None:
        chosen = {
            value
            for value in values
            if value in set(self.available_regions(selection_key))
        }
        if selection_key == "drops":
            self.drop_regions = chosen
        elif selection_key == "toxic":
            self.toxic_regions = set(list(chosen)[:2])
        elif selection_key == "mutts":
            self.mutt_regions = set(list(chosen)[:1])

    def region_option_description(self, region: str) -> str:
        occupants = len(self.game._players_in_region(region))
        parts = [_("Alive: {count}").format(count=occupants)]
        if region in self.game.active_toxic_regions:
            parts.append(_("Toxic now"))
        if region in self.game.active_mutt_regions:
            parts.append(_("Mutts now"))
        if region in self.game.region_drops:
            parts.append(_("Drop now"))
        return " | ".join(parts)

    def refresh_components(self) -> None:
        self.drop_select.refresh_options()
        self.toxic_select.refresh_options()
        self.mutt_select.refresh_options()

    def _region_field_value(self, region: str) -> str:
        occupants = self.game._players_in_region(region)
        if occupants:
            names = [player.display_name for player in occupants]
            visible_names = []
            for idx, name in enumerate(names):
                candidate = ", ".join([*visible_names, name])
                if len(candidate) > 850:
                    remaining = len(names) - idx
                    visible_names.append(_("+{count} more").format(count=remaining))
                    break
                visible_names.append(name)
            occupant_text = ", ".join(visible_names)
        else:
            occupant_text = _("None")
        status_bits = []
        if region in self.game.active_toxic_regions:
            status_bits.append("☣️ " + _("Toxic now"))
        if region in self.game.active_mutt_regions:
            status_bits.append("🐺 " + _("Mutts now"))
        if region in self.game.region_drops:
            status_bits.append("📦 " + _("Drop now"))

        if not status_bits:
            status_bits.append(_("Quiet"))
        return _(
            "Status: {status}\nTributes: {occupants}"
        ).format(
            status=" • ".join(status_bits),
            occupants=occupant_text,
        )

    def _selection_text(self, regions: set[str]) -> str:
        if not regions:
            return _("None")
        return ", ".join(f"**{region}**" for region in sorted(regions))

    def build_embed(self, note: str | None = None) -> discord.Embed:
        embed = discord.Embed(
            title=_("🎛️ Game Master Panel - Round {round}").format(
                round=self.game.round
            ),
            description=_(
                "Choose sponsor drops for this round, then lock toxic zones and mutt pressure for the next round."
            ),
            color=discord.Color.dark_purple(),
        )
        for region in self.game.REGIONS:
            embed.add_field(
                name=region,
                value=self._region_field_value(region),
                inline=False,
            )
        embed.add_field(
            name=_("Pending Directives"),
            value=_(
                "📦 Drops now: {drops}\n"
                "⚠️ Toxic next: {toxic}\n"
                "🐾 Mutts next: {mutts}"
            ).format(
                drops=self._selection_text(self.drop_regions),
                toxic=self._selection_text(self.toxic_regions),
                mutts=self._selection_text(self.mutt_regions),
            ),
            inline=False,
        )
        embed.set_footer(
            text=_(
                "Limits: up to {drops} drop regions, 2 toxic regions, 1 mutt warning. Empty slots auto-fill on lock or timeout."
            ).format(drops=self.game._gm_drop_region_limit())
        )
        if note:
            embed.add_field(name=_("Status"), value=note, inline=False)
        return embed

    async def refresh_message(
        self,
        interaction: discord.Interaction | None = None,
        *,
        note: str | None = None,
    ) -> None:
        self.refresh_components()
        embed = self.build_embed(note=note)
        if interaction is not None:
            await interaction.response.edit_message(embed=embed, view=self)
            self.message = interaction.message
            return
        if self.message is not None:
            await self.message.edit(embed=embed, view=self)

    def disable_all(self) -> None:
        for child in self.children:
            child.disabled = True

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message(
                _("This control panel is not yours."),
                ephemeral=True,
            )
            return False
        return True

    async def on_timeout(self) -> None:
        self.disable_all()
        if self.message is not None:
            try:
                await self.message.edit(
                    embed=self.build_embed(
                        note=_("Timed out. Arena defaults will be used.")
                    ),
                    view=self,
                )
            except (discord.NotFound, discord.HTTPException):
                pass

    @discord.ui.button(label="Randomize", style=ButtonStyle.primary, row=3)
    async def randomize_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        directives = self.game._random_gm_directives()
        self.drop_regions = set(directives["drops"])
        self.toxic_regions = set(directives["toxic"])
        self.mutt_regions = set(directives["mutts"])
        await self.refresh_message(
            interaction,
            note=_("Random arena directives generated."),
        )

    @discord.ui.button(label="Clear", style=ButtonStyle.secondary, row=3)
    async def clear_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        self.drop_regions.clear()
        self.toxic_regions.clear()
        self.mutt_regions.clear()
        await self.refresh_message(
            interaction,
            note=_("Selections cleared. Empty slots will auto-fill if left blank."),
        )

    @discord.ui.button(label="Lock Round", style=ButtonStyle.success, row=3)
    async def lock_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        self.locked_in = True
        self.disable_all()
        await interaction.response.edit_message(
            embed=self.build_embed(note=_("Directives locked for this round.")),
            view=self,
        )
        self.message = interaction.message
        self.stop()


class RegionGMShowdownFighterSelect(discord.ui.Select):
    def __init__(self, view, *, slot_key: str, placeholder: str, row: int) -> None:
        self.showdown_view = view
        self.slot_key = slot_key
        super().__init__(
            placeholder=placeholder,
            min_values=1,
            max_values=1,
            options=[discord.SelectOption(label="...", value="0")],
            row=row,
        )
        self.refresh_options()

    def refresh_options(self) -> None:
        contenders = self.showdown_view.contenders
        if not contenders:
            self.disabled = True
            self.options = [
                discord.SelectOption(
                    label=_("No valid contenders"),
                    value="0",
                )
            ]
            return

        selected_id = self.showdown_view.selected_id(self.slot_key)
        self.disabled = False
        self.options = []
        for contender in contenders:
            team_id = self.showdown_view.game.team_by_player_id.get(contender.id)
            description = _("District #{team}").format(team=team_id or "?")
            self.options.append(
                discord.SelectOption(
                    label=contender.display_name[:100],
                    value=str(contender.id),
                    description=description[:100],
                    default=contender.id == selected_id,
                )
            )

    async def callback(self, interaction: discord.Interaction) -> None:
        self.showdown_view.set_selected(self.slot_key, int(self.values[0]))
        self.showdown_view.refresh_components()
        await self.showdown_view.refresh_message(interaction)


class RegionGMShowdownView(discord.ui.View):
    def __init__(
        self,
        game,
        contenders: list[discord.Member],
        default_pair: tuple[discord.Member, discord.Member],
        *,
        timeout: int,
    ) -> None:
        super().__init__(timeout=timeout)
        self.game = game
        self.owner_id = game.gm_player.id
        self.message: discord.Message | None = None
        self.locked_in = False
        self.random_choice = False
        self.contenders = sorted(
            contenders,
            key=lambda member: member.display_name.casefold(),
        )
        self.first_id = default_pair[0].id
        self.second_id = default_pair[1].id
        self.first_select = RegionGMShowdownFighterSelect(
            self,
            slot_key="first",
            placeholder=_("Pick the first duelist"),
            row=0,
        )
        self.second_select = RegionGMShowdownFighterSelect(
            self,
            slot_key="second",
            placeholder=_("Pick the second duelist"),
            row=1,
        )
        self.add_item(self.first_select)
        self.add_item(self.second_select)

    def selected_id(self, slot_key: str) -> int | None:
        return self.first_id if slot_key == "first" else self.second_id

    def set_selected(self, slot_key: str, player_id: int) -> None:
        if slot_key == "first":
            self.first_id = player_id
        else:
            self.second_id = player_id

    def refresh_components(self) -> None:
        self.first_select.refresh_options()
        self.second_select.refresh_options()

    def _selected_name(self, player_id: int | None) -> str:
        if player_id is None:
            return _("None")
        player = self.game.member_by_id.get(player_id)
        if player is None:
            return _("None")
        return f"**{player.display_name}**"

    def build_embed(self, note: str | None = None) -> discord.Embed:
        contenders_text = ", ".join(
            f"**{member.display_name}**"
            f" ({_('District #{team}').format(team=self.game.team_by_player_id.get(member.id) or '?')})"
            for member in self.contenders
        )
        embed = discord.Embed(
            title=_("⚔️ Sudden Death Duel Picker"),
            description=_(
                "Multiple tributes survived into forced showdown. Choose who gets dragged into the duel."
            ),
            color=discord.Color.dark_red(),
        )
        embed.add_field(
            name=_("Eligible Contenders"),
            value=contenders_text[:1024],
            inline=False,
        )
        embed.add_field(
            name=_("Pending Duel"),
            value=_(
                "{first} vs {second}"
            ).format(
                first=self._selected_name(self.first_id),
                second=self._selected_name(self.second_id),
            ),
            inline=False,
        )
        embed.set_footer(
            text=_(
                "Pick two tributes from different districts. If the pair is incomplete or invalid, the arena auto-fills a legal duel."
            )
        )
        if note:
            embed.add_field(name=_("Status"), value=note, inline=False)
        return embed

    async def refresh_message(
        self,
        interaction: discord.Interaction | None = None,
        *,
        note: str | None = None,
    ) -> None:
        self.refresh_components()
        embed = self.build_embed(note=note)
        if interaction is not None:
            await interaction.response.edit_message(embed=embed, view=self)
            self.message = interaction.message
            return
        if self.message is not None:
            await self.message.edit(embed=embed, view=self)

    def disable_all(self) -> None:
        for child in self.children:
            child.disabled = True

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message(
                _("This control panel is not yours."),
                ephemeral=True,
            )
            return False
        return True

    async def on_timeout(self) -> None:
        self.disable_all()
        if self.message is not None:
            try:
                await self.message.edit(
                    embed=self.build_embed(
                        note=_("Timed out. The arena will auto-pick the duel.")
                    ),
                    view=self,
                )
            except (discord.NotFound, discord.HTTPException):
                pass

    @discord.ui.button(label="Random Duel", style=ButtonStyle.secondary, row=2)
    async def random_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        self.random_choice = True
        self.first_id = None
        self.second_id = None
        self.locked_in = True
        self.disable_all()
        await interaction.response.edit_message(
            embed=self.build_embed(note=_("The arena will auto-pick the duelists.")),
            view=self,
        )
        self.message = interaction.message
        self.stop()

    @discord.ui.button(label="Lock Duel", style=ButtonStyle.danger, row=2)
    async def lock_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        self.random_choice = False
        self.locked_in = True
        self.disable_all()
        await interaction.response.edit_message(
            embed=self.build_embed(note=_("Duelists locked.")),
            view=self,
        )
        self.message = interaction.message
        self.stop()


class RegionGMGame(RegionGame):
    GM_CONTROL_TIMEOUT_SECONDS = 35
    GM_SHOWDOWN_TIMEOUT_SECONDS = 20

    def __init__(self, ctx, players: list, *, gm_player: discord.Member) -> None:
        super().__init__(ctx, players)
        self.gm_player = gm_player
        self.gm_panel_message: discord.Message | None = None
        self.gm_showdown_message: discord.Message | None = None
        self.gm_panel_public = False

    def _gm_drop_region_limit(self) -> int:
        return 2 if len(self.players) >= 6 else 1

    def _gm_available_drop_regions(self) -> list[str]:
        return [
            region for region in self.REGIONS if region not in self.active_toxic_regions
        ]

    def _gm_available_toxic_regions(self) -> list[str]:
        return [
            region for region in self.REGIONS if region not in self.active_toxic_regions
        ]

    def _gm_available_mutt_regions(self) -> list[str]:
        return [
            region
            for region in self.REGIONS
            if region not in self.active_toxic_regions
            and len(self._players_in_region(region)) > 0
        ]

    def _random_gm_directives(self) -> dict[str, set[str]]:
        drops: set[str] = set()
        toxic: set[str] = set()
        mutts: set[str] = set()

        available_drop_regions = self._gm_available_drop_regions()
        drop_count = min(self._gm_drop_region_limit(), len(available_drop_regions))
        if drop_count > 0:
            drops = set(random.sample(available_drop_regions, drop_count))

        available_toxic_regions = self._gm_available_toxic_regions()
        toxic_count = 1
        if self.round >= 3 and len(self.players) >= 6:
            toxic_count = 2
        toxic_count = min(2, toxic_count, len(available_toxic_regions))
        if toxic_count > 0:
            toxic = set(random.sample(available_toxic_regions, toxic_count))

        crowded_regions = [
            region
            for region in self._gm_available_mutt_regions()
            if len(self._players_in_region(region)) >= 2
        ]
        mutt_pool = crowded_regions or self._gm_available_mutt_regions()
        if mutt_pool:
            mutts = {random.choice(mutt_pool)}

        return {"drops": drops, "toxic": toxic, "mutts": mutts}

    def _complete_gm_directive_slot(
        self,
        *,
        selected: set[str],
        fallback: set[str],
        available: list[str],
        target_count: int,
    ) -> set[str]:
        if target_count <= 0 or not available:
            return set()

        chosen: list[str] = []
        for region in sorted(selected):
            if region in available and region not in chosen:
                chosen.append(region)

        for region in sorted(fallback):
            if len(chosen) >= target_count:
                break
            if region in available and region not in chosen:
                chosen.append(region)

        if len(chosen) < target_count:
            remaining = [region for region in available if region not in chosen]
            if remaining:
                chosen.extend(
                    random.sample(
                        remaining,
                        min(target_count - len(chosen), len(remaining)),
                    )
                )

        return set(chosen)

    def _finalize_gm_directives(
        self,
        selected: dict[str, set[str]],
        defaults: dict[str, set[str]],
    ) -> tuple[dict[str, set[str]], bool]:
        finalized = {
            "drops": self._complete_gm_directive_slot(
                selected=set(selected.get("drops", set())),
                fallback=set(defaults.get("drops", set())),
                available=self._gm_available_drop_regions(),
                target_count=min(
                    len(self._gm_available_drop_regions()),
                    max(1, len(defaults.get("drops", set()))),
                ),
            ),
            "toxic": self._complete_gm_directive_slot(
                selected=set(selected.get("toxic", set())),
                fallback=set(defaults.get("toxic", set())),
                available=self._gm_available_toxic_regions(),
                target_count=min(
                    len(self._gm_available_toxic_regions()),
                    len(defaults.get("toxic", set())),
                ),
            ),
            "mutts": self._complete_gm_directive_slot(
                selected=set(selected.get("mutts", set())),
                fallback=set(defaults.get("mutts", set())),
                available=self._gm_available_mutt_regions(),
                target_count=min(
                    len(self._gm_available_mutt_regions()),
                    len(defaults.get("mutts", set())),
                ),
            ),
        }
        auto_filled = any(
            finalized[key] != set(selected.get(key, set())) for key in finalized
        )
        return finalized, auto_filled

    def _apply_gm_drop_regions(self, drop_regions: set[str]) -> None:
        self.region_drops.clear()
        early_round = self.round <= 3
        for region in sorted(drop_regions):
            self.region_drops[region] = (
                random.randint(1, 2) if early_round else random.randint(2, 3)
            )

    def _directive_text(self, regions) -> str:
        region_list = sorted(regions)
        if not region_list:
            return _("None")
        return ", ".join(f"**{region}**" for region in region_list)

    def _gm_pathways_embed(self) -> discord.Embed:
        embed = discord.Embed(
            title=_("🗺️ Arena Pathways Reference"),
            description=_(
                "Movement is limited to connected regions. Use this to funnel tributes into drops, mutts, and toxic pressure."
            ),
            color=discord.Color.dark_gold(),
        )
        for region in self.REGIONS:
            neighbors = ", ".join(self.REGION_ADJACENCY.get(region, ())) or _("None")
            embed.add_field(name=region, value=neighbors[:1024], inline=False)
        embed.set_footer(
            text=_(
                "GM note: you do not place tribute traps directly. Pathway control lets you bait or corner them."
            )
        )
        return embed

    async def _send_gm_intro(self) -> None:
        lines = [
            _("You have been chosen as this Hunger Games' Game Master."),
            _(
                "Each round, pick sponsor drops for the current round and choose toxic zones plus mutt pressure for the next round."
            ),
            _("During Sudden Death with multiple valid tributes, you also choose who gets forced into the duel."),
            _("If you leave anything blank or go AFK, the arena auto-fills the missing directives."),
            _("Back to game: {link}").format(link=self.game_channel_link),
        ]
        intro_text = "\n".join(lines)
        pathways_embed = self._gm_pathways_embed()
        try:
            await self.gm_player.send(intro_text)
            await self.gm_player.send(embed=pathways_embed)
        except (discord.Forbidden, discord.HTTPException):
            await self.ctx.send(
                _(
                    "{gm}, GM reference is public because your DMs are closed."
                ).format(gm=self.gm_player.mention)
            )
            await self.ctx.send(embed=pathways_embed)

    async def _present_gm_panel(self, view: RegionGMPanelView) -> None:
        content = None
        if self.gm_panel_public:
            content = _(
                "{gm}, your Game Master panel is here because DMs are unavailable."
            ).format(gm=self.gm_player.mention)

        if self.gm_panel_message is not None:
            try:
                await self.gm_panel_message.edit(
                    content=content,
                    embed=view.build_embed(),
                    view=view,
                )
                view.message = self.gm_panel_message
                return
            except (discord.NotFound, discord.HTTPException):
                self.gm_panel_message = None

        try:
            dm_channel = self.gm_player.dm_channel or await self.gm_player.create_dm()
            self.gm_panel_message = await dm_channel.send(embed=view.build_embed(), view=view)
            self.gm_panel_public = False
            view.message = self.gm_panel_message
        except (discord.Forbidden, discord.HTTPException):
            self.gm_panel_message = await self.ctx.send(
                _(
                    "{gm}, your Game Master panel is public because your DMs are closed."
                ).format(gm=self.gm_player.mention),
                embed=view.build_embed(),
                view=view,
            )
            self.gm_panel_public = True
            view.message = self.gm_panel_message

    async def _present_gm_showdown_view(self, view: RegionGMShowdownView) -> None:
        content = None
        if self.gm_panel_public:
            content = _(
                "{gm}, your Sudden Death picker is here because DMs are unavailable."
            ).format(gm=self.gm_player.mention)

        if self.gm_showdown_message is not None:
            try:
                await self.gm_showdown_message.edit(
                    content=content,
                    embed=view.build_embed(),
                    view=view,
                )
                view.message = self.gm_showdown_message
                return
            except (discord.NotFound, discord.HTTPException):
                self.gm_showdown_message = None

        try:
            dm_channel = self.gm_player.dm_channel or await self.gm_player.create_dm()
            self.gm_showdown_message = await dm_channel.send(
                embed=view.build_embed(),
                view=view,
            )
            self.gm_panel_public = False
            view.message = self.gm_showdown_message
        except (discord.Forbidden, discord.HTTPException):
            self.gm_showdown_message = await self.ctx.send(
                _(
                    "{gm}, your Sudden Death picker is public because your DMs are closed."
                ).format(gm=self.gm_player.mention),
                embed=view.build_embed(),
                view=view,
            )
            self.gm_panel_public = True
            view.message = self.gm_showdown_message

    def _showdown_pairs(
        self,
        killed_this_round: set,
    ) -> list[tuple[str, discord.Member, discord.Member]]:
        pairs: list[tuple[str, discord.Member, discord.Member]] = []
        for region in self.REGIONS:
            contenders = self._players_in_region(region, killed_this_round=killed_this_round)
            if len(contenders) < 2:
                continue
            for idx, left in enumerate(contenders):
                left_team = self.team_by_player_id.get(left.id)
                for right in contenders[idx + 1 :]:
                    right_team = self.team_by_player_id.get(right.id)
                    if left_team == right_team:
                        continue
                    pairs.append((region, left, right))
        return pairs

    def _complete_showdown_pair(
        self,
        *,
        pairs: list[tuple[str, discord.Member, discord.Member]],
        default_pair: tuple[str, discord.Member, discord.Member],
        first_id: int | None,
        second_id: int | None,
    ) -> tuple[tuple[str, discord.Member, discord.Member], bool]:
        pair_lookup = {
            tuple(sorted((left.id, right.id))): (region, left, right)
            for region, left, right in pairs
        }

        if first_id is not None and second_id is not None:
            exact = pair_lookup.get(tuple(sorted((first_id, second_id))))
            if exact is not None:
                return exact, False

        if first_id is not None:
            anchored = [
                pair
                for pair in pairs
                if pair[1].id == first_id or pair[2].id == first_id
            ]
            if anchored:
                if any(
                    tuple(sorted((pair[1].id, pair[2].id)))
                    == tuple(sorted((default_pair[1].id, default_pair[2].id)))
                    for pair in anchored
                ):
                    return default_pair, True
                return random.choice(anchored), True

        if second_id is not None:
            anchored = [
                pair
                for pair in pairs
                if pair[1].id == second_id or pair[2].id == second_id
            ]
            if anchored:
                if any(
                    tuple(sorted((pair[1].id, pair[2].id)))
                    == tuple(sorted((default_pair[1].id, default_pair[2].id)))
                    for pair in anchored
                ):
                    return default_pair, True
                return random.choice(anchored), True

        return default_pair, True

    def _resolve_showdown_pair(
        self,
        region: str,
        left: discord.Member,
        right: discord.Member,
        killed_this_round: set,
        round_lines: list[str],
        elimination_log: dict[int, dict],
    ) -> None:
        left_roll = self.gear_score[left.id] + random.randint(1, 4)
        right_roll = self.gear_score[right.id] + random.randint(1, 4)
        winner, loser = (left, right) if left_roll >= right_roll else (right, left)
        self._mark_kill(
            winner,
            loser,
            killed_this_round,
            elimination_log=elimination_log,
            cause=_("lost a forced showdown in **{region}** to **{killer}**").format(
                region=region,
                killer=winner.display_name,
            ),
        )
        round_lines.append(
            _(
                "💥 The silence breaks in **{region}**. **{winner}** wins a forced"
                " showdown against **{loser}**."
            ).format(
                region=region,
                winner=winner.display_name,
                loser=loser.display_name,
            )
        )

    async def _run_gm_showdown_phase(
        self,
        killed_this_round: set,
        round_lines: list[str],
        elimination_log: dict[int, dict],
    ) -> None:
        pairs = self._showdown_pairs(killed_this_round)
        if not pairs:
            return

        default_pair = random.choice(pairs)
        contenders_by_id: dict[int, discord.Member] = {}
        for _, left, right in pairs:
            contenders_by_id[left.id] = left
            contenders_by_id[right.id] = right
        contenders = list(contenders_by_id.values())

        if len(contenders) <= 2 or len(contenders) > 25:
            if len(contenders) > 2:
                round_lines.append(
                    _(
                        "🎛️ Too many tributes remain for manual duel selection. The arena chooses the Sudden Death pairing."
                    )
                )
            self._resolve_showdown_pair(
                default_pair[0],
                default_pair[1],
                default_pair[2],
                killed_this_round,
                round_lines,
                elimination_log,
            )
            return

        view = RegionGMShowdownView(
            self,
            contenders,
            (default_pair[1], default_pair[2]),
            timeout=self.GM_SHOWDOWN_TIMEOUT_SECONDS,
        )
        await self._present_gm_showdown_view(view)
        await self.ctx.send(
            _("⚔️ Sudden Death triggers. The Game Master is choosing the duelists."),
            delete_after=self.GM_SHOWDOWN_TIMEOUT_SECONDS,
        )
        await view.wait()

        chosen_pair, auto_filled = self._complete_showdown_pair(
            pairs=pairs,
            default_pair=default_pair,
            first_id=view.first_id,
            second_id=view.second_id,
        )

        status_note = _("The arena auto-picked the Sudden Death duel.")
        if view.locked_in:
            status_note = _("The Game Master locks in the Sudden Death duel.")
            if view.random_choice:
                status_note = _("The Game Master lets the arena pick the Sudden Death duel.")
            elif auto_filled:
                status_note = _(
                    "The Game Master marked the duel. Missing or invalid slots were auto-filled."
                )

        if view.message is not None:
            try:
                await view.message.edit(
                    content=view.message.content,
                    embed=view.build_embed(note=status_note),
                    view=view,
                )
            except (discord.NotFound, discord.HTTPException):
                pass

        region, left, right = chosen_pair
        if view.locked_in and view.random_choice:
            round_lines.append(
                _(
                    "🎛️ The Game Master unleashes the arena on Sudden Death. **{left}** and **{right}** are chosen."
                ).format(
                    left=left.display_name,
                    right=right.display_name,
                )
            )
        elif view.locked_in and not auto_filled:
            round_lines.append(
                _(
                    "🎛️ The Game Master drags **{left}** and **{right}** into Sudden Death."
                ).format(
                    left=left.display_name,
                    right=right.display_name,
                )
            )
        elif view.locked_in:
            round_lines.append(
                _(
                    "🎛️ The Game Master marks **{left}** and **{right}** for Sudden Death, and the arena fills the rest."
                ).format(
                    left=left.display_name,
                    right=right.display_name,
                )
            )
        else:
            round_lines.append(
                _(
                    "🎛️ The Game Master hesitates. The arena drags **{left}** and **{right}** into Sudden Death."
                ).format(
                    left=left.display_name,
                    right=right.display_name,
                )
            )

        self._resolve_showdown_pair(
            region,
            left,
            right,
            killed_this_round,
            round_lines,
            elimination_log,
        )

    async def _resolve_stalemate_with_gm(
        self,
        killed_this_round: set,
        round_lines: list[str],
        elimination_log: dict[int, dict],
    ) -> None:
        if self.no_kill_rounds < self.STALEMATE_ROUNDS:
            return
        survivors = [p for p in self.players if p not in killed_this_round]
        if len(survivors) <= 1:
            return

        round_lines.append(
            _(
                "🕛 {rounds} bloodless rounds. The Gamemakers trigger Sudden Death."
            ).format(rounds=self.no_kill_rounds)
        )
        for survivor in survivors:
            self.player_region[survivor.id] = "Cornucopia"
        round_lines.append(
            _(
                "🚨 Sirens blare. Remaining tributes are forced into **Cornucopia**."
            )
        )
        await self._run_gm_showdown_phase(
            killed_this_round,
            round_lines,
            elimination_log,
        )

    async def _run_gm_control_phase(self) -> None:
        defaults = self._random_gm_directives()
        view = RegionGMPanelView(
            self,
            defaults,
            timeout=self.GM_CONTROL_TIMEOUT_SECONDS,
        )
        await self._present_gm_panel(view)
        await self.ctx.send(
            _("🎛️ The Game Master is shaping the arena for round {round}.").format(
                round=self.round
            ),
            delete_after=self.GM_CONTROL_TIMEOUT_SECONDS,
        )
        await view.wait()

        selected = {
            "drops": set(view.drop_regions),
            "toxic": set(view.toxic_regions),
            "mutts": set(view.mutt_regions),
        }
        directives, auto_filled = self._finalize_gm_directives(selected, defaults)
        has_manual_changes = any(
            selected[key] != defaults.get(key, set()) for key in selected
        )
        has_saved_manual_choices = has_manual_changes and any(
            selected[key] for key in selected
        )
        status_note = _("Arena defaults engaged after the Game Master timed out.")
        if view.locked_in:
            status_note = _("The Game Master locks in the arena.")
            if auto_filled:
                status_note = _(
                    "The Game Master locks in the arena. Empty slots were auto-filled."
                )
        elif has_saved_manual_choices:
            status_note = _(
                "The Game Master went AFK. Their saved picks were kept and the rest auto-filled."
            )

        self._apply_gm_drop_regions(directives["drops"])
        self.next_toxic_regions = set(directives["toxic"])
        self.next_mutt_regions = set(directives["mutts"])

        if view.message is not None:
            try:
                await view.message.edit(
                    content=view.message.content,
                    embed=view.build_embed(note=status_note),
                    view=view,
                )
            except (discord.NotFound, discord.HTTPException):
                pass

        summary = discord.Embed(
            title=_("Gamemaker Briefing"),
            description=_(
                "📦 Drops this round: {drops}\n"
                "⚠️ Toxic next round: {toxic}\n"
                "🐾 Mutt warning next round: {mutts}"
            ).format(
                drops=self._directive_text(self.region_drops.keys()),
                toxic=self._directive_text(self.next_toxic_regions),
                mutts=self._directive_text(self.next_mutt_regions),
            ),
            color=discord.Color.orange(),
        )
        summary.set_footer(text=status_note)
        await self.ctx.send(embed=summary)

    async def send_cast(self):
        await self.ctx.send(
            embed=discord.Embed(
                title=_("🎛️ Game Master Selected"),
                description=_(
                    "{gm} has been chosen at random as the Game Master and will direct the arena instead of fighting."
                ).format(gm=self.gm_player.mention),
                color=discord.Color.dark_orange(),
            )
        )
        await super().send_cast()
        await self.ctx.send(
            embed=discord.Embed(
                title=_("Regions-GM Rules"),
                description=_(
                    "Before each round, the Game Master chooses this round's sponsor drops plus next round's toxic zones and mutt warning. In Sudden Death, the Game Master can also choose the forced duelists. Blank or AFK slots auto-fill."
                ),
                color=discord.Color.gold(),
            )
        )
        await self._send_gm_intro()

    async def _resolve_arena_event(
        self,
        killed_this_round: set,
        round_lines: list[str],
        elimination_log: dict[int, dict],
    ) -> None:
        if not self.active_mutt_regions:
            return

        active_candidates = [
            region
            for region in sorted(self.active_mutt_regions)
            if len(
                self._players_in_region(region, killed_this_round=killed_this_round)
            )
            >= 2
        ]
        if not active_candidates:
            faded_regions = sorted(self.active_mutt_regions)
            self.active_mutt_regions.clear()
            round_lines.append(
                _(
                    "🐾 Mutt pressure fades in {regions}. No crowded targets remain."
                ).format(
                    regions=nice_join([f"**{region}**" for region in faded_regions])
                )
            )
            return

        region = random.choice(active_candidates)
        candidates = self._players_in_region(region, killed_this_round=killed_this_round)
        victim = random.choice(candidates)
        lethality = self._mutt_lethality_chance(
            victim, base_chance=76, min_chance=24
        )
        self.active_mutt_regions.clear()
        if random.randint(1, 100) <= lethality:
            self._mark_kill(
                None,
                victim,
                killed_this_round,
                elimination_log=elimination_log,
                cause=_("was torn apart by mutts in **{region}**").format(
                    region=region
                ),
            )
            round_lines.append(
                _("🐺 Mutts ambush **{victim}** in **{region}**.").format(
                    victim=victim.display_name,
                    region=region,
                )
            )
            return

        loss = self._apply_mutt_gear_loss(victim)
        round_lines.append(
            _(
                "🐺 Mutts ambush **{victim}** in **{region}**, but they escape and lose {loss} gear level(s)."
            ).format(
                victim=victim.display_name,
                region=region,
                loss=loss,
            )
        )

    async def get_inputs(self):
        status = await self.ctx.send(
            _("🔥 **Round {round}** begins...").format(round=self.round),
            delete_after=45,
        )
        self.hidden_ids = set()
        killed_this_round: set[discord.Member] = set()
        round_lines: list[str] = []
        elimination_log: dict[int, dict] = {}

        self.active_toxic_regions = set(self.next_toxic_regions)
        self.active_mutt_regions = set(self.next_mutt_regions)
        self.fog_stage = max(1, min(6, 1 + (self.round - 1) // 2))
        self.region_drops.clear()
        await self._run_gm_control_phase()
        await self._send_region_brief()

        actors = [actor for actor in self.players if actor not in killed_this_round]
        choices_by_actor_id: dict[int, list[dict]] = {}
        for actor in actors:
            choices = self._build_action_choices(actor, killed_this_round)
            if choices:
                choices_by_actor_id[actor.id] = choices

        async def choose_for_actor(
            actor: discord.Member, choices: list[dict]
        ) -> tuple[discord.Member, dict | None]:
            if not choices:
                return actor, None
            action = await self._choose_action(actor, choices)
            return actor, action

        selected_actions_by_actor_id: dict[int, dict] = {}
        choose_tasks = [
            choose_for_actor(actor, choices_by_actor_id.get(actor.id, []))
            for actor in actors
            if actor.id in choices_by_actor_id
        ]
        if choose_tasks:
            await self.ctx.send(
                _("📩 Action prompts sent to all tributes. Choices lock together.")
            )
            for actor, action in await asyncio.gather(*choose_tasks):
                if action is not None:
                    selected_actions_by_actor_id[actor.id] = action
            await self.ctx.send(_("⏳ Action phase closed. Resolving round..."))

        turn_order = random.shuffle(actors.copy())
        for actor in turn_order:
            if actor not in self.players or actor in killed_this_round:
                continue
            action = selected_actions_by_actor_id.get(actor.id)
            if action is None:
                fallback_choices = choices_by_actor_id.get(actor.id, [])
                if not fallback_choices:
                    continue
                action = random.choice(fallback_choices)
            summary = self._resolve_action(actor, action, killed_this_round, elimination_log)
            round_lines.append(f"**{actor.display_name}** {summary}")

        await self._resolve_arena_event(killed_this_round, round_lines, elimination_log)
        self._apply_toxic_fog(killed_this_round, round_lines, elimination_log)

        if killed_this_round:
            self.no_kill_rounds = 0
        else:
            self.no_kill_rounds += 1
            self._resolve_stalemate(killed_this_round, round_lines, elimination_log)
            if killed_this_round:
                self.no_kill_rounds = 0

        for dead in list(killed_this_round):
            try:
                self.players.remove(dead)
            except ValueError:
                pass

        try:
            await status.delete()
        except discord.NotFound:
            pass
        await self._send_round_report(round_lines, killed_this_round, elimination_log)
        self.round += 1


class RegionIdeasGame(RegionGame):
    HAZARD_LABELS: dict[str, str] = {
        "wildfire": "Wildfire",
        "mutt_migration": "Mutt Migration",
        "tracker_jackers": "Tracker-Jacker Swarm",
    }
    NOISE_REVEAL_THRESHOLD = 2
    COMBAT_KINDS = {"hunt", "rush", "betray", "ambush"}

    def __init__(self, ctx, players: list):
        super().__init__(ctx, players)
        self.noise_by_player_id: dict[int, int] = {p.id: 0 for p in self.players}
        self.revealed_noisy_ids: set[int] = set()
        self.slow_next_round_ids: set[int] = set()
        self.round_slow_ids: set[int] = set()
        self.tunnel_hidden_ids: set[int] = set()
        self.combat_bonus_by_player_id: dict[int, int] = {p.id: 0 for p in self.players}
        self.fog_resistance_rounds: dict[int, int] = {p.id: 0 for p in self.players}
        self.active_contracts: dict[int, dict] = {}
        self.round_action_kind_by_player_id: dict[int, str] = {}
        self.round_kill_events: list[dict] = []
        self.active_region_hazards: dict[str, str] = {}
        self.next_region_hazards: dict[str, str] = {}
        self.region_control_owner: dict[str, int | None] = {
            region: None for region in self.REGIONS
        }
        self.region_control_streak: dict[str, int] = {
            region: 0 for region in self.REGIONS
        }
        self.collapse_announced = False

    def _is_collapse_mode(self) -> bool:
        return len(self.players) <= 4

    def _adjust_noise(self, player_id: int, delta: int) -> None:
        current = self.noise_by_player_id.get(player_id, 0)
        self.noise_by_player_id[player_id] = max(0, min(8, current + delta))

    def _hazard_display(self, hazard_key: str | None) -> str:
        if not hazard_key:
            return _("Unknown hazard")
        return _(self.HAZARD_LABELS.get(hazard_key, hazard_key))

    def _mark_kill(
        self,
        killer: discord.Member | None,
        victim: discord.Member,
        killed_this_round: set,
        *,
        elimination_log: dict[int, dict] | None = None,
        cause: str | None = None,
    ) -> bool:
        killed = super()._mark_kill(
            killer,
            victim,
            killed_this_round,
            elimination_log=elimination_log,
            cause=cause,
        )
        if not killed:
            return False
        self.round_kill_events.append(
            {
                "killer_id": killer.id if isinstance(killer, discord.Member) else None,
                "victim_id": victim.id,
                "region": self.player_region.get(victim.id),
            }
        )
        if isinstance(killer, discord.Member):
            self._adjust_noise(killer.id, 1)
        return True

    def _spawn_region_drops(self) -> None:
        if self._is_collapse_mode():
            self.region_drops.clear()
            self.region_drops["Cornucopia"] = random.randint(3, 4)
            return
        super()._spawn_region_drops()

    def _pick_next_toxic_regions(self) -> set[str]:
        if self._is_collapse_mode():
            return {region for region in self.REGIONS if region != "Cornucopia"}
        return super()._pick_next_toxic_regions()

    def _pick_next_region_hazards(self) -> dict[str, str]:
        if self._is_collapse_mode():
            return {"Cornucopia": random.choice(list(self.HAZARD_LABELS.keys()))}

        candidates = [
            region for region in self.REGIONS if region not in self.next_toxic_regions
        ]
        if not candidates:
            candidates = list(self.REGIONS)
        hazard_count = 2 if len(self.players) >= 8 else 1
        picked = random.sample(candidates, k=min(hazard_count, len(candidates)))
        return {
            region: random.choice(list(self.HAZARD_LABELS.keys()))
            for region in picked
        }

    def _contract_prompt_line(self, contract: dict | None) -> str:
        if not contract:
            return _("No sponsor contract this round.")
        contract_type = contract.get("type")
        region = str(contract.get("region", _("Unknown Region")))
        reward = str(contract.get("reward", "gear"))
        reward_text = {
            "gear": _("Gear Package (+2 gear)"),
            "fog_resist": _("Fog Shield (2 rounds)"),
            "trap_kit": _("Trap Kit (+1 trap)"),
        }.get(reward, _("Unknown reward"))

        if contract_type == "hold":
            objective = _("Hold {region} until round end.").format(region=region)
        else:
            objective = _("Eliminate someone in {region}.").format(region=region)
        return _("{objective} Reward: {reward}").format(
            objective=objective, reward=reward_text
        )

    def _assign_sponsor_contracts(self) -> None:
        self.active_contracts.clear()
        rewards = ("gear", "fog_resist", "trap_kit")
        for player in self.players:
            contract_type = random.choice(("hold", "eliminate"))
            if contract_type == "eliminate":
                live_regions = [
                    region
                    for region in self.REGIONS
                    if self._players_in_region(region)
                ]
                target_region = random.choice(live_regions or list(self.REGIONS))
            else:
                target_region = random.choice(list(self.REGIONS))
            self.active_contracts[player.id] = {
                "type": contract_type,
                "region": target_region,
                "reward": random.choice(rewards),
            }

    def _apply_contract_reward(self, player: discord.Member, reward: str) -> str:
        if reward == "gear":
            self.gear_score[player.id] = min(10, self.gear_score[player.id] + 2)
            return _("gear upgraded")
        if reward == "fog_resist":
            self.fog_resistance_rounds[player.id] = min(
                4, self.fog_resistance_rounds.get(player.id, 0) + 2
            )
            return _("fog shield online")
        self.traps[player.id] = min(4, self.traps[player.id] + 1)
        return _("received a trap kit")

    def _resolve_contracts(
        self,
        killed_this_round: set,
        round_lines: list[str],
    ) -> None:
        for player in self.players:
            if player in killed_this_round:
                continue
            contract = self.active_contracts.get(player.id)
            if not contract:
                continue

            contract_type = contract.get("type")
            target_region = str(contract.get("region", ""))
            success = False
            if contract_type == "hold":
                success = self._region_for(player) == target_region
            elif contract_type == "eliminate":
                success = any(
                    event.get("killer_id") == player.id
                    and event.get("region") == target_region
                    for event in self.round_kill_events
                )

            if not success:
                continue
            reward_text = self._apply_contract_reward(
                player, str(contract.get("reward", "gear"))
            )
            round_lines.append(
                _(
                    "🎯 Sponsor contract complete: **{player}** fulfilled a mission in"
                    " **{region}** and {reward}."
                ).format(
                    player=player.display_name,
                    region=target_region,
                    reward=reward_text,
                )
            )

        self.active_contracts.clear()

    def _update_noise_visibility(self) -> None:
        alive_ids = {player.id for player in self.players}
        for player_id in list(self.noise_by_player_id):
            if player_id not in alive_ids:
                self.noise_by_player_id[player_id] = 0
                continue
            self.noise_by_player_id[player_id] = max(
                0, self.noise_by_player_id[player_id] - 1
            )
        self.revealed_noisy_ids = {
            player_id
            for player_id in alive_ids
            if self.noise_by_player_id.get(player_id, 0) >= self.NOISE_REVEAL_THRESHOLD
        }

    def _update_tunnel_slow_state(self) -> None:
        self.slow_next_round_ids = {
            player.id
            for player in self.players
            if self._region_for(player) == "Underground Tunnels"
        }

    def _decrement_fog_shields(self) -> None:
        for player in self.players:
            current = self.fog_resistance_rounds.get(player.id, 0)
            if current > 0:
                self.fog_resistance_rounds[player.id] = current - 1

    def _update_region_control_points(self, round_lines: list[str]) -> None:
        for region in self.REGIONS:
            occupants = self._players_in_region(region)
            district_ids = {
                self.team_by_player_id.get(player.id)
                for player in occupants
                if self.team_by_player_id.get(player.id) is not None
            }
            if len(district_ids) != 1 or not occupants:
                self.region_control_owner[region] = None
                self.region_control_streak[region] = 0
                continue

            district = next(iter(district_ids))
            if self.region_control_owner.get(region) == district:
                self.region_control_streak[region] += 1
            else:
                self.region_control_owner[region] = district
                self.region_control_streak[region] = 1

            streak = self.region_control_streak[region]
            if streak >= 2 and streak % 2 == 0:
                for player in occupants:
                    self.gear_score[player.id] = min(10, self.gear_score[player.id] + 1)
                round_lines.append(
                    _(
                        "🏴 District #{district} controls **{region}** for {streak}"
                        " rounds and gains a control bonus."
                    ).format(
                        district=district,
                        region=region,
                        streak=streak,
                    )
                )

    def _apply_riverbank_recovery(
        self,
        killed_this_round: set,
        round_lines: list[str],
    ) -> None:
        for player in self.players:
            if player in killed_this_round:
                continue
            if self._region_for(player) != "Riverbank":
                continue
            action_kind = self.round_action_kind_by_player_id.get(player.id)
            if action_kind in self.COMBAT_KINDS:
                continue
            before = self.gear_score[player.id]
            self.gear_score[player.id] = min(10, before + 1)
            if self.gear_score[player.id] > before:
                round_lines.append(
                    _(
                        "🌊 **{player}** regroups at **Riverbank** and recovers gear."
                    ).format(player=player.display_name)
                )

    def _apply_cornucopia_conflict(
        self,
        killed_this_round: set,
        round_lines: list[str],
        elimination_log: dict[int, dict],
    ) -> None:
        contenders = self._players_in_region(
            "Cornucopia", killed_this_round=killed_this_round
        )
        if len(contenders) < 2:
            return
        chance = min(75, 20 + len(contenders) * 12)
        if random.randint(1, 100) > chance:
            return

        left, right = random.sample(contenders, 2)
        left_roll = (
            self.gear_score[left.id]
            + self.combat_bonus_by_player_id.get(left.id, 0) // 4
            + random.randint(1, 4)
        )
        right_roll = (
            self.gear_score[right.id]
            + self.combat_bonus_by_player_id.get(right.id, 0) // 4
            + random.randint(1, 4)
        )
        winner, loser = (left, right) if left_roll >= right_roll else (right, left)
        self._mark_kill(
            winner,
            loser,
            killed_this_round,
            elimination_log=elimination_log,
            cause=_("fell in a Cornucopia clash against **{killer}**").format(
                killer=winner.display_name
            ),
        )
        round_lines.append(
            _(
                "⚔️ Cornucopia erupts. **{winner}** overwhelms **{loser}** in the chaos."
            ).format(
                winner=winner.display_name,
                loser=loser.display_name,
            )
        )

    async def _send_region_brief(self) -> None:
        lines = []
        for region in self.REGIONS:
            alive_count = len(self._players_in_region(region))
            status_bits = [f"👥 {alive_count}"]
            if region in self.region_drops:
                status_bits.append("📦 Drop")
            if region in self.active_toxic_regions:
                status_bits.append("☣️ Toxic Now")
            elif region in self.next_toxic_regions:
                status_bits.append("⚠️ Toxic Next")
            hazard = self.active_region_hazards.get(region)
            if hazard:
                status_bits.append(f"🔥 {self._hazard_display(hazard)}")
            control_owner = self.region_control_owner.get(region)
            control_streak = self.region_control_streak.get(region, 0)
            if control_owner is not None and control_streak > 0:
                status_bits.append(f"🏴 D{control_owner} x{control_streak}")

            noisy_names = [
                player.display_name
                for player in self._players_in_region(region)
                if player.id in self.revealed_noisy_ids
            ]
            if noisy_names:
                preview = ", ".join(noisy_names[:2])
                if len(noisy_names) > 2:
                    preview += f" +{len(noisy_names) - 2}"
                status_bits.append(f"🔊 {preview}")

            lines.append(f"**{region}**: {' • '.join(status_bits)}")

        active_toxic = (
            ", ".join(sorted(self.active_toxic_regions))
            if self.active_toxic_regions
            else _("None")
        )
        next_toxic = (
            ", ".join(sorted(self.next_toxic_regions))
            if self.next_toxic_regions
            else _("None")
        )
        active_hazards = (
            ", ".join(
                f"{region} ({self._hazard_display(hazard)})"
                for region, hazard in sorted(self.active_region_hazards.items())
            )
            if self.active_region_hazards
            else _("None")
        )
        next_hazards = (
            ", ".join(
                f"{region} ({self._hazard_display(hazard)})"
                for region, hazard in sorted(self.next_region_hazards.items())
            )
            if self.next_region_hazards
            else _("None")
        )

        embed = discord.Embed(
            title=_("🗺️ Arena Regions - Round {round}").format(round=self.round),
            description="\n".join(lines),
            color=discord.Color.dark_gold(),
        )
        embed.add_field(name=_("Toxic Now"), value=active_toxic, inline=False)
        embed.add_field(name=_("Prewarned Toxic"), value=next_toxic, inline=False)
        embed.add_field(name=_("Active Hazards"), value=active_hazards, inline=False)
        embed.add_field(name=_("Prewarned Hazards"), value=next_hazards, inline=False)
        if self._is_collapse_mode():
            embed.add_field(
                name=_("Endgame Collapse"),
                value=_("Cornucopia is now the central safe focus."),
                inline=False,
            )
        embed.set_footer(
            text=_(
                "Scout adjacent regions, manage noise, and complete sponsor contracts."
            )
        )
        await self.ctx.send(embed=embed)
        await self._send_region_brief_dms(embed)

    def _build_action_choices(
        self,
        actor: discord.Member,
        killed_this_round: set,
    ) -> list[dict]:
        current_region = self._region_for(actor)
        choices: list[dict] = [
            {
                "label": _("Scavenge for weapons in {region}").format(
                    region=current_region
                ),
                "kind": "scavenge",
            },
            {
                "label": _("Hide in {region}").format(region=current_region),
                "kind": "hide",
            },
            {
                "label": _("Set a trap in {region}").format(region=current_region),
                "kind": "trap",
            },
        ]

        neighbors = list(self.REGION_ADJACENCY.get(current_region, ()))
        neighbors = random.shuffle(neighbors)
        for region in neighbors[:2]:
            choices.append(
                {
                    "label": _("Move to {region}").format(region=region),
                    "kind": "move",
                    "region": region,
                }
            )

        if neighbors:
            scout_region = random.choice(neighbors)
            choices.append(
                {
                    "label": _("Scout {region}").format(region=scout_region),
                    "kind": "scout",
                    "region": scout_region,
                }
            )

        if current_region in self.region_drops:
            choices.append(
                {
                    "label": _("Loot the supply drop in {region}").format(
                        region=current_region
                    ),
                    "kind": "lootdrop",
                }
            )

        targets = self._eligible_targets(actor, killed_this_round)
        if targets:
            hunt_target = random.choice(targets)
            rush_target = random.choice(targets)
            choices.append(
                {
                    "label": _("Hunt down {target} in {region}").format(
                        target=hunt_target.display_name,
                        region=current_region,
                    ),
                    "kind": "hunt",
                    "target_id": hunt_target.id,
                }
            )
            choices.append(
                {
                    "label": _("Rush {target} in {region}").format(
                        target=rush_target.display_name,
                        region=current_region,
                    ),
                    "kind": "rush",
                    "target_id": rush_target.id,
                }
            )

        allies = self._alive_allies(actor, killed_this_round)
        if allies:
            ally = random.choice(allies)
            choices.append(
                {
                    "label": _("Coordinate with {ally} in {region}").format(
                        ally=ally.display_name,
                        region=current_region,
                    ),
                    "kind": "teamup",
                    "target_id": ally.id,
                }
            )
            choices.append(
                {
                    "label": _("Cover fire for {ally}").format(
                        ally=ally.display_name
                    ),
                    "kind": "coverfire",
                    "target_id": ally.id,
                }
            )
            choices.append(
                {
                    "label": _("Use a shared medkit with {ally}").format(
                        ally=ally.display_name
                    ),
                    "kind": "sharedmedkit",
                    "target_id": ally.id,
                }
            )
            if targets:
                enemy = random.choice(targets)
                choices.append(
                    {
                        "label": _("Ambush {enemy} with {ally}").format(
                            enemy=enemy.display_name,
                            ally=ally.display_name,
                        ),
                        "kind": "ambush",
                        "target_id": enemy.id,
                        "ally_id": ally.id,
                    }
                )
            if self.round > self.ALLIANCE_LOCK_ROUNDS:
                choices.append(
                    {
                        "label": _("Betray {ally} in {region}").format(
                            ally=ally.display_name,
                            region=current_region,
                        ),
                        "kind": "betray",
                        "target_id": ally.id,
                    }
                )

        if len(choices) <= 8:
            return self._ensure_escape_route_choices(actor, killed_this_round, choices)
        core = choices[:3]
        extras = random.sample(choices[3:], k=5)
        picked = core + extras
        return self._ensure_escape_route_choices(actor, killed_this_round, picked)

    async def _choose_action(self, actor: discord.Member, choices: list[dict]) -> dict:
        contract_line = self._contract_prompt_line(self.active_contracts.get(actor.id))
        teammate_intel = self._teammate_intel_prompt(actor)
        try:
            idx = await self.ctx.bot.paginator.Choose(
                entries=[choice["label"] for choice in choices],
                return_index=True,
                title=_(
                    "Choose your arena action\nContract: {contract}\nTeammate intel:"
                    " {intel}\nBack to game: {link}"
                ).format(
                    contract=contract_line,
                    intel=teammate_intel,
                    link=self.game_channel_link,
                ),
                timeout=self.ACTION_TIMEOUT_SECONDS,
            ).paginate(self.ctx, location=actor)
            return choices[idx]
        except (
            self.ctx.bot.paginator.NoChoice,
            discord.Forbidden,
            asyncio.TimeoutError,
        ):
            await self.ctx.send(
                _(
                    "{user} didn't choose in time. The arena decides their move."
                ).format(user=actor.mention),
                delete_after=20,
            )
            return random.choice(choices)

    def _resolve_action(
        self,
        actor: discord.Member,
        action: dict,
        killed_this_round: set,
        elimination_log: dict[int, dict],
    ) -> str:
        kind = action["kind"]
        actor_region = self._region_for(actor)
        self.round_action_kind_by_player_id[actor.id] = kind

        noise_delta = {
            "hunt": 2,
            "rush": 2,
            "betray": 2,
            "ambush": 2,
            "lootdrop": 2,
            "scavenge": 1,
            "trap": 1,
            "teamup": 1,
            "coverfire": 1,
            "sharedmedkit": -1,
            "hide": -2,
            "scout": -1,
        }.get(kind, 0)
        if noise_delta:
            self._adjust_noise(actor.id, noise_delta)

        if kind == "move":
            new_region = str(action.get("region") or "")
            if new_region not in self.REGION_ADJACENCY.get(actor_region, ()):
                return _("tries to move, but gets turned around in the arena.")
            slowed = actor.id in self.round_slow_ids
            self.round_slow_ids.discard(actor.id)
            if slowed and random.randint(1, 100) <= 45:
                return _(
                    "tries to move from **{old}**, but tunnel fatigue slows them down."
                ).format(old=actor_region)
            abandoned = self.traps.get(actor.id, 0)
            if abandoned > 0:
                self.traps[actor.id] = 0
            self.player_region[actor.id] = new_region
            if abandoned > 0:
                return _(
                    "moves from **{old}** to **{new}**, abandoning {count} trap(s)."
                ).format(
                    old=actor_region,
                    new=new_region,
                    count=abandoned,
                )
            return _("moves from **{old}** to **{new}**.").format(
                old=actor_region,
                new=new_region,
            )

        if kind == "scout":
            region = str(action.get("region") or "")
            if region not in self.REGION_ADJACENCY.get(actor_region, ()):
                return _("tries to scout, but picks the wrong direction.")
            seen = self._players_in_region(region, killed_this_round=killed_this_round)
            has_drop = region in self.region_drops
            has_trap = any(self.traps.get(player.id, 0) > 0 for player in seen)
            drop_text = _("drop visible") if has_drop else _("no drop")
            trap_text = _("traps detected") if has_trap else _("no trap signs")
            self._adjust_noise(actor.id, -1)
            return _(
                "scouts **{region}**: 👥 {count} tribute(s), {drop}, {traps}."
            ).format(region=region, count=len(seen), drop=drop_text, traps=trap_text)

        if kind == "lootdrop":
            if actor_region not in self.region_drops:
                return _("searches for a drop in **{region}**, but it's gone.").format(
                    region=actor_region
                )
            gain = self.region_drops.pop(actor_region)
            if actor_region == "Cornucopia":
                gain += 1
            self.gear_score[actor.id] = min(10, self.gear_score[actor.id] + gain)
            return _("claims the supply drop in **{region}** and upgrades gear.").format(
                region=actor_region
            )

        target = None
        if kind in {"hunt", "rush", "teamup", "betray", "coverfire", "sharedmedkit"}:
            target = self._alive_target(action.get("target_id"), killed_this_round)
            if target is None:
                return _("finds no valid target and wastes the move.")
            if self._region_for(target) != actor_region:
                return _(
                    "targets **{target}**, but they already moved away from **{region}**."
                ).format(target=target.display_name, region=actor_region)

        if kind == "ambush":
            target = self._alive_target(action.get("target_id"), killed_this_round)
            ally = self._alive_target(action.get("ally_id"), killed_this_round)
            if target is None or ally is None or ally in {target, actor}:
                return _("can't coordinate the ambush and loses the chance.")
            if self._region_for(target) != actor_region or self._region_for(ally) != actor_region:
                return _("tries to set an ambush, but the formation collapses.")
            if self._check_trap_trigger(actor, target, killed_this_round, elimination_log):
                return _("walks into **{target}**'s trap while setting the ambush.").format(
                    target=target.display_name
                )
            chance = (
                55
                + self.gear_score[actor.id] * 5
                + self.gear_score[ally.id] * 3
                + self.combat_bonus_by_player_id.get(actor.id, 0)
                + self.combat_bonus_by_player_id.get(ally.id, 0) // 2
            )
            if actor_region == "Stone Quarry":
                chance += 10
            elif actor_region == "Cornucopia":
                chance += 6
            if target.id in self.hidden_ids:
                chance -= 12
            if target.id in self.tunnel_hidden_ids:
                chance -= 8
            chance = max(20, min(96, chance))
            if random.randint(1, 100) <= chance:
                self._mark_kill(
                    actor,
                    target,
                    killed_this_round,
                    elimination_log=elimination_log,
                    cause=_("was eliminated in a district ambush by **{killer}**").format(
                        killer=actor.display_name
                    ),
                )
                return _("ambushes **{target}** with **{ally}** and secures the kill.").format(
                    target=target.display_name, ally=ally.display_name
                )
            if random.randint(1, 100) <= 35:
                self._mark_kill(
                    target,
                    actor,
                    killed_this_round,
                    elimination_log=elimination_log,
                    cause=_("was counter-killed by **{killer}** during an ambush").format(
                        killer=target.display_name
                    ),
                )
                return _("attempts an ambush on **{target}**, but gets counter-killed.").format(
                    target=target.display_name
                )
            return _("sets an ambush on **{target}**, but they slip away.").format(
                target=target.display_name
            )

        if kind == "scavenge":
            gain = random.randint(1, 2)
            if self.round == 1 and random.randint(1, 100) <= 30:
                gain += 1
            if actor_region == "Cornucopia":
                gain += 1
            self.gear_score[actor.id] = min(10, self.gear_score[actor.id] + gain)
            return _("scavenges and upgrades to {gear}.").format(
                gear=self._weapon_name(self.gear_score[actor.id])
            )

        if kind == "hide":
            self.hidden_ids.add(actor.id)
            if actor_region == "Underground Tunnels":
                self.tunnel_hidden_ids.add(actor.id)
                return _("vanishes deep in the tunnels and becomes hard to track.")
            return _("vanishes into cover and stays hidden.")

        if kind == "trap":
            self.traps[actor.id] = min(4, self.traps[actor.id] + 1)
            return _("sets a trap. ({count} trap(s) active)").format(
                count=self.traps[actor.id]
            )

        if kind == "teamup" and target is not None:
            self.gear_score[actor.id] = min(10, self.gear_score[actor.id] + 1)
            self.gear_score[target.id] = min(10, self.gear_score[target.id] + 1)
            self.hidden_ids.discard(target.id)
            return _("teams up with **{ally}** and both leave stronger.").format(
                ally=target.display_name
            )

        if kind == "coverfire" and target is not None:
            self.combat_bonus_by_player_id[actor.id] = min(
                20, self.combat_bonus_by_player_id.get(actor.id, 0) + 6
            )
            self.combat_bonus_by_player_id[target.id] = min(
                20, self.combat_bonus_by_player_id.get(target.id, 0) + 10
            )
            return _("lays down cover fire for **{ally}**. District combat odds improve.").format(
                ally=target.display_name
            )

        if kind == "sharedmedkit" and target is not None:
            self.gear_score[actor.id] = min(10, self.gear_score[actor.id] + 1)
            self.gear_score[target.id] = min(10, self.gear_score[target.id] + 1)
            self.fog_resistance_rounds[actor.id] = min(
                4, self.fog_resistance_rounds.get(actor.id, 0) + 1
            )
            self.fog_resistance_rounds[target.id] = min(
                4, self.fog_resistance_rounds.get(target.id, 0) + 1
            )
            return _(
                "shares a medkit with **{ally}**. Both recover and gain light fog protection."
            ).format(ally=target.display_name)

        if kind == "betray" and target is not None:
            if self.round <= self.ALLIANCE_LOCK_ROUNDS:
                return _("hesitates. Alliances are still locked this round.")
            bonus = self.combat_bonus_by_player_id.get(actor.id, 0) // 2
            if actor_region == "Stone Quarry":
                bonus += 6
            success_chance = min(93, 45 + self.gear_score[actor.id] * 7 + bonus)
            if random.randint(1, 100) <= success_chance:
                self._mark_kill(
                    actor,
                    target,
                    killed_this_round,
                    elimination_log=elimination_log,
                    cause=_("was betrayed by **{killer}**").format(
                        killer=actor.display_name
                    ),
                )
                self.gear_score[actor.id] = min(10, self.gear_score[actor.id] + 1)
                return _("betrays **{ally}** and takes their loot.").format(
                    ally=target.display_name
                )
            if random.randint(1, 100) <= 50:
                self._mark_kill(
                    target,
                    actor,
                    killed_this_round,
                    elimination_log=elimination_log,
                    cause=_("was executed by **{killer}** during a failed betrayal").format(
                        killer=target.display_name
                    ),
                )
                return _("tries to betray **{ally}**, but gets executed first.").format(
                    ally=target.display_name
                )
            return _("tries to betray **{ally}**, but the moment passes.").format(
                ally=target.display_name
            )

        if target is None:
            return _("does something chaotic but pointless.")

        if kind == "hunt" and (
            target.id in self.hidden_ids or target.id in self.tunnel_hidden_ids
        ):
            return _("tries to hunt **{target}**, but they stay hidden.").format(
                target=target.display_name
            )

        if kind == "hunt" and self._check_trap_trigger(
            actor,
            target,
            killed_this_round,
            elimination_log,
            bonus_chance=20,
        ):
            return _("tracks **{target}** but triggers their trap and dies.").format(
                target=target.display_name
            )

        actor_gear = self.gear_score[actor.id]
        target_gear = self.gear_score[target.id]
        target_traps = self.traps.get(target.id, 0)
        regional_bonus = 12 if actor_region == "Stone Quarry" else 6 if actor_region == "Cornucopia" else 0
        hidden_penalty = 0
        if target.id in self.hidden_ids:
            hidden_penalty += 18
        if target.id in self.tunnel_hidden_ids:
            hidden_penalty += 8
        actor_bonus = self.combat_bonus_by_player_id.get(actor.id, 0)
        target_bonus = self.combat_bonus_by_player_id.get(target.id, 0)

        if kind == "hunt":
            chance = (
                30
                + actor_gear * 4
                + min(14, self.round * 2)
                + actor_bonus // 2
                + regional_bonus // 2
                - hidden_penalty
                - min(18, target_gear * 2)
                - target_traps * 12
            )
            chance = max(8, min(90, chance))
            if random.randint(1, 100) <= chance:
                self._mark_kill(
                    actor,
                    target,
                    killed_this_round,
                    elimination_log=elimination_log,
                    cause=_("was hunted down by **{killer}**").format(
                        killer=actor.display_name
                    ),
                )
                return _("hunts down **{target}** cleanly.").format(
                    target=target.display_name
                )
            counter_chance = min(
                75,
                22 + target_gear * 4 + target_bonus // 3 + target_traps * 8,
            )
            if random.randint(1, 100) <= counter_chance:
                self._mark_kill(
                    target,
                    actor,
                    killed_this_round,
                    elimination_log=elimination_log,
                    cause=_("was counter-killed by **{killer}**").format(
                        killer=target.display_name
                    ),
                )
                return _("misses **{target}** and gets counter-killed.").format(
                    target=target.display_name
                )
            return _("tracks **{target}** but loses them in the terrain.").format(
                target=target.display_name
            )

        if kind == "rush":
            chance = (
                38
                + actor_gear * 8
                + min(10, self.round)
                + actor_bonus // 3
                + regional_bonus
                - hidden_penalty // 2
                - min(24, target_gear * 3)
            )
            chance = max(10, min(93, chance))
            if random.randint(1, 100) <= chance:
                self._mark_kill(
                    actor,
                    target,
                    killed_this_round,
                    elimination_log=elimination_log,
                    cause=_("was killed in a brawl by **{killer}**").format(
                        killer=actor.display_name
                    ),
                )
                bleed_chance = 35 + (8 if actor_region == "Stone Quarry" else 0)
                if random.randint(1, 100) <= bleed_chance:
                    self._mark_kill(
                        None,
                        actor,
                        killed_this_round,
                        elimination_log=elimination_log,
                        cause=_("bled out after a reckless brawl"),
                    )
                    return _("rushes **{target}**, kills them, then bleeds out.").format(
                        target=target.display_name
                    )
                return _("rushes **{target}** and wins the brawl.").format(
                    target=target.display_name
                )
            counter_chance = 30 + target_gear * 3 - actor_gear * 2 + target_bonus // 4
            counter_chance = max(18, min(70, counter_chance))
            if random.randint(1, 100) <= counter_chance:
                self._mark_kill(
                    target,
                    actor,
                    killed_this_round,
                    elimination_log=elimination_log,
                    cause=_("was dropped by **{killer}** in a rush attempt").format(
                        killer=target.display_name
                    ),
                )
                return _("rushes **{target}** and gets dropped instantly.").format(
                    target=target.display_name
                )
            return _("rushes **{target}** but neither can finish it.").format(
                target=target.display_name
            )

        return _("does something chaotic but pointless.")

    def _apply_dynamic_hazards(
        self,
        killed_this_round: set,
        round_lines: list[str],
        elimination_log: dict[int, dict],
    ) -> None:
        for region, hazard in self.active_region_hazards.items():
            impacted = self._players_in_region(region, killed_this_round=killed_this_round)
            if not impacted:
                continue

            if hazard == "wildfire":
                burned_names = []
                killed_names = []
                for player in list(impacted):
                    if player in killed_this_round:
                        continue
                    chance = 24 + self.fog_stage * 4
                    if random.randint(1, 100) <= chance:
                        self._mark_kill(
                            None,
                            player,
                            killed_this_round,
                            elimination_log=elimination_log,
                            cause=_("was consumed by wildfire in **{region}**").format(
                                region=region
                            ),
                        )
                        killed_names.append(player.display_name)
                    else:
                        self.gear_score[player.id] = max(0, self.gear_score[player.id] - 1)
                        burned_names.append(player.display_name)
                if killed_names:
                    round_lines.append(
                        _("🔥 Wildfire sweeps **{region}**. Fallen: {fallen}.").format(
                            region=region,
                            fallen=nice_join([f"**{name}**" for name in killed_names]),
                        )
                    )
                elif burned_names:
                    round_lines.append(
                        _(
                            "🔥 Wildfire scorches **{region}**. {names} lose gear."
                        ).format(
                            region=region,
                            names=nice_join([f"**{name}**" for name in burned_names]),
                        )
                    )
                continue

            if hazard == "mutt_migration":
                candidates = [p for p in impacted if p.id not in self.hidden_ids] or impacted
                victim = random.choice(candidates)
                lethality = self._mutt_lethality_chance(
                    victim, base_chance=66, min_chance=24
                )
                if random.randint(1, 100) <= lethality:
                    self._mark_kill(
                        None,
                        victim,
                        killed_this_round,
                        elimination_log=elimination_log,
                        cause=_("was mauled during mutt migration in **{region}**").format(
                            region=region
                        ),
                    )
                    round_lines.append(
                        _("🐺 Mutts migrate through **{region}** and tear apart **{victim}**.").format(
                            region=region,
                            victim=victim.display_name,
                        )
                    )
                else:
                    loss = self._apply_mutt_gear_loss(victim)
                    round_lines.append(
                        _(
                            "🐺 Mutts flood **{region}**. **{victim}** escapes but loses {loss} gear level(s)."
                        ).format(
                            region=region,
                            victim=victim.display_name,
                            loss=loss,
                        )
                    )
                continue

            targets = random.sample(impacted, k=min(2, len(impacted)))
            downed = []
            stung = []
            for player in targets:
                if player in killed_this_round:
                    continue
                self._adjust_noise(player.id, 2)
                if random.randint(1, 100) <= 26:
                    self._mark_kill(
                        None,
                        player,
                        killed_this_round,
                        elimination_log=elimination_log,
                        cause=_("was overwhelmed by tracker-jackers in **{region}**").format(
                            region=region
                        ),
                    )
                    downed.append(player.display_name)
                else:
                    self.gear_score[player.id] = max(0, self.gear_score[player.id] - 1)
                    stung.append(player.display_name)
            if downed:
                round_lines.append(
                    _("🐝 Tracker-jackers descend on **{region}**. Fallen: {names}.").format(
                        region=region,
                        names=nice_join([f"**{name}**" for name in downed]),
                    )
                )
            elif stung:
                round_lines.append(
                    _("🐝 Tracker-jackers swarm **{region}**. {names} panic and lose gear.").format(
                        region=region,
                        names=nice_join([f"**{name}**" for name in stung]),
                    )
                )

    def _apply_toxic_fog(
        self,
        killed_this_round: set,
        round_lines: list[str],
        elimination_log: dict[int, dict],
    ) -> None:
        if not self.active_toxic_regions:
            return
        for player in list(self.players):
            if player in killed_this_round:
                continue
            region = self._region_for(player)
            if region not in self.active_toxic_regions:
                continue

            alive = len(self.players)
            chance = 10 + self.fog_stage * 8
            if alive <= 4:
                chance += 14
            elif alive <= 6:
                chance += 8
            elif alive <= 8:
                chance += 4
            if player.id in self.hidden_ids:
                chance = max(5, chance - 8)
            if player.id in self.tunnel_hidden_ids:
                chance = max(5, chance - 6)
            if self.fog_resistance_rounds.get(player.id, 0) > 0:
                chance = max(5, chance - 18)
            if region == "Stone Quarry":
                chance += 12
            chance = max(5, chance - min(14, self.gear_score[player.id] * 2))
            chance = min(92, chance)

            if random.randint(1, 100) <= chance:
                self._mark_kill(
                    None,
                    player,
                    killed_this_round,
                    elimination_log=elimination_log,
                    cause=_("succumbed to toxic fog in **{region}**").format(
                        region=region
                    ),
                )
                round_lines.append(
                    _("☣️ Toxic fog engulfs **{victim}** in **{region}**.").format(
                        victim=player.display_name,
                        region=region,
                    )
                )
            else:
                loss = 2 if region == "Stone Quarry" else 1
                self.gear_score[player.id] = max(0, self.gear_score[player.id] - loss)
                round_lines.append(
                    _("☣️ **{survivor}** escapes fog in **{region}**, but loses gear.").format(
                        survivor=player.display_name,
                        region=region,
                    )
                )

    async def _send_round_report(
        self,
        round_lines: list[str],
        killed_this_round: set,
        elimination_log: dict[int, dict],
    ) -> None:
        await super()._send_round_report(round_lines, killed_this_round, elimination_log)

        noisy = [
            self.member_by_id[player_id].display_name
            for player_id in self.revealed_noisy_ids
            if player_id in self.member_by_id and self.member_by_id[player_id] in self.players
        ]
        control_lines = [
            f"{region}: District #{owner} ({self.region_control_streak.get(region, 0)})"
            for region, owner in self.region_control_owner.items()
            if owner is not None and self.region_control_streak.get(region, 0) > 0
        ]
        extra = discord.Embed(
            title=_("Region-Ideas Systems"),
            description=_(
                "🔊 Revealed noisy tributes next round: {noisy}\n"
                "🏴 Control streaks: {control}\n"
                "⚠️ Prewarned hazards: {hazards}"
            ).format(
                noisy=", ".join(noisy) if noisy else _("None"),
                control=", ".join(control_lines) if control_lines else _("None"),
                hazards=", ".join(
                    f"{region} ({self._hazard_display(hazard)})"
                    for region, hazard in sorted(self.next_region_hazards.items())
                )
                if self.next_region_hazards
                else _("None"),
            ),
            color=discord.Color.dark_purple(),
        )
        await self.ctx.send(embed=extra)

    async def send_cast(self):
        await super().send_cast()
        await self.ctx.send(
            embed=discord.Embed(
                title=_("Region-Ideas Rules"),
                description=_(
                    "Advanced region systems are active: region passives, noise reveals,"
                    " scouting, sponsor contracts, district combo actions, dynamic"
                    " hazards, control-point bonuses, and endgame collapse pressure."
                ),
                color=discord.Color.gold(),
            )
        )

    async def get_inputs(self):
        status = await self.ctx.send(
            _("🔥 **Round {round}** begins...").format(round=self.round),
            delete_after=45,
        )
        self.hidden_ids = set()
        self.tunnel_hidden_ids = set()
        self.round_action_kind_by_player_id = {}
        self.round_kill_events = []
        self.combat_bonus_by_player_id = {player.id: 0 for player in self.players}
        killed_this_round: set[discord.Member] = set()
        round_lines: list[str] = []
        elimination_log: dict[int, dict] = {}

        self.round_slow_ids = set(self.slow_next_round_ids)
        self.active_toxic_regions = set(self.next_toxic_regions)
        self.active_region_hazards = dict(self.next_region_hazards)
        self.active_mutt_regions = set(self.next_mutt_regions)
        self.fog_stage = max(1, min(6, 1 + (self.round - 1) // 2))
        self._spawn_region_drops()
        self.next_toxic_regions = self._pick_next_toxic_regions()
        self.next_region_hazards = self._pick_next_region_hazards()
        self.next_mutt_regions = set()
        self._assign_sponsor_contracts()

        if self._is_collapse_mode() and not self.collapse_announced:
            self.collapse_announced = True
            await self.ctx.send(
                _(
                    "🚨 Endgame collapse engaged. Outer regions are being sealed."
                    " Cornucopia is becoming the final battlefield."
                )
            )

        await self._send_region_brief()

        actors = [actor for actor in self.players if actor not in killed_this_round]
        choices_by_actor_id: dict[int, list[dict]] = {}
        for actor in actors:
            choices = self._build_action_choices(actor, killed_this_round)
            if choices:
                choices_by_actor_id[actor.id] = choices

        async def choose_for_actor(
            actor: discord.Member, choices: list[dict]
        ) -> tuple[discord.Member, dict | None]:
            if not choices:
                return actor, None
            action = await self._choose_action(actor, choices)
            return actor, action

        selected_actions_by_actor_id: dict[int, dict] = {}
        choose_tasks = [
            choose_for_actor(actor, choices_by_actor_id.get(actor.id, []))
            for actor in actors
            if actor.id in choices_by_actor_id
        ]
        if choose_tasks:
            await self.ctx.send(
                _("📩 Action prompts sent to all tributes. Choices lock together.")
            )
            for actor, action in await asyncio.gather(*choose_tasks):
                if action is not None:
                    selected_actions_by_actor_id[actor.id] = action
            await self.ctx.send(_("⏳ Action phase closed. Resolving round..."))

        turn_order = actors.copy()
        turn_order = random.shuffle(turn_order)
        for actor in turn_order:
            if actor not in self.players or actor in killed_this_round:
                continue
            action = selected_actions_by_actor_id.get(actor.id)
            if action is None:
                fallback_choices = choices_by_actor_id.get(actor.id, [])
                if not fallback_choices:
                    continue
                action = random.choice(fallback_choices)
            summary = self._resolve_action(actor, action, killed_this_round, elimination_log)
            round_lines.append(f"**{actor.display_name}** {summary}")

        self._apply_riverbank_recovery(killed_this_round, round_lines)
        self._apply_cornucopia_conflict(killed_this_round, round_lines, elimination_log)
        await self._resolve_arena_event(killed_this_round, round_lines, elimination_log)
        self._apply_dynamic_hazards(killed_this_round, round_lines, elimination_log)
        self._resolve_contracts(killed_this_round, round_lines)
        self._apply_toxic_fog(killed_this_round, round_lines, elimination_log)

        if killed_this_round:
            self.no_kill_rounds = 0
        else:
            self.no_kill_rounds += 1
            self._resolve_stalemate(killed_this_round, round_lines, elimination_log)
            if killed_this_round:
                self.no_kill_rounds = 0

        for dead in list(killed_this_round):
            try:
                self.players.remove(dead)
            except ValueError:
                pass

        self._decrement_fog_shields()
        self._update_noise_visibility()
        self._update_tunnel_slow_state()
        self._update_region_control_points(round_lines)

        try:
            await status.delete()
        except discord.NotFound:
            pass
        await self._send_round_report(round_lines, killed_this_round, elimination_log)
        self.round += 1


class HungerGames(commands.Cog):
    REGION_DM_SETTINGS_TABLE = "hungergames_dm_settings"

    def __init__(self, bot):
        self.bot = bot
        self.games = {}
        self._region_board_dm_cache: dict[int, bool] = {}
        self._region_dm_settings_ready = False

    async def cog_load(self) -> None:
        await self._ensure_region_dm_settings_table()

    async def _ensure_region_dm_settings_table(self) -> None:
        if self._region_dm_settings_ready:
            return
        if not hasattr(self.bot, "pool"):
            return
        try:
            await self.bot.pool.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {self.REGION_DM_SETTINGS_TABLE} (
                    "user_id" BIGINT PRIMARY KEY,
                    "region_board_dm" BOOLEAN NOT NULL DEFAULT TRUE
                );
                """
            )
            self._region_dm_settings_ready = True
        except Exception:
            # DB failures should never block playing the game.
            self._region_dm_settings_ready = False

    async def region_board_dm_enabled(self, user_id: int) -> bool:
        if user_id in self._region_board_dm_cache:
            return self._region_board_dm_cache[user_id]

        if not hasattr(self.bot, "pool"):
            return True

        await self._ensure_region_dm_settings_table()
        if not self._region_dm_settings_ready:
            return True

        try:
            row = await self.bot.pool.fetchrow(
                f"""
                SELECT "region_board_dm"
                FROM {self.REGION_DM_SETTINGS_TABLE}
                WHERE "user_id" = $1;
                """,
                user_id,
            )
        except Exception:
            return True

        enabled = True if row is None else bool(row["region_board_dm"])
        self._region_board_dm_cache[user_id] = enabled
        return enabled

    async def _set_region_board_dm_enabled(self, user_id: int, enabled: bool) -> None:
        self._region_board_dm_cache[user_id] = enabled

        if not hasattr(self.bot, "pool"):
            return

        await self._ensure_region_dm_settings_table()
        if not self._region_dm_settings_ready:
            return

        try:
            await self.bot.pool.execute(
                f"""
                INSERT INTO {self.REGION_DM_SETTINGS_TABLE} ("user_id", "region_board_dm")
                VALUES ($1, $2)
                ON CONFLICT ("user_id")
                DO UPDATE SET "region_board_dm" = EXCLUDED."region_board_dm";
                """,
                user_id,
                enabled,
            )
        except Exception:
            pass

    def _regions_map_text(self) -> str:
        lines = []
        for region in RegionGame.REGIONS:
            neighbors = ", ".join(RegionGame.REGION_ADJACENCY.get(region, ()))
            lines.append(f"**{region}** -> {neighbors}")
        return "\n".join(lines)

    def _active_game_for_player(self, player_id: int) -> GameBase | None:
        for game in self.games.values():
            if not isinstance(game, GameBase):
                continue
            if player_id in game.member_by_id:
                return game
        return None

    def _living_teammates(self, game: GameBase, player: discord.Member) -> list[discord.Member]:
        ally_ids = game.allies_by_player_id.get(player.id, set())
        teammates = []
        for ally_id in sorted(ally_ids):
            ally = game.member_by_id.get(ally_id)
            if ally is None or ally not in game.players or ally == player:
                continue
            teammates.append(ally)
        return teammates

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot or message.guild is not None:
            return
        if not isinstance(message.author, discord.Member):
            # In DMs, discord.py returns User for cached-less cases; we still
            # support relays by resolving via member_by_id in the game object.
            pass

        game = self._active_game_for_player(message.author.id)
        if game is None:
            return

        sender = game.member_by_id.get(message.author.id)
        if sender is None or sender not in game.players:
            return

        teammates = self._living_teammates(game, sender)
        if not teammates:
            return

        content = message.content.strip()
        attachment_urls = [a.url for a in message.attachments]
        if not content and not attachment_urls:
            return

        payload_lines = []
        if content:
            payload_lines.append(content)
        if attachment_urls:
            payload_lines.append("\n".join(attachment_urls))
        payload = "\n".join(payload_lines)

        if isinstance(game, RegionGame):
            sender_location = game._region_for(sender)
            heading = _("📨 Team relay from **{sender}** in **{region}**").format(
                sender=sender.display_name,
                region=sender_location,
            )
        else:
            heading = _("📨 Team relay from **{sender}**").format(
                sender=sender.display_name
            )

        delivered = 0
        for teammate in teammates:
            try:
                await teammate.send(f"{heading}:\n{payload}")
                delivered += 1
            except (discord.Forbidden, discord.HTTPException):
                continue

        if delivered > 0:
            try:
                await message.channel.send(
                    _("✅ Relayed to {count} teammate(s).").format(count=delivered)
                )
            except discord.HTTPException:
                pass

    def _format_joined_players(self, joined: set) -> str:
        if not joined:
            return _("None yet")

        sorted_joined = sorted(
            joined,
            key=lambda user: getattr(user, "display_name", str(user)).casefold(),
        )
        preview_limit = 20
        preview = ", ".join(user.mention for user in sorted_joined[:preview_limit])
        extra = len(sorted_joined) - preview_limit
        if extra > 0:
            return _("{players}, and {extra} more").format(players=preview, extra=extra)
        return preview

    def _build_join_lobby_text(
        self,
        *,
        author_mention: str,
        mode_label: str,
        seconds_left: int,
        joined: set,
        is_mass_game: bool,
        extra_note: str | None = None,
    ) -> str:
        if is_mass_game:
            intro = _(
                "{author} started a mass-game of Hunger Games (**{mode}** mode)!"
            ).format(author=author_mention, mode=mode_label)
        else:
            intro = _("{author} started a game of Hunger Games (**{mode}** mode)!").format(
                author=author_mention, mode=mode_label
            )

        minutes, seconds = divmod(max(0, seconds_left), 60)
        timer = f"{minutes:02d}:{seconds:02d}"
        joined_players = self._format_joined_players(joined)
        text = _(
            "{intro}\n"
            "⏳ Starts in: **{timer}**\n"
            "👥 Joined ({count}): {players}"
        ).format(
            intro=intro,
            timer=timer,
            count=len(joined),
            players=joined_players,
        )
        if extra_note:
            text = f"{text}\n{extra_note}"
        return text

    async def _run_join_countdown(
        self,
        *,
        message: discord.Message,
        view: JoinView,
        author_mention: str,
        mode_label: str,
        duration_seconds: int,
        is_mass_game: bool,
        extra_note: str | None = None,
    ) -> None:
        update_interval = 5
        remaining = duration_seconds
        while remaining > 0 and not view.is_finished():
            wait_for = min(update_interval, remaining)
            await asyncio.sleep(wait_for)
            remaining -= wait_for
            try:
                await message.edit(
                    content=self._build_join_lobby_text(
                        author_mention=author_mention,
                        mode_label=mode_label,
                        seconds_left=remaining,
                        joined=view.joined,
                        is_mass_game=is_mass_game,
                        extra_note=extra_note,
                    ),
                    view=view,
                )
            except discord.NotFound:
                break
            except discord.HTTPException:
                pass
        view.stop()

    @commands.command(
        aliases=["hgdm", "hgdms"],
        brief=_("Toggle region board DMs"),
    )
    @locale_doc
    async def hgdmboard(self, ctx, setting: str | None = None):
        _(
            """Toggles DM board updates for Hunger Games region modes

            Enabled by default. When enabled, you receive the region board in DMs each round.

            Usage:
            - `{prefix}hgdmboard`
            - `{prefix}hgdmboard on`
            - `{prefix}hgdmboard off`"""
        )
        if setting is None:
            enabled = await self.region_board_dm_enabled(ctx.author.id)
            status = _("enabled") if enabled else _("disabled")
            return await ctx.send(
                _("Region board DMs are currently **{status}**.").format(
                    status=status
                )
            )

        normalized = setting.strip().casefold()
        truthy = {"on", "enable", "enabled", "true", "yes", "y", "1"}
        falsy = {"off", "disable", "disabled", "false", "no", "n", "0"}

        if normalized in truthy:
            enabled = True
        elif normalized in falsy:
            enabled = False
        else:
            return await ctx.send(
                _("Invalid option `{value}`. Use `on` or `off`.").format(
                    value=setting
                )
            )

        await self._set_region_board_dm_enabled(ctx.author.id, enabled)
        status = _("enabled") if enabled else _("disabled")
        await ctx.send(_("Region board DMs are now **{status}**.").format(status=status))

    @commands.command(
        aliases=["hgregionshelp", "hgregionhelp", "hgrules"],
        brief=_("Show Hunger Games regions mode help"),
    )
    @locale_doc
    async def hgregions(self, ctx, *, mode: str | None = None):
        _(
            """Shows how Hunger Games region modes work

            Use this command to learn movement, fog, mutts, traps, and team mechanics.

            Usage:
            - `{prefix}hgregions`
            - `{prefix}hgregions region-ideas`
            - `{prefix}hgregions regions-gm`"""
        )
        token = (mode or "regions").strip().casefold()
        advanced_tokens = {"region-ideas", "regionideas", "ideas", "advanced"}
        gm_tokens = {"regions-gm", "region-gm", "regionsgm", "regiongm", "gm"}
        base_tokens = {"regions", "region", "basic", ""}
        if token not in base_tokens and token not in advanced_tokens and token not in gm_tokens:
            return await ctx.send(
                _(
                    "Unknown mode `{mode}`. Valid options: `regions`, `region-ideas`, `regions-gm`."
                ).format(mode=mode or "")
            )

        core = discord.Embed(
            title=_("🗺️ Hunger Games Regions Help"),
            description=_(
                "How rounds resolve:\n"
                "1) Region brief\n"
                "2) DM choices\n"
                "3) Action resolution\n"
                "4) Arena event + toxic fog\n"
                "5) Round report"
            ),
            color=discord.Color.dark_gold(),
        )
        core.add_field(
            name=_("Connected Map"),
            value=self._regions_map_text(),
            inline=False,
        )
        core.add_field(
            name=_("Fog & Mutts"),
            value=_(
                "Emote key:\n"
                "☣️ `Toxic Now` = active this round\n"
                "⚠️ `Toxic Next` = warning for next round\n"
                "🐺 `Mutts This Round` = mutt threat can strike now\n"
                "🐾 `Mutt Warning Next` = warning only\n"
                "\n"
                "Fog resolves after movement/actions, so moving into ☣️ can get"
                " checked immediately.\n"
                "🐾 warns first; mutts can strike there next round only if 2+"
                " tributes remain."
            ),
            inline=False,
        )
        core.add_field(
            name=_("Combat & Traps"),
            value=_(
                "Combat:\n"
                "• `Hunt` fails against hidden targets\n"
                "• `Hunt` is trap-sensitive\n"
                "• `Rush` is more gear-focused\n"
                "\n"
                "Traps:\n"
                "• Trap stacks cap at 4\n"
                "• Moving abandons your trap stack\n"
                "• Trigger: `12 + 14*traps` (`+20` on hunt), max `70%`"
            ),
            inline=False,
        )
        core.add_field(
            name=_("Teams"),
            value=_(
                "• Betrayals unlock after round {round}.\n"
                "• `Coordinate/Team up` gives both teammates +1 gear.\n"
                "• DM the bot to relay to your living district teammate.\n"
                "• One district can win together.\n"
                "• `hgdmboard on/off` toggles region board DMs (default: on)."
            ).format(round=GameBase.ALLIANCE_LOCK_ROUNDS),
            inline=False,
        )
        core.set_footer(
            text=_(
                "Stalemate rule: after {rounds} bloodless rounds, survivors are forced to Cornucopia for sudden death."
            ).format(rounds=RegionGame.STALEMATE_ROUNDS)
        )
        await ctx.send(embed=core)

        if token in advanced_tokens:
            advanced = discord.Embed(
                title=_("⚙️ Region-Ideas Extras"),
                color=discord.Color.gold(),
                description=_(
                    "Region-Ideas keeps all base region rules and adds deeper systems."
                ),
            )
            advanced.add_field(
                name=_("Extra Actions"),
                value=_(
                    "• `Scout`: checks adjacent region population/drop/trap signs.\n"
                    "• `Ambush`: team attack option.\n"
                    "• `Cover Fire`: boosts district combat odds.\n"
                    "• `Shared Medkit`: both gain gear and fog resistance."
                ),
                inline=False,
            )
            advanced.add_field(
                name=_("Advanced Systems"),
                value=_(
                    "• Noise can reveal your region.\n"
                    "• Sponsor contracts grant bonuses.\n"
                    "• Dynamic hazards (wildfire, mutt migration, tracker-jackers).\n"
                    "• Region control bonuses and endgame collapse pressure."
                ),
                inline=False,
            )
            await ctx.send(embed=advanced)

        if token in gm_tokens:
            gm_embed = discord.Embed(
                title=_("🎛️ Regions-GM Extras"),
                color=discord.Color.orange(),
                description=_(
                    "One joined player is randomly chosen as Game Master and does not fight as a tribute."
                ),
            )
            gm_embed.add_field(
                name=_("Game Master Phase"),
                value=_(
                    "Before each round, the Game Master chooses:\n"
                    "• sponsor drop regions for the current round\n"
                    "• up to 2 toxic regions for the next round\n"
                    "• 1 mutt warning region for the next round\n"
                    "• Sudden Death duelists when multiple valid tributes remain"
                ),
                inline=False,
            )
            gm_embed.add_field(
                name=_("Mode Rules"),
                value=_(
                    "• Regions-GM needs at least 4 joined players.\n"
                    "• You may force a specific GM with `{prefix}hungergames regions-gm <discord_id>`.\n"
                    "• The Game Master sees where tributes are by region.\n"
                    "• If the Game Master leaves slots blank or goes AFK, the arena auto-fills the missing directives."
                ).format(prefix=ctx.clean_prefix),
                inline=False,
            )
            await ctx.send(embed=gm_embed)


    @commands.command(aliases=["hg"], brief=_("Play the hunger games"))
    @locale_doc
    async def hungergames(self, ctx, *, mode: str | None = None):
        _(
            """Starts the hunger games

            Players will be able to join via the :shallow_pan_of_food: emoji.
            District teams are formed at the start and alliance protection lasts for a few rounds before betrayals unlock.
            The game mixes random outcomes with player-selected actions.
            Players may get direct messages to choose actions; if no action is chosen, the bot picks one.

            Modes:
            - `classic` (default): current round-based battle system
            - `regions`: movement between regions, sponsor drops, and prewarned toxic fog zones
            - `region-ideas`: advanced region systems (passives, scouting, contracts, hazards, control points, collapse)
            - `regions-gm`: one random joined player becomes the Game Master and controls drops, toxic warnings, and mutt pressure

            Usage:
            - `{prefix}hungergames`
            - `{prefix}hungergames regions`
            - `{prefix}hungergames region-ideas`
            - `{prefix}hungergames regions-gm`
            - `{prefix}hungergames regions-gm 123456789012345678`
            - `{prefix}hgregions` (regions help)
            - `{prefix}hgdmboard on/off` (region board DM toggle)"""
        )
        if self.games.get(ctx.channel.id):
            return await ctx.send(_("There is already a game in here!"))

        raw_mode = (mode or "classic").strip()
        mode_parts = raw_mode.split() if raw_mode else ["classic"]
        normalized_mode = mode_parts[0].casefold()
        gm_tokens = {"regions-gm", "region-gm", "regionsgm", "regiongm", "gm"}
        forced_gm_id: int | None = None

        if normalized_mode not in gm_tokens and len(mode_parts) > 1:
            return await ctx.send(
                _(
                    "Too many mode arguments. Use `classic`, `regions`, `region-ideas`, or `regions-gm <discord_id>`."
                )
            )

        if normalized_mode in gm_tokens and len(mode_parts) > 2:
            return await ctx.send(
                _(
                    "Too many arguments for `regions-gm`. Use `regions-gm` or `regions-gm <discord_id>`."
                )
            )

        if normalized_mode in gm_tokens and len(mode_parts) == 2:
            forced_token = mode_parts[1].strip()
            if forced_token.startswith("<@") and forced_token.endswith(">"):
                forced_token = forced_token.strip("<@!>")
            if not forced_token.isdigit():
                return await ctx.send(
                    _(
                        "Invalid GM id `{value}`. Use a Discord user ID or mention."
                    ).format(value=mode_parts[1])
                )
            forced_gm_id = int(forced_token)

        gm_mode = False
        mode_note = None
        if normalized_mode in {"classic", "default", ""}:
            game_factory = GameBase
            mode_label = _("Classic")
        elif normalized_mode in {"regions", "region", "arena", "pubg"}:
            game_factory = RegionGame
            mode_label = _("Regions")
        elif normalized_mode in {"region-ideas", "regionideas", "ideas"}:
            game_factory = RegionIdeasGame
            mode_label = _("Region-Ideas")
        elif normalized_mode in gm_tokens:
            game_factory = RegionGMGame
            mode_label = _("Regions-GM")
            gm_mode = True
            if forced_gm_id is not None:
                forced_gm_label = (
                    ctx.guild.get_member(forced_gm_id).mention
                    if ctx.guild and ctx.guild.get_member(forced_gm_id)
                    else f"<@{forced_gm_id}>"
                )
                mode_note = _(
                    "{user} will be the Game Master if they join. They will not fight as a tribute."
                ).format(user=forced_gm_label)
            else:
                mode_note = _(
                    "One joined player will be chosen at random as Game Master and will not fight as a tribute."
                )
        else:
            return await ctx.send(
                _(
                    "Unknown mode `{mode}`. Valid modes: `classic`, `regions`, `region-ideas`, `regions-gm`."
                ).format(mode=raw_mode or "")
            )

        self.games[ctx.channel.id] = "forming"

        is_mass_game = (
            ctx.channel.id == self.bot.config.game.official_tournament_channel_id
        )
        join_timeout = 60 * 10 if is_mass_game else 60 * 2
        view = JoinView(
            Button(
                style=ButtonStyle.primary,
                label="Join the Hunger Games!",
                emoji="\U0001f958",
            ),
            message=_("You joined the Hunger Games."),
            timeout=join_timeout,
        )
        if not is_mass_game:
            view.joined.add(ctx.author)

        lobby_message = await ctx.send(
            self._build_join_lobby_text(
                author_mention=ctx.author.mention,
                mode_label=mode_label,
                seconds_left=join_timeout,
                joined=view.joined,
                is_mass_game=is_mass_game,
                extra_note=mode_note,
            ),
            view=view,
        )
        await self._run_join_countdown(
            message=lobby_message,
            view=view,
            author_mention=ctx.author.mention,
            mode_label=mode_label,
            duration_seconds=join_timeout,
            is_mass_game=is_mass_game,
            extra_note=mode_note,
        )
        players = list(view.joined)

        if gm_mode and len(players) < 4:
            del self.games[ctx.channel.id]
            await self.bot.reset_cooldown(ctx)
            return await ctx.send(
                _(
                    "Regions-GM needs at least 4 joined players so one can become Game Master and at least three tributes remain."
                )
            )

        if len(players) < 2:
            del self.games[ctx.channel.id]
            await self.bot.reset_cooldown(ctx)
            return await ctx.send(_("Not enough players joined..."))

        if gm_mode:
            if forced_gm_id is not None:
                gm_player = next(
                    (player for player in players if player.id == forced_gm_id),
                    None,
                )
                if gm_player is None:
                    del self.games[ctx.channel.id]
                    await self.bot.reset_cooldown(ctx)
                    return await ctx.send(
                        _(
                            "The chosen GM `{user_id}` did not join the lobby."
                        ).format(user_id=forced_gm_id)
                    )
            else:
                gm_player = random.choice(players)
            players.remove(gm_player)
            game = game_factory(ctx, players=players, gm_player=gm_player)
        else:
            game = game_factory(ctx, players=players)
        self.games[ctx.channel.id] = game
        try:
            await game.main()
        except Exception as e:
            await ctx.send(
                _("An error happened during the hungergame. Please try again!")
            )
            raise e
        finally:
            try:
                del self.games[ctx.channel.id]
            except KeyError:  # got stuck in between
                pass


async def setup(bot):
    await bot.add_cog(HungerGames(bot))

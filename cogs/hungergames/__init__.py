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
                title=_("Choose your action"),
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
    ) -> bool:
        if victim not in self.players or victim in killed_this_round:
            return False
        killed_this_round.add(victim)
        if killer is not None and killer.id in self.kills:
            self.kills[killer.id] += 1
        return True

    def _check_trap_trigger(
        self,
        attacker: discord.Member,
        defender: discord.Member,
        killed_this_round: set,
    ) -> bool:
        trap_count = self.traps.get(defender.id, 0)
        if trap_count <= 0:
            return False
        trigger_chance = min(70, 12 + trap_count * 14)
        if random.randint(1, 100) > trigger_chance:
            return False
        self.traps[defender.id] = max(0, trap_count - 1)
        self._mark_kill(defender, attacker, killed_this_round)
        return True

    def _resolve_action(
        self,
        actor: discord.Member,
        action: dict,
        killed_this_round: set,
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
                self._mark_kill(actor, target, killed_this_round)
                self.gear_score[actor.id] = min(10, self.gear_score[actor.id] + 1)
                return _("betrays **{ally}** and takes their loot.").format(
                    ally=target.display_name
                )
            if random.randint(1, 100) <= 50:
                self._mark_kill(target, actor, killed_this_round)
                return _("tries to betray **{ally}**, but gets executed first.").format(
                    ally=target.display_name
                )
            return _("tries to betray **{ally}**, but the moment passes.").format(
                ally=target.display_name
            )

        if self._check_trap_trigger(actor, target, killed_this_round):
            return _("charges **{target}** but triggers their trap and dies.").format(
                target=target.display_name
            )

        if kind == "hunt":
            chance = 35 + self.gear_score[actor.id] * 8 + min(18, self.round * 2)
            if target.id in self.hidden_ids:
                chance -= 18
            chance = max(12, min(90, chance))
            if random.randint(1, 100) <= chance:
                self._mark_kill(actor, target, killed_this_round)
                return _("hunts down **{target}** cleanly.").format(
                    target=target.display_name
                )
            counter_chance = min(60, 18 + self.gear_score[target.id] * 5)
            if random.randint(1, 100) <= counter_chance:
                self._mark_kill(target, actor, killed_this_round)
                return _("misses **{target}** and gets counter-killed.").format(
                    target=target.display_name
                )
            return _("tracks **{target}** but loses them in the terrain.").format(
                target=target.display_name
            )

        if kind == "rush":
            chance = 40 + self.gear_score[actor.id] * 6 + min(12, self.round)
            if target.id in self.hidden_ids:
                chance -= 14
            chance = max(10, min(85, chance))
            if random.randint(1, 100) <= chance:
                self._mark_kill(actor, target, killed_this_round)
                if random.randint(1, 100) <= 35:
                    self._mark_kill(None, actor, killed_this_round)
                    return _("rushes **{target}**, kills them, then bleeds out.").format(
                        target=target.display_name
                    )
                return _("rushes **{target}** and wins the brawl.").format(
                    target=target.display_name
                )
            if random.randint(1, 100) <= 40:
                self._mark_kill(target, actor, killed_this_round)
                return _("rushes **{target}** and gets dropped instantly.").format(
                    target=target.display_name
                )
            return _("rushes **{target}** but neither can finish it.").format(
                target=target.display_name
            )

        return _("does something chaotic but pointless.")

    async def _resolve_arena_event(self, killed_this_round: set, round_lines: list[str]) -> None:
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
            self._mark_kill(None, victim, killed_this_round)
            round_lines.append(
                _("🐺 Mutts swarm **{victim}** in the dark.").format(
                    victim=victim.display_name
                )
            )
            return

        if roll <= 82:
            vulnerable = [p for p in survivors if self.gear_score[p.id] <= 1]
            if vulnerable and random.randint(1, 100) <= 55:
                victim = random.choice(vulnerable)
                self._mark_kill(None, victim, killed_this_round)
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
            self._mark_kill(winner, loser, killed_this_round)
            round_lines.append(
                _("⚔️ Arena event: **{winner}** wins a sudden duel against **{loser}**.").format(
                    winner=winner.display_name,
                    loser=loser.display_name,
                )
            )

    def _force_showdown(self, killed_this_round: set, round_lines: list[str]) -> None:
        survivors = [p for p in self.players if p not in killed_this_round]
        if len(survivors) < 2:
            return
        left, right = random.sample(survivors, 2)
        left_roll = self.gear_score[left.id] + random.randint(1, 4)
        right_roll = self.gear_score[right.id] + random.randint(1, 4)
        winner, loser = (left, right) if left_roll >= right_roll else (right, left)
        self._mark_kill(winner, loser, killed_this_round)
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

    async def _send_round_report(self, round_lines: list[str], killed_this_round: set) -> None:
        killed_names = (
            nice_join([f"**{p.display_name}**" for p in killed_this_round])
            if killed_this_round
            else _("Nobody")
        )
        lock_state = (
            _("active until round {round}").format(round=self.ALLIANCE_LOCK_ROUNDS + 1)
            if self.round <= self.ALLIANCE_LOCK_ROUNDS
            else _("broken")
        )
        lines = [f"• {line}" for line in round_lines]
        lines.append(_("☠️ Eliminated: {killed}").format(killed=killed_names))
        lines.append(_("🧍 Alive now: **{alive}**").format(alive=len(self.players)))
        lines.append(_("🤝 Alliance lock: **{state}**").format(state=lock_state))
        lines.append(_("🏆 Kill leaders: {leaders}").format(leaders=self._top_killers_text()))

        pages = self._split_report(lines)
        total_pages = len(pages)
        for idx, page in enumerate(pages, start=1):
            title = _("Hunger Games - Round {round}").format(round=self.round)
            if total_pages > 1:
                title = f"{title} ({idx}/{total_pages})"
            embed = discord.Embed(
                title=title,
                description=page,
                color=discord.Color.orange(),
            )
            await self.ctx.send(embed=embed)

    async def get_inputs(self):
        status = await self.ctx.send(
            _("🔥 **Round {round}** begins...").format(round=self.round),
            delete_after=45,
        )
        self.hidden_ids = set()
        killed_this_round: set[discord.Member] = set()
        round_lines: list[str] = []

        turn_order = self.players.copy()
        random.shuffle(turn_order)
        for actor in turn_order:
            if actor not in self.players or actor in killed_this_round:
                continue
            choices = self._build_action_choices(actor, killed_this_round)
            if not choices:
                continue
            action = await self._choose_action(actor, choices)
            summary = self._resolve_action(actor, action, killed_this_round)
            round_lines.append(f"**{actor.display_name}** {summary}")

        await self._resolve_arena_event(killed_this_round, round_lines)
        if (
            not killed_this_round
            and len(self.players) > 2
            and self.round >= 2
            and not self._single_team_left(killed_this_round)
        ):
            self._force_showdown(killed_this_round, round_lines)

        for dead in list(killed_this_round):
            try:
                self.players.remove(dead)
            except ValueError:
                pass

        try:
            await status.delete()
        except discord.NotFound:
            pass
        await self._send_round_report(round_lines, killed_this_round)
        self.round += 1

    async def send_cast(self):
        cast = self.players.copy()
        random.shuffle(cast)
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
            lines.append(f"**Team #{idx}:** {mentions}")

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
                        "Alliances are protected until round {round}. Betrayals unlock after that."
                    ).format(round=self.ALLIANCE_LOCK_ROUNDS)
                )
            await self.ctx.send(embed=embed)

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
                description=_("Team #{team} wins together!").format(team=team_id),
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


class HungerGames(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.games = {}


    @commands.command(aliases=["hg"], brief=_("Play the hunger games"))
    @locale_doc
    async def hungergames(self, ctx):
        _(
            """Starts the hunger games

            Players will be able to join via the :shallow_pan_of_food: emoji.
            Teams are formed at the start and alliance protection lasts for a few rounds before betrayals unlock.
            The game mixes random outcomes with player-selected actions.
            Players may get direct messages to choose actions; if no action is chosen, the bot picks one.

            Not every player will receive a direct action prompt every round."""
        )
        if self.games.get(ctx.channel.id):
            return await ctx.send(_("There is already a game in here!"))

        self.games[ctx.channel.id] = "forming"

        if ctx.channel.id == self.bot.config.game.official_tournament_channel_id:
            view = JoinView(
                Button(
                    style=ButtonStyle.primary,
                    label="Join the Hunger Games!",
                    emoji="\U0001f958",
                ),
                message=_("You joined the Hunger Games."),
                timeout=60 * 10,
            )
            await ctx.send(
                f"{ctx.author.mention} started a mass-game of Hunger Games!",
                view=view,
            )
            await asyncio.sleep(60 * 10)
            view.stop()
            players = list(view.joined)
        else:
            view = JoinView(
                Button(
                    style=ButtonStyle.primary,
                    label="Join the Hunger Games!",
                    emoji="\U0001f958",
                ),
                message=_("You joined the Hunger Games."),
                timeout=60 * 2,
            )
            view.joined.add(ctx.author)
            text = _("{author} started a game of Hunger Games!")
            await ctx.send(text.format(author=ctx.author.mention), view=view)
            await asyncio.sleep(60 * 2)
            view.stop()
            players = list(view.joined)

        if len(players) < 2:
            del self.games[ctx.channel.id]
            await self.bot.reset_cooldown(ctx)
            return await ctx.send(_("Not enough players joined..."))

        game = GameBase(ctx, players=players)
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

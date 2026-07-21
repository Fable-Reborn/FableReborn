from __future__ import annotations

import math
import random
from collections import Counter

from .models import (
    ActionChoice,
    ActionKind,
    BossAttack,
    BossPhaseResult,
    BossState,
    GameOutcome,
    InvestigationReading,
    PlayerState,
    RoundResult,
    VoteResult,
)
from .settings import RaidSettings


class TraitorRaidEngine:
    """Pure state machine for one Traitor Raid.

    Discord interactions, timers and prose live in the cog. This object owns only
    authoritative game state and rule resolution, which keeps hidden information
    out of public presentation code and makes the mode straightforward to test.
    """

    def __init__(
        self,
        settings: RaidSettings,
        players: list[PlayerState],
        traitor_id: int,
        *,
        rng=None,
    ):
        if traitor_id not in {player.user_id for player in players}:
            raise ValueError("The traitor must be one of the raid players.")
        self.settings = settings
        self.players = {player.user_id: player for player in players}
        self.initial_player_count = len(players)
        self.traitor_id = traitor_id
        self.boss = BossState(
            name=settings.boss_name,
            hp=float(settings.boss_hp),
            max_hp=float(settings.boss_hp),
            damage=float(settings.boss_attack),
            armor=float(settings.boss_defense),
        )
        self.rng = rng or random.Random()
        self.round_no = 0
        self.actions: dict[int, ActionChoice] = {}
        self.frame_used = False
        self.traitor_revealed = False
        self.traitor_fall_applied = False
        self.telegraphed_target_ids: list[int] = []
        self.outcome: GameOutcome | None = None

    @property
    def traitor(self) -> PlayerState:
        return self.players[self.traitor_id]

    def living_players(self) -> list[PlayerState]:
        return [player for player in self.players.values() if player.alive]

    def living_innocents(self) -> list[PlayerState]:
        return [
            player
            for player in self.living_players()
            if player.user_id != self.traitor_id
        ]

    def begin_round(self) -> int:
        if self.outcome:
            raise RuntimeError("The game is already over.")
        self.round_no += 1
        self.actions.clear()
        for player in self.players.values():
            player.guarded = False
        living = self.living_players()
        self.telegraphed_target_ids = [
            player.user_id
            for player in self.rng.sample(
                living,
                k=min(self.settings.boss_targets, len(living)),
            )
        ]
        return self.round_no

    def submit_action(self, user_id: int, choice: ActionChoice) -> None:
        player = self.players.get(user_id)
        if not player or not player.alive:
            raise ValueError("Only living raiders may act.")
        if user_id in self.actions:
            raise ValueError("Your action is already locked for this round.")
        if choice.kind in {ActionKind.SABOTAGE, ActionKind.FRAME} and user_id != self.traitor_id:
            raise ValueError("That action belongs to the Traitor.")
        if choice.kind == ActionKind.FRAME and self.frame_used:
            raise ValueError("Frame has already been used this game.")
        if choice.kind in {ActionKind.INVESTIGATE, ActionKind.FRAME}:
            target = self.players.get(choice.target_id)
            if choice.kind == ActionKind.FRAME and choice.target_id == self.traitor_id:
                raise ValueError("The Traitor cannot frame themselves.")
            if not target or not target.alive or target.user_id == user_id:
                raise ValueError("Choose another living raider as the target.")
        self.actions[user_id] = choice

    def _base_contribution(self, player: PlayerState) -> float:
        return max(1.0, player.damage - self.boss.armor)

    def _public_action_name(self, kind: ActionKind) -> str:
        if kind == ActionKind.SABOTAGE:
            return "Assault"
        if kind == ActionKind.FRAME:
            return "Investigate"
        return kind.value.title()

    def _investigate(
        self,
        investigator_id: int,
        target_id: int,
        framed_target_id: int | None = None,
    ) -> InvestigationReading:
        actually_corrupt = target_id == self.traitor_id
        if target_id == framed_target_id:
            appears_corrupt = True
        else:
            accurate = self.rng.random() * 100 < self.settings.investigate_accuracy_pct
            appears_corrupt = actually_corrupt if accurate else not actually_corrupt
        return InvestigationReading(
            investigator_id=investigator_id,
            target_id=target_id,
            appears_corrupt=appears_corrupt,
        )

    def _evidence_candidates(self, subject_id: int) -> list[int]:
        living_ids = [player.user_id for player in self.living_players()]
        if subject_id not in living_ids:
            return []
        others = [user_id for user_id in living_ids if user_id != subject_id]
        count = min(self.settings.clue_suspects, len(living_ids))
        chosen = [subject_id]
        if count > 1 and others:
            chosen.extend(self.rng.sample(others, k=min(count - 1, len(others))))
        self.rng.shuffle(chosen)
        return chosen

    def resolve_player_phase(self) -> RoundResult:
        result = RoundResult()
        living = sorted(self.living_players(), key=lambda player: player.user_id)
        secret_subject = None
        evidence_kind = None
        rally_actors = []
        framed_target_id = next(
            (
                int(choice.target_id)
                for choice in self.actions.values()
                if choice.kind == ActionKind.FRAME and choice.target_id is not None
            ),
            None,
        )

        for player in living:
            choice = self.actions.get(player.user_id)
            if choice is None:
                choice = ActionChoice(ActionKind.GUARD)
                self.actions[player.user_id] = choice
                result.defaulted_ids.append(player.user_id)

            public_name = self._public_action_name(choice.kind)
            result.action_counts[public_name] = result.action_counts.get(public_name, 0) + 1
            base = self._base_contribution(player)

            if choice.kind == ActionKind.ASSAULT:
                result.party_damage += base
            elif choice.kind == ActionKind.GUARD:
                player.guarded = True
                result.party_damage += base * self.settings.guard_damage_pct / 100
            elif choice.kind == ActionKind.INVESTIGATE:
                result.party_damage += base * self.settings.investigate_damage_pct / 100
                result.investigations.append(
                    self._investigate(
                        player.user_id,
                        int(choice.target_id),
                        framed_target_id,
                    )
                )
            elif choice.kind == ActionKind.RALLY:
                result.party_damage += base * self.settings.rally_damage_pct / 100
                rally_actors.append(player)
            elif choice.kind == ActionKind.SABOTAGE:
                result.boss_healing += base * self.settings.traitor_heal_pct / 100
                secret_subject = self.traitor_id
                evidence_kind = "corruption"
            elif choice.kind == ActionKind.FRAME:
                result.boss_healing += base * self.settings.traitor_heal_pct / 200
                self.frame_used = True
                secret_subject = int(choice.target_id)
                evidence_kind = "tampered"

        for _actor in rally_actors:
            candidates = self.living_players()
            if not candidates:
                break
            target = min(candidates, key=lambda player: (player.hp_ratio, player.user_id))
            heal = target.max_hp * self.settings.rally_heal_pct / 100
            actual = min(max(0.0, target.max_hp - target.hp), heal)
            target.hp += actual
            result.rally_healing += actual

        self.boss.hp = max(
            0.0,
            min(
                self.boss.max_hp,
                self.boss.hp - result.party_damage + result.boss_healing,
            ),
        )
        if secret_subject is not None:
            result.evidence_ids = self._evidence_candidates(secret_subject)
            result.evidence_kind = evidence_kind
        return result

    def _apply_traitor_fall(self) -> float:
        if self.traitor_fall_applied:
            return 0.0
        self.traitor_fall_applied = True
        self.traitor_revealed = True
        damage = self.boss.max_hp * self.settings.traitor_death_damage_pct / 100
        actual = min(self.boss.hp, damage)
        self.boss.hp = max(0.0, self.boss.hp - damage)
        return actual

    def resolve_boss_phase(self) -> BossPhaseResult:
        result = BossPhaseResult()
        living = self.living_players()
        if not self.boss.alive or not living:
            return result

        targets = [
            self.players[user_id]
            for user_id in self.telegraphed_target_ids
            if user_id in self.players and self.players[user_id].alive
        ]
        if not targets:
            targets = self.rng.sample(
                living,
                k=min(self.settings.boss_targets, len(living)),
            )
        for target in targets:
            damage = max(1.0, self.boss.damage - target.armor)
            if target.guarded:
                damage *= 1 - self.settings.guard_reduction_pct / 100
            actual = min(target.hp, damage)
            target.hp = max(0.0, target.hp - damage)
            killed = target.hp <= 0
            result.attacks.append(
                BossAttack(
                    target_id=target.user_id,
                    damage=actual,
                    guarded=target.guarded,
                    killed=killed,
                )
            )

        newly_dead = [
            player
            for player in self.players.values()
            if player.hp <= 0 and not player.exiled and not player.death_effect_applied
        ]
        for player in newly_dead:
            player.death_effect_applied = True
            if player.user_id == self.traitor_id:
                result.traitor_fell = True
                result.traitor_burst_damage = self._apply_traitor_fall()
            else:
                result.innocent_deaths.append(player.user_id)

        if result.innocent_deaths:
            multiplier = 1 + self.settings.innocent_death_enrage_pct / 100
            self.boss.damage *= multiplier ** len(result.innocent_deaths)
        return result

    def resolve_vote(self, ballots: dict[int, int | None]) -> VoteResult:
        living_ids = {player.user_id for player in self.living_players()}
        valid = {
            voter_id: target_id
            for voter_id, target_id in ballots.items()
            if voter_id in living_ids and (target_id is None or target_id in living_ids)
        }
        abstentions = sum(target_id is None for target_id in valid.values())
        counts = Counter(target_id for target_id in valid.values() if target_id is not None)
        if not counts:
            return VoteResult(None, {}, abstentions, valid, "No exile received enough support.")

        top_count = max(counts.values())
        leaders = [target_id for target_id, count in counts.items() if count == top_count]
        minimum_support = 2 if len(living_ids) >= 3 else 1
        if len(leaders) != 1:
            reason = "The vote tied, so nobody was exiled."
            exile_id = None
        elif top_count < minimum_support:
            reason = f"An exile requires at least {minimum_support} supporting votes."
            exile_id = None
        elif abstentions >= top_count:
            reason = "Abstain matched or beat the leading accusation."
            exile_id = None
        else:
            exile_id = leaders[0]
            reason = "The accusation reached a decisive plurality."
        return VoteResult(exile_id, dict(counts), abstentions, valid, reason)

    def apply_exile(self, user_id: int) -> tuple[bool, float]:
        player = self.players.get(user_id)
        if not player or not player.alive:
            raise ValueError("That raider cannot be exiled.")
        player.exiled = True
        player.hp = 0.0
        player.death_effect_applied = True
        if user_id == self.traitor_id:
            return True, self._apply_traitor_fall()
        self.boss.damage *= 1 + self.settings.wrong_exile_enrage_pct / 100
        return False, 0.0

    def should_vote(self) -> bool:
        return bool(
            not self.outcome
            and self.traitor.alive
            and self.round_no % self.settings.vote_every == 0
            and len(self.living_players()) >= 3
        )

    def determine_outcome(self, *, round_complete: bool = False) -> GameOutcome | None:
        if self.outcome:
            return self.outcome
        if not self.boss.alive:
            self.outcome = GameOutcome("innocents", "boss_defeated")
        elif not self.living_innocents():
            self.outcome = GameOutcome("traitor", "all_innocents_fallen")
        elif (
            self.initial_player_count > 2
            and self.traitor.alive
            and len(self.living_innocents()) <= 1
        ):
            self.outcome = GameOutcome("traitor", "traitor_reached_parity")
        elif round_complete and self.round_no >= self.settings.max_rounds:
            self.outcome = GameOutcome("traitor", "round_limit")
        return self.outcome


def estimated_round_damage(players: list[PlayerState], boss_defense: float) -> float:
    return sum(max(1.0, player.damage - boss_defense) for player in players)


def suggested_boss_hp(players: list[PlayerState], boss_defense: float, rounds: int = 8) -> int:
    estimate = estimated_round_damage(players, boss_defense)
    return max(10_000, int(math.ceil(estimate * max(1, rounds) * 0.70 / 1_000) * 1_000))

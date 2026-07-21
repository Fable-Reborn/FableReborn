from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class ActionKind(str, Enum):
    ASSAULT = "assault"
    GUARD = "guard"
    INVESTIGATE = "investigate"
    RALLY = "rally"
    SABOTAGE = "sabotage"
    FRAME = "frame"


@dataclass
class PlayerState:
    user_id: int
    name: str
    hp: float
    max_hp: float
    damage: float
    armor: float
    exiled: bool = False
    guarded: bool = False
    death_effect_applied: bool = False

    @property
    def alive(self) -> bool:
        return self.hp > 0 and not self.exiled

    @property
    def hp_ratio(self) -> float:
        if self.max_hp <= 0:
            return 0.0
        return max(0.0, min(1.0, self.hp / self.max_hp))


@dataclass
class BossState:
    name: str
    hp: float
    max_hp: float
    damage: float
    armor: float

    @property
    def alive(self) -> bool:
        return self.hp > 0


@dataclass(frozen=True)
class ActionChoice:
    kind: ActionKind
    target_id: int | None = None


@dataclass(frozen=True)
class InvestigationReading:
    investigator_id: int
    target_id: int
    appears_corrupt: bool


@dataclass
class RoundResult:
    party_damage: float = 0.0
    boss_healing: float = 0.0
    rally_healing: float = 0.0
    action_counts: dict[str, int] = field(default_factory=dict)
    evidence_ids: list[int] = field(default_factory=list)
    evidence_kind: str | None = None
    defaulted_ids: list[int] = field(default_factory=list)
    investigations: list[InvestigationReading] = field(default_factory=list)


@dataclass(frozen=True)
class BossAttack:
    target_id: int
    damage: float
    guarded: bool
    killed: bool


@dataclass
class BossPhaseResult:
    attacks: list[BossAttack] = field(default_factory=list)
    innocent_deaths: list[int] = field(default_factory=list)
    traitor_fell: bool = False
    traitor_burst_damage: float = 0.0


@dataclass
class VoteResult:
    exile_id: int | None
    counts: dict[int, int]
    abstentions: int
    ballots: dict[int, int | None]
    reason: str


@dataclass(frozen=True)
class GameOutcome:
    winner: str
    reason: str


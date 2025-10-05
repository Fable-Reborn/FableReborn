"""Single-player Werewolf engine (remastered)
------------------------------------------------
A strategic deduction game against intelligent AI opponents with
sophisticated social dynamics, role questioning, and deductive reasoning.
"""
from __future__ import annotations

import asyncio
import datetime
import random
import string
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Dict, List, Optional, Set, Tuple, Union, Counter

import discord
from babel.lists import format_list
from discord.ext import commands

from classes.context import Context
from utils.werewolf import Role, Side, Player  # reuse enums for naming / goal texts

# ---------------------------------------------------------------------------
# Helper –   dummy discord.Member-like object for AI players
# ---------------------------------------------------------------------------

_NAMES = [
    "Ava", "Ben", "Cara", "Dylan", "Eva", "Finn", "Grace", "Hugo",
    "Iris", "Jack", "Kara", "Liam", "Maya", "Noah", "Olive", "Paul",
    "Quinn", "Rosa", "Sam", "Tara", "Uma", "Vince", "Wade", "Xena",
    "Yara", "Zane",
]

# AI personalities with distinct play styles
_PERSONALITIES = [
    {
        "name": "Analytical",
        "traits": ["logical", "methodical", "detail-oriented"],
        "behavior": {
            "question_chance": 0.7,        # More likely to ask about roles
            "trust_evidence": 0.8,         # Highly values evidence
            "reveal_threshold": 0.7,       # Needs good reason to reveal
            "accusation_style": "evidence-based",
            "defensive_style": "logical"
        }
    },
    {
        "name": "Aggressive",
        "traits": ["bold", "direct", "confrontational"],
        "behavior": {
            "question_chance": 0.8,        # Very likely to question others
            "trust_evidence": 0.5,         # Moderately values evidence
            "reveal_threshold": 0.5,       # More willing to make claims
            "accusation_style": "direct",
            "defensive_style": "counter-accuse"
        }
    },
    {
        "name": "Cautious",
        "traits": ["hesitant", "observant", "risk-averse"],
        "behavior": {
            "question_chance": 0.4,        # Less likely to ask directly
            "trust_evidence": 0.7,         # Values evidence
            "reveal_threshold": 0.9,       # Very reluctant to reveal
            "accusation_style": "tentative",
            "defensive_style": "evasive"
        }
    },
    {
        "name": "Emotional",
        "traits": ["intuitive", "reactive", "passionate"],
        "behavior": {
            "question_chance": 0.6,        # Average questioning
            "trust_evidence": 0.3,         # Values gut feelings more
            "reveal_threshold": 0.4,       # Quick to reveal
            "accusation_style": "passionate",
            "defensive_style": "emotional"
        }
    },
    {
        "name": "Strategic",
        "traits": ["calculating", "manipulative", "patient"],
        "behavior": {
            "question_chance": 0.5,        # Selective questioning
            "trust_evidence": 0.6,         # Considers evidence carefully
            "reveal_threshold": 0.75,      # Strategic about revealing
            "accusation_style": "calculated",
            "defensive_style": "deflect"
        }
    }
]

class ActionType(Enum):
    """Types of actions that can influence AI reasoning."""
    ROLE_CLAIM = auto()          # Player claimed a role
    ROLE_QUESTION = auto()       # Player asked about someone's role
    ACCUSATION = auto()          # Player accused someone
    DEFENSE = auto()             # Player defended someone
    SUSPICION = auto()           # Player expressed suspicion
    VOTE = auto()                # Player voted against someone
    INFORMATION = auto()         # Player revealed information
    CONTRADICTION = auto()       # Player contradicted themselves/evidence
    COORDINATION = auto()        # Players seemed to coordinate
    ROLE_REFUSAL = auto()        # Player refused to claim a role
    SEER_RESULT = auto()         # Seer revealed inspection result
    AGGRESSIVE_QUESTIONING = auto() # Player interrogated someone aggressively
    QUIET_BEHAVIOR = auto()      # Player being unusually quiet
    LIE_DETECTED = auto()        # Player caught in a lie
    NIGHT_DEATH = auto()         # Player died at night

class Evidence:
    """Tracks evidence about a player that AI can use for reasoning."""
    def __init__(self, player_id: int, day: int, action: ActionType,
                 target_id: Optional[int] = None, details: Optional[Dict] = None):
        self.player_id = player_id
        self.day = day
        self.action = action
        self.target_id = target_id
        self.details = details or {}
        self.timestamp = datetime.datetime.now()

    @property
    def age(self) -> float:
        """How old this evidence is in seconds."""
        return (datetime.datetime.now() - self.timestamp).total_seconds()

class DummyAvatar:
    """Mimic `discord.Asset` enough for `avatar.url`."""
    @property
    def url(self):
        return "https://via.placeholder.com/128?text=AI"

class AIMember:
    """Enhanced AI Member with personality traits and more humanlike behavior."""
    __slots__ = ("id", "name", "display_name", "mention", "display_avatar", "personality")

    def __init__(self, uid: int, name: str, personality: Dict):
        self.id: int = uid
        self.name = name
        self.display_name: str = name
        self.mention: str = f"**{name}**"
        self.display_avatar = DummyAvatar()
        self.personality = personality

    # Discord API stubs
    async def send(self, *_a, **_kw):
        return None

    async def create_dm(self):
        return None

    @property
    def dm_channel(self):
        return None

    def __str__(self):
        return self.name

@dataclass
class RoleClaim:
    """Tracks a player's role claim and its credibility."""
    player_id: int
    claimed_role: Role
    day_claimed: int
    supporting_evidence: List[Evidence] = field(default_factory=list)
    contradicting_evidence: List[Evidence] = field(default_factory=list)

    @property
    def credibility(self) -> float:
        """Calculate claim credibility based on evidence (0-1)."""
        base = 0.5  # Neutral starting point
        support = min(0.4, len(self.supporting_evidence) * 0.1)
        contradict = min(0.4, len(self.contradicting_evidence) * 0.15)
        return min(1.0, max(0.0, base + support - contradict))

@dataclass
class PlayerOpinion:
    """Represents one player's opinion of another player."""
    target_id: int
    suspicion: float = 0.5  # 0 = completely trusted, 1 = 100% suspicious
    evidence: List[Evidence] = field(default_factory=list)
    interactions: List[Dict] = field(default_factory=list)

    def update_suspicion(self, evidence_weight: float = 1.0):
        """Update suspicion level based on collected evidence."""
        # Base suspicion stays in mid-range without evidence
        if not self.evidence:
            return

        # Track influence from different evidence types
        evidence_influence = {
            ActionType.ROLE_CLAIM: 0,
            ActionType.ACCUSATION: 0,
            ActionType.DEFENSE: 0,
            ActionType.CONTRADICTION: 0,
            ActionType.SEER_RESULT: 0,
            ActionType.ROLE_REFUSAL: 0,
            ActionType.LIE_DETECTED: 0
        }

        # Analyze evidence collection
        for e in self.evidence:
            # Accusations increase suspicion
            if e.action == ActionType.ACCUSATION:
                evidence_influence[e.action] += 0.1

            # Defenses decrease suspicion
            elif e.action == ActionType.DEFENSE:
                evidence_influence[e.action] -= 0.1

            # Role claims affect suspicion based on credibility
            elif e.action == ActionType.ROLE_CLAIM:
                claimed_role = e.details.get('role')

                if claimed_role == Role.WEREWOLF:
                    # Claiming to be werewolf is extremely suspicious!
                    evidence_influence[e.action] += 0.8
                elif claimed_role == Role.SEER:
                    # Claiming Seer is neutral at first
                    evidence_influence[e.action] += 0.0
                else:
                    # Claiming villager slightly decreases suspicion
                    evidence_influence[e.action] -= 0.05

            # Refusing to claim a role is suspicious
            elif e.action == ActionType.ROLE_REFUSAL:
                evidence_influence[e.action] += 0.15

            # Contradictions are very suspicious
            elif e.action == ActionType.CONTRADICTION:
                evidence_influence[e.action] += 0.3

            # Seer results are highly influential
            elif e.action == ActionType.SEER_RESULT:
                result_role = e.details.get('revealed_role')
                if result_role == Role.WEREWOLF:
                    evidence_influence[e.action] += 0.6
                else:
                    evidence_influence[e.action] -= 0.4

            # Being caught in a lie is extremely suspicious
            elif e.action == ActionType.LIE_DETECTED:
                evidence_influence[e.action] += 0.7

        # Calculate net influence from all evidence types
        net_influence = sum(evidence_influence.values()) * evidence_weight

        # Update suspicion, keeping within 0-1 range
        self.suspicion = max(0.0, min(1.0, self.suspicion + net_influence))

@dataclass
class SPPlayer:
    """An enhanced player with sophisticated AI behavior and social dynamics."""

    user: Union[discord.Member, AIMember]
    role: Role
    is_human: bool

    # Game state
    alive: bool = True
    day_died: Optional[int] = None

    # Social state
    role_claims: List[RoleClaim] = field(default_factory=list)

    # AI reasoning data
    opinions: Dict[int, PlayerOpinion] = field(default_factory=dict)  # target_id -> opinion
    evidence_collected: List[Evidence] = field(default_factory=list)
    questions_asked: Dict[int, List[int]] = field(default_factory=dict)  # day -> target_ids
    questions_received: Dict[int, List[int]] = field(default_factory=dict)  # day -> asker_ids

    # Role-specific state
    seer_inspections: List[Tuple[int, Role]] = field(default_factory=list)  # list of (inspected_id, role)
    wolf_votes: List[int] = field(default_factory=list)  # IDs of players voted to kill

    # Game knowledge
    questioned_about_role: bool = False  # Directly asked about role
    claimed_innocence: bool = False  # Claimed to be on village team
    last_statement: Optional[str] = None  # Last thing this player said

    # Private AI state
    _forced_claim_day: Optional[int] = None  # Day the AI was forced to claim a role
    _strategy_state: Dict[str, Any] = field(default_factory=dict)  # For tracking AI strategy

    def __post_init__(self):
        """Initialize player opinion maps."""
        # Real Seers get a slight starting credibility boost
        if self.role == Role.SEER and not self.is_human:
            # They're more likely to claim role under pressure
            self._strategy_state['reveal_threshold'] = 0.6

    def __hash__(self):
        return hash(self.user.id)

    def __eq__(self, other):
        if not isinstance(other, SPPlayer):
            return False
        return self.user.id == other.user.id

    @property
    def role_name(self) -> str:
        """Localized role name."""
        return self.role.name.replace("_", " ").title()

    @property
    def side(self) -> Side:
        """Get player's team side."""
        return Side.WOLVES if self.role == Role.WEREWOLF else Side.VILLAGERS

    @property
    def personality(self) -> Dict:
        """Get AI personality data or default for human."""
        if hasattr(self.user, 'personality'):
            return self.user.personality
        # Default moderate personality for humans or fallback
        return _PERSONALITIES[2]  # Cautious personality as default

    @property
    def behavior(self) -> Dict:
        """Get AI behavior settings."""
        return self.personality.get('behavior', {})

    @property
    def claimed_role(self) -> Optional[Role]:
        """Get the most recent role claim, if any."""
        if not self.role_claims:
            return None
        # Sort by day claimed, get most recent
        claims = sorted(self.role_claims, key=lambda c: c.day_claimed, reverse=True)
        return claims[0].claimed_role

    @property
    def is_confirmed_seer(self) -> bool:
        """Whether this player is considered a confirmed Seer by others."""
        if self.role != Role.SEER:
            return False

        # A seer is confirmed if they've made at least one accurate inspection
        # that was proven correct (e.g., a player they identified as wolf was lynched)
        for claim in self.role_claims:
            if claim.claimed_role == Role.SEER and claim.credibility > 0.8:
                return True
        return False

    @property
    def average_suspicion(self) -> float:
        """Get the average suspicion level from all other players."""
        if not self.opinions:
            return 0.5  # Neutral if no opinions

        total = sum(op.suspicion for op in self.opinions.values())
        return total / len(self.opinions)

    def add_evidence(self, evidence: Evidence):
        """Add new evidence to the player's knowledge base."""
        self.evidence_collected.append(evidence)

        # If evidence is about another player, update opinion
        if evidence.target_id and evidence.target_id != self.user.id:
            if evidence.target_id not in self.opinions:
                self.opinions[evidence.target_id] = PlayerOpinion(evidence.target_id)

            # Add evidence to relevant opinion
            self.opinions[evidence.target_id].evidence.append(evidence)

            # Update suspicion based on new evidence
            evidence_weight = self.behavior.get('trust_evidence', 0.6)
            self.opinions[evidence.target_id].update_suspicion(evidence_weight)

    def process_role_claim(self, player_id: int, role: Role, day: int,
                           supporting_details: Optional[Dict] = None):
        """Process a role claim made by another player."""
        # Record the claim
        exists = False
        for claim in self.role_claims:
            if claim.player_id == player_id:
                exists = True
                # If claiming a different role, add as contradiction
                if claim.claimed_role != role:
                    contradiction = Evidence(
                        player_id=player_id,
                        day=day,
                        action=ActionType.CONTRADICTION,
                        details={
                            'previous_role': claim.claimed_role,
                            'new_role': role
                        }
                    )
                    claim.contradicting_evidence.append(contradiction)
                    self.add_evidence(contradiction)
                break

        # Create new claim if needed
        if not exists:
            new_claim = RoleClaim(
                player_id=player_id,
                claimed_role=role,
                day_claimed=day
            )

            # Add initial supporting evidence if provided
            if supporting_details:
                support = Evidence(
                    player_id=player_id,
                    day=day,
                    action=ActionType.INFORMATION,
                    details=supporting_details
                )
                new_claim.supporting_evidence.append(support)

            self.role_claims.append(new_claim)

        # Create evidence about the claim
        claim_evidence = Evidence(
            player_id=player_id,
            day=day,
            action=ActionType.ROLE_CLAIM,
            details={'role': role}
        )
        self.add_evidence(claim_evidence)

    def most_suspicious(self, alive_players: List[SPPlayer], exclude_ids: Optional[List[int]] = None) -> Optional[SPPlayer]:
        """Get the most suspicious player according to this player's knowledge."""
        exclude = exclude_ids or []

        # Only consider alive players not in exclude list
        candidates = [p for p in alive_players if p.user.id != self.user.id
                     and p.user.id not in exclude and p.alive]

        if not candidates:
            return None

        # For wolves, don't consider fellow wolves
        if self.role == Role.WEREWOLF:
            candidates = [p for p in candidates if p.role != Role.WEREWOLF]

        if not candidates:
            return None

        # Sort by suspicion level
        candidates_with_suspicion = []
        for p in candidates:
            if p.user.id in self.opinions:
                candidates_with_suspicion.append((p, self.opinions[p.user.id].suspicion))
            else:
                candidates_with_suspicion.append((p, 0.5))  # Default if no opinion

        # Sort by suspicion (highest first)
        sorted_candidates = sorted(candidates_with_suspicion, key=lambda x: x[1], reverse=True)

        if sorted_candidates:
            return sorted_candidates[0][0]
        return candidates[0]  # Fallback

    def choose_target(self, alive_players: List[SPPlayer], rnd: random.Random) -> Optional[SPPlayer]:
        """Choose strategic target for night actions based on role and knowledge."""
        # Filter to alive players except self
        candidates = [p for p in alive_players if p.alive and p != self]

        if not candidates:
            return None

        # Role-specific strategies
        if self.role == Role.WEREWOLF:
            # Filter out fellow wolves
            candidates = [p for p in candidates if p.role != Role.WEREWOLF]
            if not candidates:
                return None

            # Prioritization system for wolf kills
            target_scores = []
            for p in candidates:
                score = 0

                # Known/claimed Seers are high priority
                if p.role == Role.SEER or any(c.claimed_role == Role.SEER for c in p.role_claims):
                    score += 30

                # Players confirmed as non-wolves by real Seers are also threats
                if any(i[0] == p.user.id and i[1] != Role.WEREWOLF
                       for i in self.seer_inspections):
                    score += 20

                # Low-suspicion players are good targets (they're trusted)
                if p.user.id in self.opinions:
                    suspicion = self.opinions[p.user.id].suspicion
                    # Invert suspicion - lower is higher priority
                    score += 20 * (1.0 - suspicion)

                # Vocal players who question a lot are threats
                if p.user.id in self._strategy_state.get('vocal_players', []):
                    score += 15

                # Add some randomness
                score += rnd.uniform(0, 10)

                target_scores.append((p, score))

            # Choose highest-scored target
            if target_scores:
                return max(target_scores, key=lambda x: x[1])[0]

            # Fallback to random
            return rnd.choice(candidates)

        elif self.role == Role.SEER:
            # Seer strategy: prioritize suspicious players and unknowns
            target_scores = []

            # Don't reinspect players
            inspected_ids = [i[0] for i in self.seer_inspections]
            new_candidates = [p for p in candidates if p.user.id not in inspected_ids]

            # If everyone's been inspected, allow reinspection
            inspect_pool = new_candidates if new_candidates else candidates

            # Score each potential target
            for p in inspect_pool:
                score = 0

                # Suspicious players are higher priority
                if p.user.id in self.opinions:
                    suspicion = self.opinions[p.user.id].suspicion
                    score += 25 * suspicion

                # Players who have claimed roles are interesting
                if p.claimed_role is not None:
                    score += 20

                # Players who are vocal are more suspicious
                if p.user.id in self._strategy_state.get('vocal_players', []):
                    score += 10

                # Add some randomness
                score += rnd.uniform(0, 15)

                target_scores.append((p, score))

            # Choose highest-scored target
            if target_scores:
                return max(target_scores, key=lambda x: x[1])[0]

            # Fallback to random
            return rnd.choice(candidates)

        # Default random choice for non-special roles
        return rnd.choice(candidates)

    def get_role_response(self, asker_id: int, day: int,
                         game_state: Dict, rnd: random.Random) -> Tuple[str, Dict]:
        """
        Generate a response when asked about role.

        Returns:
            Tuple of (response text, event data)
        """
        # Track being questioned
        self.questioned_about_role = True

        if day not in self.questions_received:
            self.questions_received[day] = []
        self.questions_received[day].append(asker_id)

        # Find the player who asked
        asker_name = "Someone"
        for p in game_state.get('players', []):
            if p.user.id == asker_id:
                asker_name = p.user.display_name
                break

        # Human players must decide for themselves what to claim
        if self.is_human:
            return f"I should respond to {asker_name}'s question about my role...", {
                "action": "role_questioned",
                "asker_id": asker_id
            }

        # AI decision-making for role claim
        response_data = {"action": "role_response", "asker_id": asker_id}

        # Villagers: Generally honest unless threatened
        if self.role == Role.VILLAGER:
            # Claim villager (highly likely)
            if rnd.random() < 0.9:
                self.process_role_claim(self.user.id, Role.VILLAGER, day, {
                    'claim_context': 'questioned',
                    'asker_id': asker_id
                })
                response_data["claimed_role"] = Role.VILLAGER

                responses = [
                    f"I'm a Villager, {asker_name}. Nothing special I can do except help find the wolves.",
                    f"Just a regular Villager. Wish I had special abilities to help us!",
                    f"I'm a Villager. I know that's not exciting, but it's the truth.",
                    f"Villager. I know that's hard to verify, but it's what I am."
                ]
                return rnd.choice(responses), response_data
            else:
                # Occasionally refuse to claim
                response_data["role_refusal"] = True
                refusal_evidence = Evidence(
                    player_id=self.user.id,
                    day=day,
                    action=ActionType.ROLE_REFUSAL
                )
                self.add_evidence(refusal_evidence)

                responses = [
                    f"I don't think I need to reveal my role right now, {asker_name}.",
                    f"Why should I tell you my role? Who are YOU?",
                    f"I'm not comfortable sharing that information yet.",
                    f"Let's focus on finding the wolves first before demanding roles."
                ]
                return rnd.choice(responses), response_data

        # Seer: Strategic about revealing
        elif self.role == Role.SEER:
            # Calculate reveal pressure
            num_players = len(game_state.get('alive_players', []))
            reveal_threshold = self.behavior.get('reveal_threshold', 0.7)

            # More pressure in late game
            if num_players <= 4:
                reveal_threshold -= 0.3

            # More pressure if directly accused
            direct_suspicion = 0
            for p_id, opinion in game_state.get('player_opinions', {}).items():
                if opinion.get('target_id') == self.user.id and opinion.get('suspicion', 0) > 0.7:
                    direct_suspicion += 0.15

            reveal_pressure = direct_suspicion + (1.0 / num_players) * 2

            # Decide whether to reveal
            if reveal_pressure > reveal_threshold or self._forced_claim_day:
                # Reveal as Seer
                self.process_role_claim(self.user.id, Role.SEER, day, {
                    'claim_context': 'questioned',
                    'asker_id': asker_id
                })

                # Include a result if we have one
                result_text = ""
                response_data["claimed_role"] = Role.SEER

                if self.seer_inspections:
                    # Reveal last inspection
                    target_id, role = self.seer_inspections[-1]
                    target_name = "someone"

                    for p in game_state.get('players', []):
                        if p.user.id == target_id:
                            target_name = p.user.display_name
                            break

                    result_text = f" I inspected {target_name} and found they are a {role.name.title()}."
                    response_data["seer_result"] = {
                        "target_id": target_id,
                        "role": role
                    }

                responses = [
                    f"I'm the Seer, {asker_name}.{result_text} I've been keeping it quiet to avoid being targeted.",
                    f"I'm actually the Seer.{result_text} I wasn't planning to reveal yet, but I feel I need to now.",
                    f"The truth is I'm the Seer.{result_text} I hope this doesn't make me the wolves' next target.",
                    f"Seer.{result_text} Now I'm probably going to be killed tonight, thanks for forcing me to reveal."
                ]
                return rnd.choice(responses), response_data
            else:
                # Hide role - usually claim Villager
                if rnd.random() < 0.8:
                    self.process_role_claim(self.user.id, Role.VILLAGER, day, {
                        'claim_context': 'questioned',
                        'asker_id': asker_id,
                        'true_role': Role.SEER
                    })
                    response_data["claimed_role"] = Role.VILLAGER

                    responses = [
                        f"I'm a Villager, {asker_name}. Just trying to help find the wolves like everyone else.",
                        f"Villager. Nothing special about my role I'm afraid.",
                        f"Just a normal Villager. Wish I could do more to help.",
                        f"I'm a Villager. I know that's not very exciting."
                    ]
                    return rnd.choice(responses), response_data
                else:
                    # Refuse to claim
                    response_data["role_refusal"] = True
                    refusal_evidence = Evidence(
                        player_id=self.user.id,
                        day=day,
                        action=ActionType.ROLE_REFUSAL
                    )
                    self.add_evidence(refusal_evidence)

                    responses = [
                        f"I don't think I should reveal my role right now.",
                        f"I'd prefer to keep that information to myself for the moment, {asker_name}.",
                        f"Let's focus on finding the wolves first before demanding roles.",
                        f"Why don't YOU tell us YOUR role first, {asker_name}?"
                    ]
                    return rnd.choice(responses), response_data

        # Werewolf: Strategic deception
        elif self.role == Role.WEREWOLF:
            # Several options:
            # 1. Claim villager (most common)
            # 2. Claim Seer if desperate
            # 3. Refuse to claim

            # Check if there's already a claimed Seer
            seer_claims = []
            for p in game_state.get('players', []):
                if any(c.claimed_role == Role.SEER for c in p.role_claims):
                    seer_claims.append(p.user.id)

            # Calculate desperation level
            num_players = len(game_state.get('alive_players', []))
            wolf_suspicion = 0
            for p_id, opinion in game_state.get('player_opinions', {}).items():
                if opinion.get('target_id') == self.user.id and opinion.get('suspicion', 0) > 0.7:
                    wolf_suspicion += 0.2

            desperation = wolf_suspicion + (1.0 / num_players)

            # More desperate in late game
            if num_players <= 4:
                desperation += 0.3

            # If very desperate and no one has claimed Seer, consider claiming Seer
            if desperation > 0.8 and not seer_claims and rnd.random() < 0.4:
                # Claim to be Seer
                self.process_role_claim(self.user.id, Role.SEER, day, {
                    'claim_context': 'desperate',
                    'asker_id': asker_id
                })
                response_data["claimed_role"] = Role.SEER

                # Fabricate a result
                potential_targets = [p for p in game_state.get('alive_players', [])
                                    if p.user.id != self.user.id and p.role != Role.WEREWOLF]

                if potential_targets:
                    target = rnd.choice(potential_targets)
                    # Usually accuse someone of being wolf
                    fake_role = Role.WEREWOLF if rnd.random() < 0.7 else Role.VILLAGER

                    result_text = f" I inspected {target.user.display_name} last night and found they are a {fake_role.name.title()}."
                    response_data["fake_result"] = {
                        "target_id": target.user.id,
                        "claimed_role": fake_role
                    }
                else:
                    result_text = ""

                responses = [
                    f"I'm the Seer.{result_text} I've been hiding it to avoid being targeted.",
                    f"I should reveal now - I'm the Seer.{result_text}",
                    f"I'm the Seer.{result_text} I was waiting for the right moment to tell everyone.",
                    f"Actually, I'm the village Seer.{result_text} I know this puts a target on me."
                ]
                return rnd.choice(responses), response_data

            # Most common: claim Villager
            elif rnd.random() < 0.85:
                self.process_role_claim(self.user.id, Role.VILLAGER, day, {
                    'claim_context': 'questioned',
                    'asker_id': asker_id
                })
                response_data["claimed_role"] = Role.VILLAGER

                responses = [
                    f"I'm a Villager. Just trying to survive and find the real werewolves.",
                    f"Simple Villager. I know that's not very helpful for verification.",
                    f"I'm a Villager, {asker_name}. What about you?",
                    f"Villager. Wish I had a more interesting role to report!"
                ]
                return rnd.choice(responses), response_data

            # Occasionally refuse to claim
            else:
                response_data["role_refusal"] = True
                refusal_evidence = Evidence(
                    player_id=self.user.id,
                    day=day,
                    action=ActionType.ROLE_REFUSAL
                )
                self.add_evidence(refusal_evidence)

                responses = [
                    f"I don't see why I should reveal my role right now. It won't help us.",
                    f"I'd rather not say. People claim roles all the time and it doesn't prove anything.",
                    f"Why are you questioning me, {asker_name}? Trying to deflect suspicion?",
                    f"Let's focus on actions and behavior, not role claims that can't be verified."
                ]
                return rnd.choice(responses), response_data

    def ask_for_role(self, target: SPPlayer, day: int,
                    game_state: Dict, rnd: random.Random) -> Tuple[str, Dict]:
        """
        Generate a question asking someone about their role.

        Returns:
            Tuple of (question text, event data)
        """
        # Track question
        if day not in self.questions_asked:
            self.questions_asked[day] = []
        self.questions_asked[day].append(target.user.id)

        event_data = {
            "action": "role_question",
            "target_id": target.user.id
        }

        # Question style based on personality
        personality_name = self.personality.get('name', 'Neutral')

        if personality_name == "Aggressive":
            questions = [
                f"What's your role, {target.user.display_name}? And don't lie to us!",
                f"I demand to know your role, {target.user.display_name}. What are you?",
                f"Time to come clean, {target.user.display_name}. Tell us your role now!",
                f"Everyone's wondering - what's your role, {target.user.display_name}? We need answers."
            ]
            event_data["question_style"] = "aggressive"

        elif personality_name == "Analytical":
            questions = [
                f"For the sake of clarity, {target.user.display_name}, would you state your role?",
                f"I'd like to collect more data. {target.user.display_name}, what's your role?",
                f"It would be helpful if you could tell us your role, {target.user.display_name}.",
                f"In the interest of information gathering, {target.user.display_name}, what role are you?"
            ]
            event_data["question_style"] = "analytical"

        elif personality_name == "Cautious":
            questions = [
                f"I hope you don't mind me asking, but what's your role, {target.user.display_name}?",
                f"I'm curious, {target.user.display_name} - if you're comfortable sharing, what's your role?",
                f"Would you be willing to tell us your role, {target.user.display_name}?",
                f"If it's not too much trouble, could you share your role with us, {target.user.display_name}?"
            ]
            event_data["question_style"] = "cautious"

        elif personality_name == "Emotional":
            questions = [
                f"I've been wondering about you, {target.user.display_name} - what's your role?",
                f"I have a feeling I should ask - {target.user.display_name}, what role do you have?",
                f"My gut is telling me to ask you directly, {target.user.display_name} - what's your role?",
                f"I need to know, {target.user.display_name} - what role are you playing as?"
            ]
            event_data["question_style"] = "emotional"

        else:  # Strategic or default
            questions = [
                f"{target.user.display_name}, I think it's time you told us your role.",
                f"I'm interested to hear what role you claim, {target.user.display_name}.",
                f"For the village's sake, {target.user.display_name}, what's your role?",
                f"Let's hear it, {target.user.display_name} - what role do you have?"
            ]
            event_data["question_style"] = "strategic"

        return rnd.choice(questions), event_data

    def generate_message(self, current_players: List[SPPlayer],
                        day: int, game_state: Dict, rnd: random.Random) -> Tuple[str, Dict]:
        """
        Generate a contextual message based on game state and strategy.

        Returns:
            Tuple of (message text, event data)
        """
        # Find alive players except self
        alive_others = [p for p in current_players if p.alive and p != self]

        # Game state tracking
        small_game = len(current_players) <= 4
        endgame = len(current_players) <= 3

        # Update all opinions before generating message
        for p_id, opinion in self.opinions.items():
            opinion.update_suspicion(self.behavior.get('trust_evidence', 0.6))

        # Store players by suspicion level for easy reference
        very_suspicious = []
        somewhat_suspicious = []
        neutral = []
        somewhat_trusted = []
        very_trusted = []

        for p in alive_others:
            if p.user.id in self.opinions:
                suspicion = self.opinions[p.user.id].suspicion
                if suspicion > 0.8:
                    very_suspicious.append(p)
                elif suspicion > 0.6:
                    somewhat_suspicious.append(p)
                elif suspicion > 0.4:
                    neutral.append(p)
                elif suspicion > 0.2:
                    somewhat_trusted.append(p)
                else:
                    very_trusted.append(p)
            else:
                neutral.append(p)

        # ------------------------------------------------------------------
        # SPECIAL CASE 1: FORCED ROLE CLAIMS IN SMALL GAMES
        # ------------------------------------------------------------------

        # In small games, people must claim roles
        if small_game and not self.claimed_role and not self.is_human:
            # For AI, generate appropriate role claim
            if self.role == Role.VILLAGER:
                # Honestly claim Villager
                self.process_role_claim(self.user.id, Role.VILLAGER, day, {
                    'claim_context': 'small_game',
                })

                claims = [
                    f"Since we're down to just a few players, I'll just say it - I'm a Villager.",
                    f"I think we all need to claim roles now. I'm a Villager.",
                    f"Let's all be open - I'm a regular Villager.",
                    f"We need transparency at this point - I'm a Villager."
                ]

                return rnd.choice(claims), {
                    "action": "role_claim",
                    "claimed_role": Role.VILLAGER
                }

            elif self.role == Role.SEER:
                # Claim Seer and provide result
                self.process_role_claim(self.user.id, Role.SEER, day, {
                    'claim_context': 'small_game',
                })

                # Include inspection results
                result_text = ""
                event_data = {
                    "action": "role_claim",
                    "claimed_role": Role.SEER
                }

                if self.seer_inspections:
                    # Reveal most relevant inspection
                    target_id, role = self.seer_inspections[-1]

                    # Try to find if target is still alive
                    target_name = "someone"
                    for p in current_players:
                        if p.user.id == target_id:
                            target_name = p.user.display_name
                            break

                    result_text = f" I inspected {target_name} and found they are a {role.name.title()}."
                    event_data["seer_result"] = {
                        "target_id": target_id,
                        "role": role
                    }

                claims = [
                    f"Time for the truth - I'm the Seer.{result_text}",
                    f"I've been hiding this, but I'm the Seer.{result_text}",
                    f"I need to reveal now - I'm the Seer.{result_text}",
                    f"I'm the Seer.{result_text} I hope this helps us find the wolf."
                ]

                return rnd.choice(claims), event_data

            elif self.role == Role.WEREWOLF:
                # Strategic deception
                # Has someone already claimed Seer?
                seer_claims = []
                for p in current_players:
                    if p.claimed_role == Role.SEER:
                        seer_claims.append(p.user.id)

                if not seer_claims and rnd.random() < 0.4:
                    # Bold move - fake Seer claim
                    self.process_role_claim(self.user.id, Role.SEER, day, {
                        'claim_context': 'small_game_deception',
                    })

                    # Fabricate a result against someone who isn't a wolf
                    potential_targets = [p for p in alive_others if p.role != Role.WEREWOLF]
                    if potential_targets:
                        target = rnd.choice(potential_targets)
                        # Almost always accuse in small games
                        fake_role = Role.WEREWOLF

                        result_text = f" I inspected {target.user.display_name} and found they are a {fake_role.name.title()}."
                        fake_result = {
                            "target_id": target.user.id,
                            "claimed_role": fake_role
                        }
                    else:
                        result_text = ""
                        fake_result = None

                    claims = [
                        f"I need to reveal now - I'm the Seer.{result_text}",
                        f"I can't stay silent anymore. I'm the Seer.{result_text}",
                        f"We need to know the truth. I'm the Seer.{result_text}",
                        f"Time for me to come forward as the Seer.{result_text}"
                    ]

                    return rnd.choice(claims), {
                        "action": "fake_seer_claim",
                        "claimed_role": Role.SEER,
                        "fake_result": fake_result
                    }
                else:
                    # Safer option - claim Villager
                    self.process_role_claim(self.user.id, Role.VILLAGER, day, {
                        'claim_context': 'small_game_deception',
                    })

                    claims = [
                        f"Let's all be clear about roles. I'm a Villager.",
                        f"Since we're down to the final few, I'll state directly - I'm a Villager.",
                        f"For the record, I'm a Villager. I've been trying to help find the wolves.",
                        f"I'm a regular Villager. Let's figure out who the wolf really is."
                    ]

                    return rnd.choice(claims), {
                        "action": "role_claim",
                        "claimed_role": Role.VILLAGER
                    }

        # ------------------------------------------------------------------
        # SPECIAL CASE 2: RESPOND TO DEATHS
        # ------------------------------------------------------------------

        recent_deaths = game_state.get('recent_deaths', [])
        if recent_deaths:
            death_reactions = []
            for dead_player in recent_deaths:
                if dead_player.role == Role.WEREWOLF:
                    # A wolf died
                    if self.role == Role.WEREWOLF:
                        # Fellow wolf reactions (subdued)
                        death_reactions.extend([
                            f"We eliminated a werewolf! That's great progress.",
                            f"That's one wolf down! We need to stay focused.",
                            f"I'm glad we found a wolf. Let's keep up the momentum.",
                            f"Good work everyone! We're making progress against the wolves."
                        ])
                    else:
                        # Genuine celebration
                        death_reactions.extend([
                            f"We got a werewolf! This is a huge win for the village!",
                            f"One wolf down! We're making real progress now.",
                            f"That's a victory for us! One step closer to safety.",
                            f"We actually caught a werewolf! We can win this!"
                        ])
                elif dead_player.role == Role.SEER:
                    # Seer died
                    if self.role == Role.WEREWOLF:
                        # Wolf feigns concern
                        death_reactions.extend([
                            f"We lost our Seer! This is really bad for us.",
                            f"The werewolves eliminated our Seer. We need to avenge them.",
                            f"Losing the Seer is a major setback. The wolves knew exactly what they were doing.",
                            f"This is terrible - without the Seer, we're at a big disadvantage."
                        ])
                    else:
                        # Real concern
                        death_reactions.extend([
                            f"We've lost our Seer! The wolves have struck a critical blow against us.",
                            f"This is devastating - without the Seer, we're much more vulnerable.",
                            f"The werewolves knew exactly who to target. We've lost our most powerful ally.",
                            f"Losing the Seer is exactly what the wolves wanted. We need to be smarter now."
                        ])
                else:
                    # Villager died
                    if self.role == Role.WEREWOLF:
                        # Wolf feigns sadness but reinforces suspicion
                        death_reactions.extend([
                            f"Another innocent villager lost. We need to be more strategic in our voting.",
                            f"We can't keep losing villagers like this! Someone among us is making very calculated moves.",
                            f"This is getting dangerous. The wolves are picking us off one by one.",
                            f"I'm starting to wonder if some of us are deliberately voting wrong to protect the wolves."
                        ])
                    else:
                        # Real concern
                        death_reactions.extend([
                            f"We lost another innocent villager. The wolves are winning right now.",
                            f"This is bad. We need to be smarter about finding the real wolves.",
                            f"Every villager we lose brings the wolves closer to victory. We need to turn this around.",
                            f"The werewolves are outplaying us so far. We need to change our approach."
                        ])

            if death_reactions:
                return rnd.choice(death_reactions), {"action": "death_reaction"}

        # ------------------------------------------------------------------
        # SPECIAL CASE 3: SEER REVEAL DECISIONS
        # ------------------------------------------------------------------

        if self.role == Role.SEER and self.seer_inspections and not self.claimed_role:
            # Calculate reveal pressure
            reveal_threshold = self.behavior.get('reveal_threshold', 0.7)

            # Higher pressure in smaller games
            if small_game:
                reveal_threshold -= 0.3

            # Higher pressure if suspected
            suspicion_against_me = 0
            for p in alive_others:
                if hasattr(p, 'opinions') and self.user.id in p.opinions:
                    suspicion = p.opinions[self.user.id].suspicion
                    if suspicion > 0.7:
                        suspicion_against_me += 0.1

            # Found a wolf recently
            found_wolf = any(role == Role.WEREWOLF for _, role in self.seer_inspections[-2:])
            if found_wolf:
                reveal_threshold -= 0.2

            # Decide whether to reveal
            reveal_roll = rnd.random()
            if reveal_roll > reveal_threshold or suspicion_against_me > 0.3 or small_game:
                # Decide to reveal role
                self.process_role_claim(self.user.id, Role.SEER, day, {
                    'claim_context': 'voluntary',
                })

                # Choose most damning evidence to reveal
                wolf_inspections = [(p_id, role) for p_id, role in self.seer_inspections
                                  if role == Role.WEREWOLF]

                if wolf_inspections:
                    # Prioritize revealing wolves
                    target_id, role = wolf_inspections[-1]

                    # Find the target's name
                    target_name = "someone"
                    target_alive = False
                    for p in current_players:
                        if p.user.id == target_id:
                            target_name = p.user.display_name
                            target_alive = p.alive
                            break

                    if target_alive:
                        reveals = [
                            f"I need to reveal something critical - I'm the Seer, and I inspected {target_name}. They are a **{role.name.title()}**!",
                            f"I've been keeping this secret, but it's time. I'm the Seer and {target_name} is a **{role.name.title()}**!",
                            f"As the village Seer, I have important information: {target_name} is a **{role.name.title()}**!",
                            f"I can't stay quiet anymore. I'm the Seer and I'm certain {target_name} is a **{role.name.title()}**!"
                        ]

                        return rnd.choice(reveals), {
                            "action": "seer_reveal",
                            "target_id": target_id,
                            "revealed_role": role
                        }
                    else:
                        # Target is dead, reveal a different result or general claim
                        other_inspections = [i for i in self.seer_inspections if i[0] != target_id]
                        if other_inspections:
                            other_id, other_role = other_inspections[-1]

                            # Find other target's name
                            other_name = "someone else"
                            for p in current_players:
                                if p.user.id == other_id:
                                    other_name = p.user.display_name
                                    break

                            reveals = [
                                f"I should reveal my role now - I'm the Seer. I inspected {other_name} and found they are a **{other_role.name.title()}**.",
                                f"As the village Seer, I can tell you that {other_name} is a **{other_role.name.title()}**.",
                                f"I'm the Seer, and I've confirmed that {other_name} is a **{other_role.name.title()}**.",
                                f"Time for me to step forward as the Seer. {other_name} is a **{other_role.name.title()}**."
                            ]

                            return rnd.choice(reveals), {
                                "action": "seer_reveal",
                                "target_id": other_id,
                                "revealed_role": other_role
                            }
                else:
                    # No wolf inspections, reveal most recent result
                    target_id, role = self.seer_inspections[-1]

                    # Find the target's name
                    target_name = "someone"
                    for p in current_players:
                        if p.user.id == target_id:
                            target_name = p.user.display_name
                            break

                    reveals = [
                        f"I should tell everyone - I'm the Seer. I inspected {target_name} and they are a **{role.name.title()}**.",
                        f"I need to reveal my role now. I'm the Seer, and {target_name} is a **{role.name.title()}**.",
                        f"As the Seer, I can confirm that {target_name} is a **{role.name.title()}**.",
                        f"I've been concealing my role, but it's time to reveal. I'm the Seer and {target_name} is a **{role.name.title()}**."
                    ]

                    return rnd.choice(reveals), {
                        "action": "seer_reveal",
                        "target_id": target_id,
                        "revealed_role": role
                    }

        # ------------------------------------------------------------------
        # SPECIAL CASE 4: CHALLENGE FAKE SEER CLAIMS
        # ------------------------------------------------------------------

        if self.role == Role.SEER and any(p.claimed_role == Role.SEER and p != self for p in alive_others):
            # Someone else claimed Seer - challenge them
            fake_seer = next(p for p in alive_others if p.claimed_role == Role.SEER)

            challenges = [
                f"Wait a minute - {fake_seer.user.display_name} is lying! I'm the real Seer!",
                f"That's impossible, {fake_seer.user.display_name}. I'm the actual Seer. You must be a wolf trying to confuse us!",
                f"I need to speak up - {fake_seer.user.display_name} is not the Seer, I am! They're almost certainly a wolf.",
                f"Everyone listen! {fake_seer.user.display_name} is falsely claiming to be the Seer. I'm the real Seer!"
            ]

            # Include your own result as proof
            if self.seer_inspections:
                target_id, role = self.seer_inspections[-1]

                # Find the target's name
                target_name = "someone"
                for p in current_players:
                    if p.user.id == target_id:
                        target_name = p.user.display_name
                        break

                challenges = [c + f" I can prove it - I inspected {target_name} and they are a **{role.name.title()}**." for c in challenges]

                return rnd.choice(challenges), {
                    "action": "seer_challenge",
                    "challenger_id": self.user.id,
                    "fake_seer_id": fake_seer.user.id,
                    "proof_target_id": target_id,
                    "proof_role": role
                }
            else:
                return rnd.choice(challenges), {
                    "action": "seer_challenge",
                    "challenger_id": self.user.id,
                    "fake_seer_id": fake_seer.user.id
                }

        # ------------------------------------------------------------------
        # STANDARD ACTIONS: QUESTIONS, ACCUSATIONS, DEFENSES
        # ------------------------------------------------------------------

        # Decide whether to ask about someone's role
        # More common in small games and for certain personalities
        can_question = not game_state.get('recently_questioned', False)
        question_chance = self.behavior.get('question_chance', 0.5) * (2 if small_game else 1)

        if can_question and rnd.random() < question_chance:
            # Choose who to question - prefer suspicious unquestioned players
            already_questioned = set()
            for day_num, targets in self.questions_asked.items():
                already_questioned.update(targets)

            # Candidates who haven't been questioned yet, prioritizing suspicious ones
            candidates = []

            for p in alive_others:
                if p.user.id not in already_questioned:
                    # Calculate priority score
                    score = 1.0  # Base score

                    # Add suspicion factor
                    if p.user.id in self.opinions:
                        score += self.opinions[p.user.id].suspicion * 2

                    # Deprioritize those who've already claimed roles
                    if p.claimed_role is not None:
                        score *= 0.5

                    candidates.append((p, score))

            # If everyone's been questioned, can re-question but with lower priority
            if not candidates:
                for p in alive_others:
                    # Calculate priority score
                    score = 0.5  # Lower base score for requestion

                    # Add suspicion factor
                    if p.user.id in self.opinions:
                        score += self.opinions[p.user.id].suspicion

                    candidates.append((p, score))

            if candidates:
                # Choose weighted by score
                weights = [score for _, score in candidates]
                target = rnd.choices([p for p, _ in candidates], weights=weights, k=1)[0]

                # Generate question
                question, event_data = self.ask_for_role(target, day, game_state, rnd)
                return question, event_data

        # ------------------------------------------------------
        # Decide whether to make accusation, defense, or observation
        # ------------------------------------------------------

        # More likely to accuse in small games
        accusation_chance = 0.6 if small_game else 0.4

        # Respond to accusations against self
        if self.user.id in game_state.get('recent_accusations', []):
            # Self-defense needed
            if self.role == Role.WEREWOLF:
                # Wolf defensiveness
                defenses = [
                    f"Why is everyone focusing on me? I'm not the werewolf!",
                    f"You're making a serious mistake if you think I'm a wolf. Look at the evidence!",
                    f"This feels like a witch hunt. I've been trying to help the village!",
                    f"I'm being framed here. The real wolf is probably the one accusing me!"
                ]

                return rnd.choice(defenses), {
                    "action": "defend_self",
                    "actual_role": Role.WEREWOLF
                }
            else:
                # Innocent defensiveness
                defenses = [
                    f"I understand why you might suspect me, but I'm not a werewolf. I'm on the village's side!",
                    f"Please don't vote for me - I'm innocent! The real wolf is still out there.",
                    f"I know it's hard to trust anyone, but I'm genuinely trying to help us survive.",
                    f"I'm NOT a werewolf. Think about who's pushing suspicion onto innocent players!"
                ]

                return rnd.choice(defenses), {
                    "action": "defend_self",
                    "actual_role": self.role
                }

        # Make accusation if there are suspicious players
        elif very_suspicious and rnd.random() < accusation_chance:
            # Choose target from very suspicious players
            target = rnd.choice(very_suspicious)

            # Evidence-based accusation
            evidence_list = []
            if target.user.id in self.opinions:
                for e in self.opinions[target.user.id].evidence:
                    if e.action == ActionType.ROLE_REFUSAL:
                        evidence_list.append("refused to claim a role")
                    elif e.action == ActionType.CONTRADICTION:
                        evidence_list.append("contradicted themselves")
                    elif e.action == ActionType.SEER_RESULT and e.details.get('revealed_role') == Role.WEREWOLF:
                        evidence_list.append("was identified as a wolf by the Seer")

            evidence_text = ""
            if evidence_list:
                if len(evidence_list) == 1:
                    evidence_text = f" They {evidence_list[0]}!"
                else:
                    evidence_text = f" They {evidence_list[0]} and {evidence_list[1]}!"

            # Accusation style based on personality
            acc_style = self.behavior.get('accusation_style', 'direct')

            if acc_style == "evidence-based":
                accusations = [
                    f"Based on the evidence, I'm convinced {target.user.display_name} is a werewolf.{evidence_text}",
                    f"Let's look at the facts - everything points to {target.user.display_name} being a werewolf.{evidence_text}",
                    f"I've been analyzing everyone's behavior, and {target.user.display_name} is definitely suspicious.{evidence_text}",
                    f"The logical conclusion is that {target.user.display_name} is one of the wolves.{evidence_text}"
                ]
            elif acc_style == "direct":
                accusations = [
                    f"I'm calling it - {target.user.display_name} is a werewolf!{evidence_text}",
                    f"{target.user.display_name} is definitely the wolf. We need to vote them out now!{evidence_text}",
                    f"It's obvious that {target.user.display_name} is the werewolf. Let's not waste any more time!{evidence_text}",
                    f"Everyone listen - {target.user.display_name} is the werewolf! Vote them out!{evidence_text}"
                ]
            elif acc_style == "tentative":
                accusations = [
                    f"I'm not entirely sure, but I think {target.user.display_name} might be a werewolf...{evidence_text}",
                    f"I hate to say this, but {target.user.display_name} seems very suspicious to me.{evidence_text}",
                    f"Has anyone else noticed {target.user.display_name} acting strangely?{evidence_text}",
                    f"I could be wrong, but something about {target.user.display_name} feels off.{evidence_text}"
                ]
            elif acc_style == "passionate":
                accusations = [
                    f"I can FEEL it - {target.user.display_name} is a werewolf!{evidence_text}",
                    f"My instincts are screaming that {target.user.display_name} is a wolf! Trust me on this!{evidence_text}",
                    f"I just KNOW that {target.user.display_name} is one of them!{evidence_text}",
                    f"Everything about {target.user.display_name} is setting off alarm bells! They're a wolf!{evidence_text}"
                ]
            else:  # calculated or default
                accusations = [
                    f"After careful consideration, I believe {target.user.display_name} is a werewolf.{evidence_text}",
                    f"I've been watching {target.user.display_name} closely. Their behavior is consistent with being a wolf.{evidence_text}",
                    f"If we analyze the situation strategically, {target.user.display_name} is the most likely wolf.{evidence_text}",
                    f"The most probable explanation is that {target.user.display_name} is a werewolf.{evidence_text}"
                ]

            return rnd.choice(accusations), {
                "action": "accuse",
                "target_id": target.user.id,
                "evidence": evidence_list
            }

        # Defend trusted players sometimes
        elif very_trusted and rnd.random() < 0.3:
            target = rnd.choice(very_trusted)

            defenses = [
                f"I actually trust {target.user.display_name}. They've been consistent and helpful.",
                f"I don't think {target.user.display_name} is a wolf. Their actions have been logical.",
                f"Let's not waste time suspecting {target.user.display_name}. I believe they're innocent.",
                f"From what I've seen, {target.user.display_name} is probably a genuine villager."
            ]

            return rnd.choice(defenses), {
                "action": "defend_other",
                "target_id": target.user.id
            }

        # ------------------------------------------------------------------
        # GENERAL COMMENTARY
        # ------------------------------------------------------------------

        # Base commentary on game state and role
        if endgame:
            # Endgame commentary
            if self.role == Role.WEREWOLF:
                # Wolf trying to create confusion
                comments = [
                    f"We're down to the final few. We MUST get this vote right or the wolf wins.",
                    f"This is our last chance to find the werewolf. Think carefully about everyone's behavior from the start.",
                    f"If we mislynch now, it's over for the village. Let's review what we know for certain.",
                    f"Everything comes down to this vote. Who's been the most deceptive throughout the game?"
                ]
            else:
                # Villager desperately trying to identify wolf
                comments = [
                    f"We're at a critical point. If we don't identify the wolf now, we lose everything.",
                    f"This is our final chance to save the village. Let's think back on everything that's happened.",
                    f"The wolf is among the few of us left. Look at who's been acting suspiciously all game.",
                    f"Our survival depends on this vote. Who's been manipulating the conversation from the beginning?"
                ]
        elif small_game:
            # Small game commentary
            if self.role == Role.WEREWOLF:
                # Wolf trying to sow discord
                comments = [
                    f"We need to be methodical now. Let's have everyone claim their roles and work from there.",
                    f"I'm noticing inconsistencies in what some people have been saying throughout the game.",
                    f"We can't afford any more mistakes. Let's focus on the facts, not emotions.",
                    f"The wolves have been very strategic in their kills. Think about who benefits from each death."
                ]
            else:
                # Villager strategy
                comments = [
                    f"We're getting close to identifying the wolves. Let's keep pressuring everyone for information.",
                    f"At this point, role claims are crucial. Anyone refusing to claim is highly suspicious.",
                    f"We've lost too many villagers already. Let's be more systematic in our approach.",
                    f"Think about who's been subtly directing our votes away from certain players."
                ]
        else:
            # Regular game commentary
            if self.role == Role.WEREWOLF:
                # Wolf trying to blend in
                comments = [
                    f"I'm still trying to figure out who the wolves might be. What patterns have you all noticed?",
                    f"Have we considered that the wolves might be working together to manipulate our votes?",
                    f"I think we need more information before making accusations. Let's be careful not to lynch innocents.",
                    f"The werewolves are probably enjoying watching us accuse each other. We need to be smarter."
                ]
            elif self.role == Role.SEER:
                # Seer being careful
                comments = [
                    f"I've been observing everyone carefully. Some behaviors don't add up.",
                    f"Let's think about who's been consistently trying to direct suspicion away from themselves.",
                    f"The wolves typically try to blend in by making reasonable suggestions. Watch for subtle manipulation.",
                    f"I have some theories about who might be a wolf, but I need more time to confirm."
                ]
            else:
                # Regular villager
                comments = [
                    f"I'm still trying to make sense of everything that's happened so far.",
                    f"We need to be more careful about who we vote for. The wolves want us to eliminate villagers.",
                    f"Has anyone noticed patterns in the night kills? Wolves choose their targets strategically.",
                    f"Let's focus on finding the wolves instead of arguing among ourselves."
                ]

        return rnd.choice(comments), {"action": "commentary"}


class SPGame:
    """Enhanced single-player Werewolf game with sophisticated AI reasoning."""

    def __init__(self, ctx: Context, total_players: int):
        """Initialize a new single-player game."""
        self.ctx = ctx
        self.total_players = max(3, min(12, total_players))
        self.rnd = random.Random()

        # Game state
        self.players: List[SPPlayer] = []
        self.day: int = 0
        self.night: int = 0
        self.game_log: List[Dict] = []

        # Recent events for reactivity
        self.recent_deaths: List[SPPlayer] = []
        self.recent_accusations: List[int] = []  # IDs of recently accused players
        self.recent_seer_claims: List[int] = []  # IDs of players who claimed Seer
        self.recent_role_questions: List[Tuple[int, int]] = []  # (asker_id, target_id)

        # Tracking
        self.used_names: Set[str] = set()
        self.votes: Dict[int, int] = {}  # Current votes: voter_id -> target_id
        self.vote_history: Dict[int, Dict[int, int]] = {}  # day -> {voter_id -> target_id}
        self.role_claims: Dict[int, Role] = {}  # player_id -> claimed_role

        # Set up players
        self._setup_players()

    # ------------------------------------------------------------------
    #  Setup & initialization
    # ------------------------------------------------------------------

    def _get_unique_name(self) -> str:
        """Get a random name that hasn't been used yet in this game."""
        available_names = [name for name in _NAMES if name not in self.used_names]

        # If all names used, add numeric suffix
        if not available_names:
            suffix = 1
            while True:
                for name in _NAMES:
                    new_name = f"{name} {suffix}"
                    if new_name not in self.used_names:
                        self.used_names.add(new_name)
                        return new_name
                suffix += 1

        # Use an available name
        name = self.rnd.choice(available_names)
        self.used_names.add(name)
        return name

    def _setup_players(self):
        """Create and configure players for the game."""
        human_member: discord.Member = self.ctx.author

        # Create human player first (role to be assigned later)
        self.players.append(SPPlayer(
            user=human_member,
            role=Role.VILLAGER,  # Placeholder
            is_human=True
        ))

        # Determine role distribution based on player count
        num_werewolves = 1  # Default
        if self.total_players >= 8:
            num_werewolves = 2
        elif self.total_players >= 12:
            num_werewolves = 3

        # Always have one Seer if at least 4 players
        has_seer = self.total_players >= 4

        # Calculate villagers
        num_villagers = self.total_players - 1 - num_werewolves
        if has_seer:
            num_villagers -= 1

        # Create role pool
        role_pool = [Role.WEREWOLF] * num_werewolves
        if has_seer:
            role_pool.append(Role.SEER)
        role_pool.extend([Role.VILLAGER] * num_villagers)

        self.rnd.shuffle(role_pool)

        # Create AI players with unique personalities
        for role in role_pool:
            uid = self.rnd.randint(1_000_000, 9_999_999)
            name = self._get_unique_name()

            # Assign a random personality
            personality = self.rnd.choice(_PERSONALITIES)

            # Create AI player
            ai_mem = AIMember(uid, name, personality)
            self.players.append(SPPlayer(
                user=ai_mem,
                role=role,
                is_human=False
            ))

        # Randomize human role
        human_role = self.rnd.choice([Role.VILLAGER, Role.SEER, Role.WEREWOLF])
        self.players[0].role = human_role

        # Ensure correct werewolf count
        if human_role == Role.WEREWOLF:
            # Remove one AI wolf if human got wolf role
            for i, p in enumerate(self.players[1:], 1):
                if p.role == Role.WEREWOLF:
                    self.players[i].role = Role.VILLAGER
                    break

        # Randomize player order
        self.rnd.shuffle(self.players)

        # Initialize player knowledge
        self._initialize_player_knowledge()

    def _initialize_player_knowledge(self):
        """Set up initial knowledge for each player."""
        wolves = [p for p in self.players if p.role == Role.WEREWOLF]

        # Werewolves know each other
        for wolf in wolves:
            for other_wolf in wolves:
                if wolf != other_wolf:
                    # Add knowledge about fellow wolves
                    wolf_evidence = Evidence(
                        player_id=other_wolf.user.id,
                        day=0,
                        action=ActionType.INFORMATION,
                        details={'role': Role.WEREWOLF, 'is_teammate': True}
                    )
                    wolf.add_evidence(wolf_evidence)

                    # Initialize very low suspicion for teammates
                    if other_wolf.user.id in wolf.opinions:
                        wolf.opinions[other_wolf.user.id].suspicion = 0.0

    # ------------------------------------------------------------------
    #  Helper methods
    # ------------------------------------------------------------------

    def _alive_players(self) -> List[SPPlayer]:
        """Get all alive players."""
        return [p for p in self.players if p.alive]

    def _alive_ai(self) -> List[SPPlayer]:
        """Get all alive AI players."""
        return [p for p in self._alive_players() if not p.is_human]

    def _find_player_by_name(self, txt: str) -> Optional[SPPlayer]:
        """Find a player by name in text."""
        txt = txt.lower().strip()
        for p in self._alive_players():
            if p.user.display_name.lower() in txt:
                return p
        return None

    def _find_player_by_id(self, player_id: int) -> Optional[SPPlayer]:
        """Find a player by their ID."""
        for p in self.players:
            if p.user.id == player_id:
                return p
        return None

    def _get_game_state(self) -> Dict:
        """Get current game state for AI reasoning."""
        return {
            'day': self.day,
            'night': self.night,
            'players': self.players,
            'alive_players': self._alive_players(),
            'recent_deaths': self.recent_deaths,
            'recent_accusations': self.recent_accusations,
            'recent_seer_claims': self.recent_seer_claims,
            'recent_role_questions': self.recent_role_questions,
            'recently_questioned': bool(self.recent_role_questions),
            'player_opinions': {p.user.id: p.opinions for p in self._alive_players() if hasattr(p, 'opinions')},
            'role_claims': self.role_claims,
            'votes': self.votes,
            'vote_history': self.vote_history
        }

    def _get_dm_link(self, player: SPPlayer) -> str:
        """Get direct link to player's DM channel."""
        try:
            if player.is_human and player.user.dm_channel and player.user.dm_channel.id:
                return f"https://discord.com/channels/@me/{player.user.dm_channel.id}"
        except (AttributeError, TypeError):
            pass
        return "https://discord.com/channels/@me"  # Default DM link

    def _human_player(self) -> Optional[SPPlayer]:
        """Get the human player or None if not found."""
        return next((p for p in self.players if p.is_human), None)

    # ------------------------------------------------------------------
    #  Communication helpers
    # ------------------------------------------------------------------

    async def _try_send(self, content: str) -> Optional[discord.Message]:
        """Send message to game channel, handling errors."""
        try:
            return await self.ctx.send(content)
        except Exception as e:
            print(f"Error sending message: {e}")
            return None

    async def _debug(self, message: str):
        """Send debug messages if enabled."""
        debug_id = 0 #we arent using this anymore and cbf removing it all
        if self.ctx.author.id == debug_id:
            await self._try_send(f"[DEBUG] {message}")
        else:
            print(f"[DEBUG] {message}")

    async def _wait_for_response(self, timeout: float, player: Optional[SPPlayer] = None,
                                specific_check: Optional[callable] = None) -> Optional[discord.Message]:
        """
        Wait for a response in either DMs or the game channel.

        Args:
            timeout: Seconds to wait
            player: Player who should respond (or None for any player)
            specific_check: Optional additional check function

        Returns:
            The message or None if timed out
        """
        if player and (not player.is_human or not player.alive):
            return None

        try:
            def check_message(m):
                # Basic check: correct author and channel
                basic_check = (
                    (not player or m.author.id == player.user.id) and
                    (m.channel == self.ctx.channel or
                     isinstance(m.channel, discord.DMChannel) or
                     (not hasattr(m.channel, 'guild') or m.channel.guild is None))
                )

                # Apply additional check if provided
                return specific_check(m) if specific_check and basic_check else basic_check

            return await self.ctx.bot.wait_for(
                "message",
                timeout=timeout,
                check=check_message
            )
        except asyncio.TimeoutError:
            return None

    # ------------------------------------------------------------------
    #  Game flow
    # ------------------------------------------------------------------

    async def run(self):
        """Run the full game from start to finish."""
        try:
            # Setup phase
            await self._inform_roles()

            # First night
            await self._try_send("🌘 💤 **Night falls on the village for the first time...**")
            await asyncio.sleep(3)

            self.night = 1
            deaths = await self._night_phase(first_night=True)

            # Check if game ended during first night (shouldn't happen)
            if await self._check_game_end():
                return

            # Main game loop
            self.day = 1
            while True:
                # Day phase
                await self._try_send(f"**Day {self.day}**")

                try:
                    await self._day_phase(deaths)
                except Exception as e:
                    await self._debug(f"Day phase error: {str(e)}")

                if await self._check_game_end():
                    break

                # Night phase
                self.night += 1
                try:
                    deaths = await self._night_phase()
                except Exception as e:
                    await self._debug(f"Night phase error: {str(e)}")
                    deaths = []

                if await self._check_game_end():
                    break

                self.day += 1

        except Exception as e:
            await self._debug(f"Game error: {str(e)}")
            await self._try_send("The game has encountered an unexpected error and must end.")

    async def _inform_roles(self):
        """Inform players of their roles with detailed messages."""
        human = self._human_player()
        if not human:
            return

        try:
            # Prepare werewolf team info if applicable
            wolf_team_info = ""
            if human.role == Role.WEREWOLF:
                fellow_wolves = [p for p in self.players if p.role == Role.WEREWOLF and not p.is_human]
                if fellow_wolves:
                    wolf_names = ", ".join(f"**{w.user.display_name}**" for w in fellow_wolves)
                    wolf_team_info = f"\n\n🐺 **Your Wolf Team:** {wolf_names}"
                else:
                    wolf_team_info = "\n\n🐺 **Wolf Team:** You are the only werewolf!"

            # Get DM link
            dm_link = self._get_dm_link(human)

            # Detailed role descriptions with gameplay instructions
            role_details = {
                Role.VILLAGER: (
                    "You are a **Villager** 👨‍🌾\n\n"
                    "**Your Goal**: Work with the village to identify and eliminate the Werewolf before they kill everyone.\n\n"
                    "**Your Abilities**:\n"
                    "- Vote during the day to eliminate suspicious players\n"
                    "- Ask other players about their roles\n"
                    "- Form alliances and share information\n"
                    "- Use logic and deduction to identify the wolves\n\n"
                    "**Strategy Tips**:\n"
                    "- Pay attention to role claims and contradictions\n"
                    "- Watch how players respond when questioned about their role\n"
                    "- Be cautious of players who redirect suspicion without evidence\n"
                    "- In the late game, getting everyone to claim roles is crucial"
                ),
                Role.SEER: (
                    "You are a **Seer** 👁️\n\n"
                    "**Your Goal**: Use your supernatural insight to help the village identify the Werewolf.\n\n"
                    "**Your Abilities**:\n"
                    "- Each night, you can inspect ONE player to learn their true role\n"
                    "- You will receive a private message during night phases\n"
                    "- You can choose when (or if) to reveal your role and findings\n\n"
                    "**Strategy Tips**:\n"
                    "- Don't reveal immediately - the wolves will target you\n"
                    "- Consider revealing if you find a wolf or if you're under suspicion\n"
                    "- Your verified information is the village's most powerful weapon\n"
                    "- In late game, your knowledge becomes critical - reveal strategically"
                ),
                Role.WEREWOLF: (
                    "You are a **Werewolf** 🐺\n\n"
                    "**Your Goal**: Eliminate the villagers one by one until wolves equal or outnumber villagers.\n\n"
                    "**Your Abilities**:\n"
                    "- Each night, you can kill ONE player\n"
                    "- You know who the other wolves are (if any)\n"
                    "- You can claim any role to deceive the village\n\n"
                    "**Strategy Tips**:\n"
                    "- Act like a concerned villager seeking the truth\n"
                    "- Consider claiming to be the Seer if challenged\n"
                    "- Target players who are perceptive or suspicious of you\n"
                    "- The Seer is your biggest threat - eliminate them if identified" +
                    wolf_team_info
                )
            }

            # Send role information via DM
            try:
                await human.user.send(role_details.get(human.role, f"You are a **{human.role_name}**."))

                # Confirmation in main channel
                await self._try_send(
                    f"{self.ctx.author.mention}, check your [DMs]({dm_link}) for your role information!"
                )

            except (discord.Forbidden, AttributeError):
                # Fallback if DM fails
                basic_role_info = {
                    Role.VILLAGER: "You are a **Villager** 👨‍🌾. Find and eliminate the werewolf before it's too late!",
                    Role.SEER: "You are a **Seer** 👁️. Each night you can inspect a player to learn their true role.",
                    Role.WEREWOLF: "You are a **Werewolf** 🐺. Each night you can kill a villager. Don't get caught!"
                }

                await self._try_send(
                    f"{self.ctx.author.mention}, you are **{human.role_name}**. (couldn't DM you detailed information)\n{basic_role_info.get(human.role, '')}"
                )

        except Exception as e:
            await self._debug(f"Error informing roles: {e}")
            # Simple fallback
            await self._try_send(f"{self.ctx.author.mention}, you are a **{human.role_name}**.")

    async def _night_phase(self, first_night: bool = False) -> List[SPPlayer]:
        """
        Execute the night phase where special roles perform their actions.

        Returns:
            List of players who died this night
        """
        await self._try_send(f"🌙 **Night {self.night}. Everyone sleeps…**")
        await asyncio.sleep(self.rnd.uniform(2, 3) if first_night else self.rnd.uniform(3, 4))

        # ------ SEER PHASE ------
        human_seer = next((p for p in self._alive_players() if p.is_human and p.role == Role.SEER), None)
        ai_seer = next((p for p in self._alive_players() if not p.is_human and p.role == Role.SEER), None)

        # Announce Seer phase subtly
        await self._try_send("**The Seer awakens and searches for answers in the darkness...**")
        await asyncio.sleep(1.5)

        # Process human Seer if exists
        if human_seer:
            # Get DM link for human Seer
            dm_link = self._get_dm_link(human_seer)

            # Get candidates for inspection (all alive players except self)
            candidates = [p for p in self._alive_players() if p != human_seer]

            if not candidates:
                await self._try_send("*The Seer finds no one left to inspect...*")
            else:
                # Format candidate list
                candidate_list = "\n".join([f"• **{p.user.display_name}**" for p in candidates])

                # Try to send instructions via DM
                dm_sent = False
                try:
                    # Create game link for navigation
                    game_link = f"https://discord.com/channels/{self.ctx.guild.id}/{self.ctx.channel.id}/{self.ctx.message.id}"

                    await human_seer.user.send(
                        f"👁️ **Seer Action:** Choose someone to inspect.\n\n"
                        f"Available players to inspect:\n{candidate_list}\n\n"
                        f"Respond here in DMs OR in the game channel with the person's name or `skip`\n\n"
                        f"[Return to Game]({game_link})"
                    )
                    dm_sent = True
                except (discord.Forbidden, AttributeError):
                    dm_sent = False

                # Send prompt to channel as well
                if dm_sent:
                    await self._try_send(
                        f"👁️ **{self.ctx.author.mention}**, check your [DMs]({dm_link}) for Seer instructions!\n"
                        f"You can respond either in DMs or here in the channel."
                    )
                else:
                    # Fallback to channel-only
                    await self._try_send(f"👁️ **{self.ctx.author.mention}**, as the **Seer**, choose someone to inspect:")
                    await self._try_send(
                        f"Available players to inspect:\n{candidate_list}\n\nType a name to inspect, or `skip` to pass:"
                    )

                # Wait for response with appropriate timeout
                timeout = 20 if first_night else 30
                target = None

                try:
                    msg = await self._wait_for_response(timeout, human_seer)

                    if msg:
                        choice = msg.content.strip().lower()
                        if choice != "skip":
                            target = self._find_player_by_name(choice)
                            if not target:
                                # Invalid target
                                error_msg = "Could not find that player. Your inspection has been skipped."
                                if msg.channel != self.ctx.channel:
                                    await human_seer.user.send(error_msg)
                                else:
                                    await self._try_send(error_msg)
                            else:
                                # Valid target
                                confirm_msg = "*You will receive the inspection result privately.*"
                                if msg.channel != self.ctx.channel:
                                    await human_seer.user.send(
                                        f"You have chosen to inspect **{target.user.display_name}**. Results coming soon..."
                                    )
                                await self._try_send(confirm_msg)

                                # Send result via DM
                                result_msg = f"**Seer Result:** {target.user.display_name} is a **{target.role_name}**."

                                # Add interpretation/advice
                                if target.role == Role.WEREWOLF:
                                    result_msg += "\n\n⚠️ You've found a werewolf! Consider revealing this information when strategic."
                                else:
                                    result_msg += "\n\nThis player is not a werewolf. This information might help clear their name later."

                                await human_seer.user.send(result_msg)

                                # Record the inspection
                                human_seer.seer_inspections.append((target.user.id, target.role))
                        else:
                            # Player chose to skip
                            skip_msg = "You chose not to use your ability tonight."
                            if msg.channel != self.ctx.channel:
                                await human_seer.user.send(skip_msg)
                            else:
                                await self._try_send(skip_msg)
                    else:
                        # Timed out
                        timeout_msg = "You ran out of time and missed your chance to inspect someone."
                        try:
                            await human_seer.user.send(timeout_msg)
                        except:
                            await self._try_send(timeout_msg)

                except Exception as e:
                    await self._debug(f"Error in Seer action: {str(e)}")

        # Process AI Seer
        elif ai_seer:
            # AI Seer chooses someone to inspect
            candidates = [p for p in self._alive_players() if p != ai_seer]
            if candidates:
                # Get game state for AI decision making
                game_state = self._get_game_state()

                # Choose strategic target
                target = ai_seer.choose_target(candidates, self.rnd)

                if target:
                    # Record inspection for AI knowledge
                    ai_seer.seer_inspections.append((target.user.id, target.role))

                    # Create evidence about the inspection
                    inspection_evidence = Evidence(
                        player_id=target.user.id,
                        day=self.day,
                        action=ActionType.INFORMATION,
                        details={'inspected_role': target.role}
                    )
                    ai_seer.add_evidence(inspection_evidence)

                    # Update AI's opinion of the target based on role
                    if target.user.id in ai_seer.opinions:
                        if target.role == Role.WEREWOLF:
                            ai_seer.opinions[target.user.id].suspicion = 1.0  # Confirmed wolf
                        else:
                            ai_seer.opinions[target.user.id].suspicion = 0.0  # Confirmed innocent

                    await self._try_send("*The Seer's eyes glow briefly as they peer into someone's soul...*")

        # Pause before werewolf phase
        await asyncio.sleep(2)

        # ------ WEREWOLF PHASE ------
        human_wolf = next((p for p in self._alive_players() if p.is_human and p.role == Role.WEREWOLF), None)
        ai_wolves = [p for p in self._alive_players() if not p.is_human and p.role == Role.WEREWOLF]

        victim = None

        # Announce werewolf awakening
        await self._try_send("**The Werewolves awaken, hungry for blood...**")
        await asyncio.sleep(1.5)

        # Process human werewolf actions
        if human_wolf:
            # Get DM link
            dm_link = self._get_dm_link(human_wolf)

            # Get potential victims (exclude werewolves)
            candidates = [p for p in self._alive_players() if p.role != Role.WEREWOLF]

            if not candidates:
                await self._try_send("*The Werewolves find no suitable victims...*")
            else:
                # Format victim list with strategic information
                victim_details = []
                for p in candidates:
                    # Add strategic information
                    threat_level = "Unknown"
                    notes = []

                    # Determine threat level and special notes
                    if p.role == Role.SEER:
                        # We don't know they're Seer, but can give hints
                        if self.rnd.random() < 0.3:
                            threat_level = "High"
                            notes.append("Asks insightful questions")

                    # Show if they've claimed a role
                    if p.user.id in self.role_claims:
                        claimed_role = self.role_claims[p.user.id]
                        notes.append(f"Claims to be {claimed_role.name.title()}")

                        if claimed_role == Role.SEER:
                            threat_level = "Very High"
                            notes.append("Potential Seer")

                    # Base threat on how much they've interacted
                    if hasattr(p, 'questions_asked') and p.questions_asked:
                        total_questions = sum(len(targets) for day, targets in p.questions_asked.items())
                        if total_questions >= 3:
                            threat_level = "High" if threat_level == "Unknown" else threat_level
                            notes.append("Very inquisitive")

                    # Format the details
                    notes_text = f" ({', '.join(notes)})" if notes else ""
                    victim_details.append(f"• **{p.user.display_name}** - Threat: {threat_level}{notes_text}")

                # Try to send via DM
                dm_sent = False
                try:
                    # Create game link
                    game_link = f"https://discord.com/channels/{self.ctx.guild.id}/{self.ctx.channel.id}/{self.ctx.message.id}"

                    # Different advice based on game state
                    if self.night == 1:
                        wolf_advice = "Consider eliminating the Seer early if you can identify them."
                    elif len(candidates) <= 3:
                        wolf_advice = "We're in the endgame - choose carefully to secure victory!"
                    else:
                        wolf_advice = "Target players who seem perceptive or are organizing the village."

                    await human_wolf.user.send(
                        f"🐺 **Werewolf Action:** Choose someone to kill tonight.\n\n"
                        f"Potential victims:\n{chr(10).join(victim_details)}\n\n"
                        f"**Wolf Advice:** {wolf_advice}\n\n"
                        f"Respond here in DMs OR in the game channel with the person's name or `skip`\n\n"
                        f"[Return to Game]({game_link})"
                    )
                    dm_sent = True
                except (discord.Forbidden, AttributeError):
                    dm_sent = False

                # Send prompt to channel
                if dm_sent:
                    await self._try_send(
                        f"🐺 **{self.ctx.author.mention}**, check your [DMs]({dm_link}) for Werewolf instructions!\n"
                        f"You can respond either in DMs or here in the channel."
                    )
                else:
                    # Fallback to channel
                    await self._try_send(f"🐺 **{self.ctx.author.mention}**, as the **Werewolf**, choose someone to kill tonight:")
                    # Simple list without extra info
                    victim_list = "\n".join([f"• **{p.user.display_name}**" for p in candidates])
                    await self._try_send(
                        f"Potential victims:\n{victim_list}\n\nType a name to kill, or `skip` to spare everyone tonight:"
                    )

                # Wait for response
                timeout = 20 if first_night else 30
                try:
                    msg = await self._wait_for_response(timeout, human_wolf)

                    if msg:
                        choice = msg.content.strip().lower()
                        if choice != "skip":
                            victim = self._find_player_by_name(choice)
                            if victim and victim.role == Role.WEREWOLF:
                                # Can't kill fellow wolves
                                error_msg = "You can't kill another werewolf! Choose someone else or type `skip`."
                                if msg.channel != self.ctx.channel:
                                    await human_wolf.user.send(error_msg)
                                else:
                                    await self._try_send(f"{self.ctx.author.mention}, {error_msg}")
                                victim = None
                            elif not victim:
                                # Invalid target
                                error_msg = "Could not find that player. You'll spare everyone tonight."
                                if msg.channel != self.ctx.channel:
                                    await human_wolf.user.send(error_msg)
                                else:
                                    await self._try_send(f"{self.ctx.author.mention}, {error_msg}")
                                victim = None
                            else:
                                # Valid victim
                                confirm_msg = "*Your victim has been selected. The village will discover their fate in the morning...*"
                                if msg.channel != self.ctx.channel:
                                    await human_wolf.user.send(f"You have chosen to kill **{victim.user.display_name}** tonight.")
                                await self._try_send(confirm_msg)

                                # Record wolf's action
                                human_wolf.wolf_votes.append(victim.user.id)
                        else:
                            # Player chose to skip
                            skip_msg = "You chose not to kill anyone tonight."
                            if msg.channel != self.ctx.channel:
                                await human_wolf.user.send(skip_msg)
                            else:
                                await self._try_send(skip_msg)
                    else:
                        # Timed out
                        timeout_msg = "You ran out of time and missed your chance to kill someone."
                        try:
                            await human_wolf.user.send(timeout_msg)
                        except:
                            await self._try_send(timeout_msg)
                except Exception as e:
                    await self._debug(f"Error in Werewolf action: {str(e)}")

        # Process AI werewolves
        elif ai_wolves:
            # Get potential victims (non-wolves)
            candidates = [p for p in self._alive_players() if p.role != Role.WEREWOLF]

            if candidates:
                # Get game state for AI decision making
                game_state = self._get_game_state()

                # Coordinate between multiple wolves
                if len(ai_wolves) > 1:
                    # Have each wolf nominate a target
                    nominations = []
                    for wolf in ai_wolves:
                        target = wolf.choose_target(candidates, self.rnd)
                        if target:
                            nominations.append((target, wolf))

                    # Count nominations
                    vote_counts = {}
                    for target, _ in nominations:
                        vote_counts[target] = vote_counts.get(target, 0) + 1

                    # Select the most nominated target, with wolf who nominated as the killer
                    if vote_counts:
                        max_votes = max(vote_counts.values())
                        top_targets = [t for t, v in vote_counts.items() if v == max_votes]
                        victim = self.rnd.choice(top_targets)

                        # Record the kill for all wolves
                        for wolf in ai_wolves:
                            wolf.wolf_votes.append(victim.user.id)
                else:
                    # Single wolf selects target
                    lone_wolf = ai_wolves[0]
                    victim = lone_wolf.choose_target(candidates, self.rnd)

                    if victim:
                        lone_wolf.wolf_votes.append(victim.user.id)

                if victim:
                    await self._try_send("*The Werewolves stalk through the shadows, hunting their prey...*")

        # Night resolution
        await asyncio.sleep(2 if first_night else 3)
        await self._try_send("**The village falls silent as dawn approaches...**")

        # Slightly longer wait on regular nights
        await asyncio.sleep(self.rnd.uniform(5, 6) if first_night else self.rnd.uniform(7, 9))

        # Process death
        deaths = []
        if victim and victim.alive:
            victim.alive = False
            victim.day_died = self.day
            deaths.append(victim)
            self.recent_deaths = [victim]

            # Create death evidence for all players to process
            for p in self._alive_players():
                death_evidence = Evidence(
                    player_id=victim.user.id,
                    day=self.day,
                    action=ActionType.NIGHT_DEATH
                )
                p.add_evidence(death_evidence)

            # Announce death
            await self._try_send(f"💀 During the night **{victim.user.display_name}** was killed!")

            # Reveal role of the dead player
            await self._try_send(f"*The village discovers they were a **{victim.role_name}**.*")
        else:
            self.recent_deaths = []
            await self._try_send("The night passed peacefully... Everyone is still alive.")

        await asyncio.sleep(1.5)
        return deaths

    async def _day_phase(self, recent_deaths=None):
        """Handle the day phase with discussion and voting."""
        # Reset daily trackers
        self.recent_accusations = []
        self.recent_role_questions = []
        self.recent_deaths = recent_deaths or []

        # Begin day with announcement and death processing
        # (already handled in night phase return)

        # Announce discussion phase
        await self._try_send("The villagers gather in the town square to discuss the situation...")
        await asyncio.sleep(1.5)

        # --------------- DISCUSSION PHASE ---------------

        human = self._human_player()
        human_messages = []

        # Select AI speakers for discussion
        alive_ai = self._alive_ai()
        num_speakers = min(len(alive_ai), max(3, len(alive_ai)))
        speakers = alive_ai if len(alive_ai) <= num_speakers else self.rnd.sample(alive_ai, num_speakers)

        # Set up discussion timer
        discussion_time = 60 if self.day <= 2 else 90  # More time in later days
        discussion_end = datetime.datetime.now() + datetime.timedelta(seconds=discussion_time)

        # Explain discussion phase to player
        if human and human.alive:
            await self._try_send(
                f"💬 **Discussion time!** You have {discussion_time} seconds to talk with the villagers.\n"
                f"You can **ask specific players about their roles** by mentioning their name and asking directly.\n"
                f"You can also make accusations, defend players, or claim a role yourself."
            )
        else:
            await self._try_send("💬 **The villagers begin their discussion...**")

        # Initialize AI speaker timing
        next_speaker_idx = 0
        next_speaker_time = datetime.datetime.now() + datetime.timedelta(seconds=self.rnd.uniform(2.0, 4.0))

        # Main discussion loop - non-blocking with concurrent processing
        while datetime.datetime.now() < discussion_end:
            # Check for human input with short timeout
            if human and human.alive:
                try:
                    message = await asyncio.wait_for(
                        self.ctx.bot.wait_for(
                            "message",
                            check=lambda m: m.author == self.ctx.author and m.channel == self.ctx.channel
                        ),
                        timeout=0.5  # Very short timeout to keep checking other conditions
                    )

                    # Human message received
                    human_messages.append(message)

                    # Process message content
                    msg_content = message.content.lower()
                    mentioned_players = []

                    # Find mentioned players
                    for p in self._alive_players():
                        if p != human and p.user.display_name.lower() in msg_content:
                            mentioned_players.append(p)

                    # 1. Check for role questions
                    is_role_question = "role" in msg_content and any(q in msg_content for q in
                                                                   ["what", "tell me", "share", "what's", "who"])

                    # 2. Check for role claims by the human
                    is_role_claim = False
                    claimed_role = None

                    role_claim_phrases = {
                        "i am a": None,
                        "i'm a": None,
                        "i am the": None,
                        "i'm the": None,
                        "my role is": None,
                        "i have the role": None
                    }

                    for phrase in role_claim_phrases:
                        if phrase in msg_content:
                            is_role_claim = True
                            # Determine claimed role
                            if "seer" in msg_content:
                                claimed_role = Role.SEER
                            elif "villager" in msg_content:
                                claimed_role = Role.VILLAGER
                            elif "werewolf" in msg_content or "wolf" in msg_content:
                                claimed_role = Role.WEREWOLF
                            break

                    # 3. Check for accusations
                    is_accusation = any(word in msg_content for word in
                                      ["wolf", "werewolf", "suspicious", "sus", "lying", "liar", "evil", "vote"])

                    # 4. Check for defenses
                    is_defense = any(word in msg_content for word in
                                   ["innocent", "trust", "not wolf", "not a wolf", "not the wolf", "safe"])

                    # Now process the message type

                    # CASE 1: Role Question
                    if is_role_question and mentioned_players:
                        # Human is asking about someone's role
                        target = mentioned_players[0]  # Take first mentioned player

                        # Record the question
                        self.recent_role_questions.append((human.user.id, target.user.id))

                        if not target.is_human:
                            # AI will respond to role question
                            await asyncio.sleep(self.rnd.uniform(1.0, 2.0))

                            # Get AI response
                            game_state = self._get_game_state()
                            response, event_data = target.get_role_response(human.user.id, self.day, game_state, self.rnd)

                            # Process the response
                            await self._try_send(f"**{target.user.display_name}**: {response}")

                            # Record any role claims
                            if event_data.get('claimed_role'):
                                self.role_claims[target.user.id] = event_data['claimed_role']

                            # Record refusals
                            if event_data.get('role_refusal'):
                                refusal_evidence = Evidence(
                                    player_id=target.user.id,
                                    day=self.day,
                                    action=ActionType.ROLE_REFUSAL
                                )
                                human.add_evidence(refusal_evidence)

                    # CASE 2: Role Claim
                    elif is_role_claim and claimed_role:
                        # Human is claiming a role
                        self.role_claims[human.user.id] = claimed_role

                        # Create evidence for AI players to process
                        role_claim_evidence = Evidence(
                            player_id=human.user.id,
                            day=self.day,
                            action=ActionType.ROLE_CLAIM,
                            details={'role': claimed_role}
                        )

                        # Record this claim
                        for ai_player in self._alive_ai():
                            ai_player.process_role_claim(human.user.id, claimed_role, self.day)

                        # If claiming Werewolf, immediate suspicion increase
                        if claimed_role == Role.WEREWOLF:
                            for ai_player in self._alive_ai():
                                if human.user.id in ai_player.opinions:
                                    ai_player.opinions[human.user.id].suspicion = 1.0  # Maximum suspicion!

                            # Some AI will react to werewolf claim
                            if self.rnd.random() < 0.8:
                                reactor = self.rnd.choice(self._alive_ai())
                                await asyncio.sleep(self.rnd.uniform(1.0, 2.0))

                                shock_responses = [
                                    f"**{reactor.user.display_name}**: Did you just... claim to be a WEREWOLF? Are you confessing?!",
                                    f"**{reactor.user.display_name}**: Wait, what? Did you just admit to being a werewolf?",
                                    f"**{reactor.user.display_name}**: Is this some kind of joke? You're claiming to be a werewolf?",
                                    f"**{reactor.user.display_name}**: Everyone, {human.user.display_name} just claimed wolf! I think we have our vote target."
                                ]
                                await self._try_send(self.rnd.choice(shock_responses))

                        # If claiming Seer and another Seer exists and has claimed, create conflict
                        elif claimed_role == Role.SEER:
                            existing_seers = [(p_id, p) for p_id, p in self.role_claims.items()
                                             if p == Role.SEER and p_id != human.user.id]

                            if existing_seers:
                                # Counter-claim situation!
                                challenger_id = existing_seers[0][0]
                                challenger = self._find_player_by_id(challenger_id)

                                if challenger and challenger.alive and not challenger.is_human:
                                    await asyncio.sleep(self.rnd.uniform(1.0, 2.0))

                                    challenge_responses = [
                                        f"**{challenger.user.display_name}**: That's impossible! I'm the real Seer! {human.user.display_name} must be a wolf trying to confuse us!",
                                        f"**{challenger.user.display_name}**: You're lying! I've already claimed to be the Seer. There can only be one!",
                                        f"**{challenger.user.display_name}**: Nice try, wolf. I'm the actual Seer, so {human.user.display_name} is clearly trying to mislead the village.",
                                        f"**{challenger.user.display_name}**: Everyone listen! {human.user.display_name} is making a false Seer claim! I'm the real Seer!"
                                    ]
                                    await self._try_send(self.rnd.choice(challenge_responses))

                    # CASE 3: Accusation
                    elif is_accusation and mentioned_players:
                        target = mentioned_players[0]

                        # Record the accusation
                        self.recent_accusations.append(target.user.id)

                        # Create evidence
                        accusation_evidence = Evidence(
                            player_id=human.user.id,
                            day=self.day,
                            action=ActionType.ACCUSATION,
                            target_id=target.user.id
                        )

                        # Have AIs process this accusation
                        for ai_player in self._alive_ai():
                            ai_player.add_evidence(accusation_evidence)

                        # Target AI responds to accusation
                        if not target.is_human:
                            await asyncio.sleep(self.rnd.uniform(1.5, 2.5))

                            # Different responses based on role
                            if target.role == Role.WEREWOLF:
                                # Wolf defensiveness
                                defenses = [
                                    f"**{target.user.display_name}**: That's completely unfair! I'm not a werewolf!",
                                    f"**{target.user.display_name}**: Why are you accusing me? What evidence do you have?",
                                    f"**{target.user.display_name}**: You're making a serious mistake, {human.user.display_name}. I'm innocent!",
                                    f"**{target.user.display_name}**: That's absurd. Maybe YOU'RE the werewolf trying to frame me!"
                                ]
                                await self._try_send(self.rnd.choice(defenses))

                                # Sometimes counter-accuse
                                if self.rnd.random() < 0.4:
                                    await asyncio.sleep(1.0)
                                    counter = [
                                        f"**{target.user.display_name}**: Actually, I'm starting to think {human.user.display_name} might be a wolf. This accusation feels like a distraction.",
                                        f"**{target.user.display_name}**: You know what? I think {human.user.display_name} might be the real wolf here. Why else target me with no evidence?",
                                    ]
                                    await self._try_send(self.rnd.choice(counter))

                                    # Record counter-accusation
                                    self.recent_accusations.append(human.user.id)
                            else:
                                # Innocent indignation
                                defenses = [
                                    f"**{target.user.display_name}**: I'm not the werewolf! I'm a {target.role_name}!",
                                    f"**{target.user.display_name}**: You're making a mistake! I'm completely innocent!",
                                    f"**{target.user.display_name}**: Why would you think I'm a wolf? I've been trying to help!",
                                    f"**{target.user.display_name}**: I understand your suspicion, but I promise I'm not a werewolf."
                                ]
                                await self._try_send(self.rnd.choice(defenses))

                                # Sometimes reveal role under pressure
                                if target.role == Role.SEER and not target.claimed_role and self.rnd.random() < 0.5:
                                    await asyncio.sleep(1.5)

                                    # Reveal role and an inspection
                                    if target.seer_inspections:
                                        inspected_id, found_role = target.seer_inspections[-1]
                                        inspected_player = self._find_player_by_id(inspected_id)

                                        if inspected_player:
                                            reveal = f"**{target.user.display_name}**: Fine! I didn't want to reveal this, but I'm the Seer! I inspected {inspected_player.user.display_name} and they are a **{found_role.name.title()}**!"
                                            await self._try_send(reveal)

                                            # Record the claim
                                            self.role_claims[target.user.id] = Role.SEER
                                    else:
                                        # No inspections to reveal
                                        reveal = f"**{target.user.display_name}**: I have to reveal this now - I'm the Seer! I haven't had a chance to inspect anyone useful yet."
                                        await self._try_send(reveal)

                                        # Record the claim
                                        self.role_claims[target.user.id] = Role.SEER

                    # CASE 4: Defense of others
                    elif is_defense and mentioned_players:
                        target = mentioned_players[0]

                        # Create defense evidence
                        defense_evidence = Evidence(
                            player_id=human.user.id,
                            day=self.day,
                            action=ActionType.DEFENSE,
                            target_id=target.user.id
                        )

                        # Have AIs process this defense
                        for ai_player in self._alive_ai():
                            ai_player.add_evidence(defense_evidence)

                        # Sometimes the defended player responds
                        if not target.is_human and self.rnd.random() < 0.6:
                            await asyncio.sleep(self.rnd.uniform(1.0, 2.0))

                            thanks = [
                                f"**{target.user.display_name}**: Thank you for defending me, {human.user.display_name}.",
                                f"**{target.user.display_name}**: I appreciate your support. I really am innocent.",
                                f"**{target.user.display_name}**: At least someone believes in me!",
                                f"**{target.user.display_name}**: Thanks for seeing the truth, {human.user.display_name}."
                            ]
                            await self._try_send(self.rnd.choice(thanks))

                except asyncio.TimeoutError:
                    pass  # No human message this cycle

            # Check if it's time for an AI to speak
            if datetime.datetime.now() >= next_speaker_time and next_speaker_idx < len(speakers):
                speaker = speakers[next_speaker_idx]

                # Get game state for AI
                game_state = self._get_game_state()

                # Generate strategic message
                message, event_data = speaker.generate_message(self._alive_players(),
                                                             self.day, game_state, self.rnd)

                # Send the message
                await self._try_send(f"**{speaker.user.display_name}**: {message}")

                # Process any action
                action = event_data.get('action', '')

                # Handle role claims
                if action in ('role_claim', 'fake_seer_claim'):
                    claimed_role = event_data.get('claimed_role')
                    if claimed_role:
                        self.role_claims[speaker.user.id] = claimed_role

                        # If Seer claim, record it
                        if claimed_role == Role.SEER:
                            self.recent_seer_claims.append(speaker.user.id)

                            # Process any revealed results
                            if 'seer_result' in event_data:
                                target_id = event_data['seer_result']['target_id']
                                role = event_data['seer_result']['role']

                                # Create evidence for others to consider
                                result_evidence = Evidence(
                                    player_id=speaker.user.id,
                                    day=self.day,
                                    action=ActionType.SEER_RESULT,
                                    target_id=target_id,
                                    details={'revealed_role': role}
                                )

                                # All AIs process this evidence
                                for ai_player in self._alive_ai():
                                    if ai_player != speaker:
                                        ai_player.add_evidence(result_evidence)

                            # Process fake results
                            if 'fake_result' in event_data:
                                target_id = event_data['fake_result']['target_id']
                                claimed_role = event_data['fake_result']['claimed_role']

                                # Create evidence for others to consider
                                fake_evidence = Evidence(
                                    player_id=speaker.user.id,
                                    day=self.day,
                                    action=ActionType.SEER_RESULT,
                                    target_id=target_id,
                                    details={'revealed_role': claimed_role, 'is_fake': True}
                                )

                                # All AIs process this evidence
                                for ai_player in self._alive_ai():
                                    if ai_player != speaker:
                                        ai_player.add_evidence(fake_evidence)

                                # Real Seer might challenge fake claim
                                real_seer = next((p for p in self._alive_ai()
                                              if p.role == Role.SEER and p != speaker and p.alive), None)

                                if real_seer and not real_seer.claimed_role and self.rnd.random() < 0.7:
                                    # Real Seer will often challenge fake claims
                                    await asyncio.sleep(self.rnd.uniform(1.5, 2.5))

                                    challenges = [
                                        f"**{real_seer.user.display_name}**: That's a lie! I'M the real Seer!",
                                        f"**{real_seer.user.display_name}**: Everyone listen! {speaker.user.display_name} is LYING. I'm the actual Seer!",
                                        f"**{real_seer.user.display_name}**: Wait! {speaker.user.display_name} is trying to deceive everyone. I'm the true Seer!"
                                    ]
                                    await self._try_send(self.rnd.choice(challenges))

                                    # Real Seer may reveal an inspection
                                    if real_seer.seer_inspections and self.rnd.random() < 0.8:
                                        await asyncio.sleep(1.0)

                                        inspected_id, found_role = real_seer.seer_inspections[-1]
                                        inspected_player = self._find_player_by_id(inspected_id)

                                        if inspected_player:
                                            proof = f"**{real_seer.user.display_name}**: I can prove it - I inspected {inspected_player.user.display_name} and they are a **{found_role.name.title()}**!"
                                            await self._try_send(proof)

                                            # Record the counter-claim
                                            self.role_claims[real_seer.user.id] = Role.SEER
                                            self.recent_seer_claims.append(real_seer.user.id)

                # Handle role questions
                elif action == 'role_question':
                    target_id = event_data.get('target_id')
                    if target_id:
                        # Record the question
                        self.recent_role_questions.append((speaker.user.id, target_id))

                        # If target is AI, generate response
                        target = self._find_player_by_id(target_id)
                        if target and not target.is_human and target.alive:
                            await asyncio.sleep(self.rnd.uniform(1.5, 2.5))

                            # Get AI response
                            response, response_data = target.get_role_response(
                                speaker.user.id, self.day, game_state, self.rnd)

                            # Send response
                            await self._try_send(f"**{target.user.display_name}**: {response}")

                            # Process any role claims
                            if response_data.get('claimed_role'):
                                self.role_claims[target.user.id] = response_data['claimed_role']

                            # Process any revealed results
                            if 'seer_result' in response_data:
                                self.recent_seer_claims.append(target.user.id)

                # Handle accusations
                elif action == 'accuse':
                    target_id = event_data.get('target_id')
                    if target_id:
                        # Record the accusation
                        self.recent_accusations.append(target_id)

                        # Create evidence for other AIs
                        accusation_evidence = Evidence(
                            player_id=speaker.user.id,
                            day=self.day,
                            action=ActionType.ACCUSATION,
                            target_id=target_id
                        )

                        # Other AIs process this evidence
                        for ai_player in self._alive_ai():
                            if ai_player != speaker:
                                ai_player.add_evidence(accusation_evidence)

                        # If target is AI, maybe respond
                        target = self._find_player_by_id(target_id)
                        if target and not target.is_human and target.alive and self.rnd.random() < 0.7:
                            await asyncio.sleep(self.rnd.uniform(1.0, 2.0))

                            # Different response based on role
                            if target.role == Role.WEREWOLF:
                                # Wolf defense
                                defenses = [
                                    f"**{target.user.display_name}**: That's ridiculous! I'm not a werewolf!",
                                    f"**{target.user.display_name}**: You're completely wrong about me, {speaker.user.display_name}.",
                                    f"**{target.user.display_name}**: I'm being framed! I'm innocent!",
                                    f"**{target.user.display_name}**: Why would you think that? I've been trying to help!"
                                ]
                                await self._try_send(self.rnd.choice(defenses))

                                # Sometimes counter-accuse
                                if self.rnd.random() < 0.4:
                                    await asyncio.sleep(1.0)

                                    counter = [
                                        f"**{target.user.display_name}**: Actually, I'm suspicious of YOU, {speaker.user.display_name}. This feels like a distraction tactic.",
                                        f"**{target.user.display_name}**: Nice try, wolf. You're accusing me to direct attention away from yourself!",
                                    ]
                                    await self._try_send(self.rnd.choice(counter))

                                    # Record counter-accusation
                                    self.recent_accusations.append(speaker.user.id)
                            elif target.role == Role.SEER and not target.claimed_role:
                                # Seer may reveal under pressure
                                if self.rnd.random() < 0.6:
                                    # Reveal role
                                    reveal = f"**{target.user.display_name}**: I didn't want to say this, but I must defend myself. I'm the Seer!"
                                    await self._try_send(reveal)

                                    # Maybe include inspection result
                                    if target.seer_inspections and self.rnd.random() < 0.8:
                                        await asyncio.sleep(1.0)

                                        inspected_id, found_role = target.seer_inspections[-1]
                                        inspected_player = self._find_player_by_id(inspected_id)

                                        if inspected_player:
                                            result = f"**{target.user.display_name}**: I inspected {inspected_player.user.display_name} and found they are a **{found_role.name.title()}**!"
                                            await self._try_send(result)

                                    # Record the claim
                                    self.role_claims[target.user.id] = Role.SEER
                                    self.recent_seer_claims.append(target.user.id)
                                else:
                                    # Defend without revealing
                                    defenses = [
                                        f"**{target.user.display_name}**: You're making a serious mistake. I'm not the werewolf!",
                                        f"**{target.user.display_name}**: I can assure you I'm innocent. The real wolf is still out there.",
                                        f"**{target.user.display_name}**: I understand why you might suspect me, but I promise I'm on the village's side."
                                    ]
                                    await self._try_send(self.rnd.choice(defenses))
                            else:
                                # Regular villager defense
                                defenses = [
                                    f"**{target.user.display_name}**: I'm not the werewolf! I'm just a villager!",
                                    f"**{target.user.display_name}**: You're wrong, {speaker.user.display_name}. I'm innocent!",
                                    f"**{target.user.display_name}**: Please don't vote for me. I'm not a wolf!",
                                    f"**{target.user.display_name}**: I know I can't prove my innocence, but I'm not a werewolf."
                                ]
                                await self._try_send(self.rnd.choice(defenses))

                # Handle Seer reveals and challenges
                elif action in ('seer_reveal', 'seer_challenge'):
                    # Record the claim
                    self.role_claims[speaker.user.id] = Role.SEER
                    self.recent_seer_claims.append(speaker.user.id)

                    # If this is a challenge, the challenged faker might respond
                    if action == 'seer_challenge':
                        fake_seer_id = event_data.get('fake_seer_id')
                        faker = self._find_player_by_id(fake_seer_id)

                        if faker and faker.alive and not faker.is_human:
                            await asyncio.sleep(self.rnd.uniform(1.5, 2.5))

                            # Different responses based on if they're actually a wolf
                            if faker.role == Role.WEREWOLF:
                                # Wolf caught in a lie
                                responses = [
                                    f"**{faker.user.display_name}**: Don't listen to {speaker.user.display_name}! THEY'RE the one who's lying!",
                                    f"**{faker.user.display_name}**: This is absurd! I'm the real Seer! {speaker.user.display_name} is trying to trick everyone!",
                                    f"**{faker.user.display_name}**: How convenient that you claim to be the Seer now. I think you're the wolf trying to get me killed!",
                                    f"**{faker.user.display_name}**: I stand by my claim! I'm the true Seer, and {speaker.user.display_name} is obviously the wolf!"
                                ]
                                await self._try_send(self.rnd.choice(responses))

                                # Create evidence for this conflict
                                conflict_evidence = Evidence(
                                    player_id=faker.user.id,
                                    day=self.day,
                                    action=ActionType.CONTRADICTION,
                                    details={'conflict_type': 'seer_claim', 'opponent_id': speaker.user.id}
                                )

                                # Other AIs process this evidence
                                for ai_player in self._alive_ai():
                                    if ai_player != faker and ai_player != speaker:
                                        ai_player.add_evidence(conflict_evidence)
                            else:
                                # Non-wolf with false claim (shouldn't happen often)
                                responses = [
                                    f"**{faker.user.display_name}**: I... I was just trying to help the village...",
                                    f"**{faker.user.display_name}**: I thought pretending to be the Seer would draw out the real wolves...",
                                    f"**{faker.user.display_name}**: Alright, I admit it. I'm not actually the Seer. I'm just a villager.",
                                    f"**{faker.user.display_name}**: I was trying to protect the real Seer by making myself a target."
                                ]
                                await self._try_send(self.rnd.choice(responses))

                    # Other villagers might comment on Seer reveals
                    if self.rnd.random() < 0.5:
                        commenters = [p for p in self._alive_ai() if p != speaker and p.role == Role.VILLAGER]
                        if commenters:
                            commenter = self.rnd.choice(commenters)
                            await asyncio.sleep(self.rnd.uniform(1.0, 2.0))

                            comments = [
                                f"**{commenter.user.display_name}**: That's very important information! We should consider this carefully.",
                                f"**{commenter.user.display_name}**: A Seer claim! This could change everything.",
                                f"**{commenter.user.display_name}**: Let's see if this Seer claim holds up. Could be crucial for the village.",
                                f"**{commenter.user.display_name}**: That's a bold revelation. If true, it helps us tremendously."
                            ]
                            await self._try_send(self.rnd.choice(comments))

                # Set up next speaker
                next_speaker_idx += 1
                next_speaker_time = datetime.datetime.now() + datetime.timedelta(seconds=self.rnd.uniform(3.0, 6.0))

            # Short sleep to prevent tight loop
            await asyncio.sleep(0.1)

        # End of discussion announcement
        await self._try_send("💬 **Discussion time is over!** Now it's time to vote.")
        await asyncio.sleep(1.5)

        # --------------- VOTING PHASE ---------------

        # Clear previous votes
        self.votes = {}

        # Give clear voting instructions
        await self._try_send("⏳ **Voting Phase!** You have 60 seconds to decide who to eliminate.")

        # Only prompt human for voting if they're alive
        if human and human.alive:
            # Get vote options
            vote_options = ""
            for target in self._alive_players():
                # Skip self and teammates if werewolf
                if target != human and not (human.role == Role.WEREWOLF and target.role == Role.WEREWOLF):
                    vote_options += f"• **{target.user.display_name}**\n"

            # Get DM link
            dm_link = self._get_dm_link(human)

            # Try to send voting instructions via DM
            try:
                # Create game link
                game_link = f"https://discord.com/channels/{self.ctx.guild.id}/{self.ctx.channel.id}"

                await human.user.send(
                    f"🔟 **Voting Phase:** Choose someone to eliminate.\n\n"
                    f"Type a player's name here in DMs OR in the game channel to vote for them:\n{vote_options}\n"
                    f"You can also type `skip` to abstain.\n\n"
                    f"[Return to Game]({game_link})"
                )

                # Notify in channel
                await self._try_send(
                    f"🔟 **{self.ctx.author.mention}**, check your [DMs]({dm_link}) for voting instructions!\n"
                    f"You can vote either in DMs or here in the channel by typing a player's name."
                )
            except (discord.Forbidden, AttributeError):
                # Fallback to channel instructions
                await self._try_send(
                    f"🔟 **{self.ctx.author.mention}**, choose someone to vote out by typing their name:\n{vote_options}\n"
                    f"Or type `skip` to abstain."
                )
        else:
            # No human player voting
            await self._try_send("The villagers begin casting their votes...")

        # Set up voting period
        voting_end = datetime.datetime.now() + datetime.timedelta(seconds=60)
        has_human_voted = False
        human_vote_target = None

        # Wait for human vote while showing AI votes progressively
        while datetime.datetime.now() < voting_end and (not human or not human.alive or not has_human_voted):
            try:
                # Check for human vote if applicable
                if human and human.alive and not has_human_voted:
                    # Check both DMs and channel for vote
                    msg = await self._wait_for_response(0.5, human)

                    if msg:
                        # Process human vote
                        content = msg.content.lower().strip()
                        if content == "skip":
                            await self._try_send(f"{self.ctx.author.mention} has chosen to abstain from voting.")
                            has_human_voted = True
                            self.votes[human.user.id] = None
                        else:
                            # Try to match a player name
                            vote_target = None
                            for p in self._alive_players():
                                if (p != human and p.user.display_name.lower() in content and
                                        not (human.role == Role.WEREWOLF and p.role == Role.WEREWOLF)):
                                    vote_target = p
                                    break

                            if vote_target:
                                await self._try_send(f"{self.ctx.author.mention} has voted to eliminate **{vote_target.user.display_name}**!")
                                self.votes[human.user.id] = vote_target.user.id
                                human_vote_target = vote_target.user.id
                                has_human_voted = True

                                # Create voting evidence for AI
                                vote_evidence = Evidence(
                                    player_id=human.user.id,
                                    day=self.day,
                                    action=ActionType.VOTE,
                                    target_id=vote_target.user.id
                                )

                                # AIs process this vote
                                for ai_player in self._alive_ai():
                                    ai_player.add_evidence(vote_evidence)
                            elif human.role == Role.WEREWOLF and any(
                                    p.role == Role.WEREWOLF and p.user.display_name.lower() in content for p in
                                    self._alive_players()):
                                # Human werewolf tried to vote for a teammate
                                error_msg = "You can't vote to eliminate another werewolf! Choose someone else."
                                if msg.channel != self.ctx.channel:
                                    await human.user.send(error_msg)
                                else:
                                    await self._try_send(f"{self.ctx.author.mention}, {error_msg}")
                            else:
                                # Invalid vote
                                error_msg = "That's not a valid player name. Please try again."
                                if msg.channel != self.ctx.channel:
                                    await human.user.send(error_msg)
                                else:
                                    await self._try_send(f"{self.ctx.author.mention}, {error_msg}")

                # Process occasional AI votes during the waiting period
                remaining_voters = [p for p in self._alive_ai() if p.user.id not in self.votes]
                if remaining_voters and self.rnd.random() < 0.15:  # 15% chance each check
                    voter = self.rnd.choice(remaining_voters)
                    await self._process_ai_vote(voter, human_vote_target)

                    # Pause between AI votes
                    await asyncio.sleep(self.rnd.uniform(1.5, 3.0))

            except Exception as e:
                await self._debug(f"Error in vote processing: {str(e)}")

            # Short sleep to prevent CPU hogging
            await asyncio.sleep(0.05)

        # If human hasn't voted, give them a final chance
        if human and human.alive and not has_human_voted:
            await self._try_send(f"{self.ctx.author.mention}, you have 15 seconds left to vote!")

            try:
                msg = await self._wait_for_response(15, human)

                if msg:
                    # Process final human vote
                    content = msg.content.lower().strip()
                    if content == "skip":
                        await self._try_send(f"{self.ctx.author.mention} has chosen to abstain from voting.")
                        self.votes[human.user.id] = None
                    else:
                        # Try to match a player name
                        vote_target = None
                        for p in self._alive_players():
                            if (p != human and p.user.display_name.lower() in content and
                                    not (human.role == Role.WEREWOLF and p.role == Role.WEREWOLF)):
                                vote_target = p
                                break

                        if vote_target:
                            await self._try_send(f"{self.ctx.author.mention} has voted to eliminate **{vote_target.user.display_name}**!")
                            self.votes[human.user.id] = vote_target.user.id
                            human_vote_target = vote_target.user.id

                            # Create voting evidence for AI
                            vote_evidence = Evidence(
                                player_id=human.user.id,
                                day=self.day,
                                action=ActionType.VOTE,
                                target_id=vote_target.user.id
                            )

                            # AIs process this vote
                            for ai_player in self._alive_ai():
                                ai_player.add_evidence(vote_evidence)
                        else:
                            await self._try_send(f"{self.ctx.author.mention}, your vote was invalid. Your vote has been skipped.")
                            self.votes[human.user.id] = None
                else:
                    await self._try_send(f"{self.ctx.author.mention} didn't vote in time.")
                    self.votes[human.user.id] = None
            except Exception as e:
                await self._debug(f"Error in final vote processing: {str(e)}")
                self.votes[human.user.id] = None

        # Process remaining AI votes with strategic coordination
        remaining_voters = [p for p in self._alive_ai() if p.user.id not in self.votes]
        for voter in remaining_voters:
            await self._process_ai_vote(voter, human_vote_target)
            # Short pause between votes
            await asyncio.sleep(self.rnd.uniform(0.7, 1.5))

        # Tally votes
        vote_count = {}
        for voter_id, target_id in self.votes.items():
            if target_id:  # None means abstain
                if target_id not in vote_count:
                    vote_count[target_id] = 0
                vote_count[target_id] += 1

        # Find most voted player
        most_voted_id = None
        max_votes = 0

        for target_id, count in vote_count.items():
            if count > max_votes:
                most_voted_id = target_id
                max_votes = count
            elif count == max_votes and most_voted_id:
                # Tie-breaker
                if self.rnd.random() < 0.5:
                    most_voted_id = target_id

        # Check for majority
        total_players = len(self._alive_players())
        majority_threshold = total_players // 2 + (1 if total_players % 2 == 1 else 0)
        has_majority = max_votes >= majority_threshold

        # Display vote summary
        await self._try_send("🗟️ **Voting Results:**")
        if vote_count:
            vote_summary = []
            for target_id, count in vote_count.items():
                target = self._find_player_by_id(target_id)
                if target:
                    vote_summary.append(f"**{target.user.display_name}**: {count} vote{'s' if count != 1 else ''}")

            if vote_summary:
                await self._try_send("\n".join(vote_summary))
            else:
                await self._try_send("No one received any votes.")
        else:
            await self._try_send("No one received any votes.")

        await asyncio.sleep(2)

        # Process vote outcome
        if most_voted_id and has_majority:
            # Someone was voted to die
            most_voted = self._find_player_by_id(most_voted_id)

            if most_voted:
                await self._try_send(f"🔟 **{most_voted.user.display_name}** received the most votes and will be eliminated!")

                # AI plea if they're being eliminated
                if not most_voted.is_human:
                    # Choose appropriate plea based on role
                    if most_voted.role == Role.WEREWOLF:
                        # Wolf tries to appear innocent
                        wolf_pleas = [
                            f"**{most_voted.user.display_name}**: Wait! This is a terrible mistake! I'm not the werewolf!",
                            f"**{most_voted.user.display_name}**: You're all making a huge error! I'm innocent!",
                            f"**{most_voted.user.display_name}**: No! The real werewolf is still among you!",
                            f"**{most_voted.user.display_name}**: Please! Don't do this! I'm not the wolf!"
                        ]
                        await self._try_send(self.rnd.choice(wolf_pleas))
                    else:
                        # Innocent AI expresses frustration
                        innocent_pleas = [
                            f"**{most_voted.user.display_name}**: No! I'm innocent! You're making a terrible mistake!",
                            f"**{most_voted.user.display_name}**: Why won't you listen to me? I'm not a werewolf!",
                            f"**{most_voted.user.display_name}**: You're condemning an innocent villager! The real wolf is laughing at us!",
                            f"**{most_voted.user.display_name}**: This is exactly what the wolves wanted! I'm not one of them!"
                        ]
                        await self._try_send(self.rnd.choice(innocent_pleas))

                    await asyncio.sleep(2)

                # Last words if human is being eliminated
                if most_voted.is_human:
                    await self._try_send(f"{self.ctx.author.mention}, do you have any last words? You have 10 seconds.")
                    try:
                        await self._wait_for_response(10, most_voted)
                    except Exception:
                        pass

                # Eliminate player
                most_voted.alive = False
                most_voted.day_died = self.day

                # Announce elimination
                await self._try_send(f"🔥 **{most_voted.user.display_name}** has been lynched by the village!")
                await asyncio.sleep(1.5)

                # Reveal role
                if most_voted.role == Role.WEREWOLF:
                    await self._try_send(
                        f"🐺 **{most_voted.user.display_name}** was a **Werewolf**! The village has won a small victory."
                    )

                    # Create evidence about this confirmed wolf
                    confirmation_evidence = Evidence(
                        player_id=most_voted.user.id,
                        day=self.day,
                        action=ActionType.INFORMATION,
                        details={'confirmed_role': Role.WEREWOLF, 'confirmed_by': 'lynch'}
                    )

                    # All players process this confirmation
                    for p in self._alive_players():
                        p.add_evidence(confirmation_evidence)

                    # Reactions from other players
                    if self.rnd.random() < 0.8:
                        reactors = [p for p in self._alive_ai() if p.role != Role.WEREWOLF]
                        if reactors:
                            reactor = self.rnd.choice(reactors)

                            reactions = [
                                f"**{reactor.user.display_name}**: We got one! Good work everyone!",
                                f"**{reactor.user.display_name}**: That's one wolf down! Let's keep this momentum going!",
                                f"**{reactor.user.display_name}**: We found a werewolf! We can win this!",
                                f"**{reactor.user.display_name}**: Justice has been served! One wolf eliminated!"
                            ]
                            await self._try_send(self.rnd.choice(reactions))

                    # Remaining wolves might react carefully
                    remaining_wolves = [p for p in self._alive_ai() if p.role == Role.WEREWOLF]
                    if remaining_wolves and self.rnd.random() < 0.7:
                        wolf = self.rnd.choice(remaining_wolves)

                        wolf_reactions = [
                            f"**{wolf.user.display_name}**: Good work everyone! That's one threat eliminated.",
                            f"**{wolf.user.display_name}**: I'm glad we found one of the wolves. Let's stay vigilant!",
                            f"**{wolf.user.display_name}**: One down! We need to keep working together to find the others.",
                            f"**{wolf.user.display_name}**: That's a relief! I was getting worried about surviving the night."
                        ]
                        await self._try_send(self.rnd.choice(wolf_reactions))
                else:
                    await self._try_send(f"😔 **{most_voted.user.display_name}** was a **{most_voted.role_name}**! An innocent villager has died.")

                    # Create evidence about this confirmed innocent
                    confirmation_evidence = Evidence(
                        player_id=most_voted.user.id,
                        day=self.day,
                        action=ActionType.INFORMATION,
                        details={'confirmed_role': most_voted.role, 'confirmed_by': 'lynch'}
                    )

                    # All players process this confirmation
                    for p in self._alive_players():
                        p.add_evidence(confirmation_evidence)

                    # If we lynched the Seer, extra reactions
                    if most_voted.role == Role.SEER:
                        # Wolves delight privately
                        wolves = [p for p in self._alive_ai() if p.role == Role.WEREWOLF]
                        if wolves and self.rnd.random() < 0.8:
                            wolf = self.rnd.choice(wolves)

                            # Wolf trying to hide excitement
                            wolf_reactions = [
                                f"**{wolf.user.display_name}**: Oh no! We lost our Seer. This is terrible!",
                                f"**{wolf.user.display_name}**: This is a disaster for the village. We need to be more careful!",
                                f"**{wolf.user.display_name}**: We made a grave mistake. The werewolves will be happy about this.",
                                f"**{wolf.user.display_name}**: This is exactly what the wolves wanted. We've lost our most valuable player."
                            ]
                            await self._try_send(self.rnd.choice(wolf_reactions))

                        # Villagers dismay
                        villagers = [p for p in self._alive_ai() if p.role == Role.VILLAGER]
                        if villagers and self.rnd.random() < 0.7:
                            villager = self.rnd.choice(villagers)

                            villager_reactions = [
                                f"**{villager.user.display_name}**: We just lynched our Seer?! This is disastrous!",
                                f"**{villager.user.display_name}**: This is the worst possible outcome! We've lost our best chance at finding the wolves!",
                                f"**{villager.user.display_name}**: How could we make such a terrible mistake? The Seer was our best hope!",
                                f"**{villager.user.display_name}**: We need to be much more careful about who we vote for. This is a huge setback!"
                            ]
                            await self._try_send(self.rnd.choice(villager_reactions))
                    else:
                        # General reactions to innocent lynch
                        reactors = [p for p in self._alive_ai()]
                        if reactors and self.rnd.random() < 0.7:
                            reactor = self.rnd.choice(reactors)

                            if reactor.role == Role.WEREWOLF:
                                # Wolf feigning concern
                                reactions = [
                                    f"**{reactor.user.display_name}**: We need to be more careful! That's another innocent villager lost.",
                                    f"**{reactor.user.display_name}**: The wolves are manipulating us. We just killed an innocent!",
                                    f"**{reactor.user.display_name}**: This is exactly what the werewolves want - for us to turn on each other.",
                                    f"**{reactor.user.display_name}**: We can't keep making these mistakes if we want to survive!"
                                ]
                            else:
                                # Genuine concern
                                reactions = [
                                    f"**{reactor.user.display_name}**: We killed an innocent villager! The real wolf is still among us.",
                                    f"**{reactor.user.display_name}**: This is bad. We need to be more careful with our voting.",
                                    f"**{reactor.user.display_name}**: We're helping the wolves by eliminating our own. We need to think more critically!",
                                    f"**{reactor.user.display_name}**: Another innocent lost. The werewolves must be laughing at us right now."
                                ]

                            await self._try_send(self.rnd.choice(reactions))

                # Check if any Seer claims were proven wrong
                for claimer_id, claimed_role in list(self.role_claims.items()):
                    if (claimed_role == Role.SEER and claimer_id != most_voted_id and
                            most_voted.role == Role.SEER):
                        # Someone falsely claimed to be Seer when we just lynched the real one
                        claimer = self._find_player_by_id(claimer_id)

                        if claimer and claimer.alive:
                            # Create lie detection evidence
                            lie_evidence = Evidence(
                                player_id=claimer_id,
                                day=self.day,
                                action=ActionType.LIE_DETECTED,
                                details={'lie_type': 'false_seer_claim', 'proof': 'real_seer_found'}
                            )

                            # All living players process this evidence
                            for p in self._alive_players():
                                if p != claimer:
                                    p.add_evidence(lie_evidence)

                                    # Dramatically increase suspicion of the liar
                                    if claimer_id in p.opinions:
                                        p.opinions[claimer_id].suspicion = 1.0  # Maximum suspicion

                            # Someone might call out the fake
                            accusers = [p for p in self._alive_ai() if p != claimer]
                            if accusers and self.rnd.random() < 0.8:
                                accuser = self.rnd.choice(accusers)

                                accusations = [
                                    f"**{accuser.user.display_name}**: Wait! {claimer.user.display_name} claimed to be the Seer earlier, but we just found the real Seer! They must be a wolf!",
                                    f"**{accuser.user.display_name}**: {claimer.user.display_name} LIED about being the Seer! We just lynched the real one! That makes them a werewolf!",
                                    f"**{accuser.user.display_name}**: We know who one of the wolves is now! {claimer.user.display_name} falsely claimed the Seer role!",
                                    f"**{accuser.user.display_name}**: {claimer.user.display_name} is definitely a werewolf! They pretended to be the Seer when the real one was {most_voted.user.display_name}!"
                                ]
                                await self._try_send(self.rnd.choice(accusations))

        else:
            # No one to eliminate
            if not most_voted_id:
                await self._try_send("🔴 **No Lynch Today!** No one received any votes for elimination.")
            else:
                # Not enough votes for majority
                voted_player = self._find_player_by_id(most_voted_id)
                voted_name = voted_player.user.display_name if voted_player else "Unknown"

                await self._try_send(
                    f"🔴 **No Majority Reached!** **{voted_name}** received {max_votes} votes, but at least {majority_threshold} votes were needed."
                )

            await self._try_send("The village remains uneasy as night approaches...")

            # Some players might comment on the indecision
            commenters = self._alive_ai()
            if commenters and self.rnd.random() < 0.7:
                commenter = self.rnd.choice(commenters)

                if commenter.role == Role.WEREWOLF:
                    # Wolf pretending to be concerned
                    comments = [
                        f"**{commenter.user.display_name}**: We need to be more decisive tomorrow. The wolves will pick us off if we can't agree!",
                        f"**{commenter.user.display_name}**: This indecision only helps the werewolves. We have to make a choice next time!",
                        f"**{commenter.user.display_name}**: Every day we don't eliminate a wolf is another night we're in danger. We need to be braver!",
                        f"**{commenter.user.display_name}**: I hope we can come to a consensus tomorrow. Our lives depend on it!"
                    ]
                else:
                    # Genuine concern
                    comments = [
                        f"**{commenter.user.display_name}**: We can't afford another day of indecision. The wolves are winning!",
                        f"**{commenter.user.display_name}**: Tomorrow we MUST vote decisively. The wolves are counting on our hesitation.",
                        f"**{commenter.user.display_name}**: I'm worried about tonight. We should have eliminated someone today.",
                        f"**{commenter.user.display_name}**: Our inability to decide only gives the werewolves another chance to kill!"
                    ]

                await self._try_send(self.rnd.choice(comments))

        # Save vote history for this day
        self.vote_history[self.day] = self.votes.copy()

        # Dramatic pause before night
        await asyncio.sleep(3)

    async def _process_ai_vote(self, voter: SPPlayer, human_vote_target_id: Optional[int] = None):
        """Process an AI player's vote with strategic decision-making."""
        # Get alive players except self
        candidates = [p for p in self._alive_players() if p.user.id != voter.user.id]

        # Don't allow wolves to vote for wolf teammates
        if voter.role == Role.WEREWOLF:
            candidates = [p for p in candidates if p.role != Role.WEREWOLF]

        if not candidates:
            # No valid targets - abstain
            self.votes[voter.user.id] = None
            await self._try_send(f"{voter.user.display_name} has chosen to abstain from voting.")
            return

        # Get game state for decision making
        game_state = self._get_game_state()

        # STRATEGIC VOTING LOGIC

        # 1. Always target exposed liars if any
        exposed_liars = []
        for p in candidates:
            if voter.user.id in voter.opinions:
                # Look for players with high suspicion and lie evidence
                opinion = voter.opinions[p.user.id]
                if opinion.suspicion > 0.8:
                    # Check for lie detection
                    for evidence in opinion.evidence:
                        if evidence.action == ActionType.LIE_DETECTED:
                            exposed_liars.append(p)
                            break

        if exposed_liars and self.rnd.random() < 0.95:  # 95% chance to vote for exposed liar
            target = self.rnd.choice(exposed_liars)
            self.votes[voter.user.id] = target.user.id

            await self._try_send(f"{voter.user.display_name} has voted to eliminate **{target.user.display_name}**!")
            return

        # 2. Role-based voting strategies
        if voter.role == Role.WEREWOLF:
            # WOLF VOTING STRATEGY

            # If human wolf voted, usually follow their lead
            if human_vote_target_id and self.rnd.random() < 0.8:
                self.votes[voter.user.id] = human_vote_target_id
                target = self._find_player_by_id(human_vote_target_id)
                if target:
                    await self._try_send(f"{voter.user.display_name} has voted to eliminate **{target.user.display_name}**!")
                    return

            # Otherwise, target based on threat level and suspicion
            wolf_targets = []
            for p in candidates:
                # Calculate threat score
                threat_score = 0

                # Seers are highest priority
                if p.role == Role.SEER:
                    threat_score += 50

                # Players who have claimed Seer are threats
                if p.user.id in self.role_claims and self.role_claims[p.user.id] == Role.SEER:
                    threat_score += 40

                # Players with low suspicion are good targets (they're trusted)
                if p.user.id in voter.opinions:
                    suspicion = voter.opinions[p.user.id].suspicion
                    threat_score += 30 * (1.0 - suspicion)  # Higher for trusted players

                # Add some randomness
                threat_score += self.rnd.uniform(0, 10)

                wolf_targets.append((p, threat_score))

            # Choose target with highest threat score
            if wolf_targets:
                wolf_targets.sort(key=lambda x: x[1], reverse=True)
                target = wolf_targets[0][0]

                self.votes[voter.user.id] = target.user.id

                await self._try_send(f"{voter.user.display_name} has voted to eliminate **{target.user.display_name}**!")
                return

        elif voter.role == Role.SEER:
            # SEER VOTING STRATEGY

            # Check if Seer found a wolf through inspection
            wolf_found = None
            for target_id, role in voter.seer_inspections:
                if role == Role.WEREWOLF:
                    target = self._find_player_by_id(target_id)
                    if target and target.alive:
                        wolf_found = target
                        break

            # If Seer found a wolf, vote for them
            if wolf_found and self.rnd.random() < 0.95:  # 95% chance
                self.votes[voter.user.id] = wolf_found.user.id

                await self._try_send(f"{voter.user.display_name} has voted to eliminate **{wolf_found.user.display_name}**!")
                return

            # Otherwise vote based on most suspicious player known to the Seer
            seer_targets = []
            for p in candidates:
                # Calculate suspicion score
                if p.user.id in voter.opinions:
                    suspicion = voter.opinions[p.user.id].suspicion
                    seer_targets.append((p, suspicion))
                else:
                    seer_targets.append((p, 0.5))  # Default if no opinion

            # Vote for most suspicious unless very uncertain
            if seer_targets:
                seer_targets.sort(key=lambda x: x[1], reverse=True)
                if seer_targets[0][1] > 0.6:  # Only vote if reasonably suspicious
                    target = seer_targets[0][0]

                    self.votes[voter.user.id] = target.user.id

                    await self._try_send(f"{voter.user.display_name} has voted to eliminate **{target.user.display_name}**!")
                    return
                elif self.rnd.random() < 0.3:  # 30% chance to abstain if uncertain
                    self.votes[voter.user.id] = None

                    await self._try_send(f"{voter.user.display_name} has chosen to abstain from voting.")
                    return
                else:  # 70% chance to vote for most suspicious anyway
                    target = seer_targets[0][0]

                    self.votes[voter.user.id] = target.user.id

                    await self._try_send(f"{voter.user.display_name} has voted to eliminate **{target.user.display_name}**!")
                    return

        # VILLAGER OR FALLBACK STRATEGY

        # Use most suspicious player based on evidence
        target = voter.most_suspicious(self._alive_players())

        if target:
            # Decide whether to vote or abstain
            if target.user.id in voter.opinions and voter.opinions[target.user.id].suspicion > 0.5:
                # Vote if suspicion is high enough
                self.votes[voter.user.id] = target.user.id

                await self._try_send(f"{voter.user.display_name} has voted to eliminate **{target.user.display_name}**!")
                return
            elif len(self._alive_players()) <= 3:
                # In very small games, always vote
                self.votes[voter.user.id] = target.user.id

                await self._try_send(f"{voter.user.display_name} has voted to eliminate **{target.user.display_name}**!")
                return
            elif self.rnd.random() < 0.6:  # 60% chance to vote if not highly suspicious
                self.votes[voter.user.id] = target.user.id

                await self._try_send(f"{voter.user.display_name} has voted to eliminate **{target.user.display_name}**!")
                return

        # Abstain as last resort
        self.votes[voter.user.id] = None

        await self._try_send(f"{voter.user.display_name} has chosen to abstain from voting.")

    async def _check_game_end(self) -> bool:
        """Check if the game has ended and announce results if so."""
        wolves_alive = [p for p in self._alive_players() if p.role == Role.WEREWOLF]
        villagers_alive = [p for p in self._alive_players() if p.role != Role.WEREWOLF]

        game_over = False

        if not wolves_alive:
            # Wolves all dead - village wins
            await self._try_send("🎉 **The Village has won!** All werewolves have been eliminated.")
            game_over = True
        elif len(wolves_alive) >= len(villagers_alive):
            # Wolves outnumber or equal villagers - wolves win
            await self._try_send("🐺 **The Werewolves have won!** They now outnumber the villagers.")
            game_over = True

        if game_over:
            await asyncio.sleep(2)

            # Role reveal summary
            await self._try_send("\n**Game Summary - Player Roles:**")

            # Sort by role and importance
            all_players = sorted(
                self.players,
                key=lambda p: (
                    0 if p.role == Role.WEREWOLF else (1 if p.role == Role.SEER else 2),  # Role importance
                    not p.alive,  # Alive players first
                    not p.is_human  # Human players first
                )
            )

            # Group by role category
            wolves = [p for p in all_players if p.role == Role.WEREWOLF]
            seers = [p for p in all_players if p.role == Role.SEER]
            villagers = [p for p in all_players if p.role == Role.VILLAGER]

            # Display each category with status
            if wolves:
                wolf_list = "\n".join(
                    [f"**{p.user.display_name}** {'(Alive)' if p.alive else '(Dead)'} {' - YOU' if p.is_human else ''}"
                     for p in wolves])
                await self._try_send(f"**Werewolves:**\n{wolf_list}")

            if seers:
                seer_list = "\n".join(
                    [f"**{p.user.display_name}** {'(Alive)' if p.alive else '(Dead)'} {' - YOU' if p.is_human else ''}"
                     for p in seers])
                await self._try_send(f"**Seers:**\n{seer_list}")

            if villagers:
                villager_list = "\n".join(
                    [f"**{p.user.display_name}** {'(Alive)' if p.alive else '(Dead)'} {' - YOU' if p.is_human else ''}"
                     for p in villagers])
                await self._try_send(f"**Villagers:**\n{villager_list}")

            # Player stats
            human = self._human_player()
            if human:
                win_condition = (
                    (human.role != Role.WEREWOLF and not wolves_alive) or
                    (human.role == Role.WEREWOLF and len(wolves_alive) >= len(villagers_alive))
                )
                result = "WON" if win_condition else "LOST"

                await self._try_send(f"\nYou played as **{human.role_name}** and **{result}**!")

            return True

        return False


class SinglePlayerWerewolf(commands.Cog):
    """Play werewolf as a single player against AI villagers."""

    def __init__(self, bot):
        self.bot = bot
        self.active_games = {}

    @commands.command(aliases=["spww", "spwerewolf"])
    async def singleww(self, ctx, players: int = 6):
        """
        Start a single-player werewolf game with AI opponents.

        Parameters:
        -----------
        players: int
            Number of players (including you). Must be between 3-12.
        """
        # Check for active game
        if ctx.author.id in self.active_games:
            return await ctx.send("You already have an active game! Finish that one first.")

        # Validate player count
        if not 3 <= players <= 12:
            return await ctx.send("Player count must be between 3 and 12.")

        # Create and start game
        game = SPGame(ctx, players)
        self.active_games[ctx.author.id] = game

        try:
            await game.run()
        except Exception as e:
            await ctx.send(f"Game error: {str(e)}")
        finally:
            # Remove game when complete
            if ctx.author.id in self.active_games:
                del self.active_games[ctx.author.id]

    @commands.command()
    async def wwhelp(self, ctx):
        """Get help with Werewolf commands and rules."""
        embed = discord.Embed(
            title="Single-Player Werewolf Help",
            color=discord.Color.dark_red(),
            description="Play a strategic game of deduction against intelligent AI werewolves and villagers."
        )

        embed.add_field(
            name="Commands",
            value=(
                "`/singleww [players]` - Start a new game with [players] total players (default: 6)\n"
                "`/spww [players]` - Alias for singleww\n"
                "`/wwhelp` - Show this help message"
            ),
            inline=False
        )

        embed.add_field(
            name="Special Interactions",
            value=(
                "• **Ask about roles** by mentioning a player's name with a question\n"
                "• **Claim a role** by clearly stating 'I am a [role]'\n"
                "• **Make accusations** against suspicious players\n"
                "• **Defend** players you think are innocent\n"
                "• AI will respond to your questions and statements"
            ),
            inline=False
        )

        embed.add_field(
            name="Basic Rules",
            value=(
                "**Objective**:\n"
                "• **Villagers**: Find and eliminate all werewolves\n"
                "• **Werewolves**: Eliminate enough villagers to gain majority\n\n"
                "**Roles**:\n"
                "• **Villager**: Must use deduction and social skills\n"
                "• **Seer**: Can check one player's true role each night\n"
                "• **Werewolf**: Can eliminate one player each night\n\n"
                "**Game Flow**:\n"
                "1. Night: Special roles use abilities\n"
                "2. Day: Discussion, questioning, and voting\n"
                "3. Repeat until a team wins"
            ),
            inline=False
        )

        embed.add_field(
            name="Tips For Victory",
            value=(
                "• Pay attention to role claims and contradictions\n"
                "• Question players directly about their roles\n"
                "• Watch how players react when questioned\n"
                "• In small games, force everyone to claim roles\n"
                "• As Seer, reveal strategically when you find a wolf\n"
                "• As Werewolf, consider claiming to be the Seer"
            ),
            inline=False
        )

        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(SinglePlayerWerewolf(bot))
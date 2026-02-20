"""Single-player Werewolf engine (simplified)
------------------------------------------------
This is an intentionally **much smaller** re-implementation of Werewolf that can
be played solo against AI opponents.  It is *not* a drop-in replacement for the
full multi-player engine in `utils.werewolf`, but it re-uses its `Role` and
`Side` enums so that wording and translations stay consistent.

For v1 we purposefully keep the role set small (Werewolf, Seer, Villager) to
avoid an explosion of AI logic.  This can be extended later.
"""
from __future__ import annotations

import asyncio
import datetime
import random
import string
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set

import discord
from babel.lists import format_list
from discord.ext import commands

from classes.context import Context
from utils.i18n import _
from utils.werewolf import Player, Role, Side, send_traceback  # reuse enums for naming / goal texts

__all__ = ['SPGame', 'Role', 'Side']  # Explicitly export these symbols

# ---------------------------------------------------------------------------
# Helper –   dummy discord.Member-like object for AI players
# ---------------------------------------------------------------------------

# Pre-defined list of readable first names for bots
_NAMES = [
    "Ava", "Ben", "Cara", "Dylan", "Eva", "Finn", "Grace", "Hugo",
    "Iris", "Jack", "Kara", "Liam", "Maya", "Noah", "Olive", "Paul",
    "Quinn", "Rosa", "Sam", "Tara", "Uma", "Vince", "Wade", "Xena",
    "Yara", "Zane",
]


class DummyAvatar:
    """Mimic `discord.Asset` enough for `avatar.url`."""

    @property
    def url(self):  # noqa: D401 – keep minimal
        return "https://via.placeholder.com/128?text=AI"


class AIMember:
    """Very small subset of the `discord.Member` interface used by the game."""

    __slots__ = ("id", "name", "display_name", "mention", "display_avatar")

    def __init__(self, uid: int, name: str):
        self.id: int = uid
        self.name = name
        # The game uses `str(member)` to print, which for members returns
        # `name#discriminator`.  We can just return name.
        self.display_name: str = name
        self.mention: str = f"**{name}**"  # bold fake mention
        self.display_avatar = DummyAvatar()

    # ------------------------------------------------------------------
    # Stubs for API the game *might* call; they just no-op.
    # ------------------------------------------------------------------
    async def send(self, *_a, **_kw):  # type: ignore[return-value]
        # Game tries to DM players. In SP we ignore.
        return None

    async def create_dm(self):
        return None

    @property
    def dm_channel(self):
        return None

    # For `str(member)` calls
    def __str__(self):  # noqa: D401 – simple
        return self.name


# ---------------------------------------------------------------------------
#  Core classes – SPPlayer and SPGame
# ---------------------------------------------------------------------------


class Vote(Enum):
    SKIP = 0  # abstain / skip lynch
    LYNCH = 1  # vote to lynch


@dataclass
class SPPlayer:
    user: discord.Member | AIMember
    role: Role
    is_human: bool

    alive: bool = True
    suspicion: float = 0.0  # AI only – higher → more likely wolf
    credibility: float = field(default=0.5)  # how trustworthy others see this player
    last_inspect: Optional[tuple["SPPlayer", Role]] = None  # seer result
    inspect_revealed: bool = False
    _temp_chat_log: list[str] = field(default_factory=list, init=False)
    claimed_role: Optional[Role] = None  # Track what role this player has claimed
    exposed_as_fake_seer: bool = False  # Flag for fake seers who were caught

    def __post_init__(self):
        # Give real Seers higher starting credibility
        if self.role == Role.SEER:
            self.credibility = 0.7  # Higher starting credibility for real Seers

    # For easier dictionary operations
    def __hash__(self):
        return hash(self.user.id)

    def __eq__(self, other):
        if not isinstance(other, SPPlayer):
            return False
        return self.user.id == other.user.id

    # Convenience – keep same attribute names used by the multiplayer code
    @property
    def role_name(self):
        return _(self.role.name.replace("_", " ").title())

    @property
    def side(self):
        if self.role == Role.WEREWOLF:
            return Side.WOLVES
        else:
            return Side.VILLAGERS

    # ---- Mini API used by SPGame ----

    def pick_target(self, candidates: List["SPPlayer"]) -> Optional["SPPlayer"]:
        """AI chooses a target to night-kill or to inspect if Seer."""
        # Filter to only alive players
        alive_candidates = [p for p in candidates if p.alive]

        if not alive_candidates:
            return None

        # Make sure werewolves don't target their own team
        if self.role == Role.WEREWOLF:
            # Remove other werewolves from candidates
            alive_candidates = [p for p in alive_candidates if p.role != Role.WEREWOLF]
            if not alive_candidates:
                return None

        # Weight by suspicion if wolf; else random.
        if self.role == Role.WEREWOLF:
            # Make suspicion weights more impactful but ensure they're all positive
            # Prioritize high-value targets like confirmed/claimed Seers
            weights = []
            for p in alive_candidates:
                weight = max(p.suspicion + 0.2, 0.1)
                # Significantly boost weight for known/claimed Seers
                if p.claimed_role == Role.SEER or p.role == Role.SEER:
                    weight *= 3.0
                weights.append(weight)

            try:
                # Use proper random choice with error handling
                return random.choices(alive_candidates, weights=weights, k=1)[0]
            except Exception:
                # Fallback to simple random choice if weights have issues
                if alive_candidates:
                    return random.choice(alive_candidates)
                return None

        if self.role == Role.SEER:
            # Prefer highly suspicious unknowns or players claiming roles
            weights = []
            for p in alive_candidates:
                weight = max(p.suspicion + 0.5, 0.1)
                # Prioritize checking players who make claims
                if p.claimed_role is not None:
                    weight *= 2.0
                weights.append(weight)

            try:
                return random.choices(alive_candidates, weights=weights, k=1)[0]
            except Exception:
                # Fallback
                if alive_candidates:
                    return random.choice(alive_candidates)
                return None

        if alive_candidates:
            return random.choice(alive_candidates)
        return None

    def day_sentence(self, alive: List["SPPlayer"], rnd: random.Random, round_type="general") -> tuple[
        str, dict | None]:
        """Return a contextual roleplay sentence based on the conversation phase.

        Args:
            alive: List of all alive players
            rnd: Random generator for consistent choices
            round_type: Conversation phase ('reaction', 'strategic', 'defense', 'general')

        Returns:
            Tuple of (formatted message, event dict for other AI to process)
        """
        self_event: dict | None = None

        # 1. SEER REVEAL LOGIC - more strategic now, depends on suspicion and timing
        if (self.role == Role.SEER and self.last_inspect and not self.inspect_revealed and
                ((round_type == "strategic" and rnd.random() < 0.7) or  # Usually reveal during strategy phase
                 (round_type == "defense" and self.suspicion > 0.4) or  # Reveal when suspected as defense
                 (self.suspicion > 0.6 and rnd.random() < 0.9))):  # Almost always reveal when highly suspect

            target, role_found = self.last_inspect
            self.inspect_revealed = True
            self.claimed_role = Role.SEER  # Mark that this player has claimed Seer

            # More varied Seer reveal phrases
            reveal_phrases = [
                f"As the Seer, I saw that {target.user.display_name} is a **{role_found.name.title()}**!",
                f"Listen everyone! I'm the Seer and {target.user.display_name} is **{role_found.name.title()}**!",
                f"I need to share something - I checked {target.user.display_name}: they're **{role_found.name.title()}**.",
                f"I've been quiet but I'm the Seer. {target.user.display_name} is **{role_found.name.title()}**!"
            ]

            text = _(rnd.choice(reveal_phrases))
            self_event = {"action": "reveal_inspect", "target": target, "role": role_found}
            return f"**{self.user.display_name}**: {text}", self_event

        # FAKE SEER CLAIM - Werewolves may pose as Seers sometimes
        if (self.role == Role.WEREWOLF and not self.claimed_role and round_type == "strategic" and
                rnd.random() < 0.2 and len(alive) > 3):  # Reduced chance to make fake seer claim (20%)

            # Choose a target that isn't a werewolf
            potential_targets = [p for p in alive if p != self and p.role != Role.WEREWOLF]
            if potential_targets:
                target = rnd.choice(potential_targets)
                # Usually claim the target is a werewolf (60% chance instead of 80%)
                claimed_role = Role.WEREWOLF if rnd.random() < 0.6 else Role.VILLAGER

                self.claimed_role = Role.SEER  # Mark that this wolf has claimed Seer

                # Fake seer reveal phrases
                reveal_phrases = [
                    f"I need to reveal myself - I'm the Seer! Last night I checked {target.user.display_name} and saw they're a **{claimed_role.name.title()}**!",
                    f"Everyone listen! As the Seer, I can tell you that {target.user.display_name} is a **{claimed_role.name.title()}**!",
                    f"I've been keeping quiet, but I'm the Seer. {target.user.display_name} is a **{claimed_role.name.title()}** - I checked them last night."
                ]

                text = _(rnd.choice(reveal_phrases))
                self_event = {"action": "fake_reveal", "target": target, "claimed_role": claimed_role}
                return f"**{self.user.display_name}**: {text}", self_event

        # 2. REACTION ROUND - responding to events (death, accusations)
        if round_type == "reaction":
            if self.role == Role.WEREWOLF:
                # Wolf trying to blend in
                reaction_templates = [
                    "This is terrible! We need to find the werewolf quickly.",
                    "I don't like this one bit. Let's think about who might be suspicious.",
                    "We need to be smart about this. Who's been acting strange?",
                    "This is getting serious. I think we need to be more careful with our votes."
                ]
                return f"**{self.user.display_name}**: {_(rnd.choice(reaction_templates))}", None
            elif self.role == Role.SEER:
                # Seer being cautious but helpful
                reaction_templates = [
                    "I might have some information that could help us...",
                    "Let me think about what I know so far...",
                    "We should focus on finding the wolf before more people die.",
                    "I have a feeling about who might be suspicious."
                ]
                return f"**{self.user.display_name}**: {_(rnd.choice(reaction_templates))}", None
            else:
                # Regular villager reactions
                reaction_templates = [
                    "I don't know who to trust anymore!",
                    "We need to be logical about this... who's been acting strange?",
                    "The way I see it, someone here is definitely lying.",
                    "I'm trying to piece this all together..."
                ]
                return f"**{self.user.display_name}**: {_(rnd.choice(reaction_templates))}", None

        # 3. RESPOND TO FAKE SEERS - call out exposed fake seers
        fake_seers = [p for p in alive if p != self and p.exposed_as_fake_seer]
        if fake_seers and rnd.random() < 0.8:  # Increased chance to call out fake seers (80%)
            fake_seer = rnd.choice(fake_seers)
            call_out_templates = [
                f"We know {fake_seer.user.display_name} lied about being the Seer! We should vote them out!",
                f"Don't forget that {fake_seer.user.display_name} made a false Seer claim - definitely the werewolf!",
                f"Let's focus on {fake_seer.user.display_name} - they already proved they're the werewolf with that fake Seer claim!"
            ]
            text = rnd.choice(call_out_templates)
            self_event = {"action": "accuse", "target": fake_seer}
            return f"**{self.user.display_name}**: {_(text)}", self_event

        # 4. STRATEGIC ROUND - more pointed accusations or defenses
        elif round_type == "strategic":
            # Find most suspicious person (not self)
            candidates = [p for p in alive if p != self]
            # Don't target team members if werewolf
            if self.role == Role.WEREWOLF:
                candidates = [p for p in candidates if p.role != Role.WEREWOLF]

            if not candidates:
                return f"**{self.user.display_name}**: {_('I need to think carefully...')}", None

            # Sort by suspicion but also consider exposed fake seers as highest priority
            candidates_sorted = sorted(candidates, key=lambda p: (1 if p.exposed_as_fake_seer else 0, p.suspicion),
                                       reverse=True)
            most_suspicious = candidates_sorted[0] if candidates_sorted else None

            if not most_suspicious:
                return f"**{self.user.display_name}**: {_('I need to think carefully...')}", None

            # If werewolf, try to frame someone else
            if self.role == Role.WEREWOLF:
                # Wolf strategic framing
                wolf_templates = [
                    "I've been watching {target} and their behavior seems off.",
                    "Has anyone else noticed that {target} keeps changing their story?",
                    "I'm pretty sure {target} is lying to us. Let's vote for them.",
                    "Think about it - {target} was very quiet when we discussed the last death."
                ]
                text = rnd.choice(wolf_templates).format(target=most_suspicious.user.display_name)
                self_event = {"action": "accuse", "target": most_suspicious}
                return f"**{self.user.display_name}**: {_(text)}", self_event

            # If villager/seer, make legitimate accusations based on suspicion
            else:
                # Only accuse if suspicion is high enough or they're an exposed fake seer
                if most_suspicious.suspicion > 0.4 or most_suspicious.exposed_as_fake_seer:
                    accuse_templates = [
                        "I don't want to point fingers, but {target} has been very suspicious.",
                        "Based on how {target} has been talking, I think they might be the wolf.",
                        "I'm starting to think {target} might be hiding something from us.",
                        "Everything points to {target} being the werewolf. We should vote for them."
                    ]
                    text = rnd.choice(accuse_templates).format(target=most_suspicious.user.display_name)
                    self_event = {"action": "accuse", "target": most_suspicious}
                else:
                    # If no one is very suspicious, general statement
                    general_templates = [
                        "I'm still not sure who the werewolf is.",
                        "Let's not rush to judgment. We need more evidence.",
                        "I don't have a strong suspicion yet. What does everyone else think?",
                        "We should be careful not to lynch an innocent villager."
                    ]
                    text = rnd.choice(general_templates)
                    self_event = None
                return f"**{self.user.display_name}**: {_(text)}", self_event

        # 5. DEFENSE ROUND - focused on self-defense when suspected
        elif round_type == "defense" and self.suspicion > 0.4:
            if self.role == Role.WEREWOLF:
                # Wolf trying to appear innocent
                defense_templates = [
                    "Why are you all looking at me? I'm a villager just like most of you!",
                    "This is ridiculous. I'm innocent! We're wasting time focusing on me.",
                    "If you lynch me, you'll see I'm innocent and we'll lose a villager.",
                    "I think someone is trying to frame me because I'm getting close to the truth."
                ]
                text = rnd.choice(defense_templates)
                self_event = {"action": "defend", "target": self}
                return f"**{self.user.display_name}**: {_(text)}", self_event

            elif self.role == Role.SEER and not self.inspect_revealed and self.last_inspect:
                # Seer reveals under pressure (handled in section 1)
                # This should not execute due to the checks in section 1, but as fallback:
                target, role_found = self.last_inspect
                text = _(
                    f"Wait! I'm the Seer! I already checked {target.user.display_name} - they're **{role_found.name.title()}**!")
                self.inspect_revealed = True
                self.claimed_role = Role.SEER
                self_event = {"action": "reveal_inspect", "target": target, "role": role_found}
                return f"**{self.user.display_name}**: {text}", self_event

            else:  # Innocent villager defense
                defense_templates = [
                    "Listen, I'm just a villager trying to survive! Voting me out will only help the wolf.",
                    "I understand I'm under suspicion, but I'm innocent. Let's focus on finding the real wolf.",
                    "I promise I'm not the werewolf. Think about who's been trying to get me lynched.",
                    "If you lynch me, you'll be making a terrible mistake. I'm a valuable ally!"
                ]
                text = rnd.choice(defense_templates)
                self_event = {"action": "defend", "target": self}
                return f"**{self.user.display_name}**: {_(text)}", self_event

        # 6. FALLBACK GENERAL CONVERSATION - similar to original but more varied
        # Target someone with appropriate suspicion level for accusations
        candidates = [p for p in alive if p != self]
        # Don't target team members if werewolf
        if self.role == Role.WEREWOLF:
            candidates = [p for p in candidates if p.role != Role.WEREWOLF]

        if not candidates:
            return f"**{self.user.display_name}**: {_('I need to think carefully...')}", None

        # More substantial templates for general conversation
        templates_accuse = [
            "I'm getting more suspicious of {target} with every passing moment.",
            "{target} hasn't been very convincing in their explanations.",
            "Has anyone else noticed {target} behaving strangely? Very suspicious...",
            "The way {target} has been talking makes me think they're hiding something.",
            "I can't shake the feeling that {target} might be the werewolf."
        ]

        templates_defend = [
            "I actually think {target} is probably innocent, based on how they've been acting.",
            "From what I've seen, {target} seems to be genuinely trying to help the village.",
            "I'd be surprised if {target} turned out to be the wolf.",
            "Let's not be too hasty accusing {target}, they seem trustworthy to me."
        ]

        templates_other = [
            "We need to think strategically if we want to catch the werewolf.",
            "Remember, the werewolf will try to blend in and sound helpful.",
            "Let's all share what we know and try to piece this together.",
            "We need to be smart about who we vote for. Every lynch matters.",
            "I'm still trying to figure out who's telling the truth here."
        ]

        # Choose an appropriate target
        if self.role == Role.WEREWOLF:
            # Wolf targets someone else with moderate-high suspicion, to blend in
            targets_by_suspicion = sorted(candidates, key=lambda p: p.suspicion, reverse=True)
            cand = targets_by_suspicion[0] if targets_by_suspicion else rnd.choice(candidates)
            sentence = rnd.choice(templates_accuse).format(target=cand.user.display_name)
            self_event = {"action": "accuse", "target": cand}
        else:
            # Villagers more accurately target based on suspicion
            # Prioritize exposed fake seers
            fake_seers = [p for p in candidates if p.exposed_as_fake_seer]
            high_suspects = [p for p in candidates if p.suspicion > 0.5 or p in fake_seers]

            if high_suspects and rnd.random() < 0.7:
                cand = rnd.choice(high_suspects)
                sentence = rnd.choice(templates_accuse).format(target=cand.user.display_name)
                self_event = {"action": "accuse", "target": cand}
            elif rnd.random() < 0.3:
                # Sometimes defend a random person with low suspicion
                low_suspects = [p for p in candidates if p.suspicion < 0.3 and not p.exposed_as_fake_seer]
                if low_suspects:
                    cand = rnd.choice(low_suspects)
                    sentence = rnd.choice(templates_defend).format(target=cand.user.display_name)
                    self_event = {"action": "defend", "target": cand}
                else:
                    sentence = rnd.choice(templates_other)
                    self_event = None
            else:
                sentence = rnd.choice(templates_other)
                self_event = None

        return f"**{self.user.display_name}**: {_(sentence)}", self_event

    def cast_vote(self, alive: List["SPPlayer"], rnd: random.Random) -> "SPPlayer | None":
        """AI vote during lynch. Returns target player or None to skip."""
        candidates = [p for p in alive if p != self]
        if not candidates:
            return None

        # Make sure werewolves don't vote against their own kind
        if self.role == Role.WEREWOLF:
            candidates = [p for p in candidates if p.role != Role.WEREWOLF]
            if not candidates:
                return None

        # Look for players who accused this AI player (defensive voting)
        accusers = []
        for message in self._temp_chat_log[-10:]:  # Check recent messages
            for candidate in candidates:
                # If this candidate accused the AI in a recent message
                if f"**{candidate.user.display_name}**" in message and (
                        f"sus" in message.lower() or
                        f"wolf" in message.lower() or
                        f"werewolf" in message.lower() or
                        f"suspicious" in message.lower() or
                        f"kill" in message.lower() or
                        f"lynch" in message.lower()
                ) and self.user.display_name.lower() in message.lower():
                    accusers.append(candidate)

        # Look for exposed fake seers - high priority targets
        fake_seers = [p for p in candidates if p.exposed_as_fake_seer]
        if fake_seers:
            # Almost always vote for exposed fake seers (95% chance)
            if rnd.random() < 0.95:
                return rnd.choice(fake_seers)

        # Look for players claiming to have found a werewolf
        claimed_werewolves = []
        for message in self._temp_chat_log[-15:]:
            for candidate in candidates:
                if "seer" in message.lower() and f"**{candidate.user.display_name}**" in message and "werewolf" in message.lower():
                    # Message indicates someone was identified as a werewolf by a seer
                    claimed_werewolves.append(candidate)

        # High priority for accused werewolves (unless we are the werewolf)
        if claimed_werewolves and self.role != Role.WEREWOLF and rnd.random() < 0.85:
            return rnd.choice(claimed_werewolves)

        # Hugo defensive voting - vote for anyone who accuses Hugo
        if self.user.display_name == "Hugo" and accusers:
            return rnd.choice(accusers)  # Always vote for someone who accused Hugo

        # More dynamic voting system based on role and suspicion
        if self.role == Role.WEREWOLF:
            # First vote for any accuser if present (wolves defend themselves)
            if accusers and rnd.random() < 0.85:
                return rnd.choice(accusers)

            # Second priority: vote for real Seer if discovered
            seer_candidates = [p for p in candidates if p.role == Role.SEER or p.claimed_role == Role.SEER]
            if seer_candidates and rnd.random() < 0.8:
                return rnd.choice(seer_candidates)

            # Werewolf strategy: vote for high-suspicion non-wolves to blend in
            valid_targets = [p for p in candidates if p.suspicion > 0.2]
            if not valid_targets:
                valid_targets = candidates  # Fallback

            # Weights favor moderately to highly suspicious players
            weights = [p.suspicion + 0.3 for p in valid_targets]
            if rnd.random() < 0.9:  # 90% chance to vote
                return rnd.choices(valid_targets, weights=weights, k=1)[0]
            return None  # Sometimes skip to seem less eager

        elif self.role == Role.SEER:
            # Seer votes confidently if they've found a wolf
            if self.last_inspect and self.last_inspect[1] == Role.WEREWOLF:
                target, _ = self.last_inspect
                if target in candidates and target.alive:
                    return target

            # Vote for accusers defensively
            if accusers and rnd.random() < 0.7:
                return rnd.choice(accusers)

            # Otherwise like regular villager but more confident
            suspects = [p for p in candidates if p.suspicion > 0.4 or p.exposed_as_fake_seer]
            if suspects:
                # Weighted by suspicion
                weights = [p.suspicion + (0.5 if p.exposed_as_fake_seer else 0) for p in suspects]
                return rnd.choices(suspects, weights=weights, k=1)[0]
            elif rnd.random() < 0.3:  # 30% chance to skip if no good suspects
                return None
            # Fallback - pick most suspicious anyway
            return max(candidates, key=lambda p: p.suspicion)

        else:  # Regular villager
            # Vote for accusers defensively
            if accusers and rnd.random() < 0.65:
                return rnd.choice(accusers)

            # Vote if there's someone suspicious enough
            suspects = [p for p in candidates if p.suspicion > 0.3 or p.exposed_as_fake_seer]
            if suspects:
                weights = [p.suspicion + (0.5 if p.exposed_as_fake_seer else 0) for p in suspects]
                # 85% chance to vote when there are good suspects
                if rnd.random() < 0.85:
                    return rnd.choices(suspects, weights=weights, k=1)[0]
                return None

            # Skip if nobody is really suspicious
            if rnd.random() < 0.7:  # 70% chance to skip when uncertain
                return None

            # Sometimes pick randomly even when uncertain
            return rnd.choice(candidates)


class SPGame:
    """A self-contained single-player Werewolf match."""

    def __init__(self, ctx: Context, total_players: int):
        self.ctx = ctx
        self.total_players = max(3, min(9, total_players))
        self.players: list[SPPlayer] = []
        self.rnd = random.Random()
        self.revealed_fake_seers = set()  # Track fake seers that have been exposed
        self.seer_claims: dict[int, tuple[SPPlayer, Role]] = {}  # user_id -> (target, claimed_role)
        self.first_seer_claimer = None  # Track who claimed to be Seer first
        self.used_names = set()  # Keep track of names already used in this game
        self._setup_players()

    # ------------------------------------------------------------------
    #  Setup & helpers
    # ------------------------------------------------------------------

    def _get_unique_name(self):
        """Get a random name that hasn't been used yet in this game."""
        available_names = [name for name in _NAMES if name not in self.used_names]

        # If we've used all names, add a numeric suffix to existing names
        if not available_names:
            suffix = 1
            while True:
                # Try names with numeric suffixes until we find an unused one
                for name in _NAMES:
                    new_name = f"{name} {suffix}"
                    if new_name not in self.used_names:
                        self.used_names.add(new_name)
                        return new_name
                suffix += 1

        # Otherwise use an available name
        name = self.rnd.choice(available_names)
        self.used_names.add(name)
        return name

    def _setup_players(self):
        human_member: discord.Member = self.ctx.author  # type: ignore[arg-type]
        self.players.append(
            SPPlayer(user=human_member, role=Role.VILLAGER, is_human=True)
        )

        # Better role distribution rules
        num_werewolves = 1  # Default for small games

        # Adjust werewolf count for larger games
        if self.total_players >= 8:
            num_werewolves = 2

        # Always have exactly 1 Seer if at least 4 players
        has_seer = self.total_players >= 4

        # Calculate remaining villagers
        num_villagers = self.total_players - 1 - num_werewolves
        if has_seer:
            num_villagers -= 1

        # Create role pool
        role_pool = [Role.WEREWOLF] * num_werewolves
        if has_seer:
            role_pool.append(Role.SEER)
        role_pool.extend([Role.VILLAGER] * num_villagers)

        self.rnd.shuffle(role_pool)

        # Create AI players with unique names
        for role in role_pool:
            uid = self.rnd.randint(1_000_000, 9_999_999)
            name = self._get_unique_name()  # Get unique name for this player
            ai_mem = AIMember(uid, name)
            self.players.append(SPPlayer(user=ai_mem, role=role, is_human=False))

        # Randomize human role last
        human_role = self.rnd.choice([Role.VILLAGER, Role.SEER, Role.WEREWOLF])
        self.players[0].role = human_role

        # Ensure we don't exceed the intended werewolf count
        if human_role == Role.WEREWOLF:
            # Remove one wolf from the AI if human got wolf role
            for i, p in enumerate(self.players[1:], 1):
                if p.role == Role.WEREWOLF:
                    self.players[i].role = Role.VILLAGER
                    break

        self.rnd.shuffle(self.players)

    # ------------------------------------------------------------------
    #  Helper methods for DM/Channel responses and debugging
    # ------------------------------------------------------------------

    async def _wait_for_response(self, timeout, player, specific_check=None):
        """
        Wait for a response in either DMs or the game channel.

        Args:
            timeout: How long to wait
            player: The SPPlayer who should respond
            specific_check: Optional additional check function

        Returns:
            The message or None if timed out
        """
        try:
            # Skip if player is not alive or not human
            if not player or not player.is_human or not player.alive:
                return None

            def check_message(m):
                # Basic check: correct author and either in game channel or DM
                basic_check = (
                        m.author.id == player.user.id and
                        (m.channel == self.ctx.channel or
                         isinstance(m.channel, discord.DMChannel) or
                         (not hasattr(m.channel, 'guild') or m.channel.guild is None))
                )

                # Apply additional check if provided
                if specific_check and basic_check:
                    return specific_check(m)
                return basic_check

            return await self.ctx.bot.wait_for(
                "message",
                timeout=timeout,
                check=check_message
            )
        except asyncio.TimeoutError:
            return None

    async def _debug(self, message):
        """Send debug messages to the channel if the author has the specified ID."""
        if self.ctx.author.id == 29517370649647516:
            await self._try_send(f"[DEBUG] {message}")
        else:
            print(f"[DEBUG] {message}")

    # ------------------------------------------------------------------
    #  Public entry point
    # ------------------------------------------------------------------

    async def run(self):  # noqa: C901 – high complexity is acceptable for toy game
        try:
            # Setup game
            await self._inform_roles()

            # Initial message about night
            await self._try_send(_("🌘 💤 **Night falls, the town is asleep...**"))
            await asyncio.sleep(5)  # Give time to read roles like original

            # IMPORTANT: Run Night 1 first before any day phase
            night_no = 1
            try:
                # Make sure Night 1 runs properly - ensure the wait times are shorter
                # and the Seer always gets to inspect someone
                deaths = await self._night_phase(night_no, first_night=True)
                # Debug info
                if deaths:
                    await self._debug(f"Night 1 returned deaths: {[d.user.display_name for d in deaths]}")
                else:
                    await self._debug(f"Night 1 returned no deaths")
            except Exception as e:
                await self._debug(f"Night 1 error: {str(e)}")
                await send_traceback(self.ctx, e)
                deaths = []

            # Check if game ended during first night (shouldn't happen but for safety)
            if await self._check_game_end():
                return

            # Main game loop continues with Day 1
            day_no = 1
            while True:
                # Day phase
                await self._try_send(_("**Day {day_count:.0f}**").format(day_count=day_no))

                try:
                    await self._day_phase(day_no, deaths)
                except Exception as e:
                    await self._debug(f"Day phase error: {str(e)}")
                    await send_traceback(self.ctx, e)

                if await self._check_game_end():
                    break

                # Night phase (night 2 and beyond)
                night_no += 1
                try:
                    deaths = await self._night_phase(night_no)
                    # Debug info
                    if deaths:
                        await self._debug(f"Night {night_no} returned deaths: {[d.user.display_name for d in deaths]}")
                    else:
                        await self._debug(f"Night {night_no} returned no deaths")
                except Exception as e:
                    await self._debug(f"Night phase error: {str(e)}")
                    await send_traceback(self.ctx, e)
                    deaths = []

                if await self._check_game_end():
                    break

                day_no += 1

        except Exception as e:
            await self._debug(f"Game error: {str(e)}")
            await send_traceback(self.ctx, e)
            await self._try_send(_("The game has ended due to an unexpected error."))

    # ------------------------------------------------------------------
    #  Phases
    # ------------------------------------------------------------------

    async def _inform_roles(self):
        """Inform players of their roles."""
        human = next((p for p in self.players if p.is_human), None)
        if human:
            try:
                # Find team information for werewolves
                wolf_team_info = ""
                if human.role == Role.WEREWOLF:
                    # Find other werewolves to inform the player
                    fellow_wolves = [p for p in self.players if p.role == Role.WEREWOLF and not p.is_human]
                    if fellow_wolves:
                        wolf_names = ", ".join(f"**{w.user.display_name}**" for w in fellow_wolves)
                        wolf_team_info = f"\n\n🐺 **Your Wolf Team:** {wolf_names}"
                    else:
                        wolf_team_info = "\n\n🐺 **Wolf Team:** You are the only werewolf!"

                # Create user-specific DM link
                dm_link = ""
                try:
                    dm_link = "https://discord.com/channels/@me/" + str(
                        human.user.dm_channel.id) if human.user.dm_channel else ""
                except (AttributeError, TypeError):
                    # If we can't get DM channel ID, we'll use a generic link
                    dm_link = "https://discord.com/channels/@me"

                # Detailed role descriptions with clear gameplay instructions
                role_details = {
                    Role.VILLAGER: (
                        "You are a **Villager** 👨‍🌾\n\n"
                        "**Your Goal**: Work with the village to identify and eliminate the Werewolf before they kill everyone.\n\n"
                        "**Your Abilities**:\n"
                        "- Vote during the day to eliminate suspicious players\n"
                        "- Discuss with other villagers to share information\n"
                        "- Use logic and deduction to identify the Werewolf\n\n"
                        "**Strategy Tips**:\n"
                        "- Pay attention to who makes accusations and why\n"
                        "- Look for inconsistencies in players' statements\n"
                        "- Innocent players usually want to discuss openly"
                    ),
                    Role.SEER: (
                        "You are a **Seer** 👁️\n\n"
                        "**Your Goal**: Use your supernatural insight to help the village identify the Werewolf.\n\n"
                        "**Your Abilities**:\n"
                        "- Each night, you can inspect ONE player to learn their true role\n"
                        "- You will receive a private message during night phases to use your ability\n"
                        "- During the day, you can subtly guide discussions based on your knowledge\n\n"
                        "**Strategy Tips**:\n"
                        "- Don't immediately reveal what you've learned - the wolf might target you!\n"
                        "- Only reveal yourself as Seer if absolutely necessary\n"
                        "- Try to inspect the most suspicious players first"
                    ),
                    Role.WEREWOLF: (
                            "You are a **Werewolf** 🐺\n\n"
                            "**Your Goal**: Eliminate the villagers one by one without being discovered.\n\n"
                            "**Your Abilities**:\n"
                            "- Each night, you can kill ONE player\n"
                            "- You will receive a private message during night phases to choose your victim\n"
                            "- During the day, blend in with the villagers to avoid suspicion\n\n"
                            "**Strategy Tips**:\n"
                            "- Act like a villager and join in suspecting others\n"
                            "- Consider claiming to be the Seer if challenged\n"
                            "- Target players who seem the most perceptive first" +
                            wolf_team_info
                    )
                }

                # Send detailed role information via DM
                await human.user.send(_(role_details.get(human.role, f"You are a **{human.role_name}**.")))

                # Also send a short confirmation in the main channel
                await self._try_send(_(
                    "{user}, check your DMs for your role information!"
                ).format(user=self.ctx.author.mention))

            except (discord.Forbidden, AttributeError):
                # Fallback if DM fails - less detailed but still informative
                basic_role_info = {
                    Role.VILLAGER: "You are a **Villager** 👨‍🌾. Find and eliminate the werewolf before it's too late!",
                    Role.SEER: "You are a **Seer** 👁️. Each night you can inspect a player to learn their true role.",
                    Role.WEREWOLF: "You are a **Werewolf** 🐺. Each night you can kill a villager. Don't get caught!"
                }
                await self._try_send(_(
                    "{user}, you are **{role}**. (couldn't DM you detailed information)\n{basic_info}"
                ).format(
                    user=self.ctx.author.mention,
                    role=human.role_name,
                    basic_info=basic_role_info.get(human.role, "")
                ))

    async def _day_phase(self, day_no: int, deaths=None):
        # Begin day with a clear announcement
        await self._try_send(_(f"🌤️ **Day {day_no} begins!**"))

        if deaths and deaths[0]:
            await self._try_send(_("The village mourns the loss of **{victim}**.").format(
                victim=deaths[0].user.display_name
            ))

            # Check if a player who claimed to be a Seer was killed
            victim = deaths[0]
            if victim.claimed_role == Role.SEER and victim.role != Role.SEER:
                # This was a fake seer who died!
                await self._try_send(_("It seems **{victim}** falsely claimed to be the Seer!").format(
                    victim=victim.user.display_name
                ))

            # Check if any Seer claims were proven wrong by the death
            for claimer_id, (target, claimed_role) in list(self.seer_claims.items()):
                # If a player claimed someone was a wolf who wasn't
                if claimed_role == Role.WEREWOLF and victim == target and victim.role != Role.WEREWOLF:
                    # Find the player who made the false claim
                    claimer = next((p for p in self.players if p.user.id == claimer_id), None)
                    if claimer and claimer.alive:
                        claimer.exposed_as_fake_seer = True
                        self.revealed_fake_seers.add(claimer_id)
                        await self._try_send(
                            _("**{claimer}** was caught lying about **{victim}** being a werewolf!").format(
                                claimer=claimer.user.display_name,
                                victim=victim.user.display_name
                            ))

        # AI chat - less frequent, more meaningful, with proper pacing
        await self._try_send(_(
            "The villagers gather in the town square to discuss what happened..."
        ))
        await asyncio.sleep(2)

        # --------------- DISCUSSION PHASE WITH PLAYER INTERACTIONS ---------------

        try:
            # Track the last few human messages to respond to
            human_messages = []
            human = next((p for p in self.players if p.is_human and p.alive), None)

            # Select a subset of AIs to speak each day
            alive_ai = self._alive_ai()
            num_speakers = min(4, len(alive_ai))
            speakers = self.rnd.sample(alive_ai, num_speakers) if len(alive_ai) > num_speakers else alive_ai

            # DISCUSSION TIMER: 45 seconds of open discussion time
            discussion_end = datetime.datetime.now() + datetime.timedelta(seconds=45)

            # Explain discussion phase to player
            if human and human.alive:
                await self._try_send(_(
                    "💬 Discussion time! You have 45 seconds to talk with the villagers.\n"
                    "**During this time, mention players by name** if you suspect them (or think they're innocent).\n"
                    "The AI villagers will respond to your accusations and theories!"
                ))
            else:
                await self._try_send(_(
                    "💬 The villagers begin to discuss what happened..."
                ))

            # Initialize first round of AI speech
            next_speaker_idx = 0
            next_speaker_time = datetime.datetime.now() + datetime.timedelta(seconds=self.rnd.uniform(3.0, 5.0))

            while datetime.datetime.now() < discussion_end:
                # Wait for human input with a short timeout - only if human is alive
                if human and human.alive:
                    try:
                        message = await asyncio.wait_for(
                            self.ctx.bot.wait_for(
                                "message",
                                check=lambda m: m.author == self.ctx.author and m.channel == self.ctx.channel
                            ),
                            timeout=1.0  # Short timeout to check our other conditions
                        )

                        # Human spoke! Process their message
                        human_messages.append(message)

                        # Check if message mentions any player by name (accusation or defense)
                        mentioned_players = []
                        for p in self._alive_players():
                            if p != human and p.user.display_name.lower() in message.content.lower():
                                mentioned_players.append(p)

                        # Check if human is claiming to be Seer
                        if "seer" in message.content.lower():
                            # If first Seer claim of the game, record it
                            if self.first_seer_claimer is None:
                                self.first_seer_claimer = human.user.id
                                # Give credibility boost for first claim
                                human.credibility += 0.15

                            if human.role != Role.SEER:
                                # Human is claiming to be a Seer but isn't
                                human.claimed_role = Role.SEER
                                # Record the claim but don't immediately expose
                                if "werewolf" in message.content.lower():
                                    # Find who they're accusing
                                    for p in self._alive_players():
                                        if p != human and p.user.display_name.lower() in message.content.lower():
                                            self.seer_claims[human.user.id] = (p, Role.WEREWOLF)
                                            # Increase suspicion but don't immediately expose
                                            p.suspicion += 0.5
                                            break
                            else:
                                # Real Seer is claiming - record this too
                                human.claimed_role = Role.SEER
                                if "werewolf" in message.content.lower() or "villager" in message.content.lower():
                                    for p in self._alive_players():
                                        if p != human and p.user.display_name.lower() in message.content.lower():
                                            role_found = Role.WEREWOLF if "werewolf" in message.content.lower() else Role.VILLAGER
                                            self.seer_claims[human.user.id] = (p, role_found)
                                            # Adjust suspicion accordingly
                                            if role_found == Role.WEREWOLF:
                                                p.suspicion += 0.6
                                            else:
                                                p.suspicion -= 0.3
                                            break

                        if mentioned_players:
                            # Message mentions one or more players by name
                            for mentioned in mentioned_players:
                                # Analyze message content for accusation or defense clues
                                msg_lower = message.content.lower()
                                is_accusation = any(word in msg_lower for word in
                                                    ["wolf", "werewolf", "evil", "suspicious", "lying", "liar"])
                                is_defense = any(
                                    word in msg_lower for word in ["innocent", "villager", "good", "trust", "honest"])

                                # Store message in chat log for AI to reference
                                for ai_player in self._alive_ai():
                                    ai_player._temp_chat_log.append(f"**{human.user.display_name}**: {message.content}")

                                if is_accusation:
                                    # Player accused someone - increase suspicion and trigger response
                                    mentioned.suspicion += 0.3

                                    # Have the accused player respond to defend themselves
                                    if not mentioned.is_human:
                                        # Choose response based on actual role
                                        await asyncio.sleep(self.rnd.uniform(1.5, 2.5))
                                        if mentioned.role == Role.WEREWOLF:
                                            # Wolf is defensive but tries to appear innocent
                                            wolf_defenses = [
                                                f"**{mentioned.user.display_name}**: Why are you accusing me, {human.user.display_name}? I'm a villager just like you!",
                                                f"**{mentioned.user.display_name}**: That's ridiculous. I'm not the werewolf, {human.user.display_name}. You're just trying to divert attention.",
                                                f"**{mentioned.user.display_name}**: You've got it all wrong, {human.user.display_name}. Maybe YOU'RE the werewolf?"
                                            ]
                                            await self._try_send(_(self.rnd.choice(wolf_defenses)))
                                        else:
                                            # Innocent villager is genuinely confused/upset
                                            innocent_defenses = [
                                                f"**{mentioned.user.display_name}**: I'm not the werewolf, {human.user.display_name}! I'm just trying to survive like everyone else.",
                                                f"**{mentioned.user.display_name}**: {human.user.display_name}, you're making a mistake. I'm on the village's side!",
                                                f"**{mentioned.user.display_name}**: Why would you think that, {human.user.display_name}? I haven't done anything suspicious!"
                                            ]
                                            await self._try_send(_(self.rnd.choice(innocent_defenses)))

                                elif is_defense:
                                    # Player defended someone - decrease suspicion and maybe get thanks
                                    mentioned.suspicion -= 0.2

                                    # 50% chance the defended player thanks the human
                                    if not mentioned.is_human and self.rnd.random() < 0.5:
                                        await asyncio.sleep(self.rnd.uniform(1.0, 2.0))
                                        thanks_responses = [
                                            f"**{mentioned.user.display_name}**: Thanks for the vote of confidence, {human.user.display_name}.",
                                            f"**{mentioned.user.display_name}**: At least someone here trusts me. Thank you, {human.user.display_name}.",
                                            f"**{mentioned.user.display_name}**: I appreciate that, {human.user.display_name}. I AM innocent, for what it's worth."
                                        ]
                                        await self._try_send(_(self.rnd.choice(thanks_responses)))

                        # Check if message indicates human's strategy or thoughts
                        if human and human.role == Role.WEREWOLF:
                            # Human is werewolf - have wolf AI potentially support their strategy
                            wolf_ai = next((p for p in self._alive_ai() if p.role == Role.WEREWOLF), None)
                            if wolf_ai and self.rnd.random() < 0.4:  # 40% chance to coordinate
                                await asyncio.sleep(self.rnd.uniform(2.0, 3.0))
                                wolf_agreement = [
                                    f"**{wolf_ai.user.display_name}**: I think {human.user.display_name} has a point there.",
                                    f"**{wolf_ai.user.display_name}**: {human.user.display_name} makes a good argument, we should listen.",
                                    f"**{wolf_ai.user.display_name}**: That's exactly what I was thinking too, {human.user.display_name}."
                                ]
                                await self._try_send(_(self.rnd.choice(wolf_agreement)))

                    except asyncio.TimeoutError:
                        pass  # No human message this round

                # Check if it's time for AI to speak
                if datetime.datetime.now() >= next_speaker_time and next_speaker_idx < len(speakers):
                    speaker = speakers[next_speaker_idx]

                    # Decide if AI should respond to human messages or make their own statement
                    if human_messages and human and human.alive and self.rnd.random() < 0.7:  # 70% chance to respond to player
                        # Respond to the most recent human message
                        recent_msg = human_messages[-1].content.lower()

                        if human.user.display_name.lower() in recent_msg and speaker.role == Role.WEREWOLF:
                            # Player mentioned themselves and this speaker is a wolf - maybe frame player
                            if self.rnd.random() < 0.4:  # 40% chance to try to frame human
                                suspicious_comments = [
                                    f"**{speaker.user.display_name}**: Actually, {human.user.display_name}, you've been acting a bit strange yourself.",
                                    f"**{speaker.user.display_name}**: Hmm, {human.user.display_name}, that's exactly what a werewolf would say to shift suspicion.",
                                    f"**{speaker.user.display_name}**: I'm not sure about {human.user.display_name}... something feels off there."
                                ]
                                await self._try_send(_(self.rnd.choice(suspicious_comments)))
                        else:
                            # General response to player discussion
                            response_templates = [
                                f"**{speaker.user.display_name}**: I see what you're saying, {human.user.display_name}.",
                                f"**{speaker.user.display_name}**: That's an interesting point, {human.user.display_name}.",
                                f"**{speaker.user.display_name}**: I've been thinking about what {human.user.display_name} said..."
                            ]
                            await self._try_send(_(self.rnd.choice(response_templates)))
                    else:
                        # Make a standard statement if not responding to player
                        text, event = speaker.day_sentence(self._alive_players(), self.rnd,
                                                           round_type="reaction" if next_speaker_idx < 2 else "strategic")
                        await self._try_send(text)

                        # Store message in every AI's chat log
                        for ai_player in self._alive_ai():
                            ai_player._temp_chat_log.append(text)

                        if event:
                            self._process_event(event, speaker)

                    # Set up next speaker
                    next_speaker_idx += 1
                    next_speaker_time = datetime.datetime.now() + datetime.timedelta(seconds=self.rnd.uniform(4.0, 7.0))

                # Small sleep to prevent tight loop
                await asyncio.sleep(0.1)

            # End of discussion announcement - MOVED OUTSIDE THE LOOP to prevent spamming
            await self._try_send(_("💬 **Discussion time is over!** Now it's time to vote."))
            await asyncio.sleep(1.5)

        except Exception as e:
            await self._debug(f"Chat round error: {str(e)}")
            await send_traceback(self.ctx, e)

        # Give clear voting instructions with a more detailed system
        await self._try_send(_("⏳ **Voting Phase!** You have 60 seconds to decide who to eliminate."))

        # Only prompt human for voting if they're alive
        if human and human.alive:
            await self._try_send(_(
                "Type a player's **name** to vote for them, or type `skip` to abstain.\n"
                "The votes will be tallied after everyone has had a chance to vote."
            ))
        else:
            await self._try_send(_("The villagers begin casting their votes..."))

        # Initialize voting tracking
        votes = {}
        has_human_voted = False
        human_vote_target = None

        # Give 30 seconds for initial voting window
        voting_end = datetime.datetime.now() + datetime.timedelta(seconds=30)

        # Immediately show vote prompt to the human player
        if human and human.alive:
            # Get vote options (exclude werewolf teammates if human is werewolf)
            vote_options = ""
            for target in self._alive_players():
                # Skip self and teammates if werewolf
                if target != human and not (human.role == Role.WEREWOLF and target.role == Role.WEREWOLF):
                    vote_options += f"• **{target.user.display_name}**\n"

            # Try to send voting options via DM first
            try:
                # Get direct link to DM channel
                dm_link = "https://discord.com/channels/@me"
                try:
                    if human.user.dm_channel and human.user.dm_channel.id:
                        dm_link = f"https://discord.com/channels/@me/{human.user.dm_channel.id}"
                except (AttributeError, TypeError):
                    pass

                # Send voting options to human player via DM
                game_link = f"https://discord.com/channels/{self.ctx.guild.id}/{self.ctx.channel.id}/{self.ctx.message.id}"
                await human.user.send(_(
                    "🔟 **Voting Phase:** Choose someone to eliminate.\n\n"
                    "Type their name here in DMs OR in the game channel to vote for them:\n{options}\n"
                    "You can also type `skip` to abstain.\n\n"
                    "[Return to Game]({link})"
                ).format(options=vote_options, link=game_link))

                # Notify in channel that DM was sent
                await self._try_send(_(
                    "🔟 **{player}**, check your [DMs]({dm_link}) for voting instructions!\n"
                    "You can vote either in DMs or here in the channel by typing a player's name."
                ).format(player=self.ctx.author.mention, dm_link=dm_link))
            except (discord.Forbidden, AttributeError):
                # If DM fails, just show in channel
                await self._try_send(_(
                    "🔟 **{player}**, choose someone to vote out by typing their name:\n{options}\n"
                    "Or type `skip` to abstain."
                ).format(player=self.ctx.author.mention, options=vote_options))

        # Wait for human vote while showing AI votes progressively
        while datetime.datetime.now() < voting_end and not has_human_voted:
            # Skip human voting if they're dead
            if not human or not human.alive:
                break

            try:
                # Check for human vote in BOTH DMs and channel
                message = await self._wait_for_response(1.0, human)

                if message:
                    # Process human vote
                    content = message.content.lower().strip()
                    if content == "skip":
                        await self._try_send(_("{player} has chosen to abstain from voting.").format(
                            player=self.ctx.author.mention
                        ))
                        has_human_voted = True
                    else:
                        # Try to match a player name
                        voted_player = None
                        for p in self._alive_players():  # Only vote for alive players
                            # Don't allow voting for self or teammates if werewolf
                            if (p != human and p.user.display_name.lower() in content and
                                    not (human.role == Role.WEREWOLF and p.role == Role.WEREWOLF)):
                                voted_player = p
                                break

                        if voted_player:
                            await self._try_send(_("{player} has voted to eliminate **{target}**!").format(
                                player=self.ctx.author.mention,
                                target=voted_player.user.display_name
                            ))
                            votes[human.user.id] = voted_player
                            human_vote_target = voted_player
                            has_human_voted = True
                        elif human.role == Role.WEREWOLF and any(
                                p.role == Role.WEREWOLF and p.user.display_name.lower() in content for p in
                                self._alive_players()):
                            # Human werewolf tried to vote for a teammate
                            if message.channel != self.ctx.channel:
                                await human.user.send(
                                    _("You can't vote to eliminate another werewolf! Choose someone else."))
                            else:
                                await self._try_send(
                                    _("{player}, you can't vote to eliminate another werewolf! Choose someone else.").format(
                                        player=self.ctx.author.mention
                                    ))
                        else:
                            # Invalid vote
                            # If in DMs, send error there, otherwise in channel
                            if message.channel != self.ctx.channel:
                                await human.user.send(_("That's not a valid player name. Please try again."))
                            else:
                                await self._try_send(
                                    _("{player}, that's not a valid player name. Please try again.").format(
                                        player=self.ctx.author.mention
                                    ))
                else:
                    # No human vote this second, maybe have an AI cast a vote
                    remaining_voters = [p for p in self._alive_ai() if p.user.id not in votes]
                    if remaining_voters and self.rnd.random() < 0.2:  # 20% chance each second
                        voter = self.rnd.choice(remaining_voters)
                        vote_target = voter.cast_vote(self._alive_players(), self.rnd)

                        if vote_target:
                            votes[voter.user.id] = vote_target
                            await self._try_send(_("{player} has voted to eliminate **{target}**!").format(
                                player=voter.user.display_name,
                                target=vote_target.user.display_name
                            ))
                        else:
                            # AI chose to skip
                            votes[voter.user.id] = None
                            await self._try_send(_("{player} has chosen to abstain from voting.").format(
                                player=voter.user.display_name
                            ))

                        # Short pause between AI votes
                        await asyncio.sleep(self.rnd.uniform(2.0, 3.0))
            except Exception as e:
                await self._debug(f"Error in vote processing: {str(e)}")
                await send_traceback(self.ctx, e)

            # Tiny sleep to prevent CPU hogging
            await asyncio.sleep(0.05)

        # If human hasn't voted and is alive, remind them
        if not has_human_voted and human and human.alive:
            await self._try_send(_("{player}, you have 15 seconds left to vote!").format(
                player=self.ctx.author.mention
            ))

            try:
                message = await self._wait_for_response(15, human)

                if message:
                    # Process last-chance human vote
                    content = message.content.lower().strip()
                    if content == "skip":
                        await self._try_send(_("{player} has chosen to abstain from voting.").format(
                            player=self.ctx.author.mention
                        ))
                    else:
                        # Try to match a player name
                        voted_player = None
                        for p in self._alive_players():  # Only vote for alive players
                            # Don't allow voting for self or teammates if werewolf
                            if (p != human and p.user.display_name.lower() in content and
                                    not (human.role == Role.WEREWOLF and p.role == Role.WEREWOLF)):
                                voted_player = p
                                break

                        if voted_player:
                            await self._try_send(_("{player} has voted to eliminate **{target}**!").format(
                                player=self.ctx.author.mention,
                                target=voted_player.user.display_name
                            ))
                            votes[human.user.id] = voted_player
                            human_vote_target = voted_player
                        elif human.role == Role.WEREWOLF and any(
                                p.role == Role.WEREWOLF and p.user.display_name.lower() in content for p in
                                self._alive_players()):
                            # Human werewolf tried to vote for a teammate
                            if message.channel != self.ctx.channel:
                                await human.user.send(
                                    _("You can't vote to eliminate another werewolf! Your vote has been skipped."))
                            else:
                                await self._try_send(
                                    _("{player}, you can't vote to eliminate another werewolf! Your vote has been skipped.").format(
                                        player=self.ctx.author.mention
                                    ))
                        else:
                            # Invalid vote
                            if message.channel != self.ctx.channel:
                                await human.user.send(_("That's not a valid player name. Your vote has been skipped."))
                            else:
                                await self._try_send(
                                    _("{player}, that's not a valid player name. Your vote has been skipped.").format(
                                        player=self.ctx.author.mention
                                    ))
                else:
                    await self._try_send(_("{player} didn't vote in time.").format(
                        player=self.ctx.author.mention
                    ))
            except Exception as e:
                await self._debug(f"Error in last-chance vote processing: {str(e)}")
                await send_traceback(self.ctx, e)

        # Make sure all ALIVE AIs have voted
        remaining_voters = [p for p in self._alive_ai() if p.user.id not in votes]

        # Improve werewolf coordination - wolves should vote together when possible
        ai_wolves = [p for p in remaining_voters if p.role == Role.WEREWOLF]
        ai_wolf_vote_target = None

        # First look for exposed fake Seers
        exposed_fake_seers = [p for p in self._alive_players() if p.exposed_as_fake_seer]
        if exposed_fake_seers:
            ai_wolf_vote_target = exposed_fake_seers[0]
        # Otherwise look for players claiming to be Seer
        elif not ai_wolf_vote_target:
            claimed_seers = [p for p in self._alive_players() if
                             p.claimed_role == Role.SEER and p.role != Role.WEREWOLF]
            if claimed_seers:
                ai_wolf_vote_target = claimed_seers[0]

        # If we have multiple AI wolves, they should coordinate
        if len(ai_wolves) > 1 and not ai_wolf_vote_target:
            # Wolves should try to vote together for a target
            # First find potential targets
            potential_targets = [p for p in self._alive_players() if p.role != Role.WEREWOLF]
            if potential_targets:
                # Try to target the Seer first if we can identify them
                seer_targets = [p for p in potential_targets if p.role == Role.SEER]
                if seer_targets:
                    ai_wolf_vote_target = seer_targets[0]  # Target the Seer!
                else:
                    # Otherwise pick the most suspicious villager
                    ai_wolf_vote_target = max(potential_targets, key=lambda p: p.suspicion)

        # If human player is a wolf, coordinate with them
        if human and human.alive and human.role == Role.WEREWOLF and human_vote_target:
            ai_wolf_vote_target = human_vote_target  # Follow human wolf's lead

        # Process all remaining AI votes with improved strategy
        for voter in remaining_voters:
            vote_target = None

            # Check if this is a werewolf
            if voter.role == Role.WEREWOLF:
                # First priority: exposed fake Seers
                if exposed_fake_seers and self.rnd.random() < 0.95:
                    vote_target = exposed_fake_seers[0]
                # Second priority: coordinated wolf target
                elif ai_wolf_vote_target and self.rnd.random() < 0.9:
                    vote_target = ai_wolf_vote_target
                # If human villager voted, maybe follow human
                elif human_vote_target and human and human.alive and human.role != Role.WEREWOLF and self.rnd.random() < 0.6:
                    vote_target = human_vote_target
                else:
                    vote_target = voter.cast_vote(self._alive_players(), self.rnd)
            else:
                # Non-werewolf voting
                # First priority for all players: exposed fake Seers
                if exposed_fake_seers and self.rnd.random() < 0.95:
                    vote_target = exposed_fake_seers[0]
                # Otherwise, use normal voting logic
                else:
                    vote_target = voter.cast_vote(self._alive_players(), self.rnd)

            if vote_target:
                votes[voter.user.id] = vote_target
                await self._try_send(_("{player} has voted to eliminate **{target}**!").format(
                    player=voter.user.display_name,
                    target=vote_target.user.display_name
                ))
            else:
                # AI chose to skip
                votes[voter.user.id] = None
                await self._try_send(_("{player} has chosen to abstain from voting.").format(
                    player=voter.user.display_name
                ))

            # Short pause between final AI votes
            await asyncio.sleep(self.rnd.uniform(0.7, 1.5))

        # Tally votes
        vote_count = {}
        for voter_id, target in votes.items():
            if target:  # None means abstain
                if target not in vote_count:
                    vote_count[target] = 0
                vote_count[target] += 1

        # Find most voted player (if any)
        most_voted = None
        max_votes = 0
        total_players = len(self._alive_players())
        majority_threshold = total_players // 2 + (1 if total_players % 2 == 1 else 0)  # Calculate majority

        for target, count in vote_count.items():
            if count > max_votes:
                most_voted = target
                max_votes = count
            elif count == max_votes and most_voted:
                # If tied, randomly select one (deterministic with seed)
                if self.rnd.random() < 0.5:
                    most_voted = target

        # Fix: Make has_majority use >= instead of > to allow simple majority
        # Standard werewolf rule: Half or more of the alive players must vote for someone
        has_majority = max_votes >= majority_threshold

        # Display vote summary
        await self._try_send(_("🗟️ **Voting Results:**"))
        if vote_count:
            vote_summary = "\n".join([f"**{target.user.display_name}**: {count} vote{'s' if count != 1 else ''}"
                                      for target, count in vote_count.items()])
            await self._try_send(vote_summary)
        else:
            await self._try_send(_("No one received any votes."))

        await asyncio.sleep(2)

        # Process vote outcome - need simple majority to lynch
        if most_voted and has_majority:
            # Someone voted to die
            await self._try_send(_("🔟 **{victim}** received the most votes and will be eliminated!").format(
                victim=most_voted.user.display_name
            ))

            # Let AI "plead" if they're about to be eliminated
            if not most_voted.is_human:
                # Choose appropriate plea based on role
                if most_voted.role == Role.WEREWOLF:
                    # Wolf tries desperately to appear innocent
                    wolf_pleas = [
                        f"**{most_voted.user.display_name}**: Wait! You're making a terrible mistake! I'm not the werewolf!",
                        f"**{most_voted.user.display_name}**: This is wrong! You're killing an innocent villager!",
                        f"**{most_voted.user.display_name}**: You fools! The real werewolf will kill you all tonight!"
                    ]
                    await self._try_send(_(self.rnd.choice(wolf_pleas)))
                else:
                    # Innocent AI expresses confusion/frustration
                    innocent_pleas = [
                        f"**{most_voted.user.display_name}**: No! I'm innocent! You're voting for the wrong person!",
                        f"**{most_voted.user.display_name}**: Please reconsider! I'm on the village's side!",
                        f"**{most_voted.user.display_name}**: This is a mistake... I'm not the wolf!"
                    ]
                    await self._try_send(_(self.rnd.choice(innocent_pleas)))
                await asyncio.sleep(2)  # Pause for dramatic effect

            # Last words if eliminated player is human
            if most_voted.is_human:
                await self._try_send(_("{player}, do you have any last words? You have 10 seconds.").format(
                    player=self.ctx.author.mention
                ))
                try:
                    await self._wait_for_response(10, most_voted)
                except Exception:
                    pass

            # Kill player and make sure they're properly eliminated
            most_voted.alive = False

            # Add dramatic effect
            await self._try_send(_("🔥 **{victim}** has been lynched by the village!").format(
                victim=most_voted.user.display_name
            ))
            await asyncio.sleep(1)

            # Reveal role on death
            if most_voted.role == Role.WEREWOLF:
                await self._try_send(
                    _("🐺 **{victim}** was a **Werewolf**! The village has won a small victory.").format(
                        victim=most_voted.user.display_name
                    ))
            else:
                await self._try_send(_("😔 **{victim}** was a **{role}**! An innocent villager has died.").format(
                    victim=most_voted.user.display_name,
                    role=most_voted.role.name.title()
                ))

            # Check if a fake Seer was lynched
            if most_voted.claimed_role == Role.SEER and most_voted.role != Role.SEER:
                await self._try_send(
                    _("The village discovered that **{victim}** was falsely claiming to be the Seer!").format(
                        victim=most_voted.user.display_name
                    ))

            # Check if any Seer claims were proven wrong by this lynch
            for claimer_id, (target, claimed_role) in list(self.seer_claims.items()):
                # If a player claimed someone was a wolf who wasn't
                if claimed_role == Role.WEREWOLF and most_voted == target and most_voted.role != Role.WEREWOLF:
                    # Find the player who made the false claim
                    claimer = next((p for p in self.players if p.user.id == claimer_id), None)
                    if claimer and claimer.alive:
                        claimer.exposed_as_fake_seer = True
                        self.revealed_fake_seers.add(claimer_id)
                        await self._try_send(
                            _("**{claimer}** was caught lying about **{victim}** being a werewolf!").format(
                                claimer=claimer.user.display_name,
                                victim=most_voted.user.display_name
                            ))

        else:
            # No one to eliminate - either no votes or no majority
            if not most_voted:
                await self._try_send(_("🔴 **No Lynch Today!** No one received any votes for elimination."))
            else:
                # There was a most voted player but not enough votes for majority
                await self._try_send(
                    _("🔴 **No Majority Reached!** **{victim}** received {count} votes, but at least {needed} votes were needed.").format(
                        victim=most_voted.user.display_name,
                        count=max_votes,
                        needed=majority_threshold
                    ))
            await self._try_send(_("The village remains uneasy as night approaches..."))

        # Short dramatic pause before night
        await asyncio.sleep(3)

    async def _night_phase(self, night_no: int, first_night=False):
        await self._try_send(_(f"🌙 **Night {night_no}. Everyone sleeps…**"))
        await asyncio.sleep(self.rnd.uniform(2, 3) if first_night else self.rnd.uniform(3, 5))

        # ------ SEER PHASE ------
        # Check specifically for human Seer first for night 1
        human_seer = next((p for p in self._alive_players() if p.is_human and p.role == Role.SEER), None)
        ai_seer = next((p for p in self._alive_players() if not p.is_human and p.role == Role.SEER), None)

        # Process human Seer first if exists
        if human_seer:
            # Announce in main channel
            await self._try_send(_("**The Seer awakes...**"))
            await asyncio.sleep(1)

            # Try to send instructions via DM first
            dm_sent = False
            try:
                # Get a direct DM link instead of a channel link
                dm_link = "https://discord.com/channels/@me"
                try:
                    if human_seer.user.dm_channel and human_seer.user.dm_channel.id:
                        dm_link = f"https://discord.com/channels/@me/{human_seer.user.dm_channel.id}"
                except (AttributeError, TypeError):
                    pass

                # Create a game channel link
                game_link = ""
                try:
                    game_link = f"https://discord.com/channels/{self.ctx.guild.id}/{self.ctx.channel.id}/{self.ctx.message.id}"
                except AttributeError:
                    pass

                # Get candidates for inspection (all alive players except the seer)
                candidates = [p for p in self._alive_players() if p != human_seer]
                candidate_list = "\n".join([f"• **{p.user.display_name}**" for p in candidates])

                # Different message depending on if we have a game link
                if game_link:
                    await human_seer.user.send(_(
                        "👁️ **Seer Action:** Choose someone to inspect.\n\n"
                        "Available players to inspect:\n{players}\n\n"
                        "Respond right here in DMs OR in the game channel with the person's name or `skip`\n\n"
                        "[Return to Game]({link})"
                    ).format(
                        players=candidate_list,
                        link=game_link
                    ))
                else:
                    await human_seer.user.send(_(
                        "👁️ **Seer Action:** Choose someone to inspect.\n\n"
                        "Available players to inspect:\n{players}\n\n"
                        "Respond either here in DMs or in the game channel with the person's name or `skip`"
                    ).format(
                        players=candidate_list
                    ))
                dm_sent = True
            except (discord.Forbidden, AttributeError):
                # DM failed, fall back to channel
                dm_sent = False

            # If DM failed or as a reminder, send a prompt to the channel
            if dm_sent:
                await self._try_send(_(
                    "👁️ **{player}**, check your [DMs]({dm_link}) for Seer instructions!\n"
                    "You can respond either in DMs or here in the channel."
                ).format(player=self.ctx.author.mention, dm_link=dm_link))
            else:
                # Clear instructions in channel as fallback
                await self._try_send(_("👁️ **{player}**, as the **Seer**, choose someone to inspect:").format(
                    player=self.ctx.author.mention
                ))

                # Show alive players to choose from
                candidates = [p for p in self._alive_players() if p != human_seer]
                candidate_list = "\n".join([f"• **{p.user.display_name}**" for p in candidates])
                await self._try_send(
                    _("Available players to inspect:\n{players}\n\nType a name to inspect, or `skip` to pass:").format(
                        players=candidate_list
                    ))

            # Wait for player's choice with shorter timeout on first night
            timeout = 20 if first_night else 30
            try:
                await self._debug(f"Waiting for Seer response from {self.ctx.author}")
                # Use the new helper method to wait for response in both DMs and channel
                msg = await self._wait_for_response(timeout, human_seer)

                if msg:
                    choice = msg.content.strip().lower()
                    if choice != "skip":
                        target = self._find_player_by_name(choice)
                        if not target:
                            # Invalid target
                            error_msg = _("Could not find that player. Your inspection has been skipped.")
                            # Send where the message came from
                            if msg.channel != self.ctx.channel:
                                await human_seer.user.send(error_msg)
                            else:
                                await self._try_send(error_msg)
                            target = None
                        else:
                            # Valid target
                            confirm_msg = _("*You will receive the inspection result privately.*")
                            if msg.channel != self.ctx.channel:
                                await human_seer.user.send(
                                    _("You have chosen to inspect **{player}**. Results coming soon...").format(
                                        player=target.user.display_name
                                    ))
                            await self._try_send(confirm_msg)
                    else:
                        skip_msg = _("You chose not to use your ability tonight.")
                        # Send where the message came from
                        if msg.channel != self.ctx.channel:
                            await human_seer.user.send(skip_msg)
                        else:
                            await self._try_send(skip_msg)
                        target = None
                else:
                    # Timed out
                    await self._try_send(_("You ran out of time and missed your chance to inspect someone."))
                    target = None

                # Send result to player
                if target:
                    await human_seer.user.send(_("**{player}** is a **{role}**.")
                                               .format(player=target.user.display_name, role=target.role_name))

                    # Record the inspection for future reference
                    human_seer.last_inspect = (target, target.role)

            except Exception as e:
                await self._debug(f"Error in Seer action: {str(e)}")
                await send_traceback(self.ctx, e)
                target = None
        # Process AI Seer if no human Seer
        elif ai_seer:
            # Announce in main channel
            await self._try_send(_("**The Seer awakes...**"))
            await asyncio.sleep(1)

            # AI Seer actions
            cand = [p for p in self._alive_players() if p != ai_seer]
            target = ai_seer.pick_target(cand)
            if target:
                ai_seer.last_inspect = (target, target.role)
                # Show AI activity without revealing targets
                await self._try_send(_("*The Seer examines someone's identity...*"))

        # Pause before next role
        await asyncio.sleep(2)

        # ------ WEREWOLF PHASE ------
        # Check specifically for human werewolf first
        human_wolf = next((p for p in self._alive_players() if p.is_human and p.role == Role.WEREWOLF), None)
        ai_wolf = next((p for p in self._alive_players() if not p.is_human and p.role == Role.WEREWOLF), None)

        victim: Optional[SPPlayer] = None

        # Process human werewolf first if exists
        if human_wolf:
            # Announce werewolf activity in main channel
            await self._try_send(_("**The Werewolf awakes, hungry for blood...**"))
            await asyncio.sleep(1)

            # Try to send instructions via DM first
            dm_sent = False
            try:
                game_link = f"https://discord.com/channels/{self.ctx.guild.id}/{self.ctx.channel.id}/{self.ctx.message.id}"

                # Get potential victims (no werewolves)
                candidates = [p for p in self._alive_players() if p != human_wolf and p.role != Role.WEREWOLF]

                # Add suspicion info to help player make informed decisions
                victim_details = []
                for p in candidates:
                    suspicion_level = "Low"
                    if p.suspicion > 0.7:
                        suspicion_level = "High"
                    elif p.suspicion > 0.4:
                        suspicion_level = "Medium"

                    # Check if this person is the Seer (if we have a hint)
                    seer_hint = ""
                    if p.role == Role.SEER:
                        # 30% chance to give a hint that this is the Seer
                        if self.rnd.random() < 0.3:
                            seer_hint = " (Possibly the Seer!)"
                    elif p.claimed_role == Role.SEER:
                        seer_hint = " (Claims to be Seer!)"

                    victim_details.append(f"• **{p.user.display_name}** - {suspicion_level} suspicion{seer_hint}")

                # Send wolf advice
                wolf_advice = "Consider killing someone with low suspicion to avoid detection."
                if any("Seer" in detail for detail in victim_details):
                    wolf_advice = "It might be wise to eliminate the suspected Seer if you can identify them!"

                await human_wolf.user.send(_(
                    "🐺 **Werewolf Action:** Choose someone to kill tonight.\n\n"
                    "Potential victims:\n{victims}\n\n"
                    "**Wolf Advice:** {advice}\n\n"
                    "Respond right here in DMs OR in the game channel with the person's name or `skip`\n\n"
                    "[Return to Game]({link})"
                ).format(
                    victims="\n".join(victim_details),
                    advice=wolf_advice,
                    link=game_link
                ))
                dm_sent = True
            except (discord.Forbidden, AttributeError):
                # DM failed, fall back to channel
                dm_sent = False

            # If DM failed or as a reminder, send a prompt to the channel
            if dm_sent:
                await self._try_send(_(
                    "🐺 **{player}**, check your DMs for Werewolf instructions!\n"
                    "You can respond either in DMs or here in the channel."
                ).format(player=self.ctx.author.mention))
            else:
                # Clear instructions in channel as fallback
                await self._try_send(_("🐺 **{player}**, as the **Werewolf**, choose someone to kill tonight:").format(
                    player=self.ctx.author.mention
                ))

                # Show list of potential victims
                candidates = [p for p in self._alive_players() if p != human_wolf and p.role != Role.WEREWOLF]
                victim_list = "\n".join([f"• **{p.user.display_name}**" for p in candidates])
                await self._try_send(
                    _("Potential victims:\n{players}\n\nType a name to kill, or `skip` to spare everyone tonight:").format(
                        players=victim_list
                    ))

            # Wait for player's choice with shorter timeout on first night
            timeout = 20 if first_night else 30
            try:
                # Use the new helper method to wait for response in both DMs and channel
                msg = await self._wait_for_response(timeout, human_wolf)

                if msg:
                    choice = msg.content.strip().lower()
                    if choice != "skip":
                        victim = self._find_player_by_name(choice)
                        # Check if victim is a werewolf teammate
                        if victim and victim.role == Role.WEREWOLF:
                            error_msg = _("You can't kill another werewolf! Choose someone else or type `skip`.")
                            if msg.channel != self.ctx.channel:
                                await human_wolf.user.send(error_msg)
                            else:
                                await self._try_send(error_msg)
                            victim = None
                        elif not victim:
                            # Invalid victim
                            error_msg = _("Could not find that player. You'll spare everyone tonight.")
                            # Send where the message came from
                            if msg.channel != self.ctx.channel:
                                await human_wolf.user.send(error_msg)
                            else:
                                await self._try_send(error_msg)
                            victim = None
                        else:
                            # Valid victim
                            confirm_msg = _(
                                "*Your victim has been selected. The village will discover the results in the morning...*")
                            if msg.channel != self.ctx.channel:
                                await human_wolf.user.send(_("You have chosen to kill **{player}** tonight.").format(
                                    player=victim.user.display_name
                                ))
                            await self._try_send(confirm_msg)
                    else:
                        skip_msg = _("You chose not to kill anyone tonight.")
                        # Send where the message came from
                        if msg.channel != self.ctx.channel:
                            await human_wolf.user.send(skip_msg)
                        else:
                            await self._try_send(skip_msg)
                        victim = None
                else:
                    # Timed out
                    await self._try_send(_("You ran out of time and missed your chance to kill someone."))
                    victim = None
            except Exception as e:
                await self._debug(f"Error in Werewolf action: {str(e)}")
                await send_traceback(self.ctx, e)
                victim = None
        # Process AI werewolf if no human werewolf
        elif ai_wolf:
            # Announce werewolf activity in main channel
            await self._try_send(_("**The Werewolf awakes, hungry for blood...**"))
            await asyncio.sleep(1)

            # AI Werewolf action - ensure we have valid candidates
            cand = [p for p in self._alive_players() if p.side != Side.WOLVES and p.alive]
            await self._debug(f"AI wolf candidates: {[p.user.display_name for p in cand]}")

            # Make sure we have candidates before trying to pick one
            if not cand:
                await self._debug(f"No valid wolf targets found - no one will die tonight")
                victim = None
            else:
                victim = ai_wolf.pick_target(cand)
                if victim:
                    # Show generic message about wolf activity
                    await self._try_send(_("*The Werewolf stalks through the village...*"))

        # Pause before wrapping up the night - shorter for first night
        await asyncio.sleep(2 if first_night else 3)
        await self._try_send(_("**Everyone falls back asleep...**"))
        await asyncio.sleep(self.rnd.uniform(5, 7) if first_night else self.rnd.uniform(10, 15))

        # Morning outcome
        await self._debug(f"Night {night_no} victim: {victim.user.display_name if victim else 'None'}")
        if victim:
            # Double-check the victim is still alive before killing them
            if victim.alive:
                victim.alive = False
                await self._try_send(_("💀 During the night **{victim}** was killed!").format(
                    victim=victim.user.display_name
                ))
            # Reveal role on death
            await self._try_send(_(
                "*The village discovers they were a **{role}**.*"
            ).format(role=victim.role_name))
            return [victim]  # Return deaths list like original
        else:
            await self._try_send(_("The night passed peacefully... Everyone is still alive."))

        await asyncio.sleep(1)
        return []  # Empty death list if no victim

    # ------------------------------------------------------------------
    #  Game end checks
    # ------------------------------------------------------------------

    async def _check_game_end(self) -> bool:
        """Return True if the game is over, with role reveal summary."""
        wolves_alive = [p for p in self._alive_players() if p.role == Role.WEREWOLF]
        villagers_alive = [p for p in self._alive_players() if p.role != Role.WEREWOLF]

        # Check winning conditions
        game_over = False
        if not wolves_alive:
            await self._try_send(_("🎉 **Villagers win!**"))
            game_over = True
        elif len(wolves_alive) >= len(villagers_alive):
            await self._try_send(_("🐺 **Werewolves win!**"))
            game_over = True

        # If game over, show role summary
        if game_over:
            await asyncio.sleep(1)
            await self._try_send(_("\n**Game Summary - Player Roles:**"))

            # Sort by role importance: Werewolf, Seer, then Villagers
            all_players = sorted(
                self.players,
                key=lambda p: (0 if p.role == Role.WEREWOLF else
                               (1 if p.role == Role.SEER else 2))
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
                await self._try_send(_(f"**Werewolves:**\n{wolf_list}"))

            if seers:
                seer_list = "\n".join(
                    [f"**{p.user.display_name}** {'(Alive)' if p.alive else '(Dead)'} {' - YOU' if p.is_human else ''}"
                     for p in seers])
                await self._try_send(_(f"**Seers:**\n{seer_list}"))

            if villagers:
                villager_list = "\n".join(
                    [f"**{p.user.display_name}** {'(Alive)' if p.alive else '(Dead)'} {' - YOU' if p.is_human else ''}"
                     for p in villagers])
                await self._try_send(_(f"**Villagers:**\n{villager_list}"))

            # Stats
            human = next((p for p in self.players if p.is_human), None)
            if human:
                result = "WON" if ((human.role != Role.WEREWOLF and not wolves_alive) or
                                   (human.role == Role.WEREWOLF and len(wolves_alive) >= len(
                                       villagers_alive))) else "LOST"
                await self._try_send(_(f"\nYou played as **{human.role_name}** and **{result}**!"))

            return True

        return False

    # ------------------------------------------------------------------
    #  Internal helpers
    # ------------------------------------------------------------------

    def _alive_players(self) -> List[SPPlayer]:
        return [p for p in self.players if p.alive]

    def _alive_ai(self) -> List[SPPlayer]:
        return [p for p in self._alive_players() if not p.is_human]

    def _alive_role(self, role: Role) -> Optional[SPPlayer]:
        return next((p for p in self._alive_players() if p.role == role), None)

    async def _last_human_msg(self) -> Optional[discord.Message]:
        history = [msg async for msg in self.ctx.channel.history(limit=20)]
        for msg in history:
            if msg.author == self.ctx.author:
                return msg
        return None

    def _find_player_by_name(self, txt: str) -> Optional[SPPlayer]:
        txt = txt.lower()
        for p in self._alive_players():
            if p.user.display_name.lower() in txt:
                return p
        return None

    # -------- Event processing  ---------

    def _process_event(self, event: dict, speaker: SPPlayer):
        action = event.get("action")
        if action == "reveal_inspect":
            target: SPPlayer = event["target"]
            role: Role = event["role"]

            # If first Seer claim of the game, record it and give credibility boost
            if self.first_seer_claimer is None:
                self.first_seer_claimer = speaker.user.id
                speaker.credibility += 0.15

            # Record the claim for later verification
            self.seer_claims[speaker.user.id] = (target, role)

            # Boost credibility of speaker - enhanced for Seers who provide accurate information
            # If the revealed role is correct (which it always is for real Seers), significant boost
            if speaker.role == Role.SEER:
                speaker.credibility = min(1.0, speaker.credibility + 0.3)  # Bigger boost for actual Seers
            else:
                # Someone claiming to be Seer but isn't gets a smaller boost
                speaker.credibility = min(1.0, speaker.credibility + 0.2)

            # Process how this affects other AI players' trust and suspicion
            for p in self._alive_ai():
                if p == speaker:
                    continue

                # Base trust level based on speaker's credibility
                trust = speaker.credibility

                # AI players are more likely to believe actual Seers (based on speech patterns)
                if speaker.role == Role.SEER:
                    trust = min(1.0, trust * 1.2)  # 20% extra trust multiplier for real Seers

                # Apply suspicion changes based on the reveal
                if role == Role.WEREWOLF:
                    # Revealed a werewolf - increase target's suspicion
                    target.suspicion += 0.5 * trust
                    # Also slightly increase trust in the Seer for future statements
                    if p.role != Role.WEREWOLF:  # Non-wolves trust Seers more
                        # Use getattr instead of dict.get since p is an SPPlayer instance
                        p._seer_trust = getattr(p, '_seer_trust', 0) + 0.1
                else:
                    # Cleared a player - decrease their suspicion
                    target.suspicion -= 0.4 * trust
        elif action == "fake_reveal":
            # Wolf made a fake Seer claim
            target: SPPlayer = event["target"]
            claimed_role: Role = event["claimed_role"]

            # If first Seer claim of the game, record it and give some credibility
            if self.first_seer_claimer is None:
                self.first_seer_claimer = speaker.user.id
                speaker.credibility += 0.15

            # Record the claim for later verification
            self.seer_claims[speaker.user.id] = (target, claimed_role)

            # If claiming target is a werewolf, significantly increase suspicion
            if claimed_role == Role.WEREWOLF:
                target.suspicion += 0.5

            # If claiming target is innocent, decrease suspicion
            else:
                target.suspicion -= 0.3

        elif action == "accuse":
            target: SPPlayer = event["target"]
            for p in self._alive_ai():
                if p == speaker:
                    continue
                influence = speaker.credibility * 0.2
                target.suspicion += influence
                # Slight chance accuser looks suspicious for over-accusing
                if target.role != Role.WEREWOLF:
                    speaker.suspicion += 0.05
        elif action == "defend":
            target: SPPlayer = event["target"]
            for p in self._alive_ai():
                if p == speaker:
                    continue
                influence = speaker.credibility * 0.15
                target.suspicion -= influence

        # Clamp suspicion values
        for ply in self._alive_players():
            ply.suspicion = min(max(ply.suspicion, 0.0), 1.0)

    # ------------------------------------------------------------------
    #  Safe send helper
    # ------------------------------------------------------------------

    async def _try_send(self, content: str):
        """Send to ctx channel but swallow any discord errors."""
        try:
            await self.ctx.send(content)
        except Exception as exc:  # pragma: no cover – just robustness
            print(f"ctx.send error: {exc}")

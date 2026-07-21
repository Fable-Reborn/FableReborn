"""The Relic Codex: permanent discoveries with long-term set mastery.

The original ``relics`` table remains the source of truth for first discoveries.
Repeat finds now build per-relic resonance, while failed eligible drops advance a
bounded pity counter.  Set rewards are claimed through an idempotent ledger so
catalog growth and concurrent drops cannot pay the same milestone twice.
"""

import asyncio
import logging
import random
from dataclasses import dataclass
from typing import Callable, Mapping

import discord
from discord.ext import commands

from classes.badges import Badge
from utils.checks import has_char


LOGGER = logging.getLogger(__name__)


# Source rates retain the original activity identity. Rarity then modifies the
# rate and supplies the hard pity ceiling. These are the primary drop knobs.
SOURCE_DROP_CHANCES = {
    "tower": 0.15,
    "dragon": 0.08,
    "raid": 0.05,
}

RARITY_RULES = {
    "rare": {
        "label": "Rare",
        "symbol": "◇",
        "colour": 0x3498DB,
        "chance_multiplier": 1.00,
        "pity": 12,
    },
    "epic": {
        "label": "Epic",
        "symbol": "◆",
        "colour": 0x9B59B6,
        "chance_multiplier": 0.85,
        "pity": 18,
    },
    "mythic": {
        "label": "Mythic",
        "symbol": "✦",
        "colour": 0xE67E22,
        "chance_multiplier": 0.70,
        "pity": 26,
    },
    "legendary": {
        "label": "Legendary",
        "symbol": "★",
        "colour": 0xF1C40F,
        "chance_multiplier": 0.55,
        "pity": 40,
    },
}

# Kept as public aliases for compatibility with code or tooling that imported
# the old tuning constants. Listeners no longer roll these values directly.
TOWER_DROP_CHANCE = SOURCE_DROP_CHANCES["tower"]
DRAGON_DROP_CHANCE = SOURCE_DROP_CHANCES["dragon"]
RAID_DROP_CHANCE = SOURCE_DROP_CHANCES["raid"]


# A set reaches a milestone only when every relic has this much resonance.
MASTERY_STAGES = (
    {"key": "recovered", "label": "Recovered", "copies": 1},
    {"key": "attuned", "label": "Attuned", "copies": 3},
    {"key": "exalted", "label": "Exalted", "copies": 7},
    {"key": "ascendant", "label": "Ascendant", "copies": 15},
)
MASTERY_BY_KEY = {stage["key"]: stage for stage in MASTERY_STAGES}

ALLOWED_REWARD_CRATES = frozenset(
    {
        "common",
        "uncommon",
        "rare",
        "magic",
        "legendary",
        "mystery",
        "fortune",
        "divine",
    }
)

# Stage-one payouts are unchanged. Later rewards are intentionally conservative
# and live in one catalog so balance changes do not touch reward logic.
SET_MILESTONE_REWARDS = {
    "frozen_throne": {
        "recovered": {"lp": 100, "crate": "fortune", "crate_amount": 1},
        "attuned": {"lp": 40, "crate": "rare", "crate_amount": 1},
        "exalted": {"lp": 75, "crate": "legendary", "crate_amount": 1},
        "ascendant": {"lp": 125, "crate": "fortune", "crate_amount": 1},
    },
    "tower_sigils": {
        "recovered": {"lp": 120, "crate": "fortune", "crate_amount": 1},
        "attuned": {"lp": 50, "crate": "rare", "crate_amount": 1},
        "exalted": {"lp": 90, "crate": "legendary", "crate_amount": 1},
        "ascendant": {"lp": 150, "crate": "fortune", "crate_amount": 1},
    },
    "divine_embers": {
        "recovered": {"lp": 150, "crate": "divine", "crate_amount": 1},
        "attuned": {"lp": 60, "crate": "rare", "crate_amount": 1},
        "exalted": {"lp": 110, "crate": "legendary", "crate_amount": 1},
        "ascendant": {"lp": 180, "crate": "divine", "crate_amount": 1},
    },
}


# Existing set and relic keys are deliberately unchanged for data compatibility.
RELIC_SETS = {
    "frozen_throne": {
        "name": "The Frozen Throne",
        "emoji": "❄️",
        "colour": 0x70B7E6,
        "lore": (
            "Relics taken from the sovereign horrors of the frozen wastes. "
            "Stronger dragons can also yield relics from earlier stages."
        ),
        "relics": {
            "wyrm_scale": {
                "name": "Frostbite Wyrm Scale",
                "source": "Slay the Frostbite Wyrm (stages 1-5)",
                "source_type": "dragon",
                "rarity": "rare",
            },
            "corrupted_heart": {
                "name": "Corrupted Heart of Ice",
                "source": "Slay the Corrupted Ice Dragon (stages 6-10)",
                "source_type": "dragon",
                "rarity": "epic",
            },
            "permafrost_shard": {
                "name": "Permafrost Shard",
                "source": "Slay Permafrost (stages 11-15)",
                "source_type": "dragon",
                "rarity": "epic",
            },
            "deathwing_talon": {
                "name": "Deathwing's Talon",
                "source": "Slay Absolute Zero or Deathwing",
                "source_type": "dragon",
                "rarity": "mythic",
            },
            "abyssal_eye": {
                "name": "Eye of the Abyssal Maw",
                "source": "Slay the Abyssal Maw (endless dragon stage)",
                "source_type": "dragon",
                "rarity": "legendary",
            },
        },
    },
    "tower_sigils": {
        "name": "Sigils of the Tower",
        "emoji": "🗼",
        "colour": 0xC6923B,
        "lore": "Seals carried down from the tower's six decisive thresholds.",
        "relics": {
            "sigil_5": {
                "name": "Sigil of the Fifth Floor",
                "source": "Clear tower floor 5",
                "source_type": "tower",
                "rarity": "rare",
            },
            "sigil_10": {
                "name": "Sigil of the Tenth Floor",
                "source": "Clear tower floor 10",
                "source_type": "tower",
                "rarity": "rare",
            },
            "sigil_15": {
                "name": "Sigil of the Fifteenth Floor",
                "source": "Clear tower floor 15",
                "source_type": "tower",
                "rarity": "epic",
            },
            "sigil_20": {
                "name": "Sigil of the Twentieth Floor",
                "source": "Clear tower floor 20",
                "source_type": "tower",
                "rarity": "epic",
            },
            "sigil_25": {
                "name": "Sigil of the Twenty-Fifth Floor",
                "source": "Clear tower floor 25",
                "source_type": "tower",
                "rarity": "mythic",
            },
            "sigil_30": {
                "name": "Sigil of the Summit",
                "source": "Clear tower floor 30",
                "source_type": "tower",
                "rarity": "legendary",
            },
        },
    },
    "divine_embers": {
        "name": "Divine Embers",
        "emoji": "⚔️",
        "colour": 0x8E5AC7,
        "lore": "Sparks of allegiance that survive even the fall of a god's foe.",
        "relics": {
            "ember_elysia": {
                "name": "Ember of Elysia",
                "source": "Win a raid as a follower of Elysia",
                "source_type": "raid",
                "rarity": "mythic",
            },
            "ember_sepulchure": {
                "name": "Ember of Sepulchure",
                "source": "Win a raid as a follower of Sepulchure",
                "source_type": "raid",
                "rarity": "mythic",
            },
            "ember_drakath": {
                "name": "Ember of Drakath",
                "source": "Win a raid as a follower of Drakath",
                "source_type": "raid",
                "rarity": "mythic",
            },
        },
    },
}

# Flat lookup: relic_key -> (set_key, relic definition)
RELIC_INDEX = {
    relic_key: (set_key, relic)
    for set_key, set_data in RELIC_SETS.items()
    for relic_key, relic in set_data["relics"].items()
}

DRAGON_STAGE_RELICS = {
    "Frostbite Wyrm": "wyrm_scale",
    "Corrupted Ice Dragon": "corrupted_heart",
    "Permafrost": "permafrost_shard",
    "Absolute Zero": "deathwing_talon",
    "Deathwing": "deathwing_talon",
    "Void Tyrant": "deathwing_talon",
    "The Abyssal Maw": "abyssal_eye",
}
DRAGON_RELIC_ORDER = tuple(RELIC_SETS["frozen_throne"]["relics"])
DRAGON_RELIC_POSITION = {
    relic_key: position for position, relic_key in enumerate(DRAGON_RELIC_ORDER)
}


@dataclass(frozen=True)
class RelicRoll:
    """Pure result of one eligible drop roll."""

    relic_key: str
    source: str
    chance: float
    pity_limit: int
    attempt: int
    roll_value: float
    success: bool
    pity_triggered: bool


@dataclass(frozen=True)
class RelicGrant:
    """Committed result of adding one resonance copy."""

    user_id: int
    relic_key: str
    resonance: int
    set_resonance: int
    discovered: bool
    milestone_keys: tuple[str, ...]
    pity_triggered: bool = False


@dataclass(frozen=True)
class RelicDropResult:
    """Database-facing result: every attempt has a roll, successes have a grant."""

    roll: RelicRoll
    grant: RelicGrant | None


def catalog_validation_errors() -> tuple[str, ...]:
    """Return catalog/config problems without touching Discord or the database."""

    errors = []
    seen = set()
    expected_stages = set(MASTERY_BY_KEY)
    for set_key, set_data in RELIC_SETS.items():
        rewards = SET_MILESTONE_REWARDS.get(set_key, {})
        missing_stages = expected_stages - set(rewards)
        if missing_stages:
            errors.append(f"{set_key}: missing rewards for {sorted(missing_stages)}")
        for milestone_key, reward in rewards.items():
            if milestone_key not in expected_stages:
                errors.append(f"{set_key}: unknown reward milestone {milestone_key}")
            crate = reward.get("crate")
            if crate not in ALLOWED_REWARD_CRATES:
                errors.append(f"{set_key}/{milestone_key}: invalid crate {crate!r}")
            if int(reward.get("lp", 0)) < 0 or int(reward.get("crate_amount", 0)) < 0:
                errors.append(f"{set_key}/{milestone_key}: rewards cannot be negative")
        for relic_key, relic in set_data.get("relics", {}).items():
            if relic_key in seen:
                errors.append(f"duplicate relic key: {relic_key}")
            seen.add(relic_key)
            if relic.get("rarity") not in RARITY_RULES:
                errors.append(f"{relic_key}: unknown rarity {relic.get('rarity')!r}")
            if relic.get("source_type") not in SOURCE_DROP_CHANCES:
                errors.append(
                    f"{relic_key}: unknown source type {relic.get('source_type')!r}"
                )
    return tuple(errors)


def drop_rule_for(relic_key: str, source: str) -> tuple[float, int]:
    """Return effective chance and pity ceiling for an eligible source."""

    try:
        _set_key, relic = RELIC_INDEX[relic_key]
    except KeyError as exc:
        raise ValueError(f"Unknown relic key: {relic_key}") from exc
    if source != relic["source_type"]:
        raise ValueError(
            f"Relic {relic_key} belongs to {relic['source_type']}, not {source}"
        )
    rarity = RARITY_RULES[relic["rarity"]]
    chance = SOURCE_DROP_CHANCES[source] * float(rarity["chance_multiplier"])
    return max(0.0, min(1.0, chance)), int(rarity["pity"])


def evaluate_relic_roll(
    relic_key: str,
    source: str,
    previous_pity_attempts: int,
    roll_value: float,
) -> RelicRoll:
    """Evaluate one roll deterministically; suitable for focused unit tests."""

    chance, pity_limit = drop_rule_for(relic_key, source)
    roll_value = float(roll_value)
    if not 0.0 <= roll_value <= 1.0:
        raise ValueError("roll_value must be between 0 and 1")
    attempt = max(0, int(previous_pity_attempts)) + 1
    pity_triggered = attempt >= pity_limit
    return RelicRoll(
        relic_key=relic_key,
        source=source,
        chance=chance,
        pity_limit=pity_limit,
        attempt=attempt,
        roll_value=roll_value,
        success=pity_triggered or roll_value < chance,
        pity_triggered=pity_triggered,
    )


def select_dragon_catchup_relic(
    stage_relic_key: str,
    progress: Mapping[str, Mapping],
) -> str:
    """Choose one stage-eligible Frozen relic deterministically.

    The current stage keeps priority while it is at the eligible minimum. Once
    it pulls ahead, stronger dragons can yield the least-resonant earlier relic.
    Among tied relics, the highest pity counter wins, then catalog order keeps
    the choice stable across processes and restarts.
    """

    if stage_relic_key not in DRAGON_RELIC_POSITION:
        raise ValueError(f"Unknown Frozen Throne stage relic: {stage_relic_key}")
    stage_position = DRAGON_RELIC_POSITION[stage_relic_key]
    eligible_keys = DRAGON_RELIC_ORDER[: stage_position + 1]

    def state(relic_key: str) -> tuple[int, int]:
        entry = progress.get(relic_key, {})
        return (
            max(0, int(entry.get("resonance", 0) or 0)),
            max(0, int(entry.get("pity_attempts", 0) or 0)),
        )

    minimum = min(state(relic_key)[0] for relic_key in eligible_keys)
    if state(stage_relic_key)[0] == minimum:
        return stage_relic_key

    candidates = [
        relic_key
        for relic_key in eligible_keys
        if state(relic_key)[0] == minimum
    ]
    return min(
        candidates,
        key=lambda relic_key: (
            -state(relic_key)[1],
            DRAGON_RELIC_POSITION[relic_key],
        ),
    )


def progress_bar(current: int, total: int, width: int = 10) -> str:
    """Compact, Discord-safe progress bar."""

    total = max(0, int(total))
    width = max(1, int(width))
    if total == 0:
        return "▱" * width
    current = max(0, min(int(current), total))
    filled = int(width * current / total)
    return "▰" * filled + "▱" * (width - filled)


def mastery_stage_for(minimum_resonance: int) -> dict | None:
    """Highest mastery stage reached by a set's minimum resonance."""

    current = None
    for stage in MASTERY_STAGES:
        if int(minimum_resonance) >= int(stage["copies"]):
            current = stage
    return current


def next_mastery_stage(minimum_resonance: int) -> dict | None:
    """Next unreached mastery stage, if one remains."""

    for stage in MASTERY_STAGES:
        if int(minimum_resonance) < int(stage["copies"]):
            return stage
    return None


def set_minimum_resonance(resonances: list[int] | tuple[int, ...]) -> int:
    """A set's mastery is gated by its least-resonant relic."""

    return min((max(0, int(value)) for value in resonances), default=0)


def milestone_resonance_progress(
    resonances: list[int] | tuple[int, ...], copies_required: int
) -> tuple[int, int]:
    """Readable aggregate progress while still enforcing copies on every relic."""

    copies_required = max(1, int(copies_required))
    values = [max(0, int(value)) for value in resonances]
    return (
        sum(min(value, copies_required) for value in values),
        copies_required * len(values),
    )


def format_reward(reward: Mapping) -> str:
    """Compact reward copy shared by Codex pages and announcements."""

    parts = []
    lp = int(reward.get("lp", 0))
    if lp:
        parts.append(f"{lp:,} LP")
    crate = reward.get("crate")
    amount = int(reward.get("crate_amount", 0))
    if crate and amount:
        suffix = "Crate" if amount == 1 else "Crates"
        parts.append(f"{amount} {str(crate).title()} {suffix}")
    return " · ".join(parts) or "No reward"


def _state_for_relic(
    relic_key: str,
    owned: set[str],
    progress: Mapping[str, Mapping],
) -> tuple[int, int]:
    entry = progress.get(relic_key, {})
    resonance = int(entry.get("resonance", 0) or 0)
    pity_attempts = int(entry.get("pity_attempts", 0) or 0)
    if relic_key in owned:
        resonance = max(1, resonance)
    return max(0, resonance), max(0, pity_attempts)


def codex_page_limit_errors(pages: list[discord.Embed]) -> tuple[str, ...]:
    """Validate the Discord limits relevant to these single-embed pages."""

    errors = []
    for page_number, embed in enumerate(pages, start=1):
        payload = embed.to_dict()
        title = str(payload.get("title", ""))
        description = str(payload.get("description", ""))
        footer = str(payload.get("footer", {}).get("text", ""))
        author = str(payload.get("author", {}).get("name", ""))
        fields = payload.get("fields", [])
        if len(title) > 256:
            errors.append(f"page {page_number}: title exceeds 256 characters")
        if len(description) > 4096:
            errors.append(f"page {page_number}: description exceeds 4096 characters")
        if len(footer) > 2048:
            errors.append(f"page {page_number}: footer exceeds 2048 characters")
        if len(fields) > 25:
            errors.append(f"page {page_number}: more than 25 fields")
        total = len(title) + len(description) + len(footer) + len(author)
        for field_number, field in enumerate(fields, start=1):
            name = str(field.get("name", ""))
            value = str(field.get("value", ""))
            total += len(name) + len(value)
            if len(name) > 256:
                errors.append(
                    f"page {page_number}, field {field_number}: name exceeds 256 characters"
                )
            if len(value) > 1024:
                errors.append(
                    f"page {page_number}, field {field_number}: value exceeds 1024 characters"
                )
        if total > 6000:
            errors.append(f"page {page_number}: total text exceeds 6000 characters")
    return tuple(errors)


def build_relic_codex_pages(
    owned: set[str],
    progress: Mapping[str, Mapping],
    claims: set[tuple[str, str]] | None = None,
    *,
    owner_name: str | None = None,
) -> list[discord.Embed]:
    """Build the overview and one mobile-friendly page per set without I/O."""

    owned = set(owned)
    claims = set(claims or ())
    states = {
        relic_key: _state_for_relic(relic_key, owned, progress)
        for relic_key in RELIC_INDEX
    }
    total_relics = len(RELIC_INDEX)
    recovered = sum(1 for resonance, _attempts in states.values() if resonance > 0)
    total_resonance = sum(resonance for resonance, _attempts in states.values())
    ascendant_copies = int(MASTERY_BY_KEY["ascendant"]["copies"])
    mastery_resonance = sum(
        min(resonance, ascendant_copies)
        for resonance, _attempts in states.values()
    )
    mastery_target = total_relics * ascendant_copies
    valid_claims = {
        (set_key, milestone_key)
        for set_key, milestone_key in claims
        if set_key in RELIC_SETS and milestone_key in MASTERY_BY_KEY
    }
    total_milestones = len(RELIC_SETS) * len(MASTERY_STAGES)

    overview = discord.Embed(
        title="✦ Relic Codex",
        description=(
            f"Codex resonance **{mastery_resonance}/{mastery_target}**  ·  "
            f"**{(mastery_resonance / mastery_target * 100):.0f}%**\n"
            f"`{progress_bar(mastery_resonance, mastery_target)}`\n"
            f"Recovered **{recovered}/{total_relics}**  ·  "
            f"Milestones **{len(valid_claims)}/{total_milestones}**\n"
            f"Lifetime resonance **{total_resonance:,}×**"
        ),
        colour=0xC9A44C,
    )
    if owner_name:
        overview.set_author(name=f"{owner_name}'s collection")

    overview.add_field(
        name="◆ Codex Honors",
        value=(
            "Exalt every set to qualify for the **Living Legend** shop badge.\n"
            "Ascend every set to earn the permanent **Relic Sovereign** badge."
        ),
        inline=False,
    )

    for set_key, set_data in RELIC_SETS.items():
        keys = list(set_data["relics"])
        resonances = [states[key][0] for key in keys]
        minimum = set_minimum_resonance(resonances)
        current = mastery_stage_for(minimum)
        upcoming = next_mastery_stage(minimum)
        current_label = current["label"] if current else "Unrecovered"
        lines = [f"**{current_label}** · minimum resonance **{minimum}×**"]
        if upcoming:
            current_resonance, target_resonance = milestone_resonance_progress(
                resonances, int(upcoming["copies"])
            )
            reward = SET_MILESTONE_REWARDS[set_key][upcoming["key"]]
            lines.extend(
                [
                    f"`{progress_bar(current_resonance, target_resonance)}` "
                    f"Resonance {current_resonance}/{target_resonance}",
                    f"Next **{upcoming['label']}** at {upcoming['copies']}× each "
                    f"· {format_reward(reward)}",
                ]
            )
        else:
            lines.extend(
                [
                    f"`{progress_bar(1, 1)}` Mastery complete",
                    "All set milestone rewards claimed.",
                ]
            )
        overview.add_field(
            name=f"{set_data['emoji']} {set_data['name']}",
            value="\n".join(lines),
            inline=False,
        )
    overview.set_footer(text=f"Page 1/{len(RELIC_SETS) + 1} · Select a set with the arrows")

    pages = [overview]
    for page_number, (set_key, set_data) in enumerate(RELIC_SETS.items(), start=2):
        keys = list(set_data["relics"])
        resonances = [states[key][0] for key in keys]
        minimum = set_minimum_resonance(resonances)
        current = mastery_stage_for(minimum)
        upcoming = next_mastery_stage(minimum)
        current_label = current["label"] if current else "Unrecovered"
        mastery_lines = [
            set_data["lore"],
            f"**Current · {current_label}**  |  Minimum resonance **{minimum}×**",
        ]
        if set_key == "frozen_throne":
            mastery_lines.append(
                "Stronger dragons can yield missing relics from earlier stages."
            )
        if upcoming:
            current_resonance, target_resonance = milestone_resonance_progress(
                resonances, int(upcoming["copies"])
            )
            reward = SET_MILESTONE_REWARDS[set_key][upcoming["key"]]
            mastery_lines.extend(
                [
                    f"`{progress_bar(current_resonance, target_resonance)}` "
                    f"**Resonance {current_resonance}/{target_resonance}**",
                    f"Next **{upcoming['label']}** · {upcoming['copies']}× each",
                    f"Reward · **{format_reward(reward)}**",
                ]
            )
        else:
            mastery_lines.extend(
                [
                    f"`{progress_bar(1, 1)}` **Ascendant mastery complete**",
                    "Every set milestone reward has been claimed.",
                ]
            )

        page = discord.Embed(
            title=f"{set_data['emoji']} {set_data['name']}",
            description="\n".join(mastery_lines),
            colour=int(set_data["colour"]),
        )
        if owner_name:
            page.set_author(name=f"{owner_name}'s Relic Codex")

        for relic_key, relic in set_data["relics"].items():
            resonance, pity_attempts = states[relic_key]
            rarity = RARITY_RULES[relic["rarity"]]
            _chance, pity_limit = drop_rule_for(relic_key, relic["source_type"])
            if resonance > 0:
                status = "✓"
                display_name = relic["name"]
                value = (
                    f"Resonance **{resonance}×** · Pity **{pity_attempts}/{pity_limit}**\n"
                    f"*Source · {relic['source']}*"
                )
            else:
                status = "◌"
                display_name = "Unknown Relic"
                value = (
                    f"**Locked** · Pity **{pity_attempts}/{pity_limit}**\n"
                    f"*Hint · {relic['source']}*"
                )
            page.add_field(
                name=(
                    f"{status} {rarity['symbol']} {rarity['label']} · {display_name}"
                ),
                value=value,
                inline=False,
            )
        page.set_footer(
            text=(
                f"Page {page_number}/{len(RELIC_SETS) + 1} · "
                "Repeat drops build resonance; pity resets on a find"
            )
        )
        pages.append(page)

    limit_errors = codex_page_limit_errors(pages)
    if limit_errors:
        raise ValueError("Invalid Relic Codex pages: " + "; ".join(limit_errors))
    return pages


def build_relic_drop_embed(grant: RelicGrant) -> discord.Embed:
    """Build one compact announcement for a find and any claimed milestones."""

    set_key, relic = RELIC_INDEX[grant.relic_key]
    set_data = RELIC_SETS[set_key]
    rarity = RARITY_RULES[relic["rarity"]]
    title_action = "Relic Recovered" if grant.discovered else "Relic Resonates"
    embed = discord.Embed(
        title=f"{rarity['symbol']} {rarity['label']} {title_action}",
        description=f"<@{grant.user_id}> found **{relic['name']}**.",
        colour=int(rarity["colour"]),
    )
    embed.add_field(
        name=f"{set_data['emoji']} {set_data['name']}",
        value=(
            f"Relic resonance **{grant.resonance}×** · "
            f"Set minimum **{grant.set_resonance}×**"
        ),
        inline=False,
    )
    if grant.pity_triggered:
        embed.add_field(
            name="Fate Answered",
            value="The pity threshold guaranteed this relic.",
            inline=False,
        )
    if grant.milestone_keys:
        lines = []
        for milestone_key in grant.milestone_keys:
            stage = MASTERY_BY_KEY[milestone_key]
            reward = SET_MILESTONE_REWARDS[set_key][milestone_key]
            lines.append(f"**{stage['label']}** · {format_reward(reward)}")
        embed.add_field(name="Mastery Unlocked", value="\n".join(lines), inline=False)
    embed.set_footer(text="Relic Codex · $relics")
    return embed


def build_relic_sovereign_embed(user_id: int) -> discord.Embed:
    """Build the one-time full-Codex prestige announcement."""

    embed = discord.Embed(
        title="✦ Relic Sovereign",
        description=(
            f"<@{int(user_id)}> has raised every Relic set to **Ascendant** mastery."
        ),
        colour=0xC9A44C,
    )
    embed.add_field(
        name="Permanent Honor",
        value="The **Relic Sovereign** profile badge has been unlocked.",
        inline=False,
    )
    embed.set_footer(text="The Codex is complete. Its discoveries remain permanent.")
    return embed


_catalog_errors = catalog_validation_errors()
if _catalog_errors:
    raise RuntimeError("Invalid Relic Codex catalog: " + "; ".join(_catalog_errors))


class RelicCodexView(discord.ui.View):
    """Small owner-only paginator that leaves the final page visible on timeout."""

    def __init__(self, ctx, pages: list[discord.Embed], *, timeout: float = 180):
        super().__init__(timeout=timeout)
        self.ctx = ctx
        self.pages = pages
        self.index = 0
        self.message = None
        self.allowed_user_ids = {int(ctx.author.id)}
        alt_invoker_id = getattr(ctx, "alt_invoker_id", None)
        if alt_invoker_id is not None:
            self.allowed_user_ids.add(int(alt_invoker_id))
        self._sync_buttons()

    def _sync_buttons(self):
        self.previous.disabled = self.index == 0
        self.overview.disabled = self.index == 0
        self.next.disabled = self.index >= len(self.pages) - 1

    async def start(self):
        self.message = await self.ctx.send(embed=self.pages[0], view=self)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if int(interaction.user.id) in self.allowed_user_ids:
            return True
        await interaction.response.send_message(
            "This Relic Codex belongs to another player.", ephemeral=True
        )
        return False

    async def _show(self, interaction: discord.Interaction):
        self._sync_buttons()
        await interaction.response.edit_message(embed=self.pages[self.index], view=self)

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        if self.message is not None:
            try:
                await self.message.edit(view=self)
            except (discord.HTTPException, discord.NotFound):
                pass

    @discord.ui.button(label="Previous", emoji="◀", style=discord.ButtonStyle.secondary)
    async def previous(
        self, interaction: discord.Interaction, _button: discord.ui.Button
    ):
        self.index = max(0, self.index - 1)
        await self._show(interaction)

    @discord.ui.button(label="Overview", style=discord.ButtonStyle.secondary)
    async def overview(
        self, interaction: discord.Interaction, _button: discord.ui.Button
    ):
        self.index = 0
        await self._show(interaction)

    @discord.ui.button(label="Next", emoji="▶", style=discord.ButtonStyle.primary)
    async def next(self, interaction: discord.Interaction, _button: discord.ui.Button):
        self.index = min(len(self.pages) - 1, self.index + 1)
        await self._show(interaction)


class Relics(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self._tables_ready = False
        self._table_lock = asyncio.Lock()

    @property
    def logger(self):
        return getattr(self.bot, "logger", LOGGER)

    async def ensure_tables(self):
        if self._tables_ready:
            return
        async with self._table_lock:
            if self._tables_ready:
                return
            async with self.bot.pool.acquire() as conn:
                async with conn.transaction():
                    await conn.execute(
                        """
                        CREATE TABLE IF NOT EXISTS relics (
                            user_id BIGINT NOT NULL,
                            relic_key TEXT NOT NULL,
                            obtained_at TIMESTAMP NOT NULL DEFAULT NOW(),
                            PRIMARY KEY (user_id, relic_key)
                        );
                        """
                    )
                    await conn.execute(
                        """
                        CREATE TABLE IF NOT EXISTS relic_progress (
                            user_id BIGINT NOT NULL,
                            relic_key TEXT NOT NULL,
                            resonance BIGINT NOT NULL DEFAULT 0 CHECK (resonance >= 0),
                            pity_attempts INTEGER NOT NULL DEFAULT 0 CHECK (pity_attempts >= 0),
                            updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
                            PRIMARY KEY (user_id, relic_key)
                        );
                        """
                    )
                    await conn.execute(
                        """
                        CREATE TABLE IF NOT EXISTS relic_milestone_claims (
                            user_id BIGINT NOT NULL,
                            set_key TEXT NOT NULL,
                            milestone_key TEXT NOT NULL,
                            claimed_at TIMESTAMP NOT NULL DEFAULT NOW(),
                            PRIMARY KEY (user_id, set_key, milestone_key)
                        );
                        """
                    )

                    # Every legacy discovery starts at one resonance. GREATEST is
                    # deliberately non-destructive if progress already exists.
                    await conn.execute(
                        """
                        INSERT INTO relic_progress (user_id, relic_key, resonance, pity_attempts)
                        SELECT user_id, relic_key, 1, 0
                        FROM relics
                        ON CONFLICT (user_id, relic_key) DO UPDATE
                        SET resonance = GREATEST(relic_progress.resonance, 1)
                        """
                    )

                    # Mark legacy-complete sets as already paid. This is a claim
                    # backfill only: it intentionally awards no crate or LP.
                    for set_key, set_data in RELIC_SETS.items():
                        relic_keys = list(set_data["relics"])
                        await conn.execute(
                            """
                            INSERT INTO relic_milestone_claims
                                (user_id, set_key, milestone_key)
                            SELECT r.user_id, $1, 'recovered'
                            FROM relics r
                            WHERE r.relic_key = ANY($2::TEXT[])
                            GROUP BY r.user_id
                            HAVING COUNT(DISTINCT r.relic_key) = $3
                            ON CONFLICT (user_id, set_key, milestone_key) DO NOTHING
                            """,
                            set_key,
                            relic_keys,
                            len(relic_keys),
                        )
            self._tables_ready = True

    async def cog_load(self):
        await self.ensure_tables()

    async def _legacy_cog(self):
        legacy = self.bot.get_cog("Legacy")
        if legacy is None:
            raise RuntimeError("Legacy cog is required for atomic relic rewards")
        ensure_tables = getattr(legacy, "ensure_tables", None)
        if ensure_tables is not None:
            await ensure_tables()
        return legacy

    async def _lock_set_progress(self, conn, user_id: int, set_key: str):
        """Create then lock every row in a set in stable order.

        Locking the whole set serializes simultaneous finds for different relics,
        preventing both missed and duplicate mastery claims across processes.
        """

        relic_keys = sorted(RELIC_SETS[set_key]["relics"])
        await conn.execute(
            """
            INSERT INTO relic_progress (user_id, relic_key, resonance, pity_attempts)
            SELECT $1, keys.relic_key,
                   CASE WHEN EXISTS (
                       SELECT 1 FROM relics r
                       WHERE r.user_id = $1 AND r.relic_key = keys.relic_key
                   ) THEN 1 ELSE 0 END,
                   0
            FROM UNNEST($2::TEXT[]) AS keys(relic_key)
            ON CONFLICT (user_id, relic_key) DO NOTHING
            """,
            user_id,
            relic_keys,
        )
        rows = await conn.fetch(
            """
            SELECT relic_key, resonance, pity_attempts
            FROM relic_progress
            WHERE user_id = $1 AND relic_key = ANY($2::TEXT[])
            ORDER BY relic_key
            FOR UPDATE
            """,
            user_id,
            relic_keys,
        )
        return {
            row["relic_key"]: {
                "resonance": int(row["resonance"] or 0),
                "pity_attempts": int(row["pity_attempts"] or 0),
            }
            for row in rows
        }

    async def _award_milestone_reward(
        self,
        conn,
        legacy,
        user_id: int,
        set_key: str,
        milestone_key: str,
    ):
        reward = SET_MILESTONE_REWARDS[set_key][milestone_key]
        crate = reward["crate"]
        crate_amount = int(reward["crate_amount"])
        if crate not in ALLOWED_REWARD_CRATES:
            raise RuntimeError(f"Unsafe relic reward crate: {crate}")
        if crate_amount:
            updated_profile = await conn.fetchval(
                f'UPDATE profile SET crates_{crate} = crates_{crate} + $1 '
                'WHERE "user" = $2 RETURNING "user"',
                crate_amount,
                user_id,
            )
            if updated_profile is None:
                raise RuntimeError(f"Cannot reward relic milestone: profile {user_id} missing")
        lp = int(reward["lp"])
        if lp:
            await legacy.award_points(user_id, lp, conn=conn)

    async def _grant_relic_sovereign_badge(self, user_id: int) -> bool:
        """Atomically grant the full-Codex badge once all sets are Ascendant."""

        user_id = int(user_id)
        set_keys = sorted(RELIC_SETS)
        async with self.bot.pool.acquire() as conn:
            async with conn.transaction():
                # The profile lock makes simultaneous final-set completions safe.
                profile_row = await conn.fetchrow(
                    'SELECT "badges" FROM profile WHERE "user" = $1 FOR UPDATE;',
                    user_id,
                )
                if profile_row is None:
                    return False

                raw_badges = profile_row["badges"]
                try:
                    current = Badge(0) if raw_badges is None else Badge.from_db(raw_badges)
                except Exception:
                    current = Badge(0)
                if current & Badge.RELIC_SOVEREIGN:
                    return False

                ascendant_sets = await conn.fetchval(
                    """
                    SELECT COUNT(DISTINCT set_key)
                    FROM relic_milestone_claims
                    WHERE user_id = $1
                      AND milestone_key = 'ascendant'
                      AND set_key = ANY($2::TEXT[])
                    """,
                    user_id,
                    set_keys,
                )
                if int(ascendant_sets or 0) < len(set_keys):
                    return False

                await conn.execute(
                    'UPDATE profile SET "badges" = $1 WHERE "user" = $2;',
                    (current | Badge.RELIC_SOVEREIGN).to_db(),
                    user_id,
                )
                return True

    async def _apply_copy_locked(
        self,
        conn,
        legacy,
        user_id: int,
        relic_key: str,
        set_key: str,
        set_progress: dict,
        *,
        pity_triggered: bool,
    ) -> RelicGrant:
        current = set_progress[relic_key]
        new_resonance = int(current["resonance"]) + 1
        await conn.execute(
            """
            UPDATE relic_progress
            SET resonance = $3, pity_attempts = 0, updated_at = NOW()
            WHERE user_id = $1 AND relic_key = $2
            """,
            user_id,
            relic_key,
            new_resonance,
        )
        set_progress[relic_key] = {
            "resonance": new_resonance,
            "pity_attempts": 0,
        }
        discovered = bool(
            await conn.fetchval(
                """
                INSERT INTO relics (user_id, relic_key)
                VALUES ($1, $2)
                ON CONFLICT (user_id, relic_key) DO NOTHING
                RETURNING TRUE
                """,
                user_id,
                relic_key,
            )
        )

        minimum = set_minimum_resonance(
            [entry["resonance"] for entry in set_progress.values()]
        )
        milestone_keys = []
        for stage in MASTERY_STAGES:
            if minimum < int(stage["copies"]):
                continue
            claimed = await conn.fetchval(
                """
                INSERT INTO relic_milestone_claims
                    (user_id, set_key, milestone_key)
                VALUES ($1, $2, $3)
                ON CONFLICT (user_id, set_key, milestone_key) DO NOTHING
                RETURNING milestone_key
                """,
                user_id,
                set_key,
                stage["key"],
            )
            if claimed:
                await self._award_milestone_reward(
                    conn, legacy, user_id, set_key, stage["key"]
                )
                milestone_keys.append(stage["key"])

        return RelicGrant(
            user_id=user_id,
            relic_key=relic_key,
            resonance=new_resonance,
            set_resonance=minimum,
            discovered=discovered,
            milestone_keys=tuple(milestone_keys),
            pity_triggered=pity_triggered,
        )

    async def _announce_and_dispatch(self, grant: RelicGrant, channel=None):
        if channel is not None:
            try:
                await channel.send(embed=build_relic_drop_embed(grant))
            except Exception:
                self.logger.exception("Failed to announce relic %s", grant.relic_key)

        set_key, _relic = RELIC_INDEX[grant.relic_key]
        for milestone_key in grant.milestone_keys:
            if milestone_key == "recovered":
                self.bot.dispatch(
                    "relic_set_completed", grant.user_id, set_key, channel
                )
            self.bot.dispatch(
                "relic_milestone_completed",
                grant.user_id,
                set_key,
                milestone_key,
                channel,
            )

        if "ascendant" in grant.milestone_keys:
            try:
                badge_awarded = await self._grant_relic_sovereign_badge(grant.user_id)
                if badge_awarded:
                    if channel is not None:
                        await channel.send(
                            embed=build_relic_sovereign_embed(grant.user_id)
                        )
                    self.bot.dispatch(
                        "relic_codex_completed", grant.user_id, channel
                    )
            except Exception:
                self.logger.exception(
                    "Failed to grant Relic Sovereign badge to user %s",
                    grant.user_id,
                )

    async def grant_relic(self, user_id: int, relic_key: str, channel=None):
        """Force one resonance copy, retaining the original public grant API."""

        if relic_key not in RELIC_INDEX:
            return False
        await self.ensure_tables()
        legacy = await self._legacy_cog()
        user_id = int(user_id)
        set_key, _relic = RELIC_INDEX[relic_key]
        async with self.bot.pool.acquire() as conn:
            async with conn.transaction():
                set_progress = await self._lock_set_progress(conn, user_id, set_key)
                grant = await self._apply_copy_locked(
                    conn,
                    legacy,
                    user_id,
                    relic_key,
                    set_key,
                    set_progress,
                    pity_triggered=False,
                )
        await self._announce_and_dispatch(grant, channel)
        return True

    async def _attempt_locked(
        self,
        conn,
        legacy,
        user_id: int,
        relic_key: str,
        source: str,
        set_key: str,
        set_progress: dict,
        random_value: float,
    ) -> RelicDropResult:
        """Resolve one roll while the owning set is already locked."""

        previous_attempts = set_progress[relic_key]["pity_attempts"]
        roll = evaluate_relic_roll(
            relic_key, source, previous_attempts, random_value
        )
        if not roll.success:
            await conn.execute(
                """
                UPDATE relic_progress
                SET pity_attempts = $3, updated_at = NOW()
                WHERE user_id = $1 AND relic_key = $2
                """,
                user_id,
                relic_key,
                roll.attempt,
            )
            return RelicDropResult(roll=roll, grant=None)

        grant = await self._apply_copy_locked(
            conn,
            legacy,
            user_id,
            relic_key,
            set_key,
            set_progress,
            pity_triggered=roll.pity_triggered,
        )
        return RelicDropResult(roll=roll, grant=grant)

    async def attempt_relic_drop(
        self,
        user_id: int,
        relic_key: str,
        source: str,
        channel=None,
        *,
        rng: Callable[[], float] | None = None,
    ) -> RelicDropResult:
        """Record an eligible attempt and grant a pity-aware resonance copy."""

        if relic_key not in RELIC_INDEX:
            raise ValueError(f"Unknown relic key: {relic_key}")
        await self.ensure_tables()
        legacy = await self._legacy_cog()
        user_id = int(user_id)
        set_key, _relic = RELIC_INDEX[relic_key]
        random_value = float((rng or random.random)())

        async with self.bot.pool.acquire() as conn:
            async with conn.transaction():
                set_progress = await self._lock_set_progress(conn, user_id, set_key)
                result = await self._attempt_locked(
                    conn,
                    legacy,
                    user_id,
                    relic_key,
                    source,
                    set_key,
                    set_progress,
                    random_value,
                )

        if result.grant is not None:
            await self._announce_and_dispatch(result.grant, channel)
        return result

    async def attempt_dragon_relic_drop(
        self,
        user_id: int,
        stage_relic_key: str,
        channel=None,
        *,
        rng: Callable[[], float] | None = None,
    ) -> RelicDropResult:
        """Attempt one stage-aware Frozen relic with atomic catch-up selection."""

        if stage_relic_key not in DRAGON_RELIC_POSITION:
            raise ValueError(f"Unknown Frozen Throne relic: {stage_relic_key}")
        await self.ensure_tables()
        legacy = await self._legacy_cog()
        user_id = int(user_id)
        set_key = "frozen_throne"
        random_value = float((rng or random.random)())

        async with self.bot.pool.acquire() as conn:
            async with conn.transaction():
                set_progress = await self._lock_set_progress(conn, user_id, set_key)
                relic_key = select_dragon_catchup_relic(
                    stage_relic_key, set_progress
                )
                result = await self._attempt_locked(
                    conn,
                    legacy,
                    user_id,
                    relic_key,
                    "dragon",
                    set_key,
                    set_progress,
                    random_value,
                )

        if result.grant is not None:
            await self._announce_and_dispatch(result.grant, channel)
        return result

    # --- Drop listeners -----------------------------------------------------

    @commands.Cog.listener()
    async def on_battletower_completion(
        self,
        ctx,
        success,
        level=None,
        level_name=None,
        name_value=None,
        minion1_name=None,
        minion2_name=None,
    ):
        if not success or not level or level % 5 != 0:
            return
        relic_key = f"sigil_{level}"
        if relic_key not in RELIC_INDEX:
            return
        try:
            await self.attempt_relic_drop(
                ctx.author.id, relic_key, "tower", ctx.channel
            )
        except Exception:
            self.logger.exception(
                "Tower relic attempt failed for user %s at floor %s",
                getattr(ctx.author, "id", None),
                level,
            )

    @commands.Cog.listener()
    async def on_icedragon_victory(self, ctx, party_members, stage_name, dragon_level):
        relic_key = DRAGON_STAGE_RELICS.get(stage_name)
        if not relic_key:
            return
        for member in party_members:
            try:
                await self.attempt_dragon_relic_drop(
                    member.id, relic_key, ctx.channel
                )
            except Exception:
                self.logger.exception(
                    "Dragon relic attempt failed for user %s at %s",
                    getattr(member, "id", None),
                    stage_name,
                )

    @commands.Cog.listener()
    async def on_raid_favor(self, ctx, participant_ids, success):
        if not success:
            return
        try:
            unique_ids = list(dict.fromkeys(int(user_id) for user_id in participant_ids))
            if not unique_ids:
                return
            await self.ensure_tables()
            async with self.bot.pool.acquire() as conn:
                rows = await conn.fetch(
                    'SELECT "user", god FROM profile '
                    'WHERE "user" = ANY($1) AND god IS NOT NULL',
                    unique_ids,
                )
            channel = getattr(ctx, "channel", None)
            for row in rows:
                relic_key = f"ember_{str(row['god']).lower()}"
                if relic_key not in RELIC_INDEX:
                    continue
                try:
                    await self.attempt_relic_drop(
                        row["user"], relic_key, "raid", channel
                    )
                except Exception:
                    self.logger.exception(
                        "Raid relic attempt failed for user %s", row["user"]
                    )
        except Exception:
            self.logger.exception("Failed to prepare raid relic attempts")

    # --- Commands -----------------------------------------------------------

    @commands.command(aliases=["relic", "codex2"])
    @has_char()
    async def relics(self, ctx):
        """Open your permanent Relic Codex and set-mastery collection."""
        try:
            await self.ensure_tables()
            async with self.bot.pool.acquire() as conn:
                owned_rows = await conn.fetch(
                    "SELECT relic_key FROM relics WHERE user_id = $1", ctx.author.id
                )
                progress_rows = await conn.fetch(
                    """
                    SELECT relic_key, resonance, pity_attempts
                    FROM relic_progress
                    WHERE user_id = $1
                    """,
                    ctx.author.id,
                )
                claim_rows = await conn.fetch(
                    """
                    SELECT set_key, milestone_key
                    FROM relic_milestone_claims
                    WHERE user_id = $1
                    """,
                    ctx.author.id,
                )
            owned = {row["relic_key"] for row in owned_rows}
            progress = {
                row["relic_key"]: {
                    "resonance": int(row["resonance"] or 0),
                    "pity_attempts": int(row["pity_attempts"] or 0),
                }
                for row in progress_rows
            }
            claims = {
                (row["set_key"], row["milestone_key"]) for row in claim_rows
            }
            # This also backfills the honor if an older completed Codex predates
            # the badge or if its original announcement could not be delivered.
            if await self._grant_relic_sovereign_badge(ctx.author.id):
                await ctx.send(embed=build_relic_sovereign_embed(ctx.author.id))
            owner_name = getattr(ctx.author, "display_name", str(ctx.author))
            pages = build_relic_codex_pages(
                owned, progress, claims, owner_name=owner_name
            )
            await RelicCodexView(ctx, pages).start()
        except Exception as e:
            await ctx.send(e)


async def setup(bot):
    await bot.add_cog(Relics(bot))

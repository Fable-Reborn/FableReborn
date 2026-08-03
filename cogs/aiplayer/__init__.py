"""Autonomous Densetsu player bridged through a private Discord channel."""

from __future__ import annotations

import asyncio
import datetime
import io
import json
import logging
import re
import uuid
from copy import copy
from dataclasses import dataclass
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

import discord
from discord.ext import commands, tasks

from classes.classes import (
    Bard,
    Beastmaster,
    Mage,
    Paladin,
    Paragon,
    Raider,
    Ranger,
    Reaper,
    Ritualist,
    SantasHelper,
    Tank,
    Thief,
    Warrior,
    from_string as class_from_string,
    get_class_evolves,
    get_first_evolution,
)
from classes.class_mastery import (
    GAUNTLET_ICE_DRAGON_MASTERY_DAILY_CAP,
    MASTERY_AWARDS,
    MASTERY_UNLOCK_LEVEL,
    MASTERY_UNLOCK_POINTS,
    claim_free_class_mastery,
    get_class_mastery,
    get_free_mastery_claim,
)
from classes.endgame import apply_item_progression_bonus, soulbound_level_from_xp
from classes.specs import RESPEC_COST, SPECS, describe_spec, specs_for_line
from cogs.aiplayer.strategy import (
    CLASS_KNOWLEDGE,
    choose_best_equipment,
    choose_best_pet,
    choose_weakest_egg,
    combat_health_state,
    egg_combat_score,
    evaluate_raid_matchup,
    favored_weapon_bonus_rules,
    is_valid_loadout,
    pet_combat_score,
    score_loadout,
)
from cogs.miscellaneous import DAILY_MILESTONE_REWARDS, DailyRewardAlreadyClaimed
from utils import misc as rpgtools
from utils.checks import is_gm


logger = logging.getLogger(__name__)

DENSETSU_USER_ID = 750016080302440710
FABLE_USER_ID = 1403785403651063909
EVENT_MARKER = "FABLE_AI_EVENT"
DECISION_MARKER = "FABLE_AI_DECISION"
SPEAK_MARKER = "FABLE_AI_SPEAK"
BRIDGE_CHANNEL_KEY = "aiplayer:bridge_channel_id"
ENABLED_KEY = "aiplayer:enabled"
TICK_LOCK_KEY = "aiplayer:tick_lock"
MAX_WAGER_PERCENT_KEY = "aiplayer:max_wager_percent"
DEFAULT_MAX_WAGER_PERCENT = 10
DEFAULT_CHARACTER_NAME = "Densetsu"
MAX_AUTOPLAY_ACTIONS = 6
AUTOPLAY_TICK_LOCK_SECONDS = 600
AUTOPLAY_DECISION_TIMEOUT_SECONDS = 180
# The human release dropdown waits 120s. Stay well inside that so a slow model
# never leaves the battle hanging longer than a player would have.
EGG_CAPACITY_DECISION_TIMEOUT_SECONDS = 45
# Only this player's Infernal Ritual prompts Densetsu to ask for a slot, and
# only this player's answer can admit it.
EVIL_RITUAL_HOST_USER_ID = 506379037690691595
EVIL_RITUAL_GOD = "Sepulchure"
# The ritual's own join window is about 15.5 minutes. Stop listening before it
# closes so a late confirmation can never race the participant roll call.
EVIL_RITUAL_CONFIRM_TIMEOUT_SECONDS = 840
EVIL_RITUAL_ASK_TIMEOUT_SECONDS = 45
EVIL_RITUAL_DEFAULT_ASK = (
    "The eclipse is yours to command. Let me kneel among your followers "
    "and lend my voice to the chant."
)
EVIL_RITUAL_DEFAULT_ACCEPTED = "Then I chant. Try to keep up."
EVIL_RITUAL_DEFAULT_REFUSED = (
    "Suit yourself. Enjoy the ritual one voice short — I'll be watching it "
    "stall from here."
)
# "no problem" and friends are agreement that happens to contain a refusal
# word, so they are stripped before the refusal test runs.
EVIL_RITUAL_FALSE_REFUSAL = re.compile(
    r"\bno[\s-]+(problem|worries|prob|probs|issue|issues|biggie)\b",
    re.IGNORECASE,
)
EVIL_RITUAL_REFUSAL = re.compile(
    r"\b(no|nah|nope|naw|never|denied|deny|refuse[ds]?|declin(?:e|ed|es)|"
    r"reject(?:ed|s)?|forbidden|banned|absolutely\s+not|no\s+way|"
    r"not\s+a\s+chance|piss\s+off|fuck\s+off|get\s+lost|go\s+away)\b",
    re.IGNORECASE,
)
BASIC_PET_FOOD_COST = 10_000
PET_CARE_MONEY_RESERVE = 50_000
PAID_RAID_UPGRADE_MONEY_RESERVE = 50_000
CLASS_CHANGE_COST = 5_000
CLASS_CHANGE_COOLDOWN_SECONDS = 3_600
CLASS_CHANGE_COOLDOWN_KEY = f"cd:{DENSETSU_USER_ID}:class"
CLASS_PLAN_KEY = f"aiplayer:{DENSETSU_USER_ID}:class_plan"
CLASS_CHANGE_PROPOSAL_KEY = f"aiplayer:{DENSETSU_USER_ID}:class_change_proposal"
CLASS_CHANGE_PROPOSAL_TTL_SECONDS = 6 * 3_600
ADVENTURE_BALANCED_SUCCESS_THRESHOLD = 80
PET_EMERGENCY_HUNGER = 20
PET_CARE_ACTION_KNOWLEDGE = {
    "feed": {
        "command": "pets feed <pet_id> basic",
        "base_cooldown_seconds": 3600,
        "cost": BASIC_PET_FOOD_COST,
        "effects": "+50 fullness, +25 happiness, +1 trust, and 665 base XP",
    },
    "pet": {
        "command": "pets pet <pet_id>",
        "base_cooldown_seconds": 300,
        "cost": 0,
        "effects": "+5 or +10 happiness, +0 or +1 trust, and +50 base XP",
    },
    "play": {
        "command": "pets play <pet_id>",
        "base_cooldown_seconds": 300,
        "cost": 0,
        "effects": "+25 happiness, +1 trust, and +200 base XP",
    },
    "treat": {
        "command": "pets treat <pet_id>",
        "base_cooldown_seconds": 600,
        "cost": 0,
        "effects": "+50 happiness, +5 trust, and +500 base XP",
    },
    "train": {
        "command": "pets train <pet_id>",
        "base_cooldown_seconds": 1800,
        "cost": 0,
        "effects": "+2 trust and +1000 base XP",
    },
}
CRATE_RARITIES = (
    "common",
    "uncommon",
    "rare",
    "magic",
    "legendary",
    "divine",
    "mystery",
    "fortune",
    "materials",
)
CRATE_KNOWLEDGE = {
    "common": "Creates equipment with low-to-moderate stats.",
    "uncommon": "Creates equipment stronger on average than common crates.",
    "rare": "Creates mid-tier equipment.",
    "magic": "Creates high-tier equipment.",
    "legendary": "Creates very strong equipment and can award Dragon Coins.",
    "divine": "Creates the strongest ordinary crate equipment and can award Dragon Coins.",
    "mystery": "Converts into one random non-mystery crate.",
    "fortune": "Awards either level-scaled XP or a large amount of gold.",
    "materials": "Awards crafting materials instead of equipment.",
}
BOOSTER_KNOWLEDGE = {
    "time": "Halves adventure duration; activate before starting an adventure.",
    "luck": "Raises adventure success chance by 25%; it matters when the adventure resolves.",
    "money": "Raises adventure gold rewards by 25%; it matters when the adventure resolves.",
}

RACE_KNOWLEDGE = {
    "Human": {
        "attack_bonus": 2,
        "defense_bonus": 2,
        "summary": "Balanced teamwork and equal attack and defense.",
    },
    "Dwarf": {
        "attack_bonus": 1,
        "defense_bonus": 3,
        "summary": "A defensive forge-master with a small attack bonus.",
    },
    "Elf": {
        "attack_bonus": 3,
        "defense_bonus": 1,
        "summary": "An agile, attack-oriented nature fighter.",
    },
    "Orc": {
        "attack_bonus": 0,
        "defense_bonus": 4,
        "summary": "A heavily defensive race with no attack bonus.",
    },
    "Jikill": {
        "attack_bonus": 4,
        "defense_bonus": 0,
        "summary": "A heavily offensive race with no defense bonus.",
    },
    "Djinn": {
        "attack_bonus": 5,
        "defense_bonus": -1,
        "summary": "Maximum offense at the cost of one defense point.",
    },
    "Shadeborn": {
        "attack_bonus": -1,
        "defense_bonus": 5,
        "summary": "Maximum defense at the cost of one attack point.",
    },
}

PLAYABLE_CLASSES = {
    "bard": Bard,
    "beastmaster": Beastmaster,
    "mage": Mage,
    "paladin": Paladin,
    "raider": Raider,
    "ranger": Ranger,
    "ritualist": Ritualist,
    "tank": Tank,
    "thief": Thief,
    "warrior": Warrior,
}

ALL_KNOWN_CLASSES = {
    **PLAYABLE_CLASSES,
    "paragon": Paragon,
    "reaper": Reaper,
    "santashelper": SantasHelper,
}
CLASS_EVOLUTION_LEVELS = (0, 5, 10, 15, 20, 25, 30)


def available_player_classes(profile: Any) -> dict[str, type]:
    """Return class lines the current profile is genuinely allowed to select."""
    available = dict(PLAYABLE_CLASSES)
    tier = int(profile["tier"] or 0)
    if tier > 0:
        available["paragon"] = Paragon
    if bool(profile["spookyclass"]) or tier == 4:
        available["reaper"] = Reaper
    if bool(profile["chrissy2023"]) or tier == 4:
        available["santashelper"] = SantasHelper
    return available


def class_keys_for_evolution(class_name: str) -> set[str]:
    """Return every possible line for an evolution name, including aliases."""
    normalized = str(class_name or "").replace(" ", "").casefold()
    return {
        key
        for key, class_type in ALL_KNOWN_CLASSES.items()
        if any(
            evolution.class_name().replace(" ", "").casefold() == normalized
            for evolution in get_class_evolves(class_type)
        )
    }


def class_knowledge_payload(available_classes: dict[str, type]) -> dict[str, Any]:
    """Attach authoritative evolution and specialization roadmaps to each class."""
    payload = {}
    for key, class_type in ALL_KNOWN_CLASSES.items():
        knowledge = dict(CLASS_KNOWLEDGE[key])
        line_name = class_type.__name__
        knowledge.update(
            {
                "class_line": line_name,
                "selectable_now": key in available_classes,
                "evolution_path": [
                    {
                        "grade": index + 1,
                        "required_character_level": CLASS_EVOLUTION_LEVELS[index],
                        "name": evolution.class_name(),
                    }
                    for index, evolution in enumerate(get_class_evolves(class_type))
                ],
                "future_specializations": [
                    {
                        "spec_key": spec_key,
                        "name": spec["name"],
                        "kind": spec["kind"],
                        "passive": spec["passive"],
                        "effect_at_final_evolution": describe_spec(spec_key, 7),
                        "effect_formula": dict(spec["effect"]),
                        "supported_battle_engines": list(spec["engines"]),
                    }
                    for spec_key, spec in specs_for_line(line_name).items()
                ],
            }
        )
        payload[key] = knowledge
    return payload


def class_choice_options(
    *,
    class_names: list[str],
    slots: list[int],
    available_classes: dict[str, type],
    level: int,
    cost: int,
) -> list[dict[str, Any]]:
    """Return exact legal slot/class pairs instead of an unsafe Cartesian product."""
    unlocked_index = min(6, max(0, int(level)) // 5)
    options = []
    for slot in slots:
        other_keys = set()
        for index, class_name in enumerate(class_names[:2]):
            if index != slot:
                other_keys.update(class_keys_for_evolution(class_name))
        current_name = class_names[slot]
        current_keys = class_keys_for_evolution(current_name)
        for key, class_type in available_classes.items():
            if key in other_keys or key in current_keys:
                continue
            evolutions = get_class_evolves(class_type)
            options.append(
                {
                    "slot": slot,
                    "class": key,
                    "class_line": class_type.__name__,
                    "replaces": current_name,
                    "cost": int(cost),
                    "starts_as": evolutions[0].class_name(),
                    "highest_currently_unlocked_after_evolve": evolutions[
                        min(unlocked_index, len(evolutions) - 1)
                    ].class_name(),
                }
            )
    return options


def hypothetical_class_equipment_fit(
    *,
    items: list[dict[str, Any]],
    current_item_ids: list[int],
    class_names: list[str],
    slot: int,
    replacement_class_name: str,
) -> dict[str, Any]:
    """Score the full owned inventory under a proposed class replacement."""
    hypothetical_classes = list(class_names[:2])
    while len(hypothetical_classes) < 2:
        hypothetical_classes.append("No Class")
    hypothetical_classes[slot] = replacement_class_name
    current_ids = {int(item_id) for item_id in current_item_ids}
    current_items = [item for item in items if int(item["id"]) in current_ids]
    current_build_best = choose_best_equipment(items, class_names, current_ids)
    hypothetical_best = choose_best_equipment(
        items, hypothetical_classes, current_ids
    )
    equipped_under_hypothetical = (
        score_loadout(current_items, hypothetical_classes)
        if current_items
        else {"score": 0, "class_weapon_bonus_damage": 0, "class_weapon_bonus_armor": 0}
    )

    item_by_id = {int(item["id"]): item for item in items}
    best_ids = list((hypothetical_best or {}).get("item_ids", []))

    def item_summary(item: dict[str, Any]) -> dict[str, Any]:
        replacement_only = score_loadout([item], [replacement_class_name])
        return {
            "id": int(item["id"]),
            "name": str(item.get("name") or "Unknown item"),
            "type": str(item.get("type") or "Unknown"),
            "hand": str(item.get("hand") or "any"),
            "effective_damage_before_class_bonus": round(
                float(item.get("effective_damage", item.get("damage", 0)) or 0), 2
            ),
            "effective_armor_before_class_bonus": round(
                float(item.get("effective_armor", item.get("armor", 0)) or 0), 2
            ),
            "replacement_class_bonus_damage": replacement_only[
                "class_weapon_bonus_damage"
            ],
            "replacement_class_bonus_armor": replacement_only[
                "class_weapon_bonus_armor"
            ],
            "favored_by_replacement": bool(
                replacement_only["class_weapon_bonus_damage"]
                or replacement_only["class_weapon_bonus_armor"]
            ),
        }

    favored_owned = []
    for item in items:
        summary = item_summary(item)
        if summary["favored_by_replacement"]:
            summary["equipped_now"] = int(item["id"]) in current_ids
            favored_owned.append(summary)
    favored_owned.sort(
        key=lambda item: (
            item["effective_damage_before_class_bonus"]
            + item["effective_armor_before_class_bonus"]
            + item["replacement_class_bonus_damage"]
            + item["replacement_class_bonus_armor"]
        ),
        reverse=True,
    )

    current_best_score = float((current_build_best or {}).get("score", 0) or 0)
    hypothetical_best_score = float((hypothetical_best or {}).get("score", 0) or 0)
    return {
        "resulting_classes": hypothetical_classes,
        "equipped_loadout_under_replacement": equipped_under_hypothetical,
        "best_owned_loadout_under_replacement": hypothetical_best,
        "best_owned_loadout_items": [
            item_summary(item_by_id[item_id])
            for item_id in best_ids
            if item_id in item_by_id
        ],
        "favored_owned_items": favored_owned[:2],
        "equipped_favored_item_count": sum(
            1 for item in favored_owned if item["equipped_now"]
        ),
        "best_loadout_score_delta_vs_current_class_build": round(
            hypothetical_best_score - current_best_score, 2
        ),
        "uses_full_owned_inventory": True,
        "score_scope": (
            "Exact equipment, Starforge, Soulbound, hand, and favored-weapon fit only; "
            "compare class_knowledge separately for combat and utility mechanics."
        ),
    }


def class_pet_fit(
    class_key: str, *, level: int, pet_state: dict[str, Any]
) -> dict[str, Any]:
    """Make the Ranger/Beastmaster pet distinction explicit for class decisions."""
    pets = list(pet_state.get("pets") or [])
    recommended_id = pet_state.get("recommended_combat_pet_id")
    active = next((pet for pet in pets if pet.get("equipped")), None)
    if active is None and recommended_id is not None:
        active = next(
            (pet for pet in pets if int(pet.get("id", 0)) == int(recommended_id)),
            None,
        )
    grade = min(7, max(1, int(level) // 5 + 1))
    active_summary = (
        {
            "id": int(active["id"]),
            "name": str(active.get("name") or active.get("species") or "Pet"),
            "hp": int(active.get("hp", 0) or 0),
            "attack": int(active.get("attack", 0) or 0),
            "defense": int(active.get("defense", 0) or 0),
            "combat_score": float(active.get("combat_score", 0) or 0),
        }
        if active is not None
        else None
    )
    result = {
        "active_or_recommended_pet": active_summary,
        "has_combat_pet": active is not None,
        "direct_pet_stat_multiplier": 1.0,
        "direct_pet_combat_bonus": False,
        "pet_collection_utility": False,
    }
    if class_key == "beastmaster":
        multiplier = 1 + 0.03 * grade
        result.update(
            {
                "direct_pet_stat_multiplier": round(multiplier, 2),
                "direct_pet_combat_bonus": True,
                "explanation": (
                    f"At currently unlocked grade {grade}, Pack Bond multiplies the "
                    f"equipped pet's HP, attack, and defense by {multiplier:.2f} in "
                    "supported pet battle modes."
                ),
            }
        )
        if active is not None:
            result["projected_pet_stats"] = {
                stat: round(float(active.get(stat, 0) or 0) * multiplier, 2)
                for stat in ("hp", "attack", "defense")
            }
    elif class_key == "ranger":
        result.update(
            {
                "pet_collection_utility": True,
                "explanation": (
                    "Ranger/Tamer improves scouting, egg acquisition, and pet "
                    "collection but does not directly multiply a pet's battle stats."
                ),
            }
        )
    else:
        result["explanation"] = (
            "This line has no base-class mechanic that directly multiplies pet combat stats."
        )
    return result


def confirms_class_change_proposal(
    pending: dict[str, Any] | None,
    *,
    slot: int,
    expected_current: str,
    class_key: str,
    event_id: str,
) -> bool:
    """Require the same paid switch on a genuinely later model decision."""
    if not isinstance(pending, dict):
        return False
    try:
        pending_slot = int(pending.get("slot", -1))
    except (TypeError, ValueError):
        return False
    return (
        pending_slot == slot
        and str(pending.get("expected_current") or "") == expected_current
        and str(pending.get("to_class_key") or "") == class_key
        and bool(str(pending.get("event_id") or ""))
        and str(pending.get("event_id")) != event_id
    )


def class_progression_payload(
    class_names: list[str], level: int
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Describe the exact evolution ceiling even when no evolution is available."""
    level = max(1, int(level))
    unlocked_index = min(6, min(level, 30) // 5)
    progression = []
    evolution_ready = False
    for class_name in class_names:
        game_class = class_from_string(class_name)
        if game_class is None:
            continue
        evolutions = get_class_evolves(game_class.get_class_line())
        target_index = min(unlocked_index, len(evolutions) - 1)
        current_name = game_class.class_name()
        current_index = next(
            (
                index
                for index, evolution in enumerate(evolutions)
                if evolution.class_name() == current_name
            ),
            target_index,
        )
        evolution_available = current_index < target_index
        next_level = (
            (current_index + 1) * 5
            if current_index + 1 < len(evolutions)
            else None
        )
        progression.append(
            {
                "current": current_name,
                "class_line": game_class.get_class_line_name(),
                "current_grade": current_index + 1,
                "highest_unlocked": evolutions[target_index].class_name(),
                "highest_unlocked_grade": target_index + 1,
                "currently_at_highest_unlocked_grade": not evolution_available,
                "next_evolution_level": next_level,
                "levels_until_next_evolution": (
                    max(0, next_level - level) if next_level is not None else None
                ),
                "evolution_available_now": evolution_available,
                "evolution_is_free": True,
                "evolution_has_no_downside": True,
            }
        )
        evolution_ready = evolution_ready or evolution_available

    future_unlocks = [
        int(entry["next_evolution_level"])
        for entry in progression
        if entry["next_evolution_level"] is not None
        and int(entry["next_evolution_level"]) > level
    ]
    summary = {
        "evolution_available_now": evolution_ready,
        "all_equipped_classes_at_current_level_cap": bool(progression)
        and not evolution_ready,
        "next_evolution_unlock_level": min(future_unlocks)
        if future_unlocks
        else None,
        "evolve_classes_action_should_be_offered_now": evolution_ready,
        "do_not_attempt_evolve_classes_when_action_is_absent": True,
    }
    return progression, summary


@dataclass(slots=True)
class DecisionAction:
    action: str
    parameters: dict[str, Any]
    reason: str


@dataclass(slots=True)
class Decision:
    event_id: str
    action: str
    parameters: dict[str, Any]
    reason: str
    dialogue: str
    message: discord.Message
    actions: tuple[DecisionAction, ...] = ()

    def ordered_actions(self) -> tuple[DecisionAction, ...]:
        if self.actions:
            return self.actions
        return (DecisionAction(self.action, self.parameters, self.reason),)

    def for_action(self, selected: DecisionAction) -> "Decision":
        return Decision(
            event_id=self.event_id,
            action=selected.action,
            parameters=selected.parameters,
            reason=selected.reason,
            dialogue=self.dialogue,
            message=self.message,
        )


def parse_marked_json(content: str, marker: str) -> dict[str, Any] | None:
    stripped = content.strip()
    if not stripped.startswith(marker):
        return None
    try:
        value = json.loads(stripped[len(marker):].strip())
    except (TypeError, ValueError):
        return None
    return value if isinstance(value, dict) else None


def action_names(event: dict[str, Any]) -> set[str]:
    actions = event.get("allowed_actions", [])
    return {
        str(item.get("name", "")).casefold()
        for item in actions
        if isinstance(item, dict) and item.get("name")
    }


def decision_from_payload(
    payload: dict[str, Any], message: discord.Message
) -> Decision | None:
    event_id = str(payload.get("event_id", "")).strip()
    if not event_id:
        return None
    parsed_actions = []
    raw_actions = payload.get("actions")
    if isinstance(raw_actions, list):
        for raw_action in raw_actions:
            if not isinstance(raw_action, dict):
                return None
            action = str(raw_action.get("action", "")).strip().casefold()
            if not action:
                return None
            parameters = raw_action.get("parameters", {})
            if not isinstance(parameters, dict):
                parameters = {}
            parsed_actions.append(
                DecisionAction(
                    action=action,
                    parameters=parameters,
                    reason=str(raw_action.get("reason", "")).strip()[:500],
                )
            )
        if not parsed_actions:
            return None
    else:
        action = str(payload.get("action", "")).strip().casefold()
        if not action:
            return None
        parameters = payload.get("parameters", {})
        if not isinstance(parameters, dict):
            parameters = {}
        parsed_actions.append(
            DecisionAction(
                action=action,
                parameters=parameters,
                reason=str(payload.get("reason", "")).strip()[:500],
            )
        )
    first = parsed_actions[0]
    return Decision(
        event_id=event_id,
        action=first.action,
        parameters=first.parameters,
        reason=first.reason,
        dialogue=str(payload.get("dialogue", "")).strip()[:500],
        message=message,
        actions=tuple(parsed_actions),
    )


class AIPlayer(commands.Cog):
    """Runs Densetsu as a normal, validated Fable character."""

    def __init__(self, bot):
        self.bot = bot
        self._pending: dict[str, asyncio.Future[Decision]] = {}
        self._local_tick_lock = asyncio.Lock()

    async def cog_load(self) -> None:
        self.autoplay_loop.start()

    def cog_unload(self) -> None:
        self.autoplay_loop.cancel()

    async def _bridge_channel(self):
        raw = await self.bot.redis.get(BRIDGE_CHANNEL_KEY)
        if raw is None:
            return None
        try:
            channel_id = int(raw)
        except (TypeError, ValueError):
            return None
        return self.bot.get_channel(channel_id)

    async def _report_error(self, where: str, exc: BaseException) -> None:
        """Log an AI player failure and echo it to the bound bridge channel."""
        logger.exception("Densetsu %s failed", where, exc_info=exc)
        try:
            channel = await self._bridge_channel()
            if channel is None:
                return
            await channel.send(
                f"AI player error in {where}: "
                f"`{type(exc).__name__}: {str(exc)[:450]}`",
                allowed_mentions=discord.AllowedMentions.none(),
            )
        except Exception:
            logger.exception(
                "Could not report the Densetsu error to the bridge channel"
            )

    def _queue_error_report(self, where: str, exc: BaseException) -> None:
        """Schedule a bridge error report from a synchronous done-callback."""
        try:
            asyncio.get_running_loop().create_task(self._report_error(where, exc))
        except RuntimeError:
            logger.exception("Densetsu %s failed", where, exc_info=exc)

    async def _is_enabled(self) -> bool:
        value = await self.bot.redis.get(ENABLED_KEY)
        if isinstance(value, bytes):
            value = value.decode("ascii", errors="ignore")
        return str(value) == "1"

    async def is_active_for(self, user_id: int) -> bool:
        """Return whether this cog is currently controlling the requested player."""
        return int(user_id) == DENSETSU_USER_ID and await self._is_enabled()

    async def _redis_json_get(self, key: str) -> dict[str, Any] | None:
        raw = await self.bot.redis.get(key)
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8", errors="ignore")
        if not raw:
            return None
        try:
            value = json.loads(raw)
        except (TypeError, ValueError):
            return None
        return value if isinstance(value, dict) else None

    async def _redis_json_set(
        self, key: str, value: dict[str, Any], *, expires: int | None = None
    ) -> None:
        payload = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        if expires is None:
            await self.bot.redis.set(key, payload)
        else:
            await self.bot.redis.set(key, payload, ex=max(1, int(expires)))

    @staticmethod
    def _class_build_snapshot(state: dict[str, Any]) -> dict[str, Any]:
        equipment = state.get("equipment") or {}
        current_equipment = equipment.get("current") or {}
        pets = (state.get("companions") or {}).get("pets") or []
        active_pet = next(
            (pet for pet in pets if isinstance(pet, dict) and pet.get("equipped")),
            None,
        )
        raid_final = ((state.get("raid_stats") or {}).get("final_raidbattle_stats") or {})
        level = int((state.get("character") or {}).get("level", 0) or 0)
        return {
            "level": level,
            "class_evolution_cap_grade": min(7, max(1, level // 5 + 1)),
            "secondary_class_slot_unlocked": level >= 12,
            "specialization_level_gate_unlocked": level >= MASTERY_UNLOCK_LEVEL,
            "equipped_item_ids": sorted(
                int(item_id) for item_id in current_equipment.get("item_ids", [])
            ),
            "equipped_item_types": sorted(
                str(item.get("type") or "Unknown")
                for item in equipment.get("equipped_items", [])
                if isinstance(item, dict)
            ),
            "equipped_pet_id": int(active_pet["id"]) if active_pet else None,
            "equipped_pet_combat_score": (
                float(active_pet.get("combat_score", 0) or 0) if active_pet else None
            ),
            "raid_attack": float(raid_final.get("attack", 0) or 0),
            "raid_defense": float(raid_final.get("defense", 0) or 0),
            "raid_max_hp": float(raid_final.get("max_hp", 0) or 0),
        }

    async def _record_class_plan(
        self,
        *,
        decision: Decision,
        state: dict[str, Any],
        slot: int,
        class_key: str,
        previous_class_name: str,
        selection_kind: str,
    ) -> None:
        plan = await self._redis_json_get(CLASS_PLAN_KEY) or {"slots": {}}
        slots = plan.get("slots")
        if not isinstance(slots, dict):
            slots = {}
        slots[str(slot)] = {
            "slot": slot,
            "selected_class_key": class_key,
            "selected_class_line": ALL_KNOWN_CLASSES[class_key].__name__,
            "previous_class_name": previous_class_name,
            "previous_class_keys": sorted(
                class_keys_for_evolution(previous_class_name)
            ),
            "selection_kind": selection_kind,
            "reason": decision.reason or "No long-term rationale was supplied.",
            "selected_at_unix": int(
                datetime.datetime.now(datetime.timezone.utc).timestamp()
            ),
            "build_snapshot": self._class_build_snapshot(state),
        }
        plan["slots"] = slots
        await self._redis_json_set(CLASS_PLAN_KEY, plan)

    async def _collect_class_strategy_state(
        self, *, class_names: list[str], state: dict[str, Any]
    ) -> dict[str, Any]:
        plan = await self._redis_json_get(CLASS_PLAN_KEY) or {"slots": {}}
        plan_slots = plan.get("slots")
        if not isinstance(plan_slots, dict):
            plan_slots = {}
        proposal = await self._redis_json_get(CLASS_CHANGE_PROPOSAL_KEY)
        if proposal is not None:
            try:
                proposal_slot = int(proposal.get("slot", -1))
            except (TypeError, ValueError):
                proposal_slot = -1
            if (
                proposal_slot not in (0, 1)
                or proposal_slot >= len(class_names)
                or str(proposal.get("expected_current") or "")
                != str(class_names[proposal_slot])
            ):
                await self.bot.redis.delete(CLASS_CHANGE_PROPOSAL_KEY)
                proposal = None
        current_snapshot = self._class_build_snapshot(state)
        now = int(datetime.datetime.now(datetime.timezone.utc).timestamp())
        seeded_baseline = False
        for slot, class_name in enumerate(class_names[:2]):
            if class_name == "No Class" or str(slot) in plan_slots:
                continue
            current_keys = sorted(class_keys_for_evolution(class_name))
            if not current_keys:
                continue
            class_key = current_keys[0]
            plan_slots[str(slot)] = {
                "slot": slot,
                "selected_class_key": class_key,
                "selected_class_line": ALL_KNOWN_CLASSES[class_key].__name__,
                "previous_class_name": None,
                "previous_class_keys": [],
                "selection_kind": "adopted_existing_build_baseline",
                "reason": (
                    "This equipped class was adopted as the long-term baseline when "
                    "class consistency tracking was enabled."
                ),
                "selected_at_unix": now,
                "build_snapshot": current_snapshot,
            }
            seeded_baseline = True
        if seeded_baseline:
            plan["slots"] = plan_slots
            await self._redis_json_set(CLASS_PLAN_KEY, plan)
        active_plans = []
        for raw_slot, raw_plan in plan_slots.items():
            if not isinstance(raw_plan, dict):
                continue
            try:
                slot = int(raw_slot)
            except (TypeError, ValueError):
                continue
            if slot not in (0, 1) or slot >= len(class_names):
                continue
            entry = dict(raw_plan)
            selected_at = int(entry.get("selected_at_unix", 0) or 0)
            original_snapshot = entry.get("build_snapshot") or {}
            changes = []
            for field, label in (
                ("equipped_item_ids", "equipped items changed"),
                ("equipped_pet_id", "equipped pet changed"),
            ):
                if original_snapshot.get(field) != current_snapshot.get(field):
                    changes.append(label)
            for field, label in (
                ("class_evolution_cap_grade", "a new class evolution grade unlocked"),
                ("secondary_class_slot_unlocked", "the second class slot unlocked"),
                ("specialization_level_gate_unlocked", "the specialization level gate unlocked"),
            ):
                if original_snapshot.get(field) != current_snapshot.get(field):
                    changes.append(label)
            entry.update(
                {
                    "current_class_name": class_names[slot],
                    "current_class_still_matches_plan": entry.get(
                        "selected_class_key"
                    )
                    in class_keys_for_evolution(class_names[slot]),
                    "seconds_since_selection": max(0, now - selected_at),
                    "observable_build_changes_since_selection": changes,
                    "observable_build_changed": bool(changes),
                }
            )
            active_plans.append(entry)
        return {
            "policy": {
                "cooldown_expiry_only_makes_change_legal": True,
                "cooldown_expiry_is_not_a_reason_to_change": True,
                "preserve_a_coherent_long_term_build": True,
                "reversing_a_recent_choice_requires_new_concrete_evidence": True,
                "paid_change_requires_same_proposal_on_two_separate_decisions": True,
                "switching_remains_available_when_strategically_justified": True,
            },
            "recorded_slot_plans": active_plans,
            "pending_paid_change_proposal": proposal,
            "current_build_snapshot": current_snapshot,
        }

    async def _max_wager_percent(self) -> int:
        value = await self.bot.redis.get(MAX_WAGER_PERCENT_KEY)
        try:
            return max(0, min(100, int(value)))
        except (TypeError, ValueError):
            return DEFAULT_MAX_WAGER_PERCENT

    async def _maximum_raid_wager(self, money: int) -> int:
        percent = await self._max_wager_percent()
        return max(0, int(money) * percent // 100)

    async def _command_cooldown(self, command_name: str) -> int:
        command = self.bot.get_command(command_name)
        qualified_name = command.qualified_name if command else command_name
        ttl = await self.bot.redis.ttl(
            f"cd:{DENSETSU_USER_ID}:{qualified_name}"
        )
        try:
            return max(0, int(ttl))
        except (TypeError, ValueError):
            return 0

    async def _collect_health_state(
        self, connection, profile, *, level: int
    ) -> dict[str, Any]:
        amulet_hp = 0
        try:
            amulet_hp = await connection.fetchval(
                "SELECT COALESCE(hp, 0) FROM amulets "
                "WHERE user_id=$1 AND equipped=TRUE LIMIT 1;",
                DENSETSU_USER_ID,
            )
        except Exception:
            logger.exception("Could not read Densetsu's equipped amulet HP")
        return combat_health_state(
            level=level,
            profile_health_bonus=profile["health"],
            allocated_health_points=profile["stathp"],
            amulet_hp=amulet_hp or 0,
        )

    @classmethod
    def _json_safe_raid_value(cls, value):
        if isinstance(value, Decimal):
            return round(float(value), 4)
        if isinstance(value, float):
            return round(value, 4)
        if isinstance(value, (str, int, bool)) or value is None:
            return value
        if isinstance(value, dict):
            return {
                str(key): cls._json_safe_raid_value(item)
                for key, item in value.items()
            }
        if isinstance(value, (list, tuple, set)):
            return [cls._json_safe_raid_value(item) for item in value]
        return str(value)

    async def _collect_raid_stats(
        self, user_id: int, player=None
    ) -> dict[str, Any]:
        battle_cog = self.bot.get_cog("Battles")
        factory = getattr(battle_cog, "battle_factory", None)
        if factory is None or not hasattr(factory, "create_player_combatant"):
            return {"available": False}
        if player is None:
            player = self.bot.get_user(user_id)
        if player is None:
            player = SimpleNamespace(
                id=user_id,
                display_name=f"Player {user_id}",
                mention=f"<@{user_id}>",
            )
        try:
            _attack, _defense, breakdown = await self.bot.get_raidstats(
                user_id,
                return_breakdown=True,
            )
            raid_setting_names = (
                "allow_pets",
                "class_buffs",
                "element_effects",
                "reflection_damage",
                "cheat_death",
                "tripping",
                "pets_continue_battle",
            )
            raid_settings = {
                name: bool(
                    await factory.settings.get_setting_async("raid", name)
                )
                for name in raid_setting_names
            }
            raid_allows_pets = raid_settings["allow_pets"]
            combat_ctx = SimpleNamespace(bot=self.bot)
            combatant = await factory.create_player_combatant(
                combat_ctx, player, include_pet=raid_allows_pets
            )
            pet_combatant = (
                await factory.pet_ext.get_pet_combatant(combat_ctx, player)
                if raid_allows_pets
                else None
            )
        except Exception:
            logger.exception("Could not build raid stats for player %s", user_id)
            return {"available": False}

        class_effect_attributes = (
            "lifesteal_percent",
            "death_cheat_chance",
            "damage_reflection",
            "mage_evolution",
            "warrior_evolution",
            "tank_evolution",
            "paladin_evolution",
            "raider_evolution",
            "ritualist_evolution",
            "paragon_evolution",
            "bard_evolution",
            "beastmaster_evolution",
            "reaper_evolution",
            "santa_evolution",
        )
        class_effects = {
            name: self._json_safe_raid_value(getattr(combatant, name, None))
            for name in class_effect_attributes
            if getattr(combatant, name, None) not in (None, 0, 0.0, False)
        }
        pet_stats = None
        if pet_combatant is not None:
            pet_stats = {
                "id": self._json_safe_raid_value(
                    getattr(pet_combatant, "pet_id", None)
                ),
                "name": str(getattr(pet_combatant, "name", "Combat pet")),
                "level": self._json_safe_raid_value(
                    getattr(pet_combatant, "display_level", None)
                ),
                "attack": self._json_safe_raid_value(pet_combatant.damage),
                "defense": self._json_safe_raid_value(pet_combatant.armor),
                "max_hp": self._json_safe_raid_value(pet_combatant.max_hp),
                "luck_percent": self._json_safe_raid_value(pet_combatant.luck),
                "element": str(getattr(pet_combatant, "element", "Unknown")),
                "happiness": self._json_safe_raid_value(
                    getattr(pet_combatant, "happiness", None)
                ),
                "trust": self._json_safe_raid_value(
                    getattr(pet_combatant, "trust_level", None)
                ),
                "skill_effects": self._json_safe_raid_value(
                    getattr(pet_combatant, "skill_effects", {})
                ),
            }
        return {
            "available": True,
            "final_raidbattle_stats": {
                "attack": self._json_safe_raid_value(combatant.damage),
                "defense": self._json_safe_raid_value(combatant.armor),
                "max_hp": self._json_safe_raid_value(combatant.max_hp),
                "shield": self._json_safe_raid_value(
                    getattr(combatant, "shield", 0)
                ),
                "luck_percent": self._json_safe_raid_value(combatant.luck),
                "attack_element": str(
                    getattr(combatant, "attack_element", "Unknown")
                ),
                "defense_element": str(
                    getattr(combatant, "defense_element", "Unknown")
                ),
                "dual_attack_elements": self._json_safe_raid_value(
                    getattr(combatant, "dual_attack_elements", None)
                ),
            },
            "attack_defense_breakdown": self._json_safe_raid_value(breakdown),
            "class_combat_effects": class_effects,
            "specialization_effects": self._json_safe_raid_value(
                getattr(combatant, "spec_effects", {})
            ),
            "raidbattle_pet": pet_stats,
            "standard_raidbattle_allows_pets": raid_allows_pets,
            "raidbattle_settings": raid_settings,
            "stats_are_rebuilt_at_battle_start": True,
        }

    @staticmethod
    def _raid_stat_comparison(
        ours: dict[str, Any], theirs: dict[str, Any]
    ) -> dict[str, Any]:
        ours_final = ours.get("final_raidbattle_stats") or {}
        theirs_final = theirs.get("final_raidbattle_stats") or {}
        comparison = {}
        for key in ("attack", "defense", "max_hp", "luck_percent"):
            try:
                ours_value = float(ours_final[key])
                theirs_value = float(theirs_final[key])
                comparison[f"{key}_ratio"] = round(
                    ours_value / max(0.0001, theirs_value), 3
                )
            except (KeyError, TypeError, ValueError):
                continue
        ours_pet = ours.get("raidbattle_pet") or {}
        theirs_pet = theirs.get("raidbattle_pet") or {}
        for key in ("attack", "defense", "max_hp"):
            try:
                ours_value = float(ours_pet[key])
                theirs_value = float(theirs_pet[key])
                comparison[f"pet_{key}_ratio"] = round(
                    ours_value / max(0.0001, theirs_value), 3
                )
            except (KeyError, TypeError, ValueError):
                if bool(ours_pet) != bool(theirs_pet):
                    comparison["pet_advantage"] = (
                        "densetsu" if ours_pet else "opponent"
                    )
                continue
        comparison["ratio_above_one_favors_densetsu"] = True
        comparison["not_a_win_probability"] = True
        return comparison

    @staticmethod
    def _daily_reward_summary(reward: dict[str, Any]) -> str:
        kind = str(reward.get("kind") or "")
        if kind == "money":
            return f"${int(reward.get('amount') or 0):,} gold"
        rarity = str(reward.get("rarity") or "unknown")
        amount = int(reward.get("amount") or 0)
        crate_text = f"{amount} {rarity} crate{'s' if amount != 1 else ''}"
        if kind == "milestone":
            return f"{crate_text} and ${int(reward.get('money') or 0):,} gold"
        return crate_text

    async def _collect_reward_state(
        self, connection, profile
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        counts = {
            rarity: int(profile[f"crates_{rarity}"] or 0)
            for rarity in CRATE_RARITIES
        }
        material_crates_available = self.bot.get_cog("PremiumShop") is not None
        open_options = [
            {
                "rarity": rarity,
                "owned": count,
                "maximum_per_action": min(count, 100),
                "contents": CRATE_KNOWLEDGE[rarity],
            }
            for rarity, count in counts.items()
            if count > 0 and (rarity != "materials" or material_crates_available)
        ]
        actions: list[dict[str, Any]] = []
        if open_options:
            actions.append(
                {
                    "name": "open_crates",
                    "description": (
                        "Open up to 100 owned crates of one offered rarity using "
                        "Fable's normal crate command."
                    ),
                    "parameters": {
                        "rarity": [
                            option["rarity"] for option in open_options
                        ],
                        "amount": {
                            "minimum": 1,
                            "maximum_by_rarity": {
                                option["rarity"]: option["maximum_per_action"]
                                for option in open_options
                            },
                        },
                    },
                    "available_options": open_options,
                    "response_example": {
                        "action": "open_crates",
                        "parameters": {
                            "rarity": open_options[0]["rarity"],
                            "amount": open_options[0]["maximum_per_action"],
                        },
                    },
                }
            )

        vote_cooldown = await self._command_cooldown("cratesdaily")
        vote_command_loaded = self.bot.get_command("cratesdaily") is not None
        if vote_command_loaded and vote_cooldown <= 0:
            actions.append(
                {
                    "name": "claim_vote_crates",
                    "description": (
                        "Use this server's legitimate $vote/$cratesdaily reward "
                        "command on its real 12-hour cooldown."
                    ),
                }
            )

        daily_cooldown = await self._command_cooldown("daily")
        daily_cog = self.bot.get_cog("Miscellaneous")
        daily_state: dict[str, Any] = {
            "available": False,
            "cooldown_seconds": daily_cooldown,
        }
        if daily_cog is not None:
            await daily_cog._ensure_daily_streak_table()
            streak_row = await connection.fetchrow(
                """
                SELECT current_streak, highest_days, restore_points, last_daily,
                       last_daily::date =
                           (NOW() AT TIME ZONE 'UTC')::date AS claimed_today
                FROM streaks WHERE user_id=$1;
                """,
                DENSETSU_USER_ID,
            )
            claimed_today = bool(
                streak_row is not None and streak_row["claimed_today"]
            )
            if claimed_today and daily_cooldown <= 0:
                now_utc = datetime.datetime.now(datetime.timezone.utc)
                tomorrow = (now_utc + datetime.timedelta(days=1)).date()
                midnight = datetime.datetime.combine(
                    tomorrow, datetime.time.min, tzinfo=datetime.timezone.utc
                )
                daily_cooldown = max(
                    1, int((midnight - now_utc).total_seconds())
                )
            next_streak = await daily_cog._get_next_daily_streak(
                DENSETSU_USER_ID
            )
            daily_available = daily_cooldown <= 0 and not claimed_today
            daily_state = {
                "available": daily_available,
                "cooldown_seconds": daily_cooldown,
                "current_streak": int(
                    streak_row["current_streak"] if streak_row else 0
                ),
                "highest_streak": int(
                    streak_row["highest_days"] if streak_row else 0
                ),
                "restore_points": int(
                    streak_row["restore_points"] if streak_row else 3
                ),
                "next_streak": int(next_streak),
                "must_claim_within_48_hours_to_keep_streak": True,
            }
            if daily_available:
                if next_streak in DAILY_MILESTONE_REWARDS:
                    rarity, amount, money = DAILY_MILESTONE_REWARDS[next_streak]
                    rewards = [
                        {
                            "kind": "milestone",
                            "rarity": rarity,
                            "amount": amount,
                            "money": money,
                        }
                    ]
                else:
                    multiplier = await daily_cog._get_daily_money_multiplier(
                        SimpleNamespace(author=SimpleNamespace(id=DENSETSU_USER_ID))
                    )
                    rewards = [
                        daily_cog._roll_daily_reward(next_streak, multiplier),
                        daily_cog._roll_daily_reward(next_streak, multiplier),
                    ]
                choices = [
                    {
                        "choice": index,
                        "reward": reward,
                        "summary": self._daily_reward_summary(reward),
                    }
                    for index, reward in enumerate(rewards)
                ]
                daily_state["offered_rewards"] = choices
                actions.append(
                    {
                        "name": "claim_daily",
                        "description": (
                            "Claim one of today's already-rolled rewards and "
                            "advance the daily streak."
                        ),
                        "parameters": {
                            "choice": [choice["choice"] for choice in choices],
                            "options": choices,
                            "next_streak": int(next_streak),
                        },
                    }
                )

        state = {
            "crates": counts,
            "crate_contents": CRATE_KNOWLEDGE,
            "open_options": open_options,
            "daily": daily_state,
            "vote_crates": {
                "available": vote_command_loaded and vote_cooldown <= 0,
                "cooldown_seconds": vote_cooldown,
                "expected_crate_count": 4 if int(profile["tier"] or 0) >= 3 else 2,
                "command_grants_reward_directly_on_this_server": True,
            },
        }
        return state, actions

    async def _collect_booster_state(
        self, profile
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        active_values = await asyncio.gather(
            *(self.bot.get_booster(DENSETSU_USER_ID, kind) for kind in BOOSTER_KNOWLEDGE)
        )
        active_seconds = {
            kind: max(0, int(value.total_seconds())) if value else 0
            for kind, value in zip(BOOSTER_KNOWLEDGE, active_values)
        }
        owned = {
            kind: int(profile[f"{kind}_booster"] or 0)
            for kind in BOOSTER_KNOWLEDGE
        }
        activation_options = [
            {
                "type": kind,
                "owned": owned[kind],
                "effect": BOOSTER_KNOWLEDGE[kind],
            }
            for kind in BOOSTER_KNOWLEDGE
            if owned[kind] > 0 and active_seconds[kind] <= 0
        ]
        actions: list[dict[str, Any]] = []
        booster_daily_cooldown = await self._command_cooldown("boosterdaily")
        booster_daily_loaded = self.bot.get_command("boosterdaily") is not None
        if booster_daily_loaded and booster_daily_cooldown <= 0:
            actions.append(
                {
                    "name": "claim_daily_booster",
                    "description": "Claim the legitimate daily random booster reward.",
                }
            )
        if activation_options:
            actions.append(
                {
                    "name": "activate_booster",
                    "description": (
                        "Consume one owned, inactive booster. Active boosters are never "
                        "offered here, so this cannot overwrite remaining duration."
                    ),
                    "parameters": {
                        "type": [option["type"] for option in activation_options],
                    },
                    "available_options": activation_options,
                }
            )
        return {
            "owned": owned,
            "active_seconds": active_seconds,
            "effects": BOOSTER_KNOWLEDGE,
            "daily_reward": {
                "available": booster_daily_loaded and booster_daily_cooldown <= 0,
                "cooldown_seconds": booster_daily_cooldown,
                "awards_one_random_type": True,
            },
        }, actions

    async def _collect_equipment_state(
        self,
        connection,
        class_names: list[str],
        available_classes: dict[str, type],
    ) -> dict[str, Any]:
        rows = await connection.fetch(
            """
            SELECT ai.id, ai.name, ai.type, ai.damage, ai.armor, ai.hand,
                   ai.element, i.equipped
            FROM allitems ai
            JOIN inventory i ON i.item=ai.id
            WHERE ai.owner=$1;
            """,
            DENSETSU_USER_ID,
        )
        if not rows:
            return {
                "current": {"item_ids": [], "score": 0},
                "recommended": None,
                "class_weapon_bonus_rules": favored_weapon_bonus_rules(),
                "class_weapon_bonuses_apply_to_each_matching_equipped_item": True,
                "class_weapon_bonuses_are_included_in_scores": True,
                "_hypothetical_class_change_fit": {},
                "candidates": [],
            }

        item_ids = [int(row["id"]) for row in rows]
        star_map: dict[int, int] = {}
        soulbound_item_id = None
        soulbound_level = 0
        try:
            if await connection.fetchval(
                "SELECT to_regclass('public.starforged_items') IS NOT NULL;"
            ):
                star_rows = await connection.fetch(
                    "SELECT item_id, stars FROM starforged_items "
                    "WHERE item_id=ANY($1::bigint[]);",
                    item_ids,
                )
                star_map = {
                    int(row["item_id"]): int(row["stars"] or 0)
                    for row in star_rows
                }
            if await connection.fetchval(
                "SELECT to_regclass('public.soulbound') IS NOT NULL;"
            ):
                soulbound = await connection.fetchrow(
                    "SELECT item_id, xp FROM soulbound "
                    "WHERE user_id=$1 AND item_id=ANY($2::bigint[]);",
                    DENSETSU_USER_ID,
                    item_ids,
                )
                if soulbound:
                    soulbound_item_id = int(soulbound["item_id"])
                    soulbound_level = soulbound_level_from_xp(soulbound["xp"])
        except Exception:
            logger.exception("Could not read Densetsu's item progression")

        items = []
        current_ids = []
        for row in rows:
            item = dict(row)
            item_id = int(item["id"])
            effective_damage, effective_armor, bonus_pct = (
                apply_item_progression_bonus(
                    item.get("damage", 0),
                    item.get("armor", 0),
                    stars=star_map.get(item_id, 0),
                    soulbound_level=(
                        soulbound_level if item_id == soulbound_item_id else 0
                    ),
                )
            )
            item["effective_damage"] = float(effective_damage)
            item["effective_armor"] = float(effective_armor)
            item["progression_bonus_percent"] = round(float(bonus_pct * 100), 2)
            item["stars"] = star_map.get(item_id, 0)
            item["equipped"] = bool(item.get("equipped"))
            items.append(item)
            if item["equipped"]:
                current_ids.append(item_id)

        current_items = [item for item in items if int(item["id"]) in current_ids]
        current = score_loadout(current_items, class_names)
        recommended = choose_best_equipment(items, class_names, current_ids)
        hypothetical_fit = {
            str(slot): {
                key: hypothetical_class_equipment_fit(
                    items=items,
                    current_item_ids=current_ids,
                    class_names=class_names,
                    slot=slot,
                    replacement_class_name=get_first_evolution(class_type).class_name(),
                )
                for key, class_type in available_classes.items()
            }
            for slot in range(2)
        }

        ranked_items = sorted(
            items,
            key=lambda item: score_loadout([item], class_names)["score"],
            reverse=True,
        )[:16]
        candidates = []
        for item in ranked_items:
            single = score_loadout([item], class_names)
            candidates.append(
                {
                    "id": int(item["id"]),
                    "name": str(item["name"]),
                    "type": str(item["type"]),
                    "hand": str(item["hand"]),
                    "element": str(item.get("element") or "Unknown"),
                    "damage": single["effective_damage"],
                    "armor": single["effective_armor"],
                    "base_damage": single["base_effective_damage"],
                    "base_armor": single["base_effective_armor"],
                    "class_weapon_bonus_damage": single[
                        "class_weapon_bonus_damage"
                    ],
                    "class_weapon_bonus_armor": single[
                        "class_weapon_bonus_armor"
                    ],
                    "favored_by_current_class": bool(
                        single["class_weapon_bonus_damage"]
                        or single["class_weapon_bonus_armor"]
                    ),
                    "class_adjusted_score": single["score"],
                    "progression_bonus_percent": item["progression_bonus_percent"],
                    "equipped": item["equipped"],
                }
            )

        return {
            "current": current,
            "recommended": recommended,
            "recommendation_uses_real_class_and_progression_bonuses": True,
            "class_weapon_bonus_rules": favored_weapon_bonus_rules(),
            "class_weapon_bonuses_apply_to_each_matching_equipped_item": True,
            "class_weapon_bonuses_are_included_in_scores": True,
            "equipped_items": [
                {
                    "id": int(item["id"]),
                    "name": str(item["name"]),
                    "type": str(item["type"]),
                    "hand": str(item["hand"]),
                    "effective_damage": round(float(item["effective_damage"]), 2),
                    "effective_armor": round(float(item["effective_armor"]), 2),
                }
                for item in current_items
            ],
            "_hypothetical_class_change_fit": hypothetical_fit,
            "candidates": candidates,
        }

    async def _collect_amulet_state(
        self, connection, *, level: int
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        amulet_cog = self.bot.get_cog("AmuletCrafting")
        if amulet_cog is None:
            return {"available": False}, []

        try:
            resource_rows = await connection.fetch(
                "SELECT resource_type, amount FROM crafting_resources "
                "WHERE user_id=$1 AND amount>0;",
                DENSETSU_USER_ID,
            )
            amulet_rows = await connection.fetch(
                """
                SELECT id, type, tier, hp, attack, defense, equipped
                FROM amulets
                WHERE user_id=$1
                ORDER BY tier DESC, id ASC;
                """,
                DENSETSU_USER_ID,
            )
        except Exception:
            logger.exception("Could not read Densetsu's amulet state")
            return {"available": False}, []

        resources = {
            str(row["resource_type"]): int(row["amount"] or 0)
            for row in resource_rows
        }
        owned = [
            {
                "id": int(row["id"]),
                "type": str(row["type"]),
                "tier": int(row["tier"]),
                "health": int(row["hp"] or 0),
                "attack": int(row["attack"] or 0),
                "defense": int(row["defense"] or 0),
                "equipped": bool(row["equipped"]),
            }
            for row in amulet_rows
        ]
        equipped = next((amulet for amulet in owned if amulet["equipped"]), None)
        current_tier = int(equipped["tier"]) if equipped is not None else 0
        highest_owned_tier = max(
            (int(amulet["tier"]) for amulet in owned), default=0
        )
        max_unlocked_tier = max(
            (
                int(tier)
                for tier, required_level in amulet_cog.TIER_LEVELS.items()
                if level >= int(required_level)
            ),
            default=0,
        )

        craftable_upgrades = []
        next_targets = []
        owned_pairs = {
            (str(amulet["type"]).casefold(), int(amulet["tier"]))
            for amulet in owned
        }
        for amulet_type, tier_stats in amulet_cog.AMULET_TYPES.items():
            candidates = []
            targets = []
            for tier in sorted(int(value) for value in tier_stats):
                if tier > max_unlocked_tier or tier <= highest_owned_tier:
                    continue
                recipe = dict(
                    amulet_cog.AMULET_RECIPES.get(amulet_type, {}).get(tier, {})
                )
                if not recipe or (amulet_type.casefold(), tier) in owned_pairs:
                    continue
                stats = tier_stats[tier]
                missing = {
                    resource: max(0, int(required) - resources.get(resource, 0))
                    for resource, required in recipe.items()
                    if resources.get(resource, 0) < int(required)
                }
                option = {
                    "type": str(amulet_type),
                    "tier": tier,
                    "stats": {
                        "health": int(stats["health"]),
                        "attack": int(stats["attack"]),
                        "defense": int(stats["defense"]),
                    },
                    "recipe": {
                        str(resource): int(required)
                        for resource, required in recipe.items()
                    },
                    "missing_resources": missing,
                    "craftable_now": not missing,
                }
                targets.append(option)
                if not missing:
                    candidates.append(option)
            if candidates:
                craftable_upgrades.append(max(candidates, key=lambda item: item["tier"]))
            if targets:
                next_targets.append(min(targets, key=lambda item: item["tier"]))

        equip_options = [
            amulet
            for amulet in owned
            if not amulet["equipped"] and int(amulet["tier"]) > current_tier
        ]
        actions: list[dict[str, Any]] = []
        if equip_options:
            actions.append(
                {
                    "name": "equip_amulet",
                    "description": (
                        "Equip one already-owned higher-tier amulet. Only one "
                        "amulet can be equipped at a time."
                    ),
                    "parameters": {
                        "amulet_id": [option["id"] for option in equip_options]
                    },
                    "available_options": equip_options,
                }
            )
        if craftable_upgrades:
            actions.append(
                {
                    "name": "craft_and_equip_amulet",
                    "description": (
                        "Consume the exact listed materials to craft one strictly "
                        "higher-tier amulet and immediately equip it. Choose its "
                        "type for the current class and combat build."
                    ),
                    "parameters": {
                        "options": [
                            {"type": option["type"], "tier": option["tier"]}
                            for option in craftable_upgrades
                        ]
                    },
                    "available_options": craftable_upgrades,
                }
            )

        return {
            "available": True,
            "only_one_can_be_equipped": True,
            "stats": {
                "health": "flat maximum combat HP",
                "attack": "flat raid attack added after equipment multipliers",
                "defense": "flat raid defense added after equipment multipliers",
            },
            "equipped": equipped,
            "owned": owned,
            "resources": resources,
            "maximum_tier_unlocked_by_level": max_unlocked_tier,
            "highest_owned_tier": highest_owned_tier,
            "upgrade_policy": (
                "Only amulets above the highest owned tier are offered for "
                "crafting, preventing duplicate and sidegrade material waste."
            ),
            "craftable_upgrades": craftable_upgrades,
            "next_upgrade_targets": next_targets,
        }, actions

    @staticmethod
    def _egg_seconds_remaining(hatch_time) -> int:
        if hatch_time is None:
            return 0
        now = (
            datetime.datetime.now(hatch_time.tzinfo)
            if getattr(hatch_time, "tzinfo", None)
            else datetime.datetime.utcnow()
        )
        return max(0, int((hatch_time - now).total_seconds()))

    async def _collect_pet_state(
        self, connection, *, money: int, tier: int
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        try:
            pet_rows = await connection.fetch(
                """
                SELECT id, name, default_name, element, "IV", hp, attack, defense,
                       growth_stage, growth_index, happiness, hunger, equipped,
                       COALESCE(level, 1) AS level,
                       COALESCE(experience, 0) AS experience,
                       COALESCE(trust_level, 0) AS trust_level,
                       COALESCE(skill_points, 0) AS skill_points,
                       learned_skills, gm_all_skills_enabled, daycare_boarding_id
                FROM monster_pets
                WHERE user_id=$1
                ORDER BY id ASC;
                """,
                DENSETSU_USER_ID,
            )
            egg_rows = await connection.fetch(
                """
                SELECT id, egg_type, element, "IV", hp, attack, defense, hatch_time
                FROM monster_eggs
                WHERE user_id=$1 AND hatched=FALSE
                ORDER BY hatch_time ASC;
                """,
                DENSETSU_USER_ID,
            )
        except Exception:
            logger.exception("Could not read Densetsu's pets and eggs")
            return {"pets": [], "eggs": [], "automatic_hatching": True}, []

        pet_cog = self.bot.get_cog("Pets")
        pets = []
        raw_pets = [dict(row) for row in pet_rows]
        best_pet_id = choose_best_pet(raw_pets)
        for pet in raw_pets:
            learned = pet.get("learned_skills") or []
            if pet_cog is not None and hasattr(
                pet_cog, "get_effective_learned_skills"
            ):
                learned = pet_cog.get_effective_learned_skills(pet)
            elif isinstance(learned, str):
                try:
                    learned = json.loads(learned)
                except ValueError:
                    learned = []
            pets.append(
                {
                    "id": int(pet["id"]),
                    "name": str(pet["name"]),
                    "species": str(pet.get("default_name") or pet["name"]),
                    "element": str(pet.get("element") or "Unknown"),
                    "iv_percent": round(float(pet.get("IV") or 0), 2),
                    "hp": int(pet.get("hp") or 0),
                    "attack": int(pet.get("attack") or 0),
                    "defense": int(pet.get("defense") or 0),
                    "growth_stage": str(pet.get("growth_stage") or "baby"),
                    "is_adult": str(
                        pet.get("growth_stage") or "baby"
                    ).casefold() == "adult",
                    "fullness_percent": int(pet.get("hunger") or 0),
                    "fullness_scale": "100 is fully fed; 0 is starving",
                    "happiness_percent": int(pet.get("happiness") or 0),
                    "fullness_and_happiness_decay": str(
                        pet.get("growth_stage") or "baby"
                    ).casefold() != "adult",
                    "level": int(pet.get("level") or 1),
                    "experience": int(pet.get("experience") or 0),
                    "trust": int(pet.get("trust_level") or 0),
                    "skill_points": int(pet.get("skill_points") or 0),
                    "learned_skills": list(learned),
                    "equipped": bool(pet.get("equipped")),
                    "in_daycare": bool(pet.get("daycare_boarding_id")),
                    "combat_score": pet_combat_score(pet),
                }
            )

        max_collection = {1: 12, 2: 14, 3: 17, 4: 25}.get(int(tier), 10)
        # handle_egg_drop gates on pets + unhatched eggs + pending splice
        # requests. Counting only pets and eggs made Densetsu believe it had
        # room the game would refuse.
        try:
            pending_splices = int(
                await connection.fetchval(
                    "SELECT COUNT(*) FROM splice_requests "
                    "WHERE user_id=$1 AND status='pending';",
                    DENSETSU_USER_ID,
                )
                or 0
            )
        except Exception:
            logger.exception("Could not read Densetsu's pending splice requests")
            pending_splices = 0
        eggs = [
            {
                "id": int(egg["id"]),
                "species": str(egg["egg_type"]),
                "element": str(egg.get("element") or "Unknown"),
                "iv_percent": round(float(egg.get("IV") or 0), 2),
                "hp": int(egg.get("hp") or 0),
                "attack": int(egg.get("attack") or 0),
                "defense": int(egg.get("defense") or 0),
                "hatches_in_seconds": self._egg_seconds_remaining(
                    egg.get("hatch_time")
                ),
            }
            for egg in egg_rows
        ]

        actions: list[dict[str, Any]] = []
        equippable_ids = [
            pet["id"]
            for pet in pets
            if not pet["in_daycare"]
            and pet["growth_stage"].casefold() in {"young", "adult"}
        ]
        equipped_id = next(
            (pet["id"] for pet in pets if pet["equipped"]), None
        )
        if best_pet_id is not None and best_pet_id != equipped_id:
            actions.append(
                {
                    "name": "equip_pet",
                    "description": "Equip the most suitable available combat pet.",
                    "parameters": {
                        "pet_id": equippable_ids,
                        "recommended": best_pet_id,
                    },
                }
            )

        target_id = equipped_id or best_pet_id
        target = next((pet for pet in pets if pet["id"] == target_id), None)
        care_options = []
        care_action_status = []
        if target is not None and not target["in_daycare"]:
            is_adult = bool(target["is_adult"])
            fullness = int(target["fullness_percent"])
            happiness = int(target["happiness_percent"])
            can_afford_feed = money >= BASIC_PET_FOOD_COST and (
                (not is_adult and fullness <= PET_EMERGENCY_HUNGER)
                or money - BASIC_PET_FOOD_COST >= PET_CARE_MONEY_RESERVE
            )
            needed_by_kind = {
                # Adult pets never lose fullness, so feeding is not maintenance.
                "feed": not is_adult and fullness <= 60 and can_afford_feed,
                "pet": happiness < 90 or target["trust"] < 81,
                "play": happiness < 90 or target["trust"] < 81,
                "treat": happiness < 75 or target["trust"] < 61,
                "train": target["level"] < 100 or target["trust"] < 100,
            }
            reason_by_kind = {
                "feed": (
                    "Adult pets are self-sufficient and do not lose fullness."
                    if is_adult
                    else (
                        f"Growing pet fullness is {fullness}%; feeding is useful at 60% or lower."
                        if fullness <= 60
                        else f"Fullness is already safe at {fullness}%."
                    )
                ),
                "pet": "Raises happiness and can raise trust while granting a little XP.",
                "play": "Raises happiness and trust while granting pet XP.",
                "treat": "Large happiness and trust gain with moderate pet XP.",
                "train": "Best free pet XP action and always grants trust.",
            }
            for kind, knowledge in PET_CARE_ACTION_KNOWLEDGE.items():
                cooldown = await self._command_cooldown(f"pets {kind}")
                needed = bool(needed_by_kind[kind])
                offered = needed and cooldown <= 0
                status = {
                    "kind": kind,
                    "command": knowledge["command"],
                    "pet_id": target["id"],
                    "effects": knowledge["effects"],
                    "cost": int(knowledge["cost"]),
                    "base_cooldown_seconds": int(
                        knowledge["base_cooldown_seconds"]
                    ),
                    "cooldown_remaining_seconds": cooldown,
                    "cooldown_ready": cooldown <= 0,
                    "needed_now": needed,
                    "offered_now": offered,
                    "reason": reason_by_kind[kind],
                }
                care_action_status.append(status)
                if offered:
                    care_options.append(
                        {
                            "kind": kind,
                            "pet_id": target["id"],
                            "cost": int(knowledge["cost"]),
                            "effects": knowledge["effects"],
                            "reason": reason_by_kind[kind],
                            "starvation_emergency": (
                                kind == "feed"
                                and not is_adult
                                and fullness <= PET_EMERGENCY_HUNGER
                            ),
                        }
                    )
        if care_options:
            actions.append(
                {
                    "name": "care_for_pet",
                    "description": (
                        "Perform exactly one currently offered pet-care action. "
                        "Choose an exact kind and pet_id pair from parameters.options; "
                        "never invent an action omitted by its cooldown or need rules."
                    ),
                    "parameters": {"options": care_options},
                }
            )

        skill_options = []
        if pet_cog is not None and hasattr(pet_cog, "SKILL_TREES"):
            for pet in raw_pets:
                learned = set(
                    pet_cog.get_effective_learned_skills(pet)
                    if hasattr(pet_cog, "get_effective_learned_skills")
                    else pet.get("learned_skills") or []
                )
                tree = pet_cog.SKILL_TREES.get(pet.get("element"), {})
                for branch, branch_skills in tree.items():
                    for required_level, skill in branch_skills.items():
                        cost = pet_cog.calculate_skill_cost_with_battery_life(
                            pet, skill["cost"]
                        )
                        if (
                            int(pet.get("level") or 1) >= int(required_level)
                            and int(pet.get("skill_points") or 0) >= int(cost)
                            and skill["name"] not in learned
                        ):
                            skill_options.append(
                                {
                                    "pet_id": int(pet["id"]),
                                    "skill": skill["name"],
                                    "branch": branch,
                                    "cost": int(cost),
                                    "description": skill["description"],
                                }
                            )
        if skill_options:
            actions.append(
                {
                    "name": "learn_pet_skill",
                    "description": "Spend earned pet skill points on one currently learnable skill.",
                    "parameters": {"options": skill_options[:20]},
                }
            )

        collection_used = len(pets) + len(eggs) + pending_splices
        for egg in eggs:
            egg["combat_score"] = egg_combat_score(egg)
        weakest_egg = choose_weakest_egg(eggs)
        state = {
            # The cap tops out at 25, so show the whole collection. Truncating
            # to 12 hid items a tier-4 character owns and made it impossible to
            # identify the weakest egg.
            "pets": sorted(
                pets, key=lambda pet: pet["combat_score"], reverse=True
            )[:25],
            "recommended_combat_pet_id": best_pet_id,
            "eggs": sorted(
                eggs, key=lambda egg: egg["combat_score"], reverse=True
            )[:25],
            "egg_hatching_is_automatic": True,
            "weakest_owned_egg_id": (
                int(weakest_egg["id"]) if weakest_egg is not None else None
            ),
            "egg_scoring": (
                "combat_score is hp*0.1 + attack*2 + defense, which already "
                "includes the species' base stats and the rolled IV points; it "
                "ranks eggs better than iv_percent alone."
            ),
            "collection_used": collection_used,
            "collection_capacity": max_collection,
            "collection_breakdown": {
                "pets": len(pets),
                "unhatched_eggs": len(eggs),
                "pending_splice_requests": pending_splices,
            },
            "collection_slots_free": max(0, max_collection - collection_used),
            "at_collection_capacity": collection_used >= max_collection,
            "capacity_rule": (
                "The cap counts pets, unhatched eggs, and pending splice "
                "requests together. While at capacity, a PvE egg drop forces a "
                "release-or-forfeit choice: Fable offers the swap only when the "
                "new egg outscores the weakest owned egg, and pets are never "
                "released. Eggs hatch into pets and still occupy one slot each, "
                "so being full does not resolve itself over time."
            ),
            "routine_feed_money_reserve": PET_CARE_MONEY_RESERVE,
            "fullness_scale": "100 is fully fed; 0 is starving",
            "adult_pets_are_self_sufficient": True,
            "adult_fullness_and_happiness_do_not_decay": True,
            "emergency_fullness_threshold_for_growing_pets": PET_EMERGENCY_HUNGER,
            "care_target_pet_id": target["id"] if target is not None else None,
            "care_actions": care_action_status,
        }
        return state, actions

    async def _owned_egg_snapshot(self, connection) -> list[dict[str, Any]]:
        """Return every unhatched egg with its comparable combat score."""
        rows = await connection.fetch(
            """
            SELECT id, egg_type, element, "IV", hp, attack, defense, hatch_time
            FROM monster_eggs
            WHERE user_id=$1 AND hatched=FALSE
            ORDER BY id ASC;
            """,
            DENSETSU_USER_ID,
        )
        eggs = []
        for row in rows:
            egg = {
                "id": int(row["id"]),
                "species": str(row["egg_type"]),
                "element": str(row.get("element") or "Unknown"),
                "iv_percent": round(float(row.get("IV") or 0), 2),
                "hp": int(row.get("hp") or 0),
                "attack": int(row.get("attack") or 0),
                "defense": int(row.get("defense") or 0),
                "hatches_in_seconds": self._egg_seconds_remaining(
                    row.get("hatch_time")
                ),
            }
            egg["combat_score"] = egg_combat_score(egg)
            eggs.append(egg)
        return eggs

    async def resolve_egg_capacity(
        self, ctx, connection, *, monster: dict[str, Any], rolled: dict[str, Any]
    ) -> bool:
        """Trade the weakest owned egg for a better incoming drop.

        Fable ranks both sides here and only exposes the swap when the drop is a
        genuine upgrade, mirroring how raid offers only expose accept when the
        odds clear the threshold. A model slip therefore cannot destroy a better
        egg for a worse one, and pets are never release candidates.

        Returns True only when an egg was actually deleted and the caller should
        award the drop.
        """
        incoming = {
            "species": str(monster.get("name") or "Unknown"),
            "element": str(monster.get("element") or "Unknown"),
            "iv_percent": round(float(rolled["IV"]), 2),
            "hp": int(rolled["hp"]),
            "attack": int(rolled["attack"]),
            "defense": int(rolled["defense"]),
        }
        incoming["combat_score"] = egg_combat_score(incoming)

        owned = await self._owned_egg_snapshot(connection)
        weakest = choose_weakest_egg(owned)
        is_upgrade = (
            weakest is not None
            and incoming["combat_score"] > weakest["combat_score"]
        )

        allowed_actions: list[dict[str, Any]] = []
        if is_upgrade:
            allowed_actions.append(
                {
                    "name": "release_egg",
                    "description": (
                        "Release the weakest owned egg to make room, then keep "
                        "the incoming egg. This permanently destroys the "
                        "released egg and is the only way to gain this drop."
                    ),
                    "parameters": {
                        "egg_id": [int(weakest["id"])],
                        "recommended": int(weakest["id"]),
                    },
                }
            )
        allowed_actions.append(
            {
                "name": "decline",
                "description": (
                    "Keep the collection exactly as it is and forfeit the "
                    "incoming egg permanently."
                ),
            }
        )

        event = {
            "event": "egg_capacity_decision",
            "collection": {
                "at_capacity": True,
                "capacity_counts": (
                    "pets plus unhatched eggs plus pending splice requests"
                ),
                "only_eggs_may_be_released_here": True,
                "pets_are_never_release_candidates": True,
            },
            "incoming_egg": incoming,
            "owned_eggs": sorted(
                owned, key=lambda egg: egg["combat_score"], reverse=True
            ),
            "weakest_owned_egg": weakest,
            "replacement_is_an_upgrade": bool(is_upgrade),
            "combat_score_gain_if_replaced": (
                round(incoming["combat_score"] - weakest["combat_score"], 2)
                if is_upgrade
                else 0
            ),
            "scoring": (
                "combat_score is hp*0.1 + attack*2 + defense using each egg's "
                "real stats, which already include both the species' base "
                "stats and its rolled IV points. A high IV percent on a weak "
                "species can still score below a low IV percent on a strong "
                "one, so compare combat_score and not iv_percent."
            ),
            "decision_rule": (
                "Fable offers release_egg only when the incoming egg strictly "
                "outscores the weakest owned egg. When it is not an upgrade, "
                "or no unhatched egg is owned, only decline is available."
            ),
            "allowed_actions": allowed_actions,
        }

        decision = await self.choose_interaction(
            user_id=DENSETSU_USER_ID,
            event=event,
            public_channel=ctx.channel,
            timeout=EGG_CAPACITY_DECISION_TIMEOUT_SECONDS,
        )
        if decision is None or decision.action != "release_egg" or not is_upgrade:
            return False

        try:
            egg_id = int(decision.parameters.get("egg_id"))
        except (TypeError, ValueError):
            logger.warning("Densetsu returned a non-numeric egg_id to release")
            return False
        if egg_id != int(weakest["id"]):
            logger.warning(
                "Densetsu tried to release egg %s instead of the offered %s",
                egg_id,
                weakest["id"],
            )
            return False

        # DELETE ... RETURNING closes the race where the egg hatched or was
        # traded away while the model was deciding.
        released = await connection.fetchrow(
            "DELETE FROM monster_eggs WHERE id=$1 AND user_id=$2 AND "
            "hatched=FALSE RETURNING id, egg_type;",
            egg_id,
            DENSETSU_USER_ID,
        )
        if released is None:
            logger.info(
                "Densetsu's chosen egg %s was already gone; keeping the drop "
                "unclaimed rather than exceeding the cap",
                egg_id,
            )
            return False

        await ctx.send(
            f"Released the **{released['egg_type']}** egg "
            f"({weakest['combat_score']:g} score) to make room for a stronger "
            f"**{incoming['species']}** egg ({incoming['combat_score']:g} score)."
        )
        return True

    async def _collect_pve_state(
        self, battle_cog, *, level: int, in_fight: bool
    ) -> tuple[dict[str, Any], dict[str, Any] | None]:
        cooldown = await self._command_cooldown("pve")
        if battle_cog is None or not hasattr(
            battle_cog, "_get_unlocked_pve_locations"
        ):
            return {"available": False, "cooldown_seconds": cooldown}, None

        locations = battle_cog._get_unlocked_pve_locations(level)
        location_state = []
        for location in locations:
            tiers = sorted(int(key) for key in location.get("tier_weights", {}))
            location_state.append(
                {
                    "id": str(location.get("id")),
                    "name": str(location.get("name")),
                    "unlock_level": int(location.get("unlock_level", 1)),
                    "encounter_tiers": tiers,
                    "god_chance_percent": float(location.get("god_chance", 0)),
                    "frontier_active": bool(location.get("frontier_active")),
                }
            )
        default_location = None
        if hasattr(battle_cog, "_get_user_pve_default_location_id"):
            default_location = await battle_cog._get_user_pve_default_location_id(
                DENSETSU_USER_ID
            )
        splice_enabled = False
        if hasattr(battle_cog, "_get_user_pve_splice_toggle"):
            splice_enabled = await battle_cog._get_user_pve_splice_toggle(
                DENSETSU_USER_ID
            )

        available = cooldown <= 0 and not in_fight and bool(location_state)
        state = {
            "available": available,
            "cooldown_seconds": cooldown,
            "currently_in_fight": in_fight,
            "default_location": default_location,
            "splice_monsters_enabled": bool(splice_enabled),
            "unlocked_locations": location_state,
            "combat_and_egg_drops_are_resolved_by_fable": True,
        }
        action = None
        if available:
            action = {
                "name": "start_pve",
                "description": "Fight one automatic PvE encounter at an unlocked location.",
                "parameters": {
                    "location": [location["id"] for location in location_state],
                    "pool": ["default", "normal", "splice"],
                },
            }
        return state, action

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        try:
            if message.author.id != DENSETSU_USER_ID:
                return
            bridge = await self._bridge_channel()
            if bridge is None or message.channel.id != bridge.id:
                return
            payload = parse_marked_json(message.content, DECISION_MARKER)
            if payload is None:
                return
            if payload.get("payload_attachment") is True:
                payload = await self._read_decision_attachment(message, payload)
                if payload is None:
                    return
            decision = decision_from_payload(payload, message)
            if decision is None:
                return
            future = self._pending.get(decision.event_id)
            if future is not None and not future.done():
                future.set_result(decision)
        except Exception as exc:
            await self._report_error("decision handling", exc)

    async def _read_decision_attachment(
        self, message: discord.Message, envelope: dict[str, Any]
    ) -> dict[str, Any] | None:
        attachments = list(getattr(message, "attachments", []))
        if len(attachments) != 1:
            logger.warning(
                "Ignored Densetsu decision %s without exactly one attachment",
                envelope.get("event_id"),
            )
            return None
        attachment = attachments[0]
        size = int(getattr(attachment, "size", 0) or 0)
        if size > 128 * 1024:
            logger.warning("Ignored oversized Densetsu decision attachment")
            return None
        try:
            raw = await attachment.read()
            payload = json.loads(raw.decode("utf-8"))
        except (AttributeError, UnicodeDecodeError, ValueError):
            logger.warning("Ignored malformed Densetsu decision attachment")
            return None
        if not isinstance(payload, dict):
            return None
        if str(payload.get("event_id")) != str(envelope.get("event_id")):
            logger.warning("Ignored mismatched Densetsu decision attachment")
            return None
        return payload

    async def request_decision(
        self, event: dict[str, Any], *, timeout: float = 90
    ) -> Decision | None:
        channel = await self._bridge_channel()
        if channel is None:
            return None

        event = dict(event)
        event_id = str(event.get("event_id") or uuid.uuid4().hex)
        event["event_id"] = event_id
        payload = json.dumps(event, ensure_ascii=False, separators=(",", ":"))
        content = f"{EVENT_MARKER} {payload}"

        future = asyncio.get_running_loop().create_future()
        self._pending[event_id] = future
        try:
            if len(content) <= 1950:
                await channel.send(
                    content,
                    allowed_mentions=discord.AllowedMentions.none(),
                )
            else:
                envelope = json.dumps(
                    {"event_id": event_id, "payload_attachment": True},
                    separators=(",", ":"),
                )
                attachment = discord.File(
                    io.BytesIO(payload.encode("utf-8")),
                    filename=f"fable-ai-event-{event_id}.json",
                )
                await channel.send(
                    f"{EVENT_MARKER} {envelope}",
                    file=attachment,
                    allowed_mentions=discord.AllowedMentions.none(),
                )
            decision = await asyncio.wait_for(future, timeout=timeout)
        except asyncio.TimeoutError:
            logger.warning("Densetsu timed out for event %s", event_id)
            return None
        finally:
            self._pending.pop(event_id, None)

        choices = decision.ordered_actions()
        batch_allowed = event.get("multiple_actions_allowed") is True
        try:
            configured_maximum = int(event.get("maximum_actions", 1))
        except (TypeError, ValueError):
            configured_maximum = 1
        maximum = (
            min(MAX_AUTOPLAY_ACTIONS, max(1, configured_maximum))
            if batch_allowed
            else 1
        )
        if len(choices) > maximum:
            logger.warning(
                "Densetsu returned %s actions for event %s with maximum %s",
                len(choices),
                event_id,
                maximum,
            )
            return None
        if sum(choice.action == "change_class" for choice in choices) > 1:
            logger.warning(
                "Densetsu returned multiple class-change proposals for event %s",
                event_id,
            )
            return None
        allowed = action_names(event)
        fingerprints = set()
        for choice in choices:
            if choice.action not in allowed:
                logger.warning(
                    "Densetsu returned disallowed action %s for event %s",
                    choice.action,
                    event_id,
                )
                return None
            fingerprint = (
                choice.action,
                json.dumps(choice.parameters, sort_keys=True, separators=(",", ":")),
            )
            if fingerprint in fingerprints:
                logger.warning(
                    "Densetsu returned a duplicate action for event %s", event_id
                )
                return None
            fingerprints.add(fingerprint)
        if len(choices) > 1 and any(
            choice.action == "wait" for choice in choices
        ):
            logger.warning("Densetsu mixed wait into action batch %s", event_id)
            return None
        return decision

    async def choose_interaction(
        self,
        *,
        user_id: int,
        event: dict[str, Any],
        public_channel=None,
        timeout: float = 45,
    ) -> Decision | None:
        """Ask Densetsu to resolve a bounded in-game prompt."""
        if not await self.is_active_for(user_id):
            return None
        decision = await self.request_decision(event, timeout=timeout)
        if decision is None or not await self.is_active_for(user_id):
            return None
        if public_channel is not None and decision.dialogue:
            self._relay_dialogue(public_channel.id, decision.dialogue)
        return decision

    async def speak(
        self,
        channel_id: int,
        text: str,
        *,
        mention_user_ids: list[int] | None = None,
    ) -> None:
        bridge = await self._bridge_channel()
        text = text.strip()[:1900]
        if bridge is None or not text:
            return
        request: dict[str, Any] = {"channel_id": int(channel_id), "text": text}
        if mention_user_ids:
            # Densetsu suppresses every mention unless Fable names exact user
            # IDs here. @everyone and roles are never relayable.
            request["mention_user_ids"] = [
                int(value) for value in mention_user_ids[:4]
            ]
        payload = json.dumps(
            request,
            ensure_ascii=False,
            separators=(",", ":"),
        )
        await bridge.send(
            f"{SPEAK_MARKER} {payload}",
            allowed_mentions=discord.AllowedMentions.none(),
        )

    def _background_task_finished(self, task: asyncio.Task) -> None:
        if task.cancelled():
            return
        try:
            task.result()
        except Exception as exc:
            self._queue_error_report("background interaction", exc)

    def _start_background(self, coroutine) -> asyncio.Task:
        task = asyncio.create_task(coroutine)
        task.add_done_callback(self._background_task_finished)
        return task

    def _relay_dialogue(self, channel_id: int, text: str) -> None:
        self._start_background(self.speak(channel_id, text))

    async def _densetsu_user(self, ctx):
        """Resolve a Densetsu user object the raid can treat as a participant."""
        guild = getattr(ctx, "guild", None)
        if guild is not None:
            member = guild.get_member(DENSETSU_USER_ID)
            if member is not None:
                return member
        user = self.bot.get_user(DENSETSU_USER_ID)
        if user is not None:
            return user
        try:
            return await self.bot.fetch_user(DENSETSU_USER_ID)
        except discord.HTTPException:
            return None

    async def offer_evil_ritual_follower(self, ctx, join_view) -> bool:
        """Ask the ritual host for a follower slot and join if they answer.

        Densetsu cannot click the join buttons, so it asks in the channel
        instead. Only EVIL_RITUAL_HOST_USER_ID's own reply or mention admits it,
        and it only ever asks for the follower role.
        """
        if not await self.is_active_for(DENSETSU_USER_ID):
            return False
        densetsu = await self._densetsu_user(ctx)
        if densetsu is None:
            return False
        if (
            densetsu in join_view.follower_joined
            or densetsu in join_view.leader_joined
        ):
            return False

        # The ritual silently drops anyone who does not follow its god, so do
        # not ask for a slot Densetsu would be refused at roll call anyway.
        async with self.bot.pool.acquire() as connection:
            god = await connection.fetchval(
                'SELECT god FROM profile WHERE "user"=$1;', DENSETSU_USER_ID
            )
        if str(god or "") != EVIL_RITUAL_GOD:
            logger.info(
                "Densetsu follows %r, not %s, so it did not ask to join the "
                "Infernal Ritual",
                god,
                EVIL_RITUAL_GOD,
            )
            return False

        event = {
            "event": "evil_ritual_join_request",
            "ritual": {
                "name": "Infernal Ritual",
                "god": EVIL_RITUAL_GOD,
                "host_user_id": EVIL_RITUAL_HOST_USER_ID,
                "densetsu_follows_this_god": True,
            },
            "role_requested": "follower",
            "role_is_not_negotiable": (
                "Densetsu may only ask to join as a follower. It never asks to "
                "be Champion or Priest and cannot lead the ritual."
            ),
            "what_a_follower_does": (
                "Followers act as a group each turn. Densetsu will chant every "
                "turn, which adds 1% ritual progress per chanting follower."
            ),
            "permission_rule": (
                "Only the host may admit Densetsu, by replying to this message "
                "or mentioning Densetsu. Fable handles that; return the asking "
                "line only."
            ),
            "allowed_actions": [
                {
                    "name": "request_follower_slot",
                    "description": (
                        "Ask the host for permission to join the ritual as a "
                        "follower. Put the in-character request in dialogue."
                    ),
                },
                {
                    "name": "decline",
                    "description": "Stay out of this ritual and say nothing.",
                },
            ],
        }

        decision = await self.choose_interaction(
            user_id=DENSETSU_USER_ID,
            event=event,
            timeout=EVIL_RITUAL_ASK_TIMEOUT_SECONDS,
        )
        if decision is not None and decision.action == "decline":
            return False
        # A bridge or model failure still asks, because the host explicitly
        # wanted to be offered the choice.
        line = ""
        if decision is not None:
            line = (decision.dialogue or "").strip()
        await self.speak(
            ctx.channel.id,
            f"<@{EVIL_RITUAL_HOST_USER_ID}> {line or EVIL_RITUAL_DEFAULT_ASK}",
            mention_user_ids=[EVIL_RITUAL_HOST_USER_ID],
        )

        # Densetsu posts the question itself, so learn the message id to make
        # reply detection exact rather than guessing from the cache.
        channel_id = ctx.channel.id

        def is_densetsu_post(message: discord.Message) -> bool:
            return (
                message.author.id == DENSETSU_USER_ID
                and message.channel.id == channel_id
            )

        try:
            asked = await self.bot.wait_for(
                "message", check=is_densetsu_post, timeout=30
            )
            asked_id = asked.id
        except asyncio.TimeoutError:
            logger.warning("Densetsu's ritual request was never relayed")
            asked_id = None

        def is_host_confirmation(message: discord.Message) -> bool:
            if (
                message.author.id != EVIL_RITUAL_HOST_USER_ID
                or message.channel.id != channel_id
            ):
                return False
            if any(user.id == DENSETSU_USER_ID for user in message.mentions):
                return True
            reference = message.reference
            if reference is None:
                return False
            if asked_id is not None and reference.message_id == asked_id:
                return True
            replied_to = getattr(reference, "resolved", None)
            author = getattr(replied_to, "author", None)
            return author is not None and author.id == DENSETSU_USER_ID

        try:
            answer = await self.bot.wait_for(
                "message",
                check=is_host_confirmation,
                timeout=EVIL_RITUAL_CONFIRM_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            logger.info("The ritual host never answered Densetsu's request")
            return False

        if self._is_ritual_refusal(getattr(answer, "content", "")):
            logger.info("The ritual host refused Densetsu's request")
            await self._speak_ritual_reaction(ctx, accepted=False)
            return False

        if not await self.is_active_for(DENSETSU_USER_ID):
            return False
        if (
            densetsu in join_view.follower_joined
            or densetsu in join_view.leader_joined
        ):
            return False
        join_view.follower_joined.append(densetsu)
        await self._speak_ritual_reaction(ctx, accepted=True)
        logger.info("Densetsu joined the Infernal Ritual as a follower")
        return True

    @staticmethod
    def _is_ritual_refusal(text: str) -> bool:
        """Read the host's answer as a refusal rather than permission."""
        cleaned = EVIL_RITUAL_FALSE_REFUSAL.sub(" ", str(text or ""))
        return bool(EVIL_RITUAL_REFUSAL.search(cleaned))

    async def _speak_ritual_reaction(self, ctx, *, accepted: bool) -> None:
        """Answer the host in character, and never graciously when refused."""
        if accepted:
            options = [
                {
                    "name": "taunt_host",
                    "description": (
                        "Accept the slot with a smug, cocky, or backhanded line "
                        "instead of thanks."
                    ),
                },
                {
                    "name": "acknowledge_quietly",
                    "description": "Accept with a short, flat line.",
                },
            ]
        else:
            # Being refused always gets an answer; only its wording is the
            # model's to choose.
            options = [
                {
                    "name": "mock_refusal",
                    "description": (
                        "Answer the refusal with contempt, mockery, or a "
                        "threat. Do not accept it gracefully."
                    ),
                }
            ]

        event = {
            "event": "evil_ritual_join_answer",
            "host_user_id": EVIL_RITUAL_HOST_USER_ID,
            "host_answer": "accepted" if accepted else "refused",
            "outcome": (
                "Densetsu is in the ritual as a follower and will chant every "
                "turn."
                if accepted
                else "Densetsu has been shut out of the ritual entirely and "
                "cannot join by any other route."
            ),
            "tone": (
                "Densetsu is proud and does not beg or thank anyone. A refusal "
                "is an insult and should be answered with contempt, mockery, or "
                "a threat, never politeness or an apology. Being let in earns no "
                "gratitude either; smug, cocky, or backhanded is welcome. Stay "
                "in character, keep it to one line, and put it in dialogue."
            ),
            "allowed_actions": options,
        }

        decision = await self.choose_interaction(
            user_id=DENSETSU_USER_ID,
            event=event,
            timeout=EVIL_RITUAL_ASK_TIMEOUT_SECONDS,
        )
        line = ""
        if decision is not None:
            line = (decision.dialogue or "").strip()
        if not line:
            line = (
                EVIL_RITUAL_DEFAULT_ACCEPTED
                if accepted
                else EVIL_RITUAL_DEFAULT_REFUSED
            )
        await self.speak(
            ctx.channel.id,
            f"<@{EVIL_RITUAL_HOST_USER_ID}> {line}",
            mention_user_ids=[EVIL_RITUAL_HOST_USER_ID],
        )

    def start_gift_received(
        self,
        *,
        recipient_id: int,
        sender,
        gift: dict[str, Any],
        public_channel,
    ) -> asyncio.Task | None:
        if int(recipient_id) != DENSETSU_USER_ID:
            return None
        return self._start_background(
            self._handle_gift_received(
                sender=sender,
                gift=gift,
                public_channel=public_channel,
            )
        )

    async def _handle_gift_received(self, *, sender, gift, public_channel) -> None:
        if not await self.is_active_for(DENSETSU_USER_ID):
            return
        event = {
            "event": "gift_received",
            "sender": {
                "discord_id": int(sender.id),
                "display_name": str(sender.display_name),
            },
            "gift": dict(gift),
            "transfer_already_completed": True,
            "allowed_actions": [
                {
                    "name": "acknowledge",
                    "description": "Thank or react to the sender in character.",
                },
                {
                    "name": "stay_silent",
                    "description": "Do not post a public response.",
                },
            ],
        }
        decision = await self.choose_interaction(
            user_id=DENSETSU_USER_ID,
            event=event,
            timeout=30,
        )
        if decision is None or decision.action != "acknowledge":
            return
        await self.speak(
            public_channel.id,
            decision.dialogue or "Thanks. I'll put that to good use.",
        )

    @staticmethod
    def _serialize_trade_offer(offer: dict[str, Any]) -> dict[str, Any]:
        return {
            "money": int(offer.get("money", 0) or 0),
            "crates": {
                str(name): int(amount)
                for name, amount in offer.get("crates", {}).items()
                if amount
            },
            "items": [
                {
                    "id": int(item["id"]),
                    "name": str(item["name"]),
                    "type": str(item["type"]),
                    "damage": int(item["damage"] or 0),
                    "armor": int(item["armor"] or 0),
                }
                for item in offer.get("items", [])
            ],
            "resources": {
                str(name): int(amount)
                for name, amount in offer.get("resources", {}).items()
                if amount
            },
            "consumables": {
                str(name): int(amount)
                for name, amount in offer.get("consumables", {}).items()
                if amount
            },
        }

    def start_trade_offer_decision(self, *, view, trans, public_channel):
        participants = list(trans.get("content", {}).keys())
        if not any(int(user.id) == DENSETSU_USER_ID for user in participants):
            return None
        serialized_offers = [
            self._serialize_trade_offer(offer)
            for offer in trans.get("content", {}).values()
        ]
        if not any(any(offer.values()) for offer in serialized_offers):
            return None
        return self._start_background(
            self._handle_trade_offer_decision(
                view=view,
                trans=trans,
                public_channel=public_channel,
            )
        )

    async def _handle_trade_offer_decision(self, *, view, trans, public_channel) -> None:
        if not await self.is_active_for(DENSETSU_USER_ID) or view.result is not None:
            return
        participants = list(trans.get("content", {}).keys())
        densetsu = next(
            (user for user in participants if int(user.id) == DENSETSU_USER_ID),
            None,
        )
        other = next(
            (user for user in participants if int(user.id) != DENSETSU_USER_ID),
            None,
        )
        if densetsu is None or other is None:
            return
        densetsu_gives = self._serialize_trade_offer(trans["content"][densetsu])
        densetsu_receives = self._serialize_trade_offer(trans["content"][other])
        event = {
            "event": "trade_offer_confirmation",
            "counterparty_has_confirmed": True,
            "decision_requested_after_counterparty_confirmation": True,
            "counterparty": {
                "discord_id": int(other.id),
                "display_name": str(other.display_name),
            },
            "densetsu_gives": densetsu_gives,
            "densetsu_receives": densetsu_receives,
            "warning": (
                "Accepting transfers these exact assets. Fable revalidates ownership and "
                "balances atomically before completing the trade."
            ),
            "allowed_actions": [
                {"name": "accept", "description": "Accept this exact final offer."},
                {"name": "decline", "description": "Cancel the trade without transferring anything."},
            ],
        }
        decision = await self.choose_interaction(
            user_id=DENSETSU_USER_ID,
            event=event,
            timeout=45,
        )
        if decision is None or view.result is not None:
            return
        if (
            self._serialize_trade_offer(trans["content"][densetsu]) != densetsu_gives
            or self._serialize_trade_offer(trans["content"][other]) != densetsu_receives
        ):
            logger.info("Ignored a Densetsu trade decision because the offer changed")
            return
        if decision.action == "accept":
            changed, message = await view.accept_participant(DENSETSU_USER_ID)
        else:
            changed, message = await view.decline_participant(DENSETSU_USER_ID, densetsu)
        if changed:
            await self.speak(
                public_channel.id,
                decision.dialogue or message,
            )

    async def _collect_adventure_risk(
        self,
        profile,
        *,
        level: int,
        class_names: list[str],
        booster_state: dict[str, Any],
        include_levels: set[int] | None = None,
    ) -> dict[str, Any]:
        damage, armor = await self.bot.get_damage_armor_for(
            DENSETSU_USER_ID,
            classes=class_names,
            race=str(profile["race"] or "Human"),
        )
        buildings = await self.bot.get_city_buildings(profile["guild"])
        city_level = int(buildings["adventure_building"] or 0) if buildings else 0
        chance_bonus = 5 if level > 30 else city_level
        luck = profile["luck"] or Decimal("1")
        active_seconds = booster_state.get("active_seconds") or {}
        ritualist = any(
            game_class is not None and game_class.in_class_line(Ritualist)
            for game_class in (class_from_string(name) for name in class_names)
        )
        all_options = []
        for adventure_level in range(1, min(level, 100) + 1):
            duration_seconds = adventure_level * 3600
            duration_seconds *= max(0, 100 - city_level) / 100
            # The live adventure command currently applies its tier-4 25% reduction.
            duration_seconds *= 0.75
            if int(active_seconds.get("time", 0) or 0) > 0:
                duration_seconds /= 2
            duration_seconds = max(1, int(duration_seconds))

            without_booster = rpgtools.calcchance_probability(
                damage,
                armor,
                adventure_level,
                level,
                luck,
                booster=False,
                bonus=chance_bonus,
            )
            with_booster = rpgtools.calcchance_probability(
                damage,
                armor,
                adventure_level,
                level,
                luck,
                booster=True,
                bonus=chance_bonus,
            )
            luck_active_at_completion = int(
                active_seconds.get("luck", 0) or 0
            ) >= duration_seconds + 60
            money_active_at_completion = int(
                active_seconds.get("money", 0) or 0
            ) >= duration_seconds + 60
            estimated = with_booster if luck_active_at_completion else without_booster
            loot_chance = 5 if adventure_level == 1 else 5 + 1.5 * adventure_level
            if ritualist:
                loot_chance *= 2
            minimum_gold = round(20 * adventure_level * luck)
            maximum_gold = round(60 * adventure_level * luck)
            boosted_minimum_gold = int(minimum_gold * 1.25)
            boosted_maximum_gold = int(maximum_gold * 1.25)
            if money_active_at_completion:
                estimated_gold = [boosted_minimum_gold, boosted_maximum_gold]
            else:
                estimated_gold = [int(minimum_gold), int(maximum_gold)]
            minimum_xp = 250 * adventure_level
            maximum_xp = 500 * adventure_level
            if level < 29:
                minimum_xp = int(minimum_xp * 1.25)
                maximum_xp = int(maximum_xp * 1.25)
            all_options.append(
                {
                    "level": adventure_level,
                    "success_chance_percent": round(estimated, 2),
                    "death_chance_percent": round(100 - estimated, 2),
                    "success_without_luck_booster_percent": round(without_booster, 2),
                    "success_with_luck_booster_percent": round(with_booster, 2),
                    "luck_booster_expected_active_at_completion": luck_active_at_completion,
                    "money_booster_expected_active_at_completion": money_active_at_completion,
                    "duration_seconds": duration_seconds,
                    "success_reward_ranges": {
                        "gold": estimated_gold,
                        "gold_without_money_booster": [
                            int(minimum_gold),
                            int(maximum_gold),
                        ],
                        "gold_with_money_booster": [
                            boosted_minimum_gold,
                            boosted_maximum_gold,
                        ],
                        "xp": [minimum_xp, maximum_xp],
                        "loot_item_chance_percent": min(100, round(loot_chance, 2)),
                    },
                }
            )
        balanced = [
            option
            for option in all_options
            if option["success_chance_percent"]
            >= ADVENTURE_BALANCED_SUCCESS_THRESHOLD
        ]
        recommended = (
            max(balanced, key=lambda option: option["level"])["level"]
            if balanced
            else max(
                all_options,
                key=lambda option: option["success_chance_percent"],
            )["level"]
        )
        candidate_levels = {1, min(level, 100), recommended}
        candidate_levels.update(include_levels or set())
        candidate_levels.update(
            candidate
            for candidate in range(recommended - 2, recommended + 3)
            if 1 <= candidate <= min(level, 100)
        )
        for threshold in (99, 95, 90, 80, 70, 50):
            eligible = [
                option
                for option in all_options
                if option["success_chance_percent"] >= threshold
            ]
            if eligible:
                candidate_levels.add(
                    max(eligible, key=lambda option: option["level"])["level"]
                )
        options = [
            option
            for option in all_options
            if option["level"] in candidate_levels
        ]
        return {
            "current_resolution_stats": {
                "effective_damage": self._json_safe_raid_value(damage),
                "effective_armor": self._json_safe_raid_value(armor),
                "combined_power": self._json_safe_raid_value(damage + armor),
                "god_luck_multiplier": self._json_safe_raid_value(luck),
                "city_adventure_building_level": city_level,
                "chance_bonus": chance_bonus,
            },
            "options": options,
            "candidate_levels_are_curated_for_context_size": True,
            "maximum_unlocked_level": min(level, 100),
            "balanced_recommendation": recommended,
            "balanced_threshold_percent": ADVENTURE_BALANCED_SUCCESS_THRESHOLD,
            "failure_effect": "Adds one death only; it does not remove money, XP, gear, pets, or the character.",
            "odds_are_recalculated_at_claim": True,
            "claim_uses_current_equipment_luck_city_and_luck_booster": True,
        }

    async def _collect_paid_raid_upgrade_state(
        self,
        profile,
        raid_stats: dict[str, Any],
    ) -> tuple[dict[str, Any], dict[str, Any] | None]:
        raid_cog = self.bot.get_cog("Raid")
        cooldown = await self._command_cooldown("increase")
        if raid_cog is None or not hasattr(raid_cog, "getpriceto"):
            return {"available": False, "cooldown_seconds": cooldown}, None
        breakdown = raid_stats.get("attack_defense_breakdown") or {}
        base_attack = float(breakdown.get("equipment_class_race_attack", 0) or 0)
        base_defense = float(breakdown.get("equipment_class_race_defense", 0) or 0)
        money = int(profile["money"] or 0)
        raw_options = [
            {
                "upgrade": "damage",
                "current_level": float(profile["atkmultiply"]),
                "next_level": float(Decimal(profile["atkmultiply"]) + Decimal("0.1")),
                "price": int(
                    raid_cog.getpriceto(
                        Decimal(profile["atkmultiply"]) + Decimal("0.1")
                    )
                ),
                "effect": "+0.1 profile raid attack multiplier",
                "estimated_final_stat_gain": round(base_attack * 0.1, 3),
            },
            {
                "upgrade": "defense",
                "current_level": float(profile["defmultiply"]),
                "next_level": float(Decimal(profile["defmultiply"]) + Decimal("0.1")),
                "price": int(
                    raid_cog.getpriceto(
                        Decimal(profile["defmultiply"]) + Decimal("0.1")
                    )
                ),
                "effect": "+0.1 profile raid defense multiplier",
                "estimated_final_stat_gain": round(base_defense * 0.1, 3),
            },
            {
                "upgrade": "health",
                "current_level": float(profile["hplevel"]),
                "next_level": float(Decimal(profile["hplevel"]) + Decimal("0.1")),
                "price": int(
                    raid_cog.getpricetohp(
                        Decimal(profile["hplevel"]) + Decimal("0.1")
                    )
                ),
                "effect": "+5 additive maximum combat HP",
                "estimated_final_stat_gain": 5,
            },
        ]
        for option in raw_options:
            option["money_after_purchase"] = money - option["price"]
            option["affordable_with_reserve"] = (
                option["price"] > 0
                and money - option["price"] >= PAID_RAID_UPGRADE_MONEY_RESERVE
            )
        offered = [
            option for option in raw_options if option["affordable_with_reserve"]
        ]
        action = None
        if cooldown <= 0 and offered:
            action = {
                "name": "purchase_raid_upgrade",
                "description": (
                    "Spend gold on one normal $increase raid-stat step while "
                    "preserving the configured cash reserve."
                ),
                "parameters": {
                    "upgrade": [option["upgrade"] for option in offered],
                },
                "available_options": offered,
            }
        return {
            "available": bool(action),
            "cooldown_seconds": cooldown,
            "money": money,
            "minimum_money_reserve": PAID_RAID_UPGRADE_MONEY_RESERVE,
            "all_next_upgrades": raw_options,
            "offered_upgrades": offered if cooldown <= 0 else [],
            "purchase_is_permanent": True,
            "does_not_change_adventure_success": True,
        }, action

    async def _collect_class_specialization_state(
        self,
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        state: dict[str, Any] = {
            "unlock_requirements": {
                "character_level": MASTERY_UNLOCK_LEVEL,
                "final_class_grade": 7,
                "mastery_points_for_that_class_line": MASTERY_UNLOCK_POINTS,
            },
            "mastery_point_sources": dict(MASTERY_AWARDS),
            "mastery_awards_apply_to_each_equipped_grade_7_line": True,
            "gauntlet_and_ice_dragon_shared_daily_mastery_cap": (
                GAUNTLET_ICE_DRAGON_MASTERY_DAILY_CAP
            ),
            "initial_specialization_choice_is_free": True,
            "chosen_path_persists_for_its_class_line_when_unequipped": True,
            "changing_a_chosen_path_requires_reset": True,
            "reset_cost": RESPEC_COST,
            "lines": {},
        }
        actions: list[dict[str, Any]] = []
        cog = self.bot.get_cog("Specializations")
        if cog is None or not hasattr(cog, "ensure_tables"):
            state["available"] = False
            return state, actions

        await cog.ensure_tables()
        mastery = await get_class_mastery(self.bot, DENSETSU_USER_ID)
        free_claim = await get_free_mastery_claim(self.bot, DENSETSU_USER_ID)
        state["one_time_free_100_mastery_gift"] = {
            "available": free_claim is None,
            "used_for_class_line": (
                free_claim["class_line"] if free_claim is not None else None
            ),
            "strategic_note": (
                "This irreversible gift can instantly satisfy the mastery-points "
                "gate for one line. Preserve it until the intended long-term class "
                "and specialization path is clear."
            ),
        }
        async with self.bot.pool.acquire() as connection:
            rows = await connection.fetch(
                "SELECT class_line, spec_key FROM class_specs WHERE user_id=$1;",
                DENSETSU_USER_ID,
            )
        chosen = {str(row["class_line"]): str(row["spec_key"]) for row in rows}
        options = []
        mastery_claim_options = []
        for line, raw_line_state in (mastery.get("lines") or {}).items():
            line_state = dict(raw_line_state)
            chosen_key = chosen.get(line)
            chosen_spec = SPECS.get(chosen_key) if chosen_key else None
            line_state["chosen_specialization"] = (
                {
                    "spec_key": chosen_key,
                    "name": chosen_spec["name"],
                    "active_now": bool(
                        line_state.get("equipped")
                        and int(line_state.get("grade") or 0) >= 7
                    ),
                    "effect_at_current_grade": (
                        describe_spec(chosen_key, int(line_state["grade"]))
                        if line_state.get("equipped")
                        and int(line_state.get("grade") or 0) >= 7
                        else None
                    ),
                }
                if chosen_spec is not None
                else None
            )
            state["lines"][line] = line_state
            if (
                free_claim is None
                and int(mastery.get("level") or 0) >= MASTERY_UNLOCK_LEVEL
                and line_state.get("equipped")
                and int(line_state.get("grade") or 0) >= 7
                and int(line_state.get("points") or 0) < MASTERY_UNLOCK_POINTS
            ):
                mastery_claim_options.append(
                    {
                        "class_line": line,
                        "current_points": int(line_state.get("points") or 0),
                        "points_after_claim": MASTERY_UNLOCK_POINTS,
                        "enables_specialization_choice": True,
                        "cost": 0,
                    }
                )
            if (
                line_state.get("equipped")
                and line_state.get("unlocked")
                and chosen_key is None
            ):
                grade = max(1, int(line_state.get("grade") or 1))
                for spec_key, spec in specs_for_line(line).items():
                    options.append(
                        {
                            "spec_key": spec_key,
                            "name": spec["name"],
                            "class_line": line,
                            "kind": spec["kind"],
                            "passive": spec["passive"],
                            "effect_at_current_grade": describe_spec(spec_key, grade),
                            "cost": 0,
                        }
                    )

        state["available"] = True
        state["character_level"] = int(mastery.get("level") or 0)
        if mastery_claim_options:
            actions.append(
                {
                    "name": "claim_specialization_mastery",
                    "description": (
                        "Irreversibly use the one-time free mastery gift on one "
                        "equipped final-evolution class line, bringing it to 100 "
                        "mastery so its specialization can be chosen. Compare both "
                        "class roadmaps before committing the gift."
                    ),
                    "priority": "optional_irreversible_build_choice",
                    "parameters": {"options": mastery_claim_options},
                }
            )
        if options:
            actions.append(
                {
                    "name": "choose_specialization",
                    "description": (
                        "Choose one unlocked specialization using its exact effects. "
                        "The initial choice is free and immediately beneficial, but "
                        f"changing it later requires a ${RESPEC_COST:,} reset."
                    ),
                    "priority": "high_value_free_progression_choice",
                    "parameters": {"options": options},
                }
            )
        return state, actions

    async def _collect_state(self) -> dict[str, Any]:
        async with self.bot.pool.acquire() as connection:
            profile = await connection.fetchrow(
                'SELECT name, xp, money, "class", health, stathp, statatk, '
                'statdef, statpoints, atkmultiply, defmultiply, hplevel, '
                'luck, race, cv, god, favor, reset_points, guild, '
                'tier, spookyclass, chrissy2023, crates_common, crates_uncommon, crates_rare, '
                'crates_magic, crates_legendary, crates_divine, '
                'crates_mystery, crates_fortune, crates_materials, '
                'time_booster, luck_booster, money_booster '
                'FROM profile WHERE "user"=$1;',
                DENSETSU_USER_ID,
            )
            tower = await connection.fetchrow(
                "SELECT level, prestige FROM battletower WHERE id=$1;",
                DENSETSU_USER_ID,
            )

        if profile is None:
            return {
                "event": "autoplay_tick",
                "multiple_actions_allowed": True,
                "maximum_actions": MAX_AUTOPLAY_ACTIONS,
                "actions_execute_in_order_with_fresh_state_validation": True,
                "character": None,
                "allowed_actions": [
                    {
                        "name": "create_character",
                        "description": "Create Densetsu's new Fable character.",
                        "parameters": {"name": DEFAULT_CHARACTER_NAME},
                    },
                    {"name": "wait", "description": "Take no action."},
                ],
            }

        level = int(rpgtools.xptolevel(profile["xp"]))
        class_names = list(profile["class"] or ["No Class", "No Class"])
        available_classes = available_player_classes(profile)
        class_knowledge = class_knowledge_payload(available_classes)
        async with self.bot.pool.acquire() as connection:
            health_state = await self._collect_health_state(
                connection, profile, level=level
            )
            equipment_state = await self._collect_equipment_state(
                connection, class_names, available_classes
            )
            amulet_state, amulet_actions = await self._collect_amulet_state(
                connection, level=level
            )
            pet_state, pet_actions = await self._collect_pet_state(
                connection,
                money=int(profile["money"]),
                tier=int(profile["tier"] or 0),
            )
            reward_state, reward_actions = await self._collect_reward_state(
                connection, profile
            )
            booster_state, booster_actions = await self._collect_booster_state(profile)
        specialization_state, specialization_actions = (
            await self._collect_class_specialization_state()
        )
        adventure = await self.bot.get_adventure(DENSETSU_USER_ID)
        adventure_risk = await self._collect_adventure_risk(
            profile,
            level=level,
            class_names=class_names,
            booster_state=booster_state,
            include_levels={int(adventure[0])} if adventure is not None else None,
        )
        tower_cooldown = await self.bot.redis.ttl(
            f"cd:{DENSETSU_USER_ID}:battletower fight"
        )
        class_change_cooldown = await self._command_cooldown("class")
        battle_cog = self.bot.get_cog("Battles")
        raid_stats = await self._collect_raid_stats(DENSETSU_USER_ID)
        class_strategy_state = await self._collect_class_strategy_state(
            class_names=class_names,
            state={
                "character": {"level": level},
                "equipment": equipment_state,
                "companions": pet_state,
                "raid_stats": raid_stats,
            },
        )
        paid_raid_upgrades, paid_raid_action = (
            await self._collect_paid_raid_upgrade_state(profile, raid_stats)
        )
        in_fight = False
        if battle_cog is not None and hasattr(battle_cog, "is_player_in_fight"):
            try:
                in_fight = await battle_cog.is_player_in_fight(DENSETSU_USER_ID)
            except Exception:
                logger.exception("Could not read Densetsu's active-fight state")

        actions: list[dict[str, Any]] = []
        actions.extend(reward_actions)
        actions.extend(booster_actions)
        actions.extend(amulet_actions)
        actions.extend(pet_actions)
        actions.extend(specialization_actions)
        faith_state, race_choice_state, identity_actions = (
            self._collect_identity_choice_state(profile)
        )
        actions.extend(identity_actions)
        if paid_raid_action is not None:
            actions.append(paid_raid_action)
        unspent_stat_points = int(profile["statpoints"] or 0)
        stat_progression = {
            "unspent": unspent_stat_points,
            "allocated": {
                "attack": int(profile["statatk"] or 0),
                "defense": int(profile["statdef"] or 0),
                "health": int(profile["stathp"] or 0),
            },
            "per_point_effects": {
                "attack": "+0.1 raid attack multiplier",
                "defense": "+0.1 raid defense multiplier",
                "health": "+50 fresh maximum combat HP",
            },
            "does_not_change_adventure_success": True,
            "allocation_is_permanent_without_a_reset_potion": True,
        }
        if unspent_stat_points > 0:
            actions.append(
                {
                    "name": "allocate_stat_points",
                    "description": (
                        "Permanently spend available progression points to improve "
                        "raid attack, raid defense, or fresh combat HP."
                    ),
                    "parameters": {
                        "stat": ["attack", "defense", "health"],
                        "amount": {"minimum": 1, "maximum": unspent_stat_points},
                    },
                }
            )
        recommended_equipment = equipment_state.get("recommended")
        current_equipment = equipment_state.get("current") or {}
        if (
            recommended_equipment
            and set(recommended_equipment.get("item_ids", []))
            != set(current_equipment.get("item_ids", []))
            and float(recommended_equipment.get("score", 0))
            > float(current_equipment.get("score", 0))
        ):
            actions.append(
                {
                    "name": "optimize_equipment",
                    "description": (
                        "Equip Fable's highest-scoring owned loadout after real "
                        "class, starforge, and soulbound bonuses."
                    ),
                    "parameters": {
                        "item_ids": recommended_equipment["item_ids"]
                    },
                }
            )
        empty_slots = [
            index
            for index, value in enumerate(class_names[:2])
            if value == "No Class" and (index == 0 or level >= 12)
        ]
        empty_class_options = class_choice_options(
            class_names=class_names,
            slots=empty_slots,
            available_classes=available_classes,
            level=level,
            cost=0,
        )
        if empty_class_options and class_change_cooldown <= 0:
            actions.insert(
                0,
                {
                    "name": "choose_class",
                    "description": (
                        "Fill an unlocked empty class slot for free. Every class gives "
                        "immediate permanent benefits, so leaving this unresolved in "
                        "favor of wait has no strategic value."
                    ),
                    "priority": "required_free_progression",
                    "parameters": {"options": empty_class_options},
                }
            )

        filled_slots = [
            index
            for index, value in enumerate(class_names[:2])
            if value != "No Class" and (index == 0 or level >= 12)
        ]
        paid_class_options = class_choice_options(
            class_names=class_names,
            slots=filled_slots,
            available_classes=available_classes,
            level=level,
            cost=CLASS_CHANGE_COST,
        )
        plan_by_slot = {
            int(plan["slot"]): plan
            for plan in class_strategy_state.get("recorded_slot_plans", [])
            if isinstance(plan, dict) and plan.get("slot") in (0, 1)
        }
        pending_class_change = class_strategy_state.get(
            "pending_paid_change_proposal"
        )
        equipment_fit = equipment_state.get("_hypothetical_class_change_fit") or {}
        class_pet_fit_by_class = {
            key: class_pet_fit(key, level=level, pet_state=pet_state)
            for key in available_classes
        }
        for option in [*empty_class_options, *paid_class_options]:
            slot = int(option["slot"])
            class_key = str(option["class"])
            option["class_knowledge_key"] = class_key
            option["read_full_mechanics_from_class_knowledge_key"] = True
            option["equipment_fit"] = (
                equipment_fit.get(str(slot), {}).get(class_key, {})
            )
            option["pet_fit_key"] = class_key
            current_plan = plan_by_slot.get(slot)
            option["consistency"] = {
                "reverts_the_recorded_previous_class": bool(
                    current_plan
                    and class_key in current_plan.get("previous_class_keys", [])
                ),
                "read_current_plan_from_class_system": current_plan is not None,
                "cooldown_expiry_is_not_a_strategic_reason": True,
            }
            if int(option["cost"]) > 0:
                confirms_pending = bool(
                    isinstance(pending_class_change, dict)
                    and int(pending_class_change.get("slot", -1)) == slot
                    and str(pending_class_change.get("expected_current") or "")
                    == str(option["replaces"])
                    and str(pending_class_change.get("to_class_key") or "")
                    == class_key
                )
                option["confirmation"] = {
                    "confirms_pending_proposal": confirms_pending,
                    "first_selection_records_proposal_without_changing_class": not confirms_pending,
                    "same_exact_choice_on_a_later_decision_executes_change": True,
                }
            else:
                option["confirmation"] = {
                    "initial_empty_slot_selection_is_immediate_and_free": True,
                    "paid_change_confirmation_not_required": True,
                }
        equipment_state.pop("_hypothetical_class_change_fit", None)
        if (
            paid_class_options
            and class_change_cooldown <= 0
            and int(profile["money"] or 0) >= CLASS_CHANGE_COST
        ):
            actions.append(
                {
                    "name": "change_class",
                    "description": (
                        f"Propose or confirm replacing one class line for "
                        f"${CLASS_CHANGE_COST:,}. The same exact choice must be made on "
                        "two separate decisions before any class or gold changes. Only "
                        "do this for a material long-term improvement supported by the "
                        "option's equipment_fit plus the keyed pet fit, full class "
                        "mechanics, and recorded build plan. A replacement starts at "
                        "grade 1, then free "
                        "evolve_classes catches it up to the current level unlock."
                    ),
                    "priority": "optional_major_build_change",
                    "parameters": {"options": paid_class_options},
                }
            )
        class_progression, class_progression_summary = class_progression_payload(
            class_names, level
        )
        evolution_ready = class_progression_summary["evolution_available_now"]
        if evolution_ready:
            actions.insert(
                0,
                {
                    "name": "evolve_classes",
                    "description": (
                        "Immediately and freely upgrade every class to the highest "
                        "evolution already unlocked by character level. This has no "
                        "cost or downside and should never be deferred in favor of wait."
                    ),
                    "priority": "required_free_power_upgrade",
                }
            )

        if adventure is None:
            actions.append(
                {
                    "name": "start_adventure",
                    "description": (
                        "Start one offered adventure using Fable's exact calculated "
                        "risk/reward table."
                    ),
                    "parameters": {
                        "level": [
                            option["level"] for option in adventure_risk["options"]
                        ],
                        "recommended": adventure_risk["balanced_recommendation"],
                    },
                }
            )
            adventure_state = {
                "active": False,
                "risk_evaluation": adventure_risk,
            }
        else:
            number, remaining, done = adventure
            remaining_seconds = max(0, int(remaining.total_seconds()))
            resolution_risk = next(
                (
                    option
                    for option in adventure_risk["options"]
                    if int(option["level"]) == int(number)
                ),
                None,
            )
            if resolution_risk is not None:
                resolution_risk = dict(resolution_risk)
                if done:
                    luck_expected = int(
                        booster_state["active_seconds"].get("luck", 0) or 0
                    ) > 0
                    money_expected = int(
                        booster_state["active_seconds"].get("money", 0) or 0
                    ) > 0
                else:
                    luck_expected = int(
                        booster_state["active_seconds"].get("luck", 0) or 0
                    ) >= remaining_seconds + 60
                    money_expected = int(
                        booster_state["active_seconds"].get("money", 0) or 0
                    ) >= remaining_seconds + 60
                current_success = (
                    resolution_risk["success_with_luck_booster_percent"]
                    if luck_expected
                    else resolution_risk["success_without_luck_booster_percent"]
                )
                resolution_risk["success_chance_percent"] = current_success
                resolution_risk["death_chance_percent"] = round(
                    100 - current_success, 2
                )
                resolution_risk[
                    "luck_booster_expected_active_at_completion"
                ] = luck_expected
                resolution_risk[
                    "money_booster_expected_active_at_completion"
                ] = money_expected
                reward_ranges = dict(resolution_risk["success_reward_ranges"])
                reward_ranges["gold"] = (
                    reward_ranges["gold_with_money_booster"]
                    if money_expected
                    else reward_ranges["gold_without_money_booster"]
                )
                resolution_risk["success_reward_ranges"] = reward_ranges
            adventure_state = {
                "active": True,
                "level": number,
                "done": bool(done),
                "remaining_seconds": remaining_seconds,
                "resolution_risk_using_current_stats": resolution_risk,
                "odds_are_recalculated_when_claimed": True,
            }
            if done:
                actions.append(
                    {
                        "name": "claim_adventure",
                        "description": "Resolve and collect the completed adventure.",
                    }
                )

        pve_state, pve_action = await self._collect_pve_state(
            battle_cog, level=level, in_fight=in_fight
        )
        if pve_action is not None:
            actions.append(pve_action)

        if tower is None:
            actions.append(
                {
                    "name": "start_battletower",
                    "description": "Enter the Battle Tower for the first time.",
                }
            )
            tower_state = None
        else:
            tower_state = {
                "level": int(tower["level"] or 1),
                "prestige": int(tower["prestige"] or 0),
                "fight_cooldown_seconds": max(0, int(tower_cooldown)),
                "currently_in_fight": in_fight,
            }
            if int(tower["level"] or 1) >= 31:
                actions.append(
                    {
                        "name": "prestige_battletower",
                        "description": "Reset the cleared tower to floor 1 and gain one prestige.",
                    }
                )
            elif tower_cooldown <= 0 and not in_fight:
                actions.append(
                    {
                        "name": "fight_battletower",
                        "description": "Fight the current Battle Tower floor.",
                    }
                )

        actions.append({"name": "wait", "description": "Take no action this cycle."})
        class_system = {
            "primary_class_available_from_level": 1,
            "secondary_class_unlock_level": 12,
            "first_selection_for_each_slot_is_free": True,
            "class_change_cost": CLASS_CHANGE_COST,
            "class_change_cooldown_seconds": class_change_cooldown,
            "class_changes_are_optional_and_should_be_long_term_decisions": True,
            "class_strategy": class_strategy_state,
            "class_pet_fit_by_class": class_pet_fit_by_class,
            "class_change_resets_only_the_replaced_line_to_grade_1": True,
            "free_evolve_then_catches_a_new_line_up_to_character_level": True,
            "duplicate_class_lines_are_not_allowed": True,
            "evolution_unlock_levels": list(CLASS_EVOLUTION_LEVELS[1:]),
            "evolution_is_free_and_strictly_beneficial": True,
            "evolve_classes_upgrades_all_eligible_slots_together": True,
            "current_progression_status": class_progression_summary,
            "allowed_actions_is_the_exhaustive_command_whitelist": True,
            "shared_favored_weapon_rules_do_not_stack_twice": True,
            "shared_favored_weapons_still_make_pairing_equipment_efficient": True,
        }
        return {
            "event": "autoplay_tick",
            "multiple_actions_allowed": True,
            "maximum_actions": MAX_AUTOPLAY_ACTIONS,
            "actions_execute_in_order_with_fresh_state_validation": True,
            "character": {
                "name": str(profile["name"]),
                "level": level,
                "xp": int(profile["xp"]),
                "money": int(profile["money"]),
                "classes": class_names,
                "class_progression": class_progression,
                "combat_health": health_state,
                "luck": float(profile["luck"] or 1),
                "race": str(profile["race"] or "Unknown"),
                "god": (
                    str(profile["god"])
                    if profile["god"] is not None
                    else None
                ),
                "patreon_tier": int(profile["tier"] or 0),
            },
            "class_system": class_system,
            "class_knowledge": class_knowledge,
            "class_specializations": specialization_state,
            "equipment": equipment_state,
            "amulets": amulet_state,
            "raid_stats": raid_stats,
            "stat_progression": stat_progression,
            "paid_raid_upgrades": paid_raid_upgrades,
            "pve": pve_state,
            "companions": pet_state,
            "rewards": reward_state,
            "boosters": booster_state,
            "faith": faith_state,
            "race_choice": race_choice_state,
            "adventure": adventure_state,
            "battle_tower": tower_state,
            "allowed_actions": actions,
        }

    def _collect_identity_choice_state(
        self, profile
    ) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
        current_god = profile["god"]
        reset_points = int(profile["reset_points"] or 0)
        god_options = []
        for configured in getattr(self.bot.config, "gods", []) or []:
            name = str(configured.get("name") or "").strip()
            if not name:
                continue
            god_options.append(
                {
                    "god": name,
                    "description": str(configured.get("description") or ""),
                    "weekly_luck_range": {
                        "minimum": float(configured.get("boundary_low", 1)),
                        "maximum": float(configured.get("boundary_high", 1)),
                    },
                }
            )

        can_follow = current_god is None and reset_points >= 0 and bool(god_options)
        faith_state = {
            "current_god": str(current_god) if current_god is not None else None,
            "favor": int(profile["favor"] or 0),
            "reset_points": reset_points,
            "permanently_godless": current_god is None and reset_points < 0,
            "initial_selection_available": can_follow,
            "following_changes_weekly_luck_and_unlocks_god_progression": True,
            "weekly_luck_can_increase_or_decrease": True,
            "options": god_options,
        }

        current_race = str(profile["race"] or "Human")
        try:
            personal_choice = int(profile["cv"])
        except (TypeError, ValueError):
            personal_choice = -1
        can_choose_race = (
            current_race.casefold() == "human" and personal_choice == -1
        )
        race_options = [
            {"race": race, **knowledge}
            for race, knowledge in RACE_KNOWLEDGE.items()
        ]
        race_choice_state = {
            "current_race": current_race,
            "initial_selection_complete": not can_choose_race,
            "initial_selection_available": can_choose_race,
            "human_is_a_valid_choice": True,
            "choosing_human_means_staying_human": True,
            "options": race_options,
        }

        actions: list[dict[str, Any]] = []
        if can_follow:
            actions.append(
                {
                    "name": "follow_god",
                    "description": (
                        "Choose one configured god for Densetsu's currently "
                        "godless character. This is an identity and progression "
                        "choice whose weekly luck can rise or fall."
                    ),
                    "parameters": {
                        "god": [option["god"] for option in god_options]
                    },
                    "available_options": god_options,
                }
            )
        if can_choose_race:
            actions.append(
                {
                    "name": "choose_race",
                    "description": (
                        "Make the initial race choice using the exact combat "
                        "bonuses. Human is explicitly valid if Densetsu prefers "
                        "to remain Human."
                    ),
                    "parameters": {
                        "race": [option["race"] for option in race_options]
                    },
                    "available_options": race_options,
                }
            )
        return faith_state, race_choice_state, actions

    async def _context_as_densetsu(
        self,
        source_message: discord.Message,
        command_text: str,
        *,
        context_overrides: dict[str, Any] | None = None,
    ):
        command_message = copy(source_message)
        bot_user = getattr(self.bot, "user", None)
        if bot_user is not None:
            command_message.content = f"<@{bot_user.id}> {command_text}"
        else:
            command_message.content = (
                f"{self.bot.config.bot.global_prefix}{command_text}"
            )
        ctx = await self.bot.get_context(command_message)
        if not ctx.valid:
            raise ValueError(f"Unknown Fable command: {command_text}")
        for key, value in (context_overrides or {}).items():
            setattr(ctx, key, value)
        return ctx

    def _clear_global_cooldown(self, ctx) -> None:
        """Free the AI player from the human anti-spam limiter for one command."""
        for mapping_name in ("normal_cooldown", "donator_cooldown"):
            mapping = getattr(self.bot, mapping_name, None)
            if mapping is None:
                continue
            try:
                bucket = mapping.get_bucket(ctx.message)
                if bucket is not None:
                    bucket.reset()
            except Exception:
                # Never let anti-spam bookkeeping stop a validated action.
                logger.debug(
                    "Could not reset %s for the AI player", mapping_name,
                    exc_info=True,
                )

    async def _invoke_as_densetsu(
        self,
        source_message: discord.Message,
        command_text: str,
        *,
        context_overrides: dict[str, Any] | None = None,
    ) -> None:
        ctx = await self._context_as_densetsu(
            source_message,
            command_text,
            context_overrides=context_overrides,
        )
        # bot.invoke() hands CommandError to the global error handler instead of
        # raising, so a command that fails every check still looked like a
        # success and the tick reported work it never did. Run the command the
        # same way bot.invoke() does, but let the failure reach the caller.
        # The global anti-spam limiter buckets on ctx.message.created_at, but
        # every action in a batch reuses the one decision message, so all of
        # them look simultaneous and the later ones raise GlobalCooldown. The AI
        # player is already bounded by Fable's own per-command cooldowns and by
        # MAX_AUTOPLAY_ACTIONS, so clear its bucket rather than let the human
        # anti-spam rule silently drop its turn.
        self._clear_global_cooldown(ctx)

        self.bot.dispatch("command", ctx)
        try:
            if not await self.bot.can_run(ctx, call_once=True):
                raise commands.CheckFailure(
                    f"Global checks refused {command_text!r} for the AI player"
                )
            await ctx.command.invoke(ctx)
        except commands.CommandError as exc:
            logger.warning(
                "Densetsu command %r failed: %s: %s",
                command_text,
                type(exc).__name__,
                exc,
            )
            # ValueError is what the batch loop reports per action, so the
            # bridge message names the real reason instead of claiming success.
            raise ValueError(
                f"{command_text} failed: {type(exc).__name__}: {exc}"
            ) from exc
        else:
            self.bot.dispatch("command_completion", ctx)

    async def _follow_god(
        self, decision: Decision, state: dict[str, Any]
    ) -> str:
        action = self._action_definition(state, "follow_god") or {}
        offered = {
            str(value).casefold(): str(value)
            for value in (action.get("parameters") or {}).get("god", [])
        }
        requested = str(decision.parameters.get("god", "")).strip().casefold()
        god = offered.get(requested)
        if god is None:
            raise ValueError("That god was not offered to the AI player")

        configured = {
            str(value.get("name") or "").strip().casefold(): str(
                value.get("name") or ""
            ).strip()
            for value in (getattr(self.bot.config, "gods", []) or [])
            if str(value.get("name") or "").strip()
        }
        if configured.get(requested) != god:
            raise ValueError("That god is no longer configured")

        async with self.bot.pool.acquire() as connection:
            updated = await connection.fetchval(
                """
                UPDATE profile
                SET god=$1
                WHERE "user"=$2
                  AND god IS NULL
                  AND COALESCE(reset_points, 0) >= 0
                RETURNING god;
                """,
                god,
                DENSETSU_USER_ID,
            )
        if updated is None:
            raise ValueError("Densetsu is no longer eligible to follow a god")

        # Role synchronization is auxiliary; the database choice remains valid if
        # Discord role management is temporarily unavailable.
        gods_cog = self.bot.get_cog("Gods")
        try:
            support_guild = self.bot.get_guild(
                self.bot.config.game.support_server_id
            )
            member = (
                support_guild.get_member(DENSETSU_USER_ID)
                if support_guild is not None
                else None
            )
            if gods_cog is not None and member is not None:
                godless_role = support_guild.get_role(gods_cog.godless_role_id)
                stale_roles = [
                    support_guild.get_role(role_id)
                    for role_id in gods_cog.support_god_role_ids.values()
                ]
                removable = [
                    role
                    for role in [godless_role, *stale_roles]
                    if role is not None and role in member.roles
                ]
                if removable:
                    await member.remove_roles(*removable)
                role_id = gods_cog.support_god_role_ids.get(god)
                role = support_guild.get_role(role_id) if role_id else None
                if role is not None and role not in member.roles:
                    await member.add_roles(role)
        except Exception:
            logger.exception("Could not synchronize Densetsu's god role")

        return f"followed {god}"

    async def _choose_race(
        self, decision: Decision, state: dict[str, Any]
    ) -> str:
        action = self._action_definition(state, "choose_race") or {}
        offered = {
            str(value).casefold(): str(value)
            for value in (action.get("parameters") or {}).get("race", [])
        }
        requested = str(decision.parameters.get("race", "")).strip().casefold()
        race = offered.get(requested)
        if race is None or race not in RACE_KNOWLEDGE:
            raise ValueError("That race was not offered to the AI player")

        async with self.bot.pool.acquire() as connection:
            updated = await connection.fetchval(
                """
                UPDATE profile
                SET race=$1, cv=0
                WHERE "user"=$2
                  AND LOWER(COALESCE(race, 'Human'))='human'
                  AND cv=-1
                RETURNING race;
                """,
                race,
                DENSETSU_USER_ID,
            )
        if updated is None:
            raise ValueError("Densetsu's initial race choice was already completed")
        return f"selected {race} as Densetsu's race"

    def _offered_class_option(
        self, decision: Decision, state: dict[str, Any], action_name: str
    ) -> dict[str, Any]:
        try:
            slot = int(decision.parameters.get("slot", 0))
        except (TypeError, ValueError):
            raise ValueError("Class slot must be 0 or 1")
        class_key = str(decision.parameters.get("class", "")).strip().casefold()
        action = self._action_definition(state, action_name) or {}
        options = (action.get("parameters") or {}).get("options", [])
        selected = next(
            (
                option
                for option in options
                if isinstance(option, dict)
                and int(option.get("slot", -1)) == slot
                and str(option.get("class", "")).strip().casefold() == class_key
            ),
            None,
        )
        if selected is None or class_key not in ALL_KNOWN_CLASSES:
            raise ValueError("That exact class and slot combination was not offered")
        return selected

    async def _choose_class(self, decision: Decision, state: dict[str, Any]) -> str:
        selected = self._offered_class_option(decision, state, "choose_class")
        slot = int(selected["slot"])
        class_key = str(selected["class"])
        class_type = ALL_KNOWN_CLASSES[class_key]

        character = state.get("character") or {}
        level = int(character.get("level", 0))
        if slot not in (0, 1) or (slot == 1 and level < 12):
            raise ValueError("That class slot is not unlocked")

        async with self.bot.pool.acquire() as connection:
            current = await connection.fetchval(
                'SELECT "class" FROM profile WHERE "user"=$1;', DENSETSU_USER_ID
            )
            classes = list(current or ["No Class", "No Class"])
            if classes[slot] != "No Class":
                raise ValueError("The AI can only fill empty class slots automatically")
            classes[slot] = get_first_evolution(class_type).class_name()
            await connection.execute(
                'UPDATE profile SET "class"=$1 WHERE "user"=$2;',
                classes,
                DENSETSU_USER_ID,
            )
            if class_type is Ranger:
                await connection.execute(
                    'INSERT INTO pets ("user") VALUES ($1) ON CONFLICT DO NOTHING;',
                    DENSETSU_USER_ID,
                )
        await self.bot.redis.set(
            CLASS_CHANGE_COOLDOWN_KEY, "1", ex=CLASS_CHANGE_COOLDOWN_SECONDS
        )
        await self._record_class_plan(
            decision=decision,
            state=state,
            slot=slot,
            class_key=class_key,
            previous_class_name="No Class",
            selection_kind="initial_free_selection",
        )
        return f"selected {classes[slot]} in class slot {slot + 1}"

    async def _change_class(self, decision: Decision, state: dict[str, Any]) -> str:
        selected = self._offered_class_option(decision, state, "change_class")
        slot = int(selected["slot"])
        class_key = str(selected["class"])
        class_type = ALL_KNOWN_CLASSES[class_key]
        expected_current = str(selected["replaces"])
        pending = await self._redis_json_get(CLASS_CHANGE_PROPOSAL_KEY)
        confirms_pending = confirms_class_change_proposal(
            pending,
            slot=slot,
            expected_current=expected_current,
            class_key=class_key,
            event_id=decision.event_id,
        )
        if not confirms_pending:
            proposal = {
                "slot": slot,
                "expected_current": expected_current,
                "from_class_keys": sorted(
                    class_keys_for_evolution(expected_current)
                ),
                "to_class_key": class_key,
                "to_class_line": class_type.__name__,
                "reason": decision.reason or "No long-term rationale was supplied.",
                "event_id": decision.event_id,
                "proposed_at_unix": int(
                    datetime.datetime.now(datetime.timezone.utc).timestamp()
                ),
                "build_snapshot": self._class_build_snapshot(state),
                "confirmation_rule": (
                    "Select this same slot and class on a later decision to execute; "
                    "a different proposal replaces this one."
                ),
            }
            await self._redis_json_set(
                CLASS_CHANGE_PROPOSAL_KEY,
                proposal,
                expires=CLASS_CHANGE_PROPOSAL_TTL_SECONDS,
            )
            return (
                f"recorded a class-change proposal for slot {slot + 1}: "
                f"{expected_current} to {get_first_evolution(class_type).class_name()}; "
                "no class or gold changed, and the same choice must be confirmed on a "
                "later decision"
            )
        ctx = await self._context_as_densetsu(decision.message, "profile")

        async with self.bot.pool.acquire() as connection:
            async with connection.transaction():
                row = await connection.fetchrow(
                    'SELECT "class", money FROM profile WHERE "user"=$1 FOR UPDATE;',
                    DENSETSU_USER_ID,
                )
                if row is None:
                    raise ValueError("Densetsu no longer has a character")
                classes = list(row["class"] or ["No Class", "No Class"])
                if classes[slot] != expected_current:
                    raise ValueError("That class slot changed before the decision executed")
                if int(row["money"] or 0) < CLASS_CHANGE_COST:
                    raise ValueError("Densetsu can no longer afford the class change")
                other_slot = 1 - slot
                if class_key in class_keys_for_evolution(classes[other_slot]):
                    raise ValueError("The same class line cannot occupy both slots")

                old_name = classes[slot]
                classes[slot] = get_first_evolution(class_type).class_name()
                await connection.execute(
                    'UPDATE profile SET "class"=$1, money=money-$2 WHERE "user"=$3;',
                    classes,
                    CLASS_CHANGE_COST,
                    DENSETSU_USER_ID,
                )
                has_ranger = any(
                    "ranger" in class_keys_for_evolution(class_name)
                    for class_name in classes
                )
                if has_ranger:
                    await connection.execute(
                        'INSERT INTO pets ("user") VALUES ($1) ON CONFLICT DO NOTHING;',
                        DENSETSU_USER_ID,
                    )
                else:
                    await connection.execute(
                        "UPDATE pet_daycares SET is_open=FALSE WHERE owner_user_id=$1;",
                        DENSETSU_USER_ID,
                    )
                    await connection.execute(
                        'DELETE FROM pets WHERE "user"=$1;', DENSETSU_USER_ID
                    )
                await self.bot.log_transaction(
                    ctx,
                    from_=DENSETSU_USER_ID,
                    to=2,
                    subject="class change",
                    data={"Gold": CLASS_CHANGE_COST},
                    conn=connection,
                )

        await self.bot.redis.set(
            CLASS_CHANGE_COOLDOWN_KEY, "1", ex=CLASS_CHANGE_COOLDOWN_SECONDS
        )
        await self.bot.redis.delete(CLASS_CHANGE_PROPOSAL_KEY)
        await self._record_class_plan(
            decision=decision,
            state=state,
            slot=slot,
            class_key=class_key,
            previous_class_name=old_name,
            selection_kind="confirmed_paid_change",
        )
        return (
            f"changed class slot {slot + 1} from {old_name} to {classes[slot]} "
            f"for ${CLASS_CHANGE_COST:,}"
        )

    async def _choose_specialization(
        self, decision: Decision, state: dict[str, Any]
    ) -> str:
        action = self._action_definition(state, "choose_specialization") or {}
        options = (action.get("parameters") or {}).get("options", [])
        requested = str(decision.parameters.get("spec_key", "")).strip().casefold()
        selected = next(
            (
                option
                for option in options
                if isinstance(option, dict)
                and str(option.get("spec_key", "")).strip().casefold() == requested
            ),
            None,
        )
        if selected is None:
            raise ValueError("That specialization was not offered to the AI player")
        await self._invoke_as_densetsu(
            decision.message, f"spec choose {selected['name']}"
        )
        return f"selected {selected['name']} for the {selected['class_line']} line"

    async def _claim_specialization_mastery(
        self, decision: Decision, state: dict[str, Any]
    ) -> str:
        action = self._action_definition(state, "claim_specialization_mastery") or {}
        options = (action.get("parameters") or {}).get("options", [])
        requested = str(decision.parameters.get("class_line", "")).strip().casefold()
        selected = next(
            (
                option
                for option in options
                if isinstance(option, dict)
                and str(option.get("class_line", "")).strip().casefold() == requested
            ),
            None,
        )
        if selected is None:
            raise ValueError("That mastery-gift target was not offered to the AI player")
        result = await claim_free_class_mastery(
            self.bot, DENSETSU_USER_ID, str(selected["class_line"])
        )
        if result.get("status") == "already_claimed":
            raise ValueError(
                f"The mastery gift was already used on {result.get('class_line')}"
            )
        if result.get("status") == "already_mastered":
            return (
                f"{result['class_line']} was already fully mastered; "
                "the one-time gift was preserved"
            )
        return (
            f"used the one-time mastery gift on {result['class_line']} "
            f"({int(result.get('points') or 0)}/{MASTERY_UNLOCK_POINTS})"
        )

    @staticmethod
    def _action_definition(
        state: dict[str, Any], action_name: str
    ) -> dict[str, Any] | None:
        return next(
            (
                action
                for action in state.get("allowed_actions", [])
                if isinstance(action, dict) and action.get("name") == action_name
            ),
            None,
        )

    async def _optimize_equipment(self, state: dict[str, Any]) -> str:
        action = self._action_definition(state, "optimize_equipment") or {}
        raw_ids = (action.get("parameters") or {}).get("item_ids", [])
        try:
            item_ids = sorted({int(item_id) for item_id in raw_ids})
        except (TypeError, ValueError):
            raise ValueError("The recommended equipment IDs are invalid")
        if not 1 <= len(item_ids) <= 2:
            raise ValueError("A loadout must contain one or two items")

        async with self.bot.pool.acquire() as connection:
            items = await connection.fetch(
                """
                SELECT ai.id, ai.name, ai.hand
                FROM allitems ai
                JOIN inventory i ON i.item=ai.id
                WHERE ai.owner=$1 AND ai.id=ANY($2::bigint[]);
                """,
                DENSETSU_USER_ID,
                item_ids,
            )
            if len(items) != len(item_ids) or not is_valid_loadout(
                [dict(item) for item in items]
            ):
                raise ValueError("The recommended equipment is no longer available")
            async with connection.transaction():
                await connection.execute(
                    """
                    UPDATE inventory SET equipped=FALSE
                    WHERE item IN (SELECT id FROM allitems WHERE owner=$1);
                    """,
                    DENSETSU_USER_ID,
                )
                await connection.execute(
                    "UPDATE inventory SET equipped=TRUE "
                    "WHERE item=ANY($1::bigint[]);",
                    item_ids,
                )
        names = ", ".join(str(item["name"]) for item in items)
        return f"equipped optimized loadout: {names}"

    async def _equip_amulet(
        self, decision: Decision, state: dict[str, Any]
    ) -> str:
        action = self._action_definition(state, "equip_amulet") or {}
        allowed_ids = {
            int(value)
            for value in (action.get("parameters") or {}).get("amulet_id", [])
        }
        try:
            amulet_id = int(decision.parameters.get("amulet_id"))
        except (TypeError, ValueError):
            raise ValueError("A valid amulet ID is required")
        if amulet_id not in allowed_ids:
            raise ValueError("That amulet was not offered to the AI player")

        async with self.bot.pool.acquire() as connection:
            async with connection.transaction():
                amulet = await connection.fetchrow(
                    """
                    SELECT id, type, tier, equipped
                    FROM amulets
                    WHERE id=$1 AND user_id=$2
                    FOR UPDATE;
                    """,
                    amulet_id,
                    DENSETSU_USER_ID,
                )
                if amulet is None:
                    raise ValueError("Densetsu no longer owns that amulet")
                if bool(amulet["equipped"]):
                    raise ValueError("That amulet is already equipped")
                current_tier = await connection.fetchval(
                    """
                    SELECT tier FROM amulets
                    WHERE user_id=$1 AND equipped=TRUE
                    ORDER BY tier DESC
                    LIMIT 1
                    FOR UPDATE;
                    """,
                    DENSETSU_USER_ID,
                )
                if int(current_tier or 0) >= int(amulet["tier"]):
                    raise ValueError(
                        "A same-tier or stronger amulet is already equipped"
                    )
                await connection.execute(
                    "UPDATE amulets SET equipped=FALSE WHERE user_id=$1;",
                    DENSETSU_USER_ID,
                )
                await connection.execute(
                    "UPDATE amulets SET equipped=TRUE WHERE id=$1 AND user_id=$2;",
                    amulet_id,
                    DENSETSU_USER_ID,
                )
        return (
            f"equipped Tier {int(amulet['tier'])} "
            f"{str(amulet['type']).title()} amulet {amulet_id}"
        )

    async def _craft_and_equip_amulet(
        self, decision: Decision, state: dict[str, Any]
    ) -> str:
        action = self._action_definition(state, "craft_and_equip_amulet") or {}
        options = (action.get("parameters") or {}).get("options", [])
        amulet_type = str(decision.parameters.get("type", "")).strip().casefold()
        try:
            tier = int(decision.parameters.get("tier"))
        except (TypeError, ValueError):
            raise ValueError("A valid amulet tier is required")
        selected = next(
            (
                option
                for option in options
                if str(option.get("type", "")).casefold() == amulet_type
                and int(option.get("tier", 0) or 0) == tier
            ),
            None,
        )
        if selected is None:
            raise ValueError("That amulet recipe was not offered to the AI player")

        amulet_cog = self.bot.get_cog("AmuletCrafting")
        if amulet_cog is None:
            raise ValueError("Fable's amulet crafting system is unavailable")
        recipe = dict(
            amulet_cog.AMULET_RECIPES.get(amulet_type, {}).get(tier, {})
        )
        stats = amulet_cog.AMULET_TYPES.get(amulet_type, {}).get(tier)
        required_level = int(amulet_cog.TIER_LEVELS.get(tier, 999))
        if not recipe or stats is None:
            raise ValueError("That amulet recipe is no longer configured")

        async with self.bot.pool.acquire() as connection:
            xp = await connection.fetchval(
                'SELECT xp FROM profile WHERE "user"=$1;', DENSETSU_USER_ID
            )
            if xp is None or int(rpgtools.xptolevel(xp)) < required_level:
                raise ValueError("Densetsu no longer meets the amulet level requirement")
            async with connection.transaction():
                for resource, amount_needed in recipe.items():
                    current_amount = await connection.fetchval(
                        """
                        SELECT amount FROM crafting_resources
                        WHERE user_id=$1 AND resource_type=$2
                        FOR UPDATE;
                        """,
                        DENSETSU_USER_ID,
                        resource,
                    )
                    if int(current_amount or 0) < int(amount_needed):
                        raise ValueError(
                            f"Not enough {resource} remains to craft that amulet"
                        )
                highest_owned_tier = await connection.fetchval(
                    """
                    SELECT tier FROM amulets
                    WHERE user_id=$1
                    ORDER BY tier DESC
                    LIMIT 1
                    FOR UPDATE;
                    """,
                    DENSETSU_USER_ID,
                )
                if int(highest_owned_tier or 0) >= tier:
                    raise ValueError(
                        "Densetsu already owns a same-tier or stronger amulet"
                    )
                duplicate = await connection.fetchval(
                    """
                    SELECT id FROM amulets
                    WHERE user_id=$1 AND LOWER(type)=$2 AND tier=$3
                    FOR UPDATE;
                    """,
                    DENSETSU_USER_ID,
                    amulet_type,
                    tier,
                )
                if duplicate is not None:
                    raise ValueError("Densetsu already owns that exact amulet")
                for resource, amount_needed in recipe.items():
                    await connection.execute(
                        """
                        UPDATE crafting_resources
                        SET amount=amount-$1
                        WHERE user_id=$2 AND resource_type=$3;
                        """,
                        int(amount_needed),
                        DENSETSU_USER_ID,
                        resource,
                    )
                await connection.execute(
                    "UPDATE amulets SET equipped=FALSE WHERE user_id=$1;",
                    DENSETSU_USER_ID,
                )
                amulet_id = await connection.fetchval(
                    """
                    INSERT INTO amulets
                        (user_id, type, tier, hp, attack, defense, equipped)
                    VALUES ($1, $2, $3, $4, $5, $6, TRUE)
                    RETURNING id;
                    """,
                    DENSETSU_USER_ID,
                    amulet_type,
                    tier,
                    int(stats["health"]),
                    int(stats["attack"]),
                    int(stats["defense"]),
                )
                if amulet_id is None:
                    raise ValueError("Fable did not create the amulet")

        try:
            ctx = await self._context_as_densetsu(
                decision.message, f"amulet craft {amulet_type} {tier}"
            )
            self.bot.dispatch("amulet_crafted", ctx, amulet_type, tier)
        except Exception:
            logger.exception("Could not dispatch Densetsu's amulet-crafted event")
        return (
            f"crafted and equipped Tier {tier} {amulet_type.title()} amulet "
            f"{int(amulet_id)}"
        )

    async def _equip_pet(
        self, decision: Decision, state: dict[str, Any]
    ) -> str:
        action = self._action_definition(state, "equip_pet") or {}
        parameters = action.get("parameters") or {}
        allowed_ids = {int(value) for value in parameters.get("pet_id", [])}
        try:
            pet_id = int(
                decision.parameters.get("pet_id", parameters.get("recommended"))
            )
        except (TypeError, ValueError):
            raise ValueError("A valid pet ID is required")
        if pet_id not in allowed_ids:
            raise ValueError("That pet is not currently available to equip")
        await self._invoke_as_densetsu(
            decision.message, f"pets equip {pet_id}"
        )
        return f"equipped combat pet {pet_id}"

    async def _care_for_pet(
        self, decision: Decision, state: dict[str, Any]
    ) -> str:
        action = self._action_definition(state, "care_for_pet") or {}
        options = (action.get("parameters") or {}).get("options", [])
        kind = str(decision.parameters.get("kind", "")).strip().casefold()
        try:
            pet_id = int(decision.parameters.get("pet_id"))
        except (TypeError, ValueError):
            raise ValueError("A valid pet ID is required")
        selected = next(
            (
                option
                for option in options
                if option.get("kind") == kind
                and int(option.get("pet_id", 0)) == pet_id
            ),
            None,
        )
        if selected is None:
            raise ValueError("That pet-care action is not currently available")
        cooldown = await self._command_cooldown(f"pets {kind}")
        if cooldown > 0:
            raise ValueError(
                f"The pets {kind} cooldown has {cooldown} second(s) remaining"
            )
        command = (
            f"pets feed {pet_id} basic"
            if kind == "feed"
            else f"pets {kind} {pet_id}"
        )
        await self._invoke_as_densetsu(decision.message, command)
        return f"used pet-care action {kind} on pet {pet_id}"

    async def _learn_pet_skill(
        self, decision: Decision, state: dict[str, Any]
    ) -> str:
        action = self._action_definition(state, "learn_pet_skill") or {}
        options = (action.get("parameters") or {}).get("options", [])
        skill = str(decision.parameters.get("skill", "")).strip()
        try:
            pet_id = int(decision.parameters.get("pet_id"))
        except (TypeError, ValueError):
            raise ValueError("A valid pet ID is required")
        selected = next(
            (
                option
                for option in options
                if int(option.get("pet_id", 0)) == pet_id
                and str(option.get("skill", "")).casefold() == skill.casefold()
            ),
            None,
        )
        if selected is None:
            raise ValueError("That pet skill is not currently learnable")
        canonical_skill = str(selected["skill"])
        await self._invoke_as_densetsu(
            decision.message,
            f"pets learn {pet_id} {canonical_skill}",
        )
        return f"taught pet {pet_id} the skill {canonical_skill}"

    async def _start_pve(
        self, decision: Decision, state: dict[str, Any]
    ) -> str:
        action = self._action_definition(state, "start_pve") or {}
        parameters = action.get("parameters") or {}
        allowed_locations = {
            str(value).casefold() for value in parameters.get("location", [])
        }
        location = str(decision.parameters.get("location", "")).casefold()
        if location not in allowed_locations:
            raise ValueError("That PvE location is not currently unlocked")
        allowed_pools = {
            str(value).casefold() for value in parameters.get("pool", [])
        }
        pool = str(decision.parameters.get("pool", "default")).casefold()
        if pool not in allowed_pools:
            pool = "default"
        command = "pve" if pool == "default" else f"pve {pool}"
        await self._invoke_as_densetsu(
            decision.message,
            command,
            context_overrides={
                "locationchoice_override": location,
                "authorized_ai_player": True,
            },
        )
        return f"completed a PvE attempt at {location} using the {pool} pool"

    async def _open_crates(
        self, decision: Decision, state: dict[str, Any]
    ) -> str:
        action = self._action_definition(state, "open_crates") or {}
        action_parameters = action.get("parameters") or {}
        options = action.get("available_options") or action_parameters.get(
            "options", []
        )
        rarity = str(decision.parameters.get("rarity", "")).strip().casefold()
        if not rarity:
            echoed_options = decision.parameters.get("options")
            if isinstance(echoed_options, list) and len(echoed_options) == 1:
                echoed_option = echoed_options[0]
                if isinstance(echoed_option, dict):
                    rarity = str(echoed_option.get("rarity", "")).strip().casefold()
        selected = next(
            (option for option in options if option.get("rarity") == rarity),
            None,
        )
        if selected is None:
            raise ValueError("That crate rarity is not currently available to open")
        maximum = int(selected.get("maximum_per_action") or 0)
        try:
            amount = int(decision.parameters.get("amount", maximum))
        except (TypeError, ValueError):
            raise ValueError("The crate amount must be a whole number")
        if not 1 <= amount <= maximum:
            raise ValueError(
                f"The AI may currently open between 1 and {maximum} {rarity} crates"
            )
        await self._invoke_as_densetsu(
            decision.message, f"open {rarity} {amount}"
        )
        return f"opened {amount} {rarity} crate{'s' if amount != 1 else ''}"

    async def _claim_vote_crates(
        self, decision: Decision, state: dict[str, Any]
    ) -> str:
        if self._action_definition(state, "claim_vote_crates") is None:
            raise ValueError("The vote-crate reward is not currently available")
        if await self._command_cooldown("cratesdaily") > 0:
            raise ValueError("The vote-crate reward is now on cooldown")
        await self._invoke_as_densetsu(decision.message, "cratesdaily")
        return "claimed the available vote crates"

    async def _claim_daily(
        self, decision: Decision, state: dict[str, Any]
    ) -> str:
        action = self._action_definition(state, "claim_daily") or {}
        parameters = action.get("parameters") or {}
        options = parameters.get("options", [])
        try:
            choice = int(decision.parameters.get("choice", 0))
            next_streak = int(parameters["next_streak"])
        except (KeyError, TypeError, ValueError):
            raise ValueError("The daily reward choice is invalid")
        selected = next(
            (option for option in options if int(option.get("choice", -1)) == choice),
            None,
        )
        if selected is None or not isinstance(selected.get("reward"), dict):
            raise ValueError("That daily reward was not offered")
        if await self._command_cooldown("daily") > 0:
            raise ValueError("The daily reward is now on cooldown")
        daily_cog = self.bot.get_cog("Miscellaneous")
        if daily_cog is None:
            raise ValueError("Fable's daily reward system is unavailable")
        ctx = await self._context_as_densetsu(decision.message, "daily")
        reward = dict(selected["reward"])
        try:
            await daily_cog._claim_daily_reward(ctx, next_streak, reward)
        except DailyRewardAlreadyClaimed as error:
            raise ValueError("Today's daily reward was already claimed") from error
        await ctx.send(
            embed=daily_cog._build_daily_result_embed(ctx, next_streak, reward)
        )
        return (
            f"claimed daily streak day {next_streak}: "
            f"{self._daily_reward_summary(reward)}"
        )

    async def _activate_booster(
        self, decision: Decision, state: dict[str, Any]
    ) -> str:
        action = self._action_definition(state, "activate_booster") or {}
        allowed = {
            str(value).casefold()
            for value in (action.get("parameters") or {}).get("type", [])
        }
        kind = str(decision.parameters.get("type", "")).strip().casefold()
        if kind not in allowed:
            raise ValueError("That booster is not currently available to activate")
        if await self.bot.get_booster(DENSETSU_USER_ID, kind):
            raise ValueError("That booster became active before this decision completed")
        store_cog = self.bot.get_cog("Store")
        if store_cog is None:
            raise ValueError("Fable's booster system is unavailable")
        ctx = await self._context_as_densetsu(decision.message, "boosters")
        ok, message = await store_cog.activate_booster_selection(ctx, kind)
        if not ok:
            raise ValueError(message)
        return message

    async def _allocate_stat_points(
        self, decision: Decision, state: dict[str, Any]
    ) -> str:
        action = self._action_definition(state, "allocate_stat_points") or {}
        parameters = action.get("parameters") or {}
        stat = str(decision.parameters.get("stat", "")).strip().casefold()
        allowed_stats = {
            str(value).casefold() for value in parameters.get("stat", [])
        }
        try:
            amount = int(decision.parameters.get("amount", 0))
            maximum = int((parameters.get("amount") or {})["maximum"])
        except (KeyError, TypeError, ValueError):
            raise ValueError("A valid stat-point amount is required")
        if stat not in allowed_stats or not 1 <= amount <= maximum:
            raise ValueError("That stat allocation was not offered")
        profile_cog = self.bot.get_cog("Profile")
        if profile_cog is None or not hasattr(profile_cog, "_allocate_stat_points"):
            raise ValueError("Fable's stat allocation system is unavailable")
        ok, message, _snapshot = await profile_cog._allocate_stat_points(
            DENSETSU_USER_ID,
            stat,
            amount,
        )
        if not ok:
            raise ValueError(message)
        return message

    async def _purchase_raid_upgrade(
        self, decision: Decision, state: dict[str, Any]
    ) -> str:
        action = self._action_definition(state, "purchase_raid_upgrade") or {}
        options = action.get("available_options") or []
        upgrade = str(decision.parameters.get("upgrade", "")).strip().casefold()
        selected = next(
            (option for option in options if option.get("upgrade") == upgrade),
            None,
        )
        if selected is None:
            raise ValueError("That paid raid-stat upgrade was not offered")
        if await self._command_cooldown("increase") > 0:
            raise ValueError("Paid raid-stat upgrades are now on cooldown")
        raid_cog = self.bot.get_cog("Raid")
        if raid_cog is None or not hasattr(raid_cog, "purchase_raid_upgrade_for_ai"):
            raise ValueError("Fable's paid raid-stat upgrade system is unavailable")
        ctx = await self._context_as_densetsu(decision.message, "raidstats")
        ok, message, _result = await raid_cog.purchase_raid_upgrade_for_ai(
            ctx,
            upgrade,
            minimum_remaining=PAID_RAID_UPGRADE_MONEY_RESERVE,
            expected_price=int(selected["price"]),
        )
        if not ok:
            raise ValueError(message)
        return message

    async def _execute_decision(
        self, decision: Decision, state: dict[str, Any]
    ) -> str:
        if decision.action not in action_names(state):
            raise ValueError("Decision is no longer allowed")

        if decision.action == "wait":
            return "waited"
        if decision.action == "create_character":
            name = str(decision.parameters.get("name", DEFAULT_CHARACTER_NAME)).strip()
            if not 3 <= len(name) <= 20 or "`" in name:
                name = DEFAULT_CHARACTER_NAME
            await self._invoke_as_densetsu(decision.message, f"create {name}")
            return f"requested character creation as {name}"
        if decision.action == "claim_adventure":
            await self._invoke_as_densetsu(decision.message, "status")
            return "resolved the completed adventure"
        if decision.action == "start_adventure":
            action = self._action_definition(state, "start_adventure") or {}
            parameters = action.get("parameters") or {}
            offered_levels = {
                int(value) for value in parameters.get("level", [])
            }
            try:
                level = int(
                    decision.parameters.get("level", parameters.get("recommended"))
                )
            except (TypeError, ValueError):
                raise ValueError("A valid adventure level is required")
            if level not in offered_levels:
                raise ValueError("That adventure level was not offered")
            await self._invoke_as_densetsu(decision.message, f"adventure {level}")
            return f"started adventure {level}"
        if decision.action == "follow_god":
            return await self._follow_god(decision, state)
        if decision.action == "choose_race":
            return await self._choose_race(decision, state)
        if decision.action == "choose_class":
            return await self._choose_class(decision, state)
        if decision.action == "change_class":
            return await self._change_class(decision, state)
        if decision.action == "evolve_classes":
            await self._invoke_as_densetsu(decision.message, "evolve")
            return "evolved every eligible class"
        if decision.action == "choose_specialization":
            return await self._choose_specialization(decision, state)
        if decision.action == "claim_specialization_mastery":
            return await self._claim_specialization_mastery(decision, state)
        if decision.action == "optimize_equipment":
            return await self._optimize_equipment(state)
        if decision.action == "equip_amulet":
            return await self._equip_amulet(decision, state)
        if decision.action == "craft_and_equip_amulet":
            return await self._craft_and_equip_amulet(decision, state)
        if decision.action == "equip_pet":
            return await self._equip_pet(decision, state)
        if decision.action == "care_for_pet":
            return await self._care_for_pet(decision, state)
        if decision.action == "learn_pet_skill":
            return await self._learn_pet_skill(decision, state)
        if decision.action == "start_pve":
            return await self._start_pve(decision, state)
        if decision.action == "open_crates":
            return await self._open_crates(decision, state)
        if decision.action == "claim_vote_crates":
            return await self._claim_vote_crates(decision, state)
        if decision.action == "claim_daily":
            return await self._claim_daily(decision, state)
        if decision.action == "claim_daily_booster":
            if await self._command_cooldown("boosterdaily") > 0:
                raise ValueError("The daily booster reward is now on cooldown")
            await self._invoke_as_densetsu(decision.message, "boosterdaily")
            return "claimed the available daily booster"
        if decision.action == "activate_booster":
            return await self._activate_booster(decision, state)
        if decision.action == "allocate_stat_points":
            return await self._allocate_stat_points(decision, state)
        if decision.action == "purchase_raid_upgrade":
            return await self._purchase_raid_upgrade(decision, state)
        if decision.action == "start_battletower":
            async with self.bot.pool.acquire() as connection:
                await connection.execute(
                    "INSERT INTO battletower (id) VALUES ($1) ON CONFLICT DO NOTHING;",
                    DENSETSU_USER_ID,
                )
            return "entered the Battle Tower"
        if decision.action == "prestige_battletower":
            async with self.bot.pool.acquire() as connection:
                prestige = await connection.fetchval(
                    "UPDATE battletower SET level=1, prestige=prestige+1, "
                    "run_key_bits=0 WHERE id=$1 AND level>=31 RETURNING prestige;",
                    DENSETSU_USER_ID,
                )
            if prestige is None:
                raise ValueError("Battle Tower prestige is not currently available")
            ctx = await self._context_as_densetsu(
                decision.message, "battletower progress"
            )
            self.bot.dispatch("battletower_prestige", ctx, prestige)
            return f"prestiged the Battle Tower to prestige {prestige}"
        if decision.action == "fight_battletower":
            await self._invoke_as_densetsu(decision.message, "battletower fight")
            return "attempted the current Battle Tower floor"
        raise ValueError(f"Unsupported AI action: {decision.action}")

    async def run_autoplay_once(self) -> str:
        if not await self._is_enabled():
            return "disabled"
        channel = await self._bridge_channel()
        if channel is None:
            return "unbound"

        async with self._local_tick_lock:
            lock_value = uuid.uuid4().hex
            acquired = await self.bot.redis.set(
                TICK_LOCK_KEY,
                lock_value,
                ex=AUTOPLAY_TICK_LOCK_SECONDS,
                nx=True,
            )
            if not acquired:
                return "already running"
            try:
                state = await self._collect_state()
                decision = await self.request_decision(
                    state, timeout=AUTOPLAY_DECISION_TIMEOUT_SECONDS
                )
                if decision is None:
                    return "no decision"
                if not await self._is_enabled():
                    return "disabled"
                planned_actions = decision.ordered_actions()
                current_state = state
                results = []
                for index, planned in enumerate(planned_actions):
                    if not await self._is_enabled():
                        results.append("batch stopped because autoplay was disabled")
                        break
                    action_decision = decision.for_action(planned)
                    if planned.action not in action_names(current_state):
                        results.append(
                            f"{planned.action}: skipped because it is no longer available"
                        )
                    else:
                        try:
                            result = await self._execute_decision(
                                action_decision, current_state
                            )
                        except ValueError as exc:
                            logger.warning(
                                "Densetsu batch action %s failed safely: %s",
                                planned.action,
                                exc,
                            )
                            results.append(
                                f"{planned.action}: skipped ({str(exc)[:180]})"
                            )
                        else:
                            results.append(f"{planned.action}: {result}")
                    if index + 1 < len(planned_actions):
                        current_state = await self._collect_state()

                if len(results) == 1:
                    message = f"AI action complete: **{results[0]}**."
                else:
                    lines = [f"- {result[:240]}" for result in results]
                    message = "AI action batch complete:\n" + "\n".join(lines)
                await channel.send(
                    message[:1950],
                    allowed_mentions=discord.AllowedMentions.none(),
                )
                return "; ".join(results)[:1000]
            except Exception as exc:
                logger.exception("Densetsu autoplay tick failed")
                await channel.send(
                    f"AI action failed safely: `{str(exc)[:500]}`",
                    allowed_mentions=discord.AllowedMentions.none(),
                )
                return "failed"
            finally:
                current = await self.bot.redis.get(TICK_LOCK_KEY)
                if isinstance(current, bytes):
                    current = current.decode("ascii", errors="ignore")
                if current == lock_value:
                    await self.bot.redis.delete(TICK_LOCK_KEY)

    @tasks.loop(seconds=60)
    async def autoplay_loop(self) -> None:
        try:
            await self.run_autoplay_once()
        except Exception as exc:
            await self._report_error("autoplay tick", exc)

    @autoplay_loop.before_loop
    async def before_autoplay_loop(self) -> None:
        await self.bot.wait_until_ready()

    @commands.group(name="aiplayer", invoke_without_command=True, hidden=True)
    @is_gm()
    async def aiplayer(self, ctx) -> None:
        channel = await self._bridge_channel()
        enabled = await self._is_enabled()
        max_wager_percent = await self._max_wager_percent()
        await ctx.send(
            "Densetsu AI player: "
            f"**{'enabled' if enabled else 'disabled'}**; bridge: "
            f"{channel.mention if channel else 'not bound'}; maximum raid wager: "
            f"**{max_wager_percent}%** of its current money."
        )

    @aiplayer.command(name="bind", hidden=True)
    @is_gm()
    async def aiplayer_bind(self, ctx) -> None:
        await self.bot.redis.set(BRIDGE_CHANNEL_KEY, ctx.channel.id)
        await ctx.send(
            f"Densetsu's private AI bridge is now bound to {ctx.channel.mention}."
        )

    @aiplayer.command(name="enable", hidden=True)
    @is_gm()
    async def aiplayer_enable(self, ctx) -> None:
        if await self._bridge_channel() is None:
            return await ctx.send("Run `$aiplayer bind` in the bridge channel first.")
        await self.bot.redis.set(ENABLED_KEY, "1")
        await ctx.send("Densetsu autoplay enabled. Use `$aiplayer tick` to run it now.")

    @aiplayer.command(name="disable", hidden=True)
    @is_gm()
    async def aiplayer_disable(self, ctx) -> None:
        await self.bot.redis.set(ENABLED_KEY, "0")
        await ctx.send("Densetsu autoplay disabled. Pending game actions will fail safely.")

    @aiplayer.command(name="tick", hidden=True)
    @is_gm()
    async def aiplayer_tick(self, ctx) -> None:
        await ctx.send("Running one Densetsu decision cycle...")
        result = await self.run_autoplay_once()
        await ctx.send(f"Densetsu decision cycle finished: **{result}**.")

    @aiplayer.command(name="maxwager", hidden=True)
    @is_gm()
    async def aiplayer_maxwager(self, ctx, percent: int) -> None:
        if percent < 0 or percent > 100:
            return await ctx.send("Choose a percentage from 0 through 100.")
        await self.bot.redis.set(MAX_WAGER_PERCENT_KEY, percent)
        await ctx.send(
            "Densetsu's maximum raid wager is now "
            f"**{percent}%** of its current money."
        )

    def _raidbattle_offer_finished(self, task: asyncio.Task) -> None:
        if task.cancelled():
            return
        try:
            task.result()
        except Exception as exc:
            self._queue_error_report("raidbattle offer", exc)

    def start_raidbattle_offer(self, **kwargs) -> asyncio.Task:
        task = asyncio.create_task(self.offer_raidbattle(**kwargs))
        task.add_done_callback(self._raidbattle_offer_finished)
        return task

    def _raidbattle_speech_finished(self, task: asyncio.Task) -> None:
        if task.cancelled():
            return
        try:
            task.result()
        except Exception as exc:
            self._queue_error_report("raidbattle dialogue relay", exc)

    def _relay_raidbattle_dialogue(self, channel_id: int, text: str) -> None:
        speech_task = asyncio.create_task(self.speak(channel_id, text))
        speech_task.add_done_callback(self._raidbattle_speech_finished)

    async def offer_raidbattle(
        self,
        *,
        future: asyncio.Future,
        view,
        challenger: discord.Member,
        requested_enemy: discord.Member | None,
        wager: int,
        public_channel,
    ) -> None:
        if not await self._is_enabled() or future.done():
            return
        if challenger.id == DENSETSU_USER_ID:
            return
        if requested_enemy is not None and requested_enemy.id != DENSETSU_USER_ID:
            return
        guild = getattr(public_channel, "guild", None)
        if guild is None:
            return
        densetsu = guild.get_member(DENSETSU_USER_ID)
        if densetsu is None:
            try:
                densetsu = await guild.fetch_member(DENSETSU_USER_ID)
            except (discord.Forbidden, discord.NotFound, discord.HTTPException):
                return

        async with self.bot.pool.acquire() as connection:
            ai_profile = await connection.fetchrow(
                'SELECT name, xp, money, "class" FROM profile WHERE "user"=$1;',
                DENSETSU_USER_ID,
            )
            opponent_profile = await connection.fetchrow(
                'SELECT name, xp, money, "class" FROM profile WHERE "user"=$1;',
                challenger.id,
            )
        if ai_profile is None or opponent_profile is None or int(ai_profile["money"]) < wager:
            return

        maximum_wager = await self._maximum_raid_wager(int(ai_profile["money"]))
        can_accept_wager = wager <= maximum_wager

        ai_raid_stats, opponent_raid_stats = await asyncio.gather(
            self._collect_raid_stats(DENSETSU_USER_ID, densetsu),
            self._collect_raid_stats(challenger.id, challenger),
        )
        raid_comparison = self._raid_stat_comparison(
            ai_raid_stats, opponent_raid_stats
        )
        matchup_risk = evaluate_raid_matchup(
            ai_raid_stats,
            opponent_raid_stats,
            wager=wager,
            bankroll=int(ai_profile["money"]),
        )
        can_accept_matchup = bool(matchup_risk.get("acceptance_allowed"))
        can_accept = can_accept_wager and can_accept_matchup

        event = {
            "event": "raidbattle_offer",
            "character": {
                "name": str(ai_profile["name"]),
                "level": int(rpgtools.xptolevel(ai_profile["xp"])),
                "money": int(ai_profile["money"]),
                "classes": list(ai_profile["class"] or []),
                "raid_stats": ai_raid_stats,
            },
            "opponent": {
                "discord_id": challenger.id,
                "name": str(opponent_profile["name"]),
                "level": int(rpgtools.xptolevel(opponent_profile["xp"])),
                "raid_stats": opponent_raid_stats,
            },
            "raid_stat_comparison": raid_comparison,
            "matchup_risk": matchup_risk,
            "wager": int(wager),
            "maximum_allowed_wager": maximum_wager,
            "combat_is_automatic": True,
            "allowed_actions": (
                [
                    {
                        "name": "accept",
                        "description": (
                            "Join and pay the wager. Fable's conservative simulated "
                            "win chance meets the required safety threshold."
                        ),
                    },
                    {"name": "decline", "description": "Do not join."},
                ]
                if can_accept
                else [
                    {
                        "name": "decline",
                        "description": (
                            "Acceptance is blocked because the wager exceeds the "
                            "configured limit, complete combat stats are unavailable, "
                            "or the conservative simulated win chance is below the "
                            "bankroll-adjusted safety threshold."
                        ),
                    }
                ]
            ),
        }
        decision = await self.request_decision(event, timeout=45)
        if decision is None or future.done():
            return
        if not await self._is_enabled():
            return
        if decision.action == "decline":
            self._relay_raidbattle_dialogue(
                public_channel.id,
                decision.dialogue or "Not this time.",
            )
            if requested_enemy is not None and not future.done():
                future.set_exception(asyncio.TimeoutError())
                view.stop()
            return
        if decision.action != "accept":
            return
        if view.allowed is not None and view.allowed.id != densetsu.id:
            return
        if view.prohibited is not None and view.prohibited.id == densetsu.id:
            return
        if view.check is not None and not await view.check(densetsu):
            return
        current_money = await self.bot.pool.fetchval(
            'SELECT money FROM profile WHERE "user"=$1;', DENSETSU_USER_ID
        )
        if current_money is None or wager > await self._maximum_raid_wager(current_money):
            return
        fresh_ai_stats, fresh_opponent_stats = await asyncio.gather(
            self._collect_raid_stats(DENSETSU_USER_ID, densetsu),
            self._collect_raid_stats(challenger.id, challenger),
        )
        fresh_matchup_risk = evaluate_raid_matchup(
            fresh_ai_stats,
            fresh_opponent_stats,
            wager=wager,
            bankroll=int(current_money),
        )
        if not fresh_matchup_risk.get("acceptance_allowed"):
            self._relay_raidbattle_dialogue(
                public_channel.id,
                "The matchup changed, and those odds are no longer worth the wager.",
            )
            if requested_enemy is not None and not future.done():
                future.set_exception(asyncio.TimeoutError())
                view.stop()
            return
        if future.done():
            return
        future.set_result(densetsu)
        view.stop()
        self._relay_raidbattle_dialogue(
            public_channel.id,
            decision.dialogue or "I'll take that raidbattle.",
        )


async def setup(bot) -> None:
    await bot.add_cog(AIPlayer(bot))

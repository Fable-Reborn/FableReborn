"""Autonomous Densetsu player bridged through a private Discord channel."""

from __future__ import annotations

import asyncio
import datetime
import io
import json
import logging
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
    Raider,
    Ranger,
    Ritualist,
    Tank,
    Thief,
    Warrior,
    from_string as class_from_string,
    get_class_evolves,
    get_first_evolution,
)
from classes.endgame import apply_item_progression_bonus, soulbound_level_from_xp
from cogs.aiplayer.strategy import (
    CLASS_KNOWLEDGE,
    choose_best_equipment,
    choose_best_pet,
    combat_health_state,
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
BASIC_PET_FOOD_COST = 10_000
PET_CARE_MONEY_RESERVE = 50_000
PAID_RAID_UPGRADE_MONEY_RESERVE = 50_000
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


@dataclass(slots=True)
class Decision:
    event_id: str
    action: str
    parameters: dict[str, Any]
    reason: str
    dialogue: str
    message: discord.Message


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
    action = str(payload.get("action", "")).strip().casefold()
    if not event_id or not action:
        return None
    parameters = payload.get("parameters", {})
    if not isinstance(parameters, dict):
        parameters = {}
    return Decision(
        event_id=event_id,
        action=action,
        parameters=parameters,
        reason=str(payload.get("reason", "")).strip()[:500],
        dialogue=str(payload.get("dialogue", "")).strip()[:500],
        message=message,
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

    async def _is_enabled(self) -> bool:
        value = await self.bot.redis.get(ENABLED_KEY)
        if isinstance(value, bytes):
            value = value.decode("ascii", errors="ignore")
        return str(value) == "1"

    async def is_active_for(self, user_id: int) -> bool:
        """Return whether this cog is currently controlling the requested player."""
        return int(user_id) == DENSETSU_USER_ID and await self._is_enabled()

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
            raid_allows_pets = bool(
                await factory.settings.get_setting_async("raid", "allow_pets")
            )
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
        self, connection, class_names: list[str]
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

        state = {
            "pets": sorted(
                pets, key=lambda pet: pet["combat_score"], reverse=True
            )[:12],
            "recommended_combat_pet_id": best_pet_id,
            "eggs": eggs[:12],
            "egg_hatching_is_automatic": True,
            "collection_used": len(pets) + len(eggs),
            "collection_capacity": max_collection,
            "routine_feed_money_reserve": PET_CARE_MONEY_RESERVE,
            "fullness_scale": "100 is fully fed; 0 is starving",
            "adult_pets_are_self_sufficient": True,
            "adult_fullness_and_happiness_do_not_decay": True,
            "emergency_fullness_threshold_for_growing_pets": PET_EMERGENCY_HUNGER,
            "care_target_pet_id": target["id"] if target is not None else None,
            "care_actions": care_action_status,
        }
        return state, actions

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
        if message.author.id != DENSETSU_USER_ID:
            return
        bridge = await self._bridge_channel()
        if bridge is None or message.channel.id != bridge.id:
            return
        payload = parse_marked_json(message.content, DECISION_MARKER)
        if payload is None:
            return
        decision = decision_from_payload(payload, message)
        if decision is None:
            return
        future = self._pending.get(decision.event_id)
        if future is not None and not future.done():
            future.set_result(decision)

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

        if decision.action not in action_names(event):
            logger.warning(
                "Densetsu returned disallowed action %s for event %s",
                decision.action,
                event_id,
            )
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

    async def speak(self, channel_id: int, text: str) -> None:
        bridge = await self._bridge_channel()
        text = text.strip()[:1900]
        if bridge is None or not text:
            return
        payload = json.dumps(
            {"channel_id": int(channel_id), "text": text},
            ensure_ascii=False,
            separators=(",", ":"),
        )
        await bridge.send(
            f"{SPEAK_MARKER} {payload}",
            allowed_mentions=discord.AllowedMentions.none(),
        )

    @staticmethod
    def _background_task_finished(task: asyncio.Task) -> None:
        if task.cancelled():
            return
        try:
            task.result()
        except Exception:
            logger.exception("Densetsu background interaction failed")

    def _start_background(self, coroutine) -> asyncio.Task:
        task = asyncio.create_task(coroutine)
        task.add_done_callback(self._background_task_finished)
        return task

    def _relay_dialogue(self, channel_id: int, text: str) -> None:
        self._start_background(self.speak(channel_id, text))

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

    async def _collect_state(self) -> dict[str, Any]:
        async with self.bot.pool.acquire() as connection:
            profile = await connection.fetchrow(
                'SELECT name, xp, money, "class", health, stathp, statatk, '
                'statdef, statpoints, atkmultiply, defmultiply, hplevel, '
                'luck, race, cv, god, favor, reset_points, guild, '
                'tier, crates_common, crates_uncommon, crates_rare, '
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
        async with self.bot.pool.acquire() as connection:
            health_state = await self._collect_health_state(
                connection, profile, level=level
            )
            equipment_state = await self._collect_equipment_state(
                connection, class_names
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
        battle_cog = self.bot.get_cog("Battles")
        raid_stats = await self._collect_raid_stats(DENSETSU_USER_ID)
        paid_raid_upgrades, paid_raid_action = (
            await self._collect_paid_raid_upgrade_state(profile, raid_stats)
        )
        in_fight = False
        if battle_cog is not None and hasattr(battle_cog, "is_player_in_fight"):
            try:
                in_fight = await battle_cog.is_player_in_fight(DENSETSU_USER_ID)
            except Exception:
                logger.exception("Could not read Densetsu's active-fight state")

        actions: list[dict[str, Any]] = [
            {"name": "wait", "description": "Take no action this cycle."}
        ]
        actions.extend(reward_actions)
        actions.extend(booster_actions)
        actions.extend(amulet_actions)
        actions.extend(pet_actions)
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
        if empty_slots:
            actions.append(
                {
                    "name": "choose_class",
                    "description": "Fill one currently empty class slot.",
                    "parameters": {
                        "slot": empty_slots,
                        "class": sorted(PLAYABLE_CLASSES),
                    },
                }
            )
        evolution_ready = False
        class_progression = []
        if level >= 5:
            evolution_index = min(6, int(min(level, 30) / 5))
            for class_name in class_names:
                game_class = class_from_string(class_name)
                if game_class is None:
                    continue
                evolutions = get_class_evolves(game_class.get_class_line())
                target_index = min(evolution_index, len(evolutions) - 1)
                target_name = evolutions[target_index].class_name()
                current_name = game_class.class_name()
                current_index = next(
                    (
                        index
                        for index, evolution in enumerate(evolutions)
                        if evolution.class_name() == current_name
                    ),
                    target_index,
                )
                next_level = (
                    (current_index + 1) * 5
                    if current_index + 1 < len(evolutions)
                    else None
                )
                class_progression.append(
                    {
                        "current": current_name,
                        "class_line": game_class.get_class_line_name(),
                        "highest_unlocked": target_name,
                        "next_evolution_level": next_level,
                    }
                )
                if current_name != target_name:
                    evolution_ready = True
        if evolution_ready:
            actions.append(
                {
                    "name": "evolve_classes",
                    "description": "Apply every class evolution unlocked by the current level.",
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

        return {
            "event": "autoplay_tick",
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
            "class_knowledge": CLASS_KNOWLEDGE,
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
        await self.bot.invoke(ctx)

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

    async def _choose_class(self, decision: Decision, state: dict[str, Any]) -> str:
        try:
            slot = int(decision.parameters.get("slot", 0))
        except (TypeError, ValueError):
            raise ValueError("Class slot must be 0 or 1")
        class_key = str(decision.parameters.get("class", "")).strip().casefold()
        class_type = PLAYABLE_CLASSES.get(class_key)
        if class_type is None:
            raise ValueError("The selected class is not available to the AI player")

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
        return f"selected {classes[slot]} in class slot {slot + 1}"

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
        if decision.action == "evolve_classes":
            await self._invoke_as_densetsu(decision.message, "evolve")
            return "evolved every eligible class"
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
                TICK_LOCK_KEY, lock_value, ex=240, nx=True
            )
            if not acquired:
                return "already running"
            try:
                state = await self._collect_state()
                decision = await self.request_decision(state)
                if decision is None:
                    return "no decision"
                if not await self._is_enabled():
                    return "disabled"
                result = await self._execute_decision(decision, state)
                await channel.send(
                    f"AI action complete: **{result}**.",
                    allowed_mentions=discord.AllowedMentions.none(),
                )
                return result
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
        await self.run_autoplay_once()

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

    @staticmethod
    def _raidbattle_offer_finished(task: asyncio.Task) -> None:
        if task.cancelled():
            return
        try:
            task.result()
        except Exception:
            logger.exception("Densetsu raidbattle offer handler failed")

    def start_raidbattle_offer(self, **kwargs) -> asyncio.Task:
        task = asyncio.create_task(self.offer_raidbattle(**kwargs))
        task.add_done_callback(self._raidbattle_offer_finished)
        return task

    @staticmethod
    def _raidbattle_speech_finished(task: asyncio.Task) -> None:
        if task.cancelled():
            return
        try:
            task.result()
        except Exception:
            logger.exception("Densetsu raidbattle dialogue relay failed")

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
            "wager": int(wager),
            "maximum_allowed_wager": maximum_wager,
            "combat_is_automatic": True,
            "allowed_actions": (
                [
                    {"name": "accept", "description": "Join and pay the wager."},
                    {"name": "decline", "description": "Do not join."},
                ]
                if can_accept_wager
                else [
                    {
                        "name": "decline",
                        "description": "The wager exceeds the configured safety limit.",
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

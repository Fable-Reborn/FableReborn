# battles/core/battle.py
from abc import ABC, abstractmethod
import asyncio
import datetime
import uuid
from collections import deque
from dataclasses import dataclass, field
from decimal import Decimal
import logging
import random
from typing import List, Dict, Optional, Union, Any
import json

class DecimalEncoder(json.JSONEncoder):
    """Custom JSON encoder that handles Decimal objects"""
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        return super().default(obj)


@dataclass
class PetAttackOutcome:
    final_damage: Decimal
    blocked_damage: Decimal
    skill_messages: List[str] = field(default_factory=list)
    defender_messages: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

import discord
from discord.ext import commands

from classes.ascension import get_ascension_mantle

# Import the status effect registry
from .status_effect import StatusEffectRegistry

logger = logging.getLogger(__name__)

class Battle(ABC):
    """Base class for all battle types"""
    HP_BAR_STYLE_NORMAL = "normal"
    HP_BAR_STYLE_COLORFUL = "colorful"
    HP_BAR_STYLE_TEAM = "team"
    HP_BAR_EMPTY_LEFT = "<:EmptyLeftEdge:1486325193713516666>"
    HP_BAR_EMPTY_MIDDLE = "<:EmptyMiddle:1486325196351864862>"
    HP_BAR_EMPTY_RIGHT = "<:TopEmpty:1486325200441311242>"
    HP_BAR_FULL_LEFT = "<:FullLeftEdge:1486325181512286371>"
    HP_BAR_FULL_MIDDLE = "<:MiddleFullRed:1486325202186141889>"
    HP_BAR_FULL_RIGHT = "<:FullTop:1486325203939102840>"
    HP_BAR_HALF_LEFT = "<:leftedgehalf:1486331826636197979>"
    HP_BAR_HALF_MIDDLE = "<:Halfwayred:1486325198620852335>"
    HP_BAR_HALF_RIGHT = "<:halfhopedge:1486331829047787631>"
    HP_BAR_BLUE_FULL_LEFT = "<:blueleftfull:1486332749831864330>"
    HP_BAR_BLUE_FULL_MIDDLE = "<:middlefullblue:1486332751698333808>"
    HP_BAR_BLUE_FULL_RIGHT = "<:bluetopfull:1486333706569388073>"
    HP_BAR_BLUE_HALF_LEFT = "<:bluehalfleftedge:1486332747722133666>"
    HP_BAR_BLUE_HALF_MIDDLE = "<:middlehalf:1486333395339575487>"
    HP_BAR_BLUE_HALF_RIGHT = "<:bluetophalffull:1486332753841750036>"
    DISCORD_RETRY_ATTEMPTS = 3
    DISCORD_RETRY_BASE_DELAY = 1.0

    @classmethod
    def normalize_hp_bar_style(cls, style):
        normalized = str(style or "").strip().lower()
        aliases = {
            "normal": cls.HP_BAR_STYLE_NORMAL,
            "classic": cls.HP_BAR_STYLE_NORMAL,
            "default": cls.HP_BAR_STYLE_NORMAL,
            "old": cls.HP_BAR_STYLE_NORMAL,
            "text": cls.HP_BAR_STYLE_NORMAL,
            "color": cls.HP_BAR_STYLE_COLORFUL,
            "colour": cls.HP_BAR_STYLE_COLORFUL,
            "colorful": cls.HP_BAR_STYLE_COLORFUL,
            "colourful": cls.HP_BAR_STYLE_COLORFUL,
            "emoji": cls.HP_BAR_STYLE_COLORFUL,
            "red": cls.HP_BAR_STYLE_COLORFUL,
            "allred": cls.HP_BAR_STYLE_COLORFUL,
            "team": cls.HP_BAR_STYLE_TEAM,
            "vs": cls.HP_BAR_STYLE_TEAM,
            "split": cls.HP_BAR_STYLE_TEAM,
            "faction": cls.HP_BAR_STYLE_TEAM,
            "friendly": cls.HP_BAR_STYLE_TEAM,
            "friendlyfoe": cls.HP_BAR_STYLE_TEAM,
            "redblue": cls.HP_BAR_STYLE_TEAM,
            "blue": cls.HP_BAR_STYLE_TEAM,
        }
        return aliases.get(normalized, cls.HP_BAR_STYLE_NORMAL)
    
    def __init__(self, ctx, teams=None, **kwargs):
        self.ctx = ctx
        self.bot = ctx.bot
        self.teams = teams or []
        self.log = deque(maxlen=kwargs.get("log_size", 5))
        self.action_number = 0
        self.started = False
        self.finished = False
        self.start_time = None
        self.max_duration = kwargs.get("max_duration", datetime.timedelta(minutes=5))
        self.winner = None
        self.battle_message = None
        
        # Generate unique battle ID for replay system
        self.battle_id = str(uuid.uuid4())
        self.battle_type = self.__class__.__name__
        
        # Enhanced replay system - store turn-by-turn states
        self.turn_states = []  # List of detailed battle states per turn
        self.initial_state = None  # Store initial battle state
        
        hp_bar_style = self.normalize_hp_bar_style(
            kwargs.get(
                "hp_bar_style",
                self.HP_BAR_STYLE_COLORFUL
                if kwargs.get("emoji_hp_bars", False)
                else self.HP_BAR_STYLE_NORMAL,
            )
        )
        self.friendly_team_indices = {0}

        # Configuration options
        self.config = {
            "allow_pets": kwargs.get("allow_pets", True),
            "class_buffs": kwargs.get("class_buffs", True),
            "element_effects": kwargs.get("element_effects", True),
            "luck_effects": kwargs.get("luck_effects", True),
            "reflection_damage": kwargs.get("reflection_damage", True),
            "hp_bar_style": hp_bar_style,
            "emoji_hp_bars": hp_bar_style != self.HP_BAR_STYLE_NORMAL,
            "fireball_chance": kwargs.get("fireball_chance", 0.3),
            "cheat_death": kwargs.get("cheat_death", True),
            "tripping": kwargs.get("tripping", True),
            "simple": kwargs.get("simple", False),  # Simple battle = classic battle format
            "status_effects": kwargs.get("status_effects", False),  # Enable status effects system
        }

        for team_index, team in enumerate(self.teams):
            for combatant in getattr(team, "combatants", []):
                setattr(combatant, "battle", self)
                setattr(combatant, "_battle_team_index", team_index)
    
    @abstractmethod
    async def start_battle(self):
        """Initialize and start the battle"""
        self.started = True
        self.start_time = datetime.datetime.utcnow()
        return True
    
    @abstractmethod
    async def process_turn(self):
        """Process a single turn of the battle"""
        pass
    
    @abstractmethod
    async def end_battle(self):
        """End the battle and handle rewards"""
        self.finished = True
        return None
    
    @abstractmethod
    async def update_display(self):
        """Update the battle display (embed)"""
        pass
    
    async def is_battle_over(self):
        """Check if battle has conditions to end"""
        return self.finished or await self.is_timed_out()
    
    async def is_timed_out(self):
        """Check if battle has exceeded maximum duration"""
        if not self.start_time:
            return False
        return datetime.datetime.utcnow() > self.start_time + self.max_duration
    
    async def add_to_log(self, message):
        """Add a message to the battle log"""
        self.log.append((self.action_number, message))
        self.action_number += 1
        
        # Capture detailed state for live replay
        await self.capture_turn_state(message)

    def format_battle_log_field(
        self,
        entries=None,
        *,
        empty_text="Battle starting...",
        max_length=1020,
    ):
        """Format battle log text safely for a Discord embed field."""
        log_entries = list(self.log if entries is None else entries)
        if not log_entries:
            return empty_text

        formatted_entries = [
            f"**Action #{action_num}**\n{message}"
            for action_num, message in log_entries
        ]
        log_text = "\n\n".join(formatted_entries)
        if len(log_text) <= max_length:
            return log_text

        truncation_notice = "*...earlier actions truncated...*"
        kept_entries = list(formatted_entries)

        while kept_entries:
            candidate = "\n\n".join(kept_entries)
            if len(candidate) + len(truncation_notice) + 2 <= max_length:
                return f"{truncation_notice}\n\n{candidate}"
            kept_entries.pop(0)

        available = max(max_length - len(truncation_notice) - 2, 0)
        if available <= 0:
            return truncation_notice[:max_length]

        latest_entry = formatted_entries[-1]
        if len(latest_entry) > available:
            if available > 1:
                latest_entry = latest_entry[: available - 1] + "..."
            else:
                latest_entry = latest_entry[:available]

        return f"{truncation_notice}\n\n{latest_entry}"

    def _split_embed_text(self, text, *, max_length=1024):
        """Split a long text payload into Discord embed-sized chunks."""
        if len(text) <= max_length:
            return [text]

        chunks = []
        current_lines = []
        current_length = 0

        for line in text.split("\n"):
            line_length = len(line)

            if current_lines:
                candidate_length = current_length + 1 + line_length
            else:
                candidate_length = line_length

            if candidate_length <= max_length:
                current_lines.append(line)
                current_length = candidate_length
                continue

            if current_lines:
                chunks.append("\n".join(current_lines))
                current_lines = []
                current_length = 0

            while len(line) > max_length:
                chunks.append(line[:max_length])
                line = line[max_length:]

            current_lines = [line]
            current_length = len(line)

        if current_lines:
            chunks.append("\n".join(current_lines))

        return chunks or [text[:max_length]]

    def format_battle_log_fields(
        self,
        entries=None,
        *,
        empty_text="Battle starting...",
        max_length=1020,
    ):
        """Return one or more embed-safe chunks for the full battle log."""
        log_entries = list(self.log if entries is None else entries)
        if not log_entries:
            return [empty_text]

        chunks = []
        current_chunk = ""

        for action_num, message in log_entries:
            entry = f"**Action #{action_num}**\n{message}"
            entry_chunks = self._split_embed_text(entry, max_length=max_length)

            for entry_chunk in entry_chunks:
                if not current_chunk:
                    current_chunk = entry_chunk
                    continue

                candidate = f"{current_chunk}\n\n{entry_chunk}"
                if len(candidate) <= max_length:
                    current_chunk = candidate
                else:
                    chunks.append(current_chunk)
                    current_chunk = entry_chunk

        if current_chunk:
            chunks.append(current_chunk)

        return chunks or [empty_text]

    async def _run_discord_request_with_retry(self, request, *, action_name, allow_not_found=False):
        for attempt in range(1, self.DISCORD_RETRY_ATTEMPTS + 1):
            try:
                return await request()
            except discord.NotFound as exc:
                if allow_not_found:
                    return None
                logger.warning(
                    "Battle %s Discord %s failed: message not found (%s)",
                    self.battle_id,
                    action_name,
                    exc,
                )
                return False
            except discord.Forbidden as exc:
                logger.warning(
                    "Battle %s Discord %s forbidden: %s",
                    self.battle_id,
                    action_name,
                    exc,
                )
                return False
            except (discord.DiscordServerError, asyncio.TimeoutError, OSError) as exc:
                if attempt < self.DISCORD_RETRY_ATTEMPTS:
                    await asyncio.sleep(self.DISCORD_RETRY_BASE_DELAY * attempt)
                    continue
                logger.warning(
                    "Battle %s Discord %s failed on attempt %s/%s: %s",
                    self.battle_id,
                    action_name,
                    attempt,
                    self.DISCORD_RETRY_ATTEMPTS,
                    exc,
                )
                return False
            except discord.HTTPException as exc:
                status = getattr(exc, "status", None)
                if status is not None and status >= 500:
                    if attempt < self.DISCORD_RETRY_ATTEMPTS:
                        await asyncio.sleep(self.DISCORD_RETRY_BASE_DELAY * attempt)
                        continue
                    logger.warning(
                        "Battle %s Discord %s failed on attempt %s/%s: %s",
                        self.battle_id,
                        action_name,
                        attempt,
                        self.DISCORD_RETRY_ATTEMPTS,
                        exc,
                    )
                    return False

                logger.warning(
                    "Battle %s Discord %s hit non-retryable HTTP error: %s",
                    self.battle_id,
                    action_name,
                    exc,
                )
                raise
            except Exception:
                logger.exception(
                    "Battle %s Discord %s hit an unexpected error",
                    self.battle_id,
                    action_name,
                )
                raise

    async def send_with_retry(self, **kwargs):
        return await self._run_discord_request_with_retry(
            lambda: self.ctx.send(**kwargs),
            action_name="send",
        )

    async def edit_with_retry(self, message, **kwargs):
        return await self._run_discord_request_with_retry(
            lambda: message.edit(**kwargs),
            action_name="edit",
            allow_not_found=True,
        )

    async def publish_battle_message(self, **kwargs):
        if self.battle_message:
            edit_result = await self.edit_with_retry(self.battle_message, **kwargs)
            if edit_result not in (None, False):
                self.battle_message = edit_result
                return self.battle_message
            if edit_result is False:
                return self.battle_message
            self.battle_message = None

        send_result = await self.send_with_retry(**kwargs)
        if send_result not in (None, False):
            self.battle_message = send_result
        return self.battle_message

    def register_summoned_combatant(self, combatant, *, team=None, summoner=None):
        """Bind a newly summoned combatant to this battle and its team color context."""
        if combatant is None:
            return None

        setattr(combatant, "battle", self)
        if summoner is not None:
            setattr(combatant, "summoner", summoner)

        team_index = None
        if team is not None:
            for index, team_ref in enumerate(self.teams):
                if team_ref is team:
                    team_index = index
                    break

        if team_index is None and summoner is not None:
            team_index = getattr(summoner, "_battle_team_index", None)

        if team_index is not None:
            setattr(combatant, "_battle_team_index", team_index)

        return combatant
    
    def is_friendly_combatant(self, combatant):
        """Return whether a combatant belongs to the viewer-friendly side."""
        return getattr(combatant, "_battle_team_index", None) in self.friendly_team_indices

    def _get_hp_bar_palette(self, style, friendly):
        if style == self.HP_BAR_STYLE_TEAM and friendly:
            return {
                "full_left": self.HP_BAR_BLUE_FULL_LEFT,
                "half_left": self.HP_BAR_BLUE_HALF_LEFT,
                "full_middle": self.HP_BAR_BLUE_FULL_MIDDLE,
                "half_middle": self.HP_BAR_BLUE_HALF_MIDDLE,
                "full_right": self.HP_BAR_BLUE_FULL_RIGHT,
                "half_right": self.HP_BAR_BLUE_HALF_RIGHT,
            }

        return {
            "full_left": self.HP_BAR_FULL_LEFT,
            "half_left": self.HP_BAR_HALF_LEFT,
            "full_middle": self.HP_BAR_FULL_MIDDLE,
            "half_middle": self.HP_BAR_HALF_MIDDLE,
            "full_right": self.HP_BAR_FULL_RIGHT,
            "half_right": self.HP_BAR_HALF_RIGHT,
        }

    def create_hp_bar(self, current_hp, max_hp, length=None, combatant=None, friendly=None):
        """Create either the classic text HP bar or the emoji HP bar."""
        ratio = float(current_hp) / float(max_hp) if float(max_hp or 0) > 0 else 0.0
        ratio = max(0.0, min(1.0, ratio))
        style = self.normalize_hp_bar_style(
            self.config.get(
                "hp_bar_style",
                self.HP_BAR_STYLE_COLORFUL
                if self.config.get("emoji_hp_bars", False)
                else self.HP_BAR_STYLE_NORMAL,
            )
        )

        if style == self.HP_BAR_STYLE_NORMAL:
            safe_length = max(1, int(length or 20))
            filled_length = int(safe_length * ratio)
            return ("█" * filled_length) + ("░" * (safe_length - filled_length))

        safe_length = max(3, int(length or 10))
        if friendly is None and combatant is not None:
            friendly = self.is_friendly_combatant(combatant)
        palette = self._get_hp_bar_palette(style, bool(friendly))
        total_half_steps = safe_length * 2
        filled_half_steps = int(round(ratio * total_half_steps))
        filled_half_steps = max(0, min(total_half_steps, filled_half_steps))

        tiles: list[str] = []
        for tile_index in range(safe_length):
            tile_units = max(0, min(2, filled_half_steps - (tile_index * 2)))

            if tile_index == 0:
                tiles.append(
                    palette["full_left"]
                    if tile_units >= 2
                    else palette["half_left"]
                    if tile_units == 1
                    else self.HP_BAR_EMPTY_LEFT
                )
                continue

            if tile_index == safe_length - 1:
                tiles.append(
                    palette["full_right"]
                    if tile_units >= 2
                    else palette["half_right"]
                    if tile_units == 1
                    else self.HP_BAR_EMPTY_RIGHT
                )
                continue

            if tile_units >= 2:
                tiles.append(palette["full_middle"])
            elif tile_units == 1:
                tiles.append(palette["half_middle"])
            else:
                tiles.append(self.HP_BAR_EMPTY_MIDDLE)

        return "".join(tiles)
        
    def format_number(self, number):
        """Format a number to 2 decimal places for display in battle messages"""
        if isinstance(number, Decimal):
            # Convert Decimal to float, then format to 2 decimal places
            return f"{float(number):.2f}"
        elif isinstance(number, (int, float)):
            # Format to 2 decimal places
            return f"{number:.2f}"
        # If not a number, return as is
        return str(number)

    def record_damage_event(self, source, target, amount):
        """Hook for battle types that want to aggregate damage events."""
        return None

    def apply_damage(self, source, target, amount):
        """Apply damage and record the actual HP lost after mitigation."""
        if target is None or not hasattr(target, "take_damage"):
            return Decimal("0")

        before_hp = Decimal(str(getattr(target, "hp", 0) or 0))
        target.take_damage(amount)
        after_hp = Decimal(str(getattr(target, "hp", 0) or 0))
        actual_damage = max(Decimal("0"), before_hp - after_hp)

        if actual_damage > 0:
            self.record_damage_event(source, target, actual_damage)

        return actual_damage

    def resolve_attack_element(self, attacker):
        """Resolve outgoing element for an attack action."""
        if not attacker:
            return "Unknown"
        if hasattr(attacker, "get_attack_element_for_turn"):
            return attacker.get_attack_element_for_turn() or "Unknown"
        return getattr(attacker, "attack_element", getattr(attacker, "element", "Unknown")) or "Unknown"

    def resolve_defense_element(self, defender):
        """Resolve incoming element used for defense checks."""
        if not defender:
            return "Unknown"
        if hasattr(defender, "get_defense_element"):
            return defender.get_defense_element() or "Unknown"
        return getattr(defender, "defense_element", getattr(defender, "element", "Unknown")) or "Unknown"

    def _get_battles_cog(self):
        if hasattr(self.ctx, "bot") and hasattr(self.ctx.bot, "cogs"):
            return self.ctx.bot.cogs.get("Battles")
        return None

    def _get_pet_extension(self):
        battles_cog = self._get_battles_cog()
        if not battles_cog:
            return None
        battle_factory = getattr(battles_cog, "battle_factory", None)
        return getattr(battle_factory, "pet_ext", None)

    def _get_element_extension(self):
        battles_cog = self._get_battles_cog()
        if not battles_cog:
            return None
        return getattr(battles_cog, "element_ext", None)

    def _get_class_extension(self):
        battles_cog = self._get_battles_cog()
        if not battles_cog:
            return None

        class_ext = getattr(battles_cog, "class_ext", None)
        if class_ext is not None:
            return class_ext

        battle_factory = getattr(battles_cog, "battle_factory", None)
        return getattr(battle_factory, "class_ext", None)

    def can_use_mage_fireball(self, combatant):
        return bool(
            self.config.get("class_buffs", True)
            and self.config.get("fireball_chance", 0) > 0
            and combatant is not None
            and not getattr(combatant, "is_pet", False)
            and getattr(combatant, "mage_evolution", None)
        )

    def can_use_paladin_smite(self, combatant):
        return bool(
            self.config.get("class_buffs", True)
            and combatant is not None
            and not getattr(combatant, "is_pet", False)
            and getattr(combatant, "paladin_evolution", None)
        )

    def can_use_raider_mark(self, combatant):
        return bool(
            self.config.get("class_buffs", True)
            and combatant is not None
            and not getattr(combatant, "is_pet", False)
            and getattr(combatant, "raider_evolution", None)
        )

    def can_use_ritualist_doom(self, combatant):
        return bool(
            self.config.get("class_buffs", True)
            and combatant is not None
            and not getattr(combatant, "is_pet", False)
            and getattr(combatant, "ritualist_evolution", None)
        )

    def can_use_paragon_mastery(self, combatant):
        return bool(
            self.config.get("class_buffs", True)
            and combatant is not None
            and not getattr(combatant, "is_pet", False)
            and getattr(combatant, "paragon_evolution", None)
        )

    @staticmethod
    def get_runtime_combatant_marker(combatant):
        if combatant is None:
            return None
        return int(id(combatant))

    @staticmethod
    def _get_runtime_state_bucket(combatant, attr_name):
        bucket = getattr(combatant, attr_name, None)
        if not isinstance(bucket, dict):
            bucket = {}
            setattr(combatant, attr_name, bucket)
        return bucket

    @staticmethod
    def _trim_runtime_state_bucket(combatant, attr_name):
        bucket = getattr(combatant, attr_name, None)
        if isinstance(bucket, dict) and not bucket:
            delattr(combatant, attr_name)

    def apply_capped_shield(self, combatant, shield_gain, shield_cap):
        shield_gain = Decimal(str(shield_gain or 0))
        shield_cap = Decimal(str(shield_cap or 0))
        if combatant is None or shield_gain <= 0 or shield_cap <= 0:
            return Decimal("0")

        current_shield = Decimal(str(getattr(combatant, "shield", 0) or 0))
        if shield_cap <= current_shield:
            return Decimal("0")

        actual_shield_gain = min(shield_gain, shield_cap - current_shield)
        if actual_shield_gain > 0:
            setattr(combatant, "shield", current_shield + actual_shield_gain)
        return actual_shield_gain

    def get_mage_fireball_damage_multiplier(self, combatant):
        level = int(getattr(combatant, "mage_evolution", 0) or 0)
        if level <= 0:
            return Decimal("1")

        class_ext = self._get_class_extension()
        multiplier_map = (
            getattr(class_ext, "evolution_damage_multiplier", None)
            if class_ext is not None
            else None
        ) or {
            1: 1.10,
            2: 1.20,
            3: 1.30,
            4: 1.50,
            5: 1.75,
            6: 2.00,
            7: 2.10,
        }
        return Decimal(str(multiplier_map.get(level, 1.0)))

    def get_mage_arcane_shield_gain(self, combatant):
        level = int(getattr(combatant, "mage_evolution", 0) or 0)
        if level <= 0:
            return Decimal("0")

        class_ext = self._get_class_extension()
        shield_map = (
            getattr(class_ext, "mage_arcane_shield_gain", None)
            if class_ext is not None
            else None
        ) or {
            1: 0.035,
            2: 0.040,
            3: 0.045,
            4: 0.050,
            5: 0.055,
            6: 0.060,
            7: 0.065,
        }
        return Decimal(str(shield_map.get(level, 0)))

    def get_mage_arcane_shield_cap(self, combatant):
        level = int(getattr(combatant, "mage_evolution", 0) or 0)
        if level <= 0:
            return Decimal("0")

        class_ext = self._get_class_extension()
        shield_cap_map = (
            getattr(class_ext, "mage_arcane_shield_cap", None)
            if class_ext is not None
            else None
        ) or {
            1: 0.15,
            2: 0.17,
            3: 0.19,
            4: 0.21,
            5: 0.23,
            6: 0.25,
            7: 0.26,
        }
        return Decimal(str(shield_cap_map.get(level, 0)))

    def get_paladin_faith_threshold(self):
        return 3

    def get_paladin_smite_damage_multiplier(self, combatant):
        level = int(getattr(combatant, "paladin_evolution", 0) or 0)
        if level <= 0:
            return Decimal("0")

        class_ext = self._get_class_extension()
        multiplier_map = (
            getattr(class_ext, "paladin_smite_damage_multiplier", None)
            if class_ext is not None
            else None
        ) or {
            1: 0.20,
            2: 0.25,
            3: 0.30,
            4: 0.35,
            5: 0.40,
            6: 0.45,
            7: 0.50,
        }
        return Decimal(str(multiplier_map.get(level, 0)))

    def get_paladin_holy_shield_gain(self, combatant):
        level = int(getattr(combatant, "paladin_evolution", 0) or 0)
        if level <= 0:
            return Decimal("0")

        class_ext = self._get_class_extension()
        shield_map = (
            getattr(class_ext, "paladin_holy_shield_gain", None)
            if class_ext is not None
            else None
        ) or {
            1: 0.04,
            2: 0.05,
            3: 0.06,
            4: 0.07,
            5: 0.08,
            6: 0.09,
            7: 0.10,
        }
        return Decimal(str(shield_map.get(level, 0)))

    def get_paladin_holy_shield_cap(self, combatant):
        level = int(getattr(combatant, "paladin_evolution", 0) or 0)
        if level <= 0:
            return Decimal("0")

        class_ext = self._get_class_extension()
        shield_cap_map = (
            getattr(class_ext, "paladin_holy_shield_cap", None)
            if class_ext is not None
            else None
        ) or {
            1: 0.12,
            2: 0.14,
            3: 0.16,
            4: 0.18,
            5: 0.20,
            6: 0.22,
            7: 0.24,
        }
        return Decimal(str(shield_cap_map.get(level, 0)))

    def get_raider_mark_threshold(self):
        return 3

    def get_raider_mark_damage_multiplier(self, combatant):
        level = int(getattr(combatant, "raider_evolution", 0) or 0)
        if level <= 0:
            return Decimal("0")

        class_ext = self._get_class_extension()
        multiplier_map = (
            getattr(class_ext, "raider_mark_damage_multiplier", None)
            if class_ext is not None
            else None
        ) or {
            1: 0.15,
            2: 0.18,
            3: 0.21,
            4: 0.24,
            5: 0.27,
            6: 0.30,
            7: 0.35,
        }
        return Decimal(str(multiplier_map.get(level, 0)))

    def get_raider_mark_max_hp_ratio(self, combatant):
        level = int(getattr(combatant, "raider_evolution", 0) or 0)
        if level <= 0:
            return Decimal("0")

        class_ext = self._get_class_extension()
        ratio_map = (
            getattr(class_ext, "raider_mark_max_hp_ratio", None)
            if class_ext is not None
            else None
        ) or {
            1: 0.010,
            2: 0.012,
            3: 0.014,
            4: 0.016,
            5: 0.018,
            6: 0.020,
            7: 0.025,
        }
        return Decimal(str(ratio_map.get(level, 0)))

    def get_paragon_break_damage_multiplier(self, combatant):
        level = int(getattr(combatant, "paragon_evolution", 0) or 0)
        if level <= 0:
            return Decimal("0")

        class_ext = self._get_class_extension()
        multiplier_map = (
            getattr(class_ext, "paragon_break_damage_multiplier", None)
            if class_ext is not None
            else None
        ) or {
            1: 0.08,
            2: 0.10,
            3: 0.12,
            4: 0.14,
            5: 0.16,
            6: 0.18,
            7: 0.20,
        }
        return Decimal(str(multiplier_map.get(level, 0)))

    def get_paragon_guard_shield_gain(self, combatant):
        level = int(getattr(combatant, "paragon_evolution", 0) or 0)
        if level <= 0:
            return Decimal("0")

        class_ext = self._get_class_extension()
        shield_map = (
            getattr(class_ext, "paragon_guard_shield_gain", None)
            if class_ext is not None
            else None
        ) or {
            1: 0.020,
            2: 0.025,
            3: 0.030,
            4: 0.035,
            5: 0.040,
            6: 0.045,
            7: 0.050,
        }
        return Decimal(str(shield_map.get(level, 0)))

    def get_paragon_balanced_damage_multiplier(self, combatant):
        level = int(getattr(combatant, "paragon_evolution", 0) or 0)
        if level <= 0:
            return Decimal("0")

        class_ext = self._get_class_extension()
        multiplier_map = (
            getattr(class_ext, "paragon_balanced_damage_multiplier", None)
            if class_ext is not None
            else None
        ) or {
            1: 0.04,
            2: 0.05,
            3: 0.06,
            4: 0.07,
            5: 0.08,
            6: 0.09,
            7: 0.10,
        }
        return Decimal(str(multiplier_map.get(level, 0)))

    def get_paragon_balanced_shield_gain(self, combatant):
        level = int(getattr(combatant, "paragon_evolution", 0) or 0)
        if level <= 0:
            return Decimal("0")

        class_ext = self._get_class_extension()
        shield_map = (
            getattr(class_ext, "paragon_balanced_shield_gain", None)
            if class_ext is not None
            else None
        ) or {
            1: 0.010,
            2: 0.012,
            3: 0.014,
            4: 0.016,
            5: 0.018,
            6: 0.020,
            7: 0.025,
        }
        return Decimal(str(shield_map.get(level, 0)))

    def get_paragon_shield_cap(self, combatant):
        level = int(getattr(combatant, "paragon_evolution", 0) or 0)
        if level <= 0:
            return Decimal("0")

        class_ext = self._get_class_extension()
        shield_cap_map = (
            getattr(class_ext, "paragon_shield_cap", None)
            if class_ext is not None
            else None
        ) or {
            1: 0.12,
            2: 0.14,
            3: 0.16,
            4: 0.18,
            5: 0.20,
            6: 0.22,
            7: 0.25,
        }
        return Decimal(str(shield_cap_map.get(level, 0)))

    def get_ritualist_doom_threshold(self):
        return 3

    def get_ritualist_doom_burst_multiplier(self, combatant):
        level = int(getattr(combatant, "ritualist_evolution", 0) or 0)
        if level <= 0:
            return Decimal("0")

        class_ext = self._get_class_extension()
        multiplier_map = (
            getattr(class_ext, "ritualist_doom_burst_multiplier", None)
            if class_ext is not None
            else None
        ) or {
            1: 0.12,
            2: 0.15,
            3: 0.18,
            4: 0.21,
            5: 0.24,
            6: 0.27,
            7: 0.30,
        }
        return Decimal(str(multiplier_map.get(level, 0)))

    def get_ritualist_doom_echo_multiplier(self, combatant):
        level = int(getattr(combatant, "ritualist_evolution", 0) or 0)
        if level <= 0:
            return Decimal("0")

        class_ext = self._get_class_extension()
        multiplier_map = (
            getattr(class_ext, "ritualist_doom_echo_multiplier", None)
            if class_ext is not None
            else None
        ) or {
            1: 0.06,
            2: 0.07,
            3: 0.08,
            4: 0.09,
            5: 0.10,
            6: 0.11,
            7: 0.12,
        }
        return Decimal(str(multiplier_map.get(level, 0)))

    def get_ritualist_favor_shield_gain(self, combatant):
        level = int(getattr(combatant, "ritualist_evolution", 0) or 0)
        if level <= 0:
            return Decimal("0")

        class_ext = self._get_class_extension()
        shield_map = (
            getattr(class_ext, "ritualist_favor_shield_gain", None)
            if class_ext is not None
            else None
        ) or {
            1: 0.04,
            2: 0.05,
            3: 0.06,
            4: 0.07,
            5: 0.08,
            6: 0.09,
            7: 0.10,
        }
        return Decimal(str(shield_map.get(level, 0)))

    def get_ritualist_favor_shield_cap(self, combatant):
        level = int(getattr(combatant, "ritualist_evolution", 0) or 0)
        if level <= 0:
            return Decimal("0")

        class_ext = self._get_class_extension()
        shield_cap_map = (
            getattr(class_ext, "ritualist_favor_shield_cap", None)
            if class_ext is not None
            else None
        ) or {
            1: 0.12,
            2: 0.14,
            3: 0.16,
            4: 0.18,
            5: 0.20,
            6: 0.22,
            7: 0.24,
        }
        return Decimal(str(shield_cap_map.get(level, 0)))

    def advance_mage_fireball_charge(self, combatant):
        if not self.can_use_mage_fireball(combatant):
            return None

        charge_gain = Decimal(str(self.config.get("fireball_chance", 0) or 0))
        charge_gain = max(Decimal("0"), min(Decimal("1"), charge_gain))
        current_charge = Decimal(str(getattr(combatant, "fireball_charge", 0) or 0))
        new_charge = current_charge + charge_gain

        if new_charge >= Decimal("1"):
            setattr(combatant, "fireball_charge", new_charge - Decimal("1"))
            return {
                "fireball_ready": True,
                "charge": Decimal(str(getattr(combatant, "fireball_charge", 0) or 0)),
                "shield_gained": Decimal("0"),
            }

        current_shield = Decimal(str(getattr(combatant, "shield", 0) or 0))
        max_hp = Decimal(str(getattr(combatant, "max_hp", 0) or 0))
        shield_cap = max_hp * self.get_mage_arcane_shield_cap(combatant)
        shield_gain = max_hp * self.get_mage_arcane_shield_gain(combatant)
        actual_shield_gain = Decimal("0")
        if shield_cap > current_shield and shield_gain > 0:
            actual_shield_gain = min(shield_gain, shield_cap - current_shield)
            if actual_shield_gain > 0:
                setattr(combatant, "shield", current_shield + actual_shield_gain)

        setattr(combatant, "fireball_charge", new_charge)
        return {
            "fireball_ready": False,
            "charge": new_charge,
            "shield_gained": actual_shield_gain,
        }

    def advance_paladin_smite(self, combatant, target):
        if not self.can_use_paladin_smite(combatant):
            return None

        threshold = self.get_paladin_faith_threshold()
        current_faith = int(getattr(combatant, "paladin_faith", 0) or 0)
        new_faith = current_faith + 1

        if new_faith < threshold:
            setattr(combatant, "paladin_faith", new_faith)
            return {
                "smite_triggered": False,
                "faith": new_faith,
                "threshold": threshold,
                "smite_damage": Decimal("0"),
                "shield_gained": Decimal("0"),
            }

        setattr(combatant, "paladin_faith", 0)

        base_damage = Decimal(str(getattr(combatant, "damage", 0) or 0))
        smite_damage = max(
            Decimal("10"),
            base_damage * self.get_paladin_smite_damage_multiplier(combatant),
        )

        actual_smite_damage = Decimal("0")
        if target is not None and hasattr(target, "take_damage") and target.is_alive():
            actual_smite_damage = self.apply_damage(combatant, target, smite_damage)

        current_shield = Decimal(str(getattr(combatant, "shield", 0) or 0))
        max_hp = Decimal(str(getattr(combatant, "max_hp", 0) or 0))
        shield_cap = max_hp * self.get_paladin_holy_shield_cap(combatant)
        shield_gain = max_hp * self.get_paladin_holy_shield_gain(combatant)
        actual_shield_gain = Decimal("0")
        if shield_cap > current_shield and shield_gain > 0:
            actual_shield_gain = min(shield_gain, shield_cap - current_shield)
            if actual_shield_gain > 0:
                setattr(combatant, "shield", current_shield + actual_shield_gain)

        return {
            "smite_triggered": True,
            "faith": 0,
            "threshold": threshold,
            "smite_damage": actual_smite_damage,
            "shield_gained": actual_shield_gain,
        }

    def advance_raider_mark(self, combatant, target):
        if not self.can_use_raider_mark(combatant) or target is None:
            return None

        if not getattr(target, "is_alive", lambda: False)():
            return None

        marker = self.get_runtime_combatant_marker(combatant)
        if marker is None:
            return None

        threshold = self.get_raider_mark_threshold()
        marks = self._get_runtime_state_bucket(target, "raider_marks")
        new_marks = int(marks.get(marker, 0) or 0) + 1
        target_name = getattr(target, "name", "the target")

        if new_marks < threshold:
            marks[marker] = new_marks
            return {
                "mark_triggered": False,
                "marks": new_marks,
                "threshold": threshold,
                "target_name": target_name,
                "bonus_damage": Decimal("0"),
            }

        marks.pop(marker, None)
        self._trim_runtime_state_bucket(target, "raider_marks")

        base_damage = Decimal(str(getattr(combatant, "damage", 0) or 0))
        max_hp = Decimal(str(getattr(target, "max_hp", 0) or 0))
        hp_damage = min(
            max_hp * self.get_raider_mark_max_hp_ratio(combatant),
            base_damage * Decimal("1.5"),
        )
        bonus_damage = max(
            Decimal("10"),
            (base_damage * self.get_raider_mark_damage_multiplier(combatant)) + hp_damage,
        )

        actual_bonus_damage = self.apply_damage(combatant, target, bonus_damage)
        return {
            "mark_triggered": True,
            "marks": 0,
            "threshold": threshold,
            "target_name": target_name,
            "bonus_damage": actual_bonus_damage,
        }

    def advance_ritualist_doom(self, combatant, target):
        if not self.can_use_ritualist_doom(combatant) or target is None:
            return None

        marker = self.get_runtime_combatant_marker(combatant)
        if marker is None:
            return None

        target_name = getattr(target, "name", "the target")
        threshold = self.get_ritualist_doom_threshold()
        doom_hits_bucket = self._get_runtime_state_bucket(target, "ritualist_doom_hits")
        sigil_bucket = self._get_runtime_state_bucket(target, "ritualist_sigil_stacks")
        target_alive = getattr(target, "is_alive", lambda: False)()

        existing_doom_hits = int(doom_hits_bucket.get(marker, 0) or 0)
        if not target_alive and existing_doom_hits <= 0:
            self._trim_runtime_state_bucket(target, "ritualist_doom_hits")
            self._trim_runtime_state_bucket(target, "ritualist_sigil_stacks")
            return None

        doom_hits_remaining = existing_doom_hits
        echo_damage = Decimal("0")
        if existing_doom_hits > 0:
            if target_alive:
                echo_damage = self.apply_damage(
                    combatant,
                    target,
                    max(
                        Decimal("5"),
                        Decimal(str(getattr(combatant, "damage", 0) or 0))
                        * self.get_ritualist_doom_echo_multiplier(combatant),
                    ),
                )
            doom_hits_remaining = existing_doom_hits - 1
            if doom_hits_remaining > 0:
                doom_hits_bucket[marker] = doom_hits_remaining
            else:
                doom_hits_bucket.pop(marker, None)
            target_alive = getattr(target, "is_alive", lambda: False)()

        burst_triggered = False
        burst_damage = Decimal("0")
        current_sigils = int(sigil_bucket.get(marker, 0) or 0)
        if target_alive:
            new_sigils = current_sigils + 1
            if new_sigils >= threshold:
                sigil_bucket.pop(marker, None)
                burst_triggered = True
                burst_damage = self.apply_damage(
                    combatant,
                    target,
                    max(
                        Decimal("10"),
                        Decimal(str(getattr(combatant, "damage", 0) or 0))
                        * self.get_ritualist_doom_burst_multiplier(combatant),
                    ),
                )
                target_alive = getattr(target, "is_alive", lambda: False)()
                if target_alive:
                    doom_hits_bucket[marker] = 2
                    doom_hits_remaining = 2
                else:
                    doom_hits_bucket.pop(marker, None)
                    doom_hits_remaining = 0
                current_sigils = 0
            else:
                sigil_bucket[marker] = new_sigils
                current_sigils = new_sigils

        favor_shield_gained = Decimal("0")
        if not getattr(target, "is_alive", lambda: False)() and (existing_doom_hits > 0 or burst_triggered):
            max_hp = Decimal(str(getattr(combatant, "max_hp", 0) or 0))
            favor_shield_gained = self.apply_capped_shield(
                combatant,
                max_hp * self.get_ritualist_favor_shield_gain(combatant),
                max_hp * self.get_ritualist_favor_shield_cap(combatant),
            )
            doom_hits_bucket.pop(marker, None)
            sigil_bucket.pop(marker, None)
            current_sigils = 0
            doom_hits_remaining = 0

        self._trim_runtime_state_bucket(target, "ritualist_doom_hits")
        self._trim_runtime_state_bucket(target, "ritualist_sigil_stacks")
        return {
            "echo_damage": echo_damage,
            "burst_triggered": burst_triggered,
            "burst_damage": burst_damage,
            "sigils": current_sigils,
            "threshold": threshold,
            "doom_hits_remaining": doom_hits_remaining,
            "target_name": target_name,
            "favor_shield_gained": favor_shield_gained,
        }

    def resolve_paragon_mastery(self, combatant, target):
        if not self.can_use_paragon_mastery(combatant) or target is None:
            return None

        attacker_damage = Decimal(str(getattr(combatant, "damage", 0) or 0))
        target_armor = Decimal(str(getattr(target, "armor", 0) or 0))
        target_damage = Decimal(str(getattr(target, "damage", 0) or 0))
        max_hp = Decimal(str(getattr(combatant, "max_hp", 0) or 0))

        mode = "harmonic"
        bonus_damage = Decimal("0")
        shield_gained = Decimal("0")

        if target_armor >= attacker_damage * Decimal("0.75"):
            mode = "breaker"
            if getattr(target, "is_alive", lambda: False)():
                bonus_damage = self.apply_damage(
                    combatant,
                    target,
                    max(
                        Decimal("5"),
                        attacker_damage * self.get_paragon_break_damage_multiplier(combatant),
                    ),
                )
        elif target_damage >= attacker_damage * Decimal("1.10"):
            mode = "bulwark"
            shield_gained = self.apply_capped_shield(
                combatant,
                max_hp * self.get_paragon_guard_shield_gain(combatant),
                max_hp * self.get_paragon_shield_cap(combatant),
            )
        else:
            if getattr(target, "is_alive", lambda: False)():
                bonus_damage = self.apply_damage(
                    combatant,
                    target,
                    max(
                        Decimal("5"),
                        attacker_damage * self.get_paragon_balanced_damage_multiplier(combatant),
                    ),
                )
            shield_gained = self.apply_capped_shield(
                combatant,
                max_hp * self.get_paragon_balanced_shield_gain(combatant),
                max_hp * self.get_paragon_shield_cap(combatant),
            )

        return {
            "mode": mode,
            "bonus_damage": bonus_damage,
            "shield_gained": shield_gained,
        }

    def format_mage_charge_message(self, charge_state):
        if not charge_state or charge_state.get("fireball_ready"):
            return None

        charge_percent = max(
            0,
            min(99, int(round(float(charge_state.get("charge", 0)) * 100))),
        )
        shield_gained = Decimal(str(charge_state.get("shield_gained", 0) or 0))
        if shield_gained > 0:
            return (
                f"✨ Arcane charge rises to **{charge_percent}%** and "
                f"Arcane Shield absorbs **{self.format_number(shield_gained)} HP**."
            )
        return f"✨ Arcane charge rises to **{charge_percent}%**."

    def format_paladin_smite_message(self, smite_state):
        if not smite_state:
            return None

        if not smite_state.get("smite_triggered"):
            faith = int(smite_state.get("faith", 0) or 0)
            threshold = int(smite_state.get("threshold", self.get_paladin_faith_threshold()) or 1)
            return f"🙏 Faith rises to **{faith}/{threshold}**."

        smite_damage = Decimal(str(smite_state.get("smite_damage", 0) or 0))
        shield_gained = Decimal(str(smite_state.get("shield_gained", 0) or 0))
        if smite_damage > 0 and shield_gained > 0:
            return (
                f"✝️ Divine Smite crashes down for **{self.format_number(smite_damage)} HP** "
                f"holy damage and Holy Shield absorbs **{self.format_number(shield_gained)} HP**."
            )
        if smite_damage > 0:
            return f"✝️ Divine Smite crashes down for **{self.format_number(smite_damage)} HP** holy damage."
        if shield_gained > 0:
            return f"🛡️ Faith becomes Holy Shield, absorbing **{self.format_number(shield_gained)} HP**."
        return "✝️ Divine Smite surges through the battlefield."

    def format_raider_mark_message(self, mark_state):
        if not mark_state:
            return None

        target_name = mark_state.get("target_name", "the target")
        if not mark_state.get("mark_triggered"):
            return (
                f"🏴 Raid Mark settles on **{target_name}** "
                f"(**{int(mark_state.get('marks', 0) or 0)}/{int(mark_state.get('threshold', 3) or 3)}**)."
            )

        bonus_damage = Decimal(str(mark_state.get("bonus_damage", 0) or 0))
        return (
            f"⚔️ Raid Mark detonates on **{target_name}** for "
            f"**{self.format_number(bonus_damage)} HP** bonus damage!"
        )

    def format_ritualist_doom_message(self, doom_state):
        if not doom_state:
            return None

        parts = []
        echo_damage = Decimal(str(doom_state.get("echo_damage", 0) or 0))
        if echo_damage > 0:
            remaining = int(doom_state.get("doom_hits_remaining", 0) or 0)
            if remaining > 0:
                parts.append(
                    f"☠️ Doom Echo tears for **{self.format_number(echo_damage)} HP** "
                    f"(**{remaining}** hit(s) remain)."
                )
            else:
                parts.append(f"☠️ Doom Echo tears for **{self.format_number(echo_damage)} HP**.")

        if doom_state.get("burst_triggered"):
            burst_damage = Decimal(str(doom_state.get("burst_damage", 0) or 0))
            parts.append(
                f"🔮 Doom Sigils align on **{doom_state.get('target_name', 'the target')}** for "
                f"**{self.format_number(burst_damage)} HP** and bind doom for **2 hits**."
            )
        elif doom_state.get("sigils", 0):
            parts.append(
                f"🔮 Doom Sigils gather on **{doom_state.get('target_name', 'the target')}** "
                f"(**{int(doom_state.get('sigils', 0) or 0)}/{int(doom_state.get('threshold', 3) or 3)}**)."
            )

        favor_shield = Decimal(str(doom_state.get("favor_shield_gained", 0) or 0))
        if favor_shield > 0:
            parts.append(
                f"🩸 Fallen doom feeds Favor Ward, absorbing **{self.format_number(favor_shield)} HP**."
            )

        return "\n".join(parts) if parts else None

    def format_paragon_mastery_message(self, paragon_state):
        if not paragon_state:
            return None

        mode = paragon_state.get("mode")
        bonus_damage = Decimal(str(paragon_state.get("bonus_damage", 0) or 0))
        shield_gained = Decimal(str(paragon_state.get("shield_gained", 0) or 0))

        if mode == "breaker":
            return (
                f"🗡️ Adaptive Mastery breaks through for "
                f"**{self.format_number(bonus_damage)} HP** bonus damage."
            )
        if mode == "bulwark":
            return (
                f"🛡️ Adaptive Mastery forms a barrier of "
                f"**{self.format_number(shield_gained)} HP**."
            )
        if bonus_damage > 0 and shield_gained > 0:
            return (
                f"✨ Adaptive Mastery balances offense and defense: "
                f"**{self.format_number(bonus_damage)} HP** bonus damage and "
                f"**{self.format_number(shield_gained)} HP** barrier."
            )
        if bonus_damage > 0:
            return f"✨ Adaptive Mastery strikes for **{self.format_number(bonus_damage)} HP** bonus damage."
        if shield_gained > 0:
            return f"✨ Adaptive Mastery forms a barrier of **{self.format_number(shield_gained)} HP**."
        return None

    def resolve_post_hit_class_effects(self, combatant, target):
        messages = []

        for resolver, formatter in (
            (self.advance_raider_mark, self.format_raider_mark_message),
            (self.resolve_paragon_mastery, self.format_paragon_mastery_message),
            (self.advance_ritualist_doom, self.format_ritualist_doom_message),
            (self.advance_paladin_smite, self.format_paladin_smite_message),
        ):
            state = resolver(combatant, target)
            message = formatter(state)
            if message:
                messages.append(message)

        return messages

    def calculate_mage_fireball_damage(
        self,
        attacker,
        target,
        *,
        damage_variance=100,
        minimum_damage=Decimal("10"),
    ):
        damage_variance = Decimal(str(damage_variance))
        minimum_damage = Decimal(str(minimum_damage))
        raw_damage = Decimal(str(getattr(attacker, "damage", 0) or 0))
        raw_damage += Decimal(str(random.randint(0, int(damage_variance))))
        raw_damage -= Decimal(str(getattr(target, "armor", 0) or 0))
        return max(
            raw_damage * self.get_mage_fireball_damage_multiplier(attacker),
            minimum_damage,
        )

    def get_cheat_death_recovery_hp(self, combatant):
        max_hp = Decimal(str(getattr(combatant, "max_hp", 0) or 0))
        if max_hp <= 0:
            return Decimal("75")
        return min(max_hp, max(Decimal("75"), max_hp * Decimal("0.50")))

    def get_turn_priority(self, combatant):
        """Calculate turn priority score for ordering combatants."""
        if not combatant:
            return Decimal("0")

        priority = Decimal("0")
        if getattr(combatant, "attack_priority", False):
            priority += Decimal("1000")
        if getattr(combatant, "quick_charge_active", False):
            priority += Decimal("800")
        if int(getattr(combatant, "storm_lord_haste", 0) or 0) > 0:
            priority += Decimal("600")
        if getattr(combatant, "air_currents_boost", False):
            priority += Decimal("300")
        if getattr(combatant, "freedom_boost", False):
            priority += Decimal("200")
        if getattr(combatant, "sky_haste", False):
            priority += Decimal("250")
        if int(getattr(combatant, "storm_dominated", 0) or 0) > 0:
            priority -= Decimal("300")
        if hasattr(combatant, "zephyr_speed"):
            priority += Decimal(str(getattr(combatant, "zephyr_speed", 0))) * Decimal("100")
        if hasattr(combatant, "zephyr_slow"):
            priority -= Decimal(str(getattr(combatant, "zephyr_slow", 0))) * Decimal("100")
        return priority

    def prioritize_turn_order(self, combatants):
        """Return combatants sorted by priority while preserving original order ties."""
        indexed = list(enumerate(combatants))
        indexed.sort(key=lambda item: (-self.get_turn_priority(item[1]), item[0]))
        return [combatant for _, combatant in indexed]

    def resolve_pet_attack_outcome(
        self,
        attacker,
        defender,
        raw_damage,
        *,
        apply_element_mod=True,
        damage_variance=0,
        minimum_damage=Decimal("10"),
    ):
        """Canonical damage resolution path for all pet-enabled battle modes."""
        raw_damage = Decimal(str(raw_damage))
        damage_variance = Decimal(str(damage_variance))
        minimum_damage = Decimal(str(minimum_damage))
        blocked_damage = Decimal("0")
        skill_messages: List[str] = []
        defender_messages: List[str] = []
        ignore_reflection_this_hit = False

        pet_ext = self._get_pet_extension()
        element_ext = self._get_element_extension()

        # 1) Element modifier on base damage (mode-configurable).
        if apply_element_mod and self.config.get("element_effects", True) and element_ext:
            element_mod = element_ext.calculate_damage_modifier(
                self.ctx,
                self.resolve_attack_element(attacker),
                self.resolve_defense_element(defender),
            )
            # Void affinity protection is a pet-only defensive mechanic.
            if pet_ext and getattr(attacker, "is_pet", False):
                element_mod = pet_ext.apply_void_affinity_protection(defender, element_mod)
            if element_mod != 0:
                raw_damage = raw_damage * (Decimal("1") + Decimal(str(element_mod)))

        # 2) Add per-hit variance.
        raw_damage += damage_variance

        # 3) Pet attack skill effects.
        if pet_ext and getattr(attacker, "is_pet", False):
            raw_damage, skill_messages = pet_ext.process_skill_effects_on_attack(attacker, defender, raw_damage)
            setattr(attacker, "attacked_this_turn", True)
            ignore_reflection_this_hit = bool(getattr(attacker, "ignore_reflection_this_hit", False))
            if hasattr(attacker, "ignore_reflection_this_hit"):
                delattr(attacker, "ignore_reflection_this_hit")

        # 4) Apply armor/defense bypass rules.
        ignore_armor = getattr(defender, "ignore_armor_this_hit", False)
        true_damage = getattr(defender, "true_damage", False)
        bypass_defenses = getattr(defender, "bypass_defenses", False)
        ignore_all = getattr(defender, "ignore_all_defenses", False)
        partial_true_damage = Decimal(str(getattr(defender, "partial_true_damage", 0)))

        if ignore_all or true_damage or ignore_armor or bypass_defenses:
            final_damage = raw_damage
            blocked_damage = Decimal("0")
        elif partial_true_damage > 0:
            normal_after_armor = max(raw_damage - defender.armor, minimum_damage)
            final_damage = normal_after_armor + partial_true_damage
            blocked_damage = min(raw_damage, defender.armor)
        else:
            blocked_damage = min(raw_damage, defender.armor)
            final_damage = max(raw_damage - defender.armor, minimum_damage)

        # 5) Clear one-hit flags in one place.
        for flag in [
            "ignore_armor_this_hit",
            "true_damage",
            "bypass_defenses",
            "ignore_all_defenses",
            "partial_true_damage",
        ]:
            if hasattr(defender, flag):
                delattr(defender, flag)

        # 6) Defender pet mitigation effects.
        if pet_ext and getattr(defender, "is_pet", False):
            final_damage, defender_messages = pet_ext.process_skill_effects_on_damage_taken(
                defender, attacker, final_damage
            )
            if hasattr(defender, "lights_guidance_original_skill_effects"):
                defender.skill_effects = getattr(defender, "lights_guidance_original_skill_effects")
                delattr(defender, "lights_guidance_original_skill_effects")

        # 7) Track damage dealt for pet lifesteal and per-turn effects.
        if getattr(attacker, "is_pet", False):
            setattr(attacker, "last_damage_dealt", final_damage)

        return PetAttackOutcome(
            final_damage=Decimal(str(final_damage)),
            blocked_damage=Decimal(str(blocked_damage)),
            skill_messages=skill_messages,
            defender_messages=defender_messages,
            metadata={
                "raw_damage_after_mods": Decimal(str(raw_damage)),
                "ignore_reflection_this_hit": ignore_reflection_this_hit,
                "partial_true_damage": partial_true_damage,
            },
        )

    def get_team_for_combatant(self, combatant):
        for team in self.teams:
            if combatant in getattr(team, "combatants", []):
                return team
        return None

    def get_enemy_team_for_combatant(self, combatant):
        current_team = self.get_team_for_combatant(combatant)
        if current_team is None:
            return None
        for team in self.teams:
            if team is not current_team:
                return team
        return None

    def prepare_pet_context(self, combatant):
        if combatant is None or not getattr(combatant, "is_pet", False):
            return False

        team = self.get_team_for_combatant(combatant)
        enemy_team = self.get_enemy_team_for_combatant(combatant)
        if team is not None:
            setattr(combatant, "team", team)
        if enemy_team is not None:
            setattr(combatant, "enemy_team", enemy_team)
        setattr(combatant, "battle", self)
        return True

    def process_pet_turn_effects(self, combatant):
        pet_ext = self._get_pet_extension()
        if not pet_ext or combatant is None or not getattr(combatant, "is_pet", False):
            return []
        self.prepare_pet_context(combatant)
        return pet_ext.process_skill_effects_per_turn(combatant)

    def process_pet_death_effects(self, combatant):
        pet_ext = self._get_pet_extension()
        if not pet_ext or combatant is None or not getattr(combatant, "is_pet", False):
            return []
        self.prepare_pet_context(combatant)
        return pet_ext.process_skill_effects_on_death(combatant)

    def consume_pet_skill_action_lock(self, combatant):
        if combatant is None:
            return None

        for status_name, message in (
            ("stunned", "is stunned and cannot act!"),
            ("paralyzed", "is paralyzed and cannot act!"),
            ("tidal_delayed", "is swept back by tidal forces and loses the turn!"),
        ):
            turns = int(getattr(combatant, status_name, 0) or 0)
            if turns <= 0:
                continue

            if turns <= 1:
                delattr(combatant, status_name)
            else:
                setattr(combatant, status_name, turns - 1)
            return f"{combatant.name} {message}"

        return None

    def maybe_trigger_guardian_angel(self, target):
        if target is None or getattr(target, "is_pet", False) or target.is_alive():
            return None

        team = self.get_team_for_combatant(target)
        pet_ext = self._get_pet_extension()
        if team is None or pet_ext is None:
            return None

        for ally in getattr(team, "combatants", []):
            if ally is target or not getattr(ally, "is_pet", False) or not ally.is_alive():
                continue

            skill_effects = getattr(ally, "skill_effects", {})
            if "guardian_angel" not in skill_effects or getattr(ally, "guardian_used", False):
                continue

            owner = pet_ext.find_owner_combatant(ally)
            if owner is not target:
                continue

            ally.guardian_used = True
            ally.hp = Decimal("0")
            target.hp = min(target.max_hp, max(Decimal("1"), target.max_hp * Decimal("0.60")))
            current_shield = Decimal(str(getattr(target, "shield", 0) or 0))
            target.shield = current_shield + (target.max_hp * Decimal("0.20"))
            return (
                f"🕊️ **{ally.name}** sacrifices itself with Guardian Angel! "
                f"**{target.name}** is restored to **{self.format_number(target.hp)} HP** "
                "and wrapped in holy light."
            )

        return None

    def apply_pet_owner_guard(self, attacker, target, damage):
        damage = Decimal(str(damage))
        if damage <= 0 or target is None or getattr(target, "is_pet", False):
            return damage, [], None

        team = self.get_team_for_combatant(target)
        pet_ext = self._get_pet_extension()
        if team is None or pet_ext is None:
            return damage, [], None

        for ally in getattr(team, "combatants", []):
            if ally is target or not getattr(ally, "is_pet", False) or not ally.is_alive():
                continue

            self.prepare_pet_context(ally)
            skill_effects = getattr(ally, "skill_effects", {})
            embrace = skill_effects.get("oceans_embrace")
            if not embrace:
                continue

            owner = pet_ext.find_owner_combatant(ally)
            if owner is not target:
                continue

            redirected_damage = damage * Decimal(str(embrace.get("damage_share", 0)))
            if redirected_damage <= 0:
                continue

            pet_damage, pet_messages = pet_ext.process_skill_effects_on_damage_taken(
                ally,
                attacker,
                redirected_damage,
            )
            self.apply_damage(attacker, ally, pet_damage)
            messages = list(pet_messages)
            messages.append(
                f"💧 **{ally.name}** intercepts **{self.format_number(pet_damage)} HP** "
                f"for **{target.name}** with Ocean's Embrace!"
            )
            return damage - redirected_damage, messages, ally

        return damage, [], None

    def apply_bonus_lifesteal(self, attacker, damage):
        bonus_lifesteal = Decimal(str(getattr(attacker, "bonus_lifesteal", 0) or 0))
        bonus_lifesteal += Decimal(str(getattr(attacker, "dark_ritual_lifesteal", 0) or 0))
        if bonus_lifesteal <= 0:
            return Decimal("0")

        heal_amount = Decimal(str(damage)) * bonus_lifesteal
        if heal_amount <= 0:
            return Decimal("0")

        attacker.heal(heal_amount)
        return heal_amount

    def _get_counter_element(self, enemy_team, current_element):
        element_ext = self._get_element_extension()
        strengths = getattr(element_ext, "element_strengths", {}) if element_ext else {}
        if not strengths or enemy_team is None:
            return current_element

        enemy_elements = []
        for combatant in getattr(enemy_team, "combatants", []):
            if combatant.is_alive():
                element = self.resolve_defense_element(combatant)
                if element and element != "Unknown":
                    enemy_elements.append(element)
        if not enemy_elements:
            return current_element

        def score(candidate):
            total = 0
            for enemy_element in enemy_elements:
                if strengths.get(candidate) == enemy_element:
                    total += 2
                if strengths.get(enemy_element) == candidate:
                    total -= 1
            return total

        best_element = current_element
        best_score = score(current_element)
        candidates = ("Light", "Dark", "Corrupted", "Nature", "Electric", "Water", "Fire", "Wind")
        for candidate in candidates:
            candidate_score = score(candidate)
            if candidate_score > best_score:
                best_element = candidate
                best_score = candidate_score
        return best_element

    def _grant_team_shield(self, team, shield_scale: Decimal) -> None:
        for combatant in getattr(team, "combatants", []):
            if not combatant.is_alive():
                continue
            current_shield = Decimal(str(getattr(combatant, "shield", 0)))
            setattr(
                combatant,
                "shield",
                current_shield + (combatant.max_hp * shield_scale),
            )

    def _spawn_ascension_echo(
        self,
        *,
        source,
        summoner=None,
        team,
        name: str,
        hp_scale: Decimal,
        damage_scale: Decimal,
        armor_scale: Decimal,
        element: str | None = None,
    ):
        if team is None:
            return None

        from .combatant import Combatant

        echo = Combatant(
            user=name,
            hp=max(75, int(round(float(source.max_hp * hp_scale)))),
            max_hp=max(75, int(round(float(source.max_hp * hp_scale)))),
            damage=max(25, int(round(float(source.damage * damage_scale)))),
            armor=max(10, int(round(float(source.armor * armor_scale)))),
            element=element or getattr(source, "element", "Unknown"),
            luck=85,
            name=name,
            attack_priority=True,
            is_pet=False,
        )
        echo.is_summoned = True
        self.register_summoned_combatant(
            echo,
            team=team,
            summoner=summoner or source,
        )
        team.combatants.append(echo)
        if hasattr(self, "turn_order"):
            self.turn_order.append(echo)
            self.turn_order = self.prioritize_turn_order(self.turn_order)
        refresh_queue = getattr(self, "_refresh_player_turn_queue", None)
        if callable(refresh_queue):
            refresh_queue()
        return echo

    def _get_active_ascension_mantle(self, combatant):
        if combatant is None or not getattr(combatant, "ascension_enabled", True):
            return None
        return get_ascension_mantle(getattr(combatant, "ascension_mantle", None))

    async def trigger_ascension_openings(self):
        messages = []
        for team in self.teams:
            for combatant in list(getattr(team, "combatants", [])):
                if not combatant.is_alive() or getattr(combatant, "is_pet", False):
                    continue

                mantle = self._get_active_ascension_mantle(combatant)
                if mantle is None or getattr(combatant, "ascension_opening_used", False):
                    continue

                enemy_team = self.get_enemy_team_for_combatant(combatant)
                if mantle.key == "thronekeeper" and enemy_team is not None:
                    combatant.ascension_opening_used = True
                    self._grant_team_shield(team, Decimal("0.22"))
                    for enemy in getattr(enemy_team, "combatants", []):
                        if enemy.is_alive():
                            setattr(enemy, "ascension_silenced_turns", max(1, int(getattr(enemy, "ascension_silenced_turns", 0) or 0)))
                    messages.append(
                        f"👑 **{mantle.signature_name}:** {combatant.name} raises a golden decree. "
                        "Allies gain radiant shields and the enemy's first action is sealed."
                    )
                elif mantle.key == "cyclebreaker" and enemy_team is not None:
                    combatant.ascension_opening_used = True
                    current_element = self.resolve_attack_element(combatant)
                    new_element = self._get_counter_element(enemy_team, current_element)
                    combatant.attack_element = new_element
                    combatant.defense_element = new_element
                    combatant.element = new_element
                    combatant.attack_priority = True
                    messages.append(
                        f"🌀 **Fractured Attunement:** {combatant.name} studies the broken timeline and "
                        f"realigns to **{new_element}**."
                    )
        return messages

    def consume_ascension_action_lock(self, combatant):
        turns = int(getattr(combatant, "ascension_silenced_turns", 0) or 0)
        if turns <= 0:
            return None
        remaining = turns - 1
        if remaining > 0:
            setattr(combatant, "ascension_silenced_turns", remaining)
        else:
            try:
                delattr(combatant, "ascension_silenced_turns")
            except AttributeError:
                setattr(combatant, "ascension_silenced_turns", 0)
        return (
            f"🔒 **Edict of Silence:** {combatant.name} is bound by throne-law and cannot act."
        )

    async def maybe_trigger_grave_sovereign(self, attacker, target):
        mantle = self._get_active_ascension_mantle(attacker)
        if (
            mantle is None
            or mantle.key != "grave_sovereign"
            or getattr(attacker, "ascension_signature_used", False)
            or getattr(attacker, "is_pet", False)
            or target is None
        ):
            return None

        target_max_hp = Decimal(str(getattr(target, "max_hp", 0)))
        if target_max_hp <= 0:
            return None

        target_hp = Decimal(str(getattr(target, "hp", 0)))
        if target.is_alive() and (target_hp / target_max_hp) > Decimal("0.35"):
            return None

        attacker.ascension_signature_used = True
        ally_team = self.get_team_for_combatant(attacker)
        bonus_damage = Decimal("0")
        if target.is_alive():
            bonus_damage = max(target_max_hp * Decimal("0.18"), attacker.damage * Decimal("0.85"))
            existing_true_damage = Decimal(str(getattr(target, "pending_true_damage_bypass_shield", 0)))
            setattr(
                target,
                "pending_true_damage_bypass_shield",
                existing_true_damage + bonus_damage,
            )
            self.apply_damage(attacker, target, bonus_damage)

        self._spawn_ascension_echo(
            source=target,
            summoner=attacker,
            team=ally_team,
            name=f"Grave Echo of {target.name}",
            hp_scale=Decimal("0.32"),
            damage_scale=Decimal("0.40"),
            armor_scale=Decimal("0.28"),
            element="Dark",
        )

        if bonus_damage > 0:
            return (
                f"☠️ **{mantle.signature_name}:** {attacker.name} tears a Grave Echo from {target.name}, "
                f"dealing **{self.format_number(bonus_damage)} HP** true damage and forcing the echo to kneel."
            )
        return (
            f"☠️ **{mantle.signature_name}:** {attacker.name} rips a Grave Echo from the ruin of {target.name}. "
            "The dead answer your crown."
        )

    async def maybe_trigger_cyclebreaker(self, target, attacker):
        mantle = self._get_active_ascension_mantle(target)
        if (
            mantle is None
            or mantle.key != "cyclebreaker"
            or getattr(target, "ascension_survival_used", False)
            or getattr(target, "is_pet", False)
            or target.is_alive()
        ):
            return None

        target.ascension_survival_used = True
        target.hp = min(target.max_hp, max(Decimal("75"), target.max_hp * Decimal("0.40")))
        current_shield = Decimal(str(getattr(target, "shield", 0)))
        target.shield = current_shield + (target.max_hp * Decimal("0.20"))
        target.attack_priority = True

        enemy_team = self.get_enemy_team_for_combatant(target)
        if enemy_team is not None:
            new_element = self._get_counter_element(enemy_team, self.resolve_attack_element(target))
            target.attack_element = new_element
            target.defense_element = new_element
            target.element = new_element

        ally_team = self.get_team_for_combatant(target)
        self._spawn_ascension_echo(
            source=target,
            summoner=target,
            team=ally_team,
            name=f"Paradox Echo of {target.name}",
            hp_scale=Decimal("0.34"),
            damage_scale=Decimal("0.42"),
            armor_scale=Decimal("0.34"),
            element=getattr(target, "element", "Corrupted"),
        )

        if attacker is not None and attacker.is_alive():
            setattr(attacker, "ascension_silenced_turns", max(1, int(getattr(attacker, "ascension_silenced_turns", 0) or 0)))

        return (
            f"🌀 **{mantle.signature_name}:** Reality rejects the killing blow. {target.name} returns with "
            f"**{self.format_number(target.hp)} HP**, a paradox barrier, and an echo from a winning timeline."
        )
        
    # ----- Status Effect System Methods -----
    
    async def apply_status_effect(self, effect_type, target, source=None, **kwargs):
        """Apply a status effect to a target combatant"""
        try:
            # Create the effect from the registry
            effect = StatusEffectRegistry.create(effect_type, **kwargs)
            
            # Apply to the target
            effect.apply(target, source)
            
            # Add to battle log
            effect_msg = f"{effect.name} applied to {target.name}"
            if source:
                effect_msg = f"{source.name} applied {effect.name} to {target.name}"
            await self.add_to_log(effect_msg)
            
            return effect
        except ValueError as e:
            # Unknown effect type
            await self.add_to_log(f"Failed to apply effect: {str(e)}")
            return None
    
    async def process_combatant_effects(self, combatant, is_turn_start=False):
        """Process status effects for a specific combatant"""
        messages = []
        
        # First, process expiration and tick events
        status_messages = combatant.process_status_effects()
        if status_messages:
            messages.extend(status_messages)
        
        # Then process turn start/end effects
        if is_turn_start:
            turn_messages = combatant.process_turn_start_effects()
        else:
            turn_messages = combatant.process_turn_end_effects()
            
        if turn_messages:
            messages.extend(turn_messages)
            
        # Add all messages to battle log
        for message in messages:
            await self.add_to_log(message)
        
        return messages
    
    def get_effect_chance(self, source, target, base_chance):
        """Calculate if an effect should be applied based on source luck vs target luck"""
        if not self.config["luck_effects"]:
            return base_chance
            
        # Adjust effect chance based on luck difference
        luck_diff = float(source.luck - target.luck) / 100
        modified_chance = base_chance * (1 + luck_diff)
        
        # Keep within reasonable bounds
        return max(0.05, min(0.95, modified_chance))
    
    def get_effect_duration(self, base_duration, luck):
        """Calculate effect duration based on luck"""
        if not self.config["luck_effects"]:
            return base_duration
            
        # Luck affects duration (higher luck = longer effects)
        luck_modifier = (float(luck) - 50) / 100
        return max(1, base_duration + int(luck_modifier * 2))
    
    def get_combatant_status_text(self, combatant):
        """Get text showing active status effects for a combatant"""
        status_text = combatant.get_status_effects_display()
        if status_text:
            return f"Status: {status_text}"
        return ""
    
    def get_chance_to_apply_effect(self, effect_type, source=None, target=None, base_chance=0.25):
        """Determine if an effect should be applied based on chance"""
        # Check if effects are enabled
        if not self.config.get("status_effects", True):
            return False
            
        # Get modified chance based on luck
        chance = base_chance
        if source and target:
            chance = self.get_effect_chance(source, target, base_chance)
            
        # Roll for effect
        return random.random() < chance
    
    # ----- Battle Replay System Methods -----
    
    def get_participants(self):
        """Get list of participant user IDs for replay storage"""
        participants = []
        for team in self.teams:
            for combatant in team.combatants:
                # Check if combatant.user is a Discord User object with an ID
                if hasattr(combatant, 'user') and hasattr(combatant.user, 'id'):
                    participants.append(combatant.user.id)
                # Also check for direct user_id attribute (backup)
                elif hasattr(combatant, 'user_id') and combatant.user_id:
                    participants.append(combatant.user_id)
        return participants
    
    def serialize_battle_data(self):
        """Serialize battle data for storage"""
        return {
            'battle_id': self.battle_id,
            'battle_type': self.battle_type,
            'participants': self.get_participants(),
            'start_time': self.start_time.isoformat() if self.start_time else None,
            'config': self.config,
            'teams_data': [],
            'action_number': self.action_number,
            'finished': self.finished,
            'winner': self.winner
        }
    
    def serialize_battle_log(self):
        """Serialize battle log for storage"""
        return list(self.log)
    
    async def save_battle_to_database(self):
        """Save battle data to database for replay"""
        try:
            # Initialize the battle_replays table if it doesn't exist
            await self.initialize_replay_table()
            
            battle_data = await self.serialize_enhanced_battle_data()
            battle_log = self.serialize_battle_log()
            participants = self.get_participants()
            
            async with self.bot.pool.acquire() as conn:
                # Check if this battle already exists (upsert logic)
                existing = await conn.fetchrow(
                    "SELECT battle_id FROM battle_replays WHERE battle_id = $1",
                    self.battle_id
                )
                
                if existing:
                    # Update existing record
                    await conn.execute(
                        """
                        UPDATE battle_replays SET 
                            participants = $2, battle_data = $3, battle_log = $4
                        WHERE battle_id = $1
                        """,
                        self.battle_id,
                        json.dumps(participants, cls=DecimalEncoder),
                        json.dumps(battle_data, cls=DecimalEncoder),
                        json.dumps(battle_log, cls=DecimalEncoder)
                    )
                else:
                    # Insert new record
                    await conn.execute(
                        """
                        INSERT INTO battle_replays (
                            battle_id, battle_type, participants, battle_data, battle_log, created_at
                        ) VALUES ($1, $2, $3, $4, $5, $6)
                        """,
                        self.battle_id,
                        self.battle_type,
                        json.dumps(participants, cls=DecimalEncoder),
                        json.dumps(battle_data, cls=DecimalEncoder),
                        json.dumps(battle_log, cls=DecimalEncoder),
                        datetime.datetime.utcnow()
                    )
                
        except Exception as e:
            # Don't let replay saving break the battle
            print(f"Error saving battle replay {self.battle_id}: {e}")
            import traceback
            traceback.print_exc()
    
    async def initialize_replay_table(self):
        """Initialize the battle_replays table if it doesn't exist"""
        try:
            async with self.bot.pool.acquire() as conn:
                await conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS battle_replays (
                        battle_id VARCHAR(36) PRIMARY KEY,
                        battle_type VARCHAR(50) NOT NULL,
                        participants JSONB NOT NULL,
                        battle_data JSONB NOT NULL,
                        battle_log JSONB NOT NULL,
                        created_at TIMESTAMP NOT NULL,
                        CONSTRAINT unique_battle_id UNIQUE (battle_id)
                    )
                    """
                )
                
                # Create indexes for better performance
                await conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_battle_replays_type ON battle_replays (battle_type)"
                )
                await conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_battle_replays_created_at ON battle_replays (created_at)"
                )
        except Exception as e:
            print(f"Error initializing battle replay table: {e}")
    
    @staticmethod
    async def get_battle_replay(bot, battle_id):
        """Retrieve battle replay data by ID"""
        try:
            async with bot.pool.acquire() as conn:
                row = await conn.fetchrow(
                    "SELECT * FROM battle_replays WHERE battle_id = $1",
                    battle_id
                )
                
                if row:
                    return {
                        'battle_id': row['battle_id'],
                        'battle_type': row['battle_type'],
                        'participants': json.loads(row['participants']),
                        'battle_data': json.loads(row['battle_data']),
                        'battle_log': json.loads(row['battle_log']),
                        'created_at': row['created_at']
                    }
                return None
        except Exception as e:
            print(f"Error retrieving battle replay {battle_id}: {e}")
            return None
    
    # ----- Enhanced Live Replay System Methods -----
    
    async def capture_turn_state(self, action_message):
        """Capture detailed battle state for live replay"""
        try:
            # Create a snapshot of current battle state
            state = {
                'action_number': self.action_number,
                'action_message': action_message,
                'timestamp': datetime.datetime.utcnow().isoformat(),
                'teams': []
            }
            

            
            # Capture detailed state for each team and combatant
            for team_idx, team in enumerate(self.teams):
                team_state = {
                    'team_index': team_idx,
                    'combatants': []
                }
                
                for combatant in team.combatants:
                    # Get user ID properly
                    user_id = None
                    if hasattr(combatant, 'user') and hasattr(combatant.user, 'id'):
                        user_id = combatant.user.id
                    elif hasattr(combatant, 'user_id'):
                        user_id = combatant.user_id
                    
                    # Get correct name and display name for pets vs players vs dragons
                    if getattr(combatant, 'is_pet', False):
                        # For pets, use the pet's actual name
                        actual_name = combatant.name
                        display_name = combatant.name
                        pet_name = combatant.name  # This is the actual pet name
                    elif hasattr(combatant, 'user') and hasattr(combatant.user, 'display_name'):
                        # For players with Discord User objects
                        actual_name = combatant.user.display_name
                        display_name = getattr(combatant, 'display_name', actual_name)
                        pet_name = None
                    else:
                        # For dragons or other combatants without proper user objects
                        actual_name = getattr(combatant, 'name', str(combatant.user) if hasattr(combatant, 'user') else 'Unknown')
                        display_name = getattr(combatant, 'display_name', actual_name)
                        pet_name = None
                    
                    # Get element emoji for this combatant
                    element_emoji = "❓"
                    if hasattr(combatant, 'element') and combatant.element:
                        # Get element emoji mapping from Battles cog
                        if hasattr(self.ctx.bot.cogs["Battles"], "emoji_to_element"):
                            emoji_to_element = self.ctx.bot.cogs["Battles"].emoji_to_element
                            element_to_emoji = {v: k for k, v in emoji_to_element.items()}
                            element_emoji = element_to_emoji.get(combatant.element, "❓")
                    
                    combatant_state = {
                        'name': actual_name,
                        'display_name': display_name,
                        'pet_name': pet_name,  # Include pet_name for compatibility
                        'current_hp': float(combatant.hp),
                        'max_hp': float(combatant.max_hp),
                        'shield': float(Decimal(str(getattr(combatant, "shield", 0) or 0))),
                        'hp_percentage': float(combatant.hp) / float(combatant.max_hp) if combatant.max_hp > 0 else 0,
                        'element': getattr(combatant, 'element', 'none'),  # Store element as-is (capitalized)
                        'element_emoji': element_emoji,  # Store the actual emoji
                        'is_alive': combatant.is_alive(),
                        'is_pet': getattr(combatant, 'is_pet', False),
                        'damage_reflection': getattr(combatant, 'damage_reflection', 0),
                        'user_id': user_id
                    }
                    
                    # Capture status effects if available
                    if hasattr(combatant, 'status_effects'):
                        combatant_state['status_effects'] = []
                        for effect in combatant.status_effects:
                            effect_state = {
                                'name': getattr(effect, 'name', 'Unknown Effect'),
                                'duration': getattr(effect, 'duration', 0),
                                'stacks': getattr(effect, 'stacks', 1)
                            }
                            combatant_state['status_effects'].append(effect_state)
                    else:
                        combatant_state['status_effects'] = []
                    
                    team_state['combatants'].append(combatant_state)
                
                state['teams'].append(team_state)
            
            # Add battle-specific state information
            state['battle_info'] = {
                'started': self.started,
                'finished': self.finished,
                'winner': self.winner,
                'battle_type': self.battle_type,
                'config': self.config.copy()
            }
            
            # Add special state for specific battle types
            if hasattr(self, 'current_turn'):
                state['battle_info']['current_turn'] = self.current_turn
            if hasattr(self, 'level'):
                state['battle_info']['level'] = self.level
            if hasattr(self, 'current_opponent_index'):
                state['battle_info']['current_opponent_index'] = self.current_opponent_index
            
            self.turn_states.append(state)
            
            # Store initial state if this is the first capture
            if self.initial_state is None:
                self.initial_state = state.copy()
                
        except Exception as e:
            # Don't let state capture break battles
            print(f"Error capturing turn state for battle {self.battle_id}: {e}")
            import traceback
            traceback.print_exc()
    
    async def serialize_enhanced_battle_data(self):
        """Serialize enhanced battle data including turn states"""
        base_data = self.serialize_battle_data()
        base_data['turn_states'] = self.turn_states
        base_data['initial_state'] = self.initial_state
        base_data['has_enhanced_replay'] = True
        

        
        return base_data

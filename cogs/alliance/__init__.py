"""
The IdleRPG Discord Bot
Copyright (C) 2018-2021 Diniboy and Gelbpunkt

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
import math

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import asyncpg
import discord

from classes.errors import NoChoice
from discord.enums import ButtonStyle
from discord.ext import commands
from discord.ui.button import Button

from classes.bot import Bot
from classes.context import Context
from classes.converters import MemberWithCharacter
from cogs.battles.core.combatant import Combatant
from cogs.battles.core.team import Team
from cogs.shard_communication import alliance_on_cooldown as alliance_cooldown
from utils import misc as rpgtools
from utils.checks import (
    guild_has_money,
    has_char,
    has_guild,
    is_alliance_leader,
    is_guild_leader,
    owns_city,
    owns_no_city,
)
from utils.i18n import _, locale_doc
from utils.joins import JoinView
from utils.paginator import Choose


CITY_GUARD_LIMIT = 3
CITY_CONQUEST_OVERFLOW_LOSS_PERCENT = 25
CITY_ATTACK_LOCK_KEY = "citywars:lock_until"
CITY_WAR_ATTACKER_LIMIT = 3
CITY_WAR_PET_BUDGET_MULTIPLIER = Decimal("1.10")
CITY_WAR_DEFENSE_BASE_SLOTS = ("wall", "weapon", "utility")
CITY_WAR_DEFENSE_SLOT_LAYOUTS = {
    1: ("wall_1", "weapon_1", "utility_1"),
    2: ("wall_1", "weapon_1", "utility_1"),
    3: ("wall_1", "weapon_1", "utility_1", "weapon_2"),
    4: ("wall_1", "weapon_1", "utility_1", "weapon_2", "utility_2"),
}
CITY_WAR_DEFENSES = {
    "cannons": {"hp": 1000, "def": 120, "cost": 200000, "slot": "weapon", "priority": 2},
    "archers": {"hp": 2000, "def": 100, "cost": 100000, "slot": "weapon", "priority": 1},
    "outer wall": {"hp": 80000, "def": 0, "cost": 500000, "slot": "wall", "priority": 2},
    "inner wall": {"hp": 40000, "def": 0, "cost": 200000, "slot": "wall", "priority": 1},
    "moat": {"hp": 20000, "def": 50, "cost": 150000, "slot": "utility", "priority": 1},
    "tower": {"hp": 5000, "def": 100, "cost": 200000, "slot": "weapon", "priority": 3},
    "ballista": {"hp": 1000, "def": 60, "cost": 100000, "slot": "weapon", "priority": 0},
}
CITY_WAR_DEFENSE_SLOT_LABELS = {
    "wall": "Wall",
    "weapon": "Weapon",
    "utility": "Utility",
}
CITY_WAR_SLOT_NUMERALS = {
    1: "I",
    2: "II",
    3: "III",
}


class CityWarUserProxy:
    def __init__(self, user_id: int, display_name: str):
        self.id = int(user_id)
        self.display_name = display_name

    def __str__(self) -> str:
        return self.display_name


class Alliance(commands.Cog):
    def __init__(self, bot: Bot):
        self.bot = bot
        self.city_configs = {name.title(): i for name, i in bot.config.cities.items()}

    def _build_city_help_overview_embed(self, ctx: Context) -> discord.Embed:
        embed = discord.Embed(
            title=_("City War Help"),
            colour=self.bot.config.game.primary_colour,
            description=_(
                "Use `{prefix}alliance cityhelp attack` for attacker guidance and `{prefix}alliance cityhelp defend` for defender setup."
            ).format(prefix=ctx.clean_prefix),
        )
        embed.add_field(
            name=_("Attack Commands"),
            value=_(
                "`{prefix}alliance attack <city>`\n"
                "`{prefix}alliance occupy <city>`\n"
                "`{prefix}alliance cityhelp attack`"
            ).format(prefix=ctx.clean_prefix),
            inline=False,
        )
        embed.add_field(
            name=_("Defense Commands"),
            value=_(
                "`{prefix}alliance defenses`\n"
                "`{prefix}alliance build defense`\n"
                "`{prefix}alliance guards`\n"
                "`{prefix}alliance guards pet`\n"
                "`{prefix}alliance cityhelp defend`"
            ).format(prefix=ctx.clean_prefix),
            inline=False,
        )
        embed.add_field(
            name=_("Core Rules"),
            value=_(
                "City wars are guild-based. Attackers bring a live `3`-person frontline and defenders use preset fortifications, guards, and one city pet."
            ),
            inline=False,
        )
        embed.add_field(
            name=_("Win Condition"),
            value=_(
                "A city can only be occupied after all active fortifications, city guards, and the stationed city pet are gone."
            ),
            inline=False,
        )
        embed.add_field(
            name=_("Vault Stakes"),
            value=_(
                "Owning a city increases guild vault cap by city tier. Losing the city removes `25%` of vault gold stored above the guild's base cap."
            ),
            inline=False,
        )
        return embed

    def _build_city_help_attack_embed(self, ctx: Context) -> discord.Embed:
        embed = discord.Embed(
            title=_("City War Help: Attacking"),
            colour=self.bot.config.game.primary_colour,
            description=_("How to launch and finish a city attack."),
        )
        embed.add_field(
            name=_("Start"),
            value=_(
                "`{prefix}alliance attack <city>`\n"
                "Only the alliance leader can launch it.\n"
                "You cannot attack your own city.\n"
                "The city must not already be under attack or on cooldown."
            ).format(prefix=ctx.clean_prefix),
            inline=False,
        )
        embed.add_field(
            name=_("Rally Phase"),
            value=_(
                "A join button stays open for `10 minutes`.\n"
                "You need at least `3` eligible members from the same guild.\n"
                "Stationed city guards cannot join attacks.\n"
                "After rally, the leader chooses the `3` frontline attackers."
            ),
            inline=False,
        )
        embed.add_field(
            name=_("Pets"),
            value=_(
                "The attack can bring `1` pet.\n"
                "The pet owner must be one of the chosen frontline attackers.\n"
                "The pet does not need to be equipped.\n"
                "It must not be in daycare and must be `young` or `adult`."
            ),
            inline=False,
        )
        embed.add_field(
            name=_("Battle"),
            value=_(
                "City war uses city-war scaled stats, not raw stats.\n"
                "Active fortifications are fought first.\n"
                "After that, guards and the stationed city pet fight.\n"
                "The attack has a `15 minute` limit."
            ),
            inline=False,
        )
        embed.add_field(
            name=_("After Winning"),
            value=_(
                "Use `{prefix}alliance occupy <city>` immediately after clearing the city.\n"
                "If you wait too long, another guild may take it first."
            ).format(prefix=ctx.clean_prefix),
            inline=False,
        )
        return embed

    def _build_city_help_defend_embed(self, ctx: Context) -> discord.Embed:
        embed = discord.Embed(
            title=_("City War Help: Defending"),
            colour=self.bot.config.game.primary_colour,
            description=_("How to prepare a city so it can defend itself while your guild is offline."),
        )
        embed.add_field(
            name=_("Defense Slots"),
            value=_(
                "Tier `1-2` cities have `3` active defense slots: Wall, Weapon, Utility.\n"
                "Tier `3` cities gain `1` extra Weapon slot.\n"
                "Tier `4` cities gain `1` extra Weapon slot and `1` extra Utility slot.\n"
                "If an `outer wall` is active, one utility slot may instead hold an `inner wall`.\n"
                "Use `{prefix}alliance build defense` for the guided selector and view them with `{prefix}alliance defenses`."
            ).format(prefix=ctx.clean_prefix),
            inline=False,
        )
        embed.add_field(
            name=_("City Guards"),
            value=_(
                "Cities can station up to `3` city guards.\n"
                "`{prefix}alliance guards`\n"
                "`{prefix}alliance guards add <member>`\n"
                "`{prefix}alliance guards remove <member>`"
            ).format(prefix=ctx.clean_prefix),
            inline=False,
        )
        embed.add_field(
            name=_("Guard Duty Restrictions"),
            value=_(
                "Stationed guards cannot:\n"
                "join city attacks\n"
                "start guild adventures\n"
                "join guild adventures"
            ),
            inline=False,
        )
        embed.add_field(
            name=_("City Pet"),
            value=_(
                "Each city can station `1` guard pet.\n"
                "Use `{prefix}alliance guards pet set <member> <pet>`.\n"
                "The owner must be a currently assigned city guard.\n"
                "The pet does not need to be equipped but must be `young` or `adult` and not in daycare."
            ).format(prefix=ctx.clean_prefix),
            inline=False,
        )
        embed.add_field(
            name=_("Risk and Reward"),
            value=_(
                "City ownership increases the guild vault cap by tier.\n"
                "If the city falls, the guild loses `25%` of stored gold above its normal base vault cap."
            ),
            inline=False,
        )
        return embed

    async def _get_city_attack_lock(self) -> int | None:
        raw_value = await self.bot.redis.execute_command("GET", CITY_ATTACK_LOCK_KEY)
        if not raw_value:
            return None

        try:
            lock_until = int(raw_value.decode() if isinstance(raw_value, bytes) else raw_value)
        except (TypeError, ValueError):
            await self.bot.redis.execute_command("DEL", CITY_ATTACK_LOCK_KEY)
            return None

        if lock_until <= int(datetime.now(timezone.utc).timestamp()):
            await self.bot.redis.execute_command("DEL", CITY_ATTACK_LOCK_KEY)
            return None

        return lock_until

    def _format_city_attack_lock(self, lock_until: int) -> str:
        unlock_time = datetime.fromtimestamp(lock_until, tz=timezone.utc)
        return _(
            "City attacks are currently disabled until {unlock_time}."
        ).format(unlock_time=discord.utils.format_dt(unlock_time, style="F"))

    def _get_city_war_defense_meta(self, defense_name: str) -> dict | None:
        if not defense_name:
            return None
        return CITY_WAR_DEFENSES.get(str(defense_name).lower())

    def _get_city_war_defense_slot(self, defense_name: str) -> str | None:
        meta = self._get_city_war_defense_meta(defense_name)
        return None if meta is None else meta["slot"]

    def _get_city_tier(self, city_name: str | None) -> int:
        if not city_name:
            return 1

        city_config = self.city_configs.get(str(city_name).title())
        if not city_config:
            return 1

        try:
            tier = int(city_config.get("tier", 1))
        except (TypeError, ValueError):
            tier = 1

        return max(1, min(tier, max(CITY_WAR_DEFENSE_SLOT_LAYOUTS)))

    def _get_city_war_slots_for_city(self, city_name: str | None) -> tuple[str, ...]:
        return CITY_WAR_DEFENSE_SLOT_LAYOUTS[self._get_city_tier(city_name)]

    def _get_city_war_slot_category(self, slot_id: str | None) -> str | None:
        if not slot_id:
            return None
        return str(slot_id).split("_", 1)[0]

    def _get_city_war_slot_number(self, slot_id: str | None) -> int:
        if not slot_id or "_" not in str(slot_id):
            return 1
        try:
            return max(1, int(str(slot_id).rsplit("_", 1)[1]))
        except (TypeError, ValueError):
            return 1

    def _get_city_war_slot_label(self, slot_id: str | None) -> str:
        category = self._get_city_war_slot_category(slot_id)
        base_label = CITY_WAR_DEFENSE_SLOT_LABELS.get(category, _("Defense"))
        slot_number = self._get_city_war_slot_number(slot_id)
        if slot_number <= 1:
            return base_label
        numeral = CITY_WAR_SLOT_NUMERALS.get(slot_number, str(slot_number))
        return f"{base_label} {numeral}"

    def _get_city_war_defense_instance_slot_id(self, defense: dict) -> str | None:
        return (
            defense.get("resolved_slot_id")
            or defense.get("slot_id")
            or self._get_city_war_defense_slot(defense["name"])
        )

    def _get_city_war_open_slots(
        self, city_name: str, active_defenses: list[dict]
    ) -> list[str]:
        occupied_slots = {
            self._get_city_war_defense_instance_slot_id(defense)
            for defense in active_defenses
        }
        return [
            slot_id
            for slot_id in self._get_city_war_slots_for_city(city_name)
            if slot_id not in occupied_slots
        ]

    def _get_city_war_slot_capacity_text(self, city_name: str) -> str:
        slot_labels = [
            self._get_city_war_slot_label(slot_id)
            for slot_id in self._get_city_war_slots_for_city(city_name)
        ]
        return ", ".join(slot_labels)

    def _can_build_inner_wall_in_utility_slot(
        self, slot_id: str, active_defenses: list[dict]
    ) -> bool:
        if self._get_city_war_slot_category(slot_id) != "utility":
            return False

        if not any(
            str(defense["name"]).lower() == "outer wall" for defense in active_defenses
        ):
            return False

        return not any(
            str(defense["name"]).lower() == "inner wall"
            and self._get_city_war_slot_category(
                self._get_city_war_defense_instance_slot_id(defense)
            )
            == "utility"
            for defense in active_defenses
        )

    def _is_city_war_defense_allowed_in_slot(
        self,
        city_name: str,
        slot_id: str,
        defense_name: str,
        active_defenses: list[dict] | None = None,
    ) -> bool:
        active_defenses = active_defenses or []
        meta = self._get_city_war_defense_meta(defense_name)
        if meta is None:
            return False

        slot_category = self._get_city_war_slot_category(slot_id)
        if slot_category is None:
            return False

        if slot_id not in self._get_city_war_slots_for_city(city_name):
            return False

        if meta["slot"] == slot_category:
            return True

        return (
            str(defense_name).lower() == "inner wall"
            and self._can_build_inner_wall_in_utility_slot(slot_id, active_defenses)
        )

    def _get_city_war_defense_effect_text(self, defense_name: str) -> str:
        normalized_name = str(defense_name).lower()
        if normalized_name == "outer wall":
            return _("Reduces attacker damage to fortifications by 20% while it stands.")
        if normalized_name == "inner wall":
            return _(
                "Reduces attacker damage to fortifications by 10% while it stands. If an outer wall is active, one utility slot may instead hold an inner wall."
            )
        if normalized_name == "cannons":
            return _("Highest raw fortification retaliation, but fragile.")
        if normalized_name == "archers":
            return _("Cheaper weapon defense with more HP than most weapon options.")
        if normalized_name == "tower":
            return _("Balanced weapon defense with solid HP and retaliation.")
        if normalized_name == "ballista":
            return _("Cheap weapon defense with lower retaliation.")
        if normalized_name == "moat":
            return _("Utility fortification that adds extra siege HP and retaliation.")
        return _("Provides fortification HP and retaliation during the siege phase.")

    def _describe_city_war_defense(self, defense_name: str) -> str:
        meta = self._get_city_war_defense_meta(defense_name) or {}
        return _(
            "{hp} HP, {defense} retaliation, costs ${cost}. {effect}"
        ).format(
            hp=f"{int(meta.get('hp', 0)):,}",
            defense=int(meta.get("def", 0)),
            cost=f"{int(meta.get('cost', 0)):,}",
            effect=self._get_city_war_defense_effect_text(defense_name),
        )

    def _get_city_war_defenses_for_slot(
        self, city_name: str, slot_id: str, active_defenses: list[dict] | None = None
    ) -> list[str]:
        return [
            defense_name
            for defense_name, meta in CITY_WAR_DEFENSES.items()
            if self._is_city_war_defense_allowed_in_slot(
                city_name,
                slot_id,
                defense_name,
                active_defenses=active_defenses,
            )
        ]

    def _format_city_war_occupied_slots(
        self, slot_ids: list[str], occupied_slots: dict[str, dict]
    ) -> str:
        return ", ".join(
            _("{slot}: {defense}").format(
                slot=self._get_city_war_slot_label(slot_id),
                defense=occupied_slots[slot_id]["name"].title(),
            )
            for slot_id in slot_ids
            if slot_id in occupied_slots
        )

    async def _choose_city_war_slot_for_build(
        self,
        ctx: Context,
        city_name: str,
        open_slots: list[str],
        active_defenses: list[dict],
    ) -> str | None:
        if not open_slots:
            return None
        if len(open_slots) == 1:
            return open_slots[0]

        slot_entries = [
            _("{slot}: {choices}").format(
                slot=self._get_city_war_slot_label(slot_id),
                choices=", ".join(
                    defense_name.title()
                    for defense_name in self._get_city_war_defenses_for_slot(
                        city_name,
                        slot_id,
                        active_defenses,
                    )
                ),
            )
            for slot_id in open_slots
        ]
        try:
            selected_index = await Choose(
                slot_entries,
                title=_("Choose a Defense Slot"),
                choices=[self._get_city_war_slot_label(slot_id) for slot_id in open_slots],
                footer=_("City: {city}").format(city=city_name),
                timeout=60,
                return_index=True,
            ).paginate(ctx)
        except NoChoice:
            return None
        return open_slots[selected_index]

    async def _choose_city_war_defense_for_slot(
        self,
        ctx: Context,
        city_name: str,
        slot_id: str,
        active_defenses: list[dict],
    ) -> str | None:
        defense_names = self._get_city_war_defenses_for_slot(
            city_name,
            slot_id,
            active_defenses,
        )
        if not defense_names:
            return None
        if len(defense_names) == 1:
            return defense_names[0]

        defense_entries = [
            _("{name}: {details}").format(
                name=defense_name.title(),
                details=self._describe_city_war_defense(defense_name),
            )
            for defense_name in defense_names
        ]
        try:
            selected_index = await Choose(
                defense_entries,
                title=_("Choose a Defense for {slot}").format(
                    slot=self._get_city_war_slot_label(slot_id)
                ),
                choices=[defense_name.title() for defense_name in defense_names],
                footer=_("City: {city}").format(city=city_name),
                timeout=60,
                return_index=True,
            ).paginate(ctx)
        except NoChoice:
            return None
        return defense_names[selected_index]

    def _get_city_war_defense_choice_key(self, defense: dict) -> tuple[int, int, int]:
        meta = self._get_city_war_defense_meta(defense["name"]) or {}
        return (
            int(meta.get("priority", -1)),
            int(defense.get("hp", 0)),
            -int(defense.get("id", 0)),
        )

    def _partition_city_defenses(
        self, defenses: list[dict], city_name: str
    ) -> tuple[list[dict], list[dict]]:
        valid_slots = self._get_city_war_slots_for_city(city_name)
        active_by_slot: dict[str, dict] = {}
        inactive: list[dict] = []
        legacy_by_category: dict[str, list[dict]] = {
            category: [] for category in CITY_WAR_DEFENSE_BASE_SLOTS
        }

        for defense in defenses:
            resolved_defense = dict(defense)
            slot_id = resolved_defense.get("slot_id")
            if slot_id in valid_slots:
                resolved_defense["resolved_slot_id"] = slot_id
                current = active_by_slot.get(slot_id)
                if current is None or (
                    self._get_city_war_defense_choice_key(resolved_defense)
                    > self._get_city_war_defense_choice_key(current)
                ):
                    if current is not None:
                        inactive.append(current)
                    active_by_slot[slot_id] = resolved_defense
                else:
                    inactive.append(resolved_defense)
                continue

            category = self._get_city_war_defense_slot(resolved_defense["name"])
            if category is None:
                inactive.append(resolved_defense)
                continue
            legacy_by_category.setdefault(category, []).append(resolved_defense)

        for category, category_defenses in legacy_by_category.items():
            available_slots = [
                slot_id
                for slot_id in valid_slots
                if self._get_city_war_slot_category(slot_id) == category
                and slot_id not in active_by_slot
            ]
            ordered_defenses = sorted(
                category_defenses,
                key=self._get_city_war_defense_choice_key,
                reverse=True,
            )
            for slot_id, defense in zip(available_slots, ordered_defenses):
                resolved_defense = dict(defense)
                resolved_defense["resolved_slot_id"] = slot_id
                active_by_slot[slot_id] = resolved_defense
            inactive.extend(ordered_defenses[len(available_slots):])

        active = [
            active_by_slot[slot_id]
            for slot_id in valid_slots
            if slot_id in active_by_slot
        ]
        return active, inactive

    async def _load_city_defenses(self, conn, city: str) -> tuple[list[dict], list[dict]]:
        await self.bot._ensure_city_war_tables()
        defenses = [
            dict(row)
            for row in await conn.fetch(
                'SELECT * FROM defenses WHERE "city"=$1 ORDER BY "id" ASC;',
                city,
            )
        ]
        return self._partition_city_defenses(defenses, city)

    def _scale_city_war_stat(self, raw_value, *, base: int, factor: int) -> int:
        value = max(0.0, float(raw_value or 0))
        return max(1, int(round(base + (factor * math.sqrt(value)))))

    def _apply_city_war_scaling(self, combatant: Combatant) -> Combatant:
        current_hp = float(getattr(combatant, "hp", 0) or 0)
        max_hp = float(getattr(combatant, "max_hp", current_hp) or current_hp or 1)
        hp_ratio = 1.0 if max_hp <= 0 else max(0.0, min(1.0, current_hp / max_hp))

        scaled_max_hp = self._scale_city_war_stat(
            getattr(combatant, "max_hp", current_hp),
            base=2500,
            factor=40,
        )
        scaled_damage = self._scale_city_war_stat(
            getattr(combatant, "damage", 0),
            base=150,
            factor=18,
        )
        scaled_armor = self._scale_city_war_stat(
            getattr(combatant, "armor", 0),
            base=100,
            factor=15,
        )

        scaled_current_hp = max(
            0,
            int(round(scaled_max_hp * hp_ratio)),
        )
        if getattr(combatant, "is_alive", lambda: True)():
            scaled_current_hp = max(1, scaled_current_hp)

        combatant.max_hp = Decimal(str(scaled_max_hp))
        combatant.hp = Decimal(str(scaled_current_hp))
        combatant.damage = Decimal(str(scaled_damage))
        combatant.armor = Decimal(str(scaled_armor))
        combatant.city_war_scaled = True
        return combatant

    def _get_city_war_budget(self, combatant: Combatant) -> Decimal:
        return (
            (Decimal(str(getattr(combatant, "max_hp", 0) or 0)) / Decimal("5"))
            + Decimal(str(getattr(combatant, "damage", 0) or 0))
            + Decimal(str(getattr(combatant, "armor", 0) or 0))
        )

    def _cap_city_war_pet(self, pet_combatant: Combatant, owner_combatant: Combatant | None) -> Combatant:
        if not pet_combatant or not owner_combatant:
            return pet_combatant

        pet_budget = self._get_city_war_budget(pet_combatant)
        owner_budget = self._get_city_war_budget(owner_combatant)
        max_budget = owner_budget * CITY_WAR_PET_BUDGET_MULTIPLIER

        if pet_budget <= 0 or pet_budget <= max_budget:
            return pet_combatant

        scale = max_budget / pet_budget
        scaled_max_hp = max(
            1,
            int(
                round(
                    float(Decimal(str(getattr(pet_combatant, "max_hp", 1) or 1)) * scale)
                )
            ),
        )
        scaled_damage = max(
            1,
            int(
                round(
                    float(Decimal(str(getattr(pet_combatant, "damage", 1) or 1)) * scale)
                )
            ),
        )
        scaled_armor = max(
            1,
            int(
                round(
                    float(Decimal(str(getattr(pet_combatant, "armor", 1) or 1)) * scale)
                )
            ),
        )
        current_hp = float(getattr(pet_combatant, "hp", 0) or 0)
        max_hp = float(getattr(pet_combatant, "max_hp", current_hp) or current_hp or 1)
        hp_ratio = 1.0 if max_hp <= 0 else max(0.0, min(1.0, current_hp / max_hp))
        scaled_current_hp = max(1, int(round(scaled_max_hp * hp_ratio)))

        pet_combatant.max_hp = Decimal(str(scaled_max_hp))
        pet_combatant.hp = Decimal(str(scaled_current_hp))
        pet_combatant.damage = Decimal(str(scaled_damage))
        pet_combatant.armor = Decimal(str(scaled_armor))
        pet_combatant.city_war_pet_capped = True
        return pet_combatant

    def _sort_city_attackers(self, ctx: Context, attackers: list[discord.abc.User]) -> list[discord.abc.User]:
        return sorted(
            attackers,
            key=lambda member: (
                0 if member.id == ctx.author.id else 1,
                member.display_name.casefold(),
                member.id,
            ),
        )

    async def _select_city_attackers(self, ctx: Context, attackers: list[discord.abc.User]) -> list[discord.abc.User] | None:
        ordered_attackers = self._sort_city_attackers(ctx, attackers)
        if len(ordered_attackers) > 25:
            ordered_attackers = ordered_attackers[:25]
            await ctx.send(
                _("Only the first **25** eligible joined attackers can be considered for frontline selection.")
            )
        if len(ordered_attackers) <= CITY_WAR_ATTACKER_LIMIT:
            return ordered_attackers

        selected: list[discord.abc.User] = []
        remaining = ordered_attackers.copy()
        try:
            for slot_index in range(CITY_WAR_ATTACKER_LIMIT):
                selected_index = await Choose(
                    entries=[
                        _("{member}").format(member=member.display_name)
                        for member in remaining
                    ],
                    title=_("Choose frontline attacker #{slot}").format(
                        slot=slot_index + 1
                    ),
                    footer=_("Pick the {limit} frontline guild members for this city war.").format(
                        limit=CITY_WAR_ATTACKER_LIMIT
                    ),
                    return_index=True,
                    timeout=45,
                ).paginate(ctx)
                selected.append(remaining.pop(int(selected_index)))
        except NoChoice:
            return None

        return selected

    async def _get_available_city_war_pets(self, conn, user_id: int):
        return await conn.fetch(
            """
            SELECT *
            FROM monster_pets
            WHERE user_id = $1
              AND daycare_boarding_id IS NULL
              AND growth_stage IN ('young', 'adult')
            ORDER BY equipped DESC, id ASC;
            """,
            user_id,
        )

    async def _select_attack_pet(self, ctx: Context, attackers: list, conn):
        eligible = []
        for attacker in attackers:
            pets = await self._get_available_city_war_pets(conn, attacker.id)
            if pets:
                eligible.append((attacker, pets))

        if not eligible:
            return None
        eligible = eligible[:24]

        try:
            if len(eligible) == 1:
                owner_index = 0
            else:
                owner_index = await Choose(
                    entries=[
                        _("{member} ({count} eligible pets)").format(
                            member=member.display_name,
                            count=len(pets),
                        )
                        for member, pets in eligible
                    ]
                    + [_("No attack pet")],
                    title=_("Choose the pet owner"),
                    footer=_("Only joined attackers can provide a city-war pet."),
                    return_index=True,
                    timeout=45,
                ).paginate(ctx)
                if owner_index == len(eligible):
                    return None

            owner, pets = eligible[int(owner_index)]
            pets = list(pets)[:24]
            pet_index = await Choose(
                entries=[
                    _("{name} (ID {pet_id}) • {element} • {stage}").format(
                        name=pet["name"],
                        pet_id=pet["id"],
                        element=pet["element"],
                        stage=pet["growth_stage"].capitalize(),
                    )
                    for pet in pets
                ]
                + [_("No attack pet")],
                title=_("Choose the attack pet"),
                footer=_("The pet does not need to be equipped."),
                return_index=True,
                timeout=45,
            ).paginate(ctx)
            if pet_index == len(pets):
                return None

            return {"owner": owner, "pet": pets[int(pet_index)]}
        except NoChoice:
            await ctx.send(_("No attack pet was selected in time. Proceeding without one."))
            return None

    async def _build_city_structure_combatants(self, defenses: list[dict]) -> list[Combatant]:
        structures = []
        for defense in defenses:
            defense_meta = self._get_city_war_defense_meta(defense["name"]) or {}
            structure = Combatant(
                user=defense["name"],
                hp=defense["hp"],
                max_hp=defense["hp"],
                damage=max(1, int(defense["defense"])),
                armor=0,
                element="Earth",
                luck=100,
                name=defense["name"].title(),
                city_role="structure",
                city_slot=defense_meta.get("slot"),
                city_structure_name=str(defense["name"]).lower(),
                structure_id=defense["id"],
            )
            structures.append(structure)
        return structures

    async def _build_city_guard_combatants(self, ctx: Context, city: str, conn) -> list:
        battles_cog = self.bot.get_cog("Battles")
        if not battles_cog:
            return []

        guard_combatants = []
        for guard in await self.bot.get_city_guards(city, conn=conn):
            guard_name = await rpgtools.lookup(self.bot, guard["user_id"])
            guard_user = CityWarUserProxy(int(guard["user_id"]), guard_name)
            combatant = await battles_cog.battle_factory.create_player_combatant(
                ctx,
                guard_user,
                include_pet=False,
            )
            self._apply_city_war_scaling(combatant)
            combatant.name = guard_name
            combatant.city_role = "guard"
            combatant.city_guard_user_id = int(guard["user_id"])
            combatant.user_id = int(guard["user_id"])
            guard_combatants.append(combatant)

        return guard_combatants

    async def _build_city_guard_pet_combatant(
        self,
        ctx: Context,
        city: str,
        conn,
        owner_combatants: dict[int, Combatant] | None = None,
    ):
        battles_cog = self.bot.get_cog("Battles")
        if not battles_cog:
            return None

        assigned_pet = await self.bot.get_city_guard_pet(city, conn=conn)
        if not assigned_pet:
            return None

        owner_combatants = owner_combatants or {}
        owner_id = int(assigned_pet["user_id"])
        if owner_combatants and owner_id not in owner_combatants:
            await self.bot.clear_city_guard_pet(city=city, conn=conn)
            return None

        owner = CityWarUserProxy(
            owner_id,
            await rpgtools.lookup(self.bot, owner_id),
        )
        pet_combatant = await battles_cog.battle_factory.pet_ext.get_pet_combatant(
            ctx,
            owner,
            pet_id=int(assigned_pet["pet_id"]),
            conn=conn,
        )
        if not pet_combatant:
            await self.bot.clear_city_guard_pet(city=city, conn=conn)
            return None

        self._apply_city_war_scaling(pet_combatant)
        self._cap_city_war_pet(pet_combatant, owner_combatants.get(owner_id))
        pet_combatant.city_role = "guard_pet"
        pet_combatant.city_guard_pet_id = int(assigned_pet["pet_id"])
        pet_combatant.city_guard_pet_owner_id = owner_id
        pet_combatant.user_id = owner_id
        return pet_combatant

    async def _sync_city_war_battle_state(self, battle, conn) -> None:
        for combatant in battle.defender_team.combatants:
            city_role = getattr(combatant, "city_role", "")
            if city_role == "structure":
                structure_id = getattr(combatant, "structure_id", None)
                if not structure_id:
                    continue
                if combatant.is_alive():
                    await conn.execute(
                        'UPDATE defenses SET "hp"=$1 WHERE "id"=$2;',
                        int(max(0, round(float(combatant.hp)))),
                        int(structure_id),
                    )
                else:
                    await conn.execute(
                        'DELETE FROM defenses WHERE "id"=$1;',
                        int(structure_id),
                    )
            elif city_role == "guard" and not combatant.is_alive():
                await self.bot.clear_city_guards(
                    user_id=int(getattr(combatant, "city_guard_user_id")),
                    conn=conn,
                )
            elif city_role == "guard_pet" and not combatant.is_alive():
                await self.bot.clear_city_guard_pet(city=battle.city, conn=conn)

    async def _apply_conquest_vault_loss(
        self, defending_guild_id: int, conn
    ) -> tuple[int, str | None]:
        if defending_guild_id in (None, 1):
            return 0, None
        bank_caps = await self.bot.get_guild_bank_caps(defending_guild_id, conn=conn)
        if not bank_caps:
            return 0, None
        defending_guild = bank_caps["guild"]
        overflow_gold = max(
            0,
            int(defending_guild["money"]) - int(bank_caps["base_limit"]),
        )
        lost_gold = (overflow_gold * CITY_CONQUEST_OVERFLOW_LOSS_PERCENT) // 100
        if lost_gold > 0:
            await conn.execute(
                'UPDATE guild SET "money"="money"-$1 WHERE "id"=$2;',
                lost_gold,
                defending_guild_id,
            )
        return lost_gold, defending_guild["name"]

    @commands.command(name="cities", brief=_("Shows cities and owners."))
    async def show_cities(self, ctx: Context) -> None:
        city_rows = {}
        city_defense_summaries = {
            city_name: {
                "fortifications": 0,
                "fortification_hp": 0,
                "fortification_retaliation": 0,
                "guards": 0,
                "guard_pet": False,
            }
            for city_name in self.city_configs
        }
        db_warning = None

        try:
            async with self.bot.pool.acquire() as conn:
                city_rows = {
                    row["name"]: dict(row)
                    for row in await conn.fetch(
                        'SELECT c.*, g."name" AS "gname" FROM city c LEFT JOIN guild g ON c."owner"=g."id";'
                    )
                }
                for city_name in self.city_configs:
                    active_defenses, inactive_defenses = await self._load_city_defenses(
                        conn, city_name
                    )
                    guards = await self.bot.get_city_guards(city_name, conn=conn)
                    guard_pet = await self.bot.get_city_guard_pet(city_name, conn=conn)
                    city_defense_summaries[city_name] = {
                        "fortifications": len(active_defenses),
                        "fortification_hp": sum(
                            int(defense["hp"]) for defense in active_defenses
                        ),
                        "fortification_retaliation": sum(
                            int(defense["defense"]) for defense in active_defenses
                        ),
                        "guards": len(guards),
                        "guard_pet": bool(guard_pet),
                    }
        except asyncpg.PostgresError:
            self.bot.logger.exception("Failed to load cities command data from Postgres.")
            db_warning = _(
                "City ownership and defense data are temporarily unavailable."
            )
        except Exception as e:
            return await ctx.send(f"Error loading cities: {e}")

        em = discord.Embed(
            title=_("Cities"),
            colour=self.bot.config.game.primary_colour,
            description=db_warning,
        )
        for city_name, city_config in sorted(
            self.city_configs.items(),
            key=lambda item: -int(item[1]["tier"]),
        ):
            city = city_rows.get(city_name)
            owner_name = city.get("gname") if city else None
            if db_warning:
                owner_text = _("Owner data unavailable")
            elif city and city.get("owner") not in (None, 1) and owner_name:
                owner_text = _("Owned by {alliance}'s alliance").format(
                    alliance=owner_name
                )
            else:
                owner_text = _("Owned by the System Guild Alliance")
            if db_warning:
                defense_text = _("Defense data unavailable")
            else:
                defense_summary = city_defense_summaries.get(city_name, {})
                defense_text = _(
                    "Fortifications: {fortifications}/{slots} active ({hp} HP, {retaliation} retaliation)\n"
                    "Guards: {guards}\n"
                    "Guard Pet: {guard_pet}"
                ).format(
                    fortifications=defense_summary.get("fortifications", 0),
                    slots=len(self._get_city_war_slots_for_city(city_name)),
                    hp=f"{int(defense_summary.get('fortification_hp', 0)):,}",
                    retaliation=f"{int(defense_summary.get('fortification_retaliation', 0)):,}",
                    guards=defense_summary.get("guards", 0),
                    guard_pet=_("Yes")
                    if defense_summary.get("guard_pet")
                    else _("No"),
                )
            em.add_field(
                name=_("{name} (Tier {tier})").format(
                    name=city_name, tier=city_config["tier"]
                ),
                value=_(
                    "{owner_text}\nBuildings: {buildings}\n{defense_text}"
                ).format(
                    owner_text=owner_text,
                    buildings=", ".join(
                        [
                            i.title()
                            for i in ("thief", "raid", "trade", "adventure")
                            if city_config[i]
                        ]
                    ),
                    defense_text=defense_text,
                ),
                inline=False,
            )
        await ctx.send(embed=em)

    @has_char()
    @has_guild()
    @commands.group(
        invoke_without_command=True, brief=_("Interact with your alliance.")
    )
    @locale_doc
    async def alliance(self, ctx: Context) -> None:
        _(
            """Alliances are groups of guilds. Just like a guild requires at least one member, an alliance requires at least one guild and is considered a single-guild alliance.
            Alliances can occupy cities for passive bonuses given by the buildings.

            If this command is used without subcommand, it shows your allied guilds.
            See `{prefix}help alliance` for a list of commands to interact with your alliance!"""
        )
        async with self.bot.pool.acquire() as conn:
            alliance_id = await conn.fetchval(
                'SELECT alliance FROM guild WHERE "id"=$1;', ctx.character_data["guild"]
            )
            allied_guilds = await conn.fetch(
                'SELECT * FROM guild WHERE "alliance"=$1;', alliance_id
            )
        if (
                len(allied_guilds) <= 1
        ):  # your guild is the only one OR error and query returns zero guilds
            return await ctx.send(
                _(
                    "You are not in an alliance. You are alone and may still use all"
                    " other alliance commands or invite a guild to create a bigger"
                    " alliance."
                )
            )
        alliance_embed = discord.Embed(
            title=_("Your allied guilds"), color=self.bot.config.game.primary_colour
        ).set_thumbnail(url="https://idlerpg.xyz/alliance_banner.png")
        for guild in allied_guilds:
            alliance_embed.add_field(
                name=guild[1],
                value=_("Led by {leader}").format(
                    leader=await rpgtools.lookup(self.bot, guild["leader"])
                ),
                inline=False,
            )
        alliance_embed.set_footer(
            text=_(
                "{prefix}alliance buildings | {prefix}alliance defenses |"
                " {prefix}alliance attack | {prefix}alliance occupy |"
                " {prefix}alliance cityhelp"
            ).format(prefix=ctx.clean_prefix)
        )

        await ctx.send(embed=alliance_embed)

    @has_char()
    @has_guild()
    @alliance.group(
        name="cityhelp",
        aliases=["citywarhelp", "warhelp"],
        invoke_without_command=True,
        brief=_("Show city-war help."),
    )
    @locale_doc
    async def cityhelp(self, ctx: Context) -> None:
        _(
            """Show city-war help.

            Use `{prefix}alliance cityhelp attack` for attacker help or `{prefix}alliance cityhelp defend` for defender help."""
        )
        await ctx.send(embed=self._build_city_help_overview_embed(ctx))

    @has_char()
    @has_guild()
    @cityhelp.command(name="attack", aliases=["attacking"], brief=_("Show city attack help."))
    @locale_doc
    async def cityhelp_attack(self, ctx: Context) -> None:
        _(
            """Show help for attacking a city."""
        )
        await ctx.send(embed=self._build_city_help_attack_embed(ctx))

    @has_char()
    @has_guild()
    @cityhelp.command(
        name="defend",
        aliases=["defense", "defence", "defending"],
        brief=_("Show city defense help."),
    )
    @locale_doc
    async def cityhelp_defend(self, ctx: Context) -> None:
        _(
            """Show help for defending a city."""
        )
        await ctx.send(embed=self._build_city_help_defend_embed(ctx))

    @alliance_cooldown(300)
    @is_alliance_leader()
    @has_char()
    @alliance.command(brief=_("Invite a guild to your alliance."))
    @locale_doc
    async def invite(self, ctx: Context, newleader: MemberWithCharacter) -> None:
        _(
            """`<newleader>` - A user with a character who leads a guild.

            Invite a guild to your alliance. All allied guilds will benefit from your city's buildings. Once you're allied with another guild, it will be shown in {prefix}alliance.
            The other guild can't be allied with another alliance or own a city in order to be invited.

            Only the alliance leader can use this command.
            (This command has a cooldown of 5 minutes.)"""
        )
        if not ctx.user_data["guild"]:
            await self.bot.reset_alliance_cooldown(ctx)
            return await ctx.send(_("That member is not in a guild."))
        newguild = await self.bot.pool.fetchrow(
            'SELECT * FROM guild WHERE "id"=$1', ctx.user_data["guild"]
        )
        if newleader.id != newguild["leader"]:
            await self.bot.reset_alliance_cooldown(ctx)
            return await ctx.send(_("That member is not the leader of their guild."))
        elif (
                newguild["alliance"] == ctx.character_data["guild"]
        ):  # already part of your alliance
            await self.bot.reset_alliance_cooldown(ctx)
            return await ctx.send(
                _("This member's guild is already part of your alliance.")
            )

        async with self.bot.pool.acquire() as conn:
            if newguild["alliance"] != newguild["id"]:
                await self.bot.reset_alliance_cooldown(ctx)
                return await ctx.send(_("This guild is already in an alliance."))
            else:
                alliance_members = await conn.fetch(
                    'SELECT * FROM guild WHERE "alliance"=$1;', newguild["alliance"]
                )
                if len(alliance_members) > 1:
                    await self.bot.reset_alliance_cooldown(ctx)
                    return await ctx.send(
                        _("This guild is the leader of another alliance.")
                    )

            if not await ctx.confirm(
                    _(
                        "{newleader}, {author} invites you to join their alliance. React to"
                        " join now."
                    ).format(newleader=newleader.mention, author=ctx.author.mention),
                    user=newleader,
            ):
                return

            if (
                    await conn.fetchval(
                        'SELECT COUNT(*) FROM guild WHERE "alliance"=$1;',
                        ctx.character_data["guild"],
                    )
            ) == 3:
                await self.bot.reset_alliance_cooldown(ctx)
                return await ctx.send(_("Your alliance is full."))
            if await conn.fetchrow(
                    'SELECT * FROM city WHERE "owner"=$1;', ctx.user_data["guild"]
            ):
                await self.bot.reset_alliance_cooldown(ctx)
                return await ctx.send(
                    _(
                        "**{user}'s guild is a single-guild alliance and owns a city."
                    ).format(user=newleader)
                )
            await conn.execute(
                'UPDATE guild SET "alliance"=$1 WHERE "id"=$2;',
                ctx.character_data["guild"],
                ctx.user_data["guild"],
            )

        await ctx.send(
            _("**{newguild}** is now part of your alliance, {user}!").format(
                newguild=newguild["name"], user=ctx.author.mention
            )
        )

    @is_guild_leader()
    @alliance.command(brief=_("Leave your alliance"))
    @locale_doc
    async def leave(self, ctx: Context) -> None:
        _(
            """Leave your alliance. Once you left your alliance, you will no longer benefit from an owned city's buildings.

            If you lead an alliance, you cannot leave it (consider `{prefix}alliance kick`).
            Only guild leaders can use this command."""
        )
        async with self.bot.pool.acquire() as conn:
            alliance = await conn.fetchval(
                'SELECT alliance from guild WHERE "id"=$1;', ctx.character_data["guild"]
            )
            if alliance == ctx.character_data["guild"]:
                return await ctx.send(
                    _("You are the alliance's leading guild and cannot leave it!")
                )
            await conn.execute(
                'UPDATE guild SET "alliance"="id" WHERE "id"=$1;',
                ctx.character_data["guild"],
            )
        await ctx.send(_("Your guild left the alliance."))

    @is_alliance_leader()
    @has_char()
    @alliance.command(brief=_("Kick a guild from your alliance"))
    @locale_doc
    async def kick(self, ctx: Context, *, guild_to_kick: int | str) -> None:
        _(
            """`<guild_to_kick>` -  A guild's name or ID

            Remove a guild from your alliance. Once the guild was kicked, it will no longer benefit from an owned city's buildings.

            Only the alliance leader can use this command."""
        )
        if isinstance(guild_to_kick, str):
            guild = await self.bot.pool.fetchrow(
                'SELECT * FROM guild WHERE "name"=$1;', guild_to_kick
            )
        else:
            guild = await self.bot.pool.fetchrow(
                'SELECT * FROM guild WHERE "id"=$1;', guild_to_kick
            )

        if not guild:
            return await ctx.send(
                _(
                    "Cannot find guild `{guild_to_kick}`. Are you sure that's the right"
                    " name/ID?"
                ).format(guild_to_kick=guild_to_kick)
            )
        if guild["id"] == ctx.character_data["guild"]:
            return await ctx.send(_("That won't work."))

        if guild["alliance"] != ctx.character_data["guild"]:
            return await ctx.send(_("This guild is not in your alliance."))

        if not await ctx.confirm(
                _("Do you really want to kick **{guild}** from your alliance?").format(
                    guild=guild["name"]
                )
        ):
            return

        async with self.bot.pool.acquire() as conn:
            await conn.execute(
                'UPDATE guild SET "alliance"=$1 WHERE "id"=$1;', guild["id"]
            )

        await ctx.send(
            _("**{guild}** is no longer part of your alliance.").format(
                guild=guild["name"]
            )
        )

    def list_subcommands(self, ctx: Context) -> list[str] | str:
        if not ctx.command.commands:
            return "None"
        return [ctx.clean_prefix + x.qualified_name for x in ctx.command.commands]

    def get_upgrade_price(self, current: int) -> int:
        return (current + 1) * 100000

    @alliance.group(invoke_without_command=True, brief=_("Build buildings or defenses"))
    @locale_doc
    async def build(self, ctx: Context) -> None:
        _(
            """Build buildings `{prefix}alliance build building` or defenses `{prefix}alliance build defense`."""
        )
        subcommands = "```" + "\n".join(self.list_subcommands(ctx)) + "```"
        await ctx.send(_("Please use one of these subcommands:\n\n") + subcommands)

    @alliance_cooldown(120)
    @alliance.group(invoke_without_command=True, brief=_("Destroy defenses"))
    @owns_city()
    @is_alliance_leader()
    @locale_doc
    async def destroy(self, ctx, *, defense: str = None):
        _(
            """Build buildings `{prefix}alliance build building` or defenses `{prefix}alliance build defense`."""
        )
        try:
            guild_id = ctx.character_data["guild"]

            async with self.bot.pool.acquire() as connection:
                async with connection.transaction():
                    city_name = await connection.fetchval(
                        "SELECT name FROM city WHERE owner = $1", guild_id
                    )
                    if not city_name:
                        await self.bot.reset_alliance_cooldown(ctx)
                        return await ctx.send(_("City not found."))

                    raw_defenses = [
                        dict(row)
                        for row in await connection.fetch(
                            "SELECT * FROM defenses WHERE city = $1 ORDER BY id ASC",
                            city_name,
                        )
                    ]

                    if not raw_defenses:
                        await self.bot.reset_alliance_cooldown(ctx)
                        return await ctx.send(_("Defense not found"))

                    active_defenses, inactive_defenses = self._partition_city_defenses(
                        raw_defenses,
                        city_name,
                    )
                    defense_rows = active_defenses + inactive_defenses

                    if defense is None:
                        if len(defense_rows) == 1:
                            selected_defense = defense_rows[0]
                        else:
                            try:
                                selected_index = await Choose(
                                    [
                                        _("{slot}: {name} ({hp} HP)").format(
                                            slot=self._get_city_war_slot_label(
                                                self._get_city_war_defense_instance_slot_id(
                                                    defense_row
                                                )
                                            ),
                                            name=defense_row["name"].title(),
                                            hp=f"{int(defense_row['hp']):,}",
                                        )
                                        for defense_row in defense_rows
                                    ],
                                    title=_("Choose a Defense to Destroy"),
                                    choices=[
                                        _("{slot}: {name}").format(
                                            slot=self._get_city_war_slot_label(
                                                self._get_city_war_defense_instance_slot_id(
                                                    defense_row
                                                )
                                            ),
                                            name=defense_row["name"].title(),
                                        )
                                        for defense_row in defense_rows
                                    ],
                                    footer=_("City: {city}").format(city=city_name),
                                    timeout=60,
                                    return_index=True,
                                ).paginate(ctx)
                            except NoChoice:
                                await self.bot.reset_alliance_cooldown(ctx)
                                return await ctx.send(_("No defense was selected."))
                            selected_defense = defense_rows[selected_index]
                    else:
                        search = defense.strip().lower()
                        compact_search = search.replace(" ", "")
                        matching_defenses = []
                        for defense_row in defense_rows:
                            slot_id = self._get_city_war_defense_instance_slot_id(
                                defense_row
                            )
                            slot_label = self._get_city_war_slot_label(slot_id).lower()
                            if (
                                defense_row["name"].lower() == search
                                or slot_label == search
                                or slot_label.replace(" ", "") == compact_search
                                or str(slot_id).lower() == compact_search
                            ):
                                matching_defenses.append(defense_row)

                        if not matching_defenses:
                            await self.bot.reset_alliance_cooldown(ctx)
                            return await ctx.send(
                                _("{defense} not found in {city}.").format(
                                    defense=defense,
                                    city=city_name,
                                )
                            )

                        if len(matching_defenses) == 1:
                            selected_defense = matching_defenses[0]
                        else:
                            try:
                                selected_index = await Choose(
                                    [
                                        _("{slot}: {name} ({hp} HP)").format(
                                            slot=self._get_city_war_slot_label(
                                                self._get_city_war_defense_instance_slot_id(
                                                    defense_row
                                                )
                                            ),
                                            name=defense_row["name"].title(),
                                            hp=f"{int(defense_row['hp']):,}",
                                        )
                                        for defense_row in matching_defenses
                                    ],
                                    title=_("Choose a Matching Defense"),
                                    choices=[
                                        _("{slot}: {name}").format(
                                            slot=self._get_city_war_slot_label(
                                                self._get_city_war_defense_instance_slot_id(
                                                    defense_row
                                                )
                                            ),
                                            name=defense_row["name"].title(),
                                        )
                                        for defense_row in matching_defenses
                                    ],
                                    footer=_("City: {city}").format(city=city_name),
                                    timeout=60,
                                    return_index=True,
                                ).paginate(ctx)
                            except NoChoice:
                                await self.bot.reset_alliance_cooldown(ctx)
                                return await ctx.send(_("No defense was selected."))
                            selected_defense = matching_defenses[selected_index]

                    slot_label = self._get_city_war_slot_label(
                        self._get_city_war_defense_instance_slot_id(selected_defense)
                    )
                    confirmed = await ctx.confirm(
                        _(
                            "Are you sure you want to destroy **{defense}** in **{slot}** for **{city}**?"
                        ).format(
                            defense=selected_defense["name"].title(),
                            slot=slot_label,
                            city=city_name,
                        )
                    )
                    if not confirmed:
                        return await ctx.send(_("Deletion cancelled."))

                    deleted_defense = await connection.fetchrow(
                        "DELETE FROM defenses WHERE id = $1 RETURNING *",
                        selected_defense["id"],
                    )
                    if not deleted_defense:
                        await self.bot.reset_alliance_cooldown(ctx)
                        return await ctx.send(
                            _("That defense no longer exists in {city}.").format(
                                city=city_name
                            )
                        )

                    await ctx.send(
                        _("Destroyed **{defense}** in **{slot}** for **{city}**.").format(
                            defense=selected_defense["name"].title(),
                            slot=slot_label,
                            city=city_name,
                        )
                    )
        except Exception as e:
            await ctx.send(str(e))

    @alliance_cooldown(300)
    @owns_city()
    @is_alliance_leader()
    @has_char()
    @build.command(brief=_("Upgrade a building in your city."))
    @locale_doc
    async def building(self, ctx: Context, name: str.lower) -> None:
        _(
            """`<name>` - The name of the building to upgrade.

            Upgrade one of your city's buildings, granting better passive bonuses. The maximum level of any building is 10.
            Depending on the city's available buildings, `<name>` is either Thief, Raid, Trade, or Adventure. Use `{prefix}alliance buildings` to see which are available.

            The upgrade price depends on the building's next level and is calculated as next_level * $100,000.
            The upgrade price will be removed from the Alliance Leader's guild bank.

            This command requires your alliance to own a city.
            Only the alliance leader can use this command.
            (This command has a cooldown of 5 minutes)"""
        )
        city = await self.bot.pool.fetchrow(
            'SELECT * FROM city WHERE "owner"=$1;',
            ctx.character_data[
                "guild"
            ],  # can only be done by the leading g:uild so this works here
        )
        if self.city_configs[city["name"]].get(name, False) is False:
            await self.bot.reset_alliance_cooldown(ctx)
            return await ctx.send(
                _(
                    "Invalid building. Please use `{prefix}{cmd}"
                    " [thief/raid/trade/adventure]` or check the possible buildings in"
                    " your city."
                ).format(prefix=ctx.clean_prefix, cmd=ctx.command.qualified_name)
            )
        cur_level = city[f"{name}_building"]
        if cur_level == 10:
            await self.bot.reset_alliance_cooldown(ctx)
            return await ctx.send(_("This building is fully upgraded."))
        up_price = self.get_upgrade_price(cur_level)
        if not await ctx.confirm(
                _(
                    "Are you sure you want to upgrade the **{name} building** to level"
                    " {new_level}? This will cost $**{price}**."
                ).format(name=name, new_level=cur_level + 1, price=up_price)
        ):
            return
        if not await guild_has_money(self.bot, ctx.character_data["guild"], up_price):
            await self.bot.reset_alliance_cooldown(ctx)
            return await ctx.send(
                _(
                    "Your guild doesn't have enough money to upgrade the city's {name}"
                    " building."
                ).format(name=name)
            )

        async with self.bot.pool.acquire() as conn:
            await conn.execute(
                f'UPDATE city SET "{name}_building"="{name}_building"+1 WHERE'
                ' "owner"=$1;',
                ctx.character_data["guild"],
            )
            await conn.execute(
                'UPDATE guild SET "money"="money"-$1 WHERE "id"=$2;',
                up_price,
                ctx.character_data["guild"],
            )
            await self.bot.log_transaction(
                ctx,
                from_=ctx.author.id,
                to=2,
                subject="alliance",
                data={"Gold": up_price, "Building": name},
                conn=conn,
            )

        await ctx.send(
            _(
                "Successfully upgraded the city's {name} building to level"
                " **{new_level}**."
            ).format(name=name, new_level=cur_level + 1)
        )

    @alliance_cooldown(60)
    @owns_city()
    @is_alliance_leader()
    @has_char()
    @build.command(brief=_("Build a defense in your city."))
    @locale_doc
    async def defense(self, ctx: Context, *, name: str.lower = None) -> None:
        _(
            """Build some defensive fortifications in your city. The following are available:

            Cannons: 1,000HP, 120 defense for $200,000
            Archers: 2,000HP, 100 defense for $100,000
            Outer Wall: 80,000HP, 0 defense for $500,000
            Inner Wall: 40,000HP, 0 defense for $200,000
            Moat: 20,000HP, 50 defense for $150,000
            Tower: 5,000HP, 100 defense for $200,000
            Ballista: 1,000HP, 60 defense for $100,000

            Tier 1-2 cities have 3 defense slots: 1 wall, 1 weapon, and 1 utility.
            Tier 3 cities gain 1 extra weapon slot.
            Tier 4 cities gain 1 extra weapon slot and 1 extra utility slot.
            If an outer wall is active, one utility slot may instead hold an inner wall.

            Running the command without a defense name opens a guided slot picker.
            You may not build defenses while your city is under attack. The price of the defense is removed from the leading guild's bank.

            This command requires your alliance to own a city.
            Only the alliance leader can use this command.
            (This command has a cooldown of 1 minutes)"""
        )
        try:
            if name is not None and name not in CITY_WAR_DEFENSES:
                await self.bot.reset_alliance_cooldown(ctx)
                return await ctx.send(
                    _("Invalid defense. Please use `{prefix}{cmd} [{buildings}]`.").format(
                        prefix=ctx.clean_prefix,
                        cmd=ctx.command.qualified_name,
                        buildings="/".join(CITY_WAR_DEFENSES.keys()),
                    )
                )
            async with self.bot.pool.acquire() as conn:
                city_name = await conn.fetchval(
                    'SELECT name FROM city WHERE "owner"=$1;', ctx.character_data["guild"]
                )
                if (
                        await self.bot.redis.execute_command("GET", f"city:{city_name}")
                ) == b"under attack":
                    await self.bot.reset_alliance_cooldown(ctx)
                    return await ctx.send(
                        _("Your city is under attack. Defenses cannot be built.")
                    )
                active_defenses, inactive_defenses = await self._load_city_defenses(
                    conn, city_name
                )
                occupied_slots = {
                    self._get_city_war_defense_instance_slot_id(defense): defense
                    for defense in active_defenses
                }
                open_slots = self._get_city_war_open_slots(city_name, active_defenses)

                if name is None:
                    if not open_slots:
                        await self.bot.reset_alliance_cooldown(ctx)
                        return await ctx.send(
                            _(
                                "All defense slots are full for **{city}**. Occupied slots: {slots}."
                            ).format(
                                city=city_name,
                                slots=self._format_city_war_occupied_slots(
                                    list(self._get_city_war_slots_for_city(city_name)),
                                    occupied_slots,
                                ),
                            )
                        )
                    selected_slot = await self._choose_city_war_slot_for_build(
                        ctx,
                        city_name,
                        open_slots,
                        active_defenses,
                    )
                    if selected_slot is None:
                        await self.bot.reset_alliance_cooldown(ctx)
                        return await ctx.send(_("No defense slot was selected."))

                    selected_defense_name = await self._choose_city_war_defense_for_slot(
                        ctx,
                        city_name,
                        selected_slot,
                        active_defenses,
                    )
                    if selected_defense_name is None:
                        await self.bot.reset_alliance_cooldown(ctx)
                        return await ctx.send(_("No defense was selected."))
                else:
                    selected_defense_name = name
                    matching_open_slots = [
                        slot_id
                        for slot_id in open_slots
                        if self._is_city_war_defense_allowed_in_slot(
                            city_name,
                            slot_id,
                            selected_defense_name,
                            active_defenses=active_defenses,
                        )
                    ]
                    if not matching_open_slots:
                        matching_slots = [
                            slot_id
                            for slot_id in self._get_city_war_slots_for_city(city_name)
                            if self._is_city_war_defense_allowed_in_slot(
                                city_name,
                                slot_id,
                                selected_defense_name,
                                active_defenses=active_defenses,
                            )
                        ]
                        await self.bot.reset_alliance_cooldown(ctx)
                        return await ctx.send(
                            _(
                                "Your city's valid **{defense}** slots are already full. Occupied: {occupied}."
                            ).format(
                                defense=selected_defense_name.title(),
                                occupied=self._format_city_war_occupied_slots(
                                    matching_slots,
                                    occupied_slots,
                                ),
                            ),
                        )
                    selected_slot = matching_open_slots[0]

                building = CITY_WAR_DEFENSES[selected_defense_name]
                slot_label = self._get_city_war_slot_label(selected_slot)
                if selected_slot in occupied_slots:
                    active_defense = occupied_slots[selected_slot]
                    await self.bot.reset_alliance_cooldown(ctx)
                    return await ctx.send(
                        _(
                            "Your city's **{slot}** slot is already occupied by **{defense}**. Destroy it before building another defense in that slot."
                        ).format(
                            slot=slot_label.lower(),
                            defense=active_defense["name"].title(),
                        )
                    )
                if not await ctx.confirm(
                        _(
                            "Build **{defense}** in **{slot}** for **${price}**?\n{details}"
                        ).format(
                            defense=selected_defense_name.title(),
                            slot=slot_label,
                            price=f"{building['cost']:,}",
                            details=self._describe_city_war_defense(selected_defense_name),
                        )
                ):
                    return
                if not await guild_has_money(
                        self.bot, ctx.character_data["guild"], building["cost"]
                ):
                    await self.bot.reset_alliance_cooldown(ctx)
                    return await ctx.send(
                        _(
                            "Your guild doesn't have enough money to build a {defense}."
                        ).format(defense=selected_defense_name)
                    )

                await conn.execute(
                    'INSERT INTO defenses ("city", "name", "hp", "defense", "slot_id") VALUES ($1, $2,'
                    " $3, $4, $5);",
                    city_name,
                    selected_defense_name,
                    building["hp"],
                    building["def"],
                    selected_slot,
                )
                await conn.execute(
                    'UPDATE guild SET "money"="money"-$1 WHERE "id"=$2;',
                    building["cost"],
                    ctx.character_data["guild"],
                )
                await self.bot.log_transaction(
                    ctx,
                    from_=ctx.author.id,
                    to=2,
                    subject="alliance",
                    data={
                        "Gold": building["cost"],
                        "Defense": selected_defense_name,
                        "Defense Slot": slot_label,
                    },
                    conn=conn,
                )

            await ctx.send(
                _("Successfully built **{defense}** in **{slot}**.").format(
                    defense=selected_defense_name.title(),
                    slot=slot_label,
                )
            )
        except Exception as e:
            await self.bot.reset_alliance_cooldown(ctx)
            return await ctx.send(_("An error occurred while building the defense."))
        

    @has_char()
    @alliance.command(brief=_("Lists your city's buildings."))
    @locale_doc
    async def buildings(self, ctx: Context) -> None:
        _(
            """Lists all buildings in your city, along with their level. These buildings give passive rewards to all alliance members:

            Thief buildings increase your chance to steal money as a thief, for every level, this increases your chance by 5%
            Raid buildings increase a user's raidstats by 0.1 per level
            Trade buildings remove the need to pay the 5% tax when selling or buying items when it reached at least Level 1. It also increases the amount of money you get from `{prefix}merch` and `{prefix}merchall` increasing the reward by 50% for each level
            Adventure buildings shorten the adventure time by 1% per level and increase your success chances by 1% per level.

            Your alliance must own a city to use this command."""
        )
        async with self.bot.pool.acquire() as conn:
            alliance = await conn.fetchval(
                'SELECT alliance FROM guild WHERE "id"=$1;', ctx.character_data["guild"]
            )
            buildings = await conn.fetchrow(
                'SELECT * FROM city WHERE "owner"=$1;', alliance
            )
        if not buildings:
            return await ctx.send(_("Your alliance does not own a city."))
        embed = discord.Embed(
            title=_("{city}'s buildings").format(city=buildings["name"]),
            colour=self.bot.config.game.primary_colour,
        ).set_image(url="https://idlerpg.xyz/market.png")
        for i in ("thief", "raid", "trade", "adventure"):
            if self.city_configs[buildings["name"]][i]:
                embed.add_field(
                    name=f"{i.capitalize()} building",
                    value=_("Level {level}").format(level=buildings[f"{i}_building"]),
                    inline=True,
                )
        await ctx.send(embed=embed)

    @has_char()
    @alliance.command(brief=_("Lists your city's defenses."))
    @locale_doc
    async def defenses(self, ctx: Context) -> None:
        _(
            """Lists your city's defenses and view the HP left for each.

            Your alliance must own a city to use this command."""
        )
        async with self.bot.pool.acquire() as conn:
            alliance = await conn.fetchval(
                'SELECT alliance FROM guild WHERE "id"=$1;', ctx.character_data["guild"]
            )
            city_name = await conn.fetchval(
                'SELECT name FROM city WHERE "owner"=$1;', alliance
            )
            defenses, inactive_defenses = (
                await self._load_city_defenses(conn, city_name)
            ) if city_name else ([], [])
            guards = (
                await self.bot.get_city_guards(city_name, conn=conn)
                if city_name
                else []
            )
            guard_pet = (
                await self.bot.get_city_guard_pet(city_name, conn=conn)
                if city_name
                else None
            )
            guard_user_ids = {int(guard["user_id"]) for guard in guards}
            if guard_pet and int(guard_pet["user_id"]) not in guard_user_ids:
                await self.bot.clear_city_guard_pet(city=city_name, conn=conn)
                guard_pet = None
        if not city_name:
            return await ctx.send(_("Your alliance does not own a city."))
        city_tier = self._get_city_tier(city_name)
        open_slots = self._get_city_war_open_slots(city_name, defenses)
        occupied_slots = {
            self._get_city_war_defense_instance_slot_id(defense): defense
            for defense in defenses
        }
        embed = discord.Embed(
            title=_("{city}'s defenses").format(city=city_name),
            colour=self.bot.config.game.primary_colour,
        ).set_thumbnail(url="https://idlerpg.xyz/fortress.png")
        embed.description = _(
            "Tier {tier} city\nDefense slots: {slots}"
        ).format(
            tier=city_tier,
            slots=self._get_city_war_slot_capacity_text(city_name),
        )
        has_active_defenses = False
        for i in defenses:
            has_active_defenses = True
            slot_label = self._get_city_war_slot_label(
                self._get_city_war_defense_instance_slot_id(i)
            )
            embed.add_field(
                name=_("{name} ({slot} Slot)").format(
                    name=i["name"].title(),
                    slot=slot_label,
                ),
                value=_("HP: {hp}, Retaliation: {defense}").format(
                    hp=i["hp"], defense=i["defense"]
                ),
                inline=True,
            )
        if inactive_defenses:
            embed.add_field(
                name=_("Inactive Legacy Fortifications"),
                value="\n".join(
                    _("{name} ({slot} slot, {hp} HP)").format(
                        name=defense["name"].title(),
                        slot=self._get_city_war_slot_label(
                            self._get_city_war_defense_instance_slot_id(defense)
                        ).lower(),
                        hp=defense["hp"],
                    )
                    for defense in inactive_defenses
                ),
                inline=False,
            )
        embed.add_field(
            name=_("Open Defense Slots"),
            value=(
                ", ".join(self._get_city_war_slot_label(slot_id) for slot_id in open_slots)
                if open_slots
                else _("None. All available defense slots are occupied.")
            ),
            inline=False,
        )
        if guards:
            guard_names = [
                await rpgtools.lookup(self.bot, guard["user_id"]) for guard in guards
            ]
            embed.add_field(
                name=_("City Guards"),
                value=", ".join(guard_names),
                inline=False,
            )
        else:
            embed.add_field(
                name=_("City Guards"),
                value=_("No guards assigned."),
                inline=False,
            )
        embed.add_field(
            name=_("Guard Pet"),
            value=(
                _("**{pet}** (Owner: {owner})").format(
                    pet=guard_pet["pet_name"],
                    owner=await rpgtools.lookup(self.bot, guard_pet["user_id"]),
                )
                if guard_pet
                else _("No guard pet assigned.")
            ),
            inline=False,
        )
        if not has_active_defenses:
            embed.add_field(
                name=_("None built"),
                value=_(
                    "Use `{prefix}alliance build defense` to open the selector or `{prefix}alliance build defense <name>` for a direct buy."
                ).format(prefix=ctx.clean_prefix),
            )
        await ctx.send(embed=embed)

    @has_char()
    @alliance.group(
        invoke_without_command=True, brief=_("Lists and manages city guards.")
    )
    @locale_doc
    async def guards(self, ctx: Context) -> None:
        _(
            """Lists the city guards assigned to your alliance's city.

            Assigned guards are real guild members stationed in the city. While on guard duty, they cannot join guild adventures or city attacks."""
        )
        async with self.bot.pool.acquire() as conn:
            alliance = await conn.fetchval(
                'SELECT alliance FROM guild WHERE "id"=$1;', ctx.character_data["guild"]
            )
            city_row = await conn.fetchrow('SELECT * FROM city WHERE "owner"=$1;', alliance)
            if not city_row:
                return await ctx.send(_("Your alliance does not own a city."))
            owner_guild_name = await conn.fetchval(
                'SELECT name FROM guild WHERE "id"=$1;',
                city_row["owner"],
            )
            guards = await self.bot.get_city_guards(city_row["name"], conn=conn)
            guard_pet = await self.bot.get_city_guard_pet(city_row["name"], conn=conn)

        embed = discord.Embed(
            title=_("{city}'s city guards").format(city=city_row["name"]),
            colour=self.bot.config.game.primary_colour,
        ).set_thumbnail(url="https://idlerpg.xyz/fortress.png")
        embed.description = _(
            "Owner guild: {guild}\nAssigned guards: {count}/{limit}"
        ).format(
            guild=owner_guild_name,
            count=len(guards),
            limit=CITY_GUARD_LIMIT,
        )
        if guards:
            for guard in guards:
                embed.add_field(
                    name=await rpgtools.lookup(self.bot, guard["user_id"]),
                    value=_("Stationed in the city"),
                    inline=False,
                )
        else:
            embed.add_field(
                name=_("No guards assigned"),
                value=_("Use `{prefix}alliance guards add <member>` to station someone.").format(
                    prefix=ctx.clean_prefix
                ),
                inline=False,
            )
        if guard_pet:
            embed.add_field(
                name=_("Assigned Guard Pet"),
                value=_("**{pet}** (Owner: {owner})").format(
                    pet=guard_pet["pet_name"],
                    owner=await rpgtools.lookup(self.bot, guard_pet["user_id"]),
                ),
                inline=False,
            )
        else:
            embed.add_field(
                name=_("Assigned Guard Pet"),
                value=_("Use `{prefix}alliance guards pet set <member> <pet>` to station one.").format(
                    prefix=ctx.clean_prefix
                ),
                inline=False,
            )
        await ctx.send(embed=embed)

    @owns_city()
    @is_alliance_leader()
    @has_char()
    @guards.command(name="add", brief=_("Assign a city guard."))
    @locale_doc
    async def guards_add(self, ctx: Context, member: MemberWithCharacter) -> None:
        _(
            """`<member>` - A member of your guild.

            Assign a guild member as a city guard. Guard duty blocks guild adventures and city attacks while they are stationed."""
        )
        async with self.bot.pool.acquire() as conn:
            city_name = await conn.fetchval(
                'SELECT name FROM city WHERE "owner"=$1;',
                ctx.character_data["guild"],
            )
            if not city_name:
                return await ctx.send(_("Your alliance does not own a city."))
            city_status = await self.bot.redis.execute_command("GET", f"city:{city_name}")
            if city_status and city_status.decode() == "under attack":
                return await ctx.send(_("You cannot change guards while the city is under attack."))
            member_guild = await conn.fetchval(
                'SELECT "guild" FROM profile WHERE "user"=$1;',
                member.id,
            )
            if member_guild != ctx.character_data["guild"]:
                return await ctx.send(
                    _("City guards must be members of the guild that owns the city.")
                )
            existing_guard = await self.bot.get_city_guard(member.id, conn=conn)
            if existing_guard and existing_guard["city"] == city_name:
                return await ctx.send(_("That member is already stationed as a city guard."))
            if existing_guard:
                return await ctx.send(
                    _("That member is already guarding **{city}**.").format(
                        city=existing_guard["city"]
                    )
                )
            current_guards = await self.bot.get_city_guards(city_name, conn=conn)
            if len(current_guards) >= CITY_GUARD_LIMIT:
                return await ctx.send(
                    _("Your city already has the maximum of **{limit}** guards.").format(
                        limit=CITY_GUARD_LIMIT
                    )
                )
            await conn.execute(
                """
                INSERT INTO city_guards ("user_id", "guild_id", "city", "assigned_by")
                VALUES ($1, $2, $3, $4);
                """,
                member.id,
                ctx.character_data["guild"],
                city_name,
                ctx.author.id,
            )
        await ctx.send(
            _("**{member}** is now stationed as a city guard in **{city}**.").format(
                member=member,
                city=city_name,
            )
        )

    @owns_city()
    @is_alliance_leader()
    @has_char()
    @guards.command(name="remove", brief=_("Remove a city guard."))
    @locale_doc
    async def guards_remove(self, ctx: Context, member: MemberWithCharacter) -> None:
        _(
            """`<member>` - A currently assigned city guard.

            Remove a stationed city guard from duty."""
        )
        async with self.bot.pool.acquire() as conn:
            city_name = await conn.fetchval(
                'SELECT name FROM city WHERE "owner"=$1;',
                ctx.character_data["guild"],
            )
            if not city_name:
                return await ctx.send(_("Your alliance does not own a city."))
            city_status = await self.bot.redis.execute_command("GET", f"city:{city_name}")
            if city_status and city_status.decode() == "under attack":
                return await ctx.send(_("You cannot change guards while the city is under attack."))
            guard = await self.bot.get_city_guard(member.id, conn=conn)
            if not guard or guard["city"] != city_name:
                return await ctx.send(_("That member is not guarding your city."))
            await self.bot.clear_city_guards(user_id=member.id, conn=conn)
        await ctx.send(
            _("**{member}** has been relieved from city guard duty.").format(
                member=member
            )
        )

    @owns_city()
    @is_alliance_leader()
    @has_char()
    @guards.group(name="pet", invoke_without_command=True, brief=_("Show or manage the city guard pet."))
    @locale_doc
    async def guards_pet(self, ctx: Context) -> None:
        _(
            """Shows the pet currently assigned to defend your city alongside the guards."""
        )
        async with self.bot.pool.acquire() as conn:
            city_name = await conn.fetchval(
                'SELECT name FROM city WHERE "owner"=$1;',
                ctx.character_data["guild"],
            )
            if not city_name:
                return await ctx.send(_("Your alliance does not own a city."))
            guard_pet = await self.bot.get_city_guard_pet(city_name, conn=conn)

        if not guard_pet:
            return await ctx.send(_("No city guard pet is currently assigned."))

        await ctx.send(
            _("**{pet}** is stationed in **{city}** as the city guard pet. Owner: **{owner}**.").format(
                pet=guard_pet["pet_name"],
                city=city_name,
                owner=await rpgtools.lookup(self.bot, guard_pet["user_id"]),
            )
        )

    @owns_city()
    @is_alliance_leader()
    @has_char()
    @guards_pet.command(name="set", aliases=["add"], brief=_("Assign the city guard pet."))
    @locale_doc
    async def guards_pet_set(
        self,
        ctx: Context,
        member: MemberWithCharacter,
        *,
        pet_ref: str,
    ) -> None:
        _(
            """`<member>` - A stationed city guard from the guild that owns the city.
            `<pet>` - A pet ID or alias.

            Assign one pet to defend the city alongside the guards. The pet does not need to be equipped, but it must be at least young and not boarded in daycare."""
        )
        async with self.bot.pool.acquire() as conn:
            city_name = await conn.fetchval(
                'SELECT name FROM city WHERE "owner"=$1;',
                ctx.character_data["guild"],
            )
            if not city_name:
                return await ctx.send(_("Your alliance does not own a city."))

            city_status = await self.bot.redis.execute_command("GET", f"city:{city_name}")
            if city_status and city_status.decode() == "under attack":
                return await ctx.send(_("You cannot change the guard pet while the city is under attack."))

            await self.bot._ensure_city_war_tables()

            member_guild = await conn.fetchval(
                'SELECT "guild" FROM profile WHERE "user"=$1;',
                member.id,
            )
            if member_guild != ctx.character_data["guild"]:
                return await ctx.send(
                    _("The guard pet must belong to a member of the guild that owns the city.")
                )
            if not await self.bot.get_city_guard(member.id, conn=conn):
                return await ctx.send(
                    _("The city guard pet must belong to a member currently assigned as a city guard.")
                )

            pets_cog = self.bot.get_cog("Pets")
            if not pets_cog or not hasattr(pets_cog, "fetch_pet_for_user"):
                return await ctx.send(_("The pet system is unavailable right now."))

            pet, pet_id = await pets_cog.fetch_pet_for_user(conn, member.id, pet_ref)
            if not pet:
                return await ctx.send(_("That member does not have a pet matching `{pet}`.").format(pet=pet_ref))
            if pet["growth_stage"] not in ["young", "adult"]:
                return await ctx.send(
                    _("**{pet}** must be at least in the **young** growth stage.").format(
                        pet=pet["name"]
                    )
                )
            if pet["daycare_boarding_id"] is not None:
                return await ctx.send(
                    _("**{pet}** is currently boarded in daycare and cannot defend the city.").format(
                        pet=pet["name"]
                    )
                )

            await conn.execute(
                """
                INSERT INTO city_guard_pet ("city", "guild_id", "user_id", "pet_id", "assigned_by")
                VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT ("city") DO UPDATE SET
                    "guild_id" = EXCLUDED."guild_id",
                    "user_id" = EXCLUDED."user_id",
                    "pet_id" = EXCLUDED."pet_id",
                    "assigned_by" = EXCLUDED."assigned_by",
                    "assigned_at" = NOW();
                """,
                city_name,
                ctx.character_data["guild"],
                member.id,
                pet_id,
                ctx.author.id,
            )

        await ctx.send(
            _("**{pet}** now defends **{city}** as its stationed pet. Owner: **{owner}**.").format(
                pet=pet["name"],
                city=city_name,
                owner=member,
            )
        )

    @owns_city()
    @is_alliance_leader()
    @has_char()
    @guards_pet.command(name="remove", brief=_("Remove the city guard pet."))
    @locale_doc
    async def guards_pet_remove(self, ctx: Context) -> None:
        _(
            """Remove the currently assigned city guard pet."""
        )
        async with self.bot.pool.acquire() as conn:
            city_name = await conn.fetchval(
                'SELECT name FROM city WHERE "owner"=$1;',
                ctx.character_data["guild"],
            )
            if not city_name:
                return await ctx.send(_("Your alliance does not own a city."))

            city_status = await self.bot.redis.execute_command("GET", f"city:{city_name}")
            if city_status and city_status.decode() == "under attack":
                return await ctx.send(_("You cannot change the guard pet while the city is under attack."))

            guard_pet = await self.bot.get_city_guard_pet(city_name, conn=conn)
            if not guard_pet:
                return await ctx.send(_("There is no city guard pet assigned right now."))

            await self.bot.clear_city_guard_pet(city=city_name, conn=conn)

        await ctx.send(_("The city guard pet has been removed from **{city}**.").format(city=city_name))

    @owns_city()
    @is_alliance_leader()
    @has_char()
    @alliance.command(brief=_("Abandon your city"))
    @locale_doc
    async def abandon(self, ctx: Context) -> None:
        _(
            """Abandoning your city will immediately make all alliance members lose all passive bonuses offered by the city's buildings and the city ownership will be given back to the System Guild Alliance.

            Your alliance must own a city to use this command.
            Only the alliance leader can use this command."""
        )
        if not await ctx.confirm(
                _("Are you sure you want to give up control of your city?")
        ):
            return
        name = await self.bot.pool.fetchval(
            'UPDATE city SET "owner"=1 WHERE "owner"=$1 RETURNING "name";',
            ctx.character_data["guild"],
        )
        await self.bot.pool.execute('DELETE FROM defenses WHERE "city"=$1;', name)
        await self.bot.clear_city_guards(city=name)
        await self.bot.clear_city_guard_pet(city=name)
        await self.bot.redis.execute_command("DEL", f"city:{name}:occ")
        await ctx.send(_("{city} was abandoned.").format(city=name))
        await self.bot.public_log(f"**{ctx.author}** abandoned **{name}**.")

    @owns_no_city()
    @is_alliance_leader()
    @has_char()
    @alliance.command(brief=_("Take over a city."))
    @locale_doc
    async def occupy(self, ctx: Context, *, city: str.title) -> None:
        _(
            """`<city>` - The name of a city. You can check the city names with `{prefix}cities`

            Occupy a city. Your alliance will then own that city and will be able to build defenses and level up buildings.
            You can only occupy a city if it has zero fortifications, no city guards left, and no stationed city pet.

            Occupying a city sets it on a cooldown of 10 minutes, during which time it cannot be occupied by another alliance.
            Occupying a city also sets all of its buildings back to level 0.

            You cannot occupy a city if your alliance already owns one.
            Only the alliance leader can use this command."""
        )
        if city not in self.city_configs:
            return await ctx.send(_("Invalid city name."))
        async with self.bot.pool.acquire() as conn:
            previous_owner = await conn.fetchval(
                'SELECT "owner" FROM city WHERE "name"=$1;',
                city,
            )
            active_defenses, inactive_defenses = await self._load_city_defenses(
                conn, city
            )
            num_units = len(active_defenses)
            guards = await self.bot.get_city_guards(city, conn=conn)
            guard_count = len(guards)
            guard_pet = await self.bot.get_city_guard_pet(city, conn=conn)
            if guard_pet and int(guard_pet["user_id"]) not in {
                int(guard["user_id"]) for guard in guards
            }:
                await self.bot.clear_city_guard_pet(city=city, conn=conn)
                guard_pet = None
            occ_ttl = await self.bot.redis.execute_command("TTL", f"city:{city}:occ")
            if num_units != 0 or guard_count != 0 or guard_pet:
                remaining_defenders = []
                if num_units != 0:
                    remaining_defenders.append(
                        _("**{amount}** defensive fortifications").format(
                            amount=num_units
                        )
                    )
                if guard_count != 0:
                    remaining_defenders.append(
                        _("**{amount}** stationed city guards").format(
                            amount=guard_count
                        )
                    )
                if guard_pet:
                    remaining_defenders.append(
                        _("**1** stationed city pet")
                    )
                return await ctx.send(
                    _(
                        "The city is still defended by {defenders}."
                    ).format(defenders=rpgtools.nice_join(remaining_defenders))
                )
            if occ_ttl != -2:
                return await ctx.send(
                    _("{city} was just occupied and stands under protection.").format(
                        city=city
                    )
                )
            gold_lost = 0
            defending_guild_name = None
            if previous_owner not in (None, 1, ctx.character_data["guild"]):
                gold_lost, defending_guild_name = await self._apply_conquest_vault_loss(
                    previous_owner,
                    conn,
                )
            await conn.execute(
                'UPDATE city SET "owner"=$1, "raid_building"=0, "thief_building"=0,'
                ' "trade_building"=0, "adventure_building"=0 WHERE "name"=$2;',
                ctx.character_data["guild"],
                city,
            )
            await conn.execute('DELETE FROM defenses WHERE "city"=$1;', city)
            await self.bot.clear_city_guards(city=city, conn=conn)
            await self.bot.clear_city_guard_pet(city=city, conn=conn)
        conquest_note = ""
        if gold_lost and defending_guild_name:
            conquest_note = _(
                "\n\n**{guild}** lost **${gold}** from vault reserves above its base cap."
            ).format(guild=defending_guild_name, gold=gold_lost)
        await ctx.send(
            _(
                "Your alliance now rules **{city}**. You should immediately buy"
                " defenses or assign guards. You have **15 minutes** to prepare before"
                " others can occupy the city!{conquest_note}"
            ).format(city=city, conquest_note=conquest_note)
        )
        await self.bot.redis.execute_command(
            "SET", f"city:{city}:occ", ctx.character_data["guild"], "EX", 600
        )
        await self.bot.public_log(
            f"**{city}** was occupied by {ctx.author}'s alliance."
        )

    @alliance_cooldown(86400)
    @is_alliance_leader()
    @alliance.command(brief=_("Attack a city"))
    @locale_doc
    async def attack(self, ctx: Context, *, city: str.title) -> None:
        _(
            """`<city>` - The name of a city. You can check the city names with `{prefix}cities`

            Attack a city, reducing its defenses to potentially take it over.
            Attacking a city activates a grace period of 12 hours, during which time it cannot be attacked again.
            Initiating an attack costs the alliance leader's guild money, depending on the buildings in the defending city.

            When using this command, the bot sends a message with a button used to join the attack. At least 3 available members of your guild must join.
            Ten minutes after the message is sent, the alliance leader chooses the 3 frontline attackers and the battle starts with city-war scaled stats.

            During the attack, fortifications are destroyed first and city defenders fight after that. Assigned city guards cannot join attacks while they are stationed.
            The attacking party may bring one selected pet. Defending cities may station one selected pet alongside their defenders.

            If a defense, city guard, or stationed city pet reaches zero HP, it is removed from the city.

            If a city's fortifications and defenders were destroyed, your alliance can occupy the city right away (`{prefix}alliance occupy`)

            Only the alliance leader can use this command.
            (This command has a cooldown of 24 hours.)"""
        )
        if city not in self.city_configs:
            await self.bot.reset_alliance_cooldown(ctx)
            return await ctx.send(_("Invalid city."))

        if lock_until := await self._get_city_attack_lock():
            await self.bot.reset_alliance_cooldown(ctx)
            return await ctx.send(self._format_city_attack_lock(lock_until))

        if y := await self.bot.redis.execute_command("GET", f"city:{city}"):
            y = y.decode()
            if y == "cooldown":
                text = _("**{city}** has just been attacked. Have some mercy!").format(
                    city=city
                )
            else:
                text = _("**{city}** is already under attack.").format(city=city)
            await self.bot.reset_alliance_cooldown(ctx)
            return await ctx.send(text)

        battles_cog = self.bot.get_cog("Battles")
        if not battles_cog:
            await self.bot.reset_alliance_cooldown(ctx)
            return await ctx.send(_("The battle system is unavailable right now."))

        async with self.bot.pool.acquire() as conn:
            attacking_guild_name = await conn.fetchval(
                'SELECT name FROM guild WHERE "id"=$1;',
                ctx.character_data["guild"],
            )
            city_data = await conn.fetchrow('SELECT * FROM city WHERE "name"=$1;', city)
            if city_data["owner"] == ctx.character_data["guild"]:
                await self.bot.reset_alliance_cooldown(ctx)
                return await ctx.send(_("You cannot attack your own city."))

            defending_guild_name = await conn.fetchval(
                'SELECT g."name" FROM city c JOIN guild g ON g."id"=c."owner" WHERE c."name"=$1;',
                city,
            )
            defenses, inactive_defenses = await self._load_city_defenses(conn, city)
            guards = await self.bot.get_city_guards(city, conn=conn)
            guard_count = len(guards)
            guard_pet_assignment = await self.bot.get_city_guard_pet(city, conn=conn)
            if guard_pet_assignment and int(guard_pet_assignment["user_id"]) not in {
                int(guard["user_id"]) for guard in guards
            }:
                await self.bot.clear_city_guard_pet(city=city, conn=conn)
                guard_pet_assignment = None

            building_strength = (
                city_data["thief_building"]
                + city_data["raid_building"]
                + city_data["trade_building"]
                + city_data["adventure_building"]
            )
            building_percentage = building_strength / 40
            attacking_cost = int(building_percentage * 12500000)

            leading_guild_money = await conn.fetchval(
                'SELECT money FROM guild WHERE "id"=$1;',
                ctx.character_data["guild"],
            )

        if not defenses and not guard_count and not guard_pet_assignment:
            await self.bot.reset_alliance_cooldown(ctx)
            return await ctx.send(_("The city has no fortifications, guards, or stationed pet left already."))

        if leading_guild_money < attacking_cost:
            await self.bot.reset_alliance_cooldown(ctx)
            return await ctx.send(
                _(
                    "**{city}** has excellent infrastructure and attacking it would cost **${attacking_cost}**, but your guild only has **${leading_guild_money}**."
                ).format(
                    city=city,
                    attacking_cost=attacking_cost,
                    leading_guild_money=leading_guild_money,
                )
            )
        if not await ctx.confirm(
            _(
                "**{city}** has excellent infrastructure and attacking it would cost **${attacking_cost}**, do you want to proceed?"
            ).format(city=city, attacking_cost=attacking_cost)
        ):
            await self.bot.reset_alliance_cooldown(ctx)
            return

        attacking_users = []
        attack_pet_selection = None

        view = JoinView(
            Button(style=ButtonStyle.primary, label=_("Join the attack!")),
            message=_("You joined the attack."),
            timeout=60 * 10,
        )
        view.joined.add(ctx.author)

        await ctx.send(
            _(
                "**{user}** wants to attack **{city}** with **{guild_name}**."
                " At least **3** available guild members are required, and the leader will pick the **3** frontline attackers."
            ).format(
                user=ctx.author,
                city=city,
                guild_name=attacking_guild_name,
            ),
            view=view,
        )

        await asyncio.sleep(60 * 10)

        view.stop()

        async with self.bot.pool.acquire() as conn:
            for u in view.joined:
                profile = await conn.fetchrow(
                    'SELECT * FROM profile WHERE "user"=$1;', u.id
                )
                if not profile or profile["guild"] != ctx.character_data["guild"]:
                    continue
                if await self.bot.get_city_guard(u.id, conn=conn):
                    continue
                if u not in attacking_users:
                    attacking_users.append(u)

            defenses, inactive_defenses = await self._load_city_defenses(conn, city)
            guards = await self.bot.get_city_guards(city, conn=conn)
            guard_count = len(guards)
            guard_pet_assignment = await self.bot.get_city_guard_pet(city, conn=conn)
            if guard_pet_assignment and int(guard_pet_assignment["user_id"]) not in {
                int(guard["user_id"]) for guard in guards
            }:
                await self.bot.clear_city_guard_pet(city=city, conn=conn)
                guard_pet_assignment = None
            if not defenses and not guard_count and not guard_pet_assignment:
                await self.bot.reset_alliance_cooldown(ctx)
                return await ctx.send(_("The city lost its final defenders before the attack began."))
            if len(attacking_users) < 3:
                await self.bot.reset_alliance_cooldown(ctx)
                return await ctx.send(
                    _(
                        "You need at least **3** available members of your guild to attack a city. Assigned city guards cannot join."
                    )
                )
            if y := await self.bot.redis.execute_command("GET", f"city:{city}"):
                y = y.decode()
                if y == "cooldown":
                    text = _("**{city}** has just been attacked. Have some mercy!").format(
                        city=city
                    )
                else:
                    text = _("**{city}** is already under attack.").format(city=city)
                await self.bot.reset_alliance_cooldown(ctx)
                return await ctx.send(text)

            if lock_until := await self._get_city_attack_lock():
                await self.bot.reset_alliance_cooldown(ctx)
                return await ctx.send(self._format_city_attack_lock(lock_until))

            frontline_attackers = await self._select_city_attackers(
                ctx,
                attacking_users,
            )
            if (
                not frontline_attackers
                or len(frontline_attackers) < CITY_WAR_ATTACKER_LIMIT
            ):
                await self.bot.reset_alliance_cooldown(ctx)
                return await ctx.send(
                    _("No frontline attack party was locked in before selection timed out.")
                )

            attack_pet_selection = await self._select_attack_pet(
                ctx,
                frontline_attackers,
                conn,
            )

            leading_guild_money = await conn.fetchval(
                'SELECT money FROM guild WHERE "id"=$1;', ctx.character_data["guild"]
            )

            if leading_guild_money < attacking_cost:
                await self.bot.reset_alliance_cooldown(ctx)
                return await ctx.send(
                    _(
                        "The money for attacking the city has been spent in the meantime."
                    )
                )

            await conn.execute(
                'UPDATE guild SET "money"="money"-$1 WHERE "id"=$2;',
                attacking_cost,
                ctx.character_data["guild"],
            )

        attacker_combatants = []
        attacker_combatants_by_user_id: dict[int, Combatant] = {}
        for attacker in frontline_attackers:
            combatant = await battles_cog.battle_factory.create_player_combatant(
                ctx,
                attacker,
                include_pet=False,
            )
            self._apply_city_war_scaling(combatant)
            combatant.user_id = attacker.id
            attacker_combatants.append(combatant)
            attacker_combatants_by_user_id[attacker.id] = combatant

        attack_pet_combatant = None
        if attack_pet_selection:
            attack_pet_combatant = await battles_cog.battle_factory.pet_ext.get_pet_combatant(
                ctx,
                attack_pet_selection["owner"],
                pet_id=int(attack_pet_selection["pet"]["id"]),
            )
            if attack_pet_combatant:
                self._apply_city_war_scaling(attack_pet_combatant)
                self._cap_city_war_pet(
                    attack_pet_combatant,
                    attacker_combatants_by_user_id.get(
                        attack_pet_selection["owner"].id
                    ),
                )
                attacker_combatants.append(attack_pet_combatant)

        async with self.bot.pool.acquire() as conn:
            structure_combatants = await self._build_city_structure_combatants(defenses)
            guard_combatants = await self._build_city_guard_combatants(ctx, city, conn)
            guard_combatants_by_user_id = {
                int(combatant.city_guard_user_id): combatant
                for combatant in guard_combatants
            }
            guard_pet_combatant = await self._build_city_guard_pet_combatant(
                ctx,
                city,
                conn,
                owner_combatants=guard_combatants_by_user_id,
            )

        defender_combatants = structure_combatants + guard_combatants
        if guard_pet_combatant:
            defender_combatants.append(guard_pet_combatant)

        if not defender_combatants:
            async with self.bot.pool.acquire() as conn:
                await conn.execute(
                    'UPDATE guild SET "money"="money"+$1 WHERE "id"=$2;',
                    attacking_cost,
                    ctx.character_data["guild"],
                )
            await self.bot.reset_alliance_cooldown(ctx)
            return await ctx.send(_("The city lost its final defenders before the battle could start."))

        await self.bot.redis.execute_command(
            "SET", f"city:{city}", "under attack", "EX", 7200
        )

        attack_pet_text = ""
        if attack_pet_selection and attack_pet_combatant:
            attack_pet_text = _(
                "\nAttacking pet: **{pet}** (Owner: **{owner}**)"
            ).format(
                pet=attack_pet_selection["pet"]["name"],
                owner=attack_pet_selection["owner"].display_name,
            )
        guard_pet_text = ""
        if guard_pet_combatant:
            guard_pet_text = _("\nDefending pet: **{pet}**").format(
                pet=guard_pet_combatant.name
            )

        await ctx.send(
            _(
                "Attack on **{city}** starting with **{amount}** attackers against"
                " **{defense_count}** fortifications, **{guard_count}** guards, and **{guard_pet_count}** stationed pet.{attack_pet_text}{guard_pet_text}"
            ).format(
                city=city,
                amount=len(frontline_attackers),
                defense_count=len(structure_combatants),
                guard_count=len(guard_combatants),
                guard_pet_count=1 if guard_pet_combatant else 0,
                attack_pet_text=attack_pet_text,
                guard_pet_text=guard_pet_text,
            )
        )
        await self.bot.public_log(
            f"**{attacking_guild_name}** is attacking **{city}** with {len(frontline_attackers)}"
            f" attackers, {len(structure_combatants)} fortifications, {len(guard_combatants)}"
            f" guards, and {1 if guard_pet_combatant else 0} stationed pet."
        )

        attacker_team = Team("Attackers", attacker_combatants)
        defender_team = Team("Defenders", defender_combatants)
        battle = await battles_cog.battle_factory.create_city_war_battle(
            ctx,
            teams=[attacker_team, defender_team],
            city=city,
            attacking_guild_name=attacking_guild_name,
            defending_guild_name=defending_guild_name,
            allow_pets=True,
            max_duration=timedelta(minutes=15),
        )

        await battle.start_battle()
        while not await battle.is_battle_over():
            await battle.process_turn()
        result = await battle.end_battle()

        async with self.bot.pool.acquire() as conn:
            await self._sync_city_war_battle_state(battle, conn)

        await self.bot.redis.execute_command(
            "SET", f"city:{city}", "cooldown", "EX", 3600 * 12
        )

        if result["attackers_won"]:
            await ctx.send(
                _("**{guild_name}** destroyed all defenders in **{city}**!").format(
                    guild_name=attacking_guild_name,
                    city=city,
                )
            )
            await self.bot.public_log(
                f"**{attacking_guild_name}** destroyed all defenders in **{city}**!"
            )
        else:
            await ctx.send(
                _("**{guild_name}** failed to break **{city}**'s defenses!").format(
                    guild_name=attacking_guild_name,
                    city=city,
                )
            )
            await self.bot.public_log(
                f"**{attacking_guild_name}** failed to break **{city}**'s defenses!"
            )

    @has_char()
    @alliance.command(
        aliases=["cooldowns", "t", "cds"], brief=_("Lists alliance-specific cooldowns")
    )
    @locale_doc
    async def timers(self, ctx: Context) -> None:
        _(
            """Lists alliance-specific cooldowns, meaning all alliance members have these cooldowns and cannot use the commands."""
        )
        alliance = await self.bot.pool.fetchval(
            'SELECT alliance FROM guild WHERE "id"=$1;',
            ctx.character_data["guild"],
        )
        cooldowns = await self.bot.redis.execute_command(
            "KEYS", f"alliancecd:{alliance}:*"
        )
        if not cooldowns:
            return await ctx.send(
                _("Your alliance does not have any active cooldown at the moment.")
            )
        timers = _("Commands on cooldown:")
        for key in cooldowns:
            key = key.decode()
            cooldown = await self.bot.redis.execute_command("TTL", key)
            cmd = key.replace(f"alliancecd:{alliance}:", "")
            text = _("{cmd} is on cooldown and will be available after {time}").format(
                cmd=cmd, time=timedelta(seconds=int(cooldown))
            )
            timers = f"{timers}\n{text}"
        await ctx.send(f"```{timers}```")


async def setup(bot: Bot):
    await bot.add_cog(Alliance(bot))

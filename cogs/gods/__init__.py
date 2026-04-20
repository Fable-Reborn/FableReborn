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
import json
import re

from datetime import timedelta
from decimal import Decimal
from io import BytesIO
from pathlib import Path

import discord

from discord.ext import commands
from discord.http import handle_message_parameters

from classes.classes import Ritualist, from_string
from classes.converters import IntGreaterThan
from cogs.shard_communication import next_day_cooldown
from cogs.shard_communication import user_on_cooldown as user_cooldown
from utils import random
from utils.checks import has_char, has_god, has_no_god, is_gm
from utils.i18n import _, locale_doc


SPIN_GODLESS_KEY = "Godless"
SPIN_CONFIG_PATH = Path(__file__).with_name("spin_config.json")
DEFAULT_SPIN_COOLDOWN_SECONDS = 86400
SPIN_MAX_POOL_ENTRIES = 1000
DEFAULT_SPIN_TEMPLATE = (
    "{choose:Fortune Crate;500k Gold;50k XP;300k Gold;Legendary Crate;"
    "Materials Crate;Fortune Crate;Common Crate;Rare Crate;350k Gold;"
    "15k XP;Weapon token;30k favor;Divine Crate;mystery crate;Magic Crate;"
    "Fortune Crate;25k XP;30k XP;Legendary Crate;Rare Crate;Magic Crate;"
    "Divine Crate;Common Crate;200k Gold;150k Gold;Fortune Crate;"
    "Divine Crate;25k XP;Blank;100k XP;50k XP;Fortune Crate;350k Gold;"
    "Materials Crate;50k XP;300k Gold;75k XP;Fortune Crate;5000 XP;"
    "Divine Crate;50k XP;100k Gold;15k XP}\n"
    "{user} got {choice}!"
)


def _spin_pool_text_from_template(pool):
    match = re.search(r"\{choose:(.*?)\}", pool, flags=re.I | re.S)
    if match:
        return match.group(1)
    return pool


DEFAULT_SPIN_POOL = [
    reward.strip()
    for reward in _spin_pool_text_from_template(DEFAULT_SPIN_TEMPLATE).split(";")
    if reward.strip()
]
SPIN_CRATE_COLUMNS = {
    "common": "crates_common",
    "uncommon": "crates_uncommon",
    "rare": "crates_rare",
    "magic": "crates_magic",
    "legendary": "crates_legendary",
    "fortune": "crates_fortune",
    "divine": "crates_divine",
    "materials": "crates_materials",
    "mystery": "crates_mystery",
}


class SpinConfigGodSelect(discord.ui.Select):
    def __init__(self, view):
        self.panel_view = view
        god_keys = view.cog._spin_config_god_keys()
        if view.selected_god not in god_keys:
            god_keys.insert(0, view.selected_god)

        selected_first = []
        if view.selected_god in god_keys:
            selected_first.append(view.selected_god)
        option_gods = selected_first + [
            god for god in god_keys if god not in selected_first
        ]
        self.option_gods = option_gods[:25]

        options = []
        for index, god in enumerate(self.option_gods):
            config = view.cog._get_spin_config_for_god(god)
            source = "custom" if god in view.cog.spin_config else "default"
            unique_rewards = view.cog._spin_pool_unique_count(config["pool"])
            options.append(
                discord.SelectOption(
                    label=god[:100],
                    value=str(index),
                    description=(
                        f"{config['cooldown_seconds']}s, "
                        f"weight {len(config['pool'])}, "
                        f"{unique_rewards} types ({source})"
                    )[:100],
                    default=god == view.selected_god,
                )
            )

        super().__init__(
            placeholder="Choose a god",
            min_values=1,
            max_values=1,
            options=options,
            row=0,
        )

    async def callback(self, interaction: discord.Interaction):
        selected_index = int(self.values[0])
        selected_god = self.option_gods[selected_index]
        fresh_view = SpinConfigPanelView(
            self.panel_view.cog,
            self.panel_view.author_id,
            selected_god,
        )
        fresh_view.message = interaction.message
        await interaction.response.edit_message(
            embed=self.panel_view.cog._build_spin_config_embed(selected_god),
            view=fresh_view,
        )
        self.panel_view.stop()


class SpinCooldownModal(discord.ui.Modal):
    def __init__(self, panel_view):
        super().__init__(title="Set Spin Cooldown")
        self.panel_view = panel_view
        config = panel_view.cog._get_spin_config_for_god(panel_view.selected_god)
        self.cooldown_input = discord.ui.TextInput(
            label="Cooldown seconds",
            default=str(config["cooldown_seconds"]),
            placeholder="86400",
            required=True,
            max_length=10,
        )
        self.add_item(self.cooldown_input)

    async def on_submit(self, interaction: discord.Interaction):
        if interaction.user.id != self.panel_view.author_id:
            return await interaction.response.send_message(
                "This spin config menu is not for you.",
                ephemeral=True,
            )

        try:
            cooldown_seconds = int(self.cooldown_input.value.strip())
        except ValueError:
            return await interaction.response.send_message(
                "Cooldown must be a whole number of seconds.",
                ephemeral=True,
            )
        if cooldown_seconds < 0:
            return await interaction.response.send_message(
                "Cooldown must be 0 seconds or greater.",
                ephemeral=True,
            )

        await interaction.response.defer(ephemeral=True)
        await self.panel_view.cog._update_spin_cooldown(
            interaction,
            self.panel_view.selected_god,
            cooldown_seconds,
        )
        await self.panel_view.refresh_message()
        await interaction.followup.send(
            (
                f"Set {self.panel_view.selected_god} spin cooldown "
                f"to {cooldown_seconds} seconds."
            ),
            ephemeral=True,
        )


class SpinPoolModal(discord.ui.Modal):
    def __init__(self, panel_view):
        super().__init__(title="Set Spin Pool")
        self.panel_view = panel_view
        config = panel_view.cog._get_spin_config_for_god(panel_view.selected_god)
        self.pool_input = discord.ui.TextInput(
            label="Reward weights, one per line",
            default=panel_view.cog._format_spin_pool_for_edit(config["pool"]),
            placeholder="Fortune Crate: 6\n500k Gold: 1\nBlank: 1",
            style=discord.TextStyle.paragraph,
            required=True,
            max_length=4000,
        )
        self.add_item(self.pool_input)

    async def on_submit(self, interaction: discord.Interaction):
        if interaction.user.id != self.panel_view.author_id:
            return await interaction.response.send_message(
                "This spin config menu is not for you.",
                ephemeral=True,
            )

        try:
            rewards = self.panel_view.cog._parse_spin_pool(self.pool_input.value)
        except commands.BadArgument as error:
            return await interaction.response.send_message(
                str(error),
                ephemeral=True,
            )

        await interaction.response.defer(ephemeral=True)
        await self.panel_view.cog._update_spin_pool(
            interaction,
            self.panel_view.selected_god,
            rewards,
        )
        await self.panel_view.refresh_message()
        await interaction.followup.send(
            (
                f"Set {self.panel_view.selected_god} spin reward pool "
                f"to {len(rewards)} entries."
            ),
            ephemeral=True,
        )


class SpinConfigPanelView(discord.ui.View):
    def __init__(self, cog, author_id, selected_god=None):
        super().__init__(timeout=180)
        self.cog = cog
        self.author_id = author_id
        self.selected_god = selected_god or SPIN_GODLESS_KEY
        self.message = None
        self.add_item(SpinConfigGodSelect(self))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.author_id:
            return True
        await interaction.response.send_message(
            "This spin config menu is not for you.",
            ephemeral=True,
        )
        return False

    async def refresh_message(self):
        if self.message is None:
            return
        fresh_view = SpinConfigPanelView(
            self.cog,
            self.author_id,
            self.selected_god,
        )
        fresh_view.message = self.message
        await self.message.edit(
            embed=self.cog._build_spin_config_embed(self.selected_god),
            view=fresh_view,
        )
        self.stop()

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        if self.message is None:
            return
        try:
            await self.message.edit(view=self)
        except discord.HTTPException:
            pass

    @discord.ui.button(label="Set Cooldown", style=discord.ButtonStyle.primary, row=1)
    async def set_cooldown(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ):
        await interaction.response.send_modal(SpinCooldownModal(self))

    @discord.ui.button(label="Set Pool", style=discord.ButtonStyle.primary, row=1)
    async def set_pool(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ):
        await interaction.response.send_modal(SpinPoolModal(self))

    @discord.ui.button(label="Validate", style=discord.ButtonStyle.secondary, row=1)
    async def validate_config(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ):
        config = self.cog._get_spin_config_for_god(self.selected_god)
        errors = self.cog._validate_spin_pool(config["pool"])
        if errors:
            return await interaction.response.send_message(
                "Invalid spin pool:\n" + "\n".join(f"- {error}" for error in errors),
                ephemeral=True,
            )

        await interaction.response.send_message(
            (
                f"{self.selected_god} spin pool is valid.\n"
                f"Total weight: **{len(config['pool'])}**\n"
                f"Reward types: **{self.cog._spin_pool_unique_count(config['pool'])}**"
            ),
            ephemeral=True,
        )

    @discord.ui.button(label="Reset", style=discord.ButtonStyle.danger, row=1)
    async def reset_config(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ):
        before = self.cog._get_spin_config_for_god(self.selected_god)
        self.cog.spin_config.pop(self.selected_god, None)
        self.cog._save_spin_config()
        after = self.cog._get_spin_config_for_god(self.selected_god)
        await self.cog._log_spin_config_change(
            interaction,
            "reset",
            self.selected_god,
            before,
            after,
        )
        fresh_view = SpinConfigPanelView(
            self.cog,
            self.author_id,
            self.selected_god,
        )
        fresh_view.message = interaction.message
        await interaction.response.edit_message(
            embed=self.cog._build_spin_config_embed(self.selected_god),
            view=fresh_view,
        )
        self.stop()


class Gods(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.bot.gods = {god["user"]: god for god in self.bot.config.gods}
        self.spin_config = self._load_spin_config()
        ids_section = getattr(self.bot.config, "ids", None)
        gods_ids = getattr(ids_section, "gods", {}) if ids_section else {}
        if not isinstance(gods_ids, dict):
            gods_ids = {}
        support_roles = gods_ids.get("support_god_role_ids", {})
        primary_roles = gods_ids.get("primary_god_role_ids", {})
        self.support_god_role_ids = support_roles if isinstance(support_roles, dict) else {}
        self.primary_god_role_ids = primary_roles if isinstance(primary_roles, dict) else {}
        self.godless_role_id = gods_ids.get("godless_role_id")

    def _load_spin_config(self):
        if not SPIN_CONFIG_PATH.exists():
            return {}
        try:
            data = json.loads(SPIN_CONFIG_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        if not isinstance(data, dict):
            return {}

        config = {}
        for god, settings in data.items():
            if not isinstance(settings, dict):
                continue
            god_key = str(god).strip() or SPIN_GODLESS_KEY
            pool = settings.get("pool", DEFAULT_SPIN_POOL)
            if not isinstance(pool, list):
                pool = DEFAULT_SPIN_POOL
            pool = [str(item).strip() for item in pool if str(item).strip()]
            if not pool:
                pool = list(DEFAULT_SPIN_POOL)
            elif self._validate_spin_pool(pool):
                pool = list(DEFAULT_SPIN_POOL)
            try:
                cooldown_seconds = int(
                    settings.get("cooldown_seconds", DEFAULT_SPIN_COOLDOWN_SECONDS)
                )
            except (TypeError, ValueError):
                cooldown_seconds = DEFAULT_SPIN_COOLDOWN_SECONDS
            config[god_key] = {
                "cooldown_seconds": max(0, cooldown_seconds),
                "pool": pool,
            }
        return config

    def _save_spin_config(self):
        SPIN_CONFIG_PATH.write_text(
            json.dumps(self.spin_config, indent=2, sort_keys=True),
            encoding="utf-8",
        )

    def _canonical_spin_god(self, god):
        if god is None:
            return SPIN_GODLESS_KEY
        cleaned = str(god).strip()
        if not cleaned or cleaned.lower() in {
            "godless",
            "no god",
            "nogod",
            "none",
            "null",
        }:
            return SPIN_GODLESS_KEY

        for god_data in self.bot.gods.values():
            god_name = str(god_data.get("name", "")).strip()
            if cleaned.lower() == god_name.lower():
                return god_name

        for configured_god in self.spin_config:
            if cleaned.lower() == configured_god.lower():
                return configured_god

        raise commands.BadArgument(f"Unknown god: {cleaned}")

    def _spin_config_god_keys(self):
        god_keys = {SPIN_GODLESS_KEY}
        god_keys.update(self.spin_config)
        god_keys.update(
            str(god_data.get("name", "")).strip()
            for god_data in self.bot.gods.values()
            if str(god_data.get("name", "")).strip()
        )
        ordered = [SPIN_GODLESS_KEY]
        ordered.extend(sorted(god for god in god_keys if god != SPIN_GODLESS_KEY))
        return ordered

    def _get_spin_config_for_god(self, god):
        configured = self.spin_config.get(god, {})
        pool = configured.get("pool") or DEFAULT_SPIN_POOL
        return {
            "cooldown_seconds": int(
                configured.get("cooldown_seconds", DEFAULT_SPIN_COOLDOWN_SECONDS)
            ),
            "pool": list(pool),
        }

    def _build_spin_config_embed(self, god):
        config = self._get_spin_config_for_god(god)
        source = "custom" if god in self.spin_config else "default"
        unique_rewards = self._spin_pool_unique_count(config["pool"])
        embed = discord.Embed(
            title=f"Spin Config: {god}",
            color=self.bot.config.game.primary_colour,
        )
        embed.add_field(name="Source", value=source, inline=True)
        embed.add_field(
            name="Cooldown",
            value=f"{config['cooldown_seconds']} seconds",
            inline=True,
        )
        embed.add_field(
            name="Total Weight",
            value=str(len(config["pool"])),
            inline=True,
        )
        embed.add_field(
            name="Reward Types",
            value=str(unique_rewards),
            inline=True,
        )
        embed.add_field(
            name="Reward Odds",
            value=self._format_spin_pool_summary(config["pool"], 1024),
            inline=False,
        )
        embed.set_footer(
            text="Set Pool accepts 'Reward: weight', one per line. Example: 50 Dragon Coins: 1."
        )
        return embed

    def _parse_spin_pool(self, pool):
        pool = _spin_pool_text_from_template(pool.strip())
        rewards = []
        unsupported = []
        total_entries = 0
        for entry in re.split(r"[;\r\n]+", pool):
            entry = entry.strip()
            if not entry:
                continue

            reward, count = self._parse_spin_pool_entry(entry)
            if self._spin_reward_descriptor(reward) is None:
                unsupported.append(reward)
                continue

            total_entries += count
            if total_entries > SPIN_MAX_POOL_ENTRIES:
                raise commands.BadArgument(
                    (
                        "Reward pool total weight cannot be more than "
                        f"{SPIN_MAX_POOL_ENTRIES}."
                    )
                )
            rewards.extend([reward] * count)

        if unsupported:
            raise commands.BadArgument(
                "Unsupported spin rewards: "
                + ", ".join(unsupported[:10])
                + ". Use rewards like `500k Gold`, `50 Dragon Coins`, "
                "`Fortune Crate`, `Weapon token`, or `Blank`."
            )
        if not rewards:
            raise commands.BadArgument("Reward pool cannot be empty.")
        return rewards

    def _parse_spin_pool_entry(self, entry):
        leading_count = re.fullmatch(r"(\d+)\s*x\s+(.+)", entry, flags=re.I)
        if leading_count:
            count = int(leading_count.group(1))
            reward = leading_count.group(2).strip()
        else:
            trailing_count = re.fullmatch(
                r"(.+?)\s*(?:x|\*|:|\|)\s*(\d+)",
                entry,
                flags=re.I,
            )
            if trailing_count:
                reward = trailing_count.group(1).strip()
                count = int(trailing_count.group(2))
            else:
                reward = entry
                count = 1

        if count <= 0:
            raise commands.BadArgument("Reward counts must be greater than 0.")
        return reward, count

    def _validate_spin_pool(self, pool):
        errors = []
        if not isinstance(pool, list):
            return ["Pool must be a list of reward entries."]
        if not pool:
            return ["Pool cannot be empty."]
        if len(pool) > SPIN_MAX_POOL_ENTRIES:
            errors.append(
                f"Total weight cannot be more than {SPIN_MAX_POOL_ENTRIES}."
            )

        unsupported = []
        for reward in pool:
            reward = str(reward).strip()
            if not reward:
                unsupported.append("<blank entry>")
            elif self._spin_reward_descriptor(reward) is None:
                unsupported.append(reward)

        if unsupported:
            errors.append(
                "Unsupported rewards: "
                + ", ".join(unsupported[:10])
                + ". Supported examples: `500k Gold`, `50 Dragon Coins`, "
                "`Fortune Crate`, `Weapon token`, `Blank`."
            )
        return errors

    def _spin_reward_descriptor(self, reward):
        reward_text = str(reward).strip()
        normalized = " ".join(reward_text.lower().replace(",", "").split())
        if normalized == "blank":
            return ("blank", None)
        if normalized in {"weapon token", "weapon type token", "weapontoken"}:
            return ("weapon_token", 1)
        if normalized in {
            "dragon coin",
            "dragon coins",
            "dragoncoin",
            "dragoncoins",
            "dc",
        }:
            return ("dragoncoins", 1)

        amount_match = re.fullmatch(
            r"(\d+)(k?)\s+"
            r"(gold|xp|favor|favour|dragon coins?|dragoncoins?|dc)",
            normalized,
        )
        if amount_match:
            amount = int(amount_match.group(1))
            if amount_match.group(2) == "k":
                amount *= 1000
            if amount <= 0:
                return None
            reward_type = amount_match.group(3)
            if reward_type == "favour":
                reward_type = "favor"
            elif reward_type in {
                "dragon coin",
                "dragon coins",
                "dragoncoin",
                "dragoncoins",
                "dc",
            }:
                reward_type = "dragoncoins"
            return (reward_type, amount)

        crate_match = re.fullmatch(r"([a-z]+)\s+crate", normalized)
        if crate_match:
            rarity = crate_match.group(1)
            if rarity in SPIN_CRATE_COLUMNS:
                return ("crate", rarity)
        return None

    def _spin_pool_counts(self, pool):
        counts = {}
        for reward in pool:
            counts[reward] = counts.get(reward, 0) + 1
        return counts

    def _spin_pool_unique_count(self, pool):
        return len(self._spin_pool_counts(pool))

    def _format_spin_pool_for_edit(self, pool):
        pool_text = "\n".join(
            f"{reward}: {count}"
            for reward, count in self._spin_pool_counts(pool).items()
        )
        if len(pool_text) <= 4000:
            return pool_text

        lines = []
        current_length = 0
        for reward, count in self._spin_pool_counts(pool).items():
            line = f"{reward}: {count}"
            next_length = current_length + len(line) + (1 if lines else 0)
            if next_length > 4000:
                break
            lines.append(line)
            current_length = next_length
        return "\n".join(lines)

    def _format_spin_pool_summary(self, pool, max_chars=1000):
        if not pool:
            return "No rewards configured."

        counts = self._spin_pool_counts(pool)
        total = len(pool)
        lines = []
        for reward, count in counts.items():
            percentage = count / total * 100
            line = f"{reward} - weight {count} ({percentage:.1f}%)"
            projected = "\n".join([*lines, line])
            if len(projected) > max_chars:
                remaining = len(counts) - len(lines)
                suffix = f"... and {remaining} more reward types."
                while lines and len("\n".join([*lines, suffix])) > max_chars:
                    lines.pop()
                    remaining += 1
                    suffix = f"... and {remaining} more reward types."
                lines.append(suffix)
                break
            lines.append(line)
        return "\n".join(lines)

    def _format_spin_config_for_log(self, config):
        pool = config["pool"]
        pool_summary = self._format_spin_pool_summary(pool, 650).replace("\n", "; ")
        return (
            f"cooldown={config['cooldown_seconds']}s, "
            f"pool_count={len(pool)}, "
            f"unique_rewards={self._spin_pool_unique_count(pool)}, "
            f"pool_summary={pool_summary}"
        )

    async def _log_spin_config_change(self, ctx, action, god, before, after):
        gm_log_channel = getattr(self.bot.config.game, "gm_log_channel", None)
        if not gm_log_channel:
            return
        source = ctx
        actor = getattr(source, "author", None) or getattr(source, "user", None)
        actor_name = str(actor) if actor is not None else "Unknown"
        actor_id = getattr(actor, "id", "unknown")
        message = getattr(source, "message", None)
        jump_url = getattr(message, "jump_url", None)
        reason = f"<{jump_url}>" if jump_url else "Interaction"
        content = (
            "**Spin config updated**\n"
            f"GM: **{actor_name}** (`{actor_id}`)\n"
            f"God: **{god}**\n"
            f"Action: {action}\n"
            f"Before: {self._format_spin_config_for_log(before)}\n"
            f"After: {self._format_spin_config_for_log(after)}\n"
            f"Reason: {reason}"
        )
        with handle_message_parameters(content=content[:2000]) as params:
            await self.bot.http.send_message(gm_log_channel, params=params)

    async def _update_spin_cooldown(self, source, god, cooldown_seconds):
        before = self._get_spin_config_for_god(god)
        after = {
            "cooldown_seconds": cooldown_seconds,
            "pool": list(before["pool"]),
        }
        self.spin_config[god] = after
        self._save_spin_config()
        await self._log_spin_config_change(source, "cooldown", god, before, after)
        return before, after

    async def _update_spin_pool(self, source, god, rewards):
        errors = self._validate_spin_pool(rewards)
        if errors:
            raise commands.BadArgument("\n".join(errors))

        before = self._get_spin_config_for_god(god)
        after = {
            "cooldown_seconds": before["cooldown_seconds"],
            "pool": list(rewards),
        }
        self.spin_config[god] = after
        self._save_spin_config()
        await self._log_spin_config_change(source, "pool", god, before, after)
        return before, after

    async def _apply_spin_reward(self, ctx, reward):
        descriptor = self._spin_reward_descriptor(reward)
        if descriptor is None:
            raise commands.BadArgument(f"Unsupported spin reward: {reward}")

        kind, value = descriptor
        if kind == "blank":
            return

        async with self.bot.pool.acquire() as conn:
            if kind == "gold":
                await conn.execute(
                    'UPDATE profile SET "money"="money"+$1 WHERE "user"=$2;',
                    value,
                    ctx.author.id,
                )
                await self.bot.log_transaction(
                    ctx,
                    from_=1,
                    to=ctx.author.id,
                    subject="money",
                    data={"Amount": value, "Source": "spin", "Reward": reward},
                    conn=conn,
                )
            elif kind == "xp":
                before_xp = await conn.fetchval(
                    'SELECT "xp" FROM profile WHERE "user"=$1;',
                    ctx.author.id,
                )
                await conn.execute(
                    'UPDATE profile SET "xp"="xp"+$1::BIGINT WHERE "user"=$2;',
                    value,
                    ctx.author.id,
                )
                after_xp = int(before_xp) + value if before_xp is not None else None
                await self.bot.log_xp_watch_event(
                    ctx=ctx,
                    user_id=ctx.author.id,
                    delta=value,
                    source="gods.spin",
                    details={"reward": reward},
                    before_xp=before_xp,
                    after_xp=after_xp,
                    conn=conn,
                )
            elif kind == "favor":
                await conn.execute(
                    'UPDATE profile SET "favor"="favor"+$1 WHERE "user"=$2;',
                    value,
                    ctx.author.id,
                )
            elif kind == "dragoncoins":
                await conn.execute(
                    'UPDATE profile SET "dragoncoins"="dragoncoins"+$1 WHERE "user"=$2;',
                    value,
                    ctx.author.id,
                )
            elif kind == "crate":
                column = SPIN_CRATE_COLUMNS[value]
                await conn.execute(
                    f'UPDATE profile SET "{column}"="{column}"+1 WHERE "user"=$1;',
                    ctx.author.id,
                )
                await self.bot.log_transaction(
                    ctx,
                    from_=1,
                    to=ctx.author.id,
                    subject="crates",
                    data={"Rarity": value, "Amount": 1, "Source": "spin", "Reward": reward},
                    conn=conn,
                )
            elif kind == "weapon_token":
                await conn.execute(
                    'UPDATE profile SET "weapontoken"="weapontoken"+$1 WHERE "user"=$2;',
                    value,
                    ctx.author.id,
                )

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        """Assign Godless role in support server if the user is Godless."""
        support_server_id = self.bot.config.game.support_server_id
        if support_server_id is None or member.guild.id != support_server_id:
            return

        try:
            profile = await self.bot.pool.fetchrow(
                'SELECT god, reset_points FROM profile WHERE "user"=$1;',
                member.id,
            )
            if not profile:
                return

            # Godless users are those with no god and reset_points < 0 (see unfollow)
            if profile["god"] is None and profile["reset_points"] is not None and profile["reset_points"] < 0:
                godless_role_id = self.godless_role_id
                god_roles = self.support_god_role_ids

                # Remove any god roles in the support server
                for role_id in god_roles.values():
                    role = member.guild.get_role(role_id)
                    if role and role in member.roles:
                        await member.remove_roles(role)

                godless_role = member.guild.get_role(godless_role_id)
                if godless_role and godless_role not in member.roles:
                    await member.add_roles(godless_role)
        except Exception:
            # Avoid breaking joins due to role or DB issues
            return

    @has_char()
    @commands.command(brief=_("Spin for a reward from your god's pool"))
    @locale_doc
    async def spin(self, ctx):
        _(
            """Spin for a random reward from the reward pool configured for your current God.

            Godless players use the Godless reward pool.
            """
        )
        god = self._canonical_spin_god(ctx.character_data["god"])
        config = self._get_spin_config_for_god(god)
        cooldown_seconds = max(0, int(config["cooldown_seconds"]))
        cooldown_key = f"cd:{ctx.author.id}:spin"

        if cooldown_seconds > 0:
            cooldown_set = await self.bot.redis.execute_command(
                "SET",
                cooldown_key,
                "spin",
                "EX",
                cooldown_seconds,
                "NX",
            )
            if not cooldown_set:
                ttl = await self.bot.redis.execute_command("TTL", cooldown_key)
                if ttl != -2:
                    return await ctx.send(
                        _("You are on cooldown. Try again in {time}.").format(
                            time=timedelta(seconds=max(0, int(ttl)))
                        )
                    )

        reward = random.choice(config["pool"])
        try:
            await self._apply_spin_reward(ctx, reward)
        except commands.BadArgument as error:
            if cooldown_seconds > 0:
                await self.bot.redis.execute_command("DEL", cooldown_key)
            return await ctx.send(str(error))
        except Exception:
            if cooldown_seconds > 0:
                await self.bot.redis.execute_command("DEL", cooldown_key)
            raise

        await ctx.send(
            _("{user} got {choice}!").format(
                user=ctx.author.mention,
                choice=reward,
            )
        )

    @is_gm()
    @commands.group(
        name="spinconfig",
        aliases=["spincfg"],
        hidden=True,
        invoke_without_command=True,
    )
    async def spinconfig(self, ctx, *, god: str = None):
        if ctx.invoked_subcommand is not None:
            return

        god_key = SPIN_GODLESS_KEY
        if god is not None:
            try:
                god_key = self._canonical_spin_god(god)
            except commands.BadArgument as error:
                return await ctx.send(str(error))

        view = SpinConfigPanelView(self, ctx.author.id, god_key)
        view.message = await ctx.send(
            embed=self._build_spin_config_embed(god_key),
            view=view,
        )

    @is_gm()
    @spinconfig.command(name="cooldown", aliases=["cd"], hidden=True)
    async def spinconfig_cooldown(self, ctx, god: str, cooldown_seconds: int):
        if cooldown_seconds < 0:
            return await ctx.send("Cooldown must be 0 seconds or greater.")

        try:
            god_key = self._canonical_spin_god(god)
        except commands.BadArgument as error:
            return await ctx.send(str(error))
        await self._update_spin_cooldown(ctx, god_key, cooldown_seconds)
        await ctx.send(f"Set {god_key} spin cooldown to {cooldown_seconds} seconds.")

    @is_gm()
    @spinconfig.command(name="pool", aliases=["rewards"], hidden=True)
    async def spinconfig_pool(self, ctx, god: str, *, pool: str):
        try:
            god_key = self._canonical_spin_god(god)
            rewards = self._parse_spin_pool(pool)
            await self._update_spin_pool(ctx, god_key, rewards)
        except commands.BadArgument as error:
            return await ctx.send(str(error))
        await ctx.send(f"Set {god_key} spin reward pool to {len(rewards)} entries.")

    @is_gm()
    @spinconfig.command(name="reset", aliases=["default"], hidden=True)
    async def spinconfig_reset(self, ctx, god: str):
        try:
            god_key = self._canonical_spin_god(god)
        except commands.BadArgument as error:
            return await ctx.send(str(error))
        before = self._get_spin_config_for_god(god_key)
        self.spin_config.pop(god_key, None)
        self._save_spin_config()
        after = self._get_spin_config_for_god(god_key)
        await self._log_spin_config_change(ctx, "reset", god_key, before, after)
        await ctx.send(f"Reset {god_key} spin config to the default.")

    @has_god()
    @has_char()
    @user_cooldown(180)
    @commands.command(brief=_("Sacrifice loot for favor"))
    @locale_doc
    async def sacrifice(self, ctx, *loot_ids: int):
        _(
            """`[loot_ids...]` - The loot IDs to sacrifice, can be one or multiple IDs separated by space; defaults to all loot

            Sacrifice loot to your God to gain favor points.

            If no loot IDs are given with this command, all loot you own will be sacrificed.
            You can see your current loot with `{prefix}loot`.

            Only players, who follow a God can use this command."""
        )
        async with self.bot.pool.acquire() as conn:
            if not loot_ids:
                value, count = await conn.fetchval(
                    'SELECT (SUM("value"), COUNT(*)) FROM loot WHERE "user"=$1;',
                    ctx.author.id,
                )
                if count == 0:
                    await self.bot.reset_cooldown(ctx)
                    return await ctx.send(_("You don't have any loot."))
                if not await ctx.confirm(
                    _(
                        "This will sacrifice all of your loot and give {value} favor."
                        " Continue?"
                    ).format(value=value)
                ):
                    return
            else:
                value, count = await conn.fetchval(
                    'SELECT (SUM("value"), COUNT("value")) FROM loot WHERE "id"=ANY($1)'
                    ' AND "user"=$2;',
                    loot_ids,
                    ctx.author.id,
                )

                if not count:
                    await self.bot.reset_cooldown(ctx)
                    return await ctx.send(
                        _(
                            "You don't own any loot items with the IDs: {itemids}"
                        ).format(
                            itemids=", ".join([str(loot_id) for loot_id in loot_ids])
                        )
                    )
            class_ = ctx.character_data["class"]
            for class_ in ctx.character_data["class"]:
                c = from_string(class_)
                if c and c.in_class_line(Ritualist):
                    value = round(value * Decimal(1 + 0.05 * c.class_grade()))

            if len(loot_ids) > 0:
                await conn.execute(
                    'DELETE FROM loot WHERE "id"=ANY($1) AND "user"=$2;',
                    loot_ids,
                    ctx.author.id,
                )
            else:
                await conn.execute('DELETE FROM loot WHERE "user"=$1;', ctx.author.id)
            await conn.execute(
                'UPDATE profile SET "favor"="favor"+$1 WHERE "user"=$2;',
                value,
                ctx.author.id,
            )

            value = float(value)
            value = int(value)


            await self.bot.log_transaction(
                ctx,
                from_=ctx.author.id,
                to=2,
                subject="sacrifice",
                data={"Item-Count": count, "Amount": value},
                conn=conn,
            )
        await ctx.send(
            _(
                "You prayed to {god}, and they accepted your {count} sacrificed loot"
                " item(s). Your standing with the god has increased by **{points}**"
                " points."
            ).format(god=ctx.character_data["god"], count=count, points=value)
        )

    @has_char()
    @user_cooldown(1209600)  # to prevent double invoke
    @commands.command(brief=_("Choose or change your God"))
    @locale_doc
    async def follow(self, ctx):
        _(
            """Choose a God or change your current God for a reset point.
            Every player gets 2 reset points when they start playing, you cannot get any more.

            Following a God allows your `{prefix}luck` to fluctuate, check `{prefix}help luck` to see the exact effects this will have on your gameplay.
            If you don't have any reset points left, or became Godless, you cannot follow another God.

            (This command has a cooldown of 3 minutes.)"""
        )
        god_roles = self.support_god_role_ids
        godless_role_id = self.godless_role_id
        old_god = ctx.character_data["god"]

        # Check if the user already has a god and handle reset points
        if not has_no_god(ctx):
            try:
                old_role_id = god_roles.get(old_god)
                if old_role_id:
                    old_role = ctx.guild.get_role(old_role_id)
                    if old_role and old_role in ctx.author.roles:
                        await ctx.author.remove_roles(old_role)
            except Exception as e:
                print("Not in server")

        if ctx.character_data["reset_points"] < 0:
            return await ctx.send(_("You became Godless. You will not be able to follow a god anymore."))

        # Show gods selection to the user
        embeds = [
            discord.Embed(
                title=god["name"],
                description=god["description"],
                color=self.bot.config.game.primary_colour,
            )
            for god in self.bot.gods.values()
        ]
        god = await self.bot.paginator.ChoosePaginator(
            extras=embeds,
            placeholder=_("Choose a god"),
            choices=[g["name"] for g in self.bot.gods.values()],
        ).paginate(ctx)

        # Confirm the user's choice of God
        if not await ctx.confirm(
                _("""\
    ⚠ **Warning**: When you have a God, your luck will change (**including decreasing it!**)
    This impacts your adventure success chances amongst other things.
    Are you sure you want to follow {god}?""").format(god=god)
        ):
            return

        # Update the user's god and reset points in the database
        async with self.bot.pool.acquire() as conn:
            if (
                    await conn.fetchval(
                        'SELECT reset_points FROM profile WHERE "user"=$1;', ctx.author.id
                    )
                    < 0
            ):
                return await ctx.send(
                    _("You became Godless while using this command. Following a God is not allowed after that.")
                )


            await conn.execute(
                'UPDATE profile SET "god"=$1 WHERE "user"=$2;', god, ctx.author.id
            )

        # Get the target guild and check if the user is a member
        target_guild = self.bot.get_guild(self.bot.config.game.support_server_id)

        if target_guild:
            member = target_guild.get_member(ctx.author.id)
            if member:
                # Remove godless role if present
                godless_role = target_guild.get_role(godless_role_id)
                if godless_role and godless_role in member.roles:
                    await member.remove_roles(godless_role)

                # Remove old god role in the support server if present
                old_role_id = god_roles.get(old_god)
                if old_role_id:
                    old_role = target_guild.get_role(old_role_id)
                    if old_role and old_role in member.roles:
                        await member.remove_roles(old_role)

                # Assign the god's role in the target guild if the user is a member
                role_id = god_roles.get(god)
                if role_id:
                    role = target_guild.get_role(role_id)
                    if role:
                        await member.add_roles(role)
                        await ctx.send(
                            _("You are now a follower of {god}. Role assigned in the target guild.").format(god=god))
                    else:
                        await ctx.send(_("Failed to assign role in the target guild."))
                else:
                    await ctx.send(_("Failed to assign role."))
            else:
                await ctx.send(
                    _("You have successfully followed {god}, but you are not a member of the target guild.").format(
                        god=god))
        else:
            await ctx.send(
                _("You have successfully followed {god}, but the target guild could not be found.").format(god=god))

    @has_char()
    @has_god()
    @commands.command(brief=_("Unfollow your God and become Godless"))
    @locale_doc
    async def unfollow(self, ctx):
        _(
            """Unfollow your current God and become Godless. **This is permanent!**

            Looking to change your God instead? Simply use `{prefix}follow` again.

            Once you become Godless, all your reset points and your God are removed.
            Becoming Godless does not mean that your luck returns to 1.00 immediately, it changes along with everyone else's luck on Monday."""
        )
        if ctx.character_data["reset_points"] < 0:
            # this shouldn't happen in normal play, but you never know
            return await ctx.send(_("You already became Godless before."))

        old_god = ctx.character_data["god"]
        god_roles = self.primary_god_role_ids
        support_god_roles = self.support_god_role_ids
        godless_role_id = self.godless_role_id


        if not await ctx.confirm(
                _(
                    """\
        ⚠ **Warning**: After unfollowing your God, **you cannot follow any God anymore** and will remain Godless.
        If your luck is below average and you decided to unfollow, know that **your luck will not return to 1.0 immediately**.
    
        Are you sure you want to become Godless?"""
                )
        ):
            return await ctx.send(
                _("{god} smiles proudly down upon you.").format(
                    god=ctx.character_data["god"]
                )
            )

        async with self.bot.pool.acquire() as conn:
            await conn.execute(
                'UPDATE profile SET "favor"=0, "god"=NULL, "reset_points"="reset_points"-1 WHERE'
                ' "user"=$1;',
                ctx.author.id,
            )

        old_role_id = god_roles.get(old_god)
        if old_role_id:
            old_role = ctx.guild.get_role(old_role_id)
            if old_role and old_role in ctx.author.roles:
                await ctx.author.remove_roles(old_role)

        # Assign godless role in support server if the user is a member
        support_guild = self.bot.get_guild(self.bot.config.game.support_server_id)
        if support_guild:
            member = support_guild.get_member(ctx.author.id)
            if member:
                # Remove any god roles in the support server
                for role_id in support_god_roles.values():
                    role = support_guild.get_role(role_id)
                    if role and role in member.roles:
                        await member.remove_roles(role)

                godless_role = support_guild.get_role(godless_role_id)
                if godless_role and godless_role not in member.roles:
                    await member.add_roles(godless_role)

        await ctx.send(_("You are now Godless."))

    @has_god()
    @has_char()
    @next_day_cooldown()
    @commands.command(brief=_("Pray to your God to gain favor"))
    @locale_doc
    async def pray(self, ctx):
        _(
            # xgettext: no-python-format
            """Pray to your God in order to gain a random amont of favor points, ranging from 0 to 1000.

            There is a 33% chance you will gain 0 favor, a 33% chance to gain anywhere from 0 to 500 favor and a 33% chance to gain anywhere from 500 to 1000 favor.

            (This command has a cooldown until 12am UTC.)"""
        )
        if (rand := random.randint(0, 2)) == 0:
            message = random.choice(
                [
                    _("They obviously didn't like your prayer!"),
                    _("Noone heard you!"),
                    _("Your voice has made them screw off."),
                    _("Even a donkey would've been a better follower than you."),
                ]
            )
            val = 0
        elif rand == 1:
            val = random.randint(1, 500)
            message = random.choice(
                [
                    _("„Rather lousy, but okay“, they said."),
                    _("You were a little sleepy."),
                    _("They were a little amused about your singing."),
                    _("Hearing the same prayer over and over again made them tired."),
                ]
            )
        elif rand == 2:
            val = random.randint(0, 500) + 500
            message = random.choice(
                [
                    _("Your Gregorian chants were amazingly well sung."),
                    _("Even the birds joined in your singing."),
                    _(
                        "The other gods applauded while your god noted down the best"
                        " mark."
                    ),
                    _("Rarely have you had a better day!"),
                ]
            )
        if val > 0:
            await self.bot.pool.execute(
                'UPDATE profile SET "favor"="favor"+$1 WHERE "user"=$2;',
                val,
                ctx.author.id,
            )
        await ctx.send(
            _("Your prayer resulted in **{val}** favor. {message}").format(
                val=val, message=message
            )
        )

    @has_god()
    @has_char()
    @commands.command(aliases=["favour"], brief=_("Shows your God and favor"))
    @locale_doc
    async def favor(self, ctx):
        _(
            """Shows your current God and how much favor you have with them at the time.

            If you have enough favor to place in the top 25 of that God's followers, you will gain extra luck when the new luck is decided, this usually happens on Monday.
              - The top 25 to 21 will gain +0.1 luck
              - The top 20 to 16 will gain +0.2 luck
              - The top 15 to 11 will gain +0.3 luck
              - The top 10 to 6 will gain +0.4 luck
              - The top 5 to 1 will gain +0.5 luck

            These extra luck values are based off the decided luck value.
            For example, if your God's luck value is decided to be 1.2 and you are the 13th best follower, you will have 1.5 luck for that week.
            All favor is reset to 0 when the new luck is decided to make it fair for everyone."""
        )
        await ctx.send(
            _("Your god is **{god}** and you have **{favor}** favor with them.").format(
                god=ctx.character_data["god"], favor=ctx.character_data["favor"]
            )
        )

    # just like admin commands, these aren't translated
    @has_char()
    @commands.command(brief=_("Show the top followers of your God"))
    @locale_doc
    async def followers(self, ctx, limit: IntGreaterThan(0)):
        _(
            """`<limit>` - A whole number from 1 to 25. If you are a God, the upper bound is lifted.

            Display your God's (or your own, if you are a God) top followers, up to `<limit>`.
            """
        )
        if ctx.author.id in self.bot.gods:
            god = self.bot.gods[ctx.author.id]["name"]
        elif not ctx.character_data["god"]:
            return await ctx.send(
                _(
                    "You are not following any god currently, therefore the list cannot be generated."
                )
            )
        else:
            god = ctx.character_data["god"]
            if limit > 25:
                return await ctx.send(_("Normal followers may only view the top 25."))

        data = await self.bot.pool.fetch(
            'SELECT * FROM profile WHERE "god"=$1 ORDER BY "favor" DESC LIMIT $2;',
            god,
            limit,
        )

        if not data:
            return await ctx.send(_("No followers found for this God."))

        # Create an embed
        embed = discord.Embed(
            title=_("Top Followers of {god}").format(god=god),
            color=discord.Color.blue(),
        )

        for idx, record in enumerate(data, start=1):
            user = self.bot.get_user(record["user"])
            display_name = user.display_name if user else _("Unknown User")
            favor = record["favor"]
            luck = record["luck"]

            embed.add_field(
                name=f"{idx}. {display_name}",
                value=_("Favor: {favor}, Luck: {luck}").format(favor=favor, luck=luck),
                inline=False,
            )

        # Send the embed
        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(Gods(bot))

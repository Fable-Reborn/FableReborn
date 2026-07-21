"""Player-facing gameplay for the Soulforge Frontiers content update.

The Battles cog owns encounter construction.  This cog owns the weekly loop,
catalog presentation, lineage tracking, and its single transactional reward.
It deliberately leaves the campaign, classes, races, and pet skills alone.
"""

from __future__ import annotations

import datetime as dt
import inspect
import json
import logging
from pathlib import Path
from typing import Any, Mapping, Optional

import discord
from discord.ext import commands

from cogs.frontier_catalog import get_frontier_catalog
from utils import misc as rpgtools
from utils.checks import has_char

from .frontier_pve import (
    build_frontier_boss_encounter,
    get_region,
    get_rotation_state,
    load_frontier_config,
    resolve_recipe_generations,
)
from .progression import (
    WEEKLY_FORGE_REPAIR,
    WEEKLY_MATERIAL_CRATES,
    WEEKLY_MONEY_REWARD,
    WeeklyProgress,
    boss_requirements,
    boss_is_unlocked,
    collection_state,
    earned_milestones,
    objective_lines,
    weekly_reward_is_available,
)


log = logging.getLogger(__name__)
PROJECT_ROOT = Path(__file__).resolve().parents[2]
MONSTERS_PATH = PROJECT_ROOT / "monsters.json"
PAGE_SIZE = 12
COLLECTION_PAGE_SIZE = 8
MATERIALS_CRATE_EMOJI = "<:c_mats:1403797590335819897>"

ELEMENT_EMOJIS = {
    "fire": "🔥",
    "water": "💧",
    "earth": "🪨",
    "wind": "💨",
    "nature": "🌿",
    "electric": "⚡",
    "light": "✨",
    "dark": "🌑",
    "corrupted": "🌀",
    "ice": "❄️",
}

COLLECTION_STATE_EMOJIS = {
    "Unknown": "🔒",
    "Sighted": "👁️",
    "Defeated": "⚔️",
    "Egg Obtained": "🥚",
    "Personally Created": "🧬",
    "Owned": "🐾",
    "Mastered": "⭐",
}


SCHEMA_STATEMENTS = (
    """
    CREATE TABLE IF NOT EXISTS frontier_weekly_progress (
        user_id BIGINT NOT NULL,
        absolute_week INTEGER NOT NULL,
        region_id TEXT NOT NULL,
        regular_defeats INTEGER NOT NULL DEFAULT 0 CHECK (regular_defeats >= 0),
        elite_defeats INTEGER NOT NULL DEFAULT 0 CHECK (elite_defeats >= 0),
        boss_defeats INTEGER NOT NULL DEFAULT 0 CHECK (boss_defeats >= 0),
        distinct_species INTEGER NOT NULL DEFAULT 0 CHECK (distinct_species >= 0),
        reward_claimed BOOLEAN NOT NULL DEFAULT FALSE,
        reward_claimed_at TIMESTAMPTZ,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        PRIMARY KEY (user_id, absolute_week)
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS frontier_weekly_defeats (
        user_id BIGINT NOT NULL,
        absolute_week INTEGER NOT NULL,
        event_key TEXT NOT NULL,
        region_id TEXT NOT NULL,
        species_id BIGINT REFERENCES frontier_species(species_id) ON DELETE SET NULL,
        species_key TEXT NOT NULL,
        role TEXT NOT NULL CHECK (role IN ('regular', 'elite', 'boss')),
        defeated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        PRIMARY KEY (user_id, absolute_week, event_key),
        FOREIGN KEY (user_id, absolute_week)
            REFERENCES frontier_weekly_progress(user_id, absolute_week)
            ON DELETE CASCADE
    );
    """,
    """
    CREATE INDEX IF NOT EXISTS frontier_weekly_defeats_species_idx
    ON frontier_weekly_defeats(user_id, absolute_week, species_key, role);
    """,
    """
    CREATE TABLE IF NOT EXISTS frontier_lineage_tracks (
        track_id BIGSERIAL PRIMARY KEY,
        user_id BIGINT NOT NULL,
        target_species_id BIGINT NOT NULL
            REFERENCES frontier_species(species_id) ON DELETE CASCADE,
        target_name_snapshot TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'active'
            CHECK (status IN ('active', 'completed', 'abandoned')),
        started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        completed_at TIMESTAMPTZ,
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        UNIQUE (user_id, target_species_id)
    );
    """,
    """
    CREATE UNIQUE INDEX IF NOT EXISTS frontier_one_active_lineage_idx
    ON frontier_lineage_tracks(user_id) WHERE status = 'active';
    """,
)


MILESTONE_LABELS = {
    "splice_scout_10": "Encounter 10 splice species",
    "splice_scout_25": "Encounter 25 splice species",
    "splice_scout_50": "Encounter 50 splice species",
    "splice_creator_5": "Personally create 5 splices",
    "splice_creator_15": "Personally create 15 splices",
    "splice_creator_30": "Personally create 30 splices",
    "lineage_gen_1": "Create a Generation 1 splice",
    "lineage_gen_3": "Create a Generation 3 splice",
    "lineage_gen_5": "Create a Generation 5 splice",
    "lineage_gen_10": "Create a Generation 10 splice",
    "lineage_completed": "Complete a tracked lineage",
    "frontier_boss_1": "Defeat 1 Frontier boss",
    "frontier_boss_4": "Defeat 4 Frontier bosses",
    "frontier_boss_20": "Defeat 20 Frontier bosses",
}


def region_is_unlocked(player_level: int, region: Mapping[str, Any]) -> bool:
    """Pure region gate shared by commands and event listeners."""

    return max(0, int(player_level or 0)) >= int(region.get("unlock_level", 1))


def role_counter_column(role: str) -> Optional[str]:
    """Return the only counter column a trusted encounter role may change."""

    return {
        "regular": "regular_defeats",
        "elite": "elite_defeats",
        "boss": "boss_defeats",
    }.get(str(role or "").strip().casefold())


def clamp_page(page: int, total: int, page_size: int = PAGE_SIZE) -> tuple[int, int, int]:
    """Return a safe page number, offset, and number of pages."""

    pages = max(1, (max(0, int(total)) + page_size - 1) // page_size)
    selected = min(max(1, int(page or 1)), pages)
    return selected, (selected - 1) * page_size, pages


def event_key_for_battle(
    battle_id: Any,
    message_id: Any,
    species_key: str,
    role: str,
) -> str:
    """Build a deterministic retry key without relying on a display name alone."""

    if battle_id is not None and str(battle_id).strip():
        return f"battle:{battle_id}"
    if message_id is not None and str(message_id).strip():
        return f"message:{message_id}:{species_key}:{role}"
    return f"encounter:{species_key}:{role}"


def _safe_int(value: Any) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _row_dict(row: Any) -> dict[str, Any]:
    return dict(row) if row else {}


def progress_bar(current: int, total: int, *, width: int = 10) -> str:
    """Return a compact Discord-safe progress bar."""

    total = max(0, int(total or 0))
    current = max(0, int(current or 0))
    if total <= 0:
        filled = 0
    else:
        filled = round(min(current, total) / total * max(1, int(width)))
    width = max(1, int(width))
    return "▰" * filled + "▱" * (width - filled)


def species_is_known(value: Mapping[str, Any]) -> bool:
    """A permanent discovery or current holding reveals a species identity."""

    return any(
        value.get(key)
        for key in (
            "first_sighted_at",
            "first_defeated_at",
            "first_egg_at",
            "first_owned_at",
            "first_created_at",
            "mastered_at",
            "current_pet_count",
            "current_egg_count",
        )
    )


def species_collection_state(value: Mapping[str, Any]) -> str:
    """Return the best player-facing state represented by one catalog row."""

    return collection_state(
        sighted=bool(value.get("first_sighted_at")),
        defeated=bool(value.get("first_defeated_at")),
        egg_obtained=bool(value.get("first_egg_at") or value.get("current_egg_count")),
        created=bool(value.get("first_created_at")),
        owned=bool(value.get("current_pet_count") or value.get("first_owned_at")),
        mastered=bool(value.get("mastered_at")),
    )


def _element_emoji(element: Any) -> str:
    return ELEMENT_EMOJIS.get(str(element or "").strip().casefold(), "❔")


def _valid_image_url(value: Any) -> str:
    url = str(value or "").strip()
    return url if url.startswith(("https://", "http://")) else ""


class FrontierPageSelect(discord.ui.Select):
    """Direct page jump for compact Frontier books with at most 25 pages."""

    def __init__(self, book: "FrontierBookView", labels: list[str]):
        self.book = book
        options = [
            discord.SelectOption(
                label=str(label)[:100],
                value=str(index),
                default=index == book.index,
            )
            for index, label in enumerate(labels)
        ]
        super().__init__(
            placeholder="Jump to a page…",
            min_values=1,
            max_values=1,
            options=options,
            row=0,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        await self.book.show_page(interaction, int(self.values[0]))


class FrontierBookView(discord.ui.View):
    """Owner-only collection navigator that keeps its final page on timeout."""

    def __init__(
        self,
        ctx,
        pages: list[discord.Embed],
        *,
        labels: Optional[list[str]] = None,
        initial_index: int = 0,
        timeout: float = 180,
    ):
        super().__init__(timeout=timeout)
        if not pages:
            raise ValueError("FrontierBookView requires at least one page")
        self.ctx = ctx
        self.pages = pages
        self.index = min(max(0, int(initial_index or 0)), len(pages) - 1)
        self.message = None
        self.allowed_user_ids = {int(ctx.author.id)}
        alt_invoker_id = getattr(ctx, "alt_invoker_id", None)
        if alt_invoker_id is not None:
            self.allowed_user_ids.add(int(alt_invoker_id))
        self.labels = labels or [
            "Overview" if index == 0 else f"Page {index}"
            for index in range(len(pages))
        ]
        self.page_select: Optional[FrontierPageSelect] = None
        if 1 < len(self.pages) <= 25:
            self.page_select = FrontierPageSelect(self, self.labels)
            self.add_item(self.page_select)
        self._sync_components()

    def _sync_components(self) -> None:
        self.overview.disabled = self.index == 0
        self.previous.disabled = self.index == 0
        self.next.disabled = self.index >= len(self.pages) - 1
        self.last.disabled = self.index >= len(self.pages) - 1
        self.page_number.label = (
            "Overview"
            if self.index == 0
            else f"Page {self.index}/{max(1, len(self.pages) - 1)}"
        )
        if self.page_select is not None:
            for option_index, option in enumerate(self.page_select.options):
                option.default = option_index == self.index
            self.page_select.placeholder = str(self.labels[self.index])[:150]

    async def start(self):
        self.message = await self.ctx.send(embed=self.pages[self.index], view=self)
        return self.message

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if int(interaction.user.id) in self.allowed_user_ids:
            return True
        await interaction.response.send_message(
            "This Frontier journal belongs to another player.", ephemeral=True
        )
        return False

    async def show_page(self, interaction: discord.Interaction, index: int) -> None:
        self.index = min(max(0, int(index)), len(self.pages) - 1)
        self._sync_components()
        await interaction.response.edit_message(embed=self.pages[self.index], view=self)

    async def on_timeout(self) -> None:
        for item in self.children:
            item.disabled = True
        if self.message is not None:
            try:
                await self.message.edit(view=self)
            except (discord.HTTPException, discord.NotFound):
                pass

    @discord.ui.button(
        label="Overview", emoji="🏠", style=discord.ButtonStyle.secondary, row=1
    )
    async def overview(
        self, interaction: discord.Interaction, _button: discord.ui.Button
    ) -> None:
        await self.show_page(interaction, 0)

    @discord.ui.button(
        label="Previous", emoji="◀", style=discord.ButtonStyle.secondary, row=1
    )
    async def previous(
        self, interaction: discord.Interaction, _button: discord.ui.Button
    ) -> None:
        await self.show_page(interaction, self.index - 1)

    @discord.ui.button(
        label="Overview", style=discord.ButtonStyle.secondary, disabled=True, row=1
    )
    async def page_number(
        self, interaction: discord.Interaction, _button: discord.ui.Button
    ) -> None:
        return None

    @discord.ui.button(
        label="Next", emoji="▶", style=discord.ButtonStyle.primary, row=1
    )
    async def next(
        self, interaction: discord.Interaction, _button: discord.ui.Button
    ) -> None:
        await self.show_page(interaction, self.index + 1)

    @discord.ui.button(
        label="Last", emoji="⏭", style=discord.ButtonStyle.secondary, row=1
    )
    async def last(
        self, interaction: discord.Interaction, _button: discord.ui.Button
    ) -> None:
        await self.show_page(interaction, len(self.pages) - 1)


class FrontierDashboardView(discord.ui.View):
    """Four-section regional dashboard used by the root Frontier command."""

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
        self._sync_components()

    def _sync_components(self) -> None:
        for index, button in enumerate(
            (self.region, self.research, self.rotation, self.guide)
        ):
            button.disabled = index == self.index
            button.style = (
                discord.ButtonStyle.primary
                if index == self.index
                else discord.ButtonStyle.secondary
            )

    async def start(self):
        self.message = await self.ctx.send(embed=self.pages[0], view=self)
        return self.message

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if int(interaction.user.id) in self.allowed_user_ids:
            return True
        await interaction.response.send_message(
            "This Frontier dashboard belongs to another player.", ephemeral=True
        )
        return False

    async def _show(self, interaction: discord.Interaction, index: int) -> None:
        self.index = min(max(0, int(index)), len(self.pages) - 1)
        self._sync_components()
        await interaction.response.edit_message(embed=self.pages[self.index], view=self)

    async def on_timeout(self) -> None:
        for item in self.children:
            item.disabled = True
        if self.message is not None:
            try:
                await self.message.edit(view=self)
            except (discord.HTTPException, discord.NotFound):
                pass

    @discord.ui.button(label="Region", emoji="🧭", row=0)
    async def region(
        self, interaction: discord.Interaction, _button: discord.ui.Button
    ) -> None:
        await self._show(interaction, 0)

    @discord.ui.button(label="Research", emoji="📋", row=0)
    async def research(
        self, interaction: discord.Interaction, _button: discord.ui.Button
    ) -> None:
        await self._show(interaction, 1)

    @discord.ui.button(label="Rotation", emoji="🗓️", row=0)
    async def rotation(
        self, interaction: discord.Interaction, _button: discord.ui.Button
    ) -> None:
        await self._show(interaction, 2)

    @discord.ui.button(label="Guide", emoji="📖", row=0)
    async def guide(
        self, interaction: discord.Interaction, _button: discord.ui.Button
    ) -> None:
        await self._show(interaction, 3)


class SoulforgeFrontiers(commands.Cog):
    """Four rotating regions and the player-facing Soulforge Archive."""

    def __init__(self, bot):
        self.bot = bot
        self.config = load_frontier_config()
        self._synced_users: set[int] = set()

    @property
    def catalog(self):
        return get_frontier_catalog(self.bot)

    def _colour(self) -> int:
        game = getattr(getattr(self.bot, "config", None), "game", None)
        return int(getattr(game, "primary_colour", 0x6D4AFF))

    def _region_colour(self, region: Mapping[str, Any]) -> int:
        value = region.get("accent_color")
        if isinstance(value, str):
            try:
                return int(value.lstrip("#"), 16)
            except ValueError:
                pass
        if isinstance(value, int):
            return value
        return self._colour()

    @staticmethod
    def _region_emoji(region: Mapping[str, Any]) -> str:
        return str(region.get("emoji") or "🧭")

    def _decorate_region_embed(
        self,
        embed: discord.Embed,
        region: Mapping[str, Any],
        *,
        large_art: bool = False,
    ) -> discord.Embed:
        artwork = _valid_image_url(
            region.get("environment_image_url") or region.get("showcase_image_url")
        )
        if artwork:
            if large_art:
                embed.set_image(url=artwork)
            else:
                embed.set_thumbnail(url=artwork)
        return embed

    def _build_region_overview_embed(
        self,
        *,
        state,
        region: Mapping[str, Any],
        progress: WeeklyProgress,
        unlocked: bool,
        level: int,
    ) -> discord.Embed:
        ends = int(state.ends_at.timestamp())
        requirements = boss_requirements(progress)
        research_done = sum(
            1 for current, required in requirements.values() if current >= required
        )
        if not unlocked:
            next_move = (
                f"Reach **Level {region['unlock_level']}** to begin research in this region."
            )
            boss_status = "🔒 Region locked"
        elif progress.reward_claimed:
            next_move = "Your weekly expedition is complete. Explore the collections or prepare for the next rotation."
            boss_status = "✅ Cleared · reward claimed"
        elif weekly_reward_is_available(progress):
            next_move = "Your reward is waiting — use **`$frontier claim`**."
            boss_status = "🎁 Cleared · reward ready"
        elif boss_is_unlocked(progress):
            next_move = "Research complete — challenge **`$frontier boss`**."
            boss_status = "⚔️ Challenge available"
        else:
            next_move = (
                f"Enter **{region['name']}** through **`$pve`** and hunt featured encounters."
            )
            boss_status = f"🔒 Research {research_done}/{len(requirements)}"

        embed = discord.Embed(
            title=f"{self._region_emoji(region)} {region['name']}",
            description=(
                f"*{region['description']}*\n\n"
                f"**Active Frontier** · ends <t:{ends}:R>"
            ),
            color=self._region_colour(region),
        )
        embed.add_field(
            name="Expedition Access",
            value=(
                f"{'🟢 Open' if unlocked else '🔒 Locked'}\n"
                f"Your level: **{level}** · Required: **{region['unlock_level']}**"
            ),
            inline=True,
        )
        embed.add_field(
            name="Native Elements",
            value="\n".join(
                f"{_element_emoji(element)} **{element}**"
                for element in region["elements"]
            ),
            inline=True,
        )
        embed.add_field(
            name="Regional Boss",
            value=boss_status,
            inline=True,
        )
        embed.add_field(name="Your Next Move", value=next_move, inline=False)
        embed.add_field(
            name="Field Journals",
            value=(
                "📖 **`$frontier bestiary`** — permanent wild collection\n"
                "🧬 **`$frontier archive`** — discovered splice lineages\n"
                "🏅 **`$frontier milestones`** — lifetime achievements"
            ),
            inline=False,
        )
        embed.set_footer(
            text=f"Soulforge Frontiers · Rotation week {state.absolute_week}"
        )
        return self._decorate_region_embed(embed, region, large_art=True)

    def _build_research_embed(
        self,
        *,
        state,
        region: Mapping[str, Any],
        progress: WeeklyProgress,
        unlocked: bool,
        level: int,
    ) -> discord.Embed:
        embed = discord.Embed(
            title=f"📋 {region['name']} Research",
            description=(
                "Defeat this rotation's featured splice encounters to expose the "
                "regional boss. Permanent wild encounters fill your Bestiary but do "
                "not advance these objectives."
                if unlocked
                else (
                    f"🔒 Research unlocks at **Level {region['unlock_level']}**. "
                    f"Your current level is **{level}**."
                )
            ),
            color=self._region_colour(region),
        )
        for label, (current, required) in boss_requirements(progress).items():
            shown = min(current, required)
            icon = "✅" if current >= required else "▫️"
            embed.add_field(
                name=f"{icon} {label}",
                value=f"`{progress_bar(shown, required, width=5)}` **{shown}/{required}**",
                inline=True,
            )

        if not unlocked:
            boss_status = "🔒 Region locked"
            reward_status = "Unavailable"
        elif progress.reward_claimed:
            boss_status = "✅ Defeated"
            reward_status = "✅ Claimed"
        elif weekly_reward_is_available(progress):
            boss_status = "✅ Defeated"
            reward_status = "🎁 Ready — `$frontier claim`"
        elif boss_is_unlocked(progress):
            boss_status = "⚔️ Unlocked — `$frontier boss`"
            reward_status = "Defeat the boss"
        else:
            boss_status = "🔒 Complete all three objectives"
            reward_status = "Defeat the boss"
        embed.add_field(name="Regional Boss", value=boss_status, inline=False)
        embed.add_field(
            name="Weekly Reward",
            value=(
                f"**${WEEKLY_MONEY_REWARD:,}** · "
                f"{MATERIALS_CRATE_EMOJI} **{WEEKLY_MATERIAL_CRATES} Materials Crate** · "
                f"🔧 **+{WEEKLY_FORGE_REPAIR}% Soulforge condition**\n{reward_status}"
            ),
            inline=False,
        )
        embed.set_footer(
            text=(
                f"Rotation week {state.absolute_week} · Resets "
                f"{state.ends_at.strftime('%A %H:%M UTC')}"
            )
        )
        return self._decorate_region_embed(embed, region)

    def _build_forecast_embed(self, *, level: int, now: dt.datetime) -> discord.Embed:
        active_state = get_rotation_state(self.config, now)
        active_region = get_region(self.config, active_state.region_id)
        embed = discord.Embed(
            title="🗓️ Four-Week Frontier Rotation",
            description=(
                "The active region is highlighted below. Unlocked regions remain "
                "available through `$pve`, but only the active region grants weekly research."
            ),
            color=self._region_colour(active_region),
        )
        for offset in range(4):
            state = get_rotation_state(self.config, now + dt.timedelta(days=7 * offset))
            region = get_region(self.config, state.region_id)
            unlocked = region_is_unlocked(level, region)
            marker = "🟢 NOW" if offset == 0 else f"Week +{offset}"
            tier_values = sorted(int(value) for value in region["tier_weights"])
            tier_text = (
                str(tier_values[0])
                if len(tier_values) == 1
                else f"{tier_values[0]}–{tier_values[-1]}"
            )
            access_text = (
                "Open" if unlocked else f"Requires Level {region['unlock_level']}"
            )
            embed.add_field(
                name=(
                    f"{self._region_emoji(region)} {marker} · {region['name']}"
                    f"{' ' if unlocked else ' 🔒'}"
                ),
                value=(
                    f"<t:{int(state.starts_at.timestamp())}:d> → "
                    f"<t:{int(state.ends_at.timestamp())}:d>\n"
                    f"{access_text} · "
                    f"Tiers **{tier_text}** · "
                    + " ".join(
                        f"{_element_emoji(element)} {element}"
                        for element in region["elements"]
                    )
                ),
                inline=False,
            )
        embed.set_footer(text=f"Your level: {level} · Rotation changes every Monday UTC")
        return self._decorate_region_embed(embed, active_region)

    def _build_guide_embed(
        self, *, state, region: Mapping[str, Any]
    ) -> discord.Embed:
        embed = discord.Embed(
            title="📖 Frontier Field Guide",
            description=(
                "Everything in Soulforge Frontiers follows one weekly expedition loop."
            ),
            color=self._region_colour(region),
        )
        embed.add_field(
            name="1 · Research",
            value=(
                f"Use **`$pve`** and enter **{region['name']}**. Defeat featured "
                "Regular and Elite splice encounters, then check **`$frontier progress`**."
            ),
            inline=False,
        )
        embed.add_field(
            name="2 · Confront the Boss",
            value=(
                "When all three objectives are complete, use **`$frontier boss`**. "
                "The boss can be cleared once per rotation."
            ),
            inline=False,
        )
        embed.add_field(
            name="3 · Claim the Expedition Reward",
            value=(
                f"Use **`$frontier claim`** for **${WEEKLY_MONEY_REWARD:,}**, "
                f"{MATERIALS_CRATE_EMOJI} **{WEEKLY_MATERIAL_CRATES} Materials Crate**, "
                f"and **+{WEEKLY_FORGE_REPAIR}%** Soulforge condition."
            ),
            inline=False,
        )
        embed.add_field(
            name="Collections & Planning",
            value=(
                "`$frontier bestiary` · `$frontier archive` · `$frontier lineage <name>`\n"
                "`$frontier track <name>` · `$frontier milestones` · `$frontier forecast`"
            ),
            inline=False,
        )
        embed.set_footer(text=f"Active region: {region['name']} · Week {state.absolute_week}")
        return self._decorate_region_embed(embed, region)

    async def cog_load(self) -> None:
        catalog = self.catalog
        if catalog is None:
            raise RuntimeError(
                "Soulforge Frontiers requires cogs.frontier_catalog to load first"
            )
        await catalog.ensure_ready()
        async with self.bot.pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    "SELECT pg_advisory_xact_lock(hashtext($1));",
                    "soulforge-frontiers-gameplay-v1",
                )
                for statement in SCHEMA_STATEMENTS:
                    await conn.execute(statement)
                await self._publish_roster_metadata(conn)

    async def _publish_roster_metadata(self, conn) -> None:
        """Idempotently project the checked-in roster onto catalog identities."""

        for entry in self.config["entries"]:
            legacy_id = int(entry["legacy_splice_id"])
            recipe = await conn.fetchrow(
                """
                UPDATE frontier_recipes
                SET publication_status = 'approved',
                    stability = CASE
                        WHEN upper(COALESCE(legacy_result_name, '')) LIKE '%[FINAL]%'
                            THEN 'final'
                        WHEN upper(COALESCE(legacy_result_name, '')) LIKE '%[DESTABILISED]%'
                            THEN 'destabilised'
                        WHEN upper(COALESCE(legacy_result_name, '')) LIKE '%[UNSTABLE]%'
                            THEN 'unstable'
                        WHEN upper(COALESCE(legacy_result_name, '')) LIKE '%[SPECIAL]%'
                            THEN 'special'
                        ELSE stability
                    END,
                    updated_at = NOW()
                WHERE legacy_splice_id = $1
                RETURNING recipe_id, result_species_id;
                """,
                legacy_id,
            )
            if not recipe:
                log.warning("Frontier roster recipe %s is absent from catalog", legacy_id)
                continue
            await conn.execute(
                """
                UPDATE frontier_species
                SET publication_status = 'approved',
                    pve_enabled = TRUE,
                    pve_region = $2,
                    pve_tier = $3,
                    pve_role = $4,
                    generation = COALESCE(generation, $5),
                    updated_at = NOW()
                WHERE species_id = $1;
                """,
                int(recipe["result_species_id"]),
                str(entry["region_id"]),
                int(entry["tier"]),
                str(entry["role"]),
                int(entry["expected_generation"]),
            )

    async def _profile_level(self, user_id: int, ctx=None, conn=None) -> int:
        if ctx is not None:
            character = getattr(ctx, "character_data", None) or {}
            if character.get("xp") is not None:
                return int(rpgtools.xptolevel(int(character.get("xp") or 0)))
        local = conn is None
        if local:
            conn = await self.bot.pool.acquire()
        try:
            xp = await conn.fetchval('SELECT xp FROM profile WHERE "user" = $1;', user_id)
            return int(rpgtools.xptolevel(int(xp or 0)))
        finally:
            if local:
                await self.bot.pool.release(conn)

    async def _weekly_row(
        self,
        user_id: int,
        *,
        player_level: int,
        create: bool,
        conn=None,
    ):
        state = get_rotation_state(self.config)
        region = get_region(self.config, state.region_id)
        if not region_is_unlocked(player_level, region):
            return state, region, None

        local = conn is None
        if local:
            conn = await self.bot.pool.acquire()
        try:
            if create:
                await conn.execute(
                    """
                    INSERT INTO frontier_weekly_progress (
                        user_id, absolute_week, region_id
                    ) VALUES ($1, $2, $3)
                    ON CONFLICT (user_id, absolute_week) DO NOTHING;
                    """,
                    int(user_id),
                    int(state.absolute_week),
                    str(state.region_id),
                )
            row = await conn.fetchrow(
                """
                SELECT * FROM frontier_weekly_progress
                WHERE user_id = $1 AND absolute_week = $2;
                """,
                int(user_id),
                int(state.absolute_week),
            )
            return state, region, row
        finally:
            if local:
                await self.bot.pool.release(conn)

    async def _sync_legacy_discoveries(self, user_id: int, *, force: bool = False) -> dict:
        """Seed discovery history from already-linked inventory and requests."""

        user_id = int(user_id)
        if user_id in self._synced_users and not force:
            return {"pets": 0, "eggs": 0, "created": 0}
        catalog = self.catalog
        if catalog is None:
            return {"pets": 0, "eggs": 0, "created": 0}

        async with self.bot.pool.acquire() as conn:
            pets = await conn.fetch(
                """
                SELECT id AS pet_id, frontier_species_id AS species_id
                FROM monster_pets
                WHERE user_id = $1 AND frontier_species_id IS NOT NULL
                ORDER BY id;
                """,
                user_id,
            )
            eggs = await conn.fetch(
                """
                SELECT id AS egg_id, frontier_species_id AS species_id
                FROM monster_eggs
                WHERE user_id = $1 AND frontier_species_id IS NOT NULL
                ORDER BY id;
                """,
                user_id,
            )
            # Completed requests predate stable IDs.  Parent names identify all
            # but the two known legacy variant pairs; is_primary is the safe,
            # deterministic compatibility choice for those ambiguous rows.
            created = await conn.fetch(
                """
                SELECT sr.id AS request_id, chosen.recipe_id,
                       chosen.result_species_id
                FROM splice_requests sr
                JOIN LATERAL (
                    SELECT r.recipe_id, r.result_species_id
                    FROM frontier_recipes r
                    WHERE (
                        lower(btrim(COALESCE(r.legacy_parent_a_name, ''))) =
                            lower(btrim(COALESCE(sr.pet1_default, '')))
                        AND lower(btrim(COALESCE(r.legacy_parent_b_name, ''))) =
                            lower(btrim(COALESCE(sr.pet2_default, '')))
                    ) OR (
                        lower(btrim(COALESCE(r.legacy_parent_a_name, ''))) =
                            lower(btrim(COALESCE(sr.pet2_default, '')))
                        AND lower(btrim(COALESCE(r.legacy_parent_b_name, ''))) =
                            lower(btrim(COALESCE(sr.pet1_default, '')))
                    )
                    ORDER BY r.is_primary DESC, r.variant_rank ASC, r.recipe_id ASC
                    LIMIT 1
                ) chosen ON TRUE
                WHERE sr.user_id = $1 AND sr.status = 'completed';
                """,
                user_id,
            )

        inserted = {"pets": 0, "eggs": 0, "created": 0}
        for row in pets:
            if await catalog.record_discovery(
                user_id,
                "ownership_gained",
                species_id=int(row["species_id"]),
                source="legacy_inventory_sync",
                dedupe_key=f"monster-pet:{int(row['pet_id'])}",
            ):
                inserted["pets"] += 1
        for row in eggs:
            if await catalog.record_discovery(
                user_id,
                "egg_obtained",
                species_id=int(row["species_id"]),
                source="legacy_inventory_sync",
                dedupe_key=f"monster-egg:{int(row['egg_id'])}",
            ):
                inserted["eggs"] += 1
        for row in created:
            if await catalog.record_discovery(
                user_id,
                "created",
                species_id=int(row["result_species_id"]),
                recipe_id=int(row["recipe_id"]),
                source="legacy_splice_request_sync",
                dedupe_key=f"splice-request:{int(row['request_id'])}",
            ):
                inserted["created"] += 1
        self._synced_users.add(user_id)
        return inserted

    async def _resolve_encounter_species(self, monster: Mapping[str, Any]):
        catalog = self.catalog
        if catalog is None:
            return None
        species_id = _safe_int(monster.get("frontier_species_id"))
        pool_name = str(monster.get("pve_pool") or "").casefold()
        prefer = "splice" if pool_name in {"frontier", "splice"} else "wild"
        return await catalog.resolve_species(
            str(monster.get("name") or ""),
            species_id=species_id,
            prefer_origin=prefer,
        )

    @commands.Cog.listener()
    async def on_frontier_sighting(
        self,
        ctx,
        monster: Mapping[str, Any],
        encounter_id=None,
    ) -> None:
        if not monster or not getattr(ctx, "author", None):
            return
        species = await self._resolve_encounter_species(monster)
        if not species or self.catalog is None:
            return
        message_id = getattr(getattr(ctx, "message", None), "id", None)
        identity = encounter_id if encounter_id is not None else message_id
        await self.catalog.record_discovery(
            ctx.author.id,
            "sighted",
            species_id=int(species["species_id"]),
            recipe_id=_safe_int(monster.get("frontier_recipe_id")),
            source="frontier_sighting",
            dedupe_key=f"frontier-sighting:{identity}:{species['stable_key']}",
            metadata={
                "region_id": monster.get("frontier_region_id"),
                "role": monster.get("frontier_role"),
            },
        )

    @commands.Cog.listener()
    async def on_frontier_egg_obtained(
        self,
        ctx,
        monster: Mapping[str, Any],
        egg_id=None,
    ) -> None:
        if not monster or not getattr(ctx, "author", None):
            return
        species = await self._resolve_encounter_species(monster)
        if not species or self.catalog is None:
            return
        parsed_egg_id = _safe_int(egg_id)
        await self.catalog.record_discovery(
            ctx.author.id,
            "egg_obtained",
            species_id=int(species["species_id"]),
            recipe_id=_safe_int(monster.get("frontier_recipe_id")),
            source="frontier_egg_drop",
            dedupe_key=(
                f"monster-egg:{parsed_egg_id}"
                if parsed_egg_id is not None
                else f"frontier-egg-message:{getattr(getattr(ctx, 'message', None), 'id', id(ctx))}:{species['stable_key']}"
            ),
        )
        if parsed_egg_id is not None:
            async with self.bot.pool.acquire() as conn:
                await conn.execute(
                    """
                    UPDATE monster_eggs
                    SET frontier_species_id = $1
                    WHERE id = $2 AND user_id = $3;
                    """,
                    int(species["species_id"]),
                    parsed_egg_id,
                    int(ctx.author.id),
                )

    @commands.Cog.listener()
    async def on_frontier_pet_hatched(
        self,
        user_id,
        pet_id,
        species_id=None,
    ) -> None:
        """Carry a linked egg's stable identity into its new owned pet."""

        parsed_user_id = _safe_int(user_id)
        parsed_pet_id = _safe_int(pet_id)
        parsed_species_id = _safe_int(species_id)
        if not parsed_user_id or parsed_pet_id is None or self.catalog is None:
            return
        if parsed_species_id is None:
            async with self.bot.pool.acquire() as conn:
                parsed_species_id = await conn.fetchval(
                    """
                    SELECT frontier_species_id FROM monster_pets
                    WHERE id = $1 AND user_id = $2;
                    """,
                    parsed_pet_id,
                    parsed_user_id,
                )
        parsed_species_id = _safe_int(parsed_species_id)
        if parsed_species_id is None:
            return
        await self.catalog.record_discovery(
            parsed_user_id,
            "ownership_gained",
            species_id=parsed_species_id,
            source="monster_egg_hatch",
            dedupe_key=f"monster-pet:{parsed_pet_id}",
        )

    @commands.Cog.listener()
    async def on_frontier_splice_created(
        self,
        user_or_ctx,
        result_name,
        legacy_splice_id=None,
        request_id=None,
        pet_id=None,
    ) -> None:
        user = getattr(user_or_ctx, "author", user_or_ctx)
        user_id = _safe_int(getattr(user, "id", user))
        if not user_id or not result_name or self.catalog is None:
            return
        species = await self.catalog.resolve_species(
            str(result_name), prefer_origin="splice"
        )
        recipe_id = None
        parsed_legacy_id = _safe_int(legacy_splice_id)
        if parsed_legacy_id is not None:
            async with self.bot.pool.acquire() as conn:
                recipe_id = await conn.fetchval(
                    "SELECT recipe_id FROM frontier_recipes WHERE legacy_splice_id = $1;",
                    parsed_legacy_id,
                )
        if species is None or (parsed_legacy_id is not None and recipe_id is None):
            # Splice creation commits to the legacy tables first.  Refresh only
            # when its new identity/link is absent; known automatic outcomes do
            # not needlessly re-import the entire legacy catalogue.
            await self.catalog.refresh_legacy()
            species = await self.catalog.resolve_species(
                str(result_name), prefer_origin="splice"
            )
            if parsed_legacy_id is not None:
                async with self.bot.pool.acquire() as conn:
                    recipe_id = await conn.fetchval(
                        "SELECT recipe_id FROM frontier_recipes WHERE legacy_splice_id = $1;",
                        parsed_legacy_id,
                    )
        if not species:
            log.warning("New splice %r could not be refreshed into Frontier catalog", result_name)
            return
        parsed_request_id = _safe_int(request_id)
        parsed_pet_id = _safe_int(pet_id)
        creation_key = (
            f"splice-request:{parsed_request_id}"
            if parsed_request_id is not None
            else f"monster-pet-created:{parsed_pet_id}"
            if parsed_pet_id is not None
            else f"splice-created:{parsed_legacy_id or result_name}"
        )
        await self.catalog.record_discovery(
            user_id,
            "created",
            species_id=int(species["species_id"]),
            recipe_id=_safe_int(recipe_id),
            source="soulforge_creation",
            dedupe_key=creation_key,
        )
        await self.catalog.record_discovery(
            user_id,
            "ownership_gained",
            species_id=int(species["species_id"]),
            recipe_id=_safe_int(recipe_id),
            source="soulforge_creation",
            dedupe_key=(
                f"monster-pet:{parsed_pet_id}"
                if parsed_pet_id is not None
                else f"splice-owned:{parsed_request_id or parsed_legacy_id or result_name}"
            ),
        )
        async with self.bot.pool.acquire() as conn:
            if parsed_pet_id is not None:
                await conn.execute(
                    """
                    UPDATE monster_pets SET frontier_species_id = $1
                    WHERE id = $2 AND user_id = $3;
                    """,
                    int(species["species_id"]),
                    parsed_pet_id,
                    user_id,
                )
            await conn.execute(
                """
                UPDATE frontier_lineage_tracks
                SET status = 'completed', completed_at = COALESCE(completed_at, NOW()),
                    updated_at = NOW()
                WHERE user_id = $1 AND target_species_id = $2 AND status = 'active';
                """,
                user_id,
                int(species["species_id"]),
            )

    @commands.Cog.listener()
    async def on_PVE_completion(
        self,
        ctx,
        success,
        monster_name=None,
        element=None,
        levelchoice=None,
        battle_id=None,
    ) -> None:
        if not success or not getattr(ctx, "author", None):
            return
        if getattr(ctx, "_frontier_completion_recorded", False):
            return
        monster = getattr(ctx, "frontier_encounter", None)
        if not isinstance(monster, Mapping):
            monster = getattr(ctx, "monster_override", None)
        if not isinstance(monster, Mapping):
            if not monster_name:
                return
            monster = {"name": monster_name, "element": element}

        # PvE currently emits a legacy two-argument completion and then its
        # detailed completion.  Claim this context before the first await so
        # both scheduled listener tasks cannot race and count one win twice.
        setattr(ctx, "_frontier_completion_recorded", True)
        species = await self._resolve_encounter_species(monster)
        if not species or self.catalog is None:
            return
        message_id = getattr(getattr(ctx, "message", None), "id", None)
        role = str(monster.get("frontier_role") or "wild").casefold()
        defeat_key = event_key_for_battle(
            battle_id,
            message_id,
            str(species["stable_key"]),
            role,
        )
        await self.catalog.record_discovery(
            ctx.author.id,
            "defeated",
            species_id=int(species["species_id"]),
            recipe_id=_safe_int(monster.get("frontier_recipe_id")),
            source="pve_victory",
            dedupe_key=f"pve-defeat:{defeat_key}",
            metadata={"tier": levelchoice, "role": role},
        )
        if role_counter_column(role) is not None:
            await self._record_weekly_defeat(
                ctx,
                monster,
                species,
                role,
                defeat_key,
            )

    async def _record_weekly_defeat(
        self,
        ctx,
        monster: Mapping[str, Any],
        species: Mapping[str, Any],
        role: str,
        event_key: str,
    ) -> bool:
        if str(monster.get("pve_pool") or "").casefold() != "frontier":
            return False
        state = get_rotation_state(self.config)
        if str(monster.get("frontier_region_id") or "") != state.region_id:
            return False
        event_week = _safe_int(monster.get("frontier_rotation_week"))
        if event_week is not None and event_week != state.absolute_week:
            return False
        player_level = await self._profile_level(ctx.author.id, ctx=ctx)
        region = get_region(self.config, state.region_id)
        if not region_is_unlocked(player_level, region):
            return False
        counter = role_counter_column(role)
        if counter is None:
            return False

        async with self.bot.pool.acquire() as conn:
            async with conn.transaction():
                _, _, progress = await self._weekly_row(
                    ctx.author.id,
                    player_level=player_level,
                    create=True,
                    conn=conn,
                )
                if progress is None:
                    return False
                inserted = await conn.fetchval(
                    """
                    INSERT INTO frontier_weekly_defeats (
                        user_id, absolute_week, event_key, region_id,
                        species_id, species_key, role
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7)
                    ON CONFLICT (user_id, absolute_week, event_key) DO NOTHING
                    RETURNING 1;
                    """,
                    int(ctx.author.id),
                    int(state.absolute_week),
                    str(event_key),
                    str(state.region_id),
                    int(species["species_id"]),
                    str(species["stable_key"]),
                    str(role),
                )
                if not inserted:
                    return False
                # The column is selected from a closed mapping above, never user input.
                await conn.execute(
                    f"""
                    UPDATE frontier_weekly_progress
                    SET {counter} = {counter} + 1,
                        distinct_species = (
                            SELECT COUNT(DISTINCT species_key)::INTEGER
                            FROM frontier_weekly_defeats
                            WHERE user_id = $1 AND absolute_week = $2
                              AND role IN ('regular', 'elite')
                        ),
                        updated_at = NOW()
                    WHERE user_id = $1 AND absolute_week = $2;
                    """,
                    int(ctx.author.id),
                    int(state.absolute_week),
                )
        return True

    @commands.group(
        name="frontier",
        aliases=["frontiers"],
        invoke_without_command=True,
        case_insensitive=True,
        brief="Explore the rotating Soulforge Frontiers",
    )
    @has_char()
    async def frontier(self, ctx) -> None:
        """Open the Soulforge Frontiers hub."""

        await self._sync_legacy_discoveries(ctx.author.id)
        level = await self._profile_level(ctx.author.id, ctx=ctx)
        state, region, row = await self._weekly_row(
            ctx.author.id, player_level=level, create=True
        )
        unlocked = row is not None
        progress = WeeklyProgress.from_mapping(_row_dict(row))
        now = dt.datetime.now(dt.timezone.utc)
        pages = [
            self._build_region_overview_embed(
                state=state,
                region=region,
                progress=progress,
                unlocked=unlocked,
                level=level,
            ),
            self._build_research_embed(
                state=state,
                region=region,
                progress=progress,
                unlocked=unlocked,
                level=level,
            ),
            self._build_forecast_embed(level=level, now=now),
            self._build_guide_embed(state=state, region=region),
        ]
        await FrontierDashboardView(ctx, pages).start()

    @frontier.command(name="forecast", aliases=["rotation", "regions"])
    @has_char()
    async def frontier_forecast(self, ctx) -> None:
        """Show the current and next three Frontier regions."""

        now = dt.datetime.now(dt.timezone.utc)
        level = await self._profile_level(ctx.author.id, ctx=ctx)
        await ctx.send(embed=self._build_forecast_embed(level=level, now=now))

    @frontier.command(name="progress", aliases=["weekly", "objectives"])
    @has_char()
    async def frontier_progress(self, ctx) -> None:
        """Show this week's objectives and boss state."""

        level = await self._profile_level(ctx.author.id, ctx=ctx)
        state, region, row = await self._weekly_row(
            ctx.author.id, player_level=level, create=True
        )
        progress = WeeklyProgress.from_mapping(_row_dict(row))
        await ctx.send(
            embed=self._build_research_embed(
                state=state,
                region=region,
                progress=progress,
                unlocked=row is not None,
                level=level,
            )
        )

    async def _bestiary_rows(self, user_id: int, limit: int, offset: int):
        async with self.bot.pool.acquire() as conn:
            total = await conn.fetchval(
                """
                SELECT COUNT(*) FROM frontier_species
                WHERE origin = 'wild' AND publication_status = 'approved';
                """
            )
            rows = await conn.fetch(
                """
                WITH pet_counts AS (
                    SELECT frontier_species_id AS species_id, COUNT(*)::INTEGER AS n
                    FROM monster_pets WHERE user_id = $1 AND frontier_species_id IS NOT NULL
                    GROUP BY frontier_species_id
                ), egg_counts AS (
                    SELECT frontier_species_id AS species_id, COUNT(*)::INTEGER AS n
                    FROM monster_eggs
                    WHERE user_id = $1 AND frontier_species_id IS NOT NULL AND hatched = FALSE
                    GROUP BY frontier_species_id
                )
                SELECT s.*, d.first_sighted_at, d.first_defeated_at, d.first_egg_at,
                       d.first_owned_at, d.first_created_at, d.mastered_at,
                       COALESCE(p.n, 0) AS current_pet_count,
                       COALESCE(e.n, 0) AS current_egg_count
                FROM frontier_species s
                LEFT JOIN frontier_discoveries d
                    ON d.species_id = s.species_id AND d.user_id = $1
                LEFT JOIN pet_counts p ON p.species_id = s.species_id
                LEFT JOIN egg_counts e ON e.species_id = s.species_id
                WHERE s.origin = 'wild' AND s.publication_status = 'approved'
                ORDER BY COALESCE(s.legacy_tier, 999), s.canonical_name, s.species_id
                LIMIT $2 OFFSET $3;
                """,
                int(user_id),
                int(limit),
                int(offset),
            )
        return int(total or 0), rows

    def _build_bestiary_pages(
        self, rows: list[Mapping[str, Any]], total: int
    ) -> tuple[list[discord.Embed], list[str]]:
        rows = [dict(row) for row in rows]
        revealed = sum(1 for row in rows if species_is_known(row))
        percentage = (revealed / total * 100) if total else 0.0
        counts = {
            "sighted": sum(bool(row.get("first_sighted_at")) for row in rows),
            "defeated": sum(bool(row.get("first_defeated_at")) for row in rows),
            "eggs": sum(
                bool(row.get("first_egg_at") or row.get("current_egg_count"))
                for row in rows
            ),
            "created": sum(bool(row.get("first_created_at")) for row in rows),
            "owned": sum(
                bool(row.get("first_owned_at") or row.get("current_pet_count"))
                for row in rows
            ),
            "mastered": sum(bool(row.get("mastered_at")) for row in rows),
        }
        overview = discord.Embed(
            title="📖 Wild Bestiary",
            description=(
                "Your permanent field record of every approved wild species. "
                "A species is revealed when you sight or defeat it, obtain its egg, "
                "create it, or own it.\n\n"
                f"`{progress_bar(revealed, total, width=16)}`\n"
                f"**{revealed:,}/{total:,} revealed** · {percentage:.1f}% complete"
            ),
            color=self._colour(),
        )
        overview.add_field(
            name="Field Encounters",
            value=(
                f"👁️ Sighted **{counts['sighted']:,}**\n"
                f"⚔️ Defeated **{counts['defeated']:,}**\n"
                f"🥚 Eggs found **{counts['eggs']:,}**"
            ),
            inline=True,
        )
        overview.add_field(
            name="Soulforge Record",
            value=(
                f"🧬 Created **{counts['created']:,}**\n"
                f"🐾 Owned **{counts['owned']:,}**\n"
                f"⭐ Mastered **{counts['mastered']:,}**"
            ),
            inline=True,
        )
        overview.add_field(
            name="Catalog",
            value=(
                f"📚 Published **{total:,}**\n"
                f"🔓 Revealed **{revealed:,}**\n"
                f"🔒 Remaining **{max(0, total - revealed):,}**"
            ),
            inline=True,
        )
        overview.add_field(
            name="Entry Legend",
            value=(
                "🔒 Undiscovered · 👁️ Sighted · ⚔️ Defeated · 🥚 Egg Obtained\n"
                "🧬 Personally Created · 🐾 Owned · ⭐ Mastered"
            ),
            inline=False,
        )
        overview.set_footer(
            text="Choose a page above or use Next to begin browsing the catalog"
        )

        pages = [overview]
        labels = ["Overview · Collection totals"]
        for offset in range(0, len(rows), COLLECTION_PAGE_SIZE):
            chunk = rows[offset : offset + COLLECTION_PAGE_SIZE]
            page_number = (offset // COLLECTION_PAGE_SIZE) + 1
            total_pages = max(
                1, (len(rows) + COLLECTION_PAGE_SIZE - 1) // COLLECTION_PAGE_SIZE
            )
            lines = []
            first_known_image = ""
            tiers = []
            for item_index, data in enumerate(chunk, start=offset + 1):
                tier = data.get("legacy_tier") or "?"
                if isinstance(tier, int):
                    tiers.append(tier)
                if not species_is_known(data):
                    lines.append(
                        f"`{item_index:03}` 🔒 **Undiscovered Species**\n"
                        f"└ Tier **{tier}** · Identity concealed"
                    )
                    continue
                state_name = species_collection_state(data)
                state_emoji = COLLECTION_STATE_EMOJIS.get(state_name, "▫️")
                element = str(data.get("element") or "Unknown")
                lines.append(
                    f"`{item_index:03}` {state_emoji} **{str(data['canonical_name'])[:70]}**\n"
                    f"└ {_element_emoji(element)} {element} · Tier **{tier}** · {state_name}"
                )
                if not first_known_image:
                    first_known_image = _valid_image_url(data.get("image_url"))

            embed = discord.Embed(
                title="📖 Wild Bestiary · Species Journal",
                description="\n\n".join(lines) or "No published species on this page.",
                color=self._colour(),
            )
            if first_known_image:
                embed.set_thumbnail(url=first_known_image)
            end = min(offset + COLLECTION_PAGE_SIZE, len(rows))
            embed.set_footer(
                text=(
                    f"Species {offset + 1}–{end} of {total} · "
                    f"Page {page_number}/{total_pages} · Revealed {revealed}/{total}"
                )
            )
            pages.append(embed)
            if tiers:
                tier_label = (
                    f"Tier {min(tiers)}"
                    if min(tiers) == max(tiers)
                    else f"Tiers {min(tiers)}–{max(tiers)}"
                )
            else:
                tier_label = "Unknown tiers"
            labels.append(f"Page {page_number} · {tier_label}")
        return pages, labels

    @frontier.command(name="bestiary", aliases=["wilds"])
    @has_char()
    async def frontier_bestiary(self, ctx, page: int = 0) -> None:
        """Browse the finite wild-species collection."""

        await self._sync_legacy_discoveries(ctx.author.id)
        total, rows = await self._bestiary_rows(ctx.author.id, 10_000, 0)
        pages, labels = self._build_bestiary_pages(
            [dict(row) for row in rows], total
        )
        await FrontierBookView(
            ctx,
            pages,
            labels=labels,
            initial_index=max(0, int(page or 0)),
        ).start()

    def _build_archive_pages(
        self,
        rows: list[Mapping[str, Any]],
        *,
        catalog_total: int,
    ) -> tuple[list[discord.Embed], list[str]]:
        rows = [dict(row) for row in rows]
        discovered = len(rows)
        percentage = (discovered / catalog_total * 100) if catalog_total else 0.0
        created = sum(bool(row.get("first_created_at")) for row in rows)
        owned = sum(
            bool(row.get("first_owned_at") or row.get("current_pet_count"))
            for row in rows
        )
        mastered = sum(bool(row.get("mastered_at")) for row in rows)
        highest_generation = max(
            (int(row.get("generation") or 0) for row in rows), default=0
        )
        overview = discord.Embed(
            title="🧬 Soulforge Archive",
            description=(
                "Every splice lineage you have encountered, created, hatched, or owned.\n\n"
                f"`{progress_bar(discovered, catalog_total, width=16)}`\n"
                f"**{discovered:,}/{catalog_total:,} catalogued** · {percentage:.1f}% of the known Archive"
            ),
            color=self._colour(),
        )
        overview.add_field(name="Discovered", value=f"📚 **{discovered:,}** species")
        overview.add_field(name="Created", value=f"🧬 **{created:,}** species")
        overview.add_field(name="Owned", value=f"🐾 **{owned:,}** species")
        overview.add_field(name="Mastered", value=f"⭐ **{mastered:,}** species")
        overview.add_field(name="Highest Generation", value=f"🔬 **Gen {highest_generation}**")
        overview.add_field(name="Known Catalog", value=f"🌐 **{catalog_total:,}** species")
        overview.add_field(
            name="Explore a Lineage",
            value=(
                "Use **`$frontier lineage <creature>`** to inspect parents and descendants.\n"
                "Use **`$frontier track <creature>`** to make one lineage your active target."
            ),
            inline=False,
        )
        overview.set_footer(text="Choose a page above or use Next to browse your discoveries")

        pages = [overview]
        labels = ["Overview · Archive totals"]
        for offset in range(0, len(rows), COLLECTION_PAGE_SIZE):
            chunk = rows[offset : offset + COLLECTION_PAGE_SIZE]
            page_number = (offset // COLLECTION_PAGE_SIZE) + 1
            total_pages = max(
                1, (len(rows) + COLLECTION_PAGE_SIZE - 1) // COLLECTION_PAGE_SIZE
            )
            lines = []
            first_image = ""
            generations = []
            for data in chunk:
                state_name = species_collection_state(data)
                state_emoji = COLLECTION_STATE_EMOJIS.get(state_name, "▫️")
                generation = data.get("generation")
                if generation is not None:
                    generations.append(int(generation))
                generation_text = f"Gen {generation}" if generation is not None else "Gen ?"
                element = str(data.get("element") or "Unknown")
                lines.append(
                    f"{state_emoji} **{str(data['canonical_name'])[:70]}**\n"
                    f"└ {generation_text} · {str(data.get('stability') or 'unknown').title()} · "
                    f"{_element_emoji(element)} {element} · {state_name}"
                )
                if not first_image:
                    first_image = _valid_image_url(data.get("image_url"))
            embed = discord.Embed(
                title="🧬 Soulforge Archive · Lineage Journal",
                description="\n\n".join(lines) or "No splice species on this page.",
                color=self._colour(),
            )
            if first_image:
                embed.set_thumbnail(url=first_image)
            end = min(offset + COLLECTION_PAGE_SIZE, len(rows))
            embed.set_footer(
                text=(
                    f"Discoveries {offset + 1}–{end} of {discovered} · "
                    f"Page {page_number}/{total_pages} · Known catalog {catalog_total}"
                )
            )
            pages.append(embed)
            if generations:
                generation_label = (
                    f"Gen {min(generations)}"
                    if min(generations) == max(generations)
                    else f"Gen {min(generations)}–{max(generations)}"
                )
            else:
                generation_label = "Unknown generation"
            labels.append(f"Page {page_number} · {generation_label}")
        return pages, labels

    @frontier.command(name="archive", aliases=["splices", "codex"])
    @has_char()
    async def frontier_archive(self, ctx, page: int = 0) -> None:
        """Browse splice species the player has encountered or held."""

        await self._sync_legacy_discoveries(ctx.author.id)
        summary = await self.catalog.get_player_summary(ctx.author.id)
        async with self.bot.pool.acquire() as conn:
            total = await conn.fetchval(
                """
                SELECT COUNT(*)
                FROM frontier_species s
                WHERE s.origin = 'splice' AND (
                    EXISTS (
                        SELECT 1 FROM frontier_discoveries d
                        WHERE d.user_id = $1 AND d.species_id = s.species_id
                    ) OR EXISTS (
                        SELECT 1 FROM monster_pets p
                        WHERE p.user_id = $1
                          AND p.frontier_species_id = s.species_id
                    ) OR EXISTS (
                        SELECT 1 FROM monster_eggs e
                        WHERE e.user_id = $1 AND e.hatched = FALSE
                          AND e.frontier_species_id = s.species_id
                    )
                );
                """,
                int(ctx.author.id),
            )
        rows = []
        for offset in range(0, int(total or 0), 200):
            rows.extend(
                await self.catalog.list_player_species(
                    ctx.author.id,
                    origin="splice",
                    limit=200,
                    offset=offset,
                )
            )
        pages, labels = self._build_archive_pages(
            rows,
            catalog_total=int(summary.get("total_splice_species", 0)),
        )
        await FrontierBookView(
            ctx,
            pages,
            labels=labels,
            initial_index=max(0, int(page or 0)),
        ).start()

    @frontier.command(name="lineage", aliases=["tree"])
    @has_char()
    async def frontier_lineage(self, ctx, *, creature: str) -> None:
        """Show a splice creature's parents and immediate descendants."""

        species = await self.catalog.resolve_species(creature, prefer_origin="splice")
        if not species or species.get("origin") != "splice":
            return await ctx.send("That creature is not in the Soulforge Archive.")
        species_id = int(species["species_id"])
        async with self.bot.pool.acquire() as conn:
            parents = await conn.fetch(
                """
                SELECT r.recipe_id, r.generation, r.is_primary,
                       a.canonical_name AS parent_a, b.canonical_name AS parent_b,
                       COUNT(*) OVER()::INTEGER AS total_count
                FROM frontier_recipes r
                JOIN frontier_species a ON a.species_id = r.parent_low_species_id
                JOIN frontier_species b ON b.species_id = r.parent_high_species_id
                WHERE r.result_species_id = $1
                ORDER BY r.is_primary DESC, r.variant_rank, r.recipe_id
                LIMIT 8;
                """,
                species_id,
            )
            children = await conn.fetch(
                """
                WITH descendants AS (
                    SELECT DISTINCT child.canonical_name, r.generation
                    FROM frontier_recipes r
                    JOIN frontier_species child
                        ON child.species_id = r.result_species_id
                    WHERE r.parent_low_species_id = $1 OR r.parent_high_species_id = $1
                )
                SELECT *, COUNT(*) OVER()::INTEGER AS total_count
                FROM descendants
                ORDER BY generation NULLS LAST, canonical_name
                LIMIT 12;
                """,
                species_id,
            )
        parent_lines = [
            f"{'⭐ ' if row['is_primary'] else ''}{row['parent_a']} + {row['parent_b']}"
            for row in parents
        ]
        child_lines = [
            f"{row['canonical_name']} (Gen {row['generation'] if row['generation'] is not None else '?'})"
            for row in children
        ]
        embed = discord.Embed(
            title=f"🧬 {species['canonical_name']}",
            description=(
                f"**Generation {species.get('generation') if species.get('generation') is not None else '?'}** · "
                f"{str(species.get('stability') or 'unknown').title()} stability · "
                f"{_element_emoji(species.get('element'))} {species.get('element') or 'Unknown'}"
            ),
            color=self._colour(),
        )
        image_url = str(species.get("image_url") or "")
        if image_url.startswith(("https://", "http://")):
            embed.set_thumbnail(url=image_url)
        embed.add_field(
            name="⬆️ Known Parent Recipes",
            value="\n".join(parent_lines)[:1024] or "No connected parent recipe.",
            inline=False,
        )
        embed.add_field(
            name="⬇️ Immediate Descendants",
            value="\n".join(child_lines)[:1024] or "No known descendants.",
            inline=False,
        )
        parent_total = int(parents[0]["total_count"]) if parents else 0
        child_total = int(children[0]["total_count"]) if children else 0
        embed.set_footer(
            text=(
                f"Showing {len(parents)}/{parent_total} parent recipes · "
                f"{len(children)}/{child_total} descendants · ⭐ primary legacy outcome"
            )
        )
        await ctx.send(embed=embed)

    @frontier.command(name="track", aliases=["target"])
    @has_char()
    async def frontier_track(self, ctx, *, creature: str = "") -> None:
        """Track one target splice lineage, or use `clear`."""

        query = str(creature or "").strip()
        async with self.bot.pool.acquire() as conn:
            if not query:
                row = await conn.fetchrow(
                    """
                    SELECT * FROM frontier_lineage_tracks
                    WHERE user_id = $1 AND status = 'active'
                    ORDER BY updated_at DESC LIMIT 1;
                    """,
                    int(ctx.author.id),
                )
                if not row:
                    return await ctx.send(
                        embed=discord.Embed(
                            title="🧬 No Active Lineage",
                            description=(
                                "Choose a splice creation target with "
                                "**`$frontier track <creature>`**."
                            ),
                            color=self._colour(),
                        )
                    )
                return await ctx.send(
                    embed=discord.Embed(
                        title="🧬 Active Lineage Target",
                        description=(
                            f"You are tracking **{row['target_name_snapshot']}**.\n\n"
                            "Personally create it to complete this lineage. Use "
                            f"**`$frontier lineage {row['target_name_snapshot']}`** "
                            "to inspect its known path."
                        ),
                        color=self._colour(),
                    )
                )
            if query.casefold() in {"clear", "stop", "none", "off"}:
                result = await conn.execute(
                    """
                    UPDATE frontier_lineage_tracks
                    SET status = 'abandoned', updated_at = NOW()
                    WHERE user_id = $1 AND status = 'active';
                    """,
                    int(ctx.author.id),
                )
                return await ctx.send(
                    "Lineage tracking cleared."
                    if result != "UPDATE 0"
                    else "You were not tracking a lineage."
                )

        species = await self.catalog.resolve_species(query, prefer_origin="splice")
        if not species or species.get("origin") != "splice":
            return await ctx.send("Choose a known splice creature from the Archive.")
        await self._sync_legacy_discoveries(ctx.author.id)
        async with self.bot.pool.acquire() as conn:
            created = await conn.fetchval(
                """
                SELECT first_created_at IS NOT NULL FROM frontier_discoveries
                WHERE user_id = $1 AND species_id = $2;
                """,
                int(ctx.author.id),
                int(species["species_id"]),
            )
            async with conn.transaction():
                await conn.execute(
                    """
                    UPDATE frontier_lineage_tracks
                    SET status = 'abandoned', updated_at = NOW()
                    WHERE user_id = $1 AND status = 'active'
                      AND target_species_id <> $2;
                    """,
                    int(ctx.author.id),
                    int(species["species_id"]),
                )
                await conn.execute(
                    """
                    INSERT INTO frontier_lineage_tracks (
                        user_id, target_species_id, target_name_snapshot,
                        status, completed_at
                    ) VALUES ($1, $2, $3, $4, CASE WHEN $4 = 'completed' THEN NOW() END)
                    ON CONFLICT (user_id, target_species_id) DO UPDATE SET
                        target_name_snapshot = EXCLUDED.target_name_snapshot,
                        status = CASE
                            WHEN frontier_lineage_tracks.status = 'completed'
                                THEN 'completed'
                            ELSE EXCLUDED.status
                        END,
                        completed_at = CASE
                            WHEN frontier_lineage_tracks.status = 'completed'
                                THEN frontier_lineage_tracks.completed_at
                            ELSE EXCLUDED.completed_at
                        END,
                        updated_at = NOW();
                    """,
                    int(ctx.author.id),
                    int(species["species_id"]),
                    str(species["canonical_name"]),
                    "completed" if created else "active",
                )
        if created:
            await ctx.send(
                embed=discord.Embed(
                    title="✅ Lineage Already Complete",
                    description=(
                        f"You have already personally created **{species['canonical_name']}**. "
                        "This lineage remains recorded as complete."
                    ),
                    color=0x4CAF72,
                )
            )
        else:
            await ctx.send(
                embed=discord.Embed(
                    title="🧬 Lineage Target Set",
                    description=(
                        f"Now tracking **{species['canonical_name']}**.\n\n"
                        f"Use **`$frontier lineage {species['canonical_name']}`** "
                        "to inspect its known creation path."
                    ),
                    color=self._colour(),
                )
            )

    async def _build_boss_monster(self, region_id: str) -> Optional[dict]:
        battles = self.bot.get_cog("Battles")
        if battles is not None:
            provider = getattr(battles, "get_frontier_boss_encounter", None)
            if provider is not None:
                result = provider(region_id)
                if inspect.isawaitable(result):
                    result = await result
                if result:
                    return dict(result)

        if battles is not None and getattr(battles, "monsters_data", None):
            public_pool = battles.monsters_data
        else:
            public_pool = json.loads(MONSTERS_PATH.read_text(encoding="utf-8"))
        async with self.bot.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, pet1_default, pet2_default, result_name, hp, attack,
                       defense, element, url, frontier_recipe_id,
                       frontier_result_species_id
                FROM splice_combinations ORDER BY id;
                """
            )
        base_names = {
            str(monster.get("name") or "").strip()
            for monsters in public_pool.values()
            for monster in monsters
            if str(monster.get("name") or "").strip()
        }
        generations = resolve_recipe_generations(base_names, rows)
        boss = build_frontier_boss_encounter(
            self.config,
            region_id,
            public_pool,
            rows,
            generation_by_recipe_id=generations,
        )
        if boss:
            source = next(
                (row for row in rows if int(row["id"]) == int(boss["legacy_splice_id"])),
                None,
            )
            if source:
                boss["frontier_recipe_id"] = source["frontier_recipe_id"]
                boss["frontier_species_id"] = source["frontier_result_species_id"]
        return boss

    @frontier.command(name="boss", aliases=["challenge"])
    @has_char()
    async def frontier_boss(self, ctx) -> None:
        """Challenge this week's regional boss after finishing research."""

        level = await self._profile_level(ctx.author.id, ctx=ctx)
        state, region, row = await self._weekly_row(
            ctx.author.id, player_level=level, create=True
        )
        if row is None:
            return await ctx.send(
                f"🔒 **{region['name']}** requires Level {region['unlock_level']}."
            )
        progress = WeeklyProgress.from_mapping(_row_dict(row))
        if not boss_is_unlocked(progress):
            return await ctx.send(
                "The regional boss is still locked:\n" + "\n".join(objective_lines(progress)[:3])
            )
        if progress.boss_defeats >= 1:
            return await ctx.send(
                "✅ You already cleared this rotation's regional boss. "
                "Use `$frontier claim` if its reward is still waiting."
            )
        pve_command = self.bot.get_command("pve")
        if pve_command is None:
            return await ctx.send("PvE is temporarily unavailable.")
        monster = await self._build_boss_monster(state.region_id)
        if not monster:
            return await ctx.send(
                "This week's boss could not be loaded safely. Please contact a GM."
            )
        cooldown_key = f"cd:{ctx.author.id}:{pve_command.qualified_name}"
        acquired = await self.bot.redis.execute_command(
            "SET", cooldown_key, "frontier-boss", "NX", "EX", 60 * 30
        )
        if not acquired:
            ttl = await self.bot.redis.execute_command("TTL", cooldown_key)
            ttl = max(0, int(ttl or 0))
            hours, remainder = divmod(ttl, 3600)
            minutes, seconds = divmod(remainder, 60)
            return await ctx.send(
                f"You can challenge another PvE encounter in "
                f"**{hours:02}:{minutes:02}:{seconds:02}**."
            )
        ctx.monster_override = monster
        ctx.frontier_encounter = monster
        ctx.levelchoice_override = int(monster["pve_tier"])
        ctx.locationchoice_override = str(state.region_id)
        # Context.invoke intentionally bypasses checks and does not replace
        # ctx.command. Temporarily expose the real PvE command so any safe
        # early-exit path inside Battles resets the PvE cooldown key we acquired
        # above, rather than trying to reset `frontier boss`.
        previous_command = getattr(ctx, "command", None)
        ctx.command = pve_command
        try:
            await ctx.invoke(pve_command)
        except BaseException:
            await self.bot.redis.execute_command("DEL", cooldown_key)
            raise
        finally:
            ctx.command = previous_command

    @frontier.command(name="claim", aliases=["reward"])
    @has_char()
    async def frontier_claim(self, ctx) -> None:
        """Claim the completed weekly reward exactly once."""

        level = await self._profile_level(ctx.author.id, ctx=ctx)
        state = get_rotation_state(self.config)
        region = get_region(self.config, state.region_id)
        if not region_is_unlocked(level, region):
            return await ctx.send(
                f"🔒 **{region['name']}** requires Level {region['unlock_level']}."
            )
        forge_before = forge_after = None
        async with self.bot.pool.acquire() as conn:
            async with conn.transaction():
                row = await conn.fetchrow(
                    """
                    SELECT * FROM frontier_weekly_progress
                    WHERE user_id = $1 AND absolute_week = $2
                    FOR UPDATE;
                    """,
                    int(ctx.author.id),
                    int(state.absolute_week),
                )
                progress = WeeklyProgress.from_mapping(_row_dict(row))
                if not weekly_reward_is_available(progress):
                    message = (
                        "You already claimed this week's Frontier reward."
                        if progress.reward_claimed
                        else "Defeat this week's regional boss before claiming the reward."
                    )
                    return await ctx.send(message)
                profile_updated = await conn.fetchval(
                    """
                    UPDATE profile
                    SET money = money + $1,
                        crates_materials = COALESCE(crates_materials, 0) + $2
                    WHERE "user" = $3 RETURNING "user";
                    """,
                    WEEKLY_MONEY_REWARD,
                    WEEKLY_MATERIAL_CRATES,
                    int(ctx.author.id),
                )
                if profile_updated is None:
                    raise RuntimeError("Frontier claimant no longer has a profile")
                await self.bot.log_transaction(
                    ctx,
                    from_=1,
                    to=ctx.author.id,
                    subject="money",
                    data={"Amount": WEEKLY_MONEY_REWARD, "Source": "Frontier weekly"},
                    conn=conn,
                )
                await self.bot.log_transaction(
                    ctx,
                    from_=1,
                    to=ctx.author.id,
                    subject="crates",
                    data={"Rarity": "materials", "Amount": WEEKLY_MATERIAL_CRATES},
                    conn=conn,
                )
                forge = await conn.fetchrow(
                    """
                    WITH locked AS MATERIALIZED (
                        SELECT user_id, COALESCE(forge_condition, 100) AS old_condition
                        FROM splicing_quest
                        WHERE user_id = $2 AND crucible_built = TRUE
                        FOR UPDATE
                    )
                    UPDATE splicing_quest sq
                    SET forge_condition = LEAST(100, locked.old_condition + $1)
                    FROM locked
                    WHERE sq.user_id = locked.user_id
                    RETURNING locked.old_condition AS before_value,
                              sq.forge_condition AS after_value;
                    """,
                    WEEKLY_FORGE_REPAIR,
                    int(ctx.author.id),
                )
                if forge:
                    forge_before = int(forge["before_value"])
                    forge_after = int(forge["after_value"])
                updated = await conn.fetchval(
                    """
                    UPDATE frontier_weekly_progress
                    SET reward_claimed = TRUE, reward_claimed_at = NOW(), updated_at = NOW()
                    WHERE user_id = $1 AND absolute_week = $2
                      AND reward_claimed = FALSE
                    RETURNING 1;
                    """,
                    int(ctx.author.id),
                    int(state.absolute_week),
                )
                if not updated:
                    raise RuntimeError("Frontier reward claim lost its row lock")
        forge_line = (
            f"\n🔧 Soulforge condition: **{forge_before}% → {forge_after}%**"
            if forge_after is not None
            else "\n🔧 No constructed Soulforge was available to repair."
        )
        await ctx.send(
            f"✅ **Weekly Frontier reward claimed**\n"
            f"**${WEEKLY_MONEY_REWARD:,}**\n"
            f"{MATERIALS_CRATE_EMOJI} **{WEEKLY_MATERIAL_CRATES}** Materials Crate"
            f"{forge_line}"
        )

    async def _milestone_metrics(self, user_id: int) -> dict[str, int]:
        async with self.bot.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT
                    COUNT(*) FILTER (
                        WHERE s.origin = 'splice' AND d.first_sighted_at IS NOT NULL
                    )::INTEGER AS splice_sightings,
                    COALESCE(SUM(d.creations) FILTER (WHERE s.origin = 'splice'), 0)::INTEGER
                        AS splice_creations,
                    COALESCE((
                        SELECT MAX(COALESCE(r.generation, created.generation, 0))
                        FROM frontier_discovery_ledger ledger
                        JOIN frontier_species created
                            ON created.species_id = ledger.species_id
                        LEFT JOIN frontier_recipes r
                            ON r.recipe_id = ledger.recipe_id
                        WHERE ledger.user_id = $1
                          AND ledger.event_type = 'created'
                          AND created.origin = 'splice'
                    ), 0)::INTEGER AS max_generation
                FROM frontier_discoveries d
                JOIN frontier_species s ON s.species_id = d.species_id
                WHERE d.user_id = $1;
                """,
                int(user_id),
            )
            completed = await conn.fetchval(
                """
                SELECT COUNT(*) FROM frontier_lineage_tracks
                WHERE user_id = $1 AND status = 'completed';
                """,
                int(user_id),
            )
            bosses = await conn.fetchval(
                """
                SELECT COALESCE(SUM(boss_defeats), 0)
                FROM frontier_weekly_progress WHERE user_id = $1;
                """,
                int(user_id),
            )
        metrics = {key: int(value or 0) for key, value in _row_dict(row).items()}
        metrics["completed_lineages"] = int(completed or 0)
        metrics["frontier_bosses"] = int(bosses or 0)
        return metrics

    @frontier.command(name="milestones", aliases=["achievements"])
    @has_char()
    async def frontier_milestones(self, ctx) -> None:
        """Show permanent Frontier and lineage milestones."""

        await self._sync_legacy_discoveries(ctx.author.id)
        metrics = await self._milestone_metrics(ctx.author.id)
        earned = earned_milestones(metrics)
        groups = (
            (
                "👁️ Explorer",
                ("splice_scout_10", "splice_scout_25", "splice_scout_50"),
            ),
            (
                "🧬 Creator",
                ("splice_creator_5", "splice_creator_15", "splice_creator_30"),
            ),
            (
                "🔬 Lineage Research",
                ("lineage_gen_1", "lineage_gen_3", "lineage_gen_5", "lineage_gen_10"),
            ),
            ("🌳 Lineage Legacy", ("lineage_completed",)),
            (
                "⚔️ Frontier Conqueror",
                ("frontier_boss_1", "frontier_boss_4", "frontier_boss_20"),
            ),
        )
        total = len(MILESTONE_LABELS)
        embed = discord.Embed(
            title="🏅 Frontier Milestones",
            description=(
                "Permanent achievements across exploration, creation, lineage research, "
                "and regional conquests.\n\n"
                f"`{progress_bar(len(earned), total, width=14)}` "
                f"**{len(earned)}/{total} earned**"
            ),
            color=self._region_colour(
                get_region(self.config, get_rotation_state(self.config).region_id)
            ),
        )
        for title, keys in groups:
            embed.add_field(
                name=title,
                value="\n".join(
                    f"{'✅' if key in earned else '▫️'} {MILESTONE_LABELS[key]}"
                    for key in keys
                ),
                inline=False,
            )
        embed.set_footer(
            text=(
                f"Sighted {metrics['splice_sightings']} · Created {metrics['splice_creations']} · "
                f"Highest Gen {metrics['max_generation']} · "
                f"Lineages {metrics['completed_lineages']} · Bosses {metrics['frontier_bosses']}"
            )
        )
        active_region = get_region(
            self.config, get_rotation_state(self.config).region_id
        )
        self._decorate_region_embed(embed, active_region)
        await ctx.send(embed=embed)


async def setup(bot) -> None:
    await bot.add_cog(SoulforgeFrontiers(bot))


__all__ = (
    "SoulforgeFrontiers",
    "clamp_page",
    "event_key_for_battle",
    "region_is_unlocked",
    "role_counter_column",
)

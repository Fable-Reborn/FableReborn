"""
Class Specializations — master a class line and choose one of its paths.

This cog ships the progression layer (choose / reset / display / effects API).
Effects resolve in battle via cogs/battles/extensions/specs.py — live in the
Battle Tower; ice dragon and raids are next.
Design doc: docs/class_specializations.md
"""
import asyncio
import logging
from pathlib import Path

import discord
from discord.ext import commands

from classes.class_mastery import (
    GAUNTLET_ICE_DRAGON_MASTERY_DAILY_CAP,
    IRONMAN_MASTERY_FLOORS,
    MASTERY_AWARDS,
    MASTERY_UNLOCK_POINTS,
    award_class_mastery,
    ensure_mastery_tables,
    get_class_mastery,
    rift_mastery_points,
    specialization_is_unlocked,
)
from classes.classes import from_string as class_from_string
from classes.specs import (
    RESPEC_COST,
    SPEC_UNLOCK_LEVEL,
    SPECS,
    describe_spec,
    spec_value,
    specs_for_line,
)
from utils import misc as rpgtools
from utils.checks import has_char
from utils.image_choice import ImageChoice, ImageChoiceView, embed_with_image, find_image_path


SPEC_IMAGE_DIR = Path(__file__).resolve().parents[2] / "assets" / "classes" / "ClassesNew"
logger = logging.getLogger(__name__)

TOWER_MILESTONE_FLOORS = frozenset(
    {1, 4, 5, 7, 9, 10, 11, 13, 15, 17, 19, 20, 21, 25, 30}
)


def _spec_image_path(spec_key: str) -> Path | None:
    spec = SPECS.get(spec_key)
    if not spec:
        return None
    return find_image_path(SPEC_IMAGE_DIR, spec["name"])


SPEC_CATALOG_GRADE = 7
SPEC_CLASS_LINES = tuple(dict.fromkeys(spec["line"] for spec in SPECS.values()))


class SpecCatalogClassSelect(discord.ui.Select):
    def __init__(self, catalog: "SpecCatalogView"):
        self.catalog = catalog
        options = []
        for line in SPEC_CLASS_LINES:
            spec_names = " · ".join(
                spec["name"] for spec in specs_for_line(line).values()
            )
            options.append(
                discord.SelectOption(
                    label=line,
                    value=line,
                    description=spec_names[:100],
                    default=line == catalog.class_line,
                )
            )
        super().__init__(
            placeholder="Choose a class",
            min_values=1,
            max_values=1,
            options=options,
            row=0,
        )

    async def callback(self, interaction: discord.Interaction):
        await self.catalog.show_page(
            interaction,
            class_line=self.values[0],
            spec_index=0,
        )


class SpecCatalogView(discord.ui.View):
    def __init__(self, ctx, cog: "Specializations", *, timeout=180):
        super().__init__(timeout=timeout)
        self.ctx = ctx
        self.cog = cog
        self.class_line = SPEC_CLASS_LINES[0]
        self.spec_index = 0
        self.message = None
        self.allowed_user_ids = {int(ctx.author.id)}
        alt_invoker_id = getattr(ctx, "alt_invoker_id", None)
        if alt_invoker_id is not None:
            self.allowed_user_ids.add(int(alt_invoker_id))
        self.class_select = SpecCatalogClassSelect(self)
        self.add_item(self.class_select)
        self._sync_components()

    def _spec_keys(self):
        return list(specs_for_line(self.class_line))

    def _sync_components(self):
        spec_keys = self._spec_keys()
        self.spec_index = min(max(0, self.spec_index), len(spec_keys) - 1)
        self.previous.disabled = self.spec_index == 0
        self.next.disabled = self.spec_index >= len(spec_keys) - 1
        self.page_number.label = f"{self.spec_index + 1} / {len(spec_keys)}"
        self.class_select.placeholder = f"Class: {self.class_line}"
        for option in self.class_select.options:
            option.default = option.value == self.class_line

    def _current_payload(self):
        self._sync_components()
        spec_keys = self._spec_keys()
        key = spec_keys[self.spec_index]
        spec = SPECS[key]
        embed = self.cog._build_spec_choice_embed(
            key,
            SPEC_UNLOCK_LEVEL,
            SPEC_CATALOG_GRADE,
            None,
            MASTERY_UNLOCK_POINTS,
            catalog=True,
        )
        footer = embed.footer.text
        page = f"{self.class_line} · Spec {self.spec_index + 1}/{len(spec_keys)}"
        embed.set_footer(text=f"{footer} · {page}" if footer else page)
        return embed_with_image(embed, _spec_image_path(key), label=spec["name"])

    async def start(self):
        embed, files = self._current_payload()
        kwargs = {"embed": embed, "view": self}
        if files:
            kwargs["file"] = files[0]
        self.message = await self.ctx.send(**kwargs)
        return self.message

    async def interaction_check(self, interaction: discord.Interaction):
        if int(interaction.user.id) in self.allowed_user_ids:
            return True
        await interaction.response.send_message(
            "This specialization catalog was opened by another player.",
            ephemeral=True,
        )
        return False

    async def show_page(
        self,
        interaction: discord.Interaction,
        *,
        class_line=None,
        spec_index=None,
    ):
        if class_line in SPEC_CLASS_LINES:
            self.class_line = class_line
        if spec_index is not None:
            self.spec_index = int(spec_index)
        embed, files = self._current_payload()
        await interaction.response.edit_message(
            embed=embed,
            attachments=files,
            view=self,
        )

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        if self.message is not None:
            try:
                await self.message.edit(view=self)
            except (discord.HTTPException, discord.NotFound, discord.Forbidden):
                pass

    @discord.ui.button(
        label="Previous",
        emoji="◀",
        style=discord.ButtonStyle.secondary,
        row=1,
    )
    async def previous(self, interaction: discord.Interaction, _button):
        await self.show_page(interaction, spec_index=self.spec_index - 1)

    @discord.ui.button(
        label="1 / 2",
        style=discord.ButtonStyle.secondary,
        disabled=True,
        row=1,
    )
    async def page_number(self, interaction: discord.Interaction, _button):
        return None

    @discord.ui.button(
        label="Next",
        emoji="▶",
        style=discord.ButtonStyle.primary,
        row=1,
    )
    async def next(self, interaction: discord.Interaction, _button):
        await self.show_page(interaction, spec_index=self.spec_index + 1)


class Specializations(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self._tables_ready = False
        self._table_lock = asyncio.Lock()
        self._pending_confirms = set()

    async def _confirm_exclusive(self, ctx, prompt):
        """One pending confirm dialog per user — blocks dialog-stacking spam.

        Returns True/False like ctx.confirm, or None if a dialog is already open
        (in which case the caller should simply return; the user was told).
        """
        if ctx.author.id in self._pending_confirms:
            await ctx.send(
                "You already have a pending specialization confirmation — answer that one first."
            )
            return None
        self._pending_confirms.add(ctx.author.id)
        try:
            return await ctx.confirm(prompt)
        finally:
            self._pending_confirms.discard(ctx.author.id)

    async def ensure_tables(self):
        if self._tables_ready:
            return
        async with self._table_lock:
            if self._tables_ready:
                return
            async with self.bot.pool.acquire() as conn:
                await conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS class_specs (
                        user_id BIGINT NOT NULL,
                        class_line TEXT NOT NULL,
                        spec_key TEXT NOT NULL,
                        chosen_at TIMESTAMP NOT NULL DEFAULT NOW(),
                        PRIMARY KEY (user_id, class_line)
                    );
                    """
                )
            await ensure_mastery_tables(self.bot)
            self._tables_ready = True

    async def cog_load(self):
        await self.ensure_tables()

    # --- Shared helpers ------------------------------------------------------

    async def get_player_lines(self, user_id, conn=None):
        """The player's class lines as {line_name: grade}, from profile.class."""
        query = 'SELECT class, xp FROM profile WHERE "user" = $1;'
        if conn is not None:
            row = await conn.fetchrow(query, user_id)
        else:
            async with self.bot.pool.acquire() as conn2:
                row = await conn2.fetchrow(query, user_id)
        if not row:
            return {}, 0
        level = rpgtools.xptolevel(row["xp"])
        lines = {}
        raw = row["class"] if isinstance(row["class"], list) else [row["class"]]
        for class_name in raw or []:
            if not class_name:
                continue
            game_class = class_from_string(class_name)
            if game_class is None:
                continue
            line = game_class.get_class_line_name()
            grade = game_class.class_grade()
            if grade > lines.get(line, 0):
                lines[line] = grade
        return lines, level

    async def get_user_spec_effects(self, user_id, conn=None):
        """Flat effects dict for the battle engines (future wiring).

        Returns {effect_type: {"value": scaled_value, "spec": spec_key, **extras}}.
        """
        await self.ensure_tables()
        lines, _level = await self.get_player_lines(user_id, conn=conn)
        if not lines:
            return {}
        query = "SELECT class_line, spec_key FROM class_specs WHERE user_id = $1"
        if conn is not None:
            rows = await conn.fetch(query, user_id)
        else:
            async with self.bot.pool.acquire() as conn2:
                rows = await conn2.fetch(query, user_id)

        effects = {}
        for row in rows:
            spec = SPECS.get(row["spec_key"])
            if not spec or spec["line"] not in lines:
                continue  # stale pick after a class change; ignore
            grade = lines[spec["line"]]
            entry = {k: v for k, v in spec["effect"].items() if k not in ("base", "per_grade")}
            value = spec_value(spec, grade)
            entry["value"] = value
            entry["grade"] = grade
            if "execute_bonus" in spec["effect"]:
                entry["execute_value"] = round(value + spec["effect"]["execute_bonus"], 1)
            if "shield_bonus" in spec["effect"]:
                entry["shield_value"] = round(value + spec["effect"]["shield_bonus"], 1)
            if "hp_base" in spec["effect"] and "hp_per_grade" in spec["effect"]:
                entry["hp_value"] = round(
                    spec["effect"]["hp_base"] + spec["effect"]["hp_per_grade"] * grade,
                    1,
                )
            if "ward_base" in spec["effect"] and "ward_per_grade" in spec["effect"]:
                entry["ward_value"] = round(
                    spec["effect"]["ward_base"] + spec["effect"]["ward_per_grade"] * grade,
                    1,
                )
            if "reduction_base" in spec["effect"] and "reduction_per_grade" in spec["effect"]:
                entry["reduction_value"] = round(
                    spec["effect"]["reduction_base"] + spec["effect"]["reduction_per_grade"] * grade,
                    1,
                )
            if "shield_base" in spec["effect"] and "shield_per_grade" in spec["effect"]:
                entry["miracle_shield_value"] = round(
                    spec["effect"]["shield_base"] + spec["effect"]["shield_per_grade"] * grade,
                    1,
                )
            if "finisher_base" in spec["effect"] and "finisher_per_grade" in spec["effect"]:
                entry["finisher_value"] = round(
                    spec["effect"]["finisher_base"]
                    + spec["effect"]["finisher_per_grade"] * grade,
                    1,
                )
            if "momentum_base" in spec["effect"] and "momentum_per_grade" in spec["effect"]:
                entry["momentum_value"] = round(
                    spec["effect"]["momentum_base"]
                    + spec["effect"]["momentum_per_grade"] * grade,
                    1,
                )
            entry["spec"] = row["spec_key"]
            effects[spec["effect"]["type"]] = entry
        return effects

    async def get_spec_display_classes(self, user_id, class_list, conn=None):
        """Class names for profile display: a declared spec replaces the class
        name on lines at final evolution. Falls back to raw names on any error.
        """
        names = [str(c) for c in (class_list or []) if c]
        try:
            await self.ensure_tables()
            query = "SELECT class_line, spec_key FROM class_specs WHERE user_id = $1"
            if conn is not None:
                rows = await conn.fetch(query, user_id)
            else:
                async with self.bot.pool.acquire() as conn2:
                    rows = await conn2.fetch(query, user_id)
            specs_by_line = {r["class_line"]: r["spec_key"] for r in rows}
            if not specs_by_line:
                return names
            display = []
            for name in names:
                game_class = class_from_string(name)
                spec_key = (
                    specs_by_line.get(game_class.get_class_line_name())
                    if game_class
                    else None
                )
                if spec_key and spec_key in SPECS and game_class.class_grade() >= 7:
                    display.append(SPECS[spec_key]["name"])
                else:
                    display.append(name)
            return display
        except Exception:
            return names

    # --- Commands --------------------------------------------------------------

    @staticmethod
    def _bar(current, total, width=12):
        if total <= 0:
            return "▱" * width
        filled = int(width * min(current, total) / total)
        return "▰" * filled + "▱" * (width - filled)

    @staticmethod
    def _resolve_spec_key(spec_name: str) -> str | None:
        key = spec_name.strip().lower()
        if key in SPECS:
            return key
        normalized = key.replace(" ", "")
        matches = [
            spec_key
            for spec_key, spec in SPECS.items()
            if spec_key == normalized or spec["name"].lower() == key
        ]
        return matches[0] if matches else None

    def _build_spec_choice_embed(
        self,
        key: str,
        level: int,
        grade: int,
        picked_key: str | None,
        mastery_points: int,
        *,
        catalog: bool = False,
    ):
        spec_data = SPECS[key]
        embed = discord.Embed(
            title=f"{spec_data['emoji']} {spec_data['name']}",
            description=describe_spec(key, grade),
            color=0x8E44AD,
        )
        embed.add_field(
            name="Class line",
            value=f"{spec_data['line']} · Grade {grade}",
            inline=True,
        )
        embed.add_field(
            name="Path type",
            value=spec_data.get("kind", "special").title(),
            inline=True,
        )
        embed.add_field(
            name="Class Mastery",
            value=(
                f"{MASTERY_UNLOCK_POINTS} required"
                if catalog
                else f"{mastery_points} / {MASTERY_UNLOCK_POINTS}"
            ),
            inline=True,
        )
        if catalog:
            status = (
                f"Catalog preview at Grade {grade}. Use `$spec choose` to declare "
                "a path after meeting its requirements."
            )
        elif picked_key == key:
            status = "Already chosen for this class line."
        elif picked_key:
            status = (
                f"This line is already **{SPECS[picked_key]['name']}**. "
                f"Use `$spec reset {spec_data['line']}` before changing."
            )
        elif not specialization_is_unlocked(
            level=level,
            grade=grade,
            points=mastery_points,
        ):
            requirements = []
            if level < SPEC_UNLOCK_LEVEL:
                requirements.append(f"level {SPEC_UNLOCK_LEVEL}")
            if grade < 7:
                requirements.append("final evolution")
            if mastery_points < MASTERY_UNLOCK_POINTS:
                requirements.append(
                    f"{MASTERY_UNLOCK_POINTS} {spec_data['line']} Mastery"
                )
            status = (
                "Available to preview. Declaration is locked until: "
                + ", ".join(requirements)
                + "."
            )
        else:
            status = "Available to declare."
        embed.add_field(name="Status", value=status, inline=False)
        embed.set_footer(
            text=(
                "All effects shown at final evolution"
                if catalog
                else "Browse freely · Select declares only after all requirements are met"
            )
        )
        return embed

    async def _prompt_spec_choice(self, ctx, lines, chosen, level, mastery_lines):
        spec_cards = []
        for line, grade in lines.items():
            points = int(mastery_lines.get(line, {}).get("points", 0))
            for key in specs_for_line(line):
                spec_data = SPECS[key]
                ready = specialization_is_unlocked(
                    level=level,
                    grade=grade,
                    points=points,
                )
                spec_cards.append(
                    ImageChoice(
                        label=f"{spec_data['name']} ({line})",
                        description=(
                            f"{line} · {'Ready' if ready else f'{points}/{MASTERY_UNLOCK_POINTS} mastery'}"
                        ),
                        embed=self._build_spec_choice_embed(
                            key,
                            level,
                            grade,
                            chosen.get(line),
                            points,
                        ),
                        image_path=_spec_image_path(key),
                        value=key,
                    )
                )

        if not spec_cards:
            return None

        return await ImageChoiceView(
            ctx,
            spec_cards,
            placeholder="Preview a specialization",
        ).prompt()

    async def _declare_spec(
        self,
        ctx,
        key: str,
        *,
        lines=None,
        level=None,
        mastery_lines=None,
    ):
        spec_data = SPECS[key]
        if lines is None or level is None:
            lines, level = await self.get_player_lines(ctx.author.id)
        if mastery_lines is None:
            mastery = await get_class_mastery(self.bot, ctx.author.id)
            mastery_lines = mastery["lines"]

        if level < SPEC_UNLOCK_LEVEL:
            return await ctx.send(
                f"Specializations unlock at level **{SPEC_UNLOCK_LEVEL}** — you are level **{level}**."
            )
        if spec_data["line"] not in lines:
            return await ctx.send(
                f"**{spec_data['name']}** is a {spec_data['line']} spec, and you don't "
                f"walk that path. Your line(s): {', '.join(lines) or 'none'}."
            )
        if lines[spec_data["line"]] < 7:
            return await ctx.send(
                f"A path can only be declared at your line's **final evolution**. "
                f"Your {spec_data['line']} is Grade **{lines[spec_data['line']]}/7** — "
                "evolve to the end, then return."
            )
        mastery_points = int(
            mastery_lines.get(spec_data["line"], {}).get("points", 0)
        )
        if mastery_points < MASTERY_UNLOCK_POINTS:
            return await ctx.send(
                f"You need **{MASTERY_UNLOCK_POINTS} {spec_data['line']} Mastery** to "
                f"declare this path. You currently have **{mastery_points} / "
                f"{MASTERY_UNLOCK_POINTS}**. View earning details with `$spec mastery`."
            )

        async with self.bot.pool.acquire() as conn:
            existing = await conn.fetchval(
                "SELECT spec_key FROM class_specs WHERE user_id = $1 AND class_line = $2",
                ctx.author.id,
                spec_data["line"],
            )
            if existing:
                if existing == key:
                    return await ctx.send(f"You are already a **{spec_data['name']}**.")
                return await ctx.send(
                    f"Your {spec_data['line']} line is already spec'd as "
                    f"**{SPECS[existing]['name']}**. Use `$spec reset {spec_data['line']}` "
                    f"first (${RESPEC_COST:,})."
                )
            await conn.execute(
                """
                INSERT INTO class_specs (user_id, class_line, spec_key)
                VALUES ($1, $2, $3)
                ON CONFLICT (user_id, class_line) DO NOTHING
                """,
                ctx.author.id,
                spec_data["line"],
                key,
            )

        grade = lines[spec_data["line"]]
        embed = discord.Embed(
            title="The path is chosen",
            description=(
                f"{ctx.author.mention} walks the way of the "
                f"**{spec_data['name']}**.\n\n{describe_spec(key, grade)}"
            ),
            color=0x8E44AD,
        )
        embed.set_footer(
            text=(
                f"{spec_data['line']} · Grade {grade} · "
                f"Mastery {mastery_points}/{MASTERY_UNLOCK_POINTS}"
            )
        )
        embed, files = embed_with_image(embed, _spec_image_path(key), label=spec_data["name"])
        kwargs = {"embed": embed}
        if files:
            kwargs["files"] = files
        await ctx.send(**kwargs)

    async def _send_spec_overview(self, ctx):
        """View your class specializations."""
        await self.ensure_tables()
        lines, level = await self.get_player_lines(ctx.author.id)
        if not lines:
            return await ctx.send("You don't have a class yet! Pick one with `$class` first.")
        mastery = await get_class_mastery(self.bot, ctx.author.id)
        mastery_lines = mastery["lines"]

        async with self.bot.pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT class_line, spec_key FROM class_specs WHERE user_id = $1",
                ctx.author.id,
            )
        chosen = {r["class_line"]: r["spec_key"] for r in rows}
        declared = sum(1 for line in lines if chosen.get(line))

        if level < SPEC_UNLOCK_LEVEL:
            description = (
                "*Every class line forks into two paths. Choose one; become it.*\n"
                f"{self._bar(level, SPEC_UNLOCK_LEVEL, 14)}  level **{level} / {SPEC_UNLOCK_LEVEL}**\n"
                f"The paths open at level {SPEC_UNLOCK_LEVEL}. Final evolution and "
                f"{MASTERY_UNLOCK_POINTS} Class Mastery are also required."
            )
        else:
            description = (
                "*Every class line forks into two paths. Choose one; become it.*\n"
                f"Paths declared: **{declared} / {len(lines)}**  ·  "
                f"`$spec choose` picker · direct `$spec choose <name>` · "
                f"respec `$spec reset <line>` (${RESPEC_COST:,})\n"
                f"Declaring requires **Grade 7** and **{MASTERY_UNLOCK_POINTS} "
                "Class Mastery** in that line."
            )

        embed = discord.Embed(
            title="Specializations",
            description=description,
            color=0x8E44AD if declared else 0x6C7A89,
        )

        for line, grade in lines.items():
            options = specs_for_line(line)
            if not options:
                continue
            picked = chosen.get(line)
            mastery_row = mastery_lines.get(line, {})
            points = int(mastery_row.get("points", 0))
            daily_points = int(mastery_row.get("daily_points", 0))
            value_lines = [
                f"**Mastery:** {self._bar(points, MASTERY_UNLOCK_POINTS, 14)}  "
                f"**{points} / {MASTERY_UNLOCK_POINTS}**",
                f"**Today:** {daily_points} / "
                f"{GAUNTLET_ICE_DRAGON_MASTERY_DAILY_CAP} "
                "Gauntlet + Ice Dragon points",
            ]
            for key in options:
                marker = "✓" if picked == key else "·"
                card = describe_spec(key, grade)
                if picked == key:
                    header, _, body = card.partition("\n")
                    card = f"{header} — **your path**\n{body}"
                value_lines.append(f"{marker} {card}")
            field_name = f"{line} · Grade {grade} · Mastery {points}/{MASTERY_UNLOCK_POINTS}"
            if picked:
                field_name += f"  —  {SPECS[picked]['name']}"
            elif level < SPEC_UNLOCK_LEVEL:
                field_name += f"  —  locked until level {SPEC_UNLOCK_LEVEL}"
            elif grade < 7:
                field_name += "  —  locked until final evolution"
            elif points < MASTERY_UNLOCK_POINTS:
                field_name += "  —  mastery in progress"
            else:
                field_name += "  —  undeclared"
            embed.add_field(
                name=field_name,
                value="\n".join(value_lines)[:1024],
                inline=False,
            )

        embed.set_footer(
            text=(
                "Mastery is permanent per class line · restricted-source cap resets "
                "in Australia/Sydney"
            )
        )
        await ctx.send(embed=embed)

    async def _send_mastery_status(self, ctx):
        await self.ensure_tables()
        mastery = await get_class_mastery(self.bot, ctx.author.id)
        if not mastery["lines"]:
            return await ctx.send("You don't have a class yet! Pick one with `$class` first.")

        level = int(mastery["level"])
        embed = discord.Embed(
            title="Class Mastery",
            description=(
                f"Specializations require **level {SPEC_UNLOCK_LEVEL}**, **Grade 7**, "
                f"and **{MASTERY_UNLOCK_POINTS} mastery points** in that class line.\n"
                "Points are permanent and both equipped Grade 7 lines earn them."
            ),
            color=0x8E44AD,
        )
        for line, row in mastery["lines"].items():
            points = int(row["points"])
            grade = int(row["grade"])
            equipped = bool(row.get("equipped", True))
            if equipped:
                unlock_bits = [
                    f"Level {SPEC_UNLOCK_LEVEL} {'✓' if level >= SPEC_UNLOCK_LEVEL else '✗'}",
                    f"Grade 7 {'✓' if grade >= 7 else '✗'}",
                    f"Mastery {'✓' if points >= MASTERY_UNLOCK_POINTS else '✗'}",
                ]
                field_name = f"{line} · Grade {grade}"
            else:
                unlock_bits = ["Stored permanently", "equip this line to use its path"]
                field_name = f"{line} · Not currently equipped"
            embed.add_field(
                name=field_name,
                value=(
                    f"{self._bar(points, MASTERY_UNLOCK_POINTS, 14)}  "
                    f"**{points} / {MASTERY_UNLOCK_POINTS}**\n"
                    f"Today: **{int(row['daily_points'])} / "
                    f"{GAUNTLET_ICE_DRAGON_MASTERY_DAILY_CAP}** "
                    "Gauntlet + Ice Dragon points\n"
                    + " · ".join(unlock_bits)
                ),
                inline=False,
            )

        embed.add_field(
            name="Where mastery comes from",
            value=(
                "**+1** Adventure, standard PvE win, or ordinary Tower/Jury floor\n"
                "**+2** Tower/Jury boss or checkpoint, successful Gauntlet attack\n"
                "**+3** Ice Dragon victory\n"
                "**+5** Qualified raid victory or completed Boss Rush\n"
                "**Ironman:** +1 at floors 5/10/15/20/25\n"
                "**Rift:** +1 per room, plus +3 for a full clear"
            ),
            inline=False,
        )
        embed.set_footer(
            text=(
                "Gauntlet + Ice Dragon share a "
                f"{GAUNTLET_ICE_DRAGON_MASTERY_DAILY_CAP}-point Sydney-day cap "
                "· all other mastery sources are uncapped"
            )
        )
        await ctx.send(embed=embed)

    async def _award_mastery_users(
        self,
        user_ids,
        points,
        *,
        source,
    ):
        for user_id in dict.fromkeys(int(value) for value in user_ids):
            try:
                await award_class_mastery(
                    self.bot,
                    user_id,
                    points,
                    source=source,
                )
            except Exception:
                logger.exception(
                    "Class mastery award failed for source %s, user %s",
                    source,
                    user_id,
                )

    # Completion listeners keep every award at the existing, confirmed reward
    # boundary. A mode dispatches only its own event, so one victory receives the
    # single highest matching amount rather than generic + mode-specific awards.
    @commands.Cog.listener()
    async def on_adventure_completion(self, ctx, iscompleted):
        if iscompleted:
            await self._award_mastery_users(
                [ctx.author.id], MASTERY_AWARDS["adventure"], source="adventure"
            )

    @commands.Cog.listener()
    async def on_PVE_completion(self, ctx, success):
        if success:
            await self._award_mastery_users(
                [ctx.author.id], MASTERY_AWARDS["pve"], source="pve"
            )

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
        if not success:
            return
        floor = int(level or 0)
        is_checkpoint = floor in TOWER_MILESTONE_FLOORS
        get_cog = getattr(self.bot, "get_cog", None)
        battles = get_cog("Battles") if callable(get_cog) else None
        victory_data = (
            getattr(battles, "battle_data", {}).get("victories", {}).get(str(floor), {})
            if battles
            else {}
        )
        if victory_data:
            is_checkpoint = bool(
                victory_data.get("has_chest") or victory_data.get("finale")
            )
        points = MASTERY_AWARDS[
            "battle_tower_boss"
            if is_checkpoint
            else "battle_tower_floor"
        ]
        await self._award_mastery_users(
            [ctx.author.id], points, source="battle_tower"
        )

    @commands.Cog.listener()
    async def on_jurytower_completion(self, ctx, success, floor, boss_floor=False):
        if success:
            await self._award_mastery_users(
                [ctx.author.id],
                MASTERY_AWARDS[
                    "jury_tower_boss" if boss_floor else "jury_tower_floor"
                ],
                source="jury_tower",
            )

    @commands.Cog.listener()
    async def on_gauntlet_completion(
        self, ctx, attacker_id, defender_id, attacker_won
    ):
        if attacker_won:
            await self._award_mastery_users(
                [attacker_id], MASTERY_AWARDS["gauntlet"], source="gauntlet"
            )

    @commands.Cog.listener()
    async def on_icedragon_victory(
        self, ctx, party_members, stage_name, dragon_level
    ):
        await self._award_mastery_users(
            [member.id for member in party_members],
            MASTERY_AWARDS["ice_dragon"],
            source="ice_dragon",
        )

    @commands.Cog.listener()
    async def on_raid_favor(self, ctx, participant_ids, success):
        if success:
            await self._award_mastery_users(
                participant_ids,
                MASTERY_AWARDS["scheduled_raid"],
                source="scheduled_raid",
            )

    @commands.Cog.listener()
    async def on_rift_completion(
        self,
        ctx,
        rooms_cleared,
        score,
        full_clear,
        difficulty="normal",
    ):
        points = rift_mastery_points(rooms_cleared, full_clear)
        if points:
            await self._award_mastery_users(
                [ctx.author.id],
                points,
                source="rift",
            )

    @commands.Cog.listener()
    async def on_bossrush_completion(self, ctx, success):
        if success:
            await self._award_mastery_users(
                [ctx.author.id], MASTERY_AWARDS["boss_rush"], source="boss_rush"
            )

    @commands.Cog.listener()
    async def on_ironman_completion(self, ctx, floor, success, completed):
        if success and int(floor or 0) in IRONMAN_MASTERY_FLOORS:
            await self._award_mastery_users(
                [ctx.author.id],
                MASTERY_AWARDS["ironman_milestone"],
                source="ironman",
            )

    @commands.group(invoke_without_command=True, aliases=["specialization", "specs"])
    @has_char()
    async def spec(self, ctx):
        """Browse or choose a specialization for one of your class lines."""
        await self._run_spec_choose(ctx)

    @spec.command(name="list", aliases=["overview", "info"])
    @has_char()
    async def spec_list(self, ctx):
        """View your class specializations."""
        await self._send_spec_overview(ctx)

    @spec.command(name="mastery", aliases=["points", "classpoints"])
    @has_char()
    async def spec_mastery(self, ctx):
        """View class mastery progress and all earning sources."""
        await self._send_mastery_status(ctx)

    @spec.command(name="all", aliases=["catalog", "browse"])
    async def spec_all(self, ctx):
        """Browse every class specialization."""
        await SpecCatalogView(ctx, self).start()

    async def _run_spec_choose(self, ctx, *, spec_name: str = None):
        """Browse specializations and declare an unlocked path."""
        await self.ensure_tables()
        lines, level = await self.get_player_lines(ctx.author.id)
        if not lines:
            return await ctx.send("You don't have a class yet! Pick one with `$class` first.")

        mastery = await get_class_mastery(self.bot, ctx.author.id)
        mastery_lines = mastery["lines"]

        async with self.bot.pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT class_line, spec_key FROM class_specs WHERE user_id = $1",
                ctx.author.id,
            )
        chosen = {r["class_line"]: r["spec_key"] for r in rows}

        if spec_name is None:
            if not any(specs_for_line(line) for line in lines):
                return await ctx.send(
                    "None of your current class lines have specialization paths."
                )
            key = await self._prompt_spec_choice(
                ctx,
                lines,
                chosen,
                level,
                mastery_lines,
            )
            if key is None:
                return await ctx.send("Specialization selection cancelled.")
        else:
            key = self._resolve_spec_key(spec_name)
            if key is None:
                return await ctx.send(
                    "Unknown spec. Check `$spec` for the options available to your class."
                )

        await self._declare_spec(
            ctx,
            key,
            lines=lines,
            level=level,
            mastery_lines=mastery_lines,
        )

    @spec.command(name="choose", aliases=["pick"])
    @has_char()
    async def spec_choose(self, ctx, *, spec_name: str = None):
        """Choose a specialization for one of your class lines."""
        await self._run_spec_choose(ctx, spec_name=spec_name)

    @spec.command(name="reset")
    @has_char()
    async def spec_reset(self, ctx, *, class_line: str):
        """Reset the spec of a class line for a fee."""
        await self.ensure_tables()
        line = class_line.strip()
        # Case-insensitive match against the player's lines
        lines, _level = await self.get_player_lines(ctx.author.id)
        match = next((l for l in lines if l.lower() == line.lower()), None)
        if not match:
            return await ctx.send(
                f"You have no **{line}** class line. Your line(s): {', '.join(lines) or 'none'}."
            )

        async with self.bot.pool.acquire() as conn:
            existing = await conn.fetchval(
                "SELECT spec_key FROM class_specs WHERE user_id = $1 AND class_line = $2",
                ctx.author.id,
                match,
            )
            if not existing:
                return await ctx.send(f"Your {match} line has no spec to reset.")

        confirmed = await self._confirm_exclusive(
            ctx,
            f"Reset your {match} spec (**{SPECS[existing]['name']}**) for "
            f"**${RESPEC_COST:,}**? Your old identity will be lost.",
        )
        if confirmed is None:
            return
        if not confirmed:
            return await ctx.send("Respec cancelled.")

        async with self.bot.pool.acquire() as conn:
            async with conn.transaction():
                money = await conn.fetchval(
                    'SELECT money FROM profile WHERE "user" = $1 FOR UPDATE', ctx.author.id
                )
                if (money or 0) < RESPEC_COST:
                    return await ctx.send(
                        f"You need **${RESPEC_COST:,}** to respec, but you only have "
                        f"**${money or 0:,}**."
                    )
                # Delete first: if the spec vanished (e.g. a stacked/duplicate
                # confirm already reset it), nobody gets charged for nothing.
                deleted = await conn.fetchval(
                    """
                    DELETE FROM class_specs
                    WHERE user_id = $1 AND class_line = $2
                    RETURNING spec_key
                    """,
                    ctx.author.id,
                    match,
                )
                if not deleted:
                    return await ctx.send(
                        f"Your {match} line has no spec to reset — nothing was charged."
                    )
                await conn.execute(
                    'UPDATE profile SET money = money - $1 WHERE "user" = $2',
                    RESPEC_COST,
                    ctx.author.id,
                )

        await ctx.send(
            f"Your {match} path has been dissolved for **${RESPEC_COST:,}**. "
            "Choose anew with `$spec choose`."
        )


async def setup(bot):
    await bot.add_cog(Specializations(bot))

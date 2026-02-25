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
import asyncio

import discord

from discord.enums import ButtonStyle
from discord.ext import commands
from discord.ui.button import Button

from classes.badges import Badge
from classes.converters import IntGreaterThan
from utils import random
from utils.i18n import _, locale_doc
from utils.joins import JoinView
from .core import DESCRIPTIONS as ROLE_DESC
from .core import ADVANCED_BASE_ROLE_BY_ADVANCED
from .core import ADVANCED_ROLE_TIERS_BY_BASE
from .core import Game
from .core import Role as ROLES
from .core import Side as WW_SIDE
from .core import parse_custom_roles
from .core import role_level_from_xp
from .core import send_traceback
from .core import unavailable_roles_for_mode
from .tutorial_live import TutorialGame
from .tutorial_live import TUTORIAL_VARIANT_SOLO_JESTER
from .tutorial_live import TUTORIAL_VARIANT_VILLAGE_SEER
from .tutorial_live import TUTORIAL_VARIANT_WEREWOLF_GUIDED
from .role_config import (
    ROLE_XP_CHANNEL_IDS,
    ROLE_XP_LONER_WIN,
    ROLE_XP_LOSS,
    ROLE_XP_PER_LEVEL,
    ROLE_XP_REQUIRE_GM_START,
    ROLE_XP_WIN,
    ROLE_XP_WIN_ALIVE,
)

class NewWerewolf(commands.Cog):
    TUTORIAL_TRACK_COLUMNS: dict[str, str] = {
        "village": "village_completed",
        "werewolf": "werewolf_completed",
        "solo": "solo_completed",
    }
    TUTORIAL_TRACK_LABELS: dict[str, str] = {
        "village": "Village",
        "werewolf": "Werewolf",
        "solo": "Solo",
    }

    def __init__(self, bot):
        self.bot = bot
        self.games = {}
        self.tutorial_sessions: dict[int, int] = {}
        self.tutorial_progress: dict[int, dict[str, int]] = {}
        self._role_xp_tables_ready = False
        self._role_xp_table_lock = asyncio.Lock()
        self.bot.loop.create_task(self._warm_role_xp_tables())

    async def _warm_role_xp_tables(self) -> None:
        try:
            await self._ensure_role_xp_tables()
        except Exception:
            # Do not fail cog load on startup DB race; tables are retried on game start.
            pass

    async def _ensure_role_xp_tables(self) -> None:
        if self._role_xp_tables_ready:
            return
        async with self._role_xp_table_lock:
            if self._role_xp_tables_ready:
                return
            async with self.bot.pool.acquire() as conn:
                await conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS newwerewolf_role_xp (
                        user_id bigint NOT NULL,
                        role_name text NOT NULL,
                        xp integer NOT NULL DEFAULT 0 CHECK (xp >= 0),
                        updated_at timestamp with time zone NOT NULL DEFAULT now(),
                        CONSTRAINT newwerewolf_role_xp_pk PRIMARY KEY (user_id, role_name)
                    );
                    """
                )
                await conn.execute(
                    """
                    CREATE INDEX IF NOT EXISTS newwerewolf_role_xp_user_idx
                    ON newwerewolf_role_xp (user_id);
                    """
                )
                await conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS newwerewolf_tutorial_completion (
                        user_id bigint PRIMARY KEY,
                        village_completed boolean NOT NULL DEFAULT FALSE,
                        werewolf_completed boolean NOT NULL DEFAULT FALSE,
                        solo_completed boolean NOT NULL DEFAULT FALSE,
                        completed_all_at timestamp with time zone,
                        updated_at timestamp with time zone NOT NULL DEFAULT now()
                    );
                    """
                )
                await conn.execute(
                    """
                    CREATE INDEX IF NOT EXISTS newwerewolf_tutorial_completion_all_idx
                    ON newwerewolf_tutorial_completion (completed_all_at)
                    WHERE completed_all_at IS NOT NULL;
                    """
                )
            self._role_xp_tables_ready = True

    async def _fetch_tutorial_completion_row(self, user_id: int) -> dict[str, object]:
        empty_progress = {
            "village_completed": False,
            "werewolf_completed": False,
            "solo_completed": False,
            "completed_all": False,
            "completed_all_at": None,
        }
        if not hasattr(self.bot, "pool"):
            return empty_progress
        try:
            await self._ensure_role_xp_tables()
        except Exception:
            return empty_progress

        try:
            async with self.bot.pool.acquire() as conn:
                row = await conn.fetchrow(
                    """
                    SELECT village_completed, werewolf_completed, solo_completed, completed_all_at
                    FROM newwerewolf_tutorial_completion
                    WHERE user_id = $1
                    """,
                    user_id,
                )
        except Exception:
            return empty_progress

        if row is None:
            return empty_progress

        village_completed = bool(row["village_completed"])
        werewolf_completed = bool(row["werewolf_completed"])
        solo_completed = bool(row["solo_completed"])
        completed_all = village_completed and werewolf_completed and solo_completed
        return {
            "village_completed": village_completed,
            "werewolf_completed": werewolf_completed,
            "solo_completed": solo_completed,
            "completed_all": completed_all,
            "completed_all_at": row["completed_all_at"],
        }

    async def _mark_tutorial_track_completed(
        self, *, user_id: int, track: str
    ) -> tuple[dict[str, object], bool]:
        track_column = self.TUTORIAL_TRACK_COLUMNS.get(track)
        current = await self._fetch_tutorial_completion_row(user_id)
        if track_column is None:
            return current, False
        if not hasattr(self.bot, "pool"):
            return current, False
        try:
            await self._ensure_role_xp_tables()
        except Exception:
            return current, False

        newly_completed_all = False
        try:
            async with self.bot.pool.acquire() as conn:
                await conn.execute(
                    f"""
                    INSERT INTO newwerewolf_tutorial_completion (user_id, {track_column}, updated_at)
                    VALUES ($1, TRUE, now())
                    ON CONFLICT (user_id)
                    DO UPDATE SET
                        {track_column} = TRUE,
                        updated_at = now()
                    """,
                    user_id,
                )

                row = await conn.fetchrow(
                    """
                    SELECT village_completed, werewolf_completed, solo_completed, completed_all_at
                    FROM newwerewolf_tutorial_completion
                    WHERE user_id = $1
                    """,
                    user_id,
                )
                if row is not None:
                    completed_all = bool(
                        row["village_completed"]
                        and row["werewolf_completed"]
                        and row["solo_completed"]
                    )
                    if completed_all and row["completed_all_at"] is None:
                        newly_completed_all = True
                        await conn.execute(
                            """
                            UPDATE newwerewolf_tutorial_completion
                            SET completed_all_at = now(), updated_at = now()
                            WHERE user_id = $1
                            """,
                            user_id,
                        )
        except Exception:
            return current, False

        updated = await self._fetch_tutorial_completion_row(user_id)
        return updated, newly_completed_all

    async def _grant_junior_werewolf_badge(self, user_id: int) -> str:
        if not hasattr(self.bot, "pool"):
            return "db_unavailable"

        try:
            async with self.bot.pool.acquire() as conn:
                profile_row = await conn.fetchrow(
                    'SELECT "badges" FROM profile WHERE "user" = $1;',
                    user_id,
                )
                if profile_row is None:
                    return "no_profile"

                raw_badges = profile_row["badges"]
                try:
                    current_badges = (
                        Badge(0) if raw_badges is None else Badge.from_db(raw_badges)
                    )
                except Exception:
                    current_badges = Badge(0)

                if bool(current_badges & Badge.JUNIOR_WEREWOLF):
                    return "already"

                new_badges = current_badges | Badge.JUNIOR_WEREWOLF
                await conn.execute(
                    'UPDATE profile SET "badges" = $1 WHERE "user" = $2;',
                    new_badges.to_db(),
                    user_id,
                )
                return "granted"
        except Exception:
            return "error"

    async def _user_has_badge(self, user_id: int, badge: Badge) -> bool | None:
        if not hasattr(self.bot, "pool"):
            return None
        try:
            async with self.bot.pool.acquire() as conn:
                profile_row = await conn.fetchrow(
                    'SELECT "badges" FROM profile WHERE "user" = $1;',
                    user_id,
                )
        except Exception:
            return None

        if profile_row is None:
            return None
        raw_badges = profile_row["badges"]
        try:
            current_badges = Badge(0) if raw_badges is None else Badge.from_db(raw_badges)
        except Exception:
            current_badges = Badge(0)
        return bool(current_badges & badge)

    async def _update_tutorial_completion_and_badge(self, ctx, *, track: str) -> None:
        if track not in self.TUTORIAL_TRACK_COLUMNS:
            return

        progress, newly_completed_all = await self._mark_tutorial_track_completed(
            user_id=ctx.author.id,
            track=track,
        )
        completed_labels = [
            label
            for key, label in self.TUTORIAL_TRACK_LABELS.items()
            if bool(progress.get(self.TUTORIAL_TRACK_COLUMNS[key], False))
        ]
        done_count = len(completed_labels)
        if completed_labels:
            completion_text = ", ".join(completed_labels)
        else:
            completion_text = _("None")

        await ctx.send(
            _(
                "Tutorial progress saved: **{done}/3** completed"
                " (`{completion_text}`)."
            ).format(
                done=done_count,
                completion_text=completion_text,
            )
        )

        if not newly_completed_all:
            return

        badge_outcome = await self._grant_junior_werewolf_badge(ctx.author.id)
        if badge_outcome == "granted":
            await ctx.send(
                _(
                    "🏅 You completed all three tutorial tracks and earned the"
                    " **Junior Werewolf** profile badge. It now appears on `prpg`."
                )
            )
        elif badge_outcome == "already":
            await ctx.send(
                _(
                    "🏅 You completed all three tutorial tracks. Your **Junior"
                    " Werewolf** badge was already unlocked."
                )
            )
        elif badge_outcome == "no_profile":
            await ctx.send(
                _(
                    "You completed all three tutorial tracks, but no RPG profile was"
                    " found to attach the **Junior Werewolf** badge."
                )
            )

    async def _is_gm_user(self, user_id: int) -> bool:
        config_gms = set(getattr(self.bot.config.game, "game_masters", []) or [])
        if user_id in config_gms:
            return True
        try:
            async with self.bot.pool.acquire() as conn:
                row = await conn.fetchrow(
                    "SELECT 1 FROM game_masters WHERE user_id = $1",
                    user_id,
                )
        except Exception:
            return False
        return row is not None

    def _get_role_xp_channel_ids(self) -> set[int]:
        configured_channel_ids = {int(channel_id) for channel_id in ROLE_XP_CHANNEL_IDS}
        if configured_channel_ids:
            return configured_channel_ids
        official_channel = getattr(
            self.bot.config.game,
            "official_tournament_channel_id",
            None,
        )
        if official_channel is None:
            return set()
        return {int(official_channel)}

    async def _is_role_xp_eligible_match(self, ctx) -> bool:
        channel_ids = self._get_role_xp_channel_ids()
        if not channel_ids:
            return False
        if ctx.channel.id not in channel_ids:
            return False
        if ROLE_XP_REQUIRE_GM_START and not await self._is_gm_user(ctx.author.id):
            return False
        return True

    async def _award_role_xp(self, game: Game, *, eligible: bool) -> None:
        if not eligible:
            return
        if not hasattr(self.bot, "pool"):
            return

        updates: list[tuple[int, str, int]] = []
        xp_events: list[tuple] = []
        winner_ids: set[int] = {
            player.user.id for player in game.players if player.has_won
        }
        winner = game.winner
        if getattr(winner, "user", None) is not None:
            winner_ids.add(winner.user.id)
        forced_winner = getattr(game, "forced_winner", None)
        if forced_winner is not None and getattr(forced_winner, "user", None) is not None:
            winner_ids.add(forced_winner.user.id)

        loner_win_sides = {
            WW_SIDE.WHITE_WOLF,
            WW_SIDE.FLUTIST,
            WW_SIDE.SUPERSPREADER,
            WW_SIDE.JESTER,
            WW_SIDE.HEAD_HUNTER,
        }
        for player in game.players:
            if not player.initial_roles:
                role_for_xp = player.role
            else:
                role_for_xp = player.initial_roles[0]
            role_for_xp = ADVANCED_BASE_ROLE_BY_ADVANCED.get(role_for_xp, role_for_xp)
            has_won_match = player.user.id in winner_ids
            if has_won_match:
                if player.side in loner_win_sides:
                    gained_xp = ROLE_XP_LONER_WIN
                elif not player.dead:
                    gained_xp = ROLE_XP_WIN_ALIVE
                else:
                    gained_xp = ROLE_XP_WIN
            else:
                gained_xp = ROLE_XP_LOSS
            role_key = role_for_xp.name.casefold()
            updates.append((player.user.id, role_key, gained_xp))
            xp_events.append((player, role_for_xp, role_key, gained_xp))

        if not updates:
            return

        user_ids = list(dict.fromkeys(player.user.id for player, *_ in xp_events))
        existing_xp: dict[tuple[int, str], int] = {}

        async with self.bot.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT user_id, role_name, xp
                FROM newwerewolf_role_xp
                WHERE user_id = ANY($1::bigint[])
                """,
                user_ids,
            )
            for row in rows:
                existing_xp[(int(row["user_id"]), str(row["role_name"]).casefold())] = (
                    max(0, int(row["xp"] or 0))
                )

            await conn.executemany(
                """
                INSERT INTO newwerewolf_role_xp (user_id, role_name, xp)
                VALUES ($1, $2, $3)
                ON CONFLICT (user_id, role_name)
                DO UPDATE SET
                    xp = newwerewolf_role_xp.xp + EXCLUDED.xp,
                    updated_at = now()
                """,
                updates,
            )

        xp_lines: list[str] = []
        level_lines: list[str] = []
        for player, role_for_xp, role_key, gained_xp in xp_events:
            player_id = player.user.id
            before_xp = existing_xp.get((player_id, role_key), 0)
            after_xp = before_xp + gained_xp
            before_level = role_level_from_xp(before_xp)
            after_level = role_level_from_xp(after_xp)

            xp_lines.append(
                _("{player} +{xp} XP ({role})").format(
                    player=getattr(player.user, "display_name", str(player.user)),
                    xp=gained_xp,
                    role=self._role_display_name(role_for_xp),
                )
            )

            if after_level <= before_level:
                continue

            unlock_tiers = ADVANCED_ROLE_TIERS_BY_BASE.get(role_for_xp, {})
            unlocked_now = [
                advanced_role
                for unlock_level, advanced_role in sorted(
                    unlock_tiers.items(), key=lambda pair: pair[0]
                )
                if before_level < unlock_level <= after_level
            ]
            if unlocked_now:
                mode_locked_unlocks = set(unavailable_roles_for_mode(unlocked_now, game.mode))
                unlock_labels: list[str] = []
                for unlocked_role in unlocked_now:
                    unlocked_name = self._role_display_name(unlocked_role)
                    if unlocked_role in mode_locked_unlocks:
                        unlocked_name = _("{role} (available in other modes)").format(
                            role=unlocked_name
                        )
                    unlock_labels.append(unlocked_name)
                level_lines.append(
                    _(
                        "{player} leveled **{role}** to **Level {level}** and unlocked:"
                        " **{unlocks}**."
                    ).format(
                        player=player.user.mention,
                        role=self._role_display_name(role_for_xp),
                        level=after_level,
                        unlocks=", ".join(unlock_labels),
                    )
                )
            else:
                level_lines.append(
                    _("{player} leveled **{role}** to **Level {level}**.").format(
                        player=player.user.mention,
                        role=self._role_display_name(role_for_xp),
                        level=after_level,
                    )
                )

        winner_embed_updated = await self._append_xp_to_winner_embed(game, xp_lines)
        if not winner_embed_updated and xp_lines:
            await self._send_role_xp_summary_embed(game, xp_lines)
        if level_lines:
            await self._send_level_up_summary_embed(game, level_lines)

    async def _append_xp_to_winner_embed(self, game: Game, xp_lines: list[str]) -> bool:
        endgame_message = getattr(game, "endgame_summary_message", None)
        if endgame_message is None or not xp_lines:
            return False
        if not getattr(endgame_message, "embeds", None):
            return False

        try:
            embed = endgame_message.embeds[0].copy()
            for idx, chunk in enumerate(self._chunk_lines(xp_lines, max_chars=1000)):
                field_name = _("Role XP Earned")
                if idx > 0:
                    field_name = _("Role XP Earned (cont.)")
                embed.add_field(name=field_name, value=chunk, inline=False)
            await endgame_message.edit(embed=embed)
            return True
        except (discord.Forbidden, discord.HTTPException):
            return False

    async def _send_role_xp_summary_embed(self, game: Game, xp_lines: list[str]) -> None:
        chunks = self._chunk_lines(xp_lines, max_chars=3800)
        for idx, chunk in enumerate(chunks, start=1):
            embed = discord.Embed(
                title=_("Role XP Earned"),
                description=chunk,
                colour=self.bot.config.game.primary_colour,
            )
            if len(chunks) > 1:
                embed.set_footer(text=_("Page {page}/{total}").format(page=idx, total=len(chunks)))
            await game.ctx.send(embed=embed)

    async def _send_level_up_summary_embed(self, game: Game, level_lines: list[str]) -> None:
        chunks = self._chunk_lines(level_lines, max_chars=3800)
        for idx, chunk in enumerate(chunks, start=1):
            embed = discord.Embed(
                title=_("Role Level Ups"),
                description=chunk,
                colour=self.bot.config.game.primary_colour,
            )
            if len(chunks) > 1:
                embed.set_footer(text=_("Page {page}/{total}").format(page=idx, total=len(chunks)))
            await game.ctx.send(embed=embed)

    @staticmethod
    def _role_display_name(role: ROLES) -> str:
        return role.name.title().replace("_", " ")

    @staticmethod
    def _xp_progress_fraction(xp: int) -> tuple[int, int]:
        xp_value = max(0, int(xp or 0))
        xp_per_level = max(1, int(ROLE_XP_PER_LEVEL))
        if xp_value == 0:
            return 0, xp_per_level
        # Keep progress aligned with current role_level_from_xp thresholds.
        return ((xp_value - 1) % xp_per_level) + 1, xp_per_level

    async def _fetch_user_role_xp_map(self, user_id: int) -> dict[str, int]:
        if not hasattr(self.bot, "pool"):
            return {}
        try:
            await self._ensure_role_xp_tables()
        except Exception:
            pass
        try:
            async with self.bot.pool.acquire() as conn:
                rows = await conn.fetch(
                    """
                    SELECT role_name, xp
                    FROM newwerewolf_role_xp
                    WHERE user_id = $1
                    """,
                    user_id,
                )
        except Exception:
            return {}

        xp_map: dict[str, int] = {}
        for row in rows:
            role_name = str(row["role_name"]).strip().casefold()
            try:
                xp_value = max(0, int(row["xp"] or 0))
            except (TypeError, ValueError):
                continue
            xp_map[role_name] = xp_value
        return xp_map

    @staticmethod
    def _chunk_lines(lines: list[str], *, max_chars: int = 3800) -> list[str]:
        chunks: list[str] = []
        current: list[str] = []
        current_len = 0
        for line in lines:
            if current and current_len + len(line) + 1 > max_chars:
                chunks.append("\n".join(current))
                current = []
                current_len = 0
            current.append(line)
            current_len += len(line) + 1
        if current:
            chunks.append("\n".join(current))
        return chunks

    def _make_tutorial_embed(
        self,
        *,
        ctx,
        title: str,
        description: str,
    ) -> discord.Embed:
        return discord.Embed(
            title=title,
            description=description,
            colour=self.bot.config.game.primary_colour,
        ).set_author(name=str(ctx.author), icon_url=ctx.author.display_avatar.url)

    def _build_tutorial_embeds(self, *, ctx, track: str) -> list[discord.Embed]:
        prefix = ctx.clean_prefix
        embeds: list[discord.Embed] = []

        if track == "generic":
            embeds.append(
                self._make_tutorial_embed(
                    ctx=ctx,
                    title=_("NewWerewolf Tutorial: Generic"),
                    description=_(
                        "**What this game is:**\n"
                        "Werewolf is an information and coordination game.\n\n"
                        "**Core loop:**\n"
                        "1. **Night:** hidden roles act.\n"
                        "2. **Day:** players discuss and vote.\n"
                        "3. Repeat until a win condition is reached.\n\n"
                        "**Main goal:**\n"
                        "- Village: remove wolf threats.\n"
                        "- Werewolves: gain majority/control.\n"
                        "- Solos: complete their own objective.\n\n"
                        "Use `{prefix}nww tutorial village`, `{prefix}nww tutorial"
                        " werewolf`, or `{prefix}nww tutorial solo` for team-specific"
                        " coaching."
                    ).format(prefix=prefix),
                )
            )
            embeds.append(
                self._make_tutorial_embed(
                    ctx=ctx,
                    title=_("Generic: How To Think Each Phase"),
                    description=_(
                        "**Night mindset:**\n"
                        "- Value information and role protection.\n"
                        "- Plan one night ahead.\n\n"
                        "**Day mindset:**\n"
                        "- Turn information into readable claims.\n"
                        "- Vote with a reason, not a guess.\n\n"
                        "**Dawn recap reading:**\n"
                        "- Who died?\n"
                        "- Which team benefits from that death?\n"
                        "- Which claims became stronger/weaker?"
                    ),
                )
            )
            embeds.append(
                self._make_tutorial_embed(
                    ctx=ctx,
                    title=_("Generic: New Player Checklist"),
                    description=_(
                        "1. Share **why** you suspect someone.\n"
                        "2. Track claim history (who said what, when).\n"
                        "3. Avoid hard tunnel vision after one clue.\n"
                        "4. Use role power with team value in mind.\n"
                        "5. Re-evaluate after every night recap.\n\n"
                        "**Useful commands:**\n"
                        "- `{prefix}nww roles <role>`\n"
                        "- `{prefix}nww myrole`\n"
                        "- `{prefix}nww progress`"
                    ).format(prefix=prefix),
                )
            )
            return embeds

        if track == "village":
            embeds.append(
                self._make_tutorial_embed(
                    ctx=ctx,
                    title=_("Village Tutorial: Win Condition"),
                    description=_(
                        "**Village wins by reducing wolf threat to zero.**\n\n"
                        "**Your resources:**\n"
                        "- Information roles (Seer/Aura Seer/Detective)\n"
                        "- Protection roles (Doctor/Bodyguard)\n"
                        "- Vote control and discussion quality\n\n"
                        "Village loses when it ignores information timing and wastes"
                        " votes."
                    ),
                )
            )
            embeds.append(
                self._make_tutorial_embed(
                    ctx=ctx,
                    title=_("Village Tutorial: Seer + Doctor Priority"),
                    description=_(
                        "**Seer importance:**\n"
                        "- Seer creates high-value, directional info.\n"
                        "- Wrongly exposed Seer often dies fast and village loses"
                        " momentum.\n\n"
                        "**Doctor importance:**\n"
                        "- Doctor should often protect expected wolf targets.\n"
                        "- Early game, protecting Seer-equivalent claims is usually"
                        " high value.\n\n"
                        "**Rule of thumb:**\n"
                        "Protect information generation before low-impact targets."
                    ),
                )
            )
            embeds.append(
                self._make_tutorial_embed(
                    ctx=ctx,
                    title=_("Village Tutorial: Day Vote Discipline"),
                    description=_(
                        "1. Ask for structured claim order when possible.\n"
                        "2. Compare today’s statements vs previous day.\n"
                        "3. Avoid panic votes near timer end.\n"
                        "4. If uncertain, vote the highest-risk unresolved slot.\n\n"
                        "**Common error:**\n"
                        "Lynching for tone only, ignoring hard contradictions."
                    ),
                )
            )
            return embeds

        if track == "werewolf":
            embeds.append(
                self._make_tutorial_embed(
                    ctx=ctx,
                    title=_("Werewolf Tutorial: Win Condition"),
                    description=_(
                        "**Werewolves win by controlling parity/majority.**\n\n"
                        "**What wins games:**\n"
                        "- Correct night kill priorities\n"
                        "- Day narrative control\n"
                        "- Avoiding avoidable partner losses"
                    ),
                )
            )
            embeds.append(
                self._make_tutorial_embed(
                    ctx=ctx,
                    title=_("Werewolf Tutorial: Night Kill Priority"),
                    description=_(
                        "**Default priority:**\n"
                        "1. Confirmed/likely information role\n"
                        "2. Confirmed/likely protector\n"
                        "3. Strong organizer/shot-caller\n\n"
                        "If village is disorganized, removing leadership can be better"
                        " than removing hidden utility."
                    ),
                )
            )
            embeds.append(
                self._make_tutorial_embed(
                    ctx=ctx,
                    title=_("Werewolf Tutorial: Day Play"),
                    description=_(
                        "1. Push coherent alternatives, not random chaos.\n"
                        "2. Keep fake-claim stories consistent across days.\n"
                        "3. Don’t over-defend teammates in obviously losing spots.\n"
                        "4. Track which villagers are driving consensus.\n\n"
                        "**Goal:** make village spend votes inefficiently."
                    ),
                )
            )
            return embeds

        if track == "solo":
            embeds.append(
                self._make_tutorial_embed(
                    ctx=ctx,
                    title=_("Solo Tutorial: Win Condition"),
                    description=_(
                        "**Solo roles do not follow village/wolf objectives.**\n\n"
                        "Your decision quality depends on your exact role objective:\n"
                        "- survive alone,\n"
                        "- force a specific elimination pattern,\n"
                        "- or complete a role-specific trigger."
                    ),
                )
            )
            embeds.append(
                self._make_tutorial_embed(
                    ctx=ctx,
                    title=_("Solo Tutorial: Threat Management"),
                    description=_(
                        "**As solo, every team can become your enemy.**\n\n"
                        "1. Stay hard to classify early.\n"
                        "2. Avoid overclaiming power too soon.\n"
                        "3. Let major teams pressure each other when possible.\n"
                        "4. Preserve your key ability timing for swing moments."
                    ),
                )
            )
            embeds.append(
                self._make_tutorial_embed(
                    ctx=ctx,
                    title=_("Solo Tutorial: Endgame Planning"),
                    description=_(
                        "**Think 2 phases ahead.**\n\n"
                        "- Which deaths help your exact objective?\n"
                        "- Which player must stay alive for your path?\n"
                        "- What claim keeps you alive one more day?\n\n"
                        "Solo players lose most often by revealing their path too early."
                    ),
                )
            )
            return embeds

        return embeds

    @staticmethod
    def _tutorial_normalize_token(token: str) -> str:
        return str(token).strip().casefold().replace("-", "").replace("_", "")

    def _parse_tutorial_track_and_mode(self, raw: str | None) -> tuple[str | None, str]:
        mode = "sim"
        selected_track: str | None = None
        if raw is None:
            return selected_track, mode

        track_aliases = {
            "generic": "generic",
            "general": "generic",
            "overview": "generic",
            "village": "village",
            "villager": "village",
            "town": "village",
            "werewolf": "werewolf",
            "wolf": "werewolf",
            "ww": "werewolf",
            "solo": "solo",
            "loner": "solo",
            "loners": "solo",
        }
        sim_tokens = {"sim", "interactive", "play", "practice", "scenario"}
        text_tokens = {"text", "static", "guide", "pages", "read"}

        raw_text = str(raw).strip()
        if not raw_text:
            return selected_track, mode

        tokens = [
            self._tutorial_normalize_token(token)
            for token in raw_text.replace(",", " ").split()
        ]

        for token in tokens:
            if token in text_tokens:
                mode = "text"
                continue
            if token in sim_tokens:
                mode = "sim"
                continue
            if selected_track is None:
                mapped_track = track_aliases.get(token)
                if mapped_track is not None:
                    selected_track = mapped_track

        if selected_track is None:
            normalized_full = self._tutorial_normalize_token(raw_text)
            if normalized_full in text_tokens:
                mode = "text"
            elif normalized_full in sim_tokens:
                mode = "sim"
            else:
                selected_track = track_aliases.get(normalized_full)

        return selected_track, mode

    @staticmethod
    def _is_tutorial_message_from_author(ctx, message: discord.Message) -> bool:
        return message.author.id == ctx.author.id and message.channel.id == ctx.channel.id

    def _tutorial_next_progress_text(self, ctx) -> str | None:
        progress = self.tutorial_progress.get(ctx.channel.id)
        if not progress:
            return None
        total = max(1, int(progress.get("total", 1)))
        current_step = int(progress.get("step", 0)) + 1
        if current_step > total:
            current_step = total
        progress["step"] = current_step
        return _("Step {step}/{total}").format(step=current_step, total=total)

    @staticmethod
    def _tutorial_review_line(*, label: str, is_good: bool, detail: str) -> str:
        verdict = _("Strong") if is_good else _("Risky")
        return _("- {label}: {verdict} ({detail})").format(
            label=label,
            verdict=verdict,
            detail=detail,
        )

    @staticmethod
    def _tutorial_roster_lines(
        roster: list[dict[str, object]],
        *,
        viewer_name: str | None = None,
        reveal_all_roles: bool = False,
    ) -> list[str]:
        viewer_key = str(viewer_name).casefold() if viewer_name else None
        lines: list[str] = []
        for entry in roster:
            name = str(entry.get("name", "Unknown"))
            role = str(entry.get("role", "Unknown"))
            alive = bool(entry.get("alive", True))
            role_revealed = bool(entry.get("revealed", False))
            reveal_on_death = bool(entry.get("reveal_on_death", True))
            is_viewer = viewer_key is not None and name.casefold() == viewer_key
            if reveal_all_roles or is_viewer or role_revealed or (not alive and reveal_on_death):
                displayed_role = role
            else:
                displayed_role = _("Hidden Role")
            state = _("Alive") if alive else _("Dead")
            icon = "🟢" if alive else "💀"
            lines.append(f"{icon} {name} - {displayed_role} ({state})")
        return lines

    @staticmethod
    def _tutorial_mark_dead(
        roster: list[dict[str, object]],
        *names: str,
        reveal_role: bool = True,
    ) -> None:
        wanted = {str(name).casefold() for name in names}
        for entry in roster:
            entry_name = str(entry.get("name", "")).casefold()
            if entry_name in wanted:
                entry["alive"] = False
                if reveal_role:
                    entry["revealed"] = True

    async def _tutorial_send_state_embed(
        self,
        ctx,
        *,
        track: str,
        phase: str,
        objective: str,
        summary: str,
        roster: list[dict[str, object]],
    ) -> None:
        progress_text = self._tutorial_next_progress_text(ctx)
        board_lines = self._tutorial_roster_lines(
            roster,
            viewer_name=str(ctx.author.display_name),
        )
        title_text = _("Tutorial [{track}] - {phase}").format(
            track=track.title(),
            phase=phase,
        )
        if progress_text:
            title_text = f"{progress_text} | {title_text}"
        embed = discord.Embed(
            title=title_text,
            description=summary,
            colour=self.bot.config.game.primary_colour,
        ).set_author(name=str(ctx.author), icon_url=ctx.author.display_avatar.url)
        embed.add_field(name=_("Objective"), value=objective, inline=False)
        embed.add_field(
            name=_("Board State"),
            value="\n".join(board_lines) if board_lines else _("No players."),
            inline=False,
        )
        footer = _("Type continue/resume to advance, pause to hold, or stop to end.")
        if progress_text:
            footer = f"{progress_text} | {footer}"
        embed.set_footer(text=footer)
        await ctx.send(embed=embed)

    async def _tutorial_send_discussion_embed(
        self,
        ctx,
        *,
        track: str,
        scene: str,
        transcript_lines: list[str],
        important_lines: list[str],
    ) -> None:
        progress_text = self._tutorial_next_progress_text(ctx)
        transcript = "\n".join(transcript_lines) if transcript_lines else _("No transcript.")
        key_points = "\n".join(f"• {line}" for line in important_lines)
        if not key_points:
            key_points = _("No key points.")

        title_text = _("Tutorial [{track}] - {scene}").format(
            track=track.title(),
            scene=scene,
        )
        if progress_text:
            title_text = f"{progress_text} | {title_text}"
        embed = discord.Embed(
            title=title_text,
            description=_("Simulated day chat. Read it like a real game table."),
            colour=self.bot.config.game.primary_colour,
        ).set_author(name=str(ctx.author), icon_url=ctx.author.display_avatar.url)
        embed.add_field(name=_("Chat Transcript"), value=transcript, inline=False)
        embed.add_field(name=_("What's Important"), value=key_points, inline=False)
        footer = _("Your next choice should apply these priorities.")
        if progress_text:
            footer = f"{progress_text} | {footer}"
        embed.set_footer(text=footer)
        await ctx.send(embed=embed)

    async def _tutorial_send_claim_embed(
        self,
        ctx,
        *,
        track: str,
        scene: str,
        claim_lines: list[str],
        proof_lines: list[str],
        important_lines: list[str],
    ) -> None:
        progress_text = self._tutorial_next_progress_text(ctx)
        claims = "\n".join(claim_lines) if claim_lines else _("No claims.")
        proofs = "\n".join(proof_lines) if proof_lines else _("No proof notes.")
        key_points = "\n".join(f"• {line}" for line in important_lines)
        if not key_points:
            key_points = _("No key points.")

        title_text = _("Tutorial [{track}] - {scene}").format(
            track=track.title(),
            scene=scene,
        )
        if progress_text:
            title_text = f"{progress_text} | {title_text}"
        embed = discord.Embed(
            title=title_text,
            description=_("Claim vs counter-claim simulation. Resolve it with evidence."),
            colour=self.bot.config.game.primary_colour,
        ).set_author(name=str(ctx.author), icon_url=ctx.author.display_avatar.url)
        embed.add_field(name=_("Claim Board"), value=claims, inline=False)
        embed.add_field(name=_("Proof Board"), value=proofs, inline=False)
        embed.add_field(name=_("What's Important"), value=key_points, inline=False)
        footer = _("Prioritize consistency, timestamps, and role logic.")
        if progress_text:
            footer = f"{progress_text} | {footer}"
        embed.set_footer(text=footer)
        await ctx.send(embed=embed)

    async def _tutorial_wait_continue(self, ctx, *, timeout: int = 180) -> bool:
        await ctx.send(
            _(
                "Tutorial paused. Type `continue` (or `resume`) to continue, `pause` to"
                " hold, or `stop` to end. (No number needed on this step.)"
            )
        )
        paused = False
        while True:
            try:
                response = await self.bot.wait_for(
                    "message",
                    timeout=timeout,
                    check=lambda message: self._is_tutorial_message_from_author(
                        ctx, message
                    ),
                )
            except asyncio.TimeoutError:
                await ctx.send(_("Tutorial ended due to inactivity."))
                return False

            token = response.content.strip().casefold()
            if token in {"stop", "cancel", "quit", "exit", "end"}:
                await ctx.send(_("Tutorial stopped."))
                return False
            if token in {"continue", "resume", "next", "c", "r"}:
                if paused:
                    await ctx.send(_("Resuming tutorial."))
                return True
            if token in {"pause", "hold", "wait", "p"}:
                paused = True
                await ctx.send(_("Tutorial is paused. Type `resume` or `stop`."))
                continue

            await ctx.send(
                _(
                    "Reply with `continue`, `resume`, `pause`, or `stop` to control"
                    " this tutorial."
                )
            )

    async def _tutorial_choose_option(
        self,
        ctx,
        *,
        track: str,
        title: str,
        prompt: str,
        options: list[str],
        timeout: int = 180,
    ) -> int | None:
        progress_text = self._tutorial_next_progress_text(ctx)
        option_lines = [f"{index}. {option}" for index, option in enumerate(options, 1)]
        title_text = _("Tutorial [{track}] - Decision").format(track=track.title())
        if progress_text:
            title_text = f"{progress_text} | {title_text}"
        embed = discord.Embed(
            title=title_text,
            description=f"**{title}**\n{prompt}\n\n" + "\n".join(option_lines),
            colour=self.bot.config.game.primary_colour,
        ).set_author(name=str(ctx.author), icon_url=ctx.author.display_avatar.url)
        footer = _(
            "Reply with a number from 1 to {limit}, or type `stop` to end."
        ).format(limit=len(options))
        if progress_text:
            footer = f"{progress_text} | {footer}"
        embed.set_footer(text=footer)
        await ctx.send(embed=embed)

        while True:
            try:
                response = await self.bot.wait_for(
                    "message",
                    timeout=timeout,
                    check=lambda message: self._is_tutorial_message_from_author(
                        ctx, message
                    ),
                )
            except asyncio.TimeoutError:
                await ctx.send(_("Tutorial ended due to inactivity."))
                return None

            content = response.content.strip()
            token = content.casefold()
            if token in {"stop", "cancel", "quit", "exit", "end"}:
                await ctx.send(_("Tutorial stopped."))
                return None
            if token in {"pause", "hold", "wait", "p"}:
                await ctx.send(_("Tutorial is paused. Type `resume` to continue."))
                continue
            if token in {"resume", "continue", "next", "c", "r"}:
                await ctx.send(
                    _(
                        "This step needs a number input. Choose 1-{limit}."
                    ).format(limit=len(options))
                )
                continue

            try:
                selected_number = int(content)
            except ValueError:
                await ctx.send(
                    _(
                        "Please reply with a valid option number (for example `1`) or"
                        " type `stop`."
                    )
                )
                continue

            if 1 <= selected_number <= len(options):
                return selected_number - 1

            await ctx.send(
                _("Option out of range. Choose a number between 1 and {limit}.").format(
                    limit=len(options)
                )
            )

    @staticmethod
    def _tutorial_find_player(
        roster: list[dict[str, object]], name: str
    ) -> dict[str, object] | None:
        needle = str(name).casefold()
        for entry in roster:
            if str(entry.get("name", "")).casefold() == needle:
                return entry
        return None

    def _tutorial_is_alive(self, roster: list[dict[str, object]], name: str) -> bool:
        player = self._tutorial_find_player(roster, name)
        return bool(player and player.get("alive", False))

    @staticmethod
    def _tutorial_alive_names(
        roster: list[dict[str, object]], *, exclude: set[str] | None = None
    ) -> list[str]:
        excluded = {name.casefold() for name in (exclude or set())}
        return [
            str(entry["name"])
            for entry in roster
            if bool(entry.get("alive", False))
            and str(entry.get("name", "")).casefold() not in excluded
        ]

    async def _tutorial_dm_choose(
        self,
        ctx,
        *,
        title: str,
        prompt: str,
        options: list[str],
        timeout: int = 180,
    ) -> int | None:
        try:
            dm_channel = await ctx.author.create_dm()
        except discord.Forbidden:
            await ctx.send(
                _(
                    "I couldn't DM your night action prompt. Please enable DMs from this"
                    " server for tutorials."
                )
            )
            return None

        option_lines = [f"{index}. {option}" for index, option in enumerate(options, 1)]
        embed = discord.Embed(
            title=_("Tutorial Night Action"),
            description=f"**{title}**\n{prompt}\n\n" + "\n".join(option_lines),
            colour=self.bot.config.game.primary_colour,
        ).set_author(name=str(ctx.author), icon_url=ctx.author.display_avatar.url)
        embed.set_footer(text=_("Reply with a number or `stop`."))
        await dm_channel.send(embed=embed)
        await ctx.send(_("📩 Check your DMs for your night action."))

        while True:
            try:
                response = await self.bot.wait_for(
                    "message",
                    timeout=timeout,
                    check=lambda message: (
                        message.author.id == ctx.author.id
                        and message.channel.id == dm_channel.id
                    ),
                )
            except asyncio.TimeoutError:
                await ctx.send(_("Tutorial ended due to DM inactivity."))
                return None

            token = response.content.strip().casefold()
            if token in {"stop", "cancel", "quit", "exit", "end"}:
                await ctx.send(_("Tutorial stopped."))
                return None
            try:
                selected = int(token)
            except ValueError:
                await dm_channel.send(
                    _("Send a number from 1 to {limit}, or `stop`.").format(
                        limit=len(options)
                    )
                )
                continue
            if 1 <= selected <= len(options):
                return selected - 1
            await dm_channel.send(
                _("Option out of range. Choose 1 to {limit}.").format(limit=len(options))
            )

    async def _tutorial_dm_info(self, ctx, *, title: str, text: str) -> None:
        try:
            dm_channel = await ctx.author.create_dm()
        except discord.Forbidden:
            return
        embed = discord.Embed(
            title=title,
            description=text,
            colour=self.bot.config.game.primary_colour,
        )
        await dm_channel.send(embed=embed)

    async def _tutorial_play_chat(
        self, ctx, *, lines: list[tuple[str, str]], delay: float = 1.1
    ) -> None:
        for speaker, message in lines:
            await ctx.send(f"**{speaker}:** {message}")
            await asyncio.sleep(delay)

    async def _tutorial_coach_pause(
        self,
        ctx,
        *,
        track: str,
        title: str,
        text: str,
    ) -> bool:
        await ctx.send(
            embed=discord.Embed(
                title=_("Tutorial Coach [{track}] - {title}").format(
                    track=track.title(),
                    title=title,
                ),
                description=text,
                colour=self.bot.config.game.primary_colour,
            ).set_author(name=str(ctx.author), icon_url=ctx.author.display_avatar.url)
        )
        return await self._tutorial_wait_continue(ctx, timeout=300)

    async def _run_tutorial_story_generic(self, ctx) -> bool:
        user_name = str(ctx.author.display_name)
        roster: list[dict[str, object]] = [
            {"name": user_name, "role": "Seer", "alive": True, "revealed": True},
            {"name": "Rowan (Bot)", "role": "Doctor", "alive": True, "revealed": False},
            {"name": "Ivy (Bot)", "role": "Werewolf", "alive": True, "revealed": False},
            {"name": "Noah (Bot)", "role": "Villager", "alive": True, "revealed": False},
            {"name": "Luna (Bot)", "role": "Villager", "alive": True, "revealed": False},
        ]

        await self._tutorial_send_state_embed(
            ctx,
            track="generic",
            phase=_("Match Start"),
            objective=_("Play a full short match: night action, day talk, vote, outcome."),
            summary=_(
                "You are **Seer**. This tutorial now plays as a scripted match with live"
                " phase flow."
            ),
            roster=roster,
        )
        await self._tutorial_dm_info(
            ctx,
            title=_("Your Role: Seer"),
            text=_("Each night, inspect 1 player and learn their role."),
        )

        await self._tutorial_send_state_embed(
            ctx,
            track="generic",
            phase=_("Night 1"),
            objective=_("Use your Seer action from DM."),
            summary=_("Night has started. Wolves are coordinating."),
            roster=roster,
        )
        inspect_targets = self._tutorial_alive_names(roster, exclude={user_name})
        inspect_choice = await self._tutorial_dm_choose(
            ctx,
            title=_("Night 1 - Seer Inspect"),
            prompt=_("Who do you inspect?"),
            options=inspect_targets,
        )
        if inspect_choice is None:
            return False
        inspected_name = inspect_targets[inspect_choice]
        inspected_player = self._tutorial_find_player(roster, inspected_name)
        inspected_role = str(inspected_player["role"]) if inspected_player else _("Unknown")
        await self._tutorial_dm_info(
            ctx,
            title=_("Seer Result"),
            text=_("You inspected **{target}** and found **{role}**.").format(
                target=inspected_name,
                role=inspected_role,
            ),
        )

        dawn1_summary = _(
            "Wolves attacked **{you}**, but Doctor protection blocked it. No one died."
        ).format(you=user_name)
        await self._tutorial_send_state_embed(
            ctx,
            track="generic",
            phase=_("Dawn 1"),
            objective=_("Turn private information into public voting value."),
            summary=dawn1_summary,
            roster=roster,
        )
        await self._tutorial_play_chat(
            ctx,
            lines=[
                ("Rowan (Bot)", _("Night was clean. Let's use structure today.")),
                ("Ivy (Bot)", _("Fast claims are fake half the time.")),
                ("Noah (Bot)", _("Claim order first, then one vote target.")),
                ("Luna (Bot)", _("Agreed. No split wagons without evidence.")),
            ],
        )

        day1_choice_options = [
            _("Claim your Seer result and lock one target."),
            _("Soft-push without full claim."),
            _("Stay quiet and follow table momentum."),
        ]
        day1_choice = await self._tutorial_choose_option(
            ctx,
            track="generic",
            title=_("Day 1 - Your Move"),
            prompt=_("How do you use your night result?"),
            options=day1_choice_options,
        )
        if day1_choice is None:
            return False

        if inspected_role == "Werewolf" and day1_choice == 0:
            self._tutorial_mark_dead(roster, "Ivy (Bot)")
            if not await self._tutorial_coach_pause(
                ctx,
                track="generic",
                title=_("Why This Worked"),
                text=_(
                    "You converted private info into structured public action immediately."
                    " That is high-level village tempo."
                ),
            ):
                return False
            outcome = _(
                "Village executed **Ivy** from a clean Seer claim line. Village wins."
            )
        else:
            self._tutorial_mark_dead(roster, "Noah (Bot)")
            await self._tutorial_send_state_embed(
                ctx,
                track="generic",
                phase=_("Post-Vote 1"),
                objective=_("Recover after a weak day."),
                summary=_(
                    "Village misvoted **Noah**. Wolves now control match tempo."
                ),
                roster=roster,
            )
            await self._tutorial_send_state_embed(
                ctx,
                track="generic",
                phase=_("Night 2"),
                objective=_("Try to salvage with a second check."),
                summary=_("Night 2 started."),
                roster=roster,
            )
            night2_targets = self._tutorial_alive_names(roster, exclude={user_name})
            night2_choice = await self._tutorial_dm_choose(
                ctx,
                title=_("Night 2 - Seer Inspect"),
                prompt=_("Who do you inspect now?"),
                options=night2_targets,
            )
            if night2_choice is None:
                return False
            inspected2_name = night2_targets[night2_choice]
            inspected2_player = self._tutorial_find_player(roster, inspected2_name)
            inspected2_role = (
                str(inspected2_player["role"]) if inspected2_player else _("Unknown")
            )
            await self._tutorial_dm_info(
                ctx,
                title=_("Seer Result"),
                text=_("You inspected **{target}** and found **{role}**.").format(
                    target=inspected2_name,
                    role=inspected2_role,
                ),
            )
            self._tutorial_mark_dead(roster, "Rowan (Bot)")
            await self._tutorial_send_state_embed(
                ctx,
                track="generic",
                phase=_("Dawn 2"),
                objective=_("Final chance to force a correct vote."),
                summary=_("Wolves killed **Rowan** during Night 2."),
                roster=roster,
            )
            await self._tutorial_play_chat(
                ctx,
                lines=[
                    ("Luna (Bot)", _("We need one precise wagon now.")),
                    ("Ivy (Bot)", _("You're guessing, this isn't solved.")),
                ],
            )
            final_choice = await self._tutorial_choose_option(
                ctx,
                track="generic",
                title=_("Day 2 - Final Vote"),
                prompt=_("Who do you push now?"),
                options=[
                    _("Push Ivy with your full info timeline."),
                    _("Push Luna from behavior only."),
                    _("No clear push."),
                ],
            )
            if final_choice is None:
                return False
            if (
                final_choice == 0
                and (inspected_role == "Werewolf" or inspected2_role == "Werewolf")
            ):
                self._tutorial_mark_dead(roster, "Ivy (Bot)")
                outcome = _(
                    "Late recovery succeeded. **Ivy** was executed. Village wins narrowly."
                )
            else:
                outcome = _(
                    "Ivy survived to parity pressure. Werewolves win this scripted match."
                )

        await self._tutorial_send_state_embed(
            ctx,
            track="generic",
            phase=_("Game Over"),
            objective=_("Review how timing + claim clarity changed the whole game."),
            summary=outcome,
            roster=roster,
        )
        return True

    async def _run_tutorial_story_village(self, ctx) -> bool:
        user_name = str(ctx.author.display_name)
        roster: list[dict[str, object]] = [
            {"name": user_name, "role": "Doctor", "alive": True, "revealed": True},
            {"name": "Mira (Bot)", "role": "Seer", "alive": True, "revealed": False},
            {"name": "Nyx (Bot)", "role": "Werewolf", "alive": True, "revealed": False},
            {"name": "Cole (Bot)", "role": "Villager", "alive": True, "revealed": False},
            {"name": "Tara (Bot)", "role": "Villager", "alive": True, "revealed": False},
        ]

        await self._tutorial_send_state_embed(
            ctx,
            track="village",
            phase=_("Match Start"),
            objective=_("Protect information roles and convert claims into votes."),
            summary=_("You are **Doctor**. Your night protection is sent through DM."),
            roster=roster,
        )
        await self._tutorial_dm_info(
            ctx,
            title=_("Your Role: Doctor"),
            text=_("Each night, choose one player to protect from the wolf attack."),
        )

        await self._tutorial_send_state_embed(
            ctx,
            track="village",
            phase=_("Night 1"),
            objective=_("Choose your protection target in DM."),
            summary=_("Night 1 started."),
            roster=roster,
        )
        protect_targets = self._tutorial_alive_names(roster)
        protect_choice = await self._tutorial_dm_choose(
            ctx,
            title=_("Night 1 - Doctor Protect"),
            prompt=_("Who do you protect?"),
            options=protect_targets,
        )
        if protect_choice is None:
            return False
        protected_name = protect_targets[protect_choice]
        wolves_target = "Mira (Bot)"
        seer_alive = protected_name == wolves_target
        if not seer_alive:
            self._tutorial_mark_dead(roster, "Mira (Bot)")

        dawn_text = (
            _("Wolves attacked **Mira**, but your protection blocked it.")
            if seer_alive
            else _("Wolves killed **Mira**. Village lost Seer pressure.")
        )
        await self._tutorial_send_state_embed(
            ctx,
            track="village",
            phase=_("Dawn 1"),
            objective=_("Drive a structured vote from the available evidence."),
            summary=dawn_text,
            roster=roster,
        )
        chat_lines = (
            [
                ("Mira (Bot)", _("Seer claim. Nyx is wolf from Night 1.")),
                ("Nyx (Bot)", _("Fake claim. That's fabricated.")),
                ("Cole (Bot)", _("Resolve claims before voting.")),
            ]
            if seer_alive
            else [
                ("Cole (Bot)", _("Seer died. Read the kill value.")),
                ("Nyx (Bot)", _("No hard info, don't force a wagon.")),
                ("Tara (Bot)", _("Who benefited most from Seer dying?")),
            ]
        )
        await self._tutorial_play_chat(ctx, lines=chat_lines)

        vote_options = (
            [
                _("Vote Nyx from Seer claim + claim consistency."),
                _("Split to Cole from tone."),
                _("No commitment."),
            ]
            if seer_alive
            else [
                _("Pressure Nyx from kill-value logic."),
                _("Vote Tara randomly."),
                _("No commitment."),
            ]
        )
        vote_choice = await self._tutorial_choose_option(
            ctx,
            track="village",
            title=_("Day 1 - Vote"),
            prompt=_("Choose your day vote line."),
            options=vote_options,
        )
        if vote_choice is None:
            return False

        if vote_choice == 0:
            self._tutorial_mark_dead(roster, "Nyx (Bot)")
            outcome = _(
                "Village executed **Nyx** and removed wolf pressure. Village wins."
            )
        else:
            if seer_alive:
                self._tutorial_mark_dead(roster, "Cole (Bot)")
            else:
                self._tutorial_mark_dead(roster, "Tara (Bot)")
            await self._tutorial_send_state_embed(
                ctx,
                track="village",
                phase=_("Night 2"),
                objective=_("One last defensive cycle."),
                summary=_("Wolves still alive. Night 2 began."),
                roster=roster,
            )
            n2_targets = self._tutorial_alive_names(roster)
            n2_choice = await self._tutorial_dm_choose(
                ctx,
                title=_("Night 2 - Doctor Protect"),
                prompt=_("Who do you protect now?"),
                options=n2_targets,
            )
            if n2_choice is None:
                return False
            n2_protected = n2_targets[n2_choice]
            wolves_target_n2 = user_name
            if n2_protected != wolves_target_n2:
                self._tutorial_mark_dead(roster, user_name)
            await self._tutorial_send_state_embed(
                ctx,
                track="village",
                phase=_("Game Over"),
                objective=_("Understand why first-day vote discipline matters."),
                summary=_(
                    "Wolves closed the game through tempo advantage after the day miss."
                ),
                roster=roster,
            )
            return True

        await self._tutorial_send_state_embed(
            ctx,
            track="village",
            phase=_("Game Over"),
            objective=_("Protection + claim resolution + vote discipline."),
            summary=outcome,
            roster=roster,
        )
        return True

    async def _run_tutorial_story_werewolf(self, ctx) -> bool:
        user_name = str(ctx.author.display_name)
        roster: list[dict[str, object]] = [
            {"name": user_name, "role": "Werewolf", "alive": True, "revealed": True},
            {"name": "Fang (Bot)", "role": "Werewolf", "alive": True, "revealed": False},
            {"name": "Iris (Bot)", "role": "Seer", "alive": True, "revealed": False},
            {"name": "Theo (Bot)", "role": "Doctor", "alive": True, "revealed": False},
            {"name": "Mila (Bot)", "role": "Villager", "alive": True, "revealed": False},
        ]

        await self._tutorial_send_state_embed(
            ctx,
            track="werewolf",
            phase=_("Match Start"),
            objective=_("Use wolf night kills + day narrative to reach parity."),
            summary=_("You are **Werewolf** with Fang. Night kill choice is sent in DM."),
            roster=roster,
        )
        await self._tutorial_dm_info(
            ctx,
            title=_("Your Role: Werewolf"),
            text=_("At night, coordinate kill priority. During day, keep one coherent line."),
        )

        await self._tutorial_send_state_embed(
            ctx,
            track="werewolf",
            phase=_("Night 1"),
            objective=_("Choose your first wolf kill in DM."),
            summary=_("Night 1 started."),
            roster=roster,
        )
        kill_targets = self._tutorial_alive_names(roster, exclude={user_name, "Fang (Bot)"})
        kill_choice = await self._tutorial_dm_choose(
            ctx,
            title=_("Night 1 - Wolf Kill"),
            prompt=_("Who should the wolves attack?"),
            options=kill_targets,
        )
        if kill_choice is None:
            return False
        killed_name = kill_targets[kill_choice]
        if killed_name == "Theo (Bot)":
            self._tutorial_mark_dead(roster, "Theo (Bot)")
        elif killed_name == "Iris (Bot)":
            self._tutorial_mark_dead(roster, "Iris (Bot)")
        else:
            self._tutorial_mark_dead(roster, "Mila (Bot)")

        await self._tutorial_send_state_embed(
            ctx,
            track="werewolf",
            phase=_("Dawn 1"),
            objective=_("Control the day story before village organizes."),
            summary=_("Night kill resolved: **{target}** died.").format(target=killed_name),
            roster=roster,
        )
        await self._tutorial_play_chat(
            ctx,
            lines=[
                ("Mila (Bot)", _("That kill gives us alignment clues.")),
                ("Theo (Bot)", _("Let's anchor this day with consistency checks.")),
                ("Fang (Bot)", _("Too early to lock anyone.")),
            ],
        )
        day_choice_options = [
            _("Push one villager with consistent reasoning."),
            _("Spam conflicting pushes."),
            _("Over-defend Fang under pressure."),
        ]
        day_choice = await self._tutorial_choose_option(
            ctx,
            track="werewolf",
            title=_("Day 1 - Wolf Day Play"),
            prompt=_("How do you run the day?"),
            options=day_choice_options,
        )
        if day_choice is None:
            return False

        if day_choice == 0:
            target = "Mila (Bot)" if self._tutorial_is_alive(roster, "Mila (Bot)") else "Theo (Bot)"
            self._tutorial_mark_dead(roster, target)
        else:
            self._tutorial_mark_dead(roster, "Fang (Bot)")

        await self._tutorial_send_state_embed(
            ctx,
            track="werewolf",
            phase=_("Night 2"),
            objective=_("Finish parity if wolf position remains strong."),
            summary=_("Night 2 started."),
            roster=roster,
        )
        if not self._tutorial_is_alive(roster, user_name):
            return False
        alive_n2_targets = self._tutorial_alive_names(
            roster, exclude={user_name, "Fang (Bot)"}
        )
        if not alive_n2_targets:
            return False
        n2_choice = await self._tutorial_dm_choose(
            ctx,
            title=_("Night 2 - Wolf Kill"),
            prompt=_("Final kill target?"),
            options=alive_n2_targets,
        )
        if n2_choice is None:
            return False
        n2_target = alive_n2_targets[n2_choice]
        self._tutorial_mark_dead(roster, n2_target)

        wolves_alive = sum(
            1
            for entry in roster
            if bool(entry.get("alive"))
            and str(entry.get("role")).casefold() == "werewolf"
        )
        others_alive = sum(
            1
            for entry in roster
            if bool(entry.get("alive"))
            and str(entry.get("role")).casefold() != "werewolf"
        )
        if wolves_alive >= others_alive and wolves_alive > 0:
            outcome = _(
                "Wolves reached parity/control. Werewolf team wins this scripted match."
            )
        else:
            outcome = _(
                "Wolves failed to secure parity in time. Village survives and wins."
            )

        await self._tutorial_send_state_embed(
            ctx,
            track="werewolf",
            phase=_("Game Over"),
            objective=_("Night priority and coherent day pressure decide wolf games."),
            summary=outcome,
            roster=roster,
        )
        return True

    async def _run_tutorial_story_solo(self, ctx) -> bool:
        user_name = str(ctx.author.display_name)
        target_name = "Aria (Bot)"
        roster: list[dict[str, object]] = [
            {"name": user_name, "role": "Head Hunter", "alive": True, "revealed": True},
            {"name": target_name, "role": "Villager (Target)", "alive": True, "revealed": False},
            {"name": "Sven (Bot)", "role": "Werewolf", "alive": True, "revealed": False},
            {"name": "Mira (Bot)", "role": "Seer", "alive": True, "revealed": False},
            {"name": "Kade (Bot)", "role": "Doctor", "alive": True, "revealed": False},
        ]

        await self._tutorial_send_state_embed(
            ctx,
            track="solo",
            phase=_("Match Start"),
            objective=_("Get your target lynched without exposing your true objective."),
            summary=_("You are **Head Hunter**. Target is hidden from others."),
            roster=roster,
        )
        await self._tutorial_dm_info(
            ctx,
            title=_("Your Secret Objective"),
            text=_("Your target is **{target}**. Win by getting them lynched.").format(
                target=target_name
            ),
        )

        await self._tutorial_send_state_embed(
            ctx,
            track="solo",
            phase=_("Day 1"),
            objective=_("Shape vote pressure without obvious tunnel behavior."),
            summary=_("Discussion phase started."),
            roster=roster,
        )
        await self._tutorial_play_chat(
            ctx,
            lines=[
                ("Mira (Bot)", _("We need claim consistency and vote discipline.")),
                ("Sven (Bot)", _("Fast wagons usually miss wolves.")),
                ("Aria (Bot)", _("Anyone hard-pushing me this early is suspicious.")),
            ],
        )
        day1_choice = await self._tutorial_choose_option(
            ctx,
            track="solo",
            title=_("Day 1 - Solo Pressure"),
            prompt=_("How do you push your target?"),
            options=[
                _("Build a measured case with concrete contradictions."),
                _("Hard tunnel your target with weak evidence."),
                _("Stay fully passive."),
            ],
        )
        if day1_choice is None:
            return False
        vote1_choice = await self._tutorial_choose_option(
            ctx,
            track="solo",
            title=_("Day 1 - Vote"),
            prompt=_("Who does your vote push most?"),
            options=[
                _(f"{target_name}"),
                _("Kade (Bot)"),
                _("No clear vote"),
            ],
        )
        if vote1_choice is None:
            return False

        if day1_choice == 0 and vote1_choice == 0:
            self._tutorial_mark_dead(roster, target_name)
            outcome = _(
                "Target lynched on Day 1. Solo objective complete. Head Hunter wins."
            )
            await self._tutorial_send_state_embed(
                ctx,
                track="solo",
                phase=_("Game Over"),
                objective=_("Controlled pressure wins solo games."),
                summary=outcome,
                roster=roster,
            )
            return True

        if vote1_choice == 1:
            self._tutorial_mark_dead(roster, "Kade (Bot)")
        self._tutorial_mark_dead(roster, "Mira (Bot)")

        await self._tutorial_send_state_embed(
            ctx,
            track="solo",
            phase=_("Dawn 2"),
            objective=_("Second chance to close your objective."),
            summary=_("Night kill: **Mira** died. The table is more volatile now."),
            roster=roster,
        )
        final_choice = await self._tutorial_choose_option(
            ctx,
            track="solo",
            title=_("Day 2 - Final Push"),
            prompt=_("Commit to your endgame line."),
            options=[
                _(f"Commit vote pressure on {target_name}."),
                _("Pivot to another wagon."),
                _("Stay vague."),
            ],
        )
        if final_choice is None:
            return False

        if final_choice == 0:
            self._tutorial_mark_dead(roster, target_name)
            outcome = _(
                "Target lynched on Day 2. Head Hunter objective complete. Solo wins."
            )
        else:
            outcome = _(
                "Target survived. Solo objective failed and major teams close the game."
            )

        await self._tutorial_send_state_embed(
            ctx,
            track="solo",
            phase=_("Game Over"),
            objective=_("Solo success requires objective discipline over comfort votes."),
            summary=outcome,
            roster=roster,
        )
        return True

    async def _run_tutorial_sim_generic(self, ctx) -> bool:
        you_name = str(ctx.author.display_name)
        roster: list[dict[str, object]] = [
            {"name": you_name, "role": "Seer", "alive": True},
            {"name": "Rowan (Bot)", "role": "Doctor", "alive": True},
            {"name": "Ivy (Bot)", "role": "Werewolf", "alive": True},
            {"name": "Noah (Bot)", "role": "Villager", "alive": True},
            {"name": "Luna (Bot)", "role": "Villager", "alive": True},
        ]
        await self._tutorial_send_state_embed(
            ctx,
            track="generic",
            phase=_("Setup"),
            objective=_(
                "Use night information and convert it into a strong day vote."
            ),
            summary=_(
                "You are in a simulated game with bots. Focus on decision quality,"
                " not speed."
            ),
            roster=roster,
        )
        if not await self._tutorial_wait_continue(ctx):
            return False

        inspect_options = [
            _("Ivy (aggressive push, high threat if wolf)."),
            _("Noah (quiet slot, low info so far)."),
            _("Rowan (claimed Doctor, verify claim)."),
        ]
        inspect_choice = await self._tutorial_choose_option(
            ctx,
            track="generic",
            title=_("Night 1 - Seer Check"),
            prompt=_("Who should you inspect first?"),
            options=inspect_options,
        )
        if inspect_choice is None:
            return False

        if inspect_choice == 0:
            inspection_result = _(
                "You inspected **Ivy** and learned they are a **Werewolf**."
            )
        elif inspect_choice == 1:
            inspection_result = _(
                "You inspected **Noah** and learned they are **Village**."
            )
        else:
            inspection_result = _(
                "You inspected **Rowan** and learned they are the **Doctor**."
            )

        await self._tutorial_send_state_embed(
            ctx,
            track="generic",
            phase=_("Night 1 Recap"),
            objective=_("Track who lived, who died, and what your check unlocked."),
            summary=_(
                "Werewolves attacked **you**, but Rowan protected you.\n{result}"
            ).format(result=inspection_result),
            roster=roster,
        )
        if not await self._tutorial_wait_continue(ctx):
            return False

        if inspect_choice == 0:
            generic_transcript = [
                _("Narrator: A Seer claim with a wolf result just entered the table."),
                _("Ivy (Bot): Fake claim. You're lying."),
                _("Rowan (Bot): Claim order now. Any counterclaim to Seer?"),
                _("Noah (Bot): If no counterclaim, Ivy is the highest-value vote."),
            ]
        else:
            generic_transcript = [
                _("Narrator: A Seer claim with a non-wolf result is on the table."),
                _("Ivy (Bot): This sounds like stalling."),
                _("Rowan (Bot): Let's do role-claim order, then lock a vote."),
                _("Noah (Bot): We need reasons tied to night events, not tone only."),
            ]
        await self._tutorial_send_discussion_embed(
            ctx,
            track="generic",
            scene=_("Day 1 Discussion"),
            transcript_lines=generic_transcript,
            important_lines=[
                _("Force claim order and resolve contradictions."),
                _("Prioritize checkable information over tone reads."),
                _("Translate discussion into one clear vote target."),
            ],
        )
        if not await self._tutorial_wait_continue(ctx):
            return False

        discussion_options = [
            _("Call for claim order, verify claims, and lock one vote."),
            _("Argue mostly from vibes without claim structure."),
            _("Stay passive and let the timer decide."),
        ]
        discussion_choice = await self._tutorial_choose_option(
            ctx,
            track="generic",
            title=_("Day 1 - Discussion Response"),
            prompt=_("What is your best response to this table talk?"),
            options=discussion_options,
        )
        if discussion_choice is None:
            return False

        if inspect_choice == 0:
            claim_lines = [
                _("Claim A: Seer claim. N1 check -> Ivy is wolf."),
                _("Claim B: Counter-claim Seer. N1 check -> Noah is wolf."),
                _("Rowan (Bot): Two Seer claims. Post night logs now."),
            ]
            proof_lines = [
                _("Claim A: Same target/result sequence before and after pressure."),
                _("Claim B: Changed story from 'Rowan suspicious' to 'Noah wolf'."),
                _("Noah (Bot): Ivy only named me after your claim landed."),
            ]
        else:
            claim_lines = [
                _("Claim A: Seer claim with a non-wolf result from N1."),
                _("Claim B: Counter-claim Seer and calls Claim A fake."),
                _("Rowan (Bot): Both claimants must give exact target+result logs."),
            ]
            proof_lines = [
                _("Claim A: N1 target and reason stayed consistent."),
                _("Claim B: Gives result without clear N1 target timing."),
                _("Noah (Bot): Counter-claim arrived only after claim-order request."),
            ]

        await self._tutorial_send_claim_embed(
            ctx,
            track="generic",
            scene=_("Day 1 Claim Duel"),
            claim_lines=claim_lines,
            proof_lines=proof_lines,
            important_lines=[
                _("Force both claimants to post night-by-night logs."),
                _("Trust consistency over confidence or volume."),
                _("In this scenario, Seer is unique so one claimant must be false."),
            ],
        )
        if not await self._tutorial_wait_continue(ctx):
            return False

        claim_options = [
            _("Request exact logs and lock contradictions publicly."),
            _("Trust the louder claimant."),
            _("Ignore claims and vote by vibe."),
        ]
        claim_choice = await self._tutorial_choose_option(
            ctx,
            track="generic",
            title=_("Day 1 - Claim Challenge"),
            prompt=_("How do you resolve this claim/counter-claim?"),
            options=claim_options,
        )
        if claim_choice is None:
            return False

        day_options = [
            _("Lock one vote target and tie it to checked/proven information."),
            _("Hedge language and softly push without committing."),
            _("Ignore claim resolution and follow majority pressure."),
        ]
        day_choice = await self._tutorial_choose_option(
            ctx,
            track="generic",
            title=_("Day 1 - Vote Plan"),
            prompt=_("After the claim duel, how do you convert information into a vote?"),
            options=day_options,
        )
        if day_choice is None:
            return False

        if (
            inspect_choice == 0
            and discussion_choice == 0
            and claim_choice == 0
            and day_choice == 0
        ):
            self._tutorial_mark_dead(roster, "Ivy (Bot)")
            outcome = _(
                "Village voted out **Ivy**. Clean info-to-vote conversion is the"
                " strongest day play."
            )
        elif day_choice == 2 or discussion_choice == 2 or claim_choice == 2:
            self._tutorial_mark_dead(roster, "Luna (Bot)")
            outcome = _(
                "Village misvoted **Luna**. You had useful info but did not convert it"
                " into team action."
            )
        else:
            self._tutorial_mark_dead(roster, "Noah (Bot)")
            outcome = _(
                "Village voted out **Noah** after an unclear discussion. Structure and"
                " timing matter as much as information."
            )
        review_lines = [
            self._tutorial_review_line(
                label=_("Night check"),
                is_good=inspect_choice == 0,
                detail=inspect_options[inspect_choice],
            ),
            self._tutorial_review_line(
                label=_("Discussion control"),
                is_good=discussion_choice == 0,
                detail=discussion_options[discussion_choice],
            ),
            self._tutorial_review_line(
                label=_("Claim resolution"),
                is_good=claim_choice == 0,
                detail=claim_options[claim_choice],
            ),
            self._tutorial_review_line(
                label=_("Vote conversion"),
                is_good=day_choice == 0,
                detail=day_options[day_choice],
            ),
        ]
        outcome = (
            outcome
            + _("\n\nDecision Review:\n")
            + "\n".join(review_lines)
        )

        await self._tutorial_send_state_embed(
            ctx,
            track="generic",
            phase=_("Outcome"),
            objective=_("Repeat this pattern every day: information -> claim -> vote."),
            summary=outcome,
            roster=roster,
        )
        return True

    async def _run_tutorial_sim_village(self, ctx) -> bool:
        you_name = str(ctx.author.display_name)
        roster: list[dict[str, object]] = [
            {"name": you_name, "role": "Doctor", "alive": True},
            {"name": "Mira (Bot)", "role": "Seer", "alive": True},
            {"name": "Cole (Bot)", "role": "Villager", "alive": True},
            {"name": "Nyx (Bot)", "role": "Werewolf", "alive": True},
            {"name": "Tara (Bot)", "role": "Villager", "alive": True},
        ]
        await self._tutorial_send_state_embed(
            ctx,
            track="village",
            phase=_("Setup"),
            objective=_("Keep information roles alive long enough to direct votes."),
            summary=_(
                "You are the Doctor. Seer survival usually decides early village"
                " momentum."
            ),
            roster=roster,
        )
        if not await self._tutorial_wait_continue(ctx):
            return False

        protect_options = [
            _("Mira (Seer)."),
            _("Cole (Villager)."),
            _("Yourself (Doctor)."),
        ]
        protect_choice = await self._tutorial_choose_option(
            ctx,
            track="village",
            title=_("Night 1 - Doctor Protection"),
            prompt=_("Who do you protect?"),
            options=protect_options,
        )
        if protect_choice is None:
            return False

        seer_survived = protect_choice == 0
        if seer_survived:
            night_summary = _(
                "Werewolves attacked **Mira**, but your protection blocked it.\nMira"
                " checked **Nyx** and got a wolf result."
            )
        else:
            self._tutorial_mark_dead(roster, "Mira (Bot)")
            night_summary = _(
                "Werewolves killed **Mira**. Village lost its strongest early"
                " information source."
            )

        await self._tutorial_send_state_embed(
            ctx,
            track="village",
            phase=_("Night 1 Recap"),
            objective=_(
                "Use protection to preserve high-impact roles, then convert info into a"
                " vote."
            ),
            summary=night_summary,
            roster=roster,
        )
        if not await self._tutorial_wait_continue(ctx):
            return False

        if seer_survived:
            village_transcript = [
                _("Mira (Bot): Seer claim. Nyx is wolf from my night check."),
                _("Nyx (Bot): That's fake. Mira is making this up."),
                _("Cole (Bot): We need claim timing and a clean vote path."),
                _("Tara (Bot): Splitting votes here helps wolves."),
            ]
            village_prompt = _("How do you guide this discussion as Doctor?")
            village_options = [
                _("Ask for claim timeline, then unify vote on Nyx."),
                _("Push a side wagon based on tone."),
                _("Avoid structure and hope consensus appears."),
            ]
        else:
            village_transcript = [
                _("Cole (Bot): Seer died. We need to read the wolf kill."),
                _("Nyx (Bot): Anyone can guess now. Skip risky pushes."),
                _("Tara (Bot): Pressure people with incentive to kill Seer."),
                _("Narrator: The table needs structure tied to night-kill value."),
            ]
            village_prompt = _("How do you rebuild structure without Seer alive?")
            village_options = [
                _("Use kill-value logic and focus pressure on Nyx."),
                _("Pick a random target to move fast."),
                _("Refuse to vote so you cannot be blamed."),
            ]

        await self._tutorial_send_discussion_embed(
            ctx,
            track="village",
            scene=_("Day 1 Discussion"),
            transcript_lines=village_transcript,
            important_lines=[
                _("Protect information roles and convert their info immediately."),
                _("When no informer is alive, use night-kill value as evidence."),
                _("Avoid split wagons unless there is a concrete contradiction."),
            ],
        )
        if not await self._tutorial_wait_continue(ctx):
            return False

        discussion_choice = await self._tutorial_choose_option(
            ctx,
            track="village",
            title=_("Day 1 - Discussion Response"),
            prompt=village_prompt,
            options=village_options,
        )
        if discussion_choice is None:
            return False

        if seer_survived:
            claim_lines = [
                _("Mira (Bot): Seer claim. N1 result -> Nyx is wolf."),
                _("Nyx (Bot): Counter-claim Seer. N1 result -> Tara is wolf."),
                _("Cole (Bot): Post exact night target/results and timing."),
            ]
            proof_lines = [
                _("Mira (Bot): Keeps same N1 result line under pressure."),
                _("Nyx (Bot): Result changed after being accused."),
                _("Tara (Bot): Nyx named me only after Mira claimed."),
            ]
        else:
            claim_lines = [
                _("Nyx (Bot): I'm Doctor, I protected Mira last night."),
                _("Counter-claim: Doctor claim says Nyx statement is false."),
                _("Cole (Bot): Unique role conflict. One of you is lying."),
            ]
            proof_lines = [
                _("Counter-claim: N1 protection line is consistent with recap timing."),
                _("Night recap: Mira died, so Nyx's 'saved Mira' line fails."),
                _("Nyx (Bot): No stable night log when questioned."),
            ]

        await self._tutorial_send_claim_embed(
            ctx,
            track="village",
            scene=_("Day 1 Claim Duel"),
            claim_lines=claim_lines,
            proof_lines=proof_lines,
            important_lines=[
                _("Request exact night logs from both claimants."),
                _("Check if claims fit recap facts and role uniqueness."),
                _("Resolve claim board before locking vote."),
            ],
        )
        if not await self._tutorial_wait_continue(ctx):
            return False

        claim_options = [
            _("Demand logs, test consistency, then anchor one wagon."),
            _("Follow whoever sounds more confident."),
            _("Skip claim checks and vote by tone."),
        ]
        claim_choice = await self._tutorial_choose_option(
            ctx,
            track="village",
            title=_("Day 1 - Claim Challenge"),
            prompt=_("How do you handle this claim conflict?"),
            options=claim_options,
        )
        if claim_choice is None:
            return False

        if seer_survived:
            vote_options = [
                _("Vote Nyx with a clear explanation."),
                _("Split vote on Cole due to tone."),
                _("Delay and avoid commitment."),
            ]
            vote_choice = await self._tutorial_choose_option(
                ctx,
                track="village",
                title=_("Day 1 - Village Vote"),
                prompt=_("Mira publicly claims Seer and reports Nyx as wolf. Your move?"),
                options=vote_options,
            )
            if vote_choice is None:
                return False
            if vote_choice == 0 and discussion_choice == 0 and claim_choice == 0:
                self._tutorial_mark_dead(roster, "Nyx (Bot)")
                outcome = _(
                    "Village executed **Nyx**. Protecting Seer and trusting structured"
                    " info converted directly into progress."
                )
            elif vote_choice == 0:
                self._tutorial_mark_dead(roster, "Nyx (Bot)")
                outcome = _(
                    "Village still executed **Nyx**, but discussion was messy."
                    " Structured claim handling would make this line more reliable."
                )
            else:
                self._tutorial_mark_dead(roster, "Cole (Bot)")
                outcome = _(
                    "Village misvoted **Cole**. Even with strong info available,"
                    " undisciplined voting throws away advantages."
                )
        else:
            vote_options = [
                _("Pressure Nyx based on push pattern and kill value."),
                _("Vote Tara at random."),
                _("No vote to avoid responsibility."),
            ]
            vote_choice = await self._tutorial_choose_option(
                ctx,
                track="village",
                title=_("Day 1 - Recovery Vote"),
                prompt=_(
                    "With Seer dead, you must recover using behavior and night logic."
                ),
                options=vote_options,
            )
            if vote_choice is None:
                return False
            if vote_choice == 0 and discussion_choice == 0 and claim_choice == 0:
                self._tutorial_mark_dead(roster, "Nyx (Bot)")
                outcome = _(
                    "Village recovered and executed **Nyx**, but this was harder than"
                    " preserving Seer in the first place."
                )
            elif vote_choice == 0:
                self._tutorial_mark_dead(roster, "Nyx (Bot)")
                outcome = _(
                    "Village executed **Nyx**, but the table stayed fragmented."
                    " Stronger structure reduces future misvote risk."
                )
            elif vote_choice == 1:
                self._tutorial_mark_dead(roster, "Tara (Bot)")
                outcome = _(
                    "Village misvoted **Tara**. Random voting after losing Seer usually"
                    " snowballs into defeat."
                )
            else:
                outcome = _(
                    "No elimination happened. Wolves benefit when village delays"
                    " decisions."
                )
        review_lines = [
            self._tutorial_review_line(
                label=_("Protection target"),
                is_good=protect_choice == 0,
                detail=protect_options[protect_choice],
            ),
            self._tutorial_review_line(
                label=_("Discussion control"),
                is_good=discussion_choice == 0,
                detail=village_options[discussion_choice],
            ),
            self._tutorial_review_line(
                label=_("Claim resolution"),
                is_good=claim_choice == 0,
                detail=claim_options[claim_choice],
            ),
            self._tutorial_review_line(
                label=_("Vote execution"),
                is_good=vote_choice == 0,
                detail=vote_options[vote_choice],
            ),
        ]
        outcome = (
            outcome
            + _("\n\nDecision Review:\n")
            + "\n".join(review_lines)
        )

        await self._tutorial_send_state_embed(
            ctx,
            track="village",
            phase=_("Outcome"),
            objective=_(
                "Doctor value is not just saving lives, it is preserving information"
                " economy."
            ),
            summary=outcome,
            roster=roster,
        )
        return True

    async def _run_tutorial_sim_werewolf(self, ctx) -> bool:
        you_name = str(ctx.author.display_name)
        roster: list[dict[str, object]] = [
            {"name": you_name, "role": "Werewolf", "alive": True},
            {"name": "Fang (Bot)", "role": "Werewolf", "alive": True},
            {"name": "Iris (Bot)", "role": "Seer", "alive": True},
            {"name": "Theo (Bot)", "role": "Doctor", "alive": True},
            {"name": "Mila (Bot)", "role": "Villager", "alive": True},
        ]
        await self._tutorial_send_state_embed(
            ctx,
            track="werewolf",
            phase=_("Setup"),
            objective=_("Reach parity by controlling both night kills and day narrative."),
            summary=_(
                "You and Fang are wolves. Your team wins by removing village control."
            ),
            roster=roster,
        )
        if not await self._tutorial_wait_continue(ctx):
            return False

        kill_options = [
            _("Iris (Seer)."),
            _("Theo (Doctor)."),
            _("Mila (Villager)."),
        ]
        kill_choice = await self._tutorial_choose_option(
            ctx,
            track="werewolf",
            title=_("Night 1 - Wolf Kill"),
            prompt=_("Who should be the first kill?"),
            options=kill_options,
        )
        if kill_choice is None:
            return False

        if kill_choice == 0:
            self._tutorial_mark_dead(roster, "Iris (Bot)")
            night_summary = _(
                "You removed **Iris (Seer)**. Village lost high-value information."
            )
        elif kill_choice == 1:
            self._tutorial_mark_dead(roster, "Theo (Bot)")
            night_summary = _(
                "You removed **Theo (Doctor)**. Useful, but Seer is still active."
            )
        else:
            self._tutorial_mark_dead(roster, "Mila (Bot)")
            night_summary = _(
                "You removed **Mila (Villager)**. Low-value kill; village utility is"
                " mostly intact."
            )

        await self._tutorial_send_state_embed(
            ctx,
            track="werewolf",
            phase=_("Night 1 Recap"),
            objective=_("Prioritize kills that reduce village coordination power."),
            summary=night_summary,
            roster=roster,
        )
        if not await self._tutorial_wait_continue(ctx):
            return False

        await self._tutorial_send_discussion_embed(
            ctx,
            track="werewolf",
            scene=_("Day 1 Discussion"),
            transcript_lines=[
                _("Mila (Bot): Last night kill suggests wolves fear information roles."),
                _("Theo (Bot): We need claim consistency before deciding this vote."),
                _("Fang (Bot): I'm not convinced. Could be a fake narrative."),
                _("Narrator: The wolf side needs one coherent wagon story."),
            ],
            important_lines=[
                _("Push one coherent story instead of random chaos."),
                _("Do not hard-pocket your wolf partner under hard pressure."),
                _("Drive village toward a plausible villager elimination."),
            ],
        )
        if not await self._tutorial_wait_continue(ctx):
            return False

        discussion_options = [
            _("Build a consistent case with timeline and contradictions."),
            _("Spray multiple conflicting accusations."),
            _("Tunnel on defending Fang at all costs."),
        ]
        discussion_choice = await self._tutorial_choose_option(
            ctx,
            track="werewolf",
            title=_("Day 1 - Discussion Response"),
            prompt=_("How do you shape day chat as a wolf?"),
            options=discussion_options,
        )
        if discussion_choice is None:
            return False

        if kill_choice == 1:
            claim_lines = [
                _("Mila (Bot): Seer claim. N1 result -> Fang looks wolfy."),
                _("Fang (Bot): Counter-claim Seer. Mila is fake."),
                _("Narrator: Table asks both claimants for exact N1 logs."),
            ]
            proof_lines = [
                _("Mila (Bot): Gives one consistent target/result timeline."),
                _("Fang (Bot): Adds details only after Mila posts hers."),
                _("Table note: Late-edited logs look manufactured."),
            ]
        else:
            claim_lines = [
                _("Theo (Bot): Doctor claim. N1 protect was on Mila."),
                _("Fang (Bot): Counter-claim Doctor. Theo is fake."),
                _("Narrator: Table requests both protection logs with timing."),
            ]
            proof_lines = [
                _("Theo (Bot): Maintains the same N1 protection line."),
                _("Fang (Bot): Protection story shifts when challenged."),
                _("Table note: Unique-role conflict means one claim must break."),
            ]

        await self._tutorial_send_claim_embed(
            ctx,
            track="werewolf",
            scene=_("Day 1 Claim Duel"),
            claim_lines=claim_lines,
            proof_lines=proof_lines,
            important_lines=[
                _("As wolf, push the weaker proof line, not random noise."),
                _("Keep Fang's story stable; contradictions expose the pack."),
                _("Use claim chaos only if you can still control final wagon."),
            ],
        )
        if not await self._tutorial_wait_continue(ctx):
            return False

        claim_options = [
            _("Push the weaker proof line with one consistent narrative."),
            _("Flip stories repeatedly and flood chat."),
            _("Force Fang into overcommitting impossible details."),
        ]
        claim_choice = await self._tutorial_choose_option(
            ctx,
            track="werewolf",
            title=_("Day 1 - Claim Manipulation"),
            prompt=_("How do you exploit the claim duel as a wolf?"),
            options=claim_options,
        )
        if claim_choice is None:
            return False

        day_options = [
            _("Push one coherent case with consistent story."),
            _("Create chaos and contradict yourself often."),
            _("Hard-defend Fang even under strong evidence."),
        ]
        day_choice = await self._tutorial_choose_option(
            ctx,
            track="werewolf",
            title=_("Day 1 - Public Play"),
            prompt=_("How do you handle discussion?"),
            options=day_options,
        )
        if day_choice is None:
            return False

        if day_choice == 0 and discussion_choice == 0 and claim_choice == 0 and kill_choice == 0:
            target = "Theo (Bot)" if any(
                entry["name"] == "Theo (Bot)" and bool(entry["alive"]) for entry in roster
            ) else "Mila (Bot)"
            self._tutorial_mark_dead(roster, target)
            outcome = _(
                "Village executed **{target}** after your coordinated push. This is the"
                " strongest wolf line: high-value night kill plus coherent day"
                " pressure."
            ).format(target=target.split(" ")[0])
        elif day_choice == 0 and discussion_choice == 0 and claim_choice == 0:
            target = "Mila (Bot)"
            self._tutorial_mark_dead(roster, target)
            outcome = _(
                "You converted the day cleanly and village executed **Mila**. Good day"
                " control, but night kill priority can still improve."
            )
        else:
            self._tutorial_mark_dead(roster, "Fang (Bot)")
            if day_choice == 0 and claim_choice != 0:
                outcome = _(
                    "Your claim handling collapsed under scrutiny. Fang's contradictions"
                    " were exposed and village executed **Fang**."
                )
            elif day_choice == 0 and discussion_choice != 0:
                outcome = _(
                    "Your vote direction was fine, but earlier discussion looked"
                    " inconsistent. Village linked wolves and executed **Fang**."
                )
            elif day_choice == 0:
                outcome = _(
                    "Your day case was structured, but village information remained too"
                    " strong. **Fang** was executed."
                )
            elif day_choice == 1:
                outcome = _(
                    "Chaos backfired. Contradictions exposed wolf links and **Fang** was"
                    " executed."
                )
            else:
                outcome = _(
                    "Over-defending partner forced associations. Village executed"
                    " **Fang**."
                )
        review_lines = [
            self._tutorial_review_line(
                label=_("Night kill priority"),
                is_good=kill_choice == 0,
                detail=kill_options[kill_choice],
            ),
            self._tutorial_review_line(
                label=_("Discussion shaping"),
                is_good=discussion_choice == 0,
                detail=discussion_options[discussion_choice],
            ),
            self._tutorial_review_line(
                label=_("Claim manipulation"),
                is_good=claim_choice == 0,
                detail=claim_options[claim_choice],
            ),
            self._tutorial_review_line(
                label=_("Public vote line"),
                is_good=day_choice == 0,
                detail=day_options[day_choice],
            ),
        ]
        outcome = (
            outcome
            + _("\n\nDecision Review:\n")
            + "\n".join(review_lines)
        )

        await self._tutorial_send_state_embed(
            ctx,
            track="werewolf",
            phase=_("Outcome"),
            objective=_("Night priority + day coherence wins more than random chaos."),
            summary=outcome,
            roster=roster,
        )
        return True

    async def _run_tutorial_sim_solo(self, ctx) -> bool:
        you_name = str(ctx.author.display_name)
        roster: list[dict[str, object]] = [
            {"name": you_name, "role": "Head Hunter", "alive": True},
            {"name": "Aria (Bot)", "role": "Villager (Target)", "alive": True},
            {"name": "Sven (Bot)", "role": "Werewolf", "alive": True},
            {"name": "Mira (Bot)", "role": "Seer", "alive": True},
            {"name": "Kade (Bot)", "role": "Doctor", "alive": True},
        ]
        await self._tutorial_send_state_embed(
            ctx,
            track="solo",
            phase=_("Setup"),
            objective=_("Get your target lynched while staying difficult to classify."),
            summary=_(
                "You are solo. Your objective is not village win or wolf win; it is"
                " getting **Aria** eliminated by vote."
            ),
            roster=roster,
        )
        if not await self._tutorial_wait_continue(ctx):
            return False

        await self._tutorial_send_discussion_embed(
            ctx,
            track="solo",
            scene=_("Day 1 Discussion"),
            transcript_lines=[
                _("Mira (Bot): We should coordinate around claim consistency."),
                _("Sven (Bot): Fast votes are risky without hard evidence."),
                _("Aria (Bot): Anyone pushing me right now is forcing it."),
                _("Kade (Bot): We need pressure, but not obvious agenda pushes."),
            ],
            important_lines=[
                _("Advance your objective without looking tunnel-visioned."),
                _("Use verifiable contradictions, not naked accusations."),
                _("Preserve flexibility so both major teams tolerate you."),
            ],
        )
        if not await self._tutorial_wait_continue(ctx):
            return False

        discussion_options = [
            _("Ask targeted questions and build pressure slowly on Aria."),
            _("Hard tunnel Aria with no evidence."),
            _("Avoid taking any stance to stay invisible."),
        ]
        discussion_choice = await self._tutorial_choose_option(
            ctx,
            track="solo",
            title=_("Day 1 - Discussion Response"),
            prompt=_("How do you talk while hiding your solo objective?"),
            options=discussion_options,
        )
        if discussion_choice is None:
            return False

        await self._tutorial_send_claim_embed(
            ctx,
            track="solo",
            scene=_("Day 1 Claim Duel"),
            claim_lines=[
                _("Aria (Bot): Sheriff claim. Sven checked as Village."),
                _("Sven (Bot): Counter-claim Sheriff. Aria is fake."),
                _("Mira (Bot): Both must post exact target/result logs."),
            ],
            proof_lines=[
                _("Aria (Bot): Cannot keep one stable N1 timeline."),
                _("Sven (Bot): Provides a complete target+result log."),
                _("Kade (Bot): Late-edited logs are usually fake claims."),
            ],
            important_lines=[
                _("As solo, use claim tension without exposing your objective."),
                _("Ask precise questions so others draw the conclusion."),
                _("Do not over-own one side too early."),
            ],
        )
        if not await self._tutorial_wait_continue(ctx):
            return False

        claim_options = [
            _("Ask proof-focused questions and subtly isolate Aria."),
            _("Hard tunnel Aria as fake immediately."),
            _("Ignore claim conflict and stay fully neutral."),
        ]
        claim_choice = await self._tutorial_choose_option(
            ctx,
            track="solo",
            title=_("Day 1 - Claim Pressure"),
            prompt=_("How do you use this claim duel?"),
            options=claim_options,
        )
        if claim_choice is None:
            return False

        strategy_options = [
            _("Build a measured case with two concrete contradictions."),
            _("Hard accuse immediately with no evidence."),
            _("Stay quiet and avoid influencing the vote."),
        ]
        strategy_choice = await self._tutorial_choose_option(
            ctx,
            track="solo",
            title=_("Day 1 - Positioning"),
            prompt=_("After discussion, what is your strategic posture?"),
            options=strategy_options,
        )
        if strategy_choice is None:
            return False

        if strategy_choice == 0:
            setup_summary = _(
                "Your case is believable. Aria becomes a viable vote candidate."
            )
        elif strategy_choice == 1:
            setup_summary = _(
                "You look agenda-driven. Players distrust your push on Aria."
            )
        else:
            setup_summary = _(
                "You stayed off radar, but Aria gained no meaningful pressure."
            )

        self._tutorial_mark_dead(roster, "Mira (Bot)")
        await self._tutorial_send_state_embed(
            ctx,
            track="solo",
            phase=_("Night 1 Recap"),
            objective=_("Keep your objective alive while major teams fight each other."),
            summary=_(
                "{setup}\nDuring the night, wolves killed **Mira (Seer)**, increasing"
                " day volatility."
            ).format(setup=setup_summary),
            roster=roster,
        )
        if not await self._tutorial_wait_continue(ctx):
            return False

        final_options = [
            _("Commit to a clear, evidence-based lynch on Aria."),
            _("Pivot to Kade because it seems easier."),
            _("Panic and follow whichever wagon is largest."),
        ]
        final_choice = await self._tutorial_choose_option(
            ctx,
            track="solo",
            title=_("Day 2 - Commit or Pivot"),
            prompt=_("What is your final decision?"),
            options=final_options,
        )
        if final_choice is None:
            return False

        if (
            discussion_choice == 0
            and claim_choice == 0
            and strategy_choice == 0
            and final_choice == 0
        ):
            self._tutorial_mark_dead(roster, "Aria (Bot)")
            outcome = _(
                "Target achieved. **Aria** was lynched and your solo objective was met."
            )
        elif strategy_choice == 0 and final_choice == 0:
            self._tutorial_mark_dead(roster, "Aria (Bot)")
            outcome = _(
                "Target achieved, but your day chat was too transparent. In tougher"
                " lobbies this would attract immediate suspicion."
            )
        elif final_choice == 1:
            self._tutorial_mark_dead(roster, "Kade (Bot)")
            outcome = _(
                "Kade was lynched, not your target. Solo roles lose when they abandon"
                " objective for short-term safety."
            )
        else:
            outcome = _(
                "Vote became unstable and your target survived. Solo play requires"
                " objective discipline."
            )
        review_lines = [
            self._tutorial_review_line(
                label=_("Discussion posture"),
                is_good=discussion_choice == 0,
                detail=discussion_options[discussion_choice],
            ),
            self._tutorial_review_line(
                label=_("Claim pressure use"),
                is_good=claim_choice == 0,
                detail=claim_options[claim_choice],
            ),
            self._tutorial_review_line(
                label=_("Positioning"),
                is_good=strategy_choice == 0,
                detail=strategy_options[strategy_choice],
            ),
            self._tutorial_review_line(
                label=_("Final commitment"),
                is_good=final_choice == 0,
                detail=final_options[final_choice],
            ),
        ]
        outcome = (
            outcome
            + _("\n\nDecision Review:\n")
            + "\n".join(review_lines)
        )

        await self._tutorial_send_state_embed(
            ctx,
            track="solo",
            phase=_("Outcome"),
            objective=_("As solo, every choice should be judged against your true win path."),
            summary=outcome,
            roster=roster,
        )
        return True

    async def _run_tutorial_sim(self, ctx, *, track: str) -> None:
        if self.games.get(ctx.channel.id):
            await ctx.send(
                _(
                    "Finish the current NewWerewolf game in this channel before"
                    " starting a tutorial match."
                )
            )
            return

        existing_owner_id = self.tutorial_sessions.get(ctx.channel.id)
        if existing_owner_id is not None and existing_owner_id != ctx.author.id:
            await ctx.send(
                _(
                    "A tutorial session is already running in this channel. Please wait"
                    " until it finishes."
                )
            )
            return
        if existing_owner_id == ctx.author.id:
            await ctx.send(_("You already have a tutorial running in this channel."))
            return

        self.tutorial_sessions[ctx.channel.id] = ctx.author.id
        try:
            await ctx.send(
                _(
                    "Starting **{track}** tutorial match.\n"
                    "This uses the real NewWerewolf night/day game loop with bot"
                    " players.\n"
                    "Night actions are sent by DM, while nomination/voting are handled"
                    " publicly in-channel like normal matches."
                ).format(track=track.title())
            )

            async def run_tutorial_game(*, tutorial_variant: str | None = None) -> None:
                game = TutorialGame(
                    ctx,
                    track=track,
                    learner=ctx.author,
                    tutorial_variant=tutorial_variant,
                )
                self.games[ctx.channel.id] = game
                await game.run()

            await run_tutorial_game()

            if track == "village":
                await ctx.send(
                    _(
                        "Tutorial Coach: We'll try another village round where you are"
                        " **Seer**. Check the Werewolf at night, then call them out in"
                        " public chat."
                    )
                )
                await run_tutorial_game(tutorial_variant=TUTORIAL_VARIANT_VILLAGE_SEER)
            elif track == "werewolf":
                await ctx.send(
                    _(
                        "Tutorial Coach: We'll run another werewolf round focused on day"
                        " manipulation. You kill Seer at night and push one suspect"
                        " publicly."
                    )
                )
                await run_tutorial_game(tutorial_variant=TUTORIAL_VARIANT_WEREWOLF_GUIDED)
            elif track == "solo":
                await ctx.send(
                    _(
                        "Tutorial Coach: We'll run a second solo round as **Jester**."
                        " You must bait the village into lynching you."
                    )
                )
                await run_tutorial_game(tutorial_variant=TUTORIAL_VARIANT_SOLO_JESTER)

            await self._update_tutorial_completion_and_badge(ctx, track=track)
        except Exception as e:
            await send_traceback(ctx, e)
            raise
        finally:
            if self.games.get(ctx.channel.id) is not None:
                del self.games[ctx.channel.id]
            if self.tutorial_sessions.get(ctx.channel.id) == ctx.author.id:
                del self.tutorial_sessions[ctx.channel.id]
            self.tutorial_progress.pop(ctx.channel.id, None)

        await ctx.send(
            _(
                "Tutorial match ended. Use `{prefix}nww tutorial {track} text` for"
                " the static guide pages."
            ).format(prefix=ctx.clean_prefix, track=track)
        )

    async def _start_multiplayer_game(
        self,
        ctx,
        *,
        mode: str,
        speed: str,
        min_players: int,
        custom_roles: list[ROLES] | None = None,
    ) -> None:
        if self.games.get(ctx.channel.id):
            await ctx.send(_("There is already a game in here!"))
            return

        game_speeds = ["Normal", "Extended", "Fast", "Blitz"]
        if speed not in game_speeds:
            await ctx.send(
                _(
                    "Invalid game speed. Use `{prefix}help nww` to get help on this"
                    " command."
                ).format(prefix=ctx.clean_prefix)
            )
            return

        try:
            await self._ensure_role_xp_tables()
        except Exception:
            # Progression DB failures should not block playing the game.
            pass

        self.games[ctx.channel.id] = "forming"

        additional_text = _(
            "Use `{prefix}help nww` to get help on werewolf commands. Use `{prefix}nww"
            " roles` to view descriptions of game roles and their goals to win. Use"
            " `{prefix}nww modes` and `{prefix}nww speeds` to see info about available"
            " game modes and speeds."
        ).format(prefix=ctx.clean_prefix)

        mode_emojis = {"Huntergame": "🔫", "Valentines": "💕", "Custom": "🧩"}
        mode_emoji = mode_emojis.get(mode, "")
        mode_label = mode_emoji + mode + mode_emoji

        if (
            self.bot.config.game.official_tournament_channel_id
            and ctx.channel.id == self.bot.config.game.official_tournament_channel_id
        ):
            view = JoinView(
                Button(style=ButtonStyle.primary, label=_("Join the Werewolf game!")),
                message=_("You joined the Werewolf game."),
                timeout=60 * 10,
            )
            text = _(
                "**{author} started a mass-game of Werewolf!**\n**{mode}** mode on"
                " **{speed}** speed. You can join in the next 10 minutes."
                " **Minimum of {min_players} players are required.**"
            )

            await ctx.send(
                embed=discord.Embed(
                    title=_("Werewolf Mass-game!"),
                    description=text.format(
                        author=ctx.author.mention,
                        mode=mode_label,
                        speed=speed,
                        min_players=min_players,
                    ),
                    colour=self.bot.config.game.primary_colour,
                )
                .set_author(
                    name=str(ctx.author), icon_url=ctx.author.display_avatar.url
                )
                .add_field(name=_("New to Werewolf?"), value=additional_text),
                view=view,
            )

            await asyncio.sleep(60)
            view.stop()
            players = list(view.joined)
        else:
            view = JoinView(
                Button(style=ButtonStyle.primary, label=_("Join the Werewolf game!")),
                message=_("You joined the Werewolf game."),
                timeout=120,
            )
            view.joined.add(ctx.author)
            title = _("Werewolf game!")
            text = _(
                "**{author} started a game of Werewolf!**\n**{mode}** mode on"
                " **{speed}** speed. Minimum of"
                " **{min_players}** players are required. Starting in 2 minutes."
            )

            try:
                await ctx.send(
                    embed=discord.Embed(
                        title=title,
                        description=text.format(
                            author=ctx.author.mention,
                            mode=mode_label,
                            speed=speed,
                            min_players=min_players,
                        ),
                        colour=self.bot.config.game.primary_colour,
                    )
                    .set_author(
                        name=str(ctx.author), icon_url=ctx.author.display_avatar.url
                    )
                    .add_field(name=_("New to Werewolf?"), value=additional_text),
                    view=view,
                )
            except discord.errors.Forbidden:
                del self.games[ctx.channel.id]
                await ctx.send(
                    _(
                        "An error happened during the Werewolf. Missing Permission:"
                        " `Embed Links` . Please check the **Edit Channel >"
                        " Permissions** and **Server Settings > Roles** then try again!"
                    )
                )
                return

            await asyncio.sleep(60 * 2)
            view.stop()
            players = list(view.joined)

        if len(players) < min_players:
            del self.games[ctx.channel.id]
            await self.bot.reset_cooldown(ctx)
            await ctx.send(
                _(
                    "Not enough players joined... We didn't reach the minimum"
                    " {min_players} players. 🙁"
                ).format(min_players=min_players)
            )
            return

        if custom_roles is not None:
            max_roles = len(players) + 2
            if len(custom_roles) > max_roles:
                del self.games[ctx.channel.id]
                await self.bot.reset_cooldown(ctx)
                await ctx.send(
                    _(
                        "You specified **{specified}** roles, but this game can only use"
                        " up to **{max_roles}** roles with **{players}** players."
                    ).format(
                        specified=len(custom_roles),
                        max_roles=max_roles,
                        players=len(players),
                    )
                )
                return

        role_xp_eligible = await self._is_role_xp_eligible_match(ctx)
        players = random.shuffle(players)
        try:
            game = Game(ctx, players, mode, speed, custom_roles=custom_roles)
            self.games[ctx.channel.id] = game
            await game.run()
            await self._award_role_xp(game, eligible=role_xp_eligible)
        except Exception as e:
            await send_traceback(ctx, e)
            del self.games[ctx.channel.id]
            raise

        try:
            del self.games[ctx.channel.id]
        except KeyError:  # got stuck in between
            pass

    @commands.group(
        invoke_without_command=True,
        case_insensitive=True,
        aliases=["nww"],
        brief=_("Starts a game of NewWerewolf"),
    )
    @locale_doc
    async def newwerewolf(
        self,
        ctx,
        mode: str | None = "Classic",
        speed: str = "Normal",
        min_players: IntGreaterThan(1) = None,
    ):
        _(
            """
            `[mode]` - The mode to play, see below for available options. (optional and defaults to Classic)
            `[speed]` - The game speed to play, see below available options. (optional and defaults to Normal)
            `[min_players]` - The minimum players needed to play. (optional and defaults depending on the game mode: Classic: 5, Imbalanced: 5, Huntergame: 8, Villagergame: 5, Valentines: 8, IdleRPG: 5)

            Starts a game of NewWerewolf. Find the werewolves, before they find you!
            Your goal to win is indicated on the role you have.
            **Game modes:** `Classic` (default), `Imbalanced`, `Huntergame`, `Villagergame`, `Valentines`, `IdleRPG`. Use `{prefix}nww modes` for detailed info.
            **Game speeds** (in seconds): `Normal`: 60 (default), `Extended`: 90, `Fast`: 45, `Blitz`: 30. Use `{prefix}nww speeds` for detailed info.
            **Aliases:**
            `nww`
            **Examples:**
            `{prefix}nww Blitz` for Classic mode on Blitz speed
            `{prefix}nww Imbalanced` for Imbalanced mode on Normal speed
            `{prefix}nww Valentines Extended` for Valentines mode on Extended speed
            `{prefix}nww Huntergame Fast` for Huntergame mode on Fast speed
            """
        )
        # TODO:
        # Bizarro: Roles are flipped.
        # Random: Roles are reassigned randomly every night.
        # Zombie (Classic-based, another team) - There's a chance that a random player will be randomly resurrected as Zombie and they can devour any villagers or werewolves with the other zombies.

        game_modes = [
            "Classic",
            "Imbalanced",
            "Huntergame",
            "Villagergame",
            "Valentines",
            "Idlerpg",
        ]
        game_speeds = ["Normal", "Extended", "Fast", "Blitz"]
        minimum_players = {
            "Classic": 5,
            "Imbalanced": 5,
            "Huntergame": 8,
            "Villagergame": 5,
            "Valentines": 8,
            "IdleRPG": 5,
        }

        mode_token = str(mode or "Classic").strip().title()
        speed_token = str(speed or "Normal").strip().title()

        # Support shorthand like `nww Blitz` and keep roster behavior tied to mode.
        # Blitz/Fast/Extended/Normal are speeds, not separate role rosters.
        if mode_token in game_speeds:
            inferred_speed = mode_token
            inferred_mode = "Classic"
            if speed_token in game_modes:
                inferred_mode = speed_token
            elif speed_token.isdigit() and min_players is None:
                parsed_min_players = int(speed_token)
                if parsed_min_players <= 1:
                    return await ctx.send(
                        _("Minimum players must be greater than 1.")
                    )
                min_players = parsed_min_players
            mode_token = inferred_mode
            speed_token = inferred_speed

        if mode_token not in game_modes:
            return await ctx.send(
                _(
                    "Invalid game mode. Use `{prefix}help nww` to get help on this"
                    " command."
                ).format(prefix=ctx.clean_prefix)
            )
        if mode_token == "Idlerpg":
            mode_token = "IdleRPG"

        if not min_players:
            min_players = minimum_players.get(mode_token, 5)

        await self._start_multiplayer_game(
            ctx,
            mode=mode_token,
            speed=speed_token,
            min_players=min_players,
        )

    @newwerewolf.command(
        name="custom",
        aliases=["cstm"],
        brief=_("Starts a custom-role multiplayer Werewolf game"),
    )
    @locale_doc
    async def newwerewolf_custom(self, ctx, *, roles: str):
        _(
            """Start a custom-role Werewolf game.

            Usage example:
            `{prefix}nww custom witch, werewolf, jester`

            Notes:
            - Separate roles with commas.
            - Repeating a role means it can spawn multiple times.
            - Any unfilled slots are generated with the normal balanced role system.
            - The game always guarantees at least one Werewolf-team role and one Villager-team role."""
        )

        parsed_roles, invalid_tokens = parse_custom_roles(roles)
        if invalid_tokens:
            invalid_display = ", ".join(f"`{token}`" for token in invalid_tokens)
            return await ctx.send(
                _(
                    "I couldn't recognize these roles: {roles}\nUse `{prefix}nww roles`"
                    " to see valid names."
                ).format(roles=invalid_display, prefix=ctx.clean_prefix)
            )

        if not parsed_roles:
            return await ctx.send(
                _(
                    "You need to specify at least one role.\nExample: `{prefix}nww"
                    " custom witch, werewolf, jester`"
                ).format(prefix=ctx.clean_prefix)
            )
        unavailable = unavailable_roles_for_mode(parsed_roles, "Custom")
        if unavailable:
            unique_unavailable: list[ROLES] = []
            seen: set[ROLES] = set()
            for role in unavailable:
                if role in seen:
                    continue
                seen.add(role)
                unique_unavailable.append(role)
            unavailable_display = ", ".join(
                f"`{role.name.replace('_', ' ').title()}`" for role in unique_unavailable
            )
            return await ctx.send(
                _(
                    "These roles are disabled or not allowed in **Custom** mode:"
                    " {roles}\nEdit `cogs/newwerewolf/role_config.py` to change role"
                    " availability."
                ).format(roles=unavailable_display)
            )

        await self._start_multiplayer_game(
            ctx,
            mode="Custom",
            speed="Normal",
            min_players=3,
            custom_roles=parsed_roles,
        )

    @newwerewolf.command(brief=_("See available werewolf game modes"))
    @locale_doc
    async def modes(self, ctx):
        _("""Used to see the list of available werewolf game modes.""")
        return await ctx.send(
            embed=discord.Embed(
                title=_("Werewolf Game Modes"),
                description=_(
                    """\
**Game modes:** `Classic` (default), `Imbalanced`, `Huntergame`, `Villagergame`, `Valentines`, `IdleRPG`, `Custom`.
`Classic`: Play the classic werewolf game. (default)
`Imbalanced`: Some roles that are only available in larger games have chances to join even in smaller games. (The size of the game being referred here is about the number of players, i.e. 5-player game is small)
`Huntergame`: Only Hunters and Werewolves are available.
`Villagergame`: No special roles, only Villagers and Werewolves are available.
`Valentines`: There are multiple lovers or couples randomly chosen at the start of the game. A chain of lovers might exist upon the Amor's arrows. If the remaining players are in a single chain of lovers, they all win.
`IdleRPG`: (based on Imbalanced mode) New roles are available: Paragon, Raider, Lawyer, Troublemaker, War Veteran, Wolf Shaman, Wolf Necromancer, Alpha Werewolf, Guardian Wolf, Superspreader, Red Lady, Priest, Pacifist, Grumpy Grandma, Nightmare Werewolf. (`Ritualist`, `Ghost Lady`, `Marksman`, `Forger`, `Serial Killer`, `Cannibal`, `Wolf Summoner`, `Sorcerer`, and `Voodoo Werewolf` are advanced unlocks.)
`Custom`: Use `{prefix}nww custom <role1, role2, ...>` to seed exact roles (duplicates allowed). Remaining slots are filled with normal balance."""
                ).format(prefix=ctx.clean_prefix),
                colour=self.bot.config.game.primary_colour,
            ).set_author(name=str(ctx.author), icon_url=ctx.author.display_avatar.url)
        )

    @newwerewolf.command(brief=_("See available werewolf game speeds"))
    @locale_doc
    async def speeds(self, ctx):
        _("""Used to see the list of available werewolf game speeds.""")
        return await ctx.send(
            embed=discord.Embed(
                title=_("Werewolf Game Speeds"),
                description=_(
                    """\
**Game speeds** (in seconds): `Normal`: 60 (default), `Extended`: 90, `Fast`: 45, `Blitz`: 30
`Normal`: All major action timers are limited to 60 seconds and number of days to play is unlimited.
`Extended`: All major action timers are limited to 90 seconds and number of days to play is unlimited.
`Fast`: All major action timers are limited to 45 seconds and number of days to play is dependent on the number of players plus 3 days. This means not killing anyone every night or every election will likely end the game with no winners.
`Blitz`: Warning: This is a faster game speed suitable for experienced players. All action timers are limited to 30 seconds and number of days to play is dependent on the number of players plus 3 days. This means not killing anyone every night or every election will likely end the game with no winners.
`Note`: Speed does not change the role roster. `Blitz` uses the same roster as the selected mode (for example, `Classic` roster on `Blitz`)."""
                ),
                colour=self.bot.config.game.primary_colour,
            ).set_author(name=str(ctx.author), icon_url=ctx.author.display_avatar.url)
        )

    @newwerewolf.command(
        name="tutorial",
        aliases=["guide", "learn"],
        brief=_("Interactive learning guides for NewWerewolf"),
    )
    @locale_doc
    async def tutorial(self, ctx, *, track: str = None):
        _(
            """View NewWerewolf tutorials.

            `{prefix}nww tutorial`
            `{prefix}nww tutorial generic`
            `{prefix}nww tutorial generic text`
            `{prefix}nww tutorial village`
            `{prefix}nww tutorial werewolf`
            `{prefix}nww tutorial solo`
            """
        )
        if track is None:
            embed = self._make_tutorial_embed(
                ctx=ctx,
                title=_("NewWerewolf Tutorials"),
                description=_(
                    "Choose a track (interactive by default):\n"
                    "- `generic` - core day/night, voting, and recap reading\n"
                    "- `village` - info/protection priorities and vote discipline\n"
                    "- `werewolf` - kill priority and day narrative control\n"
                    "- `solo` - objective-driven survival and endgame planning\n\n"
                    "**Modes:**\n"
                    "- default/`interactive`/`sim` - play a live tutorial match that"
                    " uses the same NewWerewolf night/day engine with bot players"
                    " (DM night actions + public day nomination/voting)\n"
                    "- `text` - read static guide pages\n\n"
                    "**Examples:**\n"
                    "`{prefix}nww tutorial generic`\n"
                    "`{prefix}nww tutorial village sim`\n"
                    "`{prefix}nww tutorial werewolf text`\n"
                    "`{prefix}nww tutorial solo interactive`\n"
                    "`{prefix}nww tutorial village`\n"
                    "`{prefix}nww tutorial werewolf`\n"
                    "`{prefix}nww tutorial solo`"
                ).format(prefix=ctx.clean_prefix),
            )
            return await ctx.send(embed=embed)

        normalized_tokens = [
            self._tutorial_normalize_token(token)
            for token in str(track).replace(",", " ").split()
            if str(token).strip()
        ]
        mode_tokens = {
            "sim",
            "interactive",
            "play",
            "practice",
            "scenario",
            "text",
            "static",
            "guide",
            "pages",
            "read",
        }
        selected_track, selected_mode = self._parse_tutorial_track_and_mode(track)
        if selected_track is None:
            if normalized_tokens and all(token in mode_tokens for token in normalized_tokens):
                selected_track = "generic"
            else:
                return await ctx.send(
                    _(
                        "Unknown tutorial track: `{track}`.\n"
                        "Use one of: `generic`, `village`, `werewolf`, `solo`."
                    ).format(track=track)
                )

        if selected_mode == "sim":
            return await self._run_tutorial_sim(ctx, track=selected_track)

        if selected_mode != "text":
            return await ctx.send(
                _(
                    "Unknown tutorial mode. Use `interactive`/`sim` or `text`."
                )
            )

        embeds = self._build_tutorial_embeds(ctx=ctx, track=selected_track)
        if not embeds:
            return await ctx.send(_("No tutorial content found for that track."))
        if len(embeds) == 1:
            return await ctx.send(embed=embeds[0])
        return await self.bot.paginator.Paginator(extras=embeds).paginate(ctx)

    @newwerewolf.command(
        name="tutorialstatus",
        aliases=["tutorialprogress", "tutstatus", "tutprogress"],
        brief=_("View NewWerewolf tutorial completion status"),
    )
    @locale_doc
    async def tutorialstatus(self, ctx, user: discord.User = None):
        _(
            """View NewWerewolf tutorial completion status.

            `[user]` - Optional user to inspect, defaults to yourself

            `{prefix}nww tutorialstatus`
            `{prefix}nww tutorialstatus @user`
            """
        )
        target = user or ctx.author
        progress = await self._fetch_tutorial_completion_row(target.id)
        completed_labels = [
            label
            for key, label in self.TUTORIAL_TRACK_LABELS.items()
            if bool(progress.get(self.TUTORIAL_TRACK_COLUMNS[key], False))
        ]
        remaining_labels = [
            label
            for key, label in self.TUTORIAL_TRACK_LABELS.items()
            if not bool(progress.get(self.TUTORIAL_TRACK_COLUMNS[key], False))
        ]
        done_count = len(completed_labels)

        badge_state = await self._user_has_badge(target.id, Badge.JUNIOR_WEREWOLF)
        if bool(progress.get("completed_all")) and badge_state is False:
            badge_outcome = await self._grant_junior_werewolf_badge(target.id)
            if badge_outcome in ("granted", "already"):
                badge_state = True
            elif badge_outcome == "no_profile":
                badge_state = None
        if badge_state is True:
            badge_text = _("Unlocked")
        elif badge_state is False:
            badge_text = _("Not unlocked")
        else:
            badge_text = _("Unavailable (no profile or database)")

        embed = discord.Embed(
            title=_("NewWerewolf Tutorial Status"),
            colour=self.bot.config.game.primary_colour,
            description=_("Progress for {user}: **{done}/3** tracks completed.").format(
                user=target.mention,
                done=done_count,
            ),
        )
        embed.add_field(
            name=_("Completed"),
            value=", ".join(completed_labels) if completed_labels else _("None"),
            inline=False,
        )
        embed.add_field(
            name=_("Remaining"),
            value=", ".join(remaining_labels) if remaining_labels else _("None"),
            inline=False,
        )
        embed.add_field(
            name=_("Junior Werewolf Badge"),
            value=badge_text,
            inline=False,
        )
        return await ctx.send(embed=embed)

    @newwerewolf.command(
        name="tutorialgraduates",
        aliases=["tutorialgrads", "tutgrads", "tutorialcomplete"],
        brief=_("List users who completed all 3 NewWerewolf tutorials"),
    )
    @locale_doc
    async def tutorialgraduates(self, ctx):
        _(
            """List users who completed all three NewWerewolf tutorial tracks.

            `{prefix}nww tutorialgraduates`
            """
        )
        if not hasattr(self.bot, "pool"):
            return await ctx.send(
                _("Tutorial tracking is unavailable right now (no database connection).")
            )
        try:
            await self._ensure_role_xp_tables()
            async with self.bot.pool.acquire() as conn:
                rows = await conn.fetch(
                    """
                    SELECT user_id, completed_all_at
                    FROM newwerewolf_tutorial_completion
                    WHERE village_completed = TRUE
                      AND werewolf_completed = TRUE
                      AND solo_completed = TRUE
                    ORDER BY completed_all_at DESC NULLS LAST, updated_at DESC
                    LIMIT 100
                    """
                )
        except Exception:
            return await ctx.send(_("Couldn't load tutorial completion data right now."))

        if not rows:
            return await ctx.send(_("No players have completed all three tutorials yet."))

        lines: list[str] = []
        for row in rows:
            user_id = int(row["user_id"])
            completed_at = row["completed_all_at"]
            if completed_at is not None:
                try:
                    completed_text = f"<t:{int(completed_at.timestamp())}:R>"
                except Exception:
                    completed_text = _("unknown time")
            else:
                completed_text = _("unknown time")
            lines.append(f"<@{user_id}> - {completed_text}")

        chunks = self._chunk_lines(lines, max_chars=3800)
        embeds = []
        for idx, chunk in enumerate(chunks, start=1):
            embed = discord.Embed(
                title=_("NewWerewolf Tutorial Graduates"),
                description=chunk,
                colour=self.bot.config.game.primary_colour,
            )
            if len(chunks) > 1:
                embed.set_footer(
                    text=_("Page {page}/{total}").format(
                        page=idx,
                        total=len(chunks),
                    )
                )
            embeds.append(embed)

        if len(embeds) == 1:
            return await ctx.send(embed=embeds[0])
        return await self.bot.paginator.Paginator(extras=embeds).paginate(ctx)

    @newwerewolf.command(brief=_("Check your werewolf role"))
    @locale_doc
    async def myrole(self, ctx):
        _(
            """Check your role in the Werewolf game and have the bot DM it to you.

            You must be part of the ongoing game to get your role."""
        )
        game = self.games.get(ctx.channel.id)
        if not game:
            return await ctx.send(
                _("There is no newwerewolf game in this channel! {author}").format(
                    author=ctx.author.mention
                )
            )
        if game == "forming":
            return await ctx.send(
                _("The game has yet to be started {author}.").format(
                    author=ctx.author.mention
                )
            )
        if ctx.author not in [player.user for player in game.players]:
            return await ctx.send(
                _("You're not in the game {author}.").format(author=ctx.author.mention)
            )
        else:
            player = discord.utils.get(game.players, user=ctx.author)
            if player is None:
                return await ctx.send(
                    _(
                        "You asked for your role in {channel} but your info couldn't be"
                        " found."
                    ).format(channel=ctx.channel.mention)
                )
            else:
                try:
                    if player.role != player.initial_roles[0]:
                        initial_role_info = _(
                            " A **{initial_roles}** initially"
                        ).format(
                            initial_roles=", ".join(
                                [
                                    game.get_role_name(initial_role)
                                    for initial_role in player.initial_roles
                                ]
                            )
                        )
                    else:
                        initial_role_info = ""
                    await ctx.author.send(
                        _(
                            "Checking your role in {ww_channel}... You are a"
                            " **{role_name}**!{initial_role_info}\n\n{description}"
                        ).format(
                            ww_channel=ctx.channel.mention,
                            role_name=player.role_name,
                            initial_role_info=initial_role_info,
                            description=ROLE_DESC[player.role],
                        )
                    )
                    return await ctx.send(
                        _("I sent a DM containing your role info, {author}.").format(
                            author=ctx.author.mention
                        )
                    )
                except discord.Forbidden:
                    return await ctx.send(
                        _("I couldn't send a DM to you {author}.").format(
                            author=ctx.author.mention
                        )
                    )

    @newwerewolf.command(
        name="progress",
        aliases=["xp", "levels"],
        brief=_("View role XP and advanced unlock progress"),
    )
    @locale_doc
    async def progress(self, ctx, *, role: str = None):
        _(
            """View your NewWerewolf role XP progress and advanced unlock status.

            `{prefix}nww progress`
            `{prefix}nww progress bodyguard`
            """
        )
        if not hasattr(self.bot, "pool"):
            return await ctx.send(
                _("Role XP is unavailable right now (no database connection).")
            )

        xp_map = await self._fetch_user_role_xp_map(ctx.author.id)
        base_roles = sorted(
            ADVANCED_ROLE_TIERS_BY_BASE.keys(),
            key=lambda role_obj: self._role_display_name(role_obj).lower(),
        )
        if not base_roles:
            return await ctx.send(_("No advanced role progression is configured yet."))

        if role is not None:
            parsed_roles, invalid_tokens = parse_custom_roles(role)
            if invalid_tokens or not parsed_roles:
                return await ctx.send(
                    _(
                        "I couldn't recognize that role. Use `{prefix}nww roles` to"
                        " see valid role names."
                    ).format(prefix=ctx.clean_prefix)
                )
            if len(parsed_roles) != 1:
                return await ctx.send(_("Please specify exactly one role."))

            requested_role = parsed_roles[0]
            base_role = ADVANCED_BASE_ROLE_BY_ADVANCED.get(requested_role, requested_role)
            if base_role not in ADVANCED_ROLE_TIERS_BY_BASE:
                return await ctx.send(
                    _("**{role}** has no advanced unlock path configured.").format(
                        role=self._role_display_name(base_role)
                    )
                )

            base_role_name = self._role_display_name(base_role)
            xp = xp_map.get(base_role.name.casefold(), 0)
            level = role_level_from_xp(xp)
            xp_current, xp_needed = self._xp_progress_fraction(xp)

            unlock_tiers = sorted(
                ADVANCED_ROLE_TIERS_BY_BASE.get(base_role, {}).items(),
                key=lambda pair: pair[0],
            )
            unlock_lines = []
            for unlock_level, advanced_role in unlock_tiers:
                unlock_lines.append(
                    _("{role} - unlocks level {level}").format(
                        role=self._role_display_name(advanced_role),
                        level=unlock_level,
                    )
                )

            embed = discord.Embed(
                title=_("NewWerewolf Progress"),
                colour=self.bot.config.game.primary_colour,
            ).set_author(name=str(ctx.author), icon_url=ctx.author.display_avatar.url)
            if requested_role != base_role:
                embed.description = _(
                    "Showing base-role progression for **{base}** (requested role:"
                    " **{requested}**)."
                ).format(
                    base=base_role_name,
                    requested=self._role_display_name(requested_role),
                )
            else:
                embed.description = _("Showing progression for **{role}**.\n").format(
                    role=base_role_name
                )
            lines = [
                _("{role}: Level {level} XP: {current}/{needed} (Total: {xp})").format(
                    role=base_role_name,
                    level=level,
                    current=xp_current,
                    needed=xp_needed,
                    xp=xp,
                )
            ]
            lines.extend(unlock_lines if unlock_lines else [_("No advanced unlocks.")])
            embed.add_field(
                name=_("Progress"),
                value="\n".join(lines),
                inline=False,
            )
            return await ctx.send(embed=embed)

        role_cards: list[tuple[str, str]] = []

        for base_role in base_roles:
            role_name = self._role_display_name(base_role)
            xp = xp_map.get(base_role.name.casefold(), 0)
            level = role_level_from_xp(xp)
            xp_current, xp_needed = self._xp_progress_fraction(xp)
            unlock_tiers = sorted(
                ADVANCED_ROLE_TIERS_BY_BASE.get(base_role, {}).items(),
                key=lambda pair: pair[0],
            )

            unlock_lines = [
                _("{role} - unlocks level {level}").format(
                    role=self._role_display_name(advanced_role),
                    level=unlock_level,
                )
                for unlock_level, advanced_role in unlock_tiers
            ]
            if not unlock_lines:
                unlock_lines = [_("No advanced unlocks.")]

            field_value = _(
                "{role}: Level {level} XP: {current}/{needed} (Total: {xp})\n"
                "{unlock_lines}"
            ).format(
                role=role_name,
                level=level,
                current=xp_current,
                needed=xp_needed,
                xp=xp,
                unlock_lines="\n".join(unlock_lines),
            )
            role_cards.append((role_name, field_value))

        embeds = []
        roles_per_page = 6
        total_pages = max(1, (len(role_cards) + roles_per_page - 1) // roles_per_page)
        for idx in range(total_pages):
            page_cards = role_cards[idx * roles_per_page : (idx + 1) * roles_per_page]
            embed = discord.Embed(
                title=_("NewWerewolf Progress"),
                description=_(
                    "Format: `Base role: Level X XP: current/needed (Total: Y)` then"
                    " unlock levels below."
                ),
                colour=self.bot.config.game.primary_colour,
            ).set_author(name=str(ctx.author), icon_url=ctx.author.display_avatar.url)
            for role_name, field_value in page_cards:
                embed.add_field(name=role_name, value=field_value, inline=False)
            embed.set_footer(
                text=_(
                    "Page {page}/{total} | Use `{prefix}nww progress <role>` for details"
                ).format(
                    page=idx + 1,
                    total=total_pages,
                    prefix=ctx.clean_prefix,
                )
            )
            embeds.append(embed)

        if len(embeds) == 1:
            return await ctx.send(embed=embeds[0])
        return await self.bot.paginator.Paginator(extras=embeds).paginate(ctx)

    @newwerewolf.command(brief=_("View descriptions of game roles"))
    @locale_doc
    async def roles(self, ctx, *, role=None):
        _(
            """View the descriptions of roles in the Werewolf game.
            `{prefix}roles` to see all roles.
            `{prefix}roles <role name here>` to view info about a role.
            """
        )
        restriction = _("(IdleRPG mode only)")
        role_groups = [
            {
                "side": _("The Werewolves"),
                "members": (
                    "Werewolf, Junior Werewolf, Wolf Seer, Sorcerer - Advanced"
                    " unlock, White Wolf, Cursed Wolf"
                    " Father, Big Bad Wolf, Wolf"
                    f" Shaman - {restriction}, Wolf Necromancer - {restriction},"
                    f" Alpha Werewolf - {restriction}, Wolf Summoner - Advanced unlock,"
                    " Wolf Trickster - Advanced unlock,"
                    f" Guardian Wolf - {restriction}, Nightmare Werewolf - {restriction},"
                    " Voodoo Werewolf - Advanced unlock, Wolf Pacifist - Advanced"
                    " unlock"
                ),
                "goal": _("Must eliminate all other villagers"),
            },
            {
                "side": _("The Villagers"),
                "members": (
                    "Villager, Cursed, Pure Soul, Flower Child, Seer, Aura Seer,"
                    " Gambler - Advanced unlock, Witch,"
                    " Forger - Advanced unlock,"
                    " Doctor, Bodyguard, Sheriff, Jailer, Medium, Loudmouth, Avenger,"
                    f" Red Lady - {restriction}, Ghost Lady - Advanced unlock, Priest - {restriction}, Marksman - Advanced unlock, Pacifist -"
                    f" {restriction}, Grumpy Grandma - {restriction}, Detective,"
                    " Mortician - Advanced unlock, Warden -"
                    " Advanced unlock, Seer Apprentice - Advanced unlock, Tough Guy -"
                    " Advanced unlock,"
                    " Healer, Amor,"
                    " Knight, Fortune Teller, Hunter -"
                    " Huntergame only,"
                    f" Sister, Brother, The Old, Fox, Judge, Paragon - {restriction},"
                    " Ritualist - Advanced unlock,"
                    f" Troublemaker - {restriction}, Lawyer - {restriction},"
                    f" War Veteran - {restriction}"
                ),
                "goal": _("Must find and eliminate the werewolves"),
            },
            {
                "side": _("The Ambiguous"),
                "members": (
                    f"Thief, Maid, Wolfhound, Raider - {restriction}"
                ),
                "goal": _("Make their side win"),
            },
            {
                "side": _("The Loners"),
                "members": (
                    f"White Wolf - {_('Be the sole survivor')}, Flutist -"
                    f" {_('Must enchant every living inhabitants')}, Superspreader -"
                    f" {_('Infect all the players with your virus')} {restriction},"
                    f" Jester -"
                    f" {_('Die to win')}, Head Hunter -"
                    f" {_('Get your assigned target lynched')},"
                    f" Serial Killer - {_('Be the sole survivor')} (Advanced unlock),"
                    f" Cannibal - {_('Be the sole survivor')} (Advanced unlock)"
                ),
                "goal": _("Must complete their own objective"),
            },
        ]

        def has_role(group: dict[str, str], role_name: str) -> bool:
            normalized_members = [
                member.split(" - ")[0].strip().lower()
                for member in group["members"].split(",")
            ]
            return role_name.lower() in normalized_members

        if role is None:
            em = discord.Embed(
                title=_("Werewolf Roles"),
                description=_(
                    "Roles are grouped into \n1. the Werewolves,\n2. the Villagers,\n3."
                    " the Ambiguous, and\n4. the Loners.\n**The available roles are:**"
                ),
                url="https://wiki.idlerpg.xyz/index.php?title=Werewolf",
                colour=self.bot.config.game.primary_colour,
            ).set_author(name=str(ctx.author), icon_url=ctx.author.display_avatar.url)
            tip = _(
                "Use `{prefix}nww roles <role>` to view the description on a specific"
                " role."
            ).format(prefix=ctx.clean_prefix)
            embeds = [
                em.copy().add_field(
                    name=f"{group['side']} - {_('Goal')}: {group['goal']}",
                    value=group["members"].replace(", ", "\n") + f"\n\n**Tip:** {tip}",
                    inline=True,
                )
                for group in role_groups
            ]
            return await self.bot.paginator.Paginator(extras=embeds).paginate(ctx)

        search_role = role.upper().replace(" ", "_")
        try:
            ROLES[search_role]
        except KeyError:
            return await ctx.send(
                _("{role}? I couldn't find that role.").format(role=role.title())
            )
        role_groups.reverse()
        return await ctx.send(
            embed=discord.Embed(
                title=search_role.title().replace("_", " "),
                description=ROLE_DESC[ROLES[search_role]],
                colour=self.bot.config.game.primary_colour,
            )
            .add_field(
                name=_("Side:"),
                value=", ".join(
                    [
                        group["side"]
                        for group in role_groups
                        if has_role(group, role.title())
                    ]
                ),
                inline=True,
            )
            .add_field(
                name=_("Goal:"),
                value=", ".join(
                    [
                        group["goal"]
                        for group in role_groups
                        if has_role(group, role.title())
                    ]
                ),
                inline=True,
            )
            .set_author(name=str(ctx.author), icon_url=ctx.author.display_avatar.url)
        )


async def setup(bot):
    await bot.add_cog(NewWerewolf(bot))

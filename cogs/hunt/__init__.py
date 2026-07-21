import asyncio
import random
from collections import deque
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import discord
from discord.ext import commands, tasks

from utils import misc as rpgtools
from utils.checks import is_gm


HUNT_ADJECTIVES = ("Dread", "Ancient", "Pale", "Thundering", "Vile")
HUNT_BEASTS = ("Behemoth", "Wendigo", "Chimera", "Leviathan", "Manticore")
HUNT_JOIN_SECONDS = 900          # 15-minute join window (raid-style), not 120s
HUNT_MIN_HUNTERS = 6
HUNT_MAX_GATHER_FAILS = 3         # after this many failed gathers the beast escapes
HUNT_RESUMMON_MINUTES = 120       # a submerged beast resurfaces after this long (2 hours)
HUNT_TECHNICAL_RETRY_MINUTES = 10
HUNT_ALERT_ROLE_NAME = "Hunt Alerts"
HUNT_BOARD_REFRESH_SECONDS = 2
CRATE_WEIGHTS = (
    ("common", 40),
    ("uncommon", 25),
    ("rare", 18),
    ("magic", 10),
    ("legendary", 5),
    ("fortune", 1.5),
    ("divine", 0.5),
)
THRESHOLD_FLAVOR = {
    25: "The trail sharpens. Hunters hear distant footfalls.",
    50: "Broken trees and deep gouges mark the beast's passing.",
    75: "The air turns heavy. The beast is close.",
    100: "The quarry is cornered.",
}


def generate_beast_name(seed=None):
    rng = random.Random(seed) if seed is not None else random
    return f"the {rng.choice(HUNT_ADJECTIVES)} {rng.choice(HUNT_BEASTS)}"


def roll_weighted_crate(rng=None):
    rng = rng or random
    crates = [crate for crate, _weight in CRATE_WEIGHTS]
    weights = [weight for _crate, weight in CRATE_WEIGHTS]
    return rng.choices(crates, weights=weights, k=1)[0]


class HuntAlertView(discord.ui.View):
    """Persistent, no-clutter opt-in control for Hunt notifications."""

    def __init__(self, cog):
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(
        label="Toggle Hunt Alerts",
        emoji="🔔",
        style=discord.ButtonStyle.secondary,
        custom_id="hunt:toggle_alerts",
    )
    async def toggle_alerts(self, interaction, button):
        await self.cog.toggle_alert_role(interaction)


class HuntJoinView(discord.ui.View):
    def __init__(self, cog, beast_name, max_players=20, timeout=HUNT_JOIN_SECONDS):
        super().__init__(timeout=timeout)
        self.cog = cog
        self.beast_name = beast_name
        self.max_players = max_players
        self.min_players = HUNT_MIN_HUNTERS
        self.minutes = HUNT_JOIN_SECONDS // 60
        self.joined = []
        self.message = None
        self.closed = False
        self._join_lock = asyncio.Lock()

    def _hunter_lines(self):
        if not self.joined:
            return "No hunters have joined yet."
        return "\n".join(
            f"{idx}. {member.mention}"
            for idx, member in enumerate(self.joined, start=1)
        )

    def build_embed(self):
        needed = max(0, self.min_players - len(self.joined))
        if self.closed:
            status = "Gathering closed."
        elif needed:
            status = f"{needed} more hunter(s) needed to begin."
        else:
            status = "Minimum party ready."
        embed = discord.Embed(
            title=f"🐾 {self.beast_name} surfaces!",
            description=(
                f"Hunters have **{self.minutes} minutes** to join. "
                f"{self.min_players}-{self.max_players} players.\n{status}"
            ),
            color=0x1E8449,
        )
        embed.add_field(
            name=f"Hunters ({len(self.joined)}/{self.max_players})",
            value=self._hunter_lines(),
            inline=False,
        )
        return embed

    async def refresh_message(self):
        if not self.message:
            return
        try:
            await self.message.edit(embed=self.build_embed(), view=self)
        except Exception:
            pass

    async def close_roster(self):
        async with self._join_lock:
            self.closed = True
            for child in self.children:
                child.disabled = True
        await self.refresh_message()

    @discord.ui.button(label="Join the Hunt", style=discord.ButtonStyle.success)
    async def join_button(self, interaction, button):
        if self.closed:
            return await interaction.response.send_message(
                "This Hunt roster has closed.",
                ephemeral=True,
            )
        if any(member.id == interaction.user.id for member in self.joined):
            return await interaction.response.send_message("You already joined.", ephemeral=True)
        if len(self.joined) >= self.max_players:
            return await interaction.response.send_message("This hunt party is full.", ephemeral=True)
        async with self.cog.bot.pool.acquire() as conn:
            has_profile = await conn.fetchval(
                'SELECT 1 FROM profile WHERE "user" = $1',
                interaction.user.id,
            )
        if not has_profile:
            return await interaction.response.send_message("You need a character to join.", ephemeral=True)
        # The profile query yields control, so repeat every roster check while
        # holding the lock. This prevents duplicate, 21st, and post-deadline joins.
        rejection = None
        async with self._join_lock:
            if self.closed:
                rejection = "This Hunt roster has closed."
            elif any(member.id == interaction.user.id for member in self.joined):
                rejection = "You already joined."
            elif len(self.joined) >= self.max_players:
                rejection = "This hunt party is full."
            else:
                self.joined.append(interaction.user)
        if rejection:
            return await interaction.response.send_message(rejection, ephemeral=True)
        await interaction.response.send_message("You joined the beast hunt.", ephemeral=True)
        await self.refresh_message()


class Hunt(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self._tables_ready = False
        self._table_lock = asyncio.Lock()
        self._fight_active = False
        self._surface_task = None
        self._board_refresh_task = None
        self._board_refresh_requested = False
        self._board_message = None
        self._active_join_view = None
        self._alert_view = HuntAlertView(self)

    async def ensure_tables(self):
        if self._tables_ready:
            return
        async with self._table_lock:
            if self._tables_ready:
                return
            async with self.bot.pool.acquire() as conn:
                await conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS hunt_state (
                        id INT PRIMARY KEY,
                        active BOOLEAN NOT NULL DEFAULT FALSE,
                        channel_id BIGINT,
                        tracks INT NOT NULL DEFAULT 0,
                        target INT NOT NULL DEFAULT 100,
                        beast_name TEXT,
                        started_at TIMESTAMP,
                        expires_at TIMESTAMP
                    );
                    """
                )
                await conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS hunt_tracks (
                        user_id BIGINT PRIMARY KEY,
                        tracks INT NOT NULL DEFAULT 0
                    );
                    """
                )
                await conn.execute(
                    "ALTER TABLE hunt_tracks ADD COLUMN IF NOT EXISTS first_track_at TIMESTAMP NOT NULL DEFAULT NOW();"
                )
                # FIX 9: a failed gather submerges the beast instead of ending the hunt
                await conn.execute(
                    "ALTER TABLE hunt_state ADD COLUMN IF NOT EXISTS resummon_at TIMESTAMP;"
                )
                await conn.execute(
                    "ALTER TABLE hunt_state ADD COLUMN IF NOT EXISTS gather_fails INT NOT NULL DEFAULT 0;"
                )
                await conn.execute(
                    "ALTER TABLE hunt_state ADD COLUMN IF NOT EXISTS status_message_id BIGINT;"
                )
                await conn.execute(
                    """
                    INSERT INTO hunt_state (id, active)
                    VALUES (1, FALSE)
                    ON CONFLICT (id) DO NOTHING;
                    """
                )
            self._tables_ready = True

    async def cog_load(self):
        await self.ensure_tables()
        self.bot.add_view(self._alert_view)
        if not self.hunt_clock.is_running():
            self.hunt_clock.start()

    def cog_unload(self):
        self.hunt_clock.cancel()
        if self._surface_task and not self._surface_task.done():
            self._surface_task.cancel()
        if self._board_refresh_task and not self._board_refresh_task.done():
            self._board_refresh_task.cancel()
        if self._active_join_view:
            self._active_join_view.stop()
        self._alert_view.stop()

    async def _state(self, conn=None):
        await self.ensure_tables()
        query = "SELECT * FROM hunt_state WHERE id = 1"
        if conn is not None:
            return await conn.fetchrow(query)
        async with self.bot.pool.acquire() as conn2:
            return await conn2.fetchrow(query)

    @staticmethod
    def _row_value(row, key, default=None):
        if row is None:
            return default
        try:
            value = row[key]
        except (KeyError, IndexError, TypeError):
            value = getattr(row, key, default)
        return default if value is None else value

    @staticmethod
    def _snowflake(value):
        try:
            value = int(value)
        except (TypeError, ValueError):
            return None
        return value if value > 0 else None

    @staticmethod
    def _utc_timestamp(value):
        if not value:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return int(value.timestamp())

    def _hunt_settings(self):
        config = getattr(self.bot, "config", None)
        ids = getattr(config, "ids", None)
        if ids and hasattr(ids, "get_section"):
            return ids.get_section("hunt", {})
        return {}

    def _configured_channel_id(self):
        channel_id = self._snowflake(self._hunt_settings().get("announcement_channel_id"))
        if channel_id:
            return channel_id
        game = getattr(getattr(self.bot, "config", None), "game", None)
        return self._snowflake(getattr(game, "bot_event_channel", None))

    def _announcement_channel(self, ctx=None, state=None):
        channel_id = self._snowflake(self._row_value(state, "channel_id"))
        if not channel_id:
            channel_id = self._configured_channel_id()
        if channel_id:
            return self.bot.get_channel(channel_id)
        return getattr(ctx, "channel", None)

    def _alert_role(self, guild):
        if guild is None:
            return None
        role_id = self._snowflake(self._hunt_settings().get("ping_role_id"))
        if role_id:
            role = guild.get_role(role_id)
            if role:
                return role
        return discord.utils.get(getattr(guild, "roles", ()), name=HUNT_ALERT_ROLE_NAME)

    @staticmethod
    def _role_allowed_mentions():
        return discord.AllowedMentions(
            everyone=False,
            users=False,
            roles=True,
            replied_user=False,
        )

    @staticmethod
    def _no_mentions():
        return discord.AllowedMentions.none()

    async def toggle_alert_role(self, interaction):
        guild = getattr(interaction, "guild", None)
        member = getattr(interaction, "user", None)
        if guild is None or member is None or not hasattr(member, "roles"):
            return await interaction.response.send_message(
                "Hunt alerts can only be changed inside the server.",
                ephemeral=True,
            )
        role = self._alert_role(guild)
        if role is None:
            return await interaction.response.send_message(
                f"The **{HUNT_ALERT_ROLE_NAME}** role has not been configured yet.",
                ephemeral=True,
            )
        me = getattr(guild, "me", None)
        if role.managed or (me is not None and role >= me.top_role):
            return await interaction.response.send_message(
                "I cannot manage the Hunt Alerts role. Move it below my highest role.",
                ephemeral=True,
            )
        try:
            if role in member.roles:
                await member.remove_roles(role, reason="Hunt alert opt-out")
                message = "🔕 Hunt alerts turned **off**."
            else:
                await member.add_roles(role, reason="Hunt alert opt-in")
                message = "🔔 Hunt alerts turned **on**."
        except discord.HTTPException:
            message = "I do not have permission to manage the Hunt Alerts role."
        await interaction.response.send_message(message, ephemeral=True)

    def _surface_running(self):
        return self._fight_active or bool(self._surface_task and not self._surface_task.done())

    def _phase_text(self, state):
        if not bool(self._row_value(state, "active", False)):
            return "⚫ **Ended** — this hunt is no longer active."
        tracks = int(self._row_value(state, "tracks", 0))
        target = int(self._row_value(state, "target", 100))
        if self._surface_running():
            return "🔴 **Surfaced** — use the Join the Hunt button in this channel now."
        resummon_at = self._row_value(state, "resummon_at")
        if tracks >= target and resummon_at:
            stamp = self._utc_timestamp(resummon_at)
            fails = int(self._row_value(state, "gather_fails", 0))
            return (
                f"🌫️ **Submerged** — automatically resurfaces <t:{stamp}:R> "
                f"(gathering attempt {fails + 1}/{HUNT_MAX_GATHER_FAILS})."
            )
        if tracks >= target:
            return "🐾 **Trail complete** — the beast is preparing to surface."
        return "🔎 **Tracking** — ordinary activities can reveal tracks automatically."

    async def _top_trackers(self, limit=5):
        async with self.bot.pool.acquire() as conn:
            return await conn.fetch(
                """
                SELECT user_id, tracks
                FROM hunt_tracks
                ORDER BY tracks DESC, first_track_at ASC
                LIMIT $1
                """,
                int(limit),
            )

    async def _build_hunt_board(self, state=None):
        state = state or await self._state()
        tracks = int(self._row_value(state, "tracks", 0))
        target = int(self._row_value(state, "target", 100))
        beast_name = self._row_value(state, "beast_name", "Unknown quarry")
        expires_at = self._row_value(state, "expires_at")
        deadline = self._utc_timestamp(expires_at)
        trackers = await self._top_trackers()

        description = (
            f"## {str(beast_name).title()}\n"
            f"{self._phase_text(state)}\n\n"
            f"`{self._progress_bar(tracks, target)}` **{tracks}/{target} tracks**"
        )
        if deadline:
            description += f"\nHunt deadline: <t:{deadline}:R>"

        embed = discord.Embed(
            title="🐾 WILD HUNT BOARD",
            description=description,
            color=0x1E8449 if bool(self._row_value(state, "active", False)) else 0x626970,
        )
        embed.add_field(
            name="How to Find Tracks",
            value=(
                "Tracks roll automatically while the Hunt is active:\n"
                "🗼 **Battle Tower victory** — 12%\n"
                "🧭 **Completed adventure** — 8%\n"
                "🐉 **Ice Dragon victory** — 20% per party member\n"
                "⚔️ **Supported Ragnarok raid** — 10% per participant"
            ),
            inline=False,
        )
        embed.add_field(
            name="When the Beast Surfaces",
            value=(
                f"A **{HUNT_JOIN_SECONDS // 60}-minute** Join button opens here. "
                f"The party needs **{HUNT_MIN_HUNTERS}–20 hunters**. "
                "Use **Toggle Hunt Alerts** below for start and surface notifications."
            ),
            inline=False,
        )
        embed.add_field(
            name="Kill Rewards",
            value=(
                "Every participant: **$20,000 + 30 Legacy Points**\n"
                "Every survivor: **1 weighted crate**\n"
                "Top tracker: **1 additional Divine Crate**"
            ),
            inline=False,
        )
        embed.add_field(
            name="Top Trackers",
            value=(
                "\n".join(
                    f"**{index}.** <@{row['user_id']}> — {row['tracks']}"
                    for index, row in enumerate(trackers, start=1)
                )
                or "No tracks have been found yet."
            ),
            inline=False,
        )
        embed.set_footer(text="Commands: $hunt • $huntalerts • alerts never use @everyone")
        return embed

    async def _refresh_board(self, state=None, create_if_missing=True):
        state = state or await self._state()
        if not state:
            return None
        channel = self._announcement_channel(state=state)
        if channel is None:
            return None
        message_id = self._snowflake(self._row_value(state, "status_message_id"))
        message = self._board_message
        if message is not None and message_id and getattr(message, "id", None) != message_id:
            message = None
        if message is None and message_id:
            try:
                message = await channel.fetch_message(message_id)
            except (discord.NotFound, discord.Forbidden, discord.HTTPException, AttributeError):
                message = None
        embed = await self._build_hunt_board(state)
        if message is not None:
            try:
                await message.edit(embed=embed, view=self._alert_view)
                self._board_message = message
                return message
            except (discord.NotFound, discord.Forbidden, discord.HTTPException, AttributeError):
                message = None
        if not create_if_missing or not bool(self._row_value(state, "active", False)):
            return None
        try:
            message = await channel.send(
                embed=embed,
                view=self._alert_view,
                allowed_mentions=self._no_mentions(),
            )
        except (discord.Forbidden, discord.HTTPException, AttributeError):
            return None
        self._board_message = message
        async with self.bot.pool.acquire() as conn:
            await conn.execute(
                "UPDATE hunt_state SET status_message_id = $1 WHERE id = 1",
                message.id,
            )
        return message

    def _request_board_refresh(self):
        self._board_refresh_requested = True
        if self._board_refresh_task and not self._board_refresh_task.done():
            return

        async def runner():
            try:
                await asyncio.sleep(HUNT_BOARD_REFRESH_SECONDS)
                while self._board_refresh_requested:
                    self._board_refresh_requested = False
                    try:
                        await self._refresh_board()
                    except Exception:
                        pass
                    if self._board_refresh_requested:
                        await asyncio.sleep(HUNT_BOARD_REFRESH_SECONDS)
            finally:
                self._board_refresh_task = None

        self._board_refresh_task = asyncio.create_task(runner())

    def _schedule_spawn(self, state):
        if self._surface_running():
            return False
        task = asyncio.create_task(self._spawn_beast(state))
        self._surface_task = task

        def finished(done):
            if self._surface_task is done:
                self._surface_task = None
            if not done.cancelled():
                try:
                    done.exception()
                except Exception:
                    pass

        task.add_done_callback(finished)
        return True

    async def _expire_if_needed(self, ctx=None, *, ignore_surface=False):
        state = await self._state()
        if not state or not state["active"] or not state["expires_at"]:
            return None
        if self._surface_running() and not ignore_surface:
            return state
        expires_at = state["expires_at"].replace(tzinfo=None) if getattr(state["expires_at"], "tzinfo", None) else state["expires_at"]
        now = datetime.utcnow()
        if now <= expires_at:
            return state
        async with self.bot.pool.acquire() as conn:
            expired = await conn.fetchrow(
                """
                UPDATE hunt_state
                SET active = FALSE, resummon_at = NULL
                WHERE id = 1
                  AND active = TRUE
                  AND expires_at = $1
                  AND expires_at < $2
                RETURNING *
                """,
                state["expires_at"],
                now,
            )
        if not expired:
            # Another caller either expired this generation or started a new one.
            return await self._state()
        channel = self._announcement_channel(ctx=ctx, state=expired)
        if channel:
            await channel.send(
                f"🐾 The tracks of **{expired['beast_name']}** fade. The Hunt has ended.",
                allowed_mentions=self._no_mentions(),
            )
        self._request_board_refresh()
        return None

    async def _member_stats(self, member, conn):
        profile = await conn.fetchrow(
            'SELECT health, stathp, xp FROM profile WHERE "user" = $1',
            member.id,
        )
        if not profile:
            return None
        dmg, deff = await self.bot.get_raidstats(member, conn=conn)
        level = rpgtools.xptolevel(profile["xp"])
        hp = profile["health"] + 250 + level * 15 + profile["stathp"] * 50
        return {
            "member": member,
            "hp": float(hp),
            "max_hp": float(hp),
            "damage": float(dmg),
            "armor": float(deff),
        }

    def _living(self, players):
        return [player for player in players if player["hp"] > 0]

    def _progress_bar(self, tracks, target, width=16):
        filled = min(width, int(width * min(tracks, target) / max(1, target)))
        return "█" * filled + "░" * (width - filled)

    async def _announce_track(self, state, user_id, tracks, target, crossed=None):
        # Individual finds used to produce as many as 100 mention-heavy messages.
        # The live board now handles routine progress; only three quiet milestones post.
        if crossed not in (25, 50, 75):
            return
        channel = self._announcement_channel(state=state)
        if channel:
            await channel.send(
                f"🐾 **Hunt milestone — {crossed}%** · {tracks}/{target} tracks\n"
                f"{THRESHOLD_FLAVOR[crossed]}",
                allowed_mentions=self._no_mentions(),
            )

    async def _maybe_drop_track(self, ctx, user_id, chance):
        try:
            state = await self._expire_if_needed(ctx)
            if not state or not state["active"] or random.random() >= chance:
                return
            async with self.bot.pool.acquire() as conn:
                async with conn.transaction():
                    state = await conn.fetchrow(
                        """
                        UPDATE hunt_state
                        SET tracks = tracks + 1
                        WHERE id = 1
                          AND active = TRUE
                          AND tracks < target
                        RETURNING *
                        """
                    )
                    if not state:
                        return
                    after_tracks = int(state["tracks"] or 0)
                    target = int(state["target"] or 100)
                    before_tracks = max(0, after_tracks - 1)
                    await conn.execute(
                        """
                        INSERT INTO hunt_tracks (user_id, tracks, first_track_at)
                        VALUES ($1, 1, NOW())
                        ON CONFLICT (user_id) DO UPDATE
                        SET tracks = hunt_tracks.tracks + 1
                        """,
                        int(user_id),
                    )
            crossed = None
            for threshold in (25, 50, 75, 100):
                if before_tracks < target * threshold / 100 <= after_tracks:
                    crossed = threshold
            await self._announce_track(state, user_id, after_tracks, target, crossed=crossed)
            self._request_board_refresh()
            if after_tracks >= target:
                self._schedule_spawn(state)
        except Exception:
            pass

    def _status_embed(self, beast, players, round_no, log):
        hunter_lines = []
        for player in players:
            status = "DOWN" if player["hp"] <= 0 else f"{player['hp']:,.0f} HP"
            hunter_lines.append(f"{player['member'].mention}: {status}")
        embed = discord.Embed(
            title=f"Hunt Beast — Round {round_no}",
            description=f"{beast['name']} HP: **{max(0, beast['hp']):,.0f}/{beast['max_hp']:,.0f}**",
            color=0x1E8449,
        )
        embed.add_field(
            name="Hunters",
            value="\n".join(hunter_lines) or "None",
            inline=False,
        )
        embed.add_field(name="Battle Log", value="\n".join(log) or "The beast circles.", inline=False)
        return embed

    async def _award_money(self, user_id, amount, conn=None):
        query = 'UPDATE profile SET money = money + $1 WHERE "user" = $2'
        if conn is not None:
            await conn.execute(query, amount, user_id)
        else:
            async with self.bot.pool.acquire() as conn2:
                await conn2.execute(query, amount, user_id)

    async def _award_crate(self, user_id, crate, conn=None):
        query = f'UPDATE profile SET crates_{crate} = crates_{crate} + 1 WHERE "user" = $1'
        if conn is not None:
            await conn.execute(query, user_id)
        else:
            async with self.bot.pool.acquire() as conn2:
                await conn2.execute(query, user_id)

    async def _award_legacy(self, user_id, amount, conn=None):
        legacy = self.bot.get_cog("Legacy")
        if legacy:
            await legacy.award_points(user_id, amount, conn=conn)

    async def _submerge_or_escape(self, channel):
        """A failed gather no longer ends the hunt — the beast submerges and
        resurfaces later. Only after HUNT_MAX_GATHER_FAILS does it escape."""
        async with self.bot.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                UPDATE hunt_state
                SET gather_fails = gather_fails + 1,
                    resummon_at = $1
                WHERE id = 1
                RETURNING gather_fails, beast_name, resummon_at
                """,
                datetime.utcnow() + timedelta(minutes=HUNT_RESUMMON_MINUTES),
            )
            fails = int(row["gather_fails"]) if row else HUNT_MAX_GATHER_FAILS
            beast_name = row["beast_name"] if row else "the beast"

            if fails >= HUNT_MAX_GATHER_FAILS:
                # The beast finally escapes; refund trackers a little for their effort
                await conn.execute("UPDATE hunt_state SET active = FALSE, resummon_at = NULL WHERE id = 1")
                trackers = await conn.fetch("SELECT user_id, tracks FROM hunt_tracks")
                if channel:
                    await channel.send(
                        f"🐾 **{beast_name}** slips away for good after too few hunts gathered. "
                        "The trail goes cold. Trackers are compensated for their effort.",
                        allowed_mentions=self._no_mentions(),
                    )
                legacy = self.bot.get_cog("Legacy")
                if legacy:
                    for t in trackers:
                        await legacy.award_points(t["user_id"], min(int(t["tracks"]) * 5, 100))
                self._request_board_refresh()
                return

            if channel:
                stamp = self._utc_timestamp(row["resummon_at"]) if row else None
                await channel.send(
                    f"🌫️ Too few hunters gathered — **{beast_name}** senses the weakness and "
                    f"melts back into the wild. It will automatically resurface "
                    f"<t:{stamp}:R> (failed gathering {fails}/{HUNT_MAX_GATHER_FAILS}).",
                    allowed_mentions=self._no_mentions(),
                )
        self._request_board_refresh()

    async def maybe_resummon(self, ctx=None):
        """Atomically claim and schedule a Hunt whose resurfacing time is due."""
        if self._surface_running():
            return False
        async with self.bot.pool.acquire() as conn:
            state = await conn.fetchrow(
                """
                UPDATE hunt_state
                SET resummon_at = NULL
                WHERE id = 1
                  AND active = TRUE
                  AND tracks >= target
                  AND resummon_at IS NOT NULL
                  AND resummon_at <= $1
                  AND (expires_at IS NULL OR expires_at > $1)
                RETURNING *
                """,
                datetime.utcnow(),
            )
        if state:
            scheduled = self._schedule_spawn(state)
            if scheduled:
                self._request_board_refresh()
            return scheduled
        return False

    async def _spawn_beast(self, state):
        if self._fight_active:
            return
        latest = await self._state()
        if not latest or not latest["active"]:
            return
        scheduled_generation = self._row_value(state, "started_at")
        latest_generation = self._row_value(latest, "started_at")
        if scheduled_generation and latest_generation != scheduled_generation:
            return
        if self._row_value(latest, "beast_name") != self._row_value(state, "beast_name"):
            return
        if int(latest["tracks"] or 0) < int(latest["target"] or 100):
            return
        expires_at = latest["expires_at"]
        if expires_at:
            if getattr(expires_at, "tzinfo", None):
                expires_at = expires_at.replace(tzinfo=None)
            if datetime.utcnow() >= expires_at:
                await self._expire_if_needed(ignore_surface=True)
                return
        state = latest
        self._fight_active = True
        channel = self._announcement_channel(state=state)
        if not channel:
            self._fight_active = False
            return
        try:
            view = HuntJoinView(self, state["beast_name"])
            self._active_join_view = view
            role = self._alert_role(getattr(channel, "guild", None))
            alert = f"{role.mention}\n" if role else ""
            alert += (
                f"🐾 **{state['beast_name']} has surfaced.** "
                f"The Join button is open for {view.minutes} minutes."
            )
            view.message = await channel.send(
                content=alert,
                embed=view.build_embed(),
                view=view,
                allowed_mentions=self._role_allowed_mentions(),
            )
            await self._refresh_board(state, create_if_missing=False)
            await asyncio.sleep(HUNT_JOIN_SECONDS)
            view.stop()
            await view.close_roster()
            self._active_join_view = None
            participants = []
            seen_ids = set()
            for member in view.joined:
                if member.id in seen_ids:
                    continue
                seen_ids.add(member.id)
                participants.append(member)
            participants = participants[:20]
            if len(participants) < HUNT_MIN_HUNTERS:
                await self._submerge_or_escape(channel)
                return

            async with self.bot.pool.acquire() as conn:
                players = []
                for member in participants:
                    stats = await self._member_stats(member, conn)
                    if stats:
                        players.append(stats)
            if len(players) < HUNT_MIN_HUNTERS:
                await self._submerge_or_escape(channel)
                return

            target = int(state["target"] or 100)
            beast = {
                "name": state["beast_name"],
                "hp": float(40000 + 400 * target),
                "max_hp": float(40000 + 400 * target),
                "damage": 800.0,
                "armor": 260.0,
            }
            log = deque(maxlen=6)
            message = await channel.send(embed=self._status_embed(beast, players, 0, log))
            killed = False
            for round_no in range(1, 21):
                living = self._living(players)
                if not living:
                    break
                damage = sum(max(1.0, player["damage"] - beast["armor"]) for player in living)
                beast["hp"] -= damage
                log.append(f"The hunters strike for **{damage:,.0f}**!")
                if beast["hp"] <= 0:
                    killed = True
                    await message.edit(embed=self._status_embed(beast, players, round_no, log))
                    break
                targets = random.sample(living, k=min(2, len(living)))
                hit_lines = []
                for target_player in targets:
                    hit = max(1.0, beast["damage"] - target_player["armor"])
                    target_player["hp"] = max(0.0, target_player["hp"] - hit)
                    hit_lines.append(f"{target_player['member'].display_name} for {hit:,.0f}")
                log.append("The beast mauls " + ", ".join(hit_lines) + ".")
                await message.edit(embed=self._status_embed(beast, players, round_no, log))
                await asyncio.sleep(3)

            if not killed:
                await channel.send(
                    "🐾 The beast flees after twenty brutal rounds. No rewards are paid.",
                    allowed_mentions=self._no_mentions(),
                )
                async with self.bot.pool.acquire() as conn:
                    await conn.execute(
                        "UPDATE hunt_state SET active = FALSE, resummon_at = NULL WHERE id = 1"
                    )
                self._request_board_refresh()
                return

            survivors = self._living(players)
            survivor_ids = {player["member"].id for player in survivors}
            top_tracker = None
            try:
                async with self.bot.pool.acquire() as conn:
                    async with conn.transaction():
                        top_tracker = await conn.fetchrow(
                            """
                            SELECT user_id, tracks
                            FROM hunt_tracks
                            ORDER BY tracks DESC, first_track_at ASC
                            LIMIT 1
                            """
                        )
                        for member in participants:
                            await self._award_money(member.id, 20000, conn=conn)
                            await self._award_legacy(member.id, 30, conn=conn)
                            if member.id in survivor_ids:
                                await self._award_crate(
                                    member.id,
                                    roll_weighted_crate(),
                                    conn=conn,
                                )
                        if top_tracker:
                            await self._award_crate(
                                top_tracker["user_id"],
                                "divine",
                                conn=conn,
                            )
                        await conn.execute(
                            "UPDATE hunt_state SET active = FALSE, resummon_at = NULL WHERE id = 1"
                        )
            except Exception:
                logger = getattr(self.bot, "logger", None)
                if logger:
                    logger.exception("Hunt reward transaction failed; closing the Hunt without partial payouts.")
                try:
                    async with self.bot.pool.acquire() as conn:
                        await conn.execute(
                            "UPDATE hunt_state SET active = FALSE, resummon_at = NULL WHERE id = 1"
                        )
                except Exception:
                    if logger:
                        logger.exception("Hunt could not be marked inactive after a reward failure.")
                await channel.send(
                    "⚠️ The beast was slain, but its reward transaction could not complete. "
                    "No partial payout was kept; a Game Master has been notified.",
                    allowed_mentions=self._no_mentions(),
                )
                self._request_board_refresh()
                return

            self.bot.dispatch(
                "hunt_beast_slain",
                SimpleNamespace(channel=channel),
                [member.id for member in participants],
                [member.id for member in survivors],
                int(top_tracker["user_id"]) if top_tracker else None,
            )
            logger = getattr(self.bot, "logger", None)
            if top_tracker:
                try:
                    await channel.send(
                        f"🏆 Top tracker: <@{top_tracker['user_id']}> with **{top_tracker['tracks']}** tracks earns **1 Divine Crate**!",
                        allowed_mentions=self._no_mentions(),
                    )
                except discord.HTTPException:
                    if logger:
                        logger.exception("Could not post the Hunt top-tracker result.")
            try:
                await channel.send(
                    "🐾 The beast is slain! Participants earned **$20,000** and **+30 Legacy Points**; survivors also received a crate roll.",
                    allowed_mentions=self._no_mentions(),
                )
            except discord.HTTPException:
                if logger:
                    logger.exception("Could not post the Hunt completion result.")
            self._request_board_refresh()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger = getattr(self.bot, "logger", None)
            if logger:
                logger.exception("Unexpected Hunt surface/fight failure.")
            retry_at = datetime.utcnow() + timedelta(minutes=HUNT_TECHNICAL_RETRY_MINUTES)
            retry_scheduled = False
            try:
                async with self.bot.pool.acquire() as conn:
                    retry_scheduled = bool(
                        await conn.fetchval(
                            """
                            UPDATE hunt_state
                            SET resummon_at = $1
                            WHERE id = 1
                              AND active = TRUE
                              AND tracks >= target
                            RETURNING TRUE
                            """,
                            retry_at,
                        )
                    )
            except Exception:
                if logger:
                    logger.exception("Could not persist the Hunt technical retry timer.")
            if retry_scheduled:
                try:
                    await channel.send(
                        "⚠️ The Hunt encounter hit a technical problem and was paused. "
                        f"It will retry automatically <t:{self._utc_timestamp(retry_at)}:R>.",
                        allowed_mentions=self._no_mentions(),
                    )
                except Exception:
                    pass
                self._request_board_refresh()
        finally:
            if self._active_join_view:
                self._active_join_view.stop()
            self._active_join_view = None
            self._fight_active = False
            try:
                await self._refresh_board(create_if_missing=False)
            except Exception:
                pass

    @commands.command(name="starthunt")
    @is_gm()
    async def starthunt(self, ctx, target: int = 100):
        await self.ensure_tables()
        target = max(1, int(target))
        current = await self._expire_if_needed(ctx)
        if current and current["active"]:
            return await ctx.send(
                f"A Hunt for **{current['beast_name']}** is already active. "
                "Use `$stophunt` before replacing it.",
                allowed_mentions=self._no_mentions(),
            )
        channel = self._announcement_channel(ctx=ctx)
        if channel is None:
            return await ctx.send("I could not find a channel for Hunt announcements.")
        beast_name = generate_beast_name(f"hunt-{datetime.utcnow().isoformat()}-{channel.id}")
        now = datetime.utcnow()
        async with self.bot.pool.acquire() as conn:
            await conn.execute("TRUNCATE hunt_tracks")
            await conn.execute(
                """
                INSERT INTO hunt_state (
                    id, active, channel_id, tracks, target, beast_name,
                    started_at, expires_at, resummon_at, gather_fails,
                    status_message_id
                )
                VALUES (1, TRUE, $1, 0, $2, $3, $4, $5, NULL, 0, NULL)
                ON CONFLICT (id) DO UPDATE SET
                    active = TRUE,
                    channel_id = EXCLUDED.channel_id,
                    tracks = 0,
                    target = EXCLUDED.target,
                    beast_name = EXCLUDED.beast_name,
                    started_at = EXCLUDED.started_at,
                    expires_at = EXCLUDED.expires_at,
                    resummon_at = NULL,
                    gather_fails = 0,
                    status_message_id = NULL
                """,
                channel.id,
                target,
                beast_name,
                now,
                now + timedelta(hours=72),
            )
        state = await self._state()
        role = self._alert_role(getattr(channel, "guild", None))
        announcement = f"{role.mention}\n" if role else ""
        announcement += (
            f"🐾 **A new Wild Hunt has begun.** Find {target} tracks to draw out "
            f"**{beast_name}**."
        )
        try:
            message = await channel.send(
                content=announcement,
                embed=await self._build_hunt_board(state),
                view=self._alert_view,
                allowed_mentions=self._role_allowed_mentions(),
            )
        except (discord.Forbidden, discord.HTTPException):
            async with self.bot.pool.acquire() as conn:
                await conn.execute("UPDATE hunt_state SET active = FALSE WHERE id = 1")
            return await ctx.send(
                "I could not post the Hunt Board in the configured announcement channel."
            )
        self._board_message = message
        async with self.bot.pool.acquire() as conn:
            await conn.execute(
                "UPDATE hunt_state SET status_message_id = $1 WHERE id = 1",
                message.id,
            )
        if getattr(ctx.channel, "id", None) != channel.id:
            await ctx.send(
                f"Hunt started in {channel.mention}: {message.jump_url}",
                allowed_mentions=self._no_mentions(),
            )

    @commands.command(name="hunt")
    async def hunt(self, ctx):
        await self.ensure_tables()
        state = await self._expire_if_needed(ctx)
        if not state or not state["active"]:
            return await ctx.send("No hunt is active.")
        await self.maybe_resummon(ctx)
        state = await self._state()
        board = await self._refresh_board(state)
        if board is not None:
            return await ctx.send(
                f"🐾 Live Hunt Board: {board.jump_url}",
                delete_after=20,
                allowed_mentions=self._no_mentions(),
            )
        await ctx.send(
            embed=await self._build_hunt_board(state),
            allowed_mentions=self._no_mentions(),
        )

    @commands.command(name="huntalerts")
    @commands.guild_only()
    async def huntalerts(self, ctx, setting: str = None):
        """Opt in to Hunt start/surface alerts without using @everyone."""
        role = self._alert_role(ctx.guild)
        if role is None:
            return await ctx.send(
                f"The **{HUNT_ALERT_ROLE_NAME}** role has not been configured yet."
            )
        me = getattr(ctx.guild, "me", None)
        if role.managed or (me is not None and role >= me.top_role):
            return await ctx.send(
                "I cannot manage the Hunt Alerts role. Move it below my highest role."
            )
        normalized = setting.lower() if setting else None
        if normalized not in (None, "on", "off"):
            return await ctx.send("Use `$huntalerts`, `$huntalerts on`, or `$huntalerts off`.")
        enable = normalized == "on" if normalized else role not in ctx.author.roles
        try:
            if enable and role not in ctx.author.roles:
                await ctx.author.add_roles(role, reason="Hunt alert opt-in")
            elif not enable and role in ctx.author.roles:
                await ctx.author.remove_roles(role, reason="Hunt alert opt-out")
        except discord.HTTPException:
            return await ctx.send("I do not have permission to manage the Hunt Alerts role.")
        await ctx.send("🔔 Hunt alerts are **on**." if enable else "🔕 Hunt alerts are **off**.")

    @commands.command(name="callhunt")
    async def callhunt(self, ctx):
        """Check a submerged beast; resurfacing itself is now automatic."""
        await self.ensure_tables()
        state = await self._expire_if_needed(ctx)
        if not state or not state["active"]:
            return await ctx.send("No hunt is active.")
        if self._surface_running():
            return await ctx.send("The beast has already surfaced — go join the fight!")
        if int(state["tracks"] or 0) < int(state["target"] or 100) or not state["resummon_at"]:
            return await ctx.send("The beast is still being tracked — gather more tracks first.")
        resummon_at = state["resummon_at"]
        if getattr(resummon_at, "tzinfo", None):
            resummon_at = resummon_at.replace(tzinfo=None)
        if datetime.utcnow() < resummon_at:
            stamp = self._utc_timestamp(state["resummon_at"])
            return await ctx.send(
                f"The beast is still submerged. It automatically resurfaces <t:{stamp}:R>."
            )
        if await self.maybe_resummon(ctx):
            channel = self._announcement_channel(ctx=ctx, state=state)
            return await ctx.send(f"🐾 The beast is resurfacing in {channel.mention} now.")
        await ctx.send("The resurfacing has already been claimed; check the Hunt channel.")

    @commands.command(name="stophunt")
    @is_gm()
    async def stophunt(self, ctx):
        """Safely call off an active Hunt without replacing it silently."""
        state = await self._state()
        if not state or not state["active"]:
            return await ctx.send("No hunt is active.")
        if self._fight_active and self._active_join_view is None:
            return await ctx.send("The Hunt battle is already underway and cannot be stopped safely.")
        task = self._surface_task
        if self._active_join_view:
            self._active_join_view.stop()
            await self._active_join_view.close_roster()
        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        async with self.bot.pool.acquire() as conn:
            await conn.execute(
                "UPDATE hunt_state SET active = FALSE, resummon_at = NULL WHERE id = 1"
            )
        closed_state = await self._state()
        await self._refresh_board(closed_state, create_if_missing=False)
        channel = self._announcement_channel(ctx=ctx, state=closed_state)
        if channel:
            await channel.send(
                f"🐾 The Hunt for **{state['beast_name']}** has been called off by a Game Master.",
                allowed_mentions=self._no_mentions(),
            )
        if channel and getattr(channel, "id", None) != getattr(ctx.channel, "id", None):
            await ctx.send("Hunt stopped.")

    @tasks.loop(seconds=60)
    async def hunt_clock(self):
        """Expire and resurface Hunts without waiting for a player command."""
        try:
            state = await self._expire_if_needed()
            if not state or not state["active"] or self._surface_running():
                return
            tracks = int(state["tracks"] or 0)
            target = int(state["target"] or 100)
            if tracks < target:
                return
            if state["resummon_at"]:
                await self.maybe_resummon()
            else:
                # Recovery path for a restart during a live joining window.
                self._schedule_spawn(state)
        except Exception:
            pass

    @hunt_clock.before_loop
    async def before_hunt_clock(self):
        await self.bot.wait_until_ready()

    @commands.Cog.listener()
    async def on_battletower_completion(self, ctx, success, level, level_name, name_value, minion1_name, minion2_name):
        if success:
            await self._maybe_drop_track(ctx, ctx.author.id, 0.12)

    @commands.Cog.listener()
    async def on_adventure_completion(self, ctx, iscompleted):
        if iscompleted:
            await self._maybe_drop_track(ctx, ctx.author.id, 0.08)

    @commands.Cog.listener()
    async def on_icedragon_victory(self, ctx, party_members, stage_name, dragon_level):
        for member in party_members:
            await self._maybe_drop_track(ctx, member.id, 0.20)

    @commands.Cog.listener()
    async def on_raid_favor(self, ctx, participant_ids, success):
        # Tracking rewards participation even when the raid is lost. De-duplicate
        # IDs so a malformed raid payload cannot roll twice for one player.
        for user_id in dict.fromkeys(int(user_id) for user_id in participant_ids):
            await self._maybe_drop_track(ctx, int(user_id), 0.10)


async def setup(bot):
    await bot.add_cog(Hunt(bot))

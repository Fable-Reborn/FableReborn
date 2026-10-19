"""GM-started Hollow Manor raid. One channel, one picture, buttons only."""

import asyncio
import datetime
import json
import logging
import time

import discord
from discord.ext import commands

from utils import random
from utils.checks import is_gm
from utils.i18n import _, locale_doc

from .card import render_manor_card
from .rewards import (
    CRATE_TYPES,
    community_cleared,
    community_struggling,
    reward_for,
    search_goal,
)
from .watch import ensure_watch_role, ping_watchers, set_watching


log = logging.getLogger(__name__)

JOIN_SECONDS = 900
# Seconds before the gate closes -> Night Watch reminder in the manor channel.
GATE_WARNINGS = {
    60: "The gate closes in 1 minute and the Hollow Manor begins. Press **Investigate** or **Keep watch** now.",
    5: "5 seconds! The gate is closing. Investigators, get ready to press **Search** in the hall.",
}
SEARCH_SECONDS = 90
ACTIVE_KEY = "halloween:manor:active"
DAILY_OPEN_LIMIT = 5
LOG_LIST_SIZE = 10
MANOR_CATEGORY_ID = 1403273394853511240
# Must match the event theme key in cogs/profile/themes.py (EVENT_THEMES).
THEME_KEY = "hallowmanor"

STORY = {
    "gate": (
        "The Hollow Manor",
        "A window on the hill is lit. It should not be.\n\n"
        "**Investigate** if you will search the house. **Keep watch** if you will stay at the gate. "
        "You can switch until the gate closes.",
    ),
    "hall": (
        "The Hall",
        "The front door gives. Candle smoke moves against the draft.\n\n"
        "Investigators, press **Search**. The orders appear only for you, and they close with the room.",
    ),
    "cellar": (
        "The Cellar",
        "The stairs go down farther than the house is tall.\n\n"
        "Investigators, press **Search**.",
    ),
    "heart": (
        "The Heart",
        "Something in the dark is counting everyone who came inside.\n\n"
        "Investigators, press **Search**.",
    ),
    "cleared": (
        "The Window Goes Dark",
        "The counting stops. The house lets you leave.",
    ),
    "failed": (
        "The Window Stays Lit",
        "The house noticed the people who left too soon.",
    ),
}

CHOICES = {
    "hall": (
        ("candles", "Follow the candles", "The candles lean toward the cellar stairs."),
        ("portraits", "Check the portraits", "Every portrait is looking at the door you came through."),
        ("left", "Take the left door", "The left door opens onto a cold stair."),
    ),
    "cellar": (
        ("descend", "Descend", "The steps keep going after they should have stopped."),
        ("listen", "Listen at the wall", "Something on the other side counts under its breath."),
        ("match", "Light a match", "The match shows a handprint that is still warm."),
    ),
    "heart": (
        ("speak", "Speak", "You tell it how many of you came. It already knew."),
        ("lantern", "Raise a lantern", "The light reaches a window that has no glass."),
        ("closer", "Step closer", "The floor is soft, like ash over wood."),
    ),
}

SEARCH_PHASES = ("hall", "cellar", "heart")


def _decode(value):
    if value is None:
        return None
    if isinstance(value, bytes):
        return value.decode()
    return str(value)


class ManorButton(discord.ui.Button):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    @property
    def manor(self):
        return None


class InvestigateButton(discord.ui.Button):
    def __init__(self):
        super().__init__(
            label="Investigate",
            emoji="🕯️",
            style=discord.ButtonStyle.primary,
            custom_id="manor:investigate",
        )

    async def callback(self, interaction: discord.Interaction):
        cog = interaction.client.get_cog("HalloweenManor")
        if cog is None:
            return await interaction.response.send_message("The manor is not open.", ephemeral=True)
        await cog.handle_join(interaction, "active")


class WatchButton(discord.ui.Button):
    def __init__(self):
        super().__init__(
            label="Keep watch",
            emoji="👁️",
            style=discord.ButtonStyle.secondary,
            custom_id="manor:watch",
        )

    async def callback(self, interaction: discord.Interaction):
        cog = interaction.client.get_cog("HalloweenManor")
        if cog is None:
            return await interaction.response.send_message("The manor is not open.", ephemeral=True)
        await cog.handle_join(interaction, "passive")


class SearchButton(discord.ui.Button):
    def __init__(self):
        super().__init__(
            label="Search",
            emoji="🔦",
            style=discord.ButtonStyle.primary,
            custom_id="manor:search",
        )

    async def callback(self, interaction: discord.Interaction):
        cog = interaction.client.get_cog("HalloweenManor")
        if cog is None:
            return await interaction.response.send_message("The manor is not open.", ephemeral=True)
        await cog.open_orders(interaction)


class RewardButton(discord.ui.Button):
    def __init__(self):
        super().__init__(
            label="My reward",
            emoji="💀",
            style=discord.ButtonStyle.success,
            custom_id="manor:reward",
        )

    async def callback(self, interaction: discord.Interaction):
        cog = interaction.client.get_cog("HalloweenManor")
        if cog is None:
            return await interaction.response.send_message("The manor is not open.", ephemeral=True)
        await cog.show_reward(interaction)


class ChoiceButton(discord.ui.Button):
    def __init__(self, phase: str, key: str, label: str):
        super().__init__(label=label, style=discord.ButtonStyle.secondary)
        self.phase = phase
        self.choice_key = key

    async def callback(self, interaction: discord.Interaction):
        cog = interaction.client.get_cog("HalloweenManor")
        if cog is None:
            return await interaction.response.send_message("The manor is not open.", ephemeral=True)
        await cog.choose(interaction, self.phase, self.choice_key)


class ManorBoardView(discord.ui.View):
    def __init__(self, phase: str):
        super().__init__(timeout=None)
        if phase == "gate":
            self.add_item(InvestigateButton())
            self.add_item(WatchButton())
        elif phase in SEARCH_PHASES:
            self.add_item(SearchButton())
        else:
            self.add_item(RewardButton())


class ChoiceView(discord.ui.View):
    def __init__(self, phase: str, timeout: float):
        super().__init__(timeout=max(5.0, timeout))
        for key, label, _outcome in CHOICES[phase]:
            self.add_item(ChoiceButton(phase, key, label))


class HalloweenManor(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.raids = {}
        self.open_lock = asyncio.Lock()

    async def cog_load(self):
        self.bot.add_view(ManorBoardView("results"))
        self.bot.add_view(ManorBoardView("gate"))
        self.bot.add_view(ManorBoardView("hall"))
        await self._ensure_log_tables()
        await self._resume_raids()

    async def _ensure_log_tables(self):
        try:
            await self.bot.pool.execute(
                """
                CREATE TABLE IF NOT EXISTS hollow_manor_runs (
                    id SERIAL PRIMARY KEY,
                    guild_id BIGINT NOT NULL,
                    channel_id BIGINT NOT NULL,
                    opened_by BIGINT NOT NULL,
                    opened_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    settled_at TIMESTAMPTZ,
                    cleared BOOLEAN,
                    progress INTEGER,
                    goal INTEGER,
                    closed_by BIGINT,
                    closed_at TIMESTAMPTZ
                );
                CREATE INDEX IF NOT EXISTS hollow_manor_runs_guild_opened
                    ON hollow_manor_runs (guild_id, opened_at);
                CREATE TABLE IF NOT EXISTS hollow_manor_participants (
                    run_id INTEGER NOT NULL REFERENCES hollow_manor_runs (id) ON DELETE CASCADE,
                    user_id BIGINT NOT NULL,
                    role TEXT NOT NULL,
                    joined_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    rooms INTEGER,
                    bones INTEGER,
                    bags INTEGER,
                    crate TEXT,
                    theme BOOLEAN,
                    PRIMARY KEY (run_id, user_id)
                );
                """
            )
        except Exception:
            log.exception("Failed to create the Hollow Manor log tables")

    async def _opens_today(self, guild_id: int) -> int:
        return await self.bot.pool.fetchval(
            """
            SELECT COUNT(*) FROM hollow_manor_runs
            WHERE guild_id = $1
              AND opened_at >= date_trunc('day', NOW() AT TIME ZONE 'UTC') AT TIME ZONE 'UTC';
            """,
            guild_id,
        )

    @staticmethod
    def _next_reset() -> int:
        now = datetime.datetime.now(datetime.timezone.utc)
        tomorrow = (now + datetime.timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        return int(tomorrow.timestamp())

    async def _log_join(self, raid, user_id: int, role: str):
        if not raid.get("run_id"):
            return
        try:
            await self.bot.pool.execute(
                """
                INSERT INTO hollow_manor_participants (run_id, user_id, role)
                VALUES ($1, $2, $3)
                ON CONFLICT (run_id, user_id) DO UPDATE SET role = EXCLUDED.role;
                """,
                raid["run_id"],
                user_id,
                role,
            )
        except Exception:
            log.exception("Failed to log a Hollow Manor join")

    async def _log_settle(self, raid):
        if not raid.get("run_id"):
            return
        rows = []
        for user_id, receipt in raid["receipts"].items():
            rows.append(
                (
                    raid["run_id"],
                    user_id,
                    raid["roster"].get(user_id, receipt.get("role", "passive")),
                    len(raid["searches"].get(user_id, ())),
                    receipt["bones"],
                    receipt["bags"],
                    self._receipt_crate(receipt),
                    bool(receipt["theme"]),
                )
            )
        try:
            async with self.bot.pool.acquire() as conn:
                async with conn.transaction():
                    await conn.execute(
                        """
                        UPDATE hollow_manor_runs
                        SET settled_at = COALESCE(settled_at, NOW()), cleared = $2, progress = $3, goal = $4
                        WHERE id = $1;
                        """,
                        raid["run_id"],
                        bool(raid.get("cleared")),
                        self._progress(raid),
                        self._goal(raid),
                    )
                    if rows:
                        await conn.executemany(
                            """
                            INSERT INTO hollow_manor_participants
                                (run_id, user_id, role, rooms, bones, bags, crate, theme)
                            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                            ON CONFLICT (run_id, user_id) DO UPDATE SET
                                role = EXCLUDED.role, rooms = EXCLUDED.rooms, bones = EXCLUDED.bones,
                                bags = EXCLUDED.bags, crate = EXCLUDED.crate, theme = EXCLUDED.theme;
                            """,
                            rows,
                        )
        except Exception:
            log.exception("Failed to log Hollow Manor rewards")

    async def _log_close(self, raid, closed_by: int):
        if not raid.get("run_id"):
            return
        try:
            await self.bot.pool.execute(
                "UPDATE hollow_manor_runs SET closed_by = $2, closed_at = NOW() WHERE id = $1;",
                raid["run_id"],
                closed_by,
            )
        except Exception:
            log.exception("Failed to log a Hollow Manor close")

    async def cog_unload(self):
        for raid in list(self.raids.values()):
            task = raid.get("task")
            if task and not task.done():
                task.cancel()

    def _halloween_enabled(self) -> bool:
        flags = getattr(self.bot, "event_flags", None) or {}
        return bool(flags.get("halloween", False))

    def _raid_for(self, guild_id: int):
        return self.raids.get(guild_id)

    def _investigators(self, raid) -> list[int]:
        return [user_id for user_id, role in raid["roster"].items() if role == "active"]

    def _watchers(self, raid) -> list[int]:
        return [user_id for user_id, role in raid["roster"].items() if role == "passive"]

    def _progress(self, raid) -> int:
        return sum(len(rooms) for rooms in raid["searches"].values())

    def _goal(self, raid) -> int:
        return search_goal(len(self._investigators(raid)))

    def _art_phase(self, raid) -> str:
        if raid["phase"] == "results":
            return "cleared" if raid.get("cleared") else "heart"
        return raid["phase"]

    def _export(self, raid) -> dict:
        return {
            "guild_id": raid["guild_id"],
            "run_id": raid.get("run_id"),
            "channel_id": raid["channel_id"],
            "message_id": raid["message_id"],
            "phase": raid["phase"],
            "deadline": raid["deadline"],
            "roster": {str(user_id): role for user_id, role in raid["roster"].items()},
            "searches": {str(user_id): sorted(rooms) for user_id, rooms in raid["searches"].items()},
            "paid": raid["paid"],
            "cleared": raid.get("cleared", False),
            "warned": sorted(raid.get("warned", ())),
            "receipts": {str(user_id): receipt for user_id, receipt in raid["receipts"].items()},
        }

    def _import(self, payload: dict) -> dict:
        return {
            "guild_id": int(payload["guild_id"]),
            "run_id": payload.get("run_id"),
            "channel_id": int(payload["channel_id"]),
            "message_id": int(payload["message_id"]),
            "phase": payload["phase"],
            "deadline": float(payload["deadline"]),
            "roster": {int(user_id): role for user_id, role in payload.get("roster", {}).items()},
            "searches": {
                int(user_id): set(rooms) for user_id, rooms in payload.get("searches", {}).items()
            },
            "paid": bool(payload.get("paid")),
            "cleared": bool(payload.get("cleared")),
            "warned": set(payload["warned"]) if isinstance(payload.get("warned"), list) else set(),
            "receipts": {int(user_id): receipt for user_id, receipt in payload.get("receipts", {}).items()},
            "lock": asyncio.Lock(),
            "wake": asyncio.Event(),
            "wake_reason": None,
            "dirty": False,
            "refresh_task": None,
            "task": None,
            "message": None,
        }

    async def _save(self, raid):
        try:
            guild_id = raid["guild_id"]
            await self.bot.redis.set(f"halloween:manor:{guild_id}", json.dumps(self._export(raid)))
            await self.bot.redis.sadd(ACTIVE_KEY, str(guild_id))
        except Exception:
            log.exception("Failed to save Hollow Manor state")

    async def _forget(self, guild_id: int):
        self.raids.pop(guild_id, None)
        try:
            await self.bot.redis.delete(f"halloween:manor:{guild_id}")
            await self.bot.redis.srem(ACTIVE_KEY, str(guild_id))
        except Exception:
            log.exception("Failed to clear Hollow Manor state")

    async def _resume_raids(self):
        try:
            raw_ids = await self.bot.redis.smembers(ACTIVE_KEY)
        except Exception:
            log.exception("Failed to resume Hollow Manor raids")
            return
        for raw_id in raw_ids or []:
            guild_id = int(_decode(raw_id))
            try:
                raw = await self.bot.redis.get(f"halloween:manor:{guild_id}")
                if not raw:
                    continue
                raid = self._import(json.loads(_decode(raw)))
                channel = self.bot.get_channel(raid["channel_id"])
                if channel is None:
                    channel = await self.bot.fetch_channel(raid["channel_id"])
                raid["message"] = await channel.fetch_message(raid["message_id"])
                self.raids[guild_id] = raid
                if raid["phase"] != "results":
                    raid["task"] = asyncio.create_task(self._director(guild_id))
                elif not raid["paid"]:
                    raid["task"] = asyncio.create_task(self._conclude(guild_id))
            except Exception:
                log.exception("Dropping unrecoverable Hollow Manor raid %s", guild_id)
                await self._forget(guild_id)

    def _view_for(self, phase: str) -> ManorBoardView:
        return ManorBoardView(phase if phase in {"gate", *SEARCH_PHASES} else "results")

    def _embed(self, raid) -> discord.Embed:
        phase = raid["phase"]
        if phase == "results":
            title, description = STORY["cleared" if raid.get("cleared") else "failed"]
        else:
            title, description = STORY[phase]
        progress = self._progress(raid)
        goal = self._goal(raid)
        remaining = max(0, int(raid["deadline"] - time.time()))
        embed = discord.Embed(title=title, description=description, color=0xE4572E)
        embed.add_field(name="Investigators", value=str(len(self._investigators(raid))), inline=True)
        embed.add_field(name="Watchers", value=str(len(self._watchers(raid))), inline=True)
        embed.add_field(name="The house", value=f"{progress}/{goal}", inline=True)
        if phase == "results":
            embed.set_footer(text="Rewards were sent in private. Press My reward if yours did not arrive.")
        elif phase == "gate":
            embed.set_footer(text=f"The gate closes in {remaining}s. Chat in this channel is closed.")
        else:
            embed.set_footer(text=f"This room closes in {remaining}s. One search each.")
        embed.set_image(url="attachment://manor-card.png")
        return embed

    async def _edit_board(self, guild_id: int):
        raid = self.raids.get(guild_id)
        message = raid.get("message") if raid else None
        if raid is None or message is None:
            return
        card = await asyncio.to_thread(
            render_manor_card, self._art_phase(raid), self._progress(raid), self._goal(raid)
        )
        attachment = discord.File(card, filename="manor-card.png")
        try:
            await message.edit(embed=self._embed(raid), attachments=[attachment], view=self._view_for(raid["phase"]))
        except discord.HTTPException:
            log.exception("Failed to update the Hollow Manor board")

    def _request_refresh(self, guild_id: int):
        raid = self.raids.get(guild_id)
        if raid is None or raid["phase"] == "results":
            return
        raid["dirty"] = True
        task = raid.get("refresh_task")
        if task is None or task.done():
            raid["refresh_task"] = asyncio.create_task(self._refresh_soon(guild_id))

    async def _refresh_soon(self, guild_id: int):
        await asyncio.sleep(1.5)
        raid = self.raids.get(guild_id)
        if raid is None or not raid.get("dirty"):
            return
        raid["dirty"] = False
        await self._edit_board(guild_id)

    async def _sleep_or_wake(self, raid, seconds: float) -> str:
        if raid["wake"].is_set():
            raid["wake"].clear()
            return raid.pop("wake_reason", None) or "skip"
        if seconds <= 0:
            return "timeout"
        try:
            await asyncio.wait_for(raid["wake"].wait(), timeout=seconds)
        except asyncio.TimeoutError:
            return "timeout"
        raid["wake"].clear()
        return raid.pop("wake_reason", None) or "skip"

    def _wake(self, raid, reason: str):
        raid["wake_reason"] = reason
        raid["wake"].set()

    @staticmethod
    def _next_warning(raid, now: float):
        if raid["phase"] != "gate":
            return None
        sent = raid.setdefault("warned", set())
        for seconds in sorted(GATE_WARNINGS, reverse=True):
            if seconds not in sent and raid["deadline"] - seconds > now:
                return seconds
        return None

    async def _warn_gate(self, raid, seconds):
        raid.setdefault("warned", set()).add(seconds)
        await self._save(raid)
        message = raid.get("message")
        if message is None:
            return
        text = GATE_WARNINGS[seconds]
        await ping_watchers(message.channel, text)

    async def _director(self, guild_id: int):
        try:
            while True:
                raid = self.raids.get(guild_id)
                if raid is None or raid["phase"] == "results":
                    return
                now = time.time()
                warning = self._next_warning(raid, now)
                if warning is not None:
                    reason = await self._sleep_or_wake(raid, raid["deadline"] - warning - now)
                    if reason == "timeout":
                        await self._warn_gate(raid, warning)
                        continue
                else:
                    reason = await self._sleep_or_wake(raid, raid["deadline"] - now)
                if reason == "close":
                    return
                if reason == "end" or raid["phase"] == "heart":
                    await self._conclude(guild_id)
                    return
                await self._advance(guild_id)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("Hollow Manor director stopped")

    async def _advance(self, guild_id: int):
        raid = self.raids.get(guild_id)
        if raid is None:
            return
        async with raid["lock"]:
            if raid["phase"] == "gate":
                raid["phase"] = "hall"
            elif raid["phase"] == "hall":
                raid["phase"] = "cellar"
            elif raid["phase"] == "cellar":
                raid["phase"] = "heart"
            else:
                return
            raid["deadline"] = time.time() + SEARCH_SECONDS
            raid["dirty"] = False
            if raid["wake"].is_set() and raid.get("wake_reason") == "skip":
                raid["wake"].clear()
                raid["wake_reason"] = None
            phase = raid["phase"]
            investigators = list(self._investigators(raid))
        await self._save(raid)
        await self._edit_board(guild_id)
        await self._nudge(investigators, phase)

    async def _nudge(self, user_ids, phase: str):
        title = STORY[phase][0]
        text = _(
            "The {room} is open. Go back to the manor channel and press **Search**."
        ).format(room=title.lower())

        async def send_one(user_id):
            try:
                user = self.bot.get_user(user_id) or await self.bot.fetch_user(user_id)
                await user.send(text)
            except discord.HTTPException:
                return

        await asyncio.gather(*(send_one(user_id) for user_id in user_ids), return_exceptions=True)

    async def handle_join(self, interaction: discord.Interaction, role: str):
        if interaction.guild is None:
            return await interaction.response.send_message("The manor is not open here.", ephemeral=True)
        raid = self._raid_for(interaction.guild.id)
        if raid is None or interaction.channel_id != raid["channel_id"]:
            return await interaction.response.send_message("The manor is not open here.", ephemeral=True)
        if raid["phase"] != "gate":
            return await interaction.response.send_message("The gate has already shut.", ephemeral=True)
        has_character = await self.bot.pool.fetchval(
            'SELECT 1 FROM profile WHERE "user"=$1;', interaction.user.id
        )
        if not has_character:
            return await interaction.response.send_message("You need a character to enter the manor.", ephemeral=True)
        async with raid["lock"]:
            if raid["roster"].get(interaction.user.id) == role:
                if role == "active":
                    text = _("You are already investigating. Press **Search** when the house opens.")
                else:
                    text = _("You are already keeping watch at the gate.")
                return await interaction.response.send_message(text, ephemeral=True)
            raid["roster"][interaction.user.id] = role
        await self._save(raid)
        await self._log_join(raid, interaction.user.id, role)
        self._request_refresh(interaction.guild.id)
        if role == "active":
            text = _("You will investigate. Press **Search** when the house opens. You can still switch to **Keep watch**.")
        else:
            text = _("You will keep watch at the gate. You can still switch to **Investigate** before the gate closes.")
        await interaction.response.send_message(text, ephemeral=True)

    async def open_orders(self, interaction: discord.Interaction):
        if interaction.guild is None:
            return await interaction.response.send_message("The manor is not open here.", ephemeral=True)
        raid = self._raid_for(interaction.guild.id)
        if raid is None or interaction.channel_id != raid["channel_id"]:
            return await interaction.response.send_message("The manor is not open here.", ephemeral=True)
        phase = raid["phase"]
        if phase == "gate":
            return await interaction.response.send_message(
                "The house has not opened yet. Press **Search** when the hall opens.", ephemeral=True
            )
        if phase not in SEARCH_PHASES:
            return await interaction.response.send_message("That room has already closed.", ephemeral=True)
        role = raid["roster"].get(interaction.user.id)
        if role != "active":
            return await interaction.response.send_message(
                "You stayed at the gate. The door does not open for watchers.", ephemeral=True
            )
        if phase in raid["searches"].get(interaction.user.id, ()):
            return await interaction.response.send_message("You already chose in this room.", ephemeral=True)
        title, _description = STORY[phase]
        embed = discord.Embed(
            title=title,
            description=_("Choose once. The buttons die when the room closes."),
            color=0xE4572E,
        )
        remaining = raid["deadline"] - time.time()
        # Keep this reply image-free: Discord fails the click if the bot has not answered within 3 seconds.
        await interaction.response.send_message(
            embed=embed,
            view=ChoiceView(phase, remaining),
            ephemeral=True,
        )

    async def choose(self, interaction: discord.Interaction, phase: str, choice_key: str):
        if interaction.guild is None:
            return await interaction.response.send_message("The manor is not open here.", ephemeral=True)
        raid = self._raid_for(interaction.guild.id)
        if raid is None:
            return await interaction.response.send_message("That room has already closed.", ephemeral=True)
        outcome = next(text for key, _label, text in CHOICES[phase] if key == choice_key)
        async with raid["lock"]:
            if raid["phase"] != phase:
                return await interaction.response.edit_message(
                    content="The door has already shut.", embed=None, attachments=[], view=None
                )
            found = raid["searches"].setdefault(interaction.user.id, set())
            if phase in found:
                return await interaction.response.edit_message(
                    content="You already chose in this room.", embed=None, attachments=[], view=None
                )
            found.add(phase)
        await self._save(raid)
        self._request_refresh(interaction.guild.id)
        await interaction.response.edit_message(content=outcome, embed=None, attachments=[], view=None)

    async def show_reward(self, interaction: discord.Interaction):
        if interaction.guild is None:
            return await interaction.response.send_message("The manor is not open here.", ephemeral=True)
        raid = self._raid_for(interaction.guild.id)
        if raid is None or not raid["paid"]:
            return await interaction.response.send_message("The house has not settled yet.", ephemeral=True)
        receipt = raid["receipts"].get(interaction.user.id)
        if receipt is None:
            return await interaction.response.send_message("You were not at the manor.", ephemeral=True)
        await interaction.response.send_message(self._receipt_text(receipt), ephemeral=True)

    def _receipt_text(self, receipt: dict) -> str:
        lines = [receipt["summary"], f"💀 Bones: **{receipt['bones']}**"]
        if receipt["bags"]:
            lines.append(f"🛍️ Trick-or-treat bags: **{receipt['bags']}**")
        crate = self._receipt_crate(receipt)
        if crate:
            lines.append(f"📦 {crate.capitalize()} crate: **1**")
        if receipt["theme"]:
            lines.append(f"🎃 Profile theme: **The Last Lantern**. Equip it with `$prpg theme {THEME_KEY}`.")
        elif receipt.get("theme_owned"):
            lines.append("You already own The Last Lantern, so the house paid extra bones instead.")
        return "\n".join(lines)

    @staticmethod
    def _receipt_crate(receipt: dict):
        crate = receipt.get("crate")
        if crate in CRATE_TYPES:
            return crate
        # Receipts saved before crate types existed only recorded an uncommon crate.
        return "uncommon" if receipt.get("uncommon") else None

    async def _conclude(self, guild_id: int):
        raid = self.raids.get(guild_id)
        if raid is None or raid["paid"] or raid.get("concluding"):
            return
        async with raid["lock"]:
            if raid["paid"] or raid.get("concluding"):
                return
            raid["concluding"] = True
            investigators = len(self._investigators(raid))
            progress = self._progress(raid)
            goal = self._goal(raid)
            cleared = community_cleared(progress, goal, investigators)
            struggling = community_struggling(progress, goal)
            user_ids = list(raid["roster"])
            raid["cleared"] = cleared
            raid["phase"] = "results"
            raid["deadline"] = time.time()
            raid["dirty"] = False
        owned = set()
        if user_ids:
            rows = await self.bot.pool.fetch(
                "SELECT user_id FROM profile_theme_unlocks WHERE theme_key=$1 AND user_id = ANY($2::bigint[]);",
                THEME_KEY,
                user_ids,
            )
            owned = {row["user_id"] for row in rows}
        grants = []
        for user_id, role in list(raid["roster"].items()):
            if user_id in raid["receipts"]:
                receipt = raid["receipts"][user_id]
                if not receipt.get("applied"):
                    await self._pay(user_id, receipt)
                    receipt["applied"] = True
                    await self._save(raid)
                    grants.append((user_id, receipt))
                continue
            rooms = len(raid["searches"].get(user_id, ()))
            spec = reward_for(
                joined_as=role,
                rooms=rooms,
                cleared=cleared,
                struggling=struggling,
                owns_theme=user_id in owned,
            )
            bags = 1 if random.random() < spec.bag_chance else 0
            if bags and random.random() < spec.extra_bag_chance:
                bags += 1
            crate = random.choice(CRATE_TYPES) if random.random() < spec.crate_chance else None
            theme = (not (user_id in owned)) and random.random() < spec.theme_chance
            receipt = {
                "summary": spec.summary,
                "bones": spec.bones,
                "bags": bags,
                "crate": crate,
                "theme": bool(theme),
                "theme_owned": user_id in owned and rooms == 3 and spec.role == "active" and not struggling,
                "role": spec.role,
                "applied": False,
            }
            raid["receipts"][user_id] = receipt
            await self._save(raid)
            await self._pay(user_id, receipt)
            receipt["applied"] = True
            await self._save(raid)
            grants.append((user_id, receipt))
        raid["paid"] = True
        await self._save(raid)
        await self._log_settle(raid)
        await self._edit_board(guild_id)
        await self._send_receipts(grants)

    async def _settle(self, guild_id: int):
        raid = self.raids.get(guild_id)
        if raid is None:
            return
        task = raid.get("task")
        if task is not None and not task.done():
            self._wake(raid, "end")
            return
        raid["concluding"] = False
        raid["task"] = asyncio.create_task(self._conclude(guild_id))

    async def _pay(self, user_id: int, receipt: dict):
        async with self.bot.pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    '''
                    UPDATE profile
                    SET bones = COALESCE(bones, 0) + $1,
                        trickortreat = COALESCE(trickortreat, 0) + $2
                    WHERE "user" = $3;
                    ''',
                    receipt["bones"],
                    receipt["bags"],
                    user_id,
                )
                crate = self._receipt_crate(receipt)
                if crate:
                    column = f"crates_{crate}"
                    await conn.execute(
                        f'UPDATE profile SET "{column}" = COALESCE("{column}", 0) + 1 WHERE "user" = $1;',
                        user_id,
                    )
        if receipt["theme"]:
            from cogs.profile.theme_unlocks import grant_event_theme

            await grant_event_theme(self.bot.pool, user_id, THEME_KEY, "hollow_manor")

    async def _send_receipts(self, grants):
        async def send_one(user_id, receipt):
            try:
                user = self.bot.get_user(user_id) or await self.bot.fetch_user(user_id)
                await user.send(self._receipt_text(receipt))
            except discord.HTTPException:
                return

        await asyncio.gather(*(send_one(user_id, receipt) for user_id, receipt in grants), return_exceptions=True)

    @commands.group(name="manor", invoke_without_command=True, brief=_("The Hollow Manor"))
    @locale_doc
    async def manor(self, ctx):
        _("""The Hollow Manor is a GM-started Halloween raid in its own channel.

        Players join with the buttons on the manor picture. Investigators search each room.
        Watchers stay at the gate and receive a smaller bone reward.
        """)
        if self._raid_for(ctx.guild.id) if ctx.guild else None:
            return await self.manor_status(ctx)
        await ctx.send(
            _("The Hollow Manor opens when a GM uses `{prefix}manor open` during Halloween.").format(
                prefix=ctx.clean_prefix
            )
        )

    @is_gm()
    @manor.command(name="open")
    async def manor_open(self, ctx):
        if ctx.guild is None:
            return await ctx.send("Open the manor from a server channel.")
        if not self._halloween_enabled():
            return await ctx.send("Enable the Halloween event before opening the manor.")
        async with self.open_lock:
            await self._open_manor(ctx)

    async def _open_manor(self, ctx):
        if self._raid_for(ctx.guild.id):
            return await ctx.send("A manor is already open in this server.")
        opened = await self._opens_today(ctx.guild.id)
        if opened >= DAILY_OPEN_LIMIT:
            return await ctx.send(
                f"The manor has already opened {opened}/{DAILY_OPEN_LIMIT} times today. "
                f"The limit resets <t:{self._next_reset()}:R>."
            )
        names = {channel.name for channel in ctx.guild.text_channels}
        channel_name = "「👻」hallow-manor"
        suffix = 2
        while channel_name in names:
            channel_name = f"「👻」hallow-manor-{suffix}"
            suffix += 1
        overwrites = {
            ctx.guild.default_role: discord.PermissionOverwrite(
                view_channel=True, send_messages=False, add_reactions=False
            ),
            ctx.guild.me: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                embed_links=True,
                attach_files=True,
                manage_channels=True,
                manage_messages=True,
                read_message_history=True,
            ),
        }
        category = ctx.guild.get_channel(MANOR_CATEGORY_ID)
        if not isinstance(category, discord.CategoryChannel):
            return await ctx.send(
                f"I could not find the manor category ({MANOR_CATEGORY_ID}) in this server, so the manor did not open."
            )
        try:
            channel = await ctx.guild.create_text_channel(
                name=channel_name,
                category=category,
                overwrites=overwrites,
                topic="The Hollow Manor. Use the buttons. Chat is closed.",
                reason=f"Hollow Manor opened by {ctx.author}",
            )
        except discord.Forbidden:
            return await ctx.send("I need permission to create a channel for the manor.")
        try:
            run_id = await self.bot.pool.fetchval(
                "INSERT INTO hollow_manor_runs (guild_id, channel_id, opened_by) VALUES ($1, $2, $3) RETURNING id;",
                ctx.guild.id,
                channel.id,
                ctx.author.id,
            )
        except Exception:
            log.exception("Failed to record a Hollow Manor opening")
            try:
                await channel.delete(reason="Hollow Manor log could not be written")
            except discord.HTTPException:
                pass
            return await ctx.send("I could not write the manor log, so the manor did not open.")
        raid = self._import(
            {
                "guild_id": ctx.guild.id,
                "run_id": run_id,
                "channel_id": channel.id,
                "message_id": 0,
                "phase": "gate",
                "deadline": time.time() + JOIN_SECONDS,
                "roster": {},
                "searches": {},
                "paid": False,
                "cleared": False,
                "receipts": {},
            }
        )
        card = await asyncio.to_thread(render_manor_card, "gate", 0, 1)
        role = await ensure_watch_role(ctx.guild)
        minutes = JOIN_SECONDS // 60
        await ping_watchers(
            channel,
            f"The Hollow Manor is open. The gate closes in {minutes} minutes.",
        )
        message = await channel.send(
            embed=self._embed(raid),
            file=discord.File(card, filename="manor-card.png"),
            view=self._view_for("gate"),
        )
        raid["message_id"] = message.id
        raid["message"] = message
        self.raids[ctx.guild.id] = raid
        await self._save(raid)
        raid["task"] = asyncio.create_task(self._director(ctx.guild.id))
        text = _("The manor is open: {channel}").format(channel=channel.mention)
        text += f" Opens today: {opened + 1}/{DAILY_OPEN_LIMIT}."
        if role is None:
            text += " I could not find or create Night Watch, so nobody was pinged."
        await ctx.send(text)

    @manor.command(name="watch")
    async def manor_watch(self, ctx):
        if ctx.guild is None:
            return await ctx.send("Opt in from a server channel.")
        await ctx.send(await set_watching(ctx.author, True))

    @manor.command(name="unwatch")
    async def manor_unwatch(self, ctx):
        if ctx.guild is None:
            return await ctx.send("Opt out from a server channel.")
        await ctx.send(await set_watching(ctx.author, False))

    @manor.command(name="status")
    async def manor_status(self, ctx):
        if ctx.guild is None or self._raid_for(ctx.guild.id) is None:
            return await ctx.send("No manor is open in this server.")
        raid = self._raid_for(ctx.guild.id)
        channel = ctx.guild.get_channel(raid["channel_id"])
        await ctx.send(
            embed=discord.Embed(
                title="Hollow Manor",
                description=(
                    f"Phase: **{raid['phase']}**\n"
                    f"Channel: {channel.mention if channel else raid['channel_id']}\n"
                    f"Investigators: **{len(self._investigators(raid))}**\n"
                    f"Watchers: **{len(self._watchers(raid))}**\n"
                    f"The house: **{self._progress(raid)}/{self._goal(raid)}**"
                ),
                color=0xE4572E,
            )
        )

    @is_gm()
    @manor.command(name="skip")
    async def manor_skip(self, ctx):
        raid = self._raid_for(ctx.guild.id) if ctx.guild else None
        if raid is None or raid["phase"] == "results":
            return await ctx.send("There is no open room to skip.")
        task = raid.get("task")
        if task is None or task.done():
            raid["task"] = asyncio.create_task(self._director(ctx.guild.id))
        self._wake(raid, "skip")
        await ctx.send("The manor moves on.")

    @is_gm()
    @manor.command(name="end")
    async def manor_end(self, ctx):
        raid = self._raid_for(ctx.guild.id) if ctx.guild else None
        if raid is None or raid["paid"]:
            return await ctx.send("There is no manor to end.")
        await self._settle(ctx.guild.id)
        await ctx.send("The manor is settling.")

    @is_gm()
    @manor.command(name="close")
    async def manor_close(self, ctx):
        if ctx.guild is None:
            return
        raid = self._raid_for(ctx.guild.id)
        if raid is None:
            return await ctx.send("There is no manor channel to close.")
        if not raid["paid"]:
            await self._settle(ctx.guild.id)
        task = raid.get("task")
        if task is not None and not task.done():
            try:
                await asyncio.wait_for(task, timeout=180)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                pass
        channel = ctx.guild.get_channel(raid["channel_id"])
        self._wake(raid, "close")
        await self._log_close(raid, ctx.author.id)
        await self._forget(ctx.guild.id)
        if channel is not None:
            try:
                await channel.delete(reason=f"Hollow Manor closed by {ctx.author}")
            except discord.HTTPException:
                return await ctx.send("The raid is cleared, but I could not delete the channel.")
        await ctx.send("The manor channel is closed.")

    @is_gm()
    @manor.command(name="log")
    async def manor_log(self, ctx, run_id: int = None):
        """[GM only] Lists recent manors, or shows one manor's players and rewards."""
        if ctx.guild is None:
            return await ctx.send("Use the manor log from a server channel.")
        if run_id is None:
            return await self._send_run_list(ctx)
        await self._send_run_detail(ctx, run_id)

    @staticmethod
    def _stamp(value, style: str = "f") -> str:
        if value is None:
            return "—"
        return f"<t:{int(value.timestamp())}:{style}>"

    async def _send_run_list(self, ctx):
        runs = await self.bot.pool.fetch(
            """
            SELECT r.*,
                   COUNT(p.user_id) FILTER (WHERE p.role = 'active') AS investigators,
                   COUNT(p.user_id) FILTER (WHERE p.role = 'passive') AS watchers
            FROM hollow_manor_runs r
            LEFT JOIN hollow_manor_participants p ON p.run_id = r.id
            WHERE r.guild_id = $1
            GROUP BY r.id
            ORDER BY r.opened_at DESC
            LIMIT $2;
            """,
            ctx.guild.id,
            LOG_LIST_SIZE,
        )
        opened = await self._opens_today(ctx.guild.id)
        lines = [
            f"Opened today: **{opened}/{DAILY_OPEN_LIMIT}**. Resets <t:{self._next_reset()}:R>.",
            "",
        ]
        if not runs:
            lines.append("No manors have been opened in this server yet.")
        for run in runs:
            if run["settled_at"] is None:
                result = "In progress"
            elif run["cleared"]:
                result = f"Cleared ({run['progress']}/{run['goal']})"
            else:
                result = f"Not cleared ({run['progress']}/{run['goal']})"
            closed = (
                f"closed by <@{run['closed_by']}> {self._stamp(run['closed_at'], 't')}"
                if run["closed_at"]
                else "not closed"
            )
            lines.append(
                f"**#{run['id']}** · opened by <@{run['opened_by']}> {self._stamp(run['opened_at'])}\n"
                f"{run['investigators']} investigators · {run['watchers']} watchers · {result} · {closed}"
            )
        embed = discord.Embed(title="Hollow Manor log", description="\n".join(lines)[:4096], color=0xE4572E)
        embed.set_footer(text=f"{ctx.clean_prefix}manor log <id> shows that manor's players and rewards.")
        await ctx.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())

    async def _send_run_detail(self, ctx, run_id: int):
        run = await self.bot.pool.fetchrow(
            "SELECT * FROM hollow_manor_runs WHERE id = $1 AND guild_id = $2;", run_id, ctx.guild.id
        )
        if run is None:
            return await ctx.send(f"There is no manor #{run_id} in this server's log.")
        players = await self.bot.pool.fetch(
            "SELECT * FROM hollow_manor_participants WHERE run_id = $1 ORDER BY joined_at;", run_id
        )
        if run["settled_at"] is None:
            result = "In progress"
        else:
            result = "Cleared" if run["cleared"] else "Not cleared"
            result += f" ({run['progress']}/{run['goal']} searches)"
        header = discord.Embed(title=f"Hollow Manor #{run_id}", color=0xE4572E)
        header.add_field(name="Opened by", value=f"<@{run['opened_by']}>", inline=True)
        header.add_field(name="Opened", value=self._stamp(run["opened_at"]), inline=True)
        header.add_field(name="Settled", value=self._stamp(run["settled_at"]), inline=True)
        header.add_field(
            name="Closed by",
            value=f"<@{run['closed_by']}>" if run["closed_by"] else "—",
            inline=True,
        )
        header.add_field(name="Closed", value=self._stamp(run["closed_at"]), inline=True)
        header.add_field(name="Result", value=result, inline=True)
        investigators = sum(1 for player in players if player["role"] == "active")
        header.add_field(
            name="Players",
            value=f"{investigators} investigators · {len(players) - investigators} watchers",
            inline=False,
        )

        lines = []
        for player in players:
            role = "Investigator" if player["role"] == "active" else "Watcher"
            if player["role"] == "active" and player["rooms"] is not None:
                role += f", {player['rooms']} room{'s' if player['rooms'] != 1 else ''}"
            if player["bones"] is None:
                reward = "not paid yet"
            else:
                parts = [f"{player['bones']} bones"]
                if player["bags"]:
                    parts.append(f"{player['bags']} bag{'s' if player['bags'] != 1 else ''}")
                if player["crate"]:
                    parts.append(f"{player['crate'].capitalize()} crate")
                if player["theme"]:
                    parts.append("The Last Lantern")
                reward = ", ".join(parts)
            lines.append(
                f"<@{player['user_id']}> · {role} · {reward} · joined {self._stamp(player['joined_at'], 'T')}"
            )
        if not lines:
            lines.append("Nobody joined this manor.")

        pages = []
        chunk = ""
        for line in lines:
            if len(chunk) + len(line) + 1 > 4000:
                pages.append(chunk)
                chunk = ""
            chunk += line + "\n"
        pages.append(chunk)

        # Discord caps the combined embeds in one message at 6000 characters.
        first = discord.Embed(description=pages[0], color=0xE4572E)
        await ctx.send(embeds=[header, first], allowed_mentions=discord.AllowedMentions.none())
        for page in pages[1:]:
            await ctx.send(
                embed=discord.Embed(description=page, color=0xE4572E),
                allowed_mentions=discord.AllowedMentions.none(),
            )


async def setup(bot):
    from .door import PhantomDoor

    await bot.add_cog(HalloweenManor(bot))
    await bot.add_cog(PhantomDoor(bot))

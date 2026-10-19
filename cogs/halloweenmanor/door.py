"""Automated phantom door. Public channel, Night Watch ping, knock queue, then gone."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime, timedelta, timezone
from io import BytesIO

import discord
from discord.ext import commands

from utils.checks import is_gm
from utils.i18n import _, locale_doc

from .door_logic import (
    KNOCK_SECONDS,
    LINGER_SECONDS,
    REVEAL_SECONDS,
    image_path,
    parse_window,
    plan_night,
    settle_door,
)
from .watch import ensure_watch_role, find_watch_role, set_watching


log = logging.getLogger(__name__)

NIGHT_KEY = "halloween:door:nights"
LIVE_KEY = "halloween:door:live"
MANOR_CATEGORY_ID = 1403273394853511240
LOG_LIST_SIZE = 10
CHANNEL_NAME = "「🚪」night-door"
# Non-zero: post in this channel only. No channel create/delete. Set to 0 to go live.
PREVIEW_CHANNEL_ID = 1558205878832730233
PREVIEW_KNOCK_SECONDS = 45
PREVIEW_LINGER_SECONDS = 20
PREVIEW_FIRST_SPAWN_SECONDS = 8
EMBED_COLOR = {
    "queue": 0x2B1D24,
    "trick": 0x7A2E12,
    "treat": 0xC45C26,
    "ethereal": 0xE8D5A3,
    "empty": 0x2B1D24,
}
OUTCOME_STYLE = {
    "queue": ("🚪", "A Phantom Door", 0x3B2A32),
    "ajar": ("🕯️", "The latch turns", 0xC45C26),
    "trick": ("🎭", "It's a Trick", 0x8C2F12),
    "treat": ("🍬", "It's a Treat", 0xE08A3C),
    "ethereal": ("✨", "A Blessing", 0xE8D5A3),
    "empty": ("🌫️", "The woods go still", 0x2B1D24),
}


def _decode(value):
    if value is None:
        return None
    if isinstance(value, bytes):
        return value.decode()
    return str(value)


def _utc(ts: float | None = None) -> datetime:
    if ts is None:
        return datetime.now(timezone.utc)
    return datetime.fromtimestamp(ts, tz=timezone.utc)


def load_door_bytes(key: str) -> BytesIO | None:
    path = image_path(key)
    if not path.is_file():
        return None
    output = BytesIO(path.read_bytes())
    output.seek(0)
    return output


class KnockButton(discord.ui.Button):
    def __init__(self):
        super().__init__(
            label="Knock",
            emoji="🚪",
            style=discord.ButtonStyle.primary,
            custom_id="door:knock",
        )

    async def callback(self, interaction: discord.Interaction):
        cog = interaction.client.get_cog("PhantomDoor")
        if cog is None:
            return await interaction.response.send_message("The door is gone.", ephemeral=True)
        await cog.handle_knock(interaction)


class DoorQueueView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(KnockButton())


class PhantomDoor(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.nights = {}
        self.doors = {}
        self.start_lock = asyncio.Lock()
        self.spawn_lock = asyncio.Lock()

    async def cog_load(self):
        self.bot.add_view(DoorQueueView())
        await self._ensure_tables()
        await self._resume()

    async def cog_unload(self):
        for night in list(self.nights.values()):
            task = night.get("task")
            if task and not task.done():
                task.cancel()
        for door in list(self.doors.values()):
            task = door.get("task")
            if task and not task.done():
                task.cancel()

    def _halloween_enabled(self) -> bool:
        flags = getattr(self.bot, "event_flags", None) or {}
        return bool(flags.get("halloween", False))

    def _previewing(self) -> bool:
        return bool(PREVIEW_CHANNEL_ID)

    def _knock_seconds(self) -> int:
        return PREVIEW_KNOCK_SECONDS if self._previewing() else KNOCK_SECONDS

    def _linger_seconds(self) -> int:
        return PREVIEW_LINGER_SECONDS if self._previewing() else LINGER_SECONDS

    def _manor_open(self, guild_id: int) -> bool:
        if self._previewing():
            return False
        manor = self.bot.get_cog("HalloweenManor")
        if manor is None:
            return False
        return manor._raid_for(guild_id) is not None

    async def _ensure_tables(self):
        try:
            await self.bot.pool.execute(
                """
                CREATE TABLE IF NOT EXISTS night_door_nights (
                    id SERIAL PRIMARY KEY,
                    guild_id BIGINT NOT NULL,
                    started_by BIGINT NOT NULL,
                    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    ends_at TIMESTAMPTZ NOT NULL,
                    stopped_by BIGINT,
                    stopped_at TIMESTAMPTZ
                );
                CREATE TABLE IF NOT EXISTS night_door_spawns (
                    id SERIAL PRIMARY KEY,
                    night_id INTEGER REFERENCES night_door_nights (id) ON DELETE CASCADE,
                    guild_id BIGINT NOT NULL,
                    channel_id BIGINT,
                    scheduled_at TIMESTAMPTZ NOT NULL,
                    opened_at TIMESTAMPTZ,
                    settled_at TIMESTAMPTZ,
                    closed_at TIMESTAMPTZ,
                    outcome TEXT,
                    variant TEXT,
                    visitor_id BIGINT,
                    knocker_count INTEGER,
                    skipped TEXT
                );
                CREATE INDEX IF NOT EXISTS night_door_spawns_guild
                    ON night_door_spawns (guild_id, scheduled_at DESC);
                CREATE TABLE IF NOT EXISTS night_door_knockers (
                    spawn_id INTEGER NOT NULL REFERENCES night_door_spawns (id) ON DELETE CASCADE,
                    user_id BIGINT NOT NULL,
                    visitor BOOLEAN NOT NULL DEFAULT FALSE,
                    bones INTEGER,
                    bags INTEGER,
                    item_name TEXT,
                    item_stat INTEGER,
                    PRIMARY KEY (spawn_id, user_id)
                );
                CREATE TABLE IF NOT EXISTS night_watch_pity (
                    guild_id BIGINT NOT NULL,
                    user_id BIGINT NOT NULL,
                    extra_tickets INTEGER NOT NULL DEFAULT 0,
                    consecutive_misses INTEGER NOT NULL DEFAULT 0,
                    sitout_left INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (guild_id, user_id)
                );
                """
            )
        except Exception:
            log.exception("Failed to create phantom door tables")

    async def _save_night(self, night):
        payload = {
            "night_id": night["night_id"],
            "guild_id": night["guild_id"],
            "started_by": night["started_by"],
            "started_at": night["started_at"],
            "ends_at": night["ends_at"],
            "remaining": night["remaining"],
        }
        try:
            await self.bot.redis.set(f"halloween:door:night:{night['guild_id']}", json.dumps(payload))
            await self.bot.redis.sadd(NIGHT_KEY, str(night["guild_id"]))
        except Exception:
            log.exception("Failed to persist a phantom door night")

    async def _forget_night(self, guild_id: int):
        night = self.nights.pop(guild_id, None)
        if night:
            task = night.get("task")
            if task and not task.done() and task is not asyncio.current_task():
                task.cancel()
        try:
            await self.bot.redis.delete(f"halloween:door:night:{guild_id}")
            await self.bot.redis.srem(NIGHT_KEY, str(guild_id))
        except Exception:
            log.exception("Failed to drop a phantom door night")

    async def _save_door(self, door):
        payload = {
            "spawn_id": door.get("spawn_id"),
            "guild_id": door["guild_id"],
            "channel_id": door["channel_id"],
            "message_id": door.get("message_id") or 0,
            "phase": door["phase"],
            "deadline": door["deadline"],
            "knockers": list(door["knockers"]),
            "paid": door.get("paid", False),
            "settling": bool(door.get("settling", False)),
            "owned_channel": bool(door.get("owned_channel", False)),
        }
        try:
            await self.bot.redis.set(f"halloween:door:live:{door['guild_id']}", json.dumps(payload))
            await self.bot.redis.sadd(LIVE_KEY, str(door["guild_id"]))
        except Exception:
            log.exception("Failed to persist a live phantom door")

    async def _forget_door(self, guild_id: int):
        door = self.doors.pop(guild_id, None)
        if door:
            task = door.get("task")
            if task and not task.done() and task is not asyncio.current_task():
                task.cancel()
        try:
            await self.bot.redis.delete(f"halloween:door:live:{guild_id}")
            await self.bot.redis.srem(LIVE_KEY, str(guild_id))
        except Exception:
            log.exception("Failed to drop a live phantom door")

    async def _resume(self):
        try:
            live_ids = await self.bot.redis.smembers(LIVE_KEY) or []
        except Exception:
            live_ids = []
        for raw_id in live_ids:
            guild_id = int(_decode(raw_id))
            try:
                raw = await self.bot.redis.get(f"halloween:door:live:{guild_id}")
                if not raw:
                    await self.bot.redis.srem(LIVE_KEY, str(guild_id))
                    continue
                payload = json.loads(_decode(raw))
                door = {
                    "spawn_id": payload.get("spawn_id"),
                    "guild_id": guild_id,
                    "channel_id": int(payload["channel_id"]),
                    "message_id": int(payload.get("message_id") or 0),
                    "phase": payload.get("phase") or "queue",
                    "deadline": float(payload["deadline"]),
                    "knockers": {int(user_id) for user_id in payload.get("knockers") or []},
                    "paid": bool(payload.get("paid")),
                    "settling": False,
                    "owned_channel": bool(payload.get("owned_channel", not self._previewing())),
                    "lock": asyncio.Lock(),
                    "wake": asyncio.Event(),
                    "message": None,
                }
                if door.get("spawn_id"):
                    settled = await self.bot.pool.fetchval(
                        "SELECT settled_at FROM night_door_spawns WHERE id = $1;",
                        door["spawn_id"],
                    )
                    if settled:
                        door["paid"] = True
                        if door["phase"] == "reveal":
                            door["phase"] = "linger"
                self.doors[guild_id] = door
                door["task"] = asyncio.create_task(self._run_door(guild_id, resumed=True))
            except Exception:
                log.exception("Dropping unrecoverable live door %s", guild_id)
                await self._forget_door(guild_id)

        try:
            night_ids = await self.bot.redis.smembers(NIGHT_KEY) or []
        except Exception:
            night_ids = []
        for raw_id in night_ids:
            guild_id = int(_decode(raw_id))
            try:
                raw = await self.bot.redis.get(f"halloween:door:night:{guild_id}")
                if not raw:
                    await self.bot.redis.srem(NIGHT_KEY, str(guild_id))
                    continue
                payload = json.loads(_decode(raw))
                night = {
                    "night_id": payload["night_id"],
                    "guild_id": guild_id,
                    "started_by": int(payload["started_by"]),
                    "started_at": float(payload["started_at"]),
                    "ends_at": float(payload["ends_at"]),
                    "remaining": [float(ts) for ts in payload.get("remaining") or []],
                    "wake": asyncio.Event(),
                }
                self.nights[guild_id] = night
                night["task"] = asyncio.create_task(self._run_night(guild_id))
            except Exception:
                log.exception("Dropping unrecoverable door night %s", guild_id)
                await self._forget_night(guild_id)

    async def _pity_map(self, guild_id: int, user_ids: list[int]) -> dict:
        from .door_logic import Pity

        if not user_ids:
            return {}
        rows = await self.bot.pool.fetch(
            """
            SELECT user_id, extra_tickets, consecutive_misses, sitout_left
            FROM night_watch_pity
            WHERE guild_id = $1 AND user_id = ANY($2::bigint[]);
            """,
            guild_id,
            user_ids,
        )
        pity = {}
        for row in rows:
            pity[row["user_id"]] = Pity(
                extra_tickets=row["extra_tickets"],
                consecutive_misses=row["consecutive_misses"],
                sitout_left=row["sitout_left"],
            )
        return pity

    async def _save_pity(self, guild_id: int, pity_map: dict):
        for user_id, pity in pity_map.items():
            await self.bot.pool.execute(
                """
                INSERT INTO night_watch_pity (guild_id, user_id, extra_tickets, consecutive_misses, sitout_left)
                VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT (guild_id, user_id)
                DO UPDATE SET extra_tickets = $3, consecutive_misses = $4, sitout_left = $5;
                """,
                guild_id,
                user_id,
                pity.extra_tickets,
                pity.consecutive_misses,
                pity.sitout_left,
            )

    def _style(self, key: str):
        return OUTCOME_STYLE.get(key, OUTCOME_STYLE["queue"])

    def _board_embed(self, key: str, description: str, *, filename: str | None = "door.jpg", fields=None, footer: str | None = None):
        emoji, title, color = self._style(key)
        embed = discord.Embed(
            title=f"{emoji}  {title}",
            description=description,
            color=color,
        )
        for name, value, inline in fields or ():
            embed.add_field(name=name, value=value, inline=inline)
        if footer:
            embed.set_footer(text=footer)
        if filename:
            embed.set_image(url=f"attachment://{filename}")
        return embed

    def _queue_embed(self, door, filename: str | None = "door.jpg"):
        waiting = len(door["knockers"])
        return self._board_embed(
            "queue",
            "A door is standing in the woods. It should not be. Press **Knock** and wait on the leaves — when it answers, one visitor is chosen.",
            filename=filename,
            fields=(
                ("Waiting", f"🍂 **{waiting}**", True),
                ("Answers", f"<t:{int(door['deadline'])}:R>", True),
            ),
            footer="You can Knock once. Switching is not needed.",
        )

    def _embed(self, title: str, description: str, color_key: str, filename: str | None = "door.jpg"):
        return self._board_embed(color_key if color_key in OUTCOME_STYLE else "queue", description, filename=filename)

    async def _attach(self, key: str):
        data = await asyncio.to_thread(load_door_bytes, key)
        if data is None:
            return None
        suffix = image_path(key).suffix.lstrip(".") or "jpg"
        return discord.File(data, filename=f"door.{suffix}")

    def _queue_text(self, door) -> str:
        waiting = len(door["knockers"])
        remain = max(0, int(door["deadline"] - time.time()))
        people = "person is" if waiting == 1 else "people are"
        return (
            "A door is standing in the woods. It should not be.\n\n"
            f"**{waiting}** {people} waiting on the leaves. "
            f"**Knock** before it answers <t:{int(door['deadline'])}:R> ({remain}s)."
        )

    async def handle_knock(self, interaction: discord.Interaction):
        if interaction.guild is None:
            return await interaction.response.send_message("The door is gone.", ephemeral=True)
        door = self.doors.get(interaction.guild.id)
        if door is None or interaction.channel_id != door["channel_id"]:
            return await interaction.response.send_message("The door is gone.", ephemeral=True)
        if self._previewing() and interaction.channel_id != PREVIEW_CHANNEL_ID:
            return await interaction.response.send_message("The door is gone.", ephemeral=True)
        has_character = await self.bot.pool.fetchval(
            'SELECT 1 FROM profile WHERE "user"=$1;', interaction.user.id
        )
        if not has_character:
            return await interaction.response.send_message(
                "You need a character to knock.", ephemeral=True
            )
        async with door["lock"]:
            if door["phase"] != "queue":
                return await interaction.response.send_message(
                    "The door has already answered.", ephemeral=True
                )
            if interaction.user.id in door["knockers"]:
                return await interaction.response.send_message(
                    "You are already waiting at the door.", ephemeral=True
                )
            door["knockers"].add(interaction.user.id)
        await self._save_door(door)
        self._request_refresh(interaction.guild.id)
        await interaction.response.send_message(
            "🍂 You wait on the leaves. When the door answers, one visitor is chosen. "
            "You'll get a DM either way.",
            ephemeral=True,
        )

    def _request_refresh(self, guild_id: int):
        door = self.doors.get(guild_id)
        if door is None or door["phase"] != "queue":
            return
        door["dirty"] = True
        task = door.get("refresh_task")
        if task is None or task.done():
            door["refresh_task"] = asyncio.create_task(self._refresh_soon(guild_id))

    async def _refresh_soon(self, guild_id: int):
        await asyncio.sleep(1.5)
        door = self.doors.get(guild_id)
        if door is None or not door.get("dirty") or door["phase"] != "queue":
            return
        door["dirty"] = False
        message = door.get("message")
        if message is None:
            return
        try:
            await message.edit(embed=self._queue_embed(door, filename="door.jpg"))
        except discord.HTTPException:
            return

    async def _run_night(self, guild_id: int):
        try:
            while True:
                night = self.nights.get(guild_id)
                if night is None:
                    return
                now = time.time()
                if now >= night["ends_at"] and guild_id not in self.doors:
                    await self._forget_night(guild_id)
                    return
                upcoming = [ts for ts in night["remaining"] if ts > now - 60]
                night["remaining"] = upcoming
                await self._save_night(night)
                if not upcoming:
                    if guild_id in self.doors:
                        await asyncio.sleep(5)
                        continue
                    if now >= night["ends_at"]:
                        await self._forget_night(guild_id)
                        return
                    wait = night["ends_at"] - now
                    try:
                        await asyncio.wait_for(night["wake"].wait(), timeout=max(1.0, wait))
                    except asyncio.TimeoutError:
                        continue
                    night["wake"].clear()
                    continue
                nxt = min(upcoming)
                wait = nxt - now
                if wait > 0:
                    try:
                        await asyncio.wait_for(night["wake"].wait(), timeout=wait)
                        night["wake"].clear()
                        continue
                    except asyncio.TimeoutError:
                        pass
                night["remaining"] = [ts for ts in night["remaining"] if ts != nxt]
                await self._save_night(night)
                if not self._halloween_enabled():
                    continue
                async with self.spawn_lock:
                    await self._spawn_door(guild_id, night, nxt)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("Phantom door night stopped for %s", guild_id)

    async def _move_to_category_top(self, channel, category):
        try:
            await channel.edit(
                category=category,
                position=category.position + 1,
                reason="Phantom door at the top of the category",
            )
        except discord.HTTPException:
            log.exception("Could not move the phantom door to the top of the category")

    async def _open_spawn_channel(self, guild, preferred=None):
        del preferred
        category = guild.get_channel(MANOR_CATEGORY_ID)
        if not isinstance(category, discord.CategoryChannel):
            log.warning("Phantom door: manor category missing in guild %s", guild.id)
            return None, False
        names = {channel.name for channel in guild.text_channels}
        channel_name = CHANNEL_NAME
        suffix = 2
        while channel_name in names:
            channel_name = f"{CHANNEL_NAME}-{suffix}"
            suffix += 1
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(
                view_channel=True, send_messages=False, add_reactions=False
            ),
            guild.me: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                embed_links=True,
                attach_files=True,
                manage_channels=True,
                manage_messages=True,
                read_message_history=True,
            ),
        }
        try:
            channel = await guild.create_text_channel(
                name=channel_name,
                category=category,
                overwrites=overwrites,
                position=category.position + 1,
                topic="A door in the woods. Knock. Chat is closed.",
                reason="Phantom door",
            )
        except discord.HTTPException:
            log.exception("Failed to create a phantom door channel")
            return None, False
        await self._move_to_category_top(channel, category)
        return channel, True

    async def _discard_owned_channel(self, channel, owned_channel: bool, reason: str):
        if not owned_channel or channel is None:
            return
        if channel.id == PREVIEW_CHANNEL_ID:
            return
        try:
            await channel.delete(reason=reason)
        except discord.HTTPException:
            log.exception("Failed to delete a phantom door channel")

    async def _spawn_door(self, guild_id: int, night, scheduled_ts: float, preferred_channel=None) -> str | None:
        if guild_id in self.doors:
            return "A door is already open."
        if self._manor_open(guild_id):
            await self.bot.pool.execute(
                """
                INSERT INTO night_door_spawns (night_id, guild_id, scheduled_at, skipped)
                VALUES ($1, $2, $3, $4);
                """,
                night.get("night_id"),
                guild_id,
                _utc(scheduled_ts),
                "manor_open",
            )
            return "Skipped because a manor is open."
        guild = self.bot.get_guild(guild_id)
        if guild is None:
            return "I could not find this server."
        channel, owned_channel = await self._open_spawn_channel(guild, preferred_channel)
        if channel is None:
            return f"I could not create a door under category `{MANOR_CATEGORY_ID}`."
        try:
            spawn_id = await self.bot.pool.fetchval(
                """
                INSERT INTO night_door_spawns (night_id, guild_id, channel_id, scheduled_at, opened_at)
                VALUES ($1, $2, $3, $4, NOW()) RETURNING id;
                """,
                night.get("night_id"),
                guild_id,
                channel.id,
                _utc(scheduled_ts),
            )
        except Exception as exc:
            log.exception("Failed to log a phantom door spawn")
            await self._discard_owned_channel(channel, owned_channel, "Phantom door log failed")
            return f"I could not write the door log: {exc}"
        deadline = time.time() + self._knock_seconds()
        door = {
            "spawn_id": spawn_id,
            "guild_id": guild_id,
            "channel_id": channel.id,
            "message_id": 0,
            "phase": "queue",
            "deadline": deadline,
            "knockers": set(),
            "paid": False,
            "owned_channel": owned_channel,
            "lock": asyncio.Lock(),
            "wake": asyncio.Event(),
            "message": None,
        }
        self.doors[guild_id] = door
        attachment = await self._attach("closed")
        role = find_watch_role(channel.guild)
        content = None
        mentions = discord.AllowedMentions.none()
        if role is not None:
            content = f"{role.mention} A phantom door is standing in the woods. **Knock** before it answers."
            mentions = discord.AllowedMentions(roles=[role])
        kwargs = {
            "content": content,
            "embed": self._queue_embed(door, filename="door.jpg" if attachment else None),
            "view": DoorQueueView(),
            "allowed_mentions": mentions,
        }
        if attachment is not None:
            kwargs["file"] = attachment
        try:
            message = await channel.send(**kwargs)
        except discord.HTTPException:
            log.exception("Failed to post the phantom door with art")
            kwargs.pop("file", None)
            kwargs["embed"] = self._queue_embed(door, filename=None)
            try:
                message = await channel.send(**kwargs)
            except discord.HTTPException as exc:
                log.exception("Failed to post the phantom door")
                await self._forget_door(guild_id)
                await self._discard_owned_channel(channel, owned_channel, "Phantom door post failed")
                return f"I could not post the door here: {exc}"
        door["message_id"] = message.id
        door["message"] = message
        await self._save_door(door)
        door["task"] = asyncio.create_task(self._run_door(guild_id))
        return None

    async def _resolve_message(self, door):
        if door.get("message") is not None:
            return door["message"]
        channel = self.bot.get_channel(door["channel_id"])
        if channel is None:
            return None
        try:
            message = await channel.fetch_message(door["message_id"])
        except discord.HTTPException:
            return None
        door["message"] = message
        return message

    async def _run_door(self, guild_id: int, resumed: bool = False):
        try:
            door = self.doors.get(guild_id)
            if door is None:
                return
            await self._resolve_message(door)
            if door["phase"] == "queue":
                remaining = door["deadline"] - time.time()
                if remaining > 0:
                    try:
                        await asyncio.wait_for(door["wake"].wait(), timeout=remaining)
                        door["wake"].clear()
                        if door.get("wake_reason") == "close":
                            return
                    except asyncio.TimeoutError:
                        pass
                await self._reveal(guild_id)
                door = self.doors.get(guild_id)
                if door is None:
                    return
            if not door.get("paid"):
                await self._reveal(guild_id)
            linger_until = door.get("linger_until") or (time.time() + self._linger_seconds())
            wait = linger_until - time.time()
            if wait > 0:
                try:
                    await asyncio.wait_for(door["wake"].wait(), timeout=wait)
                    door["wake"].clear()
                except asyncio.TimeoutError:
                    pass
            await self._close_door(guild_id)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("Phantom door director stopped for %s", guild_id)

    async def _reveal(self, guild_id: int):
        from utils import random as utils_random

        door = self.doors.get(guild_id)
        if door is None or door.get("paid") or door.get("settling"):
            return
        async with door["lock"]:
            if door.get("paid") or door.get("settling"):
                return
            door["settling"] = True
            door["phase"] = "reveal"
            knockers = list(door["knockers"])
        await self._save_door(door)
        if door.get("spawn_id"):
            already = await self.bot.pool.fetchval(
                "SELECT 1 FROM night_door_knockers WHERE spawn_id = $1 LIMIT 1;",
                door["spawn_id"],
            )
            if already:
                door["paid"] = True
                await self._save_door(door)
                return
        pity_map = await self._pity_map(guild_id, knockers)
        result = settle_door(knockers, pity_map, utils_random)
        if result.visitor_id is not None:
            result.story = result.story.format(visitor=f"<@{result.visitor_id}>")
        message = await self._resolve_message(door)
        channel = self.bot.get_channel(door["channel_id"])
        if result.outcome != "empty" and message is not None:
            ajar = await self._attach(result.ajar_key)
            ajar_embed = self._board_embed(
                "ajar",
                "The smoke pulls back. The latch turns by itself.",
                filename="door.jpg" if ajar else None,
            )
            try:
                kwargs = {"embed": ajar_embed, "view": None, "content": None}
                if ajar is not None:
                    kwargs["attachments"] = [ajar]
                else:
                    kwargs["attachments"] = []
                await message.edit(**kwargs)
            except discord.HTTPException:
                log.exception("Failed to show the cracked door")
        await asyncio.sleep(REVEAL_SECONDS)
        reveal = await self._attach(result.reveal_key)
        reveal_key = result.outcome if result.outcome in OUTCOME_STYLE else "empty"
        fields = []
        if result.visitor_id is not None:
            fields.append(("Chosen", f"<@{result.visitor_id}>", True))
            fields.append(("Waiting", f"🍂 **{len(result.receipts)}**", True))
        reveal_embed = self._board_embed(
            reveal_key,
            result.story,
            filename="door.jpg" if reveal else None,
            fields=fields,
            footer="Everyone who knocked is being paid. Check your DMs.",
        )
        message = await self._resolve_message(door)
        if message is not None:
            try:
                kwargs = {"embed": reveal_embed, "view": None, "content": None}
                if reveal is not None:
                    kwargs["attachments"] = [reveal]
                else:
                    kwargs["attachments"] = []
                await message.edit(**kwargs)
            except discord.HTTPException:
                log.exception("Failed to show the door answer")
        for receipt in result.receipts:
            await self._record_and_pay(door, receipt)
        await self._save_pity(guild_id, pity_map)
        await self._log_spawn_result(door, result)
        door["paid"] = True
        door["phase"] = "linger"
        door["linger_until"] = time.time() + self._linger_seconds()
        door["result"] = result
        await self._save_door(door)
        if channel is not None and result.receipts:
            follow = self._board_embed(
                reveal_key,
                f"<@{result.visitor_id}> was chosen." if result.visitor_id else "The door answered.",
                filename=None,
                fields=(("DMs", "Everyone who knocked has a receipt waiting.", False),),
                footer="This channel will fade in a moment.",
            )
            try:
                await channel.send(
                    embed=follow,
                    allowed_mentions=discord.AllowedMentions(users=True),
                )
            except discord.HTTPException:
                pass
        await self._send_receipts(result)

    def _reward_lines(self, receipt) -> list[str]:
        lines = [f"💀 **Bones:** {receipt.bones}"]
        if receipt.bags:
            word = "bag" if receipt.bags == 1 else "bags"
            lines.append(f"🛍️ **Trick-or-treat {word}:** {receipt.bags}")
        if receipt.item is not None:
            item = receipt.item
            stat = item.armor if item.armor else item.damage
            lines.append(f"🗡️ **{item.name}** — {item.type_}, {stat} stat, {item.element}")
        return lines

    def _dm_embed(self, receipt, result, filename: str | None = None):
        key = result.outcome if result.outcome in OUTCOME_STYLE else "empty"
        emoji, title, color = self._style(key)
        if receipt.visitor:
            story = result.story.replace(f"<@{receipt.user_id}>", "**You**")
            description = f"{story}\n\n" + "\n".join(self._reward_lines(receipt))
            footer = "The woods remember who knocked."
        else:
            description = (
                "The door answered for someone else. You still waited on the leaves, "
                "and the woods paid you for showing up.\n\n" + "\n".join(self._reward_lines(receipt))
            )
            footer = "The woods still paid you for showing up."
        embed = discord.Embed(
            title=f"{emoji}  {title}" if receipt.visitor else f"🍂  You waited at the door",
            description=description,
            color=color if receipt.visitor else 0x5A463C,
        )
        embed.set_footer(text=footer)
        if filename:
            embed.set_image(url=f"attachment://{filename}")
        return embed

    def _receipt_text(self, receipt) -> str:
        lines = [receipt.summary] + self._reward_lines(receipt)
        return "\n".join(lines)

    async def _record_and_pay(self, door, receipt):
        item = receipt.item
        async with self.bot.pool.acquire() as conn:
            async with conn.transaction():
                spawn_id = door.get("spawn_id")
                if spawn_id:
                    inserted = await conn.fetchval(
                        """
                        INSERT INTO night_door_knockers
                            (spawn_id, user_id, visitor, bones, bags, item_name, item_stat)
                        VALUES ($1, $2, $3, $4, $5, $6, $7)
                        ON CONFLICT (spawn_id, user_id) DO NOTHING
                        RETURNING user_id;
                        """,
                        spawn_id,
                        receipt.user_id,
                        receipt.visitor,
                        receipt.bones,
                        receipt.bags,
                        item.name if item else None,
                        (item.armor or item.damage) if item else None,
                    )
                    if inserted is None:
                        return
                await conn.execute(
                    '''
                    UPDATE profile
                    SET bones = COALESCE(bones, 0) + $1,
                        trickortreat = COALESCE(trickortreat, 0) + $2
                    WHERE "user" = $3;
                    ''',
                    receipt.bones,
                    receipt.bags,
                    receipt.user_id,
                )
                if item is not None:
                    await self.bot.create_item(
                        name=item.name,
                        value=item.value,
                        type_=item.type_,
                        damage=item.damage,
                        armor=item.armor,
                        owner=receipt.user_id,
                        hand=item.hand,
                        element=item.element,
                        conn=conn,
                    )

    async def _send_receipts(self, result):
        async def send_one(receipt):
            try:
                user = self.bot.get_user(receipt.user_id) or await self.bot.fetch_user(receipt.user_id)
            except discord.HTTPException:
                return
            file = None
            filename = None
            if receipt.visitor:
                file = await self._attach(result.reveal_key)
                if file is not None:
                    filename = file.filename
            embed = self._dm_embed(receipt, result, filename=filename)
            try:
                if file is not None:
                    await user.send(embed=embed, file=file)
                else:
                    await user.send(embed=embed)
            except discord.HTTPException:
                try:
                    await user.send(self._receipt_text(receipt))
                except discord.HTTPException:
                    return

        await asyncio.gather(*(send_one(receipt) for receipt in result.receipts), return_exceptions=True)

    async def _log_spawn_result(self, door, result):
        spawn_id = door.get("spawn_id")
        if not spawn_id:
            return
        try:
            await self.bot.pool.execute(
                """
                UPDATE night_door_spawns
                SET settled_at = COALESCE(settled_at, NOW()),
                    outcome = $2,
                    variant = $3,
                    visitor_id = $4,
                    knocker_count = $5
                WHERE id = $1;
                """,
                spawn_id,
                result.outcome,
                result.variant,
                result.visitor_id,
                len(result.receipts),
            )
        except Exception:
            log.exception("Failed to log a phantom door settle")

    async def _close_door(self, guild_id: int):
        door = self.doors.get(guild_id)
        if door is None:
            return
        channel = self.bot.get_channel(door["channel_id"])
        if door.get("spawn_id"):
            try:
                await self.bot.pool.execute(
                    "UPDATE night_door_spawns SET closed_at = NOW() WHERE id = $1;",
                    door["spawn_id"],
                )
            except Exception:
                log.exception("Failed to log a phantom door close")
        owned = bool(door.get("owned_channel"))
        message = door.get("message")
        await self._forget_door(guild_id)
        if message is not None:
            try:
                await message.edit(view=None)
            except discord.HTTPException:
                pass
        if channel is not None and owned and channel.id != PREVIEW_CHANNEL_ID:
            try:
                await channel.delete(reason="Phantom door closed")
            except discord.HTTPException:
                log.exception("Failed to delete the phantom door channel")

    @commands.group(name="night", invoke_without_command=True, brief=_("Night Watch pings"))
    @locale_doc
    async def night(self, ctx):
        _(
            """Opt in to Night Watch pings for the Hollow Manor and the phantom door.

            `{prefix}night watch` to be pinged. `{prefix}night unwatch` to stop.
            """
        )
        await ctx.send(
            "Use `{prefix}night watch` to be pinged when the Hollow Manor opens or a phantom door appears. "
            "`{prefix}night unwatch` turns the ping off. The channels still show for everyone."
            .format(prefix=ctx.clean_prefix)
        )

    @night.command(name="watch")
    async def night_watch(self, ctx):
        if ctx.guild is None:
            return await ctx.send("Opt in from a server channel.")
        await ctx.send(await set_watching(ctx.author, True))

    @night.command(name="unwatch")
    async def night_unwatch(self, ctx):
        if ctx.guild is None:
            return await ctx.send("Opt out from a server channel.")
        await ctx.send(await set_watching(ctx.author, False))

    @commands.group(name="door", invoke_without_command=True, brief=_("The phantom door"))
    @locale_doc
    async def door(self, ctx):
        _(
            """A door that appears in the woods during Halloween.

            Opt in with `{prefix}night watch`. A GM starts the night with `{prefix}door start`.
            """
        )
        await ctx.send(
            "A phantom door may appear in the woods during Halloween. "
            "Use `{prefix}night watch` to be pinged. A GM starts the night with `{prefix}door start`."
            .format(prefix=ctx.clean_prefix)
        )

    @door.command(name="watch")
    async def door_watch(self, ctx):
        await self.night_watch(ctx)

    @door.command(name="unwatch")
    async def door_unwatch(self, ctx):
        await self.night_unwatch(ctx)

    @is_gm()
    @door.command(name="start")
    async def door_start(self, ctx, duration: str = "24h"):
        if ctx.guild is None:
            return await ctx.send("Start the door from a server channel.")
        if not self._halloween_enabled():
            return await ctx.send("Enable the Halloween event before starting the phantom door.")
        if self._previewing() and ctx.channel.id != PREVIEW_CHANNEL_ID:
            return await ctx.send(
                f"Preview is on. Start the door in <#{PREVIEW_CHANNEL_ID}>."
            )
        seconds = parse_window(duration)
        if seconds is None:
            return await ctx.send("Use a window like `24h`, `3d`, or `7d`.")
        if not self._previewing():
            category = ctx.guild.get_channel(MANOR_CATEGORY_ID)
            if not isinstance(category, discord.CategoryChannel):
                return await ctx.send(
                    f"I could not find the manor category ({MANOR_CATEGORY_ID}) in this server, so the night did not start."
                )
        async with self.start_lock:
            if ctx.guild.id in self.nights:
                return await ctx.send("A phantom door night is already running in this server.")
            started_at = datetime.now(timezone.utc)
            ends_at = started_at + timedelta(seconds=seconds)
            from utils import random as utils_random

            spawns = plan_night(started_at, ends_at, utils_random)
            try:
                night_id = await self.bot.pool.fetchval(
                    """
                    INSERT INTO night_door_nights (guild_id, started_by, started_at, ends_at)
                    VALUES ($1, $2, $3, $4) RETURNING id;
                    """,
                    ctx.guild.id,
                    ctx.author.id,
                    started_at,
                    ends_at,
                )
            except Exception:
                log.exception("Failed to record a phantom door night")
                return await ctx.send("I could not write the door log, so the night did not start.")
            remaining = [stamp.timestamp() for stamp in spawns]
            if self._previewing():
                remaining = [time.time() + PREVIEW_FIRST_SPAWN_SECONDS] + remaining
            night = {
                "night_id": night_id,
                "guild_id": ctx.guild.id,
                "started_by": ctx.author.id,
                "started_at": started_at.timestamp(),
                "ends_at": ends_at.timestamp(),
                "remaining": remaining,
                "wake": asyncio.Event(),
            }
            self.nights[ctx.guild.id] = night
            await self._save_night(night)
            night["task"] = asyncio.create_task(self._run_night(ctx.guild.id))
            await ensure_watch_role(ctx.guild)
            preview_note = (
                f" Preview is on: doors appear in <#{PREVIEW_CHANNEL_ID}> only, "
                f"and the first one is in {PREVIEW_FIRST_SPAWN_SECONDS} seconds. `{ctx.clean_prefix}door now` forces one."
                if self._previewing()
                else f" Players use `{ctx.clean_prefix}night watch` for the ping."
            )
            await ctx.send(
                f"The woods are being watched until <t:{int(ends_at.timestamp())}:f>. "
                f"**{len(remaining)}** doors are planned.{preview_note}"
            )

    @is_gm()
    @door.command(name="now")
    async def door_now(self, ctx):
        await self._spawn_now(ctx)

    async def _spawn_now(self, ctx):
        if ctx.guild is None:
            return await ctx.send("Use this in the preview channel.")
        if not self._previewing():
            return await ctx.send("`$door now` is only available while the preview channel is set.")
        if ctx.channel.id != PREVIEW_CHANNEL_ID:
            return await ctx.send(
                f"This channel is `{ctx.channel.id}`. Use `$door now` in <#{PREVIEW_CHANNEL_ID}>."
            )
        if ctx.guild.id in self.doors:
            return await ctx.send("A door is already open here. Wait for it to finish or use `$door stop`.")
        night = self.nights.get(ctx.guild.id) or {
            "night_id": None,
            "guild_id": ctx.guild.id,
        }
        try:
            async with self.spawn_lock:
                error = await self._spawn_door(
                    ctx.guild.id, night, time.time(), preferred_channel=ctx.channel
                )
        except Exception as exc:
            log.exception("Preview door spawn failed")
            return await ctx.send(f"`$door now` failed: `{type(exc).__name__}: {exc}`")
        if error:
            return await ctx.send(f"`$door now` did not open a door: {error}")
        door = self.doors.get(ctx.guild.id)
        where = f"<#{door['channel_id']}>" if door else "the category"
        await ctx.send(
            f"Preview door is up in {where} (top of the Halloween category). "
            f"Knock within **{self._knock_seconds()}** seconds. Use `$door stop` when you are done."
        )

    @is_gm()
    @door.command(name="stop")
    async def door_stop(self, ctx):
        if ctx.guild is None:
            return
        night = self.nights.get(ctx.guild.id)
        door = self.doors.get(ctx.guild.id)
        if night is None and door is None:
            return await ctx.send("There is no phantom door night running.")
        if night is not None:
            try:
                await self.bot.pool.execute(
                    "UPDATE night_door_nights SET stopped_by = $2, stopped_at = NOW() WHERE id = $1;",
                    night["night_id"],
                    ctx.author.id,
                )
            except Exception:
                log.exception("Failed to mark a phantom door night stopped")
            night["wake"].set()
            await self._forget_night(ctx.guild.id)
        if door is not None:
            door["wake_reason"] = "close"
            door["wake"].set()
            if not door.get("paid") and not door.get("settling"):
                await self._reveal(ctx.guild.id)
            await self._close_door(ctx.guild.id)
        await ctx.send("The phantom door night is over.")

    @is_gm()
    @door.command(name="log")
    async def door_log(self, ctx, spawn_id: int = None):
        if ctx.guild is None:
            return await ctx.send("Use the door log from a server channel.")
        if spawn_id is None:
            return await self._send_spawn_list(ctx)
        await self._send_spawn_detail(ctx, spawn_id)

    @staticmethod
    def _stamp(value, style: str = "f") -> str:
        if value is None:
            return "—"
        return f"<t:{int(value.timestamp())}:{style}>"

    async def _send_spawn_list(self, ctx):
        rows = await self.bot.pool.fetch(
            """
            SELECT * FROM night_door_spawns
            WHERE guild_id = $1
            ORDER BY scheduled_at DESC
            LIMIT $2;
            """,
            ctx.guild.id,
            LOG_LIST_SIZE,
        )
        night = self.nights.get(ctx.guild.id)
        lines = []
        if night:
            lines.append(
                f"Night running until {self._stamp(_utc(night['ends_at']))}. "
                f"**{len(night['remaining'])}** doors still planned."
            )
        else:
            lines.append("No phantom door night is running.")
        lines.append("")
        if not rows:
            lines.append("No doors have been recorded in this server yet.")
        for row in rows:
            if row["skipped"]:
                result = f"skipped ({row['skipped']})"
            elif row["outcome"] is None:
                result = "in progress"
            else:
                result = row["outcome"]
                if row["variant"] and row["variant"] != row["outcome"]:
                    result += f"/{row['variant']}"
            visitor = f"<@{row['visitor_id']}>" if row["visitor_id"] else "nobody"
            lines.append(
                f"**#{row['id']}** · {self._stamp(row['scheduled_at'])} · {result} · "
                f"{row['knocker_count'] or 0} knocked · visitor {visitor}"
            )
        embed = discord.Embed(title="Phantom door log", description="\n".join(lines)[:4096], color=0xC45C26)
        embed.set_footer(text=f"{ctx.clean_prefix}door log <id> shows who knocked and what they received.")
        await ctx.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())

    async def _send_spawn_detail(self, ctx, spawn_id: int):
        spawn = await self.bot.pool.fetchrow(
            "SELECT * FROM night_door_spawns WHERE id = $1 AND guild_id = $2;",
            spawn_id,
            ctx.guild.id,
        )
        if spawn is None:
            return await ctx.send(f"There is no door #{spawn_id} in this server's log.")
        knockers = await self.bot.pool.fetch(
            "SELECT * FROM night_door_knockers WHERE spawn_id = $1 ORDER BY visitor DESC, user_id;",
            spawn_id,
        )
        header = discord.Embed(title=f"Phantom door #{spawn_id}", color=0xC45C26)
        header.add_field(name="Scheduled", value=self._stamp(spawn["scheduled_at"]), inline=True)
        header.add_field(name="Opened", value=self._stamp(spawn["opened_at"]), inline=True)
        header.add_field(name="Settled", value=self._stamp(spawn["settled_at"]), inline=True)
        header.add_field(
            name="Outcome",
            value=spawn["skipped"] or spawn["outcome"] or "—",
            inline=True,
        )
        header.add_field(name="Variant", value=spawn["variant"] or "—", inline=True)
        header.add_field(
            name="Visitor",
            value=f"<@{spawn['visitor_id']}>" if spawn["visitor_id"] else "—",
            inline=True,
        )
        lines = []
        for row in knockers:
            role = "Visitor" if row["visitor"] else "Waiting"
            parts = []
            if row["bones"] is not None:
                parts.append(f"{row['bones']} bones")
            if row["bags"]:
                parts.append(f"{row['bags']} bag")
            if row["item_name"]:
                stat = f" {row['item_stat']}" if row["item_stat"] is not None else ""
                parts.append(f"{row['item_name']}{stat}")
            reward = ", ".join(parts) if parts else "—"
            lines.append(f"<@{row['user_id']}> · {role} · {reward}")
        if not lines:
            lines.append("Nobody knocked.")
        body = discord.Embed(description="\n".join(lines)[:4096], color=0xC45C26)
        await ctx.send(embeds=[header, body], allowed_mentions=discord.AllowedMentions.none())

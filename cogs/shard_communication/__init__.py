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
import json

from datetime import datetime, timedelta
from time import time
from typing import Any
from uuid import uuid4

import asyncpg
import discord
from discord.ext import commands

from cogs.scheduler import Timer
from utils.eval import evaluate as _evaluate
from utils.i18n import _, locale_doc
from utils.misc import nice_join


# Cross-process cooldown check (pass this to commands)
def user_on_cooldown(cooldown: int, identifier: str = None):
    async def predicate(ctx):
        if identifier is None:
            cmd_id = ctx.command.qualified_name
        else:
            cmd_id = identifier
        command_ttl = await ctx.bot.redis.execute_command(
            "TTL", f"cd:{ctx.author.id}:{cmd_id}"
        )
        if command_ttl == -2:
            await ctx.bot.redis.execute_command(
                "SET",
                f"cd:{ctx.author.id}:{cmd_id}",
                cmd_id,
                "EX",
                cooldown,
            )
            return True
        else:
            raise commands.CommandOnCooldown(ctx, command_ttl, commands.BucketType.user)

    return commands.check(predicate)  # TODO: Needs a redesign


# Cross-process cooldown check (pass this to commands)
def guild_on_cooldown(cooldown: int):
    async def predicate(ctx):
        guild = getattr(ctx, "character_data", None)
        if not guild:
            guild = await ctx.bot.pool.fetchval(
                'SELECT guild FROM profile WHERE "user"=$1;', ctx.author.id
            )
        else:
            guild = guild["guild"]
        command_ttl = await ctx.bot.redis.execute_command(
            "TTL", f"guildcd:{guild}:{ctx.command.qualified_name}"
        )
        if command_ttl == -2:
            await ctx.bot.redis.execute_command(
                "SET",
                f"guildcd:{guild}:{ctx.command.qualified_name}",
                ctx.command.qualified_name,
                "EX",
                cooldown,
            )
            return True
        else:
            raise commands.CommandOnCooldown(
                ctx, command_ttl, commands.BucketType.guild
            )

    return commands.check(predicate)


# Cross-process cooldown check (pass this to commands)
def alliance_on_cooldown(cooldown: int):
    async def predicate(ctx):
        data = getattr(ctx, "character_data", None)
        if not data:
            alliance = await ctx.bot.pool.fetchval(
                'SELECT alliance FROM guild WHERE "id"=(SELECT guild FROM profile WHERE'
                ' "user"=$1);',
                ctx.author.id,
            )
        else:
            guild = data["guild"]
            alliance = await ctx.bot.pool.fetchval(
                'SELECT alliance FROM guild WHERE "id"=$1;', guild
            )

        command_ttl = await ctx.bot.redis.execute_command(
            "TTL", f"alliancecd:{alliance}:{ctx.command.qualified_name}"
        )
        if command_ttl == -2:
            await ctx.bot.redis.execute_command(
                "SET",
                f"alliancecd:{alliance}:{ctx.command.qualified_name}",
                ctx.command.qualified_name,
                "EX",
                cooldown,
            )
            return True
        else:
            raise commands.CommandOnCooldown(
                ctx, command_ttl, commands.BucketType.guild
            )

    return commands.check(predicate)


def next_day_cooldown():
    async def predicate(ctx):
        command_ttl = await ctx.bot.redis.execute_command(
            "TTL", f"cd:{ctx.author.id}:{ctx.command.qualified_name}"
        )
        if command_ttl == -2:
            ctt = int(
                86400 - (time() % 86400)
            )  # Calculate the number of seconds until next UTC midnight
            await ctx.bot.redis.execute_command(
                "SET",
                f"cd:{ctx.author.id}:{ctx.command.qualified_name}",
                ctx.command.qualified_name,
                "EX",
                ctt,
            )
            return True
        else:
            raise commands.CommandOnCooldown(ctx, command_ttl, commands.BucketType.user)

    return commands.check(predicate)  # TODO: Needs a redesign


class Sharding(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.router = None
        self.pubsub = bot.redis.pubsub()
        asyncio.create_task(self.register_sub())
        self._messages = dict()
        """
        _messages should be a dict with the syntax {"<command_id>": [outputs]}
        """
        if 0 in self.bot.shard_ids:
            self.bot.add_listener(self.on_raw_interaction)

    def cog_unload(self):
        asyncio.create_task(self.unregister_sub())

    async def register_sub(self):
        await self.pubsub.subscribe(
            self.bot.config.database.redis_shard_announce_channel
        )
        self.router = asyncio.create_task(self.event_handler())

    async def unregister_sub(self):
        if self.router and not self.router.cancelled:
            self.router.cancel()
        await self.pubsub.unsubscribe(
            self.bot.config.database.redis_shard_announce_channel
        )

    async def event_handler(self):
        """
        main router

        Possible messages to come:
        {"scope":<bot/launcher>, "action": "<name>", "args": "<dict of args>", "command_id": "<uuid4>"}
        {"output": "<string>", "command_id": "<uuid4>"}
        """
        async for message in self.pubsub.listen():
            if message["type"] != "message":
                continue
            try:
                payload = json.loads(message["data"])
            except json.JSONDecodeError:
                continue

            if (type := payload.get("type")) and (data := payload.get("data")):
                # Cross process event
                if type == "raw_interaction" and 0 not in self.bot.shard_ids:
                    self.bot._connection.parse_interaction_create(data)
            if payload.get("action") and hasattr(self, payload.get("action")):
                if payload.get("scope") != "bot":
                    continue  # it's not our cup of tea
                if payload.get("args"):
                    asyncio.create_task(
                        getattr(self, payload["action"])(
                            **payload["args"],
                            command_id=payload["command_id"],
                        )
                    )
                else:
                    asyncio.create_task(
                        getattr(self, payload["action"])(
                            command_id=payload["command_id"]
                        )
                    )
            if payload.get("output") and payload.get("command_id") in self._messages:
                for fut in self._messages[payload["command_id"]]:
                    if not fut.done():
                        fut.set_result(payload["output"])
                        break

    async def reload_bans(self, command_id: int):
        await self.bot.load_bans()

    async def clear_donator_cache(self, user_id: int, command_id: int):
        self.bot.get_donator_rank.invalidate(self.bot, user_id)

    async def remove_timer(self, timer_id: int, command_id: int) -> None:
        self.bot.dispatch("timer_remove", timer_id)

    @staticmethod
    def parse_timestamp(timestamp: str) -> datetime:
        try:
            return datetime.strptime(timestamp, "%Y-%m-%dT%H:%M:%S.%f")
        except ValueError:
            return datetime.strptime(timestamp, "%Y-%m-%dT%H:%M:%S")

    async def add_timer(self, *args, **kwargs) -> None:
        kwargs["start"] = self.parse_timestamp(kwargs["start"])
        kwargs["end"] = self.parse_timestamp(kwargs["end"])
        timer = Timer(record=kwargs)
        self.bot.dispatch("timer_add", timer)

    async def guild_count(self, command_id: str):
        payload = {"output": len(self.bot.guilds), "command_id": command_id}
        await self.bot.redis.execute_command(
            "PUBLISH",
            self.bot.config.database.redis_shard_announce_channel,
            json.dumps(payload),
        )

    async def send_latency_and_shard_count(self, command_id: str):
        payload = {
            "output": {
                f"{self.bot.cluster_id}": [
                    self.bot.cluster_name,
                    self.bot.shard_ids,
                    round(self.bot.latency * 1000),
                ]
            },
            "command_id": command_id,
        }
        await self.bot.redis.execute_command(
            "PUBLISH",
            self.bot.config.database.redis_shard_announce_channel,
            json.dumps(payload),
        )

    async def evaluate(self, code, command_id: str):
        if code.startswith("```") and code.endswith("```"):
            code = "\n".join(code.split("\n")[1:-1])
        code = code.strip("` \n")
        payload = {"output": await _evaluate(self.bot, code), "command_id": command_id}
        await self.bot.redis.execute_command(
            "PUBLISH",
            self.bot.config.database.redis_shard_announce_channel,
            json.dumps(payload),
        )

    async def latency(self, command_id: str):
        payload = {
            "output": round(self.bot.latency * 1000, 2),
            "command_id": command_id,
        }
        await self.bot.redis.execute_command(
            "PUBLISH",
            self.bot.config.database.redis_shard_announce_channel,
            json.dumps(payload),
        )

    async def wait_for_dms(self, check, timeout, command_id: str):
        """
        This uses raw message create events
        The predicate is a dictionary with key-values from the event data to match 1:1
        """
        if 0 not in self.bot.shards.keys():
            return

        check = {k: str(v) if isinstance(v, int) else v for k, v in check.items()}

        def data_matches(dict1, dict2):
            for key, val in dict1.items():
                val2 = dict2[key]
                if isinstance(val2, dict):
                    if not data_matches(val, val2):
                        return False
                elif isinstance(val, (list, set)):
                    if val2 not in val:
                        return False
                elif val2 != val:
                    return False
            return True

        def pred(e):
            return data_matches(check, e)

        out = await self.bot.wait_for("raw_message_create", check=pred, timeout=timeout)
        payload = {"output": out, "command_id": command_id}
        await self.bot.redis.execute_command(
            "PUBLISH",
            self.bot.config.database.redis_shard_announce_channel,
            json.dumps(payload),
        )

    async def handler(
            self,
            action: str,
            expected_count: int,
            args: dict = {},
            _timeout: int = 2,
            scope: str = "bot",
    ):  # TODO: think of a better name
        """
        coro
        A function that sends an event and catches all incoming events. Can be used anywhere.

        ex:
            await ctx.send(await bot.cogs["Sharding"].handler("evaluate", 4, {"code": '", ".join([f"{a} - {round(b*1000,2)} ms" for a,b in self.bot.latencies])'}))

        action: str          Must be the function's name you need to call
        expected_count: int  Minimal amount of data to send back. Can be more than the given and less on timeout
        args: dict           A dictionary for the action function's args to pass
        _timeout: int=2      Maximal amount of time waiting for incoming responses
        scope: str="bot"     Can be either launcher or bot. Used to differentiate them
        """
        # Preparation
        command_id = f"{uuid4()}"  # str conversion
        if expected_count > 0:
            self._messages[command_id] = [
                asyncio.Future() for _ in range(expected_count)
            ]  # must create it (see the router)
            results = []

        # Sending
        payload = {"scope": scope, "action": action, "command_id": command_id}
        if args:
            payload["args"] = args
        await self.bot.redis.execute_command(
            "PUBLISH",
            self.bot.config.database.redis_shard_announce_channel,
            json.dumps(payload),
        )

        if expected_count > 0:
            # Message collector
            try:
                done, _ = await asyncio.wait(
                    self._messages[command_id], timeout=_timeout
                )
                for fut in done:
                    results.append(fut.result())
            except asyncio.TimeoutError:
                pass
            del self._messages[command_id]
            return results

    async def on_raw_interaction(self, interaction_data: dict[str, Any]) -> None:
        # Method called when a DM interaction is received
        payload = {"type": "raw_interaction", "data": interaction_data}
        await self.bot.redis.execute_command(
            "PUBLISH",
            self.bot.config.database.redis_shard_announce_channel,
            json.dumps(payload),
        )

    async def _get_timers_view_preference(self, user_id: int) -> bool:
        try:
            preference = await self.bot.pool.fetchval(
                'SELECT "timers_v2" FROM profile WHERE "user"=$1;',
                user_id,
            )
        except asyncpg.UndefinedColumnError:
            return True
        return True if preference is None else bool(preference)

    async def _set_timers_view_preference(
        self,
        user_id: int,
        use_new_view: bool,
    ) -> str:
        try:
            updated = await self.bot.pool.fetchval(
                'UPDATE profile SET "timers_v2"=$1 WHERE "user"=$2 RETURNING 1;',
                use_new_view,
                user_id,
            )
        except asyncpg.UndefinedColumnError:
            return "missing_column"
        return "updated" if updated else "missing_profile"

    @commands.command(
        aliases=["cooldowns", "t", "cds"], brief=_("Lists all your cooldowns")
    )
    @locale_doc
    async def timers(self, ctx, view: str = None):
        _(
            """Lists all your cooldowns, including your adventure timer.

            Use `{prefix}timers old`, `{prefix}timers new`, or `{prefix}timers toggle`
            to save your preferred layout."""
        )

        if view is not None:
            normalized_view = view.strip().lower()
            valid_views = {"old", "legacy", "new", "modern", "toggle"}
            if normalized_view not in valid_views:
                return await ctx.send(
                    _(
                        "Use `{prefix}timers`, `{prefix}timers old`,"
                        " `{prefix}timers new`, or `{prefix}timers toggle`."
                    ).format(prefix=ctx.clean_prefix)
                )

            current_preference = await self._get_timers_view_preference(ctx.author.id)
            use_new_view = (
                not current_preference
                if normalized_view == "toggle"
                else normalized_view in {"new", "modern"}
            )
            save_status = await self._set_timers_view_preference(
                ctx.author.id,
                use_new_view,
            )
            if save_status == "missing_column":
                return await ctx.send(
                    _(
                        "The timers preference column is missing. Run the shard"
                        " communication migration first."
                    )
                )
            if save_status == "missing_profile":
                return await ctx.send(
                    _(
                        "You need a character before you can save a timers layout"
                        " preference."
                    )
                )
            return await ctx.send(
                _("Your timers view is now set to **{style}**.").format(
                    style=_("new") if use_new_view else _("old")
                )
            )

        def normalize_cmd_id(raw_cmd: str) -> str:
            cmd = " ".join(raw_cmd.strip().lower().split())
            legacy_aliases = {
                "cbt_begin": "couples_battletower begin",
                "cbt_start": "couples_battletower start",
                "dragon_party": "dragonchallenge party",
                "jurytower_fight": "jurytower fight",
                "petstournament": "pets tournament",
                "process_splice": "process splice",
            }
            cmd = legacy_aliases.get(cmd, cmd)
            while cmd.startswith("pets pets "):
                cmd = f"pets {cmd[len('pets pets '):]}"
            if cmd.startswith("pet "):
                cmd = f"pets {cmd[4:]}"
            bare_pet_commands = {
                "alias",
                "feed",
                "pet",
                "play",
                "rename",
                "sell",
                "trade",
                "train",
                "treat",
            }
            if cmd in bare_pet_commands:
                cmd = f"pets {cmd}"
            return cmd

        def format_duration(total_seconds: int) -> str:
            total_seconds = max(0, int(total_seconds))
            days, remainder = divmod(total_seconds, 86400)
            hours, remainder = divmod(remainder, 3600)
            minutes, seconds = divmod(remainder, 60)

            parts = []
            if days:
                parts.append(f"{days}d")
            if hours or days:
                parts.append(f"{hours}h")
            if minutes or hours or days:
                parts.append(f"{minutes}m")
            if seconds and not days:
                parts.append(f"{seconds}s")
            return " ".join(parts) if parts else "0s"

        def format_delta(delta: timedelta) -> str:
            return format_duration(int(delta.total_seconds()))

        def display_name(cmd: str) -> str:
            names = {
                "adventure": _("Adventure"),
                "activeadventure": _("Active Adventure"),
                "activebattle": _("Active Battle"),
                "all": _("All Dailies"),
                "battle": _("Battle"),
                "bless": _("Bless"),
                "boosterdaily": _("Booster Daily"),
                "brackettournament": _("Bracket Tournament"),
                "channel": _("Challenge Channel"),
                "consume": _("Consume"),
                "couples_battletower begin": _("Couples Battle Tower Begin"),
                "couples_battletower start": _("Couples Battle Tower Start"),
                "create_party": _("Create Party"),
                "cratesdaily": _("Crates Daily"),
                "daily": _("Daily"),
                "defendforge": _("Defend Forge"),
                "dragonchallenge party": _("Dragon Challenge Party"),
                "eidolithmask": _("Eidolith Mask"),
                "familyevent": _("Family Event"),
                "follow": _("Follow God"),
                "forgegodpet": _("Forge God Pet"),
                "forgestatus": _("Forge Status"),
                "gmsign": _("GM Sign"),
                "godlocks": _("God Locks"),
                "highfive": _("High Five"),
                "increase": _("Raid Increase"),
                "juggernaut": _("Juggernaut"),
                "juggernaut2": _("Juggernaut II"),
                "jurytower fight": _("Jury Tower Fight"),
                "merchall": _("Merch All"),
                "mydefenders": _("My Defenders"),
                "offercrate": _("Offer Crate"),
                "pets alias": _("Alias"),
                "pets feed": _("Feed"),
                "pets pet": _("Pet"),
                "pets play": _("Play"),
                "pets rename": _("Rename"),
                "pets sell": _("Sell"),
                "pets trade": _("Trade"),
                "pets train": _("Train"),
                "pets treat": _("Treat"),
                "pets tournament": _("Pets Tournament"),
                "process splice": _("Process Splice"),
                "pve": _("PvE"),
                "raidbattle": _("Raid Battle"),
                "raidbattle2v1": _("Raid Battle 2v1"),
                "raidbattle2v2": _("Raid Battle 2v2"),
                "raidtournament": _("Raid Tournament"),
                "redeemdc": _("Redeem Dragon Coins"),
                "redeemweapontokens": _("Redeem Weapon Tokens"),
                "recruitdefender": _("Recruit Defender"),
                "sacrificeexchange": _("Sacrifice Exchange"),
                "sell_resources": _("Sell Resources"),
                "shotgunroulette": _("Shotgun Roulette"),
                "soulforge": _("Soulforge"),
                "soulforgeguide": _("Soulforge Guide"),
                "soullorebook": _("Soul Lorebook"),
                "speaktomorrigan": _("Speak to Morrigan"),
                "splice": _("Splice"),
                "splicestatus": _("Splice Status"),
                "statpointsredeem": _("Redeem Stat Points"),
                "takeseat": _("Take Seat"),
                "trickortreat": _("Trick or Treat"),
                "upgradeweapon": _("Upgrade Weapon"),
                "weaponlock": _("Weapon Lock"),
                "weaponunlock": _("Weapon Unlock"),
                "_buy": _("Seasonal Buy"),
                "_class": _("Class"),
                "_open": _("Seasonal Open"),
                "child": _("Child"),
                "class": _("Class"),
                "collect": _("Collect"),
                "create": _("Create"),
                "date": _("Date"),
                "fight": _("Fight"),
                "fun": _("Fun"),
                "gift": _("Gift"),
                "hunt": _("Hunt"),
                "pray": _("Pray"),
                "race": _("Race"),
                "sacrifice": _("Sacrifice"),
                "scout": _("Scout"),
                "steal": _("Steal"),
                "tournament": _("Tournament"),
                "valentine": _("Valentine"),
                "vote": _("Vote"),
            }
            return names.get(cmd, cmd.replace("_", " ").title())

        def category_for(cmd: str) -> str:
            challenge_commands = {
                "adventure",
                "activeadventure",
                "activebattle",
                "battle",
                "brackettournament",
                "channel",
                "couples_battletower begin",
                "couples_battletower start",
                "create_party",
                "dragonchallenge party",
                "fight",
                "godlocks",
                "increase",
                "juggernaut",
                "juggernaut2",
                "jurytower fight",
                "pets tournament",
                "pve",
                "raidbattle",
                "raidbattle2v1",
                "raidbattle2v2",
                "raidtournament",
                "scout",
                "shotgunroulette",
                "tournament",
            }
            social_commands = {
                "bite",
                "bonk",
                "child",
                "cuddle",
                "date",
                "familyevent",
                "highfive",
                "hug",
                "kiss",
                "lick",
                "nuzzle",
                "pat",
                "poke",
                "punch",
                "slap",
                "tickle",
                "wave",
            }
            economy_commands = {
                "gift",
                "merchant",
                "merchall",
                "offer",
                "offercrate",
                "redeemdc",
                "redeemweapontokens",
                "sell_resources",
                "sellcrate",
                "slots",
                "takeseat",
                "trader",
                "weaponlock",
                "weaponunlock",
            }
            progression_commands = {
                "_class",
                "alias",
                "bless",
                "class",
                "consume",
                "create",
                "defendforge",
                "eidolithmask",
                "equip",
                "follow",
                "forgegodpet",
                "forgestatus",
                "gmsign",
                "merge",
                "message",
                "mydefenders",
                "process splice",
                "race",
                "recruitdefender",
                "repairforge",
                "soulforge",
                "soulforgeguide",
                "soullorebook",
                "speaktomorrigan",
                "splice",
                "splicestatus",
                "statpointsredeem",
                "upgradeweapon",
            }
            daily_event_commands = {
                "_buy",
                "_open",
                "all",
                "boosterdaily",
                "collect",
                "cratesdaily",
                "daily",
                "pray",
                "sacrifice",
                "sacrificeexchange",
                "trickortreat",
                "valentine",
                "vote",
            }

            if cmd in {
                "activeadventure",
                "activebattle",
            } or cmd in challenge_commands:
                return "challenges"
            if cmd in social_commands:
                return "social"
            if cmd.startswith("pets "):
                return "pets"
            if cmd in economy_commands:
                return "economy"
            if cmd in progression_commands or cmd in {"fun", "hunt", "steal"}:
                return "progression"
            if cmd in daily_event_commands:
                return "daily_events"
            return "other"

        def chunk_lines(lines: list[str], max_length: int = 1024) -> list[str]:
            chunks = []
            current_chunk = []
            current_length = 0

            for line in lines:
                line_length = len(line) + 1
                if current_chunk and current_length + line_length > max_length:
                    chunks.append("\n".join(current_chunk))
                    current_chunk = [line]
                    current_length = line_length
                    continue
                current_chunk.append(line)
                current_length += line_length

            if current_chunk:
                chunks.append("\n".join(current_chunk))
            return chunks

        cooldowns = await self.bot.redis.execute_command("KEYS", f"cd:{ctx.author.id}:*")
        adv = await self.bot.get_adventure(ctx.author)
        use_new_view = await self._get_timers_view_preference(ctx.author.id)

        if not use_new_view:
            emoji_map = {
                "battle": "⚔️",
                "raidbattle": "⚔️",
                "child": "❤️",
                "familyevent": "❤️",
                "steal": "🔒",
                "class": "🛡️",
                "fun": "🐾",
                "activeadventure": "🏞️",
                "activebattle": "⚔️",
                "date": "❤️",
                "tournament": "🏆",
                "raidtournament": "🏆",
                "bless": "🙏",
                "pve": "⚔️",
                "scout": "🐾",
                "dragonchallenge party": "❄️",
                "pets feed": "🐾",
                "pets train": "🐾",
                "pets play": "🐾",
                "pets trade": "💰",
                "pets treat": "🐾",
                "pets pet": "🐾",
            }

            general_cooldowns = []
            battle_cooldowns = []
            family_cooldowns = []
            class_cooldowns = []
            adventure_cooldowns = []
            pets_cooldowns = []

            if not cooldowns and (not adv or adv[2]):
                embed = discord.Embed(
                    title=_("Cooldowns"),
                    description=_("You don't have any active cooldowns at the moment. 🕒"),
                    color=discord.Color.green(),
                )
                return await ctx.send(embed=embed)

            max_length = 0
            message_lengths = []
            for key in cooldowns:
                key = key.decode()
                cooldown = await self.bot.redis.execute_command("TTL", key)
                cmd = key.replace(f"cd:{ctx.author.id}:", "").lower()
                formatted_time = timedelta(seconds=int(cooldown))

                if cmd in ["battle", "raidbattle", "tournament", "raidtournament"]:
                    category_cooldowns = battle_cooldowns
                elif cmd in ["child", "familyevent", "date"]:
                    category_cooldowns = family_cooldowns
                elif cmd in ["pets feed", "pets train", "pets play", "pets trade", "pets treat", "pets pet"]:
                    category_cooldowns = pets_cooldowns
                elif cmd in ["class", "fun", "hunt", "steal", "bless", "gift", "scout"]:
                    category_cooldowns = class_cooldowns
                elif cmd in ["adventure", "activebattle", "pve", "dragonchallenge party", "activeadventure", "battletower fight"]:
                    category_cooldowns = adventure_cooldowns
                else:
                    category_cooldowns = general_cooldowns

                emoji = emoji_map.get(cmd, "⏳")
                cooldown_message = f"{emoji} • **`{cmd.capitalize()}`** is on cooldown and will be available after {formatted_time}"
                category_cooldowns.append(cooldown_message)
                message_lengths.append(len(cooldown_message))
                max_message_length = max(message_lengths)

            embed = discord.Embed(
                title=_("Cooldowns"),
                color=discord.Color.purple(),
            )

            def add_category_fields(embed, category_list, category_name):
                if not category_list:
                    return

                chunks = chunk_lines(category_list)
                for index, chunk in enumerate(chunks):
                    field_name = category_name if index == 0 else f"{category_name} (cont.)"
                    embed.add_field(name=field_name, value=chunk, inline=False)
                return len(chunks) > 0

            has_content = False

            if general_cooldowns:
                add_category_fields(embed, general_cooldowns, _("General Cooldowns"))
                has_content = True

            if battle_cooldowns:
                if has_content:
                    embed.add_field(name="\u200B", value="\n", inline=False)
                add_category_fields(embed, battle_cooldowns, _("Battle Cooldowns"))
                has_content = True

            if family_cooldowns:
                if has_content:
                    embed.add_field(name="\u200B", value="\n", inline=False)
                add_category_fields(embed, family_cooldowns, _("Family Cooldowns"))
                has_content = True

            if pets_cooldowns:
                if has_content:
                    embed.add_field(name="\u200B", value="\n", inline=False)
                add_category_fields(embed, pets_cooldowns, _("Pets Cooldowns"))
                has_content = True

            if class_cooldowns:
                if has_content:
                    embed.add_field(name="\u200B", value="\n", inline=False)
                add_category_fields(embed, class_cooldowns, _("Class Cooldowns"))
                has_content = True

            if adventure_cooldowns:
                if has_content:
                    embed.add_field(name="\u200B", value="\n", inline=False)
                add_category_fields(embed, adventure_cooldowns, _("Adventure Cooldowns"))
                has_content = True

            if adv and not adv[2]:
                if has_content:
                    embed.add_field(name="\u200B", value="\n", inline=False)
                adventure_message = _("⏳ Adventure is running and will be done after {time}").format(
                    time=adv[1]
                )
                embed.add_field(
                    name=_("Adventure Status"),
                    value=adventure_message,
                    inline=False,
                )

            return await ctx.send(embed=embed)

        normalized_cooldowns: dict[str, int] = {}
        for key in cooldowns:
            key = key.decode()
            cooldown = await self.bot.redis.execute_command("TTL", key)
            try:
                cooldown_seconds = int(cooldown)
            except (TypeError, ValueError):
                continue
            if cooldown_seconds <= 0:
                continue

            raw_cmd = key.replace(f"cd:{ctx.author.id}:", "")
            cmd = normalize_cmd_id(raw_cmd)
            previous = normalized_cooldowns.get(cmd)
            if previous is None or cooldown_seconds > previous:
                normalized_cooldowns[cmd] = cooldown_seconds

        has_ready_adventure = bool(adv and adv[2])
        if not normalized_cooldowns and not adv:
            return await ctx.send(
                _("You don't have any active cooldown at the moment.")
            )

        sections = {
            "challenges": [],
            "social": [],
            "pets": [],
            "economy": [],
            "progression": [],
            "daily_events": [],
            "other": [],
        }

        for cmd, cooldown_seconds in normalized_cooldowns.items():
            section = category_for(cmd)
            sections[section].append(
                (
                    cooldown_seconds,
                    _("• **{name}**: `{time}`").format(
                        name=display_name(cmd),
                        time=format_duration(cooldown_seconds),
                    ),
                )
            )

        if adv:
            if has_ready_adventure:
                sections["challenges"].append(
                    (-1, _("• **Adventure Ready**: claim it whenever you want"))
                )
            else:
                sections["challenges"].append(
                    (
                        int(adv[1].total_seconds()),
                        _("• **Current Adventure**: `{time}` remaining").format(
                            time=format_delta(adv[1])
                        ),
                    )
                )

        total_entries = sum(len(section_lines) for section_lines in sections.values())
        embed = discord.Embed(
            title=_("Your Cooldowns"),
            colour=self.bot.config.game.primary_colour,
        )
        embed.set_author(
            name=str(ctx.author),
            icon_url=ctx.author.display_avatar.url,
        )

        if total_entries == 0:
            embed.description = _("You don't have any active cooldowns right now.")
            embed.set_footer(text=_("Everything is ready to use."))
            return await ctx.send(embed=embed)

        section_meta = [
            ("challenges", "🗺️", _("Adventures & Challenges")),
            ("social", "❤️", _("Family & Social")),
            ("pets", "🐾", _("Pets & Companions")),
            ("economy", "💰", _("Economy & Trading")),
            ("progression", "🛠️", _("Progression & Forge")),
            ("daily_events", "📅", _("Dailies, Faith & Events")),
            ("other", "⏳", _("Other")),
        ]

        rendered_sections = []
        for key, emoji, title in section_meta:
            entries = sorted(sections[key], key=lambda entry: entry[0])
            if not entries:
                continue
            lines = [line for _, line in entries]
            heading = f"{emoji} {title} ({len(lines)})"
            rendered_sections.append((heading, lines))

        section_blocks = [
            f"**{heading}**\n" + "\n".join(lines)
            for heading, lines in rendered_sections
        ]
        description = "\n\n".join(section_blocks)

        if len(description) <= 4096:
            embed.description = description
        else:
            for heading, lines in rendered_sections:
                chunks = chunk_lines(lines)
                for index, chunk in enumerate(chunks):
                    field_name = heading if index == 0 else _("{} (cont.)").format(heading)
                    embed.add_field(name=field_name, value=chunk, inline=False)

        embed.set_footer(text=_("Sorted by time remaining"))
        await ctx.send(embed=embed)

    @commands.command(aliases=["botstatus", "shards"], brief=_("Show the clusters"))
    @locale_doc
    async def clusters(self, ctx):
        _("""Lists all clusters and their current status.""")
        launcher_res = await self.handler("statuses", 1, scope="launcher")
        if not launcher_res:
            return await ctx.send(_("Launcher is dead, that is really bad."))
        process_status = launcher_res[0]
        process_res = await self.handler(
            "send_latency_and_shard_count", self.bot.cluster_count, scope="bot"
        )
        actual_status = []
        for cluster_id, cluster_data in process_status.items():
            process_data = discord.utils.find(lambda x: cluster_id in x, process_res)
            if process_data:
                cluster_data["latency"] = f"{process_data[cluster_id][2]}ms"
            else:
                cluster_data["latency"] = "NaN"
            cluster_data["cluster_id"] = cluster_id
            cluster_data["started_at"] = datetime.fromtimestamp(
                cluster_data["started_at"]
            )
            actual_status.append(cluster_data)
        # actual_status.keys = active: bool, status: str, name: str, started_at: float, latency: str, cluster_id: int, shard_list: list[int]
        status = "\n".join(
            [
                f"Cluster #{i['cluster_id']} ({i['name']}), shards"
                f" {nice_join(i['shard_list'])}:"
                f" {'Active' if i['active'] else 'Inactive'} {i['status']}, latency"
                f" {i['latency']}. Started at: {i['started_at']}"
                for i in actual_status
            ]
        )
        await ctx.send(status)


async def setup(bot):
    await bot.add_cog(Sharding(bot))

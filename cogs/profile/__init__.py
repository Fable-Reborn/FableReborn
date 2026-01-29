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
import re

import discord
import io
from io import BytesIO

from aiohttp import ContentTypeError
from discord import Embed
from discord.ext import commands

from classes.badges import Badge
from classes.bot import Bot
from classes.classes import from_string as class_from_string
from classes.context import Context
from classes.converters import IntFromTo, MemberWithCharacter, UserWithCharacter
from classes.items import ALL_ITEM_TYPES, ItemType
from cogs.adventure import ADVENTURE_NAMES
from cogs.help import chunks
from cogs.shard_communication import user_on_cooldown as user_cooldown
from utils import checks, colors
from utils import misc as rpgtools
from utils.checks import is_gm
from utils.i18n import _, locale_doc


class Profile(commands.Cog):
    def __init__(self, bot: Bot) -> None:
        self.bot = bot

    @checks.has_no_char()
    @user_cooldown(3600)
    @commands.command(aliases=["new", "c", "start"], brief=_("Create a new character"))
    @locale_doc
    async def create(self, ctx, *, name: str = None):
        _(
            """`[name]` - The name to give your character; will be interactive if not given

            Create a new character and start playing IdleRPG.

            (This command has a cooldown of 1 hour.)"""
        )

        from discord import Embed

        if not name:
            # Create an embed with a title and description
            embed = Embed(
                title="Character Creation",
                description=(
                    "What shall your character's name be? (Minimum 3 Characters, Maximum 20)\n\n"
                    "**Please note that with the creation of a character, you agree to these rules:**\n"
                    "1) Only up to two characters per individual\n"
                    "2) No abusing or benefiting from bugs or exploits\n"
                    "3) Be friendly and kind to other players\n"
                    "4) Trading in-game content for anything outside of the game is prohibited\n\n"
                    "IdleRPG is a global bot, your characters are valid everywhere"
                ),
                color=0x00FF00  # You can customize the color of the embed here
            )

            # Send the embed message
            await ctx.send(embed=embed)



            # Send an additional message asking for the character's name
            name_msg = await ctx.send(_("Please reply with your character's name within 60 seconds."))

            def mycheck(amsg):
                return amsg.author == ctx.author and amsg.channel == ctx.channel

            try:
                name_response = await self.bot.wait_for("message", timeout=60, check=mycheck)
            except asyncio.TimeoutError:
                await ctx.send(_("Timeout expired. Please retry!"))
                await self.bot.reset_cooldown(ctx)
                return

            name = name_response.content
        else:
            if len(name) < 3 or len(name) > 20:
                await ctx.send(_("Character names must be at least 3 characters and up to 20."))
                await self.bot.reset_cooldown(ctx)
                return

        if "`" in name:
            await ctx.send(_("Illegal character (`) found in the name. Please try again and choose another name."))
            await self.bot.reset_cooldown(ctx)
            return

        # Check if user exists in the second database and offer migration if needed
        async with self.bot.second_pool.acquire() as conn:
            result = await conn.fetchrow('SELECT "money", "xp" FROM profile WHERE "user" = $1', ctx.author.id)

        if result:
            money = result['money']
            xp = result['xp']
            money = min(money, 300000)
            xp = min(xp, 5475604)

            from discord import Embed
            embed = Embed(
                title="Migration Details",
                description=(
                    "Here's what will and won't be migrated to your new character:"
                    "\n\n**Weapons:** Won't be migrated"
                    "\n**Raid Stats:** Won't be migrated"
                    "\n**Favor:** Won't be migrated"
                    "\n**XP:** Will be migrated (Up to level 30 cap)"
                    "\n**Money:** Will be migrated ($300,000 Max)"
                    "\n\nYou will only be given this option once."
                ),
                color=0x00ff00  # You can customize the color as needed
            )

            # Send the embed message
            await ctx.send(embed=embed)
            Level = int(rpgtools.xptolevel(xp))
            # Use ctx.confirm for migration confirmation
            if not await ctx.confirm(
                    _(
                        "It looks like you already have data in Idle's database. Do you want to migrate your XP and money to this new character?"
                        f"\n\nCharacter Level: **{Level}** with a small fortune of **${money}**."
                    )
            ):
                await ctx.send(_("Migration cancelled. Creating your new character without migration."))
                await self.create_character_without_migration(ctx, name)
            else:
                await self.migrate_and_create_character(ctx, name, xp, money)
        else:
            # Create the new character if no data exists in the second database
            await self.create_character_without_migration(ctx, name)

    async def create_character_without_migration(self, ctx, name):

        async with self.bot.pool.acquire() as primary_conn:
            async with primary_conn.transaction():
                await primary_conn.execute(
                    "INSERT INTO profile VALUES ($1, $2, $3, $4);",
                    ctx.author.id,
                    name,
                    100,
                    0,
                )
                await self.bot.create_item(
                    name=_("Starter Sword"),
                    value=0,
                    type_="Sword",
                    element="fire",
                    damage=3.0,
                    armor=0.0,
                    owner=ctx.author,
                    hand="any",
                    equipped=True,
                    conn=primary_conn,
                )
                await self.bot.create_item(
                    name=_("Starter Shield"),
                    value=0,
                    type_="Shield",
                    element="fire",
                    damage=0.0,
                    armor=3.0,
                    owner=ctx.author,
                    hand="left",
                    equipped=True,
                    conn=primary_conn,
                )
                await self.bot.log_transaction(
                    ctx,
                    from_=1,
                    to=ctx.author.id,
                    subject="Starting out",
                    data={"Gold": 100},
                    conn=primary_conn,
                )
                await primary_conn.execute(
                    'UPDATE profile SET "discordtag" = $1 WHERE "user" = $2',
                    str(ctx.author), ctx.author.id
                )

                async with self.bot.second_pool.acquire() as secondary_conn:
                    await secondary_conn.execute('DELETE FROM profile WHERE "user" = $1', ctx.author.id)

        await ctx.send(
            _(
                "Successfully created your new character **{name}**! Now use"
                " `{prefix}profile` to view your character!"
            ).format(name=name, prefix=ctx.clean_prefix)
        )

    async def migrate_and_create_character(self, ctx, name, xp, money):
        try:
            Level = int(rpgtools.xptolevel(xp))
            Statpoints = Level // 2
            # Convert user ID to integer if needed
            user_id = int(ctx.author.id)

            async with self.bot.pool.acquire() as primary_conn:
                async with primary_conn.transaction():
                    await primary_conn.execute(
                        'INSERT INTO profile ("user", name, xp, money, statpoints, resetpotion) VALUES ($1, $2, $3, $4, $5, $6);',
                        user_id,  # Integer
                        name,
                        xp,
                        money,
                        Statpoints,
                        1,
                    )
                    await self.bot.create_item(
                        name=_("Starter Sword"),
                        value=0,
                        type_="Sword",
                        element="fire",
                        damage=3.0,
                        armor=0.0,
                        owner=ctx.author,
                        hand="any",
                        equipped=True,
                        conn=primary_conn,
                    )
                    await self.bot.create_item(
                        name=_("Starter Shield"),
                        value=0,
                        type_="Shield",
                        element="fire",
                        damage=0.0,
                        armor=3.0,
                        owner=ctx.author,
                        hand="left",
                        equipped=True,
                        conn=primary_conn,
                    )
                    await self.bot.log_transaction(
                        ctx,
                        from_=1,
                        to=user_id,
                        subject="Starting out",
                        data={"Gold": 100},
                        conn=primary_conn,
                    )
                    await primary_conn.execute(
                        'UPDATE profile SET "discordtag" = $1 WHERE "user" = $2',
                        str(ctx.author),  # Integer
                        user_id
                    )

            # Delete data from the second database
            async with self.bot.second_pool.acquire() as secondary_conn:
                await secondary_conn.execute('DELETE FROM profile WHERE "user" = $1', user_id)

            await ctx.send(
                _(
                    "Successfully migrated your data and created your new character **{name}**! Now use"
                    " `{prefix}profile` to view your character!"
                ).format(name=name, prefix=ctx.clean_prefix)
            )
        except Exception as e:
            import traceback
            error_message = f"Error occurred: {e}\n"
            error_message += traceback.format_exc()
            await ctx.send(error_message)
            print(error_message)

    @is_gm()
    @commands.command(name="check_user", brief="Check if your ID exists in the second database")
    async def check_user(self, ctx):
        user_id = ctx.author.id

        # Acquire a connection from the second database pool
        async with self.bot.second_pool.acquire() as conn:
            # Check if the user's ID exists in the `profile` table
            result = await conn.fetchval('SELECT 1 FROM profile WHERE "user" = $1', user_id)

        if result:
            await ctx.send(f"Your ID `{user_id}` exists in the second database!")
        else:
            await ctx.send(f"Your ID `{user_id}` does not exist in the second database.")


    @commands.command(name="profilepref")
    async def profilepref_command(self, ctx, preference: int):
        if preference == 1:
            new_profilestyle = False
            new_profilestyleText = "the new format"
        elif preference == 2:
            new_profilestyle = True
            new_profilestyleText = "the old format"
        else:
            await ctx.send("Invalid preference value. Use `1` for the new style or `2` for the old style.")
            return

        # Update the profilestyle column in the database
        async with self.bot.pool.acquire() as conn:
            update_query = 'UPDATE profile SET profilestyle = $1 WHERE "user" = $2'
            await conn.execute(update_query, new_profilestyle, ctx.author.id)

        await ctx.send(f"Profile preference updated to {new_profilestyleText}")

    @commands.command(aliases=["me", "p"], brief=_("View someone's profile"))
    @locale_doc
    async def profile(self, ctx, *, person: str = None):
        _(
            """`[person]` - The person whose profile to view; defaults to oneself

            View someone's profile. This will send an image.`"""
        )


        try:
            if person is None:
                person = str(ctx.author.id)

            id_pattern = re.compile(r'^\d{17,19}$')
            mention_pattern = re.compile(r'<@!?(\d{17,19})>')
            match = mention_pattern.match(person)

            if match:
                person = int(match.group(1))
                person = await self.bot.fetch_user(int(person))

            elif id_pattern.match(person):
                person = await self.bot.fetch_user(int(person))
            else:
                async with self.bot.pool.acquire() as conn:
                    query = 'SELECT "user" FROM profile WHERE discordtag = $1'
                    user_id = await conn.fetchval(query, person)
                person = await self.bot.fetch_user(int(user_id))

            targetid = person.id
            discordtag = person.display_name

            async with self.bot.pool.acquire() as conn:
                # Fetch the profilestyle column for the given user by either discordtag or userid
                profilestyle_query = '''
                    SELECT profilestyle FROM profile 
                    WHERE "user" = $1 OR discordtag = $2
                '''
                profilestyle_result = await conn.fetchval(profilestyle_query, targetid, discordtag)

                # Convert the result to a boolean (assuming profilestyle is a boolean column)
                profilestyle = bool(profilestyle_result) if profilestyle_result is not None else False

            if not profilestyle:
                person = person or ctx.author
                targetid = person.id

                async with self.bot.pool.acquire() as conn:
                    profile = await conn.fetchrow(
                        'SELECT p.*, g.name AS guild_name FROM profile p LEFT JOIN guild g ON (g."id"=p."guild") WHERE "user"=$1;',
                        targetid,
                    )

                    if not profile:
                        return await ctx.send(
                            _("**{person}** does not have a character.").format(person=person)
                        )

                    items = await self.bot.get_equipped_items_for(targetid, conn=conn)
                    mission = await self.bot.get_adventure(targetid)

                right_hand = None
                left_hand = None

                any_count = sum(1 for i in items if i["hand"] == "any")
                if len(items) == 2 and any_count == 1 and items[0]["hand"] == "any":
                    items = [items[1], items[0]]

                for i in items:
                    stat = f"{int(i['damage'] + i['armor'])}"
                    if i["hand"] == "both":
                        right_hand = (i["type"], i["name"], stat)
                    elif i["hand"] == "left":
                        left_hand = (i["type"], i["name"], stat)
                    elif i["hand"] == "right":
                        right_hand = (i["type"], i["name"], stat)
                    elif i["hand"] == "any":
                        if right_hand is None:
                            right_hand = (i["type"], i["name"], stat)
                        else:
                            left_hand = (i["type"], i["name"], stat)

                color = profile["colour"]
                color = [color["red"], color["green"], color["blue"], color["alpha"]]
                embed_color = discord.Colour.from_rgb(color[0], color[1], color[2])
                classes = [class_from_string(c) for c in profile["class"]]
                icons = [c.get_class_line_name().lower() if c else "none" for c in classes]

                guild_rank = None if not profile["guild"] else profile["guildrank"]

                marriage = (
                    await rpgtools.lookup(self.bot, profile["marriage"], return_none=True)
                    if profile["marriage"]
                    else None
                )

                if mission:
                    adventure_name = ADVENTURE_NAMES[mission[0]]
                    adventure_time = f"{mission[1]}" if not mission[2] else _("Finished")
                else:
                    adventure_name = None
                    adventure_time = None

                badge_val = Badge.from_db(profile["badges"])
                if badge_val:
                    badges = badge_val.to_items_lowercase()
                else:
                    badges = []

                if targetid == 295173706496475131:

                    async with self.bot.trusted_session.post(
                            f"http://127.0.0.1:3000/api/genprofile",
                            json={
                                "name": profile["name"],
                                "color": color,
                                "image": profile["background"],
                                "race": profile["race"],
                                "classes": profile["class"],
                                "profession": "Novice Planter",
                                "class_icons": icons,
                                "left_hand_item": left_hand,
                                "right_hand_item": right_hand,
                                "level": f"{rpgtools.xptolevel(profile['xp'])}",
                                "guild_rank": guild_rank,
                                "guild_name": profile["guild_name"],
                                "money": f"{profile['money']}",
                                "pvp_wins": f"{profile['pvpwins']}",
                                "marriage": marriage,
                                "god": profile["god"] or _("No God"),
                                "adventure_name": adventure_name,
                                "adventure_time": adventure_time,
                                "badges": badges,
                            },
                            headers={"Authorization": self.bot.config.external.okapi_token},
                    ) as req:
                        if req.status == 200:
                            raw = await req.read()
                            if raw[:4] == b"\x89PNG" or raw[:2] == b"\xff\xd8":
                                bytebuffer = raw
                            else:
                                try:
                                    img = raw.decode("utf-8").strip()
                                except UnicodeDecodeError:
                                    return await ctx.send(
                                        _("Unexpected internal error when generating image.")
                                    )
                                async with self.bot.trusted_session.get(img) as resp:
                                    bytebuffer = await resp.read()
                                    if resp.status != 200:
                                        return await ctx.send("Error failed to fetch image")

                        else:
                            # Error, means try reading the response JSON error
                            try:
                                error_json = await req.json()
                                async with self.bot.pool.acquire() as conn:
                                    # Update the background column in the profile table for the target user
                                    update_query = 'UPDATE profile SET background = 0 WHERE "user" = $1'
                                    await conn.execute(update_query, targetid)

                                return await ctx.send(
                                    _(
                                        "There was an error processing your image. Reason: {reason} ({detail}). (Due to this, the profile image has been reset)"
                                    ).format(
                                        reason=error_json["reason"], detail=error_json["detail"]
                                    )
                                )
                            except ContentTypeError:
                                return await ctx.send(
                                    _("Unexpected internal error when generating image.")
                                )
                            except Exception:
                                return await ctx.send(_("Unexpected error when generating image."))

                else:
                    async with self.bot.trusted_session.post(
                            f"http://127.0.0.1:3000/api/genprofile",
                            json={
                                "name": profile["name"],
                                "color": color,
                                "image": profile["background"],
                                "race": profile["race"],
                                "classes": profile["class"],
                                "profession": "None",
                                "class_icons": icons,
                                "left_hand_item": left_hand,
                                "right_hand_item": right_hand,
                                "level": f"{rpgtools.xptolevel(profile['xp'])}",
                                "guild_rank": guild_rank,
                                "guild_name": profile["guild_name"],
                                "money": f"{profile['money']}",
                                "pvp_wins": f"{profile['pvpwins']}",
                                "marriage": marriage,
                                "god": profile["god"] or _("No God"),
                                "adventure_name": adventure_name,
                                "adventure_time": adventure_time,
                                "badges": badges,
                            },
                            headers={"Authorization": self.bot.config.external.okapi_token},
                    ) as req:
                        if req.status == 200:
                            raw = await req.read()
                            if raw[:4] == b"\x89PNG" or raw[:2] == b"\xff\xd8":
                                bytebuffer = raw
                            else:
                                try:
                                    img = raw.decode("utf-8").strip()
                                except UnicodeDecodeError:
                                    return await ctx.send(
                                        _("Unexpected internal error when generating image.")
                                    )
                                async with self.bot.trusted_session.get(img) as resp:
                                    bytebuffer = await resp.read()
                                    if resp.status != 200:
                                        return await ctx.send("Error failed to fetch image")

                        else:
                            # Error, means try reading the response JSON error
                            try:
                                error_json = await req.json()
                                async with self.bot.pool.acquire() as conn:
                                    # Update the background column in the profile table for the target user
                                    update_query = 'UPDATE profile SET background = 0 WHERE "user" = $1'
                                    await conn.execute(update_query, targetid)

                                return await ctx.send(
                                    _(
                                        "There was an error processing your image. Reason: {reason} ({detail}). (Due to this, the profile image has been reset)"
                                    ).format(
                                        reason=error_json["reason"], detail=error_json["detail"]
                                    )
                                )
                            except ContentTypeError:
                                return await ctx.send(
                                    _("Unexpected internal error when generating image.")
                                )
                            except Exception:
                                return await ctx.send(_("Unexpected error when generating image."))

                await ctx.send(
                    _("Your Profile:"),
                    file=discord.File(fp=io.BytesIO(bytebuffer), filename="image.png"),
                )
            else:
                person = person or ctx.author
                targetid = person.id

                async with self.bot.pool.acquire() as conn:
                    query = """
                        SELECT g.name
                        FROM profile p
                        JOIN guild g ON p.guild = g.ID
                        WHERE p.user = $1
                    """
                    guild_name = await conn.fetchval(query, targetid)

                ret = await self.bot.pool.fetch(
                    "SELECT ai.*, i.equipped FROM profile p JOIN allitems ai ON"
                    " (p.user=ai.owner) JOIN inventory i ON (ai.id=i.item) WHERE"
                    ' p."user"=$1 AND ((ai."damage"+ai."armor" BETWEEN $2 AND $3) OR'
                    ' i."equipped") ORDER BY i."equipped" DESC, ai."damage"+ai."armor"'
                    " DESC;",
                    targetid,
                    0,
                    160,
                )

                # Assuming you have 'name', 'damage', 'armor', and 'type' columns in 'allitems' table
                equipped_items = [row for row in ret if row['equipped']]

                # Separate variables for up to two equipped items
                item1 = equipped_items[0] if len(equipped_items) >= 1 else {"name": "None Equipped", "damage": 0,
                                                                            "armor": 0,
                                                                            "type": "None"}
                item2 = equipped_items[1] if len(equipped_items) >= 2 else {"name": "None Equipped", "damage": 0,
                                                                            "armor": 0,
                                                                            "type": "None"}

                async with self.bot.pool.acquire() as conn:
                    profile = await conn.fetchrow(
                        'SELECT p.*, g.name AS guild_name FROM profile p LEFT JOIN guild g ON (g."id"=p."guild") WHERE "user"=$1;',
                        targetid,
                    )

                    if not profile:
                        return await ctx.send(
                            _("**{person}** does not have a character.").format(person=person)
                        )

                    items = await self.bot.get_equipped_items_for(targetid, conn=conn)
                    mission = await self.bot.get_adventure(targetid)

                # Apply race bonuses
                race = profile["race"].lower()  # Assuming the race is stored in lowercase in the database

                damage_total = item1["damage"] + item2["damage"]
                armor_total = item1["armor"] + item2["armor"]
                item1_name = item1["name"]
                item2_name = item2["name"]
                item1_type = item1["type"]
                item2_type = item2["type"]

                classes = [class_from_string(c) for c in profile["class"]]
                icons = [c.get_class_line_name().lower() if c else "none" for c in classes]

                # Assuming you have classes with specific weapon type bonuses
                classes = {
                    "raider": {"Axe": 5},
                    "mage": {"Wand": 5},
                    "warrior": {"Sword": 5},
                    "ranger": {"Bow": 10},
                    "reaper": {"Scythe": 10},
                    "paladin": {"Hammer": 5},
                    "thief": {"Knife": 5, "Dagger": 5},
                    "paragon": {"Spear": 5}
                }

                # Initialize bonus
                class_bonus = 0

                # Check if the user has classes and apply the corresponding bonuses
                for class_name in icons:
                    class_info = classes.get(class_name.lower(), {})
                    for item in [item1_type, item2_type]:
                        item_bonus = class_info.get(item, 0)
                        class_bonus += item_bonus

                # Apply the class bonus to the damage total
                damage_total += class_bonus

                if race == "human":
                    armor_total += 2
                    damage_total += 2
                elif race == "orc":
                    armor_total += 4
                elif race == "dwarf":
                    armor_total += 3
                    damage_total += 1
                elif race == "jikill":
                    damage_total += 4
                elif race == "elf":
                    armor_total += 1
                    damage_total += 3
                elif race == "elf":
                    armor_total += 1
                    damage_total -= 3
                elif race == "djinn":
                    armor_total -= 1
                    damage_total += 5
                elif race == "shadeborn":
                    armor_total += 5
                    damage_total -= 1

                right_hand = None
                left_hand = None

                async with self.bot.pool.acquire() as conn:
                    # Check if the user exists in the battletower table
                    level_query = "SELECT level FROM battletower WHERE id = $1"
                    level_result = await conn.fetchval(level_query, targetid)

                    # If the user doesn't exist, set the level to 0
                    level = level_result if level_result is not None else 0

                any_count = sum(1 for i in items if i["hand"] == "any")
                if len(items) == 2 and any_count == 1 and items[0]["hand"] == "any":
                    items = [items[1], items[0]]

                for i in items:
                    stat = f"{int(i['damage'] + i['armor'])}"
                    if i["hand"] == "both":
                        right_hand = (i["type"], i["name"], stat)
                    elif i["hand"] == "left":
                        left_hand = (i["type"], i["name"], stat)
                    elif i["hand"] == "right":
                        right_hand = (i["type"], i["name"], stat)
                    elif i["hand"] == "any":
                        if right_hand is None:
                            right_hand = (i["type"], i["name"], stat)
                        else:
                            left_hand = (i["type"], i["name"], stat)

                color = profile["colour"]
                color = [color["red"], color["green"], color["blue"], color["alpha"]]
                embed_color = discord.Colour.from_rgb(color[0], color[1], color[2])

                guild_rank = None if not profile["guild"] else profile["guildrank"]

                marriage = (
                    await rpgtools.lookup(self.bot, profile["marriage"], return_none=True)
                    if profile["marriage"]
                    else None
                )

                if mission:
                    adventure_name = ADVENTURE_NAMES[mission[0]]
                    adventure_time = f"{mission[1]}" if not mission[2] else _("Finished")
                else:
                    adventure_name = None
                    adventure_time = None

                badge_val = Badge.from_db(profile["badges"])
                if badge_val:
                    badges = badge_val.to_items_lowercase()
                else:
                    badges = []


                async with self.bot.trusted_session.post(
                        f"http://127.0.0.1:3000/api/genprofile",
                        json={
                            "name": profile['name'],
                            "color": color,
                            "image": profile["background"],
                            "race": profile['race'],
                            "classes": profile['class'],
                            "profession": "None",
                            "damage": f"{damage_total}",
                            "defense": f"{armor_total}",
                            "swordName": f"{item1_name}",
                            "shieldName": f"{item2_name}",
                            "level": f"{rpgtools.xptolevel(profile['xp'])}",
                            "guild_rank": guild_rank,
                            "guild": guild_name,
                            "money": profile['money'],
                            "pvpWins": f"{profile['pvpwins']}",
                            "marriage": marriage or _("None"),
                            "god": profile["god"] or _("No God"),
                            "adventure": adventure_name or _("No Mission"),
                            "adventure_time": adventure_time,
                            "icons": icons,
                            "BT": f"{level}"

                        },
                        headers={"Authorization": self.bot.config.external.okapi_token},
                ) as req:
                    img = BytesIO(await req.read())
                    # await ctx.send(f"{profile['class']}")
                    await ctx.send(file=discord.File(fp=img, filename="Profile.png"))
        except Exception as e:
            await ctx.send(e)
    @user_cooldown(86400)
    @commands.command(aliases=["drink"], brief=_("View someone's profile"))
    @locale_doc
    async def consume(self, ctx, *, potion):
        _(
            """`[person]` - The person whose profile to view; defaults to oneself

            View someone's profile. This will send an image.
            For an explanation what all the fields mean, see [this picture](https://wiki.idlerpg.xyz/images/3/35/Profile_explained.png)"""
        )
        try:
            potion = potion.lower()

            async with self.bot.pool.acquire() as conn:
                reset_query = """
                SELECT resetpotion
                FROM profile
                WHERE "user" = $1;
                """
                resetpotion = await conn.fetchval(reset_query, ctx.author.id)

            if not resetpotion:
                await ctx.send("Error: Unable to retrieve reset potion count.")
                await self.bot.reset_cooldown(ctx)
                return

            if resetpotion < 1:
                await ctx.send("You don't have enough reset potions.")
                await self.bot.reset_cooldown(ctx)
                return

            if potion == "reset":
                if not await ctx.confirm(
                        _(
                            f"You are about to consume a `{potion} potion`. Proceed?"
                        ).format(
                            potion=potion
                        )
                ):
                    await ctx.send(_("Class selection cancelled."))
                    return await self.bot.reset_cooldown(ctx)

                async with self.bot.pool.acquire() as conn:
                    query = """
                    SELECT statpoints, statatk, statdef, stathp, resetpotion
                    FROM profile
                    WHERE "user" = $1
                    FOR UPDATE;
                    """

                    profile = await conn.fetchrow(query, ctx.author.id)

                if not profile:
                    return await ctx.send("Profile not found.")

                total_stats = profile["statpoints"] + profile["statatk"] + profile["statdef"] + profile["stathp"]
                async with self.bot.pool.acquire() as conn:
                    # Update the profile
                    update_query = """
                    UPDATE profile
                    SET statatk = 0, statdef = 0, stathp = 0, statpoints = $1, resetpotion = $2
                    WHERE "user" = $3;
                    """

                    await conn.execute(update_query, total_stats, profile["resetpotion"] - 1, ctx.author.id)

                await ctx.send(
                    "Stats updated successfully. As you drink the reset potion, a wave of dizziness washes over you, making the world spin for a moment. You feel disoriented but also strangely invigorated, as if your very being has been refreshed.")

            else:
                await ctx.send("Unknown Potion Type")
                await self.bot.reset_cooldown(ctx)
                return


        except Exception as e:
            import traceback
            error_message = f"Error occurred: {e}\n"
            error_message += traceback.format_exc()
            await ctx.send(error_message)
            print(error_message)

    @commands.command(
        aliases=["p2", "pp"], brief=_("View someone's profile differently")
    )
    @locale_doc
    async def profile2(self, ctx, *, target: str = None):
        _(
            """`[target]` - The person whose profile to view

            View someone's profile. This will send an embed rather than an image and is usually faster."""
        )
        try:
            if target:
                target = target.split()[0]

            if target is None:
                target = str(ctx.author.id)

            id_pattern = re.compile(r'^\d{17,19}$')
            mention_pattern = re.compile(r'<@!?(\d{17,19})>')
            match = mention_pattern.match(target)

            if match:
                target = int(match.group(1))
                target = await self.bot.fetch_user(int(target))

            elif id_pattern.match(target):
                target = await self.bot.fetch_user(int(target))
            else:
                async with self.bot.pool.acquire() as conn:
                    query = 'SELECT "user" FROM profile WHERE discordtag = $1'
                    user_id = await conn.fetchval(query, target)
                target = await self.bot.fetch_user(int(user_id))

            targetid = target.id
            discordtag = target.display_name
        except Exception as e:
            await ctx.send("Unknown User")
            return

        #000000000000000000000000000000000000000000000000000000000000000000000
        target = target or ctx.author
        rank_money, rank_xp = await self.bot.get_ranks_for(target)

        items = await self.bot.get_equipped_items_for(target)
        async with self.bot.pool.acquire() as conn:
            p_data = await conn.fetchrow(
                '''
                        SELECT * FROM profile 
                        WHERE "user" = $1 OR discordtag = $2
                    ''', target.id, discordtag
            )
            if not p_data:
                return await ctx.send(
                    _("**{target}** does not have a character.").format(target=target)
                )
            mission = await self.bot.get_adventure(target)
            guild = await conn.fetchval(
                'SELECT name FROM guild WHERE "id"=$1;', p_data["guild"]
            )
        try:
            colour = p_data["colour"]
            colour = discord.Colour.from_rgb(
                colour["red"], colour["green"], colour["blue"]
            )
        except ValueError:
            colour = 0x000000
        if mission:
            timeleft = str(mission[1]).split(".")[0] if not mission[2] else "Finished"

        right_hand = None
        left_hand = None

        any_count = sum(1 for i in items if i["hand"] == "any")
        if len(items) == 2 and any_count == 1 and items[0]["hand"] == "any":
            items = [items[1], items[0]]

        for i in items:
            if i["hand"] == "both":
                right_hand, left_hand = i, i
            elif i["hand"] == "left":
                left_hand = i
            elif i["hand"] == "right":
                right_hand = i
            elif i["hand"] == "any":
                if right_hand is None:
                    right_hand = i
                else:
                    left_hand = i

        try:
            if "marriage" in p_data:
                discord_id = p_data["marriage"]
                user = await self.bot.fetch_user(discord_id)

                if user:
                    display_name = user.display_name
                else:
                    display_name = "none"
            else:
                display_name = "none"
        except discord.errors.NotFound:
            display_name = "none"
        except Exception as e:
            display_name = "none"
            await ctx.send(f"An error occurred: {e}")

        right_hand = (
            f"{right_hand['name']} - {right_hand['damage'] + right_hand['armor']}"
            if right_hand
            else _("None Equipped")
        )
        left_hand = (
            f"{left_hand['name']} - {left_hand['damage'] + left_hand['armor']}"
            if left_hand
            else _("None Equipped")
        )
        level = rpgtools.xptolevel(p_data["xp"])
        em = discord.Embed(colour=colour, title=f"{target}: {p_data['name']}")
        em.set_thumbnail(url=target.display_avatar.url)
        em.add_field(
            name=_("General"),
            value=_(
                """\
**Money**: `${money}`
**Level**: `{level}`
**Marriage:** `{marriage}`
**Class**: `{class_}`
**Race**: `{race}`
**PvP Wins**: `{pvp}`
**Guild**: `{guild}`"""
            ).format(
                money=p_data["money"],
                level=level,
                marriage=display_name,
                class_="/".join(p_data["class"]),
                race=p_data["race"],
                pvp=p_data["pvpwins"],
                guild=guild,
            ),
        )
        em.add_field(
            name=_("Ranks"),
            value=_("**Richest**: `{rank_money}`\n**XP**: `{rank_xp}`").format(
                rank_money=rank_money, rank_xp=rank_xp
            ),
        )
        em.add_field(
            name=_("Equipment"),
            value=_("Right Hand: {right_hand}\nLeft Hand: {left_hand}").format(
                right_hand=right_hand, left_hand=left_hand
            ),
        )
        if mission:
            em.add_field(name=_("Mission"), value=f"{mission[0]} - {timeleft}")
        await ctx.send(embed=em)

    @checks.has_char()
    @commands.command(brief=_("Show your current luck"))
    @locale_doc
    async def luck(self, ctx):
        _(
            """Shows your current luck value.

            Luck updates once a week for everyone, usually on Monday. It depends on your God.
            Luck influences your adventure survival chances as well as the rewards.

            Luck is decided randomly within the Gods' luck boundaries. You can find your God's boundaries [here](https://wiki.idlerpg.xyz/index.php?title=Gods#List_of_Deities).

            If you have enough favor to place in the top 25 followers, you will gain additional luck:
              - The top 25 to 21 will gain +0.1 luck
              - The top 20 to 16 will gain +0.2 luck
              - The top 15 to 11 will gain +0.3 luck
              - The top 10 to 6 will gain +0.4 luck
              - The top 5 to 1 will gain +0.5 luck

            If you follow a new God (or become Godless), your luck will not update instantly, it will update with everyone else's luck on Monday."""
        )
        try:
            luck_value = float(ctx.character_data["luck"])  # Convert Decimal to float
            if luck_value <= 0.3:
                Luck = 20
            else:
                Luck = ((luck_value - 0.3) / (1.5 - 0.3)) * 80 + 20  # Linear interpolation between 20% and 100%
            Luck = round(Luck, 2)  # Round to two decimal places
            luck_booster = await self.bot.get_booster(ctx.author, "luck")
            if luck_booster:
                Luck += Luck * 0.25  # Add 25% if luck booster is true
                Luck = min(Luck, 100)  # Cap luck at 100%

            if luck_booster:
                calcluck = luck_value * 1.25
            else:
                calcluck = luck_value

            # Assuming Luck is a decimal.Decimal object
            flipped_luck = 100 - float(Luck)
            if flipped_luck < 0:
                flipped_luck = float(0)
            await ctx.send(
                _(
                    "Your current luck multiplier is `{luck}x.` "
                    "This makes your trip chance: `{trip}%`"
                ).format(
                    luck=round(calcluck, 2),
                    trip=round(float(flipped_luck), 2),
                )
            )
        except Exception as e:
            await ctx.send(e)

    @checks.has_char()
    @commands.command(
        aliases=["money", "e", "balance", "bal"], brief=_("Shows your balance")
    )
    @locale_doc
    async def economy(self, ctx):
        _(
            """Shows the amount of money you currently have.

            Among other ways, you can get more money by:
              - Playing adventures
              - Selling unused equipment
              - Gambling"""
        )
        await ctx.send(
            _("You currently have **${money}**, {author}!").format(
                money=ctx.character_data["money"], author=ctx.author.mention
            )
        )

    @is_gm()
    @commands.command()
    async def gmp2(self, ctx, min_xp: int, max_xp: int):
        try:
            async with self.bot.pool.acquire() as conn:
                user_records = await conn.fetch(
                    'SELECT * FROM profile WHERE xp BETWEEN $1 AND $2;', min_xp, max_xp
                )

            for user_record in user_records:
                if user_record['user'] == 1136590782183264308:
                    await ctx.send(f"Skipping processing for user: {user_record['user']} (Fable Bot)")
                    continue

                # Show information about the user being processed
                await ctx.send(f"Processing profile for user: {user_record['user']} XP: {user_record['xp']}")

                target = self.bot.get_user(user_record["user"])

                if target is None:
                    try:
                        # Attempt to fetch the user
                        target = await self.bot.fetch_user(user_record["user"])
                    except discord.NotFound:
                        # If fetch fails, user not found
                        await ctx.send(
                            f"User with ID {user_record['user']} not found. Proceed with a manual check for this user.")
                        continue
                rank_money, rank_xp = await self.bot.get_ranks_for(target)

                items = await self.bot.get_equipped_items_for(target)
                async with self.bot.pool.acquire() as conn:
                    p_data = await conn.fetchrow(
                        'SELECT * FROM profile WHERE "user"=$1;', target.id
                    )
                    if not p_data:
                        return await ctx.send(
                            _("**{target}** does not have a character.").format(target=target)
                        )
                    mission = await self.bot.get_adventure(target)
                    guild = await conn.fetchval(
                        'SELECT name FROM guild WHERE "id"=$1;', p_data["guild"]
                    )
                try:
                    colour = p_data["colour"]
                    colour = discord.Colour.from_rgb(
                        colour["red"], colour["green"], colour["blue"]
                    )
                except ValueError:
                    colour = 0x000000
                if mission:
                    timeleft = str(mission[1]).split(".")[0] if not mission[2] else "Finished"

                right_hand = None
                left_hand = None

                any_count = sum(1 for i in items if i["hand"] == "any")
                if len(items) == 2 and any_count == 1 and items[0]["hand"] == "any":
                    items = [items[1], items[0]]

                for i in items:
                    if i["hand"] == "both":
                        right_hand, left_hand = i, i
                    elif i["hand"] == "left":
                        left_hand = i
                    elif i["hand"] == "right":
                        right_hand = i
                    elif i["hand"] == "any":
                        if right_hand is None:
                            right_hand = i
                        else:
                            left_hand = i

                try:
                    if "marriage" in p_data:
                        discord_id = p_data["marriage"]
                        user = await self.bot.fetch_user(discord_id)

                        if user:
                            display_name = user.display_name
                        else:
                            display_name = "none"
                    else:
                        display_name = "none"
                except discord.errors.NotFound:
                    display_name = "none"
                except Exception as e:
                    display_name = "none"
                    await ctx.send(f"An error occurred: {e}")

                right_hand = (
                    f"{right_hand['name']} - {right_hand['damage'] + right_hand['armor']}"
                    if right_hand
                    else _("None Equipped")
                )
                left_hand = (
                    f"{left_hand['name']} - {left_hand['damage'] + left_hand['armor']}"
                    if left_hand
                    else _("None Equipped")
                )
                level = rpgtools.xptolevel(p_data["xp"])
                em = discord.Embed(colour=colour, title=f"{target}: {p_data['name']}")
                em.set_thumbnail(url=target.display_avatar.url)
                em.add_field(
                    name=_("General"),
                    value=_(
                        """\
        **Money**: `${money}`
        **Level**: `{level}`
        **Marriage:** `{marriage}`
        **Class**: `{class_}`
        **Race**: `{race}`
        **PvP Wins**: `{pvp}`
        **Guild**: `{guild}`"""
                    ).format(
                        money=p_data["money"],
                        level=level,
                        marriage=display_name,
                        class_="/".join(p_data["class"]),
                        race=p_data["race"],
                        pvp=p_data["pvpwins"],
                        guild=guild,
                    ),
                )
                em.add_field(
                    name=_("Ranks"),
                    value=_("**Richest**: `{rank_money}`\n**XP**: `{rank_xp}`").format(
                        rank_money=rank_money, rank_xp=rank_xp
                    ),
                )
                em.add_field(
                    name=_("Equipment"),
                    value=_("Right Hand: {right_hand}\nLeft Hand: {left_hand}").format(
                        right_hand=right_hand, left_hand=left_hand
                    ),
                )
                if mission:
                    em.add_field(name=_("Mission"), value=f"{mission[0]} - {timeleft}")
                await ctx.send(embed=em)
                await asyncio.sleep(2)

            await ctx.send("Profiles processing complete.")

        except Exception as e:
            await ctx.send(f"An error occurred: {e}")

    @checks.has_char()
    @commands.command(brief=_("Show a player's current XP"))
    @locale_doc
    async def xp(self, ctx, user: UserWithCharacter = None):
        _(
            """`[user]` - The player whose XP and level to show; defaults to oneself

            Show a player's XP and level.

            You can gain more XP by:
              - Completing adventures
              - Exchanging loot items for XP"""
        )
        user = user or ctx.author
        if user.id == ctx.author.id:
            points = ctx.character_data["xp"]
            await ctx.send(
                _(
                    "You currently have **{points} XP**, which means you are on Level"
                    " **{level}**. Missing to next level: **{missing}**"
                ).format(
                    points=points,
                    level=rpgtools.xptolevel(points),
                    missing=rpgtools.xptonextlevel(points),
                )
            )
        else:
            points = ctx.user_data["xp"]
            await ctx.send(
                _(
                    "{user} has **{points} XP** and is on Level **{level}**. Missing to"
                    " next level: **{missing}**"
                ).format(
                    user=user,
                    points=points,
                    level=rpgtools.xptolevel(points),
                    missing=rpgtools.xptonextlevel(points),
                )
            )

    def invembed(self, ctx, ret, currentpage, maxpage):
        result = discord.Embed(
            title=_("{user}'s inventory includes").format(user=ctx.disp),
            colour=discord.Colour.blurple(),
        )
        for weapon in ret:
            if weapon["equipped"]:
                eq = _("(**Equipped**)")
            else:
                eq = ""

            # Check if the weapon is locked and add "(locked)" if true
            locked_status = " (locked)" if weapon.get('locked', False) else ""

            statstr = (
                _("Damage: `{damage}`").format(damage=weapon["damage"])
                if weapon["type"] != "Shield"
                else _("Armor: `{armor}`").format(armor=weapon["armor"])
            )
            signature = (
                _("\nSignature: *{signature}*").format(signature=y)
                if (y := weapon["signature"])
                else ""
            )

            result.add_field(
                name=f"{weapon['name']}{locked_status} {eq}",  # Append (locked) if the item is locked
                value=_(
                    "ID: `{id}`, Element: `{element}` Type: `{type_}` (uses {hand} hand(s)) with {statstr}."
                    " Value is **${value}**{signature}"
                ).format(
                    id=weapon["id"],
                    element=weapon["element"],
                    type_=weapon["type"],
                    hand=weapon["hand"],
                    statstr=statstr,
                    value=weapon["value"],
                    signature=signature,
                ),
                inline=False,
            )

        result.set_footer(
            text=_("Page {page} of {maxpages}").format(
                page=currentpage + 1, maxpages=maxpage + 1
            )
        )
        return result

    def invembedd(self, ctx, reset_potions_chunk, amulets, level_candies, premium_consumables, current_page, max_page):
        result = discord.Embed(
            title=_("{user}'s Inventory").format(user=ctx.author.display_name),
            colour=discord.Colour.blurple(),
        )

        # Display equipped amulets first
        if current_page == 0:  # Only show on first page
            equipped_amulets = [a for a in amulets if a['equipped']]
            for amulet in equipped_amulets:
                name = ""
                value = ""
                if amulet['type'] == 'health':
                    name = f"<:balancedamulet:1403792085324267683> HP Amulet (ID: {amulet['id']}) (Equipped)"
                    value = f"Health: **+{amulet.get('hp', 0)}**, Defense: **+{amulet.get('defense', 0)}**, Attack: **+{amulet.get('attack', 0)}**\n"
                elif amulet['type'] == 'defense':
                    name = f"<:defenseamulet:1403791376432496836> Defense Amulet (ID: {amulet['id']}) (Equipped)"
                    value = f"Health: **+{amulet.get('hp', 0)}**, Defense: **+{amulet.get('defense', 0)}**, Attack: **+{amulet.get('attack', 0)}**\n"
                elif amulet['type'] == 'attack':
                    name = f"<:attackamulet:1403791304055591092> Attack Amulet (ID: {amulet['id']}) (Equipped)"
                    value = f"Health: **+{amulet.get('hp', 0)}**, Defense: **+{amulet.get('defense', 0)}**, Attack: **+{amulet.get('attack', 0)}**\n"
                elif amulet['type'] == 'balanced':
                    name = f"<:balancedamulet:1403791341376372886> Balanced Amulet (ID: {amulet['id']}) (Equipped)"
                    value = f"Health: **+{amulet.get('hp', 0)}**, Defense: **+{amulet.get('defense', 0)}**, Attack: **+{amulet.get('attack', 0)}**\n"
                value += f"Tier: {amulet.get('tier', 0)} Value: ${amulet.get('value', 0):,}"
                result.add_field(
                    name=name,
                    value=value,
                    inline=False
                )

        # Display unequipped amulets
        if current_page == 0:  # Only show on first page
            unequipped_amulets = [a for a in amulets if not a['equipped']]
            for amulet in unequipped_amulets:
                name = ""
                value = ""
                if amulet['type'] == 'health':
                    name = f"<:hp_amulet_red_glow:1403792085324267683> HP Amulet (ID: {amulet['id']})"
                    value = f"Health: **+{amulet.get('hp', 0)}**, Defense: **+{amulet.get('defense', 0)}**, Attack: **+{amulet.get('attack', 0)}**\n"
                elif amulet['type'] == 'defense':
                    name = f"<:def_amulet_blue_glow:1403791376432496836> Defense Amulet (ID: {amulet['id']})"
                    value = f"Health: **+{amulet.get('hp', 0)}**, Defense: **+{amulet.get('defense', 0)}**, Attack: **+{amulet.get('attack', 0)}**\n"
                elif amulet['type'] == 'attack':
                    name = f"<:atk_amulet_fixed_glow:1403791304055591092> Attack Amulet (ID: {amulet['id']})"
                    value = f"Health: **+{amulet.get('hp', 0)}**, Defense: **+{amulet.get('defense', 0)}**, Attack: **+{amulet.get('attack', 0)}**\n"
                elif amulet['type'] == 'balanced':
                    name = f"<:balancedamulet:1403791341376372886> Balanced Amulet (ID: {amulet['id']})"
                    value = f"Health: **+{amulet.get('hp', 0)}**, Defense: **+{amulet.get('defense', 0)}**, Attack: **+{amulet.get('attack', 0)}**\n"
                value += f"Tier: {amulet.get('tier', 0)} Value: ${amulet.get('value', 0):,}"
                result.add_field(
                    name=name,
                    value=value,
                    inline=False
                )

        # Display level candies if they exist
        for candy in level_candies:
            if candy['levelcandy'] > 0:
                result.add_field(
                    name="🍬 Level Candy",
                    value=f"Quantity: {candy['levelcandy']}\nGrants one level on use (`$consume candy`)",
                    inline=False
                )
            if candy.get('highqualitylevelcandy', 0) > 0:
                result.add_field(
                    name="🍬 Super Level Candy",
                    value=f"Quantity: {candy['highqualitylevelcandy']}\nGrants two levels on use (`$consume highcandy`)",
                    inline=False
                )

        # Display reset potions
        for reset_potion in reset_potions_chunk:
            result.add_field(
                name="<:Resetpotion2:1403792708279206001> Reset Potion",
                value=f"Quantity: {reset_potion}",
                inline=False
            )

        # Display premium consumables
        for consumable in premium_consumables:
            consumable_type = consumable['consumable_type']
            quantity = consumable['quantity']
            
            if consumable_type == 'pet_age_potion':
                result.add_field(
                    name="<:ageup:1403791288548982935> Pet Age Potion",
                    value=f"Quantity: {quantity}\nInstantly age your pet to the next growth stage (`$consume petage <pet_id>` or `$consume \"pet age potion\" <pet_id>`)",
                    inline=False
                )
            elif consumable_type == 'pet_speed_growth_potion':
                result.add_field(
                    name="<:finalpotion:1403792029653405809> Pet Speed Growth Potion",
                    value=f"Quantity: {quantity}\nDoubles growth speed for a specific pet (`$consume petspeed <pet_id>` or `$consume \"pet speed growth potion\" <pet_id>`)",
                    inline=False
                )
            elif consumable_type == 'pet_xp_potion':
                result.add_field(
                    name="<:splicepotion:1403792828064338011> Pet XP Potion",
                    value=f"Quantity: {quantity}\nGives a pet permanent x2 XP multiplier (`$consume petxp <pet_id>` or `$consume \"pet xp potion\" <pet_id>`)",
                    inline=False
                )
            elif consumable_type == 'splice_final_potion':
                result.add_field(
                    name="🔮 Splice Final Potion",
                    value=f"Quantity: {quantity}\n15% chance for [FINAL] result on next splice (`$consume splicefinal`)",
                    inline=False
                )

        result.set_footer(
            text=_("Page {page} of {maxpages}").format(
                page=current_page + 1, maxpages=max_page + 1
            )
        )
        return result

    @checks.has_char()
    @commands.command(aliases=["i", "inv"], brief=_("Show your gear items"))
    @locale_doc
    async def inventory(self, ctx):
        try:
            await ctx.send(
                "weapons has moved to `$armory` with aliases `$ar` and `$arm` to make room for a future update."
            )
            await ctx.send("Related commands `$consume <type>`")

            async with self.bot.pool.acquire() as conn:
                # Fetch reset potions and level candies
                ret = await conn.fetch(
                    'SELECT resetpotion, levelcandy, highqualitylevelcandy FROM profile WHERE "user" = $1;',
                    ctx.author.id,
                )

                # Fetch amulets
                amulets = await conn.fetch(
                    'SELECT * FROM amulets WHERE user_id = $1 ORDER BY equipped DESC;',
                    ctx.author.id,
                )
                
                # Fetch premium consumables
                premium_consumables = await conn.fetch(
                    'SELECT consumable_type, quantity FROM user_consumables WHERE user_id = $1 AND quantity > 0;',
                    ctx.author.id,
                )

            # Check if inventory is empty
            has_reset_potions = ret and ret[0]['resetpotion'] > 0
            has_level_candy = ret and ret[0]['levelcandy'] > 0
            has_high_candy = ret and ret[0]['highqualitylevelcandy'] > 0
            has_amulets = bool(amulets)
            has_premium = bool(premium_consumables)
            
            if not (has_reset_potions or has_amulets or has_level_candy or has_high_candy or has_premium):
                return await ctx.send(_("Your inventory is empty."))

            # Handle reset potions pagination
            if has_reset_potions:
                reset_potions = [item['resetpotion'] for item in ret]
                chunks_size = 5
                reset_potions_chunks = [
                    reset_potions[i:i + chunks_size]
                    for i in range(0, len(reset_potions), chunks_size)
                ]
                max_page = len(reset_potions_chunks) - 1
            else:
                # If no reset potions, create a single empty chunk
                reset_potions_chunks = [[]]
                max_page = 0

            embeds = [
                self.invembedd(ctx, chunk, amulets, ret, premium_consumables, idx, max_page)
                for idx, chunk in enumerate(reset_potions_chunks)
            ]

            await self.bot.paginator.Paginator(extras=embeds).paginate(ctx)

        except Exception as e:
            import traceback
            error_message = f"Error occurred: {e}\n"
            error_message += traceback.format_exc()
            await ctx.send(error_message)
            print(error_message)

    def lootembed(self, ctx, ret, currentpage, maxpage):
        result = discord.Embed(
            title=_("{user} has the following loot items.").format(user=ctx.disp),
            colour=discord.Colour.blurple(),
        )
        for item in ret:
            element = item.get("element", "Unknown")  # Accessing the "element" from the item data

            result.add_field(
                name=f"<:resetpotion: 1245034461960081409> - Reset Potion",  # Including element in the name of the item
                value=_("Amount: `{id}` Value is **{value}**").format(
                    id=ret[0]['resetpotion'], value=0
                ),
                inline=False,
            )

        return result

    @checks.has_char()
    @commands.command(aliases=["sp"], brief=_("Show your gear items"))
    @locale_doc
    async def statpoints(self, ctx):
        # Fetch stat points and stats for the user
        query = 'SELECT "statpoints", "statatk", "statdef", "stathp" FROM profile WHERE "user" = $1;'
        result = await self.bot.pool.fetch(query, ctx.author.id)
        if not result:
            await ctx.send("No character data found.")
            return

        player_data = result[0]
        points = player_data["statpoints"]
        atk = player_data["statatk"]
        def_ = player_data["statdef"]
        hp = player_data["stathp"]

        # Creating a clean and structured embed
        embed = Embed(title="Stat Points", description="Overview of your stat points and how to redeem them.",
                      color=0x3498db)
        embed.add_field(name="Your Stat Points", value=f"You currently have **{points}** unused stat points.",
                        inline=False)
        embed.add_field(name="How to Redeem", value="Redeem your stat points using the commands below:", inline=False)
        embed.add_field(name="Commands",
                        value="`$spr <type> <amount>` or `$statpointredeem <type> <amount>`\n- Types: `health/hp`, `defense/def`, `attack/atk`\n- Example: `$spr atk 5`",
                        inline=False)
        embed.add_field(name="Bonuses",
                        value="Raider bonuses:\n- **Attack**: `+0.1`\n- **Defense**: `+0.1`\n- **Health**: `+50`",
                        inline=False)
        embed.add_field(name="Stat Allocation",
                        value=f"**Attack**: {atk}\n**Defense**: {def_}\n**Health**: {hp}",
                        inline=False)
        embed.set_footer(text="Ensure you have sufficient stat points before redeeming.")

        # Send the embed
        await ctx.send(embed=embed)

    @checks.has_char()
    @user_cooldown(120)
    @commands.command(aliases=["spr"], brief=_("Show your gear items"))
    @locale_doc
    async def statpointsredeem(self, ctx, type: str, amount: int):
        # Validate type
        type = type.lower()  # Handle case insensitivity
        valid_types = {
            "def": "statdef",
            "defense": "statdef",
            "attack": "statatk",
            "atk": "statatk",
            "health": "stathp",
            "hp": "stathp",
        }

        if type not in valid_types:
            await ctx.send(
                _("Invalid type specified. Please use 'def', 'defense', 'attack', 'atk', 'health', or 'hp'."))
            return

        # Fetch current stat points
        query = 'SELECT "statpoints" FROM profile WHERE "user" = $1;'
        result = await self.bot.pool.fetch(query, ctx.author.id)
        if not result:
            await ctx.send(_("No character data found."))
            return

        player_data = result[0]
        points = player_data["statpoints"]

        # Check if user has enough points
        if points < amount:
            await ctx.send(_("You do not have enough stat points to redeem."))
            return

        if not await ctx.confirm(
                _("Are you sure you want to redeem {amount} {type} points?").format(amount=amount, type=type)):
            return await ctx.send(_("Redeeming cancelled."))

        # Calculate new stat points and update the profile
        new_stat_points = points - amount
        stat_column = valid_types[type]
        update_query = f'UPDATE profile SET "statpoints" = $1, "{stat_column}" = "{stat_column}" + $2 WHERE "user" = $3;'
        await self.bot.pool.execute(update_query, new_stat_points, amount, ctx.author.id)

        # Confirmation message
        await ctx.send(
            _(f"Successfully redeemed {amount} points to {type}. You now have {new_stat_points} stat points remaining."))

    @checks.has_char()
    @commands.command(aliases=["arm", "ar"], brief=_("Show your gear items"))
    @locale_doc
    async def armory(
            self,
            ctx,
            itemtype: str | None = "All",
            lowest: IntFromTo(0, 201) = 0,
            highest: IntFromTo(0, 201) = 201,
    ):
        _(
            """`[itemtype]` - The type of item to show; defaults to all items
            `[lowest]` - The lower boundary of items to show; defaults to 0
            `[highest]` - The upper boundary of items to show; defaults to 101

            Show your gear items. Items that are in the market will not be shown.

            Gear items can be equipped, sold and given away, or upgraded and merged to make them stronger.
            You can gain gear items by completing adventures, opening crates, or having your pet hunt for them, if you are a ranger.

            To sell unused items for their value, use `{prefix}merch`. To put them up on the global player market, use `{prefix}sell`."""
        )


        if highest < lowest:
            return await ctx.send(
                _("Make sure that the `highest` value is greater than `lowest`.")
            )

        if itemtype != "2h":
            if itemtype != "1h":
                itemtype = itemtype.title()
                itemtype_cls = ItemType.from_string(itemtype)
                if itemtype != "All" and itemtype_cls is None:
                    return await ctx.send(
                        _(
                            "Please select a valid item type or `all`, `1h`, `2h`. Available types:"
                            " `{all_types}`"
                        ).format(all_types=", ".join([t.name for t in ALL_ITEM_TYPES]))
                    )
        if itemtype == "All":
            ret = await self.bot.pool.fetch(
                "SELECT ai.*, i.equipped, i.locked FROM profile p JOIN allitems ai ON"
                " (p.user=ai.owner) JOIN inventory i ON (ai.id=i.item) WHERE"
                ' p."user"=$1 AND ((ai."damage"+ai."armor" BETWEEN $2 AND $3) OR'
                ' i."equipped") ORDER BY i."equipped" DESC, i.locked DESC, ai."damage"+ai."armor"'
                " DESC;",
                ctx.author.id,
                lowest,
                highest,
            )
        elif itemtype == "2h":
            twohand = "both"
            ret = await self.bot.pool.fetch(
                "SELECT ai.*, i.equipped, i.locked FROM profile p JOIN allitems ai ON"
                " (p.user=ai.owner) JOIN inventory i ON (ai.id=i.item) WHERE"
                ' p."user"=$1 AND ((ai."damage"+ai."armor" BETWEEN $2 AND $3 AND'
                ' ai."hand"=$4)  OR i."equipped") ORDER BY i."equipped" DESC, i.locked DESC,'
                ' ai."damage"+ai."armor" DESC;',
                ctx.author.id,
                lowest,
                highest,
                twohand,
            )
        elif itemtype == "1h":
            twohand = "both"
            ret = await self.bot.pool.fetch(
                "SELECT ai.*, i.equipped, i.locked FROM profile p JOIN allitems ai ON"
                " (p.user=ai.owner) JOIN inventory i ON (ai.id=i.item) WHERE"
                ' p."user"=$1 AND ((ai."damage"+ai."armor" BETWEEN $2 AND $3 AND'
                ' ai."hand"!=$4)  OR i."equipped") ORDER BY i."equipped" DESC, i.locked DESC,'
                ' ai."damage"+ai."armor" DESC;',
                ctx.author.id,
                lowest,
                highest,
                twohand,
            )
        else:
            ret = await self.bot.pool.fetch(
                "SELECT ai.*, i.equipped, i.locked FROM profile p JOIN allitems ai ON"
                " (p.user=ai.owner) JOIN inventory i ON (ai.id=i.item) WHERE"
                ' p."user"=$1 AND ((ai."damage"+ai."armor" BETWEEN $2 AND $3 AND'
                ' ai."type"=$4)  OR i."equipped") ORDER BY i."equipped" DESC, i.locked DESC,'
                ' ai."damage"+ai."armor" DESC;',
                ctx.author.id,
                lowest,
                highest,
                itemtype,
            )
        if not ret:
            return await ctx.send(_("Your inventory is empty."))
        allitems = list(chunks(ret, 5))
        maxpage = len(allitems) - 1
        embeds = [
            self.invembed(ctx, chunk, idx, maxpage)
            for idx, chunk in enumerate(allitems)
        ]
        await self.bot.paginator.Paginator(extras=embeds).paginate(ctx)

    def lootembed(self, ctx, ret, currentpage, maxpage):
        result = discord.Embed(
            title=_("{user} has the following loot items.").format(user=ctx.disp),
            colour=discord.Colour.blurple(),
        )
        for item in ret:
            element = item.get("element", "Unknown")  # Accessing the "element" from the item data

            result.add_field(
                name=f"{item['name']}",  # Including element in the name of the item
                value=_("ID: `{id}` Value is **{value}**").format(
                    id=item["id"], value=item["value"]
                ),
                inline=False,
            )

        return result

    @checks.has_char()
    @commands.command(aliases=["loot"], brief=_("Show your loot items"))
    @locale_doc
    async def items(self, ctx):
        _(
            """Show your loot items.

            Loot items can be exchanged for money or XP, or sacrificed to your God to gain favor points.

            You can gain loot items by completing adventures. The higher the difficulty, the higher the chance to get loot.
            If you are a Ritualist, your loot chances are doubled. Check [our wiki](https://wiki.idlerpg.xyz/index.php?title=Loot#Probability) for the exact chances."""
        )
        ret = await self.bot.pool.fetch(
            'SELECT * FROM loot WHERE "user"=$1 ORDER BY "value" DESC, "id" DESC;',
            ctx.author.id,
        )
        if not ret:
            return await ctx.send(_("You do not have any loot at this moment."))
        allitems = list(chunks(ret, 7))
        maxpage = len(allitems) - 1
        embeds = [
            self.lootembed(ctx, chunk, idx, maxpage)
            for idx, chunk in enumerate(allitems)
        ]
        await self.bot.paginator.Paginator(extras=embeds).paginate(ctx)

    @checks.has_char()
    @user_cooldown(180, identifier="sacrificeexchange")
    @commands.command(aliases=["ex"], brief=_("Exchange your loot for money or XP"))
    @locale_doc
    async def exchange(self, ctx, *loot_ids: int):
        _(
            """`[loot_ids...]` - The loot IDs to exchange; defaults to all loot

            Exchange your loot for money or XP, the bot will let you choose.

            If you choose money, you will get the loots' combined value in cash. For XP, you will get 1/4th of the combined value in XP."""
        )
        if none_given := (len(loot_ids) == 0):
            value, count = await self.bot.pool.fetchval(
                'SELECT (SUM("value"), COUNT(*)) FROM loot WHERE "user"=$1',
                ctx.author.id,
            )
            if count == 0:
                await self.bot.reset_cooldown(ctx)
                return await ctx.send(_("You don't have any loot."))
        else:
            value, count = await self.bot.pool.fetchval(
                'SELECT (SUM("value"), COUNT("value")) FROM loot WHERE "id"=ANY($1)'
                ' AND "user"=$2;',
                loot_ids,
                ctx.author.id,
            )
            if not count:
                await self.bot.reset_cooldown(ctx)
                return await ctx.send(
                    _("You don't own any loot items with the IDs: {itemids}").format(
                        itemids=", ".join([str(loot_id) for loot_id in loot_ids])
                    )
                )

        value = int(value)
        reward = await self.bot.paginator.Choose(
            title=_(f"Select a reward for the {count} items"),
            placeholder=_("Select a reward"),
            footer=_("Do you want favor? {prefix}sacrifice instead").format(
                prefix=ctx.clean_prefix
            ),
            return_index=True,
            entries=[f"**${value}**", _("**{value} XP**").format(value=value // 4)],
            choices=[f"${value}", _("{value} XP").format(value=value // 4)],
        ).paginate(ctx)
        reward = ["money", "xp"][reward]
        if reward == "xp":
            old_level = rpgtools.xptolevel(ctx.character_data["xp"])
            value = value // 4

        async with self.bot.pool.acquire() as conn:
            if none_given:
                await conn.execute('DELETE FROM loot WHERE "user"=$1;', ctx.author.id)
            else:
                await conn.execute(
                    'DELETE FROM loot WHERE "id"=ANY($1) AND "user"=$2;',
                    loot_ids,
                    ctx.author.id,
                )
            await conn.execute(
                f'UPDATE profile SET "{reward}"="{reward}"+$1 WHERE "user"=$2;',
                value,
                ctx.author.id,
            )
            await self.bot.log_transaction(
                ctx,
                from_=1,
                to=ctx.author.id,
                subject="exchange",
                data={"Reward": reward, "Amount": value},
                conn=conn,
            )
        if none_given:
            text = _(
                "You received **{reward}** when exchanging all of your loot."
            ).format(reward=f"${value}" if reward == "money" else f"{value} XP")
        else:
            text = _(
                "You received **{reward}** when exchanging loot item(s) `{loot_ids}`. "
            ).format(
                reward=f"${value}" if reward == "money" else f"{value} XP",
                loot_ids=", ".join([str(lootid) for lootid in loot_ids]),
            )
        additional = _("Skipped `{amount}` because they did not belong to you.").format(
            amount=len(loot_ids) - count
        )
        # if len(loot_ids) > count else ""

        await ctx.send(text + (additional if len(loot_ids) > count else ""))

        if reward == "xp":
            new_level = int(rpgtools.xptolevel(ctx.character_data["xp"] + value))
            if old_level != new_level:
                await self.bot.process_levelup(ctx, new_level, old_level)

        await self.bot.reset_cooldown(ctx)

    @commands.group(name="preset", invoke_without_command=True)
    async def preset_cmd(self, ctx):
        """
        Base command group for preset operations.
        Usage:
          $preset create <preset_name>
          $preset use <preset_name>
          $preset list
          $preset delete <preset_name>
        """
        await ctx.send("Use `$preset create|use|list|delete` ...")

    @preset_cmd.command(name="create")
    async def preset_create(self, ctx, preset_id: str):
        """
        Creates or overwrites a preset using your currently equipped items.
        Enforces a maximum of 5 total presets per user.
        Usage:
            $preset create raid_loadout
        """
        async with self.bot.pool.acquire() as conn:
            # 1) Grab currently equipped items
            rows = await conn.fetch(
                """
                SELECT i.item
                  FROM profile p
                  JOIN allitems ai ON (p.user = ai.owner)
                  JOIN inventory i ON (ai.id = i.item)
                 WHERE i.equipped = TRUE
                   AND p.user = $1
                """,
                ctx.author.id
            )
            if not rows:
                return await ctx.send("You have no currently equipped items to save.")

            item_ids = [r["item"] for r in rows]

            # 2) Check how many presets the user currently has
            preset_count = await conn.fetchval(
                """
                SELECT COUNT(*) 
                  FROM presets
                 WHERE user_id = $1
                """,
                ctx.author.id
            )

            # 3) See if this preset already exists (overwrite scenario)
            existing_preset = await conn.fetchrow(
                """
                SELECT preset_id
                  FROM presets
                 WHERE user_id = $1
                   AND preset_id = $2
                """,
                ctx.author.id,
                preset_id
            )

            # If user is at max (5) and we are not overwriting an existing preset, block
            if preset_count >= 5 and not existing_preset:
                return await ctx.send(
                    "You already have 5 presets. Please delete one first or use the same name to overwrite."
                )

            # 4) Insert or update the preset in the DB
            await conn.execute(
                """
                INSERT INTO presets (user_id, preset_id, item_ids)
                VALUES ($1, $2, $3)
                ON CONFLICT (user_id, preset_id)
                DO UPDATE SET item_ids = EXCLUDED.item_ids;
                """,
                ctx.author.id,
                preset_id,
                item_ids
            )

        await ctx.send(
            f"Preset **{preset_id}** saved with these equipped item IDs: {', '.join(map(str, item_ids))}"
        )

    @preset_cmd.command(name="use")
    async def preset_use(self, ctx, preset_id: str):
        """
        Equips all items saved in the specified preset.
        Automatically unequips currently equipped items.
        Usage: $preset use sword_shield
        """
        # 1) Fetch preset
        async with self.bot.pool.acquire() as conn:
            # Get the preset
            record = await conn.fetchrow(
                """
                SELECT item_ids
                  FROM presets
                 WHERE user_id = $1
                   AND preset_id = $2
                """,
                ctx.author.id,
                preset_id
            )
            if not record:
                return await ctx.send(f"You have no preset **{preset_id}** defined.")

            # 2) Get currently equipped items to unequip them later
            equipped = await conn.fetch(
                """
                SELECT ai.id, ai.type
                  FROM allitems ai
                  JOIN inventory i ON (ai.id = i.item)
                 WHERE i.equipped IS TRUE
                   AND ai.owner = $1;
                """,
                ctx.author.id
            )

            item_ids = record["item_ids"]
            if not item_ids:
                return await ctx.send(f"Preset **{preset_id}** has no items stored.")

            # 3) Check ownership of new items
            owned_rows = await conn.fetch(
                """
                SELECT i.item, ai.type
                  FROM inventory i
                  JOIN allitems ai ON (i.item = ai.id)
                 WHERE ai.owner = $1
                   AND i.item = ANY($2::bigint[]);
                """,
                ctx.author.id,
                item_ids
            )
            owned_items = {r["item"]: r["type"] for r in owned_rows}
            missing = set(item_ids) - set(owned_items.keys())
            if missing:
                return await ctx.send(
                    f"You no longer own these item(s): {', '.join(map(str, missing))}"
                )

            # 4) Begin transaction
            async with conn.transaction():
                # 5) Unequip currently equipped items
                for item in equipped:
                    await conn.execute(
                        """
                        UPDATE inventory
                           SET equipped = FALSE
                         WHERE item = $1;
                        """,
                        item["id"]
                    )

                # 6) Equip new items
                for item_id in item_ids:
                    item_type = owned_items[item_id]
                    # First ensure no other item of same type is equipped
                    await conn.execute(
                        """
                        UPDATE inventory
                           SET equipped = FALSE
                         WHERE item IN (
                             SELECT i.item
                               FROM inventory i
                               JOIN allitems ai ON (i.item = ai.id)
                              WHERE ai.owner = $1
                                AND ai.type = $2
                                AND i.equipped = TRUE
                         );
                        """,
                        ctx.author.id,
                        item_type
                    )
                    # Then equip the new item
                    await conn.execute(
                        """
                        UPDATE inventory
                           SET equipped = TRUE
                         WHERE item = $1;
                        """,
                        item_id
                    )

        # 7) Send success message with item details
        item_details = []
        for item_id in item_ids:
            item = await self.bot.pool.fetchrow(
                "SELECT name, type FROM allitems WHERE id = $1", item_id
            )
            if item:
                item_details.append(f"- {item['name']} ({item['type']})")

        await ctx.send(
            f"✅ **Equipped preset {preset_id}:**\n" + "\n".join(item_details)[:1900]
        )

    @preset_cmd.command(name="list")
    async def preset_list(self, ctx):
        """
        Lists all of your saved presets.
        Usage: $preset list
        """
        async with self.bot.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT preset_id, item_ids
                  FROM presets
                 WHERE user_id = $1
                 ORDER BY preset_id
                """,
                ctx.author.id
            )

        if not rows:
            return await ctx.send("You have no presets saved.")

        lines = []
        for r in rows:
            pid = r["preset_id"]
            items = r["item_ids"]
            items_str = ", ".join(map(str, items)) if items else "(none)"
            lines.append(f"**Preset {pid}:** {items_str}")

        await ctx.send("\n".join(lines))

    @preset_cmd.command(name="delete", aliases=["remove"])
    async def preset_delete(self, ctx, preset_id: str):
        """
        Deletes a preset from your list.
        Usage: $preset delete sword_shield
        """
        async with self.bot.pool.acquire() as conn:
            result = await conn.execute(
                """
                DELETE FROM presets
                      WHERE user_id = $1
                        AND preset_id = $2
                """,
                ctx.author.id,
                preset_id
            )

        if "DELETE 0" in result:
            return await ctx.send(f"No preset **{preset_id}** existed.")
        else:
            await ctx.send(f"Preset **{preset_id}** has been deleted.")


    @user_cooldown(180)
    @checks.has_char()
    @commands.command(aliases=["use"], brief=_("Equip an item"))
    @locale_doc
    async def equip(self, ctx, itemid: int):
        _(
            """`<itemid>` - The ID of the item to equip

            Equip an item by its ID, you can find the item IDs in your inventory.

            Each item has an assigned hand slot,
              "any" meaning that the item can go in either hand,
              "both" meaning it takes both hands,
              "left" and "right" should be clear.

            You cannot equip two items that use the same hand, or a second item if the one your have equipped is two-handed."""
        )
        async with self.bot.pool.acquire() as conn:
            item = await conn.fetchrow(
                'SELECT ai.* FROM inventory i JOIN allitems ai ON (i."item"=ai."id")'
                ' WHERE ai."owner"=$1 and ai."id"=$2;',
                ctx.author.id,
                itemid,
            )
            if not item:
                await self.bot.reset_cooldown(ctx)
                return await ctx.send(
                    _("You don't own an item with the ID `{itemid}`.").format(
                        itemid=itemid
                    )
                )

            olditems = await conn.fetch(
                "SELECT ai.* FROM profile p JOIN allitems ai ON (p.user=ai.owner) JOIN"
                " inventory i ON (ai.id=i.item) WHERE i.equipped IS TRUE AND"
                " p.user=$1;",
                ctx.author.id,
            )
            put_off = []
            if olditems:
                num_any = sum(1 for i in olditems if i["hand"] == "any")
                if len(olditems) == 1 and olditems[0]["hand"] == "both":
                    await conn.execute(
                        'UPDATE inventory SET "equipped"=False WHERE "item"=$1;',
                        olditems[0]["id"],
                    )
                    put_off = [olditems[0]["id"]]
                elif item["hand"] == "both":
                    all_ids = [i["id"] for i in olditems]
                    await conn.execute(
                        'UPDATE inventory SET "equipped"=False WHERE "item"=ANY($1);',
                        all_ids,
                    )
                    put_off = all_ids
                else:
                    if len(olditems) < 2:
                        if (
                                item["hand"] != "any"
                                and olditems[0]["hand"] == item["hand"]
                        ):
                            await conn.execute(
                                'UPDATE inventory SET "equipped"=False WHERE'
                                ' "item"=$1;',
                                olditems[0]["id"],
                            )
                            put_off = [olditems[0]["id"]]
                    elif (
                            item["hand"] == "left" or item["hand"] == "right"
                    ) and num_any < 2:
                        item_to_remove = [
                            i for i in olditems if i["hand"] == item["hand"]
                        ]
                        if not item_to_remove:
                            item_to_remove = [i for i in olditems if i["hand"] == "any"]
                        item_to_remove = item_to_remove[0]["id"]
                        await conn.execute(
                            'UPDATE inventory SET "equipped"=False WHERE "item"=$1;',
                            item_to_remove,
                        )
                        put_off = [item_to_remove]
                    else:
                        item_to_remove = await self.bot.paginator.Choose(
                            title=_("Select an item to unequip"),
                            return_index=True,
                            entries=[
                                f"{i['name']}, {i['type']}, {i['damage'] + i['armor']}"
                                for i in olditems
                            ],
                            choices=[i["name"] for i in olditems],
                        ).paginate(ctx)
                        item_to_remove = olditems[item_to_remove]["id"]
                        await conn.execute(
                            'UPDATE inventory SET "equipped"=False WHERE "item"=$1;',
                            item_to_remove,
                        )
                        put_off = [item_to_remove]
            await conn.execute(
                'UPDATE inventory SET "equipped"=True WHERE "item"=$1;', itemid
            )
        await self.bot.reset_cooldown(ctx)
        if put_off:
            await ctx.send(
                _(
                    "Successfully equipped item `{itemid}` and put off item(s)"
                    " {olditems}."
                ).format(
                    olditems=", ".join(f"`{i}`" for i in put_off), itemid=item["id"]
                )
            )
        else:
            await ctx.send(
                _("Successfully equipped item `{itemid}`.").format(itemid=itemid)
            )

    @checks.has_char()
    @commands.command(brief=_("Unequip an item"))
    @locale_doc
    async def unequip(self, ctx, itemid: int):
        _(
            """`<itemid>` - The ID of the item to unequip

            Unequip one of your equipped items. This has no benefit whatsoever."""
        )
        async with self.bot.pool.acquire() as conn:
            item = await conn.fetchrow(
                'SELECT * FROM inventory i JOIN allitems ai ON (i."item"=ai."id") WHERE'
                ' ai."owner"=$1 and ai."id"=$2;',
                ctx.author.id,
                itemid,
            )
            if not item:
                return await ctx.send(
                    _("You don't own an item with the ID `{itemid}`.").format(
                        itemid=itemid
                    )
                )
            if not item["equipped"]:
                return await ctx.send(_("You don't have this item equipped."))
            await conn.execute(
                'UPDATE inventory SET "equipped"=False WHERE "item"=$1;', itemid
            )
        await ctx.send(
            _("Successfully unequipped item `{itemid}`.").format(itemid=itemid)
        )

    @checks.has_char()
    @user_cooldown(3600)
    @commands.command(brief=_("Merge two items to make a stronger one"))
    @locale_doc
    async def merge(self, ctx, firstitemid: int, seconditemid: int):
        _(
            """`<firstitemid>` - The ID of the first item
            `<seconditemid>` - The ID of the second item

            Merges two items to a better one.

            ⚠ The first item will be upgraded by +1, the second item will be destroyed.

            The two items must be of the same item type and within a 5 stat range of each other.
            For example, if the first item is a 23 damage Scythe, the second item must be a Scythe with damage 18 to 28.

            One handed weapons can be merged up to 41, two handed items up to 82

            (This command has a cooldown of 1 hour.)"""
        )
        if firstitemid == seconditemid:
            await self.bot.reset_cooldown(ctx)
            return await ctx.send(_("Good luck with that."))
        async with self.bot.pool.acquire() as conn:
            item = await conn.fetchrow(
                'SELECT * FROM allitems WHERE "id"=$1 AND "owner"=$2;',
                firstitemid,
                ctx.author.id,
            )
            item2 = await conn.fetchrow(
                'SELECT * FROM allitems WHERE "id"=$1 AND "owner"=$2;',
                seconditemid,
                ctx.author.id,
            )
            if not item or not item2:
                await self.bot.reset_cooldown(ctx)
                return await ctx.send(_("You don't own both of these items."))
            if item["type"] != item2["type"]:
                await self.bot.reset_cooldown(ctx)
                return await ctx.send(
                    _(
                        "The items are of unequal type. You may only merge a sword with"
                        " a sword or a shield with a shield."
                    )
                )
            stat = "damage" if item["type"] != "Shield" else "armor"
            min_ = item[stat] - 5
            main = item[stat]
            main2 = item2[stat]
            max_ = item[stat] + 5
            main_hand = item["hand"]
            if (main > 60 and main_hand != "both") or (
                    main > 122 and main_hand == "both"
            ):
                await self.bot.reset_cooldown(ctx)
                return await ctx.send(
                    _("This item is already on the maximum upgrade level.")
                )
            if not min_ <= main2 <= max_:
                await self.bot.reset_cooldown(ctx)
                return await ctx.send(
                    _(
                        "The second item's stat must be in the range of `{min_}` to"
                        " `{max_}` to upgrade an item with the stat of `{stat}`."
                    ).format(min_=min_, max_=max_, stat=main)
                )
            await conn.execute(
                f'UPDATE allitems SET "{stat}"="{stat}"+1 WHERE "id"=$1;', firstitemid
            )
            await conn.execute('DELETE FROM inventory WHERE "item"=$1;', seconditemid)
            await conn.execute('DELETE FROM allitems WHERE "id"=$1;', seconditemid)
        await ctx.send(
            _(
                "The {stat} of your **{item}** is now **{newstat}**. The other item was"
                " destroyed."
            ).format(stat=stat, item=item["name"], newstat=main + 1)
        )

    @checks.has_char()
    @user_cooldown(3600)
    @commands.command(aliases=["upgrade"], brief=_("Upgrade an item"))
    @locale_doc
    async def upgradeweapon(self, ctx, itemid: int):
        _(
            """`<itemid>` - The ID of the item to upgrade

            Upgrades an item's stat by 1.
            The price to upgrade an item is 250 times its current stat. For example, upgrading a 15 damage sword will cost $3,750.

            One handed weapons can be upgraded up to 41, two handed items up to 82.

            (This command has a cooldown of 1 hour.)"""
        )
        async with self.bot.pool.acquire() as conn:
            item = await conn.fetchrow(
                'SELECT * FROM allitems WHERE "id"=$1 AND "owner"=$2;',
                itemid,
                ctx.author.id,
            )
            if not item:
                await self.bot.reset_cooldown(ctx)
                return await ctx.send(
                    _("You don't own an item with the ID `{itemid}`.").format(
                        itemid=itemid
                    )
                )
            if item["type"] != "Shield":
                stattoupgrade = "damage"
                pricetopay = int(item["damage"] * 1500)
            elif item["type"] == "Shield":
                stattoupgrade = "armor"
                pricetopay = int(item["armor"] * 1500)
            stat = int(item[stattoupgrade])
            hand = item["hand"]
            if (stat > 60 and hand != "both") or (stat > 122 and hand == "both"):
                await self.bot.reset_cooldown(ctx)
                return await ctx.send(
                    _("Your weapon already reached the maximum upgrade level.")
                )

        if not await ctx.confirm(
                _(
                    "Are you sure you want to upgrade this item: {item}? It will cost"
                    " **${pricetopay}**."
                ).format(item=item["name"], pricetopay=pricetopay)
        ):
            return await ctx.send(_("Weapon upgrade cancelled."))
        if not await checks.has_money(self.bot, ctx.author.id, pricetopay):
            await self.bot.reset_cooldown(ctx)
            return await ctx.send(
                _(
                    "You are too poor to upgrade this item. The upgrade costs"
                    " **${pricetopay}**, but you only have **${money}**."
                ).format(pricetopay=pricetopay, money=ctx.character_data["money"])
            )
        async with self.bot.pool.acquire() as conn:
            await conn.execute(
                f'UPDATE allitems SET {stattoupgrade}={stattoupgrade}+1 WHERE "id"=$1;',
                itemid,
            )
            await conn.execute(
                'UPDATE profile SET "money"="money"-$1 WHERE "user"=$2;',
                pricetopay,
                ctx.author.id,
            )
            await self.bot.log_transaction(
                ctx,
                from_=ctx.author.id,
                to=2,
                subject="Upgrade",
                data={"Gold": pricetopay},
                conn=conn,
            )
        await ctx.send(
            _(
                "The {stat} of your **{item}** is now **{newstat}**. **${pricetopay}**"
                " has been taken off your balance."
            ).format(
                stat=stattoupgrade,
                item=item["name"],
                newstat=int(item[stattoupgrade]) + 1,
                pricetopay=pricetopay,
            )
        )

    @checks.has_char()
    @commands.command(brief=_("Give someone money"))
    @locale_doc
    async def give(
            self, ctx, money, other: MemberWithCharacter
    ):
        _(
            """`<money>` - The amount of money to give to the other person, cannot exceed 100,000,000
            `[other]` - The person to give the money to

            Gift money! It will be removed from you and added to the other person."""
        )

        if money == "all":
            money = int(ctx.character_data["money"])

        else:
            try:
                money = int(money)
            except Exception as e:
                return await ctx.send("You used a malformed argument!")
        if money < 1:
            return await ctx.send("The supplied number must be greater than 0.")

        if ctx.author.id == 823030177025753100 and other.id == 295173706496475136:
            return await ctx.send(_("Nice try bish!"))
        if other == ctx.author:
            return await ctx.send(_("No cheating!"))
        elif other == ctx.me:
            return await ctx.send(
                _("For me? I'm flattered, but I can't accept this...")
            )
        if ctx.character_data["money"] < money:
            return await ctx.send(_("You are too poor."))
        async with self.bot.pool.acquire() as conn:
            authormoney = await conn.fetchval(
                'UPDATE profile SET "money"="money"-$1 WHERE "user"=$2 RETURNING'
                ' "money";',
                money,
                ctx.author.id,
            )
            othermoney = await conn.fetchval(
                'UPDATE profile SET "money"="money"+$1 WHERE "user"=$2 RETURNING'
                ' "money";',
                money,
                other.id,
            )
            await self.bot.log_transaction(
                ctx,
                from_=ctx.author,
                to=other,
                subject="give money",
                data={"Gold": money},
                conn=conn,
            )
        await ctx.send(
            _(
                "Success!\n{other} now has **${othermoney}**, you now have"
                " **${authormoney}**."
            ).format(
                other=other.mention, othermoney=othermoney, authormoney=authormoney
            )
        )

    @checks.has_char()
    @commands.command(brief=_("Rename your character"))
    @locale_doc
    async def rename(self, ctx, *, name: str = None):
        _(
            """`[name]` - The name to use; if not given, this will be interactive

            Renames your character. The name must be from 3 to 20 characters long."""
        )
        if not name:
            await ctx.send(
                _(
                    "What shall your character's name be? (Minimum 3 Characters,"
                    " Maximum 20)"
                )
            )

            def mycheck(amsg):
                return amsg.author == ctx.author

            try:
                name = await self.bot.wait_for("message", timeout=60, check=mycheck)
            except asyncio.TimeoutError:
                return await ctx.send(_("Timeout expired. Retry!"))
            name = name.content
        if len(name) > 2 and len(name) < 21:
            if "`" in name:
                return await ctx.send(
                    _(
                        "Illegal character (`) found in the name. Please try again and"
                        " choose another name."
                    )
                )
            await self.bot.pool.execute(
                'UPDATE profile SET "name"=$1 WHERE "user"=$2;', name, ctx.author.id
            )
            await ctx.send(_("Character name updated."))
        elif len(name) < 3:
            await ctx.send(_("Character names must be at least 3 characters!"))
        elif len(name) > 20:
            await ctx.send(_("Character names mustn't exceed 20 characters!"))

    @checks.has_char()
    @commands.command(aliases=["rm", "del"], brief=_("Delete your character"))
    @locale_doc
    async def delete(self, ctx):
        _(
            """Deletes your character. There is no way to get your character data back after deletion.

            Deleting your character also removes:
              - Your guild if you own one
              - Your alliance's city ownership
              - Your marriage and children"""
        )
        try:
            if not await ctx.confirm(
                    _(
                        "Are you absolutely sure you want to delete your character? React in"
                        " the next 30 seconds to confirm.\n**This cannot be undone.**"
                    )
            ):
                return await ctx.send(_("Cancelled deletion of your character."))
            async with self.bot.pool.acquire() as conn:
                g = await conn.fetchval(
                    'DELETE FROM guild WHERE "leader"=$1 RETURNING "id";', ctx.author.id
                )
                if g:
                    await conn.execute(
                        'UPDATE profile SET "guildrank"=$1, "guild"=$2 WHERE "guild"=$3;',
                        "Member",
                        0,
                        g,
                    )
                    await conn.execute('UPDATE city SET "owner"=1 WHERE "owner"=$1;', g)
                if partner := ctx.character_data["marriage"]:
                    await conn.execute(
                        'UPDATE profile SET "marriage"=$1 WHERE "user"=$2;',
                        0,
                        partner,
                    )
                await conn.execute(
                    'UPDATE children SET "mother"=$1, "father"=0 WHERE ("father"=$1 AND'
                    ' "mother"=$2) OR ("father"=$2 AND "mother"=$1);',
                    partner,
                    ctx.author.id,
                )
                await self.bot.delete_profile(ctx.author.id, conn=conn)
            await self.bot.delete_adventure(ctx.author)
            await ctx.send(
                _("Successfully deleted your character. Sorry to see you go :frowning:")
            )
        except Exception as e:
            await ctx.send(e)

    @checks.has_char()
    @commands.command(aliases=["color"], brief=_("Update your profile color"))
    @locale_doc
    async def colour(self, ctx, *, colour: str):
        _(
            """`<color>` - The color to use, see below for allowed format

            Sets your profile text colour. The format may be #RGB, #RRGGBB, CSS3 defaults like "cyan", a rgb(r, g, b) tuple or a rgba(r, g, b, a) tuple

            A tuple is a data type consisting of multiple parts. To make a tuple for this command, seperate your values with a comma, and surround them with parantheses.
            Here is an example of a tuple with four values: `(128,256,0,0.5)`

            This will change the text color in `{prefix}profile` and the embed color in `{prefix}profile2`."""
        )
        try:
            rgba = colors.parse(colour)
        except ValueError:
            return await ctx.send(
                _(
                    "Format for colour is `#RGB`, `#RRGGBB`, a colour code like `cyan`"
                    " or rgb/rgba values like (255, 255, 255, 0.5)."
                )
            )
        await self.bot.pool.execute(
            'UPDATE profile SET "colour"=$1 WHERE "user"=$2;',
            (rgba.red, rgba.green, rgba.blue, rgba.alpha),
            ctx.author.id,
        )
        await ctx.send(
            _("Successfully set your profile colour to `{colour}`.").format(
                colour=colour
            )
        )

    @checks.has_char()
    @commands.command(brief=_("Claim your profile badges"))
    @locale_doc
    async def claimbadges(self, ctx: Context) -> None:
        _(
            """Claim all badges for your profile based on your roles. This command can only be used in the support server."""
        )
        if not ctx.guild or ctx.guild.id != self.bot.config.game.support_server_id:
            await ctx.send(_("This command can only be used in the support server."))
            return

        roles = {
            "Contributor": Badge.CONTRIBUTOR,
            "Designer": Badge.DESIGNER,
            "Developer": Badge.DEVELOPER,
            "Game Designer": Badge.GAME_DESIGNER,
            "Game Masters": Badge.GAME_MASTER,
            "Support Team": Badge.SUPPORT,
            "Betasquad": Badge.TESTER,
            "Veterans": Badge.VETERAN,
        }

        badges = None

        for role in ctx.author.roles:
            if (badge := roles.get(role.name)) is not None:
                if badges is None:
                    badges = badge
                else:
                    badges |= badge

        if badges is not None:
            await self.bot.pool.execute(
                'UPDATE profile SET "badges"=$1 WHERE "user"=$2;',
                badges.to_db(),
                ctx.author.id,
            )

        await ctx.send(_("Successfully updated your badges."))


async def setup(bot):
    await bot.add_cog(Profile(bot))

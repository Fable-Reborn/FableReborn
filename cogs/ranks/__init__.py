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
import discord

from discord.ext import commands

from classes.bot import Bot
from classes.context import Context
from utils import misc as rpgtools
from utils.i18n import _, locale_doc
from utils.markdown import escape_markdown
import datetime


class Ranks(commands.Cog):
    def __init__(self, bot: Bot):
        self.bot = bot

    @commands.command(brief=_("Show the top 10 richest"))
    @locale_doc
    async def richest(self, ctx: Context) -> None:
        _("""The 10 richest players in Fable.""")
        await ctx.typing()
        # Fetch the top 10 richest players
        players = await self.bot.pool.fetch(
            'SELECT "user", "name", "money" FROM profile ORDER BY "money" DESC LIMIT 10;'
        )
        result = ""
        top_10_ids = [player["user"] for player in players]
        user_in_top_10 = ctx.author.id in top_10_ids

        # Build the leaderboard string
        for idx, profile in enumerate(players):
            username = await rpgtools.lookup(self.bot, profile["user"])
            text = _("{name}, a character by {username} with **${money}**").format(
                name=escape_markdown(profile["name"]),
                username=escape_markdown(username),
                money=profile["money"],
            )
            # Highlight user's own entry if they are in top 10
            if user_in_top_10 and profile["user"] == ctx.author.id:
                result += f"{idx + 1}. {text}\n"
            else:
                result += f"{idx + 1}. {text}\n"

        # If the user isn't in the top 10, fetch their rank
        if not user_in_top_10:
            # Fetch user's own money
            user_profile = await self.bot.pool.fetchrow(
                'SELECT "money", "name" FROM profile WHERE "user" = $1;', ctx.author.id
            )
            if user_profile:
                user_money = user_profile["money"]
                user_name = user_profile["name"]
                # Calculate the user's rank
                user_rank = await self.bot.pool.fetchval(
                    'SELECT COUNT(*) FROM profile WHERE "money" > $1;', user_money
                )
                user_rank += 1  # Adjust rank to be 1-based

                username = await rpgtools.lookup(self.bot, ctx.author.id)

                text = _("{name}, a character by {username} with **${money}**").format(
                    name=escape_markdown(user_name),
                    username=escape_markdown(username),
                    money=user_money,
                )
                # Add spacing and indicate user's rank
                result += _("\n**Your Rank:**\n")
                result += f"{user_rank}. {text}\n"
            else:
                # User does not have a profile
                result += _("\nYou are not currently ranked.\n")

        # Send the leaderboard embed
        embed = discord.Embed(
            title=_("The Richest Players"), description=result, colour=0xE7CA01
        )
        await ctx.send(embed=embed)

    @commands.command(aliases=["hdlb"], brief=_("Show the top 10 in horde"))
    @locale_doc
    async def hordelb(self, ctx: Context) -> None:
        _("""The 10 top horde players in Fable.""")
        await ctx.typing()
        # Fetch the top 10 horde players
        players = await self.bot.pool.fetch(
            'SELECT "user", "name", "whored" FROM profile ORDER BY "whored" DESC LIMIT 10;'
        )
        result = ""
        top_10_ids = [player["user"] for player in players]
        user_in_top_10 = ctx.author.id in top_10_ids

        # Build the leaderboard string
        for idx, profile in enumerate(players):
            username = await rpgtools.lookup(self.bot, profile["user"])
            text = _("{name}, a character by {username} with a score of **{whored}**").format(
                name=escape_markdown(profile["name"]),
                username=escape_markdown(username),
                whored=profile["whored"],
            )
            # Highlight user's own entry if they are in top 10
            if user_in_top_10 and profile["user"] == ctx.author.id:
                result += f"{idx + 1}. {text}\n"
            else:
                result += f"{idx + 1}. {text}\n"

        # If the user isn't in the top 10, fetch their rank
        if not user_in_top_10:
            # Fetch user's own horde score
            user_profile = await self.bot.pool.fetchrow(
                'SELECT "whored", "name" FROM profile WHERE "user" = $1;', ctx.author.id
            )
            if user_profile:
                user_whored = user_profile["whored"]
                user_name = user_profile["name"]
                # Calculate the user's rank
                user_rank = await self.bot.pool.fetchval(
                    'SELECT COUNT(*) FROM profile WHERE "whored" > $1;', user_whored
                )
                user_rank += 1  # Adjust rank to be 1-based

                username = await rpgtools.lookup(self.bot, ctx.author.id)

                text = _("{name}, a character by {username} with a score of **{whored}**").format(
                    name=escape_markdown(user_name),
                    username=escape_markdown(username),
                    whored=user_whored,
                )
                # Add spacing and indicate user's rank
                result += _("\n**Your Rank:**\n")
                result += f"{user_rank}. {text}\n"
            else:
                # User does not have a profile
                result += _("\nYou are not currently ranked.\n")

        # Send the leaderboard embed
        embed = discord.Embed(
            title=_("The Top Horde Players"), description=result, colour=0xE7CA01
        )
        await ctx.send(embed=embed)

    @commands.command(aliases=["hdlb2"], brief=_("Show the top 10 in horde custom"))
    @locale_doc
    async def hordelb2(self, ctx: Context) -> None:
        _("""The 10 top horde players (Custom) in Fable.""")
        await ctx.typing()
        # Fetch the top 10 custom horde players
        players = await self.bot.pool.fetch(
            'SELECT "user", "name", "whored2" FROM profile ORDER BY "whored2" DESC LIMIT 10;'
        )
        result = ""
        top_10_ids = [player["user"] for player in players]
        user_in_top_10 = ctx.author.id in top_10_ids

        # Build the leaderboard string
        for idx, profile in enumerate(players):
            username = await rpgtools.lookup(self.bot, profile["user"])
            text = _("{name}, a character by {username} with a score of **{whored}**").format(
                name=escape_markdown(profile["name"]),
                username=escape_markdown(username),
                whored=profile["whored2"],
            )
            # Highlight user's own entry if they are in top 10
            if user_in_top_10 and profile["user"] == ctx.author.id:
                result += f"{idx + 1}. {text}\n"
            else:
                result += f"{idx + 1}. {text}\n"

        # If the user isn't in the top 10, fetch their rank
        if not user_in_top_10:
            # Fetch user's own custom horde score
            user_profile = await self.bot.pool.fetchrow(
                'SELECT "whored2", "name" FROM profile WHERE "user" = $1;', ctx.author.id
            )
            if user_profile:
                user_whored2 = user_profile["whored2"]
                user_name = user_profile["name"]
                # Calculate the user's rank
                user_rank = await self.bot.pool.fetchval(
                    'SELECT COUNT(*) FROM profile WHERE "whored2" > $1;', user_whored2
                )
                user_rank += 1  # Adjust rank to be 1-based

                username = await rpgtools.lookup(self.bot, ctx.author.id)

                text = _("{name}, a character by {username} with a score of **{whored}**").format(
                    name=escape_markdown(user_name),
                    username=escape_markdown(username),
                    whored=user_whored2,
                )
                # Add spacing and indicate user's rank
                result += _("\n**Your Rank:**\n")
                result += f"{user_rank}. {text}\n"
            else:
                # User does not have a profile
                result += _("\nYou are not currently ranked.\n")

        # Send the leaderboard embed
        embed = discord.Embed(
            title=_("The Top Horde Players (Custom)"), description=result, colour=0xE7CA01
        )
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="totalboard", description="Shows the top 10 dragon slayers and your rank")
    async def totalboard(self, ctx: commands.Context):
        async with self.bot.pool.acquire() as conn:
            # Get top 10
            top_10 = await conn.fetch('''
                SELECT user_id, total_defeats, 
                       RANK() OVER (ORDER BY total_defeats DESC) as rank
                FROM dragon_contributions 
                ORDER BY total_defeats DESC 
                LIMIT 10
            ''')
            # Get user's rank if not in top 10
            user_rank = await conn.fetchrow('''
                WITH rankings AS (
                    SELECT user_id, total_defeats,
                           RANK() OVER (ORDER BY total_defeats DESC) as rank
                    FROM dragon_contributions
                )
                SELECT * FROM rankings WHERE user_id = $1
            ''', ctx.author.id)

            embed = discord.Embed(title="🏆 Total Dragon Defeats Leaderboard", color=discord.Color.gold())
            # Format top 10
            leaderboard_text = ""
            for entry in top_10:
                leaderboard_text += f"{entry['rank']}. <@{entry['user_id']}> - {entry['total_defeats']} defeats\n"
            embed.description = leaderboard_text
            # Add user's rank if not in top 10
            if user_rank and not any(entry['user_id'] == ctx.author.id for entry in top_10):
                embed.add_field(
                    name="Your Rank",
                    value=f"#{user_rank['rank']} - {user_rank['total_defeats']} defeats",
                    inline=False
                )
            await ctx.send(embed=embed)


    @commands.hybrid_command(name="weeklyboard", description="Shows the top 10 weekly dragon slayers and your rank")
    async def weeklyboard(self, ctx: commands.Context):
        try:
            async with self.bot.pool.acquire() as conn:
                # Get top 10
                top_10 = await conn.fetch('''
                    SELECT user_id, weekly_defeats,
                        RANK() OVER (ORDER BY weekly_defeats DESC) as rank
                    FROM dragon_contributions 
                    ORDER BY weekly_defeats DESC 
                    LIMIT 10
                ''')
                # Get user's rank if not in top 10
                user_rank = await conn.fetchrow('''
                    WITH rankings AS (
                        SELECT user_id, weekly_defeats,
                            RANK() OVER (ORDER BY weekly_defeats DESC) as rank
                        FROM dragon_contributions
                    )
                    SELECT * FROM rankings WHERE user_id = $1
                ''', ctx.author.id)


                reset_data = await conn.fetchrow('SELECT last_reset FROM dragon_progress WHERE id = 1')
                footer_text = "Reset time unavailable"
                if reset_data:
                    last_reset = reset_data['last_reset']
                    next_reset = last_reset + datetime.timedelta(days=7)
                    now = datetime.datetime.utcnow()
                    remaining = next_reset - now
                    
                    # Handle negative time (reset overdue)
                    if remaining < datetime.timedelta(0):
                        remaining = datetime.timedelta(0)
                    
                    days = remaining.days
                    seconds = remaining.seconds
                    hours = seconds // 3600
                    minutes = (seconds % 3600) // 60
                    footer_text = f"Time until next reset: {days}d {hours}h {minutes}m"


                embed = discord.Embed(title="🐉 Weekly Dragon Defeats Leaderboard", color=discord.Color.green())
                # Format top 10
                leaderboard_text = ""
                for entry in top_10:
                    leaderboard_text += f"{entry['rank']}. <@{entry['user_id']}> - {entry['weekly_defeats']} defeats\n"
                embed.description = leaderboard_text
                # Add user's rank if not in top 10
                if user_rank and not any(entry['user_id'] == ctx.author.id for entry in top_10):
                    embed.add_field(
                        name="Your Rank",
                        value=f"#{user_rank['rank']} - {user_rank['weekly_defeats']} defeats",
                        inline=False
                    )
                embed.set_footer(text=footer_text)
                await ctx.send(embed=embed)
        except Exception as e:
            await ctx.send(e)



    @commands.command(aliases=["btlb"], brief=_("Show the top players in the Battle Tower"))
    @locale_doc
    async def battletowerlb(self, ctx: Context) -> None:
        try:
            _("""Display the leaderboard of players in the Battle Tower.""")
            # Fetch the top 10 players
            players = await self.bot.pool.fetch(
                'SELECT bt."id", bt."prestige", bt."level", p."name" '
                'FROM battletower AS bt '
                'INNER JOIN profile AS p ON bt."id" = p."user" '
                'ORDER BY bt."prestige" DESC, bt."level" DESC LIMIT 10'
            )

            result = ""
            top_10_ids = [player["id"] for player in players]
            user_in_top_10 = ctx.author.id in top_10_ids

            # Build the leaderboard string
            for idx, player in enumerate(players):
                username = await self.bot.fetch_user(player["id"])
                character_name = player["name"]

                text = _("{name}, a character by {username} at Prestige **{prestige}** and Level **{level}**").format(
                    name=escape_markdown(character_name),
                    username=escape_markdown(username.name) if username else "Unknown User",
                    prestige=player["prestige"],
                    level=player["level"]
                )
                # Highlight user's own entry if they are in top 10
                if user_in_top_10 and player["id"] == ctx.author.id:
                    result += f"{idx + 1}. {text}\n"
                else:
                    result += f"{idx + 1}. {text}\n"

            # If the user isn't in the top 10, fetch their rank
            if not user_in_top_10:
                # Fetch user's prestige and level
                user_bt = await self.bot.pool.fetchrow(
                    'SELECT bt."prestige", bt."level" '
                    'FROM battletower AS bt '
                    'WHERE bt."id" = $1', ctx.author.id
                )
                if user_bt:
                    user_prestige = user_bt["prestige"]
                    user_level = user_bt["level"]

                    # Calculate the user's rank
                    user_rank = await self.bot.pool.fetchval(
                        'SELECT COUNT(*) FROM battletower AS bt '
                        'WHERE (bt."prestige" > $1) '
                        'OR (bt."prestige" = $1 AND bt."level" > $2)',
                        user_prestige, user_level
                    )
                    user_rank += 1  # Adjust rank to be 1-based

                    # Fetch user's character name
                    user_profile = await self.bot.pool.fetchrow(
                        'SELECT p."name" '
                        'FROM profile AS p '
                        'WHERE p."user" = $1', ctx.author.id
                    )
                    character_name = user_profile["name"] if user_profile else "Unknown"
                    username = ctx.author.name

                    text = _(
                        "{name}, a character by {username} at Prestige **{prestige}** and Level **{level}**").format(
                        name=escape_markdown(character_name),
                        username=escape_markdown(username),
                        prestige=user_prestige,
                        level=user_level
                    )
                    # Add spacing and indicate user's rank
                    result += _("\n**Your Rank:**\n")
                    result += f"{user_rank}. {text}\n"
                else:
                    # User is not in the Battle Tower
                    result += _("\nYou are not currently ranked in the Battle Tower.\n")

            # Send the leaderboard embed
            embed = discord.Embed(
                title=_("Battle Tower Leaderboard"), description=result, colour=0xE7CA01
            )
            await ctx.send(embed=embed)
        except Exception as e:
            await ctx.send(f"An error occurred: {str(e)}")

    @commands.command(aliases=["best", "high", "top"], brief=_("Show the top 10 by XP"))
    @locale_doc
    async def highscore(self, ctx: Context) -> None:
        _("""Shows you the top 10 players by XP and displays the corresponding level.""")
        await ctx.typing()
        # Fetch the top 10 players by XP
        players = await self.bot.pool.fetch(
            'SELECT "user", "name", "xp" FROM profile ORDER BY "xp" DESC LIMIT 10;'
        )
        result = ""
        top_10_ids = [player["user"] for player in players]
        user_in_top_10 = ctx.author.id in top_10_ids

        # Build the leaderboard string
        for idx, profile in enumerate(players):
            username = await rpgtools.lookup(self.bot, profile["user"])
            text = _(
                "{name}, a character by {username} with Level **{level}** (**{xp}** XP)"
            ).format(
                name=escape_markdown(profile["name"]),
                username=escape_markdown(username),
                level=rpgtools.xptolevel(profile["xp"]),
                xp=profile["xp"],
            )
            # Highlight user's own entry if they are in top 10
            if user_in_top_10 and profile["user"] == ctx.author.id:
                result += f"{idx + 1}. {text}\n"
            else:
                result += f"{idx + 1}. {text}\n"

        # If the user isn't in the top 10, fetch their rank
        if not user_in_top_10:
            # Fetch user's own XP
            user_profile = await self.bot.pool.fetchrow(
                'SELECT "xp", "name" FROM profile WHERE "user" = $1;', ctx.author.id
            )
            if user_profile:
                user_xp = user_profile["xp"]
                user_name = user_profile["name"]
                # Calculate the user's rank
                user_rank = await self.bot.pool.fetchval(
                    'SELECT COUNT(*) FROM profile WHERE "xp" > $1;', user_xp
                )
                user_rank += 1  # Adjust rank to be 1-based

                username = await rpgtools.lookup(self.bot, ctx.author.id)

                text = _(
                    "{name}, a character by {username} with Level **{level}** (**{xp}** XP)"
                ).format(
                    name=escape_markdown(user_name),
                    username=escape_markdown(username),
                    level=rpgtools.xptolevel(user_xp),
                    xp=user_xp,
                )
                # Add spacing and indicate user's rank
                result += _("\n**Your Rank:**\n")
                result += f"{user_rank}. {text}"
            else:
                # User does not have a profile
                result += _("\nYou are not currently ranked.\n")

        # Send the leaderboard embed
        embed = discord.Embed(
            title=_("The Best Players"), description=result, colour=0xE7CA01
        )
        await ctx.send(embed=embed)

    @commands.command(aliases=["pvp", "battles"], brief=_("Show the top 10 PvPers"))
    @locale_doc
    async def pvpstats(self, ctx: Context) -> None:
        _("""Shows you the top 10 players by the amount of wins in PvP matches.""")
        await ctx.typing()
        # Fetch the top 10 PvP players
        players = await self.bot.pool.fetch(
            'SELECT "user", "name", "pvpwins" FROM profile ORDER BY "pvpwins" DESC LIMIT 10;'
        )
        result = ""
        top_10_ids = [player["user"] for player in players]
        user_in_top_10 = ctx.author.id in top_10_ids

        # Build the leaderboard string
        for idx, profile in enumerate(players):
            username = await rpgtools.lookup(self.bot, profile["user"])
            text = _("{name}, a character by {username} with **{wins}** wins").format(
                name=escape_markdown(profile["name"]),
                username=escape_markdown(username),
                wins=profile["pvpwins"],
            )
            # Highlight user's own entry if they are in top 10
            if user_in_top_10 and profile["user"] == ctx.author.id:
                result += f"{idx + 1}. {text}\n"
            else:
                result += f"{idx + 1}. {text}\n"

        # If the user isn't in the top 10, fetch their rank
        if not user_in_top_10:
            # Fetch user's own PvP wins
            user_profile = await self.bot.pool.fetchrow(
                'SELECT "pvpwins", "name" FROM profile WHERE "user" = $1;', ctx.author.id
            )
            if user_profile:
                user_pvpwins = user_profile["pvpwins"]
                user_name = user_profile["name"]
                # Calculate the user's rank
                user_rank = await self.bot.pool.fetchval(
                    'SELECT COUNT(*) FROM profile WHERE "pvpwins" > $1;', user_pvpwins
                )
                user_rank += 1  # Adjust rank to be 1-based

                username = await rpgtools.lookup(self.bot, ctx.author.id)

                text = _("{name}, a character by {username} with **{wins}** wins").format(
                    name=escape_markdown(user_name),
                    username=escape_markdown(username),
                    wins=user_pvpwins,
                )
                # Add spacing and indicate user's rank
                result += _("\n**Your Rank:**\n")
                result += f"{user_rank}. {text}\n"
            else:
                # User does not have a profile
                result += _("\nYou are not currently ranked.\n")

        # Send the leaderboard embed
        embed = discord.Embed(
            title=_("The Best PvPers"), description=result, colour=0xE7CA01
        )
        await ctx.send(embed=embed)

    @commands.command(brief=_("Show the top 10 lovers"))
    @locale_doc
    async def lovers(self, ctx: Context) -> None:
        _("""The top 10 lovers sorted by their spouse's lovescore.""")
        await ctx.typing()
        # Fetch the top 10 lovers
        players = await self.bot.pool.fetch(
            'SELECT "user", "marriage", "lovescore" FROM profile ORDER BY "lovescore" DESC LIMIT 10;'
        )
        result = ""
        top_10_ids = [player["user"] for player in players]
        user_in_top_10 = ctx.author.id in top_10_ids

        # Build the leaderboard string
        for idx, profile in enumerate(players):
            lovee = await rpgtools.lookup(self.bot, profile["user"])
            lover = await rpgtools.lookup(self.bot, profile["marriage"])
            text = _(
                "**{lover}** gifted their love **{lovee}** items worth **${points}**"
            ).format(
                lover=discord.utils.escape_markdown(lover),
                lovee=discord.utils.escape_markdown(lovee),
                points=profile["lovescore"],
            )
            # Highlight user's own entry if they are in top 10
            if user_in_top_10 and profile["user"] == ctx.author.id:
                result += f"{idx + 1}. {text}\n"
            else:
                result += f"{idx + 1}. {text}\n"

        # If the user isn't in the top 10, fetch their rank
        if not user_in_top_10:
            # Fetch user's own lovescore and marriage
            user_profile = await self.bot.pool.fetchrow(
                'SELECT "marriage", "lovescore" FROM profile WHERE "user" = $1;', ctx.author.id
            )

            if user_profile:

                user_marriage = user_profile["marriage"]

                marriage = await self.bot.pool.fetchrow(
                    'SELECT "marriage", "lovescore" FROM profile WHERE "user" = $1;', user_marriage
                )
                user_lovescore = marriage["lovescore"]
                # Calculate the user's rank
                user_rank = await self.bot.pool.fetchval(
                    'SELECT COUNT(*) FROM profile WHERE "lovescore" > $1;', user_lovescore
                )
                user_rank += 1  # Adjust rank to be 1-based

                lover = await rpgtools.lookup(self.bot, ctx.author.id)
                lovee = await rpgtools.lookup(self.bot, user_marriage)
                text = _(
                    "**{lover}** gifted their love **{lovee}** items worth **${points}**"
                ).format(
                    lover=discord.utils.escape_markdown(lover),
                    lovee=discord.utils.escape_markdown(lovee),
                    points=user_lovescore,
                )
                # Add spacing and indicate user's rank
                result += _("\n**Your Rank:**\n")
                result += f"{user_rank}. {text}\n"
            else:
                # User does not have a profile or marriage
                result += _("\nYou are not currently ranked.\n")

        # Send the leaderboard embed
        embed = discord.Embed(
            title=_("The Best Lovers"), description=result, colour=0xE7CA01
        )
        await ctx.send(embed=embed)

    @commands.command(aliases=["cbtlb"], brief=_("Show the top couples in the Couples Battle Tower"))
    @locale_doc
    async def coupleslb(self, ctx: Context) -> None:
        _("""Display the leaderboard of couples in the Couples Battle Tower.""")
        await ctx.typing()
        
        try:
            # Fetch the top 10 couples by prestige and level
            couples = await self.bot.pool.fetch(
                'SELECT cbt."partner1_id", cbt."partner2_id", cbt."prestige", cbt."current_level" '
                'FROM couples_battle_tower AS cbt '
                'INNER JOIN profile AS p1 ON p1."user" = cbt."partner1_id" '
                'INNER JOIN profile AS p2 ON p2."user" = cbt."partner2_id" '
                'WHERE p1."marriage" = cbt."partner2_id" AND p2."marriage" = cbt."partner1_id" '
                'ORDER BY cbt."prestige" DESC, cbt."current_level" DESC LIMIT 10'
            )

            result = ""
            top_10_couples = []
            user_in_top_10 = False

            # Build the leaderboard string
            for idx, couple in enumerate(couples):
                partner1_id = couple["partner1_id"]
                partner2_id = couple["partner2_id"]
                prestige = couple["prestige"]
                level = couple["current_level"]

                # Check if current user is in this couple
                if ctx.author.id in (partner1_id, partner2_id):
                    user_in_top_10 = True
                    top_10_couples.append((partner1_id, partner2_id))

                # Get usernames
                partner1_username = await rpgtools.lookup(self.bot, partner1_id)
                partner2_username = await rpgtools.lookup(self.bot, partner2_id)

                text = _("**{partner1}** & **{partner2}** - Prestige {prestige}, Level {level}").format(
                    partner1=escape_markdown(partner1_username),
                    partner2=escape_markdown(partner2_username),
                    prestige=prestige,
                    level=level
                )
                
                # Highlight user's own entry if they are in top 10
                if ctx.author.id in (partner1_id, partner2_id):
                    result += f"{idx + 1}. {text}\n"
                else:
                    result += f"{idx + 1}. {text}\n"

            # If the user isn't in the top 10, fetch their rank
            if not user_in_top_10:
                # Fetch user's couple progress
                user_couple = await self.bot.pool.fetchrow(
                    'SELECT cbt."partner1_id", cbt."partner2_id", cbt."prestige", cbt."current_level" '
                    'FROM couples_battle_tower AS cbt '
                    'INNER JOIN profile AS p1 ON p1."user" = cbt."partner1_id" '
                    'INNER JOIN profile AS p2 ON p2."user" = cbt."partner2_id" '
                    'WHERE (cbt."partner1_id" = $1 OR cbt."partner2_id" = $1) '
                    'AND p1."marriage" = cbt."partner2_id" AND p2."marriage" = cbt."partner1_id"',
                    ctx.author.id
                )
                
                if user_couple:
                    user_prestige = user_couple["prestige"]
                    user_level = user_couple["current_level"]
                    partner1_id = user_couple["partner1_id"]
                    partner2_id = user_couple["partner2_id"]

                    # Calculate the user's rank
                    user_rank = await self.bot.pool.fetchval(
                        'SELECT COUNT(*) FROM couples_battle_tower AS cbt '
                        'INNER JOIN profile AS p1 ON p1."user" = cbt."partner1_id" '
                        'INNER JOIN profile AS p2 ON p2."user" = cbt."partner2_id" '
                        'WHERE p1."marriage" = cbt."partner2_id" '
                        'AND p2."marriage" = cbt."partner1_id" '
                        'AND ((cbt."prestige" > $1) '
                        'OR (cbt."prestige" = $1 AND cbt."current_level" > $2))',
                        user_prestige, user_level
                    )
                    user_rank += 1  # Adjust rank to be 1-based

                    # Get partner information
                    partner_id = partner2_id if ctx.author.id == partner1_id else partner1_id
                    partner_username = await rpgtools.lookup(self.bot, partner_id)



                    text = _("**{partner1}** & **{partner2}** - Prestige {prestige}, Level {level}").format(
                        partner1=escape_markdown(ctx.author.name),
                        partner2=escape_markdown(partner_username),
                        prestige=user_prestige,
                        level=user_level
                    )
                    # Add spacing and indicate user's rank
                    result += _("\n**Your Rank:**\n")
                    result += f"{user_rank}. {text}\n"
                else:
                    # User is not in the Couples Battle Tower
                    result += _("\nYou are not currently ranked in the Couples Battle Tower.\n")

            # Send the leaderboard embed
            embed = discord.Embed(
                title=_("💕 Couples Battle Tower Leaderboard 💕"), 
                description=result, 
                colour=0xFF69B4  # Pink color for couples
            )
            await ctx.send(embed=embed)
        except Exception as e:
            await ctx.send(f"An error occurred: {str(e)}")


async def setup(bot: Bot) -> None:
    await bot.add_cog(Ranks(bot))
    await bot.tree.sync()

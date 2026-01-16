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
import datetime
import math
import random as randomm
from typing import Optional

import fable.utils.misc as rpgtools
from decimal import Decimal, ROUND_HALF_UP

from collections import deque
from decimal import Decimal

import random as rnd

import discord

from discord.enums import ButtonStyle
from discord.ext import commands
from discord.ui.button import Button

from fable.core.converters import IntFromTo
from fable.core.classes import Raider
from fable.core.classes import from_string as class_from_string
from fable.systems.help import chunks
from fable.systems.shard_communication import user_on_cooldown as user_cooldown
from fable.utils import random
from fable.utils.checks import has_char, is_gm
from fable.utils.i18n import _, locale_doc
from fable.utils.joins import JoinView


class Tournament(commands.Cog):
    def __init__(self, bot):
        self.deffbuff = 1
        self.bot = bot
        self.dmgbuff = 1

    def get_dmgbuff(self):
        return self.dmgbuff

    def get_deffbuff(self):
        return self.deffbuff

    async def get_raidstatsjug(
            self,
            thing,
            atkmultiply=None,
            defmultiply=None,
            classes=None,
            race=None,
            guild=None,
            god=None,
            conn=None,
    ):
        """Generates the raidstats for a user"""
        v = thing.id if isinstance(thing, (discord.Member, discord.User)) else thing
        local = False
        if conn is None:
            conn = await self.bot.pool.acquire()
            local = True
        if (
                atkmultiply is None
                or defmultiply is None
                or classes is None
                or guild is None
        ):
            row = await conn.fetchrow('SELECT * FROM profile WHERE "user"=$1;', v)
            atkmultiply, defmultiply, classes, race, guild, user_god = (
                row["atkmultiply"],
                row["defmultiply"],
                row["class"],
                row["race"],
                row["guild"],
                row["god"],
            )
            if god is not None and god != user_god:
                raise ValueError()
        damage, armor = await self.bot.get_damage_armor_for(
            v, classes=classes, race=race, conn=conn
        )
        if buildings := await self.bot.get_city_buildings(guild, conn=conn):
            atkmultiply += buildings["raid_building"] * Decimal("0.1")
            defmultiply += buildings["raid_building"] * Decimal("0.1")
        classes = [class_from_string(c) for c in classes]
        tournament_instance = Tournament(self)
        dmgbuff = self.dmgbuff
        deffbuff = self.deffbuff

        atkmultiply = atkmultiply + dmgbuff
        defmultiply = defmultiply + deffbuff
        dmg = damage * atkmultiply
        deff = armor * defmultiply
        if local:
            await self.bot.pool.release(conn)
        return dmg, deff

    @has_char()
    @user_cooldown(1800)
    @commands.command(brief=_("Start a new tournament"))
    @locale_doc
    async def tournament(self, ctx, prize: IntFromTo(0, 100_000_000) = 0):
        _(
            """`[prize]` - The amount of money the winner will get

            Start a new tournament. Players have 30 seconds to join via the reaction.
            Tournament entries are free, only the tournament host has to pay the price.

            Only an exponent of 2 (2^n) users can join. If there are more than the nearest exponent, the last joined players will be disregarded.

            The match-ups will be decided at random, the battles themselves will be decided like regular battles (see `{prefix}help battle` for details).

            The winner of a match moves onto the next round, the losers get eliminated, until there is only one player left.
            Tournaments in IdleRPG follow the single-elimination principle.

            (This command has a cooldown of 30 minutes.)"""
        )
        if ctx.character_data["money"] < prize:
            await self.bot.reset_cooldown(ctx)
            return await ctx.send(_("You are too poor."))

        await self.bot.pool.execute(
            'UPDATE profile SET "money"="money"-$1 WHERE "user"=$2;',
            prize,
            ctx.author.id,
        )

        if (
                self.bot.config.game.official_tournament_channel_id
                and ctx.channel.id == self.bot.config.game.official_tournament_channel_id
        ):
            view = JoinView(
                Button(
                    style=ButtonStyle.primary,
                    label="Join the tournament!",
                    emoji="\U00002694",
                ),
                message=_("You joined the tournament."),
                timeout=60 * 10,
            )
            await ctx.send(
                "A mass-tournament has been started. The tournament starts in 10 minutes! The"
                f" prize is **${prize}**!",
                view=view,
            )
            await asyncio.sleep(60 * 10)
            view.stop()
            participants = []
            async with self.bot.pool.acquire() as conn:
                for u in view.joined:
                    if await conn.fetchrow(
                            'SELECT * FROM profile WHERE "user"=$1;', u.id
                    ):
                        participants.append(u)

        else:
            view = JoinView(
                Button(
                    style=ButtonStyle.primary,
                    label="Join the tournament!",
                    emoji="\U00002694",
                ),
                message=_("You joined the tournament."),
                timeout=60 * 5,
            )
            view.joined.add(ctx.author)
            msg = await ctx.send(
                _(
                    "{author} started a tournament! Free entries, prize is"
                    " **${prize}**. Starting in **5 Minutes!**"
                ).format(author=ctx.author.mention, prize=prize),
                view=view,
            )
            await asyncio.sleep(60 * 5)
            view.stop()
            participants = []
            async with self.bot.pool.acquire() as conn:
                for u in view.joined:
                    if await conn.fetchrow(
                            'SELECT * FROM profile WHERE "user"=$1;', u.id
                    ):
                        participants.append(u)

        if len(participants) < 2:
            await self.bot.reset_cooldown(ctx)
            await self.bot.pool.execute(
                'UPDATE profile SET "money"="money"+$1 WHERE "user"=$2;',
                prize,
                ctx.author.id,
            )
            return await ctx.send(
                _("Noone joined your tournament {author}.").format(
                    author=ctx.author.mention
                )
            )

        bye_recipients = []  # To keep track of participants who received a bye

        nearest_power_of_2 = 2 ** math.ceil(math.log2(len(participants)))
        byes_needed = nearest_power_of_2 - len(participants)

        if byes_needed > 0:
            bye_recipients = random.sample(participants, byes_needed)
            for recipient in bye_recipients:
                await ctx.send(
                    _("Participant {participant} received a bye for this round!").format(participant=recipient.mention))
                participants.remove(recipient)
            await ctx.send(
                _("Tournament started with **{num}** entries.").format(num=len(participants) + len(bye_recipients))
            )
        text = _("vs")
        while len(participants) > 1:
            participants = random.shuffle(participants)
            matches = list(chunks(participants, 2))

            for match in matches:
                await ctx.send(f"{match[0].mention} {text} {match[1].mention}")
                await asyncio.sleep(2)
                async with self.bot.pool.acquire() as conn:
                    val1 = sum(
                        await self.bot.get_damage_armor_for(match[0], conn=conn)
                    ) + random.randint(1, 7)
                    val2 = sum(
                        await self.bot.get_damage_armor_for(match[1], conn=conn)
                    ) + random.randint(1, 7)
                if val1 > val2:
                    winner = match[0]
                    looser = match[1]
                elif val2 > val1:
                    winner = match[1]
                    looser = match[0]
                else:
                    winner = random.choice(match)
                    looser = match[1 - match.index(winner)]
                participants.remove(looser)
                await ctx.send(
                    _("Winner of this match is {winner}!").format(winner=winner.mention)
                )
                await asyncio.sleep(2)

            await ctx.send(_("Round Done!"))
            participants.extend(bye_recipients)  # Add back participants who received a bye
            bye_recipients = []  # Reset the list for the next round

        msg = await ctx.send(
            _("Tournament ended! The winner is {winner}.").format(
                winner=participants[0].mention
            )
        )

        async with self.bot.pool.acquire() as conn:
            await conn.execute(
                'UPDATE profile SET "money"="money"+$1 WHERE "user"=$2;',
                prize,
                participants[0].id,
            )
            await self.bot.log_transaction(
                ctx,
                from_=ctx.author.id,
                to=participants[0].id,
                subject="Torunament Winner",
                data={"Gold": prize},
                conn=conn,
            )
        await msg.edit(
            content=_(
                "Tournament ended! The winner is {winner}.\nMoney was given!"
            ).format(winner=participants[0].mention)
        )

    @has_char()
    @user_cooldown(300)
    @commands.command()
    @locale_doc
    async def juggernaut(self, ctx, prize: IntFromTo(0, 100_000_000) = 0, hp: int = 250, juggernaut_hp: int = 7500):
        _(
            """`[prize]` - The amount of money the winner will get.
        `[hp]` - The HP for each player; default is 250.
        `[juggernaut_hp]` - The HP for the Juggernaut; default is 7500.

        Start a Juggernaut game mode where one player becomes the Juggernaut, and others attempt to defeat them.

        Usage:
          `$juggernaut [prize] [hp] [juggernaut_hp]`

        In this game mode:
        - Players have 3 minutes to join via the button.
        - A random player is chosen as the Juggernaut.
        - The Juggernaut fights against all other players.
        - If the Juggernaut defeats all players, the players receive buffs and attempt again.
        - The game continues until the Juggernaut is defeated or all players are eliminated.
        - The prize money is split between the Juggernaut and the player who deals the finishing blow.

        Note:
        - You must have a character to use this command.
        - This command has a cooldown of 5 minutes.
        """
        )

        if ctx.character_data["money"] < prize:
            await self.bot.reset_cooldown(ctx)
            return await ctx.send(_("You are too poor."))


        await self.bot.pool.execute(
            'UPDATE profile SET "money"="money"-$1 WHERE "user"=$2;',
            prize,
            ctx.author.id,
        )

        if (
                self.bot.config.game.official_tournament_channel_id
                and ctx.channel.id == self.bot.config.game.official_tournament_channel_id
        ):
            view = JoinView(
                Button(
                    style=ButtonStyle.primary,
                    label="Join Juggernaut!",
                    emoji="\U00002694",
                ),
                message=_("You joined the Juggernaut Gamemode."),
                timeout=60 * 3,
            )
            if hp == 250:
                await ctx.send(
                    "A Juggernaut gamemode has been started. The gamemode starts in 3 minutes! The"
                    f" prize pool is **${prize}**!",
                    view=view,
                )
            else:
                await ctx.send(
                    f"A Juggernaut gamemode has been started. Custom HP set to {hp}! The Juggernaut gamemode starts in 3 minutes! The"
                    f" prize is **${prize}**!",
                    view=view,
                )
            await asyncio.sleep(60 * 5)
            view.stop()
            participants = []
            async with self.bot.pool.acquire() as conn:
                for u in view.joined:
                    if await conn.fetchrow(
                            'SELECT * FROM profile WHERE "user"=$1;', u.id
                    ):
                        participants.append(u)

        else:
            view = JoinView(
                Button(
                    style=ButtonStyle.primary,
                    label="Join juggernaut!",
                    emoji="\U00002694",
                ),
                message=_("You joined the juggernaut gamemode."),
                timeout=60 * 3,
            )
            view.joined.add(ctx.author)
            msg = await ctx.send(
                _(
                    "{author} started a juggernaut gamemode! Free entries, prize pool is"
                    " **${prize}**!"
                ).format(author=ctx.author.mention, prize=prize),
                view=view,
            )
            await asyncio.sleep(60 * 3)
            view.stop()
            participants = []
            async with self.bot.pool.acquire() as conn:
                for u in view.joined:
                    if await conn.fetchrow(
                            'SELECT * FROM profile WHERE "user"=$1;', u.id
                    ):
                        participants.append(u)

        if len(participants) < 3:
            await self.bot.reset_cooldown(ctx)
            await self.bot.pool.execute('UPDATE profile SET "money"="money"+$1 WHERE "user"=$2;', prize, ctx.author.id)
            return await ctx.send(
                _("Not enough participants to start the game, {author}.").format(author=ctx.author.mention))
        try:
            await ctx.send(f"There are {len(participants)} participants in the game.")
            # 2. Select a juggernaut
            juggernaut = random.choice(participants)

            # Get and double the juggernaut's stats
            async with self.bot.pool.acquire() as conn:
                juggernaut_dmg, juggernaut_deff = await self.bot.get_raidstats(juggernaut, conn=conn)
            juggernaut_deff *= 3

            await ctx.send(_(f"{juggernaut.mention} has been chosen as the juggernaut with **{juggernaut_hp}** HP!"))
            participants.remove(juggernaut)

            self.dmgbuff = 0
            self.deffbuff = 0

        except Exception as e:
            await ctx.send(f"{e}")

        def buff_stats(stats):
            def round_to_nearest(x, base=0.1):
                return round(x / base) * base

            self.deffbuff += Decimal(round_to_nearest(rnd.uniform(0.1, 0.2)))
            self.dmgbuff += Decimal(round_to_nearest(rnd.uniform(0.1, 0.2)))

        juggernaut_tracker_HP = juggernaut_hp
        TurnCounter = 0
        juggernaut_killer = None
        all_player_stats = {}
        defeated = []
        turnpass = False
        turn = False
        battle_ongoing = True  # Initialize a variable to track the battle state

        while participants and battle_ongoing:
            random.shuffle(participants)
            for player in participants:
                # Get player's stats
                if battle_ongoing:

                    try:
                        async with self.bot.pool.acquire() as conn:
                            dmg, deff = await self.get_raidstatsjug(player, conn=conn)
                            dmg = round(dmg, 2)
                            deff = round(deff, 2)

                        async with self.bot.pool.acquire() as conn:
                            dmgt, defft = await self.bot.get_raidstats(player, conn=conn)
                            dmgt = round(dmgt, 2)
                            defft = round(defft, 2)

                        await ctx.send(f"Normie: ATK {dmgt}, DEF {defft}. Modified: {dmg}, DEF {deff}")

                    except Exception as e:
                        await ctx.send(f"{e}")

                    player_stats = {
                        "user": player,
                        "hp": hp,  # This hp needs to be defined elsewhere
                        "armor": deff,
                        "damage": dmg,
                    }
                    all_player_stats[player.id] = player_stats
                    # Set up the battle participants
                    try:
                        players = [player_stats, {
                            "user": juggernaut,
                            "hp": juggernaut_tracker_HP,
                            "damage": juggernaut_dmg,
                            "armor": juggernaut_deff
                        }]
                    except Exception as e:
                        await ctx.send(f"An error occurred: {e}")

                    battle_log = deque(
                        [
                            (
                                0,
                                _("Raidbattle {p1} vs. {p2} started!").format(
                                    p1=players[0]["user"].mention, p2=players[1]["user"].mention
                                ),
                            )
                        ],
                        maxlen=3,
                    )

                    embed = discord.Embed(
                        description=battle_log[0][1],
                        color=self.bot.config.game.primary_colour,
                    )

                    log_message = await ctx.send(embed=embed)
                    await asyncio.sleep(4)

                    start = datetime.datetime.utcnow()
                    attacker, defender = players
                    while (
                            attacker["hp"] > 0
                            and defender["hp"] > 0
                            and datetime.datetime.utcnow()
                            < start + datetime.timedelta(minutes=5)
                    ):
                        dmg = (
                                attacker["damage"]
                                + Decimal(random.randint(0, 100))
                                - defender["armor"]
                        )
                        dmg = 1 if dmg <= 0 else dmg  # make sure no negative damage happens
                        if defender["user"] != juggernaut and TurnCounter >= 6:
                            await ctx.send("The Juggernaut charges their weapon")
                            dmg = dmg + 1000
                        defender["hp"] -= dmg
                        if defender["hp"] < 0:
                            defender["hp"] = 0
                        battle_log.append(
                            (
                                battle_log[-1][0] + 1,
                                _(
                                    "{attacker} attacks! {defender} takes **{dmg}HP**"
                                    " damage."
                                ).format(
                                    attacker=attacker["user"].mention,
                                    defender=defender["user"].mention,
                                    dmg=dmg,
                                ),
                            )
                        )

                        embed = discord.Embed(
                            description=_(
                                "{p1} - {hp1} HP left\n{p2} - {hp2} HP left"
                            ).format(
                                p1=players[0]["user"].mention,
                                hp1=players[0]["hp"],
                                p2=players[1]["user"].mention,
                                hp2=players[1]["hp"],
                            ),
                            color=self.bot.config.game.primary_colour,
                        )

                        for line in battle_log:
                            embed.add_field(
                                name=_("Action #{number}").format(number=line[0]),
                                value=line[1],
                            )
                        TurnCounter = TurnCounter + 1
                        await log_message.edit(embed=embed)
                        await asyncio.sleep(4)
                        juggernaut_tracker_HP = players[1]["hp"]
                        if juggernaut_tracker_HP <= 0:
                            await ctx.send(_("Juggernaut has been defeated!"))
                            juggernaut_killer = attacker["user"].id
                            await ctx.send(
                                _("{attacker} has dealt the finishing blow to the juggernaut and is the winner!").format(
                                    attacker=attacker["user"].mention))
                            battle_ongoing = False
                            self.deffbuff = 0
                            self.dmgbuff = 0
                            break
                        if players[0]["hp"] <= 0:
                            defeated.append(player)
                            await ctx.send(_(f"Juggernaut has defeated {player.name}!"))
                            TurnCounter = 0
                            juggernaut_tracker_HP = players[1]["hp"]
                            await asyncio.sleep(2)
                        attacker, defender = defender, attacker  # This line swaps attacker and defender

            # If all players are defeated, buff their stats and go for another round
            if battle_ongoing:
                if set(defeated) == set(participants):

                    for player in participants:
                        player_stats = all_player_stats[player.id]
                        random.shuffle(participants)
                        try:
                            buff_stats(player_stats)

                        except Exception as e:
                            await ctx.send(f"An error occurred: {e}")
                            continue  # move to the next player if there was an issue buffing this one

                        # Revive the player by resetting their HP to the original value
                        player_stats["hp"] = hp

                    # Clear the list of defeated players for the next round
                    turn = True
                    await ctx.send(
                        _(f"Juggernaut has defeated all participants! The party raid stats grown to am additional x{round(self.deffbuff, 2)} DEF and x{round(self.dmgbuff, 2)} ATK.")
                    )

                    defeated.clear()

        if battle_ongoing == False:
            totalprize = prize
            prizejug = prize * 0.2
            prize = prize * 0.8
            prize = round(prize)  # Rounds to the nearest whole number
            prizejug = round(prizejug)
            async with self.bot.pool.acquire() as conn:
                await conn.execute(
                    'UPDATE profile SET "money"="money"+$1 WHERE "user"=$2;',
                    prize,
                    juggernaut_killer,
                )
                await conn.execute(
                    'UPDATE profile SET "money"="money"+$1 WHERE "user"=$2;',
                    prizejug,
                    juggernaut.id,
                )
                await self.bot.log_transaction(
                    ctx,
                    from_=ctx.author.id,
                    to=participants[0].id,
                    subject="Juggernaut",
                    data={"Gold": prize},
                    conn=conn,
                )
            if prize > 0:
                await ctx.send(
                    f"Juggernaut received **${prizejug}** and {juggernaut_killer.mention} has received **${prize}** of the total prize of **{totalprize}**")

    import asyncio
    import random as randomm  # Keeping your original import
    from decimal import Decimal
    import discord
    from discord.ext import commands
    from discord.ui import Button, View
    from discord import ButtonStyle

    # Ensure that JoinView is defined elsewhere and remains unchanged
    # from your_views_module import JoinView

    @has_char()
    @user_cooldown(300)  # 5-minute cooldown
    @commands.command()
    @locale_doc
    async def juggernaut2(
            self,
            ctx,
            prize: IntFromTo(0, 100_000_000) = 0,
            hp: int = 250,
            juggernaut_hp: int = 7500,
    ):
        """
        `[prize]` - The amount of money the winner will get

        Start a new Juggernaut game mode. Players have 3 minutes to join via the button.
        Tournament entries are free; only the tournament host has to pay the prize.

        In this mode, all players team up to defeat the Juggernaut. If they fail, they get buffs and try again.
        The game continues until the Juggernaut is defeated or all players give up.

        (This command has a cooldown of 30 minutes.)
        """

        # Check if the user has enough money
        if ctx.character_data["money"] < prize:
            await self.bot.reset_cooldown(ctx)
            return await ctx.send("You don't have enough money to start the game.")

        # Deduct the prize from the host's money
        await self.bot.pool.execute(
            'UPDATE profile SET "money"="money" - $1 WHERE "user" = $2;',
            prize,
            ctx.author.id,
        )

        # Preserve your original JoinView implementation
        view = JoinView(
            Button(
                style=ButtonStyle.primary,
                label="Join Juggernaut!",
                emoji="⚔️",
            ),
            message="You joined the Juggernaut game mode.",
            timeout=300,  # 3 minutes timeout
        )

        view.joined.add(ctx.author)

        # Start the join phase
        initial_message = await ctx.send(
            f"{ctx.author.mention} started a Juggernaut game mode! Free entries, prize pool is **${prize}**! The game starts in 5 minutes!",
            view=view,
        )
        await asyncio.sleep(300)  # Wait for 3 minutes
        view.stop()

        # Gather valid participants from the database
        participants = []
        async with self.bot.pool.acquire() as conn:
            for u in view.joined:
                if await conn.fetchrow('SELECT * FROM profile WHERE "user"=$1;', u.id):
                    participants.append(u)

        # Check if there are enough participants
        if len(participants) < 3:
            await self.bot.reset_cooldown(ctx)
            await self.bot.pool.execute(
                'UPDATE profile SET "money" = "money" + $1 WHERE "user" = $2;',
                prize,
                ctx.author.id,
            )
            return await ctx.send(
                f"Not enough participants to start the game, {ctx.author.mention}."
            )

        await ctx.send(
            f"There are {len(participants)} participants in the game."
        )

        # Select a Juggernaut randomly
        juggernaut = randomm.choice(participants)
        participants.remove(juggernaut)

        # Get Juggernaut's stats without applying triple defense
        async with self.bot.pool.acquire() as conn:
            juggernaut_dmg, juggernaut_def = await self.bot.get_raidstats(juggernaut, conn=conn)

        # Set Juggernaut's HP based on its defense
        if juggernaut_def > 350:
            juggernaut_hp = 10000
        elif 200 <= juggernaut_def <= 350:
            juggernaut_hp = 20000
        elif 100 <= juggernaut_def < 200:
            juggernaut_hp = 50000
        else:
            juggernaut_hp = 75000

        try:
            await ctx.send(
                f"{juggernaut.mention} has been chosen as the Juggernaut with **{juggernaut_hp}** HP!"
            )

            # Initialize player stats
            player_stats = {}
            for player in participants:
                async with self.bot.pool.acquire() as conn:
                    dmg, deff = await self.get_raidstatsjug(player, conn=conn)
                player_stats[player.id] = {
                    "user": player,
                    "hp": Decimal(hp),
                    "damage": Decimal(dmg),
                    "defense": Decimal(deff),
                }

            juggernaut_stats = {
                "user": juggernaut,
                "hp": Decimal(juggernaut_hp),
                "damage": Decimal(juggernaut_dmg),
                "defense": Decimal(juggernaut_def),
                "base_damage": Decimal(juggernaut_dmg)  # To reset after revival
            }

            # Battle variables
            battle_round = 1
            battle_turn = 1
            buff_amount = Decimal("0.3")  # Increased buff amount for better scaling
            MAX_ROUNDS = 10  # Fixed maximum rounds for Juggernaut victory

            # Initialize the embed with battle status
            embed = discord.Embed(
                title=f"Juggernaut Battle - Round {battle_round}",
                description="The battle begins!",
                color=self.bot.config.game.primary_colour,
            )
            embed.add_field(
                name=f"{juggernaut_stats['user'].display_name}'s HP",
                value=f"{juggernaut_stats['hp']:.2f}/{juggernaut_hp}",
                inline=False,
            )
            player_statuses = []
            for stats in player_stats.values():
                status = (
                        f"{stats['user'].mention}: {stats['hp']:.2f}/{hp} HP"
                        + (" 💀" if stats["hp"] <= 0 else "")
                )
                player_statuses.append(status)
            embed.add_field(
                name="Players' Status",
                value="\n".join(player_statuses),
                inline=False,
            )
            battle_message = await ctx.send(embed=embed)

            # Battle loop
            while battle_round <= MAX_ROUNDS:
                battle_log = []
                embed.title = f"Juggernaut Battle - Round {battle_round}"
                embed.description = f"*Battle Round {battle_round} - Turn {battle_turn} begins!*\n"

                # Players' Turns
                for player_id, stats in player_stats.items():
                    if stats["hp"] <= 0:
                        continue  # Skip defeated players

                    # Determine if the attack hits
                    hit_chance = randomm.random()
                    if hit_chance < 0.1:
                        # Missed attack: No damage and skip logging
                        continue
                    elif hit_chance > 0.9:
                        # Critical hit
                        damage = stats["damage"] * Decimal("2") + Decimal("40")  # +40 for both abilities
                        battle_log.append(
                            f"{stats['user'].mention} landed a critical hit! 🔥"
                        )
                    else:
                        # Normal hit
                        damage = stats["damage"] + Decimal("40")  # +40 for both abilities

                    # Calculate damage to Juggernaut
                    dmg = max(Decimal("1"), damage - juggernaut_stats["defense"])
                    juggernaut_stats["hp"] -= dmg
                    juggernaut_stats["hp"] = max(juggernaut_stats["hp"], Decimal("0"))  # Ensure HP doesn't go below 0

                    # Log the damage if dmg > 0
                    if dmg > 0:
                        battle_log.append(
                            f"{stats['user'].mention} deals {dmg:.2f} damage to the Juggernaut. ✅"
                        )

                    # Update the embed after each attack
                    if battle_log:
                        embed.description += "\n".join(battle_log) + "\n"
                        embed.set_field_at(
                            0,
                            name=f"{juggernaut_stats['user'].display_name}'s HP",
                            value=f"{juggernaut_stats['hp']:.2f}/{juggernaut_hp}",
                            inline=False,
                        )
                        await battle_message.edit(embed=embed)
                        await asyncio.sleep(2)  # 2-second delay per attack
                        battle_log.clear()  # Clear the log for the next entry

                    # Check if Juggernaut is defeated
                    if juggernaut_stats["hp"] <= 0:
                        break

                # Check if Juggernaut is defeated
                if juggernaut_stats["hp"] <= 0:
                    battle_log.append("The Juggernaut has been defeated by the players! 🏆")
                    embed.description += "\n".join(battle_log) + "\n"
                    embed.set_field_at(
                        0,
                        name=f"{juggernaut_stats['user'].display_name}'s HP",
                        value=f"{juggernaut_stats['hp']:.2f}/{juggernaut_hp}",
                        inline=False,
                    )
                    await battle_message.edit(embed=embed)
                    # Set winner_ids to all players still alive
                    winner_ids = [pid for pid, stats in player_stats.items() if stats["hp"] > 0]
                    break  # Exit the battle loop

                # Juggernaut's Turn to Attack
                battle_log = []
                # Increment Juggernaut's damage by +40 for the new turn
                juggernaut_stats["current_damage"] = juggernaut_stats.get("current_damage",
                                                                          juggernaut_stats["base_damage"])
                juggernaut_stats["current_damage"] += Decimal("40")

                # Determine if Juggernaut uses Smash ability
                smash_chance = randomm.random()
                if smash_chance < 0.4:
                    # Smash ability: Attack all players with increased damage (+40)
                    battle_log.append("The Juggernaut uses Smash! 💥")
                    for stats in player_stats.values():
                        if stats["hp"] > 0:
                            dmg = max(
                                Decimal("1"),
                                (juggernaut_stats["current_damage"] + Decimal("40")) - stats["defense"]
                            )
                            stats["hp"] -= dmg
                            stats["hp"] = max(stats["hp"], Decimal("0"))  # Ensure HP doesn't go below 0
                            battle_log.append(
                                f"{stats['user'].mention} takes {dmg:.2f} damage from Smash. ⚔️"
                            )
                            if stats["hp"] <= 0:
                                battle_log.append(
                                    f"{stats['user'].mention} has been defeated! 💀"
                                )
                else:
                    # Normal attack: Attack one random alive player with increased damage (+40)
                    alive_players = [stats for stats in player_stats.values() if stats["hp"] > 0]
                    if alive_players:
                        target_stats = randomm.choice(alive_players)
                        dmg = max(
                            Decimal("1"), (juggernaut_stats["current_damage"] + Decimal("40")) - target_stats["defense"]
                        )
                        target_stats["hp"] -= dmg
                        target_stats["hp"] = max(target_stats["hp"], Decimal("0"))  # Ensure HP doesn't go below 0
                        battle_log.append(
                            f"The Juggernaut attacks {target_stats['user'].mention} for {dmg:.2f} damage. ⚔️"
                        )
                        if target_stats["hp"] <= 0:
                            battle_log.append(
                                f"{target_stats['user'].mention} has been defeated! 💀"
                            )

                # Announce the Juggernaut's attack results
                if battle_log:
                    embed.description += "\n".join(battle_log) + "\n"
                    embed.set_field_at(
                        0,
                        name=f"{juggernaut_stats['user'].mention}'s HP",
                        value=f"{juggernaut_stats['hp']:.2f}/{juggernaut_hp}",
                        inline=False,
                    )
                    # Update player statuses
                    player_statuses = []
                    for stats in player_stats.values():
                        status = (
                                f"{stats['user'].mention}: {stats['hp']:.2f}/{hp} HP"
                                + (" 💀" if stats["hp"] <= 0 else "")
                        )
                        player_statuses.append(status)
                    embed.set_field_at(
                        1,
                        name="Players' Status",
                        value="\n".join(player_statuses),
                        inline=False,
                    )
                    await battle_message.edit(embed=embed)
                    await asyncio.sleep(5)  # 5-second delay after Juggernaut's attack

                # Check if all players are defeated
                if all(stats["hp"] <= 0 for stats in player_stats.values()):
                    battle_log = ["All players have been defeated! They receive buffs and try again. 🔄"]
                    # Buff players' stats
                    for stats in player_stats.values():
                        stats["hp"] = Decimal(hp)
                        stats["damage"] *= (Decimal("1") + buff_amount)
                        stats["defense"] *= (Decimal("1") + buff_amount)
                    # Announce the buff
                    battle_log.append("Players have been buffed! Their damage and defense have increased. 📈")
                    # Increment the round
                    battle_round += 1
                    # Reset turns for the new round
                    battle_turn = 1
                    # Reset Juggernaut's damage to base_damage
                    juggernaut_stats["current_damage"] = juggernaut_stats["base_damage"]
                    # Update the embed with buff information
                    embed = discord.Embed(
                        title=f"Juggernaut Battle - Round {battle_round}",
                        description="\n".join(battle_log),
                        color=self.bot.config.game.primary_colour,
                    )
                    embed.add_field(
                        name=f"{juggernaut_stats['user'].mention}'s HP",
                        value=f"{juggernaut_stats['hp']:.2f}/{juggernaut_hp}",
                        inline=False,
                    )
                    player_statuses = []
                    for stats in player_stats.values():
                        status = (
                                f"{stats['user'].mention}: {stats['hp']:.2f}/{hp} HP"
                                + (" 💀" if stats["hp"] <= 0 else "")
                        )
                        player_statuses.append(status)
                    embed.add_field(
                        name="Players' Status",
                        value="\n".join(player_statuses),
                        inline=False,
                    )
                    await battle_message.edit(embed=embed)
                    await asyncio.sleep(3)  # 3-second wait between rounds
                    continue  # Continue to the next round

                # Increment the turn after Juggernaut's attack
                battle_turn += 1

                # Check if maximum rounds have been reached
                if battle_round > MAX_ROUNDS:
                    # Juggernaut wins
                    battle_log = ["Maximum number of rounds reached. The Juggernaut wins! ⚔️"]
                    embed.description += "\n".join(battle_log) + "\n"
                    embed.set_field_at(
                        0,
                        name=f"{juggernaut_stats['user'].mention}'s HP",
                        value=f"{juggernaut_stats['hp']:.2f}/{juggernaut_hp}",
                        inline=False,
                    )
                    # Update player statuses
                    player_statuses = []
                    for stats in player_stats.values():
                        status = (
                                f"{stats['user'].mention}: {stats['hp']:.2f}/{hp} HP"
                                + (" 💀" if stats["hp"] <= 0 else "")
                        )
                        player_statuses.append(status)
                    embed.set_field_at(
                        1,
                        name="Players' Status",
                        value="\n".join(player_statuses),
                        inline=False,
                    )
                    await battle_message.edit(embed=embed)
                    break  # Exit the battle loop

            # Distribute prizes
            juggernaut_prize = round(prize * 0.2)
            winner_prize = round(prize * 0.8)
            winners = [player_stats[pid]["user"] for pid in (winner_ids if 'winner_ids' in locals() else [])]

            async with self.bot.pool.acquire() as conn:
                # Give prize to Juggernaut
                await conn.execute(
                    'UPDATE profile SET "money" = "money" + $1 WHERE "user" = $2;',
                    juggernaut_prize,
                    juggernaut.id,
                )
                # Split prize among winners
                if winners:
                    prize_per_winner = winner_prize // len(winners)
                    for winner in winners:
                        await conn.execute(
                            'UPDATE profile SET "money" = "money" + $1 WHERE "user" = $2;',
                            prize_per_winner,
                            winner.id,
                        )
                        # Log transaction for each winner
                        await self.bot.log_transaction(
                            ctx,
                            from_=ctx.author.id,
                            to=winner.id,
                            subject="Juggernaut Game",
                            data={"Gold": prize_per_winner},
                            conn=conn,
                        )
                else:
                    prize_per_winner = 0  # No winners

            # Announce the results
            if winners:
                winner_mentions = ", ".join(winner.mention for winner in winners)
                await ctx.send(
                    f"Congratulations to {winner_mentions} for defeating the Juggernaut! Each winner receives **${prize_per_winner}**!"
                )
            else:
                await ctx.send(
                    "No winners this round. Better luck next time!"
                )
            await ctx.send(
                f"{juggernaut.mention} receives **${juggernaut_prize}** for participating as the Juggernaut."
            )
        except Exception as e:
            import traceback
            error_message = f"Error occurred: {e}\n{traceback.format_exc()}"
            await ctx.send(error_message)
            print(error_message)

    @has_char()
    @user_cooldown(1800)  # 30-minute cooldown, adjust as you wish
    @commands.command(name="brackettournament")
    @locale_doc
    async def brackettournament(
            self,
            ctx,
            prize: IntFromTo(0, 100_000_000) = 0,
            level_low: int = 1,
            level_high: int = 10
    ):
        """
        `<prize>` - The amount of money the winner will receive
        `<level_low>` - The minimum level for participants (inclusive)
        `<level_high>` - The maximum level for participants (inclusive)

        Starts a bracket-based tournament, restricted to players whose XP-based level
        (via rpgtools.xptolevel) is between `level_low` and `level_high`. Everyone in that range
        can join, and battles use the same advanced raidbattle logic (pets, reflection, etc.).

        The winner at the end receives the `prize` from the host.
        (This command has a 30-minute cooldown.)
        """

        # 1) Check the host can afford the prize
        if ctx.character_data["money"] < prize:
            await self.bot.reset_cooldown(ctx)
            return await ctx.send(_("You are too poor to start this bracket tournament."))

        # Deduct the prize from the host
        async with self.bot.pool.acquire() as conn:
            await conn.execute(
                'UPDATE profile SET "money"="money"-$1 WHERE "user"=$2;',
                prize,
                ctx.author.id,
            )

        # 2) Create a JoinView for players to join within 2 minutes (adjust as you like)
        view = JoinView(
            Button(
                style=ButtonStyle.primary,
                label=_("Join the bracket tournament!"),
                emoji="\U00002694",
            ),
            message=_("You joined the bracket tournament."),
            timeout=60 * 10  # 2 minutes
        )
        # Host auto-joins


        join_msg = await ctx.send(
            _(
                "{author} started a bracket tournament! Prize: **${prize}**.\n"
                "Level bracket: {low}–{high}.\n"
                "Click the button to join!"
            ).format(
                author=ctx.author.mention,
                prize=prize,
                low=level_low,
                high=level_high
            ),
            view=view,
        )

        # Wait for the join period
        await asyncio.sleep(10 * 60)  # 2 minutes
        view.stop()
        try:

            all_participants = list(view.joined)
            if len(all_participants) < 2:
                # Not enough participants
                await self.bot.reset_cooldown(ctx)
                # Refund
                async with self.bot.pool.acquire() as conn:
                    await conn.execute(
                        'UPDATE profile SET "money"="money"+$1 WHERE "user"=$2;',
                        prize,
                        ctx.author.id,
                    )
                return await ctx.send(_("No one else joined your bracket tournament, {author}.").format(
                    author=ctx.author.mention
                ))

            # 3) Filter by level range
            bracket_participants = []
            async with self.bot.pool.acquire() as conn:
                for user in all_participants:
                    xp = await conn.fetchval('SELECT xp FROM profile WHERE "user"=$1;', user.id)
                    if xp is None:
                        continue
                    lvl = rpgtools.xptolevel(xp)
                    if level_low <= lvl <= level_high:
                        bracket_participants.append(user)

            if len(bracket_participants) < 2:
                # Not enough valid participants
                await self.bot.reset_cooldown(ctx)
                # Refund
                async with self.bot.pool.acquire() as conn:
                    await conn.execute(
                        'UPDATE profile SET "money"="money"+$1 WHERE "user"=$2;',
                        prize,
                        ctx.author.id,
                    )
                return await ctx.send(
                    _("No valid participants in the level bracket ({low}–{high}).").format(
                        low=level_low,
                        high=level_high
                    )
                )

            await ctx.send(
                _(
                    "Bracket tournament starts with **{num}** players (Lv. {low}–{high})."
                ).format(
                    num=len(bracket_participants),
                    low=level_low,
                    high=level_high
                )
            )

            # 4) Single-Elimination Bracket (nearest power of 2, byes, etc.)
            participants = bracket_participants
            nearest_power_of_2 = 2 ** math.ceil(math.log2(len(participants)))
            byes_needed = nearest_power_of_2 - len(participants)

            bye_recipients = []
            if byes_needed > 0:
                bye_recipients = random.sample(participants, byes_needed)
                for bye_user in bye_recipients:
                    await ctx.send(
                        _("{participant} receives a bye for this round!").format(
                            participant=bye_user.mention
                        )
                    )
                    participants.remove(bye_user)

            await ctx.send(_("Tournament is now beginning! Good luck to all."))

            # 5) Run matches round by round
            while len(participants) > 1:
                random.shuffle(participants)
                matches = list(chunks(participants, 2))

                winners = []

                for match in matches:
                    # If odd leftover
                    if len(match) < 2:
                        winners.extend(match)
                        continue

                    p1, p2 = match
                    await ctx.send(f"{p1.mention} **VS** {p2.mention}")

                    # Run an advanced fight using the same logic as raidbattle
                    result_winner = await self.run_bracket_match(ctx, p1, p2)
                    if result_winner is None:
                        # It's a tie -> we can do what we want here. For bracket, we might just pick random or give both a loss.
                        # We'll pick a random winner to keep the bracket going:
                        result_winner = random.choice([p1, p2])
                        await ctx.send(_(
                            "Time limit or tie occurred! Randomly choosing {winner} to advance."
                        ).format(winner=result_winner.mention))

                    winners.append(result_winner)

                # Add back the bye recipients
                winners.extend(bye_recipients)
                bye_recipients = []  # reset for next round
                participants = winners

            # 6) Declare final champion
            champion = participants[0]
            await ctx.send(_(
                "Bracket Tournament ended! The champion is {winner}. Great battles!"
            ).format(winner=champion.mention))

            # 7) Award the prize
            async with self.bot.pool.acquire() as conn:
                await conn.execute(
                    'UPDATE profile SET "money"="money"+$1 WHERE "user"=$2;',
                    prize,
                    champion.id,
                )
                await self.bot.log_transaction(
                    ctx,
                    from_=ctx.author.id,
                    to=champion.id,
                    subject="Bracket Tournament Prize",
                    data={"Gold": prize},
                    conn=conn,
                )
            await ctx.send(
                _("Congratulations! {winner} received **${prize}**!").format(
                    winner=champion.mention,
                    prize=prize
                )
            )
        except Exception as e:
            await ctx.send(e)


    async def fetch_highest_element(self, user_id):
        try:
            highest_items = await self.bot.pool.fetch(
                "SELECT ai.element FROM profile p JOIN allitems ai ON (p.user=ai.owner) JOIN"
                " inventory i ON (ai.id=i.item) WHERE i.equipped IS TRUE AND p.user=$1"
                " ORDER BY GREATEST(ai.damage, ai.armor) DESC;",
                user_id,
            )
            highest_element = highest_items[0]["element"].capitalize() if highest_items and highest_items[0][
                "element"] else "Unknown"
            return highest_element
        except Exception as e:
            await self.bot.pool.execute(
                'UPDATE profile SET "element"="Unknown" WHERE "user"=$1;',
                user_id
            )
            return "Unknown"


    async def fetch_combatants(self, ctx, player, highest_element, level, lifesteal, mage_evolution, conn):
        try:
            # First check if player has a shield equipped
            shield_check = await conn.fetchrow(
                "SELECT ai.* FROM profile p JOIN allitems ai ON (p.user=ai.owner) "
                "JOIN inventory i ON (ai.id=i.item) WHERE p.user=$1 AND "
                "i.equipped IS TRUE AND ai.type='Shield';",
                player.id
            )
            has_shield = bool(shield_check)

            # Fetch stats
            query = 'SELECT "luck", "health", "stathp", "class" FROM profile WHERE "user" = $1;'
            result = await conn.fetchrow(query, player.id)
            if result:
                luck_value = float(result['luck'])
                if luck_value <= 0.3:
                    Luck = 20.0
                else:
                    Luck = ((luck_value - 0.3) / (1.5 - 0.3)) * 80 + 20
                Luck = round(Luck, 2)

                # Apply luck booster
                luck_booster = await self.bot.get_booster(player, "luck")
                if luck_booster:
                    Luck += Luck * 0.25
                    Luck = min(Luck, 100.0)

                base_health = 200.0
                health = float(result['health']) + base_health
                stathp = float(result['stathp']) * 50.0
                player_classes = result['class']
                dmg, deff = await self.bot.get_raidstats(player, conn=conn)

                # Ensure dmg and deff are floats
                dmg = float(dmg)
                deff = float(deff)

                total_health = health + level * 15.0 + stathp

                # Get tank evolution level from player classes
                tank_evolution = None
                tank_evolution_levels = {
                    "Protector": 1,
                    "Guardian": 2,
                    "Bulwark": 3,
                    "Defender": 4,
                    "Vanguard": 5,
                    "Fortress": 6,
                    "Titan": 7,
                }

                for class_name in player_classes:
                    if class_name in tank_evolution_levels:
                        level = tank_evolution_levels[class_name]
                        if tank_evolution is None or level > tank_evolution:
                            tank_evolution = level

                # Only apply tank bonuses if they have a shield equipped
                damage_reflection = 0.0
                if tank_evolution and has_shield:
                    # Health bonus: +4% per evolution
                    health_multiplier = 1 + (0.04 * tank_evolution)
                    total_health *= health_multiplier

                    # Damage reflection: +3% per evolution
                    damage_reflection = 0.03 * tank_evolution
                elif tank_evolution and not has_shield:
                    # If they're a tank but don't have a shield, still give them a smaller health bonus
                    # but no reflection
                    health_multiplier = 1 + (0.01 * tank_evolution)  # Half the normal bonus
                    total_health *= health_multiplier



                # Create combatant dictionary
                combatant = {
                    "user": player,
                    "hp": total_health,
                    "armor": deff,
                    "damage": dmg,
                    "luck": Luck,
                    "mage_evolution": mage_evolution,
                    "tank_evolution": tank_evolution,
                    "has_shield": has_shield,  # Add this to track shield status
                    "damage_reflection": damage_reflection,
                    "max_hp": total_health,
                    "is_pet": False,
                    "element": highest_element if highest_element else "Unknown"
                }


                return combatant, None
            else:
                # Default combatant if no profile found
                combatant = {
                    "user": player,
                    "hp": 500.0,
                    "armor": 50.0,
                    "damage": 50.0,
                    "luck": 50.0,
                    "mage_evolution": None,
                    "tank_evolution": None,
                    "has_shield": False,
                    "damage_reflection": 0.0,
                    "max_hp": 500.0,
                    "is_pet": False,
                    "element": "Unknown"
                }
                return combatant, None
        except Exception as e:
            await ctx.send(f"An error occurred while fetching stats for {player.display_name}: {e}")
            # Return default combatant
            combatant = {
                "user": player,
                "hp": 500.0,
                "armor": 50.0,
                "damage": 50.0,
                "luck": 50.0,
                "mage_evolution": None,
                "tank_evolution": None,
                "has_shield": False,
                "damage_reflection": 0.0,
                "max_hp": 500.0,
                "is_pet": False,
                "element": "Unknown"
            }
            return combatant, None

    def create_hp_bar(self, current_hp, max_hp, length=20):
        ratio = current_hp / max_hp if max_hp > 0 else 0
        ratio = max(0, min(1, ratio))  # Ensure ratio is between 0 and 1
        filled_length = int(length * ratio)
        bar = '█' * filled_length + '░' * (length - filled_length)
        return bar


    def select_target(self, player_combatant, pet_combatant, player_prob=0.60, pet_prob=0.40):
        targets = []
        weights = []
        if player_combatant and player_combatant['hp'] > 0:
            targets.append(player_combatant)
            weights.append(player_prob)
        if pet_combatant and pet_combatant['hp'] > 0:
            targets.append(pet_combatant)
            weights.append(pet_prob)
        if targets:
            return randomm.choices(targets, weights=weights)[0]
        else:
            return None



    async def run_bracket_match(self, ctx, player1: discord.Member, player2: discord.Member) -> Optional[
        discord.Member]:
        """
        Run an advanced battle between two players, with all the HP bars,
        class bonuses, lifesteal, reflection, and pet logic from your raidbattle code.

        Returns:
            winner (discord.Member) if there's a clear winner,
            or None if it's a tie (time ran out).
        """
        # Very similar to your raidbattle logic:
        try:
            # 1) Gather data needed for both combatants
            #    e.g. highest_element, classes, xp, etc.
            highest_element_p1 = await self.fetch_highest_element(player1.id)
            highest_element_p2 = await self.fetch_highest_element(player2.id)

            async with self.bot.pool.acquire() as conn:
                row_p1 = await conn.fetchrow('SELECT "class", "xp" FROM profile WHERE "user" = $1;', player1.id)
                row_p2 = await conn.fetchrow('SELECT "class", "xp" FROM profile WHERE "user" = $1;', player2.id)

            p1_classes = row_p1["class"] if row_p1 else []
            p1_xp = row_p1["xp"] if row_p1 else 0
            p1_level = rpgtools.xptolevel(p1_xp)

            p2_classes = row_p2["class"] if row_p2 else []
            p2_xp = row_p2["xp"] if row_p2 else 0
            p2_level = rpgtools.xptolevel(p2_xp)

            # 2) Calculate special bonuses (lifesteal, death chance, etc.)
            #    same approach as your raidbattle
            specified_words_values = {
                "Deathshroud": 20,
                "Soul Warden": 30,
                "Reaper": 40,
                "Phantom Scythe": 50,
                "Soul Snatcher": 60,
                "Deathbringer": 70,
                "Grim Reaper": 80,
            }
            life_steal_values = {
                "Little Helper": 7,
                "Gift Gatherer": 14,
                "Holiday Aide": 21,
                "Joyful Jester": 28,
                "Yuletide Guardian": 35,
                "Festive Enforcer": 40,
                "Festive Champion": 60,
            }

            p1_death_chance = sum(specified_words_values.get(c, 0) for c in p1_classes)
            p1_lifesteal = sum(life_steal_values.get(c, 0) for c in p1_classes)

            p2_death_chance = sum(specified_words_values.get(c, 0) for c in p2_classes)
            p2_lifesteal = sum(life_steal_values.get(c, 0) for c in p2_classes)

            # 3) Build full combatant dicts (including pets) using your fetch_combatants
            async with self.bot.pool.acquire() as conn:
                p1_combatant, p1_pet = await self.fetch_combatants(
                    ctx, player1, highest_element_p1, p1_level, p1_lifesteal, None, conn
                )
                # The "mage_evolution" param is included in your code. If you need it,
                # pass it. For brevity, passing None here or handle similarly.
                p2_combatant, p2_pet = await self.fetch_combatants(
                    ctx, player2, highest_element_p2, p2_level, p2_lifesteal, None, conn
                )

            # Optionally store the death_chance in the combatant for "cheat death" logic
            p1_combatant["deathchance"] = p1_death_chance
            if p1_pet:
                p1_pet["deathchance"] = 0

            p2_combatant["deathchance"] = p2_death_chance
            if p2_pet:
                p2_pet["deathchance"] = 0

            # 4) Prepare an embed and battle log
            battle_log = deque(
                [
                    f"**Action #0**\nBracket Match: {player1.mention} vs. {player2.mention}!"
                ],
                maxlen=5
            )
            embed = discord.Embed(
                title=f"Bracket Battle: {player1.display_name} vs {player2.display_name}",
                color=self.bot.config.game.primary_colour
            )
            # Initialize some fields
            for c in [p1_combatant, p1_pet, p2_combatant, p2_pet]:
                if c:
                    current_hp = round(c["hp"], 1)
                    max_hp = round(c["max_hp"], 1)
                    hp_bar = self.create_hp_bar(current_hp, max_hp)

                    field_name = (
                        c["pet_name"] if c.get("is_pet")
                        else c["user"].display_name
                    )
                    embed.add_field(name=field_name, value=f"HP: {current_hp}/{max_hp}\n{hp_bar}", inline=False)

            embed.add_field(name="Battle Log", value=battle_log[0], inline=False)
            log_message = await ctx.send(embed=embed)
            await asyncio.sleep(2)

            # 5) Combat Round Loop (similar to your raidbattle)
            start_time = datetime.datetime.utcnow()
            action_number = 1
            cheated_death_p1 = False
            cheated_death_p2 = False

            # You can define a turn order. E.g. randomly shuffle:
            turn_order = [p1_combatant, p1_pet, p2_combatant, p2_pet]
            random.shuffle(turn_order)

            while datetime.datetime.utcnow() < start_time + datetime.timedelta(minutes=5):
                # If both sides are wiped, tie
                if self.all_dead(p1_combatant, p1_pet) and self.all_dead(p2_combatant, p2_pet):
                    return None  # tie

                # If p1 is fully dead
                if self.all_dead(p1_combatant, p1_pet):
                    return player2  # p2 wins

                # If p2 is fully dead
                if self.all_dead(p2_combatant, p2_pet):
                    return player1  # p1 wins

                for attacker in turn_order:
                    if attacker is None or attacker["hp"] <= 0:
                        continue

                    # Determine the "defender side"
                    if attacker in [p1_combatant, p1_pet]:
                        defender_main, defender_pet = p2_combatant, p2_pet
                    else:
                        defender_main, defender_pet = p1_combatant, p1_pet

                    if self.all_dead(defender_main, defender_pet):
                        # They are all dead => attacker side wins
                        if attacker in [p1_combatant, p1_pet]:
                            return player1
                        else:
                            return player2

                    # Attacker chooses a target
                    target = self.select_target(defender_main, defender_pet)
                    if target is None:
                        continue

                    # Calculate damage (similar to your code):
                    dmg_variance = random.randint(0, 100 if not attacker.get("is_pet") else 50)
                    raw_damage = attacker["damage"] + dmg_variance
                    blocked = min(raw_damage, target["armor"])
                    dmg = max(raw_damage - target["armor"], 10)

                    # Apply damage
                    target["hp"] = max(target["hp"] - dmg, 0)

                    # Construct a small log message
                    attacker_name = attacker["pet_name"] if attacker.get("is_pet") else attacker["user"].mention
                    target_name = target["pet_name"] if target.get("is_pet") else target["user"].mention
                    action_text = f"{attacker_name} attacks! {target_name} takes **{dmg:.1f} HP** damage."

                    # Reflection if target is a tank with reflection
                    if target.get("damage_reflection", 0) > 0:
                        reflected_damage = round(blocked * target["damage_reflection"], 3)
                        if reflected_damage > 0:
                            attacker["hp"] = max(attacker["hp"] - reflected_damage, 0)
                            action_text += f" {target_name} reflects **{reflected_damage}** damage back!"

                    # Lifesteal if not pet
                    if not attacker.get("is_pet"):
                        # Check if this is p1 or p2
                        if attacker["user"].id == player1.id and p1_lifesteal > 0:
                            # attacker lifesteals
                            heal = round((p1_lifesteal / 100.0) * dmg, 3)
                            attacker["hp"] = min(attacker["hp"] + heal, attacker["max_hp"])
                            if heal > 0:
                                action_text += f" Lifesteal: **{heal}**"
                        elif attacker["user"].id == player2.id and p2_lifesteal > 0:
                            heal = round((p2_lifesteal / 100.0) * dmg, 3)
                            attacker["hp"] = min(attacker["hp"] + heal, attacker["max_hp"])
                            if heal > 0:
                                action_text += f" Lifesteal: **{heal}**"

                    # Check if target died => cheat death?
                    if target["hp"] <= 0 and not target.get("is_pet"):
                        # It's a player, see if they can cheat death once
                        if target["user"].id == player1.id and (p1_death_chance > 0) and not cheated_death_p1:
                            # roll
                            r = random.randint(1, 100)
                            if r <= p1_death_chance:
                                target["hp"] = 75
                                cheated_death_p1 = True
                                action_text += f"\n{attacker_name} delivered a lethal blow, but {target_name} cheated death and revives at 75 HP!"
                        elif target["user"].id == player2.id and (p2_death_chance > 0) and not cheated_death_p2:
                            r = random.randint(1, 100)
                            if r <= p2_death_chance:
                                target["hp"] = 75
                                cheated_death_p2 = True
                                action_text += f"\n{attacker_name} delivered a lethal blow, but {target_name} cheated death and revives at 75 HP!"

                    # Add to log
                    battle_log.append(f"**Action #{action_number}**\n{action_text}")
                    action_number += 1

                    # Update embed with new HP
                    embed = discord.Embed(
                        title=f"Bracket Battle: {player1.display_name} vs {player2.display_name}",
                        color=self.bot.config.game.primary_colour
                    )

                    for c in [p1_combatant, p1_pet, p2_combatant, p2_pet]:
                        if not c:
                            continue
                        current_hp = round(c["hp"], 1)
                        max_hp = round(c["max_hp"], 1)
                        hp_bar = self.create_hp_bar(current_hp, max_hp)

                        field_name = c["pet_name"] if c.get("is_pet") else c["user"].display_name
                        extra_info = ""
                        if c.get("damage_reflection", 0) > 0:
                            reflect_pc = round(c["damage_reflection"] * 100, 1)
                            extra_info = f" (Reflect {reflect_pc}%)"
                        field_value = f"HP: {current_hp}/{max_hp}\n{hp_bar}{extra_info}"
                        embed.add_field(name=field_name, value=field_value, inline=False)

                    # Add the battle log
                    log_str = "\n\n".join(battle_log)
                    embed.add_field(name="Battle Log", value=log_str, inline=False)

                    await log_message.edit(embed=embed)
                    await asyncio.sleep(3)

                    # Check if that attack ended the battle
                    if self.all_deaddraw(p1_combatant, p1_pet, p2_combatant, p2_pet):
                        await ctx.send(f"Both {player1.mention} and {player2.mention} have fallen and neither are able to proceed!")
                        return None
                    if self.all_dead(p1_combatant, p1_pet):
                        await ctx.send(f"{player2.mention} wins and advances to the next round!")
                        return player2
                    if self.all_dead(p2_combatant, p2_pet):
                        await ctx.send(f"{player1.mention} wins and advances to the next round!")
                        return player1

            # If we exit the while, it’s a 5-min timeout => tie
            return None

        except Exception as e:
            await ctx.send(f"Error in bracket match: {e}")
            return None

    def all_dead(self, main_combatant, pet_combatant):
        """
        Utility: Return True if main_combatant is dead (hp <= 0)
        AND pet_combatant is either None or also dead.
        """
        if not main_combatant or main_combatant["hp"] <= 0:
            if pet_combatant is None or pet_combatant["hp"] <= 0:
                return True
        return False

    def all_deaddraw(self, main_combatant, pet_combatant, main_combatant2, pet_combatant2):
        """
        Utility: Return True if main_combatant is dead (hp <= 0)
        AND pet_combatant is either None or also dead.
        """
        if not main_combatant or main_combatant["hp"] <= 0:
            if pet_combatant is None or pet_combatant["hp"] <= 0:
                if not main_combatant2 or main_combatant2["hp"] <= 0:
                    if pet_combatant2 is None or pet_combatant2["hp"] <= 0:
                        return True
        return False

    @commands.command()
    @has_char()
    @user_cooldown(1800)
    @locale_doc
    async def petstournament(self, ctx, prize: int = 0, base_hp: int = 250):
        """
        [prize] - The money prize for the winner.

        Start a pet-only tournament where only users’ equipped pets fight.
        Pets battle with their proper stats and HP bars in a style similar to the raid tournament.
        The winning owner is awarded the prize.
        (This command has a cooldown of 30 minutes.)
        """
        # Verify host still has an equipped pet.
        host_pet = await self.get_equipped_pet(ctx.author)
        if not host_pet:
            return await ctx.send("You need to have an equipped pet to host a pet tournament.")

        # Check host funds.
        async with self.bot.pool.acquire() as conn:
            money = await conn.fetchval('SELECT "money" FROM profile WHERE "user"=$1;', ctx.author.id)
        if money < prize:
            return await ctx.send("You do not have enough money to host this tournament.")

        # Deduct the host’s prize amount.
        await self.bot.pool.execute(
            'UPDATE profile SET "money"="money"-$1 WHERE "user"=$2;',
            prize, ctx.author.id
        )

        # Create a join view (without a check function).
        view = JoinView(
            Button(
                style=discord.ButtonStyle.primary,
                label="Join the pet tournament!",
                emoji="\U0001F43E"  # Using a paw print emoji.
            ),
            message="You joined the pet tournament!",
            timeout=300
        )

        # Announce the tournament.
        if (hasattr(self.bot.config.game, "official_tournament_channel_id") and
                ctx.channel.id == self.bot.config.game.official_tournament_channel_id):
            await ctx.send(
                f"A pet tournament has started! The tournament will begin in 5 minutes!\nPrize: **${prize}**",
                view=view
            )
        else:
            view.joined.add(ctx.author)
            await ctx.send(
                f"{ctx.author.mention} started a pet tournament!\nFree entries. Prize: **${prize}**",
                view=view
            )

        # Wait for the join period to elapse.
        await asyncio.sleep(300)
        view.stop()

        # Get list of participants; remove anyone who no longer has an equipped pet.
        participants = []
        async with self.bot.pool.acquire() as conn:
            for member in list(view.joined):
                profile = await conn.fetchrow('SELECT * FROM profile WHERE "user"=$1;', member.id)
                pet = await self.get_equipped_pet(member)
                if profile and pet:
                    participants.append(member)
                else:
                    await ctx.send(
                        f"{member.mention} has been disqualified for not having an equipped pet at tournament lock-in.")

        if len(participants) < 2:
            # Refund prize if too few participants remain.
            await self.bot.pool.execute(
                'UPDATE profile SET "money"="money"+$1 WHERE "user"=$2;',
                prize, ctx.author.id
            )
            return await ctx.send(
                f"Not enough participants remain. The pet tournament has been cancelled, {ctx.author.mention}.")

        # Adjust participants to a power of 2 (using byes).
        nearest_power = 2 ** math.ceil(math.log2(len(participants)))
        byes_needed = nearest_power - len(participants)
        bye_recipients = []
        if byes_needed > 0:
            bye_recipients = random.sample(participants, byes_needed)
            for bye in bye_recipients:
                await ctx.send(f"{bye.mention} receives a bye for this round!")
                participants.remove(bye)

        await ctx.send(f"Tournament starting with **{len(participants) + len(bye_recipients)}** entries!")

        round_no = 1
        # Run tournament bracket.
        while len(participants) > 1:
            await ctx.send(f"**Round {round_no} start!**")
            random.shuffle(participants)
            matches = list(self.chunks(participants, 2))
            winners_this_round = []
            for match in matches:
                if len(match) < 2:
                    winners_this_round.append(match[0])
                    continue

                # Recheck that both participants still have an equipped pet.
                pet1 = await self.get_equipped_pet(match[0])
                pet2 = await self.get_equipped_pet(match[1])
                if not pet1 and not pet2:
                    await ctx.send(
                        f"Both {match[0].mention} and {match[1].mention} have no equipped pet and are disqualified.")
                    continue
                elif not pet1:
                    await ctx.send(
                        f"{match[0].mention} has unequipped their pet and is disqualified. {match[1].mention} automatically wins the duel!")
                    winners_this_round.append(match[1])
                    continue
                elif not pet2:
                    await ctx.send(
                        f"{match[1].mention} has unequipped their pet and is disqualified. {match[0].mention} automatically wins the duel!")
                    winners_this_round.append(match[0])
                    continue

                # Announce the duel.
                duel_embed = discord.Embed(
                    title="Pet Duel",
                    description=f"{match[0].mention}'s **{pet1['name']}** vs {match[1].mention}'s **{pet2['name']}**",
                    color=self.bot.config.game.primary_colour
                )
                await ctx.send(embed=duel_embed)

                # Execute the pet duel.
                winner = await self.battle_pets(ctx, match[0], pet1, match[1], pet2, base_hp)
                winners_this_round.append(winner)
                await asyncio.sleep(2)

            # Next round participants: winners plus any byes from this round.
            participants = winners_this_round + bye_recipients
            bye_recipients = []  # Byes only apply for the first round.
            round_no += 1
            await asyncio.sleep(3)

        # Final champion.
        winner = participants[0]
        await ctx.send(f"🏆 The pet tournament has ended! Congratulations to {winner.mention} and their pet!")

        # Award prize to the winner.
        async with self.bot.pool.acquire() as conn:
            await conn.execute(
                'UPDATE profile SET "money"="money"+$1 WHERE "user"=$2;',
                prize, winner.id
            )
            await self.bot.log_transaction(
                ctx,
                from_=ctx.author.id,
                to=winner.id,
                subject="Pet Tournament Prize",
                data={"Gold": prize},
                conn=conn,
            )

    # –––––– Helper Methods –––––––

    async def get_equipped_pet(self, user: discord.Member):
        """
        Returns the user's equipped pet from monster_pets,
        or None if no pet is equipped.
        """
        async with self.bot.pool.acquire() as conn:
            pet = await conn.fetchrow(
                "SELECT * FROM monster_pets WHERE user_id = $1 AND equipped = TRUE;",
                user.id
            )
        return pet

    def create_hp_bar(self, current_hp, max_hp, length=20):
        ratio = current_hp / max_hp if max_hp > 0 else 0
        ratio = max(0, min(1, ratio))
        filled_length = int(length * ratio)
        bar = '█' * filled_length + '░' * (length - filled_length)
        return bar

    def chunks(self, lst, n):
        """
        Yield successive n-sized chunks from lst.
        """
        for i in range(0, len(lst), n):
            yield lst[i:i + n]

    async def battle_pets(self, ctx, owner1: discord.Member, pet1, owner2: discord.Member, pet2, base_hp: int):
        """
        Simulate a battle between two pets using the same embed style as your raid battles.
        Before the duel starts the pets' stats (including HP bars) are shown in two fields,
        and a third field labeled "Battle Log" displays log messages (last five entries only).
        If during battle a pet is missing (due to unequipping), the owner is disqualified.
        Returns the owner (discord.Member) of the winning pet.
        """
        # Build combatant dictionaries.
        combatant1 = {
            "owner": owner1,
            "name": pet1["name"],
            "hp": float(pet1["hp"]) if pet1["hp"] > 0 else base_hp,
            "attack": float(pet1["attack"]),
            "defense": float(pet1["defense"]),
            "element": pet1["element"].capitalize() if pet1["element"] else "Unknown",
            "max_hp": float(pet1["hp"]) if pet1["hp"] > 0 else base_hp
        }
        combatant2 = {
            "owner": owner2,
            "name": pet2["name"],
            "hp": float(pet2["hp"]) if pet2["hp"] > 0 else base_hp,
            "attack": float(pet2["attack"]),
            "defense": float(pet2["defense"]),
            "element": pet2["element"].capitalize() if pet2["element"] else "Unknown",
            "max_hp": float(pet2["hp"]) if pet2["hp"] > 0 else base_hp
        }

        # Prepare the battle log (max 5 entries).
        battle_log = deque(maxlen=5)
        battle_log.append(f"**Battle Start!** {combatant1['name']} VS {combatant2['name']}")

        # Create an embed displaying the current HP bars and battle log.
        embed = discord.Embed(
            title="Pet Duel",
            color=self.bot.config.game.primary_colour
        )
        embed.add_field(
            name=f"{combatant1['name']} ({combatant1['element']})",
            value=f"HP: {combatant1['hp']:.0f}/{combatant1['max_hp']:.0f}\n{self.create_hp_bar(combatant1['hp'], combatant1['max_hp'])}",
            inline=True
        )
        embed.add_field(
            name=f"{combatant2['name']} ({combatant2['element']})",
            value=f"HP: {combatant2['hp']:.0f}/{combatant2['max_hp']:.0f}\n{self.create_hp_bar(combatant2['hp'], combatant2['max_hp'])}",
            inline=True
        )
        embed.add_field(
            name="Battle Log",
            value="\n".join(battle_log),
            inline=False
        )
        battle_message = await ctx.send(embed=embed)
        await asyncio.sleep(2)

        # (Optional) Element modifier system.
        element_strengths = {"Fire": "Nature", "Nature": "Water", "Water": "Fire"}

        def calc_modifier(attacker, defender):
            if attacker["element"] in element_strengths and element_strengths[attacker["element"]] == defender[
                "element"]:
                return 0.2  # 20% bonus damage.
            return 0.0

        round_no = 1
        # Randomly determine who attacks first.
        attacker, defender = (combatant1, combatant2) if random.choice([True, False]) else (combatant2, combatant1)

        while combatant1["hp"] > 0 and combatant2["hp"] > 0:
            # Calculate damage with a small random variance and element modifier.
            modifier = calc_modifier(attacker, defender)
            raw_dmg = attacker["attack"] * (1 + modifier) + random.randint(0, 20)
            dmg = max(raw_dmg - defender["defense"], 1)
            defender["hp"] -= dmg
            if defender["hp"] < 0:
                defender["hp"] = 0

            battle_log.append(
                f"Round {round_no}: **{attacker['name']}** deals {dmg:.0f} damage to **{defender['name']}** (HP left: {defender['hp']:.0f}).")
            # Update embed fields.
            embed.set_field_at(0,
                               name=f"{combatant1['name']} ({combatant1['element']})",
                               value=f"HP: {combatant1['hp']:.0f}/{combatant1['max_hp']:.0f}\n{self.create_hp_bar(combatant1['hp'], combatant1['max_hp'])}",
                               inline=True
                               )
            embed.set_field_at(1,
                               name=f"{combatant2['name']} ({combatant2['element']})",
                               value=f"HP: {combatant2['hp']:.0f}/{combatant2['max_hp']:.0f}\n{self.create_hp_bar(combatant2['hp'], combatant2['max_hp'])}",
                               inline=True
                               )
            embed.set_field_at(2, name="Battle Log", value="\n".join(battle_log), inline=False)
            await battle_message.edit(embed=embed)
            await asyncio.sleep(2)

            # If a pet reaches 0 HP, break out.
            if defender["hp"] <= 0:
                battle_log.append(f"**{defender['name']}** has been defeated!")
                embed.set_field_at(2, name="Battle Log", value="\n".join(battle_log), inline=False)
                await battle_message.edit(embed=embed)
                break

            # Swap roles for next round.
            attacker, defender = defender, attacker
            round_no += 1

        # Determine winner.
        winner_owner = combatant1["owner"] if combatant1["hp"] > 0 else combatant2["owner"]
        return winner_owner


    @has_char()
    @user_cooldown(1800)
    @commands.command()
    @locale_doc
    async def raidtournament(self, ctx, prize: IntFromTo(0, 100_000_000) = 0, hp: int = 250):
        _(
            """`[prize]` - The amount of money the winner will get

            Start a new raid tournament. Players have 30 seconds to join via the reaction.
            Tournament entries are free, only the tournament host has to pay the price.

            Only an exponent of 2 (2^n) users can join. If there are more than the nearest exponent, the last joined players will be disregarded.

            The match-ups will be decided at random, the battles themselves will be decided like raid battles (see `{prefix}help raidbattle` for details).

            The winner of a match moves onto the next round, the losers get eliminated, until there is only one player left.
            Tournaments in IdleRPG follow the single-elimination principle.

            (This command has a cooldown of 30 minutes.)"""
        )
        try:
            author_chance = 0
            enemy_chance = 0
            lifestealauth = 0
            lifestealopp = 0
            authorchance = 0
            enemychance = 0
            cheated = False
            if ctx.character_data["money"] < prize:
                await self.bot.reset_cooldown(ctx)
                return await ctx.send(_("You are too poor."))

            await self.bot.pool.execute(
                'UPDATE profile SET "money"="money"-$1 WHERE "user"=$2;',
                prize,
                ctx.author.id,
            )

            if (
                    self.bot.config.game.official_tournament_channel_id
                    and ctx.channel.id == self.bot.config.game.official_tournament_channel_id
            ):
                view = JoinView(
                    Button(
                        style=ButtonStyle.primary,
                        label="Join the raid tournament!",
                        emoji="\U00002694",
                    ),
                    message=_("You joined the raid tournament."),
                    timeout=300,
                )
                if hp == 250:
                    await ctx.send(
                        "A mass-raidtournament has been started. The tournament starts in 5 minutes! The"
                        f" prize is **${prize}**!",
                        view=view,
                    )
                else:
                    await ctx.send(
                        f"A mass-raidtournament has been started. Custom HP set to {hp}! The tournament starts in 5 minutes! The"
                        f" prize is **${prize}**!",
                        view=view,
                    )
                await asyncio.sleep(60*5)
                view.stop()
                participants = []
                async with self.bot.pool.acquire() as conn:
                    for u in view.joined:
                        if await conn.fetchrow(
                                'SELECT * FROM profile WHERE "user"=$1;', u.id
                        ):
                            participants.append(u)

            else:
                view = JoinView(
                    Button(
                        style=ButtonStyle.primary,
                        label="Join the raid tournament!",
                        emoji="\U00002694",
                    ),
                    message=_("You joined the raid tournament."),
                    timeout=300,
                )
                view.joined.add(ctx.author)
                msg = await ctx.send(
                    _(
                        "{author} started a raid tournament! Free entries, prize is"
                        " **${prize}**!"
                    ).format(author=ctx.author.mention, prize=prize),
                    view=view,
                )
                await asyncio.sleep(60*5)


            # Process the users as before
            view.stop()
            participants = []
            async with self.bot.pool.acquire() as conn:
                for u in view.joined:
                    if await conn.fetchrow(
                            'SELECT * FROM profile WHERE "user"=$1;', u.id
                    ):
                        participants.append(u)
            if len(participants) < 2:
                await self.bot.reset_cooldown(ctx)
                await self.bot.pool.execute(
                    'UPDATE profile SET "money"="money"+$1 WHERE "user"=$2;',
                    prize,
                    ctx.author.id,
                )
                return await ctx.send(
                    _("Noone joined your raid tournament {author}.").format(
                        author=ctx.author.mention
                    )
                )

            bye_recipients = []  # To keep track of participants who received a bye

            nearest_power_of_2 = 2 ** math.ceil(math.log2(len(participants)))
            byes_needed = nearest_power_of_2 - len(participants)

            if byes_needed > 0:
                bye_recipients = random.sample(participants, byes_needed)
                for recipient in bye_recipients:
                    await ctx.send(
                        _("Participant {participant} received a bye for this round!").format(
                            participant=recipient.mention))
                    participants.remove(recipient)

            await ctx.send(
                _("Tournament started with **{num}** entries.").format(num=len(participants) + len(bye_recipients)))

            text = _("vs")
            while len(participants) > 1:
                participants = random.shuffle(participants)
                matches = list(chunks(participants, 2))

                for match in matches:
                    await ctx.send(f"{match[0].mention} {text} {match[1].mention}")

                    players = []
                    async with self.bot.pool.acquire() as conn:
                        for player in match:
                            author_chance = 0  # Initialize the variable inside the loop
                            lifestealauth = 0  # Initialize the variable inside the loop
                            specified_words_values = {
                                "Deathshroud": 20,
                                "Soul Warden": 30,
                                "Reaper": 40,
                                "Phantom Scythe": 50,
                                "Soul Snatcher": 60,
                                "Deathbringer": 70,
                                "Grim Reaper": 80,
                            }

                            life_steal_values = {
                                "Little Helper": 7,
                                "Gift Gatherer": 14,
                                "Holiday Aide": 21,
                                "Joyful Jester": 28,
                                "Yuletide Guardian": 35,
                                "Festive Enforcer": 40,
                                "Festive Champion": 60,
                            }
                            # User ID you want to check
                            user_id = ctx.author.id

                            try:


                                # Define common queries
                                query_class = 'SELECT "class" FROM profile WHERE "user" = $1;'
                                query_xp = 'SELECT "xp" FROM profile WHERE "user" = $1;'

                                # Query data for ctx.author.id
                                result_author = await self.bot.pool.fetch(query_class, player.id)
                                auth_xp = await self.bot.pool.fetch(query_xp, player.id)

                                # Convert XP to level for ctx.author.id
                                auth_level = rpgtools.xptolevel(auth_xp[0]['xp'])

                                # Query data for enemy_.id
                                result_opp = await self.bot.pool.fetch(query_class, player.id)
                                opp_xp = await self.bot.pool.fetch(query_xp, player.id)

                                # Convert XP to level for enemy_.id
                                opp_level = rpgtools.xptolevel(opp_xp[0]['xp'])

                                # Initialize chance

                                # await ctx.send(f"{author_chance}")
                                if result_author:
                                    author_classes = result_author[0]["class"]  # Assume it's a list of classes
                                    for class_name in author_classes:
                                        if class_name in specified_words_values:
                                            author_chance += specified_words_values[class_name]
                                        if class_name in life_steal_values:
                                            lifestealauth += life_steal_values[class_name]

                                if result_opp:
                                    opp_classes = result_opp[0]["class"]  # Assume it's a list of classes
                                    for class_name in opp_classes:
                                        if class_name in life_steal_values:
                                            lifestealopp += life_steal_values[class_name]
                                        if class_name in specified_words_values:
                                            enemy_chance += specified_words_values[class_name]
                                            # await ctx.send(f"{author_chance}")
                            except Exception as e:
                                await ctx.send(f"{e}")

                            if author_chance != 0:
                                authorchance = author_chance

                            user_id = player.id

                            luck_booster = await self.bot.get_booster(player, "luck")

                            query = 'SELECT "luck", "health", "stathp" FROM profile WHERE "user" = $1;'
                            result = await conn.fetchrow(query, user_id)

                            if result:
                                # Extract the health value from the result
                                base_health = 200
                                health = result['health'] + base_health
                                stathp = result['stathp'] * 50

                                # Calculate total health based on level and add to current health
                                level = rpgtools.xptolevel(
                                    auth_xp[0]['xp']) if player == ctx.author else rpgtools.xptolevel(opp_xp[0]['xp'])
                                total_health = health + (level * 15)
                                total_health = total_health + stathp

                            dmg, deff = await self.bot.get_raidstats(player, conn=conn)
                            u = {
                                "user": player,
                                "hp": total_health,
                                "armor": deff,
                                "damage": dmg,
                                "deathchance": author_chance,
                                "lifesteal": lifestealauth,
                            }
                            players.append(u)

                        #await ctx.send(f"DEBUG {players[0]} {players[1]}")

                    battle_log = deque(
                        [
                            (
                                0,
                                _("Raidbattle {p1} vs. {p2} started!").format(
                                    p1=players[0]["user"], p2=players[1]["user"]
                                ),
                            )
                        ],
                        maxlen=3,
                    )

                    embed = discord.Embed(
                        description=battle_log[0][1],
                        color=self.bot.config.game.primary_colour,
                    )

                    log_message = await ctx.send(embed=embed)
                    await asyncio.sleep(4)

                    start = datetime.datetime.utcnow()
                    attacker, defender = random.shuffle(players)

                    while (
                            players[0]["hp"] > 0
                            and players[1]["hp"] > 0
                            and datetime.datetime.utcnow() < start + datetime.timedelta(minutes=5)
                    ):
                        # this is where the fun begins
                        dmg = (
                                attacker["damage"] + Decimal(random.randint(0, 100)) - defender["armor"]
                        )
                        dmg = 1 if dmg <= 0 else dmg  # make sure no negative damage happens
                        defender["hp"] -= dmg
                        if defender["hp"] < 0:
                            defender["hp"] = 0

                        if defender["hp"] <= 0:
                            # Calculate the chance of cheating death for the defender (enemy)

                            chance = defender["deathchance"]

                            # Generate a random number between 1 and 100
                            random_number = random.randint(1, 100)

                            if not cheated:
                                # The player cheats death and survives with 50 HP
                                # await ctx.send(
                                # f"{authorchance}, {enemychance}, rand {random_number} (ignore this) ")  # -- Debug Line
                                if random_number <= chance:
                                    defender["hp"] = 75
                                    battle_log.append(
                                        (
                                            battle_log[-1][0] + 1,
                                            _("{defender} cheats death and survives with 75HP!").format(
                                                defender=defender["user"].mention,
                                            ),
                                        )
                                    )
                                    cheated = True
                                else:
                                    battle_log.append(
                                        (
                                            battle_log[-1][0] + 1,
                                            _("{attacker} deals **{dmg}HP** damage. {defender} is defeated!").format(
                                                attacker=attacker["user"].mention,
                                                defender=defender["user"].mention,
                                                dmg=dmg,
                                            ),
                                        )
                                    )
                            else:
                                # The player is defeated
                                battle_log.append(
                                    (
                                        battle_log[-1][0] + 1,
                                        _("{attacker} deals **{dmg}HP** damage. {defender} is defeated!").format(
                                            attacker=attacker["user"].mention,
                                            defender=defender["user"].mention,
                                            dmg=dmg,
                                        ),
                                    )
                                )
                        else:

                            if attacker["lifesteal"] > 0:
                                lifesteal_percentage = Decimal(lifestealauth) / Decimal(100)
                                heal = lifesteal_percentage * Decimal(dmg)
                                attacker["hp"] += heal.quantize(Decimal('0.00'), rounding=ROUND_HALF_UP)

                            if attacker["lifesteal"] > 0:

                                battle_log.append(
                                    (
                                        battle_log[-1][0] + 1,
                                        _("{attacker} attacks! {defender} takes **{dmg}HP** damage. Lifesteals: **{heal}**").format(
                                            attacker=attacker["user"].mention,
                                            defender=defender["user"].mention,
                                            dmg=dmg,
                                            heal=heal,
                                        ),
                                    )
                                )
                            else:
                                battle_log.append(
                                    (
                                        battle_log[-1][0] + 1,
                                        _("{attacker} attacks! {defender} takes **{dmg}HP** damage.").format(
                                            attacker=attacker["user"].mention,
                                            defender=defender["user"].mention,
                                            dmg=dmg,
                                        ),
                                    )
                                )

                        embed = discord.Embed(
                            description=_(
                                "{p1} - {hp1} HP left\n{p2} - {hp2} HP left").format(
                                p1=players[0]["user"],
                                hp1=players[0]["hp"],
                                p2=players[1]["user"],
                                hp2=players[1]["hp"],
                            ),
                            color=self.bot.config.game.primary_colour,
                        )

                        for line in battle_log:
                            embed.add_field(
                                name=_("Action #{number}").format(number=line[0]), value=line[1]
                            )

                        await log_message.edit(embed=embed)
                        await asyncio.sleep(4)
                        attacker, defender = defender, attacker  # switch places
                    if players[0]["hp"] == 0:
                        winner = match[1]
                        looser = match[0]
                    else:
                        winner = match[0]
                        looser = match[1]
                    participants.remove(looser)
                    await ctx.send(
                        _("Winner of this match is {winner}!").format(winner=winner.mention)
                    )
                    await asyncio.sleep(2)

                    await ctx.send(_("Round Done!"))
                    lifestealauth = 0
                    lifestealopp = 0
                    authorchance = 0
                    enemychance = 0
                    cheated = False
                    participants.extend(bye_recipients)  # Add back participants who received a bye
                    bye_recipients = []  # Reset the list for the next round
        except Exception as e:
            await ctx.send(e)

        msg = await ctx.send(
            _("Raid Tournament ended! The winner is {winner}.").format(
                winner=participants[0].mention
            )
        )

        async with self.bot.pool.acquire() as conn:
            await conn.execute(
                'UPDATE profile SET "money"="money"+$1 WHERE "user"=$2;',
                prize,
                participants[0].id,
            )
            await self.bot.log_transaction(
                ctx,
                from_=ctx.author.id,
                to=participants[0].id,
                subject="Tournament Prize",
                data={"Gold": prize},
                conn=conn,
            )
        await msg.edit(
            content=_(
                "Raid Tournament ended! The winner is {winner}.\nMoney was given!"
            ).format(winner=participants[0].mention)
        )


async def setup(bot):
    await bot.add_cog(Tournament(bot))

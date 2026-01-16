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
import decimal

from collections import deque
from decimal import Decimal

import discord
import random as random
from discord.enums import ButtonStyle
from discord.ext import commands
from discord.http import handle_message_parameters
from discord.ui.button import Button

from fable.core.classes import Ranger, Reaper
from fable.core.classes import from_string as class_from_string
from fable.core.converters import IntGreaterThan, MemberWithCharacter
from fable.systems.shard_communication import user_on_cooldown as user_cooldown
from fable.utils import random as randomm
from fable.utils.checks import has_char, has_money, is_gm
from fable.utils.i18n import _, locale_doc
from fable.utils.joins import SingleJoinView
import asyncpg


# Assuming you have a database connection pool (self.bot.pool) already set up

class Lottery(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(hidden=True)
    @is_gm()
    async def gmlotto(self, ctx, amount: int, tickets: int):
        # Update the database with the new lottery settings

        try:
            async with self.bot.pool.acquire() as connection:
                # Check if data already exists
                existing_data = await connection.fetchrow("SELECT 1 FROM lottodata LIMIT 1")

                if existing_data:
                    # If data exists, remove it
                    await connection.execute("DELETE FROM lottodata")

                # Insert the new data
                await connection.execute(
                    "INSERT INTO lottodata (maxtickets, ticketcost) VALUES ($1, $2)",
                    tickets, amount
                )

            await ctx.send(
                f"Lottery settings updated. Ticket cost: **${amount}**, Max tickets per player: **{tickets}**")

            # Send a message to the specified channel
            lottery_channel_id = 1408144167632371845  # Replace with your desired channel ID
            lottery_channel = self.bot.get_channel(lottery_channel_id)

            if lottery_channel:
                embed = discord.Embed(
                    title="Weekly Lotto Started!",
                    description=f"**Ticket Cost:** ${amount}\n**Max Tickets per Player:** {tickets}\n\nTo participate, use the commands:\n`$lotto` - View lottery information\n`$lotto buy [num_tickets]` - Purchase lottery tickets",
                    color=0x00ff00
                )
                await lottery_channel.send(embed=embed)

                # Tag the specified role after sending the embed
                role_id = 1411806405299671232  # Replace with your desired role ID
                role = ctx.guild.get_role(role_id)  # Retrieve the role object using role ID
                if role:  # Check if role exists
                    role_mention = role.mention  # Get the mention string of the role
                    await ctx.send(f"{role_mention} Lottery announcement sent!", allowed_mentions=discord.AllowedMentions(roles=True))  # Send message with role mention
                else:
                    await ctx.send(
                        "Error: Role not found. Please check the role ID.")  # Send error message if role not found


            else:
                await ctx.send("Error: Lottery channel not found. Please check the channel ID.")
        except Exception as e:
            await ctx.send(f"Error: {e}")

    @commands.command(
        hidden=True, aliases=["lt"], brief=_("Shows who owns how many tickets")
    )
    @is_gm()
    async def lottotickets(self, ctx):
        async with self.bot.pool.acquire() as connection:
            rows = await connection.fetch('SELECT * FROM lottery')

        results = []
        total_tickets = 0  # Initialize total tickets counter
        for row in rows:
            user_id = row['id']
            tickets = row['tickets']
            user = self.bot.get_user(user_id)
            display_name = user.display_name if user else f'Unknown User ({user_id})'
            results.append(f'{display_name}: {tickets} tickets')
            total_tickets += tickets  # Add tickets for the current user to total

        results.append(f'============')  # Append total tickets to results
        results.append(f'Total Tickets: {total_tickets}')  # Append total tickets to results

        await ctx.send('\n'.join(results))


    @commands.command(hidden=True)
    @has_char()
    @is_gm()
    @has_char()
    async def gmtickets(self, ctx, other: MemberWithCharacter, num_tickets: int = None):
        try:
            egg = True
            if egg:
                # Check if there is existing lottery data
                async with self.bot.pool.acquire() as connection:
                    existing_data = await connection.fetchrow("SELECT * FROM lottodata")
                    user_tickets = await connection.fetchval("SELECT tickets FROM lottery WHERE id = $1",
                                                             other.id)

                if existing_data:
                    # Fetch the current lottery settings from the database
                    async with self.bot.pool.acquire() as connection:
                        row = await connection.fetchrow("SELECT maxtickets, ticketcost FROM lottodata")

                    if row:
                        max_tickets = row['maxtickets']
                        ticket_cost = row['ticketcost']
                        usertickets = user_tickets or 0
                        maxtickets = (user_tickets or 0) + num_tickets

                        # Check if the user is trying to buy more tickets than the maximum limit

                        if maxtickets > max_tickets:
                            return await ctx.send(
                                f"You cannot purchase more than {max_tickets} tickets total. You have {usertickets}.")

                        if num_tickets is None:
                            await ctx.send("Please provide a valid number of tickets to purchase.")
                        else:
                            # Fetch the current number of tickets the user has
                            async with self.bot.pool.acquire() as connection:
                                user_id = other.id
                                user_tickets = await connection.fetchval("SELECT tickets FROM lottery WHERE id = $1",
                                                                         user_id)

                            # Calculate the total cost
                            total_cost = num_tickets * ticket_cost
                            #await ctx.send(f"{total_cost}")

                            updated_tickets = 0  # Initialize the variable outside the if block



                            if egg:
                                # Execute buy logic if the user confirms
                                async with self.bot.pool.acquire() as connection:
                                    # If the user doesn't exist in the table, insert a new row
                                    if user_tickets is None:
                                        await connection.execute("INSERT INTO lottery (id, tickets) VALUES ($1, $2)",
                                                                 user_id, num_tickets)
                                    else:
                                        # Update the number of tickets if the user already exists
                                        await connection.execute("UPDATE lottery SET tickets = $1 WHERE id = $2",
                                                                 user_tickets + num_tickets, user_id)

                                        # Fetch the updated number of tickets
                                    updated_tickets = await connection.fetchval(
                                        "SELECT tickets FROM lottery WHERE id = $1", user_id)

                                await ctx.send(
                                    f"You have successfully gave {user_id} {num_tickets} tickets for the lottery. They now have {updated_tickets} tickets.")
                                with handle_message_parameters(
                                        content="**{gm}** added tickets to **{other}**.\n\nReason: *{reason}*".format(
                                            gm=ctx.author,
                                            other=other,
                                            reason=f"<{ctx.message.jump_url}>",
                                        )
                                ) as params:
                                    await self.bot.http.send_message(
                                        self.bot.config.game.gm_log_channel,
                                        params=params,
                                    )
                            else:
                                await ctx.send("Purchase cancelled.")
                    else:
                        await ctx.send("No lottery settings found. Use $gmlotto to set them.")
                else:
                    await ctx.send("No lottery is currently running. Use $gmlotto to start a new lottery.")
            else:
                # Fetch and display lottery settings
                async with self.bot.pool.acquire() as connection:
                    row = await connection.fetchrow("SELECT maxtickets, ticketcost FROM lottodata")

                if row:
                    return

                else:
                    await ctx.send("No lottery settings found. Use $gmlotto to set them.")
        except Exception as e:
            await ctx.send(f"Error: {e}")

    @commands.command()
    @has_char()
    @locale_doc
    async def lotto(self, ctx, subcommand=None, num_tickets: int = None):
        _(
            """Participate in the lottery by buying tickets or viewing lottery information.

        **Usage:**
        - `$lotto`: View current lottery settings and your tickets.
        - `$lotto buy <num_tickets>`: Purchase lottery tickets.

        **Parameters:**
        - `[subcommand]`: Optional subcommand. Currently, only `'buy'` is supported.
        - `[num_tickets]`: Number of tickets to buy when using the `'buy'` subcommand. Must be a positive integer.

        **Details:**
        - **Buying Tickets:**
          - Use `$lotto buy <num_tickets>` to purchase lottery tickets.
          - Each ticket costs a set amount defined in the current lottery settings.
          - There is a maximum number of tickets you can purchase per player.
          - The total cost is calculated as `num_tickets * ticket_cost`.
          - You will be prompted for confirmation before the purchase is completed.
          - If you do not have enough money, the purchase will be canceled.

        - **Viewing Lottery Information:**
          - Simply use `$lotto` to view the current lottery settings, your ticket count, total tickets sold, and the current prize pool.

        **Notes:**
        - If no lottery is currently running, you will be informed.
        - **Game Masters** can start a new lottery using the `$gmlotto` command.
        """
        )

        try:
            if subcommand == 'buy':
                # Check if there is existing lottery data
                async with self.bot.pool.acquire() as connection:
                    existing_data = await connection.fetchrow("SELECT * FROM lottodata")
                    user_tickets = await connection.fetchval("SELECT tickets FROM lottery WHERE id = $1",
                                                             ctx.author.id)

                if existing_data:
                    # Fetch the current lottery settings from the database
                    async with self.bot.pool.acquire() as connection:
                        row = await connection.fetchrow("SELECT maxtickets, ticketcost FROM lottodata")

                    if row:
                        max_tickets = row['maxtickets']
                        ticket_cost = row['ticketcost']
                        usertickets = user_tickets or 0
                        maxtickets = (user_tickets or 0) + num_tickets

                        # Check if the user is trying to buy more tickets than the maximum limit

                        if maxtickets > max_tickets:
                            return await ctx.send(
                                f"You cannot purchase more than {max_tickets} tickets total. You have {usertickets}.")

                        if num_tickets is None or num_tickets <= 0:
                            await ctx.send("Please provide a valid number of tickets to purchase.")
                        elif num_tickets > max_tickets:
                            await ctx.send(f"You cannot purchase more than {max_tickets} tickets total.")
                        else:
                            # Fetch the current number of tickets the user has
                            async with self.bot.pool.acquire() as connection:
                                user_id = ctx.author.id
                                user_tickets = await connection.fetchval("SELECT tickets FROM lottery WHERE id = $1",
                                                                         user_id)

                            # Calculate the total cost
                            total_cost = num_tickets * ticket_cost
                            #await ctx.send(f"{total_cost}")

                            updated_tickets = 0  # Initialize the variable outside the if block

                            if ctx.character_data["money"] < total_cost:
                                return await ctx.send(_("You are too poor."))

                            # Ask for confirmation
                            confirmation_message = (
                                f"You are about to purchase **{num_tickets}** tickets for a total cost of **${total_cost}**.\n"
                                f"Your current ticket count is **{user_tickets or 0}**. Do you want to proceed?"
                            )

                            if await ctx.confirm(confirmation_message):
                                # Execute buy logic if the user confirms
                                if ctx.character_data["money"] < total_cost:
                                    return await ctx.send(_("You are too poor."))
                                async with self.bot.pool.acquire() as connection:
                                    await self.bot.pool.execute(
                                        'UPDATE profile SET "money"="money"-$1 WHERE "user"=$2;',
                                        total_cost,
                                        ctx.author.id,
                                    )
                                async with self.bot.pool.acquire() as connection:
                                    # If the user doesn't exist in the table, insert a new row
                                    if user_tickets is None:
                                        await connection.execute("INSERT INTO lottery (id, tickets) VALUES ($1, $2)",
                                                                 user_id, num_tickets)
                                    else:
                                        # Update the number of tickets if the user already exists
                                        await connection.execute("UPDATE lottery SET tickets = $1 WHERE id = $2",
                                                                 user_tickets + num_tickets, user_id)

                                        # Fetch the updated number of tickets
                                    updated_tickets = await connection.fetchval(
                                        "SELECT tickets FROM lottery WHERE id = $1", user_id)

                                await ctx.send(
                                    f"You have successfully purchased {num_tickets} tickets for the lottery. You now have {updated_tickets} tickets.")
                            else:
                                await ctx.send("Purchase cancelled.")
                    else:
                        await ctx.send("No lottery settings found. Use $gmlotto to set them.")
                else:
                    await ctx.send("No lottery is currently running. Use $gmlotto to start a new lottery.")
            else:
                # Fetch and display lottery settings
                async with self.bot.pool.acquire() as connection:
                    row = await connection.fetchrow("SELECT maxtickets, ticketcost FROM lottodata")

                if row:
                    max_tickets = row['maxtickets']
                    ticket_cost = row['ticketcost']

                    # Fetch and display user tickets from the lottery table
                    async with self.bot.pool.acquire() as connection:
                        user_tickets = await connection.fetch("SELECT id, tickets FROM lottery WHERE id = $1",
                                                              ctx.author.id)

                    # Fetch the total tickets and calculate the prize pool before releasing the connection
                    async with self.bot.pool.acquire() as connection:
                        total_tickets = await connection.fetchval("SELECT SUM(tickets) FROM lottery")

                    # Calculate prize pool
                    total_tickets = total_tickets or 0
                    prize_pool = total_tickets * ticket_cost

                    if user_tickets:
                        tickets_info = "\n".join(
                            [f"{self.bot.get_user(user['id']).display_name}: {user['tickets']} tickets" for user in
                             user_tickets])
                    else:
                        # If user_tickets is empty, assume the user has 0 tickets
                        tickets_info = f"{ctx.author.display_name}: 0 tickets"

                    # Construct and send the embed
                    embed = discord.Embed(title="Lottery Information", color=0x00ff00)
                    embed.add_field(name="**Current Lottery Settings**",
                                    value=f"Ticket Cost: ${ticket_cost}\nMax Tickets per Player: {max_tickets}")
                    embed.add_field(name="**User Tickets**", value=tickets_info, inline=False)
                    embed.add_field(name="**Total Tickets in the Lottery**", value=total_tickets, inline=False)
                    embed.add_field(name="**Prize Pool**", value=f"${prize_pool}", inline=False)

                    await ctx.send(embed=embed)

                else:
                    await ctx.send("No lottery settings found. Use $gmlotto to set them.")
        except Exception as e:
            await ctx.send(f"Error: {e}")



    @commands.command(hidden=True)
    @is_gm()
    async def gmdraw(self, ctx):
        # Fetch the current lottery settings from the database
        async with self.bot.pool.acquire() as connection:
            row = await connection.fetchrow("SELECT maxtickets, ticketcost FROM lottodata")

        if row:
            max_tickets = row['maxtickets']
            ticket_cost = row['ticketcost']

            # Fetch all participants and their ticket counts
            async with self.bot.pool.acquire() as connection:
                participants = await connection.fetch("SELECT id, tickets FROM lottery")

            if participants:
                # Create a weighted list for random selection
                weighted_list = []
                for participant in participants:
                    user_id = participant['id']
                    tickets = participant['tickets']
                    weighted_list.extend([user_id] * tickets)

                if weighted_list:
                    # Select a winner randomly from the weighted list
                    winner_id = random.choice(weighted_list)

                    # Notify the winner
                    winner = await self.bot.fetch_user(winner_id)
                    await ctx.send(f"Congratulations to {winner.mention}! You've won the lottery!")

                    # Reset the lottery data
                    async with self.bot.pool.acquire() as connection:
                        await connection.execute("DELETE FROM lottodata")
                        await connection.execute("DELETE FROM lottery")


                    await ctx.send("Lottery data has been reset for the next round.")
                else:
                    await ctx.send("No participants found. Lotto ended with no winner.")
                    try:
                        async with self.bot.pool.acquire() as connection:
                            await connection.execute("DELETE FROM lottodata")
                    except Exception as e:
                        pass
            else:
                await ctx.send("No participants found. Lotto ended with no winner.")
                try:
                    async with self.bot.pool.acquire() as connection:
                        await connection.execute("DELETE FROM lottodata")
                except Exception as e:
                    pass
        else:
            await ctx.send("No lottery settings found. Use $gmlotto to set them.")


async def setup(bot):
    await bot.add_cog(Lottery(bot))

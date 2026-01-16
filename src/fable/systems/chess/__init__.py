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

import chess.engine
import discord
from discord.ui import Button, View

from discord.ext import commands

from fable.utils.chess import ChessGame, ProtocolAdapter
from fable.utils.i18n import _, locale_doc


class ColorSelectionView(View):
    def __init__(self, author, timeout=30):
        super().__init__(timeout=timeout)
        self.author = author
        self.selected_color = None
        
    @discord.ui.button(label="White", style=discord.ButtonStyle.primary, emoji="⬜", row=0)
    async def white_button(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id != self.author.id:
            await interaction.response.send_message("This is not your game!", ephemeral=True)
            return
        self.selected_color = "white"
        await interaction.response.send_message("You selected **White**!", ephemeral=True)
        self.stop()
        
    @discord.ui.button(label="Black", style=discord.ButtonStyle.secondary, emoji="⬛", row=0)
    async def black_button(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id != self.author.id:
            await interaction.response.send_message("This is not your game!", ephemeral=True)
            return
        self.selected_color = "black"
        await interaction.response.send_message("You selected **Black**!", ephemeral=True)
        self.stop()


class DifficultySelectionView(View):
    def __init__(self, author, timeout=30):
        super().__init__(timeout=timeout)
        self.author = author
        self.selected_difficulty = None
        
    @discord.ui.button(label="Beginner", style=discord.ButtonStyle.success, row=0)
    async def beginner_button(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id != self.author.id:
            await interaction.response.send_message("This is not your game!", ephemeral=True)
            return
        self.selected_difficulty = "beginner"
        await interaction.response.send_message("You selected **Beginner** difficulty!", ephemeral=True)
        self.stop()
        
    @discord.ui.button(label="Easy", style=discord.ButtonStyle.success, row=0)
    async def easy_button(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id != self.author.id:
            await interaction.response.send_message("This is not your game!", ephemeral=True)
            return
        self.selected_difficulty = "easy"
        await interaction.response.send_message("You selected **Easy** difficulty!", ephemeral=True)
        self.stop()
        
    @discord.ui.button(label="Medium", style=discord.ButtonStyle.primary, row=0)
    async def medium_button(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id != self.author.id:
            await interaction.response.send_message("This is not your game!", ephemeral=True)
            return
        self.selected_difficulty = "medium"
        await interaction.response.send_message("You selected **Medium** difficulty!", ephemeral=True)
        self.stop()
        
    @discord.ui.button(label="Hard", style=discord.ButtonStyle.secondary, row=1)
    async def hard_button(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id != self.author.id:
            await interaction.response.send_message("This is not your game!", ephemeral=True)
            return
        self.selected_difficulty = "hard"
        await interaction.response.send_message("You selected **Hard** difficulty!", ephemeral=True)
        self.stop()
        
    @discord.ui.button(label="Expert", style=discord.ButtonStyle.danger, row=1)
    async def expert_button(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id != self.author.id:
            await interaction.response.send_message("This is not your game!", ephemeral=True)
            return
        self.selected_difficulty = "expert"
        await interaction.response.send_message("You selected **Expert** difficulty!", ephemeral=True)
        self.stop()
        
    @discord.ui.button(label="Master", style=discord.ButtonStyle.danger, row=1)
    async def master_button(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id != self.author.id:
            await interaction.response.send_message("This is not your game!", ephemeral=True)
            return
        self.selected_difficulty = "master"
        await interaction.response.send_message("You selected **Master** difficulty!", ephemeral=True)
        self.stop()


class Chess(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.matches = {}
        # Define difficulty modes with their corresponding depth values
        self.difficulty_modes = {
            "beginner": 1,
            "easy": 3,
            "medium": 8,
            "hard": 15,
            "expert": 25,
            "master": 35
        }
        asyncio.create_task(self.initialize())

    async def initialize(self):
        await self.bot.wait_until_ready()
        try:
            _, adapter = await asyncio.get_running_loop().create_connection(
                lambda: ProtocolAdapter(chess.engine.UciProtocol()), "127.0.0.1", 4000
            )
        except ConnectionRefusedError:
            self.bot.logger.warning(
                "FAILED to connect to stockfish backend, unloading chess cog..."
            )
            self.bot.unload_extension("fable.systems.chess")
            return
        self.engine = adapter.protocol
        await self.engine.initialize()

    @commands.group(invoke_without_command=True, brief=_("Play chess."))
    @locale_doc
    async def chess(self, ctx):
        _(
            """FableRPG's Chess system. You can play against AI or other users and gain ELO."""
        )
        await ctx.send(
            _(
                "Please use `{prefix}chess match` to play.\nIf you want to play"
                " ELO-rated, you must use `{prefix}chess register` first.\n"
                "The match command will guide you through color and difficulty selection with buttons."
            ).format(prefix=ctx.clean_prefix)
        )

    @chess.command(brief=_("Register for ELO-rating in FableRPG."))
    @locale_doc
    async def register(self, ctx):
        _(
            """Register an ELO-rating eligible account for Idle's Chess.
            The rating determines your relative skill and can be increased/decreased by winning/losing matches."""
        )
        async with self.bot.pool.acquire() as conn:
            if await conn.fetchrow(
                'SELECT * FROM chess_players WHERE "user"=$1;', ctx.author.id
            ):
                return await ctx.send(_("You are already registered."))
            await conn.execute(
                'INSERT INTO chess_players ("user") VALUES ($1);', ctx.author.id
            )
        await ctx.send(
            _(
                "You have been registered with an ELO of 1000 as a default. Play"
                " matches against other registered users to increase it!"
            )
        )

    @chess.command(brief=_("Shows global ELO stats for FableRPG chess."))
    @locale_doc
    async def elo(self, ctx):
        _(
            """Shows your ELO and the best chess players' ELO rating limited to FableRPG's chess."""
        )
        async with self.bot.pool.acquire() as conn:
            player = await conn.fetchrow(
                'SELECT * FROM chess_players WHERE "user"=$1;', ctx.author.id
            )
            top_players = await conn.fetch(
                'SELECT * FROM chess_players ORDER BY "elo" DESC LIMIT 15;'
            )
            top_text = ""
            for idx, row in enumerate(top_players):
                user = await self.bot.get_user_global(row["user"]) or "Unknown Player"
                text = _("**{user}** with ELO **{elo}**").format(
                    user=user, elo=row["elo"]
                )
                top_text = f"{top_text}{idx + 1}. {text}\n"
            embed = discord.Embed(title=_("Chess ELOs")).add_field(
                name=_("Top 15"), value=top_text
            )
            if player:
                player_pos = await conn.fetchval(
                    "SELECT position FROM (SELECT chess_players.*, ROW_NUMBER()"
                    " OVER(ORDER BY chess_players.elo DESC) AS position FROM"
                    " chess_players) s WHERE s.user = $1 LIMIT 1;",
                    ctx.author.id,
                )
                text = _("**{user}** with ELO **{elo}**").format(
                    user=ctx.author, elo=player["elo"]
                )
                text = f"{player_pos}. {text}"
                embed.add_field(name=_("Your position"), value=text)
            await ctx.send(embed=embed)

    @chess.group(invoke_without_command=True, brief=_("Play a chess match."))
    @locale_doc
    async def match(
        self,
        ctx,
        enemy: discord.Member = None,
    ):
        _(
            """Play a chess match against AI or another player.
            
            **Flow:**
            1. Choose your color (White/Black) with buttons
            2. If playing against AI, choose difficulty with buttons
            3. If playing against another player, they will be asked to accept the challenge
            
            **Examples:**
            - `{prefix}chess match` - Play against AI (will prompt for color and difficulty)
            - `{prefix}chess match @user` - Challenge a user to a match
            """
        )
        try:
            if enemy == ctx.author:
                return await ctx.send(_("You cannot play against yourself."))
            
            # Step 1: Color selection
            color_view = ColorSelectionView(ctx.author, timeout=30)
            color_embed = discord.Embed(
                title=_("Choose Your Color"),
                description=_("Please select the color you want to play as:"),
                color=discord.Color.blurple()
            )
            color_msg = await ctx.send(embed=color_embed, view=color_view)
            
            # Wait for color selection
            try:
                await color_view.wait()
            except asyncio.TimeoutError:
                await color_msg.edit(content=_("You took too long to choose a color."), embed=None, view=None)
                return
            
            if color_view.selected_color is None:
                await color_msg.edit(content=_("No color was selected."), embed=None, view=None)
                return
                
            side = color_view.selected_color
            await color_msg.delete()

            # Step 2: Difficulty selection (only for AI games)
            difficulty_value = None
            difficulty_name = "PvP"
            
            if enemy is None:  # Playing against AI
                difficulty_view = DifficultySelectionView(ctx.author, timeout=30)
                difficulty_embed = discord.Embed(
                    title=_("Choose AI Difficulty"),
                    description=_("Please select the difficulty level for the AI:"),
                    color=discord.Color.green()
                )
                difficulty_msg = await ctx.send(embed=difficulty_embed, view=difficulty_view)
                
                # Wait for difficulty selection
                try:
                    await difficulty_view.wait()
                except asyncio.TimeoutError:
                    await difficulty_msg.edit(content=_("You took too long to choose difficulty."), embed=None, view=None)
                    return
                
                if difficulty_view.selected_difficulty is None:
                    await difficulty_msg.edit(content=_("No difficulty was selected."), embed=None, view=None)
                    return
                
                difficulty_value = self.difficulty_modes[difficulty_view.selected_difficulty]
                difficulty_name = difficulty_view.selected_difficulty.title()
                await difficulty_msg.delete()



            if enemy is not None:
                async with self.bot.pool.acquire() as conn:
                    player_elo = await conn.fetchval(
                        'SELECT elo FROM chess_players WHERE "user"=$1;', ctx.author.id
                    )
                    enemy_elo = await conn.fetchval(
                        'SELECT elo FROM chess_players WHERE "user"=$1;', enemy.id
                    )
                if player_elo is not None and enemy_elo is not None:
                    rated = await ctx.confirm(
                        _(
                            "{author}, would you like to play an ELO-rated match? Your elo"
                            " is {elo1}, their elo is {elo2}."
                        ).format(
                            author=ctx.author.mention, elo1=player_elo, elo2=enemy_elo
                        ),
                    )
                else:
                    rated = False

                if not await ctx.confirm(
                        _(
                            "{user}, you have been challenged to a chess match by {author}."
                            " They will be {color}. Do you accept? {extra}"
                        ).format(
                            user=enemy.mention,
                            author=ctx.author.mention,
                            color=side,
                            extra=_("**The match will be ELO rated!**") if rated else "",
                        ),
                        user=enemy,
                ):
                    return await ctx.send(
                        _("{user} rejected the chess match.").format(user=enemy)
                    )
            else:
                rated = False

            if self.matches.get(ctx.channel.id):
                return await ctx.send(_("Wait for the match here to end."))
            
            # Send confirmation message with difficulty info
            if enemy is None:
                await ctx.send(
                    _("Starting chess match against AI ({difficulty_name})! You are playing as {color}.").format(
                        difficulty_name=difficulty_name, color=side
                    )
                )
            
            self.matches[ctx.channel.id] = ChessGame(
                ctx, ctx.author, side, enemy, difficulty_value, rated
            )
            try:
                await self.matches[ctx.channel.id].run()
            except Exception as inner_exception:
                del self.matches[ctx.channel.id]
                raise inner_exception
            del self.matches[ctx.channel.id]

        except Exception as e:
            await ctx.send(f"An error occurred: {str(e)}")

    @match.command(brief=_("Shows past moves for this game"))
    @locale_doc
    async def moves(self, ctx):
        _(
            """Shows the moves of the current match in the channel that you and your opponent took."""
        )
        game = self.matches.get(ctx.channel.id)
        if not game:
            return await ctx.send(_("No game here."))
        moves = "\n".join(
            [f"{idx + 1}. {i}" for idx, i in enumerate(game.pretty_moves())]
        )
        await ctx.send(moves)

    @chess.command(brief=_("Shows available difficulty modes for AI chess."))
    @locale_doc
    async def difficulties(self, ctx):
        _("""Shows the available difficulty modes when playing against AI.""")
        embed = discord.Embed(
            title=_("Chess AI Difficulty Modes"),
            description=_("Available difficulty levels when playing against AI:"),
            color=discord.Color.green()
        )
        
        for mode, depth in self.difficulty_modes.items():
            embed.add_field(
                name=mode.title(),
                value=_("Depth: {depth} - {description}").format(
                    depth=depth,
                    description=self._get_difficulty_description(mode)
                ),
                inline=True
            )
        
        embed.add_field(
            name=_("Custom"),
            value=_("You can also use any number 1-40 for custom difficulty."),
            inline=False
        )
        
        await ctx.send(embed=embed)
    
    def _get_difficulty_description(self, mode):
        descriptions = {
            "beginner": "Perfect for new players",
            "easy": "Good for casual players",
            "medium": "Balanced challenge",
            "hard": "Experienced players",
            "expert": "Very challenging",
            "master": "Maximum difficulty"
        }
        return descriptions.get(mode, "Custom difficulty")

    def cog_unload(self):
        if hasattr(self, "engine"):
            asyncio.create_task(self.engine.quit())


async def setup(bot):
    await bot.add_cog(Chess(bot))

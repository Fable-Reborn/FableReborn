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
from discord.ui import View, Button, button
import random
import aiohttp
import asyncio
from utils.checks import is_gm

WHITE_CARDS_URL = "https://raw.githubusercontent.com/PrototypeX37/CAHList/main/cah_black.txt"
BLACK_CARDS_URL = "https://raw.githubusercontent.com/PrototypeX37/CAHList/main/cah_white.txt"


class JudgingButton(Button):
    def __init__(self, label, ctx):  # Added a ctx parameter
        super().__init__(style=discord.ButtonStyle.primary, label=label)
        self.ctx = ctx  # Store the ctx

    async def callback(self, interaction: discord.Interaction):
        card_number = int(self.label.split(" ")[1])
        await self.view.cah.pick_winner(interaction, card_number, self.ctx)  # Pass the ctx to pick_winner
        self.view.stopped = True  # Add this line
        self.view.stop()


class JudgingView(View):
    def __init__(self, cah_instance, ctx, num_cards, timeout_duration=60):
        super().__init__(timeout=timeout_duration)
        self.cah = cah_instance
        self.ctx = ctx
        self.stopped = False  # Add this line

        for i in range(1, num_cards + 1):
            button = JudgingButton(f"Card {i}", ctx)
            self.add_item(button)


class CardButton(Button):
    def __init__(self, cah_instance, player, index, card, **kwargs):
        super().__init__(**kwargs)
        self.cah = cah_instance
        self.player = player
        self.index = index
        self.card = card
        self.required_cards_for_round = 1

    async def callback(self, interaction: discord.Interaction):
        try:
            if len(self.cah.played_cards.get(self.player, [])) >= self.cah.required_cards_for_round:
                await interaction.response.send_message(
                    "You've already chosen the maximum number of cards for this round!")
                return

            if self.card in self.cah.played_cards.get(self.player, []):
                await interaction.response.send_message("You've already chosen this card!")
                return

            # The card is now appended to the player's list of played cards
            if self.player not in self.cah.played_cards:
                self.cah.played_cards[self.player] = []
            self.cah.played_cards[self.player].append(self.card)

            # Store cards to be removed later in a list
            cards_to_remove = []

            player_hand = self.cah.players.get(self.player, [])

            print("Player's hand before removing:", player_hand)
            print("Attempting to access index:", self.index)

            if self.card in player_hand:
                cards_to_remove.append(self.card)

            # Remove the cards after collecting all the cards to be removed.
            for card in cards_to_remove:
                if card in player_hand:
                    player_hand.remove(card)

            print("Player's hand after removing:", player_hand)

            message = await interaction.response.send_message(
                f"You've chosen your card for this round! Shortcut back to {self.cah.ctx.channel.mention}")

            if interaction.user.id not in self.cah.last_messages:
                self.cah.last_messages[interaction.user.id] = []

            self.cah.last_messages[interaction.user.id].append(message)

        except Exception as e:
            await interaction.response.send_message(f"An error occurred: {e}")


class CardSelectionView(View):
    def __init__(self, cah_instance, player):
        super().__init__(timeout=60)
        self.cah = cah_instance
        self.player = player

        for index, card in enumerate(cah_instance.players[player], 1):
            button = CardButton(cah_instance, player, index - 1, card, style=discord.ButtonStyle.primary,
                                label=f"Card {index}")
            self.add_item(button)


class CardsAgainstHumanity(commands.Cog):
    def __init__(self, bot):
        self.ctx = None
        self.white_cards = None
        self.black_cards = None
        self.bot = bot
        self.players = {}  # {player: [hand]}
        self.scores = {}  # {player: score}
        self.played_cards = {}  # {player: card}
        self.current_black_card = ""
        self.game_state = "inactive"  # possible values: waiting, started, judging
        self.judge = None
        self.last_messages = {}
        self.skips = {}
        self.lobby_open = False

    async def fetch_cards(self, url):
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status != 200:
                    return []
                data = await response.text()
                return data.splitlines()

    async def judge_timeout(self, view: JudgingView, delay: int):
        await self.ctx.send("Timer Started!")
        await asyncio.sleep(delay)  # Wait for the specified delay

        # Check if the view has already been stopped (i.e., a choice was made)
        if not view.stopped:
            await self.ctx.send("The judge took too long to choose! Ending this round.")
            await self.end_round(self.ctx)

    @commands.command()
    async def cah(self, ctx):
        # Check if a game is already running
        if self.game_state not in ["inactive", "waiting"] or self.lobby_open:
            await ctx.send("A game of Cards Against Humanity is already in progress!")
            return
        self.ctx = ctx
        self.lobby_open = True

        # Initialize/reset the game
        self.players = {}  # Reset players list
        self.scores = {}
        self.played_cards = {}
        self.current_black_card = ""
        self.game_state = "waiting"
        self.judge = None

        # Send an invitation message
        await ctx.send(
            "A new game of Cards Against Humanity is starting! Type `$cahjoin` to join the game! You have 2 minutes to "
            "join.")

        if ctx.author not in self.players:
            # Deal 7 white cards to the new player
            self.players[ctx.author] = []
            self.scores[ctx.author] = 0

        # Wait for 2 minutes
        await asyncio.sleep(30)

        self.lobby_open = False

        if len(self.players) < 3:  # Assuming a minimum of 2 players to start a game
            await ctx.send("Not enough players to start the game.")
            self.game_state = "inactive"
            return

        self.black_cards = await self.fetch_cards(BLACK_CARDS_URL)
        self.white_cards = await self.fetch_cards(WHITE_CARDS_URL)
        # Shuffle the players to determine the first judge
        player_list = list(self.players.keys())
        random.shuffle(player_list)
        self.judge = player_list[0]

        # Deal white cards to each player
        for player in self.players.keys():
            self.players[player] = random.sample(self.white_cards, 7)
            await self.show_hand(player)
        self.game_state = "started"
        await self.rotate_judge(ctx)
        await self.start_round(ctx)

    @commands.command()
    async def cahjoin(self, ctx):
        if self.game_state != "waiting" or self.game_state == "inactive":
            await ctx.send(
                "There's no game currently accepting players. Wait for a new game to start or initiate one with `$cah`!")
            return

        if ctx.author not in self.players:
            # Deal 7 white cards to the new player
            self.players[ctx.author] = random.sample(self.white_cards, 7)

            # Initialize their score
            self.scores[ctx.author] = 0

            await ctx.send(f"{ctx.author.mention} has joined the game and received their cards!")
        else:
            await ctx.send(f"{ctx.author.mention}, you're already in the game!")

    async def rotate_judge(self, ctx):
        player_list = list(self.players.keys())

        current_index = player_list.index(self.judge)
        next_index = (current_index + 1) % len(player_list)

        self.judge = player_list[next_index]
        await ctx.send(f"**{self.judge.mention}** has been selected to be the judge!")

    def all_players_played(self):
        for player in self.players:
            if player == self.judge:  # Exclude the judge
                continue

            played_count = len(self.played_cards.get(player, []))

            if played_count < self.required_cards_for_round:
                return False

        return True

    async def start_round(self, ctx):
        try:
            self.played_cards = {}

            self.current_black_card = random.choice(self.black_cards)
            await ctx.send(f"**Selecting a black card..**")
            await asyncio.sleep(5)
            required_cards_for_round = self.current_black_card.count('_')
            if required_cards_for_round == 0:
                self.required_cards_for_round = 1
            else:
                self.required_cards_for_round = required_cards_for_round
            embed_color = 0x1C1C1C  # A different shade of black

            embed = discord.Embed(title="**Black Card!**", color=embed_color)

            # Use the provided image as the thumbnail
            embed.set_thumbnail(url="https://i.ibb.co/82tdznC/back-black.png")

            # Add the game name as the author with an icon
            embed.set_author(name="Cards Against Humanity - Fable Edition",
                             icon_url="https://i.ibb.co/37jwws4/6204e99fbddc85da51bd3def67e083bc.png")

            # Using the description to set the challenge content
            challenge_content = f"\n**{self.current_black_card}**\n"
            embed.description = "\n" + challenge_content + "\n"  # Add a newline at the start and end

            # Setting the footer with a note about the game and adding an icon
            embed.set_footer(text="\nChoose your best white card to win this round!")

            await ctx.send(embed=embed)

            for player in self.players.keys():
                if player != self.judge:
                    for _ in range(self.required_cards_for_round):
                        view = CardSelectionView(self, player)  # Create a new view object for each card selection

                        message = await player.send(
                            f"Please select a card for the black card: **{self.current_black_card}** (if buttons appear twice, you are required to pick 2 cards!)",
                            view=view)

                        if player.id not in self.last_messages:
                            self.last_messages[player.id] = []

                        self.last_messages[player.id].append(message)

            await ctx.send("Players have 2 minutes to play their cards...")
            await self.wait_for_players()

            for player in self.players.keys():
                if player == self.judge:  # Skip the judge
                    continue
                num_cards_played = len(self.played_cards.get(player, []))

                if num_cards_played < self.required_cards_for_round:
                    await ctx.send(f"{player.mention} didn't play enough cards and is skipped this round!")
                    # Increment skip count for the player
                    self.skips[player] = self.skips.get(player, 0) + 1

                    # If player has 2 consecutive skips, kick them
                    if self.skips[player] >= 2:
                        await ctx.send(
                            f"{player.mention} has been inactive for 2 consecutive rounds and is removed from the game!")
                        del self.players[player]
                        del self.scores[player]
                        del self.skips[player]

                        # Check if less than 2 players are left and declare winner(s) if true
                        if len(self.players) < 3:
                            max_score = max(self.scores.values())
                            max_score_players = [player for player, score in self.scores.items() if score == max_score]

                            if len(max_score_players) == 1:
                                await ctx.send(
                                    f"The game has ended due to lack of players! The winner is {max_score_players[0].mention} 🥳")
                            else:
                                winners_mentions = ', '.join([winner.mention for winner in max_score_players])
                                await ctx.send(
                                    f"The game has ended due to lack of players! It's a tie between {winners_mentions} 🎉")

                            await self.end_game(ctx)
                            return  # exit the loop since the game has ended

                else:
                    # If player played this round, reset their skip count
                    if player in self.skips:
                        del self.skips[player]

            await self.show_cards_for_judging(ctx)

        except Exception as e:
            await self.ctx.send(f"An error occurred during the round: {e}")
            raise e

    async def show_hand(self, player):
        try:
            player_hand = self.players[player]

            # Using a gradient color for visual enhancement
            embed_color = 0x3498db  # Light blue color

            # Add a title and description for context
            embed = discord.Embed(
                title="🃏 Your Cards 🃏",
                description=f"Here's your current hand, {player.name}!",
                color=embed_color
            )
            if player.avatar:
                embed.set_thumbnail(url=player.avatar.url)
            else:
                default_avatar_url = "https://i.ibb.co/m4HzBGG/image-12.png"
                embed.set_thumbnail(url=default_avatar_url)
            # Optionally, you can set a thumbnail for the embed (e.g., a card image or player's avatar)

            # Adding each card in the player's hand
            for index, card in enumerate(player_hand, 1):
                embed.add_field(name=f"Card {index}", value=card, inline=False)

            # Sending the embed message
            message = await player.send(embed=embed)

            # Storing the message for future reference
            self.store_message(player.id, message)

        except Exception as e:
            await self.ctx.send(f"🚫 Error showing hand for {player.mention}: {e}")

    def store_message(self, player_id, message):
        """Store the sent message for future reference."""
        if player_id not in self.last_messages:
            self.last_messages[player_id] = []
        self.last_messages[player_id].append(message)

    async def wait_for_players(self):
        for _ in range(120):  # Check for 120 seconds
            if self.all_players_played():
                break
            await asyncio.sleep(2)

    async def show_cards_for_judging(self, ctx):
        embed_color = 0xE6E6E6  # A lighter shade of gray

        embed = discord.Embed(title="🃏 **Played Cards** 🃏", color=embed_color)

        # Use an image to make the embed visually appealing
        embed.set_thumbnail(url="https://i.ibb.co/82tdznC/back-black.png")

        # Add the game name as the author with an icon
        embed.set_author(name="Cards Against Humanity - Fable Edition",
                         icon_url="https://i.ibb.co/37jwws4/6204e99fbddc85da51bd3def67e083bc.png")

        # Using bold for the Black Card description
        black_card_content = f"**Black Card:** {self.current_black_card}"
        embed.add_field(name="🖤 Current Challenge:", value=black_card_content, inline=False)

        embed.set_footer(text="Choose your favorite response!",
                         icon_url="https://i.ibb.co/VMSGRDk/trophy.png")

        for index, (player, cards) in enumerate(self.played_cards.items(), 1):
            if player == self.judge:
                continue  # Skip the judge's cards
            card_text = self.current_black_card  # Start with the black card text
            for card in cards:
                card_text = card_text.replace("_", f"**{card}**", 1)  # Replace one underscore at a time
            embed.add_field(name=f"Card Set {index}", value=card_text, inline=False)

        # Create a JudgingView and attach it to the message
        view = JudgingView(self, ctx, len(self.played_cards))  # Set 60 seconds for the judge to pick
        await ctx.send(embed=embed, view=view)
        await ctx.send(f"{self.judge.mention} Please choose your favorite card! You have 2 minutes to decide.")

        # Schedule the timeout function
        asyncio.create_task(self.judge_timeout(view, 60))

    async def pick_winner(self, interaction, card_number, ctx):
        # Ensure that only the judge can pick the winner.
        if interaction.user != self.judge:
            await interaction.response.send_message("Only the judge can pick the winner!", ephemeral=True)
            return

        # Extract the player who played the chosen card
        winning_player = list(self.played_cards.keys())[card_number - 1]
        self.scores[winning_player] += 1
        await interaction.response.send_message(f"{winning_player.name}'s card was chosen and scored a point!")
        embed_color = 0x00FF00  # Green color

        # Creating the embed with added title, description, and color.
        embed = discord.Embed(
            title="🏆 Scores 🏆",
            description="Here are the current scores for all players.",
            color=embed_color
        )
        for player, score in self.scores.items():
            embed.add_field(name=player.name, value=str(score), inline=False)

        # Adding the image to the embed
        embed.set_thumbnail(url="https://i.ibb.co/37jwws4/6204e99fbddc85da51bd3def67e083bc.png")

        # Setting the footer
        embed.set_footer(text="Cards Against Humanity - Fable Edition")

        # Using the interaction's follow-up to send the embed
        await interaction.followup.send(embed=embed)

        # Here, after announcing the winner for the round, we'll transition to the end of the round.
        await asyncio.sleep(5)
        await self.end_round(ctx)

        # Prepare for the next round or end the game as needed.

    async def end_round(self, ctx):

        await self.rotate_judge(ctx)

        for player, cards_played in self.played_cards.items():
            # Determine the number of cards to give back based on the number played.
            num_cards_to_give = len(cards_played)

            for _ in range(num_cards_to_give):
                new_card = random.choice(self.white_cards)
                self.white_cards.remove(new_card)  # Remove the card from the deck to prevent repetition.
                self.players[player].append(new_card)  # Give the new card to the player.

                # Notify players of their new card:
                await player.send(f"You've received a new card for the next round: {new_card}")

        # Clear the played cards for the next round.
        self.played_cards = {}
        round_limit = 10
        highest_score = max(self.scores.values())
        if highest_score >= round_limit:
            max_score_players = [player for player, score in self.scores.items() if score == highest_score]

            if self.game_state == "inactive":
                return

            if len(max_score_players) == 1:
                await ctx.send(f"The game has ended! The winner is {max_score_players[0].mention} 🥳")
            else:
                winners_mentions = ', '.join([winner.mention for winner in max_score_players])
                await ctx.send(f"The game has ended! It's a tie between {winners_mentions} 🎉")

            await self.end_game(ctx)
        else:
            for player in self.players.keys():
                embed = discord.Embed(title="Your Cards", color=0xFFFFFF)  # White color
                for index, card in enumerate(self.players[player], 1):  # Fetch cards of the current player
                    embed.add_field(name=f"Card {index}", value=card, inline=False)
                await player.send(embed=embed)  # Send the embed to the current player

            await self.start_round(ctx)

    @commands.command()
    async def cahjoin(self, ctx):
        if self.game_state == 'inactive':
            await ctx.send("There is currently no active CAH Game.")
            return

        if ctx.author not in self.players:
            self.players[ctx.author] = []
            self.scores[ctx.author] = 0
            await ctx.send(f"{ctx.author.mention} has joined the game!")

    @commands.command()
    async def scores(self, ctx):
        embed = discord.Embed(title="Scores", color=0x00FF00)  # Green color
        for player, score in self.scores.items():
            embed.add_field(name=player.name, value=str(score), inline=False)
        await ctx.send(embed=embed)

    @commands.command()
    async def cahinstructions(self, ctx):
        embed = discord.Embed(title="🎲 Cards Against Humanity Instructions", color=0x3498db)  # Blue color

        embed.add_field(name="🚀 Starting the Game", value="The game is started with the `cah` command.", inline=False)
        embed.add_field(name="👥 Joining", value="Players join the game using the `cahjoin` command.", inline=False)
        embed.add_field(name="🃏 Playing Cards",
                        value="Players will receive their hand in DMs and must choose a card to play within a set time.",
                        inline=False)
        embed.add_field(name="🤣 Judging", value="After everyone has played, the judge will choose the funniest card.",
                        inline=False)
        embed.add_field(name="🏆 Scoring", value="Points are awarded, and a new round begins.", inline=False)
        embed.add_field(name="🚪 Leaving the Game", value="Players can leave using `cahleave`", inline=False)

        embed.set_thumbnail(
            url="https://i.ibb.co/37jwws4/6204e99fbddc85da51bd3def67e083bc.png")  # Example URL. Replace if needed.

        embed.set_footer(text="Enjoy the game and play responsibly!")

        await ctx.send(embed=embed)

    @commands.command()
    async def cahleave(self, ctx):
        if ctx.author in self.players:
            del self.players[ctx.author]
            del self.scores[ctx.author]
            await ctx.send(f"{ctx.author.mention} has left the game!")
        else:
            await ctx.send(f"{ctx.author.mention}, you're not in the game!")

    async def end_game(self, ctx):
        # Resetting the game variables
        self.players = {}
        self.scores = {}
        self.played_cards = {}
        self.current_black_card = ""
        self.game_state = "inactive"
        self.judge = None
        await ctx.send("The game has been ended!")

    @is_gm()
    @commands.command()
    async def forceendcah(self, ctx):
        # Resetting the game variables
        self.players = {}
        self.scores = {}
        self.played_cards = {}
        self.current_black_card = ""
        self.game_state = "inactive"
        self.judge = None
        await ctx.send("The game has been ended!")


async def setup(bot):
    await bot.add_cog(CardsAgainstHumanity(bot))

import asyncio
import datetime
import re
import traceback

from discord import Embed, File
from decimal import Decimal, ROUND_HALF_UP, getcontext
import utils.misc as rpgtools
import discord

from discord.enums import ButtonStyle
import random as randomm
from discord.ext import commands, tasks
from discord.ui.button import Button
from discord.interactions import Interaction
from discord.ui import Button, View

from classes.classes import Raider
from classes.classes import from_string as class_from_string
from classes.converters import IntGreaterThan
from cogs.shard_communication import user_on_cooldown as user_cooldown
from utils import random
from utils.checks import AlreadyRaiding, has_char, is_gm, is_god
from utils.i18n import _, locale_doc
from utils.joins import JoinView

class ElysiaTrials(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.raid_active = False
        ids_section = getattr(self.bot.config, "ids", None)
        trial_ids = getattr(ids_section, "elysiatrials", {}) if ids_section else {}
        if not isinstance(trial_ids, dict):
            trial_ids = {}
        self.channel_ids = trial_ids.get("channel_ids", [])
        self.ping_role_id = trial_ids.get("ping_role_id")
        if not isinstance(self.channel_ids, list):
            self.channel_ids = []

    async def set_raid_timer(self):
        self.raid_active = True

    async def clear_raid_timer(self):
        self.raid_active = False

    @is_god()
    @commands.command(hidden=True, brief=_("Starts Elysia's trial"))
    async def goodspawn(self, ctx):
        """[Elysia only] Starts a Trial."""
        if not self.channel_ids or not self.ping_role_id:
            await ctx.send("Elysia trials channels/role are not configured.")
            return
        await self.set_raid_timer()

        try:
            view = JoinView(
                Button(style=ButtonStyle.primary, label="Join the trial!"),
                message=_("You joined the trial."),
                timeout=60 * 15,
            )

            channels = [self.bot.get_channel(channel_id) for channel_id in self.channel_ids]

            channel1 = self.bot.get_channel(self.channel_ids[0])
            role_id1 = self.ping_role_id

            if channel1:
                role1 = ctx.guild.get_role(role_id1)
                if role1:
                    await channel1.send(content=f"{role1.mention}", allowed_mentions=discord.AllowedMentions(roles=True))

            # Message content, organized for better formatting
            message_intro = """
            In Athena's grace, embrace the light,
            Seek trials that soothe, heal the blight.
            With kindness as your guiding star,
            Illuminate souls from near and far.
            """

            message_trial = """
            **__Champions of compassion, take your stand.__**
            Trial Begins in 15 minutes
            """

            message_note = """
            **Only followers of Elysia may join.**
            """

            # Create the embed with structured fields
            embed = discord.Embed(
                title="Champions of Compassion",
                color=discord.Color.blue()
            )
            embed.add_field(name="Athena's Blessing", value=message_intro, inline=False)
            embed.add_field(name="Trial Information", value=message_trial, inline=False)
            embed.add_field(name="Notice", value=message_note, inline=False)
            embed.set_footer(text="Prepare your souls for the trials to come.")
            embed.timestamp = discord.utils.utcnow()

            # Attach the file (image)
            file = discord.File("assets/other/lyx.webp", filename="lyx.webp")
            embed.set_image(url="attachment://lyx.webp")

            # Updated helper function to send to both channels and handle file closing issue
            async def send_to_channels(embed=None, content=None, view=None, file_path=None):
                """Helper function to send a message to all channels."""
                for channel in channels:
                    if channel is not None:  # Ensure the channel is valid
                        try:
                            if file_path:
                                file = discord.File(file_path, filename="lyx.webp")
                                await channel.send(embed=embed, content=content, view=view, file=file)
                            else:
                                await channel.send(embed=embed, content=content, view=view)
                        except Exception as e:
                            await ctx.send(f"Failed to send message to {channel.name}: {str(e)}")
                    else:
                        await ctx.send("One of the channels could not be found.")

            # Call this function with file_path
            await send_to_channels(embed=embed, content=None, view=view, file_path="assets/other/lyx.webp")

            # Sending the embed with the file to the channels

            if not self.bot.config.bot.is_beta:
                await asyncio.sleep(300)
                await send_to_channels(content="**Elysia and her Ouroboros will be visible in 10 minutes**")
                await asyncio.sleep(300)
                await send_to_channels(content="**Elysia and her Ouroboros will be visible in 5 minutes**")
                await asyncio.sleep(180)
                await send_to_channels(content="**Elysia and her Ouroboros will be visible in 2 minutes**")
                await asyncio.sleep(60)
                await send_to_channels(content="**Elysia and her Ouroboros will be visible in 1 minute**")
                await asyncio.sleep(30)
                await send_to_channels(content="**Elysia and her Ouroboros will be visible in 30 seconds**")
                await asyncio.sleep(20)
                await send_to_channels(content="**Elysia and her Ouroboros will be visible in 10 seconds**")
            else:
                await asyncio.sleep(300)
                await send_to_channels(content="**Elysia's trial will commence in 10 minutes**")
                await asyncio.sleep(300)
                await send_to_channels(content="**Elysia's trial will commence in 5 minutes**")
                await asyncio.sleep(180)
                await send_to_channels(content="**Elysia's trial will commence in 2 minutes**")
                await asyncio.sleep(60)
                await send_to_channels(content="**Elysia's trial will commence in 1 minute**")
                await asyncio.sleep(30)
                await send_to_channels(content="**Elysia's trial will commence in 30 seconds**")
                await asyncio.sleep(20)
                await send_to_channels(content="**Elysia's trial will commence in 10 seconds**")

            view.stop()

            await send_to_channels(content="**Elysia's trial will commence! Fetch participant data... Hang on!**")

            async with self.bot.pool.acquire() as conn:
                raid = []
                HowMany = 0
                for u in view.joined:
                    if (
                            not (
                                    profile := await conn.fetchrow(
                                        'SELECT * FROM profile WHERE "user"=$1;', u.id
                                    )
                            )
                            or profile["god"] != "Elysia"
                    ):
                        continue
                    HowMany = HowMany + 1
                    raid.append(u)

            await send_to_channels(content="**Done getting data!**")
            await send_to_channels(content=f"**{HowMany} followers joined!**")

            while len(raid) > 1:
                time = random.choice(["day", "night"])
                if time == "day":
                    em = discord.Embed(
                        title="It turns day",
                        description="As the sun's golden rays grace the horizon, a sense of renewal spreads across the "
                                    "land. The world awakens from its slumber, bathed in warmth and hope.",
                        colour=0xFFB900,
                    )
                else:
                    em = discord.Embed(
                        title="It turns night",
                        description="The world embraces the embrace of the night, shrouded in mystery and quietude. The "
                                    "stars twinkle like distant promises, and the nocturnal creatures begin their "
                                    "whispered symphony.",
                        colour=0xFFB900,
                    )
                em.set_thumbnail(url=f"http://vivi.1.free.fr/lyx.png")
                await send_to_channels(embed=em)
                await asyncio.sleep(5)
                target = random.choice(raid)
                if time == "day":
                    event = random.choice(
                        [
                            {
                                "text": "Extend a Healing Hand",
                                "win": 80,
                                "win_text": "Your compassionate efforts have brought healing and solace. Elysia smiles "
                                            "upon you.",
                                "lose_text": "Despite your intentions, your healing touch falters. Elysia's grace eludes "
                                             "you.",
                            },
                            {
                                "text": "Ease Emotional Burdens",
                                "win": 50,
                                "win_text": "Through your empathetic words, you mend fractured souls. Elysia's favor "
                                            "shines on you.",
                                "lose_text": "Your words fall short, unable to mend the hearts before you. Elysia's "
                                             "blessing slips away.",
                            },
                            {
                                "text": "Kindness in Action",
                                "win": 60,
                                "win_text": "Your selfless actions spread ripples of kindness. Elysia's radiant gaze "
                                            "embraces you.",
                                "lose_text": "Your attempts at kindness don't fully resonate. Elysia's warmth remains "
                                             "distant.",
                            },
                        ]
                    )
                else:
                    event = random.choice(
                        [
                            {
                                "text": "Guiding Light of Compassion",
                                "win": 30,
                                "win_text": "Amidst the tranquil night, your compassion brings light to dark corners. "
                                            "Elysia's approval graces you.",
                                "lose_text": "Your efforts to bring solace in the night are met with challenges. Elysia's "
                                             "light evades you.",
                            },
                            {
                                "text": "Healing Moon's Embrace",
                                "win": 45,
                                "win_text": "Under the moon's serenity, your healing touch is magnified. Elysia's "
                                            "presence envelops you.",
                                "lose_text": "Your attempts to heal are hindered by unseen forces. Elysia's touch remains "
                                             "elusive.",
                            },
                            {
                                "text": "Celestial Blessing of Serenity",
                                "win": 20,
                                "win_text": "As the stars align in your favor, Elysia's serene blessings envelop you. A "
                                            "tranquil aura emanates from your being, soothing all around.",
                                "lose_text": "Despite your efforts to channel the cosmos, Elysia's tranquility eludes "
                                             "you, leaving only fleeting traces of its presence.",
                            },
                            {
                                "text": "Stellar Harmonies of Renewal",
                                "win": 20,
                                "win_text": "In harmony with the celestial melodies, your actions resonate with Elysia's "
                                            "essence. The stars themselves seem to sing your praises, infusing the air "
                                            "with renewal.",
                                "lose_text": "The cosmic harmonies remain elusive, and your attempts to align with "
                                             "Elysia's melody falter, leaving a sense of missed opportunity in the "
                                             "night's chorus.",
                            }
                        ]
                    )
                does_win = event["win"] >= random.randint(1, 100)
                if does_win:
                    text = event["win_text"]
                else:
                    text = event["lose_text"]
                    raid.remove(target)
                em = discord.Embed(
                    title=event["text"],
                    description=text,
                    colour=0xFFB900,
                )
                em.set_author(name=f"{target}", icon_url=target.display_avatar.url)
                em.set_footer(text=f"{len(raid)} followers remain")
                em.set_thumbnail(url=f"http://vivi.1.free.fr/lyx.png")
                await send_to_channels(embed=em)
                await asyncio.sleep(5)

            winner = raid[0]
            async with self.bot.pool.acquire() as conn:
                # Fetch the luck value for the specified user (winner)
                luck_query = await conn.fetchval(
                    'SELECT luck FROM profile WHERE "user" = $1;',
                    winner.id,
                )

            # Convert luck_query to float
            luck_query_float = float(luck_query)

            # Define gods with their boundaries
            gods = {
                "Elysia": {"boundary_low": 0.9, "boundary_high": 1.1},
                "Sepulchure": {"boundary_low": 0.75, "boundary_high": 1.5},
                "Drakath": {"boundary_low": 0.3, "boundary_high": 2.0},
            }

            # Replace 'selected_god' with the actual selected god name (e.g., "Elysia")
            selected_god = "Elysia"  # Example, replace dynamically
            god_data = gods.get(selected_god)

            if not god_data:
                raise ValueError(f"God {selected_god} not found.")

            boundary_low = god_data["boundary_low"]
            boundary_high = god_data["boundary_high"]

            # Normalize the user's luck value
            normalized_luck = (luck_query_float - boundary_low) / (boundary_high - boundary_low)
            normalized_luck = max(0.0, min(1.0, normalized_luck))  # Clamp between 0.0 and 1.0

            # Scale the divine weight
            weightdivine = 0.20 + (0.20 * normalized_luck)  # Example scaling factor
            rounded_weightdivine = round(weightdivine, 3)

            # Define weights for crate selection
            options = ['legendary', 'fortune', 'divine']
            weights = [0.40, 0.40, rounded_weightdivine]

            # Select a crate based on weights
            crate = randomm.choices(options, weights=weights)[0]

            await send_to_channels(
                content=f"In the divine radiance of Elysia, {winner.mention} ascends to the cosmic realm. Guided by the "
                        f"goddess's embrace, they uncover a celestial treasure—an enigmatic, {crate} crate adorned with "
                        f"stardust among the constellations."
            )

            # Update the profile and clear the raid timer
            async with self.bot.pool.acquire() as conn:
                await conn.execute(
                    f'UPDATE profile SET "crates_{crate}" = "crates_{crate}" + 1 WHERE "user" = $1;',
                    winner.id,
                )

            await self.clear_raid_timer()
        except Exception as e:
            import traceback
            error_message = f"Error occurred: {e}\n"
            error_message += traceback.format_exc()
            await ctx.send(error_message)
            print(error_message)

async def setup(bot):
    await bot.add_cog(ElysiaTrials(bot))

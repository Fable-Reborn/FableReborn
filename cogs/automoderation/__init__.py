import discord
from discord.ext import commands, tasks
from discord.ui import View, Button
import aiohttp
import re
import asyncio
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('AutoModeration')

class AutoModeration(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.guild_id = 1402911850802315336  # Target Guild ID
        self.admin_channel_id = 1406295336313557124

        # ID of the user to receive DM logs
        self.log_user_id = 171645746993561600

        # URL of the NSFW word list (raw content)
        self.nsfw_word_list_url = "https://gist.githubusercontent.com/ryanlewis/a37739d710ccdb4b406d/raw/0fbd315eb2900bb736609ea894b9bde8217b991a/google_twunter_lol"

        self.nsfw_words = set()
        self.nsfw_pattern = None

        # Initialize the word list using asyncio.create_task
        asyncio.create_task(self.fetch_nsfw_words())

        # Schedule periodic updates (e.g., every 24 hours)
        self.update_word_list.start()

    def cog_unload(self):
        self.update_word_list.cancel()

    async def send_log_dm(self, message: str):
        """Send a DM to the designated log user."""
        user = self.bot.get_user(self.log_user_id)
        if user is None:
            # Attempt to fetch the user if not cached
            try:
                user = await self.bot.fetch_user(self.log_user_id)
            except discord.NotFound:
                logger.error(f"Log user with ID {self.log_user_id} not found.")
                return
            except discord.HTTPException as e:
                logger.error(f"HTTP exception while fetching log user: {e}")
                return

        try:
            await user.send(message)
            logger.info(f"Sent log DM: {message}")
        except discord.Forbidden:
            logger.error(f"Cannot send DM to user ID {self.log_user_id}. They might have DMs disabled.")
        except Exception as e:
            logger.error(f"Unexpected error when sending DM to log user: {e}")

    @tasks.loop(hours=24)
    async def update_word_list(self):
        """Periodically update the NSFW word list."""
        await self.fetch_nsfw_words()

    async def fetch_nsfw_words(self):
        """Fetch NSFW words from the online GitHub repository."""
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(self.nsfw_word_list_url) as response:
                    if response.status == 200:
                        data = await response.text()
                        # Split the data by whitespace (spaces, tabs, newlines)
                        words = data.split()
                        # Update the word set, excluding single-letter words
                        self.nsfw_words = set(
                            word.strip().lower() for word in words
                            if word.strip() and len(word.strip()) >= 2
                        )
                        # Recompile the regex pattern
                        if self.nsfw_words:
                            pattern = r'\b(' + '|'.join(re.escape(word) for word in self.nsfw_words) + r')\b'
                            self.nsfw_pattern = re.compile(pattern, re.IGNORECASE)
                            #await self.send_log_dm("✅ NSFW word list successfully updated.")
                            logger.info("NSFW word list successfully updated.")
                        else:
                            self.nsfw_pattern = None
                            #await self.send_log_dm("⚠️ NSFW word list is empty after fetching.")
                            logger.warning("NSFW word list is empty after fetching.")
                    else:
                        #await self.send_log_dm(f"❌ Failed to fetch NSFW word list. HTTP Status: {response.status}")
                        logger.error(f"Failed to fetch NSFW word list. HTTP Status: {response.status}")
            except Exception as e:
                #await self.send_log_dm(f"❌ Exception occurred while fetching NSFW word list: {e}")
                logger.error(f"Exception occurred while fetching NSFW word list: {e}")

    @commands.Cog.listener()
    async def on_message(self, message):
        # Ensure the message is in the target guild
        if message.guild is None or message.guild.id != self.guild_id:
            return

        # Ignore messages sent by bots
        if message.author.bot:
            return

        # Ignore messages prefixed with '$'
        if message.content.startswith('$'):
            return

        # Check for NSFW content
        if self.is_nsfw(message.content):
            await self.handle_nsfw_message(message)

    def is_nsfw(self, content):
        if not self.nsfw_pattern:
            return False
        return bool(self.nsfw_pattern.search(content))

    async def handle_nsfw_message(self, message):
        admin_channel = self.bot.get_channel(self.admin_channel_id)
        if not admin_channel:
            #await self.send_log_dm(f"❌ Admin channel with ID {self.admin_channel_id} not found.")
            logger.error(f"Admin channel with ID {self.admin_channel_id} not found.")
            return

        # Create an embed with details
        embed = discord.Embed(
            title="🚫 NSFW Content Detected",
            description="A message containing potentially inappropriate content was detected.",
            color=discord.Color.red(),
            timestamp=discord.utils.utcnow()
        )
        embed.add_field(name="User", value=f"{message.author} (ID: {message.author.id})", inline=False)
        embed.add_field(name="Channel", value=f"{message.channel.mention} (ID: {message.channel.id})", inline=False)
        embed.add_field(name="Message", value=message.content, inline=False)
        embed.add_field(name="Jump to Message", value=f"[Click Here]({message.jump_url})", inline=False)
        if message.author.avatar:
            embed.set_thumbnail(url=message.author.avatar.url)
        else:
            embed.set_thumbnail(url=message.author.default_avatar.url)

        # Additional Details
        embed.add_field(name="Message ID", value=message.id, inline=True)
        embed.add_field(name="Timestamp", value=message.created_at.strftime("%Y-%m-%d %H:%M:%S"), inline=True)

        # Create a View with Buttons (Non-Persistent)
        view = ModerationView(
            bot=self.bot,
            message=message,
            admin_channel=admin_channel
        )

        # Send the embed with the interactive buttons to the admin channel
        try:
            await admin_channel.send(embed=embed, view=view)
            #await self.send_log_dm(f"✅ NSFW message detected and reported: {message.id}")
            logger.info(f"NSFW message detected and reported: {message.id}")
        except discord.Forbidden:
            #await self.send_log_dm(f"❌ Permission denied when trying to send embed to admin channel ID {self.admin_channel_id}.")
            logger.error(f"Permission denied when trying to send embed to admin channel ID {self.admin_channel_id}.")
        except Exception as e:
            #await self.send_log_dm(f"❌ Unexpected error when sending embed to admin channel: {e}")
            logger.error(f"Unexpected error when sending embed to admin channel: {e}")

    @commands.Cog.listener()
    async def on_ready(self):
        #await self.send_log_dm(f"✅ AutoModeration cog loaded and monitoring guild ID {self.guild_id}.")
        logger.info(f"AutoModeration cog loaded and monitoring guild ID {self.guild_id}.")

class ModerationView(discord.ui.View):
    def __init__(self, bot, message: discord.Message, admin_channel: discord.abc.GuildChannel):
        super().__init__(timeout=None)  # Removed timeout=None for non-persistent View
        self.bot = bot
        self.message = message
        self.admin_channel = admin_channel
        self.user = message.author

        # ID of the user to receive DM logs
        self.log_user_id = 171645746993561600



    @discord.ui.button(label="Warn", style=discord.ButtonStyle.primary, custom_id="automod_warn")
    async def warn_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.warn_user(interaction)

    @discord.ui.button(label="Kick", style=discord.ButtonStyle.danger, custom_id="automod_kick")
    async def kick_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.kick_user(interaction)

    @discord.ui.button(label="Ban", style=discord.ButtonStyle.danger, custom_id="automod_ban")
    async def ban_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.ban_user(interaction)

    @discord.ui.button(label="Delete Message", style=discord.ButtonStyle.secondary, custom_id="automod_delete")
    async def delete_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            await self.message.delete()
            await interaction.response.send_message(
                "🗑️ Offending message has been deleted.", ephemeral=True
            )
        except discord.Forbidden:
            await interaction.response.send_message(
                "⚠️ I do not have permission to delete this message.", ephemeral=True
            )
        except Exception as e:
            await interaction.response.send_message(
                "⚠️ An error occurred while trying to delete the message.", ephemeral=True
            )

    @discord.ui.button(label="Approve", style=discord.ButtonStyle.success, custom_id="automod_approve")
    async def approve_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.approve_moderation(interaction)

    async def warn_user(self, interaction: discord.Interaction):
        warning_message = (
            f"⚠️ You have been warned for sending a message that violates the server's NSFW policies.\n"
            f"**Message Link:** [Click Here]({self.message.jump_url})"
        )
        try:
            await self.user.send(warning_message)
            await interaction.response.send_message(
                f"⚠️ Warned {self.user.mention}.", ephemeral=True
            )
        except discord.Forbidden:
            await interaction.response.send_message(
                f"⚠️ Could not send a DM to {self.user.mention}. They might have DMs disabled.",
                ephemeral=True
            )
        except Exception as e:
            await interaction.response.send_message(
                "⚠️ An unexpected error occurred while trying to warn the user.",
                ephemeral=True
            )

    async def kick_user(self, interaction: discord.Interaction):
        guild = interaction.guild
        try:
            await guild.kick(self.user, reason=f"NSFW content: Message ID {self.message.id}")
            await interaction.response.send_message(
                f"🔨 Kicked {self.user.mention} from the server.", ephemeral=True
            )
        except discord.Forbidden:
            await interaction.response.send_message(
                "⚠️ I do not have permission to kick this user.", ephemeral=True
            )
        except Exception as e:
            await interaction.response.send_message(
                "⚠️ An error occurred while trying to kick the user.", ephemeral=True
            )

    async def ban_user(self, interaction: discord.Interaction):
        guild = interaction.guild
        try:
            await guild.ban(self.user, reason=f"NSFW content: Message ID {self.message.id}")
            await interaction.response.send_message(
                f"🔨 Banned {self.user.mention} from the server.", ephemeral=True
            )
        except discord.Forbidden:
            await interaction.response.send_message(
                "⚠️ I do not have permission to ban this user.", ephemeral=True
            )
        except Exception as e:
            await interaction.response.send_message(
                "⚠️ An error occurred while trying to ban the user.", ephemeral=True
            )

    async def delete_offending_message(self, interaction: discord.Interaction):
        try:
            await self.message.delete()
            await interaction.response.send_message(
                "🗑️ Offending message has been deleted.", ephemeral=True
            )
        except discord.Forbidden:
            await interaction.response.send_message(
                "⚠️ I do not have permission to delete this message.", ephemeral=True
            )
        except Exception as e:
            await interaction.response.send_message(
                "⚠️ An error occurred while trying to delete the message.", ephemeral=True
            )

    async def approve_moderation(self, interaction: discord.Interaction):
        try:
            await interaction.response.send_message(
                "✅ Moderation approved and embed deleted.", ephemeral=True
            )
        except Exception as e:
            logger.error(f"Failed to send approval response: {e}")
            return  # Early exit to prevent further issues

        # Start background tasks
        asyncio.create_task(interaction.message.delete())


# Setup function to add the cog to the bot
async def setup(bot):
    await bot.add_cog(AutoModeration(bot))
    logger.info("AutoModeration cog has been added to the bot.")

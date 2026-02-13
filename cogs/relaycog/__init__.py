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
import aiohttp


class RelayCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        ids_section = getattr(self.bot.config, "ids", None)
        relay_ids = getattr(ids_section, "relaycog", {}) if ids_section else {}
        if not isinstance(relay_ids, dict):
            relay_ids = {}
        self.source_channel_id = relay_ids.get("source_channel_id")
        self.error_channel_id = relay_ids.get("error_channel_id")
        self.WEBHOOK_URL = ''
        self.messages = []  # List to store messages

    @commands.Cog.listener()
    async def on_message(self, message):
        if self.source_channel_id and message.channel.id == self.source_channel_id:

            # Ignoring specific phrases
            if "You joined the raid" in message.content or "You already joined" in message.content:
                return

            if "You joined the waid" in message.content or "You already joined" in message.content:
                return

            # Avatar handling
            if message.author.avatar:
                avatar_url = message.author.avatar  # Ensure to get the URL of the avatar
            else:
                default_avatar_number = int(message.author.discriminator) % 5
                avatar_url = f"https://cdn.discordapp.com/embed/avatars/{default_avatar_number}.png"

            # Check for embeds
            embeds = message.embeds

            async with aiohttp.ClientSession() as session:
                try:
                    webhook = discord.Webhook.from_url(self.WEBHOOK_URL, session=session)
                    await webhook.send(
                        content=message.content,
                        username=message.author.display_name,
                        avatar_url=avatar_url,
                        embeds=embeds  # Pass the list of embeds to webhook from the original message
                    )
                except Exception as e:
                    error_channel = (
                        self.bot.get_channel(self.error_channel_id)
                        if self.error_channel_id
                        else None
                    )
                    if error_channel:
                        await error_channel.send(f"Failed to send message: {e}")


async def setup(bot):
    await bot.add_cog(RelayCog(bot))

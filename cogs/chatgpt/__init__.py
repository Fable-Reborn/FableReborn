import discord
from discord.ext import commands
import requests


class ChatGPTCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot



async def setup(bot):
    await bot.add_cog(ChatGPTCog(bot))

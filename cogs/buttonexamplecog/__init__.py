import discord
from discord.ext import commands

class PersistentButtonView(discord.ui.View):
    def __init__(self, bot):
        super().__init__(timeout=None)  # Persistent views must have `timeout=None`
        self.bot = bot

    @discord.ui.button(label="Persistent Button", style=discord.ButtonStyle.primary, custom_id="persistent_button")
    async def persistent_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("You clicked the persistent button!", ephemeral=True)

class PersistentButtonExampleCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # Add the persistent view when the bot starts
        self.bot.add_view(PersistentButtonView(bot))

    @commands.command(name="persistent_button_example")
    async def persistent_button_example(self, ctx):
        """Command to display a persistent button."""
        await ctx.send("Here is your persistent button!", view=PersistentButtonView(self.bot))

# Setup the cog
async def setup(bot):
    await bot.add_cog(PersistentButtonExampleCog(bot))

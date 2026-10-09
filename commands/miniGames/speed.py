import discord
from discord import app_commands
from discord.ext import commands

class Speed(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="speed", description="Check your typing speed.")
    async def speed(self, interaction: discord.Interaction):
        await interaction.response.send_message("Type as fast as you can!")

import discord
from discord.ext import commands

class PublicEchoCommand(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @discord.app_commands.command(name="say", description="Der Bot sendet eine öffentliche Nachricht.")
    async def say(self, interaction: discord.Interaction, message: str):
        
        await interaction.channel.send(content=message)

        # Beendet die Interaktion, indem wir eine leere Antwort senden
        await interaction.response.send_message(content=" die nachricht wurde gesendet! ", ephemeral=True)  

async def setup(bot):
    await bot.add_cog(PublicEchoCommand(bot))

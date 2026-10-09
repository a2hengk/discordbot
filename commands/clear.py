import discord
from discord.ext import commands

class ClearCommand(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @discord.app_commands.command(name="clear", description="Löscht eine bestimmte Anzahl an Nachrichten.")
    @discord.app_commands.checks.has_permissions(manage_messages=True)
    async def clear(self, interaction: discord.Interaction, amount: int):
        # Überprüfen, ob die Anzahl im erlaubten Bereich liegt
        if amount < 1:
            await interaction.response.send_message("Bitte gib eine Zahl größer als 0 ein.", ephemeral=True)
            return
        elif amount > 100:
            await interaction.response.send_message("Du kannst maximal 100 Nachrichten auf einmal löschen.", ephemeral=True)
            return

        # Setze die Interaktion auf "wartend"
        await interaction.response.defer(thinking=True)

        # Lösche die Nachrichten
        deleted = await interaction.channel.purge(limit=amount)
        
async def setup(bot):
    await bot.add_cog(ClearCommand(bot))

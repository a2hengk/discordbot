import discord
from discord import app_commands
from discord.ext import commands
import random

class Zahlenraten(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.active_games = {}  # user_id -> (number_to_guess, attempts)

    @app_commands.command(name="zahlenraten", description="Starte ein Zahlenratespiel")
    async def zahlenraten(self, interaction: discord.Interaction):
        number = random.randint(1, 100)
        self.active_games[interaction.user.id] = (number, 0)
        await interaction.response.send_message(
            "Ich habe mir eine Zahl zwischen 1 und 100 ausgedacht. Rate sie!"
        )

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # Ignoriere Nachrichten von Bots
        if message.author.bot:
            return

        # Prüfe, ob der User ein aktives Spiel hat
        if message.author.id not in self.active_games:
            return

        # Versuche, die Nachricht als Zahl zu interpretieren
        try:
            guess = int(message.content)
        except ValueError:
            return  # ignorieren, wenn kein Integer
        
        # Spiel beenden, wenn "exit" eingegeben wird
        content = message.content.strip().lower()
        if content == "exit":
            del self.active_games[message.author.id]
            await message.channel.send(f"{message.author.mention} Das Spiel wurde beendet.")
            return
        
        number_to_guess, attempts = self.active_games[message.author.id]
        attempts += 1
        self.active_games[message.author.id] = (number_to_guess, attempts)

        if guess < number_to_guess:
            await message.channel.send(f"{message.author.mention} Zu niedrig! Versuch es nochmal.")
        elif guess > number_to_guess:
            await message.channel.send(f"{message.author.mention} Zu hoch! Versuch es nochmal.")
        else:
            await message.channel.send(
                f"{message.author.mention} 🎉 Glückwunsch! Du hast die Zahl **{number_to_guess}** "
                f"in **{attempts}** Versuchen erraten!"
            )
            del self.active_games[message.author.id]


async def setup(bot):
    await bot.add_cog(Zahlenraten(bot))

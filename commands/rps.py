import random
import discord
from discord import app_commands
from discord.ext import commands

class RPS(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="rps", description="Spiele Schere, Stein, Papier gegen den Bot")
    @app_commands.describe(choice="Wähle Schere, Stein oder Papier")
    @app_commands.choices(choice=[
        app_commands.Choice(name="Schere", value="Schere"),
        app_commands.Choice(name="Stein", value="Stein"),
        app_commands.Choice(name="Papier", value="Papier"),
    ])
    async def rps(self, interaction: discord.Interaction, choice: app_commands.Choice[str]):
        user_choice = choice.value
        choices = ["Schere", "Stein", "Papier"]
        bot_choice = random.choice(choices)

        if user_choice == bot_choice:
            result = "Unentschieden, spielt doch noch eine Runde :D"
        elif (
            (user_choice == "Schere" and bot_choice == "Stein") or
            (user_choice == "Stein" and bot_choice == "Papier") or
            (user_choice == "Papier" and bot_choice == "Schere")
        ):
            result = "AI gewinnt."
        else:
            result = "Du gewinnst."

        embed = discord.Embed(
            title="Ergebnis",
            description=f"{result}\nDu hast **{user_choice}** gewählt und der Bot hat **{bot_choice}** gewählt.",
            color=0x0099ff
        )
        embed.timestamp = discord.utils.utcnow()

        await interaction.response.send_message(embed=embed)

async def setup(bot: commands.Bot):
    await bot.add_cog(RPS(bot))

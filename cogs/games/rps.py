from __future__ import annotations

import random

import discord
from discord import app_commands
from discord.ext import commands

from core.bot import LunasBot

# Was schlägt was
BEATS = {"Schere": "Papier", "Stein": "Schere", "Papier": "Stein"}
EMOJI = {"Schere": "✂️", "Stein": "🪨", "Papier": "📄"}


class RPS(commands.Cog):
    def __init__(self, bot: LunasBot):
        self.bot = bot

    @app_commands.command(name="rps", description="Schere, Stein, Papier gegen den Bot")
    @app_commands.describe(wahl="Schere, Stein oder Papier")
    @app_commands.choices(wahl=[app_commands.Choice(name=f"{EMOJI[c]} {c}", value=c) for c in BEATS])
    async def rps(self, interaction: discord.Interaction, wahl: app_commands.Choice[str]):
        user, bot = wahl.value, random.choice(list(BEATS))

        if user == bot:
            result, color = "Unentschieden – noch eine Runde? :D", discord.Color.light_grey()
        elif BEATS[user] == bot:
            result, color = "Du gewinnst! 🎉", discord.Color.green()
        else:
            result, color = "Der Bot gewinnt. 😈", discord.Color.red()

        embed = discord.Embed(
            title="Schere, Stein, Papier",
            description=f"**{result}**\nDu: {EMOJI[user]} {user} · Bot: {EMOJI[bot]} {bot}",
            color=color,
            timestamp=discord.utils.utcnow(),
        )
        await interaction.response.send_message(embed=embed)


async def setup(bot: LunasBot) -> None:
    await bot.add_cog(RPS(bot))

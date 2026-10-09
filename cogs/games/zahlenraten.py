from __future__ import annotations

import random
from dataclasses import dataclass

import discord
from discord import app_commands
from discord.ext import commands

from core.bot import LunasBot

LOW, HIGH = 1, 100


@dataclass
class Game:
    number: int
    channel_id: int
    attempts: int = 0


class Zahlenraten(commands.Cog):
    def __init__(self, bot: LunasBot):
        self.bot = bot
        self.games: dict[int, Game] = {}  # user_id -> Game

    @app_commands.command(name="zahlenraten", description=f"Errate eine Zahl zwischen {LOW} und {HIGH}")
    async def zahlenraten(self, interaction: discord.Interaction):
        restarted = interaction.user.id in self.games
        self.games[interaction.user.id] = Game(random.randint(LOW, HIGH), interaction.channel_id)
        hint = " (dein altes Spiel wurde ersetzt)" if restarted else ""
        await interaction.response.send_message(
            f"🎲 Ich denke an eine Zahl zwischen {LOW} und {HIGH}. Schreib deinen Tipp in den Chat!"
            f"\nMit `exit` brichst du ab.{hint}"
        )

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        game = self.games.get(message.author.id)
        if message.author.bot or game is None or message.channel.id != game.channel_id:
            return

        content = message.content.strip().lower()
        # exit muss VOR dem int()-Parsing kommen – vorher war das unerreichbar
        if content == "exit":
            del self.games[message.author.id]
            await message.reply(f"Spiel beendet. Die Zahl war **{game.number}**.", mention_author=False)
            return

        try:
            guess = int(content)
        except ValueError:
            return

        game.attempts += 1
        if guess < game.number:
            await message.reply("⬆️ Zu niedrig!", mention_author=False)
        elif guess > game.number:
            await message.reply("⬇️ Zu hoch!", mention_author=False)
        else:
            del self.games[message.author.id]
            await message.reply(
                f"🎉 Richtig! **{game.number}** in **{game.attempts}** "
                f"{'Versuch' if game.attempts == 1 else 'Versuchen'}.",
                mention_author=False,
            )


async def setup(bot: LunasBot) -> None:
    await bot.add_cog(Zahlenraten(bot))

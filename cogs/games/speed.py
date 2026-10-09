"""Tipp-Speedtest. War vorher nur ein Stub ohne setup() – hat den Bot beim Start gecrasht."""

from __future__ import annotations

import asyncio
import difflib
import random

import discord
from discord import app_commands
from discord.ext import commands

from core.bot import LunasBot

SENTENCES = [
    "Der schnelle braune Fuchs springt über den faulen Hund.",
    "Zwölf Boxkämpfer jagen Viktor quer über den großen Sylter Deich.",
    "Wer zuletzt committet, merged am besten.",
    "Heute ist ein guter Tag, um endlich das README zu schreiben.",
    "Kaffee rein, Code raus, Bugs inklusive.",
]
ZWSP = "​"  # unsichtbares Zeichen gegen Copy-Paste
TIMEOUT = 60


class Speed(commands.Cog):
    def __init__(self, bot: LunasBot):
        self.bot = bot
        self.running: set[int] = set()

    @app_commands.command(name="speed", description="Teste deine Tippgeschwindigkeit.")
    async def speed(self, interaction: discord.Interaction):
        if interaction.user.id in self.running:
            await interaction.response.send_message("Du hast schon einen Test laufen.", ephemeral=True)
            return

        sentence = random.choice(SENTENCES)
        protected = ZWSP.join(sentence)
        self.running.add(interaction.user.id)
        try:
            await interaction.response.send_message(
                f"⌨️ {interaction.user.mention}, tipp so schnell du kannst:\n> {protected}"
            )
            prompt = await interaction.original_response()

            def check(m: discord.Message) -> bool:
                return m.author.id == interaction.user.id and m.channel.id == interaction.channel_id

            try:
                reply = await self.bot.wait_for("message", check=check, timeout=TIMEOUT)
            except asyncio.TimeoutError:
                await interaction.followup.send(f"⏱️ Zeit abgelaufen ({TIMEOUT}s).")
                return

            if ZWSP in reply.content:
                await reply.reply("🚫 Copy-Paste erkannt. Nice try.", mention_author=False)
                return

            # Discord-Zeitstempel statt lokaler Uhr → Latenz zählt nicht gegen dich
            seconds = max((reply.created_at - prompt.created_at).total_seconds(), 0.1)
            wpm = (len(reply.content) / 5) / (seconds / 60)
            accuracy = difflib.SequenceMatcher(a=sentence, b=reply.content.strip()).ratio() * 100

            embed = discord.Embed(title="⌨️ Ergebnis", color=discord.Color.blurple())
            embed.add_field(name="Zeit", value=f"{seconds:.2f}s")
            embed.add_field(name="WPM", value=f"{wpm:.0f}")
            embed.add_field(name="Genauigkeit", value=f"{accuracy:.0f}%")
            await reply.reply(embed=embed, mention_author=False)
        finally:
            self.running.discard(interaction.user.id)


async def setup(bot: LunasBot) -> None:
    await bot.add_cog(Speed(bot))

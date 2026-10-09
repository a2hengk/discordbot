"""Moderations- und Utility-Commands: /clear, /say, /embed."""

from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from core.bot import LunasBot


class Moderation(commands.Cog):
    def __init__(self, bot: LunasBot):
        self.bot = bot

    @app_commands.command(name="clear", description="Löscht die letzten Nachrichten im Kanal.")
    @app_commands.describe(anzahl="Wie viele Nachrichten (1–100)")
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_messages=True)
    @app_commands.checks.bot_has_permissions(manage_messages=True, read_message_history=True)
    async def clear(self, interaction: discord.Interaction, anzahl: app_commands.Range[int, 1, 100]):
        # Ephemeral defern, sonst löscht purge die eigene "denkt nach…"-Antwort mit
        await interaction.response.defer(ephemeral=True, thinking=True)
        deleted = await interaction.channel.purge(limit=anzahl)
        await interaction.followup.send(f"🧹 {len(deleted)} Nachrichten gelöscht.", ephemeral=True)

    @app_commands.command(name="say", description="Der Bot schreibt eine Nachricht in diesen Kanal.")
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_messages=True)
    async def say(self, interaction: discord.Interaction, nachricht: app_commands.Range[str, 1, 2000]):
        await interaction.channel.send(nachricht, allowed_mentions=discord.AllowedMentions.none())
        await interaction.response.send_message("✅ Gesendet.", ephemeral=True)

    @app_commands.command(name="embed", description="Sendet einen Text und/oder ein Bild als Embed.")
    async def embed(
        self,
        interaction: discord.Interaction,
        text: app_commands.Range[str, 1, 4000] | None = None,
        bild: discord.Attachment | None = None,
    ):
        if not text and not bild:
            await interaction.response.send_message("Gib mindestens Text oder ein Bild an.", ephemeral=True)
            return
        if bild and not (bild.content_type or "").startswith("image/"):
            await interaction.response.send_message("Das Attachment ist kein Bild.", ephemeral=True)
            return

        embed = discord.Embed(description=text, color=discord.Color.blue())
        embed.set_author(name=interaction.user.display_name, icon_url=interaction.user.display_avatar.url)
        if not bild:
            await interaction.response.send_message(embed=embed)
            return

        # Neu hochladen statt bild.url verlinken – die URL von Slash-Command-Uploads läuft ab
        await interaction.response.defer()
        file = await bild.to_file()
        embed.set_image(url=f"attachment://{file.filename}")
        await interaction.followup.send(embed=embed, file=file)


async def setup(bot: LunasBot) -> None:
    await bot.add_cog(Moderation(bot))

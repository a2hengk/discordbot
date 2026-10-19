"""Verifizierung: Neue Mitglieder klicken einen Button und lösen eine kleine Rechenaufgabe.

Setup auf dem Server (macht der Bot NICHT automatisch, damit er dir keine Rechte zerschießt):
1. Rolle "Verifiziert" anlegen
2. @everyone darf nur den Verifizierungs-Kanal sehen, alle anderen Kanäle nur "Verifiziert"
3. /verifizierung einrichten kanal:#verify rolle:@Verifiziert

Hält einfache Bots und Raid-Accounts fern – gegen echte Menschen mit bösen Absichten hilft
das natürlich nicht, dafür gibt's Anti-Raid (Kontoalter) und Moderation.
"""

from __future__ import annotations

import random

import discord
from discord import app_commands
from discord.ext import commands

from core.bot import LunasBot
from core.utils import role_problem


class CaptchaModal(discord.ui.Modal):
    def __init__(self, cog: Verification):
        a, b = random.randint(2, 12), random.randint(2, 12)
        super().__init__(title="Kurz checken, ob du ein Mensch bist")
        self.cog = cog
        self.solution = a + b
        self.answer = discord.ui.TextInput(label=f"Was ist {a} + {b}?", placeholder="Zahl eingeben",
                                           max_length=4, required=True)
        self.add_item(self.answer)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if self.answer.value.strip() != str(self.solution):
            await interaction.response.send_message("❌ Leider falsch – klick nochmal auf den Button.", ephemeral=True)
            return
        await self.cog.verify(interaction)


class VerifyView(discord.ui.View):
    def __init__(self, cog: Verification):
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(label="Verifizieren", style=discord.ButtonStyle.success, emoji="✅", custom_id="verify:start")
    async def start(self, interaction: discord.Interaction, _: discord.ui.Button):
        role = self.cog.role(interaction.guild)
        if role is None:
            await interaction.response.send_message("⚠️ Verifizierung ist gerade nicht eingerichtet.", ephemeral=True)
        elif role in interaction.user.roles:
            await interaction.response.send_message("Du bist schon verifiziert. 👍", ephemeral=True)
        else:
            await interaction.response.send_modal(CaptchaModal(self.cog))


@app_commands.guild_only()
@app_commands.default_permissions(manage_guild=True)
class Verification(commands.GroupCog, group_name="verifizierung", group_description="Verifizierung neuer Mitglieder"):
    def __init__(self, bot: LunasBot):
        self.bot = bot

    async def cog_load(self) -> None:
        self.bot.add_view(VerifyView(self))

    def role(self, guild: discord.Guild) -> discord.Role | None:
        role_id = self.bot.storage.get(guild.id, "verify_role")
        return guild.get_role(role_id) if role_id else None

    async def verify(self, interaction: discord.Interaction) -> None:
        role = self.role(interaction.guild)
        if role is None:
            await interaction.response.send_message("⚠️ Verifizierung ist gerade nicht eingerichtet.", ephemeral=True)
            return
        try:
            await interaction.user.add_roles(role, reason="Verifiziert")
        except discord.HTTPException:
            await interaction.response.send_message("⚠️ Ich konnte dir die Rolle nicht geben – sag einem Admin Bescheid.",
                                                    ephemeral=True)
            return
        await interaction.response.send_message("✅ Verifiziert, willkommen! 🎉", ephemeral=True)
        self.bot.dispatch("member_verified", interaction.user)  # → Autorole in roles.py

    @app_commands.command(name="einrichten", description="Verifizierungs-Panel posten und Rolle festlegen.")
    @app_commands.describe(kanal="Kanal, den neue Leute sehen", rolle="Rolle, die man nach dem Verifizieren bekommt")
    async def einrichten(self, interaction: discord.Interaction, kanal: discord.TextChannel, rolle: discord.Role):
        if problem := role_problem(rolle):
            return await interaction.response.send_message(f"⛔ {problem}", ephemeral=True)

        embed = discord.Embed(
            title="👋 Willkommen!",
            description="Klick auf **Verifizieren** und beantworte eine kurze Rechenaufgabe, "
                        "dann siehst du den restlichen Server.",
            color=discord.Color.green(),
        )
        try:
            await kanal.send(embed=embed, view=VerifyView(self))
        except discord.Forbidden:
            return await interaction.response.send_message(f"⛔ Ich darf in {kanal.mention} nicht schreiben.",
                                                           ephemeral=True)
        await self.bot.storage.set(interaction.guild_id, "verify_role", rolle.id)
        await interaction.response.send_message(
            f"✅ Panel in {kanal.mention} gepostet, Rolle: {rolle.mention}.\n"
            f"Denk dran: @everyone sollte nur {kanal.mention} sehen, der Rest nur {rolle.mention}.",
            ephemeral=True,
        )

    @app_commands.command(name="aus", description="Verifizierung abschalten (Panel-Button macht dann nichts mehr).")
    async def aus(self, interaction: discord.Interaction):
        await self.bot.storage.set(interaction.guild_id, "verify_role", None)
        await interaction.response.send_message("✅ Verifizierung aus. Autorole gibt's jetzt direkt beim Join.",
                                                ephemeral=True)


async def setup(bot: LunasBot) -> None:
    await bot.add_cog(Verification(bot))

"""/config – alle Server-Einstellungen an einem Ort, nur für Admins sichtbar."""

from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from core.bot import LunasBot
from core.utils import role_problem


def _channel(guild: discord.Guild, channel_id: int | None) -> str:
    if not channel_id:
        return "—"
    ch = guild.get_channel(channel_id)
    return ch.mention if ch else f"⚠️ gelöscht ({channel_id})"


@app_commands.guild_only()
@app_commands.default_permissions(manage_guild=True)
class Config(commands.GroupCog, group_name="config", group_description="Bot-Einstellungen für diesen Server"):
    def __init__(self, bot: LunasBot):
        self.bot = bot

    @app_commands.command(name="auditlog", description="Kanal für Audit-Logs setzen (leer lassen = aus).")
    async def auditlog(self, interaction: discord.Interaction, kanal: discord.TextChannel | None = None):
        await self.bot.storage.set(interaction.guild_id, "audit_log_channel", kanal.id if kanal else None)
        text = f"✅ Audit-Log geht jetzt nach {kanal.mention}." if kanal else "✅ Audit-Log deaktiviert."
        await interaction.response.send_message(text, ephemeral=True)

    @app_commands.command(name="willkommen", description="Kanal für Willkommensnachrichten setzen (leer = aus).")
    async def willkommen(self, interaction: discord.Interaction, kanal: discord.TextChannel | None = None):
        await self.bot.storage.set(interaction.guild_id, "welcome_channel", kanal.id if kanal else None)
        text = f"✅ Willkommensnachrichten gehen nach {kanal.mention}." if kanal else "✅ Willkommensnachrichten aus."
        await interaction.response.send_message(text, ephemeral=True)

    @app_commands.command(name="modlog", description="Kanal für Mod-Aktionen (Warns, Bans, Automod…). Leer = Audit-Log-Kanal.")
    async def modlog(self, interaction: discord.Interaction, kanal: discord.TextChannel | None = None):
        await self.bot.storage.set(interaction.guild_id, "mod_log_channel", kanal.id if kanal else None)
        text = f"✅ Mod-Log geht jetzt nach {kanal.mention}." if kanal else "✅ Mod-Log nutzt jetzt den Audit-Log-Kanal."
        await interaction.response.send_message(text, ephemeral=True)

    @app_commands.command(name="autorole", description="Rolle, die neue Mitglieder automatisch bekommen (leer = aus).")
    async def autorole(self, interaction: discord.Interaction, rolle: discord.Role | None = None):
        if rolle and (problem := role_problem(rolle)):
            return await interaction.response.send_message(f"⛔ {problem}", ephemeral=True)
        await self.bot.storage.set(interaction.guild_id, "autorole", rolle.id if rolle else None)
        text = f"✅ Neue Mitglieder bekommen {rolle.mention}." if rolle else "✅ Autorole aus."
        if rolle and self.bot.storage.get(interaction.guild_id, "verify_role"):
            text += " (Weil Verifizierung an ist: erst nach dem Verifizieren.)"
        await interaction.response.send_message(text, ephemeral=True)

    @app_commands.command(name="verwarnungen", description="Ab wie vielen Verwarnungen es automatisch Timeout gibt.")
    @app_commands.describe(schwelle="Alle X Verwarnungen → Timeout (0 = aus)", minuten="Timeout-Dauer in Minuten")
    async def verwarnungen(self, interaction: discord.Interaction, schwelle: app_commands.Range[int, 0, 20],
                           minuten: app_commands.Range[int, 1, 40320] = 60):
        await self.bot.storage.set(interaction.guild_id, "warn_escalation", {"threshold": schwelle, "minutes": minuten})
        text = (f"✅ Alle {schwelle} Verwarnungen gibt's {minuten} Minuten Timeout." if schwelle
                else "✅ Automatischer Timeout bei Verwarnungen aus.")
        await interaction.response.send_message(text, ephemeral=True)

    @app_commands.command(name="tickets", description="Ticket-System konfigurieren.")
    @app_commands.describe(
        archiv="Hier landen die Verläufe geschlossener Tickets",
        supportrolle="Diese Rolle sieht alle Tickets und darf sie beanspruchen",
        kategorie="In dieser Kategorie werden Ticket-Kanäle erstellt",
    )
    async def tickets(
        self,
        interaction: discord.Interaction,
        archiv: discord.TextChannel | None = None,
        supportrolle: discord.Role | None = None,
        kategorie: discord.CategoryChannel | None = None,
    ):
        storage, gid = self.bot.storage, interaction.guild_id
        if archiv:
            await storage.set(gid, "ticket_archive_channel", archiv.id)
        if supportrolle:
            await storage.set(gid, "ticket_support_role", supportrolle.id)
        if kategorie:
            await storage.set(gid, "ticket_category", kategorie.id)
        await interaction.response.send_message(
            "✅ Ticket-Einstellungen gespeichert. Panel posten mit `/ticketpanel`.", ephemeral=True
        )

    @app_commands.command(name="anzeigen", description="Aktuelle Einstellungen anzeigen.")
    async def anzeigen(self, interaction: discord.Interaction):
        guild, s = interaction.guild, self.bot.storage
        role_id = s.get(guild.id, "ticket_support_role")
        role = guild.get_role(role_id) if role_id else None
        category_id = s.get(guild.id, "ticket_category")

        embed = discord.Embed(title="⚙️ Einstellungen", color=discord.Color.blurple())
        embed.add_field(name="Audit-Log", value=_channel(guild, s.get(guild.id, "audit_log_channel")))
        embed.add_field(name="Willkommen", value=_channel(guild, s.get(guild.id, "welcome_channel")))
        embed.add_field(name="Ticket-Archiv", value=_channel(guild, s.get(guild.id, "ticket_archive_channel")))
        embed.add_field(name="Support-Rolle", value=role.mention if role else "— (nur Admins)")
        embed.add_field(name="Ticket-Kategorie", value=_channel(guild, category_id))
        embed.add_field(name="Offene Tickets", value=str(len(s.get(guild.id, "tickets", {}))))
        embed.add_field(name="Mod-Log", value=_channel(guild, s.get(guild.id, "mod_log_channel")) + " (sonst Audit-Log)")
        autorole = guild.get_role(s.get(guild.id, "autorole") or 0)
        embed.add_field(name="Autorole", value=autorole.mention if autorole else "—")
        verify = guild.get_role(s.get(guild.id, "verify_role") or 0)
        embed.add_field(name="Verifizierung", value=verify.mention if verify else "aus")
        esc = s.get(guild.id, "warn_escalation", {"threshold": 3, "minutes": 60})
        embed.add_field(name="Warn-Eskalation",
                        value=f"alle {esc['threshold']} → {esc['minutes']} min Timeout" if esc["threshold"] else "aus")
        embed.set_footer(text="Mehr: /automod anzeigen · /antiraid status · /levels anzeigen")
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: LunasBot) -> None:
    await bot.add_cog(Config(bot))

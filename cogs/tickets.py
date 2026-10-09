"""Ticket-System mit Panel, Beanspruchen, Schließen und Archiv-Transkript.

Unterschiede zur alten Version:
- Views sind persistent (bot.add_view) → Buttons funktionieren auch nach Neustart.
- Ticket-Zustand (Ersteller, beansprucht von) liegt in settings.json statt im RAM.
- Verlauf wird als .txt-Transkript archiviert statt in Embed-Felder gequetscht
  (die waren auf 25 Felder à 1024 Zeichen begrenzt und sind bei langen Tickets gecrasht).
"""

from __future__ import annotations

import asyncio
import io
import re

import discord
from discord import app_commands
from discord.ext import commands

from core.bot import LunasBot

TICKET_TYPES = {
    "general": ("Allgemeine Anfrage", discord.ButtonStyle.primary, "💬"),
    "tech": ("Technische Unterstützung", discord.ButtonStyle.secondary, "🛠️"),
}


async def _deny(interaction: discord.Interaction, msg: str) -> None:
    await interaction.response.send_message(msg, ephemeral=True)


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9-]+", "-", text.lower()).strip("-")[:40] or "user"


class Tickets(commands.Cog):
    def __init__(self, bot: LunasBot):
        self.bot = bot

    async def cog_load(self) -> None:
        # Persistente Views einmal registrieren – Discord leitet Klicks dann über custom_id hierher
        self.bot.add_view(TicketPanelView(self))
        self.bot.add_view(TicketControlView(self))

    # ---------- State-Helfer ---------- #

    def tickets(self, guild_id: int) -> dict[str, dict]:
        return self.bot.storage.guild(guild_id).setdefault("tickets", {})

    def ticket_for_channel(self, guild_id: int, channel_id: int) -> dict | None:
        return self.tickets(guild_id).get(str(channel_id))

    def open_ticket_of(self, guild: discord.Guild, user_id: int) -> discord.TextChannel | None:
        for channel_id, data in self.tickets(guild.id).items():
            if data["creator"] == user_id:
                channel = guild.get_channel(int(channel_id))
                if channel:
                    return channel
        return None

    def is_staff(self, member: discord.Member) -> bool:
        role_id = self.bot.storage.get(member.guild.id, "ticket_support_role")
        return member.guild_permissions.manage_channels or any(r.id == role_id for r in member.roles)

    # ---------- Commands & Events ---------- #

    @app_commands.command(name="ticketpanel", description="Postet das Ticket-Panel in einen Kanal.")
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.checks.bot_has_permissions(manage_channels=True, manage_roles=True)
    async def ticketpanel(self, interaction: discord.Interaction, kanal: discord.TextChannel):
        embed = discord.Embed(
            title="🎫 Support-Tickets",
            description="Wähle eine Ticket-Art aus und ein privater Support-Kanal wird für dich erstellt.",
            color=discord.Color.blue(),
        )
        embed.set_footer(text="Support-Team")
        await kanal.send(embed=embed, view=TicketPanelView(self))
        await interaction.response.send_message(f"✅ Panel in {kanal.mention} gepostet.", ephemeral=True)

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel):
        # Ticket-Kanal manuell gelöscht → Eintrag aufräumen, sonst ist der User "für immer" blockiert
        if self.tickets(channel.guild.id).pop(str(channel.id), None) is not None:
            await self.bot.storage.save()

    # ---------- Aktionen (von den Views aufgerufen) ---------- #

    async def open_ticket(self, interaction: discord.Interaction, type_key: str) -> None:
        guild, user = interaction.guild, interaction.user
        label = TICKET_TYPES[type_key][0]

        if existing := self.open_ticket_of(guild, user.id):
            await interaction.response.send_message(
                f"⚠️ Du hast schon ein offenes Ticket: {existing.mention}", ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True, thinking=True)

        storage = self.bot.storage
        overwrites: dict[discord.abc.Snowflake, discord.PermissionOverwrite] = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            user: discord.PermissionOverwrite(
                view_channel=True, send_messages=True, attach_files=True, read_message_history=True
            ),
            guild.me: discord.PermissionOverwrite(
                view_channel=True, send_messages=True, manage_channels=True, read_message_history=True
            ),
        }
        if (role_id := storage.get(guild.id, "ticket_support_role")) and (role := guild.get_role(role_id)):
            overwrites[role] = discord.PermissionOverwrite(
                view_channel=True, send_messages=True, read_message_history=True
            )
        category = guild.get_channel(storage.get(guild.id, "ticket_category") or 0)

        channel = await guild.create_text_channel(
            name=f"ticket-{slug(user.name)}-{type_key}",
            topic=f"{label} von {user.display_name}",
            overwrites=overwrites,
            category=category if isinstance(category, discord.CategoryChannel) else None,
            reason=f"Ticket von {user}",
        )

        self.tickets(guild.id)[str(channel.id)] = {"creator": user.id, "type": label, "claimed_by": None}
        await storage.save()

        embed = discord.Embed(
            title=f"{label}",
            description=f"Hallo {user.mention}, beschreib dein Anliegen – das Support-Team meldet sich hier.",
            color=discord.Color.green(),
        )
        embed.set_footer(text="Klicke auf 'Schließen', wenn alles geklärt ist.")
        await channel.send(content=user.mention, embed=embed, view=TicketControlView(self))
        await interaction.followup.send(f"✅ Ticket erstellt: {channel.mention}", ephemeral=True)

    async def claim_ticket(self, interaction: discord.Interaction) -> None:
        ticket = self.ticket_for_channel(interaction.guild_id, interaction.channel_id)
        if ticket is None:
            return await _deny(interaction, "Das ist kein aktives Ticket.")
        if interaction.user.id == ticket["creator"]:
            return await _deny(interaction, "⚠️ Dein eigenes Ticket kannst du nicht beanspruchen.")
        if not self.is_staff(interaction.user):
            return await _deny(interaction, "⛔ Nur das Support-Team kann Tickets beanspruchen.")
        if ticket["claimed_by"]:
            return await _deny(interaction, f"⚠️ Schon beansprucht von <@{ticket['claimed_by']}>.")

        ticket["claimed_by"] = interaction.user.id
        await self.bot.storage.save()
        await interaction.response.send_message(f"🎯 {interaction.user.mention} kümmert sich um dieses Ticket.")

    async def close_ticket(self, interaction: discord.Interaction) -> None:
        guild, channel = interaction.guild, interaction.channel
        ticket = self.ticket_for_channel(guild.id, channel.id)
        if ticket is None:
            return await _deny(interaction, "Das ist kein aktives Ticket.")
        if interaction.user.id != ticket["creator"] and not self.is_staff(interaction.user):
            return await _deny(interaction, "⛔ Nur der Ersteller oder Support kann schließen.")

        # Erst austragen, dann archivieren – sonst archiviert ein Doppelklick zweimal
        self.tickets(guild.id).pop(str(channel.id), None)
        await self.bot.storage.save()
        await interaction.response.send_message("🔒 Ticket wird archiviert und in 5 Sekunden geschlossen…")

        archive_id = self.bot.storage.get(guild.id, "ticket_archive_channel")
        archive = guild.get_channel(archive_id) if archive_id else None
        if isinstance(archive, discord.TextChannel):
            await self._archive(channel, archive, ticket, closed_by=interaction.user)

        await asyncio.sleep(5)
        await channel.delete(reason=f"Ticket geschlossen von {interaction.user}")

    async def _archive(
        self, channel: discord.TextChannel, archive: discord.TextChannel, ticket: dict, closed_by: discord.abc.User
    ) -> None:
        lines: list[str] = []
        async for msg in channel.history(limit=None, oldest_first=True):
            stamp = msg.created_at.strftime("%Y-%m-%d %H:%M")
            content = msg.clean_content or ""
            for embed in msg.embeds:
                content += f" [Embed: {embed.title or embed.description or ''}]"
            for att in msg.attachments:
                content += f" [Anhang: {att.url}]"
            lines.append(f"[{stamp}] {msg.author.display_name}: {content.strip()}")

        file = discord.File(io.BytesIO("\n".join(lines).encode("utf-8")), filename=f"{channel.name}.txt")

        embed = discord.Embed(title="📂 Ticket archiviert", color=discord.Color.gold())
        embed.add_field(name="Ticket", value=channel.name)
        embed.add_field(name="Art", value=ticket["type"])
        embed.add_field(name="Ersteller", value=f"<@{ticket['creator']}>")
        embed.add_field(name="Beansprucht", value=f"<@{ticket['claimed_by']}>" if ticket["claimed_by"] else "—")
        embed.add_field(name="Geschlossen von", value=closed_by.mention)
        embed.add_field(name="Nachrichten", value=str(len(lines)))
        embed.timestamp = discord.utils.utcnow()
        await archive.send(embed=embed, file=file)


# ---------- Views ---------- #


class TicketPanelView(discord.ui.View):
    def __init__(self, cog: Tickets):
        super().__init__(timeout=None)
        for key, (label, style, emoji) in TICKET_TYPES.items():
            button = discord.ui.Button(label=label, style=style, emoji=emoji, custom_id=f"ticket:open:{key}")
            button.callback = self._make_callback(cog, key)
            self.add_item(button)

    @staticmethod
    def _make_callback(cog: Tickets, key: str):
        async def callback(interaction: discord.Interaction):
            await cog.open_ticket(interaction, key)
        return callback


class TicketControlView(discord.ui.View):
    def __init__(self, cog: Tickets):
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(label="Beanspruchen", style=discord.ButtonStyle.success, emoji="🎯", custom_id="ticket:claim")
    async def claim(self, interaction: discord.Interaction, _: discord.ui.Button):
        await self.cog.claim_ticket(interaction)

    @discord.ui.button(label="Schließen", style=discord.ButtonStyle.danger, emoji="🔒", custom_id="ticket:close")
    async def close(self, interaction: discord.Interaction, _: discord.ui.Button):
        await self.cog.close_ticket(interaction)


async def setup(bot: LunasBot) -> None:
    await bot.add_cog(Tickets(bot))

import discord
from discord.ext import commands
from discord import app_commands
from discord.ui import Button, View


class TicketSystem(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.ticket_channel_id: int | None = None
        self.archive_channel_id: int | None = None
        self.open_tickets: dict[int, int] = {}  # user_id -> channel_id

    # ---------------- Commands ---------------- #

    @app_commands.command(name="set_ticket_panel", description="Setze den Kanal für das Ticket-Panel.")
    async def set_ticket_panel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        """Ticket-Panel mit Buttons im angegebenen Kanal erstellen."""
        self.ticket_channel_id = channel.id
        await interaction.response.send_message(
            f"✅ Ticket-Panel wurde auf {channel.mention} gesetzt.", ephemeral=True
        )

        embed = discord.Embed(
            title="🎫 Support-Tickets",
            description="Wähle eine Ticket-Art aus und ein Support-Kanal wird für dich erstellt.",
            color=discord.Color.blue(),
        )
        embed.set_footer(text="Support-Team")

        view = TicketActionView(self)
        await channel.send(embed=embed, view=view)

    @app_commands.command(name="set_archive_channel", description="Setze den Archivkanal für geschlossene Tickets.")
    async def set_archive_channel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        self.archive_channel_id = channel.id
        await interaction.response.send_message(
            f"✅ Archivkanal wurde auf {channel.mention} gesetzt.", ephemeral=True
        )


# ---------------- Ticket Panel ---------------- #

class TicketActionView(View):
    def __init__(self, cog: TicketSystem):
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(label="Allgemeine Anfrage", style=discord.ButtonStyle.primary, custom_id="general_ticket")
    async def general_ticket(self, interaction: discord.Interaction, button: Button):
        await self.create_ticket(interaction, "Allgemeine Anfrage")

    @discord.ui.button(label="Technische Unterstützung", style=discord.ButtonStyle.secondary, custom_id="technical_ticket")
    async def technical_ticket(self, interaction: discord.Interaction, button: Button):
        await self.create_ticket(interaction, "Technische Unterstützung")

    async def create_ticket(self, interaction: discord.Interaction, ticket_type: str):
        user = interaction.user
        guild = interaction.guild

        # Verhindern, dass ein User mehrere Tickets gleichzeitig hat
        if user.id in self.cog.open_tickets:
            await interaction.response.send_message("⚠️ Du hast bereits ein offenes Ticket.", ephemeral=True)
            return

        ticket_channel = await guild.create_text_channel(
            name=f"ticket-{user.name}-{ticket_type.replace(' ', '-').lower()}",
            topic=f"{ticket_type} für {user.display_name}",
            reason="Neues Ticket erstellt"
        )

        # Berechtigungen setzen
        await ticket_channel.set_permissions(user, read_messages=True, send_messages=True)
        await ticket_channel.set_permissions(guild.default_role, read_messages=False)

        self.cog.open_tickets[user.id] = ticket_channel.id

        embed = discord.Embed(
            title=f"{ticket_type} Ticket",
            description=f"Hallo {user.mention}, das Support-Team wird sich hier um dein Anliegen kümmern.",
            color=discord.Color.green(),
        )
        embed.set_footer(text="Klicke auf 'Schließen', wenn das Ticket abgeschlossen ist.")

        view = CloseTicketView(self.cog, ticket_channel, user)
        await ticket_channel.send(content=user.mention, embed=embed, view=view)

        await interaction.response.send_message(
            f"✅ Dein {ticket_type}-Ticket wurde erstellt: {ticket_channel.mention}", ephemeral=True
        )


# ---------------- Ticket Management ---------------- #

class CloseTicketView(View):
    def __init__(self, cog: TicketSystem, channel: discord.TextChannel, creator: discord.User):
        super().__init__(timeout=None)
        self.cog = cog
        self.channel = channel
        self.creator = creator
        self.claimed_by: discord.Member | None = None

    @discord.ui.button(label="Beanspruchen", style=discord.ButtonStyle.success, custom_id="claim_ticket")
    async def claim_ticket_button(self, interaction: discord.Interaction, button: Button):
        # Ersteller darf sein Ticket nicht beanspruchen
        if interaction.user.id == self.creator.id:
            await interaction.response.send_message("⚠️ Du kannst dein eigenes Ticket nicht beanspruchen.", ephemeral=True)
            return

        # Prüfen, ob Ticket schon beansprucht wurde
        if self.claimed_by:
            await interaction.response.send_message("⚠️ Dieses Ticket wurde bereits beansprucht.", ephemeral=True)
            return

        self.claimed_by = interaction.user
        await interaction.response.send_message("✅ Du hast das Ticket erfolgreich beansprucht.", ephemeral=True)

        # Falls Admin: Zugriff auf Ersteller + Admin beschränken
        if interaction.user.guild_permissions.administrator:
            await self.channel.set_permissions(interaction.guild.default_role, read_messages=False)
            for member in self.channel.members:
                if member not in (self.creator, interaction.user):
                    await self.channel.set_permissions(member, overwrite=None)

            await self.channel.set_permissions(self.creator, read_messages=True, send_messages=True)
            await self.channel.set_permissions(interaction.user, read_messages=True, send_messages=True)

        await self.channel.send(f"🎯 {interaction.user.mention} hat das Ticket beansprucht und wird dir helfen.")

    @discord.ui.button(label="Schließen", style=discord.ButtonStyle.danger, custom_id="close_ticket")
    async def close_ticket_button(self, interaction: discord.Interaction, button: Button):
        if self.creator.id in self.cog.open_tickets:
            del self.cog.open_tickets[self.creator.id]

        await self.archive_ticket(interaction)
        await self.channel.delete(reason="Ticket geschlossen")

    async def archive_ticket(self, interaction: discord.Interaction):
        """Speichert den Ticketverlauf im Archivkanal."""
        if not self.cog.archive_channel_id:
            await interaction.response.send_message("⚠️ Archivkanal ist nicht gesetzt. Nutze `/set_archive_channel`.", ephemeral=True)
            return

        archive_channel = interaction.guild.get_channel(self.cog.archive_channel_id)
        if not archive_channel:
            await interaction.response.send_message("⚠️ Archivkanal wurde nicht gefunden.", ephemeral=True)
            return

        # Verlauf sammeln
        messages = []
        async for msg in self.channel.history(limit=100):
            if msg.content:
                messages.append(f"{msg.author.display_name}: {msg.content}")

        messages.reverse()

        embed = discord.Embed(
            title="📂 Archiviertes Ticket",
            description=f"Ticket-Verlauf von {self.creator.mention} aus {self.channel.name}.",
            color=discord.Color.gold(),
        )

        chunk_size = 1024
        for i in range(0, len(messages), chunk_size // 80):
            chunk = "\n".join(messages[i:i + chunk_size // 80])
            embed.add_field(name="Verlauf", value=chunk, inline=False)

        await archive_channel.send(embed=embed)
        await interaction.response.send_message("✅ Ticket wurde erfolgreich im Archiv gespeichert.", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(TicketSystem(bot))

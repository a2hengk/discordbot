import discord
from discord.ext import commands
import difflib


class AuditLog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.audit_log_channel_id: int | None = None

    # ---------------- Hilfsfunktionen ---------------- #

    def get_audit_log_channel(self, guild: discord.Guild) -> discord.TextChannel | None:
        """Gibt den gespeicherten Audit-Log-Kanal zurück, falls vorhanden."""
        return guild.get_channel(self.audit_log_channel_id)

    async def send_audit_log(
        self,
        guild: discord.Guild,
        title: str,
        description: str,
        color: discord.Color,
        user: discord.abc.User,
        fields: list[tuple[str, str, bool]] | None = None
    ):
        """Erstellt und sendet ein Embed an den Audit-Log-Kanal."""
        channel = self.get_audit_log_channel(guild)
        if not channel:
            return

        embed = discord.Embed(title=title, description=description, color=color)
        embed.set_footer(text=f"Benutzer_ID: {user.id}")

        if fields:
            for name, value, inline in fields:
                embed.add_field(name=name, value=value, inline=inline)

        await channel.send(embed=embed)

    # ---------------- Event-Listener ---------------- #

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        await self.send_audit_log(
            guild=member.guild,
            title="👋 Neuer Benutzer beigetreten",
            description=f"Der Benutzer `{member.name}` ist dem Server beigetreten.",
            color=discord.Color.green(),
            user=member,
        )

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        await self.send_audit_log(
            guild=member.guild,
            title="🚪 Benutzer hat den Server verlassen",
            description=f"Der Benutzer `{member.name}` hat den Server verlassen.",
            color=discord.Color.red(),
            user=member,
        )

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        if not message.content:  # leere Nachrichten ignorieren
            return

        await self.send_audit_log(
            guild=message.guild,
            title="🗑️ Nachricht gelöscht",
            description=f"Nachricht von Benutzer `{message.author.name}` wurde gelöscht.",
            color=discord.Color.orange(),
            user=message.author,
            fields=[("Gelöschter Inhalt", message.content, False)],
        )

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        if before.content == after.content:
            return

        diff = list(difflib.ndiff(before.content.split(), after.content.split()))
        changes = [d for d in diff if d.startswith("- ") or d.startswith("+ ")]
        if not changes:
            return

        fields: list[tuple[str, str, bool]] = []

        # Durchlaufen und Kontext-Snippets bauen
        for idx, change in enumerate(diff):
            if change.startswith("- "):  # Entfernt
                word = change[2:]
                before_ctx = diff[idx - 1][2:] if idx > 0 and not diff[idx - 1].startswith("? ") else "…"
                after_ctx = diff[idx + 1][2:] if idx + 1 < len(diff) and not diff[idx + 1].startswith("? ") else "…"
                snippet = f"{before_ctx} __{word}__ {after_ctx}"
                fields.append(("Entfernt", snippet, False))

            elif change.startswith("+ "):  # Hinzugefügt
                word = change[2:]
                before_ctx = diff[idx - 1][2:] if idx > 0 and not diff[idx - 1].startswith("? ") else "…"
                snippet = f"{before_ctx} __**{word}**__"
                fields.append(("Hinzugefügt", snippet, False))

        await self.send_audit_log(
            guild=before.guild,
            title="✏️ Nachricht bearbeitet",
            description=(
                f"Nachricht von **{before.author.display_name}** wurde bearbeitet "
                f"in {before.channel.mention}."
            ),
            color=discord.Color.blue(),
            user=before.author,
            fields=fields,
       )


    # ---------------- Slash-Commands ---------------- #

    @discord.app_commands.command(
        name="set_audit_log_channel",
        description="Setze den Kanal für Audit-Logs."
    )
    async def set_audit_log_channel(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel
    ):
        self.audit_log_channel_id = channel.id
        await interaction.response.send_message(
            f"✅ Audit-Log-Kanal wurde auf {channel.mention} gesetzt."
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(AuditLog(bot))

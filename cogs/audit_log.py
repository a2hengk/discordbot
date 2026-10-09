"""Audit-Log: Joins, Leaves, gelöschte und bearbeitete Nachrichten."""

from __future__ import annotations

import difflib

import discord
from discord.ext import commands

from core.bot import LunasBot

FIELD_LIMIT = 1024


def truncate(text: str, limit: int = FIELD_LIMIT) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"


def word_diff(before: str, after: str) -> str:
    """Markiert Änderungen inline: ~~entfernt~~ und **neu**."""
    a, b = before.split(), after.split()
    parts: list[str] = []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(a=a, b=b).get_opcodes():
        if op == "equal":
            parts.append(" ".join(a[i1:i2]))
        if op in ("delete", "replace"):
            parts.append(f"~~{' '.join(a[i1:i2])}~~")
        if op in ("insert", "replace"):
            parts.append(f"**{' '.join(b[j1:j2])}**")
    return " ".join(parts)


class AuditLog(commands.Cog):
    def __init__(self, bot: LunasBot):
        self.bot = bot

    async def send(self, guild: discord.Guild | None, embed: discord.Embed) -> None:
        if guild is None:
            return
        channel_id = self.bot.storage.get(guild.id, "audit_log_channel")
        channel = guild.get_channel(channel_id) if channel_id else None
        if isinstance(channel, discord.TextChannel):
            embed.timestamp = discord.utils.utcnow()
            await channel.send(embed=embed)

    @staticmethod
    def _user_embed(title: str, user: discord.abc.User, color: discord.Color, description: str = "") -> discord.Embed:
        embed = discord.Embed(title=title, description=description, color=color)
        embed.set_author(name=str(user), icon_url=user.display_avatar.url)
        embed.set_footer(text=f"User-ID: {user.id}")
        return embed

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        created = discord.utils.format_dt(member.created_at, "R")
        embed = self._user_embed("👋 Beigetreten", member, discord.Color.green(),
                                 f"{member.mention} – Account erstellt {created}")
        await self.send(member.guild, embed)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        embed = self._user_embed("🚪 Verlassen", member, discord.Color.red(), member.mention)
        await self.send(member.guild, embed)

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        if message.guild is None or message.author.bot or (not message.content and not message.attachments):
            return
        embed = self._user_embed("🗑️ Nachricht gelöscht", message.author, discord.Color.orange(),
                                 f"in {message.channel.mention}")
        if message.content:
            embed.add_field(name="Inhalt", value=truncate(message.content), inline=False)
        if message.attachments:
            names = "\n".join(a.filename for a in message.attachments)
            embed.add_field(name="Anhänge", value=truncate(names), inline=False)
        await self.send(message.guild, embed)

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        if before.guild is None or before.author.bot or before.content == after.content:
            return
        embed = self._user_embed("✏️ Nachricht bearbeitet", before.author, discord.Color.blue(),
                                 f"in {before.channel.mention} · [zur Nachricht]({after.jump_url})")
        embed.add_field(name="Änderung", value=truncate(word_diff(before.content, after.content)), inline=False)
        await self.send(before.guild, embed)


async def setup(bot: LunasBot) -> None:
    await bot.add_cog(AuditLog(bot))

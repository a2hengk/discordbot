"""Willkommensnachricht mit GIF für neue Mitglieder."""

from __future__ import annotations

import discord
from discord.ext import commands

from core.bot import LunasBot
from core.config import ASSETS_DIR

WELCOME_GIF = ASSETS_DIR / "join.gif"


class Welcome(commands.Cog):
    def __init__(self, bot: LunasBot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        channel_id = self.bot.storage.get(member.guild.id, "welcome_channel")
        channel = member.guild.get_channel(channel_id) if channel_id else None
        if not isinstance(channel, discord.TextChannel):
            return

        embed = discord.Embed(
            title="Willkommen auf dem Server!",
            description=f"Hallo {member.mention}, wir freuen uns, dich hier zu haben!",
            color=discord.Color.green(),
        )
        embed.set_thumbnail(url=member.display_avatar.url)

        if WELCOME_GIF.is_file():
            file = discord.File(WELCOME_GIF, filename="welcome.gif")
            embed.set_image(url="attachment://welcome.gif")
            await channel.send(embed=embed, file=file)
        else:
            await channel.send(embed=embed)


async def setup(bot: LunasBot) -> None:
    await bot.add_cog(Welcome(bot))

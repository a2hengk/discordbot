"""Mod-Fälle: speichern + ins Mod-Log schreiben. Wird von Moderation, Automod und Anti-Raid genutzt."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

import discord

from core.utils import format_duration

if TYPE_CHECKING:
    from core.bot import LunasBot

ACTIONS: dict[str, tuple[str, discord.Color]] = {
    "warn": ("⚠️ Verwarnung", discord.Color.yellow()),
    "timeout": ("🔇 Timeout", discord.Color.orange()),
    "untimeout": ("🔊 Timeout aufgehoben", discord.Color.green()),
    "kick": ("👢 Kick", discord.Color.dark_orange()),
    "ban": ("🔨 Bann", discord.Color.red()),
    "unban": ("🕊️ Entbannt", discord.Color.green()),
    "automod": ("🛡️ Automod", discord.Color.dark_gold()),
    "antiraid": ("🚨 Anti-Raid", discord.Color.dark_red()),
}


async def create_case(
    bot: LunasBot,
    guild: discord.Guild,
    user: discord.abc.User,
    moderator: discord.abc.User,
    action: str,
    reason: str | None,
    duration_s: int | None = None,
) -> int:
    case_id = await bot.db.execute(
        """INSERT INTO mod_cases (guild_id, user_id, moderator_id, action, reason, duration_s, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (guild.id, user.id, moderator.id, action, reason, duration_s, int(time.time())),
    )

    title, color = ACTIONS.get(action, (action, discord.Color.greyple()))
    embed = discord.Embed(title=f"{title} · Fall #{case_id}", color=color)
    embed.add_field(name="User", value=f"{user.mention}\n`{user}`")
    embed.add_field(name="Moderator", value=moderator.mention)
    if duration_s:
        embed.add_field(name="Dauer", value=format_duration(duration_s))
    embed.add_field(name="Grund", value=reason or "—", inline=False)
    embed.set_thumbnail(url=user.display_avatar.url)
    embed.set_footer(text=f"User-ID: {user.id}")
    await bot.modlog(guild, embed)
    return case_id


async def notify_user(
    user: discord.abc.User, guild: discord.Guild, action: str, reason: str | None, duration_s: int | None = None
) -> bool:
    """DM an den bestraften User. Klappt nicht, wenn er DMs zu hat – dann eben nicht."""
    title, color = ACTIONS.get(action, (action, discord.Color.greyple()))
    embed = discord.Embed(title=f"{title} auf {guild.name}", color=color)
    embed.add_field(name="Grund", value=reason or "—", inline=False)
    if duration_s:
        embed.add_field(name="Dauer", value=format_duration(duration_s))
    try:
        await user.send(embed=embed)
        return True
    except (discord.Forbidden, discord.HTTPException):
        return False

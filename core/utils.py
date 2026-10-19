"""Kleine Helfer, die mehrere Cogs brauchen."""

from __future__ import annotations

import re
from datetime import timedelta

import discord

MAX_TIMEOUT = timedelta(days=28)  # Discord-Limit für Timeouts

_DURATION_PART = re.compile(r"(\d+)\s*(w|d|h|m|s)", re.IGNORECASE)
_UNITS = {"w": 604800, "d": 86400, "h": 3600, "m": 60, "s": 1}


def parse_duration(text: str) -> timedelta | None:
    """'10m', '2h', '1d', '1h30m', '1w' → timedelta. Ungültig → None."""
    cleaned = text.replace(" ", "").lower()
    if not cleaned:
        return None
    total, consumed = 0, 0
    for match in _DURATION_PART.finditer(cleaned):
        total += int(match.group(1)) * _UNITS[match.group(2).lower()]
        consumed += len(match.group(0))
    if consumed != len(cleaned) or total <= 0:
        return None
    return timedelta(seconds=total)


def format_duration(seconds: int | float) -> str:
    seconds = int(seconds)
    parts = []
    for unit, size in (("w", 604800), ("d", 86400), ("h", 3600), ("m", 60), ("s", 1)):
        if seconds >= size:
            amount, seconds = divmod(seconds, size)
            parts.append(f"{amount}{unit}")
    return " ".join(parts) or "0s"


def hierarchy_problem(moderator: discord.Member, target: discord.Member) -> str | None:
    """Prüft, ob moderator (und der Bot) target überhaupt bestrafen dürfen. None = alles ok."""
    guild = target.guild
    if target == moderator:
        return "Dich selbst kannst du nicht bestrafen."
    if target == guild.owner:
        return "Der Server-Owner kann nicht bestraft werden."
    if target == guild.me:
        return "Netter Versuch. 🙃"
    if moderator != guild.owner and target.top_role >= moderator.top_role:
        return f"{target.mention} hat eine gleich hohe oder höhere Rolle als du."
    if target.top_role >= guild.me.top_role:
        return f"{target.mention} steht über meiner höchsten Rolle – schieb meine Rolle in den Servereinstellungen höher."
    return None


DANGEROUS_PERMS = (
    "administrator", "manage_guild", "manage_roles", "manage_channels", "ban_members",
    "kick_members", "moderate_members", "manage_messages", "manage_webhooks", "mention_everyone",
)


def role_problem(role: discord.Role, *, allow_dangerous: bool = False) -> str | None:
    """Prüft, ob der Bot diese Rolle automatisch vergeben kann/sollte. None = ok."""
    me = role.guild.me
    if role.is_default():
        return "@everyone kann man nicht vergeben."
    if role.managed:
        return f"{role.mention} wird von einer Integration/einem Bot verwaltet."
    if role >= me.top_role:
        return f"{role.mention} steht über meiner höchsten Rolle – ich kann sie nicht vergeben."
    if not allow_dangerous:
        bad = [p for p in DANGEROUS_PERMS if getattr(role.permissions, p)]
        if bad:
            return f"{role.mention} hat Mod-/Admin-Rechte (`{', '.join(bad)}`) – die vergebe ich nicht automatisch."
    return None

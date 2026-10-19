from __future__ import annotations

import logging
import pkgutil

import discord
from discord import app_commands
from discord.ext import commands

import cogs
from core.config import DB_FILE, SETTINGS_FILE, Config
from core.db import Database
from core.storage import GuildStorage

log = logging.getLogger(__name__)


def discover_extensions() -> list[str]:
    """Findet alle Module unter cogs/ (inkl. Unterordnern) mit setup()-Funktion."""
    return sorted(
        mod.name
        for mod in pkgutil.walk_packages(cogs.__path__, prefix="cogs.")
        if not mod.ispkg
    )


class LunasBot(commands.Bot):
    def __init__(self, config: Config):
        intents = discord.Intents.default()
        intents.message_content = True  # Chat-Antworten, Zahlenraten, Speed, Audit-Log
        intents.members = True          # Join/Leave-Events, Anti-Raid, Autorole

        super().__init__(
            command_prefix="!",
            intents=intents,
            # Standardmäßig keine @everyone/@here/Rollen-Pings durch den Bot
            allowed_mentions=discord.AllowedMentions(everyone=False, roles=False, users=True),
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name="The Angel Next Door Spoils Me Rotten",
            ),
        )
        self.config = config
        self.db = Database(DB_FILE)
        self.storage = GuildStorage(self.db)
        # Nachrichten, die der Bot selbst gelöscht hat (Automod) – das Audit-Log ignoriert sie,
        # weil sie schon im Mod-Log stehen
        self.suppressed_deletes: set[int] = set()
        self.tree.on_error = self.on_app_command_error

    async def setup_hook(self) -> None:
        await self.db.connect()
        await self.storage.load(legacy_json=SETTINGS_FILE)

        for ext in discover_extensions():
            await self.load_extension(ext)
            log.info("Extension geladen: %s", ext)

        # Sync einmal beim Start statt bei jedem on_ready (das feuert auch bei Reconnects).
        if self.config.dev_guild_id:
            guild = discord.Object(id=self.config.dev_guild_id)
            self.tree.copy_global_to(guild=guild)
            synced = await self.tree.sync(guild=guild)
            log.info("%d Slash-Commands auf Dev-Server synchronisiert", len(synced))
        else:
            synced = await self.tree.sync()
            log.info("%d Slash-Commands global synchronisiert", len(synced))

    async def close(self) -> None:
        await super().close()
        await self.db.close()

    async def modlog(self, guild: discord.Guild, embed: discord.Embed) -> None:
        """Schickt ein Embed in den Mod-Log-Kanal (Fallback: Audit-Log-Kanal)."""
        channel_id = self.storage.get(guild.id, "mod_log_channel") or self.storage.get(guild.id, "audit_log_channel")
        channel = guild.get_channel(channel_id) if channel_id else None
        if isinstance(channel, discord.TextChannel):
            embed.timestamp = embed.timestamp or discord.utils.utcnow()
            try:
                await channel.send(embed=embed)
            except discord.HTTPException:
                log.warning("Mod-Log in %s konnte nicht gesendet werden", channel)

    async def on_ready(self) -> None:
        log.info("Online als %s (ID: %s)", self.user, self.user.id if self.user else "?")

    async def on_app_command_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ) -> None:
        if isinstance(error, app_commands.MissingPermissions):
            msg = "⛔ Dafür fehlen dir die Rechte."
        elif isinstance(error, app_commands.BotMissingPermissions):
            missing = ", ".join(error.missing_permissions)
            msg = f"⛔ Mir fehlen Rechte: `{missing}`"
        elif isinstance(error, app_commands.CommandOnCooldown):
            msg = f"⏳ Mach mal langsam – geht wieder in {error.retry_after:.0f}s."
        elif isinstance(error, app_commands.NoPrivateMessage):
            msg = "Das geht nur auf einem Server."
        else:
            log.exception("Fehler in /%s", interaction.command.name if interaction.command else "?",
                          exc_info=error)
            msg = "💥 Da ist was schiefgelaufen."

        if interaction.response.is_done():
            await interaction.followup.send(msg, ephemeral=True)
        else:
            await interaction.response.send_message(msg, ephemeral=True)

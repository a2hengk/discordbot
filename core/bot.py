from __future__ import annotations

import logging
import pkgutil

import discord
from discord import app_commands
from discord.ext import commands

import cogs
from core.config import SETTINGS_FILE, Config
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
        intents.members = True          # Join/Leave-Events

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
        self.storage = GuildStorage(SETTINGS_FILE)
        self.tree.on_error = self.on_app_command_error

    async def setup_hook(self) -> None:
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

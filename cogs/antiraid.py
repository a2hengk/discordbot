"""Anti-Raid + Lockdown. Sitzt als "Türsteher" vor allen Join-Features.

Bei jedem Join:
1. Lockdown aktiv?              → kicken (mit DM)
2. Raid-Modus aktiv?            → kicken (mit DM)
3. Account jünger als X Tage?  → kicken (mit DM) + Mod-Log
4. Zu viele Joins in kurzer Zeit → Raid-Modus für ein paar Minuten + Alarm im Mod-Log
5. Alles ok → Event "member_accepted" → Willkommensnachricht + Autorole

/lockdown an  sperrt das Schreiben in allen Textkanälen für @everyone und blockt Joins.
/lockdown aus stellt die vorherigen Kanalrechte exakt wieder her (liegen in der DB).
"""

from __future__ import annotations

import json
import time
from collections import defaultdict, deque

import discord
from discord import app_commands
from discord.ext import commands

from core.bot import LunasBot
from core.cases import create_case

DEFAULTS = {"enabled": False, "joins": 8, "seconds": 10, "min_age_days": 0, "raid_minutes": 10}
LOCK_PERMS = ("send_messages", "send_messages_in_threads", "create_public_threads")


def _perm_to_str(value: bool | None) -> str:
    return {True: "allow", False: "deny", None: "none"}[value]


def _str_to_perm(value: str) -> bool | None:
    return {"allow": True, "deny": False, "none": None}[value]


class AntiRaid(commands.Cog):
    antiraid = app_commands.Group(name="antiraid", description="Schutz gegen Raids und Fake-Accounts",
                                  guild_only=True, default_permissions=discord.Permissions(manage_guild=True))
    lockdown = app_commands.Group(name="lockdown", description="Server dichtmachen",
                                  guild_only=True, default_permissions=discord.Permissions(manage_guild=True))

    def __init__(self, bot: LunasBot):
        self.bot = bot
        self.joins: dict[int, deque[tuple[float, int]]] = defaultdict(deque)
        self.raid_until: dict[int, float] = {}
        self.raid_kicks: dict[int, int] = defaultdict(int)

    def config(self, guild_id: int) -> dict:
        return {**DEFAULTS, **self.bot.storage.get(guild_id, "antiraid", {})}

    def lockdown_active(self, guild_id: int) -> bool:
        return bool(self.bot.storage.get(guild_id, "lockdown", {}).get("active"))

    def raid_active(self, guild_id: int) -> bool:
        return self.raid_until.get(guild_id, 0) > time.monotonic()

    # ---------- Join-Pipeline ---------- #

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        guild = member.guild
        if member.bot:  # Bots werden von Admins eingeladen, die lassen wir durch
            self.bot.dispatch("member_accepted", member)
            return

        if self.lockdown_active(guild.id):
            await self.reject(member, "Der Server ist gerade im Lockdown. Versuch's später nochmal.")
            return

        cfg = self.config(guild.id)
        if cfg["enabled"]:
            if self.raid_active(guild.id):
                self.raid_kicks[guild.id] += 1
                await self.reject(member, "Gerade läuft ein Raid-Schutz. Versuch's in ein paar Minuten nochmal.")
                return

            age_days = (discord.utils.utcnow() - member.created_at).days
            if cfg["min_age_days"] and age_days < cfg["min_age_days"]:
                reason = f"Account zu neu ({age_days} Tage, mindestens {cfg['min_age_days']} nötig)"
                if await self.reject(member, f"Dein Account ist zu neu für diesen Server ({reason})."):
                    await create_case(self.bot, guild, member, guild.me, "antiraid", reason)
                return

            await self.track_join(member, cfg)

        self.bot.dispatch("member_accepted", member)

    async def track_join(self, member: discord.Member, cfg: dict) -> None:
        guild, now = member.guild, time.monotonic()
        joins = self.joins[guild.id]
        joins.append((now, member.id))
        while joins and now - joins[0][0] > cfg["seconds"]:
            joins.popleft()
        if len(joins) < cfg["joins"]:
            return

        suspects = [user_id for _, user_id in joins]
        joins.clear()
        self.raid_until[guild.id] = now + cfg["raid_minutes"] * 60
        self.raid_kicks[guild.id] = 0

        embed = discord.Embed(
            title="🚨 Raid erkannt – Raid-Modus aktiv",
            description=(
                f"**{len(suspects)} Joins in {cfg['seconds']}s.** Neue Joins werden die nächsten "
                f"{cfg['raid_minutes']} Minuten automatisch gekickt.\n\n"
                f"Verdächtige Accounts (schon drin):\n" + " ".join(f"<@{uid}>" for uid in suspects)[:3500]
                + "\n\nFrüher beenden: `/antiraid raidmodus-beenden` · Alles dichtmachen: `/lockdown an`"
            ),
            color=discord.Color.dark_red(),
        )
        await self.bot.modlog(guild, embed)

    async def reject(self, member: discord.Member, message: str) -> bool:
        try:
            await member.send(f"🚪 **{member.guild.name}:** {message}")
        except discord.HTTPException:
            pass
        try:
            await member.kick(reason=f"Anti-Raid: {message}")
            return True
        except discord.HTTPException:
            return False

    # ---------- /antiraid ---------- #

    @antiraid.command(name="einstellen", description="Anti-Raid konfigurieren (nur was du angibst, wird geändert).")
    @app_commands.describe(
        aktiv="Anti-Raid an/aus",
        joins="So viele Joins …",
        sekunden="… in so vielen Sekunden = Raid",
        kontoalter_tage="Accounts jünger als X Tage werden gekickt (0 = aus)",
        raid_minuten="So lange bleibt der Raid-Modus an",
    )
    async def einstellen(
        self, interaction: discord.Interaction,
        aktiv: bool | None = None,
        joins: app_commands.Range[int, 3, 100] | None = None,
        sekunden: app_commands.Range[int, 3, 300] | None = None,
        kontoalter_tage: app_commands.Range[int, 0, 365] | None = None,
        raid_minuten: app_commands.Range[int, 1, 120] | None = None,
    ):
        cfg = self.config(interaction.guild_id)
        for key, value in (("enabled", aktiv), ("joins", joins), ("seconds", sekunden),
                           ("min_age_days", kontoalter_tage), ("raid_minutes", raid_minuten)):
            if value is not None:
                cfg[key] = value
        await self.bot.storage.set(interaction.guild_id, "antiraid", cfg)
        await interaction.response.send_message(embed=self.status_embed(interaction.guild), ephemeral=True)

    @antiraid.command(name="status", description="Anti-Raid- und Lockdown-Status anzeigen.")
    async def status(self, interaction: discord.Interaction):
        await interaction.response.send_message(embed=self.status_embed(interaction.guild), ephemeral=True)

    @antiraid.command(name="raidmodus-beenden", description="Raid-Modus vorzeitig beenden.")
    async def raidmodus_beenden(self, interaction: discord.Interaction):
        if not self.raid_active(interaction.guild_id):
            return await interaction.response.send_message("Der Raid-Modus ist gerade nicht aktiv.", ephemeral=True)
        self.raid_until.pop(interaction.guild_id, None)
        kicked = self.raid_kicks.pop(interaction.guild_id, 0)
        await interaction.response.send_message(f"✅ Raid-Modus beendet ({kicked} Joins wurden geblockt).",
                                                ephemeral=True)

    def status_embed(self, guild: discord.Guild) -> discord.Embed:
        cfg = self.config(guild.id)
        embed = discord.Embed(title="🛡️ Anti-Raid", color=discord.Color.dark_red())
        embed.add_field(name="Status", value="🟢 an" if cfg["enabled"] else "⚫ aus")
        embed.add_field(name="Raid ab", value=f"{cfg['joins']} Joins / {cfg['seconds']}s")
        embed.add_field(name="Mindest-Kontoalter", value=f"{cfg['min_age_days']} Tage" if cfg["min_age_days"] else "aus")
        embed.add_field(name="Raid-Modus-Dauer", value=f"{cfg['raid_minutes']} min")
        if self.raid_active(guild.id):
            left = int(self.raid_until[guild.id] - time.monotonic()) // 60 + 1
            embed.add_field(name="Raid-Modus", value=f"🔴 aktiv, noch ~{left} min ({self.raid_kicks[guild.id]} geblockt)")
        embed.add_field(name="Lockdown", value="🔴 aktiv" if self.lockdown_active(guild.id) else "⚫ aus")
        if not guild.me.guild_permissions.kick_members:
            embed.set_footer(text="⚠️ Mir fehlt das Recht 'Mitglieder kicken' – so kann ich niemanden rauswerfen.")
        return embed

    # ---------- /lockdown ---------- #

    @lockdown.command(name="an", description="Alle Textkanäle für @everyone sperren und neue Joins blocken.")
    @app_commands.checks.bot_has_permissions(manage_roles=True, manage_channels=True)
    async def lockdown_an(self, interaction: discord.Interaction, grund: str = "Kein Grund angegeben"):
        guild = interaction.guild
        if self.lockdown_active(guild.id):
            return await interaction.response.send_message("Der Lockdown läuft schon.", ephemeral=True)
        await interaction.response.defer(ephemeral=True, thinking=True)

        everyone, locked, failed = guild.default_role, 0, []
        for channel in [*guild.text_channels, *guild.forums]:
            overwrite = channel.overwrites_for(everyone)
            previous = {perm: _perm_to_str(getattr(overwrite, perm)) for perm in LOCK_PERMS}
            for perm in LOCK_PERMS:
                setattr(overwrite, perm, False)
            try:
                await channel.set_permissions(everyone, overwrite=overwrite, reason=f"Lockdown: {grund}")
            except discord.HTTPException:
                failed.append(channel.mention)
                continue
            # OR IGNORE: Falls schon ein alter Eintrag da ist, bleibt der Original-Zustand erhalten
            await self.bot.db.execute(
                "INSERT OR IGNORE INTO lockdown_channels (guild_id, channel_id, previous) VALUES (?, ?, ?)",
                (guild.id, channel.id, json.dumps(previous)),
            )
            locked += 1

        await self.bot.storage.set(guild.id, "lockdown", {"active": True, "reason": grund})
        embed = discord.Embed(title="🔒 Lockdown aktiv", color=discord.Color.dark_red(),
                              description=f"{locked} Kanäle gesperrt, neue Joins werden gekickt.\n**Grund:** {grund}")
        embed.add_field(name="Ausgelöst von", value=interaction.user.mention)
        await self.bot.modlog(guild, embed)

        text = f"🔒 Lockdown aktiv – {locked} Kanäle gesperrt. Aufheben mit `/lockdown aus`."
        if failed:
            text += f"\n⚠️ Nicht geklappt bei: {', '.join(failed)[:1500]}"
        await interaction.followup.send(text, ephemeral=True)

    @lockdown.command(name="aus", description="Lockdown aufheben und Kanalrechte wiederherstellen.")
    @app_commands.checks.bot_has_permissions(manage_roles=True, manage_channels=True)
    async def lockdown_aus(self, interaction: discord.Interaction):
        guild = interaction.guild
        await interaction.response.defer(ephemeral=True, thinking=True)
        rows = await self.bot.db.fetchall("SELECT channel_id, previous FROM lockdown_channels WHERE guild_id = ?",
                                          (guild.id,))
        restored = 0
        for row in rows:
            channel = guild.get_channel(row["channel_id"])
            if channel is not None:
                overwrite = channel.overwrites_for(guild.default_role)
                for perm, value in json.loads(row["previous"]).items():
                    setattr(overwrite, perm, _str_to_perm(value))
                try:
                    await channel.set_permissions(
                        guild.default_role, overwrite=None if overwrite.is_empty() else overwrite,
                        reason="Lockdown aufgehoben",
                    )
                    restored += 1
                except discord.HTTPException:
                    continue
            await self.bot.db.execute("DELETE FROM lockdown_channels WHERE guild_id = ? AND channel_id = ?",
                                      (guild.id, row["channel_id"]))

        await self.bot.storage.set(guild.id, "lockdown", None)
        embed = discord.Embed(title="🔓 Lockdown aufgehoben", color=discord.Color.green(),
                              description=f"{restored} Kanäle wiederhergestellt.")
        embed.add_field(name="Aufgehoben von", value=interaction.user.mention)
        await self.bot.modlog(guild, embed)
        await interaction.followup.send(f"🔓 Lockdown aufgehoben – {restored} Kanäle wiederhergestellt.", ephemeral=True)


async def setup(bot: LunasBot) -> None:
    await bot.add_cog(AntiRaid(bot))

"""Moderation: /warn, /timeout, /kick, /ban, /unban + Verwarnungs-Historie und Eskalation.

Jede Aktion
- prüft Rollen-Hierarchie (Mod darf niemanden über sich bestrafen, Bot auch nicht)
- schickt dem User eine DM mit Grund (falls DMs offen)
- landet als Fall (#ID) in der Datenbank und im Mod-Log-Kanal

Eskalation: ab X aktiven Verwarnungen gibt's automatisch einen Timeout
(einstellbar mit /config verwarnungen).
"""

from __future__ import annotations

from datetime import timedelta

import discord
from discord import app_commands
from discord.ext import commands

from core.bot import LunasBot
from core.cases import ACTIONS, create_case, notify_user
from core.utils import MAX_TIMEOUT, format_duration, hierarchy_problem, parse_duration

DEFAULT_ESCALATION = {"threshold": 3, "minutes": 60}



async def _fail(interaction: discord.Interaction, msg: str) -> None:
    await interaction.response.send_message(f"⛔ {msg}", ephemeral=True)


class Moderation(commands.Cog):
    def __init__(self, bot: LunasBot):
        self.bot = bot

    # ---------- /warn ---------- #

    @app_commands.command(name="warn", description="Verwarnt ein Mitglied.")
    @app_commands.describe(mitglied="Wen?", grund="Warum? (bekommt der User per DM)")
    @app_commands.guild_only()
    @app_commands.default_permissions(moderate_members=True)
    async def warn(self, interaction: discord.Interaction, mitglied: discord.Member,
                   grund: app_commands.Range[str, 1, 500]):
        if problem := hierarchy_problem(interaction.user, mitglied):
            return await _fail(interaction, problem)

        case_id = await create_case(self.bot, interaction.guild, mitglied, interaction.user, "warn", grund)
        dm = await notify_user(mitglied, interaction.guild, "warn", grund)
        active = await self.active_warns(interaction.guild.id, mitglied.id)

        text = f"⚠️ {mitglied.mention} verwarnt (Fall #{case_id}, {active}. aktive Verwarnung)."
        if not dm:
            text += " _(DM ging nicht durch)_"
        await interaction.response.send_message(text, ephemeral=True)
        await self.maybe_escalate(interaction.guild, mitglied, active)

    async def active_warns(self, guild_id: int, user_id: int) -> int:
        return await self.bot.db.fetchval(
            "SELECT COUNT(*) FROM mod_cases WHERE guild_id = ? AND user_id = ? AND action = 'warn' AND active = 1",
            (guild_id, user_id), default=0,
        )

    async def maybe_escalate(self, guild: discord.Guild, member: discord.Member, active: int) -> None:
        cfg = self.bot.storage.get(guild.id, "warn_escalation", DEFAULT_ESCALATION)
        threshold, minutes = cfg.get("threshold", 0), cfg.get("minutes", 0)
        if not threshold or not minutes or active % threshold != 0:
            return
        duration = timedelta(minutes=minutes)
        reason = f"Automatisch: {active} aktive Verwarnungen"
        try:
            await member.timeout(duration, reason=reason)
        except discord.HTTPException:
            return
        await notify_user(member, guild, "timeout", reason, int(duration.total_seconds()))
        await create_case(self.bot, guild, member, guild.me, "timeout", reason, int(duration.total_seconds()))

    # ---------- /verlauf + /warn-entfernen ---------- #

    @app_commands.command(name="verlauf", description="Zeigt alle Mod-Fälle eines Mitglieds.")
    @app_commands.guild_only()
    @app_commands.default_permissions(moderate_members=True)
    async def verlauf(self, interaction: discord.Interaction, user: discord.User):
        rows = await self.bot.db.fetchall(
            """SELECT id, action, reason, moderator_id, created_at, duration_s, active FROM mod_cases
               WHERE guild_id = ? AND user_id = ? ORDER BY id DESC LIMIT 15""",
            (interaction.guild_id, user.id),
        )
        if not rows:
            return await interaction.response.send_message(f"✨ {user.mention} hat eine weiße Weste.", ephemeral=True)

        active = await self.active_warns(interaction.guild_id, user.id)
        embed = discord.Embed(title=f"Verlauf von {user}", color=discord.Color.blurple(),
                              description=f"Aktive Verwarnungen: **{active}**")
        embed.set_thumbnail(url=user.display_avatar.url)
        for row in rows:
            label = ACTIONS.get(row["action"], (row["action"], None))[0]
            if not row["active"]:
                label = f"~~{label}~~ (entfernt)"
            extra = f" · {format_duration(row['duration_s'])}" if row["duration_s"] else ""
            when = f"<t:{row['created_at']}:R>"
            embed.add_field(
                name=f"#{row['id']} {label}{extra}",
                value=f"{(row['reason'] or '—')[:200]}\nvon <@{row['moderator_id']}> {when}",
                inline=False,
            )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="warn-entfernen", description="Nimmt eine Verwarnung zurück (zählt nicht mehr).")
    @app_commands.describe(fall="Fall-Nummer aus /verlauf")
    @app_commands.guild_only()
    @app_commands.default_permissions(moderate_members=True)
    async def warn_entfernen(self, interaction: discord.Interaction, fall: int):
        row = await self.bot.db.fetchone(
            "SELECT user_id, active FROM mod_cases WHERE id = ? AND guild_id = ? AND action = 'warn'",
            (fall, interaction.guild_id),
        )
        if row is None:
            return await _fail(interaction, f"Keine Verwarnung mit Fall #{fall} gefunden.")
        if not row["active"]:
            return await _fail(interaction, f"Fall #{fall} ist schon entfernt.")
        await self.bot.db.execute("UPDATE mod_cases SET active = 0 WHERE id = ?", (fall,))
        await interaction.response.send_message(f"✅ Verwarnung #{fall} von <@{row['user_id']}> entfernt.",
                                                ephemeral=True)

    # ---------- /timeout + /untimeout ---------- #

    @app_commands.command(name="timeout", description="Schaltet ein Mitglied für eine Zeit stumm.")
    @app_commands.describe(dauer="z.B. 10m, 2h, 1d, 1h30m (max. 28d)", grund="Warum?")
    @app_commands.guild_only()
    @app_commands.default_permissions(moderate_members=True)
    @app_commands.checks.bot_has_permissions(moderate_members=True)
    async def timeout(self, interaction: discord.Interaction, mitglied: discord.Member, dauer: str,
                      grund: app_commands.Range[str, 1, 500]):
        duration = parse_duration(dauer)
        if duration is None:
            return await _fail(interaction, "Dauer nicht verstanden. Beispiele: `10m`, `2h`, `1d`, `1h30m`.")
        if duration > MAX_TIMEOUT:
            return await _fail(interaction, "Discord erlaubt maximal 28 Tage Timeout.")
        if problem := hierarchy_problem(interaction.user, mitglied):
            return await _fail(interaction, problem)

        seconds = int(duration.total_seconds())
        await mitglied.timeout(duration, reason=f"{interaction.user}: {grund}")
        await notify_user(mitglied, interaction.guild, "timeout", grund, seconds)
        case_id = await create_case(self.bot, interaction.guild, mitglied, interaction.user, "timeout", grund, seconds)
        await interaction.response.send_message(
            f"🔇 {mitglied.mention} ist für {format_duration(seconds)} stumm (Fall #{case_id}).", ephemeral=True
        )

    @app_commands.command(name="untimeout", description="Hebt einen Timeout auf.")
    @app_commands.guild_only()
    @app_commands.default_permissions(moderate_members=True)
    @app_commands.checks.bot_has_permissions(moderate_members=True)
    async def untimeout(self, interaction: discord.Interaction, mitglied: discord.Member,
                        grund: app_commands.Range[str, 1, 500] = "Timeout aufgehoben"):
        if not mitglied.is_timed_out():
            return await _fail(interaction, f"{mitglied.mention} hat gerade keinen Timeout.")
        await mitglied.timeout(None, reason=f"{interaction.user}: {grund}")
        case_id = await create_case(self.bot, interaction.guild, mitglied, interaction.user, "untimeout", grund)
        await interaction.response.send_message(f"🔊 Timeout von {mitglied.mention} aufgehoben (Fall #{case_id}).",
                                                ephemeral=True)

    # ---------- /kick ---------- #

    @app_commands.command(name="kick", description="Wirft ein Mitglied vom Server (kann wieder joinen).")
    @app_commands.guild_only()
    @app_commands.default_permissions(kick_members=True)
    @app_commands.checks.bot_has_permissions(kick_members=True)
    async def kick(self, interaction: discord.Interaction, mitglied: discord.Member,
                   grund: app_commands.Range[str, 1, 500]):
        if problem := hierarchy_problem(interaction.user, mitglied):
            return await _fail(interaction, problem)
        await notify_user(mitglied, interaction.guild, "kick", grund)  # DM VOR dem Kick, danach geht's nicht mehr
        await mitglied.kick(reason=f"{interaction.user}: {grund}")
        case_id = await create_case(self.bot, interaction.guild, mitglied, interaction.user, "kick", grund)
        await interaction.response.send_message(f"👢 {mitglied} gekickt (Fall #{case_id}).", ephemeral=True)

    # ---------- /ban + /unban ---------- #

    @app_commands.command(name="ban", description="Bannt einen User (geht auch, wenn er nicht auf dem Server ist).")
    @app_commands.describe(nachrichten_loeschen="Nachrichten der letzten … löschen")
    @app_commands.choices(nachrichten_loeschen=[
        app_commands.Choice(name="nichts löschen", value=0),
        app_commands.Choice(name="letzte Stunde", value=3600),
        app_commands.Choice(name="letzte 24 Stunden", value=86400),
        app_commands.Choice(name="letzte 7 Tage", value=604800),
    ])
    @app_commands.guild_only()
    @app_commands.default_permissions(ban_members=True)
    @app_commands.checks.bot_has_permissions(ban_members=True)
    async def ban(self, interaction: discord.Interaction, user: discord.User,
                  grund: app_commands.Range[str, 1, 500], nachrichten_loeschen: int = 0):
        member = interaction.guild.get_member(user.id)
        if member and (problem := hierarchy_problem(interaction.user, member)):
            return await _fail(interaction, problem)
        if member:
            await notify_user(member, interaction.guild, "ban", grund)
        await interaction.guild.ban(user, reason=f"{interaction.user}: {grund}",
                                    delete_message_seconds=nachrichten_loeschen)
        case_id = await create_case(self.bot, interaction.guild, user, interaction.user, "ban", grund)
        await interaction.response.send_message(f"🔨 {user} gebannt (Fall #{case_id}).", ephemeral=True)

    @app_commands.command(name="unban", description="Hebt einen Bann auf.")
    @app_commands.describe(user_id="ID des gebannten Users (Rechtsklick → ID kopieren)")
    @app_commands.guild_only()
    @app_commands.default_permissions(ban_members=True)
    @app_commands.checks.bot_has_permissions(ban_members=True)
    async def unban(self, interaction: discord.Interaction, user_id: str,
                    grund: app_commands.Range[str, 1, 500] = "Bann aufgehoben"):
        if not user_id.isdigit():
            return await _fail(interaction, "Das ist keine gültige User-ID.")
        try:
            ban = await interaction.guild.fetch_ban(discord.Object(id=int(user_id)))
        except discord.NotFound:
            return await _fail(interaction, "Dieser User ist nicht gebannt.")
        await interaction.guild.unban(ban.user, reason=f"{interaction.user}: {grund}")
        case_id = await create_case(self.bot, interaction.guild, ban.user, interaction.user, "unban", grund)
        await interaction.response.send_message(f"🕊️ {ban.user} entbannt (Fall #{case_id}).", ephemeral=True)


async def setup(bot: LunasBot) -> None:
    await bot.add_cog(Moderation(bot))

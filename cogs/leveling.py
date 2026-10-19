"""Leveling: XP fürs Schreiben, Level-Ups, Rangliste und Belohnungsrollen.

- Pro Nachricht 15–25 XP, aber höchstens einmal pro Minute pro User (sonst lohnt sich Spam)
- XP für das nächste Level: 5·L² + 50·L + 100 (dieselbe Kurve wie MEE6 → fühlt sich vertraut an)
- /rank, /rangliste für alle; /levels … für Admins (Belohnungen, Kanal, an/aus)
"""

from __future__ import annotations

import random
import time

import discord
from discord import app_commands
from discord.ext import commands

from core.bot import LunasBot
from core.utils import role_problem

XP_MIN, XP_MAX, COOLDOWN = 15, 25, 60
DEFAULTS = {"enabled": True, "channel": None}


def xp_for_next(level: int) -> int:
    return 5 * level**2 + 50 * level + 100


def level_from_xp(total: int) -> tuple[int, int, int]:
    """Gesamt-XP → (Level, XP im aktuellen Level, XP fürs nächste Level)."""
    level = 0
    while total >= xp_for_next(level):
        total -= xp_for_next(level)
        level += 1
    return level, total, xp_for_next(level)


def progress_bar(current: int, needed: int, width: int = 12) -> str:
    filled = round(width * current / needed) if needed else width
    return "▰" * filled + "▱" * (width - filled)


class Leveling(commands.Cog):
    levels = app_commands.Group(name="levels", description="Level-System einstellen",
                                guild_only=True, default_permissions=discord.Permissions(manage_guild=True))

    def __init__(self, bot: LunasBot):
        self.bot = bot
        self.cooldowns: dict[tuple[int, int], float] = {}

    def config(self, guild_id: int) -> dict:
        return {**DEFAULTS, **self.bot.storage.get(guild_id, "leveling", {})}

    # ---------- XP vergeben ---------- #

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.guild is None or message.author.bot or not isinstance(message.author, discord.Member):
            return
        if not self.config(message.guild.id)["enabled"]:
            return
        key, now = (message.guild.id, message.author.id), time.monotonic()
        if now - self.cooldowns.get(key, 0) < COOLDOWN:
            return
        self.cooldowns[key] = now

        gained = random.randint(XP_MIN, XP_MAX)
        row = await self.bot.db.fetchone(
            """INSERT INTO levels (guild_id, user_id, xp, messages) VALUES (?, ?, ?, 1)
               ON CONFLICT (guild_id, user_id) DO UPDATE SET xp = xp + excluded.xp, messages = messages + 1
               RETURNING xp, level""",
            (message.guild.id, message.author.id, gained),
        )
        await self.bot.db.conn.commit()

        new_level = level_from_xp(row["xp"])[0]
        if new_level > row["level"]:
            await self.bot.db.execute("UPDATE levels SET level = ? WHERE guild_id = ? AND user_id = ?",
                                      (new_level, message.guild.id, message.author.id))
            await self.level_up(message, new_level)

    async def level_up(self, message: discord.Message, level: int) -> None:
        member, guild = message.author, message.guild
        rewards = await self.apply_rewards(member, level)

        text = f"🎉 {member.mention} ist jetzt **Level {level}**!"
        if rewards:
            text += f" Neue Rolle: {', '.join(r.mention for r in rewards)}"

        channel_id = self.config(guild.id)["channel"]
        channel = guild.get_channel(channel_id) if channel_id else message.channel
        if isinstance(channel, (discord.TextChannel, discord.Thread, discord.VoiceChannel)):
            try:
                await channel.send(text, allowed_mentions=discord.AllowedMentions(users=True, roles=False))
            except discord.HTTPException:
                pass

    async def apply_rewards(self, member: discord.Member, level: int) -> list[discord.Role]:
        rows = await self.bot.db.fetchall(
            "SELECT role_id FROM level_rewards WHERE guild_id = ? AND level <= ?", (member.guild.id, level)
        )
        roles = [r for row in rows if (r := member.guild.get_role(row["role_id"])) and r not in member.roles
                 and r < member.guild.me.top_role]
        if roles:
            try:
                await member.add_roles(*roles, reason=f"Level {level} erreicht")
            except discord.HTTPException:
                return []
        return roles

    # ---------- /rank + /rangliste ---------- #

    @app_commands.command(name="rank", description="Zeigt dein Level (oder das von jemand anderem).")
    @app_commands.guild_only()
    async def rank(self, interaction: discord.Interaction, mitglied: discord.Member | None = None):
        member = mitglied or interaction.user
        row = await self.bot.db.fetchone("SELECT xp, messages FROM levels WHERE guild_id = ? AND user_id = ?",
                                         (interaction.guild_id, member.id))
        if row is None:
            who = "Du hast" if member == interaction.user else f"{member.display_name} hat"
            return await interaction.response.send_message(f"{who} noch keine XP. Einfach mal was schreiben! ✍️",
                                                           ephemeral=True)

        position = await self.bot.db.fetchval(
            "SELECT COUNT(*) + 1 FROM levels WHERE guild_id = ? AND xp > ?", (interaction.guild_id, row["xp"])
        )
        level, current, needed = level_from_xp(row["xp"])
        embed = discord.Embed(color=member.color if member.color.value else discord.Color.blurple())
        embed.set_author(name=member.display_name, icon_url=member.display_avatar.url)
        embed.add_field(name="Level", value=f"**{level}**")
        embed.add_field(name="Rang", value=f"#{position}")
        embed.add_field(name="Nachrichten", value=str(row["messages"]))
        embed.add_field(name=f"Fortschritt · {current}/{needed} XP",
                        value=f"`{progress_bar(current, needed)}`", inline=False)
        embed.set_footer(text=f"{row['xp']} XP insgesamt")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="rangliste", description="Die Top 10 des Servers.")
    @app_commands.guild_only()
    async def rangliste(self, interaction: discord.Interaction):
        rows = await self.bot.db.fetchall(
            "SELECT user_id, xp FROM levels WHERE guild_id = ? ORDER BY xp DESC LIMIT 10", (interaction.guild_id,)
        )
        if not rows:
            return await interaction.response.send_message("Noch niemand hat XP gesammelt.", ephemeral=True)
        medals = {1: "🥇", 2: "🥈", 3: "🥉"}
        lines = [
            f"{medals.get(i, f'`#{i}`')} <@{row['user_id']}> · Level **{level_from_xp(row['xp'])[0]}** · {row['xp']} XP"
            for i, row in enumerate(rows, start=1)
        ]
        embed = discord.Embed(title=f"🏆 Rangliste · {interaction.guild.name}", description="\n".join(lines),
                              color=discord.Color.gold())
        await interaction.response.send_message(embed=embed, allowed_mentions=discord.AllowedMentions.none())

    # ---------- /levels (Admin) ---------- #

    @levels.command(name="belohnung", description="Rolle, die man ab einem Level automatisch bekommt.")
    async def belohnung(self, interaction: discord.Interaction, level: app_commands.Range[int, 1, 500],
                        rolle: discord.Role):
        if problem := role_problem(rolle):
            return await interaction.response.send_message(f"⛔ {problem}", ephemeral=True)
        await self.bot.db.execute(
            """INSERT INTO level_rewards (guild_id, level, role_id) VALUES (?, ?, ?)
               ON CONFLICT (guild_id, level) DO UPDATE SET role_id = excluded.role_id""",
            (interaction.guild_id, level, rolle.id),
        )
        await interaction.response.send_message(
            f"✅ Ab Level {level} gibt's {rolle.mention}. (Wer schon drüber ist, bekommt sie beim nächsten Level-Up.)",
            ephemeral=True,
        )

    @levels.command(name="belohnung-entfernen", description="Belohnungsrolle für ein Level entfernen.")
    async def belohnung_entfernen(self, interaction: discord.Interaction, level: int):
        await self.bot.db.execute("DELETE FROM level_rewards WHERE guild_id = ? AND level = ?",
                                  (interaction.guild_id, level))
        await interaction.response.send_message(f"✅ Belohnung für Level {level} entfernt.", ephemeral=True)

    @levels.command(name="kanal", description="Wohin Level-Up-Nachrichten gehen (leer = da, wo geschrieben wurde).")
    async def kanal(self, interaction: discord.Interaction, kanal: discord.TextChannel | None = None):
        cfg = self.config(interaction.guild_id)
        cfg["channel"] = kanal.id if kanal else None
        await self.bot.storage.set(interaction.guild_id, "leveling", cfg)
        where = kanal.mention if kanal else "den Kanal, in dem geschrieben wurde"
        await interaction.response.send_message(f"✅ Level-Ups gehen jetzt in {where}.", ephemeral=True)

    @levels.command(name="schalter", description="Level-System an- oder ausschalten.")
    async def schalter(self, interaction: discord.Interaction, aktiv: bool):
        cfg = self.config(interaction.guild_id)
        cfg["enabled"] = aktiv
        await self.bot.storage.set(interaction.guild_id, "leveling", cfg)
        await interaction.response.send_message(f"✅ Level-System ist {'an' if aktiv else 'aus'}.", ephemeral=True)

    @levels.command(name="anzeigen", description="Einstellungen und Belohnungen anzeigen.")
    async def anzeigen(self, interaction: discord.Interaction):
        cfg = self.config(interaction.guild_id)
        rows = await self.bot.db.fetchall(
            "SELECT level, role_id FROM level_rewards WHERE guild_id = ? ORDER BY level", (interaction.guild_id,)
        )
        embed = discord.Embed(title="📈 Level-System", color=discord.Color.gold())
        embed.add_field(name="Status", value="🟢 an" if cfg["enabled"] else "⚫ aus")
        embed.add_field(name="Level-Up-Kanal", value=f"<#{cfg['channel']}>" if cfg["channel"] else "wo geschrieben wurde")
        embed.add_field(name="Belohnungen", inline=False,
                        value="\n".join(f"Level {r['level']} → <@&{r['role_id']}>" for r in rows) or "—")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @levels.command(name="zurücksetzen", description="XP eines Mitglieds auf 0 setzen.")
    async def zuruecksetzen(self, interaction: discord.Interaction, mitglied: discord.Member):
        await self.bot.db.execute("DELETE FROM levels WHERE guild_id = ? AND user_id = ?",
                                  (interaction.guild_id, mitglied.id))
        await interaction.response.send_message(f"✅ XP von {mitglied.mention} zurückgesetzt.", ephemeral=True)


async def setup(bot: LunasBot) -> None:
    await bot.add_cog(Leveling(bot))

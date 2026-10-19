"""Selbstvergabe-Rollen (Buttons oder Dropdown) + Autorole beim Join.

Rollen-Panels:
  /rollenpanel erstellen   → postet ein (noch leeres) Panel in einen Kanal
  /rollenpanel hinzufügen  → Rolle ans Panel hängen (Button bzw. Dropdown-Option)
  /rollenpanel entfernen   → Rolle wieder raus
Klick auf eine Rolle = an/aus (toggle). Panels funktionieren auch nach einem Neustart,
weil die Buttons über "Dynamic Items" (custom_id mit Rollen-ID drin) erkannt werden.

Autorole:
  Wird mit /config autorole gesetzt. Ohne Verifizierung gibt's die Rolle direkt nach dem Join
  (nach den Anti-Raid-Checks), mit Verifizierung erst nach dem Verifizieren.
"""

from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from core.bot import LunasBot
from core.utils import role_problem

MAX_ENTRIES = 25  # Discord-Limit: 25 Buttons bzw. 25 Dropdown-Optionen pro Nachricht


def _emoji(raw: str | None) -> discord.PartialEmoji | None:
    return discord.PartialEmoji.from_str(raw) if raw else None


async def _panel_roles(bot: LunasBot, message_id: int) -> set[int]:
    rows = await bot.db.fetchall("SELECT role_id FROM role_panel_entries WHERE message_id = ?", (message_id,))
    return {row["role_id"] for row in rows}


async def _toggle(interaction: discord.Interaction, role_ids: list[int]) -> str:
    """Schaltet Rollen beim klickenden User an/aus und gibt eine Zusammenfassung zurück."""
    guild, member = interaction.guild, interaction.user
    allowed = await _panel_roles(interaction.client, interaction.message.id)
    added, removed, failed = [], [], []

    for role_id in role_ids:
        role = guild.get_role(role_id)
        if role is None or role_id not in allowed or role >= guild.me.top_role:
            failed.append(f"<@&{role_id}>")
            continue
        try:
            if role in member.roles:
                await member.remove_roles(role, reason="Rollen-Panel")
                removed.append(role.mention)
            else:
                await member.add_roles(role, reason="Rollen-Panel")
                added.append(role.mention)
        except discord.HTTPException:
            failed.append(role.mention)

    lines = []
    if added:
        lines.append(f"✅ Bekommen: {', '.join(added)}")
    if removed:
        lines.append(f"➖ Entfernt: {', '.join(removed)}")
    if failed:
        lines.append(f"⚠️ Ging nicht: {', '.join(failed)} – sag einem Admin Bescheid.")
    return "\n".join(lines) or "Nichts geändert."


class RoleButton(discord.ui.DynamicItem[discord.ui.Button], template=r"rp:b:(?P<role_id>[0-9]+)"):
    def __init__(self, role_id: int, label: str | None = None, emoji: discord.PartialEmoji | str | None = None):
        super().__init__(discord.ui.Button(
            label=label, emoji=emoji, style=discord.ButtonStyle.secondary, custom_id=f"rp:b:{role_id}",
        ))
        self.role_id = role_id

    @classmethod
    async def from_custom_id(cls, interaction: discord.Interaction, item: discord.ui.Button, match):
        return cls(int(match["role_id"]), item.label, item.emoji)

    async def callback(self, interaction: discord.Interaction) -> None:
        text = await _toggle(interaction, [self.role_id])
        await interaction.response.send_message(text, ephemeral=True)


class RoleSelect(discord.ui.DynamicItem[discord.ui.Select], template=r"rp:s:(?P<message_id>[0-9]+)"):
    def __init__(self, message_id: int, options: list[discord.SelectOption]):
        super().__init__(discord.ui.Select(
            custom_id=f"rp:s:{message_id}",
            placeholder="Rollen auswählen (nochmal wählen = entfernen)",
            min_values=1,
            max_values=max(1, len(options)),
            options=options,
        ))
        self.message_id = message_id

    @classmethod
    async def from_custom_id(cls, interaction: discord.Interaction, item: discord.ui.Select, match):
        return cls(int(match["message_id"]), list(item.options))

    async def callback(self, interaction: discord.Interaction) -> None:
        values = [int(v) for v in interaction.data.get("values", [])]
        text = await _toggle(interaction, values)
        # Nachricht mit derselben View neu setzen → Auswahl im Dropdown springt zurück
        await interaction.response.edit_message(view=discord.ui.View(timeout=None).add_item(
            RoleSelect(self.message_id, list(self.item.options))
        ))
        await interaction.followup.send(text, ephemeral=True)


class Roles(commands.Cog):
    panel = app_commands.Group(
        name="rollenpanel", description="Rollen zum Selbst-Abholen",
        guild_only=True, default_permissions=discord.Permissions(manage_roles=True),
    )

    def __init__(self, bot: LunasBot):
        self.bot = bot

    async def cog_load(self) -> None:
        self.bot.add_dynamic_items(RoleButton, RoleSelect)

    async def cog_unload(self) -> None:
        self.bot.remove_dynamic_items(RoleButton, RoleSelect)

    # ---------- Panel rendern ---------- #

    async def render(self, message_id: int) -> str | None:
        """Baut Embed + Buttons/Dropdown aus der DB neu. Gibt Fehlertext zurück oder None."""
        panel = await self.bot.db.fetchone("SELECT * FROM role_panels WHERE message_id = ?", (message_id,))
        entries = await self.bot.db.fetchall(
            "SELECT * FROM role_panel_entries WHERE message_id = ? ORDER BY position", (message_id,)
        )
        channel = self.bot.get_channel(panel["channel_id"])
        if not isinstance(channel, discord.TextChannel):
            return "Der Kanal vom Panel existiert nicht mehr."

        lines = [panel["description"]] if panel["description"] else []
        if entries:
            lines.append("")
            lines += [f"{e['emoji'] or '•'} <@&{e['role_id']}>" for e in entries]
        else:
            lines.append("_Noch keine Rollen – Admins fügen welche mit `/rollenpanel hinzufügen` hinzu._")
        embed = discord.Embed(title=panel["title"], description="\n".join(lines), color=discord.Color.blurple())

        view = discord.ui.View(timeout=None)
        if entries and panel["mode"] == "buttons":
            for e in entries:
                view.add_item(RoleButton(e["role_id"], e["label"], _emoji(e["emoji"])))
        elif entries:
            options = [
                discord.SelectOption(label=e["label"], value=str(e["role_id"]), emoji=_emoji(e["emoji"]))
                for e in entries
            ]
            view.add_item(RoleSelect(message_id, options))

        try:
            message = channel.get_partial_message(message_id)
            await message.edit(embed=embed, view=view)
        except discord.NotFound:
            await self.bot.db.execute("DELETE FROM role_panels WHERE message_id = ?", (message_id,))
            return "Die Panel-Nachricht wurde gelöscht – Panel entfernt."
        except discord.HTTPException as e:
            return f"Discord hat das Panel abgelehnt ({e.text or e.status}). Ungültiges Emoji?"
        return None

    async def panel_autocomplete(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        rows = await self.bot.db.fetchall(
            "SELECT message_id, channel_id, title FROM role_panels WHERE guild_id = ? ORDER BY message_id DESC",
            (interaction.guild_id,),
        )
        choices = []
        for row in rows:
            channel = interaction.guild.get_channel(row["channel_id"])
            name = f"{row['title']} (#{channel.name if channel else '?'})"
            if current.lower() in name.lower():
                choices.append(app_commands.Choice(name=name[:100], value=str(row["message_id"])))
        return choices[:25]

    async def _get_panel(self, interaction: discord.Interaction, panel: str):
        if not panel.isdigit():
            return None
        return await self.bot.db.fetchone(
            "SELECT * FROM role_panels WHERE message_id = ? AND guild_id = ?", (int(panel), interaction.guild_id)
        )

    # ---------- Commands ---------- #

    @panel.command(name="erstellen", description="Neues Rollen-Panel in einem Kanal posten.")
    @app_commands.describe(modus="Buttons (bis 25) oder ein Dropdown-Menü")
    @app_commands.choices(modus=[
        app_commands.Choice(name="Buttons", value="buttons"),
        app_commands.Choice(name="Dropdown", value="dropdown"),
    ])
    async def erstellen(self, interaction: discord.Interaction, kanal: discord.TextChannel,
                        titel: app_commands.Range[str, 1, 200], modus: str = "buttons",
                        beschreibung: app_commands.Range[str, 1, 2000] | None = None):
        embed = discord.Embed(title=titel, description="_wird eingerichtet…_", color=discord.Color.blurple())
        try:
            message = await kanal.send(embed=embed)
        except discord.Forbidden:
            return await interaction.response.send_message(f"⛔ Ich darf in {kanal.mention} nicht schreiben.",
                                                           ephemeral=True)
        await self.bot.db.execute(
            "INSERT INTO role_panels (message_id, guild_id, channel_id, mode, title, description) VALUES (?,?,?,?,?,?)",
            (message.id, interaction.guild_id, kanal.id, modus, titel, beschreibung),
        )
        await self.render(message.id)
        await interaction.response.send_message(
            f"✅ Panel in {kanal.mention} erstellt. Jetzt Rollen dazu: `/rollenpanel hinzufügen`", ephemeral=True
        )

    @panel.command(name="hinzufügen", description="Rolle an ein Panel hängen.")
    @app_commands.describe(emoji="z.B. 🎮 oder ein Server-Emoji", beschriftung="Text auf dem Button (Standard: Rollenname)")
    @app_commands.autocomplete(panel=panel_autocomplete)
    async def hinzufuegen(self, interaction: discord.Interaction, panel: str, rolle: discord.Role,
                          emoji: str | None = None, beschriftung: app_commands.Range[str, 1, 80] | None = None):
        row = await self._get_panel(interaction, panel)
        if row is None:
            return await interaction.response.send_message("⛔ Panel nicht gefunden.", ephemeral=True)
        if problem := role_problem(rolle):
            return await interaction.response.send_message(f"⛔ {problem}", ephemeral=True)

        existing = await _panel_roles(self.bot, row["message_id"])
        if rolle.id in existing:
            return await interaction.response.send_message("⚠️ Die Rolle ist schon drin.", ephemeral=True)
        if len(existing) >= MAX_ENTRIES:
            return await interaction.response.send_message(f"⛔ Mehr als {MAX_ENTRIES} Rollen gehen nicht.",
                                                           ephemeral=True)

        await interaction.response.defer(ephemeral=True)
        await self.bot.db.execute(
            "INSERT INTO role_panel_entries (message_id, role_id, label, emoji, position) VALUES (?,?,?,?,?)",
            (row["message_id"], rolle.id, beschriftung or rolle.name, emoji, len(existing)),
        )
        if error := await self.render(row["message_id"]):
            await self.bot.db.execute("DELETE FROM role_panel_entries WHERE message_id = ? AND role_id = ?",
                                      (row["message_id"], rolle.id))
            await self.render(row["message_id"])
            return await interaction.followup.send(f"⛔ {error}", ephemeral=True)
        await interaction.followup.send(f"✅ {rolle.mention} hängt jetzt am Panel **{row['title']}**.", ephemeral=True)

    @panel.command(name="entfernen", description="Rolle von einem Panel nehmen.")
    @app_commands.autocomplete(panel=panel_autocomplete)
    async def entfernen(self, interaction: discord.Interaction, panel: str, rolle: discord.Role):
        row = await self._get_panel(interaction, panel)
        if row is None:
            return await interaction.response.send_message("⛔ Panel nicht gefunden.", ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        await self.bot.db.execute("DELETE FROM role_panel_entries WHERE message_id = ? AND role_id = ?",
                                  (row["message_id"], rolle.id))
        error = await self.render(row["message_id"])
        await interaction.followup.send(f"⛔ {error}" if error else f"✅ {rolle.mention} entfernt.", ephemeral=True)

    @commands.Cog.listener()
    async def on_raw_message_delete(self, payload: discord.RawMessageDeleteEvent) -> None:
        await self.bot.db.execute("DELETE FROM role_panels WHERE message_id = ?", (payload.message_id,))

    # ---------- Autorole ---------- #

    async def give_autorole(self, member: discord.Member) -> None:
        role_id = self.bot.storage.get(member.guild.id, "autorole")
        role = member.guild.get_role(role_id) if role_id else None
        if role is None or role in member.roles or role >= member.guild.me.top_role:
            return
        try:
            await member.add_roles(role, reason="Autorole")
        except discord.HTTPException:
            pass

    @commands.Cog.listener()
    async def on_member_accepted(self, member: discord.Member) -> None:
        # Eigenes Event aus antiraid.py: User hat die Anti-Raid-Checks bestanden
        if not member.bot and not self.bot.storage.get(member.guild.id, "verify_role"):
            await self.give_autorole(member)

    @commands.Cog.listener()
    async def on_member_verified(self, member: discord.Member) -> None:
        await self.give_autorole(member)


async def setup(bot: LunasBot) -> None:
    await bot.add_cog(Roles(bot))

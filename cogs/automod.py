"""Automod: Spam, Links, Discord-Einladungen, Caps und Massen-Pings.

Ergänzt Discords eingebaute AutoMod (die macht Wortfilter schon gut) um Dinge, die sie
nicht kann: Spam-Erkennung über Zeit, Link-Whitelist und Eskalation bei Wiederholung.

Ablauf bei einem Verstoß:
1. Nachricht löschen + kurzer Hinweis im Kanal (verschwindet nach ein paar Sekunden)
2. Eintrag im Mod-Log
3. Wer in 10 Minuten 3x auffällt, bekommt automatisch 10 Minuten Timeout

Leute mit "Nachrichten verwalten" werden ignoriert (Mods sollen nicht vom Bot gelöscht werden).
"""

from __future__ import annotations

import re
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import timedelta

import discord
from discord import app_commands
from discord.ext import commands

from core.bot import LunasBot
from core.cases import create_case, notify_user

RULES = {
    "spam": "Spam (zu viele / gleiche Nachrichten hintereinander)",
    "invites": "Discord-Einladungen zu anderen Servern",
    "links": "Links (außer freigegebene Domains)",
    "caps": "VIEL ZU VIEL CAPSLOCK",
    "mentions": "Massen-Pings (5+ Erwähnungen)",
}
DEFAULT_RULES = {rule: False for rule in RULES}
DEFAULT_DOMAINS = ["tenor.com", "giphy.com", "discord.com", "discordapp.com", "discordapp.net"]

# Grenzwerte – bewusst hier oben, damit man sie leicht anpassen kann
SPAM_MESSAGES, SPAM_SECONDS = 5, 5          # 5 Nachrichten in 5 Sekunden
DUPLICATE_COUNT, DUPLICATE_SECONDS = 3, 30   # 3x dieselbe Nachricht in 30 Sekunden
CAPS_MIN_LETTERS, CAPS_RATIO = 10, 0.7
MENTION_LIMIT = 5
STRIKES, STRIKE_WINDOW, STRIKE_TIMEOUT = 3, 600, timedelta(minutes=10)

INVITE_RE = re.compile(r"(?:discord(?:app)?\.com/invite|discord\.gg|dsc\.gg)/[\w-]+", re.IGNORECASE)
URL_RE = re.compile(r"https?://([^\s/:?#]+)", re.IGNORECASE)

REASONS = {
    "spam": "Bitte nicht spammen.",
    "invites": "Einladungen zu anderen Servern sind hier nicht erlaubt.",
    "links": "Links sind hier nur von freigegebenen Seiten erlaubt.",
    "caps": "Bitte nicht so viel Caps.",
    "mentions": "Bitte nicht so viele Leute auf einmal pingen.",
}


# ---------- reine Prüf-Funktionen (ohne Discord, leicht zu testen) ---------- #


def has_invite(text: str) -> bool:
    return bool(INVITE_RE.search(text))


def forbidden_links(text: str, allowed: list[str]) -> list[str]:
    bad = []
    for domain in URL_RE.findall(text):
        domain = domain.lower().removeprefix("www.")
        if not any(domain == a or domain.endswith("." + a) for a in allowed):
            bad.append(domain)
    return bad


def too_much_caps(text: str) -> bool:
    letters = [c for c in text if c.isalpha()]
    if len(letters) < CAPS_MIN_LETTERS:
        return False
    return sum(c.isupper() for c in letters) / len(letters) >= CAPS_RATIO


@dataclass
class SpamTracker:
    times: deque[float]
    recent: deque[tuple[float, str]]

    @classmethod
    def new(cls) -> SpamTracker:
        return cls(deque(maxlen=SPAM_MESSAGES), deque(maxlen=DUPLICATE_COUNT))

    def hit(self, content: str, now: float) -> bool:
        """Speichert die Nachricht und sagt, ob das jetzt Spam ist."""
        self.times.append(now)
        self.recent.append((now, content.strip().lower()))
        too_fast = len(self.times) == SPAM_MESSAGES and now - self.times[0] <= SPAM_SECONDS
        same = (
            len(self.recent) == DUPLICATE_COUNT
            and bool(content.strip())
            and len({c for _, c in self.recent}) == 1
            and now - self.recent[0][0] <= DUPLICATE_SECONDS
        )
        return too_fast or same


# ---------- Cog ---------- #


@app_commands.guild_only()
@app_commands.default_permissions(manage_guild=True)
class Automod(commands.GroupCog, group_name="automod", group_description="Automatische Moderation einstellen"):
    def __init__(self, bot: LunasBot):
        self.bot = bot
        self.spam: dict[tuple[int, int], SpamTracker] = defaultdict(SpamTracker.new)
        self.strikes: dict[tuple[int, int], deque[float]] = defaultdict(lambda: deque(maxlen=STRIKES))
        self.last_notice: dict[tuple[int, int], float] = {}

    def rules(self, guild_id: int) -> dict[str, bool]:
        return {**DEFAULT_RULES, **self.bot.storage.get(guild_id, "automod", {})}

    def domains(self, guild_id: int) -> list[str]:
        return self.bot.storage.get(guild_id, "automod_domains", DEFAULT_DOMAINS)

    # ---------- Prüfen ---------- #

    def check(self, message: discord.Message) -> str | None:
        """Gibt die verletzte Regel zurück oder None."""
        rules = self.rules(message.guild.id)
        text = message.content
        key = (message.guild.id, message.author.id)

        # Spam zuerst tracken, auch wenn die Nachricht gleich wegen was anderem fliegt
        if rules["spam"] and self.spam[key].hit(text, time.monotonic()):
            return "spam"
        if rules["invites"] and has_invite(text):
            return "invites"
        if rules["links"] and forbidden_links(text, self.domains(message.guild.id)):
            return "links"
        if rules["mentions"] and (
            message.mention_everyone or len(set(message.raw_mentions) | set(message.raw_role_mentions)) >= MENTION_LIMIT
        ):
            return "mentions"
        if rules["caps"] and too_much_caps(text):
            return "caps"
        return None

    def exempt(self, message: discord.Message) -> bool:
        if message.guild is None or message.author.bot or not isinstance(message.author, discord.Member):
            return True
        perms = message.channel.permissions_for(message.author)
        return perms.manage_messages or perms.administrator

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if self.exempt(message):
            return
        if rule := self.check(message):
            await self.punish(message, rule)

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message) -> None:
        # Sonst schreibt man was Harmloses und editiert den Invite-Link nachträglich rein
        if before.content == after.content or self.exempt(after):
            return
        rules = self.rules(after.guild.id)
        text = after.content
        rule = (
            "invites" if rules["invites"] and has_invite(text)
            else "links" if rules["links"] and forbidden_links(text, self.domains(after.guild.id))
            else None
        )
        if rule:
            await self.punish(after, rule)

    async def punish(self, message: discord.Message, rule: str) -> None:
        guild, member = message.guild, message.author
        key = (guild.id, member.id)
        now = time.monotonic()

        self.bot.suppressed_deletes.add(message.id)
        try:
            await message.delete()
        except discord.NotFound:
            pass
        except discord.Forbidden:
            self.bot.suppressed_deletes.discard(message.id)
            return  # Bot darf hier nicht löschen → nichts tun statt halb zu reagieren

        # Hinweis max. alle 10 Sekunden pro User, sonst spammt der Bot beim Spam mit
        if now - self.last_notice.get(key, 0) > 10:
            self.last_notice[key] = now
            try:
                await message.channel.send(f"🛡️ {member.mention} {REASONS[rule]}", delete_after=6,
                                           allowed_mentions=discord.AllowedMentions(users=True))
            except discord.HTTPException:
                pass

        reason = f"Automod: {RULES[rule]}"
        if message.content:
            reason += f"\n> {message.content[:300]}"
        await create_case(self.bot, guild, member, guild.me, "automod", reason)

        strikes = self.strikes[key]
        strikes.append(now)
        if len(strikes) == STRIKES and now - strikes[0] <= STRIKE_WINDOW:
            strikes.clear()
            timeout_reason = f"Automod: {STRIKES} Verstöße in {STRIKE_WINDOW // 60} Minuten"
            try:
                await member.timeout(STRIKE_TIMEOUT, reason=timeout_reason)
            except discord.HTTPException:
                return
            seconds = int(STRIKE_TIMEOUT.total_seconds())
            await notify_user(member, guild, "timeout", timeout_reason, seconds)
            await create_case(self.bot, guild, member, guild.me, "timeout", timeout_reason, seconds)

    # ---------- Einstellungen ---------- #

    @app_commands.command(name="regel", description="Automod-Regel an- oder ausschalten.")
    @app_commands.choices(regel=[app_commands.Choice(name=desc, value=key) for key, desc in RULES.items()]
                          + [app_commands.Choice(name="Alle Regeln", value="alle")])
    async def regel(self, interaction: discord.Interaction, regel: str, aktiv: bool):
        rules = self.rules(interaction.guild_id)
        for key in (RULES if regel == "alle" else [regel]):
            rules[key] = aktiv
        await self.bot.storage.set(interaction.guild_id, "automod", rules)
        name = "Alle Regeln" if regel == "alle" else RULES[regel]
        await interaction.response.send_message(f"✅ {name}: **{'an' if aktiv else 'aus'}**", ephemeral=True)

    @app_commands.command(name="domain", description="Domain für Links freigeben oder sperren.")
    @app_commands.describe(domain="z.B. youtube.com (Subdomains zählen mit)")
    async def domain(self, interaction: discord.Interaction, domain: str, erlauben: bool):
        domain = domain.lower().strip().removeprefix("https://").removeprefix("http://").removeprefix("www.").strip("/")
        domains = list(self.domains(interaction.guild_id))
        if erlauben and domain not in domains:
            domains.append(domain)
        elif not erlauben and domain in domains:
            domains.remove(domain)
        await self.bot.storage.set(interaction.guild_id, "automod_domains", domains)
        await interaction.response.send_message(
            f"✅ `{domain}` ist jetzt {'erlaubt' if erlauben else 'gesperrt'}.", ephemeral=True
        )

    @app_commands.command(name="anzeigen", description="Aktuelle Automod-Einstellungen.")
    async def anzeigen(self, interaction: discord.Interaction):
        rules = self.rules(interaction.guild_id)
        embed = discord.Embed(title="🛡️ Automod", color=discord.Color.dark_gold())
        embed.description = "\n".join(f"{'🟢' if rules[k] else '⚫'} {desc}" for k, desc in RULES.items())
        embed.add_field(name="Erlaubte Domains", value=", ".join(f"`{d}`" for d in self.domains(interaction.guild_id))
                        or "—", inline=False)
        embed.set_footer(text="Mods mit 'Nachrichten verwalten' sind ausgenommen. "
                              "Wortfilter: Servereinstellungen → AutoMod (Discord-eigen).")
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: LunasBot) -> None:
    await bot.add_cog(Automod(bot))

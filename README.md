# discordbot

Discord-Bot mit Python & [discord.py](https://discordpy.readthedocs.io/) – Moderation, Automod, Anti-Raid, Verifizierung, Rollen-Panels, Leveling, Tickets, Audit-Log, Minigames und ein bisschen Chat-Persönlichkeit.

## Features

| Bereich | Command / Trigger | Wer | Was passiert |
|---|---|---|---|
| ⚙️ Einstellungen | `/config auditlog`, `modlog`, `willkommen`, `autorole`, `verwarnungen`, `tickets`, `anzeigen` | Server verwalten | Kanäle, Rollen und Eskalation pro Server festlegen |
| 🔨 Moderation | `/warn`, `/timeout`, `/untimeout`, `/kick`, `/ban`, `/unban` | Mods | Strafe mit Grund, DM an den User, Fall-Nummer im Mod-Log |
| | `/verlauf <user>`, `/warn-entfernen <fall>` | Mods | Alle Fälle eines Users / Verwarnung zurücknehmen |
| | automatisch | – | Alle X Verwarnungen → Timeout (Standard: 3 → 60 min) |
| 🛡️ Automod | `/automod regel`, `/automod domain`, `/automod anzeigen` | Server verwalten | Spam, Invites, Links (mit Whitelist), Caps, Massen-Pings. 3 Verstöße in 10 min → 10 min Timeout |
| 🚨 Anti-Raid | `/antiraid einstellen`, `status`, `raidmodus-beenden` | Server verwalten | Join-Rate-Erkennung → Raid-Modus, Mindest-Kontoalter |
| 🔒 Lockdown | `/lockdown an`, `/lockdown aus` | Server verwalten | Alle Textkanäle für @everyone sperren + Joins blocken, danach exakt wiederherstellen |
| ✅ Verifizierung | `/verifizierung einrichten`, `aus` | Server verwalten | Button + kleine Rechenaufgabe → Rolle |
| 🎭 Rollen | `/rollenpanel erstellen`, `hinzufügen`, `entfernen` | Rollen verwalten | Rollen zum Selbst-Abholen per Buttons oder Dropdown |
| | automatisch | – | Autorole beim Join (bzw. nach Verifizierung) |
| 📈 Leveling | `/rank`, `/rangliste` | alle | XP fürs Schreiben (1x pro Minute), Level-Ups, Top 10 |
| | `/levels belohnung`, `kanal`, `schalter`, `anzeigen`, `zurücksetzen` | Server verwalten | Belohnungsrollen pro Level, Level-Up-Kanal |
| 🎫 Tickets | `/ticketpanel <kanal>` | Server verwalten | Postet ein Panel mit „Allgemeine Anfrage“ / „Technische Unterstützung“ |
| | Buttons im Ticket | Support / Ersteller | Beanspruchen, Schließen → Verlauf als `.txt` ins Archiv |
| 📋 Audit-Log | automatisch | – | Joins, Leaves, gelöschte und bearbeitete Nachrichten (mit Wort-Diff) |
| 👋 Willkommen | automatisch | – | Embed + GIF für neue Mitglieder (nach den Anti-Raid-Checks) |
| 🧹 Utility | `/clear <1-100>`, `/say <text>` | Nachrichten verwalten | Nachrichten löschen / Bot schreiben lassen |
| | `/embed [text] [bild]` | alle | Text/Bild als Embed posten (30 s Cooldown) |
| 🎮 Games | `/rps`, `/zahlenraten`, `/speed` | alle | Schere-Stein-Papier, Zahl 1–100 erraten, Tipp-Speedtest |
| 💬 Chat | „gumo“, „guna“, „mahlzeit“ … / @Bot | alle | Begrüßungen und Antworten (siehe `data/convo.json`) |

Mod-Commands sind standardmäßig nur für Leute mit den passenden Discord-Rechten sichtbar
(z.B. `/ban` nur mit „Mitglieder bannen“). Feinjustieren: Servereinstellungen → Integrationen → Bot.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env             # Token eintragen
python main.py
```

Im [Developer Portal](https://discord.com/developers/applications) unter **Bot → Privileged Gateway Intents** müssen **Server Members** und **Message Content** an sein.

Beim Einladen braucht der Bot die Scopes `bot` + `applications.commands` und: Kanäle verwalten, Rollen verwalten, Nachrichten verwalten, Mitglieder kicken, Mitglieder bannen, Mitglieder moderieren (Timeout), Nachrichten senden, Dateien anhängen, Nachrichtenverlauf lesen.

**Wichtig:** Die Bot-Rolle muss in der Rollenliste **über** allen Rollen stehen, die er vergeben oder bestrafen soll. Discord lässt Bots nur Rollen unter ihrer eigenen anfassen.

**Tipp zum Entwickeln:** `DEV_GUILD_ID` in der `.env` setzen – dann sind Slash-Commands auf diesem Server sofort da statt nach bis zu einer Stunde.

## Daten

Alles liegt in **`data/bot.db`**, einer SQLite-Datenbank (eine einzige Datei, kein DB-Server nötig).
Der Bot spricht sie über [aiosqlite](https://github.com/omnilib/aiosqlite) an, damit Datenbankzugriffe
die Event-Loop nicht blockieren. Tabellen werden beim Start automatisch angelegt (`core/db.py` → `MIGRATIONS`).
Eine alte `data/settings.json` wird beim ersten Start einmalig importiert.

Backup = `data/bot.db` kopieren (am besten, während der Bot aus ist). Reinschauen geht z.B. mit
[DB Browser for SQLite](https://sqlitebrowser.org/).

## Verifizierung einrichten

1. Rolle „Verifiziert“ anlegen (unter der Bot-Rolle)
2. @everyone sieht nur den Verifizierungs-Kanal, alle anderen Kanäle nur „Verifiziert“
3. `/verifizierung einrichten kanal:#verify rolle:@Verifiziert`
4. Optional `/config autorole` – die gibt's dann nach dem Verifizieren

## Struktur

```
main.py              Einstiegspunkt
core/
  bot.py             Bot-Klasse, lädt alle Cogs automatisch, Fehlerbehandlung, Mod-Log
  config.py          .env + Pfade
  db.py              SQLite-Verbindung (aiosqlite) + Migrationen
  storage.py         Einstellungen pro Server (Tabelle guild_settings, RAM-Cache)
  cases.py           Mod-Fälle speichern + ins Mod-Log schreiben
  utils.py           Dauer parsen, Rollen-Hierarchie prüfen
cogs/                Jede Datei = ein Feature, wird automatisch geladen
  antiraid.py        Join-Türsteher, Raid-Modus, Lockdown
  automod.py         Spam/Links/Invites/Caps/Pings
  moderation.py      warn/timeout/kick/ban + Verlauf
  roles.py           Rollen-Panels + Autorole
  verification.py    Verifizierung mit Rechenaufgabe
  leveling.py        XP, /rank, /rangliste, Belohnungen
  games/             Minigames
data/convo.json      Chat-Trigger und Antworten – hier einfach erweitern
assets/join.gif      Willkommens-GIF
```

**Join-Ablauf:** `on_member_join` → `antiraid.py` prüft Lockdown, Raid-Modus und Kontoalter →
bei Erfolg feuert der Bot das eigene Event `member_accepted` → Willkommensnachricht + Autorole.
Neue Join-Features also auf `on_member_accepted` hören, nicht auf `on_member_join`.

Neues Feature = neue Datei in `cogs/` mit einer `async def setup(bot)`-Funktion. Fertig.

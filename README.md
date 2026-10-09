# discordbot

Kleiner Discord-Bot mit Python & [discord.py](https://discordpy.readthedocs.io/) – Ticket-System, Audit-Log, Willkommensnachrichten, Moderation, Minigames und ein bisschen Chat-Persönlichkeit.

## Features

| Bereich | Command / Trigger | Wer | Was passiert |
|---|---|---|---|
| ⚙️ Einstellungen | `/config auditlog`, `/config willkommen`, `/config tickets`, `/config anzeigen` | Server verwalten | Kanäle, Support-Rolle und Kategorie pro Server festlegen (bleibt nach Neustart gespeichert) |
| 🎫 Tickets | `/ticketpanel <kanal>` | Server verwalten | Postet ein Panel mit „Allgemeine Anfrage“ / „Technische Unterstützung“ |
| | Buttons im Ticket | Support / Ersteller | Beanspruchen, Schließen → Verlauf als `.txt` ins Archiv |
| 📋 Audit-Log | automatisch | – | Joins, Leaves, gelöschte und bearbeitete Nachrichten (mit Wort-Diff) |
| 👋 Willkommen | automatisch | – | Embed + GIF für neue Mitglieder |
| 🧹 Moderation | `/clear <1-100>` | Nachrichten verwalten | Löscht die letzten Nachrichten |
| | `/say <text>` | Nachrichten verwalten | Bot schreibt eine Nachricht (ohne @everyone-Pings) |
| | `/embed [text] [bild]` | alle | Text/Bild als Embed posten |
| 🎮 Games | `/rps` | alle | Schere, Stein, Papier |
| | `/zahlenraten` | alle | Zahl 1–100 erraten, `exit` bricht ab |
| | `/speed` | alle | Tipp-Speedtest mit WPM & Genauigkeit (Copy-Paste wird erkannt) |
| 💬 Chat | „gumo“, „guna“, „mahlzeit“ … | alle | Begrüßungen |
| | @Bot / Reply an den Bot | alle | Antworten auf „wie gehts“, „was machst du“, „erzähl mir einen witz“ … (siehe `data/convo.json`) |

## Setup

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env             # Token eintragen
python main.py
```

Im [Developer Portal](https://discord.com/developers/applications) unter **Bot → Privileged Gateway Intents** müssen **Server Members** und **Message Content** an sein.

Beim Einladen braucht der Bot die Scopes `bot` + `applications.commands` und mindestens: Kanäle verwalten, Rollen verwalten, Nachrichten verwalten, Nachrichten senden, Dateien anhängen, Nachrichtenverlauf lesen.

**Tipp zum Entwickeln:** `DEV_GUILD_ID` in der `.env` setzen – dann sind Slash-Commands auf diesem Server sofort da statt nach bis zu einer Stunde.

## Struktur

```
main.py              Einstiegspunkt
core/
  bot.py             Bot-Klasse, lädt alle Cogs automatisch, Fehlerbehandlung
  config.py          .env + Pfade
  storage.py         Einstellungen pro Server → data/settings.json
cogs/                Jede Datei = ein Feature, wird automatisch geladen
  games/             Minigames
data/convo.json      Chat-Trigger und Antworten – hier einfach erweitern
assets/join.gif      Willkommens-GIF
```

Neues Feature = neue Datei in `cogs/` mit einer `async def setup(bot)`-Funktion. Fertig.

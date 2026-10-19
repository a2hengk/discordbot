"""Einstellungen pro Server – jetzt in SQLite (Tabelle guild_settings) statt settings.json.

Die API ist dieselbe wie vorher, damit die bestehenden Cogs nicht umgebaut werden müssen:
- get()/guild() lesen synchron aus einem RAM-Cache (schnell, kein await nötig)
- set()/save() schreiben in die Datenbank

Jeder Wert wird als JSON gespeichert, daher gehen auch Listen/Dicts (z.B. offene Tickets).
Beim ersten Start wird eine alte data/settings.json einmalig importiert.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from core.db import Database

log = logging.getLogger(__name__)

UPSERT = """
    INSERT INTO guild_settings (guild_id, key, value) VALUES (?, ?, ?)
    ON CONFLICT (guild_id, key) DO UPDATE SET value = excluded.value
"""


class GuildStorage:
    def __init__(self, db: Database):
        self.db = db
        self._data: dict[int, dict[str, Any]] = {}

    async def load(self, legacy_json: Path | None = None) -> None:
        for row in await self.db.fetchall("SELECT guild_id, key, value FROM guild_settings"):
            self._data.setdefault(row["guild_id"], {})[row["key"]] = json.loads(row["value"])

        if legacy_json and legacy_json.exists():
            await self._import_legacy(legacy_json)

    async def _import_legacy(self, path: Path) -> None:
        try:
            legacy: dict[str, dict[str, Any]] = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            log.exception("Alte settings.json konnte nicht gelesen werden – Import übersprungen.")
            return
        for guild_id, values in legacy.items():
            target = self._data.setdefault(int(guild_id), {})
            for key, value in values.items():
                target.setdefault(key, value)  # DB gewinnt, falls schon was drin ist
        await self.save()
        path.rename(path.with_suffix(".json.migrated"))
        log.info("settings.json in die Datenbank übernommen (alte Datei → settings.json.migrated)")

    def guild(self, guild_id: int) -> dict[str, Any]:
        return self._data.setdefault(guild_id, {})

    def get(self, guild_id: int, key: str, default: Any = None) -> Any:
        return self.guild(guild_id).get(key, default)

    async def set(self, guild_id: int, key: str, value: Any) -> None:
        if value is None:
            self.guild(guild_id).pop(key, None)
            await self.db.execute("DELETE FROM guild_settings WHERE guild_id = ? AND key = ?", (guild_id, key))
        else:
            self.guild(guild_id)[key] = value
            await self.db.execute(UPSERT, (guild_id, key, json.dumps(value, ensure_ascii=False)))

    async def save(self) -> None:
        """Schreibt alles aus dem Cache zurück – für Cogs, die Dicts direkt verändern (Tickets)."""
        rows = [
            (guild_id, key, json.dumps(value, ensure_ascii=False))
            for guild_id, values in self._data.items()
            for key, value in values.items()
        ]
        await self.db.executemany(UPSERT, rows)
        # Keys, die im Cache entfernt wurden, auch in der DB löschen
        for guild_id, values in self._data.items():
            keys = list(values)
            placeholders = ",".join("?" * len(keys)) or "''"
            await self.db.execute(
                f"DELETE FROM guild_settings WHERE guild_id = ? AND key NOT IN ({placeholders})",
                (guild_id, *keys),
            )

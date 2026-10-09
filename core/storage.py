"""Kleiner JSON-Store für Einstellungen pro Server.

Vorher lagen Audit-Log-Kanal, Ticket-Kanäle usw. nur im RAM und waren nach
jedem Neustart weg. Hier landen sie in data/settings.json.
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)


class GuildStorage:
    def __init__(self, path: Path):
        self.path = path
        self._lock = asyncio.Lock()
        self._data: dict[str, dict[str, Any]] = self._load()

    def _load(self) -> dict[str, dict[str, Any]]:
        if not self.path.exists():
            return {}
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            log.exception("settings.json konnte nicht gelesen werden – starte leer.")
            return {}

    def _write(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self._data, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self.path)  # atomar, damit die Datei nie halb geschrieben ist

    def guild(self, guild_id: int) -> dict[str, Any]:
        return self._data.setdefault(str(guild_id), {})

    def get(self, guild_id: int, key: str, default: Any = None) -> Any:
        return self.guild(guild_id).get(key, default)

    async def set(self, guild_id: int, key: str, value: Any) -> None:
        async with self._lock:
            if value is None:
                self.guild(guild_id).pop(key, None)
            else:
                self.guild(guild_id)[key] = value
            self._write()

    async def save(self) -> None:
        async with self._lock:
            self._write()

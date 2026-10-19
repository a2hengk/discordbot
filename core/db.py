"""SQLite-Datenbank über aiosqlite.

SQLite ist eine komplette SQL-Datenbank in EINER Datei (data/bot.db) – kein Server,
nichts zu installieren. aiosqlite ist nur ein async-Wrapper drumherum, damit
Datenbankzugriffe den Bot nicht blockieren (discord.py läuft in einer asyncio-Loop,
ein normales sqlite3-Query würde die ganze Loop kurz anhalten).

Schema-Änderungen laufen über MIGRATIONS: SQLite merkt sich in `PRAGMA user_version`,
welche Migration zuletzt lief. Neue Tabelle/Spalte? → einfach einen Eintrag hinten
an MIGRATIONS anhängen, niemals alte Einträge ändern.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Iterable

import aiosqlite

log = logging.getLogger(__name__)

MIGRATIONS: list[str] = [
    # 1 – Grundschema
    """
    CREATE TABLE guild_settings (
        guild_id INTEGER NOT NULL,
        key      TEXT    NOT NULL,
        value    TEXT    NOT NULL,          -- JSON
        PRIMARY KEY (guild_id, key)
    );

    CREATE TABLE mod_cases (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        guild_id     INTEGER NOT NULL,
        user_id      INTEGER NOT NULL,
        moderator_id INTEGER NOT NULL,
        action       TEXT    NOT NULL,      -- warn, timeout, untimeout, kick, ban, unban, automod
        reason       TEXT,
        duration_s   INTEGER,
        created_at   INTEGER NOT NULL,      -- Unix-Zeit
        active       INTEGER NOT NULL DEFAULT 1
    );
    CREATE INDEX idx_mod_cases_user ON mod_cases (guild_id, user_id);

    CREATE TABLE role_panels (
        message_id  INTEGER PRIMARY KEY,
        guild_id    INTEGER NOT NULL,
        channel_id  INTEGER NOT NULL,
        mode        TEXT    NOT NULL,       -- buttons | dropdown
        title       TEXT    NOT NULL,
        description TEXT
    );
    CREATE TABLE role_panel_entries (
        message_id INTEGER NOT NULL REFERENCES role_panels (message_id) ON DELETE CASCADE,
        role_id    INTEGER NOT NULL,
        label      TEXT    NOT NULL,
        emoji      TEXT,
        position   INTEGER NOT NULL,
        PRIMARY KEY (message_id, role_id)
    );

    CREATE TABLE levels (
        guild_id INTEGER NOT NULL,
        user_id  INTEGER NOT NULL,
        xp       INTEGER NOT NULL DEFAULT 0,
        level    INTEGER NOT NULL DEFAULT 0,
        messages INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY (guild_id, user_id)
    );
    CREATE INDEX idx_levels_xp ON levels (guild_id, xp DESC);

    CREATE TABLE level_rewards (
        guild_id INTEGER NOT NULL,
        level    INTEGER NOT NULL,
        role_id  INTEGER NOT NULL,
        PRIMARY KEY (guild_id, level)
    );

    CREATE TABLE lockdown_channels (
        guild_id   INTEGER NOT NULL,
        channel_id INTEGER NOT NULL,
        previous   TEXT    NOT NULL,        -- allow | deny | none (vorheriger send_messages-Wert)
        PRIMARY KEY (guild_id, channel_id)
    );
    """,
]


class Database:
    def __init__(self, path: Path):
        self.path = path
        self._conn: aiosqlite.Connection | None = None

    @property
    def conn(self) -> aiosqlite.Connection:
        if self._conn is None:
            raise RuntimeError("Datenbank ist nicht verbunden – erst connect() aufrufen.")
        return self._conn

    async def connect(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = await aiosqlite.connect(self.path)
        self._conn.row_factory = aiosqlite.Row          # Zeilen wie dicts: row["xp"]
        await self._conn.execute("PRAGMA journal_mode = WAL")   # Lesen blockiert Schreiben nicht
        await self._conn.execute("PRAGMA foreign_keys = ON")    # ON DELETE CASCADE aktivieren
        await self._migrate()

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None

    async def _migrate(self) -> None:
        async with self.conn.execute("PRAGMA user_version") as cur:
            (version,) = await cur.fetchone()
        for number, sql in enumerate(MIGRATIONS[version:], start=version + 1):
            log.info("Datenbank-Migration %d wird ausgeführt", number)
            await self.conn.executescript(f"BEGIN; {sql}; PRAGMA user_version = {number}; COMMIT;")

    # ---------- kleine Helfer, damit Cogs kein Cursor-Handling brauchen ---------- #

    async def execute(self, sql: str, params: Iterable[Any] = ()) -> int:
        """Schreibender Query. Gibt lastrowid zurück (praktisch für INSERT)."""
        cur = await self.conn.execute(sql, tuple(params))
        await self.conn.commit()
        row_id = cur.lastrowid or 0
        await cur.close()
        return row_id

    async def executemany(self, sql: str, rows: Iterable[Iterable[Any]]) -> None:
        await self.conn.executemany(sql, [tuple(r) for r in rows])
        await self.conn.commit()

    async def fetchone(self, sql: str, params: Iterable[Any] = ()) -> aiosqlite.Row | None:
        async with self.conn.execute(sql, tuple(params)) as cur:
            return await cur.fetchone()

    async def fetchall(self, sql: str, params: Iterable[Any] = ()) -> list[aiosqlite.Row]:
        async with self.conn.execute(sql, tuple(params)) as cur:
            return list(await cur.fetchall())

    async def fetchval(self, sql: str, params: Iterable[Any] = (), default: Any = None) -> Any:
        row = await self.fetchone(sql, params)
        return row[0] if row is not None else default

"""Zentrale Konfiguration: Pfade und Werte aus der .env."""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

log = logging.getLogger(__name__)

ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"
ASSETS_DIR = ROOT_DIR / "assets"
SETTINGS_FILE = DATA_DIR / "settings.json"
CONVO_FILE = DATA_DIR / "convo.json"


@dataclass(frozen=True)
class Config:
    token: str
    dev_guild_id: int | None


def _legacy_token() -> str | None:
    """Fallback für das alte config.json-Setup, damit nichts sofort bricht."""
    legacy = ROOT_DIR / "config.json"
    if not legacy.exists():
        return None
    try:
        token = json.loads(legacy.read_text(encoding="utf-8")).get("discord_token")
    except (OSError, json.JSONDecodeError):
        return None
    if token:
        log.warning("Token kommt noch aus config.json – bitte nach .env (DISCORD_TOKEN) umziehen.")
    return token


def load_config() -> Config:
    load_dotenv(ROOT_DIR / ".env")

    token = os.getenv("DISCORD_TOKEN") or _legacy_token()
    if not token:
        raise SystemExit("DISCORD_TOKEN fehlt. Lege eine .env an (siehe .env.example).")

    dev_guild = os.getenv("DEV_GUILD_ID")
    return Config(token=token, dev_guild_id=int(dev_guild) if dev_guild else None)

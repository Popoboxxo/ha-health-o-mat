"""JSON-Backup (alle Personen/Datensätze/Zeiträume) nach ``/config/health_o_mat_export/``.

Nutzt ausschließlich ``store.raw_data()`` — kein Parallel-Datenmodell. Das
Dokument ist versioniert (``format``/``version``), damit ein späterer Restore
es sicher validieren kann. Geschrieben wird nur in den privaten Export-Ordner,
nie nach ``/config/www`` (Datenschutzregel).
"""

from __future__ import annotations

import copy
import json
import logging
import os
from datetime import datetime

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.util import dt as dt_util

from .store import HealthOMatStore

_LOGGER = logging.getLogger(__name__)

BACKUP_DIR_NAME = "health_o_mat_export"
BACKUP_FORMAT = "health_o_mat_backup"
BACKUP_VERSION = 1


def build_backup_document(raw_data: dict, created: datetime) -> dict:
    """Versioniertes Backup-Dokument aus den rohen Store-Daten (HA-frei).

    Tiefe Kopie der ``entries``, damit ein späteres Verändern des Dokuments den
    laufenden Store nicht berührt. ``raw_data`` ohne ``entries`` → leeres
    ``entries`` (kein Absturz bei Erstanlage).
    """
    entries = raw_data.get("entries", {}) if isinstance(raw_data, dict) else {}
    return {
        "format": BACKUP_FORMAT,
        "version": BACKUP_VERSION,
        "created": created.isoformat(),
        "entries": copy.deepcopy(entries),
    }


def backup_filename(created: datetime) -> str:
    """Dateiname mit Zeitstempel: ``health_o_mat_backup_<YYYYMMDD-HHMMSS>.json``."""
    return f"health_o_mat_backup_{created.strftime('%Y%m%d-%H%M%S')}.json"


async def async_backup(hass: HomeAssistant, store: HealthOMatStore) -> str:
    """Service ``health_o_mat.backup`` — schreibt den Voll-Export als JSON.

    Alle Personen und Datensätze, alle Zeiträume; Quelle ist ``raw_data()``.
    """
    if store is None:
        raise ServiceValidationError("Health-O-Mat-Speicher nicht verfügbar")

    now = dt_util.now()
    document = build_backup_document(store.raw_data(), now)
    export_dir = hass.config.path(BACKUP_DIR_NAME)
    path = os.path.join(export_dir, backup_filename(now))

    def _write() -> None:
        os.makedirs(export_dir, exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="") as fh:
            json.dump(document, fh, ensure_ascii=False, indent=2)

    await hass.async_add_executor_job(_write)

    await hass.services.async_call(
        "persistent_notification",
        "create",
        {"title": "HA Health-O-Mat Backup", "message": f"Backup geschrieben:\n{path}"},
        blocking=False,
    )
    return path

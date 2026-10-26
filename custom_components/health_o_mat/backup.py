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
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.util import dt as dt_util

from .store import HealthOMatStore

_LOGGER = logging.getLogger(__name__)

BACKUP_DIR_NAME = "health_o_mat_export"
BACKUP_FORMAT = "health_o_mat_backup"
BACKUP_VERSION = 2


def _list_counts(items: Any) -> dict[str, int]:
    """Zähler einer Eintragsliste: gesamt / aktiv / gelöscht (voided)."""
    if not isinstance(items, list):
        return {"total": 0, "active": 0, "voided": 0}
    total = sum(1 for item in items if isinstance(item, dict))
    voided = sum(1 for item in items if isinstance(item, dict) and item.get("voided_at"))
    return {"total": total, "active": total - voided, "voided": voided}


def _entry_counts(entry: Any) -> dict[str, dict[str, int]]:
    """Zähler je Person: gesamt / aktiv / gelöscht (voided).

    Quelle sind die v4-Listen (``drinks``/``readings``/``wellbeing_entries``).
    Ein Eintrag ohne ``voided_at`` gilt als aktiv. Für Bestände ohne
    ``wellbeing_entries`` (vor v4) wird das Legacy-Wohlbefinden gezählt:
    Historie + aktueller Wert, alle aktiv.
    """
    data = entry if isinstance(entry, dict) else {}

    if "wellbeing_entries" in data:
        wellbeing = _list_counts(data.get("wellbeing_entries"))
    else:
        legacy_total = 0
        if isinstance(data.get("wellbeing"), dict) and data["wellbeing"].get("status"):
            legacy_total += 1
        history = data.get("wellbeing_history")
        if isinstance(history, list):
            legacy_total += sum(1 for item in history if isinstance(item, dict))
        wellbeing = {"total": legacy_total, "active": legacy_total, "voided": 0}

    return {
        "drinks": _list_counts(data.get("drinks")),
        "readings": _list_counts(data.get("readings")),
        "wellbeing": wellbeing,
    }


def _archive_counts(archive_data: dict | None) -> dict[str, Any]:
    """Zähler des Archiv-Stores (drinks/readings) je Person."""
    if not isinstance(archive_data, dict):
        return {}
    entries = archive_data.get("entries", {})
    if not isinstance(entries, dict):
        return {}
    counts: dict[str, Any] = {}
    for entry_id, entry in entries.items():
        data = entry if isinstance(entry, dict) else {}
        counts[str(entry_id)] = {
            "drinks": _list_counts(data.get("drinks")),
            "readings": _list_counts(data.get("readings")),
        }
    return counts


def build_backup_document(
    raw_data: dict, created: datetime, archive_data: dict | None = None
) -> dict:
    """Versioniertes Backup-Dokument aus den rohen Store-Daten (HA-frei).

    Tiefe Kopie der ``entries``, damit ein späteres Verändern des Dokuments den
    laufenden Store nicht berührt. ``raw_data`` ohne ``entries`` → leeres
    ``entries`` (kein Absturz bei Erstanlage).

    v2 ergänzt (additiv, ``format``/``version``/``created``/``entries`` bleiben):

    - ``schema``: Schema-Stufe des Stores (``None``, wenn nicht vorhanden).
    - ``persons``: ``{entry_id: Anzeigename}`` — die Entry-ID ist der stabile
      Schlüssel, der Name nur Anzeige (Personen-Identität über Instanzen
      hinweg klärt der Restore).
    - ``counts``: je Person ``{drinks, readings, wellbeing}`` mit
      ``{"total", "active", "voided"}``. Gelöschte (voided) Einträge werden
      separat ausgewiesen; ``total`` enthält sie mit.
    - ``archive_entries``/``archive_schema``/``archive_counts``: Inhalt des
      separaten Retention-Archivs, damit ein Restore auch die archivierten
      Zeiträume abdeckt. Ohne Archiv leer (abwärtskompatibel, additiv).
    """
    entries = raw_data.get("entries", {}) if isinstance(raw_data, dict) else {}
    persons: dict[str, Any] = {}
    counts: dict[str, Any] = {}
    for entry_id, entry in entries.items():
        data = entry if isinstance(entry, dict) else {}
        persons[str(entry_id)] = data.get("person") or ""
        counts[str(entry_id)] = _entry_counts(data)
    archive_entries = archive_data.get("entries", {}) if isinstance(archive_data, dict) else {}
    return {
        "format": BACKUP_FORMAT,
        "version": BACKUP_VERSION,
        "schema": raw_data.get("schema") if isinstance(raw_data, dict) else None,
        "created": created.isoformat(),
        "persons": persons,
        "counts": counts,
        "entries": copy.deepcopy(entries),
        "archive_schema": (archive_data.get("schema") if isinstance(archive_data, dict) else None),
        "archive_counts": _archive_counts(archive_data),
        "archive_entries": copy.deepcopy(archive_entries),
    }


def backup_filename(created: datetime) -> str:
    """Dateiname mit Zeitstempel: ``health_o_mat_backup_<YYYYMMDD-HHMMSS>.json``."""
    return f"health_o_mat_backup_{created.strftime('%Y%m%d-%H%M%S')}.json"


async def async_backup(
    hass: HomeAssistant,
    store: HealthOMatStore,
    archive_store: HealthOMatStore | None = None,
) -> str:
    """Service ``health_o_mat.backup`` — schreibt den Voll-Export als JSON.

    Alle Personen und Datensätze, alle Zeiträume; Quelle ist ``raw_data()``.
    ``archive_store`` (Retention) wird — falls vorhanden — mit aufgenommen,
    damit ein späterer Restore auch archivierte Zeiträume abdeckt.
    """
    if store is None:
        raise ServiceValidationError("Health-O-Mat-Speicher nicht verfügbar")

    now = dt_util.now()
    document = build_backup_document(
        store.raw_data(),
        now,
        archive_store.raw_data() if archive_store is not None else None,
    )
    path = await async_write_backup_document(hass, document, prefix="backup")

    await hass.services.async_call(
        "persistent_notification",
        "create",
        {"title": "HA Health-O-Mat Backup", "message": f"Backup geschrieben:\n{path}"},
        blocking=False,
    )
    return path


async def async_write_backup_document(
    hass: HomeAssistant, document: dict, *, prefix: str = "pre_restore"
) -> str:
    """Schreibt ein fertiges Backup-Dokument in den Export-Ordner (ohne Notification).

    Für das Pre-Restore-Sicherheitsbackup: es darf keinen Notification-Spam
    erzeugen, muss aber vor jeder Änderung auf der Platte liegen.
    """
    now = dt_util.now()
    stamp = now.strftime("%Y%m%d-%H%M%S")
    name = f"health_o_mat_{prefix}_{stamp}.json"
    export_dir = hass.config.path(BACKUP_DIR_NAME)
    path = os.path.join(export_dir, name)

    def _write() -> None:
        os.makedirs(export_dir, exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="") as fh:
            json.dump(document, fh, ensure_ascii=False, indent=2)

    await hass.async_add_executor_job(_write)
    return path

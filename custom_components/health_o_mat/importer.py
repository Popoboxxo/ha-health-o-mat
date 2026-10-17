"""CSV-Import (REQ-HOM-007): toleranter Import aus ``/config/health_o_mat_import/``.

Datenschutzregel (HART): gelesen wird ausschließlich aus dem privaten
Import-Verzeichnis — niemals aus dem öffentlich erreichbaren ``www``.
:safe_import_path: ist reine Logik (HA-frei, testbar) und weist absolute Pfade,
Traversal (``..``) und Symlink-Escapes zurück.

Das Parsen/Planen ist bewusst HA-frei gehalten (``parse_csv_text`` /
``plan_import``), damit Toleranz und Duplikat-Schutz ohne Home Assistant
getestet werden können. Nur ``async_import_csv`` berührt HA (Datei-I/O,
Store, Notification).
"""

from __future__ import annotations

import csv
import io
import logging
import os
import re
from dataclasses import dataclass, field
from datetime import datetime

from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError

from .const import MAX_AMOUNT_ML, NO_TYPE_LABEL
from .entity import signal_refresh
from .store import HealthOMatStore

_LOGGER = logging.getLogger(__name__)

IMPORT_DIR_NAME = "health_o_mat_import"

# Kopfzeilen-Erkennung (tolerant: fehlender/abweichender Header wird toleriert).
_HEADER_FIRST = {"datum", "date", "zeitstempel", "timestamp", "zeit", "person"}
_DRINKS_HINTS = {"getraenk", "getränk", "drink", "menge_ml", "menge", "quelle", "ml"}
_BP_HINTS = {
    "systolisch",
    "systolic",
    "diastolisch",
    "diastolic",
    "sys",
    "dia",
    "puls",
    "pulse",
    "notiz",
    "note",
}
_DRIVE_RE = re.compile(r"^[A-Za-z]:")

DATASETS = ("drinks", "blood_pressure")


def safe_import_path(config_dir: str, filename: str) -> str:
    """Löst einen Import-Dateinamen auf und prüft die Whitelist (HA-frei).

    Erlaubt ist NUR ein relativer Pfad unterhalb von
    ``<config_dir>/health_o_mat_import/``. Abgelehnt werden leere Namen,
    absolute Pfade (``/...``, ``\\...``, ``C:...``), Traversal-Komponenten
    (``..``) und Symlink-Escapes (das Ziel läge nach ``realpath`` außerhalb
    des Import-Ordners).

    Returns:
        Absoluter, real aufgelöster Pfad unterhalb des Import-Ordners.

    Raises:
        ValueError: wenn der Pfad die Whitelist verletzt.
    """
    if not isinstance(filename, str) or not filename.strip():
        raise ValueError("Dateiname fehlt")
    name = filename.strip()
    if "\x00" in name:
        raise ValueError("Ungültiger Dateiname")
    if name.startswith(("/", "\\")) or _DRIVE_RE.match(name):
        raise ValueError("Absoluter Pfad ist nicht erlaubt")
    base = os.path.realpath(os.path.join(config_dir, IMPORT_DIR_NAME))
    candidate = os.path.realpath(os.path.join(base, name))
    if candidate == base:
        raise ValueError("Ungültiger Dateiname")
    try:
        contained = os.path.commonpath([base, candidate]) == base
    except ValueError:  # unterschiedliche Laufwerke (Windows)
        contained = False
    if not contained:
        raise ValueError("Pfad verlässt das Import-Verzeichnis")
    return candidate


def _norm_ts(raw: object) -> str | None:
    """ISO-Zeitstempel normalisieren (``datetime.isoformat()``); None bei Murks."""
    if not isinstance(raw, str):
        return None
    try:
        return datetime.fromisoformat(raw.strip()).isoformat()
    except ValueError:
        return None


def _join_ts(date_s: str, time_s: str) -> str | None:
    """Getränke-Format ``datum`` + ``uhrzeit`` → ISO-Zeitstempel."""
    date_s, time_s = date_s.strip(), time_s.strip()
    if time_s:
        return _norm_ts(f"{date_s}T{time_s}")
    return _norm_ts(date_s)


def _detect_kind(rows: list[list[str]]) -> str:
    """Datensatz-Typ aus den Datenzeilen ableiten (Header fehlt/abweichend)."""
    for cells in rows[:5]:
        if len(cells) < 4:
            continue
        first = cells[0]
        if "T" in first and _norm_ts(first) is not None:
            return "blood_pressure"  # voller ISO-Zeitstempel in Spalte 1
        if "-" in first and len(cells) >= 5:
            return "drinks"
    return "drinks"


def parse_csv_text(text: str) -> tuple[list[list[str]], str | None]:
    """CSV-Text → Datenzeilen plus erkannter Datensatz-Typ.

    Toleriert UTF-8-BOM, ``#``-Kommentarzeilen, Leerzeilen und einen
    fehlenden bzw. abweichenden Header (Semikolon-getrennt).
    """
    if text.startswith("\ufeff"):
        text = text[1:]
    rows: list[list[str]] = []
    kind: str | None = None
    for raw in csv.reader(io.StringIO(text), delimiter=";"):
        cells = [c.strip() for c in raw]
        if not cells or all(c == "" for c in cells):
            continue
        first = cells[0].lstrip("\ufeff").lower()
        if first.startswith("#"):
            continue
        joined = {c.lower() for c in cells}
        is_header = first in _HEADER_FIRST and bool(joined & (_DRINKS_HINTS | _BP_HINTS))
        if is_header:
            if kind is None:
                kind = "blood_pressure" if joined & _BP_HINTS else "drinks"
            continue  # Kopfzeile
        rows.append(cells)
    return rows, kind


def _to_int(raw: str) -> int:
    """Zahl tolerant lesen: ``250``, ``250.0``, ``250,0`` → 250."""
    return int(float(raw.strip().replace(",", ".")))


def _parse_drink_row(cells: list[str]) -> dict | str:
    """Getränke-Zeile → Record-Dict oder Fehlermeldung (str)."""
    if len(cells) < 5:
        return f"Getränk-Zeile mit zu wenigen Spalten: {';'.join(cells)}"
    ts = _join_ts(cells[0], cells[1] if len(cells) > 1 else "")
    if ts is None:
        return f"Ungültiger Zeitstempel: {' '.join(cells[:2])}"
    try:
        ml = _to_int(cells[4])
    except ValueError:
        return f"Ungültige Menge: {cells[4]!r}"
    if ml <= 0 or ml > MAX_AMOUNT_ML:
        return f"Menge außerhalb des Bereichs: {ml}"
    return {
        "ts": ts,
        "ml": ml,
        "type": cells[3].strip() or NO_TYPE_LABEL,
        "src": cells[5].strip() if len(cells) > 5 else "",
    }


def _parse_reading_row(cells: list[str]) -> dict | str:
    """Blutdruck-Zeile → Record-Dict oder Fehlermeldung (str)."""
    if len(cells) < 4:
        return f"Blutdruck-Zeile mit zu wenigen Spalten: {';'.join(cells)}"
    ts = _norm_ts(cells[0])
    if ts is None:
        return f"Ungültiger Zeitstempel: {cells[0]!r}"
    try:
        sys_ = _to_int(cells[2])
        dia = _to_int(cells[3])
    except ValueError:
        return f"Ungültiger Blutdruckwert: {';'.join(cells[2:4])}"
    if not (0 < sys_ <= 1000 and 0 < dia <= 1000):
        return f"Blutdruckwert außerhalb des Bereichs: {sys_}/{dia}"
    pulse: int | None = None
    if len(cells) > 4 and cells[4].strip():
        try:
            pulse = _to_int(cells[4])
        except ValueError:
            return f"Ungültiger Puls: {cells[4]!r}"
        if pulse <= 0:
            pulse = None
    return {
        "ts": ts,
        "sys": sys_,
        "dia": dia,
        "pulse": pulse,
        "note": cells[5].strip() if len(cells) > 5 else "",
        "src": "import",
    }


@dataclass
class ImportPlan:
    """Ergebnis der reinen Import-Planung (Records + Zähler)."""

    drinks: list[dict] = field(default_factory=list)
    readings: list[dict] = field(default_factory=list)
    skipped: int = 0
    rejected: int = 0
    errors: list[str] = field(default_factory=list)

    @property
    def imported(self) -> int:
        return len(self.drinks) + len(self.readings)


def _existing_drink_keys(existing: list[dict]) -> set[tuple[str, int]]:
    keys: set[tuple[str, int]] = set()
    for item in existing:
        if not isinstance(item, dict):
            continue
        ts = _norm_ts(item.get("ts")) or str(item.get("ts"))
        try:
            keys.add((ts, int(item.get("ml", 0))))
        except (TypeError, ValueError):
            continue
    return keys


def _existing_reading_keys(existing: list[dict]) -> set[tuple[str, int, int]]:
    keys: set[tuple[str, int, int]] = set()
    for item in existing:
        if not isinstance(item, dict):
            continue
        ts = _norm_ts(item.get("ts")) or str(item.get("ts"))
        try:
            keys.add((ts, int(item.get("sys", 0)), int(item.get("dia", 0))))
        except (TypeError, ValueError):
            continue
    return keys


def plan_import(
    text: str,
    dataset: str,
    existing_drinks: list[dict] | None = None,
    existing_readings: list[dict] | None = None,
) -> ImportPlan:
    """Plant den Import HA-frei: parst, prüft und filtert Duplikate.

    ``dataset`` ist ``drinks``, ``blood_pressure`` oder ``all`` (auto-erkennen).
    Duplikate werden über ``(ts, ml)`` bzw. ``(ts, sys, dia)`` erkannt —
    bestehende Einträge und Wiederholungen innerhalb der Datei zählen als
    ``skipped``, unlesbare Zeilen als ``rejected``.
    """
    rows, header_kind = parse_csv_text(text)
    resolved = dataset
    if dataset == "all":
        resolved = header_kind or _detect_kind(rows)

    plan = ImportPlan()
    if resolved == "blood_pressure":
        seen = _existing_reading_keys(existing_readings or [])
        for cells in rows:
            record = _parse_reading_row(cells)
            if isinstance(record, str):
                plan.rejected += 1
                plan.errors.append(record)
                continue
            key = (record["ts"], record["sys"], record["dia"])
            if key in seen:
                plan.skipped += 1
                continue
            seen.add(key)
            plan.readings.append(record)
    else:
        seen_drinks = _existing_drink_keys(existing_drinks or [])
        for cells in rows:
            record = _parse_drink_row(cells)
            if isinstance(record, str):
                plan.rejected += 1
                plan.errors.append(record)
                continue
            key = (record["ts"], record["ml"])
            if key in seen_drinks:
                plan.skipped += 1
                continue
            seen_drinks.add(key)
            plan.drinks.append(record)
    return plan


async def async_import_csv(
    hass: HomeAssistant,
    store: HealthOMatStore,
    entry_id: str,
    call: ServiceCall,
) -> dict:
    """Service ``health_o_mat.import_csv`` — liest und übernimmt eine CSV-Datei.

    Wiederherstellung läuft über die bestehenden Store-Pfade
    (``add_drink`` / ``add_reading``), danach ``signal_refresh`` und eine
    ``persistent_notification`` mit der Zusammenfassung. Rückgabe ist ein
    strukturiertes Ergebnis (für WS/UI und Tests).
    """
    if store is None:
        raise ServiceValidationError("Health-O-Mat-Speicher nicht verfügbar")

    filename = call.data.get("filename") or ""
    dataset = call.data.get("dataset", "all")

    try:
        path = safe_import_path(hass.config.config_dir, filename)
    except ValueError as err:
        raise ServiceValidationError(str(err)) from err

    def _read() -> str:
        with open(path, encoding="utf-8-sig", newline="") as fh:
            return fh.read()

    try:
        text = await hass.async_add_executor_job(_read)
    except FileNotFoundError as err:
        raise ServiceValidationError(f"Import-Datei nicht gefunden: {filename}") from err
    except OSError as err:
        raise ServiceValidationError(f"Import-Datei nicht lesbar: {filename}") from err

    entry = store.entry(entry_id)
    plan = plan_import(text, dataset, entry.get("drinks", []), entry.get("readings", []))

    for drink in plan.drinks:
        await store.add_drink(entry_id, drink["ts"], drink["ml"], drink["type"], drink["src"])
    for reading in plan.readings:
        await store.add_reading(
            entry_id,
            reading["ts"],
            reading["sys"],
            reading["dia"],
            reading["pulse"],
            reading["note"],
            reading["src"],
        )
    signal_refresh(hass, entry_id)

    summary = (
        f"Import '{os.path.basename(path)}': "
        f"{plan.imported} übernommen, {plan.skipped} übersprungen (Duplikat), "
        f"{plan.rejected} ungültig."
    )
    await hass.services.async_call(
        "persistent_notification",
        "create",
        {"title": "HA Health-O-Mat Import", "message": summary},
        blocking=False,
    )
    return {
        "imported": plan.imported,
        "skipped": plan.skipped,
        "rejected": plan.rejected,
        "errors": plan.errors,
    }

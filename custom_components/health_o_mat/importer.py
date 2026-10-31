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

from .backup import BACKUP_DIR_NAME
from .const import (
    DEFAULT_AUDIT_LIMIT,
    DOMAIN,
    MAX_AMOUNT_ML,
    NO_TYPE_LABEL,
    OPTION_LAB_CUSTOM_MARKERS,
)
from .entity import signal_refresh
from .logic import convert_lab_value, resolve_lab_marker
from .store import HealthOMatStore

_LOGGER = logging.getLogger(__name__)

IMPORT_DIR_NAME = "health_o_mat_import"
# Restore-Backups dürfen aus Import- UND Export-Ordner gelesen werden: die
# Integration schreibt Backup/Pre-Restore dorthin, die Restore-UI muss sie
# also auch wieder anbieten. Beide Ordner sind privat (nie /config/www).
RESTORE_DIR_NAMES: tuple[str, ...] = (IMPORT_DIR_NAME, BACKUP_DIR_NAME)

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
# Nur eindeutige Spaltennamen: generische Wie "wert"/"einheit" könnten auch
# in fremden Getränke-/Blutdruck-Dateien auftauchen und würden `all` falsch
# routen. Die eigene Laborwert-Kopfzeile ist über diese Keys eindeutig.
_LAB_HINTS = {"marker", "kategorie", "berichts_referenz"}
_DRIVE_RE = re.compile(r"^[A-Za-z]:")

DATASETS = ("drinks", "blood_pressure", "lab_values")


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


def list_import_files(config_dir: str) -> list[str]:
    """JSON-Backup-Dateinamen aus Import- UND Export-Ordner (sortiert).

    Liefert ausschließlich Basisnamen — niemals Pfade. Verzeichnisse,
    Symlinks, versteckte Dateien und Nicht-``.json``-Dateien bleiben außen vor
    (kein Traversal, kein Escape). Ein fehlender Ordner ist kein Fehler,
    sondern eine leere Liste. Der Export-Ordner enthält Backup- und
    Pre-Restore-Dateien, damit sie in der Restore-UI sichtbar sind.
    """
    files: set[str] = set()
    for dir_name in RESTORE_DIR_NAMES:
        base = os.path.realpath(os.path.join(config_dir, dir_name))
        try:
            names = os.listdir(base)
        except OSError:
            continue
        for name in names:
            if name.startswith(".") or not name.lower().endswith(".json"):
                continue
            try:
                path = safe_restore_path(config_dir, name)
            except ValueError:
                continue
            if os.path.islink(os.path.join(base, name)):
                continue
            try:
                if not os.path.isfile(path):
                    continue
            except OSError:  # pragma: no cover - nur bei Race mit dem Dateisystem
                continue
            files.add(name)
    return sorted(files, key=lambda value: (value.lower(), value))


def _restore_candidate(config_dir: str, dir_name: str, name: str) -> str:
    """Kandidatenpfad in einem erlaubten Ordner (realpath, Whitelist)."""
    base = os.path.realpath(os.path.join(config_dir, dir_name))
    candidate = os.path.realpath(os.path.join(base, name))
    if candidate == base:
        raise ValueError("Ungültiger Dateiname")
    try:
        contained = os.path.commonpath([base, candidate]) == base
    except ValueError:  # unterschiedliche Laufwerke (Windows)
        contained = False
    if not contained:
        raise ValueError("Pfad verlässt das Backup-Verzeichnis")
    return candidate


def safe_restore_path(config_dir: str, filename: str) -> str:
    """Löst einen Restore-Dateinamen auf (Import- oder Export-Ordner).

    Nur relative Basisnamen mit ``.json``-Endung sind erlaubt; absolute Pfade,
    Traversal, Symlinks und Nicht-JSON-Dateien werden abgelehnt. Existiert die
    Datei in beiden Ordnern, gewinnt der Import-Ordner (bestehendes Verhalten).
    Ist sie in keinem Ordner vorhanden, wird der Import-Pfad zurückgegeben,
    damit der Aufrufer einen klaren ``FileNotFoundError`` melden kann.

    Raises:
        ValueError: wenn der Name/das Ziel die Whitelist verletzt.
    """
    if not isinstance(filename, str) or not filename.strip():
        raise ValueError("Dateiname fehlt")
    name = filename.strip()
    if "\x00" in name:
        raise ValueError("Ungültiger Dateiname")
    if name.startswith(("/", "\\")) or _DRIVE_RE.match(name):
        raise ValueError("Absoluter Pfad ist nicht erlaubt")
    if "/" in name or "\\" in name or name != os.path.basename(name):
        raise ValueError("Unterordner sind nicht erlaubt")
    if not name.lower().endswith(".json"):
        raise ValueError("Nur JSON-Backups können wiederhergestellt werden")

    candidates: list[str] = []
    for dir_name in RESTORE_DIR_NAMES:
        candidate = _restore_candidate(config_dir, dir_name, name)
        if os.path.islink(os.path.join(config_dir, dir_name, name)):
            raise ValueError("Symbolische Links sind nicht erlaubt")
        candidates.append(candidate)
        try:
            if os.path.isfile(candidate):
                return candidate
        except OSError:  # pragma: no cover - nur bei Race mit dem Dateisystem
            continue
    return candidates[0]


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
        is_header = first in _HEADER_FIRST and bool(
            joined & (_DRINKS_HINTS | _BP_HINTS | _LAB_HINTS)
        )
        if is_header:
            if kind is None:
                if joined & _LAB_HINTS:
                    kind = "lab_values"
                elif joined & _BP_HINTS:
                    kind = "blood_pressure"
                else:
                    kind = "drinks"
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


def _parse_lab_row(cells: list[str]) -> dict | str:
    """Laborwert-Zeile → Record-Dict (noch unaufgelöster `marker_raw`) oder Fehlermeldung.

    Spalten (siehe `exporter.py`): zeitstempel, person, marker, kategorie, wert,
    einheit, eingegeben_als_wert, eingegeben_als_einheit, berichts_referenz.
    Die Marker-Auflösung (Alias/Katalog/Custom) passiert erst in `plan_import`
    — diese Funktion bleibt reine Zeilen-Validierung, analog zu
    `_parse_drink_row`/`_parse_reading_row`.
    """
    if len(cells) < 6:
        return f"Laborwert-Zeile mit zu wenigen Spalten: {';'.join(cells)}"
    ts = _norm_ts(cells[0])
    if ts is None:
        return f"Ungültiger Zeitstempel: {cells[0]!r}"
    marker_raw = cells[2].strip()
    if not marker_raw:
        return f"Laborwert-Zeile ohne Marker: {';'.join(cells)}"
    try:
        value = float(cells[4].strip().replace(",", "."))
    except ValueError:
        return f"Ungültiger Laborwert: {cells[4]!r}"
    unit = cells[5].strip()
    reported_value = value
    if len(cells) > 6 and cells[6].strip():
        try:
            reported_value = float(cells[6].strip().replace(",", "."))
        except ValueError:
            return f"Ungültiger eingegebener Wert: {cells[6]!r}"
    reported_unit = cells[7].strip() if len(cells) > 7 and cells[7].strip() else unit
    report_ref = cells[8].strip() if len(cells) > 8 and cells[8].strip() else None
    return {
        "ts": ts,
        "marker_raw": marker_raw,
        "value": value,
        "unit": unit,
        "reported_value": reported_value,
        "reported_unit": reported_unit,
        "report_ref": report_ref,
    }


@dataclass
class ImportPlan:
    """Ergebnis der reinen Import-Planung (Records + Zähler)."""

    drinks: list[dict] = field(default_factory=list)
    readings: list[dict] = field(default_factory=list)
    lab_readings: list[dict] = field(default_factory=list)
    skipped: int = 0
    rejected: int = 0
    errors: list[str] = field(default_factory=list)

    @property
    def imported(self) -> int:
        return len(self.drinks) + len(self.readings) + len(self.lab_readings)


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


def _existing_lab_keys(existing: list[dict]) -> set[tuple[str, str, float]]:
    """``(ts, marker_key, value)`` — dieselbe Dedup-Logik wie in ``restore.py``."""
    keys: set[tuple[str, str, float]] = set()
    for item in existing:
        if not isinstance(item, dict):
            continue
        ts = _norm_ts(item.get("ts")) or str(item.get("ts"))
        try:
            keys.add((ts, str(item.get("marker_key") or ""), float(item.get("value", 0))))
        except (TypeError, ValueError):
            continue
    return keys


def plan_import(
    text: str,
    dataset: str,
    existing_drinks: list[dict] | None = None,
    existing_readings: list[dict] | None = None,
    existing_lab_readings: list[dict] | None = None,
    lab_custom_markers: list[dict] | None = None,
) -> ImportPlan:
    """Plant den Import HA-frei: parst, prüft und filtert Duplikate.

    ``dataset`` ist ``drinks``, ``blood_pressure``, ``lab_values`` oder ``all``
    (auto-erkennen). Duplikate werden über ``(ts, ml)``, ``(ts, sys, dia)`` bzw.
    ``(ts, marker_key, value)`` erkannt — bestehende Einträge und Wiederholungen
    innerhalb der Datei zählen als ``skipped``, unlesbare Zeilen, unbekannte
    Laborwert-Marker und nicht unterstützte Einheiten als ``rejected``.

    Laborwerte werden nach der Marker-Auflösung über
    ``logic.convert_lab_value`` in den ``canonical_unit`` des Markers umgerechnet
    (Spec-Invariante: ``value``/``unit`` sind immer kanonisch). Die Rohwerte
    bleiben als ``reported_value``/``reported_unit`` erhalten.
    """
    rows, header_kind = parse_csv_text(text)
    resolved = dataset
    if dataset == "all":
        resolved = header_kind or _detect_kind(rows)

    plan = ImportPlan()
    if resolved == "lab_values":
        seen_labs = _existing_lab_keys(existing_lab_readings or [])
        for cells in rows:
            record = _parse_lab_row(cells)
            if isinstance(record, str):
                plan.rejected += 1
                plan.errors.append(record)
                continue
            resolved_marker = resolve_lab_marker(record["marker_raw"], lab_custom_markers)
            if resolved_marker is None:
                plan.rejected += 1
                plan.errors.append(f"Unbekannter Marker: {record['marker_raw']!r}")
                continue
            marker_key, marker_def = resolved_marker
            try:
                value, unit = convert_lab_value(marker_def, record["value"], record["unit"])
            except ValueError:
                plan.rejected += 1
                plan.errors.append(f"Nicht unterstützte Einheit: {record['unit']!r}")
                continue
            record["marker_key"] = marker_key
            record["value"] = value
            record["unit"] = unit
            del record["marker_raw"]
            key = (record["ts"], marker_key, record["value"])
            if key in seen_labs:
                plan.skipped += 1
                continue
            seen_labs.add(key)
            plan.lab_readings.append(record)
    elif resolved == "blood_pressure":
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


def _entry_lab_custom_markers(hass: HomeAssistant, entry_id: str) -> list[dict] | None:
    """`entry.options["lab_custom_markers"]` einer Person (nicht im Store)."""
    try:
        entries = hass.config_entries.async_entries(DOMAIN)
    except (AttributeError, TypeError):
        return None
    for config_entry in entries:
        if getattr(config_entry, "entry_id", None) != entry_id:
            continue
        options = getattr(config_entry, "options", None)
        custom = options.get(OPTION_LAB_CUSTOM_MARKERS) if hasattr(options, "get") else None
        return custom if isinstance(custom, list) else None
    return None


async def async_import_csv(
    hass: HomeAssistant,
    store: HealthOMatStore,
    entry_id: str,
    call: ServiceCall,
    audit_limit: int = DEFAULT_AUDIT_LIMIT,
    lab_custom_markers: list[dict] | None = None,
) -> dict:
    """Service ``health_o_mat.import_csv`` — liest und übernimmt eine CSV-Datei.

    Wiederherstellung läuft über die bestehenden Store-Pfade
    (``add_drink`` / ``add_reading``), danach ``signal_refresh`` und eine
    ``persistent_notification`` mit der Zusammenfassung. Rückgabe ist ein
    strukturiertes Ergebnis (für WS/UI und Tests).

    Die Duplikat-Erkennung arbeitet bewusst gegen die **rohen** Listen
    (aktive *und* voided Einträge): ein zuvor gelöschter Eintrag darf nicht
    durch einen Re-Import stillschweigend wieder auferstehen. Importierte
    Einträge werden über die Store-Pfade angelegt und sind damit aktiv.
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
    if lab_custom_markers is None:
        lab_custom_markers = _entry_lab_custom_markers(hass, entry_id)
    # Rohe Listen (inkl. voided) — gelöschte Einträge gelten als Duplikat.
    plan = plan_import(
        text,
        dataset,
        entry.get("drinks", []),
        entry.get("readings", []),
        existing_lab_readings=entry.get("lab_readings", []),
        lab_custom_markers=lab_custom_markers,
    )

    for drink in plan.drinks:
        await store.add_drink(
            entry_id,
            drink["ts"],
            drink["ml"],
            drink["type"],
            drink["src"],
            audit_limit=audit_limit,
        )
    for reading in plan.readings:
        await store.add_reading(
            entry_id,
            reading["ts"],
            reading["sys"],
            reading["dia"],
            reading["pulse"],
            reading["note"],
            reading["src"],
            audit_limit=audit_limit,
        )
    for lab_reading in plan.lab_readings:
        await store.add_lab_reading(
            entry_id,
            lab_reading["ts"],
            lab_reading["marker_key"],
            lab_reading["value"],
            lab_reading["unit"],
            lab_reading["reported_value"],
            lab_reading["reported_unit"],
            report_ref=lab_reading["report_ref"],
            audit_limit=audit_limit,
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

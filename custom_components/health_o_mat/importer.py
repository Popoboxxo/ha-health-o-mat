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
    IMPORT_ERROR_LIMIT,
    MAX_AMOUNT_ML,
    NO_TYPE_LABEL,
    OPTION_LAB_CUSTOM_MARKERS,
)
from .entity import signal_refresh
from .logic import convert_lab_value, resolve_lab_marker
from .store import HealthOMatStore, lab_dedupe_key

_LOGGER = logging.getLogger(__name__)

IMPORT_DIR_NAME = "health_o_mat_import"
# Restore-Backups dürfen aus Import- UND Export-Ordner gelesen werden: die
# Integration schreibt Backup/Pre-Restore dorthin, die Restore-UI muss sie
# also auch wieder anbieten. Beide Ordner sind privat (nie /config/www).
RESTORE_DIR_NAMES: tuple[str, ...] = (IMPORT_DIR_NAME, BACKUP_DIR_NAME)
# CSV-Import (#72): eine direkt zuvor exportierte Datei liegt im Export-Ordner
# und muss ohne Umkopieren wieder importierbar sein. Die Whitelist wird damit
# erweitert, nicht ersetzt — beide Ordner sind privat.
CSV_SOURCE_DIR_NAMES: tuple[str, ...] = (IMPORT_DIR_NAME, BACKUP_DIR_NAME)

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
# Header-basierte Spaltenzuordnung für `lab_values.csv` (Reihenfolgen-tolerant).
# Schlüssel = kanonischer Feldname, Werte = akzeptierte Kopfzellen. Ohne
# brauchbare Kopfzeile (Altdatei) gilt weiterhin die Positions-Konvention aus
# `exporter.py`: 0 zeitstempel … 8 berichts_referenz.
_LAB_HEADER_ALIASES: dict[str, tuple[str, ...]] = {
    "ts": ("zeitstempel", "timestamp", "datum", "date"),
    "marker": ("marker",),
    "value": ("wert", "value"),
    "unit": ("einheit", "unit"),
    "reported_value": ("eingegeben_als_wert", "reported_value"),
    "reported_unit": ("eingegeben_als_einheit", "reported_unit"),
    "report_ref": ("berichts_referenz", "report_ref"),
    "voided_at": ("voided_at",),
    "void_reason": ("void_reason",),
}
_LAB_REQUIRED_COLUMNS = frozenset({"ts", "marker", "value"})
_DRIVE_RE = re.compile(r"^[A-Za-z]:")

DATASETS = ("drinks", "blood_pressure", "lab_values")

# Stabile Fehlergründe des Import-Reports. Bewusst OHNE Zellinhalte/Messwerte:
# die Antworten landen im Automation-Trace (docs/SERVICE-RESPONSES.md) — nur
# `Zeile <N>: <Grund>` wird preisgegeben, `rejected` bleibt der Zähler.
REASON_TOO_FEW_COLUMNS = "zu wenige Spalten"
REASON_INVALID_TIMESTAMP = "ungültiger Zeitstempel"
REASON_INVALID_AMOUNT = "ungültige Menge"
REASON_AMOUNT_OUT_OF_RANGE = "Menge außerhalb des Bereichs"
REASON_INVALID_BP = "ungültiger Blutdruckwert"
REASON_BP_OUT_OF_RANGE = "Blutdruckwert außerhalb des Bereichs"
REASON_INVALID_PULSE = "ungültiger Puls"
REASON_INVALID_LAB_VALUE = "ungültiger Laborwert"
REASON_INVALID_REPORTED_VALUE = "ungültiger eingegebener Wert"
REASON_UNKNOWN_MARKER = "unbekannter Marker"
REASON_UNIT_REQUIRED = "Einheit erforderlich"
REASON_UNSUPPORTED_UNIT = "nicht unterstützte Einheit"


def _row_error(line_no: int, reason: str) -> str:
    """Import-Fehlertext ohne Zellinhalte: ``Zeile <N>: <Grund>``."""
    return f"Zeile {line_no}: {reason}"


def safe_import_path(config_dir: str, filename: str) -> str:
    """Löst einen Import-Dateinamen auf und prüft die Whitelist (HA-frei).

    Erlaubt ist NUR ein relativer Pfad unterhalb von
    ``<config_dir>/health_o_mat_import/`` **oder** (seit #72) dem privaten
    Export-Ordner ``<config_dir>/health_o_mat_export/`` — damit ist eine
    gerade exportierte CSV ohne Umkopieren wieder importierbar. Abgelehnt
    werden leere Namen, absolute Pfade (``/...``, ``\\...``, ``C:...``),
    Traversal-Komponenten (``..``) und Symlink-Escapes (das Ziel läge nach
    ``realpath`` außerhalb der erlaubten Ordner).

    Existiert der Name in beiden Ordnern, gewinnt der Import-Ordner (wie beim
    Restore). Existiert er in keinem, wird der Import-Pfad zurückgegeben,
    damit der Aufrufer einen klaren ``FileNotFoundError`` melden kann.

    Returns:
        Absoluter, real aufgelöster Pfad unterhalb eines erlaubten Ordners.

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
    candidates: list[str] = []
    for dir_name in CSV_SOURCE_DIR_NAMES:
        base = os.path.realpath(os.path.join(config_dir, dir_name))
        candidate = os.path.realpath(os.path.join(base, name))
        if candidate == base:
            raise ValueError("Ungültiger Dateiname")
        try:
            contained = os.path.commonpath([base, candidate]) == base
        except ValueError:  # unterschiedliche Laufwerke (Windows)
            contained = False
        if not contained:
            raise ValueError("Pfad verlässt das Import-Verzeichnis")
        candidates.append(candidate)
        try:
            if os.path.isfile(candidate):
                return candidate
        except OSError:  # pragma: no cover - nur bei Race mit dem Dateisystem
            continue
    return candidates[0]


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
    rows, kind, _header, _lines = _parse_csv_text(text)
    return rows, kind


def _parse_csv_text(
    text: str,
) -> tuple[list[list[str]], str | None, list[str] | None, list[int]]:
    """Wie :func:`parse_csv_text`, liefert zusätzlich Kopfzeile und Zeilennummern.

    Die Kopfzellen werden nur zurückgegeben, wenn eine Kopfzeile erkannt wurde;
    sie erlauben die reihenfolgen-tolerante Spaltenzuordnung der Laborwerte
    (``voided_at``/``void_reason``) ohne Positions-Annahmen. ``lines`` enthält
    je Datenzeile die physische Zeilennummer der CSV (für ``Zeile <N>: …`` in
    Fehlermeldungen — ohne Zellinhalte).
    """
    if text.startswith("\ufeff"):
        text = text[1:]
    rows: list[list[str]] = []
    lines: list[int] = []
    kind: str | None = None
    header: list[str] | None = None
    reader = csv.reader(io.StringIO(text), delimiter=";")
    for raw in reader:
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
                header = cells
            continue  # Kopfzeile
        rows.append(cells)
        lines.append(reader.line_num)
    return rows, kind, header, lines


def _to_int(raw: str) -> int:
    """Zahl tolerant lesen: ``250``, ``250.0``, ``250,0`` → 250."""
    return int(float(raw.strip().replace(",", ".")))


def _parse_drink_row(cells: list[str]) -> dict | str:
    """Getränke-Zeile → Record-Dict oder stabiler Fehlergrund (str)."""
    if len(cells) < 5:
        return REASON_TOO_FEW_COLUMNS
    ts = _join_ts(cells[0], cells[1] if len(cells) > 1 else "")
    if ts is None:
        return REASON_INVALID_TIMESTAMP
    try:
        ml = _to_int(cells[4])
    except ValueError:
        return REASON_INVALID_AMOUNT
    if ml <= 0 or ml > MAX_AMOUNT_ML:
        return REASON_AMOUNT_OUT_OF_RANGE
    return {
        "ts": ts,
        "ml": ml,
        "type": cells[3].strip() or NO_TYPE_LABEL,
        "src": cells[5].strip() if len(cells) > 5 else "",
    }


def _parse_reading_row(cells: list[str]) -> dict | str:
    """Blutdruck-Zeile → Record-Dict oder stabiler Fehlergrund (str)."""
    if len(cells) < 4:
        return REASON_TOO_FEW_COLUMNS
    ts = _norm_ts(cells[0])
    if ts is None:
        return REASON_INVALID_TIMESTAMP
    try:
        sys_ = _to_int(cells[2])
        dia = _to_int(cells[3])
    except ValueError:
        return REASON_INVALID_BP
    if not (0 < sys_ <= 1000 and 0 < dia <= 1000):
        return REASON_BP_OUT_OF_RANGE
    pulse: int | None = None
    if len(cells) > 4 and cells[4].strip():
        try:
            pulse = _to_int(cells[4])
        except ValueError:
            return REASON_INVALID_PULSE
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


def _norm_header_cell(cell: str) -> str:
    """Kopfzelle normalisieren: BOM-, Whitespace- und Groß-/Kleinschreibung-tolerant."""
    return cell.strip().lstrip("\ufeff").strip().lower().replace(" ", "_")


def _lab_column_map(header: list[str] | None) -> dict[str, int] | None:
    """Kopfzeile → Spaltenindex je Laborwert-Feld (``None`` = Positions-Fallback).

    Nur eine Kopfzeile, die alle Kernspalten (``ts``/``marker``/``value``)
    benennt, gilt als brauchbar. Sonst bleibt es bei der bestehenden
    Positions-Konvention (Index 0..8) — Altdateien ohne die neuen Spalten
    importieren damit unverändert.
    """
    if not header:
        return None
    normalized = [_norm_header_cell(cell) for cell in header]
    columns: dict[str, int] = {}
    for field_name, aliases in _LAB_HEADER_ALIASES.items():
        for index, cell in enumerate(normalized):
            if cell in aliases:
                columns[field_name] = index
                break
    if not _LAB_REQUIRED_COLUMNS <= columns.keys():
        return None
    return columns


def _is_voided_lab_row(cells: list[str], columns: dict[str, int] | None) -> bool:
    """True, wenn die Zeile eine gefüllte ``voided_at``-Spalte trägt.

    Header-basiert: ohne erkannte ``voided_at``-Spalte (Altdatei) gibt es
    keine voideten Zeilen — das Verhalten bleibt dort unverändert.
    """
    if columns is None:
        return False
    index = columns.get("voided_at")
    if index is None or index >= len(cells):
        return False
    return bool(cells[index].strip())


def _parse_lab_row(cells: list[str], columns: dict[str, int] | None = None) -> dict | str:
    """Laborwert-Zeile → Record-Dict (noch unaufgelöster `marker_raw`) oder Fehlermeldung.

    Spalten (siehe `exporter.py`): zeitstempel, person, marker, kategorie, wert,
    einheit, eingegeben_als_wert, eingegeben_als_einheit, berichts_referenz,
    voided_at, void_reason. ``columns`` ist die header-basierte Zuordnung aus
    :func:`_lab_column_map`; fehlt sie (Altdatei ohne Kopfzeile), gilt die
    Positions-Konvention 0..8. Die Marker-Auflösung (Alias/Katalog/Custom)
    passiert erst in `plan_import` — diese Funktion bleibt reine
    Zeilen-Validierung, analog zu `_parse_drink_row`/`_parse_reading_row`.
    """
    if len(cells) < 6:
        return REASON_TOO_FEW_COLUMNS

    def cell(field_name: str, fallback: int) -> str:
        index = columns.get(field_name) if columns is not None else None
        if index is None:
            index = fallback
        return cells[index].strip() if 0 <= index < len(cells) else ""

    ts = _norm_ts(cell("ts", 0))
    if ts is None:
        return REASON_INVALID_TIMESTAMP
    marker_raw = cell("marker", 2)
    if not marker_raw:
        return REASON_UNKNOWN_MARKER
    raw_value = cell("value", 4)
    try:
        value = float(raw_value.replace(",", "."))
    except ValueError:
        return REASON_INVALID_LAB_VALUE
    unit = cell("unit", 5)
    reported_value = value
    raw_reported = cell("reported_value", 6)
    if raw_reported:
        try:
            reported_value = float(raw_reported.replace(",", "."))
        except ValueError:
            return REASON_INVALID_REPORTED_VALUE
    reported_unit = cell("reported_unit", 7) or unit
    report_ref = cell("report_ref", 8) or None
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


def _existing_lab_keys(existing: list[dict]) -> set[tuple[str, str]]:
    """``(ts, marker_key)`` — dieselbe kanonische Regel wie der Store-Guard.

    Ein gleicher Zeitpunkt/Marker mit **abweichendem** Wert ist ein Duplikat
    (#71/#72, RVW2-02): der Befund wird nicht überschrieben, die Zeile zählt
    als ``skipped`` und bricht den Import nicht ab.
    """
    keys: set[tuple[str, str]] = set()
    for item in existing:
        if not isinstance(item, dict):
            continue
        keys.add(lab_dedupe_key(item.get("ts"), item.get("marker_key")))
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
    ``(ts, marker_key)`` erkannt — bestehende Einträge und Wiederholungen
    innerhalb der Datei zählen als ``skipped``, unlesbare Zeilen, unbekannte
    Laborwert-Marker und nicht unterstützte Einheiten als ``rejected``.
    Ein Laborwert mit gleichem ``(ts, marker_key)``, aber neuem Wert ist damit
    ebenfalls ein Duplikat (kein Überschreiben, kein Abbruch; #71/#72).

    Laborwerte: Zeilen mit gefüllter ``voided_at``-Spalte (Export enthält auch
    voidete Werte) werden **übersprungen** und als ``skipped`` gezählt — das
    gilt unabhängig vom Bestand, also auch für einen leeren Store (keine
    Wiederbelebung gelöschter Werte). Erkannt wird die Spalte header-basiert;
    Altdateien ohne die Spalte behalten die Positions-Konvention.

    Laborwerte werden nach der Marker-Auflösung über
    ``logic.convert_lab_value`` in den ``canonical_unit`` des Markers umgerechnet
    (Spec-Invariante: ``value``/``unit`` sind immer kanonisch). Die Rohwerte
    bleiben als ``reported_value``/``reported_unit`` erhalten. Eine leere
    Einheitsspalte bedeutet "keine Angabe" → kanonische Einheit (N-4); nur
    Marker mit ``require_explicit_unit`` lehnen sie ab.
    """
    rows, header_kind, header, lines = _parse_csv_text(text)
    resolved = dataset
    if dataset == "all":
        resolved = header_kind or _detect_kind(rows)

    plan = ImportPlan()
    if resolved == "lab_values":
        columns = _lab_column_map(header)
        seen_labs = _existing_lab_keys(existing_lab_readings or [])
        for line_no, cells in zip(lines, rows, strict=True):
            # REQ-HOM-129: voidete Zeilen nie importieren (sonst würden sie in
            # einem leeren Store als aktive Werte wiederauferstehen).
            if _is_voided_lab_row(cells, columns):
                plan.skipped += 1
                continue
            record = _parse_lab_row(cells, columns)
            if isinstance(record, str):
                plan.rejected += 1
                plan.errors.append(_row_error(line_no, record))
                continue
            resolved_marker = resolve_lab_marker(record["marker_raw"], lab_custom_markers)
            if resolved_marker is None:
                plan.rejected += 1
                plan.errors.append(_row_error(line_no, REASON_UNKNOWN_MARKER))
                continue
            marker_key, marker_def = resolved_marker
            # N-4: Eine leere Einheitsspalte ist "keine Angabe" — analog zu
            # `convert_lab_value(unit=None)` und zum Service `add_lab_value`
            # (unit optional) wird die kanonische Einheit angenommen. Nur Marker
            # mit `require_explicit_unit` verlangen zwingend eine Einheit.
            raw_unit = record["unit"] or None
            if raw_unit is None and marker_def.get("require_explicit_unit"):
                plan.rejected += 1
                plan.errors.append(_row_error(line_no, REASON_UNIT_REQUIRED))
                continue
            try:
                value, unit = convert_lab_value(marker_def, record["value"], raw_unit)
            except ValueError:
                plan.rejected += 1
                plan.errors.append(_row_error(line_no, REASON_UNSUPPORTED_UNIT))
                continue
            record["marker_key"] = marker_key
            record["value"] = value
            record["unit"] = unit
            # Ohne gedruckte Einheit bleibt `reported_unit` leer — dann gilt die
            # kanonische Einheit (gleiche Invariante wie im Service).
            record["reported_unit"] = record["reported_unit"] or unit
            del record["marker_raw"]
            key = lab_dedupe_key(record["ts"], marker_key)
            if key in seen_labs:
                plan.skipped += 1
                continue
            seen_labs.add(key)
            plan.lab_readings.append(record)
    elif resolved == "blood_pressure":
        seen = _existing_reading_keys(existing_readings or [])
        for line_no, cells in zip(lines, rows, strict=True):
            record = _parse_reading_row(cells)
            if isinstance(record, str):
                plan.rejected += 1
                plan.errors.append(_row_error(line_no, record))
                continue
            key = (record["ts"], record["sys"], record["dia"])
            if key in seen:
                plan.skipped += 1
                continue
            seen.add(key)
            plan.readings.append(record)
    else:
        seen_drinks = _existing_drink_keys(existing_drinks or [])
        for line_no, cells in zip(lines, rows, strict=True):
            record = _parse_drink_row(cells)
            if isinstance(record, str):
                plan.rejected += 1
                plan.errors.append(_row_error(line_no, record))
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


def _group_lab_readings(readings: list[dict]) -> list[dict]:
    """Laborzeilen nach ``(ts, report_ref)`` gruppieren (O-3, je Bericht).

    Die Reihenfolge der Gruppen ist die Reihenfolge des ersten Auftretens in
    der Datei; innerhalb einer Gruppe bleibt die Zeilenreihenfolge erhalten.
    """
    grouped: dict[tuple[str, str | None], list[dict]] = {}
    for reading in readings:
        key = (reading["ts"], reading.get("report_ref"))
        grouped.setdefault(key, []).append(reading)
    return [
        {"ts_iso": ts, "report_ref": report_ref, "rows": rows}
        for (ts, report_ref), rows in grouped.items()
    ]


async def async_import_csv(
    hass: HomeAssistant,
    store: HealthOMatStore,
    entry_id: str,
    call: ServiceCall | None = None,
    audit_limit: int = DEFAULT_AUDIT_LIMIT,
    lab_custom_markers: list[dict] | None = None,
    *,
    filename: str | None = None,
    content: str | None = None,
    dataset: str | None = None,
    actor: str | None = None,
) -> dict:
    """Service ``health_o_mat.import_csv`` — liest und übernimmt eine CSV-Datei.

    Quelle ist entweder ``filename`` (aufgelöst über :func:`safe_import_path`,
    Import- **oder** privater Export-Ordner) oder ``content`` (UTF-8-Text aus
    einem WebSocket-Upload, #72 — nie auf Platte geschrieben). Genau eine
    Quelle wird genutzt; der Aufrufer (WS) erzwingt die Eindeutigkeit.

    ``dataset``/``actor`` sind explizite Parameter für den WS-Pfad (kein
    Fake-ServiceCall über Modulgrenzen, #WP1-03); ohne sie fallen die Werte auf
    ``call.data`` zurück. Der Actor landet im Audit der geschriebenen Einträge.

    Wiederherstellung läuft über die bestehenden Store-Pfade
    (``add_drink`` / ``add_reading``), danach ``signal_refresh`` und eine
    ``persistent_notification`` mit der Zusammenfassung. Rückgabe ist der
    Service-Response-Vertrag (#71): ``{imported, skipped, rejected, errors}``
    mit auf :data:`IMPORT_ERROR_LIMIT` gedeckelten Fehlertexten.

    Die Duplikat-Erkennung arbeitet bewusst gegen die **rohen** Listen
    (aktive *und* voided Einträge): ein zuvor gelöschter Eintrag darf nicht
    durch einen Re-Import stillschweigend wieder auferstehen. Zusätzlich
    überspringt ``plan_import`` Zeilen, die im Export ``voided_at`` tragen —
    unabhängig davon, ob der Store sie kennt. Importierte Einträge werden über
    die Store-Pfade angelegt und sind damit aktiv.

    Laborwerte werden je Bericht gruppiert und über
    :meth:`HealthOMatStore.add_lab_readings_bulk` in **einem** Speichervorgang
    je Labor-Dataset geschrieben (O-3); Getränke/Blutdruck bleiben zeilenweise.
    """
    if store is None:
        raise ServiceValidationError("Health-O-Mat-Speicher nicht verfügbar")

    if dataset is None:
        dataset = call.data.get("dataset", "all") if call is not None else "all"
    path: str | None = None
    source_label: str
    if content is not None:
        text = content
        source_label = "upload"
    else:
        if filename is None:
            filename = (call.data.get("filename") or "") if call is not None else ""
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
        except UnicodeDecodeError as err:
            raise ServiceValidationError(
                "Import-Datei ist nicht UTF-8 "
                f"(nur UTF-8 mit/ohne BOM wird unterstützt): {filename}"
            ) from err
        except OSError as err:
            raise ServiceValidationError(f"Import-Datei nicht lesbar: {filename}") from err
        source_label = os.path.basename(path)

    entry = store.entry(entry_id)
    if lab_custom_markers is None:
        lab_custom_markers = _entry_lab_custom_markers(hass, entry_id)

    # Parsen/Planen im Executor: ein 2-MiB-Upload darf den Event-Loop nicht
    # blockieren (Risiko aus #72).
    def _plan() -> ImportPlan:
        return plan_import(
            text,
            dataset,
            entry.get("drinks", []),
            entry.get("readings", []),
            existing_lab_readings=entry.get("lab_readings", []),
            lab_custom_markers=lab_custom_markers,
        )

    plan = await hass.async_add_executor_job(_plan)

    for drink in plan.drinks:
        await store.add_drink(
            entry_id,
            drink["ts"],
            drink["ml"],
            drink["type"],
            drink["src"],
            actor=actor,
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
            actor=actor,
            audit_limit=audit_limit,
        )
    # Autoritative Zähler (#WP1-02): die vom Store tatsächlich geschriebenen
    # IDs zählen — nicht die geplante Zeilenzahl. Was der Store als Duplikat
    # verwirft (Race/Altbestand), wird zu `skipped` statt still zu `imported`.
    planned_labs = len(plan.lab_readings)
    written_labs = 0
    groups = _group_lab_readings(plan.lab_readings)
    if groups:
        written_ids = await store.add_lab_readings_bulk(
            entry_id, groups, actor=actor, audit_limit=audit_limit
        )
        written_labs = len(written_ids)
    imported = len(plan.drinks) + len(plan.readings) + written_labs
    skipped = plan.skipped + (planned_labs - written_labs)
    signal_refresh(hass, entry_id)

    summary = (
        f"Import '{source_label}': "
        f"{imported} übernommen, {skipped} übersprungen (Duplikat), "
        f"{plan.rejected} ungültig."
    )
    await hass.services.async_call(
        "persistent_notification",
        "create",
        {"title": "HA Health-O-Mat Import", "message": summary},
        blocking=False,
    )
    return {
        "imported": imported,
        "skipped": skipped,
        "rejected": plan.rejected,
        "errors": plan.errors[:IMPORT_ERROR_LIMIT],
    }

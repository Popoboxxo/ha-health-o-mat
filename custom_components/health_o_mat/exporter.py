"""CSV-Export (Service-only, kein Button)."""

from __future__ import annotations

import os
from typing import Any

from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
from homeassistant.util import dt as dt_util

from .const import DOMAIN, OPTION_LAB_CUSTOM_MARKERS
from .logic import csv_filename, drinks_csv_rows, effective_lab_markers, rows_to_csv_string
from .store import HealthOMatStore

_LAB_VALUES_HEADER = [
    "zeitstempel",
    "person",
    "marker",
    "kategorie",
    "wert",
    "einheit",
    "eingegeben_als_wert",
    "eingegeben_als_einheit",
    "berichts_referenz",
    "voided_at",
    "void_reason",
]


def _custom_lab_markers_from_entries(hass: HomeAssistant, entry_id: str) -> list[dict] | None:
    """`entry.options["lab_custom_markers"]` einer Person (HA-Options, nicht Store).

    Laborwert-Optionen liegen bewusst in `entry.options`; der Export bekommt nur
    `hass`/`store`/`call`, deshalb wird hier über die Config-Entries gelesen.
    Unbekannte/unbrauchbare Werte → `None` (nur Katalog-Marker).
    """
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


async def async_export_csv(
    hass: HomeAssistant,
    store: HealthOMatStore,
    call: ServiceCall,
    archive_store: HealthOMatStore | None = None,
    lab_custom_markers_by_entry: dict[str, list[dict]] | None = None,
) -> dict[str, Any]:
    """Schreibt Getränke-/BP-/Labor-CSV(s) nach /config/health_o_mat_export/.

    Rückgabe: der Service-Response-Vertrag (#71, O-2) —
    ``{filename, filenames, rows, dataset}``. ``filenames`` enthält **alle**
    geschriebenen Dateien (Basenamen), ``filename`` ist die erste,
    ``rows`` die Summe der Datenzeilen über alle Dateien.

    `archive_store` (Retention, REQ-HOM-109) wird — falls vorhanden — mit den
    aktuellen Daten zusammengeführt, damit der Export weiterhin die vollständige
    Historie enthält. Ohne Archiv (Default AUS) bleibt das Verhalten identisch.
    Exportiert werden ausschließlich **aktive** Getränke/Blutdruck-Einträge:
    voided (gelöschte) Buchungen/Messungen tauchen in keiner CSV auf (M2a).
    Laborwerte sind die Ausnahme (REQ-HOM-129): sie werden inklusive voideter
    Zeilen exportiert, damit Retention/Grund (`voided_at`/`void_reason`)
    nachvollziehbar bleiben.

    `lab_custom_markers_by_entry` liefert die Custom-Marker je Person (sie
    liegen in `entry.options`, nicht im Store). Fehlt der Parameter, werden
    die Options direkt aus `hass.config_entries` gelesen (REQ-HOM-122).
    """
    person_filter = (call.data.get("person") or "").strip().lower()
    dataset = call.data.get("dataset", "all")
    now = dt_util.now()

    def _combined(eid: str) -> tuple[list, list, list]:
        """Aktive Getränke/Readings + alle Laborwerte (inkl. voided), mit Archiv."""
        drinks = list(store.active_drinks(eid))
        readings = list(store.active_readings(eid))
        # REQ-HOM-129: Laborwerte werden inkl. voideter Zeilen exportiert
        # (Retention/Grund nachvollziehbar). Getränke/BD bleiben "nur aktive".
        lab_readings = list(store.entry(eid).get("lab_readings") or [])
        if archive_store is not None and eid in archive_store.all_entries():
            drinks += list(archive_store.active_drinks(eid))
            readings += list(archive_store.active_readings(eid))
            # Das Retention-Archiv kennt (aktuell) keine Laborwerte.
        return drinks, readings, lab_readings

    def _lab_markers(eid: str) -> dict[str, dict]:
        """Katalog- + Custom-Marker der Person (für die `kategorie`-Spalte)."""
        if lab_custom_markers_by_entry is not None:
            custom = lab_custom_markers_by_entry.get(eid)
        else:
            custom = _custom_lab_markers_from_entries(hass, eid)
        return effective_lab_markers(custom)

    def _resolve_entry_ids() -> list[str]:
        ids = []
        for eid, e in store.all_entries().items():
            if not person_filter or e.get("person", "").strip().lower() == person_filter:
                ids.append(eid)
        return ids

    entry_ids = _resolve_entry_ids()
    if person_filter and not entry_ids:
        raise ServiceValidationError(f"Person '{person_filter}' nicht gefunden")

    export_dir = hass.config.path("health_o_mat_export")

    def _write_files() -> tuple[list[str], int]:
        os.makedirs(export_dir, exist_ok=True)
        written: list[str] = []
        rows_total = 0
        for eid in entry_ids:
            data = store.all_entries()[eid]
            person = data.get("person") or "Person"
            drinks, readings, lab_readings = _combined(eid)
            if dataset in ("drinks", "all"):
                rows = drinks_csv_rows(drinks, person)
                name = csv_filename("drinks", person, now)
                path = os.path.join(export_dir, name)
                with open(path, "w", encoding="utf-8-sig", newline="") as f:
                    f.write(rows_to_csv_string(rows))
                written.append(path)
                rows_total += len(rows) - 1  # ohne Kopfzeile
            if dataset in ("blood_pressure", "all"):
                rows = [["zeitstempel", "person", "systolisch", "diastolisch", "puls", "notiz"]]
                for r in sorted(readings, key=lambda x: x.get("ts", "")):
                    rows.append(
                        [
                            r.get("ts", ""),
                            person,
                            str(r.get("sys", "")),
                            str(r.get("dia", "")),
                            "" if r.get("pulse") is None else str(r["pulse"]),
                            r.get("note", ""),
                        ]
                    )
                name = csv_filename("bloodpressure", person, now)
                path = os.path.join(export_dir, name)
                with open(path, "w", encoding="utf-8-sig", newline="") as f:
                    buf = ";".join(rows[0]) + "\n"
                    for row in rows[1:]:
                        buf += ";".join(str(c) for c in row) + "\n"
                    f.write(buf)
                written.append(path)
                rows_total += len(rows) - 1
            if dataset in ("lab_values", "all"):
                markers = _lab_markers(eid)
                rows = [list(_LAB_VALUES_HEADER)]
                for reading in sorted(lab_readings, key=lambda x: x.get("ts", "")):
                    marker_key = reading.get("marker_key", "")
                    category = (markers.get(marker_key) or {}).get("category", "")
                    rows.append(
                        [
                            reading.get("ts", ""),
                            person,
                            marker_key,
                            category,
                            str(reading.get("value", "")),
                            reading.get("unit", ""),
                            str(reading.get("reported_value", "")),
                            reading.get("reported_unit", ""),
                            reading.get("report_ref") or "",
                            reading.get("voided_at") or "",
                            reading.get("void_reason") or "",
                        ]
                    )
                name = csv_filename("labvalues", person, now)
                path = os.path.join(export_dir, name)
                with open(path, "w", encoding="utf-8-sig", newline="") as f:
                    f.write(rows_to_csv_string(rows))
                written.append(path)
                rows_total += len(rows) - 1
        return written, rows_total

    paths, rows_total = await hass.async_add_executor_job(_write_files)
    if not paths:
        raise ServiceValidationError("Keine Daten zum Exportieren")

    await hass.services.async_call(
        "persistent_notification",
        "create",
        {"title": "HA Health-O-Mat Export", "message": "Exportiert:\n" + "\n".join(paths)},
        blocking=False,
    )
    filenames = [os.path.basename(path) for path in paths]
    return {
        "filename": filenames[0],
        "filenames": filenames,
        "rows": rows_total,
        "dataset": dataset,
    }

"""CSV-Export (Service-only, kein Button)."""
from __future__ import annotations

import os

from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
from homeassistant.util import dt as dt_util

from .logic import csv_filename, drinks_csv_rows, rows_to_csv_string
from .store import HealthOMatStore


async def async_export_csv(hass: HomeAssistant, store: HealthOMatStore, call: ServiceCall) -> str:
    """Schreibt Getränke-/BP-CSV(s) nach /config/health_o_mat_export/."""
    person_filter = (call.data.get("person") or "").strip().lower()
    dataset = call.data.get("dataset", "all")
    now = dt_util.now()

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

    def _write_files() -> list[str]:
        os.makedirs(export_dir, exist_ok=True)
        written = []
        for eid in entry_ids:
            data = store.all_entries()[eid]
            person = data.get("person") or "Person"
            if dataset in ("drinks", "all"):
                rows = drinks_csv_rows(data.get("drinks", []), person)
                name = csv_filename("drinks", person, now)
                path = os.path.join(export_dir, name)
                with open(path, "w", encoding="utf-8-sig", newline="") as f:
                    f.write(rows_to_csv_string(rows))
                written.append(path)
            if dataset in ("blood_pressure", "all"):
                rows = [["zeitstempel", "person", "systolisch", "diastolisch",
                         "puls", "notiz"]]
                for r in sorted(data.get("readings", []), key=lambda x: x.get("ts", "")):
                    rows.append([
                        r.get("ts", ""), person,
                        str(r.get("sys", "")), str(r.get("dia", "")),
                        "" if r.get("pulse") is None else str(r["pulse"]),
                        r.get("note", ""),
                    ])
                name = csv_filename("bloodpressure", person, now)
                path = os.path.join(export_dir, name)
                with open(path, "w", encoding="utf-8-sig", newline="") as f:
                    buf = ";".join(rows[0]) + "\n"
                    for row in rows[1:]:
                        buf += ";".join(str(c) for c in row) + "\n"
                    f.write(buf)
                written.append(path)
        return written

    paths = await hass.async_add_executor_job(_write_files)
    if not paths:
        raise ServiceValidationError("Keine Daten zum Exportieren")

    await hass.services.async_call(
        "persistent_notification", "create",
        {"title": "HA Health-O-Mat Export",
         "message": "Exportiert:\n" + "\n".join(paths)},
        blocking=False,
    )
    return paths[0]

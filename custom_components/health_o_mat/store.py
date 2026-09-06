"""Persistenter Speicher (Store) — Quelle der Wahrheit, versioniert.

Schema-Stufen (STORE_SCHEMA_VERSION in const.py):
- v1: Ursprungsschema (drinks, readings, total_ml_lifetime, person, wellbeing*)
- v2: + `inputs` je Person (persistierte BP-Eingaben, REQ-HOM-104)

Migration on-load: fehlende `schema`-Markierung gilt als v1; die Migrationskette
bringt Alt-Bestände idempotent auf die aktuelle Stufe (REQ-HOM-102).
Bei defektem/ungültigem Load: Datei wird als `health_o_mat.corrupt-<ts>` gesichert,
Notification erzeugt, definierter Start mit leerem Bestand (REQ-HOM-103).
"""
from __future__ import annotations

import json
import logging
import os
from collections.abc import Callable
from datetime import datetime

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import STORE_SCHEMA_VERSION, STORE_VERSION

_LOGGER = logging.getLogger(__name__)


def _migrate_v1_to_v2(data: dict) -> dict:
    """v1 → v2: `inputs`-Dict je Person ergänzen (idempotent)."""
    for entry in data.get("entries", {}).values():
        entry.setdefault("inputs", {})
    return data


_MIGRATIONS: dict[int, Callable[[dict], dict]] = {
    1: _migrate_v1_to_v2,
}


class HealthOMatStore:
    """Append-only Historie je Person, persistiert via HA-Store."""

    def __init__(self, hass: HomeAssistant) -> None:
        self._hass = hass
        self._store = Store(
            hass, STORE_VERSION, "health_o_mat",
            minor_version=STORE_SCHEMA_VERSION,
        )
        self._data: dict = {}

    async def async_load(self) -> None:
        """Laden, migrieren und bei Defekt reparieren (leerer Start)."""
        data = await self._load_with_recovery()
        # bewusst frisches Dict je Instanz (keine geteilte Modul-Referenz!)
        self._data = self._migrate(data) if data else {"entries": {}}

    def _migrate(self, data: dict) -> dict:
        """Bringt geladene Daten idempotent auf STORE_SCHEMA_VERSION."""
        schema = int(data.get("schema", 1))
        for step in range(schema, STORE_SCHEMA_VERSION):
            migration = _MIGRATIONS.get(step)
            if migration:
                data = migration(data)
        data["schema"] = STORE_SCHEMA_VERSION
        return data

    async def _load_with_recovery(self) -> dict | None:
        """Load mit Corrupt-Recovery (REQ-HOM-103).

        Fehler (kaputtes JSON, ungültiges Schema) → Store-Datei als Backup
        sichern, Notification erzeugen, None zurückgeben (leerer Start).
        """
        try:
            data = await self._store.async_load()
        except Exception as err:  # noqa: BLE001 — Absicherung gegen kaputtes JSON
            await self._handle_corrupt(err)
            return None
        if data is None:
            return None  # Erstanlage — kein Defekt
        if not isinstance(data, dict) or "entries" not in data:
            await self._handle_corrupt(ValueError("Store-Inhalt ohne 'entries'"))
            return None
        return data

    async def _handle_corrupt(self, err: Exception) -> None:
        """Store-Datei sichern + Notification (Executor-Job, nie blockierend)."""
        _LOGGER.error("Health-O-Mat-Store defekt: %s — Backup + leerer Start", err)
        src = self._hass.config.path(".storage", "health_o_mat")
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        dst = f"{src}.corrupt-{stamp}"

        def _backup() -> bool:
            if os.path.exists(src):
                os.replace(src, dst)
                return True
            return False

        backed_up = await self._hass.async_add_executor_job(_backup)
        message = (
            f"Der Health-O-Mat-Speicher konnte nicht gelesen werden ({err}).\n"
            + (f"Die Originaldatei wurde gesichert nach:\n{dst}\n" if backed_up
               else "Keine Speicherdatei gefunden.\n")
            + "Die Integration startet mit leerem Bestand. "
            + "Bitte das Backup im GitHub-Issue anfügen, wenn Daten vermisst werden."
        )
        await self._hass.services.async_call(
            "persistent_notification", "create",
            {"title": "HA Health-O-Mat — Speicher defekt", "message": message},
            blocking=False,
        )

    def entry(self, entry_id: str) -> dict:
        return self._data["entries"].setdefault(
            entry_id, {
                "person": "", "drinks": [], "readings": [],
                "total_ml_lifetime": 0, "inputs": {},
            }
        )

    def all_entries(self) -> dict:
        return self._data["entries"]

    async def add_drink(self, entry_id: str, ts_iso: str, ml: int, drink_type: str, src: str) -> None:
        e = self.entry(entry_id)
        e["drinks"].append({"ts": ts_iso, "ml": int(ml), "type": drink_type, "src": src})
        e["total_ml_lifetime"] = int(e.get("total_ml_lifetime", 0)) + int(ml)
        await self._async_save()

    async def remove_last_drink(self, entry_id: str) -> bool:
        e = self.entry(entry_id)
        if not e["drinks"]:
            return False
        removed = e["drinks"].pop()
        e["total_ml_lifetime"] = max(0, int(e.get("total_ml_lifetime", 0)) - int(removed["ml"]))
        await self._async_save()
        return True

    async def add_reading(self, entry_id: str, ts_iso: str, sys_: int, dia: int, pulse: int | None,
                          note: str = "", src: str = "button") -> None:
        reading: dict = {
            "ts": ts_iso, "sys": int(sys_), "dia": int(dia),
            "pulse": int(pulse) if pulse is not None else None,
            "note": note, "src": src,
        }
        self.entry(entry_id)["readings"].append(reading)
        await self._async_save()

    async def set_person(self, entry_id: str, person: str) -> None:
        self.entry(entry_id)["person"] = person
        await self._async_save()

    async def set_lifetime_start(self, entry_id: str, ml: int) -> None:
        self.entry(entry_id)["total_ml_lifetime"] = int(ml)
        await self._async_save()

    def inputs(self, entry_id: str) -> dict:
        """Persistierte BP-Eingaben (Systolic/Diastolic/Pulse) je Person."""
        return self.entry(entry_id).setdefault("inputs", {})

    async def set_inputs(self, entry_id: str, key: str, value: int | None) -> None:
        """EINEN Eingabewert setzen (None = leeren) und persistieren."""
        self.inputs(entry_id)[key] = value
        await self._async_save()

    async def clear_inputs(self, entry_id: str) -> None:
        """Alle BP-Eingaben leeren (nach save_measurement)."""
        self.entry(entry_id)["inputs"] = {}
        await self._async_save()

    async def set_wellbeing(self, entry_id: str, status: str, ts_iso: str) -> None:
        """Wohlbefinden-Meldung setzen + Historie führen."""
        e = self.entry(entry_id)
        wb = e.setdefault("wellbeing", {})
        history = e.setdefault("wellbeing_history", [])
        if wb.get("status"):
            history.append({"ts": ts_iso, "status": wb["status"]})
            del history[:-100]
        wb["status"] = status
        wb["ts"] = ts_iso
        await self._async_save()

    def raw_data(self) -> dict:
        """Rohe Store-Daten (für Tests/Diagnostics)."""
        return self._data

    async def _async_save(self) -> None:
        await self._store.async_save(self._data)

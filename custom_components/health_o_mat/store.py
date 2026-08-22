"""Persistenter Speicher (Store) — Quelle der Wahrheit, versioniert."""
from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import STORE_VERSION


class HealthOMatStore:
    """Append-only Historie je Person, persistiert via HA-Store."""

    def __init__(self, hass: HomeAssistant) -> None:
        self._store = Store(hass, STORE_VERSION, "health_o_mat")
        self._data: dict = {}

    async def async_load(self) -> None:
        data = await self._store.async_load()
        self._data = data or {"entries": {}}

    def entry(self, entry_id: str) -> dict:
        return self._data["entries"].setdefault(
            entry_id, {"person": "", "drinks": [], "readings": [], "total_ml_lifetime": 0}
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

    async def _async_save(self) -> None:
        await self._store.async_save(self._data)

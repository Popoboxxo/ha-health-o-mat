"""Binary-Sensoren: Tagesziel erreicht + Blutdruck-Warnung."""
from __future__ import annotations

from datetime import datetime

from homeassistant.components.binary_sensor import BinarySensorEntity

from .const import DOMAIN
from .entity import HealthOMatEntity


async def async_setup_entry(hass, entry, async_add_entities) -> None:
    coord = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    store = hass.data[DOMAIN]["store"]
    async_add_entities([
        GoalReachedEntity(coord, entry, store),
        BloodPressureWarningEntity(coord, entry, store),
    ])


class HealthOMatBinary(HealthOMatEntity, BinarySensorEntity):
    def __init__(self, coordinator, entry, store) -> None:
        super().__init__(coordinator, entry)
        self._store = store
        self._attr_has_entity_name = True

    @property
    def _data(self) -> dict:
        return self._store.all_entries().get(self._entry.entry_id, {})

    def _today_ml(self) -> int:
        from . import logic
        now = datetime.now()
        rt = self._entry.runtime_data
        sums = logic.window_sums(
            self._data.get("drinks", []),
            logic.day_start(now, rt.boundary_hour, rt.boundary_minute),
            now,
        )
        return sums["total_ml"]


class GoalReachedEntity(HealthOMatBinary):
    _attr_translation_key = "goal_reached"

    @property
    def is_on(self) -> bool:
        goal = max(1, self._entry.runtime_data.daily_goal_ml)
        return self._today_ml() >= goal


class BloodPressureWarningEntity(HealthOMatBinary):
    _attr_translation_key = "bp_warning"
    _attr_icon = "mdi:alert-octagon"

    @property
    def is_on(self) -> bool:
        readings = self._data.get("readings", [])
        if not readings:
            return False
        last = sorted(readings, key=lambda r: r.get("ts", ""))[-1]
        rt = self._entry.runtime_data
        return (last.get("sys", 0) >= rt.sys_threshold
                or last.get("dia", 0) >= rt.dia_threshold)

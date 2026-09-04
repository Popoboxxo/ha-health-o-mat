"""Binary-Sensoren: Tagesziel erreicht + Blutdruck-Warnung."""
from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .entity import HealthOMatEntity
from . import logic


async def async_setup_entry(hass, entry, async_add_entities) -> None:
    coord = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    store = hass.data[DOMAIN]["shared"]["store"]
    async_add_entities([
        GoalReachedEntity(coord, entry, store),
        BloodPressureWarningEntity(coord, entry, store),
    ])


class HealthOMatBinary(HealthOMatEntity, BinarySensorEntity):
    def __init__(self, coordinator, entry, store, key: str) -> None:
        super().__init__(coordinator, entry, key)
        self._store = store

    @property
    def _data(self) -> dict:
        return self._store.all_entries().get(self._entry.entry_id, {})

    def _today_ml(self) -> int:
        now = dt_util.now()
        sums = logic.window_sums(
            self._data.get("drinks", []),
            logic.day_start(now),
            now,
        )
        return sums["total_ml"]


class GoalReachedEntity(HealthOMatBinary):
    _attr_translation_key = "goal_reached"

    def __init__(self, coordinator, entry, store) -> None:
        super().__init__(coordinator, entry, store, "binary_goal_reached")

    @property
    def is_on(self) -> bool:
        goal = max(1, self._entry.runtime_data.daily_goal_ml)
        return self._today_ml() >= goal


class BloodPressureWarningEntity(HealthOMatBinary):
    _attr_translation_key = "bp_warning"
    _attr_icon = "mdi:alert-octagon"

    def __init__(self, coordinator, entry, store) -> None:
        super().__init__(coordinator, entry, store, "binary_bp_warning")

    @property
    def is_on(self) -> bool:
        readings = self._data.get("readings", [])
        if not readings:
            return False
        last = sorted(readings, key=lambda r: r.get("ts", ""))[-1]
        rt = self._entry.runtime_data
        return (last.get("sys", 0) >= rt.sys_threshold
                or last.get("dia", 0) >= rt.dia_threshold)

"""Sensor-Plattform: Aggregate + Verlauf + BP-Werte je Person."""
from __future__ import annotations

from datetime import datetime
import json

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .entity import HealthOMatEntity
from . import logic


async def async_setup_entry(hass, entry, async_add_entities) -> None:
    coord = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    store = hass.data[DOMAIN]["shared"]["store"]

    entities = [
        TodaySensor(coord, entry, store),
        PercentSensor(coord, entry, store),
        HistoryDrinksSensor(coord, entry, store),
        LifetimeSensor(coord, entry, store),
        BloodPressureHistorySensor(coord, entry, store),
        WellbeingSinceSensor(coord, entry, store),
    ]
    for key, unit in (("sys", "mmHg"), ("dia", "mmHg"), ("pulse", "BPM")):
        entities.append(LastReadingSensor(coord, entry, store, key, unit))
    async_add_entities(entities)


class HealthOMatSensor(HealthOMatEntity, SensorEntity):
    """Basis-Sensor."""

    def __init__(self, coordinator, entry, store) -> None:
        super().__init__(coordinator, entry, "sensor")
        self._store = store
        self._attr_unique_id = f"{entry.entry_id}_sensor_{type(self).__name__}"

    @property
    def _data(self) -> dict:
        return self._store.all_entries().get(self._entry.entry_id, {})

    def _today_sums(self) -> dict:
        return logic.today_sums(self._data.get("drinks", []), dt_util.now())


class TodaySensor(HealthOMatSensor):
    """Sauberer Mengen-Sensor in ml für „Heute"."""

    _attr_translation_key = "today"
    _attr_native_unit_of_measurement = "ml"
    _attr_state_class = SensorStateClass.TOTAL
    _attr_icon = "mdi:cup-water"

    @property
    def native_value(self) -> int:
        return self._today_sums()["total_ml"]

    @property
    def extra_state_attributes(self) -> dict:
        sums = self._today_sums()
        rt = self._entry.runtime_data
        now = dt_util.now()
        y_start, y_end = logic.yesterday_window(now)
        yesterday = logic.window_sums(self._data.get("drinks", []), y_start, y_end)
        return {
            "drinks_count": sums["count"],
            "percent_of_goal": round(sums["total_ml"] / max(1, rt.daily_goal_ml) * 100, 1),
            "breakdown_by_type": json.dumps(sums["breakdown"], ensure_ascii=False),
            "last_drink_at": sums["last_ts"],
            "yesterday_ml": yesterday["total_ml"],
        }


class PercentSensor(HealthOMatSensor):
    """Tagesziel in Prozent (Gauge-fähig)."""

    _attr_translation_key = "goal_percent"
    _attr_native_unit_of_measurement = "%"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:gauge"

    @property
    def native_value(self) -> float:
        return round(
            self._today_sums()["total_ml"] / max(1, self._entry.runtime_data.daily_goal_ml) * 100,
            1,
        )


class HistoryDrinksSensor(HealthOMatSensor):
    """Rohhistorie der Getränke als JSON-Attribut."""

    _attr_translation_key = "history_drinks"
    _attr_icon = "mdi:format-list-bulleted"
    # native_value ist die Anzahl Getränke im heutigen (on-read berechneten)
    # Fenster und wird beim Tageswechsel implizit auf 0 zurückgesetzt (kein
    # Reset-Job, siehe logic.today_sums). Ohne last_reset-Attribut wäre TOTAL
    # semantisch falsch (HA-Statistics-Engine kann den Reset nicht als
    # legitimen Cycle erkennen) - daher MEASUREMENT statt TOTAL.
    _attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def native_value(self) -> int:
        return self._today_sums()["count"]

    @property
    def extra_state_attributes(self) -> dict:
        return {"entries_json": json.dumps(self._data.get("drinks", []), ensure_ascii=False)}


class LifetimeSensor(HealthOMatSensor):
    """Kumulierter Lebenszähler."""

    _attr_translation_key = "lifetime"
    _attr_native_unit_of_measurement = "ml"
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_icon = "mdi:water-well"

    @property
    def native_value(self) -> int:
        return int(self._data.get("total_ml_lifetime", 0))


class LastReadingSensor(HealthOMatSensor):
    """Letzter gemessener Blutdruck-/Pulswert (measurement → Verlaufsgraph)."""

    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:heart-pulse"

    def __init__(self, coordinator, entry, store, key: str, unit: str) -> None:
        super().__init__(coordinator, entry, store)
        self._key = key
        self._attr_unique_id = f"{entry.entry_id}_sensor_bp_{key}"
        self._attr_translation_key = f"bp_{key}"
        self._attr_native_unit_of_measurement = unit

    def _sorted_readings(self) -> list[dict]:
        return sorted(self._data.get("readings", []), key=lambda r: r.get("ts", ""))

    @property
    def native_value(self) -> int | None:
        readings = self._sorted_readings()
        if not readings:
            return None
        return readings[-1].get(self._key)

    @property
    def extra_state_attributes(self) -> dict:
        readings = self._sorted_readings()
        if not readings:
            return {}
        avg = logic.avg_over_window(readings, self._key, dt_util.now())
        return {
            "measured_at": readings[-1].get("ts"),
            "avg_7d": round(avg, 1) if avg is not None else None,
            "readings_total": len(readings),
        }


class BloodPressureHistorySensor(HealthOMatSensor):
    """BP-Verlauf (letzte 30 Messungen) als JSON-Attribut."""

    _attr_translation_key = "history_bp"
    _attr_icon = "mdi:heart-box-outline"
    # native_value ist die Gesamtzahl aller je gespeicherten Messungen
    # (store.py haengt readings nur an, es gibt keinen Loesch-/Trim-Pfad) -
    # ein monoton steigender Lebenszaehler, analog zu LifetimeSensor.
    _attr_state_class = SensorStateClass.TOTAL_INCREASING

    @property
    def native_value(self) -> int:
        return len(self._data.get("readings", []))

    @property
    def extra_state_attributes(self) -> dict:
        readings = sorted(self._data.get("readings", []), key=lambda r: r.get("ts", ""))[-30:]
        return {"history_json": json.dumps(readings, ensure_ascii=False)}


class WellbeingSinceSensor(HealthOMatSensor):
    """Zeitpunkt der letzten Wohlbefinden-Meldung."""

    _attr_translation_key = "wellbeing_since"
    _attr_device_class = "timestamp"
    _attr_icon = "mdi:emoticon-outline"

    @property
    def native_value(self):
        wb = self._data.get("wellbeing") or {}
        ts = wb.get("ts")
        if not ts:
            return None
        # ts wird seit M-3 tz-aware geschrieben (dt_util.now().isoformat());
        # ältere naive Bestandsdaten fängt as_local() ab (nimmt lokale
        # HA-Zeitzone an statt sie undefiniert zu belassen).
        return dt_util.as_local(datetime.fromisoformat(ts))

"""Sensor-Plattform: Aggregate + Verlauf + BP-Werte je Person."""

from __future__ import annotations

import json
from datetime import datetime

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.util import dt as dt_util

from . import areas, logic
from .const import DOMAIN, HISTORY_ATTRIBUTE_LIMIT
from .entity import HealthOMatEntity


async def async_setup_entry(hass, entry, async_add_entities) -> None:
    coord = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    store = hass.data[DOMAIN]["shared"]["store"]
    active = areas.active_areas(entry.options)

    entities: list = []
    if active[areas.AREA_DRINK]:
        entities.extend(
            [
                TodaySensor(coord, entry, store),
                PercentSensor(coord, entry, store),
                HistoryDrinksSensor(coord, entry, store),
                LifetimeSensor(coord, entry, store),
                DrinksTrendSensor(coord, entry, store),
                GoalStreakSensor(coord, entry, store),
                CaffeineTodaySensor(coord, entry, store),
            ]
        )
    if active[areas.AREA_BP]:
        entities.extend(
            [
                BloodPressureHistorySensor(coord, entry, store),
                BloodPressureCategorySensor(coord, entry, store),
                BpTrendSensor(coord, entry, store),
            ]
        )
        for key, unit in (("sys", "mmHg"), ("dia", "mmHg"), ("pulse", "BPM")):
            entities.append(LastReadingSensor(coord, entry, store, key, unit))
    if active[areas.AREA_WELLBEING]:
        entities.append(WellbeingSinceSensor(coord, entry, store))
    async_add_entities(entities)


class HealthOMatSensor(HealthOMatEntity, SensorEntity):
    """Basis-Sensor. `key` bildet die semantische unique_id ({entry_id}_{key})."""

    def __init__(self, coordinator, entry, store, key: str) -> None:
        super().__init__(coordinator, entry, key)
        self._store = store

    @property
    def _data(self) -> dict:
        return self._store.all_entries().get(self._entry.entry_id, {})

    def _today_sums(self) -> dict:
        hour = self._entry.options.get("daily_reset_hour", 0)
        return logic.today_sums(self._data.get("drinks", []), dt_util.now(), hour=hour)


class TodaySensor(HealthOMatSensor):
    """Sauberer Mengen-Sensor in ml für „Heute"."""

    _attr_translation_key = "today"
    # HA-valid unit for SensorDeviceClass.VOLUME is "mL" (not "ml"); with "ml"
    # HA logs a "not a valid unit" warning and offers no native conversion (N-9).
    _attr_native_unit_of_measurement = "mL"
    _attr_device_class = SensorDeviceClass.VOLUME
    # Tageszähler: state_class TOTAL ist korrekt, weil das Fenster täglich
    # (on-read) zurücksetzt. Damit die HA-Statistics-Engine den Tagesreset als
    # legitimen Cycle statt als Anomalie/Abnahme erkennt, meldet last_reset
    # den Beginn des aktuellen Tagesfensters (Finding N-3).
    _attr_state_class = SensorStateClass.TOTAL
    _attr_icon = "mdi:cup-water"

    def __init__(self, coordinator, entry, store) -> None:
        super().__init__(coordinator, entry, store, "sensor_drinks_today")

    @property
    def last_reset(self) -> datetime:
        """Beginn des laufenden Tracking-Tags (dieselbe Grenze wie native_value)."""
        hour = self._entry.options.get("daily_reset_hour", 0)
        return logic.day_start(dt_util.now(), hour=hour)

    @property
    def native_value(self) -> int:
        return self._today_sums()["total_ml"]

    @property
    def extra_state_attributes(self) -> dict:
        sums = self._today_sums()
        rt = self._entry.runtime_data
        now = dt_util.now()
        hour = self._entry.options.get("daily_reset_hour", 0)
        y_start, y_end = logic.yesterday_window(now, hour=hour)
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

    def __init__(self, coordinator, entry, store) -> None:
        super().__init__(coordinator, entry, store, "sensor_goal_percent")

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

    def __init__(self, coordinator, entry, store) -> None:
        super().__init__(coordinator, entry, store, "sensor_drinks_history")

    @property
    def native_value(self) -> int:
        return self._today_sums()["count"]

    @property
    def extra_state_attributes(self) -> dict:
        # N-1: nur die letzten HISTORY_ATTRIBUTE_LIMIT Buchungen (nach ts
        # sortiert) landen im State-Attribut — sonst wächst das State-Objekt
        # und der Recorder unbegrenzt mit. Die Gesamtzahl bleibt über
        # total_count sichtbar; der Rohdaten-Vollbestand liegt weiterhin im
        # Store bzw. im CSV-Export.
        drinks = sorted(self._data.get("drinks", []), key=lambda d: d.get("ts", ""))
        return {
            "entries_json": json.dumps(drinks[-HISTORY_ATTRIBUTE_LIMIT:], ensure_ascii=False),
            "total_count": len(drinks),
        }


class LifetimeSensor(HealthOMatSensor):
    """Kumulierter Lebenszähler."""

    _attr_translation_key = "lifetime"
    _attr_native_unit_of_measurement = "mL"
    _attr_device_class = SensorDeviceClass.VOLUME
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_icon = "mdi:water-well"

    def __init__(self, coordinator, entry, store) -> None:
        super().__init__(coordinator, entry, store, "sensor_lifetime_total")

    @property
    def native_value(self) -> int:
        return int(self._data.get("total_ml_lifetime", 0))


class LastReadingSensor(HealthOMatSensor):
    """Letzter gemessener Blutdruck-/Pulswert (measurement → Verlaufsgraph)."""

    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:heart-pulse"

    def __init__(self, coordinator, entry, store, key: str, unit: str) -> None:
        super().__init__(coordinator, entry, store, f"sensor_bp_{key}")
        self._key = key
        self._attr_translation_key = f"bp_{key}"
        self._attr_native_unit_of_measurement = unit
        # N-9: sys/dia sind Druckwerte (mmHg) → device_class PRESSURE.
        # Puls (BPM) ist keine Druckgröße und bleibt bewusst ohne device_class.
        self._attr_device_class = SensorDeviceClass.PRESSURE if key in ("sys", "dia") else None

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
    # (store.py haengt readings nur an, es gibt keinen Loesch-/Trim-Pfad).
    # Bewusst MEASUREMENT statt TOTAL_INCREASING: "Anzahl Messungen gesamt" ist
    # kein sinnvoller Langzeit-Zaehler (der Statistics-Graph zeigt sonst nur
    # eine monotone, mehrwertfreie Summe) — Finding N-4.
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, entry, store) -> None:
        super().__init__(coordinator, entry, store, "sensor_bp_history")

    @property
    def native_value(self) -> int:
        return len(self._data.get("readings", []))

    @property
    def extra_state_attributes(self) -> dict:
        readings = sorted(self._data.get("readings", []), key=lambda r: r.get("ts", ""))[-30:]
        return {"history_json": json.dumps(readings, ensure_ascii=False)}


class BloodPressureCategorySensor(HealthOMatSensor):
    """WHO-Kategorie der letzten Messung (REQ-HOM-001).

    Native_value ist der Kategorie-Key (optimal … crisis) und wird über
    ``entity.sensor.blood_pressure_category.state.*`` lokalisiert. Ohne Messung
    → None (HA zeigt `unknown`). Sekundärwerte der klassifizierten Messung
    liegen als Attribute bei — keine eigene Entity je Wert.
    """

    _attr_translation_key = "blood_pressure_category"
    _attr_icon = "mdi:heart-pulse"

    def __init__(self, coordinator, entry, store) -> None:
        super().__init__(coordinator, entry, store, "sensor_bp_category")

    def _sorted_readings(self) -> list[dict]:
        return sorted(self._data.get("readings", []), key=lambda r: r.get("ts", ""))

    @property
    def native_value(self) -> str | None:
        readings = self._sorted_readings()
        if not readings:
            return None
        last = readings[-1]
        return logic.bp_category(last.get("sys"), last.get("dia"))

    @property
    def extra_state_attributes(self) -> dict:
        readings = self._sorted_readings()
        if not readings:
            return {}
        last = readings[-1]
        return {
            "measured_at": last.get("ts"),
            "systolic": last.get("sys"),
            "diastolic": last.get("dia"),
        }


class DrinksTrendSensor(HealthOMatSensor):
    """Getränke-Trend: heute vs. Tages-Ø der Vorwoche in % (REQ-HOM-002).

    Ohne Vorwochendaten (Ø = 0) gibt es keine sinnvolle Prozentänderung →
    None (`unknown`). today_ml und prev_week_avg_ml sind Attribute.
    """

    _attr_translation_key = "drinks_trend"
    _attr_native_unit_of_measurement = "%"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:chart-timeline-variant"

    def __init__(self, coordinator, entry, store) -> None:
        super().__init__(coordinator, entry, store, "sensor_drinks_trend")

    def _trend(self) -> dict | None:
        hour = self._entry.options.get("daily_reset_hour", 0)
        return logic.drinks_trend(self._data.get("drinks", []), dt_util.now(), hour=hour)

    @property
    def native_value(self) -> float | None:
        trend = self._trend()
        return None if trend is None else trend["percent"]

    @property
    def extra_state_attributes(self) -> dict:
        trend = self._trend()
        if trend is None:
            return {}
        return {
            "today_ml": trend["today_ml"],
            "prev_week_avg_ml": trend["prev_week_avg_ml"],
        }


class BpTrendSensor(HealthOMatSensor):
    """Blutdruck-Trend: steigend/fallend/stabil über 7-Tage-Mittel (REQ-HOM-002).

    Native_value ist die Richtung (rising/falling/stable) und wird über
    ``entity.sensor.bp_trend.state.*`` lokalisiert. < 3 gültige Messungen →
    None (`unknown`). sys-/dia-Deltas und die Mittelwerte liegen als Attribute
    bei — keine eigene Entity je Teilwert.
    """

    _attr_translation_key = "bp_trend"
    _attr_icon = "mdi:chart-line"

    def __init__(self, coordinator, entry, store) -> None:
        super().__init__(coordinator, entry, store, "sensor_bp_trend")

    def _trend(self) -> dict | None:
        readings = self._data.get("readings", [])
        return logic.bp_trend(readings, dt_util.now())

    @property
    def native_value(self) -> str | None:
        trend = self._trend()
        return None if trend is None else trend["direction"]

    @property
    def extra_state_attributes(self) -> dict:
        trend = self._trend()
        if trend is None:
            return {}
        return {
            "sys_delta": trend["sys_delta"],
            "dia_delta": trend["dia_delta"],
            "sys_avg_recent": trend["sys_avg_recent"],
            "sys_avg_previous": trend["sys_avg_previous"],
        }


class GoalStreakSensor(HealthOMatSensor):
    """Tage in Folge mit erreichtem Tagesziel (REQ-HOM-003).

    Native_value ist die laufende Serie in Tagen; der heutige Tag zählt nur mit,
    wenn das Ziel bereits erreicht ist. `best_streak` (längste Serie) liegt als
    Attribut bei — kein eigener Sensor je Teilwert (Design-Regel Review §5).
    """

    _attr_translation_key = "goal_streak"
    _attr_native_unit_of_measurement = "d"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:fire"

    def __init__(self, coordinator, entry, store) -> None:
        super().__init__(coordinator, entry, store, "sensor_goal_streak")

    def _streak(self) -> dict:
        hour = self._entry.options.get("daily_reset_hour", 0)
        return logic.goal_streak(
            self._data.get("drinks", []),
            self._entry.runtime_data.daily_goal_ml,
            dt_util.now(),
            hour=hour,
        )

    @property
    def native_value(self) -> int:
        return self._streak()["current_streak"]

    @property
    def extra_state_attributes(self) -> dict:
        return {"best_streak": self._streak()["best_streak"]}


class CaffeineTodaySensor(HealthOMatSensor):
    """Geschätzte Koffeinzufuhr heute in mg (REQ-HOM-004).

    Grobe Schätzung anhand der mg/100-ml-Tabelle in `const.py` — ausdrücklich
    KEINE medizinische Aussage. Der mg-Anteil je Getränketyp liegt als
    JSON-Attribut bei (nur Typen mit > 0 mg); die nackte Summe wäre ohne
    Zuordnung wenig hilfreich.
    """

    _attr_translation_key = "caffeine_today"
    _attr_native_unit_of_measurement = "mg"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:coffee-outline"

    def __init__(self, coordinator, entry, store) -> None:
        super().__init__(coordinator, entry, store, "sensor_caffeine_today")

    def _caffeine(self) -> dict:
        hour = self._entry.options.get("daily_reset_hour", 0)
        return logic.caffeine_today(self._data.get("drinks", []), dt_util.now(), hour=hour)

    @property
    def native_value(self) -> float:
        return self._caffeine()["total_mg"]

    @property
    def extra_state_attributes(self) -> dict:
        return {
            "caffeine_by_type_mg": json.dumps(self._caffeine()["breakdown"], ensure_ascii=False)
        }


class WellbeingSinceSensor(HealthOMatSensor):
    """Zeitpunkt der letzten Wohlbefinden-Meldung."""

    _attr_translation_key = "wellbeing_since"
    _attr_device_class = "timestamp"
    _attr_icon = "mdi:emoticon-outline"

    def __init__(self, coordinator, entry, store) -> None:
        super().__init__(coordinator, entry, store, "sensor_wellbeing_since")

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

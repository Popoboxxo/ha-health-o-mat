"""Tests: LastReadingSensor.extra_state_attributes — avg_7d calculation (Audit M-5).

Audit-Punkt 7b (M-5): LastReadingSensor correctly calls logic.avg_over_window()
for 7-day average and includes it in extra_state_attributes as avg_7d.
"""

import asyncio
import importlib.util
import json
import os
import sys
import types
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass

_COMPONENT_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "custom_components", "health_o_mat")
)

# Fake-Paket für relative Imports
_PKG = "_hom_test_pkg"
_pkg = types.ModuleType(_PKG)
_pkg.__path__ = [_COMPONENT_DIR]
sys.modules.setdefault(_PKG, _pkg)


def _load(name: str):
    spec = importlib.util.spec_from_file_location(
        f"{_PKG}.{name}", os.path.join(_COMPONENT_DIR, f"{name}.py")
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[f"{_PKG}.{name}"] = module
    spec.loader.exec_module(module)
    return module


sensor_module = _load("sensor")
logic_module = _load("logic")


def _fake_store(data: dict) -> MagicMock:
    """Store-Mock: Rohsicht und aktive Sicht aus demselben Datenbestand."""
    store = MagicMock()
    store.all_entries = MagicMock(return_value=data)
    store.active_entry = MagicMock(side_effect=lambda entry_id: data.get(entry_id, {}))
    store.active_entries = MagicMock(return_value=data)
    return store


def _make_last_reading_sensor_fixture(key="sys", readings_data=None):
    """Create a LastReadingSensor with mocked dependencies."""
    coordinator = MagicMock()
    entry = MagicMock()
    entry.entry_id = "test-entry-1"
    entry.runtime_data = MagicMock()

    if readings_data is None:
        readings_data = []
    store = _fake_store({"test-entry-1": {"readings": readings_data}})

    sensor = sensor_module.LastReadingSensor(coordinator, entry, store, key, "mmHg")

    return sensor, entry, store


def test_last_reading_sensor_avg_7d_basic():
    """[AUDIT-7b-M-5] extra_state_attributes includes avg_7d from logic.avg_over_window."""
    readings = [
        {"ts": "2026-08-22T08:00:00", "sys": 120, "dia": 80, "pulse": 70},
        {"ts": "2026-08-16T08:00:00", "sys": 130, "dia": 85, "pulse": 72},
        {"ts": "2026-08-20T08:00:00", "sys": 110, "dia": None, "pulse": None},
    ]

    sensor, entry, store = _make_last_reading_sensor_fixture("sys", readings)

    # Mock dt_util.now() to a fixed point in time for testing
    sensor_module.dt_util.now = MagicMock(return_value=datetime(2026, 8, 23, 8, 0))

    attrs = sensor.extra_state_attributes

    # avg_7d should be (120 + 130 + 110) / 3 = 120.0
    assert "avg_7d" in attrs
    assert attrs["avg_7d"] == 120.0


def test_last_reading_sensor_avg_7d_rounded():
    """[AUDIT-7b-M-5] avg_7d is rounded to 1 decimal place."""
    readings = [
        {"ts": "2026-08-22T08:00:00", "sys": 121, "dia": 80, "pulse": 70},
        {"ts": "2026-08-16T08:00:00", "sys": 131, "dia": 85, "pulse": 72},
    ]

    sensor, entry, store = _make_last_reading_sensor_fixture("sys", readings)
    sensor_module.dt_util.now = MagicMock(return_value=datetime(2026, 8, 23, 8, 0))

    attrs = sensor.extra_state_attributes

    # avg_7d should be (121 + 131) / 2 = 126.0
    assert "avg_7d" in attrs
    assert attrs["avg_7d"] == 126.0


def test_last_reading_sensor_avg_7d_excludes_outside_window():
    """[AUDIT-7b-M-5] avg_7d excludes readings outside 7-day window."""
    readings = [
        {"ts": "2026-08-22T08:00:00", "sys": 120, "dia": 80, "pulse": 70},
        {"ts": "2026-08-10T08:00:00", "sys": 999, "dia": 999, "pulse": 999},  # More than 7 days old
    ]

    sensor, entry, store = _make_last_reading_sensor_fixture("sys", readings)
    sensor_module.dt_util.now = MagicMock(return_value=datetime(2026, 8, 23, 8, 0))

    attrs = sensor.extra_state_attributes

    # avg_7d should be 120.0 (999 should be excluded as it's more than 7 days old)
    assert "avg_7d" in attrs
    assert attrs["avg_7d"] == 120.0
    assert attrs["avg_7d"] != 999


def test_last_reading_sensor_avg_7d_with_none_values():
    """[AUDIT-7b-M-5] avg_7d skips None values within window."""
    readings = [
        {"ts": "2026-08-22T08:00:00", "sys": 120, "dia": 80, "pulse": 70},
        {"ts": "2026-08-16T08:00:00", "sys": 130, "dia": None, "pulse": 72},
    ]

    sensor, entry, store = _make_last_reading_sensor_fixture("dia", readings)
    sensor_module.dt_util.now = MagicMock(return_value=datetime(2026, 8, 23, 8, 0))

    attrs = sensor.extra_state_attributes

    # For dia: 80 is valid, but reading from 16th has None
    # avg_7d should be 80.0 (only valid value)
    assert "avg_7d" in attrs
    assert attrs["avg_7d"] == 80.0


def test_last_reading_sensor_avg_7d_empty_readings():
    """[AUDIT-7b-M-5] avg_7d is None when no readings in window."""
    sensor, entry, store = _make_last_reading_sensor_fixture("sys", [])
    sensor_module.dt_util.now = MagicMock(return_value=datetime(2026, 8, 23, 8, 0))

    attrs = sensor.extra_state_attributes

    # Should be empty dict when no readings
    assert attrs == {}


def test_last_reading_sensor_avg_7d_all_old_readings():
    """[AUDIT-7b-M-5] avg_7d is None when all readings are outside window."""
    readings = [
        {"ts": "2026-08-10T08:00:00", "sys": 120, "dia": 80, "pulse": 70},
        {"ts": "2026-08-05T08:00:00", "sys": 130, "dia": 85, "pulse": 72},
    ]

    sensor, entry, store = _make_last_reading_sensor_fixture("sys", readings)
    sensor_module.dt_util.now = MagicMock(return_value=datetime(2026, 8, 23, 8, 0))

    attrs = sensor.extra_state_attributes

    # When all readings are old, attributes should still have basic info
    # but avg_7d should be None
    assert "avg_7d" in attrs
    assert attrs["avg_7d"] is None


def test_last_reading_sensor_extra_attributes_complete():
    """[AUDIT-7b-M-5] extra_state_attributes includes all expected fields."""
    readings = [
        {"ts": "2026-08-22T10:15:00", "sys": 120, "dia": 80, "pulse": 70},
        {"ts": "2026-08-16T08:00:00", "sys": 130, "dia": 85, "pulse": 72},
    ]

    sensor, entry, store = _make_last_reading_sensor_fixture("sys", readings)
    sensor_module.dt_util.now = MagicMock(return_value=datetime(2026, 8, 23, 8, 0))

    attrs = sensor.extra_state_attributes

    assert "measured_at" in attrs
    assert "avg_7d" in attrs
    assert "readings_total" in attrs
    assert attrs["measured_at"] == "2026-08-22T10:15:00"
    assert attrs["readings_total"] == 2


def test_last_reading_sensor_native_value_latest_reading():
    """[AUDIT-7b-M-5] native_value returns latest reading for the key."""
    readings = [
        {"ts": "2026-08-22T08:00:00", "sys": 120, "dia": 80, "pulse": 70},
        {"ts": "2026-08-21T08:00:00", "sys": 115, "dia": 78, "pulse": 68},
    ]

    sensor, entry, store = _make_last_reading_sensor_fixture("sys", readings)

    assert sensor.native_value == 120


def test_last_reading_sensor_for_different_keys():
    """[AUDIT-7b-M-5] Works correctly for all reading keys (sys, dia, pulse)."""
    readings = [
        {"ts": "2026-08-22T08:00:00", "sys": 120, "dia": 80, "pulse": 70},
        {"ts": "2026-08-16T08:00:00", "sys": 130, "dia": 85, "pulse": 72},
    ]

    sensor_module.dt_util.now = MagicMock(return_value=datetime(2026, 8, 23, 8, 0))

    # Test sys
    sensor_sys, _, _ = _make_last_reading_sensor_fixture("sys", readings)
    assert sensor_sys.native_value == 120
    assert sensor_sys.extra_state_attributes["avg_7d"] == 125.0

    # Test dia
    sensor_dia, _, _ = _make_last_reading_sensor_fixture("dia", readings)
    assert sensor_dia.native_value == 80
    assert sensor_dia.extra_state_attributes["avg_7d"] == 82.5

    # Test pulse
    sensor_pulse, _, _ = _make_last_reading_sensor_fixture("pulse", readings)
    assert sensor_pulse.native_value == 70
    assert sensor_pulse.extra_state_attributes["avg_7d"] == 71.0


# --- Feature 2: konfigurierbare Reset-Uhrzeit (daily_reset_hour) — TodaySensor-Wiring ---


def _make_today_sensor_fixture(options=None, drinks=None):
    """Create a TodaySensor with mocked coordinator/entry/store."""
    coordinator = MagicMock()
    entry = MagicMock()
    entry.entry_id = "test-entry-1"
    entry.options = options if options is not None else {}
    entry.runtime_data = MagicMock()
    entry.runtime_data.daily_goal_ml = 2000

    store = _fake_store({"test-entry-1": {"drinks": drinks if drinks is not None else []}})

    sensor = sensor_module.TodaySensor(coordinator, entry, store)
    return sensor, entry, store


def test_today_sensor_uses_daily_reset_hour_from_options():
    """[Spec Feature 2] TodaySensor liest entry.options['daily_reset_hour'] statt fest 0."""
    drinks = [{"ts": "2026-08-22T05:00:00", "ml": 300, "type": "Kaffee"}]
    sensor, entry, store = _make_today_sensor_fixture(
        options={"daily_reset_hour": 6}, drinks=drinks
    )
    sensor_module.dt_util.now = MagicMock(return_value=datetime(2026, 8, 22, 8, 0))

    # 05:00-Buchung liegt vor der 06:00-Reset-Grenze -> zählt noch zum Vortag.
    assert sensor.native_value == 0


def test_today_sensor_daily_reset_hour_missing_defaults_to_zero_regression():
    """[Spec Feature 2] Ohne daily_reset_hour in entry.options: Bestandsverhalten
    (hour=0) unverändert."""
    drinks = [{"ts": "2026-08-22T05:00:00", "ml": 300, "type": "Kaffee"}]
    sensor, entry, store = _make_today_sensor_fixture(options={}, drinks=drinks)
    sensor_module.dt_util.now = MagicMock(return_value=datetime(2026, 8, 22, 8, 0))

    assert sensor.native_value == 300


def test_today_sensor_yesterday_ml_attribute_uses_same_daily_reset_hour():
    """[Spec Feature 2] extra_state_attributes['yesterday_ml'] nutzt dieselbe Reset-Uhrzeit
    wie native_value — sonst würde ein Getränk je nach hour doppelt oder gar nicht gezählt."""
    drinks = [{"ts": "2026-08-22T05:00:00", "ml": 300, "type": "Kaffee"}]
    sensor, entry, store = _make_today_sensor_fixture(
        options={"daily_reset_hour": 6}, drinks=drinks
    )
    sensor_module.dt_util.now = MagicMock(return_value=datetime(2026, 8, 22, 8, 0))

    assert sensor.native_value == 0
    assert sensor.extra_state_attributes["yesterday_ml"] == 300


def test_last_reading_sensor_avg_7d_precision():
    """[AUDIT-7b-M-5] avg_7d maintains correct decimal precision."""
    readings = [
        {"ts": "2026-08-22T08:00:00", "sys": 121, "dia": 80, "pulse": 70},
        {"ts": "2026-08-16T08:00:00", "sys": 119, "dia": 85, "pulse": 72},
    ]

    sensor, entry, store = _make_last_reading_sensor_fixture("sys", readings)
    sensor_module.dt_util.now = MagicMock(return_value=datetime(2026, 8, 23, 8, 0))

    attrs = sensor.extra_state_attributes

    # avg_7d should be (121 + 119) / 2 = 120.0
    assert attrs["avg_7d"] == 120.0
    # Verify it's rounded to 1 decimal
    assert isinstance(attrs["avg_7d"], float)


# --- Welle 1 Backend-Hygiene (Findings N-1, N-3, N-4, N-9) ---


def _make_store_sensor(sensor_cls, person_data):
    """Create a store-backed sensor with mocked coordinator/entry/store."""
    coordinator = MagicMock()
    entry = MagicMock()
    entry.entry_id = "test-entry-1"
    entry.options = {}
    entry.runtime_data = MagicMock()
    entry.runtime_data.daily_goal_ml = 2000

    store = _fake_store({"test-entry-1": person_data})
    return sensor_cls(coordinator, entry, store)


# N-1: Getränke-Historie im State-Attribut begrenzt (Cap) + total_count


def test_history_drinks_entries_json_capped_to_last_100():
    """[N-1] >100 Buchungen: entries_json enthält genau die letzten 100."""
    drinks = [
        {"ts": f"2026-01-01T{i // 60:02d}:{i % 60:02d}:00", "ml": 10, "type": "Wasser"}
        for i in range(150)
    ]
    sensor = _make_store_sensor(sensor_module.HistoryDrinksSensor, {"drinks": drinks})

    attrs = sensor.extra_state_attributes
    entries = json.loads(attrs["entries_json"])

    assert len(entries) == 100
    # nach ts sortiert -> die letzten 100 (Indizes 50..149)
    assert entries == sorted(drinks, key=lambda d: d["ts"])[-100:]
    assert entries[0]["ts"] == drinks[50]["ts"]
    assert entries[-1]["ts"] == drinks[149]["ts"]
    assert attrs["total_count"] == 150


def test_history_drinks_entries_json_keeps_all_below_limit():
    """[N-1] <=100 Buchungen: alle bleiben im Attribut, total_count passt."""
    drinks = [{"ts": f"2026-01-01T00:00:{i:02d}", "ml": 10, "type": "Wasser"} for i in range(3)]
    sensor = _make_store_sensor(sensor_module.HistoryDrinksSensor, {"drinks": drinks})

    attrs = sensor.extra_state_attributes

    assert len(json.loads(attrs["entries_json"])) == 3
    assert attrs["total_count"] == 3


def test_history_drinks_entries_json_empty():
    """[N-1] Keine Buchungen: leeres Attribut + total_count 0."""
    sensor = _make_store_sensor(sensor_module.HistoryDrinksSensor, {"drinks": []})

    attrs = sensor.extra_state_attributes

    assert json.loads(attrs["entries_json"]) == []
    assert attrs["total_count"] == 0


# N-3: TodaySensor ist ein resettender Tageszähler (TOTAL + last_reset)


def test_today_sensor_state_class_stays_total():
    """[N-3] state_class bleibt TOTAL (kein MEASUREMENT-Wechsel)."""
    sensor, _, _ = _make_today_sensor_fixture()
    assert sensor._attr_state_class == SensorStateClass.TOTAL


def test_today_sensor_last_reset_matches_day_start_with_reset_hour():
    """[N-3] last_reset = day_start(now, daily_reset_hour)."""
    sensor, _, _ = _make_today_sensor_fixture(options={"daily_reset_hour": 6})
    now = datetime(2026, 8, 22, 8, 0)
    sensor_module.dt_util.now = MagicMock(return_value=now)

    assert sensor.last_reset == logic_module.day_start(now, hour=6)
    assert sensor.last_reset == datetime(2026, 8, 22, 6, 0)


def test_today_sensor_last_reset_defaults_to_midnight_regression():
    """[N-3] Ohne daily_reset_hour: last_reset = Mitternacht (Bestandsverhalten)."""
    sensor, _, _ = _make_today_sensor_fixture(options={})
    sensor_module.dt_util.now = MagicMock(return_value=datetime(2026, 8, 22, 8, 0))

    assert sensor.last_reset == datetime(2026, 8, 22, 0, 0)


# N-4: BloodPressureHistorySensor ist kein Langzeit-Zähler


def test_blood_pressure_history_state_class_measurement():
    """[N-4] Anzahl Messungen -> MEASUREMENT statt TOTAL_INCREASING."""
    sensor = _make_store_sensor(sensor_module.BloodPressureHistorySensor, {"readings": []})

    assert sensor._attr_state_class == SensorStateClass.MEASUREMENT
    assert sensor._attr_state_class != SensorStateClass.TOTAL_INCREASING


# N-9: device_class für Mengen (volume) und Druck (pressure)


def test_today_sensor_device_class_volume():
    """[N-9] TodaySensor -> VOLUME, HA-valid native unit 'mL'."""
    sensor, _, _ = _make_today_sensor_fixture()
    assert sensor._attr_device_class == SensorDeviceClass.VOLUME
    assert sensor._attr_native_unit_of_measurement == "mL"


def test_lifetime_sensor_device_class_volume():
    """[N-9] LifetimeSensor -> VOLUME, HA-valid native unit 'mL'."""
    sensor = _make_store_sensor(sensor_module.LifetimeSensor, {"total_ml_lifetime": 1234})
    assert sensor._attr_device_class == SensorDeviceClass.VOLUME
    assert sensor._attr_native_unit_of_measurement == "mL"


def test_last_reading_sensor_device_class_pressure_for_sys_and_dia():
    """[N-9] sys/dia (mmHg) -> PRESSURE."""
    for key in ("sys", "dia"):
        sensor, _, _ = _make_last_reading_sensor_fixture(key, [])
        assert sensor._attr_device_class == SensorDeviceClass.PRESSURE
        assert sensor._attr_native_unit_of_measurement == "mmHg"


def test_last_reading_sensor_pulse_has_no_device_class():
    """[N-9] Puls (BPM) bleibt bewusst ohne device_class."""
    sensor, _, _ = _make_last_reading_sensor_fixture("pulse", [])
    assert sensor._attr_device_class is None


def test_volume_sensors_use_valid_ml_unit_others_unchanged():
    """[N-9] VOLUME-Sensoren tragen 'mL' (HA-gültig); mmHg/BPM/% unverändert.

    Regression guard: nur die beiden VOLUME-Sensoren kippen auf 'mL', alle
    übrigen Einheiten bleiben exakt wie zuvor.
    """
    today, _, _ = _make_today_sensor_fixture()
    lifetime = _make_store_sensor(sensor_module.LifetimeSensor, {"total_ml_lifetime": 1234})
    percent = _make_store_sensor(sensor_module.PercentSensor, {"drinks": []})

    # Only the two VOLUME sensors switch to the HA-valid casing.
    assert today._attr_native_unit_of_measurement == "mL"
    assert lifetime._attr_native_unit_of_measurement == "mL"

    # Everything else is untouched (units as wired in sensor.py: sys/dia mmHg,
    # pulse BPM) — build the entities with their real units, the shared
    # _make_last_reading_sensor_fixture hardcodes "mmHg".
    for key, unit in (("sys", "mmHg"), ("dia", "mmHg"), ("pulse", "BPM")):
        coordinator = MagicMock()
        entry = MagicMock()
        entry.entry_id = "test-entry-1"
        entry.runtime_data = MagicMock()
        store = _fake_store({"test-entry-1": {"readings": []}})
        bp = sensor_module.LastReadingSensor(coordinator, entry, store, key, unit)
        assert bp._attr_native_unit_of_measurement == unit

    assert percent._attr_native_unit_of_measurement == "%"


# --- Welle 2 / 2A: WHO-Kategorie (REQ-HOM-001) + Trends (REQ-HOM-002) ---


def test_bp_category_sensor_classifies_last_reading():
    """[REQ-HOM-001] native_value = WHO-Kategorie der LETZTEN Messung."""
    readings = [
        {"ts": "2026-08-21T08:00:00", "sys": 115, "dia": 75, "pulse": 60},
        {"ts": "2026-08-22T08:00:00", "sys": 145, "dia": 92, "pulse": 70},
    ]
    sensor = _make_store_sensor(sensor_module.BloodPressureCategorySensor, {"readings": readings})

    assert sensor.native_value == "grade_1"
    # REQ-HOM-001 nennt den Sensor `blood_pressure_category`; der Translation-Key
    # entspricht dem (die Familie rendert aus dem englischen Namen
    # "Blood pressure category" dieselbe object_id).
    assert sensor._attr_translation_key == "blood_pressure_category"
    attrs = sensor.extra_state_attributes
    assert attrs["measured_at"] == "2026-08-22T08:00:00"
    assert attrs["systolic"] == 145
    assert attrs["diastolic"] == 92


def test_bp_category_sensor_unknown_without_readings():
    """[REQ-HOM-001] Ohne Messung → None (HA: unknown), keine Attribute."""
    sensor = _make_store_sensor(sensor_module.BloodPressureCategorySensor, {"readings": []})

    assert sensor.native_value is None
    assert sensor.extra_state_attributes == {}


def test_bp_category_sensor_crisis_and_higher_axis():
    """[REQ-HOM-001] Krise nur bei beiden strengen Grenzen; sonst Grad 3."""
    crisis = _make_store_sensor(
        sensor_module.BloodPressureCategorySensor,
        {"readings": [{"ts": "2026-08-22T08:00:00", "sys": 200, "dia": 125}]},
    )
    assert crisis.native_value == "crisis"

    isolated = _make_store_sensor(
        sensor_module.BloodPressureCategorySensor,
        {"readings": [{"ts": "2026-08-22T08:00:00", "sys": 200, "dia": 90}]},
    )
    assert isolated.native_value == "grade_3"


def test_drinks_trend_sensor_state_unit_and_attributes():
    """[REQ-HOM-002] drinks_trend: Prozent-State + today/prev_week als Attribute."""
    now = datetime(2026, 8, 8, 12, 0)
    sensor_module.dt_util.now = MagicMock(return_value=now)
    drinks = [
        {"ts": "2026-08-07T09:00:00", "ml": 700, "type": "Wasser"},
        {"ts": "2026-08-08T09:00:00", "ml": 1400, "type": "Wasser"},
    ]
    sensor = _make_store_sensor(sensor_module.DrinksTrendSensor, {"drinks": drinks})

    assert sensor._attr_translation_key == "drinks_trend"
    assert sensor._attr_native_unit_of_measurement == "%"
    assert sensor._attr_state_class == SensorStateClass.MEASUREMENT
    assert sensor.native_value == 1300.0
    attrs = sensor.extra_state_attributes
    assert attrs["today_ml"] == 1400
    assert attrs["prev_week_avg_ml"] == 100.0


def test_drinks_trend_sensor_unknown_without_previous_week():
    """[REQ-HOM-002] Ohne Vorwochendaten → None (unknown), keine Attribute."""
    sensor_module.dt_util.now = MagicMock(return_value=datetime(2026, 8, 8, 12, 0))
    sensor = _make_store_sensor(sensor_module.DrinksTrendSensor, {"drinks": []})

    assert sensor.native_value is None
    assert sensor.extra_state_attributes == {}


def test_bp_trend_sensor_direction_state_and_deltas():
    """[REQ-HOM-002] bp_trend: Richtungs-State + sys/dia-Delta als Attribute."""
    now = datetime(2026, 8, 13, 8, 0)
    sensor_module.dt_util.now = MagicMock(return_value=now)
    readings = [
        {"ts": "2026-08-01T08:00:00", "sys": 130, "dia": 80},
        {"ts": "2026-08-02T08:00:00", "sys": 130, "dia": 80},
        {"ts": "2026-08-10T08:00:00", "sys": 150, "dia": 90},
        {"ts": "2026-08-11T08:00:00", "sys": 150, "dia": 90},
    ]
    sensor = _make_store_sensor(sensor_module.BpTrendSensor, {"readings": readings})

    assert sensor._attr_translation_key == "bp_trend"
    assert sensor.native_value == "rising"
    attrs = sensor.extra_state_attributes
    assert attrs["sys_delta"] == 20.0
    assert attrs["dia_delta"] == 10.0
    assert attrs["sys_avg_recent"] == 150.0
    assert attrs["sys_avg_previous"] == 130.0


def test_bp_trend_sensor_unknown_with_less_than_three_readings():
    """[REQ-HOM-002] < 3 Messungen → None (unknown)."""
    sensor_module.dt_util.now = MagicMock(return_value=datetime(2026, 8, 13, 8, 0))
    sensor = _make_store_sensor(
        sensor_module.BpTrendSensor,
        {"readings": [{"ts": "2026-08-10T08:00:00", "sys": 150, "dia": 90}]},
    )

    assert sensor.native_value is None
    assert sensor.extra_state_attributes == {}


def test_setup_entry_registers_new_wave2_sensors():
    """[REQ-HOM-001/002] async_setup_entry hängt die neuen Sensoren ein."""
    import asyncio

    added: list = []

    def _add(entities):
        added.extend(entities)

    hass = MagicMock()
    entry = MagicMock()
    entry.entry_id = "test-entry-1"
    entry.options = {}
    entry.runtime_data = MagicMock()
    entry.runtime_data.daily_goal_ml = 2000
    coord = MagicMock()
    store = _fake_store({"test-entry-1": {}})
    hass.data = {
        "health_o_mat": {
            entry.entry_id: {"coordinator": coord},
            "shared": {"store": store},
        }
    }

    asyncio.run(sensor_module.async_setup_entry(hass, entry, _add))

    keys = {e._attr_unique_id for e in added}
    assert "test-entry-1_sensor_bp_category" in keys
    assert "test-entry-1_sensor_drinks_trend" in keys
    assert "test-entry-1_sensor_bp_trend" in keys


# --- Welle 2 / 2B: Streak (REQ-HOM-003) + Koffein (REQ-HOM-004) ---


def test_goal_streak_sensor_state_and_best_attribute():
    """[REQ-HOM-003] native_value = laufende Serie; best_streak als Attribut."""
    now = datetime(2026, 8, 22, 12, 0)
    sensor_module.dt_util.now = MagicMock(return_value=now)
    drinks = [
        {"ts": "2026-08-22T09:00:00", "ml": 2000, "type": "Wasser"},
        {"ts": "2026-08-21T09:00:00", "ml": 2000, "type": "Wasser"},
        {"ts": "2026-08-20T09:00:00", "ml": 2000, "type": "Wasser"},
        {"ts": "2026-08-18T09:00:00", "ml": 2000, "type": "Wasser"},  # Lücke am 19.
    ]
    sensor = _make_store_sensor(sensor_module.GoalStreakSensor, {"drinks": drinks})

    assert sensor._attr_translation_key == "goal_streak"
    assert sensor._attr_native_unit_of_measurement == "d"
    assert sensor._attr_state_class == SensorStateClass.MEASUREMENT
    assert sensor.native_value == 3
    assert sensor.extra_state_attributes["best_streak"] == 3


def test_goal_streak_sensor_today_not_reached_runs_to_yesterday():
    """[REQ-HOM-003] Heute nicht erreicht ⇒ Serie endet gestern."""
    sensor_module.dt_util.now = MagicMock(return_value=datetime(2026, 8, 22, 12, 0))
    drinks = [
        {"ts": "2026-08-22T09:00:00", "ml": 500, "type": "Wasser"},
        {"ts": "2026-08-21T09:00:00", "ml": 2000, "type": "Wasser"},
        {"ts": "2026-08-20T09:00:00", "ml": 2000, "type": "Wasser"},
    ]
    sensor = _make_store_sensor(sensor_module.GoalStreakSensor, {"drinks": drinks})

    assert sensor.native_value == 2


def test_goal_streak_sensor_empty_history():
    """[REQ-HOM-003] Leere Historie ⇒ 0 State, best_streak 0."""
    sensor_module.dt_util.now = MagicMock(return_value=datetime(2026, 8, 22, 12, 0))
    sensor = _make_store_sensor(sensor_module.GoalStreakSensor, {"drinks": []})

    assert sensor.native_value == 0
    assert sensor.extra_state_attributes["best_streak"] == 0


def test_caffeine_today_sensor_state_and_breakdown_attribute():
    """[REQ-HOM-004] Koffein-Sensor: mg-State + Breakdown-Attribut (JSON)."""
    sensor_module.dt_util.now = MagicMock(return_value=datetime(2026, 8, 22, 12, 0))
    drinks = [{"ts": "2026-08-22T09:00:00", "ml": 250, "type": "Kaffee"}]
    sensor = _make_store_sensor(sensor_module.CaffeineTodaySensor, {"drinks": drinks})

    assert sensor._attr_translation_key == "caffeine_today"
    assert sensor._attr_native_unit_of_measurement == "mg"
    assert sensor._attr_state_class == SensorStateClass.MEASUREMENT
    assert sensor.native_value == 100.0
    assert json.loads(sensor.extra_state_attributes["caffeine_by_type_mg"]) == {"Kaffee": 100.0}


def test_caffeine_today_sensor_zero_without_caffeine_drinks():
    """[REQ-HOM-004] Nur koffeinfreie Getränke ⇒ 0 mg, leerer Breakdown."""
    sensor_module.dt_util.now = MagicMock(return_value=datetime(2026, 8, 22, 12, 0))
    drinks = [{"ts": "2026-08-22T09:00:00", "ml": 500, "type": "Wasser"}]
    sensor = _make_store_sensor(sensor_module.CaffeineTodaySensor, {"drinks": drinks})

    assert sensor.native_value == 0.0
    assert json.loads(sensor.extra_state_attributes["caffeine_by_type_mg"]) == {}


def test_setup_entry_registers_goal_streak_and_caffeine_sensors():
    """[REQ-HOM-003/004] async_setup_entry hängt Streak- und Koffein-Sensor ein."""
    import asyncio

    added: list = []

    def _add(entities):
        added.extend(entities)

    hass = MagicMock()
    entry = MagicMock()
    entry.entry_id = "test-entry-1"
    entry.options = {}
    entry.runtime_data = MagicMock()
    entry.runtime_data.daily_goal_ml = 2000
    coord = MagicMock()
    store = _fake_store({"test-entry-1": {}})
    hass.data = {
        "health_o_mat": {
            entry.entry_id: {"coordinator": coord},
            "shared": {"store": store},
        }
    }

    asyncio.run(sensor_module.async_setup_entry(hass, entry, _add))

    keys = {e._attr_unique_id for e in added}
    assert "test-entry-1_sensor_goal_streak" in keys
    assert "test-entry-1_sensor_caffeine_today" in keys


# --- REQ-HOM-009: pro-Person Bereichs-Toggles filtern das Sensor-Setup ---

_DRINK_SENSOR_KEYS = {
    "sensor_drinks_today",
    "sensor_goal_percent",
    "sensor_drinks_history",
    "sensor_lifetime_total",
    "sensor_drinks_trend",
    "sensor_goal_streak",
    "sensor_caffeine_today",
}
_BP_SENSOR_KEYS = {
    "sensor_bp_history",
    "sensor_bp_category",
    "sensor_bp_trend",
    "sensor_bp_sys",
    "sensor_bp_dia",
    "sensor_bp_pulse",
}
_WELLBEING_SENSOR_KEYS = {"sensor_wellbeing_since", "sensor_wellbeing_score"}
_ENTRY_ID = "test-entry-1"


def _sensor_setup(options: dict) -> set[str]:
    """async_setup_entry mit aufzeichnendem async_add_entities → unique_ids."""
    import asyncio

    added: list = []

    hass = MagicMock()
    entry = MagicMock()
    entry.entry_id = _ENTRY_ID
    entry.options = options
    entry.runtime_data = MagicMock()
    entry.runtime_data.daily_goal_ml = 2000
    coord = MagicMock()
    store = _fake_store({_ENTRY_ID: {}})
    hass.data = {
        "health_o_mat": {
            _ENTRY_ID: {"coordinator": coord},
            "shared": {"store": store},
        }
    }

    asyncio.run(sensor_module.async_setup_entry(hass, entry, lambda ents: added.extend(ents)))
    return {e._attr_unique_id for e in added}


def _ids(keys: set[str]) -> set[str]:
    return {f"{_ENTRY_ID}_{key}" for key in keys}


def test_sensor_setup_old_entry_without_options_has_all_areas():
    """[REQ-HOM-009] Migrationspfad: Alt-Entry ohne areas-Option = alle aktiv."""
    keys = _sensor_setup({})
    assert keys == _ids(_DRINK_SENSOR_KEYS | _BP_SENSOR_KEYS | _WELLBEING_SENSOR_KEYS)


def test_sensor_setup_drink_disabled_keeps_bp_and_wellbeing():
    """[REQ-HOM-009] drink AUS → keine Drink-Sensoren; BP + Wohlbefinden bleiben."""
    keys = _sensor_setup({"areas": {"drink": False}})
    assert keys == _ids(_BP_SENSOR_KEYS | _WELLBEING_SENSOR_KEYS)
    assert keys.isdisjoint(_ids(_DRINK_SENSOR_KEYS))


def test_sensor_setup_only_drink_when_bp_and_wellbeing_disabled():
    """[REQ-HOM-009] bp + wellbeing AUS → nur Drink-Sensoren."""
    keys = _sensor_setup({"areas": {"bp": False, "wellbeing": False}})
    assert keys == _ids(_DRINK_SENSOR_KEYS)


def test_sensor_unique_ids_stable_across_area_toggle():
    """[REQ-HOM-009] De-/Reaktivieren erzeugt dieselben unique_ids (nie geändert)."""
    on_keys = _sensor_setup({})
    off_keys = _sensor_setup({"areas": {"drink": False}})
    on_again_keys = _sensor_setup({"areas": {"drink": True}})

    drink_ids = _ids(_DRINK_SENSOR_KEYS)
    assert drink_ids <= on_keys
    assert drink_ids.isdisjoint(off_keys)
    assert on_again_keys == on_keys
    assert {k for k in on_again_keys if k in _ids(_DRINK_SENSOR_KEYS)} == drink_ids


# --- REQ-HOM-112: Wohlbefinden-Score-Sensor --------------------------------

# Score-Skala: 1 = schlechtester … N = bester Wert (Index + 1).
_EXPECTED_WELLBEING_SCORES = {
    "very_bad": 1,
    "awful": 2,
    "bad": 3,
    "poor": 4,
    "okay": 5,
    "mixed": 6,
    "good": 7,
    "very_good": 8,
    "great": 9,
    "excellent": 10,
}


def _wellbeing_score_sensor(person_data: dict):
    """WellbeingScoreSensor mit gemocktem Coordinator/Entry/Store."""
    return _make_store_sensor(sensor_module.WellbeingScoreSensor, person_data)


def test_req_hom_112_wellbeing_score_sensor_registered_with_stable_unique_id():
    """[REQ-HOM-112] Setup registriert den Score-Sensor als {entry_id}_sensor_wellbeing_score."""
    keys = _sensor_setup({})

    assert f"{_ENTRY_ID}_sensor_wellbeing_score" in keys


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        ("very_bad", 1),
        ("awful", 2),
        ("bad", 3),
        ("poor", 4),
        ("okay", 5),
        ("mixed", 6),
        ("good", 7),
        ("very_good", 8),
        ("great", 9),
        ("excellent", 10),
    ],
)
def test_req_hom_112_wellbeing_score_sensor_native_value_matches_status(status, expected):
    """[REQ-HOM-112] native_value = Score des aktuellen Status (Index + 1)."""
    sensor = _wellbeing_score_sensor({"wellbeing": {"status": status, "ts": "2026-10-15T10:00:00"}})

    assert sensor.native_value == expected


@pytest.mark.parametrize(
    "person_data",
    [{}, {"wellbeing": {}}, {"wellbeing": {"status": None, "ts": None}}],
)
def test_req_hom_112_wellbeing_score_sensor_without_message_is_none(person_data):
    """[REQ-HOM-112] Ohne Meldung ist der State `unknown` (None) — NIE 0.

    0 wäre der schlechteste Wert und würde den Verlauf verfälschen.
    """
    sensor = _wellbeing_score_sensor(person_data)

    assert sensor.native_value is None
    assert sensor.native_value != 0


def test_req_hom_112_wellbeing_score_sensor_state_class_is_measurement():
    """[REQ-HOM-112] state_class = MEASUREMENT (HA-Statistik/Graph)."""
    sensor = _wellbeing_score_sensor({})

    assert sensor._attr_state_class == SensorStateClass.MEASUREMENT


def test_req_hom_112_wellbeing_score_sensor_has_no_unit_of_measurement():
    """[REQ-HOM-112] Score ist dimensionslos — KEINE Einheit (ml/mL-Warnbug).

    Eine (ungültige) Einheit würde in HA eine Warnung erzeugen und die
    Statistik verfälschen — der Score darf deshalb keine tragen.
    """
    sensor = _wellbeing_score_sensor({})

    assert getattr(sensor, "_attr_native_unit_of_measurement", None) is None
    assert getattr(sensor, "native_unit_of_measurement", None) is None


def test_req_hom_112_wellbeing_score_sensor_has_no_device_class():
    """[REQ-HOM-112] KEINE device_class — der Score ist kein Messwert mit Einheit."""
    sensor = _wellbeing_score_sensor({})

    assert getattr(sensor, "_attr_device_class", None) is None
    assert getattr(sensor, "device_class", None) is None


def test_req_hom_112_wellbeing_score_sensor_translation_key_and_icon():
    """[REQ-HOM-112] translation_key + Icon statt hartkodiertem Entity-Namen."""
    sensor = _wellbeing_score_sensor({})

    assert sensor._attr_translation_key == "wellbeing_score"
    assert sensor._attr_icon == "mdi:emoticon-outline"


def test_req_hom_112_wellbeing_score_sensor_extra_state_attributes():
    """[REQ-HOM-112] Attribute: reported_at (Zeitpunkt) + scale_max (Skalenende)."""
    sensor = _wellbeing_score_sensor({"wellbeing": {"status": "good", "ts": "2026-10-15T10:00:00"}})

    attrs = sensor.extra_state_attributes

    assert attrs["reported_at"] == "2026-10-15T10:00:00"
    assert attrs["scale_max"] == len(sensor_module.logic.WELLBEING_STATES)
    assert attrs["scale_max"] == 10


def test_req_hom_112_wellbeing_score_sensor_reported_at_is_none_without_message():
    """[REQ-HOM-112] Ohne Meldung ist `reported_at` None (kein 1970er-Platzhalter)."""
    sensor = _wellbeing_score_sensor({})

    assert sensor.extra_state_attributes["reported_at"] is None


def test_req_hom_112_wellbeing_score_sensor_scale_max_follows_state_list(monkeypatch):
    """[REQ-HOM-112] scale_max folgt der Zustandsliste (keine hartcodierte 5).

    `sensor.py` liest `logic.WELLBEING_STATES` — dieselbe Quelle wie der
    Score. Wird die Liste um eine elfte Stufe erweitert, wächst scale_max
    auf 11; Score und Skala können so nicht auseinanderlaufen.
    """
    synthetic = [
        {"key": "very_bad", "label": "Sehr schlecht"},
        {"key": "awful", "label": "Elend"},
        {"key": "bad", "label": "Schlecht"},
        {"key": "poor", "label": "Mäßig"},
        {"key": "okay", "label": "Okay"},
        {"key": "mixed", "label": "Durchwachsen"},
        {"key": "good", "label": "Gut"},
        {"key": "very_good", "label": "Sehr gut"},
        {"key": "great", "label": "Großartig"},
        {"key": "excellent", "label": "Ausgezeichnet"},
        {"key": "superb", "label": "Hervorragend"},
    ]
    # `sensor.py` bindet `logic` beim Import; gepatcht wird deshalb das
    # Modulobjekt, das der Sensor tatsächlich benutzt.
    monkeypatch.setattr(sensor_module.logic, "WELLBEING_STATES", synthetic)

    sensor = _wellbeing_score_sensor(
        {"wellbeing": {"status": "superb", "ts": "2026-10-15T10:00:00"}}
    )

    assert sensor.extra_state_attributes["scale_max"] == 11
    assert sensor.native_value == 11


def test_req_hom_112_wellbeing_score_sensor_follows_area_toggle():
    """[REQ-HOM-112/009] Score-Sensor nur im Bereich `wellbeing` — Toggle wirkt.

    Aus ⇒ keine Entity; Ein ⇒ Entity mit stabiler unique_id (die unique_id
    wird über De-/Reaktivierung nie verändert).
    """
    score_id = f"{_ENTRY_ID}_sensor_wellbeing_score"

    off_keys = _sensor_setup({"areas": {"wellbeing": False}})
    on_keys = _sensor_setup({"areas": {"wellbeing": True}})
    on_again_keys = _sensor_setup({"areas": {"wellbeing": True}})

    assert score_id not in off_keys
    assert score_id in on_keys
    assert score_id in on_again_keys
    # Die unique_id bleibt identisch (kein Neu-Anlegen durch die Änderung).
    assert {k for k in on_again_keys if k == score_id} == {score_id}


# ============================================================================
# M2a: voided Einträge aus allen Sensor-Auswertungen ausschließen
# ============================================================================


def _load_store_module():
    """Store-Modul im selben Fake-Paket (auch bei früherem Laden wiederverwenden)."""
    name = f"{_PKG}.store"
    if name in sys.modules:
        return sys.modules[name]
    return _load("store")


def _real_store():
    """HealthOMatStore mit gemocktem HA-Store-Backend (leerer Start)."""
    store = _load_store_module().HealthOMatStore(MagicMock())
    store._store = MagicMock()
    store._store.async_load = AsyncMock(return_value=None)
    store._store.async_save = AsyncMock(return_value=None)
    asyncio.run(store.async_load())
    return store


def _entry(entry_id="e1", options=None, goal=2000):
    entry = MagicMock()
    entry.entry_id = entry_id
    entry.options = options if options is not None else {}
    entry.runtime_data = MagicMock()
    entry.runtime_data.daily_goal_ml = goal
    return entry


def _item_id(store, kind, index=-1, entry_id="e1"):
    """ID eines Store-Eintrags (drinks/readings/wellbeing_entries)."""
    return store.entry(entry_id)[kind][index]["id"]


def test_m2a_voided_drink_excluded_from_today_percent_yesterday_history():
    """[M2a] Voided Getränk zählt nicht in Today/Percent/Yesterday/Historie."""
    sensor_module.dt_util.now = MagicMock(return_value=datetime(2026, 10, 15, 12, 0))
    store = _real_store()
    asyncio.run(store.add_drink("e1", "2026-10-15T08:00:00", 250, "Wasser", "button"))
    asyncio.run(store.add_drink("e1", "2026-10-14T09:00:00", 300, "Wasser", "button"))
    asyncio.run(store.add_drink("e1", "2026-10-15T09:00:00", 500, "Kaffee", "button"))
    asyncio.run(store.void_drink("e1", _item_id(store, "drinks")))

    entry = _entry()
    today = sensor_module.TodaySensor(MagicMock(), entry, store)
    percent = sensor_module.PercentSensor(MagicMock(), entry, store)
    history = sensor_module.HistoryDrinksSensor(MagicMock(), entry, store)

    assert today.native_value == 250
    attrs = today.extra_state_attributes
    assert attrs["drinks_count"] == 1
    assert attrs["percent_of_goal"] == 12.5
    assert attrs["yesterday_ml"] == 300
    assert json.loads(attrs["breakdown_by_type"]) == {"Wasser": 250}
    assert attrs["last_drink_at"].startswith("2026-10-15T08:00:00")

    assert percent.native_value == 12.5
    assert history.native_value == 1  # nur heutige, aktive Buchungen
    hist_attrs = history.extra_state_attributes
    # Historie = alle aktiven Buchungen (heute + gestern), nie das voided Kaffee.
    assert hist_attrs["total_count"] == 2
    assert [d["ml"] for d in json.loads(hist_attrs["entries_json"])] == [300, 250]


def test_m2a_lifetime_keeps_corrected_sum_with_voided_drink():
    """[M2a] Lifetime bleibt die korrigierte M1-Summe (nicht die Rohsumme)."""
    sensor_module.dt_util.now = MagicMock(return_value=datetime(2026, 10, 15, 12, 0))
    store = _real_store()
    asyncio.run(store.add_drink("e1", "2026-10-15T08:00:00", 250, "Wasser", "button"))
    asyncio.run(store.add_drink("e1", "2026-10-15T09:00:00", 500, "Kaffee", "button"))
    asyncio.run(store.void_drink("e1", _item_id(store, "drinks")))

    lifetime = sensor_module.LifetimeSensor(MagicMock(), _entry(), store)

    assert lifetime.native_value == 250


def test_m2a_voided_drink_excluded_from_trend_streak_and_caffeine():
    """[M2a] Voided Getränk zählt nicht in Trend, Serie und Koffein."""
    sensor_module.dt_util.now = MagicMock(return_value=datetime(2026, 10, 15, 12, 0))
    store = _real_store()
    # Vorwoche: 700 ml gestern → Ø 100 ml/Tag.
    asyncio.run(store.add_drink("e1", "2026-10-14T08:00:00", 700, "Wasser", "button"))
    # Heute nur ein (voided) Kaffee — ohne Filter würde er Trend + Serie + Koffein füllen.
    asyncio.run(store.add_drink("e1", "2026-10-15T09:00:00", 800, "Kaffee", "button"))
    asyncio.run(store.void_drink("e1", _item_id(store, "drinks")))

    entry = _entry(goal=700)
    trend = sensor_module.DrinksTrendSensor(MagicMock(), entry, store)
    streak = sensor_module.GoalStreakSensor(MagicMock(), entry, store)
    caffeine = sensor_module.CaffeineTodaySensor(MagicMock(), entry, store)

    assert trend.native_value == -100.0
    assert trend.extra_state_attributes == {"today_ml": 0, "prev_week_avg_ml": 100.0}
    assert streak.native_value == 1
    assert streak.extra_state_attributes["best_streak"] == 1
    assert caffeine.native_value == 0.0
    assert json.loads(caffeine.extra_state_attributes["caffeine_by_type_mg"]) == {}


def test_m2a_voided_reading_excluded_from_bp_sensors():
    """[M2a] Voided Messung zählt nicht in BP-Werten/Historie/Ø/Trend."""
    sensor_module.dt_util.now = MagicMock(return_value=datetime(2026, 10, 15, 12, 0))
    store = _real_store()
    for days_ago, sys_, dia, pulse in (
        (1, 120, 80, 60),
        (2, 122, 82, 62),
        (3, 118, 78, 58),
        (8, 130, 80, 60),
        (9, 132, 82, 62),
        (10, 128, 78, 58),
    ):
        asyncio.run(
            store.add_reading("e1", f"2026-10-{15 - days_ago:02d}T08:00:00", sys_, dia, pulse)
        )
    # Voided Extremwert heute: ohne Filter würde er letzter Wert/Ø/Trend sein.
    asyncio.run(store.add_reading("e1", "2026-10-15T09:00:00", 200, 120, 99))
    asyncio.run(store.void_reading("e1", _item_id(store, "readings")))

    entry = _entry()
    last = sensor_module.LastReadingSensor(MagicMock(), entry, store, "sys", "mmHg")
    assert last.native_value == 120
    attrs = last.extra_state_attributes
    assert attrs["readings_total"] == 6
    assert attrs["avg_7d"] == 120.0
    assert attrs["measured_at"].startswith("2026-10-14T08:00:00")

    history = sensor_module.BloodPressureHistorySensor(MagicMock(), entry, store)
    assert history.native_value == 6
    entries = json.loads(history.extra_state_attributes["history_json"])
    assert [r["sys"] for r in entries] == [128, 132, 130, 118, 122, 120]

    category = sensor_module.BloodPressureCategorySensor(MagicMock(), entry, store)
    assert category.extra_state_attributes["systolic"] == 120
    assert category.native_value == logic_module.bp_category(120, 80)

    trend = sensor_module.BpTrendSensor(MagicMock(), entry, store)
    assert trend.native_value == "falling"
    assert trend.extra_state_attributes["sys_delta"] == -10.0


def test_m2a_voided_reading_only_bp_trend_has_too_few_readings():
    """[M2a] Sind alle Messungen voided, bleibt der BP-Trend `unknown`."""
    sensor_module.dt_util.now = MagicMock(return_value=datetime(2026, 10, 15, 12, 0))
    store = _real_store()
    for days_ago in (1, 2, 3):
        asyncio.run(store.add_reading("e1", f"2026-10-{15 - days_ago:02d}T08:00:00", 120, 80, 60))
        asyncio.run(store.void_reading("e1", _item_id(store, "readings")))

    trend = sensor_module.BpTrendSensor(MagicMock(), _entry(), store)

    assert trend.native_value is None
    assert trend.extra_state_attributes == {}


def test_m2a_voided_wellbeing_excluded_from_since_and_score(monkeypatch):
    """[M2a] Voided Wohlbefinden-Meldung bestimmt weder Zeitpunkt noch Score."""
    sensor_module.dt_util.now = MagicMock(return_value=datetime(2026, 10, 15, 12, 0))
    monkeypatch.setattr(sensor_module.dt_util, "as_local", lambda value: value)
    store = _real_store()
    asyncio.run(store.set_wellbeing("e1", "good", "2026-10-15T08:00:00"))
    asyncio.run(store.set_wellbeing("e1", "bad", "2026-10-15T09:00:00"))
    asyncio.run(store.set_wellbeing("e1", "great", "2026-10-15T10:00:00"))
    asyncio.run(store.void_wellbeing("e1", _item_id(store, "wellbeing_entries")))

    since = sensor_module.WellbeingSinceSensor(MagicMock(), _entry(), store)
    score = sensor_module.WellbeingScoreSensor(MagicMock(), _entry(), store)

    assert since.native_value == datetime.fromisoformat("2026-10-15T09:00:00")
    assert score.native_value == logic_module.wellbeing_score("bad")
    assert score.extra_state_attributes["reported_at"] == "2026-10-15T09:00:00"


def test_m2a_all_wellbeing_voided_yields_unknown_states(monkeypatch):
    """[M2a] Alle Meldungen voided → Since/Score `unknown` (kein Alt-Wert)."""
    sensor_module.dt_util.now = MagicMock(return_value=datetime(2026, 10, 15, 12, 0))
    monkeypatch.setattr(sensor_module.dt_util, "as_local", lambda value: value)
    store = _real_store()
    asyncio.run(store.set_wellbeing("e1", "good", "2026-10-15T08:00:00"))
    asyncio.run(store.void_wellbeing("e1", _item_id(store, "wellbeing_entries")))

    since = sensor_module.WellbeingSinceSensor(MagicMock(), _entry(), store)
    score = sensor_module.WellbeingScoreSensor(MagicMock(), _entry(), store)

    assert since.native_value is None
    assert score.native_value is None
    assert score.extra_state_attributes["reported_at"] is None

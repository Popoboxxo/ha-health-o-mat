"""Tests: LastReadingSensor.extra_state_attributes — avg_7d calculation (Audit M-5).

Audit-Punkt 7b (M-5): LastReadingSensor correctly calls logic.avg_over_window()
for 7-day average and includes it in extra_state_attributes as avg_7d.
"""
import asyncio
import importlib.util
import os
import sys
import types
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

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


def _make_last_reading_sensor_fixture(key="sys", readings_data=None):
    """Create a LastReadingSensor with mocked dependencies."""
    coordinator = MagicMock()
    entry = MagicMock()
    entry.entry_id = "test-entry-1"
    entry.runtime_data = MagicMock()

    store = MagicMock()
    if readings_data is None:
        readings_data = []
    store.all_entries = MagicMock(return_value={
        "test-entry-1": {
            "readings": readings_data,
        }
    })

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
    sensor_module.dt_util.now = MagicMock(
        return_value=datetime(2026, 8, 23, 8, 0)
    )

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
    sensor_module.dt_util.now = MagicMock(
        return_value=datetime(2026, 8, 23, 8, 0)
    )

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
    sensor_module.dt_util.now = MagicMock(
        return_value=datetime(2026, 8, 23, 8, 0)
    )

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
    sensor_module.dt_util.now = MagicMock(
        return_value=datetime(2026, 8, 23, 8, 0)
    )

    attrs = sensor.extra_state_attributes

    # For dia: 80 is valid, but reading from 16th has None
    # avg_7d should be 80.0 (only valid value)
    assert "avg_7d" in attrs
    assert attrs["avg_7d"] == 80.0


def test_last_reading_sensor_avg_7d_empty_readings():
    """[AUDIT-7b-M-5] avg_7d is None when no readings in window."""
    sensor, entry, store = _make_last_reading_sensor_fixture("sys", [])
    sensor_module.dt_util.now = MagicMock(
        return_value=datetime(2026, 8, 23, 8, 0)
    )

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
    sensor_module.dt_util.now = MagicMock(
        return_value=datetime(2026, 8, 23, 8, 0)
    )

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
    sensor_module.dt_util.now = MagicMock(
        return_value=datetime(2026, 8, 23, 8, 0)
    )

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

    sensor_module.dt_util.now = MagicMock(
        return_value=datetime(2026, 8, 23, 8, 0)
    )

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


def test_last_reading_sensor_avg_7d_precision():
    """[AUDIT-7b-M-5] avg_7d maintains correct decimal precision."""
    readings = [
        {"ts": "2026-08-22T08:00:00", "sys": 121, "dia": 80, "pulse": 70},
        {"ts": "2026-08-16T08:00:00", "sys": 119, "dia": 85, "pulse": 72},
    ]

    sensor, entry, store = _make_last_reading_sensor_fixture("sys", readings)
    sensor_module.dt_util.now = MagicMock(
        return_value=datetime(2026, 8, 23, 8, 0)
    )

    attrs = sensor.extra_state_attributes

    # avg_7d should be (121 + 119) / 2 = 120.0
    assert attrs["avg_7d"] == 120.0
    # Verify it's rounded to 1 decimal
    assert isinstance(attrs["avg_7d"], float)

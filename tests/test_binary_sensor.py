"""Tests: GoalReachedEntity — daily_reset_hour-Wiring (Feature 2).

binary_sensor.py hatte bislang keine eigene Testdatei; ergänzt hier gezielt
die Abdeckung für die neue Reset-Uhrzeit-Verdrahtung (Spec Feature 2), analog
zum Muster in test_sensor.py.
"""
import os
import sys
import types
import importlib.util
from datetime import datetime
from unittest.mock import MagicMock

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


binary_sensor_module = _load("binary_sensor")


def _make_goal_reached_fixture(options=None, drinks=None, daily_goal_ml=500):
    coordinator = MagicMock()
    entry = MagicMock()
    entry.entry_id = "test-entry-1"
    entry.options = options if options is not None else {}
    entry.runtime_data = MagicMock()
    entry.runtime_data.daily_goal_ml = daily_goal_ml

    store = MagicMock()
    store.all_entries = MagicMock(return_value={
        "test-entry-1": {"drinks": drinks if drinks is not None else []},
    })

    entity = binary_sensor_module.GoalReachedEntity(coordinator, entry, store)
    return entity, entry, store


def test_goal_reached_uses_daily_reset_hour_from_options():
    """[Spec Feature 2] GoalReachedEntity liest entry.options['daily_reset_hour'] statt fest 0."""
    drinks = [{"ts": "2026-08-22T05:00:00", "ml": 500, "type": "Kaffee"}]
    entity, entry, store = _make_goal_reached_fixture(
        options={"daily_reset_hour": 6}, drinks=drinks, daily_goal_ml=500
    )
    binary_sensor_module.dt_util.now = MagicMock(return_value=datetime(2026, 8, 22, 8, 0))

    # 05:00-Buchung liegt vor der 06:00-Reset-Grenze -> zählt noch zum Vortag,
    # heutiges Fenster ist leer -> Ziel (500ml) nicht erreicht.
    assert entity.is_on is False


def test_goal_reached_daily_reset_hour_missing_defaults_to_zero_regression():
    """[Spec Feature 2] Ohne daily_reset_hour in entry.options: Bestandsverhalten (hour=0) unverändert."""
    drinks = [{"ts": "2026-08-22T05:00:00", "ml": 500, "type": "Kaffee"}]
    entity, entry, store = _make_goal_reached_fixture(
        options={}, drinks=drinks, daily_goal_ml=500
    )
    binary_sensor_module.dt_util.now = MagicMock(return_value=datetime(2026, 8, 22, 8, 0))

    assert entity.is_on is True

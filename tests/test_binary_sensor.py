"""Tests: GoalReachedEntity — daily_reset_hour-Wiring (Feature 2).

binary_sensor.py hatte bislang keine eigene Testdatei; ergänzt hier gezielt
die Abdeckung für die neue Reset-Uhrzeit-Verdrahtung (Spec Feature 2), analog
zum Muster in test_sensor.py.
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


binary_sensor_module = _load("binary_sensor")


def _load_init():
    """__init__.py mit Fake-Modulen laden (analog test_wave_a._load_init)."""
    for name in ("store", "entity", "const", "parser", "logic", "exporter"):
        _load(name)
    spec = importlib.util.spec_from_file_location(
        f"{_PKG}.init", os.path.join(_COMPONENT_DIR, "__init__.py")
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[f"{_PKG}.init"] = module
    spec.loader.exec_module(module)
    return module


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _make_goal_reached_fixture(options=None, drinks=None, daily_goal_ml=500):
    coordinator = MagicMock()
    entry = MagicMock()
    entry.entry_id = "test-entry-1"
    entry.options = options if options is not None else {}
    entry.runtime_data = MagicMock()
    entry.runtime_data.daily_goal_ml = daily_goal_ml

    store = MagicMock()
    store.all_entries = MagicMock(
        return_value={
            "test-entry-1": {"drinks": drinks if drinks is not None else []},
        }
    )

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
    """[Spec Feature 2] Ohne daily_reset_hour in entry.options: Bestandsverhalten
    (hour=0) unverändert."""
    drinks = [{"ts": "2026-08-22T05:00:00", "ml": 500, "type": "Kaffee"}]
    entity, entry, store = _make_goal_reached_fixture(options={}, drinks=drinks, daily_goal_ml=500)
    binary_sensor_module.dt_util.now = MagicMock(return_value=datetime(2026, 8, 22, 8, 0))

    assert entity.is_on is True


# ============================================================================
# BP-Schwellen: Options → runtime_data-Spiegel (Fix: L3-Admin ändert Schwellen,
# aber die BP-Warnung blieb auf den Defaults stehen).
# ============================================================================


def _fresh_store(store_module):
    """HealthOMatStore mit gemocktem HA-Store-Backend (leerer Start)."""
    store = store_module.HealthOMatStore(MagicMock())
    store._store = MagicMock()
    store._store.async_load = AsyncMock(return_value=None)
    store._store.async_save = AsyncMock(return_value=None)
    _run(store.async_load())
    return store


def _bp_entity(entry, readings):
    """BloodPressureWarningEntity mit fixem Store-Fixture (letzte Messung)."""
    coordinator = MagicMock()
    store = MagicMock()
    store.all_entries = MagicMock(return_value={entry.entry_id: {"readings": readings}})
    return binary_sensor_module.BloodPressureWarningEntity(coordinator, entry, store)


def _bp_entry(entry_id="e1", options=None, data=None):
    entry = MagicMock()
    entry.entry_id = entry_id
    entry.data = data if data is not None else {"person": "Max"}
    entry.options = options if options is not None else {}
    return entry


def _mirror_hass(init_module, const_module, store, entry):
    hass = MagicMock()
    hass.data = {
        const_module.DOMAIN: {
            "shared": {"store": store},
            entry.entry_id: {"coordinator": MagicMock()},
        }
    }
    hass.config_entries.async_entries = MagicMock(return_value=[entry])
    return hass


def test_options_updated_mirrors_bp_thresholds_to_runtime_data(monkeypatch):
    """[BP-Fix] Options-Update spiegelt sys/dia-Schwellen nach runtime_data."""
    init = _load_init()
    const_module = sys.modules[f"{_PKG}.const"]
    store = _fresh_store(sys.modules[f"{_PKG}.store"])
    _run(store.set_person("e1", "Max"))

    entry = _bp_entry(options={"sys_threshold": 150, "dia_threshold": 95})
    entry.runtime_data = init.HealthOMatData()
    monkeypatch.setattr(init, "_async_apply_panel_layer", AsyncMock())
    hass = _mirror_hass(init, const_module, store, entry)

    # Vorher: Defaults (140/90)
    assert (entry.runtime_data.sys_threshold, entry.runtime_data.dia_threshold) == (140, 90)

    _run(init._options_updated(hass, entry))

    assert (entry.runtime_data.sys_threshold, entry.runtime_data.dia_threshold) == (150, 95)


def test_options_updated_bp_warning_entity_reflects_new_thresholds(monkeypatch):
    """[BP-Fix] Nach dem Options-Update folgt die BP-Warnung den neuen Schwellen.

    Messung 145/88: unter den Defaults (140/90) eine Warnung, unter den neuen
    Schwellen (150/95) nicht mehr — 155/88 wiederum schon.
    """
    init = _load_init()
    const_module = sys.modules[f"{_PKG}.const"]
    store = _fresh_store(sys.modules[f"{_PKG}.store"])
    _run(store.set_person("e1", "Max"))

    entry = _bp_entry(options={"sys_threshold": 150, "dia_threshold": 95})
    entry.runtime_data = init.HealthOMatData()
    monkeypatch.setattr(init, "_async_apply_panel_layer", AsyncMock())
    hass = _mirror_hass(init, const_module, store, entry)

    below_new = [{"ts": "2026-10-14T08:00:00", "sys": 145, "dia": 88}]
    above_new = [{"ts": "2026-10-14T08:00:00", "sys": 155, "dia": 88}]

    # Vor dem Update: Default-Schwellen → 145/88 warnt.
    assert _bp_entity(entry, below_new).is_on is True

    _run(init._options_updated(hass, entry))

    # Nach dem Update: Schwellen aus den Options → 145/88 warnt nicht mehr,
    # 155/88 weiterhin (Warnung an/aus je Wert).
    assert _bp_entity(entry, below_new).is_on is False
    assert _bp_entity(entry, above_new).is_on is True


def test_apply_options_keeps_defaults_for_missing_or_invalid_thresholds():
    """[BP-Fix] Fehlende/ungültige Schwellen-Options lassen die Defaults stehen."""
    init = _load_init()
    entry = _bp_entry(options={"sys_threshold": None, "dia_threshold": "abc"})
    entry.runtime_data = init.HealthOMatData()

    init._apply_options(MagicMock(), entry)

    assert (entry.runtime_data.sys_threshold, entry.runtime_data.dia_threshold) == (140, 90)


def test_apply_options_mirrors_bp_thresholds_on_setup():
    """[BP-Fix] Setup-Pfad (_apply_options) spiegelt gültige Schwellen-Werte."""
    init = _load_init()
    entry = _bp_entry(options={"sys_threshold": "130", "dia_threshold": 85})
    entry.runtime_data = init.HealthOMatData()

    init._apply_options(MagicMock(), entry)

    assert (entry.runtime_data.sys_threshold, entry.runtime_data.dia_threshold) == (130, 85)

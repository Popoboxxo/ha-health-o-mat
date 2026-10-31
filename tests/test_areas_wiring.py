"""Tests: __init__.py-Verdrahtung der Bereichs-Toggles (REQ-HOM-009).

Prüft den Runtime-Spiegel (HealthOMatData.areas, _apply_options) und den
Reload-Trigger bei geänderter Bereichs-Auswahl in _options_updated — inklusive
Regression, dass die Personen-Umbenennung weiterhin neu lädt.
"""

from __future__ import annotations

import asyncio
import importlib.util
import os
import sys
import types
from unittest.mock import AsyncMock, MagicMock

_COMPONENT_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "custom_components", "health_o_mat")
)

# Fake-Paket für relative Imports
_PKG = "_hom_areas_wiring_test_pkg"
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


def _load_init():
    """__init__.py mit Fake-Modulen laden (analog test_binary_sensor._load_init)."""
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


def _fresh_store():
    store = sys.modules[f"{_PKG}.store"].HealthOMatStore(MagicMock())
    store._store = MagicMock()
    store._store.async_load = AsyncMock(return_value=None)
    store._store.async_save = AsyncMock(return_value=None)
    _run(store.async_load())
    return store


def _cfg_entry(entry_id="e1", person="Max", options=None):
    entry = MagicMock()
    entry.entry_id = entry_id
    entry.data = {"person": person}
    entry.options = options if options is not None else {}
    return entry


def _hass(store, entry):
    const_module = sys.modules[f"{_PKG}.const"]
    hass = MagicMock()
    hass.data = {
        const_module.DOMAIN: {
            "shared": {"store": store},
            entry.entry_id: {"coordinator": MagicMock()},
        }
    }
    hass.config_entries.async_reload = MagicMock()
    return hass


def test_health_o_mat_data_defaults_all_areas_active():
    """[REQ-HOM-009] Runtime-Daten starten mit allen Bereichen aktiv."""
    init = _load_init()
    rt = init.HealthOMatData()
    assert rt.areas == {"drink": True, "bp": True, "wellbeing": True, "labs": True}
    assert rt.areas is not init.HealthOMatData().areas  # frische Kopie je Instanz


def test_apply_options_mirrors_areas_from_options():
    """[REQ-HOM-009] _apply_options spiegelt entry.options['areas'] in rt.areas."""
    init = _load_init()
    entry = _cfg_entry(options={"areas": {"wellbeing": False}})
    entry.runtime_data = init.HealthOMatData()

    init._apply_options(MagicMock(), entry)

    assert entry.runtime_data.areas == {"drink": True, "bp": True, "wellbeing": False, "labs": True}


def test_apply_options_missing_areas_keeps_all_active():
    """[REQ-HOM-009] Alt-Entry ohne areas-Option bleibt voll aktiv (Migrationspfad)."""
    init = _load_init()
    entry = _cfg_entry(options={})
    entry.runtime_data = init.HealthOMatData()

    init._apply_options(MagicMock(), entry)

    assert entry.runtime_data.areas == {"drink": True, "bp": True, "wellbeing": True, "labs": True}


def test_options_updated_area_change_triggers_reload(monkeypatch):
    """[REQ-HOM-009] Geänderte Bereichs-Auswahl → rt.areas gesetzt + Reload."""
    init = _load_init()
    monkeypatch.setattr(init, "_async_apply_panel_layer", AsyncMock())
    store = _fresh_store()
    _run(store.set_person("e1", "Max"))
    entry = _cfg_entry(options={"areas": {"drink": False}})
    entry.runtime_data = init.HealthOMatData()
    hass = _hass(store, entry)

    _run(init._options_updated(hass, entry))

    assert entry.runtime_data.areas == {"drink": False, "bp": True, "wellbeing": True, "labs": True}
    hass.config_entries.async_reload.assert_called_once_with("e1")


def test_options_updated_unchanged_areas_does_not_reload(monkeypatch):
    """[REQ-HOM-009] Unveränderte Auswahl → kein unnötiger Reload."""
    init = _load_init()
    monkeypatch.setattr(init, "_async_apply_panel_layer", AsyncMock())
    store = _fresh_store()
    _run(store.set_person("e1", "Max"))
    entry = _cfg_entry(options={})
    entry.runtime_data = init.HealthOMatData()
    hass = _hass(store, entry)

    _run(init._options_updated(hass, entry))

    hass.config_entries.async_reload.assert_not_called()
    assert entry.runtime_data.areas == {"drink": True, "bp": True, "wellbeing": True, "labs": True}


def test_options_updated_person_rename_still_reloads(monkeypatch):
    """[REQ-HOM-009] Regression: Personen-Umbenennung lädt weiterhin neu."""
    init = _load_init()
    monkeypatch.setattr(init, "_async_apply_panel_layer", AsyncMock())
    store = _fresh_store()
    _run(store.set_person("e1", "Max"))
    entry = _cfg_entry(person="Caro", options={})
    entry.runtime_data = init.HealthOMatData()
    hass = _hass(store, entry)

    _run(init._options_updated(hass, entry))

    hass.config_entries.async_reload.assert_called_once_with("e1")
    assert store.all_entries()["e1"]["person"] == "Caro"


def test_apply_options_does_not_touch_lifetime():
    """Setup-/Reload-Pfad darf den Lebenszähler NICHT auf set_lifetime_ml zurücksetzen.

    Regression-Schutz: Bereichs-Toggles lösen einen Reload aus; würde
    _apply_options den gespeicherten set_lifetime_ml-Sollwert erneut anwenden,
    verlöre der gewachsene Lebenszähler bei jeder Umschaltung Daten.
    """
    init = _load_init()
    store = _fresh_store()
    _run(store.set_lifetime_start("e1", 1000))  # gewachsener Zähler
    entry = _cfg_entry(options={"set_lifetime_ml": 750})
    entry.runtime_data = init.HealthOMatData()
    hass = _hass(store, entry)

    init._apply_options(hass, entry)

    assert store.all_entries()["e1"]["total_ml_lifetime"] == 1000
    hass.async_create_task.assert_not_called()


def test_unload_reapplies_panel_layer_excluding_entry(monkeypatch):
    """Beim Unload wird der Panel-Zustand domain-weit neu angewandt (Entry ausgenommen).

    Behebt: blieb die letzte Panel-freischaltende Person in einem Mehr-Personen-
    Setup weg, blieb das Panel bis zum HA-Neustart registriert.
    """
    init = _load_init()
    store = _fresh_store()
    _run(store.set_person("e1", "Max"))
    entry = _cfg_entry()
    entry.runtime_data = init.HealthOMatData()
    hass = _hass(store, entry)
    hass.config_entries.async_unload_platforms = AsyncMock(return_value=True)
    layer = AsyncMock()
    monkeypatch.setattr(init, "_async_apply_panel_layer", layer)
    monkeypatch.setattr(init, "async_unregister_frontend", AsyncMock())

    _run(init.async_unload_entry(hass, entry))

    layer.assert_awaited_once_with(hass, exclude_entry_id="e1")


# --- Review-Fix S-4 ---------------------------------------------------------


def _lifetime_setup(monkeypatch, options, lifetime):
    init = _load_init()
    monkeypatch.setattr(init, "_async_apply_panel_layer", AsyncMock())
    monkeypatch.setattr(init, "async_setup_reminders", AsyncMock())
    store = _fresh_store()
    _run(store.set_person("e1", "Max"))
    _run(store.set_lifetime_start("e1", lifetime))
    entry = _cfg_entry(options=options)
    entry.runtime_data = init.HealthOMatData()
    hass = _hass(store, entry)
    init._apply_options(hass, entry)
    return init, store, entry, hass


def test_options_updated_goal_change_does_not_reset_lifetime(monkeypatch):
    """[S-4] Tagesziel ändern lässt den gewachsenen Lebenszähler unverändert."""
    init, store, entry, hass = _lifetime_setup(
        monkeypatch, {"daily_goal_ml": 2500, "set_lifetime_ml": 1000}, 1000
    )

    entry.options = {"daily_goal_ml": 3000, "set_lifetime_ml": 1000}
    _run(init._options_updated(hass, entry))

    assert store.all_entries()["e1"]["total_ml_lifetime"] == 1000


def test_options_updated_wizard_save_after_bookings_keeps_lifetime(monkeypatch):
    """[S-4] Wizard-Save mit altem Formular-Default setzt den Zähler nicht zurück."""
    init, store, entry, hass = _lifetime_setup(
        monkeypatch, {"daily_goal_ml": 2000, "set_lifetime_ml": 500}, 750
    )

    entry.options = {"daily_goal_ml": 2500, "set_lifetime_ml": 500}
    _run(init._options_updated(hass, entry))

    assert store.all_entries()["e1"]["total_ml_lifetime"] == 750


def test_options_updated_explicit_lifetime_change_applies(monkeypatch):
    """[S-4] Eine echte Änderung des Lebenszähler-Feldes wird weiterhin angewandt."""
    init, store, entry, hass = _lifetime_setup(
        monkeypatch, {"daily_goal_ml": 2000, "set_lifetime_ml": 1000}, 1000
    )

    entry.options = {"daily_goal_ml": 2000, "set_lifetime_ml": 900}
    _run(init._options_updated(hass, entry))

    assert store.all_entries()["e1"]["total_ml_lifetime"] == 900


# --- Review-Fix B-1: Lab-Options lösen einen Reload aus ----------------------


def _lab_setup(monkeypatch, options):
    """Setup-Baseline: `_apply_options` spiegelt die Lab-Options in rt."""
    init = _load_init()
    monkeypatch.setattr(init, "_async_apply_panel_layer", AsyncMock())
    monkeypatch.setattr(init, "async_setup_reminders", AsyncMock())
    store = _fresh_store()
    _run(store.set_person("e1", "Max"))
    entry = _cfg_entry(options=dict(options))
    entry.runtime_data = init.HealthOMatData()
    hass = _hass(store, entry)
    init._apply_options(hass, entry)
    return init, entry, hass


def test_apply_options_mirrors_lab_options_snapshot(monkeypatch):
    """[REQ-HOM-122/B-1] _apply_options spiegelt die Lab-Options in rt.lab_options."""
    init, entry, _hass_mock = _lab_setup(
        monkeypatch, {"lab_custom_markers": [{"name": "Vitamin D", "unit": "ng/mL"}]}
    )

    markers, _overrides, hidden = entry.runtime_data.lab_options

    assert [marker["key"] for marker in markers] == ["vitamin_d"]
    assert hidden == frozenset()


def test_options_updated_new_custom_marker_triggers_reload(monkeypatch):
    """[REQ-HOM-122/B-1] Neuer Custom-Marker → Reload erzeugt den Sensor."""
    init, entry, hass = _lab_setup(monkeypatch, {})
    assert hass.config_entries.async_reload.call_count == 0

    entry.options = {"lab_custom_markers": [{"name": "Vitamin D", "unit": "ng/mL"}]}
    _run(init._options_updated(hass, entry))

    hass.config_entries.async_reload.assert_called_once_with("e1")


def test_options_updated_removed_custom_marker_triggers_reload(monkeypatch):
    """[REQ-HOM-122/B-1] Entfernter Custom-Marker → Reload räumt die Entity ab."""
    init, entry, hass = _lab_setup(
        monkeypatch, {"lab_custom_markers": [{"name": "Vitamin D", "unit": "ng/mL"}]}
    )

    entry.options = {}
    _run(init._options_updated(hass, entry))

    hass.config_entries.async_reload.assert_called_once_with("e1")


def test_options_updated_lab_changes_trigger_reload_for_each_key(monkeypatch):
    """[REQ-HOM-122/B-1] Auch Overrides und verborgene Kategorien laden neu."""
    init, entry, hass = _lab_setup(monkeypatch, {})

    entry.options = {"lab_ref_overrides": {"alt": {"ref_max": 40}}}
    _run(init._options_updated(hass, entry))
    hass.config_entries.async_reload.assert_called_once_with("e1")

    # Verborgenes Kategorie-Set ändert den Warn-Sensor-Satz ebenfalls.
    entry.options = {
        "lab_ref_overrides": {"alt": {"ref_max": 40}},
        "lab_hidden_categories": ["liver"],
    }
    _run(init._options_updated(hass, entry))
    assert hass.config_entries.async_reload.call_count == 2


def test_options_updated_unchanged_lab_options_do_not_reload(monkeypatch):
    """[REQ-HOM-122/B-1] Unveränderte Lab-Options (nur unkritische Keys) → kein Reload."""
    init, entry, hass = _lab_setup(
        monkeypatch,
        {"lab_custom_markers": [{"name": "Vitamin D", "unit": "ng/mL"}], "daily_goal_ml": 2000},
    )

    entry.options = {
        "lab_custom_markers": [{"name": "Vitamin D", "unit": "ng/mL"}],
        "daily_goal_ml": 2500,
    }
    _run(init._options_updated(hass, entry))

    hass.config_entries.async_reload.assert_not_called()


def test_options_updated_lab_format_noise_does_not_reload(monkeypatch):
    """[REQ-HOM-122/B-1] Format-/Reihenfolge-Rauschen löst keinen Reload aus."""
    init, entry, hass = _lab_setup(
        monkeypatch,
        {
            "lab_custom_markers": [
                {"name": "Vitamin D", "unit": "ng/mL", "ref_min": 30},
                {"name": "Ferritin", "unit": "µg/L", "ref_min": 30},
            ],
            "lab_hidden_categories": ["liver", "kidney"],
        },
    )

    # Reihenfolge getauscht, Zahlen als Strings, Whitespace im Namen.
    entry.options = {
        "lab_custom_markers": [
            {"name": "  Ferritin  ", "unit": "µg/L", "ref_min": "30"},
            {"name": "Vitamin D", "unit": "ng/mL", "ref_min": 30},
        ],
        "lab_hidden_categories": ["kidney", "liver"],
    }
    _run(init._options_updated(hass, entry))

    hass.config_entries.async_reload.assert_not_called()


def test_options_updated_lab_reload_is_idempotent(monkeypatch):
    """[REQ-HOM-122/B-1] Kein Reload-Loop: derselbe Optionsstand lädt nur einmal."""
    init, entry, hass = _lab_setup(monkeypatch, {})

    entry.options = {"lab_custom_markers": [{"name": "Vitamin D", "unit": "ng/mL"}]}
    _run(init._options_updated(hass, entry))
    # Nach dem Reload: frisches Runtime-Objekt (wie in async_setup_entry) und
    # erneutes Options-Spiegeln dürfen keinen weiteren Reload auslösen.
    entry.runtime_data = init.HealthOMatData()
    init._apply_options(hass, entry)
    _run(init._options_updated(hass, entry))

    hass.config_entries.async_reload.assert_called_once_with("e1")

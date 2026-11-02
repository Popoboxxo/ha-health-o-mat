"""Tests: button.py — pro-Person Bereichs-Filter im Setup (REQ-HOM-009)."""

from __future__ import annotations

import asyncio
import importlib.util
import os
import sys
import types
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

_COMPONENT_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "custom_components", "health_o_mat")
)

# Fake-Paket für relative Imports
_PKG = "_hom_button_test_pkg"
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


button_module = _load("button")
store_module = _load("store")
sensor_module = _load("sensor")
exporter_module = _load("exporter")

_ENTRY_ID = "test-entry-1"
_DRINK_BUTTON_KEYS = {
    "button_book_custom",
    "button_undo_drink",
    "button_quick_0",
    "button_quick_1",
    "button_quick_2",
    "button_quick_3",
}
_BP_BUTTON_KEYS = {"button_save_reading"}
_WELLBEING_BUTTON_KEYS = {
    "button_wellbeing_report_very_bad",
    "button_wellbeing_report_awful",
    "button_wellbeing_report_bad",
    "button_wellbeing_report_poor",
    "button_wellbeing_report_okay",
    "button_wellbeing_report_mixed",
    "button_wellbeing_report_good",
    "button_wellbeing_report_very_good",
    "button_wellbeing_report_great",
    "button_wellbeing_report_excellent",
}


def _button_setup(options: dict) -> set[str]:
    added: list = []

    hass = MagicMock()
    entry = MagicMock()
    entry.entry_id = _ENTRY_ID
    entry.options = options
    coord = MagicMock()
    store = MagicMock()
    hass.data = {
        "health_o_mat": {
            _ENTRY_ID: {"coordinator": coord},
            "shared": {"store": store},
        }
    }

    asyncio.new_event_loop().run_until_complete(
        button_module.async_setup_entry(hass, entry, lambda ents: added.extend(ents))
    )
    return {e._attr_unique_id for e in added}


def _ids(keys: set[str]) -> set[str]:
    return {f"{_ENTRY_ID}_{key}" for key in keys}


def test_button_setup_old_entry_without_options_has_all_areas():
    """[REQ-HOM-009] Alt-Entry ohne areas-Option = alle Bereiche aktiv."""
    keys = _button_setup({})
    assert keys == _ids(_DRINK_BUTTON_KEYS | _BP_BUTTON_KEYS | _WELLBEING_BUTTON_KEYS)


def test_button_setup_drink_disabled_keeps_bp_and_wellbeing():
    """[REQ-HOM-009] drink AUS → keine Drink-Buttons; BP + Wohlbefinden bleiben."""
    keys = _button_setup({"areas": {"drink": False}})
    assert keys == _ids(_BP_BUTTON_KEYS | _WELLBEING_BUTTON_KEYS)
    assert keys.isdisjoint(_ids(_DRINK_BUTTON_KEYS))


def test_button_setup_only_drink_when_bp_and_wellbeing_disabled():
    """[REQ-HOM-009] bp + wellbeing AUS → nur Drink-Buttons."""
    keys = _button_setup({"areas": {"bp": False, "wellbeing": False}})
    assert keys == _ids(_DRINK_BUTTON_KEYS)


def test_button_unique_ids_stable_across_area_toggle():
    """[REQ-HOM-009] De-/Reaktivieren erzeugt dieselben unique_ids."""
    on_keys = _button_setup({})
    off_keys = _button_setup({"areas": {"drink": False}})
    on_again_keys = _button_setup({"areas": {"drink": True}})

    drink_ids = _ids(_DRINK_BUTTON_KEYS)
    assert drink_ids <= on_keys
    assert drink_ids.isdisjoint(off_keys)
    assert on_again_keys == on_keys


def _make_entry() -> MagicMock:
    """Entry ohne quick_drinks-Option → DEFAULT_QUICK_DRINKS (Index 2 = Tasse Kaffee)."""
    entry = MagicMock()
    entry.entry_id = _ENTRY_ID
    entry.options = {}
    return entry


def test_req_hom_130_quick_drink_suggested_object_id_is_one_based():
    """[REQ-HOM-130] New quick drinks register as `quick_drink_<n>` (A-5)."""
    entry = _make_entry()
    button = button_module.QuickDrinkButton(MagicMock(), entry, MagicMock(), 2)

    assert button.suggested_object_id == "quick_drink_3"
    # The display name stays the user label — no literal name in the id.
    assert button.name == "Tasse Kaffee"


# --- REQ-HOM-010: Button übergibt die angefangene Mess-Notiz ---


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _call(data: dict | None = None) -> MagicMock:
    call = MagicMock()
    call.data = data or {}
    return call


def _real_store():
    """Echte `HealthOMatStore`-Instanz mit gemocktem HA-Store-Backend."""
    store = store_module.HealthOMatStore(MagicMock())
    store._store = MagicMock()
    store._store.async_load = AsyncMock(return_value=None)
    store._store.async_save = AsyncMock(return_value=None)
    _run(store.async_load())
    return store


def _press_save_reading(store, entry=None):
    entry = entry or _make_entry()
    button = button_module.SaveReadingButton(MagicMock(), entry, store)
    button.hass = MagicMock()
    _run(button.async_press())
    return entry


def _prime_bp_inputs(store) -> None:
    _run(store.set_inputs(_ENTRY_ID, "sys", 120))
    _run(store.set_inputs(_ENTRY_ID, "dia", 80))
    _run(store.set_pending_note(_ENTRY_ID, "morgens"))


def test_save_reading_consumes_pending_note_and_clears_it():
    """[REQ-HOM-010] Button schreibt die Notiz in die Messung und leert das Feld."""
    store = _real_store()
    _prime_bp_inputs(store)

    _press_save_reading(store)

    reading = store.entry(_ENTRY_ID)["readings"][0]
    assert reading["note"] == "morgens"
    assert store.pending_note(_ENTRY_ID) == ""


def test_save_reading_note_visible_in_history_json_and_csv(tmp_path, monkeypatch):
    """[REQ-HOM-010] Die Notiz steht in `history_json` und im BP-CSV."""
    store = _real_store()
    _prime_bp_inputs(store)
    entry = _press_save_reading(store)

    history = sensor_module.BloodPressureHistorySensor(MagicMock(), entry, store)
    assert "morgens" in history.extra_state_attributes["history_json"]

    monkeypatch.setattr(
        exporter_module, "dt_util", SimpleNamespace(now=lambda: datetime(2026, 11, 2, 12, 0))
    )
    hass = MagicMock()
    hass.config.path = MagicMock(return_value=str(tmp_path))
    hass.async_add_executor_job = AsyncMock(side_effect=lambda fn: fn())
    hass.services.async_call = AsyncMock()
    _run(exporter_module.async_export_csv(hass, store, _call({"dataset": "blood_pressure"})))

    csv_text = next(tmp_path.glob("health_o_mat_bloodpressure_*.csv")).read_text(
        encoding="utf-8-sig"
    )
    assert "morgens" in csv_text

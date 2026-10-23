"""Tests: button.py — pro-Person Bereichs-Filter im Setup (REQ-HOM-009)."""

from __future__ import annotations

import asyncio
import importlib.util
import os
import sys
import types
from unittest.mock import MagicMock

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

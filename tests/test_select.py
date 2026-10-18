"""Tests: select.py — pro-Person Bereichs-Filter im Setup (REQ-HOM-009).

select.py ist wellbeing-only; dieser Test sichert den bedingten Aufbau ab.
"""

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
_PKG = "_hom_select_test_pkg"
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


select_module = _load("select")

_ENTRY_ID = "test-entry-1"
_SELECT_ID = "test-entry-1_select_wellbeing_state"


def _select_setup(options: dict) -> set[str]:
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
        select_module.async_setup_entry(hass, entry, lambda ents: added.extend(ents))
    )
    return {e._attr_unique_id for e in added}


def test_select_setup_old_entry_without_options_has_wellbeing():
    """[REQ-HOM-009] Alt-Entry ohne areas-Option = Wellbeing aktiv."""
    assert _select_setup({}) == {_SELECT_ID}


def test_select_setup_wellbeing_disabled_creates_no_entity():
    """[REQ-HOM-009] wellbeing AUS → kein Select-Entity."""
    assert _select_setup({"areas": {"wellbeing": False}}) == set()


def test_select_setup_other_areas_do_not_affect_select():
    """[REQ-HOM-009] drink/bp AUS lassen das Wellbeing-Select unberührt."""
    assert _select_setup({"areas": {"drink": False, "bp": False}}) == {_SELECT_ID}


def test_select_unique_id_stable_across_area_toggle():
    """[REQ-HOM-009] De-/Reaktivieren erzeugt dieselbe unique_id."""
    on_ids = _select_setup({})
    off_ids = _select_setup({"areas": {"wellbeing": False}})
    on_again_ids = _select_setup({"areas": {"wellbeing": True}})

    assert on_ids == {_SELECT_ID}
    assert off_ids == set()
    assert on_again_ids == on_ids

"""Tests: areas.py — pro-Person Feature-Flächen (REQ-HOM-009), HA-frei.

Prüft die Default-/Migrations-Semantik („fehlender Schlüssel = aktiv"), das
Ignorieren unbekannter Schlüssel, das Frisch-Kopieren des Ergebnis-Dicts und den
Convenience-Wrapper ``area_enabled``.
"""

from __future__ import annotations

import importlib.util
import os
import sys
import types

_COMPONENT_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "custom_components", "health_o_mat")
)

# Fake-Paket für relative Imports
_PKG = "_hom_areas_test_pkg"
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


areas = _load("areas")

ALL_ON = {"drink": True, "bp": True, "wellbeing": True, "labs": True}


def test_constants():
    """[REQ-HOM-009] Konstanten: Bereiche, Options-Schlüssel, Default alle aktiv."""
    assert areas.AREA_DRINK == "drink"
    assert areas.AREA_BP == "bp"
    assert areas.AREA_WELLBEING == "wellbeing"
    assert areas.AREA_LABS == "labs"
    assert areas.AREAS == ("drink", "bp", "wellbeing", "labs")
    assert areas.OPTION_AREAS == "areas"
    assert areas.DEFAULT_AREAS == ALL_ON


def test_active_areas_none_is_all_true():
    """[REQ-HOM-009] Keine Options (Alt-Entry) → alle Bereiche aktiv."""
    assert areas.active_areas(None) == ALL_ON


def test_active_areas_empty_options_is_all_true():
    """[REQ-HOM-009] Leere Options ({}) → alle Bereiche aktiv (Migrationspfad)."""
    assert areas.active_areas({}) == ALL_ON


def test_active_areas_returns_fresh_dict():
    """Mutation des Ergebnisses darf nachfolgende Aufrufe nicht beeinflussen."""
    first = areas.active_areas({})
    first["drink"] = False
    assert areas.active_areas({})["drink"] is True
    assert areas.active_areas({"areas": {"drink": False}})["drink"] is False


def test_active_areas_explicit_drink_false_keeps_others_true():
    """[REQ-HOM-009] Nur explizit abgeschaltete Bereiche kippen; Rest bleibt aktiv."""
    assert areas.active_areas({"areas": {"drink": False}}) == {
        "drink": False,
        "bp": True,
        "wellbeing": True,
        "labs": True,
    }


def test_active_areas_missing_sub_key_stays_true():
    """[REQ-HOM-009] Fehlender Unter-Schlüssel bedeutet aktiv, nicht inaktiv."""
    result = areas.active_areas({"areas": {"bp": False}})
    assert result == {"drink": True, "bp": False, "wellbeing": True, "labs": True}
    assert result["wellbeing"] is True


def test_active_areas_unknown_keys_ignored():
    """Unbekannte Schlüssel werden weder übernommen noch als Fehler gewertet."""
    result = areas.active_areas({"areas": {"drink": False, "bogus": True, "x": False}})
    assert set(result) == {"drink", "bp", "wellbeing", "labs"}
    assert result["drink"] is False
    assert "bogus" not in result


def test_active_areas_non_mapping_value_is_all_true():
    """``areas`` ist kein Mapping (None/String/Liste) → alle Bereiche aktiv."""
    assert areas.active_areas({"areas": None}) == ALL_ON
    assert areas.active_areas({"areas": "nope"}) == ALL_ON
    assert areas.active_areas({"areas": []}) == ALL_ON


def test_active_areas_coerces_values_to_bool():
    """Unter-Schlüssel-Werte werden mit bool() normalisiert."""
    assert areas.active_areas({"areas": {"drink": 0}})["drink"] is False
    assert areas.active_areas({"areas": {"drink": 1}})["drink"] is True


def test_area_enabled_wrapper():
    """[REQ-HOM-009] area_enabled spiegelt active_areas; unbekannt → False."""
    opts = {"areas": {"drink": False}}
    assert areas.area_enabled(opts, "drink") is False
    assert areas.area_enabled(opts, "bp") is True
    assert areas.area_enabled(None, "bp") is True
    assert areas.area_enabled(None, "unknown") is False


def test_areas_equal_normalizes():
    """areas_equal vergleicht normalisiert (fehlende Schlüssel = aktiv)."""
    assert areas.areas_equal(None, {}) is True
    assert areas.areas_equal({"drink": False}, {"drink": False}) is True
    assert areas.areas_equal({"drink": False}, {"drink": True}) is False
    assert areas.areas_equal({"drink": True}, {}) is True


def test_req_hom_122_lab_area_defaults_active():
    from custom_components.health_o_mat import areas

    assert areas.active_areas(None)[areas.AREA_LABS] is True


def test_req_hom_122_lab_area_can_be_disabled():
    from custom_components.health_o_mat import areas

    assert areas.active_areas({"areas": {"labs": False}})[areas.AREA_LABS] is False


def test_req_hom_122_lab_area_missing_subkey_stays_active():
    from custom_components.health_o_mat import areas

    # Existing options written before this feature never mention "labs" —
    # a missing sub-key must mean "active" (REQ-HOM-009 migration semantics).
    assert areas.active_areas({"areas": {"drink": False}})[areas.AREA_LABS] is True

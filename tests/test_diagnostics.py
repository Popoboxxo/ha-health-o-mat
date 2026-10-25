"""Tests: Diagnostics strikt redigiert (REQ-HOM-105, Fund N-5).

Beweist, dass die Diagnostics-Antwort nur erlaubte Felder enthält:
Versionen, Entity-IDs, Options (Personenname maskiert) und reine Zähler —
und dass KEINE Gesundheitswerte (ml je Buchung, sys/dia/puls, Wohlbefinden),
KEINE Personennamen und KEINE rohen Zeitstempel durchsickern.
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import os
import sys
import types
from types import SimpleNamespace
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


const = _load("const")
diagnostics = _load("diagnostics")

DOMAIN = const.DOMAIN


def _blob(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


# Sensible Testdaten: alles hiervon darf NICHT im Output auftauchen.
_PERSON = "Max Mustermann"
_FORBIDDEN_TOKENS = [
    _PERSON,  # Personenname
    "2026-10-14T",  # roher Zeitstempel (Buchung/Messung)
    "2026-10-13T",  # roher Zeitstempel (Wellbeing-Historie)
    "137",  # systolisch
    "88",  # diastolisch
    "71",  # Puls
    "miserable",  # Wohlbefinden-Status
    "Kaffee",  # Getränke-Typ
    "123456",  # total_ml_lifetime
    '"ml": 250',  # ml-Menge je Buchung
    "leak-me",  # unbekannter Rohschlüssel
]

_RAW = {
    "integration_version": "9.9.9",
    "entry_version": 7,
    "store_schema_version": 2,
    "store_available": True,
    "entity_ids": [
        "sensor.health_o_mat_drinks_today",
        "sensor.health_o_mat_lifetime_total",
    ],
    "options": {
        "daily_goal_ml": 2000,
        "person_display": _PERSON,
        "quick_drinks": [
            {"key": "glas_wasser", "label": "Glas Wasser", "ml": 200},
        ],
    },
    "secret": "leak-me",
    "store_entry": {
        "person": _PERSON,
        "drinks": [
            {"ts": "2026-10-14T08:00:00+02:00", "ml": 250, "type": "Kaffee", "src": "button"},
        ],
        "readings": [
            {"ts": "2026-10-14T09:00:00+02:00", "sys": 137, "dia": 88, "pulse": 71, "note": "x"},
        ],
        "total_ml_lifetime": 123456,
        "wellbeing": {"status": "miserable", "ts": "2026-10-14T10:00:00+02:00"},
        "wellbeing_history": [
            {"ts": "2026-10-13T10:00:00+02:00", "status": "miserable"},
        ],
    },
}


def test_redact_contains_only_allowed_fields():
    """[REQ-HOM-105] Erlaubte Felder sind vorhanden: Versionen, IDs, Options, Zähler."""
    out = diagnostics.redact_diagnostics(_RAW)

    assert out["integration"]["domain"] == DOMAIN
    assert out["integration"]["version"] == "9.9.9"
    assert out["config_entry"]["version"] == 7
    assert out["store"]["schema_version"] == 2
    assert out["store"]["available"] is True

    assert out["entities"] == [
        "sensor.health_o_mat_drinks_today",
        "sensor.health_o_mat_lifetime_total",
    ]
    assert out["options"]["daily_goal_ml"] == 2000
    assert out["counters"] == {
        "drinks": 1,
        "drinks_active": 1,
        "drinks_voided": 0,
        "readings": 1,
        "readings_active": 1,
        "readings_voided": 0,
        "wellbeing_history": 1,
        "wellbeing_entries": 2,
        "wellbeing_active": 2,
        "wellbeing_voided": 0,
        "audit_events": 0,
    }


def test_redact_masks_person_name():
    """[REQ-HOM-105] Personennamen werden maskiert (Entry + Options)."""
    out = diagnostics.redact_diagnostics(_RAW)

    assert out["config_entry"]["person"] == "***"
    assert out["options"]["person_display"] == "***"
    assert _PERSON not in _blob(out)


def test_redact_has_no_health_values_names_or_timestamps():
    """[REQ-HOM-105] KEINE Gesundheitswerte/Namen/Rohzeitstempel im Output."""
    out = diagnostics.redact_diagnostics(_RAW)
    blob = _blob(out)

    for token in _FORBIDDEN_TOKENS:
        assert token not in blob, f"geleakt: {token!r}"


def test_redact_drops_total_ml_lifetime_counter():
    """[REQ-HOM-105] Grenzwertige Gesamtmenge total_ml_lifetime wird weggelassen."""
    out = diagnostics.redact_diagnostics(_RAW)

    assert "total_ml_lifetime" not in out["counters"]
    assert "total_ml_lifetime" not in out
    assert "123456" not in _blob(out)


def test_redact_tolerates_missing_store_entry():
    """[REQ-HOM-105] Fehlender Store-Eintrag ⇒ Zähler 0, kein Fehler."""
    out = diagnostics.redact_diagnostics({"integration_version": "0.0.1"})

    assert out["counters"] == {
        "drinks": 0,
        "drinks_active": 0,
        "drinks_voided": 0,
        "readings": 0,
        "readings_active": 0,
        "readings_voided": 0,
        "wellbeing_history": 0,
        "wellbeing_entries": 0,
        "wellbeing_active": 0,
        "wellbeing_voided": 0,
        "audit_events": 0,
    }
    assert out["store"]["available"] is False
    assert out["options"] == {}
    assert out["entities"] == []


def test_async_diagnostics_redacted_with_store():
    """[REQ-HOM-105] async_get_config_entry_diagnostics liefert redigierte Antwort."""
    store = MagicMock()
    store.all_entries.return_value = {"e1": _RAW["store_entry"]}

    hass = MagicMock()
    hass.data = {DOMAIN: {"shared": {"store": store}}}
    entry = SimpleNamespace(
        entry_id="e1", version=3, options={"daily_goal_ml": 1500, "person_display": _PERSON}
    )

    out = asyncio.run(diagnostics.async_get_config_entry_diagnostics(hass, entry))
    blob = _blob(out)
    for token in _FORBIDDEN_TOKENS:
        assert token not in blob, f"geleakt: {token!r}"

    assert out["store"]["available"] is True
    assert out["counters"]["drinks"] == 1
    assert out["options"]["daily_goal_ml"] == 1500
    assert out["options"]["person_display"] == "***"


def test_async_diagnostics_without_store_is_defined():
    """[REQ-HOM-105] Ohne Store/Entry definiertes Ergebnis (available False, Zähler 0)."""
    hass = MagicMock()
    hass.data = {}
    entry = SimpleNamespace(entry_id="e1", version=2, options={})

    out = asyncio.run(diagnostics.async_get_config_entry_diagnostics(hass, entry))

    assert out["store"]["available"] is False
    assert out["counters"]["drinks"] == 0
    assert out["counters"]["drinks_active"] == 0
    assert out["counters"]["wellbeing_entries"] == 0
    assert out["entities"] == []


def test_async_diagnostics_survives_store_error():
    """[REQ-HOM-105] Fehler beim Store-Zugriff bricht Diagnostics nicht ab."""
    store = MagicMock()
    store.all_entries.side_effect = RuntimeError("boom")

    hass = MagicMock()
    hass.data = {DOMAIN: {"shared": {"store": store}}}
    entry = SimpleNamespace(entry_id="e1", version=2, options={})

    out = asyncio.run(diagnostics.async_get_config_entry_diagnostics(hass, entry))

    assert out["store"]["available"] is False
    assert out["counters"]["drinks"] == 0


def test_async_diagnostics_collects_entity_ids_from_registry(monkeypatch):
    """[REQ-HOM-105] Entity-IDs der Person stammen aus der Entity-Registry."""
    registry_module = types.ModuleType("homeassistant.helpers.entity_registry")
    registry_module.async_get = lambda hass: "registry"
    registry_module.async_entries_for_config_entry = lambda registry, entry_id: [
        SimpleNamespace(entity_id="sensor.health_o_mat_drinks_today"),
        SimpleNamespace(entity_id="binary_sensor.health_o_mat_daily_goal_reached"),
    ]
    monkeypatch.setitem(sys.modules, "homeassistant.helpers.entity_registry", registry_module)
    helpers_module = sys.modules.get("homeassistant.helpers")
    if helpers_module is not None:
        monkeypatch.setattr(helpers_module, "entity_registry", registry_module, raising=False)

    hass = MagicMock()
    hass.data = {DOMAIN: {}}
    entry = SimpleNamespace(entry_id="e1", version=2, options={})

    out = asyncio.run(diagnostics.async_get_config_entry_diagnostics(hass, entry))

    assert out["entities"] == [
        "binary_sensor.health_o_mat_daily_goal_reached",
        "sensor.health_o_mat_drinks_today",
    ]


def test_manifest_version_is_reported():
    """[REQ-HOM-105] Integrationsversion stammt aus manifest.json."""
    manifest_path = os.path.join(_COMPONENT_DIR, "manifest.json")
    with open(manifest_path, encoding="utf-8") as handle:
        expected = json.load(handle)["version"]

    assert diagnostics._integration_version() == expected


# ============================================================================
# M2a: Zähler unterscheiden aktiv/voided (ohne Inhalte zu leaken)
# ============================================================================


def test_counters_split_total_active_voided_and_audit():
    """[M2a] Zähler weisen gesamt/aktiv/voided sowie Audit-Anzahl aus."""
    store_entry = {
        "person": _PERSON,
        "drinks": [
            {"ts": "2026-10-14T08:00:00+02:00", "ml": 250, "type": "Kaffee"},
            {
                "ts": "2026-10-13T08:00:00+02:00",
                "ml": 500,
                "type": "Kaffee",
                "voided_at": "2026-10-14T09:00:00+02:00",
            },
        ],
        "readings": [
            {"ts": "2026-10-14T09:00:00+02:00", "sys": 137, "dia": 88, "pulse": 71},
            {
                "ts": "2026-10-13T09:00:00+02:00",
                "sys": 150,
                "dia": 95,
                "pulse": 80,
                "voided_at": "2026-10-14T10:00:00+02:00",
            },
        ],
        "wellbeing_entries": [
            {"ts": "2026-10-14T10:00:00+02:00", "key": "miserable"},
            {
                "ts": "2026-10-13T10:00:00+02:00",
                "key": "bad",
                "voided_at": "2026-10-14T11:00:00+02:00",
            },
        ],
        "wellbeing": {"status": "miserable", "ts": "2026-10-14T10:00:00+02:00"},
        "wellbeing_history": [],
        "audit_log": [{"action": "drink_added"}, {"action": "entry_voided"}],
    }

    out = diagnostics.redact_diagnostics({"store_entry": store_entry})

    assert out["counters"] == {
        "drinks": 2,
        "drinks_active": 1,
        "drinks_voided": 1,
        "readings": 2,
        "readings_active": 1,
        "readings_voided": 1,
        "wellbeing_history": 0,
        "wellbeing_entries": 2,
        "wellbeing_active": 1,
        "wellbeing_voided": 1,
        "audit_events": 2,
    }
    blob = _blob(out)
    for token in (_PERSON, "2026-10-13T", "2026-10-14T", "250", "500", "137", "150", "miserable"):
        assert token not in blob, f"geleakt: {token!r}"


def test_counters_legacy_wellbeing_without_event_list():
    """[M2a] Vor-v4-Bestand: Wellbeing-Zähler fallen auf den Legacy-Spiegel zurück."""
    store_entry = {
        "wellbeing": {"status": "good", "ts": "2026-10-14T10:00:00+02:00"},
        "wellbeing_history": [{"ts": "2026-10-13T10:00:00+02:00", "status": "bad"}],
    }

    out = diagnostics.redact_diagnostics({"store_entry": store_entry})

    assert out["counters"]["wellbeing_entries"] == 2
    assert out["counters"]["wellbeing_active"] == 2
    assert out["counters"]["wellbeing_voided"] == 0
    assert out["counters"]["wellbeing_history"] == 1

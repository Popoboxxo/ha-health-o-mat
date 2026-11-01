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


# ============================================================================
# REQ-HOM-122 — Lab-Optionen: Freitext/Marker-Identitäten nur als Zähler
# ============================================================================

_LAB_OPTIONS = {
    const.OPTION_LAB_CUSTOM_MARKERS: [
        {"key": "vitamin_d", "name": "Vitamin-D-Mangel", "category": "other", "unit": "ng/mL"},
        {"key": "ferritin", "name": "Ferritin", "category": "blood_count", "unit": "ng/mL"},
    ],
    const.OPTION_LAB_REF_OVERRIDES: {"creatinine": {"ref_min": 60, "ref_max": 110}},
    const.OPTION_LAB_HIDDEN_CATEGORIES: ["thyroid", "drug_levels"],
}


def test_redact_lab_options_as_counts_only():
    """[REQ-HOM-122] Lab-Options nur als Zähler — keine Namen, Marker oder Werte."""
    out = diagnostics.redact_diagnostics({"options": _LAB_OPTIONS})

    options = out["options"]
    assert options[const.OPTION_LAB_CUSTOM_MARKERS] == {"count": 2}
    assert options[const.OPTION_LAB_REF_OVERRIDES] == {"count": 1}
    assert options[const.OPTION_LAB_HIDDEN_CATEGORIES] == {"count": 2}

    blob = _blob(out)
    for token in (
        "Vitamin-D-Mangel",
        "vitamin_d",
        "ferritin",
        '"creatinine"',
        '"ref_min"',
        "thyroid",
        "drug_levels",
    ):
        assert token not in blob, f"geleakt: {token!r}"


def test_req_hom_129_redacts_new_lab_options_as_counts_only():
    """[REQ-HOM-129] Retention/Disclaimer werden als reine Zähler redigiert."""
    options = {
        const.OPTION_LAB_RETENTION_MONTHS: 24,
        const.OPTION_LAB_HIDE_PANEL_DISCLAIMER: True,
    }

    out = diagnostics.redact_diagnostics({"options": options})

    # Skalare haben keine Sequenzlänge → `count` 0; der Wert selbst leakt nie.
    assert out["options"][const.OPTION_LAB_RETENTION_MONTHS] == {"count": 0}
    assert out["options"][const.OPTION_LAB_HIDE_PANEL_DISCLAIMER] == {"count": 0}
    assert isinstance(out["options"][const.OPTION_LAB_RETENTION_MONTHS], dict)
    assert isinstance(out["options"][const.OPTION_LAB_HIDE_PANEL_DISCLAIMER], dict)


def test_async_diagnostics_redacts_lab_options_from_entry():
    """[REQ-HOM-122] entry.options mit Lab-Inhalten → nur Zähler im Download."""
    hass = MagicMock()
    hass.data = {}
    entry = SimpleNamespace(entry_id="e1", version=5, options=_LAB_OPTIONS)

    out = asyncio.run(diagnostics.async_get_config_entry_diagnostics(hass, entry))

    assert out["options"][const.OPTION_LAB_CUSTOM_MARKERS] == {"count": 2}
    blob = _blob(out)
    assert "Vitamin-D-Mangel" not in blob
    assert "vitamin_d" not in blob


# ============================================================================
# REQ-HOM-122, Fund N-1 — Labor-Entity-IDs maskieren (Freitext-Markername)
# ============================================================================


def _registry_fake(monkeypatch, entries):
    """Entity-Registry-Fake mit expliziten ``unique_id``-Werten installieren."""
    registry_module = types.ModuleType("homeassistant.helpers.entity_registry")
    registry_module.async_get = lambda hass: "registry"
    registry_module.async_entries_for_config_entry = lambda registry, entry_id: list(entries)
    monkeypatch.setitem(sys.modules, "homeassistant.helpers.entity_registry", registry_module)
    helpers_module = sys.modules.get("homeassistant.helpers")
    if helpers_module is not None:
        monkeypatch.setattr(helpers_module, "entity_registry", registry_module, raising=False)
    return registry_module


def test_async_diagnostics_masks_custom_lab_entity_ids(monkeypatch):
    """[REQ-HOM-122/N-1] Custom-Marker-Freitext leakt nicht über die Entity-ID.

    Ein Custom-Labor-Sensor heißt ``sensor.<person>_<marker-name>`` — der Name
    ist Nutzer-Freitext (potenziell eine Diagnose) und darf im öffentlich
    teilbaren Diagnostics-Download nicht auftauchen. Katalog-Marker bleiben als
    öffentlicher Katalog-Key lesbar, Custom-Marker werden durchnummeriert.
    """
    _registry_fake(
        monkeypatch,
        [
            SimpleNamespace(entity_id="sensor.max_hiv_test", unique_id="e1_lab_hiv_test"),
            SimpleNamespace(entity_id="sensor.max_alt", unique_id="e1_lab_alt"),
            SimpleNamespace(
                entity_id="sensor.max_borreliose_titer", unique_id="e1_lab_borreliose_titer"
            ),
            SimpleNamespace(entity_id="sensor.max_drinks_today", unique_id="e1_drinks_today"),
            SimpleNamespace(
                entity_id="binary_sensor.max_lab_warning_liver",
                unique_id="e1_binary_lab_warning_liver",
            ),
        ],
    )

    hass = MagicMock()
    hass.data = {DOMAIN: {}}
    entry = SimpleNamespace(entry_id="e1", version=5, options={})

    out = asyncio.run(diagnostics.async_get_config_entry_diagnostics(hass, entry))

    assert out["entities"] == [
        "binary_sensor.max_lab_warning_liver",
        "sensor.***_lab_alt",
        "sensor.***_lab_custom_1",
        "sensor.***_lab_custom_2",
        "sensor.max_drinks_today",
    ]
    blob = _blob(out)
    for token in ("hiv_test", "borreliose_titer", "max_hiv"):
        assert token not in blob, f"geleakt: {token!r}"


def test_redact_entity_ids_without_registry_metadata_keeps_ids():
    """[REQ-HOM-122/N-1] Ohne Marker-Key (reine IDs) bleibt die Liste unverändert."""
    out = diagnostics.redact_diagnostics({"entity_ids": ["sensor.a", "sensor.b"]})

    assert out["entities"] == ["sensor.a", "sensor.b"]


# ============================================================================
# Post-Release-Befund 1 — verwaiste Labor-Entities (Soll/Ist-Vergleich)
# ============================================================================
#
# Nach der A-1-Normalisierung (unbekannte Custom-Kategorie -> "other") können
# Labor-Entities in der Registry stehen, die das Setup nicht mehr anlegt. Sie
# sind als "restored"/"unavailable" weiter sichtbar — ein Check "Registry-
# Eintrag ohne State" findet sie deshalb NICHT. Die Sektion
# `lab_entity_orphans` vergleicht die Soll-Menge (dieselben Keys, die
# sensor.py/binary_sensor.py beim Setup erzeugen) mit der Registry.

_LAB_ENTRY_ID = "e1"


class _States:
    """Minimal-``hass.states`` mit ``get(entity_id)``."""

    def __init__(self, mapping):
        self._mapping = mapping

    def get(self, entity_id):
        return self._mapping.get(entity_id)


def _lab_registry(monkeypatch, entries):
    """Registry-Fake mit vollständigen Labor-Records (platform + unique_id)."""
    return _registry_fake(
        monkeypatch,
        [
            SimpleNamespace(
                entity_id=entity_id,
                unique_id=f"{_LAB_ENTRY_ID}_{key_part}",
                platform=platform,
            )
            for entity_id, key_part, platform in entries
        ],
    )


def _lab_hass(states=None):
    return SimpleNamespace(data={DOMAIN: {}}, states=_States(states or {}))


def _lab_entry(options=None):
    return SimpleNamespace(entry_id=_LAB_ENTRY_ID, version=5, options=dict(options or {}))


def _custom_marker(key="ferritin", name="Ferritin", category="blood_count", unit="ng/mL"):
    return {"key": key, "name": name, "category": category, "unit": unit}


def test_expected_lab_entity_keys_matches_platform_setup():
    """[Orphan-Diagnose] Soll-Menge = ein Sensor je Marker + Warnung je Kategorie."""
    keys = diagnostics.expected_lab_entity_keys({})

    # Katalog: ein Sensor je Marker.
    for marker_key in const.LAB_MARKERS:
        assert f"lab_{marker_key}" in keys
    # Warnungen je Markt-Kategorie — "other" hat bewusst keine Warn-Entity.
    assert "binary_lab_warning_liver" in keys
    assert "binary_lab_warning_lipids" in keys
    assert "binary_lab_warning_other" not in keys
    # REQ-HOM-133 (#73): neue Kategorie inkl. HbA1c-Sensor/Warnung.
    assert "binary_lab_warning_metabolism" in keys
    assert "lab_hba1c" in keys
    assert len(keys) == len(const.LAB_MARKERS) + (
        len(const.LAB_CATEGORIES) - 1  # alle außer "other"
    )
    # Jede Warn-Kategorie stammt aus const.LAB_CATEGORIES.
    categories = {category["key"] for category in const.LAB_CATEGORIES}
    for key in keys:
        if key.startswith("binary_lab_warning_"):
            assert key.removeprefix("binary_lab_warning_") in categories


def test_expected_lab_entity_keys_adds_custom_marker_and_category():
    """[Orphan-Diagnose] Custom-Marker erweitert Soll-Menge (Sensor + Warnung)."""
    keys = diagnostics.expected_lab_entity_keys(
        {const.OPTION_LAB_CUSTOM_MARKERS: [_custom_marker()]}
    )

    assert "lab_ferritin" in keys
    # blood_count existiert bereits im Katalog -> keine neue Kategorie.
    assert "binary_lab_warning_blood_count" in keys


def test_expected_lab_entity_keys_empty_when_labs_area_disabled():
    """[Orphan-Diagnose] Bereich "labs" aus -> Soll-Menge leer, hypothetisch nicht."""
    options = {"areas": {"labs": False}}

    assert diagnostics.expected_lab_entity_keys(options) == set()
    assert "lab_alt" in diagnostics.expected_lab_entity_keys(options, ignore_area=True)


def test_lab_entity_orphans_flags_foreign_category(monkeypatch):
    """[Orphan-Diagnose] Warn-Entity einer Fremdkategorie wird als Orphan erkannt.

    A-1: eine unbekannte Custom-Kategorie fällt auf "other" — die frühere
    Warn-Entity ``binary_lab_warning_hair_analysis`` legt das Setup nicht mehr
    an. Der Sensor desselben Markers bleibt gültig.
    """
    _lab_registry(
        monkeypatch,
        [
            (
                "binary_sensor.max_lab_warning_hair_analysis",
                "binary_lab_warning_hair_analysis",
                DOMAIN,
            ),
            ("sensor.max_haar", "lab_haar", DOMAIN),
            ("sensor.max_alt", "lab_alt", DOMAIN),
        ],
    )
    options = {
        const.OPTION_LAB_CUSTOM_MARKERS: [
            _custom_marker(key="haar", name="Haaranalyse", category="hair_analysis"),
        ]
    }

    out = asyncio.run(
        diagnostics.async_get_config_entry_diagnostics(_lab_hass(), _lab_entry(options))
    )

    orphans = out["lab_entity_orphans"]
    assert orphans["count"] == 1
    assert orphans["items"] == [
        {
            "entity_id": "binary_sensor.***_lab_warning_hair_analysis",
            "unique_id": "e1_binary_lab_warning_hair_analysis",
            "state": "missing",
            "reason": "unknown_category",
        }
    ]
    # Der Sensor des Custom-Markers ist KEIN Orphan (er wird weiter angelegt).
    assert "sensor.***_lab_custom_1" in out["entities"]


def test_lab_entity_orphans_flags_stale_marker_key_and_masks_it(monkeypatch):
    """[Orphan-Diagnose/N-1] Entfernter Custom-Marker: Orphan, aber maskiert."""
    _lab_registry(
        monkeypatch,
        [
            ("sensor.max_hiv_test", "lab_hiv_test", DOMAIN),
            ("sensor.max_alt", "lab_alt", DOMAIN),
        ],
    )

    out = asyncio.run(diagnostics.async_get_config_entry_diagnostics(_lab_hass(), _lab_entry({})))

    orphans = out["lab_entity_orphans"]
    assert orphans["count"] == 1
    item = orphans["items"][0]
    assert item["reason"] == "stale_marker_key"
    assert item["entity_id"] == "sensor.***_lab_custom_1"
    assert item["unique_id"] == "e1_lab_custom_1"
    # Der Freitext-Key (potenziell eine Diagnose) darf nirgends auftauchen.
    blob = _blob(out)
    for token in ("hiv_test", "max_hiv"):
        assert token not in blob, f"geleakt: {token!r}"


def test_lab_entity_orphans_does_not_flag_valid_entities(monkeypatch):
    """[Orphan-Diagnose] Korrekt angelegte Labor-Entities sind keine Orphans."""
    _lab_registry(
        monkeypatch,
        [
            ("sensor.max_alt", "lab_alt", DOMAIN),
            ("sensor.max_ferritin", "lab_ferritin", DOMAIN),
            ("binary_sensor.max_lab_warning_blood_count", "binary_lab_warning_blood_count", DOMAIN),
            ("binary_sensor.max_lab_warning_liver", "binary_lab_warning_liver", DOMAIN),
        ],
    )
    options = {const.OPTION_LAB_CUSTOM_MARKERS: [_custom_marker()]}

    out = asyncio.run(
        diagnostics.async_get_config_entry_diagnostics(_lab_hass(), _lab_entry(options))
    )

    assert out["lab_entity_orphans"] == {"count": 0, "items": []}


def test_lab_entity_orphans_reports_not_provided_when_area_disabled(monkeypatch):
    """[Orphan-Diagnose] Bereich "labs" aus -> gültige Keys sind nicht bereitgestellt."""
    _lab_registry(monkeypatch, [("sensor.max_alt", "lab_alt", DOMAIN)])
    options = {"areas": {"labs": False}}

    out = asyncio.run(
        diagnostics.async_get_config_entry_diagnostics(_lab_hass(), _lab_entry(options))
    )

    assert out["lab_entity_orphans"]["count"] == 1
    assert out["lab_entity_orphans"]["items"][0]["reason"] == "not_provided"


def test_lab_entity_orphans_honours_platform_filter(monkeypatch):
    """[Orphan-Diagnose] Nur eigene Plattform-Einträge werden bewertet."""
    _lab_registry(
        monkeypatch,
        [
            ("sensor.max_alt", "lab_alt", "other_integration"),
            ("sensor.max_ghost", "lab_ghost", "other_integration"),
        ],
    )

    out = asyncio.run(diagnostics.async_get_config_entry_diagnostics(_lab_hass(), _lab_entry({})))

    assert out["lab_entity_orphans"] == {"count": 0, "items": []}


def test_lab_entity_orphans_reports_state_class_never_the_value(monkeypatch):
    """[Orphan-Diagnose/N-5] State wird als Klasse ausgegeben, nie als Messwert."""
    _lab_registry(
        monkeypatch,
        [
            ("sensor.max_hiv_test", "lab_hiv_test", DOMAIN),
            ("sensor.max_old", "lab_old", DOMAIN),
            ("sensor.max_gone", "lab_gone", DOMAIN),
        ],
    )
    states = {
        "sensor.max_hiv_test": SimpleNamespace(state="restored"),
        # Ein echter Laborwert darf NICHT in den Output wandern.
        "sensor.max_old": SimpleNamespace(state="42.7"),
    }

    out = asyncio.run(
        diagnostics.async_get_config_entry_diagnostics(_lab_hass(states), _lab_entry({}))
    )

    by_reason = {item["entity_id"]: item["state"] for item in out["lab_entity_orphans"]["items"]}
    # Ordinal = sortierte Custom-Keys: gone=1, hiv_test=2, old=3.
    assert by_reason["sensor.***_lab_custom_2"] == "restored"
    assert by_reason["sensor.***_lab_custom_3"] == "provided"
    assert by_reason["sensor.***_lab_custom_1"] == "missing"
    assert "42.7" not in _blob(out)


def test_lab_entity_orphans_defaults_to_empty_without_registry():
    """[Orphan-Diagnose] Ohne Registry-Metadaten: definierte leere Sektion."""
    out = diagnostics.redact_diagnostics({"entity_ids": ["sensor.a"]})

    assert out["lab_entity_orphans"] == {"count": 0, "items": []}

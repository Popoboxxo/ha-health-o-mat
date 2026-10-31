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
    store.active_entry = MagicMock(
        side_effect=lambda entry_id: {
            "test-entry-1": {"drinks": drinks if drinks is not None else []},
        }.get(entry_id, {})
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
    data = {entry.entry_id: {"readings": readings}}
    store.all_entries = MagicMock(return_value=data)
    store.active_entry = MagicMock(side_effect=lambda entry_id: data.get(entry_id, {}))
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


# --- REQ-HOM-009: pro-Person Bereichs-Toggles filtern das Binary-Sensor-Setup ---

_ENTRY_ID = "test-entry-1"
_GOAL_REACHED_ID = "test-entry-1_binary_goal_reached"
_BP_WARNING_ID = "test-entry-1_binary_bp_warning"

_LOGIC = binary_sensor_module.logic
_CATALOG_LAB_CATEGORIES = {
    marker["category"]
    for marker in _LOGIC.LAB_MARKERS.values()
    if marker["category"] != _LOGIC.LAB_CATEGORY_OTHER
}
_LAB_WARNING_IDS = {
    f"{_ENTRY_ID}_binary_lab_warning_{category}" for category in _CATALOG_LAB_CATEGORIES
}


def _binary_setup(options: dict) -> set[str]:
    added: list = []

    hass = MagicMock()
    entry = MagicMock()
    entry.entry_id = _ENTRY_ID
    entry.options = options
    coord = MagicMock()
    store = MagicMock()
    store.all_entries = MagicMock(return_value={_ENTRY_ID: {}})
    store.active_entry = MagicMock(return_value={})
    hass.data = {
        "health_o_mat": {
            _ENTRY_ID: {"coordinator": coord},
            "shared": {"store": store},
        }
    }

    _run(binary_sensor_module.async_setup_entry(hass, entry, lambda ents: added.extend(ents)))
    return {e._attr_unique_id for e in added}


def test_binary_setup_old_entry_without_options_has_all_areas():
    """[REQ-HOM-009] Alt-Entry ohne areas-Option = alle Bereiche aktiv."""
    assert _binary_setup({}) == {_GOAL_REACHED_ID, _BP_WARNING_ID} | _LAB_WARNING_IDS


def test_binary_setup_drink_disabled_keeps_bp():
    """[REQ-HOM-009] drink AUS → BP-Warnung + Lab-Warnungen bleiben."""
    assert _binary_setup({"areas": {"drink": False}}) == {_BP_WARNING_ID} | _LAB_WARNING_IDS


def test_binary_setup_only_drink_when_bp_disabled():
    """[REQ-HOM-009] bp AUS → Tagesziel-Binary + Lab-Warnungen bleiben."""
    assert _binary_setup({"areas": {"bp": False}}) == {_GOAL_REACHED_ID} | _LAB_WARNING_IDS


def test_binary_unique_ids_stable_across_area_toggle():
    """[REQ-HOM-009] De-/Reaktivieren erzeugt dieselben unique_ids."""
    on_ids = _binary_setup({})
    off_ids = _binary_setup({"areas": {"drink": False}})
    on_again_ids = _binary_setup({"areas": {"drink": True}})

    assert _GOAL_REACHED_ID in on_ids
    assert _GOAL_REACHED_ID not in off_ids
    assert on_again_ids == on_ids


# ============================================================================
# M2a: voided Einträge lösen keine Zustände aus
# ============================================================================


def test_m2a_goal_reached_ignores_voided_drink():
    """[M2a] Voided Getränk zählt nicht für das Tagesziel."""
    init = _load_init()
    store_module = sys.modules[f"{_PKG}.store"]
    store = _fresh_store(store_module)
    _run(store.add_drink("e1", "2026-10-15T08:00:00", 250, "Wasser", "button"))
    _run(store.add_drink("e1", "2026-10-15T09:00:00", 800, "Kaffee", "button"))
    _run(store.void_drink("e1", store.entry("e1")["drinks"][1]["id"]))

    entry = _bp_entry("e1")
    entry.runtime_data = init.HealthOMatData()
    entry.runtime_data.daily_goal_ml = 500
    binary_sensor_module.dt_util.now = MagicMock(return_value=datetime(2026, 10, 15, 12, 0))

    entity = binary_sensor_module.GoalReachedEntity(MagicMock(), entry, store)

    assert entity.is_on is False


def test_m2a_bp_warning_ignores_voided_reading():
    """[M2a] Voided Messung löst keine BP-Warnung aus (aktive bleibt maßgeblich)."""
    init = _load_init()
    store_module = sys.modules[f"{_PKG}.store"]
    store = _fresh_store(store_module)
    _run(store.add_reading("e1", "2026-10-15T08:00:00", 120, 80, 60))
    _run(store.add_reading("e1", "2026-10-15T09:00:00", 200, 120, 90))
    _run(store.void_reading("e1", store.entry("e1")["readings"][1]["id"]))

    entry = _bp_entry("e1")
    entry.runtime_data = init.HealthOMatData()

    entity = binary_sensor_module.BloodPressureWarningEntity(MagicMock(), entry, store)

    assert entity.is_on is False


def test_m2a_bp_warning_uses_latest_active_reading():
    """[M2a] Maßgeblich ist die letzte AKTIVE Messung (voided Neue zählt nicht)."""
    init = _load_init()
    store_module = sys.modules[f"{_PKG}.store"]
    store = _fresh_store(store_module)
    _run(store.add_reading("e1", "2026-10-15T08:00:00", 200, 120, 90))
    _run(store.add_reading("e1", "2026-10-16T08:00:00", 125, 82, 60))
    _run(store.void_reading("e1", store.entry("e1")["readings"][1]["id"]))

    entry = _bp_entry("e1")
    entry.runtime_data = init.HealthOMatData()

    entity = binary_sensor_module.BloodPressureWarningEntity(MagicMock(), entry, store)

    assert entity.is_on is True


# ============================================================================
# REQ-HOM-122: LabCategoryWarningEntity — Warnung je Laborwert-Kategorie
# ============================================================================

_LAB_ENTRY_ID = "e1"


def _lab_marker_value(marker_def: dict) -> float:
    """Repräsentativer Wert INNERHALB des Katalog-Referenzbereichs."""
    ref_min, ref_max = marker_def.get("ref_min"), marker_def.get("ref_max")
    if ref_min is not None and ref_max is not None:
        return (ref_min + ref_max) / 2
    if ref_min is not None:
        return ref_min + 1
    if ref_max is not None:
        return ref_max - 1
    return 1.0


def _lab_store(overrides: dict[str, float] | None = None) -> MagicMock:
    """Store-Mock: liefert je Marker den letzten aktiven Laborwert.

    Default = jeweils Bereichsmitte des Katalog-Referenzbereichs (also
    in-range); ``overrides`` setzt einzelne Marker auf einen abweichenden Wert.
    """
    values = {
        marker_key: _lab_marker_value(marker_def)
        for marker_key, marker_def in _LOGIC.LAB_MARKERS.items()
    }
    values.update(overrides or {})
    store = MagicMock()
    store.last_active_lab_reading = MagicMock(
        side_effect=lambda entry_id, marker_key: (
            {"value": values[marker_key]} if marker_key in values else None
        )
    )
    return store


def _lab_entity(
    options: dict | None = None, store: MagicMock | None = None, category: str = "liver"
):
    entry = _bp_entry(_LAB_ENTRY_ID, options=options)
    return binary_sensor_module.LabCategoryWarningEntity(
        MagicMock(), entry, store if store is not None else _lab_store(), category
    )


def _run_binary_setup(options: dict) -> list:
    """async_setup_entry mit aufzeichnendem async_add_entities → Entities."""
    added: list = []
    hass = MagicMock()
    entry = MagicMock()
    entry.entry_id = _ENTRY_ID
    entry.options = options
    hass.data = {
        "health_o_mat": {
            _ENTRY_ID: {"coordinator": MagicMock()},
            "shared": {"store": MagicMock()},
        }
    }
    _run(binary_sensor_module.async_setup_entry(hass, entry, lambda ents: added.extend(ents)))
    return added


def test_req_hom_122_lab_category_warning_off_when_in_range():
    """[REQ-HOM-122] Alle Marker der Kategorie im Referenzbereich → Warnung AUS."""
    entity = _lab_entity()

    assert entity.is_on is False


def test_req_hom_122_lab_category_warning_on_when_out_of_range():
    """[REQ-HOM-122] Ein Marker (GGT) außerhalb des Bereichs → Warnung AN."""
    entity = _lab_entity(store=_lab_store({"ggt": 999.0}))

    assert entity.is_on is True


def test_req_hom_122_lab_category_warning_off_without_any_reading():
    """[REQ-HOM-122] Keine erfassten Werte → keine Warnung."""
    store = MagicMock()
    store.last_active_lab_reading = MagicMock(return_value=None)
    entity = _lab_entity(store=store)

    assert entity.is_on is False


def test_req_hom_122_lab_category_warning_ignores_other_categories():
    """[REQ-HOM-122] Nur Marker der eigenen Kategorie lösen die Warnung aus."""
    # Kreatinin gehört zu "kidney", nicht zu "liver".
    entity = _lab_entity(store=_lab_store({"creatinine": 999.0}))

    assert entity.is_on is False


def test_req_hom_122_lab_category_warning_respects_ref_overrides():
    """[REQ-HOM-122] Options-Overrides verschieben den Referenzbereich."""
    # ALT-Bereichsmitte (30) liegt mit Override 40..60 außerhalb.
    entity = _lab_entity(options={"lab_ref_overrides": {"alt": {"ref_min": 40, "ref_max": 60}}})

    assert entity.is_on is True


def test_req_hom_122_lab_category_warning_reads_only_active_lab_readings():
    """[REQ-HOM-122] Quelle ist last_active_lab_reading (voided-Werte zählen nicht)."""
    store = _lab_store()
    entity = _lab_entity(store=store)

    assert entity.is_on is False
    assert store.last_active_lab_reading.called
    store.active_entry.assert_not_called()


def test_req_hom_122_async_setup_entry_creates_one_binary_sensor_per_catalog_category():
    """[REQ-HOM-122] Eine Warn-Entity je Katalog-Kategorie (stabile unique_id)."""
    added = _run_binary_setup({})

    lab_warnings = [
        entity
        for entity in added
        if isinstance(entity, binary_sensor_module.LabCategoryWarningEntity)
    ]
    assert {warning._category for warning in lab_warnings} == _CATALOG_LAB_CATEGORIES
    assert {warning._attr_unique_id for warning in lab_warnings} == _LAB_WARNING_IDS


def test_req_hom_122_async_setup_entry_skips_other_category():
    """[REQ-HOM-122] Kategorie "other" (nur Custom-Marker) bekommt keine Warnung."""
    added = _run_binary_setup(
        {"lab_custom_markers": [{"name": "Vitamin D", "category": "other", "unit": "ng/mL"}]}
    )

    lab_warnings = [
        entity
        for entity in added
        if isinstance(entity, binary_sensor_module.LabCategoryWarningEntity)
    ]
    assert all(warning._category != _LOGIC.LAB_CATEGORY_OTHER for warning in lab_warnings)
    assert {warning._category for warning in lab_warnings} == _CATALOG_LAB_CATEGORIES


def test_req_hom_122_async_setup_entry_skips_lab_warnings_when_area_disabled():
    """[REQ-HOM-122] labs AUS → keine Lab-Warn-Entities."""
    added = _run_binary_setup({"areas": {"labs": False}})

    lab_warnings = [
        entity
        for entity in added
        if isinstance(entity, binary_sensor_module.LabCategoryWarningEntity)
    ]
    assert lab_warnings == []

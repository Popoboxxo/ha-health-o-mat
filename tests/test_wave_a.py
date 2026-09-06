"""Tests: Funde-&-Risiken-Fixes Welle A (REQ-HOM-101/102/103/104).

- Store-Schema-Migration v1 → v2 (+inputs)
- Corrupt-Recovery (Backup + Notification + leerer Start)
- Config-Entry-Migration v1 → v2 (quick_drinks → options)
- Persistierte BP-Eingaben (InputNumber ↔ Store)
"""
import asyncio
import importlib.util
import os
import sys
import types
from unittest.mock import AsyncMock, MagicMock, PropertyMock

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


store_module = _load("store")
config_flow_module = _load("config_flow")
number_module = _load("number")
const_module = _load("const")

SCHEMA = const_module.STORE_SCHEMA_VERSION


def _make_store():
    store = store_module.HealthOMatStore(MagicMock())
    # Store-Backend mocken: async_load liefert das Fixture, async_save nichts
    store._store = MagicMock()
    store._store.async_save = AsyncMock(return_value=None)
    return store


def _v1_fixture() -> dict:
    """Repäsentativer v0.4.0-Bestand (kein schema-Feld, keine inputs)."""
    return {
        "entries": {
            "e1": {
                "person": "Max",
                "drinks": [{"ts": "2026-09-01T08:00:00", "ml": 250, "type": "Kaffee", "src": "quick_button"}],
                "readings": [{"ts": "2026-09-01T09:00:00", "sys": 120, "dia": 80, "pulse": 60, "note": "", "src": "button"}],
                "total_ml_lifetime": 250,
                "wellbeing": {"status": "good", "ts": "2026-09-01T10:00:00"},
                "wellbeing_history": [],
            }
        }
    }


def test_store_migration_v1_to_current_adds_inputs():
    """[REQ-HOM-102] v1-Bestand wird auf aktuelle Schema-Stufe migriert."""
    store = _make_store()
    store._store.async_load = AsyncMock(return_value=_v1_fixture())
    asyncio.get_event_loop().run_until_complete(store.async_load()) \
        if False else _run(store.async_load())
    data = store.raw_data()
    assert data["schema"] == SCHEMA
    e1 = data["entries"]["e1"]
    assert e1["inputs"] == {}
    assert e1["drinks"] == _v1_fixture()["entries"]["e1"]["drinks"]  # Daten unverändert


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def test_store_migration_is_idempotent():
    """[REQ-HOM-102] Doppeltes Laden migriert nicht kaputt (idempotent)."""
    store = _make_store()
    store._store.async_load = AsyncMock(return_value=_v1_fixture())
    _run(store.async_load())
    first = store.raw_data()["entries"]["e1"]
    _run(store.async_load())
    second = store.raw_data()["entries"]["e1"]
    assert second["inputs"] == first["inputs"] == {}
    assert store.raw_data()["schema"] == SCHEMA


def test_store_invalid_schema_creates_backup_and_notification():
    """[REQ-HOM-103] Valides JSON ohne 'entries' → Backup + Notification + leerer Start.

    (Kaputtes JSON handhabt HA selbst: Backup *.corrupt.* + Repairs-Eintrag —
    dies hier ist nur der Schema-Fall.)
    """
    store = _make_store()
    store._store.async_load = AsyncMock(return_value={"unexpected": True})
    hass = MagicMock()
    hass.async_add_executor_job = AsyncMock(return_value=True)
    hass.services.async_call = AsyncMock()
    store._hass = hass

    _run(store.async_load())

    assert store.raw_data() == {"entries": {}}
    hass.services.async_call.assert_called_once()
    args = hass.services.async_call.call_args[0]
    assert args[0] == "persistent_notification"
    assert ".invalid-schema-" in args[2]["message"]


def test_store_none_is_fresh_start_without_notification():
    """[REQ-HOM-103] Erstanlage (None) — kein Alarm, kein Backup."""
    store = _make_store()
    store._store.async_load = AsyncMock(return_value=None)
    hass = MagicMock()
    store._hass = hass

    _run(store.async_load())

    assert store.raw_data() == {"entries": {}}
    hass.services.async_call.assert_not_called()


def _migrate_entry(entry, hass):
    """async_migrate_entry aus __init__.py — hier isoliert nachgebaut getestet,
    weil das Modul homeassistant-Setup-Imports braucht; Logik wird 1:1 in
    __init__.py gepflegt (Doppelwache gegen Drift über gemeinsame Fixture)."""
    init_module = _load_init()
    return init_module.async_migrate_entry(hass, entry)


def _load_init():
    """__init__.py mit Fake-Modulen laden (Store/Entityketten via _PKG)."""
    for name in ("store", "entity", "const", "parser", "logic", "exporter"):
        _load(name)
    spec = importlib.util.spec_from_file_location(
        f"{_PKG}.init", os.path.join(_COMPONENT_DIR, "__init__.py")
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[f"{_PKG}.init"] = module
    spec.loader.exec_module(module)
    return module


def test_config_entry_migration_v1_moves_quick_drinks_to_options():
    """[REQ-HOM-101] v1-Entry: quick_drinks aus data → options, Version 2."""
    entry = MagicMock()
    entry.version = 1
    entry.title = "Health-O-Mat · Max"
    entry.data = {
        "person": "Max",
        "quick_drinks": [{"key": "glas_wasser", "label": "Glas Wasser", "ml": 200, "icon": "mdi:glass-water"}],
    }
    entry.options = {}
    hass = MagicMock()
    hass.config_entries.async_update_entry = MagicMock()

    ok = _run(_migrate_entry(entry, hass))

    assert ok is True
    updated = hass.config_entries.async_update_entry.call_args
    assert updated[1]["version"] == 2
    assert "quick_drinks" not in updated[1]["data"]
    assert updated[1]["options"]["quick_drinks"][0]["label"] == "Glas Wasser"


def test_config_entry_migration_v2_is_noop():
    """[REQ-HOM-101] v2-Entry wird nicht erneut angefasst."""
    entry = MagicMock()
    entry.version = 2
    entry.data = {"person": "Max"}
    entry.options = {}
    hass = MagicMock()
    hass.config_entries.async_update_entry = MagicMock()

    ok = _run(_migrate_entry(entry, hass))

    assert ok is True
    hass.config_entries.async_update_entry.assert_not_called()


def test_config_entry_migration_rejects_downgrade():
    """[REQ-HOM-101] Version > 2 → False (kein Downgrade)."""
    entry = MagicMock()
    entry.version = 3
    hass = MagicMock()
    ok = _run(_migrate_entry(entry, hass))
    assert ok is False


def _make_input_number(store):
    entry = MagicMock()
    entry.entry_id = "e1"
    coordinator = MagicMock()
    number = number_module.InputNumber(
        coordinator, entry, store, "sys", "input_systolic", 40, 260, "mdi:arrow-up-right"
    )
    return number, entry


def test_input_number_persists_via_store():
    """[REQ-HOM-104] InputNumber liest/schreibt über den Store (neustartfest)."""
    real_store = _make_store()
    real_store._store.async_load = AsyncMock(return_value=None)
    _run(real_store.async_load())

    number, entry = _make_input_number(real_store)
    assert number.native_value is None

    _run(number._apply(125))
    assert real_store.inputs("e1")["sys"] == 125
    assert number.native_value == 125

    _run(number._apply(0))  # 0/leer → None
    assert real_store.inputs("e1")["sys"] is None


def test_store_clear_inputs():
    """[REQ-HOM-104] save_measurement leert alle Eingaben."""
    real_store = _make_store()
    real_store._store.async_load = AsyncMock(return_value=None)
    _run(real_store.async_load())
    _run(real_store.set_inputs("e1", "sys", 120))
    _run(real_store.set_inputs("e1", "dia", 80))
    assert real_store.inputs("e1") == {"sys": 120, "dia": 80}
    _run(real_store.clear_inputs("e1"))
    assert real_store.inputs("e1") == {}

"""Tests: `async_migrate_entry` v2->v3 against a fake registry (REQ-HOM-130).

`__init__.py` is loaded via importlib like in `tests/test_wave_a.py` (own package
prefix so the two modules do not collide in the `sys.modules` cache).
`er.async_migrate_entries` is an `AsyncMock` whose side effect actually applies
the callback dicts — only then do the mapping and the drift diagnosis get
exercised instead of just the `await` (Spec §6.2).
"""

from __future__ import annotations

import asyncio
import importlib.util
import os
import sys
import types
from dataclasses import dataclass, field
from unittest.mock import AsyncMock, MagicMock

import homeassistant.helpers.device_registry as dr
import homeassistant.helpers.entity_registry as er

_COMPONENT_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "custom_components", "health_o_mat")
)
_PKG = "_hom_entry_migration_pkg"
_pkg = types.ModuleType(_PKG)
_pkg.__path__ = [_COMPONENT_DIR]
sys.modules.setdefault(_PKG, _pkg)

ENTRY_ID = "01JENTRY"
SLUG = "health_o_mat_max"
DEVICE_ID = "dev1"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(
        f"{_PKG}.{name}", os.path.join(_COMPONENT_DIR, f"{name}.py")
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[f"{_PKG}.{name}"] = module
    spec.loader.exec_module(module)
    return module


def _load_init():
    for name in ("store", "entity", "const", "parser", "logic", "exporter", "migration"):
        _load(name)
    spec = importlib.util.spec_from_file_location(
        f"{_PKG}.init", os.path.join(_COMPONENT_DIR, "__init__.py")
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[f"{_PKG}.init"] = module
    spec.loader.exec_module(module)
    return module


@dataclass
class _RegEntry:
    entity_id: str
    unique_id: str
    translation_key: str | None = None
    device_id: str | None = DEVICE_ID
    config_entry_id: str = ENTRY_ID
    original_name: str | None = None
    entity_category: str | None = None
    labels: set[str] = field(default_factory=set)
    aliases: list[str] = field(default_factory=list)
    area_id: str | None = None
    hidden_by: str | None = None
    disabled_by: str | None = None


class _FakeRegistry:
    def __init__(self, entries: list[_RegEntry]) -> None:
        self.entities = {entry.entity_id: entry for entry in entries}

    def async_get(self, entity_id: str) -> _RegEntry | None:
        return self.entities.get(entity_id)


class _FakeDevice:
    def __init__(self, name: str, name_by_user: str | None = None) -> None:
        self.id = DEVICE_ID
        self.name = name
        self.name_by_user = name_by_user
        self.identifiers = {("health_o_mat", ENTRY_ID)}


class _FakeDeviceRegistry:
    def __init__(self, device: _FakeDevice | None) -> None:
        self._device = device

    def async_get_device_by_identifier(self, identifiers, config_entry_id):
        if (
            self._device is not None
            and ("health_o_mat", config_entry_id) in self._device.identifiers
        ):
            return self._device
        return None

    def async_get(self, device_id: str | None):
        if self._device is not None and device_id == self._device.id:
            return self._device
        return None


def _make_hass(*, states: list | None = None) -> MagicMock:
    hass = MagicMock()
    hass.states.async_all = MagicMock(return_value=list(states or []))
    hass.config_entries.async_update_entry = MagicMock()
    return hass


def _make_entry(*, version: int = 2, data: dict | None = None, options: dict | None = None):
    entry = MagicMock()
    entry.entry_id = ENTRY_ID
    entry.version = version
    entry.title = "Health-O-Mat · Max"
    entry.data = data if data is not None else {"person": "Max"}
    entry.options = options if options is not None else {}
    return entry


def _install(monkeypatch, registry: _FakeRegistry, device: _FakeDevice | None):
    """Wire the fake registries into the fake HA modules; return the AsyncMock."""
    migrate = AsyncMock()

    async def _apply(hass, config_entry_id, update_callback):
        for reg in list(registry.entities.values()):
            if reg.config_entry_id != config_entry_id:
                continue
            changes = update_callback(reg)
            if not changes:
                continue
            new_id = changes["new_entity_id"]
            registry.entities.pop(reg.entity_id)
            reg.entity_id = new_id
            registry.entities[new_id] = reg

    migrate.side_effect = _apply
    monkeypatch.setattr(er, "async_migrate_entries", migrate)
    monkeypatch.setattr(
        er,
        "async_entries_for_config_entry",
        lambda reg, config_entry_id: [
            item for item in reg.entities.values() if item.config_entry_id == config_entry_id
        ],
    )
    monkeypatch.setattr(er, "async_get", lambda hass: registry)
    monkeypatch.setattr(dr, "async_get", lambda hass: _FakeDeviceRegistry(device))
    return migrate


def _standard_entries() -> list[_RegEntry]:
    return [
        _RegEntry(
            f"button.{SLUG}_glas_wasser",
            f"{ENTRY_ID}_button_quick_0",
            original_name="Glas Wasser",
        ),
        _RegEntry(
            f"button.{SLUG}_tasse_kaffee",
            f"{ENTRY_ID}_button_quick_2",
            original_name="Kaffee",
        ),
        _RegEntry(
            f"sensor.{SLUG}_vitamin_d",
            f"{ENTRY_ID}_lab_vitamin_d",
            original_name="Vitamin D",
        ),
        _RegEntry(f"sensor.{SLUG}_crp", f"{ENTRY_ID}_lab_crp", "lab_crp", original_name="CRP"),
        _RegEntry(
            f"sensor.{SLUG}_drinks_today",
            f"{ENTRY_ID}_today",
            "today",
            original_name="Heute getrunken",
        ),
        _RegEntry(
            f"sensor.{SLUG}_daily_goal_progress",
            f"{ENTRY_ID}_goal_percent",
            "goal_percent",
            original_name="Tagesziel",
        ),
        _RegEntry(
            f"button.{SLUG}_book_custom_amount",
            f"{ENTRY_ID}_button_book_custom",
            "book_custom",
            original_name="Eigene Menge",
        ),
    ]


def test_req_hom_130_migrates_quick_and_custom_only(monkeypatch):
    registry = _FakeRegistry(_standard_entries())
    migrate = _install(monkeypatch, registry, _FakeDevice("Health-O-Mat Max"))
    init = _load_init()
    hass = _make_hass()

    assert asyncio.run(init.async_migrate_entry(hass, _make_entry())) is True

    assert migrate.await_count == 1
    callback = migrate.call_args.args[2]
    applied = {}
    for reg in _standard_entries():
        changes = callback(reg)
        if changes:
            applied[reg.entity_id] = changes["new_entity_id"]
    assert applied == {
        f"button.{SLUG}_glas_wasser": f"button.{SLUG}_quick_drink_1",
        f"button.{SLUG}_tasse_kaffee": f"button.{SLUG}_quick_drink_3",
        f"sensor.{SLUG}_vitamin_d": f"sensor.{SLUG}_lab_vitamin_d",
    }


def test_req_hom_130_callback_sets_only_new_entity_id(monkeypatch):
    registry = _FakeRegistry(_standard_entries())
    migrate = _install(monkeypatch, registry, _FakeDevice("Health-O-Mat Max"))
    init = _load_init()

    assert asyncio.run(init.async_migrate_entry(_make_hass(), _make_entry())) is True

    callback = migrate.call_args.args[2]
    for reg in _standard_entries():
        changes = callback(reg)
        if changes:
            assert set(changes) == {"new_entity_id"}


def test_req_hom_130_awaits_async_migrate_entries(monkeypatch):
    """B-1 regression: a non-awaited call fails this test."""
    registry = _FakeRegistry(_standard_entries())
    migrate = _install(monkeypatch, registry, _FakeDevice("Health-O-Mat Max"))
    init = _load_init()

    asyncio.run(init.async_migrate_entry(_make_hass(), _make_entry()))

    migrate.assert_awaited_once()


def test_req_hom_130_bumps_to_version_3_on_success(monkeypatch):
    registry = _FakeRegistry(_standard_entries())
    _install(monkeypatch, registry, _FakeDevice("Health-O-Mat Max"))
    init = _load_init()
    hass = _make_hass()
    entry = _make_entry(options={"lab_custom_markers": [{"name": "Vitamin D", "unit": "ng/mL"}]})

    assert asyncio.run(init.async_migrate_entry(hass, entry)) is True

    hass.config_entries.async_update_entry.assert_called_once()
    _args, kwargs = hass.config_entries.async_update_entry.call_args
    assert kwargs["version"] == 3
    assert kwargs["data"] == {"person": "Max"}
    assert "lab_custom_markers" in kwargs["options"]


def test_req_hom_130_downgrade_guard_v4(monkeypatch):
    _install(monkeypatch, _FakeRegistry(_standard_entries()), _FakeDevice("Health-O-Mat Max"))
    init = _load_init()
    hass = _make_hass()

    assert asyncio.run(init.async_migrate_entry(hass, _make_entry(version=4))) is False
    hass.config_entries.async_update_entry.assert_not_called()


def test_req_hom_130_collision_skips_and_keeps_version(monkeypatch, caplog):
    registry = _FakeRegistry(_standard_entries())
    _install(monkeypatch, registry, _FakeDevice("Health-O-Mat Max"))
    init = _load_init()
    hass = _make_hass(states=[MagicMock(entity_id=f"button.{SLUG}_quick_drink_1")])

    with caplog.at_level("WARNING"):
        ok = asyncio.run(init.async_migrate_entry(hass, _make_entry()))

    assert ok is False
    hass.config_entries.async_update_entry.assert_not_called()
    assert "target_occupied" in caplog.text
    # Pair list, not just a count.
    assert f"button.{SLUG}_glas_wasser" in caplog.text


def test_req_hom_130_collision_retry_after_fix(monkeypatch):
    registry = _FakeRegistry(_standard_entries())
    _install(monkeypatch, registry, _FakeDevice("Health-O-Mat Max"))
    init = _load_init()
    entry = _make_entry()

    first_hass = _make_hass(states=[MagicMock(entity_id=f"button.{SLUG}_quick_drink_1")])
    assert asyncio.run(init.async_migrate_entry(first_hass, entry)) is False
    first_hass.config_entries.async_update_entry.assert_not_called()
    # Everything else was renamed — the retry only has the collision left.
    assert registry.async_get(f"button.{SLUG}_quick_drink_3") is not None
    assert registry.async_get(f"sensor.{SLUG}_lab_vitamin_d") is not None

    second_hass = _make_hass(states=[])
    assert asyncio.run(init.async_migrate_entry(second_hass, entry)) is True
    second_hass.config_entries.async_update_entry.assert_called_once()
    assert registry.async_get(f"button.{SLUG}_quick_drink_1") is not None


def test_req_hom_130_value_error_fails_closed(monkeypatch, caplog):
    registry = _FakeRegistry(_standard_entries())
    migrate = _install(monkeypatch, registry, _FakeDevice("Health-O-Mat Max"))
    migrate.side_effect = ValueError("Entity id already exists")
    init = _load_init()
    hass = _make_hass()

    with caplog.at_level("ERROR"):
        ok = asyncio.run(init.async_migrate_entry(hass, _make_entry()))

    assert ok is False
    hass.config_entries.async_update_entry.assert_not_called()
    assert "abgebrochen" in caplog.text


def test_req_hom_130_stale_marker_key_warns_but_renames(monkeypatch, caplog):
    registry = _FakeRegistry(_standard_entries())
    _install(monkeypatch, registry, _FakeDevice("Health-O-Mat Max"))
    init = _load_init()
    hass = _make_hass()

    with caplog.at_level("WARNING"):
        # Options do NOT list vitamin_d -> registry wins, rename still happens.
        ok = asyncio.run(
            init.async_migrate_entry(hass, _make_entry(options={"lab_custom_markers": []}))
        )

    assert ok is True
    assert "stale_marker_key vitamin_d" in caplog.text
    assert registry.async_get(f"sensor.{SLUG}_lab_vitamin_d") is not None


def test_req_hom_130_schema_drift_warns_and_fails(monkeypatch, caplog):
    registry = _FakeRegistry(_standard_entries())
    migrate = _install(monkeypatch, registry, _FakeDevice("Health-O-Mat Max"))
    # Simulate a silently broken pass: the callback is never applied.
    migrate.side_effect = None
    migrate.return_value = None
    init = _load_init()
    hass = _make_hass()

    with caplog.at_level("WARNING"):
        ok = asyncio.run(init.async_migrate_entry(hass, _make_entry()))

    assert ok is False
    hass.config_entries.async_update_entry.assert_not_called()
    assert "schema_drift" in caplog.text


def test_req_hom_130_second_run_is_noop(monkeypatch):
    registry = _FakeRegistry(_standard_entries())
    migrate = _install(monkeypatch, registry, _FakeDevice("Health-O-Mat Max"))
    init = _load_init()
    hass = _make_hass()

    assert asyncio.run(init.async_migrate_entry(hass, _make_entry(version=3))) is True

    migrate.assert_not_awaited()
    hass.config_entries.async_update_entry.assert_not_called()


def test_req_hom_130_v1_entry_is_migrated_to_v3_in_one_update(monkeypatch):
    registry = _FakeRegistry(_standard_entries())
    _install(monkeypatch, registry, _FakeDevice("Health-O-Mat Max"))
    init = _load_init()
    hass = _make_hass()
    entry = _make_entry(
        version=1,
        data={
            "person": "Max",
            "quick_drinks": [{"key": "glas_wasser", "label": "Glas Wasser", "ml": 200}],
        },
    )

    assert asyncio.run(init.async_migrate_entry(hass, entry)) is True

    hass.config_entries.async_update_entry.assert_called_once()
    _args, kwargs = hass.config_entries.async_update_entry.call_args
    assert kwargs["version"] == 3
    assert "quick_drinks" not in kwargs["data"]
    assert kwargs["options"]["quick_drinks"][0]["label"] == "Glas Wasser"
    assert registry.async_get(f"button.{SLUG}_quick_drink_1") is not None


def test_req_hom_130_v1_entity_failure_does_not_write_data(monkeypatch):
    registry = _FakeRegistry(_standard_entries())
    _install(monkeypatch, registry, _FakeDevice("Health-O-Mat Max"))
    init = _load_init()
    hass = _make_hass(states=[MagicMock(entity_id=f"button.{SLUG}_quick_drink_1")])
    entry = _make_entry(
        version=1,
        data={"person": "Max", "quick_drinks": [{"label": "Glas Wasser", "ml": 200}]},
    )

    assert asyncio.run(init.async_migrate_entry(hass, entry)) is False
    hass.config_entries.async_update_entry.assert_not_called()


def test_req_hom_130_no_entities_still_bumps_version(monkeypatch):
    _install(monkeypatch, _FakeRegistry([]), _FakeDevice("Health-O-Mat Max"))
    init = _load_init()
    hass = _make_hass()

    assert asyncio.run(init.async_migrate_entry(hass, _make_entry())) is True
    hass.config_entries.async_update_entry.assert_called_once()


def test_req_hom_130_state_machine_target_counts_as_occupied(monkeypatch):
    registry = _FakeRegistry(_standard_entries())
    _install(monkeypatch, registry, _FakeDevice("Health-O-Mat Max"))
    init = _load_init()
    # Target exists only in the state machine (no registry entry).
    hass = _make_hass(states=[MagicMock(entity_id=f"sensor.{SLUG}_lab_vitamin_d")])

    assert asyncio.run(init.async_migrate_entry(hass, _make_entry())) is False
    hass.config_entries.async_update_entry.assert_not_called()


def test_req_hom_130_migration_version_matches_config_flow():
    init = _load_init()
    config_flow = _load("config_flow")
    assert init.ENTITY_ID_MIGRATION_VERSION == config_flow.HealthOMatConfigFlow.VERSION


def test_req_hom_130_registry_fields_survive_the_rename(monkeypatch):
    quick = _RegEntry(
        f"button.{SLUG}_glas_wasser",
        f"{ENTRY_ID}_button_quick_0",
        original_name="Glas Wasser",
        entity_category="config",
        labels={"quick"},
        aliases=["button.glas_wasser"],
        area_id="kitchen",
        hidden_by="user",
        disabled_by=None,
    )
    today = _RegEntry(
        f"sensor.{SLUG}_drinks_today", f"{ENTRY_ID}_today", "today", original_name="Heute"
    )
    goal = _RegEntry(
        f"sensor.{SLUG}_daily_goal_progress",
        f"{ENTRY_ID}_goal_percent",
        "goal_percent",
        original_name="Ziel",
    )
    registry = _FakeRegistry([quick, today, goal])
    _install(monkeypatch, registry, _FakeDevice("Health-O-Mat Max"))
    init = _load_init()

    assert asyncio.run(init.async_migrate_entry(_make_hass(), _make_entry())) is True

    migrated = registry.async_get(f"button.{SLUG}_quick_drink_1")
    assert migrated is quick  # same registry record, only entity_id changed
    assert migrated.unique_id == f"{ENTRY_ID}_button_quick_0"
    assert migrated.original_name == "Glas Wasser"
    assert migrated.entity_category == "config"
    assert migrated.labels == {"quick"}
    assert migrated.aliases == ["button.glas_wasser"]
    assert migrated.area_id == "kitchen"
    assert migrated.hidden_by == "user"
    assert migrated.disabled_by is None

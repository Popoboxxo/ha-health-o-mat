"""Tests: Recorder-Statistik-Migration "ml" → "mL" (P1-Fix).

Deckt ab:
* Kernlogik (HA-frei): canonical_volume_unit()
* Verdrahtung: Recorder nicht eingerichtet → No-op, kein Recorder-Start, kein
  Retry/Start-Listener, kein Pending-Container in hass.data (F-04)
* Migration: nur eigene statistic_ids mit Legacy-Einheit werden angefasst
* Fallback (F-02): Registry liefert nichts → ungefilterter Recorder-Scan,
  gefiltert auf unsere beiden Volumen-Sensoren; Registry liefert IDs → KEIN
  Vollscan
* Idempotenz: zweiter Lauf tut nichts
* Fehlertoleranz: Recorder-API-Fehler → kein Raise (Setup scheitert nicht)
* Entity-IDs kommen aus der Entity-Registry (unique_id-basiert), nicht aus
  String-Konstruktion (Person-Slug/Sprache)
* Recorder-API-Signatur: exakte Keyword-Argumente (Schutz gegen API-Drift)
* Verdrahtung in __init__.py: das Setup ruft die Migration auf
"""

from __future__ import annotations

import asyncio
import importlib.util
import inspect
import os
import sys
import types
from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.exceptions import ServiceValidationError

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


def _load_init():
    """__init__.py mit Fake-Modulen laden (analog test_binary_sensor._load_init)."""
    for name in ("store", "entity", "const", "parser", "logic", "exporter", "statistics"):
        _load(name)
    spec = importlib.util.spec_from_file_location(
        f"{_PKG}.init", os.path.join(_COMPONENT_DIR, "__init__.py")
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[f"{_PKG}.init"] = module
    spec.loader.exec_module(module)
    return module


statistics_module = _load("statistics")

_ENTRY_ID = "entry-1"
_TODAY_ENTITY = "sensor.health_o_mat_max_drinks_today"
_LIFETIME_ENTITY = "sensor.health_o_mat_max_lifetime_total"


# --- Testdouble -----------------------------------------------------------


class _FakeRegistryEntry:
    """Entity-Registry-Eintrag (read-only Doublette)."""

    def __init__(self, entity_id: str, unique_id: str, platform: str = "sensor") -> None:
        self.entity_id = entity_id
        self.unique_id = unique_id
        self.platform = platform


class _FakeEntityRegistry:
    """Minimaler Entity-Registry-Ersatz — liefert nur Einträge zum Config-Entry."""

    def __init__(self, entries: list[_FakeRegistryEntry]) -> None:
        self._entries = entries
        self.requested_entry_ids: list[str] = []

    def async_get(self, hass):
        return "registry"

    def async_entries_for_config_entry(self, registry, config_entry_id):
        self.requested_entry_ids.append(config_entry_id)
        return list(self._entries)


class _FakeRecorderApi:
    """Recorder-API-Doublette.

    `list_statistic_ids` ist ein Coroutine (HA: async_list_statistic_ids),
    `update_statistics_metadata` ist ein Sync-Callback (HA:
    async_update_statistics_metadata) — genau diese Signaturen muss das Modul
    verwenden (kein await auf dem Update!).
    """

    def __init__(self, metadata: list[dict] | None = None, list_error=None) -> None:
        self.metadata = metadata if metadata is not None else []
        self.list_error = list_error
        # Je Aufruf der statistic_id-Liste: die Filter-Menge (set) oder None
        # für den ungefilterten Vollscan (Fallback).
        self.list_calls: list[set[str] | None] = []
        self.updates: list[tuple[str, dict]] = []

    async def list_statistic_ids(self, hass, statistic_ids=None, statistic_type=None):
        self.list_calls.append(statistic_ids)
        if self.list_error is not None:
            raise self.list_error
        return list(self.metadata)

    def update_statistics_metadata(self, hass, statistic_id, **kwargs):
        self.updates.append((statistic_id, kwargs))
        for item in self.metadata:
            if item.get("statistic_id") == statistic_id:
                item["statistics_unit_of_measurement"] = kwargs.get("new_unit_of_measurement")


def _make_hass(*, recorder_ready: bool = True) -> MagicMock:
    hass = MagicMock()
    hass.data = {}
    if recorder_ready:
        hass.data["recorder_instance"] = object()
    hass.state = "starting"
    hass.bus = MagicMock()
    return hass


def _make_entry(entry_id: str = _ENTRY_ID) -> MagicMock:
    entry = MagicMock()
    entry.entry_id = entry_id
    entry.data = {"person": "Max"}
    entry.options = {"retention_months": 0}
    return entry


def _install(monkeypatch, registry: _FakeEntityRegistry, api: _FakeRecorderApi) -> None:
    """Registry- und Recorder-Doubletten in das Modul einspeisen."""
    monkeypatch.setattr(statistics_module, "_load_entity_registry", lambda: registry)
    monkeypatch.setattr(
        statistics_module,
        "_load_recorder_api",
        lambda: (api.list_statistic_ids, api.update_statistics_metadata),
    )


def _default_registry() -> _FakeEntityRegistry:
    return _FakeEntityRegistry(
        [
            _FakeRegistryEntry(_TODAY_ENTITY, f"{_ENTRY_ID}_sensor_drinks_today"),
            _FakeRegistryEntry(_LIFETIME_ENTITY, f"{_ENTRY_ID}_sensor_lifetime_total"),
        ]
    )


# --- Kernlogik (HA-frei) --------------------------------------------------


def test_canonical_volume_unit_recognizes_legacy_variants():
    """Legacy-Einheit wird case-insensitive (mit Leerzeichen) erkannt."""
    assert statistics_module.canonical_volume_unit("ml") == "mL"
    assert statistics_module.canonical_volume_unit("ML") == "mL"
    assert statistics_module.canonical_volume_unit(" ml ") == "mL"


def test_canonical_volume_unit_ignores_canonical_and_other_units():
    """Kanonische Einheit und Fremdeinheiten → nichts zu tun."""
    assert statistics_module.canonical_volume_unit("mL") is None
    assert statistics_module.canonical_volume_unit("l") is None
    assert statistics_module.canonical_volume_unit("L") is None
    assert statistics_module.canonical_volume_unit("m³") is None
    assert statistics_module.canonical_volume_unit("") is None
    assert statistics_module.canonical_volume_unit(None) is None


def test_module_constants():
    """Die drei Konstanten der Kernlogik sind fest verdrahtet."""
    assert statistics_module.LEGACY_VOLUME_UNIT == "ml"
    assert statistics_module.CANONICAL_VOLUME_UNIT == "mL"
    assert statistics_module.VOLUME_UNIT_CLASS == "volume"


def test_legacy_volume_sensor_keys_match_sensor_unique_ids():
    """Die Allow-Liste bleibt mit den unique_ids der Volumen-Sensoren synchron.

    statistics.py filtert über die unique_id-Suffixe "{entry_id}_{key}" — die
    Keys müssen exakt den unique_ids der beiden Volumen-Sensoren in sensor.py
    entsprechen, sonst liefe die Migration ins Leere (kein Treffer in der
    Entity-Registry). Zusätzlich geprüft: die Sensoren melden bereits die
    kanonische Einheit, auf die migriert wird.

    Geprüft werden die ``_attr_*``-Attribute (die Quelle der Wahrheit in der
    HA-Entity): die Fake-HA im CI hat die Properties ``unique_id``/
    ``native_unit_of_measurement`` nicht — der Test muss in beiden Modi
    (echte HA / Fake-HA) identisch grün sein.
    """
    sensor_module = _load("sensor")
    entry = MagicMock()
    entry.entry_id = "entry-1"

    today = sensor_module.TodaySensor(MagicMock(), entry, MagicMock())
    lifetime = sensor_module.LifetimeSensor(MagicMock(), entry, MagicMock())

    assert today._attr_unique_id == "entry-1_sensor_drinks_today"
    assert lifetime._attr_unique_id == "entry-1_sensor_lifetime_total"
    assert set(statistics_module._LEGACY_VOLUME_SENSOR_KEYS) == {
        "sensor_drinks_today",
        "sensor_lifetime_total",
    }
    assert today._attr_native_unit_of_measurement == statistics_module.CANONICAL_VOLUME_UNIT
    assert lifetime._attr_native_unit_of_measurement == statistics_module.CANONICAL_VOLUME_UNIT


# --- Verdrahtung / No-op ---------------------------------------------------


def test_migration_is_noop_when_recorder_not_configured(monkeypatch):
    """Recorder nicht eingerichtet → kein API-Aufruf, kein Recorder-Start, kein Fehler."""
    api = _FakeRecorderApi()
    registry = _default_registry()
    _install(monkeypatch, registry, api)
    hass = _make_hass(recorder_ready=False)
    entry = _make_entry()

    result = asyncio.run(statistics_module.async_migrate_legacy_volume_statistics(hass, entry))

    assert result == 0
    assert api.list_calls == []
    assert api.updates == []
    # Der Recorder wird weder gestartet noch initialisiert.
    hass.config.async_setup_component.assert_not_called()
    # F-04: KEIN Start-Event-Listener, KEIN Pending-Container — die Migration
    # wird beim nächsten Setup (HA-Neustart/Entry-Reload) nachgeholt.
    assert hass.bus.async_listen_once.call_count == 0
    assert "health_o_mat" not in hass.data


def test_migration_creates_no_pending_container(monkeypatch):
    """Nach der Migration enthält hass.data[DOMAIN] nur bekannte Schlüssel (F-04).

    Der Pending-Container "statistics_migration" (Start-Retry) ist entfernt —
    hass.data[DOMAIN] kennt nur noch "shared" und die Entry-IDs.
    """
    api = _FakeRecorderApi()
    _install(monkeypatch, _default_registry(), api)
    hass = _make_hass(recorder_ready=False)
    entry = _make_entry()

    asyncio.run(statistics_module.async_migrate_legacy_volume_statistics(hass, entry))

    assert "health_o_mat" not in hass.data
    # Auch im Erfolgsfall (Recorder bereit) entsteht kein Fremd-Key.
    hass2 = _make_hass()
    asyncio.run(statistics_module.async_migrate_legacy_volume_statistics(hass2, entry))
    assert "health_o_mat" not in hass2.data


def test_migration_is_noop_without_recorder_api(monkeypatch):
    """HA-Version ohne Recorder-API → No-op, kein Raise."""
    monkeypatch.setattr(statistics_module, "_load_entity_registry", lambda: _default_registry())
    monkeypatch.setattr(statistics_module, "_load_recorder_api", lambda: None)
    hass = _make_hass()
    entry = _make_entry()

    assert asyncio.run(statistics_module.async_migrate_legacy_volume_statistics(hass, entry)) == 0


def test_migration_is_noop_without_own_entities(monkeypatch):
    """Registry UND Recorder liefern nichts → kein Update, kein Fehler."""
    api = _FakeRecorderApi()
    _install(monkeypatch, _FakeEntityRegistry([]), api)
    hass = _make_hass()
    entry = _make_entry()

    assert asyncio.run(statistics_module.async_migrate_legacy_volume_statistics(hass, entry)) == 0
    assert api.updates == []


def test_migration_ignores_foreign_units(monkeypatch):
    """Nicht-Volume-Einheiten (%/mmHg) werden nicht angefasst."""
    api = _FakeRecorderApi(
        metadata=[
            {"statistic_id": _TODAY_ENTITY, "statistics_unit_of_measurement": "%"},
            {"statistic_id": _LIFETIME_ENTITY, "statistics_unit_of_measurement": "mmHg"},
        ]
    )
    _install(monkeypatch, _default_registry(), api)
    hass = _make_hass()
    entry = _make_entry()

    result = asyncio.run(statistics_module.async_migrate_legacy_volume_statistics(hass, entry))

    assert result == 0
    assert api.updates == []


def test_start_listener_is_unregistered_on_unload(monkeypatch):
    """F-04: Es gibt keinen Start-Listener und keinen Unload-Hook mehr (KISS)."""
    api = _FakeRecorderApi()
    _install(monkeypatch, _default_registry(), api)
    hass = _make_hass(recorder_ready=False)
    entry = _make_entry()

    asyncio.run(statistics_module.async_migrate_legacy_volume_statistics(hass, entry))

    assert hass.bus.async_listen_once.call_count == 0
    assert entry.async_on_unload.call_count == 0


# --- Migration -------------------------------------------------------------


def test_migration_updates_only_own_legacy_statistics(monkeypatch):
    """Nur eigene statistic_ids mit Legacy-Einheit werden auf "mL" gehoben."""
    api = _FakeRecorderApi(
        metadata=[
            {
                "statistic_id": _TODAY_ENTITY,
                "statistics_unit_of_measurement": "ml",
                "unit_class": None,
            },
            {
                "statistic_id": _LIFETIME_ENTITY,
                "statistics_unit_of_measurement": "ml",
                "unit_class": None,
            },
            # Fremde statistic_id (gehört nicht zu unseren Sensoren)
            {"statistic_id": "sensor.someone_else", "statistics_unit_of_measurement": "ml"},
        ]
    )
    _install(monkeypatch, _default_registry(), api)
    hass = _make_hass()
    entry = _make_entry()

    result = asyncio.run(statistics_module.async_migrate_legacy_volume_statistics(hass, entry))

    assert result == 2
    assert api.updates == [
        (_TODAY_ENTITY, {"new_unit_of_measurement": "mL", "new_unit_class": "volume"}),
        (_LIFETIME_ENTITY, {"new_unit_of_measurement": "mL", "new_unit_class": "volume"}),
    ]


def test_migration_leaves_canonical_units_untouched(monkeypatch):
    """Statistiken mit bereits kanonischer Einheit "mL" bleiben unangetastet."""
    api = _FakeRecorderApi(
        metadata=[
            {"statistic_id": _TODAY_ENTITY, "statistics_unit_of_measurement": "mL"},
            {"statistic_id": _LIFETIME_ENTITY, "statistics_unit_of_measurement": "mL"},
        ]
    )
    _install(monkeypatch, _default_registry(), api)
    hass = _make_hass()
    entry = _make_entry()

    result = asyncio.run(statistics_module.async_migrate_legacy_volume_statistics(hass, entry))

    assert result == 0
    assert api.updates == []


def test_migration_accepts_legacy_unit_key(monkeypatch):
    """Ältere Kern-Versionen liefern den Einheiten-Key unter "unit_of_measurement"."""
    api = _FakeRecorderApi(metadata=[{"statistic_id": _TODAY_ENTITY, "unit_of_measurement": "ml"}])
    _install(monkeypatch, _default_registry(), api)
    hass = _make_hass()
    entry = _make_entry()

    result = asyncio.run(statistics_module.async_migrate_legacy_volume_statistics(hass, entry))

    assert result == 1
    assert api.updates == [
        (_TODAY_ENTITY, {"new_unit_of_measurement": "mL", "new_unit_class": "volume"})
    ]


def test_migration_is_idempotent(monkeypatch):
    """Der zweite Lauf findet "mL" vor und schreibt nichts mehr."""
    api = _FakeRecorderApi(
        metadata=[
            {"statistic_id": _TODAY_ENTITY, "statistics_unit_of_measurement": "ml"},
            {"statistic_id": _LIFETIME_ENTITY, "statistics_unit_of_measurement": "ml"},
        ]
    )
    _install(monkeypatch, _default_registry(), api)
    hass = _make_hass()
    entry = _make_entry()

    first = asyncio.run(statistics_module.async_migrate_legacy_volume_statistics(hass, entry))
    second = asyncio.run(statistics_module.async_migrate_legacy_volume_statistics(hass, entry))

    assert first == 2
    assert second == 0
    assert len(api.updates) == 2


def test_migration_swallows_recorder_errors(monkeypatch):
    """Recorder-API-Fehler → Log, kein Raise (Setup darf nicht scheitern)."""
    api = _FakeRecorderApi(list_error=RuntimeError("recorder explodiert"))
    _install(monkeypatch, _default_registry(), api)
    hass = _make_hass()
    entry = _make_entry()

    assert asyncio.run(statistics_module.async_migrate_legacy_volume_statistics(hass, entry)) == 0
    assert api.updates == []


# --- Entity-IDs aus der Registry -------------------------------------------


def test_entity_ids_are_resolved_from_registry_unique_ids(monkeypatch):
    """Entity-IDs kommen aus der Registry (unique_id), nicht aus String-Konstruktion."""
    registry = _FakeEntityRegistry(
        [
            # Absichtlich "unleserliche" IDs — der Slug darf nicht konstruiert werden.
            _FakeRegistryEntry("sensor.a", f"{_ENTRY_ID}_sensor_drinks_today"),
            _FakeRegistryEntry("sensor.b", f"{_ENTRY_ID}_sensor_lifetime_total"),
            # Numbers erzeugen keine Recorder-Statistik → gehören nicht dazu.
            _FakeRegistryEntry("number.c", f"{_ENTRY_ID}_number_daily_goal", platform="number"),
            # Fremder Config-Entry.
            _FakeRegistryEntry("sensor.d", "other_entry_sensor_drinks_today"),
        ]
    )
    api = _FakeRecorderApi()
    _install(monkeypatch, registry, api)
    hass = _make_hass()
    entry = _make_entry()

    asyncio.run(statistics_module.async_migrate_legacy_volume_statistics(hass, entry))

    assert registry.requested_entry_ids == [_ENTRY_ID]
    assert api.list_calls == [{"sensor.a", "sensor.b"}]


# --- Fallback: Registry liefert nichts (Bereich "Getränke" deaktiviert) -----


def test_fallback_migrates_only_our_volume_statistics(monkeypatch):
    """Registry leer → Fallback greift und migriert NUR unsere beiden Volumen-Sensoren.

    Szenario: Der Bereich "Getränke" ist deaktiviert → sensor.py legt keine
    Volumen-Sensoren an → keine Registry-Einträge. Die veraltete
    Metadatenzeile "ml" bliebe sonst stehen. Der Fallback nimmt deshalb einen
    ungefilterten Recorder-Scan her, filtert aber streng auf unsere beiden
    Volumen-Sensoren.
    """
    api = _FakeRecorderApi(
        metadata=[
            # Unsere beiden Volumen-Sensoren (Legacy-Einheit) → MIGRATION
            {
                "statistic_id": _TODAY_ENTITY,
                "statistics_unit_of_measurement": "ml",
                "unit_class": None,
            },
            {
                "statistic_id": _LIFETIME_ENTITY,
                "statistics_unit_of_measurement": "ml",
                "unit_class": None,
            },
            # Eigene Nicht-Volume-Sensoren (%/mg/mmHg/d) → NICHT migrieren
            {
                "statistic_id": "sensor.health_o_mat_max_goal_percent",
                "statistics_unit_of_measurement": "%",
            },
            {
                "statistic_id": "sensor.health_o_mat_max_caffeine_today",
                "statistics_unit_of_measurement": "mg",
            },
            {
                "statistic_id": "sensor.health_o_mat_max_bp_sys",
                "statistics_unit_of_measurement": "mmHg",
            },
            {
                "statistic_id": "sensor.health_o_mat_max_goal_streak",
                "statistics_unit_of_measurement": "d",
            },
            # Fremde Domain / Fremd-Integration → NICHT migrieren
            {
                "statistic_id": "sensor.someone_else_drinks_today",
                "statistics_unit_of_measurement": "ml",
            },
            {
                "statistic_id": "binary_sensor.health_o_mat_max_drinks_today",
                "statistics_unit_of_measurement": "ml",
            },
            # Fremde Integration mit gleichem Namensschema → NICHT migrieren
            {
                "statistic_id": "sensor.other_integration_max_drinks_today",
                "statistics_unit_of_measurement": "ml",
            },
        ]
    )
    _install(monkeypatch, _FakeEntityRegistry([]), api)
    hass = _make_hass()
    entry = _make_entry()

    result = asyncio.run(statistics_module.async_migrate_legacy_volume_statistics(hass, entry))

    assert result == 2
    assert api.updates == [
        (_TODAY_ENTITY, {"new_unit_of_measurement": "mL", "new_unit_class": "volume"}),
        (_LIFETIME_ENTITY, {"new_unit_of_measurement": "mL", "new_unit_class": "volume"}),
    ]
    # Der Fallback ist ein ungefilterter Scan (kein statistic_ids-Filter).
    assert api.list_calls == [None]


def test_fallback_not_used_when_registry_resolves_ids(monkeypatch):
    """Registry liefert IDs → der Fallback (Vollscan) wird NICHT verwendet."""
    api = _FakeRecorderApi(
        metadata=[{"statistic_id": _TODAY_ENTITY, "statistics_unit_of_measurement": "ml"}]
    )
    _install(monkeypatch, _default_registry(), api)
    hass = _make_hass()
    entry = _make_entry()

    asyncio.run(statistics_module.async_migrate_legacy_volume_statistics(hass, entry))

    # Genau ein Aufruf, mit Filter — kein ungefilterter Vollscan.
    assert api.list_calls == [{_TODAY_ENTITY, _LIFETIME_ENTITY}]
    assert None not in api.list_calls


def test_fallback_ignores_foreign_units_even_with_legacy_suffix(monkeypatch):
    """Auch im Fallback wird NUR die Legacy-Einheit "ml" angehoben."""
    api = _FakeRecorderApi(
        metadata=[
            # Bereits kanonisch → keine Aktion
            {"statistic_id": _TODAY_ENTITY, "statistics_unit_of_measurement": "mL"},
            # Fremde Einheit, aber passender Name → keine Aktion
            {
                "statistic_id": "sensor.health_o_mat_max_lifetime_total",
                "statistics_unit_of_measurement": "L",
            },
        ]
    )
    _install(monkeypatch, _FakeEntityRegistry([]), api)
    hass = _make_hass()
    entry = _make_entry()

    result = asyncio.run(statistics_module.async_migrate_legacy_volume_statistics(hass, entry))

    assert result == 0
    assert api.updates == []


# --- Recorder-API-Signatur (Schutz gegen API-Drift des HA-Kerns) ----------


def test_recorder_api_is_called_with_exact_keyword_arguments(monkeypatch):
    """Die Recorder-API wird mit EXAKT diesen Keyword-Argumenten aufgerufen.

    "new_unit_of_measurement" und "new_unit_class" sind in der echten HA-API
    keyword-only. Übergibt das Modul sie positional, schlägt der Aufruf in
    der echten HA fehl (TypeError) — dieser Test sichert die Aufrufsignatur.
    """
    api = _FakeRecorderApi(
        metadata=[{"statistic_id": _TODAY_ENTITY, "statistics_unit_of_measurement": "ml"}]
    )
    _install(monkeypatch, _default_registry(), api)
    hass = _make_hass()
    entry = _make_entry()

    asyncio.run(statistics_module.async_migrate_legacy_volume_statistics(hass, entry))

    assert api.updates == [
        (_TODAY_ENTITY, {"new_unit_of_measurement": "mL", "new_unit_class": "volume"})
    ]
    # Der Aufruf darf NICHT positional erfolgen: die Doublette akzeptiert
    # ausschließlich Keyword-Argumente (**kwargs) für die beiden Parameter.
    statistic_id, kwargs = api.updates[0]
    assert statistic_id == _TODAY_ENTITY
    assert set(kwargs) == {"new_unit_of_measurement", "new_unit_class"}
    assert kwargs["new_unit_of_measurement"] == "mL"
    assert kwargs["new_unit_class"] == "volume"


def test_real_recorder_api_signature_matches_expectation():
    """Die echte HA-Recorder-API hat die erwartete Signatur (kein Signatur-Drift).

    Prüft gegen die installierte HA-Version:
    * async_list_statistic_ids ist ein Coroutine (muss awaited werden).
    * async_update_statistics_metadata ist ein Sync-Callback (darf NICHT
      awaited werden) und nimmt new_unit_of_measurement/new_unit_class als
      keyword-only Parameter entgegen.
    """
    recorder_statistics = pytest.importorskip(
        "homeassistant.components.recorder.statistics",
        reason="HA-Recorder-Komponente nicht installiert",
    )
    list_fn = recorder_statistics.async_list_statistic_ids
    update_fn = recorder_statistics.async_update_statistics_metadata

    assert inspect.iscoroutinefunction(list_fn)
    assert not inspect.iscoroutinefunction(update_fn)

    params = inspect.signature(update_fn).parameters
    assert "new_unit_of_measurement" in params
    assert "new_unit_class" in params
    assert params["new_unit_of_measurement"].kind is inspect.Parameter.KEYWORD_ONLY
    assert params["new_unit_class"].kind is inspect.Parameter.KEYWORD_ONLY

    list_params = inspect.signature(list_fn).parameters
    assert "statistic_ids" in list_params
    assert list_params["statistic_ids"].default is None


# --- Verdrahtung in __init__.py --------------------------------------------


class _FakeCoordinator:
    """DataUpdateCoordinator-Ersatz (nur für den Setup-Aufruf nötig)."""

    def __init__(self, *args, **kwargs) -> None:
        self.data = None

    def async_set_updated_data(self, data) -> None:
        self.data = data


def test_setup_entry_triggers_statistics_migration(monkeypatch):
    """Das Config-Entry-Setup ruft die Statistik-Migration auf."""
    init_module = _load_init()
    calls: list[tuple] = []

    async def _fake_migration(hass, entry):
        calls.append((hass, entry))
        return 0

    monkeypatch.setattr(init_module, "async_migrate_legacy_volume_statistics", _fake_migration)
    monkeypatch.setattr(init_module, "DataUpdateCoordinator", _FakeCoordinator)

    store = AsyncMock()
    hass = MagicMock()
    hass.data = {"health_o_mat": {"shared": {"store": store}}}
    hass.config_entries.async_forward_entry_setups = AsyncMock()
    entry = _make_entry()

    assert asyncio.run(init_module.async_setup_entry(hass, entry)) is True
    assert calls == [(hass, entry)]
    # Die Migration läuft NACH dem Plattform-Setup (Entity-IDs existieren dann).
    assert hass.config_entries.async_forward_entry_setups.await_count == 1


def test_setup_entry_survives_failing_statistics_migration(monkeypatch):
    """Eine fehlschlagende Migration darf das Setup nicht scheitern lassen."""
    init_module = _load_init()

    async def _boom(hass, entry):
        raise RuntimeError("Migration kaputt")

    monkeypatch.setattr(init_module, "async_migrate_legacy_volume_statistics", _boom)
    monkeypatch.setattr(init_module, "DataUpdateCoordinator", _FakeCoordinator)

    store = AsyncMock()
    hass = MagicMock()
    hass.data = {"health_o_mat": {"shared": {"store": store}}}
    hass.config_entries.async_forward_entry_setups = AsyncMock()
    entry = _make_entry()

    assert asyncio.run(init_module.async_setup_entry(hass, entry)) is True


def test_unload_leaves_only_known_entry_registry_keys():
    """Nach dem Unload bleiben nur bekannte Keys in hass.data[DOMAIN] (F-04).

    Der Pending-Container "statistics_migration" existiert nicht mehr — nach
    dem Entladen eines Entries bleibt die Entry-Registry auf die übrigen
    Entry-IDs plus "shared"/"signal" beschränkt.
    """
    init_module = _load_init()
    hass = MagicMock()
    hass.data = {
        "health_o_mat": {
            _ENTRY_ID: {"coordinator": object()},
            "other-entry": {"coordinator": object()},
            "shared": {"store": object()},
        }
    }
    hass.config_entries.async_unload_platforms = AsyncMock(return_value=True)
    entry = _make_entry()

    assert asyncio.run(init_module.async_unload_entry(hass, entry)) is True
    assert "statistics_migration" not in hass.data["health_o_mat"]
    assert set(hass.data["health_o_mat"]) == {"other-entry", "shared"}


def test_entry_registry_has_no_migration_side_container():
    """Die Entry-Registry kennt nur noch "shared" und "signal" als Fremd-Keys."""
    init_module = _load_init()

    assert init_module._NON_ENTRY_KEYS == ("shared", "signal")
    assert "statistics_migration" not in init_module._NON_ENTRY_KEYS


def test_shared_key_does_not_collide_with_entry_registry():
    """Der Shared-Key "shared" wird als Entry-Registry ignoriert."""
    init_module = _load_init()
    hass = MagicMock()
    hass.data = {
        "health_o_mat": {
            _ENTRY_ID: {"coordinator": object()},
            "shared": {"store": object()},
        }
    }

    # Der Shared-Key zählt nicht als Runtime-Entry ...
    assert init_module._has_runtime_entries(hass) is True

    # ... und der Service-Resolver findet weiterhin die Person.
    cfg_entry = MagicMock()
    cfg_entry.entry_id = _ENTRY_ID
    cfg_entry.data = {"person": "Max"}
    hass.config_entries.async_entries = MagicMock(return_value=[cfg_entry])
    call = MagicMock()
    call.data = {"person": "Max"}

    entry_id, info = init_module.get_runtime_data(hass, call)

    assert entry_id == _ENTRY_ID
    assert "coordinator" in info


def test_without_any_entry_no_person_is_resolved():
    """Ohne echten Entry gibt es keine Person (Service-Fehler)."""
    init_module = _load_init()
    hass = MagicMock()
    hass.data = {"health_o_mat": {"shared": {"store": object()}}}
    hass.config_entries.async_entries = MagicMock(return_value=[])

    assert init_module._has_runtime_entries(hass) is False

    call = MagicMock()
    call.data = {}
    with pytest.raises(ServiceValidationError):
        init_module.get_runtime_data(hass, call)

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
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
import voluptuous as vol

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
                "drinks": [
                    {
                        "ts": "2026-09-01T08:00:00",
                        "ml": 250,
                        "type": "Kaffee",
                        "src": "quick_button",
                    }
                ],
                "readings": [
                    {
                        "ts": "2026-09-01T09:00:00",
                        "sys": 120,
                        "dia": 80,
                        "pulse": 60,
                        "note": "",
                        "src": "button",
                    }
                ],
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
    asyncio.get_event_loop().run_until_complete(store.async_load()) if False else _run(
        store.async_load()
    )
    data = store.raw_data()
    assert data["schema"] == SCHEMA
    e1 = data["entries"]["e1"]
    assert e1["inputs"] == {}
    # Bestandsdaten unverändert; v4 ergänzt nur id/created_at/voided_*
    assert [{k: d[k] for k in ("ts", "ml", "type", "src")} for d in e1["drinks"]] == [
        {k: d[k] for k in ("ts", "ml", "type", "src")}
        for d in _v1_fixture()["entries"]["e1"]["drinks"]
    ]


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

    assert store.raw_data() == {"schema": SCHEMA, "entries": {}}
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

    assert store.raw_data() == {"schema": SCHEMA, "entries": {}}
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
        "quick_drinks": [
            {"key": "glas_wasser", "label": "Glas Wasser", "ml": 200, "icon": "mdi:glass-water"}
        ],
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


# ============================================================================
# Welle 1 Backend-Hygiene: N-2 (Retention), N-7 (Service-Undo), N-8 (Lookup)
# ============================================================================

_DOMAIN = const_module.DOMAIN


def _fresh_store():
    """HealthOMatStore mit gemocktem HA-Store-Backend (leerer Start)."""
    store = store_module.HealthOMatStore(MagicMock())
    store._store = MagicMock()
    store._store.async_load = AsyncMock(return_value=None)
    store._store.async_save = AsyncMock(return_value=None)
    _run(store.async_load())
    return store


def _cfg_entry(entry_id: str, person: str, options: dict | None = None) -> MagicMock:
    entry = MagicMock()
    entry.entry_id = entry_id
    entry.data = {"person": person}
    entry.options = options or {}
    return entry


def _call(data: dict | None = None) -> MagicMock:
    call = MagicMock()
    call.data = data or {}
    return call


class _FakeServices:
    """Minimal-Service-Registry zum Einsammeln der registrierten Handler."""

    def __init__(self) -> None:
        self.registered: dict[str, tuple] = {}
        # Vorhandene Fremd-Services (z. B. notify.mobile_app_phone).
        self.known: set[str] = set()
        self.async_call = AsyncMock()

    def has_service(self, domain, name) -> bool:
        return name in self.registered or f"{domain}.{name}" in self.known

    def async_register(self, domain, name, *, schema=None, service_func=None) -> None:
        self.registered[name] = (schema, service_func)


def _runtime_hass(entries, *, store=None, archive_store=None) -> MagicMock:
    domain_data: dict = {"shared": {}}
    if store is not None:
        domain_data["shared"]["store"] = store
    if archive_store is not None:
        domain_data["shared"]["archive_store"] = archive_store
    for e in entries:
        domain_data[e.entry_id] = {"coordinator": MagicMock()}
    hass = MagicMock()
    hass.data = {_DOMAIN: domain_data}
    hass.services = _FakeServices()
    hass.config_entries.async_entries = MagicMock(return_value=list(entries))
    return hass


# --- N-8: get_runtime_data (Entry-Lookup, O(n) statt O(n²)) ---


def test_get_runtime_data_single_person_without_person_arg():
    """[N-8] Eine Person ohne 'person'-Argument → genau dieser Entry."""
    init = _load_init()
    hass = _runtime_hass([_cfg_entry("e1", "Max")])

    key, _info = init.get_runtime_data(hass, _call())

    assert key == "e1"


def test_get_runtime_data_no_entries_raises():
    """[N-8] Keine laufende Person → ServiceValidationError."""
    init = _load_init()
    hass = _runtime_hass([])

    with pytest.raises(init.ServiceValidationError):
        init.get_runtime_data(hass, _call())


def test_get_runtime_data_multiple_without_person_lists_names():
    """[N-8] Mehrere Personen ohne Auswahl → Fehler mit Namensliste."""
    init = _load_init()
    hass = _runtime_hass([_cfg_entry("e1", "Max"), _cfg_entry("e2", "Caro")])

    with pytest.raises(init.ServiceValidationError) as exc:
        init.get_runtime_data(hass, _call())

    message = str(exc.value)
    assert "max" in message and "caro" in message


def test_get_runtime_data_matches_case_insensitively():
    """[N-8] Person-Matching über entry.data['person'] ist case-insensitiv."""
    init = _load_init()
    hass = _runtime_hass([_cfg_entry("e1", "Max"), _cfg_entry("e2", "Caro")])

    key, _info = init.get_runtime_data(hass, _call({"person": "CARO"}))

    assert key == "e2"


def test_get_runtime_data_unknown_person_raises():
    """[N-8] Unbekannter Name → ServiceValidationError."""
    init = _load_init()
    hass = _runtime_hass([_cfg_entry("e1", "Max")])

    with pytest.raises(init.ServiceValidationError):
        init.get_runtime_data(hass, _call({"person": "Niemand"}))


def test_get_runtime_data_indexes_config_entries_once():
    """[N-8] O(n²)-Fix: Config-Entries werden genau EINMAL indexiert."""
    init = _load_init()
    entries = [_cfg_entry(f"e{i}", f"P{i}") for i in range(4)]
    hass = _runtime_hass(entries)

    init.get_runtime_data(hass, _call({"person": "P3"}))

    hass.config_entries.async_entries.assert_called_once()


# --- N-7: remove_last_entry wertet 'kind' aus ---


def _registered_remove_last_entry(hass):
    init = _load_init()
    init._register_services(hass)
    return init, hass.services.registered["remove_last_entry"]


def test_remove_last_entry_default_kind_removes_drink():
    """[N-7] Ohne 'kind' wird wie bisher der letzte Drink entfernt."""
    store = _fresh_store()
    _run(store.add_drink("e1", "2026-09-05T10:00:00Z", 500, "Wasser", "service"))
    hass = _runtime_hass([_cfg_entry("e1", "Max")], store=store)
    init, (schema, func) = _registered_remove_last_entry(hass)

    validated = schema({})
    assert validated["kind"] == "drinks"

    _run(func(_call({"kind": validated["kind"]})))
    # M2b: Undo voidet (kein Pop) — die Rohliste behält den Eintrag.
    assert store.active_drinks("e1") == []
    assert len(store.entry("e1")["drinks"]) == 1
    assert store.entry("e1")["drinks"][0]["voided_at"] is not None
    assert store.entry("e1")["total_ml_lifetime"] == 0


def test_remove_last_entry_kind_blood_pressure_removes_reading():
    """[N-7] kind=blood_pressure entfernt die letzte BP-Messung."""
    store = _fresh_store()
    _run(store.add_reading("e1", "2026-09-05T10:00:00Z", 120, 80, 70))
    _run(store.add_reading("e1", "2026-09-05T11:00:00Z", 130, 85, 75))
    hass = _runtime_hass([_cfg_entry("e1", "Max")], store=store)
    init, (_schema, func) = _registered_remove_last_entry(hass)

    _run(func(_call({"kind": "blood_pressure"})))

    readings = store.entry("e1")["readings"]
    assert len(readings) == 2, "der voided Eintrag bleibt in der Rohliste"
    assert [r["sys"] for r in store.active_readings("e1")] == [120]


def test_remove_last_entry_blood_pressure_empty_raises():
    """[N-7] Leerer BP-Bestand → ServiceValidationError mit passendem Text."""
    store = _fresh_store()
    hass = _runtime_hass([_cfg_entry("e1", "Max")], store=store)
    init, (_schema, func) = _registered_remove_last_entry(hass)

    with pytest.raises(init.ServiceValidationError) as exc:
        _run(func(_call({"kind": "blood_pressure"})))

    assert "Blutdruck" in str(exc.value)


def test_remove_last_entry_drinks_empty_raises():
    """[N-7] Leerer Drink-Bestand → ServiceValidationError mit passendem Text."""
    store = _fresh_store()
    hass = _runtime_hass([_cfg_entry("e1", "Max")], store=store)
    init, (_schema, func) = _registered_remove_last_entry(hass)

    with pytest.raises(init.ServiceValidationError) as exc:
        _run(func(_call({"kind": "drinks"})))

    assert "Getränke" in str(exc.value)


def test_remove_last_entry_schema_rejects_unknown_kind():
    """[N-7] Unbekanntes 'kind' wird bereits vom Schema abgelehnt."""
    store = _fresh_store()
    hass = _runtime_hass([_cfg_entry("e1", "Max")], store=store)
    _init, (schema, _func) = _registered_remove_last_entry(hass)

    with pytest.raises(vol.Invalid):
        schema({"kind": "blood"})


# --- N-2: Retention-Wiring im Setup + CSV-Export inkl. Archiv ---


def test_apply_retention_default_off_is_noop():
    """[N-2] Default AUS (kein/0 Monatswert): nichts wird verschoben."""
    init = _load_init()
    store = _fresh_store()
    entry_data = store.entry("e1")
    entry_data["drinks"] = [
        {"ts": "2020-01-01T00:00:00", "ml": 250, "type": "Kaffee", "src": "button"},
        {"ts": "2026-09-30T10:00:00", "ml": 500, "type": "Wasser", "src": "button"},
    ]
    entry_data["total_ml_lifetime"] = 750
    archive = _fresh_store()
    entry = _cfg_entry("e1", "Max", {})  # kein retention_months → 0/AUS
    hass = _runtime_hass([entry], store=store, archive_store=archive)

    _run(init._apply_retention(hass, entry, store))

    assert len(store.entry("e1")["drinks"]) == 2
    assert store.entry("e1")["total_ml_lifetime"] == 750
    assert archive.all_entries().get("e1", {}) == {}


def test_apply_retention_active_moves_old_and_keeps_lifetime(monkeypatch):
    """[N-2] Aktiv: alte Einträge ins Archiv, Summen unverändert."""
    init = _load_init()
    monkeypatch.setattr(
        init, "dt_util", types.SimpleNamespace(now=lambda: datetime(2026, 10, 14, 12, 0))
    )
    store = _fresh_store()
    old_drink = {"ts": "2025-12-31T10:00:00", "ml": 250, "type": "Kaffee", "src": "button"}
    recent_drink = {"ts": "2026-09-30T10:00:00", "ml": 500, "type": "Wasser", "src": "button"}
    old_reading = {
        "ts": "2025-06-01T08:00:00",
        "sys": 120,
        "dia": 80,
        "pulse": 70,
        "note": "",
        "src": "button",
    }
    e = store.entry("e1")
    e["drinks"] = [old_drink, recent_drink]
    e["readings"] = [old_reading]
    e["total_ml_lifetime"] = 750
    archive = _fresh_store()
    entry = _cfg_entry("e1", "Max", {"retention_months": 6})  # Stichtag 2026-04-14
    hass = _runtime_hass([entry], store=store, archive_store=archive)

    _run(init._apply_retention(hass, entry, store))

    main = store.entry("e1")
    assert main["drinks"] == [recent_drink]
    assert main["readings"] == []
    assert main["total_ml_lifetime"] == 750  # Summe unverändert
    assert main["archived_counts"] == {"drinks": 1, "readings": 1}
    archived = archive.all_entries()["e1"]
    assert archived["drinks"] == [old_drink]
    assert archived["readings"] == [old_reading]


def test_retention_months_reads_options_or_zero():
    """[N-2] Ungültige/fehlende Retention → 0 (AUS), kein Absturz."""
    init = _load_init()
    assert init._retention_months(_cfg_entry("e1", "Max")) == 0
    assert init._retention_months(_cfg_entry("e1", "Max", {"retention_months": 12})) == 12
    assert init._retention_months(_cfg_entry("e1", "Max", {"retention_months": "x"})) == 0


def test_export_csv_includes_archived_entries(tmp_path):
    """[N-2] CSV-Export führt Haupt-Store und Archiv zusammen."""
    _load_init()  # stellt _PKG.logic/_PKG.store bereit
    exporter = _load("exporter")
    store = _fresh_store()
    _run(store.set_person("e1", "Max"))
    _run(store.add_drink("e1", "2026-09-30T10:00:00", 500, "Wasser", "button"))
    archive = _fresh_store()
    _run(
        archive.append_archive(
            "e1",
            [{"ts": "2025-12-31T10:00:00", "ml": 250, "type": "Kaffee", "src": "button"}],
            [],
        )
    )

    hass = MagicMock()
    hass.config.path = MagicMock(return_value=str(tmp_path))
    hass.async_add_executor_job = AsyncMock(side_effect=lambda fn: fn())
    hass.services.async_call = AsyncMock()
    exporter.dt_util = types.SimpleNamespace(now=lambda: datetime(2026, 10, 14, 12, 0))

    _run(
        exporter.async_export_csv(hass, store, _call({"dataset": "drinks"}), archive_store=archive)
    )

    files = list(tmp_path.glob("*.csv"))
    assert len(files) == 1
    content = files[0].read_text(encoding="utf-8-sig")
    assert "Kaffee" in content  # aus dem Archiv
    assert "Wasser" in content  # aus dem Haupt-Store


# --- set_wellbeing-Service (PLAN-CARD-CONFIG §4.2) ---------------------------


def test_set_wellbeing_service_registered_with_schema():
    """Der Service akzeptiert `status` ODER `score`; `person` ist optional."""
    init = _load_init()
    hass = _runtime_hass([_cfg_entry("e1", "Max")])

    init._register_services(hass)

    schema, _func = hass.services.registered["set_wellbeing"]
    assert schema({"status": "good"}) == {"status": "good"}
    assert schema({"person": "Max", "status": "great"})["person"] == "Max"
    assert schema({"score": 7}) == {"score": 7}
    # Die Pflichtprüfung (status/score) passiert im Handler, nicht im Schema.
    assert schema({}) == {}


def test_register_services_registers_missing_service_despite_add_drink():
    """Ein bereits vorhandenes add_drink blockiert spätere Services nicht."""
    init = _load_init()
    hass = _runtime_hass([_cfg_entry("e1", "Max")])
    hass.services.registered["add_drink"] = (vol.Schema({}), MagicMock())

    init._register_services(hass)

    assert set(hass.services.registered) == set(init._SERVICE_NAMES)


def test_register_services_is_idempotent():
    """Zweifacher Setup-Lauf registriert keinen Service doppelt."""
    init = _load_init()
    hass = _runtime_hass([_cfg_entry("e1", "Max")])

    init._register_services(hass)
    first = set(hass.services.registered)
    init._register_services(hass)

    assert set(hass.services.registered) == first == set(init._SERVICE_NAMES)


def test_set_wellbeing_service_persists_and_refreshes(monkeypatch):
    """Gültiger Status → Store-Schreibzugriff + signal_refresh am Coordinator."""
    init = _load_init()
    monkeypatch.setattr(
        init, "dt_util", types.SimpleNamespace(now=lambda: datetime(2026, 10, 15, 12, 0))
    )
    store = _fresh_store()
    hass = _runtime_hass([_cfg_entry("e1", "Max")], store=store)
    init._register_services(hass)
    _schema, func = hass.services.registered["set_wellbeing"]

    _run(func(_call({"status": "good"})))

    assert store.entry("e1")["wellbeing"] == {"status": "good", "ts": "2026-10-15T12:00:00"}
    hass.data[_DOMAIN]["e1"]["coordinator"].async_set_updated_data.assert_called_once()


def test_set_wellbeing_service_accepts_numeric_score(monkeypatch):
    """Numerischer Score 1..10 wird auf den kanonischen Key abgebildet."""
    init = _load_init()
    monkeypatch.setattr(
        init, "dt_util", types.SimpleNamespace(now=lambda: datetime(2026, 10, 15, 12, 0))
    )
    store = _fresh_store()
    hass = _runtime_hass([_cfg_entry("e1", "Max")], store=store)
    init._register_services(hass)
    _schema, func = hass.services.registered["set_wellbeing"]

    _run(func(_call({"score": 7})))

    assert store.entry("e1")["wellbeing"] == {"status": "good", "ts": "2026-10-15T12:00:00"}


@pytest.mark.parametrize("status", ["bogus", "", None, 5])
def test_set_wellbeing_service_rejects_unknown_status(status):
    """[Card-Config] Unbekannter Status wird abgelehnt — auf beiden Ebenen.

    Zwei getrennte Verteidigungslinien, beide hier belegt:

    * Das registrierte voluptuous-Schema weist Nicht-Strings (`None`, `5`)
      bereits vor dem Handler ab (`vol.Invalid`).
    * Der Handler selbst weist unbekannte/leere STRINGS ab
      (`ServiceValidationError`) — er wird hier direkt aufgerufen, also ohne
      das vorgelagerte Schema.

    In keinem Fall wird geschrieben.
    """
    init = _load_init()
    store = _fresh_store()
    hass = _runtime_hass([_cfg_entry("e1", "Max")], store=store)
    init._register_services(hass)
    schema, func = hass.services.registered["set_wellbeing"]

    if not isinstance(status, str):
        # Schema-Ebene: der Wert erreicht den Handler nie.
        with pytest.raises(vol.Invalid):
            schema({"status": status})
        assert "wellbeing" not in store.entry("e1")
        return

    # Handler-Ebene (Schema bewusst umgangen).
    with pytest.raises(init.ServiceValidationError) as exc:
        _run(func(_call({"status": status})))

    message = str(exc.value)
    for key in ("very_bad", "bad", "okay", "good", "great"):
        assert key in message
    assert "wellbeing" not in store.entry("e1")


def test_set_wellbeing_service_resolves_person(monkeypatch):
    """`person` wählt wie bei den übrigen Services den richtigen Entry."""
    init = _load_init()
    monkeypatch.setattr(
        init, "dt_util", types.SimpleNamespace(now=lambda: datetime(2026, 10, 15, 12, 0))
    )
    store = _fresh_store()
    hass = _runtime_hass([_cfg_entry("e1", "Max"), _cfg_entry("e2", "Caro")], store=store)
    init._register_services(hass)
    _schema, func = hass.services.registered["set_wellbeing"]

    _run(func(_call({"person": "caro", "status": "great"})))

    assert store.entry("e2")["wellbeing"]["status"] == "great"
    assert "wellbeing" not in store.entry("e1")


def test_set_wellbeing_service_multiple_persons_without_selection_raises():
    """Ohne `person` bei mehreren Entries: gleiche Fehlersemantik wie überall."""
    init = _load_init()
    store = _fresh_store()
    hass = _runtime_hass([_cfg_entry("e1", "Max"), _cfg_entry("e2", "Caro")], store=store)
    init._register_services(hass)
    _schema, func = hass.services.registered["set_wellbeing"]

    with pytest.raises(init.ServiceValidationError) as exc:
        _run(func(_call({"status": "good"})))

    assert "Mehrere Personen" in str(exc.value)
    assert "wellbeing" not in store.entry("e1")


# --- M2a: Retention lässt voided Einträge im Haupt-Store ---------------------


def test_apply_retention_keeps_voided_entries_in_main_store(monkeypatch):
    """[M2a] Nur aktive Einträge wandern ins Archiv; voided bleibt im Haupt-Store."""
    init = _load_init()
    monkeypatch.setattr(
        init, "dt_util", types.SimpleNamespace(now=lambda: datetime(2026, 10, 14, 12, 0))
    )
    store = _fresh_store()
    old_active = {"ts": "2025-12-31T10:00:00", "ml": 250, "type": "Kaffee", "src": "button"}
    old_voided = {
        "ts": "2025-01-01T10:00:00",
        "ml": 400,
        "type": "Wasser",
        "src": "button",
        "voided_at": "2025-02-01T00:00:00",
    }
    recent = {"ts": "2026-09-30T10:00:00", "ml": 500, "type": "Wasser", "src": "button"}
    voided_reading = {
        "ts": "2025-03-01T08:00:00",
        "sys": 120,
        "dia": 80,
        "pulse": 70,
        "note": "",
        "src": "button",
        "voided_at": "2025-04-01T00:00:00",
    }
    e = store.entry("e1")
    e["drinks"] = [old_active, old_voided, recent]
    e["readings"] = [voided_reading]
    e["total_ml_lifetime"] = 750
    archive = _fresh_store()
    entry = _cfg_entry("e1", "Max", {"retention_months": 6})  # Stichtag 2026-04-14
    hass = _runtime_hass([entry], store=store, archive_store=archive)

    _run(init._apply_retention(hass, entry, store))

    main = store.entry("e1")
    # Reihenfolge des Rohbestands bleibt erhalten, voided wurde nicht verschoben.
    assert main["drinks"] == [old_voided, recent]
    assert main["readings"] == [voided_reading]
    assert main["total_ml_lifetime"] == 750  # Summe unverändert
    assert main["archived_counts"] == {"drinks": 1, "readings": 0}
    archived = archive.all_entries()["e1"]
    assert archived["drinks"] == [old_active]
    assert archived["readings"] == []


def test_apply_retention_with_only_voided_entries_is_noop(monkeypatch):
    """[M2a] Ausschließlich voided (alt) → nichts wird archiviert."""
    init = _load_init()
    monkeypatch.setattr(
        init, "dt_util", types.SimpleNamespace(now=lambda: datetime(2026, 10, 14, 12, 0))
    )
    store = _fresh_store()
    voided = {
        "ts": "2025-01-01T10:00:00",
        "ml": 400,
        "type": "Wasser",
        "src": "button",
        "voided_at": "2025-02-01T00:00:00",
    }
    e = store.entry("e1")
    e["drinks"] = [voided]
    e["total_ml_lifetime"] = 0
    entry = _cfg_entry("e1", "Max", {"retention_months": 6})
    hass = _runtime_hass([entry], store=store)

    _run(init._apply_retention(hass, entry, store))

    assert store.entry("e1")["drinks"] == [voided]
    assert store.entry("e1")["archived_counts"] == {"drinks": 0, "readings": 0}
    # Kein Archiv-Store angelegt (kein Verschieben nötig).
    assert "archive_store" not in hass.data[_DOMAIN]["shared"]


# --- M2b: Void/Restore-Services + Undo-Semantik -----------------------------


def _registered_service(hass, name):
    init = _load_init()
    init._register_services(hass)
    return init, hass.services.registered[name]


def test_remove_last_entry_kind_wellbeing_voids_last_report():
    """[M2b] remove_last_entry unterstützt kind=wellbeing (Void, kein Pop)."""
    store = _fresh_store()
    _run(store.set_wellbeing("e1", "good", "2026-10-14T08:00:00"))
    _run(store.set_wellbeing("e1", "bad", "2026-10-14T09:00:00"))
    hass = _runtime_hass([_cfg_entry("e1", "Max")], store=store)
    init, (_schema, func) = _registered_service(hass, "remove_last_entry")

    _run(func(_call({"kind": "wellbeing"})))

    entry = store.entry("e1")
    assert len(entry["wellbeing_entries"]) == 2, "kein Hard-Delete"
    assert entry["wellbeing_entries"][-1]["voided_at"] is not None
    assert store.current_wellbeing("e1")["key"] == "good"

    # Zweites Undo voidet die verbleibende aktive Meldung …
    _run(func(_call({"kind": "wellbeing"})))
    assert store.current_wellbeing("e1") is None
    # … danach gibt es nichts mehr zu entfernen.
    with pytest.raises(init.ServiceValidationError) as exc:
        _run(func(_call({"kind": "wellbeing"})))
    assert "Wohlbefinden" in str(exc.value)


def test_remove_last_entry_schema_accepts_wellbeing():
    """[M2b] Das Service-Schema kennt das dritte Ziel."""
    store = _fresh_store()
    hass = _runtime_hass([_cfg_entry("e1", "Max")], store=store)
    _init, (schema, _func) = _registered_service(hass, "remove_last_entry")

    assert schema({"kind": "wellbeing"})["kind"] == "wellbeing"


def test_void_entry_service_marks_entry_deleted_and_audits():
    """[M2b] health_o_mat.void_entry voidet per ID und schreibt Audit."""
    store = _fresh_store()
    _run(store.add_drink("e1", "2026-10-14T08:00:00", 250, "Wasser", "service"))
    drink_id = store.entry("e1")["drinks"][0]["id"]
    hass = _runtime_hass([_cfg_entry("e1", "Max")], store=store)
    init, (_schema, func) = _registered_service(hass, "void_entry")

    _run(func(_call({"kind": "drinks", "id": drink_id})))

    assert store.active_drinks("e1") == []
    assert store.entry("e1")["total_ml_lifetime"] == 0
    assert any(
        event["action"] == "entry_voided" and event["target_id"] == drink_id
        for event in store.entry("e1")["audit_log"]
    )


def test_void_entry_service_unknown_id_raises():
    """[M2b] Unbekannte ID → ServiceValidationError (kein stiller Erfolg)."""
    store = _fresh_store()
    hass = _runtime_hass([_cfg_entry("e1", "Max")], store=store)
    init, (_schema, func) = _registered_service(hass, "void_entry")

    with pytest.raises(init.ServiceValidationError) as exc:
        _run(func(_call({"kind": "drinks", "id": "nope"})))

    assert "nicht gefunden" in str(exc.value)


def test_void_entry_service_schema_requires_kind_and_id():
    """[M2b] kind und id sind Pflichtfelder des Service-Schemas."""
    store = _fresh_store()
    hass = _runtime_hass([_cfg_entry("e1", "Max")], store=store)
    _init, (schema, _func) = _registered_service(hass, "void_entry")

    with pytest.raises(vol.Invalid):
        schema({})
    with pytest.raises(vol.Invalid):
        schema({"kind": "tea", "id": "x"})
    validated = schema({"kind": "wellbeing", "id": "w1"})
    assert validated == {"kind": "wellbeing", "id": "w1"}


def test_restore_entry_service_restores_voided_entry():
    """[M2b] health_o_mat.restore_entry hebt die Löschmarkierung auf."""
    store = _fresh_store()
    _run(store.add_drink("e1", "2026-10-14T08:00:00", 250, "Wasser", "service"))
    drink_id = store.entry("e1")["drinks"][0]["id"]
    _run(store.void_drink("e1", drink_id))
    assert store.entry("e1")["total_ml_lifetime"] == 0
    hass = _runtime_hass([_cfg_entry("e1", "Max")], store=store)
    init, (_schema, func) = _registered_service(hass, "restore_entry")

    _run(func(_call({"kind": "drinks", "id": drink_id})))

    assert [d["id"] for d in store.active_drinks("e1")] == [drink_id]
    assert store.entry("e1")["total_ml_lifetime"] == 250
    assert any(
        event["action"] == "entry_restored" and event["target_id"] == drink_id
        for event in store.entry("e1")["audit_log"]
    )

    with pytest.raises(init.ServiceValidationError) as exc:
        _run(func(_call({"kind": "drinks", "id": drink_id})))
    assert "nicht gelöscht" in str(exc.value)


def test_service_registration_includes_void_and_restore():
    """[M2b] Beide neuen Services werden idempotent registriert."""
    store = _fresh_store()
    hass = _runtime_hass([_cfg_entry("e1", "Max")], store=store)
    init = _load_init()
    init._register_services(hass)
    init._register_services(hass)

    assert {"void_entry", "restore_entry"}.issubset(hass.services.registered)


# --- restore_backup-Service (M2c) -------------------------------------------


def test_restore_backup_service_registered_with_schema():
    """[M2c] restore_backup ist registriert; Defaults und Pflichtfelder stimmen."""
    init = _load_init()
    hass = _runtime_hass([_cfg_entry("e1", "Max")])

    init._register_services(hass)

    schema, _func = hass.services.registered["restore_backup"]
    validated = schema({"filename": "backup.json"})
    assert validated["mode"] == "merge"
    assert validated["dry_run"] is False
    assert validated["restore_audit"] is False
    with pytest.raises(vol.Invalid):
        schema({})
    with pytest.raises(vol.Invalid):
        schema({"filename": "backup.json", "mode": "bogus"})


def test_restore_backup_service_rejects_non_admin():
    """[M2c] Nicht-Admin → ServiceValidationError, kein Restore."""
    init = _load_init()
    hass = _runtime_hass([_cfg_entry("e1", "Max")], store=_fresh_store())
    hass.auth = MagicMock()
    hass.auth.async_get_user = AsyncMock(return_value=types.SimpleNamespace(is_admin=False))
    init._register_services(hass)
    _schema, func = hass.services.registered["restore_backup"]
    call = MagicMock()
    call.data = {"filename": "backup.json"}
    call.context.user_id = "user-1"

    with pytest.raises(init.ServiceValidationError) as exc:
        _run(func(call))

    assert "Administratoren" in str(exc.value)


def test_restore_backup_service_without_user_is_trusted(tmp_path, monkeypatch):
    """[M2c] Ohne User-ID (Automation) läuft der Restore-Pfad weiter."""
    init = _load_init()
    restore = _import_restore_module()
    called = AsyncMock(return_value={"ok": True})
    monkeypatch.setattr(restore, "async_restore_command", called)
    hass = _runtime_hass([_cfg_entry("e1", "Max")], store=_fresh_store())
    hass.config.config_dir = str(tmp_path)
    init._register_services(hass)
    _schema, func = hass.services.registered["restore_backup"]
    call = MagicMock()
    call.data = {"filename": "backup.json", "dry_run": True}
    call.context.user_id = None

    _run(func(call))

    called.assert_awaited_once()
    assert called.await_args.args[1] == {"filename": "backup.json", "dry_run": True}
    assert called.await_args.kwargs["actor"] is None


def _import_restore_module():
    """Lazy-Modul des Service-Handlers (``__init__`` ist als ``<pkg>.init`` geladen)."""
    return importlib.import_module(f"{_PKG}.init.restore")


# --- REQ-HOM-120: Rückdatierung über die Services ---------------------------


def _services_hass(monkeypatch, now: datetime = datetime(2026, 10, 15, 12, 0)):
    init = _load_init()
    monkeypatch.setattr(init, "dt_util", types.SimpleNamespace(now=lambda: now))
    store = _fresh_store()
    hass = _runtime_hass([_cfg_entry("e1", "Max")], store=store)
    init._register_services(hass)
    return init, store, hass


def test_req_hom_120_add_drink_service_accepts_ts(monkeypatch):
    """[REQ-HOM-120] `add_drink` speichert `ts` und `created_at` getrennt."""
    init, store, hass = _services_hass(monkeypatch)
    schema, func = hass.services.registered["add_drink"]

    assert schema({"amount_ml": 250, "ts": "2026-10-15T09:30:00"})["ts"] == ("2026-10-15T09:30:00")
    _run(func(_call({"amount_ml": 250, "ts": "2026-10-15T09:30:00"})))

    drink = store.entry("e1")["drinks"][0]
    assert drink["ts"].startswith("2026-10-15T09:30:00")
    assert drink["created_at"] == "2026-10-15T12:00:00"


def test_req_hom_120_add_blood_pressure_service_accepts_ts(monkeypatch):
    """[REQ-HOM-120] `add_blood_pressure` speichert `ts` und `created_at` getrennt."""
    init, store, hass = _services_hass(monkeypatch)
    _schema, func = hass.services.registered["add_blood_pressure"]

    _run(
        func(
            _call(
                {
                    "systolic": 124,
                    "diastolic": 82,
                    "ts": "2026-10-15T07:15:00",
                }
            )
        )
    )

    reading = store.entry("e1")["readings"][0]
    assert reading["ts"].startswith("2026-10-15T07:15:00")
    assert reading["created_at"] == "2026-10-15T12:00:00"


def test_req_hom_120_set_wellbeing_service_accepts_ts(monkeypatch):
    """[REQ-HOM-120] `set_wellbeing` speichert `ts` und `created_at` getrennt."""
    init, store, hass = _services_hass(monkeypatch)
    _schema, func = hass.services.registered["set_wellbeing"]

    _run(func(_call({"status": "good", "ts": "2026-10-14T20:00:00"})))

    entry = store.entry("e1")
    assert entry["wellbeing"] == {
        "status": "good",
        "ts": entry["wellbeing_entries"][0]["ts"],
    }
    assert entry["wellbeing_entries"][0]["ts"].startswith("2026-10-14T20:00:00")
    assert entry["wellbeing_entries"][0]["created_at"] == "2026-10-15T12:00:00"


@pytest.mark.parametrize(
    "ts",
    [
        "kaputt",
        "2026-10-15T13:00:00",  # mehr als 5 Minuten in der Zukunft
        "1899-12-31T23:59:59",  # vor 1900
    ],
)
@pytest.mark.parametrize("service", ["add_drink", "add_blood_pressure", "set_wellbeing"])
def test_req_hom_120_services_reject_invalid_ts(monkeypatch, service, ts):
    """[REQ-HOM-120] Ungültige/zukünftige/zu alte Zeitpunkte → ServiceValidationError."""
    init, store, hass = _services_hass(monkeypatch)
    _schema, func = hass.services.registered[service]
    payloads = {
        "add_drink": {"amount_ml": 250},
        "add_blood_pressure": {"systolic": 120, "diastolic": 80},
        "set_wellbeing": {"status": "good"},
    }

    with pytest.raises(init.ServiceValidationError) as exc:
        _run(func(_call({**payloads[service], "ts": ts})))

    assert "Zeitpunkt" in str(exc.value)
    entry = store.entry("e1")
    assert entry["drinks"] == []
    assert entry["readings"] == []
    assert entry.get("wellbeing_entries", []) == []


def test_req_hom_120_service_ts_without_value_keeps_now(monkeypatch):
    """[REQ-HOM-120] Ohne `ts` bleibt das bisherige Verhalten (jetzt) erhalten."""
    init, store, hass = _services_hass(monkeypatch)
    _schema, func = hass.services.registered["add_drink"]

    _run(func(_call({"amount_ml": 250})))

    drink = store.entry("e1")["drinks"][0]
    assert drink["ts"] == "2026-10-15T12:00:00"
    assert drink["created_at"] == "2026-10-15T12:00:00"


# --- M3d: Wochenbericht-Service (REQ-HOM-118) -------------------------------


def test_weekly_report_service_registered_with_schema():
    """`weekly_report` ist registriert; `person` ist optional."""
    init = _load_init()
    hass = _runtime_hass([_cfg_entry("e1", "Max")])

    init._register_services(hass)

    schema, _func = hass.services.registered["weekly_report"]
    assert schema({}) == {}
    assert schema({"person": "Max"}) == {"person": "Max"}
    assert "weekly_report" in init._SERVICE_NAMES


def _seed_week(store) -> None:
    """Kleine Woche für den Bericht (heute = 2026-10-26)."""
    for ts, ml, drink_type in (
        ("2026-10-26T09:00:00", 500, "Wasser"),
        ("2026-10-25T09:00:00", 500, "Wasser"),
        ("2026-10-24T09:00:00", 250, "Kaffee"),
    ):
        store.entry("e1")["drinks"].append({"ts": ts, "ml": ml, "type": drink_type})


def test_weekly_report_service_sends_one_notification_per_person(monkeypatch):
    """Ohne `person`: je laufender Person genau eine Markdown-Notification."""
    init = _load_init()
    monkeypatch.setattr(
        init, "dt_util", types.SimpleNamespace(now=lambda: datetime(2026, 10, 26, 18, 0))
    )
    store = _fresh_store()
    _seed_week(store)
    hass = _runtime_hass([_cfg_entry("e1", "Max"), _cfg_entry("e2", "Caro")], store=store)
    hass.config.language = "de"
    init._register_services(hass)
    _schema, func = hass.services.registered["weekly_report"]

    _run(func(_call({})))

    assert hass.services.async_call.await_count == 2
    calls = [call.args for call in hass.services.async_call.await_args_list]
    assert [args[0] for args in calls] == ["persistent_notification", "persistent_notification"]
    titles = [args[2]["title"] for args in calls]
    assert titles == ["Wochenbericht — Max", "Wochenbericht — Caro"]
    assert "## Wochenbericht" in calls[0][2]["message"]
    assert "1250 ml" in calls[0][2]["message"]


def test_weekly_report_service_filters_person(monkeypatch):
    """`person` wählt genau eine Person (Case-insensitive, wie alle Services)."""
    init = _load_init()
    monkeypatch.setattr(
        init, "dt_util", types.SimpleNamespace(now=lambda: datetime(2026, 10, 26, 18, 0))
    )
    store = _fresh_store()
    _seed_week(store)
    hass = _runtime_hass([_cfg_entry("e1", "Max"), _cfg_entry("e2", "Caro")], store=store)
    hass.config.language = "en"
    init._register_services(hass)
    _schema, func = hass.services.registered["weekly_report"]

    _run(func(_call({"person": "caro"})))

    assert hass.services.async_call.await_count == 1
    args = hass.services.async_call.await_args.args
    assert args[2]["title"] == "Weekly report — Caro"
    assert "## Weekly report" in args[2]["message"]


def test_weekly_report_service_uses_configured_notify_service(monkeypatch):
    """Konfigurierter Notify-Service wird genutzt (kein persistent-Fallback)."""
    init = _load_init()
    monkeypatch.setattr(
        init, "dt_util", types.SimpleNamespace(now=lambda: datetime(2026, 10, 26, 18, 0))
    )
    store = _fresh_store()
    _seed_week(store)
    options = {"weekly_report": {"enabled": False, "notify_service": "mobile_app_phone"}}
    hass = _runtime_hass([_cfg_entry("e1", "Max", options)], store=store)
    hass.services.known.add("notify.mobile_app_phone")
    init._register_services(hass)
    _schema, func = hass.services.registered["weekly_report"]

    _run(func(_call({})))

    args = hass.services.async_call.await_args.args
    assert args[:2] == ("notify", "mobile_app_phone")


def test_weekly_report_service_unknown_person_raises():
    """Unbekannte Person → ServiceValidationError, keine Notification."""
    init = _load_init()
    store = _fresh_store()
    hass = _runtime_hass([_cfg_entry("e1", "Max")], store=store)
    init._register_services(hass)
    _schema, func = hass.services.registered["weekly_report"]

    with pytest.raises(init.ServiceValidationError):
        _run(func(_call({"person": "Niemand"})))

    hass.services.async_call.assert_not_awaited()


def test_weekly_report_service_without_runtime_entries_raises():
    """Keine laufende Person → ServiceValidationError."""
    init = _load_init()
    store = _fresh_store()
    hass = _runtime_hass([], store=store)
    init._register_services(hass)
    _schema, func = hass.services.registered["weekly_report"]

    with pytest.raises(init.ServiceValidationError):
        _run(func(_call({})))


def test_weekly_report_service_without_store_raises():
    """Fehlender Store → ServiceValidationError statt AttributeError."""
    init = _load_init()
    hass = _runtime_hass([_cfg_entry("e1", "Max")])
    init._register_services(hass)
    _schema, func = hass.services.registered["weekly_report"]

    with pytest.raises(init.ServiceValidationError):
        _run(func(_call({})))

"""Tests: ws_api.py — Entity-Resolver, Personenliste, panel_data-Shape.

Läuft ohne Home-Assistant-Runtime: `hass`, Registries und Store sind minimale
Fakes. Die Auflösung logischer Schlüssel → `entity_id` geschieht ausschließlich
über den stabilen `unique_id`-Suffix `{entry_id}_{key}` (kein Raten von
`entity_id`s).
"""

from __future__ import annotations

import asyncio
import importlib.util
import os
import sys
import types
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
import voluptuous as vol

_COMPONENT_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "custom_components", "health_o_mat")
)

# Fake-Paket für relative Imports
_PKG = "_hom_ws_test_pkg"
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


ws_api = _load("ws_api")

DOMAIN = "health_o_mat"
NOW = datetime(2026, 10, 15, 12, 0)


# --- Fakes ------------------------------------------------------------------


class RegEntry:
    """Minimaler Entity-Registry-Eintrag (Objektform)."""

    def __init__(self, unique_id, entity_id) -> None:
        self.unique_id = unique_id
        self.entity_id = entity_id


class FakeConfigEntries:
    def __init__(self, entries: list) -> None:
        self.entries = list(entries)

    def async_entries(self, domain: str) -> list:
        return list(self.entries)

    def async_get_entry(self, entry_id: str):
        for entry in self.entries:
            if entry.entry_id == entry_id:
                return entry
        return None


class FakeHass:
    def __init__(self, entries: list | None = None) -> None:
        self.data: dict = {}
        self.config_entries = FakeConfigEntries(entries or [])


class FakeConnection:
    def __init__(self, user_id: str | None = "user-1") -> None:
        self.results: list[tuple] = []
        self.errors: list[tuple] = []
        self.events: list[tuple] = []
        self.subscriptions: dict = {}
        self.user = SimpleNamespace(id=user_id) if user_id else None

    def send_result(self, msg_id, result=None) -> None:
        self.results.append((msg_id, result))

    def send_error(self, msg_id, code, message) -> None:
        self.errors.append((msg_id, code, message))

    def send_event(self, msg_id, event) -> None:
        self.events.append((msg_id, event))


class FakeCoordinator:
    """Coordinator-Fake: Listener-Verwaltung wie `DataUpdateCoordinator`."""

    def __init__(self) -> None:
        self.listeners: list = []
        self.updated: list = []

    def async_add_listener(self, update_callback, context=None):
        self.listeners.append(update_callback)

        def _remove() -> None:
            if update_callback in self.listeners:
                self.listeners.remove(update_callback)

        return _remove

    def async_set_updated_data(self, data) -> None:
        self.updated.append(data)
        for listener in list(self.listeners):
            listener()


def _entry(
    entry_id: str = "e1",
    person: str = "Caro",
    display: str | None = None,
    options: dict | None = None,
    goal: int = 2000,
    sys_threshold: int = 140,
    dia_threshold: int = 90,
):
    opts = dict(options or {})
    if display is not None:
        opts["person_display"] = display
    return SimpleNamespace(
        entry_id=entry_id,
        data={"person": person},
        options=opts,
        runtime_data=SimpleNamespace(
            daily_goal_ml=goal,
            sys_threshold=sys_threshold,
            dia_threshold=dia_threshold,
        ),
    )


def _store(data: dict):
    store = MagicMock()
    store.all_entries.return_value = data
    return store


def _write_store() -> MagicMock:
    """Store-Fake mit async-Write-Methoden (Aufrufe + Rückgaben injizierbar)."""
    store = MagicMock()
    store.all_entries.return_value = {}
    store.add_drink = AsyncMock()
    store.add_reading = AsyncMock()
    store.set_wellbeing = AsyncMock()
    store.remove_last_drink = AsyncMock(return_value=True)
    store.remove_last_reading = AsyncMock(return_value=True)
    return store


def _write_hass(store, entries: list, coordinators: dict | None = None) -> FakeHass:
    """Fake-Hass mit Shared-Store + Runtime-Registry (je Entry ein Coordinator)."""
    hass = FakeHass(entries)
    registry: dict = {"shared": {"store": store}}
    for entry in entries:
        coordinator = (coordinators or {}).get(entry.entry_id, FakeCoordinator())
        registry[entry.entry_id] = {
            "coordinator": coordinator,
            "store": store,
            "data": MagicMock(),
        }
    hass.data[DOMAIN] = registry
    return hass


# --- Resolver (rein) --------------------------------------------------------


def test_resolve_entity_ids_maps_by_unique_id_suffix():
    """Logische Schlüssel werden über `{entry_id}_{suffix}` aufgelöst."""
    entries = [
        RegEntry("e1_sensor_drinks_today", "sensor.health_o_mat_caro_drinks_today"),
        RegEntry("e1_sensor_bp_sys", "sensor.health_o_mat_caro_blood_pressure_systolic"),
        RegEntry("e1_sensor_wellbeing_since", "sensor.health_o_mat_caro_wellbeing_last_reported"),
    ]

    mapping = ws_api.resolve_entity_ids(entries, "e1")

    assert set(mapping) == set(ws_api.ENTITY_SUFFIXES)
    assert mapping["drinks_today"] == "sensor.health_o_mat_caro_drinks_today"
    assert mapping["bp_sys"] == "sensor.health_o_mat_caro_blood_pressure_systolic"
    assert mapping["wellbeing"] == "sensor.health_o_mat_caro_wellbeing_last_reported"
    # Fehlende Entities → None, kein Crash
    assert mapping["percent"] is None
    assert mapping["bp_history"] is None


def test_resolve_entity_ids_never_leaks_other_entries():
    """Fremde Entries und unvollständige Einträge werden ignoriert (kein Raten)."""
    entries = [
        RegEntry("e2_sensor_drinks_today", "sensor.health_o_mat_max_drinks_today"),
        RegEntry(None, "sensor.health_o_mat_caro_drinks_today"),
        RegEntry("e1_sensor_drinks_today", None),
    ]

    mapping = ws_api.resolve_entity_ids(entries, "e1")

    assert mapping["drinks_today"] is None
    assert "sensor.health_o_mat_max_drinks_today" not in mapping.values()
    assert "sensor.health_o_mat_caro_drinks_today" not in mapping.values()


def test_resolve_entity_ids_accepts_mapping_entries():
    """Auch Dict-förmige Registry-Einträge (z. B. aus Tests/Serialisierung) zählen."""
    entries = [{"unique_id": "e1_sensor_goal_percent", "entity_id": "sensor.caro_goal_percent"}]

    assert ws_api.resolve_entity_ids(entries, "e1")["percent"] == "sensor.caro_goal_percent"


def test_entity_ids_for_entry_tolerates_registry_failure(monkeypatch):
    """Bricht die Entity-Registry weg, kommt eine vollständige None-Map zurück."""
    monkeypatch.setattr(ws_api.er, "async_get", MagicMock(side_effect=RuntimeError("boom")))

    mapping = ws_api.entity_ids_for_entry(FakeHass(), "e1")

    assert set(mapping) == set(ws_api.ENTITY_SUFFIXES)
    assert all(value is None for value in mapping.values())


def test_entity_ids_for_entry_uses_registry_per_config_entry(monkeypatch):
    """Der Resolver fragt die Registry gezielt für den Config-Entry ab."""
    seen: list[str] = []

    def _entries(registry, entry_id):
        seen.append(entry_id)
        return [RegEntry(f"{entry_id}_sensor_bp_category", "sensor.caro_bp_category")]

    monkeypatch.setattr(ws_api.er, "async_get", lambda hass: object())
    monkeypatch.setattr(ws_api.er, "async_entries_for_config_entry", _entries)

    mapping = ws_api.entity_ids_for_entry(FakeHass(), "e7")

    assert seen == ["e7"]
    assert mapping["bp_category"] == "sensor.caro_bp_category"


# --- compute_pace -----------------------------------------------------------


def test_compute_pace_labels():
    """Pace-Label aus Ist-Stand vs. linearem Soll-Verlauf (8 h von 24 h = 1/3)."""
    # Soll bei 1/3 des Tages: 2000/3 ≈ 667 ml, Toleranz 200 ml
    assert ws_api.compute_pace(300, 2000, NOW, 4) == "behind"
    assert ws_api.compute_pace(700, 2000, NOW, 4) == "on_track"
    assert ws_api.compute_pace(1200, 2000, NOW, 4) == "ahead"
    assert ws_api.compute_pace(2000, 2000, NOW, 4) == "goal_reached"


def test_compute_pace_without_goal():
    """Ohne (positives) Tagesziel gibt es keinen Soll-Verlauf → None."""
    assert ws_api.compute_pace(500, 0, NOW, 4) is None
    assert ws_api.compute_pace(500, -1, NOW, 4) is None


# --- list_persons -----------------------------------------------------------


def test_list_persons_returns_entries_sorted_with_device_id(monkeypatch):
    """Personenliste: entry_id + Anzeigename (Options-Override) + Device-ID."""
    hass = FakeHass([_entry("e2", person="Max"), _entry("e1", person="caro", display="Caro")])
    monkeypatch.setattr(ws_api.dr, "async_get", lambda hass: object())
    monkeypatch.setattr(
        ws_api.dr,
        "async_entries_for_config_entry",
        lambda registry, entry_id: [SimpleNamespace(id=f"dev-{entry_id}")],
    )

    persons = ws_api.list_persons(hass)

    assert persons == [
        {"entry_id": "e1", "display_name": "Caro", "device_id": "dev-e1"},
        {"entry_id": "e2", "display_name": "Max", "device_id": "dev-e2"},
    ]


def test_list_persons_without_device(monkeypatch):
    """Ohne Device-Eintrag bleibt device_id None (kein Crash)."""
    hass = FakeHass([_entry("e1", person="Caro")])
    monkeypatch.setattr(ws_api.dr, "async_get", lambda hass: object())
    monkeypatch.setattr(ws_api.dr, "async_entries_for_config_entry", lambda registry, entry_id: [])

    assert ws_api.list_persons(hass)[0]["device_id"] is None


def test_list_persons_survives_config_entry_failure(monkeypatch):
    """Config-Entries nicht lesbar → leere Liste statt Exception."""
    hass = FakeHass()
    monkeypatch.setattr(hass.config_entries, "async_entries", MagicMock(side_effect=RuntimeError))

    assert ws_api.list_persons(hass) == []


# --- panel_data -------------------------------------------------------------


def _panel_hass(store_data: dict, entry, registry_entries: list, monkeypatch) -> FakeHass:
    hass = FakeHass([entry])
    hass.data[DOMAIN] = {
        "shared": {"store": _store(store_data)},
        entry.entry_id: {
            "coordinator": MagicMock(),
            "store": _store(store_data),
            "data": MagicMock(),
        },
    }
    monkeypatch.setattr(ws_api.er, "async_get", lambda hass: object())
    monkeypatch.setattr(
        ws_api.er,
        "async_entries_for_config_entry",
        lambda registry, entry_id: list(registry_entries),
    )
    monkeypatch.setattr(ws_api.dt_util, "now", lambda: NOW)
    return hass


def _sample_store_data() -> dict:
    return {
        "e1": {
            "person": "Caro",
            "total_ml_lifetime": 1234,
            "drinks": [
                {"ts": "2026-10-14T20:00:00", "ml": 500, "type": "Wasser", "src": "button"},
                {"ts": "2026-10-15T03:00:00", "ml": 200, "type": "Kaffee", "src": "service"},
                {"ts": "2026-10-15T08:00:00", "ml": 300, "type": "Wasser", "src": "service"},
            ],
            "readings": [
                {"ts": "2026-10-14T09:00:00", "sys": 120, "dia": 80, "pulse": 60},
                {"ts": "2026-10-15T09:30:00", "sys": 150, "dia": 95, "pulse": 70},
            ],
            "wellbeing": {"status": "good", "ts": "2026-10-15T10:00:00"},
            "wellbeing_history": [{"status": "okay", "ts": "2026-10-14T10:00:00"}],
        }
    }


def _registry_entries() -> list:
    return [
        RegEntry("e1_sensor_drinks_today", "sensor.caro_drinks_today"),
        RegEntry("e1_sensor_goal_percent", "sensor.caro_goal_percent"),
        RegEntry("e1_sensor_lifetime_total", "sensor.caro_lifetime_total"),
        RegEntry("e1_sensor_bp_sys", "sensor.caro_bp_sys"),
        RegEntry("e1_sensor_bp_dia", "sensor.caro_bp_dia"),
        RegEntry("e1_sensor_bp_pulse", "sensor.caro_bp_pulse"),
        RegEntry("e1_sensor_bp_category", "sensor.caro_bp_category"),
        RegEntry("e1_sensor_wellbeing_since", "sensor.caro_wellbeing_since"),
        RegEntry("e1_sensor_drinks_history", "sensor.caro_drinks_history"),
        RegEntry("e1_sensor_bp_history", "sensor.caro_bp_history"),
    ]


def test_panel_data_full_payload(monkeypatch):
    """panel_data liefert das definierte Shape mit korrekten Werten (reset_hour=4)."""
    entry = _entry(options={"daily_goal_ml": 2000, "daily_reset_hour": 4})
    hass = _panel_hass(_sample_store_data(), entry, _registry_entries(), monkeypatch)
    connection = FakeConnection()

    asyncio.run(
        ws_api.websocket_panel_data(
            hass, connection, {"id": 1, "type": ws_api.COMMAND_PANEL_DATA, "entry_id": "e1"}
        )
    )

    assert connection.errors == []
    msg_id, payload = connection.results[0]
    assert msg_id == 1

    # Kopf
    assert payload["entry_id"] == "e1"
    assert payload["person"] == "Caro"
    assert payload["goal_ml"] == 2000
    assert payload["reset_hour"] == 4

    # Heute (Tagesgrenze 04:00 → 03:00-Buchung zählt zum Vortag)
    today = payload["today"]
    assert today["ml"] == 300
    assert today["percent"] == 15.0
    assert today["count"] == 1
    assert today["breakdown"] == {"Wasser": 300}
    assert today["yesterday_ml"] == 700
    assert today["pace"] == "behind"

    # Blutdruck
    bp = payload["bp"]
    assert (bp["sys"], bp["dia"], bp["pulse"]) == (150, 95, 70)
    assert bp["at"] == "2026-10-15T09:30:00"
    assert bp["avg7"] == {"sys": 135.0, "dia": 87.5, "pulse": 65.0}
    assert bp["category"] == "grade_1"
    assert bp["warning"] is True
    assert len(bp["entries"]) == 2

    # Wohlbefinden
    wellbeing = payload["wellbeing"]
    assert wellbeing["key"] == "good"
    assert wellbeing["label"] == "Gut"
    assert wellbeing["emoji"] == "🙂"
    assert wellbeing["at"] == "2026-10-15T10:00:00"
    assert wellbeing["history"] == [
        {"key": "okay", "label": "Okay", "emoji": "😐", "ts": "2026-10-14T10:00:00"}
    ]

    # Entity-Bindung (unique_id-Suffix, nicht geraten)
    assert payload["entities"]["drinks_today"] == "sensor.caro_drinks_today"
    assert payload["entities"]["bp_history"] == "sensor.caro_bp_history"
    assert set(payload["entities"]) == set(ws_api.ENTITY_SUFFIXES)


def test_panel_data_person_anchor_is_stable_service_anchor(monkeypatch):
    """`person` = Anzeigename, `person_anchor` = stabiler Service-Anker (entry.data)."""
    entry = _entry("e1", person="caro", display="Caro (Privat)")
    hass = _panel_hass(_sample_store_data(), entry, _registry_entries(), monkeypatch)

    payload = ws_api.build_panel_data(hass, "e1", NOW)

    assert payload is not None
    # Anzeigename (options.person_display überschreibt)
    assert payload["person"] == "Caro (Privat)"
    # Stabiler Service-Anker = entry.data["person"], den `get_runtime_data` matcht
    assert payload["person_anchor"] == "caro"
    assert payload["person_anchor"] != payload["person"]


def test_panel_data_person_anchor_without_display_override(monkeypatch):
    """Ohne Options-Override sind Anzeigename und Service-Anker identisch."""
    entry = _entry("e1", person="Caro")
    hass = _panel_hass(_sample_store_data(), entry, _registry_entries(), monkeypatch)

    payload = ws_api.build_panel_data(hass, "e1", NOW)

    assert payload is not None
    assert payload["person"] == "Caro"
    assert payload["person_anchor"] == "Caro"


def test_panel_data_unknown_entry_sends_error(monkeypatch):
    """Unbekannte/nicht geladene entry_id → sauberer WS-Fehler, kein Crash."""
    hass = FakeHass([_entry()])
    hass.data[DOMAIN] = {"shared": {}}
    connection = FakeConnection()

    asyncio.run(
        ws_api.websocket_panel_data(
            hass, connection, {"id": 9, "type": ws_api.COMMAND_PANEL_DATA, "entry_id": "nope"}
        )
    )

    assert connection.results == []
    assert connection.errors[0][0] == 9
    assert connection.errors[0][1] == "not_found"


def test_panel_data_without_store_or_readings(monkeypatch):
    """Entry ohne Store-Daten: vollständiges Shape, alle Werte leer/None."""
    entry = _entry(goal=0, options={"daily_goal_ml": 0, "daily_reset_hour": 0})
    hass = _panel_hass({}, entry, [], monkeypatch)
    connection = FakeConnection()

    asyncio.run(
        ws_api.websocket_panel_data(
            hass, connection, {"id": 2, "type": ws_api.COMMAND_PANEL_DATA, "entry_id": "e1"}
        )
    )

    payload = connection.results[0][1]
    assert payload["goal_ml"] == 0
    assert payload["today"]["ml"] == 0
    assert payload["today"]["percent"] == 0.0  # kein Ziel → kein ZeroDivisionError
    assert payload["today"]["pace"] is None
    assert payload["bp"]["sys"] is None
    assert payload["bp"]["avg7"] == {"sys": None, "dia": None, "pulse": None}
    assert payload["bp"]["category"] is None
    assert payload["bp"]["warning"] is False
    assert payload["bp"]["entries"] == []
    assert payload["wellbeing"]["key"] is None
    assert payload["wellbeing"]["history"] == []
    assert all(value is None for value in payload["entities"].values())


def test_panel_data_warning_respects_thresholds(monkeypatch):
    """Warnung nur bei Überschreiten der (Runtime-)Schwellen."""
    data = {
        "e1": {
            "drinks": [],
            "readings": [{"ts": "2026-10-15T09:00:00", "sys": 140, "dia": 90, "pulse": 60}],
        }
    }
    entry = _entry(sys_threshold=140, dia_threshold=90)
    hass = _panel_hass(data, entry, [], monkeypatch)

    payload = ws_api.build_panel_data(hass, "e1", NOW)
    assert payload is not None
    assert payload["bp"]["warning"] is False  # exakt auf der Schwelle ≠ oberhalb

    data["e1"]["readings"] = [{"ts": "2026-10-15T09:00:00", "sys": 141, "dia": 90, "pulse": 60}]
    assert ws_api.build_panel_data(hass, "e1", NOW)["bp"]["warning"] is True


def test_panel_data_caps_bp_entries(monkeypatch):
    """Der Verlauf ist auf die letzten 30 Messungen begrenzt (Payload-Größe)."""
    readings = [
        {"ts": f"2026-09-{day:02d}T09:00:00", "sys": 120, "dia": 80, "pulse": 60}
        for day in range(1, 31)
    ]
    readings.append({"ts": "2026-10-14T23:00:00", "sys": 199, "dia": 99, "pulse": 99})
    data = {"e1": {"drinks": [], "readings": readings}}
    hass = _panel_hass(data, _entry(), [], monkeypatch)

    payload = ws_api.build_panel_data(hass, "e1", NOW)

    assert len(payload["bp"]["entries"]) == ws_api.BP_ENTRIES_LIMIT
    assert payload["bp"]["entries"][-1]["sys"] == 199  # neueste Messung zuletzt
    assert payload["bp"]["sys"] == 199


def test_panel_data_survives_broken_store(monkeypatch):
    """Fehlender Shared-Store → Null-Payload statt Exception."""
    entry = _entry()
    hass = FakeHass([entry])
    hass.data[DOMAIN] = {entry.entry_id: {"coordinator": MagicMock()}}
    monkeypatch.setattr(ws_api.er, "async_get", lambda hass: object())
    monkeypatch.setattr(ws_api.er, "async_entries_for_config_entry", lambda registry, entry_id: [])

    payload = ws_api.build_panel_data(hass, "e1", NOW)

    assert payload is not None
    assert payload["today"]["ml"] == 0
    assert payload["bp"]["entries"] == []


# --- Registrierung ----------------------------------------------------------

_ALL_COMMANDS = (
    ws_api.COMMAND_LIST_PERSONS,
    ws_api.COMMAND_PANEL_DATA,
    ws_api.COMMAND_BOOK_DRINK,
    ws_api.COMMAND_UNDO_LAST,
    ws_api.COMMAND_SAVE_MEASUREMENT,
    ws_api.COMMAND_SET_WELLBEING,
    ws_api.COMMAND_SUBSCRIBE,
    ws_api.COMMAND_GET_UI_SETTINGS,
    ws_api.COMMAND_SET_UI_SETTINGS,
)


def test_register_ws_api_is_idempotent_and_schema_validates(monkeypatch):
    """Zweimaliges Registrieren erzeugt keine Duplikate; Schemas sind strikt."""
    hass = FakeHass()
    calls: list[tuple] = []

    def _spy(hass, command, handler, schema):
        calls.append((command, handler, schema))

    monkeypatch.setattr(ws_api.websocket_api, "async_register_command", _spy)

    asyncio.run(ws_api.async_register_ws_api(hass))
    asyncio.run(ws_api.async_register_ws_api(hass))

    assert [command for command, _handler, _schema in calls] == list(_ALL_COMMANDS)
    assert ws_api.shared_data(hass)[ws_api.WS_MARKER] is True

    # async_response wandelt die Coroutine in den (synchronen) WS-Handler
    for _command, handler, _schema in calls:
        assert not asyncio.iscoroutinefunction(handler)

    schemas = {command: schema for command, _handler, schema in calls}

    # panel_data: entry_id Pflicht
    with pytest.raises(vol.Invalid):
        schemas[ws_api.COMMAND_PANEL_DATA]({"id": 1, "type": ws_api.COMMAND_PANEL_DATA})
    assert (
        schemas[ws_api.COMMAND_PANEL_DATA](
            {"id": 1, "type": ws_api.COMMAND_PANEL_DATA, "entry_id": "e1"}
        )["entry_id"]
        == "e1"
    )

    # book_drink: ml Pflicht und bereichsgeprüft
    with pytest.raises(vol.Invalid):
        schemas[ws_api.COMMAND_BOOK_DRINK](
            {"id": 1, "type": ws_api.COMMAND_BOOK_DRINK, "entry_id": "e1"}
        )
    with pytest.raises(vol.Invalid):
        schemas[ws_api.COMMAND_BOOK_DRINK](
            {"id": 1, "type": ws_api.COMMAND_BOOK_DRINK, "entry_id": "e1", "ml": 0}
        )
    assert (
        schemas[ws_api.COMMAND_BOOK_DRINK](
            {"id": 1, "type": ws_api.COMMAND_BOOK_DRINK, "entry_id": "e1", "ml": 250}
        )["ml"]
        == 250
    )

    # save_measurement: sys/dia Pflicht und bereichsgeprüft
    with pytest.raises(vol.Invalid):
        schemas[ws_api.COMMAND_SAVE_MEASUREMENT](
            {"id": 1, "type": ws_api.COMMAND_SAVE_MEASUREMENT, "entry_id": "e1", "sys": 120}
        )
    with pytest.raises(vol.Invalid):
        schemas[ws_api.COMMAND_SAVE_MEASUREMENT](
            {
                "id": 1,
                "type": ws_api.COMMAND_SAVE_MEASUREMENT,
                "entry_id": "e1",
                "sys": 120,
                "dia": 10,
            }
        )

    # set_wellbeing: key Pflicht
    with pytest.raises(vol.Invalid):
        schemas[ws_api.COMMAND_SET_WELLBEING](
            {"id": 1, "type": ws_api.COMMAND_SET_WELLBEING, "entry_id": "e1"}
        )

    # subscribe: entry_id optional (ohne → alle Personen)
    assert schemas[ws_api.COMMAND_SUBSCRIBE]({"id": 1, "type": ws_api.COMMAND_SUBSCRIBE})["id"] == 1

    # set_ui_settings: selected_person + prefs optional
    assert schemas[ws_api.COMMAND_SET_UI_SETTINGS](
        {"id": 1, "type": ws_api.COMMAND_SET_UI_SETTINGS, "prefs": {"compact": True}}
    )["prefs"] == {"compact": True}


def test_register_ws_api_uses_real_registration():
    """Echte Registrierung (ohne Mock): alle Kommandos + Schemas landen in hass.data."""
    hass = FakeHass()

    asyncio.run(ws_api.async_register_ws_api(hass))

    handlers = hass.data["websocket_api"]
    assert set(handlers) == set(_ALL_COMMANDS)

    for handler, _schema in handlers.values():
        assert not asyncio.iscoroutinefunction(handler)  # async_response → sync

    _handler, book_schema = handlers[ws_api.COMMAND_BOOK_DRINK]
    with pytest.raises(vol.Invalid):
        book_schema({"id": 3, "type": ws_api.COMMAND_BOOK_DRINK, "entry_id": "e1"})  # ml fehlt


def test_list_persons_handler_sends_result(monkeypatch):
    """`health_o_mat/list_persons` antwortet im definierten Shape."""
    hass = FakeHass([_entry("e1", person="Caro")])
    monkeypatch.setattr(ws_api.dr, "async_get", lambda hass: object())
    monkeypatch.setattr(ws_api.dr, "async_entries_for_config_entry", lambda registry, entry_id: [])
    connection = FakeConnection()

    asyncio.run(
        ws_api.websocket_list_persons(
            hass, connection, {"id": 5, "type": ws_api.COMMAND_LIST_PERSONS}
        )
    )

    assert connection.results == [
        (5, {"persons": [{"entry_id": "e1", "display_name": "Caro", "device_id": None}]})
    ]


# --- Undo-Kind-Normalisierung (rein) ----------------------------------------


def test_normalize_undo_kind_aliases():
    """`drink`/`drinks` → Getränke, `blood_pressure` → BP, fehlend → Getränke."""
    assert ws_api.normalize_undo_kind(None) == "drinks"
    assert ws_api.normalize_undo_kind("") == "drinks"
    assert ws_api.normalize_undo_kind("drink") == "drinks"
    assert ws_api.normalize_undo_kind("DRINKS") == "drinks"
    assert ws_api.normalize_undo_kind(" blood_pressure ") == "blood_pressure"
    assert ws_api.normalize_undo_kind("tea") is None
    assert ws_api.normalize_undo_kind(5) is None


# --- book_drink -------------------------------------------------------------


def _now(monkeypatch) -> None:
    monkeypatch.setattr(ws_api.dt_util, "now", lambda: NOW)


def test_book_drink_calls_store_and_refreshes(monkeypatch):
    """book_drink bucht ml+Typ über `store.add_drink` und triggert den Refresh."""
    _now(monkeypatch)
    store = _write_store()
    coordinator = FakeCoordinator()
    hass = _write_hass(store, [_entry("e1")], {"e1": coordinator})
    connection = FakeConnection()

    asyncio.run(
        ws_api.websocket_book_drink(
            hass,
            connection,
            {
                "id": 1,
                "type": ws_api.COMMAND_BOOK_DRINK,
                "entry_id": "e1",
                "ml": 250,
                "drink_type": "Kaffee",
            },
        )
    )

    assert connection.errors == []
    assert connection.results == [(1, None)]
    store.add_drink.assert_awaited_once()
    entry_id, ts, ml, drink_type, src = store.add_drink.await_args.args
    assert (entry_id, ml, drink_type) == ("e1", 250, "Kaffee")
    assert ts == NOW.isoformat()
    assert coordinator.updated == [NOW.isoformat()]


def test_book_drink_defaults_drink_type_to_eigen(monkeypatch):
    """Ohne `drink_type` wird der neutrale Standardtyp 'Eigen' gebucht."""
    _now(monkeypatch)
    store = _write_store()
    hass = _write_hass(store, [_entry("e1")])
    connection = FakeConnection()

    asyncio.run(
        ws_api.websocket_book_drink(
            hass,
            connection,
            {"id": 2, "type": ws_api.COMMAND_BOOK_DRINK, "entry_id": "e1", "ml": 300},
        )
    )

    assert store.add_drink.await_args.args[3] == "Eigen"


@pytest.mark.parametrize("ml", [0, -5, 10001])
def test_book_drink_invalid_ml_sends_error(monkeypatch, ml):
    """ml außerhalb 1..10000 → `invalid_format`, kein Store-Schreibzugriff."""
    _now(monkeypatch)
    store = _write_store()
    hass = _write_hass(store, [_entry("e1")])
    connection = FakeConnection()

    asyncio.run(
        ws_api.websocket_book_drink(
            hass,
            connection,
            {"id": 3, "type": ws_api.COMMAND_BOOK_DRINK, "entry_id": "e1", "ml": ml},
        )
    )

    assert connection.results == []
    assert connection.errors[0][1] == "invalid_format"
    store.add_drink.assert_not_called()


def test_book_drink_unknown_entry_sends_error(monkeypatch):
    """Unbekannte/nicht geladene entry_id → sauberer WS-Fehler (kein Crash)."""
    _now(monkeypatch)
    store = _write_store()
    hass = _write_hass(store, [_entry("e1")])
    connection = FakeConnection()

    asyncio.run(
        ws_api.websocket_book_drink(
            hass,
            connection,
            {"id": 4, "type": ws_api.COMMAND_BOOK_DRINK, "entry_id": "nope", "ml": 250},
        )
    )

    assert connection.results == []
    assert connection.errors[0][1] == "not_found"
    store.add_drink.assert_not_called()


# --- undo_last --------------------------------------------------------------


def test_undo_last_drinks_default(monkeypatch):
    """Ohne kind entfernt undo_last das letzte Getränk."""
    _now(monkeypatch)
    store = _write_store()
    coordinator = FakeCoordinator()
    hass = _write_hass(store, [_entry("e1")], {"e1": coordinator})
    connection = FakeConnection()

    asyncio.run(
        ws_api.websocket_undo_last(
            hass,
            connection,
            {"id": 1, "type": ws_api.COMMAND_UNDO_LAST, "entry_id": "e1"},
        )
    )

    assert connection.results == [(1, None)]
    store.remove_last_drink.assert_awaited_once_with("e1")
    store.remove_last_reading.assert_not_called()
    assert coordinator.updated == [NOW.isoformat()]


def test_undo_last_drink_alias(monkeypatch):
    """Der Alias `drink` (Singular) zielt ebenfalls auf Getränke."""
    _now(monkeypatch)
    store = _write_store()
    hass = _write_hass(store, [_entry("e1")])
    connection = FakeConnection()

    asyncio.run(
        ws_api.websocket_undo_last(
            hass,
            connection,
            {"id": 2, "type": ws_api.COMMAND_UNDO_LAST, "entry_id": "e1", "kind": "drink"},
        )
    )

    store.remove_last_drink.assert_awaited_once_with("e1")
    store.remove_last_reading.assert_not_called()


def test_undo_last_blood_pressure(monkeypatch):
    """kind='blood_pressure' entfernt die letzte Messung."""
    _now(monkeypatch)
    store = _write_store()
    hass = _write_hass(store, [_entry("e1")])
    connection = FakeConnection()

    asyncio.run(
        ws_api.websocket_undo_last(
            hass,
            connection,
            {
                "id": 3,
                "type": ws_api.COMMAND_UNDO_LAST,
                "entry_id": "e1",
                "kind": "blood_pressure",
            },
        )
    )

    store.remove_last_reading.assert_awaited_once_with("e1")
    store.remove_last_drink.assert_not_called()


def test_undo_last_empty_sends_error(monkeypatch):
    """Leerer Bestand → `not_found`-Fehler statt stiller Erfolg."""
    _now(monkeypatch)
    store = _write_store()
    store.remove_last_drink = AsyncMock(return_value=False)
    hass = _write_hass(store, [_entry("e1")])
    connection = FakeConnection()

    asyncio.run(
        ws_api.websocket_undo_last(
            hass,
            connection,
            {"id": 4, "type": ws_api.COMMAND_UNDO_LAST, "entry_id": "e1"},
        )
    )

    assert connection.results == []
    assert connection.errors[0][1] == "not_found"


def test_undo_last_unknown_kind_sends_error(monkeypatch):
    """Unbekanntes kind → `invalid_format`, kein Store-Zugriff."""
    _now(monkeypatch)
    store = _write_store()
    hass = _write_hass(store, [_entry("e1")])
    connection = FakeConnection()

    asyncio.run(
        ws_api.websocket_undo_last(
            hass,
            connection,
            {"id": 5, "type": ws_api.COMMAND_UNDO_LAST, "entry_id": "e1", "kind": "tea"},
        )
    )

    assert connection.errors[0][1] == "invalid_format"
    store.remove_last_drink.assert_not_called()
    store.remove_last_reading.assert_not_called()


# --- save_measurement -------------------------------------------------------


def test_save_measurement_saves_and_refreshes(monkeypatch):
    """Gültige Messung geht (inkl. pulse/note) an `store.add_reading`."""
    _now(monkeypatch)
    store = _write_store()
    coordinator = FakeCoordinator()
    hass = _write_hass(store, [_entry("e1")], {"e1": coordinator})
    connection = FakeConnection()

    asyncio.run(
        ws_api.websocket_save_measurement(
            hass,
            connection,
            {
                "id": 1,
                "type": ws_api.COMMAND_SAVE_MEASUREMENT,
                "entry_id": "e1",
                "sys": 130,
                "dia": 85,
                "pulse": 68,
                "note": "morgens",
            },
        )
    )

    assert connection.results == [(1, None)]
    entry_id, ts, sys_, dia, pulse, note, src = store.add_reading.await_args.args
    assert (entry_id, sys_, dia, pulse, note) == ("e1", 130, 85, 68, "morgens")
    assert ts == NOW.isoformat()
    assert coordinator.updated == [NOW.isoformat()]


def test_save_measurement_pulse_optional(monkeypatch):
    """Ohne pulse bleibt der Wert None (kein Coerce in die Store-Methode)."""
    _now(monkeypatch)
    store = _write_store()
    hass = _write_hass(store, [_entry("e1")])
    connection = FakeConnection()

    asyncio.run(
        ws_api.websocket_save_measurement(
            hass,
            connection,
            {
                "id": 2,
                "type": ws_api.COMMAND_SAVE_MEASUREMENT,
                "entry_id": "e1",
                "sys": 120,
                "dia": 80,
            },
        )
    )

    assert store.add_reading.await_args.args[4] is None


@pytest.mark.parametrize(
    "sys_value,dia_value",
    [(10, 80), (300, 80), (120, 10), (120, 999)],
)
def test_save_measurement_out_of_range_sends_error(monkeypatch, sys_value, dia_value):
    """sys/dia außerhalb MIN_BP_VALUE..MAX_BP_VALUE → `invalid_format`."""
    _now(monkeypatch)
    store = _write_store()
    hass = _write_hass(store, [_entry("e1")])
    connection = FakeConnection()

    asyncio.run(
        ws_api.websocket_save_measurement(
            hass,
            connection,
            {
                "id": 3,
                "type": ws_api.COMMAND_SAVE_MEASUREMENT,
                "entry_id": "e1",
                "sys": sys_value,
                "dia": dia_value,
            },
        )
    )

    assert connection.results == []
    assert connection.errors[0][1] == "invalid_format"
    store.add_reading.assert_not_called()


def test_save_measurement_unknown_entry_sends_error(monkeypatch):
    """Unbekannte entry_id → `not_found`."""
    _now(monkeypatch)
    store = _write_store()
    hass = _write_hass(store, [_entry("e1")])
    connection = FakeConnection()

    asyncio.run(
        ws_api.websocket_save_measurement(
            hass,
            connection,
            {
                "id": 4,
                "type": ws_api.COMMAND_SAVE_MEASUREMENT,
                "entry_id": "nope",
                "sys": 120,
                "dia": 80,
            },
        )
    )

    assert connection.errors[0][1] == "not_found"
    store.add_reading.assert_not_called()


# --- set_wellbeing ----------------------------------------------------------


def test_set_wellbeing_valid_key(monkeypatch):
    """Gültiger Wohlbefinden-Key wird mit Zeitstempel persistiert."""
    _now(monkeypatch)
    store = _write_store()
    coordinator = FakeCoordinator()
    hass = _write_hass(store, [_entry("e1")], {"e1": coordinator})
    connection = FakeConnection()

    asyncio.run(
        ws_api.websocket_set_wellbeing(
            hass,
            connection,
            {"id": 1, "type": ws_api.COMMAND_SET_WELLBEING, "entry_id": "e1", "key": "good"},
        )
    )

    assert connection.results == [(1, None)]
    store.set_wellbeing.assert_awaited_once_with("e1", "good", NOW.isoformat())
    assert coordinator.updated == [NOW.isoformat()]


@pytest.mark.parametrize("key", ["bogus", "", None, 5])
def test_set_wellbeing_invalid_key_sends_error(monkeypatch, key):
    """Unbekannter/leerer Key → `invalid_format`, kein Schreibzugriff."""
    _now(monkeypatch)
    store = _write_store()
    hass = _write_hass(store, [_entry("e1")])
    connection = FakeConnection()

    asyncio.run(
        ws_api.websocket_set_wellbeing(
            hass,
            connection,
            {"id": 2, "type": ws_api.COMMAND_SET_WELLBEING, "entry_id": "e1", "key": key},
        )
    )

    assert connection.results == []
    assert connection.errors[0][1] == "invalid_format"
    store.set_wellbeing.assert_not_called()


# --- subscribe --------------------------------------------------------------


def test_subscribe_registers_listener_and_pushes_refresh():
    """Ein Coordinator-Refresh pusht `{type:refresh, entry_id}` an die Verbindung."""
    store = _write_store()
    coordinator = FakeCoordinator()
    hass = _write_hass(store, [_entry("e1")], {"e1": coordinator})
    connection = FakeConnection()

    asyncio.run(
        ws_api.websocket_subscribe(
            hass,
            connection,
            {"id": 7, "type": ws_api.COMMAND_SUBSCRIBE, "entry_id": "e1"},
        )
    )

    assert connection.results == [(7, None)]
    assert len(coordinator.listeners) == 1
    assert 7 in connection.subscriptions

    ws_api.signal_refresh(hass, "e1")

    assert connection.events == [(7, {"type": "refresh", "entry_id": "e1"})]


def test_subscribe_unsubscribe_stops_events():
    """Nach dem Unsubscribe kommen keine weiteren Events (Listener entfernt)."""
    store = _write_store()
    coordinator = FakeCoordinator()
    hass = _write_hass(store, [_entry("e1")], {"e1": coordinator})
    connection = FakeConnection()

    asyncio.run(
        ws_api.websocket_subscribe(
            hass,
            connection,
            {"id": 8, "type": ws_api.COMMAND_SUBSCRIBE, "entry_id": "e1"},
        )
    )
    ws_api.signal_refresh(hass, "e1")

    connection.subscriptions[8]()

    assert coordinator.listeners == []
    ws_api.signal_refresh(hass, "e1")
    assert len(connection.events) == 1  # nur das Event vor dem Unsubscribe


def test_subscribe_without_entry_listens_all_persons():
    """Ohne entry_id werden ALLE geladenen Personen abonniert."""
    store = _write_store()
    c1, c2 = FakeCoordinator(), FakeCoordinator()
    hass = _write_hass(store, [_entry("e1"), _entry("e2")], {"e1": c1, "e2": c2})
    connection = FakeConnection()

    asyncio.run(
        ws_api.websocket_subscribe(hass, connection, {"id": 9, "type": ws_api.COMMAND_SUBSCRIBE})
    )

    assert len(c1.listeners) == 1
    assert len(c2.listeners) == 1

    ws_api.signal_refresh(hass, "e2")
    assert connection.events == [(9, {"type": "refresh", "entry_id": "e2"})]

    connection.subscriptions[9]()
    assert c1.listeners == [] and c2.listeners == []


def test_subscribe_unknown_entry_sends_error():
    """Unbekannte entry_id → `not_found`, keine Subscription registriert."""
    hass = _write_hass(_write_store(), [_entry("e1")])
    connection = FakeConnection()

    asyncio.run(
        ws_api.websocket_subscribe(
            hass,
            connection,
            {"id": 10, "type": ws_api.COMMAND_SUBSCRIBE, "entry_id": "nope"},
        )
    )

    assert connection.results == []
    assert connection.errors[0][1] == "not_found"
    assert connection.subscriptions == {}


# --- UI-Einstellungen -------------------------------------------------------


class FakeUiStore:
    """Minimaler In-Memory-Ersatz für `HealthOMatUiStore` (pro User)."""

    instances: list = []

    def __init__(self, hass) -> None:
        self.users: dict = {}
        self.loads = 0
        FakeUiStore.instances.append(self)

    async def async_load(self) -> None:
        self.loads += 1

    def get(self, user_id):
        return dict(self.users.get(user_id) or {"selected_person": None, "prefs": {}})

    async def async_set(self, user_id, **updates):
        current = dict(self.users.get(user_id) or {"selected_person": None, "prefs": {}})
        for key, value in updates.items():
            if key == "prefs" and isinstance(value, dict):
                current["prefs"] = {**current.get("prefs", {}), **value}
            else:
                current[key] = value
        self.users[user_id] = current
        return dict(current)


def test_ui_settings_roundtrip_per_user(monkeypatch):
    """get/set_ui_settings persistieren je HA-Nutzer; Lazy-Init ist idempotent."""
    FakeUiStore.instances = []
    monkeypatch.setattr(ws_api, "HealthOMatUiStore", FakeUiStore)
    hass = FakeHass()
    connection = FakeConnection(user_id="user-42")

    asyncio.run(
        ws_api.websocket_get_ui_settings(
            hass, connection, {"id": 1, "type": ws_api.COMMAND_GET_UI_SETTINGS}
        )
    )
    assert connection.results[0][1] == {"selected_person": None, "prefs": {}}

    asyncio.run(
        ws_api.websocket_set_ui_settings(
            hass,
            connection,
            {
                "id": 2,
                "type": ws_api.COMMAND_SET_UI_SETTINGS,
                "selected_person": "e1",
                "prefs": {"compact": True},
            },
        )
    )
    assert connection.results[1][1] == {"selected_person": "e1", "prefs": {"compact": True}}

    asyncio.run(
        ws_api.websocket_get_ui_settings(
            hass, connection, {"id": 3, "type": ws_api.COMMAND_GET_UI_SETTINGS}
        )
    )
    assert connection.results[2][1] == {"selected_person": "e1", "prefs": {"compact": True}}

    # Lazy-Init: genau EINE Instanz, genau EIN Load über drei Aufrufe.
    assert len(FakeUiStore.instances) == 1
    assert FakeUiStore.instances[0].loads == 1


def test_ui_settings_isolated_between_users(monkeypatch):
    """Settings sind je HA-Nutzer getrennt (kein Überschreiben)."""
    FakeUiStore.instances = []
    monkeypatch.setattr(ws_api, "HealthOMatUiStore", FakeUiStore)
    hass = FakeHass()
    user_a = FakeConnection(user_id="user-a")
    user_b = FakeConnection(user_id="user-b")

    asyncio.run(
        ws_api.websocket_set_ui_settings(
            hass,
            user_a,
            {
                "id": 1,
                "type": ws_api.COMMAND_SET_UI_SETTINGS,
                "selected_person": "e1",
            },
        )
    )
    asyncio.run(
        ws_api.websocket_get_ui_settings(
            hass, user_b, {"id": 2, "type": ws_api.COMMAND_GET_UI_SETTINGS}
        )
    )

    assert user_a.results[0][1]["selected_person"] == "e1"
    assert user_b.results[0][1] == {"selected_person": None, "prefs": {}}


def test_set_ui_settings_prefs_merge(monkeypatch):
    """`prefs` werden flach gemergt (bestehende Schlüssel bleiben)."""
    FakeUiStore.instances = []
    monkeypatch.setattr(ws_api, "HealthOMatUiStore", FakeUiStore)
    hass = FakeHass()
    connection = FakeConnection(user_id="user-1")

    asyncio.run(
        ws_api.websocket_set_ui_settings(
            hass,
            connection,
            {"id": 1, "type": ws_api.COMMAND_SET_UI_SETTINGS, "prefs": {"compact": True}},
        )
    )
    asyncio.run(
        ws_api.websocket_set_ui_settings(
            hass,
            connection,
            {"id": 2, "type": ws_api.COMMAND_SET_UI_SETTINGS, "prefs": {"theme": "dark"}},
        )
    )

    assert connection.results[1][1]["prefs"] == {"compact": True, "theme": "dark"}


def test_set_ui_settings_without_user_sends_error(monkeypatch):
    """Ohne angemeldeten Benutzer → `unauthorized`, nichts persistiert."""
    FakeUiStore.instances = []
    monkeypatch.setattr(ws_api, "HealthOMatUiStore", FakeUiStore)
    hass = FakeHass()
    connection = FakeConnection(user_id=None)

    asyncio.run(
        ws_api.websocket_set_ui_settings(
            hass,
            connection,
            {"id": 5, "type": ws_api.COMMAND_SET_UI_SETTINGS, "selected_person": "e1"},
        )
    )

    assert connection.results == []
    assert connection.errors[0][1] == "unauthorized"
    assert FakeUiStore.instances == []  # gar nicht erst initialisiert

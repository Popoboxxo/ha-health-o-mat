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
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError

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
    """Config-Entries-Fake inkl. `async_update_entry`-Spur.

    `async_update_entry` protokolliert VOR dem Setzen die alten Options
    (`before`) — so lässt sich belegen, dass das Kommando nicht direkt in
    `entry.options` schreibt. Danach werden die registrierten
    update-Listener aufgerufen, genau wie HA es beim echten Pfad tut
    (`entry.add_update_listener` → `_options_updated`).
    """

    def __init__(self, entries: list) -> None:
        self.entries = list(entries)
        self.updates: list[dict] = []
        self.flows: list[dict] = []
        self.flow_result: dict = {"flow_id": "flow-1"}
        self.removed: list[str] = []

    def async_entries(self, domain: str) -> list:
        return list(self.entries)

    def async_get_entry(self, entry_id: str):
        for entry in self.entries:
            if entry.entry_id == entry_id:
                return entry
        return None

    async def async_init(self, domain: str, context: dict | None = None):
        """Flow-Start-Fake: zeichnet (domain, context) auf und liefert `flow_result`."""
        self.flows.append({"domain": domain, "context": context})
        return dict(self.flow_result)

    async def async_remove(self, entry_id: str) -> None:
        self.removed.append(entry_id)
        self.entries = [entry for entry in self.entries if entry.entry_id != entry_id]

    def async_update_entry(self, entry, **kwargs) -> bool:
        self.updates.append({"entry_id": entry.entry_id, "before": dict(entry.options), **kwargs})
        for key, value in kwargs.items():
            setattr(entry, key, value)
        for listener in list(getattr(entry, "_update_listeners", [])):
            listener(entry)
        return True


class FakeHass:
    def __init__(self, entries: list | None = None) -> None:
        self.data: dict = {}
        self.config_entries = FakeConfigEntries(entries or [])


class FakeConnection:
    def __init__(self, user_id: str | None = "user-1", is_admin: bool = False) -> None:
        self.results: list[tuple] = []
        self.errors: list[tuple] = []
        self.events: list[tuple] = []
        self.subscriptions: dict = {}
        self.user = SimpleNamespace(id=user_id, is_admin=is_admin) if user_id else None

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
    entry = SimpleNamespace(
        entry_id=entry_id,
        data={"person": person},
        options=opts,
        runtime_data=SimpleNamespace(
            daily_goal_ml=goal,
            sys_threshold=sys_threshold,
            dia_threshold=dia_threshold,
        ),
    )
    # update-Listener-Verwaltung wie beim echten ConfigEntry (nur für den
    # Options-Pfad genutzt: `entry.add_update_listener(_options_updated)`).
    entry._update_listeners = []
    entry.add_update_listener = lambda listener: (
        entry._update_listeners.append(listener) or (lambda: None)
    )
    return entry


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


# --- pace_label (String-Vertrag der UI) -------------------------------------


def test_pace_label_maps_status_and_goal_reached():
    """`pace_label` bildet den Logik-Status auf den UI-String ab (+goal_reached)."""
    assert ws_api.pace_label({"status": "ahead"}, 1500, 2000) == "ahead"
    assert ws_api.pace_label({"status": "on_track"}, 1000, 2000) == "on_track"
    assert ws_api.pace_label({"status": "behind"}, 500, 2000) == "behind"
    # Ziel erreicht (auch exakt) hat Vorrang vor dem Logik-Status.
    assert ws_api.pace_label({"status": "ahead"}, 2000, 2000) == "goal_reached"
    assert ws_api.pace_label({"status": "ahead"}, 2500, 2000) == "goal_reached"


def test_pace_label_without_goal_is_none():
    """Ohne (positives) Tagesziel gibt es keinen Soll-Verlauf → None."""
    assert ws_api.pace_label({"status": None}, 500, 0) is None
    assert ws_api.pace_label({"status": None}, 500, -1) is None


def test_pace_label_tolerates_missing_status():
    """Fehlender/ungültiger Status → None statt eines falschen Labels."""
    assert ws_api.pace_label({}, 500, 2000) is None
    assert ws_api.pace_label({"status": 42}, 500, 2000) is None


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
        {
            "entry_id": "e1",
            "display_name": "Caro",
            "device_id": "dev-e1",
            "person_slug": "caro",
            "areas": {"drink": True, "bp": True, "wellbeing": True},
        },
        {
            "entry_id": "e2",
            "display_name": "Max",
            "device_id": "dev-e2",
            "person_slug": "Max",
            "areas": {"drink": True, "bp": True, "wellbeing": True},
        },
    ]


def test_list_persons_includes_slug_and_areas(monkeypatch):
    """`person_slug` ist der stabile entry.data-Anker, `areas` die aktiven Flächen."""
    entry = _entry("e1", person="caro", display="Caro (Privat)", options={"areas": {"bp": False}})
    hass = FakeHass([entry])
    monkeypatch.setattr(ws_api.dr, "async_get", lambda hass: object())
    monkeypatch.setattr(ws_api.dr, "async_entries_for_config_entry", lambda registry, entry_id: [])

    person = ws_api.list_persons(hass)[0]

    assert person["person_slug"] == "caro"  # entry.data["person"], NICHT der Anzeigename
    assert person["person_slug"] != person["display_name"]
    assert person["areas"] == {"drink": True, "bp": False, "wellbeing": True}


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
    assert payload["person_slug"] == "Caro"
    assert payload["areas"] == {"drink": True, "bp": True, "wellbeing": True}
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
        {
            "key": "okay",
            "label": "Okay",
            "emoji": "😐",
            "image": None,
            "score": 5,
            "ts": "2026-10-14T10:00:00",
        }
    ]

    # Entity-Bindung (unique_id-Suffix, nicht geraten)
    assert payload["entities"]["drinks_today"] == "sensor.caro_drinks_today"
    assert payload["entities"]["bp_history"] == "sensor.caro_bp_history"
    assert set(payload["entities"]) == set(ws_api.ENTITY_SUFFIXES)


# L2-Panel-JS liest `today.pace` als String; diese Menge ist der stabile Vertrag.
_PACE_LABELS = {"goal_reached", "ahead", "on_track", "behind"}


@pytest.mark.parametrize(
    ("ml", "expected_pace"),
    [
        (1300, "ahead"),  # Soll bei Halbzeit 1000, Toleranz 200 → +300
        (1000, "on_track"),  # exakt auf dem Soll
        (600, "behind"),  # -400 → unter dem Band
        (2000, "goal_reached"),  # Ziel erreicht (Vorrang vor "ahead")
    ],
)
def test_panel_data_pace_uses_logic_hydration_pace(monkeypatch, ml, expected_pace):
    """`today.pace` liefert echte Labels aus `logic.hydration_pace` (reset_hour=0)."""
    data = {"e1": {"drinks": [{"ts": "2026-10-15T09:00:00", "ml": ml, "type": "Wasser"}]}}
    entry = _entry(options={"daily_goal_ml": 2000, "daily_reset_hour": 0})
    hass = _panel_hass(data, entry, [], monkeypatch)

    payload = ws_api.build_panel_data(hass, "e1", NOW)

    assert payload is not None
    assert payload["today"]["pace"] == expected_pace
    assert payload["today"]["pace"] in _PACE_LABELS


def test_panel_data_pace_detail_fields_are_additive(monkeypatch):
    """Zusätzliche Detailwerte (expected/delta/forecast) ohne Umbenennung."""
    data = {"e1": {"drinks": [{"ts": "2026-10-15T09:00:00", "ml": 1300, "type": "Wasser"}]}}
    entry = _entry(options={"daily_goal_ml": 2000, "daily_reset_hour": 0})
    hass = _panel_hass(data, entry, [], monkeypatch)

    today = ws_api.build_panel_data(hass, "e1", NOW)["today"]

    # Bestehender Vertrag unverändert …
    assert today["ml"] == 1300
    assert today["percent"] == 65.0
    assert today["pace"] == "ahead"
    # … plus neue, rein additive Felder.
    assert today["expected_ml"] == 1000.0
    assert today["delta_ml"] == 300.0
    assert today["forecast_ml"] == 2600.0


def test_panel_data_pace_detail_fields_without_goal_are_none(monkeypatch):
    """Ohne Ziel: pace + Detailwerte None (kein Soll-Verlauf), kein Crash."""
    entry = _entry(goal=0, options={"daily_goal_ml": 0, "daily_reset_hour": 0})
    hass = _panel_hass({"e1": {"drinks": []}}, entry, [], monkeypatch)

    today = ws_api.build_panel_data(hass, "e1", NOW)["today"]

    assert today["pace"] is None
    assert today["expected_ml"] is None
    assert today["delta_ml"] is None
    assert today["forecast_ml"] is None


def test_panel_data_pace_never_emits_unknown_label(monkeypatch):
    """`today.pace` bleibt über alle Ist-Stände auf die bekannten Labels begrenzt."""
    entry = _entry(options={"daily_goal_ml": 2000, "daily_reset_hour": 0})
    for ml in (0, 100, 600, 1000, 1300, 2000, 5000):
        data = {"e1": {"drinks": [{"ts": "2026-10-15T09:00:00", "ml": ml, "type": "Wasser"}]}}
        hass = _panel_hass(data, entry, [], monkeypatch)

        assert ws_api.build_panel_data(hass, "e1", NOW)["today"]["pace"] in _PACE_LABELS


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


def test_panel_data_carries_slug_and_areas(monkeypatch):
    """`person_slug` (stabil) + `areas` (deaktivierter Bereich) im Panel-Payload."""
    entry = _entry("e1", person="caro", display="Caro", options={"areas": {"drink": False}})
    hass = _panel_hass(_sample_store_data(), entry, _registry_entries(), monkeypatch)

    payload = ws_api.build_panel_data(hass, "e1", NOW)

    assert payload is not None
    assert payload["person_slug"] == "caro"
    assert payload["areas"] == {"drink": False, "bp": True, "wellbeing": True}


# Top-Level-Vertrag des Panel-Payloads (additiv erweitert um `quick_drinks`).
_PANEL_TOP_LEVEL_KEYS = {
    "entry_id",
    "person",
    "person_slug",
    "areas",
    "person_anchor",
    "goal_ml",
    "reset_hour",
    "today",
    "bp",
    "wellbeing",
    "wellbeing_scale",
    "quick_drinks",
    "entities",
}


def test_panel_data_top_level_keys_are_additive(monkeypatch):
    """`quick_drinks` kommt hinzu, alle bestehenden Keys bleiben unverändert."""
    entry = _entry(options={"daily_goal_ml": 2000, "daily_reset_hour": 4})
    hass = _panel_hass(_sample_store_data(), entry, _registry_entries(), monkeypatch)

    payload = ws_api.build_panel_data(hass, "e1", NOW)

    assert payload is not None
    assert set(payload) == _PANEL_TOP_LEVEL_KEYS


def test_panel_data_quick_drinks_from_options(monkeypatch):
    """Konfigurierte Quick-Drinks (Key/Label/ml/Icon) landen im Panel-Payload."""
    configured = [
        {"key": "slot_0", "label": "Kaffee", "ml": 250, "icon": "mdi:coffee"},
        {"key": "slot_1", "label": "Wasser", "ml": 500, "icon": "mdi:glass-water"},
    ]
    entry = _entry(options={"quick_drinks": configured})
    hass = _panel_hass({}, entry, [], monkeypatch)

    payload = ws_api.build_panel_data(hass, "e1", NOW)

    assert payload is not None
    assert payload["quick_drinks"] == [
        {"key": "slot_0", "label": "Kaffee", "ml": 250, "icon": "mdi:coffee"},
        {"key": "slot_1", "label": "Wasser", "ml": 500, "icon": "mdi:glass-water"},
    ]


def test_panel_data_quick_drinks_default_fallback(monkeypatch):
    """Ohne Option: Standard-Set als frische Kopien (kein geteiltes Dict)."""
    entry = _entry()
    hass = _panel_hass({}, entry, [], monkeypatch)

    payload = ws_api.build_panel_data(hass, "e1", NOW)

    assert payload is not None
    assert payload["quick_drinks"] == ws_api.DEFAULT_QUICK_DRINKS
    assert payload["quick_drinks"][0] is not ws_api.DEFAULT_QUICK_DRINKS[0]
    assert payload["quick_drinks"][0]["key"] == "glas_wasser"
    assert payload["quick_drinks"][0]["ml"] == 200


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
    ws_api.COMMAND_GET_SETTINGS,
    ws_api.COMMAND_SET_SETTINGS,
    ws_api.COMMAND_EXPORT_CSV,
    ws_api.COMMAND_START_PERSON_FLOW,
    ws_api.COMMAND_DELETE_PERSON,
    ws_api.COMMAND_BACKUP,
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

    # set_wellbeing: key ODER score (die Pflichtprüfung macht der Handler)
    assert (
        schemas[ws_api.COMMAND_SET_WELLBEING](
            {"id": 1, "type": ws_api.COMMAND_SET_WELLBEING, "entry_id": "e1", "key": "good"}
        )["key"]
        == "good"
    )
    assert (
        schemas[ws_api.COMMAND_SET_WELLBEING](
            {"id": 1, "type": ws_api.COMMAND_SET_WELLBEING, "entry_id": "e1", "score": 7}
        )["score"]
        == 7
    )

    # subscribe: entry_id optional (ohne → alle Personen)
    assert schemas[ws_api.COMMAND_SUBSCRIBE]({"id": 1, "type": ws_api.COMMAND_SUBSCRIBE})["id"] == 1

    # set_ui_settings: selected_person + prefs optional
    assert schemas[ws_api.COMMAND_SET_UI_SETTINGS](
        {"id": 1, "type": ws_api.COMMAND_SET_UI_SETTINGS, "prefs": {"compact": True}}
    )["prefs"] == {"compact": True}

    # get_settings: entry_id Pflicht
    with pytest.raises(vol.Invalid):
        schemas[ws_api.COMMAND_GET_SETTINGS]({"id": 1, "type": ws_api.COMMAND_GET_SETTINGS})

    # set_settings: entry_id Pflicht, Settings-Felder durchgereicht (Wertprüfung
    # übernimmt parse_settings_message), unbekannte Felder hart abgewiesen.
    with pytest.raises(vol.Invalid):
        schemas[ws_api.COMMAND_SET_SETTINGS]({"id": 1, "type": ws_api.COMMAND_SET_SETTINGS})
    parsed = schemas[ws_api.COMMAND_SET_SETTINGS](
        {
            "id": 1,
            "type": ws_api.COMMAND_SET_SETTINGS,
            "entry_id": "e1",
            "daily_goal_ml": 2500,
            "quick_drinks": [{"key": "a", "label": "A", "ml": 200, "icon": "mdi:cup-water"}],
        }
    )
    assert parsed["daily_goal_ml"] == 2500
    assert parsed["quick_drinks"][0]["ml"] == 200
    with pytest.raises(vol.Invalid):
        schemas[ws_api.COMMAND_SET_SETTINGS](
            {"id": 1, "type": ws_api.COMMAND_SET_SETTINGS, "entry_id": "e1", "bogus": 1}
        )

    # export_csv: entry_id/dataset optional, unbekannte Felder abgewiesen
    assert (
        schemas[ws_api.COMMAND_EXPORT_CSV](
            {"id": 1, "type": ws_api.COMMAND_EXPORT_CSV, "entry_id": "e1", "dataset": "drinks"}
        )["dataset"]
        == "drinks"
    )
    assert (
        schemas[ws_api.COMMAND_EXPORT_CSV]({"id": 1, "type": ws_api.COMMAND_EXPORT_CSV})["id"] == 1
    )
    with pytest.raises(vol.Invalid):
        schemas[ws_api.COMMAND_EXPORT_CSV]({"id": 1, "type": ws_api.COMMAND_EXPORT_CSV, "bogus": 1})

    # delete_person: entry_id + confirm sind Pflicht
    with pytest.raises(vol.Invalid):
        schemas[ws_api.COMMAND_DELETE_PERSON](
            {"id": 1, "type": ws_api.COMMAND_DELETE_PERSON, "entry_id": "e1"}
        )
    assert (
        schemas[ws_api.COMMAND_DELETE_PERSON](
            {
                "id": 1,
                "type": ws_api.COMMAND_DELETE_PERSON,
                "entry_id": "e1",
                "confirm": "caro",
            }
        )["confirm"]
        == "caro"
    )

    # start_person_flow / backup: keine Parameter
    assert (
        schemas[ws_api.COMMAND_START_PERSON_FLOW](
            {"id": 1, "type": ws_api.COMMAND_START_PERSON_FLOW}
        )["id"]
        == 1
    )
    assert schemas[ws_api.COMMAND_BACKUP]({"id": 1, "type": ws_api.COMMAND_BACKUP})["id"] == 1


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


def test_register_ws_api_guards_exactly_the_admin_commands(monkeypatch):
    """Der Admin-Guard wird NUR auf die admin-only Kommandos angewendet."""
    hass = FakeHass()
    calls: list[tuple] = []
    guarded: list = []

    class _Guarded:
        """Marker: `_admin_guard` wurde für diesen Handler aufgerufen."""

        def __init__(self, inner) -> None:
            self.inner = inner

    def _spy_register(hass, command, handler, schema):
        calls.append((command, isinstance(handler, _Guarded)))

    def _spy_guard(handler):
        guarded.append(handler)
        return _Guarded(handler)

    monkeypatch.setattr(ws_api.websocket_api, "async_register_command", _spy_register)
    monkeypatch.setattr(ws_api, "_admin_guard", _spy_guard)

    asyncio.run(ws_api.async_register_ws_api(hass))

    assert len(calls) == len(_ALL_COMMANDS)
    assert len(guarded) == len(ws_api.ADMIN_ONLY_COMMANDS)
    for command, is_guarded in calls:
        assert is_guarded is (command in ws_api.ADMIN_ONLY_COMMANDS)


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
        (
            5,
            {
                "persons": [
                    {
                        "entry_id": "e1",
                        "display_name": "Caro",
                        "device_id": None,
                        "person_slug": "Caro",
                        "areas": {"drink": True, "bp": True, "wellbeing": True},
                    }
                ]
            },
        )
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


def test_set_wellbeing_accepts_numeric_score(monkeypatch):
    """Numerischer Score wird auf den kanonischen Key abgebildet."""
    _now(monkeypatch)
    store = _write_store()
    hass = _write_hass(store, [_entry("e1")])
    connection = FakeConnection()

    asyncio.run(
        ws_api.websocket_set_wellbeing(
            hass,
            connection,
            {"id": 3, "type": ws_api.COMMAND_SET_WELLBEING, "entry_id": "e1", "score": 7},
        )
    )

    assert connection.results == [(3, None)]
    store.set_wellbeing.assert_awaited_once_with("e1", "good", NOW.isoformat())


def test_set_wellbeing_requires_key_or_score(monkeypatch):
    """Weder key noch score → `invalid_format`, kein Schreibzugriff."""
    _now(monkeypatch)
    store = _write_store()
    hass = _write_hass(store, [_entry("e1")])
    connection = FakeConnection()

    asyncio.run(
        ws_api.websocket_set_wellbeing(
            hass,
            connection,
            {"id": 4, "type": ws_api.COMMAND_SET_WELLBEING, "entry_id": "e1"},
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


# --- Admin/Settings + Export (L3) -------------------------------------------
# Schreibrechte: Settings/Export admin-only, Alltag (book_drink & Co.) für alle.

SETTINGS_DEFAULTS = {
    "daily_goal_ml": 2000,
    "daily_reset_hour": 0,
    "person_display": "Caro",
    "sys_threshold": 140,
    "dia_threshold": 90,
    "retention_months": 0,
    "enable_sidebar_panel": False,
}


def _settings_hass(entry) -> FakeHass:
    """Fake-Hass mit geladenem Entry, Shared-Store und Service-Aufruf-Spy."""
    hass = _write_hass(_write_store(), [entry])
    hass.services = SimpleNamespace(async_call=AsyncMock())
    return hass


def _settings_msg(command: str, msg_id: int = 1, **extra) -> dict:
    return {"id": msg_id, "type": command, **extra}


def _admin_connection() -> FakeConnection:
    return FakeConnection(is_admin=True)


# --- get_settings -----------------------------------------------------------


def test_get_settings_returns_options_in_options_flow_shape():
    """`get_settings` liefert exakt die Options (inkl. Textform des Lexikons)."""
    entry = _entry(
        "e1",
        options={
            "daily_goal_ml": 2500,
            "daily_reset_hour": 5,
            "person_display": "Caro (Privat)",
            "quick_drinks": [
                {
                    "key": "glas_wasser",
                    "label": "Glas Wasser",
                    "ml": 200,
                    "icon": "mdi:glass-water",
                }
            ],
            # JSON-Roundtrip der Options: Lexikon-Werte kommen als Listen zurück.
            "drink_lexicon": {"wasser": ["Wasser", 250], "kaffee": ["Kaffee", 250]},
            "sys_threshold": 135,
            "dia_threshold": 85,
            "retention_months": 6,
            "enable_sidebar_panel": True,
        },
    )
    hass = _settings_hass(entry)
    connection = _admin_connection()

    asyncio.run(
        ws_api.websocket_get_settings(
            hass, connection, _settings_msg(ws_api.COMMAND_GET_SETTINGS, entry_id="e1")
        )
    )

    assert connection.errors == []
    assert connection.results == [
        (
            1,
            {
                "daily_goal_ml": 2500,
                "daily_reset_hour": 5,
                "person_display": "Caro (Privat)",
                "quick_drinks": [
                    {
                        "key": "glas_wasser",
                        "label": "Glas Wasser",
                        "ml": 200,
                        "icon": "mdi:glass-water",
                    }
                ],
                "drink_lexicon": "wasser=Wasser,250\nkaffee=Kaffee,250",
                "sys_threshold": 135,
                "dia_threshold": 85,
                "retention_months": 6,
                "enable_sidebar_panel": True,
                "areas": {"drink": True, "bp": True, "wellbeing": True},
            },
        )
    ]


def test_get_settings_defaults_when_options_empty():
    """Leere Options → Options-Flow-Defaults (Ziel aus Runtime-Spiegel)."""
    entry = _entry("e1", person="Caro")

    result = ws_api.build_settings(entry)

    assert {key: result[key] for key in SETTINGS_DEFAULTS} == SETTINGS_DEFAULTS
    assert [qd["key"] for qd in result["quick_drinks"]] == [
        qd["key"] for qd in ws_api.DEFAULT_QUICK_DRINKS
    ]
    assert result["drink_lexicon"].startswith("wasser=Wasser,250")
    assert result["drink_lexicon"] == ws_api.format_lexicon_text(ws_api.DRINK_LEXICON)


def test_get_settings_empty_quick_drinks_option_falls_back_to_default():
    """Eine leere quick_drinks-Option fällt auf das Standard-Set zurück."""
    entry = _entry("e1", options={"quick_drinks": []})

    assert len(ws_api.build_settings(entry)["quick_drinks"]) == len(ws_api.DEFAULT_QUICK_DRINKS)


def test_get_settings_uses_runtime_mirror_for_untouched_options():
    """Nie gesetzte Option → Runtime-Spiegel (kein hartkodierter Default)."""
    entry = _entry("e1", goal=2800, sys_threshold=125, dia_threshold=75)

    result = ws_api.build_settings(entry)

    assert result["daily_goal_ml"] == 2800
    assert result["sys_threshold"] == 125
    assert result["dia_threshold"] == 75


def test_get_settings_includes_areas_default_all_active():
    """Ohne `areas`-Option sind alle Bereiche aktiv (fehlender Schlüssel = aktiv)."""
    entry = _entry("e1")

    assert ws_api.build_settings(entry)["areas"] == {
        "drink": True,
        "bp": True,
        "wellbeing": True,
    }


def test_get_settings_reflects_disabled_area():
    """Ein explizit auf False gesetzter Bereich erscheint deaktiviert."""
    entry = _entry("e1", options={"areas": {"wellbeing": False}})

    assert ws_api.build_settings(entry)["areas"] == {
        "drink": True,
        "bp": True,
        "wellbeing": False,
    }


def test_set_settings_persists_areas():
    """`areas` wird über den Options-Pfad persistiert und zurückgespiegelt."""
    entry = _entry("e1", options={"daily_goal_ml": 2000})
    hass = _settings_hass(entry)
    connection = _admin_connection()

    asyncio.run(
        ws_api.websocket_set_settings(
            hass,
            connection,
            _settings_msg(
                ws_api.COMMAND_SET_SETTINGS,
                entry_id="e1",
                areas={"drink": False, "bp": True, "wellbeing": True},
            ),
        )
    )

    assert connection.errors == []
    stored = hass.config_entries.updates[0]["options"]["areas"]
    assert stored == {"drink": False, "bp": True, "wellbeing": True}
    assert connection.results[0][1]["areas"] == {
        "drink": False,
        "bp": True,
        "wellbeing": True,
    }


def test_parse_settings_message_accepts_areas():
    """Ein gültiges `areas`-Dict wird unverändert übernommen."""
    updates, error = ws_api.parse_settings_message({"areas": {"drink": False}})

    assert error is None
    assert updates == {"areas": {"drink": False}}


@pytest.mark.parametrize(
    "areas",
    [
        {"bogus": True},  # unbekannter Bereich → PREVENT_EXTRA des Nested-Schemas
        {"drink": "vielleicht"},  # falscher Wertetyp → vol.Boolean- Fehler
        "kein-dict",
    ],
)
def test_parse_settings_message_rejects_invalid_areas(areas):
    """Ungültige `areas`-Angaben → Fehler statt stiller Übernahme."""
    updates, error = ws_api.parse_settings_message({"areas": areas})

    assert updates == {}
    assert error is not None


def test_set_settings_rejects_invalid_area_value():
    """Falscher Bereichstyp → `invalid_format` mit Feldpfad, kein Schreibzugriff."""
    entry = _entry("e1", options={"daily_goal_ml": 2000})
    hass = _settings_hass(entry)
    connection = _admin_connection()

    asyncio.run(
        ws_api.websocket_set_settings(
            hass,
            connection,
            _settings_msg(
                ws_api.COMMAND_SET_SETTINGS, entry_id="e1", areas={"drink": "vielleicht"}
            ),
        )
    )

    assert connection.results == []
    assert connection.errors[0][1] == "invalid_format"
    assert "area" in connection.errors[0][2]
    assert hass.config_entries.updates == []


def test_get_settings_unknown_entry_sends_error():
    """Unbekannte/nicht geladene entry_id → `not_found`."""
    entry = _entry("e1")
    hass = _settings_hass(entry)
    connection = _admin_connection()

    asyncio.run(
        ws_api.websocket_get_settings(
            hass, connection, _settings_msg(ws_api.COMMAND_GET_SETTINGS, entry_id="nope")
        )
    )

    assert connection.results == []
    assert connection.errors[0][1] == "not_found"


@pytest.mark.parametrize("user_id", [None, "user-1"])
def test_get_settings_requires_admin(user_id):
    """Ohne Admin-Recht (oder ohne User) → `unauthorized`, kein Ergebnis."""
    entry = _entry("e1")
    hass = _settings_hass(entry)
    connection = FakeConnection(user_id=user_id, is_admin=False)

    asyncio.run(
        ws_api.websocket_get_settings(
            hass, connection, _settings_msg(ws_api.COMMAND_GET_SETTINGS, entry_id="e1")
        )
    )

    assert connection.results == []
    assert connection.errors[0][1] == "unauthorized"


# --- set_settings -----------------------------------------------------------


def test_set_settings_persists_via_async_update_entry_and_fires_listener():
    """Schreibt NUR über `async_update_entry` (Options-Listener-Pfad)."""
    entry = _entry("e1", options={"daily_goal_ml": 2000, "retention_months": 3})
    hass = _settings_hass(entry)
    listener = MagicMock()
    entry.add_update_listener(listener)
    connection = _admin_connection()

    asyncio.run(
        ws_api.websocket_set_settings(
            hass,
            connection,
            _settings_msg(
                ws_api.COMMAND_SET_SETTINGS,
                entry_id="e1",
                daily_goal_ml=3000,
                daily_reset_hour=4,
            ),
        )
    )

    assert connection.errors == []
    # Genau EIN Schreibzugriff — über genau den Listener-Pfad.
    assert len(hass.config_entries.updates) == 1
    record = hass.config_entries.updates[0]
    assert record["entry_id"] == "e1"
    # Kein Direktschreiben vor dem Aufruf: die alten Options waren noch unverändert.
    assert record["before"] == {"daily_goal_ml": 2000, "retention_months": 3}
    # Merge: nur die übergebenen Felder ändern sich, der Rest bleibt erhalten.
    assert record["options"] == {
        "daily_goal_ml": 3000,
        "daily_reset_hour": 4,
        "retention_months": 3,
    }
    assert entry.options == record["options"]
    listener.assert_called_once_with(entry)

    # Antwort = neue Settings (gleiches Format wie get_settings).
    result = connection.results[0][1]
    assert result["daily_goal_ml"] == 3000
    assert result["daily_reset_hour"] == 4
    assert result["retention_months"] == 3
    assert set(result) == set(SETTINGS_DEFAULTS) | {"quick_drinks", "drink_lexicon", "areas"}


def test_set_settings_persists_canonical_quick_drinks():
    """Quick-Drinks werden in der Options-Flow-Repräsentation persistiert."""
    entry = _entry("e1")
    hass = _settings_hass(entry)
    connection = _admin_connection()

    asyncio.run(
        ws_api.websocket_set_settings(
            hass,
            connection,
            _settings_msg(
                ws_api.COMMAND_SET_SETTINGS,
                entry_id="e1",
                quick_drinks=[
                    {"key": "slot_0", "label": "Glas Wasser", "ml": 200},
                    {"key": "slot_1", "label": "Kaffee", "ml": 250, "icon": "mdi:coffee"},
                ],
            ),
        )
    )

    assert connection.errors == []
    stored = hass.config_entries.updates[0]["options"]["quick_drinks"]
    # Fehlendes icon bekommt den Standard; Reihenfolge bleibt erhalten.
    assert stored == [
        {"key": "slot_0", "label": "Glas Wasser", "ml": 200, "icon": "mdi:cup-water"},
        {"key": "slot_1", "label": "Kaffee", "ml": 250, "icon": "mdi:coffee"},
    ]


def test_set_settings_persists_person_display_and_panel_toggle():
    """person_display und enable_sidebar_panel landen (typkorrekt) in den Options."""
    entry = _entry("e1", person="caro")
    hass = _settings_hass(entry)
    connection = _admin_connection()

    asyncio.run(
        ws_api.websocket_set_settings(
            hass,
            connection,
            _settings_msg(
                ws_api.COMMAND_SET_SETTINGS,
                entry_id="e1",
                person_display="Caro",
                enable_sidebar_panel=True,
            ),
        )
    )

    stored = hass.config_entries.updates[0]["options"]
    assert stored["person_display"] == "Caro"
    assert stored["enable_sidebar_panel"] is True
    assert connection.results[0][1]["person_display"] == "Caro"
    assert connection.results[0][1]["enable_sidebar_panel"] is True


def test_set_settings_retention_zero_disables_archiving():
    """retention_months=0 schaltet das Archiv ab (nicht „nicht gesetzt")."""
    entry = _entry("e1", options={"retention_months": 12})
    hass = _settings_hass(entry)
    connection = _admin_connection()

    asyncio.run(
        ws_api.websocket_set_settings(
            hass,
            connection,
            _settings_msg(ws_api.COMMAND_SET_SETTINGS, entry_id="e1", retention_months=0),
        )
    )

    assert hass.config_entries.updates[0]["options"]["retention_months"] == 0
    assert connection.results[0][1]["retention_months"] == 0


def test_set_settings_lexicon_parsed_like_the_options_flow():
    """Lexikon-Text → exakt die Dict-Repräsentation des Options-Flows."""
    text = "# Kommentar\nWasser=Wasser,500\nKaffee=Kaffee,250\n"
    entry = _entry("e1")
    hass = _settings_hass(entry)
    connection = _admin_connection()

    asyncio.run(
        ws_api.websocket_set_settings(
            hass,
            connection,
            _settings_msg(ws_api.COMMAND_SET_SETTINGS, entry_id="e1", drink_lexicon=text),
        )
    )

    assert connection.errors == []
    stored = hass.config_entries.updates[0]["options"]["drink_lexicon"]
    expected = ws_api.parser.parse_lexicon_text(text)
    assert expected == {"wasser": ("Wasser", 500), "kaffee": ("Kaffee", 250)}
    assert stored == expected
    # Antwort enthält wieder die Textform (Hin- und Rückweg sind stabil).
    assert connection.results[0][1]["drink_lexicon"] == "wasser=Wasser,500\nkaffee=Kaffee,250"


@pytest.mark.parametrize(
    "text,line",
    [
        ("wasser=Wasser,250\nkaputt\nkaffee=Kaffee,250", 2),
        ("wasser=Wasser,250\nkaffee=Kaffee\n", 2),
        ("wasser=Wasser,250\nkaffee=Kaffee,0\n", 2),
        ("wasser=Wasser,250\n=Kaffee,250\n", 2),
    ],
)
def test_set_settings_invalid_lexicon_line_reports_line_number(text, line):
    """Ungültige Lexikon-Zeile → `invalid_format` MIT Zeilenangabe, kein Write."""
    entry = _entry("e1", options={"daily_goal_ml": 2000})
    hass = _settings_hass(entry)
    connection = _admin_connection()

    asyncio.run(
        ws_api.websocket_set_settings(
            hass,
            connection,
            _settings_msg(ws_api.COMMAND_SET_SETTINGS, entry_id="e1", drink_lexicon=text),
        )
    )

    assert connection.results == []
    assert connection.errors[0][1] == "invalid_format"
    message = connection.errors[0][2]
    assert "Getränke-Lexikon" in message
    assert f"Zeile {line}" in message
    assert hass.config_entries.updates == []  # nichts persistiert


def test_set_settings_lexicon_wrong_type_sends_error():
    """drink_lexicon muss Text sein (kein stiller No-op)."""
    entry = _entry("e1")
    hass = _settings_hass(entry)
    connection = _admin_connection()

    asyncio.run(
        ws_api.websocket_set_settings(
            hass,
            connection,
            _settings_msg(ws_api.COMMAND_SET_SETTINGS, entry_id="e1", drink_lexicon=42),
        )
    )

    assert connection.errors[0][1] == "invalid_format"
    assert "drink_lexicon" in connection.errors[0][2]
    assert hass.config_entries.updates == []


@pytest.mark.parametrize(
    "payload",
    [
        {"daily_goal_ml": 0},
        {"daily_goal_ml": -10},
        {"daily_goal_ml": "viel"},
        {"daily_reset_hour": 24},
        {"daily_reset_hour": -1},
        {"sys_threshold": 10},
        {"sys_threshold": 999},
        {"dia_threshold": 10},
        {"dia_threshold": 999},
        {"retention_months": -1},
        {"retention_months": "x"},
        {"quick_drinks": []},
        {"quick_drinks": "kein-liste"},
        {"quick_drinks": [{"key": "a", "label": "A"}]},
        {"quick_drinks": [{"key": "a", "label": "A", "ml": 0}]},
        {"quick_drinks": [{"key": "a", "label": "A", "ml": 99999}]},
        {"enable_sidebar_panel": "vielleicht"},
    ],
)
def test_set_settings_rejects_invalid_values(payload):
    """Bereichs-/Typfehler → `invalid_format` mit Feldpfad, kein Schreibzugriff."""
    entry = _entry("e1", options={"daily_goal_ml": 2000})
    hass = _settings_hass(entry)
    connection = _admin_connection()

    asyncio.run(
        ws_api.websocket_set_settings(
            hass,
            connection,
            _settings_msg(ws_api.COMMAND_SET_SETTINGS, entry_id="e1", **payload),
        )
    )

    assert connection.results == []
    assert connection.errors[0][1] == "invalid_format"
    field = next(iter(payload))
    assert field in connection.errors[0][2]
    assert hass.config_entries.updates == []
    assert entry.options == {"daily_goal_ml": 2000}


def test_set_settings_without_any_field_sends_error():
    """Payload ohne bekanntes Feld → klarer Fehler statt stillem Erfolg."""
    entry = _entry("e1")
    hass = _settings_hass(entry)
    connection = _admin_connection()

    asyncio.run(
        ws_api.websocket_set_settings(
            hass, connection, _settings_msg(ws_api.COMMAND_SET_SETTINGS, entry_id="e1")
        )
    )

    assert connection.results == []
    assert connection.errors[0][1] == "invalid_format"
    assert "Keine Einstellung" in connection.errors[0][2]
    assert hass.config_entries.updates == []


def test_set_settings_accepts_boundary_values():
    """Grenzwerte der Bereiche sind gültig (daily_reset_hour 0/23, Schwellen)."""
    entry = _entry("e1")
    hass = _settings_hass(entry)
    connection = _admin_connection()

    asyncio.run(
        ws_api.websocket_set_settings(
            hass,
            connection,
            _settings_msg(
                ws_api.COMMAND_SET_SETTINGS,
                entry_id="e1",
                daily_reset_hour=23,
                sys_threshold=40,
                dia_threshold=260,
                retention_months=ws_api.MAX_RETENTION_MONTHS,
                daily_goal_ml=1,
            ),
        )
    )

    assert connection.errors == []
    stored = hass.config_entries.updates[0]["options"]
    assert (stored["daily_reset_hour"], stored["sys_threshold"]) == (23, 40)
    assert (stored["dia_threshold"], stored["retention_months"]) == (260, 120)


def test_set_settings_non_admin_denied_without_any_write():
    """Nicht-Admin → `unauthorized` und KEIN Options-Schreibzugriff."""
    entry = _entry("e1", options={"daily_goal_ml": 2000})
    hass = _settings_hass(entry)
    connection = FakeConnection(is_admin=False)

    asyncio.run(
        ws_api.websocket_set_settings(
            hass,
            connection,
            _settings_msg(ws_api.COMMAND_SET_SETTINGS, entry_id="e1", daily_goal_ml=3000),
        )
    )

    assert connection.results == []
    assert connection.errors[0][1] == "unauthorized"
    assert hass.config_entries.updates == []
    assert entry.options == {"daily_goal_ml": 2000}


def test_set_settings_unknown_entry_sends_error():
    """Unbekannte entry_id → `not_found`, kein Schreibzugriff."""
    entry = _entry("e1")
    hass = _settings_hass(entry)
    connection = _admin_connection()

    asyncio.run(
        ws_api.websocket_set_settings(
            hass,
            connection,
            _settings_msg(ws_api.COMMAND_SET_SETTINGS, entry_id="nope", daily_goal_ml=2500),
        )
    )

    assert connection.errors[0][1] == "not_found"
    assert hass.config_entries.updates == []


def test_parse_settings_message_ignores_non_settings_keys():
    """Nur bekannte Settings-Schlüssel werden übernommen (id/type bleiben außen vor)."""
    updates, error = ws_api.parse_settings_message(
        {"id": 1, "type": ws_api.COMMAND_SET_SETTINGS, "entry_id": "e1", "daily_goal_ml": 2500}
    )

    assert error is None
    assert updates == {"daily_goal_ml": 2500}


# --- export_csv -------------------------------------------------------------


def test_export_csv_trigger_calls_existing_service():
    """Der Trigger ruft den BESTEHENDEN Service mit Personen-Anker auf."""
    entry = _entry("e1", person="caro", display="Caro (Privat)")
    hass = _settings_hass(entry)
    connection = _admin_connection()

    asyncio.run(
        ws_api.websocket_export_csv(
            hass,
            connection,
            _settings_msg(ws_api.COMMAND_EXPORT_CSV, entry_id="e1", dataset="drinks"),
        )
    )

    assert connection.errors == []
    hass.services.async_call.assert_awaited_once_with(
        ws_api.DOMAIN,
        "export_csv",
        {"dataset": "drinks", "person": "Caro (Privat)"},
        blocking=True,
    )
    assert connection.results == [
        (
            1,
            {
                "ok": True,
                "entry_id": "e1",
                "person": "Caro (Privat)",
                "dataset": "drinks",
            },
        )
    ]


def test_export_csv_without_entry_exports_all_persons():
    """Ohne entry_id → wie der Service: alle Personen, Dataset-Default 'all'."""
    entry = _entry("e1")
    hass = _settings_hass(entry)
    connection = _admin_connection()

    asyncio.run(
        ws_api.websocket_export_csv(hass, connection, _settings_msg(ws_api.COMMAND_EXPORT_CSV))
    )

    hass.services.async_call.assert_awaited_once_with(
        ws_api.DOMAIN, "export_csv", {"dataset": "all"}, blocking=True
    )
    assert connection.results[0][1]["person"] is None
    assert connection.results[0][1]["dataset"] == "all"


def test_export_csv_unknown_dataset_sends_error():
    """Unbekannter Datensatz → `invalid_format`, kein Service-Aufruf."""
    entry = _entry("e1")
    hass = _settings_hass(entry)
    connection = _admin_connection()

    asyncio.run(
        ws_api.websocket_export_csv(
            hass,
            connection,
            _settings_msg(ws_api.COMMAND_EXPORT_CSV, entry_id="e1", dataset="pdf"),
        )
    )

    assert connection.results == []
    assert connection.errors[0][1] == "invalid_format"
    hass.services.async_call.assert_not_called()


def test_export_csv_unknown_entry_sends_error():
    """Unbekannte entry_id → `not_found`, kein Service-Aufruf."""
    entry = _entry("e1")
    hass = _settings_hass(entry)
    connection = _admin_connection()

    asyncio.run(
        ws_api.websocket_export_csv(
            hass, connection, _settings_msg(ws_api.COMMAND_EXPORT_CSV, entry_id="nope")
        )
    )

    assert connection.errors[0][1] == "not_found"
    hass.services.async_call.assert_not_called()


@pytest.mark.parametrize("exc_type", [ServiceValidationError, HomeAssistantError])
def test_export_csv_service_error_is_structured(exc_type):
    """HA-Fehler des Services → eigener, strukturierter Fehlercode."""
    entry = _entry("e1")
    hass = _settings_hass(entry)
    hass.services.async_call = AsyncMock(side_effect=exc_type("Keine Daten zum Exportieren"))
    connection = _admin_connection()

    asyncio.run(
        ws_api.websocket_export_csv(
            hass, connection, _settings_msg(ws_api.COMMAND_EXPORT_CSV, entry_id="e1")
        )
    )

    assert connection.results == []
    assert connection.errors[0][1] == "export_failed"
    assert connection.errors[0][2] == "Keine Daten zum Exportieren"


def test_export_csv_requires_admin():
    """Nicht-Admin → `unauthorized`, der Service wird nicht aufgerufen."""
    entry = _entry("e1")
    hass = _settings_hass(entry)
    connection = FakeConnection(is_admin=False)

    asyncio.run(
        ws_api.websocket_export_csv(
            hass, connection, _settings_msg(ws_api.COMMAND_EXPORT_CSV, entry_id="e1")
        )
    )

    assert connection.results == []
    assert connection.errors[0][1] == "unauthorized"
    hass.services.async_call.assert_not_called()


# --- Personen-Verwaltung: start_person_flow / delete_person / backup ---------


def test_start_person_flow_returns_flow_id():
    """`start_person_flow` startet den Config-Flow und gibt die flow_id zurück."""
    hass = _settings_hass(_entry("e1"))
    connection = _admin_connection()

    asyncio.run(
        ws_api.websocket_start_person_flow(
            hass, connection, _settings_msg(ws_api.COMMAND_START_PERSON_FLOW)
        )
    )

    assert connection.errors == []
    assert connection.results == [(1, {"flow_id": "flow-1"})]
    assert hass.config_entries.flows == [{"domain": ws_api.DOMAIN, "context": {"source": "user"}}]


def test_start_person_flow_requires_admin():
    """Nicht-Admin → `unauthorized`, kein Flow-Start."""
    hass = _settings_hass(_entry("e1"))
    connection = FakeConnection(is_admin=False)

    asyncio.run(
        ws_api.websocket_start_person_flow(
            hass, connection, _settings_msg(ws_api.COMMAND_START_PERSON_FLOW)
        )
    )

    assert connection.results == []
    assert connection.errors[0][1] == "unauthorized"
    assert hass.config_entries.flows == []


def test_start_person_flow_without_async_init_is_structured():
    """Fehlende `async_init`-API → strukturierter Fehler statt Crash."""
    hass = _settings_hass(_entry("e1"))
    hass.config_entries = SimpleNamespace()
    connection = _admin_connection()

    asyncio.run(
        ws_api.websocket_start_person_flow(
            hass, connection, _settings_msg(ws_api.COMMAND_START_PERSON_FLOW)
        )
    )

    assert connection.results == []
    assert connection.errors[0][1] == "invalid_format"


def test_start_person_flow_raising_async_init_is_structured():
    """Wirft der Flow-Start, kommt ein strukturierter Fehler statt eines Crashs."""
    hass = _settings_hass(_entry("e1"))
    connection = _admin_connection()

    async def _boom(domain, context=None):
        raise RuntimeError("flow backend down")

    hass.config_entries.async_init = _boom

    asyncio.run(
        ws_api.websocket_start_person_flow(
            hass, connection, _settings_msg(ws_api.COMMAND_START_PERSON_FLOW)
        )
    )

    assert connection.results == []
    assert connection.errors[0][1] == "invalid_format"


def test_delete_person_removes_entry_on_matching_confirmation():
    """Korrekte Bestätigung (== Slug) entfernt GENAU diesen Entry."""
    entry = _entry("e1", person="caro")
    hass = _settings_hass(entry)
    connection = _admin_connection()

    asyncio.run(
        ws_api.websocket_delete_person(
            hass,
            connection,
            _settings_msg(ws_api.COMMAND_DELETE_PERSON, entry_id="e1", confirm="caro"),
        )
    )

    assert connection.errors == []
    assert hass.config_entries.removed == ["e1"]
    assert connection.results == [(1, {"ok": True, "entry_id": "e1"})]


@pytest.mark.parametrize("confirm", ["falsch", "Caro", "", "caro "])
def test_delete_person_mismatched_confirmation_is_rejected(confirm):
    """Nicht exakt passende Bestätigung → `invalid_format`, KEIN Entfernen."""
    entry = _entry("e1", person="caro")
    hass = _settings_hass(entry)
    connection = _admin_connection()

    asyncio.run(
        ws_api.websocket_delete_person(
            hass,
            connection,
            _settings_msg(ws_api.COMMAND_DELETE_PERSON, entry_id="e1", confirm=confirm),
        )
    )

    assert connection.results == []
    assert connection.errors[0][1] == "invalid_format"
    assert hass.config_entries.removed == []


def test_delete_person_requires_admin():
    """Nicht-Admin → `unauthorized`, kein Entfernen."""
    hass = _settings_hass(_entry("e1", person="caro"))
    connection = FakeConnection(is_admin=False)

    asyncio.run(
        ws_api.websocket_delete_person(
            hass,
            connection,
            _settings_msg(ws_api.COMMAND_DELETE_PERSON, entry_id="e1", confirm="caro"),
        )
    )

    assert connection.results == []
    assert connection.errors[0][1] == "unauthorized"
    assert hass.config_entries.removed == []


def test_delete_person_unknown_entry_sends_error():
    """Unbekannte entry_id → `not_found`, kein Entfernen."""
    hass = _settings_hass(_entry("e1"))
    connection = _admin_connection()

    asyncio.run(
        ws_api.websocket_delete_person(
            hass,
            connection,
            _settings_msg(ws_api.COMMAND_DELETE_PERSON, entry_id="nope", confirm="x"),
        )
    )

    assert connection.errors[0][1] == "not_found"
    assert hass.config_entries.removed == []


def test_backup_triggers_existing_service():
    """`backup` ruft den bestehenden `health_o_mat.backup`-Service genau so auf."""
    hass = _settings_hass(_entry("e1"))
    connection = _admin_connection()

    asyncio.run(ws_api.websocket_backup(hass, connection, _settings_msg(ws_api.COMMAND_BACKUP)))

    hass.services.async_call.assert_awaited_once_with(ws_api.DOMAIN, "backup", {}, blocking=True)
    assert connection.errors == []
    assert connection.results == [(1, {"ok": True})]


def test_backup_service_error_is_structured():
    """Service-Fehler → eigener, strukturierter Fehlercode `backup_failed`."""
    hass = _settings_hass(_entry("e1"))
    hass.services.async_call = AsyncMock(side_effect=HomeAssistantError("Sicherung fehlgeschlagen"))
    connection = _admin_connection()

    asyncio.run(ws_api.websocket_backup(hass, connection, _settings_msg(ws_api.COMMAND_BACKUP)))

    assert connection.results == []
    assert connection.errors[0][1] == "backup_failed"
    assert connection.errors[0][2] == "Sicherung fehlgeschlagen"


def test_backup_requires_admin():
    """Nicht-Admin → `unauthorized`, der Service wird nicht aufgerufen."""
    hass = _settings_hass(_entry("e1"))
    connection = FakeConnection(is_admin=False)

    asyncio.run(ws_api.websocket_backup(hass, connection, _settings_msg(ws_api.COMMAND_BACKUP)))

    assert connection.results == []
    assert connection.errors[0][1] == "unauthorized"
    hass.services.async_call.assert_not_called()


# --- Admin-Gate: Alltag bleibt offen ----------------------------------------


def test_is_admin_connection_fail_closed():
    """Kein/teilweiser User → kein Admin-Recht (fail-closed)."""
    assert ws_api.is_admin_connection(FakeConnection(is_admin=True)) is True
    assert ws_api.is_admin_connection(FakeConnection(is_admin=False)) is False
    assert ws_api.is_admin_connection(FakeConnection(user_id=None)) is False
    assert ws_api.is_admin_connection(SimpleNamespace(user=None)) is False
    assert ws_api.is_admin_connection(SimpleNamespace(user=SimpleNamespace())) is False


def test_admin_only_commands_are_marked():
    """Settings/Export und Personen-Verwaltung sind admin-only — Alltag nicht."""
    assert ws_api.ADMIN_ONLY_COMMANDS == {
        ws_api.COMMAND_GET_SETTINGS,
        ws_api.COMMAND_SET_SETTINGS,
        ws_api.COMMAND_EXPORT_CSV,
        ws_api.COMMAND_START_PERSON_FLOW,
        ws_api.COMMAND_DELETE_PERSON,
        ws_api.COMMAND_BACKUP,
    }
    for command in (
        ws_api.COMMAND_BOOK_DRINK,
        ws_api.COMMAND_UNDO_LAST,
        ws_api.COMMAND_SAVE_MEASUREMENT,
        ws_api.COMMAND_SET_WELLBEING,
        ws_api.COMMAND_PANEL_DATA,
    ):
        assert command not in ws_api.ADMIN_ONLY_COMMANDS


def test_everyday_write_commands_stay_open_for_non_admins(monkeypatch):
    """Buchen/Melden funktioniert weiterhin für Nicht-Admins."""
    _now(monkeypatch)
    store = _write_store()
    coordinator = FakeCoordinator()
    hass = _write_hass(store, [_entry("e1")], {"e1": coordinator})
    connection = FakeConnection(is_admin=False)

    asyncio.run(
        ws_api.websocket_book_drink(
            hass,
            connection,
            {
                "id": 1,
                "type": ws_api.COMMAND_BOOK_DRINK,
                "entry_id": "e1",
                "ml": 250,
            },
        )
    )
    asyncio.run(
        ws_api.websocket_set_wellbeing(
            hass,
            connection,
            {"id": 2, "type": ws_api.COMMAND_SET_WELLBEING, "entry_id": "e1", "key": "good"},
        )
    )

    assert connection.errors == []
    store.add_drink.assert_awaited_once()
    store.set_wellbeing.assert_awaited_once()


def test_admin_guard_wraps_with_require_admin_when_available(monkeypatch):
    """Ist `require_admin` vorhanden, wird der (synchrone) Handler gewrappt."""
    calls: list = []

    def _fake_require_admin(handler):
        calls.append(handler)

        def _guarded(hass, connection, msg):
            return handler(hass, connection, msg)

        return _guarded

    monkeypatch.setattr(ws_api.websocket_api, "require_admin", _fake_require_admin, raising=False)
    handler = object()

    assert ws_api._admin_guard(handler) is not handler
    assert calls == [handler]


def test_admin_guard_falls_back_without_require_admin(monkeypatch):
    """Ohne `require_admin` bleibt der explizite Handler-Check die Sperre."""
    monkeypatch.delattr(ws_api.websocket_api, "require_admin", raising=False)
    handler = object()

    assert ws_api._admin_guard(handler) is handler


def test_format_lexicon_text_tolerates_broken_stored_value():
    """Unbrauchbar gespeichertes Lexikon → Standard-Lexikon (kein Crash)."""
    assert ws_api.format_lexicon_text(None).startswith("wasser=Wasser,250")
    assert ws_api.format_lexicon_text({"kaputt": "kein-paar"}).startswith("wasser=Wasser,250")
    assert ws_api.format_lexicon_text({"wasser": ["Wasser", 250]}) == "wasser=Wasser,250"


# --- REQ-HOM-112: Wohlbefinden-Score im Payload ----------------------------

# Score-Skala: 1 = schlechtester … N = bester Wert (Index + 1).
_EXPECTED_WELLBEING_SCORES = {
    "very_bad": 1,
    "awful": 2,
    "bad": 3,
    "poor": 4,
    "okay": 5,
    "mixed": 6,
    "good": 7,
    "very_good": 8,
    "great": 9,
    "excellent": 10,
}

# ENTITY_SUFFIXES vor REQ-HOM-112 — die Erweiterung muss rein ADDITIV sein
# (kein Schlüssel entfernt, kein Suffix umbenannt: das würde Entity-IDs und
# damit Automatisierungen/Dashboards zerstören).
_ENTITY_SUFFIXES_BEFORE_WELLBEING_SCORE = {
    "drinks_today": "sensor_drinks_today",
    "percent": "sensor_goal_percent",
    "lifetime": "sensor_lifetime_total",
    "bp_sys": "sensor_bp_sys",
    "bp_dia": "sensor_bp_dia",
    "bp_pulse": "sensor_bp_pulse",
    "bp_category": "sensor_bp_category",
    "wellbeing": "sensor_wellbeing_since",
    "drinks_history": "sensor_drinks_history",
    "bp_history": "sensor_bp_history",
    "drinks_trend": "sensor_drinks_trend",
    "bp_trend": "sensor_bp_trend",
    "goal_streak": "sensor_goal_streak",
    "caffeine_today": "sensor_caffeine_today",
}


@pytest.mark.parametrize(("key", "expected"), sorted(_EXPECTED_WELLBEING_SCORES.items()))
def test_req_hom_112_wellbeing_block_contains_current_score(key, expected):
    """[REQ-HOM-112] Der Wohlbefinden-Block trägt den Score der letzten Meldung."""
    block = ws_api._wellbeing_block({"wellbeing": {"status": key, "ts": "2026-10-15T10:00:00"}})

    assert block["score"] == expected
    assert block["key"] == key


def test_req_hom_112_wellbeing_block_score_is_none_without_message():
    """[REQ-HOM-112] Ohne Meldung ist der Score None (nicht 0)."""
    assert ws_api._wellbeing_block({})["score"] is None
    assert ws_api._wellbeing_block({"wellbeing": {}})["score"] is None
    assert ws_api._wellbeing_block({"wellbeing": {"status": None}})["score"] is None


def test_req_hom_112_wellbeing_block_score_is_none_for_unknown_status():
    """[REQ-HOM-112] Unbekannter Status ⇒ Score None (defensiv, kein 0)."""
    block = ws_api._wellbeing_block({"wellbeing": {"status": "super_good"}})

    assert block["score"] is None
    assert block["score"] != 0


def test_req_hom_112_wellbeing_history_entries_contain_score():
    """[REQ-HOM-112] Jeder Verlaufseintrag trägt seinen Score."""
    history = ws_api._wellbeing_history(
        [
            {"status": "very_bad", "ts": "2026-10-13T10:00:00"},
            {"status": "okay", "ts": "2026-10-14T10:00:00"},
            {"status": "great", "ts": "2026-10-15T10:00:00"},
        ]
    )

    assert [entry["score"] for entry in history] == [1, 5, 9]
    assert [entry["key"] for entry in history] == ["very_bad", "okay", "great"]


def test_req_hom_112_wellbeing_history_unknown_key_has_none_score():
    """[REQ-HOM-112] Verlaufseintrag mit unbekanntem Key ⇒ Score None (defensiv)."""
    history = ws_api._wellbeing_history([{"status": "super_good", "ts": "2026-10-15T10:00:00"}])

    assert len(history) == 1
    assert history[0]["score"] is None
    assert history[0]["score"] != 0


def test_req_hom_112_panel_data_wellbeing_block_contains_score(monkeypatch):
    """[REQ-HOM-112] `panel_data` liefert den Score im Wohlbefinden-Block."""
    entry = _entry(options={"daily_goal_ml": 2000, "daily_reset_hour": 4})
    hass = _panel_hass(_sample_store_data(), entry, _registry_entries(), monkeypatch)

    payload = ws_api.build_panel_data(hass, "e1", NOW)

    assert payload["wellbeing"]["key"] == "good"
    assert payload["wellbeing"]["score"] == 7
    assert payload["wellbeing"]["history"][0]["score"] == 5


def test_req_hom_112_panel_data_wellbeing_score_is_none_without_message(monkeypatch):
    """[REQ-HOM-112] `panel_data` ohne Meldung ⇒ Score None (nicht 0)."""
    store_data = _sample_store_data()
    store_data["e1"].pop("wellbeing")
    entry = _entry(options={"daily_goal_ml": 2000, "daily_reset_hour": 4})
    hass = _panel_hass(store_data, entry, _registry_entries(), monkeypatch)

    payload = ws_api.build_panel_data(hass, "e1", NOW)

    assert payload["wellbeing"]["key"] is None
    assert payload["wellbeing"]["score"] is None
    assert payload["wellbeing"]["score"] != 0


def test_req_hom_112_entity_suffixes_contains_wellbeing_score():
    """[REQ-HOM-112] `ENTITY_SUFFIXES` kennt den Score-Sensor (Suffix = unique_id)."""
    assert ws_api.ENTITY_SUFFIXES["wellbeing_score"] == "sensor_wellbeing_score"


def test_req_hom_112_entity_suffixes_extension_is_additive():
    """[REQ-HOM-112] Die Erweiterung ist rein additiv — alle Alt-Schlüssel bleiben.

    Ein umbenannter/entfernter Schlüssel würde die unique_id (und damit die
    Entity-ID) der Bestands-User ändern — daher explizit abgesichert.
    """
    for logical, suffix in _ENTITY_SUFFIXES_BEFORE_WELLBEING_SCORE.items():
        assert logical in ws_api.ENTITY_SUFFIXES, f"Alt-Schlüssel '{logical}' fehlt"
        assert ws_api.ENTITY_SUFFIXES[logical] == suffix, (
            f"Suffix von '{logical}' wurde geändert — unique_id/Entity-ID wäre gebrochen"
        )

    assert set(ws_api.ENTITY_SUFFIXES) == set(_ENTITY_SUFFIXES_BEFORE_WELLBEING_SCORE) | {
        "wellbeing_score"
    }


def test_panel_data_includes_wellbeing_scale_and_images(monkeypatch):
    """panel_data liefert die Skala inkl. eigener Bilder je Key."""
    entry = _entry(
        options={
            "daily_goal_ml": 2000,
            "wellbeing_images": {"good": "stufe7.png", "bogus": "x.png"},
        }
    )
    hass = _panel_hass(_sample_store_data(), entry, _registry_entries(), monkeypatch)

    payload = ws_api.build_panel_data(hass, "e1", NOW)

    assert payload is not None
    assert [item["score"] for item in payload["wellbeing_scale"]] == list(range(1, 11))
    good = next(item for item in payload["wellbeing_scale"] if item["key"] == "good")
    assert good["image"] == "/local/stufe7.png"
    assert payload["wellbeing"]["image"] == "/local/stufe7.png"
    assert all(item["key"] != "bogus" for item in payload["wellbeing_scale"])

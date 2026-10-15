"""WebSocket-API für die Health-O-Mat-Oberfläche (Card/Panel).

Lese-Kommandos, die der Frontend-Schicht die echte Bindung liefern
(docs/CONCEPT-UI.md, Abschnitt 5.2). Entities werden AUSSCHLIESSLICH über den
stabilen `unique_id`-Suffix `{entry_id}_{key}` aus der Entity-Registry
aufgelöst — nie über geratene `entity_id`s (Lehre aus ha-go-gauge: Slugs
ändern sich mit Name/Sprache, unique_ids nicht).

Die Kommandos sind idempotent registrierbar (Marker im Shared-Bereich) und
liefern für unbekannte/nicht geladene `entry_id`s einen sauberen WS-Fehler
statt eines Crashs.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from datetime import datetime
from typing import Any

import voluptuous as vol
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from . import logic
from .const import (
    DEFAULT_DAILY_GOAL_ML,
    DEFAULT_DIA_THRESHOLD,
    DEFAULT_SYS_THRESHOLD,
    DOMAIN,
    MAX_AMOUNT_ML,
    MAX_BP_VALUE,
    MIN_BP_VALUE,
    WELLBEING_STATES,
)
from .entity import effective_person, signal_refresh
from .frontend import shared_data
from .ui_store import HealthOMatUiStore

try:  # HA-Kernkomponente; Import bleibt tolerant, damit das Paket auch ohne
    # WebSocket-Komponente importierbar ist (Frontend-Ebene ist optional).
    from homeassistant.components import websocket_api
except ImportError:  # pragma: no cover - nur ohne WebSocket-Komponente
    websocket_api = None  # type: ignore[assignment]

try:  # Registry-Helfer: ein fehlendes Registry-Modul darf das Paket nicht killen.
    from homeassistant.helpers import device_registry as dr
    from homeassistant.helpers import entity_registry as er
except ImportError:  # pragma: no cover - nur ohne Registry-Module
    dr = None  # type: ignore[assignment]
    er = None  # type: ignore[assignment]

_LOGGER = logging.getLogger(__name__)

# Logischer UI-Schlüssel → unique_id-Suffix der Entity (siehe sensor.py).
ENTITY_SUFFIXES: dict[str, str] = {
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
}

# Payload-Obergrenzen (N-1: keine unbegrenzten Attribute/Payloads).
BP_ENTRIES_LIMIT = 30
WELLBEING_HISTORY_LIMIT = 30

# Toleranzband für die Pace-Bewertung (Anteil des Tagesziels).
PACE_TOLERANCE_RATIO = 0.1

WS_MARKER = "ws_api_registered"

COMMAND_LIST_PERSONS = "health_o_mat/list_persons"
COMMAND_PANEL_DATA = "health_o_mat/panel_data"
COMMAND_BOOK_DRINK = "health_o_mat/book_drink"
COMMAND_UNDO_LAST = "health_o_mat/undo_last"
COMMAND_SAVE_MEASUREMENT = "health_o_mat/save_measurement"
COMMAND_SET_WELLBEING = "health_o_mat/set_wellbeing"
COMMAND_SUBSCRIBE = "health_o_mat/subscribe"
COMMAND_GET_UI_SETTINGS = "health_o_mat/get_ui_settings"
COMMAND_SET_UI_SETTINGS = "health_o_mat/set_ui_settings"

# Untergrenze für eine Getränke-Buchung (Obergrenze ist MAX_AMOUNT_ML aus const).
MIN_DRINK_ML = 1

# Undo-Ziel-Typen (empfängt die schon normalisierte Form).
UNDO_DRINK = "drinks"
UNDO_BLOOD_PRESSURE = "blood_pressure"
_UNDO_ALIASES: dict[str, str] = {
    "drink": UNDO_DRINK,
    "drinks": UNDO_DRINK,
    "blood_pressure": UNDO_BLOOD_PRESSURE,
}

# Shared-Bereich: Lazy-Singleton des Per-User-UI-Stores.
UI_STORE_MARKER = "ui_store"
UI_STORE_LOADED_MARKER = "ui_store_loaded"

# WS-Fehlercodes (defensiv: die Konstante fehlt evtl. in Fake-/Teil-Umgebungen).
if websocket_api is not None:  # pragma: no branch - websocket_api ist fast immer da
    ERR_NOT_FOUND = getattr(websocket_api, "ERR_NOT_FOUND", "not_found")
    ERR_INVALID_FORMAT = getattr(websocket_api, "ERR_INVALID_FORMAT", "invalid_format")
    ERR_UNAUTHORIZED = getattr(websocket_api, "ERR_UNAUTHORIZED", "unauthorized")
else:  # pragma: no cover - nur ohne WS-Komponente
    ERR_NOT_FOUND = "not_found"
    ERR_INVALID_FORMAT = "invalid_format"
    ERR_UNAUTHORIZED = "unauthorized"


# --- Reine Auflösungs-/Rechenfunktionen (HA-frei testbar) -------------------


def _registry_pair(item: Any) -> tuple[str | None, str | None]:
    """(unique_id, entity_id) eines Registry-Eintrags — Dict oder Objekt."""
    if isinstance(item, dict):
        return item.get("unique_id"), item.get("entity_id")
    return getattr(item, "unique_id", None), getattr(item, "entity_id", None)


def resolve_entity_ids(entries: Iterable[Any], entry_id: str) -> dict[str, str | None]:
    """Logische Schlüssel → echte `entity_id`, aufgelöst über den unique_id-Suffix.

    Reine Funktion: Nimmt die Registry-Einträge EINES Config-Entries und bildet
    jeden in `ENTITY_SUFFIXES` definierten Schlüssel auf `{entry_id}_{suffix}`
    ab. Nicht auflösbare Entities → `None` (die UI blendet sie aus, kein Crash).
    """
    by_unique_id: dict[str, str] = {}
    for item in entries:
        unique_id, entity_id = _registry_pair(item)
        if unique_id and entity_id:
            by_unique_id[unique_id] = entity_id
    return {
        logical: by_unique_id.get(f"{entry_id}_{suffix}")
        for logical, suffix in ENTITY_SUFFIXES.items()
    }


def compute_pace(today_ml: int, goal_ml: int, now: datetime, hour: int = 0) -> str | None:
    """Grober Tages-Pace gegenüber dem linearen Soll-Verlauf (Platzhalter).

    Bewusst hier statt in `logic.py`: die im Konzept (Abschnitt 6.3) geplante
    Funktion `logic.hydration_pace` existiert noch nicht; bis dahin liefert
    diese kleine reine Vergleichsrechnung ein UI-taugliches Label
    (`goal_reached` / `ahead` / `on_track` / `behind`). `None`, wenn kein Ziel
    gesetzt ist — ohne Ziel gibt es keinen sinnvollen Soll-Verlauf.
    """
    goal = int(goal_ml)
    if goal <= 0:
        return None
    if int(today_ml) >= goal:
        return "goal_reached"
    elapsed = (now - logic.day_start(now, hour=hour)).total_seconds()
    progress = min(max(elapsed / 86400.0, 0.0), 1.0)
    expected = goal * progress
    tolerance = goal * PACE_TOLERANCE_RATIO
    if today_ml > expected + tolerance:
        return "ahead"
    if today_ml < expected - tolerance:
        return "behind"
    return "on_track"


def _as_int(value: Any, default: int) -> int:
    """Defensive Ganzzahl-Konvertierung (ungültig/fehlend → default)."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _round_or_none(value: float | None, digits: int = 1) -> float | None:
    return None if value is None else round(value, digits)


def _wellbeing_state(key: Any) -> dict | None:
    """Zustandseintrag (label/emoji) zu einem Wohlbefinden-Key."""
    for state in WELLBEING_STATES:
        if state["key"] == key:
            return state
    return None


def normalize_undo_kind(kind: Any) -> str | None:
    """Freies `kind` → kanonisches Undo-Ziel (None = unbekannt/ungültig).

    Akzeptiert die Service-Aliase (`drink`/`drinks` → Getränke,
    `blood_pressure` → Blutdruck) und behandelt fehlend/leer wie Getränke
    (Rückwärtskompatibilität zur bisherigen Service-Semantik).
    """
    if kind is None or kind == "":
        return UNDO_DRINK
    if not isinstance(kind, str):
        return None
    return _UNDO_ALIASES.get(kind.strip().lower())


def user_id_of(connection: Any) -> str | None:
    """HA-User-ID einer WebSocket-Verbindung (None, wenn anonym/nicht verfügbar)."""
    user = getattr(connection, "user", None)
    uid = getattr(user, "id", None)
    return str(uid) if uid else None


# --- Aufbau der Antwort-Payloads -------------------------------------------


def list_persons(hass: HomeAssistant) -> list[dict[str, Any]]:
    """Alle konfigurierten Personen für die Mehr-Personen-Übersicht."""
    try:
        entries = hass.config_entries.async_entries(DOMAIN)
    except Exception:  # noqa: BLE001 - Config-Entries-API defensiv
        _LOGGER.exception("Health-O-Mat: Config-Entries nicht lesbar")
        return []
    persons = [
        {
            "entry_id": entry.entry_id,
            "display_name": effective_person(entry),
            "device_id": _device_id(hass, entry.entry_id),
        }
        for entry in entries
    ]
    persons.sort(key=lambda person: person["display_name"].lower())
    return persons


def build_panel_data(hass: HomeAssistant, entry_id: str, now: datetime) -> dict[str, Any] | None:
    """Antwort-Payload für `health_o_mat/panel_data`.

    `None` = unbekannte oder nicht geladene `entry_id` (Aufrufer sendet dann
    einen WS-Fehler). Alle Werte stammen aus dem Store bzw. den HA-freien
    `logic`-Funktionen — kein Zweit-Datenmodell.
    """
    entry = _runtime_entry(hass, entry_id)
    if entry is None:
        return None
    store = _store(hass)
    data = store.all_entries().get(entry_id, {}) if store is not None else {}

    options = getattr(entry, "options", None) or {}
    reset_hour = _as_int(options.get("daily_reset_hour"), 0)
    goal_ml = _goal_ml(entry)

    drinks = data.get("drinks") or []
    readings = _sorted_readings(data.get("readings") or [])
    sums = logic.today_sums(drinks, now, hour=reset_hour)
    today_ml = int(sums["total_ml"])
    y_start, y_end = logic.yesterday_window(now, hour=reset_hour)
    yesterday_ml = int(logic.window_sums(drinks, y_start, y_end)["total_ml"])

    return {
        "entry_id": entry_id,
        "person": effective_person(entry),
        # Stabiler Service-Anker für Karten-Schreibzugriffe: `get_runtime_data`
        # matcht Service-Calls gegen `entry.data["person"]`, NICHT gegen den
        # Anzeigenamen (`person` kann per `options.person_display` abweichen).
        "person_anchor": entry.data.get("person", ""),
        "goal_ml": goal_ml,
        "reset_hour": reset_hour,
        "today": {
            "ml": today_ml,
            "percent": round(today_ml / goal_ml * 100, 1) if goal_ml > 0 else 0.0,
            "count": int(sums["count"]),
            "breakdown": dict(sums["breakdown"]),
            "yesterday_ml": yesterday_ml,
            "pace": compute_pace(today_ml, goal_ml, now, reset_hour),
        },
        "bp": _bp_block(entry, readings, now),
        "wellbeing": _wellbeing_block(data),
        "entities": entity_ids_for_entry(hass, entry_id),
    }


def _bp_block(entry: Any, readings: list[dict], now: datetime) -> dict[str, Any]:
    """Blutdruck-Block: letzte Messung, 7-Tage-Mittel, Kategorie, Warnung, Verlauf."""
    last = readings[-1] if readings else None
    sys_value = last.get("sys") if last else None
    dia_value = last.get("dia") if last else None
    return {
        "sys": sys_value,
        "dia": dia_value,
        "pulse": last.get("pulse") if last else None,
        "at": last.get("ts") if last else None,
        "avg7": {
            "sys": _round_or_none(logic.avg_over_window(readings, "sys", now)),
            "dia": _round_or_none(logic.avg_over_window(readings, "dia", now)),
            "pulse": _round_or_none(logic.avg_over_window(readings, "pulse", now)),
        },
        "category": logic.bp_category(sys_value, dia_value) if last else None,
        "warning": _above_threshold(entry, sys_value, dia_value),
        "entries": [dict(reading) for reading in readings[-BP_ENTRIES_LIMIT:]],
    }


def _above_threshold(entry: Any, systolic: Any, diastolic: Any) -> bool:
    """True, wenn die übergebene (letzte) Messung oberhalb einer Schwelle liegt."""
    if systolic is None and diastolic is None:
        return False
    sys_threshold = _runtime_int(entry, "sys_threshold", DEFAULT_SYS_THRESHOLD)
    dia_threshold = _runtime_int(entry, "dia_threshold", DEFAULT_DIA_THRESHOLD)
    return _is_above(systolic, sys_threshold) or _is_above(diastolic, dia_threshold)


def _is_above(value: Any, threshold: int) -> bool:
    """Defensiver `>`-Vergleich (None/ungültig → False)."""
    if value is None:
        return False
    try:
        return int(value) > int(threshold)
    except (TypeError, ValueError):
        return False


def _wellbeing_block(data: dict) -> dict[str, Any]:
    """Wohlbefinden-Block: letzte Meldung (Key/Label/Emoji/Zeitpunkt) + Verlauf."""
    current = data.get("wellbeing") or {}
    key = current.get("status") or None
    state = _wellbeing_state(key) or {}
    return {
        "key": key,
        "label": state.get("label"),
        "emoji": state.get("emoji"),
        "at": current.get("ts") or None,
        "history": _wellbeing_history(data.get("wellbeing_history")),
    }


def _wellbeing_history(items: Any) -> list[dict[str, Any]]:
    """Letzte Meldungen des Verlaufs, angereichert mit Label/Emoji."""
    if not isinstance(items, list):
        return []
    history: list[dict[str, Any]] = []
    for item in items[-WELLBEING_HISTORY_LIMIT:]:
        if not isinstance(item, dict):
            continue
        key = item.get("status")
        if not key:
            continue
        state = _wellbeing_state(key) or {}
        history.append(
            {
                "key": key,
                "label": state.get("label"),
                "emoji": state.get("emoji"),
                "ts": item.get("ts"),
            }
        )
    return history


# --- HA-Zugriffe (defensiv) -------------------------------------------------


def _runtime_entry(hass: HomeAssistant, entry_id: str) -> Any | None:
    """Config-Entry einer LAUFENDEN Person (None = unbekannt/nicht geladen)."""
    registry = hass.data.get(DOMAIN)
    if not isinstance(registry, dict):
        return None
    info = registry.get(entry_id)
    if not isinstance(info, dict) or "coordinator" not in info:
        return None
    try:
        return hass.config_entries.async_get_entry(entry_id)
    except Exception:  # noqa: BLE001 - Config-Entries-API defensiv
        _LOGGER.exception("Health-O-Mat: Config-Entry %s nicht lesbar", entry_id)
        return None


def _store(hass: HomeAssistant) -> Any | None:
    """Shared-Store (None, wenn die Integration noch nicht geladen ist)."""
    registry = hass.data.get(DOMAIN)
    if not isinstance(registry, dict):
        return None
    shared = registry.get("shared")
    if not isinstance(shared, dict):
        return None
    return shared.get("store")


def _registry(hass: HomeAssistant) -> dict[str, Any]:
    """Runtime-Registry der Integration (leer, wenn nicht geladen)."""
    registry = hass.data.get(DOMAIN)
    return registry if isinstance(registry, dict) else {}


def _coordinator(hass: HomeAssistant, entry_id: str) -> Any | None:
    """Coordinator einer geladenen Person (None = unbekannt/nicht geladen)."""
    info = _registry(hass).get(entry_id)
    if isinstance(info, dict):
        return info.get("coordinator")
    return None


def _entry_ready(hass: HomeAssistant, entry_id: str) -> bool:
    """True, wenn `entry_id` zu einer geladenen Person mit Coordinator gehört."""
    return _coordinator(hass, entry_id) is not None


def _send_entry_error(connection: Any, msg: dict[str, Any], entry_id: str) -> None:
    """Sauberer WS-Fehler für eine unbekannte/nicht geladene Person."""
    connection.send_error(
        msg["id"],
        ERR_NOT_FOUND,
        f"Unbekannte oder nicht geladene Person: {entry_id}",
    )


async def _ui_store(hass: HomeAssistant) -> HealthOMatUiStore:
    """Per-User-UI-Store lazily anlegen/laden (idempotent, pro Prozess einmal)."""
    shared = shared_data(hass)
    store = shared.get(UI_STORE_MARKER)
    if store is None:
        store = HealthOMatUiStore(hass)
        shared[UI_STORE_MARKER] = store
    if not shared.get(UI_STORE_LOADED_MARKER):
        await store.async_load()
        shared[UI_STORE_LOADED_MARKER] = True
    return store


def _device_id(hass: HomeAssistant, entry_id: str) -> str | None:
    """Device-ID des Personen-Devices (None, wenn nicht vorhanden)."""
    if dr is None:  # pragma: no cover - nur ohne Device-Registry
        return None
    try:
        devices = dr.async_entries_for_config_entry(dr.async_get(hass), entry_id)
    except Exception:  # noqa: BLE001 - Device-Registry optional/versionsabhängig
        return None
    return devices[0].id if devices else None


def entity_ids_for_entry(hass: HomeAssistant, entry_id: str) -> dict[str, str | None]:
    """Logische Schlüssel → `entity_id` für einen Config-Entry (Registry-Lookup)."""
    if er is None:  # pragma: no cover - nur ohne Entity-Registry
        return dict.fromkeys(ENTITY_SUFFIXES)
    try:
        entries = er.async_entries_for_config_entry(er.async_get(hass), entry_id)
    except Exception:  # noqa: BLE001 - Entity-Registry optional/versionsabhängig
        _LOGGER.exception("Health-O-Mat: Entity-Registry nicht lesbar")
        return dict.fromkeys(ENTITY_SUFFIXES)
    return resolve_entity_ids(entries, entry_id)


def _sorted_readings(readings: Iterable[dict]) -> list[dict]:
    """Messungen nach Zeitstempel sortiert (ungültige ts sortieren nach vorn)."""
    return sorted(
        (reading for reading in readings if isinstance(reading, dict)),
        key=lambda reading: str(reading.get("ts") or ""),
    )


def _goal_ml(entry: Any) -> int:
    """Tagesziel in ml: Runtime-Spiegel, sonst Options, sonst Default."""
    runtime_goal = getattr(getattr(entry, "runtime_data", None), "daily_goal_ml", None)
    if runtime_goal:
        return _as_int(runtime_goal, DEFAULT_DAILY_GOAL_ML)
    options = getattr(entry, "options", None) or {}
    return _as_int(options.get("daily_goal_ml"), DEFAULT_DAILY_GOAL_ML)


def _runtime_int(entry: Any, attribute: str, default: int) -> int:
    """Ganzzahliger Runtime-Wert (z. B. BP-Schwelle) mit Default."""
    value = getattr(getattr(entry, "runtime_data", None), attribute, None)
    return default if value is None else _as_int(value, default)


# --- WebSocket-Kommandos ----------------------------------------------------


async def async_register_ws_api(hass: HomeAssistant) -> None:
    """Registriert die Kommandos genau EINMAL pro HA-Prozess (idempotent).

    Registrierung in der expliziten Form (`async_register_command` mit
    Handler + Schema) statt per Dekorator: so bleibt dieses Modul auch ohne
    importierbare WebSocket-Komponente ladbar. `async_response` wrappt die
    Coroutinen in den vom WS-Dispatcher erwarteten (synchronen) Handler.
    """
    if websocket_api is None:  # pragma: no cover - nur ohne WS-Komponente
        _LOGGER.warning("Health-O-Mat: WebSocket-Komponente fehlt — Karte ohne Live-Daten")
        return
    shared = shared_data(hass)
    if shared.get(WS_MARKER):
        return

    def _schema(command: str, extra: dict[Any, Any]) -> Any:
        return websocket_api.BASE_COMMAND_MESSAGE_SCHEMA.extend(
            {vol.Required("type"): command, **extra}
        )

    commands: tuple[tuple[str, Any, dict[Any, Any]], ...] = (
        (COMMAND_LIST_PERSONS, websocket_list_persons, {}),
        (COMMAND_PANEL_DATA, websocket_panel_data, {vol.Required("entry_id"): str}),
        (
            COMMAND_BOOK_DRINK,
            websocket_book_drink,
            {
                vol.Required("entry_id"): str,
                vol.Required("ml"): vol.All(
                    vol.Coerce(int), vol.Range(min=MIN_DRINK_ML, max=MAX_AMOUNT_ML)
                ),
                vol.Optional("drink_type"): str,
            },
        ),
        (
            COMMAND_UNDO_LAST,
            websocket_undo_last,
            {vol.Required("entry_id"): str, vol.Optional("kind"): str},
        ),
        (
            COMMAND_SAVE_MEASUREMENT,
            websocket_save_measurement,
            {
                vol.Required("entry_id"): str,
                vol.Required("sys"): vol.All(
                    vol.Coerce(int), vol.Range(min=MIN_BP_VALUE, max=MAX_BP_VALUE)
                ),
                vol.Required("dia"): vol.All(
                    vol.Coerce(int), vol.Range(min=MIN_BP_VALUE, max=MAX_BP_VALUE)
                ),
                vol.Optional("pulse"): vol.Coerce(int),
                vol.Optional("note"): str,
            },
        ),
        (
            COMMAND_SET_WELLBEING,
            websocket_set_wellbeing,
            {vol.Required("entry_id"): str, vol.Required("key"): str},
        ),
        (COMMAND_SUBSCRIBE, websocket_subscribe, {vol.Optional("entry_id"): str}),
        (COMMAND_GET_UI_SETTINGS, websocket_get_ui_settings, {}),
        (
            COMMAND_SET_UI_SETTINGS,
            websocket_set_ui_settings,
            {
                vol.Optional("selected_person"): vol.Any(str, None),
                vol.Optional("prefs"): dict,
            },
        ),
    )
    for command, handler, extra in commands:
        websocket_api.async_register_command(
            hass, command, websocket_api.async_response(handler), _schema(command, extra)
        )
    shared[WS_MARKER] = True


async def websocket_list_persons(hass: HomeAssistant, connection: Any, msg: dict[str, Any]) -> None:
    """`health_o_mat/list_persons` → alle Personen mit Anzeigename und Device-ID."""
    connection.send_result(msg["id"], {"persons": list_persons(hass)})


async def websocket_panel_data(hass: HomeAssistant, connection: Any, msg: dict[str, Any]) -> None:
    """`health_o_mat/panel_data` → kompletter Karten-Payload einer Person."""
    entry_id = msg["entry_id"]
    payload = build_panel_data(hass, entry_id, dt_util.now())
    if payload is None:
        code = websocket_api.ERR_NOT_FOUND if websocket_api is not None else "not_found"
        connection.send_error(
            msg["id"],
            code,
            f"Unbekannte oder nicht geladene Person: {entry_id}",
        )
        return
    connection.send_result(msg["id"], payload)


# --- Schreibkommandos (Panel, L2) -------------------------------------------
# Alle Schreiber laufen über DIESELBEN Store-Methoden und denselben
# Signalweg (`signal_refresh`) wie die Services — kein Zweitweg für Daten.


async def websocket_book_drink(hass: HomeAssistant, connection: Any, msg: dict[str, Any]) -> None:
    """`health_o_mat/book_drink` → Getränk buchen (ml 1..MAX_AMOUNT_ML)."""
    entry_id = msg["entry_id"]
    store = _store(hass)
    if store is None or not _entry_ready(hass, entry_id):
        _send_entry_error(connection, msg, entry_id)
        return
    ml = _as_int(msg.get("ml"), 0)
    if ml < MIN_DRINK_ML or ml > MAX_AMOUNT_ML:
        connection.send_error(
            msg["id"],
            ERR_INVALID_FORMAT,
            f"ml muss zwischen {MIN_DRINK_ML} und {MAX_AMOUNT_ML} liegen",
        )
        return
    await store.add_drink(
        entry_id,
        dt_util.now().isoformat(),
        ml,
        msg.get("drink_type") or "Eigen",
        "panel",
    )
    signal_refresh(hass, entry_id)
    connection.send_result(msg["id"])


async def websocket_undo_last(hass: HomeAssistant, connection: Any, msg: dict[str, Any]) -> None:
    """`health_o_mat/undo_last` → letzten Eintrag entfernen (drinks|blood_pressure)."""
    entry_id = msg["entry_id"]
    store = _store(hass)
    if store is None or not _entry_ready(hass, entry_id):
        _send_entry_error(connection, msg, entry_id)
        return
    kind = normalize_undo_kind(msg.get("kind"))
    if kind is None:
        connection.send_error(
            msg["id"],
            ERR_INVALID_FORMAT,
            f"Unbekannter kind: {msg.get('kind')!r} (erlaubt: drinks, blood_pressure)",
        )
        return
    if kind == UNDO_BLOOD_PRESSURE:
        removed = await store.remove_last_reading(entry_id)
        what = "Blutdruckmessungen"
    else:
        removed = await store.remove_last_drink(entry_id)
        what = "Getränke"
    if not removed:
        connection.send_error(msg["id"], ERR_NOT_FOUND, f"Keine {what} zum Entfernen")
        return
    signal_refresh(hass, entry_id)
    connection.send_result(msg["id"])


async def websocket_save_measurement(
    hass: HomeAssistant, connection: Any, msg: dict[str, Any]
) -> None:
    """`health_o_mat/save_measurement` → Blutdruckmessung speichern."""
    entry_id = msg["entry_id"]
    store = _store(hass)
    if store is None or not _entry_ready(hass, entry_id):
        _send_entry_error(connection, msg, entry_id)
        return
    sys_value = _as_int(msg.get("sys"), 0)
    dia_value = _as_int(msg.get("dia"), 0)
    if not (MIN_BP_VALUE <= sys_value <= MAX_BP_VALUE) or not (
        MIN_BP_VALUE <= dia_value <= MAX_BP_VALUE
    ):
        connection.send_error(
            msg["id"],
            ERR_INVALID_FORMAT,
            f"sys/dia müssen zwischen {MIN_BP_VALUE} und {MAX_BP_VALUE} liegen",
        )
        return
    pulse = msg.get("pulse")
    await store.add_reading(
        entry_id,
        dt_util.now().isoformat(),
        sys_value,
        dia_value,
        int(pulse) if pulse is not None else None,
        msg.get("note") or "",
        "panel",
    )
    signal_refresh(hass, entry_id)
    connection.send_result(msg["id"])


async def websocket_set_wellbeing(
    hass: HomeAssistant, connection: Any, msg: dict[str, Any]
) -> None:
    """`health_o_mat/set_wellbeing` → Wohlbefinden melden (Key-validiert)."""
    entry_id = msg["entry_id"]
    store = _store(hass)
    if store is None or not _entry_ready(hass, entry_id):
        _send_entry_error(connection, msg, entry_id)
        return
    key = msg.get("key")
    if _wellbeing_state(key) is None:
        connection.send_error(msg["id"], ERR_INVALID_FORMAT, f"Unbekannter Wohlbefinden-Key: {key}")
        return
    await store.set_wellbeing(entry_id, key, dt_util.now().isoformat())
    signal_refresh(hass, entry_id)
    connection.send_result(msg["id"])


# --- Live-Subscription ------------------------------------------------------


def _wait_for_refresh(connection: Any, msg_id: int, entry_id: str, coordinator: Any) -> Any:
    """Coordinator-Listener, der jeder Refresh als `refresh`-Event pusht."""

    def _on_update() -> None:
        connection.send_event(msg_id, {"type": "refresh", "entry_id": entry_id})

    return coordinator.async_add_listener(_on_update)


def _unsubscriber(removers: list[Any]) -> Any:
    """Sammel-Unsubscribe für eine Subscription (defensiv/idempotent)."""

    def _unsubscribe() -> None:
        for remove in removers:
            try:
                remove()
            except Exception:  # noqa: BLE001 - Abmelden ist nie kritisch
                _LOGGER.debug("Health-O-Mat: WS-Listener nicht abmeldbar", exc_info=True)

    return _unsubscribe


async def websocket_subscribe(hass: HomeAssistant, connection: Any, msg: dict[str, Any]) -> None:
    """`health_o_mat/subscribe` → Live-Refresh-Events für eine/alle Personen."""
    entry_id = msg.get("entry_id")
    if entry_id is not None:
        if not _entry_ready(hass, entry_id):
            _send_entry_error(connection, msg, entry_id)
            return
        targets = [(entry_id, _coordinator(hass, entry_id))]
    else:
        targets = [
            (key, info.get("coordinator"))
            for key, info in _registry(hass).items()
            if isinstance(info, dict) and info.get("coordinator") is not None
        ]
    removers = [
        _wait_for_refresh(connection, msg["id"], key, coordinator) for key, coordinator in targets
    ]
    connection.subscriptions[msg["id"]] = _unsubscriber(removers)
    connection.send_result(msg["id"])


# --- UI-Einstellungen je HA-Nutzer ------------------------------------------


async def websocket_get_ui_settings(
    hass: HomeAssistant, connection: Any, msg: dict[str, Any]
) -> None:
    """`health_o_mat/get_ui_settings` → gespeicherte Settings des HA-Nutzers."""
    store = await _ui_store(hass)
    connection.send_result(msg["id"], store.get(user_id_of(connection)))


async def websocket_set_ui_settings(
    hass: HomeAssistant, connection: Any, msg: dict[str, Any]
) -> None:
    """`health_o_mat/set_ui_settings` → Settings des HA-Nutzers persistieren."""
    user_id = user_id_of(connection)
    if user_id is None:
        connection.send_error(msg["id"], ERR_UNAUTHORIZED, "Kein angemeldeter Benutzer")
        return
    store = await _ui_store(hass)
    updates: dict[str, Any] = {}
    if "selected_person" in msg:
        updates["selected_person"] = msg["selected_person"]
    if "prefs" in msg:
        updates["prefs"] = msg["prefs"]
    connection.send_result(msg["id"], await store.async_set(user_id, **updates))

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
from collections.abc import Iterable, Mapping
from datetime import datetime
from typing import Any

import voluptuous as vol
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.util import dt as dt_util

from . import logic, parser
from .areas import AREAS, OPTION_AREAS, active_areas
from .const import (
    DEFAULT_DAILY_GOAL_ML,
    DEFAULT_DIA_THRESHOLD,
    DEFAULT_QUICK_DRINKS,
    DEFAULT_RETENTION_MONTHS,
    DEFAULT_SYS_THRESHOLD,
    DOMAIN,
    DRINK_LEXICON,
    MAX_AMOUNT_ML,
    MAX_BP_VALUE,
    MAX_RETENTION_MONTHS,
    MIN_BP_VALUE,
    OPTION_WELLBEING_CONFIRM,
    WELLBEING_IMAGES_OPTION,
    WELLBEING_STATES,
)
from .entity import effective_person, signal_refresh
from .frontend import shared_data
from .panel import OPTION_ENABLE_SIDEBAR_PANEL
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
    # Rein additiv (keine bestehenden Schlüssel umbenannt/entfernt): kompakte
    # Karten-Zusatzwerte. Die Sensoren existieren bereits (REQ-HOM-002/003/004).
    "drinks_trend": "sensor_drinks_trend",
    "bp_trend": "sensor_bp_trend",
    "goal_streak": "sensor_goal_streak",
    "caffeine_today": "sensor_caffeine_today",
    # Rein additiv (REQ-HOM-112): numerischer Wohlbefinden-Score.
    "wellbeing_score": "sensor_wellbeing_score",
}

# Payload-Obergrenzen (N-1: keine unbegrenzten Attribute/Payloads).
BP_ENTRIES_LIMIT = 30
WELLBEING_HISTORY_LIMIT = 30

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
COMMAND_GET_SETTINGS = "health_o_mat/get_settings"
COMMAND_SET_SETTINGS = "health_o_mat/set_settings"
COMMAND_EXPORT_CSV = "health_o_mat/export_csv"
COMMAND_START_PERSON_FLOW = "health_o_mat/start_person_flow"
COMMAND_DELETE_PERSON = "health_o_mat/delete_person"
COMMAND_BACKUP = "health_o_mat/backup"

# Admin-only (Konzept §8.4, Entscheidung 4): Settings lesen/schreiben und
# Export sind Verwaltungsvorgänge. Die Alltags-Schreibkommandos
# (book_drink/undo_last/save_measurement/set_wellbeing) bleiben für ALLE
# angemeldeten User offen — bewusst KEIN Admin-Gate dort.
ADMIN_ONLY_COMMANDS: frozenset[str] = frozenset(
    {
        COMMAND_GET_SETTINGS,
        COMMAND_SET_SETTINGS,
        COMMAND_EXPORT_CSV,
        COMMAND_START_PERSON_FLOW,
        COMMAND_DELETE_PERSON,
        COMMAND_BACKUP,
    }
)

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

# Eigener Fehlercode: der bestehende `export_csv`-Service meldet fachliche
# Probleme als `ServiceValidationError` (z. B. „Keine Daten zum Exportieren").
ERR_EXPORT_FAILED = "export_failed"
ERR_BACKUP_FAILED = "backup_failed"


# --- Admin-/Settings-Kommandos (L3, Konzept §4.5/§8.4) ---------------------
# Persistenz läuft AUSSCHLIESSLICH über `async_update_entry(entry, options=…)`
# (löst den bestehenden Options-Listener `_options_updated` aus) bzw. über den
# bestehenden `health_o_mat.export_csv`-Service — kein Zweitweg, kein direkter
# Runtime-Schreibzugriff.

# Options-Schlüssel, die die Admin-Maske liest/schreibt — exakt die Schlüssel
# des Options-Flows (config_flow.py), inkl. `enable_sidebar_panel` aus panel.py.
SETTINGS_KEYS: tuple[str, ...] = (
    "daily_goal_ml",
    "daily_reset_hour",
    "person_display",
    "quick_drinks",
    "drink_lexicon",
    WELLBEING_IMAGES_OPTION,
    OPTION_WELLBEING_CONFIRM,
    "sys_threshold",
    "dia_threshold",
    "retention_months",
    OPTION_ENABLE_SIDEBAR_PANEL,
    OPTION_AREAS,
)

# Datensätze des bestehenden `health_o_mat.export_csv`-Service (services.yaml).
EXPORT_DATASETS: tuple[str, ...] = ("drinks", "blood_pressure", "all")
DEFAULT_EXPORT_DATASET = "all"

DEFAULT_QUICK_DRINK_ICON = "mdi:cup-water"


def _any_value(value: Any) -> Any:
    """Passthrough-Validator für die WS-Whitelist der Settings-Kommandos.

    HA-WebSocket-Schemas sind `PREVENT_EXTRA`, unbekannte Felder werden also
    schon am Transportrand abgewiesen. Die WERTE werden bewusst nicht hier,
    sondern feldgenau in `parse_settings_message()` geprüft — nur so gibt es
    präzise Meldungen (Feldpfad, Lexikon-Zeilennummer) statt generischer
    Schema-Fehler.
    """
    return value


def _strict_bool(value: Any) -> bool:
    """Strikter Boolean-Validator für Options-Schalter.

    `vol.Boolean()` bzw. `vol.Coerce(bool)` würden `"true"`, `"false"` und
    `1`/`0` stillschweigend umwandeln. Für Options-Schalter ist das eine
    stille Verhaltensänderung — deshalb akzeptiert dieser Validator
    ausschließlich echte JSON-Booleans.
    """
    if isinstance(value, bool):
        return value
    raise vol.Invalid(
        f"erwartet true oder false (Boolean), erhalten {type(value).__name__} {value!r}"
    )


# Feldgenaue Validierung eines `set_settings`-Payloads.
SETTINGS_SCHEMA = vol.Schema(
    {
        vol.Optional("daily_goal_ml"): vol.All(vol.Coerce(int), vol.Range(min=1)),
        vol.Optional("daily_reset_hour"): vol.All(vol.Coerce(int), vol.Range(min=0, max=23)),
        vol.Optional("person_display"): str,
        # Quick-Drinks: dieselben 4 Felder, die der Options-Flow schreibt
        # (config_flow.quick_drinks_from_user_input) — gleiche Repräsentation.
        vol.Optional("quick_drinks"): vol.All(
            [
                vol.Schema(
                    {
                        vol.Required("key"): str,
                        vol.Required("label"): str,
                        vol.Required("ml"): vol.All(
                            vol.Coerce(int), vol.Range(min=MIN_DRINK_ML, max=MAX_AMOUNT_ML)
                        ),
                        vol.Optional("icon", default=DEFAULT_QUICK_DRINK_ICON): str,
                    }
                )
            ],
            vol.Length(min=1),
        ),
        # Eigene Wellbeing-Bilder: optionale Map key -> URL/Pfad. Die
        # Normalisierung (nur erlaubte Keys/Formate) passiert in
        # `parse_settings_message` über `logic.normalize_wellbeing_images`.
        vol.Optional(WELLBEING_IMAGES_OPTION): dict,
        # Wohlbefinden-Bestätigung (REQ-HOM-114): STRIKT bool, kein Coerce —
        # `vol.Boolean()` würde "true"/1 akzeptieren und still umdeuten.
        vol.Optional(OPTION_WELLBEING_CONFIRM): _strict_bool,
        vol.Optional("sys_threshold"): vol.All(
            vol.Coerce(int), vol.Range(min=MIN_BP_VALUE, max=MAX_BP_VALUE)
        ),
        vol.Optional("dia_threshold"): vol.All(
            vol.Coerce(int), vol.Range(min=MIN_BP_VALUE, max=MAX_BP_VALUE)
        ),
        # Retention: 0 = AUS (exakt bisheriges Verhalten, REQ-HOM-109).
        vol.Optional("retention_months"): vol.All(
            vol.Coerce(int), vol.Range(min=0, max=MAX_RETENTION_MONTHS)
        ),
        vol.Optional(OPTION_ENABLE_SIDEBAR_PANEL): vol.Boolean(),
        vol.Optional(OPTION_AREAS): vol.Schema(
            {vol.Optional(area): vol.Boolean() for area in AREAS}
        ),
    }
)


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


def pace_label(pace: dict[str, Any], today_ml: int, goal_ml: int) -> str | None:
    """UI-Pace-String aus dem `logic.hydration_pace`-Ergebnis (stabiler Vertrag).

    Das L2-Panel-JS liest `today.pace` als STRING mit den Werten
    `goal_reached` | `ahead` | `on_track` | `behind` (oder `None` ohne Ziel).
    `goal_reached` wird hier vergeben (`actual_ml >= goal_ml`), die Logik-Schicht
    liefert nur ahead/on_track/behind. Ohne (positives) Ziel → None.
    """
    if goal_ml <= 0:
        return None
    if today_ml >= goal_ml:
        return "goal_reached"
    status = pace.get("status")
    return status if isinstance(status, str) else None


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
    """Alle konfigurierten Personen für die Mehr-Personen-Übersicht.

    `person_slug` ist der STABILE Deep-Link-Anker (`entry.data["person"]`) und
    `areas` die aktivierten Feature-Flächen — beides additiv zum bestehenden
    Vertrag (entry_id/display_name/device_id).
    """
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
            "person_slug": entry.data.get("person", ""),
            "areas": active_areas(getattr(entry, "options", None)),
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
    # Aktive Sicht: voided Einträge erscheinen weder in today/bp/wellbeing noch
    # in der Undo-Verfügbarkeit (M2a). Rohdaten bleiben dem Schreibpfad/Backup
    # vorbehalten.
    data = store.active_entry(entry_id) if store is not None else {}

    options = getattr(entry, "options", None) or {}
    reset_hour = _as_int(options.get("daily_reset_hour"), 0)
    goal_ml = _goal_ml(entry)

    drinks = data.get("drinks") or []
    readings = _sorted_readings(data.get("readings") or [])
    sums = logic.today_sums(drinks, now, hour=reset_hour)
    today_ml = int(sums["total_ml"])
    y_start, y_end = logic.yesterday_window(now, hour=reset_hour)
    yesterday_ml = int(logic.window_sums(drinks, y_start, y_end)["total_ml"])
    pace = logic.hydration_pace(drinks, now, goal_ml, hour=reset_hour)

    return {
        "entry_id": entry_id,
        "person": effective_person(entry),
        "person_slug": entry.data.get("person", ""),
        "areas": active_areas(options),
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
            # String-Label (stabiler UI-Vertrag) + additive Detailwerte aus
            # `logic.hydration_pace` (neue Keys, nichts Bestehendes umbenannt).
            "pace": pace_label(pace, today_ml, goal_ml),
            "expected_ml": pace["expected_ml"],
            "delta_ml": pace["delta_ml"],
            "forecast_ml": pace["forecast_ml"],
        },
        # Additiv: Undo-Verfügbarkeit, damit die UI den Button deaktivieren
        # kann, statt einen Service-/WS-Fehler ("keine Getränke") auszulösen.
        # `data` ist die aktive Sicht — voided Einträge zählen hier nicht (M2a).
        "undo": {
            "drink": bool(data.get("drinks")),
            "blood_pressure": bool(readings),
        },
        "bp": _bp_block(entry, readings, now),
        "wellbeing": _wellbeing_block(data, entry),
        # Additiv: die vollständige Skala inkl. eigener Bilder, damit Karte und
        # Panel dieselbe Quelle nutzen (Label/Emoji/Bild je Key).
        "wellbeing_scale": logic.wellbeing_scale(_wellbeing_images(entry)),
        # Additiv: die konfigurierten Quick-Drinks, damit Karte und Editor die
        # Auswahl kennen, ohne das admin-only `get_settings` aufzurufen.
        "quick_drinks": _quick_drinks(entry),
        # Additiv (REQ-HOM-114): Bestätigung vor der Übernahme einer
        # Wohlbefinden-Meldung — der Detail-Tab braucht die Option, ohne das
        # admin-only `get_settings` aufzurufen.
        OPTION_WELLBEING_CONFIRM: bool(options.get(OPTION_WELLBEING_CONFIRM, False)),
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


def _wellbeing_images(entry: Any) -> dict[str, str]:
    """Normalisierte eigene Wellbeing-Bilder aus den Entry-Options."""
    options = getattr(entry, "options", None) or {}
    return logic.normalize_wellbeing_images(options.get(WELLBEING_IMAGES_OPTION))


def _wellbeing_block(data: dict, entry: Any = None) -> dict[str, Any]:
    """Wohlbefinden-Block: letzte Meldung (Key/Label/Emoji/Bild) + Verlauf."""
    current = data.get("wellbeing") or {}
    key = current.get("status") or None
    state = _wellbeing_state(key) or {}
    images = _wellbeing_images(entry) if entry is not None else {}
    return {
        "key": key,
        "label": state.get("label"),
        "emoji": state.get("emoji"),
        "image": images.get(key),
        "at": current.get("ts") or None,
        # Rein additiv (REQ-HOM-112): numerischer Score zur aktuellen Meldung.
        "score": logic.wellbeing_score(key),
        "scale_max": len(WELLBEING_STATES),
        "history": _wellbeing_history(data.get("wellbeing_history"), images),
    }


def _wellbeing_history(items: Any, images: dict[str, str] | None = None) -> list[dict[str, Any]]:
    """Letzte Meldungen des Verlaufs, angereichert mit Label/Emoji/Bild."""
    if not isinstance(items, list):
        return []
    images = images or {}
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
                "image": images.get(key),
                # Rein additiv (REQ-HOM-112): Score je Verlaufseintrag.
                "score": logic.wellbeing_score(key),
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
            {
                vol.Required("entry_id"): str,
                vol.Optional("key"): str,
                vol.Optional("score"): vol.Coerce(int),
            },
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
        (COMMAND_GET_SETTINGS, websocket_get_settings, {vol.Required("entry_id"): str}),
        (
            COMMAND_SET_SETTINGS,
            websocket_set_settings,
            {
                vol.Required("entry_id"): str,
                # Whitelist statt Vorab-Validierung: HA-Schemas sind PREVENT_EXTRA,
                # die Feldprüfung passiert feldgenau in `parse_settings_message`
                # (präzise Meldungen inkl. Lexikon-Zeilennummer).
                **{vol.Optional(key): _any_value for key in SETTINGS_KEYS},
            },
        ),
        (
            COMMAND_EXPORT_CSV,
            websocket_export_csv,
            {vol.Optional("entry_id"): str, vol.Optional("dataset"): _any_value},
        ),
        (COMMAND_START_PERSON_FLOW, websocket_start_person_flow, {}),
        (
            COMMAND_DELETE_PERSON,
            websocket_delete_person,
            {vol.Required("entry_id"): str, vol.Required("confirm"): str},
        ),
        (COMMAND_BACKUP, websocket_backup, {}),
    )
    for command, handler, extra in commands:
        wrapped = websocket_api.async_response(handler)
        if command in ADMIN_ONLY_COMMANDS:
            # HAs `require_admin` ist ein SYNCHRONER Wrapper und ruft den inneren
            # Handler ohne `await` — die Reihenfolge ist deshalb zwingend
            # `require_admin(async_response(handler))` (umgekehrt erzeugt
            # `async_response` einen Task für `None`).
            wrapped = _admin_guard(wrapped)
        websocket_api.async_register_command(hass, command, wrapped, _schema(command, extra))
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
    """`health_o_mat/set_wellbeing` → Wohlbefinden per Key ODER Score melden."""
    entry_id = msg["entry_id"]
    store = _store(hass)
    if store is None or not _entry_ready(hass, entry_id):
        _send_entry_error(connection, msg, entry_id)
        return
    key = msg.get("key")
    score = msg.get("score")
    if key is None and score is None:
        connection.send_error(msg["id"], ERR_INVALID_FORMAT, "Entweder 'key' oder 'score' angeben")
        return
    if key is None:
        key = logic.wellbeing_key_for_score(score)
        if key is None:
            connection.send_error(
                msg["id"],
                ERR_INVALID_FORMAT,
                f"Ungültiger Wohlbefinden-Score: {score} (erlaubt: 1 bis {len(WELLBEING_STATES)})",
            )
            return
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


# --- Admin/Settings + Export (L3) -------------------------------------------
# Schreibrechte (Konzept §8.4, Entscheidung 4): Settings/Export admin-only,
# Alltag (Buchen/Melden) für alle. Die Sperre sitzt doppelt: HA-seitig als
# `require_admin`-Wrapper (falls die installierte HA-Version ihn anbietet) und
# im Handler als expliziter `connection.user.is_admin`-Check — fail-closed,
# damit auch Umgebungen ohne `require_admin` (Fake-/Teil-Stacks) geschützt sind.


def is_admin_connection(connection: Any) -> bool:
    """True nur bei angemeldetem User mit `is_admin` (fehlend/None → False)."""
    user = getattr(connection, "user", None)
    if user is None:
        return False
    return bool(getattr(user, "is_admin", False))


def _admin_guard(handler: Any) -> Any:
    """Wrappt einen (bereits synchronen) Handler in HAs `require_admin`.

    Fehlt `require_admin` (ältere HA-Version, Fake-Umgebung), bleibt der
    explizite Check in den Handlern die wirksame Sperre.
    """
    require_admin = getattr(websocket_api, "require_admin", None)
    if require_admin is None:  # pragma: no cover - nur ohne require_admin
        return handler
    return require_admin(handler)


def _send_unauthorized(connection: Any, msg: dict[str, Any]) -> None:
    """Nicht-Admin → derselbe Fehlercode, den HAs `require_admin` auslöst."""
    connection.send_error(
        msg["id"],
        ERR_UNAUTHORIZED,
        "Dieses Kommando ist Administratoren vorbehalten",
    )


def _option_int(entry: Any, key: str, mirror_attr: str, default: int) -> int:
    """Ganzzahlige Einstellung: Options → Runtime-Spiegel → Default.

    `entry.options` ist die Quelle der Wahrheit; der Runtime-Spiegel
    (`entry.runtime_data`) wird nur als Fallback gelesen, wenn die Option noch
    nie gesetzt wurde.
    """
    options = getattr(entry, "options", None) or {}
    if options.get(key) is not None:
        return _as_int(options[key], default)
    mirror = getattr(getattr(entry, "runtime_data", None), mirror_attr, None)
    return default if mirror is None else _as_int(mirror, default)


def _lexicon_pairs(lexicon: Any) -> dict[str, tuple[str, int]]:
    """Lexikon defensiv normalisieren: {wort: (Typ, ml)}.

    Options-Werte überleben einen JSON-Roundtrip (HA persistiert sie), Tupel
    kommen also als 2-elementige Listen zurück — beide Formen sind gültig.
    Unbrauchbare Einträge werden übersprungen statt zu crashen.
    """
    if not isinstance(lexicon, Mapping):
        return {}
    pairs: dict[str, tuple[str, int]] = {}
    for word, value in lexicon.items():
        if not isinstance(value, (list, tuple)) or len(value) != 2:
            continue
        pairs[str(word)] = (str(value[0]), _as_int(value[1], 0))
    return pairs


def format_lexicon_text(lexicon: Any) -> str:
    """Lexikon (Dict-Repräsentation) → Textform des Options-Flows.

    Nutzt exakt `parser.format_lexicon` — dieselbe Serialisierung wie der
    Options-Flow (config_flow.async_step_drink_lexicon), keine zweite Quelle.
    Fallback auf das Standard-Lexikon, wenn nichts Brauchbares gespeichert ist.
    """
    pairs = _lexicon_pairs(lexicon) or _lexicon_pairs(DRINK_LEXICON)
    return parser.format_lexicon(pairs)


def _quick_drinks(entry: Any) -> list[dict[str, Any]]:
    """Quick-Drinks der Option, sonst das Standard-Set (frische Kopien)."""
    options = getattr(entry, "options", None) or {}
    stored = options.get("quick_drinks")
    source = stored if isinstance(stored, list) and stored else DEFAULT_QUICK_DRINKS
    return [
        {
            "key": str(item.get("key") or ""),
            "label": str(item.get("label") or ""),
            "ml": _as_int(item.get("ml"), 0),
            "icon": str(item.get("icon") or DEFAULT_QUICK_DRINK_ICON),
        }
        for item in source
        if isinstance(item, Mapping)
    ]


def build_settings(entry: Any) -> dict[str, Any]:
    """Antwort-Payload für `get_settings` (auch Pflichtformat der set-Antwort).

    Alle Werte kommen ausschließlich aus `entry.options` (mit Options-Flow-
    Defaults, wenn nichts gesetzt ist) — kein Zweit-Datenmodell.
    """
    options = getattr(entry, "options", None) or {}
    return {
        "daily_goal_ml": _option_int(
            entry, "daily_goal_ml", "daily_goal_ml", DEFAULT_DAILY_GOAL_ML
        ),
        "daily_reset_hour": _as_int(options.get("daily_reset_hour"), 0),
        "person_display": effective_person(entry),
        "quick_drinks": _quick_drinks(entry),
        "drink_lexicon": format_lexicon_text(options.get("drink_lexicon")),
        WELLBEING_IMAGES_OPTION: logic.normalize_wellbeing_images(
            options.get(WELLBEING_IMAGES_OPTION)
        ),
        OPTION_WELLBEING_CONFIRM: bool(options.get(OPTION_WELLBEING_CONFIRM, False)),
        "sys_threshold": _option_int(
            entry, "sys_threshold", "sys_threshold", DEFAULT_SYS_THRESHOLD
        ),
        "dia_threshold": _option_int(
            entry, "dia_threshold", "dia_threshold", DEFAULT_DIA_THRESHOLD
        ),
        "retention_months": _as_int(options.get("retention_months"), DEFAULT_RETENTION_MONTHS),
        OPTION_ENABLE_SIDEBAR_PANEL: bool(options.get(OPTION_ENABLE_SIDEBAR_PANEL, False)),
        OPTION_AREAS: active_areas(options),
    }


def parse_settings_message(msg: Mapping[str, Any]) -> tuple[dict[str, Any], str | None]:
    """WS-Payload → (Options-Updates, Fehlermeldung). Reine Funktion.

    Es werden ausschließlich bekannte Settings-Schlüssel übernommen. Skalare
    Felder laufen durch `SETTINGS_SCHEMA` (Bereiche aus const.py), das
    `drink_lexicon` durch `parser.parse_lexicon_text()` — dieselbe Funktion, die
    der Options-Flow benutzt, also exakt dieselbe Dict-Repräsentation
    (`{wort: (Typ, ml)}`). Lexikon-Fehler tragen die Zeilennummer mit.
    """
    raw = {key: msg[key] for key in SETTINGS_KEYS if key in msg}
    if not raw:
        return {}, f"Keine Einstellung übergeben (erlaubt: {', '.join(SETTINGS_KEYS)})"

    updates: dict[str, Any] = {}
    if WELLBEING_IMAGES_OPTION in raw:
        raw_images = raw.pop(WELLBEING_IMAGES_OPTION)
        if not isinstance(raw_images, dict):
            return {}, (
                "Ungültige Einstellung 'wellbeing_images': erwartet ein Objekt, "
                f"erhalten {type(raw_images).__name__}"
            )
        updates[WELLBEING_IMAGES_OPTION] = logic.normalize_wellbeing_images(raw_images)

    if "drink_lexicon" in raw:
        raw_text = raw.pop("drink_lexicon")
        if not isinstance(raw_text, str):
            return {}, (
                "Ungültige Einstellung 'drink_lexicon': erwartet Text, "
                f"erhalten {type(raw_text).__name__}"
            )
        try:
            updates["drink_lexicon"] = parser.parse_lexicon_text(raw_text)
        except ValueError as err:
            return {}, f"Getränke-Lexikon: {err}"

    try:
        updates.update(SETTINGS_SCHEMA(raw))
    except vol.Invalid as err:
        field = ".".join(str(part) for part in err.path) or "settings"
        return {}, f"Ungültige Einstellung '{field}': {err.msg}"
    return updates, None


async def websocket_get_settings(hass: HomeAssistant, connection: Any, msg: dict[str, Any]) -> None:
    """`health_o_mat/get_settings` → Admin-Maske einer Person (nur Admin)."""
    if not is_admin_connection(connection):
        _send_unauthorized(connection, msg)
        return
    entry_id = msg["entry_id"]
    entry = _runtime_entry(hass, entry_id)
    if entry is None:
        _send_entry_error(connection, msg, entry_id)
        return
    connection.send_result(msg["id"], build_settings(entry))


async def websocket_set_settings(hass: HomeAssistant, connection: Any, msg: dict[str, Any]) -> None:
    """`health_o_mat/set_settings` → Einstellungen einer Person (nur Admin).

    Persistiert ausschließlich über `async_update_entry(entry, options=merged)`:
    das ist der Pfad, an dem der bestehende Options-Listener `_options_updated`
    hängt (Sync von Runtime-Spiegel, Retention, Panel-Status, Refresh).
    """
    if not is_admin_connection(connection):
        _send_unauthorized(connection, msg)
        return
    entry_id = msg["entry_id"]
    entry = _runtime_entry(hass, entry_id)
    if entry is None:
        _send_entry_error(connection, msg, entry_id)
        return
    updates, error = parse_settings_message(msg)
    if error is not None:
        connection.send_error(msg["id"], ERR_INVALID_FORMAT, error)
        return
    merged = {**(getattr(entry, "options", None) or {}), **updates}
    hass.config_entries.async_update_entry(entry, options=merged)
    connection.send_result(msg["id"], build_settings(entry))


async def websocket_export_csv(hass: HomeAssistant, connection: Any, msg: dict[str, Any]) -> None:
    """`health_o_mat/export_csv` → bestehenden CSV-Service auslösen (nur Admin).

    Kein Zweitweg: der Service schreibt nach /config/health_o_mat_export/ und
    kennt Person-/Dataset-Filter sowie das Retention-Archiv. Ohne `entry_id`
    wird — wie beim Service — über alle Personen exportiert.
    """
    if not is_admin_connection(connection):
        _send_unauthorized(connection, msg)
        return
    dataset = msg.get("dataset") or DEFAULT_EXPORT_DATASET
    if dataset not in EXPORT_DATASETS:
        connection.send_error(
            msg["id"],
            ERR_INVALID_FORMAT,
            f"Unbekannter Datensatz: {dataset!r} (erlaubt: {', '.join(EXPORT_DATASETS)})",
        )
        return

    entry_id = msg.get("entry_id")
    service_data: dict[str, Any] = {"dataset": dataset}
    if entry_id is not None:
        entry = _runtime_entry(hass, entry_id)
        if entry is None:
            _send_entry_error(connection, msg, entry_id)
            return
        # Der Service filtert über den Store-Personen-Schlüssel, der dem
        # effektiven Anzeigenamen entspricht (store.set_person im Setup).
        service_data["person"] = effective_person(entry)

    try:
        await hass.services.async_call(DOMAIN, "export_csv", service_data, blocking=True)
    except HomeAssistantError as err:
        # Deckt `ServiceValidationError` (fachlich, z. B. „Keine Daten") und
        # `ServiceNotFound` (kein Entry geladen) ab — beides strukturiert
        # zurückmelden statt als `unknown_error` zu verpuffen.
        connection.send_error(msg["id"], ERR_EXPORT_FAILED, str(err))
        return

    connection.send_result(
        msg["id"],
        {
            "ok": True,
            "entry_id": entry_id,
            "person": service_data.get("person"),
            "dataset": dataset,
        },
    )


async def websocket_start_person_flow(
    hass: HomeAssistant, connection: Any, msg: dict[str, Any]
) -> None:
    """`health_o_mat/start_person_flow` → Config-Flow zum Anlegen einer Person (nur Admin)."""
    if not is_admin_connection(connection):
        _send_unauthorized(connection, msg)
        return
    async_init = getattr(getattr(hass, "config_entries", None), "async_init", None)
    if async_init is None:
        connection.send_error(
            msg["id"],
            ERR_INVALID_FORMAT,
            "Config-Flow-Start wird von dieser Home-Assistant-Version nicht unterstützt",
        )
        return
    try:
        flow = await async_init(DOMAIN, context={"source": "user"})
    except Exception as err:  # noqa: BLE001 - Flow-Start darf nie den WS-Handler sprengen
        _LOGGER.exception("Health-O-Mat: Config-Flow konnte nicht gestartet werden")
        connection.send_error(
            msg["id"],
            ERR_INVALID_FORMAT,
            f"Config-Flow konnte nicht gestartet werden: {err}",
        )
        return
    flow_id = flow.get("flow_id") if isinstance(flow, Mapping) else None
    connection.send_result(msg["id"], {"flow_id": flow_id})


async def websocket_delete_person(
    hass: HomeAssistant, connection: Any, msg: dict[str, Any]
) -> None:
    """`health_o_mat/delete_person` → Person nach Doppelbestätigung entfernen (nur Admin).

    Die Bestätigung (`confirm`) muss EXAKT dem stabilen Slug
    `entry.data["person"]` entsprechen — so kann nie versehentlich eine andere
    Person gelöscht werden.
    """
    if not is_admin_connection(connection):
        _send_unauthorized(connection, msg)
        return
    entry_id = msg["entry_id"]
    entry = _runtime_entry(hass, entry_id)
    if entry is None:
        _send_entry_error(connection, msg, entry_id)
        return
    slug = entry.data.get("person", "")
    if msg["confirm"] != slug:
        connection.send_error(
            msg["id"],
            ERR_INVALID_FORMAT,
            "Die Bestätigung stimmt nicht mit dem Personen-Schlüssel überein",
        )
        return
    await hass.config_entries.async_remove(entry_id)
    connection.send_result(msg["id"], {"ok": True, "entry_id": entry_id})


async def websocket_backup(hass: HomeAssistant, connection: Any, msg: dict[str, Any]) -> None:
    """`health_o_mat/backup` → bestehenden Backup-Service auslösen (nur Admin).

    Kein Zweitweg: es wird genau der `health_o_mat.backup`-Service aufgerufen.
    """
    if not is_admin_connection(connection):
        _send_unauthorized(connection, msg)
        return
    try:
        await hass.services.async_call(DOMAIN, "backup", {}, blocking=True)
    except HomeAssistantError as err:
        connection.send_error(msg["id"], ERR_BACKUP_FAILED, str(err))
        return
    connection.send_result(msg["id"], {"ok": True})

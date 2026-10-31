"""Diagnostics-Plattform — strikt redigiert (REQ-HOM-105, Fund N-5).

Home Assistant entdeckt die Plattform automatisch über den Dateinamen und ruft
``async_get_config_entry_diagnostics`` beim Diagnostics-Download auf — eine
Registrierung in ``__init__.py`` ist nicht nötig.

Schutzgut dieser Integration sind **Gesundheitsdaten**: der Diagnostics-Download
landet üblicherweise in einem öffentlichen GitHub-Issue. Deshalb gilt eine strikte
**Allow-List** statt einer Deny-List:

Erlaubt: Integrations-/Entry-/Schema-Versionen, Entity-IDs der Person (Laborwert-
Entity-IDs namensmaskiert, siehe unten), ``entry.options`` (Personennamen darin
maskiert, Lab-Optionen nur als Zähler) und reine **Zähler** (gesamt/aktiv/voided
je Datensatz sowie Audit-Anzahl).
Verboten: ml-Mengen je Buchung, sys/dia/puls, Wohlbefinden-Status, Personennamen,
rohe Zeitstempel. ``total_ml_lifetime`` wird bewusst weggelassen (grenzwertige
Gesundheitsmenge, vgl. Fund N-5).

Review-Fix N-1: Ein **Custom-Labor-Marker** trägt den vom Nutzer vergebenen
Freitext-Namen in der Entity-ID (``sensor.<person>_<marker-name>``) — der wäre im
öffentlich teilbaren Download eine Diagnose-Veröffentlichung. Laborwert-Entities
werden daher auf ``<domain>.***_lab_<katalog-key>`` (Katalog-Keys sind öffentlich)
bzw. ``<domain>.***_lab_custom_<n>`` (Custom-Marker: nur eine laufende Nummer)
abgebildet. Alle anderen Entity-IDs bleiben unverändert.

Die Redaktion ist als reine, HA-freie Funktion ``redact_diagnostics`` gekapselt und
damit ohne Home-Assistant-Installation unit-testbar.
"""

from __future__ import annotations

import json
import pathlib
from collections.abc import Mapping, Sequence
from typing import Any

from .const import (
    DOMAIN,
    LAB_MARKERS,
    OPTION_LAB_CUSTOM_MARKERS,
    OPTION_LAB_HIDDEN_CATEGORIES,
    OPTION_LAB_REF_OVERRIDES,
    STORE_SCHEMA_VERSION,
)

#: Ersatz für jeden Personennamen im Output — nie der reale Name.
_PERSON_MASK = "***"

#: Options-Schlüssel, die einen Personennamen tragen und daher maskiert werden.
_NAME_KEYS = frozenset({"person", "person_display"})

#: Entity-Key-Präfix der Laborwert-Sensoren (``entity.py``: ``unique_id`` =
#: ``f"{entry_id}_{key}"``, ``sensor.py``: ``key`` = ``f"lab_{marker_key}"``).
_LAB_ENTITY_KEY = "lab_"

#: Lab-Options mit Freitext/Gesundheitsbezug: nur als reiner Zähler ausgeben.
#: ``lab_custom_markers`` enthält frei wählbare Namen (potenziell Diagnosen),
#: ``lab_ref_overrides``/``lab_hidden_categories`` Marker-Identitäten.
_LAB_OPTION_KEYS = frozenset(
    {
        OPTION_LAB_CUSTOM_MARKERS,
        OPTION_LAB_HIDDEN_CATEGORIES,
        OPTION_LAB_REF_OVERRIDES,
    }
)


def redact_diagnostics(raw: Mapping[str, Any]) -> dict[str, Any]:
    """Baue die strikt redigierte Diagnostics-Antwort aus ``raw``.

    Allow-List: nur die unten explizit gelesenen Felder überleben. Alles andere —
    unbekannte Schlüssel, Gesundheitswerte, Personennamen und Zeitstempel — wird
    verworfen. Der Personname wird immer durch ``***`` ersetzt.
    """
    store_entry = raw.get("store_entry")
    if not isinstance(store_entry, Mapping):
        store_entry = {}

    return {
        "integration": {
            "domain": DOMAIN,
            "version": str(raw.get("integration_version") or "unknown"),
        },
        "config_entry": {
            "version": raw.get("entry_version"),
            "person": _PERSON_MASK,
        },
        "store": {
            "schema_version": raw.get("store_schema_version"),
            "available": bool(raw.get("store_available", False)),
        },
        "entities": _redact_entity_ids(raw.get("entity_ids")),
        "options": _redact_options(raw.get("options")),
        "counters": _counters(store_entry),
    }


def _redact_entity_ids(items: Any) -> list[str]:
    """Entity-IDs für den Output aufbereiten — Laborwerte namensmaskiert (N-1).

    Akzeptiert zwei Eingabeformen: die reine Liste von Entity-ID-Strings
    (``redact_diagnostics``-Aufrufer ohne Registry-Kontext) und die Registry-
    Datensätze aus ``_collect_entity_ids`` (``{"entity_id", "lab_marker_key"}``).
    Nur im zweiten Fall ist der Marker-Key bekannt — ohne ihn bleibt eine
    Entity-ID unverändert (Nicht-Labor-Entity oder Fake-Registry im Test).
    """
    records: list[tuple[str, str]] = []
    for item in _as_sequence(items):
        if isinstance(item, Mapping):
            entity_id = str(item.get("entity_id") or "")
            lab_marker_key = str(item.get("lab_marker_key") or "")
        else:
            entity_id, lab_marker_key = str(item), ""
        if entity_id:
            records.append((entity_id, lab_marker_key))

    # Custom-Marker-Namen sind Freitext — sie werden auf eine laufende Nummer
    # abgebildet. Die Nummerierung ist über die sortierten Keys stabil, damit
    # derselbe Optionsstand denselben Output ergibt.
    custom_keys = sorted({key for _entity_id, key in records if key and key not in LAB_MARKERS})
    custom_ordinal = {key: index for index, key in enumerate(custom_keys, start=1)}
    return sorted(
        _mask_entity_id(entity_id, lab_marker_key, custom_ordinal)
        for entity_id, lab_marker_key in records
    )


def _mask_entity_id(entity_id: str, lab_marker_key: str, custom_ordinal: Mapping[str, int]) -> str:
    """Eine Entity-ID maskieren, wenn sie zu einem Laborwert-Sensor gehört.

    Katalog-Keys sind öffentlich (jede Installation hat dieselben Sensoren) und
    bleiben lesbar; ein Custom-Marker-Key ist aus dem Nutzer-Freitext abgeleitet
    und wird deshalb durch seine laufende Nummer ersetzt.
    """
    if not lab_marker_key:
        return entity_id
    domain = entity_id.split(".", 1)[0] or "sensor"
    if lab_marker_key in LAB_MARKERS:
        return f"{domain}.{_PERSON_MASK}_lab_{lab_marker_key}"
    ordinal = custom_ordinal.get(lab_marker_key, 0)
    return f"{domain}.{_PERSON_MASK}_lab_custom_{ordinal}"


def _counters(store_entry: Mapping[str, Any]) -> dict[str, int]:
    """Reine Zähler je Datensatz — gesamt, aktiv und voided (M2a).

    Die bestehenden Keys (`drinks`, `readings`, `wellbeing_history`) behalten
    ihre Bedeutung (Gesamtzahl der Rohliste bzw. Historie). Die `*_active`/
    `*_voided`-Keys sind additiv und erlauben die Unterscheidung ohne jede
    inhaltliche Angabe (keine Mengen, Werte oder Zeitstempel).
    """
    drinks_total, drinks_voided = _split_count(store_entry.get("drinks"))
    readings_total, readings_voided = _split_count(store_entry.get("readings"))
    wellbeing_total, wellbeing_voided = _wellbeing_counts(store_entry)
    return {
        "drinks": drinks_total,
        "drinks_active": drinks_total - drinks_voided,
        "drinks_voided": drinks_voided,
        "readings": readings_total,
        "readings_active": readings_total - readings_voided,
        "readings_voided": readings_voided,
        "wellbeing_history": _count(store_entry.get("wellbeing_history")),
        "wellbeing_entries": wellbeing_total,
        "wellbeing_active": wellbeing_total - wellbeing_voided,
        "wellbeing_voided": wellbeing_voided,
        "audit_events": _count(store_entry.get("audit_log")),
    }


def _split_count(value: Any) -> tuple[int, int]:
    """(gesamt, voided) einer Buchungsliste — voided = gesetztes `voided_at`."""
    items = _as_sequence(value)
    voided = sum(1 for item in items if isinstance(item, Mapping) and item.get("voided_at"))
    return len(items), voided


def _wellbeing_counts(store_entry: Mapping[str, Any]) -> tuple[int, int]:
    """(gesamt, voided) der Wohlbefinden-Meldungen.

    Ab v4 zählt `wellbeing_entries`; für Vor-v4-Bestände ohne Ereignisliste
    wird der Legacy-Spiegel (aktueller Wert + Historie) als aktiv gezählt.
    """
    entries = store_entry.get("wellbeing_entries")
    if isinstance(entries, list):
        return _split_count(entries)
    legacy = _count(store_entry.get("wellbeing_history"))
    current = store_entry.get("wellbeing")
    if isinstance(current, Mapping) and current.get("status"):
        legacy += 1
    return legacy, 0


def _as_sequence(value: Any) -> list[Any]:
    """Nur echte Sequenzen (keine Strings/Bytes) als Liste zurückgeben."""
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return list(value)
    return []


def _count(value: Any) -> int:
    """Länge einer Buchungs-/Historienliste — reiner Zähler, keine Inhalte."""
    return len(_as_sequence(value))


def _redact_options(options: Any) -> dict[str, Any]:
    """Options kopieren, Personennamen maskieren, Lab-Optionen nur zählen."""
    if not isinstance(options, Mapping):
        return {}
    return {str(key): _redact_option_value(key, value) for key, value in options.items()}


def _redact_option_value(key: Any, value: Any) -> Any:
    """Einen Options-Wert redigieren: Name maskieren, Lab-Inhalt nur zählen."""
    name = str(key)
    if name in _NAME_KEYS:
        return _PERSON_MASK
    if name in _LAB_OPTION_KEYS:
        return {"count": _option_count(value)}
    return _scrub(value)


def _option_count(value: Any) -> int:
    """Anzahl der Einträge einer Lab-Option — nie deren Inhalt."""
    if isinstance(value, Mapping):
        return len(value)
    return _count(value)


def _scrub(value: Any) -> Any:
    """Rekursiv Personennamen und Lab-Inhalte in verschachtelten Options redigieren."""
    if isinstance(value, Mapping):
        return {str(key): _redact_option_value(key, item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return [_scrub(item) for item in value]
    return value


def _integration_version() -> str:
    """``manifest.version`` lesen — ohne Home-Assistant-Abhängigkeit."""
    try:
        manifest = pathlib.Path(__file__).with_name("manifest.json")
        with manifest.open(encoding="utf-8") as handle:
            return str(json.load(handle).get("version") or "unknown")
    except (OSError, ValueError):
        return "unknown"


def _collect_entity_ids(hass: Any, entry: Any) -> list[dict[str, str]]:
    """Registry-Datensätze der zum Config-Entry gehörenden Entities (best effort).

    Rückgabe ist bewusst strukturiert (``entity_id`` + ``lab_marker_key``) statt
    einer reinen ID-Liste: nur so lässt sich N-1 umsetzen — ein Laborwert-Sensor
    ist an seiner ``unique_id`` erkennbar, nicht an der Entity-ID (deren Suffix
    bei Custom-Markern der Nutzer-Freitext ist).

    Die Entity-Registry wird erst zur Laufzeit importiert und defensiv behandelt:
    fehlt sie (Fake-HA in den Unit-Tests) oder schlägt der Zugriff fehl, liefern
    wir eine leere Liste statt den Diagnostics-Download abzubrechen.
    """
    try:
        from homeassistant.helpers import entity_registry as er
    except Exception:  # pragma: no cover - Registry optional im Test-Kontext
        return []
    try:
        registry = er.async_get(hass)
        entries = er.async_entries_for_config_entry(registry, entry.entry_id)
    except Exception:  # pragma: no cover - defensiv: Diagnostics nie abbrechen
        return []
    collected: list[dict[str, str]] = []
    for item in entries:
        entity_id = str(getattr(item, "entity_id", "") or "")
        if not entity_id:
            continue
        collected.append({"entity_id": entity_id, "lab_marker_key": _lab_marker_key(entry, item)})
    return collected


def _lab_marker_key(entry: Any, registry_entry: Any) -> str:
    """Marker-Key, wenn die Registry-Entity ein Laborwert-Sensor ist, sonst ``""``.

    Der Key wird aus der stabilen ``unique_id`` gelesen (``{entry_id}_lab_{key}``),
    NICHT aus der Entity-ID — nur so ist er unabhängig von Sprache, Person und
    Nutzer-Freitext.
    """
    unique_id = str(getattr(registry_entry, "unique_id", "") or "")
    entry_id = str(getattr(entry, "entry_id", "") or "")
    prefix = f"{entry_id}_{_LAB_ENTITY_KEY}"
    if not entry_id or not unique_id.startswith(prefix):
        return ""
    return unique_id[len(prefix) :]


async def async_get_config_entry_diagnostics(hass: Any, entry: Any) -> dict[str, Any]:
    """Diagnostics-Download für genau eine Person (= ein Config-Entry).

    Definiertes Verhalten bei fehlendem Store/Entry: ``store.available`` wird
    ``False`` und alle Zähler bleiben ``0`` — kein Fehler, keine Rohdaten.
    """
    store_entry: Mapping[str, Any] = {}
    store_available = False

    domain_data = getattr(hass, "data", None)
    domain_data = domain_data.get(DOMAIN) if isinstance(domain_data, Mapping) else None
    shared = domain_data.get("shared") if isinstance(domain_data, Mapping) else None
    store = shared.get("store") if isinstance(shared, Mapping) else None

    if store is not None:
        try:
            store_entry = store.all_entries().get(entry.entry_id) or {}
            store_available = True
        except Exception:  # pragma: no cover - defensiv: Diagnostics nie abbrechen
            store_entry = {}
            store_available = False

    raw = {
        "integration_version": _integration_version(),
        "entry_version": getattr(entry, "version", None),
        "store_schema_version": STORE_SCHEMA_VERSION,
        "store_available": store_available,
        "entity_ids": _collect_entity_ids(hass, entry),
        "options": dict(getattr(entry, "options", None) or {}),
        "store_entry": store_entry,
    }
    return redact_diagnostics(raw)

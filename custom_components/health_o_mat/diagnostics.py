"""Diagnostics-Plattform — strikt redigiert (REQ-HOM-105, Fund N-5).

Home Assistant entdeckt die Plattform automatisch über den Dateinamen und ruft
``async_get_config_entry_diagnostics`` beim Diagnostics-Download auf — eine
Registrierung in ``__init__.py`` ist nicht nötig.

Schutzgut dieser Integration sind **Gesundheitsdaten**: der Diagnostics-Download
landet üblicherweise in einem öffentlichen GitHub-Issue. Deshalb gilt eine strikte
**Allow-List** statt einer Deny-List:

Erlaubt: Integrations-/Entry-/Schema-Versionen, Entity-IDs der Person,
``entry.options`` (Personennamen darin maskiert) und reine **Zähler**
(gesamt/aktiv/voided je Datensatz sowie Audit-Anzahl).
Verboten: ml-Mengen je Buchung, sys/dia/puls, Wohlbefinden-Status, Personennamen,
rohe Zeitstempel. ``total_ml_lifetime`` wird bewusst weggelassen (grenzwertige
Gesundheitsmenge, vgl. Fund N-5).

Die Redaktion ist als reine, HA-freie Funktion ``redact_diagnostics`` gekapselt und
damit ohne Home-Assistant-Installation unit-testbar.
"""

from __future__ import annotations

import json
import pathlib
from collections.abc import Mapping, Sequence
from typing import Any

from .const import DOMAIN, STORE_SCHEMA_VERSION

#: Ersatz für jeden Personennamen im Output — nie der reale Name.
_PERSON_MASK = "***"

#: Options-Schlüssel, die einen Personennamen tragen und daher maskiert werden.
_NAME_KEYS = frozenset({"person", "person_display"})


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
        "entities": sorted(str(entity) for entity in _as_sequence(raw.get("entity_ids"))),
        "options": _redact_options(raw.get("options")),
        "counters": _counters(store_entry),
    }


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
    """Options kopieren, Personennamen maskieren, sonst tief durchreichen."""
    if not isinstance(options, Mapping):
        return {}
    return {
        str(key): (_PERSON_MASK if key in _NAME_KEYS else _scrub(value))
        for key, value in options.items()
    }


def _scrub(value: Any) -> Any:
    """Rekursiv Personennamen in verschachtelten Options maskieren."""
    if isinstance(value, Mapping):
        return {
            str(key): (_PERSON_MASK if key in _NAME_KEYS else _scrub(item))
            for key, item in value.items()
        }
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


def _collect_entity_ids(hass: Any, entry: Any) -> list[str]:
    """Entity-IDs der zum Config-Entry gehörenden Entities (best effort).

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
        return sorted(str(item.entity_id) for item in entries)
    except Exception:  # pragma: no cover - defensiv: Diagnostics nie abbrechen
        return []


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

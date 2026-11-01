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

**Sektion ``lab_entity_orphans`` (Post-Release-Befund 1):** Nach der Normalisierung
der Custom-Marker-Kategorie (A-1: unbekannte Kategorie fällt auf ``other``) können
Labor-Entities entstehen, die das Setup **nicht mehr anlegt** — sie bleiben als
``restored``/``unavailable`` in der Registry stehen und sind über einen bloßen
State-Check („Registry-Eintrag ohne State") NICHT auffindbar, weil HA für sie
weiterhin einen (Restored-)State führt. Die Sektion vergleicht deshalb die
**Soll**-Menge der Labor-Entity-Keys (genau die Keys, die ``sensor.py`` /
``binary_sensor.py`` beim Setup erzeugen) mit dem **Ist** der Entity-Registry.
Reine Diagnose: kein Setup-Eingriff, keine Auto-Löschung, keine ``unique_id``-
Änderung. Auch hier wird nichts Gesundheitsbezogenes ausgegeben — ``state`` ist auf
eine Zustandsklasse reduziert (``restored``/``unavailable``/``unknown``/``missing``/
``provided``), nie der Messwert, und Custom-Marker-Keys sind durchnummeriert.
"""

from __future__ import annotations

import json
import pathlib
from collections.abc import Mapping, Sequence
from typing import Any

from . import areas, logic
from .const import (
    DOMAIN,
    LAB_CATEGORIES,
    LAB_CATEGORY_OTHER,
    LAB_MARKERS,
    OPTION_LAB_CUSTOM_MARKERS,
    OPTION_LAB_HIDDEN_CATEGORIES,
    OPTION_LAB_HIDE_PANEL_DISCLAIMER,
    OPTION_LAB_REF_OVERRIDES,
    OPTION_LAB_RETENTION_MONTHS,
    STORE_SCHEMA_VERSION,
)

#: Ersatz für jeden Personennamen im Output — nie der reale Name.
_PERSON_MASK = "***"

#: Options-Schlüssel, die einen Personennamen tragen und daher maskiert werden.
_NAME_KEYS = frozenset({"person", "person_display"})

#: Entity-Key-Präfix der Laborwert-Sensoren (``entity.py``: ``unique_id`` =
#: ``f"{entry_id}_{key}"``, ``sensor.py``: ``key`` = ``f"lab_{marker_key}"``).
_LAB_ENTITY_KEY = "lab_"

#: Entity-Key-Präfix der Labor-Warn-Binaries (``binary_sensor.py``: ``key`` =
#: ``f"binary_lab_warning_{category}"``).
_LAB_WARNING_ENTITY_KEY = "binary_lab_warning_"

#: Zustände, die eine verwaiste Entity diagnostisch kennzeichnen (HA-Restored-
#: bzw. Nicht-verfügbar-Zustand). Alles andere ist eine normale Zustandsklasse.
_ORPHAN_STATE_VALUES = frozenset({"restored", "unavailable", "unknown"})

#: Zustandsklasse, wenn gar kein State-Objekt existiert.
_STATE_MISSING = "missing"

#: Zustandsklasse für eine Entity, die regulär einen Wert liefert — der Wert
#: selbst wird NIE ausgegeben (Gesundheitsdatum).
_STATE_PROVIDED = "provided"

#: Gründe eines Labor-Orphans (stabile, maschinenlesbare Kennungen).
_REASON_UNKNOWN_CATEGORY = "unknown_category"
_REASON_STALE_MARKER_KEY = "stale_marker_key"
_REASON_NOT_PROVIDED = "not_provided"

#: Lab-Options mit Freitext/Gesundheitsbezug: nur als reiner Zähler ausgeben.
#: ``lab_custom_markers`` enthält frei wählbare Namen (potenziell Diagnosen),
#: ``lab_ref_overrides``/``lab_hidden_categories`` Marker-Identitäten.
_LAB_OPTION_KEYS = frozenset(
    {
        OPTION_LAB_CUSTOM_MARKERS,
        OPTION_LAB_HIDDEN_CATEGORIES,
        OPTION_LAB_REF_OVERRIDES,
        OPTION_LAB_HIDE_PANEL_DISCLAIMER,
        OPTION_LAB_RETENTION_MONTHS,
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

    options = raw.get("options")
    records = _entity_records(raw.get("entity_ids"))
    custom_ordinal = _custom_ordinal(records)

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
        "entities": _redact_entity_ids(records, custom_ordinal),
        "lab_entity_orphans": _lab_entity_orphans(records, options, custom_ordinal),
        "options": _redact_options(options),
        "counters": _counters(store_entry),
    }


def _entity_records(items: Any) -> list[Mapping[str, Any]]:
    """Registry-Datensätze normalisieren — reine IDs werden zu Minimal-Records.

    Akzeptiert die Registry-Datensätze aus ``_collect_entity_ids`` und (für
    Aufrufer ohne Registry-Kontext) eine reine Liste von Entity-ID-Strings.
    """
    records: list[Mapping[str, Any]] = []
    for item in _as_sequence(items):
        if isinstance(item, Mapping):
            record = dict(item)
            if not str(record.get("entity_id") or ""):
                continue
        else:
            entity_id = str(item)
            if not entity_id:
                continue
            record = {"entity_id": entity_id}
        records.append(record)
    return records


def _custom_ordinal(records: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    """Custom-Marker-Keys auf eine stabile laufende Nummer abbilden.

    Custom-Marker-Namen sind Freitext — sie werden auf eine laufende Nummer
    abgebildet. Die Nummerierung ist über die sortierten Keys stabil, damit
    derselbe Optionsstand denselben Output ergibt — in der ``entities``-Liste
    UND in ``lab_entity_orphans`` (dieselbe Nummer = derselbe Marker).
    """
    custom_keys = sorted(
        {
            key
            for record in records
            if (key := str(record.get("lab_marker_key") or "")) and key not in LAB_MARKERS
        }
    )
    return {key: index for index, key in enumerate(custom_keys, start=1)}


def _redact_entity_ids(
    records: Sequence[Mapping[str, Any]], custom_ordinal: Mapping[str, int]
) -> list[str]:
    """Entity-IDs für den Output aufbereiten — Laborwerte namensmaskiert (N-1).

    Ohne bekannten Marker-Key bleibt eine Entity-ID unverändert (Nicht-Labor-
    Entity oder Fake-Registry im Test).
    """
    return sorted(
        _mask_entity_id(
            str(record.get("entity_id") or ""),
            str(record.get("lab_marker_key") or ""),
            custom_ordinal,
        )
        for record in records
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


def expected_lab_entity_keys(
    options: Mapping[str, Any] | None, *, ignore_area: bool = False
) -> set[str]:
    """Soll-Menge der Labor-Entity-Keys — exakt die Keys aus dem Plattform-Setup.

    Der Key ist der Teil der ``unique_id`` NACH ``f"{entry_id}_"`` (also
    ``lab_<marker_key>`` bzw. ``binary_lab_warning_<category>``). Beide
    Plattformen legen diese Entities nur an, wenn der Bereich "labs" aktiv ist
    (``areas.AREA_LABS``) — deshalb ist ``ignore_area=True`` die hypothetische
    Menge "wenn der Bereich aktiv wäre" (Grundlage der ``not_provided``-Diagnose).

    Marker-Quelle ist ``logic.effective_lab_markers`` — dieselbe Funktion, die
    ``sensor.py``/``binary_sensor.py`` beim Setup benutzen. Damit fällt z. B. ein
    Custom-Marker mit unbekannter Kategorie (A-1 → ``other``) automatisch aus der
    Warn-Entity-Menge heraus; eine vorhandene Warn-Entity dieser Fremdkategorie
    wird dadurch als Orphan sichtbar. Kategorien werden über ``LAB_CATEGORIES``
    geführt; ``other`` erzeugt bewusst keine Warn-Entity.
    """
    opts: Mapping[str, Any] = options if isinstance(options, Mapping) else {}
    if not ignore_area and not areas.area_enabled(opts, areas.AREA_LABS):
        return set()
    markers = logic.effective_lab_markers(opts.get(OPTION_LAB_CUSTOM_MARKERS))
    marker_categories = {str(definition.get("category") or "") for definition in markers.values()}
    keys = {f"{_LAB_ENTITY_KEY}{marker_key}" for marker_key in markers}
    keys.update(
        f"{_LAB_WARNING_ENTITY_KEY}{category['key']}"
        for category in LAB_CATEGORIES
        if category["key"] != LAB_CATEGORY_OTHER and category["key"] in marker_categories
    )
    return keys


def _lab_entity_orphans(
    records: Sequence[Mapping[str, Any]],
    options: Any,
    custom_ordinal: Mapping[str, int],
) -> dict[str, Any]:
    """Labor-Entities in der Registry, die das aktuelle Setup nicht mehr anlegt.

    Ist-Menge = Registry-Einträge dieses Entrys (``platform == DOMAIN``) mit
    Labor-Key; Soll-Menge = ``expected_lab_entity_keys``. Ein Eintrag außerhalb
    der Soll-Menge ist ein Orphan — er bleibt in HA als ``restored``/
    ``unavailable`` stehen und ist über "Registry-Eintrag ohne State" NICHT
    auffindbar.

    Reine Diagnose: es wird nichts gelöscht und kein Setup beeinflusst.
    """
    expected = expected_lab_entity_keys(options)
    expected_without_area = expected_lab_entity_keys(options, ignore_area=True)
    orphans = [
        _orphan_item(record, expected_without_area, custom_ordinal)
        for record in records
        if _is_lab_record(record) and str(record.get("lab_entity_key") or "") not in expected
    ]
    orphans.sort(key=lambda item: (item["entity_id"], item["unique_id"]))
    return {"count": len(orphans), "items": orphans}


def _is_lab_record(record: Mapping[str, Any]) -> bool:
    """True, wenn der Record eine Labor-Entity DIESER Integration ist."""
    if str(record.get("platform") or "") != DOMAIN:
        return False
    return bool(str(record.get("lab_entity_key") or ""))


def _orphan_item(
    record: Mapping[str, Any],
    expected_without_area: set[str],
    custom_ordinal: Mapping[str, int],
) -> dict[str, str]:
    """Eine Orphan-Zeile bauen — Entity-ID/unique_id maskiert, State als Klasse."""
    key_part = str(record.get("lab_entity_key") or "")
    masked_key = _mask_lab_key_part(key_part, custom_ordinal)
    entity_id = str(record.get("entity_id") or "")
    domain = entity_id.split(".", 1)[0] or "sensor"
    unique_id = str(record.get("unique_id") or "")
    return {
        "entity_id": f"{domain}.{_PERSON_MASK}_{_entity_id_key_part(masked_key)}",
        # entry_id-Präfix bleibt erhalten (opake ID, kein Personenbezug) —
        # nur der Custom-Marker-Key ist maskiert.
        "unique_id": f"{unique_id[: len(unique_id) - len(key_part)]}{masked_key}",
        "state": str(record.get("state") or _STATE_MISSING),
        "reason": _orphan_reason(key_part, expected_without_area),
    }


def _entity_id_key_part(key_part: str) -> str:
    """unique_id-Key -> Anteil, wie er in der Entity-ID erscheint.

    ``entity.py`` bildet ``unique_id = f"{entry_id}_{key}"`` auf
    ``<domain>.<person>_<key ohne Plattform-Präfix>`` ab: aus
    ``binary_lab_warning_liver`` wird ``binary_sensor.…_lab_warning_liver``.
    """
    if key_part.startswith(_LAB_WARNING_ENTITY_KEY):
        return key_part.removeprefix("binary_")
    return key_part


def _orphan_reason(key_part: str, expected_without_area: set[str]) -> str:
    """Grund des Orphans — spezifisch, wenn möglich; sonst ``not_provided``.

    * ``not_provided`` — der Key wäre bei aktivem Bereich "labs" korrekt; die
      Entity fehlt nur, weil der Bereich abgeschaltet ist.
    * ``unknown_category`` — Warn-Entity einer Kategorie, die die aktuellen
      Marker nicht (mehr) erzeugen (z. B. Kategorie nach A-1 auf ``other``
      gefallen; ``other`` hat bewusst keine Warn-Entity).
    * ``stale_marker_key`` — Laborwert-Sensor eines Markers, der nicht mehr in
      ``lab_custom_markers`` steht (entfernt, umbenannt oder von der
      Normalisierung verworfen).
    """
    if key_part in expected_without_area:
        return _REASON_NOT_PROVIDED
    if key_part.startswith(_LAB_WARNING_ENTITY_KEY):
        return _REASON_UNKNOWN_CATEGORY
    return _REASON_STALE_MARKER_KEY


def _mask_lab_key_part(key_part: str, custom_ordinal: Mapping[str, int]) -> str:
    """Labor-Key maskieren: Katalog-Keys bleiben, Custom-Keys werden nummeriert.

    Katalog-Keys (``LAB_MARKERS``/``LAB_CATEGORIES``) sind öffentlich — jede
    Installation hat dieselben Entities. Ein Custom-Marker-Key ist aus dem
    Nutzer-Freitext abgeleitet (potenziell eine Diagnose) und wird deshalb durch
    seine laufende Nummer ersetzt.
    """
    if key_part.startswith(_LAB_WARNING_ENTITY_KEY):
        return key_part
    marker_key = key_part[len(_LAB_ENTITY_KEY) :]
    if marker_key in LAB_MARKERS:
        return key_part
    ordinal = custom_ordinal.get(marker_key, 0)
    return f"{_LAB_ENTITY_KEY}custom_{ordinal}"


def _state_class(state: Any) -> str:
    """Beobachteten Entity-Zustand auf eine Klasse reduzieren — nie den Wert.

    Ein Laborwert-Sensor trägt seinen Messwert im State; der Diagnostics-Download
    ist öffentlich teilbar, deshalb wird ausschließlich die Zustandsklasse
    ausgegeben (``restored``/``unavailable``/``unknown``/``provided``/``missing``).
    """
    value = getattr(state, "state", None)
    if not isinstance(value, str) or not value:
        return _STATE_MISSING
    if value in _ORPHAN_STATE_VALUES:
        return value
    return _STATE_PROVIDED


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

    Rückgabe ist bewusst strukturiert statt einer reinen ID-Liste:

    * ``lab_marker_key`` — Marker-Key eines Laborwert-Sensors (N-1-Maskierung:
      ein Laborwert-Sensor ist an seiner ``unique_id`` erkennbar, nicht an der
      Entity-ID, deren Suffix bei Custom-Markern der Nutzer-Freitext ist).
    * ``lab_entity_key`` — der Labor-Key-Teil der ``unique_id``
      (``lab_<key>``/``binary_lab_warning_<category>``, sonst ``""``) für den
      Soll/Ist-Vergleich in ``lab_entity_orphans``.
    * ``platform`` — Plattform des Registry-Eintrags; die Orphan-Diagnose
      betrachtet ausschließlich eigene Einträge (``platform == DOMAIN``).
    * ``state`` — Zustandsklasse (nie der Messwert), damit "verwaist" von
      "liefert regulär einen Wert" unterscheidbar bleibt.

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
        lab_entity_key = _lab_entity_key(entry, item)
        collected.append(
            {
                "entity_id": entity_id,
                "unique_id": str(getattr(item, "unique_id", "") or ""),
                "platform": str(getattr(item, "platform", "") or ""),
                "lab_entity_key": lab_entity_key,
                "lab_marker_key": _marker_key_from_lab_key(lab_entity_key),
                "state": _observed_state_class(hass, entity_id) if lab_entity_key else "",
            }
        )
    return collected


def _lab_entity_key(entry: Any, registry_entry: Any) -> str:
    """Labor-Key-Teil der ``unique_id`` (``lab_…``/``binary_lab_warning_…``), sonst ``""``.

    Der Key wird aus der stabilen ``unique_id`` gelesen
    (``{entry_id}_{key}``), NICHT aus der Entity-ID — nur so ist er unabhängig
    von Sprache, Person und Nutzer-Freitext.
    """
    unique_id = str(getattr(registry_entry, "unique_id", "") or "")
    entry_id = str(getattr(entry, "entry_id", "") or "")
    prefix = f"{entry_id}_"
    if not entry_id or not unique_id.startswith(prefix):
        return ""
    key_part = unique_id[len(prefix) :]
    if key_part.startswith((_LAB_ENTITY_KEY, _LAB_WARNING_ENTITY_KEY)):
        return key_part
    return ""


def _marker_key_from_lab_key(lab_entity_key: str) -> str:
    """Marker-Key eines Laborwert-Sensors; für Warn-Entities ``""`` (N-1-Pfad)."""
    if not lab_entity_key.startswith(_LAB_ENTITY_KEY):
        return ""
    return lab_entity_key[len(_LAB_ENTITY_KEY) :]


def _observed_state_class(hass: Any, entity_id: str) -> str:
    """Zustandsklasse einer Entity aus ``hass.states`` (defensiv, nie der Wert)."""
    states = getattr(hass, "states", None)
    get_state = getattr(states, "get", None)
    if get_state is None:
        return _STATE_MISSING
    try:
        return _state_class(get_state(entity_id))
    except Exception:  # pragma: no cover - State-Zugriff nie diagnostics-kritisch
        return _STATE_MISSING


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

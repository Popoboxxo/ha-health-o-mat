"""Recorder-Statistik-Migration: Legacy-Volume-Einheit "ml" → HA-kanonisch "mL".

Hintergrund (P1-Bug, auf der Testinstanz belegt): Ältere Installationen haben
Recorder-Statistik-Metadaten mit der Einheit "ml" (unit_class=NULL). Die
Sensoren melden inzwischen die HA-kanonische Einheit "mL"
(SensorDeviceClass.VOLUME). Home Assistant verweigert deshalb die Fortsetzung
der Langzeitstatistik:

    "The unit of ... (mL) cannot be converted to the unit of previously
     compiled statistics (ml). Generation of long term statistics will be
     suppressed"

Der HA-Kern heilt das nicht (er migriert nur bei entity_id-Änderungen) — die
Integration muss die Metadaten selbst nachziehen. Betroffen sind
ausschließlich die beiden Volumen-Sensoren mit state_class
("sensor_drinks_today" = TOTAL, "sensor_lifetime_total" = TOTAL_INCREASING).
Alle anderen Sensoren (%, mmHg, mg, d, BPM) haben ihre Einheit nie geändert;
number/text/button/select/binary_sensor erzeugen per HA-Regel KEINE
Recorder-Statistik.

Die Migration ist verlustfrei ("ml" ≡ "mL") und idempotent: ein zweiter Lauf
findet die kanonische Einheit vor und tut nichts.

Ablauf (bewusst KISS, OHNE Start-Event-Retry):
* Recorder nicht eingerichtet → Migration wird übersprungen und beim NÄCHSTEN
  Setup (HA-Neustart oder Reload des Config-Entries) nachgeholt. Das ist
  idempotent und verlustfrei: es wird nichts gelöscht, nur die Einheit einer
  Metadatenzeile gehoben, und ein zweiter Lauf ändert nichts mehr. Der
  Recorder ist Bootstrap-STAGE_0 und steht damit IMMER bereit, bevor ein
  Config-Entry-Setup läuft — ein Start-Event-Listener wäre toter Code.
* Recorder-API nicht verfügbar (HA-Version ohne Recorder) → No-op.

Entity-IDs: primär über die Entity-Registry (unique_id "{entry_id}_{key}" der
Config-Entry) — KEINE entity_id-Konstruktion aus dem Person-Slug.

Registry-Timing (verifiziert gegen die installierte HA-Version 2026.2.3):
``await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)``
garantiert, dass die Entity-Registry-Einträge angelegt sind:
  * homeassistant/helpers/entity_platform.py:457-463 — "_async_setup_platform"
    wartet auf alle Add-Entity-Tasks ("Block till all entities are done",
    asyncio.gather über self._tasks).
  * homeassistant/helpers/entity_platform.py:911 — der Registry-Eintrag
    entsteht erst dort (entity_registry.async_get_or_create).
  * homeassistant/config_entries.py:2632-2647 — "async_forward_entry_setups"
    sammelt die Plattform-Setups per asyncio.gather und awaited sie
    (config_entries.py:2676 → entry.async_setup → entity_platform.py:422).
Der Registry-Pfad ist damit der Primärpfad. Der unten beschriebene Fallback
bleibt trotzdem aktiv (Schutznetz — siehe dort).

Fallback (Sicherheitsnetz): liefert die Registry-Auflösung KEINE Entity-IDs,
wird ein ungefilterter Recorder-Scan (``async_list_statistic_ids(hass)``)
gemacht und daraus nur die statistic_ids behalten, die zweifelsfrei zu unseren
beiden Volumen-Sensoren gehören (Prefix "sensor.health_o_mat_" UND Endung
"_drinks_today"/"_lifetime_total"). Gründe:
  (a) Der Bereich "Getränke" kann deaktiviert sein → sensor.py legt dann
      KEINE Volumen-Sensoren an → keine Registry-Einträge → die veraltete
      Metadatenzeile "ml" bliebe stehen und HA unterdrückt die
      Langzeitstatistik weiter.
  (b) Der Fallback macht die Migration unabhängig vom exakten Zeitpunkt der
      Registry-Anlage beim Plattform-Setup.
Fremde Domains, Fremd-Integrationen und Nicht-Volume-IDs (%, mmHg, mg, d, BPM)
bleiben ausgeschlossen. Der Fallback läuft ausschließlich, wenn der
Registry-Pfad leer ist — im Normalfall entsteht kein unnötiger Vollscan. Der
Vollscan liest einmalig alle Statistic-IDs der Recorder-DB (ein DB-Query pro
Setup eines Eintrags, dessen Getränke-Bereich deaktiviert ist) und ist
idempotent: ein zweiter Lauf findet die kanonische Einheit vor und schreibt
nichts mehr.

Das Modul ist auf Modulebene bewusst HA-frei: Recorder- und Registry-Importe
passieren lazy innerhalb der Funktionen (try/except ImportError), damit das
Modul auch in HA-Versionen ohne Recorder-API importierbar bleibt und die
Unit-Tests ohne echte HA-Installation laufen.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

__all__ = [
    "CANONICAL_VOLUME_UNIT",
    "LEGACY_VOLUME_UNIT",
    "VOLUME_UNIT_CLASS",
    "async_migrate_legacy_volume_statistics",
    "canonical_volume_unit",
]

LEGACY_VOLUME_UNIT = "ml"
CANONICAL_VOLUME_UNIT = "mL"
VOLUME_UNIT_CLASS = "volume"

# unique_id-Suffixe der beiden betroffenen Sensoren (sensor.py). Nur Sensoren
# mit state_class landen in der Recorder-Statistics-Engine — die anderen
# Geräte-Domains erzeugen per HA-Regel keine Recorder-Statistik.
_LEGACY_VOLUME_SENSOR_KEYS: tuple[str, ...] = (
    "sensor_drinks_today",
    "sensor_lifetime_total",
)

# Fallback-Filter (nur wenn die Registry-Auflösung nichts liefert):
# statistic_ids, die eindeutig zu unseren beiden Volumen-Sensoren gehören.
# Der Prefix entsteht aus dem Device-Namen "Health-O-Mat <Person>" (entity.py),
# die Endungen aus den Objekt-IDs der beiden Sensoren.
_FALLBACK_STATISTIC_ID_PREFIX = "sensor.health_o_mat_"
_FALLBACK_STATISTIC_ID_SUFFIXES: tuple[str, ...] = ("_drinks_today", "_lifetime_total")

# Schlüssel im hass.data, unter dem der Recorder seine Instanz ablegt
# (homeassistant.helpers.recorder: DATA_INSTANCE). Der Import ist optional —
# ohne HA-Recorder-Helfer gilt das Literal.
_RECORDER_INSTANCE_KEY = "recorder_instance"


def canonical_volume_unit(unit: str | None) -> str | None:
    """Legacy-Volume-Einheit auf die kanonische HA-Einheit abbilden.

    "ml" / "ML" / " ml " → "mL". Die bereits kanonische "mL" und alles andere
    → None (nichts zu tun). Die Zuordnung ist verlustfrei: "ml" und "mL" sind
    dieselbe physikalische Größe, HA verlangt für die Unit-Class "volume" aber
    zwingend die Schreibweise "mL".
    """
    if not isinstance(unit, str):
        return None
    normalized = unit.strip()
    if not normalized or normalized == CANONICAL_VOLUME_UNIT:
        return None
    if normalized.lower() == LEGACY_VOLUME_UNIT:
        return CANONICAL_VOLUME_UNIT
    return None


def _recorder_instance_key() -> str:
    """DATA_INSTANCE des Recorders — mit Fallback auf das Literal."""
    try:
        from homeassistant.helpers.recorder import DATA_INSTANCE
    except ImportError:  # pragma: no cover - nur ohne HA-Recorder-Helfer
        return _RECORDER_INSTANCE_KEY
    return DATA_INSTANCE


def _recorder_ready(hass: HomeAssistant) -> bool:
    """True, wenn der Recorder eingerichtet ist.

    Bewusst passiv: es wird weder ``get_instance()`` aufgerufen noch der
    Recorder gestartet — es wird nur geprüft, ob die Recorder-Instanz bereits
    in ``hass.data`` liegt. Fehlt sie, wird die Migration übersprungen und
    beim nächsten Setup nachgeholt (siehe Modul-Docstring).
    """
    data = getattr(hass, "data", None)
    if not isinstance(data, dict):
        return False
    return data.get(_recorder_instance_key()) is not None


def _load_entity_registry() -> Any | None:
    """Entity-Registry-Helfer laden (lazy, tolerant) — None ohne Registry."""
    try:
        from homeassistant.helpers import entity_registry as er
    except ImportError:  # pragma: no cover - nur ohne HA-Registry
        return None
    return er


def _resolve_statistic_entity_ids(hass: HomeAssistant, entry: ConfigEntry) -> set[str]:
    """Entity-IDs der beiden Volumen-Sensoren — read-only aus der Registry.

    Es wird KEINE entity_id konstruiert (Person-Slug/Sprache-abhängig): die
    Zuordnung läuft über die stabile unique_id ({entry_id}_{key}). Die Registry
    wird nur gelesen, nichts wird angelegt, geändert oder entfernt.
    """
    er = _load_entity_registry()
    if er is None:
        return set()
    registry = er.async_get(hass)
    entries = er.async_entries_for_config_entry(registry, entry.entry_id)
    wanted = {f"{entry.entry_id}_{key}" for key in _LEGACY_VOLUME_SENSOR_KEYS}
    return {
        item.entity_id
        for item in entries
        if getattr(item, "platform", None) == "sensor"
        and getattr(item, "unique_id", None) in wanted
    }


def _fallback_statistic_entity_ids(metadata: list[dict] | None) -> set[str]:
    """statistic_ids aus einem ungefilterten Recorder-Scan → nur unsere Volumen-Sensoren.

    Kriterium: Prefix "sensor.health_o_mat_" UND Endung "_drinks_today" bzw.
    "_lifetime_total". Damit bleiben Fremde Domains, Fremd-Integrationen und
    Nicht-Volume-IDs unserer eigenen Sensoren (%, mmHg, mg, d, BPM) außen vor.
    """
    result: set[str] = set()
    for item in metadata or []:
        if not isinstance(item, dict):
            continue
        statistic_id = item.get("statistic_id")
        if not isinstance(statistic_id, str):
            continue
        if not statistic_id.startswith(_FALLBACK_STATISTIC_ID_PREFIX):
            continue
        if statistic_id.endswith(_FALLBACK_STATISTIC_ID_SUFFIXES):
            result.add(statistic_id)
    return result


def _load_recorder_api() -> tuple[Any, Any] | None:
    """(async_list_statistic_ids, async_update_statistics_metadata) oder None.

    Lazy Import mit try/except ImportError: eine HA-Version ohne Recorder-API
    darf die Integration nicht am Import hindern.
    """
    try:
        from homeassistant.components.recorder import statistics as recorder_statistics
    except ImportError:  # pragma: no cover - nur ohne Recorder-Komponente
        return None
    return (
        recorder_statistics.async_list_statistic_ids,
        recorder_statistics.async_update_statistics_metadata,
    )


async def async_migrate_legacy_volume_statistics(hass: HomeAssistant, entry: ConfigEntry) -> int:
    """Migriert die Recorder-Metadaten unserer Volumen-Sensoren von "ml" auf "mL".

    Gibt die Anzahl migrierter statistic_ids zurück (0 = nichts zu tun). Der
    öffentliche Einstieg wirft NIE: Fehler werden geloggt, damit das Setup der
    Integration nie daran scheitern kann. Ist der Recorder noch nicht bereit,
    wird die Migration beim nächsten Setup (HA-Neustart/Entry-Reload)
    nachgeholt — idempotent und verlustfrei.
    """
    try:
        return await _async_migrate_inner(hass, entry)
    except Exception:  # noqa: BLE001 - die Migration ist nie setup-kritisch
        _LOGGER.exception(
            "Health-O-Mat: Recorder-Statistik-Migration für Entry %s fehlgeschlagen",
            getattr(entry, "entry_id", "?"),
        )
        return 0


async def _async_migrate_inner(hass: HomeAssistant, entry: ConfigEntry) -> int:
    """Eigentliche Migration (Fehler werden vom Aufrufer abgefangen)."""
    if not _recorder_ready(hass):
        _LOGGER.debug(
            "Health-O-Mat: Recorder nicht eingerichtet — Statistik-Migration wird "
            "beim nächsten Setup (HA-Neustart/Entry-Reload) nachgeholt"
        )
        return 0

    api = _load_recorder_api()
    if api is None:
        _LOGGER.debug(
            "Health-O-Mat: Recorder-API nicht verfügbar — Statistik-Migration übersprungen"
        )
        return 0
    list_statistic_ids, update_statistics_metadata = api

    entity_ids = _resolve_statistic_entity_ids(hass, entry)
    metadata: list[dict] = []
    if entity_ids:
        metadata = await list_statistic_ids(hass, statistic_ids=entity_ids)
    else:
        # Registry liefert nichts (z. B. Bereich "Getränke" deaktiviert) →
        # Sicherheitsnetz: ungefilterter Recorder-Scan, eng gefiltert auf unsere
        # beiden Volumen-Sensoren. Siehe Modul-Docstring.
        metadata = await list_statistic_ids(hass)
        entity_ids = _fallback_statistic_entity_ids(metadata)
        if not entity_ids:
            _LOGGER.debug(
                "Health-O-Mat: Keine Volumen-Statistiken gefunden — Migration übersprungen"
            )
            return 0

    migrated = 0
    for item in metadata or []:
        if not isinstance(item, dict):
            continue
        statistic_id = item.get("statistic_id")
        if not statistic_id or statistic_id not in entity_ids:
            continue
        unit = item.get("statistics_unit_of_measurement")
        if unit is None:
            # Ältere Kern-Versionen liefern den Einheiten-Key unter
            # "unit_of_measurement". BEWUSSTE Toleranz gegen API-Drift des
            # Kerns (kein YAGNI): der Key-Name hat sich zwischen HA-Versionen
            # geändert, die Semantik ("die gemessene Einheit") nicht.
            unit = item.get("unit_of_measurement")
        canonical = canonical_volume_unit(unit)
        if canonical is None:
            continue
        # Achtung: async_update_statistics_metadata ist ein Sync-@callback
        # (KEIN Coroutine) — ein await hier wäre ein Fehler.
        # new_unit_class MUSS mitgegeben werden: ohne ihn meldet der Kern
        # eine Deprecation ("breaks_in_ha_version=2026.11") und leitet die
        # Unit-Class aus der Einheit ab — "mL" gehört zu "volume".
        update_statistics_metadata(
            hass,
            statistic_id,
            new_unit_of_measurement=canonical,
            new_unit_class=VOLUME_UNIT_CLASS,
        )
        migrated += 1
        _LOGGER.info(
            "Health-O-Mat: Statistik-Metadaten von '%s' auf '%s' migriert (%s)",
            LEGACY_VOLUME_UNIT,
            CANONICAL_VOLUME_UNIT,
            statistic_id,
        )

    if migrated:
        _LOGGER.info("Health-O-Mat: %s Recorder-Statistik-Metadaten migriert (ml → mL)", migrated)
    return migrated

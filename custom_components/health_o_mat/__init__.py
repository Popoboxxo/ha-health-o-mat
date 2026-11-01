"""HA Health-O-Mat — Integration Setup."""

from __future__ import annotations

import inspect
import logging
from collections.abc import Callable
from datetime import datetime
from typing import Any, NamedTuple

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util
from homeassistant.util import slugify

from . import areas, logic
from .const import (
    DEFAULT_DAILY_GOAL_ML,
    DEFAULT_DIA_THRESHOLD,
    DEFAULT_QUICK_DRINKS,
    DEFAULT_SYS_THRESHOLD,
    DOMAIN,
    LAB_MARKERS,
    LAB_REPORT_REF_MAX_LEN,
    OPTION_LAB_CUSTOM_MARKERS,
    OPTION_LAB_HIDDEN_CATEGORIES,
    OPTION_LAB_REF_OVERRIDES,
    OPTION_LAB_RETENTION_MONTHS,
    OPTION_WEEKLY_REPORT,
    WELLBEING_STATES,
)
from .entity import effective_person, signal_refresh
from .frontend import async_setup_frontend, async_unregister_frontend
from .migration import (
    NON_BLOCKING_SKIP_REASONS,
    MigrationPlan,
    build_migration_plan,
    custom_lab_target,
    parse_custom_lab_key,
    parse_quick_drink_index,
    quick_drink_target,
)
from .panel import async_apply_panel_state
from .reminders import (
    async_send_notification,
    async_setup_reminders,
    async_unload_reminders,
    collect_weekly_metrics,
    normalize_weekly_report,
    render_weekly_report_markdown,
    weekly_report_title,
)
from .statistics import async_migrate_legacy_volume_statistics
from .store import HealthOMatStore, async_load_archive_store
from .ws_api import async_register_ws_api

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.TEXT,
    Platform.NUMBER,
    Platform.SELECT,
]

# Keys in hass.data[DOMAIN], die KEINE Config-Entry-Runtime-Daten sind und
# daher bei Entry-Iterationen (Services, Unload) übersprungen werden müssen:
# "shared" (Store) und "signal" (Legacy).
_NON_ENTRY_KEYS = ("shared", "signal")

# Alle öffentlichen Service-Namen. Der Idempotenz-Guard in
# `_register_services` prüft sie VOLLSTÄNDIG: ein einzelner bereits
# vorhandener Service (z. B. `add_drink` aus einer älteren Registrierung)
# darf die Registrierung der übrigen Services nicht verhindern.
_SERVICE_NAMES = (
    "add_drink",
    "add_blood_pressure",
    "remove_last_entry",
    "void_entry",
    "restore_entry",
    "export_csv",
    "import_csv",
    "backup",
    "restore_backup",
    "set_wellbeing",
    "weekly_report",
    "add_lab_value",
    "add_lab_report",
    "remove_last_lab_value",
    "remove_lab_report",
)

# Config entry version that carries the entity id migration (REQ-HOM-130).
# Kept next to the handler so `tests/test_entry_migration.py` can assert it
# equals `HealthOMatConfigFlow.VERSION` (drift guard).
ENTITY_ID_MIGRATION_VERSION = 3

type HealthOMatConfigEntry = ConfigEntry[HealthOMatData]


# Vergleichbarer Stand der Lab-Options: (Custom-Marker nach `key` sortiert,
# Ref-Overrides nach Marker sortiert, verborgene Kategorien als Set).
class LabOptionsSnapshot(NamedTuple):
    """Normalisierter Stand der drei Lab-Options eines Entries.

    ``markers`` entscheidet über die **Entity-Menge** (ein Sensor je Marker) und
    löst damit als einziges Feld einen Reload aus. ``overrides`` wird von den
    Entities live aus ``entry.options`` gelesen (nur ein Refresh nötig),
    ``hidden`` ist ein reines Anzeige-Flag des Panels (ws_api, kein Entity).
    """

    markers: tuple[dict, ...]
    overrides: tuple[tuple[str, dict], ...]
    hidden: frozenset[str]


def _lab_options_snapshot(options: dict) -> LabOptionsSnapshot:
    """Vergleichbarer Snapshot der Lab-Options (Review-Fix B-1, geschärft N-2).

    Die Lab-Entities (ein Sensor je Marker) entstehen beim Setup aus
    ``lab_custom_markers``. Ändert sich dieser Satz, muss der Entry neu geladen
    werden — deshalb wird der Stand, aus dem die Entities gebaut wurden, in
    ``HealthOMatData.lab_options`` gespiegelt.

    Normalisiert über die `logic.*`-Normalisierer und reihenfolge-unabhängig
    (Custom-Marker nach ihrem stabilen `key`, verborgene Kategorien als Set):
    reines Format-Rauschen (Whitespace, Zahlen als Strings, Listen-Reihenfolge)
    darf keinen Reload auslösen.
    """
    markers = logic.normalize_lab_custom_markers(options.get(OPTION_LAB_CUSTOM_MARKERS))
    overrides = logic.normalize_lab_ref_overrides(options.get(OPTION_LAB_REF_OVERRIDES))
    hidden = logic.normalize_lab_hidden_categories(options.get(OPTION_LAB_HIDDEN_CATEGORIES))
    return LabOptionsSnapshot(
        markers=tuple(sorted(markers, key=lambda marker: marker["key"])),
        overrides=tuple(sorted(overrides.items())),
        hidden=frozenset(hidden),
    )


class HealthOMatData:
    """Laufzeitdaten eines Config-Entries (= eine Person)."""

    def __init__(self) -> None:
        self.daily_goal_ml: int = DEFAULT_DAILY_GOAL_ML
        self.custom_amount_ml: int = 250
        self.sys_threshold: int = DEFAULT_SYS_THRESHOLD
        self.dia_threshold: int = DEFAULT_DIA_THRESHOLD
        self.areas: dict[str, bool] = dict(areas.DEFAULT_AREAS)
        # B-1: Lab-Options, aus denen die Entities beim Setup gebaut wurden.
        # Startwert = "keine Lab-Options" (das ist der Entity-Satz eines
        # frischen Setups ohne Custom-Marker/Overrides), damit ein Entry ohne
        # Lab-Options keinen Reload auslöst.
        self.lab_options: LabOptionsSnapshot = _lab_options_snapshot({})
        # S-4: zuletzt gesehener `set_lifetime_ml`-Optionswert. Nur eine
        # explizite Änderung darf den Lebenszähler setzen — sonst würde jede
        # Options-Änderung (z. B. Tagesziel) den gewachsenen Zähler zurücksetzen.
        self.lifetime_setting_seen: int | None = None


async def _async_migrate_entity_ids(
    hass: HomeAssistant, entry: HealthOMatConfigEntry
) -> MigrationPlan | None:
    """Rename F-1/F-2 entities to the language-independent scheme (REQ-HOM-130).

    Returns the executed plan when nothing was skipped and no schema drift
    remains, ``None`` otherwise. Fail-closed: the caller keeps the entry version
    untouched on ``None``, so HA retries the whole pass on the next start.

    Diagnostics contract: each planned skip is reported exactly ONCE — blocking
    reasons inside the single failure summary below, ``custom_entity_id`` as its
    own warning (the entity keeps a hand-picked id on purpose). Confirmation
    mismatches of a sibling-derived prefix (device name, device link) collapse into
    exactly ONE warning on the success path — never double-reported, never blocking.
    The drift check therefore ignores entities that already carry a planned skip
    (they intentionally stay on their old id), and one summary line carries the
    whole failure (counts plus pairs). The plan itself is returned instead of a
    bare ``bool`` so the caller's success line can report the counters.
    """
    registry = er.async_get(hass)
    entries = er.async_entries_for_config_entry(registry, entry.entry_id)

    device_registry = dr.async_get(hass)
    # HA 2026.9: `async_get_device(identifiers=...)` is deprecated.
    device = device_registry.async_get_device_by_identifier(
        (DOMAIN, entry.entry_id), entry.entry_id
    )
    if device is None:
        fallback_id = next((reg.device_id for reg in entries if reg.device_id), None)
        device = device_registry.async_get(fallback_id) if fallback_id else None
    hint = slugify(device.name_by_user or device.name) if device is not None else None

    # The registry is authoritative; the state check is best effort (restored
    # states only exist after EVENT_HOMEASSISTANT_START).
    occupied = {reg.entity_id for reg in registry.entities.values()}
    occupied.update(state.entity_id for state in hass.states.async_all())

    plan = build_migration_plan(
        entry.entry_id,
        [
            {
                "entity_id": reg.entity_id,
                "unique_id": reg.unique_id,
                "translation_key": reg.translation_key,
                "device_id": reg.device_id,
            }
            for reg in entries
        ],
        device_slug_hint=hint,
        device_id=device.id if device is not None else None,
        catalog_keys=LAB_MARKERS,
        occupied_entity_ids=occupied,
    )

    known_marker_keys = {
        marker["key"]
        for marker in logic.normalize_lab_custom_markers(
            entry.options.get(OPTION_LAB_CUSTOM_MARKERS)
        )
    }
    for rename in plan.renames:
        key = parse_custom_lab_key(rename.unique_id, entry.entry_id, LAB_MARKERS)
        if key is not None and key not in known_marker_keys:
            _LOGGER.warning(
                "Entity-ID-Migration %s: stale_marker_key %s (%s) — Entity wird "
                "umbenannt, der Key fehlt in den Options",
                entry.title,
                key,
                rename.source_entity_id,
            )

    mapping = {item.source_entity_id: item.target_entity_id for item in plan.renames}
    if mapping:
        try:
            # Coroutine since HA 2026.8 — must be awaited (B-1).
            await er.async_migrate_entries(
                hass,
                entry.entry_id,
                lambda reg: (
                    {"new_entity_id": mapping[reg.entity_id]} if reg.entity_id in mapping else None
                ),
            )
        except ValueError as err:
            # Race with a parallel registry write: HA would turn this into
            # MIGRATION_ERROR; we treat it as a failed pass with a clear cause.
            _LOGGER.error("Entity-ID-Migration %s abgebrochen: %s", entry.title, err)
            return None

    # Drift diagnosis: every F-1/F-2 entity must now sit on its expected id.
    # Planned skips are excluded: a skipped entity stays on its old id by
    # design, so reporting it here as well would duplicate the skip (F-1).
    planned_skips = {skip.unique_id for skip in plan.skipped}
    drift: list[tuple[str, str]] = []
    if plan.device_slug is not None:
        for reg in er.async_entries_for_config_entry(registry, entry.entry_id):
            if reg.unique_id in planned_skips:
                continue
            index = parse_quick_drink_index(reg.unique_id, entry.entry_id)
            key = parse_custom_lab_key(reg.unique_id, entry.entry_id, LAB_MARKERS)
            if index is not None:
                expected = f"button.{quick_drink_target(plan.device_slug, index)}"
            elif key is not None:
                expected = f"sensor.{custom_lab_target(plan.device_slug, key)}"
            else:
                continue
            if reg.entity_id != expected:
                drift.append((reg.entity_id, expected))

    # ``custom_entity_id`` is a user decision, not a failure: the entity keeps
    # the id the user gave it. It is reported once as a warning and does not
    # block the pass (otherwise the entry would never migrate).
    for skip in plan.skipped:
        if skip.reason in NON_BLOCKING_SKIP_REASONS:
            _LOGGER.warning(
                "Entity-ID-Migration %s: %s bleibt unverändert (Grund: %s)",
                entry.title,
                skip.source_entity_id,
                skip.reason,
            )

    blocking = [skip for skip in plan.skipped if skip.reason not in NON_BLOCKING_SKIP_REASONS]
    if blocking or drift:
        # The ONE summary of the failure path (F-2): counts plus the pair list
        # (source, unique_id, target, reason) — without it the user only sees
        # MIGRATION_ERROR / "unavailable" and has no actionable cause.
        _LOGGER.warning(
            "Entity-ID-Migration %s fehlgeschlagen: %d übersprungen, %d schema_drift — "
            "übersprungen (Quelle, unique_id, Ziel, Grund): %s; "
            "schema_drift (Ist, Soll): %s",
            entry.title,
            len(blocking),
            len(drift),
            [
                (skip.source_entity_id, skip.unique_id, skip.target_entity_id, skip.reason)
                for skip in blocking
            ],
            drift,
        )
        return None

    if plan.warnings:
        # The prefix was derived from the entities that are being renamed, so a
        # diverging device name or device link is only a confirmation mismatch:
        # ONE warning on the success path, never a blocker (0.17.1 production bug).
        _LOGGER.warning(
            "Entity-ID-Migration %s: Präfix %s aus den Entity-IDs abgeleitet, "
            "Bestätigung weicht ab (%s) — Migration läuft weiter",
            entry.title,
            plan.device_slug,
            ", ".join(plan.warnings),
        )
    return plan


async def async_migrate_entry(hass: HomeAssistant, entry: HealthOMatConfigEntry) -> bool:
    """Config entry migration: v1 quick_drinks -> options, v2 -> v3 entity ids.

    v1 (<= v0.4.0) kept `quick_drinks` in entry.data (only removable by
    re-creating the entry = data loss). v2 (<= v0.16.2) still registered
    quick-drink buttons and custom lab markers from user text; v3 renames them
    to `quick_drink_<n>` / `lab_<key>` (REQ-HOM-130).

    All-or-nothing: data, options and version are written in exactly ONE
    `async_update_entry` call, and only when the entity pass fully succeeded.

    Logging contract (F-4): the success path emits exactly ONE INFO line, and
    it carries the counters (`renamed=N skipped=M`) for support and release
    verification. INFO (not WARNING) is deliberate — a successful migration is
    a one-time, expected event, so WARNING would be permanent noise in the
    default log (WARNING and above). Failures are unaffected: they stay visible
    at the default level (WARNING summary / ERROR abort in the pass above).
    """
    if entry.version > ENTITY_ID_MIGRATION_VERSION:
        # Defensive: HA only calls the handler for entry.version < flow.VERSION.
        _LOGGER.error(
            "Config entry %s hat Version %s > %s — Downgrade nicht unterstützt",
            entry.title,
            entry.version,
            ENTITY_ID_MIGRATION_VERSION,
        )
        return False

    data = dict(entry.data)
    options = dict(entry.options)

    if entry.version == 1:
        options.setdefault("quick_drinks", [dict(qd) for qd in DEFAULT_QUICK_DRINKS])
        data = {k: v for k, v in data.items() if k != "quick_drinks"}

    if entry.version < ENTITY_ID_MIGRATION_VERSION:
        plan = await _async_migrate_entity_ids(hass, entry)
        if plan is None:
            # No async_update_entry: the version stays, HA retries on the next
            # setup and the v1 data step is not half-written either.
            return False

        hass.config_entries.async_update_entry(
            entry, data=data, options=options, version=ENTITY_ID_MIGRATION_VERSION
        )
        _LOGGER.info(
            "Config entry %s: auf Version %s migriert (renamed=%d skipped=%d)",
            entry.title,
            ENTITY_ID_MIGRATION_VERSION,
            len(plan.renames),
            len(plan.skipped),
        )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: HealthOMatConfigEntry) -> bool:
    """Einrichtung: ein Entry = eine Person = ein Device."""
    hass.data.setdefault(DOMAIN, {})
    shared: dict = hass.data[DOMAIN].setdefault("shared", {})

    store: HealthOMatStore | None = shared.get("store")
    if store is None:
        store = HealthOMatStore(hass)
        await store.async_load()
        shared["store"] = store

    await store.set_person(entry.entry_id, effective_person(entry))

    lifetime_start = entry.data.get("lifetime_start_ml")
    if lifetime_start:
        await store.set_lifetime_start(entry.entry_id, int(lifetime_start))

    # B-2: Archiv-Store immer laden, wenn die Datei existiert — unabhängig von
    # `retention_months`. Sonst fehlt das Archiv nach einem Neustart mit
    # Retention AUS in Backup/Export/Restore (Lifetime wäre inkonsistent).
    await async_load_archive_store(hass, create=False)

    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name=f"health_o_mat_{entry.entry_id}",
        update_method=lambda: dt_util.now().isoformat(),
        update_interval=None,
    )

    # Registry für Services + Plattformen (v0.1.0-Bug: Entry-Registry fehlte)
    hass.data[DOMAIN][entry.entry_id] = {
        "coordinator": coordinator,
        "store": store,
        "data": HealthOMatData(),
    }
    entry.runtime_data = hass.data[DOMAIN][entry.entry_id]["data"]

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Recorder-Statistik-Metadaten der Volumen-Sensoren von "ml" auf "mL"
    # nachziehen (P1: sonst bricht HA die Langzeitstatistik ab). Läuft NACH dem
    # Plattform-Setup, weil die Entity-IDs erst dann in der Registry stehen.
    # Ist der Recorder dann noch nicht bereit, wird die Migration beim
    # nächsten Setup (HA-Neustart/Entry-Reload) nachgeholt — idempotent und
    # verlustfrei. Nie setup-kritisch: Fehler werden im Modul geloggt, nicht
    # geworfen.
    await _async_migrate_recorder_statistics(hass, entry)

    _register_services(hass)
    await _async_setup_frontend_layer(hass)
    _apply_options(hass, entry)
    # Opt-in-Sidebar-Panel (L2) erst NACH der Options-Auswertung anwenden.
    await _async_apply_panel_layer(hass)
    await _apply_retention(hass, entry, store)
    await _apply_lab_retention(hass, entry, store)
    await async_setup_reminders(hass, entry, store)
    entry.async_on_unload(entry.add_update_listener(_options_updated))

    return True


async def _async_migrate_recorder_statistics(
    hass: HomeAssistant, entry: HealthOMatConfigEntry
) -> None:
    """Recorder-Statistik-Metadaten migrieren — nie setup-kritisch.

    Der Einstieg in statistics.py wirft bereits nicht; die zusätzliche
    Absicherung hier hält das Setup zusätzlich sicher (z. B. wenn die
    Recorder-API in einer fremden HA-Version fehlt). Die doppelte Barriere ist
    BEWUSST: das Vertrag "Setup scheitert NIE" soll an zwei unabhängigen
    Stellen abgesichert sein (Modul + Aufrufer) — ein Fehler in einer der
    beiden Schichten darf das Setup der Integration nicht kippen. Die
    Migration ist idempotent und verlustfrei.
    """
    try:
        await async_migrate_legacy_volume_statistics(hass, entry)
    except Exception:  # noqa: BLE001 - die Migration ist nie setup-kritisch
        _LOGGER.exception("Health-O-Mat: Recorder-Statistik-Migration nicht ausführbar")


def _retention_months(entry) -> int:
    """Retention in Monaten aus den Options (0/ungültig = AUS)."""
    try:
        return int(entry.options.get("retention_months") or 0)
    except (TypeError, ValueError):
        return 0


def _lab_retention_months(entry) -> int:
    """Labor-Retention in Monaten aus den Options (0/ungültig = AUS)."""
    try:
        return int(entry.options.get(OPTION_LAB_RETENTION_MONTHS) or 0)
    except (TypeError, ValueError):
        return 0


async def _apply_lab_retention(hass: HomeAssistant, entry, store: HealthOMatStore) -> None:
    """Labor-Retention: alte aktive Werte voiden (REQ-HOM-129).

    Eigener Schritt NEBEN `_apply_retention` (Getränke/BD) — kein Archiv, keine
    Listenkürzung. Default 0 = no-op; idempotent (voidete Einträge zählen nie
    erneut), Audit nur bei Treffern (macht der Store).
    """
    months = _lab_retention_months(entry)
    if months <= 0:
        return
    cutoff = logic.months_ago(dt_util.now(), months)
    voided = await store.void_lab_readings_before(
        entry.entry_id,
        cutoff.isoformat(),
        audit_limit=_entry_audit_limit(hass, entry.entry_id),
        months=months,
    )
    if voided:
        signal_refresh(hass, entry.entry_id)


async def _get_archive_store(hass: HomeAssistant) -> HealthOMatStore:
    """Archiv-Store einmalig anlegen/laden (Shared-Bereich)."""
    archive = await async_load_archive_store(hass, create=True)
    if archive is None:  # pragma: no cover - create=True liefert immer einen Store
        raise RuntimeError("Archiv-Speicher nicht verfügbar")
    return archive


def _kept_with_voided(raw_items: object, moved: list) -> list:
    """Rohliste ohne die ins Archiv wandernden Einträge (voided bleibt erhalten).

    `moved` enthält nur aktive Einträge (partitioniert auf der aktiven Sicht);
    voided Einträge sind dort nie enthalten und bleiben damit im Haupt-Store.
    Die Reihenfolge des Rohbestands bleibt unverändert.
    """
    items = raw_items if isinstance(raw_items, list) else []
    moved_ids = {id(item) for item in moved}
    return [item for item in items if id(item) not in moved_ids]


async def _apply_retention(hass: HomeAssistant, entry, store: HealthOMatStore) -> None:
    """Optionale Retention beim Setup (REQ-HOM-109).

    Default AUS (0/None): sofortiger No-op — exakt das bisherige Verhalten,
    nichts wird verschoben und kein Archiv-Store angelegt. Aktiv: Einträge
    älter als `retention_months` wandern on-read ins Archiv; der Lebenszähler
    bleibt unverändert.

    Partitioniert wird ausschließlich auf der **aktiven** Sicht: voided
    (gelöschte) Einträge werden nie archiviert, sondern bleiben im Haupt-Store
    — sonst würde ein gelöschter Eintrag im Archiv wieder auftauchen (M2a).
    `archived_counts` zählt entsprechend nur aktive Verschiebungen.
    """
    months = _retention_months(entry)
    if months <= 0:
        return
    current = store.entry(entry.entry_id)
    cutoff = logic.months_ago(dt_util.now(), months)
    _, moved_drinks = logic.partition_by_cutoff(store.active_drinks(entry.entry_id), cutoff)
    _, moved_readings = logic.partition_by_cutoff(store.active_readings(entry.entry_id), cutoff)
    if not moved_drinks and not moved_readings:
        return
    kept_drinks = _kept_with_voided(current.get("drinks", []), moved_drinks)
    kept_readings = _kept_with_voided(current.get("readings", []), moved_readings)
    archive = await _get_archive_store(hass)
    # S-5: Erst das Archiv schreiben, dann im Haupt-Store entfernen. Schlägt
    # der Archiv-Save fehl, bleibt der Haupt-Store unverändert (kein Daten-
    # verlust); schlägt danach der Haupt-Save fehl, wird das Archiv zurück-
    # gerollt.
    previous_archive = archive.raw_entries_copy()
    try:
        await archive.append_archive(entry.entry_id, moved_drinks, moved_readings)
    except Exception:
        # In-Memory-Stand des Archivs zurücksetzen (der Save ist fehlgeschlagen;
        # ein erneuter Versuch darf keine Duplikate sehen).
        try:
            await archive.async_set_entries(previous_archive)
        except Exception:  # noqa: BLE001 - Rollback ist best effort
            _LOGGER.exception("Health-O-Mat: Archiv-Rollback nach Save-Fehler fehlgeschlagen")
        raise
    try:
        await store.apply_retention(entry.entry_id, kept_drinks, kept_readings)
    except Exception:
        try:
            await archive.async_set_entries(previous_archive)
        except Exception:  # noqa: BLE001 - Rollback ist best effort
            _LOGGER.exception("Health-O-Mat: Archiv-Rollback nach Retention-Fehler fehlgeschlagen")
        raise
    signal_refresh(hass, entry.entry_id)


def _mirror_bp_thresholds(rt, opts: dict) -> None:
    """BP-Schwellen aus entry.options in den Runtime-Spiegel übernehmen.

    entry.options ist die Quelle der Wahrheit; rt.sys_threshold/rt.dia_threshold
    sind nur Lese-Spiegel für binary_sensor.py (BP-Warnung). Nur ein gesetzter,
    gültiger Zahlenwert überschreibt den Default — fehlende ('None'/leer) oder
    unbrauchbare (nicht-numerische) Werte lassen den Runtime-Spiegel unverändert.
    """
    for key in ("sys_threshold", "dia_threshold"):
        value = opts.get(key)
        if value is None or value == "":
            continue
        try:
            setattr(rt, key, int(value))
        except (TypeError, ValueError):
            continue


def _apply_options(hass: HomeAssistant, entry) -> None:
    """Options-Werte zur Laufzeit übernehmen.

    entry.options ist die einzige Quelle der Wahrheit für daily_goal_ml (Audit C-2).
    rt.daily_goal_ml ist nur ein Lese-Spiegel für schnellen Zugriff in Sensoren/
    Binary-Sensoren — er wird ausschließlich hier und in _options_updated() aus
    entry.options nachgezogen, nie eigenständig geschrieben (auch nicht von der
    DailyGoalNumber-Entity, siehe number.py).
    """
    rt = entry.runtime_data
    opts = entry.options or {}
    rt.areas = areas.active_areas(opts)
    rt.lab_options = _lab_options_snapshot(opts)
    if opts.get("daily_goal_ml"):
        rt.daily_goal_ml = int(opts["daily_goal_ml"])
    _mirror_bp_thresholds(rt, opts)
    # S-4: Optionswert nur als "zuletzt gesehen" merken, nicht anwenden. Ein
    # späterer Options-Save ohne explizite Änderung darf den Zähler nicht
    # zurücksetzen; nur `_options_updated` wendet eine echte Änderung an.
    try:
        rt.lifetime_setting_seen = int(opts.get("set_lifetime_ml") or 0)
    except (TypeError, ValueError):
        rt.lifetime_setting_seen = 0
    # `set_lifetime_ml` wird bewusst NICHT hier (Setup/Reload) angewandt: der
    # Options-Wert bleibt dauerhaft gespeichert, ein Reload (z. B. ausgelöst
    # durch eine Bereichs-Umschaltung) würde den gewachsenen Lebenszähler sonst
    # auf den alten Sollwert zurücksetzen. Angewandt wird er ausschließlich im
    # expliziten Options-Änderungspfad `_options_updated`; der Erstanlage-Wert
    # kommt aus `entry.data["lifetime_start_ml"]` (siehe async_setup_entry).


async def _options_updated(hass, entry) -> None:
    """Wird bei jeder entry.options-Änderung aufgerufen (Options-Dialog UND
    DailyGoalNumber.async_set_native_value, siehe number.py — beide schreiben nur
    noch in entry.options, dieser Listener ist der einzige Sync-Punkt zurück in
    den Runtime-Spiegel rt.daily_goal_ml).

    Ein Reload ist genau dann nötig, wenn sich die **Entity-Menge** ändert:
    Personen-Umbenennung (Device-Name), Bereichs-Auswahl und — seit REQ-HOM-122
    (Review-Fix B-1) — die Menge der Custom-Lab-Marker (ein Sensor je Marker).
    Alles andere wird am laufenden Entry nachgezogen.

    Review-Fix N-2: Die übrigen Lab-Options lösen KEINEN Reload mehr aus:
    ``lab_ref_overrides`` lesen sensor.py/binary_sensor.py live über die
    Entity-Properties (ein ``signal_refresh`` genügt), ``lab_hidden_categories``
    ist ein reines Anzeige-Flag des Panels (ws_api._labs_block liest es pro
    Request) und berührt keine Entity. Ein Reload würde dort alle States
    unnötig auf ``unavailable`` setzen.
    """
    rt = entry.runtime_data
    opts = entry.options or {}
    if opts.get("daily_goal_ml"):
        rt.daily_goal_ml = int(opts["daily_goal_ml"])
    _mirror_bp_thresholds(rt, opts)
    store: HealthOMatStore = hass.data[DOMAIN]["shared"]["store"]

    new_areas = areas.active_areas(opts)
    new_lab_options = _lab_options_snapshot(opts)

    # Anzeige-Name geändert → Store synchron halten + Entities neu laden
    # (Device-Name kommt aus den Entities; Reload ist einzig sauberer Weg)
    current_person = store.all_entries().get(entry.entry_id, {}).get("person")
    person_changed = current_person != effective_person(entry)
    # N-2: Nur der Marker-Satz bestimmt die Entity-Menge.
    markers_changed = new_lab_options.markers != rt.lab_options.markers
    if person_changed or new_areas != rt.areas or markers_changed:
        if person_changed:
            await store.set_person(entry.entry_id, effective_person(entry))
        rt.areas = new_areas
        # Snapshot VOR dem Reload setzen: der Reload baut die Entities aus
        # genau diesen Optionen neu auf, ein erneuter Listener-Lauf darf also
        # keinen weiteren Reload auslösen (kein Reload-Loop).
        rt.lab_options = new_lab_options
        # Vor dem Reload: Timer neu aufsetzen (der Reload löst zwar erneut
        # Setup aus, aber bis dahin soll die neue Options-Wahl schon gelten).
        await async_setup_reminders(hass, entry, store)
        hass.async_create_task(hass.config_entries.async_reload(entry.entry_id))
        return  # Reload baut Entities neu auf — kein weiterer Refresh nötig

    # Kein Reload: Overrides/Hidden sind live gelesen bzw. reine Anzeige —
    # den gespiegelten Stand trotzdem nachziehen, damit ein späterer
    # Marker-Vergleich nur die Entity-Menge bewertet.
    rt.lab_options = new_lab_options

    wanted = int(opts.get("set_lifetime_ml") or 0)
    seen = getattr(rt, "lifetime_setting_seen", None)
    if seen is None:
        # Erster Lauf ohne Setup-Spiegel: den aktuellen Optionswert nur merken,
        # nicht anwenden (kein Rücksetzen eines bereits gewachsenen Zählers).
        seen = wanted
    if wanted and wanted != seen:
        await store.set_lifetime_start(entry.entry_id, wanted)
    rt.lifetime_setting_seen = wanted
    # Retention nach Options-Änderung anwenden (idempotent, No-op wenn AUS).
    await _apply_retention(hass, entry, store)
    await _apply_lab_retention(hass, entry, store)
    # Opt-in-Sidebar-Panel: Option enable/disable → Panel registrieren/entfernen.
    await _async_apply_panel_layer(hass)
    # Erinnerungs-/Berichts-Timer an die neuen Optionen anpassen (idempotent).
    await async_setup_reminders(hass, entry, store)
    signal_refresh(hass, entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: HealthOMatConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        await async_unload_reminders(hass, entry.entry_id)
        hass.data[DOMAIN].pop(entry.entry_id, None)
        if not _has_runtime_entries(hass):
            # Letzter Entry entladen → Frontend-Fallback zurückbauen (defensiv:
            # ein Fehler hier darf den Unload-Status nicht kippen).
            try:
                await async_unregister_frontend(hass)
            except Exception:  # noqa: BLE001 - Rückbau ist nie unload-kritisch
                _LOGGER.exception("Health-O-Mat: Frontend-Rückbau fehlgeschlagen")
        # Panel-Zustand domain-weit neu anwenden, den entladenen Entry
        # ausgenommen: verliert das Entfernen/Entladen die letzte
        # Panel-freischaltende Person, wird das Panel jetzt abgemeldet (vorher
        # blieb es bis zum HA-Neustart stehen).
        await _async_apply_panel_layer(hass, exclude_entry_id=entry.entry_id)
    return unload_ok


async def async_remove_entry(hass: HomeAssistant, entry: HealthOMatConfigEntry) -> None:
    """Langzeitstatistik der Entities eines gelöschten Entrys aufräumen.

    Post-Release-Befund 2: Beim Entfernen eines Config-Entry über ``DELETE``
    leert HA nur die Entity-Registry (``ent_reg.async_clear_config_entry``,
    ``config_entries.py`` → ``_async_clean_up``). Die ``statistics_meta``-Zeilen
    (und damit die Langzeitstatistik) der Entities bleiben bestehen —
    ``recorder.purge_entities`` entfernt sie nicht, weil eine verwaiste
    Statistik weiterhin eine gültige ``statistic_id`` besitzt.

    Ablauf: Entity-IDs aus der Registry (sie ist beim Aufruf noch gefüllt; HA
    leert sie erst NACH ``async_remove_entry``), danach die zugehörigen
    Statistik-IDs aufräumen. Ein Entity-Statistik-Eintrag heißt exakt wie die
    Entity-ID, deshalb ist die Registry-Liste bereits die Statistik-ID-Liste.

    Bewusst NICHT hier: Löschung des Store-Eintrags, ``unique_id``-Änderungen,
    Registry-Eingriffe. Reines Aufräumen der Recorder-Seite — und defensiv:
    ohne Recorder (nicht eingerichtet/deaktiviert) oder ohne die API in der
    installierten HA-Version wird still übersprungen (debug-Log). Das Entfernen
    der Integration darf NIE an diesem Cleanup scheitern.
    """
    entity_ids = _entry_entity_ids(hass, entry)
    if not entity_ids:
        _LOGGER.debug(
            "Health-O-Mat: keine Entities zu Entry %s — Statistik-Cleanup übersprungen",
            entry.entry_id,
        )
        return
    if await _async_clear_statistics(hass, entity_ids):
        _LOGGER.debug(
            "Health-O-Mat: Langzeitstatistik von %d Entities des Entrys %s entfernt",
            len(entity_ids),
            entry.entry_id,
        )
    else:
        _LOGGER.debug(
            "Health-O-Mat: Recorder nicht verfügbar — Statistik-Cleanup für Entry %s übersprungen",
            entry.entry_id,
        )


def _entry_entity_ids(hass: HomeAssistant, entry: HealthOMatConfigEntry) -> list[str]:
    """Entity-IDs des Entrys aus der Registry (best effort, stabil sortiert).

    Kein ``platform``-Filter: die Registry-Abfrage ist bereits auf den
    ``entry_id`` eingeschränkt, jede zurückgelieferte Entity gehört damit zu
    diesem Entry. Ein zusätzlicher Filter würde bei Registry-Einträgen ohne
    ``platform`` (Alt-Bestand) stillschweigend Statistik-Waisen hinterlassen.
    """
    try:
        registry = er.async_get(hass)
        entries = er.async_entries_for_config_entry(registry, entry.entry_id)
    except Exception:  # Cleanup ist nie remove-kritisch
        _LOGGER.debug(
            "Health-O-Mat: Entity-Registry für Entry %s nicht lesbar",
            getattr(entry, "entry_id", "?"),
            exc_info=True,
        )
        return []
    return sorted(
        {
            str(getattr(reg, "entity_id", "") or "")
            for reg in entries
            if str(getattr(reg, "entity_id", "") or "")
        }
    )


async def _async_clear_statistics(hass: HomeAssistant, statistic_ids: list[str]) -> bool:
    """Statistik-IDs über die Recorder-API aufräumen (True = Aufruf erfolgt).

    Zwei API-Formen, in dieser Reihenfolge (gegen das installierte HA 2026.2.3
    geprüft): die Modul-API ``async_clear_statistics`` aus
    ``homeassistant.components.recorder.statistics``, falls die HA-Version sie
    anbietet (in 2026.2.3 NICHT vorhanden — der Import schlägt dort fehl), sonst
    ``Recorder.async_clear_statistics`` auf der Instanz aus ``get_instance``.
    Ein Fehler in einer der beiden Formen wird geloggt und als "nicht
    aufgeräumt" gemeldet, nie geworfen.
    """
    module_clear = _module_clear_statistics()
    if module_clear is not None:
        try:
            result = module_clear(hass, statistic_ids)
            if inspect.isawaitable(result):
                await result
        except Exception:  # Cleanup ist nie remove-kritisch
            _LOGGER.debug("Health-O-Mat: Statistiken nicht aufräumbar", exc_info=True)
            return False
        return True

    instance_clear = _instance_clear_statistics(hass)
    if instance_clear is None:
        return False
    try:
        instance_clear(statistic_ids)
    except Exception:  # Cleanup ist nie remove-kritisch
        _LOGGER.debug("Health-O-Mat: Statistiken nicht aufräumbar", exc_info=True)
        return False
    return True


def _module_clear_statistics() -> Callable[..., Any] | None:
    """``async_clear_statistics`` aus der Recorder-Statistik-API, sonst ``None``."""
    try:
        from homeassistant.components.recorder import statistics as recorder_statistics
    except ImportError:
        return None
    clear = getattr(recorder_statistics, "async_clear_statistics", None)
    return clear if callable(clear) else None


def _instance_clear_statistics(hass: HomeAssistant) -> Callable[[list[str]], Any] | None:
    """``Recorder.async_clear_statistics`` der laufenden Instanz, sonst ``None``.

    ``get_instance`` wirft, wenn der Recorder nicht eingerichtet ist (bzw. der
    Recorder-Schlüssel fehlt) — das ist der dokumentierte Fall "Recorder
    deaktiviert" und wird hier zu ``None``.
    """
    try:
        from homeassistant.components.recorder import get_instance
    except ImportError:
        return None
    try:
        instance = get_instance(hass)
    except Exception:  # Recorder nicht eingerichtet (nicht gecachter Fehlerpfad)
        return None
    clear = getattr(instance, "async_clear_statistics", None)
    return clear if callable(clear) else None


def _has_runtime_entries(hass: HomeAssistant) -> bool:
    """True, solange noch mindestens ein Entry Runtime-Daten hält."""
    registry = hass.data.get(DOMAIN)
    if not isinstance(registry, dict):
        return False
    for key, value in registry.items():
        if key in _NON_ENTRY_KEYS:
            continue
        if isinstance(value, dict) and "coordinator" in value:
            return True
    return False


def get_runtime_data(hass: HomeAssistant, call: ServiceCall):
    """Person aus einem Service-Call auflösen (Name → Entry).

    Eingleisig statt O(n²): die Config-Entries werden EINMAL in ein
    `{entry_id: person_slug}`-Lookup indexiert; danach genügt ein einziger
    Durchlauf über die Runtime-Registry. Person-Matching und Fehlersemantik
    (keine Person / mehrere ohne Angabe / nicht gefunden) bleiben unverändert.
    """
    wanted = (call.data.get("person") or "").strip().lower()

    # Person-Matching über entry.data["person"] (stabiler Service-Anker) —
    # person_display (Options) ist reine Anzeige und hier bewusst irrelevant.
    persons = {
        cfg_entry.entry_id: (cfg_entry.data.get("person", "") or "").strip().lower()
        for cfg_entry in hass.config_entries.async_entries(DOMAIN)
    }

    matches = []
    for key, value in hass.data.get(DOMAIN, {}).items():
        if key in _NON_ENTRY_KEYS:
            continue
        if not isinstance(value, dict) or "coordinator" not in value:
            continue
        matches.append((key, value, persons.get(key, "")))

    if not matches:
        raise ServiceValidationError("Keine Health-O-Mat-Person eingerichtet")
    if not wanted:
        if len(matches) > 1:
            names = ", ".join(m[2] for m in matches)
            raise ServiceValidationError(
                f"Mehrere Personen vorhanden ({names}) — bitte 'person' angeben"
            )
        return matches[0][0], matches[0][1]
    for key, value, person in matches:
        if person == wanted:
            return key, value
    raise ServiceValidationError(f"Person '{wanted}' nicht gefunden")


async def _async_setup_frontend_layer(hass: HomeAssistant) -> None:
    """Card (Frontend) + WS-API einmalig für die ganze Domain registrieren.

    Wird von JEDEM Entry-Setup aufgerufen; beide Funktionen sind intern
    idempotent (Marker im Shared-Bereich), es entsteht also keine
    Doppel-Registrierung über mehrere Entries. Der Guard hier ist die zweite
    Verteidigungslinie: die UI-Ebene ist ein Zusatz zur Entity-Ebene und darf
    ein Entity-Setup nie zum Scheitern bringen.
    """
    try:
        await async_register_ws_api(hass)
        await async_setup_frontend(hass)
    except Exception:  # noqa: BLE001 - UI-Ebene ist nie setup-kritisch
        _LOGGER.exception("Health-O-Mat: Frontend-/WS-Ebene nicht registrierbar")


async def _async_apply_panel_layer(
    hass: HomeAssistant, exclude_entry_id: str | None = None
) -> None:
    """Wendet den Opt-in-Zustand des Sidebar-Panels an (defensiv).

    Das Panel ist domain-weit EIN Element: es wird registriert, sobald
    mindestens ein Entry die Option `enable_sidebar_panel` gesetzt hat, und
    andernfalls entfernt. `async_apply_panel_state` ist idempotent (Marker im
    Shared-Bereich), mehrfache Aufrufe erzeugen also keine Doppel-Registrierung.
    Die UI-Ebene ist ein Zusatz und darf das Setup nie zum Scheitern bringen.

    `exclude_entry_id` blendet einen Entry aus, der gerade entladen/entfernt
    wird — beim Unload ist er noch in der Registry, soll aber für die
    Panel-Entscheidung nicht mehr zählen.
    """
    try:
        entries = [
            e
            for e in hass.config_entries.async_entries(DOMAIN)
            if exclude_entry_id is None or e.entry_id != exclude_entry_id
        ]
        await async_apply_panel_state(hass, entries)
    except Exception:  # noqa: BLE001 - UI-Ebene ist nie setup-kritisch
        _LOGGER.exception("Health-O-Mat: Sidebar-Panel-Zustand nicht anwendbar")


def _service_actor(call: ServiceCall) -> str | None:
    """HA-User-ID eines Service-Calls (None bei Automationen/anonymen Aufrufen)."""
    user_id = getattr(getattr(call, "context", None), "user_id", None)
    return str(user_id) if user_id else None


def _entry_audit_limit(hass: HomeAssistant, entry_id: str) -> int:
    """Audit-Cap der Person aus `entry.options` (Default 1000, 0 = unbegrenzt)."""
    try:
        entry = hass.config_entries.async_get_entry(entry_id)
    except Exception:  # noqa: BLE001 - Options-Lesen ist nie service-kritisch
        entry = None
    options = getattr(entry, "options", None) if entry is not None else None
    return logic.audit_limit_from_options(options)


def _entry_options(hass: HomeAssistant, entry_id: str) -> dict:
    """`entry.options` eines Entries (leeres Dict bei unbekannter ID)."""
    try:
        entry = hass.config_entries.async_get_entry(entry_id)
    except Exception:  # noqa: BLE001 - Options-Lesen ist nie service-kritisch
        entry = None
    return dict(getattr(entry, "options", None) or {})


def _service_entry_ts(call: ServiceCall, now: datetime) -> str | None:
    """Optionales Service-Feld `ts` validieren (REQ-HOM-120).

    ``None`` bedeutet "kein Zeitpunkt übergeben" → der Aufrufer setzt jetzt.
    Ein ungültiger, zu weit in der Zukunft oder vor 1900 liegender Wert wird
    als ``ServiceValidationError`` gemeldet.
    """
    raw = call.data.get("ts")
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        return None
    parsed = logic.parse_entry_timestamp(raw, now=now)
    if parsed is None:
        raise ServiceValidationError(logic.ENTRY_TS_INVALID_MESSAGE.format(value=raw))
    return parsed.isoformat()


async def _async_require_admin(hass: HomeAssistant, call: ServiceCall) -> None:
    """Admin-Gate für Verwaltungs-Services (z. B. Restore).

    Ein Service-Call OHNE User-ID stammt aus einer Automation/einem Skript und
    gilt als vertrauenswürdig (dokumentiert: Automationen laufen bewusst ohne
    Login). Mit User-ID wird der HA-User geladen und ``is_admin`` geprüft.
    """
    user_id = getattr(getattr(call, "context", None), "user_id", None)
    if not user_id:
        return
    auth = getattr(hass, "auth", None)
    get_user = getattr(auth, "async_get_user", None)
    if get_user is None:
        raise ServiceValidationError("Admin-Prüfung ist nicht verfügbar")
    user = await get_user(user_id)
    if not getattr(user, "is_admin", False):
        raise ServiceValidationError("Dieser Service ist Administratoren vorbehalten")


# Menschliche Bezeichnung der Korrektur-Ziele (Fehlertexte).
_KIND_LABELS: dict[str, str] = {
    "drinks": "Getränke",
    "blood_pressure": "Blutdruckmessungen",
    "wellbeing": "Wohlbefinden-Meldungen",
}

# Laborwerte als viertes Korrektur-Ziel (REQ-HOM-122). `logic.HISTORY_KINDS`
# führt bewusst nur die drei klassischen Ziele; das Lab-Ziel wird deshalb hier
# aufgelöst und über dessen bestehende Store-Methoden bedient (ein Aufruf,
# kein Zweitweg in der API).
_LAB_STATE_KINDS: tuple[str, ...] = ("lab_values",)
_LAB_STATE_ALIASES: dict[str, str] = {
    "lab_value": "lab_values",
    "lab_values": "lab_values",
    "lab_readings": "lab_values",
}
_LAB_VOID_METHOD = "void_lab_reading"
_LAB_RESTORE_METHOD = "restore_lab_reading"


def _normalize_state_kind(kind: object) -> str | None:
    """`kind` → kanonisches Korrektur-Ziel inklusive Laborwerten (None = unbekannt)."""
    if isinstance(kind, str):
        lab_kind = _LAB_STATE_ALIASES.get(kind.strip().lower())
        if lab_kind is not None:
            return lab_kind
    return logic.normalize_history_kind(kind)


async def _set_entry_state(hass: HomeAssistant, call: ServiceCall, *, restore: bool) -> None:
    """Gemeinsamer Pfad für `void_entry`/`restore_entry` (ein Store-Aufruf je Ziel).

    `kind` und `id` werden fachlich validiert; ein unbekanntes/bereits im
    Zielzustand befindliches Ziel wird als `ServiceValidationError` gemeldet
    (kein stiller Erfolg). Schreibwege bleiben die bestehenden `void_*`/
    `restore_*`-Methoden — inklusive Audit-Eintrag und Store-Persistenz.
    """
    entry_id, _info = get_runtime_data(hass, call)
    raw_kind = call.data.get("kind")
    kind = _normalize_state_kind(raw_kind)
    if kind is None:
        allowed = (*logic.HISTORY_KINDS, *_LAB_STATE_KINDS)
        raise ServiceValidationError(
            f"Unbekannter kind '{raw_kind}' — erlaubt: {', '.join(allowed)}"
        )
    item_id = str(call.data.get("id") or "").strip()
    if not item_id:
        raise ServiceValidationError("id fehlt")
    store: HealthOMatStore = hass.data[DOMAIN]["shared"]["store"]
    methods = logic.RESTORE_METHOD_BY_KIND if restore else logic.VOID_METHOD_BY_KIND
    method = methods.get(kind) or (_LAB_RESTORE_METHOD if restore else _LAB_VOID_METHOD)
    changed = await getattr(store, method)(
        entry_id,
        item_id,
        actor=_service_actor(call),
        audit_limit=_entry_audit_limit(hass, entry_id),
    )
    if not changed:
        state = "nicht gelöscht" if restore else "bereits gelöscht"
        raise ServiceValidationError(f"Eintrag '{item_id}' nicht gefunden oder {state}")
    signal_refresh(hass, entry_id)


def _register_services(hass: HomeAssistant) -> None:
    """Öffentliche Services (idempotent registriert).

    Der Guard prüft ALLE Service-Namen: nur wenn wirklich jeder Service schon
    registriert ist, wird abgebrochen. Ein einzelner vorhandener Service (etwa
    `add_drink` nach einem Teil-Reload) blockiert so nicht die Registrierung
    der übrigen — insbesondere des später ergänzten `set_wellbeing`.
    """
    if all(hass.services.has_service(DOMAIN, name) for name in _SERVICE_NAMES):
        return

    async def add_drink(call: ServiceCall) -> None:
        entry_id, _info = get_runtime_data(hass, call)
        ml = int(call.data["amount_ml"])
        if ml <= 0 or ml > 10000:
            raise ServiceValidationError("amount_ml muss zwischen 1 und 10000 liegen")
        now = dt_util.now()
        ts_iso = _service_entry_ts(call, now) or now.isoformat()
        store: HealthOMatStore = hass.data[DOMAIN]["shared"]["store"]
        await store.add_drink(
            entry_id,
            ts_iso,
            ml,
            call.data.get("drink_type") or "Eigen",
            call.data.get("source") or "service",
            created_ts_iso=now.isoformat(),
            actor=_service_actor(call),
            audit_limit=_entry_audit_limit(hass, entry_id),
        )
        signal_refresh(hass, entry_id)

    async def add_blood_pressure(call: ServiceCall) -> None:
        entry_id, _info = get_runtime_data(hass, call)
        store: HealthOMatStore = hass.data[DOMAIN]["shared"]["store"]
        pulse = call.data.get("pulse")
        now = dt_util.now()
        ts_iso = _service_entry_ts(call, now) or now.isoformat()
        await store.add_reading(
            entry_id,
            ts_iso,
            int(call.data["systolic"]),
            int(call.data["diastolic"]),
            int(pulse) if pulse else None,
            call.data.get("note") or "",
            "service",
            created_ts_iso=now.isoformat(),
            actor=_service_actor(call),
            audit_limit=_entry_audit_limit(hass, entry_id),
        )
        signal_refresh(hass, entry_id)

    async def add_lab_value(call: ServiceCall) -> None:
        """Laborwert erfassen (Katalog- oder Custom-Marker, REQ-HOM-122).

        Der Wert wird in die kanonische Einheit umgerechnet; der gedruckte
        Befundwert bleibt als `reported_*` erhalten. Unbekannte Marker/Einheiten
        sind ein `ServiceValidationError` — es wird NIE stillschweigend
        uminterpretiert oder ein Custom-Marker automatisch angelegt.
        """
        entry_id, _info = get_runtime_data(hass, call)
        options = _entry_options(hass, entry_id)
        resolved = logic.resolve_lab_marker(
            call.data["marker"], options.get(OPTION_LAB_CUSTOM_MARKERS)
        )
        if resolved is None:
            raise ServiceValidationError("unknown_marker")
        marker_key, marker_def = resolved
        raw_unit = call.data.get("unit")
        if raw_unit is None and marker_def.get("require_explicit_unit"):
            raise ServiceValidationError("unit_required")
        value = logic.coerce_lab_number(call.data["value"])
        if value is None:
            raise ServiceValidationError("invalid_value")
        try:
            canonical_value, canonical_unit = logic.convert_lab_value(marker_def, value, raw_unit)
        except ValueError as err:
            raise ServiceValidationError(str(err)) from err
        report_ref = (call.data.get("report_ref") or "").strip()[:LAB_REPORT_REF_MAX_LEN] or None
        now = dt_util.now()
        ts_iso = _service_entry_ts(call, now) or now.isoformat()
        store: HealthOMatStore = hass.data[DOMAIN]["shared"]["store"]
        await store.add_lab_reading(
            entry_id,
            ts_iso,
            marker_key,
            canonical_value,
            canonical_unit,
            value,
            raw_unit or canonical_unit,
            report_ref=report_ref,
            created_ts_iso=now.isoformat(),
            actor=_service_actor(call),
            audit_limit=_entry_audit_limit(hass, entry_id),
        )
        signal_refresh(hass, entry_id)

    async def add_lab_report(call: ServiceCall) -> None:
        """Laborbericht (mehrere Werte) als EINEN Vorgang erfassen (REQ-HOM-123).

        Reihenfolge ist Vertrag (§2.5): Person → Zeitpunkt → Zeilen. Eine
        ungültige Zeile lehnt den gesamten Bericht ab; es wird nichts
        geschrieben. Leere Zeilen werden ignoriert.
        """
        entry_id, _info = get_runtime_data(hass, call)
        options = _entry_options(hass, entry_id)
        now = dt_util.now()
        raw_ts = call.data.get("ts")
        try:
            parsed_ts = _service_entry_ts(call, now)
        except ServiceValidationError as err:
            raise ServiceValidationError(
                logic.lab_report_error("invalid_ts", {"value": raw_ts})["message"]
            ) from err
        # Der validierte Originalstring bleibt erhalten (Offset-Schreibweise
        # des Aufrufers), statt ihn in die Systemzone umzurechnen — der
        # Bericht soll exakt den eingegebenen Zeitpunkt tragen (§2.2).
        ts_iso = (
            raw_ts.strip() if parsed_ts is not None and isinstance(raw_ts, str) else now.isoformat()
        )
        rows, error = logic.validate_lab_report_rows(
            call.data.get("values"), options.get(OPTION_LAB_CUSTOM_MARKERS)
        )
        if error is not None:
            raise ServiceValidationError(error["message"])
        report_ref = (call.data.get("report_ref") or "").strip()[:LAB_REPORT_REF_MAX_LEN] or None
        store: HealthOMatStore = hass.data[DOMAIN]["shared"]["store"]
        await store.add_lab_readings(
            entry_id,
            ts_iso,
            rows,
            report_ref=report_ref,
            created_ts_iso=now.isoformat(),
            actor=_service_actor(call),
            audit_limit=_entry_audit_limit(hass, entry_id),
        )
        signal_refresh(hass, entry_id)

    async def remove_lab_report(call: ServiceCall) -> None:
        """Laborbericht verwerfen — alle aktiven Werte eines Zeitpunkts (REQ-HOM-128).

        Mit ``report_ref`` werden nur Einträge mit exakt diesem Tag getroffen.
        Ohne Treffer: ``no_active_report``. Kein Gruppen-Restore — einzeln über
        ``restore_entry`` (``kind: lab_values``).
        """
        entry_id, _info = get_runtime_data(hass, call)
        now = dt_util.now()
        raw_ts = call.data.get("ts")
        try:
            parsed_ts = _service_entry_ts(call, now)
        except ServiceValidationError as err:
            raise ServiceValidationError(
                logic.lab_report_error("invalid_ts", {"value": raw_ts})["message"]
            ) from err
        if parsed_ts is None:
            raise ServiceValidationError(
                logic.lab_report_error("invalid_ts", {"value": raw_ts})["message"]
            )
        # Wie `add_lab_report`: der validierte Originalstring bleibt erhalten.
        ts_iso = raw_ts.strip() if isinstance(raw_ts, str) else parsed_ts.isoformat()
        report_ref = (call.data.get("report_ref") or "").strip()[:LAB_REPORT_REF_MAX_LEN] or None
        store: HealthOMatStore = hass.data[DOMAIN]["shared"]["store"]
        voided = await store.void_lab_report(
            entry_id,
            ts_iso,
            report_ref=report_ref,
            actor=_service_actor(call),
            audit_limit=_entry_audit_limit(hass, entry_id),
        )
        if not voided:
            raise ServiceValidationError(
                logic.lab_report_error("no_active_report", {"ts": ts_iso})["message"]
            )
        signal_refresh(hass, entry_id)

    async def set_wellbeing(call: ServiceCall) -> None:
        """Wohlbefinden melden — per Status-Key ODER numerischem Score (1..N)."""
        entry_id, _info = get_runtime_data(hass, call)
        status = call.data.get("status")
        score = call.data.get("score")
        allowed = [state["key"] for state in WELLBEING_STATES]
        if status is None and score is None:
            raise ServiceValidationError("Entweder 'status' oder 'score' angeben")
        if status is None:
            status = logic.wellbeing_key_for_score(score)
            if status is None:
                raise ServiceValidationError(
                    f"Ungültiger Wohlbefinden-Score '{score}' — erlaubt: 1 bis {len(allowed)}"
                )
        elif status not in allowed:
            raise ServiceValidationError(
                f"Ungültiger Wohlbefinden-Status '{status}' — erlaubt: {', '.join(allowed)}"
            )
        now = dt_util.now()
        ts_iso = _service_entry_ts(call, now) or now.isoformat()
        store: HealthOMatStore = hass.data[DOMAIN]["shared"]["store"]
        await store.set_wellbeing(
            entry_id,
            status,
            ts_iso,
            created_ts_iso=now.isoformat(),
            actor=_service_actor(call),
            audit_limit=_entry_audit_limit(hass, entry_id),
        )
        signal_refresh(hass, entry_id)

    async def remove_last_entry(call: ServiceCall) -> None:
        """Letzte **aktive** Buchung voiden (Undo, drinks|blood_pressure|wellbeing)."""
        entry_id, _info = get_runtime_data(hass, call)
        store: HealthOMatStore = hass.data[DOMAIN]["shared"]["store"]
        kind = logic.normalize_history_kind(call.data.get("kind") or "drinks")
        if kind is None:
            raise ServiceValidationError(
                f"Unbekannter kind '{call.data.get('kind')}' — "
                f"erlaubt: {', '.join(logic.HISTORY_KINDS)}"
            )
        remove_last = getattr(store, logic.REMOVE_LAST_METHOD_BY_KIND[kind])
        removed = await remove_last(
            entry_id,
            actor=_service_actor(call),
            audit_limit=_entry_audit_limit(hass, entry_id),
        )
        if not removed:
            raise ServiceValidationError(f"Keine {_KIND_LABELS[kind]} zum Entfernen")
        signal_refresh(hass, entry_id)

    async def remove_last_lab_value(call: ServiceCall) -> None:
        """Zeitlich neuesten aktiven Laborwert EINES Markers voiden (Undo, §5.2).

        Bewusst marker-spezifisch: Laborwerte kommen befundweise, ein globales
        "letzter Eintrag" wäre mehrdeutig. Entfernt wird der aktive Wert mit
        dem größten `ts` — also der zeitlich neueste, NICHT zwingend der
        zuletzt eingegebene (nachgetragene alte Befunde bleiben unberührt;
        genau das verhindert, dass ein Undo einen älteren Befund trifft).
        `remove_last_lab_reading` voidet (kein Pop) und liefert `False`, wenn
        kein aktiver Wert existiert.
        """
        entry_id, _info = get_runtime_data(hass, call)
        options = _entry_options(hass, entry_id)
        resolved = logic.resolve_lab_marker(
            call.data["marker"], options.get(OPTION_LAB_CUSTOM_MARKERS)
        )
        if resolved is None:
            raise ServiceValidationError("unknown_marker")
        marker_key, _marker_def = resolved
        store: HealthOMatStore = hass.data[DOMAIN]["shared"]["store"]
        changed = await store.remove_last_lab_reading(
            entry_id,
            marker_key,
            actor=_service_actor(call),
            audit_limit=_entry_audit_limit(hass, entry_id),
        )
        if not changed:
            raise ServiceValidationError(
                f"Kein aktiver Wert für Marker '{marker_key}' zum Entfernen"
            )
        signal_refresh(hass, entry_id)

    async def void_entry(call: ServiceCall) -> None:
        """Einen Eintrag als gelöscht markieren (kein Hard-Delete)."""
        await _set_entry_state(hass, call, restore=False)

    async def restore_entry(call: ServiceCall) -> None:
        """Einen gelöschten Eintrag wiederherstellen."""
        await _set_entry_state(hass, call, restore=True)

    async def export_csv(call: ServiceCall) -> None:
        """CSV-Export (Admin-only, wie das WS-Pendant)."""
        await _async_require_admin(hass, call)
        shared = hass.data.get(DOMAIN, {}).get("shared", {})
        store: HealthOMatStore = shared.get("store")
        # B-2: Archiv on demand laden (create=False) — der Shared-Eintrag kann
        # fehlen, wenn die Archiv-Datei erst nach dem Setup entstanden ist.
        archive_store = await async_load_archive_store(hass, create=False)
        from .exporter import async_export_csv

        await async_export_csv(hass, store, call, archive_store=archive_store)

    async def import_csv(call: ServiceCall) -> None:
        entry_id, _info = get_runtime_data(hass, call)
        shared = hass.data.get(DOMAIN, {}).get("shared", {})
        store: HealthOMatStore = shared.get("store")
        from .importer import async_import_csv

        await async_import_csv(
            hass,
            store,
            entry_id,
            call,
            audit_limit=_entry_audit_limit(hass, entry_id),
        )

    async def backup(call: ServiceCall) -> None:
        """JSON-Backup schreiben (Admin-only, wie das WS-Pendant)."""
        await _async_require_admin(hass, call)
        shared = hass.data.get(DOMAIN, {}).get("shared", {})
        store: HealthOMatStore = shared.get("store")
        # B-2: wie export_csv — Archiv on demand nachladen, nie still weglassen.
        archive_store = await async_load_archive_store(hass, create=False)
        from .backup import async_backup

        await async_backup(hass, store, archive_store)

    async def restore_backup(call: ServiceCall) -> None:
        """Backup kontrolliert zurückspielen (Admin-only, optional Dry-Run)."""
        await _async_require_admin(hass, call)
        from .restore import RestoreError, async_restore_command

        try:
            await async_restore_command(hass, dict(call.data), actor=_service_actor(call))
        except RestoreError as err:
            raise ServiceValidationError(str(err)) from err

    async def weekly_report(call: ServiceCall) -> None:
        """Wochenbericht als Markdown-Notification senden (REQ-HOM-118).

        Kein Datei-Schreiben, kein Export-Ordner: der Bericht ist eine reine
        Notification. Ohne ``person`` bekommt jede laufende Person einen
        eigenen Bericht; eine unbekannte Person wird abgelehnt.
        """
        store: HealthOMatStore = hass.data.get(DOMAIN, {}).get("shared", {}).get("store")
        try:
            if store is None:
                raise ServiceValidationError("Keine Health-O-Mat-Person eingerichtet")
            if (call.data.get("person") or "").strip():
                entry_id, _info = get_runtime_data(hass, call)
                target_ids = [entry_id]
            else:
                target_ids = [
                    key
                    for key, value in hass.data.get(DOMAIN, {}).items()
                    if key not in _NON_ENTRY_KEYS
                    and isinstance(value, dict)
                    and "coordinator" in value
                ]
                if not target_ids:
                    raise ServiceValidationError("Keine Health-O-Mat-Person eingerichtet")
            entries = {e.entry_id: e for e in hass.config_entries.async_entries(DOMAIN)}
            language = getattr(hass.config, "language", "de")
            now = dt_util.now()
            for entry_id in target_ids:
                entry = entries.get(entry_id)
                if entry is None:
                    continue
                options = entry.options or {}
                report = normalize_weekly_report(options.get(OPTION_WEEKLY_REPORT))
                metrics = collect_weekly_metrics(store.active_entry(entry_id), options, now)
                person = effective_person(entry)
                await async_send_notification(
                    hass,
                    report["notify_service"],
                    weekly_report_title(person, language),
                    render_weekly_report_markdown(metrics, person, language),
                )
        except ServiceValidationError:
            raise
        except Exception as err:  # noqa: BLE001 - einheitliche Service-Fehlersemantik
            raise ServiceValidationError(f"Wochenbericht fehlgeschlagen: {err}") from err

    hass.services.async_register(
        DOMAIN,
        "add_drink",
        schema=vol.Schema(
            {
                vol.Required("amount_ml"): vol.Coerce(int),
                vol.Optional("drink_type"): str,
                vol.Optional("person"): str,
                vol.Optional("source"): str,
                vol.Optional("ts"): str,
            }
        ),
        service_func=add_drink,
    )
    hass.services.async_register(
        DOMAIN,
        "add_blood_pressure",
        schema=vol.Schema(
            {
                vol.Required("systolic"): vol.Coerce(int),
                vol.Required("diastolic"): vol.Coerce(int),
                vol.Optional("pulse"): vol.Coerce(int),
                vol.Optional("person"): str,
                vol.Optional("note"): str,
                vol.Optional("ts"): str,
            }
        ),
        service_func=add_blood_pressure,
    )
    hass.services.async_register(
        DOMAIN,
        "add_lab_value",
        schema=vol.Schema(
            {
                vol.Required("marker"): str,
                vol.Required("value"): vol.Coerce(float),
                vol.Optional("unit"): str,
                vol.Optional("person"): str,
                vol.Optional("ts"): str,
                vol.Optional("report_ref"): str,
            }
        ),
        service_func=add_lab_value,
    )
    hass.services.async_register(
        DOMAIN,
        "add_lab_report",
        schema=vol.Schema(
            {
                vol.Optional("person"): str,
                vol.Optional("ts"): str,
                vol.Optional("report_ref"): str,
                vol.Required("values"): vol.All(
                    cv.ensure_list,
                    [
                        vol.Schema(
                            {
                                # Bewusst Optional: die UI sendet leere Zeilen, und
                                # ein `{}`-Eintrag ist eine ignorierte Leerzeile.
                                vol.Optional("marker"): str,
                                vol.Optional("value"): vol.Any(str, int, float),
                                vol.Optional("unit"): vol.Any(str, None),
                            }
                        )
                    ],
                ),
            }
        ),
        service_func=add_lab_report,
    )
    hass.services.async_register(
        DOMAIN,
        "remove_lab_report",
        schema=vol.Schema(
            {
                vol.Optional("person"): str,
                vol.Required("ts"): str,
                vol.Optional("report_ref"): str,
            }
        ),
        service_func=remove_lab_report,
    )
    hass.services.async_register(
        DOMAIN,
        "set_wellbeing",
        schema=vol.Schema(
            {
                vol.Optional("person"): str,
                vol.Optional("status"): str,
                vol.Optional("score"): vol.Coerce(int),
                vol.Optional("ts"): str,
            }
        ),
        service_func=set_wellbeing,
    )
    hass.services.async_register(
        DOMAIN,
        "remove_last_entry",
        schema=vol.Schema(
            {
                vol.Optional("person"): str,
                vol.Optional("kind", default="drinks"): vol.In(
                    ["drinks", "blood_pressure", "wellbeing"]
                ),
            }
        ),
        service_func=remove_last_entry,
    )
    hass.services.async_register(
        DOMAIN,
        "remove_last_lab_value",
        schema=vol.Schema(
            {
                vol.Optional("person"): str,
                vol.Required("marker"): str,
            }
        ),
        service_func=remove_last_lab_value,
    )
    hass.services.async_register(
        DOMAIN,
        "void_entry",
        schema=vol.Schema(
            {
                vol.Optional("person"): str,
                vol.Required("kind"): vol.In(
                    ["drinks", "blood_pressure", "wellbeing", "lab_values"]
                ),
                vol.Required("id"): str,
            }
        ),
        service_func=void_entry,
    )
    hass.services.async_register(
        DOMAIN,
        "restore_entry",
        schema=vol.Schema(
            {
                vol.Optional("person"): str,
                vol.Required("kind"): vol.In(
                    ["drinks", "blood_pressure", "wellbeing", "lab_values"]
                ),
                vol.Required("id"): str,
            }
        ),
        service_func=restore_entry,
    )
    hass.services.async_register(
        DOMAIN,
        "export_csv",
        schema=vol.Schema(
            {
                vol.Optional("person"): str,
                vol.Optional("dataset", default="all"): vol.In(
                    ["drinks", "blood_pressure", "lab_values", "all"]
                ),
            }
        ),
        service_func=export_csv,
    )
    hass.services.async_register(
        DOMAIN,
        "import_csv",
        schema=vol.Schema(
            {
                vol.Required("filename"): str,
                vol.Optional("person"): str,
                vol.Optional("dataset", default="all"): vol.In(
                    ["drinks", "blood_pressure", "lab_values", "all"]
                ),
            }
        ),
        service_func=import_csv,
    )
    hass.services.async_register(
        DOMAIN,
        "backup",
        schema=vol.Schema({}),
        service_func=backup,
    )
    hass.services.async_register(
        DOMAIN,
        "restore_backup",
        schema=vol.Schema(
            {
                vol.Required("filename"): str,
                vol.Optional("mode", default="merge"): vol.In(["merge", "replace"]),
                vol.Optional("persons"): [str],
                vol.Optional("datasets"): [str],
                vol.Optional("from"): str,
                vol.Optional("to"): str,
                vol.Optional("person_map"): dict,
                vol.Optional("dry_run", default=False): bool,
                vol.Optional("confirm"): str,
                vol.Optional("restore_audit", default=False): bool,
            }
        ),
        service_func=restore_backup,
    )
    hass.services.async_register(
        DOMAIN,
        "weekly_report",
        schema=vol.Schema({vol.Optional("person"): str}),
        service_func=weekly_report,
    )

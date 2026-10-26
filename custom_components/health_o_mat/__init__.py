"""HA Health-O-Mat — Integration Setup."""

from __future__ import annotations

import logging
from datetime import datetime

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from . import areas, logic
from .const import (
    DEFAULT_DAILY_GOAL_ML,
    DEFAULT_DIA_THRESHOLD,
    DEFAULT_QUICK_DRINKS,
    DEFAULT_SYS_THRESHOLD,
    DOMAIN,
    OPTION_WEEKLY_REPORT,
    WELLBEING_STATES,
)
from .entity import effective_person, signal_refresh
from .frontend import async_setup_frontend, async_unregister_frontend
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
)

type HealthOMatConfigEntry = ConfigEntry[HealthOMatData]


class HealthOMatData:
    """Laufzeitdaten eines Config-Entries (= eine Person)."""

    def __init__(self) -> None:
        self.daily_goal_ml: int = DEFAULT_DAILY_GOAL_ML
        self.custom_amount_ml: int = 250
        self.sys_threshold: int = DEFAULT_SYS_THRESHOLD
        self.dia_threshold: int = DEFAULT_DIA_THRESHOLD
        self.areas: dict[str, bool] = dict(areas.DEFAULT_AREAS)
        # S-4: zuletzt gesehener `set_lifetime_ml`-Optionswert. Nur eine
        # explizite Änderung darf den Lebenszähler setzen — sonst würde jede
        # Options-Änderung (z. B. Tagesziel) den gewachsenen Zähler zurücksetzen.
        self.lifetime_setting_seen: int | None = None


async def async_migrate_entry(hass: HomeAssistant, entry: HealthOMatConfigEntry) -> bool:
    """v1 → v2: quick_drinks aus entry.data nach entry.options verlagern (Fund F1).

    v1-Entries (≤ v0.4.0) hatten quick_drinks unveränderlich in entry.data —
    Ändern war nur durch Löschen+Neu-Anlegen möglich (Datenverlust, da Store
    entry_id-keyed ist). Ab v2 gehört die Konfiguration in entry.options.
    """
    if entry.version > 2:
        _LOGGER.error(
            "Config entry %s hat Version %s > 2 — Downgrade nicht unterstützt",
            entry.title,
            entry.version,
        )
        return False
    if entry.version == 1:
        options = dict(entry.options)
        options.setdefault("quick_drinks", [dict(qd) for qd in DEFAULT_QUICK_DRINKS])
        new_data = {k: v for k, v in entry.data.items() if k != "quick_drinks"}
        hass.config_entries.async_update_entry(
            entry,
            data=new_data,
            options=options,
            version=2,
        )
        _LOGGER.info("Config entry %s: v1 → v2 migriert (quick_drinks → options)", entry.title)
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
    """
    rt = entry.runtime_data
    opts = entry.options or {}
    if opts.get("daily_goal_ml"):
        rt.daily_goal_ml = int(opts["daily_goal_ml"])
    _mirror_bp_thresholds(rt, opts)
    store: HealthOMatStore = hass.data[DOMAIN]["shared"]["store"]

    new_areas = areas.active_areas(opts)

    # Anzeige-Name geändert → Store synchron halten + Entities neu laden
    # (Device-Name kommt aus den Entities; Reload ist einzig sauberer Weg)
    current_person = store.all_entries().get(entry.entry_id, {}).get("person")
    person_changed = current_person != effective_person(entry)
    if person_changed or new_areas != rt.areas:
        if person_changed:
            await store.set_person(entry.entry_id, effective_person(entry))
        rt.areas = new_areas
        # Vor dem Reload: Timer neu aufsetzen (der Reload löst zwar erneut
        # Setup aus, aber bis dahin soll die neue Options-Wahl schon gelten).
        await async_setup_reminders(hass, entry, store)
        hass.async_create_task(hass.config_entries.async_reload(entry.entry_id))
        return  # Reload baut Entities neu auf — kein weiterer Refresh nötig

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


async def _set_entry_state(hass: HomeAssistant, call: ServiceCall, *, restore: bool) -> None:
    """Gemeinsamer Pfad für `void_entry`/`restore_entry` (ein Store-Aufruf je Ziel).

    `kind` und `id` werden fachlich validiert; ein unbekanntes/bereits im
    Zielzustand befindliches Ziel wird als `ServiceValidationError` gemeldet
    (kein stiller Erfolg). Schreibwege bleiben die bestehenden `void_*`/
    `restore_*`-Methoden — inklusive Audit-Eintrag und Store-Persistenz.
    """
    entry_id, _info = get_runtime_data(hass, call)
    kind = logic.normalize_history_kind(call.data.get("kind"))
    if kind is None:
        raise ServiceValidationError(
            f"Unbekannter kind '{call.data.get('kind')}' — "
            f"erlaubt: {', '.join(logic.HISTORY_KINDS)}"
        )
    item_id = str(call.data.get("id") or "").strip()
    if not item_id:
        raise ServiceValidationError("id fehlt")
    store: HealthOMatStore = hass.data[DOMAIN]["shared"]["store"]
    methods = logic.RESTORE_METHOD_BY_KIND if restore else logic.VOID_METHOD_BY_KIND
    changed = await getattr(store, methods[kind])(
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
        "void_entry",
        schema=vol.Schema(
            {
                vol.Optional("person"): str,
                vol.Required("kind"): vol.In(["drinks", "blood_pressure", "wellbeing"]),
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
                vol.Required("kind"): vol.In(["drinks", "blood_pressure", "wellbeing"]),
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
                vol.Optional("dataset", default="all"): vol.In(["drinks", "blood_pressure", "all"]),
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
                vol.Optional("dataset", default="all"): vol.In(["drinks", "blood_pressure", "all"]),
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

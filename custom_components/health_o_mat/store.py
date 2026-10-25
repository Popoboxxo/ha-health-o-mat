"""Persistenter Speicher (Store) — Quelle der Wahrheit, versioniert.

Schema-Stufen (STORE_SCHEMA_VERSION in const.py):
- v1: Ursprungsschema (drinks, readings, total_ml_lifetime, person, wellbeing*)
- v2: + `inputs` je Person (persistierte BP-Eingaben, REQ-HOM-104)
- v3: + `archived_counts` je Person (Retention/Archiv-Kennzahlen, REQ-HOM-109)
- v4: + `id`/`created_at`/`voided_*` je Eintrag, + `wellbeing_entries`,
  + `audit_log` je Person (Korrigierbarkeit/Audit, REQ-HOM-115)

Ab v4 ist das Wohlbefinden eine Ereignisliste (`wellbeing_entries`); die
Legacy-Felder `wellbeing`/`wellbeing_history` bleiben als abgeleitete
Kompatibilitäts-Spiegel erhalten. `audit_log` ist append-only und wird je
Person optional gekappt (Default 1000, `0` = unbegrenzt).

Lesepfade für Anzeige/Auswertung nutzen die **aktive Sicht**
(`active_entry`/`active_entries`): voided Einträge (`voided_at` gesetzt) sind
dort herausgefiltert und die Wellbeing-Spiegel aus den aktiven Ereignissen neu
aufgebaut. `entry()`/`all_entries()` bleiben bewusst **roh** (Schreibpfad,
Backup, Diagnostics-Rohzahlen).

Die Klasse bedient sowohl den Haupt-Store (`MAIN_STORE_KEY`) als auch den
separaten Archiv-Store (`ARCHIVE_STORE_KEY`); beide teilen sich dieselbe
Migrationskette. Migration on-load: fehlende `schema`-Markierung gilt als v1;
die Migrationskette bringt Alt-Bestände idempotent auf die aktuelle Stufe
(REQ-HOM-102).
Kaputtes JSON sichert Home Assistant selbst (Backup `*.corrupt.*` + Repairs-Eintrag) —
hier bleibt der Fall „valides JSON, falsches Schema": Backup als
`*.invalid-schema-<ts>` + Notification + definierter leerer Start (REQ-HOM-103).
"""

from __future__ import annotations

import copy
import logging
import os
import uuid
from collections.abc import Callable
from datetime import datetime
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import (
    DEFAULT_AUDIT_LIMIT,
    MAIN_STORE_KEY,
    STORE_SCHEMA_VERSION,
    STORE_VERSION,
)

_LOGGER = logging.getLogger(__name__)

# Legacy-Historie des Wohlbefindens bleibt wie bisher auf 100 Einträge begrenzt.
_WELLBEING_HISTORY_LIMIT = 100


def _now_iso() -> str:
    """Aktueller Zeitpunkt als ISO-String (HA-Zeitzone)."""
    return dt_util.now().isoformat()


def _deterministic_id(entry_id: str, kind: str, index: int, ts: Any) -> str:
    """Stabile UUID für migrierte Einträge (uuid5 aus Entry/Kind/Index/ts).

    Deterministisch, damit ein erneuter Lauf (oder ein zweiter Import derselben
    Daten) dieselben IDs erzeugt und Einträge nicht dupliziert.
    """
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"{entry_id}:{kind}:{index}:{ts}"))


def _migrate_entry_timestamps(entry_id: str, entry: dict, kind: str) -> None:
    """v4: `id`/`created_at`/Void-Felder je Eintrag einer Liste ergänzen."""
    items = entry.get(kind)
    if not isinstance(items, list):
        return
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        item.setdefault("id", _deterministic_id(entry_id, kind, index, item.get("ts")))
        item.setdefault("created_at", item.get("ts"))
        item.setdefault("voided_at", None)
        item.setdefault("voided_by", None)
        item.setdefault("void_reason", None)


def _wellbeing_event(entry_id: str, index: int, key: str, ts: Any) -> dict:
    """v4: Wohlbefinden-Ereignis mit deterministischer ID."""
    return {
        "id": _deterministic_id(entry_id, "wellbeing", index, ts),
        "ts": ts,
        "key": key,
        "created_at": ts,
        "voided_at": None,
        "voided_by": None,
        "void_reason": None,
    }


def _migrate_wellbeing(entry_id: str, entry: dict) -> None:
    """v4: `wellbeing` + `wellbeing_history` → `wellbeing_entries` (idempotent).

    Bestehende `wellbeing_entries` werden nie überschrieben oder ergänzt —
    sonst würden wiederholte Läufe Einträge duplizieren. Die Historie wird in
    ihrer Ablage-Reihenfolge übernommen (der abgelöste Status trägt seinen
    eigenen Meldezeitpunkt), der aktuelle Wert ist der letzte Eintrag. Fehlende
    oder direkt aufeinanderfolgende doppelte `(key, ts)`-Paare werden defensiv
    übersprungen.
    """
    if "wellbeing_entries" in entry:
        return  # bereits v4-konform (auch wenn leer) — nicht anfassen

    events: list[dict] = []

    def _append(key: Any, ts: Any) -> None:
        if not key:
            return
        if events and events[-1]["key"] == key and events[-1]["ts"] == ts:
            return  # Duplikat (z. B. aktueller Wert zusätzlich in der Historie)
        events.append(_wellbeing_event(entry_id, len(events), str(key), ts))

    history = entry.get("wellbeing_history")
    if isinstance(history, list):
        for item in history:
            if isinstance(item, dict):
                _append(item.get("status"), item.get("ts"))

    current = entry.get("wellbeing")
    if isinstance(current, dict):
        _append(current.get("status"), current.get("ts"))

    entry["wellbeing_entries"] = events


def _migrate_v1_to_v2(data: dict) -> dict:
    """v1 → v2: `inputs`-Dict je Person ergänzen (idempotent)."""
    for entry in data.get("entries", {}).values():
        entry.setdefault("inputs", {})
    return data


def _migrate_v2_to_v3(data: dict) -> dict:
    """v2 → v3: `archived_counts` je Person ergänzen (Retention, idempotent)."""
    for entry in data.get("entries", {}).values():
        entry.setdefault("archived_counts", {"drinks": 0, "readings": 0})
    return data


def _migrate_v3_to_v4(data: dict) -> dict:
    """v3 → v4: IDs/Void-Felder, Wellbeing-Ereignisse, Audit-Log (idempotent)."""
    for entry_id, entry in data.get("entries", {}).items():
        if not isinstance(entry, dict):
            continue
        _migrate_entry_timestamps(entry_id, entry, "drinks")
        _migrate_entry_timestamps(entry_id, entry, "readings")
        _migrate_wellbeing(entry_id, entry)
        entry.setdefault("audit_log", [])
    return data


_MIGRATIONS: dict[int, Callable[[dict], dict]] = {
    1: _migrate_v1_to_v2,
    2: _migrate_v2_to_v3,
    3: _migrate_v3_to_v4,
}


def migrate_store_data(data: dict) -> dict:
    """Bringt Store-Daten idempotent auf ``STORE_SCHEMA_VERSION`` (HA-frei).

    Gemeinsamer Pfad für ``async_load`` und den Restore: ein Backup kann eine
    ältere Schema-Stufe tragen (v1/v2/v3) und wird hier über dieselbe
    Migrationskette normalisiert wie ein persistierter Altbestand. Wiederholte
    Aufrufe ändern nichts (idempotent).
    """
    if not isinstance(data, dict):
        raise ValueError("Store-Daten müssen ein Objekt sein")
    try:
        schema = max(1, int(data.get("schema", 1)))
    except (TypeError, ValueError):
        schema = 1
    for step in range(schema, STORE_SCHEMA_VERSION):
        migration = _MIGRATIONS.get(step)
        if migration:
            data = migration(data)
    data["schema"] = STORE_SCHEMA_VERSION
    return data


class HealthOMatStore:
    """Append-only Historie je Person, persistiert via HA-Store.

    `storage_key` unterscheidet den Haupt-Store vom Archiv-Store; die
    Methoden sind für beide identisch, die Semantik der Aufrufer nicht.
    """

    def __init__(self, hass: HomeAssistant, storage_key: str = MAIN_STORE_KEY) -> None:
        self._hass = hass
        self._storage_key = storage_key
        self._store = Store(
            hass,
            STORE_VERSION,
            storage_key,
            minor_version=STORE_SCHEMA_VERSION,
        )
        self._data: dict = {}

    async def async_load(self) -> None:
        """Laden, migrieren und bei Defekt reparieren (leerer Start)."""
        data = await self._load_with_recovery()
        # bewusst frisches Dict je Instanz (keine geteilte Modul-Referenz!)
        # Auch der leere Start trägt die aktuelle Schema-Markierung, damit
        # Backups/Diagnostics die Stufe korrekt ausweisen.
        self._data = (
            self._migrate(data) if data else {"schema": STORE_SCHEMA_VERSION, "entries": {}}
        )

    def _migrate(self, data: dict) -> dict:
        """Bringt geladene Daten idempotent auf STORE_SCHEMA_VERSION."""
        return migrate_store_data(data)

    async def _load_with_recovery(self) -> dict | None:
        """Load mit Recovery (REQ-HOM-103).

        Kaputtes JSON handhabt Home Assistant selbst (Backup `*.corrupt.<ts>` +
        Repairs-Eintrag im UI) — _store.async_load() liefert dann None.
        Hier bleibt nur der Fall „valides JSON, aber kein Health-O-Mat-Schema":
        Datei sichern, Notification erzeugen, leer starten.
        """
        data = await self._store.async_load()
        if data is None:
            return None  # Erstanlage — oder HA-Corrupt-Recovery (Backup: *.corrupt.*)
        if not isinstance(data, dict) or "entries" not in data:
            await self._handle_invalid_schema()
            return None
        return data

    async def _handle_invalid_schema(self) -> None:
        """Store-Datei mit falschem Schema sichern + Notification (Executor-Job)."""
        _LOGGER.error("Health-O-Mat-Store ohne 'entries'-Schema — Backup + leerer Start")
        src = self._hass.config.path(".storage", self._storage_key)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        dst = f"{src}.invalid-schema-{stamp}"

        def _backup() -> bool:
            if os.path.exists(src):
                os.replace(src, dst)
                return True
            return False

        backed_up = await self._hass.async_add_executor_job(_backup)
        message = (
            "Der Health-O-Mat-Speicher hat ein unerwartetes Format.\n"
            + (
                f"Die Originaldatei wurde gesichert nach:\n{dst}\n"
                if backed_up
                else "Keine Speicherdatei gefunden.\n"
            )
            + "Die Integration startet mit leerem Bestand. "
            + "Bitte das Backup im GitHub-Issue anfügen, wenn Daten vermisst werden."
        )
        await self._hass.services.async_call(
            "persistent_notification",
            "create",
            {"title": "HA Health-O-Mat — Speicherformat unbekannt", "message": message},
            blocking=False,
        )

    def entry(self, entry_id: str) -> dict:
        return self._data["entries"].setdefault(
            entry_id,
            {
                "person": "",
                "drinks": [],
                "readings": [],
                "total_ml_lifetime": 0,
                "inputs": {},
                "archived_counts": {"drinks": 0, "readings": 0},
                "wellbeing_entries": [],
                "audit_log": [],
            },
        )

    def all_entries(self) -> dict:
        return self._data["entries"]

    # ------------------------------------------------------------------
    # Aktive Sicht (Anzeige/Auswertung, ohne voided Einträge)
    # ------------------------------------------------------------------
    def active_entry(self, entry_id: str) -> dict:
        """Aktive Sicht eines Eintrags als Kopie (ohne voided Einträge).

        Reiner Lesezugriff: `None`/unbekannte Personen liefern ein leeres Dict,
        der Rohdatensatz wird weder verändert noch angelegt. Die Listen
        (`drinks`/`readings`/`wellbeing_entries`) enthalten nur aktive Einträge;
        die Legacy-Spiegel `wellbeing`/`wellbeing_history` werden daraus neu
        aufgebaut (aktueller Wert = letzter aktiver, Historie = übrige aktive).
        Alle übrigen Felder (`person`, `total_ml_lifetime`, `inputs`,
        `archived_counts`, `audit_log`, …) werden unverändert übernommen.
        """
        raw = self._data.get("entries", {}).get(entry_id)
        if not isinstance(raw, dict):
            return {}
        return _active_view(raw)

    def active_entries(self) -> dict[str, dict]:
        """Aktive Sicht aller Personen (`{entry_id: aktive Kopie}`)."""
        return {
            entry_id: _active_view(raw)
            for entry_id, raw in self._data.get("entries", {}).items()
            if isinstance(raw, dict)
        }

    # ------------------------------------------------------------------
    # Audit-Log (append-only, optional gekappt)
    # ------------------------------------------------------------------
    def _append_audit(
        self,
        entry_id: str,
        action: str,
        kind: str,
        target_id: str | None = None,
        actor: str | None = None,
        details: dict[str, Any] | None = None,
        audit_limit: int = DEFAULT_AUDIT_LIMIT,
    ) -> None:
        """Ein Audit-Ereignis anhängen und den Cap anwenden.

        `details` trägt nur Metadaten (z. B. `{"ml": 250}`), nie vollständige
        Gesundheitswerte — die stehen im Eintrag selbst.
        """
        append_audit_event_to_entry(
            self.entry(entry_id),
            action,
            kind,
            target_id=target_id,
            actor=actor,
            details=details,
            audit_limit=audit_limit,
        )

    def append_audit_event(
        self,
        entry_id: str,
        action: str,
        kind: str,
        target_id: str | None = None,
        actor: str | None = None,
        details: dict[str, Any] | None = None,
        audit_limit: int = DEFAULT_AUDIT_LIMIT,
    ) -> dict:
        """Öffentliches Audit-Ereignis anhängen — OHNE Save.

        Für den Restore: der Plan wird in-memory aufgebaut und in genau einem
        ``async_set_entries``-Save persistiert. Reguläre Schreibpfade nutzen
        weiterhin ``_append_audit`` + eigenen Save.
        """
        return append_audit_event_to_entry(
            self.entry(entry_id),
            action,
            kind,
            target_id=target_id,
            actor=actor,
            details=details,
            audit_limit=audit_limit,
        )

    @staticmethod
    def _prune_audit(audit: list[dict], audit_limit: int) -> None:
        """Älteste Ereignisse entfernen, damit höchstens `audit_limit` bleiben.

        `0` (oder negativ) = unbegrenzt. Bei genau einem erlaubten Ereignis
        bleibt defensiv nur das neueste erhalten (ein Summary-Ereignis würde
        das Limit selbst sprengen); ab zwei Ereignissen bleibt ein
        `audit_pruned`-Summary am Ende stehen.
        """
        prune_audit_log(audit, audit_limit)

    # ------------------------------------------------------------------
    # Getränke
    # ------------------------------------------------------------------
    async def add_drink(
        self,
        entry_id: str,
        ts_iso: str,
        ml: int,
        drink_type: str,
        src: str,
        created_ts_iso: str | None = None,
        actor: str | None = None,
        audit_limit: int = DEFAULT_AUDIT_LIMIT,
    ) -> None:
        e = self.entry(entry_id)
        drink = {
            "id": str(uuid.uuid4()),
            "ts": ts_iso,
            "ml": int(ml),
            "type": drink_type,
            "src": src,
            "created_at": created_ts_iso or _now_iso(),
            "voided_at": None,
            "voided_by": None,
            "void_reason": None,
        }
        e["drinks"].append(drink)
        e["total_ml_lifetime"] = int(e.get("total_ml_lifetime", 0)) + int(ml)
        self._append_audit(
            entry_id,
            "drink_added",
            "drinks",
            drink["id"],
            actor,
            {"ml": drink["ml"]},
            audit_limit,
        )
        await self._async_save()

    async def remove_last_drink(
        self,
        entry_id: str,
        actor: str | None = None,
        audit_limit: int = DEFAULT_AUDIT_LIMIT,
    ) -> bool:
        """Undo: letzten **aktiven** Drink voiden (kein Hard-Delete).

        Bewusst KEIN `pop()`: ein bereits gelöschter Eintrag am Listenende
        bliebe sonst hart entfernbar und würde `total_ml_lifetime` doppelt
        kürzen. Der voided Eintrag bleibt in der Rohliste (Audit/Backup).
        """
        drink = self.last_active_drink(entry_id)
        if drink is None:
            return False
        return await self.void_drink(
            entry_id, drink.get("id"), actor=actor, audit_limit=audit_limit
        )

    def last_active_drink(self, entry_id: str) -> dict | None:
        """Letzter nicht-gelöschter Drink (None = kein aktiver Eintrag)."""
        return _last_active(self.entry(entry_id).get("drinks"))

    def active_drinks(self, entry_id: str) -> list[dict]:
        """Nur nicht-gelöschte Getränke (Reihenfolge bleibt Erfassungsreihenfolge)."""
        return [
            item
            for item in self.entry(entry_id).get("drinks", [])
            if isinstance(item, dict) and not item.get("voided_at")
        ]

    async def void_drink(
        self,
        entry_id: str,
        drink_id: str,
        actor: str | None = None,
        reason: str | None = None,
        audit_limit: int = DEFAULT_AUDIT_LIMIT,
    ) -> bool:
        """Getränk als gelöscht markieren (kein Hard-Delete) und Lifetime kürzen."""
        e = self.entry(entry_id)
        drink = _find_by_id(e.get("drinks"), drink_id)
        if drink is None or drink.get("voided_at"):
            return False
        drink["voided_at"] = _now_iso()
        drink["voided_by"] = actor
        drink["void_reason"] = reason
        e["total_ml_lifetime"] = max(
            0, int(e.get("total_ml_lifetime", 0)) - int(drink.get("ml", 0))
        )
        self._append_audit(
            entry_id,
            "entry_voided",
            "drinks",
            drink_id,
            actor,
            {"reason": reason} if reason else {},
            audit_limit,
        )
        await self._async_save()
        return True

    async def restore_drink(
        self,
        entry_id: str,
        drink_id: str,
        actor: str | None = None,
        audit_limit: int = DEFAULT_AUDIT_LIMIT,
    ) -> bool:
        """Gelöschtes Getränk wiederherstellen und Lifetime wieder addieren."""
        e = self.entry(entry_id)
        drink = _find_by_id(e.get("drinks"), drink_id)
        if drink is None or not drink.get("voided_at"):
            return False
        drink["voided_at"] = None
        drink["voided_by"] = None
        drink["void_reason"] = None
        e["total_ml_lifetime"] = int(e.get("total_ml_lifetime", 0)) + int(drink.get("ml", 0))
        self._append_audit(entry_id, "entry_restored", "drinks", drink_id, actor, {}, audit_limit)
        await self._async_save()
        return True

    async def remove_last_reading(
        self,
        entry_id: str,
        actor: str | None = None,
        audit_limit: int = DEFAULT_AUDIT_LIMIT,
    ) -> bool:
        """Undo: letzte **aktive** Blutdruckmessung voiden (N-7).

        Berührt `total_ml_lifetime` bewusst NICHT — Messwerte tragen keine
        Trinkmenge. Leerer Bestand/keine aktive Messung → False (Aufrufer
        entscheidet über den Fehlertext).
        """
        reading = self.last_active_reading(entry_id)
        if reading is None:
            return False
        return await self.void_reading(
            entry_id, reading.get("id"), actor=actor, audit_limit=audit_limit
        )

    def last_active_reading(self, entry_id: str) -> dict | None:
        """Letzte nicht-gelöschte Messung (None = keine aktive Messung)."""
        return _last_active(self.entry(entry_id).get("readings"))

    # ------------------------------------------------------------------
    # Blutdruck-Messungen
    # ------------------------------------------------------------------
    async def add_reading(
        self,
        entry_id: str,
        ts_iso: str,
        sys_: int,
        dia: int,
        pulse: int | None,
        note: str = "",
        src: str = "button",
        created_ts_iso: str | None = None,
        actor: str | None = None,
        audit_limit: int = DEFAULT_AUDIT_LIMIT,
    ) -> None:
        reading: dict = {
            "id": str(uuid.uuid4()),
            "ts": ts_iso,
            "sys": int(sys_),
            "dia": int(dia),
            "pulse": int(pulse) if pulse is not None else None,
            "note": note,
            "src": src,
            "created_at": created_ts_iso or _now_iso(),
            "voided_at": None,
            "voided_by": None,
            "void_reason": None,
        }
        self.entry(entry_id)["readings"].append(reading)
        self._append_audit(
            entry_id,
            "reading_added",
            "readings",
            reading["id"],
            actor,
            {"src": src},
            audit_limit,
        )
        await self._async_save()

    def active_readings(self, entry_id: str) -> list[dict]:
        """Nur nicht-gelöschte Messungen."""
        return [
            item
            for item in self.entry(entry_id).get("readings", [])
            if isinstance(item, dict) and not item.get("voided_at")
        ]

    async def void_reading(
        self,
        entry_id: str,
        reading_id: str,
        actor: str | None = None,
        reason: str | None = None,
        audit_limit: int = DEFAULT_AUDIT_LIMIT,
    ) -> bool:
        """Messung als gelöscht markieren (kein Hard-Delete)."""
        e = self.entry(entry_id)
        reading = _find_by_id(e.get("readings"), reading_id)
        if reading is None or reading.get("voided_at"):
            return False
        reading["voided_at"] = _now_iso()
        reading["voided_by"] = actor
        reading["void_reason"] = reason
        self._append_audit(
            entry_id,
            "entry_voided",
            "readings",
            reading_id,
            actor,
            {"reason": reason} if reason else {},
            audit_limit,
        )
        await self._async_save()
        return True

    async def restore_reading(
        self,
        entry_id: str,
        reading_id: str,
        actor: str | None = None,
        audit_limit: int = DEFAULT_AUDIT_LIMIT,
    ) -> bool:
        """Gelöschte Messung wiederherstellen."""
        e = self.entry(entry_id)
        reading = _find_by_id(e.get("readings"), reading_id)
        if reading is None or not reading.get("voided_at"):
            return False
        reading["voided_at"] = None
        reading["voided_by"] = None
        reading["void_reason"] = None
        self._append_audit(
            entry_id, "entry_restored", "readings", reading_id, actor, {}, audit_limit
        )
        await self._async_save()
        return True

    async def set_person(self, entry_id: str, person: str) -> None:
        self.entry(entry_id)["person"] = person
        await self._async_save()

    async def set_lifetime_start(self, entry_id: str, ml: int) -> None:
        self.entry(entry_id)["total_ml_lifetime"] = int(ml)
        await self._async_save()

    def inputs(self, entry_id: str) -> dict:
        """Persistierte BP-Eingaben (Systolic/Diastolic/Pulse) je Person."""
        return self.entry(entry_id).setdefault("inputs", {})

    async def set_inputs(self, entry_id: str, key: str, value: int | None) -> None:
        """EINEN Eingabewert setzen (None = leeren) und persistieren."""
        self.inputs(entry_id)[key] = value
        await self._async_save()

    async def clear_inputs(self, entry_id: str) -> None:
        """Alle BP-Eingaben leeren (nach save_measurement)."""
        self.entry(entry_id)["inputs"] = {}
        await self._async_save()

    # ------------------------------------------------------------------
    # Wohlbefinden (Ereignisliste + Legacy-Spiegel)
    # ------------------------------------------------------------------
    async def set_wellbeing(
        self,
        entry_id: str,
        status: str,
        ts_iso: str,
        created_ts_iso: str | None = None,
        actor: str | None = None,
        audit_limit: int = DEFAULT_AUDIT_LIMIT,
    ) -> None:
        """Wohlbefinden-Meldung setzen + Historie führen."""
        e = self.entry(entry_id)
        event = {
            "id": str(uuid.uuid4()),
            "ts": ts_iso,
            "key": status,
            "created_at": created_ts_iso or _now_iso(),
            "voided_at": None,
            "voided_by": None,
            "void_reason": None,
        }
        e.setdefault("wellbeing_entries", []).append(event)
        wb = e.setdefault("wellbeing", {})
        history = e.setdefault("wellbeing_history", [])
        if wb.get("status"):
            # Der abgelöste Status wird mit SEINEM eigenen Zeitstempel archiviert
            # (wann er gemeldet wurde) — nicht mit dem Zeitstempel der Meldung,
            # die ihn ablöst. Sonst zeigt der Verlauf den Vorgänger zu neu.
            history.append({"ts": wb.get("ts") or ts_iso, "status": wb["status"]})
            del history[:-_WELLBEING_HISTORY_LIMIT]
        wb["status"] = status
        wb["ts"] = ts_iso
        self._append_audit(
            entry_id,
            "wellbeing_added",
            "wellbeing",
            event["id"],
            actor,
            {"key": status},
            audit_limit,
        )
        await self._async_save()

    def active_wellbeing_entries(self, entry_id: str) -> list[dict]:
        """Nur nicht-gelöschte Wohlbefinden-Meldungen (Erfassungsreihenfolge)."""
        return [
            item
            for item in self.entry(entry_id).get("wellbeing_entries", [])
            if isinstance(item, dict) and not item.get("voided_at")
        ]

    def current_wellbeing(self, entry_id: str) -> dict | None:
        """Aktueller Wohlbefindenswert = letzter nicht-gelöschter Eintrag."""
        active = self.active_wellbeing_entries(entry_id)
        return active[-1] if active else None

    async def void_wellbeing(
        self,
        entry_id: str,
        wellbeing_id: str,
        actor: str | None = None,
        reason: str | None = None,
        audit_limit: int = DEFAULT_AUDIT_LIMIT,
    ) -> bool:
        """Wohlbefinden-Meldung als gelöscht markieren + Legacy-Spiegel neu bauen."""
        e = self.entry(entry_id)
        item = _find_by_id(e.get("wellbeing_entries"), wellbeing_id)
        if item is None or item.get("voided_at"):
            return False
        item["voided_at"] = _now_iso()
        item["voided_by"] = actor
        item["void_reason"] = reason
        _sync_wellbeing_mirrors(e)
        self._append_audit(
            entry_id,
            "entry_voided",
            "wellbeing",
            wellbeing_id,
            actor,
            {"reason": reason} if reason else {},
            audit_limit,
        )
        await self._async_save()
        return True

    async def restore_wellbeing(
        self,
        entry_id: str,
        wellbeing_id: str,
        actor: str | None = None,
        audit_limit: int = DEFAULT_AUDIT_LIMIT,
    ) -> bool:
        """Gelöschte Wohlbefinden-Meldung wiederherstellen + Spiegel neu bauen."""
        e = self.entry(entry_id)
        item = _find_by_id(e.get("wellbeing_entries"), wellbeing_id)
        if item is None or not item.get("voided_at"):
            return False
        item["voided_at"] = None
        item["voided_by"] = None
        item["void_reason"] = None
        _sync_wellbeing_mirrors(e)
        self._append_audit(
            entry_id, "entry_restored", "wellbeing", wellbeing_id, actor, {}, audit_limit
        )
        await self._async_save()
        return True

    async def remove_last_wellbeing(
        self,
        entry_id: str,
        actor: str | None = None,
        audit_limit: int = DEFAULT_AUDIT_LIMIT,
    ) -> bool:
        """Undo: letzte **aktive** Wohlbefinden-Meldung voiden (kein Pop)."""
        item = self.last_active_wellbeing(entry_id)
        if item is None:
            return False
        return await self.void_wellbeing(
            entry_id, item.get("id"), actor=actor, audit_limit=audit_limit
        )

    def last_active_wellbeing(self, entry_id: str) -> dict | None:
        """Letzte nicht-gelöschte Wohlbefinden-Meldung (None = keine)."""
        return _last_active(self.entry(entry_id).get("wellbeing_entries"))

    async def apply_retention(self, entry_id: str, kept_drinks: list, kept_readings: list) -> None:
        """Retention anwenden: nur die behaltenen Listen speichern (REQ-HOM-109).

        `total_ml_lifetime` bleibt UNVERÄNDERT — Archivieren ist ein reines
        Verschieben der Historie, keine Summenkorrektur. Die Zahl der
        verschobenen Einträge wird in `archived_counts` mitgeführt.
        """
        e = self.entry(entry_id)
        moved_drinks = len(e.get("drinks", [])) - len(kept_drinks)
        moved_readings = len(e.get("readings", [])) - len(kept_readings)
        e["drinks"] = list(kept_drinks)
        e["readings"] = list(kept_readings)
        counts = e.setdefault("archived_counts", {"drinks": 0, "readings": 0})
        counts["drinks"] = int(counts.get("drinks", 0)) + moved_drinks
        counts["readings"] = int(counts.get("readings", 0)) + moved_readings
        await self._async_save()

    async def append_archive(self, entry_id: str, drinks: list, readings: list) -> None:
        """Verschiebt Einträge in den Archiv-Store (nur anhängen)."""
        e = self._data["entries"].setdefault(entry_id, {"drinks": [], "readings": []})
        e.setdefault("drinks", []).extend(drinks)
        e.setdefault("readings", []).extend(readings)
        await self._async_save()

    def raw_data(self) -> dict:
        """Rohe Store-Daten (für Tests/Diagnostics)."""
        return self._data

    def raw_entries_copy(self) -> dict:
        """Tiefe Kopie von ``entries`` (Restore-Planung, keine Referenzteilung)."""
        return copy.deepcopy(self._data.get("entries", {}))

    async def async_set_entries(self, entries: dict) -> None:
        """Ersetzt ``entries`` in genau EINEM Save (Restore-Pfad).

        Das Schema bleibt erhalten. Schlägt der Save fehl, wird der vorherige
        In-Memory-Stand wiederhergestellt (kein stiller Teil-Schreibstand).
        """
        if not isinstance(entries, dict):
            raise ValueError("entries müssen ein Objekt sein")
        previous = self._data.get("entries", {})
        self._data["schema"] = STORE_SCHEMA_VERSION
        self._data["entries"] = entries
        try:
            await self._async_save()
        except Exception:
            self._data["entries"] = previous
            raise

    def rebuild_wellbeing_mirrors(self, entry: dict) -> None:
        """Legacy-Spiegel aus ``wellbeing_entries`` neu bauen (Restore-Helfer)."""
        sync_wellbeing_mirrors(entry)

    async def _async_save(self) -> None:
        await self._store.async_save(self._data)


def prune_audit_log(audit: list[dict], audit_limit: int) -> None:
    """Audit-Liste in-place auf ``audit_limit`` kappen (0 = unbegrenzt).

    Öffentliche Variante der Store-Logik, damit der Restore denselben Cap
    anwendet, ohne die privaten Interna zu duplizieren.
    """
    limit = int(audit_limit)
    if limit <= 0 or len(audit) <= limit:
        return
    if limit == 1:
        audit[:] = audit[-1:]
        return

    # Ein Platz ist für das (einzige) Summary-Ereignis reserviert. Ältere
    # Summaries werden durch das neue ersetzt statt sich anzusammeln.
    keep = limit - 1
    body = [
        event
        for event in audit
        if isinstance(event, dict) and event.get("action") != "audit_pruned"
    ]
    retained = body[-keep:]
    pruned = len(audit) - len(retained)
    oldest_retained = retained[0].get("ts") if retained else None
    audit[:] = retained + [
        {
            "id": str(uuid.uuid4()),
            "ts": _now_iso(),
            "action": "audit_pruned",
            "kind": "audit",
            "target_id": None,
            "actor": None,
            "details": {"pruned": pruned, "oldest_retained": oldest_retained},
        }
    ]


def append_audit_event_to_entry(
    entry: dict,
    action: str,
    kind: str,
    target_id: str | None = None,
    actor: str | None = None,
    details: dict[str, Any] | None = None,
    audit_limit: int = DEFAULT_AUDIT_LIMIT,
    ts: str | None = None,
) -> dict:
    """Audit-Ereignis an ein Eintrags-Dict anhängen (HA-frei, ohne Save).

    ``details`` trägt nur Metadaten, nie vollständige Gesundheitswerte.
    """
    audit = entry.setdefault("audit_log", [])
    event = {
        "id": str(uuid.uuid4()),
        "ts": ts or _now_iso(),
        "action": action,
        "kind": kind,
        "target_id": target_id,
        "actor": actor,
        "details": details or {},
    }
    audit.append(event)
    prune_audit_log(audit, audit_limit)
    return event


def _find_by_id(items: Any, item_id: str) -> dict | None:
    """Eintrag mit passender `id` in einer Store-Liste suchen."""
    if not isinstance(items, list):
        return None
    for item in items:
        if isinstance(item, dict) and item.get("id") == item_id:
            return item
    return None


def _last_active(items: Any) -> dict | None:
    """Letzter aktiver (nicht voided) Dict-Eintrag einer Store-Liste."""
    if not isinstance(items, list):
        return None
    for item in reversed(items):
        if isinstance(item, dict) and not item.get("voided_at"):
            return item
    return None


def _active_items(items: Any) -> list[dict]:
    """Nur aktive (nicht voided) Dict-Einträge einer Store-Liste."""
    if not isinstance(items, list):
        return []
    return [item for item in items if isinstance(item, dict) and not item.get("voided_at")]


def _active_view(entry: dict) -> dict:
    """HA-freie Kopie eines Eintrags mit ausschließlich aktiven Einträgen.

    Die Listen werden neu angelegt (der Rohdatensatz behält seine Objekte);
    Element-Dicts werden geteilt, weil alle Aufrufer sie nur lesen. Die
    Wellbeing-Spiegel werden aus den aktiven Ereignissen neu aufgebaut —
    dieselbe Semantik wie `_sync_wellbeing_mirrors`.
    """
    view = dict(entry)
    view["drinks"] = _active_items(entry.get("drinks"))
    view["readings"] = _active_items(entry.get("readings"))
    if isinstance(entry.get("wellbeing_entries"), list):
        view["wellbeing_entries"] = _active_items(entry.get("wellbeing_entries"))
        _sync_wellbeing_mirrors(view)
    return view


def sync_wellbeing_mirrors(entry: dict) -> None:
    """Öffentlicher Wrapper für ``_sync_wellbeing_mirrors`` (Restore, HA-frei)."""
    _sync_wellbeing_mirrors(entry)


def _sync_wellbeing_mirrors(entry: dict) -> None:
    """Legacy-Spiegel `wellbeing`/`wellbeing_history` aus v4-Events neu bauen.

    Aktueller Wert = letzter aktiver Eintrag. Die Historie führt alle übrigen
    aktiven Meldungen (abgelöste Werte) in Erfassungsreihenfolge, begrenzt auf
    die letzten 100 — exakt die Semantik, die `set_wellbeing` bisher pflegte.
    """
    entries = entry.get("wellbeing_entries")
    if not isinstance(entries, list):
        return
    active = [
        item
        for item in entries
        if isinstance(item, dict) and item.get("key") and not item.get("voided_at")
    ]
    if not active:
        entry["wellbeing"] = {}
        entry["wellbeing_history"] = []
        return
    current = active[-1]
    entry["wellbeing"] = {"status": current["key"], "ts": current.get("ts")}
    entry["wellbeing_history"] = [
        {"ts": item.get("ts"), "status": item["key"]} for item in active[:-1]
    ][-_WELLBEING_HISTORY_LIMIT:]

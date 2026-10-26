"""Restore-Engine für JSON-Backups (Merge/Replace, Teil-Restore, Dry-Run).

Die Planung ist bewusst HA-frei (``parse_backup_document`` / ``plan_restore``):
sie arbeitet ausschließlich auf rohen Store-Dicts und ist damit ohne
Home-Assistant-Instanz testbar. Nur ``apply_restore``/``async_restore_from_file``
berühren HA (Datei-I/O, Store-Save, Notifications/Refresh).

Vertrag in Kurzform:

- ``merge`` (Default): Backup-Einträge ergänzen, Duplikate werden übersprungen.
- ``replace``: gewählter Scope (Personen/Datasets/Zeitraum) wird vorher geleert.
  Mehrere Quellen dürfen auf dasselbe Ziel zeigen (many-to-one): ihre Records
  werden gesammelt, dedupliziert und der Ziel-Scope genau einmal geleert.
- Filter: ``persons``, ``datasets``, ``from``/``to`` (inklusiv auf ``ts``;
  naive Zeitstempel gelten als lokale HA-Zeitzone).
- ``person_map``: ``{source_slug|source_entry_id: target_entry_id}`` — ohne
  Mapping wird über den Personen-Slug (case-insensitive, exakt eine Übereinstimmung)
  zugeordnet. Personen werden NIE automatisch neu angelegt.
- ``restore_audit``: importiert das Audit-Log aus dem Backup zusätzlich
  (dedupliziert über ``id``); standardmäßig werden nur neue
  ``restore_backup``-Events geschrieben.
- Genau EIN Save pro Store; bei Fehlern wird der In-Memory-Stand zurückgerollt.
- Vor jedem echten Restore entsteht ein Pre-Restore-Backup im privaten
  Export-Ordner.
"""

from __future__ import annotations

import copy
import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .backup import (
    BACKUP_FORMAT,
    BACKUP_VERSION,
    async_write_backup_document,
    build_backup_document,
)
from .const import DEFAULT_AUDIT_LIMIT, DOMAIN, STORE_SCHEMA_VERSION
from .entity import signal_refresh
from .importer import safe_restore_path
from .store import (
    HealthOMatStore,
    append_audit_event_to_entry,
    async_load_archive_store,
    migrate_store_data,
    prune_audit_log,
    sync_wellbeing_mirrors,
)

_LOGGER = logging.getLogger(__name__)

RESTORE_MODES: tuple[str, ...] = ("merge", "replace")
DATASETS: tuple[str, ...] = ("drinks", "blood_pressure", "wellbeing")
DATASET_LIST: dict[str, str] = {
    "drinks": "drinks",
    "blood_pressure": "readings",
    "wellbeing": "wellbeing_entries",
}
_DATASET_ALIASES: dict[str, str] = {
    "drink": "drinks",
    "drinks": "drinks",
    "readings": "blood_pressure",
    "reading": "blood_pressure",
    "blood_pressure": "blood_pressure",
    "wellbeing": "wellbeing",
    "wellbeing_entries": "wellbeing",
}
REPLACE_CONFIRM = "REPLACE"
ACTION_DETAIL_LIMIT = 1000


class RestoreError(ValueError):
    """Fachlicher Restore-Fehler (Datei/Format/Plan/Apply)."""


# ---------------------------------------------------------------------------
# Parsen / Validieren
# ---------------------------------------------------------------------------
def validate_backup(document: Any) -> str | None:
    """Prüft Format/Version/Schema/Entries. ``None`` = gültig, sonst Meldung."""
    if not isinstance(document, dict):
        return "Backup-Dokument muss ein JSON-Objekt sein"
    if document.get("format") != BACKUP_FORMAT:
        return f"Unbekanntes Backup-Format: {document.get('format')!r} (erwartet {BACKUP_FORMAT!r})"
    version = document.get("version")
    if isinstance(version, bool) or not isinstance(version, int):
        return "Backup-Version fehlt oder ist keine Zahl"
    if version < 1:
        return f"Ungültige Backup-Version: {version}"
    if version > BACKUP_VERSION:
        return (
            f"Backup-Version {version} wird nicht unterstützt "
            f"(diese Integration liest bis Version {BACKUP_VERSION})"
        )
    entries = document.get("entries")
    if not isinstance(entries, dict):
        return "Backup enthält keine gültige 'entries'-Sektion"
    for source_id, entry in entries.items():
        if not isinstance(entry, dict):
            return f"Backup-Eintrag {source_id!r} ist kein Objekt"
    schema = document.get("schema")
    if schema is not None:
        if isinstance(schema, bool) or not isinstance(schema, int):
            return "Backup-Schema ist keine Zahl"
        if schema > STORE_SCHEMA_VERSION:
            return f"Backup-Schema {schema} ist neuer als unterstützt ({STORE_SCHEMA_VERSION})"
    archive = document.get("archive_entries")
    if archive is not None:
        if not isinstance(archive, dict):
            return "Backup enthält keine gültige 'archive_entries'-Sektion"
        for source_id, entry in archive.items():
            if not isinstance(entry, dict):
                return f"Archiv-Eintrag {source_id!r} ist kein Objekt"
    archive_schema = document.get("archive_schema")
    if archive_schema is not None:
        if isinstance(archive_schema, bool) or not isinstance(archive_schema, int):
            return "Backup-Archiv-Schema ist keine Zahl"
        if archive_schema > STORE_SCHEMA_VERSION:
            return (
                f"Backup-Archiv-Schema {archive_schema} ist neuer als unterstützt "
                f"({STORE_SCHEMA_VERSION})"
            )
    return None


def parse_backup_document(document: Any) -> dict:
    """Validiert und normalisiert ein Backup-Dokument auf Store-Schema v4.

    v1-Backups (``version: 1``) werden über die bestehende Migrationskette
    angehoben; ``version > BACKUP_VERSION`` wird klar abgelehnt.
    """
    error = validate_backup(document)
    if error is not None:
        raise RestoreError(error)

    version = int(document["version"])
    schema = document.get("schema")
    if schema is None:
        # Fehlende Schema-Markierung = Altbestand (v1); die Migrationskette ist
        # idempotent und lässt bereits v4-konforme Einträge unverändert.
        schema = 1
    entries = copy.deepcopy(document.get("entries") or {})
    store_data = {"schema": int(schema), "entries": entries}
    try:
        migrate_store_data(store_data)
    except (TypeError, ValueError) as err:
        raise RestoreError(f"Backup-Einträge nicht migrierbar: {err}") from err
    entries = {str(key): value for key, value in store_data["entries"].items()}

    archive_entries = copy.deepcopy(document.get("archive_entries") or {})
    archive_schema = document.get("archive_schema")
    if archive_entries:
        try:
            migrate_store_data(
                {
                    "schema": int(archive_schema or schema),
                    "entries": archive_entries,
                }
            )
        except (TypeError, ValueError) as err:
            raise RestoreError(f"Archiv-Einträge nicht migrierbar: {err}") from err

    normalized = dict(document)
    normalized["version"] = version
    normalized["schema"] = int(store_data["schema"])
    normalized["entries"] = entries
    normalized["archive_entries"] = {str(key): value for key, value in archive_entries.items()}
    normalized["archive_schema"] = archive_schema
    normalized["persons"] = (
        document.get("persons") if isinstance(document.get("persons"), dict) else {}
    )
    normalized["counts"] = (
        document.get("counts") if isinstance(document.get("counts"), dict) else {}
    )
    return normalized


# ---------------------------------------------------------------------------
# Plan
# ---------------------------------------------------------------------------
@dataclass
class RestorePlan:
    """Ergebnis der reinen Restore-Planung.

    ``target_entries``/``target_archive_entries``/``audit_imports`` sind interne
    Apply-Daten und werden von :meth:`as_dict` NICHT nach außen gegeben.
    """

    mode: str = "merge"
    persons: dict[str, str] = field(default_factory=dict)
    actions: list[dict] = field(default_factory=list)
    counts: dict[str, dict[str, dict[str, int]]] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    target_entries: dict[str, dict] = field(default_factory=dict, repr=False)
    target_archive_entries: dict[str, dict] | None = field(default=None, repr=False)
    audit_imports: dict[str, list[dict]] = field(default_factory=dict, repr=False)
    affected_targets: list[str] = field(default_factory=list, repr=False)
    archive_changed: bool = False
    has_changes: bool = False

    def totals(self) -> dict[str, int]:
        totals = {"added": 0, "skipped": 0, "conflicts": 0, "errors": 0}
        for per_dataset in self.counts.values():
            for values in per_dataset.values():
                for key in totals:
                    totals[key] += int(values.get(key, 0))
        return totals

    def as_dict(self) -> dict:
        """Öffentliche, kompakte Darstellung (Dry-Run/WS/Service)."""
        actions = self.actions[:ACTION_DETAIL_LIMIT]
        return {
            "mode": self.mode,
            "persons": dict(self.persons),
            "counts": copy.deepcopy(self.counts),
            "totals": self.totals(),
            "actions": copy.deepcopy(actions),
            "actions_truncated": len(self.actions) > ACTION_DETAIL_LIMIT,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
            "has_changes": self.has_changes,
        }


def _new_counts() -> dict[str, int]:
    return {"added": 0, "skipped": 0, "conflicts": 0, "errors": 0}


def _local_timezone() -> Any:
    """Lokale HA-Zeitzone, defensiv (Fakes/Tests ohne ``DEFAULT_TIME_ZONE``)."""
    return getattr(dt_util, "DEFAULT_TIME_ZONE", None)


def _iso(value: Any) -> str | None:
    """Dedup-Schlüssel: Zeitpunkt auf **UTC normalisiert**.

    Derselbe Instant in unterschiedlicher Repräsentation (``Z`` vs. Offset)
    ergibt so denselben Schlüssel — sonst würden Einträge doppelt gezählt.
    """
    normalized = _ts_dt(value)
    return normalized.isoformat() if normalized is not None else None


def _ts_dt(value: Any) -> datetime | None:
    """ISO-Zeitstempel als vergleichbares ``datetime`` (UTC, naiv).

    Naive Werte (z. B. rohe ``datetime-local``-Eingaben der Admin-UI) werden
    als **lokale HA-Zeitzone** interpretiert — nicht als UTC. Sonst verschiebt
    sich der Restore-Zeitraum um den Zonen-Offset und ein Replace kann
    Einträge außerhalb des gewählten Fensters löschen.
    """
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.strip())
        except ValueError:
            return None
    else:
        return None
    if parsed.tzinfo is not None:
        return parsed.astimezone(UTC).replace(tzinfo=None)
    tz = _local_timezone()
    if tz is not None:
        try:
            return parsed.replace(tzinfo=tz).astimezone(UTC).replace(tzinfo=None)
        except (TypeError, ValueError, AttributeError, OSError):
            # Defensive: unbrauchbare Fake-Zeitzone → wie bisher naiv weiter.
            pass
    return parsed


def _parse_bound(value: Any, label: str) -> datetime | None:
    if value is None or value == "":
        return None
    parsed = _ts_dt(value)
    if parsed is None:
        raise RestoreError(f"Ungültiger '{label}'-Zeitstempel: {value!r} (ISO erwartet)")
    return parsed


def _in_range(record: dict, start: datetime | None, end: datetime | None) -> bool:
    if start is None and end is None:
        return True
    ts = _ts_dt(record.get("ts"))
    if ts is None:
        return False
    if start is not None and ts < start:
        return False
    if end is not None and ts > end:
        return False
    return True


def _dedup_key(dataset: str, record: dict) -> tuple | None:
    ts = _iso(record.get("ts")) or str(record.get("ts"))
    try:
        if dataset == "drinks":
            return (ts, int(record.get("ml", 0)), str(record.get("type") or ""))
        if dataset == "blood_pressure":
            return (ts, int(record.get("sys", 0)), int(record.get("dia", 0)))
        if dataset == "wellbeing":
            return (ts, str(record.get("key") or ""))
    except (TypeError, ValueError):
        return None
    return None


def _normalize_record(record: dict) -> dict:
    """v4-Felder ergänzen, ohne vorhandene Werte zu überschreiben."""
    if not record.get("id"):
        record["id"] = str(uuid.uuid4())
    else:
        record["id"] = str(record["id"])
    record.setdefault("created_at", record.get("ts"))
    record.setdefault("voided_at", None)
    record.setdefault("voided_by", None)
    record.setdefault("void_reason", None)
    return record


def _is_active(record: dict) -> bool:
    return isinstance(record, dict) and not record.get("voided_at")


def _ml(record: dict) -> int:
    try:
        return int(record.get("ml", 0))
    except (TypeError, ValueError):
        return 0


def _int(value: Any, default: int = 0) -> int:
    if isinstance(value, bool):
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _collect_ids(entries: dict) -> set[str]:
    used: set[str] = set()
    for entry in entries.values():
        if not isinstance(entry, dict):
            continue
        for list_name in (*DATASET_LIST.values(),):
            for item in entry.get(list_name) or []:
                if isinstance(item, dict) and item.get("id"):
                    used.add(str(item["id"]))
    return used


def _prepare_records(
    records: list[dict],
    dataset: str,
    used_ids: set[str],
    counts: dict[str, int],
    warnings: list[str],
    seen: set,
) -> tuple[list[dict], int]:
    """Validieren, deduplizieren und für den Store vorbereiten (Merge/Replace).

    Beide Modi nutzen dieselbe Prüfung: ein Record ohne gültigen Dedup-Schlüssel
    (z. B. ``ml: "abc"``) wird verworfen und als Fehler gezählt — Replace darf
    ungültige Backup-Records nicht ungeprüft einfügen. ``seen`` wird in-place
    erweitert und liefert die Rückgabe ``(prepared_records, active_ml)``.
    """
    prepared_records: list[dict] = []
    active_ml = 0
    for record in records:
        key = _dedup_key(dataset, record)
        if key is None:
            counts["errors"] += 1
            warnings.append(f"{dataset}: Eintrag ohne gültigen Schlüssel")
            continue
        if key in seen:
            counts["skipped"] += 1
            continue
        seen.add(key)
        prepared = _normalize_record(copy.deepcopy(record))
        record_id = str(prepared.get("id"))
        if record_id in used_ids:
            prepared["id"] = str(uuid.uuid4())
            counts["conflicts"] += 1
        used_ids.add(str(prepared["id"]))
        prepared_records.append(prepared)
        if dataset == "drinks" and _is_active(prepared):
            active_ml += _ml(prepared)
    return prepared_records, active_ml


def _normalize_datasets(datasets: Any) -> tuple[str, ...] | None:
    if datasets is None:
        return None
    if isinstance(datasets, str):
        datasets = [datasets]
    if not isinstance(datasets, (list, tuple, set)):
        raise RestoreError("'datasets' muss eine Liste sein")
    resolved: list[str] = []
    for value in datasets:
        canonical = _DATASET_ALIASES.get(str(value).strip().lower())
        if canonical is None:
            raise RestoreError(f"Unbekannter Datensatz {value!r} — erlaubt: {', '.join(DATASETS)}")
        if canonical not in resolved:
            resolved.append(canonical)
    return tuple(resolved) or None


def _slug(entry: dict) -> str:
    return str(entry.get("person") or "").strip()


def _resolve_persons(
    backup: dict,
    current_entries: dict[str, dict],
    person_map: dict | None,
    persons_filter: list[str] | None,
) -> tuple[list[tuple[str, str]], dict[str, str], list[str], list[str]]:
    """Quelle→Ziel-Mapping auflösen (kein Auto-Anlegen).

    Returns: ``(selected, public_map, errors, warnings)``.
    """
    errors: list[str] = []
    warnings: list[str] = []
    source_ids = [str(key) for key in backup.get("entries", {})]
    current = {str(key): value for key, value in current_entries.items() if isinstance(value, dict)}
    slug_index: dict[str, list[str]] = {}
    for target_id, entry in current.items():
        slug = _slug(entry).lower()
        if slug:
            slug_index.setdefault(slug, []).append(target_id)

    explicit_exact: dict[str, str] = {}
    explicit_lower: dict[str, str] = {}
    if person_map is not None and not isinstance(person_map, dict):
        errors.append("'person_map' muss ein Objekt {Quelle: Ziel-Entry-ID} sein")
        person_map = {}
    for raw_key, raw_target in (person_map or {}).items():
        key = str(raw_key).strip()
        target = str(raw_target).strip()
        if not key or not target:
            errors.append("person_map enthält einen leeren Schlüssel oder ein leeres Ziel")
            continue
        if target not in current:
            errors.append(f"person_map: Ziel-Entry '{target}' existiert nicht")
            continue
        explicit_exact[key] = target
        explicit_lower[key.lower()] = target

    mapping: dict[str, str] = {}
    for source_id in source_ids:
        source_entry = backup["entries"].get(source_id)
        source_entry = source_entry if isinstance(source_entry, dict) else {}
        slug = _slug(source_entry)
        target = (
            explicit_exact.get(source_id)
            or explicit_lower.get(source_id.lower())
            or (explicit_exact.get(slug) if slug else None)
            or (explicit_lower.get(slug.lower()) if slug else None)
        )
        if target is None:
            if not slug:
                errors.append(
                    f"Quelle '{source_id}' hat keinen Personennamen — person_map ist erforderlich"
                )
                continue
            matches = slug_index.get(slug.lower(), [])
            if len(matches) == 1:
                target = matches[0]
            elif not matches:
                errors.append(
                    f"Person '{slug}' (Quelle {source_id}) existiert im Ziel nicht — "
                    "person_map angeben (Personen werden nicht automatisch angelegt)"
                )
                continue
            else:
                errors.append(
                    f"Person '{slug}' ist im Ziel mehrdeutig "
                    f"({', '.join(sorted(matches))}) — person_map angeben"
                )
                continue
        mapping[source_id] = target

    known_sources = set(source_ids)
    for key in list(explicit_exact):
        if key not in known_sources and key.lower() not in {
            _slug(backup["entries"].get(sid) or {}).lower() for sid in source_ids
        }:
            warnings.append(f"person_map: Quelle '{key}' kommt im Backup nicht vor")

    resolved = [(source_id, target) for source_id, target in mapping.items()]
    if persons_filter:
        wanted = {str(value).strip().lower() for value in persons_filter if str(value).strip()}
        selected: list[tuple[str, str]] = []
        matched: set[str] = set()
        for source_id, target in resolved:
            entry = backup["entries"].get(source_id) or {}
            slug = _slug(entry)
            candidates = {source_id.lower(), target.lower()}
            if slug:
                candidates.add(slug.lower())
            hit = candidates & wanted
            if hit:
                selected.append((source_id, target))
                matched |= hit
        unknown = sorted(wanted - matched)
        for value in unknown:
            errors.append(f"Unbekannte Person im Filter: '{value}'")
        resolved = selected

    if not resolved and not errors:
        errors.append("Keine Person für den Restore ausgewählt")

    public: dict[str, str] = {}
    for source_id, target in resolved:
        public[source_id] = target
        slug = _slug(backup["entries"].get(source_id) or {})
        if slug and slug not in public:
            public[slug] = target
    return resolved, public, errors, warnings


def plan_restore(
    backup: dict,
    current_entries: dict,
    *,
    mode: str = "merge",
    persons: list[str] | None = None,
    datasets: list[str] | None = None,
    from_ts: Any = None,
    to_ts: Any = None,
    person_map: dict | None = None,
    restore_audit: bool = False,
    current_archive_entries: dict | None = None,
) -> RestorePlan:
    """Plant einen Restore HA-frei (keine Schreibzugriffe)."""
    normalized = parse_backup_document(backup)
    normalized_mode = str(mode or "merge").strip().lower()
    if normalized_mode not in RESTORE_MODES:
        raise RestoreError(f"Unbekannter Modus {mode!r} — erlaubt: {', '.join(RESTORE_MODES)}")
    selected_datasets = _normalize_datasets(datasets)
    start = _parse_bound(from_ts, "from")
    end = _parse_bound(to_ts, "to")
    if start is not None and end is not None and start > end:
        raise RestoreError("'from' liegt nach 'to'")

    plan = RestorePlan(
        mode=normalized_mode,
        target_entries=copy.deepcopy(current_entries),
    )
    if current_archive_entries is not None:
        plan.target_archive_entries = copy.deepcopy(current_archive_entries)
    else:
        plan.target_archive_entries = None
        if normalized.get("archive_entries"):
            plan.warnings.append(
                "Archiv-Store nicht verfügbar — Archivdaten werden nicht wiederhergestellt"
            )

    selected, public_map, errors, warnings = _resolve_persons(
        normalized, current_entries, person_map, persons
    )
    plan.persons = public_map
    plan.errors.extend(errors)
    plan.warnings.extend(warnings)
    if plan.errors:
        return plan

    chosen = selected_datasets or DATASETS
    used_ids = _collect_ids(plan.target_entries)
    if plan.target_archive_entries is not None:
        used_ids |= _collect_ids(plan.target_archive_entries)

    # Laufzeit-Metriken je Ziel
    lifetime_add: dict[str, int] = {}
    lifetime_removed: dict[str, int] = {}
    lifetime_added: dict[str, int] = {}
    sources_per_target: dict[str, int] = {}
    backup_lifetime: dict[str, int | None] = {}
    wellbeing_touched: set[str] = set()
    changed_targets: set[str] = set()
    # Dedup im Merge gilt über BEIDE Stores: ein Eintrag, der im Ziel bereits
    # im Haupt- oder Archiv-Store liegt, darf nicht in den anderen Store
    # dupliziert werden (sonst zählt Export/Lifetime ihn doppelt).
    merge_seen: dict[tuple[str, str], set] = {}
    # Replace wird pro Ziel/Datensatz aggregiert (B-1): mehrere Quellen können
    # auf dasselbe Ziel zeigen (many-to-one). Der Scope darf dann nur EINMAL
    # geleert werden — sonst überschreibt die letzte Quelle die vorherigen.
    replace_records: dict[tuple[str, str], list[dict]] = {}
    replace_archive: dict[tuple[str, str], list[dict]] = {}
    replace_sources: dict[tuple[str, str], list[str]] = {}

    for source_id, target in selected:
        sources_per_target[target] = sources_per_target.get(target, 0) + 1
        source_entry = normalized["entries"].get(source_id) or {}
        if isinstance(source_entry.get("total_ml_lifetime"), int) and not isinstance(
            source_entry.get("total_ml_lifetime"), bool
        ):
            backup_lifetime[target] = int(source_entry["total_ml_lifetime"])
        elif target not in backup_lifetime:
            backup_lifetime[target] = None

        plan.target_entries.setdefault(target, {})
        plan.counts.setdefault(target, {dataset: _new_counts() for dataset in chosen})

        if restore_audit:
            events = source_entry.get("audit_log")
            if isinstance(events, list):
                bucket = plan.audit_imports.setdefault(target, [])
                known = {event.get("id") for event in bucket if isinstance(event, dict)}
                for event in events:
                    if isinstance(event, dict) and event.get("id") not in known:
                        bucket.append(copy.deepcopy(event))
                        known.add(event.get("id"))

        for dataset in chosen:
            counts = plan.counts[target][dataset]
            list_name = DATASET_LIST[dataset]
            source_records = source_entry.get(list_name)
            source_records = source_records if isinstance(source_records, list) else []
            records = [
                record
                for record in source_records
                if isinstance(record, dict) and _in_range(record, start, end)
            ]
            for record in source_records:
                if not isinstance(record, dict):
                    counts["errors"] += 1
                    plan.warnings.append(f"{dataset}: ungültiger Eintrag in Quelle {source_id}")

            archive_records: list[dict] = []
            if dataset != "wellbeing" and plan.target_archive_entries is not None:
                archive_source_entry = (normalized.get("archive_entries") or {}).get(
                    source_id
                ) or {}
                archive_source = archive_source_entry.get(list_name)
                archive_source = archive_source if isinstance(archive_source, list) else []
                archive_records = [
                    record
                    for record in archive_source
                    if isinstance(record, dict) and _in_range(record, start, end)
                ]

            if normalized_mode == "merge":
                target_entry = plan.target_entries[target]
                existing = target_entry.setdefault(list_name, [])
                if not isinstance(existing, list):
                    existing = []
                    target_entry[list_name] = existing
                seen_key = (target, dataset)
                seen = merge_seen.get(seen_key)
                if seen is None:
                    seen = {
                        _dedup_key(dataset, item) for item in existing if isinstance(item, dict)
                    }
                    if plan.target_archive_entries is not None:
                        archive_lists = plan.target_archive_entries.get(target) or {}
                        archive_items = archive_lists.get(list_name)
                        if isinstance(archive_items, list):
                            seen |= {
                                _dedup_key(dataset, item)
                                for item in archive_items
                                if isinstance(item, dict)
                            }
                    merge_seen[seen_key] = seen
                prepared_records, added_ml = _prepare_records(
                    records, dataset, used_ids, counts, plan.warnings, seen
                )
                for prepared in prepared_records:
                    existing.append(prepared)
                    counts["added"] += 1
                    changed_targets.add(target)
                    plan.actions.append(
                        {
                            "target": target,
                            "source": source_id,
                            "dataset": dataset,
                            "op": "add",
                            "id": prepared["id"],
                            "ts": prepared.get("ts"),
                        }
                    )
                if dataset == "drinks" and added_ml:
                    lifetime_add[target] = lifetime_add.get(target, 0) + added_ml
                if dataset == "wellbeing":
                    wellbeing_touched.add(target)

                # Archiv nur für Getränke/Messungen; Wellbeing hat kein Archiv.
                if dataset == "wellbeing" or plan.target_archive_entries is None:
                    continue
                archive_entry = plan.target_archive_entries.setdefault(
                    target, {"drinks": [], "readings": []}
                )
                archive_existing = archive_entry.setdefault(list_name, [])
                if not isinstance(archive_existing, list):
                    archive_existing = []
                    archive_entry[list_name] = archive_existing
                seen = merge_seen.setdefault((target, dataset), set())
                prepared_archive, archive_ml = _prepare_records(
                    archive_records, dataset, used_ids, counts, plan.warnings, seen
                )
                for prepared in prepared_archive:
                    archive_existing.append(prepared)
                    counts["added"] += 1
                    plan.archive_changed = True
                    changed_targets.add(target)
                    plan.actions.append(
                        {
                            "target": target,
                            "source": source_id,
                            "dataset": dataset,
                            "op": "add",
                            "archive": True,
                            "id": prepared["id"],
                            "ts": prepared.get("ts"),
                        }
                    )
                if dataset == "drinks" and archive_ml:
                    lifetime_add[target] = lifetime_add.get(target, 0) + archive_ml
            else:  # replace — nur sammeln, Ausführung nach allen Quellen
                replace_records.setdefault((target, dataset), []).extend(records)
                sources = replace_sources.setdefault((target, dataset), [])
                if source_id not in sources:
                    sources.append(source_id)
                if dataset != "wellbeing" and plan.target_archive_entries is not None:
                    replace_archive.setdefault((target, dataset), []).extend(archive_records)

    if normalized_mode == "replace":
        for (target, dataset), records in replace_records.items():
            counts = plan.counts[target][dataset]
            target_entry = plan.target_entries.setdefault(target, {})
            list_name = DATASET_LIST[dataset]
            existing = target_entry.get(list_name)
            if not isinstance(existing, list):
                existing = []
                target_entry[list_name] = existing
            kept: list[dict] = []
            removed = 0
            removed_ml = 0
            for item in existing:
                if isinstance(item, dict) and _in_range(item, start, end):
                    removed += 1
                    if item.get("id"):
                        used_ids.discard(str(item["id"]))
                    if dataset == "drinks" and _is_active(item):
                        removed_ml += _ml(item)
                else:
                    kept.append(item)
            prepared_records, added_ml = _prepare_records(
                records, dataset, used_ids, counts, plan.warnings, set()
            )
            kept.extend(prepared_records)
            target_entry[list_name] = kept
            counts["added"] += len(prepared_records)
            if removed or prepared_records:
                changed_targets.add(target)
            if dataset == "drinks":
                lifetime_removed[target] = lifetime_removed.get(target, 0) + removed_ml
                lifetime_added[target] = lifetime_added.get(target, 0) + added_ml
            if dataset == "wellbeing":
                wellbeing_touched.add(target)
            sources = replace_sources.get((target, dataset), [])
            plan.actions.append(
                {
                    "target": target,
                    "source": sources[0] if len(sources) == 1 else ", ".join(sources),
                    "sources": list(sources),
                    "dataset": dataset,
                    "op": "replace",
                    "removed": removed,
                    "added": len(prepared_records),
                    "from": start.isoformat() if start else None,
                    "to": end.isoformat() if end else None,
                }
            )

        for (target, dataset), records in replace_archive.items():
            if plan.target_archive_entries is None:
                continue
            counts = plan.counts[target][dataset]
            list_name = DATASET_LIST[dataset]
            archive_entry = plan.target_archive_entries.setdefault(
                target, {"drinks": [], "readings": []}
            )
            archive_existing = archive_entry.get(list_name)
            if not isinstance(archive_existing, list):
                archive_existing = []
                archive_entry[list_name] = archive_existing
            kept_archive: list[dict] = []
            removed_archive = 0
            removed_archive_ml = 0
            for item in archive_existing:
                if isinstance(item, dict) and _in_range(item, start, end):
                    removed_archive += 1
                    if item.get("id"):
                        used_ids.discard(str(item["id"]))
                    if dataset == "drinks" and _is_active(item):
                        removed_archive_ml += _ml(item)
                else:
                    kept_archive.append(item)
            prepared_archive, added_archive_ml = _prepare_records(
                records, dataset, used_ids, counts, plan.warnings, set()
            )
            kept_archive.extend(prepared_archive)
            archive_entry[list_name] = kept_archive
            if removed_archive or prepared_archive:
                plan.archive_changed = True
                changed_targets.add(target)
            if dataset == "drinks":
                lifetime_removed[target] = lifetime_removed.get(target, 0) + removed_archive_ml
                lifetime_added[target] = lifetime_added.get(target, 0) + added_archive_ml
            counts["added"] += len(prepared_archive)
            sources = replace_sources.get((target, dataset), [])
            plan.actions.append(
                {
                    "target": target,
                    "source": sources[0] if len(sources) == 1 else ", ".join(sources),
                    "sources": list(sources),
                    "dataset": dataset,
                    "op": "replace",
                    "archive": True,
                    "removed": removed_archive,
                    "added": len(prepared_archive),
                    "from": start.isoformat() if start else None,
                    "to": end.isoformat() if end else None,
                }
            )

    # Wellbeing-Spiegel aus den Ereignissen neu bauen (Store-Logik, kein Duplikat).
    for target in wellbeing_touched:
        entry = plan.target_entries.get(target)
        if isinstance(entry, dict):
            sync_wellbeing_mirrors(entry)

    # Lifetime: Merge addiert nur aktive importierte ml; Replace setzt im
    # Gesamt-Personen-Scope den Backup-Wert, sonst Delta-Korrektur (nie negativ).
    full_scope = (
        (selected_datasets is None or set(selected_datasets) == set(DATASETS))
        and start is None
        and end is None
    )
    for target in plan.counts:
        entry = plan.target_entries.setdefault(target, {})
        current_lifetime = _int(entry.get("total_ml_lifetime"), 0)
        if normalized_mode == "merge":
            new_lifetime = current_lifetime + lifetime_add.get(target, 0)
        elif (
            full_scope
            and sources_per_target.get(target, 0) == 1
            and isinstance(backup_lifetime.get(target), int)
            and "drinks" in chosen
        ):
            new_lifetime = int(backup_lifetime[target])
        else:
            new_lifetime = (
                current_lifetime - lifetime_removed.get(target, 0) + lifetime_added.get(target, 0)
            )
            if full_scope and sources_per_target.get(target, 0) > 1:
                plan.warnings.append(
                    f"Person {target}: mehrere Quellen — Lebenszähler per Delta "
                    "korrigiert statt gesetzt"
                )
        entry["total_ml_lifetime"] = max(0, new_lifetime)

    plan.affected_targets = sorted(changed_targets)
    plan.has_changes = bool(changed_targets)
    return plan


# ---------------------------------------------------------------------------
# Apply
# ---------------------------------------------------------------------------
def _audit_limit_for(hass: HomeAssistant, entry_id: str) -> int:
    """Audit-Cap aus ``entry.options`` (Default 1000, 0 = unbegrenzt)."""
    from . import logic

    try:
        entry = hass.config_entries.async_get_entry(entry_id)
    except Exception:  # noqa: BLE001 - Options-Lesen ist nie restore-kritisch
        entry = None
    options = getattr(entry, "options", None) if entry is not None else None
    return logic.audit_limit_from_options(options)


async def apply_restore(
    hass: HomeAssistant,
    store: HealthOMatStore,
    archive_store: HealthOMatStore | None,
    plan: RestorePlan,
    *,
    actor: str | None = None,
    audit_limit_by_entry: dict[str, int] | None = None,
    write_pre_backup: bool = True,
) -> dict:
    """Wendet einen Plan an — Pre-Backup, genau ein Save je Store, Rollback.

    Bei ``plan.errors`` oder ohne Änderungen wird nichts geschrieben.
    """
    if plan.errors:
        raise RestoreError("; ".join(plan.errors))
    if store is None:
        raise RestoreError("Health-O-Mat-Speicher nicht verfügbar")
    if not plan.has_changes:
        return {
            "applied": True,
            "dry_run": False,
            "backup_path": None,
            "mode": plan.mode,
            "persons": dict(plan.persons),
            "counts": copy.deepcopy(plan.counts),
            "totals": plan.totals(),
            "warnings": list(plan.warnings),
        }

    pre_backup_path: str | None = None
    if write_pre_backup:
        document = build_backup_document(
            store.raw_data(),
            dt_util.now(),
            archive_store.raw_data() if archive_store is not None else None,
        )
        try:
            pre_backup_path = await async_write_backup_document(
                hass, document, prefix="pre_restore"
            )
        except OSError as err:
            raise RestoreError(f"Sicherheitsbackup konnte nicht geschrieben werden: {err}") from err

    limits = audit_limit_by_entry or {}
    desired = copy.deepcopy(plan.target_entries)
    for target in plan.affected_targets:
        entry = desired.get(target)
        if not isinstance(entry, dict):
            continue
        limit = int(limits.get(target, DEFAULT_AUDIT_LIMIT))
        imports = plan.audit_imports.get(target, [])
        if imports:
            audit = entry.setdefault("audit_log", [])
            known_ids = {event.get("id") for event in audit if isinstance(event, dict)}
            for event in imports:
                if event.get("id") in known_ids:
                    continue
                audit.append(copy.deepcopy(event))
                known_ids.add(event.get("id"))
            prune_audit_log(audit, limit)
        append_audit_event_to_entry(
            entry,
            "restore_backup",
            "restore",
            actor=actor,
            details={
                "mode": plan.mode,
                "counts": copy.deepcopy(plan.counts.get(target, {})),
            },
            audit_limit=limit,
        )

    old_archive = None
    new_archive = None
    if archive_store is not None and plan.target_archive_entries is not None:
        old_archive = archive_store.raw_entries_copy()
        new_archive = copy.deepcopy(plan.target_archive_entries)

    try:
        if archive_store is not None and new_archive is not None:
            if new_archive != old_archive:
                await archive_store.async_set_entries(new_archive)
        await store.async_set_entries(desired)
    except Exception as err:  # noqa: BLE001 - jeder Fehler wird zum Rollback
        if archive_store is not None and old_archive is not None:
            try:
                await archive_store.async_set_entries(old_archive)
            except Exception:  # noqa: BLE001 - Rollback ist best effort
                _LOGGER.exception("Health-O-Mat: Archiv-Rollback fehlgeschlagen")
        raise RestoreError(f"Restore fehlgeschlagen, keine Änderung übernommen: {err}") from err

    for target in plan.affected_targets:
        try:
            signal_refresh(hass, target)
        except Exception:  # noqa: BLE001 - Refresh ist nie restore-kritisch
            _LOGGER.exception("Health-O-Mat: Refresh nach Restore für %s fehlgeschlagen", target)

    return {
        "applied": True,
        "dry_run": False,
        "backup_path": pre_backup_path,
        "mode": plan.mode,
        "persons": dict(plan.persons),
        "counts": copy.deepcopy(plan.counts),
        "totals": plan.totals(),
        "warnings": list(plan.warnings),
    }


# ---------------------------------------------------------------------------
# Datei/Service/WS-Einstieg
# ---------------------------------------------------------------------------
def _read_backup_file(path: str) -> dict:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


async def async_restore_from_file(
    hass: HomeAssistant,
    store: HealthOMatStore,
    archive_store: HealthOMatStore | None,
    data: dict,
    *,
    actor: str | None = None,
) -> dict:
    """Liest ein Backup aus dem Import-Ordner, plant und wendet es an."""
    if store is None:
        raise RestoreError("Health-O-Mat-Speicher nicht verfügbar")
    filename = str(data.get("filename") or "").strip()
    try:
        path = safe_restore_path(hass.config.config_dir, filename)
    except ValueError as err:
        raise RestoreError(str(err)) from err

    try:
        payload = await hass.async_add_executor_job(_read_backup_file, path)
    except FileNotFoundError as err:
        raise RestoreError(f"Backup-Datei nicht gefunden: {filename}") from err
    except OSError as err:
        raise RestoreError(f"Backup-Datei nicht lesbar: {filename}") from err
    except json.JSONDecodeError as err:
        raise RestoreError(f"Backup-Datei ist kein gültiges JSON: {err.msg}") from err

    document = parse_backup_document(payload)

    mode = str(data.get("mode") or "merge").strip().lower()
    if mode not in RESTORE_MODES:
        raise RestoreError(f"Unbekannter Modus {mode!r} — erlaubt: {', '.join(RESTORE_MODES)}")
    dry_run = bool(data.get("dry_run", False))
    confirm = str(data.get("confirm") or "")
    # N-7: Nur der echte Replace-Lauf braucht die Bestätigung — ein Dry-Run
    # darf die Auswirkungen immer anzeigen.
    if mode == "replace" and not dry_run and confirm != REPLACE_CONFIRM:
        raise RestoreError(f"Replace erfordert die Bestätigung '{REPLACE_CONFIRM}'")

    person_map = data.get("person_map")
    if person_map is not None and not isinstance(person_map, dict):
        raise RestoreError("'person_map' muss ein Objekt {Quelle: Ziel-Entry-ID} sein")

    plan = plan_restore(
        document,
        store.raw_entries_copy(),
        mode=mode,
        persons=data.get("persons"),
        datasets=data.get("datasets"),
        from_ts=data.get("from"),
        to_ts=data.get("to"),
        person_map=person_map,
        restore_audit=bool(data.get("restore_audit", False)),
        current_archive_entries=(
            archive_store.raw_entries_copy() if archive_store is not None else None
        ),
    )
    if plan.errors:
        raise RestoreError("; ".join(plan.errors))

    if dry_run:
        return {
            "plan": plan.as_dict(),
            "applied": False,
            "dry_run": True,
            "backup_path": None,
        }

    result = await apply_restore(
        hass,
        store,
        archive_store,
        plan,
        actor=actor,
        audit_limit_by_entry={
            target: _audit_limit_for(hass, target) for target in plan.affected_targets
        },
    )
    return {
        "plan": plan.as_dict(),
        "applied": result["applied"],
        "dry_run": False,
        "backup_path": result["backup_path"],
        "counts": result["counts"],
        "totals": result["totals"],
        "warnings": result["warnings"],
    }


async def async_restore_command(
    hass: HomeAssistant, data: dict, *, actor: str | None = None
) -> dict:
    """Gemeinsamer Einstieg für Service und WS (löst Store/Archiv auf)."""
    shared = hass.data.get(DOMAIN, {}).get("shared", {})
    store = shared.get("store")
    archive_store = shared.get("archive_store")
    if store is not None and archive_store is None:
        # B-2: Das Archiv darf nicht unsichtbar sein, nur weil Retention beim
        # Setup AUS war. Bei Bedarf laden (leerer Bestand, kein Schreiben);
        # so deckt ein Restore mit `archive_entries` auch das Archiv ab.
        archive_store = await async_load_archive_store(hass, create=True)
    return await async_restore_from_file(hass, store, archive_store, data, actor=actor)

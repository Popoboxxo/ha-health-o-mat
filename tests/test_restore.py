"""Tests: Restore-Engine (M2c) — Planung, Merge/Replace, Dry-Run, Apply.

Die Planungslogik ist HA-frei testbar; Apply nutzt einen Fake-Hass mit
gemocktem Store-Backend. Es werden keine echten Dateien außerhalb von
``tmp_path`` berührt.
"""

from __future__ import annotations

import asyncio
import copy
import importlib.util
import json
import os
import sys
import types
import uuid
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

_COMPONENT_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "custom_components", "health_o_mat")
)

_PKG = "_hom_restore_test_pkg"
_pkg = types.ModuleType(_PKG)
_pkg.__path__ = [_COMPONENT_DIR]
sys.modules.setdefault(_PKG, _pkg)


def _load(name: str):
    spec = importlib.util.spec_from_file_location(
        f"{_PKG}.{name}", os.path.join(_COMPONENT_DIR, f"{name}.py")
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[f"{_PKG}.{name}"] = module
    spec.loader.exec_module(module)
    return module


for _name in ("const", "entity", "store", "backup", "importer", "restore"):
    _load(_name)

const_module = sys.modules[f"{_PKG}.const"]
store_module = sys.modules[f"{_PKG}.store"]
backup_module = sys.modules[f"{_PKG}.backup"]
restore = sys.modules[f"{_PKG}.restore"]
_DOMAIN = const_module.DOMAIN


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _fresh_store(entries: dict | None = None):
    store = store_module.HealthOMatStore(MagicMock())
    store._store = MagicMock()
    store._store.async_load = AsyncMock(return_value=None)
    store._store.async_save = AsyncMock(return_value=None)
    _run(store.async_load())
    if entries is not None:
        _run(store.async_set_entries(copy.deepcopy(entries)))
    return store


def _drink(ts: str, ml: int, type_: str = "Wasser", **extra) -> dict:
    record = {
        "id": str(uuid.uuid4()),
        "ts": ts,
        "ml": ml,
        "type": type_,
        "src": "button",
        "created_at": ts,
        "voided_at": None,
        "voided_by": None,
        "void_reason": None,
    }
    record.update(extra)
    return record


def _reading(ts: str, sys_: int, dia: int, **extra) -> dict:
    record = {
        "id": str(uuid.uuid4()),
        "ts": ts,
        "sys": sys_,
        "dia": dia,
        "pulse": 60,
        "note": "",
        "src": "button",
        "created_at": ts,
        "voided_at": None,
        "voided_by": None,
        "void_reason": None,
    }
    record.update(extra)
    return record


def _wellbeing(ts: str, key: str, **extra) -> dict:
    record = {
        "id": str(uuid.uuid4()),
        "ts": ts,
        "key": key,
        "created_at": ts,
        "voided_at": None,
        "voided_by": None,
        "void_reason": None,
    }
    record.update(extra)
    return record


def _entry(person: str, *, drinks=None, readings=None, wellbeing=None, total=0, audit=None):
    return {
        "person": person,
        "drinks": copy.deepcopy(drinks or []),
        "readings": copy.deepcopy(readings or []),
        "wellbeing_entries": copy.deepcopy(wellbeing or []),
        "audit_log": copy.deepcopy(audit or []),
        "total_ml_lifetime": total,
        "inputs": {},
        "archived_counts": {"drinks": 0, "readings": 0},
    }


def _doc(entries: dict, *, version: int = 2, schema: int = 4, archive: dict | None = None):
    document = {
        "format": backup_module.BACKUP_FORMAT,
        "version": version,
        "schema": schema,
        "created": "2026-10-14T12:00:00",
        "persons": {key: value.get("person", "") for key, value in entries.items()},
        "counts": {},
        "entries": copy.deepcopy(entries),
    }
    if version >= 2:
        document["archive_entries"] = copy.deepcopy(archive or {})
        document["archive_schema"] = 4
        document["archive_counts"] = {}
    return document


def _hass(tmp_path: Path, store, archive_store=None):
    hass = MagicMock()
    hass.config.config_dir = str(tmp_path)
    hass.config.path = MagicMock(side_effect=lambda *parts: os.path.join(str(tmp_path), *parts))
    hass.async_add_executor_job = AsyncMock(side_effect=lambda fn, *args: fn(*args))
    hass.services.async_call = AsyncMock()
    hass.data = {_DOMAIN: {"shared": {"store": store}}}
    if archive_store is not None:
        hass.data[_DOMAIN]["shared"]["archive_store"] = archive_store
    hass.config_entries.async_get_entry = MagicMock(return_value=None)
    return hass


def _write_import_file(tmp_path: Path, document: dict, name: str = "backup.json") -> str:
    folder = tmp_path / "health_o_mat_import"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / name).write_text(json.dumps(document), encoding="utf-8")
    return name


def _now(monkeypatch):
    fixed = types.SimpleNamespace(now=lambda: datetime(2026, 10, 25, 12, 0, 0))
    monkeypatch.setattr(restore, "dt_util", fixed)
    monkeypatch.setattr(backup_module, "dt_util", fixed)


# ============================================================================
# Parse / Validate
# ============================================================================


def test_parse_v1_migrates_entries_to_v4():
    """[M2c] v1-Backup wird über die Store-Migrationskette auf v4 normalisiert."""
    document = {
        "format": backup_module.BACKUP_FORMAT,
        "version": 1,
        "created": "2026-01-01T00:00:00",
        "entries": {
            "src": {
                "person": "Max",
                "drinks": [{"ts": "2026-01-01T08:00:00", "ml": 250, "type": "Kaffee"}],
                "wellbeing": {"status": "good", "ts": "2026-01-01T09:00:00"},
                "wellbeing_history": [],
                "total_ml_lifetime": 250,
            }
        },
    }

    parsed = restore.parse_backup_document(document)

    assert parsed["version"] == 1
    assert parsed["schema"] == const_module.STORE_SCHEMA_VERSION
    entry = parsed["entries"]["src"]
    assert entry["drinks"][0]["id"]
    assert entry["drinks"][0]["created_at"] == "2026-01-01T08:00:00"
    assert entry["drinks"][0]["voided_at"] is None
    assert entry["wellbeing_entries"][0]["key"] == "good"
    assert entry["audit_log"] == []
    assert parsed["archive_entries"] == {}


def test_parse_v2_keeps_archive():
    """[M2c] v2-Backup behält Archiv-Einträge."""
    document = _doc(
        {"src": _entry("Max")},
        archive={"src": {"drinks": [_drink("2025-01-01T08:00:00", 500)], "readings": []}},
    )

    parsed = restore.parse_backup_document(document)

    assert parsed["entries"]["src"]["person"] == "Max"
    assert parsed["archive_entries"]["src"]["drinks"][0]["ml"] == 500


@pytest.mark.parametrize(
    ("document", "fragment"),
    [
        ({"format": "other", "version": 2, "entries": {}}, "Format"),
        ({"format": backup_module.BACKUP_FORMAT, "version": 99, "entries": {}}, "Version 99"),
        ({"format": backup_module.BACKUP_FORMAT, "version": 2, "entries": []}, "entries"),
        (
            {"format": backup_module.BACKUP_FORMAT, "version": 2, "entries": {"e": 1}},
            "kein Objekt",
        ),
        (
            {
                "format": backup_module.BACKUP_FORMAT,
                "version": 2,
                "schema": 99,
                "entries": {},
            },
            "Schema",
        ),
        ({"format": backup_module.BACKUP_FORMAT, "entries": {}}, "Version"),
    ],
)
def test_validate_rejects_invalid_documents(document, fragment):
    """[M2c] Format/Version/Entries/Schema werden klar geprüft."""
    error = restore.validate_backup(document)
    assert error and fragment in error
    with pytest.raises(restore.RestoreError):
        restore.parse_backup_document(document)


# ============================================================================
# Mapping
# ============================================================================


def _current_entries(*entries):
    return {entry_id: entry for entry_id, entry in ((item[0], item[1]) for item in entries)}


def test_mapping_by_slug_case_insensitive():
    """[M2c] Ohne person_map wird eindeutig über den Slug (case-insensitive) gemappt."""
    backup = _doc({"src": _entry("Max", drinks=[_drink("2026-10-14T08:00:00", 250)])})
    current = _current_entries(("target", _entry("max")))

    plan = restore.plan_restore(backup, current)

    assert plan.errors == []
    assert plan.persons["src"] == "target"
    assert plan.persons["Max"] == "target"


def test_mapping_person_map_accepts_slug_and_source_id():
    """[M2c] person_map darf Source-Slug oder Source-Entry-ID als Schlüssel nutzen."""
    backup = _doc(
        {
            "src-a": _entry("Max"),
            "src-b": _entry("Caro"),
        }
    )
    current = _current_entries(("t1", _entry("Ziel A")), ("t2", _entry("Ziel B")))

    plan = restore.plan_restore(backup, current, person_map={"Max": "t1", "src-b": "t2"})

    assert plan.errors == []
    assert plan.persons["src-a"] == "t1"
    assert plan.persons["src-b"] == "t2"


def test_mapping_missing_person_is_an_error():
    """[M2c] Keine automatische Neuanlage: unbekannte Person → Fehler."""
    backup = _doc({"src": _entry("Max")})
    current = _current_entries(("target", _entry("Caro")))

    plan = restore.plan_restore(backup, current)

    assert plan.errors
    assert "person_map" in plan.errors[0]


def test_mapping_ambiguous_slug_is_an_error():
    """[M2c] Mehrere Ziel-Personen mit gleichem Slug → Fehler statt Raten."""
    backup = _doc({"src": _entry("Max")})
    current = _current_entries(("t1", _entry("Max")), ("t2", _entry("max")))

    plan = restore.plan_restore(backup, current)

    assert plan.errors
    assert "mehrdeutig" in plan.errors[0]


def test_person_filter_accepts_source_slug_source_id_and_target_id():
    """[M2c] persons-Filter akzeptiert Quelle-Slug, Quelle-ID und Ziel-ID."""
    backup = _doc(
        {
            "src-a": _entry("Max"),
            "src-b": _entry("Caro"),
        }
    )
    current = _current_entries(("t1", _entry("Max")), ("t2", _entry("Caro")))

    by_slug = restore.plan_restore(backup, current, persons=["max"])
    by_source = restore.plan_restore(backup, current, persons=["src-b"])
    by_target = restore.plan_restore(backup, current, persons=["t1"])

    assert set(by_slug.persons.values()) == {"t1"}
    assert set(by_source.persons.values()) == {"t2"}
    assert set(by_target.persons.values()) == {"t1"}


# ============================================================================
# Filter
# ============================================================================


def test_dataset_filter_limits_changes():
    """[M2c] datasets-Filter verändert nur die gewählten Listen."""
    backup = _doc(
        {
            "src": _entry(
                "Max",
                drinks=[_drink("2026-10-14T08:00:00", 250)],
                readings=[_reading("2026-10-14T09:00:00", 120, 80)],
                wellbeing=[_wellbeing("2026-10-14T10:00:00", "good")],
            )
        }
    )
    current = _current_entries(("t1", _entry("Max")))

    plan = restore.plan_restore(backup, current, datasets=["blood_pressure"])

    target = plan.target_entries["t1"]
    assert target["drinks"] == []
    assert len(target["readings"]) == 1
    assert target["wellbeing_entries"] == []
    assert set(plan.counts["t1"]) == {"blood_pressure"}


def test_time_filter_is_inclusive_on_ts():
    """[M2c] from/to filtern inklusiv auf ts (nicht created_at)."""
    backup = _doc(
        {
            "src": _entry(
                "Max",
                drinks=[
                    _drink("2026-10-01T00:00:00", 100),
                    _drink("2026-10-15T00:00:00", 200),
                    _drink("2026-10-31T23:59:59", 300),
                    _drink("2026-11-01T00:00:00", 400),
                ],
            )
        }
    )
    current = _current_entries(("t1", _entry("Max")))

    plan = restore.plan_restore(
        backup,
        current,
        from_ts="2026-10-15T00:00:00",
        to_ts="2026-10-31T23:59:59",
    )

    assert [item["ml"] for item in plan.target_entries["t1"]["drinks"]] == [200, 300]


def test_invalid_time_range_raises():
    """[M2c] from > to bzw. kaputte ISO-Werte werden abgelehnt."""
    backup = _doc({"src": _entry("Max")})
    current = _current_entries(("t1", _entry("Max")))

    with pytest.raises(restore.RestoreError):
        restore.plan_restore(
            backup, current, from_ts="2026-10-20T00:00:00", to_ts="2026-10-10T00:00:00"
        )
    with pytest.raises(restore.RestoreError):
        restore.plan_restore(backup, current, from_ts="kein-datum")


# ============================================================================
# Merge
# ============================================================================


def test_merge_skips_duplicates_including_voided():
    """[M2c] Duplikate werden auch gegen voided Bestand erkannt (kein Auferstehen)."""
    existing = _drink("2026-10-14T08:00:00", 250, "Wasser", voided_at="2026-10-14T09:00:00")
    backup = _doc({"src": _entry("Max", drinks=[_drink("2026-10-14T08:00:00", 250, "Wasser")])})
    current = _current_entries(("t1", _entry("Max", drinks=[existing])))

    plan = restore.plan_restore(backup, current)

    assert plan.counts["t1"]["drinks"]["skipped"] == 1
    assert plan.counts["t1"]["drinks"]["added"] == 0
    assert len(plan.target_entries["t1"]["drinks"]) == 1


def test_merge_id_collision_assigns_new_uuid():
    """[M2c] Vorhandene Backup-ID im Ziel → neue UUID, Konflikt gezählt."""
    shared_id = "11111111-1111-1111-1111-111111111111"
    backup = _doc(
        {"src": _entry("Max", drinks=[_drink("2026-10-14T08:00:00", 250, "Wasser", id=shared_id)])}
    )
    current = _current_entries(
        (
            "t1",
            _entry("Max", drinks=[_reading("2026-10-13T08:00:00", 120, 80, id=shared_id)]),
        )
    )

    plan = restore.plan_restore(backup, current)

    assert plan.counts["t1"]["drinks"]["conflicts"] == 1
    new_drink = plan.target_entries["t1"]["drinks"][-1]
    assert new_drink["id"] != shared_id


def test_merge_lifetime_adds_only_active_imported_ml():
    """[M2c] Merge addiert nur aktive neu importierte Getränke zum Lebenszähler."""
    backup = _doc(
        {
            "src": _entry(
                "Max",
                drinks=[
                    _drink("2026-10-14T08:00:00", 250),
                    _drink("2026-10-14T09:00:00", 500, voided_at="2026-10-14T10:00:00"),
                ],
            )
        }
    )
    current = _current_entries(("t1", _entry("Max", total=1000)))

    plan = restore.plan_restore(backup, current)

    assert plan.target_entries["t1"]["total_ml_lifetime"] == 1250
    assert plan.target_entries["t1"]["drinks"][1]["voided_at"] is not None


def test_merge_rebuilds_wellbeing_mirrors():
    """[M2c] Wellbeing-Spiegel werden über die Store-Logik neu gebaut."""
    backup = _doc(
        {
            "src": _entry(
                "Max",
                wellbeing=[
                    _wellbeing("2026-10-14T08:00:00", "bad"),
                    _wellbeing("2026-10-14T09:00:00", "good"),
                ],
            )
        }
    )
    current = _current_entries(("t1", _entry("Max")))

    plan = restore.plan_restore(backup, current)

    entry = plan.target_entries["t1"]
    assert entry["wellbeing"]["status"] == "good"
    assert entry["wellbeing_history"] == [{"ts": "2026-10-14T08:00:00", "status": "bad"}]


# ============================================================================
# Replace
# ============================================================================


def test_replace_full_person_uses_backup_lifetime():
    """[M2c] Replace im Gesamt-Personen-Scope setzt den Backup-Lebenszähler."""
    backup = _doc(
        {
            "src": _entry(
                "Max",
                drinks=[_drink("2026-10-14T08:00:00", 250)],
                total=250,
            )
        }
    )
    current = _current_entries(
        ("t1", _entry("Max", drinks=[_drink("2026-10-13T08:00:00", 900)], total=900))
    )

    plan = restore.plan_restore(backup, current, mode="replace")

    entry = plan.target_entries["t1"]
    assert [item["ml"] for item in entry["drinks"]] == [250]
    assert entry["total_ml_lifetime"] == 250
    assert plan.counts["t1"]["drinks"]["added"] == 1


def test_replace_dataset_keeps_other_datasets():
    """[M2c] Replace eines Datensatzes lässt die übrigen unangetastet."""
    backup = _doc(
        {
            "src": _entry(
                "Max",
                drinks=[_drink("2026-10-14T08:00:00", 250)],
                readings=[_reading("2026-10-14T09:00:00", 120, 80)],
            )
        }
    )
    current_readings = [_reading("2026-10-13T09:00:00", 130, 85)]
    current = _current_entries(("t1", _entry("Max", readings=current_readings)))

    plan = restore.plan_restore(backup, current, mode="replace", datasets=["drinks"])

    entry = plan.target_entries["t1"]
    assert entry["readings"] == current_readings
    assert entry["total_ml_lifetime"] == 250


def test_replace_time_range_only_replaces_window():
    """[M2c] Replace mit from/to ersetzt nur Einträge im Zeitraum; Lifetime per Delta."""
    old_inside = _drink("2026-10-15T08:00:00", 300)
    old_outside = _drink("2026-10-01T08:00:00", 400)
    backup = _doc(
        {
            "src": _entry(
                "Max",
                drinks=[_drink("2026-10-15T09:00:00", 250)],
                total=250,
            )
        }
    )
    current = _current_entries(("t1", _entry("Max", drinks=[old_inside, old_outside], total=700)))

    plan = restore.plan_restore(
        backup,
        current,
        mode="replace",
        from_ts="2026-10-15T00:00:00",
        to_ts="2026-10-15T23:59:59",
    )

    entry = plan.target_entries["t1"]
    assert [item["ml"] for item in entry["drinks"]] == [400, 250]
    assert entry["total_ml_lifetime"] == 650


def test_replace_never_negative_lifetime():
    """[M2c] Lifetime wird bei Teil-Replace nie negativ."""
    backup = _doc({"src": _entry("Max", drinks=[])})
    current = _current_entries(
        (
            "t1",
            _entry("Max", drinks=[_drink("2026-10-15T08:00:00", 300)], total=100),
        )
    )

    plan = restore.plan_restore(
        backup,
        current,
        mode="replace",
        from_ts="2026-10-15T00:00:00",
        to_ts="2026-10-15T23:59:59",
    )

    assert plan.target_entries["t1"]["total_ml_lifetime"] == 0


# ============================================================================
# Archiv
# ============================================================================


def test_merge_imports_archive_and_adds_lifetime():
    """[M2c] Merge übernimmt Archiv-Einträge und zählt aktive ml zum Lifetime."""
    backup = _doc(
        {"src": _entry("Max", drinks=[_drink("2026-10-14T08:00:00", 250)])},
        archive={"src": {"drinks": [_drink("2025-01-01T08:00:00", 500)], "readings": []}},
    )
    current = _current_entries(("t1", _entry("Max", total=0)))

    plan = restore.plan_restore(backup, current, current_archive_entries={})

    assert plan.target_archive_entries["t1"]["drinks"][0]["ml"] == 500
    assert plan.target_entries["t1"]["total_ml_lifetime"] == 750


def test_replace_clears_archive_in_scope():
    """[M2c] Replace leert auch den Archiv-Scope und setzt Backup-Archiv neu."""
    backup = _doc(
        {"src": _entry("Max")},
        archive={"src": {"drinks": [_drink("2025-01-01T08:00:00", 500)], "readings": []}},
    )
    current = _current_entries(("t1", _entry("Max")))
    archive_current = {
        "t1": {
            "drinks": [_drink("2024-01-01T08:00:00", 300)],
            "readings": [],
        }
    }

    plan = restore.plan_restore(
        backup,
        current,
        mode="replace",
        current_archive_entries=archive_current,
    )

    assert plan.target_archive_entries["t1"]["drinks"][0]["ml"] == 500
    assert plan.target_entries["t1"]["total_ml_lifetime"] == 0


# ============================================================================
# Apply
# ============================================================================


def _apply_setup(tmp_path, monkeypatch, current_entries, archive_entries=None):
    _now(monkeypatch)
    store = _fresh_store(current_entries)
    archive = _fresh_store(archive_entries) if archive_entries is not None else None
    hass = _hass(tmp_path, store, archive)
    return hass, store, archive


def test_apply_dry_run_writes_nothing(tmp_path, monkeypatch):
    """[M2c] Dry-Run liefert den Plan, schreibt aber nichts."""
    hass, store, _archive = _apply_setup(tmp_path, monkeypatch, {"t1": _entry("Max")})
    filename = _write_import_file(
        tmp_path,
        _doc({"src": _entry("Max", drinks=[_drink("2026-10-14T08:00:00", 250)])}),
    )
    store._store.async_save.reset_mock()

    result = _run(
        restore.async_restore_from_file(hass, store, None, {"filename": filename, "dry_run": True})
    )

    assert result["dry_run"] is True
    assert result["applied"] is False
    assert result["backup_path"] is None
    assert result["plan"]["totals"]["added"] == 1
    store._store.async_save.assert_not_awaited()
    assert store.entry("t1")["drinks"] == []
    assert not list(tmp_path.glob("health_o_mat_export/*.json"))


def test_apply_writes_pre_restore_backup_and_audit_event(tmp_path, monkeypatch):
    """[M2c] Echter Restore schreibt Pre-Backup und ein restore_backup-Audit-Event."""
    hass, store, _archive = _apply_setup(tmp_path, monkeypatch, {"t1": _entry("Max")})
    filename = _write_import_file(
        tmp_path,
        _doc({"src": _entry("Max", drinks=[_drink("2026-10-14T08:00:00", 250)])}),
    )
    store._store.async_save.reset_mock()

    result = _run(
        restore.async_restore_from_file(hass, store, None, {"filename": filename}, actor="user-1")
    )

    assert result["applied"] is True
    store._store.async_save.assert_awaited_once()
    assert result["backup_path"] and os.path.isfile(result["backup_path"])
    pre = json.loads(Path(result["backup_path"]).read_text(encoding="utf-8"))
    assert pre["format"] == backup_module.BACKUP_FORMAT
    entry = store.entry("t1")
    assert entry["drinks"][0]["ml"] == 250
    assert entry["audit_log"][-1]["action"] == "restore_backup"
    assert entry["audit_log"][-1]["actor"] == "user-1"
    assert entry["audit_log"][-1]["details"]["mode"] == "merge"


def test_apply_does_not_copy_audit_by_default(tmp_path, monkeypatch):
    """[M2c] Fremdes Audit-Log wird standardmäßig nicht übernommen."""
    foreign = {
        "id": "audit-from-backup",
        "ts": "2020-01-01T00:00:00",
        "action": "drink_added",
        "kind": "drinks",
        "target_id": None,
        "actor": None,
        "details": {},
    }
    hass, store, _archive = _apply_setup(tmp_path, monkeypatch, {"t1": _entry("Max")})
    filename = _write_import_file(
        tmp_path,
        _doc(
            {
                "src": _entry(
                    "Max",
                    drinks=[_drink("2026-10-14T08:00:00", 250)],
                    audit=[foreign],
                )
            }
        ),
    )

    _run(restore.async_restore_from_file(hass, store, None, {"filename": filename}))

    ids = [event["id"] for event in store.entry("t1")["audit_log"]]
    assert "audit-from-backup" not in ids


def test_apply_can_import_audit_when_explicitly_requested(tmp_path, monkeypatch):
    """[M2c] restore_audit=True importiert Audit-Ereignisse dedupliziert über id."""
    foreign = {
        "id": "audit-from-backup",
        "ts": "2020-01-01T00:00:00",
        "action": "drink_added",
        "kind": "drinks",
        "target_id": None,
        "actor": None,
        "details": {},
    }
    hass, store, _archive = _apply_setup(tmp_path, monkeypatch, {"t1": _entry("Max")})
    filename = _write_import_file(
        tmp_path,
        _doc(
            {
                "src": _entry(
                    "Max",
                    drinks=[_drink("2026-10-14T08:00:00", 250)],
                    audit=[foreign, dict(foreign)],
                )
            }
        ),
    )

    _run(
        restore.async_restore_from_file(
            hass, store, None, {"filename": filename, "restore_audit": True}
        )
    )

    events = store.entry("t1")["audit_log"]
    assert [event["id"] for event in events].count("audit-from-backup") == 1
    assert events[-1]["action"] == "restore_backup"


def test_apply_replace_requires_confirm(tmp_path, monkeypatch):
    """[M2c] Replace ohne/mit falscher Bestätigung wird abgelehnt (Service-Pfad)."""
    hass, store, _archive = _apply_setup(tmp_path, monkeypatch, {"t1": _entry("Max")})
    filename = _write_import_file(tmp_path, _doc({"src": _entry("Max")}))
    store._store.async_save.reset_mock()

    for confirm in (None, "RESTORE", "replace"):
        data = {"filename": filename, "mode": "replace"}
        if confirm is not None:
            data["confirm"] = confirm
        with pytest.raises(restore.RestoreError):
            _run(restore.async_restore_from_file(hass, store, None, data))
    store._store.async_save.assert_not_awaited()


def test_apply_rolls_back_in_memory_on_save_failure(tmp_path, monkeypatch):
    """[M2c] Save-Fehler → In-Memory-Bestand unverändert."""
    hass, store, _archive = _apply_setup(tmp_path, monkeypatch, {"t1": _entry("Max")})
    before = copy.deepcopy(store.entry("t1"))
    store._store.async_save = AsyncMock(side_effect=RuntimeError("disk full"))
    filename = _write_import_file(
        tmp_path,
        _doc({"src": _entry("Max", drinks=[_drink("2026-10-14T08:00:00", 250)])}),
    )

    with pytest.raises(restore.RestoreError):
        _run(restore.async_restore_from_file(hass, store, None, {"filename": filename}))

    assert store.entry("t1") == before


def test_apply_v1_backup_end_to_end(tmp_path, monkeypatch):
    """[M2c] v1-Backup wird normalisiert und erfolgreich eingespielt."""
    hass, store, _archive = _apply_setup(tmp_path, monkeypatch, {"t1": _entry("Max")})
    filename = _write_import_file(
        tmp_path,
        {
            "format": backup_module.BACKUP_FORMAT,
            "version": 1,
            "created": "2026-01-01T00:00:00",
            "entries": {
                "src": {
                    "person": "Max",
                    "drinks": [{"ts": "2026-01-01T08:00:00", "ml": 250, "type": "Kaffee"}],
                    "total_ml_lifetime": 250,
                }
            },
        },
    )

    result = _run(restore.async_restore_from_file(hass, store, None, {"filename": filename}))

    assert result["applied"] is True
    entry = store.entry("t1")
    assert entry["drinks"][0]["ml"] == 250
    assert entry["drinks"][0]["id"]
    assert entry["total_ml_lifetime"] == 250


def test_safe_import_path_rejects_traversal(tmp_path, monkeypatch):
    """[M2c] Restore liest nur aus dem Import-Ordner (kein Traversal)."""
    hass, store, _archive = _apply_setup(tmp_path, monkeypatch, {"t1": _entry("Max")})

    with pytest.raises(restore.RestoreError):
        _run(restore.async_restore_from_file(hass, store, None, {"filename": "../evil.json"}))


def test_apply_archive_replace_is_persisted(tmp_path, monkeypatch):
    """[M2c] Archiv-Store wird beim Replace mitgeschrieben."""
    hass, store, archive = _apply_setup(
        tmp_path,
        monkeypatch,
        {"t1": _entry("Max")},
        {"t1": {"drinks": [_drink("2024-01-01T08:00:00", 300)], "readings": []}},
    )
    filename = _write_import_file(
        tmp_path,
        _doc(
            {"src": _entry("Max")},
            archive={"src": {"drinks": [_drink("2025-01-01T08:00:00", 500)], "readings": []}},
        ),
    )

    _run(
        restore.async_restore_from_file(
            hass,
            store,
            archive,
            {"filename": filename, "mode": "replace", "confirm": "REPLACE"},
        )
    )

    assert archive.entry("t1")["drinks"][0]["ml"] == 500


def test_merge_does_not_duplicate_across_main_and_archive():
    """[M2c] Ein im Haupt-Store vorhandener Eintrag wird nicht ins Archiv dupliziert."""
    record = _drink("2026-10-14T08:00:00", 250, "Wasser")
    backup = _doc(
        {"src": _entry("Max", drinks=[record])},
        archive={"src": {"drinks": [record], "readings": []}},
    )
    current = _current_entries(("t1", _entry("Max", drinks=[record])))

    plan = restore.plan_restore(backup, current, current_archive_entries={})

    assert plan.counts["t1"]["drinks"]["added"] == 0
    assert plan.counts["t1"]["drinks"]["skipped"] == 2
    assert plan.target_archive_entries["t1"]["drinks"] == []


def test_replace_with_explicit_all_datasets_is_full_scope():
    """[M2c] Explizit alle Datensätze zählen als Gesamt-Personen-Scope."""
    backup = _doc(
        {
            "src": _entry(
                "Max",
                drinks=[_drink("2026-10-14T08:00:00", 250)],
                total=250,
            )
        }
    )
    current = _current_entries(
        ("t1", _entry("Max", drinks=[_drink("2026-10-13T08:00:00", 900)], total=900))
    )

    plan = restore.plan_restore(
        backup,
        current,
        mode="replace",
        datasets=["drinks", "blood_pressure", "wellbeing"],
    )

    assert plan.target_entries["t1"]["total_ml_lifetime"] == 250


def test_replace_reuses_backup_ids_after_clearing_scope():
    """[M2c] Replace übernimmt Backup-IDs, wenn der alte Eintrag im Scope entfernt wird."""
    record_id = "22222222-2222-2222-2222-222222222222"
    backup = _doc({"src": _entry("Max", drinks=[_drink("2026-10-15T08:00:00", 250, id=record_id)])})
    current = _current_entries(
        (
            "t1",
            _entry(
                "Max",
                drinks=[_drink("2026-10-15T07:00:00", 250, id=record_id)],
                total=250,
            ),
        )
    )

    plan = restore.plan_restore(
        backup,
        current,
        mode="replace",
        from_ts="2026-10-15T00:00:00",
        to_ts="2026-10-15T23:59:59",
    )

    assert plan.counts["t1"]["drinks"]["conflicts"] == 0
    assert plan.target_entries["t1"]["drinks"][0]["id"] == record_id


def test_parse_v2_without_schema_treats_entries_as_legacy():
    """[M2c] Fehlende Schema-Markierung wird als Altbestand migriert."""
    document = {
        "format": backup_module.BACKUP_FORMAT,
        "version": 2,
        "created": "2026-01-01T00:00:00",
        "entries": {
            "src": {
                "person": "Max",
                "wellbeing": {"status": "good", "ts": "2026-01-01T09:00:00"},
                "wellbeing_history": [],
            }
        },
    }

    parsed = restore.parse_backup_document(document)

    assert parsed["schema"] == const_module.STORE_SCHEMA_VERSION
    assert parsed["entries"]["src"]["wellbeing_entries"][0]["key"] == "good"

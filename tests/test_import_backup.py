"""Tests: CSV-Import (REQ-HOM-007) + JSON-Backup (REQ-HOM-007/§4.5).

Isoliert über ``importlib`` (wie ``test_wave_a.py``): die HA-freien Teile
(``safe_import_path``, ``parse_csv_text``, ``plan_import``,
``build_backup_document``, ``backup_filename``) laufen ohne Home Assistant.
Der Service-Layer (Datei-I/O, Store, Notification) wird mit einem Fake-Hass
geprüft.
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import os
import sys
import types
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
import voluptuous as vol

_COMPONENT_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "custom_components", "health_o_mat")
)

# Eigenes Fake-Paket (Kollisionsfreiheit zu anderen Testmodulen).
_PKG = "_hom_import_test_pkg"
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


def _load_init():
    """__init__.py mit Fake-Modulen laden (Service-Wiring)."""
    for name in ("store", "entity", "const", "parser", "logic", "exporter"):
        _load(name)
    spec = importlib.util.spec_from_file_location(
        f"{_PKG}.init", os.path.join(_COMPONENT_DIR, "__init__.py")
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[f"{_PKG}.init"] = module
    spec.loader.exec_module(module)
    return module


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


const_module = _load("const")
logic_module = _load("logic")
entity_module = _load("entity")
store_module = _load("store")
importer = _load("importer")
backup = _load("backup")

_DOMAIN = const_module.DOMAIN


class _FakeServices:
    """Minimal-Service-Registry zum Einsammeln der registrierten Handler."""

    def __init__(self) -> None:
        self.registered: dict[str, tuple] = {}

    def has_service(self, domain, name) -> bool:
        return name in self.registered

    def async_register(self, domain, name, *, schema=None, service_func=None) -> None:
        self.registered[name] = (schema, service_func)

    async def async_call(self, *args, **kwargs) -> None:
        return None


def _call(data: dict | None = None) -> MagicMock:
    call = MagicMock()
    call.data = data or {}
    return call


def _fresh_store():
    """HealthOMatStore mit gemocktem HA-Store-Backend (leerer Start)."""
    store = store_module.HealthOMatStore(MagicMock())
    store._store = MagicMock()
    store._store.async_load = AsyncMock(return_value=None)
    store._store.async_save = AsyncMock(return_value=None)
    _run(store.async_load())
    return store


def _import_hass(config_dir: Path, entry_id: str = "e1") -> MagicMock:
    hass = MagicMock()
    hass.config.config_dir = str(config_dir)
    hass.async_add_executor_job = AsyncMock(side_effect=lambda fn: fn())
    hass.services.async_call = AsyncMock()
    hass.data = {_DOMAIN: {"shared": {}, entry_id: {"coordinator": MagicMock()}}}
    return hass


def _drinks_csv() -> str:
    rows = logic_module.drinks_csv_rows(
        [
            {"ts": "2026-10-14T08:30:00", "ml": 250, "type": "Kaffee", "src": "quick_button"},
            {"ts": "2026-10-14T12:00:00", "ml": 500, "type": "Wasser", "src": "service"},
        ],
        "Max",
    )
    return logic_module.rows_to_csv_string(rows)


def _import_dir(config_dir: Path) -> Path:
    folder = config_dir / importer.IMPORT_DIR_NAME
    folder.mkdir(parents=True, exist_ok=True)
    return folder


# ============================================================================
# safe_import_path — Pfad-Whitelist (Datenschutzregel)
# ============================================================================


def test_safe_import_path_accepts_basename(tmp_path):
    """[REQ-HOM-007] Basisname → Pfad unter <config>/health_o_mat_import/."""
    _import_dir(tmp_path)

    path = importer.safe_import_path(str(tmp_path), "drinks.csv")

    expected = os.path.realpath(os.path.join(str(tmp_path), importer.IMPORT_DIR_NAME, "drinks.csv"))
    assert path == expected


def test_safe_import_path_rejects_absolute(tmp_path):
    """[REQ-HOM-007] Absolute Pfade werden abgelehnt."""
    with pytest.raises(ValueError):
        importer.safe_import_path(str(tmp_path), "/etc/passwd")


def test_safe_import_path_rejects_www(tmp_path):
    """[REQ-HOM-007] /config/www ist tabu (Datenschutzregel)."""
    with pytest.raises(ValueError):
        importer.safe_import_path(str(tmp_path), "/config/www/leak.csv")


def test_safe_import_path_rejects_windows_drive(tmp_path):
    """[REQ-HOM-007] Windows-Laufwerkspfade werden abgelehnt."""
    with pytest.raises(ValueError):
        importer.safe_import_path(str(tmp_path), "C:/secrets.csv")


def test_safe_import_path_rejects_traversal(tmp_path):
    """[REQ-HOM-007] Traversal (..) verlässt den Import-Ordner → abgelehnt."""
    _import_dir(tmp_path)

    with pytest.raises(ValueError):
        importer.safe_import_path(str(tmp_path), "../secrets.csv")


def test_safe_import_path_rejects_empty(tmp_path):
    """[REQ-HOM-007] Leerer Dateiname → ValueError."""
    with pytest.raises(ValueError):
        importer.safe_import_path(str(tmp_path), "   ")


def test_safe_import_path_rejects_symlink_escape(tmp_path):
    """[REQ-HOM-007] Symlink aus dem Import-Ordner heraus → abgelehnt."""
    folder = _import_dir(tmp_path)
    outside = tmp_path / "outside.csv"
    outside.write_text("x", encoding="utf-8")
    link = folder / "link.csv"
    try:
        link.symlink_to(outside)
    except (OSError, NotImplementedError):
        pytest.skip("Symlinks auf diesem System nicht verfügbar")

    with pytest.raises(ValueError):
        importer.safe_import_path(str(tmp_path), "link.csv")


# ============================================================================
# plan_import — Toleranz, Duplikat-Schutz, Zähler
# ============================================================================


def test_plan_import_roundtrip_drinks():
    """[REQ-HOM-007] Export-Format → Import: alle Getränke übernommen."""
    plan = importer.plan_import(_drinks_csv(), "all", [], [])

    assert plan.imported == 2
    assert plan.skipped == 0
    assert plan.rejected == 0
    assert {d["ts"] for d in plan.drinks} == {"2026-10-14T08:30:00", "2026-10-14T12:00:00"}
    assert {d["ml"] for d in plan.drinks} == {250, 500}
    assert {d["type"] for d in plan.drinks} == {"Kaffee", "Wasser"}
    assert {d["src"] for d in plan.drinks} == {"quick_button", "service"}


def test_plan_import_tolerates_bom_and_missing_header():
    """[REQ-HOM-007] BOM + fehlender Header werden toleriert."""
    text = "\ufeff2026-10-14;08:30:00;Max;Kaffee;250;button\n2026-10-14;09:00:00;Max;Tee;300;\n"

    plan = importer.plan_import(text, "all", [], [])

    assert plan.imported == 2
    assert plan.rejected == 0


def test_plan_import_counts_rejected_rows():
    """[REQ-HOM-007] Unlesbare Zeilen zählen als rejected (mit Fehlertext)."""
    text = (
        "datum;uhrzeit;person;getraenk;menge_ml;quelle\n"
        "?;?;Max;Kaffee;250;\n"
        "2026-10-14;08:00:00;Max;Tee;abc;\n"
        "2026-10-14;09:00:00;Max;Wasser;250;\n"
    )

    plan = importer.plan_import(text, "drinks", [], [])

    assert plan.imported == 1
    assert plan.rejected == 2
    assert len(plan.errors) == 2


def test_plan_import_skips_existing_duplicates():
    """[REQ-HOM-007] Bereits vorhandene Getränke (ts+ml) werden übersprungen."""
    existing = [{"ts": "2026-10-14T08:30:00", "ml": 250, "type": "Kaffee", "src": ""}]

    plan = importer.plan_import(_drinks_csv(), "drinks", existing, [])

    assert plan.skipped == 1
    assert plan.imported == 1
    assert {d["ml"] for d in plan.drinks} == {500}


def test_plan_import_skips_duplicates_within_file():
    """[REQ-HOM-007] Doppelte Zeilen innerhalb der Datei zählen als skipped."""
    text = (
        "datum;uhrzeit;person;getraenk;menge_ml;quelle\n"
        "2026-10-14;08:00:00;Max;Wasser;250;\n"
        "2026-10-14;08:00:00;Max;Wasser;250;\n"
    )

    plan = importer.plan_import(text, "drinks", [], [])

    assert plan.imported == 1
    assert plan.skipped == 1


def test_plan_import_blood_pressure_autodetect():
    """[REQ-HOM-007] BP-Format wird am Header erkannt (all)."""
    text = (
        "zeitstempel;person;systolisch;diastolisch;puls;notiz\n"
        "2026-10-14T08:00:00;Max;120;80;60;morgens\n"
        "2026-10-14T20:00:00;Max;130;85;;\n"
    )

    plan = importer.plan_import(text, "all", [], [])

    assert plan.imported == 2
    assert plan.rejected == 0
    assert plan.readings[0]["pulse"] == 60
    assert plan.readings[0]["note"] == "morgens"
    assert plan.readings[1]["pulse"] is None


def test_plan_import_blood_pressure_dedup():
    """[REQ-HOM-007] BP-Duplikate werden über (ts, sys, dia) erkannt."""
    text = (
        "zeitstempel;person;systolisch;diastolisch;puls;notiz\n2026-10-14T08:00:00;Max;120;80;60;\n"
    )
    existing = [
        {
            "ts": "2026-10-14T08:00:00",
            "sys": 120,
            "dia": 80,
            "pulse": 60,
            "note": "",
            "src": "button",
        }
    ]

    plan = importer.plan_import(text, "blood_pressure", [], existing)

    assert plan.imported == 0
    assert plan.skipped == 1


def test_plan_import_auto_without_header_is_drinks():
    """[REQ-HOM-007] Headerlos + Datum in Spalte 1 → Getränke."""
    text = "2026-10-14;08:00:00;Max;Wasser;250;\n"

    plan = importer.plan_import(text, "all", [], [])

    assert plan.imported == 1
    assert plan.drinks[0]["type"] == "Wasser"


# ============================================================================
# async_import_csv — Service (Datei-I/O, Store, Notification)
# ============================================================================


def test_async_import_csv_reads_file_and_notifies(tmp_path):
    """[REQ-HOM-007] Service liest, speichert und benachrichtigt."""
    folder = _import_dir(tmp_path)
    (folder / "drinks.csv").write_text(_drinks_csv(), encoding="utf-8")
    store = _fresh_store()
    hass = _import_hass(tmp_path)

    result = _run(
        importer.async_import_csv(
            hass, store, "e1", _call({"filename": "drinks.csv", "dataset": "all"})
        )
    )

    assert result["imported"] == 2
    assert result["skipped"] == 0
    assert result["rejected"] == 0
    assert len(store.entry("e1")["drinks"]) == 2
    assert store.entry("e1")["total_ml_lifetime"] == 750
    hass.services.async_call.assert_called_once()
    assert hass.services.async_call.call_args[0][0] == "persistent_notification"


def test_async_import_csv_second_run_skips_duplicates(tmp_path):
    """[REQ-HOM-007] Zweiter Import derselben Datei legt nichts doppelt an."""
    folder = _import_dir(tmp_path)
    (folder / "drinks.csv").write_text(_drinks_csv(), encoding="utf-8")
    store = _fresh_store()
    hass = _import_hass(tmp_path)
    call = _call({"filename": "drinks.csv", "dataset": "drinks"})

    _run(importer.async_import_csv(hass, store, "e1", call))
    second = _run(importer.async_import_csv(hass, store, "e1", call))

    assert len(store.entry("e1")["drinks"]) == 2
    assert second["imported"] == 0
    assert second["skipped"] == 2


def test_async_import_csv_rejects_path_outside_import_dir(tmp_path):
    """[REQ-HOM-007] Pfad außerhalb des Import-Ordners → ServiceValidationError."""
    store = _fresh_store()
    hass = _import_hass(tmp_path)

    with pytest.raises(importer.ServiceValidationError):
        _run(
            importer.async_import_csv(
                hass, store, "e1", _call({"filename": "../evil.csv", "dataset": "all"})
            )
        )


def test_async_import_csv_missing_file_raises(tmp_path):
    """[REQ-HOM-007] Fehlende Datei → ServiceValidationError."""
    _import_dir(tmp_path)
    store = _fresh_store()
    hass = _import_hass(tmp_path)

    with pytest.raises(importer.ServiceValidationError):
        _run(
            importer.async_import_csv(
                hass, store, "e1", _call({"filename": "nope.csv", "dataset": "all"})
            )
        )


# ============================================================================
# Backup — Dokument, Dateiname, Service
# ============================================================================


def test_build_backup_document_shape():
    """[REQ-HOM-007] Backup-Dokument ist versioniert und enthält alle Einträge."""
    raw = {"schema": 4, "entries": {"e1": {"person": "Max", "drinks": [{"ml": 250}]}}}

    document = backup.build_backup_document(raw, datetime(2026, 10, 14, 12, 0, 0))

    assert document["format"] == backup.BACKUP_FORMAT
    assert document["version"] == backup.BACKUP_VERSION == 3
    assert document["schema"] == 4
    assert document["created"] == "2026-10-14T12:00:00"
    assert document["persons"] == {"e1": "Max"}
    assert document["counts"] == {
        "e1": {
            "drinks": {"total": 1, "active": 1, "voided": 0},
            "readings": {"total": 0, "active": 0, "voided": 0},
            "wellbeing": {"total": 0, "active": 0, "voided": 0},
            "lab_readings": {"total": 0, "active": 0, "voided": 0},
        }
    }
    assert document["entries"] == raw["entries"]


def test_build_backup_document_counts_voided_separately():
    """[REQ-HOM-007] counts weist gelöschte (voided) Einträge separat aus."""
    raw = {
        "schema": 4,
        "entries": {
            "e1": {
                "person": "Max",
                "drinks": [{"ml": 250}, {"ml": 500, "voided_at": "2026-10-14T10:00:00"}],
                "readings": [
                    {"sys": 120, "dia": 80},
                    {"sys": 130, "dia": 85, "voided_at": "2026-10-14T11:00:00"},
                ],
                "wellbeing_entries": [
                    {"key": "good"},
                    {"key": "bad", "voided_at": "2026-10-14T12:00:00"},
                ],
            }
        },
    }

    document = backup.build_backup_document(raw, datetime(2026, 10, 14))

    assert document["counts"]["e1"] == {
        "drinks": {"total": 2, "active": 1, "voided": 1},
        "readings": {"total": 2, "active": 1, "voided": 1},
        "wellbeing": {"total": 2, "active": 1, "voided": 1},
        "lab_readings": {"total": 0, "active": 0, "voided": 0},
    }


def test_build_backup_document_legacy_wellbeing_counts():
    """[REQ-HOM-007] Vor-v4-Bestände: Wellbeing aus Legacy-Spiegel gezählt."""
    raw = {
        "entries": {
            "e1": {
                "person": "Max",
                "wellbeing": {"status": "good", "ts": "2026-10-14T10:00:00"},
                "wellbeing_history": [{"ts": "2026-10-13T10:00:00", "status": "bad"}],
            }
        }
    }

    document = backup.build_backup_document(raw, datetime(2026, 10, 14))

    assert document["schema"] is None
    assert document["counts"]["e1"]["wellbeing"] == {
        "total": 2,
        "active": 2,
        "voided": 0,
    }


def test_build_backup_document_is_deep_copy():
    """[REQ-HOM-007] Das Dokument teilt keine Referenzen mit dem Store."""
    raw = {"entries": {"e1": {"drinks": [{"ml": 250}]}}}

    document = backup.build_backup_document(raw, datetime(2026, 10, 14))
    document["entries"]["e1"]["drinks"][0]["ml"] = 999

    assert raw["entries"]["e1"]["drinks"][0]["ml"] == 250


def test_backup_filename_has_timestamp():
    """[REQ-HOM-007] Backup-Dateiname trägt einen Zeitstempel."""
    name = backup.backup_filename(datetime(2026, 10, 14, 12, 34, 56))

    assert name == "health_o_mat_backup_20261014-123456.json"


def test_async_backup_writes_all_persons(tmp_path, monkeypatch):
    """[REQ-HOM-007] Backup schreibt alle Personen/Datensätze als JSON."""
    store = _fresh_store()
    _run(store.set_person("e1", "Max"))
    _run(store.set_person("e2", "Caro"))
    _run(store.add_drink("e1", "2026-10-14T08:00:00", 250, "Kaffee", "import"))
    _run(store.add_reading("e2", "2026-10-14T09:00:00", 120, 80, 60))
    hass = MagicMock()
    hass.config.path = MagicMock(return_value=str(tmp_path))
    hass.async_add_executor_job = AsyncMock(side_effect=lambda fn: fn())
    hass.services.async_call = AsyncMock()
    monkeypatch.setattr(
        backup, "dt_util", types.SimpleNamespace(now=lambda: datetime(2026, 10, 14, 12, 0, 0))
    )

    path = _run(backup.async_backup(hass, store))

    document = json.loads(Path(path).read_text(encoding="utf-8"))
    assert document["format"] == backup.BACKUP_FORMAT
    assert document["version"] == 3
    assert document["schema"] == const_module.STORE_SCHEMA_VERSION
    assert document["lab_options"] == {}
    assert set(document["entries"]) == {"e1", "e2"}
    assert document["persons"] == {"e1": "Max", "e2": "Caro"}
    assert document["counts"]["e1"]["drinks"] == {"total": 1, "active": 1, "voided": 0}
    assert document["entries"]["e1"]["drinks"][0]["ml"] == 250
    assert document["entries"]["e2"]["readings"][0]["sys"] == 120
    # v4-Felder sind im Backup vollständig enthalten
    assert document["entries"]["e1"]["drinks"][0]["voided_at"] is None
    assert document["entries"]["e1"]["audit_log"]
    assert "wellbeing_entries" in document["entries"]["e1"]
    hass.services.async_call.assert_called_once()
    assert hass.services.async_call.call_args[0][0] == "persistent_notification"


def test_backup_writes_into_private_export_dir(tmp_path, monkeypatch):
    """[REQ-HOM-007] Backup landet in health_o_mat_export, nie in /www."""
    store = _fresh_store()
    hass = MagicMock()
    hass.config.path = MagicMock(return_value=str(tmp_path / "health_o_mat_export"))
    hass.async_add_executor_job = AsyncMock(side_effect=lambda fn: fn())
    hass.services.async_call = AsyncMock()
    monkeypatch.setattr(
        backup, "dt_util", types.SimpleNamespace(now=lambda: datetime(2026, 10, 14, 12, 0, 0))
    )

    path = _run(backup.async_backup(hass, store))

    assert "health_o_mat_export" in path
    assert os.path.isfile(path)


# ============================================================================
# Service-Wiring (__init__._register_services)
# ============================================================================


def test_services_registered_with_schemas():
    """[REQ-HOM-007] import_csv + backup sind registriert und validieren."""
    init = _load_init()
    hass = MagicMock()
    hass.services = _FakeServices()

    init._register_services(hass)

    assert "import_csv" in hass.services.registered
    assert "backup" in hass.services.registered

    schema, _func = hass.services.registered["import_csv"]
    validated = schema({"filename": "drinks.csv"})
    assert validated["dataset"] == "all"
    with pytest.raises(vol.Invalid):
        schema({})  # filename ist Pflicht


def test_import_csv_service_writes_via_runtime_data(tmp_path):
    """[REQ-HOM-007] Registrierter Handler löst Person auf und importiert."""
    init = _load_init()
    folder = _import_dir(tmp_path)
    (folder / "drinks.csv").write_text(_drinks_csv(), encoding="utf-8")
    store = _fresh_store()
    hass = _import_hass(tmp_path)
    hass.data[_DOMAIN]["shared"]["store"] = store
    hass.config.config_dir = str(tmp_path)
    hass.services = _FakeServices()
    hass.config_entries = MagicMock()
    entry = MagicMock()
    entry.entry_id = "e1"
    entry.data = {"person": "Max"}
    hass.config_entries.async_entries = MagicMock(return_value=[entry])
    init._register_services(hass)

    _schema, func = hass.services.registered["import_csv"]
    _run(func(_call({"filename": "drinks.csv", "dataset": "all", "person": "Max"})))

    assert len(store.entry("e1")["drinks"]) == 2


# ============================================================================
# M2a: voided Einträge in Export/Import/Backup
# ============================================================================


def test_export_csv_excludes_voided_entries(tmp_path):
    """[M2a] CSV-Export enthält nur aktive Drinks/Readings (voided fehlt)."""
    _load_init()  # lädt u. a. das exporter-Modul
    exporter = importlib.import_module(f"{_PKG}.init.exporter")
    store = _fresh_store()
    _run(store.set_person("e1", "Max"))
    _run(store.add_drink("e1", "2026-10-14T08:00:00", 250, "Wasser", "button"))
    _run(store.add_drink("e1", "2026-10-14T09:00:00", 500, "Kaffee", "button"))
    _run(store.void_drink("e1", store.entry("e1")["drinks"][1]["id"]))
    _run(store.add_reading("e1", "2026-10-14T09:00:00", 120, 80, 60, "aktiv"))
    _run(store.add_reading("e1", "2026-10-14T10:00:00", 200, 120, 99, "voided-notiz"))
    _run(store.void_reading("e1", store.entry("e1")["readings"][1]["id"]))

    hass = MagicMock()
    hass.config.path = MagicMock(return_value=str(tmp_path))
    hass.async_add_executor_job = AsyncMock(side_effect=lambda fn: fn())
    hass.services.async_call = AsyncMock()
    exporter.dt_util = types.SimpleNamespace(now=lambda: datetime(2026, 10, 14, 12, 0))

    _run(exporter.async_export_csv(hass, store, _call({"dataset": "all"})))

    drinks_csv = next(tmp_path.glob("health_o_mat_drinks_*.csv")).read_text(encoding="utf-8-sig")
    bp_csv = next(tmp_path.glob("health_o_mat_bloodpressure_*.csv")).read_text(encoding="utf-8-sig")

    assert "Wasser" in drinks_csv
    assert "Kaffee" not in drinks_csv
    assert "250" in drinks_csv
    assert "500" not in drinks_csv

    assert "120;80;60" in bp_csv
    assert "voided-notiz" not in bp_csv
    assert ";200;" not in bp_csv


def test_export_csv_excludes_voided_entries_from_archive(tmp_path):
    """[M2a] Auch Archiv-Einträge werden nur aktiv exportiert (defensiv)."""
    _load_init()
    exporter = importlib.import_module(f"{_PKG}.init.exporter")
    store = _fresh_store()
    _run(store.set_person("e1", "Max"))
    _run(store.add_drink("e1", "2026-10-14T08:00:00", 250, "Wasser", "button"))
    archive = _fresh_store()
    _run(
        archive.append_archive(
            "e1",
            [
                {"ts": "2025-12-31T10:00:00", "ml": 300, "type": "Saft", "src": "button"},
                {
                    "ts": "2025-12-30T10:00:00",
                    "ml": 700,
                    "type": "Kaffee",
                    "src": "button",
                    "voided_at": "2026-01-01T00:00:00",
                },
            ],
            [],
        )
    )

    hass = MagicMock()
    hass.config.path = MagicMock(return_value=str(tmp_path))
    hass.async_add_executor_job = AsyncMock(side_effect=lambda fn: fn())
    hass.services.async_call = AsyncMock()
    exporter.dt_util = types.SimpleNamespace(now=lambda: datetime(2026, 10, 14, 12, 0))

    _run(
        exporter.async_export_csv(hass, store, _call({"dataset": "drinks"}), archive_store=archive)
    )

    content = next(tmp_path.glob("health_o_mat_drinks_*.csv")).read_text(encoding="utf-8-sig")
    assert "Wasser" in content
    assert "Saft" in content
    assert "Kaffee" not in content
    assert "700" not in content


def test_async_import_csv_skips_voided_duplicates(tmp_path):
    """[M2a] Re-Import lässt einen bewusst gelöschten Eintrag nicht auferstehen."""
    folder = _import_dir(tmp_path)
    (folder / "drinks.csv").write_text(_drinks_csv(), encoding="utf-8")
    store = _fresh_store()
    hass = _import_hass(tmp_path)
    call = _call({"filename": "drinks.csv", "dataset": "drinks"})

    _run(importer.async_import_csv(hass, store, "e1", call))
    for drink in list(store.entry("e1")["drinks"]):
        _run(store.void_drink("e1", drink["id"]))

    second = _run(importer.async_import_csv(hass, store, "e1", call))

    assert second["imported"] == 0
    assert second["skipped"] == 2
    assert len(store.entry("e1")["drinks"]) == 2
    assert all(drink["voided_at"] for drink in store.entry("e1")["drinks"])


def test_backup_contains_voided_entries_and_audit(tmp_path, monkeypatch):
    """[M2a] Backup bleibt roh: voided Einträge + Audit-Log sind enthalten."""
    store = _fresh_store()
    _run(store.set_person("e1", "Max"))
    _run(store.add_drink("e1", "2026-10-14T08:00:00", 250, "Kaffee", "button"))
    _run(store.void_drink("e1", store.entry("e1")["drinks"][0]["id"]))

    hass = MagicMock()
    hass.config.path = MagicMock(return_value=str(tmp_path))
    hass.async_add_executor_job = AsyncMock(side_effect=lambda fn: fn())
    hass.services.async_call = AsyncMock()
    monkeypatch.setattr(
        backup, "dt_util", types.SimpleNamespace(now=lambda: datetime(2026, 10, 14, 12, 0, 0))
    )

    path = _run(backup.async_backup(hass, store))

    document = json.loads(Path(path).read_text(encoding="utf-8"))
    entry = document["entries"]["e1"]
    assert len(entry["drinks"]) == 1
    assert entry["drinks"][0]["voided_at"] is not None
    assert [event["action"] for event in entry["audit_log"]] == [
        "drink_added",
        "entry_voided",
    ]
    assert document["counts"]["e1"]["drinks"] == {"total": 1, "active": 0, "voided": 1}


# ============================================================================
# Backup v2 — Archiv-Store (M2c)
# ============================================================================


def test_build_backup_document_includes_archive_additively():
    """[M2c] v2-Backup nimmt den Archiv-Store additiv mit auf."""
    raw = {"schema": 4, "entries": {"e1": {"person": "Max", "drinks": []}}}
    archive = {
        "schema": 4,
        "entries": {
            "e1": {
                "drinks": [{"ml": 500, "voided_at": None}],
                "readings": [{"sys": 120, "dia": 80, "voided_at": None}],
            }
        },
    }

    document = backup.build_backup_document(raw, datetime(2026, 10, 14), archive)

    assert document["archive_schema"] == 4
    assert document["archive_entries"]["e1"]["drinks"][0]["ml"] == 500
    assert document["archive_entries"]["e1"]["readings"][0]["sys"] == 120
    assert document["archive_counts"]["e1"]["drinks"] == {
        "total": 1,
        "active": 1,
        "voided": 0,
    }
    # Hauptbestand bleibt unverändert enthalten (keine Regression).
    assert document["entries"]["e1"]["person"] == "Max"


def test_build_backup_document_without_archive_is_empty():
    """[M2c] Ohne Archiv bleiben die Archivfelder leer (abwärtskompatibel)."""
    document = backup.build_backup_document({"schema": 4, "entries": {}}, datetime(2026, 10, 14))

    assert document["archive_entries"] == {}
    assert document["archive_schema"] is None
    assert document["archive_counts"] == {}


def test_async_backup_includes_archive_store(tmp_path, monkeypatch):
    """[M2c] async_backup schreibt Archiv-Einträge in dasselbe Dokument."""
    store = _fresh_store()
    archive = _fresh_store()
    _run(store.set_person("e1", "Max"))
    _run(store.add_drink("e1", "2026-10-14T08:00:00", 250, "Kaffee", "button"))
    _run(archive.append_archive("e1", [{"ml": 500, "ts": "2025-01-01T08:00:00"}], []))
    hass = MagicMock()
    hass.config.path = MagicMock(return_value=str(tmp_path))
    hass.async_add_executor_job = AsyncMock(side_effect=lambda fn: fn())
    hass.services.async_call = AsyncMock()
    monkeypatch.setattr(
        backup, "dt_util", types.SimpleNamespace(now=lambda: datetime(2026, 10, 14, 12, 0, 0))
    )

    path = _run(backup.async_backup(hass, store, archive))

    document = json.loads(Path(path).read_text(encoding="utf-8"))
    assert document["archive_schema"] == const_module.STORE_SCHEMA_VERSION
    assert document["archive_entries"]["e1"]["drinks"][0]["ml"] == 500


def test_backup_service_passes_archive_store():
    """[M2c] Der Backup-Service übergibt den vorhandenen Archiv-Store."""
    init = _load_init()
    store = _fresh_store()
    archive = _fresh_store()
    hass = _import_hass(Path("/tmp"))
    hass.data[_DOMAIN]["shared"]["store"] = store
    hass.data[_DOMAIN]["shared"]["archive_store"] = archive
    hass.services = _FakeServices()
    init._register_services(hass)
    _schema, func = hass.services.registered["backup"]
    calls = []

    async def _fake_backup(hass_, store_, archive_=None):
        calls.append((store_, archive_))
        return "/tmp/x.json"

    original = backup.async_backup
    lazy_backup = importlib.import_module(f"{_PKG}.init.backup")
    lazy_backup.async_backup = _fake_backup
    try:
        call = _call({})
        call.context.user_id = None  # Automation/Skript → Admin-Gate lässt durch
        _run(func(call))
    finally:
        lazy_backup.async_backup = original

    assert calls == [(store, archive)]


def _on_demand_archive(tmp_path, monkeypatch, init, archive):
    """Shared ohne archive_store; Archiv-Datei existiert → Laden on demand."""
    store_mod = importlib.import_module(f"{_PKG}.init.store")
    monkeypatch.setattr(store_mod, "HealthOMatStore", lambda hass_, storage_key=None: archive)
    storage_dir = tmp_path / ".storage"
    storage_dir.mkdir(exist_ok=True)
    (storage_dir / const_module.ARCHIVE_STORE_KEY).write_text("{}", encoding="utf-8")
    hass = _import_hass(tmp_path)
    hass.config.path = MagicMock(side_effect=lambda *parts: os.path.join(str(tmp_path), *parts))
    hass.async_add_executor_job = AsyncMock(side_effect=lambda fn, *args: fn(*args))
    hass.services = _FakeServices()
    init._register_services(hass)
    return hass


def test_backup_service_loads_archive_on_demand(tmp_path, monkeypatch):
    """[B-2] Fehlender Shared-Store wird bei vorhandener Archiv-Datei nachgeladen."""
    init = _load_init()
    store = _fresh_store()
    _run(store.set_person("e1", "Max"))
    archive = _fresh_store()
    _run(archive.append_archive("e1", [{"ml": 500, "ts": "2025-01-01T08:00:00"}], []))
    # On-demand-Laden darf den vorhandenen Archiv-Inhalt nicht verlieren.
    archive._store.async_load = AsyncMock(return_value=archive.raw_data())
    hass = _on_demand_archive(tmp_path, monkeypatch, init, archive)
    hass.data[_DOMAIN]["shared"]["store"] = store
    backup_mod = importlib.import_module(f"{_PKG}.init.backup")
    monkeypatch.setattr(
        backup_mod,
        "dt_util",
        types.SimpleNamespace(now=lambda: datetime(2026, 10, 14, 12, 0, 0)),
    )
    _schema, func = hass.services.registered["backup"]

    call = _call({})
    call.context.user_id = None
    _run(func(call))

    assert hass.data[_DOMAIN]["shared"]["archive_store"] is archive
    path = next((tmp_path / "health_o_mat_export").glob("health_o_mat_backup_*.json"))
    document = json.loads(path.read_text(encoding="utf-8"))
    assert document["archive_entries"]["e1"]["drinks"][0]["ml"] == 500


def test_export_csv_service_loads_archive_on_demand(tmp_path, monkeypatch):
    """[B-2] CSV-Export enthält das on-demand geladene Archiv."""
    init = _load_init()
    exporter = importlib.import_module(f"{_PKG}.init.exporter")
    store = _fresh_store()
    _run(store.set_person("e1", "Max"))
    _run(store.add_drink("e1", "2026-10-14T08:00:00", 250, "Wasser", "button"))
    archive = _fresh_store()
    _run(
        archive.append_archive(
            "e1", [{"ts": "2025-01-01T08:00:00", "ml": 500, "type": "Saft", "src": "button"}], []
        )
    )
    # On-demand-Laden darf den vorhandenen Archiv-Inhalt nicht verlieren.
    archive._store.async_load = AsyncMock(return_value=archive.raw_data())
    hass = _on_demand_archive(tmp_path, monkeypatch, init, archive)
    hass.data[_DOMAIN]["shared"]["store"] = store
    monkeypatch.setattr(
        exporter, "dt_util", types.SimpleNamespace(now=lambda: datetime(2026, 10, 14, 12, 0))
    )
    _schema, func = hass.services.registered["export_csv"]

    call = _call({"dataset": "drinks"})
    call.context.user_id = None
    _run(func(call))

    assert hass.data[_DOMAIN]["shared"]["archive_store"] is archive
    content = next((tmp_path / "health_o_mat_export").glob("health_o_mat_drinks_*.csv")).read_text(
        encoding="utf-8-sig"
    )
    assert "Wasser" in content
    assert "Saft" in content


# ============================================================================
# Review-Fix S-11: Backup-/Pre-Restore-Dateien im Restore-Pfad
# ============================================================================


def test_list_import_files_includes_export_dir_json_only(tmp_path):
    """[S-11] Export-Ordner (Backups/Pre-Restore) ist in der Restore-Liste sichtbar."""
    import_dir = tmp_path / importer.IMPORT_DIR_NAME
    export_dir = tmp_path / "health_o_mat_export"
    import_dir.mkdir()
    export_dir.mkdir()
    (import_dir / "manual.json").write_text("{}", encoding="utf-8")
    (export_dir / "health_o_mat_backup_1.json").write_text("{}", encoding="utf-8")
    (export_dir / "health_o_mat_pre_restore_1.json").write_text("{}", encoding="utf-8")
    (export_dir / "drinks_export.csv").write_text("a;b", encoding="utf-8")
    (export_dir / ".hidden.json").write_text("{}", encoding="utf-8")

    files = importer.list_import_files(str(tmp_path))

    assert files == [
        "health_o_mat_backup_1.json",
        "health_o_mat_pre_restore_1.json",
        "manual.json",
    ]


def test_safe_restore_path_accepts_import_and_export(tmp_path):
    """[S-11] Whitelist erlaubt nur JSON in Import-/Export-Ordner."""
    (tmp_path / importer.IMPORT_DIR_NAME).mkdir()
    export_dir = tmp_path / "health_o_mat_export"
    export_dir.mkdir()
    created = export_dir / "backup.json"
    created.write_text("{}", encoding="utf-8")

    path = importer.safe_restore_path(str(tmp_path), "backup.json")

    assert os.path.realpath(path) == os.path.realpath(created)


@pytest.mark.parametrize(
    "filename",
    ["/etc/passwd", "../secret.json", "unterordner/backup.json", "backup.csv", "   "],
)
def test_safe_restore_path_rejects_invalid_names(tmp_path, filename):
    """[S-11] Absolute Pfade, Traversal, Unterordner und Nicht-JSON sind tabu."""
    with pytest.raises(ValueError):
        importer.safe_restore_path(str(tmp_path), filename)


def test_safe_restore_path_rejects_symlink(tmp_path):
    """[S-11] Symlinks werden auch im Export-Ordner abgelehnt."""
    export_dir = tmp_path / "health_o_mat_export"
    export_dir.mkdir()
    outside = tmp_path / "aussen.json"
    outside.write_text("{}", encoding="utf-8")
    link = export_dir / "link.json"
    try:
        link.symlink_to(outside)
    except (OSError, NotImplementedError):
        pytest.skip("Symlinks auf diesem System nicht verfügbar")

    with pytest.raises(ValueError):
        importer.safe_restore_path(str(tmp_path), "link.json")


# ============================================================================
# REQ-HOM-122 — Laborwerte + Lab-Optionen im Backup-Dokument (v3)
# ============================================================================


def test_req_hom_122_backup_document_includes_lab_readings_counts():
    """[REQ-HOM-122] counts weist Laborwerte wie die übrigen Datensätze aus."""
    raw_data = {
        "schema": 5,
        "entries": {
            "e1": {
                "person": "Caro",
                "drinks": [],
                "readings": [],
                "wellbeing_entries": [],
                "lab_readings": [
                    {"marker_key": "alt", "value": 32.0, "voided_at": None},
                    {"marker_key": "ast", "value": 20.0, "voided_at": "2026-10-30T00:00:00"},
                ],
            }
        },
    }

    doc = backup.build_backup_document(raw_data, datetime(2026, 10, 31))

    assert doc["counts"]["e1"]["lab_readings"] == {"total": 2, "active": 1, "voided": 1}
    # Die übrigen Zähler bleiben unverändert (additive Erweiterung).
    assert doc["counts"]["e1"]["drinks"] == {"total": 0, "active": 0, "voided": 0}


def test_req_hom_122_backup_document_includes_lab_options():
    """[REQ-HOM-122] Lab-Optionen (aus entry.options) landen top-level im Dokument."""
    raw_data = {"schema": 5, "entries": {"e1": {"drinks": [], "readings": []}}}
    lab_options = {
        "e1": {
            "lab_custom_markers": [
                {"key": "vitamin_d", "name": "Vitamin D", "category": "other", "unit": "ng/mL"}
            ],
            "lab_ref_overrides": {"alt": {"ref_min": 5}},
            "lab_hidden_categories": ["thyroid"],
        }
    }

    doc = backup.build_backup_document(raw_data, datetime(2026, 10, 31), lab_options=lab_options)

    assert doc["lab_options"] == lab_options


def test_req_hom_122_backup_document_lab_options_default_empty():
    """[REQ-HOM-122] Ohne lab_options bleibt das Feld leer (abwärtskompatibel)."""
    doc = backup.build_backup_document({"schema": 5, "entries": {}}, datetime(2026, 10, 31))

    assert doc["lab_options"] == {}


def test_req_hom_122_backup_document_lab_options_is_deep_copy():
    """[REQ-HOM-122] lab_options wird tief kopiert (kein Store-/Options-Alias)."""
    lab_options = {"e1": {"lab_custom_markers": [{"key": "vitamin_d"}]}}

    doc = backup.build_backup_document(
        {"schema": 5, "entries": {}}, datetime(2026, 10, 31), lab_options=lab_options
    )
    doc["lab_options"]["e1"]["lab_custom_markers"][0]["key"] = "changed"

    assert lab_options["e1"]["lab_custom_markers"][0]["key"] == "vitamin_d"


def test_req_hom_122_backup_version_bumped_to_3():
    """[REQ-HOM-122] Backup-Format ist Version 3."""
    assert backup.BACKUP_VERSION == 3


def test_req_hom_122_async_backup_collects_lab_options_from_entries(tmp_path, monkeypatch):
    """[REQ-HOM-122] async_backup liest die Lab-Optionen je Config-Entry."""
    store = _fresh_store()
    _run(store.set_person("e1", "Max"))
    hass = MagicMock()
    hass.config.path = MagicMock(return_value=str(tmp_path))
    hass.async_add_executor_job = AsyncMock(side_effect=lambda fn: fn())
    hass.services.async_call = AsyncMock()
    configured = MagicMock()
    configured.entry_id = "e1"
    configured.options = {
        const_module.OPTION_LAB_CUSTOM_MARKERS: [{"key": "vitamin_d"}],
        const_module.OPTION_LAB_REF_OVERRIDES: {"alt": {"ref_min": 5}},
        const_module.OPTION_LAB_HIDDEN_CATEGORIES: ["thyroid"],
    }
    bare = MagicMock()
    bare.entry_id = "e2"
    bare.options = {}
    hass.config_entries = MagicMock()
    hass.config_entries.async_entries = MagicMock(return_value=[configured, bare])
    monkeypatch.setattr(
        backup, "dt_util", types.SimpleNamespace(now=lambda: datetime(2026, 10, 14, 12, 0, 0))
    )

    path = _run(backup.async_backup(hass, store))

    document = json.loads(Path(path).read_text(encoding="utf-8"))
    assert document["lab_options"] == {
        "e1": {
            "lab_custom_markers": [{"key": "vitamin_d"}],
            "lab_ref_overrides": {"alt": {"ref_min": 5}},
            "lab_hidden_categories": ["thyroid"],
        },
        "e2": {
            "lab_custom_markers": [],
            "lab_ref_overrides": {},
            "lab_hidden_categories": [],
        },
    }


# ============================================================================
# REQ-HOM-122 — Labwerte im CSV-Export (Task 24)
# ============================================================================

_LAB_CSV_HEADER = (
    "zeitstempel;person;marker;kategorie;wert;einheit;"
    "eingegeben_als_wert;eingegeben_als_einheit;berichts_referenz"
)


def test_req_hom_122_export_csv_writes_lab_values_file(tmp_path):
    """[REQ-HOM-122] dataset=lab_values schreibt eine Laborwert-CSV."""
    exporter = _load("exporter")
    store = _fresh_store()
    _run(store.set_person("e1", "Caro"))
    _run(
        store.add_lab_reading(
            "e1",
            "2026-10-31T09:00:00+01:00",
            "alt",
            32.0,
            "U/L",
            32.0,
            "U/L",
            report_ref="https://example.com/x",
        )
    )
    hass = MagicMock()
    hass.config.path = MagicMock(return_value=str(tmp_path))
    hass.async_add_executor_job = AsyncMock(side_effect=lambda fn: fn())
    hass.services.async_call = AsyncMock()

    paths = _run(
        exporter.async_export_csv(hass, store, _call({"person": "", "dataset": "lab_values"}))
    )

    written = list(tmp_path.glob("*lab*"))
    assert written, "no lab_values CSV written"
    content = written[0].read_text(encoding="utf-8-sig")
    assert content.splitlines()[0] == _LAB_CSV_HEADER
    assert "alt" in content
    assert "liver" in content
    assert "32.0" in content
    assert "U/L" in content
    assert "https://example.com/x" in content
    assert paths == str(written[0])


def test_req_hom_122_export_csv_lab_values_only_when_selected(tmp_path):
    """[REQ-HOM-122] Andere Datensätze schreiben keine Laborwert-CSV."""
    exporter = _load("exporter")
    store = _fresh_store()
    _run(store.set_person("e1", "Caro"))
    _run(store.add_lab_reading("e1", "2026-10-31T09:00:00", "alt", 32.0, "U/L", 32.0, "U/L"))
    hass = MagicMock()
    hass.config.path = MagicMock(return_value=str(tmp_path))
    hass.async_add_executor_job = AsyncMock(side_effect=lambda fn: fn())
    hass.services.async_call = AsyncMock()

    _run(exporter.async_export_csv(hass, store, _call({"dataset": "drinks"})))

    assert not list(tmp_path.glob("*lab*"))


def test_req_hom_122_export_csv_all_includes_lab_values_file(tmp_path):
    """[REQ-HOM-122] dataset=all exportiert zusätzlich die Laborwerte."""
    exporter = _load("exporter")
    store = _fresh_store()
    _run(store.set_person("e1", "Caro"))
    _run(store.add_lab_reading("e1", "2026-10-31T09:00:00", "alt", 32.0, "U/L", 32.0, "U/L"))
    hass = MagicMock()
    hass.config.path = MagicMock(return_value=str(tmp_path))
    hass.async_add_executor_job = AsyncMock(side_effect=lambda fn: fn())
    hass.services.async_call = AsyncMock()

    _run(exporter.async_export_csv(hass, store, _call({"dataset": "all"})))

    lab_files = list(tmp_path.glob("*lab*"))
    assert len(lab_files) == 1
    assert lab_files[0].read_text(encoding="utf-8-sig").splitlines()[0] == _LAB_CSV_HEADER


def test_req_hom_122_export_csv_lab_values_uses_custom_marker_category(tmp_path):
    """[REQ-HOM-122] Custom-Marker-Kategorien kommen aus den Entry-Options."""
    exporter = _load("exporter")
    store = _fresh_store()
    _run(store.set_person("e1", "Caro"))
    _run(
        store.add_lab_reading(
            "e1", "2026-10-31T09:00:00", "vitamin_d", 30.0, "ng/mL", 30.0, "ng/mL"
        )
    )
    hass = MagicMock()
    hass.config.path = MagicMock(return_value=str(tmp_path))
    hass.async_add_executor_job = AsyncMock(side_effect=lambda fn: fn())
    hass.services.async_call = AsyncMock()
    custom = {
        "e1": [{"key": "vitamin_d", "name": "Vitamin D", "category": "other", "unit": "ng/mL"}]
    }

    _run(
        exporter.async_export_csv(
            hass,
            store,
            _call({"dataset": "lab_values"}),
            lab_custom_markers_by_entry=custom,
        )
    )

    content = next(tmp_path.glob("*lab*")).read_text(encoding="utf-8-sig")
    assert "vitamin_d;other;30.0;ng/mL" in content


def test_req_hom_122_export_csv_lab_values_reads_custom_markers_from_entries(tmp_path):
    """[REQ-HOM-122] Ohne expliziten Parameter liest der Export entry.options."""
    exporter = _load("exporter")
    store = _fresh_store()
    _run(store.set_person("e1", "Caro"))
    _run(
        store.add_lab_reading(
            "e1", "2026-10-31T09:00:00", "vitamin_d", 30.0, "ng/mL", 30.0, "ng/mL"
        )
    )
    hass = MagicMock()
    hass.config.path = MagicMock(return_value=str(tmp_path))
    hass.async_add_executor_job = AsyncMock(side_effect=lambda fn: fn())
    hass.services.async_call = AsyncMock()
    entry = MagicMock()
    entry.entry_id = "e1"
    entry.options = {
        const_module.OPTION_LAB_CUSTOM_MARKERS: [
            {"key": "vitamin_d", "name": "Vitamin D", "category": "other", "unit": "ng/mL"}
        ]
    }
    hass.config_entries = MagicMock()
    hass.config_entries.async_entries = MagicMock(return_value=[entry])

    _run(exporter.async_export_csv(hass, store, _call({"dataset": "lab_values"})))

    content = next(tmp_path.glob("*lab*")).read_text(encoding="utf-8-sig")
    assert "vitamin_d;other;30.0;ng/mL" in content


# ============================================================================
# REQ-HOM-122 — Labwerte im CSV-Import (Task 25)
# ============================================================================

_LAB_CSV_HEADER_LINE = (
    "zeitstempel;person;marker;kategorie;wert;einheit;"
    "eingegeben_als_wert;eingegeben_als_einheit;berichts_referenz"
)


def test_req_hom_122_parse_lab_row_valid():
    """[REQ-HOM-122] Vollständige Laborwert-Zeile → Record-Dict."""
    record = importer._parse_lab_row(
        ["2026-10-31T09:00:00", "Caro", "alt", "liver", "32.0", "U/L", "32.0", "U/L", ""]
    )

    assert record["ts"] == "2026-10-31T09:00:00"
    assert record["marker_raw"] == "alt"
    assert record["value"] == 32.0
    assert record["unit"] == "U/L"
    assert record["reported_value"] == 32.0
    assert record["reported_unit"] == "U/L"
    assert record["report_ref"] is None


def test_req_hom_122_parse_lab_row_keeps_report_ref():
    """[REQ-HOM-122] Berichts-Referenz bleibt erhalten."""
    record = importer._parse_lab_row(
        ["2026-10-31T09:00:00", "Caro", "alt", "liver", "32.0", "U/L", "32.0", "U/L", "https://x"]
    )

    assert record["report_ref"] == "https://x"


def test_req_hom_122_parse_lab_row_invalid_timestamp_returns_error_string():
    """[REQ-HOM-122] Ungültiger Zeitstempel → Fehlermeldung statt Record."""
    result = importer._parse_lab_row(
        ["not-a-ts", "Caro", "alt", "liver", "32.0", "U/L", "32.0", "U/L", ""]
    )

    assert isinstance(result, str)


def test_req_hom_122_parse_lab_row_invalid_value_returns_error_string():
    """[REQ-HOM-122] Unlesbarer Wert → Fehlermeldung statt Record."""
    result = importer._parse_lab_row(
        ["2026-10-31T09:00:00", "Caro", "alt", "liver", "not-a-number", "U/L", "", "", ""]
    )

    assert isinstance(result, str)


def test_req_hom_122_plan_import_lab_values_happy_path():
    """[REQ-HOM-122] Kopfzeile + Datenzeile → ein geplanter Laborwert."""
    text = f"{_LAB_CSV_HEADER_LINE}\n2026-10-31T09:00:00;Caro;alt;liver;32.0;U/L;32.0;U/L;\n"

    plan = importer.plan_import(text, "lab_values", existing_lab_readings=[], lab_custom_markers=[])

    assert len(plan.lab_readings) == 1
    assert plan.lab_readings[0]["marker_key"] == "alt"
    assert plan.lab_readings[0]["value"] == 32.0
    assert plan.rejected == 0
    assert plan.imported == 1


def test_req_hom_122_plan_import_lab_values_resolves_alias():
    """[REQ-HOM-122] Alias (gpt) wird auf den Katalog-Key (alt) aufgelöst."""
    text = f"{_LAB_CSV_HEADER_LINE}\n2026-10-31T09:00:00;Caro;gpt;liver;32.0;U/L;32.0;U/L;\n"

    plan = importer.plan_import(text, "lab_values", existing_lab_readings=[], lab_custom_markers=[])

    assert plan.lab_readings[0]["marker_key"] == "alt"


def test_req_hom_122_plan_import_lab_values_rejects_unknown_marker_without_auto_create():
    """[REQ-HOM-122] Unbekannter Marker → rejected, nie automatisch angelegt."""
    text = f"{_LAB_CSV_HEADER_LINE}\n2026-10-31T09:00:00;Caro;not_a_marker;other;1;x;1;x;\n"

    plan = importer.plan_import(text, "lab_values", existing_lab_readings=[], lab_custom_markers=[])

    assert plan.lab_readings == []
    assert plan.rejected == 1


def test_req_hom_122_plan_import_lab_values_dedup_by_ts_marker_value():
    """[REQ-HOM-122] Duplikat über (ts, marker_key, value) → skipped."""
    text = f"{_LAB_CSV_HEADER_LINE}\n2026-10-31T09:00:00;Caro;alt;liver;32.0;U/L;32.0;U/L;\n"
    existing = [{"ts": "2026-10-31T09:00:00", "marker_key": "alt", "value": 32.0}]

    plan = importer.plan_import(
        text, "lab_values", existing_lab_readings=existing, lab_custom_markers=[]
    )

    assert plan.lab_readings == []
    assert plan.skipped == 1


def test_req_hom_122_plan_import_lab_values_autodetect_header_in_all_mode():
    """[REQ-HOM-122] dataset=all erkennt die Laborwert-Kopfzeile."""
    text = f"{_LAB_CSV_HEADER_LINE}\n2026-10-31T09:00:00;Caro;alt;liver;32.0;U/L;32.0;U/L;\n"

    plan = importer.plan_import(text, "all", existing_lab_readings=[], lab_custom_markers=[])

    assert len(plan.lab_readings) == 1
    assert plan.rejected == 0


def test_req_hom_122_plan_import_lab_values_resolves_custom_marker():
    """[REQ-HOM-122] Custom-Marker aus den Options werden aufgelöst."""
    text = f"{_LAB_CSV_HEADER_LINE}\n2026-10-31T09:00:00;Caro;vitamin_d;other;30;ng/mL;30;ng/mL;\n"
    custom = [{"key": "vitamin_d", "name": "Vitamin D", "category": "other", "unit": "ng/mL"}]

    plan = importer.plan_import(
        text, "lab_values", existing_lab_readings=[], lab_custom_markers=custom
    )

    assert plan.lab_readings[0]["marker_key"] == "vitamin_d"


def test_req_hom_122_plan_import_lab_values_converts_alt_unit_to_canonical():
    """[REQ-HOM-122] mg/dL wird in den canonical_unit (µmol/L) umgerechnet.

    Spec-Invariante: ``value``/``unit`` sind immer kanonisch, die Rohwerte
    bleiben als ``reported_value``/``reported_unit`` erhalten.
    """
    text = f"{_LAB_CSV_HEADER_LINE}\n2026-10-31T09:00:00;Caro;creatinine;kidney;1.1;mg/dL;;;\n"

    plan = importer.plan_import(text, "lab_values", existing_lab_readings=[], lab_custom_markers=[])

    assert plan.rejected == 0
    record = plan.lab_readings[0]
    assert record["marker_key"] == "creatinine"
    assert record["value"] == 97.24
    assert record["unit"] == "µmol/L"
    assert record["reported_value"] == 1.1
    assert record["reported_unit"] == "mg/dL"


def test_req_hom_122_plan_import_lab_values_rejects_unsupported_unit():
    """[REQ-HOM-122] Unbekannte Einheit → rejected, nie roh persistiert."""
    text = f"{_LAB_CSV_HEADER_LINE}\n2026-10-31T09:00:00;Caro;alt;liver;32.0;furlongs;;;\n"

    plan = importer.plan_import(text, "lab_values", existing_lab_readings=[], lab_custom_markers=[])

    assert plan.lab_readings == []
    assert plan.rejected == 1
    assert "furlongs" in plan.errors[0]


def test_req_hom_122_plan_import_lab_values_empty_unit_falls_back_to_canonical():
    """[REQ-HOM-122/N-4] Leere Einheitsspalte = "keine Angabe" → kanonische Einheit.

    Konsistent zu ``convert_lab_value(unit=None)`` und zum Service
    ``add_lab_value`` (``unit`` optional): eine leere Spalte ist kein Fehler.
    """
    text = f"{_LAB_CSV_HEADER_LINE}\n2026-10-31T09:00:00;Caro;alt;liver;32.0;;32.0;;\n"

    plan = importer.plan_import(text, "lab_values", existing_lab_readings=[], lab_custom_markers=[])

    assert plan.rejected == 0
    assert plan.errors == []
    record = plan.lab_readings[0]
    assert record["marker_key"] == "alt"
    assert record["unit"] == "U/L"
    assert record["value"] == 32.0
    # Ohne gedruckte Einheit gilt die kanonische (nie eine leere Zeichenkette).
    assert record["reported_unit"] == "U/L"


def test_req_hom_122_plan_import_lab_values_empty_unit_rejected_if_required():
    """[REQ-HOM-122/N-4] Marker mit ``require_explicit_unit`` verlangt eine Einheit."""
    marker = "urine_protein_creatinine_ratio"
    text = f"{_LAB_CSV_HEADER_LINE}\n2026-10-31T09:00:00;Caro;{marker};kidney;10;;10;;\n"

    plan = importer.plan_import(text, "lab_values", existing_lab_readings=[], lab_custom_markers=[])

    assert plan.lab_readings == []
    assert plan.rejected == 1
    assert marker in plan.errors[0]
    assert "Einheit erforderlich" in plan.errors[0]


def test_req_hom_122_async_import_csv_writes_lab_readings(tmp_path):
    """[REQ-HOM-122] Service legt Laborwerte über den Store an."""
    folder = _import_dir(tmp_path)
    text = f"{_LAB_CSV_HEADER_LINE}\n2026-10-31T09:00:00;Caro;alt;liver;32.0;U/L;32.0;U/L;\n"
    (folder / "labs.csv").write_text(text, encoding="utf-8")
    store = _fresh_store()
    hass = _import_hass(tmp_path)

    result = _run(
        importer.async_import_csv(
            hass, store, "e1", _call({"filename": "labs.csv", "dataset": "lab_values"})
        )
    )

    assert result["imported"] == 1
    assert result["rejected"] == 0
    labs = store.entry("e1")["lab_readings"]
    assert len(labs) == 1
    assert labs[0]["marker_key"] == "alt"
    assert labs[0]["value"] == 32.0
    assert labs[0]["unit"] == "U/L"
    assert labs[0]["reported_value"] == 32.0
    assert labs[0]["reported_unit"] == "U/L"
    assert labs[0]["report_ref"] is None
    assert labs[0]["voided_at"] is None


def test_req_hom_122_async_import_csv_uses_entry_lab_custom_markers(tmp_path):
    """[REQ-HOM-122] Import liest Custom-Marker aus den Entry-Options."""
    folder = _import_dir(tmp_path)
    text = f"{_LAB_CSV_HEADER_LINE}\n2026-10-31T09:00:00;Caro;vitamin_d;other;30;ng/mL;30;ng/mL;\n"
    (folder / "labs.csv").write_text(text, encoding="utf-8")
    store = _fresh_store()
    hass = _import_hass(tmp_path)
    entry = MagicMock()
    entry.entry_id = "e1"
    entry.options = {
        const_module.OPTION_LAB_CUSTOM_MARKERS: [
            {"key": "vitamin_d", "name": "Vitamin D", "category": "other", "unit": "ng/mL"}
        ]
    }
    hass.config_entries = MagicMock()
    hass.config_entries.async_entries = MagicMock(return_value=[entry])

    result = _run(
        importer.async_import_csv(
            hass, store, "e1", _call({"filename": "labs.csv", "dataset": "lab_values"})
        )
    )

    assert result["imported"] == 1
    assert store.entry("e1")["lab_readings"][0]["marker_key"] == "vitamin_d"


def test_req_hom_122_async_import_csv_stores_canonical_lab_value(tmp_path):
    """[REQ-HOM-122] Service persistiert Laborwerte kanonisch, Rohwert bleibt reported."""
    folder = _import_dir(tmp_path)
    text = f"{_LAB_CSV_HEADER_LINE}\n2026-10-31T09:00:00;Caro;creatinine;kidney;1.1;mg/dL;;;\n"
    (folder / "labs.csv").write_text(text, encoding="utf-8")
    store = _fresh_store()
    hass = _import_hass(tmp_path)

    result = _run(
        importer.async_import_csv(
            hass, store, "e1", _call({"filename": "labs.csv", "dataset": "lab_values"})
        )
    )

    assert result["imported"] == 1
    lab = store.entry("e1")["lab_readings"][0]
    assert lab["value"] == 97.24
    assert lab["unit"] == "µmol/L"
    assert lab["reported_value"] == 1.1
    assert lab["reported_unit"] == "mg/dL"


def test_req_hom_122_async_import_csv_rejects_unsupported_unit_without_write(tmp_path):
    """[REQ-HOM-122] Unbekannte Einheit → rejected, keine Store-Schreibung."""
    folder = _import_dir(tmp_path)
    text = f"{_LAB_CSV_HEADER_LINE}\n2026-10-31T09:00:00;Caro;alt;liver;32.0;furlongs;;;\n"
    (folder / "labs.csv").write_text(text, encoding="utf-8")
    store = _fresh_store()
    hass = _import_hass(tmp_path)

    result = _run(
        importer.async_import_csv(
            hass, store, "e1", _call({"filename": "labs.csv", "dataset": "lab_values"})
        )
    )

    assert result["imported"] == 0
    assert result["rejected"] == 1
    assert result["errors"]
    assert store.entry("e1")["lab_readings"] == []


def test_req_hom_122_lab_export_import_roundtrip_stays_canonical(tmp_path):
    """[REQ-HOM-122] Export → Import: kanonischer Wert bleibt, Rohwert bleibt reported."""
    exporter = _load("exporter")
    store = _fresh_store()
    _run(store.set_person("e1", "Caro"))
    _run(
        store.add_lab_reading(
            "e1", "2026-10-31T09:00:00", "creatinine", 97.24, "µmol/L", 1.1, "mg/dL"
        )
    )
    hass = MagicMock()
    hass.config.path = MagicMock(return_value=str(tmp_path))
    hass.async_add_executor_job = AsyncMock(side_effect=lambda fn: fn())
    hass.services.async_call = AsyncMock()

    _run(exporter.async_export_csv(hass, store, _call({"dataset": "lab_values"})))
    content = next(tmp_path.glob("*lab*")).read_text(encoding="utf-8-sig")

    plan = importer.plan_import(
        content, "lab_values", existing_lab_readings=[], lab_custom_markers=[]
    )

    assert plan.rejected == 0
    record = plan.lab_readings[0]
    assert record["value"] == 97.24
    assert record["unit"] == "µmol/L"
    assert record["reported_value"] == 1.1
    assert record["reported_unit"] == "mg/dL"

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
    assert document["version"] == backup.BACKUP_VERSION == 2
    assert document["schema"] == 4
    assert document["created"] == "2026-10-14T12:00:00"
    assert document["persons"] == {"e1": "Max"}
    assert document["counts"] == {
        "e1": {
            "drinks": {"total": 1, "active": 1, "voided": 0},
            "readings": {"total": 0, "active": 0, "voided": 0},
            "wellbeing": {"total": 0, "active": 0, "voided": 0},
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
    assert document["version"] == 2
    assert document["schema"] == 4
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

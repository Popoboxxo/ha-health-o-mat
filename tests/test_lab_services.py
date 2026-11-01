"""Tests: add_lab_value / remove_last_lab_value service handlers (REQ-HOM-122).

Muster bewusst identisch zu `tests/test_binary_sensor.py`/`test_wave_a.py`:
`__init__.py` wird über ein Fake-Paket geladen, damit die relativen Importe
(`from . import logic`, `from .store import ...`) ohne installiertes
HA-Integration-Paket aufgelöst werden.
"""

import asyncio
import importlib.util
import os
import sys
import types
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
import voluptuous as vol
import yaml
from homeassistant.exceptions import ServiceValidationError

_COMPONENT_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "custom_components", "health_o_mat")
)

# Eigener Paketname: kollidiert nicht mit dem `_hom_test_pkg` anderer Suiten.
_PKG = "_hom_lab_test_pkg"
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
    """__init__.py mit Fake-Modulen laden (analog test_binary_sensor._load_init)."""
    for name in ("store", "entity", "const", "parser", "logic", "exporter", "areas"):
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


def _make_call(data):
    call = MagicMock()
    call.data = data
    call.context = MagicMock()
    call.context.user_id = None
    return call


def _wire_services_and_schemas(hass, store, entry_id="e1", options=None):
    """`_register_services` auf einem MagicMock-Hass ausführen.

    Gibt `({service_name: handler}, {service_name: schema})` zurück. Die
    Handler-Tests rufen den Handler direkt auf; die Schema-Tests validieren
    gegen das tatsächlich registrierte voluptuous-Schema.
    """
    hass.data = {
        hass_init.DOMAIN: {
            "shared": {"store": store},
            entry_id: {"coordinator": MagicMock(), "store": store, "data": MagicMock()},
        }
    }
    entry = MagicMock()
    entry.entry_id = entry_id
    entry.data = {"person": "caro"}
    entry.options = options or {}
    hass.config_entries = MagicMock()
    hass.config_entries.async_entries.return_value = [entry]
    hass.config_entries.async_get_entry.return_value = entry
    registered = {}
    schemas = {}

    def _register(domain, name, schema=None, service_func=None, supports_response=None):
        registered[name] = service_func
        schemas[name] = schema

    hass.services = MagicMock()
    hass.services.has_service.return_value = False
    hass.services.async_register.side_effect = _register
    hass_init._register_services(hass)
    return registered, schemas


def _wire_services(hass, store, entry_id="e1", options=None):
    """Nur die Handler — Kurzform für die bestehenden Handler-Tests."""
    registered, _schemas = _wire_services_and_schemas(hass, store, entry_id, options)
    return registered


hass_init = _load_init()


# ---------------------------------------------------------------------------
# add_lab_value
# ---------------------------------------------------------------------------


def test_req_hom_122_add_lab_value_converts_unit_and_stores_reported_value():
    store = MagicMock()
    store.add_lab_reading = AsyncMock()
    hass = MagicMock()
    registered = _wire_services(hass, store)
    call = _make_call({"marker": "creatinine", "value": 1.1, "unit": "mg/dL"})

    _run(registered["add_lab_value"](call))

    store.add_lab_reading.assert_awaited_once()
    args, _kwargs = store.add_lab_reading.call_args
    assert args[2] == "creatinine"  # marker_key
    assert round(args[3], 2) == 97.24  # canonical value (µmol/L)
    assert args[4] == "µmol/L"
    assert args[5] == 1.1  # reported_value
    assert args[6] == "mg/dL"  # reported_unit


def test_req_hom_122_add_lab_value_resolves_german_alias():
    store = MagicMock()
    store.add_lab_reading = AsyncMock()
    hass = MagicMock()
    registered = _wire_services(hass, store)
    call = _make_call({"marker": "gpt", "value": 32.0})

    _run(registered["add_lab_value"](call))

    args, _kwargs = store.add_lab_reading.call_args
    assert args[2] == "alt"


def test_req_hom_122_add_lab_value_unknown_marker_raises():
    store = MagicMock()
    hass = MagicMock()
    registered = _wire_services(hass, store)
    call = _make_call({"marker": "not_a_marker", "value": 1})

    with pytest.raises(ServiceValidationError, match="unknown_marker"):
        _run(registered["add_lab_value"](call))


def test_req_hom_122_add_lab_value_missing_unit_required_marker_raises():
    store = MagicMock()
    hass = MagicMock()
    registered = _wire_services(hass, store)
    call = _make_call({"marker": "urine_protein_creatinine_ratio", "value": 10})

    with pytest.raises(ServiceValidationError, match="unit_required"):
        _run(registered["add_lab_value"](call))


def test_req_hom_122_add_lab_value_unsupported_unit_raises():
    store = MagicMock()
    hass = MagicMock()
    registered = _wire_services(hass, store)
    call = _make_call({"marker": "alt", "value": 32.0, "unit": "mg/dL"})

    with pytest.raises(ServiceValidationError, match="unsupported_unit"):
        _run(registered["add_lab_value"](call))


def test_req_hom_122_add_lab_value_resolves_custom_marker():
    store = MagicMock()
    store.add_lab_reading = AsyncMock()
    hass = MagicMock()
    options = {
        "lab_custom_markers": [
            {"key": "vitamin_d", "name": "Vitamin D", "category": "other", "unit": "ng/mL"}
        ]
    }
    registered = _wire_services(hass, store, options=options)
    call = _make_call({"marker": "vitamin_d", "value": 42.0})

    _run(registered["add_lab_value"](call))

    args, _kwargs = store.add_lab_reading.call_args
    assert args[2] == "vitamin_d"
    assert args[4] == "ng/mL"


def test_req_hom_122_add_lab_value_caps_report_ref_length():
    store = MagicMock()
    store.add_lab_reading = AsyncMock()
    hass = MagicMock()
    registered = _wire_services(hass, store)
    long_ref = "x" * 600
    call = _make_call({"marker": "alt", "value": 32.0, "report_ref": long_ref})

    _run(registered["add_lab_value"](call))

    _args, kwargs = store.add_lab_reading.call_args
    report_ref = kwargs.get("report_ref")
    assert report_ref is not None
    assert len(report_ref) == 500


# ---------------------------------------------------------------------------
# remove_last_lab_value
# ---------------------------------------------------------------------------


def test_req_hom_122_remove_last_lab_value_calls_store():
    store = MagicMock()
    store.remove_last_lab_reading = AsyncMock(return_value=True)
    hass = MagicMock()
    registered = _wire_services(hass, store)
    call = _make_call({"marker": "alt"})

    _run(registered["remove_last_lab_value"](call))

    store.remove_last_lab_reading.assert_awaited_once()
    args, _kwargs = store.remove_last_lab_reading.call_args
    assert args[1] == "alt"


def test_req_hom_122_remove_last_lab_value_resolves_alias():
    store = MagicMock()
    store.remove_last_lab_reading = AsyncMock(return_value=True)
    hass = MagicMock()
    registered = _wire_services(hass, store)
    call = _make_call({"marker": "gpt"})

    _run(registered["remove_last_lab_value"](call))

    args, _kwargs = store.remove_last_lab_reading.call_args
    assert args[1] == "alt"


def test_req_hom_122_remove_last_lab_value_unknown_marker_raises():
    store = MagicMock()
    hass = MagicMock()
    registered = _wire_services(hass, store)
    call = _make_call({"marker": "not_a_marker"})

    with pytest.raises(ServiceValidationError, match="unknown_marker"):
        _run(registered["remove_last_lab_value"](call))


def test_req_hom_122_remove_last_lab_value_no_active_value_raises():
    store = MagicMock()
    store.remove_last_lab_reading = AsyncMock(return_value=False)
    hass = MagicMock()
    registered = _wire_services(hass, store)
    call = _make_call({"marker": "alt"})

    with pytest.raises(ServiceValidationError):
        _run(registered["remove_last_lab_value"](call))


# ---------------------------------------------------------------------------
# export_csv / import_csv: `lab_values` im Service-Schema (REQ-HOM-122)
# ---------------------------------------------------------------------------

_CSV_SERVICES = ("export_csv", "import_csv")
_CSV_DATASETS = ("drinks", "blood_pressure", "lab_values", "all")


@pytest.mark.parametrize("service", _CSV_SERVICES)
@pytest.mark.parametrize("dataset", _CSV_DATASETS)
def test_req_hom_122_csv_services_schema_accepts_dataset(service, dataset):
    """[REQ-HOM-122] Beide CSV-Services akzeptieren `lab_values` (und die alten Werte)."""
    hass = MagicMock()
    _registered, schemas = _wire_services_and_schemas(hass, MagicMock())
    payload = {"dataset": dataset}
    if service == "import_csv":
        payload["filename"] = "health_o_mat_lab_values_caro.csv"

    validated = schemas[service](payload)

    assert validated["dataset"] == dataset


@pytest.mark.parametrize("service", _CSV_SERVICES)
def test_req_hom_122_csv_services_schema_rejects_unknown_dataset(service):
    """[REQ-HOM-122] Unbekannte Datensätze bleiben abgewiesen (lab_values ist erlaubt)."""
    hass = MagicMock()
    _registered, schemas = _wire_services_and_schemas(hass, MagicMock())
    payload = {"dataset": "pdf"}
    if service == "import_csv":
        payload["filename"] = "x.csv"

    with pytest.raises(vol.Invalid) as exc:
        schemas[service](payload)

    assert "lab_values" in str(exc.value)


# ---------------------------------------------------------------------------
# void_entry / restore_entry: `lab_values` als viertes Korrektur-Ziel
# ---------------------------------------------------------------------------

_STATE_SERVICES = ("void_entry", "restore_entry")


def _make_lab_store():
    """Echter Store (wie `test_wave_a`): void/restore laufen über den Storage-Pfad."""
    store_module = sys.modules[f"{_PKG}.store"]
    store = store_module.HealthOMatStore(MagicMock())
    store._store = MagicMock()
    store._store.async_load = AsyncMock(return_value=None)
    store._store.async_save = AsyncMock(return_value=None)
    _run(store.async_load())
    return store


def _add_lab_reading(store, entry_id="e1"):
    """Laborwert anlegen und dessen ID zurückgeben."""
    _run(store.add_lab_reading(entry_id, "2026-10-31T09:00:00", "alt", 32.0, "U/L", 32.0, "U/L"))
    return store.entry(entry_id)["lab_readings"][0]["id"]


def test_req_hom_122_restore_entry_restores_voided_lab_reading():
    """[REQ-HOM-122] restore_entry mit kind=lab_values hebt die Löschmarkierung auf."""
    store = _make_lab_store()
    reading_id = _add_lab_reading(store)
    _run(store.void_lab_reading("e1", reading_id))
    assert store.active_lab_readings("e1") == []
    hass = MagicMock()
    registered = _wire_services(hass, store)

    _run(registered["restore_entry"](_make_call({"kind": "lab_values", "id": reading_id})))

    assert [item["id"] for item in store.active_lab_readings("e1")] == [reading_id]
    assert any(
        event["action"] == "entry_restored" and event["target_id"] == reading_id
        for event in store.entry("e1")["audit_log"]
    ), "restore schreibt kein Audit-Event"


def test_req_hom_122_restore_entry_unknown_lab_id_raises():
    """[REQ-HOM-122] Unbekannte Laborwert-ID → ServiceValidationError (kein stiller Erfolg)."""
    store = _make_lab_store()
    hass = MagicMock()
    registered = _wire_services(hass, store)

    with pytest.raises(ServiceValidationError, match="nicht gefunden"):
        _run(registered["restore_entry"](_make_call({"kind": "lab_values", "id": "nope"})))


def test_req_hom_122_void_entry_marks_lab_reading_voided():
    """[REQ-HOM-122] void_entry kann Laborwerte voiden (gleicher Pfad wie restore)."""
    store = _make_lab_store()
    reading_id = _add_lab_reading(store)
    hass = MagicMock()
    registered = _wire_services(hass, store)

    _run(registered["void_entry"](_make_call({"kind": "lab_values", "id": reading_id})))

    assert store.active_lab_readings("e1") == []
    assert any(
        event["action"] == "entry_voided" and event["target_id"] == reading_id
        for event in store.entry("e1")["audit_log"]
    )


@pytest.mark.parametrize("service", _STATE_SERVICES)
def test_req_hom_122_state_services_schema_accepts_lab_values(service):
    """[REQ-HOM-122] Beide Korrektur-Services akzeptieren kind=lab_values."""
    hass = MagicMock()
    _registered, schemas = _wire_services_and_schemas(hass, MagicMock())

    validated = schemas[service]({"kind": "lab_values", "id": "r1"})

    assert validated == {"kind": "lab_values", "id": "r1"}
    with pytest.raises(vol.Invalid):
        schemas[service]({"kind": "tea", "id": "r1"})


def test_req_hom_122_void_entry_unknown_kind_lists_lab_values_once():
    """[Issue #70, RVW-05] Erlaubt-Liste nennt `lab_values` genau einmal.

    Der frühere Labor-Sonderweg (`_LAB_STATE_KINDS`) stand zusätzlich zu
    `logic.HISTORY_KINDS` in `allowed`; nach der Konsolidierung auf die
    logic-Tabellen darf der Fehlertext nicht doppeln.
    """
    store = _make_lab_store()
    hass = MagicMock()
    registered = _wire_services(hass, store)

    with pytest.raises(ServiceValidationError) as exc:
        _run(registered["void_entry"](_make_call({"kind": "tea", "id": "x"})))

    assert str(exc.value).count("lab_values") == 1


def test_req_hom_122_remove_last_entry_rejects_lab_values_without_keyerror():
    """[Issue #70] Labor hat kein globales Undo — klare Meldung statt KeyError."""
    store = _make_lab_store()
    hass = MagicMock()
    registered = _wire_services(hass, store)

    with pytest.raises(ServiceValidationError, match="nicht verfügbar"):
        _run(registered["remove_last_entry"](_make_call({"kind": "lab_values"})))


def test_req_hom_122_remove_last_entry_unknown_kind_excludes_lab_values():
    """[Issue #70, F1] Die Undo-Fehlerliste bietet `lab_values` nicht an."""
    store = _make_lab_store()
    hass = MagicMock()
    registered = _wire_services(hass, store)

    with pytest.raises(ServiceValidationError) as exc:
        _run(registered["remove_last_entry"](_make_call({"kind": "tea"})))

    message = str(exc.value)
    assert "lab_values" not in message
    assert "drinks, blood_pressure, wellbeing" in message


def test_req_hom_122_restore_backup_schema_accepts_lab_values_dataset():
    """[REQ-HOM-122] `restore_backup` akzeptiert `lab_values` als Datensatz-Filter."""
    hass = MagicMock()
    _registered, schemas = _wire_services_and_schemas(hass, MagicMock())

    validated = schemas["restore_backup"]({"filename": "b.json", "datasets": ["lab_values"]})

    assert validated["datasets"] == ["lab_values"]


# ---------------------------------------------------------------------------
# Service-Schema-Mirror (REQ-HOM-123/128)
# ---------------------------------------------------------------------------


def test_req_hom_123_marker_options_mirror_the_catalog_in_both_services():
    """[REQ-HOM-123] `add_lab_value` und `add_lab_report` kennen exakt `LAB_MARKERS`."""
    const_module = sys.modules[f"{_PKG}.const"]
    with open(os.path.join(_COMPONENT_DIR, "services.yaml"), encoding="utf-8") as fh:
        services = yaml.safe_load(fh)

    single = {
        option["value"]
        for option in services["add_lab_value"]["fields"]["marker"]["selector"]["select"]["options"]
    }
    batch = {
        option["value"]
        for option in services["add_lab_report"]["fields"]["values"]["selector"]["object"][
            "fields"
        ]["marker"]["selector"]["select"]["options"]
    }

    expected = set(const_module.LAB_MARKERS)
    assert single == expected, "add_lab_value driftet gegen den Katalog"
    assert batch == expected, "add_lab_report driftet gegen den Katalog"


def test_req_hom_128_remove_lab_report_fields_and_required_ts():
    """[REQ-HOM-128] Undo-Service: person/ts/report_ref, `ts` ist Pflicht."""
    with open(os.path.join(_COMPONENT_DIR, "services.yaml"), encoding="utf-8") as fh:
        services = yaml.safe_load(fh)

    fields = services["remove_lab_report"]["fields"]
    assert set(fields) == {"person", "ts", "report_ref"}
    assert fields["ts"].get("required") is True


# ---------------------------------------------------------------------------
# add_lab_report (REQ-HOM-123)
# ---------------------------------------------------------------------------


def test_req_hom_123_add_lab_report_writes_one_batch_with_shared_context(monkeypatch):
    monkeypatch.setattr(
        hass_init,
        "dt_util",
        types.SimpleNamespace(now=lambda: datetime(2026, 10, 31, 12, 0, tzinfo=UTC)),
    )

    store = MagicMock()
    store.add_lab_readings = AsyncMock(return_value=["r1", "r2"])
    hass = MagicMock()
    registered = _wire_services(hass, store)
    call = _make_call(
        {
            "values": [
                {"marker": "alt", "value": 32, "unit": "U/L"},
                {"marker": "creatinine", "value": 1.1, "unit": "mg/dL"},
            ],
            # Vergangenheit relativ zur im Test gepinnten Uhr.
            "ts": "2026-10-30T09:15:00+01:00",
            "report_ref": "  Labor 10/2026  ",
        }
    )

    assert _run(registered["add_lab_report"](call)) is None

    store.add_lab_readings.assert_awaited_once()
    args, kwargs = store.add_lab_readings.call_args
    assert args[0] == "e1"
    assert args[1] == "2026-10-30T09:15:00+01:00"
    assert [row["marker_key"] for row in args[2]] == ["alt", "creatinine"]
    assert args[2][1]["unit"] == "µmol/L"
    assert kwargs["report_ref"] == "Labor 10/2026"


def test_req_hom_123_add_lab_report_ignores_empty_rows():
    store = MagicMock()
    store.add_lab_readings = AsyncMock(return_value=["r1"])
    hass = MagicMock()
    registered = _wire_services(hass, store)
    call = _make_call({"values": [{"marker": "alt", "value": 32}, {}, {"marker": "", "value": ""}]})

    _run(registered["add_lab_report"](call))

    rows = store.add_lab_readings.call_args.args[2]
    assert [row["marker_key"] for row in rows] == ["alt"]


def test_req_hom_123_add_lab_report_rejects_unknown_marker_without_write():
    store = MagicMock()
    store.add_lab_readings = AsyncMock()
    hass = MagicMock()
    registered = _wire_services(hass, store)
    call = _make_call(
        {
            "values": [
                {"marker": "alt", "value": 32},
                {"marker": "crp", "value": 4.8},
                {"marker": "gptx", "value": 1},
            ]
        }
    )

    with pytest.raises(ServiceValidationError, match=r"Zeile 3 \(gptx\): unknown_marker"):
        _run(registered["add_lab_report"](call))

    store.add_lab_readings.assert_not_awaited()


def test_req_hom_123_add_lab_report_prefixes_invalid_ts():
    store = MagicMock()
    store.add_lab_readings = AsyncMock()
    hass = MagicMock()
    registered = _wire_services(hass, store)
    call = _make_call({"values": [{"marker": "alt", "value": 32}], "ts": "kaputt"})

    with pytest.raises(ServiceValidationError, match="^invalid_ts: "):
        _run(registered["add_lab_report"](call))

    store.add_lab_readings.assert_not_awaited()


def test_req_hom_123_add_lab_report_resolves_person_before_timestamp():
    """Ein unbekannter Entry meldet den Entry-Fehler, nicht `invalid_ts` (§2.5)."""
    store = MagicMock()
    hass = MagicMock()
    registered = _wire_services(hass, store)
    call = _make_call(
        {"person": "niemand", "values": [{"marker": "alt", "value": 32}], "ts": "kaputt"}
    )

    with pytest.raises(ServiceValidationError, match="nicht gefunden"):
        _run(registered["add_lab_report"](call))


def test_req_hom_123_add_lab_report_caps_report_ref_length():
    store = MagicMock()
    store.add_lab_readings = AsyncMock(return_value=["r1"])
    hass = MagicMock()
    registered = _wire_services(hass, store)
    call = _make_call({"values": [{"marker": "alt", "value": 32}], "report_ref": "x" * 600})

    _run(registered["add_lab_report"](call))

    assert len(store.add_lab_readings.call_args.kwargs["report_ref"]) == 500


def test_req_hom_123_add_lab_report_schema_allows_empty_row_and_rejects_extra():
    hass = MagicMock()
    _registered, schemas = _wire_services_and_schemas(hass, MagicMock())
    schema = schemas["add_lab_report"]

    parsed = schema({"values": [{}], "ts": "2026-11-01T09:15:00+01:00"})
    assert parsed["values"] == [{}]
    parsed = schema({"values": {"marker": "alt", "value": "32.5"}})
    assert parsed["values"] == [{"marker": "alt", "value": "32.5"}]

    with pytest.raises(vol.Invalid):
        schema({"values": [{"marker": "alt", "value": 1, "bogus": 2}]})
    with pytest.raises(vol.Invalid):
        schema({"ts": "2026-11-01T09:15:00+01:00"})


def test_req_hom_123_add_lab_value_rejects_nan_and_inf():
    store = MagicMock()
    store.add_lab_reading = AsyncMock()
    hass = MagicMock()
    registered = _wire_services(hass, store)

    for bad in (float("nan"), float("inf")):
        with pytest.raises(ServiceValidationError, match="invalid_value"):
            _run(registered["add_lab_value"](_make_call({"marker": "alt", "value": bad})))

    store.add_lab_reading.assert_not_awaited()


# ---------------------------------------------------------------------------
# remove_lab_report (REQ-HOM-128)
# ---------------------------------------------------------------------------


def test_req_hom_128_remove_lab_report_voids_report_with_ref(monkeypatch):
    monkeypatch.setattr(
        hass_init,
        "dt_util",
        types.SimpleNamespace(now=lambda: datetime(2026, 10, 31, 12, 0, tzinfo=UTC)),
    )

    store = MagicMock()
    store.void_lab_report = AsyncMock(return_value=["r1", "r2"])
    hass = MagicMock()
    registered = _wire_services(hass, store)
    call = _make_call(
        {
            "ts": "2026-10-30T09:15:00+01:00",
            "report_ref": "  Labor 10/2026  ",
        }
    )

    assert _run(registered["remove_lab_report"](call)) is None

    store.void_lab_report.assert_awaited_once()
    args, kwargs = store.void_lab_report.call_args
    assert args == ("e1", "2026-10-30T09:15:00+01:00")
    assert kwargs["report_ref"] == "Labor 10/2026"


def test_req_hom_128_remove_lab_report_without_ref_passes_none(monkeypatch):
    monkeypatch.setattr(
        hass_init,
        "dt_util",
        types.SimpleNamespace(now=lambda: datetime(2026, 10, 31, 12, 0, tzinfo=UTC)),
    )

    store = MagicMock()
    store.void_lab_report = AsyncMock(return_value=["r1"])
    hass = MagicMock()
    registered = _wire_services(hass, store)

    _run(registered["remove_lab_report"](_make_call({"ts": "2026-10-30T09:15:00+01:00"})))

    assert store.void_lab_report.call_args.kwargs["report_ref"] is None


def test_req_hom_128_remove_lab_report_no_match_raises(monkeypatch):
    monkeypatch.setattr(
        hass_init,
        "dt_util",
        types.SimpleNamespace(now=lambda: datetime(2026, 10, 31, 12, 0, tzinfo=UTC)),
    )

    store = MagicMock()
    store.void_lab_report = AsyncMock(return_value=[])
    hass = MagicMock()
    registered = _wire_services(hass, store)

    with pytest.raises(ServiceValidationError, match="no_active_report"):
        _run(registered["remove_lab_report"](_make_call({"ts": "2026-10-30T09:15:00+01:00"})))


def test_req_hom_128_remove_lab_report_invalid_ts_raises_with_prefix():
    store = MagicMock()
    store.void_lab_report = AsyncMock()
    hass = MagicMock()
    registered = _wire_services(hass, store)

    with pytest.raises(ServiceValidationError, match="^invalid_ts: "):
        _run(registered["remove_lab_report"](_make_call({"ts": "kaputt"})))

    store.void_lab_report.assert_not_awaited()


def test_req_hom_128_remove_lab_report_caps_report_ref_length(monkeypatch):
    monkeypatch.setattr(
        hass_init,
        "dt_util",
        types.SimpleNamespace(now=lambda: datetime(2026, 10, 31, 12, 0, tzinfo=UTC)),
    )

    store = MagicMock()
    store.void_lab_report = AsyncMock(return_value=["r1"])
    hass = MagicMock()
    registered = _wire_services(hass, store)

    _run(
        registered["remove_lab_report"](
            _make_call({"ts": "2026-10-30T09:15:00+01:00", "report_ref": "x" * 600})
        )
    )

    assert len(store.void_lab_report.call_args.kwargs["report_ref"]) == 500


def test_req_hom_128_remove_lab_report_schema_requires_ts():
    hass = MagicMock()
    _registered, schemas = _wire_services_and_schemas(hass, MagicMock())
    schema = schemas["remove_lab_report"]

    parsed = schema({"ts": "2026-10-30T09:15:00+01:00"})
    assert parsed["ts"] == "2026-10-30T09:15:00+01:00"

    with pytest.raises(vol.Invalid):
        schema({})
    with pytest.raises(vol.Invalid):
        schema({"ts": "2026-10-30T09:15:00+01:00", "bogus": 1})


# ---------------------------------------------------------------------------
# Labor-Retention (REQ-HOM-129)
# ---------------------------------------------------------------------------


def test_req_hom_129_lab_retention_months_reads_options_or_zero():
    assert hass_init._lab_retention_months(_wire_entry_like({})) == 0
    assert hass_init._lab_retention_months(_wire_entry_like({"lab_retention_months": 24})) == 24
    assert hass_init._lab_retention_months(_wire_entry_like({"lab_retention_months": "x"})) == 0


def _wire_entry_like(options: dict):
    entry = MagicMock()
    entry.entry_id = "e1"
    entry.options = options
    return entry


def test_req_hom_129_apply_lab_retention_default_off_is_noop(monkeypatch):
    store = MagicMock()
    store.void_lab_readings_before = AsyncMock()
    entry = _wire_entry_like({})
    hass = MagicMock()

    _run(hass_init._apply_lab_retention(hass, entry, store))

    store.void_lab_readings_before.assert_not_awaited()


def test_req_hom_129_apply_lab_retention_voids_before_cutoff(monkeypatch):
    store = MagicMock()
    store.void_lab_readings_before = AsyncMock(return_value=["r1"])
    entry = _wire_entry_like({"lab_retention_months": 12})
    hass = MagicMock()
    monkeypatch.setattr(
        hass_init.dt_util,
        "now",
        lambda: datetime(2026, 11, 1, 12, 0, tzinfo=UTC),
    )

    _run(hass_init._apply_lab_retention(hass, entry, store))

    store.void_lab_readings_before.assert_awaited_once()
    args, kwargs = store.void_lab_readings_before.call_args
    assert args[0] == "e1"
    assert args[1] == "2025-11-01T12:00:00+00:00"
    assert kwargs["months"] == 12


# ---------------------------------------------------------------------------
# #71/#72: Einzel-Add lehnt Duplikate `(ts, marker_key)` ab
# ---------------------------------------------------------------------------


def _freeze_clock(monkeypatch) -> None:
    """`dt_util.now` fixieren: die festen Test-`ts` müssen in der Vergangenheit liegen.

    Andere Suiten setzen `dt_util.now` teils dauerhaft (Modul-Attribut); ohne
    Fixierung hinge das Ergebnis hier von der Testreihenfolge ab.
    """
    monkeypatch.setattr(hass_init.dt_util, "now", lambda: datetime(2026, 11, 5, 12, 0))


def test_req_hom_122_add_lab_value_duplicate_marker_raises(monkeypatch):
    """[#72] Store meldet Duplikat → ServiceValidationError, kein Refresh."""
    _freeze_clock(monkeypatch)
    store = MagicMock()
    store.add_lab_reading = AsyncMock(side_effect=ValueError("duplicate_marker"))
    hass = MagicMock()
    registered = _wire_services(hass, store)
    call = _make_call({"marker": "alt", "value": 32.0, "ts": "2026-10-31T09:00:00"})

    with pytest.raises(ServiceValidationError, match="duplicate_marker"):
        _run(registered["add_lab_value"](call))

    store.add_lab_reading.assert_awaited_once()


def test_req_hom_123_add_lab_report_duplicate_marker_raises(monkeypatch):
    """[#72] Bericht mit vorhandenem `(ts, marker_key)` → ServiceValidationError."""
    _freeze_clock(monkeypatch)
    store = MagicMock()
    store.add_lab_readings = AsyncMock(side_effect=ValueError("duplicate_marker"))
    hass = MagicMock()
    registered = _wire_services(hass, store)
    call = _make_call(
        {
            "ts": "2026-10-31T09:00:00",
            "values": [{"marker": "alt", "value": 32.0, "unit": "U/L"}],
        }
    )

    with pytest.raises(ServiceValidationError, match="duplicate_marker"):
        _run(registered["add_lab_report"](call))

    store.add_lab_readings.assert_awaited_once()


def test_req_hom_122_add_lab_value_second_write_is_rejected_by_real_store(monkeypatch):
    """[#72] Echter Store: gleicher ts/Marker, neuer Wert → kein zweiter Eintrag."""
    _freeze_clock(monkeypatch)
    store = _make_lab_store()
    hass = MagicMock()
    registered = _wire_services(hass, store)
    first = _make_call({"marker": "alt", "value": 32.0, "ts": "2026-10-31T09:00:00+01:00"})
    # Derselbe Instant in anderer Schreibweise ist ebenfalls ein Duplikat.
    second = _make_call({"marker": "alt", "value": 99.0, "ts": "2026-10-31T08:00:00Z"})

    _run(registered["add_lab_value"](first))
    with pytest.raises(ServiceValidationError, match="duplicate_marker"):
        _run(registered["add_lab_value"](second))

    readings = store.entry("e1")["lab_readings"]
    assert [item["value"] for item in readings] == [32.0]


def test_req_hom_123_add_lab_report_second_write_is_rejected_by_real_store(monkeypatch):
    """[#72] Echter Store: Bericht mit gleichem `(ts, marker)` → alles-oder-nichts."""
    _freeze_clock(monkeypatch)
    store = _make_lab_store()
    hass = MagicMock()
    registered = _wire_services(hass, store)
    first = _make_call(
        {
            "ts": "2026-10-31T09:00:00",
            "values": [{"marker": "alt", "value": 32.0, "unit": "U/L"}],
        }
    )
    second = _make_call(
        {
            "ts": "2026-10-31T09:00:00",
            "values": [
                {"marker": "crp", "value": 4.8, "unit": "mg/L"},
                {"marker": "alt", "value": 99.0, "unit": "U/L"},
            ],
        }
    )

    _run(registered["add_lab_report"](first))
    with pytest.raises(ServiceValidationError, match="duplicate_marker"):
        _run(registered["add_lab_report"](second))

    assert [item["marker_key"] for item in store.entry("e1")["lab_readings"]] == ["alt"]

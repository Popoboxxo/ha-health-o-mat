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
from unittest.mock import AsyncMock, MagicMock

import pytest
import voluptuous as vol
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

    def _register(domain, name, schema=None, service_func=None):
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

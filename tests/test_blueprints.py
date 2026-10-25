"""Tests: HA-Blueprints für Erinnerungen/Blutdruck/Wochenbericht (REQ-HOM-118)."""

from __future__ import annotations

import importlib.util
import json
import os
import sys
import types
from pathlib import Path

import pytest
import yaml

_ROOT = Path(__file__).resolve().parent.parent
_COMPONENT_DIR = _ROOT / "custom_components" / "health_o_mat"
_BLUEPRINT_DIR = _ROOT / "blueprints" / "automation" / "health_o_mat"

_BLUEPRINTS = {
    "evening_reminder": {
        "inputs": {"person_name", "goal_sensor", "notify_service", "reminder_time"},
        "entity_domain": "sensor",
    },
    "blood_pressure_warning": {
        "inputs": {"person_name", "warning_sensor", "notify_service"},
        "entity_domain": "binary_sensor",
    },
    "weekly_report": {
        "inputs": {"person_name", "report_day", "report_time"},
        "entity_domain": None,
    },
}


class _BlueprintLoader(yaml.SafeLoader):
    """SafeLoader mit HA-``!input``-Tag (Blueprint-Platzhalter)."""


def _construct_input(loader: _BlueprintLoader, node: yaml.Node) -> dict[str, str]:
    return {"__input__": loader.construct_scalar(node)}


_BlueprintLoader.add_constructor("!input", _construct_input)


def _load_yaml(path: Path) -> dict:
    return yaml.load(path.read_text(encoding="utf-8"), Loader=_BlueprintLoader)


@pytest.mark.parametrize("name", sorted(_BLUEPRINTS))
def test_blueprint_has_valid_structure(name: str) -> None:
    """Jeder Blueprint ist parsebar und trägt das HA-Pflichtschema."""
    blueprint = _load_yaml(_BLUEPRINT_DIR / f"{name}.yaml")["blueprint"]

    assert blueprint["name"]
    assert blueprint["description"]
    assert blueprint["domain"] == "automation"
    assert isinstance(blueprint["input"], dict) and blueprint["input"]

    data = _load_yaml(_BLUEPRINT_DIR / f"{name}.yaml")
    assert isinstance(data["trigger"], list) and data["trigger"]
    assert "condition" in data
    assert isinstance(data["action"], list) and data["action"]
    assert data.get("mode") in (None, "single", "restart", "queued", "parallel")


@pytest.mark.parametrize("name", sorted(_BLUEPRINTS))
def test_blueprint_inputs_are_documented_and_bilingual(name: str) -> None:
    """Alle erwarteten Inputs existieren; Beschreibung nennt DE und EN."""
    data = _load_yaml(_BLUEPRINT_DIR / f"{name}.yaml")
    inputs = data["blueprint"]["input"]

    assert set(inputs) == _BLUEPRINTS[name]["inputs"]
    for key, spec in inputs.items():
        assert spec.get("name"), f"{name}.{key}: name fehlt"
        assert spec.get("description"), f"{name}.{key}: description fehlt"
        assert "English" in spec["description"], f"{name}.{key}: englische Beschreibung fehlt"
    assert "English:" in data["blueprint"]["description"]


@pytest.mark.parametrize("name", ["evening_reminder", "blood_pressure_warning"])
def test_notify_blueprints_reference_input_service(name: str) -> None:
    """Notify-Blueprints rufen den als Input gewählten Service auf."""
    data = _load_yaml(_BLUEPRINT_DIR / f"{name}.yaml")
    step = data["action"][0]

    assert step["service"] == {"__input__": "notify_service"}
    assert step["data"]["title"]
    assert step["data"]["message"]


@pytest.mark.parametrize(
    ("name", "domain"),
    [("evening_reminder", "sensor"), ("blood_pressure_warning", "binary_sensor")],
)
def test_blueprint_entity_selector_matches_domain(name: str, domain: str) -> None:
    """Der Entity-Selector zeigt auf die passende Entity-Domain."""
    data = _load_yaml(_BLUEPRINT_DIR / f"{name}.yaml")
    inputs = data["blueprint"]["input"]

    key = next(key for key, spec in inputs.items() if "entity" in spec.get("selector", {}))
    assert inputs[key]["selector"]["entity"]["domain"] == domain


def test_weekly_report_blueprint_calls_the_registered_service() -> None:
    """Der Wochenbericht-Blueprint nutzt den echten Service-Namen."""
    data = _load_yaml(_BLUEPRINT_DIR / "weekly_report.yaml")
    step = data["action"][0]

    assert step["service"] == "health_o_mat.weekly_report"
    assert step["data"]["person"] == {"__input__": "person_name"}

    services_yaml = yaml.safe_load((_COMPONENT_DIR / "services.yaml").read_text(encoding="utf-8"))
    assert "weekly_report" in services_yaml

    master = json.loads((_COMPONENT_DIR / "strings.json").read_text(encoding="utf-8"))
    assert "weekly_report" in master["services"]


def test_weekly_report_blueprint_condition_uses_report_day() -> None:
    """Der Wochenbericht läuft nur am gewählten Wochentag."""
    data = _load_yaml(_BLUEPRINT_DIR / "weekly_report.yaml")

    assert data["condition"] == [{"condition": "time", "weekday": {"__input__": "report_day"}}]


def test_weekly_report_service_is_part_of_the_service_registry() -> None:
    """`health_o_mat.weekly_report` steht in der Service-Registry des Setups."""
    for name in ("store", "entity", "const", "parser", "logic", "exporter"):
        _load_module(name)
    init = _load_module("init", filename="__init__.py")

    assert "weekly_report" in init._SERVICE_NAMES


# --- Helpers ---------------------------------------------------------------


def _load_module(name: str, *, filename: str | None = None):
    package = "_hom_blueprint_test_pkg"
    if package not in sys.modules:
        pkg = types.ModuleType(package)
        pkg.__path__ = [str(_COMPONENT_DIR)]
        sys.modules[package] = pkg
    full_name = f"{package}.{name}"
    if full_name in sys.modules:
        return sys.modules[full_name]
    path = os.path.join(str(_COMPONENT_DIR), filename or f"{name}.py")
    spec = importlib.util.spec_from_file_location(full_name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[full_name] = module
    spec.loader.exec_module(module)
    return module

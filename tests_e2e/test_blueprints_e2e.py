"""E2E: blueprints imported and validated by Home Assistant (REQ-HOM-006 AK 1).

The unit suite (``tests/test_blueprints.py``) proves that *our* YAML loader sees
four structurally sound blueprints. That is not what AK 1 asks for: the
acceptance criterion is "validate against the HA schema (E2E: import on
ha-test)", i.e. Home Assistant itself has to read the files and accept them.

This module therefore never asserts on its own YAML parsing. Every fact comes
from HA's blueprint/automation machinery, driven over the admin websocket and
REST API of the **Compose** E2E stack (``docker-compose.e2e.yml``, port
``8124``) — never from the shared ``/home/hermes/ha-test`` instance:

* **import** — ``blueprint/save`` (what the "Import blueprint" frontend does)
  writes the file into ``hass.config.path("blueprints/automation",
  "health_o_mat")`` and builds a ``blueprint.models.Blueprint`` from it. That
  constructor *is* the validator: ``BLUEPRINT_SCHEMA``, the expected domain
  check and "every ``!input`` must be declared". A rejected blueprint raises
  and no file is written.
* **discovery** — ``automation.reload`` runs
  ``DomainBlueprints.async_reset_cache()`` (``components/automation/__init__.py``),
  so the following ``blueprint/list`` re-globs ``blueprints/automation/**/*.yaml``
  from disk instead of answering from the cache filled by the save.
* **automation schema validation** — ``POST /api/config/automation/config/<id>``
  is served by ``EditAutomationConfigView(data_validator=async_validate_config_item)``
  with ``raise_on_errors=True``: HA substitutes the inputs, validates the
  *substituted* config against ``automation.PLATFORM_SCHEMA`` and then validates
  triggers, conditions and actions. Every problem becomes HTTP 400, so a 200 is
  a genuine "HA accepted this blueprint instantiation" — and a 400 is a genuine
  rejection, not an exception from this test's own loader.
* **rendering** — ``POST /api/template`` executes HA's own Jinja environment,
  the same one that renders an automation's ``message``.

What this module does **not** prove: that a real automation fires and hits a
notify service. The seed ``configuration.yaml`` deliberately has no
``automation:`` include, so HA stores the automation config but creates no
automation entity that could be triggered.

This module **writes** to the instance (it imports blueprints and creates
automations), so it refuses to run against the shared dev instance
(``/home/hermes/ha-test``, loopback:8123) — see the import-time guard below.
"""

from __future__ import annotations

import json
import os
import pathlib
import urllib.parse
from typing import Any

import pytest
import requests

from scripts.e2e_bootstrap import BootstrapError, _headers, _ws_command

pytestmark = pytest.mark.e2e

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
BLUEPRINT_DIR = REPO_ROOT / "blueprints" / "automation" / "health_o_mat"

# The shared multi-repo dev instance. Never a target for this module (its
# blueprint folder and registries are used by other projects).
SHARED_DEV_PORT = 8123
LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1", "[::1]"})
ALLOW_SHARED_ENV = "HASS_ALLOW_PORT_8123"


def _is_shared_dev_instance(base_url: str) -> bool:
    """Whether `base_url` addresses the shared instance (loopback:8123).

    Deliberately host-aware: inside the Compose network the stack is reached as
    ``http://homeassistant:8123``, which is a throwaway instance and must run.
    """
    parsed = urllib.parse.urlsplit(base_url)
    return (parsed.hostname or "") in LOOPBACK_HOSTS and (
        parsed.port or (443 if parsed.scheme == "https" else 80)
    ) == SHARED_DEV_PORT


# Import-time guard, not a fixture: this module imports blueprints and creates
# automations, and pytest may build session fixtures (conftest's bootstrap)
# before any module fixture runs. Checking at import is the only point that is
# guaranteed to precede every write. `pytest.skip` keeps the refusal visible
# (a skipped module, not a silently green one) without mutating anything.
if (
    _is_shared_dev_instance(os.environ.get("HASS_BASE_URL", f"http://localhost:{SHARED_DEV_PORT}"))
    and os.environ.get(ALLOW_SHARED_ENV) != "1"
):
    pytest.skip(
        "test_blueprints_e2e imports blueprints and creates automations — it"
        " refuses to run against the shared dev instance (loopback:8123)."
        " Point HASS_BASE_URL at the Compose stack (E2E_HA_PORT, default 8124)"
        f" or set {ALLOW_SHARED_ENV}=1 if that really is a throwaway stack.",
        allow_module_level=True,
    )

# Synthetically generated, realistic-shaped fixture data (no production data).
PERSON = "Marlene Hoffmann"
GOAL_SENSOR = "binary_sensor.marlene_hoffmann_daily_goal_reached"
PROGRESS_SENSOR = "sensor.marlene_hoffmann_daily_goal_progress"
WARNING_SENSOR = "binary_sensor.marlene_hoffmann_blood_pressure_warning"
NOTIFY_SERVICE = "notify.persistent_notification"

# The contract HA has to read back: relative path in
# /config/blueprints/automation, the `blueprint.name`, the declared input keys
# and the defaults of the optional inputs.
BLUEPRINTS: dict[str, dict[str, Any]] = {
    "weekly_report": {
        "path": "health_o_mat/weekly_report.yaml",
        "name": "Health-O-Mat Wochenbericht",
        "inputs": {"person_name", "report_day", "report_time"},
        "defaults": {"person_name": "", "report_day": "mon", "report_time": "18:00:00"},
    },
    "evening_reminder": {
        "path": "health_o_mat/evening_reminder.yaml",
        "name": "Health-O-Mat Abend-Erinnerung",
        "inputs": {"person_name", "goal_sensor", "notify_service", "reminder_time"},
        "defaults": {
            "person_name": "",
            "notify_service": "notify.notify",
            "reminder_time": "20:00:00",
        },
    },
    "blood_pressure_warning": {
        "path": "health_o_mat/blood_pressure_warning.yaml",
        "name": "Health-O-Mat Blutdruck-Warnung",
        "inputs": {"person_name", "warning_sensor", "notify_service"},
        "defaults": {"person_name": "", "notify_service": "notify.notify"},
    },
    "goal_reached": {
        "path": "health_o_mat/goal_reached.yaml",
        "name": "Health-O-Mat Ziel erreicht",
        "inputs": {"person_name", "goal_sensor", "notify_service"},
        "defaults": {"person_name": "", "notify_service": "notify.notify"},
    },
}

# Fully specified input sets — every blueprint needs its non-defaulted inputs.
INPUTS: dict[str, dict[str, Any]] = {
    "weekly_report": {
        "person_name": PERSON,
        "report_day": "wed",
        "report_time": "18:30:00",
    },
    "evening_reminder": {
        "person_name": PERSON,
        "goal_sensor": PROGRESS_SENSOR,
        "notify_service": NOTIFY_SERVICE,
        "reminder_time": "20:15:00",
    },
    "blood_pressure_warning": {
        "person_name": PERSON,
        "warning_sensor": WARNING_SENSOR,
        "notify_service": NOTIFY_SERVICE,
    },
    "goal_reached": {
        "person_name": PERSON,
        "goal_sensor": GOAL_SENSOR,
        "notify_service": NOTIFY_SERVICE,
    },
}

# Deliberately broken blueprints HA must refuse to import. Each one is a
# distinct rejection reason of the real validator.
INVALID_BLUEPRINTS: dict[str, tuple[str, str]] = {
    # 1. `blueprint.name` is mandatory in BLUEPRINT_SCHEMA.
    "missing_name": (
        "health_o_mat/zz_e2e_missing_name.yaml",
        "blueprint:\n"
        "  domain: automation\n"
        "  input:\n"
        "    person_name:\n"
        "      name: Person\n"
        "trigger:\n"
        "  - platform: time\n"
        "    at: !input person_name\n"
        "action: []\n",
    ),
    # 2. `!input` without a matching declaration in `blueprint.input`.
    "undeclared_input": (
        "health_o_mat/zz_e2e_undeclared_input.yaml",
        "blueprint:\n"
        "  name: E2E undeclared input\n"
        "  domain: automation\n"
        "  input:\n"
        "    person_name:\n"
        "      name: Person\n"
        "trigger:\n"
        "  - platform: time\n"
        "    at: !input not_declared\n"
        "action: []\n",
    ),
    # 3. A `script` blueprint saved into the automation folder is rejected.
    "wrong_domain": (
        "health_o_mat/zz_e2e_wrong_domain.yaml",
        "blueprint:\n  name: E2E wrong domain\n  domain: script\ntrigger: []\naction: []\n",
    ),
}


# --- helpers ---------------------------------------------------------------


def _ws(base_url: str, token: str, payload: dict[str, Any]) -> Any:
    return _ws_command(base_url, token, payload)


def _save_blueprint(base_url: str, token: str, rel_path: str, yaml_text: str) -> Any:
    """Import one blueprint exactly like the frontend's import dialog does."""
    return _ws(
        base_url,
        token,
        {
            "type": "blueprint/save",
            "domain": "automation",
            "path": rel_path,
            "yaml": yaml_text,
            "allow_override": True,
        },
    )


def _list_blueprints(base_url: str, token: str) -> dict[str, Any]:
    return dict(_ws(base_url, token, {"type": "blueprint/list", "domain": "automation"}))


def _substitute(
    base_url: str, token: str, rel_path: str, blueprint_input: dict[str, Any]
) -> dict[str, Any]:
    result = _ws(
        base_url,
        token,
        {
            "type": "blueprint/substitute",
            "domain": "automation",
            "path": rel_path,
            "input": blueprint_input,
        },
    )
    return dict(result["substituted_config"])


def _reload_automations(base_url: str, token: str) -> None:
    """Drop the blueprint cache so the next list re-reads the folder from disk."""
    response = requests.post(
        f"{base_url}/api/services/automation/reload",
        headers=_headers(token),
        json={},
        timeout=60,
    )
    response.raise_for_status()


def _dig(value: Any, path: tuple[str | int, ...]) -> Any:
    for key in path:
        value = value[key]
    return value


def _post_automation(
    base_url: str, token: str, config_key: str, config: dict[str, Any]
) -> requests.Response:
    return requests.post(
        f"{base_url}/api/config/automation/config/{config_key}",
        headers=_headers(token),
        json=config,
        timeout=60,
    )


def _delete_automation(base_url: str, token: str, config_key: str) -> None:
    requests.delete(
        f"{base_url}/api/config/automation/config/{config_key}",
        headers=_headers(token),
        timeout=60,
    )


# --- fixtures --------------------------------------------------------------


@pytest.fixture(scope="session")
def blueprint_library(hass_base_url: str, hass_bearer_token: str) -> dict[str, Any]:
    """Import all four blueprints through HA, then read the folder back.

    `blueprint/save` performs the import (schema + input-definition
    validation); `automation.reload` clears the cache that save populated, so
    the returned `blueprint/list` is a genuine scan of
    ``/config/blueprints/automation/**/*.yaml``.
    """
    for spec in BLUEPRINTS.values():
        source = BLUEPRINT_DIR / pathlib.Path(str(spec["path"])).name
        _save_blueprint(
            hass_base_url,
            hass_bearer_token,
            str(spec["path"]),
            source.read_text(encoding="utf-8"),
        )

    _reload_automations(hass_base_url, hass_bearer_token)
    return _list_blueprints(hass_base_url, hass_bearer_token)


@pytest.fixture
def created_automations(hass_base_url: str, hass_bearer_token: str):
    """Config keys created by a test; removed again afterwards."""
    keys: list[str] = []
    yield keys
    for key in keys:
        _delete_automation(hass_base_url, hass_bearer_token, key)


# --- 1. real import into HA's blueprint folder -----------------------------


@pytest.mark.parametrize("blueprint", sorted(BLUEPRINTS))
def test_req_hom_006_ak1_ha_lists_imported_blueprint(
    blueprint_library: dict[str, Any], blueprint: str
) -> None:
    """HA's own listing knows the blueprint, with the expected metadata."""
    spec = BLUEPRINTS[blueprint]
    rel_path = spec["path"]

    assert rel_path in blueprint_library, (
        f"{rel_path} missing from blueprint/list (got {sorted(blueprint_library)})"
    )
    entry = blueprint_library[rel_path]
    assert "error" not in entry, f"HA failed to parse {rel_path}: {entry['error']}"

    metadata = entry["metadata"]
    assert metadata["name"] == spec["name"]
    assert metadata["domain"] == "automation"
    assert str(metadata["source_url"]).startswith("https://github.com/Popoboxxo/ha-health-o-mat/")
    # HA parsed every declared input, not just the header.
    assert set(metadata["input"]) == spec["inputs"]
    for input_key, default in spec["defaults"].items():
        assert metadata["input"][input_key]["default"] == default
    # The inputs the person has to pick are mandatory (no default to fall back to).
    for input_key in spec["inputs"] - set(spec["defaults"]):
        assert "default" not in metadata["input"][input_key]


def test_req_hom_006_ak1_blueprint_list_scans_config_folder(
    blueprint_library: dict[str, Any],
) -> None:
    """The listing comes from the config folder, not from a private registry.

    HA ships sample blueprints in ``blueprints/automation/homeassistant/``; they
    are listed by the very same scan that found our four files.
    """
    assert {key for key in blueprint_library if key.startswith("health_o_mat/")} == {
        spec["path"] for spec in BLUEPRINTS.values()
    }
    assert "homeassistant/motion_light.yaml" in blueprint_library


# --- 2. HA resolves the inputs (no `!input` left) --------------------------


@pytest.mark.parametrize("blueprint", sorted(BLUEPRINTS))
def test_req_hom_006_ak1_ha_substitutes_every_input(
    hass_base_url: str, hass_bearer_token: str, blueprint_library: dict[str, Any], blueprint: str
) -> None:
    """`blueprint/substitute` leaves no placeholder behind and binds the values."""
    spec = BLUEPRINTS[blueprint]
    substituted = _substitute(hass_base_url, hass_bearer_token, spec["path"], INPUTS[blueprint])

    assert "!input" not in json.dumps(substituted)
    assert "blueprint" not in substituted
    assert "use_blueprint" not in substituted

    if blueprint == "weekly_report":
        # No `variables:` block here — the input is bound straight into the call.
        assert _dig(substituted, ("actions", 0, "data", "person")) == PERSON
        return

    # The `variables:` binding is what makes the person name usable in a
    # template at all (blueprint inputs are not template variables by default).
    assert _dig(substituted, ("variables", "person")) == PERSON
    assert _dig(substituted, ("actions", 0, "service")) == NOTIFY_SERVICE


def test_req_hom_006_ak1_goal_reached_binds_trigger_and_condition(
    hass_base_url: str, hass_bearer_token: str, blueprint_library: dict[str, Any]
) -> None:
    """The entity inputs land in trigger *and* condition of `goal_reached`."""
    substituted = _substitute(
        hass_base_url,
        hass_bearer_token,
        BLUEPRINTS["goal_reached"]["path"],
        INPUTS["goal_reached"],
    )

    assert _dig(substituted, ("triggers", 0, "entity_id")) == GOAL_SENSOR
    assert _dig(substituted, ("triggers", 0, "from")) == "off"
    assert _dig(substituted, ("triggers", 0, "to")) == "on"
    assert _dig(substituted, ("conditions", 0, "entity_id")) == GOAL_SENSOR
    assert _dig(substituted, ("conditions", 0, "state")) == "on"


# --- 3. negative: HA rejects invalid blueprints ----------------------------


@pytest.mark.parametrize("case", sorted(INVALID_BLUEPRINTS))
def test_req_hom_006_ak1_invalid_blueprint_is_rejected(
    hass_base_url: str, hass_bearer_token: str, blueprint_library: dict[str, Any], case: str
) -> None:
    """An invalid blueprint is refused by HA itself and never becomes importable."""
    rel_path, yaml_text = INVALID_BLUEPRINTS[case]

    with pytest.raises(BootstrapError) as rejection:
        _save_blueprint(hass_base_url, hass_bearer_token, rel_path, yaml_text)

    error = str(rejection.value)
    assert "invalid_format" in error, error
    assert "Invalid blueprint" in error, error

    # ... and it is not part of what HA offers for instantiation.
    assert rel_path not in _list_blueprints(hass_base_url, hass_bearer_token)


# --- 4. negatives on the automation schema ---------------------------------


def test_req_hom_006_ak1_automation_without_required_input_is_rejected(
    hass_base_url: str, hass_bearer_token: str, blueprint_library: dict[str, Any]
) -> None:
    """HA's automation validator enforces the declared inputs (HTTP 400)."""
    response = _post_automation(
        hass_base_url,
        hass_bearer_token,
        "hom_e2e_blueprint_missing_input",
        {
            "alias": "HOM E2E blueprint incomplete",
            "use_blueprint": {
                "path": BLUEPRINTS["goal_reached"]["path"],
                "input": {"person_name": PERSON, "notify_service": NOTIFY_SERVICE},
            },
        },
    )

    assert response.status_code == 400, response.text
    assert "goal_sensor" in response.text


def test_req_hom_006_ak1_automation_with_unknown_blueprint_is_rejected(
    hass_base_url: str, hass_bearer_token: str, blueprint_library: dict[str, Any]
) -> None:
    """A `use_blueprint` path HA cannot load is a validation error, not a silent no-op."""
    response = _post_automation(
        hass_base_url,
        hass_bearer_token,
        "hom_e2e_blueprint_unknown",
        {
            "alias": "HOM E2E blueprint unknown",
            "use_blueprint": {
                "path": "health_o_mat/does_not_exist.yaml",
                "input": {"person_name": PERSON},
            },
        },
    )

    assert response.status_code == 400, response.text
    assert "Failed to load blueprint" in response.text


# --- 5. positive: an automation is created *from* the blueprint ------------


@pytest.mark.parametrize("blueprint", ["goal_reached", "evening_reminder"])
def test_req_hom_006_ak1_automation_from_blueprint_is_accepted(
    hass_base_url: str,
    hass_bearer_token: str,
    blueprint_library: dict[str, Any],
    created_automations: list[str],
    blueprint: str,
) -> None:
    """POST + GET through HA's automation config API prove the schema holds.

    `POST /api/config/automation/config/<id>` validates the *substituted*
    config (blueprint inputs -> platform schema -> trigger/condition/action
    validation) and only stores it afterwards, so a 200 plus a read-back of the
    identical `use_blueprint` block is HA's own statement that the blueprint
    generates a valid automation.
    """
    spec = BLUEPRINTS[blueprint]
    config_key = f"hom_e2e_blueprint_{blueprint}"
    config = {
        "alias": f"HOM E2E {blueprint}",
        "use_blueprint": {"path": spec["path"], "input": INPUTS[blueprint]},
    }
    created_automations.append(config_key)

    response = _post_automation(hass_base_url, hass_bearer_token, config_key, config)
    assert response.status_code == 200, response.text
    assert response.json() == {"result": "ok"}

    read_back = requests.get(
        f"{hass_base_url}/api/config/automation/config/{config_key}",
        headers=_headers(hass_bearer_token),
        timeout=60,
    )
    assert read_back.status_code == 200, read_back.text
    stored = read_back.json()
    assert stored["id"] == config_key
    assert stored["alias"] == config["alias"]
    assert stored["use_blueprint"] == config["use_blueprint"]


# --- 6. the `variables` binding really reaches the message -----------------


RENDER_CASES = [
    (
        "evening_reminder",
        "Erinnerung: ",
    ),
    (
        "blood_pressure_warning",
        "Blutdruck-Warnung: ",
    ),
]


@pytest.mark.parametrize(("blueprint", "fallback_prefix"), RENDER_CASES)
def test_req_hom_006_ak1_message_renders_person_name(
    hass_base_url: str,
    hass_bearer_token: str,
    blueprint_library: dict[str, Any],
    blueprint: str,
    fallback_prefix: str,
) -> None:
    """HA's own template engine renders the person name into the message.

    The substituted `message` and the substituted `variables` are handed to
    `POST /api/template` — the same renderer an automation uses. The empty-name
    run is the counter-check: without the binding the person name cannot appear,
    so a green result here cannot be produced by a hardcoded default.
    """
    spec = BLUEPRINTS[blueprint]

    substituted = _substitute(hass_base_url, hass_bearer_token, spec["path"], INPUTS[blueprint])
    message_template = _dig(substituted, ("actions", 0, "data", "message"))
    variables = dict(substituted["variables"])
    assert variables["person"] == PERSON

    def render(payload: dict[str, Any]) -> str:
        response = requests.post(
            f"{hass_base_url}/api/template",
            headers=_headers(hass_bearer_token),
            json=payload,
            timeout=60,
        )
        assert response.status_code == 200, response.text
        return response.text

    rendered = render({"template": message_template, "variables": variables})
    assert PERSON in rendered, rendered
    assert not rendered.startswith(fallback_prefix), rendered

    # Counter-check: the same template with an empty person must NOT leak the name.
    anonymous = render({"template": message_template, "variables": {"person": ""}})
    assert PERSON not in anonymous, anonymous
    assert anonymous.startswith(fallback_prefix), anonymous

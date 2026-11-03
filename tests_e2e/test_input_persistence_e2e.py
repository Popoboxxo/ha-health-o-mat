"""E2E: a half-filled blood-pressure capture survives an HA restart (REQ-HOM-104).

REQ-HOM-104 stores the three BP input fields (``sys``/``dia``/``pulse``) in the
shared store instead of keeping them in the entity's runtime memory, and empties
them when a reading is saved. The unit suite proves the store round-trip
(``tests/test_store.py``), but "survives a restart" is a property of the running
process: only a real stop/start shows whether the values were really persisted
before the process went away or merely held in memory.

The scenario therefore drives the *entity* path a user takes — ``number.set_value``
on the three input entities — then restarts the Compose container and reads the
values back from both the served entity states and the store document on disk.
Saving through the real save button must then clear store **and** entities, and
produce exactly one reading (otherwise "cleared" could just mean "nothing was
saved").

This module restarts the instance, so it refuses to run against the shared dev
instance (``/home/hermes/ha-test``, loopback:8123) — see the import-time guard.
Inside the Compose ``e2e`` runner container there is no Docker socket, so the
scenario skips there with an explicit reason instead of pretending to pass.
"""

from __future__ import annotations

import json
import os
import pathlib
from typing import Any

import pytest
import requests
from e2e_helpers import (
    ALLOW_SHARED_ENV,
    compose_container,
    host_config_dir,
    is_shared_dev_instance,
    restart_home_assistant,
    wait_for,
    wait_for_entry_loaded,
    wait_for_instance_ready,
    ws_command,
)

from scripts.e2e_bootstrap import _headers, ensure_person

pytestmark = pytest.mark.e2e

# Throwaway person, created through the real config flow and deleted in `finally`.
PERSON = "E2E-BpPersist"

# Synthetic values with a distinctive shape (no realistic patient data, no
# default values of the number entities, which start empty anyway).
SYS, DIA, PULSE = 137, 89, 73

# `unique_id` keys of the entities involved (entity.py: `{entry_id}_{key}`).
INPUT_KEYS = ("number_input_sys", "number_input_dia", "number_input_pulse")
SAVE_KEY = "button_save_reading"
HISTORY_KEY = "sensor_bp_history"

# Import-time guard, not a fixture: this module stops the instance, and pytest
# may build session fixtures before any module fixture runs.
if (
    is_shared_dev_instance(os.environ.get("HASS_BASE_URL", "http://localhost:8123"))
    and os.environ.get(ALLOW_SHARED_ENV) != "1"
):
    pytest.skip(
        "test_input_persistence_e2e restarts the instance — it refuses to run"
        " against the shared dev instance (loopback:8123). Point HASS_BASE_URL at"
        " the Compose stack (E2E_HA_PORT, default 8124) or set"
        f" {ALLOW_SHARED_ENV}=1 if that really is a throwaway stack.",
        allow_module_level=True,
    )


# --- helpers ---------------------------------------------------------------


def _state(base_url: str, token: str, entity_id: str) -> dict[str, Any] | None:
    """One entity state, or None when the entity is not in the state machine."""
    response = requests.get(
        f"{base_url}/api/states/{entity_id}", headers=_headers(token), timeout=30
    )
    if response.status_code == 404:
        return None
    response.raise_for_status()
    return response.json()


def _number_value(base_url: str, token: str, entity_id: str) -> float | None:
    """The numeric state of a number entity, or None while it is empty."""
    state = _state(base_url, token, entity_id)
    if state is None:
        return None
    try:
        return float(state["state"])
    except (TypeError, ValueError):
        return None


def _call_service(
    base_url: str, token: str, domain: str, service: str, data: dict[str, Any]
) -> None:
    """Call a real HA service (the path a user or automation triggers)."""
    response = requests.post(
        f"{base_url}/api/services/{domain}/{service}",
        headers=_headers(token),
        json=data,
        timeout=60,
    )
    response.raise_for_status()


def _entity_ids(base_url: str, token: str, entry_id: str) -> dict[str, str]:
    """`unique_id -> entity_id` of one config entry's entities."""
    registry = ws_command(base_url, token, {"type": "config/entity_registry/list"}) or []
    return {
        str(row["unique_id"]): str(row["entity_id"])
        for row in registry
        if row.get("config_entry_id") == entry_id
    }


def _wait_entity_ids(
    base_url: str, token: str, entry_id: str, keys: tuple[str, ...]
) -> dict[str, str]:
    """Poll the registry until all `keys` (`{entry_id}_<key>`) are registered."""
    return wait_for(
        lambda: _entity_ids(base_url, token, entry_id),
        lambda mapping: {f"{entry_id}_{key}" for key in keys}.issubset(mapping),
        "the BP input entities to be registered",
    )


def _store_inputs(config_dir: pathlib.Path, entry_id: str) -> dict[str, Any]:
    """The persisted `inputs` dict of one person, read from the store document."""
    document = json.loads((config_dir / ".storage" / "health_o_mat").read_text(encoding="utf-8"))
    record = document["data"]["entries"].get(entry_id) or {}
    return record.get("inputs") or {}


def _delete_entry(base_url: str, token: str, entry_id: str) -> None:
    """Remove one config entry (idempotent cleanup)."""
    response = requests.delete(
        f"{base_url}/api/config/config_entries/entry/{entry_id}",
        headers=_headers(token),
        timeout=30,
    )
    if response.status_code not in (200, 404):
        response.raise_for_status()


# --- test ------------------------------------------------------------------


def test_req_hom_104_half_filled_bp_inputs_survive_restart(hass_base_url, hass_bearer_token):
    """[REQ-HOM-104] Half-filled BP inputs persist across a restart; saving clears both.

    Asserts four things:

    1. the three input entities accept the values and serve them back,
    2. the store document on disk holds exactly those three keys (persisted, not
       only held in memory),
    3. after a real container restart the values are still served by the same
       entities (and still in the store) — the entity-to-store wiring survived
       setup,
    4. pressing the save button creates exactly one reading and empties the
       store dict **and** the entity states.
    """
    container = compose_container(hass_base_url)
    config_dir = host_config_dir(hass_base_url)
    if container is None or config_dir is None:
        pytest.skip(
            "REQ-HOM-104 is a restart scenario: no Docker control or /config bind"
            " mount available (the Compose `e2e` runner container has neither)."
            " Run it from the host with HASS_BASE_URL=http://127.0.0.1:8124."
        )

    person = ensure_person(hass_base_url, hass_bearer_token, PERSON, enable_panel=False)
    entry_id = str(person["entry_id"])
    try:
        # The bootstrap saves the quick-drink set, which reloads the entry; the
        # input entities below are (re)built by that setup.
        wait_for_entry_loaded(hass_base_url, hass_bearer_token, entry_id)
        mapping = _wait_entity_ids(
            hass_base_url, hass_bearer_token, entry_id, (*INPUT_KEYS, SAVE_KEY, HISTORY_KEY)
        )
        input_ids = {key: mapping[f"{entry_id}_{key}"] for key in INPUT_KEYS}
        save_id = mapping[f"{entry_id}_{SAVE_KEY}"]
        history_id = mapping[f"{entry_id}_{HISTORY_KEY}"]

        # 1) Fill the capture through the entities a user operates.
        for key, value in zip(INPUT_KEYS, (SYS, DIA, PULSE), strict=True):
            _call_service(
                hass_base_url,
                hass_bearer_token,
                "number",
                "set_value",
                {"entity_id": input_ids[key], "value": value},
            )
        expected = {"sys": SYS, "dia": DIA, "pulse": PULSE}
        for key, value in zip(INPUT_KEYS, (SYS, DIA, PULSE), strict=True):
            wait_for(
                lambda key=key: _number_value(hass_base_url, hass_bearer_token, input_ids[key]),
                lambda current, value=value: current == value,
                f"the {key} input to serve the written value",
            )

        # 2) Persisted, not just held in memory.
        wait_for(
            lambda: _store_inputs(config_dir, entry_id),
            lambda inputs: inputs == expected,
            "the BP inputs in the store document",
        )

        # 3) Restart the whole instance and read the values back.
        restart_home_assistant(container, hass_base_url)
        wait_for_instance_ready(hass_base_url, hass_bearer_token, list(input_ids.values()))

        for key, value in zip(INPUT_KEYS, (SYS, DIA, PULSE), strict=True):
            served = _number_value(hass_base_url, hass_bearer_token, input_ids[key])
            assert served == value, (
                f"{input_ids[key]} lost its value across the restart: {served!r}"
            )
        assert _store_inputs(config_dir, entry_id) == expected

        # 4) Saving consumes the input: one reading, empty store, empty entities.
        _call_service(hass_base_url, hass_bearer_token, "button", "press", {"entity_id": save_id})
        wait_for(
            lambda: _store_inputs(config_dir, entry_id),
            lambda inputs: not inputs,
            "the BP inputs to be cleared after saving",
        )
        history = wait_for(
            lambda: _state(hass_base_url, hass_bearer_token, history_id),
            lambda state: state is not None and float(state["state"]) == 1,
            "the saved reading to show up in the BP history sensor",
        )
        assert float(history["state"]) == 1
        readings = json.loads(history["attributes"]["history_json"])
        assert len(readings) == 1, readings
        saved = readings[0]
        assert (saved["sys"], saved["dia"], saved["pulse"]) == (SYS, DIA, PULSE), saved

        for key in INPUT_KEYS:
            served = _number_value(hass_base_url, hass_bearer_token, input_ids[key])
            assert served is None, f"{input_ids[key]} still serves {served!r} after saving"
    finally:
        _delete_entry(hass_base_url, hass_bearer_token, entry_id)

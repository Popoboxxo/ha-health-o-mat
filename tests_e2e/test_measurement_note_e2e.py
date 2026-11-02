"""E2E: measurement note input (REQ-HOM-010) against a real Home Assistant.

The note is an *input field* of the blood-pressure capture, not a data object
of its own: it lives in the person's persisted ``store.inputs["note"]``
(REQ-HOM-104), is consumed by the save button as the reading's ``note`` and is
visible afterwards in the BP history sensor (``history_json``) and in the
blood-pressure CSV (column ``notiz``). None of that exists outside a running
instance — the entity, the store round-trip, the coordinator refresh and the
CSV writer only exist at runtime — so this module drives the real Compose
stack (``docker-compose.e2e.yml``, host port 8124) through its own API.

Every scenario step is asserted against the *served* data, never against the
test's own input:

* the entity registry (``unique_id`` = ``{entry_id}_text_measurement_note``,
  English-pinned ``entity_id``) and the state machine (localized friendly name),
* the reading that the save button wrote (``history_json`` of the BP history
  sensor), including the independent second save that proves the pending note
  was really cleared instead of merely not rendered,
* the readings written by the ``add_blood_pressure`` *service* (the same
  store write through a different entry point): the pending note is used when
  the call omits ``note``, an explicit ``note`` always wins over it, and the
  pending note is consumed in both cases,
* the exported CSV file itself (header + ``notiz`` column),
* the area gate: disabling ``bp`` takes the entity out of service, re-enabling
  it brings back the *same* registry entry (no re-registration).

Deliberate scope notes:

* Each test owns one throwaway person created through the real config flow and
  removes it again in ``finally`` (same helper as ``test_entity_ids_e2e``), so
  repeated runs stay independent and the shared instance does not accumulate
  persons.
* The note is asserted as a plain value without ``;`` — the BP CSV is
  semicolon-separated, so a note containing the delimiter would prove nothing
  about column placement.
* The exported file is read from the host bind mount
  (``docker/ha_config_e2e/health_o_mat_export/``). The containerized E2E runner
  has no ``/config`` mount, so the CSV test skips there with an explicit reason
  instead of pretending to pass.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest
import requests
from e2e_helpers import wait_for, ws_command
from test_entity_ids_e2e import _delete_entry

from scripts.e2e_bootstrap import _headers, _ws_command, ensure_person, set_person_options

pytestmark = pytest.mark.e2e

DOMAIN = "health_o_mat"
NOTE_KEY = "text_measurement_note"
NOTE = "morgens nach dem Aufstehen"
EXPLICIT_NOTE = "nach dem Training"
SYS, DIA, PULSE = 128, 84, 67
ALL_AREAS = {"drink": True, "bp": True, "wellbeing": True}
BP_OFF = {"drink": True, "bp": False, "wellbeing": True}

# Throwaway persons: one per test, created via the real config flow and
# deleted again in the teardown, so no test depends on another one's leftovers.
PERSON_FLOW = "E2E-NoteFlow"
PERSON_SAVE = "E2E-NoteSave"
PERSON_STATE = "E2E-NoteState"
PERSON_CSV = "E2E-NoteCsv"
PERSON_TOGGLE = "E2E-NoteToggle"
PERSON_SERVICE = "E2E-NoteService"
PERSON_SERVICE_EXPLICIT = "E2E-NoteExplicit"

_REPO_ROOT = Path(__file__).resolve().parents[1]
_TRANSLATIONS = _REPO_ROOT / "custom_components" / "health_o_mat" / "translations"
# Host view of HA's `/config` (bind mount in docker-compose.e2e.yml).
_EXPORT_DIR = _REPO_ROOT / "docker" / "ha_config_e2e" / "health_o_mat_export"


# --- helpers ---------------------------------------------------------------


def _state(base_url: str, token: str, entity_id: str) -> dict[str, Any] | None:
    """One entity state, or ``None`` when the entity is not in the state machine."""
    response = requests.get(
        f"{base_url}/api/states/{entity_id}", headers=_headers(token), timeout=30
    )
    if response.status_code == 404:
        return None
    response.raise_for_status()
    return response.json()


def _call_service(
    base_url: str,
    token: str,
    domain: str,
    service: str,
    data: dict[str, Any],
    *,
    return_response: bool = False,
) -> dict[str, Any]:
    """Call a real service through HA's REST API (the path a user triggers)."""
    url = f"{base_url}/api/services/{domain}/{service}"
    if return_response:
        url += "?return_response"
    response = requests.post(url, headers=_headers(token), json=data, timeout=60)
    response.raise_for_status()
    return response.json()


def _registry_entries(base_url: str, token: str, entry_id: str) -> list[dict[str, Any]]:
    """Entity-registry entries owned by one config entry."""
    registry = ws_command(base_url, token, {"type": "config/entity_registry/list"}) or []
    return [item for item in registry if item.get("config_entry_id") == entry_id]


def _note_registry_entry(base_url: str, token: str, entry_id: str) -> dict[str, Any]:
    """The measurement-note registry entry, polling until the platform registered it."""
    unique_id = f"{entry_id}_{NOTE_KEY}"
    entries = wait_for(
        lambda: _registry_entries(base_url, token, entry_id),
        lambda items: any(item.get("unique_id") == unique_id for item in items),
        "the measurement note entity to be registered",
    )
    matches = [item for item in entries if item.get("unique_id") == unique_id]
    assert len(matches) == 1, f"expected exactly one registry entry, got {matches!r}"
    return matches[0]


def _entity_ids(base_url: str, token: str, entry_id: str) -> dict[str, str]:
    """`unique_id -> entity_id` of one config entry's entities."""
    return {
        str(item["unique_id"]): str(item["entity_id"])
        for item in _registry_entries(base_url, token, entry_id)
    }


def _wait_entity_ids(base_url: str, token: str, entry_id: str, keys: set[str]) -> dict[str, str]:
    """Poll the registry until all `keys` (`{entry_id}_<key>`) are registered."""
    return wait_for(
        lambda: _entity_ids(base_url, token, entry_id),
        lambda mapping: {f"{entry_id}_{key}" for key in keys}.issubset(mapping),
        "entity registry entries of the fresh person",
    )


def _fresh_person(base_url: str, token: str, name: str) -> dict[str, Any]:
    """Create one person through the real config flow with the BP area active."""
    return ensure_person(base_url, token, name, enable_panel=False, areas=dict(ALL_AREAS))


def _instance_language(base_url: str, token: str) -> str:
    config = _ws_command(base_url, token, {"type": "get_config"}) or {}
    return str(config.get("language") or "")


def _translated_note_name(language: str) -> str:
    """The entity name HA renders for `language` (the system language, not ours)."""
    path = _TRANSLATIONS / f"{language}.json"
    if not path.is_file():
        path = _TRANSLATIONS.parent / "strings.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    return str(data["entity"]["text"]["measurement_note"]["name"])


def _slug(text: str) -> str:
    """HA's object-id slug (`Health-O-Mat X` -> `health_o_mat_x`)."""
    return re.sub(r"_+", "_", re.sub(r"[^a-z0-9]+", "_", text.lower())).strip("_")


def _history(base_url: str, token: str, entity_id: str) -> list[dict[str, Any]]:
    state = _state(base_url, token, entity_id)
    assert state is not None, f"{entity_id} is not in the state machine"
    return json.loads(state["attributes"]["history_json"])


def _fill_and_save(
    base_url: str, token: str, entity_ids: dict[str, str], entry_id: str, note: str | None
) -> None:
    """Set the pending note (optionally) and save a reading via the real button."""
    if note is not None:
        _call_service(
            base_url,
            token,
            "text",
            "set_value",
            {"entity_id": entity_ids[f"{entry_id}_{NOTE_KEY}"], "value": note},
        )
    inputs = {
        "number_input_sys": SYS,
        "number_input_dia": DIA,
        "number_input_pulse": PULSE,
    }
    for key, value in inputs.items():
        _call_service(
            base_url,
            token,
            "number",
            "set_value",
            {"entity_id": entity_ids[f"{entry_id}_{key}"], "value": value},
        )
    _call_service(
        base_url,
        token,
        "button",
        "press",
        {"entity_id": entity_ids[f"{entry_id}_button_save_reading"]},
    )


def _set_pending_note(
    base_url: str, token: str, entity_ids: dict[str, str], entry_id: str, note: str
) -> None:
    """Write the pending note through the entity and wait until it is served."""
    note_id = entity_ids[f"{entry_id}_{NOTE_KEY}"]
    _call_service(base_url, token, "text", "set_value", {"entity_id": note_id, "value": note})
    wait_for(
        lambda: _state(base_url, token, note_id),
        lambda value: value is not None and value["state"] == note,
        "the pending note to be stored by the text entity",
        timeout=10,
    )


def _add_blood_pressure(
    base_url: str, token: str, person_slug: str, *, note: str | None = None
) -> None:
    """Save a reading through the `add_blood_pressure` service (no button involved)."""
    data: dict[str, Any] = {
        "person": person_slug,
        "systolic": SYS,
        "diastolic": DIA,
        "pulse": PULSE,
    }
    if note is not None:
        data["note"] = note
    _call_service(base_url, token, DOMAIN, "add_blood_pressure", data)


def _assert_note_field_empty(base_url: str, token: str, entity_id: str) -> None:
    """The pending-note entity must read back empty after a reading was stored."""
    state = _state(base_url, token, entity_id)
    assert state is not None
    assert state["state"] in ("", "unknown"), (
        f"note field must be empty after saving, got {state['state']!r}"
    )


# --- tests -----------------------------------------------------------------


def test_req_hom_010_measurement_note_entity_identity(hass_base_url, hass_bearer_token):
    """[REQ-HOM-010] Note entity: stable unique_id, English entity_id, localized name."""
    person = _fresh_person(hass_base_url, hass_bearer_token, PERSON_FLOW)
    entry_id = str(person["entry_id"])
    try:
        entry = _note_registry_entry(hass_base_url, hass_bearer_token, entry_id)
        device_slug = _slug(f"Health-O-Mat {person['person_slug']}")
        expected_entity_id = f"text.{device_slug}_measurement_note"

        assert entry["unique_id"] == f"{entry_id}_{NOTE_KEY}"
        assert entry["entity_id"] == expected_entity_id, (
            f"entity_id {entry['entity_id']!r} is not the English-pinned object id"
        )
        assert entry["entity_id"].isascii()

        language = _instance_language(hass_base_url, hass_bearer_token)
        expected_name = _translated_note_name(language)
        assert entry["original_name"] == expected_name, (
            f"language={language!r}: original_name {entry['original_name']!r}"
            f" != translation {expected_name!r}"
        )

        state = wait_for(
            lambda: _state(hass_base_url, hass_bearer_token, entry["entity_id"]),
            lambda value: value is not None,
            "the measurement note entity state",
        )
        assert state["attributes"]["friendly_name"] == (
            f"Health-O-Mat {person['person_slug']} {expected_name}"
        )
    finally:
        _delete_entry(hass_base_url, hass_bearer_token, entry_id)


def test_req_hom_010_note_visible_in_entity_after_set_value(hass_base_url, hass_bearer_token):
    """[REQ-HOM-010] Setting the note through the entity updates the entity state."""
    person = _fresh_person(hass_base_url, hass_bearer_token, PERSON_STATE)
    entry_id = str(person["entry_id"])
    try:
        entry = _note_registry_entry(hass_base_url, hass_bearer_token, entry_id)
        _call_service(
            hass_base_url,
            hass_bearer_token,
            "text",
            "set_value",
            {"entity_id": entry["entity_id"], "value": NOTE},
        )
        state = wait_for(
            lambda: _state(hass_base_url, hass_bearer_token, entry["entity_id"]),
            lambda value: value is not None and value["state"] == NOTE,
            "the note entity to show the pending note after text.set_value",
            timeout=10,
        )
        assert state["state"] == NOTE
    finally:
        _delete_entry(hass_base_url, hass_bearer_token, entry_id)


def test_req_hom_010_save_consumes_note_and_clears_it(hass_base_url, hass_bearer_token):
    """[REQ-HOM-010] The save button attaches the note and consumes it."""
    person = _fresh_person(hass_base_url, hass_bearer_token, PERSON_SAVE)
    entry_id = str(person["entry_id"])
    try:
        entity_ids = _wait_entity_ids(
            hass_base_url,
            hass_bearer_token,
            entry_id,
            {
                NOTE_KEY,
                "number_input_sys",
                "number_input_dia",
                "number_input_pulse",
                "button_save_reading",
                "sensor_bp_history",
            },
        )
        history_id = entity_ids[f"{entry_id}_sensor_bp_history"]

        _fill_and_save(hass_base_url, hass_bearer_token, entity_ids, entry_id, NOTE)
        readings = wait_for(
            lambda: _history(hass_base_url, hass_bearer_token, history_id),
            lambda items: any(item.get("note") == NOTE for item in items),
            "the saved reading to carry the pending note",
        )
        reading = next(item for item in readings if item.get("note") == NOTE)
        assert (reading["sys"], reading["dia"], reading["pulse"]) == (SYS, DIA, PULSE)

        note_state = _state(hass_base_url, hass_bearer_token, entity_ids[f"{entry_id}_{NOTE_KEY}"])
        assert note_state is not None
        assert note_state["state"] in ("", "unknown"), (
            f"note field must be empty after saving, got {note_state['state']!r}"
        )

        # Independent proof that the note was *consumed*, not just not rendered:
        # a second save without touching the note must carry an empty note.
        before = len(readings)
        _fill_and_save(hass_base_url, hass_bearer_token, entity_ids, entry_id, None)
        after = wait_for(
            lambda: _history(hass_base_url, hass_bearer_token, history_id),
            lambda items: len(items) > before,
            "the second reading to appear",
        )
        second = after[-1]
        assert second.get("note") == "", (
            f"second reading still carries note {second.get('note')!r} —"
            " the pending note was not cleared on save"
        )
    finally:
        _delete_entry(hass_base_url, hass_bearer_token, entry_id)


def test_req_hom_010_service_uses_pending_note(hass_base_url, hass_bearer_token):
    """[REQ-HOM-010] `add_blood_pressure` without `note` uses the entity's pending note."""
    person = _fresh_person(hass_base_url, hass_bearer_token, PERSON_SERVICE)
    entry_id = str(person["entry_id"])
    try:
        entity_ids = _wait_entity_ids(
            hass_base_url,
            hass_bearer_token,
            entry_id,
            {NOTE_KEY, "sensor_bp_history"},
        )
        note_id = entity_ids[f"{entry_id}_{NOTE_KEY}"]
        history_id = entity_ids[f"{entry_id}_sensor_bp_history"]

        _set_pending_note(hass_base_url, hass_bearer_token, entity_ids, entry_id, NOTE)

        # No `note` in the service call: the pending note must be picked up.
        _add_blood_pressure(hass_base_url, hass_bearer_token, str(person["person_slug"]))
        readings = wait_for(
            lambda: _history(hass_base_url, hass_bearer_token, history_id),
            lambda items: any(item.get("note") == NOTE for item in items),
            "the service-written reading to carry the pending note",
        )
        reading = next(item for item in readings if item.get("note") == NOTE)
        assert (reading["sys"], reading["dia"], reading["pulse"]) == (SYS, DIA, PULSE)
        assert reading["src"] == "service", (
            f"reading came from {reading['src']!r}, not from the service path"
        )

        _assert_note_field_empty(hass_base_url, hass_bearer_token, note_id)
    finally:
        _delete_entry(hass_base_url, hass_bearer_token, entry_id)


def test_req_hom_010_service_explicit_note_wins(hass_base_url, hass_bearer_token):
    """[REQ-HOM-010] An explicit `note` on the service call beats the pending note."""
    person = _fresh_person(hass_base_url, hass_bearer_token, PERSON_SERVICE_EXPLICIT)
    entry_id = str(person["entry_id"])
    try:
        entity_ids = _wait_entity_ids(
            hass_base_url,
            hass_bearer_token,
            entry_id,
            {NOTE_KEY, "sensor_bp_history"},
        )
        note_id = entity_ids[f"{entry_id}_{NOTE_KEY}"]
        history_id = entity_ids[f"{entry_id}_sensor_bp_history"]

        _set_pending_note(hass_base_url, hass_bearer_token, entity_ids, entry_id, NOTE)

        _add_blood_pressure(
            hass_base_url,
            hass_bearer_token,
            str(person["person_slug"]),
            note=EXPLICIT_NOTE,
        )
        readings = wait_for(
            lambda: _history(hass_base_url, hass_bearer_token, history_id),
            lambda items: any(item.get("note") == EXPLICIT_NOTE for item in items),
            "the service-written reading to carry the explicit note",
        )
        reading = next(item for item in readings if item.get("note") == EXPLICIT_NOTE)
        assert reading["src"] == "service", (
            f"reading came from {reading['src']!r}, not from the service path"
        )
        assert all(item.get("note") != NOTE for item in readings), (
            f"the pending note leaked into a reading: {readings!r}"
        )

        # The pending note is consumed even though it lost against the explicit one.
        _assert_note_field_empty(hass_base_url, hass_bearer_token, note_id)
    finally:
        _delete_entry(hass_base_url, hass_bearer_token, entry_id)


def test_req_hom_010_note_in_blood_pressure_csv(hass_base_url, hass_bearer_token):
    """[REQ-HOM-010] The note reaches the exported blood-pressure CSV (`notiz`)."""
    person = _fresh_person(hass_base_url, hass_bearer_token, PERSON_CSV)
    entry_id = str(person["entry_id"])
    try:
        entity_ids = _wait_entity_ids(
            hass_base_url,
            hass_bearer_token,
            entry_id,
            {
                NOTE_KEY,
                "number_input_sys",
                "number_input_dia",
                "number_input_pulse",
                "button_save_reading",
                "sensor_bp_history",
            },
        )
        _fill_and_save(hass_base_url, hass_bearer_token, entity_ids, entry_id, NOTE)
        wait_for(
            lambda: _history(
                hass_base_url, hass_bearer_token, entity_ids[f"{entry_id}_sensor_bp_history"]
            ),
            lambda items: any(item.get("note") == NOTE for item in items),
            "the saved reading to carry the pending note",
        )

        result = _call_service(
            hass_base_url,
            hass_bearer_token,
            DOMAIN,
            "export_csv",
            {"dataset": "blood_pressure", "person": person["person_slug"]},
            return_response=True,
        )
        payload = result["service_response"]
        assert payload["rows"] >= 1, payload

        path = _EXPORT_DIR / str(payload["filename"])
        if not path.is_file():
            pytest.skip(
                f"exported CSV {path} is not reachable from this runner — the"
                " containerized E2E image has no /config bind mount"
            )
        try:
            lines = [
                line for line in path.read_text(encoding="utf-8-sig").splitlines() if line.strip()
            ]
            assert lines[0] == "zeitstempel;person;systolisch;diastolisch;puls;notiz"
            cells = next(
                row.split(";")
                for row in lines[1:]
                if row.split(";")[1] == person["person_slug"] and row.split(";")[5] == NOTE
            )
            assert cells[2:5] == [str(SYS), str(DIA), str(PULSE)], cells
        finally:
            try:
                path.unlink()
            except OSError:
                # HA creates /config/health_o_mat_export as root when it does not
                # exist yet; the host user cannot remove the file in that case.
                pass
    finally:
        _delete_entry(hass_base_url, hass_bearer_token, entry_id)


def test_req_hom_010_note_entity_follows_bp_area_toggle(hass_base_url, hass_bearer_token):
    """[REQ-HOM-010] Disabling `bp` takes the entity out of service; re-enabling restores it."""
    person = _fresh_person(hass_base_url, hass_bearer_token, PERSON_TOGGLE)
    entry_id = str(person["entry_id"])
    try:
        before = _note_registry_entry(hass_base_url, hass_bearer_token, entry_id)
        entity_id = str(before["entity_id"])
        wait_for(
            lambda: _state(hass_base_url, hass_bearer_token, entity_id),
            lambda value: value is not None,
            "the note entity state",
        )

        set_person_options(
            hass_base_url, hass_bearer_token, entry_id, enable_panel=False, areas=dict(BP_OFF)
        )
        wait_for(
            lambda: _state(hass_base_url, hass_bearer_token, entity_id),
            lambda value: value is None or value["state"] == "unavailable",
            "the note entity to leave service while the bp area is disabled",
        )

        set_person_options(
            hass_base_url, hass_bearer_token, entry_id, enable_panel=False, areas=dict(ALL_AREAS)
        )
        state = wait_for(
            lambda: _state(hass_base_url, hass_bearer_token, entity_id),
            lambda value: value is not None and value["state"] != "unavailable",
            "the note entity to come back when the bp area is re-enabled",
        )
        assert state is not None

        after = _note_registry_entry(hass_base_url, hass_bearer_token, entry_id)
        assert after["unique_id"] == before["unique_id"]
        assert after["entity_id"] == before["entity_id"], (
            "re-enabling the area registered a new entity:"
            f" {before['entity_id']!r} -> {after['entity_id']!r}"
        )
        matches = [
            item
            for item in _registry_entries(hass_base_url, hass_bearer_token, entry_id)
            if item.get("unique_id") == f"{entry_id}_{NOTE_KEY}"
        ]
        assert len(matches) == 1, f"duplicate registrations: {matches!r}"
    finally:
        _delete_entry(hass_base_url, hass_bearer_token, entry_id)

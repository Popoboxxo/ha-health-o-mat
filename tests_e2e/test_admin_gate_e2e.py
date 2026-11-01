"""E2E: the admin gate of the admin-only websocket commands (#28, REQ-HOM-013).

`custom_components/health_o_mat/ws_api.py` guards `get_settings`, `set_settings`,
`export_csv`, `import_csv`, `delete_person`, `backup`, … with
`connection.user.is_admin` (`ADMIN_ONLY_COMMANDS` + the explicit
`is_admin_connection` check inside each handler). That is an authorization
contract against a REAL Home Assistant user database: it can only fail/pass
against a user that genuinely lacks `is_admin`, i.e. a different user than the
instance owner minted by onboarding.

So this module needs a non-admin HA user. It is created idempotently by
`scripts.e2e_bootstrap.ensure_non_admin_user` via HA's own admin-only
`config/auth/create` websocket command (group `system-users`, see the
`non_admin` fixture in conftest.py) and logged in through the normal password
login — no test-only path, no mocked permission layer.

Three properties are asserted, and only together do they prove the gate:

1. the fixture user really is not an admin (not a badly created second owner),
2. every command in `ws_api.ADMIN_ONLY_COMMANDS` answers `unauthorized` (an
   explicit error code, not a timeout and not a schema/`invalid_format` answer),
3. regular commands still work for the same user — otherwise "unauthorized"
   could simply mean the account cannot do anything at all,

plus an admin control proving the same command does succeed with an admin token
(otherwise a globally broken command would look like a working gate).
"""

from __future__ import annotations

import json
import time
from typing import Any

import pytest
from e2e_helpers import ws_command
from websockets.sync.client import connect
from ws_api_catalog import admin_only_commands

from scripts.e2e_bootstrap import _ws_url

pytestmark = pytest.mark.e2e

# HA's websocket error code for "the caller is not allowed to do this"
# (`websocket_api.const.ERR_UNAUTHORIZED`); the integration mirrors it in
# `_send_unauthorized`, so both gates (HA's `require_admin` wrapper and the
# handler's own check) answer with exactly this code.
UNAUTHORIZED = "unauthorized"

WS_TIMEOUT = 30.0

# The catalog is read from `ws_api.py` itself (parsed, not imported: the E2E
# runner image has no Home Assistant package). Membership in ADMIN_ONLY_COMMANDS
# is what makes `async_register_ws_api` wrap a handler in HA's `require_admin`,
# so the set *is* the gate definition — no command can be forgotten here without
# the coverage test below failing.
ADMIN_ONLY_COMMANDS: dict[str, str] = admin_only_commands()

# Placeholders filled per test run: the configured fixture person and an
# entry_id that exists nowhere.
FIXTURE_ENTRY = "{entry_id}"
UNKNOWN_ENTRY = "{unknown_entry_id}"

# One SCHEMA-VALID payload per admin-only command: HA validates the message
# schema BEFORE the handler runs, so an invalid payload would answer
# `invalid_format` and hide whether the permission check works. Every payload is
# additionally inert — even with a MISSING gate it could not mutate anything:
# read-only commands, a bogus export dataset, import/restore files that do not
# exist and a delete confirmation/entry that cannot match. That keeps
# `delete_person` in the live gate test instead of dropping it.
ADMIN_ONLY_CALLS: dict[str, dict[str, Any]] = {
    "COMMAND_GET_SETTINGS": {"entry_id": FIXTURE_ENTRY},
    "COMMAND_SET_SETTINGS": {"entry_id": FIXTURE_ENTRY},
    "COMMAND_EXPORT_CSV": {"dataset": "e2e-not-an-export-dataset"},
    "COMMAND_BACKUP": {},
    "COMMAND_LIST_IMPORT_FILES": {},
    "COMMAND_RESTORE_BACKUP": {
        "filename": "e2e-nonadmin-restore-does-not-exist.json",
        "dry_run": True,
    },
    "COMMAND_IMPORT_CSV": {
        "entry_id": FIXTURE_ENTRY,
        "filename": "e2e-nonadmin-import-does-not-exist.csv",
    },
    "COMMAND_DELETE_PERSON": {
        # Unknown person + mismatching confirmation: the handler answers
        # `not_found` before it could remove anything.
        "entry_id": UNKNOWN_ENTRY,
        "confirm": "e2e-confirmation-cannot-match",
    },
}

# Commands that are NOT executed: `start_person_flow` takes no parameters, so
# there is no inert payload — a call would actually start a config flow if the
# gate ever failed. For those the gate definition itself is asserted (the
# coverage test below); they can never be missing from ADMIN_ONLY_COMMANDS
# silently.
EXECUTION_FREE_COMMANDS: frozenset[str] = frozenset({"COMMAND_START_PERSON_FLOW"})

UNKNOWN_ENTRY_VALUE = "e2e-entry-that-does-not-exist"


def _ws_exchange(
    base_url: str, token: str, payload: dict[str, Any], *, timeout: float = WS_TIMEOUT
) -> dict[str, Any]:
    """Send ONE websocket command and return the raw answer (result or error).

    Unlike `scripts.e2e_bootstrap._ws_command` this does not raise on an error
    answer — the error code is the assertion subject here. A missing answer is
    reported as a failure with the command name: an admin command that hangs
    must never be mistaken for "rejected".
    """
    deadline = time.monotonic() + timeout
    with connect(_ws_url(base_url), open_timeout=timeout, close_timeout=5) as socket:
        hello = json.loads(socket.recv(timeout))
        assert hello.get("type") == "auth_required", f"unexpected greeting: {hello}"
        socket.send(json.dumps({"type": "auth", "access_token": token}))
        auth = json.loads(socket.recv(timeout))
        assert auth.get("type") == "auth_ok", f"websocket authentication failed: {auth}"

        socket.send(json.dumps({"id": 1, **payload}))
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                pytest.fail(
                    f"no answer within {timeout:g}s for {payload['type']!r} — "
                    "a timeout is NOT a rejection"
                )
            message = json.loads(socket.recv(remaining))
            if message.get("id") == 1:
                return message


def _admin_only_payload(constant: str, entry_id: str) -> dict[str, Any]:
    """Fill the placeholders of `ADMIN_ONLY_CALLS[constant]` for one fixture run."""
    payload: dict[str, Any] = {"type": ADMIN_ONLY_COMMANDS[constant]}
    for key, value in ADMIN_ONLY_CALLS[constant].items():
        if isinstance(value, str):
            payload[key] = value.replace(FIXTURE_ENTRY, entry_id).replace(
                UNKNOWN_ENTRY, UNKNOWN_ENTRY_VALUE
            )
        else:
            payload[key] = value
    return payload


def test_req_hom_013_non_admin_fixture_user_has_no_admin_rights(non_admin):
    """[REQ-HOM-013] The gate is only meaningful with a genuinely non-admin user."""
    assert non_admin["is_admin"] is False, (
        "the bootstrap derives is_admin from config/auth/list groups — a True "
        f"here means the fixture user really is an admin: {non_admin['group_ids']}"
    )
    assert "system-admin" not in non_admin["group_ids"], (
        f"the E2E gate user must not be in the admin group: {non_admin['group_ids']}"
    )
    assert non_admin["username"], "the non-admin fixture needs a username"
    assert non_admin["token"], "the non-admin fixture needs a working access token"


@pytest.mark.parametrize("constant", sorted(ADMIN_ONLY_CALLS), ids=sorted(ADMIN_ONLY_CALLS))
def test_req_hom_013_admin_only_command_is_rejected_for_non_admin(
    hass_base_url, non_admin, panel_person, constant
):
    """[REQ-HOM-013] Non-admin → `unauthorized`, for every admin-only command."""
    payload = _admin_only_payload(constant, panel_person["entry_id"])
    command = payload["type"]
    message = _ws_exchange(hass_base_url, non_admin["token"], payload)

    assert message.get("success") is False, (
        f"{command} was NOT rejected for the non-admin user {non_admin['username']!r}: {message}"
    )
    error = message.get("error") or {}
    assert error.get("code") == UNAUTHORIZED, (
        f"{command} must answer {UNAUTHORIZED!r} for a non-admin user, "
        f"got error={error!r} — a different code means the rejection came from "
        "schema validation or a broken command, not from the permission gate"
    )


def test_req_hom_013_every_admin_only_command_is_covered():
    """[REQ-HOM-013] The parametrization covers the whole catalog, not a subset.

    Guards the intent of #28: a command added to `ADMIN_ONLY_COMMANDS` has to be
    classified here (executed with an inert payload, or explicitly
    execution-free) instead of silently disappearing from the suite.
    """
    covered = set(ADMIN_ONLY_CALLS) | EXECUTION_FREE_COMMANDS
    assert covered == set(ADMIN_ONLY_COMMANDS), (
        "ADMIN_ONLY_COMMANDS and the E2E coverage drifted apart — "
        f"uncovered: {sorted(set(ADMIN_ONLY_COMMANDS) - covered)}, "
        f"unknown: {sorted(covered - set(ADMIN_ONLY_COMMANDS))}"
    )
    assert EXECUTION_FREE_COMMANDS.isdisjoint(ADMIN_ONLY_CALLS), (
        "a command cannot be both executed and execution-free"
    )


def test_req_hom_013_non_admin_can_still_use_regular_commands(
    hass_base_url, non_admin, panel_person
):
    """[REQ-HOM-013] Positive control: everyday (non-gated) commands keep working.

    Without this control, `unauthorized` above could simply mean "this account
    may do nothing at all" — the gate would look correct while the user is
    locked out of the product.
    """
    result = ws_command(
        hass_base_url,
        non_admin["token"],
        {"type": "health_o_mat/panel_data", "entry_id": panel_person["entry_id"]},
    )

    assert isinstance(result, dict) and result, f"empty panel_data payload: {result!r}"
    assert result.get("entry_id") == panel_person["entry_id"]
    assert result.get("person_slug") == panel_person["slug"]

    # A second, read-only command outside the admin catalog: `list_history` is
    # the everyday entry point for corrections and must stay usable as well.
    history = ws_command(
        hass_base_url,
        non_admin["token"],
        {
            "type": "health_o_mat/list_history",
            "entry_id": panel_person["entry_id"],
            "kind": "drinks",
            "limit": 5,
        },
    )

    assert history.get("kind") == "drinks", f"unexpected list_history payload: {history!r}"
    assert isinstance(history.get("entries"), list), (
        f"list_history must return an entries list, got: {history!r}"
    )


def test_req_hom_013_admin_control_reaches_the_admin_only_command(
    hass_base_url, hass_bearer_token, panel_person
):
    """[REQ-HOM-013] Admin control: the same command succeeds with an admin token.

    A command that fails for everybody would make the rejection assertions
    above pass for the wrong reason.
    """
    result = ws_command(
        hass_base_url,
        hass_bearer_token,
        {"type": "health_o_mat/get_settings", "entry_id": panel_person["entry_id"]},
    )

    assert isinstance(result, dict) and result, f"empty get_settings payload: {result!r}"

"""E2E: the diagnostics download for one person (REQ-HOM-105).

REQ-HOM-105 asks for a diagnostics download that carries versions, entity ids,
options and counters — and **no** health values, no person names and no raw
timestamps. The unit suite (``tests/test_diagnostics.py:101-711``) proves that
for ``redact_diagnostics`` in isolation; this module proves it for the artifact a
user actually uploads: HA's own ``GET /api/diagnostics/config_entry/<entry_id>``
view, which wraps our redacted payload in HA's diagnostics envelope and is
served with admin-only authorization.

Two things can only fail here, never in a unit test:

* the **wiring** — a platform file that does not expose
  ``async_get_config_entry_diagnostics`` returns HA's "no diagnostics" answer
  instead of our payload, and an entry that never reached ``async_setup_entry``
  would answer with an empty store,
* the **authorization** — the admin gate of the view against a real non-admin
  account (the onboarding owner is always admin).

The person is created through the real config flow and filled with *distinctive*
values (337 ml, 137/89/73 mmHg, a note and a drink label) so every "must not
appear" assertion measures something that really is in the store. Those values
are synthetically chosen, not copied from any real record.
"""

from __future__ import annotations

import json
import os
import pathlib
import re
from typing import Any

import pytest
import requests
from e2e_helpers import ALLOW_SHARED_ENV, is_shared_dev_instance, wait_for

from scripts.e2e_bootstrap import _headers, ensure_person

pytestmark = pytest.mark.e2e

DOMAIN = "health_o_mat"

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
MANIFEST = REPO_ROOT / "custom_components" / "health_o_mat" / "manifest.json"

# Throwaway persons (one per test, deleted again in `finally`).
PERSON_DIAG = "E2E-Diag"
PERSON_GATE = "E2E-DiagGate"

# Synthetic health data with values that cannot collide with a counter, a
# schema version or an option (counters stay in the single digits).
AMOUNT_ML = 337
DRINK_TYPE = "Diagnose-Probe"
SYSTOLIC = 137
DIASTOLIC = 89
PULSE = 73
NOTE = "diagnose-probe-notiz"

#: A raw timestamp like ``2026-11-03T12:34`` — the diagnostics download must not
#: contain one (only the store schema/version integers and counters are allowed).
_ISO_TIMESTAMP = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}")

# Import-time guard: the person fixtures write into the instance, and the
# diagnostics payload is assembled from whatever a shared instance already
# holds (other projects' persons would end up in the same store file). Same
# refusal pattern as `test_blueprints_e2e.py`.
if (
    is_shared_dev_instance(os.environ.get("HASS_BASE_URL", "http://localhost:8123"))
    and os.environ.get(ALLOW_SHARED_ENV) != "1"
):
    pytest.skip(
        "test_diagnostics_e2e creates persons and reads their diagnostics — it"
        " refuses to run against the shared dev instance (loopback:8123)."
        " Point HASS_BASE_URL at the Compose stack (E2E_HA_PORT, default 8124)"
        f" or set {ALLOW_SHARED_ENV}=1 if that really is a throwaway stack.",
        allow_module_level=True,
    )


def _call_service(base_url: str, token: str, service: str, data: dict[str, Any]) -> dict[str, Any]:
    """Call one `health_o_mat/*` service (the path a user or automation uses)."""
    response = requests.post(
        f"{base_url}/api/services/{DOMAIN}/{service}",
        headers=_headers(token),
        json=data,
        timeout=60,
    )
    response.raise_for_status()
    return response.json()


def _diagnostics(base_url: str, token: str, entry_id: str) -> requests.Response:
    """HA's own per-entry diagnostics view (the URL offered by the UI)."""
    return requests.get(
        f"{base_url}/api/diagnostics/config_entry/{entry_id}",
        headers=_headers(token),
        timeout=60,
    )


def _manifest_version() -> str:
    """`manifest.version` of the integration under test (the mounted source)."""
    return str(json.loads(MANIFEST.read_text(encoding="utf-8"))["version"])


def _numbers(value: Any) -> list[float]:
    """Every numeric leaf of a JSON document (for the "no health value" check)."""
    if isinstance(value, bool):
        return []
    if isinstance(value, (int, float)):
        return [value]
    if isinstance(value, dict):
        return [number for item in value.values() for number in _numbers(item)]
    if isinstance(value, list):
        return [number for item in value for number in _numbers(item)]
    return []


def _delete_entry(base_url: str, token: str, entry_id: str) -> None:
    """Remove one config entry (idempotent cleanup)."""
    response = requests.delete(
        f"{base_url}/api/config/config_entries/entry/{entry_id}",
        headers=_headers(token),
        timeout=30,
    )
    if response.status_code not in (200, 404):
        response.raise_for_status()


def test_req_hom_105_diagnostics_download_is_valid_json_and_redacted(
    hass_base_url, hass_bearer_token
):
    """[REQ-HOM-105] Admin download: valid JSON, versions/options/counters, no health data.

    The assertions mirror ``tests/test_diagnostics.py:101-711`` on the real
    artifact: the allow-list keys are present with the running version, and
    every value the person actually stored (amount, sys/dia/pulse, note, drink
    label, display name) is absent.
    """
    person = ensure_person(
        hass_base_url,
        hass_bearer_token,
        PERSON_DIAG,
        enable_panel=False,
    )
    entry_id = str(person["entry_id"])
    try:
        _call_service(
            hass_base_url,
            hass_bearer_token,
            "add_drink",
            {
                "person": PERSON_DIAG,
                "amount_ml": AMOUNT_ML,
                "drink_type": DRINK_TYPE,
            },
        )
        _call_service(
            hass_base_url,
            hass_bearer_token,
            "add_blood_pressure",
            {
                "person": PERSON_DIAG,
                "systolic": SYSTOLIC,
                "diastolic": DIASTOLIC,
                "pulse": PULSE,
                "note": NOTE,
            },
        )
        _call_service(
            hass_base_url,
            hass_bearer_token,
            "set_wellbeing",
            {"person": PERSON_DIAG, "status": "poor"},
        )

        # The counters are read from the store, so wait until the writes landed
        # instead of racing them (a 0 would make the redaction check vacuous).
        def _counters() -> dict[str, int]:
            response = _diagnostics(hass_base_url, hass_bearer_token, entry_id)
            response.raise_for_status()
            return response.json()["data"]["counters"]

        wait_for(
            _counters,
            lambda counters: counters["drinks"] >= 1 and counters["readings"] >= 1,
            "the diagnostics counters to reflect the stored health data",
        )

        response = _diagnostics(hass_base_url, hass_bearer_token, entry_id)
        assert response.status_code == 200, response.text
        assert response.headers.get("content-type", "").startswith("application/json")
        body = response.json()  # raises if the download is not valid JSON
        data = body["data"]

        # --- allow-list: versions, options, counters, entity ids -------------
        assert set(data) == {
            "integration",
            "config_entry",
            "store",
            "entities",
            "lab_entity_orphans",
            "options",
            "counters",
        }, sorted(data)
        assert data["integration"] == {
            "domain": DOMAIN,
            "version": _manifest_version(),
        }, data["integration"]
        assert data["config_entry"]["version"] == 3, data["config_entry"]
        assert data["store"]["available"] is True, data["store"]
        assert isinstance(data["store"]["schema_version"], int)
        assert data["counters"]["drinks"] == 1, data["counters"]
        assert data["counters"]["readings"] == 1, data["counters"]
        assert data["counters"]["drinks_active"] == 1, data["counters"]
        assert data["counters"]["readings_active"] == 1, data["counters"]
        assert data["entities"], "the entity list must not be empty for a set-up entry"
        # Entity ids only: no state, no attribute and no raw registry row.
        assert all("." in entity and " " not in entity for entity in data["entities"])
        assert sorted(data["entities"]) == data["entities"], "entity list is not sorted"

        # --- redaction: person name, health values, note, raw timestamps -----
        assert data["config_entry"]["person"] == "***", data["config_entry"]
        # `person_display` carries the display name in `entry.options`; other
        # options are allowed verbatim (they are configuration, not measurements).
        assert data["options"].get("person_display") == "***", data["options"]

        whole = json.dumps(body, ensure_ascii=False)
        for forbidden in (PERSON_DIAG, NOTE, DRINK_TYPE):
            assert forbidden not in whole, f"{forbidden!r} leaked into the diagnostics download"

        # Numeric health values: checked on `data` only — HA's surrounding
        # envelope (`setup_times`) legitimately contains arbitrary floats.
        stored = {AMOUNT_ML, SYSTOLIC, DIASTOLIC, PULSE}
        leaked = stored.intersection(int(number) for number in _numbers(data))
        assert not leaked, f"health values leaked into the diagnostics payload: {sorted(leaked)}"

        assert not _ISO_TIMESTAMP.search(json.dumps(data, ensure_ascii=False)), (
            "a raw timestamp leaked into the diagnostics payload"
        )
    finally:
        _delete_entry(hass_base_url, hass_bearer_token, entry_id)


def test_req_hom_105_diagnostics_download_rejects_non_admin(
    hass_base_url, hass_bearer_token, non_admin
):
    """[REQ-HOM-105] The per-entry diagnostics view is admin-only (real non-admin user).

    The download is the most sensitive endpoint of the integration (it is meant
    to be pasted into a public issue), so the gate is asserted against an
    account that genuinely lacks ``is_admin`` — not against the onboarding owner.
    """
    assert non_admin["is_admin"] is False, non_admin["group_ids"]

    person = ensure_person(
        hass_base_url,
        hass_bearer_token,
        PERSON_GATE,
        enable_panel=False,
    )
    entry_id = str(person["entry_id"])
    try:
        # Control: the admin token does reach the view (otherwise 401 for the
        # non-admin could simply mean the view does not exist).
        assert _diagnostics(hass_base_url, hass_bearer_token, entry_id).status_code == 200

        denied = _diagnostics(hass_base_url, non_admin["token"], entry_id)
        assert denied.status_code == 401, denied.text
        assert "data" not in denied.text
    finally:
        _delete_entry(hass_base_url, hass_bearer_token, entry_id)

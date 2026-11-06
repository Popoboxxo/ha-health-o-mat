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
from e2e_helpers import (
    ALLOW_SHARED_ENV,
    call_service,
    is_shared_dev_instance,
    wait_for,
    wait_for_entry_loaded,
    ws_command,
)

from scripts.e2e_bootstrap import _headers, ensure_person

pytestmark = pytest.mark.e2e

DOMAIN = "health_o_mat"

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
MANIFEST = REPO_ROOT / "custom_components" / "health_o_mat" / "manifest.json"

# Throwaway persons (one per test, deleted again in `finally`).
PERSON_DIAG = "E2E-Diag"
PERSON_GATE = "E2E-DiagGate"
PERSON_UNITS = "E2E-DiagUnits"
PERSON_UNITS_LEGACY = "E2E-DiagUnitsLegacy"

# REQ-HOM-134 display units: a catalog marker (public key) plus a custom
# marker whose slug is derived from the free-text name (must never leak).
CATALOG_MARKER_KEY = "creatinine"
CUSTOM_MARKER_NAME = "E2E Slug Probe"
CUSTOM_MARKER_UNIT = "nmol/L"
DEFAULT_UNITS = {CATALOG_MARKER_KEY: "mg/dL"}

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


def _settings(base_url: str, token: str, entry_id: str) -> dict[str, Any]:
    """The authoritative settings payload (`health_o_mat/get_settings`)."""
    result = ws_command(
        base_url, token, {"type": "health_o_mat/get_settings", "entry_id": entry_id}
    )
    return result or {}


def _set_settings(base_url: str, token: str, entry_id: str, **payload: Any) -> dict[str, Any]:
    """`health_o_mat/set_settings` (admin) and the full settings payload back."""
    return (
        ws_command(
            base_url,
            token,
            {"type": "health_o_mat/set_settings", "entry_id": entry_id, **payload},
        )
        or {}
    )


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
        # `ensure_person` saves the quick-drink set through the options flow, and
        # that save reloads the entry (REQ-HOM-101 AK1). Until the reload is done
        # the person is not resolvable, so every service call below would answer
        # "Person '...' nicht gefunden".
        wait_for_entry_loaded(hass_base_url, hass_bearer_token, entry_id)
        call_service(
            hass_base_url,
            hass_bearer_token,
            DOMAIN,
            "add_drink",
            {
                "person": PERSON_DIAG,
                "amount_ml": AMOUNT_ML,
                "drink_type": DRINK_TYPE,
            },
            entry_id=entry_id,
        )
        call_service(
            hass_base_url,
            hass_bearer_token,
            DOMAIN,
            "add_blood_pressure",
            {
                "person": PERSON_DIAG,
                "systolic": SYSTOLIC,
                "diastolic": DIASTOLIC,
                "pulse": PULSE,
                "note": NOTE,
            },
            entry_id=entry_id,
        )
        call_service(
            hass_base_url,
            hass_bearer_token,
            DOMAIN,
            "set_wellbeing",
            {"person": PERSON_DIAG, "status": "poor"},
            entry_id=entry_id,
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
        # The bootstrap's options save reloads the entry; the download is only
        # meaningful once it is set up again (same gate as the admin test).
        wait_for_entry_loaded(hass_base_url, hass_bearer_token, entry_id)
        # Control: the admin token does reach the view (otherwise 401 for the
        # non-admin could simply mean the view does not exist).
        assert _diagnostics(hass_base_url, hass_bearer_token, entry_id).status_code == 200

        denied = _diagnostics(hass_base_url, non_admin["token"], entry_id)
        assert denied.status_code == 401, denied.text
        assert "data" not in denied.text
    finally:
        _delete_entry(hass_base_url, hass_bearer_token, entry_id)


# --- REQ-HOM-134 display units (§12.4) --------------------------------------


def test_req_hom_134_diagnostics_default_units_are_count_only(hass_base_url, hass_bearer_token):
    """[REQ-HOM-134/F1] §12.4 Nr.1: `lab_default_units` is a counter, slug never leaks.

    The override map mixes a catalog marker (public key) with a custom marker
    whose slug is derived from free text (potentially a diagnosis). The
    diagnostics download may expose only the entry count — not the marker keys
    and not the custom slug — anywhere in the serialized payload.
    """
    person = ensure_person(
        hass_base_url,
        hass_bearer_token,
        PERSON_UNITS,
        enable_panel=False,
    )
    entry_id = str(person["entry_id"])
    try:
        wait_for_entry_loaded(hass_base_url, hass_bearer_token, entry_id)

        # Start from a clean lab-options state, then create exactly one custom
        # marker. Clearing first keeps repeated runs from accumulating markers.
        _set_settings(
            hass_base_url,
            hass_bearer_token,
            entry_id,
            lab_custom_markers=[],
            lab_default_units={},
        )
        wait_for_entry_loaded(hass_base_url, hass_bearer_token, entry_id)
        _set_settings(
            hass_base_url,
            hass_bearer_token,
            entry_id,
            lab_custom_markers=[
                {
                    "name": CUSTOM_MARKER_NAME,
                    "unit": CUSTOM_MARKER_UNIT,
                    "category": "other",
                }
            ],
        )
        wait_for_entry_loaded(hass_base_url, hass_bearer_token, entry_id)

        settings = wait_for(
            lambda: _settings(hass_base_url, hass_bearer_token, entry_id),
            lambda value: any(
                marker.get("name") == CUSTOM_MARKER_NAME
                for marker in value.get("lab_custom_markers") or []
            ),
            "the custom marker to be persisted before setting its display unit",
        )
        slug = next(
            str(marker["key"])
            for marker in settings["lab_custom_markers"]
            if marker.get("name") == CUSTOM_MARKER_NAME
        )
        assert slug != CATALOG_MARKER_KEY, slug

        expected = {**DEFAULT_UNITS, slug: CUSTOM_MARKER_UNIT}
        _set_settings(
            hass_base_url,
            hass_bearer_token,
            entry_id,
            lab_default_units=expected,
        )
        wait_for(
            lambda: _settings(hass_base_url, hass_bearer_token, entry_id),
            lambda value: value.get("lab_default_units") == expected,
            "both display-unit overrides (catalog marker + custom slug) to persist",
        )

        response = _diagnostics(hass_base_url, hass_bearer_token, entry_id)
        assert response.status_code == 200, response.text
        body = response.json()
        data = body["data"]

        assert data["options"]["lab_default_units"] == {"count": 2}, data["options"]

        blob = json.dumps(body, ensure_ascii=False)
        assert slug not in blob, (
            f"the custom marker slug {slug!r} leaked into the diagnostics download"
        )
        assert CUSTOM_MARKER_NAME not in blob, (
            f"the custom marker name {CUSTOM_MARKER_NAME!r} leaked into the diagnostics download"
        )
    finally:
        _delete_entry(hass_base_url, hass_bearer_token, entry_id)


def test_req_hom_134_diagnostics_legacy_entry_without_default_units(
    hass_base_url, hass_bearer_token
):
    """[REQ-HOM-134/F1] §12.4 Nr.2: a legacy entry reports zero overrides.

    A pre-feature entry has no `lab_default_units` option at all; the download
    must still succeed and report zero overrides (HA omits an unset option, so
    the observable contract is "absent or `{'count': 0}`"). Persisting an empty
    map (what an admin save of "all defaults" produces) then yields the literal
    `{'count': 0}` payload.
    """
    person = ensure_person(
        hass_base_url,
        hass_bearer_token,
        PERSON_UNITS_LEGACY,
        enable_panel=False,
    )
    entry_id = str(person["entry_id"])
    try:
        wait_for_entry_loaded(hass_base_url, hass_bearer_token, entry_id)

        # 1. Legacy entry: the option was never written. HA's options mapping
        # omits it, and diagnostics must not fail on that.
        response = _diagnostics(hass_base_url, hass_bearer_token, entry_id)
        assert response.status_code == 200, response.text
        options = response.json()["data"]["options"]
        assert options.get("lab_default_units", {"count": 0}) == {"count": 0}, options

        # 2. An explicitly empty override map (all defaults) is count-only, 0.
        _set_settings(
            hass_base_url,
            hass_bearer_token,
            entry_id,
            lab_default_units={},
        )
        wait_for(
            lambda: _settings(hass_base_url, hass_bearer_token, entry_id),
            lambda value: value.get("lab_default_units") == {},
            "the empty display-unit option to persist",
        )
        response = _diagnostics(hass_base_url, hass_bearer_token, entry_id)
        assert response.status_code == 200, response.text
        data = response.json()["data"]
        assert data["options"]["lab_default_units"] == {"count": 0}, data["options"]
    finally:
        _delete_entry(hass_base_url, hass_bearer_token, entry_id)

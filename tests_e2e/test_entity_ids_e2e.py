"""E2E: entity ids of a freshly registered person (REQ-HOM-130, A-4).

A-4 is the regression net for the `suggested_object_id` override: HA's
`platform_data` / `_name_internal` / `default_language_platform_translations`
are internal API, so only a real registration against a real instance proves
that object ids stay English/ASCII. The test never switches the instance
language (Spec §1.4) — it reads `hass.config.language` and asserts the same
language-independent contract either way.
"""

from __future__ import annotations

import pytest
import requests
from e2e_helpers import wait_for, ws_command

from scripts.e2e_bootstrap import _headers, ensure_person

pytestmark = pytest.mark.e2e

PERSON = "E2E-EntityIds"
PREFIX = "health_o_mat_e2e_entityids"

# Old, user-text derived ids that must never come back.
OLD_IDS = (
    f"button.{PREFIX}_glas_wasser",
    f"button.{PREFIX}_flasche_wasser",
    f"button.{PREFIX}_tasse_kaffee",
    f"button.{PREFIX}_glas_saft",
)

# `{unique_id suffix}` -> expected english `entity_id`. The unique ids are
# `{entry_id}_{key}` (`entity.HealthOMatEntity.__init__`).
EXPECTED_IDS = {
    "sensor_drinks_today": f"sensor.{PREFIX}_drinks_today",
    "binary_bp_warning": f"binary_sensor.{PREFIX}_blood_pressure_warning",
    "button_quick_0": f"button.{PREFIX}_quick_drink_1",
    "button_quick_3": f"button.{PREFIX}_quick_drink_4",
}


def _ws_result(base_url: str, token: str, payload: dict) -> object:
    return ws_command(base_url, token, payload)


def _registry_by_unique(base_url: str, token: str, entry_id: str) -> dict[str, str]:
    """`unique_id -> entity_id` of one config entry's entities."""
    registry = _ws_result(base_url, token, {"type": "config/entity_registry/list"})
    return {
        str(item["unique_id"]): str(item["entity_id"])
        for item in registry or []
        if item.get("config_entry_id") == entry_id
    }


def _delete_entry(base_url: str, token: str, entry_id: str) -> None:
    """Remove one config entry (and its entities/device).

    The store record of the entry survives (Spec §6.3 Phase 0c) — one small,
    empty record per run on the shared test instance, cleaned up by the next
    `bin/reset`/provision.
    """
    response = requests.delete(
        f"{base_url}/api/config/config_entries/entry/{entry_id}",
        headers=_headers(token),
        timeout=30,
    )
    if response.status_code not in (200, 404):
        response.raise_for_status()


def test_req_hom_131_fresh_person_gets_language_independent_entity_ids(
    hass_base_url, hass_bearer_token
):
    person = ensure_person(hass_base_url, hass_bearer_token, PERSON, enable_panel=False)
    entry_id = str(person["entry_id"])
    try:
        # The options write above reloads the entry, so the platforms register
        # asynchronously — poll for the expected entities instead of reading
        # once and racing the setup.
        by_unique = wait_for(
            lambda: _registry_by_unique(hass_base_url, hass_bearer_token, entry_id),
            lambda registry: {f"{entry_id}_{key}" for key in EXPECTED_IDS}.issubset(registry),
            "entity registry entries of the fresh person",
        )
        language = _ws_result(hass_base_url, hass_bearer_token, {"type": "get_config"}).get(
            "language"
        )

        # 1) Language independent, English/ASCII ids (the actual A-4 assertion).
        #    The quick-drink slots are pinned to the index (A-5), not the label.
        for key, expected in EXPECTED_IDS.items():
            actual = by_unique[f"{entry_id}_{key}"]
            assert actual == expected, f"language={language!r}: {key} registered as {actual!r}"

        # 2) No localized / label-derived ids exist for this person.
        existing = set(by_unique.values())
        assert not existing.intersection(OLD_IDS), sorted(existing.intersection(OLD_IDS))
        assert not any(
            entity_id.endswith(("_heute_getrunken", "_blutdruck_warnung")) for entity_id in existing
        )
    finally:
        _delete_entry(hass_base_url, hass_bearer_token, entry_id)

"""E2E: backdating + history/void/restore in the panel (REQ-HOM-115/120).

The panel is a shadow-DOM web component; these flows only exist at runtime.
The test uses data attributes (language-agnostic) and reads back the
authoritative ``health_o_mat/list_history`` payload.
"""

from __future__ import annotations

import pytest
from e2e_helpers import ws_command
from test_card_config_e2e import CARD_TIMEOUT, _panel_data, _wait_for
from test_panel_deeplink_e2e import open_panel, wait_for_detail

pytestmark = pytest.mark.e2e

DRINK_TAB = ".tab[data-tab='drink']"
DRINK_TS_YESTERDAY = "[data-action='drink-ts-yesterday']"
QUICK_DRINK = "[data-action='book']"


def _history(base_url: str, token: str, entry_id: str, *, include_voided: bool) -> list[dict]:
    result = ws_command(
        base_url,
        token,
        {
            "type": "health_o_mat/list_history",
            "entry_id": entry_id,
            "kind": "drinks",
            "include_voided": include_voided,
        },
    )
    return (result or {}).get("entries") or []


def _new_drink(base_url: str, token: str, entry_id: str, before_ids: set[str]) -> dict | None:
    return next(
        (
            entry
            for entry in _history(base_url, token, entry_id, include_voided=True)
            if entry.get("id") not in before_ids
        ),
        None,
    )


def test_req_hom_115_120_panel_backdates_then_voids_and_restores(
    logged_in_page, hass_base_url, hass_bearer_token, tab_person
):
    """[REQ-HOM-115/120] A yesterday drink does not count today; it can be voided/restored."""
    entry_id = tab_person["entry_id"]

    before = _panel_data(hass_base_url, hass_bearer_token, entry_id)
    before_today = float((before.get("today") or {}).get("ml") or 0)
    before_ids = {
        entry["id"]
        for entry in _history(hass_base_url, hass_bearer_token, entry_id, include_voided=True)
    }

    panel = open_panel(logged_in_page, hass_base_url, person=tab_person["slug"])
    wait_for_detail(panel)
    panel.locator(DRINK_TAB).click()
    panel.locator(DRINK_TS_YESTERDAY).wait_for(state="visible", timeout=CARD_TIMEOUT)
    panel.locator(DRINK_TS_YESTERDAY).click()
    panel.locator(QUICK_DRINK).first.click()

    entry = _wait_for(
        lambda: _new_drink(hass_base_url, hass_bearer_token, entry_id, before_ids),
        lambda value: value is not None,
        "the backdated drink to appear in list_history",
    )
    assert entry["voided_at"] is None
    assert entry["ts"] != entry["created_at"], "the drink must keep the selected timestamp"

    after = _panel_data(hass_base_url, hass_bearer_token, entry_id)
    after_today = float((after.get("today") or {}).get("ml") or 0)
    assert after_today == before_today, "a yesterday drink must not count in today's total"

    row = panel.locator(f"li.history-item[data-history-id='{entry['id']}']")
    row.wait_for(state="visible", timeout=CARD_TIMEOUT)
    row.locator("[data-action='history-void']").click()
    row.locator("[data-action='history-void-confirm']").click()

    voided = _wait_for(
        lambda: next(
            (
                item
                for item in _history(
                    hass_base_url, hass_bearer_token, entry_id, include_voided=True
                )
                if item.get("id") == entry["id"]
            ),
            None,
        ),
        lambda value: value is not None and bool(value.get("voided_at")),
        "the drink to be voided",
    )
    assert voided["id"] == entry["id"]

    # The default filter shows active entries only; switch to "include deleted"
    # so the voided row and its restore action stay visible.
    panel.locator("[data-action='history-filter'][data-kind='drinks'][data-voided='1']").click()

    row.locator("[data-action='history-restore']").wait_for(state="visible", timeout=CARD_TIMEOUT)
    row.locator("[data-action='history-restore']").click()

    restored = _wait_for(
        lambda: next(
            (
                item
                for item in _history(
                    hass_base_url, hass_bearer_token, entry_id, include_voided=True
                )
                if item.get("id") == entry["id"]
            ),
            None,
        ),
        lambda value: value is not None and not value.get("voided_at"),
        "the drink to be restored",
    )
    assert restored["id"] == entry["id"]

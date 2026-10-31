"""E2E: confirmation before a wellbeing report (REQ-HOM-114).

Two independent switches share the same name:

* the panel/server option ``wellbeing_confirm`` per config entry (edited in
  the admin settings view),
* the Lovelace card's own ``wellbeing_confirm`` config option.

Both are verified here against a real Home Assistant instance in a real
browser: a staged selection must not reach the server until the confirmation
button is clicked, and the button must only exist while a selection is staged.
"""

from __future__ import annotations

import time

import pytest
from e2e_helpers import ws_command
from test_card_config_e2e import (
    CARD_TIMEOUT,
    _open_card,
    _panel_data,
    _wait_for,
    card_dashboard,  # noqa: F401 - re-exported pytest fixture
)
from test_panel_deeplink_e2e import open_panel

pytestmark = pytest.mark.e2e

WB_BUTTON = ".wb-btn[data-key='good']"
WB_CONFIRM = "[data-action='wellbeing-confirm']"
PANEL_WB_CONFIRM = "[data-action='wb-confirm']"
SETTINGS_CHECKBOX = "[data-field='wellbeing_confirm']"


def _set_wellbeing_status(base_url: str, token: str, entry_id: str, key: str) -> None:
    ws_command(
        base_url,
        token,
        {"type": "health_o_mat/set_wellbeing", "entry_id": entry_id, "key": key},
    )


def _set_confirm_option(base_url: str, token: str, entry_id: str, value: bool) -> None:
    ws_command(
        base_url,
        token,
        {
            "type": "health_o_mat/set_settings",
            "entry_id": entry_id,
            "wellbeing_confirm": value,
        },
    )


def _wait_for_status(base_url: str, token: str, entry_id: str, key: str) -> None:
    _wait_for(
        lambda: _panel_data(base_url, token, entry_id),
        lambda value: (value.get("wellbeing") or {}).get("key") == key,
        f"panel_data.wellbeing.key to become {key!r}",
        timeout=15.0,
    )


def test_req_hom_114_card_stages_until_confirmed(
    card_dashboard,  # noqa: F811 - pytest fixture
    logged_in_page,
    hass_base_url,
    hass_bearer_token,
    panel_person,
):
    """[REQ-HOM-114] The card option gates the report behind a confirm button."""
    entry_id = panel_person["entry_id"]
    _set_wellbeing_status(hass_base_url, hass_bearer_token, entry_id, "bad")
    _wait_for_status(hass_base_url, hass_bearer_token, entry_id, "bad")

    card_dashboard.save_card(
        entry_id,
        show_hydration=False,
        show_drinks=False,
        show_manual_amounts=False,
        show_undo=False,
        show_blood_pressure=False,
        show_blood_pressure_input=False,
        wellbeing_confirm=True,
    )
    card = _open_card(logged_in_page, card_dashboard, panel_person["display_name"])

    card.locator(".wb-btn[data-key='bad'][aria-pressed='true']").wait_for(
        state="visible", timeout=CARD_TIMEOUT
    )
    card.locator(WB_BUTTON).click()

    card.locator("[data-action='wellbeing-confirm']").wait_for(
        state="visible", timeout=CARD_TIMEOUT
    )
    assert card.locator(".wb-btn[data-key='good'].pending").count() == 1, (
        "the staged selection must be marked as pending"
    )
    assert "not reported yet" in card.locator(".wb-confirm").inner_text()

    time.sleep(1.2)
    payload = _panel_data(hass_base_url, hass_bearer_token, entry_id)
    assert (payload.get("wellbeing") or {}).get("key") == "bad", (
        "clicking a stage must not report it while confirmation is required"
    )

    card.locator(WB_CONFIRM).click()
    _wait_for_status(hass_base_url, hass_bearer_token, entry_id, "good")
    card.locator(WB_CONFIRM).wait_for(state="detached", timeout=CARD_TIMEOUT)
    card.locator(".wb-btn[data-key='good'][aria-pressed='true']").wait_for(
        state="visible", timeout=CARD_TIMEOUT
    )


def test_req_hom_114_panel_admin_option_controls_confirmation(
    logged_in_page, hass_base_url, hass_bearer_token, panel_person
):
    """[REQ-HOM-114] The per-person admin option is saved and used by the panel."""
    page = logged_in_page
    entry_id = panel_person["entry_id"]

    _set_confirm_option(hass_base_url, hass_bearer_token, entry_id, False)
    _set_wellbeing_status(hass_base_url, hass_bearer_token, entry_id, "bad")
    _wait_for_status(hass_base_url, hass_bearer_token, entry_id, "bad")

    try:
        panel = open_panel(page, hass_base_url, person=panel_person["slug"])
        panel.locator("[data-action='settings']").click()
        checkbox = panel.locator(SETTINGS_CHECKBOX)
        checkbox.wait_for(state="visible", timeout=CARD_TIMEOUT)
        assert not checkbox.is_checked(), "the default must stay off"

        checkbox.check()
        panel.locator("[data-save-button]").click()
        # Language-agnostic: the status text follows hass.language (en on this
        # instance); the authoritative check is the get_settings round-trip below.
        panel.locator(".settings-status.ok").wait_for(state="visible", timeout=CARD_TIMEOUT)

        settings = ws_command(
            hass_base_url,
            hass_bearer_token,
            {"type": "health_o_mat/get_settings", "entry_id": entry_id},
        )
        assert settings.get("wellbeing_confirm") is True, (
            f"the admin checkbox must persist the option, got {settings!r}"
        )

        panel = open_panel(page, hass_base_url, person=panel_person["slug"])
        panel.locator(".tab[data-tab='wellbeing']").click()
        panel.locator(WB_BUTTON).wait_for(state="visible", timeout=CARD_TIMEOUT)
        panel.locator(WB_BUTTON).click()

        panel.locator(PANEL_WB_CONFIRM).wait_for(state="visible", timeout=CARD_TIMEOUT)
        assert panel.locator(".wb-btn[data-key='good'].pending").count() == 1

        time.sleep(1.2)
        payload = _panel_data(hass_base_url, hass_bearer_token, entry_id)
        assert (payload.get("wellbeing") or {}).get("key") == "bad", (
            "the panel must not report while confirmation is required"
        )

        panel.locator(PANEL_WB_CONFIRM).click()
        _wait_for_status(hass_base_url, hass_bearer_token, entry_id, "good")
        panel.locator(PANEL_WB_CONFIRM).wait_for(state="detached", timeout=CARD_TIMEOUT)
    finally:
        _set_confirm_option(hass_base_url, hass_bearer_token, entry_id, False)

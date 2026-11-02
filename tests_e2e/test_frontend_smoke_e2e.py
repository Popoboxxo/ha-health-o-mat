"""E2E: frontend smoke test for card and panel (#31, REQ-HOM-014).

The panel and the card are vanilla-JS web components with no build step. A
broken import path, a cache-busting mismatch or a runtime exception in one of
the ES modules therefore does not fail any Python-side test — it only shows up
as a blank component (or a silently dead click handler) in a real browser.

This module is the cheapest possible net for exactly that class of defect:

* both components are loaded in a REAL browser against a REAL Home Assistant,
* `pageerror` (uncaught exception) and `console.error` are collected from the
  moment the component's page is opened — minus HA's own CSS pseudo-class
  deprecation notice, see `_HA_OWN_DEPRECATION_PREFIXES`,
* one stable DOM anchor per component has to be visible.

Deliberately NOT a screenshot/visual comparison: pixel diffs against HA's
frontend are flaky across versions and locales and would drown real JS
regressions in false positives. The contract verified here is "loads, renders,
throws nothing" — the component's behaviour is covered by the feature tests
(test_panel_deeplink_e2e.py, test_card_config_e2e.py, …).

The card needs a dashboard to live on, so the throwaway-dashboard fixture from
test_card_config_e2e.py is reused (one source of truth for dashboard creation
and teardown) instead of duplicating that plumbing.
"""

from __future__ import annotations

import pytest
from test_card_config_e2e import (
    CARD_TAG,
    CARD_TIMEOUT,
    card_dashboard,  # noqa: F401 - pytest fixture re-export
)

pytestmark = pytest.mark.e2e

PANEL_TAG = "health-o-mat-panel"
PANEL_PATH = "/health-o-mat"

# Stable structural anchors (see www/health-o-mat-panel.js `_html()`/`_topbarHtml()`
# and www/health-o-mat-card.js `_html()`): the panel renders a `.page` shell with
# a `.topbar`, the card a `ha-card > .hom` wrapper. Both exist from the first
# paint on and do not depend on the data payload.
PANEL_SHELL = ".page"
PANEL_TOPBAR = ".topbar"
CARD_ROOT = "ha-card .hom"

# The overview tiles only exist once `list_persons` answered — i.e. they prove
# the panel's own websocket bootstrap ran, not just that the element mounted.
OVERVIEW_TILE = ".tile[data-action='open']"

# Settle window after the visible anchor appears: console errors are delivered
# asynchronously (a rejected import, a failed `panel_data` call), so asserting
# immediately after the first paint would let late errors slip through. Not an
# assertion on timing — just the observation window.
SETTLE_MS = 500

# Home Assistant's OWN frontend ships CSS with the deprecated custom state
# pseudo-class syntax (`:--disabled`, `:--checked`, …) and the browser reports
# each use as a `console.error`. That noise is emitted by HA's bundle, not by
# ours — the contract verified here is "our components throw nothing", and a
# deprecation inside HA's frontend is not a defect in our code.
#
# Deliberately narrow: only this one exact message family is dropped. Every
# other `console.error` and EVERY `pageerror` (uncaught exception) still fails
# the test, so a real regression cannot hide behind this.
#
# Revisit when HA raises the deprecation to a hard error: the message then
# disappears (or turns into a genuine error), and a leftover allowlist entry
# would silently mask the very message it was written for.
_HA_OWN_DEPRECATION_PREFIXES = ("Custom state pseudo classes have been changed",)


def _is_known_ha_own_deprecation(text: str) -> bool:
    """True for HA's own CSS pseudo-class deprecation notice (see constant above)."""
    return text.startswith(_HA_OWN_DEPRECATION_PREFIXES)


def _collect_js_errors(page) -> list[str]:
    """Record uncaught exceptions and `console.error` messages of `page`."""
    errors: list[str] = []

    def _on_pageerror(exception) -> None:
        # Never filtered: an uncaught exception is always a defect.
        errors.append(f"pageerror: {exception}")

    def _on_console(message) -> None:
        if message.type != "error":
            return
        if _is_known_ha_own_deprecation(message.text):
            return
        errors.append(f"console.error: {message.text}")

    page.on("pageerror", _on_pageerror)
    page.on("console", _on_console)
    return errors


def _assert_no_js_errors(errors: list[str], component: str) -> None:
    assert not errors, f"{component} logged {len(errors)} JS error(s):\n" + "\n".join(errors)


def test_req_hom_014_panel_loads_without_javascript_errors(logged_in_page, hass_base_url):
    """[REQ-HOM-014] Panel mounts, renders its shell and raises nothing in the browser."""
    page = logged_in_page

    # Registered BEFORE navigating to the panel: module loading errors are
    # exactly what this test exists for.
    errors = _collect_js_errors(page)

    page.goto(f"{hass_base_url}{PANEL_PATH}")
    panel = page.locator(PANEL_TAG)
    panel.wait_for(state="attached", timeout=CARD_TIMEOUT)

    panel.locator(PANEL_SHELL).wait_for(state="visible", timeout=CARD_TIMEOUT)
    topbar = panel.locator(PANEL_TOPBAR)
    topbar.wait_for(state="visible", timeout=CARD_TIMEOUT)
    assert "Health-O-Mat" in topbar.inner_text()

    # The panel's own data path (imported ES modules + `list_persons`) must have
    # produced the overview, not just an empty shell.
    panel.locator(OVERVIEW_TILE).first.wait_for(state="visible", timeout=CARD_TIMEOUT)

    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(SETTLE_MS)
    _assert_no_js_errors(errors, "panel")


@pytest.fixture
def dashboard(request):
    """The throwaway Lovelace dashboard from test_card_config_e2e.py.

    Importing the fixture registers it in this module; resolving it through
    `request.getfixturevalue` keeps the wrapper's name distinct from the
    imported attribute (a same-named test argument would shadow the import and
    make the module look like it redefines its own fixture).
    """
    return request.getfixturevalue("card_dashboard")


def test_req_hom_014_card_loads_without_javascript_errors(dashboard, logged_in_page, panel_person):
    """[REQ-HOM-014] The Lovelace card renders on a real dashboard without JS errors."""
    page = logged_in_page
    dashboard.save_card(panel_person["entry_id"])

    errors = _collect_js_errors(page)

    page.goto(f"{dashboard.base_url}/{dashboard.url_path}")

    # Diagnosable failure instead of a bare locator timeout when the resource
    # did not register: Lovelace then renders its error card.
    page.locator(f"{CARD_TAG}, hui-error-card").first.wait_for(
        state="attached", timeout=CARD_TIMEOUT
    )
    if page.locator("hui-error-card").count():
        raise AssertionError(
            "Lovelace rendered hui-error-card instead of the Health-O-Mat card — "
            "the card resource is not registered (custom_components/health_o_mat/"
            f"frontend.py) or the integration is not loaded. URL: {page.url}"
        )

    card = page.locator(CARD_TAG)
    card.locator(CARD_ROOT).wait_for(state="visible", timeout=CARD_TIMEOUT)
    # `.head .name` only appears once `panel_data` answered — the card's own
    # websocket path, not just its markup.
    card.locator(".head .name", has_text=panel_person["display_name"]).wait_for(
        state="visible", timeout=CARD_TIMEOUT
    )

    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(SETTLE_MS)
    _assert_no_js_errors(errors, "card")

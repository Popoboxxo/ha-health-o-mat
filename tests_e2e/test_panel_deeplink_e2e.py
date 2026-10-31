"""E2E: the Health-O-Mat sidebar panel in a real browser (REQ-HOM-012).

The panel is a vanilla-JS web component with no build step and no Python-side
test surface, so a real browser against a real Home Assistant instance is the
only way to verify its behaviour at all: the `?person=<slug>` deep link, the
`history.pushState`/`popstate` round-trip and the tab rendering of the person
detail view.

Scope is deliberately narrow (deep link + panel mount + tab visibility); the
panel's WebSocket write paths are covered by tests/test_ws_api.py and
tests/test_panel_js.py.
"""

from __future__ import annotations

import re
from urllib.parse import parse_qs, urlparse

import pytest

pytestmark = pytest.mark.e2e

PANEL = "health-o-mat-panel"
PANEL_PATH = "/health-o-mat"

# Panel identity/contract anchors (custom_components/health_o_mat/panel.py and
# www/health-o-mat-panel-views.js): the overview renders one `.tile` button per
# person, the detail view a `.tabs` bar with one `.tab[data-tab]` per ENABLED
# feature area (drink / bp / wellbeing / labs).
TILE = ".tile[data-action='open']"
TAB = ".tab[data-action='tab']"


def open_panel(page, base_url: str, person: str | None = None):
    """Load the panel and wait for its custom element to be attached."""
    url = f"{base_url}{PANEL_PATH}"
    if person:
        url = f"{url}?person={person}"
    page.goto(url)
    panel = page.locator(PANEL)
    panel.wait_for(state="attached", timeout=60000)
    return panel


def person_param(page) -> str:
    """Current `person` query parameter ("" when absent)."""
    query = parse_qs(urlparse(page.url).query)
    return (query.get("person") or [""])[0]


def tile(panel, entry_id: str):
    return panel.locator(f"{TILE}[data-entry='{entry_id}']")


def tab_keys(panel) -> list[str]:
    """`data-tab` of every rendered tab, in DOM order."""
    tabs = panel.locator(TAB)
    return [tabs.nth(index).get_attribute("data-tab") for index in range(tabs.count())]


def wait_for_overview(panel) -> None:
    panel.locator(TILE).first.wait_for(state="visible", timeout=60000)


def wait_for_detail(panel) -> None:
    panel.locator(TAB).first.wait_for(state="visible", timeout=60000)


def test_panel_mounts_under_its_url_path(logged_in_page, hass_base_url):
    """The registered panel element really mounts at /health-o-mat."""
    page = logged_in_page
    panel = open_panel(page, hass_base_url)

    assert panel.count() == 1, "expected exactly one <health-o-mat-panel> element"
    panel.locator(".topbar").wait_for(state="visible", timeout=60000)
    assert "Health-O-Mat" in panel.locator(".topbar").inner_text()


def test_deep_link_opens_the_person_detail_directly(logged_in_page, hass_base_url, panel_person):
    """`/health-o-mat?person=<slug>` must land on the person page right away —
    no click, no tile, straight into the detail view with its tabs."""
    page = logged_in_page
    slug = panel_person["slug"]

    panel = open_panel(page, hass_base_url, person=slug)
    wait_for_detail(panel)

    assert person_param(page) == slug
    assert panel.locator(".person-head").inner_text().strip() == panel_person["display_name"]
    assert tab_keys(panel) == ["drink", "bp", "wellbeing", "labs"]


def test_tile_click_pushes_the_person_deep_link(logged_in_page, hass_base_url, panel_person):
    """Clicking a person tile pushes `?person=<slug>` onto the history.

    The `history.length` check is what distinguishes `pushState` (a new entry,
    the browser Back button returns to the overview) from `replaceState`
    (which would silently destroy the overview entry).
    """
    page = logged_in_page
    slug = panel_person["slug"]

    panel = open_panel(page, hass_base_url)
    wait_for_overview(panel)
    assert person_param(page) == "", "the overview must not address a person"

    history_before = page.evaluate("() => history.length")
    tile(panel, panel_person["entry_id"]).click()

    page.wait_for_url(re.compile(r"[?&]person="), timeout=60000)
    assert person_param(page) == slug
    wait_for_detail(panel)
    assert tab_keys(panel) == ["drink", "bp", "wellbeing", "labs"]
    assert page.evaluate("() => history.length") == history_before + 1, (
        "opening a person must push a history entry (pushState), not replace the URL"
    )


def test_browser_back_restores_the_overview(logged_in_page, hass_base_url, panel_person):
    """`popstate` must bring the overview back and drop the `person` param."""
    page = logged_in_page

    panel = open_panel(page, hass_base_url)
    wait_for_overview(panel)
    tile(panel, panel_person["entry_id"]).click()
    page.wait_for_url(re.compile(r"[?&]person="), timeout=60000)
    wait_for_detail(panel)

    page.go_back()
    page.wait_for_function("() => !window.location.search.includes('person=')", timeout=60000)

    wait_for_overview(panel)
    assert person_param(page) == ""
    assert tab_keys(panel) == [], "the overview has no tab bar (it is not a person page)"


def test_unknown_person_param_falls_back_safely(logged_in_page, hass_base_url):
    """An unknown/malformed deep link must never break the panel.

    The conftest's `reset_panel_selection` fixture already cleared the per-user
    "last opened person" the panel would otherwise resume, so the expected
    fallback is unambiguously the overview.
    """
    page = logged_in_page

    panel = open_panel(page, hass_base_url, person="does-not-exist-0f3a")
    wait_for_overview(panel)

    assert panel.locator(".msg.error").count() == 0
    assert panel.locator(".banner").count() == 0
    assert panel.locator(TILE).count() >= 2, "expected the overview for every person"
    assert tab_keys(panel) == []


def test_disabled_area_hides_its_tab(logged_in_page, hass_base_url, tab_person):
    """A switched-off feature area must not render its detail tab.

    `tab_person` disables exactly one area (`bp`); `labs` is not mentioned in
    its fixture options and is therefore enabled by default. The assertion is
    deliberately exhaustive — every enabled tab in order, including the
    default-on `labs` — so it still proves that the ONE disabled area is gone
    while its neighbours (and a sibling default area) survive. A weaker
    "bp not in tabs" check alone would also pass if the tab bar stopped
    rendering altogether.
    """
    page = logged_in_page

    panel = open_panel(page, hass_base_url, person=tab_person["slug"])
    wait_for_detail(panel)

    keys = tab_keys(panel)
    assert keys == ["drink", "wellbeing", "labs"], f"unexpected tab set: {keys!r}"
    assert "labs" in keys, "the default-enabled lab area must keep rendering its tab"
    assert panel.locator(".tab[data-tab='bp']").count() == 0

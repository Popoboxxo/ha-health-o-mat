"""E2E: UI internationalisation de/en (REQ-HOM-117).

The panel and the Lovelace card load their UI strings from Home Assistant's
own translation store (`frontend/get_translations`, category `common`). Both
are vanilla web components, so a real browser against a real HA instance is
the only way to verify that `hass.language` actually switches the rendered
labels.

`logged_in_page` runs with `locale=de-DE` (the existing German assertions stay
stable); `english_page` opens a second context with `locale=en-US` and is used
here. Server-side data labels (person names, configured quick-drink labels)
remain user data and are intentionally not asserted.
"""

from __future__ import annotations

import pytest
from test_card_config_e2e import CARD_TIMEOUT, _open_card, card_dashboard  # noqa: F401
from test_panel_deeplink_e2e import TAB, open_panel, wait_for_detail

pytestmark = pytest.mark.e2e

PANEL = "health-o-mat-panel"


def test_req_hom_117_panel_renders_english_labels(english_page, hass_base_url, panel_person):
    """[REQ-HOM-117] An en-US browser gets the English panel labels."""
    panel = open_panel(english_page, hass_base_url, person=panel_person["slug"])
    wait_for_detail(panel)

    tabs = panel.locator(TAB)
    labels = [tabs.nth(index).inner_text().strip() for index in range(tabs.count())]
    assert labels == ["Drinking", "Blood pressure", "Wellbeing"], (
        f"expected English tab labels, got {labels!r}"
    )
    # A couple of body labels follow the same translation source. The panel is a
    # shadow host, so read the rendered views container rather than the host.
    views = panel.locator(".views")
    views.locator(".muted", has_text="Quick add").wait_for(state="visible", timeout=CARD_TIMEOUT)
    body = views.inner_text()
    assert "Today" in body
    assert "Quick add" in body
    assert "History" in body
    assert "Heute" not in body
    assert "ui_" not in body, "raw translation key leaked into the UI"


def test_req_hom_117_card_renders_english_labels(
    english_page,
    card_dashboard,  # noqa: F811 - pytest fixture
    panel_person,
):
    """[REQ-HOM-117] An en-US browser gets the English card labels."""
    card_dashboard.save_card(
        panel_person["entry_id"],
        show_blood_pressure=False,
        show_blood_pressure_history=False,
        show_wellbeing=False,
        show_blood_pressure_input=False,
        show_wellbeing_input=False,
        show_drinks=False,
        show_manual_amounts=False,
        show_undo=False,
    )
    card = _open_card(english_page, card_dashboard, panel_person["display_name"])

    card.locator(".stat .k", has_text="Goal").wait_for(state="visible", timeout=CARD_TIMEOUT)
    stats = card.locator(".stat .k").all_inner_texts()
    assert "Goal" in stats, f"expected the English card label, got {stats!r}"
    assert "Ziel" not in stats
    assert "ui_" not in card.inner_text()

"""E2E: the configurable Health-O-Mat card (docs/PLAN-CARD-CONFIG.md).

The card is a vanilla web component: its configuration handling (`show_*` flags,
`drinks`, `manual_amounts`, BP/wellbeing inputs) exists only at runtime inside a
real Lovelace dashboard. These tests therefore create a THROWAWAY storage
dashboard through the Lovelace WebSocket API, put a single
`custom:health-o-mat-card` on it and drive the rendered card in a real browser
against a real Home Assistant instance.

The dashboard is created per test with a unique `url_path`
(``hom-card-e2e-<uuid>``, ``show_in_sidebar: false``) and deleted again in the
fixture teardown — also when the test fails — so repeated runs stay idempotent
and never depend on (or leave behind) pre-existing dashboards.

What is verified against the *served* data rather than against the test's own
input:

* (a) the `show_*` combinations really change the rendered DOM,
* (b) filling the blood-pressure form writes a real measurement — the store
  entry is read back from the ``bp_history`` sensor's ``history_json`` attribute
  (which keeps ``note``, the only public surface that exposes it) and from the
  ``health_o_mat/panel_data`` payload the card itself renders from,
* (c) clicking a wellbeing button changes ``panel_data.wellbeing.key`` and the
  UI (active button + display label). To make the UI change observable, the
  current status is first seeded server-side with the integration's own
  `health_o_mat/set_wellbeing` WebSocket command.

Documented gaps (deliberately NOT faked):

* Changing a card config is applied by re-saving the dashboard and loading the
  page fresh (most tests use one fresh config; `..._config_resave_is_applied`
  exercises the re-save path on the same dashboard). Lovelace *may* pick up a
  storage-dashboard config change live, but that is frontend-internal behaviour
  we do not want to depend on; the tests assert the card's rendering contract,
  not Lovelace's live-reload mechanism.
* The card resource itself is registered by the integration's frontend setup
  (`frontend.py`). If it is missing, the dashboard renders an `hui-error-card`
  instead of the card; `_open_card` fails with that diagnosis instead of
  silently skipping.
* ``note`` has no entity of its own — it is verified through the
  ``bp_history`` attribute, not through a dedicated sensor state.
"""

from __future__ import annotations

import json
import uuid
import warnings
from typing import Any

import pytest
import requests
from e2e_helpers import wait_for as _wait_for
from e2e_helpers import ws_command

from scripts.e2e_bootstrap import _ws_command

pytestmark = pytest.mark.e2e

CARD_TAG = "health-o-mat-card"
ENTRY_ID_KEY = "entry_id"

# The display/input switches of the card schema (docs/PLAN-CARD-CONFIG.md,
# `CARD_SHOW_KEYS` in www/health-o-mat-card.js).
SHOW_KEYS = (
    "show_person",
    "show_hydration",
    "show_blood_pressure",
    "show_blood_pressure_history",
    "show_wellbeing",
    "show_drinks",
    "show_manual_amounts",
    "show_blood_pressure_input",
    "show_wellbeing_input",
    "show_wellbeing_numeric",
    "show_undo",
)

ALL_OFF = dict.fromkeys(SHOW_KEYS, False)

# Markup anchors of the rendered card (inside its shadow root; Playwright CSS
# locators pierce open shadow DOM).
RING = ".ring"
ROW = ".row"
BP_INPUT_SYS = "[data-role='bp-sys']"
BP_SAVE = "[data-action='save-bp']"
WB_BUTTON = "[data-action='wellbeing']"

# Block emoji of the two display rows (`_bloodPressure` / `_wellbeing` in the
# card source). The `.row` class is only used by the display blocks, so the
# emoji makes the row unambiguous even when no measurement exists yet.
BP_DISPLAY_EMOJI = "\N{DROP OF BLOOD}"
WB_DISPLAY_EMOJI = "\N{SLIGHTLY SMILING FACE}"

# The write target of test (b) — values well inside the card's validation range.
BP_SYS = 137
BP_DIA = 86
BP_PULSE = 63

REST_TIMEOUT = 30
CARD_TIMEOUT = 60000


# --- small, dependency-light helpers ---------------------------------------


def _rest_state(base_url: str, token: str, entity_id: str) -> dict[str, Any]:
    """One entity state (REST) — used to read the persisted measurement back."""
    response = requests.get(
        f"{base_url}/api/states/{entity_id}",
        headers={"Authorization": f"Bearer {token}"},
        timeout=REST_TIMEOUT,
    )
    response.raise_for_status()
    return response.json()


def _panel_data(base_url: str, token: str, entry_id: str) -> dict[str, Any]:
    """The exact payload the card renders from (`health_o_mat/panel_data`)."""
    result = ws_command(base_url, token, {"type": "health_o_mat/panel_data", "entry_id": entry_id})
    return result or {}


def _last_reading_with_note(
    base_url: str, token: str, history_entity: str, note: str
) -> dict[str, Any] | None:
    """Newest stored reading carrying our unique note (None until it is there)."""
    state = _rest_state(base_url, token, history_entity)
    raw = (state.get("attributes") or {}).get("history_json") or "[]"
    try:
        readings = json.loads(raw)
    except ValueError:
        return None
    if not isinstance(readings, list):
        return None
    for reading in reversed(readings):
        if isinstance(reading, dict) and reading.get("note") == note:
            return reading
    return None


# --- dashboard fixture ------------------------------------------------------


class CardDashboard:
    """Handle of the throwaway dashboard created for one test."""

    def __init__(self, base_url: str, token: str, url_path: str, dashboard_id: str) -> None:
        self.base_url = base_url
        self.token = token
        self.url_path = url_path
        self.dashboard_id = dashboard_id

    def save_card(self, entry_id: str, **overrides: Any) -> None:
        """Put one Health-O-Mat card on the dashboard (replaces the view)."""
        card = {"type": "custom:health-o-mat-card", ENTRY_ID_KEY: entry_id, **overrides}
        _ws_command(
            self.base_url,
            self.token,
            {
                "type": "lovelace/config/save",
                "url_path": self.url_path,
                "config": {
                    "views": [
                        {
                            "path": "main",
                            "title": "Health-O-Mat card E2E",
                            "cards": [card],
                        }
                    ]
                },
            },
        )


@pytest.fixture
def card_dashboard(hass_base_url, hass_bearer_token) -> CardDashboard:
    """Create a unique storage dashboard and guarantee its deletion.

    `lovelace/dashboards/create` returns the collection item; deletion needs its
    `dashboard_id` (the generic storage-collection WebSocket API). The unique
    `url_path` keeps parallel/shared instances conflict-free; the teardown runs
    in a `finally` block so a failing test never leaks a dashboard.
    """
    url_path = f"hom-card-e2e-{uuid.uuid4().hex[:12]}"
    created = _ws_command(
        hass_base_url,
        hass_bearer_token,
        {
            "type": "lovelace/dashboards/create",
            "url_path": url_path,
            "title": "Health-O-Mat card E2E",
            "mode": "storage",
            "show_in_sidebar": False,
            "require_admin": False,
        },
    )
    dashboard = CardDashboard(hass_base_url, hass_bearer_token, url_path, str(created["id"]))
    try:
        yield dashboard
    finally:
        try:
            _ws_command(
                hass_base_url,
                hass_bearer_token,
                {"type": "lovelace/dashboards/delete", "dashboard_id": dashboard.dashboard_id},
            )
        except Exception as exc:  # noqa: BLE001 - teardown must not mask the test result
            warnings.warn(
                f"could not delete E2E dashboard {url_path!r} "
                f"(dashboard_id={dashboard.dashboard_id!r}): {exc} — delete it manually",
                RuntimeWarning,
                stacklevel=2,
            )


# --- browser helpers --------------------------------------------------------


def _open_card(page, dashboard: CardDashboard, display_name: str):
    """Load the dashboard and return the mounted, data-loaded card locator."""
    page.goto(f"{dashboard.base_url}/{dashboard.url_path}")

    # Either the card mounts, or Lovelace renders its error card (most likely a
    # missing custom-card resource). Waiting for both keeps the failure
    # diagnosable instead of a bare locator timeout.
    page.locator(f"{CARD_TAG}, hui-error-card").first.wait_for(
        state="attached", timeout=CARD_TIMEOUT
    )
    if page.locator("hui-error-card").count():
        raise AssertionError(
            "Lovelace rendered hui-error-card instead of the Health-O-Mat card — "
            "is the card resource registered (custom_components/health_o_mat/frontend.py) "
            f"and the integration loaded? URL: {page.url}"
        )

    card = page.locator(CARD_TAG)
    # The head is always rendered; the person name only appears once
    # `panel_data` has loaded, which is what every following assertion needs.
    card.locator(".head .name", has_text=display_name).wait_for(
        state="visible", timeout=CARD_TIMEOUT
    )
    return card


def _reload_card(page, dashboard: CardDashboard, display_name: str):
    """Re-open the dashboard after a config re-save (fresh server config)."""
    page.reload()
    card = page.locator(CARD_TAG)
    card.locator(".head .name", has_text=display_name).wait_for(
        state="visible", timeout=CARD_TIMEOUT
    )
    return card


# --- (a) show_* combinations ------------------------------------------------


def test_req_hom_113_card_all_blocks_off_shows_the_hint(
    card_dashboard, logged_in_page, panel_person
):
    """[REQ-HOM-113] All nine switches off → hint instead of blocks."""
    card_dashboard.save_card(panel_person["entry_id"], **ALL_OFF)
    card = _open_card(logged_in_page, card_dashboard, panel_person["display_name"])

    card.locator(".msg", has_text="No blocks enabled").wait_for(
        state="visible", timeout=CARD_TIMEOUT
    )
    assert card.locator(RING).count() == 0, "hydration ring must be hidden"
    assert card.locator(ROW).count() == 0, "no display rows must remain"
    assert card.locator(BP_INPUT_SYS).count() == 0, "BP input must be hidden"
    assert card.locator(WB_BUTTON).count() == 0, "wellbeing input must be hidden"
    assert card.locator("[data-action='book']").count() == 0, "drink buttons must be hidden"
    assert card.locator("[data-action='undo']").count() == 0, "undo must be hidden"


def test_req_hom_113_card_bp_display_off_hides_display_and_input(
    card_dashboard, logged_in_page, panel_person
):
    """[REQ-HOM-113] `show_blood_pressure: false` hides display AND (implicit) input.

    `show_blood_pressure_input` is deliberately NOT passed: the point of this
    test is the IMPLICIT follow rule (input follows the display flag when the
    input flag is absent). Passing it explicitly would prove nothing about it.
    """
    card_dashboard.save_card(panel_person["entry_id"], show_blood_pressure=False)
    card = _open_card(logged_in_page, card_dashboard, panel_person["display_name"])

    # Positive controls first: the rest of the card is still there.
    card.locator(RING).wait_for(state="visible", timeout=CARD_TIMEOUT)
    card.locator(ROW, has_text=WB_DISPLAY_EMOJI).wait_for(state="visible", timeout=CARD_TIMEOUT)

    assert card.locator(ROW, has_text=BP_DISPLAY_EMOJI).count() == 0, (
        "BP display row must be hidden"
    )
    assert card.locator(BP_INPUT_SYS).count() == 0, "BP input must follow the display flag"


def test_req_hom_113_card_explicit_bp_input_overrides_hidden_display(
    card_dashboard, logged_in_page, panel_person
):
    """[REQ-HOM-113] Explicit `show_blood_pressure_input: true` wins over a hidden display."""
    card_dashboard.save_card(
        panel_person["entry_id"], show_blood_pressure=False, show_blood_pressure_input=True
    )
    card = _open_card(logged_in_page, card_dashboard, panel_person["display_name"])

    card.locator(BP_INPUT_SYS).wait_for(state="visible", timeout=CARD_TIMEOUT)
    assert card.locator(ROW, has_text=BP_DISPLAY_EMOJI).count() == 0, (
        "BP display row must stay hidden"
    )


def test_req_hom_113_card_hydration_off_hides_the_ring(
    card_dashboard, logged_in_page, panel_person
):
    """[REQ-HOM-113] `show_hydration: false` hides the ring, other blocks survive."""
    card_dashboard.save_card(panel_person["entry_id"], show_hydration=False)
    card = _open_card(logged_in_page, card_dashboard, panel_person["display_name"])

    # Positive controls: the other display blocks are unaffected.
    card.locator(ROW, has_text=BP_DISPLAY_EMOJI).wait_for(state="visible", timeout=CARD_TIMEOUT)
    card.locator(ROW, has_text=WB_DISPLAY_EMOJI).wait_for(state="visible", timeout=CARD_TIMEOUT)

    assert card.locator(RING).count() == 0, "hydration ring must be hidden"


def test_req_hom_113_card_config_resave_is_applied(card_dashboard, logged_in_page, panel_person):
    """[REQ-HOM-113] Re-saving the dashboard config changes what the card renders.

    This is the switch-config path in one test: the very same dashboard first
    renders the all-off hint, then (after `lovelace/config/save` + reload) the
    hydration ring — proving the rendered DOM follows the served config, not a
    card-local default.
    """
    entry_id = panel_person["entry_id"]

    card_dashboard.save_card(entry_id, **ALL_OFF)
    card = _open_card(logged_in_page, card_dashboard, panel_person["display_name"])
    card.locator(".msg", has_text="No blocks enabled").wait_for(
        state="visible", timeout=CARD_TIMEOUT
    )

    card_dashboard.save_card(entry_id, **{**ALL_OFF, "show_hydration": True})
    card = _reload_card(logged_in_page, card_dashboard, panel_person["display_name"])

    card.locator(RING).wait_for(state="visible", timeout=CARD_TIMEOUT)
    assert card.locator(".msg", has_text="No blocks enabled").count() == 0


# --- (b) blood-pressure input writes ---------------------------------------


def test_req_hom_113_card_bp_input_writes_a_measurement(
    card_dashboard, logged_in_page, hass_base_url, hass_bearer_token, panel_person
):
    """[REQ-HOM-113] Filling sys/dia/pulse/note writes a real measurement.

    Note: the card is the only UI that writes a measurement through this form;
    the snapshot written by `health_o_mat.add_blood_pressure` is verified through
    `bp_history` (note included) and through the `panel_data` payload the card
    re-renders from.
    """
    entry_id = panel_person["entry_id"]
    note = f"card-e2e-{uuid.uuid4().hex[:10]}"

    card_dashboard.save_card(
        entry_id,
        show_hydration=False,
        show_drinks=False,
        show_manual_amounts=False,
        show_undo=False,
        show_wellbeing=False,
        show_wellbeing_input=False,
    )
    card = _open_card(logged_in_page, card_dashboard, panel_person["display_name"])

    # Fill the note first (it lives behind a collapsed <details>), then the
    # numbers; the last action is the click, so a `hass` update cannot re-render
    # the still-focused fields away before the save handler reads them.
    card.locator("details.note summary").click()
    card.locator("[data-role='bp-note']").fill(note)
    card.locator(BP_INPUT_SYS).fill(str(BP_SYS))
    card.locator("[data-role='bp-dia']").fill(str(BP_DIA))
    card.locator("[data-role='bp-pulse']").fill(str(BP_PULSE))
    card.locator(BP_SAVE).click()

    entities = _panel_data(hass_base_url, hass_bearer_token, entry_id).get("entities") or {}
    history_entity = entities.get("bp_history")
    assert isinstance(history_entity, str) and history_entity, (
        f"panel_data has no bp_history entity for {entry_id}: {entities!r}"
    )

    reading = _wait_for(
        lambda: _last_reading_with_note(hass_base_url, hass_bearer_token, history_entity, note),
        lambda value: value is not None,
        f"the measurement with note {note!r} to reach the store",
    )
    assert reading["sys"] == BP_SYS
    assert reading["dia"] == BP_DIA
    assert reading["pulse"] == BP_PULSE
    assert reading["note"] == note
    assert reading["src"] == "service", (
        f"the card must write through the service, got source {reading['src']!r}"
    )

    # The same write must show up in the card's own data source, and the
    # (still enabled) BP display must render it.
    payload = _wait_for(
        lambda: _panel_data(hass_base_url, hass_bearer_token, entry_id),
        lambda value: (
            (value.get("bp") or {}).get("sys") == BP_SYS
            and (value.get("bp") or {}).get("dia") == BP_DIA
        ),
        "panel_data to expose the new blood-pressure reading",
    )
    assert payload["bp"]["pulse"] == BP_PULSE
    assert payload["bp"]["at"] == reading["ts"]

    display = card.locator(ROW, has_text=BP_DISPLAY_EMOJI).locator(
        ".big", has_text=f"{BP_SYS}/{BP_DIA}"
    )
    display.wait_for(state="visible", timeout=CARD_TIMEOUT)
    assert display.inner_text().strip() == f"{BP_SYS}/{BP_DIA}"


# --- (c) wellbeing input writes + UI update --------------------------------


def test_req_hom_113_card_wellbeing_input_writes_and_updates_the_ui(
    card_dashboard, logged_in_page, hass_base_url, hass_bearer_token, panel_person
):
    """[REQ-HOM-113] Clicking a wellbeing button writes it and updates the card.

    The person's status is seeded to `bad` server-side first, so "becomes good"
    is an observable change in both payload and UI (not a state that happens to
    be there already).
    """
    entry_id = panel_person["entry_id"]

    ws_command(
        hass_base_url,
        hass_bearer_token,
        {"type": "health_o_mat/set_wellbeing", "entry_id": entry_id, "key": "bad"},
    )
    _wait_for(
        lambda: _panel_data(hass_base_url, hass_bearer_token, entry_id),
        lambda value: (value.get("wellbeing") or {}).get("key") == "bad",
        "the seeded wellbeing status 'bad'",
        timeout=15.0,
    )

    card_dashboard.save_card(
        entry_id,
        show_hydration=False,
        show_drinks=False,
        show_manual_amounts=False,
        show_undo=False,
        show_blood_pressure=False,
        show_blood_pressure_input=False,
    )
    card = _open_card(logged_in_page, card_dashboard, panel_person["display_name"])

    card.locator(".wb-btn[data-key='bad'][aria-pressed='true']").wait_for(
        state="visible", timeout=CARD_TIMEOUT
    )
    card.locator(".wb-btn[data-key='good']").click()

    payload = _wait_for(
        lambda: _panel_data(hass_base_url, hass_bearer_token, entry_id),
        lambda value: (value.get("wellbeing") or {}).get("key") == "good",
        "panel_data.wellbeing.key to become 'good'",
    )
    history = payload["wellbeing"].get("history") or []
    assert history, "the replaced status must be recorded in the wellbeing history"
    assert history[-1]["key"] == "bad", (
        f"the replaced status must be appended to the history, got {history[-1]!r}"
    )

    # UI: the clicked button is marked active and the display label follows.
    card.locator(".wb-btn[data-key='good'][aria-pressed='true']").wait_for(
        state="visible", timeout=CARD_TIMEOUT
    )
    display = card.locator(ROW, has_text=WB_DISPLAY_EMOJI).locator(".big", has_text="Good")
    display.wait_for(state="visible", timeout=CARD_TIMEOUT)
    assert display.inner_text().strip() == "Good"

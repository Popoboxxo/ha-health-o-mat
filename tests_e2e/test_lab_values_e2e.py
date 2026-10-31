"""E2E smoke test: lab values end-to-end (REQ-HOM-122).

Mirrors the existing Card/Panel E2E pattern (``test_card_config_e2e.py`` /
``test_panel_deeplink_e2e.py``): a real Home Assistant instance from
``docker-compose.e2e.yml`` driven by Playwright, reusing the shared fixtures
(``logged_in_page``, ``hass_base_url``, ``hass_bearer_token``, ``panel_person``).

Scenarios:

* REQ-HOM-122 (smoke, below): create a custom marker in the Admin UI → override
  a catalog reference range → record a value through the panel's "Lab values"
  tab → verify the value and its in-range badge in the tab, and the lab-warning
  row on the overview tile.
* REQ-HOM-123: the multi-row report dialog (batch write, hybrid fill button,
  all-or-nothing duplicate rejection), plus the same card on a real dashboard.
* REQ-HOM-125: the medical disclaimer in the panel's lab tab (default visible,
  admin-hideable, also in the all-categories-hidden empty state).
* REQ-HOM-124: the admin catalog's conversion column ("alt unit × factor →
  canonical", locale-formatted factor, "unit required" badge).
* REQ-HOM-126: `examples/dashboard-labs-card.yaml` renders the labs card in
  Lovelace.

Everything is asserted twice where it matters: the visible UI and the
authoritative server payload (``panel_data`` / ``get_settings``), so a green
test cannot come from the test's own input alone.

Deliberate scope notes:

* Selectors are the panel's stable data attributes (``data-field`` /
  ``data-action``), never bare display text of the controls. Translated
  *results* (the tile row) are asserted as text, because that text IS the
  contract under test.
* The catalog marker ``alt`` gets a reference override of 5–45 while the
  catalog default is 10–50: recording 47 is therefore out of range only if the
  override reached the UI — the badge proves the override, not just the
  settings payload.
* The person's lab options are snapshotted and restored after the test: the
  E2E instance is shared and its options survive a run. Without the restore,
  every run would leave another custom marker behind.
* Lab *readings* stay in the store (like the drinks/BP writes of the other E2E
  tests); the tile-row assertion derives its expected count from the live
  payload instead of hard-coding a number, so leftover data can never make the
  test flaky.
* The test also walks the ENTITY layer, not only the panel payload: creating a
  custom marker must create ``sensor.<...>_lab_<key>`` in the entity registry
  and the state machine *without* a Home Assistant restart (review finding B-1:
  an options change used to leave the new marker entity missing until the next
  restart). Removing the marker again must take the entity out of service, so a
  stale value can never keep being reported.
"""

from __future__ import annotations

import re
import uuid
import warnings
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
import yaml
from e2e_helpers import ws_command
from playwright.sync_api import expect
from test_card_config_e2e import CARD_TIMEOUT, _panel_data, _wait_for
from test_panel_deeplink_e2e import open_panel, tab_keys, tile, wait_for_detail, wait_for_overview

from scripts.e2e_bootstrap import _ws_command

pytestmark = pytest.mark.e2e

# --- selectors (panel data attributes, language-agnostic) -------------------

SETTINGS_GEAR = "[data-action='settings']"
SETTINGS_FORM = "form[data-form='settings']"
SETTINGS_PERSON = "select[data-action='settings-person']"
SAVE_BUTTON = "button[data-save-button]"
BACK = "[data-action='back']"

LAB_REF_TABLE = "table.lab-ref-table"
CUSTOM_NAME = "[data-field='lab-custom-name']"
CUSTOM_UNIT = "[data-field='lab-custom-unit']"
CUSTOM_CATEGORY = "[data-field='lab-custom-category']"
CUSTOM_REF_MIN_FIELD = "[data-field='lab-custom-ref-min']"
CUSTOM_REF_MAX_FIELD = "[data-field='lab-custom-ref-max']"
CUSTOM_ADD = "[data-action='lab-custom-add']"
CUSTOM_LIST = "ul.lab-custom-list li"
REF_MIN_ALT = "[data-field='lab-ref-min-alt']"
REF_MAX_ALT = "[data-field='lab-ref-max-alt']"

LAB_TAB = ".tab[data-tab='labs']"
LAB_CATEGORY_BAR = ".lab-category-bar"
LAB_CATEGORY_BUTTON = "[data-action='lab-category'][data-category='%s']"
LAB_ROW = "div.lab-row[data-marker='%s']"
LAB_ROW_NAME = ".lab-row-name"
LAB_ROW_VALUE = ".lab-row-value"
LAB_ROW_OK = ".status.good"
LAB_ROW_WARN = ".status.bad"

# Home Assistant's own websocket commands (no integration-specific extra API).
ENTITY_REGISTRY = "config/entity_registry/list"
ENTITY_REGISTRY_REMOVE = "config/entity_registry/remove"
STATES = "get_states"

ENTRY_FORM = "details.lab-entry-form"
ENTRY_MARKER = "[data-field='lab-add-marker']"
ENTRY_VALUE = "[data-field='lab-add-value']"
ENTRY_SAVE = "[data-action='lab-add-value']"

# Mehrzeilen-Dialog "Laborbericht" (REQ-HOM-123) — Panel-Zweitimplementierung
# der Karte, gleiche `data-field`/`data-action`-Namen (§6.3).
LAB_REPORT_FORM = "details.lab-report-form"
LAB_REPORT_FILL_VISIBLE = "[data-action='lab-report-fill-visible']"
LAB_REPORT_FILL_LAST = "[data-action='lab-report-fill-last']"
LAB_REPORT_ADD = "[data-action='lab-report-add']"
LAB_REPORT_SAVE = "[data-action='lab-report-save']"
LAB_REPORT_DISCARD = "[data-action='lab-report-discard']"
LAB_REPORT_MARKER = "[data-field='lab-report-marker-%d']"
LAB_REPORT_VALUE = "[data-field='lab-report-value-%d']"
LAB_REPORT_UNIT = "[data-field='lab-report-unit-%d']"
LAB_REPORT_MARKER_SELECT = "[data-field^='lab-report-marker-']"
LAB_REPORT_ERROR = ".msg.error"

# Medizin-Hinweis (REQ-HOM-125) + Admin-Schalter dafür.
LAB_DISCLAIMER = ".labs-disclaimer"
DISCLAIMER_CHECKBOX = "[data-field='lab-hide-panel-disclaimer']"

# Laborwerte-Karte in einem echten Lovelace-Dashboard (REQ-HOM-126).
LABS_CARD_TAG = "health-o-mat-labs-card"
EXAMPLE_LABS_DASHBOARD = (
    Path(__file__).resolve().parents[1] / "examples" / "dashboard-labs-card.yaml"
)

TILE_LAB_ROW = ".lab-row-tile"
TILE_STATUS = ".status.bad"

# --- values ----------------------------------------------------------------

# Category of the custom marker: the only category without catalog markers, so
# its bar entry exists solely because of this test's marker.
CUSTOM_CATEGORY_KEY = "other"
CUSTOM_UNIT_VALUE = "ng/mL"
CUSTOM_REF_MIN = 2.0
CUSTOM_REF_MAX = 8.0
CUSTOM_VALUE = 4  # inside 2–8

CATALOG_MARKER = "alt"  # catalog default 10–50 U/L
CATALOG_MARKER_UNIT = "U/L"
ALT_REF_MIN = 5.0
ALT_REF_MAX = 45.0
ALT_VALUE = 47  # inside 10–50 (catalog default), outside 5–45 (override)

BADGE_OK = "\u2713"
BADGE_WARN = "\u26a0"


# --- helpers ----------------------------------------------------------------


def _settings(base_url: str, token: str, entry_id: str) -> dict[str, Any]:
    """The authoritative settings payload (`health_o_mat/get_settings`)."""
    result = ws_command(
        base_url, token, {"type": "health_o_mat/get_settings", "entry_id": entry_id}
    )
    return result or {}


def _lab_marker(payload: dict[str, Any], marker_key: str) -> dict[str, Any]:
    """One marker entry of the `panel_data.labs` block ({} when absent)."""
    return ((payload.get("labs") or {}).get("markers") or {}).get(marker_key) or {}


def _expected_lab_warning_count(payload: dict[str, Any]) -> int:
    """Markers outside their reference range in visible categories.

    The same rule the panel applies when it builds the overview tile row
    (`_labWarningCount` in health-o-mat-panel-views.js): hidden categories are
    excluded, `in_range is False` counts.
    """
    labs = payload.get("labs") or {}
    hidden = {
        str(category.get("key"))
        for category in labs.get("categories") or []
        if category.get("hidden")
    }
    return sum(
        1
        for marker in (labs.get("markers") or {}).values()
        if marker and str(marker.get("category")) not in hidden and marker.get("in_range") is False
    )


def _lab_unique_id(entry_id: str, marker_key: str) -> str:
    """`unique_id` of one marker's lab sensor (stable HACS contract)."""
    return f"{entry_id}_lab_{marker_key}"


def _entity_registry_entries(base_url: str, token: str) -> list[dict[str, Any]]:
    """Every entity-registry entry of the instance (`config/entity_registry/list`)."""
    return _ws_command(base_url, token, {"type": ENTITY_REGISTRY}) or []


def _entity_state(base_url: str, token: str, entity_id: str) -> dict[str, Any] | None:
    """One state-machine entry from HA itself (None when the entity has no state)."""
    for state in _ws_command(base_url, token, {"type": STATES}) or []:
        if state.get("entity_id") == entity_id:
            return state
    return None


def _lab_entity(base_url: str, token: str, entry_id: str, marker_key: str) -> dict[str, Any]:
    """Registry entry + state of a marker's lab sensor (each may be None)."""
    unique_id = _lab_unique_id(entry_id, marker_key)
    registry_entry = next(
        (
            item
            for item in _entity_registry_entries(base_url, token)
            if item.get("unique_id") == unique_id
        ),
        None,
    )
    entity_id = str(registry_entry["entity_id"]) if registry_entry else ""
    return {
        "registry": registry_entry,
        "state": _entity_state(base_url, token, entity_id) if entity_id else None,
    }


def _record_lab_value(panel, marker_key: str, value: float) -> None:
    """Record one value through the lab tab's entry form.

    Ends by waiting for the save button to be ENABLED again: the panel disables
    it while writing and re-renders after the reload, so "enabled" is the
    observable end of the write. Clicking into a DOM that is about to be
    replaced is the one reliable flakiness source in this flow.

    The panel lives inside Home Assistant's shadow DOM, so this uses locators
    (which pierce it) — a `document.querySelector` page function would not find
    it at all.
    """
    form = panel.locator(ENTRY_FORM).first
    form.wait_for(state="attached", timeout=CARD_TIMEOUT)
    if not form.evaluate("(el) => el.open"):
        form.locator("summary").click()

    marker_field = panel.locator(ENTRY_MARKER)
    marker_field.wait_for(state="visible", timeout=CARD_TIMEOUT)
    marker_field.select_option(marker_key)
    panel.locator(ENTRY_VALUE).fill(str(value))
    panel.locator(ENTRY_SAVE).click()

    expect(panel.locator(ENTRY_SAVE)).to_be_enabled(timeout=CARD_TIMEOUT)


# --- fixtures ---------------------------------------------------------------


def _remove_orphaned_lab_entities(
    base_url: str, token: str, entry_id: str, settings: dict[str, Any]
) -> None:
    """Drop lab entities that no effective marker backs any more.

    Home Assistant keeps the registry entry of an entity its platform stops
    providing and only marks it `unavailable`; on a shared instance that would
    add one orphan per run. Removing them keeps the test instance's registry
    clean without touching any non-lab entity.
    """
    catalog_keys = set((settings.get("lab_catalog") or {}).get("markers") or {})
    custom_keys = {str(marker["key"]) for marker in settings.get("lab_custom_markers") or []}
    valid = {_lab_unique_id(entry_id, key) for key in catalog_keys | custom_keys}
    prefix = f"{entry_id}_lab_"
    for item in _entity_registry_entries(base_url, token):
        unique_id = str(item.get("unique_id") or "")
        if item.get("platform") != "health_o_mat" or not unique_id.startswith(prefix):
            continue
        if unique_id in valid:
            continue
        _ws_command(
            base_url, token, {"type": ENTITY_REGISTRY_REMOVE, "entity_id": item["entity_id"]}
        )


@pytest.fixture
def restore_lab_options(hass_base_url, hass_bearer_token, panel_person) -> Iterator[dict[str, Any]]:
    """Snapshot the person's lab options and restore them afterwards.

    The E2E instance is shared and `entry.options` survive a run, so a custom
    marker created here would otherwise accumulate on every run. Only the lab
    option keys are touched; everything else is left alone. The orphaned lab
    entity such a marker leaves behind is removed afterwards, too (also when
    the test fails halfway).

    `lab_hide_panel_disclaimer` belongs to the same snapshot since REQ-HOM-125:
    the disclaimer test turns the note off and would otherwise leave the shared
    instance with a hidden disclaimer for every later run.
    """
    entry_id = panel_person["entry_id"]
    before = _settings(hass_base_url, hass_bearer_token, entry_id)
    snapshot = {
        "lab_custom_markers": before.get("lab_custom_markers") or [],
        "lab_ref_overrides": before.get("lab_ref_overrides") or {},
        "lab_hidden_categories": before.get("lab_hidden_categories") or [],
        "lab_hide_panel_disclaimer": before.get("lab_hide_panel_disclaimer") is True,
    }
    try:
        yield snapshot
    finally:
        try:
            current = _settings(hass_base_url, hass_bearer_token, entry_id)
            changed = any(current.get(key) != snapshot[key] for key in snapshot)
            if changed:
                current = ws_command(
                    hass_base_url,
                    hass_bearer_token,
                    {"type": "health_o_mat/set_settings", "entry_id": entry_id, **snapshot},
                ) or _settings(hass_base_url, hass_bearer_token, entry_id)
            _remove_orphaned_lab_entities(hass_base_url, hass_bearer_token, entry_id, current)
        except Exception as exc:  # noqa: BLE001 - teardown must not mask the test result
            warnings.warn(
                f"could not restore the lab options of {entry_id!r} "
                f"(snapshot={snapshot!r}): {exc} — check them manually",
                RuntimeWarning,
                stacklevel=2,
            )


# --- the smoke test ---------------------------------------------------------


def test_req_hom_122_lab_values_smoke(
    logged_in_page, hass_base_url, hass_bearer_token, panel_person, restore_lab_options
):
    """[REQ-HOM-122] Custom marker + reference override + value reach tab and overview tile."""
    page = logged_in_page
    entry_id = panel_person["entry_id"]
    # Unique per run so a leftover marker from an aborted run can never make the
    # "the row shows OUR marker" assertions pass by accident.
    marker_name = f"E2E Marker {uuid.uuid4().hex[:8]}"

    # 1. Admin settings of the person under test (gear lives in the panel topbar).
    panel = open_panel(page, hass_base_url, person=panel_person["slug"])
    wait_for_detail(panel)
    panel.locator(SETTINGS_GEAR).click()
    panel.locator(SETTINGS_FORM).wait_for(state="visible", timeout=CARD_TIMEOUT)
    panel.locator(LAB_REF_TABLE).wait_for(state="visible", timeout=CARD_TIMEOUT)

    # The admin form resumes the person opened in the detail view; state it
    # explicitly anyway, the instance holds more than one person.
    person_select = panel.locator(SETTINGS_PERSON)
    if person_select.count():
        person_select.select_option(entry_id)
        panel.locator(LAB_REF_TABLE).wait_for(state="visible", timeout=CARD_TIMEOUT)

    # 2. Add a custom marker through the Admin UI.
    panel.locator(CUSTOM_NAME).fill(marker_name)
    panel.locator(CUSTOM_UNIT).fill(CUSTOM_UNIT_VALUE)
    panel.locator(CUSTOM_CATEGORY).select_option(CUSTOM_CATEGORY_KEY)
    panel.locator(CUSTOM_REF_MIN_FIELD).fill(str(CUSTOM_REF_MIN))
    panel.locator(CUSTOM_REF_MAX_FIELD).fill(str(CUSTOM_REF_MAX))
    panel.locator(CUSTOM_ADD).click()
    panel.locator(CUSTOM_LIST, has_text=marker_name).wait_for(state="visible", timeout=CARD_TIMEOUT)

    # 3. Override the catalog reference range of ALT (5–45 instead of 10–50).
    panel.locator(REF_MIN_ALT).fill(str(ALT_REF_MIN))
    panel.locator(REF_MAX_ALT).fill(str(ALT_REF_MAX))
    panel.locator(SAVE_BUTTON).click()

    saved = _wait_for(
        lambda: _settings(hass_base_url, hass_bearer_token, entry_id),
        lambda value: (
            any(
                marker.get("name") == marker_name
                for marker in value.get("lab_custom_markers") or []
            )
            and (value.get("lab_ref_overrides") or {}).get(CATALOG_MARKER)
            == {"ref_min": ALT_REF_MIN, "ref_max": ALT_REF_MAX}
        ),
        "the saved custom marker and reference override to reach the store",
    )

    custom_marker = next(
        marker for marker in saved["lab_custom_markers"] if marker.get("name") == marker_name
    )
    marker_key = str(custom_marker["key"])
    assert custom_marker["unit"] == CUSTOM_UNIT_VALUE
    assert custom_marker["category"] == CUSTOM_CATEGORY_KEY
    assert custom_marker["ref_min"] == CUSTOM_REF_MIN
    assert custom_marker["ref_max"] == CUSTOM_REF_MAX

    # 3b. Review finding B-1: the new marker must exist as a REAL entity right
    # away. An options change used to update only the runtime mirror, so
    # `sensor.<person>_lab_<key>` appeared not before the next HA restart —
    # invisible to `panel_data`, which is why an UI-only test missed it.
    entity = _wait_for(
        lambda: _lab_entity(hass_base_url, hass_bearer_token, entry_id, marker_key),
        lambda value: value["state"] is not None,
        "the lab sensor entity of the new custom marker (B-1: lab option change "
        "must reload the entry, no restart)",
    )
    lab_entity_id = str(entity["registry"]["entity_id"])
    registry_entry = entity["registry"]
    assert lab_entity_id.startswith("sensor."), f"unexpected domain: {lab_entity_id!r}"
    assert registry_entry["platform"] == "health_o_mat"
    assert registry_entry["unique_id"] == _lab_unique_id(entry_id, marker_key)

    entity_attributes = entity["state"]["attributes"] or {}
    assert entity_attributes.get("unit_of_measurement") == CUSTOM_UNIT_VALUE
    assert entity_attributes.get("ref_min") == CUSTOM_REF_MIN
    assert entity_attributes.get("ref_max") == CUSTOM_REF_MAX
    assert entity_attributes.get("category") == CUSTOM_CATEGORY_KEY
    assert entity["state"]["state"] == "unknown", "no value recorded yet"

    # 4. Person detail → lab tab (the admin form's back button leads to the overview).
    panel.locator(BACK).click()
    wait_for_overview(panel)
    tile(panel, entry_id).click()
    wait_for_detail(panel)
    assert "labs" in tab_keys(panel), "the lab tab must be rendered for an enabled lab area"

    panel.locator(LAB_TAB).click()
    panel.locator(LAB_CATEGORY_BAR).wait_for(state="visible", timeout=CARD_TIMEOUT)

    # 5. Record a value for the custom marker (in range 2–8).
    _record_lab_value(panel, marker_key, CUSTOM_VALUE)
    custom = _wait_for(
        lambda: _lab_marker(_panel_data(hass_base_url, hass_bearer_token, entry_id), marker_key),
        lambda value: value.get("value") == CUSTOM_VALUE,
        f"the custom lab value {CUSTOM_VALUE} to reach the store",
    )
    assert custom["unit"] == CUSTOM_UNIT_VALUE
    assert custom["in_range"] is True

    # The sensor state must follow the write, not just the panel payload.
    sensor_state = _wait_for(
        lambda: _entity_state(hass_base_url, hass_bearer_token, lab_entity_id),
        lambda value: (
            value is not None and value.get("state") not in (None, "unknown", "unavailable")
        ),
        f"the lab sensor state to mirror the recorded value {CUSTOM_VALUE}",
    )
    assert float(sensor_state["state"]) == CUSTOM_VALUE
    sensor_attributes = sensor_state["attributes"] or {}
    assert sensor_attributes.get("unit_of_measurement") == CUSTOM_UNIT_VALUE
    assert sensor_attributes.get("in_range") is True

    panel.locator(LAB_CATEGORY_BUTTON % CUSTOM_CATEGORY_KEY).click()
    custom_row = panel.locator(LAB_ROW % marker_key)
    custom_row.wait_for(state="visible", timeout=CARD_TIMEOUT)
    assert custom_row.locator(LAB_ROW_NAME).inner_text().strip() == marker_name
    assert (
        custom_row.locator(LAB_ROW_VALUE).inner_text().strip()
        == f"{CUSTOM_VALUE} {CUSTOM_UNIT_VALUE}"
    )
    badge_ok = custom_row.locator(LAB_ROW_OK)
    badge_ok.wait_for(state="visible", timeout=CARD_TIMEOUT)
    assert badge_ok.inner_text().strip() == BADGE_OK
    assert custom_row.locator(LAB_ROW_WARN).count() == 0, (
        "a value inside its reference range must not be flagged"
    )

    # 6. Record ALT = 47: inside the catalog default, outside the override.
    _record_lab_value(panel, CATALOG_MARKER, ALT_VALUE)
    alt = _wait_for(
        lambda: _lab_marker(
            _panel_data(hass_base_url, hass_bearer_token, entry_id), CATALOG_MARKER
        ),
        lambda value: (
            value.get("value") == ALT_VALUE
            and value.get("ref_min") == ALT_REF_MIN
            and value.get("ref_max") == ALT_REF_MAX
            and value.get("in_range") is False
        ),
        "the ALT value to be classified against the overridden reference range",
    )
    assert alt["unit"] == CATALOG_MARKER_UNIT

    panel.locator(LAB_CATEGORY_BUTTON % alt["category"]).click()
    alt_row = panel.locator(LAB_ROW % CATALOG_MARKER)
    alt_row.wait_for(state="visible", timeout=CARD_TIMEOUT)
    assert (
        alt_row.locator(LAB_ROW_VALUE).inner_text().strip() == f"{ALT_VALUE} {CATALOG_MARKER_UNIT}"
    )
    badge_warn = alt_row.locator(LAB_ROW_WARN)
    badge_warn.wait_for(state="visible", timeout=CARD_TIMEOUT)
    assert BADGE_WARN in badge_warn.inner_text()
    assert alt_row.locator(LAB_ROW_OK).count() == 0

    # 7. Overview tile: the lab row and the ⚠ badge must reflect the live payload.
    panel.locator(BACK).click()
    wait_for_overview(panel)

    payload = _panel_data(hass_base_url, hass_bearer_token, entry_id)
    expected_count = _expected_lab_warning_count(payload)
    assert expected_count >= 1, "the out-of-range ALT value must count as a warning"
    assert _lab_marker(payload, CATALOG_MARKER).get("in_range") is False

    person_tile = tile(panel, entry_id)
    lab_row = person_tile.locator(TILE_LAB_ROW)
    lab_row.wait_for(state="visible", timeout=CARD_TIMEOUT)
    assert f"{expected_count} markers outside reference" in lab_row.inner_text()

    status = person_tile.locator(TILE_STATUS)
    status.wait_for(state="visible", timeout=CARD_TIMEOUT)
    status_title = status.get_attribute("title") or ""
    assert f"{expected_count} lab values outside reference" in status_title, (
        f"the warning badge must name the lab cause, got title {status_title!r}"
    )

    # 8. Removing the marker again (Admin UI) must take its entity out of
    # service — an orphaned sensor that keeps reporting the last value would be
    # data the user cannot get rid of.
    panel.locator(SETTINGS_GEAR).click()
    panel.locator(SETTINGS_FORM).wait_for(state="visible", timeout=CARD_TIMEOUT)
    panel.locator(LAB_REF_TABLE).wait_for(state="visible", timeout=CARD_TIMEOUT)
    custom_entry = panel.locator(CUSTOM_LIST, has_text=marker_name)
    custom_entry.wait_for(state="visible", timeout=CARD_TIMEOUT)
    custom_entry.locator("[data-action='lab-custom-remove']").click()
    assert panel.locator(CUSTOM_LIST, has_text=marker_name).count() == 0, (
        "the removed marker must disappear from the admin list"
    )

    panel.locator(SAVE_BUTTON).click()
    _wait_for(
        lambda: _settings(hass_base_url, hass_bearer_token, entry_id),
        lambda value: all(
            marker.get("name") != marker_name for marker in value.get("lab_custom_markers") or []
        ),
        "the custom marker to be removed from the store",
    )

    # Home Assistant keeps the registry entry of an entity its platform no
    # longer provides; what matters is that it is out of service (state
    # `unavailable`) or gone entirely.
    retired = _wait_for(
        lambda: _lab_entity(hass_base_url, hass_bearer_token, entry_id, marker_key),
        lambda value: (
            value["registry"] is None
            or value["state"] is None
            or value["state"].get("state") == "unavailable"
        ),
        "the lab sensor entity to be gone/unavailable after removing the marker",
    )
    assert retired["state"] is None or retired["state"]["state"] == "unavailable"


# --- REQ-HOM-123…126: Batch, Disclaimer, Admin-Faktoren, Beispiel-Dashboard --


def _open_labs_tab(page, base_url: str, person: str):
    """Person detail view with the lab tab active (category bar rendered)."""
    panel = open_panel(page, base_url, person=person)
    wait_for_detail(panel)
    panel.locator(LAB_TAB).click()
    panel.locator(LAB_CATEGORY_BAR).wait_for(state="visible", timeout=CARD_TIMEOUT)
    return panel


def _open_report_form(panel):
    """Open the collapsed report dialog (`<details>`) and return its locator."""
    form = panel.locator(LAB_REPORT_FORM)
    form.wait_for(state="attached", timeout=CARD_TIMEOUT)
    if not form.evaluate("(el) => el.open"):
        form.locator("summary").click()
    panel.locator(LAB_REPORT_ADD).wait_for(state="visible", timeout=CARD_TIMEOUT)
    return form


def _visible_marker_keys(payload: dict[str, Any]) -> list[str]:
    """Marker keys the panel auto-fills ("alle sichtbaren Marker").

    Same rule as `visibleLabCategories` in health-o-mat-panel-views.js: a
    category is visible when it is not hidden AND has at least one marker.
    """
    labs = payload.get("labs") or {}
    markers = labs.get("markers") or {}
    hidden = {
        str(category.get("key"))
        for category in labs.get("categories") or []
        if category.get("hidden")
    }
    with_markers = {str(marker.get("category")) for marker in markers.values() if marker}
    return sorted(
        str(key)
        for key, marker in markers.items()
        if marker and str(marker.get("category")) not in hidden
        if str(marker.get("category")) in with_markers
    )


def _report_row_markers(panel) -> list[str]:
    """`value` of every marker select of the report dialog (row order)."""
    return panel.locator(LAB_REPORT_MARKER_SELECT).evaluate_all("els => els.map(el => el.value)")


def _report_field(panel, selector: str):
    """One control of the report dialog, with the `<details>` opened first.

    The panel re-renders its whole shadow root on structural changes (add a
    row, pick a marker), which resets the `<details>` element to "closed" —
    the controls then exist but are not visible. Re-opening before every
    interaction keeps the test on the user-visible path instead of poking at
    hidden DOM.
    """
    _open_report_form(panel)
    field = panel.locator(selector)
    field.wait_for(state="visible", timeout=CARD_TIMEOUT)
    return field


def _report_type(panel, selector: str, value: str) -> None:
    """Type into a dialog input and commit it like a user leaving the field.

    The panel keeps the dialog draft in `change` events (the `input` event is
    not wired), so a bare `fill()` would leave the draft empty and the report
    would be rejected as "marker without value". Blurring commits the value.
    """
    field = _report_field(panel, selector)
    field.fill(value)
    field.blur()


def _labs_dashboard_config() -> dict[str, Any]:
    """The shipped example dashboard — the artifact under test (REQ-HOM-126).

    Read verbatim from ``examples/dashboard-labs-card.yaml``. There is
    deliberately no inline fallback: a fallback would keep the test green while
    the shipped example is broken (or missing from the E2E image), which is
    exactly the failure mode this test exists to catch.
    """
    assert EXAMPLE_LABS_DASHBOARD.is_file(), (
        f"the example dashboard under test is missing: {EXAMPLE_LABS_DASHBOARD} "
        "(the E2E image must ship it — see Dockerfile.e2e's 'COPY examples/')"
    )
    with EXAMPLE_LABS_DASHBOARD.open(encoding="utf-8") as handle:
        config = yaml.safe_load(handle)
    assert isinstance(config, dict), (
        f"{EXAMPLE_LABS_DASHBOARD} must parse to a Lovelace config mapping, "
        f"got {type(config).__name__}"
    )
    return config


def test_req_hom_123_hybrid_button_prefills_visible_markers(
    logged_in_page, hass_base_url, hass_bearer_token, panel_person
):
    """[REQ-HOM-123] "Fill all visible markers" prefills one row per visible marker.

    Spec §6.1 (hybrid filling) and §6.3 (the panel is a second implementation of
    the same dialog) require the two fill buttons next to the multi-row form.
    Kept separate from the write/duplicate test on purpose: a broken fill button
    must not mask the batch-write contract (and vice versa).
    """
    page = logged_in_page
    entry_id = panel_person["entry_id"]

    panel = _open_labs_tab(page, hass_base_url, panel_person["slug"])
    _open_report_form(panel)
    panel.locator(LAB_REPORT_FILL_VISIBLE).click()

    expected_keys = _visible_marker_keys(_panel_data(hass_base_url, hass_bearer_token, entry_id))
    assert expected_keys, "the catalog must provide visible markers to fill"
    assert sorted(_report_row_markers(panel)) == expected_keys, (
        "the hybrid button must prefill exactly the visible markers, one row each "
        "(reproduce: open the panel's lab tab → 'Laborbericht erfassen' → "
        "'Alle sichtbaren Marker anlegen'; it adds no rows because the panel "
        "passes an empty entry id)"
    )


def test_req_hom_123_lab_report_dialog_writes_and_rejects_duplicates(
    logged_in_page, hass_base_url, hass_bearer_token, panel_person
):
    """[REQ-HOM-123] Two rows in one write; a duplicate is rejected and keeps the input."""
    page = logged_in_page
    entry_id = panel_person["entry_id"]
    # One decimal that is never .0: the panel renders the raw JSON number, so a
    # whole number would read "137" instead of a formatted "137.0".
    alt_value = round(100 + (uuid.uuid4().int % 90) + 0.5, 1)
    crp_value = round(10 + (uuid.uuid4().int % 90) + 0.5, 1)

    # 1. Two rows, one save.
    panel = _open_labs_tab(page, hass_base_url, panel_person["slug"])
    _open_report_form(panel)
    panel.locator(LAB_REPORT_ADD).click()
    _report_field(panel, LAB_REPORT_MARKER % 0).select_option(CATALOG_MARKER)
    _report_type(panel, LAB_REPORT_VALUE % 0, str(alt_value))
    _report_field(panel, LAB_REPORT_MARKER % 1).select_option("crp")
    _report_type(panel, LAB_REPORT_VALUE % 1, str(crp_value))
    _report_type(panel, LAB_REPORT_UNIT % 1, "mg/L")
    _report_field(panel, LAB_REPORT_SAVE).click()

    after = _wait_for(
        lambda: _panel_data(hass_base_url, hass_bearer_token, entry_id),
        lambda value: _lab_marker(value, "crp").get("reported_value") == crp_value,
        "the report values to reach the store",
    )
    alt = _lab_marker(after, CATALOG_MARKER)
    crp = _lab_marker(after, "crp")
    assert alt["reported_value"] == alt_value
    assert alt["reported_unit"] == CATALOG_MARKER_UNIT
    assert alt["value"] == alt_value, "U/L is canonical, no conversion expected"
    assert crp["reported_value"] == crp_value
    assert crp["reported_unit"] == "mg/L"
    assert crp["value"] == crp_value
    last_report = (after.get("labs") or {}).get("last_report") or {}
    assert sorted(last_report.get("marker_keys") or []) == sorted([CATALOG_MARKER, "crp"]), (
        "both rows must belong to ONE report (single batch write, §2.5)"
    )

    # The sensor layer must follow the batch write, not just the panel payload.
    alt_entity = _wait_for(
        lambda: _lab_entity(hass_base_url, hass_bearer_token, entry_id, CATALOG_MARKER),
        lambda value: (
            value["state"] is not None
            and value["state"].get("state") not in (None, "unknown", "unavailable")
        ),
        "the ALT lab sensor to mirror the batch write",
    )
    assert float(alt_entity["state"]["state"]) == alt_value
    crp_entity = _wait_for(
        lambda: _lab_entity(hass_base_url, hass_bearer_token, entry_id, "crp"),
        lambda value: (
            value["state"] is not None
            and value["state"].get("state") not in (None, "unknown", "unavailable")
        ),
        "the CRP lab sensor to mirror the batch write",
    )
    assert float(crp_entity["state"]["state"]) == crp_value

    # ... and the tab itself shows both values.
    alt_row = panel.locator(LAB_ROW % CATALOG_MARKER)
    alt_row.wait_for(state="visible", timeout=CARD_TIMEOUT)
    assert alt_row.locator(LAB_ROW_VALUE).inner_text().strip() == (
        f"{alt_value} {CATALOG_MARKER_UNIT}"
    )
    panel.locator(LAB_CATEGORY_BUTTON % crp["category"]).click()
    crp_row = panel.locator(LAB_ROW % "crp")
    crp_row.wait_for(state="visible", timeout=CARD_TIMEOUT)
    assert crp_row.locator(LAB_ROW_VALUE).inner_text().strip() == f"{crp_value} mg/L"

    # 2. Duplicate: the same resolved marker twice → server refuses the WHOLE
    # report, names row and marker, and the dialog keeps its input.
    before = _lab_marker(_panel_data(hass_base_url, hass_bearer_token, entry_id), CATALOG_MARKER)[
        "reported_value"
    ]
    _open_report_form(panel)
    panel.locator(LAB_REPORT_ADD).click()
    _report_field(panel, LAB_REPORT_MARKER % 0).select_option(CATALOG_MARKER)
    _report_type(panel, LAB_REPORT_VALUE % 0, "33")
    _report_field(panel, LAB_REPORT_MARKER % 1).select_option(CATALOG_MARKER)
    _report_type(panel, LAB_REPORT_VALUE % 1, "34")
    _report_field(panel, LAB_REPORT_SAVE).click()

    error = panel.locator(LAB_REPORT_ERROR).first
    error.wait_for(state="visible", timeout=CARD_TIMEOUT)
    message = error.inner_text()
    assert "Zeile 2" in message, f"the error must name the offending row: {message!r}"
    assert CATALOG_MARKER in message, f"the error must name the marker: {message!r}"
    assert "duplicate_marker" in message, f"the error must carry the code: {message!r}"
    assert panel.locator(LAB_REPORT_VALUE % 0).input_value() == "33", (
        "a rejected report must keep the entered values"
    )
    assert panel.locator(LAB_REPORT_VALUE % 1).input_value() == "34"

    unchanged = _panel_data(hass_base_url, hass_bearer_token, entry_id)
    assert _lab_marker(unchanged, CATALOG_MARKER)["reported_value"] == before, (
        "an all-or-nothing rejection must not touch the stored value"
    )


def test_req_hom_125_panel_disclaimer_visibility_and_empty_state(
    logged_in_page, hass_base_url, hass_bearer_token, panel_person, restore_lab_options
):
    """[REQ-HOM-125] Visible by default, hideable by admins, also in the empty state."""
    page = logged_in_page
    entry_id = panel_person["entry_id"]
    settings = _settings(hass_base_url, hass_bearer_token, entry_id)

    # 1. Default: the note is part of the lab tab (before any settings load).
    panel = _open_labs_tab(page, hass_base_url, panel_person["slug"])
    disclaimer = panel.locator(LAB_DISCLAIMER)
    disclaimer.wait_for(state="visible", timeout=CARD_TIMEOUT)
    assert "medical" in disclaimer.inner_text().lower()
    assert panel.locator(LAB_CATEGORY_BAR).count() == 1, (
        "the disclaimer must not replace the category bar while categories are visible"
    )

    # 2. Admin: hide the note through the settings form.
    panel.locator(SETTINGS_GEAR).click()
    panel.locator(SETTINGS_FORM).wait_for(state="visible", timeout=CARD_TIMEOUT)
    checkbox = panel.locator(DISCLAIMER_CHECKBOX)
    checkbox.wait_for(state="visible", timeout=CARD_TIMEOUT)
    assert not checkbox.is_checked(), "the E2E fixture must start with a visible disclaimer"
    checkbox.set_checked(True)
    panel.locator(SAVE_BUTTON).click()
    _wait_for(
        lambda: _settings(hass_base_url, hass_bearer_token, entry_id),
        lambda value: value.get("lab_hide_panel_disclaimer") is True,
        "the disclaimer option to be persisted",
    )

    panel.locator(BACK).click()
    wait_for_overview(panel)
    tile(panel, entry_id).click()
    wait_for_detail(panel)
    panel.locator(LAB_TAB).click()
    panel.locator(LAB_CATEGORY_BAR).wait_for(state="visible", timeout=CARD_TIMEOUT)
    assert panel.locator(LAB_DISCLAIMER).count() == 0, (
        "a hidden disclaimer must not be rendered at all (not merely invisible)"
    )

    # 3. Hide EVERY category: empty state keeps the note (the data is still
    # there, only the display is filtered) and names the settings cause.
    panel.locator(SETTINGS_GEAR).click()
    panel.locator(SETTINGS_FORM).wait_for(state="visible", timeout=CARD_TIMEOUT)
    panel.locator(DISCLAIMER_CHECKBOX).set_checked(False)
    for category in settings["lab_catalog"]["categories"]:
        box = panel.locator(f"[data-field='lab-hide-{category['key']}']")
        if box.count():
            box.set_checked(False)
    panel.locator(SAVE_BUTTON).click()
    _wait_for(
        lambda: _settings(hass_base_url, hass_bearer_token, entry_id),
        lambda value: bool(value.get("lab_hidden_categories")),
        "all categories to be hidden",
    )

    panel.locator(BACK).click()
    wait_for_overview(panel)
    tile(panel, entry_id).click()
    wait_for_detail(panel)
    panel.locator(LAB_TAB).click()
    empty_disclaimer = panel.locator(LAB_DISCLAIMER)
    empty_disclaimer.wait_for(state="visible", timeout=CARD_TIMEOUT)
    assert "medical" in empty_disclaimer.inner_text().lower()
    assert panel.locator(LAB_CATEGORY_BAR).count() == 0, "no category bar in the empty state"
    assert settings["lab_catalog"]["categories"], "the catalog must not be empty"

    empty_message = panel.locator(".msg", has_text="hidden").first
    empty_message.wait_for(state="visible", timeout=CARD_TIMEOUT)
    empty_text = empty_message.inner_text().lower()
    assert "categor" in empty_text and "hidden" in empty_text, (
        f"the empty state must explain that the categories are hidden: {empty_text!r}"
    )


def test_req_hom_124_admin_conversion_column_visible(logged_in_page, hass_base_url, panel_person):
    """[REQ-HOM-124] The catalog table shows "alt unit × factor → canonical"."""
    page = logged_in_page
    panel = open_panel(page, hass_base_url, person=panel_person["slug"])
    wait_for_detail(panel)
    panel.locator(SETTINGS_GEAR).click()
    panel.locator(LAB_REF_TABLE).wait_for(state="visible", timeout=CARD_TIMEOUT)

    text = panel.locator(LAB_REF_TABLE).inner_text()
    # Bilirubin: mg/dL × 17.1 → µmol/L. The factor goes through
    # `Intl.NumberFormat`, so the decimal separator follows the UI language
    # (17.1 in en, 17,1 in de) — the test accepts both instead of pinning one.
    assert re.search(r"mg/dL × 17[.,]1 → µmol/L", text), (
        f"missing the bilirubin conversion column entry: {text!r}"
    )
    # Urea: g/g × 1,000 → mg/g — the grouping separator proves the factor is
    # formatted locally instead of string-concatenated.
    assert re.search(r"g/g × 1[.,]000 → mg/g", text), (
        f"missing the locale-formatted conversion factor: {text!r}"
    )
    # The marker without a usable alt unit has no conversion ("—"), and the
    # marker that requires an explicit unit carries the badge.
    assert "Unit required" in text, (
        f"missing the 'unit required' badge of the catalog markers: {text!r}"
    )


def test_req_hom_126_labs_card_example_dashboard_renders(
    logged_in_page, hass_base_url, hass_bearer_token
):
    """[REQ-HOM-126] The example dashboard renders the labs card in Lovelace."""
    page = logged_in_page
    config = _labs_dashboard_config()
    views = config.get("views") or []
    assert views, "the labs dashboard example must define at least one view"
    view_path = str(views[0].get("path") or "")
    # The shipped example must actually wire the labs card — otherwise the test
    # would render an empty dashboard and prove nothing about the example.
    card_types = [
        str(card.get("type"))
        for view in views
        for card in (view.get("cards") or [])
        if isinstance(card, dict)
    ]
    assert f"custom:{LABS_CARD_TAG}" in card_types, (
        f"{EXAMPLE_LABS_DASHBOARD.name} must contain a 'custom:{LABS_CARD_TAG}' "
        f"card, found: {card_types}"
    )

    # Throwaway storage dashboard (same pattern as test_card_config_e2e.py):
    # unique url_path, deleted again even when the test fails.
    url_path = f"e2e-labs-{uuid.uuid4().hex[:10]}"
    created = _ws_command(
        hass_base_url,
        hass_bearer_token,
        {
            "type": "lovelace/dashboards/create",
            "url_path": url_path,
            "title": "E2E Labs",
            "mode": "storage",
            "show_in_sidebar": False,
            "require_admin": False,
            "icon": "mdi:flask-outline",
        },
    )
    dashboard_id = (created or {}).get("id")
    try:
        _ws_command(
            hass_base_url,
            hass_bearer_token,
            {"type": "lovelace/config/save", "url_path": url_path, "config": config},
        )

        url = f"{hass_base_url}/{url_path}"
        page.goto(f"{url}/{view_path}" if view_path else url)

        # Mount or a diagnosable error card — never a bare timeout.
        page.locator(f"{LABS_CARD_TAG}, hui-error-card").first.wait_for(
            state="attached", timeout=CARD_TIMEOUT
        )
        assert page.locator("hui-error-card").count() == 0, (
            "Lovelace rendered hui-error-card instead of the labs card — is the card "
            f"resource registered (frontend.py)? URL: {page.url}"
        )

        card = page.locator(LABS_CARD_TAG)
        card.locator("ha-card").wait_for(state="visible", timeout=CARD_TIMEOUT)
        card.locator(".labs-title").wait_for(state="visible", timeout=CARD_TIMEOUT)

        # Defaults of the example: disclaimer on, category tabs and one row per
        # marker of the active category — i.e. `panel_data` really reached the
        # card instead of only the empty shell being mounted.
        card.locator(".labs-disclaimer").wait_for(state="visible", timeout=CARD_TIMEOUT)
        card.locator(".labs-tabs button").first.wait_for(state="visible", timeout=CARD_TIMEOUT)
        card.locator(".labs-row").first.wait_for(state="visible", timeout=CARD_TIMEOUT)
        assert card.locator(".labs-error").count() == 0, (
            "the card must not render an error banner for a configured person"
        )
    finally:
        if dashboard_id:
            _ws_command(
                hass_base_url,
                hass_bearer_token,
                {"type": "lovelace/dashboards/delete", "dashboard_id": dashboard_id},
            )

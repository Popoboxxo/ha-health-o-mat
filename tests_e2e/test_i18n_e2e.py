"""E2E: UI internationalisation de/en (REQ-HOM-117) and the error contract (REQ-HOM-127).

The panel and the Lovelace card load their UI strings from Home Assistant's
own translation store (`frontend/get_translations`, categories `common` and
`exceptions`). Both are vanilla web components, so a real browser against a
real HA instance is the only way to verify that `hass.language` actually
switches the rendered labels.

`logged_in_page` runs with `locale=en-US` (the same context as
`english_page`); `english_page` makes that explicit for this i18n coverage.
Server-side data labels (person names, configured quick-drink labels)
remain user data and are intentionally not asserted.

REQ-HOM-127 is verified one level deeper than the object shape: the concept
(§11) demands the **rendered** message, i.e. the catalog text after `{…}`
interpolation, in both languages. Two things can therefore only fail here:

* the wire object of a real failing command (the unit tests fake the
  connection), and
* the pair HA actually ships: the `exceptions` resource for the code plus the
  `translation_placeholders` of the same error object. Asserting the two
  separately would leave the interpolation itself — the only thing a user
  sees — unproven.

The instance language stays `en`; the German text is read through
`frontend/get_translations` with an explicit `language: "de"` argument, which
never changes the instance (shared-instance etiquette). The REQ-HOM-127 checks
only read and trigger commands that are *rejected*, so they write no data. The
shared-instance guard is a per-test `skipif`: the checks are read-only, but a
mislabelled run against loopback:8123 must stay visible instead of silently
"passing" against another project's data.
"""

from __future__ import annotations

import os
import re
from typing import Any

import pytest
from e2e_helpers import (
    ALLOW_SHARED_ENV,
    is_shared_dev_instance,
    wait_for,
    ws_command,
    ws_error,
)
from test_card_config_e2e import CARD_TIMEOUT, _open_card, card_dashboard  # noqa: F401
from test_panel_deeplink_e2e import TAB, open_panel, wait_for_detail

pytestmark = pytest.mark.e2e

PANEL = "health-o-mat-panel"

#: The shared multi-repo dev instance; the module refuses to run there.
SHARED_DEV = (
    is_shared_dev_instance(os.environ.get("HASS_BASE_URL", "http://localhost:8123"))
    and os.environ.get(ALLOW_SHARED_ENV) != "1"
)
SHARED_SKIP = pytest.mark.skipif(
    SHARED_DEV,
    reason=(
        "test_i18n_e2e reads the error contract of the instance it runs on —"
        " point HASS_BASE_URL at the Compose stack (default 8124) or set"
        f" {ALLOW_SHARED_ENV}=1 if that really is a throwaway stack."
    ),
)

#: HA's flat resource prefix for the integration's `exceptions` category.
ERROR_PREFIX = "component.health_o_mat.exceptions."

#: A marker key that cannot exist in any catalog (synthetic, not user data).
UNKNOWN_MARKER = "e2e-unknown-marker-127"

#: The catalog marker used for the batch duplicate (a real, visible marker).
BATCH_MARKER = "alt"

#: An entry id that never exists; hitting it answers with HA's transport
#: `not_found` — a code outside the 35-code catalog (the negative case).
UNKNOWN_ENTRY = "e2e-does-not-exist-127"


def _exception_catalog(base_url: str, token: str, language: str) -> dict[str, str]:
    """The integration's `exceptions` resources for one language, prefix stripped.

    Polls a bounded window for an EMPTY answer only: HA loads translations per
    language into its cache lazily, so a cold instance can answer with no
    resources on the very first call. A catalogue that is genuinely empty keeps
    failing after the window (the `wait_for` assertion names the language), so
    the retry cannot hide a missing translation.
    """

    def read() -> dict[str, str]:
        result = ws_command(
            base_url,
            token,
            {
                "type": "frontend/get_translations",
                "language": language,
                "category": "exceptions",
                "integration": ["health_o_mat"],
            },
        )
        resources = (result or {}).get("resources") or {}
        return {
            key[len(ERROR_PREFIX) :]: value
            for key, value in resources.items()
            if key.startswith(ERROR_PREFIX) and isinstance(value, str)
        }

    return wait_for(
        read,
        bool,
        f"the `exceptions` catalog for language {language!r}",
    )


def _interpolate(template: str, placeholders: dict[str, Any]) -> str:
    """Replace every `{name}` the error object supplies (same rule as the JS)."""

    def replace(match: re.Match[str]) -> str:
        name = match.group(1)
        return str(placeholders[name]) if name in placeholders else match.group(0)

    return re.sub(r"\{([A-Za-z0-9_]+)\}", replace, template)


def test_req_hom_117_panel_renders_english_labels(english_page, hass_base_url, panel_person):
    """[REQ-HOM-117] An en-US browser gets the English panel labels."""
    panel = open_panel(english_page, hass_base_url, person=panel_person["slug"])
    wait_for_detail(panel)

    tabs = panel.locator(TAB)
    labels = [tabs.nth(index).inner_text().strip() for index in range(tabs.count())]
    # `panel_person` enables every area; the lab area is also default-enabled,
    # so its tab (`ui_panel_tab_labs`) belongs to the expected label set.
    assert labels == ["Drinking", "Blood pressure", "Wellbeing", "Lab values"], (
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


@SHARED_SKIP
def test_req_hom_127_error_codes_are_localized(hass_base_url, hass_bearer_token, panel_person):
    """[REQ-HOM-127] A placeholdered error renders as the localized catalog text.

    Two stages, exactly as the concept (§11) requires:

    1. the **object** a failing command delivers: HA's transport code stays in
       `code`, the domain code travels as `translation_key`, the values as
       `translation_placeholders`, and `message` is the neutral fallback;
    2. the **rendered** message: the `exceptions` resource for that same code,
       interpolated with those same placeholders, is the expected sentence in
       `de` and `en` — not the code, not the neutral fallback and not the old
       German prose (``Zeile …``/``unbekannter Marker …``).
    """
    entry_id = panel_person["entry_id"]

    # 1. A rejected lab write (no store mutation) — the code carries a placeholder.
    error = ws_error(
        hass_base_url,
        hass_bearer_token,
        {
            "type": "health_o_mat/add_lab_value",
            "entry_id": entry_id,
            "marker": UNKNOWN_MARKER,
            "value": 1,
        },
    )

    # HA's own transport code is unchanged; the domain code is the translation key.
    assert error["code"] == "invalid_format", f"unexpected transport code: {error!r}"
    assert error["translation_domain"] == "health_o_mat", error
    assert error["translation_key"] == "unknown_marker", error
    assert error["translation_placeholders"] == {"marker": UNKNOWN_MARKER}, error

    # `message` is the neutral, language-free fallback (never the bare code, never prose).
    assert error["message"] == f"unknown_marker (marker={UNKNOWN_MARKER})", error
    assert "Zeile" not in error["message"]

    # 2. The rendered message per language: catalog text + the object's own values.
    expected = {
        "de": f"Unbekannter Marker {UNKNOWN_MARKER}.",
        "en": f"Unknown marker {UNKNOWN_MARKER}.",
    }
    rendered: dict[str, str] = {}
    for language in ("de", "en"):
        catalog = _exception_catalog(hass_base_url, hass_bearer_token, language)
        template = catalog["unknown_marker.message"]
        assert "{marker}" in template, (
            f"the {language} translation must keep the placeholder: {template!r}"
        )
        rendered[language] = _interpolate(template, error["translation_placeholders"])
        assert rendered[language] == expected[language], (
            f"expected the interpolated {language} catalog text, got {rendered[language]!r}"
        )
        # Neither the raw code nor the neutral fallback may be what a user reads.
        assert rendered[language] not in (error["translation_key"], error["message"])
        assert "Zeile" not in rendered[language]

    assert rendered["de"] != rendered["en"], f"de and en must differ, got {rendered['de']!r} twice"


@SHARED_SKIP
def test_req_hom_127_batch_error_envelope_has_no_translation_keys(
    hass_base_url, hass_bearer_token, panel_person
):
    """[REQ-HOM-127] The batch envelope keeps `{code, params, message}` only.

    REQ-HOM-123/132 pin the batch form; the localization of the labs UI happens
    client-side from `code`/`params`. A `translation_*` key on the envelope
    would silently change that contract (and leak the HA transport shape into a
    documented payload), so the exact key set is asserted — with a real,
    all-or-nothing rejected report (nothing is stored).
    """
    result = ws_command(
        hass_base_url,
        hass_bearer_token,
        {
            "type": "health_o_mat/add_lab_report",
            "entry_id": panel_person["entry_id"],
            "values": [
                {"marker": BATCH_MARKER, "value": 101},
                {"marker": BATCH_MARKER, "value": 102},
            ],
        },
    )

    assert result and result.get("ok") is False, (
        f"the duplicate report must be rejected: {result!r}"
    )
    error = result["error"]
    assert set(error) == {"code", "params", "message"}, (
        f"the batch envelope must not carry translation_* keys: {error!r}"
    )
    assert error["code"] == "duplicate_marker", error
    assert error["params"] == {"row": 2, "marker": BATCH_MARKER, "first_row": 1}, error
    # Neutral, language-free template — not the old German prose.
    assert error["message"] == f"duplicate_marker (row=2, marker={BATCH_MARKER}, first_row=1)", (
        error
    )
    assert "Zeile" not in error["message"] and "schon in Zeile" not in error["message"]


@SHARED_SKIP
def test_req_hom_127_unknown_code_falls_back_to_neutral_message(hass_base_url, hass_bearer_token):
    """[REQ-HOM-127] A code outside the catalog keeps its neutral message, no crash.

    The negative case is a *real* error whose code is not one of the 35 catalog
    codes: HA's transport `not_found` for an entry id that never exists. The
    backend must not fabricate `translation_*` fields for it (there is no text
    to resolve), the catalog must have no entry either, and the connection must
    keep working — which is exactly the input the frontend fallback rule
    (`translation_key || code` → catalog → `message`) is defined on.

    The DOM half of that rule is not reachable from the product for an
    uncataloged code (every UI write is pre-validated or answers a catalog
    code); it is covered by the Node assertions of `tests/test_card_js.py` /
    `tests/test_panel_js.py`.
    """
    error = ws_error(
        hass_base_url,
        hass_bearer_token,
        {"type": "health_o_mat/panel_data", "entry_id": UNKNOWN_ENTRY},
    )

    assert error["code"] == "not_found", f"expected HA's transport code, got {error!r}"
    for key in ("translation_domain", "translation_key", "translation_placeholders"):
        assert key not in error, f"an uncataloged code must not carry {key}: {error!r}"
    message = error.get("message")
    assert isinstance(message, str) and message.strip(), (
        f"the neutral message must not be empty: {error!r}"
    )
    assert message != error["code"], "the fallback must not degrade to the bare code"

    # No catalog text exists for the transport code → the renderer must use `message`.
    catalog = _exception_catalog(hass_base_url, hass_bearer_token, "en")
    assert "not_found.message" not in catalog

    # ... and nothing crashed: the same instance still answers a normal command.
    persons = ws_command(hass_base_url, hass_bearer_token, {"type": "health_o_mat/list_persons"})
    assert persons and persons.get("persons"), f"the instance stopped answering: {persons!r}"

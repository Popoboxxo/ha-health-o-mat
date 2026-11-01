"""Fixtures for the Health-O-Mat E2E suite.

These tests drive a REAL, running Home Assistant instance through an actual
browser via Playwright — unlike tests/ (fast, isolated, HA-free unit tests).
The instance only has to be reachable; onboarding, the E2E persons and their
options are prepared by scripts/e2e_bootstrap.py (see `hass_bearer_token` /
`hass_fixtures`), so nothing depends on a human having clicked through the UI.

Run it with:
    HASS_BASE_URL=http://localhost:8123 pytest tests_e2e/ -v
or against the Docker stack:
    docker compose -f docker-compose.e2e.yml up --build \\
        --abort-on-container-exit --exit-code-from e2e
"""

from __future__ import annotations

import os
import re

import pytest

from scripts.e2e_bootstrap import (
    PASSWORD,
    PERSON_DEEP,
    PERSON_TAB,
    USERNAME,
    bootstrap,
    clear_ui_selection,
    ensure_fixtures,
    ensure_non_admin_user,
)

# `hass_base_url` may point at a shared instance; every entry starts at the
# instance root, which redirects to the auth screens when not logged in.
_AUTH_SETTLED = (
    "() => !window.location.pathname.startsWith('/auth/')"
    " && !window.location.href.includes('auth_callback')"
)


@pytest.fixture(scope="session")
def browser_context_args(browser_context_args):
    """English UI + a desktop-sized viewport.

    `hass.language` is the integration's translation source and stays `en` on
    the E2E instance (the backend/user language, not the browser locale), so
    the suite asserts English panel/card texts. The wide viewport keeps HA's
    desktop layout (sidebar visible, no mobile overlay) and gives the panel
    room for its two overview tiles side by side.
    """
    return {
        **browser_context_args,
        "locale": "en-US",
        "viewport": {"width": 1600, "height": 900},
    }


@pytest.fixture(scope="session")
def hass_base_url() -> str:
    """Base URL of the instance under test (`HASS_BASE_URL`)."""
    return os.environ.get("HASS_BASE_URL", "http://localhost:8123").rstrip("/")


@pytest.fixture(scope="session")
def hass_credentials() -> tuple[str, str]:
    """Username/password of the E2E user (env-overridable via the bootstrap)."""
    return USERNAME, PASSWORD


@pytest.fixture(scope="session")
def hass_bearer_token(hass_base_url: str) -> str:
    """Onboard the instance (idempotent) and return an access token.

    Session-scoped, so every test that depends on it (directly or through
    `logged_in_page`) is guaranteed to run against a fully onboarded instance —
    otherwise HA's frontend would bounce every page to /onboarding.html.
    """
    return bootstrap(hass_base_url)


@pytest.fixture(scope="session")
def hass_fixtures(hass_base_url: str, hass_bearer_token: str) -> dict[str, dict]:
    """The persons this suite owns, keyed by their stable slug.

    Creates them (real config flow) and applies the options the panel tests
    need (real options flow) — including `enable_sidebar_panel`, without which
    `/health-o-mat` would not exist at all.
    """
    return ensure_fixtures(hass_base_url, hass_bearer_token)["persons"]


@pytest.fixture(scope="session")
def non_admin(hass_base_url: str, hass_bearer_token: str) -> dict:
    """A real non-admin HA user (`system-users`) plus its access token (#28).

    Created through HA's own `config/auth/create` (idempotently) because the
    onboarding user is the instance owner and therefore always admin — the
    admin gate of the admin-only websocket commands can only be verified
    against a user that actually lacks `is_admin`.

    `ensure_non_admin_user` raises instead of returning a partly usable handle
    (user exists but is admin, login fails, wrong group), so a broken setup
    fails the test loudly instead of skipping the gate assertions.
    """
    return ensure_non_admin_user(hass_base_url, hass_bearer_token)


def _person_ref(person: dict) -> dict:
    return {
        "slug": str(person["person_slug"]),
        "entry_id": str(person["entry_id"]),
        "display_name": str(person["display_name"]),
    }


@pytest.fixture(scope="session")
def panel_person(hass_fixtures: dict[str, dict]) -> dict:
    """Fixture person with every feature area enabled — the deep-link subject."""
    return _person_ref(hass_fixtures[PERSON_DEEP])


@pytest.fixture(scope="session")
def tab_person(hass_fixtures: dict[str, dict]) -> dict:
    """Fixture person with the "bp" area switched off (tab-hiding subject)."""
    return _person_ref(hass_fixtures[PERSON_TAB])


@pytest.fixture(autouse=True)
def reset_panel_selection(hass_base_url, hass_fixtures, hass_bearer_token):
    """Start every test from a clean per-user panel selection.

    The panel persists the last opened person server-side, per HA user
    (`health_o_mat/set_ui_settings`), and resumes it whenever a URL carries no
    usable `person` parameter. Without this reset, whether a test starts on the
    overview or straight inside a person page would depend on what a preceding
    test happened to click — a real flakiness source, not a hypothetical one.

    Depends on `hass_fixtures` purely as a guard: the websocket command only
    exists once the integration is set up (i.e. once at least one person
    exists).
    """
    clear_ui_selection(hass_base_url, hass_bearer_token)


def _login(page, base_url: str, credentials: tuple[str, str]) -> None:
    """Authenticate `page` against the instance (shared by both page fixtures)."""
    page.set_default_timeout(60000)

    username, password = credentials
    page.goto(base_url)

    # Every test gets a fresh browser context (no cookies), so the login form
    # is expected here. Auto-wait on the locator instead of an upfront
    # .count() check: the latter races the SPA's client-side render and would
    # silently skip a login that has not painted yet.
    username_field = page.locator("input[name='username']")
    username_field.wait_for(state="visible", timeout=30000)
    username_field.fill(username)
    password_field = page.locator("input[name='password']")
    password_field.fill(password)
    # Pressing Enter submits the form like a real user would; the submit
    # button is a custom element that does not reliably expose role="button".
    password_field.press("Enter")

    # Wait for the whole auth round-trip, not just for a paint: HA first lands
    # on /?auth_callback=1&code=... and only then rewrites the URL to the
    # dashboard. Returning earlier lets a following goto() re-enter the
    # authorize flow.
    page.wait_for_function(_AUTH_SETTLED, timeout=60000)
    page.wait_for_load_state("networkidle")

    assert not re.search(r"/auth/|auth_callback", page.url), (
        f"login did not complete, still on {page.url!r} — check HASS_USERNAME/"
        f"HASS_PASSWORD (the E2E bootstrap user)"
    )


@pytest.fixture
def logged_in_page(page, hass_base_url, hass_credentials, hass_bearer_token):
    """A Playwright page already authenticated against the instance (en-US).

    The default context uses `locale=en-US`; `hass.language` is `en` on the
    E2E instance, so panel/card labels are English. The bearer token is not
    used directly here — depending on it only forces onboarding to have
    finished before the browser ever loads the page (the token itself is used
    by tests that talk to the REST/WS API).
    """
    _login(page, hass_base_url, hass_credentials)
    return page


@pytest.fixture
def english_page(browser, browser_context_args, hass_base_url, hass_credentials, hass_bearer_token):
    """A second, English (en-US) browser context authenticated like `page`.

    The default context is already English because `hass.language` is `en` on
    the E2E instance; this fixture makes the English assumption explicit and
    isolates the i18n coverage (REQ-HOM-117) without leaking the context.
    """
    context = browser.new_context(**{**browser_context_args, "locale": "en-US"})
    page = context.new_page()
    try:
        _login(page, hass_base_url, hass_credentials)
        yield page
    finally:
        context.close()

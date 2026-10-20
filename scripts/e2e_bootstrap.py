"""Bootstrap a real Home Assistant instance for the Health-O-Mat E2E suite.

Everything the browser tests need is prepared here, without a single UI click:

1. **Onboarding** — HA's onboarding has 4 steps that must ALL be completed
   before the frontend stops redirecting to /onboarding.html (user ->
   core_config -> integration -> analytics). The "integration" step mints the
   auth code that is actually usable for the frontend/API afterwards.
2. **Token** — returned to the tests (and usable for direct REST/WS calls).
3. **Test persons** — one config entry per person (see `PERSON_FIXTURES`) plus
   the options that make the panel tests meaningful (`enable_sidebar_panel`,
   per-person feature areas). The options are written through the REAL options
   flow, because that is exactly the code path the panel registration depends
   on (`health_o_mat/__init__.py` update listener -> `panel.async_apply_panel_state`).

Idempotent by construction: an already onboarded instance (previously
bootstrapped, or onboarded by a human) is reused via a normal password login,
and the persons are looked up by their stable slug (`entry.data["person"]`,
exposed as `person_slug` by `health_o_mat/list_persons`) instead of being
created twice.

Scope guard: only entries whose slug is one of `PERSON_FIXTURES` are ever
touched — foreign config entries (a human's real persons on a shared instance)
are read-only for this script.

Usage:
    python scripts/e2e_bootstrap.py [--base-url http://localhost:8123]
        [--username e2e] [--password ...] [--json-out e2e-state.json]

Note: stdout/`--json-out` contain a live Home Assistant **access token** for the
target instance. Treat it like a password — never commit it, never paste it
into an issue or a log that is kept.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from typing import Any

import requests
from websockets.sync.client import connect

DOMAIN = "health_o_mat"


class BootstrapError(RuntimeError):
    """Raised when the E2E instance could not be prepared."""


class CommandUnavailable(BootstrapError):
    """The integration's websocket API is not registered (yet).

    `health_o_mat/*` websocket commands are registered while the FIRST config
    entry is set up (`__init__.async_setup_entry` -> `ws_api.async_register_ws_api`),
    so on a brand-new instance every websocket call fails with HA's
    `unknown_command` until the first entry exists. Kept as its own error so
    callers can tell "not there yet" apart from "actually broken".
    """


# Credentials for the E2E user. On a fresh instance the bootstrap creates this
# admin account during onboarding; on a reused instance it is the login.
USERNAME = os.environ.get("HASS_USERNAME", "e2e")
PASSWORD = os.environ.get("HASS_PASSWORD", "e2e-bootstrap-password-not-a-secret")

# The two persons the suite owns. Slugs are URL-safe on purpose (no spaces) so
# `?person=<slug>` stays readable in assertions and traces.
#
#   deep — every feature area on, sidebar panel enabled. The deep-link subject.
#   tab  — sidebar panel enabled, "bp" area off: proves that a disabled area
#          hides its detail tab (REQ-HOM-009 + REQ-HOM-012).
PERSON_DEEP = "E2E-Deep"
PERSON_TAB = "E2E-Tab"
PERSON_FIXTURES: tuple[tuple[str, dict[str, bool]], ...] = (
    (PERSON_DEEP, {"drink": True, "bp": True, "wellbeing": True}),
    (PERSON_TAB, {"drink": True, "bp": False, "wellbeing": True}),
)

# Options-flow inputs (the flow validates them against the same schema as the
# UI: 4 quick-drink slots + a "wort=Typ,ml" lexicon, see parser.parse_lexicon_text).
DEFAULT_GOAL_ML = 2000
QUICK_DRINKS: tuple[dict[str, Any], ...] = (
    {"label": "Glas Wasser", "ml": 250, "icon": "mdi:cup-water"},
    {"label": "Flasche Wasser", "ml": 500, "icon": "mdi:bottle-water"},
    {"label": "Kaffee", "ml": 150, "icon": "mdi:coffee"},
    {"label": "Saft", "ml": 200, "icon": "mdi:fruit-citrus"},
)
LEXICON_TEXT = "wasser=Wasser,250\nkaffee=Kaffee,150"

REQUEST_TIMEOUT = 30


# --- low level helpers ------------------------------------------------------


def _client_id(base_url: str) -> str:
    """HA validates client_id as a URL, not an arbitrary string — mirror what
    the frontend/onboarding UI sends (the instance's own origin)."""
    return f"{base_url}/"


def _ws_url(base_url: str) -> str:
    scheme = "wss" if base_url.startswith("https://") else "ws"
    return f"{scheme}://{base_url.split('://', 1)[1].rstrip('/')}/api/websocket"


def _headers(access_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {access_token}"}


def _post_json(url: str, access_token: str, payload: dict[str, Any]) -> dict[str, Any]:
    response = requests.post(
        url, headers=_headers(access_token), json=payload, timeout=REQUEST_TIMEOUT
    )
    response.raise_for_status()
    return response.json()


def _ws_command(base_url: str, access_token: str, payload: dict[str, Any]) -> Any:
    """Run one HA websocket command and return its result.

    Used for the two commands the integration only exposes over the websocket
    API: `health_o_mat/list_persons` (stable slug + entry_id) and
    `health_o_mat/set_ui_settings` (per-user UI state, which the panel resumes
    from when a URL has no `person` parameter).
    """
    with connect(_ws_url(base_url), open_timeout=15, close_timeout=5) as socket:
        hello = json.loads(socket.recv())
        if hello.get("type") != "auth_required":
            raise BootstrapError(f"unexpected websocket greeting: {hello}")

        socket.send(json.dumps({"type": "auth", "access_token": access_token}))
        auth = json.loads(socket.recv())
        if auth.get("type") != "auth_ok":
            raise BootstrapError(f"websocket authentication failed: {auth}")

        socket.send(json.dumps({"id": 1, **payload}))
        while True:
            message = json.loads(socket.recv())
            if message.get("id") != 1:
                continue
            if not message.get("success"):
                error = message.get("error") or {}
                detail = f"websocket command {payload.get('type')!r} failed: {error}"
                if error.get("code") == "unknown_command":
                    raise CommandUnavailable(detail)
                raise BootstrapError(detail)
            return message.get("result")


# --- onboarding -------------------------------------------------------------


def _onboarding_status(base_url: str) -> list[dict[str, Any]] | None:
    """Per-step onboarding status, or None once onboarding is fully finished —
    HA then unregisters the onboarding views entirely (404) instead of
    reporting done=True for every step."""
    response = requests.get(f"{base_url}/api/onboarding", timeout=REQUEST_TIMEOUT)
    if response.status_code == 404:
        return None
    response.raise_for_status()
    return response.json()


def _create_user(base_url: str, username: str, password: str) -> str | None:
    """Create the onboarding admin user. Returns an auth code, or None when the
    user step is already done (existing deployment)."""
    response = requests.post(
        f"{base_url}/api/onboarding/users",
        json={
            "client_id": _client_id(base_url),
            "name": "E2E",
            "username": username,
            "password": password,
            "language": "en",
        },
        timeout=REQUEST_TIMEOUT,
    )
    if response.status_code in (403, 404):
        # 403 "already done" while onboarding is still partially complete; 404
        # once every step is done (the views are gone by then).
        return None
    response.raise_for_status()
    return response.json()["auth_code"]


def _exchange_code_for_token(base_url: str, auth_code: str) -> str:
    response = requests.post(
        f"{base_url}/auth/token",
        data={
            "grant_type": "authorization_code",
            "code": auth_code,
            "client_id": _client_id(base_url),
        },
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    return response.json()["access_token"]


def _login_for_token(base_url: str, username: str, password: str) -> str:
    """Fall back to a normal password login when the user step is already done."""
    flow = requests.post(
        f"{base_url}/auth/login_flow",
        json={
            "client_id": _client_id(base_url),
            "handler": ["homeassistant", None],
            "redirect_uri": f"{base_url}/",
        },
        timeout=REQUEST_TIMEOUT,
    )
    flow.raise_for_status()
    flow_id = flow.json()["flow_id"]

    step = requests.post(
        f"{base_url}/auth/login_flow/{flow_id}",
        json={"username": username, "password": password, "client_id": _client_id(base_url)},
        timeout=REQUEST_TIMEOUT,
    )
    step.raise_for_status()
    return _exchange_code_for_token(base_url, step.json()["result"])


def _finish_onboarding(base_url: str, access_token: str) -> str:
    """Complete whichever onboarding steps are still open; returns a token that
    is valid for the frontend afterwards (the integration step mints a fresh
    auth code, which has to be exchanged again)."""
    status = _onboarding_status(base_url)
    if status is None:
        return access_token

    done = {step["step"] for step in status if step.get("done")}

    if "core_config" not in done:
        requests.post(
            f"{base_url}/api/onboarding/core_config",
            headers=_headers(access_token),
            timeout=REQUEST_TIMEOUT,
        ).raise_for_status()

    if "integration" not in done:
        response = requests.post(
            f"{base_url}/api/onboarding/integration",
            headers=_headers(access_token),
            json={"client_id": _client_id(base_url), "redirect_uri": f"{base_url}/"},
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        access_token = _exchange_code_for_token(base_url, response.json()["auth_code"])

    if "analytics" not in done:
        requests.post(
            f"{base_url}/api/onboarding/analytics",
            headers=_headers(access_token),
            timeout=REQUEST_TIMEOUT,
        ).raise_for_status()

    return access_token


def bootstrap(base_url: str, username: str = USERNAME, password: str = PASSWORD) -> str:
    """Onboard (idempotent) and return an access token for REST/WS/frontend."""
    auth_code = _create_user(base_url, username, password)
    access_token = (
        _exchange_code_for_token(base_url, auth_code)
        if auth_code is not None
        else _login_for_token(base_url, username, password)
    )
    return _finish_onboarding(base_url, access_token)


# --- persons + options ------------------------------------------------------


def list_persons(base_url: str, access_token: str) -> list[dict[str, Any]]:
    """All configured persons (`health_o_mat/list_persons`), slug included."""
    result = _ws_command(base_url, access_token, {"type": f"{DOMAIN}/list_persons"})
    persons = (result or {}).get("persons")
    return persons if isinstance(persons, list) else []


def _list_persons_or_none(base_url: str, access_token: str) -> list[dict[str, Any]] | None:
    """Person list, or None while the integration's WS API is not registered yet."""
    try:
        return list_persons(base_url, access_token)
    except CommandUnavailable:
        return None


def clear_ui_selection(base_url: str, access_token: str) -> None:
    """Forget the panel's per-user "last opened person".

    The panel resumes that selection when the URL carries no `person`
    parameter, so a test that asserts the overview fallback has to start from a
    clean slate — otherwise the choice persisted by an earlier test would win.
    """
    _ws_command(
        base_url,
        access_token,
        {"type": f"{DOMAIN}/set_ui_settings", "selected_person": ""},
    )


def _find_person(persons: list[dict[str, Any]] | None, name: str) -> dict[str, Any] | None:
    for person in persons or []:
        if person.get("person_slug") == name:
            return person
    return None


def _wait_for_person(
    base_url: str, access_token: str, name: str, *, timeout: float = 60.0
) -> dict[str, Any]:
    """Wait until `name` shows up in the person list.

    The config flow returns as soon as the entry exists, while the entry's
    setup (and with it the websocket API registration) still runs; a short poll
    bridges that window without sleeping blindly.
    """
    deadline = time.monotonic() + timeout
    while True:
        person = _find_person(_list_persons_or_none(base_url, access_token), name)
        if person is not None:
            return person
        if time.monotonic() >= deadline:
            raise BootstrapError(
                f"person {name!r} did not appear within {timeout:.0f}s — check the "
                f"Home Assistant log for a failed health_o_mat entry setup"
            )
        time.sleep(1.0)


def _create_person(base_url: str, access_token: str, name: str) -> None:
    """Run the real config flow for one person; an "already configured" abort is
    an expected outcome for a repeated run."""
    flow = _post_json(
        f"{base_url}/api/config/config_entries/flow",
        access_token,
        {"handler": DOMAIN, "show_advanced_options": False},
    )
    result = _post_json(
        f"{base_url}/api/config/config_entries/flow/{flow['flow_id']}",
        access_token,
        {"person": name},
    )
    if result.get("type") not in ("create_entry", "abort"):
        raise BootstrapError(f"config flow for person {name!r} did not finish: {result}")


def _require_form_step(result: dict[str, Any], step_id: str) -> None:
    is_match = result.get("type") == "form" and result.get("step_id") == step_id
    if is_match and not result.get("errors"):
        return
    raise BootstrapError(f"expected options flow step {step_id!r}, got: {result}")


def set_person_options(
    base_url: str,
    access_token: str,
    entry_id: str,
    *,
    enable_panel: bool,
    areas: dict[str, bool],
    goal_ml: int = DEFAULT_GOAL_ML,
) -> None:
    """Configure one person through the real options flow (init -> quick_drinks
    -> drink_lexicon). `enable_panel` is the opt-in that registers the sidebar
    panel; the update listener reacts to it (`panel.async_apply_panel_state`)."""
    base = f"{base_url}/api/config/config_entries/options/flow"
    flow = _post_json(base, access_token, {"handler": entry_id})
    flow_id = flow["flow_id"]
    _require_form_step(flow, "init")

    flow = _post_json(
        f"{base}/{flow_id}",
        access_token,
        {
            "daily_goal_ml": goal_ml,
            "daily_reset_hour": 0,
            "retention_months": 0,
            "enable_sidebar_panel": enable_panel,
            "area_drink": areas.get("drink", True),
            "area_bp": areas.get("bp", True),
            "area_wellbeing": areas.get("wellbeing", True),
        },
    )
    _require_form_step(flow, "quick_drinks")

    quick: dict[str, Any] = {}
    for index, drink in enumerate(QUICK_DRINKS):
        quick[f"quick_{index}_label"] = drink["label"]
        quick[f"quick_{index}_ml"] = drink["ml"]
        quick[f"quick_{index}_icon"] = drink["icon"]

    flow = _post_json(f"{base}/{flow_id}", access_token, quick)
    _require_form_step(flow, "drink_lexicon")

    flow = _post_json(f"{base}/{flow_id}", access_token, {"drink_lexicon": LEXICON_TEXT})
    if flow.get("type") != "create_entry":
        raise BootstrapError(f"options flow for entry {entry_id} did not finish: {flow}")


def ensure_person(
    base_url: str,
    access_token: str,
    name: str,
    *,
    enable_panel: bool = True,
    areas: dict[str, bool] | None = None,
) -> dict[str, Any]:
    """Look up or create one person fixture, then apply its options."""
    person = _find_person(_list_persons_or_none(base_url, access_token), name)
    if person is None:
        _create_person(base_url, access_token, name)
        person = _wait_for_person(base_url, access_token, name)

    set_person_options(
        base_url,
        access_token,
        str(person["entry_id"]),
        enable_panel=enable_panel,
        areas=areas if areas is not None else {"drink": True, "bp": True, "wellbeing": True},
    )
    return person


def ensure_fixtures(base_url: str, access_token: str) -> dict[str, Any]:
    """Ensure both E2E persons exist and are configured; return their state."""
    names = {name for name, _areas in PERSON_FIXTURES}
    for name, areas in PERSON_FIXTURES:
        ensure_person(base_url, access_token, name, enable_panel=True, areas=areas)

    # Re-read after configuring: the list is the authoritative view (applied
    # areas included) and the tests assert against exactly these fields.
    persons = {
        person["person_slug"]: person
        for person in list_persons(base_url, access_token)
        if person.get("person_slug") in names
    }
    missing = names - set(persons)
    if missing:
        raise BootstrapError(f"person fixtures missing after setup: {sorted(missing)}")
    return {
        "base_url": base_url,
        "username": USERNAME,
        "token": access_token,
        "persons": persons,
        "panel_person": PERSON_DEEP,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base-url", default=os.environ.get("HASS_BASE_URL", "http://localhost:8123")
    )
    parser.add_argument("--username", default=USERNAME)
    parser.add_argument("--password", default=PASSWORD)
    parser.add_argument("--json-out", help="write the bootstrap result to this file")
    parser.add_argument(
        "--no-persons",
        action="store_true",
        help="only onboard and mint a token, do not create/configure the E2E persons",
    )
    args = parser.parse_args(argv)

    base_url = args.base_url.rstrip("/")
    try:
        token = bootstrap(base_url, args.username, args.password)
        state: dict[str, Any] = {"base_url": base_url, "username": args.username, "token": token}
        if not args.no_persons:
            state = ensure_fixtures(base_url, token)
    except Exception as exc:  # noqa: BLE001 - CLI error path
        print(f"e2e_bootstrap failed: {exc}", file=sys.stderr)
        return 1

    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as handle:
            json.dump(state, handle, indent=2)
    print(json.dumps(state, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

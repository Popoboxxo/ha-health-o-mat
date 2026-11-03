"""Shared polling/websocket helpers for the E2E suite.

Every assertion on a write has to bridge two asynchronous windows of the live
instance:

1. the **write path** itself (service/WS write -> store write -> coordinator
   refresh -> entity state), and
2. the **entry reload window**: saving options triggers
   ``hass.config_entries.async_reload`` (``__init__._options_updated``), so for
   a moment ``hass.data[DOMAIN][entry_id]`` is gone and every ``health_o_mat/*``
   command that resolves a person answers ``not_found`` ("Unbekannte oder nicht
   geladene Person", ``ws_api._send_entry_error``).

(2) is expected product behaviour, not a defect — but a naive poll treats the
first answer of that window as the final one and aborts. The helpers below
therefore handle **only** that transient window:

* ``wait_for_entry_loaded`` gates every step that follows an options write: it
  polls HA's config-entry state until the entry is ``loaded`` again.
* ``wait_for`` counts a transient reload answer as "not yet" and keeps polling
  (it is the same polling loop as for a store write).
* ``ws_command`` retries a one-shot read that lands in the window, bounded by
  ``RELOAD_RETRY_TIMEOUT``.
* ``call_service`` does the same for a ``health_o_mat/*`` service call, which
  answers ``HTTP 500`` (``ServiceValidationError: Person '<slug>' nicht
  gefunden``) instead of a websocket error code; retries there are tied to the
  observable reload state, not to a blanket timeout.

Everything else — including a permanently unknown ``entry_id``, which answers
with the same ``not_found``, and a wrong person name, which answers with the
same ``Person '<slug>' nicht gefunden`` — exhausts the retry and then raises as
before, so no real failure is swallowed.
"""

from __future__ import annotations

import json
import os
import pathlib
import subprocess
import time
import urllib.parse
from collections.abc import Callable, Sequence
from typing import Any

import requests
from websockets.sync.client import connect

from scripts.e2e_bootstrap import BootstrapError, _headers, _ws_command, _ws_url

# Default poll window for an asynchronous write (shared with the E2E tests).
WRITE_TIMEOUT = 45.0

# Bounded retry window for a one-shot read that hits an entry reload.
RELOAD_RETRY_TIMEOUT = 10.0
RELOAD_RETRY_INTERVAL = 0.25

# The transient reload answer: HA's error code plus the integration's message.
# Matching BOTH keeps unrelated `not_found` answers (e.g. a typo'd command)
# out of the retry path.
_TRANSIENT_CODE = "not_found"
_TRANSIENT_MESSAGE = "Unbekannte oder nicht geladene Person"


def is_transient_reload_error(exc: BaseException) -> bool:
    """Whether `exc` is the expected "person entry is being reloaded" answer.

    ``scripts.e2e_bootstrap.BootstrapError`` carries only the formatted message
    (``"websocket command '<type>' failed: {...}"``), so the check matches the
    two identifying fragments of ``ws_api._send_entry_error``.
    """
    if not isinstance(exc, BootstrapError):
        return False
    text = str(exc)
    return _TRANSIENT_CODE in text and _TRANSIENT_MESSAGE in text


def wait_for(
    read: Callable[[], Any],
    condition: Callable[[Any], bool],
    description: str,
    *,
    timeout: float = WRITE_TIMEOUT,
    interval: float = 0.4,
) -> Any:
    """Poll `read()` until `condition` is true, else fail with the last value.

    The live instance is asynchronous (service call -> store write -> coordinator
    refresh -> entity state), so every assertion on a write has to bridge that
    window instead of reading once and hoping.

    A transient reload-window error from `read()` counts as "not yet" — the
    option save that triggered the reload is exactly what the caller is waiting
    for. Any other exception is re-raised immediately; a wrong ``entry_id``
    keeps answering ``not_found``, exhausts the timeout and still fails hard.
    """
    deadline = time.monotonic() + timeout
    last: Any = None
    while time.monotonic() < deadline:
        try:
            last = read()
        except BootstrapError as exc:
            if not is_transient_reload_error(exc):
                raise
            last = exc
        else:
            if condition(last):
                return last
        time.sleep(interval)
    raise AssertionError(f"timed out after {timeout:g}s waiting for {description} (last: {last!r})")


def ws_command(
    base_url: str,
    token: str,
    payload: dict[str, Any],
    *,
    timeout: float = RELOAD_RETRY_TIMEOUT,
    interval: float = RELOAD_RETRY_INTERVAL,
) -> Any:
    """Run one HA websocket command, retrying the transient reload window.

    One-shot reads (``get_settings`` / ``panel_data`` / ``list_history``) and
    writes outside a ``wait_for`` poll would otherwise break on the first call
    that lands in the reload window. Only the transient ``not_found`` above is
    retried, bounded by `timeout`; every other error — and a permanent
    ``not_found`` such as a wrong ``entry_id`` — raises instead of returning an
    empty payload. Retrying is safe for the writes that use it here: a command
    rejected with ``not_found`` never reached the store, and the setters
    (``set_settings`` / ``set_wellbeing``) are idempotent.
    """
    deadline = time.monotonic() + timeout
    while True:
        try:
            return _ws_command(base_url, token, payload)
        except BootstrapError as exc:
            if not is_transient_reload_error(exc) or time.monotonic() >= deadline:
                raise
        time.sleep(interval)


def _ws_error_once(base_url: str, token: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Run one websocket command that is EXPECTED to fail; return its `error`."""
    with connect(_ws_url(base_url), open_timeout=15, close_timeout=5) as socket:
        hello = json.loads(socket.recv())
        if hello.get("type") != "auth_required":
            raise AssertionError(f"unexpected websocket greeting: {hello}")
        socket.send(json.dumps({"type": "auth", "access_token": token}))
        auth = json.loads(socket.recv())
        if auth.get("type") != "auth_ok":
            raise AssertionError("websocket authentication failed")
        socket.send(json.dumps({"id": 1, **payload}))
        while True:
            message = json.loads(socket.recv())
            if message.get("id") != 1:
                continue
            if message.get("success"):
                raise AssertionError(
                    f"websocket command {payload.get('type')!r} was expected to fail,"
                    f" but succeeded: {message.get('result')!r}"
                )
            error = message.get("error")
            if not isinstance(error, dict):
                raise AssertionError(
                    f"websocket command {payload.get('type')!r} answered without an"
                    f" `error` object: {message!r}"
                )
            return error


def ws_error(
    base_url: str,
    token: str,
    payload: dict[str, Any],
    *,
    timeout: float = RELOAD_RETRY_TIMEOUT,
    interval: float = RELOAD_RETRY_INTERVAL,
) -> dict[str, Any]:
    """Run one failing websocket command and return the RAW `error` object.

    `_ws_command` deliberately collapses a failure into a formatted
    `BootstrapError`; the error contract (REQ-HOM-127) is about the object
    itself (`code`, `message`, `translation_*`), so the E2E assertions need the
    unchanged payload HA delivered. Expecting a failure is asserted, not
    assumed: a command that succeeds raises instead of returning `{}`.

    The transient entry-reload answer (``not_found`` for a person that is being
    reloaded) is retried exactly like `ws_command`, so a rejected command never
    fails the test just because an options write of the preceding test is still
    reloading. Any other error — including a permanent ``not_found`` — is
    returned as-is for the caller to assert on.
    """
    deadline = time.monotonic() + timeout
    while True:
        error = _ws_error_once(base_url, token, payload)
        # Same identifiers as `is_transient_reload_error`, read from the raw
        # object instead of the formatted BootstrapError.
        transient = error.get("code") == _TRANSIENT_CODE and _TRANSIENT_MESSAGE in str(
            error.get("message") or ""
        )
        if not transient or time.monotonic() >= deadline:
            return error
        time.sleep(interval)


# ---------------------------------------------------------------------------
# Entry-reload gate (REQ-HOM-101 AK1)
#
# Saving options can schedule ``hass.config_entries.async_reload``
# (``__init__._options_updated``: a changed quick-drink set or area set). The
# entry then leaves ``loaded``, drops ``hass.data[DOMAIN][entry_id]`` and sets up
# again — a service call or entity write issued in between answers "person not
# found". The reload is *scheduled*, so it can also start a moment after the
# options write returned: callers therefore gate on the entry state instead of
# sleeping, and `call_service` keeps that gate for the write itself.
# ---------------------------------------------------------------------------

#: A reload re-runs the whole entry setup (store load, platform forwarding), so
#: the gate gets a generous window — never a fixed sleep.
ENTRY_RELOAD_TIMEOUT = 60.0


def config_entry_state(base_url: str, token: str, entry_id: str) -> str | None:
    """`state` of one config entry (`loaded`, `setup_in_progress`, ...).

    ``None`` means the entry does not exist (deleted). HA's per-entry REST
    resource only supports POST/DELETE here, so the state is read from the
    collection view and selected by `entry_id`.
    """
    response = requests.get(
        f"{base_url}/api/config/config_entries/entry",
        headers=_headers(token),
        timeout=30,
    )
    response.raise_for_status()
    for entry in response.json():
        if entry.get("entry_id") == entry_id:
            return str(entry.get("state") or "") or None
    return None


def wait_for_entry_loaded(
    base_url: str,
    token: str,
    entry_id: str,
    *,
    timeout: float = ENTRY_RELOAD_TIMEOUT,
) -> str:
    """Block until the config entry is `loaded` again (no reload in flight).

    Must be called after every options write that can change the entity set
    (bootstrap ``ensure_person``, the options flow) before the test talks to
    *this* person again. While a reload runs, HA serves
    ``setup_in_progress``/``unload_in_progress``/``not_loaded``; those are
    rejected, and an entry that never comes back raises with the observed
    state instead of silently proceeding.
    """
    return str(
        wait_for(
            lambda: config_entry_state(base_url, token, entry_id),
            lambda state: state == "loaded",
            f"config entry {entry_id} to be loaded again (an options write reloads the entry)",
            timeout=timeout,
        )
    )


def call_service(
    base_url: str,
    token: str,
    domain: str,
    service: str,
    data: dict[str, Any],
    *,
    entry_id: str | None = None,
    timeout: float = RELOAD_RETRY_TIMEOUT,
) -> Any:
    """Call one real service, surviving the entry-reload window.

    A ``health_o_mat/*`` call that lands in the reload window fails with a bare
    ``HTTP 500`` (``ServiceValidationError: Person '<slug>' nicht gefunden`` from
    ``get_runtime_data``: the person's runtime registry entry is gone). That
    request never reached the store, so repeating it cannot book twice.

    The retry is tied to the **observable** window, not to a blanket timeout:
    while the entry is not ``loaded`` (requires `entry_id`) the call is
    retried; once the entry is loaded again at most **one** confirmation
    attempt follows — a genuinely wrong person name produces the same 500 and
    is then raised. Every other status is raised immediately, so no real
    failure is delayed or swallowed.
    """
    url = f"{base_url}/api/services/{domain}/{service}"
    deadline = time.monotonic() + timeout
    confirmed_after_recovery = False
    while True:
        response = requests.post(url, headers=_headers(token), json=data, timeout=60)
        if response.status_code != 500 or entry_id is None:
            response.raise_for_status()
            return response.json() if response.content.strip() else None
        state = config_entry_state(base_url, token, entry_id)
        if state != "loaded" and time.monotonic() < deadline:
            pass  # still unloading/setting up -> retry below
        elif state == "loaded" and not confirmed_after_recovery:
            # The window may have closed between the call and this read: give
            # the request exactly one more chance instead of guessing.
            confirmed_after_recovery = True
        else:
            response.raise_for_status()
        time.sleep(RELOAD_RETRY_INTERVAL)


# ---------------------------------------------------------------------------
# Instance control: restart-based scenarios (REQ-HOM-101 AK4, REQ-HOM-104)
#
# Two gaps need the *process* to go away and come back — a half-filled BP entry
# has to survive a restart (REQ-HOM-104), and a legacy config entry is only
# migrated while the entry is set up (REQ-HOM-101 AK4). An entry reload is not a
# substitute: the store, the entity registry and the config-entry migration all
# read from disk exactly once per HA start.
#
# Everything below is deliberately optional. Inside the Compose `e2e` runner
# there is no Docker socket and no `/config` bind mount, so the callers skip with
# an explicit reason instead of pretending to pass. On the host (the documented
# `HASS_BASE_URL=http://127.0.0.1:8124 pytest tests_e2e/` run) the container is
# discovered and verified against `HASS_BASE_URL` before anything is touched.
# ---------------------------------------------------------------------------

#: The shared multi-repo dev instance. Never a target for restarting/storage
#: rewriting tests (see the module guards in the test modules).
SHARED_DEV_PORT = 8123
LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1", "[::1]"})
ALLOW_SHARED_ENV = "HASS_ALLOW_PORT_8123"

#: Compose project/service of the E2E stack (`docker-compose.e2e.yml`).
COMPOSE_PROJECT = "health-o-mat-e2e"
COMPOSE_SERVICE = "homeassistant"

#: Explicit container name override (a renamed project, a second stack).
CONTAINER_ENV = "HASS_E2E_CONTAINER"

#: HA's config directory as a host bind mount (`docker-compose.e2e.yml`).
_HOST_CONFIG_RELATIVE = pathlib.Path("docker") / "ha_config_e2e"

#: How long a restart may take before the helper calls it a failure.
RESTART_TIMEOUT = 240.0

_REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent


def is_shared_dev_instance(base_url: str) -> bool:
    """Whether `base_url` addresses the shared instance (loopback:8123).

    Deliberately host-aware: inside the Compose network the stack is reached as
    ``http://homeassistant:8123``, which is a throwaway instance and must run.
    """
    parsed = urllib.parse.urlsplit(base_url)
    return (parsed.hostname or "") in LOOPBACK_HOSTS and (
        parsed.port or (443 if parsed.scheme == "https" else 80)
    ) == SHARED_DEV_PORT


def _port_of(base_url: str) -> int:
    parsed = urllib.parse.urlsplit(base_url)
    return parsed.port or (443 if parsed.scheme == "https" else 80)


def _docker(*args: str, timeout: float = 60.0) -> subprocess.CompletedProcess[str]:
    """Run one docker CLI call, capturing stdout/stderr for the error path."""
    return subprocess.run(
        ["docker", *args],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def compose_container(base_url: str, *, timeout: float = 30.0) -> str | None:
    """Name of the Compose HA container behind `base_url`, or None.

    ``None`` means "this environment cannot restart the instance" (no docker CLI,
    no matching container) and is reported to the caller as a skip reason, never
    as a silent pass. The published port is compared against `base_url`, so a
    stack running next to the shared instance can never be restarted by accident.
    """
    override = os.environ.get(CONTAINER_ENV)
    if override:
        return override
    try:
        listing = _docker(
            "ps",
            "--format",
            '{{.Names}}\t{{.Label "com.docker.compose.project"}}'
            '\t{{.Label "com.docker.compose.service"}}',
            timeout=timeout,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if listing.returncode != 0:
        return None
    candidates = [
        name
        for name, project, service in (
            line.split("\t") for line in listing.stdout.splitlines() if line.count("\t") == 2
        )
        if project == COMPOSE_PROJECT and service == COMPOSE_SERVICE
    ]
    for name in candidates:
        ports = _docker("port", name, "8123/tcp", timeout=timeout)
        published = {part.rsplit(":", 1)[-1] for part in ports.stdout.split() if ":" in part}
        if ports.returncode == 0 and str(_port_of(base_url)) in published:
            return name
    return None


def host_config_dir(base_url: str) -> pathlib.Path | None:
    """Host view of HA's `/config` for the Compose stack, or None.

    The bind mount is declared in `docker-compose.e2e.yml`. It only exists for a
    host-side run; inside the `e2e` runner container this returns None.
    """
    if compose_container(base_url) is None:
        return None
    path = _REPO_ROOT / _HOST_CONFIG_RELATIVE
    return path if path.is_dir() else None


def _wait_for_api(base_url: str, *, timeout: float) -> None:
    """Poll until HA's HTTP stack answers again (any non-5xx answer counts)."""
    deadline = time.monotonic() + timeout
    last = "no response yet"
    while time.monotonic() < deadline:
        try:
            response = requests.get(f"{base_url}/api/", timeout=5)
        except requests.RequestException as err:
            last = f"{type(err).__name__}: {err}"
        else:
            # 401 is the expected answer to an unauthenticated probe: it proves
            # the HTTP layer (and therefore HA's web server) is back.
            if response.status_code in (200, 401):
                return
            last = f"HTTP {response.status_code}"
        time.sleep(1.0)
    raise AssertionError(
        f"Home Assistant at {base_url} did not answer within {timeout:g}s after the"
        f" restart (last: {last})"
    )


def restart_home_assistant(
    container: str, base_url: str, *, timeout: float = RESTART_TIMEOUT
) -> None:
    """Stop + start the E2E container and wait until the API answers again.

    Blocks until HA's web server is back. Entities/entries are asserted
    separately by `wait_for_instance_ready` — this function only proves the
    process restart happened, so a slow entity setup cannot look like a restart
    failure (and vice versa).
    """
    stop_home_assistant(container, timeout=timeout)
    start_home_assistant(container, base_url, timeout=timeout)


def stop_home_assistant(container: str, *, timeout: float = RESTART_TIMEOUT) -> None:
    """Gracefully stop the E2E container (HA flushes `.storage` on shutdown)."""
    result = _docker("stop", "--time", "30", container, timeout=timeout)
    if result.returncode != 0:
        raise AssertionError(
            f"docker stop {container} failed (rc={result.returncode}):"
            f" {(result.stderr or result.stdout).strip()}"
        )


def start_home_assistant(
    container: str, base_url: str, *, timeout: float = RESTART_TIMEOUT
) -> None:
    """Start the E2E container and wait until HA's API answers again."""
    result = _docker("start", container, timeout=timeout)
    if result.returncode != 0:
        raise AssertionError(
            f"docker start {container} failed (rc={result.returncode}):"
            f" {(result.stderr or result.stdout).strip()}"
        )
    _wait_for_api(base_url, timeout=timeout)


def wait_for_instance_ready(
    base_url: str,
    token: str,
    entity_ids: Sequence[str],
    *,
    timeout: float = RESTART_TIMEOUT,
) -> dict[str, Any]:
    """Poll until HA is up AND every given entity has a real (non-unavailable) state.

    A restarted HA answers HTTP long before its config entries are set up, so the
    entity states are the only honest readiness signal. Returns the last observed
    states so the caller can assert on them directly.
    """
    deadline = time.monotonic() + timeout
    last: dict[str, Any] = {}
    while time.monotonic() < deadline:
        states: dict[str, Any] = {}
        for entity_id in entity_ids:
            response = requests.get(
                f"{base_url}/api/states/{entity_id}", headers=_headers(token), timeout=10
            )
            if response.status_code != 200:
                states[entity_id] = f"HTTP {response.status_code}"
                continue
            states[entity_id] = response.json()
        ready = all(
            isinstance(state, dict) and state.get("state") not in (None, "", "unavailable")
            for state in states.values()
        )
        last = states
        if ready:
            return last
        time.sleep(1.0)
    missing = {key: value for key, value in last.items() if not isinstance(value, dict)}
    raise AssertionError(
        f"entities did not become available within {timeout:g}s after the restart"
        f" (last: {last!r}, unresolved: {missing!r})"
    )

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
first answer of that window as the final one and aborts. Both helpers below
therefore retry **only** that exact transient answer:

* ``wait_for`` counts it as "not yet" and keeps polling (it is the same polling
  loop as for a store write).
* ``ws_command`` retries a one-shot read that lands in the window, bounded by
  ``RELOAD_RETRY_TIMEOUT``.

Everything else — including a permanently unknown ``entry_id``, which answers
with the same ``not_found`` — exhausts the retry and then raises as before, so
no real failure is swallowed.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

from scripts.e2e_bootstrap import BootstrapError, _ws_command

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

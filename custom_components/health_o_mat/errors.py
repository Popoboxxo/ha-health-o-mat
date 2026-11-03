"""Home Assistant adapters for the error catalog (REQ-HOM-127).

The catalog itself lives in :mod:`logic` and stays HA-free. This module is the
only place that projects it onto HA transport channels:

* :func:`validation_error` -> :class:`ServiceValidationError` (service calls),
* :func:`send_ws_error` -> ``connection.send_error`` (custom WS commands),
* :func:`relay_error` -> code-preserving relay of a raised exception.

``code == translation_key`` holds on every channel. ``params`` stay typed in
the catalog; only the HA projection stringifies them (``{k: str(v)}``).
"""

from __future__ import annotations

import inspect
from collections.abc import Mapping
from typing import Any

from homeassistant.exceptions import ServiceValidationError

from . import logic

TRANSLATION_DOMAIN = "health_o_mat"

# Per-connection-class cache: does ``send_error`` accept ``translation_*``?
# HA 2026.9 added the keyword arguments; older/foreign connections only take
# ``(msg_id, code, message)``. Probing once per class keeps the hot path cheap.
TRANSLATION_KWARGS_SUPPORTED: dict[type, bool] = {}


def _translation_kwargs(error: Mapping[str, Any]) -> dict[str, Any]:
    """HA projection: stringified placeholders for one built error object."""
    return {
        "translation_domain": TRANSLATION_DOMAIN,
        "translation_key": error["code"],
        "translation_placeholders": {key: str(value) for key, value in error["params"].items()},
    }


def validation_error(code: str, params: Mapping[str, Any] | None = None) -> ServiceValidationError:
    """Build the service-call exception for a catalog code (§5.2).

    The positional argument is the neutral catalog message so ``str(err)``
    stays readable in logs even before translations are loaded; the
    ``translation_*`` fields make the error localizable for the HA UI.
    """
    error = logic.build_error(code, params)
    return ServiceValidationError(
        error["message"],
        translation_domain=TRANSLATION_DOMAIN,
        translation_key=code,
        translation_placeholders={key: str(value) for key, value in error["params"].items()},
    )


def _supports_translation_kwargs(connection: Any) -> bool:
    """Whether ``connection.send_error`` accepts ``translation_*`` kwargs.

    Fail-open: an uninspectable signature is treated as supporting the kwargs
    (the actual call then falls back on ``TypeError``). Connections with an
    explicit ``**kwargs`` parameter are supported as well.
    """
    connection_class = type(connection)
    cached = TRANSLATION_KWARGS_SUPPORTED.get(connection_class)
    if cached is not None:
        return cached

    try:
        parameters = inspect.signature(connection.send_error).parameters
    except (TypeError, ValueError):
        supported = True
    else:
        supported = "translation_domain" in parameters or any(
            parameter.kind is inspect.Parameter.VAR_KEYWORD for parameter in parameters.values()
        )
    TRANSLATION_KWARGS_SUPPORTED[connection_class] = supported
    return supported


def _send(
    connection: Any,
    msg_id: Any,
    ha_code: str,
    message: str,
    kwargs: dict[str, Any],
) -> None:
    """Send with ``translation_*`` when supported, else 3-arg (fail-open)."""
    if kwargs and _supports_translation_kwargs(connection):
        try:
            connection.send_error(msg_id, ha_code, message, **kwargs)
        except TypeError:
            # Signature lied (or a wrapped callable rejected the kwargs):
            # remember that and fall back to the transport-only form.
            TRANSLATION_KWARGS_SUPPORTED[type(connection)] = False
        else:
            return
    connection.send_error(msg_id, ha_code, message)


def send_ws_error(
    connection: Any,
    msg_id: Any,
    ha_code: str,
    code: str,
    params: Mapping[str, Any] | None = None,
) -> None:
    """Send a custom-WS error with the catalog code as ``translation_key`` (§5.3).

    ``ha_code`` stays HA's transport code (``invalid_format``, ``not_found``,
    …) and is never overloaded with the domain code.
    """
    error = logic.build_error(code, params)
    _send(
        connection,
        msg_id,
        ha_code,
        error["message"],
        _translation_kwargs(error),
    )


def relay_error(
    connection: Any,
    msg_id: Any,
    ha_code: str,
    err: BaseException,
) -> None:
    """Relay an already-raised exception, keeping its own translation fields.

    Used by the code-preserving relay sites (§7.7): the transport code is
    supplied by the caller, the payload is the exception message, and any
    ``translation_*`` fields on *err* are forwarded when present.
    """
    translation_domain = getattr(err, "translation_domain", None)
    translation_key = getattr(err, "translation_key", None)
    kwargs: dict[str, Any] = {}
    if translation_domain and translation_key:
        placeholders = getattr(err, "translation_placeholders", None)
        kwargs = {
            "translation_domain": translation_domain,
            "translation_key": translation_key,
            "translation_placeholders": dict(placeholders or {}),
        }
    _send(connection, msg_id, ha_code, str(err), kwargs)

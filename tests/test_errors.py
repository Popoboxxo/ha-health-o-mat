"""Tests for the Home Assistant error adapters (REQ-HOM-127).

``errors`` projects the HA-free catalog (``logic.build_error``) onto the three
HA transport channels: ``ServiceValidationError`` for services,
``connection.send_error`` for custom websocket commands and the passthrough
``relay_error`` for code-preserving relay sites.
"""

from __future__ import annotations

from homeassistant.exceptions import HomeAssistantError, ServiceValidationError

from custom_components.health_o_mat import errors, logic


class FakeConnection:
    """Connection that accepts and records ``translation_*`` keyword arguments."""

    def __init__(self) -> None:
        self.errors: list[tuple] = []
        self.error_kwargs: list[tuple] = []

    def send_error(self, msg_id, code, message, **kwargs) -> None:
        self.errors.append((msg_id, code, message))
        if kwargs:
            self.error_kwargs.append((msg_id, kwargs))


class LegacyConnection:
    """Connection with the pre-2026.9 three-argument ``send_error`` signature."""

    def __init__(self) -> None:
        self.errors: list[tuple] = []

    def send_error(self, msg_id, code, message) -> None:
        self.errors.append((msg_id, code, message))


def test_translation_domain_is_the_integration_domain() -> None:
    assert errors.TRANSLATION_DOMAIN == "health_o_mat"


def test_validation_error_carries_code_params_and_fallback() -> None:
    err = errors.validation_error("amount_out_of_range", {"min": 1, "max": 10000})

    assert isinstance(err, ServiceValidationError)
    assert str(err) == logic.build_error("amount_out_of_range", {"min": 1, "max": 10000})["message"]
    assert err.translation_domain == "health_o_mat"
    assert err.translation_key == "amount_out_of_range"
    assert err.translation_placeholders == {"min": "1", "max": "10000"}


def test_validation_error_placeholders_are_str() -> None:
    err = errors.validation_error("amount_out_of_range", {"min": 1, "max": 10000})

    assert err.translation_placeholders is not None
    assert all(isinstance(value, str) for value in err.translation_placeholders.values())


def test_validation_error_drops_undeclared_params() -> None:
    err = errors.validation_error("offset_invalid", {"secret": "x"})

    assert err.translation_key == "offset_invalid"
    assert err.translation_placeholders == {}


def test_send_ws_error_keeps_transport_code() -> None:
    connection = FakeConnection()

    errors.send_ws_error(connection, 7, "invalid_format", "unknown_marker", {"marker": "x"})

    assert connection.errors == [(7, "invalid_format", "unknown_marker (marker=x)")]
    assert connection.error_kwargs == [
        (
            7,
            {
                "translation_domain": "health_o_mat",
                "translation_key": "unknown_marker",
                "translation_placeholders": {"marker": "x"},
            },
        )
    ]


def test_send_ws_error_falls_back_without_kwargs() -> None:
    connection = LegacyConnection()

    errors.send_ws_error(connection, 8, "invalid_format", "offset_invalid")

    assert connection.errors == [(8, "invalid_format", "offset_invalid")]


def test_send_ws_error_caches_signature_support_per_class() -> None:
    connection = FakeConnection()

    errors.send_ws_error(connection, 1, "invalid_format", "offset_invalid")
    errors.send_ws_error(connection, 2, "invalid_format", "offset_invalid")

    assert len(connection.error_kwargs) == 2


def test_relay_error_forwards_translation_fields() -> None:
    connection = FakeConnection()
    err = HomeAssistantError(
        "boom",
        translation_domain="health_o_mat",
        translation_key="restore_failed",
        translation_placeholders={"detail": "x"},
    )

    errors.relay_error(connection, 9, "restore_failed", err)

    assert connection.errors == [(9, "restore_failed", "boom")]
    assert connection.error_kwargs == [
        (
            9,
            {
                "translation_domain": "health_o_mat",
                "translation_key": "restore_failed",
                "translation_placeholders": {"detail": "x"},
            },
        )
    ]


def test_relay_error_plain_exception_has_no_kwargs() -> None:
    connection = FakeConnection()

    errors.relay_error(connection, 10, "export_failed", RuntimeError("boom"))

    assert connection.errors == [(10, "export_failed", "boom")]
    assert connection.error_kwargs == []

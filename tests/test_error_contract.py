"""Tests for the HA-free error catalog and ``logic.build_error`` (REQ-HOM-127).

The catalog is the single source of truth for every user-visible error code
(§5.1/§6 of the error-contract design). These tests are HA-free on purpose:
``logic`` imports neither ``homeassistant`` nor any adapter module, so the
contract can be pinned without the fake-HA scaffolding.
"""

from __future__ import annotations

import re

import pytest

from custom_components.health_o_mat import logic

CATALOG_SIZE = 35
CODE_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")
PLACEHOLDER_PATTERN = re.compile(r"\{([a-z][a-z0-9_]*)\}")
FORBIDDEN_PARAM_NAMES = frozenset({"person", "note", "comment", "name"})


def _templates(spec: dict) -> list[str]:
    return [template for template in (spec["template"], spec["row_template"]) if template]


def test_catalog_has_35_unique_snake_case_codes() -> None:
    assert len(logic.ERROR_SPECS) == CATALOG_SIZE
    assert len(set(logic.ERROR_SPECS)) == CATALOG_SIZE
    for code in logic.ERROR_SPECS:
        assert CODE_PATTERN.match(code), code


def test_catalog_params_are_declared_tuples() -> None:
    for code, spec in logic.ERROR_SPECS.items():
        assert isinstance(spec["params"], tuple), code
        for name in spec["params"]:
            assert CODE_PATTERN.match(name), (code, name)
        assert isinstance(spec["template"], str) and spec["template"], code
        assert spec["row_template"] is None or isinstance(spec["row_template"], str)


def test_message_template_is_ascii() -> None:
    # Review condition 2: only the *template* is ASCII-guaranteed — params
    # (marker/value) may contain non-ASCII characters and are substituted.
    for code, spec in logic.ERROR_SPECS.items():
        for template in _templates(spec):
            template.encode("ascii")  # must not raise
            assert "\u00df" not in template, code
            assert not any("ä" <= char <= "ü" for char in template.lower()), code


def test_message_template_placeholders_are_declared() -> None:
    for code, spec in logic.ERROR_SPECS.items():
        declared = set(spec["params"])
        for template in _templates(spec):
            for placeholder in PLACEHOLDER_PATTERN.findall(template):
                assert placeholder in declared, (code, placeholder)
        if spec["row_template"] is not None:
            assert "row" in declared, code


def test_message_template_value_scope() -> None:
    for code, spec in logic.ERROR_SPECS.items():
        for template in _templates(spec):
            if code == "invalid_ts":
                continue
            assert "{value}" not in template, code
    assert "{value}" in logic.ERROR_SPECS["invalid_ts"]["template"]


def test_build_error_returns_all_three_fields() -> None:
    for code in logic.ERROR_SPECS:
        result = logic.build_error(code)
        assert set(result) == {"code", "params", "message"}, code
        assert result["code"] == code
        assert isinstance(result["params"], dict), code
        assert isinstance(result["message"], str) and result["message"], code


def test_build_error_uses_row_template_when_row_present() -> None:
    with_row = logic.build_error("unknown_marker", {"row": 3, "marker": "kreatinin"})
    assert with_row["message"] == "unknown_marker (row=3, marker=kreatinin)"

    without_row = logic.build_error("unknown_marker", {"marker": "kreatinin"})
    assert without_row["message"] == "unknown_marker (marker=kreatinin)"


def test_build_error_unknown_code_falls_back_to_code() -> None:
    result = logic.build_error("does_not_exist", {"x": 1})

    assert result["code"] == "does_not_exist"
    assert result["params"] == {}
    assert result["message"] == "does_not_exist"


def test_error_contract_no_pii_params() -> None:
    for code, spec in logic.ERROR_SPECS.items():
        for name in spec["params"]:
            assert name not in FORBIDDEN_PARAM_NAMES, (code, name)
            if name == "value":
                assert code in logic.RAW_ECHO_CODES, code


def test_raw_echo_truncated_to_64_chars() -> None:
    result = logic.build_error("invalid_ts", {"value": "x" * 200})

    assert len(result["params"]["value"]) == 64


def test_params_stringified_projection() -> None:
    for code in logic.ERROR_SPECS:
        result = logic.build_error(code, {"row": 1, "marker": "alt", "min": 1})
        projected = {key: str(value) for key, value in result["params"].items()}
        assert all(isinstance(value, str) for value in projected.values()), code


def test_params_whitelist_drops_undeclared_keys() -> None:
    result = logic.build_error("amount_out_of_range", {"min": 1, "max": 10, "secret": "x"})

    assert "secret" not in result["params"]
    assert "secret" not in result["message"]


def test_lab_report_error_delegates_to_build_error() -> None:
    params = {"row": 3, "marker": "gptx"}

    assert logic.lab_report_error("unknown_marker", params) == logic.build_error(
        "unknown_marker", params
    )


def test_raw_echo_codes_are_a_frozenset_of_catalog_codes() -> None:
    assert isinstance(logic.RAW_ECHO_CODES, frozenset)
    assert logic.RAW_ECHO_CODES == frozenset({"invalid_ts", "invalid_value"})
    assert logic.RAW_ECHO_CODES <= set(logic.ERROR_SPECS)


@pytest.mark.parametrize("code", sorted(logic.ERROR_SPECS))
def test_every_catalog_code_renders_a_non_empty_message(code: str) -> None:
    assert logic.build_error(code)["message"].startswith(code)

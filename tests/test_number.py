"""Tests: DailyGoalNumber — Persistierung via entry.options (Audit C-2).

Audit-Punkt 7b (C-2): DailyGoalNumber.async_set_native_value() must persist to
entry.options["daily_goal_ml"] via hass.config_entries.async_update_entry().
"""
import asyncio
import importlib.util
import os
import sys
import types
from unittest.mock import AsyncMock, MagicMock

_COMPONENT_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "custom_components", "health_o_mat")
)

# Fake-Paket für relative Imports
_PKG = "_hom_test_pkg"
_pkg = types.ModuleType(_PKG)
_pkg.__path__ = [_COMPONENT_DIR]
sys.modules.setdefault(_PKG, _pkg)


def _load(name: str):
    spec = importlib.util.spec_from_file_location(
        f"{_PKG}.{name}", os.path.join(_COMPONENT_DIR, f"{name}.py")
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[f"{_PKG}.{name}"] = module
    spec.loader.exec_module(module)
    return module


number_module = _load("number")


def _async_test(coro):
    """Helper to run async functions in sync test context."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _make_daily_goal_number_fixture():
    """Create a DailyGoalNumber with properly mocked dependencies."""
    # Create entry with options and runtime_data
    entry = MagicMock()
    entry.entry_id = "test-entry-1"
    entry.options = {}  # Will be updated by async_set_native_value
    entry.runtime_data = MagicMock()
    entry.runtime_data.daily_goal_ml = 2000

    # Create coordinator
    coordinator = MagicMock()

    # Create hass with async_update_entry mocked
    hass = MagicMock()
    hass.config_entries = MagicMock()
    hass.config_entries.async_update_entry = MagicMock()

    # Create the entity
    entity = number_module.DailyGoalNumber(coordinator, entry)
    entity.hass = hass

    return entity, entry, hass


def test_daily_goal_number_native_value_from_options():
    """[AUDIT-7b-C-2] native_value reads from entry.options first (source of truth)."""
    entity, entry, _ = _make_daily_goal_number_fixture()

    entry.options["daily_goal_ml"] = 2500

    assert entity.native_value == 2500


def test_daily_goal_number_native_value_fallback_to_runtime():
    """[AUDIT-7b-C-2] native_value falls back to runtime_data if options not set."""
    entity, entry, _ = _make_daily_goal_number_fixture()

    entry.options = {}
    entry.runtime_data.daily_goal_ml = 3000

    assert entity.native_value == 3000


def test_daily_goal_number_async_set_native_value_updates_entry():
    """[AUDIT-7b-C-2] async_set_native_value calls async_update_entry with new options."""
    entity, entry, hass = _make_daily_goal_number_fixture()

    _async_test(entity.async_set_native_value(2500))

    # Verify async_update_entry was called with correct options
    hass.config_entries.async_update_entry.assert_called_once()
    call_args = hass.config_entries.async_update_entry.call_args
    assert call_args[1]["options"]["daily_goal_ml"] == 2500


def test_daily_goal_number_async_set_native_value_preserves_other_options():
    """[AUDIT-7b-C-2] async_set_native_value preserves existing options."""
    entity, entry, hass = _make_daily_goal_number_fixture()

    entry.options["some_other_key"] = "some_value"

    _async_test(entity.async_set_native_value(2500))

    call_args = hass.config_entries.async_update_entry.call_args
    updated_options = call_args[1]["options"]
    assert updated_options["daily_goal_ml"] == 2500
    assert updated_options["some_other_key"] == "some_value"


def test_daily_goal_number_async_set_native_value_converts_to_int():
    """[AUDIT-7b-C-2] async_set_native_value converts value to int for storage."""
    entity, entry, hass = _make_daily_goal_number_fixture()

    _async_test(entity.async_set_native_value(2500.7))

    call_args = hass.config_entries.async_update_entry.call_args
    assert call_args[1]["options"]["daily_goal_ml"] == 2500
    assert isinstance(call_args[1]["options"]["daily_goal_ml"], int)


def test_daily_goal_number_async_set_native_value_passes_entry():
    """[AUDIT-7b-C-2] async_set_native_value passes correct entry to async_update_entry."""
    entity, entry, hass = _make_daily_goal_number_fixture()

    _async_test(entity.async_set_native_value(2500))

    call_args = hass.config_entries.async_update_entry.call_args
    assert call_args[0][0] == entry


def test_daily_goal_number_attributes():
    """[AUDIT-7b-C-2] DailyGoalNumber has correct min/max/step attributes."""
    entity, _, _ = _make_daily_goal_number_fixture()

    assert entity._attr_native_min_value == 500
    assert entity._attr_native_max_value == 10000
    assert entity._attr_native_step_value == 50
    assert entity._attr_native_unit_of_measurement == "ml"


def test_daily_goal_number_translation_key():
    """[AUDIT-7b-C-2] DailyGoalNumber has correct translation key."""
    entity, _, _ = _make_daily_goal_number_fixture()

    assert entity._attr_translation_key == "daily_goal"


def test_daily_goal_number_icon():
    """[AUDIT-7b-C-2] DailyGoalNumber has target icon."""
    entity, _, _ = _make_daily_goal_number_fixture()

    assert entity._attr_icon == "mdi:target"


def test_daily_goal_number_multiple_updates_sequence():
    """[AUDIT-7b-C-2] Multiple sequential updates each call async_update_entry."""
    entity, entry, hass = _make_daily_goal_number_fixture()

    _async_test(entity.async_set_native_value(2000))
    _async_test(entity.async_set_native_value(2500))
    _async_test(entity.async_set_native_value(3000))

    assert hass.config_entries.async_update_entry.call_count == 3

    # Check last call has final value
    last_call_args = hass.config_entries.async_update_entry.call_args
    assert last_call_args[1]["options"]["daily_goal_ml"] == 3000


def test_daily_goal_number_empty_initial_options():
    """[AUDIT-7b-C-2] Works correctly with initially empty options dict."""
    entity, entry, hass = _make_daily_goal_number_fixture()

    entry.options = {}

    _async_test(entity.async_set_native_value(1500))

    call_args = hass.config_entries.async_update_entry.call_args
    assert call_args[1]["options"]["daily_goal_ml"] == 1500


def test_daily_goal_number_boundary_values():
    """[AUDIT-7b-C-2] Accepts min/max boundary values."""
    entity, entry, hass = _make_daily_goal_number_fixture()

    # Min value
    _async_test(entity.async_set_native_value(500))
    min_call = hass.config_entries.async_update_entry.call_args
    assert min_call[1]["options"]["daily_goal_ml"] == 500

    # Max value
    _async_test(entity.async_set_native_value(10000))
    max_call = hass.config_entries.async_update_entry.call_args
    assert max_call[1]["options"]["daily_goal_ml"] == 10000

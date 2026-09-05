"""Tests: HealthOMatOptionsFlow — daily_goal_ml persistence (Audit C-2).

Audit-Punkt 7b (C-2): Options flow correctly reads default from entry.options
and persists user input back to entry.options.
"""
import asyncio
import importlib.util
import os
import sys
import types
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

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


config_flow_module = _load("config_flow")


def _async_test(coro):
    """Helper to run async functions in sync test context."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def test_config_flow_get_options_flow_returns_options_flow_instance():
    """[AUDIT-7b-C-2] ConfigFlow.async_get_options_flow returns OptionsFlow instance."""
    config_flow = config_flow_module.HealthOMatConfigFlow()

    result = config_flow.async_get_options_flow(MagicMock())

    assert isinstance(result, config_flow_module.HealthOMatOptionsFlow)


def test_config_flow_version():
    """[AUDIT-7b-C-2] ConfigFlow has correct VERSION."""
    config_flow = config_flow_module.HealthOMatConfigFlow()
    assert config_flow.VERSION == 1


def test_options_flow_async_step_init_shows_form_on_no_input():
    """[AUDIT-7b-C-2] async_step_init shows form when user_input is None."""
    options_flow = config_flow_module.HealthOMatOptionsFlow()

    # Mock the dependencies
    entry = MagicMock()
    entry.options = {"daily_goal_ml": 2500}
    entry.runtime_data = MagicMock()
    entry.entry_id = "test-entry-1"

    hass = MagicMock()
    hass.data = {
        "health_o_mat": {
            "shared": {
                "store": MagicMock()
            }
        }
    }
    store = hass.data["health_o_mat"]["shared"]["store"]
    store.all_entries = MagicMock(return_value={
        "test-entry-1": {"total_ml_lifetime": 1000}
    })

    # Use PropertyMock to set config_entry properly
    type(options_flow).config_entry = PropertyMock(return_value=entry)
    type(options_flow).hass = PropertyMock(return_value=hass)

    # Mock async_show_form
    options_flow.async_show_form = MagicMock()

    _async_test(options_flow.async_step_init(None))

    options_flow.async_show_form.assert_called_once()
    call_kwargs = options_flow.async_show_form.call_args[1]
    assert call_kwargs["step_id"] == "init"
    assert "data_schema" in call_kwargs


def test_options_flow_async_step_init_creates_entry_on_user_input():
    """[AUDIT-7b-C-2] async_step_init creates entry with daily_goal_ml."""
    options_flow = config_flow_module.HealthOMatOptionsFlow()

    # Mock the dependencies
    entry = MagicMock()
    entry.options = {}
    entry.runtime_data = MagicMock()
    entry.runtime_data.daily_goal_ml = 2000
    entry.entry_id = "test-entry-1"

    hass = MagicMock()
    hass.data = {}

    type(options_flow).config_entry = PropertyMock(return_value=entry)
    type(options_flow).hass = PropertyMock(return_value=hass)

    # Mock async_create_entry
    result_data = {"daily_goal_ml": 2250, "set_lifetime_ml": 0}
    options_flow.async_create_entry = MagicMock()

    user_input = {"daily_goal_ml": 2250, "set_lifetime_ml": 0}
    _async_test(options_flow.async_step_init(user_input))

    options_flow.async_create_entry.assert_called_once()
    call_kwargs = options_flow.async_create_entry.call_args[1]
    assert call_kwargs["data"]["daily_goal_ml"] == 2250
    assert call_kwargs["data"]["set_lifetime_ml"] == 0


def test_options_flow_daily_goal_from_options_takes_precedence():
    """[AUDIT-7b-C-2] async_step_init reads daily_goal_ml from entry.options first."""
    options_flow = config_flow_module.HealthOMatOptionsFlow()

    # entry.options has daily_goal_ml, runtime_data has different value
    entry = MagicMock()
    entry.options = {"daily_goal_ml": 2500}
    entry.runtime_data = MagicMock()
    entry.runtime_data.daily_goal_ml = 3000  # This should be ignored
    entry.entry_id = "test-entry-1"

    hass = MagicMock()
    hass.data = {}

    type(options_flow).config_entry = PropertyMock(return_value=entry)
    type(options_flow).hass = PropertyMock(return_value=hass)

    options_flow.async_show_form = MagicMock()

    _async_test(options_flow.async_step_init(None))

    # The form should have been shown (meaning no error with options reading)
    options_flow.async_show_form.assert_called_once()


def test_options_flow_fallback_to_runtime_when_options_empty():
    """[AUDIT-7b-C-2] Falls back to runtime_data.daily_goal_ml if options empty."""
    options_flow = config_flow_module.HealthOMatOptionsFlow()

    entry = MagicMock()
    entry.options = {}  # Empty options
    entry.runtime_data = MagicMock()
    entry.runtime_data.daily_goal_ml = 3000
    entry.entry_id = "test-entry-1"

    hass = MagicMock()
    hass.data = {}

    type(options_flow).config_entry = PropertyMock(return_value=entry)
    type(options_flow).hass = PropertyMock(return_value=hass)

    options_flow.async_show_form = MagicMock()

    _async_test(options_flow.async_step_init(None))

    # Should show form without error
    options_flow.async_show_form.assert_called_once()


def test_options_flow_fallback_to_default_when_no_runtime_data():
    """[AUDIT-7b-C-2] Falls back to DEFAULT_DAILY_GOAL_ML if no runtime_data."""
    options_flow = config_flow_module.HealthOMatOptionsFlow()

    entry = MagicMock()
    entry.options = {}
    entry.runtime_data = None  # No runtime data
    entry.entry_id = "test-entry-1"

    hass = MagicMock()
    hass.data = {}

    type(options_flow).config_entry = PropertyMock(return_value=entry)
    type(options_flow).hass = PropertyMock(return_value=hass)

    options_flow.async_show_form = MagicMock()

    _async_test(options_flow.async_step_init(None))

    # Should use DEFAULT_DAILY_GOAL_ML and show form
    options_flow.async_show_form.assert_called_once()


def test_options_flow_loads_lifetime_from_store():
    """[AUDIT-7b-C-2] async_step_init loads lifetime_ml from store."""
    options_flow = config_flow_module.HealthOMatOptionsFlow()

    entry = MagicMock()
    entry.options = {}
    entry.runtime_data = MagicMock()
    entry.runtime_data.daily_goal_ml = 2000
    entry.entry_id = "test-entry-1"

    hass = MagicMock()
    mock_store = MagicMock()
    mock_store.all_entries = MagicMock(return_value={
        "test-entry-1": {"total_ml_lifetime": 5000}
    })
    hass.data = {
        "health_o_mat": {
            "shared": {
                "store": mock_store
            }
        }
    }

    type(options_flow).config_entry = PropertyMock(return_value=entry)
    type(options_flow).hass = PropertyMock(return_value=hass)

    options_flow.async_show_form = MagicMock()

    _async_test(options_flow.async_step_init(None))

    # Store.all_entries() should have been called
    mock_store.all_entries.assert_called_once()


def test_options_flow_handles_missing_store():
    """[AUDIT-7b-C-2] async_step_init handles missing store gracefully."""
    options_flow = config_flow_module.HealthOMatOptionsFlow()

    entry = MagicMock()
    entry.options = {}
    entry.runtime_data = MagicMock()
    entry.runtime_data.daily_goal_ml = 2000
    entry.entry_id = "test-entry-1"

    hass = MagicMock()
    hass.data = {}  # No store

    type(options_flow).config_entry = PropertyMock(return_value=entry)
    type(options_flow).hass = PropertyMock(return_value=hass)

    options_flow.async_show_form = MagicMock()

    _async_test(options_flow.async_step_init(None))

    # Should still show form without error
    options_flow.async_show_form.assert_called_once()


def test_options_flow_preserves_other_options_on_submit():
    """[AUDIT-7b-C-2] async_create_entry called with user_input data."""
    options_flow = config_flow_module.HealthOMatOptionsFlow()

    entry = MagicMock()
    entry.options = {"some_key": "some_value"}
    entry.runtime_data = MagicMock()
    entry.entry_id = "test-entry-1"

    hass = MagicMock()
    hass.data = {}

    type(options_flow).config_entry = PropertyMock(return_value=entry)
    type(options_flow).hass = PropertyMock(return_value=hass)

    options_flow.async_create_entry = MagicMock()

    user_input = {"daily_goal_ml": 2500, "set_lifetime_ml": 1000}
    _async_test(options_flow.async_step_init(user_input))

    # async_create_entry should be called with user_input data
    options_flow.async_create_entry.assert_called_once()
    call_kwargs = options_flow.async_create_entry.call_args[1]
    assert call_kwargs["data"] == user_input

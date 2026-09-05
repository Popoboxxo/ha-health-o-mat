"""Fake Home Assistant package for pytest.

Enables unit tests to run without a full Home Assistant installation.
Attempts real import first; falls back to MagicMock on ImportError.

This conftest is auto-loaded by pytest and patches sys.modules before
any custom_components imports happen.
"""
import sys
from unittest.mock import MagicMock

# Attempt real import first (for testing with actual HA installation)
try:
    import homeassistant  # noqa: F401
    _USING_REAL_HA = True
except ImportError:
    _USING_REAL_HA = False

if not _USING_REAL_HA:
    # Comprehensive list of homeassistant.* submodules imported by health_o_mat
    # Extracted from custom_components/health_o_mat/ via grep:
    # - homeassistant.components.button (ButtonEntity)
    # - homeassistant.exceptions (HomeAssistantError, ServiceValidationError)
    # - homeassistant.util (dt_util), homeassistant.util.dt
    # - homeassistant.core (HomeAssistant, ServiceCall, callback)
    # - homeassistant.components.binary_sensor (BinarySensorEntity)
    # - homeassistant.components.number (NumberEntity, NumberMode)
    # - homeassistant.config_entries (ConfigEntry)
    # - homeassistant.const (Platform)
    # - homeassistant.helpers.update_coordinator (DataUpdateCoordinator)
    # - homeassistant.helpers.device_registry (DeviceInfo)
    # - homeassistant.helpers.storage (Store)
    # - homeassistant.components.sensor (SensorEntity, SensorStateClass)
    # - homeassistant.components.text (TextEntity)
    # - homeassistant.components.select (SelectEntity)
    #
    # Important: EVERY submodule must be listed separately, because Python's
    # import system requires each level to exist in sys.modules.
    _FAKE_MODULES = [
        "homeassistant",
        "homeassistant.core",
        "homeassistant.exceptions",
        "homeassistant.util",
        "homeassistant.util.dt",
        "homeassistant.config_entries",
        "homeassistant.const",
        "homeassistant.components",
        "homeassistant.components.binary_sensor",
        "homeassistant.components.button",
        "homeassistant.components.number",
        "homeassistant.components.sensor",
        "homeassistant.components.select",
        "homeassistant.components.text",
        "homeassistant.helpers",
        "homeassistant.helpers.device_registry",
        "homeassistant.helpers.storage",
        "homeassistant.helpers.update_coordinator",
    ]

    for _mod in _FAKE_MODULES:
        sys.modules.setdefault(_mod, MagicMock())

"""Fake Home Assistant package for pytest.

Enables unit tests to run without a full Home Assistant installation.
Attempts real import first; falls back to a set of hand-built fake
``homeassistant.*`` modules on ImportError.

This conftest is auto-loaded by pytest and patches sys.modules before
any custom_components imports happen.
"""

from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock

import voluptuous as vol

# Attempt real import first (for testing with actual HA installation)
try:
    import homeassistant  # noqa: F401

    _USING_REAL_HA = True
except ImportError:
    _USING_REAL_HA = False

if not _USING_REAL_HA:
    # ------------------------------------------------------------------
    # Why not just `sys.modules.setdefault(_mod, MagicMock())` per module?
    #
    # A bare MagicMock() *instance* standing in for a whole module looks
    # convenient, but attribute access on it (e.g. `module.NumberEntity`)
    # auto-generates a new MagicMock *instance*, not a class. Using that
    # instance as a base class works fine for single-base classes
    # (`class HealthOMatEntity(CoordinatorEntity):`), but breaks for
    # multi-base classes such as
    # `class HealthOMatNumber(HealthOMatEntity, NumberEntity):` with
    # `TypeError: metaclass conflict: the metaclass of a derived class
    # must be a (non-strict) subclass of the metaclasses of all its
    # bases` — because the metaclass implicitly derived from a Mock
    # instance (MagicMock) is unrelated to `type`.
    #
    # Fix: every homeassistant.* class that custom_components/health_o_mat
    # actually uses as a BASE CLASS gets a real (empty/minimal) Python
    # class here. Everything else — constants, enums used only as
    # attribute values, helper callables like Store/DeviceInfo that are
    # only ever instantiated/called, never subclassed — stays a
    # MagicMock, exactly as before.
    # ------------------------------------------------------------------

    class Entity:
        """Minimal stand-in for homeassistant.helpers.entity.Entity."""

    _UNDEFINED = object()  # stand-in for helpers.typing.UNDEFINED (identity sentinel)

    class CoordinatorEntity(Entity):
        """Minimal stand-in for homeassistant.helpers.update_coordinator.

        CoordinatorEntity. Stores the coordinator like the real base does,
        which is all HealthOMatEntity.__init__ relies on via super().__init__().
        """

        def __init__(self, coordinator, context=None) -> None:
            self.coordinator = coordinator

    class ButtonEntity(Entity):
        """Minimal stand-in for homeassistant.components.button.ButtonEntity."""

    class NumberEntity(Entity):
        """Minimal stand-in for homeassistant.components.number.NumberEntity."""

    class SensorEntity(Entity):
        """Minimal stand-in for homeassistant.components.sensor.SensorEntity."""

    class BinarySensorEntity(Entity):
        """Minimal stand-in for binary_sensor.BinarySensorEntity."""

    class SelectEntity(Entity):
        """Minimal stand-in for homeassistant.components.select.SelectEntity."""

    class TextEntity(Entity):
        """Minimal stand-in for homeassistant.components.text.TextEntity."""

    class DataUpdateCoordinator:
        """Minimal stand-in for update_coordinator.DataUpdateCoordinator.

        Not used as a base class anywhere in this integration (only
        instantiated in __init__.py), but implemented for real here too so
        its constructor signature and async_set_updated_data() behave
        predictably instead of silently accepting/returning Mocks.
        """

        def __init__(
            self,
            hass=None,
            logger=None,
            *,
            name=None,
            update_method=None,
            update_interval=None,
            **kwargs,
        ) -> None:
            self.hass = hass
            self.logger = logger
            self.name = name
            self.update_method = update_method
            self.update_interval = update_interval
            self.data = None

        def async_set_updated_data(self, data) -> None:
            self.data = data

    class ConfigEntry:
        """Minimal stand-in for homeassistant.config_entries.ConfigEntry.

        Supports `ConfigEntry[SomeType]` subscription used for the
        `HealthOMatConfigEntry = ConfigEntry[HealthOMatData]` type alias.
        """

        def __class_getitem__(cls, item):
            return cls

    class ConfigFlow:
        """Minimal stand-in for homeassistant.config_entries.ConfigFlow."""

        def __init_subclass__(cls, *, domain: str | None = None, **kwargs) -> None:
            super().__init_subclass__(**kwargs)
            cls._domain = domain

        async def async_set_unique_id(self, unique_id: str) -> None:
            self.unique_id = unique_id

        def _abort_if_unique_id_configured(self) -> None:
            return None

        def async_create_entry(self, **kwargs):
            return {"type": "create_entry", **kwargs}

        def async_show_form(self, **kwargs):
            return {"type": "form", **kwargs}

        def add_suggested_values_to_schema(self, schema, suggested_values):
            return schema

    class TextSelectorConfig:
        """Minimal stand-in for homeassistant.helpers.selector.TextSelectorConfig."""

        def __init__(self, **kwargs) -> None:
            self.config = kwargs

    class TextSelector:
        """Minimal stand-in for homeassistant.helpers.selector.TextSelector.

        Only instantiated (never subclassed) — used as the voluptuous value
        validator for a schema key. A no-op passthrough is enough here since
        the real selector's job (rendering a multiline textarea) is a
        frontend concern, not exercised by these HA-free unit tests.
        """

        def __init__(self, config=None) -> None:
            self.config = config

        def __call__(self, value):
            return value

    class OptionsFlow:
        """Minimal stand-in for homeassistant.config_entries.OptionsFlow."""

        def async_create_entry(self, **kwargs):
            return {"type": "create_entry", **kwargs}

        def async_show_form(self, **kwargs):
            return {"type": "form", **kwargs}

    class HomeAssistant:
        """Minimal stand-in for homeassistant.core.HomeAssistant (type hints only)."""

    class ServiceCall:
        """Minimal stand-in for homeassistant.core.ServiceCall (type hints only)."""

    class HomeAssistantError(Exception):
        """Minimal stand-in for homeassistant.exceptions.HomeAssistantError."""

    class ServiceValidationError(HomeAssistantError):
        """Minimal stand-in for homeassistant.exceptions.ServiceValidationError."""

    def callback(func):
        """Identity decorator — real HA's @callback just tags the function."""
        return func

    def _module(name: str, **attrs) -> types.ModuleType:
        mod = types.ModuleType(name)
        for attr_name, value in attrs.items():
            setattr(mod, attr_name, value)
        return mod

    # --- Frontend / HTTP / Lovelace / WebSocket shims (wave 3) -------------
    # These modules are the handful that MUST behave for real rather than as
    # a bare MagicMock: the tests assert on what they write into `hass.data`
    # (static path list, extra-JS URL set, Lovelace resources, WS handlers),
    # so a swallowing Mock would make every such assertion vacuous.
    DATA_EXTRA_MODULE_URL = "frontend_extra_module_url"
    LOVELACE_DATA = "lovelace"
    WS_API_DATA = "websocket_api"

    def add_extra_js_url(hass, url: str) -> None:
        hass.data.setdefault(DATA_EXTRA_MODULE_URL, set()).add(url)

    def remove_extra_js_url(hass, url: str) -> None:
        hass.data.setdefault(DATA_EXTRA_MODULE_URL, set()).discard(url)

    class StaticPathConfig:
        """Minimal stand-in for homeassistant.components.http.StaticPathConfig."""

        def __init__(self, url_path: str, path: str, cache_headers: bool = True) -> None:
            self.url_path = url_path
            self.path = path
            self.cache_headers = cache_headers

    def websocket_async_register_command(hass, command, handler, schema) -> None:
        hass.data.setdefault(WS_API_DATA, {})[command] = (handler, schema)

    def websocket_async_response(func):
        """Wrap a coroutine handler in the sync callable the WS dispatcher expects."""

        def _async_response(*args, **kwargs):
            coro = func(*args, **kwargs)
            hass = args[0] if args else None
            if hasattr(hass, "async_create_task"):
                hass.async_create_task(coro)
            else:  # no running loop in the test fakes — drop it without a warning
                coro.close()

        return _async_response

    _FAKE_MODULES: dict[str, types.ModuleType] = {
        "homeassistant": _module("homeassistant"),
        "homeassistant.core": _module(
            "homeassistant.core",
            HomeAssistant=HomeAssistant,
            ServiceCall=ServiceCall,
            callback=callback,
        ),
        "homeassistant.exceptions": _module(
            "homeassistant.exceptions",
            HomeAssistantError=HomeAssistantError,
            ServiceValidationError=ServiceValidationError,
        ),
        "homeassistant.util": _module("homeassistant.util"),
        "homeassistant.util.dt": MagicMock(),  # dt_util.now()/.as_local() mocked per-test
        "homeassistant.config_entries": _module(
            "homeassistant.config_entries",
            ConfigEntry=ConfigEntry,
            ConfigFlow=ConfigFlow,
            OptionsFlow=OptionsFlow,
        ),
        "homeassistant.const": _module("homeassistant.const", Platform=MagicMock()),
        "homeassistant.components": _module("homeassistant.components"),
        "homeassistant.components.binary_sensor": _module(
            "homeassistant.components.binary_sensor",
            BinarySensorEntity=BinarySensorEntity,
            BinarySensorDeviceClass=MagicMock(),
        ),
        "homeassistant.components.button": _module(
            "homeassistant.components.button",
            ButtonEntity=ButtonEntity,
        ),
        "homeassistant.components.number": _module(
            "homeassistant.components.number",
            NumberEntity=NumberEntity,
            NumberMode=MagicMock(),
        ),
        "homeassistant.components.sensor": _module(
            "homeassistant.components.sensor",
            SensorEntity=SensorEntity,
            SensorStateClass=MagicMock(),
            SensorDeviceClass=MagicMock(),
        ),
        "homeassistant.components.select": _module(
            "homeassistant.components.select",
            SelectEntity=SelectEntity,
        ),
        "homeassistant.components.text": _module(
            "homeassistant.components.text",
            TextEntity=TextEntity,
        ),
        "homeassistant.components.frontend": _module(
            "homeassistant.components.frontend",
            DATA_EXTRA_MODULE_URL=DATA_EXTRA_MODULE_URL,
            add_extra_js_url=add_extra_js_url,
            remove_extra_js_url=remove_extra_js_url,
        ),
        "homeassistant.components.http": _module(
            "homeassistant.components.http",
            StaticPathConfig=StaticPathConfig,
        ),
        "homeassistant.components.lovelace": _module("homeassistant.components.lovelace"),
        "homeassistant.components.lovelace.const": _module(
            "homeassistant.components.lovelace.const",
            LOVELACE_DATA=LOVELACE_DATA,
        ),
        "homeassistant.components.websocket_api": _module(
            "homeassistant.components.websocket_api",
            ERR_NOT_FOUND="not_found",
            BASE_COMMAND_MESSAGE_SCHEMA=vol.Schema(
                {vol.Required("id"): int, vol.Required("type"): str}
            ),
            async_register_command=websocket_async_register_command,
            async_response=websocket_async_response,
        ),
        "homeassistant.helpers": _module("homeassistant.helpers"),
        "homeassistant.helpers.typing": _module(
            "homeassistant.helpers.typing",
            UNDEFINED=_UNDEFINED,
        ),
        "homeassistant.helpers.device_registry": _module(
            "homeassistant.helpers.device_registry",
            DeviceInfo=MagicMock(),
            async_get=MagicMock(),
            async_entries_for_config_entry=MagicMock(),
        ),
        "homeassistant.helpers.entity_registry": _module(
            "homeassistant.helpers.entity_registry",
            async_get=MagicMock(),
            async_entries_for_config_entry=MagicMock(),
        ),
        "homeassistant.helpers.entity": _module(
            "homeassistant.helpers.entity",
            DeviceInfo=MagicMock(),
            Entity=Entity,
            UNDEFINED=_UNDEFINED,
        ),
        "homeassistant.helpers.storage": _module(
            "homeassistant.helpers.storage",
            Store=MagicMock(),
        ),
        "homeassistant.helpers.selector": _module(
            "homeassistant.helpers.selector",
            TextSelector=TextSelector,
            TextSelectorConfig=TextSelectorConfig,
        ),
        "homeassistant.helpers.update_coordinator": _module(
            "homeassistant.helpers.update_coordinator",
            CoordinatorEntity=CoordinatorEntity,
            DataUpdateCoordinator=DataUpdateCoordinator,
        ),
    }

    for _mod_name, _mod_obj in _FAKE_MODULES.items():
        sys.modules.setdefault(_mod_name, _mod_obj)

    # Pre-loading a module in sys.modules skips the import machinery's usual
    # parent wiring, so `from homeassistant.components import websocket_api`
    # and `from homeassistant.helpers import device_registry` would fail with
    # AttributeError. Give every package-like fake a `__path__` and register
    # each child as an attribute of its parent module to make those forms work.
    _PACKAGE_NAMES = {name.rpartition(".")[0] for name in _FAKE_MODULES if "." in name}
    for _mod_name, _mod_obj in _FAKE_MODULES.items():
        if _mod_name in _PACKAGE_NAMES and not hasattr(_mod_obj, "__path__"):
            _mod_obj.__path__ = []
        _parent_name, _, _child = _mod_name.rpartition(".")
        if _child and _parent_name in _FAKE_MODULES:
            setattr(_FAKE_MODULES[_parent_name], _child, _mod_obj)

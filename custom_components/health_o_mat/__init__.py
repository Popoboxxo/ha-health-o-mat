"""HA Health-O-Mat — Integration Setup."""
from __future__ import annotations

from datetime import datetime
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
import voluptuous as vol

from .const import (
    DEFAULT_DIA_THRESHOLD,
    DEFAULT_DAILY_GOAL_ML,
    DEFAULT_QUICK_DRINKS,
    DEFAULT_SYS_THRESHOLD,
    DOMAIN,
)
from .store import HealthOMatStore

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.SENSOR, Platform.BINARY_SENSOR, Platform.BUTTON,
             Platform.TEXT, Platform.NUMBER]

type HealthOMatConfigEntry = ConfigEntry[HealthOMatData]


class HealthOMatData:
    """Laufzeitdaten eines Config-Entries (= eine Person)."""

    def __init__(self, store: HealthOMatStore) -> None:
        self.store = store
        # Laufzeit-Einstellungen (werden von Entities geschrieben/gelesen)
        self.daily_goal_ml: int = DEFAULT_DAILY_GOAL_ML
        self.custom_amount_ml: int = 250
        self.sys_threshold: int = DEFAULT_SYS_THRESHOLD
        self.dia_threshold: int = DEFAULT_DIA_THRESHOLD
        self.boundary_hour: int = 0
        self.boundary_minute: int = 0


async def async_setup_entry(hass: HomeAssistant, entry: HealthOMatConfigEntry) -> bool:
    """Einrichtung: ein Entry = eine Person = ein Device."""
    hass.data.setdefault(DOMAIN, {})
    shared_stores: dict = hass.data[DOMAIN].setdefault("stores", {})

    store = shared_stores.get("store")
    if store is None:
        store = HealthOMatStore(hass)
        await store.async_load()
        shared_stores["store"] = store

    data = HealthOMatData(store)
    await store.set_person(entry.entry_id, entry.data.get("person", "Person"))

    lifetime_start = entry.data.get("lifetime_start_ml")
    if lifetime_start is not None:
        await store.set_lifetime_start(entry.entry_id, int(lifetime_start))

    from datetime import datetime as _dt
    from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
    coordinator = DataUpdateCoordinator(
        hass, _LOGGER,
        name=f"health_o_mat_{entry.entry_id}",
        update_method=lambda: _dt.now().isoformat(),
        update_interval=None,
    )
    hass.data[DOMAIN][entry.entry_id] = {"coordinator": coordinator}
    entry.runtime_data = data
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    _register_services(hass, store)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: HealthOMatConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok


def get_runtime_data(hass: HomeAssistant, call: ServiceCall) -> tuple[HealthOMatConfigEntry, HealthOMatData]:
    """Person aus einem Service-Call auflösen (Name → Entry)."""
    person = call.data.get("person", "").strip().lower()
    for entry_id, entry in list(hass.data.get(DOMAIN, {}).items()):
        if not isinstance(entry, ConfigEntry):
            continue
        runtime = getattr(entry, "runtime_data", None)
        if runtime is None:
            continue
        stored = entry.data.get("person", "").strip().lower()
        if not person or stored == person:
            return entry, runtime
    raise ServiceValidationError(f"Person '{person}' nicht gefunden")


def _register_services(hass: HomeAssistant, store: HealthOMatStore) -> None:
    """Öffentliche Services (idempotent registriert)."""
    if hass.services.has_service(DOMAIN, "add_drink"):
        return

    async def add_drink(call: ServiceCall) -> None:
        entry, _data = get_runtime_data(hass, call)
        ml = int(call.data["amount_ml"])
        if ml <= 0 or ml > 10000:
            raise ServiceValidationError("amount_ml muss zwischen 1 und 10000 liegen")
        await store.add_drink(
            entry.entry_id, datetime.now().isoformat(), ml,
            call.data.get("drink_type") or "Eigen",
            call.data.get("source") or "service",
        )
        dispatcher = hass.data[DOMAIN].get("signal")
        if dispatcher:
            dispatcher(entry.entry_id)

    async def add_blood_pressure(call: ServiceCall) -> None:
        entry, _data = get_runtime_data(hass, call)
        await store.add_reading(
            entry.entry_id, datetime.now().isoformat(),
            int(call.data["systolic"]), int(call.data["diastolic"]),
            call.data.get("pulse"), call.data.get("note") or "", "service",
        )
        dispatcher = hass.data[DOMAIN].get("signal")
        if dispatcher:
            dispatcher(entry.entry_id)

    async def remove_last_entry(call: ServiceCall) -> None:
        entry, _data = get_runtime_data(hass, call)
        kind = call.data.get("kind", "drinks")
        if kind != "drinks":
            raise ServiceValidationError("Nur kind='drinks' wird unterstützt")
        removed = await store.remove_last_drink(entry.entry_id)
        if not removed:
            raise ServiceValidationError("Keine Getränke zum Entfernen")
        dispatcher = hass.data[DOMAIN].get("signal")
        if dispatcher:
            dispatcher(entry.entry_id)

    from .exporter import async_export_csv  # lokaler Import gegen Zyklen

    async def export_csv(call: ServiceCall) -> None:
        await async_export_csv(hass, store, call)

    hass.services.async_register(
        DOMAIN, "add_drink",
        schema=vol.Schema({
            vol.Required("amount_ml"): vol.All(vol.Coerce(int)),
            vol.Optional("drink_type"): str,
            vol.Optional("person"): str,
            vol.Optional("source"): str,
        }),
        service_func=add_drink,
    )
    hass.services.async_register(
        DOMAIN, "add_blood_pressure",
        schema=vol.Schema({
            vol.Required("systolic"): vol.Coerce(int),
            vol.Required("diastolic"): vol.Coerce(int),
            vol.Optional("pulse"): vol.Coerce(int),
            vol.Optional("person"): str,
            vol.Optional("note"): str,
        }),
        service_func=add_blood_pressure,
    )
    hass.services.async_register(
        DOMAIN, "remove_last_entry",
        schema=vol.Schema({
            vol.Optional("person"): str,
            vol.Optional("kind", default="drinks"): str,
        }),
        service_func=remove_last_entry,
    )
    hass.services.async_register(
        DOMAIN, "export_csv",
        schema=vol.Schema({
            vol.Optional("person"): str,
            vol.Optional("dataset", default="all"): vol.In(["drinks", "blood_pressure", "all"]),
        }),
        service_func=export_csv,
    )


def signal_update(hass: HomeAssistant, entry_id: str) -> None:
    """Entities auffrischen (von Button/Text-Entities aufgerufen)."""
    dispatcher = hass.data.get(DOMAIN, {}).get("signal")
    if dispatcher:
        dispatcher(entry_id)


DEFAULTS = {
    "quick_drinks": DEFAULT_QUICK_DRINKS,
}

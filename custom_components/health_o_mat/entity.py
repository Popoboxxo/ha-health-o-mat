"""Gemeinsame Basis: unique_id + Device-Kopplung für alle Entities."""
from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER, MODEL


class HealthOMatEntity(CoordinatorEntity):
    """Basis: hängt am Entry-Coordinator eines Personen-Devices.

    Jede Entity bekommt eine stabile unique_id ({entry_id}_{key}) — ohne die
    keine Registry-Anmeldung und keine Device-Zuordnung (v0.1.0-Bug).
    """

    def __init__(self, coordinator, entry, key: str) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        person = entry.data.get("person", "Person")
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=f"Health-O-Mat {person}",
            manufacturer=MANUFACTURER,
            model=MODEL,
        )
        self._attr_has_entity_name = True

    @property
    def available(self) -> bool:
        return True


def signal_refresh(hass, entry_id: str) -> None:
    """Coordinator-Refresh nach Datenänderung."""
    coordinator = hass.data[DOMAIN][entry_id]["coordinator"]
    coordinator.async_set_updated_data(__import__("datetime").datetime.now().isoformat())

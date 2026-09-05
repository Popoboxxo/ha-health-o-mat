"""Gemeinsame Basis: unique_id + Device-Kopplung für alle Entities."""
from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.typing import UNDEFINED
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

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
    def suggested_object_id(self) -> str | None:
        """Objekt-IDs (Entity-ID-Suffixe) immer aus dem ENGLISCHEN Namen.

        HA >= 2026.9 erzeugt für Sprachen in NATIVE_ENTITY_IDS (u. a. Deutsch)
        Objekt-IDs in der Systemsprache — die IDs würden mit der Sprache
        wechseln (z. B. `melder_sehr_schlecht`). Wir pinnen die Suffixe auf
        Englisch: stabil, lesbar, sprachunabhängig. Der Anzeigename bleibt
        davon unberührt (folgt weiterhin der Systemsprache).
        """
        platform_data = self.platform_data
        if (
            platform_data is not None
            and type.__getattribute__(self.__class__, "name")
            is type.__getattribute__(Entity, "name")
        ):
            name = self._name_internal(
                self._object_id_device_class_name,
                getattr(platform_data, "default_language_platform_translations", None) or {},
            )
            if name is not UNDEFINED:
                return name
        return super().suggested_object_id

    @property
    def available(self) -> bool:
        return True


def signal_refresh(hass: HomeAssistant, entry_id: str) -> None:
    """Zentraler Refresh-Trigger für einen Config-Entry.

    Einziger Signalweg für alle Trigger-Punkte (Person-Setup, Quick-Drink-Eintrag,
    Service-Aufrufe, Entity-Writes) — ersetzt die vormals vierfach redundanten
    Direktaufrufe von coordinator.async_set_updated_data() (Audit-Finding C-1).
    """
    info = hass.data.get(DOMAIN, {}).get(entry_id)
    if info and "coordinator" in info:
        info["coordinator"].async_set_updated_data(dt_util.now().isoformat())

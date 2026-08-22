"""Text-Entity: Freitext-Eingabe „Kaffee 300ml" mit Parser."""
from __future__ import annotations

from datetime import datetime

from homeassistant.components.text import TextEntity
from homeassistant.exceptions import HomeAssistantError

from .const import DOMAIN
from .entity import HealthOMatEntity
from . import parser


async def async_setup_entry(hass, entry, async_add_entities) -> None:
    coord = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    store = hass.data[DOMAIN]["store"]
    async_add_entities([FreeTextDrinkEntity(coord, entry, store)])


class FreeTextDrinkEntity(HealthOMatEntity, TextEntity):
    """Eingabefeld; Setzen des Werts bucht das Getränk."""

    _attr_translation_key = "freetext"
    _attr_icon = "mdi:keyboard-return"
    _attr_native_max = 60
    _attr_mode = "text"

    def __init__(self, coordinator, entry, store) -> None:
        super().__init__(coordinator, entry)
        self._store = store
        self._attr_has_entity_name = True
        self._native_value: str = ""

    async def async_set_value(self, value: str) -> None:
        result = parser.parse(value)
        if not result.ok:
            raise HomeAssistantError(
                f"Nicht erkannt: '{value}' ({result.error}). "
                "Beispiel: 'Kaffee 300ml' oder '0,5 l wasser'"
            )
        await self._store.add_drink(
            self._entry.entry_id,
            datetime.now().isoformat(),
            result.amount_ml,
            result.drink_type,
            "freetext",
        )
        self._last_parsed = {
            "amount_ml": result.amount_ml,
            "drink_type": result.drink_type,
            "input": value,
        }
        self._native_value = ""
        coordinator = self.hass.data[DOMAIN][self._entry.entry_id]["coordinator"]
        coordinator.async_set_updated_data(datetime.now().isoformat())

    @property
    def native_value(self) -> str:
        return self._native_value

    @property
    def extra_state_attributes(self) -> dict:
        return getattr(self, "_last_parsed", {})

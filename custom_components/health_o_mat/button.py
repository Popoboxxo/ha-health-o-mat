"""Buttons: Quick-Drinks, Custom-Buchung, Undo, BP-Speichern."""
from __future__ import annotations

from datetime import datetime

from homeassistant.components.button import ButtonEntity
from homeassistant.exceptions import HomeAssistantError

from .const import DOMAIN
from .entity import HealthOMatEntity


async def async_setup_entry(hass, entry, async_add_entities) -> None:
    coord = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    store = hass.data[DOMAIN]["store"]
    entities: list = [
        CustomDrinkButton(coord, entry, store),
        UndoDrinkButton(coord, entry, store),
        SaveReadingButton(coord, entry, store),
    ]
    for i, qd in enumerate(entry.data.get("quick_drinks", []) or []):
        entities.append(QuickDrinkButton(coord, entry, store, i))
    async_add_entities(entities)


def _signal(hass, entry_id: str) -> None:
    coordinator = hass.data[DOMAIN][entry_id]["coordinator"]
    coordinator.async_set_updated_data(datetime.now().isoformat())


class HealthOMatButton(HealthOMatEntity, ButtonEntity):
    def __init__(self, coordinator, entry, store) -> None:
        super().__init__(coordinator, entry)
        self._store = store
        self._attr_has_entity_name = True

    @property
    def _data(self) -> dict:
        return self._store.all_entries().get(self._entry.entry_id, {})

    async def _book(self, ml: int, drink_type: str, src: str) -> None:
        await self._store.add_drink(
            self._entry.entry_id, datetime.now().isoformat(), ml, drink_type, src
        )
        _signal(self.hass, self._entry.entry_id)


class QuickDrinkButton(HealthOMatButton):
    """Vorgefertigter Getränke-Button (Label + ml aus Config)."""

    _attr_icon = "mdi:cup-water"

    def __init__(self, coordinator, entry, store, index: int) -> None:
        super().__init__(coordinator, entry, store)
        self._index = index
        qd = entry.data.get("quick_drinks", [])[index]
        self._ml = int(qd.get("ml", 200))
        self._label = qd.get("label") or f"Quick {index + 1}"
        self._attr_translation_key = None
        self._attr_translation_placeholders = {}
        self._attr_name = self._label

    async def async_press(self) -> None:
        await self._book(self._ml, self._label, "quick_button")


class CustomDrinkButton(HealthOMatButton):
    """Bucht die Menge aus number.…_eigene_menge_ml."""

    _attr_translation_key = "book_custom"
    _attr_icon = "mdi:plus-circle-outline"

    async def async_press(self) -> None:
        ml = int(self._entry.runtime_data.custom_amount_ml or 0)
        if ml <= 0:
            raise HomeAssistantError("Eigenmenge ist 0 — erst Menge eintragen")
        await self._book(ml, "Eigen", "custom_button")


class UndoDrinkButton(HealthOMatButton):
    """Entfernt die letzte Getränkebuchung."""

    _attr_translation_key = "undo_drink"
    _attr_icon = "mdi:undo-variant"

    async def async_press(self) -> None:
        removed = await self._store.remove_last_drink(self._entry.entry_id)
        if not removed:
            raise HomeAssistantError("Keine Getränke zum Entfernen")
        _signal(self.hass, self._entry.entry_id)


class SaveReadingButton(HealthOMatButton):
    """Übernimmt die BP-Eingabefelder als neue Messung."""

    _attr_translation_key = "save_reading"
    _attr_icon = "mdi:content-save-check"

    async def async_press(self) -> None:
        rt = self._entry.runtime_data
        inputs = getattr(rt, "_inputs", {})
        sys_v = inputs.get("sys")
        dia_v = inputs.get("dia")
        pulse_v = inputs.get("pulse")
        if not sys_v or not dia_v:
            raise HomeAssistantError("Erst Systolisch und Diastolisch eintragen")
        await self._store.add_reading(
            self._entry.entry_id,
            datetime.now().isoformat(),
            int(sys_v), int(dia_v),
            int(pulse_v) if pulse_v else None,
            "", "button",
        )
        rt._inputs = {}
        _signal(self.hass, self._entry.entry_id)

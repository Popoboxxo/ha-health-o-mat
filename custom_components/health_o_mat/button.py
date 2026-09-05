"""Buttons: Quick-Drinks, Custom-Buchung, Undo, BP-Speichern, Wohlbefinden."""
from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.exceptions import HomeAssistantError
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .entity import HealthOMatEntity, signal_refresh


async def async_setup_entry(hass, entry, async_add_entities) -> None:
    coord = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    store = hass.data[DOMAIN]["shared"]["store"]
    entities: list = [
        CustomDrinkButton(coord, entry, store),
        UndoDrinkButton(coord, entry, store),
        SaveReadingButton(coord, entry, store),
    ]
    for i in range(len(entry.data.get("quick_drinks", []) or [])):
        entities.append(QuickDrinkButton(coord, entry, store, i))
    from .const import WELLBEING_STATES
    for status in WELLBEING_STATES:
        entities.append(WellbeingButton(coord, entry, store, status))
    async_add_entities(entities)


class HealthOMatButton(HealthOMatEntity, ButtonEntity):
    def __init__(self, coordinator, entry, store, key: str) -> None:
        super().__init__(coordinator, entry, key)
        self._store = store

    @property
    def _data(self) -> dict:
        return self._store.all_entries().get(self._entry.entry_id, {})

    async def _book(self, ml: int, drink_type: str, src: str) -> None:
        await self._store.add_drink(
            self._entry.entry_id, dt_util.now().isoformat(), ml, drink_type, src
        )
        signal_refresh(self.hass, self._entry.entry_id)


class QuickDrinkButton(HealthOMatButton):
    """Vorgefertigter Getränke-Button (Label + ml aus Config).

    Bewusst kein translation_key: das Label ist Freitext aus der
    nutzerdefinierten quick_drinks-Config (z. B. "Kaffee 200ml"), keine
    vom Code fest vergebene Bezeichnung — dafür gibt es nichts zu
    übersetzen (Audit-Finding M-8).
    """

    _attr_icon = "mdi:cup-water"

    def __init__(self, coordinator, entry, store, index: int) -> None:
        super().__init__(coordinator, entry, store, f"button_quick_{index}")
        qd = entry.data.get("quick_drinks", [])[index]
        self._ml = int(qd.get("ml", 200))
        self._label = str(qd.get("label") or f"Quick {index + 1}")
        self._icon = str(qd.get("icon") or "mdi:cup-water")
        self._attr_name = self._label
        self._attr_icon = self._icon

    async def async_press(self) -> None:
        await self._book(self._ml, self._label, "quick_button")


class CustomDrinkButton(HealthOMatButton):
    """Bucht die Menge aus number.…_eigene_menge_ml."""

    _attr_translation_key = "book_custom"
    _attr_icon = "mdi:plus-circle-outline"

    def __init__(self, coordinator, entry, store) -> None:
        super().__init__(coordinator, entry, store, "button_book_custom")

    async def async_press(self) -> None:
        ml = int(self._entry.runtime_data.custom_amount_ml or 0)
        if ml <= 0:
            raise HomeAssistantError("Eigenmenge ist 0 — erst Menge eintragen")
        await self._book(ml, "Eigen", "custom_button")


class UndoDrinkButton(HealthOMatButton):
    """Entfernt die letzte Getränkebuchung."""

    _attr_translation_key = "undo_drink"
    _attr_icon = "mdi:undo-variant"

    def __init__(self, coordinator, entry, store) -> None:
        super().__init__(coordinator, entry, store, "button_undo_drink")

    async def async_press(self) -> None:
        removed = await self._store.remove_last_drink(self._entry.entry_id)
        if not removed:
            raise HomeAssistantError("Keine Getränke zum Entfernen")
        signal_refresh(self.hass, self._entry.entry_id)


class SaveReadingButton(HealthOMatButton):
    """Übernimmt die BP-Eingabefelder als neue Messung (Blutdruck-Manager)."""

    _attr_translation_key = "save_reading"
    _attr_icon = "mdi:content-save-check"

    def __init__(self, coordinator, entry, store) -> None:
        super().__init__(coordinator, entry, store, "button_save_reading")

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
            dt_util.now().isoformat(),
            int(sys_v), int(dia_v),
            int(pulse_v) if pulse_v else None,
            "", "button",
        )
        rt._inputs = {}
        signal_refresh(self.hass, self._entry.entry_id)


class WellbeingButton(HealthOMatButton):
    """Meldet „Wie geht es dir?" und setzt den Select-Status."""

    def __init__(self, coordinator, entry, store, status: dict) -> None:
        super().__init__(coordinator, entry, store, f"button_report_{status['key']}")
        self._status = status
        self._attr_translation_key = f"report_{status['key']}"
        self._attr_icon = str(status["icon"])

    @property
    def extra_state_attributes(self) -> dict:
        return {"status": self._status["key"], "emoji": self._status["emoji"]}

    async def async_press(self) -> None:
        await self._store.set_wellbeing(
            self._entry.entry_id,
            self._status["key"],
            dt_util.now().isoformat(),
        )
        signal_refresh(self.hass, self._entry.entry_id)


def build_wellbeing_buttons(hass, entry, store):
    """5 Melden-Buttons (einer pro Status) für Wohlbefinden."""
    from .const import WELLBEING_STATES
    coord = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    return [WellbeingButton(coord, entry, store, status) for status in WELLBEING_STATES]

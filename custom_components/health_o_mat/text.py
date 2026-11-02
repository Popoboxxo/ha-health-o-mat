"""Text-Entity: Freitext-Eingabe „Kaffee 300ml" mit Parser."""

from __future__ import annotations

import json

from homeassistant.components.text import TextEntity
from homeassistant.exceptions import HomeAssistantError
from homeassistant.util import dt as dt_util

from . import areas, logic, parser
from .const import DOMAIN, DRINK_LEXICON
from .entity import HealthOMatEntity, signal_refresh


async def async_setup_entry(hass, entry, async_add_entities) -> None:
    coord = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    store = hass.data[DOMAIN]["shared"]["store"]
    active = areas.active_areas(entry.options)

    entities: list = []
    if active[areas.AREA_DRINK]:
        entities.append(FreeTextDrinkEntity(coord, entry, store))
    if active[areas.AREA_BP]:
        entities.append(MeasurementNoteEntity(coord, entry, store))
    async_add_entities(entities)


class FreeTextDrinkEntity(HealthOMatEntity, TextEntity):
    """Eingabefeld; Setzen des Werts bucht das Getränk."""

    _attr_translation_key = "freetext"
    _attr_icon = "mdi:keyboard-return"
    _attr_native_max = 60
    _attr_mode = "text"

    def __init__(self, coordinator, entry, store) -> None:
        super().__init__(coordinator, entry, "text_freetext")
        self._store = store
        self._native_value: str = ""
        self._last_parsed: dict = {}

    async def async_set_value(self, value: str) -> None:
        # On-read, kein Cache: entry.options["drink_lexicon"] ist einzige
        # Quelle der Wahrheit, eine Options-Änderung wirkt sofort (kein Reload
        # nötig). Kann ein list statt tuple sein (JSON-Storage-Roundtrip,
        # siehe config_flow.py) — parse() greift nur per Index-Unpacking zu.
        lexicon = self._entry.options.get("drink_lexicon") or DRINK_LEXICON
        result = parser.parse(value, lexicon=lexicon)
        if not result.ok:
            raise HomeAssistantError(
                f"Nicht erkannt: '{value}' ({result.error}). "
                "Beispiel: 'Kaffee 300ml' oder '0,5 l wasser'"
            )
        await self._store.add_drink(
            self._entry.entry_id,
            dt_util.now().isoformat(),
            result.amount_ml,
            result.drink_type,
            "freetext",
            audit_limit=logic.audit_limit_from_options(self._entry.options),
        )
        self._last_parsed = {
            "amount_ml": result.amount_ml,
            "drink_type": result.drink_type,
            "input": value,
        }
        self._native_value = ""
        signal_refresh(self.hass, self._entry.entry_id)

    @property
    def native_value(self) -> str:
        return self._native_value

    @property
    def extra_state_attributes(self) -> dict:
        return {
            "amount_ml": self._last_parsed.get("amount_ml"),
            "drink_type": self._last_parsed.get("drink_type"),
            "last_input": self._last_parsed.get("input"),
            "_json": json.dumps(self._last_parsed, ensure_ascii=False),
        }


class MeasurementNoteEntity(HealthOMatEntity, TextEntity):
    """Angefangene Notiz zur nächsten Blutdruck-Messung (REQ-HOM-010).

    Der Wert liegt im bereits persistierten ``store.inputs``-Dict der Person
    (Store-Schema v2) — dadurch überlebt eine angefangene Notiz einen Neustart.
    Geleert wird zentral in ``HealthOMatStore.add_reading``.
    """

    _attr_translation_key = "measurement_note"
    _attr_icon = "mdi:note-text-outline"
    _attr_native_max = 255
    _attr_mode = "text"

    def __init__(self, coordinator, entry, store) -> None:
        super().__init__(coordinator, entry, "text_measurement_note")
        self._store = store

    @property
    def native_value(self) -> str:
        return self._store.pending_note(self._entry.entry_id)

    async def async_set_value(self, value: str) -> None:
        await self._store.set_pending_note(self._entry.entry_id, value)
        # Only this entity's own state changed (native_value reads the store);
        # CoordinatorEntity.should_poll is False, so push it explicitly.
        self.async_write_ha_state()

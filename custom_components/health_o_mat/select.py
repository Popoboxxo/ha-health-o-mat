"""Select: „Wie geht es dir?" mit 5 Smileys (manuell setzbar)."""
from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.util import dt as dt_util

from .const import DOMAIN, WELLBEING_STATES
from .entity import HealthOMatEntity, signal_refresh


async def async_setup_entry(hass, entry, async_add_entities) -> None:
    coord = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    store = hass.data[DOMAIN]["shared"]["store"]
    async_add_entities([WellbeingSelect(coord, entry, store)])


class WellbeingSelect(HealthOMatEntity, SelectEntity):
    """„Wie geht es dir?" — Status per Select oder Melden-Button."""

    _attr_icon = "mdi:emoticon-outline"

    def __init__(self, coordinator, entry, store) -> None:
        super().__init__(coordinator, entry, "select_wellbeing")
        self._store = store
        self._attr_name = "Wie geht es dir?"
        self._attr_options = [s["label"] for s in WELLBEING_STATES]
        self._by_key = {s["key"]: s for s in WELLBEING_STATES}
        self._by_label = {s["label"]: s for s in WELLBEING_STATES}

    @property
    def _data(self) -> dict:
        return self._store.all_entries().get(self._entry.entry_id, {})

    @property
    def current_option(self) -> str | None:
        wb = self._data.get("wellbeing") or {}
        status = wb.get("status")
        return self._by_key[status]["label"] if status in self._by_key else None

    async def async_select_option(self, option: str) -> None:
        status = self._by_label.get(option)
        if not status:
            return
        await self._store.set_wellbeing(
            self._entry.entry_id, status["key"], dt_util.now().isoformat()
        )
        signal_refresh(self.hass, self._entry.entry_id)

    @property
    def extra_state_attributes(self) -> dict:
        wb = self._data.get("wellbeing") or {}
        status = self._by_key.get(wb.get("status"), {})
        history = self._data.get("wellbeing_history", [])[-10:]
        return {
            "emoji": status.get("emoji"),
            "reported_at": wb.get("ts"),
            "history_json": __import__("json").dumps(history, ensure_ascii=False),
        }

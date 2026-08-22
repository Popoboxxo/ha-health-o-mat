"""Number-Entities: Runtime-Settings + BP-Eingabefelder."""
from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode

from .const import (
    DEFAULT_CUSTOM_AMOUNT_ML,
    DEFAULT_DAILY_GOAL_ML,
    DEFAULT_DIA_THRESHOLD,
    DEFAULT_SYS_THRESHOLD,
    DOMAIN,
    MAX_AMOUNT_ML,
)
from .entity import HealthOMatEntity


async def async_setup_entry(hass, entry, async_add_entities) -> None:
    coord = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    async_add_entities([
        DailyGoalNumber(coord, entry),
        CustomAmountNumber(coord, entry),
        ThresholdNumber(coord, entry, "sys"),
        ThresholdNumber(coord, entry, "dia"),
        InputNumber(coord, entry, "input_sys", "input_systolic", 40, 260, "mdi:arrow-up-right"),
        InputNumber(coord, entry, "input_dia", "input_diastolic", 40, 260, "mdi:arrow-down-right"),
        InputNumber(coord, entry, "input_pulse", "input_pulse", 20, 250, "mdi:heart-pulse"),
    ])


class HealthOMatNumber(HealthOMatEntity, NumberEntity):
    _attr_mode = NumberMode.BOX
    _attr_has_entity_name = True

    def __init__(self, coordinator, entry) -> None:
        super().__init__(coordinator, entry)

    def _refresh(self) -> None:
        coordinator = self.hass.data[DOMAIN][self._entry.entry_id]["coordinator"]
        coordinator.async_set_updated_data(datetime_now_iso())

    async def async_set_native_value(self, value: float) -> None:
        self._apply(value)
        self._refresh()

    def _apply(self, value: float) -> None:
        raise NotImplementedError


def datetime_now_iso() -> str:
    from datetime import datetime
    return datetime.now().isoformat()


class DailyGoalNumber(HealthOMatNumber):
    """Tagesziel in ml — Laufzeit-Setting, sofort wirksam."""

    _attr_translation_key = "daily_goal"
    _attr_icon = "mdi:target"
    _attr_native_min_value = 500
    _attr_native_max_value = MAX_AMOUNT_ML
    _attr_native_step_value = 50
    _attr_native_unit_of_measurement = "ml"

    @property
    def native_value(self) -> float:
        return self._entry.runtime_data.daily_goal_ml

    def _apply(self, value: float) -> None:
        self._entry.runtime_data.daily_goal_ml = int(value)


class CustomAmountNumber(HealthOMatNumber):
    """Eigenmenge für den Buchen-Button (Default 250 ml)."""

    _attr_translation_key = "custom_amount"
    _attr_icon = "mdi:cup-outline"
    _attr_native_min_value = 1
    _attr_native_max_value = MAX_AMOUNT_ML
    _attr_native_step_value = 10
    _attr_native_unit_of_measurement = "ml"

    @property
    def native_value(self) -> float:
        return self._entry.runtime_data.custom_amount_ml or DEFAULT_CUSTOM_AMOUNT_ML

    def _apply(self, value: float) -> None:
        self._entry.runtime_data.custom_amount_ml = int(value)


class ThresholdNumber(HealthOMatNumber):
    """BP-Warnschwelle sys/dia — Laufzeit-Setting."""

    _attr_translation_key = "threshold"
    _attr_icon = "mdi:alert-decagram"
    _attr_native_step_value = 1

    def __init__(self, coordinator, entry, key: str) -> None:
        super().__init__(coordinator, entry)
        self._key = key
        self._attr_translation_key = f"threshold_{key}"
        self._attr_native_min_value = 60 if key == "dia" else 80
        self._attr_native_max_value = 260
        self._attr_native_unit_of_measurement = "mmHg"

    @property
    def native_value(self) -> float:
        rt = self._entry.runtime_data
        return getattr(rt, f"{self._key}_threshold")

    def _apply(self, value: float) -> None:
        setattr(self._entry.runtime_data, f"{self._key}_threshold", int(value))


class InputNumber(HealthOMatNumber):
    """Eingabefeld für die nächste Blutdruckmessung."""

    _attr_mode = NumberMode.BOX

    def __init__(self, coordinator, entry, key: str, translation_key: str,
                 vmin: int, vmax: int, icon: str) -> None:
        super().__init__(coordinator, entry)
        self._input_key = key
        self._attr_translation_key = translation_key
        self._attr_native_min_value = vmin
        self._attr_native_max_value = vmax
        self._attr_native_step_value = 1
        self._attr_icon = icon

    @property
    def _inputs(self) -> dict:
        rt = self._entry.runtime_data
        if not hasattr(rt, "_inputs"):
            rt._inputs = {}
        return rt._inputs

    @property
    def native_value(self) -> float | None:
        return self._inputs.get(self._input_key)

    def _apply(self, value: float) -> None:
        self._inputs[self._input_key] = value if value else None

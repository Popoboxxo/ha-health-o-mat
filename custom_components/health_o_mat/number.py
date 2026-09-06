"""Number-Entities: Runtime-Settings + BP-Eingabefelder."""
from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode

from .const import (
    DEFAULT_CUSTOM_AMOUNT_ML,
    DEFAULT_DAILY_GOAL_ML,
    DOMAIN,
    MAX_AMOUNT_ML,
)
from .entity import HealthOMatEntity, signal_refresh


async def async_setup_entry(hass, entry, async_add_entities) -> None:
    coord = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    store = hass.data[DOMAIN]["shared"]["store"]
    async_add_entities([
        DailyGoalNumber(coord, entry),
        CustomAmountNumber(coord, entry),
        ThresholdNumber(coord, entry, "sys"),
        ThresholdNumber(coord, entry, "dia"),
        InputNumber(coord, entry, store, "sys", "input_systolic", 40, 260, "mdi:arrow-up-right"),
        InputNumber(coord, entry, store, "dia", "input_diastolic", 40, 260, "mdi:arrow-down-right"),
        InputNumber(coord, entry, store, "pulse", "input_pulse", 20, 250, "mdi:heart-pulse"),
    ])


class HealthOMatNumber(HealthOMatEntity, NumberEntity):
    _attr_mode = NumberMode.BOX

    def __init__(self, coordinator, entry, key: str) -> None:
        super().__init__(coordinator, entry, key)

    def _refresh(self) -> None:
        signal_refresh(self.hass, self._entry.entry_id)

    async def async_set_native_value(self, value: float) -> None:
        await self._apply(value)
        self._refresh()

    async def _apply(self, value: float) -> None:
        raise NotImplementedError


class DailyGoalNumber(HealthOMatNumber):
    """Tagesziel in ml.

    entry.options["daily_goal_ml"] ist die einzige Quelle der Wahrheit (Audit C-2):
    sowohl der Options-Flow als auch diese Entity schreiben ausschließlich dorthin.
    runtime_data.daily_goal_ml ist nur noch ein Lese-Spiegel, der vom
    entry.add_update_listener (_options_updated in __init__.py) aus entry.options
    synchronisiert wird — Entity-Writes schreiben ihn nicht mehr direkt.
    """

    _attr_translation_key = "daily_goal"
    _attr_icon = "mdi:target"
    _attr_native_min_value = 500
    _attr_native_max_value = MAX_AMOUNT_ML
    _attr_native_step_value = 50
    _attr_native_unit_of_measurement = "ml"

    def __init__(self, coordinator, entry) -> None:
        super().__init__(coordinator, entry, "number_daily_goal")

    @property
    def native_value(self) -> float:
        # entry.options zuerst (Quelle der Wahrheit), Runtime-Spiegel nur als Fallback
        # für den kurzen Moment vor dem allerersten Options-Sync.
        return self._entry.options.get("daily_goal_ml", self._entry.runtime_data.daily_goal_ml)

    async def async_set_native_value(self, value: float) -> None:
        """Persistiert direkt in entry.options statt nur in runtime_data (Audit C-2).

        `async_update_entry` aktualisiert `entry.options` synchron (native_value ist
        danach sofort konsistent) und stößt den bereits registrierten Update-Listener
        (`_options_updated`) an, der den Runtime-Spiegel nachzieht und per
        `signal_refresh()` alle abhängigen Entities (z.B. PercentSensor,
        GoalReachedEntity) aktualisiert. Kein separater `_apply`/`_refresh`-Pfad nötig.
        """
        new_options = dict(self._entry.options)
        new_options["daily_goal_ml"] = int(value)
        self.hass.config_entries.async_update_entry(self._entry, options=new_options)

    async def _apply(self, value: float) -> None:  # pragma: no cover - nicht mehr genutzt
        raise NotImplementedError("DailyGoalNumber überschreibt async_set_native_value direkt")


class CustomAmountNumber(HealthOMatNumber):
    """Eigenmenge für den Buchen-Button."""

    _attr_translation_key = "custom_amount"
    _attr_icon = "mdi:cup-outline"
    _attr_native_min_value = 1
    _attr_native_max_value = MAX_AMOUNT_ML
    _attr_native_step_value = 10
    _attr_native_unit_of_measurement = "ml"

    def __init__(self, coordinator, entry) -> None:
        super().__init__(coordinator, entry, "number_custom_amount")

    @property
    def native_value(self) -> float:
        return self._entry.runtime_data.custom_amount_ml or DEFAULT_CUSTOM_AMOUNT_ML

    async def _apply(self, value: float) -> None:
        self._entry.runtime_data.custom_amount_ml = int(value)


class ThresholdNumber(HealthOMatNumber):
    """BP-Warnschwelle sys/dia — Laufzeit-Setting."""

    _attr_native_step_value = 1
    _attr_native_unit_of_measurement = "mmHg"

    def __init__(self, coordinator, entry, key: str) -> None:
        super().__init__(coordinator, entry, f"number_threshold_{key}")
        self._key = key
        self._attr_translation_key = f"threshold_{key}"
        self._attr_native_min_value = 60 if key == "dia" else 80
        self._attr_native_max_value = 260

    @property
    def native_value(self) -> float:
        return getattr(self._entry.runtime_data, f"{self._key}_threshold")

    async def _apply(self, value: float) -> None:
        setattr(self._entry.runtime_data, f"{self._key}_threshold", int(value))


class InputNumber(HealthOMatNumber):
    """Eingabefeld für die nächste Blutdruckmessung (Blutdruck-Manager).

    Eingaben sind persistiert (Store, REQ-HOM-104): eine halbfüllte Messung
    überlebt HA-Neustarts; save_measurement leert den Store (button.py).
    """

    def __init__(self, coordinator, entry, store, key: str, translation_key: str,
                 vmin: int, vmax: int, icon: str) -> None:
        super().__init__(coordinator, entry, f"number_input_{key}")
        self._store = store
        self._input_key = key
        self._attr_translation_key = translation_key
        self._attr_native_min_value = vmin
        self._attr_native_max_value = vmax
        self._attr_native_step_value = 1
        self._attr_icon = icon

    @property
    def native_value(self) -> float | None:
        return self._store.inputs(self._entry.entry_id).get(self._input_key)

    async def _apply(self, value: float) -> None:
        await self._store.set_inputs(
            self._entry.entry_id, self._input_key, int(value) if value else None
        )

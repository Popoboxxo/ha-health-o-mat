"""Binary-Sensoren: Tagesziel, Blutdruck-Warnung und Laborwert-Warnungen."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.util import dt as dt_util

from . import areas, logic
from .const import (
    DOMAIN,
    LAB_CATEGORY_OTHER,
    OPTION_LAB_CUSTOM_MARKERS,
    OPTION_LAB_REF_OVERRIDES,
)
from .entity import HealthOMatEntity


async def async_setup_entry(hass, entry, async_add_entities) -> None:
    coord = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    store = hass.data[DOMAIN]["shared"]["store"]
    active = areas.active_areas(entry.options)

    entities: list = []
    if active[areas.AREA_DRINK]:
        entities.append(GoalReachedEntity(coord, entry, store))
    if active[areas.AREA_BP]:
        entities.append(BloodPressureWarningEntity(coord, entry, store))
    if active[areas.AREA_LABS]:
        # Eine Warn-Entity je Kategorie (Katalog + Custom); "other" bewusst
        # ausgenommen — dort liegen ausschließlich nutzerdefinierte Marker.
        custom_markers = entry.options.get(OPTION_LAB_CUSTOM_MARKERS)
        categories = {
            marker_def["category"]
            for marker_def in logic.effective_lab_markers(custom_markers).values()
            if marker_def["category"] != LAB_CATEGORY_OTHER
        }
        for category in sorted(categories):
            entities.append(LabCategoryWarningEntity(coord, entry, store, category))
    async_add_entities(entities)


class HealthOMatBinary(HealthOMatEntity, BinarySensorEntity):
    def __init__(self, coordinator, entry, store, key: str) -> None:
        super().__init__(coordinator, entry, key)
        self._store = store

    @property
    def _data(self) -> dict:
        # Aktive Sicht: voided Getränke/Messungen zählen nicht (M2a).
        return self._store.active_entry(self._entry.entry_id)

    def _today_ml(self) -> int:
        hour = self._entry.options.get("daily_reset_hour", 0)
        return logic.today_sums(self._data.get("drinks", []), dt_util.now(), hour=hour)["total_ml"]


class GoalReachedEntity(HealthOMatBinary):
    _attr_translation_key = "goal_reached"

    def __init__(self, coordinator, entry, store) -> None:
        super().__init__(coordinator, entry, store, "binary_goal_reached")

    @property
    def is_on(self) -> bool:
        goal = max(1, self._entry.runtime_data.daily_goal_ml)
        return self._today_ml() >= goal


class BloodPressureWarningEntity(HealthOMatBinary):
    _attr_translation_key = "bp_warning"
    _attr_icon = "mdi:alert-octagon"
    # is_on == True bedeutet: letzte Messung liegt auf oder ueber dem
    # sys/dia-Schwellwert (Code: >=), also "Problem erkannt" - passt zur
    # PROBLEM-Semantik (on = Problem).
    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    def __init__(self, coordinator, entry, store) -> None:
        super().__init__(coordinator, entry, store, "binary_bp_warning")

    @property
    def is_on(self) -> bool:
        readings = self._data.get("readings", [])
        if not readings:
            return False
        last = sorted(readings, key=lambda r: r.get("ts", ""))[-1]
        rt = self._entry.runtime_data
        return last.get("sys", 0) >= rt.sys_threshold or last.get("dia", 0) >= rt.dia_threshold


class LabCategoryWarningEntity(HealthOMatBinary):
    """Warnung, wenn ≥ 1 Marker einer Kategorie außerhalb des Referenzbereichs liegt."""

    _attr_icon = "mdi:flask-alert-outline"
    # is_on == True bedeutet "mindestens ein Wert außerhalb des Referenzbereichs"
    # — passt zur PROBLEM-Semantik (on = Problem).
    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    def __init__(self, coordinator, entry, store, category: str) -> None:
        super().__init__(coordinator, entry, store, f"binary_lab_warning_{category}")
        self._category = category
        self._attr_translation_key = f"lab_warning_{category}"

    @property
    def is_on(self) -> bool:
        custom_markers = self._entry.options.get(OPTION_LAB_CUSTOM_MARKERS)
        ref_overrides = self._entry.options.get(OPTION_LAB_REF_OVERRIDES)
        for marker_key, marker_def in logic.effective_lab_markers(custom_markers).items():
            if marker_def["category"] != self._category:
                continue
            # Nur aktive Werte: voided Laborwerte dürfen keine Warnung auslösen.
            reading = self._store.last_active_lab_reading(self._entry.entry_id, marker_key)
            if reading is None:
                continue
            ref_min, ref_max = logic.resolve_lab_reference(
                marker_key,
                marker_def,
                ref_overrides if not marker_def.get("is_custom") else None,
            )
            if logic.lab_marker_in_range(reading.get("value"), ref_min, ref_max) is False:
                return True
        return False

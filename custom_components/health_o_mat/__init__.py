"""HA Health-O-Mat — Integration Setup."""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util
import voluptuous as vol

from .const import (
    DEFAULT_DIA_THRESHOLD,
    DEFAULT_DAILY_GOAL_ML,
    DEFAULT_SYS_THRESHOLD,
    DOMAIN,
)
from .entity import signal_refresh
from .store import HealthOMatStore

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.SENSOR, Platform.BINARY_SENSOR, Platform.BUTTON,
             Platform.TEXT, Platform.NUMBER, Platform.SELECT]

type HealthOMatConfigEntry = ConfigEntry[HealthOMatData]


class HealthOMatData:
    """Laufzeitdaten eines Config-Entries (= eine Person)."""

    def __init__(self) -> None:
        self.daily_goal_ml: int = DEFAULT_DAILY_GOAL_ML
        self.custom_amount_ml: int = 250
        self.sys_threshold: int = DEFAULT_SYS_THRESHOLD
        self.dia_threshold: int = DEFAULT_DIA_THRESHOLD
        self._inputs: dict = {}


async def async_setup_entry(hass: HomeAssistant, entry: HealthOMatConfigEntry) -> bool:
    """Einrichtung: ein Entry = eine Person = ein Device."""
    hass.data.setdefault(DOMAIN, {})
    shared: dict = hass.data[DOMAIN].setdefault("shared", {})

    store: HealthOMatStore | None = shared.get("store")
    if store is None:
        store = HealthOMatStore(hass)
        await store.async_load()
        shared["store"] = store

    await store.set_person(entry.entry_id, entry.data.get("person", "Person"))

    lifetime_start = entry.data.get("lifetime_start_ml")
    if lifetime_start:
        await store.set_lifetime_start(entry.entry_id, int(lifetime_start))

    coordinator = DataUpdateCoordinator(
        hass, _LOGGER,
        name=f"health_o_mat_{entry.entry_id}",
        update_method=lambda: dt_util.now().isoformat(),
        update_interval=None,
    )

    # Registry für Services + Plattformen (v0.1.0-Bug: Entry-Registry fehlte)
    hass.data[DOMAIN][entry.entry_id] = {
        "coordinator": coordinator,
        "store": store,
        "data": HealthOMatData(),
    }
    entry.runtime_data = hass.data[DOMAIN][entry.entry_id]["data"]

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    _register_services(hass)
    _apply_options(hass, entry)
    entry.async_on_unload(entry.add_update_listener(_options_updated))

    return True


def _apply_options(hass: HomeAssistant, entry) -> None:
    """Options-Werte zur Laufzeit übernehmen.

    entry.options ist die einzige Quelle der Wahrheit für daily_goal_ml (Audit C-2).
    rt.daily_goal_ml ist nur ein Lese-Spiegel für schnellen Zugriff in Sensoren/
    Binary-Sensoren — er wird ausschließlich hier und in _options_updated() aus
    entry.options nachgezogen, nie eigenständig geschrieben (auch nicht von der
    DailyGoalNumber-Entity, siehe number.py).
    """
    rt = entry.runtime_data
    opts = entry.options or {}
    if opts.get("daily_goal_ml"):
        rt.daily_goal_ml = int(opts["daily_goal_ml"])
    if opts.get("set_lifetime_ml") is not None:
        store: HealthOMatStore = hass.data[DOMAIN]["shared"]["store"]
        current = store.all_entries().get(entry.entry_id, {}).get("total_ml_lifetime", 0)
        wanted = int(opts["set_lifetime_ml"])
        if wanted != int(current):
            hass.async_create_task(store.set_lifetime_start(entry.entry_id, wanted))
            signal_refresh(hass, entry.entry_id)


async def _options_updated(hass, entry) -> None:
    """Wird bei jeder entry.options-Änderung aufgerufen (Options-Dialog UND
    DailyGoalNumber.async_set_native_value, siehe number.py — beide schreiben nur
    noch in entry.options, dieser Listener ist der einzige Sync-Punkt zurück in
    den Runtime-Spiegel rt.daily_goal_ml).
    """
    rt = entry.runtime_data
    opts = entry.options or {}
    if opts.get("daily_goal_ml"):
        rt.daily_goal_ml = int(opts["daily_goal_ml"])
    store: HealthOMatStore = hass.data[DOMAIN]["shared"]["store"]
    wanted = int(opts.get("set_lifetime_ml") or 0)
    current = int(store.all_entries().get(entry.entry_id, {}).get("total_ml_lifetime", 0))
    if wanted and wanted != current:
        await store.set_lifetime_start(entry.entry_id, wanted)
    signal_refresh(hass, entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: HealthOMatConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok


def get_runtime_data(hass: HomeAssistant, call: ServiceCall):
    """Person aus einem Service-Call auflösen (Name → Entry)."""
    wanted = (call.data.get("person") or "").strip().lower()
    matches = []
    for key, value in hass.data.get(DOMAIN, {}).items():
        if key in ("shared", "signal"):
            continue
        if not isinstance(value, dict) or "coordinator" not in value:
            continue
        person = ""
        # Person aus Entry-Daten lesen (Registry speichert nur Runtime)
        from homeassistant.config_entries import ConfigEntry  # noqa: PLC0415
        for cfg_entry in hass.config_entries.async_entries(DOMAIN):
            if cfg_entry.entry_id == key:
                person = cfg_entry.data.get("person", "")
                break
        matches.append((key, value, person.strip().lower()))

    if not matches:
        raise ServiceValidationError("Keine Health-O-Mat-Person eingerichtet")
    if not wanted:
        if len(matches) > 1:
            names = ", ".join(m[2] for m in matches)
            raise ServiceValidationError(
                f"Mehrere Personen vorhanden ({names}) — bitte 'person' angeben")
        return matches[0][0], matches[0][1]
    for key, value, person in matches:
        if person == wanted:
            return key, value
    raise ServiceValidationError(f"Person '{wanted}' nicht gefunden")


def _register_services(hass: HomeAssistant) -> None:
    """Öffentliche Services (idempotent registriert)."""
    if hass.services.has_service(DOMAIN, "add_drink"):
        return

    async def add_drink(call: ServiceCall) -> None:
        entry_id, _info = get_runtime_data(hass, call)
        ml = int(call.data["amount_ml"])
        if ml <= 0 or ml > 10000:
            raise ServiceValidationError("amount_ml muss zwischen 1 und 10000 liegen")
        store: HealthOMatStore = hass.data[DOMAIN]["shared"]["store"]
        await store.add_drink(
            entry_id, dt_util.now().isoformat(), ml,
            call.data.get("drink_type") or "Eigen",
            call.data.get("source") or "service",
        )
        signal_refresh(hass, entry_id)

    async def add_blood_pressure(call: ServiceCall) -> None:
        entry_id, _info = get_runtime_data(hass, call)
        store: HealthOMatStore = hass.data[DOMAIN]["shared"]["store"]
        pulse = call.data.get("pulse")
        await store.add_reading(
            entry_id, dt_util.now().isoformat(),
            int(call.data["systolic"]), int(call.data["diastolic"]),
            int(pulse) if pulse else None,
            call.data.get("note") or "", "service",
        )
        signal_refresh(hass, entry_id)

    async def remove_last_entry(call: ServiceCall) -> None:
        entry_id, _info = get_runtime_data(hass, call)
        store: HealthOMatStore = hass.data[DOMAIN]["shared"]["store"]
        removed = await store.remove_last_drink(entry_id)
        if not removed:
            raise ServiceValidationError("Keine Getränke zum Entfernen")
        signal_refresh(hass, entry_id)

    async def export_csv(call: ServiceCall) -> None:
        store: HealthOMatStore = hass.data[DOMAIN]["shared"]["store"]
        from .exporter import async_export_csv
        await async_export_csv(hass, store, call)

    hass.services.async_register(
        DOMAIN, "add_drink",
        schema=vol.Schema({
            vol.Required("amount_ml"): vol.Coerce(int),
            vol.Optional("drink_type"): str,
            vol.Optional("person"): str,
            vol.Optional("source"): str,
        }),
        service_func=add_drink,
    )
    hass.services.async_register(
        DOMAIN, "add_blood_pressure",
        schema=vol.Schema({
            vol.Required("systolic"): vol.Coerce(int),
            vol.Required("diastolic"): vol.Coerce(int),
            vol.Optional("pulse"): vol.Coerce(int),
            vol.Optional("person"): str,
            vol.Optional("note"): str,
        }),
        service_func=add_blood_pressure,
    )
    hass.services.async_register(
        DOMAIN, "remove_last_entry",
        schema=vol.Schema({
            vol.Optional("person"): str,
            vol.Optional("kind", default="drinks"): str,
        }),
        service_func=remove_last_entry,
    )
    hass.services.async_register(
        DOMAIN, "export_csv",
        schema=vol.Schema({
            vol.Optional("person"): str,
            vol.Optional("dataset", default="all"): vol.In(["drinks", "blood_pressure", "all"]),
        }),
        service_func=export_csv,
    )

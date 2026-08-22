"""Config-Flow: eine Person pro Einrichtung (beliebig oft wiederholbar)."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant import config_entries
from homeassistant.core import callback
import voluptuous as vol

from .const import DEFAULT_DAILY_GOAL_ML, DOMAIN

_LOGGER = logging.getLogger(__name__)

STEP_USER_SCHEMA = vol.Schema(
    {
        vol.Required("person"): str,
        vol.Optional("lifetime_start_ml", default=0): vol.Coerce(int),
    }
)


class HealthOMatConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle einen Config-Flow für HA Health-O-Mat."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}
        if user_input is not None:
            person = user_input["person"].strip()
            if not person:
                errors["person"] = "invalid_person"
            else:
                await self.async_set_unique_id(person.lower())
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=f"Health-O-Mat · {person}",
                    data={
                        "person": person,
                        "lifetime_start_ml": int(user_input.get("lifetime_start_ml", 0)),
                    },
                )
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(STEP_USER_SCHEMA, user_input),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return HealthOMatOptionsFlow()


class HealthOMatOptionsFlow(config_entries.OptionsFlow):
    """Optionen: Tagesziel + Quick-Drinks-Menge (Struktur bleibt stabil)."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Required("daily_goal_ml", default=2000): vol.All(vol.Coerce(int), vol.Range(min=500, max=10000)),
            }),
        )

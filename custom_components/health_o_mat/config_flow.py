"""Config-Flow: eine Person pro Einrichtung (+ Options: Ziel, Quick-Drinks, Anzeigename).

Schema-Versionen:
- v1 (≤ v0.4.0): quick_drinks lagen in entry.data (unveränderlich — Fund F1)
- v2 (ab v0.5.0): entry.data nur noch strukturell (person-Slug, lifetime_start_ml);
  quick_drinks + person_display liegen in entry.options und sind editierbar.
async_migrate_entry verlagert bestehende Werte bei Update ohne Datenverlust.
"""
from __future__ import annotations

import logging
from typing import Any

from homeassistant import config_entries
from homeassistant.core import callback
import voluptuous as vol

from .const import DEFAULT_DAILY_GOAL_ML, DEFAULT_QUICK_DRINKS, DOMAIN

_LOGGER = logging.getLogger(__name__)

STEP_USER_SCHEMA = vol.Schema({vol.Required("person"): str})


def _default_quick_drinks() -> list[dict]:
    """Frische Kopie der Standard-Quick-Drinks (keine geteilten Referenzen)."""
    return [dict(qd) for qd in DEFAULT_QUICK_DRINKS]


def quick_drinks_schema(current: list[dict]) -> vol.Schema:
    """Formular für 4 Quick-Drink-Slots (Label, ml, Icon)."""
    slots = {}
    for i in range(4):
        qd = current[i] if i < len(current) else {}
        slots[vol.Required(f"quick_{i}_label",
                           default=qd.get("label", f"Quick {i + 1}"))] = str
        slots[vol.Required(f"quick_{i}_ml",
                           default=int(qd.get("ml", 200)))] = vol.All(
            vol.Coerce(int), vol.Range(min=1, max=10000))
        slots[vol.Optional(f"quick_{i}_icon",
                           default=qd.get("icon", "mdi:cup-water"))] = str
    return vol.Schema(slots)


def quick_drinks_from_user_input(user_input: dict[str, Any]) -> list[dict]:
    """Formularfelder → Quick-Drinks-Liste (Reihenfolge fix, 4 Slots)."""
    return [
        {
            "key": f"slot_{i}",
            "label": user_input[f"quick_{i}_label"].strip() or f"Quick {i + 1}",
            "ml": int(user_input[f"quick_{i}_ml"]),
            "icon": user_input[f"quick_{i}_icon"] or "mdi:cup-water",
        }
        for i in range(4)
    ]


class HealthOMatConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle einen Config-Flow für HA Health-O-Mat."""

    VERSION = 2

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
                        # Quick-Drinks/Anzeigename gehören in Options (Fund F1):
                        # editierbar ohne Neu-Anlegen, entry.data bleibt strukturell.
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
    """Options: Tagesziel/Lebenszähler → Quick-Drinks → Speichern."""

    def __init__(self) -> None:
        self._pending: dict[str, Any] = {}

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        """Schritt 1: Tagesziel, Lebenszähler-Startwert, Anzeige-Name."""
        if user_input is not None:
            self._pending.update(user_input)
            return await self.async_step_quick_drinks()
        current_goal = self.config_entry.options.get("daily_goal_ml")
        if current_goal is None:
            current_goal = getattr(self.config_entry.runtime_data, "daily_goal_ml",
                                   DEFAULT_DAILY_GOAL_ML) \
                if self.config_entry.runtime_data else DEFAULT_DAILY_GOAL_ML
        lifetime = 0
        store = self.hass.data.get(DOMAIN, {}).get("shared", {}).get("store")
        if store:
            e = store.all_entries().get(self.config_entry.entry_id, {})
            lifetime = int(e.get("total_ml_lifetime", 0))
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Required("daily_goal_ml", default=current_goal): vol.All(
                    vol.Coerce(int), vol.Range(min=500, max=10000)),
                vol.Optional("set_lifetime_ml", default=lifetime): vol.All(vol.Coerce(int)),
                vol.Optional("person_display",
                             default=self.config_entry.options.get("person_display")
                             or self.config_entry.data.get("person", "")): str,
            }),
        )

    async def async_step_quick_drinks(self, user_input: dict[str, Any] | None = None):
        """Schritt 2: vier Quick-Drink-Slots editieren."""
        current = self.config_entry.options.get("quick_drinks") or _default_quick_drinks()
        if user_input is not None:
            merged = dict(self._pending)
            merged["quick_drinks"] = quick_drinks_from_user_input(user_input)
            return self.async_create_entry(title="", data=merged)
        return self.async_show_form(
            step_id="quick_drinks",
            data_schema=quick_drinks_schema(current),
            description_placeholders={"person": self.config_entry.data.get("person", "")},
        )

"""Config-Flow: eine Person pro Einrichtung (+ Options: Ziel, Quick-Drinks,
Anzeigename, Erinnerungen, Wochenbericht).

Schema-Versionen:
- v1 (≤ v0.4.0): quick_drinks lagen in entry.data (unveränderlich — Fund F1)
- v2 (ab v0.5.0): entry.data nur noch strukturell (person-Slug, lifetime_start_ml);
  quick_drinks + person_display liegen in entry.options und sind editierbar.
async_migrate_entry verlagert bestehende Werte bei Update ohne Datenverlust.
"""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import selector

from . import areas, logic, parser, reminders
from .const import (
    DEFAULT_DAILY_GOAL_ML,
    DEFAULT_QUICK_DRINKS,
    DOMAIN,
    DRINK_LEXICON,
    MAX_RETENTION_MONTHS,
    OPTION_REMINDERS,
    OPTION_WEEKLY_REPORT,
    WELLBEING_IMAGES_OPTION,
    WELLBEING_STATES,
)
from .panel import OPTION_ENABLE_SIDEBAR_PANEL

_LOGGER = logging.getLogger(__name__)

STEP_USER_SCHEMA = vol.Schema({vol.Required("person"): str})


def _default_quick_drinks() -> list[dict]:
    """Frische Kopie der Standard-Quick-Drinks (keine geteilten Referenzen)."""
    return [dict(qd) for qd in DEFAULT_QUICK_DRINKS]


_AREA_FORM_FIELDS: dict[str, str] = {
    "area_drink": areas.AREA_DRINK,
    "area_bp": areas.AREA_BP,
    "area_wellbeing": areas.AREA_WELLBEING,
}


def areas_from_user_input(user_input: dict[str, Any], current: dict[str, bool]) -> dict[str, bool]:
    """Flache ``area_*``-Formularfelder → verschachteltes ``areas``-Dict.

    Fehlt ein Feld im Input, bleibt der bisherige Wert (``current``) erhalten —
    so kippt ein unvollständiger Submit keinen Bereich unbeabsichtigt auf aktiv.
    """
    return {
        area: bool(user_input[field]) if field in user_input else current[area]
        for field, area in _AREA_FORM_FIELDS.items()
    }


def quick_drinks_schema(current: list[dict]) -> vol.Schema:
    """Formular für 4 Quick-Drink-Slots (Label, ml, Icon)."""
    slots = {}
    for i in range(4):
        qd = current[i] if i < len(current) else {}
        slots[vol.Required(f"quick_{i}_label", default=qd.get("label", f"Quick {i + 1}"))] = str
        slots[vol.Required(f"quick_{i}_ml", default=int(qd.get("ml", 200)))] = vol.All(
            vol.Coerce(int), vol.Range(min=1, max=10000)
        )
        slots[vol.Optional(f"quick_{i}_icon", default=qd.get("icon", "mdi:cup-water"))] = str
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


def wellbeing_images_schema(current: dict[str, str] | None) -> vol.Schema:
    """Formular für optionale eigene Bilder je Wellbeing-Key.

    Die Eingabe ist eine Bild-URL oder ein Dateiname/Pfad (PNG/JPG/WebP).
    Reine Dateinamen werden auf ``/local/<name>`` abgebildet; Pfade unter
    ``/config/www/`` sind damit direkt erreichbar.
    """
    images = logic.normalize_wellbeing_images(current or {})
    fields = {}
    for state in WELLBEING_STATES:
        fields[
            vol.Optional(f"wellbeing_image_{state['key']}", default=images.get(state["key"], ""))
        ] = str
    return vol.Schema(fields)


def wellbeing_images_from_user_input(user_input: dict[str, Any]) -> dict[str, str]:
    """Formularfelder → normalisiertes ``{key: bild}`` (leere Werte entfallen)."""
    raw: dict[str, str] = {}
    for state in WELLBEING_STATES:
        raw[state["key"]] = user_input.get(f"wellbeing_image_{state['key']}", "")
    return logic.normalize_wellbeing_images(raw)


_WEEKDAY_LABELS: dict[str, tuple[str, ...]] = {
    "de": ("Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"),
    "en": ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"),
}

_WEEKDAY_NAMES: dict[str, tuple[str, ...]] = {
    "de": (
        "Montag",
        "Dienstag",
        "Mittwoch",
        "Donnerstag",
        "Freitag",
        "Samstag",
        "Sonntag",
    ),
    "en": (
        "Monday",
        "Tuesday",
        "Wednesday",
        "Thursday",
        "Friday",
        "Saturday",
        "Sunday",
    ),
}


class OptionalTimeSelector(selector.TimeSelector):
    """TimeSelector, der ein leeres Feld zulässt (optionale Quiet-Hours-Grenze).

    ``cv.time`` weist ``""`` ab; für die optionalen Ruhefenster ist ein leeres
    Feld aber der Normalfall (kein Ruhefenster). Die UI rendert weiterhin einen
    Time-Picker, weil ``selector_type`` geerbt wird.
    """

    def __call__(self, data):
        if data is None or (isinstance(data, str) and not data.strip()):
            return ""
        return super().__call__(data)


def notifications_schema(options: dict[str, Any] | None, language: str = "de") -> vol.Schema:
    """Formular für Erinnerungen + Wochenbericht (Defaults aus entry.options)."""
    raw = options if isinstance(options, dict) else {}
    rem = reminders.normalize_reminders(raw.get(OPTION_REMINDERS))
    weekly = reminders.normalize_weekly_report(raw.get(OPTION_WEEKLY_REPORT))
    lang = reminders.normalize_language(language)
    day_options = [
        selector.SelectOptionDict(value=str(index), label=label)
        for index, label in enumerate(_WEEKDAY_LABELS[lang])
    ]
    weekly_options = [
        selector.SelectOptionDict(value=str(index), label=label)
        for index, label in enumerate(_WEEKDAY_NAMES[lang])
    ]
    return vol.Schema(
        {
            vol.Optional("reminders_enabled", default=rem["enabled"]): bool,
            vol.Optional("reminder_time", default=rem["time"]): selector.TimeSelector(),
            vol.Optional(
                "reminder_days",
                default=[str(day) for day in rem["days"]],
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(options=day_options, multiple=True)
            ),
            vol.Optional("reminder_notify_service", default=rem["notify_service"]): str,
            vol.Optional(
                "reminder_quiet_start", default=rem["quiet_start"]
            ): OptionalTimeSelector(),
            vol.Optional("reminder_quiet_end", default=rem["quiet_end"]): OptionalTimeSelector(),
            vol.Optional("reminder_drink_goal", default=rem["conditions"]["drink_goal"]): bool,
            vol.Optional(
                "reminder_no_drink_hours", default=rem["conditions"]["no_drink_hours"]
            ): vol.All(vol.Coerce(int), vol.Range(min=0, max=24)),
            vol.Optional("reminder_bp_days", default=rem["conditions"]["bp_days"]): vol.All(
                vol.Coerce(int), vol.Range(min=0, max=365)
            ),
            vol.Optional(
                "reminder_wellbeing_days", default=rem["conditions"]["wellbeing_days"]
            ): vol.All(vol.Coerce(int), vol.Range(min=0, max=365)),
            vol.Optional("weekly_report_enabled", default=weekly["enabled"]): bool,
            vol.Optional("weekly_report_day", default=str(weekly["day"])): selector.SelectSelector(
                selector.SelectSelectorConfig(options=weekly_options)
            ),
            vol.Optional("weekly_report_time", default=weekly["time"]): selector.TimeSelector(),
            vol.Optional("weekly_report_notify_service", default=weekly["notify_service"]): str,
        }
    )


def notifications_from_user_input(user_input: dict[str, Any]) -> dict[str, Any]:
    """Flache Formularfelder → normalisierte genestete Options-Strukturen."""
    rem = reminders.normalize_reminders(
        {
            "enabled": user_input.get("reminders_enabled", False),
            "time": user_input.get("reminder_time"),
            "days": user_input.get("reminder_days"),
            "notify_service": user_input.get("reminder_notify_service", ""),
            "quiet_start": user_input.get("reminder_quiet_start", ""),
            "quiet_end": user_input.get("reminder_quiet_end", ""),
            "conditions": {
                "drink_goal": user_input.get("reminder_drink_goal", True),
                "no_drink_hours": user_input.get("reminder_no_drink_hours", 3),
                "bp_days": user_input.get("reminder_bp_days", 0),
                "wellbeing_days": user_input.get("reminder_wellbeing_days", 0),
            },
        }
    )
    weekly = reminders.normalize_weekly_report(
        {
            "enabled": user_input.get("weekly_report_enabled", False),
            "day": user_input.get("weekly_report_day", 0),
            "time": user_input.get("weekly_report_time"),
            "notify_service": user_input.get("weekly_report_notify_service", ""),
        }
    )
    return {OPTION_REMINDERS: rem, OPTION_WEEKLY_REPORT: weekly}


def drink_lexicon_schema(current_text: str) -> vol.Schema:
    """Formular für das Getränke-Lexikon (mehrzeiliges Textfeld)."""
    return vol.Schema(
        {
            vol.Required("drink_lexicon", default=current_text): selector.TextSelector(
                selector.TextSelectorConfig(multiline=True)
            ),
        }
    )


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
    """Options: Allgemein → Quick-Drinks → Bilder → Lexikon → Benachrichtigungen."""

    def __init__(self) -> None:
        self._pending: dict[str, Any] = {}

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        """Schritt 1: Tagesziel, Lebenszähler-Startwert, Anzeige-Name."""
        if user_input is not None:
            pending = dict(user_input)
            for field in _AREA_FORM_FIELDS:
                pending.pop(field, None)
            pending["areas"] = areas_from_user_input(
                user_input, areas.active_areas(self.config_entry.options)
            )
            self._pending.update(pending)
            return await self.async_step_quick_drinks()
        current_goal = self.config_entry.options.get("daily_goal_ml")
        if current_goal is None:
            current_goal = (
                getattr(self.config_entry.runtime_data, "daily_goal_ml", DEFAULT_DAILY_GOAL_ML)
                if self.config_entry.runtime_data
                else DEFAULT_DAILY_GOAL_ML
            )
        lifetime = 0
        store = self.hass.data.get(DOMAIN, {}).get("shared", {}).get("store")
        if store:
            e = store.all_entries().get(self.config_entry.entry_id, {})
            lifetime = int(e.get("total_ml_lifetime", 0))
        current_retention = self.config_entry.options.get("retention_months") or 0
        current_areas = areas.active_areas(self.config_entry.options)
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required("daily_goal_ml", default=current_goal): vol.All(
                        vol.Coerce(int), vol.Range(min=500, max=10000)
                    ),
                    vol.Optional("set_lifetime_ml", default=lifetime): vol.All(vol.Coerce(int)),
                    vol.Optional(
                        "person_display",
                        default=self.config_entry.options.get("person_display")
                        or self.config_entry.data.get("person", ""),
                    ): str,
                    vol.Optional(
                        "daily_reset_hour",
                        default=self.config_entry.options.get("daily_reset_hour", 0),
                    ): vol.All(vol.Coerce(int), vol.Range(min=0, max=23)),
                    # Retention/Archiv (REQ-HOM-109): 0 = AUS (Default, exakt bisheriges
                    # Verhalten); >0 = Einträge älter als X Monate beim Start archivieren.
                    vol.Optional(
                        "retention_months",
                        default=int(current_retention),
                    ): vol.All(vol.Coerce(int), vol.Range(min=0, max=MAX_RETENTION_MONTHS)),
                    # Opt-in-Sidebar-Panel (CONCEPT-UI §8.3): Default AUS; der
                    # bestehende Wert wird unverändert als Default übernommen.
                    # `bool` (nicht `vol.Boolean()`) ist Pflicht: nur `bool`
                    # serialisiert zu einem Boolean-Toggle im Options-Dialog.
                    vol.Optional(
                        OPTION_ENABLE_SIDEBAR_PANEL,
                        default=bool(
                            self.config_entry.options.get(OPTION_ENABLE_SIDEBAR_PANEL, False)
                        ),
                    ): bool,
                    vol.Optional(
                        "area_drink",
                        default=current_areas[areas.AREA_DRINK],
                    ): bool,
                    vol.Optional(
                        "area_bp",
                        default=current_areas[areas.AREA_BP],
                    ): bool,
                    vol.Optional(
                        "area_wellbeing",
                        default=current_areas[areas.AREA_WELLBEING],
                    ): bool,
                }
            ),
        )

    async def async_step_quick_drinks(self, user_input: dict[str, Any] | None = None):
        """Schritt 2: vier Quick-Drink-Slots editieren."""
        current = self.config_entry.options.get("quick_drinks") or _default_quick_drinks()
        if user_input is not None:
            self._pending["quick_drinks"] = quick_drinks_from_user_input(user_input)
            return await self.async_step_wellbeing_images()
        return self.async_show_form(
            step_id="quick_drinks",
            data_schema=quick_drinks_schema(current),
            description_placeholders={"person": self.config_entry.data.get("person", "")},
        )

    async def async_step_wellbeing_images(self, user_input: dict[str, Any] | None = None):
        """Schritt 3: optionale eigene Bilder je Wellbeing-Key (PNG/JPG/WebP)."""
        if user_input is not None:
            self._pending[WELLBEING_IMAGES_OPTION] = wellbeing_images_from_user_input(user_input)
            return await self.async_step_drink_lexicon()
        return self.async_show_form(
            step_id="wellbeing_images",
            data_schema=wellbeing_images_schema(
                self.config_entry.options.get(WELLBEING_IMAGES_OPTION)
            ),
        )

    async def async_step_drink_lexicon(self, user_input: dict[str, Any] | None = None):
        """Schritt 4: Getränke-Lexikon bearbeiten, dann zu den Benachrichtigungen."""
        if user_input is not None:
            raw_text = user_input["drink_lexicon"]
            try:
                lexicon = parser.parse_lexicon_text(raw_text)
            except ValueError as err:
                return self.async_show_form(
                    step_id="drink_lexicon",
                    data_schema=drink_lexicon_schema(raw_text),
                    errors={"base": "invalid_lexicon_format"},
                    description_placeholders={"detail": str(err)},
                )
            # Bestehende Optionen übernehmen: der Options-Flow zeigt nicht jede
            # Option als Feld (z. B. `wellbeing_confirm` aus dem Panel). Ein
            # reiner `_pending`-Dict würde sie beim Speichern verlieren.
            self._pending["drink_lexicon"] = lexicon
            return await self.async_step_notifications()

        current = self.config_entry.options.get("drink_lexicon") or DRINK_LEXICON
        return self.async_show_form(
            step_id="drink_lexicon",
            data_schema=drink_lexicon_schema(parser.format_lexicon(current)),
        )

    async def async_step_notifications(self, user_input: dict[str, Any] | None = None):
        """Schritt 5 (terminal): Erinnerungen + Wochenbericht, dann speichern.

        Die Felder sind flach (HA-Formular), gespeichert werden die
        genesteten, normalisierten Strukturen. Bestehende Optionen, die kein
        Formularfeld haben (z. B. `wellbeing_confirm`, `audit_limit`), bleiben
        über den Merge erhalten.
        """
        if user_input is not None:
            self._pending.update(notifications_from_user_input(user_input))
            merged = dict(self.config_entry.options)
            merged.update(self._pending)
            return self.async_create_entry(title="", data=merged)

        language = reminders.normalize_language(
            getattr(getattr(self.hass, "config", None), "language", None)
        )
        return self.async_show_form(
            step_id="notifications",
            data_schema=notifications_schema(self.config_entry.options, language),
        )

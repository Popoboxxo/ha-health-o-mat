"""Tests: Options-Flow als Menü-Wizard (REQ-HOM-101/109/114/118/119).

Der Options-Flow ist seit M3e (REQ-HOM-119) ein Menü mit optionalen
Abschnitten. Änderungen landen in ``_pending`` und werden erst in der
Zusammenfassung gemerged gespeichert — nicht angezeigte Optionen bleiben so
erhalten.
"""

import asyncio
import importlib.util
import os
import sys
import types
from unittest.mock import MagicMock, PropertyMock

import pytest

_COMPONENT_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "custom_components", "health_o_mat")
)

# Fake-Paket für relative Imports
_PKG = "_hom_test_pkg"
_pkg = types.ModuleType(_PKG)
_pkg.__path__ = [_COMPONENT_DIR]
sys.modules.setdefault(_PKG, _pkg)


def _load(name: str):
    spec = importlib.util.spec_from_file_location(
        f"{_PKG}.{name}", os.path.join(_COMPONENT_DIR, f"{name}.py")
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[f"{_PKG}.{name}"] = module
    spec.loader.exec_module(module)
    return module


config_flow_module = _load("config_flow")


def _async_test(coro):
    """Helper to run async functions in sync test context."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


_MISSING = object()


def _make_flow(options=None, data=None, runtime=_MISSING, store=_MISSING):
    """OptionsFlow mit gemocktem Config-Entry/Hass bauen."""
    options_flow = config_flow_module.HealthOMatOptionsFlow()

    entry = MagicMock()
    entry.options = {} if options is None else options
    entry.data = {"person": "Max"} if data is None else data
    entry.entry_id = "test-entry-1"
    entry.runtime_data = MagicMock() if runtime is _MISSING else runtime

    hass = MagicMock()
    hass.data = {}
    if store is not _MISSING:
        hass.data = {"health_o_mat": {"shared": {"store": store}}}

    type(options_flow).config_entry = PropertyMock(return_value=entry)
    type(options_flow).hass = PropertyMock(return_value=hass)
    return options_flow


def _quick_input(ml: int = 200, prefix: str = "Drink") -> dict:
    """Vollständige Quick-Drink-Formulareingabe für vier Slots."""
    user_input = {}
    for i in range(4):
        user_input[f"quick_{i}_label"] = f"{prefix} {i}"
        user_input[f"quick_{i}_ml"] = ml
        user_input[f"quick_{i}_icon"] = "mdi:cup-water"
    return user_input


def _schema_defaults(result: dict) -> dict:
    """Formular-Defaults aus einem async_show_form-Ergebnis lesen."""
    return {str(key): key.default() for key in result["data_schema"].schema}


# --- ConfigFlow / OptionsFlow Grundlagen -----------------------------------


def test_config_flow_get_options_flow_returns_options_flow_instance():
    """[AUDIT-7b-C-2] ConfigFlow.async_get_options_flow returns OptionsFlow instance."""
    config_flow = config_flow_module.HealthOMatConfigFlow()

    result = config_flow.async_get_options_flow(MagicMock())

    assert isinstance(result, config_flow_module.HealthOMatOptionsFlow)


def test_config_flow_version():
    """ConfigFlow VERSION 2 (quick_drinks → options, Fund F1 / REQ-HOM-101)."""
    config_flow = config_flow_module.HealthOMatConfigFlow()
    assert config_flow.VERSION == 2


# --- Menü-Navigation (REQ-HOM-119) -----------------------------------------


def test_init_step_shows_menu_with_all_sections():
    """[REQ-HOM-119] async_step_init zeigt das Menü mit allen Abschnitten."""
    options_flow = _make_flow()

    result = _async_test(options_flow.async_step_init(None))

    assert result["type"] == "menu"
    assert result["step_id"] == "init"
    assert result["menu_options"] == [
        "basics",
        "drinks",
        "wellbeing",
        "notifications",
        "defaults",
        "summary",
    ]
    assert result["description_placeholders"]["person"] == "Max"


def test_init_step_ignores_user_input_and_always_shows_menu():
    """[REQ-HOM-119] Das Menü hat kein Formular — HA routet die Auswahl selbst."""
    options_flow = _make_flow()

    result = _async_test(options_flow.async_step_init({"next_step_id": "basics"}))

    assert result["type"] == "menu"
    assert options_flow._pending == {}


# --- Grundlagen (basics) ---------------------------------------------------


def test_basics_step_defaults_from_options_and_store():
    """[REQ-HOM-101/109] Grundlagen-Vorbelegung aus Options + Store."""
    store = MagicMock()
    store.all_entries = MagicMock(return_value={"test-entry-1": {"total_ml_lifetime": 1000}})
    options_flow = _make_flow(
        options={
            "daily_goal_ml": 2500,
            "person_display": "Maxi",
            "daily_reset_hour": 4,
            "retention_months": 6,
            "enable_sidebar_panel": True,
            "areas": {"drink": False, "bp": True},
        },
        store=store,
    )

    result = _async_test(options_flow.async_step_basics(None))
    defaults = _schema_defaults(result)

    assert result["type"] == "form"
    assert result["step_id"] == "basics"
    assert defaults["daily_goal_ml"] == 2500
    assert defaults["set_lifetime_ml"] == 1000
    assert defaults["person_display"] == "Maxi"
    assert defaults["daily_reset_hour"] == 4
    assert defaults["retention_months"] == 6
    assert defaults["enable_sidebar_panel"] is True
    assert defaults["area_drink"] is False
    assert defaults["area_bp"] is True
    assert defaults["area_wellbeing"] is True
    assert defaults["skip"] is False
    assert (
        result["data_schema"].schema[
            next(key for key in result["data_schema"].schema if str(key) == "enable_sidebar_panel")
        ]
        is bool
    )


def test_basics_step_falls_back_to_runtime_daily_goal():
    """[AUDIT-7b-C-2] Ohne Options zählt runtime_data.daily_goal_ml."""
    runtime = MagicMock()
    runtime.daily_goal_ml = 3000
    options_flow = _make_flow(options={}, runtime=runtime)

    result = _async_test(options_flow.async_step_basics(None))

    assert _schema_defaults(result)["daily_goal_ml"] == 3000


def test_basics_step_falls_back_to_default_without_runtime_data():
    """[AUDIT-7b-C-2] Ohne Options und Runtime gilt DEFAULT_DAILY_GOAL_ML."""
    options_flow = _make_flow(options={}, runtime=None)

    result = _async_test(options_flow.async_step_basics(None))

    assert _schema_defaults(result)["daily_goal_ml"] == config_flow_module.DEFAULT_DAILY_GOAL_ML


def test_basics_step_handles_missing_store():
    """[AUDIT-7b-C-2] Fehlender Store → Lebenszähler 0, Formular bleibt nutzbar."""
    options_flow = _make_flow(options={}, store=_MISSING)

    result = _async_test(options_flow.async_step_basics(None))

    assert _schema_defaults(result)["set_lifetime_ml"] == 0


def test_basics_step_reads_lifetime_from_store():
    """[AUDIT-7b-C-2] Lebenszähler wird aus dem Store vorbelegt."""
    store = MagicMock()
    store.all_entries = MagicMock(return_value={"test-entry-1": {"total_ml_lifetime": 5000}})
    options_flow = _make_flow(store=store)

    _async_test(options_flow.async_step_basics(None))

    store.all_entries.assert_called_once()


def test_basics_step_uses_pending_before_options():
    """[REQ-HOM-119] Nach einem Submit gewinnt der vorgemerkte Wert."""
    options_flow = _make_flow(options={"daily_goal_ml": 2000})
    options_flow._pending["daily_goal_ml"] = 2750

    result = _async_test(options_flow.async_step_basics(None))

    assert _schema_defaults(result)["daily_goal_ml"] == 2750


def test_basics_step_daily_reset_hour_accepts_only_0_to_23():
    """[Spec Feature 2] vol.Range(min=0, max=23) lehnt 24/-1 ab."""
    import voluptuous as vol  # noqa: PLC0415

    options_flow = _make_flow()
    result = _async_test(options_flow.async_step_basics(None))
    schema = result["data_schema"]

    for bad in (24, -1):
        with pytest.raises(vol.Invalid):
            schema({"daily_goal_ml": 2000, "daily_reset_hour": bad})
    for good in (0, 6, 23):
        validated = schema({"daily_goal_ml": 2000, "daily_reset_hour": good})
        assert validated["daily_reset_hour"] == good


def test_basics_step_retention_months_defaults_off_and_validates_range():
    """[REQ-HOM-109] retention_months: Default 0 (AUS), Range 0..MAX."""
    import voluptuous as vol  # noqa: PLC0415

    options_flow = _make_flow()
    schema = _async_test(options_flow.async_step_basics(None))["data_schema"]

    retention_key = next(k for k in schema.schema if str(k) == "retention_months")
    assert retention_key.default() == 0

    max_months = config_flow_module.MAX_RETENTION_MONTHS
    for good in (0, max_months):
        assert schema({"daily_goal_ml": 2000, "retention_months": good})["retention_months"] == good
    for bad in (-1, max_months + 1):
        with pytest.raises(vol.Invalid):
            schema({"daily_goal_ml": 2000, "retention_months": bad})


def test_basics_step_area_toggles_default_all_true():
    """[REQ-HOM-009] Ohne areas-Option: alle Toggles default True, Typ bool."""
    options_flow = _make_flow(options={})
    schema = _async_test(options_flow.async_step_basics(None))["data_schema"]

    for field in ("area_drink", "area_bp", "area_wellbeing"):
        key = next(k for k in schema.schema if str(k) == field)
        assert key.default() is True
        assert schema.schema[key] is bool


def test_basics_submit_stores_nested_areas_and_returns_to_menu():
    """[REQ-HOM-009/119] Submit merkt Werte vor und kehrt ins Menü zurück."""
    options_flow = _make_flow(options={})

    result = _async_test(
        options_flow.async_step_basics(
            {
                "daily_goal_ml": 2250,
                "set_lifetime_ml": 0,
                "person_display": "Max",
                "daily_reset_hour": 3,
                "retention_months": 6,
                "enable_sidebar_panel": True,
                "area_drink": False,
                "area_bp": True,
                "area_wellbeing": False,
            }
        )
    )

    assert result["type"] == "menu"
    assert options_flow._pending["daily_goal_ml"] == 2250
    assert options_flow._pending["areas"] == {
        "drink": False,
        "bp": True,
        "wellbeing": False,
    }
    assert not any(key.startswith("area_") for key in options_flow._pending)
    assert "skip" not in options_flow._pending


def test_basics_skip_returns_to_menu_without_changes():
    """[REQ-HOM-119] skip=True lässt `_pending` unverändert."""
    options_flow = _make_flow()
    options_flow._pending = {"daily_goal_ml": 2000}

    result = _async_test(options_flow.async_step_basics({"skip": True}))

    assert result["type"] == "menu"
    assert options_flow._pending == {"daily_goal_ml": 2000}


def test_areas_from_user_input_keeps_current_for_missing_fields():
    """[REQ-HOM-009] Fehlt ein Feld, bleibt der bisherige Wert (kein Kipp auf True)."""
    current = {"drink": False, "bp": True, "wellbeing": False}
    assert config_flow_module.areas_from_user_input({"area_drink": True}, current) == {
        "drink": True,
        "bp": True,
        "wellbeing": False,
    }


# --- Getränke (drinks: Quick-Drinks + Lexikon) -----------------------------


def test_drinks_step_combines_quick_drinks_and_lexicon():
    """[REQ-HOM-119] Ein Formular für Quick-Drinks und Lexikon."""
    options_flow = _make_flow(
        options={
            "quick_drinks": [{"key": "slot_0", "label": "Kaffee", "ml": 250, "icon": "mdi:coffee"}],
            "drink_lexicon": {"matecha": ("Matcha-Tee", 300)},
        }
    )

    result = _async_test(options_flow.async_step_drinks(None))
    defaults = _schema_defaults(result)

    assert result["type"] == "form"
    assert result["step_id"] == "drinks"
    assert defaults["quick_0_label"] == "Kaffee"
    assert defaults["quick_0_ml"] == 250
    assert defaults["quick_1_label"] == "Quick 2"
    assert defaults["drink_lexicon"] == "matecha=Matcha-Tee,300"
    assert defaults["skip"] is False


def test_drinks_step_falls_back_to_builtin_defaults():
    """[REQ-HOM-119] Ohne Optionen greifen DEFAULT_QUICK_DRINKS und DRINK_LEXICON."""
    options_flow = _make_flow(options={})

    result = _async_test(options_flow.async_step_drinks(None))
    defaults = _schema_defaults(result)

    assert defaults["quick_0_label"] == config_flow_module.DEFAULT_QUICK_DRINKS[0]["label"]
    assert "wasser=Wasser,250" in defaults["drink_lexicon"]


def test_drinks_submit_stores_both_and_returns_to_menu():
    """[REQ-HOM-119] Submit merkt Quick-Drinks + Lexikon vor."""
    options_flow = _make_flow(options={})

    result = _async_test(
        options_flow.async_step_drinks({**_quick_input(250), "drink_lexicon": "kaffee=Kaffee,250"})
    )

    assert result["type"] == "menu"
    assert len(options_flow._pending["quick_drinks"]) == 4
    assert options_flow._pending["quick_drinks"][0]["label"] == "Drink 0"
    assert options_flow._pending["drink_lexicon"] == {"kaffee": ("Kaffee", 250)}
    assert "skip" not in options_flow._pending


def test_drinks_invalid_lexicon_reshows_form_with_line_error():
    """[Spec Feature 1 / REQ-HOM-119] Zeilenfehler → Formular mit errors, kein Pending."""
    options_flow = _make_flow(options={})

    result = _async_test(
        options_flow.async_step_drinks({**_quick_input(), "drink_lexicon": "kaffee=Kaffee"})
    )

    assert result["type"] == "form"
    assert result["step_id"] == "drinks"
    assert result["errors"] == {"base": "invalid_lexicon_format"}
    assert "Zeile 1" in result["description_placeholders"]["detail"]
    assert "quick_drinks" not in options_flow._pending
    assert "drink_lexicon" not in options_flow._pending


def test_drinks_invalid_lexicon_keeps_submitted_quick_drink_values():
    """[REQ-HOM-119] Beim Fehler bleiben die eingegebenen Quick-Drinks erhalten."""
    options_flow = _make_flow(options={})

    result = _async_test(
        options_flow.async_step_drinks(
            {**_quick_input(333, prefix="Eingabe"), "drink_lexicon": "kaputt"}
        )
    )

    defaults = _schema_defaults(result)
    assert defaults["quick_0_label"] == "Eingabe 0"
    assert defaults["quick_0_ml"] == 333
    assert defaults["drink_lexicon"] == "kaputt"


def test_drinks_skip_returns_to_menu_without_changes():
    """[REQ-HOM-119] skip überspringt den kombinierten Getränke-Schritt."""
    options_flow = _make_flow()
    options_flow._pending = {"daily_goal_ml": 2000}

    result = _async_test(options_flow.async_step_drinks({"skip": True}))

    assert result["type"] == "menu"
    assert options_flow._pending == {"daily_goal_ml": 2000}


def test_drinks_quick_drink_ml_range_is_validated():
    """[Spec Feature 1] ml außerhalb 1..10000 wird vom Schema abgewiesen."""
    import voluptuous as vol  # noqa: PLC0415

    options_flow = _make_flow()
    schema = _async_test(options_flow.async_step_drinks(None))["data_schema"]

    for bad in (0, 10001):
        with pytest.raises(vol.Invalid):
            schema({**_quick_input(bad), "drink_lexicon": "kaffee=Kaffee,250"})


# --- Wohlbefinden (wellbeing) ----------------------------------------------


def test_wellbeing_step_maps_and_normalizes_images():
    """[REQ-HOM-119] Bildfelder werden auf gültige Keys normalisiert."""
    options_flow = _make_flow(options={})

    result = _async_test(
        options_flow.async_step_wellbeing(
            {
                "wellbeing_image_very_bad": "stufe1.png",
                "wellbeing_image_good": "/local/good.jpg",
                "wellbeing_image_poor": "böse.html",
            }
        )
    )

    assert result["type"] == "menu"
    assert options_flow._pending["wellbeing_images"] == {
        "very_bad": "/local/stufe1.png",
        "good": "/local/good.jpg",
    }


def test_wellbeing_step_has_all_ten_image_fields_plus_skip():
    """[REQ-HOM-119] Jede der zehn Stufen hat ein Feld, plus skip."""
    options_flow = _make_flow(options={})

    result = _async_test(options_flow.async_step_wellbeing(None))
    defaults = _schema_defaults(result)

    assert result["step_id"] == "wellbeing"
    assert len([key for key in defaults if key.startswith("wellbeing_image_")]) == 10
    assert "wellbeing_image_excellent" in defaults
    assert defaults["skip"] is False


def test_wellbeing_step_reads_existing_images_and_skip_keeps_them():
    """[REQ-HOM-119] Bestehende Bilder werden vorbelegt; skip ändert nichts."""
    options_flow = _make_flow(options={"wellbeing_images": {"good": "/local/good.jpg"}})

    result = _async_test(options_flow.async_step_wellbeing(None))
    assert _schema_defaults(result)["wellbeing_image_good"] == "/local/good.jpg"

    skipped = _async_test(options_flow.async_step_wellbeing({"skip": True}))
    assert skipped["type"] == "menu"
    assert options_flow._pending == {}


# --- Benachrichtigungen (notifications) ------------------------------------


def test_notifications_step_defaults_are_all_off():
    """[REQ-HOM-118] Alle Benachrichtigungen standardmäßig AUS."""
    options_flow = _make_flow()
    result = _async_test(options_flow.async_step_notifications(None))
    defaults = _schema_defaults(result)

    assert result["step_id"] == "notifications"
    assert defaults["reminders_enabled"] is False
    assert defaults["reminder_time"] == "20:00"
    assert defaults["reminder_days"] == ["0", "1", "2", "3", "4", "5", "6"]
    assert defaults["reminder_notify_service"] == ""
    assert defaults["reminder_quiet_start"] == ""
    assert defaults["reminder_quiet_end"] == ""
    assert defaults["reminder_drink_goal"] is True
    assert defaults["reminder_no_drink_hours"] == 3
    assert defaults["reminder_bp_days"] == 0
    assert defaults["reminder_wellbeing_days"] == 0
    assert defaults["weekly_report_enabled"] is False
    assert defaults["weekly_report_day"] == "0"
    assert defaults["weekly_report_time"] == "18:00"
    assert defaults["skip"] is False


def test_notifications_step_reads_existing_nested_options():
    """[REQ-HOM-118] Formular-Defaults kommen aus den genesteten Optionen."""
    options_flow = _make_flow(
        options={
            "reminders": {
                "enabled": True,
                "time": "07:30",
                "days": [0, 2],
                "notify_service": "notify.mobile_app_phone",
                "quiet_start": "22:00",
                "quiet_end": "06:30",
                "conditions": {"drink_goal": False, "no_drink_hours": 5, "bp_days": 14},
            },
            "weekly_report": {"enabled": True, "day": 4, "time": "09:15"},
        }
    )
    result = _async_test(options_flow.async_step_notifications(None))
    defaults = _schema_defaults(result)

    assert defaults["reminders_enabled"] is True
    assert defaults["reminder_time"] == "07:30"
    assert defaults["reminder_days"] == ["0", "2"]
    assert defaults["reminder_notify_service"] == "mobile_app_phone"
    assert defaults["reminder_quiet_start"] == "22:00"
    assert defaults["reminder_quiet_end"] == "06:30"
    assert defaults["reminder_drink_goal"] is False
    assert defaults["reminder_no_drink_hours"] == 5
    assert defaults["reminder_bp_days"] == 14
    assert defaults["weekly_report_enabled"] is True
    assert defaults["weekly_report_day"] == "4"
    assert defaults["weekly_report_time"] == "09:15"


def test_notifications_step_reads_pending_values_before_options():
    """[REQ-HOM-119] Vorgemerkte Benachrichtigungen gewinnen bei erneutem Öffnen."""
    options_flow = _make_flow(options={"reminders": {"enabled": False, "time": "20:00"}})
    options_flow._pending["reminders"] = {
        **options_flow.config_entry.options["reminders"],
        "enabled": True,
        "time": "06:15",
    }

    result = _async_test(options_flow.async_step_notifications(None))
    defaults = _schema_defaults(result)

    assert defaults["reminders_enabled"] is True
    assert defaults["reminder_time"] == "06:15"


def test_notifications_submit_saves_nested_structures_and_returns_to_menu():
    """[REQ-HOM-118/119] Flache Felder werden nicht persistiert; zurück ins Menü."""
    options_flow = _make_flow()
    options_flow.async_create_entry = MagicMock()

    result = _async_test(
        options_flow.async_step_notifications(
            {
                "reminders_enabled": True,
                "reminder_time": "20:30",
                "reminder_days": ["0", "3"],
                "reminder_notify_service": "notify.mobile_app_phone",
                "reminder_quiet_start": "22:00",
                "reminder_quiet_end": "07:00",
                "reminder_drink_goal": False,
                "reminder_no_drink_hours": 4,
                "reminder_bp_days": 7,
                "reminder_wellbeing_days": 3,
                "weekly_report_enabled": True,
                "weekly_report_day": "2",
                "weekly_report_time": "18:30",
                "weekly_report_notify_service": "mobile_app_phone",
            }
        )
    )

    assert result["type"] == "menu"
    options_flow.async_create_entry.assert_not_called()
    pending = options_flow._pending
    assert pending["reminders"] == {
        "enabled": True,
        "time": "20:30",
        "days": [0, 3],
        "notify_service": "mobile_app_phone",
        "quiet_start": "22:00",
        "quiet_end": "07:00",
        "conditions": {
            "drink_goal": False,
            "no_drink_hours": 4,
            "bp_days": 7,
            "wellbeing_days": 3,
        },
    }
    assert pending["weekly_report"] == {
        "enabled": True,
        "day": 2,
        "time": "18:30",
        "notify_service": "mobile_app_phone",
    }
    assert not any(key.startswith("reminder_") for key in pending)
    assert not any(key.startswith("weekly_report_") for key in pending)


def test_notifications_skip_returns_to_menu_without_changes():
    """[REQ-HOM-119] skip überspringt Benachrichtigungen ohne Pending-Änderung."""
    options_flow = _make_flow(options={"reminders": {"enabled": True, "time": "07:00"}})

    result = _async_test(options_flow.async_step_notifications({"skip": True}))

    assert result["type"] == "menu"
    assert options_flow._pending == {}


def test_notifications_submit_normalizes_invalid_values():
    """[REQ-HOM-118] Ungültige Zeiten/Wochentage/Zahlen → Defaults."""
    options_flow = _make_flow()

    _async_test(
        options_flow.async_step_notifications(
            {
                "reminders_enabled": True,
                "reminder_time": "25:99",
                "reminder_days": ["0", "x", "8"],
                "reminder_quiet_start": "abc",
                "reminder_quiet_end": "24:00",
                "reminder_no_drink_hours": 99,
                "reminder_bp_days": -3,
                "reminder_wellbeing_days": 999,
                "weekly_report_day": "9",
                "weekly_report_time": "later",
            }
        )
    )

    pending = options_flow._pending
    assert pending["reminders"]["time"] == "20:00"
    assert pending["reminders"]["days"] == [0]
    assert pending["reminders"]["quiet_start"] == ""
    assert pending["reminders"]["quiet_end"] == ""
    assert pending["reminders"]["conditions"]["no_drink_hours"] == 3
    assert pending["reminders"]["conditions"]["bp_days"] == 0
    assert pending["reminders"]["conditions"]["wellbeing_days"] == 0
    assert pending["weekly_report"]["day"] == 0
    assert pending["weekly_report"]["time"] == "18:00"


def test_notifications_schema_rejects_out_of_range_values():
    """[REQ-HOM-118] Die Formular-Validierung begrenzt Stunden/Tage."""
    import voluptuous as vol  # noqa: PLC0415

    options_flow = _make_flow()
    schema = _async_test(options_flow.async_step_notifications(None))["data_schema"]

    with pytest.raises(vol.Invalid):
        schema({"reminder_no_drink_hours": 25})
    with pytest.raises(vol.Invalid):
        schema({"reminder_bp_days": 366})
    with pytest.raises(vol.Invalid):
        schema({"reminder_wellbeing_days": -1})


# --- Defaults + Zusammenfassung -------------------------------------------


def test_defaults_step_sets_defaults_and_jumps_to_summary():
    """[REQ-HOM-119] Defaults übernehmen → Pending gefüllt → Zusammenfassung."""
    options_flow = _make_flow(options={"daily_goal_ml": 1800})

    result = _async_test(options_flow.async_step_defaults(None))

    assert result["type"] == "form"
    assert result["step_id"] == "summary"
    pending = options_flow._pending
    assert pending["quick_drinks"] == config_flow_module.DEFAULT_QUICK_DRINKS
    assert pending["drink_lexicon"] == config_flow_module.DRINK_LEXICON
    assert pending["wellbeing_images"] == {}
    assert pending["reminders"]["enabled"] is False
    assert pending["weekly_report"]["enabled"] is False
    # Nicht im Defaults-Set: bestehende Grundlagen bleiben unberührt.
    assert "daily_goal_ml" not in pending


def test_defaults_do_not_drop_previous_pending_changes():
    """[REQ-HOM-119] Defaults ergänzen `_pending`, statt es zu ersetzen."""
    options_flow = _make_flow()
    options_flow._pending["daily_goal_ml"] = 2300

    _async_test(options_flow.async_step_defaults(None))

    assert options_flow._pending["daily_goal_ml"] == 2300
    assert options_flow._pending["quick_drinks"] == config_flow_module.DEFAULT_QUICK_DRINKS


def test_summary_shows_changed_keys_and_values():
    """[REQ-HOM-119] Zusammenfassung beschreibt die geänderten Schlüssel/Werte."""
    options_flow = _make_flow()
    options_flow._pending = {
        "daily_goal_ml": 2250,
        "quick_drinks": [{"label": "Kaffee", "ml": 250}],
    }

    result = _async_test(options_flow.async_step_summary(None))
    changes = result["description_placeholders"]["changes"]

    assert result["type"] == "form"
    assert result["step_id"] == "summary"
    assert "daily_goal_ml: 2250" in changes
    assert '"label": "Kaffee"' in changes


def test_summary_without_changes_shows_placeholder():
    """[REQ-HOM-119] Ohne Pending-Änderungen bleibt die Zusammenfassung leer."""
    options_flow = _make_flow()

    result = _async_test(options_flow.async_step_summary(None))

    assert result["description_placeholders"]["changes"] == "—"


def test_summary_save_merges_pending_and_preserves_foreign_options():
    """[REQ-HOM-114/119] Speichern merged; nicht angezeigte Optionen bleiben."""
    options_flow = _make_flow(
        options={
            "wellbeing_confirm": True,
            "audit_limit": 500,
            "daily_goal_ml": 1800,
            "reminders": {"enabled": True, "time": "07:00"},
        }
    )
    options_flow.async_create_entry = MagicMock()
    options_flow._pending = {"daily_goal_ml": 2200, "areas": {"drink": False}}

    _async_test(options_flow.async_step_summary({}))

    options_flow.async_create_entry.assert_called_once()
    data = options_flow.async_create_entry.call_args[1]["data"]
    assert data["daily_goal_ml"] == 2200
    assert data["areas"] == {"drink": False}
    assert data["wellbeing_confirm"] is True
    assert data["audit_limit"] == 500
    assert data["reminders"] == {"enabled": True, "time": "07:00"}


def test_summary_save_without_changes_keeps_options_identical():
    """[REQ-HOM-119] „Speichern" ohne Änderung verändert die Options nicht."""
    original = {"daily_goal_ml": 2000, "wellbeing_confirm": False}
    options_flow = _make_flow(options=dict(original))
    options_flow.async_create_entry = MagicMock()

    _async_test(options_flow.async_step_summary({}))

    data = options_flow.async_create_entry.call_args[1]["data"]
    assert data == original


def test_cancel_without_save_does_not_create_entry():
    """[REQ-HOM-119] Ohne Speichern (Flow-Abbruch) wird kein Entry erzeugt."""
    options_flow = _make_flow()
    options_flow.async_create_entry = MagicMock()

    _async_test(options_flow.async_step_basics({"daily_goal_ml": 2200}))
    _async_test(options_flow.async_step_drinks(_quick_input()))

    options_flow.async_create_entry.assert_not_called()
    assert options_flow.config_entry.options == {}


# --- Vollständiger Wizard-Durchlauf ---------------------------------------


def test_full_menu_flow_creates_merged_entry():
    """[REQ-HOM-101/109/114/118/119] Alle Abschnitte → Zusammenfassung → Entry."""
    options_flow = _make_flow(options={"wellbeing_confirm": True, "daily_goal_ml": 1800})
    options_flow.async_create_entry = MagicMock()

    menu = _async_test(options_flow.async_step_init(None))
    assert menu["type"] == "menu"

    basics = _async_test(
        options_flow.async_step_basics(
            {
                "daily_goal_ml": 2250,
                "set_lifetime_ml": 0,
                "person_display": "Max",
                "daily_reset_hour": 4,
                "retention_months": 6,
                "enable_sidebar_panel": True,
                "area_drink": True,
                "area_bp": False,
                "area_wellbeing": True,
            }
        )
    )
    assert basics["type"] == "menu"

    drinks = _async_test(
        options_flow.async_step_drinks({**_quick_input(250), "drink_lexicon": "kaffee=Kaffee,250"})
    )
    assert drinks["type"] == "menu"

    wellbeing = _async_test(
        options_flow.async_step_wellbeing({"wellbeing_image_good": "/local/good.jpg"})
    )
    assert wellbeing["type"] == "menu"

    notifications = _async_test(
        options_flow.async_step_notifications(
            {"reminders_enabled": False, "weekly_report_enabled": False}
        )
    )
    assert notifications["type"] == "menu"

    summary = _async_test(options_flow.async_step_summary(None))
    assert summary["type"] == "form"
    assert summary["step_id"] == "summary"

    _async_test(options_flow.async_step_summary({}))

    options_flow.async_create_entry.assert_called_once()
    data = options_flow.async_create_entry.call_args[1]["data"]
    assert data["daily_goal_ml"] == 2250
    assert data["daily_reset_hour"] == 4
    assert data["retention_months"] == 6
    assert data["enable_sidebar_panel"] is True
    assert data["areas"] == {"drink": True, "bp": False, "wellbeing": True}
    assert len(data["quick_drinks"]) == 4
    assert data["quick_drinks"][0]["label"] == "Drink 0"
    assert data["drink_lexicon"] == {"kaffee": ("Kaffee", 250)}
    assert data["wellbeing_images"] == {"good": "/local/good.jpg"}
    assert data["reminders"]["enabled"] is False
    assert data["weekly_report"]["enabled"] is False
    # Fremde Option überlebt den gesamten Wizard.
    assert data["wellbeing_confirm"] is True
    assert not any(key.startswith("area_") for key in data)
    assert "skip" not in data


def test_full_flow_with_skipped_sections_keeps_existing_options():
    """[REQ-HOM-119] Nur Grundlagen ändern, alle anderen Abschnitte überspringen."""
    original = {
        "daily_goal_ml": 1800,
        "quick_drinks": [{"key": "slot_0", "label": "Alt", "ml": 100}],
        "drink_lexicon": {"alt": ("Alt", 100)},
        "wellbeing_images": {"good": "/local/alt.jpg"},
        "reminders": {"enabled": True, "time": "06:00"},
        "weekly_report": {"enabled": True, "day": 6, "time": "20:00"},
        "wellbeing_confirm": True,
        "audit_limit": 100,
    }
    options_flow = _make_flow(options=original)
    options_flow.async_create_entry = MagicMock()

    for step in (
        options_flow.async_step_drinks({"skip": True}),
        options_flow.async_step_wellbeing({"skip": True}),
        options_flow.async_step_notifications({"skip": True}),
    ):
        assert _async_test(step)["type"] == "menu"

    _async_test(options_flow.async_step_basics({"daily_goal_ml": 2000}))
    _async_test(options_flow.async_step_summary({}))

    data = options_flow.async_create_entry.call_args[1]["data"]
    assert data["daily_goal_ml"] == 2000
    for key, value in original.items():
        if key != "daily_goal_ml":
            assert data[key] == value


def test_defaults_flow_overwrites_default_keys_but_keeps_foreign_options():
    """[REQ-HOM-119] Defaults ersetzen nur ihre Schlüssel; Fremdoptionen bleiben."""
    options_flow = _make_flow(
        options={
            "daily_goal_ml": 1900,
            "wellbeing_confirm": True,
            "audit_limit": 0,
            "quick_drinks": [{"key": "slot_0", "label": "Alt", "ml": 100}],
            "reminders": {"enabled": True, "time": "06:00"},
        }
    )
    options_flow.async_create_entry = MagicMock()

    _async_test(options_flow.async_step_defaults(None))
    _async_test(options_flow.async_step_summary({}))

    data = options_flow.async_create_entry.call_args[1]["data"]
    assert data["quick_drinks"] == config_flow_module.DEFAULT_QUICK_DRINKS
    assert data["drink_lexicon"] == config_flow_module.DRINK_LEXICON
    assert data["reminders"]["enabled"] is False
    assert data["daily_goal_ml"] == 1900
    assert data["wellbeing_confirm"] is True
    assert data["audit_limit"] == 0


# --- Modul-Helfer ----------------------------------------------------------


def test_summary_text_formats_nested_values():
    """[REQ-HOM-119] Verschachtelte Werte werden deterministisch serialisiert."""
    text = config_flow_module.summary_text({"b": {"z": 1, "a": 2}, "a": True})

    assert text.splitlines()[0] == "• a: True"
    assert text.splitlines()[1] == '• b: {"a": 2, "z": 1}'


def test_drinks_schema_contains_skip_and_lexicon():
    """[REQ-HOM-119] Kombiniertes Schema: 12 Quick-Felder + Lexikon + skip."""
    schema = config_flow_module.drinks_schema(
        config_flow_module._default_quick_drinks(), "kaffee=Kaffee,250"
    )
    keys = {str(key) for key in schema.schema}

    assert "quick_3_icon" in keys
    assert "drink_lexicon" in keys
    assert "skip" in keys

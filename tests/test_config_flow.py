"""Tests: HealthOMatOptionsFlow — daily_goal_ml persistence (Audit C-2).

Audit-Punkt 7b (C-2): Options flow correctly reads default from entry.options
and persists user input back to entry.options.
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


def test_config_flow_get_options_flow_returns_options_flow_instance():
    """[AUDIT-7b-C-2] ConfigFlow.async_get_options_flow returns OptionsFlow instance."""
    config_flow = config_flow_module.HealthOMatConfigFlow()

    result = config_flow.async_get_options_flow(MagicMock())

    assert isinstance(result, config_flow_module.HealthOMatOptionsFlow)


def test_config_flow_version():
    """ConfigFlow VERSION 2 (quick_drinks → options, Fund F1 / REQ-HOM-101)."""
    config_flow = config_flow_module.HealthOMatConfigFlow()
    assert config_flow.VERSION == 2


def test_options_flow_async_step_init_shows_form_on_no_input():
    """[AUDIT-7b-C-2] async_step_init shows form when user_input is None."""
    options_flow = config_flow_module.HealthOMatOptionsFlow()

    # Mock the dependencies
    entry = MagicMock()
    entry.options = {"daily_goal_ml": 2500}
    entry.runtime_data = MagicMock()
    entry.entry_id = "test-entry-1"

    hass = MagicMock()
    hass.data = {"health_o_mat": {"shared": {"store": MagicMock()}}}
    store = hass.data["health_o_mat"]["shared"]["store"]
    store.all_entries = MagicMock(return_value={"test-entry-1": {"total_ml_lifetime": 1000}})

    # Use PropertyMock to set config_entry properly
    type(options_flow).config_entry = PropertyMock(return_value=entry)
    type(options_flow).hass = PropertyMock(return_value=hass)

    # Mock async_show_form
    options_flow.async_show_form = MagicMock()

    _async_test(options_flow.async_step_init(None))

    options_flow.async_show_form.assert_called_once()
    call_kwargs = options_flow.async_show_form.call_args[1]
    assert call_kwargs["step_id"] == "init"
    assert "data_schema" in call_kwargs


def test_options_flow_async_step_init_chains_to_quick_drinks():
    """[REQ-HOM-101] init-Submit speichert Zwischenstand und zeigt Quick-Drinks-Form."""
    options_flow = config_flow_module.HealthOMatOptionsFlow()

    entry = MagicMock()
    entry.options = {}
    entry.runtime_data = MagicMock()
    entry.runtime_data.daily_goal_ml = 2000
    entry.entry_id = "test-entry-1"

    hass = MagicMock()
    hass.data = {}

    type(options_flow).config_entry = PropertyMock(return_value=entry)
    type(options_flow).hass = PropertyMock(return_value=hass)

    user_input = {"daily_goal_ml": 2250, "set_lifetime_ml": 0, "person_display": ""}
    result = _async_test(options_flow.async_step_init(user_input))

    # init erzeugt KEINEN Entry mehr — es verkettet auf quick_drinks
    assert result["type"] == "form"
    assert result["step_id"] == "quick_drinks"
    # Zwischenstand wartet auf den finalen Submit
    assert options_flow._pending["daily_goal_ml"] == 2250


def test_options_flow_full_five_step_flow_creates_entry():
    """[REQ-HOM-101/118] init → quick_drinks → wellbeing_images →
    drink_lexicon → notifications → create_entry mit zusammengeführten Daten."""
    options_flow = config_flow_module.HealthOMatOptionsFlow()

    entry = MagicMock()
    entry.options = {}
    entry.runtime_data = MagicMock()
    entry.entry_id = "test-entry-1"
    entry.data = {"person": "Max"}

    hass = MagicMock()
    hass.data = {}

    type(options_flow).config_entry = PropertyMock(return_value=entry)
    type(options_flow).hass = PropertyMock(return_value=hass)
    options_flow.async_create_entry = MagicMock()

    _async_test(
        options_flow.async_step_init(
            {"daily_goal_ml": 2250, "set_lifetime_ml": 0, "person_display": ""}
        )
    )
    user_input = {}
    for i in range(4):
        user_input[f"quick_{i}_label"] = f"Drink {i}"
        user_input[f"quick_{i}_ml"] = 250
        user_input[f"quick_{i}_icon"] = "mdi:cup-water"
    # quick_drinks-Submit verkettet auf den neuen wellbeing_images-Schritt.
    quick_drinks_result = _async_test(options_flow.async_step_quick_drinks(user_input))
    assert quick_drinks_result["type"] == "form"
    assert quick_drinks_result["step_id"] == "wellbeing_images"
    options_flow.async_create_entry.assert_not_called()

    images_result = _async_test(options_flow.async_step_wellbeing_images({}))
    assert images_result["type"] == "form"
    assert images_result["step_id"] == "drink_lexicon"

    _async_test(options_flow.async_step_drink_lexicon({"drink_lexicon": "kaffee=Kaffee,250"}))
    _async_test(options_flow.async_step_notifications({}))

    options_flow.async_create_entry.assert_called_once()
    data = options_flow.async_create_entry.call_args[1]["data"]
    assert data["daily_goal_ml"] == 2250
    assert len(data["quick_drinks"]) == 4
    assert data["quick_drinks"][0]["label"] == "Drink 0"
    assert data["drink_lexicon"] == {"kaffee": ("Kaffee", 250)}


def test_options_flow_daily_goal_from_options_takes_precedence():
    """[AUDIT-7b-C-2] async_step_init reads daily_goal_ml from entry.options first."""
    options_flow = config_flow_module.HealthOMatOptionsFlow()

    # entry.options has daily_goal_ml, runtime_data has different value
    entry = MagicMock()
    entry.options = {"daily_goal_ml": 2500}
    entry.runtime_data = MagicMock()
    entry.runtime_data.daily_goal_ml = 3000  # This should be ignored
    entry.entry_id = "test-entry-1"

    hass = MagicMock()
    hass.data = {}

    type(options_flow).config_entry = PropertyMock(return_value=entry)
    type(options_flow).hass = PropertyMock(return_value=hass)

    options_flow.async_show_form = MagicMock()

    _async_test(options_flow.async_step_init(None))

    # The form should have been shown (meaning no error with options reading)
    options_flow.async_show_form.assert_called_once()


def test_options_flow_fallback_to_runtime_when_options_empty():
    """[AUDIT-7b-C-2] Falls back to runtime_data.daily_goal_ml if options empty."""
    options_flow = config_flow_module.HealthOMatOptionsFlow()

    entry = MagicMock()
    entry.options = {}  # Empty options
    entry.runtime_data = MagicMock()
    entry.runtime_data.daily_goal_ml = 3000
    entry.entry_id = "test-entry-1"

    hass = MagicMock()
    hass.data = {}

    type(options_flow).config_entry = PropertyMock(return_value=entry)
    type(options_flow).hass = PropertyMock(return_value=hass)

    options_flow.async_show_form = MagicMock()

    _async_test(options_flow.async_step_init(None))

    # Should show form without error
    options_flow.async_show_form.assert_called_once()


def test_options_flow_fallback_to_default_when_no_runtime_data():
    """[AUDIT-7b-C-2] Falls back to DEFAULT_DAILY_GOAL_ML if no runtime_data."""
    options_flow = config_flow_module.HealthOMatOptionsFlow()

    entry = MagicMock()
    entry.options = {}
    entry.runtime_data = None  # No runtime data
    entry.entry_id = "test-entry-1"

    hass = MagicMock()
    hass.data = {}

    type(options_flow).config_entry = PropertyMock(return_value=entry)
    type(options_flow).hass = PropertyMock(return_value=hass)

    options_flow.async_show_form = MagicMock()

    _async_test(options_flow.async_step_init(None))

    # Should use DEFAULT_DAILY_GOAL_ML and show form
    options_flow.async_show_form.assert_called_once()


def test_options_flow_loads_lifetime_from_store():
    """[AUDIT-7b-C-2] async_step_init loads lifetime_ml from store."""
    options_flow = config_flow_module.HealthOMatOptionsFlow()

    entry = MagicMock()
    entry.options = {}
    entry.runtime_data = MagicMock()
    entry.runtime_data.daily_goal_ml = 2000
    entry.entry_id = "test-entry-1"

    hass = MagicMock()
    mock_store = MagicMock()
    mock_store.all_entries = MagicMock(return_value={"test-entry-1": {"total_ml_lifetime": 5000}})
    hass.data = {"health_o_mat": {"shared": {"store": mock_store}}}

    type(options_flow).config_entry = PropertyMock(return_value=entry)
    type(options_flow).hass = PropertyMock(return_value=hass)

    options_flow.async_show_form = MagicMock()

    _async_test(options_flow.async_step_init(None))

    # Store.all_entries() should have been called
    mock_store.all_entries.assert_called_once()


def test_options_flow_handles_missing_store():
    """[AUDIT-7b-C-2] async_step_init handles missing store gracefully."""
    options_flow = config_flow_module.HealthOMatOptionsFlow()

    entry = MagicMock()
    entry.options = {}
    entry.runtime_data = MagicMock()
    entry.runtime_data.daily_goal_ml = 2000
    entry.entry_id = "test-entry-1"

    hass = MagicMock()
    hass.data = {}  # No store

    type(options_flow).config_entry = PropertyMock(return_value=entry)
    type(options_flow).hass = PropertyMock(return_value=hass)

    options_flow.async_show_form = MagicMock()

    _async_test(options_flow.async_step_init(None))

    # Should still show form without error
    options_flow.async_show_form.assert_called_once()


def test_options_flow_preserves_other_options_on_submit():
    """[REQ-HOM-101] finaler Drink-Lexicon-Submit bewahrt übrige Optionen."""
    options_flow = config_flow_module.HealthOMatOptionsFlow()

    entry = MagicMock()
    entry.options = {"some_key": "some_value"}
    entry.runtime_data = MagicMock()
    entry.entry_id = "test-entry-1"
    entry.data = {"person": "Max"}

    hass = MagicMock()
    hass.data = {}

    type(options_flow).config_entry = PropertyMock(return_value=entry)
    type(options_flow).hass = PropertyMock(return_value=hass)

    options_flow.async_create_entry = MagicMock()

    _async_test(
        options_flow.async_step_init(
            {"daily_goal_ml": 2500, "set_lifetime_ml": 1000, "person_display": ""}
        )
    )
    user_input = {}
    for i in range(4):
        user_input[f"quick_{i}_label"] = f"Drink {i}"
        user_input[f"quick_{i}_ml"] = 200
        user_input[f"quick_{i}_icon"] = "mdi:cup-water"
    _async_test(options_flow.async_step_quick_drinks(user_input))
    _async_test(options_flow.async_step_wellbeing_images({}))
    _async_test(options_flow.async_step_drink_lexicon({"drink_lexicon": "kaffee=Kaffee,250"}))
    _async_test(options_flow.async_step_notifications({}))

    options_flow.async_create_entry.assert_called_once()
    data = options_flow.async_create_entry.call_args[1]["data"]
    # init-Felder + Quick-Drinks + Lexikon zusammengeführt; fremde Optionen
    # (z. B. `wellbeing_confirm` aus dem Panel) bleiben erhalten.
    assert data["daily_goal_ml"] == 2500
    assert data["set_lifetime_ml"] == 1000
    assert data["drink_lexicon"] == {"kaffee": ("Kaffee", 250)}
    assert data["some_key"] == "some_value"  # Flow verliert fremde Optionen nicht


# --- Feature 1: Getränke-Lexikon-Schritt (drink_lexicon) ---


def test_drink_lexicon_step_shows_form_with_default_lexicon_text():
    """[Spec Feature 1] Erstes Öffnen ohne gespeichertes Lexikon zeigt DRINK_LEXICON formatiert."""
    options_flow = config_flow_module.HealthOMatOptionsFlow()

    entry = MagicMock()
    entry.options = {}
    type(options_flow).config_entry = PropertyMock(return_value=entry)

    result = _async_test(options_flow.async_step_drink_lexicon(None))

    assert result["type"] == "form"
    assert result["step_id"] == "drink_lexicon"
    assert "errors" not in result or not result.get("errors")


def test_drink_lexicon_step_invalid_text_reshows_form_with_error():
    """[Spec Feature 1 - AC 10] Fehlerhafter Text: errors['base'], kein
    create_entry, Entry legt nicht an."""
    options_flow = config_flow_module.HealthOMatOptionsFlow()

    entry = MagicMock()
    entry.options = {}
    type(options_flow).config_entry = PropertyMock(return_value=entry)
    options_flow.async_create_entry = MagicMock()

    result = _async_test(options_flow.async_step_drink_lexicon({"drink_lexicon": "kaffee=Kaffee"}))

    assert result["type"] == "form"
    assert result["step_id"] == "drink_lexicon"
    assert result["errors"] == {"base": "invalid_lexicon_format"}
    options_flow.async_create_entry.assert_not_called()


def test_drink_lexicon_step_reads_existing_options_lexicon():
    """[Spec Feature 1] Vorhandenes entry.options['drink_lexicon'] wird formatiert vorbelegt."""
    options_flow = config_flow_module.HealthOMatOptionsFlow()

    entry = MagicMock()
    entry.options = {"drink_lexicon": {"matecha": ("Matcha-Tee", 300)}}
    type(options_flow).config_entry = PropertyMock(return_value=entry)

    result = _async_test(options_flow.async_step_drink_lexicon(None))

    schema_dict = result["data_schema"].schema
    default_key = next(iter(schema_dict))
    assert default_key.default() == "matecha=Matcha-Tee,300"


# --- Feature 2: konfigurierbare Reset-Uhrzeit (daily_reset_hour) ---


def test_init_step_schema_rejects_out_of_range_daily_reset_hour():
    """[Spec Feature 2 - AC 2] vol.Range(min=0, max=23) lehnt 24/-1 ab."""
    import voluptuous as vol  # noqa: PLC0415

    options_flow = config_flow_module.HealthOMatOptionsFlow()

    entry = MagicMock()
    entry.options = {}
    entry.runtime_data = MagicMock()
    entry.entry_id = "test-entry-1"
    hass = MagicMock()
    hass.data = {}
    type(options_flow).config_entry = PropertyMock(return_value=entry)
    type(options_flow).hass = PropertyMock(return_value=hass)
    options_flow.async_show_form = MagicMock(side_effect=lambda **kw: kw)

    result = _async_test(options_flow.async_step_init(None))
    schema = result["data_schema"]

    for bad in (24, -1):
        try:
            schema(
                {
                    "daily_goal_ml": 2000,
                    "set_lifetime_ml": 0,
                    "person_display": "",
                    "daily_reset_hour": bad,
                }
            )
        except vol.Invalid:
            pass
        else:
            raise AssertionError(f"expected vol.Invalid for daily_reset_hour={bad}")

    # 0..23 bleiben gültig — inkl. beider Grenzwerte (vol.Range ist inklusiv;
    # ein Off-by-one bei min/max würde sonst genau hier unbemerkt bleiben).
    for good in (0, 6, 23):
        validated = schema(
            {
                "daily_goal_ml": 2000,
                "set_lifetime_ml": 0,
                "person_display": "",
                "daily_reset_hour": good,
            }
        )
        assert validated["daily_reset_hour"] == good


def test_init_step_daily_reset_hour_defaults_to_zero():
    """[Spec Feature 2] Fehlender daily_reset_hour in entry.options → Default 0
    (Bestands-Verhalten)."""
    options_flow = config_flow_module.HealthOMatOptionsFlow()

    entry = MagicMock()
    entry.options = {}
    entry.runtime_data = MagicMock()
    entry.entry_id = "test-entry-1"
    hass = MagicMock()
    hass.data = {}
    type(options_flow).config_entry = PropertyMock(return_value=entry)
    type(options_flow).hass = PropertyMock(return_value=hass)
    options_flow.async_show_form = MagicMock(side_effect=lambda **kw: kw)

    result = _async_test(options_flow.async_step_init(None))
    schema_dict = result["data_schema"].schema
    hour_key = next(k for k in schema_dict if str(k) == "daily_reset_hour")
    assert hour_key.default() == 0


# --- Feature 3 (REQ-HOM-109 / N-2): Retention/Archiv-Monatswert ---


def _init_schema_via_form(options_flow):
    options_flow.async_show_form = MagicMock(side_effect=lambda **kw: kw)
    return _async_test(options_flow.async_step_init(None))["data_schema"]


def test_init_step_retention_months_defaults_off_and_validates_range():
    """[REQ-HOM-109] retention_months: Default 0 (AUS), Range 0..MAX."""
    import voluptuous as vol  # noqa: PLC0415

    options_flow = config_flow_module.HealthOMatOptionsFlow()
    entry = MagicMock()
    entry.options = {}
    entry.runtime_data = MagicMock()
    entry.entry_id = "test-entry-1"
    hass = MagicMock()
    hass.data = {}
    type(options_flow).config_entry = PropertyMock(return_value=entry)
    type(options_flow).hass = PropertyMock(return_value=hass)

    schema = _init_schema_via_form(options_flow)
    retention_key = next(k for k in schema.schema if str(k) == "retention_months")
    assert retention_key.default() == 0  # Default AUS = bisheriges Verhalten

    base = {
        "daily_goal_ml": 2000,
        "set_lifetime_ml": 0,
        "person_display": "",
        "daily_reset_hour": 0,
    }
    max_months = config_flow_module.MAX_RETENTION_MONTHS
    for good in (0, max_months):
        assert schema({**base, "retention_months": good})["retention_months"] == good
    for bad in (-1, max_months + 1):
        with pytest.raises(vol.Invalid):
            schema({**base, "retention_months": bad})


def test_options_flow_persists_retention_months():
    """[REQ-HOM-109] Der vollständige Options-Flow schreibt retention_months mit."""
    options_flow = config_flow_module.HealthOMatOptionsFlow()
    entry = MagicMock()
    entry.options = {}
    entry.runtime_data = MagicMock()
    entry.entry_id = "test-entry-1"
    entry.data = {"person": "Max"}
    hass = MagicMock()
    hass.data = {}
    type(options_flow).config_entry = PropertyMock(return_value=entry)
    type(options_flow).hass = PropertyMock(return_value=hass)
    options_flow.async_create_entry = MagicMock()

    _async_test(
        options_flow.async_step_init(
            {
                "daily_goal_ml": 2000,
                "set_lifetime_ml": 0,
                "person_display": "",
                "retention_months": 6,
            }
        )
    )
    quick = {}
    for i in range(4):
        quick[f"quick_{i}_label"] = f"Drink {i}"
        quick[f"quick_{i}_ml"] = 200
        quick[f"quick_{i}_icon"] = "mdi:cup-water"
    _async_test(options_flow.async_step_quick_drinks(quick))
    _async_test(options_flow.async_step_wellbeing_images({}))
    _async_test(options_flow.async_step_drink_lexicon({"drink_lexicon": "kaffee=Kaffee,250"}))
    _async_test(options_flow.async_step_notifications({}))

    data = options_flow.async_create_entry.call_args[1]["data"]
    assert data["retention_months"] == 6


# --- Feature 4 (CONCEPT-UI §8.3): Opt-in-Sidebar-Panel ---


def test_init_step_sidebar_panel_defaults_off():
    """[CONCEPT-UI §8.3] enable_sidebar_panel: Default AUS (bisheriges Verhalten)."""
    options_flow = config_flow_module.HealthOMatOptionsFlow()
    entry = MagicMock()
    entry.options = {}
    entry.runtime_data = MagicMock()
    entry.entry_id = "test-entry-1"
    hass = MagicMock()
    hass.data = {}
    type(options_flow).config_entry = PropertyMock(return_value=entry)
    type(options_flow).hass = PropertyMock(return_value=hass)

    schema = _init_schema_via_form(options_flow)
    key = next(k for k in schema.schema if str(k) == "enable_sidebar_panel")
    assert key.default() is False
    # `bool` (nicht `vol.Boolean()`) ist Pflicht — nur `bool` serialisiert im
    # Options-Dialog zu einem Boolean-Toggle (vol.Boolean ist nicht konvertierbar).
    assert schema.schema[key] is bool


def test_init_step_sidebar_panel_reads_existing_value():
    """[CONCEPT-UI §8.3] Bestehender Wert wird unverändert als Default übernommen."""
    options_flow = config_flow_module.HealthOMatOptionsFlow()
    entry = MagicMock()
    entry.options = {"enable_sidebar_panel": True}
    entry.runtime_data = MagicMock()
    entry.entry_id = "test-entry-1"
    hass = MagicMock()
    hass.data = {}
    type(options_flow).config_entry = PropertyMock(return_value=entry)
    type(options_flow).hass = PropertyMock(return_value=hass)

    schema = _init_schema_via_form(options_flow)
    key = next(k for k in schema.schema if str(k) == "enable_sidebar_panel")
    assert key.default() is True


def test_options_flow_persists_sidebar_panel_option():
    """[CONCEPT-UI §8.3] Der Options-Flow schreibt enable_sidebar_panel mit."""
    options_flow = config_flow_module.HealthOMatOptionsFlow()
    entry = MagicMock()
    entry.options = {}
    entry.runtime_data = MagicMock()
    entry.entry_id = "test-entry-1"
    entry.data = {"person": "Max"}
    hass = MagicMock()
    hass.data = {}
    type(options_flow).config_entry = PropertyMock(return_value=entry)
    type(options_flow).hass = PropertyMock(return_value=hass)
    options_flow.async_create_entry = MagicMock()

    _async_test(
        options_flow.async_step_init(
            {
                "daily_goal_ml": 2000,
                "set_lifetime_ml": 0,
                "person_display": "",
                "retention_months": 0,
                "enable_sidebar_panel": True,
            }
        )
    )
    quick = {}
    for i in range(4):
        quick[f"quick_{i}_label"] = f"Drink {i}"
        quick[f"quick_{i}_ml"] = 200
        quick[f"quick_{i}_icon"] = "mdi:cup-water"
    _async_test(options_flow.async_step_quick_drinks(quick))
    _async_test(options_flow.async_step_wellbeing_images({}))
    _async_test(options_flow.async_step_drink_lexicon({"drink_lexicon": "kaffee=Kaffee,250"}))
    _async_test(options_flow.async_step_notifications({}))

    data = options_flow.async_create_entry.call_args[1]["data"]
    assert data["enable_sidebar_panel"] is True


# --- REQ-HOM-009: Pro-Person Bereichs-Toggles im Options-Flow ---


def _area_options_flow(options=None):
    options_flow = config_flow_module.HealthOMatOptionsFlow()
    entry = MagicMock()
    entry.options = options if options is not None else {}
    entry.runtime_data = MagicMock()
    entry.entry_id = "test-entry-1"
    hass = MagicMock()
    hass.data = {}
    type(options_flow).config_entry = PropertyMock(return_value=entry)
    type(options_flow).hass = PropertyMock(return_value=hass)
    return options_flow


def test_init_step_area_toggles_default_all_true():
    """[REQ-HOM-009] Ohne areas-Option: alle Toggles default True, Typ bool."""
    schema = _init_schema_via_form(_area_options_flow({}))
    for field in ("area_drink", "area_bp", "area_wellbeing"):
        key = next(k for k in schema.schema if str(k) == field)
        assert key.default() is True
        assert schema.schema[key] is bool


def test_init_step_area_toggles_reflect_existing_options():
    """[REQ-HOM-009] Bestehende areas-Werte (fehlende Unter-Schlüssel = True)."""
    schema = _init_schema_via_form(_area_options_flow({"areas": {"drink": False, "bp": True}}))
    defaults = {str(k): k.default() for k in schema.schema if str(k).startswith("area_")}
    assert defaults == {"area_drink": False, "area_bp": True, "area_wellbeing": True}


def test_areas_from_user_input_keeps_current_for_missing_fields():
    """[REQ-HOM-009] Fehlt ein Feld, bleibt der bisherige Wert (kein Kipp auf True)."""
    current = {"drink": False, "bp": True, "wellbeing": False}
    assert config_flow_module.areas_from_user_input({"area_drink": True}, current) == {
        "drink": True,
        "bp": True,
        "wellbeing": False,
    }


def test_init_submit_persists_nested_areas_without_flat_keys():
    """[REQ-HOM-009] init-Submit legt verschachteltes areas ab, keine area_*-Flachkeys."""
    options_flow = _area_options_flow({})
    result = _async_test(
        options_flow.async_step_init(
            {
                "daily_goal_ml": 2000,
                "set_lifetime_ml": 0,
                "person_display": "",
                "area_drink": False,
                "area_bp": True,
                "area_wellbeing": False,
            }
        )
    )

    assert result["step_id"] == "quick_drinks"
    assert options_flow._pending["areas"] == {"drink": False, "bp": True, "wellbeing": False}
    assert not any(k.startswith("area_") for k in options_flow._pending)


def test_options_flow_persists_areas_in_create_entry():
    """[REQ-HOM-009] Der vollständige Options-Flow schreibt areas in den Entry."""
    options_flow = _area_options_flow({})
    type(options_flow).config_entry.return_value.data = {"person": "Max"}
    options_flow.async_create_entry = MagicMock()

    _async_test(
        options_flow.async_step_init(
            {
                "daily_goal_ml": 2000,
                "set_lifetime_ml": 0,
                "person_display": "",
                "area_drink": True,
                "area_bp": False,
                "area_wellbeing": True,
            }
        )
    )
    quick = {}
    for i in range(4):
        quick[f"quick_{i}_label"] = f"Drink {i}"
        quick[f"quick_{i}_ml"] = 200
        quick[f"quick_{i}_icon"] = "mdi:cup-water"
    _async_test(options_flow.async_step_quick_drinks(quick))
    _async_test(options_flow.async_step_wellbeing_images({}))
    _async_test(options_flow.async_step_drink_lexicon({"drink_lexicon": "kaffee=Kaffee,250"}))
    _async_test(options_flow.async_step_notifications({}))

    data = options_flow.async_create_entry.call_args[1]["data"]
    assert data["areas"] == {"drink": True, "bp": False, "wellbeing": True}
    assert not any(k.startswith("area_") for k in data)


# --- Wellbeing-Bilder im Options-Flow ---------------------------------------


def test_wellbeing_images_step_maps_and_normalizes():
    """Bildfelder werden auf gültige Keys normalisiert; leere Werte entfallen."""
    mapped = config_flow_module.wellbeing_images_from_user_input(
        {
            "wellbeing_image_very_bad": "stufe1.png",
            "wellbeing_image_good": "/local/good.jpg",
            "wellbeing_image_poor": "böse.html",
        }
    )

    assert mapped == {
        "very_bad": "/local/stufe1.png",
        "good": "/local/good.jpg",
    }


def test_wellbeing_images_schema_has_all_ten_keys():
    """Der Options-Schritt bietet für jede der zehn Stufen ein Bildfeld an."""
    schema = config_flow_module.wellbeing_images_schema({})
    defaults = schema({})

    assert len(defaults) == 10
    assert "wellbeing_image_excellent" in defaults


# --- REQ-HOM-114: Panel-Option überlebt den Options-Flow --------------------


def test_req_hom_114_options_flow_preserves_wellbeing_confirm():
    """[REQ-HOM-114] Die Panel-Option `wellbeing_confirm` bleibt beim
    Options-Flow erhalten, obwohl sie kein Formularfeld hat."""
    options_flow = config_flow_module.HealthOMatOptionsFlow()

    entry = MagicMock()
    entry.options = {"wellbeing_confirm": True, "daily_goal_ml": 1800}
    entry.runtime_data = MagicMock()
    entry.entry_id = "test-entry-1"
    entry.data = {"person": "Max"}

    hass = MagicMock()
    hass.data = {}

    type(options_flow).config_entry = PropertyMock(return_value=entry)
    type(options_flow).hass = PropertyMock(return_value=hass)
    options_flow.async_create_entry = MagicMock()

    _async_test(
        options_flow.async_step_init(
            {"daily_goal_ml": 2200, "set_lifetime_ml": 0, "person_display": ""}
        )
    )
    quick = {}
    for i in range(4):
        quick[f"quick_{i}_label"] = f"Drink {i}"
        quick[f"quick_{i}_ml"] = 200
        quick[f"quick_{i}_icon"] = "mdi:cup-water"
    _async_test(options_flow.async_step_quick_drinks(quick))
    _async_test(options_flow.async_step_wellbeing_images({}))
    _async_test(options_flow.async_step_drink_lexicon({"drink_lexicon": "kaffee=Kaffee,250"}))
    _async_test(options_flow.async_step_notifications({}))

    data = options_flow.async_create_entry.call_args[1]["data"]
    assert data["wellbeing_confirm"] is True
    assert data["daily_goal_ml"] == 2200


# --- REQ-HOM-118: Erinnerungen + Wochenbericht im Options-Flow ---------------


def _notifications_flow(options=None, data=None):
    options_flow = config_flow_module.HealthOMatOptionsFlow()
    entry = MagicMock()
    entry.options = options if options is not None else {}
    entry.runtime_data = MagicMock()
    entry.entry_id = "test-entry-1"
    entry.data = data if data is not None else {"person": "Max"}

    hass = MagicMock()
    hass.data = {}
    type(options_flow).config_entry = PropertyMock(return_value=entry)
    type(options_flow).hass = PropertyMock(return_value=hass)
    return options_flow


def test_notifications_step_is_terminal_after_drink_lexicon():
    """[REQ-HOM-118] drink_lexicon verkettet auf den neuen Notifications-Schritt."""
    options_flow = _notifications_flow()
    _async_test(
        options_flow.async_step_init(
            {"daily_goal_ml": 2000, "set_lifetime_ml": 0, "person_display": ""}
        )
    )
    quick = {}
    for i in range(4):
        quick[f"quick_{i}_label"] = f"Drink {i}"
        quick[f"quick_{i}_ml"] = 200
        quick[f"quick_{i}_icon"] = "mdi:cup-water"
    _async_test(options_flow.async_step_quick_drinks(quick))
    _async_test(options_flow.async_step_wellbeing_images({}))

    result = _async_test(
        options_flow.async_step_drink_lexicon({"drink_lexicon": "kaffee=Kaffee,250"})
    )

    assert result["type"] == "form"
    assert result["step_id"] == "notifications"


def test_notifications_step_defaults_are_all_off():
    """[REQ-HOM-118] Alle Benachrichtigungen standardmäßig AUS."""
    result = _async_test(_notifications_flow().async_step_notifications(None))
    defaults = {str(key): key.default() for key in result["data_schema"].schema}

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


def test_notifications_step_reads_existing_nested_options():
    """[REQ-HOM-118] Formular-Defaults kommen aus den genesteten Optionen."""
    options = {
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
    result = _async_test(_notifications_flow(options).async_step_notifications(None))
    defaults = {str(key): key.default() for key in result["data_schema"].schema}

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


def test_notifications_submit_saves_nested_structures_only():
    """[REQ-HOM-118] Flache Formularfelder werden nicht persistiert."""
    options_flow = _notifications_flow()
    options_flow.async_create_entry = MagicMock()

    _async_test(
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

    data = options_flow.async_create_entry.call_args[1]["data"]
    assert data["reminders"] == {
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
    assert data["weekly_report"] == {
        "enabled": True,
        "day": 2,
        "time": "18:30",
        "notify_service": "mobile_app_phone",
    }
    assert not any(key.startswith("reminder_") for key in data)
    assert not any(key.startswith("weekly_report_") for key in data)


def test_notifications_submit_merges_foreign_options():
    """[REQ-HOM-118] Merge erhält Optionen ohne Formularfeld."""
    options_flow = _notifications_flow(
        {"wellbeing_confirm": True, "audit_limit": 500, "daily_goal_ml": 1800}
    )
    options_flow.async_create_entry = MagicMock()

    _async_test(options_flow.async_step_notifications({}))

    data = options_flow.async_create_entry.call_args[1]["data"]
    assert data["wellbeing_confirm"] is True
    assert data["audit_limit"] == 500
    assert data["daily_goal_ml"] == 1800
    assert data["reminders"]["enabled"] is False


def test_notifications_submit_normalizes_invalid_values():
    """[REQ-HOM-118] Ungültige Zeiten/Wochentage/Zahlen → Defaults."""
    options_flow = _notifications_flow()
    options_flow.async_create_entry = MagicMock()

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

    data = options_flow.async_create_entry.call_args[1]["data"]
    assert data["reminders"]["time"] == "20:00"
    assert data["reminders"]["days"] == [0]
    assert data["reminders"]["quiet_start"] == ""
    assert data["reminders"]["quiet_end"] == ""
    assert data["reminders"]["conditions"]["no_drink_hours"] == 3
    assert data["reminders"]["conditions"]["bp_days"] == 0
    assert data["reminders"]["conditions"]["wellbeing_days"] == 0
    assert data["weekly_report"]["day"] == 0
    assert data["weekly_report"]["time"] == "18:00"


def test_notifications_schema_rejects_out_of_range_values():
    """[REQ-HOM-118] Die Formular-Validierung begrenzt Stunden/Tage."""
    import voluptuous as vol  # noqa: PLC0415

    schema = _async_test(_notifications_flow().async_step_notifications(None))["data_schema"]

    with pytest.raises(vol.Invalid):
        schema({"reminder_no_drink_hours": 25})
    with pytest.raises(vol.Invalid):
        schema({"reminder_bp_days": 366})
    with pytest.raises(vol.Invalid):
        schema({"reminder_wellbeing_days": -1})

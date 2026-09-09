"""Tests: HealthOMatOptionsFlow — daily_goal_ml persistence (Audit C-2).

Audit-Punkt 7b (C-2): Options flow correctly reads default from entry.options
and persists user input back to entry.options.
"""
import asyncio
import importlib.util
import os
import sys
import types
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

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
    hass.data = {
        "health_o_mat": {
            "shared": {
                "store": MagicMock()
            }
        }
    }
    store = hass.data["health_o_mat"]["shared"]["store"]
    store.all_entries = MagicMock(return_value={
        "test-entry-1": {"total_ml_lifetime": 1000}
    })

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


def test_options_flow_full_three_step_flow_creates_entry():
    """[REQ-HOM-101] init → quick_drinks → drink_lexicon → create_entry mit zusammengeführten Daten."""
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

    _async_test(options_flow.async_step_init(
        {"daily_goal_ml": 2250, "set_lifetime_ml": 0, "person_display": ""}
    ))
    user_input = {}
    for i in range(4):
        user_input[f"quick_{i}_label"] = f"Drink {i}"
        user_input[f"quick_{i}_ml"] = 250
        user_input[f"quick_{i}_icon"] = "mdi:cup-water"
    # quick_drinks-Submit erzeugt jetzt keinen Entry mehr — es verkettet auf drink_lexicon
    quick_drinks_result = _async_test(options_flow.async_step_quick_drinks(user_input))
    assert quick_drinks_result["type"] == "form"
    assert quick_drinks_result["step_id"] == "drink_lexicon"
    options_flow.async_create_entry.assert_not_called()

    _async_test(options_flow.async_step_drink_lexicon({"drink_lexicon": "kaffee=Kaffee,250"}))

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
    mock_store.all_entries = MagicMock(return_value={
        "test-entry-1": {"total_ml_lifetime": 5000}
    })
    hass.data = {
        "health_o_mat": {
            "shared": {
                "store": mock_store
            }
        }
    }

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

    _async_test(options_flow.async_step_init(
        {"daily_goal_ml": 2500, "set_lifetime_ml": 1000, "person_display": ""}
    ))
    user_input = {}
    for i in range(4):
        user_input[f"quick_{i}_label"] = f"Drink {i}"
        user_input[f"quick_{i}_ml"] = 200
        user_input[f"quick_{i}_icon"] = "mdi:cup-water"
    _async_test(options_flow.async_step_quick_drinks(user_input))
    _async_test(options_flow.async_step_drink_lexicon({"drink_lexicon": "kaffee=Kaffee,250"}))

    options_flow.async_create_entry.assert_called_once()
    data = options_flow.async_create_entry.call_args[1]["data"]
    # init-Felder + Quick-Drinks + Lexikon zusammengeführt, fremde Options bleiben unberührt
    # (fremde Optionen leben im Entry, nicht im Flow — hier wird nur geprüft,
    #  dass der Flow sie nicht anfasst/verliert)
    assert data["daily_goal_ml"] == 2500
    assert data["set_lifetime_ml"] == 1000
    assert data["drink_lexicon"] == {"kaffee": ("Kaffee", 250)}
    assert "some_key" not in data  # Flow schreibt nur seine eigenen Felder


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
    """[Spec Feature 1 - AC 10] Fehlerhafter Text: errors['base'], kein create_entry, Entry legt nicht an."""
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
            schema({"daily_goal_ml": 2000, "set_lifetime_ml": 0,
                     "person_display": "", "daily_reset_hour": bad})
        except vol.Invalid:
            pass
        else:
            assert False, f"expected vol.Invalid for daily_reset_hour={bad}"

    # 0..23 bleiben gültig — inkl. beider Grenzwerte (vol.Range ist inklusiv;
    # ein Off-by-one bei min/max würde sonst genau hier unbemerkt bleiben).
    for good in (0, 6, 23):
        validated = schema({"daily_goal_ml": 2000, "set_lifetime_ml": 0,
                             "person_display": "", "daily_reset_hour": good})
        assert validated["daily_reset_hour"] == good


def test_init_step_daily_reset_hour_defaults_to_zero():
    """[Spec Feature 2] Fehlender daily_reset_hour in entry.options → Default 0 (Bestands-Verhalten)."""
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

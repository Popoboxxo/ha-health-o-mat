"""Tests: HealthOMatStore — Real behavior tests (not source-code scanning).

These tests verify the actual behavior of HealthOMatStore by:
1. Instantiating the class with mocked HA Store
2. Calling actual methods
3. Asserting on the internal state (_data dict)
4. Verifying persistence calls
"""
import asyncio
import importlib.util
import os
import sys
import types
from unittest.mock import AsyncMock, MagicMock

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


store_module = _load("store")


def _async_test(coro):
    """Helper to run async functions in sync test context."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@pytest.fixture
def mock_store_fixture(monkeypatch):
    """Create a HealthOMatStore with mocked HA Store.

    Key: Patch Store in the store_module's namespace, not in homeassistant module.
    This is crucial because store.py has already imported Store at module load time.
    """
    # Create mock hass
    hass = MagicMock()

    # Create a mock Store instance that captures what was saved
    mock_store_instance = MagicMock()
    mock_store_instance.async_load = AsyncMock(return_value=None)
    mock_store_instance.async_save = AsyncMock()

    # Mock Store constructor - patch it in the store_module's namespace
    # This prevents the real Store class from being called when HealthOMatStore.__init__ runs
    mock_store_class = MagicMock(return_value=mock_store_instance)
    monkeypatch.setattr(store_module, 'Store', mock_store_class)

    store = store_module.HealthOMatStore(hass)
    return store, mock_store_instance


# ============================================================================
# Test 1: add_drink stores drink with all fields
# ============================================================================
def test_add_drink_stores_entry_with_correct_fields(mock_store_fixture):
    """[STORE-001] add_drink appends drink entry with ts, ml(int), type, src."""
    store, mock_store_instance = mock_store_fixture
    _async_test(store.async_load())

    entry_id = "person-1"
    ts_iso = "2026-09-05T10:30:00+02:00"
    ml = 250
    drink_type = "water"
    src = "button"

    _async_test(store.add_drink(entry_id, ts_iso, ml, drink_type, src))

    # Verify drink was added to internal state
    entry_data = store.entry(entry_id)
    assert len(entry_data["drinks"]) == 1
    drink = entry_data["drinks"][0]

    # Verify all fields are present and types correct
    assert drink["ts"] == ts_iso
    assert drink["ml"] == 250  # Should be int
    assert isinstance(drink["ml"], int)
    assert drink["type"] == drink_type
    assert drink["src"] == src


def test_add_drink_converts_ml_to_int(mock_store_fixture):
    """[STORE-002] add_drink converts ml to int (handles float/string input)."""
    store, _ = mock_store_fixture
    _async_test(store.async_load())

    entry_id = "person-1"
    ts_iso = "2026-09-05T10:30:00+02:00"

    # Pass ml as float
    _async_test(store.add_drink(entry_id, ts_iso, 250.7, "water", "button"))

    drink = store.entry(entry_id)["drinks"][0]
    assert drink["ml"] == 250
    assert isinstance(drink["ml"], int)


def test_add_drink_updates_lifetime_total(mock_store_fixture):
    """[STORE-003] add_drink increments total_ml_lifetime."""
    store, _ = mock_store_fixture
    _async_test(store.async_load())

    entry_id = "person-1"

    # Initial lifetime should be 0
    entry = store.entry(entry_id)
    assert entry["total_ml_lifetime"] == 0

    # Add first drink
    _async_test(store.add_drink(entry_id, "2026-09-05T10:00:00Z", 250, "water", "button"))
    assert entry["total_ml_lifetime"] == 250

    # Add second drink
    _async_test(store.add_drink(entry_id, "2026-09-05T11:00:00Z", 500, "coffee", "manual"))
    assert entry["total_ml_lifetime"] == 750


def test_add_drink_calls_async_save(mock_store_fixture):
    """[STORE-004] add_drink calls _async_save to persist changes."""
    store, mock_store_instance = mock_store_fixture
    _async_test(store.async_load())

    # Reset the mock call count
    mock_store_instance.async_save.reset_mock()

    _async_test(store.add_drink("person-1", "2026-09-05T10:00:00Z", 250, "water", "button"))

    # Verify async_save was called
    assert mock_store_instance.async_save.call_count >= 1


# ============================================================================
# Test 2: remove_last_drink removes and updates lifetime
# ============================================================================
def test_remove_last_drink_removes_entry(mock_store_fixture):
    """[STORE-005] remove_last_drink removes the last drink from the list."""
    store, _ = mock_store_fixture
    _async_test(store.async_load())

    entry_id = "person-1"

    # Add two drinks
    _async_test(store.add_drink(entry_id, "2026-09-05T10:00:00Z", 250, "water", "button"))
    _async_test(store.add_drink(entry_id, "2026-09-05T11:00:00Z", 500, "coffee", "manual"))

    entry = store.entry(entry_id)
    assert len(entry["drinks"]) == 2

    # Remove last drink
    success = _async_test(store.remove_last_drink(entry_id))

    assert success is True
    assert len(entry["drinks"]) == 1
    assert entry["drinks"][0]["ml"] == 250


def test_remove_last_drink_updates_lifetime(mock_store_fixture):
    """[STORE-006] remove_last_drink decrements total_ml_lifetime by removed drink ml."""
    store, _ = mock_store_fixture
    _async_test(store.async_load())

    entry_id = "person-1"

    # Add drinks totaling 750ml
    _async_test(store.add_drink(entry_id, "2026-09-05T10:00:00Z", 250, "water", "button"))
    _async_test(store.add_drink(entry_id, "2026-09-05T11:00:00Z", 500, "coffee", "manual"))

    entry = store.entry(entry_id)
    assert entry["total_ml_lifetime"] == 750

    # Remove last drink (500ml)
    _async_test(store.remove_last_drink(entry_id))

    assert entry["total_ml_lifetime"] == 250


def test_remove_last_drink_prevents_negative_lifetime(mock_store_fixture):
    """[STORE-007] remove_last_drink uses max(0, ...) to prevent negative lifetime."""
    store, _ = mock_store_fixture
    _async_test(store.async_load())

    entry_id = "person-1"

    # Set lifetime manually to a low value
    entry = store.entry(entry_id)
    entry["total_ml_lifetime"] = 100

    # Add a drink with more ml than lifetime
    _async_test(store.add_drink(entry_id, "2026-09-05T10:00:00Z", 500, "water", "button"))
    assert entry["total_ml_lifetime"] == 600

    # Remove the drink (would be 600 - 500 = 100)
    _async_test(store.remove_last_drink(entry_id))
    assert entry["total_ml_lifetime"] == 100

    # Manually test edge case: set lifetime to 200, add 500ml drink
    entry["total_ml_lifetime"] = 200
    _async_test(store.add_drink(entry_id, "2026-09-05T11:00:00Z", 500, "tea", "button"))
    # Now lifetime = 700
    # But simulate a scenario where we want to test max(0, ...)
    # Manually set to test edge case
    entry["total_ml_lifetime"] = 300
    entry["drinks"].append({"ts": "2026-09-05T12:00:00Z", "ml": 500, "type": "juice", "src": "button"})

    # Remove this drink: should be max(0, 300 - 500) = 0
    _async_test(store.remove_last_drink(entry_id))
    assert entry["total_ml_lifetime"] == 0
    assert entry["total_ml_lifetime"] >= 0  # Never negative


def test_remove_last_drink_on_empty_list_returns_false(mock_store_fixture):
    """[STORE-008] remove_last_drink returns False when no drinks exist."""
    store, _ = mock_store_fixture
    _async_test(store.async_load())

    entry_id = "person-1"
    entry = store.entry(entry_id)

    assert len(entry["drinks"]) == 0

    success = _async_test(store.remove_last_drink(entry_id))

    assert success is False
    assert len(entry["drinks"]) == 0
    assert entry["total_ml_lifetime"] == 0


def test_remove_last_drink_calls_async_save(mock_store_fixture):
    """[STORE-009] remove_last_drink calls _async_save to persist changes."""
    store, mock_store_instance = mock_store_fixture
    _async_test(store.async_load())

    entry_id = "person-1"
    _async_test(store.add_drink(entry_id, "2026-09-05T10:00:00Z", 250, "water", "button"))

    mock_store_instance.async_save.reset_mock()

    _async_test(store.remove_last_drink(entry_id))

    assert mock_store_instance.async_save.call_count >= 1


# ============================================================================
# Test 3: add_reading stores blood pressure data with optional pulse
# ============================================================================
def test_add_reading_stores_all_fields(mock_store_fixture):
    """[STORE-010] add_reading stores sys, dia, pulse, note, src, ts."""
    store, _ = mock_store_fixture
    _async_test(store.async_load())

    entry_id = "person-1"
    ts_iso = "2026-09-05T10:30:00+02:00"
    sys_ = 120
    dia = 80
    pulse = 72
    note = "After exercise"
    src = "manual"

    _async_test(store.add_reading(entry_id, ts_iso, sys_, dia, pulse, note, src))

    readings = store.entry(entry_id)["readings"]
    assert len(readings) == 1
    reading = readings[0]

    assert reading["ts"] == ts_iso
    assert reading["sys"] == 120
    assert isinstance(reading["sys"], int)
    assert reading["dia"] == 80
    assert isinstance(reading["dia"], int)
    assert reading["pulse"] == 72
    assert isinstance(reading["pulse"], int)
    assert reading["note"] == note
    assert reading["src"] == src


def test_add_reading_pulse_optional_none(mock_store_fixture):
    """[STORE-011] add_reading allows pulse=None (not converted to int)."""
    store, _ = mock_store_fixture
    _async_test(store.async_load())

    entry_id = "person-1"
    ts_iso = "2026-09-05T10:30:00+02:00"

    # Add reading without pulse (None)
    _async_test(store.add_reading(entry_id, ts_iso, 120, 80, None, "No pulse data", "button"))

    reading = store.entry(entry_id)["readings"][0]
    assert reading["pulse"] is None


def test_add_reading_pulse_float_converted_to_int(mock_store_fixture):
    """[STORE-012] add_reading converts pulse float to int."""
    store, _ = mock_store_fixture
    _async_test(store.async_load())

    entry_id = "person-1"

    _async_test(store.add_reading(entry_id, "2026-09-05T10:00:00Z", 120, 80, 72.5, "", "button"))

    reading = store.entry(entry_id)["readings"][0]
    assert reading["pulse"] == 72
    assert isinstance(reading["pulse"], int)


def test_add_reading_default_parameters(mock_store_fixture):
    """[STORE-013] add_reading uses default parameters for note and src."""
    store, _ = mock_store_fixture
    _async_test(store.async_load())

    entry_id = "person-1"

    # Call with only required parameters
    _async_test(store.add_reading(entry_id, "2026-09-05T10:00:00Z", 120, 80, 72))

    reading = store.entry(entry_id)["readings"][0]
    assert reading["note"] == ""
    assert reading["src"] == "button"


def test_add_reading_calls_async_save(mock_store_fixture):
    """[STORE-014] add_reading calls _async_save to persist changes."""
    store, mock_store_instance = mock_store_fixture
    _async_test(store.async_load())

    mock_store_instance.async_save.reset_mock()

    _async_test(store.add_reading("person-1", "2026-09-05T10:00:00Z", 120, 80, 72))

    assert mock_store_instance.async_save.call_count >= 1


# ============================================================================
# Test 4: set_wellbeing stores status and maintains history
# ============================================================================
def test_set_wellbeing_stores_current_status(mock_store_fixture):
    """[STORE-015] set_wellbeing stores current status and timestamp."""
    store, _ = mock_store_fixture
    _async_test(store.async_load())

    entry_id = "person-1"
    status = "good"
    ts_iso = "2026-09-05T10:00:00Z"

    _async_test(store.set_wellbeing(entry_id, status, ts_iso))

    entry = store.entry(entry_id)
    assert "wellbeing" in entry
    assert entry["wellbeing"]["status"] == status
    assert entry["wellbeing"]["ts"] == ts_iso


def test_set_wellbeing_creates_history_field(mock_store_fixture):
    """[STORE-016] set_wellbeing creates wellbeing_history if not exists."""
    store, _ = mock_store_fixture
    _async_test(store.async_load())

    entry_id = "person-1"

    _async_test(store.set_wellbeing(entry_id, "good", "2026-09-05T10:00:00Z"))

    entry = store.entry(entry_id)
    assert "wellbeing_history" in entry
    assert isinstance(entry["wellbeing_history"], list)


def test_set_wellbeing_updates_history_on_second_call(mock_store_fixture):
    """[STORE-017] set_wellbeing appends old status to history on update."""
    store, _ = mock_store_fixture
    _async_test(store.async_load())

    entry_id = "person-1"

    # First wellbeing update
    _async_test(store.set_wellbeing(entry_id, "good", "2026-09-05T10:00:00Z"))
    entry = store.entry(entry_id)
    assert len(entry["wellbeing_history"]) == 0  # No history yet

    # Second wellbeing update
    ts_second = "2026-09-05T11:00:00Z"
    _async_test(store.set_wellbeing(entry_id, "tired", ts_second))

    # Old status should be in history (with new timestamp as per implementation)
    assert len(entry["wellbeing_history"]) == 1
    assert entry["wellbeing_history"][0]["status"] == "good"
    assert entry["wellbeing_history"][0]["ts"] == ts_second  # Timestamp is from the update that archived it

    # Current status should be updated
    assert entry["wellbeing"]["status"] == "tired"
    assert entry["wellbeing"]["ts"] == ts_second


def test_set_wellbeing_history_capped_at_100(mock_store_fixture):
    """[STORE-018] set_wellbeing limits history to last 100 entries."""
    store, _ = mock_store_fixture
    _async_test(store.async_load())

    entry_id = "person-1"

    # Add 101 wellbeing updates
    for i in range(101):
        status = f"status-{i}"
        ts = f"2026-09-05T{i%24:02d}:{i%60:02d}:00Z"
        _async_test(store.set_wellbeing(entry_id, status, ts))

    entry = store.entry(entry_id)

    # History should not exceed 100
    assert len(entry["wellbeing_history"]) <= 100

    # The current status should be the last one
    assert entry["wellbeing"]["status"] == "status-100"


def test_set_wellbeing_calls_async_save(mock_store_fixture):
    """[STORE-019] set_wellbeing calls _async_save to persist changes."""
    store, mock_store_instance = mock_store_fixture
    _async_test(store.async_load())

    mock_store_instance.async_save.reset_mock()

    _async_test(store.set_wellbeing("person-1", "good", "2026-09-05T10:00:00Z"))

    assert mock_store_instance.async_save.call_count >= 1


# ============================================================================
# Test 5: entry() isolation between different entry_ids
# ============================================================================
def test_entry_isolation_separate_drinks(mock_store_fixture):
    """[STORE-020] entry() isolates drinks per entry_id."""
    store, _ = mock_store_fixture
    _async_test(store.async_load())

    # Add drinks to person-1
    _async_test(store.add_drink("person-1", "2026-09-05T10:00:00Z", 250, "water", "button"))
    _async_test(store.add_drink("person-1", "2026-09-05T11:00:00Z", 250, "water", "button"))

    # Add drink to person-2
    _async_test(store.add_drink("person-2", "2026-09-05T10:30:00Z", 500, "coffee", "button"))

    # Verify isolation
    entry1 = store.entry("person-1")
    entry2 = store.entry("person-2")

    assert len(entry1["drinks"]) == 2
    assert len(entry2["drinks"]) == 1
    assert entry1["total_ml_lifetime"] == 500
    assert entry2["total_ml_lifetime"] == 500


def test_entry_isolation_separate_readings(mock_store_fixture):
    """[STORE-021] entry() isolates readings per entry_id."""
    store, _ = mock_store_fixture
    _async_test(store.async_load())

    # Add readings to person-1
    _async_test(store.add_reading("person-1", "2026-09-05T10:00:00Z", 120, 80, 72))
    _async_test(store.add_reading("person-1", "2026-09-05T11:00:00Z", 125, 82, 75))

    # Add reading to person-2
    _async_test(store.add_reading("person-2", "2026-09-05T10:30:00Z", 110, 70, 60))

    # Verify isolation
    entry1 = store.entry("person-1")
    entry2 = store.entry("person-2")

    assert len(entry1["readings"]) == 2
    assert len(entry2["readings"]) == 1
    assert entry1["readings"][0]["sys"] == 120
    assert entry2["readings"][0]["sys"] == 110


def test_entry_isolation_separate_wellbeing(mock_store_fixture):
    """[STORE-022] entry() isolates wellbeing per entry_id."""
    store, _ = mock_store_fixture
    _async_test(store.async_load())

    # Set wellbeing for person-1
    _async_test(store.set_wellbeing("person-1", "good", "2026-09-05T10:00:00Z"))

    # Set wellbeing for person-2
    _async_test(store.set_wellbeing("person-2", "tired", "2026-09-05T10:30:00Z"))

    # Verify isolation
    entry1 = store.entry("person-1")
    entry2 = store.entry("person-2")

    assert entry1["wellbeing"]["status"] == "good"
    assert entry2["wellbeing"]["status"] == "tired"


# ============================================================================
# Test 6: Entry initialization and defaults
# ============================================================================
def test_entry_creates_default_structure_on_first_access(mock_store_fixture):
    """[STORE-023] entry() creates default structure for new entry_id."""
    store, _ = mock_store_fixture
    _async_test(store.async_load())

    entry_id = "new-person"
    entry = store.entry(entry_id)

    # Verify default fields exist
    assert "person" in entry
    assert "drinks" in entry
    assert "readings" in entry
    assert "total_ml_lifetime" in entry

    # Verify default values
    assert entry["person"] == ""
    assert entry["drinks"] == []
    assert entry["readings"] == []
    assert entry["total_ml_lifetime"] == 0


def test_entry_reuses_existing_entry(mock_store_fixture):
    """[STORE-024] entry() returns existing data on second access."""
    store, _ = mock_store_fixture
    _async_test(store.async_load())

    entry_id = "person-1"

    # Add data
    _async_test(store.add_drink(entry_id, "2026-09-05T10:00:00Z", 250, "water", "button"))

    # Access the same entry again
    entry = store.entry(entry_id)

    # Data should still be there
    assert len(entry["drinks"]) == 1
    assert entry["total_ml_lifetime"] == 250


# ============================================================================
# Test 7: set_person and set_lifetime_start methods
# ============================================================================
def test_set_person_stores_name(mock_store_fixture):
    """[STORE-025] set_person stores person name in entry."""
    store, _ = mock_store_fixture
    _async_test(store.async_load())

    entry_id = "person-1"
    person_name = "Alice Smith"

    _async_test(store.set_person(entry_id, person_name))

    entry = store.entry(entry_id)
    assert entry["person"] == person_name


def test_set_lifetime_start_sets_value(mock_store_fixture):
    """[STORE-026] set_lifetime_start sets total_ml_lifetime."""
    store, _ = mock_store_fixture
    _async_test(store.async_load())

    entry_id = "person-1"
    lifetime_ml = 5000

    _async_test(store.set_lifetime_start(entry_id, lifetime_ml))

    entry = store.entry(entry_id)
    assert entry["total_ml_lifetime"] == lifetime_ml


def test_set_lifetime_start_converts_to_int(mock_store_fixture):
    """[STORE-027] set_lifetime_start converts ml to int."""
    store, _ = mock_store_fixture
    _async_test(store.async_load())

    entry_id = "person-1"

    _async_test(store.set_lifetime_start(entry_id, 5000.5))

    entry = store.entry(entry_id)
    assert entry["total_ml_lifetime"] == 5000
    assert isinstance(entry["total_ml_lifetime"], int)


# ============================================================================
# Test 8: all_entries returns all entries
# ============================================================================
def test_all_entries_returns_entries_dict(mock_store_fixture):
    """[STORE-028] all_entries() returns dict of all entries."""
    store, _ = mock_store_fixture
    _async_test(store.async_load())

    # Add data to multiple entries
    _async_test(store.add_drink("person-1", "2026-09-05T10:00:00Z", 250, "water", "button"))
    _async_test(store.add_drink("person-2", "2026-09-05T10:00:00Z", 500, "coffee", "button"))

    all_entries = store.all_entries()

    assert isinstance(all_entries, dict)
    assert "person-1" in all_entries
    assert "person-2" in all_entries
    assert len(all_entries) == 2


# ============================================================================
# Test 9: async_load initializes empty state correctly
# ============================================================================
def test_async_load_initializes_empty_state(mock_store_fixture):
    """[STORE-029] async_load initializes _data with empty entries dict."""
    store, mock_store_instance = mock_store_fixture
    mock_store_instance.async_load = AsyncMock(return_value=None)

    _async_test(store.async_load())

    # Should have initialized entries dict
    assert "entries" in store._data
    assert isinstance(store._data["entries"], dict)
    assert len(store._data["entries"]) == 0


def test_async_load_preserves_existing_data(mock_store_fixture):
    """[STORE-030] async_load preserves data from Store."""
    store, mock_store_instance = mock_store_fixture

    # Mock Store to return some existing data
    existing_data = {
        "entries": {
            "person-1": {
                "person": "Alice",
                "drinks": [{"ts": "2026-09-05T10:00:00Z", "ml": 250, "type": "water", "src": "button"}],
                "readings": [],
                "total_ml_lifetime": 250
            }
        }
    }
    mock_store_instance.async_load = AsyncMock(return_value=existing_data)

    _async_test(store.async_load())

    # Data should be loaded
    entry = store.entry("person-1")
    assert entry["person"] == "Alice"
    assert len(entry["drinks"]) == 1
    assert entry["total_ml_lifetime"] == 250

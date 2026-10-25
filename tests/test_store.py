"""Tests: HealthOMatStore — Real behavior tests (not source-code scanning).

These tests verify the actual behavior of HealthOMatStore by:
1. Instantiating the class with mocked HA Store
2. Calling actual methods
3. Asserting on the internal state (_data dict)
4. Verifying persistence calls
"""

import asyncio
import copy
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
    monkeypatch.setattr(store_module, "Store", mock_store_class)

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
    entry["drinks"].append(
        {"ts": "2026-09-05T12:00:00Z", "ml": 500, "type": "juice", "src": "button"}
    )

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

    # Old status should be in history WITH ITS OWN timestamp (when it was
    # reported), not with the timestamp of the update that archived it.
    assert len(entry["wellbeing_history"]) == 1
    assert entry["wellbeing_history"][0]["status"] == "good"
    assert entry["wellbeing_history"][0]["ts"] == "2026-09-05T10:00:00Z"

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
        ts = f"2026-09-05T{i % 24:02d}:{i % 60:02d}:00Z"
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
# REQ-HOM-112: Historie-Semantik festgeschrieben
# ============================================================================
def test_req_hom_112_wellbeing_history_records_replaced_status_with_report_timestamp(
    mock_store_fixture,
):
    """[REQ-HOM-112] Die Wohlbefinden-Historie führt vergangene Meldungen.

    Ein Historieneintrag `{ts, status}` bedeutet "dieser Status wurde zu `ts`
    gemeldet". Der ABGELOESTE Status traegt seinen EIGENEN Meldezeitpunkt, nicht
    den Zeitpunkt des Wechsels. Der AKTUELLE Zustand steht ausschliesslich in
    `wellbeing`.

    Diese Semantik ist die Grundlage des Chart-Fixes: wer die Serie nur aus
    der Historie baut, markiert den abgeloesten Wert als "aktuell".
    """
    store, _ = mock_store_fixture
    _async_test(store.async_load())

    entry_id = "person-1"
    first_ts = "2026-10-19T08:00:00+02:00"
    second_ts = "2026-10-19T18:00:00+02:00"

    _async_test(store.set_wellbeing(entry_id, "bad", first_ts))
    _async_test(store.set_wellbeing(entry_id, "good", second_ts))

    entry = store.entry(entry_id)
    history = entry["wellbeing_history"]

    # Genau ein Historieneintrag …
    assert len(history) == 1
    # … mit dem ABGELOESTEN Status …
    assert history[0]["status"] == "bad"
    # … und dessen eigenem Meldezeitpunkt (nicht dem des Wechsels).
    assert history[0]["ts"] == first_ts
    assert set(history[0]) == {"ts", "status"}

    # Der aktuelle Zustand steht ausschliesslich in `wellbeing`.
    assert entry["wellbeing"]["status"] == "good"
    assert entry["wellbeing"]["ts"] == second_ts

    # Der aktuelle Status taucht NICHT in der Historie auf.
    assert all(item["status"] != "good" for item in history)


def test_req_hom_112_wellbeing_history_stays_empty_for_the_first_report(mock_store_fixture):
    """[REQ-HOM-112] Die erste Meldung erzeugt noch keinen Historieneintrag.

    Ohne Vorgabe gibt es nichts zu protokollieren — der erste Wert ist der
    aktuelle Wert, kein abgeloester.
    """
    store, _ = mock_store_fixture
    _async_test(store.async_load())

    entry_id = "person-1"
    ts_iso = "2026-10-19T08:00:00+02:00"

    _async_test(store.set_wellbeing(entry_id, "bad", ts_iso))

    entry = store.entry(entry_id)
    assert entry["wellbeing_history"] == []
    assert entry["wellbeing"]["status"] == "bad"
    assert entry["wellbeing"]["ts"] == ts_iso


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
                "drinks": [
                    {"ts": "2026-09-05T10:00:00Z", "ml": 250, "type": "water", "src": "button"}
                ],
                "readings": [],
                "total_ml_lifetime": 250,
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


# ============================================================================
# Finding N-7: remove_last_reading (BP-Undo)
# ============================================================================
def test_remove_last_reading_removes_last_reading(mock_store_fixture):
    """[N-7] remove_last_reading entfernt die zuletzt angehängte Messung."""
    store, _ = mock_store_fixture
    _async_test(store.async_load())

    _async_test(store.add_reading("person-1", "2026-09-05T10:00:00Z", 120, 80, 70))
    _async_test(store.add_reading("person-1", "2026-09-05T11:00:00Z", 130, 85, 75))

    success = _async_test(store.remove_last_reading("person-1"))

    assert success is True
    readings = store.entry("person-1")["readings"]
    assert len(readings) == 1
    assert readings[0]["sys"] == 120


def test_remove_last_reading_on_empty_returns_false(mock_store_fixture):
    """[N-7] Leerer Bestand → False (Aufrufer entscheidet über Fehlertext)."""
    store, _ = mock_store_fixture
    _async_test(store.async_load())

    assert _async_test(store.remove_last_reading("person-1")) is False
    assert store.entry("person-1")["readings"] == []


def test_remove_last_reading_does_not_touch_lifetime(mock_store_fixture):
    """[N-7] BP-Undo lässt den Trink-Lebenszähler unberührt."""
    store, _ = mock_store_fixture
    _async_test(store.async_load())

    _async_test(store.add_drink("person-1", "2026-09-05T10:00:00Z", 500, "water", "button"))
    _async_test(store.add_reading("person-1", "2026-09-05T11:00:00Z", 120, 80, 70))

    _async_test(store.remove_last_reading("person-1"))

    assert store.entry("person-1")["total_ml_lifetime"] == 500


def test_remove_last_reading_calls_async_save(mock_store_fixture):
    """[N-7] remove_last_reading persistiert die Änderung."""
    store, mock_store_instance = mock_store_fixture
    _async_test(store.async_load())
    _async_test(store.add_reading("person-1", "2026-09-05T10:00:00Z", 120, 80, 70))

    mock_store_instance.async_save.reset_mock()
    _async_test(store.remove_last_reading("person-1"))

    assert mock_store_instance.async_save.call_count >= 1


# ============================================================================
# Finding N-2: Retention/Archiv (REQ-HOM-109)
# ============================================================================
def test_entry_default_includes_archived_counts(mock_store_fixture):
    """[N-2] Neue Einträge tragen die Archiv-Kennzahlen (Default 0)."""
    store, _ = mock_store_fixture
    _async_test(store.async_load())

    assert store.entry("person-1")["archived_counts"] == {"drinks": 0, "readings": 0}


def test_apply_retention_keeps_only_kept_lists_and_lifetime_unchanged(mock_store_fixture):
    """[N-2] apply_retention ersetzt die Listen; total_ml_lifetime bleibt gleich."""
    store, _ = mock_store_fixture
    _async_test(store.async_load())

    entry = store.entry("person-1")
    old_drink = {"ts": "2025-01-01T00:00:00", "ml": 250, "type": "water", "src": "button"}
    new_drink = {"ts": "2026-09-01T00:00:00", "ml": 500, "type": "water", "src": "button"}
    old_reading = {
        "ts": "2025-01-01T00:00:00",
        "sys": 120,
        "dia": 80,
        "pulse": 70,
        "note": "",
        "src": "button",
    }
    entry["drinks"] = [old_drink, new_drink]
    entry["readings"] = [old_reading]
    entry["total_ml_lifetime"] = 750

    _async_test(store.apply_retention("person-1", [new_drink], []))

    assert entry["drinks"] == [new_drink]
    assert entry["readings"] == []
    # Summe/Eintragszahl der Historie bleibt unangetastet
    assert entry["total_ml_lifetime"] == 750
    assert entry["archived_counts"] == {"drinks": 1, "readings": 1}


def test_append_archive_extends_archive_store(mock_store_fixture):
    """[N-2] append_archive hängt verschobene Einträge an (separater Store)."""
    archive, _ = mock_store_fixture
    _async_test(archive.async_load())

    drinks = [{"ts": "2025-01-01T00:00:00", "ml": 250, "type": "water", "src": "button"}]
    readings = [{"ts": "2025-01-01T00:00:00", "sys": 120, "dia": 80}]

    _async_test(archive.append_archive("person-1", drinks, readings))

    e = archive.all_entries()["person-1"]
    assert e["drinks"] == drinks
    assert e["readings"] == readings


def test_append_archive_is_additive(mock_store_fixture):
    """[N-2] Mehrfaches Archivieren verliert keine bereits archivierten Einträge."""
    archive, _ = mock_store_fixture
    _async_test(archive.async_load())

    _async_test(archive.append_archive("person-1", [{"ts": "2025-01-01"}], []))
    _async_test(archive.append_archive("person-1", [{"ts": "2025-02-01"}], []))

    assert [d["ts"] for d in archive.all_entries()["person-1"]["drinks"]] == [
        "2025-01-01",
        "2025-02-01",
    ]


# ============================================================================
# Finding N-2: Store-Schema-Migration v2 → v3 (archived_counts)
# ============================================================================
def _v2_fixture() -> dict:
    """Repräsentativer Bestand auf Schema-Stufe 2 (keine archived_counts)."""
    return {
        "schema": 2,
        "entries": {
            "e1": {
                "person": "Max",
                "drinks": [
                    {"ts": "2026-09-01T08:00:00", "ml": 250, "type": "Kaffee", "src": "button"}
                ],
                "readings": [],
                "total_ml_lifetime": 250,
                "inputs": {"sys": 120},
            }
        },
    }


def test_store_migration_v2_to_v3_adds_archived_counts(mock_store_fixture):
    """[N-2/REQ-HOM-102] v2-Bestand → v3 ergänzt archived_counts, Daten bleiben."""
    store, mock_store_instance = mock_store_fixture
    mock_store_instance.async_load = AsyncMock(side_effect=lambda: _v2_fixture())

    _async_test(store.async_load())

    assert store.raw_data()["schema"] == store_module.STORE_SCHEMA_VERSION
    e1 = store.entry("e1")
    assert e1["archived_counts"] == {"drinks": 0, "readings": 0}
    # Bestandsdaten unverändert; v4 ergänzt nur id/created_at/voided_*
    assert [{k: d[k] for k in ("ts", "ml", "type", "src")} for d in e1["drinks"]] == [
        {k: d[k] for k in ("ts", "ml", "type", "src")}
        for d in _v2_fixture()["entries"]["e1"]["drinks"]
    ]
    assert e1["total_ml_lifetime"] == 250
    assert e1["inputs"] == {"sys": 120}


def test_store_migration_v2_to_v3_is_idempotent(mock_store_fixture):
    """[N-2/REQ-HOM-102] Erneutes Laden des migrierten Bestands ändert nichts."""
    store, mock_store_instance = mock_store_fixture
    mock_store_instance.async_load = AsyncMock(side_effect=lambda: _v2_fixture())
    _async_test(store.async_load())
    assert store.raw_data()["schema"] == store_module.STORE_SCHEMA_VERSION

    # Bereits migrierten Bestand (schema=3) erneut laden — vorhandene Zähler
    # dürfen dabei NICHT zurückgesetzt werden.
    migrated = store.raw_data()
    migrated["entries"]["e1"]["archived_counts"]["drinks"] = 7
    mock_store_instance.async_load = AsyncMock(return_value=migrated)
    _async_test(store.async_load())

    assert store.entry("e1")["archived_counts"]["drinks"] == 7
    assert store.raw_data()["schema"] == store_module.STORE_SCHEMA_VERSION


def test_invalid_schema_backup_targets_own_storage_key():
    """[N-2] Recovery sichert die EIGENE Store-Datei, nie die des Haupt-Stores."""
    hass = MagicMock()
    hass.config.path = MagicMock(return_value="/data/.storage/health_o_mat_archive")
    store = store_module.HealthOMatStore(hass, storage_key="health_o_mat_archive")
    store._store = MagicMock()
    store._store.async_load = AsyncMock(return_value={"unexpected": True})
    hass.async_add_executor_job = AsyncMock(return_value=True)
    hass.services.async_call = AsyncMock()

    _async_test(store.async_load())

    assert hass.config.path.call_args[0] == (".storage", "health_o_mat_archive")
    assert store.raw_data() == {"schema": 4, "entries": {}}


# ============================================================================
# Store-Schema v4 (REQ-HOM-115): IDs/Void-Felder, Wellbeing-Ereignisse, Audit
# ============================================================================
def _v1_bestand() -> dict:
    """v1-Bestand: kein schema-Feld, keine inputs/archived_counts/v4-Felder."""
    return {
        "entries": {
            "e1": {
                "person": "Max",
                "drinks": [
                    {"ts": "2026-09-01T08:00:00", "ml": 250, "type": "Kaffee", "src": "button"}
                ],
                "readings": [
                    {
                        "ts": "2026-09-01T09:00:00",
                        "sys": 120,
                        "dia": 80,
                        "pulse": 60,
                        "note": "",
                        "src": "button",
                    }
                ],
                "total_ml_lifetime": 250,
                "wellbeing": {"status": "good", "ts": "2026-09-01T10:00:00"},
                "wellbeing_history": [
                    {"ts": "2026-09-01T07:00:00", "status": "bad"},
                    {"ts": "2026-09-01T08:30:00", "status": "okay"},
                ],
            }
        }
    }


def _v2_bestand() -> dict:
    data = _v1_bestand()
    data["schema"] = 2
    data["entries"]["e1"]["inputs"] = {"sys": 120}
    return data


def _v3_bestand() -> dict:
    data = _v2_bestand()
    data["schema"] = 3
    data["entries"]["e1"]["archived_counts"] = {"drinks": 0, "readings": 0}
    return data


def _expected_id(kind: str, index: int, ts) -> str:
    import uuid as _uuid

    return str(_uuid.uuid5(_uuid.NAMESPACE_URL, f"e1:{kind}:{index}:{ts}"))


@pytest.mark.parametrize("fixture", [_v1_bestand, _v2_bestand, _v3_bestand])
def test_store_migration_to_v4_adds_ids_and_void_fields(mock_store_fixture, fixture):
    """[REQ-HOM-115] v1/v2/v3 → v4 ergänzt id, created_at und Void-Felder."""
    store, mock_store_instance = mock_store_fixture
    mock_store_instance.async_load = AsyncMock(return_value=fixture())

    _async_test(store.async_load())

    assert store.raw_data()["schema"] == 4
    e1 = store.entry("e1")
    drink = e1["drinks"][0]
    reading = e1["readings"][0]
    assert drink["id"] == _expected_id("drinks", 0, "2026-09-01T08:00:00")
    assert drink["created_at"] == "2026-09-01T08:00:00"
    assert drink["voided_at"] is None
    assert drink["voided_by"] is None
    assert drink["void_reason"] is None
    assert reading["id"] == _expected_id("readings", 0, "2026-09-01T09:00:00")
    assert reading["created_at"] == "2026-09-01T09:00:00"
    assert reading["voided_at"] is None
    # Bestandsdaten unverändert
    assert (drink["ts"], drink["ml"], drink["type"], drink["src"]) == (
        "2026-09-01T08:00:00",
        250,
        "Kaffee",
        "button",
    )
    assert e1["total_ml_lifetime"] == 250
    assert e1["audit_log"] == []


@pytest.mark.parametrize("fixture", [_v1_bestand, _v2_bestand, _v3_bestand])
def test_store_migration_to_v4_builds_wellbeing_entries(mock_store_fixture, fixture):
    """[REQ-HOM-115] Historie + aktueller Wert → wellbeing_entries, aktueller zuletzt."""
    store, mock_store_instance = mock_store_fixture
    mock_store_instance.async_load = AsyncMock(return_value=fixture())

    _async_test(store.async_load())

    entries = store.entry("e1")["wellbeing_entries"]
    assert [item["key"] for item in entries] == ["bad", "okay", "good"]
    assert [item["ts"] for item in entries] == [
        "2026-09-01T07:00:00",
        "2026-09-01T08:30:00",
        "2026-09-01T10:00:00",
    ]
    assert entries[-1]["created_at"] == "2026-09-01T10:00:00"
    assert entries[-1]["voided_at"] is None
    assert entries[-1]["id"] == _expected_id("wellbeing", 2, "2026-09-01T10:00:00")
    assert all(
        set(item)
        == {
            "id",
            "ts",
            "key",
            "created_at",
            "voided_at",
            "voided_by",
            "void_reason",
        }
        for item in entries
    )
    # Legacy-Spiegel bleibt unverändert/kompatibel
    assert store.entry("e1")["wellbeing"] == {
        "status": "good",
        "ts": "2026-09-01T10:00:00",
    }
    assert store.entry("e1")["wellbeing_history"] == [
        {"ts": "2026-09-01T07:00:00", "status": "bad"},
        {"ts": "2026-09-01T08:30:00", "status": "okay"},
    ]


def test_store_migration_v4_is_idempotent_and_deterministic(mock_store_fixture):
    """[REQ-HOM-115] Zweimal migrieren = gleiche IDs/Daten (keine Duplikate)."""
    store, mock_store_instance = mock_store_fixture
    mock_store_instance.async_load = AsyncMock(return_value=_v1_bestand())

    _async_test(store.async_load())
    first = copy.deepcopy(store.raw_data())
    _async_test(store.async_load())
    second = copy.deepcopy(store.raw_data())

    assert first == second
    assert second["schema"] == 4
    assert len(second["entries"]["e1"]["wellbeing_entries"]) == 3
    assert len(second["entries"]["e1"]["drinks"]) == 1


def test_store_migration_v4_same_ids_for_separate_loads(mock_store_fixture):
    """[REQ-HOM-115] Deterministische IDs: getrennte Läufe erzeugen dieselben IDs."""
    store, mock_store_instance = mock_store_fixture
    mock_store_instance.async_load = AsyncMock(return_value=_v1_bestand())
    _async_test(store.async_load())
    ids_first = [d["id"] for d in store.entry("e1")["drinks"]]

    mock_store_instance.async_load = AsyncMock(return_value=_v1_bestand())
    _async_test(store.async_load())
    ids_second = [d["id"] for d in store.entry("e1")["drinks"]]

    assert ids_first == ids_second


def test_store_migration_v4_wellbeing_dedupes_and_tolerates_missing_ts(
    mock_store_fixture,
):
    """[REQ-HOM-115] Doppelte (key, ts)-Paare und fehlende ts brechen nichts."""
    store, mock_store_instance = mock_store_fixture
    fixture = {
        "schema": 3,
        "entries": {
            "e1": {
                "drinks": [],
                "readings": [],
                "wellbeing": {"status": "good", "ts": "2026-09-01T10:00:00"},
                "wellbeing_history": [
                    {"ts": "2026-09-01T07:00:00", "status": "bad"},
                    {"ts": "2026-09-01T07:00:00", "status": "bad"},
                    {"status": "okay"},
                    {"ts": "2026-09-01T10:00:00", "status": "good"},
                ],
            }
        },
    }
    mock_store_instance.async_load = AsyncMock(return_value=fixture)

    _async_test(store.async_load())

    entries = store.entry("e1")["wellbeing_entries"]
    assert [item["key"] for item in entries] == ["bad", "okay", "good"]
    assert entries[1]["ts"] is None
    assert entries[-1]["key"] == "good"


def test_entry_default_includes_v4_fields(mock_store_fixture):
    """[REQ-HOM-115] Neue Einträge tragen wellbeing_entries und audit_log."""
    store, _ = mock_store_fixture
    _async_test(store.async_load())

    entry = store.entry("person-1")
    assert entry["wellbeing_entries"] == []
    assert entry["audit_log"] == []
    assert entry["readings"] == []


def test_active_helpers_filter_voided_entries(mock_store_fixture):
    """[REQ-HOM-115] active_* blendet gelöschte Einträge aus, Bestand bleibt."""
    store, _ = mock_store_fixture
    _async_test(store.async_load())

    _async_test(store.add_drink("e1", "2026-09-05T10:00:00Z", 250, "Wasser", "button"))
    _async_test(store.add_drink("e1", "2026-09-05T11:00:00Z", 500, "Kaffee", "button"))
    _async_test(store.add_reading("e1", "2026-09-05T12:00:00Z", 120, 80, 70))
    _async_test(store.set_wellbeing("e1", "good", "2026-09-05T13:00:00Z"))

    first_drink = store.entry("e1")["drinks"][0]
    _async_test(store.void_drink("e1", first_drink["id"]))

    assert [d["ml"] for d in store.active_drinks("e1")] == [500]
    assert len(store.entry("e1")["drinks"]) == 2  # kein Hard-Delete
    assert len(store.active_readings("e1")) == 1
    assert len(store.active_wellbeing_entries("e1")) == 1
    assert store.current_wellbeing("e1")["key"] == "good"


def test_void_and_restore_drink_updates_lifetime(mock_store_fixture):
    """[REQ-HOM-115] Void subtrahiert ml, Restore addiert sie wieder."""
    store, _ = mock_store_fixture
    _async_test(store.async_load())

    _async_test(store.add_drink("e1", "2026-09-05T10:00:00Z", 250, "Wasser", "button"))
    _async_test(store.add_drink("e1", "2026-09-05T11:00:00Z", 500, "Kaffee", "button"))
    entry = store.entry("e1")
    assert entry["total_ml_lifetime"] == 750
    first_id = entry["drinks"][0]["id"]

    assert _async_test(store.void_drink("e1", first_id, actor="user-1", reason="Tippfehler"))
    assert entry["total_ml_lifetime"] == 500
    assert [d["ml"] for d in store.active_drinks("e1")] == [500]
    assert entry["drinks"][0]["voided_by"] == "user-1"
    assert entry["drinks"][0]["void_reason"] == "Tippfehler"
    assert entry["drinks"][0]["voided_at"] is not None

    # Doppeltes Void / unbekannte ID → False
    assert _async_test(store.void_drink("e1", first_id)) is False
    assert _async_test(store.void_drink("e1", "nope")) is False

    assert _async_test(store.restore_drink("e1", first_id, actor="user-1"))
    assert entry["total_ml_lifetime"] == 750
    assert len(store.active_drinks("e1")) == 2
    assert entry["drinks"][0]["voided_at"] is None
    assert entry["drinks"][0]["voided_by"] is None
    assert entry["drinks"][0]["void_reason"] is None
    assert _async_test(store.restore_drink("e1", first_id)) is False


def test_void_drink_lifetime_never_negative(mock_store_fixture):
    """[REQ-HOM-115] Void klemmt total_ml_lifetime bei 0 (nie negativ)."""
    store, _ = mock_store_fixture
    _async_test(store.async_load())

    _async_test(store.add_drink("e1", "2026-09-05T10:00:00Z", 500, "Wasser", "button"))
    entry = store.entry("e1")
    entry["total_ml_lifetime"] = 100  # z. B. manuell korrigierter Startwert
    drink_id = entry["drinks"][0]["id"]

    _async_test(store.void_drink("e1", drink_id))

    assert entry["total_ml_lifetime"] == 0


def test_void_and_restore_reading(mock_store_fixture):
    """[REQ-HOM-115] Void/Restore einer Messung lässt Lifetime unberührt."""
    store, _ = mock_store_fixture
    _async_test(store.async_load())

    _async_test(store.add_drink("e1", "2026-09-05T09:00:00Z", 250, "Wasser", "button"))
    _async_test(store.add_reading("e1", "2026-09-05T10:00:00Z", 120, 80, 70))
    _async_test(store.add_reading("e1", "2026-09-05T11:00:00Z", 130, 85, 75))
    entry = store.entry("e1")
    reading_id = entry["readings"][0]["id"]

    assert _async_test(store.void_reading("e1", reading_id, actor="user-1", reason="doppelt"))
    assert [r["sys"] for r in store.active_readings("e1")] == [130]
    assert len(entry["readings"]) == 2
    assert entry["readings"][0]["void_reason"] == "doppelt"
    assert entry["total_ml_lifetime"] == 250
    assert _async_test(store.void_reading("e1", reading_id)) is False

    assert _async_test(store.restore_reading("e1", reading_id, actor="user-1"))
    assert [r["sys"] for r in store.active_readings("e1")] == [120, 130]
    assert entry["total_ml_lifetime"] == 250
    assert _async_test(store.restore_reading("e1", reading_id)) is False


def test_void_and_restore_wellbeing_falls_back_to_predecessor(mock_store_fixture):
    """[REQ-HOM-115] Nach Void fällt der aktuelle Wert auf den Vorgänger."""
    store, _ = mock_store_fixture
    _async_test(store.async_load())

    _async_test(store.set_wellbeing("e1", "good", "2026-09-05T10:00:00Z"))
    _async_test(store.set_wellbeing("e1", "bad", "2026-09-05T11:00:00Z"))
    entry = store.entry("e1")
    bad_id = entry["wellbeing_entries"][-1]["id"]
    assert entry["wellbeing"] == {"status": "bad", "ts": "2026-09-05T11:00:00Z"}

    assert _async_test(store.void_wellbeing("e1", bad_id, actor="user-1", reason="falsch"))
    assert store.current_wellbeing("e1")["key"] == "good"
    assert entry["wellbeing"] == {"status": "good", "ts": "2026-09-05T10:00:00Z"}
    assert entry["wellbeing_history"] == []
    assert len(entry["wellbeing_entries"]) == 2  # kein Hard-Delete
    assert _async_test(store.void_wellbeing("e1", bad_id)) is False

    assert _async_test(store.restore_wellbeing("e1", bad_id, actor="user-1"))
    assert store.current_wellbeing("e1")["key"] == "bad"
    assert entry["wellbeing"] == {"status": "bad", "ts": "2026-09-05T11:00:00Z"}
    assert entry["wellbeing_history"] == [{"ts": "2026-09-05T10:00:00Z", "status": "good"}]
    assert _async_test(store.restore_wellbeing("e1", bad_id)) is False


def test_void_wellbeing_every_entry_leaves_empty_mirrors(mock_store_fixture):
    """[REQ-HOM-115] Ohne aktive Meldung bleiben die Legacy-Spiegel leer."""
    store, _ = mock_store_fixture
    _async_test(store.async_load())

    _async_test(store.set_wellbeing("e1", "good", "2026-09-05T10:00:00Z"))
    entry = store.entry("e1")
    entry_id = entry["wellbeing_entries"][0]["id"]

    _async_test(store.void_wellbeing("e1", entry_id))

    assert store.current_wellbeing("e1") is None
    assert entry["wellbeing"] == {}
    assert entry["wellbeing_history"] == []


# ============================================================================
# Audit-Log (REQ-HOM-115)
# ============================================================================
def _actions(store, entry_id: str = "e1") -> list[str]:
    return [event["action"] for event in store.entry(entry_id)["audit_log"]]


def test_audit_log_records_add_void_restore(mock_store_fixture):
    """[REQ-HOM-115] add/void/restore erzeugen Audit-Events mit minimalen Details."""
    store, _ = mock_store_fixture
    _async_test(store.async_load())

    _async_test(
        store.add_drink("e1", "2026-09-05T10:00:00Z", 250, "Wasser", "button", actor="user-1")
    )
    drink = store.entry("e1")["drinks"][0]
    _async_test(store.void_drink("e1", drink["id"], actor="user-1", reason="Tippfehler"))
    _async_test(store.restore_drink("e1", drink["id"], actor="user-1"))

    audit = store.entry("e1")["audit_log"]
    assert [event["action"] for event in audit] == [
        "drink_added",
        "entry_voided",
        "entry_restored",
    ]
    assert all(
        set(event)
        == {
            "id",
            "ts",
            "action",
            "kind",
            "target_id",
            "actor",
            "details",
        }
        for event in audit
    )
    assert all(event["kind"] == "drinks" for event in audit)
    assert all(event["target_id"] == drink["id"] for event in audit)
    assert all(event["actor"] == "user-1" for event in audit)
    # Nur Metadaten — keine vollständigen Gesundheitsdaten
    assert audit[0]["details"] == {"ml": 250}
    assert audit[1]["details"] == {"reason": "Tippfehler"}
    assert audit[2]["details"] == {}
    assert isinstance(audit[0]["ts"], str)


def test_audit_log_covers_reading_and_wellbeing(mock_store_fixture):
    """[REQ-HOM-115] Messung und Wohlbefinden erzeugen passende Events."""
    store, _ = mock_store_fixture
    _async_test(store.async_load())

    _async_test(store.add_reading("e1", "2026-09-05T10:00:00Z", 120, 80, 70))
    _async_test(store.set_wellbeing("e1", "good", "2026-09-05T11:00:00Z"))
    reading_id = store.entry("e1")["readings"][0]["id"]
    wellbeing_id = store.entry("e1")["wellbeing_entries"][0]["id"]
    _async_test(store.void_reading("e1", reading_id))
    _async_test(store.void_wellbeing("e1", wellbeing_id))
    _async_test(store.restore_reading("e1", reading_id))
    _async_test(store.restore_wellbeing("e1", wellbeing_id))

    audit = store.entry("e1")["audit_log"]
    assert [event["action"] for event in audit] == [
        "reading_added",
        "wellbeing_added",
        "entry_voided",
        "entry_voided",
        "entry_restored",
        "entry_restored",
    ]
    assert [event["kind"] for event in audit] == [
        "readings",
        "wellbeing",
        "readings",
        "wellbeing",
        "readings",
        "wellbeing",
    ]
    assert audit[0]["details"] == {"src": "button"}
    assert audit[1]["details"] == {"key": "good"}


def test_audit_log_cap_prunes_oldest_with_summary(mock_store_fixture):
    """[REQ-HOM-115] Cap 3 hält höchstens 3 Events inkl. audit_pruned-Summary."""
    store, _ = mock_store_fixture
    _async_test(store.async_load())

    for index in range(5):
        _async_test(
            store.add_drink(
                "e1",
                f"2026-09-05T1{index}:00:00Z",
                250,
                "Wasser",
                "button",
                audit_limit=3,
            )
        )

    audit = store.entry("e1")["audit_log"]
    assert len(audit) == 3
    assert audit[-1]["action"] == "audit_pruned"
    assert audit[-1]["kind"] == "audit"
    assert audit[-1]["details"]["pruned"] >= 1
    assert isinstance(audit[-1]["details"]["oldest_retained"], str)
    assert _actions(store).count("audit_pruned") == 1


def test_audit_log_cap_zero_means_unlimited(mock_store_fixture):
    """[REQ-HOM-115] audit_limit=0 = unbegrenzt (kein Pruning)."""
    store, _ = mock_store_fixture
    _async_test(store.async_load())

    for index in range(5):
        _async_test(
            store.add_drink(
                "e1",
                f"2026-09-05T1{index}:00:00Z",
                250,
                "Wasser",
                "button",
                audit_limit=0,
            )
        )

    audit = store.entry("e1")["audit_log"]
    assert len(audit) == 5
    assert _actions(store) == ["drink_added"] * 5


def test_audit_log_cap_one_keeps_newest_event(mock_store_fixture):
    """[REQ-HOM-115] Sehr kleines Limit (<2) bleibt defensiv beim neuesten Event."""
    store, _ = mock_store_fixture
    _async_test(store.async_load())

    _async_test(
        store.add_drink("e1", "2026-09-05T10:00:00Z", 250, "Wasser", "button", audit_limit=1)
    )
    _async_test(
        store.add_drink("e1", "2026-09-05T11:00:00Z", 500, "Kaffee", "button", audit_limit=1)
    )

    audit = store.entry("e1")["audit_log"]
    assert len(audit) == 1
    assert audit[0]["action"] == "drink_added"
    assert audit[0]["details"] == {"ml": 500}


def test_audit_log_default_cap_from_const(mock_store_fixture):
    """[REQ-HOM-115] Default-Cap ist der Konstantenwert (1000)."""
    store, _ = mock_store_fixture
    _async_test(store.async_load())

    _async_test(store.add_drink("e1", "2026-09-05T10:00:00Z", 250, "Wasser", "button"))

    assert len(store.entry("e1")["audit_log"]) == 1
    assert store_module.DEFAULT_AUDIT_LIMIT == 1000


# ============================================================================
# v4-Felder beim Anlegen (IDs, created_at, Void-Felder)
# ============================================================================
def test_add_drink_sets_v4_fields(mock_store_fixture):
    """[REQ-HOM-115] add_drink setzt id/created_at/void-Felder (ts bleibt separat)."""
    store, _ = mock_store_fixture
    _async_test(store.async_load())

    _async_test(
        store.add_drink(
            "e1",
            "2026-09-01T00:00:00Z",
            250,
            "Wasser",
            "button",
            created_ts_iso="2026-09-05T10:00:00Z",
        )
    )

    drink = store.entry("e1")["drinks"][0]
    assert drink["ts"] == "2026-09-01T00:00:00Z"  # Messzeit (rückdatiert)
    assert drink["created_at"] == "2026-09-05T10:00:00Z"  # Erfassungszeit
    assert isinstance(drink["id"], str) and drink["id"]
    assert drink["voided_at"] is None
    assert drink["voided_by"] is None
    assert drink["void_reason"] is None


def test_add_reading_and_set_wellbeing_set_v4_fields(mock_store_fixture):
    """[REQ-HOM-115] add_reading/set_wellbeing setzen id/created_at/void-Felder."""
    store, _ = mock_store_fixture
    _async_test(store.async_load())

    _async_test(store.add_reading("e1", "2026-09-05T10:00:00Z", 120, 80, 70))
    _async_test(store.set_wellbeing("e1", "good", "2026-09-05T11:00:00Z"))

    reading = store.entry("e1")["readings"][0]
    wellbeing = store.entry("e1")["wellbeing_entries"][0]
    for item in (reading, wellbeing):
        assert isinstance(item["id"], str) and item["id"]
        assert isinstance(item["created_at"], str) and item["created_at"]
        assert item["voided_at"] is None
        assert item["voided_by"] is None
        assert item["void_reason"] is None
    assert reading["id"] != wellbeing["id"]


# ============================================================================
# M2a: aktive Sicht (active_entry/active_entries)
# ============================================================================


def _void_all(store, entry_id, kind):
    for item in list(store.entry(entry_id)[kind]):
        if kind == "drinks":
            _async_test(store.void_drink(entry_id, item["id"]))
        elif kind == "readings":
            _async_test(store.void_reading(entry_id, item["id"]))
        else:
            _async_test(store.void_wellbeing(entry_id, item["id"]))


def test_active_entry_filters_voided_lists_and_rebuilds_wellbeing(mock_store_fixture):
    """[M2a] active_entry liefert nur aktive Einträge + aktive Wellbeing-Spiegel."""
    store, _ = mock_store_fixture
    _async_test(store.async_load())
    _async_test(store.add_drink("e1", "2026-10-14T08:00:00", 250, "Wasser", "button"))
    _async_test(store.add_drink("e1", "2026-10-14T09:00:00", 500, "Kaffee", "button"))
    _async_test(store.add_reading("e1", "2026-10-14T09:00:00", 120, 80, 60))
    _async_test(store.add_reading("e1", "2026-10-14T10:00:00", 180, 110, 90))
    _async_test(store.set_wellbeing("e1", "good", "2026-10-14T08:00:00"))
    _async_test(store.set_wellbeing("e1", "bad", "2026-10-14T09:00:00"))
    _async_test(store.set_wellbeing("e1", "great", "2026-10-14T10:00:00"))

    raw = store.entry("e1")
    _async_test(store.void_drink("e1", raw["drinks"][1]["id"]))
    _async_test(store.void_reading("e1", raw["readings"][1]["id"]))
    _async_test(store.void_wellbeing("e1", raw["wellbeing_entries"][2]["id"]))

    view = store.active_entry("e1")

    assert [d["type"] for d in view["drinks"]] == ["Wasser"]
    assert [r["sys"] for r in view["readings"]] == [120]
    assert [e["key"] for e in view["wellbeing_entries"]] == ["good", "bad"]
    assert view["wellbeing"] == {"status": "bad", "ts": "2026-10-14T09:00:00"}
    assert view["wellbeing_history"] == [{"ts": "2026-10-14T08:00:00", "status": "good"}]


def test_active_entry_leaves_raw_data_untouched(mock_store_fixture):
    """[M2a] entry()/all_entries() bleiben roh; active_entry verändert nichts."""
    store, _ = mock_store_fixture
    _async_test(store.async_load())
    _async_test(store.add_drink("e1", "2026-10-14T08:00:00", 250, "Wasser", "button"))
    _async_test(store.add_drink("e1", "2026-10-14T09:00:00", 500, "Kaffee", "button"))
    _async_test(store.void_drink("e1", store.entry("e1")["drinks"][1]["id"]))

    view = store.active_entry("e1")
    view["drinks"].clear()
    view["drinks"].append({"ts": "x", "ml": 1, "type": "Fake", "voided_at": None})

    raw = store.all_entries()["e1"]
    assert len(raw["drinks"]) == 2
    assert [d["ml"] for d in raw["drinks"]] == [250, 500]
    assert raw["drinks"][1]["voided_at"] is not None

    # Zweiter Aufruf liefert wieder die unveränderte aktive Sicht.
    assert [d["ml"] for d in store.active_entry("e1")["drinks"]] == [250]


def test_active_entry_carries_person_lifetime_inputs_counts_and_audit(mock_store_fixture):
    """[M2a] Nicht-Listen-Felder werden unverändert übernommen."""
    store, _ = mock_store_fixture
    _async_test(store.async_load())
    _async_test(store.set_person("e1", "Caro"))
    _async_test(store.add_drink("e1", "2026-10-14T08:00:00", 250, "Wasser", "button"))
    _async_test(store.add_drink("e1", "2026-10-14T09:00:00", 500, "Kaffee", "button"))
    _async_test(store.void_drink("e1", store.entry("e1")["drinks"][1]["id"]))
    _async_test(store.set_inputs("e1", "sys", 120))
    raw = store.entry("e1")
    raw["archived_counts"] = {"drinks": 3, "readings": 2}

    view = store.active_entry("e1")

    assert view["person"] == "Caro"
    assert view["total_ml_lifetime"] == 250  # korrigierte M1-Summe
    assert view["inputs"] == {"sys": 120}
    assert view["archived_counts"] == {"drinks": 3, "readings": 2}
    assert view["audit_log"] == raw["audit_log"]


def test_active_entry_unknown_person_returns_empty_without_creating(mock_store_fixture):
    """[M2a] Unbekannte Person: leeres Dict, kein Seiteneffekt im Store."""
    store, _ = mock_store_fixture
    _async_test(store.async_load())

    assert store.active_entry("unknown") == {}
    assert "unknown" not in store.all_entries()


def test_active_entries_returns_filtered_views_for_all_persons(mock_store_fixture):
    """[M2a] active_entries filtert je Person, Schlüssel bleiben erhalten."""
    store, _ = mock_store_fixture
    _async_test(store.async_load())
    _async_test(store.add_drink("e1", "2026-10-14T08:00:00", 250, "Wasser", "button"))
    _async_test(store.add_drink("e2", "2026-10-14T08:00:00", 300, "Kaffee", "button"))
    _async_test(store.add_drink("e2", "2026-10-14T09:00:00", 400, "Wasser", "button"))
    _async_test(store.void_drink("e2", store.entry("e2")["drinks"][0]["id"]))

    views = store.active_entries()

    assert set(views) == {"e1", "e2"}
    assert [d["ml"] for d in views["e1"]["drinks"]] == [250]
    assert [d["ml"] for d in views["e2"]["drinks"]] == [400]
    # Rohbestand bleibt vollständig (Schreibpfad/Backup/Diagnostics).
    assert len(store.entry("e2")["drinks"]) == 2


def test_active_entry_all_wellbeing_voided_leaves_empty_mirrors(mock_store_fixture):
    """[M2a] Alle Meldungen voided → leere Wellbeing-Spiegel in der aktiven Sicht."""
    store, _ = mock_store_fixture
    _async_test(store.async_load())
    _async_test(store.set_wellbeing("e1", "good", "2026-10-14T08:00:00"))
    _void_all(store, "e1", "wellbeing_entries")

    view = store.active_entry("e1")

    assert view["wellbeing_entries"] == []
    assert view["wellbeing"] == {}
    assert view["wellbeing_history"] == []

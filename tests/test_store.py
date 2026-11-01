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
from datetime import datetime, timedelta
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
def test_remove_last_drink_voids_entry(mock_store_fixture):
    """[STORE-005] remove_last_drink voidet den letzten Eintrag (kein Hard-Delete)."""
    store, _ = mock_store_fixture
    _async_test(store.async_load())

    entry_id = "person-1"

    # Add two drinks
    _async_test(store.add_drink(entry_id, "2026-09-05T10:00:00Z", 250, "water", "button"))
    _async_test(store.add_drink(entry_id, "2026-09-05T11:00:00Z", 500, "coffee", "manual"))

    entry = store.entry(entry_id)
    assert len(entry["drinks"]) == 2

    # Undo voidet den letzten Eintrag; die Rohliste behält ihn (Audit/Backup).
    success = _async_test(store.remove_last_drink(entry_id))

    assert success is True
    assert len(entry["drinks"]) == 2, "der voided Eintrag darf nicht hart entfernt werden"
    assert entry["drinks"][-1]["voided_at"] is not None
    assert [d["ml"] for d in store.active_drinks(entry_id)] == [250]


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
        {
            "id": "raw-1",
            "ts": "2026-09-05T12:00:00Z",
            "ml": 500,
            "type": "juice",
            "src": "button",
            "voided_at": None,
        }
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

    # Add 101 wellbeing updates (chronologisch aufsteigend — die Reihenfolge
    # der Meldungen ist seit REQ-HOM-120 der `ts`, nicht die Erfassungsfolge).
    base = datetime(2026, 9, 5, 0, 0)
    for i in range(101):
        status = f"status-{i}"
        ts = (base + timedelta(minutes=i)).isoformat()
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
def test_remove_last_reading_voids_last_active_reading(mock_store_fixture):
    """[N-7] remove_last_reading voidet die letzte aktive Messung (kein Pop)."""
    store, _ = mock_store_fixture
    _async_test(store.async_load())

    _async_test(store.add_reading("person-1", "2026-09-05T10:00:00Z", 120, 80, 70))
    _async_test(store.add_reading("person-1", "2026-09-05T11:00:00Z", 130, 85, 75))

    success = _async_test(store.remove_last_reading("person-1"))

    assert success is True
    readings = store.entry("person-1")["readings"]
    assert len(readings) == 2, "der voided Eintrag bleibt in der Rohliste"
    assert readings[-1]["voided_at"] is not None
    assert [r["sys"] for r in store.active_readings("person-1")] == [120]


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


def test_apply_retention_rolls_back_in_memory_on_save_failure(mock_store_fixture):
    """[S-5] Save-Fehler lässt den RAM-Stand unverändert (kein stiller Verlust)."""
    store, backend = mock_store_fixture
    _async_test(store.async_load())

    entry = store.entry("person-1")
    old_drink = {"ts": "2025-01-01T00:00:00", "ml": 250, "type": "water", "src": "button"}
    new_drink = {"ts": "2026-09-01T00:00:00", "ml": 500, "type": "water", "src": "button"}
    old_reading = {"ts": "2025-01-01T00:00:00", "sys": 120, "dia": 80}
    entry["drinks"] = [old_drink, new_drink]
    entry["readings"] = [old_reading]
    entry["archived_counts"] = {"drinks": 3, "readings": 2}
    before = copy.deepcopy(entry)

    backend.async_save = AsyncMock(side_effect=RuntimeError("save failed"))
    with pytest.raises(RuntimeError, match="save failed"):
        _async_test(store.apply_retention("person-1", [new_drink], []))

    # Unveränderte Listen UND unveränderte Zähler (kein gekürzter RAM-Stand).
    assert store.raw_data()["entries"]["person-1"] == before
    assert store.raw_data()["entries"]["person-1"]["drinks"] == [old_drink, new_drink]
    assert store.raw_data()["entries"]["person-1"]["archived_counts"] == {
        "drinks": 3,
        "readings": 2,
    }

    # Ein erneuter Versuch ist nach dem Rollback wieder möglich.
    backend.async_save = AsyncMock()
    _async_test(store.apply_retention("person-1", [new_drink], []))
    current = store.raw_data()["entries"]["person-1"]
    assert current["drinks"] == [new_drink]
    assert current["readings"] == []
    assert current["archived_counts"] == {"drinks": 4, "readings": 3}


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
    assert store.raw_data() == {"schema": store_module.STORE_SCHEMA_VERSION, "entries": {}}


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

    assert store.raw_data()["schema"] == store_module.STORE_SCHEMA_VERSION
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
    assert second["schema"] == store_module.STORE_SCHEMA_VERSION
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
    assert audit[0]["details"] == {"src": "button"}
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
    assert audit[1]["details"] == {}


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
    assert audit[0]["details"] == {"src": "button"}


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


# ============================================================================
# M2b: Undo-Semantik (letzter AKTIVER Eintrag) + Wellbeing-Undo + Audit
# ============================================================================
def test_remove_last_drink_skips_already_voided_tail(mock_store_fixture):
    """[M2b] Undo voidet den letzten AKTIVEN Drink, nicht den voided Tail."""
    store, _ = mock_store_fixture
    _async_test(store.async_load())
    entry_id = "person-1"
    _async_test(store.add_drink(entry_id, "2026-10-14T08:00:00", 250, "Wasser", "button"))
    _async_test(store.add_drink(entry_id, "2026-10-14T09:00:00", 500, "Kaffee", "button"))
    last_id = store.entry(entry_id)["drinks"][-1]["id"]
    _async_test(store.remove_last_drink(entry_id))
    assert store.entry(entry_id)["total_ml_lifetime"] == 250

    # Zweites Undo: der Tail ist bereits voided → der erste Drink wird voided.
    assert _async_test(store.remove_last_drink(entry_id)) is True
    drinks = store.entry(entry_id)["drinks"]
    assert len(drinks) == 2, "kein Hard-Delete"
    assert drinks[1]["id"] == last_id
    assert all(d["voided_at"] for d in drinks)
    # Lifetime darf NICHT doppelt gekürzt werden (einmal pro voided Drink).
    assert store.entry(entry_id)["total_ml_lifetime"] == 0

    # Drittes Undo: kein aktiver Eintrag mehr → False, unverändert.
    assert _async_test(store.remove_last_drink(entry_id)) is False
    assert store.entry(entry_id)["total_ml_lifetime"] == 0


def test_remove_last_drink_audit_event_records_void(mock_store_fixture):
    """[M2b] Undo schreibt ein Audit-Ereignis (Akteur + Ziel-ID)."""
    store, _ = mock_store_fixture
    _async_test(store.async_load())
    _async_test(store.add_drink("person-1", "2026-10-14T08:00:00", 250, "Wasser", "button"))
    target_id = store.entry("person-1")["drinks"][0]["id"]

    _async_test(store.remove_last_drink("person-1", actor="user-7", audit_limit=50))

    audit = store.entry("person-1")["audit_log"]
    void_events = [event for event in audit if event["action"] == "entry_voided"]
    assert len(void_events) == 1
    assert void_events[0]["target_id"] == target_id
    assert void_events[0]["actor"] == "user-7"
    assert void_events[0]["kind"] == "drinks"


def test_remove_last_reading_skips_voided_tail(mock_store_fixture):
    """[M2b] BP-Undo voidet die letzte aktive Messung."""
    store, _ = mock_store_fixture
    _async_test(store.async_load())
    _async_test(store.add_reading("person-1", "2026-10-14T08:00:00", 120, 80, 60))
    first_id = store.entry("person-1")["readings"][0]["id"]
    _async_test(store.add_reading("person-1", "2026-10-14T09:00:00", 130, 85, 65))
    _async_test(store.void_reading("person-1", store.entry("person-1")["readings"][-1]["id"]))

    assert _async_test(store.remove_last_reading("person-1")) is True

    readings = store.entry("person-1")["readings"]
    assert len(readings) == 2
    assert readings[0]["id"] == first_id and readings[0]["voided_at"] is not None
    assert store.active_readings("person-1") == []
    assert _async_test(store.remove_last_reading("person-1")) is False


def test_remove_last_wellbeing_voids_last_active_event(mock_store_fixture):
    """[M2b] Wellbeing-Undo voidet die letzte aktive Meldung, Spiegel folgen."""
    store, _ = mock_store_fixture
    _async_test(store.async_load())
    _async_test(store.set_wellbeing("person-1", "good", "2026-10-14T08:00:00"))
    _async_test(store.set_wellbeing("person-1", "bad", "2026-10-14T09:00:00"))

    assert _async_test(store.remove_last_wellbeing("person-1", actor="user-1")) is True

    entry = store.entry("person-1")
    assert len(entry["wellbeing_entries"]) == 2, "kein Hard-Delete"
    assert entry["wellbeing_entries"][-1]["voided_at"] is not None
    assert store.current_wellbeing("person-1")["key"] == "good"
    assert entry["wellbeing"]["status"] == "good"
    assert _async_test(store.remove_last_wellbeing("person-1")) is True
    assert store.current_wellbeing("person-1") is None
    assert _async_test(store.remove_last_wellbeing("person-1")) is False


def test_last_active_helpers_ignore_voided_entries(mock_store_fixture):
    """[M2b] last_active_* liefert den letzten nicht-voided Eintrag."""
    store, _ = mock_store_fixture
    _async_test(store.async_load())
    _async_test(store.add_drink("person-1", "2026-10-14T08:00:00", 250, "Wasser", "button"))
    _async_test(store.add_reading("person-1", "2026-10-14T08:00:00", 120, 80, 60))
    _async_test(store.set_wellbeing("person-1", "okay", "2026-10-14T08:00:00"))
    _async_test(store.void_drink("person-1", store.entry("person-1")["drinks"][0]["id"]))

    assert store.last_active_drink("person-1") is None
    assert store.last_active_reading("person-1")["sys"] == 120
    assert store.last_active_wellbeing("person-1")["key"] == "okay"


# ============================================================================
# REQ-HOM-120: Rückdatierte Wohlbefinden-Meldungen
# ============================================================================


def test_req_hom_120_backdated_wellbeing_current_follows_ts_not_capture_order(
    mock_store_fixture,
):
    """[REQ-HOM-120] Aktueller Wert = zeitlich letzter, nicht zuletzt erfasst."""
    store, _ = mock_store_fixture
    _async_test(store.async_load())

    _async_test(store.set_wellbeing("e1", "good", "2026-10-14T08:00:00+02:00"))
    _async_test(store.set_wellbeing("e1", "great", "2026-10-14T09:00:00+02:00"))
    # Rückdatiert NACH der neuesten Meldung erfasst.
    _async_test(store.set_wellbeing("e1", "awful", "2026-10-14T07:00:00+02:00"))

    entry = store.entry("e1")
    assert entry["wellbeing"] == {"status": "great", "ts": "2026-10-14T09:00:00+02:00"}
    assert entry["wellbeing_history"] == [
        {"ts": "2026-10-14T07:00:00+02:00", "status": "awful"},
        {"ts": "2026-10-14T08:00:00+02:00", "status": "good"},
    ]
    assert [item["key"] for item in store.active_wellbeing_entries("e1")] == [
        "awful",
        "good",
        "great",
    ]
    assert store.current_wellbeing("e1")["key"] == "great"


def test_req_hom_120_wellbeing_sort_tiebreak_is_created_at_then_insertion(
    mock_store_fixture,
):
    """[REQ-HOM-120] Gleicher `ts`: `created_at`, danach Einfüge-Reihenfolge."""
    store, _ = mock_store_fixture
    _async_test(store.async_load())

    ts = "2026-10-14T08:00:00+02:00"
    _async_test(store.set_wellbeing("e1", "good", ts, created_ts_iso="2026-10-14T12:00:00+02:00"))
    _async_test(store.set_wellbeing("e1", "bad", ts, created_ts_iso="2026-10-14T12:05:00+02:00"))
    assert store.current_wellbeing("e1")["key"] == "bad"

    # Gleicher ts UND gleiches created_at: die spätere Erfassung gewinnt (stabil).
    _async_test(store.set_wellbeing("e1", "okay", ts, created_ts_iso="2026-10-14T12:05:00+02:00"))
    assert store.current_wellbeing("e1")["key"] == "okay"


def test_req_hom_120_remove_last_wellbeing_uses_capture_order(mock_store_fixture):
    """[REQ-HOM-120] Undo nimmt die zuletzt ERFASSTE Meldung, nicht den größten `ts`."""
    store, _ = mock_store_fixture
    _async_test(store.async_load())

    _async_test(store.set_wellbeing("e1", "good", "2026-10-14T09:00:00+02:00"))
    _async_test(store.set_wellbeing("e1", "awful", "2026-10-14T07:00:00+02:00"))

    assert store.current_wellbeing("e1")["key"] == "good"
    assert _async_test(store.remove_last_wellbeing("e1")) is True

    entry = store.entry("e1")
    assert entry["wellbeing_entries"][-1]["key"] == "awful"
    assert entry["wellbeing_entries"][-1]["voided_at"] is not None
    assert store.current_wellbeing("e1")["key"] == "good"
    assert entry["wellbeing_history"] == []

    assert _async_test(store.remove_last_wellbeing("e1")) is True
    assert store.current_wellbeing("e1") is None


def test_req_hom_120_legacy_mirrors_follow_chronology_after_rebuild(mock_store_fixture):
    """[REQ-HOM-120] `rebuild_wellbeing_mirrors` sortiert gemischte Roh-Reihenfolge."""
    store, _ = mock_store_fixture
    entry = {
        "wellbeing_entries": [
            {"key": "great", "ts": "2026-10-14T10:00:00+02:00", "created_at": None},
            {"key": "bad", "ts": "2026-10-14T08:00:00+02:00", "created_at": None},
            {"key": "good", "ts": "2026-10-14T09:00:00+02:00", "created_at": None},
        ]
    }

    store.rebuild_wellbeing_mirrors(entry)

    assert entry["wellbeing"] == {"status": "great", "ts": "2026-10-14T10:00:00+02:00"}
    assert [item["status"] for item in entry["wellbeing_history"]] == ["bad", "good"]


# --- Review-Fix S-9 ---------------------------------------------------------


def test_audit_details_store_metadata_only(mock_store_fixture):
    """[S-9] Audit-Details enthalten keine Gesundheitswerte (nur Metadaten)."""
    store, _ = mock_store_fixture
    _async_test(store.async_load())

    _async_test(store.add_drink("e1", "2026-09-05T10:00:00Z", 250, "Wasser", "button"))
    _async_test(store.set_wellbeing("e1", "good", "2026-09-05T11:00:00Z"))

    by_action = {event["action"]: event for event in store.entry("e1")["audit_log"]}
    assert by_action["drink_added"]["details"] == {"src": "button"}
    assert by_action["wellbeing_added"]["details"] == {}
    for event in by_action.values():
        assert "ml" not in event["details"]
        assert "key" not in event["details"]
        assert "sys" not in event["details"]
        assert "dia" not in event["details"]


# ============================================================================
# Laborwerte (REQ-HOM-122): Schema v5, Schreiben/Lesen
# ============================================================================


def test_req_hom_122_migrate_v4_to_v5_adds_empty_lab_readings():
    from custom_components.health_o_mat.store import migrate_store_data

    data = {"schema": 4, "entries": {"e1": {"drinks": [], "readings": []}}}
    migrated = migrate_store_data(data)
    assert migrated["entries"]["e1"]["lab_readings"] == []
    assert migrated["schema"] == 5


def test_req_hom_122_migrate_v4_to_v5_is_idempotent():
    from custom_components.health_o_mat.store import migrate_store_data

    data = {"schema": 4, "entries": {"e1": {"drinks": [], "readings": []}}}
    once = migrate_store_data(data)
    twice = migrate_store_data(once)
    assert twice["entries"]["e1"]["lab_readings"] == []


def test_req_hom_122_migrate_v4_to_v5_does_not_overwrite_existing_lab_readings():
    from custom_components.health_o_mat.store import migrate_store_data

    existing = [{"id": "x", "marker_key": "alt", "value": 1}]
    data = {
        "schema": 4,
        "entries": {"e1": {"drinks": [], "readings": [], "lab_readings": existing}},
    }
    migrated = migrate_store_data(data)
    assert migrated["entries"]["e1"]["lab_readings"] == existing


def test_req_hom_122_entry_defaults_include_empty_lab_readings(mock_store_fixture):
    store, _ = mock_store_fixture
    _async_test(store.async_load())
    entry = store.entry("e1")
    assert entry["lab_readings"] == []


def test_req_hom_122_add_lab_reading_stores_fields(mock_store_fixture):
    store, _ = mock_store_fixture
    _async_test(store.async_load())
    _async_test(
        store.add_lab_reading(
            "e1",
            "2026-10-31T09:00:00+01:00",
            "alt",
            32.0,
            "U/L",
            32.0,
            "U/L",
            report_ref="https://example.com/x",
        )
    )
    readings = store.entry("e1")["lab_readings"]
    assert len(readings) == 1
    reading = readings[0]
    assert reading["marker_key"] == "alt"
    assert reading["value"] == 32.0
    assert reading["unit"] == "U/L"
    assert reading["reported_value"] == 32.0
    assert reading["reported_unit"] == "U/L"
    assert reading["report_ref"] == "https://example.com/x"
    assert reading["voided_at"] is None
    assert "id" in reading and "created_at" in reading


def test_req_hom_122_active_lab_readings_filters_by_marker(mock_store_fixture):
    store, _ = mock_store_fixture
    _async_test(store.async_load())
    _async_test(store.add_lab_reading("e1", "t1", "alt", 1, "U/L", 1, "U/L"))
    _async_test(store.add_lab_reading("e1", "t2", "ast", 2, "U/L", 2, "U/L"))
    assert len(store.active_lab_readings("e1")) == 2
    assert len(store.active_lab_readings("e1", marker_key="alt")) == 1
    assert store.active_lab_readings("e1", marker_key="alt")[0]["marker_key"] == "alt"


def test_req_hom_122_last_active_lab_reading_returns_latest_for_marker(mock_store_fixture):
    store, _ = mock_store_fixture
    _async_test(store.async_load())
    _async_test(store.add_lab_reading("e1", "t1", "alt", 1, "U/L", 1, "U/L"))
    _async_test(store.add_lab_reading("e1", "t2", "alt", 2, "U/L", 2, "U/L"))
    last = store.last_active_lab_reading("e1", "alt")
    assert last["value"] == 2


def test_req_hom_122_last_active_lab_reading_none_when_no_reading(mock_store_fixture):
    store, _ = mock_store_fixture
    _async_test(store.async_load())
    assert store.last_active_lab_reading("e1", "alt") is None


# ============================================================================
# Laborwerte (REQ-HOM-122): Void/Restore/Undo
# ============================================================================


def test_req_hom_122_void_lab_reading_marks_voided(mock_store_fixture):
    store, _ = mock_store_fixture
    _async_test(store.async_load())
    _async_test(store.add_lab_reading("e1", "t1", "alt", 1, "U/L", 1, "U/L"))
    reading_id = store.entry("e1")["lab_readings"][0]["id"]
    changed = _async_test(store.void_lab_reading("e1", reading_id, reason="typo"))
    assert changed is True
    reading = store.entry("e1")["lab_readings"][0]
    assert reading["voided_at"] is not None
    assert reading["void_reason"] == "typo"
    assert store.active_lab_readings("e1") == []


def test_req_hom_122_void_lab_reading_unknown_id_returns_false(mock_store_fixture):
    store, _ = mock_store_fixture
    _async_test(store.async_load())
    changed = _async_test(store.void_lab_reading("e1", "nope"))
    assert changed is False


def test_req_hom_122_restore_lab_reading_clears_void_fields(mock_store_fixture):
    store, _ = mock_store_fixture
    _async_test(store.async_load())
    _async_test(store.add_lab_reading("e1", "t1", "alt", 1, "U/L", 1, "U/L"))
    reading_id = store.entry("e1")["lab_readings"][0]["id"]
    _async_test(store.void_lab_reading("e1", reading_id))
    changed = _async_test(store.restore_lab_reading("e1", reading_id))
    assert changed is True
    assert store.entry("e1")["lab_readings"][0]["voided_at"] is None


def test_req_hom_122_remove_last_lab_reading_voids_only_matching_marker(mock_store_fixture):
    store, _ = mock_store_fixture
    _async_test(store.async_load())
    _async_test(store.add_lab_reading("e1", "t1", "alt", 1, "U/L", 1, "U/L"))
    _async_test(store.add_lab_reading("e1", "t2", "ast", 2, "U/L", 2, "U/L"))
    changed = _async_test(store.remove_last_lab_reading("e1", "alt"))
    assert changed is True
    assert store.active_lab_readings("e1", marker_key="alt") == []
    assert len(store.active_lab_readings("e1", marker_key="ast")) == 1


def test_req_hom_122_remove_last_lab_reading_no_active_reading_returns_false(mock_store_fixture):
    store, _ = mock_store_fixture
    _async_test(store.async_load())
    changed = _async_test(store.remove_last_lab_reading("e1", "alt"))
    assert changed is False


# ============================================================================
# Laborwerte (REQ-HOM-122): Review-Fixes NB-1 (Zeitstempel) + NB-5 (aktive Sicht)
# ============================================================================


def _add_lab(store, ts: str, marker: str, value: float) -> None:
    """Kurzschreibweise für `add_lab_reading` (kanonische Einheit = U/L)."""
    _async_test(store.add_lab_reading("e1", ts, marker, value, "U/L", value, "U/L"))


def test_req_hom_122_nb1_last_active_lab_reading_uses_latest_ts(mock_store_fixture):
    """[NB-1] Nachgetragener älterer Befund überschreibt den aktuellen Wert nicht.

    Erfassungs-Reihenfolge: erst der NEUERE Befund (03.11.), dann der
    NACHGETRAGENE ältere (30.10.). "Aktuell" ist der neuere `ts`.
    """
    store, _ = mock_store_fixture
    _async_test(store.async_load())
    _add_lab(store, "2026-11-03T09:00:00+01:00", "alt", 40)
    _add_lab(store, "2026-10-30T09:00:00+01:00", "alt", 25)

    last = store.last_active_lab_reading("e1", "alt")

    assert last["value"] == 40
    assert last["ts"] == "2026-11-03T09:00:00+01:00"


def test_req_hom_122_nb1_last_active_lab_reading_handles_naive_and_aware_mixes(mock_store_fixture):
    """[NB-1] Naive und tz-aware `ts` sind vergleichbar (kein TypeError, korrekte Wahl)."""
    store, _ = mock_store_fixture
    _async_test(store.async_load())
    _add_lab(store, "2026-11-03T09:00:00", "alt", 40)
    _add_lab(store, "2026-10-30T09:00:00Z", "alt", 25)

    last = store.last_active_lab_reading("e1", "alt")

    assert last["value"] == 40


def test_req_hom_122_nb1_last_active_lab_reading_skips_voided_newest(mock_store_fixture):
    """[NB-1] Der neueste Wert ist voided → der davor liegende aktive gewinnt."""
    store, _ = mock_store_fixture
    _async_test(store.async_load())
    _add_lab(store, "2026-10-30T09:00:00+01:00", "alt", 25)
    _add_lab(store, "2026-11-03T09:00:00+01:00", "alt", 40)
    newest_id = store.active_lab_readings("e1", marker_key="alt")[1]["id"]
    _async_test(store.void_lab_reading("e1", newest_id))

    last = store.last_active_lab_reading("e1", "alt")

    assert last["value"] == 25


def test_req_hom_122_n6_last_active_lab_reading_tiebreak_is_last_inserted(mock_store_fixture):
    """[N-6] `max` statt `sorted()[-1]`: bei exakt gleichem ts/created_at gewinnt der
    zuletzt eingetragene Eintrag (Semantik der vorherigen Sortier-Variante)."""
    store, _ = mock_store_fixture
    _async_test(store.async_load())
    # Alt-/Migrationsbestand: der Schreibpfad lehnt gleiche (ts, marker_key)
    # inzwischen ab (#71/#72), historische Daten können sie aber enthalten.
    for index, value in enumerate((20.0, 30.0)):
        store.entry("e1")["lab_readings"].append(
            {
                "id": f"r{index}",
                "ts": "2026-11-03T09:00:00+01:00",
                "marker_key": "alt",
                "value": value,
                "unit": "U/L",
                "reported_value": value,
                "reported_unit": "U/L",
                "report_ref": None,
                "created_at": "2026-11-03T09:05:00+01:00",
                "voided_at": None,
                "voided_by": None,
                "void_reason": None,
            }
        )

    last = store.last_active_lab_reading("e1", "alt")

    assert last["value"] == 30.0


def test_req_hom_122_nb1_remove_last_lab_reading_voids_chronologically_newest(mock_store_fixture):
    """[NB-1] Undo trifft den zeitlich neuesten Wert, nicht den zuletzt erfassten."""
    store, _ = mock_store_fixture
    _async_test(store.async_load())
    _add_lab(store, "2026-11-03T09:00:00+01:00", "alt", 40)
    _add_lab(store, "2026-10-30T09:00:00+01:00", "alt", 25)

    changed = _async_test(store.remove_last_lab_reading("e1", "alt"))

    assert changed is True
    active = store.active_lab_readings("e1", marker_key="alt")
    assert [item["value"] for item in active] == [25.0]


def test_req_hom_122_nb5_active_entry_filters_voided_lab_readings(mock_store_fixture):
    """[NB-5] `active_entry()` verspricht 'ohne voided' — auch für `lab_readings`."""
    store, _ = mock_store_fixture
    _async_test(store.async_load())
    _add_lab(store, "2026-10-30T09:00:00+01:00", "alt", 25)
    _add_lab(store, "2026-11-03T09:00:00+01:00", "alt", 40)
    voided_id = store.entry("e1")["lab_readings"][0]["id"]
    _async_test(store.void_lab_reading("e1", voided_id))

    view = store.active_entry("e1")

    assert [item["value"] for item in view["lab_readings"]] == [40.0]
    # Rohbestand bleibt vollständig (Schreibpfad/Backup/Diagnostics).
    assert len(store.entry("e1")["lab_readings"]) == 2


# --- REQ-HOM-123: add_lab_readings ------------------------------------------


def _lab_rows(count: int = 2) -> list[dict]:
    return [
        {
            "marker_key": f"marker_{index}",
            "value": float(index + 1),
            "unit": "U/L",
            "reported_value": float(index + 1),
            "reported_unit": "U/L",
        }
        for index in range(count)
    ]


def test_req_hom_123_add_lab_readings_writes_all_rows_with_one_save(mock_store_fixture):
    store, mock_save = mock_store_fixture
    _async_test(store.async_load())

    ids = _async_test(
        store.add_lab_readings(
            "e1",
            "2026-11-01T09:15:00+01:00",
            _lab_rows(2),
            report_ref="https://example.com/1",
            created_ts_iso="2026-11-01T10:00:00+01:00",
        )
    )

    readings = store.entry("e1")["lab_readings"]
    assert [reading["marker_key"] for reading in readings] == ["marker_0", "marker_1"]
    assert all(reading["ts"] == "2026-11-01T09:15:00+01:00" for reading in readings)
    assert all(reading["report_ref"] == "https://example.com/1" for reading in readings)
    assert all(reading["created_at"] == "2026-11-01T10:00:00+01:00" for reading in readings)
    assert all(reading["voided_at"] is None for reading in readings)
    assert {reading["id"] for reading in readings} == set(ids)
    mock_save.async_save.assert_awaited_once()


def test_req_hom_123_add_lab_readings_writes_one_privacy_safe_audit_entry(mock_store_fixture):
    store, _mock_save = mock_store_fixture
    _async_test(store.async_load())

    ids = _async_test(
        store.add_lab_readings(
            "e1",
            "2026-11-01T09:15:00+01:00",
            _lab_rows(2),
            report_ref="Labor 10/2026",
            created_ts_iso="2026-11-01T10:00:00+01:00",
        )
    )

    audit = store.entry("e1")["audit_log"]
    assert len(audit) == 1
    assert audit[0]["action"] == "lab_values_added"
    assert audit[0]["kind"] == "lab_readings"
    assert audit[0]["target_id"] is None
    assert audit[0]["details"] == {
        "count": 2,
        "marker_keys": ["marker_0", "marker_1"],
        "reading_ids": ids,
        "created_at": "2026-11-01T10:00:00+01:00",
    }
    assert "report_ref" not in audit[0]["details"]
    assert "Labor 10/2026" not in repr(audit[0])


def test_req_hom_123_add_lab_readings_caps_details_lists_at_20(mock_store_fixture):
    store, _mock_save = mock_store_fixture
    _async_test(store.async_load())

    ids = _async_test(store.add_lab_readings("e1", "2026-11-01T09:15:00+01:00", _lab_rows(25)))

    details = store.entry("e1")["audit_log"][0]["details"]
    assert details["count"] == 25
    assert len(details["marker_keys"]) == 20
    assert len(details["reading_ids"]) == 20
    assert details["reading_ids"] == ids[:20]
    assert len(store.entry("e1")["lab_readings"]) == 25


def test_req_hom_123_add_lab_readings_rolls_back_on_save_error(mock_store_fixture, monkeypatch):
    store, _mock_save = mock_store_fixture
    _async_test(store.async_load())
    existing = {"id": "old-reading", "marker_key": "alt", "value": 32.0}
    store.entry("e1")["lab_readings"] = [existing]
    # Zwei Alt-Einträge + Limit 2: das Anhängen kappt den Ring (inkl.
    # `audit_pruned`-Summary). Ein Slice-Rollback würde das NICHT
    # wiederherstellen — der Test pinnt den deepcopy-Snapshot (§2.8).
    store.entry("e1")["audit_log"] = [
        {
            "id": "audit-1",
            "ts": "2026-10-01T08:00:00+02:00",
            "action": "lab_value_added",
            "kind": "lab_readings",
            "target_id": "old-reading",
            "actor": None,
            "details": {},
        },
        {
            "id": "audit-2",
            "ts": "2026-10-02T08:00:00+02:00",
            "action": "entry_voided",
            "kind": "lab_readings",
            "target_id": "old-reading",
            "actor": None,
            "details": {},
        },
    ]

    async def _fail_save() -> None:
        raise RuntimeError("disk full")

    monkeypatch.setattr(store, "_async_save", _fail_save)

    with pytest.raises(RuntimeError, match="disk full"):
        _async_test(
            store.add_lab_readings("e1", "2026-11-01T09:15:00+01:00", _lab_rows(2), audit_limit=2)
        )

    assert store.entry("e1")["lab_readings"] == [existing]
    assert [event["id"] for event in store.entry("e1")["audit_log"]] == [
        "audit-1",
        "audit-2",
    ]


# --- REQ-HOM-128/129: Batch-Undo + Retention --------------------------------


def _seed_lab(store, entry_id: str = "e1", **kwargs) -> None:
    _async_test(store.add_lab_readings(entry_id, **kwargs))


def test_req_hom_128_void_lab_report_voids_only_matching_instant(mock_store_fixture):
    store, mock_save = mock_store_fixture
    _async_test(store.async_load())
    store.entry("e1")["lab_readings"] = [
        {
            "id": "r1",
            "ts": "2026-11-01T09:15:00+01:00",
            "marker_key": "alt",
            "report_ref": "A",
            "voided_at": None,
        },
        {
            "id": "r2",
            "ts": "2026-11-01T08:15:00+00:00",
            "marker_key": "crp",
            "report_ref": "A",
            "voided_at": None,
        },
        {
            "id": "r3",
            "ts": "2026-10-01T09:15:00+01:00",
            "marker_key": "tsh",
            "report_ref": None,
            "voided_at": None,
        },
    ]

    voided = _async_test(store.void_lab_report("e1", "2026-11-01T09:15:00+01:00", report_ref="A"))

    assert voided == ["r1", "r2"]
    readings = {reading["id"]: reading for reading in store.entry("e1")["lab_readings"]}
    assert readings["r1"]["void_reason"] == "report_discarded"
    assert readings["r1"]["voided_at"] is not None
    assert readings["r2"]["voided_at"] is not None
    assert readings["r3"]["voided_at"] is None
    mock_save.async_save.assert_awaited_once()


def test_req_hom_128_void_lab_report_without_ref_voids_all_at_that_instant(mock_store_fixture):
    store, _mock_save = mock_store_fixture
    _async_test(store.async_load())
    store.entry("e1")["lab_readings"] = [
        {
            "id": "r1",
            "ts": "2026-11-01T09:15:00+01:00",
            "marker_key": "alt",
            "report_ref": "A",
            "voided_at": None,
        },
        {
            "id": "r2",
            "ts": "2026-11-01T09:15:00+01:00",
            "marker_key": "crp",
            "report_ref": None,
            "voided_at": None,
        },
    ]

    voided = _async_test(store.void_lab_report("e1", "2026-11-01T09:15:00+01:00"))

    assert voided == ["r1", "r2"]


def test_req_hom_128_void_lab_report_writes_one_audit_entry(mock_store_fixture):
    store, _mock_save = mock_store_fixture
    _async_test(store.async_load())
    store.entry("e1")["lab_readings"] = [
        {
            "id": "r1",
            "ts": "2026-11-01T09:15:00+01:00",
            "marker_key": "alt",
            "report_ref": "A",
            "voided_at": None,
        },
    ]

    _async_test(store.void_lab_report("e1", "2026-11-01T09:15:00+01:00", actor="u1"))

    audit = store.entry("e1")["audit_log"]
    assert len(audit) == 1
    assert audit[0]["action"] == "lab_report_voided"
    assert audit[0]["kind"] == "lab_readings"
    assert audit[0]["target_id"] is None
    assert audit[0]["actor"] == "u1"
    assert "report_ref" not in audit[0]["details"]
    assert audit[0]["details"]["count"] == 1
    assert audit[0]["details"]["reading_ids"] == ["r1"]
    assert audit[0]["details"]["created_at"]


def test_req_hom_128_void_lab_report_without_match_returns_empty_without_write(
    mock_store_fixture,
):
    store, mock_save = mock_store_fixture
    _async_test(store.async_load())
    store.entry("e1")["lab_readings"] = [
        {
            "id": "r1",
            "ts": "2026-10-01T09:15:00+01:00",
            "marker_key": "alt",
            "report_ref": None,
            "voided_at": None,
        },
    ]

    voided = _async_test(store.void_lab_report("e1", "2026-11-01T09:15:00+01:00"))

    assert voided == []
    assert store.entry("e1")["audit_log"] == []
    mock_save.async_save.assert_not_awaited()


def test_req_hom_128_void_lab_report_rolls_back_voided_fields_on_save_error(
    mock_store_fixture, monkeypatch
):
    store, _mock_save = mock_store_fixture
    _async_test(store.async_load())
    original = {
        "id": "r1",
        "ts": "2026-11-01T09:15:00+01:00",
        "marker_key": "alt",
        "report_ref": None,
        "voided_at": None,
        "voided_by": None,
        "void_reason": None,
    }
    store.entry("e1")["lab_readings"] = [copy.deepcopy(original)]

    async def _fail_save() -> None:
        raise RuntimeError("disk full")

    monkeypatch.setattr(store, "_async_save", _fail_save)

    with pytest.raises(RuntimeError, match="disk full"):
        _async_test(store.void_lab_report("e1", "2026-11-01T09:15:00+01:00"))

    assert store.entry("e1")["lab_readings"] == [original]
    assert store.entry("e1")["audit_log"] == []


def test_req_hom_129_void_lab_readings_before_voids_only_older_active(
    mock_store_fixture,
):
    store, mock_save = mock_store_fixture
    _async_test(store.async_load())
    store.entry("e1")["lab_readings"] = [
        {"id": "old", "ts": "2026-01-01T09:00:00+01:00", "marker_key": "alt", "voided_at": None},
        {"id": "new", "ts": "2026-10-01T09:00:00+02:00", "marker_key": "crp", "voided_at": None},
        {
            "id": "already",
            "ts": "2025-01-01T09:00:00+01:00",
            "marker_key": "tsh",
            "voided_at": "2026-02-01T00:00:00+01:00",
            "voided_by": None,
            "void_reason": None,
        },
    ]

    voided = _async_test(
        store.void_lab_readings_before("e1", "2026-09-01T00:00:00+02:00", months=12)
    )

    assert voided == ["old"]
    readings = {reading["id"]: reading for reading in store.entry("e1")["lab_readings"]}
    assert readings["old"]["void_reason"] == "retention"
    assert readings["new"]["voided_at"] is None
    assert readings["already"]["void_reason"] is None
    audit = store.entry("e1")["audit_log"]
    assert len(audit) == 1
    assert audit[0]["action"] == "lab_values_retention"
    assert audit[0]["details"]["count"] == 1
    assert audit[0]["details"]["months"] == 12
    assert audit[0]["details"]["cutoff"] == "2026-09-01T00:00:00+02:00"
    assert audit[0]["details"]["reading_ids"] == ["old"]
    mock_save.async_save.assert_awaited_once()


def test_req_hom_129_void_lab_readings_before_is_idempotent(mock_store_fixture):
    store, _mock_save = mock_store_fixture
    _async_test(store.async_load())
    store.entry("e1")["lab_readings"] = [
        {"id": "old", "ts": "2026-01-01T09:00:00+01:00", "marker_key": "alt", "voided_at": None},
    ]

    first = _async_test(
        store.void_lab_readings_before("e1", "2026-09-01T00:00:00+02:00", months=12)
    )
    second = _async_test(
        store.void_lab_readings_before("e1", "2026-09-01T00:00:00+02:00", months=12)
    )

    assert first == ["old"]
    assert second == []
    assert (
        len([e for e in store.entry("e1")["audit_log"] if e["action"] == "lab_values_retention"])
        == 1
    )


def test_req_hom_129_void_lab_readings_before_rolls_back_on_save_error(
    mock_store_fixture, monkeypatch
):
    store, _mock_save = mock_store_fixture
    _async_test(store.async_load())
    original = {
        "id": "old",
        "ts": "2026-01-01T09:00:00+01:00",
        "marker_key": "alt",
        "voided_at": None,
        "voided_by": None,
        "void_reason": None,
    }
    store.entry("e1")["lab_readings"] = [copy.deepcopy(original)]

    async def _fail_save() -> None:
        raise RuntimeError("disk full")

    monkeypatch.setattr(store, "_async_save", _fail_save)

    with pytest.raises(RuntimeError, match="disk full"):
        _async_test(store.void_lab_readings_before("e1", "2026-09-01T00:00:00+02:00", months=12))

    assert store.entry("e1")["lab_readings"] == [original]
    assert store.entry("e1")["audit_log"] == []


# --- #71/#72: kanonische Dedupe-Regel + Mehrgruppen-Save --------------------


def test_req_hom_122_add_lab_reading_rejects_same_ts_and_marker(mock_store_fixture):
    """[#72] Gleiches `(ts, marker_key)` — auch mit neuem Wert — ist ein Duplikat."""
    store, mock_save = mock_store_fixture
    _async_test(store.async_load())
    _async_test(
        store.add_lab_reading("e1", "2026-11-01T09:00:00+01:00", "alt", 32.0, "U/L", 32.0, "U/L")
    )
    mock_save.async_save.reset_mock()

    with pytest.raises(ValueError, match="duplicate_marker"):
        _async_test(
            store.add_lab_reading("e1", "2026-11-01T08:00:00Z", "alt", 99.0, "U/L", 99.0, "U/L")
        )

    assert [item["value"] for item in store.entry("e1")["lab_readings"]] == [32.0]
    assert len(store.entry("e1")["audit_log"]) == 1
    mock_save.async_save.assert_not_awaited()


def test_req_hom_122_add_lab_reading_duplicate_also_counts_voided(mock_store_fixture):
    """[#72] Auch ein voideter Wert blockiert denselben `(ts, marker_key)`."""
    store, _mock_save = mock_store_fixture
    _async_test(store.async_load())
    _async_test(store.add_lab_reading("e1", "2026-11-01T09:00:00", "alt", 32.0, "U/L", 32.0, "U/L"))
    _async_test(store.void_lab_reading("e1", store.entry("e1")["lab_readings"][0]["id"]))

    with pytest.raises(ValueError, match="duplicate_marker"):
        _async_test(
            store.add_lab_reading("e1", "2026-11-01T09:00:00", "alt", 33.0, "U/L", 33.0, "U/L")
        )


def test_req_hom_123_add_lab_readings_rejects_duplicate_report_without_partial_state(
    mock_store_fixture,
):
    """[#72] Bericht mit vorhandenem `(ts, marker_key)` → nichts geschrieben."""
    store, mock_save = mock_store_fixture
    _async_test(store.async_load())
    _async_test(store.add_lab_reading("e1", "2026-11-01T09:00:00", "alt", 32.0, "U/L", 32.0, "U/L"))
    mock_save.async_save.reset_mock()

    with pytest.raises(ValueError, match="duplicate_marker"):
        _async_test(
            store.add_lab_readings(
                "e1",
                "2026-11-01T09:00:00",
                [
                    {
                        "marker_key": "crp",
                        "value": 4.8,
                        "unit": "mg/L",
                        "reported_value": 4.8,
                        "reported_unit": "mg/L",
                    },
                    {
                        "marker_key": "alt",
                        "value": 99.0,
                        "unit": "U/L",
                        "reported_value": 99.0,
                        "reported_unit": "U/L",
                    },
                ],
            )
        )

    assert [item["marker_key"] for item in store.entry("e1")["lab_readings"]] == ["alt"]
    mock_save.async_save.assert_not_awaited()


def test_req_hom_123_add_lab_readings_bulk_writes_groups_with_one_save(
    mock_store_fixture,
):
    """[#72/O-3] N Gruppen → ein Save, ein Audit je Bericht, IDs in Reihenfolge."""
    store, mock_save = mock_store_fixture
    _async_test(store.async_load())

    ids = _async_test(
        store.add_lab_readings_bulk(
            "e1",
            [
                {
                    "ts_iso": "2026-11-01T09:00:00+01:00",
                    "report_ref": "Labor A",
                    "rows": _lab_rows(2),
                },
                {
                    "ts_iso": "2026-10-01T09:00:00+01:00",
                    "report_ref": None,
                    "rows": _lab_rows(1),
                },
            ],
            actor="user-1",
        )
    )

    readings = store.entry("e1")["lab_readings"]
    assert [item["marker_key"] for item in readings] == ["marker_0", "marker_1", "marker_0"]
    assert [item["id"] for item in readings] == ids
    assert readings[0]["report_ref"] == "Labor A"
    assert readings[2]["report_ref"] is None
    audit = store.entry("e1")["audit_log"]
    assert len(audit) == 2
    assert [event["details"]["count"] for event in audit] == [2, 1]
    mock_save.async_save.assert_awaited_once()


def test_req_hom_123_add_lab_readings_bulk_skips_duplicates_without_abort(
    mock_store_fixture,
):
    """[#72/O-3] Wiederholter Import schreibt nur fehlende Zeilen (kein Fehler)."""
    store, _mock_save = mock_store_fixture
    _async_test(store.async_load())
    _async_test(
        store.add_lab_readings_bulk(
            "e1",
            [
                {
                    "ts_iso": "2026-11-01T09:00:00+01:00",
                    "report_ref": None,
                    "rows": _lab_rows(2),
                }
            ],
        )
    )

    ids = _async_test(
        store.add_lab_readings_bulk(
            "e1",
            [
                {
                    "ts_iso": "2026-11-01T09:00:00+01:00",
                    "report_ref": None,
                    "rows": _lab_rows(4),  # 0/1 Duplikat, 2/3 neu
                }
            ],
        )
    )

    assert len(ids) == 2
    assert [item["marker_key"] for item in store.entry("e1")["lab_readings"]] == [
        "marker_0",
        "marker_1",
        "marker_2",
        "marker_3",
    ]


def test_req_hom_123_add_lab_readings_bulk_rolls_back_all_groups_on_save_error(
    mock_store_fixture, monkeypatch
):
    """[#72/O-3] Save-Fehler setzt In-Memory-Zustand über ALLE Gruppen zurück."""
    store, _mock_save = mock_store_fixture
    _async_test(store.async_load())
    existing = {"id": "old-reading", "marker_key": "alt", "value": 32.0}
    store.entry("e1")["lab_readings"] = [existing]
    store.entry("e1")["audit_log"] = [
        {
            "id": "audit-1",
            "ts": "2026-10-01T08:00:00+02:00",
            "action": "lab_value_added",
            "kind": "lab_readings",
            "target_id": "old-reading",
            "actor": None,
            "details": {},
        }
    ]

    async def _fail_save() -> None:
        raise RuntimeError("disk full")

    monkeypatch.setattr(store, "_async_save", _fail_save)

    with pytest.raises(RuntimeError, match="disk full"):
        _async_test(
            store.add_lab_readings_bulk(
                "e1",
                [
                    {"ts_iso": "2026-11-01T09:00:00", "report_ref": "A", "rows": _lab_rows(2)},
                    {"ts_iso": "2026-10-01T09:00:00", "report_ref": "B", "rows": _lab_rows(2)},
                ],
            )
        )

    assert store.entry("e1")["lab_readings"] == [existing]
    assert [event["id"] for event in store.entry("e1")["audit_log"]] == ["audit-1"]

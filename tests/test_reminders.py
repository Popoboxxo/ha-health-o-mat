"""Tests: Erinnerungen, Quiet Hours, Scheduler und Zustellung (REQ-HOM-118)."""

from __future__ import annotations

import asyncio
import importlib.util
import os
import sys
import types
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

_COMPONENT_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "custom_components", "health_o_mat")
)

_PKG = "_hom_reminders_test_pkg"
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


reminders = _load("reminders")
const = _load("const")

_DOMAIN = const.DOMAIN
_NOW = datetime(2026, 10, 26, 20, 0)  # Montag


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


class _FakeServices:
    """Minimal-Registry: sammelt Service-Aufrufe, kennt registrierte Notify-Ziele."""

    def __init__(self, notify: set[str] | None = None) -> None:
        self.known = {f"notify.{name}" for name in (notify or set())}
        self.calls: list[tuple[str, str, dict]] = []

    def has_service(self, domain: str, name: str) -> bool:
        return f"{domain}.{name}" in self.known

    async def async_call(self, domain, service, data, blocking=False) -> None:
        self.calls.append((domain, service, data))


def _hass(language: str = "de", notify: set[str] | None = None):
    hass = MagicMock()
    hass.data = {_DOMAIN: {}}
    hass.config.language = language
    hass.services = _FakeServices(notify)
    return hass


def _entry(entry_id: str = "e1", person: str = "Max", options: dict | None = None) -> MagicMock:
    entry = MagicMock()
    entry.entry_id = entry_id
    entry.data = {"person": person}
    entry.options = options if options is not None else {}
    return entry


class _Store:
    def __init__(self, data: dict | None = None) -> None:
        self._data = data if data is not None else {}

    def active_entry(self, entry_id: str) -> dict:
        assert entry_id == "e1"
        return dict(self._data)


def _reminders_options(**overrides) -> dict:
    options = {
        "enabled": True,
        "time": "20:00",
        "days": [0, 1, 2, 3, 4, 5, 6],
        "notify_service": "",
        "quiet_start": "",
        "quiet_end": "",
        "conditions": {
            "drink_goal": True,
            "no_drink_hours": 3,
            "bp_days": 0,
            "wellbeing_days": 0,
        },
    }
    options.update(overrides)
    return options


def _track(monkeypatch) -> list[dict]:
    """async_track_time_change durch einen Recorder ersetzen."""
    calls: list[dict] = []

    def _fake(hass, action, **kwargs):
        unsub = MagicMock(name=f"unsub-{len(calls)}")
        calls.append({"action": action, "kwargs": kwargs, "unsub": unsub})
        return unsub

    monkeypatch.setattr(reminders, "async_track_time_change", _fake)
    return calls


# --- Normalisierung ---------------------------------------------------------


def test_normalize_reminders_empty_is_all_off_with_defaults():
    result = reminders.normalize_reminders(None)

    assert result["enabled"] is False
    assert result["time"] == "20:00"
    assert result["days"] == [0, 1, 2, 3, 4, 5, 6]
    assert result["notify_service"] == ""
    assert result["quiet_start"] == result["quiet_end"] == ""
    assert result["conditions"] == {
        "drink_goal": True,
        "no_drink_hours": 3,
        "bp_days": 0,
        "wellbeing_days": 0,
    }


@pytest.mark.parametrize("raw", ["25:00", "20:60", "abc", "", None, "20", "20:00:99"])
def test_normalize_reminders_invalid_time_falls_back(raw):
    result = reminders.normalize_reminders({"time": raw})
    assert result["time"] == "20:00"


def test_normalize_reminders_accepts_time_selector_seconds():
    assert reminders.normalize_reminders({"time": "07:05:00"})["time"] == "07:05"


def test_normalize_reminders_days_filters_and_falls_back():
    assert reminders.normalize_reminders({"days": ["3", 1, 1, 9, "x", True]})["days"] == [1, 3]
    assert reminders.normalize_reminders({"days": []})["days"] == [0, 1, 2, 3, 4, 5, 6]
    assert reminders.normalize_reminders({"days": "mo"})["days"] == [0, 1, 2, 3, 4, 5, 6]


def test_normalize_reminders_boolean_strings_are_not_truthy():
    """Defensiv: "false"/"0" aus Fremd-JSON schalten nicht versehentlich ein."""
    result = reminders.normalize_reminders({"enabled": "false", "conditions": {"drink_goal": "0"}})

    assert result["enabled"] is False
    assert result["conditions"]["drink_goal"] is False
    assert reminders.normalize_reminders({"enabled": "true"})["enabled"] is True


def test_normalize_reminders_conditions_invalid_values_use_defaults():
    result = reminders.normalize_reminders(
        {
            "conditions": {
                "no_drink_hours": -2,
                "bp_days": 999,
                "wellbeing_days": -1,
            }
        }
    )

    assert result["conditions"]["no_drink_hours"] == 3
    assert result["conditions"]["bp_days"] == 0
    assert result["conditions"]["wellbeing_days"] == 0


def test_normalize_weekly_report_defaults_and_invalid_day():
    assert reminders.normalize_weekly_report(None) == {
        "enabled": False,
        "day": 0,
        "time": "18:00",
        "notify_service": "",
    }
    assert reminders.normalize_weekly_report({"day": 9, "time": "later"})["day"] == 0
    assert reminders.normalize_weekly_report({"day": 9, "time": "later"})["time"] == "18:00"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("mobile_app_phone", "mobile_app_phone"),
        ("notify.mobile_app_phone", "mobile_app_phone"),
        ("  notify.mobile_app_phone  ", "mobile_app_phone"),
        ("notify.", ""),
        ("", ""),
        (None, ""),
    ],
)
def test_normalize_notify_service(raw, expected):
    assert reminders.normalize_notify_service(raw) == expected


# --- Quiet Hours ------------------------------------------------------------


def _at(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 10, 26, hour, minute)


def test_quiet_hours_simple_window():
    assert reminders.in_quiet_hours(_at(13, 30), "13:00", "14:00") is True
    assert reminders.in_quiet_hours(_at(14, 0), "13:00", "14:00") is False
    assert reminders.in_quiet_hours(_at(12, 59), "13:00", "14:00") is False


def test_quiet_hours_midnight_rollover():
    assert reminders.in_quiet_hours(_at(23, 0), "22:00", "07:00") is True
    assert reminders.in_quiet_hours(_at(3, 0), "22:00", "07:00") is True
    assert reminders.in_quiet_hours(_at(7, 0), "22:00", "07:00") is False
    assert reminders.in_quiet_hours(_at(12, 0), "22:00", "07:00") is False


@pytest.mark.parametrize(
    ("start", "end"),
    [("", ""), ("22:00", ""), ("", "07:00"), ("22:00", "22:00")],
)
def test_quiet_hours_incomplete_or_empty_is_off(start, end):
    assert reminders.in_quiet_hours(_at(23, 0), start, end) is False


# --- Fälligkeit -------------------------------------------------------------


def _data() -> dict:
    return {
        "drinks": [
            {"ts": "2026-10-26T10:00:00", "ml": 250, "type": "Wasser"},
            {"ts": "2026-10-26T11:00:00", "ml": 250, "type": "Wasser", "voided_at": "x"},
        ],
        "readings": [],
        "wellbeing_entries": [],
    }


def test_reminder_due_disabled_returns_empty():
    options = {"reminders": _reminders_options(enabled=False)}
    assert reminders.reminder_due(_data(), options, _NOW) == []


def test_reminder_due_goal_and_no_drink():
    options = {"daily_goal_ml": 2000, "reminders": _reminders_options()}
    assert reminders.reminder_due(_data(), options, _NOW) == ["drink_goal", "no_drink"]


def test_reminder_due_goal_reached_and_recent_drink():
    data = _data()
    data["drinks"].append({"ts": "2026-10-26T19:30:00", "ml": 2000, "type": "Wasser"})
    options = {"daily_goal_ml": 2000, "reminders": _reminders_options()}
    assert reminders.reminder_due(data, options, _NOW) == []


def test_reminder_due_voided_drink_does_not_count():
    data = _data()
    data["drinks"].append({"ts": "2026-10-26T19:30:00", "ml": 2000, "type": "Wasser"})
    data["drinks"][-1]["voided_at"] = "2026-10-26T19:31:00"
    options = {"daily_goal_ml": 2000, "reminders": _reminders_options()}
    assert "drink_goal" in reminders.reminder_due(data, options, _NOW)


def test_reminder_due_bp_and_wellbeing_staleness():
    options = {
        "reminders": _reminders_options(
            conditions={
                "drink_goal": False,
                "no_drink_hours": 0,
                "bp_days": 7,
                "wellbeing_days": 7,
            }
        )
    }
    assert reminders.reminder_due(_data(), options, _NOW) == ["bp", "wellbeing"]

    data = _data()
    data["readings"] = [{"ts": "2026-10-25T08:00:00", "sys": 120, "dia": 80}]
    data["wellbeing_entries"] = [{"ts": "2026-10-25T09:00:00", "key": "good"}]
    assert reminders.reminder_due(data, options, _NOW) == []


def test_reminder_due_all_conditions_off_returns_empty():
    options = {
        "reminders": _reminders_options(
            conditions={
                "drink_goal": False,
                "no_drink_hours": 0,
                "bp_days": 0,
                "wellbeing_days": 0,
            }
        )
    }
    assert reminders.reminder_due(_data(), options, _NOW) == []


# --- Nachrichten ------------------------------------------------------------


def test_build_reminder_message_de_and_en():
    de = reminders.build_reminder_message(["drink_goal", "bp"], "Max", "de")
    en = reminders.build_reminder_message(["drink_goal", "bp"], "Max", "en")

    assert de.startswith("**Erinnerung für Max**")
    assert "Tagesziel" in de and "Blutdruck" in de
    assert "nichts getrunken" not in de
    assert en.startswith("**Reminder for Max**")
    assert "Daily drinking goal" in en and "Blood pressure" in en


def test_build_reminder_message_language_fallback_is_german():
    assert "Erinnerung" in reminders.build_reminder_message(["bp"], "Max", None)
    assert "Erinnerung" in reminders.build_reminder_message(["bp"], "Max", "")
    assert "Reminder" in reminders.build_reminder_message(["bp"], "Max", "en-GB")


def test_reminder_titles_per_language():
    assert reminders.reminder_title("de") == "Health-O-Mat Erinnerung"
    assert reminders.reminder_title("en") == "Health-O-Mat reminder"


# --- Scheduler --------------------------------------------------------------


def test_setup_registers_both_timers(monkeypatch):
    calls = _track(monkeypatch)
    hass = _hass()
    entry = _entry(
        options={
            "reminders": _reminders_options(),
            "weekly_report": {"enabled": True, "day": 0, "time": "18:00"},
        }
    )

    _run(reminders.async_setup_reminders(hass, entry, _Store()))

    assert len(calls) == 2
    assert calls[0]["kwargs"] == {"hour": 20, "minute": 0, "second": 0}
    assert calls[1]["kwargs"] == {"hour": 18, "minute": 0, "second": 0}
    assert hass.data[_DOMAIN]["e1"]["reminder_unsubs"] == [
        calls[0]["unsub"],
        calls[1]["unsub"],
    ]


def test_setup_disabled_registers_no_timer(monkeypatch):
    calls = _track(monkeypatch)
    hass = _hass()

    _run(reminders.async_setup_reminders(hass, _entry(options={}), _Store()))

    assert calls == []
    assert hass.data[_DOMAIN]["e1"]["reminder_unsubs"] == []


def test_setup_is_idempotent_and_cancels_previous_unsubs(monkeypatch):
    calls = _track(monkeypatch)
    hass = _hass()
    entry = _entry(options={"reminders": _reminders_options()})

    _run(reminders.async_setup_reminders(hass, entry, _Store()))
    first_unsub = calls[0]["unsub"]
    _run(reminders.async_setup_reminders(hass, entry, _Store()))

    first_unsub.assert_called_once()
    assert len(calls) == 2
    assert hass.data[_DOMAIN]["e1"]["reminder_unsubs"] == [calls[1]["unsub"]]


def test_setup_failure_never_raises(monkeypatch):
    def _boom(*args, **kwargs):
        raise RuntimeError("track kaputt")

    monkeypatch.setattr(reminders, "async_track_time_change", _boom)
    hass = _hass()
    entry = _entry(options={"reminders": _reminders_options()})

    _run(reminders.async_setup_reminders(hass, entry, _Store()))  # kein Raise

    assert "reminder_unsubs" not in hass.data[_DOMAIN]["e1"]


def test_unload_cancels_timers_and_clears_sent_state(monkeypatch):
    calls = _track(monkeypatch)
    hass = _hass()
    entry = _entry(options={"reminders": _reminders_options()})
    _run(reminders.async_setup_reminders(hass, entry, _Store()))
    hass.data[_DOMAIN]["e1"]["reminder_sent"] = {"drink_goal": "2026-10-26"}

    _run(reminders.async_unload_reminders(hass, "e1"))

    calls[0]["unsub"].assert_called_once()
    assert "reminder_unsubs" not in hass.data[_DOMAIN]["e1"]
    assert "reminder_sent" not in hass.data[_DOMAIN]["e1"]


def test_unload_unknown_entry_is_noop():
    hass = _hass()
    _run(reminders.async_unload_reminders(hass, "unbekannt"))  # kein Raise


# --- Zustellung -------------------------------------------------------------


def test_send_notification_prefers_configured_notify_service():
    hass = _hass(notify={"mobile_app_phone"})

    used = _run(reminders.async_send_notification(hass, "notify.mobile_app_phone", "T", "M"))

    assert used is True
    assert hass.services.calls == [("notify", "mobile_app_phone", {"title": "T", "message": "M"})]


def test_send_notification_falls_back_to_persistent():
    hass = _hass(notify=set())

    used = _run(reminders.async_send_notification(hass, "mobile_app_phone", "T", "M"))

    assert used is False
    assert hass.services.calls == [
        ("persistent_notification", "create", {"title": "T", "message": "M"})
    ]


def test_send_notification_empty_service_uses_persistent():
    hass = _hass()

    used = _run(reminders.async_send_notification(hass, "", "T", "M"))

    assert used is False
    assert hass.services.calls[0][0] == "persistent_notification"


def test_send_notification_failing_notify_falls_back():
    """Ein fehlschlagender Notify-Aufruf endet persistent, nicht in einem Fehler."""
    hass = _hass(notify={"mobile_app_phone"})
    calls: list[tuple[str, str, dict]] = []

    async def _call(domain, service, data, blocking=False):
        if domain == "notify":
            raise RuntimeError("Handy offline")
        calls.append((domain, service, data))

    hass.services.async_call = _call

    used = _run(reminders.async_send_notification(hass, "mobile_app_phone", "T", "M"))

    assert used is False
    assert calls == [("persistent_notification", "create", {"title": "T", "message": "M"})]


# --- Timer-Callbacks (Dedup, Wochentag, Quiet Hours) ------------------------


def _setup_with_timer(monkeypatch, options: dict, data: dict, *, language="de"):
    calls = _track(monkeypatch)
    hass = _hass(language=language)
    entry = _entry(options=options)
    _run(reminders.async_setup_reminders(hass, entry, _Store(data)))
    assert len(calls) == 1
    return hass, calls[0]["action"]


def test_callback_sends_one_bundled_notification(monkeypatch):
    hass, callback = _setup_with_timer(
        monkeypatch,
        {"daily_goal_ml": 2000, "reminders": _reminders_options()},
        _data(),
    )

    _run(callback(datetime(2026, 10, 26, 20, 0)))

    assert len(hass.services.calls) == 1
    _domain, _service, payload = hass.services.calls[0]
    assert "Tagesziel" in payload["message"]
    assert "nichts getrunken" in payload["message"]
    assert hass.data[_DOMAIN]["e1"]["reminder_sent"] == {
        "drink_goal": "2026-10-26",
        "no_drink": "2026-10-26",
    }


def test_callback_dedup_same_day(monkeypatch):
    hass, callback = _setup_with_timer(
        monkeypatch,
        {"daily_goal_ml": 2000, "reminders": _reminders_options()},
        _data(),
    )

    _run(callback(datetime(2026, 10, 26, 20, 0)))
    _run(callback(datetime(2026, 10, 26, 21, 0)))

    assert len(hass.services.calls) == 1


def test_callback_sends_again_next_day(monkeypatch):
    hass, callback = _setup_with_timer(
        monkeypatch,
        {"daily_goal_ml": 2000, "reminders": _reminders_options()},
        _data(),
    )

    _run(callback(datetime(2026, 10, 26, 20, 0)))
    _run(callback(datetime(2026, 10, 27, 20, 0)))

    assert len(hass.services.calls) == 2


def test_callback_skips_other_weekday(monkeypatch):
    hass, callback = _setup_with_timer(
        monkeypatch,
        {"daily_goal_ml": 2000, "reminders": _reminders_options(days=[1])},
        _data(),
    )

    _run(callback(datetime(2026, 10, 26, 20, 0)))  # Montag, days=[Dienstag]

    assert hass.services.calls == []


def test_callback_skips_quiet_hours(monkeypatch):
    hass, callback = _setup_with_timer(
        monkeypatch,
        {
            "daily_goal_ml": 2000,
            "reminders": _reminders_options(quiet_start="19:00", quiet_end="22:00"),
        },
        _data(),
    )

    _run(callback(datetime(2026, 10, 26, 20, 0)))

    assert hass.services.calls == []


def test_callback_uses_configured_notify_service_and_language(monkeypatch):
    calls = _track(monkeypatch)
    hass = _hass(language="en", notify={"mobile_app_phone"})
    entry = _entry(
        options={
            "daily_goal_ml": 2000,
            "reminders": _reminders_options(notify_service="notify.mobile_app_phone"),
        }
    )
    _run(reminders.async_setup_reminders(hass, entry, _Store(_data())))

    _run(calls[0]["action"](datetime(2026, 10, 26, 20, 0)))

    domain, service, payload = hass.services.calls[0]
    assert (domain, service) == ("notify", "mobile_app_phone")
    assert "Reminder for Max" in payload["message"]


def test_weekly_callback_sends_report_and_dedups(monkeypatch):
    calls = _track(monkeypatch)
    hass = _hass(language="de")
    entry = _entry(
        options={
            "weekly_report": {"enabled": True, "day": 0, "time": "18:00"},
            "daily_goal_ml": 2000,
        }
    )
    _run(reminders.async_setup_reminders(hass, entry, _Store(_data())))
    callback = calls[0]["action"]

    _run(callback(datetime(2026, 10, 26, 18, 0)))
    _run(callback(datetime(2026, 10, 26, 18, 0)))

    assert len(hass.services.calls) == 1
    payload = hass.services.calls[0][2]
    assert "Wochenbericht" in payload["title"]
    assert "## Wochenbericht" in payload["message"]
    assert hass.data[_DOMAIN]["e1"]["reminder_sent"]["weekly_report"] == "2026-10-26"


def test_weekly_callback_skips_other_weekday(monkeypatch):
    calls = _track(monkeypatch)
    hass = _hass()
    entry = _entry(options={"weekly_report": {"enabled": True, "day": 2, "time": "18:00"}})
    _run(reminders.async_setup_reminders(hass, entry, _Store(_data())))

    _run(calls[0]["action"](datetime(2026, 10, 26, 18, 0)))  # Montag statt Mittwoch

    assert hass.services.calls == []


def test_callback_error_is_swallowed(monkeypatch):
    calls = _track(monkeypatch)
    hass = _hass()
    entry = _entry(options={"reminders": _reminders_options()})

    class _BrokenStore:
        def active_entry(self, entry_id):
            raise RuntimeError("Store kaputt")

    _run(reminders.async_setup_reminders(hass, entry, _BrokenStore()))

    _run(calls[0]["action"](datetime(2026, 10, 26, 20, 0)))  # kein Raise

    assert hass.services.calls == []


# --- Verdrahtung in __init__.py ---------------------------------------------


def _load_init_module():
    for name in ("store", "entity", "const", "parser", "logic", "exporter"):
        _load(name)
    spec = importlib.util.spec_from_file_location(
        f"{_PKG}.init", os.path.join(_COMPONENT_DIR, "__init__.py")
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[f"{_PKG}.init"] = module
    spec.loader.exec_module(module)
    return module


def test_setup_entry_sets_up_reminders(monkeypatch):
    """async_setup_entry verdrahtet den Scheduler (REQ-HOM-118)."""
    init = _load_init_module()
    calls: list[tuple] = []

    async def _setup(hass, entry, store):
        calls.append((hass, entry, store))

    class _Coordinator:
        def __init__(self, *args, **kwargs):
            pass

    store = MagicMock()
    store.set_person = _async_noop
    hass = MagicMock()
    hass.data = {_DOMAIN: {"shared": {"store": store}}}
    hass.config_entries.async_forward_entry_setups = _async_noop
    entry = _entry()
    entry.async_on_unload = MagicMock()
    entry.add_update_listener = MagicMock(return_value=MagicMock())

    monkeypatch.setattr(init, "async_setup_reminders", _setup)
    monkeypatch.setattr(init, "DataUpdateCoordinator", _Coordinator)
    monkeypatch.setattr(init, "_async_migrate_recorder_statistics", _async_noop)
    monkeypatch.setattr(init, "_register_services", lambda hass: None)
    monkeypatch.setattr(init, "_async_setup_frontend_layer", _async_noop)
    monkeypatch.setattr(init, "_async_apply_panel_layer", _async_noop)
    monkeypatch.setattr(init, "_apply_retention", _async_noop)

    assert _run(init.async_setup_entry(hass, entry)) is True
    assert calls == [(hass, entry, store)]


def test_options_updated_rearms_reminders(monkeypatch):
    """Options-Änderung setzt die Timer neu auf (idempotenter Pfad)."""
    init = _load_init_module()
    store = MagicMock()
    store.all_entries.return_value = {"e1": {"person": "Max", "total_ml_lifetime": 0}}
    hass = MagicMock()
    hass.data = {_DOMAIN: {"shared": {"store": store}, "e1": {"coordinator": MagicMock()}}}
    entry = _entry(options={})
    entry.runtime_data = init.HealthOMatData()
    calls: list[str] = []

    async def _setup(hass, entry, store):
        calls.append("setup")

    monkeypatch.setattr(init, "async_setup_reminders", _setup)
    monkeypatch.setattr(init, "_async_apply_panel_layer", _async_noop)
    monkeypatch.setattr(init, "_apply_retention", _async_noop)

    _run(init._options_updated(hass, entry))

    assert calls == ["setup"]


def test_unload_entry_tears_down_reminders(monkeypatch):
    """async_unload_entry meldet die Timer ab, bevor die Registry geleert wird."""
    init = _load_init_module()
    hass = MagicMock()
    hass.data = {_DOMAIN: {"e1": {"coordinator": MagicMock()}, "shared": {}}}
    hass.config_entries.async_unload_platforms = _async_noop_true
    entry = _entry()

    unload = AsyncMock()
    monkeypatch.setattr(init, "async_unload_reminders", unload)
    monkeypatch.setattr(init, "_async_apply_panel_layer", _async_noop)
    monkeypatch.setattr(init, "async_unregister_frontend", _async_noop)

    assert _run(init.async_unload_entry(hass, entry)) is True
    unload.assert_awaited_once_with(hass, "e1")


async def _async_noop(*args, **kwargs):
    return None


async def _async_noop_true(*args, **kwargs):
    return True


# --- Review-Fix S-3 ---------------------------------------------------------


def test_send_notification_awaits_handler_and_falls_back_on_async_error():
    """[S-3] `blocking=True` lässt Handler-Fehler ankommen → persistent-Fallback."""
    hass = _hass(notify={"mobile_app_phone"})
    calls: list[tuple[str, str, bool]] = []

    async def _call(domain, service, data, blocking=False):
        calls.append((domain, service, blocking))
        if domain == "notify":
            raise RuntimeError("Handy offline")

    hass.services.async_call = _call

    used = _run(reminders.async_send_notification(hass, "mobile_app_phone", "T", "M"))

    assert used is False
    assert calls[0] == ("notify", "mobile_app_phone", True)
    assert calls[-1][0] == "persistent_notification"

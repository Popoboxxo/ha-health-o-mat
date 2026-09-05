"""Tests: Tagesfenster, Summen und CSV (reine Logik)."""
import importlib.util
import os
import sys
import types
from datetime import datetime

_COMPONENT_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "custom_components", "health_o_mat")
)

# Fake-Paket (wie in test_parser.py), damit relative Imports funktionieren
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


logic = _load("logic")


def test_day_start_midnight():
    now = datetime(2026, 8, 22, 15, 30)
    assert logic.day_start(now) == datetime(2026, 8, 22, 0, 0)


def test_day_start_before_boundary():
    # 01:00 nachts mit 22:00-Grenze → Tag begann gestern 22:00
    now = datetime(2026, 8, 22, 1, 0)
    start = logic.day_start(now, hour=22)
    assert start == datetime(2026, 8, 21, 22, 0)


def test_day_start_4am():
    now = datetime(2026, 8, 22, 3, 59)
    assert logic.day_start(now, hour=4) == datetime(2026, 8, 21, 4, 0)


DRINKS = [
    {"ts": "2026-08-22T07:41:00", "ml": 250, "type": "Kaffee"},
    {"ts": "2026-08-22T12:10:00", "ml": 500, "type": "Wasser"},
    {"ts": "2026-08-21T20:00:00", "ml": 200, "type": "Wasser"},
    {"ts": "kaputt", "ml": 999},
]


def test_window_sums_today():
    sums = logic.window_sums(DRINKS, datetime(2026, 8, 22, 0, 0), datetime(2026, 8, 22, 23, 59))
    assert sums["total_ml"] == 750
    assert sums["count"] == 2
    assert sums["breakdown"] == {"Kaffee": 250, "Wasser": 500}
    assert sums["last_ts"] == "2026-08-22T12:10:00"


def test_window_sums_yesterday_only():
    sums = logic.window_sums(DRINKS, datetime(2026, 8, 21, 0, 0), datetime(2026, 8, 22, 0, 0))
    assert sums["total_ml"] == 200


def test_csv_rows():
    rows = logic.drinks_csv_rows(DRINKS[:2], "Caro")
    assert rows[0] == ["datum", "uhrzeit", "person", "getraenk", "menge_ml", "quelle"]
    assert rows[1][2] == "Caro" and rows[1][4] == "250"
    csv_text = logic.rows_to_csv_string(rows)
    assert ";" in csv_text


def test_filename():
    name = logic.csv_filename("drinks", "Caro", datetime(2026, 8, 22, 18, 5))
    assert name == "health_o_mat_drinks_Caro_20260822-1805.csv"


def test_today_sums_matches_window_sums():
    now = datetime(2026, 8, 22, 23, 0)
    expected = logic.window_sums(DRINKS, logic.day_start(now), now)
    assert logic.today_sums(DRINKS, now) == expected
    assert logic.today_sums(DRINKS, now)["total_ml"] == 750


def test_yesterday_window():
    now = datetime(2026, 8, 22, 23, 0)
    s, e = logic.yesterday_window(now)
    assert s == datetime(2026, 8, 21, 0, 0) and e == datetime(2026, 8, 22, 0, 0)


READINGS = [
    {"ts": "2026-08-22T08:00:00", "sys": 120, "dia": 80, "pulse": 70},
    {"ts": "2026-08-16T08:00:00", "sys": 130, "dia": 85, "pulse": 72},  # exactly 7 days before "today"
    {"ts": "2026-08-10T08:00:00", "sys": 999, "dia": 999, "pulse": 999},  # outside window, must be excluded
    {"ts": "2026-08-20T08:00:00", "sys": 110, "dia": None, "pulse": None},  # None value for dia/pulse
    {"ts": "kaputt", "sys": 500, "dia": 500, "pulse": 500},  # invalid ts, must be excluded
]


def test_avg_over_window_basic():
    now = datetime(2026, 8, 23, 8, 0)
    avg = logic.avg_over_window(READINGS, "sys", now)
    # within [now-7d, now]: 120 (22.), 130 (16., exactly at boundary), 110 (20.)
    assert avg == (120 + 130 + 110) / 3


def test_avg_over_window_excludes_outside_range():
    now = datetime(2026, 8, 23, 8, 0)
    avg = logic.avg_over_window(READINGS, "sys", now)
    assert avg != 999
    # sanity: the outlier reading from 08-10 is more than 7 days before "now"
    assert (now - datetime(2026, 8, 10, 8, 0)).days > 7


def test_avg_over_window_skips_none_values():
    now = datetime(2026, 8, 23, 8, 0)
    avg = logic.avg_over_window(READINGS, "dia", now)
    # only 2026-08-22 (80) and 2026-08-16 (85) have a non-None dia in window
    assert avg == (80 + 85) / 2


def test_avg_over_window_empty_when_no_readings_in_range():
    now = datetime(2026, 8, 23, 8, 0)
    assert logic.avg_over_window([], "sys", now) is None
    only_old = [{"ts": "2020-01-01T00:00:00", "sys": 120}]
    assert logic.avg_over_window(only_old, "sys", now) is None


def test_avg_over_window_custom_days():
    now = datetime(2026, 8, 23, 8, 0)
    # with days=1, only the 08-22 reading qualifies
    avg = logic.avg_over_window(READINGS, "sys", now, days=1)
    assert avg == 120

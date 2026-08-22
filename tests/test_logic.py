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


def test_yesterday_window():
    now = datetime(2026, 8, 22, 23, 0)
    s, e = logic.yesterday_window(now)
    assert s == datetime(2026, 8, 21, 0, 0) and e == datetime(2026, 8, 22, 0, 0)

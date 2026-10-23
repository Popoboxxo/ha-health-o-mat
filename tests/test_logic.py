"""Tests: Tagesfenster, Summen und CSV (reine Logik)."""

import importlib.util
import os
import re
import sys
import types
from datetime import UTC, datetime, timedelta, timezone

import pytest

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
const = _load("const")


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


# --- Konfigurierbare Reset-Uhrzeit (daily_reset_hour) ---


def test_today_sums_with_custom_hour_shifts_window():
    # 05:00-Buchung zählt bei hour=6 noch zum Vortag (Fenster beginnt erst 06:00).
    drinks = [{"ts": "2026-08-22T05:00:00", "ml": 300, "type": "Kaffee"}]
    now = datetime(2026, 8, 22, 8, 0)
    assert logic.today_sums(drinks, now, hour=6)["total_ml"] == 0
    assert logic.today_sums(drinks, now, hour=0)["total_ml"] == 300


def test_yesterday_window_with_custom_hour_matches_today_sums_boundary():
    # yesterday_window(now, hour=h) und today_sums(..., hour=h) müssen dieselbe
    # Tagesgrenze verwenden — sonst wird ein Getränk doppelt oder gar nicht gezählt.
    now = datetime(2026, 8, 22, 8, 0)
    hour = 6
    y_start, y_end = logic.yesterday_window(now, hour=hour)
    assert y_end == logic.day_start(now, hour=hour)
    drinks = [{"ts": "2026-08-22T05:00:00", "ml": 300, "type": "Kaffee"}]
    yesterday_sums = logic.window_sums(drinks, y_start, y_end)
    today_sums = logic.today_sums(drinks, now, hour=hour)
    assert yesterday_sums["total_ml"] == 300
    assert today_sums["total_ml"] == 0


READINGS = [
    {"ts": "2026-08-22T08:00:00", "sys": 120, "dia": 80, "pulse": 70},
    {
        "ts": "2026-08-16T08:00:00",
        "sys": 130,
        "dia": 85,
        "pulse": 72,
    },  # exactly 7 days before "today"
    {
        "ts": "2026-08-10T08:00:00",
        "sys": 999,
        "dia": 999,
        "pulse": 999,
    },  # outside window, must be excluded
    {
        "ts": "2026-08-20T08:00:00",
        "sys": 110,
        "dia": None,
        "pulse": None,
    },  # None value for dia/pulse
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


# --- Retention/Archiv (REQ-HOM-109, Finding N-2) ---


def test_months_ago_calendar_exact():
    """[REQ-HOM-109] X Kalendermonate zurück — kein 30-Tage-Approx."""
    assert logic.months_ago(datetime(2026, 10, 14), 6) == datetime(2026, 4, 14)
    assert logic.months_ago(datetime(2026, 10, 14), 1) == datetime(2026, 9, 14)


def test_months_ago_clamps_to_shorter_target_month():
    """[REQ-HOM-109] 31.03. minus 1 Monat → 28.02. (Tag wird geklemmt)."""
    assert logic.months_ago(datetime(2026, 3, 31), 1) == datetime(2026, 2, 28)
    # Schaltjahr: 31.03.2028 minus 1 Monat → 29.02.2028
    assert logic.months_ago(datetime(2028, 3, 31), 1) == datetime(2028, 2, 29)


def test_months_ago_year_rollover():
    """[REQ-HOM-109] Monatsarithmetik rollt korrekt über Jahresgrenzen."""
    assert logic.months_ago(datetime(2026, 1, 15), 1) == datetime(2025, 12, 15)
    assert logic.months_ago(datetime(2026, 1, 15), 13) == datetime(2024, 12, 15)


def test_months_ago_preserves_timezone():
    """[REQ-HOM-109] tz-aware `now` behält Zeitzone (DST-festes Fenster)."""
    tz = timezone(timedelta(hours=2))
    now = datetime(2026, 10, 14, 12, 30, tzinfo=tz)
    cutoff = logic.months_ago(now, 2)
    assert cutoff == datetime(2026, 8, 14, 12, 30, tzinfo=tz)
    assert cutoff.tzinfo is tz


def test_partition_by_cutoff_splits_old_and_recent():
    """[REQ-HOM-109] Einträge vor dem Stichtag ins Archiv, ab Stichtag bleiben."""
    cutoff = datetime(2026, 4, 14)
    items = [
        {"ts": "2026-04-13T23:59:59", "ml": 1},
        {"ts": "2026-04-14T00:00:00", "ml": 2},  # exakt Stichtag → bleibt
        {"ts": "2026-05-01T00:00:00", "ml": 3},
    ]
    recent, archived = logic.partition_by_cutoff(items, cutoff)
    assert [i["ml"] for i in archived] == [1]
    assert [i["ml"] for i in recent] == [2, 3]


def test_partition_by_cutoff_keeps_invalid_and_missing_ts():
    """[REQ-HOM-109] Unbekannte Daten werden NIE stillschweigend archiviert."""
    cutoff = datetime(2026, 4, 14)
    items = [{"ts": "kaputt"}, {"ml": 5}, {"ts": None}]
    recent, archived = logic.partition_by_cutoff(items, cutoff)
    assert archived == []
    assert recent == items


def test_partition_by_cutoff_mixes_naive_and_aware_without_typeerror():
    """[REQ-HOM-109] Alt-Bestand (naive ts) + new (aware) brechen nicht ab."""
    cutoff = datetime(2026, 4, 14, tzinfo=UTC)
    old = {"ts": "2026-01-01T00:00:00"}  # naive, älter → Archiv
    new = {"ts": "2026-10-14T00:00:00+00:00"}  # aware, neuer → bleibt
    recent, archived = logic.partition_by_cutoff([old, new], cutoff)
    assert archived == [old]
    assert recent == [new]


# --- WHO-Blutdruck-Klassifikation (REQ-HOM-001) ---


@pytest.mark.parametrize(
    ("sys", "dia", "expected"),
    [
        # Optimal / normal / hoch-normal an den exakten Grenzen
        (119, 79, "optimal"),
        (120, 79, "normal"),  # systolische Achse treibt
        (119, 80, "normal"),  # diastolische Achse treibt
        (129, 84, "normal"),
        (130, 84, "high_normal"),
        (129, 85, "high_normal"),
        (139, 89, "high_normal"),
        # Grad 1
        (140, 89, "grade_1"),
        (139, 90, "grade_1"),
        (159, 99, "grade_1"),
        # Grad 2
        (160, 99, "grade_2"),
        (159, 100, "grade_2"),
        (179, 109, "grade_2"),
        # Grad 3
        (180, 90, "grade_3"),  # isoliert systolisch
        (170, 110, "grade_3"),  # isoliert diastolisch
        (200, 90, "grade_3"),  # isoliert systolisch, KEINE Krise
        (170, 125, "grade_3"),  # diastolisch hoch, systolisch nicht >180
        # Hypertensive Krise nur wenn BEIDE streng überschritten
        (181, 121, "crisis"),
        (250, 130, "crisis"),
    ],
)
def test_bp_category_boundaries(sys: int, dia: int, expected: str) -> None:
    """[REQ-HOM-001] WHO-Kategorie inkl. Grenzwerte und "höherer Wert zählt"."""
    assert logic.bp_category(sys, dia) == expected


def test_bp_category_higher_axis_wins():
    """[REQ-HOM-001] Die höhere der beiden Achsen-Kategorien zählt."""
    assert logic.bp_category(110, 95) == "grade_1"  # sys optimal, dia Grad 1
    assert logic.bp_category(165, 70) == "grade_2"  # sys Grad 2, dia optimal
    assert logic.bp_category(130, 88) == "high_normal"


def test_bp_category_missing_values_return_none():
    """[REQ-HOM-001] Fehlender Wert → None (Sensor: unknown)."""
    assert logic.bp_category(None, 80) is None
    assert logic.bp_category(120, None) is None
    assert logic.bp_category(None, None) is None


def test_bp_category_pulse_independent_of_classification():
    """[REQ-HOM-001] Puls beeinflusst die Kategorie nicht."""
    assert logic.bp_category(120, 80) == "normal"


# --- Trend-Metriken (REQ-HOM-002) ---


def _daily_drinks(now: datetime, days_back: int, ml: int) -> list[dict]:
    """Drei Buchungen pro Tag für `days_back` volle Tage vor dem heutigen Start."""
    out: list[dict] = []
    start = logic.day_start(now)
    for day in range(1, days_back + 1):
        base = start - timedelta(days=day)
        for hour in (8, 12, 18):
            out.append(
                {"ts": (base + timedelta(hours=hour)).isoformat(), "ml": ml // 3, "type": "Wasser"}
            )
    return out


def test_drinks_trend_none_when_prev_week_average_zero():
    """[REQ-HOM-002] Vorwochen-Ø = 0 ⇒ keine sinnvolle Prozentänderung → None."""
    now = datetime(2026, 8, 8, 12, 0)
    today = [{"ts": "2026-08-08T09:00:00", "ml": 500, "type": "Wasser"}]
    assert logic.drinks_trend(today, now) is None
    assert logic.drinks_trend([], now) is None


def test_drinks_trend_positive_percent():
    """[REQ-HOM-002] Heute über dem Vorwochen-Ø ⇒ positives Prozent."""
    now = datetime(2026, 8, 8, 12, 0)
    drinks = _daily_drinks(now, 7, 1200)  # Ø 1200 ml/Tag
    drinks.append({"ts": "2026-08-08T09:00:00", "ml": 1800, "type": "Wasser"})
    trend = logic.drinks_trend(drinks, now)
    assert trend is not None
    assert trend["percent"] == 50.0
    assert trend["today_ml"] == 1800
    assert trend["prev_week_avg_ml"] == 1200.0


def test_drinks_trend_negative_percent():
    """[REQ-HOM-002] Heute unter dem Vorwochen-Ø ⇒ negatives Prozent."""
    now = datetime(2026, 8, 8, 12, 0)
    drinks = _daily_drinks(now, 7, 900)  # Ø 900 ml/Tag (900/3 ganzzahlig)
    drinks.append({"ts": "2026-08-08T09:00:00", "ml": 450, "type": "Wasser"})
    trend = logic.drinks_trend(drinks, now)
    assert trend is not None
    assert trend["percent"] == -50.0
    assert trend["today_ml"] == 450


def test_drinks_trend_day_without_drinks_counts_as_zero():
    """[REQ-HOM-002] Das Ø teilt immer durch 7 — Leertage zählen als 0."""
    now = datetime(2026, 8, 8, 12, 0)
    # nur 1 der 7 Vorwochentage hat 700 ml → Ø 100 ml/Tag
    drinks = [{"ts": "2026-08-07T09:00:00", "ml": 700, "type": "Wasser"}]
    drinks.append({"ts": "2026-08-08T09:00:00", "ml": 200, "type": "Wasser"})
    trend = logic.drinks_trend(drinks, now)
    assert trend is not None
    assert trend["prev_week_avg_ml"] == 100.0
    assert trend["percent"] == 100.0


def test_drinks_trend_excludes_older_than_previous_week():
    """[REQ-HOM-002] Buchungen älter als 7 Tage fließen nicht in den Ø ein."""
    now = datetime(2026, 8, 8, 12, 0)
    drinks = [{"ts": "2026-07-01T09:00:00", "ml": 9999, "type": "Wasser"}]
    drinks.append({"ts": "2026-08-07T09:00:00", "ml": 700, "type": "Wasser"})
    drinks.append({"ts": "2026-08-08T09:00:00", "ml": 700, "type": "Wasser"})
    trend = logic.drinks_trend(drinks, now)
    assert trend is not None
    assert trend["prev_week_avg_ml"] == 100.0


def test_drinks_trend_respects_daily_reset_hour():
    """[REQ-HOM-002] Tagesgrenze via daily_reset_hour verschiebt das Fenster."""
    now = datetime(2026, 8, 8, 8, 0)
    drinks = [{"ts": "2026-08-08T05:00:00", "ml": 300, "type": "Kaffee"}]
    trend6 = logic.drinks_trend(drinks, now, hour=6)
    # hour=6: die 05:00-Buchung gehört noch zum Vortag → heute 0, Ø 300/7
    # → -100.0 %.
    assert trend6 is not None
    assert trend6["today_ml"] == 0
    assert trend6["percent"] == -100.0


BP_TREND_READINGS = [
    # Vorwoche: niedrige Werte
    {"ts": "2026-08-01T08:00:00", "sys": 130, "dia": 80, "pulse": 70},
    {"ts": "2026-08-02T08:00:00", "sys": 130, "dia": 80, "pulse": 70},
    {"ts": "2026-08-03T08:00:00", "sys": 130, "dia": 80, "pulse": 70},
    # letzte 7 Tage: höhere Werte
    {"ts": "2026-08-10T08:00:00", "sys": 150, "dia": 90, "pulse": 70},
    {"ts": "2026-08-11T08:00:00", "sys": 150, "dia": 90, "pulse": 70},
    {"ts": "2026-08-12T08:00:00", "sys": 150, "dia": 90, "pulse": 70},
]


def test_bp_trend_requires_min_three_readings():
    """[REQ-HOM-002] < 3 gültige Messungen ⇒ None (Sensor: unknown)."""
    now = datetime(2026, 8, 13, 8, 0)
    assert logic.bp_trend(BP_TREND_READINGS[:2], now) is None
    assert logic.bp_trend([], now) is None
    # Genau 3 Messungen (2 Vorwoche + 1 letzte Woche) reichen → Ergebnis.
    three = [
        {"ts": "2026-08-01T08:00:00", "sys": 130, "dia": 80},
        {"ts": "2026-08-02T08:00:00", "sys": 130, "dia": 80},
        {"ts": "2026-08-10T08:00:00", "sys": 150, "dia": 90},
    ]
    assert logic.bp_trend(three, now) is not None


def test_bp_trend_rising():
    """[REQ-HOM-002] Höheres 7-Tage-Mittel ⇒ rising mit sys/dia-Delta."""
    now = datetime(2026, 8, 13, 8, 0)
    trend = logic.bp_trend(BP_TREND_READINGS, now)
    assert trend is not None
    assert trend["direction"] == "rising"
    assert trend["sys_delta"] == 20.0
    assert trend["dia_delta"] == 10.0
    assert trend["sys_avg_recent"] == 150.0
    assert trend["sys_avg_previous"] == 130.0


def test_bp_trend_falling():
    """[REQ-HOM-002] Niedrigeres 7-Tage-Mittel ⇒ falling."""
    now = datetime(2026, 8, 13, 8, 0)
    flipped = [{**r, "sys": 270 - r["sys"], "dia": 170 - r["dia"]} for r in BP_TREND_READINGS]
    trend = logic.bp_trend(flipped, now)
    assert trend is not None
    assert trend["direction"] == "falling"
    assert trend["sys_delta"] == -20.0


def test_bp_trend_stable_within_threshold():
    """[REQ-HOM-002] |sys-Delta| < 2 mmHg ⇒ stable."""
    now = datetime(2026, 8, 13, 8, 0)
    readings = [
        {"ts": "2026-08-01T08:00:00", "sys": 139, "dia": 82},
        {"ts": "2026-08-02T08:00:00", "sys": 139, "dia": 82},
        {"ts": "2026-08-10T08:00:00", "sys": 140, "dia": 82},
        {"ts": "2026-08-11T08:00:00", "sys": 140, "dia": 82},
    ]
    trend = logic.bp_trend(readings, now)
    assert trend is not None
    assert trend["direction"] == "stable"
    assert trend["sys_delta"] == 1.0


def test_bp_trend_none_without_previous_week_data():
    """[REQ-HOM-002] Ohne Messungen im Vorfenster kein Delta ⇒ None."""
    now = datetime(2026, 8, 13, 8, 0)
    recent_only = [r for r in BP_TREND_READINGS if r["ts"] >= "2026-08-10"]
    assert logic.bp_trend(recent_only, now) is None


def test_bp_trend_dia_delta_none_when_diastolic_missing():
    """[REQ-HOM-002] Fehlende dia-Werte ⇒ dia_delta None, sys-Trend bleibt."""
    now = datetime(2026, 8, 13, 8, 0)
    readings = [
        {"ts": "2026-08-01T08:00:00", "sys": 130, "dia": None},
        {"ts": "2026-08-02T08:00:00", "sys": 130, "dia": None},
        {"ts": "2026-08-10T08:00:00", "sys": 150, "dia": 90},
        {"ts": "2026-08-11T08:00:00", "sys": 150, "dia": 90},
        {"ts": "2026-08-12T08:00:00", "sys": 150, "dia": 90},
    ]
    trend = logic.bp_trend(readings, now)
    assert trend is not None
    assert trend["direction"] == "rising"
    assert trend["dia_delta"] is None


# --- Streak-Sensor (REQ-HOM-003) ---


def _morning(day: datetime, ml: int, dtype: str = "Wasser") -> dict:
    """Eine Morgen-Buchung am gegebenen Tag."""
    return {"ts": (day.replace(hour=9, minute=0)).isoformat(), "ml": ml, "type": dtype}


def test_goal_streak_empty_history_is_zero():
    """[REQ-HOM-003] Leere Historie ⇒ 0/0."""
    now = datetime(2026, 8, 22, 12, 0)
    assert logic.goal_streak([], 2000, now) == {"current_streak": 0, "best_streak": 0}


def test_goal_streak_counts_consecutive_goal_days():
    """[REQ-HOM-003] Drei Tage in Folge mit erreichtem Ziel (heute erreicht)."""
    now = datetime(2026, 8, 22, 12, 0)
    drinks = [
        _morning(datetime(2026, 8, 22), 1000),
        _morning(datetime(2026, 8, 21), 1500),
        _morning(datetime(2026, 8, 20), 1000),
        _morning(datetime(2026, 8, 18), 2000),  # Lücke am 19.
    ]
    assert logic.goal_streak(drinks, 1000, now) == {"current_streak": 3, "best_streak": 3}


def test_goal_streak_today_not_reached_runs_to_yesterday():
    """[REQ-HOM-003] Heute noch nicht erreicht ⇒ Serie endet gestern."""
    now = datetime(2026, 8, 22, 12, 0)
    drinks = [
        _morning(datetime(2026, 8, 22), 500),  # 500 < 1000
        _morning(datetime(2026, 8, 21), 1000),
        _morning(datetime(2026, 8, 20), 1000),
        _morning(datetime(2026, 8, 19), 1000),
        _morning(datetime(2026, 8, 18), 400),
    ]
    assert logic.goal_streak(drinks, 1000, now) == {"current_streak": 3, "best_streak": 3}


def test_goal_streak_gap_breaks_series_and_best_can_exceed_current():
    """[REQ-HOM-003] Lücke bricht die laufende Serie; best_streak > current."""
    now = datetime(2026, 8, 22, 12, 0)
    drinks = [
        _morning(datetime(2026, 8, 22), 1000),  # 2er-Serie bis heute
        _morning(datetime(2026, 8, 21), 1000),
        _morning(datetime(2026, 8, 20), 100),  # Lücke
        _morning(datetime(2026, 8, 19), 1000),  # 3er-Serie
        _morning(datetime(2026, 8, 18), 1000),
        _morning(datetime(2026, 8, 17), 1000),
    ]
    assert logic.goal_streak(drinks, 1000, now) == {"current_streak": 2, "best_streak": 3}


def test_goal_streak_exact_goal_counts_but_one_ml_less_does_not():
    """[REQ-HOM-003] Ziel exakt erreicht zählt; 1 ml darunter bricht."""
    now = datetime(2026, 8, 22, 12, 0)
    reached = [_morning(datetime(2026, 8, 22), 1000)]
    missed = [_morning(datetime(2026, 8, 22), 999)]
    assert logic.goal_streak(reached, 1000, now) == {"current_streak": 1, "best_streak": 1}
    assert logic.goal_streak(missed, 1000, now) == {"current_streak": 0, "best_streak": 0}


def test_goal_streak_multiple_bookings_on_same_day_sum_up():
    """[REQ-HOM-003] Mehrere Buchungen desselben Tages werden summiert."""
    now = datetime(2026, 8, 22, 12, 0)
    drinks = [
        {"ts": "2026-08-22T09:00:00", "ml": 600, "type": "Wasser"},
        {"ts": "2026-08-22T15:00:00", "ml": 400, "type": "Wasser"},
    ]
    assert logic.goal_streak(drinks, 1000, now) == {"current_streak": 1, "best_streak": 1}


def test_goal_streak_respects_daily_reset_hour():
    """[REQ-HOM-003] Tagesgrenze via daily_reset_hour verschiebt die Tagesschlüssel."""
    now = datetime(2026, 8, 22, 8, 0)
    drinks = [
        {"ts": "2026-08-22T05:00:00", "ml": 1000, "type": "Wasser"},  # vor 06:00
        {"ts": "2026-08-22T07:00:00", "ml": 1000, "type": "Wasser"},  # nach 06:00
    ]
    # hour=6: 05:00 gehört zum 21., 07:00 zum 22. → zwei erreichte Tage
    assert logic.goal_streak(drinks, 1000, now, hour=6) == {
        "current_streak": 2,
        "best_streak": 2,
    }
    # hour=0: beide am 22. → nur ein erreichtes Tag
    assert logic.goal_streak(drinks, 1000, now, hour=0) == {
        "current_streak": 1,
        "best_streak": 1,
    }


def test_goal_streak_before_reset_boundary_belongs_to_previous_day():
    """[REQ-HOM-003] Buchung kurz vor der Grenze zählt zum Vortag — Serie bleibt."""
    now = datetime(2026, 8, 22, 8, 0)
    drinks = [
        {"ts": "2026-08-22T05:59:00", "ml": 1000, "type": "Wasser"},
        {"ts": "2026-08-21T05:30:00", "ml": 1000, "type": "Wasser"},
    ]
    # hour=6: 22.05:59 → 21., 21.05:30 → 20. → Serie über 21.+20., heute (22.) offen
    assert logic.goal_streak(drinks, 1000, now, hour=6) == {
        "current_streak": 2,
        "best_streak": 2,
    }


def test_goal_streak_non_positive_goal_is_zero():
    """[REQ-HOM-003] Ziel <= 0 ist undefiniert ⇒ 0/0 (kein „immer erreicht")."""
    now = datetime(2026, 8, 22, 12, 0)
    drinks = [_morning(datetime(2026, 8, 22), 1000)]
    assert logic.goal_streak(drinks, 0, now) == {"current_streak": 0, "best_streak": 0}


def test_goal_streak_skips_invalid_timestamps():
    """[REQ-HOM-003] Ungültiger/fehlender ts bricht die Ableitung nicht ab."""
    now = datetime(2026, 8, 22, 12, 0)
    drinks = [
        {"ts": "kaputt", "ml": 5000, "type": "Wasser"},
        {"ml": 5000, "type": "Wasser"},
        _morning(datetime(2026, 8, 22), 1000),
    ]
    assert logic.goal_streak(drinks, 1000, now) == {"current_streak": 1, "best_streak": 1}


# --- Koffein-Tagessensor (REQ-HOM-004) ---


def test_caffeine_today_no_drinks_is_zero():
    """[REQ-HOM-004] Keine Getränke ⇒ 0 mg, leerer Breakdown."""
    now = datetime(2026, 8, 22, 12, 0)
    assert logic.caffeine_today([], now) == {"total_mg": 0.0, "breakdown": {}}


def test_caffeine_today_scales_with_ml():
    """[REQ-HOM-004] mg skalieren linear mit der Menge (mg je 100 ml)."""
    now = datetime(2026, 8, 22, 12, 0)
    drinks = [{"ts": "2026-08-22T09:00:00", "ml": 250, "type": "Kaffee"}]
    result = logic.caffeine_today(drinks, now)
    # 250 ml * 40 mg/100 ml = 100 mg
    assert result["total_mg"] == 100.0
    assert result["breakdown"] == {"Kaffee": 100.0}


def test_caffeine_today_sums_multiple_types():
    """[REQ-HOM-004] Mehrere Typen werden je Typ und in Summe erfasst."""
    now = datetime(2026, 8, 22, 12, 0)
    drinks = [
        {"ts": "2026-08-22T08:00:00", "ml": 250, "type": "Kaffee"},  # 100 mg
        {"ts": "2026-08-22T10:00:00", "ml": 40, "type": "Espresso"},  # 80 mg
        {"ts": "2026-08-22T11:00:00", "ml": 330, "type": "Cola"},  # 33 mg
    ]
    result = logic.caffeine_today(drinks, now)
    assert result["breakdown"] == {"Kaffee": 100.0, "Espresso": 80.0, "Cola": 33.0}
    assert result["total_mg"] == 213.0


def test_caffeine_today_unknown_and_eigen_types_are_zero():
    """[REQ-HOM-004] Unbekannter Typ und „Eigen" ⇒ 0 mg, nicht im Breakdown."""
    now = datetime(2026, 8, 22, 12, 0)
    drinks = [
        {"ts": "2026-08-22T09:00:00", "ml": 500, "type": "Eigen"},
        {"ts": "2026-08-22T10:00:00", "ml": 500, "type": "Unbekannt"},
        {"ts": "2026-08-22T11:00:00", "ml": 300, "type": "Wasser"},  # koffeinfrei
    ]
    result = logic.caffeine_today(drinks, now)
    assert result["total_mg"] == 0.0
    assert result["breakdown"] == {}


def test_caffeine_today_respects_daily_reset_hour_and_other_days():
    """[REQ-HOM-004] Nur das heutige Fenster zählt; daily_reset_hour verschiebt es."""
    now = datetime(2026, 8, 22, 8, 0)
    drinks = [
        {"ts": "2026-08-21T20:00:00", "ml": 250, "type": "Kaffee"},  # Vortag
        {"ts": "2026-08-22T05:00:00", "ml": 250, "type": "Kaffee"},  # vor 06:00-Grenze
        {"ts": "2026-08-22T07:00:00", "ml": 250, "type": "Kaffee"},  # heute
    ]
    # hour=6: nur die 07:00-Buchung liegt im heutigen Fenster → 100 mg
    assert logic.caffeine_today(drinks, now, hour=6)["total_mg"] == 100.0
    # hour=0: 05:00 + 07:00 gehören heute (Vortag 20:00 nicht) → 200 mg
    assert logic.caffeine_today(drinks, now, hour=0)["total_mg"] == 200.0


def test_caffeine_table_covers_every_canonical_lexicon_type():
    """[REQ-HOM-004] Schätztabelle kennt jeden kanonischen DRINK_LEXICON-Typ."""
    canonical = {canonical_name for canonical_name, _default_ml in const.DRINK_LEXICON.values()}
    assert canonical <= set(const.CAFFEINE_MG_PER_100ML)


# --- Zeitzonen-Robustheit: Alt-Bestand (naive ts) + aware Fenster ---
#
# Regression: `window_sums`/`avg_over_window` parsten `ts` im try, verglichen
# aber AUSSERHALB — ein naiver Alt-Zeitstempel gegen ein tz-aware Fenster
# (`dt_util.now()`) warf `TypeError: can't compare offset-naive and offset-aware
# datetimes` und riss den Sensor-Read ab. Zentrale Normalisierung `_normalize_ts`
# weist naiven Werten die Zeitzone der Referenz zu; `_in_window` fängt Restfälle.

_TZ = timezone(timedelta(hours=2))


def test_normalize_ts_assigns_reference_tz_to_naive():
    """[TZ] Naiver ts übernimmt die Zeitzone der Referenz."""
    ref = datetime(2026, 8, 22, 12, 0, tzinfo=_TZ)
    ts = logic._normalize_ts("2026-08-22T09:00:00", ref)
    assert ts is not None and ts.tzinfo is not None and ts.utcoffset() == timedelta(hours=2)
    assert ts.hour == 9  # Wanduhrzeit bleibt, nur die tz wird ergänzt


def test_normalize_ts_leaves_aware_value_unchanged():
    """[TZ] Ein tz-aware ts bleibt UNVERÄNDERT (eigene Zone wird nicht ersetzt)."""
    ref = datetime(2026, 8, 22, 12, 0, tzinfo=_TZ)
    aware = datetime(2026, 8, 22, 9, 0, tzinfo=timezone(timedelta(hours=5)))
    assert logic._normalize_ts(aware.isoformat(), ref) == aware


def test_normalize_ts_invalid_or_missing_returns_none():
    """[TZ] Ungültige/fehlende Werte → None (werden übersprungen, kein Crash)."""
    ref = datetime(2026, 8, 22, 12, 0, tzinfo=_TZ)
    assert logic._normalize_ts("kaputt", ref) is None
    assert logic._normalize_ts(None, ref) is None
    assert logic._normalize_ts(12345, ref) is None


def test_in_window_defensive_on_tz_mismatch():
    """[TZ] `_in_window` fängt unerwarteten TypeError defensiv ab (→ False)."""
    naive = datetime(2026, 8, 22, 9, 0)
    aware_start = datetime(2026, 8, 22, 0, 0, tzinfo=_TZ)
    aware_end = datetime(2026, 8, 22, 23, 0, tzinfo=_TZ)
    assert logic._in_window(naive, aware_start, aware_end) is False


def test_window_sums_naive_ts_with_aware_window_no_crash():
    """[TZ] Naiver Alt-ts gegen aware Fenster → kein Crash, korrekte Summe."""
    start = datetime(2026, 8, 22, 0, 0, tzinfo=_TZ)
    end = datetime(2026, 8, 22, 12, 0, tzinfo=_TZ)
    drinks = [{"ts": "2026-08-22T09:00:00", "ml": 250, "type": "Kaffee"}]
    sums = logic.window_sums(drinks, start, end)
    assert sums["total_ml"] == 250
    assert sums["count"] == 1
    assert sums["breakdown"] == {"Kaffee": 250}


def test_window_sums_naive_ts_interpreted_as_local_tz_not_utc():
    """[TZ] Naive Wanduhrzeit = lokale Zeitzone, NICHT UTC.

    11:00 als lokal (+02:00) liegt vor dem 12:00-Ende; als UTC (13:00 lokal)
    läge es dahinter. Das Getränk MUSS also zählen.
    """
    start = datetime(2026, 8, 22, 0, 0, tzinfo=_TZ)
    end = datetime(2026, 8, 22, 12, 0, tzinfo=_TZ)
    drinks = [{"ts": "2026-08-22T11:00:00", "ml": 300, "type": "Wasser"}]
    assert logic.window_sums(drinks, start, end)["total_ml"] == 300


def test_window_sums_mixed_naive_and_aware_ts():
    """[TZ] Gemischte naive + aware Einträge: keine Crash, korrekte Summen."""
    start = datetime(2026, 8, 22, 0, 0, tzinfo=_TZ)
    end = datetime(2026, 8, 22, 12, 0, tzinfo=_TZ)
    drinks = [
        {"ts": "2026-08-22T09:00:00", "ml": 250, "type": "Kaffee"},  # naive
        {"ts": "2026-08-22T10:00:00+02:00", "ml": 500, "type": "Wasser"},  # aware
        {"ts": "2026-08-21T20:00:00", "ml": 999, "type": "Wasser"},  # Vortag
        {"ts": "kaputt", "ml": 999},
    ]
    sums = logic.window_sums(drinks, start, end)
    assert sums["total_ml"] == 750
    assert sums["count"] == 2
    assert sums["breakdown"] == {"Kaffee": 250, "Wasser": 500}


def test_window_sums_empty_list():
    """[TZ] Leere Liste → Null-Summe, kein Crash."""
    start = datetime(2026, 8, 22, 0, 0, tzinfo=_TZ)
    end = datetime(2026, 8, 22, 12, 0, tzinfo=_TZ)
    assert logic.window_sums([], start, end) == {
        "total_ml": 0,
        "count": 0,
        "breakdown": {},
        "last_ts": None,
    }


def test_window_sums_only_naive_ts():
    """[TZ] Ausschließlich naive Zeitstempel gegen aware Fenster."""
    start = datetime(2026, 8, 22, 0, 0, tzinfo=_TZ)
    end = datetime(2026, 8, 22, 12, 0, tzinfo=_TZ)
    drinks = [{"ts": "2026-08-22T08:00:00", "ml": 100, "type": "Wasser"}]
    assert logic.window_sums(drinks, start, end)["total_ml"] == 100


def test_window_sums_only_aware_ts():
    """[TZ] Ausschließlich aware Zeitstempel (Regression, unverändert)."""
    start = datetime(2026, 8, 22, 0, 0, tzinfo=_TZ)
    end = datetime(2026, 8, 22, 12, 0, tzinfo=_TZ)
    drinks = [{"ts": "2026-08-22T08:00:00+02:00", "ml": 100, "type": "Wasser"}]
    assert logic.window_sums(drinks, start, end)["total_ml"] == 100


def test_window_sums_all_invalid_or_missing_ts_skipped():
    """[TZ] Nur ungültige/fehlende ts → alles übersprungen, keine Summe."""
    start = datetime(2026, 8, 22, 0, 0, tzinfo=_TZ)
    end = datetime(2026, 8, 22, 12, 0, tzinfo=_TZ)
    drinks = [{"ts": "kaputt", "ml": 500}, {"ml": 500}, {"ts": None, "ml": 500}]
    sums = logic.window_sums(drinks, start, end)
    assert sums["total_ml"] == 0 and sums["count"] == 0


def test_today_sums_naive_ts_with_aware_now_no_crash():
    """[TZ] `today_sums` (delegiert an window_sums) mit aware `now`."""
    now = datetime(2026, 8, 22, 12, 0, tzinfo=_TZ)
    drinks = [
        {"ts": "2026-08-22T09:00:00", "ml": 250, "type": "Kaffee"},  # naive
        {"ts": "2026-08-22T10:00:00+02:00", "ml": 500, "type": "Wasser"},  # aware
        {"ts": "2026-08-21T09:00:00", "ml": 999, "type": "Wasser"},  # Vortag
    ]
    sums = logic.today_sums(drinks, now)
    assert sums["total_ml"] == 750
    assert sums["count"] == 2


def test_today_sums_naive_after_now_on_same_day_still_bound():
    """[TZ] Naive Buchung 13:00 mit aware now 12:00 → liegt (lokal) in der Zukunft."""
    now = datetime(2026, 8, 22, 12, 0, tzinfo=_TZ)
    drinks = [{"ts": "2026-08-22T13:00:00", "ml": 500, "type": "Wasser"}]
    assert logic.today_sums(drinks, now)["total_ml"] == 0


def test_avg_over_window_naive_ts_with_aware_now_no_crash():
    """[TZ] `avg_over_window` mit naive Alt-Messungen + aware `now`."""
    now = datetime(2026, 8, 22, 12, 0, tzinfo=_TZ)
    readings = [
        {"ts": "2026-08-22T09:00:00", "sys": 120},  # naive, im Fenster
        {"ts": "2026-08-21T09:00:00+02:00", "sys": 140},  # aware, im Fenster
        {"ts": "kaputt", "sys": 999},
    ]
    assert logic.avg_over_window(readings, "sys", now) == (120 + 140) / 2


def test_avg_over_window_mixed_tz_boundary_excluded():
    """[TZ] Gemischte Einträge außerhalb des Fensters werden korrekt ausgeschlossen."""
    now = datetime(2026, 8, 22, 12, 0, tzinfo=_TZ)
    readings = [
        {"ts": "2026-08-10T09:00:00", "sys": 100},  # naive, > 7 Tage alt
        {"ts": "2026-08-22T09:00:00+02:00", "sys": 200},  # aware, heute
    ]
    assert logic.avg_over_window(readings, "sys", now) == 200


def test_avg_over_window_only_naive_and_only_aware():
    """[TZ] Nur naive bzw. nur aware Einträge liefern denselben Schnitt."""
    now = datetime(2026, 8, 22, 12, 0, tzinfo=_TZ)
    naive = [{"ts": "2026-08-22T09:00:00", "sys": 120}]
    aware = [{"ts": "2026-08-22T09:00:00+02:00", "sys": 120}]
    assert logic.avg_over_window(naive, "sys", now) == 120
    assert logic.avg_over_window(aware, "sys", now) == 120


def test_avg_over_window_empty_and_all_invalid_with_aware_now():
    """[TZ] Leere Liste und ausschließlich ungültige ts → None (kein Crash)."""
    now = datetime(2026, 8, 22, 12, 0, tzinfo=_TZ)
    assert logic.avg_over_window([], "sys", now) is None
    assert logic.avg_over_window([{"ts": "kaputt", "sys": 1}, {"sys": 2}], "sys", now) is None


def test_bp_trend_mixed_naive_and_aware_no_crash():
    """[TZ] `bp_trend` (`_count_valid_bp`/`_avg_in_range`) mit gemischten ts."""
    now = datetime(2026, 8, 13, 8, 0, tzinfo=_TZ)
    readings = [
        # Vorwoche: naive Zeitstempel
        {"ts": "2026-08-01T08:00:00", "sys": 130, "dia": 80},
        {"ts": "2026-08-02T08:00:00", "sys": 130, "dia": 80},
        {"ts": "2026-08-03T08:00:00", "sys": 130, "dia": 80},
        # letzte 7 Tage: aware Zeitstempel
        {"ts": "2026-08-10T08:00:00+02:00", "sys": 150, "dia": 90},
        {"ts": "2026-08-11T08:00:00+02:00", "sys": 150, "dia": 90},
        {"ts": "2026-08-12T08:00:00+02:00", "sys": 150, "dia": 90},
    ]
    trend = logic.bp_trend(readings, now)
    assert trend is not None
    assert trend["direction"] == "rising"
    assert trend["sys_delta"] == 20.0


def test_goal_streak_mixed_naive_and_aware_no_crash():
    """[TZ] `goal_streak` (`_daily_totals_by_day`) mit gemischten ts."""
    now = datetime(2026, 8, 22, 12, 0, tzinfo=_TZ)
    drinks = [
        {"ts": "2026-08-22T09:00:00", "ml": 1500, "type": "Wasser"},  # naive
        {"ts": "2026-08-21T09:00:00+02:00", "ml": 1500, "type": "Wasser"},  # aware
        {"ts": "kaputt", "ml": 5000, "type": "Wasser"},
    ]
    assert logic.goal_streak(drinks, 1000, now) == {"current_streak": 2, "best_streak": 2}


def test_drinks_trend_mixed_naive_and_aware_no_crash():
    """[TZ] `drinks_trend` mit aware `now` und gemischten ts."""
    now = datetime(2026, 8, 8, 12, 0, tzinfo=_TZ)
    drinks = [
        {"ts": "2026-08-07T09:00:00", "ml": 700, "type": "Wasser"},  # naive, Vorwoche
        {"ts": "2026-08-06T09:00:00+02:00", "ml": 700, "type": "Wasser"},  # aware, Vorwoche
        {"ts": "2026-08-08T09:00:00", "ml": 100, "type": "Wasser"},  # naive, heute
    ]
    trend = logic.drinks_trend(drinks, now)
    assert trend is not None
    assert trend["today_ml"] == 100
    assert trend["prev_week_avg_ml"] == 200.0
    assert trend["percent"] == -50.0


def test_caffeine_today_naive_ts_with_aware_now_no_crash():
    """[TZ] `caffeine_today` mit naive Alt-Buchungen + aware `now`."""
    now = datetime(2026, 8, 22, 12, 0, tzinfo=_TZ)
    drinks = [{"ts": "2026-08-22T09:00:00", "ml": 250, "type": "Kaffee"}]
    assert logic.caffeine_today(drinks, now)["total_mg"] == 100.0


# --- Hydration-Pace (Konzept docs/CONCEPT-UI.md §6.3) ---
#
# Halbzeit-Anker: NOW = 12:00 bei Tagesgrenze 00:00 ⇒ Anteil 0.5,
# Soll = goal * 0.5, Toleranz = 10 % des Ziels (2000 → 200 ml).

_PACE_NOW = datetime(2026, 8, 22, 12, 0)


def _pace_drink(ml: int, ts: str = "2026-08-22T09:00:00") -> dict:
    return {"ts": ts, "ml": ml, "type": "Wasser"}


def test_hydration_pace_ahead_and_forecast_may_exceed_goal():
    """[PACE] Deutlich über dem linearen Soll ⇒ ahead; Forecast darf > Ziel sein."""
    pace = logic.hydration_pace([_pace_drink(1300)], _PACE_NOW, 2000)
    assert pace == {
        "status": "ahead",
        "actual_ml": 1300,
        "expected_ml": 1000.0,
        "delta_ml": 300.0,
        "forecast_ml": 2600.0,
        "percent": 65.0,
    }


def test_hydration_pace_on_track():
    """[PACE] Genau auf dem linearen Soll ⇒ on_track, delta 0."""
    pace = logic.hydration_pace([_pace_drink(1000)], _PACE_NOW, 2000)
    assert pace["status"] == "on_track"
    assert pace["delta_ml"] == 0.0
    assert pace["forecast_ml"] == 2000.0
    assert pace["percent"] == 50.0


def test_hydration_pace_behind():
    """[PACE] Deutlich unter dem linearen Soll ⇒ behind."""
    pace = logic.hydration_pace([_pace_drink(600)], _PACE_NOW, 2000)
    assert pace["status"] == "behind"
    assert pace["delta_ml"] == -400.0
    assert pace["forecast_ml"] == 1200.0
    assert pace["percent"] == 30.0


def test_hydration_pace_tolerance_boundary_is_on_track():
    """[PACE] |delta| exakt auf der Toleranz (200 ml) ⇒ noch on_track."""
    assert logic.hydration_pace([_pace_drink(1200)], _PACE_NOW, 2000)["status"] == "on_track"
    assert logic.hydration_pace([_pace_drink(800)], _PACE_NOW, 2000)["status"] == "on_track"


def test_hydration_pace_never_returns_goal_reached():
    """[PACE] `goal_reached` vergibt die UI-Schicht — logic liefert nur 3 Werte."""
    pace = logic.hydration_pace([_pace_drink(3000)], _PACE_NOW, 2000)
    assert pace["status"] == "ahead"


def test_hydration_pace_empty_drinks_is_zero_actual():
    """[PACE] Keine Buchungen ⇒ actual 0 (bei Halbzeit ⇒ behind)."""
    pace = logic.hydration_pace([], _PACE_NOW, 2000)
    assert pace["actual_ml"] == 0
    assert pace["status"] == "behind"
    assert pace["percent"] == 0.0


def test_hydration_pace_non_positive_goal_is_undefined():
    """[PACE] goal <= 0 ⇒ kein Soll-Verlauf; Ist-Stand bleibt erhalten."""
    drinks = [_pace_drink(1500)]
    for goal in (0, -500):
        pace = logic.hydration_pace(drinks, _PACE_NOW, goal)
        assert pace["status"] is None
        assert pace["actual_ml"] == 1500
        assert pace["expected_ml"] is None
        assert pace["delta_ml"] is None
        assert pace["forecast_ml"] is None
        assert pace["percent"] == 0.0


def test_hydration_pace_invalid_goal_is_robust():
    """[PACE] Ungültiges Ziel (None/Text) ⇒ kein Crash, wie goal <= 0 behandelt."""
    for goal in (None, "kein-ziel"):
        pace = logic.hydration_pace([], _PACE_NOW, goal)
        assert pace["status"] is None
        assert pace["percent"] == 0.0


def test_hydration_pace_at_day_start_no_division_by_zero():
    """[PACE] Exakt am Tagesbeginn (Anteil 0): forecast None, kein ZeroDivisionError."""
    at_start = datetime(2026, 8, 22, 0, 0)
    pace = logic.hydration_pace([], at_start, 2000)
    assert pace["expected_ml"] == 0.0
    assert pace["delta_ml"] == 0.0
    assert pace["status"] == "on_track"
    assert pace["forecast_ml"] is None
    assert pace["percent"] == 0.0


def test_hydration_pace_at_day_start_with_intake_is_ahead():
    """[PACE] Erste Buchung direkt am Tagesbeginn ⇒ Soll 0, also ahead."""
    at_start = datetime(2026, 8, 22, 0, 30)
    pace = logic.hydration_pace([_pace_drink(500, "2026-08-22T00:15:00")], at_start, 2000)
    assert pace["actual_ml"] == 500
    assert pace["expected_ml"] == 41.7  # 2000 * 0.5 h / 24 h
    assert pace["status"] == "ahead"


def test_hydration_pace_shortly_before_day_end():
    """[PACE] Anteil ~1 kurz vor Tagesende: Forecast knapp über dem Ist-Stand."""
    now = datetime(2026, 8, 22, 23, 30)
    pace = logic.hydration_pace([_pace_drink(1900)], now, 2000)
    assert pace["status"] == "on_track"  # Soll 1958.3, Toleranz 200
    assert pace["expected_ml"] == pytest.approx(1958.3, abs=0.1)
    assert pace["forecast_ml"] == pytest.approx(1940.4, abs=0.1)


def test_hydration_pace_respects_reset_hour_boundary():
    """[PACE] Tagesgrenze 04:00: 03:00-Buchung zählt zum Vortag, Fenster = 8 h."""
    drinks = [
        _pace_drink(500, "2026-08-22T03:00:00"),  # vor 04:00 → Vortag
        _pace_drink(300, "2026-08-22T09:00:00"),  # heute
    ]
    pace = logic.hydration_pace(drinks, _PACE_NOW, 2000, hour=4)
    assert pace["actual_ml"] == 300
    assert pace["expected_ml"] == 666.7  # 2000 * 8 h / 24 h
    assert pace["status"] == "behind"


def test_hydration_pace_respects_reset_minute_boundary():
    """[PACE] Grenze mit Minute != 0 (06:30): Fenster = 5,5 h."""
    drinks = [_pace_drink(500, "2026-08-22T06:00:00")]  # vor 06:30 → Vortag
    pace = logic.hydration_pace(drinks, _PACE_NOW, 2000, hour=6, minute=30)
    assert pace["actual_ml"] == 0
    assert pace["expected_ml"] == pytest.approx(2000 * 5.5 / 24, abs=0.1)
    assert pace["status"] == "behind"


def test_hydration_pace_mixed_naive_and_aware_ts_no_crash():
    """[TZ] Gemischte naive/aware ts + ungültiger ts ⇒ kein Crash, korrekter Ist-Stand."""
    now = datetime(2026, 8, 22, 12, 0, tzinfo=_TZ)
    drinks = [
        {"ts": "2026-08-22T09:00:00", "ml": 600, "type": "Wasser"},  # naive
        {"ts": "2026-08-22T10:00:00+02:00", "ml": 600, "type": "Wasser"},  # aware
        {"ts": "2026-08-21T20:00:00", "ml": 999, "type": "Wasser"},  # Vortag
        {"ts": "kaputt", "ml": 999, "type": "Wasser"},
    ]
    pace = logic.hydration_pace(drinks, now, 2000)
    assert pace["actual_ml"] == 1200
    assert pace["status"] == "on_track"  # delta +200 == Toleranz
    assert pace["percent"] == 60.0


def test_hydration_pace_is_consistent_with_today_sums():
    """[PACE] `actual_ml` ist exakt die heutige Summe (`today_sums`)."""
    now = datetime(2026, 8, 22, 15, 0)
    drinks = [
        _pace_drink(250, "2026-08-22T08:00:00"),
        _pace_drink(500, "2026-08-22T13:00:00"),
        _pace_drink(999, "2026-08-21T20:00:00"),  # Vortag
    ]
    pace = logic.hydration_pace(drinks, now, 2000, hour=4)
    assert pace["actual_ml"] == logic.today_sums(drinks, now, hour=4)["total_ml"] == 750


# --- REQ-HOM-112: Wohlbefinden-Score (rein abgeleitet, HA-frei) -------------

# Erwartete Skala der aktuellen Zustände: Index + 1 (1 = schlechtester).
_EXPECTED_WELLBEING_SCORES = {
    "very_bad": 1,
    "awful": 2,
    "bad": 3,
    "poor": 4,
    "okay": 5,
    "mixed": 6,
    "good": 7,
    "very_good": 8,
    "great": 9,
    "excellent": 10,
}

# Synthetische Zustandsliste mit EINER zusätzlichen Stufe (Skala 1…11).
_SYNTHETIC_WELLBEING_STATES = [
    {"key": "very_bad", "label": "Sehr schlecht"},
    {"key": "awful", "label": "Elend"},
    {"key": "bad", "label": "Schlecht"},
    {"key": "poor", "label": "Mäßig"},
    {"key": "okay", "label": "Okay"},
    {"key": "mixed", "label": "Durchwachsen"},
    {"key": "good", "label": "Gut"},
    {"key": "very_good", "label": "Sehr gut"},
    {"key": "great", "label": "Großartig"},
    {"key": "excellent", "label": "Ausgezeichnet"},
    {"key": "superb", "label": "Hervorragend"},
]


def test_req_hom_112_wellbeing_score_maps_every_state_to_index_plus_one():
    """[REQ-HOM-112] Jeder Zustand aus WELLBEING_STATES ⇒ Index + 1."""
    scores = {state["key"]: logic.wellbeing_score(state["key"]) for state in logic.WELLBEING_STATES}

    assert scores == _EXPECTED_WELLBEING_SCORES
    # Die Reihenfolge der Zustandsliste ist die aufsteigende Qualität —
    # der Score folgt ihr (Index + 1), er ist nicht hartkodiert.
    assert [state["key"] for state in logic.WELLBEING_STATES] == list(_EXPECTED_WELLBEING_SCORES)


@pytest.mark.parametrize(
    ("key", "expected"),
    [
        ("very_bad", 1),
        ("awful", 2),
        ("bad", 3),
        ("poor", 4),
        ("okay", 5),
        ("mixed", 6),
        ("good", 7),
        ("very_good", 8),
        ("great", 9),
        ("excellent", 10),
    ],
)
def test_req_hom_112_wellbeing_score_explicit_scale_values(key, expected):
    """[REQ-HOM-112] Feste Skala: very_bad=1 … excellent=10."""
    assert logic.wellbeing_score(key) == expected


@pytest.mark.parametrize("key", ["super_good", "bogus", "superb", "VERY_BAD", "Good"])
def test_req_hom_112_wellbeing_score_unknown_key_returns_none(key):
    """[REQ-HOM-112] Unbekannter Key ⇒ None (nie 0, nie geraten)."""
    assert logic.wellbeing_score(key) is None


def test_req_hom_112_wellbeing_score_missing_key_returns_none():
    """[REQ-HOM-112] Fehlender Wert (None) ⇒ None (HA-State `unknown`)."""
    assert logic.wellbeing_score(None) is None


def test_req_hom_112_wellbeing_score_empty_string_returns_none():
    """[REQ-HOM-112] Leerer String ⇒ None (kein Treffer auf einer leeren Stufe)."""
    assert logic.wellbeing_score("") is None


@pytest.mark.parametrize("value", [3, 3.5, [], {}, (), True])
def test_req_hom_112_wellbeing_score_non_string_input_returns_none(value):
    """[REQ-HOM-112] Nicht-String-Eingaben ⇒ None (defensiv, kein Absturz)."""
    assert logic.wellbeing_score(value) is None


def test_req_hom_112_wellbeing_score_scale_follows_wellbeing_states(monkeypatch):
    """[REQ-HOM-112] Skala folgt `WELLBEING_STATES` — keine Hartcodierung.

    Kern-Beweis: wird die Zustandsliste um eine sechste Stufe erweitert, so
    bekommt diese den Score 6, während die bisherigen Stufen 1…5 unverändert
    bleiben. Eine hartcodierte Skala (z. B. `if key == "good": return 4`)
    würde hier scheitern.
    """
    monkeypatch.setattr(logic, "WELLBEING_STATES", _SYNTHETIC_WELLBEING_STATES)

    # (a) Die neue Stufe bekommt den Score 11 …
    assert logic.wellbeing_score("superb") == 11
    # (b) … die bisherigen Stufen bleiben unverändert (alte Keys auf
    #     ungeraden Stufen).
    assert logic.wellbeing_score("very_bad") == 1
    assert logic.wellbeing_score("bad") == 3
    assert logic.wellbeing_score("okay") == 5
    assert logic.wellbeing_score("good") == 7
    assert logic.wellbeing_score("great") == 9
    # Höchstwert = Anzahl der Zustände.
    assert max(logic.wellbeing_score(state["key"]) for state in logic.WELLBEING_STATES) == len(
        logic.WELLBEING_STATES
    )


def test_req_hom_112_wellbeing_score_never_returns_zero():
    """[REQ-HOM-112] Nie 0: der schlechteste bekannte Key liefert 1.

    0 würde als schlechtester Wert den Verlauf verfälschen — deshalb muss
    der Score für bekannte Stufen immer >= 1 sein.
    """
    scores = [logic.wellbeing_score(state["key"]) for state in logic.WELLBEING_STATES]

    assert scores == [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
    assert min(scores) == 1
    assert 0 not in scores
    assert logic.wellbeing_score("very_bad") == 1
    assert logic.wellbeing_score("very_bad") != 0


# --- REQ-HOM-112: Frontend-Spiegel der Wohlbefinden-Skala --------------------
#
# Serverseitig waechst die Skala automatisch mit: `logic.wellbeing_score`
# liest `const.WELLBEING_STATES` zur AUFrufZEIT (Index + 1). Die Frontends
# haben dagegen EIGENE Spiegel dieser Zustandsliste:
#
#   * Panel: `WELLBEING_STATES` in `health-o-mat-panel-base.js`
#   * Karte: `WELLBEING_SCALE`  in `health-o-mat-card.js`
#
# Ein still veralteter Spiegel liefert stille Falschwerte: Score-Maximum,
# Y-Achse, Emoji-/Label-Zuordnung und die clientseitige Ableitung aus dem
# Key. Deshalb werden die Spiegel hier an die Server-Skala gepinnt — ohne
# JS-Runner, nur Quelltext-Analyse der Array-Literale.

_WWW_DIR = os.path.join(_COMPONENT_DIR, "www")
_PANEL_BASE_JS = os.path.join(_WWW_DIR, "health-o-mat-panel-base.js")
_CARD_JS = os.path.join(_WWW_DIR, "health-o-mat-card.js")


def _js_array_keys(path: str, name: str) -> list[str]:
    """Die `key`-Werte des JS-Array-Literals `name` — in Deklarationsreihenfolge.

    Ermittelt wird der Array-Inhalt per Klammerzaehlung (robust gegen
    Formatierung) und daraus die `key`-Eigenschaften per Regex gelesen.
    """
    with open(path, encoding="utf-8") as handle:
        text = handle.read()

    match = re.search(rf"\b{re.escape(name)}\s*=\s*\[", text)
    assert match is not None, f"{name} fehlt in {os.path.basename(path)}"

    depth = 1
    index = match.end()
    while index < len(text) and depth:
        if text[index] == "[":
            depth += 1
        elif text[index] == "]":
            depth -= 1
        index += 1
    assert depth == 0, f"das Array-Literal {name} in {os.path.basename(path)} ist nicht geschlossen"

    block = text[match.end() : index - 1]
    return re.findall(r'\bkey\s*:\s*"([^"]+)"', block)


def _server_scale_keys() -> list[str]:
    """Die kanonische Server-Skala (Reihenfolge = aufsteigende Qualitaet)."""
    return [state["key"] for state in const.WELLBEING_STATES]


def _assert_mirror_matches(mirror_keys: list[str], expected: list[str], label: str) -> None:
    """Prueft einen Frontend-Spiegel gegen die Server-Skala (Keys + Reihenfolge)."""
    assert len(mirror_keys) == len(expected), (
        f"{label}: der Spiegel hat {len(mirror_keys)} Stufen, die Server-Skala {len(expected)} "
        "— das Score-Maximum der Frontends waere falsch"
    )
    assert mirror_keys == expected, (
        f"{label}: der Spiegel weicht von der Server-Skala ab — "
        f"Spiegel {mirror_keys} != Server {expected}"
    )


def test_req_hom_112_frontend_wellbeing_mirrors_match_server_scale():
    """[REQ-HOM-112] Beide Frontend-Spiegel == `const.WELLBEING_STATES`.

    Geprueft werden Schluesselliste UND Reihenfolge (die Reihenfolge definiert
    den Score: Index + 1) sowie die Laenge (Score-Maximum der Frontends ==
    Laenge der Server-Skala). Eine zusaetzliche oder fehlende Stufe im Spiegel
    waere ein stiller Fehler — der Score waere dann an der falschen Stelle.
    """
    expected = _server_scale_keys()

    _assert_mirror_matches(
        _js_array_keys(_PANEL_BASE_JS, "WELLBEING_STATES"), expected, "Panel (WELLBEING_STATES)"
    )
    _assert_mirror_matches(
        _js_array_keys(_CARD_JS, "WELLBEING_SCALE"), expected, "Karte (WELLBEING_SCALE)"
    )


def test_req_hom_112_frontend_wellbeing_mirror_check_detects_deviation():
    """[REQ-HOM-112] Gegenbeweis: der Spiegel-Check weist Abweichungen nach.

    Ohne diesen Gegenbeweis waere der Pinning-Test ein "always green"-Test:
    ein Spiegel mit zusaetzlicher Stufe, fehlender Stufe, vertauschter
    Reihenfolge oder ersetztem Key muesste den Check fehlschlagen lassen.
    """
    expected = _server_scale_keys()

    # Kontrollfall: der unveränderte Spiegel besteht den Check.
    _assert_mirror_matches(list(expected), expected, "Karte")

    # (a) eine zusaetzliche Stufe (Skala waechst, der Spiegel nicht)
    with pytest.raises(AssertionError):
        _assert_mirror_matches([*expected, "excellent"], expected, "Karte")
    # (b) eine fehlende Stufe
    with pytest.raises(AssertionError):
        _assert_mirror_matches(expected[:-1], expected, "Karte")
    # (c) vertauschte Reihenfolge (aendert die Score-Zuordnung)
    with pytest.raises(AssertionError):
        _assert_mirror_matches(list(reversed(expected)), expected, "Karte")
    # (d) gleich lange Liste mit einem anderen Key
    with pytest.raises(AssertionError):
        _assert_mirror_matches([*expected[:-1], "unknown_key"], expected, "Karte")


# --- Wellbeing-Ausbau: Numerik + eigene Bilder ------------------------------


@pytest.mark.parametrize(
    ("score", "expected"),
    [(1, "very_bad"), (2, "awful"), (5, "okay"), (7, "good"), (9, "great"), (10, "excellent")],
)
def test_wellbeing_key_for_score_maps_numbers_to_keys(score, expected):
    """Score 1..10 wird auf den kanonischen Key abgebildet."""
    assert logic.wellbeing_key_for_score(score) == expected


@pytest.mark.parametrize("score", [0, 11, -1, None, "x", 3.9])
def test_wellbeing_key_for_score_rejects_invalid(score):
    """Ungültige Scores liefern None (3.9 wird bewusst nicht geraten)."""
    assert logic.wellbeing_key_for_score(score) is None


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("stufe1.png", "/local/stufe1.png"),
        ("local/stufe1.png", "/local/stufe1.png"),
        ("/local/wellbeing/stufe2.jpg", "/local/wellbeing/stufe2.jpg"),
        ("https://example.org/a.webp", "https://example.org/a.webp"),
        ("data:image/png;base64,AAAA", "data:image/png;base64,AAAA"),
        ("", None),
        ("stufe1.html", None),
        ("javascript:alert(1).png", None),
        ("/local/../secret.png", None),
        ("https://example.org/a.exe", None),
    ],
)
def test_normalize_wellbeing_image(raw, expected):
    """Bild-Referenzen werden defensiv normalisiert (nur PNG/JPG/WebP)."""
    assert logic.normalize_wellbeing_image(raw) == expected


def test_wellbeing_scale_includes_images_and_scores():
    """Die Skala trägt je Eintrag Key, Emoji, Score und optionales Bild."""
    scale = logic.wellbeing_scale({"good": "/local/good.png", "bogus": "x.png"})

    assert [entry["score"] for entry in scale] == list(range(1, 11))
    good = next(entry for entry in scale if entry["key"] == "good")
    assert good["image"] == "/local/good.png"
    assert all(entry["key"] != "bogus" for entry in scale)
    # Frische Kopien: Änderungen am Ergebnis dürfen const nicht verändern.
    scale[0]["label"] = "x"
    assert logic.WELLBEING_STATES[0]["label"] != "x"

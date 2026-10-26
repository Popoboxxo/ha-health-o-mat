"""Tests: Wochenbericht — Fenster, Kennzahlen, Markdown (REQ-HOM-118)."""

from __future__ import annotations

import importlib.util
import os
import sys
import types
from datetime import datetime, timedelta

_COMPONENT_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "custom_components", "health_o_mat")
)

_PKG = "_hom_report_test_pkg"
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

_NOW = datetime(2026, 10, 26, 18, 0)


def _fixture() -> dict:
    return {
        "drinks": [
            {"ts": "2026-10-26T09:00:00", "ml": 500, "type": "Wasser"},
            {"ts": "2026-10-25T10:00:00", "ml": 500, "type": "Wasser"},
            {"ts": "2026-10-24T11:00:00", "ml": 250, "type": "Kaffee"},
            # außerhalb des 7-Tage-Fensters
            {"ts": "2026-10-18T10:00:00", "ml": 1000, "type": "Wasser"},
            # voided: darf weder Summe noch Top-Drinks beeinflussen
            {
                "ts": "2026-10-26T12:00:00",
                "ml": 999,
                "type": "Wasser",
                "voided_at": "2026-10-26T12:05:00",
            },
        ],
        "readings": [
            {"ts": "2026-10-26T08:00:00", "sys": 130, "dia": 85},
            {"ts": "2026-10-24T08:00:00", "sys": 120, "dia": 80},
            {"ts": "2026-10-20T08:00:00", "sys": 110, "dia": 70},
            # Vorwoche (für den Trend), außerhalb der Wochen-Kennzahlen
            {"ts": "2026-10-16T08:00:00", "sys": 100, "dia": 65},
            {
                "ts": "2026-10-26T09:00:00",
                "sys": 200,
                "dia": 120,
                "voided_at": "2026-10-26T09:05:00",
            },
        ],
        "wellbeing_entries": [
            {"ts": "2026-10-26T09:00:00", "key": "good"},
            {"ts": "2026-10-24T09:00:00", "key": "okay"},
            {
                "ts": "2026-10-26T10:00:00",
                "key": "great",
                "voided_at": "2026-10-26T10:05:00",
            },
        ],
    }


_OPTIONS = {"daily_goal_ml": 1000}


# --- Fenster ----------------------------------------------------------------


def test_weekly_window_is_the_last_seven_days():
    start, end = reminders.weekly_window(_NOW)

    assert end == _NOW
    assert start == _NOW - timedelta(days=7)
    assert (end - start) == timedelta(days=7)


# --- Kennzahlen -------------------------------------------------------------


def test_collect_weekly_metrics_core_numbers():
    metrics = reminders.collect_weekly_metrics(_fixture(), _OPTIONS, _NOW)

    assert metrics["period_start"] == "2026-10-19"
    assert metrics["period_end"] == "2026-10-26"
    assert metrics["window_days"] == 7
    assert metrics["goal_ml"] == 1000
    assert metrics["total_ml"] == 1250
    assert metrics["avg_goal_percent"] == 17.9
    assert metrics["goal_days"] == 0
    assert metrics["goal_streak"] == 0
    assert metrics["top_drinks"] == [
        {"type": "Wasser", "ml": 1000},
        {"type": "Kaffee", "ml": 250},
    ]
    assert metrics["caffeine_mg"] == 100.0
    assert metrics["days_with_data"] == 4
    assert metrics["completeness_percent"] == 57.1


def test_collect_weekly_metrics_blood_pressure_and_trend():
    metrics = reminders.collect_weekly_metrics(_fixture(), _OPTIONS, _NOW)

    assert metrics["bp_count"] == 3  # voided + Vorwoche zählen nicht mit
    assert metrics["bp_avg_sys"] == 120.0
    assert metrics["bp_avg_dia"] == 78.3
    assert metrics["bp_trend"]["direction"] == "rising"
    assert metrics["bp_trend"]["sys_delta"] == 20.0


def test_collect_weekly_metrics_wellbeing_histogram():
    metrics = reminders.collect_weekly_metrics(_fixture(), _OPTIONS, _NOW)

    assert metrics["wellbeing_count"] == 2
    assert metrics["wellbeing_avg"] == 6.0
    assert metrics["wellbeing_max"] == 10
    assert metrics["wellbeing_histogram"] == {"good": 1, "okay": 1}


def test_collect_weekly_metrics_goal_days_and_streak():
    data = {
        "drinks": [
            {"ts": "2026-10-26T09:00:00", "ml": 1200, "type": "Wasser"},
            {"ts": "2026-10-25T09:00:00", "ml": 1000, "type": "Wasser"},
            {"ts": "2026-10-24T09:00:00", "ml": 1000, "type": "Wasser"},
        ],
        "readings": [],
        "wellbeing_entries": [],
    }

    metrics = reminders.collect_weekly_metrics(data, _OPTIONS, _NOW)

    assert metrics["goal_days"] == 3
    assert metrics["goal_streak"] == 3
    assert metrics["total_ml"] == 3200


def test_collect_weekly_metrics_empty_data_is_robust():
    metrics = reminders.collect_weekly_metrics({}, {}, _NOW)

    assert metrics["total_ml"] == 0
    assert metrics["avg_goal_percent"] == 0.0
    assert metrics["top_drinks"] == []
    assert metrics["bp_count"] == 0
    assert metrics["bp_avg_sys"] is None
    assert metrics["bp_trend"] is None
    assert metrics["wellbeing_avg"] is None
    assert metrics["wellbeing_histogram"] == {}
    assert metrics["caffeine_mg"] == 0.0
    assert metrics["days_with_data"] == 0
    assert metrics["completeness_percent"] == 0.0


def test_collect_weekly_metrics_ignores_invalid_and_future_timestamps():
    data = {
        "drinks": [
            {"ts": "kaputt", "ml": 500, "type": "Wasser"},
            {"ts": "2026-10-27T00:00:00", "ml": 500, "type": "Wasser"},
            {"ts": "2026-10-26T09:00:00", "ml": 250, "type": "Wasser"},
        ]
    }

    metrics = reminders.collect_weekly_metrics(data, _OPTIONS, _NOW)

    assert metrics["total_ml"] == 250


# --- Markdown ---------------------------------------------------------------


def test_render_weekly_report_markdown_german_golden():
    metrics = reminders.collect_weekly_metrics(_fixture(), _OPTIONS, _NOW)

    assert reminders.render_weekly_report_markdown(metrics, "Max", "de") == (
        "## Wochenbericht — Max\n"
        "\n"
        "**Zeitraum:** 19.10.2026 – 26.10.2026 (7 Tage)\n"
        "\n"
        "### Trinken\n"
        "- Gesamt: 1250 ml\n"
        "- Ø Tagesziel: 17.9 %\n"
        "- Ziel erreicht: 0 von 7 (1000 ml)\n"
        "- Serie: 0\n"
        "- Top-Getränke: Wasser (1000 ml), Kaffee (250 ml)\n"
        "\n"
        "### Blutdruck\n"
        "- Ø: 120.0/78.3 mmHg (3 Messungen)\n"
        "- Trend: steigend (+20.0 mmHg)\n"
        "\n"
        "### Wohlbefinden\n"
        "- Ø: 6.0 von 10 (2 Meldungen)\n"
        "- Verteilung: Okay (1), Gut (1)\n"
        "\n"
        "### Koffein\n"
        "- Geschätzt: 100.0 mg\n"
        "\n"
        "### Datenvollständigkeit\n"
        "- 4 von 7 Tagen mit Einträgen (57.1 %)"
    )


def test_render_weekly_report_markdown_english():
    metrics = reminders.collect_weekly_metrics(_fixture(), _OPTIONS, _NOW)
    text = reminders.render_weekly_report_markdown(metrics, "Max", "en")

    assert text.startswith("## Weekly report — Max")
    assert "**Period:** 2026-10-19 – 2026-10-26 (7 days)" in text
    assert "Goal reached: 0 of 7 (1000 ml)" in text
    assert "Trend: rising (+20.0 mmHg)" in text
    assert "Distribution: Okay (1), Good (1)" in text
    assert "Data completeness" in text


def test_render_weekly_report_markdown_empty_data_uses_placeholders():
    metrics = reminders.collect_weekly_metrics({}, _OPTIONS, _NOW)
    text = reminders.render_weekly_report_markdown(metrics, "Max", "de")

    assert "- Ø: —" in text
    assert "- Top-Getränke: —" in text
    assert "- Ø Tagesziel: 0.0 %" in text
    assert "- 0 von 7 Tagen mit Einträgen (0.0 %)" in text


def test_weekly_report_title_and_language_fallback():
    assert reminders.weekly_report_title("Max", "de") == "Wochenbericht — Max"
    assert reminders.weekly_report_title("Max", "en") == "Weekly report — Max"
    assert reminders.weekly_report_title("Max", None) == "Wochenbericht — Max"

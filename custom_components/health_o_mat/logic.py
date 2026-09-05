"""Reine Logik ohne Home-Assistant-Imports — unit-testbar.

Enthält Tagesfenster-Berechnung, Summenbildung und CSV-Zeilenerzeugung.
"""
from __future__ import annotations

from collections.abc import Iterable
import csv
import io
from datetime import datetime, timedelta
from typing import Any


def day_start(now: datetime, hour: int = 0, minute: int = 0) -> datetime:
    """Beginn des laufenden Tracking-Tags im Zeitzonen-Kontext von *now*.

    Bewusst on-read berechnet (kein Reset-Job): neustart- und DST-fest.
    """
    candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if now < candidate:
        candidate -= timedelta(days=1)
    return candidate


def window_sums(
    drinks: Iterable[dict[str, Any]],
    start: datetime,
    end: datetime,
) -> dict[str, Any]:
    """Summen über Getränke im Zeitfenster [start, end).

    Rückgabe: total_ml, count, breakdown ({Typ: ml}), last_ts.
    Erwartete Einträge: {"ts": ISO-String, "ml": int, "type": str}.
    """
    total = 0
    count = 0
    breakdown: dict[str, int] = {}
    last_ts: str | None = None
    for d in drinks:
        try:
            ts = datetime.fromisoformat(d["ts"])
        except (KeyError, TypeError, ValueError):
            continue
        if start <= ts < end:
            ml = int(d.get("ml", 0))
            total += ml
            count += 1
            dtype = str(d.get("type") or "Eigen")
            breakdown[dtype] = breakdown.get(dtype, 0) + ml
            if last_ts is None or ts.isoformat() > last_ts:
                last_ts = ts.isoformat()
    return {
        "total_ml": total,
        "count": count,
        "breakdown": breakdown,
        "last_ts": last_ts,
    }


def today_sums(
    drinks: Iterable[dict[str, Any]],
    now: datetime,
    hour: int = 0,
    minute: int = 0,
) -> dict[str, Any]:
    """Summen über Getränke im laufenden Tracking-Tag [day_start(now), now).

    Zentrale Aggregations-Funktion für alle Plattformen (sensor, binary_sensor, …) —
    vermeidet duplizierte `window_sums(drinks, day_start(now), now)`-Aufrufe.
    Rückgabe wie `window_sums`: total_ml, count, breakdown, last_ts.
    """
    return window_sums(drinks, day_start(now, hour, minute), now)


def avg_over_window(
    readings: Iterable[dict[str, Any]],
    key: str,
    now: datetime,
    days: int = 7,
) -> float | None:
    """Durchschnitt von `key` über Messungen im Zeitfenster [now - days, now].

    Bewusst on-read berechnet (kein Reset-Job): neustart- und DST-fest, analog
    zu `today_sums`/`window_sums`. Werte mit fehlendem/None `key` und Einträge
    mit ungültigem/fehlendem `ts` werden übersprungen.
    Rückgabe: None, falls kein gültiger Wert im Fenster liegt (statt 0, um
    "keine Daten" von "Durchschnitt 0" zu unterscheiden).
    """
    start = now - timedelta(days=days)
    values: list[float] = []
    for r in readings:
        try:
            ts = datetime.fromisoformat(r["ts"])
        except (KeyError, TypeError, ValueError):
            continue
        if start <= ts <= now:
            val = r.get(key)
            if val is not None:
                values.append(val)
    if not values:
        return None
    return sum(values) / len(values)


def yesterday_window(now: datetime, hour: int = 0, minute: int = 0) -> tuple[datetime, datetime]:
    """Fenster des Vortags [Start(Vortag), Start(heute))."""
    this_start = day_start(now, hour, minute)
    return this_start - timedelta(days=1), this_start


def drinks_csv_rows(drinks: Iterable[dict[str, Any]], person: str) -> list[list[str]]:
    """CSV-Zeilen für Getränke (Semikolon, Excel-DE-tauglich)."""
    rows = [["datum", "uhrzeit", "person", "getraenk", "menge_ml", "quelle"]]
    for d in sorted(drinks, key=lambda x: x.get("ts", "")):
        try:
            ts = datetime.fromisoformat(d["ts"])
            date_part = ts.strftime("%Y-%m-%d")
            time_part = ts.strftime("%H:%M:%S")
        except (TypeError, ValueError):
            date_part, time_part = "?", "?"
        rows.append(
            [
                date_part,
                time_part,
                person,
                str(d.get("type") or "Eigen"),
                str(int(d.get("ml", 0))),
                str(d.get("src") or ""),
            ]
        )
    return rows


def rows_to_csv_string(rows: list[list[str]]) -> str:
    """Zeilen → CSV-String mit Semikolon-Trenner."""
    buf = io.StringIO()
    writer = csv.writer(buf, delimiter=";", quoting=csv.QUOTE_MINIMAL)
    writer.writerows(rows)
    return buf.getvalue()


def csv_filename(kind: str, person: str, now: datetime) -> str:
    """Dateiname nach Konzept: health_o_mat_<kind>_<PERSON>_<YYYYMMDD-HHMM>.csv."""
    stamp = now.strftime("%Y%m%d-%H%M")
    safe_person = "".join(c if c.isalnum() else "_" for c in person).strip("_") or "alle"
    return f"health_o_mat_{kind}_{safe_person}_{stamp}.csv"


def csv_header_footer(rows_count: int, person: str, kind: str, now: datetime) -> tuple[str, str]:
    """Kopf- und Fußzeile des Exports."""
    header = (
        f"# HA Health-O-Mat Export — {kind} — Person: {person}\n"
        f"# Erstellt: {now.strftime('%Y-%m-%d %H:%M:%S')}"
    )
    footer = f"# Datensaetze: {rows_count}"
    return header, footer

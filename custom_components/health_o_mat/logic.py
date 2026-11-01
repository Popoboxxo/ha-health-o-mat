"""Reine Logik ohne Home-Assistant-Imports — unit-testbar.

Enthält Tagesfenster-Berechnung, Summenbildung und CSV-Zeilenerzeugung.
"""

from __future__ import annotations

import calendar
import csv
import io
import math
import re
import unicodedata
from collections.abc import Iterable, Mapping
from datetime import UTC, date, datetime, timedelta, tzinfo
from typing import Any

from .const import (
    AUDIT_LIMIT_OPTION,
    CAFFEINE_MG_PER_100ML,
    DEFAULT_AUDIT_LIMIT,
    LAB_CATEGORIES,
    LAB_CATEGORY_OTHER,
    LAB_MARKER_ALIASES,
    LAB_MARKERS,
    LAB_REPORT_MAX_ROWS,
    MAX_AUDIT_LIMIT,
    WELLBEING_STATES,
)


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
        ts = _normalize_ts(d.get("ts"), start)
        if ts is None:
            continue
        if _in_window(ts, start, end):
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
        ts = _normalize_ts(r.get("ts"), now)
        if ts is None:
            continue
        if _in_window(ts, start, now, inclusive_end=True):
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


def months_ago(now: datetime, months: int) -> datetime:
    """Zeitpunkt `months` Kalendermonate vor *now*.

    Kalendergenau (kein 30-Tage-Approx): der Tag wird auf die Länge des
    Zielmonats geklemmt (31.03. minus 1 Monat → 28./29.02.). Ein tz-aware
    `now` behält seine Zeitzone — das Fenster bleibt damit DST-fest.
    """
    total = now.month - 1 - int(months)
    year = now.year + total // 12
    month = total % 12 + 1
    day = min(now.day, calendar.monthrange(year, month)[1])
    return now.replace(year=year, month=month, day=day)


def _parse_ts(value: Any) -> datetime | None:
    """ISO-Zeitstempel robust parsen (ungültige/fehlende → None)."""
    try:
        return datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None


# --- Rückdatierung (REQ-HOM-120) -------------------------------------------

# Zukunfts-Toleranz: Uhren zwischen Browser und Server driften leicht; bis
# 5 Minuten "Zukunft" gilt als "jetzt" statt als Fehler.
ENTRY_TS_FUTURE_TOLERANCE = timedelta(minutes=5)

# Untergrenze: ältere Werte sind keine plausiblen Erfassungen (und würden in
# Zeitfenster-/Trend-Berechnungen nur Rauschen erzeugen).
ENTRY_TS_MIN = datetime(1900, 1, 1, tzinfo=UTC)

# Einheitliche Fehlermeldung für Services/WS (beide Schreibwege).
ENTRY_TS_INVALID_MESSAGE = (
    "Ungültiger Zeitpunkt '{value}' — erwartet ISO 8601 (z. B. 2026-10-24T18:30), "
    "höchstens 5 Minuten in der Zukunft und nicht vor 1900."
)


def parse_entry_timestamp(
    value: Any,
    *,
    now: datetime | None = None,
    tz: tzinfo | None = None,
) -> datetime | None:
    """Nutzer-Zeitstempel (ISO 8601) validieren und lokalisieren.

    HA-frei: naive Werte werden in der übergebenen Zeitzone interpretiert
    (``tz``), sonst in der Zone von ``now`` bzw. der lokalen Systemzone. Ein
    tz-aware Wert wird in dieselbe Zone umgerechnet, damit der Rückgabewert
    einheitlich lokal (mit Offset) ist.

    Rückgabe ``None`` bei: fehlendem/nicht-String-Wert, kaputtem ISO-String,
    Zeitpunkten mehr als ``ENTRY_TS_FUTURE_TOLERANCE`` in der Zukunft und
    Werten vor ``ENTRY_TS_MIN`` (1900-01-01).
    """
    if not isinstance(value, str):
        return None
    raw = value.strip()
    if not raw:
        return None
    # `fromisoformat` akzeptiert "Z" erst ab Python 3.11; defensiv normalisieren.
    if raw[-1:] in ("Z", "z"):
        raw = raw[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None

    reference = now if now is not None else datetime.now().astimezone()
    zone = tz or reference.tzinfo
    if zone is None:
        zone = datetime.now().astimezone().tzinfo

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=zone)
    else:
        parsed = parsed.astimezone(zone)

    # Grenzprüfung im UTC-Raum: DST-unabhängig und ohne naive/aware-Mischung.
    ts_utc = parsed.astimezone(UTC)
    ref_aware = reference if reference.tzinfo is not None else reference.replace(tzinfo=zone)
    now_utc = ref_aware.astimezone(UTC)
    if ts_utc > now_utc + ENTRY_TS_FUTURE_TOLERANCE:
        return None
    if ts_utc < ENTRY_TS_MIN:
        return None
    return parsed


def _align_tz(ts: datetime, reference: datetime) -> datetime:
    """Naive und tz-aware Zeitstempel vergleichbar machen.

    Alt-Bestände (< M-3) schrieben naive Zeitstempel, neue tz-aware. Ohne
    Angleichung würde der Vergleich `datetime` mit/ohne tzinfo einen TypeError
    werfen. Die Referenz-Zeitzone (bzw. Naivität) wird auf den Wert übertragen.
    """
    if ts.tzinfo is None and reference.tzinfo is not None:
        return ts.replace(tzinfo=reference.tzinfo)
    if ts.tzinfo is not None and reference.tzinfo is None:
        return ts.replace(tzinfo=None)
    return ts


def _normalize_ts(value: Any, reference: datetime) -> datetime | None:
    """Zentraler, HA-freier Zeitstempel-Normalisierer.

    Parst `value` defensiv (ungültige/fehlende Werte → None, werden vom
    Aufrufer übersprungen) und gleicht die Zeitzone an `reference` an:
    ein naiver Wert übernimmt die Zeitzone des übergebenen Fenster-/`now`-Werts
    (`reference.tzinfo`), ein tz-aware Wert bleibt UNVERÄNDERT. Damit ist der
    Vergleich mit einem tz-aware Fenster (z. B. aus `dt_util.now()`) auch für
    Alt-Bestand mit naiven Zeitstempeln (< M-3) ohne TypeError möglich.
    """
    ts = _parse_ts(value)
    if ts is None:
        return None
    return _align_tz(ts, reference)


def _in_window(
    ts: datetime, start: datetime, end: datetime, *, inclusive_end: bool = False
) -> bool:
    """Defensiver Fenstervergleich; unerwarteter TypeError → False.

    Prüft `start <= ts < end` (bzw. `start <= ts <= end` mit
    `inclusive_end=True`). `_normalize_ts` sollte gemischte Naivität bereits
    ausgeschlossen haben — der Try/Except ist die zweite Verteidigungslinie,
    damit ein unerwarteter Typkonflikt einen Sensor-Read nicht zum Absturz
    bringt (sondern den Eintrag still übergeht).
    """
    try:
        if inclusive_end:
            return start <= ts <= end
        return start <= ts < end
    except TypeError:
        return False


def _is_before(ts: datetime, reference: datetime) -> bool:
    """Defensiver `<`-Vergleich; unerwarteter TypeError → False."""
    try:
        return ts < reference
    except TypeError:
        return False


def partition_by_cutoff(
    items: Iterable[dict[str, Any]],
    cutoff: datetime,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Teilt Einträge in (recent, archived) anhand eines Stichtags.

    Einträge mit `ts < cutoff` wandern ins Archiv; alles ab `cutoff`
    (inklusive) sowie Einträge ohne gültigen Zeitstempel bleiben erhalten —
    unbekannte/fremde Daten werden nie stillschweigend archiviert.
    Bewusst on-read als reine Funktion (kein Reset-Job, REQ-HOM-109).
    """
    recent: list[dict[str, Any]] = []
    archived: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            recent.append(item)  # type: ignore[arg-type]
            continue
        ts = _normalize_ts(item.get("ts"), cutoff)
        if ts is None:
            recent.append(item)
            continue
        (archived if _is_before(ts, cutoff) else recent).append(item)
    return recent, archived


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


# --- WHO-Blutdruck-Klassifikation (REQ-HOM-001) ---
#
# Schwellen in mmHg. Beide Achsen werden separat eingestuft; die Gesamt-
# kategorie ist die HÖHERE der beiden (Vorgabe REQ-HOM-001). Grenzen sind
# inklusive Untergrenze, exklusive Obergrenze:
#     optimal     sys <120  / dia <80
#     normal      sys 120–129 / dia 80–84
#     high_normal sys 130–139 / dia 85–89
#     grade_1     sys 140–159 / dia 90–99
#     grade_2     sys 160–179 / dia 100–109
#     grade_3     sys >=180  / dia >=110
# "Hypertensive Krise" überlagert Grad 3 nur, wenn BEIDE Werte die strengen
# Grenzen überschreiten (sys >180 UND dia >120). Die AHA-Definition lautet
# sys >180 und/oder dia >120; hier bewusst konservativer, damit eine isolierte
# systolische Erhöhung (z. B. 200/90) als Grad 3 und nicht als Krise gilt.
BP_CATEGORY_OPTIMAL = "optimal"
BP_CATEGORY_NORMAL = "normal"
BP_CATEGORY_HIGH_NORMAL = "high_normal"
BP_CATEGORY_GRADE_1 = "grade_1"
BP_CATEGORY_GRADE_2 = "grade_2"
BP_CATEGORY_GRADE_3 = "grade_3"
BP_CATEGORY_CRISIS = "crisis"

# Rangfolge: höherer Rang = schwerere Kategorie ("höherer Wert zählt").
BP_CATEGORY_RANK: dict[str, int] = {
    BP_CATEGORY_OPTIMAL: 0,
    BP_CATEGORY_NORMAL: 1,
    BP_CATEGORY_HIGH_NORMAL: 2,
    BP_CATEGORY_GRADE_1: 3,
    BP_CATEGORY_GRADE_2: 4,
    BP_CATEGORY_GRADE_3: 5,
    BP_CATEGORY_CRISIS: 6,
}


def _systolic_category(value: Any) -> str | None:
    """WHO-Kategorie der systolischen Achse (None → None)."""
    if value is None:
        return None
    value = int(value)
    if value < 120:
        return BP_CATEGORY_OPTIMAL
    if value < 130:
        return BP_CATEGORY_NORMAL
    if value < 140:
        return BP_CATEGORY_HIGH_NORMAL
    if value < 160:
        return BP_CATEGORY_GRADE_1
    if value < 180:
        return BP_CATEGORY_GRADE_2
    return BP_CATEGORY_GRADE_3


def _diastolic_category(value: Any) -> str | None:
    """WHO-Kategorie der diastolischen Achse (None → None)."""
    if value is None:
        return None
    value = int(value)
    if value < 80:
        return BP_CATEGORY_OPTIMAL
    if value < 85:
        return BP_CATEGORY_NORMAL
    if value < 90:
        return BP_CATEGORY_HIGH_NORMAL
    if value < 100:
        return BP_CATEGORY_GRADE_1
    if value < 110:
        return BP_CATEGORY_GRADE_2
    return BP_CATEGORY_GRADE_3


def bp_category(systolic: Any, diastolic: Any) -> str | None:
    """WHO-Kategorie einer Blutdruckmessung (REQ-HOM-001).

    Liefert den Kategorie-Key (optimal/normal/high_normal/grade_1/grade_2/
    grade_3/crisis) oder None, wenn ein Wert fehlt — der Sensor übersetzt
    None bzw. das Fehlen jeder Messung zu `unknown`. Es zählt die höhere der
    beiden Achsen-Kategorien. `systolic`/`diastolic` dürfen int/float/str sein.
    """
    if systolic is None or diastolic is None:
        return None
    sys_val = int(systolic)
    dia_val = int(diastolic)
    if sys_val > 180 and dia_val > 120:
        return BP_CATEGORY_CRISIS
    sys_cat = _systolic_category(sys_val)
    dia_cat = _diastolic_category(dia_val)
    return max((sys_cat, dia_cat), key=lambda cat: BP_CATEGORY_RANK[cat])


# --- Trend-Metriken (REQ-HOM-002) ---

# Ab diesem Betrag (mmHg) gilt ein 7-Tage-Mittelwert-Delta als "stabil".
# Kleinere Änderungen liegen im Rauschen einzelner Messungen.
BP_TREND_STABLE_DELTA_MMHG = 2.0


def _avg_in_range(
    readings: Iterable[dict[str, Any]], key: str, start: datetime, end: datetime
) -> float | None:
    """Mittelwert von `key` in [start, end) — half-open, tz-tolerant.

    None, falls kein gültiger Wert im Fenster liegt (unterscheidet "keine
    Daten" von "Durchschnitt 0"). Alt-Bestand mit naiven Zeitstempeln wird
    an die Referenz-Zeitzone angeglichen (`_align_tz`).
    """
    values: list[float] = []
    for r in readings:
        ts = _normalize_ts(r.get("ts"), start)
        if ts is None:
            continue
        if _in_window(ts, start, end):
            val = r.get(key)
            if val is not None:
                values.append(val)
    if not values:
        return None
    return sum(values) / len(values)


def _count_valid_bp(readings: Iterable[dict[str, Any]], start: datetime, end: datetime) -> int:
    """Anzahl Messungen mit sys UND dia im Fenster [start, end)."""
    count = 0
    for r in readings:
        ts = _normalize_ts(r.get("ts"), start)
        if ts is None:
            continue
        has_both = r.get("sys") is not None and r.get("dia") is not None
        if has_both and _in_window(ts, start, end):
            count += 1
    return count


def drinks_trend(
    drinks: Iterable[dict[str, Any]],
    now: datetime,
    hour: int = 0,
    minute: int = 0,
) -> dict[str, Any] | None:
    """Trink-Trend: heutige Menge vs. Tages-Ø der Vorwoche in Prozent (on-read).

    "Vorwoche" = die sieben vollständigen Tracking-Tage unmittelbar vor dem
    laufenden Tag (gleitendes Fenster, Tagesgrenze via `daily_reset_hour`).
    Das Ø wird immer durch 7 geteilt — Tage ohne Buchung zählen als 0.
    Rückgabe: {"percent", "today_ml", "prev_week_avg_ml"} oder None, wenn der
    Vorwochen-Schnitt 0 ist (Prozentänderung gegenüber 0 ist undefiniert).
    """
    drinks = list(drinks)
    today = today_sums(drinks, now, hour, minute)
    today_start = day_start(now, hour, minute)
    window_start = today_start - timedelta(days=7)
    prev_week = window_sums(drinks, window_start, today_start)
    avg = prev_week["total_ml"] / 7
    if avg <= 0:
        return None
    percent = (today["total_ml"] - avg) / avg * 100
    return {
        "percent": round(percent, 1),
        "today_ml": today["total_ml"],
        "prev_week_avg_ml": round(avg, 1),
    }


def bp_trend(
    readings: Iterable[dict[str, Any]],
    now: datetime,
    days: int = 7,
    min_readings: int = 3,
) -> dict[str, Any] | None:
    """Blutdruck-Trend über zwei aneinandergrenzende 7-Tage-Mittelwerte.

    Vergleicht das Mittel der letzten `days` Tage mit dem der unmittelbar
    davorliegenden `days` Tage. Richtung primär aus dem systolischen Delta
    (|delta| < BP_TREND_STABLE_DELTA_MMHG → "stable"); dia-Delta ist Attribut.
    Mindestdatenschutz (REQ-HOM-002): < `min_readings` gültige Messungen
    (sys UND dia) im betrachteten Zeitraum → None (Sensor: `unknown`).
    """
    readings = list(readings)
    current_start = now - timedelta(days=days)
    previous_start = current_start - timedelta(days=days)
    if _count_valid_bp(readings, previous_start, now) < min_readings:
        return None

    sys_recent = _avg_in_range(readings, "sys", current_start, now)
    sys_previous = _avg_in_range(readings, "sys", previous_start, current_start)
    if sys_recent is None or sys_previous is None:
        return None

    dia_recent = _avg_in_range(readings, "dia", current_start, now)
    dia_previous = _avg_in_range(readings, "dia", previous_start, current_start)
    dia_delta = (
        dia_recent - dia_previous if dia_recent is not None and dia_previous is not None else None
    )

    sys_delta = sys_recent - sys_previous
    if abs(sys_delta) < BP_TREND_STABLE_DELTA_MMHG:
        direction = "stable"
    elif sys_delta > 0:
        direction = "rising"
    else:
        direction = "falling"

    return {
        "direction": direction,
        "sys_delta": round(sys_delta, 1),
        "dia_delta": round(dia_delta, 1) if dia_delta is not None else None,
        "sys_avg_recent": round(sys_recent, 1),
        "sys_avg_previous": round(sys_previous, 1),
    }


# --- Streak (REQ-HOM-003) ---


def _daily_totals_by_day(
    drinks: Iterable[dict[str, Any]], hour: int, minute: int
) -> dict[date, int]:
    """Summierte Trinkmenge je Tracking-Tag, geschlüsselt nach Kalendertag.

    Der Schlüssel ist das DATUM des Tagesbeginns (`day_start`) — bewusst ein
    reines `date` statt eines tz-aware `datetime`: über eine DST-Umstellung
    hinweg ändert sich der UTC-Offset, sodass ein schrittweises
    `+ timedelta(days=1)` auf einem aware-Wert andere Zeitpunkte träfe als die
    aus Buchungen abgeleiteten Tagesschlüssel (stiller Serienbruch). Kalender-
    tage sind davon unabhängig.
    """
    totals: dict[date, int] = {}
    for d in drinks:
        ts = _parse_ts(d.get("ts"))
        if ts is None:
            continue
        key = day_start(ts, hour, minute).date()
        totals[key] = totals.get(key, 0) + int(d.get("ml", 0) or 0)
    return totals


def goal_streak(
    drinks: Iterable[dict[str, Any]],
    daily_goal_ml: int,
    now: datetime,
    hour: int = 0,
    minute: int = 0,
) -> dict[str, int]:
    """Serie von Tagen mit erreichtem Tagesziel (REQ-HOM-003), on-read.

    `current_streak`: Anzahl aufeinanderfolgender Tracking-Tage bis heute, an
    denen das Tagesziel erreicht wurde. Der heutige, noch laufende Tag zählt nur
    mit, wenn das Ziel BEREITS erreicht ist — sonst endet die Serie gestern
    (andernfalls würde jede Serie jeden Morgen „abreißen").
    `best_streak`: längste Serie über die gesamte vorhandene Historie, ebenfalls
    on-read. Tage ohne Buchung (Lücke) brechen die Serie.

    Tagesgrenze via `day_start(now, hour, minute)` (`daily_reset_hour`) — kein
    Reset-Job, neustart- und DST-fest. Leere Historie oder Ziel <= 0 → 0/0.
    """
    goal = int(daily_goal_ml)
    if goal <= 0:
        return {"current_streak": 0, "best_streak": 0}
    totals = _daily_totals_by_day(drinks, hour, minute)
    if not totals:
        return {"current_streak": 0, "best_streak": 0}

    today = day_start(now, hour, minute).date()
    earliest = min(totals)

    # Laufende Serie: ab heute (falls Ziel erreicht) bzw. ab gestern rückwärts.
    current = 0
    cursor = today if totals.get(today, 0) >= goal else today - timedelta(days=1)
    while cursor >= earliest and totals.get(cursor, 0) >= goal:
        current += 1
        cursor -= timedelta(days=1)

    # Längste Serie über die gesamte Historie [earliest, today].
    best = 0
    run = 0
    day = earliest
    while day <= today:
        if totals.get(day, 0) >= goal:
            run += 1
            best = max(best, run)
        else:
            run = 0
        day += timedelta(days=1)

    return {"current_streak": current, "best_streak": best}


# --- Koffein (REQ-HOM-004) ---


def caffeine_today(
    drinks: Iterable[dict[str, Any]],
    now: datetime,
    hour: int = 0,
    minute: int = 0,
) -> dict[str, Any]:
    """Geschätzte Koffeinzufuhr des laufenden Tracking-Tags in mg (REQ-HOM-004).

    Nutzt das heutige Tagesfenster (`today_sums`, Tagesgrenze via
    `daily_reset_hour`) und die grobe Schätztabelle `CAFFEINE_MG_PER_100ML`
    (mg pro 100 ml). Unbekannte Typen und „Eigen" liefern 0 mg.
    Rückgabe: {"total_mg": float, "breakdown": {Typ: mg}} — der Breakdown
    enthält nur Typen mit > 0 mg (koffeinfreie Getränke bleiben außen vor).
    Bewusst on-read (kein Reset-Job), neustart- und DST-fest.
    """
    sums = today_sums(drinks, now, hour, minute)
    total_mg = 0.0
    breakdown: dict[str, float] = {}
    for drink_type, ml in sums["breakdown"].items():
        per_100 = CAFFEINE_MG_PER_100ML.get(drink_type, 0.0)
        mg = round(int(ml) * per_100 / 100.0, 1)
        if mg > 0:
            breakdown[drink_type] = mg
            total_mg += mg
    return {"total_mg": round(total_mg, 1), "breakdown": breakdown}


# --- Hydration-Pace (Konzept docs/CONCEPT-UI.md §6.3) ---

# Toleranzband um den linearen Soll-Stand, als Anteil des Tagesziels.
# |delta_ml| <= goal * PACE_TOLERANCE_RATIO gilt als "on_track".
PACE_TOLERANCE_RATIO = 0.1

# Nominale Dauer eines Tracking-Tags in Sekunden. Die Tagesgrenze
# (`daily_reset_hour`/`daily_reset_minute`) verschiebt nur den START des
# Fensters, nicht seine Länge — der Anteil ist daher verstrichene Sekunden
# geteilt durch 24 h (lineare Näherung, DST-tolerant wie `day_start`).
PACE_DAY_SECONDS = 86400.0


def hydration_pace(
    drinks: Iterable[dict[str, Any]],
    now: datetime,
    goal_ml: Any,
    hour: int = 0,
    minute: int = 0,
) -> dict[str, Any]:
    """Trink-Pace des laufenden Tracking-Tags: Ist-Stand vs. linearer Soll-Verlauf.

    HA-frei und on-read (kein Reset-Job), konsistent mit `today_sums`/
    `day_start` — neustart- und DST-fest.

    Fenster = laufender Tracking-Tag [`day_start(now, hour, minute)`, `now`).
    `expected_ml` ist der lineare Soll-Stand "gleichmäßig über den Tag"
    (`goal * Anteil des Tages`, Anteil auf [0, 1] geklemmt), `delta_ml` die
    Abweichung Ist − Soll, `forecast_ml` die Hochrechnung auf das Tagesende
    (`actual / Anteil`; darf das Ziel überschreiten).

    Rückgabe (alle Werte robust, keine Exception):
        status: "ahead" | "on_track" | "behind" | None
            None nur, wenn kein positives Ziel gesetzt ist. `goal_reached`
            ist bewusst NICHT Teil dieser Funktion — die UI-Schicht vergibt es
            aus `actual_ml >= goal_ml`.
        actual_ml: heutige Summe (`today_sums`), auch ohne Ziel berechnet.
        expected_ml: Soll-Stand, gerundet auf 1 Nachkommastelle; None ohne Ziel.
        delta_ml: actual − expected, 1 Nachkommastelle; None ohne Ziel.
        forecast_ml: Hochrechnung auf Tagesende, 1 Nachkommastelle; None ohne
            Ziel ODER exakt am Tagesbeginn (Anteil 0 → keine Division durch 0).
        percent: actual / goal * 100, 1 Nachkommastelle; 0.0 ohne Ziel.

    `goal_ml <= 0`/ungültig ⇒ kein Soll-Verlauf: status/expected/delta/forecast
    None, percent 0.0 (der Ist-Stand bleibt trotzdem erhalten).
    """
    try:
        goal = int(goal_ml)
    except (TypeError, ValueError):
        goal = 0

    actual_ml = int(today_sums(drinks, now, hour, minute)["total_ml"])

    if goal <= 0:
        return {
            "status": None,
            "actual_ml": actual_ml,
            "expected_ml": None,
            "delta_ml": None,
            "forecast_ml": None,
            "percent": 0.0,
        }

    elapsed = (now - day_start(now, hour, minute)).total_seconds()
    fraction = min(max(elapsed / PACE_DAY_SECONDS, 0.0), 1.0)
    expected = goal * fraction
    delta = actual_ml - expected
    tolerance = goal * PACE_TOLERANCE_RATIO
    if delta > tolerance:
        status = "ahead"
    elif delta < -tolerance:
        status = "behind"
    else:
        status = "on_track"

    return {
        "status": status,
        "actual_ml": actual_ml,
        "expected_ml": round(expected, 1),
        "delta_ml": round(delta, 1),
        "forecast_ml": None if fraction <= 0.0 else round(actual_ml / fraction, 1),
        "percent": round(actual_ml / goal * 100, 1),
    }


# --- Wohlbefinden-Score (REQ-HOM-112) ---


def wellbeing_score(key: Any) -> int | None:
    """Numerischer Wohlbefinden-Score (1 = schlechtester … N = bester Wert).

    Der Score ist rein abgeleitet (on-read, keine eigene Persistenz): er
    ergibt sich reihenfolgetreu aus `WELLBEING_STATES` (aufsteigende
    Qualität very_bad … great) — der 0-basierte Index + 1 ist der Score.

    Die Skala ist bewusst NICHT hartkodiert, sondern folgt der Länge der
    Zustandsliste: eine neue Stufe in `const.WELLBEING_STATES` schlägt
    automatisch durch (neuer Score = Index + 1). Die Liste wird deshalb zur
    AUFrufZEIT aus dem Modul-Global gelesen (kein Default-Argument), damit
    Tests sie monkeypatchen können.

    Unbekannter Key, fehlender Wert oder ein Nicht-String → None (HA zeigt
    `unknown`). NIEMALS 0: 0 würde den schlechtesten Wert bedeuten und den
    Verlauf verfälschen.

    Import-Richtung: `logic` → `const`; `const` importiert NICHTS aus dem
    Paket — daher keine Zirkularität. HA-frei (kein homeassistant-Import).
    """
    if not isinstance(key, str) or not key:
        return None
    for index, state in enumerate(WELLBEING_STATES):
        if state.get("key") == key:
            return index + 1
    return None


def wellbeing_key_for_score(score: Any) -> str | None:
    """Wellbeing-Key zu einem numerischen Score (1 … N).

    Der Score wird auf eine Ganzzahl gerundet; Werte außerhalb 1..N und
    nicht-numerische Eingaben liefern None. Die Skala folgt derselben
    Reihenfolge wie `wellbeing_score` (Index + 1).
    """
    if isinstance(score, bool):
        return None
    if isinstance(score, float) and not score.is_integer():
        return None
    try:
        value = int(score)
    except (TypeError, ValueError):
        return None
    if value < 1 or value > len(WELLBEING_STATES):
        return None
    return WELLBEING_STATES[value - 1].get("key")


# Erlaubte Bildtypen für eigene Wellbeing-Bilder. Bewusst klein gehalten:
# die URL landet als <img src> im Frontend, also nur harmlose Bildformate.
_IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp")
_IMAGE_DATA_PREFIXES = (
    "data:image/png;base64,",
    "data:image/jpeg;base64,",
    "data:image/jpg;base64,",
    "data:image/webp;base64,",
)


def normalize_wellbeing_image(value: Any) -> str | None:
    """Bild-Referenz defensiv normalisieren (None = keine/ungültige Angabe).

    Akzeptiert:
    - absolute HTTP(S)-URLs,
    - absolute Pfade wie ``/local/wellbeing/1.png``,
    - relative Dateinamen; diese werden zu ``/local/<name>`` (HA-www).
    - Base64-Data-URIs für PNG/JPEG/WebP.

    Abgelehnt werden leere Werte, ``javascript:``/``file:``/``data:``-URIs mit
    fremdem MIME-Typ sowie Pfade ohne erlaubte Bild-Endung.
    """
    if not isinstance(value, str):
        return None
    ref = value.strip()
    if not ref:
        return None
    lowered = ref.lower()
    if lowered.startswith("data:"):
        return ref if lowered.startswith(_IMAGE_DATA_PREFIXES) else None
    if lowered.startswith(("javascript:", "vbscript:", "file:")):
        return None
    if lowered.startswith("//"):
        return None
    if lowered.startswith(("http://", "https://")):
        base = lowered.split("?", 1)[0].split("#", 1)[0]
        return ref if base.endswith(_IMAGE_EXTENSIONS) else None
    if ".." in ref.replace("\\", "/").split("/"):
        return None
    if not lowered.startswith("/"):
        if lowered.startswith("local/"):
            ref = f"/{ref}"
        else:
            ref = f"/local/{ref.lstrip('/')}"
        lowered = ref.lower()
    base = lowered.split("?", 1)[0].split("#", 1)[0]
    if not base.endswith(_IMAGE_EXTENSIONS):
        return None
    return ref


def normalize_wellbeing_images(value: Any) -> dict[str, str]:
    """Options-Mapping ``{key: bild}`` auf gültige Keys + Bild-Refs reduzieren."""
    if not isinstance(value, dict):
        return {}
    valid_keys = {state.get("key") for state in WELLBEING_STATES}
    out: dict[str, str] = {}
    for key, raw in value.items():
        if key not in valid_keys:
            continue
        image = normalize_wellbeing_image(raw)
        if image:
            out[key] = image
    return out


def wellbeing_scale(images: Any = None) -> list[dict[str, Any]]:
    """Kanonische Wellbeing-Skala inkl. optionaler eigener Bilder.

    Liefert frische Dicts (keine geteilten Referenzen auf ``const``), damit
    Aufrufer die Liste gefahrlos an das Frontend weitergeben können.
    ``image`` ist ``None``, wenn für den Key kein (gültiges) Bild konfiguriert
    ist — das Frontend fällt dann auf das Emoji zurück.
    """
    normalized = normalize_wellbeing_images(images)
    return [
        {
            "key": state["key"],
            "label": state["label"],
            "emoji": state["emoji"],
            "icon": state["icon"],
            "image": normalized.get(state["key"]),
            "score": index + 1,
        }
        for index, state in enumerate(WELLBEING_STATES)
    ]


# --- Korrigierbarkeit / Audit (REQ-HOM-115) --------------------------------


def audit_limit_from_options(options: Any) -> int:
    """Audit-Cap aus den Entry-Options (HA-frei, defensiv).

    Vertrag:
    - fehlend/``None``/nicht-numerisch/negativ → ``DEFAULT_AUDIT_LIMIT``
    - ``0`` = unbegrenzt (bewusst KEIN Default-Ersatz)
    - Werte über ``MAX_AUDIT_LIMIT`` werden auf das Maximum begrenzt
    - Booleans gelten als ungültig (``True`` ist keine Zahl 1)

    ``options`` darf ``None`` oder ein beliebiger Nicht-Mapping-Wert sein
    (z. B. ein Mock/Fake in Tests) — dann greift der Default.
    """
    if not isinstance(options, Mapping):
        return DEFAULT_AUDIT_LIMIT
    raw = options.get(AUDIT_LIMIT_OPTION)
    if raw is None or isinstance(raw, bool):
        return DEFAULT_AUDIT_LIMIT
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return DEFAULT_AUDIT_LIMIT
    if value < 0:
        return DEFAULT_AUDIT_LIMIT
    return min(value, MAX_AUDIT_LIMIT)


# Laborwerte als eigenes Verlaufsziel (REQ-HOM-122). Bewusst NICHT in
# `REMOVE_LAST_METHOD_BY_KIND`: ein globales "letzter Laborwert" wäre
# mehrdeutig — das Undo ist marker-spezifisch (`remove_last_lab_reading`).
HISTORY_KIND_LAB: str = "lab_values"

# Kanonische Korrektur-Ziele (Store-Listen + Methoden je Ziel).
HISTORY_KINDS: tuple[str, ...] = (
    "drinks",
    "blood_pressure",
    "wellbeing",
    HISTORY_KIND_LAB,
)

# Kanonisches Ziel → Store-Listenname (Rohlisten, inkl. voided Einträge).
HISTORY_LIST_BY_KIND: dict[str, str] = {
    "drinks": "drinks",
    "blood_pressure": "readings",
    "wellbeing": "wellbeing_entries",
    HISTORY_KIND_LAB: "lab_readings",
}

# Kanonisches Ziel → Store-Methoden (ein Name, kein Zweitweg in der API).
VOID_METHOD_BY_KIND: dict[str, str] = {
    "drinks": "void_drink",
    "blood_pressure": "void_reading",
    "wellbeing": "void_wellbeing",
    HISTORY_KIND_LAB: "void_lab_reading",
}
RESTORE_METHOD_BY_KIND: dict[str, str] = {
    "drinks": "restore_drink",
    "blood_pressure": "restore_reading",
    "wellbeing": "restore_wellbeing",
    HISTORY_KIND_LAB: "restore_lab_reading",
}
REMOVE_LAST_METHOD_BY_KIND: dict[str, str] = {
    "drinks": "remove_last_drink",
    "blood_pressure": "remove_last_reading",
    "wellbeing": "remove_last_wellbeing",
}

_KIND_ALIASES: dict[str, str] = {
    "drink": "drinks",
    "drinks": "drinks",
    "blood_pressure": "blood_pressure",
    # Toleranter Alias: der Store führt Messungen intern als `readings`.
    "reading": "blood_pressure",
    "readings": "blood_pressure",
    "wellbeing": "wellbeing",
    "wellbeing_entries": "wellbeing",
    # Laborwerte (REQ-HOM-122): `normalize_history_kind` löst ausschließlich
    # über dieses Dict auf — ohne die Aliase bliebe `kind=lab_values` unbekannt.
    "lab_value": HISTORY_KIND_LAB,
    "lab_values": HISTORY_KIND_LAB,
    "lab_readings": HISTORY_KIND_LAB,
}


def normalize_history_kind(kind: Any) -> str | None:
    """Freies ``kind`` → kanonisches Korrektur-Ziel (``None`` = unbekannt).

    Anders als ``ws_api.normalize_undo_kind`` gibt es hier KEINEN
    Leer-Default: ``void_entry``/``restore_entry``/``list_history`` brauchen
    ein explizites Ziel, sonst wäre eine Löschung mehrdeutig.
    """
    if not isinstance(kind, str):
        return None
    return _KIND_ALIASES.get(kind.strip().lower())


# --- Laborwerte: Marker-Auflösung + Einheiten-Konvertierung (REQ-HOM-122) ---


def _slugify_lab_marker_name(name: str) -> str:
    """Freitext-Marker-Name -> slug (ASCII, Kleinbuchstaben, Unterstriche).

    Einfache, bewusst nicht-internationalisierte Normalisierung (YAGNI) —
    ausreichend für die Admin-Eingabe eines Custom-Marker-Namens.
    """
    slug = re.sub(r"[^a-z0-9]+", "_", name.strip().lower()).strip("_")
    return slug or "marker"


def _norm_unit(value: Any) -> str:
    """Einheiten-Vergleich case-/whitespace-/kompatibilitäts-insensitiv (HA-frei).

    ``NFKC`` faltet typografische Varianten derselben Einheit auf dieselbe Form —
    insbesondere ``µ`` (U+00B5, Mikro-Zeichen) auf ``μ`` (U+03BC, griechisches My),
    wie es Labor-CSVs aus Fremdsystemen liefern. Betrifft ausschließlich den
    VERGLEICH; gespeichert/angezeigt wird weiterhin die kanonische Einheit.
    """
    text = unicodedata.normalize("NFKC", str(value if value is not None else ""))
    return text.strip().lower()


def _previous_marker_keys(previous: Any) -> dict[str, str]:
    """``stripped name -> key`` from already persisted markers (first hit wins)."""
    keys: dict[str, str] = {}
    if not isinstance(previous, list):
        return keys
    for item in previous:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        key = str(item.get("key") or "").strip().lower()
        if name and key:
            keys.setdefault(name, key)
    return keys


def normalize_lab_custom_markers(raw: Any, previous: Any = None) -> list[dict]:
    """`entry.options["lab_custom_markers"]` normalisieren (HA-frei, §2.2).

    Jeder Eintrag erhält einen stabilen `key` (slugify aus `name`, bei
    Kollision mit einem Katalog-Key ODER einem bereits vergebenen Custom-Key
    dieses Aufrufs mit `_2`/`_3`/... suffixiert — Reihenfolge bleibt stabil).
    Unbrauchbare Einträge (kein `name`/`unit`) werden übersprungen, kein
    Absturz bei Teil-Murks aus altem Options-Bestand.

    REQ-HOM-130: `previous` schützt den `key` gegen Fremd-Client-Drift (A-2) —
    ein Eintrag ohne `key`, dessen `name` exakt einem gespeicherten Marker
    entspricht, erbt dessen `key` statt neu geslugt zu werden (der `key` ist
    Teil der `unique_id`). Ein explizit gesendeter `key` gewinnt immer.
    A-1: eine `category` außerhalb von `LAB_CATEGORIES` fällt auf `other`.
    """
    if not isinstance(raw, list):
        return []
    inherited = _previous_marker_keys(previous)
    known_categories = {category["key"] for category in LAB_CATEGORIES}
    used_keys: set[str] = set(LAB_MARKERS.keys())
    result: list[dict] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        unit = str(item.get("unit") or "").strip()
        if not name or not unit:
            continue
        explicit_key = str(item.get("key") or "").strip().lower()
        if explicit_key:
            base_key = explicit_key
        else:
            base_key = inherited.get(name) or _slugify_lab_marker_name(name)
        key = base_key
        suffix = 2
        while key in used_keys:
            key = f"{base_key}_{suffix}"
            suffix += 1
        used_keys.add(key)

        category = str(item.get("category") or "").strip().lower()
        if category not in known_categories:
            category = LAB_CATEGORY_OTHER
        entry: dict[str, Any] = {"key": key, "name": name, "category": category, "unit": unit}
        for bound in ("ref_min", "ref_max"):
            if item.get(bound) is not None:
                try:
                    entry[bound] = float(item[bound])
                except (TypeError, ValueError):
                    pass
        alt_unit = item.get("alt_unit")
        if (
            isinstance(alt_unit, dict)
            and alt_unit.get("unit")
            and alt_unit.get("factor_to_canonical") is not None
        ):
            try:
                entry["alt_unit"] = {
                    "unit": str(alt_unit["unit"]).strip(),
                    "factor_to_canonical": float(alt_unit["factor_to_canonical"]),
                }
            except (TypeError, ValueError):
                pass
        result.append(entry)
    return result


def effective_lab_markers(custom_markers: Any = None) -> dict[str, dict]:
    """Katalog- + Custom-Marker zu EINER einheitlichen Lookup-Struktur mergen.

    Jeder Wert trägt `is_custom` — das entscheidet in sensor.py/ws_api.py, ob
    `translation_key` (Katalog) oder der nutzervergebene `name` (Custom)
    verwendet wird (§4 der Spec). Custom-Marker können nie einen Katalog-Key
    überschreiben (normalize_lab_custom_markers garantiert das bereits).
    """
    markers: dict[str, dict] = {
        key: {**definition, "is_custom": False} for key, definition in LAB_MARKERS.items()
    }
    for custom in normalize_lab_custom_markers(custom_markers):
        markers[custom["key"]] = {
            "category": custom["category"],
            "name_de": custom["name"],
            "name_en": custom["name"],
            "name": custom["name"],
            "canonical_unit": custom["unit"],
            "ref_min": custom.get("ref_min"),
            "ref_max": custom.get("ref_max"),
            "alt_units": (
                {custom["alt_unit"]["unit"]: custom["alt_unit"]["factor_to_canonical"]}
                if custom.get("alt_unit")
                else {}
            ),
            "require_explicit_unit": False,
            "is_custom": True,
        }
    return markers


def resolve_lab_marker(raw_key: Any, custom_markers: Any = None) -> tuple[str, dict] | None:
    """Marker-Schlüssel auflösen: Alias -> Katalog -> Custom (§2.1a/§5.1).

    `None` = kein Treffer in allen drei Schritten (Aufrufer meldet
    `unknown_marker`, legt NIE automatisch einen Custom-Marker an).
    """
    normalized = str(raw_key if raw_key is not None else "").strip().lower()
    key = LAB_MARKER_ALIASES.get(normalized, normalized)
    markers = effective_lab_markers(custom_markers)
    marker = markers.get(key)
    if marker is None:
        return None
    return key, marker


def convert_lab_value(marker_def: dict, value: float, unit: str | None) -> tuple[float, str]:
    """Rohwert + Ursprungseinheit -> (kanonischer Wert, kanonische Einheit).

    Bidirektional (§3 der Spec): `unit` darf die Haupt-Einheit ODER eine
    bekannte Alt-Einheit sein, beide gelten als gültige Eingabe. Fehlende
    `unit` fällt auf die kanonische Einheit zurück (Aufrufer prüft vorher
    `require_explicit_unit`, falls das für diesen Marker verboten ist).
    Unbekannte Einheit -> `ValueError("unsupported_unit")`, NIE stillschweigend
    falsch rechnen.
    """
    canonical_unit = marker_def["canonical_unit"]
    if unit is None or _norm_unit(unit) == _norm_unit(canonical_unit):
        return float(value), canonical_unit
    alt_units = marker_def.get("alt_units") or {}
    for alt_unit, factor in alt_units.items():
        if _norm_unit(alt_unit) == _norm_unit(unit):
            return round(float(value) * float(factor), 6), canonical_unit
    raise ValueError("unsupported_unit")


# --- Laborbericht-Batch (REQ-HOM-123/128/129) -------------------------------

# Fehlercodes, deren `params` einen Zeilenbezug tragen (§2.4).
_LAB_ROW_ERROR_CODES = frozenset(
    {
        "unknown_marker",
        "unit_required",
        "invalid_value",
        "unsupported_unit",
        "duplicate_marker",
    }
)


def lab_report_error(code: str, params: Mapping[str, Any] | None = None) -> dict:
    """Fehlerobjekt im Batch-Vertrag bauen (§2.4).

    Rückgabe: ``{"code": str, "params": dict, "message": str}``. Der Service
    transportiert nur ``message``; die WS-Batch-Kommandos liefern das ganze
    Objekt. ``marker`` ist immer der eingegebene Rohwert; ein leerer Marker
    erscheint im Text als ``-``.
    """
    values = dict(params or {})
    if code == "invalid_ts":
        prose = ENTRY_TS_INVALID_MESSAGE.format(value=values.get("value"))
        message = f"invalid_ts: {prose}"
    elif code == "too_many_rows":
        message = f"too_many_rows ({values.get('count')} > {values.get('limit')})"
    elif code in _LAB_ROW_ERROR_CODES:
        marker = values.get("marker") or "-"
        message = f"Zeile {values.get('row')} ({marker}): {code}"
        if code == "duplicate_marker":
            message += f" (schon in Zeile {values.get('first_row')})"
    else:
        message = code
    return {"code": code, "params": values, "message": message}


def coerce_lab_number(value: Any) -> float | None:
    """Messwert zu ``float`` — ``None`` bei bool, Nicht-Zahl, NaN/±inf (§2.5).

    ``bool`` ist in Python eine ``int``-Unterklasse (``True == 1``), aber kein
    Messwert. Nicht-endliche Werte würden sonst in Konvertierung, Anzeige und
    Referenzvergleich als scheinbar gültige Zahl durchrutschen.
    """
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return number


def _lab_row_is_empty(row: Mapping[str, Any]) -> bool:
    """Leerzeile (§2.3): Marker, Wert und Einheit fehlen/whitespace."""
    marker = str(row.get("marker") or "").strip()
    raw_value = row.get("value")
    value = "" if raw_value is None else str(raw_value).strip()
    unit = str(row.get("unit") or "").strip()
    return not (marker or value or unit)


def validate_lab_report_rows(
    values: Any, custom_markers: Any = None
) -> tuple[list[dict], dict | None]:
    """Leerzeilen filtern, Zeilen validieren, in kanonische Einheiten konvertieren.

    Rückgabe: (konvertierte Zeilen, Fehlerobjekt oder None). Das Fehlerobjekt
    ist ``{"code", "params", "message"}`` (§2.4). Die Zeilennummer ist der
    ORIGINALindex der Eingabeliste (1-basiert, inklusive Leerzeilen), damit der
    Nutzer die Zeile in seinem Eingabefeld wiederfindet.
    """
    if isinstance(values, Mapping):
        values = [values]
    if not isinstance(values, list):
        return [], lab_report_error("empty_report")

    filled = [
        (index, row)
        for index, row in enumerate(values, start=1)
        if isinstance(row, Mapping) and not _lab_row_is_empty(row)
    ]
    if not filled:
        return [], lab_report_error("empty_report")
    if len(filled) > LAB_REPORT_MAX_ROWS:
        return [], lab_report_error(
            "too_many_rows", {"count": len(filled), "limit": LAB_REPORT_MAX_ROWS}
        )

    converted: list[dict] = []
    resolved_keys: list[tuple[int, str, str]] = []
    for index, row in filled:
        raw_marker = str(row.get("marker") or "").strip()
        resolved = resolve_lab_marker(raw_marker, custom_markers) if raw_marker else None
        if resolved is None:
            return [], lab_report_error("unknown_marker", {"row": index, "marker": raw_marker})
        marker_key, marker_def = resolved
        raw_unit = row.get("unit")
        unit = str(raw_unit).strip() if raw_unit is not None else ""
        if not unit and marker_def.get("require_explicit_unit"):
            return [], lab_report_error("unit_required", {"row": index, "marker": raw_marker})
        # Zahlenprüfung VOR der Einheitenprüfung: `convert_lab_value` beginnt mit
        # `float(value)` und würde "abc" sonst als `unsupported_unit` melden.
        raw_value = row.get("value")
        reported_value = coerce_lab_number(raw_value)
        if reported_value is None:
            return [], lab_report_error(
                "invalid_value",
                {"row": index, "marker": raw_marker, "value": raw_value},
            )
        try:
            canonical_value, canonical_unit = convert_lab_value(
                marker_def, reported_value, unit or None
            )
        except ValueError:
            return [], lab_report_error(
                "unsupported_unit",
                {"row": index, "marker": raw_marker, "unit": unit},
            )
        converted.append(
            {
                "marker_key": marker_key,
                "value": canonical_value,
                "unit": canonical_unit,
                "reported_value": reported_value,
                "reported_unit": unit or canonical_unit,
            }
        )
        resolved_keys.append((index, marker_key, raw_marker))

    # Duplikate erst nach der Zeilenvalidierung (§2.5: Schritt 4 vor Schritt 5).
    first_row: dict[str, int] = {}
    for index, marker_key, raw_marker in resolved_keys:
        if marker_key in first_row:
            return [], lab_report_error(
                "duplicate_marker",
                {"row": index, "marker": raw_marker, "first_row": first_row[marker_key]},
            )
        first_row[marker_key] = index
    return converted, None


def lab_report_matches(
    reading: Any,
    ts: datetime,
    report_ref: str | None = None,
) -> bool:
    """True, wenn eine Lesung zum Bericht gehört (Instant + optionaler Tag).

    Zeitvergleich als **Instant**: Offset-Schreibweisen derselben Zeit treffen
    sich (kein String-Vergleich). ``report_ref is None`` = kein Tag-Filter; ein
    gesetzter Filter trifft nur Einträge mit exakt diesem Tag (``None`` im
    Eintrag zählt nicht als Treffer).
    """
    if not isinstance(reading, Mapping):
        return False
    parsed = _parse_ts(reading.get("ts"))
    if parsed is None:
        return False
    left = _align_tz(parsed, ts)
    if left.tzinfo is None or ts.tzinfo is None:
        if left.replace(tzinfo=None) != ts.replace(tzinfo=None):
            return False
    elif left.astimezone(UTC) != ts.astimezone(UTC):
        return False
    if report_ref is None:
        return True
    return (reading.get("report_ref") or None) == report_ref


# --- Laborwerte: Referenzbereich + In-Range-Prüfung (REQ-HOM-122) ---


def resolve_lab_reference(
    marker_key: str, marker_def: dict, ref_overrides: Any
) -> tuple[float | None, float | None]:
    """Referenzbereich auflösen: Override (nur Katalog) > Katalog-Default (§2.3).

    Custom-Marker haben keinen Override-Layer (sie sind schon
    personenspezifisch) — ein Override-Dict ohne passenden `marker_key` wirkt
    für sie ohnehin nicht, diese Funktion braucht also keinen Sonderfall.
    """
    override = ref_overrides.get(marker_key) if isinstance(ref_overrides, Mapping) else None
    if isinstance(override, Mapping):
        return (
            override.get("ref_min", marker_def.get("ref_min")),
            override.get("ref_max", marker_def.get("ref_max")),
        )
    return marker_def.get("ref_min"), marker_def.get("ref_max")


def lab_marker_in_range(
    value: float | None, ref_min: float | None, ref_max: float | None
) -> bool | None:
    """`True`/`False`/`None` (kein Wert ODER kein Referenzbereich hinterlegt).

    Die Integration klassifiziert nicht medizinisch (Vision §4.2) — dies ist
    eine reine Bereichsprüfung, keine Diagnose.
    """
    if value is None or (ref_min is None and ref_max is None):
        return None
    if ref_min is not None and value < ref_min:
        return False
    if ref_max is not None and value > ref_max:
        return False
    return True


def normalize_lab_ref_overrides(raw: Any) -> dict[str, dict]:
    """`entry.options["lab_ref_overrides"]` normalisieren (§2.3, HA-frei).

    Nur bekannte Katalog-Marker-Keys bleiben erhalten (ein gelöschter/
    umbenannter Marker würde sonst einen verwaisten Override-Eintrag
    hinterlassen); nur `ref_min`/`ref_max` werden übernommen.
    """
    if not isinstance(raw, dict):
        return {}
    result: dict[str, dict] = {}
    for marker_key, bounds in raw.items():
        if marker_key not in LAB_MARKERS or not isinstance(bounds, dict):
            continue
        entry: dict[str, float] = {}
        for bound in ("ref_min", "ref_max"):
            if bounds.get(bound) is not None:
                try:
                    entry[bound] = float(bounds[bound])
                except (TypeError, ValueError):
                    continue
        if entry:
            result[str(marker_key)] = entry
    return result


def normalize_lab_hidden_categories(raw: Any) -> list[str]:
    """`entry.options["lab_hidden_categories"]` normalisieren (§2.5, HA-frei)."""
    if not isinstance(raw, list):
        return []
    known = {category["key"] for category in LAB_CATEGORIES}
    return [str(item) for item in raw if str(item) in known]

"""Reine Logik ohne Home-Assistant-Imports — unit-testbar.

Enthält Tagesfenster-Berechnung, Summenbildung und CSV-Zeilenerzeugung.
"""

from __future__ import annotations

import calendar
import csv
import io
from collections.abc import Iterable, Mapping
from datetime import UTC, date, datetime, timedelta, tzinfo
from typing import Any

from .const import (
    AUDIT_LIMIT_OPTION,
    CAFFEINE_MG_PER_100ML,
    DEFAULT_AUDIT_LIMIT,
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


def csv_header_footer(rows_count: int, person: str, kind: str, now: datetime) -> tuple[str, str]:
    """Kopf- und Fußzeile des Exports."""
    header = (
        f"# HA Health-O-Mat Export — {kind} — Person: {person}\n"
        f"# Erstellt: {now.strftime('%Y-%m-%d %H:%M:%S')}"
    )
    footer = f"# Datensaetze: {rows_count}"
    return header, footer


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


# Kanonische Korrektur-Ziele (Store-Listen + Methoden je Ziel).
HISTORY_KINDS: tuple[str, ...] = ("drinks", "blood_pressure", "wellbeing")

# Kanonisches Ziel → Store-Listenname (Rohlisten, inkl. voided Einträge).
HISTORY_LIST_BY_KIND: dict[str, str] = {
    "drinks": "drinks",
    "blood_pressure": "readings",
    "wellbeing": "wellbeing_entries",
}

# Kanonisches Ziel → Store-Methoden (ein Name, kein Zweitweg in der API).
VOID_METHOD_BY_KIND: dict[str, str] = {
    "drinks": "void_drink",
    "blood_pressure": "void_reading",
    "wellbeing": "void_wellbeing",
}
RESTORE_METHOD_BY_KIND: dict[str, str] = {
    "drinks": "restore_drink",
    "blood_pressure": "restore_reading",
    "wellbeing": "restore_wellbeing",
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

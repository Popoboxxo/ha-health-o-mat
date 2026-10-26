"""Erinnerungen, Wochenbericht und Benachrichtigungs-Zustellung (REQ-HOM-118).

Aufteilung:

* **HA-frei** (unit-testbar, kein ``homeassistant``-Import nötig): die
  Normalisierung der Options-Struktur, Quiet-Hours-Prüfung, Fälligkeits-Logik,
  Kennzahlen des Wochenberichts und die Text-Erzeugung (de/en).
* **HA-Kopplung**: nur der Scheduler (``async_track_time_change``) und die
  Zustellung über ``notify.*`` bzw. ``persistent_notification`` am Dateiende.

Alle Zustands-/Zeitfenster-Auswertungen laufen on-read gegen die **aktive**
Store-Sicht (ohne voided Einträge) und respektieren den ``ts`` des Eintrags —
es gibt keinen Reset-Job, damit bleibt das Verhalten neustart- und DST-fest.

Defaults sind bewusst AUS: eine bestehende Installation ändert ohne explizites
Aktivieren im Options-Flow ihr Verhalten nicht.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.event import async_track_time_change

from . import logic
from .const import (
    CAFFEINE_MG_PER_100ML,
    DEFAULT_DAILY_GOAL_ML,
    DEFAULT_REMINDER_NO_DRINK_HOURS,
    DEFAULT_REMINDER_TIME,
    DEFAULT_WEEKLY_REPORT_TIME,
    DOMAIN,
    OPTION_REMINDERS,
    OPTION_WEEKLY_REPORT,
    REMINDER_KINDS,
    WELLBEING_STATES,
)

_LOGGER = logging.getLogger(__name__)

_WEEKDAYS: tuple[int, ...] = tuple(range(7))
_WEEKLY_REPORT_DEDUP_KEY = "weekly_report"
_NOTIFY_DOMAIN = "notify"
_PERSISTENT_NOTIFICATION_DOMAIN = "persistent_notification"


# ---------------------------------------------------------------------------
# Normalisierung (HA-frei)
# ---------------------------------------------------------------------------


def normalize_language(value: Any) -> str:
    """Sprachcode auf die unterstützten Berichtssprachen abbilden.

    Deutsch wird erkannt (``de``/``de-DE``), jede andere vorhandene Sprache
    erhält Englisch; fehlt der Wert, gilt Deutsch als Fallback.
    """
    if not isinstance(value, str) or not value.strip():
        return "de"
    return "de" if value.strip().lower().startswith("de") else "en"


def _parse_time(value: Any) -> tuple[int, int] | None:
    """``HH:MM`` (optional ``HH:MM:SS``) parsen — ungültig → ``None``.

    HA-TimeSelector liefert je nach Version ``HH:MM`` oder ``HH:MM:SS``; beide
    Formen sind gültig, intern wird immer auf ``HH:MM`` normalisiert.
    """
    if not isinstance(value, str):
        return None
    parts = value.strip().split(":")
    if len(parts) not in (2, 3):
        return None
    try:
        hour, minute = int(parts[0]), int(parts[1])
    except ValueError:
        return None
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return None
    if len(parts) == 3:
        try:
            second = int(parts[2])
        except ValueError:
            return None
        if not 0 <= second <= 59:
            return None
    return hour, minute


def _normalize_time(value: Any, default: str) -> str:
    """Gültige Zeit als ``HH:MM``, sonst *default*."""
    parsed = _parse_time(value)
    if parsed is None:
        return default
    return f"{parsed[0]:02d}:{parsed[1]:02d}"


def _optional_time(value: Any) -> str:
    """Optionale Zeit (Quiet Hours): ungültig/leer → leere Zeichenkette."""
    parsed = _parse_time(value)
    if parsed is None:
        return ""
    return f"{parsed[0]:02d}:{parsed[1]:02d}"


def _time_parts(value: str) -> tuple[int, int]:
    """Normalisierte Zeit in ``(hour, minute)`` — unerreichbarer Fallback 0:00."""
    return _parse_time(value) or (0, 0)


def _as_bool(value: Any, default: bool = False) -> bool:
    """Bool defensiv interpretieren (Strings wie ``"false"`` sind nicht truthy)."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in ("1", "true", "yes", "on"):
            return True
        if normalized in ("0", "false", "no", "off", ""):
            return False
        return default
    if isinstance(value, (int, float)):
        return bool(value)
    return default


def _bounded_int(value: Any, default: int, minimum: int, maximum: int) -> int:
    """Ganzzahl im Bereich [minimum, maximum], sonst *default*."""
    if isinstance(value, bool):
        return default
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    if number < minimum or number > maximum:
        return default
    return number


def _coerce_weekday(value: Any) -> int | None:
    """Wochentag 0–6 (0 = Montag), akzeptiert auch numerische Strings."""
    if isinstance(value, bool):
        return None
    try:
        day = int(value)
    except (TypeError, ValueError):
        return None
    return day if 0 <= day <= 6 else None


def normalize_days(value: Any) -> list[int]:
    """Wochentagsliste defensiv normalisieren (leer/ungültig → alle Tage).

    Eine explizit leere Auswahl wird wie „ungültig" behandelt und fällt auf
    alle Tage zurück: An/aus wird über ``enabled`` gesteuert, eine leere
    Auswahl würde Erinnerungen sonst stillschweigend nie auslösen.
    """
    if not isinstance(value, (list, tuple, set)):
        return list(_WEEKDAYS)
    days = sorted({day for day in (_coerce_weekday(item) for item in value) if day is not None})
    return days or list(_WEEKDAYS)


def normalize_notify_service(value: Any) -> str:
    """Notify-Ziel auf den Service-Namen normalisieren.

    Akzeptiert ``mobile_app_x`` und ``notify.mobile_app_x`` und speichert
    intern immer ohne Domain-Präfix (``mobile_app_x``). Leer/ungültig → ``""``
    (Fallback ``persistent_notification``).
    """
    if not isinstance(value, str):
        return ""
    name = value.strip()
    if name.lower().startswith(f"{_NOTIFY_DOMAIN}."):
        name = name[len(_NOTIFY_DOMAIN) + 1 :].strip()
    return name


def normalize_reminders(value: Any) -> dict[str, Any]:
    """Erinnerungs-Options defensiv auf die vollständige Struktur bringen."""
    raw = value if isinstance(value, dict) else {}
    raw_conditions = raw.get("conditions")
    conditions = raw_conditions if isinstance(raw_conditions, dict) else {}
    return {
        "enabled": _as_bool(raw.get("enabled"), False),
        "time": _normalize_time(raw.get("time"), DEFAULT_REMINDER_TIME),
        "days": normalize_days(raw.get("days")),
        "notify_service": normalize_notify_service(raw.get("notify_service")),
        "quiet_start": _optional_time(raw.get("quiet_start")),
        "quiet_end": _optional_time(raw.get("quiet_end")),
        "conditions": {
            "drink_goal": _as_bool(conditions.get("drink_goal"), True),
            "no_drink_hours": _bounded_int(
                conditions.get("no_drink_hours"),
                DEFAULT_REMINDER_NO_DRINK_HOURS,
                0,
                24,
            ),
            "bp_days": _bounded_int(conditions.get("bp_days"), 0, 0, 365),
            "wellbeing_days": _bounded_int(conditions.get("wellbeing_days"), 0, 0, 365),
        },
    }


def normalize_weekly_report(value: Any) -> dict[str, Any]:
    """Wochenbericht-Options defensiv auf die vollständige Struktur bringen."""
    raw = value if isinstance(value, dict) else {}
    day = _coerce_weekday(raw.get("day"))
    return {
        "enabled": _as_bool(raw.get("enabled"), False),
        "day": 0 if day is None else day,
        "time": _normalize_time(raw.get("time"), DEFAULT_WEEKLY_REPORT_TIME),
        "notify_service": normalize_notify_service(raw.get("notify_service")),
    }


# ---------------------------------------------------------------------------
# Quiet Hours (HA-frei)
# ---------------------------------------------------------------------------


def in_quiet_hours(now: datetime, start: Any, end: Any) -> bool:
    """Liegt *now* im Ruhefenster [start, end)?

    Unterstützt Mitternachtsüberlauf (``22:00``–``07:00``). Fehlt eine der
    Grenzen oder sind beide gleich, gilt kein Ruhefenster (``False``).
    """
    start_minutes = _parse_time(start)
    end_minutes = _parse_time(end)
    if start_minutes is None or end_minutes is None:
        return False
    start_total = start_minutes[0] * 60 + start_minutes[1]
    end_total = end_minutes[0] * 60 + end_minutes[1]
    if start_total == end_total:
        return False
    current = now.hour * 60 + now.minute
    if start_total < end_total:
        return start_total <= current < end_total
    return current >= start_total or current < end_total


# ---------------------------------------------------------------------------
# Fälligkeits-Prüfung (HA-frei)
# ---------------------------------------------------------------------------


def _active_items(items: Any) -> list[dict[str, Any]]:
    """Nur aktive (nicht voided) Dict-Einträge einer Liste."""
    if not isinstance(items, list):
        return []
    return [item for item in items if isinstance(item, dict) and not item.get("voided_at")]


def _parse_dt(value: Any, reference: datetime) -> datetime | None:
    """ISO-Zeitstempel parsen und an die Zeitzone von *reference* angleichen."""
    if not isinstance(value, str):
        return None
    raw = value.strip()
    if not raw:
        return None
    if raw[-1:] in ("Z", "z"):
        raw = raw[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if parsed.tzinfo is None and reference.tzinfo is not None:
        return parsed.replace(tzinfo=reference.tzinfo)
    if parsed.tzinfo is not None and reference.tzinfo is None:
        return parsed.replace(tzinfo=None)
    return parsed


def _last_ts(items: Any, reference: datetime) -> datetime | None:
    """Jüngster gültiger ``ts`` der aktiven Einträge (oder ``None``)."""
    stamps = [
        parsed
        for parsed in (_parse_dt(item.get("ts"), reference) for item in _active_items(items))
        if parsed is not None
    ]
    return max(stamps) if stamps else None


def _stale_since(items: Any, now: datetime, days: int) -> bool:
    """True, wenn seit *days* Tagen kein aktiver Eintrag mehr vorliegt."""
    last = _last_ts(items, now)
    if last is None:
        return True
    return last < now - timedelta(days=days)


def _daily_goal(options: dict[str, Any]) -> int:
    """Tagesziel aus den Options (Fallback: Default-Ziel)."""
    return _bounded_int(options.get("daily_goal_ml"), DEFAULT_DAILY_GOAL_ML, 1, 100_000)


def _reset_parts(options: dict[str, Any]) -> tuple[int, int]:
    """Tagesgrenze aus ``daily_reset_hour`` (Sekunden sind irrelevant)."""
    return _bounded_int(options.get("daily_reset_hour"), 0, 0, 23), 0


def reminder_due(data: Any, options: Any, now: datetime) -> list[str]:
    """Fällige Erinnerungs-Arten anhand der aktiven Sicht und der Bedingungen.

    ``data`` ist die aktive Store-Sicht (voided Einträge werden zusätzlich
    defensiv herausgefiltert). Rückgabe ist eine Liste aus ``REMINDER_KINDS``
    in stabiler Reihenfolge; leer, wenn keine Bedingung zutrifft, die
    Erinnerungen deaktiviert sind oder alle Einzelbedingungen aus sind.
    """
    opts = options if isinstance(options, dict) else {}
    reminders = normalize_reminders(opts.get(OPTION_REMINDERS))
    if not reminders["enabled"]:
        return []

    active = data if isinstance(data, dict) else {}
    drinks = _active_items(active.get("drinks"))
    conditions = reminders["conditions"]
    hour, minute = _reset_parts(opts)
    due: list[str] = []

    goal = _daily_goal(opts)
    if conditions["drink_goal"] and goal > 0:
        today_ml = int(logic.today_sums(drinks, now, hour, minute)["total_ml"])
        if today_ml < goal:
            due.append("drink_goal")

    hours = conditions["no_drink_hours"]
    if hours > 0:
        last = _last_ts(drinks, now)
        if last is None or (now - last).total_seconds() >= hours * 3600:
            due.append("no_drink")

    if conditions["bp_days"] > 0 and _stale_since(
        active.get("readings"), now, conditions["bp_days"]
    ):
        due.append("bp")

    if conditions["wellbeing_days"] > 0 and _stale_since(
        active.get("wellbeing_entries"), now, conditions["wellbeing_days"]
    ):
        due.append("wellbeing")

    return due


# ---------------------------------------------------------------------------
# Texte (HA-frei)
# ---------------------------------------------------------------------------

_REMINDER_TITLES = {"de": "Health-O-Mat Erinnerung", "en": "Health-O-Mat reminder"}

_REMINDER_HEADINGS = {"de": "Erinnerung für {person}", "en": "Reminder for {person}"}

_REMINDER_LINES: dict[str, dict[str, str]] = {
    "de": {
        "drink_goal": "💧 Tagesziel noch nicht erreicht.",
        "no_drink": "🥤 Schon länger nichts getrunken.",
        "bp": "🩺 Blutdruck seit einigen Tagen nicht gemessen.",
        "wellbeing": "🙂 Wohlbefinden seit einigen Tagen nicht gemeldet.",
    },
    "en": {
        "drink_goal": "💧 Daily drinking goal not reached yet.",
        "no_drink": "🥤 Nothing to drink for a while.",
        "bp": "🩺 Blood pressure not measured for a few days.",
        "wellbeing": "🙂 Wellbeing not reported for a few days.",
    },
}


def reminder_title(language: Any = "de") -> str:
    """Titel einer Erinnerungs-Notification."""
    return _REMINDER_TITLES[normalize_language(language)]


def build_reminder_message(kinds: Any, person: str, language: Any = "de") -> str:
    """Markdown-Nachricht mit allen fälligen Punkten (de/en)."""
    lang = normalize_language(language)
    lines_map = _REMINDER_LINES[lang]
    wanted = set(kinds) if isinstance(kinds, (list, tuple, set)) else set()
    lines = [f"- {lines_map[kind]}" for kind in REMINDER_KINDS if kind in wanted]
    heading = _REMINDER_HEADINGS[lang].format(person=person or "—")
    body = "\n".join(lines) if lines else "- —"
    return f"**{heading}**\n\n{body}"


_WELLBEING_LABELS_EN: dict[str, str] = {
    "very_bad": "Very bad",
    "awful": "Awful",
    "bad": "Bad",
    "poor": "Poor",
    "okay": "Okay",
    "mixed": "Mixed",
    "good": "Good",
    "very_good": "Very good",
    "great": "Great",
    "excellent": "Excellent",
}

_REPORT_TEXTS: dict[str, dict[str, str]] = {
    "de": {
        "title": "Wochenbericht",
        "period": "Zeitraum",
        "days": "{count} Tage",
        "drinks": "Trinken",
        "total": "Gesamt",
        "avg_goal": "Ø Tagesziel",
        "goal_days": "Ziel erreicht",
        "streak": "Serie",
        "top": "Top-Getränke",
        "bp": "Blutdruck",
        "avg": "Ø",
        "measurements": "{count} Messungen",
        "trend": "Trend",
        "rising": "steigend",
        "falling": "fallend",
        "stable": "stabil",
        "wellbeing": "Wohlbefinden",
        "distribution": "Verteilung",
        "caffeine": "Koffein",
        "estimated": "Geschätzt",
        "completeness": "Datenvollständigkeit",
        "data_days": "{count} von {total} Tagen mit Einträgen",
        "of_scale": "von {max}",
        "reports": "{count} Meldungen",
        "none": "—",
    },
    "en": {
        "title": "Weekly report",
        "period": "Period",
        "days": "{count} days",
        "drinks": "Drinks",
        "total": "Total",
        "avg_goal": "Ø daily goal",
        "goal_days": "Goal reached",
        "streak": "Streak",
        "top": "Top drinks",
        "bp": "Blood pressure",
        "avg": "Ø",
        "measurements": "{count} readings",
        "trend": "Trend",
        "rising": "rising",
        "falling": "falling",
        "stable": "stable",
        "wellbeing": "Wellbeing",
        "distribution": "Distribution",
        "caffeine": "Caffeine",
        "estimated": "Estimated",
        "completeness": "Data completeness",
        "data_days": "{count} of {total} days with entries",
        "of_scale": "of {max}",
        "reports": "{count} reports",
        "none": "—",
    },
}


def weekly_window(now: datetime) -> tuple[datetime, datetime]:
    """Fenster des Wochenberichts: die letzten sieben Tage ``[now-7d, now]``."""
    return now - timedelta(days=7), now


# ---------------------------------------------------------------------------
# Wochen-Kennzahlen (HA-frei)
# ---------------------------------------------------------------------------


def _in_window(ts: datetime, start: datetime, end: datetime) -> bool:
    return start <= ts <= end


def _day_key(ts: datetime, hour: int, minute: int) -> date:
    return logic.day_start(ts, hour, minute).date()


def collect_weekly_metrics(data: Any, options: Any, now: datetime) -> dict[str, Any]:
    """Kennzahlen des Wochenberichts aus der aktiven Sicht berechnen.

    ``data`` ist die aktive Store-Sicht; voided Einträge werden zusätzlich
    defensiv gefiltert. Alle Werte sind on-read berechnet und robust gegen
    fehlende/kaputte Zeitstempel. Es werden ausschließlich Metriken geliefert,
    keine Rohdaten — der Bericht ist eine Notification, keine Datei.
    """
    opts = options if isinstance(options, dict) else {}
    active = data if isinstance(data, dict) else {}
    start, end = weekly_window(now)
    goal = _daily_goal(opts)
    hour, minute = _reset_parts(opts)

    day_keys = [
        _day_key(now, hour, minute) - timedelta(days=offset) for offset in range(len(_WEEKDAYS))
    ]
    day_set = set(day_keys)

    daily_ml: dict[date, int] = {}
    breakdown: dict[str, int] = {}
    total_ml = 0
    for drink in _active_items(active.get("drinks")):
        ts = _parse_dt(drink.get("ts"), now)
        if ts is None or not _in_window(ts, start, end):
            continue
        ml = int(drink.get("ml") or 0)
        drink_type = str(drink.get("type") or "Eigen")
        total_ml += ml
        breakdown[drink_type] = breakdown.get(drink_type, 0) + ml
        key = _day_key(ts, hour, minute)
        if key in day_set:
            daily_ml[key] = daily_ml.get(key, 0) + ml

    goal_days = sum(1 for key in day_keys if daily_ml.get(key, 0) >= goal) if goal > 0 else 0
    avg_goal_percent = round(total_ml / (goal * len(day_keys)) * 100, 1) if goal > 0 else None

    top_drinks = [
        {"type": drink_type, "ml": ml}
        for drink_type, ml in sorted(breakdown.items(), key=lambda item: (-item[1], item[0]))[:3]
    ]

    sys_values: list[float] = []
    dia_values: list[float] = []
    bp_days_set: set[date] = set()
    readings = _active_items(active.get("readings"))
    week_readings = 0
    for reading in readings:
        ts = _parse_dt(reading.get("ts"), now)
        if ts is None or not _in_window(ts, start, end):
            continue
        bp_days_set.add(_day_key(ts, hour, minute))
        if reading.get("sys") is not None:
            sys_values.append(float(reading["sys"]))
        if reading.get("dia") is not None:
            dia_values.append(float(reading["dia"]))
        if reading.get("sys") is not None and reading.get("dia") is not None:
            week_readings += 1

    scores: list[int] = []
    histogram: dict[str, int] = {}
    wellbeing_days_set: set[date] = set()
    for event in _active_items(active.get("wellbeing_entries")):
        ts = _parse_dt(event.get("ts"), now)
        if ts is None or not _in_window(ts, start, end):
            continue
        wellbeing_days_set.add(_day_key(ts, hour, minute))
        key = event.get("key")
        score = logic.wellbeing_score(key)
        if score is None:
            continue
        scores.append(score)
        histogram[str(key)] = histogram.get(str(key), 0) + 1

    caffeine_mg = round(
        sum(
            ml * CAFFEINE_MG_PER_100ML.get(drink_type, 0.0) / 100.0
            for drink_type, ml in breakdown.items()
        ),
        1,
    )

    data_days = set(daily_ml) | bp_days_set | wellbeing_days_set
    data_days &= day_set

    return {
        "period_start": start.date().isoformat(),
        "period_end": end.date().isoformat(),
        "window_days": len(day_keys),
        "goal_ml": goal,
        "total_ml": total_ml,
        "avg_goal_percent": avg_goal_percent,
        "goal_days": goal_days,
        "goal_streak": logic.goal_streak(
            _active_items(active.get("drinks")), goal, now, hour, minute
        )["current_streak"],
        "top_drinks": top_drinks,
        "bp_count": week_readings,
        "bp_avg_sys": round(sum(sys_values) / len(sys_values), 1) if sys_values else None,
        "bp_avg_dia": round(sum(dia_values) / len(dia_values), 1) if dia_values else None,
        "bp_trend": logic.bp_trend(readings, now),
        "wellbeing_count": len(scores),
        "wellbeing_avg": round(sum(scores) / len(scores), 1) if scores else None,
        "wellbeing_max": len(WELLBEING_STATES),
        "wellbeing_histogram": histogram,
        "caffeine_mg": caffeine_mg,
        "days_with_data": len(data_days),
        "completeness_percent": round(len(data_days) / len(day_keys) * 100, 1),
    }


def _wellbeing_label(key: str, language: str) -> str:
    """Anzeigename eines Wellbeing-Keys in der Zielsprache."""
    if language == "en":
        return _WELLBEING_LABELS_EN.get(key, key)
    for state in WELLBEING_STATES:
        if state.get("key") == key:
            return str(state.get("label", key))
    return key


def _format_date(value: str, language: str) -> str:
    """ISO-Datum für die Zielsprache formatieren (de: TT.MM.JJJJ)."""
    try:
        parsed = date.fromisoformat(value)
    except (TypeError, ValueError):
        return value or "—"
    return parsed.strftime("%d.%m.%Y" if language == "de" else "%Y-%m-%d")


def _fmt_number(value: Any, digits: int = 1) -> str:
    if value is None:
        return "—"
    return f"{float(value):.{digits}f}"


def weekly_report_title(person: str, language: Any = "de") -> str:
    """Titel der Wochenbericht-Notification."""
    lang = normalize_language(language)
    return f"{_REPORT_TEXTS[lang]['title']} — {person or '—'}"


def render_weekly_report_markdown(metrics: Any, person: str, language: Any = "de") -> str:
    """Wochenbericht als Markdown-Nachricht rendern (de/en)."""
    lang = normalize_language(language)
    texts = _REPORT_TEXTS[lang]
    data = metrics if isinstance(metrics, dict) else {}
    none = texts["none"]

    period = (
        f"{_format_date(str(data.get('period_start', '')), lang)} – "
        f"{_format_date(str(data.get('period_end', '')), lang)}"
    )
    window_days = int(data.get("window_days") or 0)

    lines: list[str] = [
        f"## {texts['title']} — {person or '—'}",
        "",
        f"**{texts['period']}:** {period} ({texts['days'].format(count=window_days)})",
        "",
        f"### {texts['drinks']}",
        f"- {texts['total']}: {int(data.get('total_ml') or 0)} ml",
        f"- {texts['avg_goal']}: {_fmt_number(data.get('avg_goal_percent'))} %",
    ]

    goal_ml = int(data.get("goal_ml") or 0)
    lines.append(
        f"- {texts['goal_days']}: "
        f"{int(data.get('goal_days') or 0)} {texts['of_scale'].format(max=window_days)}"
        f" ({goal_ml} ml)"
    )
    lines.append(f"- {texts['streak']}: {int(data.get('goal_streak') or 0)}")

    top_drinks = data.get("top_drinks") or []
    top_text = ", ".join(
        f"{entry.get('type')} ({int(entry.get('ml') or 0)} ml)" for entry in top_drinks
    )
    lines.append(f"- {texts['top']}: {top_text or none}")

    lines.extend(["", f"### {texts['bp']}"])
    bp_count = int(data.get("bp_count") or 0)
    if bp_count:
        lines.append(
            f"- {texts['avg']}: {_fmt_number(data.get('bp_avg_sys'))}/"
            f"{_fmt_number(data.get('bp_avg_dia'))} mmHg "
            f"({texts['measurements'].format(count=bp_count)})"
        )
    else:
        lines.append(f"- {texts['avg']}: {none}")
    trend = data.get("bp_trend")
    if isinstance(trend, dict) and trend.get("direction") in texts:
        delta = trend.get("sys_delta")
        delta_text = f" ({float(delta):+.1f} mmHg)" if delta is not None else ""
        lines.append(f"- {texts['trend']}: {texts[str(trend['direction'])]}{delta_text}")

    lines.extend(["", f"### {texts['wellbeing']}"])
    wb_count = int(data.get("wellbeing_count") or 0)
    if wb_count:
        lines.append(
            f"- {texts['avg']}: {_fmt_number(data.get('wellbeing_avg'))} "
            f"{texts['of_scale'].format(max=int(data.get('wellbeing_max') or 0))} "
            f"({texts['reports'].format(count=wb_count)})"
        )
        histogram = data.get("wellbeing_histogram") or {}
        distribution = ", ".join(
            f"{_wellbeing_label(key, lang)} ({count})"
            for key, count in sorted(
                histogram.items(),
                key=lambda item: next(
                    (
                        index
                        for index, state in enumerate(WELLBEING_STATES)
                        if state.get("key") == item[0]
                    ),
                    len(WELLBEING_STATES),
                ),
            )
        )
        if distribution:
            lines.append(f"- {texts['distribution']}: {distribution}")
    else:
        lines.append(f"- {texts['avg']}: {none}")

    lines.extend(
        [
            "",
            f"### {texts['caffeine']}",
            f"- {texts['estimated']}: {_fmt_number(data.get('caffeine_mg'))} mg",
            "",
            f"### {texts['completeness']}",
            f"- {
                texts['data_days'].format(
                    count=int(data.get('days_with_data') or 0), total=window_days
                )
            }"
            f" ({_fmt_number(data.get('completeness_percent'))} %)",
        ]
    )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Scheduler + Zustellung (HA-Kopplung)
# ---------------------------------------------------------------------------


def _language(hass: HomeAssistant) -> str:
    """Systemsprache aus der HA-Konfiguration (Fallback Deutsch)."""
    return normalize_language(getattr(getattr(hass, "config", None), "language", None))


def _person_name(entry: Any) -> str:
    """Anzeigename der Person (Options-Anzeigename vor strukturellem Namen)."""
    options = getattr(entry, "options", None) or {}
    data = getattr(entry, "data", None) or {}
    return str(options.get("person_display") or data.get("person") or "Person")


def _entry_state(hass: HomeAssistant, entry_id: str) -> dict:
    """Runtime-State eines Entries (legt ihn bei Bedarf an)."""
    registry = hass.data.setdefault(DOMAIN, {})
    state = registry.get(entry_id)
    if not isinstance(state, dict):
        state = {}
        registry[entry_id] = state
    return state


def _cancel_unsubs(hass: HomeAssistant, entry_id: str) -> None:
    """Alle registrierten Scheduler-Unsubs eines Entries ausführen (idempotent)."""
    registry = hass.data.get(DOMAIN)
    if not isinstance(registry, dict):
        return
    state = registry.get(entry_id)
    if not isinstance(state, dict):
        return
    for unsub in state.pop("reminder_unsubs", None) or []:
        try:
            unsub()
        except Exception:  # noqa: BLE001 - Unsub-Fehler ist nie setup/unload-kritisch
            _LOGGER.exception("Health-O-Mat: Erinnerungs-Unsub fehlgeschlagen")


def _sent_state(hass: HomeAssistant, entry_id: str) -> dict[str, str]:
    """Dedup-Speicher ``{kind: date.isoformat()}`` im Entry-State."""
    state = _entry_state(hass, entry_id)
    sent = state.get("reminder_sent")
    if not isinstance(sent, dict):
        sent = {}
        state["reminder_sent"] = sent
    return sent


def _was_sent(hass: HomeAssistant, entry_id: str, key: str, now: datetime) -> bool:
    """Wurde *key* heute schon zugestellt?"""
    return _sent_state(hass, entry_id).get(key) == now.date().isoformat()


def _mark_sent(hass: HomeAssistant, entry_id: str, keys: list[str], now: datetime) -> None:
    """Zustellung für heute vermerken (Dedup-Schlüssel = ISO-Datum)."""
    sent = _sent_state(hass, entry_id)
    for key in keys:
        sent[key] = now.date().isoformat()


async def async_send_notification(
    hass: HomeAssistant, notify_service: Any, title: str, message: str
) -> bool:
    """Notification über ``notify.<name>`` senden, sonst persistent.

    Rückgabe ``True``, wenn ein echter Notify-Service genutzt wurde. Ein
    fehlender oder fehlschlagender Notify-Service fällt auf
    ``persistent_notification`` zurück — eine Erinnerung darf nie verloren
    gehen, nur weil ein Handy gerade nicht erreichbar ist.
    """
    name = normalize_notify_service(notify_service)
    if name:
        try:
            if hass.services.has_service(_NOTIFY_DOMAIN, name):
                # S-3: blockierend aufrufen, damit Zustellfehler des Handlers
                # hier ankommen und der persistent-Fallback wirklich greift.
                await hass.services.async_call(
                    _NOTIFY_DOMAIN,
                    name,
                    {"title": title, "message": message},
                    blocking=True,
                )
                return True
            _LOGGER.warning(
                "Health-O-Mat: notify.%s nicht vorhanden — Fallback auf persistent_notification",
                name,
            )
        except Exception:  # noqa: BLE001 - Zustellung fällt auf persistent zurück
            _LOGGER.exception(
                "Health-O-Mat: notify.%s fehlgeschlagen — Fallback auf persistent_notification",
                name,
            )
    await hass.services.async_call(
        _PERSISTENT_NOTIFICATION_DOMAIN,
        "create",
        {"title": title, "message": message},
        blocking=False,
    )
    return False


async def _async_run_reminder(hass: HomeAssistant, entry: Any, store: Any, now: datetime) -> None:
    """Fällige Erinnerungen prüfen und genau EINE Notification senden."""
    options = getattr(entry, "options", None) or {}
    reminders = normalize_reminders(options.get(OPTION_REMINDERS))
    if not reminders["enabled"]:
        return
    if now.weekday() not in reminders["days"]:
        return
    if in_quiet_hours(now, reminders["quiet_start"], reminders["quiet_end"]):
        return

    active = store.active_entry(entry.entry_id) if store is not None else {}
    due = [
        kind
        for kind in reminder_due(active, options, now)
        if not _was_sent(hass, entry.entry_id, kind, now)
    ]
    if not due:
        return

    language = _language(hass)
    message = build_reminder_message(due, _person_name(entry), language)
    await async_send_notification(
        hass, reminders["notify_service"], reminder_title(language), message
    )
    _mark_sent(hass, entry.entry_id, due, now)


async def _async_run_weekly_report(
    hass: HomeAssistant, entry: Any, store: Any, now: datetime
) -> None:
    """Wochenbericht senden, wenn Wochentag passt und heute noch nicht gesendet."""
    options = getattr(entry, "options", None) or {}
    report = normalize_weekly_report(options.get(OPTION_WEEKLY_REPORT))
    if not report["enabled"] or now.weekday() != report["day"]:
        return
    if _was_sent(hass, entry.entry_id, _WEEKLY_REPORT_DEDUP_KEY, now):
        return

    active = store.active_entry(entry.entry_id) if store is not None else {}
    language = _language(hass)
    person = _person_name(entry)
    metrics = collect_weekly_metrics(active, options, now)
    message = render_weekly_report_markdown(metrics, person, language)
    await async_send_notification(
        hass,
        report["notify_service"],
        weekly_report_title(person, language),
        message,
    )
    _mark_sent(hass, entry.entry_id, [_WEEKLY_REPORT_DEDUP_KEY], now)


def _reminder_callback(hass: HomeAssistant, entry: Any, store: Any):
    """Timer-Callback für Erinnerungen (Fehler werden nur geloggt)."""

    async def _handle(now: datetime) -> None:
        try:
            await _async_run_reminder(hass, entry, store, now)
        except Exception:  # noqa: BLE001 - Timer-Callback darf HA nie stören
            _LOGGER.exception("Health-O-Mat: Erinnerung nicht zustellbar")

    return _handle


def _weekly_callback(hass: HomeAssistant, entry: Any, store: Any):
    """Timer-Callback für den Wochenbericht (Fehler werden nur geloggt)."""

    async def _handle(now: datetime) -> None:
        try:
            await _async_run_weekly_report(hass, entry, store, now)
        except Exception:  # noqa: BLE001 - Timer-Callback darf HA nie stören
            _LOGGER.exception("Health-O-Mat: Wochenbericht nicht zustellbar")

    return _handle


async def async_setup_reminders(hass: HomeAssistant, entry: Any, store: Any) -> None:
    """Erinnerungs-/Berichts-Timer eines Entries (neu) aufsetzen.

    Idempotent: vorhandene Unsubs des Entries werden zuerst abgemeldet. Der
    Dedup-Zustand bleibt dabei erhalten — ein Options-Speichern am selben Tag
    löst keine zweite Notification aus. Fehler sind nie setup-kritisch.
    """
    try:
        entry_id = entry.entry_id
        _cancel_unsubs(hass, entry_id)
        state = _entry_state(hass, entry_id)
        options = getattr(entry, "options", None) or {}
        rem = normalize_reminders(options.get(OPTION_REMINDERS))
        weekly = normalize_weekly_report(options.get(OPTION_WEEKLY_REPORT))
        unsubs: list[Any] = []
        if rem["enabled"]:
            hour, minute = _time_parts(rem["time"])
            unsubs.append(
                async_track_time_change(
                    hass,
                    _reminder_callback(hass, entry, store),
                    hour=hour,
                    minute=minute,
                    second=0,
                )
            )
        if weekly["enabled"]:
            hour, minute = _time_parts(weekly["time"])
            unsubs.append(
                async_track_time_change(
                    hass,
                    _weekly_callback(hass, entry, store),
                    hour=hour,
                    minute=minute,
                    second=0,
                )
            )
        state["reminder_unsubs"] = unsubs
    except Exception:  # noqa: BLE001 - Scheduler ist nie setup-kritisch
        _LOGGER.exception("Health-O-Mat: Erinnerungs-Scheduler nicht einrichtbar")


async def async_unload_reminders(hass: HomeAssistant, entry_id: str) -> None:
    """Timer abmelden und Dedup-State des Entries aufräumen."""
    try:
        _cancel_unsubs(hass, entry_id)
        registry = hass.data.get(DOMAIN)
        state = registry.get(entry_id) if isinstance(registry, dict) else None
        if isinstance(state, dict):
            state.pop("reminder_sent", None)
    except Exception:  # noqa: BLE001 - Unload darf nie am Scheduler scheitern
        _LOGGER.exception("Health-O-Mat: Erinnerungs-Scheduler nicht abbaubar")

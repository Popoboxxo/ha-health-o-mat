"""Konstanten für HA Health-O-Mat."""

from __future__ import annotations

DOMAIN = "health_o_mat"
MANUFACTURER = "Popoboxxo"
MODEL = "Health-O-Mat"

# Store
STORE_VERSION = 1
# Schema-Stufe des Store-Inhalts (steuert die Migrationskette in store.py);
# v1 = Ursprungsschema, v2 = +inputs (BP-Eingaben) je Person,
# v3 = +archived_counts (Retention/Archiv-Kennzahlen, REQ-HOM-109) je Person,
# v4 = +id/created_at/voided_* je Eintrag, +wellbeing_entries, +audit_log
#      (Korrigierbarkeit/Audit, REQ-HOM-115)
STORE_SCHEMA_VERSION = 4

# Audit-Log: Default-Cap an Ereignissen je Person (0 = unbegrenzt).
DEFAULT_AUDIT_LIMIT = 1000
# Obergrenze des Audit-Caps (Admin-Feld/Settings-Schema). Höhere Werte werden
# auf diesen Wert begrenzt, damit ein Zahlendreher das Log nicht unbegrenzt
# wachsen lässt (0 bleibt der explizite "unbegrenzt"-Wert).
MAX_AUDIT_LIMIT = 1_000_000
# Options-Schlüssel für den Audit-Cap (Admin-Maske via ws_api set_settings).
AUDIT_LIMIT_OPTION = "audit_limit"

# HA-Store-Keys: Haupt-Store (Historie) und separater Archiv-Store (Retention).
MAIN_STORE_KEY = "health_o_mat"
ARCHIVE_STORE_KEY = "health_o_mat_archive"

# Retention/Archiv (REQ-HOM-109): Monatswert 0 = AUS (exakt heutiges Verhalten).
DEFAULT_RETENTION_MONTHS = 0
MAX_RETENTION_MONTHS = 120

# Tagesziel / Mengen
DEFAULT_DAILY_GOAL_ML = 2000
DEFAULT_CUSTOM_AMOUNT_ML = 250
MAX_AMOUNT_ML = 10000

# Max. Anzahl Buchungen, die als JSON-Attribut im State landen (Finding N-1).
# Attribute werden im State-Objekt und im Recorder gespeichert und wüchsen
# sonst unbegrenzt mit jeder Buchung. Der Rohdaten-Vollbestand bleibt
# unverändert im Store bzw. im CSV-Export erhalten.
HISTORY_ATTRIBUTE_LIMIT = 100

# Blutdruck-Schwellen (Warn-Binary)
DEFAULT_SYS_THRESHOLD = 140
DEFAULT_DIA_THRESHOLD = 90
MIN_BP_VALUE = 40
MAX_BP_VALUE = 260

# Label für Buchungen ohne erkannten Typ
NO_TYPE_LABEL = "Eigen"

# Quick-Drinks-Standardset: (Schlüssel, Anzeigename, ml, MDI-Icon)
DEFAULT_QUICK_DRINKS: list[dict] = [
    {"key": "glas_wasser", "label": "Glas Wasser", "ml": 200, "icon": "mdi:glass-water"},
    {"key": "flasche_wasser", "label": "Flasche Wasser", "ml": 500, "icon": "mdi:bottle-water"},
    {"key": "kaffee", "label": "Tasse Kaffee", "ml": 250, "icon": "mdi:coffee"},
    {"key": "saft", "label": "Glas Saft", "ml": 200, "icon": "mdi:fruit-citrus"},
]

# Lexikon: Eingabe-Wort -> (kanonischer Typ, Default-ml)
DRINK_LEXICON: dict[str, tuple[str, int]] = {
    # Wasser
    "wasser": ("Wasser", 250),
    "water": ("Wasser", 250),
    "sprudel": ("Wasser", 250),
    "glas": ("Wasser", 200),
    "flasche": ("Wasser", 500),
    # Kaffee & Tee
    "kaffee": ("Kaffee", 250),
    "coffee": ("Kaffee", 250),
    "espresso": ("Espresso", 40),
    "tee": ("Tee", 300),
    "tea": ("Tee", 300),
    # Sonstiges
    "saft": ("Saft", 200),
    "juice": ("Saft", 200),
    "cola": ("Cola", 330),
    "limo": ("Limonade", 330),
    "bier": ("Bier", 500),
    "beer": ("Bier", 500),
    "wein": ("Wein", 200),
    "wine": ("Wein", 200),
    "sekt": ("Sekt", 100),
    "milch": ("Milch", 200),
    "milk": ("Milch", 200),
}

# Geschätzte Koffeinmenge je kanonischem Getränketyp in mg pro 100 ml
# (REQ-HOM-004). GROBE SCHÄTZWERTE — keine medizinische Aussage: reale Werte
# schwanken stark nach Sorte, Brühstärke, Zubereitung und Hersteller.
# Schlüssel sind exakt die kanonischen Typen aus DRINK_LEXICON; unbekannte
# Typen und der Label NO_TYPE_LABEL („Eigen") gelten als 0 mg.
CAFFEINE_MG_PER_100ML: dict[str, float] = {
    "Wasser": 0.0,
    "Kaffee": 40.0,  # Filterkaffee, grob ~80-100 mg je 250-ml-Tasse
    "Espresso": 200.0,  # ~80 mg je 40-ml-Shot
    "Tee": 20.0,  # Schwarztee, grob ~50-60 mg je 300-ml-Tasse
    "Saft": 0.0,
    "Cola": 10.0,  # ~34 mg je 330-ml-Dose
    "Limonade": 0.0,
    "Bier": 0.0,
    "Wein": 0.0,
    "Sekt": 0.0,
    "Milch": 0.0,
}

# Wohlbefinden „Wie geht es dir?": key, Anzeigename, Emoji, MDI-Icon.
# Die Reihenfolge ist die Score-Skala: Index + 1 = Score (1 = schlechtester,
# 10 = bester Wert). Bestehende Keys bleiben erhalten und liegen bewusst auf
# den ungeraden Stufen (1/3/5/7/9) — alte Messwerte bleiben damit lesbar.
WELLBEING_STATES: list[dict] = [
    {
        "key": "very_bad",
        "label": "Sehr schlecht",
        "emoji": "😭",
        "icon": "mdi:emoticon-cry-outline",
    },
    {"key": "awful", "label": "Elend", "emoji": "😖", "icon": "mdi:emoticon-dead-outline"},
    {"key": "bad", "label": "Schlecht", "emoji": "🙁", "icon": "mdi:emoticon-sad-outline"},
    {"key": "poor", "label": "Mäßig", "emoji": "😔", "icon": "mdi:emoticon-frown-outline"},
    {"key": "okay", "label": "Okay", "emoji": "😐", "icon": "mdi:emoticon-neutral-outline"},
    {
        "key": "mixed",
        "label": "Durchwachsen",
        "emoji": "😕",
        "icon": "mdi:emoticon-confused-outline",
    },
    {"key": "good", "label": "Gut", "emoji": "🙂", "icon": "mdi:emoticon-happy-outline"},
    {
        "key": "very_good",
        "label": "Sehr gut",
        "emoji": "😊",
        "icon": "mdi:emoticon-smile-outline",
    },
    {"key": "great", "label": "Großartig", "emoji": "😄", "icon": "mdi:emoticon-excited-outline"},
    {
        "key": "excellent",
        "label": "Ausgezeichnet",
        "emoji": "🤩",
        "icon": "mdi:emoticon-cool-outline",
    },
]

# Options-Schlüssel für eigene PNG/JPG-Bilder je Wellbeing-Key.
WELLBEING_IMAGES_OPTION = "wellbeing_images"

# Options-Schlüssel (REQ-HOM-114): Wohlbefinden-Auswahl erst nach Bestätigung
# übernehmen. Default aus = bisheriges Sofort-Verhalten.
OPTION_WELLBEING_CONFIRM = "wellbeing_confirm"

# --- Benachrichtigungen (REQ-HOM-118) ---------------------------------------
# Options-Schlüssel der genesteten Erinnerungs-/Berichtsstrukturen. Beide
# Defaults sind AUS: bestehende Installationen ändern ihr Verhalten nicht.
OPTION_REMINDERS = "reminders"
OPTION_WEEKLY_REPORT = "weekly_report"

DEFAULT_REMINDER_TIME = "20:00"
DEFAULT_WEEKLY_REPORT_TIME = "18:00"
# Default für "seit X Stunden nichts getrunken" (0 = Bedingung aus).
DEFAULT_REMINDER_NO_DRINK_HOURS = 3
# Fällige Erinnerungs-Arten in stabiler Reihenfolge (Notification-Reihenfolge).
REMINDER_KINDS: tuple[str, ...] = ("drink_goal", "no_drink", "bp", "wellbeing")

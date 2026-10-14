"""Konstanten für HA Health-O-Mat."""

from __future__ import annotations

DOMAIN = "health_o_mat"
MANUFACTURER = "Popoboxxo"
MODEL = "Health-O-Mat"

# Store
STORE_VERSION = 1
# Schema-Stufe des Store-Inhalts (steuert die Migrationskette in store.py);
# v1 = Ursprungsschema, v2 = +inputs (BP-Eingaben) je Person,
# v3 = +archived_counts (Retention/Archiv-Kennzahlen, REQ-HOM-109) je Person
STORE_SCHEMA_VERSION = 3

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

# Wohlbefinden „Wie geht es dir?": key, Anzeigename, Emoji, MDI-Icon
WELLBEING_STATES: list[dict] = [
    {
        "key": "very_bad",
        "label": "Sehr schlecht",
        "emoji": "😵",
        "icon": "mdi:emoticon-dead-outline",
    },
    {"key": "bad", "label": "Schlecht", "emoji": "🙁", "icon": "mdi:emoticon-sad-outline"},
    {"key": "okay", "label": "Okay", "emoji": "😐", "icon": "mdi:emoticon-neutral-outline"},
    {"key": "good", "label": "Gut", "emoji": "🙂", "icon": "mdi:emoticon-happy-outline"},
    {"key": "great", "label": "Super", "emoji": "😄", "icon": "mdi:emoticon-excited-outline"},
]

"""Konstanten für HA Health-O-Mat."""
from __future__ import annotations

DOMAIN = "health_o_mat"
MANUFACTURER = "Popoboxxo"
MODEL = "Health-O-Mat"

# Store
STORE_VERSION = 1
# Schema-Stufe des Store-Inhalts (steuert die Migrationskette in store.py);
# v1 = Ursprungsschema, v2 = +inputs (BP-Eingaben) je Person
STORE_SCHEMA_VERSION = 2

# Tagesziel / Mengen
DEFAULT_DAILY_GOAL_ML = 2000
DEFAULT_CUSTOM_AMOUNT_ML = 250
MAX_AMOUNT_ML = 10000

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
    "wasser": ("Wasser", 250), "water": ("Wasser", 250), "sprudel": ("Wasser", 250),
    "glas": ("Wasser", 200), "flasche": ("Wasser", 500),
    # Kaffee & Tee
    "kaffee": ("Kaffee", 250), "coffee": ("Kaffee", 250), "espresso": ("Espresso", 40),
    "tee": ("Tee", 300), "tea": ("Tee", 300),
    # Sonstiges
    "saft": ("Saft", 200), "juice": ("Saft", 200),
    "cola": ("Cola", 330), "limo": ("Limonade", 330),
    "bier": ("Bier", 500), "beer": ("Bier", 500),
    "wein": ("Wein", 200), "wine": ("Wein", 200), "sekt": ("Sekt", 100),
    "milch": ("Milch", 200), "milk": ("Milch", 200),
}

# Wohlbefinden „Wie geht es dir?": key, Anzeigename, Emoji, MDI-Icon
WELLBEING_STATES: list[dict] = [
    {"key": "very_bad", "label": "Sehr schlecht", "emoji": "😵", "icon": "mdi:emoticon-dead-outline"},
    {"key": "bad", "label": "Schlecht", "emoji": "🙁", "icon": "mdi:emoticon-sad-outline"},
    {"key": "okay", "label": "Okay", "emoji": "😐", "icon": "mdi:emoticon-neutral-outline"},
    {"key": "good", "label": "Gut", "emoji": "🙂", "icon": "mdi:emoticon-happy-outline"},
    {"key": "great", "label": "Super", "emoji": "😄", "icon": "mdi:emoticon-excited-outline"},
]

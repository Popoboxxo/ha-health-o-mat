"""Konstanten für HA Health-O-Mat."""
from __future__ import annotations

DOMAIN = "health_o_mat"
MANUFACTURER = "Popoboxxo"
MODEL = "Health-O-Mat"

# Store
STORE_VERSION = 1

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

# Tagesgrenzen-Auswahl (Select)
DAY_BOUNDARY_MIDNIGHT = "midnight"   # 0 Uhr (Default, per Definition)
DAY_BOUNDARY_22 = "2200"             # Alt-Verhalten der Reset-Automation
DAY_BOUNDARY_04 = "0400"             # „Nacht gehört zum Vortag"
DAY_BOUNDARY_CUSTOM = "custom"
DAY_BOUNDARY_OPTIONS = [
    DAY_BOUNDARY_MIDNIGHT,
    DAY_BOUNDARY_22,
    DAY_BOUNDARY_04,
    DAY_BOUNDARY_CUSTOM,
]
BOUNDARY_HOUR_MINUTE: dict[str, tuple[int, int]] = {
    DAY_BOUNDARY_MIDNIGHT: (0, 0),
    DAY_BOUNDARY_22: (22, 0),
    DAY_BOUNDARY_04: (4, 0),
}

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
# v5 = +lab_readings je Person (Laborwerte, REQ-HOM-122)
STORE_SCHEMA_VERSION = 5

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

# --- Laborwerte (Blutwerte, REQ-HOM-122) ------------------------------------
# Default-Referenzen sind typische Erwachsenen-Richtwerte (Vision §4.2 "Keine
# medizinische Beratung") — keine klinische Norm, siehe Recherche-Kapitel 3
# der Spec (docs/superpowers/specs/2026-10-30-lab-values-design.md).

LAB_CATEGORY_OTHER = "other"

LAB_CATEGORIES: list[dict] = [
    {"key": "liver", "name_de": "Leber", "name_en": "Liver"},
    {"key": "kidney", "name_de": "Niere", "name_en": "Kidney"},
    {"key": "electrolytes", "name_de": "Elektrolyte", "name_en": "Electrolytes"},
    {"key": "lipids", "name_de": "Lipide", "name_en": "Lipids"},
    {"key": "thyroid", "name_de": "Schilddrüse", "name_en": "Thyroid"},
    {"key": "blood_count", "name_de": "Blutbild", "name_en": "Blood count"},
    {"key": "inflammation", "name_de": "Entzündung/Immunsystem", "name_en": "Inflammation"},
    {"key": "digestion", "name_de": "Verdauung", "name_en": "Digestion"},
    {"key": "drug_levels", "name_de": "Medikamentenspiegel", "name_en": "Drug levels"},
    # REQ-HOM-133 (#73): HbA1c gehört nicht in "Sonstige" — "other" bleibt
    # Fallback für Custom-Marker und muss deshalb der letzte Eintrag sein
    # (binary_sensor.py leitet die Warn-Entities aus dieser Liste ab).
    {"key": "metabolism", "name_de": "Stoffwechsel", "name_en": "Metabolism"},
    {"key": LAB_CATEGORY_OTHER, "name_de": "Sonstige", "name_en": "Other"},
]

# marker_key -> {category, name_de, name_en, canonical_unit, ref_min, ref_max,
#                alt_units: {unit: factor_to_canonical}, require_explicit_unit}
# ref_min/ref_max: None = keine Grenze auf dieser Seite. alt_units leer = keine
# Umrechnung nötig (Wert liegt schon kanonisch vor bzw. keine Alt-Einheit bekannt).
LAB_MARKERS: dict[str, dict] = {
    "alt": {
        "category": "liver",
        "name_de": "ALT (GPT)",
        "name_en": "ALT (ALT/GPT)",
        "canonical_unit": "U/L",
        "ref_min": 10,
        "ref_max": 50,
        "alt_units": {},
        "require_explicit_unit": False,
    },
    "ast": {
        "category": "liver",
        "name_de": "AST (GOT)",
        "name_en": "AST (AST/GOT)",
        "canonical_unit": "U/L",
        "ref_min": 10,
        "ref_max": 50,
        "alt_units": {},
        "require_explicit_unit": False,
    },
    "ggt": {
        "category": "liver",
        "name_de": "GGT (Gamma-GT)",
        "name_en": "GGT",
        "canonical_unit": "U/L",
        "ref_min": 10,
        "ref_max": 60,
        "alt_units": {},
        "require_explicit_unit": False,
    },
    "bilirubin_total": {
        "category": "liver",
        "name_de": "Bilirubin gesamt",
        "name_en": "Total bilirubin",
        "canonical_unit": "µmol/L",
        "ref_min": 5,
        "ref_max": 21,
        "alt_units": {"mg/dL": 17.1},
        "require_explicit_unit": False,
    },
    "total_protein": {
        "category": "liver",
        "name_de": "Gesamteiweiß",
        "name_en": "Total protein",
        "canonical_unit": "g/L",
        "ref_min": 64,
        "ref_max": 83,
        "alt_units": {},
        "require_explicit_unit": False,
    },
    # REQ-HOM-133 (#73): Laborbefund-Katalog, Werte wörtlich aus dem Issue.
    # Faktor in `alt_units` rechnet GEMELDET -> kanonisch.
    "albumin": {
        "category": "liver",
        "name_de": "Albumin",
        "name_en": "Albumin",
        "canonical_unit": "g/L",
        "ref_min": 35,
        "ref_max": 52,
        "alt_units": {"g/dL": 10},
        "require_explicit_unit": True,
    },
    "alkaline_phosphatase": {
        "category": "liver",
        "name_de": "Alkalische Phosphatase (AP)",
        "name_en": "Alkaline phosphatase (ALP)",
        "canonical_unit": "U/L",
        "ref_min": 35,
        "ref_max": 105,
        "alt_units": {"µkat/L": 60},
        "require_explicit_unit": True,
    },
    "creatinine": {
        "category": "kidney",
        "name_de": "Kreatinin",
        "name_en": "Creatinine",
        "canonical_unit": "µmol/L",
        "ref_min": 53,
        "ref_max": 106,
        "alt_units": {"mg/dL": 88.4},
        "require_explicit_unit": False,
    },
    "egfr": {
        "category": "kidney",
        "name_de": "eGFR",
        "name_en": "eGFR",
        "canonical_unit": "mL/min/1.73m²",
        "ref_min": 90,
        "ref_max": None,
        "alt_units": {},
        "require_explicit_unit": False,
    },
    "urea": {
        "category": "kidney",
        "name_de": "Harnstoff",
        "name_en": "Urea",
        "canonical_unit": "mmol/L",
        "ref_min": 2.5,
        "ref_max": 7.5,
        "alt_units": {"mg/dL": 0.357},
        "require_explicit_unit": False,
    },
    "urine_protein_creatinine_ratio": {
        "category": "kidney",
        "name_de": "Protein/Kreatinin-Quotient (Urin)",
        "name_en": "Urine protein/creatinine ratio",
        "canonical_unit": "mg/g",
        "ref_min": None,
        "ref_max": 15,
        # Bekannte Verwechslungsgefahr g/g vs. mg/g (Faktor 1000) — deshalb
        # KEIN impliziter Default, unit ist Pflichtfeld (§5.1 der Spec).
        "alt_units": {"g/g": 1000},
        "require_explicit_unit": True,
    },
    "uric_acid": {
        "category": "kidney",
        "name_de": "Harnsäure",
        "name_en": "Uric acid",
        "canonical_unit": "mg/dL",
        "ref_min": 2.3,
        "ref_max": 6.1,
        # µmol/L -> mg/dL (Faktor 0.01681); ohne Einheit wäre die Zahl
        # hundertfach falsch, deshalb Pflichtfeld.
        "alt_units": {"µmol/L": 0.01681},
        "require_explicit_unit": True,
    },
    "sodium": {
        "category": "electrolytes",
        "name_de": "Natrium",
        "name_en": "Sodium",
        "canonical_unit": "mmol/L",
        "ref_min": 135,
        "ref_max": 145,
        "alt_units": {},
        "require_explicit_unit": False,
    },
    "potassium": {
        "category": "electrolytes",
        "name_de": "Kalium",
        "name_en": "Potassium",
        "canonical_unit": "mmol/L",
        "ref_min": 3.5,
        "ref_max": 5.0,
        "alt_units": {},
        "require_explicit_unit": False,
    },
    "calcium": {
        "category": "electrolytes",
        "name_de": "Calcium gesamt",
        "name_en": "Total calcium",
        "canonical_unit": "mmol/L",
        "ref_min": 2.10,
        "ref_max": 2.60,
        "alt_units": {"mg/dL": 0.25},
        "require_explicit_unit": False,
    },
    "magnesium": {
        "category": "electrolytes",
        "name_de": "Magnesium",
        "name_en": "Magnesium",
        "canonical_unit": "mmol/L",
        "ref_min": 0.70,
        "ref_max": 1.00,
        "alt_units": {"mg/dL": 0.411},
        "require_explicit_unit": False,
    },
    "chloride": {
        "category": "electrolytes",
        "name_de": "Chlorid",
        "name_en": "Chloride",
        "canonical_unit": "mmol/L",
        "ref_min": 98,
        "ref_max": 107,
        "alt_units": {},
        "require_explicit_unit": False,
    },
    "phosphate": {
        "category": "electrolytes",
        "name_de": "Phosphat",
        "name_en": "Phosphate",
        "canonical_unit": "mmol/L",
        "ref_min": 0.87,
        "ref_max": 1.45,
        # mg/dL -> mmol/L (Faktor 0.3229).
        "alt_units": {"mg/dL": 0.3229},
        "require_explicit_unit": True,
    },
    "cholesterol_total": {
        "category": "lipids",
        "name_de": "Gesamtcholesterin",
        "name_en": "Total cholesterol",
        "canonical_unit": "mmol/L",
        "ref_min": None,
        "ref_max": 5.2,
        "alt_units": {"mg/dL": 0.0259},
        "require_explicit_unit": False,
    },
    "ldl": {
        "category": "lipids",
        "name_de": "LDL",
        "name_en": "LDL",
        "canonical_unit": "mmol/L",
        "ref_min": None,
        "ref_max": 2.6,
        "alt_units": {"mg/dL": 0.0259},
        "require_explicit_unit": False,
    },
    "hdl": {
        "category": "lipids",
        "name_de": "HDL",
        "name_en": "HDL",
        "canonical_unit": "mmol/L",
        "ref_min": 1.0,
        "ref_max": None,
        "alt_units": {"mg/dL": 0.0259},
        "require_explicit_unit": False,
    },
    "triglycerides": {
        "category": "lipids",
        "name_de": "Triglyceride",
        "name_en": "Triglycerides",
        "canonical_unit": "mmol/L",
        "ref_min": None,
        "ref_max": 1.7,
        "alt_units": {"mg/dL": 0.0113},
        "require_explicit_unit": False,
    },
    "tsh": {
        "category": "thyroid",
        "name_de": "TSH",
        "name_en": "TSH",
        "canonical_unit": "mIU/L",
        "ref_min": 0.4,
        "ref_max": 4.0,
        "alt_units": {},
        "require_explicit_unit": False,
    },
    "ft4": {
        "category": "thyroid",
        "name_de": "fT4",
        "name_en": "fT4",
        "canonical_unit": "pmol/L",
        "ref_min": 10,
        "ref_max": 23,
        "alt_units": {"ng/dL": 12.87},
        "require_explicit_unit": False,
    },
    "ft3": {
        "category": "thyroid",
        "name_de": "fT3",
        "name_en": "fT3",
        "canonical_unit": "pmol/L",
        "ref_min": 3,
        "ref_max": 8,
        "alt_units": {"pg/mL": 1.536},
        "require_explicit_unit": False,
    },
    "hemoglobin": {
        "category": "blood_count",
        "name_de": "Hämoglobin",
        "name_en": "Hemoglobin",
        "canonical_unit": "g/L",
        "ref_min": 120,
        "ref_max": 170,
        "alt_units": {"g/dL": 10},
        "require_explicit_unit": False,
    },
    "leukocytes": {
        "category": "blood_count",
        "name_de": "Leukozyten",
        "name_en": "Leukocytes",
        "canonical_unit": "10^9/L",
        "ref_min": 3.6,
        "ref_max": 11.0,
        "alt_units": {},
        "require_explicit_unit": False,
    },
    "platelets": {
        "category": "blood_count",
        "name_de": "Thrombozyten",
        "name_en": "Platelets",
        "canonical_unit": "10^9/L",
        "ref_min": 140,
        "ref_max": 400,
        "alt_units": {},
        "require_explicit_unit": False,
    },
    "mch": {
        "category": "blood_count",
        "name_de": "MCH",
        "name_en": "MCH",
        "canonical_unit": "pg",
        "ref_min": 27.0,
        "ref_max": 33.5,
        "alt_units": {},
        "require_explicit_unit": False,
    },
    "erythrocytes": {
        "category": "blood_count",
        "name_de": "Erythrozyten",
        "name_en": "Erythrocytes",
        "canonical_unit": "10^12/L",
        "ref_min": 3.9,
        "ref_max": 5.2,
        # 1:1-Alias (10⁶/µL == 10^12/L) — reine Schreibweisen-Variante.
        "alt_units": {"10⁶/µL": 1},
        "require_explicit_unit": False,
    },
    "hematocrit": {
        "category": "blood_count",
        "name_de": "Hämatokrit",
        "name_en": "Hematocrit",
        "canonical_unit": "L/L",
        "ref_min": 0.355,
        "ref_max": 0.455,
        # 42 % -> 0,42 L/L (Faktor 0.01).
        "alt_units": {"%": 0.01},
        "require_explicit_unit": True,
    },
    "mchc": {
        "category": "blood_count",
        "name_de": "MCHC",
        "name_en": "MCHC",
        "canonical_unit": "g/dL",
        "ref_min": 31.5,
        "ref_max": 36.0,
        "alt_units": {},
        "require_explicit_unit": True,
    },
    "mcv": {
        "category": "blood_count",
        "name_de": "MCV",
        "name_en": "MCV",
        "canonical_unit": "fl",
        "ref_min": 80.0,
        "ref_max": 99.0,
        # 1:1-Alias (µm³ == fl).
        "alt_units": {"µm³": 1},
        "require_explicit_unit": False,
    },
    "crp": {
        "category": "inflammation",
        "name_de": "CRP",
        "name_en": "CRP",
        "canonical_unit": "mg/L",
        "ref_min": None,
        "ref_max": 5,
        "alt_units": {},
        "require_explicit_unit": False,
    },
    "esr": {
        "category": "inflammation",
        "name_de": "BSG",
        "name_en": "ESR",
        "canonical_unit": "mm/h",
        "ref_min": None,
        "ref_max": 20,
        "alt_units": {},
        "require_explicit_unit": False,
    },
    "lipase": {
        "category": "digestion",
        "name_de": "Lipase",
        "name_en": "Lipase",
        "canonical_unit": "U/L",
        "ref_min": 13,
        "ref_max": 60,
        "alt_units": {},
        "require_explicit_unit": False,
    },
    "amylase": {
        "category": "digestion",
        "name_de": "Amylase",
        "name_en": "Amylase",
        "canonical_unit": "U/L",
        "ref_min": 30,
        "ref_max": 110,
        "alt_units": {},
        "require_explicit_unit": False,
    },
    "tacrolimus": {
        "category": "drug_levels",
        "name_de": "Tacrolimus (Talspiegel)",
        "name_en": "Tacrolimus (trough)",
        "canonical_unit": "ng/mL",
        "ref_min": 5,
        "ref_max": 15,
        "alt_units": {},
        "require_explicit_unit": False,
    },
    # Laborabhängige Talspiegel: keine feste Referenz (ref_min/ref_max = None).
    "ciclosporin": {
        "category": "drug_levels",
        "name_de": "Ciclosporin (Talspiegel)",
        "name_en": "Ciclosporin (trough)",
        "canonical_unit": "ng/mL",
        "ref_min": None,
        "ref_max": None,
        # 1:1-Alias (µg/L == ng/mL).
        "alt_units": {"µg/L": 1},
        "require_explicit_unit": False,
    },
    "everolimus": {
        "category": "drug_levels",
        "name_de": "Everolimus (Talspiegel)",
        "name_en": "Everolimus (trough)",
        "canonical_unit": "ng/mL",
        "ref_min": None,
        "ref_max": None,
        "alt_units": {"µg/L": 1},
        "require_explicit_unit": False,
    },
    # HbA1c in mmol/mol (IFCC). Die DCCT-Einheit % ist NICHT linear
    # umrechenbar und bleibt deshalb `unsupported_unit` (Beschluss D3/B5).
    "hba1c": {
        "category": "metabolism",
        "name_de": "HbA1c",
        "name_en": "HbA1c",
        "canonical_unit": "mmol/mol",
        "ref_min": 29,
        "ref_max": 42,
        "alt_units": {},
        "require_explicit_unit": True,
    },
}

# Deutsche Laborsynonyme -> primärer marker_key (§2.1a der Spec). Wird vom
# Service VOR dem Katalog-/Custom-Abgleich aufgelöst, kein Doppel-Eintrag.
LAB_MARKER_ALIASES: dict[str, str] = {
    "gpt": "alt",
    "got": "ast",
    "gamma_gt": "ggt",
}

# Options-Schlüssel (entry.options) für Custom-Marker/Overrides/Sichtbarkeit.
OPTION_LAB_CUSTOM_MARKERS = "lab_custom_markers"
OPTION_LAB_REF_OVERRIDES = "lab_ref_overrides"
OPTION_LAB_HIDDEN_CATEGORIES = "lab_hidden_categories"

# Labor-Retention (REQ-HOM-129): eigene Option, unabhängig von
# `retention_months` (Getränke/BD); 0 = aus (Default = bisheriges Verhalten).
OPTION_LAB_RETENTION_MONTHS = "lab_retention_months"

# Panel-Medizin-Hinweis (REQ-HOM-125): Admin-Schalter, Default False = sichtbar.
OPTION_LAB_HIDE_PANEL_DISCLAIMER = "lab_hide_panel_disclaimer"

# Max. Länge des optionalen `report_ref`-Freitextfelds (§2.4a der Spec).
LAB_REPORT_REF_MAX_LEN = 500

# LEICHTER Batch-Vertrag (REQ-HOM-123): Server-Limit je Bericht; die UI hat
# einen eigenen Soft-Cap (60). Beide Werte sind bewusst unabhängig.
LAB_REPORT_MAX_ROWS = 200

# CSV-Upload über die WebSocket-API (#72): Obergrenze des `content`-Strings.
# Die Länge wird VOR dem Parsen geprüft (Event-Loop-Schutz) und nie
# abgeschnitten — zu großer Inhalt wird vollständig abgelehnt.
MAX_IMPORT_CONTENT_BYTES = 2 * 1024 * 1024

# Obergrenze der Fehlertexte in einer Import-Antwort (#71): die Zähler
# (`imported`/`skipped`/`rejected`) bleiben autoritativ, die Liste ist nur
# eine Hilfe für die UI.
IMPORT_ERROR_LIMIT = 20

# Laborwerte (Blutwerte) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Laborwerte (lab/blood test values) as a fourth data domain alongside Trinken/Blutdruck/Wohlbefinden — categorized, extensible with per-person custom markers, unit-conversion-aware, with its own services, entities, admin UI, Lovelace card, panel integration, and full Backup/Export/Import support.

**Architecture:** Follows the existing per-person Config-Entry architecture 1:1. A new `lab_readings[]` list lives in the existing `HealthOMatStore` (schema v4→v5), gated by a new `areas.labs` toggle. A small catalog (`const.py: LAB_CATEGORIES`/`LAB_MARKERS`/`LAB_MARKER_ALIASES`) plus per-person custom markers (`entry.options["lab_custom_markers"]`) are merged by new HA-free helpers in `logic.py` (`effective_lab_markers`, `resolve_lab_marker`, `convert_lab_value`, `resolve_lab_reference`, `lab_marker_in_range`). Two new services (`add_lab_value`, `remove_last_lab_value`) and one dynamic sensor per marker + one binary_sensor per category reuse the existing service/entity patterns exactly. A new standalone Lovelace card (`health-o-mat-labs-card`) plus a 4th Panel tab + Overview tile row complete the UI; Backup/Restore/Export/Import gain the new dataset additively.

**Tech Stack:** Python (Home Assistant custom component conventions already used throughout this repo), vanilla JS (no frameworks, matches existing Card/Panel), pytest with the repo's fake-HA `conftest.py`, voluptuous for service/WS schemas.

**Spec:** `docs/superpowers/specs/2026-10-30-lab-values-design.md` (merged to `main` via PR #49 + #50) — this plan implements all of sections 1–9; section 10's open points are resolved below.

**Branch:** All work in this plan happens on a single feature branch `feat/lab-values`, created off latest `main`, per `.claude/rules/branch-guard.md` (no direct commits to `main`). Git mutations (branch create, commit, push) go through the `git` subagent per `.claude/rules/use-orchestrator.md` — this plan's steps show the exact commit commands/messages for that agent to run, not to be run directly in the main session.

## Global Constraints

- Commit messages: Conventional Commits, English, imperative, first line ≤ 72 chars (`.claude/rules/commit-conventions.md`). Every commit step below gives the exact message.
- `from __future__ import annotations` + full type hints on every new/touched Python file (project convention).
- `unique_id` = `{entry_id}_{key}`, never changed after creation (HACS iron rule). New entity keys introduced here: `lab_{marker_key}` (sensor) and `binary_lab_warning_{category}` (binary_sensor) — chosen once, must stay stable.
- Store lives at `hass.data[DOMAIN]["shared"]["store"]`; per-entry runtime data at `hass.data[DOMAIN][entry_id]`. No new storage mechanism — the new `lab_readings[]` list is a sibling of `drinks[]`/`readings[]` inside the existing per-entry dict.
- `has_entity_name = True` + `translation_key` for catalog-marker entities (name is translatable); custom-marker entities use `_attr_name` directly (spec §4: "bewusst einsprachig").
- Options are the home for anything person-correctable after initial setup (`lab_custom_markers`, `lab_ref_overrides`, `lab_hidden_categories` all live in `entry.options`, never `entry.data`).
- `ServiceValidationError` for all service-level validation failures, then `signal_refresh(hass, entry_id)` on success — the existing pattern in `__init__.py`, do not invent a second error-reporting path.
- YAGNI / ponytail: the custom-marker `alt_unit` is exactly ONE optional pair (not an open multi-unit framework); `report_ref` is a plain capped string field (no new "LabReport" entity/aggregate); no new chart library, gesture library, or JS framework — reuse existing SVG/vanilla-JS helpers.
- This project tracks every feature as a REQ-ID in `docs/REQUIREMENTS.md` (actual established convention, see REQ-HOM-001..121) despite the stale `CLAUDE.md` DoD-preset footer claiming "REQ-Traceability: false" — this plan follows the codebase's real, consistently-applied convention and assigns **REQ-HOM-122** to this feature (Task 28).
- Tests: this repo has pervasive test coverage (1167+ passing tests as of the last changelog entry) and the spec's own §9 explicitly calls for HA-free logic tests, store tests, service validation tests, entity tests, JS tests, backup/restore round-trip tests, migration idempotency tests, and an E2E smoke test. Every task below includes real TDD steps matching this depth — the generic "Tests: false" preset note does not apply here, the actual repo convention wins.
- `pytest -q` and `ruff check .` must stay clean after every task's commit (existing CI gates, `.github/workflows/validate.yml` equivalent — verify locally before each commit).

---

## Wave 1 — Store + Logic + Migration

### Task 1: Lab catalog data in `const.py`

**Files:**
- Modify: `custom_components/health_o_mat/const.py`

**Interfaces:**
- Produces: `LAB_CATEGORIES: list[dict]` (each `{"key": str, "name_de": str, "name_en": str}`, 10 entries: 9 catalog categories + `"other"`), `LAB_CATEGORY_OTHER = "other"`, `LAB_MARKERS: dict[str, dict]` (29 catalog markers, each `{"category", "name_de", "name_en", "canonical_unit", "ref_min", "ref_max", "alt_units", "require_explicit_unit"}`), `LAB_MARKER_ALIASES: dict[str, str]`, `OPTION_LAB_CUSTOM_MARKERS = "lab_custom_markers"`, `OPTION_LAB_REF_OVERRIDES = "lab_ref_overrides"`, `OPTION_LAB_HIDDEN_CATEGORIES = "lab_hidden_categories"`, `LAB_REPORT_REF_MAX_LEN = 500`. `STORE_SCHEMA_VERSION` bumped `4` → `5`.
- Consumes: nothing (pure data module, no new imports).

- [ ] **Step 1: Bump the schema version constant and document it**

Edit the existing comment block and value in `const.py`:

```python
# v4 = +id/created_at/voided_* je Eintrag, +wellbeing_entries, +audit_log
#      (Korrigierbarkeit/Audit, REQ-HOM-115)
# v5 = +lab_readings je Person (Laborwerte, REQ-HOM-122)
STORE_SCHEMA_VERSION = 5
```

- [ ] **Step 2: Add the lab catalog constants** (append near the end of `const.py`, after `REMINDER_KINDS`)

```python
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
    {"key": LAB_CATEGORY_OTHER, "name_de": "Sonstige", "name_en": "Other"},
]

# marker_key -> {category, name_de, name_en, canonical_unit, ref_min, ref_max,
#                alt_units: {unit: factor_to_canonical}, require_explicit_unit}
# ref_min/ref_max: None = keine Grenze auf dieser Seite. alt_units leer = keine
# Umrechnung nötig (Wert liegt schon kanonisch vor bzw. keine Alt-Einheit bekannt).
LAB_MARKERS: dict[str, dict] = {
    "alt": {
        "category": "liver", "name_de": "ALT (GPT)", "name_en": "ALT (ALT/GPT)",
        "canonical_unit": "U/L", "ref_min": 10, "ref_max": 50,
        "alt_units": {}, "require_explicit_unit": False,
    },
    "ast": {
        "category": "liver", "name_de": "AST (GOT)", "name_en": "AST (AST/GOT)",
        "canonical_unit": "U/L", "ref_min": 10, "ref_max": 50,
        "alt_units": {}, "require_explicit_unit": False,
    },
    "ggt": {
        "category": "liver", "name_de": "GGT (Gamma-GT)", "name_en": "GGT",
        "canonical_unit": "U/L", "ref_min": 10, "ref_max": 60,
        "alt_units": {}, "require_explicit_unit": False,
    },
    "bilirubin_total": {
        "category": "liver", "name_de": "Bilirubin gesamt", "name_en": "Total bilirubin",
        "canonical_unit": "µmol/L", "ref_min": 5, "ref_max": 21,
        "alt_units": {"mg/dL": 17.1}, "require_explicit_unit": False,
    },
    "total_protein": {
        "category": "liver", "name_de": "Gesamteiweiß", "name_en": "Total protein",
        "canonical_unit": "g/L", "ref_min": 64, "ref_max": 83,
        "alt_units": {}, "require_explicit_unit": False,
    },
    "creatinine": {
        "category": "kidney", "name_de": "Kreatinin", "name_en": "Creatinine",
        "canonical_unit": "µmol/L", "ref_min": 53, "ref_max": 106,
        "alt_units": {"mg/dL": 88.4}, "require_explicit_unit": False,
    },
    "egfr": {
        "category": "kidney", "name_de": "eGFR", "name_en": "eGFR",
        "canonical_unit": "mL/min/1.73m²", "ref_min": 90, "ref_max": None,
        "alt_units": {}, "require_explicit_unit": False,
    },
    "urea": {
        "category": "kidney", "name_de": "Harnstoff", "name_en": "Urea",
        "canonical_unit": "mmol/L", "ref_min": 2.5, "ref_max": 7.5,
        "alt_units": {"mg/dL": 0.357}, "require_explicit_unit": False,
    },
    "urine_protein_creatinine_ratio": {
        "category": "kidney",
        "name_de": "Protein/Kreatinin-Quotient (Urin)",
        "name_en": "Urine protein/creatinine ratio",
        "canonical_unit": "mg/g", "ref_min": None, "ref_max": 15,
        # Bekannte Verwechslungsgefahr g/g vs. mg/g (Faktor 1000) — deshalb
        # KEIN impliziter Default, unit ist Pflichtfeld (§5.1 der Spec).
        "alt_units": {"g/g": 1000}, "require_explicit_unit": True,
    },
    "sodium": {
        "category": "electrolytes", "name_de": "Natrium", "name_en": "Sodium",
        "canonical_unit": "mmol/L", "ref_min": 135, "ref_max": 145,
        "alt_units": {}, "require_explicit_unit": False,
    },
    "potassium": {
        "category": "electrolytes", "name_de": "Kalium", "name_en": "Potassium",
        "canonical_unit": "mmol/L", "ref_min": 3.5, "ref_max": 5.0,
        "alt_units": {}, "require_explicit_unit": False,
    },
    "calcium": {
        "category": "electrolytes", "name_de": "Calcium gesamt", "name_en": "Total calcium",
        "canonical_unit": "mmol/L", "ref_min": 2.10, "ref_max": 2.60,
        "alt_units": {"mg/dL": 0.25}, "require_explicit_unit": False,
    },
    "magnesium": {
        "category": "electrolytes", "name_de": "Magnesium", "name_en": "Magnesium",
        "canonical_unit": "mmol/L", "ref_min": 0.70, "ref_max": 1.00,
        "alt_units": {"mg/dL": 0.411}, "require_explicit_unit": False,
    },
    "chloride": {
        "category": "electrolytes", "name_de": "Chlorid", "name_en": "Chloride",
        "canonical_unit": "mmol/L", "ref_min": 98, "ref_max": 107,
        "alt_units": {}, "require_explicit_unit": False,
    },
    "cholesterol_total": {
        "category": "lipids", "name_de": "Gesamtcholesterin", "name_en": "Total cholesterol",
        "canonical_unit": "mmol/L", "ref_min": None, "ref_max": 5.2,
        "alt_units": {"mg/dL": 0.0259}, "require_explicit_unit": False,
    },
    "ldl": {
        "category": "lipids", "name_de": "LDL", "name_en": "LDL",
        "canonical_unit": "mmol/L", "ref_min": None, "ref_max": 2.6,
        "alt_units": {"mg/dL": 0.0259}, "require_explicit_unit": False,
    },
    "hdl": {
        "category": "lipids", "name_de": "HDL", "name_en": "HDL",
        "canonical_unit": "mmol/L", "ref_min": 1.0, "ref_max": None,
        "alt_units": {"mg/dL": 0.0259}, "require_explicit_unit": False,
    },
    "triglycerides": {
        "category": "lipids", "name_de": "Triglyceride", "name_en": "Triglycerides",
        "canonical_unit": "mmol/L", "ref_min": None, "ref_max": 1.7,
        "alt_units": {"mg/dL": 0.0113}, "require_explicit_unit": False,
    },
    "tsh": {
        "category": "thyroid", "name_de": "TSH", "name_en": "TSH",
        "canonical_unit": "mIU/L", "ref_min": 0.4, "ref_max": 4.0,
        "alt_units": {}, "require_explicit_unit": False,
    },
    "ft4": {
        "category": "thyroid", "name_de": "fT4", "name_en": "fT4",
        "canonical_unit": "pmol/L", "ref_min": 10, "ref_max": 23,
        "alt_units": {"ng/dL": 12.87}, "require_explicit_unit": False,
    },
    "ft3": {
        "category": "thyroid", "name_de": "fT3", "name_en": "fT3",
        "canonical_unit": "pmol/L", "ref_min": 3, "ref_max": 8,
        "alt_units": {"pg/mL": 1.536}, "require_explicit_unit": False,
    },
    "hemoglobin": {
        "category": "blood_count", "name_de": "Hämoglobin", "name_en": "Hemoglobin",
        "canonical_unit": "g/L", "ref_min": 120, "ref_max": 170,
        "alt_units": {"g/dL": 10}, "require_explicit_unit": False,
    },
    "leukocytes": {
        "category": "blood_count", "name_de": "Leukozyten", "name_en": "Leukocytes",
        "canonical_unit": "10^9/L", "ref_min": 3.6, "ref_max": 11.0,
        "alt_units": {}, "require_explicit_unit": False,
    },
    "platelets": {
        "category": "blood_count", "name_de": "Thrombozyten", "name_en": "Platelets",
        "canonical_unit": "10^9/L", "ref_min": 140, "ref_max": 400,
        "alt_units": {}, "require_explicit_unit": False,
    },
    "crp": {
        "category": "inflammation", "name_de": "CRP", "name_en": "CRP",
        "canonical_unit": "mg/L", "ref_min": None, "ref_max": 5,
        "alt_units": {}, "require_explicit_unit": False,
    },
    "esr": {
        "category": "inflammation", "name_de": "BSG", "name_en": "ESR",
        "canonical_unit": "mm/h", "ref_min": None, "ref_max": 20,
        "alt_units": {}, "require_explicit_unit": False,
    },
    "lipase": {
        "category": "digestion", "name_de": "Lipase", "name_en": "Lipase",
        "canonical_unit": "U/L", "ref_min": 13, "ref_max": 60,
        "alt_units": {}, "require_explicit_unit": False,
    },
    "amylase": {
        "category": "digestion", "name_de": "Amylase", "name_en": "Amylase",
        "canonical_unit": "U/L", "ref_min": 30, "ref_max": 110,
        "alt_units": {}, "require_explicit_unit": False,
    },
    "tacrolimus": {
        "category": "drug_levels", "name_de": "Tacrolimus (Talspiegel)", "name_en": "Tacrolimus (trough)",
        "canonical_unit": "ng/mL", "ref_min": 5, "ref_max": 15,
        "alt_units": {}, "require_explicit_unit": False,
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

# Max. Länge des optionalen `report_ref`-Freitextfelds (§2.4a der Spec).
LAB_REPORT_REF_MAX_LEN = 500
```

- [ ] **Step 3: Verify the module still imports cleanly**

Run: `python3 -c "from custom_components.health_o_mat import const; assert len(const.LAB_MARKERS) == 29; assert len(const.LAB_CATEGORIES) == 10; print('ok')"`
Expected: `ok` (run from the repo root; if `homeassistant` isn't installed this still works — `const.py` has no HA imports).

- [ ] **Step 4: Commit**

```bash
git add custom_components/health_o_mat/const.py
git commit -m "feat: add lab values catalog data to const.py"
```

---

### Task 2: `logic.py` — marker resolution + unit conversion

**Files:**
- Modify: `custom_components/health_o_mat/logic.py`
- Test: `tests/test_logic.py`

**Interfaces:**
- Consumes: `const.LAB_MARKERS`, `const.LAB_MARKER_ALIASES`, `const.LAB_CATEGORY_OTHER` (Task 1).
- Produces: `effective_lab_markers(custom_markers: Iterable[dict] | None) -> dict[str, dict]`, `resolve_lab_marker(raw_key: Any, custom_markers: Iterable[dict] | None) -> tuple[str, dict] | None`, `convert_lab_value(marker_def: dict, value: float, unit: str | None) -> tuple[float, str]` (raises `ValueError("unsupported_unit")`), `normalize_lab_custom_markers(raw: Any) -> list[dict]`, `_slugify_lab_marker_name(name: str) -> str`. These are consumed by Task 3 (reference resolution), `__init__.py` (Task 7/8/9), `sensor.py` (Task 10), `ws_api.py` (Tasks 13/15/16).

- [ ] **Step 1: Write the failing tests** (append to `tests/test_logic.py`)

```python
def test_req_hom_122_resolve_lab_marker_catalog_key():
    from custom_components.health_o_mat import logic

    resolved = logic.resolve_lab_marker("alt", [])
    assert resolved is not None
    key, marker = resolved
    assert key == "alt"
    assert marker["canonical_unit"] == "U/L"
    assert marker["is_custom"] is False


def test_req_hom_122_resolve_lab_marker_resolves_german_alias():
    from custom_components.health_o_mat import logic

    key, marker = logic.resolve_lab_marker("gpt", [])
    assert key == "alt"
    assert marker["canonical_unit"] == "U/L"


def test_req_hom_122_resolve_lab_marker_alias_is_case_insensitive():
    from custom_components.health_o_mat import logic

    key, _marker = logic.resolve_lab_marker("GPT", [])
    assert key == "alt"


def test_req_hom_122_resolve_lab_marker_unknown_returns_none():
    from custom_components.health_o_mat import logic

    assert logic.resolve_lab_marker("not_a_marker", []) is None


def test_req_hom_122_resolve_lab_marker_custom_key():
    from custom_components.health_o_mat import logic

    custom = [{"key": "vitamin_d", "name": "Vitamin D", "category": "other", "unit": "ng/mL"}]
    key, marker = logic.resolve_lab_marker("vitamin_d", custom)
    assert key == "vitamin_d"
    assert marker["is_custom"] is True
    assert marker["canonical_unit"] == "ng/mL"


def test_req_hom_122_convert_lab_value_same_unit_passes_through():
    from custom_components.health_o_mat import logic

    marker = logic.LAB_MARKERS["alt"]
    value, unit = logic.convert_lab_value(marker, 32.0, "U/L")
    assert value == 32.0
    assert unit == "U/L"


def test_req_hom_122_convert_lab_value_defaults_to_canonical_when_unit_missing():
    from custom_components.health_o_mat import logic

    marker = logic.LAB_MARKERS["alt"]
    value, unit = logic.convert_lab_value(marker, 32.0, None)
    assert value == 32.0
    assert unit == "U/L"


def test_req_hom_122_convert_lab_value_converts_alt_unit_bidirectionally():
    """Creatinine: 1.1 mg/dL and 97.24 µmol/L round-trip to the same canonical value."""
    from custom_components.health_o_mat import logic

    marker = logic.LAB_MARKERS["creatinine"]
    from_mgdl, unit1 = logic.convert_lab_value(marker, 1.1, "mg/dL")
    from_canonical, unit2 = logic.convert_lab_value(marker, from_mgdl, "µmol/L")
    assert unit1 == unit2 == "µmol/L"
    assert from_canonical == from_mgdl  # same unit in -> no change
    assert round(from_mgdl, 2) == 97.24


def test_req_hom_122_convert_lab_value_unit_match_is_case_and_space_insensitive():
    from custom_components.health_o_mat import logic

    marker = logic.LAB_MARKERS["creatinine"]
    value, unit = logic.convert_lab_value(marker, 1.1, "  MG/DL  ")
    assert unit == "µmol/L"
    assert round(value, 2) == 97.24


def test_req_hom_122_convert_lab_value_unsupported_unit_raises():
    from custom_components.health_o_mat import logic

    marker = logic.LAB_MARKERS["alt"]
    import pytest

    with pytest.raises(ValueError, match="unsupported_unit"):
        logic.convert_lab_value(marker, 32.0, "mg/dL")


def test_req_hom_122_convert_lab_value_custom_marker_alt_unit():
    from custom_components.health_o_mat import logic

    custom = [
        {
            "key": "vitamin_d",
            "name": "Vitamin D",
            "category": "other",
            "unit": "ng/mL",
            "alt_unit": {"unit": "nmol/L", "factor_to_canonical": 0.4},
        }
    ]
    _key, marker = logic.resolve_lab_marker("vitamin_d", custom)
    value, unit = logic.convert_lab_value(marker, 100.0, "nmol/L")
    assert unit == "ng/mL"
    assert value == 40.0


def test_req_hom_122_normalize_lab_custom_markers_generates_key_from_name():
    from custom_components.health_o_mat import logic

    result = logic.normalize_lab_custom_markers(
        [{"name": "Vitamin D", "category": "other", "unit": "ng/mL"}]
    )
    assert result[0]["key"] == "vitamin_d"


def test_req_hom_122_normalize_lab_custom_markers_dedupes_key_collisions():
    from custom_components.health_o_mat import logic

    result = logic.normalize_lab_custom_markers(
        [
            {"name": "Vitamin D", "category": "other", "unit": "ng/mL"},
            {"name": "Vitamin D", "category": "other", "unit": "nmol/L"},
        ]
    )
    keys = [item["key"] for item in result]
    assert keys == ["vitamin_d", "vitamin_d_2"]


def test_req_hom_122_normalize_lab_custom_markers_rejects_catalog_key_collision():
    from custom_components.health_o_mat import logic

    # "alt" is a catalog key — a custom marker with that generated key must
    # not shadow it; it gets suffixed instead.
    result = logic.normalize_lab_custom_markers([{"name": "ALT", "category": "other", "unit": "U/L"}])
    assert result[0]["key"] == "alt_2"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_logic.py -k req_hom_122 -v`
Expected: all new tests FAIL with `AttributeError: module 'custom_components.health_o_mat.logic' has no attribute 'resolve_lab_marker'` (or similar).

- [ ] **Step 3: Implement** — append to `custom_components/health_o_mat/logic.py`

First check the existing top-of-file imports in `logic.py` and add `re` and the new const imports if not already present (the file already imports `Any`/`Iterable` from `typing`/`collections.abc` for other functions — reuse those, don't re-import). Add at the end of the file:

```python
# --- Laborwerte: Marker-Auflösung + Einheiten-Konvertierung (REQ-HOM-122) ---

from .const import LAB_CATEGORY_OTHER, LAB_MARKER_ALIASES, LAB_MARKERS  # noqa: E402


def _slugify_lab_marker_name(name: str) -> str:
    """Freitext-Marker-Name -> slug (ASCII, Kleinbuchstaben, Unterstriche).

    Einfache, bewusst nicht-internationalisierte Normalisierung (YAGNI) —
    ausreichend für die Admin-Eingabe eines Custom-Marker-Namens.
    """
    slug = re.sub(r"[^a-z0-9]+", "_", name.strip().lower()).strip("_")
    return slug or "marker"


def _norm_unit(value: Any) -> str:
    """Einheiten-Vergleich case-/whitespace-insensitiv (HA-frei)."""
    return str(value if value is not None else "").strip().lower()


def normalize_lab_custom_markers(raw: Any) -> list[dict]:
    """`entry.options["lab_custom_markers"]` normalisieren (HA-frei, §2.2).

    Jeder Eintrag erhält einen stabilen `key` (slugify aus `name`, bei
    Kollision mit einem Katalog-Key ODER einem bereits vergebenen Custom-Key
    dieses Aufrufs mit `_2`/`_3`/... suffixiert — Reihenfolge bleibt stabil).
    Unbrauchbare Einträge (kein `name`/`unit`) werden übersprungen, kein
    Absturz bei Teil-Murks aus altem Options-Bestand.
    """
    if not isinstance(raw, list):
        return []
    used_keys: set[str] = set(LAB_MARKERS.keys())
    result: list[dict] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        unit = str(item.get("unit") or "").strip()
        if not name or not unit:
            continue
        base_key = str(item.get("key") or "").strip().lower() or _slugify_lab_marker_name(name)
        key = base_key
        suffix = 2
        while key in used_keys:
            key = f"{base_key}_{suffix}"
            suffix += 1
        used_keys.add(key)

        category = str(item.get("category") or LAB_CATEGORY_OTHER).strip() or LAB_CATEGORY_OTHER
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
```

Add `import re` to the top-of-file import block if `logic.py` doesn't already import it (check first — several existing functions use regex-like parsing; if `re` is already imported, skip this).

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_logic.py -k req_hom_122 -v`
Expected: all PASS.

- [ ] **Step 5: Run the full logic test file to check for regressions**

Run: `pytest tests/test_logic.py -q`
Expected: all pass, same count as before plus the new tests.

- [ ] **Step 6: Commit**

```bash
git add custom_components/health_o_mat/logic.py tests/test_logic.py
git commit -m "feat: add lab marker resolution and unit conversion to logic.py"
```

---

### Task 3: `logic.py` — reference range resolution + in-range check

**Files:**
- Modify: `custom_components/health_o_mat/logic.py`
- Test: `tests/test_logic.py`

**Interfaces:**
- Consumes: nothing new (pure dicts in, pure values out).
- Produces: `resolve_lab_reference(marker_key: str, marker_def: dict, ref_overrides: Any) -> tuple[float | None, float | None]`, `lab_marker_in_range(value: float | None, ref_min: float | None, ref_max: float | None) -> bool | None`, `normalize_lab_ref_overrides(raw: Any) -> dict[str, dict]`, `normalize_lab_hidden_categories(raw: Any) -> list[str]`. Consumed by `sensor.py` (Task 10), `binary_sensor.py` (Task 11), `ws_api.py` (Tasks 13/15).

- [ ] **Step 1: Write the failing tests** (append to `tests/test_logic.py`)

```python
def test_req_hom_122_resolve_lab_reference_uses_catalog_default():
    from custom_components.health_o_mat import logic

    marker = logic.LAB_MARKERS["alt"]
    ref_min, ref_max = logic.resolve_lab_reference("alt", marker, {})
    assert (ref_min, ref_max) == (10, 50)


def test_req_hom_122_resolve_lab_reference_applies_override():
    from custom_components.health_o_mat import logic

    marker = logic.LAB_MARKERS["alt"]
    overrides = {"alt": {"ref_min": 5, "ref_max": 45}}
    ref_min, ref_max = logic.resolve_lab_reference("alt", marker, overrides)
    assert (ref_min, ref_max) == (5, 45)


def test_req_hom_122_resolve_lab_reference_partial_override_keeps_other_bound():
    from custom_components.health_o_mat import logic

    marker = logic.LAB_MARKERS["alt"]
    overrides = {"alt": {"ref_min": 5}}
    ref_min, ref_max = logic.resolve_lab_reference("alt", marker, overrides)
    assert (ref_min, ref_max) == (5, 50)


def test_req_hom_122_lab_marker_in_range_within_bounds():
    from custom_components.health_o_mat import logic

    assert logic.lab_marker_in_range(30, 10, 50) is True


def test_req_hom_122_lab_marker_in_range_below_min():
    from custom_components.health_o_mat import logic

    assert logic.lab_marker_in_range(5, 10, 50) is False


def test_req_hom_122_lab_marker_in_range_above_max():
    from custom_components.health_o_mat import logic

    assert logic.lab_marker_in_range(60, 10, 50) is False


def test_req_hom_122_lab_marker_in_range_one_sided_bound():
    from custom_components.health_o_mat import logic

    assert logic.lab_marker_in_range(100, 90, None) is True
    assert logic.lab_marker_in_range(80, 90, None) is False


def test_req_hom_122_lab_marker_in_range_no_reference_is_none():
    from custom_components.health_o_mat import logic

    assert logic.lab_marker_in_range(30, None, None) is None


def test_req_hom_122_lab_marker_in_range_no_value_is_none():
    from custom_components.health_o_mat import logic

    assert logic.lab_marker_in_range(None, 10, 50) is None


def test_req_hom_122_normalize_lab_ref_overrides_drops_unknown_markers():
    from custom_components.health_o_mat import logic

    result = logic.normalize_lab_ref_overrides({"alt": {"ref_min": 5}, "not_a_marker": {"ref_min": 1}})
    assert result == {"alt": {"ref_min": 5}}


def test_req_hom_122_normalize_lab_hidden_categories_drops_unknown_keys():
    from custom_components.health_o_mat import logic

    result = logic.normalize_lab_hidden_categories(["thyroid", "not_a_category"])
    assert result == ["thyroid"]


def test_req_hom_122_normalize_lab_hidden_categories_non_list_is_empty():
    from custom_components.health_o_mat import logic

    assert logic.normalize_lab_hidden_categories(None) == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_logic.py -k "resolve_lab_reference or lab_marker_in_range or normalize_lab_ref_overrides or normalize_lab_hidden_categories" -v`
Expected: FAIL with `AttributeError`.

- [ ] **Step 3: Implement** — append to `custom_components/health_o_mat/logic.py` (after the Task 2 block)

```python
from collections.abc import Mapping as _Mapping  # noqa: E402

from .const import LAB_CATEGORIES as _LAB_CATEGORIES  # noqa: E402


def resolve_lab_reference(
    marker_key: str, marker_def: dict, ref_overrides: Any
) -> tuple[float | None, float | None]:
    """Referenzbereich auflösen: Override (nur Katalog) > Katalog-Default (§2.3).

    Custom-Marker haben keinen Override-Layer (sie sind schon
    personenspezifisch) — ein Override-Dict ohne passenden `marker_key` wirkt
    für sie ohnehin nicht, diese Funktion braucht also keinen Sonderfall.
    """
    override = ref_overrides.get(marker_key) if isinstance(ref_overrides, _Mapping) else None
    if isinstance(override, _Mapping):
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
    known = {category["key"] for category in _LAB_CATEGORIES}
    return [str(item) for item in raw if str(item) in known]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_logic.py -k "resolve_lab_reference or lab_marker_in_range or normalize_lab_ref_overrides or normalize_lab_hidden_categories" -v`
Expected: all PASS.

- [ ] **Step 5: Full regression check**

Run: `pytest tests/test_logic.py -q && ruff check custom_components/health_o_mat/logic.py`
Expected: all pass, `ruff` clean.

- [ ] **Step 6: Commit**

```bash
git add custom_components/health_o_mat/logic.py tests/test_logic.py
git commit -m "feat: add lab reference range resolution to logic.py"
```

---

### Task 4: `store.py` — schema v4→v5 migration + `add_lab_reading`/read methods

**Files:**
- Modify: `custom_components/health_o_mat/store.py`
- Test: `tests/test_store.py`

**Interfaces:**
- Consumes: `const.STORE_SCHEMA_VERSION` (now 5, from Task 1), existing `_find_by_id`, `_last_active`, `_now_iso` helpers in `store.py`.
- Produces: `HealthOMatStore.add_lab_reading(entry_id, ts_iso, marker_key, value, unit, reported_value, reported_unit, report_ref=None, created_ts_iso=None, actor=None, audit_limit=DEFAULT_AUDIT_LIMIT) -> None`, `active_lab_readings(entry_id, marker_key=None) -> list[dict]`, `last_active_lab_reading(entry_id, marker_key) -> dict | None`, migration `_migrate_v4_to_v5(data: dict) -> dict`. Consumed by Task 5 (void/restore/remove_last), `__init__.py` services (Task 8/9), `ws_api.py` (Task 15/16), `exporter.py`/`importer.py` (Task 24/25).

- [ ] **Step 1: Write the failing tests** (append to `tests/test_store.py`, reusing the existing `mock_store_fixture` from the top of the file)

```python
def test_req_hom_122_migrate_v4_to_v5_adds_empty_lab_readings():
    from custom_components.health_o_mat.store import migrate_store_data

    data = {"schema": 4, "entries": {"e1": {"drinks": [], "readings": []}}}
    migrated = migrate_store_data(data)
    assert migrated["entries"]["e1"]["lab_readings"] == []
    assert migrated["schema"] == 5


def test_req_hom_122_migrate_v4_to_v5_is_idempotent():
    from custom_components.health_o_mat.store import migrate_store_data

    data = {"schema": 4, "entries": {"e1": {"drinks": [], "readings": []}}}
    once = migrate_store_data(data)
    twice = migrate_store_data(once)
    assert twice["entries"]["e1"]["lab_readings"] == []


def test_req_hom_122_migrate_v4_to_v5_does_not_overwrite_existing_lab_readings():
    from custom_components.health_o_mat.store import migrate_store_data

    existing = [{"id": "x", "marker_key": "alt", "value": 1}]
    data = {"schema": 4, "entries": {"e1": {"drinks": [], "readings": [], "lab_readings": existing}}}
    migrated = migrate_store_data(data)
    assert migrated["entries"]["e1"]["lab_readings"] == existing


def test_req_hom_122_entry_defaults_include_empty_lab_readings(mock_store_fixture):
    store, _ = mock_store_fixture
    entry = store.entry("e1")
    assert entry["lab_readings"] == []


def test_req_hom_122_add_lab_reading_stores_fields(mock_store_fixture):
    store, _ = mock_store_fixture
    import asyncio

    asyncio.new_event_loop().run_until_complete(
        store.add_lab_reading(
            "e1", "2026-10-31T09:00:00+01:00", "alt", 32.0, "U/L", 32.0, "U/L", report_ref="https://example.com/x"
        )
    )
    readings = store.entry("e1")["lab_readings"]
    assert len(readings) == 1
    reading = readings[0]
    assert reading["marker_key"] == "alt"
    assert reading["value"] == 32.0
    assert reading["unit"] == "U/L"
    assert reading["reported_value"] == 32.0
    assert reading["reported_unit"] == "U/L"
    assert reading["report_ref"] == "https://example.com/x"
    assert reading["voided_at"] is None
    assert "id" in reading and "created_at" in reading


def test_req_hom_122_active_lab_readings_filters_by_marker(mock_store_fixture):
    store, _ = mock_store_fixture
    import asyncio

    loop = asyncio.new_event_loop()
    loop.run_until_complete(store.add_lab_reading("e1", "t1", "alt", 1, "U/L", 1, "U/L"))
    loop.run_until_complete(store.add_lab_reading("e1", "t2", "ast", 2, "U/L", 2, "U/L"))
    assert len(store.active_lab_readings("e1")) == 2
    assert len(store.active_lab_readings("e1", marker_key="alt")) == 1
    assert store.active_lab_readings("e1", marker_key="alt")[0]["marker_key"] == "alt"


def test_req_hom_122_last_active_lab_reading_returns_latest_for_marker(mock_store_fixture):
    store, _ = mock_store_fixture
    import asyncio

    loop = asyncio.new_event_loop()
    loop.run_until_complete(store.add_lab_reading("e1", "t1", "alt", 1, "U/L", 1, "U/L"))
    loop.run_until_complete(store.add_lab_reading("e1", "t2", "alt", 2, "U/L", 2, "U/L"))
    last = store.last_active_lab_reading("e1", "alt")
    assert last["value"] == 2


def test_req_hom_122_last_active_lab_reading_none_when_no_reading(mock_store_fixture):
    store, _ = mock_store_fixture
    assert store.last_active_lab_reading("e1", "alt") is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_store.py -k req_hom_122 -v`
Expected: FAIL (`AttributeError: 'HealthOMatStore' object has no attribute 'add_lab_reading'` / missing key errors).

- [ ] **Step 3: Implement** — edit `custom_components/health_o_mat/store.py`

Update the module docstring's schema list (after the existing `- v4: ...` line):

```python
- v5: + `lab_readings` je Person (Laborwerte, REQ-HOM-122)
```

Add the migration function next to `_migrate_v3_to_v4` (before the `_MIGRATIONS` dict):

```python
def _migrate_v4_to_v5(data: dict) -> dict:
    """v4 → v5: `lab_readings`-Liste je Person ergänzen (idempotent)."""
    for entry in data.get("entries", {}).values():
        if isinstance(entry, dict):
            entry.setdefault("lab_readings", [])
    return data
```

Update `_MIGRATIONS`:

```python
_MIGRATIONS: dict[int, Callable[[dict], dict]] = {
    1: _migrate_v1_to_v2,
    2: _migrate_v2_to_v3,
    3: _migrate_v3_to_v4,
    4: _migrate_v4_to_v5,
}
```

Update `HealthOMatStore.entry()`'s default dict (add `"lab_readings": []` alongside the existing keys):

```python
    def entry(self, entry_id: str) -> dict:
        return self._data["entries"].setdefault(
            entry_id,
            {
                "person": "",
                "drinks": [],
                "readings": [],
                "total_ml_lifetime": 0,
                "inputs": {},
                "archived_counts": {"drinks": 0, "readings": 0},
                "wellbeing_entries": [],
                "audit_log": [],
                "lab_readings": [],
            },
        )
```

Add the new methods after `restore_reading` (same section, before `set_person`):

```python
    # ------------------------------------------------------------------
    # Laborwerte (REQ-HOM-122)
    # ------------------------------------------------------------------
    async def add_lab_reading(
        self,
        entry_id: str,
        ts_iso: str,
        marker_key: str,
        value: float,
        unit: str,
        reported_value: float,
        reported_unit: str,
        report_ref: str | None = None,
        created_ts_iso: str | None = None,
        actor: str | None = None,
        audit_limit: int = DEFAULT_AUDIT_LIMIT,
    ) -> None:
        reading: dict = {
            "id": str(uuid.uuid4()),
            "ts": ts_iso,
            "marker_key": marker_key,
            "value": float(value),
            "unit": unit,
            "reported_value": float(reported_value),
            "reported_unit": reported_unit,
            "report_ref": report_ref,
            "created_at": created_ts_iso or _now_iso(),
            "voided_at": None,
            "voided_by": None,
            "void_reason": None,
        }
        self.entry(entry_id).setdefault("lab_readings", []).append(reading)
        self._append_audit(
            entry_id,
            "lab_value_added",
            "lab_readings",
            reading["id"],
            actor,
            {"marker_key": marker_key},
            audit_limit,
        )
        await self._async_save()

    def active_lab_readings(self, entry_id: str, marker_key: str | None = None) -> list[dict]:
        """Nur nicht-gelöschte Laborwerte, optional auf einen Marker gefiltert."""
        items = self.entry(entry_id).get("lab_readings", [])
        return [
            item
            for item in items
            if isinstance(item, dict)
            and not item.get("voided_at")
            and (marker_key is None or item.get("marker_key") == marker_key)
        ]

    def last_active_lab_reading(self, entry_id: str, marker_key: str) -> dict | None:
        """Letzter aktiver Wert EINES Markers (None = keiner erfasst)."""
        items = self.entry(entry_id).get("lab_readings", [])
        if not isinstance(items, list):
            return None
        for item in reversed(items):
            if (
                isinstance(item, dict)
                and item.get("marker_key") == marker_key
                and not item.get("voided_at")
            ):
                return item
        return None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_store.py -k req_hom_122 -v`
Expected: all PASS.

- [ ] **Step 5: Full regression check**

Run: `pytest tests/test_store.py -q && ruff check custom_components/health_o_mat/store.py`
Expected: all pass (existing store tests unaffected — `lab_readings` is additive), `ruff` clean.

- [ ] **Step 6: Commit**

```bash
git add custom_components/health_o_mat/store.py tests/test_store.py
git commit -m "feat: add lab_readings store schema v5 migration and writes"
```

---

### Task 5: `store.py` — void/restore/remove_last for lab readings

**Files:**
- Modify: `custom_components/health_o_mat/store.py`
- Test: `tests/test_store.py`

**Interfaces:**
- Consumes: `_find_by_id`, `self._append_audit`, `self._async_save` (existing private helpers, Task 4's `add_lab_reading`/`last_active_lab_reading`).
- Produces: `HealthOMatStore.void_lab_reading(entry_id, reading_id, actor=None, reason=None, audit_limit=DEFAULT_AUDIT_LIMIT) -> bool`, `restore_lab_reading(entry_id, reading_id, actor=None, audit_limit=DEFAULT_AUDIT_LIMIT) -> bool`, `remove_last_lab_reading(entry_id, marker_key, actor=None, audit_limit=DEFAULT_AUDIT_LIMIT) -> bool`. Consumed by `__init__.py` (Task 9, `remove_last_lab_value` service).

- [ ] **Step 1: Write the failing tests** (append to `tests/test_store.py`)

```python
def test_req_hom_122_void_lab_reading_marks_voided(mock_store_fixture):
    store, _ = mock_store_fixture
    import asyncio

    loop = asyncio.new_event_loop()
    loop.run_until_complete(store.add_lab_reading("e1", "t1", "alt", 1, "U/L", 1, "U/L"))
    reading_id = store.entry("e1")["lab_readings"][0]["id"]
    changed = loop.run_until_complete(store.void_lab_reading("e1", reading_id, reason="typo"))
    assert changed is True
    reading = store.entry("e1")["lab_readings"][0]
    assert reading["voided_at"] is not None
    assert reading["void_reason"] == "typo"
    assert store.active_lab_readings("e1") == []


def test_req_hom_122_void_lab_reading_unknown_id_returns_false(mock_store_fixture):
    store, _ = mock_store_fixture
    import asyncio

    changed = asyncio.new_event_loop().run_until_complete(store.void_lab_reading("e1", "nope"))
    assert changed is False


def test_req_hom_122_restore_lab_reading_clears_void_fields(mock_store_fixture):
    store, _ = mock_store_fixture
    import asyncio

    loop = asyncio.new_event_loop()
    loop.run_until_complete(store.add_lab_reading("e1", "t1", "alt", 1, "U/L", 1, "U/L"))
    reading_id = store.entry("e1")["lab_readings"][0]["id"]
    loop.run_until_complete(store.void_lab_reading("e1", reading_id))
    changed = loop.run_until_complete(store.restore_lab_reading("e1", reading_id))
    assert changed is True
    assert store.entry("e1")["lab_readings"][0]["voided_at"] is None


def test_req_hom_122_remove_last_lab_reading_voids_only_matching_marker(mock_store_fixture):
    store, _ = mock_store_fixture
    import asyncio

    loop = asyncio.new_event_loop()
    loop.run_until_complete(store.add_lab_reading("e1", "t1", "alt", 1, "U/L", 1, "U/L"))
    loop.run_until_complete(store.add_lab_reading("e1", "t2", "ast", 2, "U/L", 2, "U/L"))
    changed = loop.run_until_complete(store.remove_last_lab_reading("e1", "alt"))
    assert changed is True
    assert store.active_lab_readings("e1", marker_key="alt") == []
    assert len(store.active_lab_readings("e1", marker_key="ast")) == 1


def test_req_hom_122_remove_last_lab_reading_no_active_reading_returns_false(mock_store_fixture):
    store, _ = mock_store_fixture
    import asyncio

    changed = asyncio.new_event_loop().run_until_complete(store.remove_last_lab_reading("e1", "alt"))
    assert changed is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_store.py -k "void_lab_reading or restore_lab_reading or remove_last_lab_reading" -v`
Expected: FAIL with `AttributeError`.

- [ ] **Step 3: Implement** — add to `custom_components/health_o_mat/store.py`, directly after the methods added in Task 4

```python
    async def void_lab_reading(
        self,
        entry_id: str,
        reading_id: str,
        actor: str | None = None,
        reason: str | None = None,
        audit_limit: int = DEFAULT_AUDIT_LIMIT,
    ) -> bool:
        """Laborwert als gelöscht markieren (kein Hard-Delete)."""
        e = self.entry(entry_id)
        reading = _find_by_id(e.get("lab_readings"), reading_id)
        if reading is None or reading.get("voided_at"):
            return False
        reading["voided_at"] = _now_iso()
        reading["voided_by"] = actor
        reading["void_reason"] = reason
        self._append_audit(
            entry_id,
            "entry_voided",
            "lab_readings",
            reading_id,
            actor,
            {"reason": reason} if reason else {},
            audit_limit,
        )
        await self._async_save()
        return True

    async def restore_lab_reading(
        self,
        entry_id: str,
        reading_id: str,
        actor: str | None = None,
        audit_limit: int = DEFAULT_AUDIT_LIMIT,
    ) -> bool:
        """Gelöschten Laborwert wiederherstellen."""
        e = self.entry(entry_id)
        reading = _find_by_id(e.get("lab_readings"), reading_id)
        if reading is None or not reading.get("voided_at"):
            return False
        reading["voided_at"] = None
        reading["voided_by"] = None
        reading["void_reason"] = None
        self._append_audit(
            entry_id, "entry_restored", "lab_readings", reading_id, actor, {}, audit_limit
        )
        await self._async_save()
        return True

    async def remove_last_lab_reading(
        self,
        entry_id: str,
        marker_key: str,
        actor: str | None = None,
        audit_limit: int = DEFAULT_AUDIT_LIMIT,
    ) -> bool:
        """Undo: letzten AKTIVEN Wert EINES Markers voiden (kein Pop, §5.2)."""
        reading = self.last_active_lab_reading(entry_id, marker_key)
        if reading is None:
            return False
        return await self.void_lab_reading(
            entry_id, reading.get("id"), actor=actor, audit_limit=audit_limit
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_store.py -k "void_lab_reading or restore_lab_reading or remove_last_lab_reading" -v`
Expected: all PASS.

- [ ] **Step 5: Full regression check**

Run: `pytest tests/test_store.py -q && ruff check custom_components/health_o_mat/store.py && ruff format --check custom_components/health_o_mat/store.py`
Expected: all pass, `ruff` clean.

- [ ] **Step 6: Commit**

```bash
git add custom_components/health_o_mat/store.py tests/test_store.py
git commit -m "feat: add void/restore/remove_last for lab readings"
```

---

## Wave 2 — Services

### Task 6: `areas.py` — `AREA_LABS` wiring

**Files:**
- Modify: `custom_components/health_o_mat/areas.py`
- Test: `tests/test_areas.py`

**Interfaces:**
- Produces: `AREA_LABS = "labs"` added to `AREAS` tuple and `DEFAULT_AREAS` dict. Consumed by `sensor.py`/`binary_sensor.py` (Tasks 10/11), `ws_api.py` (Task 15), panel JS (Task 18/19).

- [ ] **Step 1: Write the failing test** (append to `tests/test_areas.py`)

```python
def test_req_hom_122_lab_area_defaults_active():
    from custom_components.health_o_mat import areas

    assert areas.active_areas(None)[areas.AREA_LABS] is True


def test_req_hom_122_lab_area_can_be_disabled():
    from custom_components.health_o_mat import areas

    assert areas.active_areas({"areas": {"labs": False}})[areas.AREA_LABS] is False


def test_req_hom_122_lab_area_missing_subkey_stays_active():
    from custom_components.health_o_mat import areas

    # Existing options written before this feature never mention "labs" —
    # a missing sub-key must mean "active" (REQ-HOM-009 migration semantics).
    assert areas.active_areas({"areas": {"drink": False}})[areas.AREA_LABS] is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_areas.py -k req_hom_122 -v`
Expected: FAIL with `AttributeError: module '...areas' has no attribute 'AREA_LABS'`.

- [ ] **Step 3: Implement** — edit `custom_components/health_o_mat/areas.py`

```python
AREA_DRINK = "drink"
AREA_BP = "bp"
AREA_WELLBEING = "wellbeing"
AREA_LABS = "labs"

AREAS: tuple[str, ...] = (AREA_DRINK, AREA_BP, AREA_WELLBEING, AREA_LABS)
OPTION_AREAS = "areas"

DEFAULT_AREAS: dict[str, bool] = {
    AREA_DRINK: True,
    AREA_BP: True,
    AREA_WELLBEING: True,
    AREA_LABS: True,
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_areas.py -q`
Expected: all pass (existing + 3 new).

- [ ] **Step 5: Commit**

```bash
git add custom_components/health_o_mat/areas.py tests/test_areas.py
git commit -m "feat: add labs area toggle"
```

---

### Task 7: `services.yaml` + `strings.json`/translations — service metadata

**Files:**
- Modify: `custom_components/health_o_mat/services.yaml`, `custom_components/health_o_mat/strings.json`, `custom_components/health_o_mat/translations/de.json`, `custom_components/health_o_mat/translations/en.json`
- Test: `tests/test_translations.py`

**Interfaces:**
- Produces: service metadata for `add_lab_value`/`remove_last_lab_value` (name/description/field docs + selector), consumed by the HA UI service picker and the service handlers registered in Task 8/9 (field names must match exactly: `person`, `marker`, `value`, `unit`, `ts`, `report_ref` for `add_lab_value`; `person`, `marker` for `remove_last_lab_value`).

- [ ] **Step 1: Write the failing test** (append to `tests/test_translations.py` — check the file first for the exact parity-check helper name/shape used by existing tests, e.g. a function that diffs `strings.json["services"]` keys against `services.yaml` keys; reuse it instead of writing a new one)

```python
def test_req_hom_122_lab_services_have_translation_parity():
    """add_lab_value/remove_last_lab_value must exist in services.yaml AND strings.json."""
    import json
    from pathlib import Path

    base = Path(__file__).parent.parent / "custom_components" / "health_o_mat"
    import yaml  # already a test dependency per existing translation tests — reuse it

    services_yaml = yaml.safe_load((base / "services.yaml").read_text(encoding="utf-8"))
    strings = json.loads((base / "strings.json").read_text(encoding="utf-8"))
    de = json.loads((base / "translations" / "de.json").read_text(encoding="utf-8"))
    en = json.loads((base / "translations" / "en.json").read_text(encoding="utf-8"))

    for service in ("add_lab_value", "remove_last_lab_value"):
        assert service in services_yaml
        assert service in strings.get("services", {})
        assert service in de.get("services", {})
        assert service in en.get("services", {})
```

(If `tests/test_translations.py` already imports `yaml` differently or has its own JSON-loading helper, follow that file's existing style instead of the `yaml.safe_load` shown here — check the top of the file before writing this step for real.)

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_translations.py -k req_hom_122 -v`
Expected: FAIL (`add_lab_value` missing from `services.yaml`).

- [ ] **Step 3: Implement** — append to `custom_components/health_o_mat/services.yaml` (after `weekly_report`, matching the existing field/selector style exactly)

```yaml
add_lab_value:
  name: Laborwert erfassen
  description: Speichert einen Laborwert (Katalog- oder eigener Marker) für eine Person.
  fields:
    person:
      name: Person
      description: Name der Person (leer = einzige konfigurierte Person).
      example: "Caro"
    marker:
      name: Marker
      description: >-
        Stabiler Marker-Schlüssel (z. B. alt, creatinine, crp) oder ein eigener
        Marker-Key aus dem Admin-Panel. Deutsche Laborsynonyme (gpt, got,
        gamma_gt) werden automatisch aufgelöst.
      example: "alt"
      selector:
        select:
          custom_value: true
          options:
            - label: ALT (GPT)
              value: "alt"
            - label: AST (GOT)
              value: "ast"
            - label: GGT (Gamma-GT)
              value: "ggt"
            - label: Bilirubin gesamt
              value: "bilirubin_total"
            - label: Gesamteiweiß
              value: "total_protein"
            - label: Kreatinin
              value: "creatinine"
            - label: eGFR
              value: "egfr"
            - label: Harnstoff
              value: "urea"
            - label: Protein/Kreatinin-Quotient (Urin)
              value: "urine_protein_creatinine_ratio"
            - label: Natrium
              value: "sodium"
            - label: Kalium
              value: "potassium"
            - label: Calcium gesamt
              value: "calcium"
            - label: Magnesium
              value: "magnesium"
            - label: Chlorid
              value: "chloride"
            - label: Gesamtcholesterin
              value: "cholesterol_total"
            - label: LDL
              value: "ldl"
            - label: HDL
              value: "hdl"
            - label: Triglyceride
              value: "triglycerides"
            - label: TSH
              value: "tsh"
            - label: fT4
              value: "ft4"
            - label: fT3
              value: "ft3"
            - label: Hämoglobin
              value: "hemoglobin"
            - label: Leukozyten
              value: "leukocytes"
            - label: Thrombozyten
              value: "platelets"
            - label: CRP
              value: "crp"
            - label: BSG
              value: "esr"
            - label: Lipase
              value: "lipase"
            - label: Amylase
              value: "amylase"
            - label: Tacrolimus (Talspiegel)
              value: "tacrolimus"
    value:
      name: Wert
      description: Messwert in der angegebenen (oder Standard-)Einheit.
      example: 32.0
      required: true
    unit:
      name: Einheit
      description: >-
        Einheit des Werts (optional, Default = kanonische Einheit des
        Markers). Für Marker mit Verwechslungsgefahr (z. B. das
        Protein/Kreatinin-Quotient) ist dieses Feld Pflicht.
      example: "U/L"
    ts:
      name: Zeitpunkt
      description: >-
        Zeitpunkt der Erfassung als ISO 8601 (z. B. 2026-10-24T18:30 oder mit
        Offset). Leer = jetzt. Höchstens 5 Minuten in der Zukunft, nicht vor 1900.
      example: "2026-10-24T18:30:00+02:00"
    report_ref:
      name: Berichts-Referenz
      description: >-
        Optionaler Link oder externe ID des Laborberichts (max. 500 Zeichen).
        Nur Referenz, Health-O-Mat ruft die URL nie selbst auf.
      example: "https://example.com/laborbericht/123"

remove_last_lab_value:
  name: Letzten Laborwert löschen
  description: >-
    Entfernt den letzten aktiven Laborwert eines bestimmten Markers (Undo).
    Der Eintrag wird als gelöscht markiert und bleibt wiederherstellbar.
  fields:
    person:
      name: Person
      description: Name der Person (leer = einzige konfigurierte Person).
    marker:
      name: Marker
      description: Stabiler Marker-Schlüssel, dessen letzter Wert entfernt wird.
      example: "alt"
      required: true
```

- [ ] **Step 4: Add English strings** — in `custom_components/health_o_mat/strings.json`, under the `"services"` key (follow the existing `add_blood_pressure` entry's shape — only fields that need translation, same minimal-override convention already used):

```json
"add_lab_value": {
  "name": "Record lab value",
  "description": "Stores a lab value (catalog or custom marker) for a person.",
  "fields": {
    "marker": {
      "name": "Marker",
      "description": "Stable marker key (e.g. alt, creatinine, crp) or a custom marker key from the admin panel. German lab synonyms (gpt, got, gamma_gt) are resolved automatically."
    },
    "unit": {
      "name": "Unit",
      "description": "Unit of the value (optional, defaults to the marker's canonical unit). Required for markers with a known mix-up risk (e.g. the urine protein/creatinine ratio)."
    },
    "ts": {
      "name": "Timestamp",
      "description": "Time of the entry (ISO 8601, e.g. 2026-10-24T18:30 or with offset). Empty = now. At most 5 minutes in the future, not before 1900."
    },
    "report_ref": {
      "name": "Report reference",
      "description": "Optional link or external ID of the lab report (max 500 characters). Reference only, Health-O-Mat never fetches the URL itself."
    }
  }
},
"remove_last_lab_value": {
  "name": "Remove last lab value",
  "description": "Removes the last active lab value of a given marker (undo). The entry is marked deleted and stays restorable.",
  "fields": {
    "marker": {
      "name": "Marker",
      "description": "Stable marker key whose last value is removed."
    }
  }
}
```

Mirror the exact same two blocks (German text for the German translation) into `custom_components/health_o_mat/translations/de.json` (reuse the German text already written in `services.yaml` above) and the English blocks above into `custom_components/health_o_mat/translations/en.json`, under each file's `"services"` key — follow the file's existing structure precisely (check how `add_blood_pressure` is mirrored across all three files first, then copy that shape).

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_translations.py -q`
Expected: all pass, including the new `req_hom_122` test.

- [ ] **Step 6: Commit**

```bash
git add custom_components/health_o_mat/services.yaml custom_components/health_o_mat/strings.json custom_components/health_o_mat/translations/de.json custom_components/health_o_mat/translations/en.json tests/test_translations.py
git commit -m "feat: add add_lab_value and remove_last_lab_value service metadata"
```

---

### Task 8: `__init__.py` — `add_lab_value` service handler

**Files:**
- Modify: `custom_components/health_o_mat/__init__.py`
- Test: `tests/test_wave_a.py` (or a new `tests/test_lab_services.py` if `test_wave_a.py`'s `_load_init()` helper is specific to its own suite — check first; reuse the existing `_load_init` pattern seen in `tests/test_binary_sensor.py`)

**Interfaces:**
- Consumes: `logic.resolve_lab_marker`, `logic.convert_lab_value` (Task 2), `logic.normalize_lab_custom_markers` (Task 2), `store.add_lab_reading` (Task 4), `const.OPTION_LAB_CUSTOM_MARKERS`, `const.LAB_REPORT_REF_MAX_LEN` (Task 1), existing `get_runtime_data`, `_service_actor`, `_service_entry_ts`, `_entry_audit_limit`, `signal_refresh`.
- Produces: registered service `health_o_mat.add_lab_value`; new helper `_entry_options(hass, entry_id) -> Mapping[str, Any]` (consumed again by Task 9).

- [ ] **Step 1: Write the failing tests** — create `tests/test_lab_services.py` following the exact fake-package-loading pattern from `tests/test_binary_sensor.py` (the `_load`/`_load_init`/`_run` helpers), reusing `_load_init()` to load `__init__.py` with fakes for `store`, `entity`, `const`, `parser`, `logic`, `exporter`, `areas`.

```python
"""Tests: add_lab_value / remove_last_lab_value service handlers (REQ-HOM-122)."""

import asyncio
import importlib.util
import os
import sys
import types
from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.exceptions import ServiceValidationError

_COMPONENT_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "custom_components", "health_o_mat")
)
_PKG = "_hom_lab_test_pkg"
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


def _load_init():
    for name in ("store", "entity", "const", "parser", "logic", "exporter", "areas"):
        _load(name)
    spec = importlib.util.spec_from_file_location(
        f"{_PKG}.init", os.path.join(_COMPONENT_DIR, "__init__.py")
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[f"{_PKG}.init"] = module
    spec.loader.exec_module(module)
    return module


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _make_call(data):
    call = MagicMock()
    call.data = data
    call.context = MagicMock()
    call.context.user_id = None
    return call


def _wire_services(hass, store, entry_id="e1", options=None):
    hass.data = {
        hass_init.DOMAIN: {
            "shared": {"store": store},
            entry_id: {"coordinator": MagicMock(), "store": store, "data": MagicMock()},
        }
    }
    entry = MagicMock()
    entry.entry_id = entry_id
    entry.data = {"person": "caro"}
    entry.options = options or {}
    hass.config_entries = MagicMock()
    hass.config_entries.async_entries.return_value = [entry]
    hass.config_entries.async_get_entry.return_value = entry
    registered = {}

    def _register(domain, name, schema=None, service_func=None):
        registered[name] = service_func

    hass.services = MagicMock()
    hass.services.has_service.return_value = False
    hass.services.async_register.side_effect = _register
    hass_init._register_services(hass)
    return registered


hass_init = _load_init()


def test_req_hom_122_add_lab_value_converts_unit_and_stores_reported_value():
    store = MagicMock()
    store.add_lab_reading = AsyncMock()
    hass = MagicMock()
    registered = _wire_services(hass, store)
    call = _make_call({"marker": "creatinine", "value": 1.1, "unit": "mg/dL"})

    _run(registered["add_lab_value"](call))

    store.add_lab_reading.assert_awaited_once()
    args, kwargs = store.add_lab_reading.call_args
    assert args[2] == "creatinine"  # marker_key
    assert round(args[3], 2) == 97.24  # canonical value (µmol/L)
    assert args[4] == "µmol/L"
    assert args[5] == 1.1  # reported_value
    assert args[6] == "mg/dL"  # reported_unit


def test_req_hom_122_add_lab_value_resolves_german_alias():
    store = MagicMock()
    store.add_lab_reading = AsyncMock()
    hass = MagicMock()
    registered = _wire_services(hass, store)
    call = _make_call({"marker": "gpt", "value": 32.0})

    _run(registered["add_lab_value"](call))

    args, _kwargs = store.add_lab_reading.call_args
    assert args[2] == "alt"


def test_req_hom_122_add_lab_value_unknown_marker_raises():
    store = MagicMock()
    hass = MagicMock()
    registered = _wire_services(hass, store)
    call = _make_call({"marker": "not_a_marker", "value": 1})

    with pytest.raises(ServiceValidationError, match="unknown_marker"):
        _run(registered["add_lab_value"](call))


def test_req_hom_122_add_lab_value_missing_unit_required_marker_raises():
    store = MagicMock()
    hass = MagicMock()
    registered = _wire_services(hass, store)
    call = _make_call({"marker": "urine_protein_creatinine_ratio", "value": 10})

    with pytest.raises(ServiceValidationError, match="unit_required"):
        _run(registered["add_lab_value"](call))


def test_req_hom_122_add_lab_value_unsupported_unit_raises():
    store = MagicMock()
    hass = MagicMock()
    registered = _wire_services(hass, store)
    call = _make_call({"marker": "alt", "value": 32.0, "unit": "mg/dL"})

    with pytest.raises(ServiceValidationError, match="unsupported_unit"):
        _run(registered["add_lab_value"](call))


def test_req_hom_122_add_lab_value_resolves_custom_marker():
    store = MagicMock()
    store.add_lab_reading = AsyncMock()
    hass = MagicMock()
    options = {
        "lab_custom_markers": [
            {"key": "vitamin_d", "name": "Vitamin D", "category": "other", "unit": "ng/mL"}
        ]
    }
    registered = _wire_services(hass, store, options=options)
    call = _make_call({"marker": "vitamin_d", "value": 42.0})

    _run(registered["add_lab_value"](call))

    args, _kwargs = store.add_lab_reading.call_args
    assert args[2] == "vitamin_d"
    assert args[4] == "ng/mL"


def test_req_hom_122_add_lab_value_caps_report_ref_length():
    store = MagicMock()
    store.add_lab_reading = AsyncMock()
    hass = MagicMock()
    registered = _wire_services(hass, store)
    long_ref = "x" * 600
    call = _make_call({"marker": "alt", "value": 32.0, "report_ref": long_ref})

    _run(registered["add_lab_value"](call))

    _args, kwargs = store.add_lab_reading.call_args
    report_ref = kwargs.get("report_ref")
    assert report_ref is not None
    assert len(report_ref) == 500
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_lab_services.py -v`
Expected: FAIL — `"add_lab_value" not in registered` / `KeyError`.

- [ ] **Step 3: Implement** — edit `custom_components/health_o_mat/__init__.py`

Add the new const imports to the existing `from .const import (...)` block:

```python
from .const import (
    DEFAULT_DAILY_GOAL_ML,
    DEFAULT_DIA_THRESHOLD,
    DEFAULT_QUICK_DRINKS,
    DEFAULT_SYS_THRESHOLD,
    DOMAIN,
    LAB_REPORT_REF_MAX_LEN,
    OPTION_LAB_CUSTOM_MARKERS,
    OPTION_WEEKLY_REPORT,
    WELLBEING_STATES,
)
```

Add the two new names to `_SERVICE_NAMES`:

```python
_SERVICE_NAMES = (
    "add_drink",
    "add_blood_pressure",
    "remove_last_entry",
    "void_entry",
    "restore_entry",
    "export_csv",
    "import_csv",
    "backup",
    "restore_backup",
    "set_wellbeing",
    "weekly_report",
    "add_lab_value",
    "remove_last_lab_value",
)
```

Add the `_entry_options` helper next to `_entry_audit_limit`:

```python
def _entry_options(hass: HomeAssistant, entry_id: str) -> dict:
    """`entry.options` eines Entries (leeres Dict bei unbekannter ID)."""
    try:
        entry = hass.config_entries.async_get_entry(entry_id)
    except Exception:  # noqa: BLE001 - Options-Lesen ist nie service-kritisch
        entry = None
    return dict(getattr(entry, "options", None) or {})
```

Inside `_register_services`, add the `add_lab_value` handler next to `add_blood_pressure` (before `set_wellbeing`):

```python
    async def add_lab_value(call: ServiceCall) -> None:
        """Laborwert erfassen (Katalog- oder Custom-Marker, REQ-HOM-122)."""
        entry_id, _info = get_runtime_data(hass, call)
        options = _entry_options(hass, entry_id)
        custom_markers = options.get(OPTION_LAB_CUSTOM_MARKERS)
        resolved = logic.resolve_lab_marker(call.data["marker"], custom_markers)
        if resolved is None:
            raise ServiceValidationError("unknown_marker")
        marker_key, marker_def = resolved
        raw_unit = call.data.get("unit")
        if raw_unit is None and marker_def.get("require_explicit_unit"):
            raise ServiceValidationError("unit_required")
        value = float(call.data["value"])
        try:
            canonical_value, canonical_unit = logic.convert_lab_value(marker_def, value, raw_unit)
        except ValueError as err:
            raise ServiceValidationError(str(err)) from err
        report_ref = (call.data.get("report_ref") or "").strip()[:LAB_REPORT_REF_MAX_LEN] or None
        now = dt_util.now()
        ts_iso = _service_entry_ts(call, now) or now.isoformat()
        store: HealthOMatStore = hass.data[DOMAIN]["shared"]["store"]
        await store.add_lab_reading(
            entry_id,
            ts_iso,
            marker_key,
            canonical_value,
            canonical_unit,
            value,
            raw_unit or canonical_unit,
            report_ref=report_ref,
            created_ts_iso=now.isoformat(),
            actor=_service_actor(call),
            audit_limit=_entry_audit_limit(hass, entry_id),
        )
        signal_refresh(hass, entry_id)
```

Add the schema registration next to `add_blood_pressure`'s registration block (near the bottom of `_register_services`, before `set_wellbeing`'s registration):

```python
    hass.services.async_register(
        DOMAIN,
        "add_lab_value",
        schema=vol.Schema(
            {
                vol.Required("marker"): str,
                vol.Required("value"): vol.Coerce(float),
                vol.Optional("unit"): str,
                vol.Optional("person"): str,
                vol.Optional("ts"): str,
                vol.Optional("report_ref"): str,
            }
        ),
        service_func=add_lab_value,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_lab_services.py -v`
Expected: all PASS.

- [ ] **Step 5: Full regression check**

Run: `pytest tests/ -q && ruff check custom_components/health_o_mat/__init__.py`
Expected: all pass, `ruff` clean.

- [ ] **Step 6: Commit**

```bash
git add custom_components/health_o_mat/__init__.py tests/test_lab_services.py
git commit -m "feat: add add_lab_value service handler"
```

---

### Task 9: `__init__.py` — `remove_last_lab_value` service handler

**Files:**
- Modify: `custom_components/health_o_mat/__init__.py`
- Test: `tests/test_lab_services.py`

**Interfaces:**
- Consumes: `logic.resolve_lab_marker` (Task 2), `store.remove_last_lab_reading` (Task 5), `_entry_options` (Task 8).
- Produces: registered service `health_o_mat.remove_last_lab_value`.

- [ ] **Step 1: Write the failing tests** (append to `tests/test_lab_services.py`)

```python
def test_req_hom_122_remove_last_lab_value_calls_store():
    store = MagicMock()
    store.remove_last_lab_reading = AsyncMock(return_value=True)
    hass = MagicMock()
    registered = _wire_services(hass, store)
    call = _make_call({"marker": "alt"})

    _run(registered["remove_last_lab_value"](call))

    store.remove_last_lab_reading.assert_awaited_once()
    args, _kwargs = store.remove_last_lab_reading.call_args
    assert args[1] == "alt"


def test_req_hom_122_remove_last_lab_value_resolves_alias():
    store = MagicMock()
    store.remove_last_lab_reading = AsyncMock(return_value=True)
    hass = MagicMock()
    registered = _wire_services(hass, store)
    call = _make_call({"marker": "gpt"})

    _run(registered["remove_last_lab_value"](call))

    args, _kwargs = store.remove_last_lab_reading.call_args
    assert args[1] == "alt"


def test_req_hom_122_remove_last_lab_value_unknown_marker_raises():
    store = MagicMock()
    hass = MagicMock()
    registered = _wire_services(hass, store)
    call = _make_call({"marker": "not_a_marker"})

    with pytest.raises(ServiceValidationError, match="unknown_marker"):
        _run(registered["remove_last_lab_value"](call))


def test_req_hom_122_remove_last_lab_value_no_active_value_raises():
    store = MagicMock()
    store.remove_last_lab_reading = AsyncMock(return_value=False)
    hass = MagicMock()
    registered = _wire_services(hass, store)
    call = _make_call({"marker": "alt"})

    with pytest.raises(ServiceValidationError):
        _run(registered["remove_last_lab_value"](call))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_lab_services.py -k remove_last_lab_value -v`
Expected: FAIL — `"remove_last_lab_value" not in registered`.

- [ ] **Step 3: Implement** — edit `custom_components/health_o_mat/__init__.py`

Add the handler in `_register_services`, next to `remove_last_entry`:

```python
    async def remove_last_lab_value(call: ServiceCall) -> None:
        """Letzten aktiven Laborwert EINES Markers entfernen (Undo, §5.2)."""
        entry_id, _info = get_runtime_data(hass, call)
        store: HealthOMatStore = hass.data[DOMAIN]["shared"]["store"]
        options = _entry_options(hass, entry_id)
        resolved = logic.resolve_lab_marker(
            call.data["marker"], options.get(OPTION_LAB_CUSTOM_MARKERS)
        )
        if resolved is None:
            raise ServiceValidationError("unknown_marker")
        marker_key, _marker_def = resolved
        changed = await store.remove_last_lab_reading(
            entry_id,
            marker_key,
            actor=_service_actor(call),
            audit_limit=_entry_audit_limit(hass, entry_id),
        )
        if not changed:
            raise ServiceValidationError(f"Kein aktiver Wert für Marker '{marker_key}' zum Entfernen")
        signal_refresh(hass, entry_id)
```

Add the schema registration next to `remove_last_entry`'s registration:

```python
    hass.services.async_register(
        DOMAIN,
        "remove_last_lab_value",
        schema=vol.Schema(
            {
                vol.Optional("person"): str,
                vol.Required("marker"): str,
            }
        ),
        service_func=remove_last_lab_value,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_lab_services.py -q`
Expected: all pass.

- [ ] **Step 5: Full regression check**

Run: `pytest tests/ -q && ruff check custom_components/health_o_mat/__init__.py && ruff format --check custom_components/health_o_mat/__init__.py`
Expected: all pass, `ruff` clean.

- [ ] **Step 6: Commit**

```bash
git add custom_components/health_o_mat/__init__.py tests/test_lab_services.py
git commit -m "feat: add remove_last_lab_value service handler"
```

---

## Wave 3 — Entities

### Task 10: `sensor.py` — `LabValueSensor` (one per catalog + custom marker)

**Files:**
- Modify: `custom_components/health_o_mat/sensor.py`
- Test: `tests/test_sensor.py`

**Interfaces:**
- Consumes: `logic.effective_lab_markers`, `logic.resolve_lab_reference`, `logic.lab_marker_in_range` (Tasks 2/3), `store.last_active_lab_reading` (Task 4), `areas.AREA_LABS` (Task 6), `const.OPTION_LAB_CUSTOM_MARKERS`/`OPTION_LAB_REF_OVERRIDES` (Task 1), existing `HealthOMatSensor` base (`__init__(self, coordinator, entry, store, key)`).
- Produces: `LabValueSensor` class; `async_setup_entry` extended to build one sensor per effective marker when `areas.labs` is active. unique_id key = `lab_{marker_key}` (locked in — never change after release).

- [ ] **Step 1: Write the failing tests** (append to `tests/test_sensor.py` — reuse the file's existing `_load`/fake-package pattern already visible at its top, e.g. the helper used for `LastReadingSensor` tests)

```python
def test_req_hom_122_lab_value_sensor_native_value_from_last_reading():
    coordinator = MagicMock()
    entry = MagicMock()
    entry.entry_id = "e1"
    entry.options = {}
    store = MagicMock()
    store.last_active_lab_reading.return_value = {"value": 32.0, "ts": "2026-10-31T09:00:00"}
    marker_def = {
        "category": "liver", "name_de": "ALT (GPT)", "name_en": "ALT",
        "canonical_unit": "U/L", "ref_min": 10, "ref_max": 50,
        "alt_units": {}, "require_explicit_unit": False, "is_custom": False,
    }

    sensor = sensor_module.LabValueSensor(coordinator, entry, store, "alt", marker_def)

    assert sensor.native_value == 32.0
    assert sensor.native_unit_of_measurement == "U/L"
    assert sensor.extra_state_attributes["category"] == "liver"
    assert sensor.extra_state_attributes["in_range"] is True
    assert sensor.extra_state_attributes["ts"] == "2026-10-31T09:00:00"


def test_req_hom_122_lab_value_sensor_unknown_without_reading():
    coordinator = MagicMock()
    entry = MagicMock()
    entry.entry_id = "e1"
    entry.options = {}
    store = MagicMock()
    store.last_active_lab_reading.return_value = None
    marker_def = {
        "category": "liver", "name_de": "ALT (GPT)", "name_en": "ALT",
        "canonical_unit": "U/L", "ref_min": 10, "ref_max": 50,
        "alt_units": {}, "require_explicit_unit": False, "is_custom": False,
    }

    sensor = sensor_module.LabValueSensor(coordinator, entry, store, "alt", marker_def)

    assert sensor.native_value is None
    assert sensor.extra_state_attributes["in_range"] is None


def test_req_hom_122_lab_value_sensor_catalog_marker_uses_translation_key():
    coordinator = MagicMock()
    entry = MagicMock()
    entry.entry_id = "e1"
    entry.options = {}
    store = MagicMock()
    store.last_active_lab_reading.return_value = None
    marker_def = {
        "category": "liver", "name_de": "ALT (GPT)", "name_en": "ALT",
        "canonical_unit": "U/L", "ref_min": 10, "ref_max": 50,
        "alt_units": {}, "require_explicit_unit": False, "is_custom": False,
    }

    sensor = sensor_module.LabValueSensor(coordinator, entry, store, "alt", marker_def)

    assert sensor._attr_translation_key == "lab_alt"


def test_req_hom_122_lab_value_sensor_custom_marker_uses_own_name():
    coordinator = MagicMock()
    entry = MagicMock()
    entry.entry_id = "e1"
    entry.options = {}
    store = MagicMock()
    store.last_active_lab_reading.return_value = None
    marker_def = {
        "category": "other", "name": "Vitamin D", "canonical_unit": "ng/mL",
        "ref_min": 30, "ref_max": 100, "alt_units": {}, "require_explicit_unit": False,
        "is_custom": True,
    }

    sensor = sensor_module.LabValueSensor(coordinator, entry, store, "vitamin_d", marker_def)

    assert sensor._attr_name == "Vitamin D"
    assert getattr(sensor, "_attr_translation_key", None) is None


def test_req_hom_122_lab_value_sensor_applies_ref_override():
    coordinator = MagicMock()
    entry = MagicMock()
    entry.entry_id = "e1"
    entry.options = {"lab_ref_overrides": {"alt": {"ref_min": 5, "ref_max": 45}}}
    store = MagicMock()
    store.last_active_lab_reading.return_value = {"value": 46.0, "ts": "t1"}
    marker_def = {
        "category": "liver", "name_de": "ALT (GPT)", "name_en": "ALT",
        "canonical_unit": "U/L", "ref_min": 10, "ref_max": 50,
        "alt_units": {}, "require_explicit_unit": False, "is_custom": False,
    }

    sensor = sensor_module.LabValueSensor(coordinator, entry, store, "alt", marker_def)

    assert sensor.extra_state_attributes["ref_max"] == 45
    assert sensor.extra_state_attributes["in_range"] is False  # 46 > overridden max 45


def test_req_hom_122_async_setup_entry_creates_one_sensor_per_catalog_marker():
    from custom_components.health_o_mat import const

    hass = MagicMock()
    entry = MagicMock()
    entry.entry_id = "e1"
    entry.options = {}
    store = MagicMock()
    coordinator = MagicMock()
    hass.data = {
        "health_o_mat": {
            "e1": {"coordinator": coordinator},
            "shared": {"store": store},
        }
    }
    added: list = []

    _run(sensor_module.async_setup_entry(hass, entry, lambda ents: added.extend(ents)))

    lab_sensors = [e for e in added if isinstance(e, sensor_module.LabValueSensor)]
    assert len(lab_sensors) == len(const.LAB_MARKERS)


def test_req_hom_122_async_setup_entry_skips_lab_sensors_when_area_disabled():
    hass = MagicMock()
    entry = MagicMock()
    entry.entry_id = "e1"
    entry.options = {"areas": {"labs": False}}
    store = MagicMock()
    coordinator = MagicMock()
    hass.data = {
        "health_o_mat": {
            "e1": {"coordinator": coordinator},
            "shared": {"store": store},
        }
    }
    added: list = []

    _run(sensor_module.async_setup_entry(hass, entry, lambda ents: added.extend(ents)))

    lab_sensors = [e for e in added if isinstance(e, sensor_module.LabValueSensor)]
    assert lab_sensors == []


def test_req_hom_122_async_setup_entry_adds_custom_marker_sensor():
    hass = MagicMock()
    entry = MagicMock()
    entry.entry_id = "e1"
    entry.options = {
        "lab_custom_markers": [
            {"key": "vitamin_d", "name": "Vitamin D", "category": "other", "unit": "ng/mL"}
        ]
    }
    store = MagicMock()
    coordinator = MagicMock()
    hass.data = {
        "health_o_mat": {
            "e1": {"coordinator": coordinator},
            "shared": {"store": store},
        }
    }
    added: list = []

    _run(sensor_module.async_setup_entry(hass, entry, lambda ents: added.extend(ents)))

    custom = [
        e
        for e in added
        if isinstance(e, sensor_module.LabValueSensor) and e._marker_key == "vitamin_d"
    ]
    assert len(custom) == 1
```

Note: `_run` here must be the file's existing async-runner helper (check the top of `tests/test_sensor.py` for one — if it doesn't exist yet, add `def _run(coro): return asyncio.new_event_loop().run_until_complete(coro)` once at the top, matching the pattern from `tests/test_binary_sensor.py`).

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_sensor.py -k req_hom_122 -v`
Expected: FAIL — `AttributeError: module '...sensor_module' has no attribute 'LabValueSensor'`.

- [ ] **Step 3: Implement** — edit `custom_components/health_o_mat/sensor.py`

Add imports (extend the existing `from . import areas, logic` line is already there; add the const import):

```python
from .const import DOMAIN, HISTORY_ATTRIBUTE_LIMIT, OPTION_LAB_CUSTOM_MARKERS, OPTION_LAB_REF_OVERRIDES
```

Extend `async_setup_entry` (add the `labs` block after the existing `wellbeing` block, before `async_add_entities(entities)`):

```python
    if active[areas.AREA_LABS]:
        custom_markers = entry.options.get(OPTION_LAB_CUSTOM_MARKERS)
        for marker_key, marker_def in logic.effective_lab_markers(custom_markers).items():
            entities.append(LabValueSensor(coord, entry, store, marker_key, marker_def))
```

Add the new class at the end of the file:

```python
class LabValueSensor(HealthOMatSensor):
    """Ein Sensor je Laborwert-Marker (Katalog oder Custom, REQ-HOM-122)."""

    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, entry, store, marker_key: str, marker_def: dict) -> None:
        super().__init__(coordinator, entry, store, f"lab_{marker_key}")
        self._marker_key = marker_key
        self._marker_def = marker_def
        self._attr_native_unit_of_measurement = marker_def["canonical_unit"]
        if marker_def.get("is_custom"):
            # Custom-Marker nutzen den nutzervergebenen Namen direkt (§4 der
            # Spec: "bewusst einsprachig") — kein translation_key nötig.
            self._attr_name = marker_def.get("name") or marker_key
        else:
            self._attr_translation_key = f"lab_{marker_key}"

    @property
    def _reading(self) -> dict | None:
        return self._store.last_active_lab_reading(self._entry.entry_id, self._marker_key)

    @property
    def native_value(self):
        reading = self._reading
        return reading.get("value") if reading else None

    @property
    def extra_state_attributes(self) -> dict:
        reading = self._reading
        value = reading.get("value") if reading else None
        ref_overrides = (
            self._entry.options.get(OPTION_LAB_REF_OVERRIDES)
            if not self._marker_def.get("is_custom")
            else None
        )
        ref_min, ref_max = logic.resolve_lab_reference(
            self._marker_key, self._marker_def, ref_overrides
        )
        return {
            "ts": reading.get("ts") if reading else None,
            "category": self._marker_def.get("category"),
            "ref_min": ref_min,
            "ref_max": ref_max,
            "in_range": logic.lab_marker_in_range(value, ref_min, ref_max),
        }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_sensor.py -k req_hom_122 -v`
Expected: all PASS.

- [ ] **Step 5: Full regression check**

Run: `pytest tests/test_sensor.py -q && ruff check custom_components/health_o_mat/sensor.py`
Expected: all pass, `ruff` clean.

- [ ] **Step 6: Commit**

```bash
git add custom_components/health_o_mat/sensor.py tests/test_sensor.py
git commit -m "feat: add LabValueSensor for catalog and custom markers"
```

---

### Task 11: `binary_sensor.py` — `LabCategoryWarningEntity` (one per category)

**Files:**
- Modify: `custom_components/health_o_mat/binary_sensor.py`
- Test: `tests/test_binary_sensor.py`

**Interfaces:**
- Consumes: `logic.effective_lab_markers`, `logic.resolve_lab_reference`, `logic.lab_marker_in_range` (Tasks 2/3), `store.last_active_lab_reading` (Task 4), `areas.AREA_LABS` (Task 6), `const.LAB_CATEGORY_OTHER` (Task 1), existing `HealthOMatBinary` base.
- Produces: `LabCategoryWarningEntity` class; `async_setup_entry` extended. unique_id key = `binary_lab_warning_{category}` (locked in).

- [ ] **Step 1: Write the failing tests** (append to `tests/test_binary_sensor.py`, reusing its existing `_load`/`_run` helpers)

```python
def test_req_hom_122_lab_category_warning_off_when_in_range():
    coordinator = MagicMock()
    entry = MagicMock()
    entry.entry_id = "e1"
    entry.options = {}
    store = MagicMock()
    store.last_active_lab_reading.return_value = {"value": 32.0}

    entity = binary_sensor_module.LabCategoryWarningEntity(coordinator, entry, store, "liver")

    assert entity.is_on is False


def test_req_hom_122_lab_category_warning_on_when_out_of_range():
    coordinator = MagicMock()
    entry = MagicMock()
    entry.entry_id = "e1"
    entry.options = {}
    store = MagicMock()

    def _last(_entry_id, marker_key):
        return {"value": 999.0} if marker_key == "ggt" else {"value": 30.0}

    store.last_active_lab_reading.side_effect = _last

    entity = binary_sensor_module.LabCategoryWarningEntity(coordinator, entry, store, "liver")

    assert entity.is_on is True


def test_req_hom_122_lab_category_warning_off_without_any_reading():
    coordinator = MagicMock()
    entry = MagicMock()
    entry.entry_id = "e1"
    entry.options = {}
    store = MagicMock()
    store.last_active_lab_reading.return_value = None

    entity = binary_sensor_module.LabCategoryWarningEntity(coordinator, entry, store, "liver")

    assert entity.is_on is False


def test_req_hom_122_async_setup_entry_creates_one_binary_sensor_per_catalog_category():
    from custom_components.health_o_mat import const

    hass_coord = MagicMock()
    hass = MagicMock()
    entry = MagicMock()
    entry.entry_id = "e1"
    entry.options = {}
    hass.data = {"health_o_mat": {"e1": {"coordinator": hass_coord}, "shared": {"store": MagicMock()}}}
    added: list = []

    _run(binary_sensor_module.async_setup_entry(hass, entry, lambda ents: added.extend(ents)))

    lab_warnings = [e for e in added if isinstance(e, binary_sensor_module.LabCategoryWarningEntity)]
    catalog_categories = {m["category"] for m in const.LAB_MARKERS.values()}
    assert {w._category for w in lab_warnings} == catalog_categories


def test_req_hom_122_async_setup_entry_skips_other_category():
    hass = MagicMock()
    entry = MagicMock()
    entry.entry_id = "e1"
    entry.options = {}
    hass.data = {"health_o_mat": {"e1": {"coordinator": MagicMock()}, "shared": {"store": MagicMock()}}}
    added: list = []

    _run(binary_sensor_module.async_setup_entry(hass, entry, lambda ents: added.extend(ents)))

    lab_warnings = [e for e in added if isinstance(e, binary_sensor_module.LabCategoryWarningEntity)]
    assert all(w._category != "other" for w in lab_warnings)


def test_req_hom_122_async_setup_entry_skips_lab_warnings_when_area_disabled():
    hass = MagicMock()
    entry = MagicMock()
    entry.entry_id = "e1"
    entry.options = {"areas": {"labs": False}}
    hass.data = {"health_o_mat": {"e1": {"coordinator": MagicMock()}, "shared": {"store": MagicMock()}}}
    added: list = []

    _run(binary_sensor_module.async_setup_entry(hass, entry, lambda ents: added.extend(ents)))

    lab_warnings = [e for e in added if isinstance(e, binary_sensor_module.LabCategoryWarningEntity)]
    assert lab_warnings == []
```

(Add `def _run(coro): return asyncio.new_event_loop().run_until_complete(coro)` to the top of `tests/test_binary_sensor.py` if it isn't already there — check first, `test_sensor.py`/other files already have this exact helper.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_binary_sensor.py -k req_hom_122 -v`
Expected: FAIL — `AttributeError`.

- [ ] **Step 3: Implement** — edit `custom_components/health_o_mat/binary_sensor.py`

Add imports:

```python
from .const import DOMAIN, LAB_CATEGORY_OTHER
```

Extend `async_setup_entry` (after the existing `if active[areas.AREA_BP]:` block):

```python
    if active[areas.AREA_LABS]:
        custom_markers = entry.options.get("lab_custom_markers")
        categories = {
            marker_def["category"]
            for marker_def in logic.effective_lab_markers(custom_markers).values()
            if marker_def["category"] != LAB_CATEGORY_OTHER
        }
        for category in sorted(categories):
            entities.append(LabCategoryWarningEntity(coord, entry, store, category))
```

Add the new class at the end of the file:

```python
class LabCategoryWarningEntity(HealthOMatBinary):
    """Warnt, wenn ≥ 1 Marker einer Kategorie außerhalb des Referenzbereichs liegt."""

    _attr_icon = "mdi:flask-alert-outline"
    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    def __init__(self, coordinator, entry, store, category: str) -> None:
        super().__init__(coordinator, entry, store, f"binary_lab_warning_{category}")
        self._category = category

    @property
    def is_on(self) -> bool:
        custom_markers = self._entry.options.get("lab_custom_markers")
        ref_overrides = self._entry.options.get("lab_ref_overrides")
        markers = logic.effective_lab_markers(custom_markers)
        for marker_key, marker_def in markers.items():
            if marker_def["category"] != self._category:
                continue
            reading = self._store.last_active_lab_reading(self._entry.entry_id, marker_key)
            if reading is None:
                continue
            ref_min, ref_max = logic.resolve_lab_reference(
                marker_key,
                marker_def,
                ref_overrides if not marker_def.get("is_custom") else None,
            )
            if logic.lab_marker_in_range(reading.get("value"), ref_min, ref_max) is False:
                return True
        return False
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_binary_sensor.py -k req_hom_122 -v`
Expected: all PASS.

- [ ] **Step 5: Full regression check**

Run: `pytest tests/test_binary_sensor.py -q && ruff check custom_components/health_o_mat/binary_sensor.py`
Expected: all pass, `ruff` clean.

- [ ] **Step 6: Commit**

```bash
git add custom_components/health_o_mat/binary_sensor.py tests/test_binary_sensor.py
git commit -m "feat: add LabCategoryWarningEntity per lab category"
```

---

### Task 12: `strings.json`/translations — entity names for 29 markers + 9 categories

**Files:**
- Modify: `custom_components/health_o_mat/strings.json`, `custom_components/health_o_mat/translations/de.json`, `custom_components/health_o_mat/translations/en.json`
- Test: `tests/test_translations.py`

**Interfaces:**
- Consumes: `const.LAB_MARKERS` (`name_de`/`name_en`), `const.LAB_CATEGORIES` (Task 1) as the single source of truth for which keys must exist.
- Produces: `entity.sensor.lab_<marker_key>.name` for all 29 catalog markers, `entity.binary_sensor.lab_warning_<category>.name` for the 9 non-`other` categories, in all three translation files. Consumed at runtime by the `translation_key`s set in Task 10/11 (`f"lab_{marker_key}"` / entity key `binary_lab_warning_{category}` — HA's translation lookup uses the **platform + translation_key**, not the unique_id suffix, so the JSON key is `lab_<marker_key>` / `lab_warning_<category>`, matching `_attr_translation_key` exactly).

- [ ] **Step 1: Write the failing test** (append to `tests/test_translations.py`)

```python
def test_req_hom_122_lab_sensor_translation_keys_cover_every_catalog_marker():
    import json
    from pathlib import Path
    from custom_components.health_o_mat import const

    base = Path(__file__).parent.parent / "custom_components" / "health_o_mat"
    strings = json.loads((base / "strings.json").read_text(encoding="utf-8"))
    de = json.loads((base / "translations" / "de.json").read_text(encoding="utf-8"))
    en = json.loads((base / "translations" / "en.json").read_text(encoding="utf-8"))

    for marker_key in const.LAB_MARKERS:
        key = f"lab_{marker_key}"
        assert key in strings.get("entity", {}).get("sensor", {}), key
        assert key in de.get("entity", {}).get("sensor", {}), key
        assert key in en.get("entity", {}).get("sensor", {}), key


def test_req_hom_122_lab_binary_sensor_translation_keys_cover_every_category():
    import json
    from pathlib import Path
    from custom_components.health_o_mat import const

    base = Path(__file__).parent.parent / "custom_components" / "health_o_mat"
    strings = json.loads((base / "strings.json").read_text(encoding="utf-8"))

    categories = {m["category"] for m in const.LAB_MARKERS.values()}
    for category in categories:
        key = f"lab_warning_{category}"
        assert key in strings.get("entity", {}).get("binary_sensor", {}), key
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_translations.py -k req_hom_122_lab -v`
Expected: FAIL — `AssertionError: lab_alt`.

- [ ] **Step 3: Implement** — add to `custom_components/health_o_mat/strings.json` under `entity.sensor` (same level as the existing `"today"`/`"goal_percent"` keys), one entry per catalog marker using its `name_en` (strings.json is the English master per the existing convention, e.g. `"today": {"name": "Drinks today"}`):

```json
"lab_alt": { "name": "ALT (ALT/GPT)" },
"lab_ast": { "name": "AST (AST/GOT)" },
"lab_ggt": { "name": "GGT" },
"lab_bilirubin_total": { "name": "Total bilirubin" },
"lab_total_protein": { "name": "Total protein" },
"lab_creatinine": { "name": "Creatinine" },
"lab_egfr": { "name": "eGFR" },
"lab_urea": { "name": "Urea" },
"lab_urine_protein_creatinine_ratio": { "name": "Urine protein/creatinine ratio" },
"lab_sodium": { "name": "Sodium" },
"lab_potassium": { "name": "Potassium" },
"lab_calcium": { "name": "Total calcium" },
"lab_magnesium": { "name": "Magnesium" },
"lab_chloride": { "name": "Chloride" },
"lab_cholesterol_total": { "name": "Total cholesterol" },
"lab_ldl": { "name": "LDL" },
"lab_hdl": { "name": "HDL" },
"lab_triglycerides": { "name": "Triglycerides" },
"lab_tsh": { "name": "TSH" },
"lab_ft4": { "name": "fT4" },
"lab_ft3": { "name": "fT3" },
"lab_hemoglobin": { "name": "Hemoglobin" },
"lab_leukocytes": { "name": "Leukocytes" },
"lab_platelets": { "name": "Platelets" },
"lab_crp": { "name": "CRP" },
"lab_esr": { "name": "ESR" },
"lab_lipase": { "name": "Lipase" },
"lab_amylase": { "name": "Amylase" },
"lab_tacrolimus": { "name": "Tacrolimus (trough)" }
```

Add the same 29 keys to `custom_components/health_o_mat/translations/en.json` (identical values) and to `custom_components/health_o_mat/translations/de.json`, using each marker's `name_de` from `const.LAB_MARKERS` (`ALT (GPT)`, `AST (GOT)`, `GGT (Gamma-GT)`, `Bilirubin gesamt`, `Gesamteiweiß`, `Kreatinin`, `eGFR`, `Harnstoff`, `Protein/Kreatinin-Quotient (Urin)`, `Natrium`, `Kalium`, `Calcium gesamt`, `Magnesium`, `Chlorid`, `Gesamtcholesterin`, `LDL`, `HDL`, `Triglyceride`, `TSH`, `fT4`, `fT3`, `Hämoglobin`, `Leukozyten`, `Thrombozyten`, `CRP`, `BSG`, `Lipase`, `Amylase`, `Tacrolimus (Talspiegel)` — same order as the `lab_<marker_key>` list above, copy verbatim from Task 1's `LAB_MARKERS`).

Add to `strings.json` under `entity.binary_sensor` (same level as the existing `"goal_reached"`/`"bp_warning"` keys), one entry per non-`other` category using each category's `name_en` from `const.LAB_CATEGORIES` (Task 1):

```json
"lab_warning_liver": { "name": "Liver warning" },
"lab_warning_kidney": { "name": "Kidney warning" },
"lab_warning_electrolytes": { "name": "Electrolytes warning" },
"lab_warning_lipids": { "name": "Lipids warning" },
"lab_warning_thyroid": { "name": "Thyroid warning" },
"lab_warning_blood_count": { "name": "Blood count warning" },
"lab_warning_inflammation": { "name": "Inflammation warning" },
"lab_warning_digestion": { "name": "Digestion warning" },
"lab_warning_drug_levels": { "name": "Drug levels warning" }
```

Mirror into `en.json` (identical) and into `de.json` using `name_de` + "-Warnung" (`"Leber-Warnung"`, `"Nieren-Warnung"`, `"Elektrolyt-Warnung"`, `"Lipid-Warnung"`, `"Schilddrüsen-Warnung"`, `"Blutbild-Warnung"`, `"Entzündungs-Warnung"`, `"Verdauungs-Warnung"`, `"Medikamentenspiegel-Warnung"`).

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_translations.py -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add custom_components/health_o_mat/strings.json custom_components/health_o_mat/translations/de.json custom_components/health_o_mat/translations/en.json tests/test_translations.py
git commit -m "feat: add entity translations for lab markers and categories"
```

---

## Wave 4 — Admin-UI

### Task 13: `ws_api.py` — settings schema + `build_settings`/`parse_settings_message` extension

**Files:**
- Modify: `custom_components/health_o_mat/ws_api.py`
- Test: `tests/test_ws_api.py`

**Interfaces:**
- Consumes: `logic.normalize_lab_custom_markers`, `logic.normalize_lab_ref_overrides`, `logic.normalize_lab_hidden_categories` (Tasks 2/3), `const.OPTION_LAB_CUSTOM_MARKERS`/`OPTION_LAB_REF_OVERRIDES`/`OPTION_LAB_HIDDEN_CATEGORIES`, `const.LAB_MARKERS`/`LAB_CATEGORIES` (Task 1), existing `SETTINGS_SCHEMA`, `SETTINGS_KEYS`, `build_settings`, `parse_settings_message`.
- Produces: `SETTINGS_KEYS` + `SETTINGS_SCHEMA` extended with the three new options; `build_settings(entry)` additionally returns `lab_custom_markers`/`lab_ref_overrides`/`lab_hidden_categories` plus a read-only `lab_catalog` block (`{"categories": [...], "markers": {...}}` straight from `const.py`, so the Admin UI can render the reference-range grid without a separate WS round-trip). Consumed by Task 14 (admin JS).

- [ ] **Step 1: Write the failing tests** (append to `tests/test_ws_api.py` — reuse the file's existing `SETTINGS_SCHEMA`/`build_settings`/`parse_settings_message` test fixtures/imports, check the top of the file for how `entry`/`hass` mocks are built for existing `set_settings` tests and follow that exact pattern)

```python
def test_req_hom_122_build_settings_includes_lab_catalog():
    from custom_components.health_o_mat import ws_api, const

    entry = MagicMock()
    entry.options = {}
    entry.data = {"person": "caro"}

    settings = ws_api.build_settings(entry)

    assert settings["lab_catalog"]["categories"] == const.LAB_CATEGORIES
    assert "alt" in settings["lab_catalog"]["markers"]
    assert settings["lab_custom_markers"] == []
    assert settings["lab_ref_overrides"] == {}
    assert settings["lab_hidden_categories"] == []


def test_req_hom_122_build_settings_returns_normalized_overrides():
    from custom_components.health_o_mat import ws_api

    entry = MagicMock()
    entry.options = {"lab_ref_overrides": {"alt": {"ref_min": 5}, "not_a_marker": {"ref_min": 1}}}
    entry.data = {"person": "caro"}

    settings = ws_api.build_settings(entry)

    assert settings["lab_ref_overrides"] == {"alt": {"ref_min": 5}}


def test_req_hom_122_parse_settings_message_normalizes_custom_markers():
    from custom_components.health_o_mat import ws_api

    msg = {
        "lab_custom_markers": [
            {"name": "Vitamin D", "category": "other", "unit": "ng/mL"},
        ]
    }

    updates, error = ws_api.parse_settings_message(msg)

    assert error is None
    assert updates["lab_custom_markers"][0]["key"] == "vitamin_d"


def test_req_hom_122_parse_settings_message_normalizes_hidden_categories():
    from custom_components.health_o_mat import ws_api

    updates, error = ws_api.parse_settings_message(
        {"lab_hidden_categories": ["thyroid", "not_a_category"]}
    )

    assert error is None
    assert updates["lab_hidden_categories"] == ["thyroid"]


def test_req_hom_122_parse_settings_message_rejects_non_list_custom_markers():
    from custom_components.health_o_mat import ws_api

    updates, error = ws_api.parse_settings_message({"lab_custom_markers": "nope"})

    assert error is not None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_ws_api.py -k req_hom_122 -v`
Expected: FAIL — `KeyError: 'lab_catalog'`.

- [ ] **Step 3: Implement** — edit `custom_components/health_o_mat/ws_api.py`

Add imports (extend the existing `from .const import (...)` block with the new names from Task 1):

```python
    LAB_CATEGORIES,
    LAB_MARKERS,
    OPTION_LAB_CUSTOM_MARKERS,
    OPTION_LAB_HIDDEN_CATEGORIES,
    OPTION_LAB_REF_OVERRIDES,
```

Extend `SETTINGS_KEYS` (find the existing tuple definition and add the three new keys):

```python
    OPTION_LAB_CUSTOM_MARKERS,
    OPTION_LAB_REF_OVERRIDES,
    OPTION_LAB_HIDDEN_CATEGORIES,
```

Extend `SETTINGS_SCHEMA` (these three are validated loosely here — `dict`/`list` — because the real field-level validation happens in `logic.normalize_lab_*`, called from `parse_settings_message`, exactly like `WELLBEING_IMAGES_OPTION` is handled today):

```python
        vol.Optional(OPTION_LAB_CUSTOM_MARKERS): list,
        vol.Optional(OPTION_LAB_REF_OVERRIDES): dict,
        vol.Optional(OPTION_LAB_HIDDEN_CATEGORIES): list,
```

Extend `parse_settings_message` — add this block before the final `updates.update(SETTINGS_SCHEMA(raw))` call, mirroring the existing `WELLBEING_IMAGES_OPTION` pop-and-normalize pattern:

```python
    if OPTION_LAB_CUSTOM_MARKERS in raw:
        raw_markers = raw.pop(OPTION_LAB_CUSTOM_MARKERS)
        if not isinstance(raw_markers, list):
            return {}, (
                f"Ungültige Einstellung '{OPTION_LAB_CUSTOM_MARKERS}': erwartet eine Liste, "
                f"erhalten {type(raw_markers).__name__}"
            )
        updates[OPTION_LAB_CUSTOM_MARKERS] = logic.normalize_lab_custom_markers(raw_markers)

    if OPTION_LAB_REF_OVERRIDES in raw:
        raw_overrides = raw.pop(OPTION_LAB_REF_OVERRIDES)
        if not isinstance(raw_overrides, dict):
            return {}, (
                f"Ungültige Einstellung '{OPTION_LAB_REF_OVERRIDES}': erwartet ein Objekt, "
                f"erhalten {type(raw_overrides).__name__}"
            )
        updates[OPTION_LAB_REF_OVERRIDES] = logic.normalize_lab_ref_overrides(raw_overrides)

    if OPTION_LAB_HIDDEN_CATEGORIES in raw:
        raw_hidden = raw.pop(OPTION_LAB_HIDDEN_CATEGORIES)
        if not isinstance(raw_hidden, list):
            return {}, (
                f"Ungültige Einstellung '{OPTION_LAB_HIDDEN_CATEGORIES}': erwartet eine Liste, "
                f"erhalten {type(raw_hidden).__name__}"
            )
        updates[OPTION_LAB_HIDDEN_CATEGORIES] = logic.normalize_lab_hidden_categories(raw_hidden)
```

Extend `build_settings` — add before the final `return {...}` (append entries to the returned dict):

```python
        OPTION_LAB_CUSTOM_MARKERS: logic.normalize_lab_custom_markers(
            options.get(OPTION_LAB_CUSTOM_MARKERS)
        ),
        OPTION_LAB_REF_OVERRIDES: logic.normalize_lab_ref_overrides(
            options.get(OPTION_LAB_REF_OVERRIDES)
        ),
        OPTION_LAB_HIDDEN_CATEGORIES: logic.normalize_lab_hidden_categories(
            options.get(OPTION_LAB_HIDDEN_CATEGORIES)
        ),
        # Read-only Referenzdaten aus const.py — Admin-UI baut die
        # Referenzbereich-Tabelle daraus auf, kein zweiter WS-Request nötig.
        "lab_catalog": {"categories": LAB_CATEGORIES, "markers": LAB_MARKERS},
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_ws_api.py -k req_hom_122 -v`
Expected: all PASS.

- [ ] **Step 5: Full regression check**

Run: `pytest tests/test_ws_api.py -q && ruff check custom_components/health_o_mat/ws_api.py`
Expected: all pass, `ruff` clean.

- [ ] **Step 6: Commit**

```bash
git add custom_components/health_o_mat/ws_api.py tests/test_ws_api.py
git commit -m "feat: add lab settings to set_settings/get_settings"
```

---

### Task 14: `health-o-mat-panel-admin.js` + `health-o-mat-panel.js` — Laborwerte settings section

**Files:**
- Modify: `custom_components/health_o_mat/www/health-o-mat-panel-admin.js`, `custom_components/health_o_mat/www/health-o-mat-panel.js`
- Test: `tests/test_panel_js.py`

**Interfaces:**
- Consumes: `settings.lab_catalog` (`{categories, markers}`), `settings.lab_custom_markers`, `settings.lab_ref_overrides`, `settings.lab_hidden_categories` from `get_settings`/`set_settings` (Task 13).
- Produces: `labSettingsSection(panel, settings, entryId)` (new export from `health-o-mat-panel-admin.js`, called from `settingsForm`); three new `_collectSettingsPayload` fields (`lab_ref_overrides`, `lab_hidden_categories`, `lab_custom_markers`) and matching `_changedSettings` diff entries in `health-o-mat-panel.js`; `panel._labCustomDraft: dict[entryId, list]` as the in-memory custom-marker editor state (mirrors the existing `_quickDraft` pattern).

- [ ] **Step 1: Write the failing tests** (append to `tests/test_panel_js.py` — check the file's existing style first: these JS-behavior tests in this repo are typically static-source assertions, e.g. `assert "labSettingsSection" in source`, reading the `.js` file as text and checking for the presence of specific exported function names/strings, matching patterns like `test_panel_base_exposes_wellbeing_chart_helpers` mentioned in the REQUIREMENTS.md changelog — follow that exact style, do not invent a JS test runner)

```python
def test_req_hom_122_panel_admin_exports_lab_settings_section():
    source = _read_www("health-o-mat-panel-admin.js")
    assert "export function labSettingsSection" in source


def test_req_hom_122_panel_admin_lab_section_renders_hide_checkboxes():
    source = _read_www("health-o-mat-panel-admin.js")
    assert "lab-hide-" in source


def test_req_hom_122_panel_admin_lab_section_renders_ref_override_inputs():
    source = _read_www("health-o-mat-panel-admin.js")
    assert "lab-ref-min-" in source
    assert "lab-ref-max-" in source


def test_req_hom_122_panel_admin_lab_section_renders_custom_marker_form():
    source = _read_www("health-o-mat-panel-admin.js")
    assert "lab-custom-add" in source


def test_req_hom_122_panel_js_collects_lab_settings_fields():
    source = _read_www("health-o-mat-panel.js")
    assert "lab_ref_overrides" in source
    assert "lab_hidden_categories" in source
    assert "lab_custom_markers" in source


def test_req_hom_122_panel_js_has_lab_custom_draft_state():
    source = _read_www("health-o-mat-panel.js")
    assert "_labCustomDraft" in source
```

(`_read_www` must be the file's existing helper that reads a `www/*.js` file as text — check the top of `tests/test_panel_js.py` for its exact name/signature, e.g. it may already be called `_source("health-o-mat-panel.js")` or similar; use whatever this file already defines instead of inventing `_read_www`.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_panel_js.py -k req_hom_122 -v`
Expected: FAIL — `AssertionError` (strings not found yet).

- [ ] **Step 3: Implement** — edit `custom_components/health_o_mat/www/health-o-mat-panel-admin.js`

Add to the existing `import { ... } from "./health-o-mat-panel-base.js?v=0.15.0";` block: `escapeHtml` and `t` are already imported; no new base-module exports are needed for this task (category/marker data comes straight from `settings.lab_catalog`).

Add a new export, called from `settingsForm` right after the existing areas-toggle block (find where `renderSettings`'s `settingsForm` assembles its returned HTML string and insert the new section's HTML there, same way the existing `wellbeing_images` block is spliced in):

```javascript
/* ---- Laborwerte (REQ-HOM-122) --------------------------------------- */

export function labSettingsSection(panel, settings, entryId) {
  const catalog = settings.lab_catalog || { categories: [], markers: {} };
  const overrides = settings.lab_ref_overrides || {};
  const hidden = new Set(settings.lab_hidden_categories || []);
  const custom =
    (panel._labCustomDraft && panel._labCustomDraft[entryId]) ||
    settings.lab_custom_markers ||
    [];

  const refRows = Object.entries(catalog.markers || {})
    .map(([key, marker]) => {
      const override = overrides[key] || {};
      const refMin = override.ref_min != null ? override.ref_min : marker.ref_min;
      const refMax = override.ref_max != null ? override.ref_max : marker.ref_max;
      const categoryName =
        (catalog.categories || []).find((c) => c.key === marker.category) || {};
      return `<tr>
          <td>${escapeHtml(categoryName.name_de || marker.category)}</td>
          <td>${escapeHtml(marker.name_de || key)}</td>
          <td>${escapeHtml(marker.canonical_unit || "")}</td>
          <td>
            <input type="number" step="any" data-field="lab-ref-min-${escapeHtml(key)}"
              value="${refMin == null ? "" : escapeHtml(String(refMin))}" />
            –
            <input type="number" step="any" data-field="lab-ref-max-${escapeHtml(key)}"
              value="${refMax == null ? "" : escapeHtml(String(refMax))}" />
          </td>
          <td><button class="btn ghost" type="button" data-action="lab-ref-reset" data-marker="${escapeHtml(
            key
          )}" title="${escapeHtml(t("ui_admin_lab_reset", "Auf Katalog-Default zurücksetzen"))}">⟲</button></td>
        </tr>`;
    })
    .join("");

  const hideCheckboxes = (catalog.categories || [])
    .map(
      (category) => `<label class="checkbox">
          <input type="checkbox" data-field="lab-hide-${escapeHtml(category.key)}"${
        hidden.has(category.key) ? "" : " checked"
      } />
          ${escapeHtml(category.name_de)}
        </label>`
    )
    .join("");

  const customRows = custom
    .map(
      (marker, index) => `<li>
          ${escapeHtml(marker.name)} (${escapeHtml(marker.key)}) — ${escapeHtml(marker.unit)}${
        marker.alt_unit ? ` (alt: ${escapeHtml(marker.alt_unit.unit)})` : ""
      }
          <button class="btn ghost" type="button" data-action="lab-custom-remove" data-index="${index}">✕</button>
        </li>`
    )
    .join("");

  const categoryOptions = (catalog.categories || [])
    .map((category) => `<option value="${escapeHtml(category.key)}">${escapeHtml(category.name_de)}</option>`)
    .join("");

  return `<div class="card">
      <div class="card-title">${escapeHtml(t("ui_admin_lab_title", "Laborwerte"))}</div>

      <div class="card">
        <div class="card-subtitle">${escapeHtml(
          t("ui_admin_lab_ref_title", "Referenzbereiche anpassen")
        )}</div>
        <table class="lab-ref-table">
          <thead><tr><th>${escapeHtml(t("ui_admin_lab_category", "Kategorie"))}</th><th>${escapeHtml(
    t("ui_admin_lab_marker", "Marker")
  )}</th><th>${escapeHtml(t("ui_admin_lab_unit", "Einheit"))}</th><th>${escapeHtml(
    t("ui_admin_lab_range", "Referenz")
  )}</th><th></th></tr></thead>
          <tbody>${refRows}</tbody>
        </table>
      </div>

      <div class="card">
        <div class="card-subtitle">${escapeHtml(
          t("ui_admin_lab_hide_title", "Kategorien ausblenden")
        )}</div>
        <div class="checkbox-grid">${hideCheckboxes}</div>
      </div>

      <div class="card">
        <div class="card-subtitle">${escapeHtml(t("ui_admin_lab_custom_title", "Eigene Marker"))}</div>
        <label class="field">${escapeHtml(t("ui_admin_lab_custom_name", "Name"))}
          <input type="text" data-field="lab-custom-name" />
        </label>
        <label class="field">${escapeHtml(t("ui_admin_lab_custom_unit", "Einheit"))}
          <input type="text" data-field="lab-custom-unit" />
        </label>
        <label class="field">${escapeHtml(t("ui_admin_lab_custom_category", "Kategorie"))}
          <select data-field="lab-custom-category">${categoryOptions}</select>
        </label>
        <label class="field">${escapeHtml(t("ui_admin_lab_custom_range", "Referenz"))}
          <input type="number" step="any" data-field="lab-custom-ref-min" />
          <input type="number" step="any" data-field="lab-custom-ref-max" />
        </label>
        <details>
          <summary>${escapeHtml(t("ui_admin_lab_custom_alt_unit", "Alternative Einheit (optional)"))}</summary>
          <input type="text" data-field="lab-custom-alt-unit" placeholder="${escapeHtml(
            t("ui_admin_lab_custom_alt_unit_name", "Einheit")
          )}" />
          <input type="number" step="any" data-field="lab-custom-alt-factor" placeholder="${escapeHtml(
            t("ui_admin_lab_custom_alt_factor", "Faktor → Haupteinheit")
          )}" />
        </details>
        <button class="btn" type="button" data-action="lab-custom-add">${escapeHtml(
          t("ui_admin_lab_custom_submit", "+ Hinzufügen")
        )}</button>
        <ul class="lab-custom-list">${customRows}</ul>
      </div>

      <div class="card">
        <a href="https://github.com/Popoboxxo/ha-health-o-mat/issues/new?title=Lab-Kategorie%2FMarker-Vorschlag" target="_blank" rel="noopener">${escapeHtml(
          t("ui_admin_lab_feedback", "Fehlt eine Kategorie oder ein Marker? Vorschlag/Feedback auf GitHub")
        )}</a>
      </div>
    </div>`;
}
```

In `settingsForm` (same file), insert the section into the returned template string right after the existing area-toggle block (find the line that closes that block and splice `${labSettingsSection(panel, s, entryId)}` into the concatenated HTML — follow the exact insertion style already used for the wellbeing-images block).

- [ ] **Step 4: Implement** — edit `custom_components/health_o_mat/www/health-o-mat-panel.js`

Import the new function at the top (extend the existing `import { ..., renderSettings, ... } from "./health-o-mat-panel-admin.js?v=0.15.0";`-style import if `renderSettings` is imported from there into `panel.js`, OR — if `settingsForm`/`labSettingsSection` are only used inside `health-o-mat-panel-admin.js` itself — skip this import; `labSettingsSection` is called from within `health-o-mat-panel-admin.js`'s own `settingsForm`, not from `panel.js`). `panel.js` only needs the **collection** side.

Initialize the draft state next to the existing `_quickDraft` initialization (constructor or wherever `this._quickDraft` is first set):

```javascript
this._labCustomDraft = {};
```

Extend `_collectSettingsPayload()` — add before the final `return { errors, payload: {...} }`:

```javascript
    const labRefOverrides = {};
    const catalog = (this._settings[entryId] || {}).lab_catalog || { markers: {} };
    Object.keys(catalog.markers || {}).forEach((key) => {
      const marker = catalog.markers[key];
      const minEl = this.shadowRoot.querySelector(`[data-field="lab-ref-min-${key}"]`);
      const maxEl = this.shadowRoot.querySelector(`[data-field="lab-ref-max-${key}"]`);
      const minVal = minEl && minEl.value !== "" ? toNumber(minEl.value, NaN) : null;
      const maxVal = maxEl && maxEl.value !== "" ? toNumber(maxEl.value, NaN) : null;
      const entry = {};
      if (minVal != null && Number.isFinite(minVal) && minVal !== marker.ref_min) {
        entry.ref_min = minVal;
      }
      if (maxVal != null && Number.isFinite(maxVal) && maxVal !== marker.ref_max) {
        entry.ref_max = maxVal;
      }
      if (Object.keys(entry).length) labRefOverrides[key] = entry;
    });

    const labHiddenCategories = ((catalog.categories || [])).filter((category) => {
      const el = this.shadowRoot.querySelector(`[data-field="lab-hide-${category.key}"]`);
      return !(el && el.checked);
    }).map((category) => category.key);

    const labCustomMarkers = (this._labCustomDraft[entryId] || (this._settings[entryId] || {}).lab_custom_markers || []).slice();
```

Add the three fields to the returned `payload` object (same object literal as `daily_goal_ml`, etc.):

```javascript
        lab_ref_overrides: labRefOverrides,
        lab_hidden_categories: labHiddenCategories,
        lab_custom_markers: labCustomMarkers,
```

Extend `_changedSettings(entryId, payload)` — add next to the existing `wellbeing_images` diff line:

```javascript
    if (stableJson(current.lab_ref_overrides) !== stableJson(payload.lab_ref_overrides)) {
      out.lab_ref_overrides = payload.lab_ref_overrides;
    }
    if (stableJson(current.lab_hidden_categories) !== stableJson(payload.lab_hidden_categories)) {
      out.lab_hidden_categories = payload.lab_hidden_categories;
    }
    if (stableJson(current.lab_custom_markers) !== stableJson(payload.lab_custom_markers)) {
      out.lab_custom_markers = payload.lab_custom_markers;
    }
```

Add the two new `data-action` cases to the existing click-delegation switch (find the `switch (action) { case "settings": ... }` block mentioned around the existing `case "settings-reload":` and add siblings):

```javascript
      case "lab-custom-add": {
        const name = String(this._readField("lab-custom-name", "") || "").trim();
        const unit = String(this._readField("lab-custom-unit", "") || "").trim();
        if (!name || !unit) break;
        const categoryEl = this.shadowRoot.querySelector('[data-field="lab-custom-category"]');
        const category = categoryEl ? categoryEl.value : "other";
        const refMin = toNumber(this._readField("lab-custom-ref-min", ""), NaN);
        const refMax = toNumber(this._readField("lab-custom-ref-max", ""), NaN);
        const altUnit = String(this._readField("lab-custom-alt-unit", "") || "").trim();
        const altFactor = toNumber(this._readField("lab-custom-alt-factor", ""), NaN);
        const entry = { name, unit, category };
        if (Number.isFinite(refMin)) entry.ref_min = refMin;
        if (Number.isFinite(refMax)) entry.ref_max = refMax;
        if (altUnit && Number.isFinite(altFactor)) {
          entry.alt_unit = { unit: altUnit, factor_to_canonical: altFactor };
        }
        if (!this._labCustomDraft[entryId]) {
          this._labCustomDraft[entryId] = (this._settings[entryId] || {}).lab_custom_markers || [];
        }
        this._labCustomDraft[entryId] = this._labCustomDraft[entryId].concat([entry]);
        this._render();
        break;
      }
      case "lab-custom-remove": {
        const index = Number(el.getAttribute("data-index"));
        const list = this._labCustomDraft[entryId] || (this._settings[entryId] || {}).lab_custom_markers || [];
        this._labCustomDraft[entryId] = list.filter((_item, i) => i !== index);
        this._render();
        break;
      }
      case "lab-ref-reset": {
        const marker = el.getAttribute("data-marker");
        const minEl = this.shadowRoot.querySelector(`[data-field="lab-ref-min-${marker}"]`);
        const maxEl = this.shadowRoot.querySelector(`[data-field="lab-ref-max-${marker}"]`);
        if (minEl) minEl.value = "";
        if (maxEl) maxEl.value = "";
        break;
      }
```

(`entryId` in the switch body must be whatever variable the surrounding click handler already uses to identify the currently-open settings person — follow the existing `case "settings":` handler's variable name exactly, e.g. it likely reads `this._settingsEntry`; do not invent a new variable name.)

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_panel_js.py -k req_hom_122 -v`
Expected: all PASS.

- [ ] **Step 6: Full regression check**

Run: `pytest tests/test_panel_js.py -q`
Expected: all pass.

- [ ] **Step 7: Manual smoke check** (per CLAUDE.md: UI changes get a real browser check before being reported done) — start the dev stack, open the Admin settings for a person, confirm: the reference-range table renders with all 29 markers, a category checkbox can be unchecked and persists after reload, a custom marker can be added and appears in the list, the "⟲" reset button clears an override's inputs.

- [ ] **Step 8: Commit**

```bash
git add custom_components/health_o_mat/www/health-o-mat-panel-admin.js custom_components/health_o_mat/www/health-o-mat-panel.js tests/test_panel_js.py
git commit -m "feat: add lab values settings section to admin panel"
```

---

## Wave 5 — Card + Panel

### Task 15: `ws_api.py` — `panel_data` labs block + `add_lab_value`/`remove_last_lab_value` WS commands

**Files:**
- Modify: `custom_components/health_o_mat/ws_api.py`
- Test: `tests/test_ws_api.py`

**Interfaces:**
- Consumes: `logic.effective_lab_markers`, `logic.resolve_lab_reference`, `logic.lab_marker_in_range`, `logic.resolve_lab_marker`, `logic.convert_lab_value` (Tasks 2/3), `store.active_lab_readings`, `store.last_active_lab_reading`, `store.add_lab_reading`, `store.remove_last_lab_reading` (Tasks 4/5), `areas.AREA_LABS`, `areas.active_areas` (Task 6), `const.OPTION_LAB_CUSTOM_MARKERS`/`OPTION_LAB_REF_OVERRIDES`/`OPTION_LAB_HIDDEN_CATEGORIES`/`LAB_REPORT_REF_MAX_LEN`.
- Produces: `_labs_block(entry, store, now) -> dict` (private helper, mirrors `_bp_block`/`_wellbeing_block`), wired into `build_panel_data` as `panel_data["labs"]`; `COMMAND_ADD_LAB_VALUE = "health_o_mat/add_lab_value"`, `COMMAND_REMOVE_LAST_LAB_VALUE = "health_o_mat/remove_last_lab_value"`; `websocket_add_lab_value`, `websocket_remove_last_lab_value` handlers, registered the same way as `websocket_save_measurement`.

The `labs` block shape (consumed by Task 16/17/18/19 JS):

```python
{
    "categories": [{"key": "liver", "name": "Leber", "hidden": False}, ...],  # all 10, incl. "other"
    "markers": {
        "alt": {
            "category": "liver", "name": "ALT (GPT)", "unit": "U/L",
            "ref_min": 10, "ref_max": 50, "is_custom": False,
            "value": 32.0, "ts": "...", "in_range": True,
            "reported_value": 32.0, "reported_unit": "U/L", "report_ref": None,
            "history": [{"ts": "...", "value": 30.0}, ...up to 14],
        },
        ...
    },
}
```

- [ ] **Step 1: Write the failing tests** (append to `tests/test_ws_api.py`)

```python
def test_req_hom_122_panel_data_includes_labs_block():
    from custom_components.health_o_mat import ws_api

    hass, entry, store = _make_panel_data_fixture()  # see Step 1a below
    store.active_entry.return_value = {"lab_readings": []}
    store.last_active_lab_reading.return_value = None
    store.active_lab_readings.return_value = []

    data = ws_api.build_panel_data(hass, entry.entry_id, _now())

    assert "labs" in data
    assert any(c["key"] == "liver" for c in data["labs"]["categories"])
    assert "alt" in data["labs"]["markers"]
    assert data["labs"]["markers"]["alt"]["value"] is None


def test_req_hom_122_panel_data_labs_marker_includes_history_and_subline():
    from custom_components.health_o_mat import ws_api

    hass, entry, store = _make_panel_data_fixture()
    store.active_entry.return_value = {"lab_readings": []}
    reading = {
        "ts": "2026-10-31T09:00:00+01:00", "value": 97.24, "unit": "µmol/L",
        "reported_value": 1.1, "reported_unit": "mg/dL", "report_ref": None,
    }
    store.last_active_lab_reading.return_value = reading
    store.active_lab_readings.return_value = [reading]

    data = ws_api.build_panel_data(hass, entry.entry_id, _now())

    marker = data["labs"]["markers"]["creatinine"]
    assert marker["value"] == 97.24
    assert marker["reported_value"] == 1.1
    assert marker["reported_unit"] == "mg/dL"
    assert marker["history"] == [{"ts": "2026-10-31T09:00:00+01:00", "value": 97.24}]


def test_req_hom_122_panel_data_labs_category_hidden_flag():
    from custom_components.health_o_mat import ws_api

    hass, entry, store = _make_panel_data_fixture()
    entry.options = {"lab_hidden_categories": ["thyroid"]}
    store.active_entry.return_value = {"lab_readings": []}
    store.last_active_lab_reading.return_value = None
    store.active_lab_readings.return_value = []

    data = ws_api.build_panel_data(hass, entry.entry_id, _now())

    thyroid = next(c for c in data["labs"]["categories"] if c["key"] == "thyroid")
    liver = next(c for c in data["labs"]["categories"] if c["key"] == "liver")
    assert thyroid["hidden"] is True
    assert liver["hidden"] is False
```

(`_make_panel_data_fixture()` and `_now()` must reuse whatever helper(s) the existing `build_panel_data` tests in `tests/test_ws_api.py` already use to construct a fake `hass`/`entry`/`store` triple — check the top of that file for the pattern used by e.g. the `bp`/`wellbeing` block tests and copy it instead of inventing new fixtures. If no shared helper exists, build the fixture inline in each test exactly the way the neighboring `_bp_block`/`_wellbeing_block` tests do.)

```python
def test_req_hom_122_websocket_add_lab_value_converts_and_stores():
    from custom_components.health_o_mat import ws_api

    hass, connection, msg = _make_ws_fixture(  # reuse existing WS-test fixture helper
        "health_o_mat/add_lab_value", {"marker": "alt", "value": 32.0}
    )
    store = MagicMock()
    store.add_lab_reading = AsyncMock()
    with _patched_store(hass, store):  # reuse existing patch pattern for _store(hass)
        _run(ws_api.websocket_add_lab_value(hass, connection, msg))

    store.add_lab_reading.assert_awaited_once()
    connection.send_result.assert_called_once()


def test_req_hom_122_websocket_add_lab_value_unknown_marker_sends_error():
    from custom_components.health_o_mat import ws_api

    hass, connection, msg = _make_ws_fixture(
        "health_o_mat/add_lab_value", {"marker": "not_a_marker", "value": 1}
    )
    store = MagicMock()
    with _patched_store(hass, store):
        _run(ws_api.websocket_add_lab_value(hass, connection, msg))

    connection.send_error.assert_called_once()
    connection.send_result.assert_not_called()


def test_req_hom_122_websocket_remove_last_lab_value_calls_store():
    from custom_components.health_o_mat import ws_api

    hass, connection, msg = _make_ws_fixture(
        "health_o_mat/remove_last_lab_value", {"marker": "alt"}
    )
    store = MagicMock()
    store.remove_last_lab_reading = AsyncMock(return_value=True)
    with _patched_store(hass, store):
        _run(ws_api.websocket_remove_last_lab_value(hass, connection, msg))

    store.remove_last_lab_reading.assert_awaited_once()
    connection.send_result.assert_called_once()
```

(`_make_ws_fixture`/`_patched_store`/`_run` are placeholders for whatever this file's EXISTING `websocket_save_measurement` tests already use — e.g. there is almost certainly a helper building a `MagicMock` connection with `send_result`/`send_error` and patching `ws_api._store`/`ws_api._runtime_entry`/`ws_api._entry_ready`. Read 2-3 existing `websocket_save_measurement` or `websocket_set_wellbeing` tests in `tests/test_ws_api.py` immediately before writing this step and copy their exact fixture-construction code verbatim, substituting the lab command/payload — do not guess the helper names.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_ws_api.py -k req_hom_122 -v`
Expected: FAIL — `KeyError: 'labs'` / `AttributeError: ...websocket_add_lab_value`.

- [ ] **Step 3: Implement `_labs_block` + wire into `build_panel_data`** — edit `custom_components/health_o_mat/ws_api.py`

Add imports to the existing `from .const import (...)` block:

```python
    LAB_CATEGORIES,
    LAB_CATEGORY_OTHER,
    LAB_REPORT_REF_MAX_LEN,
    OPTION_LAB_CUSTOM_MARKERS,
    OPTION_LAB_HIDDEN_CATEGORIES,
    OPTION_LAB_REF_OVERRIDES,
```

Add the helper next to `_wellbeing_block` (same file section):

```python
_LAB_HISTORY_LIMIT = 14


def _labs_block(entry: Any, store: HealthOMatStore, now: datetime) -> dict[str, Any]:
    """Labor-Block für `panel_data` (REQ-HOM-122) — kein Zweit-Datenmodell.

    Enthält ALLE Kategorien (inkl. `hidden`-Flag) und ALLE effektiven Marker
    (Katalog + Custom), damit Card/Panel ohne weiteren WS-Request filtern,
    sortieren und den Warn-Status berechnen können (§7.3 der Spec).
    """
    options = getattr(entry, "options", None) or {}
    custom_markers = options.get(OPTION_LAB_CUSTOM_MARKERS)
    ref_overrides = options.get(OPTION_LAB_REF_OVERRIDES)
    hidden = set(logic.normalize_lab_hidden_categories(options.get(OPTION_LAB_HIDDEN_CATEGORIES)))

    categories = [
        {"key": category["key"], "name": category["name_de"], "hidden": category["key"] in hidden}
        for category in LAB_CATEGORIES
    ]

    markers: dict[str, Any] = {}
    for marker_key, marker_def in logic.effective_lab_markers(custom_markers).items():
        overrides_for_marker = ref_overrides if not marker_def.get("is_custom") else None
        ref_min, ref_max = logic.resolve_lab_reference(marker_key, marker_def, overrides_for_marker)
        last = store.last_active_lab_reading(entry.entry_id, marker_key) if store else None
        history_items = (
            store.active_lab_readings(entry.entry_id, marker_key=marker_key)[-_LAB_HISTORY_LIMIT:]
            if store
            else []
        )
        markers[marker_key] = {
            "category": marker_def.get("category"),
            "name": marker_def.get("name") or marker_def.get("name_de"),
            "unit": marker_def.get("canonical_unit"),
            "ref_min": ref_min,
            "ref_max": ref_max,
            "is_custom": bool(marker_def.get("is_custom")),
            "value": last.get("value") if last else None,
            "ts": last.get("ts") if last else None,
            "in_range": logic.lab_marker_in_range(last.get("value") if last else None, ref_min, ref_max),
            "reported_value": last.get("reported_value") if last else None,
            "reported_unit": last.get("reported_unit") if last else None,
            "report_ref": last.get("report_ref") if last else None,
            "history": [
                {"ts": item.get("ts"), "value": item.get("value")} for item in history_items
            ],
        }

    return {"categories": categories, "markers": markers}
```

Wire it into `build_panel_data` — add a line next to `"wellbeing": _wellbeing_block(data, entry),`:

```python
        "labs": _labs_block(entry, store, now) if active_areas(options).get(AREA_LABS) else {"categories": [], "markers": {}},
```

(`AREA_LABS` needs importing from `.areas` — extend the existing `from .areas import ...` line; `active_areas(options)` is already imported/used elsewhere in this function.)

- [ ] **Step 4: Implement `websocket_add_lab_value`/`websocket_remove_last_lab_value`**

Add the two command-name constants next to `COMMAND_SAVE_MEASUREMENT`:

```python
COMMAND_ADD_LAB_VALUE = "health_o_mat/add_lab_value"
COMMAND_REMOVE_LAST_LAB_VALUE = "health_o_mat/remove_last_lab_value"
```

Add the handlers next to `websocket_save_measurement`:

```python
async def websocket_add_lab_value(hass: HomeAssistant, connection: Any, msg: dict[str, Any]) -> None:
    """`health_o_mat/add_lab_value` → Laborwert erfassen (REQ-HOM-122).

    Fehler (unbekannter Marker, Pflicht-Einheit fehlt, nicht unterstützte
    Einheit) kommen als `connection.send_error` zurück, damit die Card/das
    Panel sie als Karten-Fehlermeldung statt als HA-Service-Toast zeigen
    (§7.1 der Spec) — bewusst NICHT über `hass.services.async_call`.
    """
    entry_id = msg["entry_id"]
    store = _store(hass)
    entry = _runtime_entry(hass, entry_id)
    if store is None or entry is None or not _entry_ready(hass, entry_id):
        _send_entry_error(connection, msg, entry_id)
        return
    options = getattr(entry, "options", None) or {}
    resolved = logic.resolve_lab_marker(msg.get("marker"), options.get(OPTION_LAB_CUSTOM_MARKERS))
    if resolved is None:
        connection.send_error(msg["id"], ERR_INVALID_FORMAT, "unknown_marker")
        return
    marker_key, marker_def = resolved
    raw_unit = msg.get("unit")
    if raw_unit is None and marker_def.get("require_explicit_unit"):
        connection.send_error(msg["id"], ERR_INVALID_FORMAT, "unit_required")
        return
    try:
        value = float(msg["value"])
        canonical_value, canonical_unit = logic.convert_lab_value(marker_def, value, raw_unit)
    except (TypeError, ValueError) as err:
        connection.send_error(msg["id"], ERR_INVALID_FORMAT, str(err) or "invalid_value")
        return
    report_ref = (msg.get("report_ref") or "").strip()[:LAB_REPORT_REF_MAX_LEN] or None
    now = dt_util.now()
    try:
        ts_iso = parse_entry_ts(msg.get("ts"), now) or now.isoformat()
    except ValueError as err:
        connection.send_error(msg["id"], ERR_INVALID_FORMAT, str(err))
        return
    await store.add_lab_reading(
        entry_id,
        ts_iso,
        marker_key,
        canonical_value,
        canonical_unit,
        value,
        raw_unit or canonical_unit,
        report_ref=report_ref,
        created_ts_iso=now.isoformat(),
        actor=user_id_of(connection),
        audit_limit=_audit_limit(hass, entry_id),
    )
    signal_refresh(hass, entry_id)
    connection.send_result(msg["id"])


async def websocket_remove_last_lab_value(
    hass: HomeAssistant, connection: Any, msg: dict[str, Any]
) -> None:
    """`health_o_mat/remove_last_lab_value` → letzten aktiven Wert EINES Markers entfernen."""
    entry_id = msg["entry_id"]
    store = _store(hass)
    entry = _runtime_entry(hass, entry_id)
    if store is None or entry is None or not _entry_ready(hass, entry_id):
        _send_entry_error(connection, msg, entry_id)
        return
    options = getattr(entry, "options", None) or {}
    resolved = logic.resolve_lab_marker(msg.get("marker"), options.get(OPTION_LAB_CUSTOM_MARKERS))
    if resolved is None:
        connection.send_error(msg["id"], ERR_INVALID_FORMAT, "unknown_marker")
        return
    marker_key, _marker_def = resolved
    changed = await store.remove_last_lab_reading(
        entry_id, marker_key, actor=user_id_of(connection), audit_limit=_audit_limit(hass, entry_id)
    )
    if not changed:
        connection.send_error(msg["id"], ERR_INVALID_FORMAT, "no_active_value")
        return
    signal_refresh(hass, entry_id)
    connection.send_result(msg["id"])
```

Register both commands next to `websocket_save_measurement`'s registration (find the explicit `async_register_command` call list mentioned around line 812/859/896 in the existing file and add two siblings, same `_schema(command, extra)` wrapping style):

```python
    websocket_api.async_register_command(
        hass,
        _schema(COMMAND_ADD_LAB_VALUE, {
            vol.Required("marker"): str,
            vol.Required("value"): vol.Coerce(float),
            vol.Optional("unit"): str,
            vol.Optional("ts"): str,
            vol.Optional("report_ref"): str,
        }),
        websocket_add_lab_value,
    )
    websocket_api.async_register_command(
        hass,
        _schema(COMMAND_REMOVE_LAST_LAB_VALUE, {vol.Required("marker"): str}),
        websocket_remove_last_lab_value,
    )
```

(Match the EXACT call shape of the existing registrations around line 812/859/896 — the snippet above shows the logical schema/handler pairing; copy the real wrapping code, e.g. `websocket_api.async_register_command(hass, command, wrapped, _schema(command, extra))` per the grep result from this file's registration block, rather than the simplified form shown here if it differs.)

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_ws_api.py -k req_hom_122 -v`
Expected: all PASS.

- [ ] **Step 6: Full regression check**

Run: `pytest tests/test_ws_api.py -q && ruff check custom_components/health_o_mat/ws_api.py`
Expected: all pass, `ruff` clean.

- [ ] **Step 7: Commit**

```bash
git add custom_components/health_o_mat/ws_api.py tests/test_ws_api.py
git commit -m "feat: add labs block to panel_data and add_lab_value WS command"
```

---

### Task 16: `health-o-mat-panel-base.js` — shared lab rendering helpers

**Files:**
- Modify: `custom_components/health_o_mat/www/health-o-mat-panel-base.js`
- Test: `tests/test_panel_js.py`

**Interfaces:**
- Consumes: nothing new (pure rendering helpers over the `labs` block shape from Task 15).
- Produces: `labBadge(inRange)`, `labReportedSubline(marker)`, `labSparklineHtml(history, opts)`, `labChartHtml(history, opts)`, `labMarkerOptionsHtml(markers, selectedKey)` — exported from `health-o-mat-panel-base.js?v=0.16.0`, consumed by Task 17 (panel tab), Task 18 (overview tile), Task 19 (labs card).

- [ ] **Step 1: Write the failing tests** (append to `tests/test_panel_js.py`)

```python
def test_req_hom_122_panel_base_exports_lab_helpers():
    source = _read_www("health-o-mat-panel-base.js")
    for name in (
        "export function labBadge",
        "export function labReportedSubline",
        "export function labSparklineHtml",
        "export function labChartHtml",
        "export function labMarkerOptionsHtml",
    ):
        assert name in source, name
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_panel_js.py -k req_hom_122_panel_base -v`
Expected: FAIL — `AssertionError`.

- [ ] **Step 3: Implement** — append to `custom_components/health_o_mat/www/health-o-mat-panel-base.js` (near the existing `bpHistoryChartHtml`/`wellbeingChartHtml` section — reuse `escapeHtml`/`t`/`toNumber`, already defined in this file, no new imports)

```javascript
/* ---- Laborwerte (REQ-HOM-122) --------------------------------------------- */

/* ✓ im Referenzbereich, ⚠ außerhalb, – kein Referenzbereich hinterlegt. */
export function labBadge(inRange) {
  if (inRange === true) return `<span class="status good" aria-hidden="true">✓</span>`;
  if (inRange === false) return `<span class="status bad" aria-hidden="true">⚠️</span>`;
  return `<span class="muted" aria-hidden="true">–</span>`;
}

/* Dezente Subzeile "⤷ eingegeben als <reported_value> <reported_unit>" — nur
 * wenn die Eingabe-Einheit von der kanonischen Einheit abweicht (§7.1 der
 * Spec). Entfällt komplett bei Gleichheit, kein Rauschen im Normalfall. */
export function labReportedSubline(marker) {
  if (!marker || marker.reported_unit == null || marker.reported_unit === marker.unit) {
    return "";
  }
  return `<div class="lab-subline muted">↷ ${escapeHtml(
    t("ui_panel_lab_reported_as", "eingegeben als {value} {unit}", {
      value: marker.reported_value,
      unit: marker.reported_unit,
    })
  )}</div>`;
}

/* Kompakte Sparkline (Card): reine SVG-Polyline über die letzten Werte,
 * dasselbe Berechnungsmuster wie der bestehende Wellbeing-/BD-Chart (kein
 * neues Rendering-Konzept, keine Bibliothek). */
export function labSparklineHtml(history, opts) {
  const options = opts || {};
  const points = (Array.isArray(history) ? history : []).filter((p) =>
    Number.isFinite(toNumber(p && p.value, NaN))
  );
  if (points.length < 2) return `<span class="muted">–</span>`;
  const values = points.map((p) => toNumber(p.value, 0));
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const width = options.width || 60;
  const height = options.height || 20;
  const coords = values
    .map((v, i) => {
      const x = (i / (values.length - 1)) * width;
      const y = height - ((v - min) / span) * height;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
  return `<svg class="lab-sparkline" viewBox="0 0 ${width} ${height}" preserveAspectRatio="none" width="${width}" height="${height}">
      <polyline points="${coords}" fill="none" stroke="var(--primary-color)" stroke-width="1.5" />
    </svg>`;
}

/* Vollwertiger SVG-Chart (Panel): Referenzbereich als Band + Werte-Linie,
 * analog zum bestehenden BD-Verlaufsgraph (bpHistoryChartHtml) — Y-Achse
 * = Referenzbereich ± Puffer statt Blutdruck-Kategorien. */
export function labChartHtml(history, opts) {
  const options = opts || {};
  const points = (Array.isArray(history) ? history : []).filter((p) =>
    Number.isFinite(toNumber(p && p.value, NaN))
  );
  const title = options.title ? String(options.title) : "";
  const head = title ? `<div class="card-title">${escapeHtml(title)}</div>` : "";
  if (points.length < 2) {
    return `<div class="card">${head}${messageHtml(
      t("ui_panel_chart_lab_empty", "Noch zu wenige Werte – der Verlauf erscheint ab zwei Messungen."),
      false
    )}</div>`;
  }
  const values = points.map((p) => toNumber(p.value, 0));
  const refMin = Number.isFinite(toNumber(options.refMin, NaN)) ? toNumber(options.refMin, NaN) : null;
  const refMax = Number.isFinite(toNumber(options.refMax, NaN)) ? toNumber(options.refMax, NaN) : null;
  const dataMin = Math.min(...values, refMin != null ? refMin : Infinity);
  const dataMax = Math.max(...values, refMax != null ? refMax : -Infinity);
  const buffer = (dataMax - dataMin || 1) * 0.15;
  const min = dataMin - buffer;
  const max = dataMax + buffer;
  const span = max - min || 1;
  const width = 280;
  const height = 100;
  const toY = (v) => height - ((v - min) / span) * height;
  const coords = values
    .map((v, i) => `${((i / (values.length - 1)) * width).toFixed(1)},${toY(v).toFixed(1)}`)
    .join(" ");
  const band =
    refMin != null && refMax != null
      ? `<rect x="0" y="${toY(refMax).toFixed(1)}" width="${width}" height="${(toY(refMin) - toY(refMax)).toFixed(1)}" fill="var(--primary-color)" opacity="0.1" />`
      : "";
  return `<div class="card">${head}
      <svg class="lab-chart" viewBox="0 0 ${width} ${height}" preserveAspectRatio="none" width="100%" height="${height}">
        ${band}
        <polyline points="${coords}" fill="none" stroke="var(--primary-color)" stroke-width="2" />
      </svg>
    </div>`;
}

/* <option>-Liste für den Marker-Picker im Eingabe-Block (Card/Panel), sortiert
 * nach Kategorie-Reihenfolge wie `labs.categories`, dann Marker-Name. */
export function labMarkerOptionsHtml(markers, selectedKey) {
  const entries = Object.entries(markers || {}).sort(([, a], [, b]) =>
    String(a.name).localeCompare(String(b.name))
  );
  return entries
    .map(
      ([key, marker]) =>
        `<option value="${escapeHtml(key)}"${key === selectedKey ? " selected" : ""}>${escapeHtml(
          marker.name
        )} (${escapeHtml(marker.unit)})</option>`
    )
    .join("");
}
```

Bump the module's own cache-buster-carrying import specifier is NOT needed here (this file is the one being edited; its own internal `?v=` references other modules, not itself) — no change needed in this file for that, but Task 20 will bump the *global* `?v=` cache-buster string across every file's import specifiers when the version is released (existing project convention: all `?v=` suffixes move together).

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_panel_js.py -k req_hom_122_panel_base -v`
Expected: PASS.

- [ ] **Step 5: Full regression check**

Run: `pytest tests/test_panel_js.py -q`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add custom_components/health_o_mat/www/health-o-mat-panel-base.js tests/test_panel_js.py
git commit -m "feat: add shared lab rendering helpers to panel base module"
```

---

### Task 17: `health-o-mat-panel-views.js` — Panel tab "Laborwerte" + category swipe bar

**Files:**
- Modify: `custom_components/health_o_mat/www/health-o-mat-panel-views.js`
- Test: `tests/test_panel_js.py`

**Interfaces:**
- Consumes: `labBadge`, `labReportedSubline`, `labChartHtml`, `labMarkerOptionsHtml` (Task 16), `data.labs` (Task 15), the existing `TABS`/`enabledTabs` pattern from `health-o-mat-panel-base.js`.
- Produces: a 4th entry in the `TABS` constant (`{key: "labs", area: "labs", label: "Laborwerte", labelKey: "ui_panel_tab_labs"}`, in `health-o-mat-panel-base.js` — same file that defines `TABS` today, not `-views.js`); `labsTab(panel, data, entryId)` rendering function wired into `renderDetail`'s `if/else if` chain; `panel._labCategory` state field (per-person active category, mirrors `panel._tab`); swipe handling via `touchstart`/`touchend` delta-X, same vanilla-JS style as the rest of the panel (no gesture library).

- [ ] **Step 1: Write the failing tests** (append to `tests/test_panel_js.py`)

```python
def test_req_hom_122_tabs_include_labs_entry():
    source = _read_www("health-o-mat-panel-base.js")
    assert '"labs"' in source


def test_req_hom_122_panel_views_exports_labs_tab():
    source = _read_www("health-o-mat-panel-views.js")
    assert "function labsTab" in source


def test_req_hom_122_panel_views_renders_category_bar():
    source = _read_www("health-o-mat-panel-views.js")
    assert "lab-category" in source


def test_req_hom_122_panel_views_wires_touch_swipe():
    source = _read_www("health-o-mat-panel-views.js")
    assert "touchstart" in source
    assert "touchend" in source


def test_req_hom_122_panel_views_detail_dispatches_to_labs_tab():
    source = _read_www("health-o-mat-panel-views.js")
    assert 'activeTab === "labs"' in source
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_panel_js.py -k "req_hom_122_tabs or req_hom_122_panel_views" -v`
Expected: FAIL — `AssertionError`.

- [ ] **Step 3: Extend `TABS`** — edit `custom_components/health_o_mat/www/health-o-mat-panel-base.js`. Find the existing `TABS` constant (consumed by `enabledTabs`, grep confirmed it's defined above line 842 in this file) and add a 4th entry, same shape as the existing three:

```javascript
const TABS = [
  { key: "drink", area: "drink", labelKey: "ui_panel_tab_drink", label: "Trinken" },
  { key: "bp", area: "bp", labelKey: "ui_panel_tab_bp", label: "Blutdruck" },
  { key: "wellbeing", area: "wellbeing", labelKey: "ui_panel_tab_wellbeing", label: "Wohlbefinden" },
  { key: "labs", area: "labs", labelKey: "ui_panel_tab_labs", label: "Laborwerte" },
];
```

(Read the EXACT existing `TABS` array literal first via `grep -n "const TABS" -A 6 health-o-mat-panel-base.js` before editing — the snippet above assumes the shown shape; preserve whatever field names the real array already uses and add the 4th entry in the same shape, don't restructure the existing three.)

- [ ] **Step 4: Implement `labsTab` + swipe + dispatch** — edit `custom_components/health_o_mat/www/health-o-mat-panel-views.js`

Extend the top-of-file import from `health-o-mat-panel-base.js`:

```javascript
  labBadge,
  labReportedSubline,
  labChartHtml,
  labMarkerOptionsHtml,
```

Extend `renderDetail`'s dispatch chain (add a branch before the final `else` that renders the "no area active" message):

```javascript
  else if (activeTab === "labs") content = labsTab(panel, data, entryId);
```

Add the new rendering function near the other `*Tab` functions (`bpTab`/`wellbeingTab`/`drinkTab` — follow their exact calling convention: `(panel, data, entryId)`, returning an HTML string):

```javascript
/* ---- Laborwerte-Tab (REQ-HOM-122) ---------------------------------------- */

function visibleLabCategories(labs) {
  return (labs.categories || []).filter((category) => {
    if (category.hidden) return false;
    // Nur Kategorien mit mindestens einem Marker zeigen (Katalog oder Custom).
    return Object.values(labs.markers || {}).some((marker) => marker.category === category.key);
  });
}

function labCategoryBar(panel, labs, activeCategory) {
  const categories = visibleLabCategories(labs);
  if (!categories.length) return "";
  return `<div class="lab-category-bar" role="tablist">
      <button class="btn ghost" type="button" data-action="lab-category-prev" aria-label="${escapeHtml(
        t("ui_panel_lab_prev", "Vorherige Kategorie")
      )}">‹</button>
      ${categories
        .map(
          (category) =>
            `<button class="lab-category${category.key === activeCategory ? " active" : ""}" type="button" data-action="lab-category" data-category="${escapeHtml(
              category.key
            )}" role="tab" aria-selected="${category.key === activeCategory ? "true" : "false"}">${escapeHtml(
              category.name
            )}</button>`
        )
        .join("")}
      <button class="btn ghost" type="button" data-action="lab-category-next" aria-label="${escapeHtml(
        t("ui_panel_lab_next", "Nächste Kategorie")
      )}">›</button>
    </div>`;
}

function labMarkerRow(panel, marker, entryId, markerKey) {
  const value = marker.value == null ? "–" : `${marker.value} ${escapeHtml(marker.unit)}`;
  return `<div class="lab-row">
      <div class="lab-row-main">
        <span class="lab-row-name">${escapeHtml(marker.name)}</span>
        <span class="lab-row-value">${value}</span>
        ${labBadge(marker.in_range)}
      </div>
      ${labReportedSubline(marker)}
      ${labChartHtml(marker.history, {
        title: "",
        refMin: marker.ref_min,
        refMax: marker.ref_max,
      })}
    </div>`;
}

export function labsTab(panel, data, entryId) {
  const labs = data.labs || { categories: [], markers: {} };
  const categories = visibleLabCategories(labs);
  if (!categories.length) {
    return messageHtml(
      t("ui_panel_lab_no_categories", "Keine Laborwert-Kategorie sichtbar."),
      false
    );
  }
  let active = panel._labCategory;
  if (!categories.some((category) => category.key === active)) {
    active = categories[0].key;
  }
  panel._labCategory = active;

  const markersInCategory = Object.entries(labs.markers || {}).filter(
    ([, marker]) => marker.category === active
  );

  const rows = markersInCategory
    .map(([key, marker]) => labMarkerRow(panel, marker, entryId, key))
    .join("");

  const entryForm = `<details class="lab-entry-form">
      <summary>${escapeHtml(t("ui_panel_lab_add_value", "Neuen Wert erfassen"))}</summary>
      <label class="field">${escapeHtml(t("ui_panel_lab_marker", "Marker"))}
        <select data-field="lab-add-marker">${labMarkerOptionsHtml(labs.markers, null)}</select>
      </label>
      <label class="field">${escapeHtml(t("ui_panel_lab_value_field", "Wert"))}
        <input type="number" step="any" data-field="lab-add-value" />
      </label>
      <label class="field">${escapeHtml(t("ui_panel_lab_unit_field", "Einheit (optional)"))}
        <input type="text" data-field="lab-add-unit" />
      </label>
      <label class="field">${escapeHtml(t("ui_panel_lab_report_ref", "Bericht-Link/ID (optional)"))}
        <input type="text" data-field="lab-add-report-ref" />
      </label>
      <button class="btn" type="button" data-action="lab-add-value" data-entry="${escapeHtml(
        entryId
      )}">${escapeHtml(t("ui_panel_lab_save", "Speichern"))}</button>
    </details>`;

  return `${labCategoryBar(panel, labs, active)}<div class="views">${rows}</div>${entryForm}`;
}
```

Add touch-swipe wiring. This panel's shared element already has a `touchstart`/`touchend` (or equivalent click-delegation) listener setup somewhere in `health-o-mat-panel.js` — find that listener-registration section (same place `this.shadowRoot.addEventListener("click", this._onClick)` lives, per the existing code) and add two siblings next to it:

```javascript
this.shadowRoot.addEventListener("touchstart", this._onTouchStart, { passive: true });
this.shadowRoot.addEventListener("touchend", this._onTouchEnd, { passive: true });
```

Add the two handlers + the `lab-category`/`lab-category-prev`/`lab-category-next` click cases in `health-o-mat-panel.js` (same switch block extended in Task 14):

```javascript
_onTouchStart = (ev) => {
  const touch = ev.touches && ev.touches[0];
  this._touchStartX = touch ? touch.clientX : null;
};

_onTouchEnd = (ev) => {
  if (this._touchStartX == null) return;
  const touch = ev.changedTouches && ev.changedTouches[0];
  if (!touch) return;
  const deltaX = touch.clientX - this._touchStartX;
  this._touchStartX = null;
  const SWIPE_THRESHOLD = 40;
  if (Math.abs(deltaX) < SWIPE_THRESHOLD) return;
  // Nur auf dem Laborwerte-Tab aktiv — andere Tabs haben kein Kategorie-Konzept.
  if (this._tab !== "labs") return;
  this._stepLabCategory(deltaX < 0 ? 1 : -1);
};

_stepLabCategory(direction) {
  const entryId = this._selectedEntry;
  const data = this._data[entryId];
  const labs = (data && data.labs) || { categories: [] };
  const categories = (labs.categories || []).filter((c) => !c.hidden);
  if (!categories.length) return;
  const currentIndex = categories.findIndex((c) => c.key === this._labCategory);
  const nextIndex = (currentIndex + direction + categories.length) % categories.length;
  this._labCategory = categories[nextIndex].key;
  this._render();
}
```

Add the click cases:

```javascript
      case "lab-category":
        this._labCategory = el.getAttribute("data-category");
        this._render();
        break;
      case "lab-category-prev":
        this._stepLabCategory(-1);
        break;
      case "lab-category-next":
        this._stepLabCategory(1);
        break;
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_panel_js.py -k "req_hom_122_tabs or req_hom_122_panel_views" -v`
Expected: all PASS.

- [ ] **Step 6: Full regression check**

Run: `pytest tests/test_panel_js.py -q`
Expected: all pass (existing `enabledTabs`/tab tests still green — the 4th `TABS` entry is additive and gated by `areas.labs`, which defaults active, same as the other three areas default active).

- [ ] **Step 7: Manual smoke check** — start the dev stack, open the panel, confirm the "Laborwerte" tab appears, category buttons switch content, and a left/right swipe on a touch device (or emulated touch in devtools) changes category.

- [ ] **Step 8: Commit**

```bash
git add custom_components/health_o_mat/www/health-o-mat-panel-base.js custom_components/health_o_mat/www/health-o-mat-panel-views.js custom_components/health_o_mat/www/health-o-mat-panel.js tests/test_panel_js.py
git commit -m "feat: add labs panel tab with category swipe bar"
```

---

### Task 18: `health-o-mat-panel-views.js` — Overview tile lab-warning row + tile-head badge

**Files:**
- Modify: `custom_components/health_o_mat/www/health-o-mat-panel-views.js`
- Test: `tests/test_panel_js.py`

**Interfaces:**
- Consumes: `data.labs` (Task 15), `areasForPerson` (existing helper).
- Produces: `panel._labWarningCount(data) -> number` (pure, reads already-loaded `panel_data`, no new WS request per §7.3 of the spec); a 4th row in `renderTile`'s tile body; an additive extension of the existing tile-head ⚠-badge tooltip.

- [ ] **Step 1: Write the failing tests** (append to `tests/test_panel_js.py`)

```python
def test_req_hom_122_panel_views_exports_lab_warning_count():
    source = _read_www("health-o-mat-panel-views.js")
    assert "_labWarningCount" in source


def test_req_hom_122_panel_views_tile_shows_lab_row():
    source = _read_www("health-o-mat-panel-views.js")
    assert "lab-row-tile" in source or "\\U0001F9EA" in source or "🧪" in source


def test_req_hom_122_panel_views_tile_head_badge_mentions_lab():
    source = _read_www("health-o-mat-panel-views.js")
    assert "ui_panel_lab_threshold_title" in source
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_panel_js.py -k req_hom_122_panel_views_tile -v`
Expected: FAIL — `AssertionError`.

- [ ] **Step 3: Implement** — edit `custom_components/health_o_mat/www/health-o-mat-panel-views.js`

Add the pure counter function near `renderTile` (private helper, not exported — matches the file's existing convention of unexported helpers like `tabButton`):

```javascript
/* Zahl der Marker außerhalb des Referenzbereichs über alle SICHTBAREN
 * Kategorien (lab_hidden_categories ausgenommen) — reine Darstellungslogik
 * auf bereits geladenen panel_data-Attributen, kein Extra-Request (§7.3). */
function labWarningCount(data) {
  const labs = (data && data.labs) || { categories: [], markers: {} };
  const hiddenCategories = new Set(
    (labs.categories || []).filter((c) => c.hidden).map((c) => c.key)
  );
  return Object.values(labs.markers || {}).filter(
    (marker) => !hiddenCategories.has(marker.category) && marker.in_range === false
  ).length;
}
```

Extend `renderTile` — add a `labRow` next to the existing `wbRow` definition:

```javascript
  const labCount = areas.labs ? labWarningCount(data) : 0;
  const labRow = areas.labs
    ? `<div class="tile-row"><span class="em" aria-hidden="true">\u{1F9EA}</span><span>${
        labCount > 0
          ? escapeHtml(
              t("ui_panel_tile_lab_warning", "{count} Marker außerhalb Referenz", { count: labCount })
            )
          : escapeHtml(t("ui_panel_tile_lab_ok", "Alles im Bereich"))
      }</span>${labCount > 0 ? `<span class="muted">· ⚠️</span>` : ""}</div>`
    : "";
```

Add `${labRow}` to the returned tile HTML, right after `${wbRow}`:

```javascript
      ${drinkSection}
      ${bpRow}
      ${wbRow}
      ${labRow}
    </button>`;
```

Extend the tile-head ⚠-badge — find the existing `warn` boolean and its badge span (`const warn = areas.bp ? panel._isWarning(data) : false;` and the `${warn ? ...}` badge in the returned template) and make the tooltip additive:

```javascript
  const warn = areas.bp ? panel._isWarning(data) : false;
  const labWarn = labCount > 0;
  const warnTitleParts = [];
  if (warn) {
    warnTitleParts.push(t("ui_panel_bp_threshold_title", "Blutdruck oberhalb der Schwellen"));
  }
  if (labWarn) {
    warnTitleParts.push(
      t("ui_panel_lab_threshold_title", "{count} Laborwerte außerhalb Referenz", { count: labCount })
    );
  }
```

Replace the existing single-condition badge span with one driven by `warn || labWarn`, joining the tooltip parts (same single-icon rule as the spec: one ⚠ badge, tooltip lists both causes if both apply):

```javascript
        ${warn || labWarn ? `<span class="status bad" title="${escapeHtml(
          warnTitleParts.join("; ")
        )}">⚠️</span>` : ""}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_panel_js.py -k req_hom_122_panel_views_tile -v`
Expected: all PASS.

- [ ] **Step 5: Full regression check**

Run: `pytest tests/test_panel_js.py -q`
Expected: all pass (existing BP-only tile-head badge tests must still pass unmodified — the badge condition is additive via `||`, never removes the existing `warn`-only case).

- [ ] **Step 6: Manual smoke check** — a person with a lab value out of range shows the 🧪 row and the ⚠ badge with a combined tooltip when BD is also over threshold.

- [ ] **Step 7: Commit**

```bash
git add custom_components/health_o_mat/www/health-o-mat-panel-views.js tests/test_panel_js.py
git commit -m "feat: add lab warning row and tile-head badge to overview tile"
```

---

### Task 19: new `health-o-mat-labs-card.js` — standalone Lovelace card

**Files:**
- Create: `custom_components/health_o_mat/www/health-o-mat-labs-card.js`
- Test: `tests/test_card_js.py` (or a new `tests/test_labs_card_js.py` mirroring its static-source-assertion style — check which file the existing `health-o-mat-card.js` tests live in and follow that exact file/naming convention)

**Interfaces:**
- Consumes: `labBadge`, `labReportedSubline`, `labSparklineHtml`, `labMarkerOptionsHtml` — these live in `health-o-mat-panel-base.js`, which is a **Panel-internal** module; the Lovelace card is a **separate, standalone custom element** loaded directly by Lovelace (not through the panel's module graph) — per the spec (§7.1: "Eigene, neue Custom-Card … Folgt denselben Grundmustern wie die bestehende Card … kein externes Chart-Framework") the card must NOT import from the panel's module path (Lovelace cards are sandboxed per-dashboard and HA does not guarantee the panel's static path is loaded in every dashboard context). The card therefore defines its own small, self-contained copies of `labBadge`/`labReportedSubline`/a sparkline helper — same ~15-line functions as Task 16, duplicated intentionally (ponytail: a shared-module import across the Card/Panel boundary would need a THIRD shared file just for ~3 one-line functions used in 2 places each — not worth the indirection; the existing `health-o-mat-card.js` already duplicates its own wellbeing-chart logic rather than importing from the panel for the same reason — verify this by checking whether `health-o-mat-card.js` imports anything from `health-o-mat-panel-base.js`; if it does, import from there instead of duplicating).
- Produces: custom element `health-o-mat-labs-card` (tag name registered via `customElements.define`), plus `HealthOMatLabsCardEditor` (visual editor), calling the WS commands `health_o_mat/add_lab_value` (Task 15) directly via `hass.connection.sendMessagePromise` (same call style as the existing card's `book_drink`/`save_measurement` calls — reuse that exact pattern, do not call `hass.callService`, per the spec §7.1 "nicht den Service direkt, damit UI-Fehler als Karten-Fehlermeldung … erscheinen").

- [ ] **Step 1: Write the failing tests** — create (or extend) the test file, following this repo's exact existing JS-source-assertion style (confirm by reading 2-3 existing tests in `tests/test_card_js.py` first):

```python
def test_req_hom_122_labs_card_file_exists_and_defines_custom_element():
    source = _read_www("health-o-mat-labs-card.js")
    assert 'customElements.define("health-o-mat-labs-card"' in source


def test_req_hom_122_labs_card_defines_editor():
    source = _read_www("health-o-mat-labs-card.js")
    assert "class HealthOMatLabsCardEditor" in source


def test_req_hom_122_labs_card_supports_person_mode_and_filter():
    source = _read_www("health-o-mat-labs-card.js")
    assert "person_mode" in source
    assert "person_filter" in source
    assert "default_person" in source


def test_req_hom_122_labs_card_calls_ws_not_service():
    source = _read_www("health-o-mat-labs-card.js")
    assert "sendMessagePromise" in source
    assert "callService" not in source


def test_req_hom_122_labs_card_has_disclaimer_flag():
    source = _read_www("health-o-mat-labs-card.js")
    assert "show_disclaimer" in source


def test_req_hom_122_labs_card_editor_schema_has_five_keys():
    """entry_id/person_mode-family aside, show_categories/show_trend/allow_manual_entry/show_disclaimer (§7.1 editor table)."""
    source = _read_www("health-o-mat-labs-card.js")
    for key in ("show_categories", "show_trend", "allow_manual_entry", "show_disclaimer"):
        assert key in source, key
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_card_js.py -k req_hom_122_labs_card -v`
Expected: FAIL — file doesn't exist / `_read_www` raises `FileNotFoundError`.

- [ ] **Step 3: Implement** — create `custom_components/health_o_mat/www/health-o-mat-labs-card.js`. Structure it as a minimal, self-contained custom element following the EXACT skeleton of the existing `health-o-mat-card.js`'s `HealthOMatCard`/`HealthOMatCardEditor` classes (same `setConfig`/`getStubConfig`/`getConfigElement`/`set hass`/shadow-DOM-render-on-property-set pattern — read that file's class bodies around lines 966-1150 and 2680-2700 immediately before writing this file, and copy the lifecycle methods verbatim, replacing only the config schema and render body):

```javascript
/**
 * Health-O-Mat — Laborwerte Lovelace card (REQ-HOM-122).
 *
 * Standalone custom card, same base patterns as health-o-mat-card.js
 * (person_mode/person_filter/default_person, ?v= cache-buster, HA CSS
 * variables, no external chart library) — kept separate per the spec
 * (§7.1): the existing card already has nine show_* flags, a tenth
 * subject area would overload its editor.
 */

const CARD_VERSION = "0.16.0";

function escapeHtml(value) {
  return String(value == null ? "" : value).replace(/[&<>"']/g, (ch) => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch]
  ));
}

function labBadge(inRange) {
  if (inRange === true) return `<span class="status good">✓</span>`;
  if (inRange === false) return `<span class="status bad">⚠️</span>`;
  return `<span class="muted">–</span>`;
}

function labReportedSubline(marker) {
  if (!marker || marker.reported_unit == null || marker.reported_unit === marker.unit) return "";
  return `<div class="lab-subline muted">↷ eingegeben als ${escapeHtml(marker.reported_value)} ${escapeHtml(
    marker.reported_unit
  )}</div>`;
}

function labSparkline(history) {
  const points = (Array.isArray(history) ? history : []).filter((p) => Number.isFinite(Number(p && p.value)));
  if (points.length < 2) return `<span class="muted">–</span>`;
  const values = points.map((p) => Number(p.value));
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const w = 60;
  const h = 20;
  const coords = values
    .map((v, i) => `${((i / (values.length - 1)) * w).toFixed(1)},${(h - ((v - min) / span) * h).toFixed(1)}`)
    .join(" ");
  return `<svg viewBox="0 0 ${w} ${h}" width="${w}" height="${h}"><polyline points="${coords}" fill="none" stroke="var(--primary-color)" stroke-width="1.5" /></svg>`;
}

class HealthOMatLabsCard extends HTMLElement {
  static getStubConfig() {
    return { entry_id: "", show_trend: true, allow_manual_entry: true, show_disclaimer: true };
  }

  setConfig(config) {
    if (!config || typeof config !== "object") {
      throw new Error("Invalid configuration");
    }
    this._config = { ...config };
    this._render();
  }

  static getConfigElement() {
    return document.createElement("health-o-mat-labs-card-editor");
  }

  set hass(hass) {
    this._hass = hass;
    this._render();
  }

  getCardSize() {
    return 4;
  }

  connectedCallback() {
    if (!this.shadowRoot) this.attachShadow({ mode: "open" });
    this.shadowRoot.addEventListener("click", this._onClick);
  }

  disconnectedCallback() {
    if (this.shadowRoot) this.shadowRoot.removeEventListener("click", this._onClick);
  }

  _resolveEntryId() {
    if (this._config.entry_id) return this._config.entry_id;
    if (!this._hass) return null;
    const entries = Object.keys(this._hass.states).filter((id) =>
      id.startsWith("sensor.") && id.includes("_lab_")
    );
    return entries.length ? entries[0].split(".")[1].split("_lab_")[0] : null;
  }

  _panelData() {
    // Re-uses the same subscription channel the panel uses; a minimal card
    // reads live entity attributes directly instead of re-implementing the
    // WS subscription (kept intentionally simple — ponytail).
    return this._hass && this._hass.states ? this._hass.states : {};
  }

  _onClick = (ev) => {
    const el = ev.target.closest("[data-action]");
    if (!el) return;
    const action = el.getAttribute("data-action");
    if (action === "lab-save") this._saveValue();
  };

  async _saveValue() {
    const markerEl = this.shadowRoot.querySelector('[data-field="lab-marker"]');
    const valueEl = this.shadowRoot.querySelector('[data-field="lab-value"]');
    const unitEl = this.shadowRoot.querySelector('[data-field="lab-unit"]');
    const refEl = this.shadowRoot.querySelector('[data-field="lab-report-ref"]');
    const entryId = this._resolveEntryId();
    if (!entryId || !markerEl || !valueEl) return;
    const payload = {
      type: "health_o_mat/add_lab_value",
      entry_id: entryId,
      marker: markerEl.value,
      value: Number(valueEl.value),
    };
    if (unitEl && unitEl.value) payload.unit = unitEl.value;
    if (refEl && refEl.value) payload.report_ref = refEl.value;
    try {
      await this._hass.connection.sendMessagePromise(payload);
      this._error = null;
    } catch (err) {
      this._error = (err && err.message) || String(err);
    }
    this._render();
  }

  _render() {
    if (!this.shadowRoot || !this._config) return;
    const disclaimer = this._config.show_disclaimer !== false
      ? `<div class="banner">⚠️ Hinweis: keine medizinische Beratung – Richtwerte, keine Diagnose.</div>`
      : "";
    const errorBanner = this._error
      ? `<div class="banner error">⚠️ ${escapeHtml(this._error)}</div>`
      : "";
    const entryForm = this._config.allow_manual_entry !== false
      ? `<div class="entry-form">
          <select data-field="lab-marker"></select>
          <input type="number" step="any" data-field="lab-value" placeholder="Wert" />
          <input type="text" data-field="lab-unit" placeholder="Einheit" />
          <input type="text" data-field="lab-report-ref" placeholder="Bericht-Link/ID" />
          <button data-action="lab-save">Speichern</button>
        </div>`
      : "";
    this.shadowRoot.innerHTML = `
      <style>
        :host { display: block; }
        .card { padding: 16px; background: var(--ha-card-background, var(--card-background-color)); border-radius: var(--ha-card-border-radius, 12px); }
        .banner { padding: 8px; margin-bottom: 8px; border-radius: 8px; background: var(--warning-color, #ff9800); color: #fff; }
        .banner.error { background: var(--error-color, #db4437); }
        .status.good { color: var(--success-color, green); }
        .status.bad { color: var(--error-color, red); }
        .muted { color: var(--secondary-text-color); }
      </style>
      <div class="card">
        ${disclaimer}
        ${errorBanner}
        <div class="lab-rows"></div>
        ${entryForm}
      </div>
    `;
  }
}

class HealthOMatLabsCardEditor extends HTMLElement {
  setConfig(config) {
    this._config = { ...config };
    this._render();
  }

  connectedCallback() {
    if (!this.shadowRoot) this.attachShadow({ mode: "open" });
    this.shadowRoot.addEventListener("change", this._onChange);
    this._render();
  }

  _onChange = (ev) => {
    const el = ev.target.closest("[data-key]");
    if (!el) return;
    const key = el.getAttribute("data-key");
    const next = { ...this._config };
    if (el.type === "checkbox") next[key] = el.checked;
    else next[key] = el.value;
    this._config = next;
    this.dispatchEvent(new CustomEvent("config-changed", { detail: { config: next } }));
  };

  _render() {
    if (!this.shadowRoot) return;
    const c = this._config || {};
    this.shadowRoot.innerHTML = `
      <div>
        <label>Entry-ID <input data-key="entry_id" value="${escapeHtml(c.entry_id || "")}" /></label>
        <label>Personen-Modus
          <select data-key="person_mode">
            <option value="fixed" ${c.person_mode === "fixed" ? "selected" : ""}>Fest</option>
            <option value="selector" ${c.person_mode === "selector" ? "selected" : ""}>Auswahl</option>
          </select>
        </label>
        <label>Default-Person <input data-key="default_person" value="${escapeHtml(c.default_person || "")}" /></label>
        <label><input type="checkbox" data-key="show_trend" ${c.show_trend !== false ? "checked" : ""} /> Sparkline anzeigen</label>
        <label><input type="checkbox" data-key="allow_manual_entry" ${c.allow_manual_entry !== false ? "checked" : ""} /> Manuelle Eingabe erlauben</label>
        <label><input type="checkbox" data-key="show_disclaimer" ${c.show_disclaimer !== false ? "checked" : ""} /> Medizin-Hinweis anzeigen</label>
      </div>
    `;
  }
}

customElements.define("health-o-mat-labs-card", HealthOMatLabsCard);
customElements.define("health-o-mat-labs-card-editor", HealthOMatLabsCardEditor);

window.customCards = window.customCards || [];
window.customCards.push({
  type: "health-o-mat-labs-card",
  name: "Health-O-Mat Laborwerte",
  description: "Laborwerte (Blutwerte) je Person, kategorisiert mit Referenzbereichen.",
});
```

(`person_filter`/`show_categories` config keys from the editor table in §7.1 of the spec are read directly off `this._config` in `_render()`/`_resolveEntryId()` exactly like `person_mode`/`default_person` above — the skeleton here covers the lifecycle and WS-write path precisely; the full multi-person selector dropdown and category-tab rendering inside `_render()` should be copied from the equivalent logic in `health-o-mat-card.js`'s `HealthOMatCard._render()`/`HealthOMatCardEditor._render()` — same `person_mode`/`person_filter` resolution code, same dropdown markup — rather than re-derived from scratch, per this repo's "follow existing patterns" convention.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_card_js.py -k req_hom_122_labs_card -v`
Expected: all PASS.

- [ ] **Step 5: Manual smoke check** — add the card to a test dashboard via YAML (`type: custom:health-o-mat-labs-card`), confirm it renders without console errors and the manual-entry form calls `add_lab_value` successfully.

- [ ] **Step 6: Commit**

```bash
git add custom_components/health_o_mat/www/health-o-mat-labs-card.js tests/test_card_js.py
git commit -m "feat: add standalone Lovelace card for lab values"
```

---

### Task 20: `frontend.py` — register the second card file as a Lovelace resource

**Files:**
- Modify: `custom_components/health_o_mat/frontend.py`
- Test: `tests/test_frontend.py`

**Interfaces:**
- Consumes: `versioned_url` (existing), `WWW_DIR`/`URL_BASE` (existing, unchanged — both cards share the same static path).
- Produces: `LABS_CARD_FILENAME = "health-o-mat-labs-card.js"`, `LABS_CARD_BASE_URL`, `LABS_CARD_URL`; `_async_register_card_resource` generalized to register BOTH card files (ponytail: exactly 2 cards exist — generalize the existing single-card functions to take a `(filename, url, base_url, marker_suffix)` tuple and loop over a 2-item list, rather than inventing a plugin registry for a fixed pair).

- [ ] **Step 1: Write the failing tests** (append to `tests/test_frontend.py` — check the file's existing style for how `_async_register_lovelace_resource`/`_async_register_card_resource` are tested with a fake `hass`/Lovelace-resources mock, and follow it exactly)

```python
def test_req_hom_122_labs_card_url_is_versioned():
    from custom_components.health_o_mat import frontend

    assert frontend.LABS_CARD_URL.startswith(f"{frontend.URL_BASE}/{frontend.LABS_CARD_FILENAME}?v=")


async def test_req_hom_122_setup_frontend_registers_both_card_resources(hass):
    """Reuse this file's existing `async_setup_frontend` test fixture/mock Lovelace resources."""
    from custom_components.health_o_mat import frontend

    # Build the same fake Lovelace-resources mock the existing
    # `test_async_setup_frontend_registers_card` (or equivalent) test uses,
    # then assert BOTH urls were created:
    # created_urls = [item["url"] for item in resources.async_create_item.call_args_list ...]
    # assert any(frontend.CARD_URL == u for u in created_urls)
    # assert any(frontend.LABS_CARD_URL == u for u in created_urls)
    pass  # replaced with the file's real fixture pattern when implementing
```

(The second test above is a placeholder for the SHAPE of the assertion only — per the "No Placeholders" rule this must be filled in with the file's real fixture before being committed; read `tests/test_frontend.py`'s existing `async_setup_frontend`/Lovelace-mock test in full immediately before writing this step, copy its exact mock construction, and assert on both `CARD_URL` and `LABS_CARD_URL` instead of leaving a `pass` body.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_frontend.py -k req_hom_122 -v`
Expected: FAIL — `AttributeError: module 'frontend' has no attribute 'LABS_CARD_URL'`.

- [ ] **Step 3: Implement** — edit `custom_components/health_o_mat/frontend.py`

Add the filename/URL constants next to the existing `CARD_FILENAME`/`CARD_URL`:

```python
CARD_FILENAME = "health-o-mat-card.js"
LABS_CARD_FILENAME = "health-o-mat-labs-card.js"

# ...

CARD_BASE_URL = f"{URL_BASE}/{CARD_FILENAME}"
CARD_URL = versioned_url(CARD_FILENAME)
LABS_CARD_BASE_URL = f"{URL_BASE}/{LABS_CARD_FILENAME}"
LABS_CARD_URL = versioned_url(LABS_CARD_FILENAME)

# Beide Cards teilen sich EINEN Registrierungsweg (Marker-Namen bleiben wie
# gehabt, jetzt als Liste statt Einzelwert).
_CARDS: tuple[tuple[str, str, str], ...] = (
    (CARD_FILENAME, CARD_BASE_URL, CARD_URL),
    (LABS_CARD_FILENAME, LABS_CARD_BASE_URL, LABS_CARD_URL),
)
```

Generalize `_async_register_card_resource` to loop over `_CARDS` instead of handling only one card (replace the single-card body):

```python
async def _async_register_card_resource(hass: HomeAssistant, shared: dict[str, Any]) -> None:
    """Beide Cards als Lovelace-Ressource anlegen, sonst `add_extra_js_url` als Fallback."""
    if shared.get(_CARD_MARKER):
        return
    method = _METHOD_LOVELACE
    for _filename, base_url, url in _CARDS:
        if await _async_register_lovelace_resource(hass, base_url, url):
            continue
        if _add_extra_js_url(hass, url):
            method = _METHOD_EXTRA_JS
        else:
            method = None
    if method is not None:
        shared[_CARD_MARKER] = method
```

Generalize `_async_register_lovelace_resource`, `_async_refresh_card_resource_url`, `_is_card_resource`, and `_add_extra_js_url` to take `base_url`/`url` as parameters instead of reading the module-level `CARD_BASE_URL`/`CARD_URL` constants directly (mechanical refactor — same bodies, parameterized):

```python
async def _async_register_lovelace_resource(hass: HomeAssistant, base_url: str, url: str) -> bool:
    try:
        from homeassistant.components.lovelace.const import LOVELACE_DATA
    except ImportError:  # pragma: no cover - Lovelace ist HA-Kernbestandteil
        return False

    resources = getattr(hass.data.get(LOVELACE_DATA), "resources", None)
    if resources is None or not hasattr(resources, "async_create_item"):
        return False
    try:
        if not getattr(resources, "loaded", True):
            await resources.async_load()
            resources.loaded = True
        items = resources.async_items() or []
        existing = next((item for item in items if _is_card_resource(item, base_url)), None)
        if existing is not None:
            await _async_refresh_card_resource_url(resources, existing, url)
            return True
        await resources.async_create_item({"res_type": "module", "url": url})
    except Exception:  # noqa: BLE001 - Lovelace/Dashboard-Storage ist optional
        _LOGGER.exception("Health-O-Mat: Lovelace-Ressource %s nicht anlegbar", url)
        return False
    return True


async def _async_refresh_card_resource_url(resources: Any, item: Any, url: str) -> None:
    if item.get("url") == url:
        return
    update = getattr(resources, "async_update_item", None)
    item_id = item.get("id")
    if update is None or item_id is None:
        return
    try:
        await update(item_id, {"url": url})
    except Exception:  # noqa: BLE001 - Ressourcen-Storage variiert je HA-Version
        _LOGGER.debug("Health-O-Mat: Lovelace-Ressource %s nicht aktualisierbar", item_id)


def _is_card_resource(item: Any, base_url: str) -> bool:
    if not isinstance(item, dict):
        return False
    url = item.get("url")
    if not isinstance(url, str):
        return False
    return url.split("?", 1)[0].rstrip("/") == base_url


def _add_extra_js_url(hass: HomeAssistant, url: str) -> bool:
    if add_extra_js_url is None:
        return False
    try:
        add_extra_js_url(hass, url)
    except Exception:  # noqa: BLE001 - Frontend nicht (oder anders) initialisiert
        _LOGGER.warning("Health-O-Mat: Custom-Card %s konnte nicht als Extra-JS registriert werden", url)
        return False
    return True
```

Update `async_unregister_frontend` to remove the fallback for both cards if the `extra_js` method was used:

```python
async def async_unregister_frontend(hass: HomeAssistant) -> None:
    shared = shared_data(hass)
    if shared.get(_CARD_MARKER) != _METHOD_EXTRA_JS:
        return
    if remove_extra_js_url is not None:
        for _filename, _base_url, url in _CARDS:
            try:
                remove_extra_js_url(hass, url)
            except Exception:  # noqa: BLE001 - HA-internes Datenformat, nie unload-kritisch
                _LOGGER.debug("Health-O-Mat: Extra-JS-URL %s war nicht registriert", url)
    shared.pop(_CARD_MARKER, None)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_frontend.py -q`
Expected: all pass (existing single-card tests must still pass against the generalized code — if any existing test asserts on the now-renamed private function signatures, e.g. calls `_is_card_resource(item)` with one arg, update those call sites to pass `CARD_BASE_URL` explicitly).

- [ ] **Step 5: Full regression check**

Run: `pytest tests/test_frontend.py -q && ruff check custom_components/health_o_mat/frontend.py`
Expected: all pass, `ruff` clean.

- [ ] **Step 6: Commit**

```bash
git add custom_components/health_o_mat/frontend.py tests/test_frontend.py
git commit -m "feat: register the labs card as a second Lovelace resource"
```

---

### Task 21: Common UI strings for all new lab-values JS text

**Files:**
- Modify: `custom_components/health_o_mat/strings.json`, `custom_components/health_o_mat/translations/de.json`, `custom_components/health_o_mat/translations/en.json`
- Test: `tests/test_translations.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: every `"ui_*"` key referenced via `t("ui_...", "<German fallback>")` calls added in Tasks 14/16/17/18/19, added under the existing top-level `"common"` key in all three files (confirmed via `python3 -c "import json; print(list(json.load(open('strings.json')).keys()))"` → `['config', 'options', 'entity', 'services', 'common']`).

- [ ] **Step 1: Write the failing test** (append to `tests/test_translations.py`)

```python
_REQ_HOM_122_UI_KEYS = [
    "ui_admin_lab_title", "ui_admin_lab_ref_title", "ui_admin_lab_category", "ui_admin_lab_marker",
    "ui_admin_lab_unit", "ui_admin_lab_range", "ui_admin_lab_reset", "ui_admin_lab_hide_title",
    "ui_admin_lab_custom_title", "ui_admin_lab_custom_name", "ui_admin_lab_custom_unit",
    "ui_admin_lab_custom_category", "ui_admin_lab_custom_range", "ui_admin_lab_custom_alt_unit",
    "ui_admin_lab_custom_alt_unit_name", "ui_admin_lab_custom_alt_factor", "ui_admin_lab_custom_submit",
    "ui_admin_lab_feedback",
    "ui_panel_lab_reported_as", "ui_panel_chart_lab_empty",
    "ui_panel_tab_labs", "ui_panel_lab_prev", "ui_panel_lab_next", "ui_panel_lab_no_categories",
    "ui_panel_lab_add_value", "ui_panel_lab_marker", "ui_panel_lab_value_field",
    "ui_panel_lab_unit_field", "ui_panel_lab_report_ref", "ui_panel_lab_save",
    "ui_panel_tile_lab_warning", "ui_panel_tile_lab_ok", "ui_panel_lab_threshold_title",
]


def test_req_hom_122_common_ui_keys_exist_in_all_three_files():
    import json
    from pathlib import Path

    base = Path(__file__).parent.parent / "custom_components" / "health_o_mat"
    strings = json.loads((base / "strings.json").read_text(encoding="utf-8"))
    de = json.loads((base / "translations" / "de.json").read_text(encoding="utf-8"))
    en = json.loads((base / "translations" / "en.json").read_text(encoding="utf-8"))

    for key in _REQ_HOM_122_UI_KEYS:
        assert key in strings.get("common", {}), f"strings.json missing {key}"
        assert key in de.get("common", {}), f"de.json missing {key}"
        assert key in en.get("common", {}), f"en.json missing {key}"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_translations.py -k req_hom_122_common -v`
Expected: FAIL — `AssertionError: strings.json missing ui_admin_lab_title`.

- [ ] **Step 3: Implement** — add to the `"common"` object in all three files. German text (for `translations/de.json`, and reused as the `t()` fallback argument already written into the JS in Tasks 14/16/17/18/19) and English text (for `strings.json` + `translations/en.json`):

```json
"ui_admin_lab_title": "Laborwerte" / "Lab values",
"ui_admin_lab_ref_title": "Referenzbereiche anpassen" / "Adjust reference ranges",
"ui_admin_lab_category": "Kategorie" / "Category",
"ui_admin_lab_marker": "Marker" / "Marker",
"ui_admin_lab_unit": "Einheit" / "Unit",
"ui_admin_lab_range": "Referenz" / "Reference",
"ui_admin_lab_reset": "Auf Katalog-Default zurücksetzen" / "Reset to catalog default",
"ui_admin_lab_hide_title": "Kategorien ausblenden" / "Hide categories",
"ui_admin_lab_custom_title": "Eigene Marker" / "Custom markers",
"ui_admin_lab_custom_name": "Name" / "Name",
"ui_admin_lab_custom_unit": "Einheit" / "Unit",
"ui_admin_lab_custom_category": "Kategorie" / "Category",
"ui_admin_lab_custom_range": "Referenz" / "Reference",
"ui_admin_lab_custom_alt_unit": "Alternative Einheit (optional)" / "Alternative unit (optional)",
"ui_admin_lab_custom_alt_unit_name": "Einheit" / "Unit",
"ui_admin_lab_custom_alt_factor": "Faktor → Haupteinheit" / "Factor → main unit",
"ui_admin_lab_custom_submit": "+ Hinzufügen" / "+ Add",
"ui_admin_lab_feedback": "Fehlt eine Kategorie oder ein Marker? Vorschlag/Feedback auf GitHub" / "Missing a category or marker? Suggest it on GitHub",
"ui_panel_lab_reported_as": "eingegeben als {value} {unit}" / "entered as {value} {unit}",
"ui_panel_chart_lab_empty": "Noch zu wenige Werte – der Verlauf erscheint ab zwei Messungen." / "Not enough values yet – the chart appears after two measurements.",
"ui_panel_tab_labs": "Laborwerte" / "Lab values",
"ui_panel_lab_prev": "Vorherige Kategorie" / "Previous category",
"ui_panel_lab_next": "Nächste Kategorie" / "Next category",
"ui_panel_lab_no_categories": "Keine Laborwert-Kategorie sichtbar." / "No lab value category visible.",
"ui_panel_lab_add_value": "Neuen Wert erfassen" / "Record new value",
"ui_panel_lab_marker": "Marker" / "Marker",
"ui_panel_lab_value_field": "Wert" / "Value",
"ui_panel_lab_unit_field": "Einheit (optional)" / "Unit (optional)",
"ui_panel_lab_report_ref": "Bericht-Link/ID (optional)" / "Report link/ID (optional)",
"ui_panel_lab_save": "Speichern" / "Save",
"ui_panel_tile_lab_warning": "{count} Marker außerhalb Referenz" / "{count} markers outside reference",
"ui_panel_tile_lab_ok": "Alles im Bereich" / "All within range",
"ui_panel_lab_threshold_title": "{count} Laborwerte außerhalb Referenz" / "{count} lab values outside reference"
```

Write these as proper `"key": "value"` JSON entries (the `de / en` slash notation above is this plan's shorthand, not literal JSON — split each line into the German value for `de.json` and the English value for both `strings.json` and `en.json`, matching every other key already in the `"common"` object).

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_translations.py -k req_hom_122_common -v`
Expected: PASS.

- [ ] **Step 5: Full regression check**

Run: `pytest tests/test_translations.py -q`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add custom_components/health_o_mat/strings.json custom_components/health_o_mat/translations/de.json custom_components/health_o_mat/translations/en.json tests/test_translations.py
git commit -m "feat: add common UI strings for lab values"
```

---

## Wave 6 — Backup/Export/Import

### Task 22: `backup.py` — lab readings + lab options in the backup document

**Files:**
- Modify: `custom_components/health_o_mat/backup.py`
- Test: `tests/test_report.py` (or wherever `build_backup_document`/`async_backup` are currently tested — check first; `tests/test_report.py`'s name suggests it covers backup/report document shape)

**Interfaces:**
- Consumes: `store.raw_data()` (already includes `lab_readings[]` per-entry since Task 4 made it a sibling of `drinks`/`readings` — no store-side change needed here), `hass.config_entries.async_entries(DOMAIN)` (new: `async_backup` now also reads each entry's `entry.options` for the three lab option keys, since those live outside the store).
- Produces: `build_backup_document(raw_data, created, archive_data=None, lab_options=None) -> dict` gains a `lab_options: dict[entry_id, {"lab_custom_markers": [...], "lab_ref_overrides": {...}, "lab_hidden_categories": [...]}]` top-level key (empty dict per entry if not provided — backward compatible, additive); `_entry_counts` gains a `"lab_readings"` count block. `async_backup(hass, store, archive_store=None)` now also collects `lab_options` from `hass.config_entries.async_entries(DOMAIN)` before calling `build_backup_document`. `BACKUP_VERSION` bumped `2` → `3`.

- [ ] **Step 1: Write the failing tests** (append to `tests/test_report.py` — read its existing `build_backup_document` tests first for the exact fixture shape used for `raw_data`/`archive_data`, then mirror it)

```python
def test_req_hom_122_backup_document_includes_lab_readings_counts():
    from custom_components.health_o_mat.backup import build_backup_document
    from datetime import datetime

    raw_data = {
        "schema": 5,
        "entries": {
            "e1": {
                "person": "Caro",
                "drinks": [], "readings": [], "wellbeing_entries": [],
                "lab_readings": [
                    {"marker_key": "alt", "value": 32.0, "voided_at": None},
                    {"marker_key": "ast", "value": 20.0, "voided_at": "2026-10-30T00:00:00"},
                ],
            }
        },
    }
    doc = build_backup_document(raw_data, datetime(2026, 10, 31))
    assert doc["counts"]["e1"]["lab_readings"] == {"total": 2, "active": 1, "voided": 1}


def test_req_hom_122_backup_document_includes_lab_options():
    from custom_components.health_o_mat.backup import build_backup_document
    from datetime import datetime

    raw_data = {"schema": 5, "entries": {"e1": {"drinks": [], "readings": []}}}
    lab_options = {
        "e1": {
            "lab_custom_markers": [{"key": "vitamin_d", "name": "Vitamin D", "category": "other", "unit": "ng/mL"}],
            "lab_ref_overrides": {"alt": {"ref_min": 5}},
            "lab_hidden_categories": ["thyroid"],
        }
    }
    doc = build_backup_document(raw_data, datetime(2026, 10, 31), lab_options=lab_options)
    assert doc["lab_options"] == lab_options


def test_req_hom_122_backup_document_lab_options_default_empty():
    from custom_components.health_o_mat.backup import build_backup_document
    from datetime import datetime

    doc = build_backup_document({"schema": 5, "entries": {}}, datetime(2026, 10, 31))
    assert doc["lab_options"] == {}


def test_req_hom_122_backup_version_bumped_to_3():
    from custom_components.health_o_mat import backup

    assert backup.BACKUP_VERSION == 3
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_report.py -k req_hom_122 -v`
Expected: FAIL — `KeyError: 'lab_options'` / `AssertionError: 2 != 3`.

- [ ] **Step 3: Implement** — edit `custom_components/health_o_mat/backup.py`

```python
BACKUP_VERSION = 3
```

Extend `_entry_counts` — add a line next to the existing `"readings"` entry:

```python
    return {
        "drinks": _list_counts(data.get("drinks")),
        "readings": _list_counts(data.get("readings")),
        "wellbeing": wellbeing,
        "lab_readings": _list_counts(data.get("lab_readings")),
    }
```

Extend `build_backup_document`'s signature and return value:

```python
def build_backup_document(
    raw_data: dict,
    created: datetime,
    archive_data: dict | None = None,
    lab_options: dict | None = None,
) -> dict:
    """... (docstring: extend the existing "v2 ergänzt" bullet list with:)

    v3 ergänzt (additiv):
    - ``counts[entry_id]["lab_readings"]``: wie die übrigen Datensatz-Zähler.
    - ``lab_options``: ``{entry_id: {lab_custom_markers, lab_ref_overrides,
      lab_hidden_categories}}`` — liegt in ``entry.options``, nicht im Store,
      deshalb als separater Parameter statt aus ``raw_data`` abgeleitet.
    """
    entries = raw_data.get("entries", {}) if isinstance(raw_data, dict) else {}
    persons: dict[str, Any] = {}
    counts: dict[str, Any] = {}
    for entry_id, entry in entries.items():
        data = entry if isinstance(entry, dict) else {}
        persons[str(entry_id)] = data.get("person") or ""
        counts[str(entry_id)] = _entry_counts(data)
    archive_entries = archive_data.get("entries", {}) if isinstance(archive_data, dict) else {}
    return {
        "format": BACKUP_FORMAT,
        "version": BACKUP_VERSION,
        "schema": raw_data.get("schema") if isinstance(raw_data, dict) else None,
        "created": created.isoformat(),
        "persons": persons,
        "counts": counts,
        "entries": copy.deepcopy(entries),
        "archive_schema": (archive_data.get("schema") if isinstance(archive_data, dict) else None),
        "archive_counts": _archive_counts(archive_data),
        "archive_entries": copy.deepcopy(archive_entries),
        "lab_options": copy.deepcopy(lab_options) if isinstance(lab_options, dict) else {},
    }
```

Extend `async_backup` to collect `lab_options` from the live config entries (the one place in this flow that has `hass` and therefore `hass.config_entries`):

```python
async def async_backup(
    hass: HomeAssistant,
    store: HealthOMatStore,
    archive_store: HealthOMatStore | None = None,
) -> str:
    if store is None:
        raise ServiceValidationError("Health-O-Mat-Speicher nicht verfügbar")

    now = dt_util.now()
    lab_options = {
        entry.entry_id: {
            "lab_custom_markers": entry.options.get("lab_custom_markers", []),
            "lab_ref_overrides": entry.options.get("lab_ref_overrides", {}),
            "lab_hidden_categories": entry.options.get("lab_hidden_categories", []),
        }
        for entry in hass.config_entries.async_entries(DOMAIN)
    }
    document = build_backup_document(
        store.raw_data(),
        now,
        archive_store.raw_data() if archive_store is not None else None,
        lab_options=lab_options,
    )
    path = await async_write_backup_document(hass, document, prefix="backup")

    await hass.services.async_call(
        "persistent_notification",
        "create",
        {"title": "HA Health-O-Mat Backup", "message": f"Backup geschrieben:\n{path}"},
        blocking=False,
    )
    return path
```

Add the `DOMAIN` import (`from .const import DOMAIN` — `backup.py` currently doesn't import it; check first, it may already be imported for another reason).

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_report.py -k req_hom_122 -v`
Expected: all PASS.

- [ ] **Step 5: Full regression check**

Run: `pytest tests/test_report.py -q && ruff check custom_components/health_o_mat/backup.py`
Expected: all pass — existing backup tests must tolerate the new `lab_options` key appearing in the document (additive field, no existing assertion should do an exact-dict-equality check against the whole document; if one does, update it to account for the new key rather than removing the new key).

- [ ] **Step 6: Commit**

```bash
git add custom_components/health_o_mat/backup.py tests/test_report.py
git commit -m "feat: include lab readings and lab options in backup v3"
```

---

### Task 23: `restore.py` — `lab_values` dataset wiring + custom-marker merge validation

**Files:**
- Modify: `custom_components/health_o_mat/restore.py`
- Test: `tests/test_restore.py`

**Interfaces:**
- Consumes: `logic.resolve_lab_marker`, `logic.normalize_lab_custom_markers` (Task 2), `backup.build_backup_document`'s `lab_options` key (Task 22), the existing `DATASETS`/`DATASET_LIST`/`_DATASET_ALIASES`/`_dedup_key`/`plan_restore`/`RestorePlan` structures already confirmed in this file (lines ~60-76, ~304-317, ~533-710 — read the real surrounding code immediately before editing, this task's snippets below show the exact additions, not full-file rewrites).
- Produces: `DATASETS` gains `"lab_values"`; `DATASET_LIST["lab_values"] = "lab_readings"`; `_DATASET_ALIASES["lab_values"] = "lab_values"` (and `"lab_readings": "lab_values"` as a tolerant alias, same pattern as `"readings"`/`"blood_pressure"`); `_dedup_key` gains a `"lab_values"` branch (`(ts, marker_key, value)`, per spec §8); two new HA-free functions `merge_lab_custom_markers(current: list[dict], incoming: list[dict]) -> list[dict]` and `unknown_lab_marker_keys(records: list[dict], custom_markers: list[dict]) -> list[str]`; `plan_restore(...)` gains an optional `lab_options: dict[str, dict] | None = None` parameter (the backup document's `lab_options`, keyed by SOURCE entry_id) and a `RestorePlan.lab_custom_markers_by_target: dict[str, list[dict]]` field; `apply_restore`/`async_restore_from_file` additionally call `hass.config_entries.async_update_entry(target_entry, options={**target_entry.options, "lab_custom_markers": merged})` per target after the store save succeeds.

- [ ] **Step 1: Write the failing tests** (append to `tests/test_restore.py` — read 2-3 of the file's existing `plan_restore`/`_dedup_key` tests first for the exact `RestorePlan`/document fixture shape, then mirror it)

```python
def test_req_hom_122_dedup_key_lab_values_uses_ts_marker_value():
    from custom_components.health_o_mat.restore import _dedup_key

    record = {"ts": "2026-10-31T09:00:00", "marker_key": "alt", "value": 32.0}
    assert _dedup_key("lab_values", record) == ("2026-10-31T09:00:00", "alt", 32.0)


def test_req_hom_122_lab_values_in_datasets_and_dataset_list():
    from custom_components.health_o_mat import restore

    assert "lab_values" in restore.DATASETS
    assert restore.DATASET_LIST["lab_values"] == "lab_readings"


def test_req_hom_122_dataset_alias_lab_readings_resolves_to_lab_values():
    from custom_components.health_o_mat.restore import _normalize_datasets

    assert _normalize_datasets(["lab_readings"]) == ("lab_values",)


def test_req_hom_122_merge_lab_custom_markers_appends_new_keys():
    from custom_components.health_o_mat.restore import merge_lab_custom_markers

    current = [{"key": "vitamin_d", "name": "Vitamin D", "category": "other", "unit": "ng/mL"}]
    incoming = [{"key": "ferritin", "name": "Ferritin", "category": "other", "unit": "µg/L"}]
    merged = merge_lab_custom_markers(current, incoming)
    assert {m["key"] for m in merged} == {"vitamin_d", "ferritin"}


def test_req_hom_122_merge_lab_custom_markers_keeps_existing_definition_on_key_clash():
    """Merge semantics (REQ-HOM-116): existing wins, no silent overwrite."""
    from custom_components.health_o_mat.restore import merge_lab_custom_markers

    current = [{"key": "vitamin_d", "name": "Vitamin D (eigene Def.)", "category": "other", "unit": "ng/mL"}]
    incoming = [{"key": "vitamin_d", "name": "Vitamin D (Backup-Def.)", "category": "other", "unit": "nmol/L"}]
    merged = merge_lab_custom_markers(current, incoming)
    assert len(merged) == 1
    assert merged[0]["name"] == "Vitamin D (eigene Def.)"


def test_req_hom_122_unknown_lab_marker_keys_flags_missing_marker():
    from custom_components.health_o_mat.restore import unknown_lab_marker_keys

    records = [{"marker_key": "alt"}, {"marker_key": "not_a_marker"}]
    assert unknown_lab_marker_keys(records, []) == ["not_a_marker"]


def test_req_hom_122_unknown_lab_marker_keys_accepts_merged_custom_marker():
    from custom_components.health_o_mat.restore import unknown_lab_marker_keys

    records = [{"marker_key": "vitamin_d"}]
    custom = [{"key": "vitamin_d", "name": "Vitamin D", "category": "other", "unit": "ng/mL"}]
    assert unknown_lab_marker_keys(records, custom) == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_restore.py -k req_hom_122 -v`
Expected: FAIL — `AttributeError`/`KeyError`.

- [ ] **Step 3: Implement the dataset wiring** — edit `custom_components/health_o_mat/restore.py`

```python
DATASETS: tuple[str, ...] = ("drinks", "blood_pressure", "wellbeing", "lab_values")
DATASET_LIST: dict[str, str] = {
    "drinks": "drinks",
    "blood_pressure": "readings",
    "wellbeing": "wellbeing_entries",
    "lab_values": "lab_readings",
}
_DATASET_ALIASES: dict[str, str] = {
    "drink": "drinks",
    "drinks": "drinks",
    "readings": "blood_pressure",
    "reading": "blood_pressure",
    "blood_pressure": "blood_pressure",
    "wellbeing": "wellbeing",
    "wellbeing_entries": "wellbeing",
    "lab_values": "lab_values",
    "lab_readings": "lab_values",
    "lab_value": "lab_values",
}
```

Extend `_dedup_key` — add a branch next to the existing `if dataset == "wellbeing":` branch:

```python
def _dedup_key(dataset: str, record: dict) -> tuple | None:
    ts = _iso(record.get("ts"))
    if ts is None:
        return None
    if dataset == "drinks":
        return (ts, _int(record.get("ml")), str(record.get("type") or ""))
    if dataset == "blood_pressure":
        return (ts, _int(record.get("sys")), _int(record.get("dia")))
    if dataset == "wellbeing":
        return (ts, str(record.get("key") or ""))
    if dataset == "lab_values":
        return (ts, str(record.get("marker_key") or ""), record.get("value"))
    return None
```

(Confirm the EXACT existing body of `_dedup_key` via `grep -n "_dedup_key" -A 15 restore.py` before editing — the snippet above assumes the shown branches; add the `lab_values` branch alongside them without altering the others.)

- [ ] **Step 4: Implement the custom-marker merge + validation helpers** — add near `_normalize_record`/`_is_active` (same HA-free section of the file):

```python
def merge_lab_custom_markers(current: list[dict], incoming: list[dict]) -> list[dict]:
    """Custom-Marker-Definitionen beim Restore mergen (REQ-HOM-122, §8).

    Merge-Semantik wie der Rest des Restore (Duplikate überspringen): ein
    bereits vorhandener `key` gewinnt — ein Backup überschreibt NIE eine
    lokal schon existierende Custom-Marker-Definition, es ergänzt nur fehlende.
    """
    from .logic import normalize_lab_custom_markers

    normalized_current = normalize_lab_custom_markers(current)
    existing_keys = {marker["key"] for marker in normalized_current}
    merged = list(normalized_current)
    for marker in normalize_lab_custom_markers(incoming):
        if marker["key"] not in existing_keys:
            merged.append(marker)
            existing_keys.add(marker["key"])
    return merged


def unknown_lab_marker_keys(records: list[dict], custom_markers: list[dict]) -> list[str]:
    """`marker_key`s ohne Treffer in Katalog ODER den (gemergten) Custom-Markern.

    Läuft NACH dem Custom-Marker-Merge (`merge_lab_custom_markers`) — ein
    Restore auf eine leere/andere Installation bringt die Marker-Definition
    gleich mit, sonst würde dieselbe Prüfung grundlos fehlschlagen (§8 der Spec).
    """
    from .logic import resolve_lab_marker

    unknown = []
    for record in records:
        marker_key = record.get("marker_key")
        if resolve_lab_marker(marker_key, custom_markers) is None:
            unknown.append(str(marker_key))
    return unknown
```

- [ ] **Step 5: Wire `lab_options` through `plan_restore` + validation**

Read `plan_restore`'s current full signature and the `RestorePlan` dataclass definition (`grep -n "class RestorePlan" -A 20 restore.py` and `grep -n "^def plan_restore" -A 50 restore.py`) immediately before this step — then:

- Add `lab_options: dict[str, dict] | None = None` as a new keyword parameter of `plan_restore`, and `current_lab_custom_markers: dict[str, list[dict]] | None = None` (target entry_id → that entry's CURRENT `lab_custom_markers`, supplied by the caller since `plan_restore` itself has no `hass` access).
- Add a field `lab_custom_markers_by_target: dict[str, list[dict]] = field(default_factory=dict)` to `RestorePlan`.
- Inside the existing per-target, per-dataset loop (the `for dataset in chosen:` block around line 626), when `dataset == "lab_values"`: before preparing/deduping records for that target, compute the merged custom markers ONCE per target (`plan.lab_custom_markers_by_target.setdefault(target, merge_lab_custom_markers(current_lab_custom_markers.get(target, []) if current_lab_custom_markers else [], lab_options.get(source_id, {}).get("lab_custom_markers", []) if lab_options else []))`), then call `unknown_lab_marker_keys(records, plan.lab_custom_markers_by_target[target])` — any unknown key appends to `plan.warnings` (same style as the existing `plan.warnings.append(f"{dataset}: ungültiger Eintrag in Quelle {source_id}")` line) AND that record is skipped (not written) rather than raising, consistent with this file's existing "warn + skip" convention for malformed records (do NOT abort the whole restore for one bad row — the existing pattern for the sibling case already does per-record skip-with-warning).

- [ ] **Step 6: Wire the options write-back into the apply path**

Find `apply_restore`/`async_restore_from_file` (the HA-touching functions that call `store.async_set_entries(...)` after planning) and add, immediately after the store save succeeds, one `hass.config_entries.async_update_entry` call per target entry that has a non-empty `plan.lab_custom_markers_by_target[target]`:

```python
    for target_entry_id, merged_markers in plan.lab_custom_markers_by_target.items():
        if not merged_markers:
            continue
        target_entry = hass.config_entries.async_get_entry(target_entry_id)
        if target_entry is None:
            continue
        hass.config_entries.async_update_entry(
            target_entry,
            options={**target_entry.options, "lab_custom_markers": merged_markers},
        )
```

(Place this loop at the exact point in `apply_restore` where other post-save side effects already happen — e.g. next to wherever `signal_refresh` is called per target after a successful save; read that function's tail before inserting.)

- [ ] **Step 7: Run tests to verify they pass**

Run: `pytest tests/test_restore.py -k req_hom_122 -v`
Expected: all PASS.

- [ ] **Step 8: Full regression check**

Run: `pytest tests/test_restore.py -q && ruff check custom_components/health_o_mat/restore.py`
Expected: all pass (existing 3-dataset restore tests unaffected — `lab_values` is a 4th, additive dataset; a restore call that doesn't mention `datasets` at all now also includes `lab_values` by default via `chosen = selected_datasets or DATASETS`, matching how the 3 existing datasets already behave without an explicit filter).

- [ ] **Step 9: Commit**

```bash
git add custom_components/health_o_mat/restore.py tests/test_restore.py
git commit -m "feat: restore lab readings and merge custom marker definitions"
```

---

### Task 24: `exporter.py` — `lab_values.csv` export

**Files:**
- Modify: `custom_components/health_o_mat/exporter.py`, `custom_components/health_o_mat/services.yaml`, `custom_components/health_o_mat/strings.json`, `custom_components/health_o_mat/translations/de.json`, `custom_components/health_o_mat/translations/en.json`
- Test: `tests/test_report.py` (or wherever `async_export_csv` is tested today — check first)

**Interfaces:**
- Consumes: `store.active_lab_readings(entry_id)` (Task 4), `logic.effective_lab_markers` (Task 2), existing `csv_filename`/`rows_to_csv_string` from `logic.py`.
- Produces: a 4th `export_csv` `dataset` selector option `"lab_values"` (label "Laborwerte"); `lab_values.csv` written per person when `dataset in ("lab_values", "all")`, header `zeitstempel, person, marker, kategorie, wert, einheit, eingegeben_als_wert, eingegeben_als_einheit, berichts_referenz`.

- [ ] **Step 1: Write the failing tests** (append to the file that already tests `async_export_csv` — reuse its exact `hass`/`store`/`call` fixture construction)

```python
def test_req_hom_122_export_csv_writes_lab_values_file(tmp_path):
    """Reuse the existing async_export_csv test fixture (fake hass.config.path -> tmp_path,
    fake store with active_drinks/active_readings/active_lab_readings, fake call.data)."""
    import asyncio
    from unittest.mock import MagicMock
    from custom_components.health_o_mat.exporter import async_export_csv

    store = MagicMock()
    store.all_entries.return_value = {"e1": {"person": "Caro"}}
    store.active_drinks.return_value = []
    store.active_readings.return_value = []
    store.active_lab_readings.return_value = [
        {
            "ts": "2026-10-31T09:00:00+01:00", "marker_key": "alt", "value": 32.0, "unit": "U/L",
            "reported_value": 32.0, "reported_unit": "U/L", "report_ref": "https://example.com/x",
        }
    ]
    hass = MagicMock()
    hass.config.path.return_value = str(tmp_path)
    hass.async_add_executor_job = lambda fn: fn()
    hass.services.async_call = MagicMock()
    call = MagicMock()
    call.data = {"person": "", "dataset": "lab_values"}

    path = asyncio.new_event_loop().run_until_complete(async_export_csv(hass, store, call))

    written = list(tmp_path.glob("*lab*"))
    assert written, "no lab_values CSV written"
    content = written[0].read_text(encoding="utf-8-sig")
    assert "alt" in content
    assert "32.0" in content
    assert "https://example.com/x" in content
```

(Adjust the fixture construction to exactly match whatever helper/mock shape the file's EXISTING `async_export_csv` tests already use for `hass.config.path`/`store`/`call` — read 1-2 of those tests first; the mock shown here is a best-effort reconstruction from `exporter.py`'s real signature, not a guaranteed match to this repo's actual fixture helper names.)

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_report.py -k req_hom_122_export -v`
Expected: FAIL — no file matching `*lab*` written (dataset `"lab_values"` falls through both existing `if` branches today, since `exporter.py` only knows `"drinks"`/`"blood_pressure"`/`"all"`).

- [ ] **Step 3: Implement** — edit `custom_components/health_o_mat/exporter.py`

Extend `_combined` to also gather lab readings:

```python
    def _combined(eid: str) -> tuple[list, list, list]:
        """Aktive Getränke/Readings/Laborwerte des Haupt-Stores + Archiv je Person."""
        drinks = list(store.active_drinks(eid))
        readings = list(store.active_readings(eid))
        lab_readings = list(store.active_lab_readings(eid))
        if archive_store is not None and eid in archive_store.all_entries():
            drinks += list(archive_store.active_drinks(eid))
            readings += list(archive_store.active_readings(eid))
            # Das Retention-Archiv kennt (aktuell) keine Laborwerte — Labs sind
            # additiv zum bestehenden Archiv-Konzept, kein rückwirkender Umbau.
        return drinks, readings, lab_readings
```

Update the call site inside `_write_files` (`drinks, readings = _combined(eid)` → `drinks, readings, lab_readings = _combined(eid)`), and add a third dataset branch next to the existing two:

```python
            if dataset in ("lab_values", "all"):
                markers = logic.effective_lab_markers(None)  # Katalog-Kategorien für die CSV-Spalte
                rows = [
                    [
                        "zeitstempel", "person", "marker", "kategorie", "wert", "einheit",
                        "eingegeben_als_wert", "eingegeben_als_einheit", "berichts_referenz",
                    ]
                ]
                for r in sorted(lab_readings, key=lambda x: x.get("ts", "")):
                    marker_key = r.get("marker_key", "")
                    category = (markers.get(marker_key) or {}).get("category", "")
                    rows.append(
                        [
                            r.get("ts", ""),
                            person,
                            marker_key,
                            category,
                            str(r.get("value", "")),
                            r.get("unit", ""),
                            str(r.get("reported_value", "")),
                            r.get("reported_unit", ""),
                            r.get("report_ref") or "",
                        ]
                    )
                name = csv_filename("labvalues", person, now)
                path = os.path.join(export_dir, name)
                with open(path, "w", encoding="utf-8-sig", newline="") as f:
                    buf = ";".join(rows[0]) + "\n"
                    for row in rows[1:]:
                        buf += ";".join(str(c) for c in row) + "\n"
                    f.write(buf)
                written.append(path)
```

(`logic.effective_lab_markers(None)` is called WITHOUT the person's custom markers here — this gives only catalog categories for the CSV's `kategorie` column. If a custom marker's category lookup is wanted too, pass the person's `lab_custom_markers` from `data.get("lab_custom_markers")`... but custom markers live in `entry.options`, not the store `data` dict read here (`data = store.all_entries()[eid]`) — `exporter.py` only has `hass`/`store`/`call`, not `entry.options`, exactly the same gap Task 22 hit for backup. Resolve it the same way: accept the custom markers for the current person via an optional parameter threaded in from the service/WS caller (`__init__.py`'s `export_csv` handler already has `entry_id`/`entry.options` available before calling `async_export_csv` — pass `lab_custom_markers_by_entry: dict[str, list] | None = None` through and use `logic.effective_lab_markers(lab_custom_markers_by_entry.get(eid) if lab_custom_markers_by_entry else None)` per person instead of `None`). Wire this exactly as Task 22 wired `lab_options` into `async_backup` — same shape of fix, same reason (options live outside the store).)

Add `from . import logic` to `exporter.py`'s imports (it currently only imports specific names from `.logic` — add the module import alongside, or add `effective_lab_markers` to the existing `from .logic import (...)` line).

Add the 4th selector option to `services.yaml`'s `export_csv` service (find the existing `dataset` selector under `export_csv` and add a sibling option):

```yaml
            - label: Laborwerte
              value: "lab_values"
```

Add the matching English override to `strings.json`'s `services.export_csv.fields.dataset` (check whether this field already has a translation entry — if not, this is the first one needed and should mirror the existing `void_entry`/`restore_entry` `kind` field's translation shape) and mirror into `translations/de.json`/`en.json`.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_report.py -k req_hom_122_export -v`
Expected: PASS.

- [ ] **Step 5: Full regression check**

Run: `pytest tests/test_report.py -q && ruff check custom_components/health_o_mat/exporter.py`
Expected: all pass, `ruff` clean.

- [ ] **Step 6: Commit**

```bash
git add custom_components/health_o_mat/exporter.py custom_components/health_o_mat/services.yaml custom_components/health_o_mat/strings.json custom_components/health_o_mat/translations/de.json custom_components/health_o_mat/translations/en.json tests/test_report.py
git commit -m "feat: add lab_values.csv to CSV export"
```

---

### Task 25: `importer.py` — `lab_values.csv` detection, parsing, dedup, rejection

**Files:**
- Modify: `custom_components/health_o_mat/importer.py`, `custom_components/health_o_mat/services.yaml` (`import_csv`'s `dataset` selector gains the `lab_values` option, same as Task 24 did for `export_csv`)
- Test: `tests/test_parser.py` or `tests/test_import_backup.py` (check which file currently hosts `plan_import`/`_parse_reading_row`-style tests and add there — `tests/test_import_backup.py`'s name suggests it's the one)

**Interfaces:**
- Consumes: `logic.resolve_lab_marker` (Task 2), existing `_norm_ts`, `_to_int`, `NO_TYPE_LABEL`-style helpers in this file.
- Produces: `_parse_lab_row(cells: list[str]) -> dict | str`; `_existing_lab_keys(existing: list[dict]) -> set[tuple]`; `ImportPlan.lab_readings: list[dict]` (new field, counted in `imported`); `plan_import(..., existing_lab_readings=None, lab_custom_markers=None)` gains a `"lab_values"` branch; `async_import_csv` calls `store.add_lab_reading` for each planned lab record.

- [ ] **Step 1: Write the failing tests** (append to `tests/test_import_backup.py` — check its existing imports/fixtures for `plan_import`/`ImportPlan` first)

```python
def test_req_hom_122_parse_lab_row_valid():
    from custom_components.health_o_mat.importer import _parse_lab_row

    record = _parse_lab_row(
        ["2026-10-31T09:00:00", "Caro", "alt", "liver", "32.0", "U/L", "32.0", "U/L", ""]
    )
    assert record["ts"] == "2026-10-31T09:00:00"
    assert record["marker_raw"] == "alt"
    assert record["value"] == 32.0
    assert record["unit"] == "U/L"
    assert record["reported_value"] == 32.0
    assert record["reported_unit"] == "U/L"
    assert record["report_ref"] is None


def test_req_hom_122_parse_lab_row_keeps_report_ref():
    from custom_components.health_o_mat.importer import _parse_lab_row

    record = _parse_lab_row(
        ["2026-10-31T09:00:00", "Caro", "alt", "liver", "32.0", "U/L", "32.0", "U/L", "https://x"]
    )
    assert record["report_ref"] == "https://x"


def test_req_hom_122_parse_lab_row_invalid_timestamp_returns_error_string():
    from custom_components.health_o_mat.importer import _parse_lab_row

    result = _parse_lab_row(["not-a-ts", "Caro", "alt", "liver", "32.0", "U/L", "32.0", "U/L", ""])
    assert isinstance(result, str)


def test_req_hom_122_parse_lab_row_invalid_value_returns_error_string():
    from custom_components.health_o_mat.importer import _parse_lab_row

    result = _parse_lab_row(
        ["2026-10-31T09:00:00", "Caro", "alt", "liver", "not-a-number", "U/L", "", "", ""]
    )
    assert isinstance(result, str)


def test_req_hom_122_plan_import_lab_values_happy_path():
    from custom_components.health_o_mat.importer import plan_import

    text = (
        "zeitstempel;person;marker;kategorie;wert;einheit;eingegeben_als_wert;eingegeben_als_einheit;berichts_referenz\n"
        "2026-10-31T09:00:00;Caro;alt;liver;32.0;U/L;32.0;U/L;\n"
    )
    plan = plan_import(text, "lab_values", existing_lab_readings=[], lab_custom_markers=[])
    assert len(plan.lab_readings) == 1
    assert plan.lab_readings[0]["marker_key"] == "alt"
    assert plan.rejected == 0


def test_req_hom_122_plan_import_lab_values_resolves_alias():
    from custom_components.health_o_mat.importer import plan_import

    text = (
        "zeitstempel;person;marker;kategorie;wert;einheit;eingegeben_als_wert;eingegeben_als_einheit;berichts_referenz\n"
        "2026-10-31T09:00:00;Caro;gpt;liver;32.0;U/L;32.0;U/L;\n"
    )
    plan = plan_import(text, "lab_values", existing_lab_readings=[], lab_custom_markers=[])
    assert plan.lab_readings[0]["marker_key"] == "alt"


def test_req_hom_122_plan_import_lab_values_rejects_unknown_marker_without_auto_create():
    from custom_components.health_o_mat.importer import plan_import

    text = (
        "zeitstempel;person;marker;kategorie;wert;einheit;eingegeben_als_wert;eingegeben_als_einheit;berichts_referenz\n"
        "2026-10-31T09:00:00;Caro;not_a_marker;other;1;x;1;x;\n"
    )
    plan = plan_import(text, "lab_values", existing_lab_readings=[], lab_custom_markers=[])
    assert plan.lab_readings == []
    assert plan.rejected == 1


def test_req_hom_122_plan_import_lab_values_dedup_by_ts_marker_value():
    from custom_components.health_o_mat.importer import plan_import

    text = (
        "zeitstempel;person;marker;kategorie;wert;einheit;eingegeben_als_wert;eingegeben_als_einheit;berichts_referenz\n"
        "2026-10-31T09:00:00;Caro;alt;liver;32.0;U/L;32.0;U/L;\n"
    )
    existing = [{"ts": "2026-10-31T09:00:00", "marker_key": "alt", "value": 32.0}]
    plan = plan_import(text, "lab_values", existing_lab_readings=existing, lab_custom_markers=[])
    assert plan.lab_readings == []
    assert plan.skipped == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_import_backup.py -k req_hom_122 -v`
Expected: FAIL — `ImportError: cannot import name '_parse_lab_row'`.

- [ ] **Step 3: Implement** — edit `custom_components/health_o_mat/importer.py`

Add the row parser next to `_parse_reading_row`:

```python
def _parse_lab_row(cells: list[str]) -> dict | str:
    """Laborwert-Zeile → Record-Dict (noch unaufgelöster `marker_raw`) oder Fehlermeldung.

    Spalten (siehe `exporter.py`, Task 24): zeitstempel, person, marker,
    kategorie, wert, einheit, eingegeben_als_wert, eingegeben_als_einheit,
    berichts_referenz. Die Marker-Auflösung (Alias/Katalog/Custom) passiert
    erst in `plan_import` — diese Funktion bleibt reine Zeilen-Validierung,
    analog zu `_parse_drink_row`/`_parse_reading_row`.
    """
    if len(cells) < 6:
        return f"Laborwert-Zeile mit zu wenigen Spalten: {';'.join(cells)}"
    ts = _norm_ts(cells[0])
    if ts is None:
        return f"Ungültiger Zeitstempel: {cells[0]!r}"
    marker_raw = cells[2].strip()
    if not marker_raw:
        return f"Laborwert-Zeile ohne Marker: {';'.join(cells)}"
    try:
        value = float(cells[4].strip().replace(",", "."))
    except ValueError:
        return f"Ungültiger Laborwert: {cells[4]!r}"
    unit = cells[5].strip()
    reported_value = value
    if len(cells) > 6 and cells[6].strip():
        try:
            reported_value = float(cells[6].strip().replace(",", "."))
        except ValueError:
            return f"Ungültiger eingegebener Wert: {cells[6]!r}"
    reported_unit = cells[7].strip() if len(cells) > 7 and cells[7].strip() else unit
    report_ref = cells[8].strip() if len(cells) > 8 and cells[8].strip() else None
    return {
        "ts": ts,
        "marker_raw": marker_raw,
        "value": value,
        "unit": unit,
        "reported_value": reported_value,
        "reported_unit": reported_unit,
        "report_ref": report_ref,
    }
```

Add the dedup-key helper next to `_existing_reading_keys`:

```python
def _existing_lab_keys(existing: list[dict]) -> set[tuple[str, str, float]]:
    """`(ts, marker_key, value)` — dieselbe Dedup-Logik wie `restore.py`s `_dedup_key`."""
    keys: set[tuple[str, str, float]] = set()
    for item in existing:
        if not isinstance(item, dict):
            continue
        ts = _norm_ts(item.get("ts")) or str(item.get("ts"))
        try:
            keys.add((ts, str(item.get("marker_key") or ""), float(item.get("value", 0))))
        except (TypeError, ValueError):
            continue
    return keys
```

Extend `ImportPlan`:

```python
@dataclass
class ImportPlan:
    drinks: list[dict] = field(default_factory=list)
    readings: list[dict] = field(default_factory=list)
    lab_readings: list[dict] = field(default_factory=list)
    skipped: int = 0
    rejected: int = 0
    errors: list[str] = field(default_factory=list)

    @property
    def imported(self) -> int:
        return len(self.drinks) + len(self.readings) + len(self.lab_readings)
```

Extend `plan_import`'s signature and add the `"lab_values"` branch:

```python
def plan_import(
    text: str,
    dataset: str,
    existing_drinks: list[dict] | None = None,
    existing_readings: list[dict] | None = None,
    existing_lab_readings: list[dict] | None = None,
    lab_custom_markers: list[dict] | None = None,
) -> ImportPlan:
    rows, header_kind = parse_csv_text(text)
    resolved = dataset
    if dataset == "all":
        resolved = header_kind or _detect_kind(rows)

    plan = ImportPlan()
    if resolved == "lab_values":
        from .logic import resolve_lab_marker

        seen = _existing_lab_keys(existing_lab_readings or [])
        for cells in rows:
            record = _parse_lab_row(cells)
            if isinstance(record, str):
                plan.rejected += 1
                plan.errors.append(record)
                continue
            resolved_marker = resolve_lab_marker(record["marker_raw"], lab_custom_markers)
            if resolved_marker is None:
                plan.rejected += 1
                plan.errors.append(f"Unbekannter Marker: {record['marker_raw']!r}")
                continue
            marker_key, _marker_def = resolved_marker
            record["marker_key"] = marker_key
            del record["marker_raw"]
            key = (record["ts"], marker_key, record["value"])
            if key in seen:
                plan.skipped += 1
                continue
            seen.add(key)
            plan.lab_readings.append(record)
    elif resolved == "blood_pressure":
        # ... (unchanged — existing branch stays exactly as-is)
```

(Keep the existing `blood_pressure`/else-`drinks` branches byte-for-byte as they are today — only the new `if resolved == "lab_values":` branch is inserted, as the FIRST branch checked, with the existing two renumbered to `elif`/`else` without changing their bodies.)

- [ ] **Step 4: Wire the apply path in `async_import_csv`**

```python
    plan = plan_import(
        text,
        dataset,
        entry.get("drinks", []),
        entry.get("readings", []),
        existing_lab_readings=entry.get("lab_readings", []),
        lab_custom_markers=entry_options_lab_custom_markers,  # see note below
    )
```

(`entry_options_lab_custom_markers` needs the calling person's `entry.options["lab_custom_markers"]` — `async_import_csv` currently only receives `store`/`entry_id`/`call`, not the config entry itself. Resolve exactly like Task 22/24 did: have the `import_csv` service handler in `__init__.py` fetch `entry.options.get("lab_custom_markers")` via the existing `_entry_options` helper from Task 8 and pass it through as a new `lab_custom_markers: list | None = None` parameter of `async_import_csv`.)

Add the write-back loop next to the existing `for reading in plan.readings:` loop:

```python
    for lab_reading in plan.lab_readings:
        await store.add_lab_reading(
            entry_id,
            lab_reading["ts"],
            lab_reading["marker_key"],
            lab_reading["value"],
            lab_reading["unit"],
            lab_reading["reported_value"],
            lab_reading["reported_unit"],
            report_ref=lab_reading["report_ref"],
            audit_limit=audit_limit,
        )
```

Add the selector option to `services.yaml`'s `import_csv` `dataset` field (mirror Task 24's `export_csv` addition exactly):

```yaml
            - label: Laborwerte
              value: "lab_values"
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_import_backup.py -k req_hom_122 -v`
Expected: all PASS.

- [ ] **Step 6: Full regression check**

Run: `pytest tests/ -q && ruff check custom_components/health_o_mat/importer.py custom_components/health_o_mat/__init__.py`
Expected: all pass, `ruff` clean.

- [ ] **Step 7: Commit**

```bash
git add custom_components/health_o_mat/importer.py custom_components/health_o_mat/__init__.py custom_components/health_o_mat/services.yaml tests/test_import_backup.py
git commit -m "feat: add lab_values.csv detection, parsing, and dedup to CSV import"
```

---

## Wave 7 — Docs + E2E

### Task 26: `docs/REQUIREMENTS.md` — REQ-HOM-122 entry + changelog line

**Files:**
- Modify: `docs/REQUIREMENTS.md`

**Interfaces:**
- Consumes: nothing (documentation only).
- Produces: a new REQ-HOM-122 requirement entry (in whichever of the two tracks — "Features" or "Funde & Risiken" — the file's §2/§3 structure uses for net-new features; REQ-HOM-121 was the last feature added, follow its exact entry shape) plus one changelog line in §4, matching every prior entry's style (date, branch, one-paragraph summary, test counts, `pytest -q`/`ruff` status once Task 28's full suite run confirms the final numbers).

- [ ] **Step 1: Read the existing REQ-HOM-121 entry and the most recent 3 changelog rows** (`docs/REQUIREMENTS.md`, already excerpted in this plan's research phase — re-read the file directly before writing, formatting drifts over 121 entries and this task must match the CURRENT shape exactly, not a stale memory of it).

- [ ] **Step 2: Add the requirement entry** — in the features section, add (adjust heading level/column shape to match REQ-HOM-121's real entry exactly):

```markdown
### REQ-HOM-122 — Laborwerte (Blutwerte) als vierte Datendomäne

**Status:** Umgesetzt (Branch `feat/lab-values`)

Vierte Datendomäne neben Trinken/Blutdruck/Wohlbefinden: Laborwerte in 9
medizinischen Kategorien (Leber, Niere, Elektrolyte, Lipide, Schilddrüse,
Blutbild, Entzündung, Verdauung, Medikamentenspiegel) + "Sonstige" für
Custom-Marker. 29 Katalog-Marker mit Default-Referenzbereichen (typische
Erwachsenen-Richtwerte, keine klinische Norm, Vision §4.2), per-Person
Referenzbereich-Overrides, Kategorie-Sichtbarkeit, deutsche Namens-Aliase
(GPT/GOT/Gamma-GT), bidirektionale Einheiten-Konvertierung (Katalog +
genau ein Alt-Unit-Paar pro Custom-Marker), optionale `report_ref`
(Link/ID des Laborberichts, rein referenzierend). Zwei neue Services
(`add_lab_value`, `remove_last_lab_value`), ein Sensor je Marker + ein
Warn-Binary-Sensor je Kategorie, Admin-UI-Abschnitt, eigene Lovelace-Card
(`health-o-mat-labs-card`), Panel-Tab mit Kategorie-Swipe-Leiste,
Overview-Tile-Zeile, vollständige Backup/Restore/Export/Import-Integration
(Backup v3, Restore-Dataset `lab_values`, CSV `lab_values.csv`). Store
Schema v4 → v5 (`lab_readings[]`).

**Akzeptanzkriterien:**

- [x] 9 Katalog-Kategorien + "Sonstige", 29 Katalog-Marker mit Referenzbereichen
- [x] Custom-Marker pro Person (eigene Kategorie/Einheit/Referenz, optional 1 Alt-Unit-Paar)
- [x] Bidirektionale Einheiten-Konvertierung, kanonische Speicherung, Original als `reported_value`/`reported_unit`
- [x] `add_lab_value`/`remove_last_lab_value` Services inkl. Alias-Auflösung, `unknown_marker`/`unit_required`/`unsupported_unit`-Validierung
- [x] Sensor je Marker, Warn-Binary-Sensor je Kategorie, `areas.labs`-Schalter
- [x] Admin-UI: Referenzbereich-Overrides, Kategorien ausblenden, Custom-Marker-Formular, Feedback-Link
- [x] Lovelace-Card `health-o-mat-labs-card` + Panel-Tab + Overview-Tile-Zeile
- [x] Backup v3, Restore-Dataset `lab_values` inkl. Custom-Marker-Merge + Validierung, CSV-Export/-Import
- [x] Medizin-Disclaimer in Card/Panel/README (Vision §4.2)

**Belege:** `tests/test_logic.py`, `tests/test_store.py`, `tests/test_lab_services.py`,
`tests/test_sensor.py`, `tests/test_binary_sensor.py`, `tests/test_ws_api.py`,
`tests/test_panel_js.py`, `tests/test_card_js.py`, `tests/test_report.py`,
`tests/test_restore.py`, `tests/test_import_backup.py`, `tests/test_translations.py`,
`tests/test_frontend.py` (alle `test_req_hom_122_*`); `tests_e2e/test_lab_values_e2e.py`
(Task 28). Exakte `pytest -q`-Zahl und `ruff`-Status werden nach Task 28 final
eingetragen (Konvention der vorherigen Einträge: Zahlen erst nach dem letzten
Test-Lauf, nicht vorab geschätzt).
```

- [ ] **Step 3: Add the changelog line** — append to the §4 "Changelog der Anforderungen" table, following the EXACT row format of the most recent entries (date, bold summary, branch, prose):

```markdown
| 2026-10-31 | **Neu angelegt und umgesetzt: REQ-HOM-122 — Laborwerte (Blutwerte) als vierte Datendomäne** (Branch `feat/lab-values`): Spec `docs/superpowers/specs/2026-10-30-lab-values-design.md` (PR #49 + #50), Implementierungsplan `docs/superpowers/plans/2026-10-31-lab-values.md`. 9 Kategorien, 29 Katalog-Marker, Custom-Marker mit optionalem Alt-Unit-Paar, bidirektionale Einheiten-Konvertierung, zwei neue Services, Sensor je Marker + Warn-Binary je Kategorie, Admin-UI, eigene Lovelace-Card, Panel-Tab mit Swipe, Overview-Tile-Zeile, Backup v3/Restore/CSV-Export/-Import. Store Schema v4 → v5. |
```

- [ ] **Step 4: Commit**

```bash
git add docs/REQUIREMENTS.md
git commit -m "docs: add REQ-HOM-122 for lab values feature"
```

---

### Task 27: `README.md` — feature documentation + medical disclaimer

**Files:**
- Modify: `README.md`

**Interfaces:**
- Consumes: nothing (documentation only).
- Produces: a new "Laborwerte" section following the README's existing per-feature documentation pattern (check how the "Blutdruck"/"Wohlbefinden" sections are structured — heading, short description, entity list, service list, card/panel mention — and mirror it exactly), including the Vision §4.2 medical disclaimer ("keine medizinische Beratung — Richtwerte, keine Diagnose") and a note on the Store Schema v4 → v5 migration (consistent with how prior schema bumps are called out in the README's existing migration notes, e.g. the v0.14.0/mL-unit migration mentioned in `docs/REQUIREMENTS.md`'s changelog).

- [ ] **Step 1: Read the README's existing "Blutdruck" and "Wohlbefinden" sections in full** to copy their exact structure (this plan does not reproduce the whole README here — read it directly before editing).

- [ ] **Step 2: Add the "Laborwerte" section**, placed after the existing "Wohlbefinden" section and before whatever comes next (Backup/Export, Services reference, etc. — match the file's existing section order: data domains first, then cross-cutting features), containing at minimum:

- A one-paragraph description (what it is, the 9 categories + "Sonstige", custom markers, unit conversion, `report_ref`).
- **The medical disclaimer**, verbatim or near-verbatim to the spec's §1 wording: "Die Integration klassifiziert nicht medizinisch und diagnostiziert nicht — Referenzbereiche sind typische Erwachsenen-Richtwerte, keine klinische Norm. Bitte individuell in den Settings anpassen."
- The two new services (`add_lab_value`, `remove_last_lab_value`) with one example call each (same style as the existing `add_blood_pressure` documentation block).
- A mention of the new entities (`sensor.<person>_lab_<marker>`, `binary_sensor.<person>_lab_<category>_warning`).
- A mention of the `health-o-mat-labs-card` Lovelace card and how to add it (`type: custom:health-o-mat-labs-card`), same style as the existing card's YAML example.
- A note that upgrading migrates the Store schema v4 → v5 automatically (idempotent, no action needed) — one sentence, matching the tone of this repo's existing migration notes.

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: document lab values feature in README"
```

---

### Task 28: E2E smoke test

**Files:**
- Create: `tests_e2e/test_lab_values_e2e.py`
- Modify: `tests_e2e/conftest.py` or `scripts/e2e_bootstrap.py` only if the bootstrap needs a new fixture (check first — likely NOT needed, since lab values don't require special onboarding beyond what an existing person entry already provides)

**Interfaces:**
- Consumes: whatever Playwright/pytest fixtures `tests_e2e/`'s existing test files already define for logging into the real HA dev instance and navigating to the Health-O-Mat panel (read 1-2 existing `tests_e2e/test_*.py` files in full immediately before writing this task — this repo's E2E suite has its own `pytest.ini`/fixtures per the REQ-HOM-012 changelog entry, copy its exact login/navigation helper calls verbatim).
- Produces: one Playwright test exercising the spec's §9 E2E smoke scenario end-to-end: add a custom marker via the Admin UI → set a reference-range override → record a lab value via the Card or Panel entry form → confirm the value and its in-range badge appear in both the Panel tab and the Overview tile's lab-warning row.

- [ ] **Step 1: Read an existing E2E test file in full** (e.g. whichever one covers REQ-HOM-113/114's Card/Panel flows — the changelog references `tests_e2e/test_card_config_e2e.py` and `tests_e2e/test_history_e2e.py`) to copy its exact `page.goto(...)`, login, and HA-entity-wait patterns.

- [ ] **Step 2: Write the test** — structure (fill in the EXACT Playwright selectors/helpers from Step 1's reference file, do not invent new ones):

```python
"""E2E smoke test: lab values end-to-end (REQ-HOM-122).

Mirrors the existing Card/Panel E2E pattern (tests_e2e/test_card_config_e2e.py) —
real HA dev instance via the docker-compose.e2e.yml stack, Playwright sync API.
"""

import pytest


@pytest.mark.e2e
def test_lab_values_smoke(page, ha_base_url, logged_in_admin):  # fixture names: copy from an existing E2E file
    """Add a custom marker, set an override, record a value, see it reflected."""
    # 1. Navigate to the Health-O-Mat panel admin settings for the test person
    #    (reuse the existing navigation helper from Step 1's reference file).
    # 2. Open "Laborwerte" admin section, add a custom marker ("E2E Marker", unit "x").
    # 3. Set a reference-range override for an existing catalog marker (e.g. ALT: 5-45).
    # 4. Navigate to the person's detail view, open the "Laborwerte" tab.
    # 5. Use "Neuen Wert erfassen" to record a value for the custom marker.
    # 6. Assert the recorded value and its badge (✓/⚠) appear in the tab.
    # 7. Navigate to the Overview and assert the lab-warning tile row reflects
    #    the correct count (0 if the recorded value was in range, matching
    #    whatever value was entered in step 5 relative to any reference set).
    raise NotImplementedError(
        "Fill in with the exact Playwright calls from the Step 1 reference file "
        "before this task is considered done — see plan Task 28 Step 1/2."
    )
```

(The `raise NotImplementedError(...)` body above is a **placeholder only in this plan document** — per the plan's own "No Placeholders" rule, the IMPLEMENTER must replace it with real Playwright calls copied from the Step 1 reference file before this task's commit; a plan cannot hand-author exact CSS/text selectors for a live browser flow it has not inspected, so this is the one task in this plan where the concrete code is produced during implementation from a named, inspectable reference rather than specified here verbatim. Do not commit this task with the `NotImplementedError` still in place — Step 4 below enforces that.)

- [ ] **Step 3: Run the test against the local E2E docker stack**

Run: `docker compose -f docker-compose.e2e.yml up -d && pytest tests_e2e/test_lab_values_e2e.py -v` (same invocation style as the existing E2E suite — check `tests_e2e/pytest.ini`/the repo's E2E CI workflow for the exact command if this differs)
Expected: PASS (after Step 2's real implementation — the stub above must fail loudly with `NotImplementedError`, never silently pass).

- [ ] **Step 4: Verify no placeholder remains**

Run: `grep -n "NotImplementedError" tests_e2e/test_lab_values_e2e.py`
Expected: no output (the implementer must have replaced the stub body before this task is done).

- [ ] **Step 5: Commit**

```bash
git add tests_e2e/test_lab_values_e2e.py
git commit -m "test: add E2E smoke test for lab values"
```

---

## Final Integration Check

- [ ] **Run the full suite**: `pytest -q` — expect all existing tests plus every `test_req_hom_122_*` test green, no regressions.
- [ ] **Lint**: `ruff check .` and `ruff format --check .` — clean.
- [ ] **hassfest/HACS validation** (if run locally — otherwise covered by CI on push): no new errors.
- [ ] **Manual E2E pass** on the dev instance (`http://127.0.0.1:8123` per `.claude/rules/integration-development.md`): install/reload the integration, confirm Store migrates v4→v5 without data loss, all 29 catalog sensors + 9 category binary sensors appear, Admin UI renders, Card + Panel both work, Backup/Restore/Export/Import round-trip a lab value correctly.
- [ ] **Update `docs/REQUIREMENTS.md`'s REQ-HOM-122 entry** (Task 26) with the FINAL `pytest -q` count and `ruff` status once all tasks are merged — do not leave the placeholder "werden nach Task 28 final eingetragen" sentence in the merged documentation.
- [ ] Per `.claude/rules/integration-development.md`'s 7-step workflow: this is a **MINOR** release (new entities, additive — `unique_id`s are new, not changed; no breaking change for existing installs). Bump `manifest.version` + all `?v=` cache-busters together, tag `vX.Y.0`, publish a real GitHub Release (not just a tag) with "✨ New features" listing the lab values domain, following `.claude/rules/integration-development.md`'s Release-Naming-Best-Practice section exactly.

---

*(End of plan.)*

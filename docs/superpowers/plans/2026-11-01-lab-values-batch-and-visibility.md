# Laborwerte — Batch-Erfassung & Sichtbarkeit: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task.
> Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Die Laborwerte-Domäne um einen atomaren **Bericht** erweitern: Service + WS
`add_lab_report` (mehrere Werte, **ein** `ts`/`report_ref`, Alles-oder-nichts, ein
Store-Write/Refresh/Audit), symmetrisches Batch-Undo `remove_lab_report`, eine eigene
**Labor-Retention** (`lab_retention_months`, voidet statt archiviert), den
Umrechnungsfaktoren im Admin sichtbar machen, den Medizin-Hinweis kontextbezogen in den
Panel-Lab-Tab bringen (abschaltbar über `lab_hide_panel_disclaimer`, Transport via
`panel_data`), die Karten-Disclaimer-Lokalisierung sowie ein Beispiel-Dashboard — ohne
neues Datenmodell, ohne `unique_id`-Änderung, ohne Store-Schema-Bump.

**Architecture:** Bleibt 1:1 in der bestehenden Per-Person-Config-Entry-Architektur.
`lab_readings[]` behält exakt das heutige Format (**Store-Schema bleibt v5**); Batch,
Batch-Undo und Retention sind nur andere Schreibweisen über derselben Liste. Ein neuer
HA-freier Validator (`logic.validate_lab_report_rows`) liefert konvertierte Zeilen **oder
ein strukturiertes Fehlerobjekt** `{code, params, message}`; ein HA-freier Matcher
(`logic.lab_report_matches`) definiert „gehört zum Bericht" (Instant + optionaler Tag).
Drei neue Store-Methoden (`add_lab_readings`, `void_lab_report`,
`void_lab_readings_before`) schreiben je **einmal** mit `deepcopy`-Snapshot-Rollback.
Service (`__init__.py`) und WS (`ws_api.py`) rufen denselben Validator, keiner den anderen.
`panel_data` wächst additiv um `labs.markers[*].alt_units`, `labs.last_report` (inkl.
`report_ref`) und das Top-Level-Flag `lab_hide_panel_disclaimer`; der Admin-Schreibpfad
dafür bleibt `set_settings`. Card und Panel bekommen je eine lokale Dialog-Implementierung
(bewusst kein Shared-Modul, Parität per Test). Retention **voidet** (kein Archiv).

**Tech Stack:** Python 3.13 (Home Assistant Custom Component, bestehende Konventionen),
vanilla JS (kein Framework, ES-Module für das Panel, klassisches Script für die Karte),
pytest mit der Fake-HA-Technik aus `tests/conftest.py`, voluptuous für Service-/WS-Schemata.

**Spec:** `docs/superpowers/specs/2026-11-01-lab-values-batch-and-visibility-design.md`
(final, 1094 Zeilen). Dieser Plan setzt §1–§14 um; §14.1 (Editor-Darstellung des
`object`-Selectors) ist ein Umsetzungs-Hinweis, kein Blocker. Ergänzende Domänen-Spec:
`docs/superpowers/specs/2026-10-30-lab-values-design.md`.

**Branch:** Ein einziger Feature-Branch **`feat/lab-batch-visibility`**, von
`main` (`9cdec0f`) abgezweigt, gemäß `.claude/rules/branch-guard.md` (keine direkten
Commits auf `main`). Git-Mutationen (Branch, Commit, Push) laufen über den `git`-Agenten;
die Commit-Zeilen unten sind die exakten Befehle/Nachrichten für ihn.

**Pre-flight (vor dem Branch, vom `git`-Agenten):** Die finalisierte Spec liegt bereits als
Commit `9cdec0f` auf `main`. Diesen Plan zuerst als eigenen Doku-Commit ablegen, dann
branchen:

```bash
git switch main
git pull --ff-only
git add docs/superpowers/plans/2026-11-01-lab-values-batch-and-visibility.md
git commit -m "docs: plan lab report batch capture and visibility"
git switch -c feat/lab-batch-visibility
```

**Release:** Ziel ist **0.16.2 (PATCH)** — additive Services/UI, keine Breaking
Entity-/Schema-Änderung. Der Release selbst (Version-Bump, Tag, GitHub-Release) ist
**nicht** Teil dieses Plans (siehe Final Integration Check).

## Global Constraints

- Conventional Commits, English, imperative, erste Zeile ≤ 72 Zeichen; jede Commit-Nachricht
  steht exakt im Task. Keine führende UTF-8-BOM.
- `from __future__ import annotations` + vollständige Type-Hints in jeder neuen/berührten
  Python-Datei.
- **`unique_id`s bleiben unverändert.** Kein neues Entity, kein Rename, kein
  `device_info`-Eingriff.
- **Store-Schema bleibt v5**, `lab_readings[]` unverändert
  (`{id, ts, marker_key, value, unit, reported_value, reported_unit, report_ref, created_at,
  voided_at, voided_by, void_reason}`). Kein `batch_id`, kein `LabReport`-Aggregat.
- **Ein Store-Write pro Vorgang:** alle drei Batch-Store-Methoden rufen `_async_save()`
  genau einmal; bei Fehler `deepcopy`-Rollback beider Listen (readings + audit), dann
  `raise` (§2.8 der Spec).
- **Fehlervertrag:** HA-frei `{code, params, message}` (§2.4). Service transportiert nur
  `error["message"]` via `ServiceValidationError`; WS-Batch-Kommandos liefern
  `{"ok": false, "error": …}` als `send_result`. `send_error` bleibt Entry-/Transportfehlern
  vorbehalten. Bestehende Einzelpfade werden **nicht** migriert (REQ-HOM-127).
- **Zeilennummer** = Originalzeile der Eingabeliste, 1-basiert, **inklusive** Leerzeilen;
  `marker` in `params`/`message` ist immer der eingegebene Rohwert (leer → `-`).
  Limits: **200** Server, **60** UI.
- **Retention voidet**, archiviert nicht; Default `0` = aus; eigener Audit-Eintrag nur bei
  `count > 0`; idempotent.
- **`panel_data` wächst nur** um `alt_units`, `last_report`, `lab_hide_panel_disclaimer`.
  Kein `require_explicit_unit` im Payload (§6.2).
- **Doku/Sprache:** Plan/README/Doku deutsch, Code/Kommentare/Commits/Testnamen englisch.
- Nach **jedem** Task: `pytest -q` (oder die genannten Dateien) und `ruff check .` /
  `ruff format --check .` grün. Neue Tests tragen `test_req_hom_123_*` … `test_req_hom_129_*`
  bzw. `test_req_hom_128_*` (Undo).

## Wellen- und Task-Übersicht (20 Tasks, 7 Wellen)

| Wave | Tasks | Inhalt | REQ |
|---|---|---|---|
| 1 | 1–4 | Logik-Validator + Fehlerobjekt, Bericht-Matcher, Store `add_lab_readings`, Store `void_lab_report`/`void_lab_readings_before` | 123, 128, 129 |
| 2 | 5–8 | `services.yaml` + Service-i18n, Service `add_lab_report`, Service `remove_lab_report`, Retention-Option/Wizard/Backup/Diagnostics + Lauf | 123, 128, 129 |
| 3 | 9–10 | WS-Kommandos + Fehler-Envelope, `panel_data` (+3 Felder) + Disclaimer-Settings-Backend | 123, 128, 125 |
| 4 | 11–13 | Card-Dialog, Panel-Dialog, „Bericht verwerfen" in Card+Panel | 123, 128 |
| 5 | 14–16 | Panel-Disclaimer + Leerzustand + Admin-Checkbox, Admin-Umrechnungsspalte + Badge, Karten-Disclaimer-i18n | 124, 125 |
| 6 | 17 | Export voideter Zeilen + Import-Test | 129 |
| 7 | 18–20 | Beispiel-Dashboard, 4 E2E-Tests, Doku/REQUIREMENTS | 126 |

Reihenfolge ist verbindlich; Details siehe „Dependency- & Parallelisierungs-Hinweise".

### Dependency- & Parallelisierungs-Hinweise (Kurzfassung)

**Gemeinsame Engpässe — nie parallel starten:**

| Engpass | Tasks | Grund |
|---|---|---|
| `strings.json` + `translations/{de,en}.json` + `tests/test_translations.py` | 5, 8, 12, 13, 14, 15, 16 | Service-Blöcke, Options-Label, Report-/Disclaimer-/Admin-Keys; `_LAB_SERVICE_FIELDS`/`_REQ_HOM_122_UI_KEYS` sind geteilte Listen |
| `custom_components/health_o_mat/www/health-o-mat-panel-views.js` | 12, 13, 14 | Report-Abschnitt → Verwerfen-Aktion → Disclaimer/Leerzustand im selben `labsTab` |
| `custom_components/health_o_mat/www/health-o-mat-panel-admin.js` | 14, 15 | Disclaimer-Checkbox → Umrechnungsspalte (gleiche Funktion `labSettingsSection`) |
| `custom_components/health_o_mat/www/health-o-mat-panel-base.js` | 12, 13, 14 | Report-CSS → `WS.removeLabReport` → Disclaimer-CSS |
| `custom_components/health_o_mat/www/health-o-mat-panel.js` | 12, 14 | `_labReportDraft`-Init + Change-Handler → Settings-Collect/PATCH |
| `custom_components/health_o_mat/www/health-o-mat-labs-card.js` | 11, 13, 16 | Dialog → Verwerfen → lokalisierter Disclaimer |
| `custom_components/health_o_mat/ws_api.py` | 9, 10 | Kommandos → `panel_data`/Settings (gleiche Datei, aufeinander aufbauend) |
| `tests_e2e/test_lab_values_e2e.py` + `restore_lab_options`-Fixture | 19 | einmalige Fixture-Erweiterung; alle vier neuen Tests in einer Datei |

**Harte Abhängigkeiten (Kette):** 1 → 2 → 4; 1 → 3; 1/2/3 → 6/7/9; 5 → 6/7;
4/8 → 9; 9 → 10; 10 → 11/12; 11/12 → 13; 10/12 → 14; 10/14 → 15; 11 → 16;
3/4 → 17; 13 → 16; 11 → 19; 19 → 20 (Belege).

**Parallelisierbar (disjunkte Dateien):**

| Parallel | Bedingung |
|---|---|
| 3 ‖ 4 | beide `store.py`? **Nein** — gleiche Datei, sequenziell. Nur 1 ‖ 2 formal (gleiche Datei `logic.py`) → **sequenziell**. |
| 17 ‖ 14/15/16 | `exporter.py`/`importer.py`/`tests/test_import_backup.py` vs. Panel-JS/i18n — aber `translations` sind in 14/15/16 im Spiel, 17 nicht: 17 darf parallel zu 14–16 laufen |
| 18 ‖ 14–17 | `examples/` + `tests/test_dashboards.py`; README-Kollision mit 20 → **vor** Task 20 |
| 13 (Panel-Teil) ‖ 16 | beide `labs-card.js`? 13 berührt Card **und** Panel → erst nach 11; 16 ist Card-only → nach 13 |
| 19 nach 11–16 | E2E braucht alle Selektoren/Verhalten |

**Nicht parallel:** 1 ‖ 2 (`logic.py`), 3 ‖ 4 (`store.py`), 6 ‖ 7 (`__init__.py`),
12 ‖ 13 ‖ 14 (`panel-views.js`), 14 ‖ 15 (`panel-admin.js`), 11 ‖ 16 (`labs-card.js`).

---

## Wave 1 — Store & Logik

### Task 1: `const.py` + `logic.py` — Fehlerobjekt, `coerce_lab_number`, `validate_lab_report_rows`

**Files:**
- Modify: `custom_components/health_o_mat/const.py`
- Modify: `custom_components/health_o_mat/logic.py`
- Test: `tests/test_logic.py`

**Interfaces:**
- Consumes: `resolve_lab_marker` (`logic.py:1076`), `convert_lab_value`
  (`logic.py:1091`), `ENTRY_TS_INVALID_MESSAGE` (`logic.py:158`), `Mapping`/`Any`.
- Produces:
  - `const.OPTION_LAB_HIDE_PANEL_DISCLAIMER = "lab_hide_panel_disclaimer"`
  - `const.OPTION_LAB_RETENTION_MONTHS = "lab_retention_months"`
  - `const.LAB_REPORT_MAX_ROWS = 200`
  - `logic.coerce_lab_number(value: Any) -> float | None`
  - `logic.lab_report_error(code: str, params: Mapping[str, Any] | None = None) -> dict`
    (`{"code", "params", "message"}` nach §2.4)
  - `logic.validate_lab_report_rows(values: Any, custom_markers: Any = None)
    -> tuple[list[dict], dict | None]`
  - `logic._lab_row_is_empty(row) -> bool` (intern)
- Verbraucher: Task 2 (Matcher), Task 4 (Store-Void nutzt nur `lab_report_matches`),
  Task 6/7 (Services), Task 9 (WS), Task 11/12 via UI-Fehlertexte.

**Spec-Bezug:** §2.3 (Zeilenform/Leerzeilen), §2.4 (Fehlervertrag + `params` + `message`),
§2.5 (Reihenfolge, `NaN`/`inf`-Härtung), §12 (HA-freie Logiktests).

> **Präzisierung zu §2.4:** Das dortige Beispiel `Zeile 3 (-): invalid_value` widerspricht
> der in §2.5 festgelegten Reihenfolge (unknown_marker **vor** invalid_value). Dieser Plan
> folgt §2.3/§2.5: ein leerer Marker ergibt `unknown_marker`; der leere Rohwert wird im
> Text als `-` gerendert (`Zeile 1 (-): unknown_marker`).

- [ ] **Step 1: Write the failing tests** (ans Ende von `tests/test_logic.py`)

```python
# --- REQ-HOM-123/129: Laborbericht-Batch (HA-frei) --------------------------


def test_req_hom_123_coerce_lab_number_rejects_bool_nan_inf_and_non_numbers():
    from custom_components.health_o_mat import logic

    assert logic.coerce_lab_number(32) == 32.0
    assert logic.coerce_lab_number("32.5") == 32.5
    assert logic.coerce_lab_number(0) == 0.0
    for rejected in (True, False, float("nan"), float("inf"), float("-inf"), "abc", None):
        assert logic.coerce_lab_number(rejected) is None, rejected


def test_req_hom_123_lab_report_error_builds_the_contract_shape():
    from custom_components.health_o_mat import logic

    row_error = logic.lab_report_error(
        "unknown_marker", {"row": 3, "marker": "kreatinin"}
    )
    assert row_error == {
        "code": "unknown_marker",
        "params": {"row": 3, "marker": "kreatinin"},
        "message": "Zeile 3 (kreatinin): unknown_marker",
    }

    duplicate = logic.lab_report_error(
        "duplicate_marker", {"row": 2, "marker": "gpt", "first_row": 1}
    )
    assert duplicate["message"] == (
        "Zeile 2 (gpt): duplicate_marker (schon in Zeile 1)"
    )

    too_many = logic.lab_report_error("too_many_rows", {"count": 201, "limit": 200})
    assert too_many["message"] == "too_many_rows (201 > 200)"

    invalid_ts = logic.lab_report_error("invalid_ts", {"value": "kaputt"})
    assert invalid_ts["message"].startswith("invalid_ts: ")
    assert "kaputt" in invalid_ts["message"]

    assert logic.lab_report_error("no_active_report", {"ts": "2026-11-01T09:15:00+01:00"})[
        "message"
    ] == "no_active_report"


def test_req_hom_123_validate_rows_converts_and_keeps_reported_values():
    from custom_components.health_o_mat import logic

    rows, error = logic.validate_lab_report_rows(
        [
            {"marker": "creatinine", "value": 1.1, "unit": "mg/dL"},
            {"marker": "tsh", "value": "1.9"},
        ]
    )

    assert error is None
    assert [row["marker_key"] for row in rows] == ["creatinine", "tsh"]
    assert rows[0]["unit"] == "µmol/L"
    assert round(rows[0]["value"], 2) == 97.24
    assert rows[0]["reported_value"] == 1.1
    assert rows[0]["reported_unit"] == "mg/dL"
    assert rows[1]["reported_unit"] == "mIU/L"


def test_req_hom_123_validate_rows_resolves_alias_and_custom_marker():
    from custom_components.health_o_mat import logic

    custom = [
        {"key": "vitamin_d", "name": "Vitamin D", "category": "other", "unit": "ng/mL"}
    ]
    rows, error = logic.validate_lab_report_rows(
        [{"marker": "gpt", "value": 32}, {"marker": "vitamin_d", "value": 42}], custom
    )

    assert error is None
    assert [row["marker_key"] for row in rows] == ["alt", "vitamin_d"]
    assert rows[1]["unit"] == "ng/mL"


def test_req_hom_123_validate_rows_ignores_empty_rows():
    from custom_components.health_o_mat import logic

    rows, error = logic.validate_lab_report_rows(
        [
            {},
            {"marker": "", "value": "", "unit": ""},
            {"marker": "alt", "value": 32},
            {"marker": "  ", "value": "  ", "unit": ""},
        ]
    )

    assert error is None
    assert [row["marker_key"] for row in rows] == ["alt"]


def test_req_hom_123_validate_rows_rejects_empty_report():
    from custom_components.health_o_mat import logic

    for empty in ([{}, {"marker": " ", "value": " "}], None, []):
        rows, error = logic.validate_lab_report_rows(empty)
        assert rows == []
        assert error == {"code": "empty_report", "params": {}, "message": "empty_report"}


def test_req_hom_123_validate_rows_rejects_more_than_200_filled_rows():
    from custom_components.health_o_mat import logic

    values = [{"marker": "alt", "value": index} for index in range(201)]

    rows, error = logic.validate_lab_report_rows(values)

    assert rows == []
    assert error == {
        "code": "too_many_rows",
        "params": {"count": 201, "limit": 200},
        "message": "too_many_rows (201 > 200)",
    }


def test_req_hom_123_validate_rows_accepts_200_filled_rows():
    from custom_components.health_o_mat import logic

    custom = [
        {"key": f"m{index}", "name": f"M{index}", "category": "other", "unit": "U/L"}
        for index in range(200)
    ]
    values = [{"marker": f"m{index}", "value": index} for index in range(200)]

    rows, error = logic.validate_lab_report_rows(values, custom)

    assert error is None
    assert len(rows) == 200


def test_req_hom_123_validate_rows_does_not_count_empty_rows_for_the_cap():
    from custom_components.health_o_mat import logic

    values = [{"marker": "alt", "value": 32}] + [{} for _ in range(250)]

    rows, error = logic.validate_lab_report_rows(values)

    assert error is None
    assert len(rows) == 1


def test_req_hom_123_validate_rows_row_numbers_count_original_positions():
    from custom_components.health_o_mat import logic

    rows, error = logic.validate_lab_report_rows(
        [{}, {"marker": "alt", "value": 32}, {"marker": "gptx", "value": 1}]
    )

    assert rows == []
    assert error["code"] == "unknown_marker"
    assert error["params"] == {"row": 3, "marker": "gptx"}
    assert error["message"] == "Zeile 3 (gptx): unknown_marker"


def test_req_hom_123_validate_rows_renders_missing_marker_as_dash():
    from custom_components.health_o_mat import logic

    # §2.5: ein fehlender Marker ist ZUERST `unknown_marker` (vor
    # `invalid_value`); der leere Rohwert erscheint im Text als `-` (§2.4).
    rows, error = logic.validate_lab_report_rows([{"value": "abc"}])

    assert rows == []
    assert error == {
        "code": "unknown_marker",
        "params": {"row": 1, "marker": ""},
        "message": "Zeile 1 (-): unknown_marker",
    }


def test_req_hom_123_validate_rows_requires_explicit_unit():
    from custom_components.health_o_mat import logic

    rows, error = logic.validate_lab_report_rows(
        [{"marker": "urine_protein_creatinine_ratio", "value": 10}]
    )

    assert rows == []
    assert error == {
        "code": "unit_required",
        "params": {"row": 1, "marker": "urine_protein_creatinine_ratio"},
        "message": "Zeile 1 (urine_protein_creatinine_ratio): unit_required",
    }


def test_req_hom_123_validate_rows_reports_invalid_value_before_unsupported_unit():
    from custom_components.health_o_mat import logic

    rows, error = logic.validate_lab_report_rows(
        [{"marker": "alt", "value": "abc", "unit": "mg/dL"}]
    )

    assert rows == []
    assert error["code"] == "invalid_value"
    assert error["params"] == {"row": 1, "marker": "alt", "value": "abc"}


def test_req_hom_123_validate_rows_rejects_bool_and_nan_values():
    from custom_components.health_o_mat import logic

    for bad in (True, float("nan"), float("inf")):
        rows, error = logic.validate_lab_report_rows([{"marker": "alt", "value": bad}])
        assert rows == []
        assert error["code"] == "invalid_value"


def test_req_hom_123_validate_rows_reports_unsupported_unit():
    from custom_components.health_o_mat import logic

    rows, error = logic.validate_lab_report_rows(
        [{"marker": "alt", "value": 32, "unit": "mg/dL"}]
    )

    assert rows == []
    assert error == {
        "code": "unsupported_unit",
        "params": {"row": 1, "marker": "alt", "unit": "mg/dL"},
        "message": "Zeile 1 (alt): unsupported_unit",
    }


def test_req_hom_123_validate_rows_reports_alias_duplicate_with_first_row():
    from custom_components.health_o_mat import logic

    rows, error = logic.validate_lab_report_rows(
        [{"marker": "alt", "value": 32}, {"marker": "gpt", "value": 30}]
    )

    assert rows == []
    assert error == {
        "code": "duplicate_marker",
        "params": {"row": 2, "marker": "gpt", "first_row": 1},
        "message": "Zeile 2 (gpt): duplicate_marker (schon in Zeile 1)",
    }


def test_req_hom_123_validate_rows_row_error_wins_over_earlier_duplicate():
    from custom_components.health_o_mat import logic

    rows, error = logic.validate_lab_report_rows(
        [
            {"marker": "alt", "value": 32},
            {"marker": "gpt", "value": 30},
            {"marker": "gptx", "value": 1},
        ]
    )

    assert rows == []
    assert error["code"] == "unknown_marker"
    assert error["params"]["row"] == 3
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_logic.py -k req_hom_123 -q`
Expected: FAIL — `AttributeError: module 'custom_components.health_o_mat.logic' has no
attribute 'coerce_lab_number'` (bzw. `lab_report_error` / `validate_lab_report_rows`).

- [ ] **Step 3: Implement — `const.py`**

Nach `LAB_REPORT_REF_MAX_LEN = 500` (`const.py:501`) einfügen:

```python
# LEICHTER Batch-Vertrag (REQ-HOM-123): Server-Limit je Bericht; die UI hat
# einen eigenen Soft-Cap (60). Beide Werte sind bewusst unabhängig.
LAB_REPORT_MAX_ROWS = 200

# Labor-Retention (REQ-HOM-129): eigene Option, unabhängig von
# `retention_months` (Getränke/BD); 0 = aus (Default = bisheriges Verhalten).
OPTION_LAB_RETENTION_MONTHS = "lab_retention_months"

# Panel-Medizin-Hinweis (REQ-HOM-125): Admin-Schalter, Default False = sichtbar.
OPTION_LAB_HIDE_PANEL_DISCLAIMER = "lab_hide_panel_disclaimer"
```

- [ ] **Step 4: Implement — `logic.py`**

Import ergänzen (`math`, alphabetisch zwischen `io` und `re`):

```python
import calendar
import csv
import io
import math
import re
import unicodedata
```

`LAB_REPORT_MAX_ROWS` in den `const`-Import aufnehmen (alphabetisch nach
`LAB_MARKER_ALIASES`).

Nach `convert_lab_value` (`logic.py:1108`) einfügen:

```python
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
            return [], lab_report_error(
                "unknown_marker", {"row": index, "marker": raw_marker}
            )
        marker_key, marker_def = resolved
        raw_unit = row.get("unit")
        unit = str(raw_unit).strip() if raw_unit is not None else ""
        if not unit and marker_def.get("require_explicit_unit"):
            return [], lab_report_error(
                "unit_required", {"row": index, "marker": raw_marker}
            )
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
    for (index, marker_key, raw_marker) in resolved_keys:
        if marker_key in first_row:
            return [], lab_report_error(
                "duplicate_marker",
                {"row": index, "marker": raw_marker, "first_row": first_row[marker_key]},
            )
        first_row[marker_key] = index
    return converted, None
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_logic.py -k req_hom_123 -q`
Expected: all PASS.

- [ ] **Step 6: Regression**

Run: `python3 -m pytest tests/test_logic.py -q && ruff check custom_components/health_o_mat/const.py custom_components/health_o_mat/logic.py tests/test_logic.py && ruff format --check custom_components/health_o_mat/const.py custom_components/health_o_mat/logic.py tests/test_logic.py`
Expected: grün/clean.

- [ ] **Step 7: Commit**

```bash
git add custom_components/health_o_mat/const.py custom_components/health_o_mat/logic.py tests/test_logic.py
git commit -m "feat: add lab report validation and structured errors"
```

---

### Task 2: `logic.py` — `lab_report_matches` (Berichts-Zugehörigkeit)

**Files:**
- Modify: `custom_components/health_o_mat/logic.py`
- Test: `tests/test_logic.py`

**Interfaces:**
- Consumes: `_parse_ts` (`logic.py:139`), `_align_tz` (`logic.py:215`), `UTC`.
- Produces: `lab_report_matches(reading: Mapping[str, Any], ts: datetime,
  report_ref: str | None = None) -> bool` — Instant-Vergleich (Offset-Varianten derselben
  Zeit treffen), optionaler Tag-Filter (`None` = kein Filter; ein gesetzter Filter trifft
  `report_ref IS NULL` **nicht**).
- Verbraucher: Task 4 (`store.void_lab_report`).

**Spec-Bezug:** §2.13 (Zeitvergleich als Instant, `report_ref`-Filter), §12
(`lab_report_matches`).

- [ ] **Step 1: Write the failing tests** (ans Ende von `tests/test_logic.py`)

```python
# --- REQ-HOM-128: Berichts-Matcher (HA-frei) --------------------------------


def _reading(ts: str, report_ref: str | None = None) -> dict:
    return {"ts": ts, "marker_key": "alt", "value": 32.0, "report_ref": report_ref}


def test_req_hom_128_lab_report_matches_compares_instants_not_offsets():
    from datetime import datetime

    from custom_components.health_o_mat import logic

    target = datetime.fromisoformat("2026-11-01T08:15:00+00:00")

    assert logic.lab_report_matches(_reading("2026-11-01T09:15:00+01:00"), target) is True
    assert logic.lab_report_matches(_reading("2026-11-01T09:15:00+02:00"), target) is False


def test_req_hom_128_lab_report_matches_filters_by_report_ref():
    from datetime import datetime

    from custom_components.health_o_mat import logic

    target = datetime.fromisoformat("2026-11-01T09:15:00+01:00")

    assert logic.lab_report_matches(_reading("2026-11-01T09:15:00+01:00", "Labor A"), target)
    assert not logic.lab_report_matches(
        _reading("2026-11-01T09:15:00+01:00", "Labor A"), target, "Labor B"
    )
    # Ein gesetzter Filter trifft einen Eintrag ohne Tag NICHT.
    assert not logic.lab_report_matches(
        _reading("2026-11-01T09:15:00+01:00", None), target, "Labor A"
    )
    # Ohne Filter zählt jeder Eintrag dieses Zeitpunkts.
    assert logic.lab_report_matches(_reading("2026-11-01T09:15:00+01:00", None), target)


def test_req_hom_128_lab_report_matches_tolerates_broken_or_missing_ts():
    from datetime import datetime

    from custom_components.health_o_mat import logic

    target = datetime.fromisoformat("2026-11-01T09:15:00+01:00")

    assert logic.lab_report_matches({"ts": "kaputt"}, target) is False
    assert logic.lab_report_matches({}, target) is False
    assert logic.lab_report_matches("kein-dict", target) is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_logic.py -k req_hom_128 -q`
Expected: FAIL — `AttributeError: ... no attribute 'lab_report_matches'`.

- [ ] **Step 3: Implement** — direkt nach `validate_lab_report_rows` einfügen

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_logic.py -k req_hom_128 -q`
Expected: all PASS.

- [ ] **Step 5: Regression**

Run: `python3 -m pytest tests/test_logic.py -q && ruff check custom_components/health_o_mat/logic.py tests/test_logic.py`
Expected: grün/clean.

- [ ] **Step 6: Commit**

```bash
git add custom_components/health_o_mat/logic.py tests/test_logic.py
git commit -m "feat: add lab report instant matcher"
```

---

### Task 3: `store.py` — `add_lab_readings` (ein Save, ein Audit, Rollback)

**Files:**
- Modify: `custom_components/health_o_mat/store.py`
- Test: `tests/test_store.py`

**Interfaces:**
- Consumes: `self.entry`, `self._append_audit` (`store.py:334`), `self._async_save`
  (`store.py:1007`), `_now_iso`, `copy.deepcopy`, `uuid`.
- Produces: `HealthOMatStore.add_lab_readings(entry_id: str, ts_iso: str, rows: list[dict],
  report_ref: str | None = None, created_ts_iso: str | None = None, actor: str | None =
  None, audit_limit: int = DEFAULT_AUDIT_LIMIT) -> list[str]`.
- Audit: `lab_values_added`, `target_id=None`, Details
  `{"count", "marker_keys"[:20], "reading_ids"[:20], "created_at"}` (§2.9).

**Spec-Bezug:** §2.8 (Store-API + `deepcopy`-Rollback), §2.9 (ein Audit-Eintrag,
Datenminimierung, `created_at`), §12 (Store-Tests).

- [ ] **Step 1: Write the failing tests** (ans Ende von `tests/test_store.py`)

```python
# --- REQ-HOM-123: add_lab_readings ------------------------------------------


def _lab_rows(count: int = 2) -> list[dict]:
    return [
        {
            "marker_key": f"marker_{index}",
            "value": float(index + 1),
            "unit": "U/L",
            "reported_value": float(index + 1),
            "reported_unit": "U/L",
        }
        for index in range(count)
    ]


def test_req_hom_123_add_lab_readings_writes_all_rows_with_one_save(mock_store_fixture):
    store, mock_save = mock_store_fixture

    ids = _async_test(
        store.add_lab_readings(
            "e1",
            "2026-11-01T09:15:00+01:00",
            _lab_rows(2),
            report_ref="https://example.com/1",
            created_ts_iso="2026-11-01T10:00:00+01:00",
        )
    )

    readings = store.entry("e1")["lab_readings"]
    assert [reading["marker_key"] for reading in readings] == ["marker_0", "marker_1"]
    assert all(reading["ts"] == "2026-11-01T09:15:00+01:00" for reading in readings)
    assert all(reading["report_ref"] == "https://example.com/1" for reading in readings)
    assert all(reading["created_at"] == "2026-11-01T10:00:00+01:00" for reading in readings)
    assert all(reading["voided_at"] is None for reading in readings)
    assert {reading["id"] for reading in readings} == set(ids)
    mock_save.async_save.assert_awaited_once()


def test_req_hom_123_add_lab_readings_writes_one_privacy_safe_audit_entry(mock_store_fixture):
    store, _mock_save = mock_store_fixture

    ids = _async_test(
        store.add_lab_readings(
            "e1",
            "2026-11-01T09:15:00+01:00",
            _lab_rows(2),
            report_ref="Labor 10/2026",
            created_ts_iso="2026-11-01T10:00:00+01:00",
        )
    )

    audit = store.entry("e1")["audit_log"]
    assert len(audit) == 1
    assert audit[0]["action"] == "lab_values_added"
    assert audit[0]["kind"] == "lab_readings"
    assert audit[0]["target_id"] is None
    assert audit[0]["details"] == {
        "count": 2,
        "marker_keys": ["marker_0", "marker_1"],
        "reading_ids": ids,
        "created_at": "2026-11-01T10:00:00+01:00",
    }
    assert "report_ref" not in audit[0]["details"]
    assert "Labor 10/2026" not in repr(audit[0])


def test_req_hom_123_add_lab_readings_caps_details_lists_at_20(mock_store_fixture):
    store, _mock_save = mock_store_fixture

    ids = _async_test(store.add_lab_readings("e1", "2026-11-01T09:15:00+01:00", _lab_rows(25)))

    details = store.entry("e1")["audit_log"][0]["details"]
    assert details["count"] == 25
    assert len(details["marker_keys"]) == 20
    assert len(details["reading_ids"]) == 20
    assert details["reading_ids"] == ids[:20]
    assert len(store.entry("e1")["lab_readings"]) == 25


def test_req_hom_123_add_lab_readings_rolls_back_on_save_error(
    mock_store_fixture, monkeypatch
):
    store, _mock_save = mock_store_fixture
    existing = {"id": "old-reading", "marker_key": "alt", "value": 32.0}
    store.entry("e1")["lab_readings"] = [existing]
    # Zwei Alt-Einträge + Limit 2: das Anhängen kappt den Ring (inkl.
    # `audit_pruned`-Summary). Ein Slice-Rollback würde das NICHT
    # wiederherstellen — der Test pinnt den deepcopy-Snapshot (§2.8).
    store.entry("e1")["audit_log"] = [
        {
            "id": "audit-1",
            "ts": "2026-10-01T08:00:00+02:00",
            "action": "lab_value_added",
            "kind": "lab_readings",
            "target_id": "old-reading",
            "actor": None,
            "details": {},
        },
        {
            "id": "audit-2",
            "ts": "2026-10-02T08:00:00+02:00",
            "action": "entry_voided",
            "kind": "lab_readings",
            "target_id": "old-reading",
            "actor": None,
            "details": {},
        },
    ]

    async def _fail_save() -> None:
        raise RuntimeError("disk full")

    monkeypatch.setattr(store, "_async_save", _fail_save)

    with pytest.raises(RuntimeError, match="disk full"):
        _async_test(
            store.add_lab_readings(
                "e1", "2026-11-01T09:15:00+01:00", _lab_rows(2), audit_limit=2
            )
        )

    assert store.entry("e1")["lab_readings"] == [existing]
    assert [event["id"] for event in store.entry("e1")["audit_log"]] == [
        "audit-1",
        "audit-2",
    ]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_store.py -k req_hom_123 -q`
Expected: FAIL — `AttributeError: 'HealthOMatStore' object has no attribute
'add_lab_readings'`.

- [ ] **Step 3: Implement** — direkt nach `add_lab_reading` (`store.py:680`) einfügen

```python
    async def add_lab_readings(
        self,
        entry_id: str,
        ts_iso: str,
        rows: list[dict],
        report_ref: str | None = None,
        created_ts_iso: str | None = None,
        actor: str | None = None,
        audit_limit: int = DEFAULT_AUDIT_LIMIT,
    ) -> list[str]:
        """Mehrere Laborwerte eines Berichts als EIN Vorgang schreiben (§2.8).

        ``rows`` sind bereits validierte, kanonisch konvertierte Zeilen
        (``{marker_key, value, unit, reported_value, reported_unit}``). Genau ein
        Save, genau ein Audit-Eintrag; schlägt der Save fehl, wird der
        In-Memory-Zustand (deepcopy-Snapshot) exakt zurückgesetzt und der Fehler
        weitergereicht.
        """
        created = created_ts_iso or _now_iso()
        entry = self.entry(entry_id)
        readings_before = copy.deepcopy(entry.get("lab_readings") or [])
        audit_before = copy.deepcopy(entry.get("audit_log") or [])
        reading_ids: list[str] = []
        marker_keys: list[str] = []
        try:
            for row in rows:
                reading = {
                    "id": str(uuid.uuid4()),
                    "ts": ts_iso,
                    "marker_key": row["marker_key"],
                    "value": float(row["value"]),
                    "unit": row["unit"],
                    "reported_value": float(row["reported_value"]),
                    "reported_unit": row["reported_unit"],
                    "report_ref": report_ref,
                    "created_at": created,
                    "voided_at": None,
                    "voided_by": None,
                    "void_reason": None,
                }
                entry.setdefault("lab_readings", []).append(reading)
                reading_ids.append(reading["id"])
                marker_keys.append(reading["marker_key"])
            self._append_audit(
                entry_id,
                "lab_values_added",
                "lab_readings",
                None,
                actor,
                {
                    "count": len(reading_ids),
                    "marker_keys": marker_keys[:20],
                    "reading_ids": reading_ids[:20],
                    "created_at": created,
                },
                audit_limit,
            )
            await self._async_save()
        except Exception:
            entry["lab_readings"] = readings_before
            entry["audit_log"] = audit_before
            raise
        return reading_ids
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_store.py -k req_hom_123 -q`
Expected: all PASS.

- [ ] **Step 5: Regression**

Run: `python3 -m pytest tests/test_store.py tests/test_import_backup.py tests/test_restore.py -q && ruff check custom_components/health_o_mat/store.py tests/test_store.py`
Expected: grün/clean.

- [ ] **Step 6: Commit**

```bash
git add custom_components/health_o_mat/store.py tests/test_store.py
git commit -m "feat: add atomic lab report writer to store"
```

---

### Task 4: `store.py` — `void_lab_report` + `void_lab_readings_before` (Retention)

**Files:**
- Modify: `custom_components/health_o_mat/store.py`
- Test: `tests/test_store.py`

**Interfaces:**
- Consumes: `logic.lab_report_matches` (Task 2), `_chrono_sort_key` (`store.py:1172`),
  `self._append_audit`, `self._async_save`, `copy.deepcopy`.
- Produces:
  - `void_lab_report(entry_id, ts_iso, report_ref=None, actor=None,
    reason="report_discarded", audit_limit=DEFAULT_AUDIT_LIMIT) -> list[str]`
  - `void_lab_readings_before(entry_id, cutoff_iso, actor=None,
    audit_limit=DEFAULT_AUDIT_LIMIT, months: int = 0) -> list[str]`
    (`months` ist additiv für den Audit-Details-Eintrag `lab_values_retention`;
    die vier spezifizierten Parameter bleiben unverändert).
- Audit: `lab_report_voided` bzw. `lab_values_retention`, je ein Eintrag, `reading_ids`
  ≤ 20, `created_at`, keine Messwerte/`report_ref`.

**Spec-Bezug:** §2.8 (Signatur + Rollback), §2.9 (Audit-Details), §2.13 (`void_reason`),
§2.14 (Retention idempotent, nur aktive, `ts < cutoff`), §12.

- [ ] **Step 1: Write the failing tests** (ans Ende von `tests/test_store.py`)

```python
# --- REQ-HOM-128/129: Batch-Undo + Retention --------------------------------


def _seed_lab(store, entry_id: str = "e1", **kwargs) -> None:
    _async_test(store.add_lab_readings(entry_id, **kwargs))


def test_req_hom_128_void_lab_report_voids_only_matching_instant(mock_store_fixture):
    store, mock_save = mock_store_fixture
    store.entry("e1")["lab_readings"] = [
        {"id": "r1", "ts": "2026-11-01T09:15:00+01:00", "marker_key": "alt",
         "report_ref": "A", "voided_at": None},
        {"id": "r2", "ts": "2026-11-01T08:15:00+00:00", "marker_key": "crp",
         "report_ref": "A", "voided_at": None},
        {"id": "r3", "ts": "2026-10-01T09:15:00+01:00", "marker_key": "tsh",
         "report_ref": None, "voided_at": None},
    ]

    voided = _async_test(
        store.void_lab_report("e1", "2026-11-01T09:15:00+01:00", report_ref="A")
    )

    assert voided == ["r1", "r2"]
    readings = {reading["id"]: reading for reading in store.entry("e1")["lab_readings"]}
    assert readings["r1"]["void_reason"] == "report_discarded"
    assert readings["r1"]["voided_at"] is not None
    assert readings["r2"]["voided_at"] is not None
    assert readings["r3"]["voided_at"] is None
    mock_save.async_save.assert_awaited_once()


def test_req_hom_128_void_lab_report_without_ref_voids_all_at_that_instant(mock_store_fixture):
    store, _mock_save = mock_store_fixture
    store.entry("e1")["lab_readings"] = [
        {"id": "r1", "ts": "2026-11-01T09:15:00+01:00", "marker_key": "alt",
         "report_ref": "A", "voided_at": None},
        {"id": "r2", "ts": "2026-11-01T09:15:00+01:00", "marker_key": "crp",
         "report_ref": None, "voided_at": None},
    ]

    voided = _async_test(store.void_lab_report("e1", "2026-11-01T09:15:00+01:00"))

    assert voided == ["r1", "r2"]


def test_req_hom_128_void_lab_report_writes_one_audit_entry(mock_store_fixture):
    store, _mock_save = mock_store_fixture
    store.entry("e1")["lab_readings"] = [
        {"id": "r1", "ts": "2026-11-01T09:15:00+01:00", "marker_key": "alt",
         "report_ref": "A", "voided_at": None},
    ]

    _async_test(store.void_lab_report("e1", "2026-11-01T09:15:00+01:00", actor="u1"))

    audit = store.entry("e1")["audit_log"]
    assert len(audit) == 1
    assert audit[0]["action"] == "lab_report_voided"
    assert audit[0]["kind"] == "lab_readings"
    assert audit[0]["target_id"] is None
    assert audit[0]["actor"] == "u1"
    assert "report_ref" not in audit[0]["details"]
    assert audit[0]["details"]["count"] == 1
    assert audit[0]["details"]["reading_ids"] == ["r1"]
    assert audit[0]["details"]["created_at"]


def test_req_hom_128_void_lab_report_without_match_returns_empty_without_write(
    mock_store_fixture,
):
    store, mock_save = mock_store_fixture
    store.entry("e1")["lab_readings"] = [
        {"id": "r1", "ts": "2026-10-01T09:15:00+01:00", "marker_key": "alt",
         "report_ref": None, "voided_at": None},
    ]

    voided = _async_test(store.void_lab_report("e1", "2026-11-01T09:15:00+01:00"))

    assert voided == []
    assert store.entry("e1")["audit_log"] == []
    mock_save.async_save.assert_not_awaited()


def test_req_hom_128_void_lab_report_rolls_back_voided_fields_on_save_error(
    mock_store_fixture, monkeypatch
):
    store, _mock_save = mock_store_fixture
    original = {"id": "r1", "ts": "2026-11-01T09:15:00+01:00", "marker_key": "alt",
                "report_ref": None, "voided_at": None, "voided_by": None,
                "void_reason": None}
    store.entry("e1")["lab_readings"] = [copy.deepcopy(original)]

    async def _fail_save() -> None:
        raise RuntimeError("disk full")

    monkeypatch.setattr(store, "_async_save", _fail_save)

    with pytest.raises(RuntimeError, match="disk full"):
        _async_test(store.void_lab_report("e1", "2026-11-01T09:15:00+01:00"))

    assert store.entry("e1")["lab_readings"] == [original]
    assert store.entry("e1")["audit_log"] == []


def test_req_hom_129_void_lab_readings_before_voids_only_older_active(
    mock_store_fixture,
):
    store, mock_save = mock_store_fixture
    store.entry("e1")["lab_readings"] = [
        {"id": "old", "ts": "2026-01-01T09:00:00+01:00", "marker_key": "alt",
         "voided_at": None},
        {"id": "new", "ts": "2026-10-01T09:00:00+02:00", "marker_key": "crp",
         "voided_at": None},
        {"id": "already", "ts": "2025-01-01T09:00:00+01:00", "marker_key": "tsh",
         "voided_at": "2026-02-01T00:00:00+01:00"},
    ]

    voided = _async_test(
        store.void_lab_readings_before(
            "e1", "2026-09-01T00:00:00+02:00", months=12
        )
    )

    assert voided == ["old"]
    readings = {reading["id"]: reading for reading in store.entry("e1")["lab_readings"]}
    assert readings["old"]["void_reason"] == "retention"
    assert readings["new"]["voided_at"] is None
    assert readings["already"]["void_reason"] is None
    audit = store.entry("e1")["audit_log"]
    assert len(audit) == 1
    assert audit[0]["action"] == "lab_values_retention"
    assert audit[0]["details"]["count"] == 1
    assert audit[0]["details"]["months"] == 12
    assert audit[0]["details"]["cutoff"] == "2026-09-01T00:00:00+02:00"
    assert audit[0]["details"]["reading_ids"] == ["old"]
    mock_save.async_save.assert_awaited_once()


def test_req_hom_129_void_lab_readings_before_is_idempotent(mock_store_fixture):
    store, _mock_save = mock_store_fixture
    store.entry("e1")["lab_readings"] = [
        {"id": "old", "ts": "2026-01-01T09:00:00+01:00", "marker_key": "alt",
         "voided_at": None},
    ]

    first = _async_test(store.void_lab_readings_before("e1", "2026-09-01T00:00:00+02:00", months=12))
    second = _async_test(
        store.void_lab_readings_before("e1", "2026-09-01T00:00:00+02:00", months=12)
    )

    assert first == ["old"]
    assert second == []
    assert len([e for e in store.entry("e1")["audit_log"] if e["action"] == "lab_values_retention"]) == 1


def test_req_hom_129_void_lab_readings_before_rolls_back_on_save_error(
    mock_store_fixture, monkeypatch
):
    store, _mock_save = mock_store_fixture
    original = {"id": "old", "ts": "2026-01-01T09:00:00+01:00", "marker_key": "alt",
                "voided_at": None, "voided_by": None, "void_reason": None}
    store.entry("e1")["lab_readings"] = [copy.deepcopy(original)]

    async def _fail_save() -> None:
        raise RuntimeError("disk full")

    monkeypatch.setattr(store, "_async_save", _fail_save)

    with pytest.raises(RuntimeError, match="disk full"):
        _async_test(
            store.void_lab_readings_before("e1", "2026-09-01T00:00:00+02:00", months=12)
        )

    assert store.entry("e1")["lab_readings"] == [original]
    assert store.entry("e1")["audit_log"] == []
```

`copy` ist in `tests/test_store.py` bereits importiert.

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_store.py -k "req_hom_128 or req_hom_129" -q`
Expected: FAIL — `AttributeError: 'HealthOMatStore' object has no attribute
'void_lab_report'`.

- [ ] **Step 3: Implement**

(a) Import ergänzen (nach dem `const`-Importblock):

```python
from .logic import lab_report_matches
```

(b) Nach `void_lab_reading` (`store.py:754`) einfügen:

```python
    async def void_lab_report(
        self,
        entry_id: str,
        ts_iso: str,
        report_ref: str | None = None,
        actor: str | None = None,
        reason: str = "report_discarded",
        audit_limit: int = DEFAULT_AUDIT_LIMIT,
    ) -> list[str]:
        """Alle aktiven Werte eines Berichts voiden (REQ-HOM-128).

        Treffer = gleicher Instant wie ``ts_iso`` und — falls ``report_ref``
        gesetzt ist — exakt derselbe Tag. Ein Save, ein Audit, Rollback bei
        Save-Fehler. Leere Rückgabe = kein aktiver Treffer (kein Write).
        """
        entry = self.entry(entry_id)
        try:
            target = datetime.fromisoformat(ts_iso)
        except (TypeError, ValueError):
            return []
        readings_before = copy.deepcopy(entry.get("lab_readings") or [])
        audit_before = copy.deepcopy(entry.get("audit_log") or [])
        voided_at = _now_iso()
        voided_ids: list[str] = []
        try:
            for reading in entry.get("lab_readings") or []:
                if not isinstance(reading, dict) or reading.get("voided_at"):
                    continue
                if not lab_report_matches(reading, target, report_ref):
                    continue
                reading["voided_at"] = voided_at
                reading["voided_by"] = actor
                reading["void_reason"] = reason
                voided_ids.append(reading["id"])
            if not voided_ids:
                return []
            self._append_audit(
                entry_id,
                "lab_report_voided",
                "lab_readings",
                None,
                actor,
                {
                    "count": len(voided_ids),
                    "reading_ids": voided_ids[:20],
                    "created_at": voided_at,
                },
                audit_limit,
            )
            await self._async_save()
        except Exception:
            entry["lab_readings"] = readings_before
            entry["audit_log"] = audit_before
            raise
        return voided_ids

    async def void_lab_readings_before(
        self,
        entry_id: str,
        cutoff_iso: str,
        actor: str | None = None,
        audit_limit: int = DEFAULT_AUDIT_LIMIT,
        months: int = 0,
    ) -> list[str]:
        """Labor-Retention: aktive Werte mit ``ts < cutoff`` voiden (REQ-HOM-129).

        Kein Archiv, keine Listenkürzung, keine Änderung an Getränken/BD.
        Idempotent: bereits voidete Einträge werden nie erneut gezählt oder
        geauditet. ``months`` landet nur im Audit-Details-Objekt.
        """
        entry = self.entry(entry_id)
        cutoff = _chrono_sort_key(cutoff_iso)
        readings_before = copy.deepcopy(entry.get("lab_readings") or [])
        audit_before = copy.deepcopy(entry.get("audit_log") or [])
        voided_at = _now_iso()
        voided_ids: list[str] = []
        try:
            for reading in entry.get("lab_readings") or []:
                if not isinstance(reading, dict) or reading.get("voided_at"):
                    continue
                if _chrono_sort_key(reading.get("ts")) >= cutoff:
                    continue
                reading["voided_at"] = voided_at
                reading["voided_by"] = actor
                reading["void_reason"] = "retention"
                voided_ids.append(reading["id"])
            if not voided_ids:
                return []
            self._append_audit(
                entry_id,
                "lab_values_retention",
                "lab_readings",
                None,
                actor,
                {
                    "count": len(voided_ids),
                    "months": int(months),
                    "cutoff": cutoff_iso,
                    "reading_ids": voided_ids[:20],
                    "created_at": voided_at,
                },
                audit_limit,
            )
            await self._async_save()
        except Exception:
            entry["lab_readings"] = readings_before
            entry["audit_log"] = audit_before
            raise
        return voided_ids
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_store.py -k "req_hom_128 or req_hom_129" -q`
Expected: all PASS.

- [ ] **Step 5: Regression**

Run: `python3 -m pytest tests/test_store.py -q && ruff check custom_components/health_o_mat/store.py tests/test_store.py && ruff format --check custom_components/health_o_mat/store.py tests/test_store.py`
Expected: grün/clean.

- [ ] **Step 6: Commit**

```bash
git add custom_components/health_o_mat/store.py tests/test_store.py
git commit -m "feat: add lab report voiding and retention to store"
```

---

## Wave 2 — Services & Retention-Optionen

### Task 5: `services.yaml` + Service-i18n — `add_lab_report` und `remove_lab_report` + Mirror-Test

**Files:**
- Modify: `custom_components/health_o_mat/services.yaml`
- Modify: `custom_components/health_o_mat/strings.json`
- Modify: `custom_components/health_o_mat/translations/de.json`
- Modify: `custom_components/health_o_mat/translations/en.json`
- Test: `tests/test_translations.py`, `tests/test_lab_services.py`

**Interfaces:**
- Consumes: nichts aus dem Code (reine Deklaration); der 29er-Optionssatz ist 1:1 aus
  `add_lab_value` (`services.yaml:337-405`).
- Produces:
  - `services.yaml`: `add_lab_report` (`person`, `values`, `ts`, `report_ref`;
    `values` = `object`-Selector mit `multiple: true`, `label_field: marker`, drei
    Unterfeldern) und `remove_lab_report` (`person`, `ts` **required**, `report_ref`).
  - i18n: `services.add_lab_report` (Felder `values`/`ts`/`report_ref`) und
    `services.remove_lab_report` (Felder `ts`/`report_ref`) in Master + de + en.
- Handler folgen in Tasks 6/7; dieser Task ist reine Metadaten-/Paritätsarbeit.

**Spec-Bezug:** §2.2 (Feldtabelle + YAML), §2.13 (Undo-Felder), §2.12 (Nicht-Idempotenz in
der Description), §11/§12 (i18n, Mirror).

- [ ] **Step 1: Write the failing tests**

(a) `tests/test_translations.py` (`_LAB_SERVICE_FIELDS`/`_LAB_TRANSLATED_FIELDS`,
`Zeile 392-403`):

```python
_LAB_SERVICE_FIELDS = {
    "add_lab_value": {"person", "marker", "value", "unit", "ts", "report_ref"},
    "add_lab_report": {"person", "values", "ts", "report_ref"},
    "remove_last_lab_value": {"person", "marker"},
    "remove_lab_report": {"person", "ts", "report_ref"},
}

_LAB_TRANSLATED_FIELDS = {
    "add_lab_value": {"marker", "unit", "ts", "report_ref"},
    "add_lab_report": {"values", "ts", "report_ref"},
    "remove_last_lab_value": {"marker"},
    "remove_lab_report": {"ts", "report_ref"},
}
```

(b) `tests/test_lab_services.py`: `import yaml` ergänzen und ans Dateiende:

```python
# ---------------------------------------------------------------------------
# Service-Schema-Mirror (REQ-HOM-123/128)
# ---------------------------------------------------------------------------


def test_req_hom_123_marker_options_mirror_the_catalog_in_both_services():
    """[REQ-HOM-123] `add_lab_value` und `add_lab_report` kennen exakt `LAB_MARKERS`."""
    import yaml

    const_module = sys.modules[f"{_PKG}.const"]
    with open(os.path.join(_COMPONENT_DIR, "services.yaml"), encoding="utf-8") as fh:
        services = yaml.safe_load(fh)

    single = {
        option["value"]
        for option in services["add_lab_value"]["fields"]["marker"]["selector"]["select"][
            "options"
        ]
    }
    batch = {
        option["value"]
        for option in services["add_lab_report"]["fields"]["values"]["selector"]["object"][
            "fields"
        ]["marker"]["selector"]["select"]["options"]
    }

    expected = set(const_module.LAB_MARKERS)
    assert single == expected, "add_lab_value driftet gegen den Katalog"
    assert batch == expected, "add_lab_report driftet gegen den Katalog"


def test_req_hom_128_remove_lab_report_fields_and_required_ts():
    """[REQ-HOM-128] Undo-Service: person/ts/report_ref, `ts` ist Pflicht."""
    import yaml

    with open(os.path.join(_COMPONENT_DIR, "services.yaml"), encoding="utf-8") as fh:
        services = yaml.safe_load(fh)

    fields = services["remove_lab_report"]["fields"]
    assert set(fields) == {"person", "ts", "report_ref"}
    assert fields["ts"].get("required") is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_translations.py -k "lab_services_have_translation_parity" tests/test_lab_services.py -k "req_hom_123 or req_hom_128" -q`
Expected: FAIL — `AssertionError: services.yaml: add_lab_report fehlt` und
`KeyError: 'remove_lab_report'`.

- [ ] **Step 3: Implement — `services.yaml`**

Direkt **nach** `add_lab_value` (vor `remove_last_lab_value`, `services.yaml:431`)
`add_lab_report` einfügen:

```yaml
add_lab_report:
  name: Laborbericht erfassen
  description: >-
    Erfasst mehrere Laborwerte eines Berichts in einem Vorgang — gleicher
    Zeitpunkt, gleiche Berichts-Referenz, Alles-oder-nichts: eine ungültige
    Zeile lehnt den gesamten Bericht ab. Leere Zeilen werden ignoriert. Ein
    erneuter Aufruf schreibt erneut (nicht idempotent).
  fields:
    person:
      name: Person
      description: Name der Person (leer = einzige konfigurierte Person).
      example: "Caro"
    ts:
      name: Zeitpunkt
      description: >-
        Zeitpunkt des Berichts als ISO 8601 (z. B. 2026-11-01T09:15 oder mit
        Offset). Leer = jetzt. Höchstens 5 Minuten in der Zukunft, nicht vor 1900.
      example: "2026-11-01T09:15:00+01:00"
    report_ref:
      name: Berichts-Referenz
      description: >-
        Optionaler Link oder externe ID des Laborberichts (max. 500 Zeichen).
        Nur Referenz, Health-O-Mat ruft die URL nie selbst auf.
      example: "https://example.com/laborbericht/123"
    values:
      name: Werte
      description: Zeilen aus Marker, Wert und (optionaler) Einheit.
      required: true
      selector:
        object:
          multiple: true
          label_field: marker
          fields:
            marker:
              label: Marker
              required: true
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
              label: Wert
              required: true
              selector:
                number:
                  step: any
                  mode: box
            unit:
              label: Einheit
              selector:
                text:
```

Direkt **nach** `remove_last_lab_value` (Dateiende) `remove_lab_report` einfügen:

```yaml
remove_lab_report:
  name: Laborbericht verwerfen
  description: >-
    Verwirft alle aktiven Laborwerte eines Berichts (gemeinsamer Zeitpunkt).
    Ist eine Berichts-Referenz gesetzt, werden nur Einträge mit exakt diesem
    Tag verworfen. Kein Treffer ist ein Fehler. Verwerfen markiert die Werte
    als gelöscht; sie bleiben einzeln über restore_entry wiederherstellbar.
  fields:
    person:
      name: Person
      description: Name der Person (leer = einzige konfigurierte Person).
      example: "Caro"
    ts:
      name: Zeitpunkt
      description: >-
        Zeitpunkt des Berichts als ISO 8601 — derselbe Wert wie beim Erfassen
        (z. B. aus panel_data.labs.last_report.ts). Pflichtfeld.
      example: "2026-11-01T09:15:00+01:00"
      required: true
    report_ref:
      name: Berichts-Referenz
      description: >-
        Optional: grenzt das Verwerfen auf genau diesen Tag ein (max. 500
        Zeichen). Ohne Angabe werden alle aktiven Werte dieses Zeitpunkts
        verworfen.
      example: "https://example.com/laborbericht/123"
```

- [ ] **Step 4: Implement — i18n**

`strings.json` (`services`):

```json
"add_lab_report": {
  "name": "Record lab report",
  "description": "Records several lab values of one report in a single operation — same timestamp, same report reference, all-or-nothing: one invalid row rejects the whole report. Empty rows are ignored. Calling it again writes the values again (not idempotent).",
  "fields": {
    "values": {
      "name": "Values",
      "description": "Rows of marker, value and (optional) unit."
    },
    "ts": {
      "name": "Timestamp",
      "description": "Time of the report (ISO 8601, e.g. 2026-11-01T09:15 or with offset). Empty = now. At most 5 minutes in the future, not before 1900."
    },
    "report_ref": {
      "name": "Report reference",
      "description": "Optional link or external ID of the lab report (max 500 characters). Reference only, Health-O-Mat never fetches the URL itself."
    }
  }
},
"remove_lab_report": {
  "name": "Discard lab report",
  "description": "Discards all active lab values of one report (shared timestamp). With a report reference only entries carrying exactly that tag are discarded. No match is an error. Discarded values are marked as deleted and stay individually restorable via restore_entry.",
  "fields": {
    "ts": {
      "name": "Timestamp",
      "description": "Timestamp of the report (ISO 8601) — the same value used when recording it (e.g. from panel_data.labs.last_report.ts). Required."
    },
    "report_ref": {
      "name": "Report reference",
      "description": "Optional: limits the discard to exactly this tag (max 500 characters). Without it all active values of that timestamp are discarded."
    }
  }
}
```

`translations/de.json`:

```json
"add_lab_report": {
  "name": "Laborbericht erfassen",
  "description": "Erfasst mehrere Laborwerte eines Berichts in einem Vorgang — gleicher Zeitpunkt, gleiche Berichts-Referenz, Alles-oder-nichts: eine ungültige Zeile lehnt den gesamten Bericht ab. Leere Zeilen werden ignoriert. Ein erneuter Aufruf schreibt erneut (nicht idempotent).",
  "fields": {
    "values": {
      "name": "Werte",
      "description": "Zeilen aus Marker, Wert und (optionaler) Einheit."
    },
    "ts": {
      "name": "Zeitpunkt",
      "description": "Zeitpunkt des Berichts als ISO 8601 (z. B. 2026-11-01T09:15 oder mit Offset). Leer = jetzt. Höchstens 5 Minuten in der Zukunft, nicht vor 1900."
    },
    "report_ref": {
      "name": "Berichts-Referenz",
      "description": "Optionaler Link oder externe ID des Laborberichts (max. 500 Zeichen). Nur Referenz, Health-O-Mat ruft die URL nie selbst auf."
    }
  }
},
"remove_lab_report": {
  "name": "Laborbericht verwerfen",
  "description": "Verwirft alle aktiven Laborwerte eines Berichts (gemeinsamer Zeitpunkt). Ist eine Berichts-Referenz gesetzt, werden nur Einträge mit exakt diesem Tag verworfen. Kein Treffer ist ein Fehler. Verwerfen markiert die Werte als gelöscht; sie bleiben einzeln über restore_entry wiederherstellbar.",
  "fields": {
    "ts": {
      "name": "Zeitpunkt",
      "description": "Zeitpunkt des Berichts als ISO 8601 — derselbe Wert wie beim Erfassen (z. B. aus panel_data.labs.last_report.ts). Pflichtfeld."
    },
    "report_ref": {
      "name": "Berichts-Referenz",
      "description": "Optional: grenzt das Verwerfen auf genau diesen Tag ein (max. 500 Zeichen). Ohne Angabe werden alle aktiven Werte dieses Zeitpunkts verworfen."
    }
  }
}
```

`translations/en.json`: identisch zu `strings.json`.

- [ ] **Step 5: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_translations.py -q && python3 -m pytest tests/test_lab_services.py -k "req_hom_123 or req_hom_128" -q`
Expected: all PASS.

- [ ] **Step 6: Regression**

Run: `python3 -m pytest tests/test_translations.py tests/test_lab_services.py -q && ruff check . && ruff format --check .`
Expected: grün/clean.

- [ ] **Step 7: Commit**

```bash
git add custom_components/health_o_mat/services.yaml custom_components/health_o_mat/strings.json custom_components/health_o_mat/translations/de.json custom_components/health_o_mat/translations/en.json tests/test_translations.py tests/test_lab_services.py
git commit -m "feat: declare lab report and discard services"
```

---

### Task 6: `__init__.py` — Service `add_lab_report` + `add_lab_value`-Härtung

**Files:**
- Modify: `custom_components/health_o_mat/__init__.py`
- Test: `tests/test_lab_services.py`

**Interfaces:**
- Consumes: `logic.validate_lab_report_rows`, `logic.lab_report_error`,
  `logic.coerce_lab_number` (Task 1), `store.add_lab_readings` (Task 3),
  `get_runtime_data` (`__init__.py:485`), `_service_entry_ts` (`__init__.py:592`),
  `_entry_options` (`__init__.py:583`), `_entry_audit_limit`, `_service_actor`,
  `signal_refresh`, `LAB_REPORT_REF_MAX_LEN`, `OPTION_LAB_CUSTOM_MARKERS`,
  `homeassistant.helpers.config_validation as cv`.
- Produces: registrierter Service `health_o_mat.add_lab_report`; Eintrag in
  `_SERVICE_NAMES` (`__init__.py:73-87`); gehärteter `add_lab_value`
  (`invalid_value` statt `NaN`/`inf`-Write).

**Spec-Bezug:** §2.2 (Voluptuous), §2.5 (Reihenfolge Person → `invalid_ts` → Zeilen),
§2.7 (kein Rückgabewert), §2.10 (`report_ref`-Cap), §2.5 (`NaN`/`inf` **fixed**).

- [ ] **Step 1: Write the failing tests** (ans Ende von `tests/test_lab_services.py`)

```python
# ---------------------------------------------------------------------------
# add_lab_report (REQ-HOM-123)
# ---------------------------------------------------------------------------


def test_req_hom_123_add_lab_report_writes_one_batch_with_shared_context():
    store = MagicMock()
    store.add_lab_readings = AsyncMock(return_value=["r1", "r2"])
    hass = MagicMock()
    registered = _wire_services(hass, store)
    call = _make_call(
        {
            "values": [
                {"marker": "alt", "value": 32, "unit": "U/L"},
                {"marker": "creatinine", "value": 1.1, "unit": "mg/dL"},
            ],
            # Vergangenheit relativ zu `dt_util.now()` (echte HA-Uhr im Test).
            "ts": "2026-10-30T09:15:00+01:00",
            "report_ref": "  Labor 10/2026  ",
        }
    )

    assert _run(registered["add_lab_report"](call)) is None

    store.add_lab_readings.assert_awaited_once()
    args, kwargs = store.add_lab_readings.call_args
    assert args[0] == "e1"
    assert args[1] == "2026-10-30T09:15:00+01:00"
    assert [row["marker_key"] for row in args[2]] == ["alt", "creatinine"]
    assert args[2][1]["unit"] == "µmol/L"
    assert kwargs["report_ref"] == "Labor 10/2026"


def test_req_hom_123_add_lab_report_ignores_empty_rows():
    store = MagicMock()
    store.add_lab_readings = AsyncMock(return_value=["r1"])
    hass = MagicMock()
    registered = _wire_services(hass, store)
    call = _make_call(
        {"values": [{"marker": "alt", "value": 32}, {}, {"marker": "", "value": ""}]}
    )

    _run(registered["add_lab_report"](call))

    rows = store.add_lab_readings.call_args.args[2]
    assert [row["marker_key"] for row in rows] == ["alt"]


def test_req_hom_123_add_lab_report_rejects_unknown_marker_without_write():
    store = MagicMock()
    hass = MagicMock()
    registered = _wire_services(hass, store)
    call = _make_call(
        {
            "values": [
                {"marker": "alt", "value": 32},
                {"marker": "crp", "value": 4.8},
                {"marker": "gptx", "value": 1},
            ]
        }
    )

    with pytest.raises(
        ServiceValidationError, match=r"Zeile 3 \(gptx\): unknown_marker"
    ):
        _run(registered["add_lab_report"](call))

    store.add_lab_readings.assert_not_awaited()


def test_req_hom_123_add_lab_report_prefixes_invalid_ts():
    store = MagicMock()
    hass = MagicMock()
    registered = _wire_services(hass, store)
    call = _make_call({"values": [{"marker": "alt", "value": 32}], "ts": "kaputt"})

    with pytest.raises(ServiceValidationError, match="^invalid_ts: "):
        _run(registered["add_lab_report"](call))

    store.add_lab_readings.assert_not_awaited()


def test_req_hom_123_add_lab_report_resolves_person_before_timestamp():
    """Ein unbekannter Entry meldet den Entry-Fehler, nicht `invalid_ts` (§2.5)."""
    store = MagicMock()
    hass = MagicMock()
    registered = _wire_services(hass, store)
    call = _make_call(
        {"person": "niemand", "values": [{"marker": "alt", "value": 32}], "ts": "kaputt"}
    )

    with pytest.raises(ServiceValidationError, match="nicht gefunden"):
        _run(registered["add_lab_report"](call))


def test_req_hom_123_add_lab_report_caps_report_ref_length():
    store = MagicMock()
    store.add_lab_readings = AsyncMock(return_value=["r1"])
    hass = MagicMock()
    registered = _wire_services(hass, store)
    call = _make_call(
        {"values": [{"marker": "alt", "value": 32}], "report_ref": "x" * 600}
    )

    _run(registered["add_lab_report"](call))

    assert len(store.add_lab_readings.call_args.kwargs["report_ref"]) == 500


def test_req_hom_123_add_lab_report_schema_allows_empty_row_and_rejects_extra():
    hass = MagicMock()
    _registered, schemas = _wire_services_and_schemas(hass, MagicMock())
    schema = schemas["add_lab_report"]

    parsed = schema({"values": [{}], "ts": "2026-11-01T09:15:00+01:00"})
    assert parsed["values"] == [{}]
    parsed = schema({"values": {"marker": "alt", "value": "32.5"}})
    assert parsed["values"] == [{"marker": "alt", "value": "32.5"}]

    with pytest.raises(vol.Invalid):
        schema({"values": [{"marker": "alt", "value": 1, "bogus": 2}]})
    with pytest.raises(vol.Invalid):
        schema({"ts": "2026-11-01T09:15:00+01:00"})


def test_req_hom_123_add_lab_value_rejects_nan_and_inf():
    store = MagicMock()
    store.add_lab_reading = AsyncMock()
    hass = MagicMock()
    registered = _wire_services(hass, store)

    for bad in (float("nan"), float("inf")):
        with pytest.raises(ServiceValidationError, match="invalid_value"):
            _run(registered["add_lab_value"](_make_call({"marker": "alt", "value": bad})))

    store.add_lab_reading.assert_not_awaited()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_lab_services.py -k req_hom_123 -q`
Expected: FAIL — `KeyError: 'add_lab_report'`; der `NaN`-Test scheitert an einer
`float`-Meldung statt `invalid_value`.

- [ ] **Step 3: Implement**

(a) Import ergänzen (alphabetisch vor `update_coordinator`):

```python
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
```

(b) `_SERVICE_NAMES` (`__init__.py:73-87`) nach `"add_lab_value"` um
`"add_lab_report"` erweitern.

(c) Handler direkt nach `add_lab_value` (`__init__.py:783`) einfügen:

```python
    async def add_lab_report(call: ServiceCall) -> None:
        """Laborbericht (mehrere Werte) als EINEN Vorgang erfassen (REQ-HOM-123).

        Reihenfolge ist Vertrag (§2.5): Person → Zeitpunkt → Zeilen. Eine
        ungültige Zeile lehnt den gesamten Bericht ab; es wird nichts
        geschrieben. Leere Zeilen werden ignoriert.
        """
        entry_id, _info = get_runtime_data(hass, call)
        options = _entry_options(hass, entry_id)
        now = dt_util.now()
        raw_ts = call.data.get("ts")
        try:
            ts_iso = _service_entry_ts(call, now) or now.isoformat()
        except ServiceValidationError as err:
            raise ServiceValidationError(
                logic.lab_report_error("invalid_ts", {"value": raw_ts})["message"]
            ) from err
        rows, error = logic.validate_lab_report_rows(
            call.data.get("values"), options.get(OPTION_LAB_CUSTOM_MARKERS)
        )
        if error is not None:
            raise ServiceValidationError(error["message"])
        report_ref = (
            (call.data.get("report_ref") or "").strip()[:LAB_REPORT_REF_MAX_LEN] or None
        )
        store: HealthOMatStore = hass.data[DOMAIN]["shared"]["store"]
        await store.add_lab_readings(
            entry_id,
            ts_iso,
            rows,
            report_ref=report_ref,
            created_ts_iso=now.isoformat(),
            actor=_service_actor(call),
            audit_limit=_entry_audit_limit(hass, entry_id),
        )
        signal_refresh(hass, entry_id)
```

(d) `add_lab_value` härten (`__init__.py:761`): die Zeile

```python
        value = float(call.data["value"])
```

ersetzen durch

```python
        value = logic.coerce_lab_number(call.data["value"])
        if value is None:
            raise ServiceValidationError("invalid_value")
```

(e) Registrierung nach dem `add_lab_value`-Block (`__init__.py:1012`):

```python
    hass.services.async_register(
        DOMAIN,
        "add_lab_report",
        schema=vol.Schema(
            {
                vol.Optional("person"): str,
                vol.Optional("ts"): str,
                vol.Optional("report_ref"): str,
                vol.Required("values"): vol.All(
                    cv.ensure_list,
                    [
                        vol.Schema(
                            {
                                # Bewusst Optional: die UI sendet leere Zeilen, und
                                # ein `{}`-Eintrag ist eine ignorierte Leerzeile.
                                vol.Optional("marker"): str,
                                vol.Optional("value"): vol.Any(str, int, float),
                                vol.Optional("unit"): vol.Any(str, None),
                            }
                        )
                    ],
                ),
            }
        ),
        service_func=add_lab_report,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_lab_services.py -k req_hom_123 -q`
Expected: all PASS.

- [ ] **Step 5: Regression**

Run: `python3 -m pytest tests/test_lab_services.py tests/test_wave_a.py -q && ruff check custom_components/health_o_mat/__init__.py tests/test_lab_services.py && ruff format --check custom_components/health_o_mat/__init__.py tests/test_lab_services.py`
Expected: grün/clean (bestehende `add_lab_value`-Tests bleiben grün).

- [ ] **Step 6: Commit**

```bash
git add custom_components/health_o_mat/__init__.py tests/test_lab_services.py
git commit -m "feat: add add_lab_report service handler"
```

---

### Task 7: `__init__.py` — Service `remove_lab_report` (Batch-Undo)

**Files:**
- Modify: `custom_components/health_o_mat/__init__.py`
- Test: `tests/test_lab_services.py`

**Interfaces:**
- Consumes: `store.void_lab_report` (Task 4), `logic.lab_report_error` (Task 1),
  `get_runtime_data`, `_service_entry_ts`, `_entry_audit_limit`, `_service_actor`,
  `signal_refresh`, `LAB_REPORT_REF_MAX_LEN`.
- Produces: registrierter Service `health_o_mat.remove_lab_report` + `_SERVICE_NAMES`-Eintrag.
  Kein Rückgabewert; `no_active_report` → `ServiceValidationError`.

**Spec-Bezug:** §2.13 (Semantik, `report_ref`-Filter, Grenzfall gleicher `ts`),
§2.7 (Fehler), §2.9 (ein Audit `lab_report_voided`).

- [ ] **Step 1: Write the failing tests** (ans Ende von `tests/test_lab_services.py`)

```python
# ---------------------------------------------------------------------------
# remove_lab_report (REQ-HOM-128)
# ---------------------------------------------------------------------------


def test_req_hom_128_remove_lab_report_voids_report_with_ref():
    store = MagicMock()
    store.void_lab_report = AsyncMock(return_value=["r1", "r2"])
    hass = MagicMock()
    registered = _wire_services(hass, store)
    call = _make_call(
        {
            "ts": "2026-11-01T09:15:00+01:00",
            "report_ref": "  Labor 10/2026  ",
        }
    )

    assert _run(registered["remove_lab_report"](call)) is None

    store.void_lab_report.assert_awaited_once()
    args, kwargs = store.void_lab_report.call_args
    assert args == ("e1", "2026-11-01T09:15:00+01:00")
    assert kwargs["report_ref"] == "Labor 10/2026"


def test_req_hom_128_remove_lab_report_without_ref_passes_none():
    store = MagicMock()
    store.void_lab_report = AsyncMock(return_value=["r1"])
    hass = MagicMock()
    registered = _wire_services(hass, store)

    _run(
        registered["remove_lab_report"](
            _make_call({"ts": "2026-11-01T09:15:00+01:00"})
        )
    )

    assert store.void_lab_report.call_args.kwargs["report_ref"] is None


def test_req_hom_128_remove_lab_report_no_match_raises():
    store = MagicMock()
    store.void_lab_report = AsyncMock(return_value=[])
    hass = MagicMock()
    registered = _wire_services(hass, store)

    with pytest.raises(ServiceValidationError, match="no_active_report"):
        _run(
            registered["remove_lab_report"](
                _make_call({"ts": "2026-11-01T09:15:00+01:00"})
            )
        )


def test_req_hom_128_remove_lab_report_invalid_ts_raises_with_prefix():
    store = MagicMock()
    hass = MagicMock()
    registered = _wire_services(hass, store)

    with pytest.raises(ServiceValidationError, match="^invalid_ts: "):
        _run(registered["remove_lab_report"](_make_call({"ts": "kaputt"})))

    store.void_lab_report.assert_not_awaited()


def test_req_hom_128_remove_lab_report_caps_report_ref_length():
    store = MagicMock()
    store.void_lab_report = AsyncMock(return_value=["r1"])
    hass = MagicMock()
    registered = _wire_services(hass, store)

    _run(
        registered["remove_lab_report"](
            _make_call({"ts": "2026-11-01T09:15:00+01:00", "report_ref": "x" * 600})
        )
    )

    assert len(store.void_lab_report.call_args.kwargs["report_ref"]) == 500


def test_req_hom_128_remove_lab_report_schema_requires_ts():
    hass = MagicMock()
    _registered, schemas = _wire_services_and_schemas(hass, MagicMock())
    schema = schemas["remove_lab_report"]

    parsed = schema({"ts": "2026-11-01T09:15:00+01:00"})
    assert parsed["ts"] == "2026-11-01T09:15:00+01:00"

    with pytest.raises(vol.Invalid):
        schema({})
    with pytest.raises(vol.Invalid):
        schema({"ts": "2026-11-01T09:15:00+01:00", "bogus": 1})
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_lab_services.py -k req_hom_128_remove -q`
Expected: FAIL — `KeyError: 'remove_lab_report'`.

- [ ] **Step 3: Implement**

(a) `_SERVICE_NAMES` um `"remove_lab_report"` erweitern.

(b) Handler direkt nach `add_lab_report` einfügen:

```python
    async def remove_lab_report(call: ServiceCall) -> None:
        """Laborbericht verwerfen — alle aktiven Werte eines Zeitpunkts (REQ-HOM-128).

        Mit ``report_ref`` werden nur Einträge mit exakt diesem Tag getroffen.
        Ohne Treffer: ``no_active_report``. Kein Gruppen-Restore — einzeln über
        ``restore_entry`` (``kind: lab_values``).
        """
        entry_id, _info = get_runtime_data(hass, call)
        now = dt_util.now()
        raw_ts = call.data.get("ts")
        try:
            ts_iso = _service_entry_ts(call, now)
        except ServiceValidationError as err:
            raise ServiceValidationError(
                logic.lab_report_error("invalid_ts", {"value": raw_ts})["message"]
            ) from err
        if ts_iso is None:
            raise ServiceValidationError(
                logic.lab_report_error("invalid_ts", {"value": raw_ts})["message"]
            )
        report_ref = (
            (call.data.get("report_ref") or "").strip()[:LAB_REPORT_REF_MAX_LEN] or None
        )
        store: HealthOMatStore = hass.data[DOMAIN]["shared"]["store"]
        voided = await store.void_lab_report(
            entry_id,
            ts_iso,
            report_ref=report_ref,
            actor=_service_actor(call),
            audit_limit=_entry_audit_limit(hass, entry_id),
        )
        if not voided:
            raise ServiceValidationError(
                logic.lab_report_error("no_active_report", {"ts": ts_iso})["message"]
            )
        signal_refresh(hass, entry_id)
```

(c) Registrierung nach dem `add_lab_report`-Block:

```python
    hass.services.async_register(
        DOMAIN,
        "remove_lab_report",
        schema=vol.Schema(
            {
                vol.Optional("person"): str,
                vol.Required("ts"): str,
                vol.Optional("report_ref"): str,
            }
        ),
        service_func=remove_lab_report,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_lab_services.py -k req_hom_128_remove -q`
Expected: all PASS.

- [ ] **Step 5: Regression**

Run: `python3 -m pytest tests/test_lab_services.py -q && ruff check custom_components/health_o_mat/__init__.py tests/test_lab_services.py`
Expected: grün/clean.

- [ ] **Step 6: Commit**

```bash
git add custom_components/health_o_mat/__init__.py tests/test_lab_services.py
git commit -m "feat: add remove_lab_report service"
```

---

### Task 8: Optionen-Persistenz — `lab_retention_months` (Wizard, Lauf, Backup, Diagnostics)

**Files:**
- Modify: `custom_components/health_o_mat/config_flow.py`
- Modify: `custom_components/health_o_mat/__init__.py`
- Modify: `custom_components/health_o_mat/backup.py`
- Modify: `custom_components/health_o_mat/diagnostics.py`
- Modify: `custom_components/health_o_mat/strings.json`, `translations/{de,en}.json`
- Test: `tests/test_config_flow.py`, `tests/test_lab_services.py`,
  `tests/test_import_backup.py`, `tests/test_diagnostics.py`

**Interfaces:**
- Consumes: `logic.months_ago` (`logic.py:125`), `store.void_lab_readings_before` (Task 4),
  `const.OPTION_LAB_RETENTION_MONTHS`/`OPTION_LAB_HIDE_PANEL_DISCLAIMER`/
  `MAX_RETENTION_MONTHS` (`const.py:34`), `_entry_audit_limit`, `signal_refresh`.
- Produces:
  - `__init__._lab_retention_months(entry) -> int`
  - `__init__._apply_lab_retention(hass, entry, store) -> None` — No-op bei `<= 0`;
    sonst `cutoff = logic.months_ago(dt_util.now(), months)` →
    `store.void_lab_readings_before(..., months=months)` → `signal_refresh` nur bei Treffern.
  - Aufrufe im Setup (nach `_apply_retention`, `__init__.py:227`) und im Options-Listener
    (nach `_apply_retention`, `__init__.py:444`).
  - `config_flow`-Feld `lab_retention_months` im Schritt `basics` (Default 0, 0…120).
  - `backup.lab_options` enthält `lab_retention_months` **und**
    `lab_hide_panel_disclaimer` (Default `0`/`False`).
  - `diagnostics._LAB_OPTION_KEYS` enthält beide Schlüssel.

**Spec-Bezug:** §2.14 (Option, Laufzeitpunkt, Idempotenz, Audit nur bei `count > 0`),
§2.16 (Backup), §8.6 (Diagnostics-Redaktion), §11.

- [ ] **Step 1: Write the failing tests**

(a) `tests/test_lab_services.py` — Imports ergänzen (`from datetime import UTC, datetime`)
und ans Dateiende:

```python
# ---------------------------------------------------------------------------
# Labor-Retention (REQ-HOM-129)
# ---------------------------------------------------------------------------


def test_req_hom_129_lab_retention_months_reads_options_or_zero():
    assert hass_init._lab_retention_months(_wire_entry_like({})) == 0
    assert (
        hass_init._lab_retention_months(
            _wire_entry_like({"lab_retention_months": 24})
        )
        == 24
    )
    assert (
        hass_init._lab_retention_months(
            _wire_entry_like({"lab_retention_months": "x"})
        )
        == 0
    )


def _wire_entry_like(options: dict):
    entry = MagicMock()
    entry.entry_id = "e1"
    entry.options = options
    return entry


def test_req_hom_129_apply_lab_retention_default_off_is_noop(monkeypatch):
    store = MagicMock()
    store.void_lab_readings_before = AsyncMock()
    entry = _wire_entry_like({})
    hass = MagicMock()

    _run(hass_init._apply_lab_retention(hass, entry, store))

    store.void_lab_readings_before.assert_not_awaited()


def test_req_hom_129_apply_lab_retention_voids_before_cutoff(monkeypatch):
    store = MagicMock()
    store.void_lab_readings_before = AsyncMock(return_value=["r1"])
    entry = _wire_entry_like({"lab_retention_months": 12})
    hass = MagicMock()
    monkeypatch.setattr(
        hass_init.dt_util,
        "now",
        lambda: datetime(2026, 11, 1, 12, 0, tzinfo=UTC),
    )

    _run(hass_init._apply_lab_retention(hass, entry, store))

    store.void_lab_readings_before.assert_awaited_once()
    args, kwargs = store.void_lab_readings_before.call_args
    assert args[0] == "e1"
    assert args[1] == "2025-11-01T12:00:00+00:00"
    assert kwargs["months"] == 12
```

(b) `tests/test_config_flow.py` — `import voluptuous as vol` ergänzen und ans Dateiende:

```python
# --- REQ-HOM-129: Labor-Retention im Grundlagen-Schritt ---------------------


def test_req_hom_129_basics_step_exposes_lab_retention():
    options_flow = _make_flow(options={"lab_retention_months": 24})

    result = _async_test(options_flow.async_step_basics(None))

    assert "lab_retention_months" in result["data_schema"].schema
    defaults = _schema_defaults(result)
    assert defaults["lab_retention_months"] == 24


def test_req_hom_129_basics_step_rejects_out_of_range_lab_retention():
    options_flow = _make_flow()
    schema = _async_test(options_flow.async_step_basics(None))["data_schema"]

    with pytest.raises(vol.Invalid):
        schema({"daily_goal_ml": 2000, "lab_retention_months": 121})
```

(c) `tests/test_import_backup.py` — den bestehenden Test
`test_req_hom_122_async_backup_collects_lab_options_from_entries` anpassen
(Erwartung um zwei Schlüssel erweitern) und einen Test für die gesetzten Werte ergänzen:

```python
    assert document["lab_options"] == {
        "e1": {
            "lab_custom_markers": [{"key": "vitamin_d"}],
            "lab_ref_overrides": {"alt": {"ref_min": 5}},
            "lab_hidden_categories": ["thyroid"],
            "lab_hide_panel_disclaimer": False,
            "lab_retention_months": 0,
        },
        "e2": {
            "lab_custom_markers": [],
            "lab_ref_overrides": {},
            "lab_hidden_categories": [],
            "lab_hide_panel_disclaimer": False,
            "lab_retention_months": 0,
        },
    }


def test_req_hom_129_backup_collects_lab_retention_and_disclaimer(tmp_path, monkeypatch):
    store = _fresh_store()
    _run(store.set_person("e1", "Max"))
    hass = MagicMock()
    hass.config.path = MagicMock(return_value=str(tmp_path))
    hass.async_add_executor_job = AsyncMock(side_effect=lambda fn: fn())
    hass.services.async_call = AsyncMock()
    entry = MagicMock()
    entry.entry_id = "e1"
    entry.options = {
        const_module.OPTION_LAB_RETENTION_MONTHS: 24,
        const_module.OPTION_LAB_HIDE_PANEL_DISCLAIMER: True,
    }
    hass.config_entries = MagicMock()
    hass.config_entries.async_entries = MagicMock(return_value=[entry])
    monkeypatch.setattr(
        backup, "dt_util", types.SimpleNamespace(now=lambda: datetime(2026, 10, 14, 12, 0, 0))
    )

    path = _run(backup.async_backup(hass, store))

    document = json.loads(Path(path).read_text(encoding="utf-8"))
    assert document["lab_options"]["e1"]["lab_retention_months"] == 24
    assert document["lab_options"]["e1"]["lab_hide_panel_disclaimer"] is True
```

(d) `tests/test_diagnostics.py` — nach `test_redact_lab_options_as_counts_only`:

```python
def test_req_hom_129_redacts_new_lab_options_as_counts_only():
    """[REQ-HOM-129] Retention/Disclaimer werden als reine Zähler redigiert."""
    options = {
        const.OPTION_LAB_RETENTION_MONTHS: 24,
        const.OPTION_LAB_HIDE_PANEL_DISCLAIMER: True,
    }

    out = diagnostics.redact_diagnostics({"options": options})

    # Skalare haben keine Sequenzlänge → `count` 0; der Wert selbst leakt nie.
    assert out["options"][const.OPTION_LAB_RETENTION_MONTHS] == {"count": 0}
    assert out["options"][const.OPTION_LAB_HIDE_PANEL_DISCLAIMER] == {"count": 0}
    assert isinstance(out["options"][const.OPTION_LAB_RETENTION_MONTHS], dict)
    assert isinstance(out["options"][const.OPTION_LAB_HIDE_PANEL_DISCLAIMER], dict)
```

> Hinweis: `_LAB_OPTION_KEYS` redigiert **alle** dort gelisteten Schlüssel einheitlich als
> `{"count": n}` (`diagnostics._option_count`); Skalare ergeben `0`, Listen/Maps ihre Länge.

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_lab_services.py -k req_hom_129 tests/test_config_flow.py -k req_hom_129 tests/test_import_backup.py -k "req_hom_122_async_backup_collects or req_hom_129" tests/test_diagnostics.py -k req_hom_129 -q`
Expected: FAIL — `AttributeError: ... '_apply_lab_retention'`; fehlender Schema-Key;
Backup-Erwartung weicht ab; Diagnostics-Key fehlt.

- [ ] **Step 3: Implement — `config_flow.py`**

Import ergänzen (`const`-Block):

```python
    OPTION_LAB_RETENTION_MONTHS,
```

Feld im `async_step_basics`-Schema direkt nach `retention_months`
(`config_flow.py:431-433`):

```python
                    # Labor-Retention (REQ-HOM-129): eigene Option, unabhängig von
                    # `retention_months`; 0 = AUS (Default = bisheriges Verhalten).
                    vol.Optional(
                        OPTION_LAB_RETENTION_MONTHS,
                        default=int(self._option(OPTION_LAB_RETENTION_MONTHS, 0) or 0),
                    ): vol.All(vol.Coerce(int), vol.Range(min=0, max=MAX_RETENTION_MONTHS)),
```

- [ ] **Step 4: Implement — `__init__.py`**

(a) Import ergänzen (`const`-Block): `OPTION_LAB_RETENTION_MONTHS`.

(b) Nach `_retention_months` (`__init__.py:253-258`) einfügen:

```python
def _lab_retention_months(entry) -> int:
    """Labor-Retention in Monaten aus den Options (0/ungültig = AUS)."""
    try:
        return int(entry.options.get(OPTION_LAB_RETENTION_MONTHS) or 0)
    except (TypeError, ValueError):
        return 0


async def _apply_lab_retention(hass: HomeAssistant, entry, store: HealthOMatStore) -> None:
    """Labor-Retention: alte aktive Werte voiden (REQ-HOM-129).

    Eigener Schritt NEBEN `_apply_retention` (Getränke/BD) — kein Archiv, keine
    Listenkürzung. Default 0 = no-op; idempotent (voidete Einträge zählen nie
    erneut), Audit nur bei Treffern (macht der Store).
    """
    months = _lab_retention_months(entry)
    if months <= 0:
        return
    cutoff = logic.months_ago(dt_util.now(), months)
    voided = await store.void_lab_readings_before(
        entry.entry_id,
        cutoff.isoformat(),
        audit_limit=_entry_audit_limit(hass, entry.entry_id),
        months=months,
    )
    if voided:
        signal_refresh(hass, entry.entry_id)
```

> `_entry_audit_limit` ist zum Aufrufzeitpunkt auf Modulebene definiert — keine
> Reihenfolgeabhängigkeit.

(c) Setup (`__init__.py:227`): direkt nach `await _apply_retention(hass, entry, store)`:

```python
    await _apply_lab_retention(hass, entry, store)
```

(d) Options-Listener (`__init__.py:444`): direkt nach
`await _apply_retention(hass, entry, store)`:

```python
    await _apply_lab_retention(hass, entry, store)
```

- [ ] **Step 5: Implement — `backup.py`**

Import ergänzen (`const`-Block): `OPTION_LAB_HIDE_PANEL_DISCLAIMER`,
`OPTION_LAB_RETENTION_MONTHS`. In `lab_options` (`backup.py:167-171`) zwei Schlüssel:

```python
            OPTION_LAB_HIDE_PANEL_DISCLAIMER: bool(
                entry.options.get(OPTION_LAB_HIDE_PANEL_DISCLAIMER, False)
            ),
            OPTION_LAB_RETENTION_MONTHS: int(
                entry.options.get(OPTION_LAB_RETENTION_MONTHS, 0) or 0
            ),
```

- [ ] **Step 6: Implement — `diagnostics.py`**

Import ergänzen und `_LAB_OPTION_KEYS` (`diagnostics.py:57-63`) erweitern:

```python
        OPTION_LAB_HIDE_PANEL_DISCLAIMER,
        OPTION_LAB_RETENTION_MONTHS,
```

- [ ] **Step 7: Implement — i18n (Options-Schritt)**

`strings.json` → `options.step.basics.data`:

```json
          "lab_retention_months": "Lab value retention in months (0 = off)",
```

`translations/de.json`:

```json
          "lab_retention_months": "Aufbewahrung der Laborwerte in Monaten (0 = aus)",
```

`translations/en.json`: identisch zu `strings.json`.

- [ ] **Step 8: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_lab_services.py -k req_hom_129 tests/test_config_flow.py -k req_hom_129 tests/test_import_backup.py -k "req_hom_122_async_backup_collects or req_hom_129" tests/test_diagnostics.py -k req_hom_129 -q`
Expected: all PASS.

- [ ] **Step 9: Regression**

Run: `python3 -m pytest tests/test_config_flow.py tests/test_import_backup.py tests/test_diagnostics.py tests/test_lab_services.py tests/test_translations.py tests/test_wave_a.py -q && ruff check . && ruff format --check .`
Expected: grün/clean.

- [ ] **Step 10: Commit**

```bash
git add custom_components/health_o_mat/config_flow.py custom_components/health_o_mat/__init__.py custom_components/health_o_mat/backup.py custom_components/health_o_mat/diagnostics.py custom_components/health_o_mat/strings.json custom_components/health_o_mat/translations/de.json custom_components/health_o_mat/translations/en.json tests/test_config_flow.py tests/test_lab_services.py tests/test_import_backup.py tests/test_diagnostics.py
git commit -m "feat: add lab retention option and wiring"
```

---

## Wave 3 — WS & Panel-Payload

### Task 9: `ws_api.py` — Kommandos `add_lab_report`/`remove_lab_report` + Fehler-Envelope

**Files:**
- Modify: `custom_components/health_o_mat/ws_api.py`
- Test: `tests/test_ws_api.py`

**Interfaces:**
- Consumes: `logic.validate_lab_report_rows`, `logic.lab_report_error`,
  `logic.coerce_lab_number` (Task 1), `store.add_lab_readings`/`void_lab_report`
  (Tasks 3/4), `_store`, `_runtime_entry`, `_entry_ready`, `_send_entry_error`,
  `parse_entry_ts` (`ws_api.py:806`), `signal_refresh`, `user_id_of`, `_audit_limit`.
- Produces:
  - `COMMAND_ADD_LAB_REPORT = "health_o_mat/add_lab_report"`,
    `COMMAND_REMOVE_LAB_REPORT = "health_o_mat/remove_lab_report"` (neben
    `COMMAND_ADD_LAB_VALUE`, `ws_api.py:107`).
  - Erfolg: `{"ok": True, "written": n, "ts": ts_iso}` bzw.
    `{"ok": True, "voided": n}`.
  - Fachfehler: `send_result(id, {"ok": False, "error": {code, params, message}})`.
  - `send_error` **nur** Entry-/Transportfehler (`_send_entry_error`).

**Spec-Bezug:** §3 (beide Kommandos, `PREVENT_EXTRA`, Envelope), §2.4 (Fehlerobjekt),
§2.7 (Erfolg), §6.2 (kein `require_explicit_unit` im Payload).

- [ ] **Step 1: Write the failing tests**

(a) `_write_store()` (`tests/test_ws_api.py:197`) um zwei Mocks erweitern:

```python
    store.add_lab_readings = AsyncMock()
    store.void_lab_report = AsyncMock(return_value=["r1"])
```

(b) `import datetime`? — die Datei nutzt `from datetime import datetime` bereits. Tests ans
Dateiende:

```python
# --- REQ-HOM-123/128: WS-Batch ----------------------------------------------


def test_req_hom_123_websocket_add_lab_report_returns_success_envelope(monkeypatch):
    _now(monkeypatch)
    store = _write_store()
    store.add_lab_readings = AsyncMock(return_value=["r1", "r2"])
    hass = _write_hass(store, [_entry("e1")])
    connection = FakeConnection()

    asyncio.run(
        ws_api.websocket_add_lab_report(
            hass,
            connection,
            {
                "id": 21,
                "type": ws_api.COMMAND_ADD_LAB_REPORT,
                "entry_id": "e1",
                # `_now()` pinnt NOW = 2026-10-15 → ts muss davor liegen.
                "ts": "2026-10-14T09:15:00+02:00",
                "report_ref": "  Labor 10/2026  ",
                "values": [
                    {"marker": "alt", "value": 32},
                    {"marker": "creatinine", "value": 1.1, "unit": "mg/dL"},
                    {},
                ],
            },
        )
    )

    assert connection.errors == []
    assert connection.results == [
        (21, {"ok": True, "written": 2, "ts": "2026-10-14T09:15:00+02:00"})
    ]
    args, kwargs = store.add_lab_readings.call_args
    assert args[0] == "e1"
    assert args[1] == "2026-10-14T09:15:00+02:00"
    assert [row["marker_key"] for row in args[2]] == ["alt", "creatinine"]
    assert kwargs["report_ref"] == "Labor 10/2026"


def test_req_hom_123_websocket_add_lab_report_sends_structured_error(monkeypatch):
    _now(monkeypatch)
    store = _write_store()
    hass = _write_hass(store, [_entry("e1")])
    connection = FakeConnection()

    asyncio.run(
        ws_api.websocket_add_lab_report(
            hass,
            connection,
            {
                "id": 22,
                "type": ws_api.COMMAND_ADD_LAB_REPORT,
                "entry_id": "e1",
                "values": [{"marker": "alt", "value": 32}, {"marker": "gptx", "value": 1}],
            },
        )
    )

    assert connection.errors == []
    assert connection.results == [
        (
            22,
            {
                "ok": False,
                "error": {
                    "code": "unknown_marker",
                    "params": {"row": 2, "marker": "gptx"},
                    "message": "Zeile 2 (gptx): unknown_marker",
                },
            },
        )
    ]
    store.add_lab_readings.assert_not_awaited()


def test_req_hom_123_websocket_add_lab_report_invalid_ts_envelope(monkeypatch):
    _now(monkeypatch)
    store = _write_store()
    hass = _write_hass(store, [_entry("e1")])
    connection = FakeConnection()

    asyncio.run(
        ws_api.websocket_add_lab_report(
            hass,
            connection,
            {
                "id": 23,
                "type": ws_api.COMMAND_ADD_LAB_REPORT,
                "entry_id": "e1",
                "ts": "kaputt",
                "values": [{"marker": "alt", "value": 32}],
            },
        )
    )

    assert connection.errors == []
    result = connection.results[0][1]
    assert result["ok"] is False
    assert result["error"]["code"] == "invalid_ts"
    assert result["error"]["params"] == {"value": "kaputt"}
    assert result["error"]["message"].startswith("invalid_ts: ")
    store.add_lab_readings.assert_not_awaited()


def test_req_hom_123_websocket_add_lab_report_unknown_entry_stays_send_error(monkeypatch):
    _now(monkeypatch)
    store = _write_store()
    hass = _write_hass(store, [_entry("e1")])
    connection = FakeConnection()

    asyncio.run(
        ws_api.websocket_add_lab_report(
            hass,
            connection,
            {
                "id": 24,
                "type": ws_api.COMMAND_ADD_LAB_REPORT,
                "entry_id": "unknown",
                "ts": "kaputt",
                "values": [{"marker": "alt", "value": 32}],
            },
        )
    )

    assert connection.results == []
    assert connection.errors[0][1] == ws_api.ERR_NOT_FOUND


def test_req_hom_128_websocket_remove_lab_report_success(monkeypatch):
    _now(monkeypatch)
    store = _write_store()
    store.void_lab_report = AsyncMock(return_value=["r1", "r2"])
    hass = _write_hass(store, [_entry("e1")])
    connection = FakeConnection()

    asyncio.run(
        ws_api.websocket_remove_lab_report(
            hass,
            connection,
            {
                "id": 25,
                "type": ws_api.COMMAND_REMOVE_LAB_REPORT,
                "entry_id": "e1",
                "ts": "2026-10-14T09:15:00+02:00",
                "report_ref": "Labor A",
            },
        )
    )

    assert connection.errors == []
    assert connection.results == [(25, {"ok": True, "voided": 2})]
    args, kwargs = store.void_lab_report.call_args
    assert args == ("e1", "2026-10-14T09:15:00+02:00")
    assert kwargs["report_ref"] == "Labor A"


def test_req_hom_128_websocket_remove_lab_report_no_match_envelope(monkeypatch):
    _now(monkeypatch)
    store = _write_store()
    store.void_lab_report = AsyncMock(return_value=[])
    hass = _write_hass(store, [_entry("e1")])
    connection = FakeConnection()

    asyncio.run(
        ws_api.websocket_remove_lab_report(
            hass,
            connection,
            {
                "id": 26,
                "type": ws_api.COMMAND_REMOVE_LAB_REPORT,
                "entry_id": "e1",
                "ts": "2026-10-14T09:15:00+02:00",
            },
        )
    )

    assert connection.results[0][1]["ok"] is False
    assert connection.results[0][1]["error"]["code"] == "no_active_report"


def test_req_hom_123_lab_report_commands_are_registered(monkeypatch):
    registered: list[tuple] = []
    hass = FakeHass()
    monkeypatch.setattr(
        ws_api.websocket_api,
        "async_register_command",
        lambda *args: registered.append(args),
    )

    asyncio.run(ws_api.async_register_ws_api(hass))

    schemas = {args[1]: args[3] for args in registered}
    add_schema = schemas[ws_api.COMMAND_ADD_LAB_REPORT]
    parsed = add_schema(
        {
            "id": 1,
            "type": ws_api.COMMAND_ADD_LAB_REPORT,
            "entry_id": "e1",
            "values": [{"marker": "alt", "value": "32.5"}, {}],
        }
    )
    assert parsed["values"][0]["value"] == "32.5"
    assert parsed["values"][1] == {}
    with pytest.raises(vol.Invalid):
        add_schema(
            {
                "id": 2,
                "type": ws_api.COMMAND_ADD_LAB_REPORT,
                "entry_id": "e1",
                "values": [{"marker": "alt", "value": 1, "bogus": 2}],
            }
        )
    with pytest.raises(vol.Invalid):
        add_schema({"id": 3, "type": ws_api.COMMAND_ADD_LAB_REPORT, "values": []})

    remove_schema = schemas[ws_api.COMMAND_REMOVE_LAB_REPORT]
    with pytest.raises(vol.Invalid):
        remove_schema({"id": 4, "type": ws_api.COMMAND_REMOVE_LAB_REPORT, "entry_id": "e1"})


def test_req_hom_123_websocket_add_lab_value_rejects_nan(monkeypatch):
    _now(monkeypatch)
    store = _write_store()
    hass = _write_hass(store, [_entry("e1")])
    connection = FakeConnection()

    asyncio.run(
        ws_api.websocket_add_lab_value(
            hass,
            connection,
            {
                "id": 27,
                "type": ws_api.COMMAND_ADD_LAB_VALUE,
                "entry_id": "e1",
                "marker": "alt",
                "value": float("nan"),
            },
        )
    )

    assert connection.results == []
    assert connection.errors == [(27, ws_api.ERR_INVALID_FORMAT, "invalid_value")]
    store.add_lab_reading.assert_not_awaited()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_ws_api.py -k "req_hom_123_websocket or req_hom_128_websocket or lab_report_commands" -q`
Expected: FAIL — `AttributeError: module 'ws_api' has no attribute 'COMMAND_ADD_LAB_REPORT'`.

- [ ] **Step 3: Implement**

(a) Konstanten nach `COMMAND_ADD_LAB_VALUE` (`ws_api.py:107`):

```python
COMMAND_ADD_LAB_REPORT = "health_o_mat/add_lab_report"
COMMAND_REMOVE_LAB_REPORT = "health_o_mat/remove_lab_report"
```

(b) Registrierungs-Tupel nach dem `COMMAND_ADD_LAB_VALUE`-Eintrag (`ws_api.py:987`):

```python
        (
            COMMAND_ADD_LAB_REPORT,
            websocket_add_lab_report,
            {
                vol.Required("entry_id"): str,
                vol.Optional("ts"): str,
                vol.Optional("report_ref"): str,
                vol.Required("values"): [
                    vol.Schema(
                        {
                            # Leerzeilen sind erlaubt (§2.3): alle drei Felder
                            # Optional; die Pflicht-Semantik prüft der Handler.
                            vol.Optional("marker"): str,
                            vol.Optional("value"): vol.Any(str, int, float),
                            vol.Optional("unit"): vol.Any(str, None),
                        }
                    )
                ],
            },
        ),
        (
            COMMAND_REMOVE_LAB_REPORT,
            websocket_remove_lab_report,
            {
                vol.Required("entry_id"): str,
                vol.Required("ts"): str,
                vol.Optional("report_ref"): str,
            },
        ),
```

(c) Handler nach `websocket_add_lab_value` (`ws_api.py:1365`) einfügen:

```python
def _lab_error_result(error: dict[str, Any]) -> dict[str, Any]:
    """Fachfehler-Envelope der Batch-Kommandos (§3)."""
    return {"ok": False, "error": error}


async def websocket_add_lab_report(
    hass: HomeAssistant, connection: Any, msg: dict[str, Any]
) -> None:
    """`health_o_mat/add_lab_report` → Bericht als EINEN Vorgang (REQ-HOM-123).

    Reihenfolge wie beim Service (§2.5): Entry → Zeitpunkt → Zeilen. Fachfehler
    kommen als Ergebnis-Envelope (strukturiert), `send_error` bleibt Entry-/
    Transportfehlern vorbehalten.
    """
    entry_id = msg["entry_id"]
    store = _store(hass)
    entry = _runtime_entry(hass, entry_id)
    if store is None or entry is None or not _entry_ready(hass, entry_id):
        _send_entry_error(connection, msg, entry_id)
        return
    options = getattr(entry, "options", None) or {}
    now = dt_util.now()
    try:
        ts_iso = parse_entry_ts(msg.get("ts"), now) or now.isoformat()
    except ValueError:
        connection.send_result(
            msg["id"],
            _lab_error_result(
                logic.lab_report_error("invalid_ts", {"value": msg.get("ts")})
            ),
        )
        return
    rows, error = logic.validate_lab_report_rows(
        msg.get("values"), options.get(OPTION_LAB_CUSTOM_MARKERS)
    )
    if error is not None:
        connection.send_result(msg["id"], _lab_error_result(error))
        return
    report_ref = (msg.get("report_ref") or "").strip()[:LAB_REPORT_REF_MAX_LEN] or None
    await store.add_lab_readings(
        entry_id,
        ts_iso,
        rows,
        report_ref=report_ref,
        created_ts_iso=now.isoformat(),
        actor=user_id_of(connection),
        audit_limit=_audit_limit(hass, entry_id),
    )
    signal_refresh(hass, entry_id)
    connection.send_result(msg["id"], {"ok": True, "written": len(rows), "ts": ts_iso})


async def websocket_remove_lab_report(
    hass: HomeAssistant, connection: Any, msg: dict[str, Any]
) -> None:
    """`health_o_mat/remove_lab_report` → Bericht verwerfen (REQ-HOM-128)."""
    entry_id = msg["entry_id"]
    store = _store(hass)
    entry = _runtime_entry(hass, entry_id)
    if store is None or entry is None or not _entry_ready(hass, entry_id):
        _send_entry_error(connection, msg, entry_id)
        return
    now = dt_util.now()
    try:
        ts_iso = parse_entry_ts(msg["ts"], now)
    except ValueError:
        ts_iso = None
    if ts_iso is None:
        connection.send_result(
            msg["id"],
            _lab_error_result(logic.lab_report_error("invalid_ts", {"value": msg["ts"]})),
        )
        return
    report_ref = (msg.get("report_ref") or "").strip()[:LAB_REPORT_REF_MAX_LEN] or None
    voided = await store.void_lab_report(
        entry_id,
        ts_iso,
        report_ref=report_ref,
        actor=user_id_of(connection),
        audit_limit=_audit_limit(hass, entry_id),
    )
    if not voided:
        connection.send_result(
            msg["id"],
            _lab_error_result(logic.lab_report_error("no_active_report", {"ts": ts_iso})),
        )
        return
    signal_refresh(hass, entry_id)
    connection.send_result(msg["id"], {"ok": True, "voided": len(voided)})
```

(d) Einzelpfad härten (`ws_api.py:1335-1342`): den Block

```python
    try:
        reported_value = float(msg.get("value"))
        canonical_value, canonical_unit = logic.convert_lab_value(
            marker_def, reported_value, raw_unit
        )
    except (TypeError, ValueError) as err:
        connection.send_error(msg["id"], ERR_INVALID_FORMAT, str(err) or "invalid_value")
        return
```

ersetzen durch:

```python
    reported_value = logic.coerce_lab_number(msg.get("value"))
    if reported_value is None:
        connection.send_error(msg["id"], ERR_INVALID_FORMAT, "invalid_value")
        return
    try:
        canonical_value, canonical_unit = logic.convert_lab_value(
            marker_def, reported_value, raw_unit
        )
    except (TypeError, ValueError) as err:
        connection.send_error(msg["id"], ERR_INVALID_FORMAT, str(err) or "unsupported_unit")
        return
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_ws_api.py -k "req_hom_123_websocket or req_hom_128_websocket or lab_report_commands" -q`
Expected: all PASS.

- [ ] **Step 5: Regression**

Run: `python3 -m pytest tests/test_ws_api.py tests/test_lab_services.py -q && ruff check custom_components/health_o_mat/ws_api.py tests/test_ws_api.py && ruff format --check custom_components/health_o_mat/ws_api.py tests/test_ws_api.py`
Expected: grün/clean.

- [ ] **Step 6: Commit**

```bash
git add custom_components/health_o_mat/ws_api.py tests/test_ws_api.py
git commit -m "feat: add lab report websocket commands"
```

---

### Task 10: `ws_api.py` — `panel_data` (+3 Felder) + Disclaimer-Settings-Backend

**Files:**
- Modify: `custom_components/health_o_mat/ws_api.py`
- Test: `tests/test_ws_api.py`

**Interfaces:**
- Consumes: `_labs_block` (`ws_api.py:629`), `store.active_lab_readings`,
  `lab_reading_chrono_key` (`store.py:1197`), `SETTINGS_KEYS` (`ws_api.py:192`),
  `SETTINGS_SCHEMA` (`ws_api.py:258`), `_strict_bool` (`ws_api.py:230`),
  `build_settings` (`ws_api.py:1615`), `parse_settings_message` (`ws_api.py:1663`).
- Produces:
  - `_labs_block` marker-Feld `alt_units: dict[str, float]` (Katalog + Custom).
  - `_labs_block` Rückgabe-Feld `last_report: {"ts": str|None, "marker_keys": [str],
    "report_ref": str|None}` — neuester gemeinsamer **Instant**; `report_ref` ist für die
    Verwerfen-Aktion (§6.5) nötig und liegt **innerhalb** von `last_report` (die Spec
    nennt drei neue Payload-Bereiche: `alt_units`, `last_report`,
    `lab_hide_panel_disclaimer`).
  - Top-Level `lab_hide_panel_disclaimer: bool` (Default `false`).
  - `OPTION_LAB_HIDE_PANEL_DISCLAIMER` in `SETTINGS_KEYS` + `SETTINGS_SCHEMA`
    (`_strict_bool`), `build_settings` liefert den Boolean.
- **Kein** `require_explicit_unit` im Payload.

**Spec-Bezug:** §6.2 (drei Felder, Präzedenz `quick_drinks`/`wellbeing_confirm`), §6.5
(`last_report` inkl. Tag), §7.4/§8.3 (Admin-Schreibpfad, strikter Bool).

- [ ] **Step 1: Write the failing tests** (ans Ende von `tests/test_ws_api.py`)

```python
# --- REQ-HOM-123/125: panel_data-Zusatzfelder -------------------------------


def test_req_hom_123_panel_data_labs_marker_exposes_alt_units(monkeypatch):
    entry = _entry(
        options={
            "lab_custom_markers": [
                {
                    "key": "vitamin_d",
                    "name": "Vitamin D",
                    "category": "other",
                    "unit": "ng/mL",
                    "alt_unit": {"unit": "nmol/L", "factor_to_canonical": 0.4},
                }
            ]
        }
    )
    hass, _store_mock = _lab_panel_hass(entry, monkeypatch)

    markers = ws_api.build_panel_data(hass, "e1", NOW)["labs"]["markers"]

    assert markers["creatinine"]["alt_units"] == {"mg/dL": 88.4}
    assert markers["alt"]["alt_units"] == {}
    assert markers["vitamin_d"]["alt_units"] == {"nmol/L": 0.4}
    # Bewusst NICHT im Payload (§6.2).
    assert "require_explicit_unit" not in markers["urine_protein_creatinine_ratio"]


def test_req_hom_123_panel_data_last_report_uses_latest_common_instant(monkeypatch):
    hass, store = _lab_panel_hass(_entry(), monkeypatch)
    store.active_lab_readings.return_value = [
        {"ts": "2026-10-01T09:00:00+01:00", "marker_key": "alt", "value": 32.0},
        {"ts": "2026-10-31T09:00:00+01:00", "marker_key": "alt", "value": 33.0},
        {"ts": "2026-10-31T08:00:00+00:00", "marker_key": "crp", "value": 4.8,
         "report_ref": "Labor A"},
        {"ts": "2026-10-01T09:00:00+01:00", "marker_key": "tsh", "value": 1.9},
    ]

    last = ws_api.build_panel_data(hass, "e1", NOW)["labs"]["last_report"]

    assert last["ts"] == "2026-10-31T09:00:00+01:00"
    assert last["marker_keys"] == ["alt", "crp"]
    assert last["report_ref"] == "Labor A"


def test_req_hom_123_panel_data_last_report_empty_without_readings(monkeypatch):
    hass, _store_mock = _lab_panel_hass(_entry(), monkeypatch)

    assert ws_api.build_panel_data(hass, "e1", NOW)["labs"]["last_report"] == {
        "ts": None,
        "marker_keys": [],
        "report_ref": None,
    }


def test_req_hom_125_panel_data_carries_disclaimer_flag(monkeypatch):
    hass, _store_mock = _lab_panel_hass(_entry(), monkeypatch)
    assert ws_api.build_panel_data(hass, "e1", NOW)["lab_hide_panel_disclaimer"] is False

    ward = _entry("e1", options={"lab_hide_panel_disclaimer": True})
    hass2, _store2 = _lab_panel_hass(ward, monkeypatch)
    assert ws_api.build_panel_data(hass2, "e1", NOW)["lab_hide_panel_disclaimer"] is True


def test_req_hom_125_settings_accepts_and_returns_disclaimer_flag(monkeypatch):
    entry = _entry("e1", options={"daily_goal_ml": 2000})
    hass = _settings_hass(entry)
    connection = _admin_connection()

    asyncio.run(
        ws_api.websocket_set_settings(
            hass,
            connection,
            _settings_msg(ws_api.COMMAND_SET_SETTINGS, entry_id="e1",
                          lab_hide_panel_disclaimer=True),
        )
    )

    assert connection.errors == []
    assert hass.config_entries.updates[0]["options"]["lab_hide_panel_disclaimer"] is True
    assert connection.results[0][1]["lab_hide_panel_disclaimer"] is True


def test_req_hom_125_settings_rejects_non_boolean_disclaimer(monkeypatch):
    entry = _entry("e1", options={"daily_goal_ml": 2000})
    hass = _settings_hass(entry)
    connection = _admin_connection()

    asyncio.run(
        ws_api.websocket_set_settings(
            hass,
            connection,
            _settings_msg(ws_api.COMMAND_SET_SETTINGS, entry_id="e1",
                          lab_hide_panel_disclaimer="true"),
        )
    )

    assert connection.errors, "ein String darf kein stiller Boolean sein"
    assert hass.config_entries.updates == []


def test_req_hom_129_settings_merge_keeps_lab_retention(monkeypatch):
    entry = _entry(
        "e1", options={"daily_goal_ml": 2000, "lab_retention_months": 24}
    )
    hass = _settings_hass(entry)
    connection = _admin_connection()

    asyncio.run(
        ws_api.websocket_set_settings(
            hass,
            connection,
            _settings_msg(ws_api.COMMAND_SET_SETTINGS, entry_id="e1",
                          lab_hide_panel_disclaimer=True),
        )
    )

    stored = hass.config_entries.updates[0]["options"]
    assert stored["lab_retention_months"] == 24
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_ws_api.py -k "alt_units or last_report or disclaimer_flag or non_boolean_disclaimer or merge_keeps_lab_retention" -q`
Expected: FAIL — `KeyError: 'alt_units'` / `KeyError: 'last_report'` / unbekannter
Settings-Key (`lab_hide_panel_disclaimer` fehlt in `SETTINGS_KEYS`).

- [ ] **Step 3: Implement — `panel_data`**

(a) In `_labs_block` (`ws_api.py:629-680`) im Marker-Dict nach `"unit"`:

```python
            # Additiv (REQ-HOM-123): Alt-Einheiten fürs Einheiten-Dropdown.
            # Katalog: `alt_units`; Custom: das eine optionale Alt-Paar.
            "alt_units": dict(marker_def.get("alt_units") or {}),
```

(b) Nach der Marker-Schleife vor dem `return`:

```python
    return {
        "categories": categories,
        "markers": markers,
        "last_report": _last_report(store, entry.entry_id),
    }
```

(c) Vor `_labs_block` (oder direkt danach) einfügen:

```python
def _last_report(store: Any, entry_id: str) -> dict[str, Any]:
    """Bericht mit dem neuesten gemeinsamen Zeitpunkt (§6.2).

    „Bericht" = alle aktiven Marker, deren neuester aktiver Wert denselben
    Instant trägt (Offset-Schreibweisen zählen zusammen). ``report_ref`` ist der
    erste nicht-leere Tag dieses Berichts — die Verwerfen-Aktion (§6.5) sendet
    ihn mit, damit nur genau dieser Bericht getroffen wird.
    """
    empty = {"ts": None, "marker_keys": [], "report_ref": None}
    if store is None:
        return empty
    newest: dict[str, dict] = {}
    for reading in store.active_lab_readings(entry_id):
        key = reading.get("marker_key")
        if not key:
            continue
        current = newest.get(key)
        if current is None or lab_reading_chrono_key(reading) > lab_reading_chrono_key(current):
            newest[key] = reading
    if not newest:
        return empty
    latest_instant = max(lab_reading_chrono_key(item)[0] for item in newest.values())
    members = [
        item for item in newest.values() if lab_reading_chrono_key(item)[0] == latest_instant
    ]
    anchor = max(members, key=lab_reading_chrono_key)
    report_ref = next(
        (item.get("report_ref") for item in members if item.get("report_ref")), None
    )
    return {
        "ts": anchor.get("ts"),
        "marker_keys": sorted(str(item.get("marker_key")) for item in members),
        "report_ref": report_ref,
    }
```

(d) Top-Level in `build_panel_data` (nach `OPTION_WELLBEING_CONFIRM`):

```python
        # Additiv (REQ-HOM-125): Disclaimer-Zustand für den Lab-Tab — NICHT über
        # das admin-only `get_settings`, sonst wäre er für Nicht-Admins leer.
        OPTION_LAB_HIDE_PANEL_DISCLAIMER: bool(
            options.get(OPTION_LAB_HIDE_PANEL_DISCLAIMER, False)
        ),
```

- [ ] **Step 4: Implement — Settings-Backend**

(a) `SETTINGS_KEYS` nach `OPTION_LAB_HIDDEN_CATEGORIES`:

```python
    OPTION_LAB_HIDE_PANEL_DISCLAIMER,
```

(b) `SETTINGS_SCHEMA` (nach `OPTION_WELLBEING_CONFIRM`):

```python
        # Panel-Disclaimer-Schalter (REQ-HOM-125): strikt bool, kein Coerce.
        vol.Optional(OPTION_LAB_HIDE_PANEL_DISCLAIMER): _strict_bool,
```

(c) `build_settings` nach `OPTION_LAB_HIDDEN_CATEGORIES`:

```python
        OPTION_LAB_HIDE_PANEL_DISCLAIMER: bool(
            options.get(OPTION_LAB_HIDE_PANEL_DISCLAIMER, False)
        ),
```

`parse_settings_message` braucht keine Sonderbehandlung — der Schlüssel läuft durch
`SETTINGS_SCHEMA` (`strict bool`), und `websocket_set_settings` merged mit den bestehenden
Optionen (`{**current_options, **updates}`, `ws_api.py:1774`), sodass
`lab_retention_months` erhalten bleibt.

- [ ] **Step 5: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_ws_api.py -k "alt_units or last_report or disclaimer_flag or non_boolean_disclaimer or merge_keeps_lab_retention" -q`
Expected: all PASS.

- [ ] **Step 6: Regression**

Run: `python3 -m pytest tests/test_ws_api.py -q && ruff check custom_components/health_o_mat/ws_api.py tests/test_ws_api.py && ruff format --check custom_components/health_o_mat/ws_api.py tests/test_ws_api.py`
Expected: grün/clean (bestehende `panel_data`-Tests bleiben grün — additive Felder).

- [ ] **Step 7: Commit**

```bash
git add custom_components/health_o_mat/ws_api.py tests/test_ws_api.py
git commit -m "feat: expose lab report metadata in panel data"
```

---

## Wave 4 — UI: Batch-Dialog & Batch-Undo

### Task 11: Card — Mehrzeilen-Dialog (`health-o-mat-labs-card.js`)

**Files:**
- Modify: `custom_components/health_o_mat/www/health-o-mat-labs-card.js`
- Test: `tests/test_card_js.py`

**Interfaces:**
- Consumes (innerhalb der Datei): `_markers()`, `_visibleCategories()`,
  `labMarkerOptionsHtml(markers, selectedKey)`, `escapeHtml`, `TS_FUTURE_TOLERANCE_MS`,
  `this._saving`, `this._actionError`, `this._render`, `this._loadData(true)`,
  `this._hass.connection.sendMessagePromise`.
- Produces (dateiintern, keine Exporte — die Karte ist ein klassisches Script):
  - `LAB_REPORT_MAX_ROWS_UI = 60`
  - `EMPTY_REPORT_ROW()`, `EMPTY_REPORT_DRAFT()`
  - `resultError(result)` / `reportErrorMessage(err)` — liest
    `{"ok": false, "error": {"message": …}}` (strukturierter Fehler, §2.4/§3)
  - Methoden `_reportMarkerOptions`, `_unitOptions`, `_reportRow`, `_reportForm`,
    `_collectReportDraftFromDom`, `_fillReportDraft(mode)`, `_addReportRow`,
    `_removeReportRow`, `_onReportField`, `_onUnitPick`, `_validateTs`, `_readReportTs`,
    `_saveReport`
  - State `this._reportDraft = {ts, reportRef, rows: [{marker, value, unit}]}` und
    `this._fillNote` (Limit-Hinweis)
- WS-Nachricht: `{type:"health_o_mat/add_lab_report", entry_id, values, ts?, report_ref?}`.
- **Kein** Export, kein Import, Karte bleibt standalone (§6.3).

**Spec-Bezug:** §6.1 (inline `<details>`, Hybrid-Knöpfe, Einheiten-Dropdown, 60er-Cap),
§6.2 (Client prüft nur Bericht/Zeit/Wert; `alt_units` aus `panel_data`), §6.4
(Single-Flight, Reset-Semantik, Fehlerbanner aus `error.message`), §12.

- [ ] **Step 1: Write the failing tests** (ans Ende von `tests/test_card_js.py`)

```python
# --- REQ-HOM-123: Mehrzeilen-Dialog der Laborwerte-Karte --------------------


def _js_method_text(source: str, name: str) -> str:
    """Methodenrumpf bis zur nächsten Zeile `  }` (Muster von test_panel_js)."""
    match = re.search(rf"\n\s+(?:async\s+)?{re.escape(name)}\s*\([^)]*\)\s*\{{", source)
    assert match is not None, f"{name}() fehlt"
    end = source.find("\n  }", match.end())
    assert end != -1, f"{name}() hat keinen abschliessenden Block"
    return source[match.end() : end]


def test_req_hom_123_labs_card_report_dialog_shape():
    source = _labs_card_source()

    assert "const LAB_REPORT_MAX_ROWS_UI = 60;" in source
    assert '<details class="labs-report">' in source
    for name in ("_reportForm", "_fillReportDraft", "_saveReport", "_unitOptions"):
        assert re.search(rf"(?:async\s+)?{name}\s*\(", source), f"{name}() fehlt"
    for action in (
        'data-action="lab-report-add"',
        'data-action="lab-report-remove"',
        'data-action="lab-report-save"',
        'data-action="lab-report-fill-visible"',
        'data-action="lab-report-fill-last"',
    ):
        assert action in source, action
    assert 'data-field="lab-report-unit-pick-' in source
    assert 'value="__custom__"' in source
    assert "alt_units" in source
    assert "health_o_mat/add_lab_report" in source


def test_req_hom_123_labs_card_report_single_flight_and_error_envelope():
    source = _labs_card_source()
    body = _js_method_text(source, "_saveReport")

    assert "if (this._saving) return;" in body
    assert "this._saving = true;" in body
    assert "this._saving = false;" in body
    assert "resultError(result)" in body
    assert "result.ok !== false" in source
    # Erfolg: Werte + Zeilen leeren, ts/reportRef NICHT (§6.4).
    assert "rows: [EMPTY_REPORT_ROW()]" in body
    assert 'ts: ""' not in body
    assert 'reportRef: ""' not in body


_NODE_LABS_REPORT_RUNNER = """import { readFileSync } from "node:fs";
import vm from "node:vm";

const source = readFileSync(process.argv[2], "utf8");
const mode = process.argv[3];

class FakeShadowRoot {
  constructor() { this.innerHTML = ""; }
  addEventListener() {}
  removeEventListener() {}
  querySelector() { return null; }
  querySelectorAll() { return []; }
}
class FakeHTMLElement {
  constructor() { this._shadow = new FakeShadowRoot(); }
  attachShadow() { return this._shadow; }
  get shadowRoot() { return this._shadow; }
}
const context = {
  HTMLElement: FakeHTMLElement,
  customElements: {
    _classes: {},
    get() { return undefined; },
    define(tag, cls) { this._classes[tag] = cls; },
  },
  window: {},
  document: { createElement: () => ({}) },
  console: { info: () => {}, log: () => {}, warn: () => {}, error: () => {} },
};
vm.createContext(context);
vm.runInContext(source, context, { filename: "health-o-mat-labs-card.js" });

const CardClass = context.customElements._classes["health-o-mat-labs-card"];
const card = new CardClass();
card._config = { entry_id: "entry-1", person_mode: "fixed" };
card._normalized = null;
card._activeEntry = "entry-1";
card._saving = false;
card._data = {
  person: "Alex",
  labs: {
    categories: [
      { key: "liver", name: "Leber", hidden: false },
      { key: "kidney", name: "Niere", hidden: false },
    ],
    markers: {
      alt: { category: "liver", name: "ALT", unit: "U/L", alt_units: {}, history: [] },
      creatinine: {
        category: "kidney", name: "Kreatinin", unit: "µmol/L",
        alt_units: { "mg/dL": 88.4 }, history: [],
      },
    },
    last_report: {
      ts: "2026-10-30T09:15:00+01:00", marker_keys: ["creatinine"], report_ref: "Labor A",
    },
  },
};
card._reportDraft = {
  ts: "2026-10-30T09:15",
  reportRef: "Labor A",
  rows: [{ marker: "alt", value: "32", unit: "U/L" }],
};
card._collectReportDraftFromDom = () => {};
card._loadData = async () => {};
card._render = () => {};
const sent = [];
card._hass = {
  connection: {
    sendMessagePromise: async (payload) => {
      sent.push(payload);
      if (mode === "fail") {
        return {
          ok: false,
          error: {
            code: "unknown_marker",
            params: { row: 1, marker: "alt" },
            message: "Zeile 1 (alt): unknown_marker",
          },
        };
      }
      return { ok: true, written: 1 };
    },
  },
};

if (mode === "fill") {
  card._fillReportDraft("last");
  process.stdout.write(JSON.stringify({ rows: card._reportDraft.rows }));
} else {
  await card._saveReport();
  process.stdout.write(
    JSON.stringify({
      payload: sent[0],
      draft: card._reportDraft,
      error: card._actionError,
      saving: card._saving,
      calls: sent.length,
    })
  );
}
"""


@pytest.mark.skipif(shutil.which("node") is None, reason="node nicht verfügbar")
def test_req_hom_123_labs_card_report_roundtrip(tmp_path):
    outcomes = {}
    for mode in ("ok", "fail", "fill"):
        outcomes[mode] = json.loads(
            _run_node(
                tmp_path,
                _NODE_LABS_REPORT_RUNNER,
                [str(Path(_LABS_CARD_JS)), mode],
                f"runner_labs_report_{mode}",
            )
        )

    ok = outcomes["ok"]
    assert ok["calls"] == 1
    assert ok["payload"]["type"] == "health_o_mat/add_lab_report"
    assert ok["payload"]["entry_id"] == "entry-1"
    assert ok["payload"]["values"] == [{"marker": "alt", "value": 32, "unit": "U/L"}]
    assert ok["payload"]["ts"].startswith("2026-10-30T09:15")
    assert ok["draft"]["ts"] == "2026-10-30T09:15"
    assert ok["draft"]["reportRef"] == "Labor A"
    assert ok["draft"]["rows"] == [{"marker": "", "value": "", "unit": ""}]
    assert ok["error"] == ""
    assert ok["saving"] is False

    failed = outcomes["fail"]
    assert failed["error"] == "Zeile 1 (alt): unknown_marker"
    assert failed["draft"]["rows"] == [{"marker": "alt", "value": "32", "unit": "U/L"}]
    assert failed["draft"]["ts"] == "2026-10-30T09:15"

    filled = outcomes["fill"]
    assert filled["rows"][0]["marker"] == "alt"
    assert filled["rows"][1]["marker"] == "creatinine"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_card_js.py -k req_hom_123 -q`
Expected: FAIL — `AssertionError` (kein `LAB_REPORT_MAX_ROWS_UI`, keine
`_reportForm`-Methode); der Node-Test scheitert an der fehlenden Methode.

- [ ] **Step 3: Implement — Konstanten, CSS, State**

(a) Nach `const TS_FUTURE_TOLERANCE_MS = 5 * 60 * 1000;` (`Zeile 31`):

```js
// UI-Soft-Cap des Bericht-Dialogs (Render-Schutz). Server-Limit bleibt 200 (§2.5).
const LAB_REPORT_MAX_ROWS_UI = 60;
```

(b) Nach `EMPTY_DRAFT` (`Zeile 254`):

```js
const EMPTY_DRAFT = () => ({ marker: "", value: "", unit: "", ts: "", reportRef: "" });

const EMPTY_REPORT_ROW = () => ({ marker: "", value: "", unit: "" });
const EMPTY_REPORT_DRAFT = () => ({
  ts: "",
  reportRef: "",
  rows: [EMPTY_REPORT_ROW()],
});
```

(c) Im `CARD_CSS`-Block nach `.labs-form-grid`:

```css
  .labs-report { border-top: 1px solid var(--divider-color, rgba(0,0,0,.08)); padding-top: 8px; }
  .labs-report summary { cursor: pointer; font-weight: 600; }
  .labs-report-fill { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 8px; }
  .labs-report-rows { display: flex; flex-direction: column; gap: 8px; margin-top: 8px; }
  .labs-report-row {
    display: grid;
    grid-template-columns: minmax(0, 2fr) minmax(0, 1fr) minmax(0, 1fr) minmax(0, 1fr) auto;
    gap: 8px; align-items: center;
  }
  .labs-report-actions {
    display: flex; justify-content: space-between; gap: 8px;
    margin-top: 8px; flex-wrap: wrap;
  }
```

(d) Konstruktor (`Zeile 344-348`): nach `this._draft = EMPTY_DRAFT();`

```js
    this._reportDraft = EMPTY_REPORT_DRAFT();
    this._fillNote = "";
```

(e) `_selectPerson` (`Zeile 382-386`): nach `this._draft = EMPTY_DRAFT();`

```js
    this._reportDraft = EMPTY_REPORT_DRAFT();
    this._fillNote = "";
```

- [ ] **Step 4: Implement — Helfer + Methoden**

(a) Nach `errorMessage()` (`Zeile 212`) zwei neue Funktionen (der alte
`errorMessage` bleibt unverändert für den Einzelpfad):

```js
/* Strukturierte Batch-Fehler (§2.4/§3): `sendMessagePromise` löst bei
 * {"ok": false} NICHT ab — der Aufrufer muss die Envelope selbst prüfen. */
function resultError(result) {
  if (!result || result.ok !== false) return "";
  const error = result.error && typeof result.error === "object" ? result.error : {};
  return error.message || error.code || "Speichern fehlgeschlagen.";
}

function reportErrorMessage(err) {
  const message = err && err.message ? String(err.message) : String(err == null ? "" : err);
  return message.trim() || "Speichern fehlgeschlagen.";
}
```

(b) Vor `/* ---- Events ---` (nach `_saveValue`) einfügen:

```js
  /* ---- Mehrzeilen-Dialog: Laborbericht (REQ-HOM-123) ---------------------- */

  _reportMarkerOptions(markers, selectedKey) {
    const placeholder = selectedKey
      ? ""
      : '<option value="" selected>— bitte wählen —</option>';
    return `${placeholder}${labMarkerOptionsHtml(markers, selectedKey)}`;
  }

  _unitOptions(marker, selectedUnit) {
    const canonical = (marker && marker.unit) || "";
    const altUnits = Object.keys((marker && marker.alt_units) || {});
    const known = [canonical, ...altUnits].filter(
      (unit, index, all) => unit && all.indexOf(unit) === index
    );
    const current = selectedUnit
      ? known.includes(selectedUnit)
        ? selectedUnit
        : "__custom__"
      : canonical;
    const options = known
      .map(
        (unit) =>
          `<option value="${escapeHtml(unit)}"${
            unit === current ? " selected" : ""
          }>${escapeHtml(unit)}</option>`
      )
      .join("");
    return `${options}<option value="__custom__"${
      current === "__custom__" ? " selected" : ""
    }>Andere …</option>`;
  }

  _reportRow(row, index, markers) {
    const marker = markers[row.marker];
    const disabled = this._saving ? " disabled" : "";
    return `<div class="labs-report-row" data-role="lab-report-row">
      <select data-field="lab-report-marker-${index}" aria-label="Marker"${disabled}>${this._reportMarkerOptions(
        markers,
        row.marker
      )}</select>
      <input type="number" step="any" inputmode="decimal" data-field="lab-report-value-${index}"
        aria-label="Wert" value="${escapeHtml(row.value)}" placeholder="Wert"${disabled} />
      <select data-field="lab-report-unit-pick-${index}" aria-label="Einheit"${disabled}>${this._unitOptions(
        marker,
        row.unit
      )}</select>
      <input type="text" data-field="lab-report-unit-${index}" aria-label="Einheit (Freitext)"
        value="${escapeHtml(row.unit)}" placeholder="${escapeHtml(
          (marker && marker.unit) || "Einheit"
        )}" autocomplete="off"${disabled} />
      <button type="button" class="labs-tab" data-action="lab-report-remove" data-index="${index}"
        aria-label="Zeile entfernen"${disabled}>✕</button>
    </div>`;
  }

  _reportForm() {
    const markers = this._markers();
    if (!Object.keys(markers).length) return "";
    const draft = this._reportDraft;
    const atLimit = draft.rows.length >= LAB_REPORT_MAX_ROWS_UI;
    const disabled = this._saving ? " disabled" : "";
    const addDisabled = this._saving || atLimit ? " disabled" : "";
    const rows = draft.rows
      .map((row, index) => this._reportRow(row, index, markers))
      .join("");
    const note = atLimit
      ? `Höchstens ${LAB_REPORT_MAX_ROWS_UI} Zeilen pro Bericht.`
      : this._fillNote;
    const noteHtml = note ? `<div class="labs-empty">${escapeHtml(note)}</div>` : "";
    return `<details class="labs-report">
      <summary>Laborbericht erfassen</summary>
      <div class="labs-report-fill">
        <button type="button" class="labs-tab" data-action="lab-report-fill-visible"${disabled}>Alle sichtbaren Marker anlegen</button>
        <button type="button" class="labs-tab" data-action="lab-report-fill-last"${disabled}>Zuletzt verwendete Marker anlegen</button>
      </div>
      <div class="labs-form-grid">
        <label>Zeitpunkt
          <input type="datetime-local" data-field="lab-report-ts" aria-label="Zeitpunkt"
            value="${escapeHtml(draft.ts)}" />
        </label>
        <label class="wide">Bericht-Link/ID (optional)
          <input type="text" data-field="lab-report-ref" aria-label="Bericht-Link oder ID"
            value="${escapeHtml(draft.reportRef)}" placeholder="https://… oder Befund-ID"
            autocomplete="off" />
        </label>
      </div>
      <div class="labs-report-rows">${rows}</div>
      ${noteHtml}
      <div class="labs-report-actions">
        <button type="button" class="labs-tab" data-action="lab-report-add"${addDisabled}>＋ Zeile</button>
        <button type="button" class="labs-save" data-action="lab-report-save"${disabled}>${
          this._saving ? "Speichern…" : "Bericht speichern"
        }</button>
      </div>
    </details>`;
  }

  _collectReportDraftFromDom() {
    const read = (field) => {
      const el = this.shadowRoot.querySelector(`[data-field="${field}"]`);
      return el && el.value != null ? String(el.value) : "";
    };
    this._reportDraft.ts = read("lab-report-ts");
    this._reportDraft.reportRef = read("lab-report-ref");
    this._reportDraft.rows = this._reportDraft.rows.map((_row, index) => ({
      marker: read(`lab-report-marker-${index}`),
      value: read(`lab-report-value-${index}`),
      unit: read(`lab-report-unit-${index}`),
    }));
  }

  _fillReportDraft(mode) {
    this._collectReportDraftFromDom();
    const markers = this._markers();
    let keys = [];
    if (mode === "visible") {
      // „sichtbar" = was die Karte tatsächlich als Kategorie zeigt (hidden-Flag
      // UND show_categories-Konfiguration).
      const visible = new Set(this._visibleCategories().map((category) => category.key));
      keys = Object.keys(markers).filter((key) => visible.has(markers[key].category));
    } else {
      const last = this._labs().last_report || {};
      keys = (Array.isArray(last.marker_keys) ? last.marker_keys : []).filter(
        (key) => markers[key]
      );
    }
    const used = new Set(this._reportDraft.rows.map((row) => row.marker).filter(Boolean));
    let limitHit = false;
    for (const key of keys) {
      if (used.has(key)) continue;
      const empty = this._reportDraft.rows.find(
        (row) => !row.marker && !row.value && !row.unit
      );
      if (empty) {
        empty.marker = key;
      } else if (this._reportDraft.rows.length < LAB_REPORT_MAX_ROWS_UI) {
        this._reportDraft.rows.push({ marker: key, value: "", unit: "" });
      } else {
        limitHit = true;
        break;
      }
      used.add(key);
    }
    this._fillNote = limitHit
      ? `Höchstens ${LAB_REPORT_MAX_ROWS_UI} Zeilen pro Bericht.`
      : "";
    this._render();
  }

  _addReportRow() {
    if (this._reportDraft.rows.length >= LAB_REPORT_MAX_ROWS_UI) return;
    this._collectReportDraftFromDom();
    this._reportDraft.rows.push(EMPTY_REPORT_ROW());
    this._render();
  }

  _removeReportRow(index) {
    if (!Number.isInteger(index) || this._reportDraft.rows.length <= 1) return;
    this._collectReportDraftFromDom();
    this._reportDraft.rows.splice(index, 1);
    this._render();
  }

  _onReportField(field, value) {
    if (field === "lab-report-ts") {
      this._reportDraft.ts = value;
      return;
    }
    if (field === "lab-report-ref") {
      this._reportDraft.reportRef = value;
      return;
    }
    const match = /^lab-report-(marker|value|unit)-(\d+)$/.exec(field);
    if (!match) return;
    const row = this._reportDraft.rows[Number(match[2])];
    if (row) row[match[1]] = value;
  }

  _onUnitPick(index, value) {
    const row = this._reportDraft.rows[index];
    if (!row) return;
    row.unit = value === "__custom__" ? "" : value;
    const input = this.shadowRoot.querySelector(`[data-field="lab-report-unit-${index}"]`);
    if (input) input.value = row.unit;
  }

  _validateTs(rawInput) {
    const raw = String(rawInput || "").trim();
    if (!raw) return { iso: "" };
    const parsed = new Date(raw);
    if (!Number.isFinite(parsed.getTime())) {
      return { error: "Ungültiger Zeitpunkt — bitte Datum und Uhrzeit prüfen." };
    }
    if (parsed.getTime() > Date.now() + TS_FUTURE_TOLERANCE_MS) {
      return {
        error:
          "Der Zeitpunkt liegt in der Zukunft (erlaubt sind bis zu 5 Minuten Toleranz).",
      };
    }
    return { iso: parsed.toISOString() };
  }

  _readReportTs() {
    return this._validateTs(this._reportDraft.ts);
  }

  async _saveReport() {
    if (this._saving) return;
    this._collectReportDraftFromDom();
    const entryId = this._activeEntry;
    if (!entryId) {
      this._actionError = "Keine Person ausgewählt.";
      this._render();
      return;
    }
    const ts = this._readReportTs();
    if (ts.error) {
      this._actionError = ts.error;
      this._render();
      return;
    }
    const values = [];
    for (const row of this._reportDraft.rows) {
      const marker = String(row.marker || "").trim();
      const rawValue = String(row.value || "").trim().replace(",", ".");
      const unit = String(row.unit || "").trim();
      if (!marker && !rawValue && !unit) continue;
      if (!marker) {
        this._actionError = "Bitte für jede befüllte Zeile einen Marker auswählen.";
        this._render();
        return;
      }
      if (!/^-?\d+(\.\d+)?$/.test(rawValue)) {
        this._actionError = "Bitte für jede befüllte Zeile einen gültigen Wert eingeben.";
        this._render();
        return;
      }
      values.push(
        unit
          ? { marker, value: Number(rawValue), unit }
          : { marker, value: Number(rawValue) }
      );
    }
    if (!values.length) {
      this._actionError = "Bitte mindestens einen Wert erfassen.";
      this._render();
      return;
    }
    const payload = { type: "health_o_mat/add_lab_report", entry_id: entryId, values };
    if (ts.iso) payload.ts = ts.iso;
    if (String(this._reportDraft.reportRef || "").trim()) {
      payload.report_ref = String(this._reportDraft.reportRef).trim();
    }
    this._saving = true;
    this._actionError = "";
    this._render();
    try {
      const result = await this._hass.connection.sendMessagePromise(payload);
      const failure = resultError(result);
      if (failure) {
        this._actionError = failure;
        return;
      }
      this._actionError = "";
      // Bericht-Kontext (ts/reportRef) bleibt für Nachtrag-Korrekturen stehen
      // (§6.4) — geleert werden nur Wert-Felder und die Zeilenliste.
      this._reportDraft = { ...this._reportDraft, rows: [EMPTY_REPORT_ROW()] };
      this._fillNote = "";
      await this._loadData(true);
    } catch (err) {
      this._actionError = reportErrorMessage(err);
    } finally {
      this._saving = false;
      this._render();
    }
  }
```

- [ ] **Step 5: Implement — `_readEntryTs` vereinheitlichen, Render, Events**

(a) `_readEntryTs` (`Zeile 730-744`) auf den gemeinsamen Validator umstellen
(Verhalten unverändert):

```js
  _readEntryTs() {
    return this._validateTs(this._draft.ts);
  }
```

(b) `_render` (`Zeile 860-885`): nach `const entryForm = ...` ergänzen und im Template
einsetzen:

```js
    const reportForm = hasData && cfg.allowManualEntry ? this._reportForm() : "";
```

```js
          ${body}
          ${entryForm}
          ${reportForm}
```

(c) `_onClick` (`Zeile 809-823`) erweitern:

```js
    if (action === "lab-report-add") {
      this._addReportRow();
      return;
    }
    if (action === "lab-report-remove") {
      this._removeReportRow(Number(el.getAttribute("data-index")));
      return;
    }
    if (action === "lab-report-fill-visible") {
      this._fillReportDraft("visible");
      return;
    }
    if (action === "lab-report-fill-last") {
      this._fillReportDraft("last");
      return;
    }
    if (action === "lab-report-save") this._saveReport();
```

(d) `_onInput` (`Zeile 825-830`) und `_onChange` (`Zeile 832-850`): jeweils nach dem
`data-field`-Lookup

```js
    if (field && field.startsWith("lab-report-")) {
      this._onReportField(field, String(el.value || ""));
      return;
    }
```

(e) In `_onChange` **vor** dem generischen Report-Zweig die Sonderfälle (Marker-Reset +
Einheiten-Picker):

```js
    const markerMatch = /^lab-report-marker-(\d+)$/.exec(field);
    if (markerMatch) {
      this._collectReportDraftFromDom();
      const row = this._reportDraft.rows[Number(markerMatch[1])];
      if (row) {
        row.marker = String(el.value || "");
        row.unit = ""; // Einheiten-Dropdown hängt am Marker
      }
      this._render();
      return;
    }
    const unitPickMatch = /^lab-report-unit-pick-(\d+)$/.exec(field);
    if (unitPickMatch) {
      this._onUnitPick(Number(unitPickMatch[1]), String(el.value || ""));
      return;
    }
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_card_js.py -k req_hom_123 -q`
Expected: all PASS (Node-Test wird ohne `node` sauber übersprungen).

- [ ] **Step 7: Regression**

Run: `python3 -m pytest tests/test_card_js.py tests/test_frontend.py -q && ruff check . && ruff format --check .`
Expected: grün/clean; bestehende `test_req_hom_122_labs_card_*` bleiben grün
(kein Export, kein neuer Import, Karte bleibt standalone).

- [ ] **Step 8: Commit**

```bash
git add custom_components/health_o_mat/www/health-o-mat-labs-card.js tests/test_card_js.py
git commit -m "feat: add multi-row lab report dialog to labs card"
```

---

### Task 12: Panel — Batch-Abschnitt (`health-o-mat-panel-views.js` + `panel.js` + `panel-base.js`)

**Files:**
- Modify: `custom_components/health_o_mat/www/health-o-mat-panel-views.js`
- Modify: `custom_components/health_o_mat/www/health-o-mat-panel.js`
- Modify: `custom_components/health_o_mat/www/health-o-mat-panel-base.js` (WS-Konstante + CSS)
- Modify: `custom_components/health_o_mat/strings.json`, `translations/{de,en}.json` (10 Keys)
- Test: `tests/test_panel_js.py`, `tests/test_translations.py`

**Interfaces:**
- Consumes: `escapeHtml`, `attrValue`, `labMarkerOptionsHtml`, `t`, `WS`,
  `errMsg` (bestehende Importe in `panel-views.js`), `panel._ws`, `panel._busy`,
  `panel._formError`, `panel._reloadEntry(entryId)`.
- Produces:
  - `panel-base.js`: `WS.addLabReport = "health_o_mat/add_lab_report"`.
  - `panel-views.js` (exportiert, damit `panel.js`/Tests sie nutzen):
    `labReportForm(panel, labs, entryId)`, `addLabReportRow(panel, entryId)`,
    `handleLabReportChange(panel, entryId, field, value) -> bool` (true = neu rendern).
  - dateiintern: `LAB_REPORT_MAX_ROWS_UI = 60`, `emptyLabReportRow()`,
    `labReportDraft(panel, entryId)` (defensiv), `collectLabReportDraft`,
    `removeLabReportRow`, `fillLabReportDraft`, `validLabReportTs`,
    `reportMarkerOptions`, `labReportRowHtml`, `submitLabReport`.
  - `panel.js`: `this._labReportDraft = {}` im Konstruktor; `_onChange`-Delegation an
    `handleLabReportChange`.
  - i18n-Keys (`common`): `ui_panel_lab_report_title`, `ui_panel_lab_report_add_row`,
    `ui_panel_lab_report_remove_row`, `ui_panel_lab_report_save`,
    `ui_panel_lab_report_ts`, `ui_panel_lab_marker_choose`,
    `ui_panel_lab_fill_visible`, `ui_panel_lab_fill_last`,
    `ui_panel_lab_report_limit`, `ui_panel_lab_report_empty` (10 Keys).
    (`ui_panel_lab_report_ref`, `ui_panel_lab_marker`, `ui_panel_lab_value_field`,
    `ui_panel_lab_unit_field`, `ui_common_optional`, `ui_panel_val_lab_value` existieren.)

**Spec-Bezug:** §6.1–§6.4 (gleiche Funktionsparität wie die Card, defensiver Draft),
§6.3 (`panel._labReportDraft && panel._labReportDraft[entryId]`), §12 (Paritätstests).

- [ ] **Step 1: Write the failing tests**

(a) `tests/test_panel_js.py` ans Ende:

```python
# --- REQ-HOM-123: Panel-Bericht-Abschnitt -----------------------------------


def test_req_hom_123_panel_base_ws_knows_add_lab_report():
    assert 'addLabReport: "health_o_mat/add_lab_report",' in _panel_base_source()


def test_req_hom_123_panel_views_renders_report_form():
    views = (_WWW_DIR / "health-o-mat-panel-views.js").read_text(encoding="utf-8")
    body = (
        _js_function_block(views, "labReportForm")
        + _js_function_block(views, "labReportRowHtml")
        + _js_function_block(views, "reportMarkerOptions")
        + _js_function_block(views, "unitOptions")
    )

    for needle in (
        "lab-report-ts",
        "lab-report-ref",
        "lab-report-marker-",
        "lab-report-value-",
        "lab-report-unit-pick-",
        'data-action="lab-report-fill-visible"',
        'data-action="lab-report-fill-last"',
        'data-action="lab-report-add"',
        'data-action="lab-report-remove"',
        'data-action="lab-report-save"',
        "labMarkerOptionsHtml(",
        "alt_units",
        "escapeHtml(",
        "attrValue(",
    ):
        assert needle in body, needle
    assert "LAB_REPORT_MAX_ROWS_UI" in views


def test_req_hom_123_panel_entry_module_initialises_report_draft_and_delegates_changes():
    entry = (_WWW_DIR / "health-o-mat-panel.js").read_text(encoding="utf-8")

    assert re.search(r"this\._labReportDraft\s*=\s*\{\s*\}", entry)
    assert "handleLabReportChange" in entry


def test_req_hom_123_panel_report_draft_is_read_defensively():
    views = (_WWW_DIR / "health-o-mat-panel-views.js").read_text(encoding="utf-8")

    assert "panel._labReportDraft && panel._labReportDraft[entryId]" in views


def test_req_hom_123_panel_report_single_flight_context_reset_and_envelope():
    views = (_WWW_DIR / "health-o-mat-panel-views.js").read_text(encoding="utf-8")
    body = _js_function_block(views, "submitLabReport")

    assert "panel._busy" in body
    assert "WS.addLabReport" in body
    assert "resultError(result)" in body
    assert "rows: [emptyLabReportRow()]" in body
    assert 'ts: ""' not in body
    assert 'reportRef: ""' not in body


_NODE_PANEL_REPORT_RUNNER = """import { pathToFileURL } from "node:url";

const base = await import(pathToFileURL(process.argv[2]).href);
const views = await import(pathToFileURL(process.argv[3]).href);
base.setUiLanguage("de");

const panel = {};
const labs = {
  categories: [],
  markers: {
    creatinine: {
      unit: "µmol/L",
      alt_units: { "mg/dL": 88.4 },
    },
  },
  last_report: { ts: null, marker_keys: [], report_ref: null },
};
panel._labReportDraft = {
  "entry-1": { ts: "", reportRef: "", rows: [{ marker: "", value: "", unit: "" }] },
};

const html = views.labReportForm(panel, labs, "entry-1");
const changed = views.handleLabReportChange(
  panel, "entry-1", "lab-report-marker-0", "creatinine"
);
const draft = panel._labReportDraft["entry-1"];
process.stdout.write(JSON.stringify({ html, changed, draft }));
"""


@pytest.mark.skipif(shutil.which("node") is None, reason="node nicht verfügbar")
def test_req_hom_123_panel_report_form_and_change_handler(tmp_path):
    (tmp_path / "package.json").write_text('{"type": "module"}', encoding="utf-8")
    (tmp_path / "health-o-mat-panel-base.js").write_bytes(
        (_WWW_DIR / "health-o-mat-panel-base.js").read_bytes()
    )
    views_path = tmp_path / "health-o-mat-panel-views.js"
    views_path.write_bytes((_WWW_DIR / "health-o-mat-panel-views.js").read_bytes())

    out = json.loads(
        _run_node(
            tmp_path,
            _NODE_PANEL_REPORT_RUNNER,
            [str(tmp_path / "health-o-mat-panel-base.js"), str(views_path)],
            "runner_panel_report",
        )
    )

    assert "mg/dL" in out["html"]
    assert "__custom__" in out["html"]
    assert 'data-action="lab-report-fill-visible"' in out["html"]
    assert out["changed"] is True
    assert out["draft"]["rows"][0]["marker"] == "creatinine"
    assert out["draft"]["rows"][0]["unit"] == ""
```

(b) `tests/test_translations.py`: die zehn Keys in `_REQ_HOM_122_UI_KEYS` aufnehmen.

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_panel_js.py -k req_hom_123 -q && python3 -m pytest tests/test_translations.py -k req_hom_122_common_ui_keys -q`
Expected: FAIL — fehlende `labReportForm`/`handleLabReportChange`; i18n-Test meldet
fehlende Keys.

- [ ] **Step 3: Implement — `panel-base.js`**

Nach `addLabValue: "health_o_mat/add_lab_value",` (`Zeile 135`):

```js
  addLabReport: "health_o_mat/add_lab_report",
```

CSS in `PANEL_CSS` bei den `.lab-*`-Regeln (nach `.lab-entry-form .field`):

```css
  .lab-report-form { margin-top: 8px; }
  .lab-report-form > summary { cursor: pointer; min-height: 44px; display: flex;
    align-items: center; font-weight: 600; }
  .lab-report-fill { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 8px; }
  .lab-report-rows { display: flex; flex-direction: column; gap: 8px; margin-top: 8px; }
  .lab-report-row {
    display: grid;
    grid-template-columns: minmax(0, 2fr) minmax(0, 1fr) minmax(0, 1fr) minmax(0, 1fr) auto;
    gap: 8px; align-items: center;
  }
  .lab-report-actions {
    display: flex; justify-content: space-between; gap: 8px;
    margin-top: 8px; flex-wrap: wrap;
  }
```

- [ ] **Step 4: Implement — `panel.js`**

(a) Nach `this._labCustomDraft = {};` (`Zeile 138`):

```js
    this._labReportDraft = {}; // entry_id -> working copy of a lab report dialog
```

(b) Import aus `panel-views` erweitern (`Zeile 81`):

```js
import {
  renderOverview,
  renderDetail,
  handleLabReportChange,
} from "./health-o-mat-panel-views.js?v=0.16.1";
```

(c) `_onChange` (`Zeile 2219`) am Anfang nach `const field = ...`:

```js
    if (field.startsWith("lab-report-")) {
      const rerender = handleLabReportChange(
        this,
        this._selectedEntry,
        field,
        el.value == null ? "" : String(el.value)
      );
      if (rerender) this._render();
      return;
    }
```

- [ ] **Step 5: Implement — `panel-views.js`**

(a) Import-Block (`Zeile 13-43`) um `attrValue,` erweitern.

(b) Block „Laborbericht" vor `function stepLabCategory` (nach `submitLabValue`):

```js
/* ---- Laborbericht (REQ-HOM-123) ------------------------------------------
 *
 * Panel-lokale Zweitimplementierung des Dialogs (§6.3): die Karte ist
 * standalone; ein Shared-Modul lohnte erst beim dritten Konsumenten.
 */

const LAB_REPORT_MAX_ROWS_UI = 60;

function emptyLabReportRow() {
  return { marker: "", value: "", unit: "" };
}

function labReportDraft(panel, entryId) {
  // Defensiv: Panel-Instanzen überleben Hot-Reloads nicht garantiert (§6.3).
  const existing = panel._labReportDraft && panel._labReportDraft[entryId];
  if (existing) return existing;
  if (!panel._labReportDraft) panel._labReportDraft = {};
  panel._labReportDraft[entryId] = { ts: "", reportRef: "", rows: [emptyLabReportRow()] };
  return panel._labReportDraft[entryId];
}

function collectLabReportDraft(panel, entryId) {
  const draft = labReportDraft(panel, entryId);
  const read = (field) => {
    const el = panel.shadowRoot.querySelector(`[data-field="${field}"]`);
    return el && el.value != null ? String(el.value) : "";
  };
  draft.ts = read("lab-report-ts");
  draft.reportRef = read("lab-report-ref");
  draft.rows = draft.rows.map((_row, index) => ({
    marker: read(`lab-report-marker-${index}`),
    value: read(`lab-report-value-${index}`),
    unit: read(`lab-report-unit-${index}`),
  }));
  return draft;
}

function validLabReportTs(raw) {
  const value = String(raw || "").trim();
  if (!value) return { iso: "" };
  const parsed = new Date(value);
  if (!Number.isFinite(parsed.getTime())) {
    return { error: t("ui_panel_lab_report_ts", "Zeitpunkt") + ": ungültig" };
  }
  return { iso: parsed.toISOString() };
}

function reportMarkerOptions(markers, selectedKey) {
  const placeholder = selectedKey
    ? ""
    : `<option value="" selected>${escapeHtml(
        t("ui_panel_lab_marker_choose", "— bitte wählen —")
      )}</option>`;
  return `${placeholder}${labMarkerOptionsHtml(markers, selectedKey)}`;
}

function unitOptions(marker, selectedUnit) {
  const canonical = (marker && marker.unit) || "";
  const altUnits = Object.keys((marker && marker.alt_units) || {});
  const known = [canonical, ...altUnits].filter(
    (unit, index, all) => unit && all.indexOf(unit) === index
  );
  const current = selectedUnit
    ? known.includes(selectedUnit)
      ? selectedUnit
      : "__custom__"
    : canonical;
  const options = known
    .map(
      (unit) =>
        `<option value="${escapeHtml(unit)}"${
          unit === current ? " selected" : ""
        }>${escapeHtml(unit)}</option>`
    )
    .join("");
  return `${options}<option value="__custom__"${
    current === "__custom__" ? " selected" : ""
  }>${escapeHtml(t("ui_panel_lab_marker_choose", "Andere …"))}</option>`;
}

function labReportRowHtml(markers, row, index, entryId) {
  const marker = markers[row.marker];
  return `<div class="lab-report-row">
      <select data-field="lab-report-marker-${index}" aria-label="${escapeHtml(
        t("ui_panel_lab_marker", "Marker")
      )}">${reportMarkerOptions(markers, row.marker)}</select>
      <input type="number" step="any" inputmode="decimal"
        data-field="lab-report-value-${index}" aria-label="${escapeHtml(
          t("ui_panel_lab_value_field", "Wert")
        )}" value="${attrValue(row.value)}" />
      <select data-field="lab-report-unit-pick-${index}" aria-label="${escapeHtml(
        t("ui_panel_lab_unit_field", "Einheit (optional)")
      )}">${unitOptions(marker, row.unit)}</select>
      <input type="text" data-field="lab-report-unit-${index}" aria-label="${escapeHtml(
        t("ui_panel_lab_unit_field", "Einheit (optional)")
      )}" value="${attrValue(row.unit)}" placeholder="${escapeHtml(
        (marker && marker.unit) || t("ui_common_optional", "optional")
      )}" autocomplete="off" />
      <button class="btn ghost" type="button" data-action="lab-report-remove"
        data-entry="${escapeHtml(entryId)}" data-index="${index}" aria-label="${escapeHtml(
          t("ui_panel_lab_report_remove_row", "Zeile entfernen")
        )}">\u2715</button>
    </div>`;
}

export function labReportForm(panel, labs, entryId) {
  const draft = labReportDraft(panel, entryId);
  const atLimit = draft.rows.length >= LAB_REPORT_MAX_ROWS_UI;
  const disabled = panel._busy ? " disabled" : "";
  const addDisabled = panel._busy || atLimit ? " disabled" : "";
  const rows = draft.rows
    .map((row, index) => labReportRowHtml(labs.markers || {}, row, index, entryId))
    .join("");
  const note = atLimit
    ? `<div class="muted">${escapeHtml(
        t("ui_panel_lab_report_limit", "Höchstens 60 Zeilen pro Bericht.")
      )}</div>`
    : "";
  return `<details class="lab-report-form">
      <summary>${escapeHtml(t("ui_panel_lab_report_title", "Laborbericht erfassen"))}</summary>
      <div class="lab-report-fill">
        <button class="btn ghost" type="button" data-action="lab-report-fill-visible"${disabled}>${escapeHtml(
          t("ui_panel_lab_fill_visible", "Alle sichtbaren Marker anlegen")
        )}</button>
        <button class="btn ghost" type="button" data-action="lab-report-fill-last"${disabled}>${escapeHtml(
          t("ui_panel_lab_fill_last", "Zuletzt verwendete Marker anlegen")
        )}</button>
      </div>
      <label class="field">${escapeHtml(t("ui_panel_lab_report_ts", "Zeitpunkt"))}
        <input type="datetime-local" data-field="lab-report-ts" value="${attrValue(draft.ts)}" />
      </label>
      <label class="field">${escapeHtml(
        t("ui_panel_lab_report_ref", "Bericht-Link/ID (optional)")
      )}
        <input type="text" data-field="lab-report-ref" value="${attrValue(draft.reportRef)}"
          placeholder="${escapeHtml(t("ui_common_optional", "optional"))}" autocomplete="off" />
      </label>
      <div class="lab-report-rows">${rows}</div>
      ${note}
      <div class="lab-report-actions">
        <button class="btn ghost" type="button" data-action="lab-report-add"
          data-entry="${escapeHtml(entryId)}"${addDisabled}>＋ ${escapeHtml(
            t("ui_panel_lab_report_add_row", "Zeile")
          )}</button>
        <button class="btn" type="button" data-action="lab-report-save"
          data-entry="${escapeHtml(entryId)}"${disabled}>\u{1F4BE} ${escapeHtml(
            t("ui_panel_lab_report_save", "Bericht speichern")
          )}</button>
      </div>
    </details>`;
}

export function handleLabReportChange(panel, entryId, field, value) {
  if (!entryId || !field || !field.startsWith("lab-report-")) return false;
  const draft = labReportDraft(panel, entryId);
  if (field === "lab-report-ts") {
    draft.ts = value;
    return false;
  }
  if (field === "lab-report-ref") {
    draft.reportRef = value;
    return false;
  }
  const markerMatch = /^lab-report-marker-(\d+)$/.exec(field);
  if (markerMatch) {
    const row = draft.rows[Number(markerMatch[1])];
    if (!row) return false;
    row.marker = value;
    row.unit = ""; // Einheiten-Dropdown hängt am Marker
    return true;
  }
  const pickMatch = /^lab-report-unit-pick-(\d+)$/.exec(field);
  if (pickMatch) {
    const row = draft.rows[Number(pickMatch[1])];
    if (!row) return false;
    row.unit = value === "__custom__" ? "" : value;
    return true;
  }
  const unitMatch = /^lab-report-unit-(\d+)$/.exec(field);
  if (unitMatch) {
    const row = draft.rows[Number(unitMatch[1])];
    if (row) row.unit = value;
    return false;
  }
  const valueMatch = /^lab-report-value-(\d+)$/.exec(field);
  if (valueMatch) {
    const row = draft.rows[Number(valueMatch[1])];
    if (row) row.value = value;
    return false;
  }
  return false;
}

export function addLabReportRow(panel, entryId) {
  const draft = collectLabReportDraft(panel, entryId);
  if (draft.rows.length >= LAB_REPORT_MAX_ROWS_UI) return;
  draft.rows.push(emptyLabReportRow());
  panel._render();
}

function removeLabReportRow(panel, entryId, index) {
  const draft = collectLabReportDraft(panel, entryId);
  if (!Number.isInteger(index) || draft.rows.length <= 1) return;
  draft.rows.splice(index, 1);
  panel._render();
}

export function fillLabReportDraft(panel, entryId, mode) {
  const draft = collectLabReportDraft(panel, entryId);
  const data = (panel._data || {})[entryId] || {};
  const labs = data.labs || { categories: [], markers: {} };
  const markers = labs.markers || {};
  let keys = [];
  if (mode === "visible") {
    const visible = new Set(visibleLabCategories(labs).map((category) => category.key));
    keys = Object.keys(markers).filter((key) => visible.has(markers[key].category));
  } else {
    const last = labs.last_report || {};
    keys = (Array.isArray(last.marker_keys) ? last.marker_keys : []).filter(
      (key) => markers[key]
    );
  }
  const used = new Set(draft.rows.map((row) => row.marker).filter(Boolean));
  for (const key of keys) {
    if (used.has(key)) continue;
    const empty = draft.rows.find((row) => !row.marker && !row.value && !row.unit);
    if (empty) {
      empty.marker = key;
    } else if (draft.rows.length < LAB_REPORT_MAX_ROWS_UI) {
      draft.rows.push({ marker: key, value: "", unit: "" });
    } else {
      break;
    }
    used.add(key);
  }
  panel._render();
}

async function submitLabReport(panel, entryId) {
  if (!panel || !entryId || panel._busy || typeof panel._ws !== "function") return;
  const draft = collectLabReportDraft(panel, entryId);
  const ts = validLabReportTs(draft.ts);
  if (ts.error) {
    panel._formError = ts.error;
    panel._render();
    return;
  }
  const values = [];
  for (const row of draft.rows) {
    const marker = String(row.marker || "").trim();
    const rawValue = String(row.value || "").trim().replace(",", ".");
    const unit = String(row.unit || "").trim();
    if (!marker && !rawValue && !unit) continue;
    if (!marker || !/^-?\d+(\.\d+)?$/.test(rawValue)) {
      panel._formError = t(
        "ui_panel_val_lab_value",
        "Bitte Marker und einen numerischen Wert angeben."
      );
      panel._render();
      return;
    }
    values.push(
      unit
        ? { marker, value: Number(rawValue), unit }
        : { marker, value: Number(rawValue) }
    );
  }
  if (!values.length) {
    panel._formError = t(
      "ui_panel_lab_report_empty",
      "Bitte mindestens einen Wert erfassen."
    );
    panel._render();
    return;
  }
  const message = { type: WS.addLabReport, entry_id: entryId, values };
  if (ts.iso) message.ts = ts.iso;
  if (String(draft.reportRef || "").trim()) {
    message.report_ref = String(draft.reportRef).trim();
  }

  panel._busy = true;
  panel._actionError = null;
  panel._formError = null;
  panel._render();
  try {
    const result = await panel._ws(message);
    const failure = resultError(result);
    if (failure) {
      panel._formError = failure;
      return;
    }
    // ts/reportRef bleiben stehen (§6.4) — nur Werte + Zeilen werden geleert.
    panel._labReportDraft[entryId] = { ...draft, rows: [emptyLabReportRow()] };
    await panel._reloadEntry(entryId);
  } catch (err) {
    panel._formError = errMsg(err);
  } finally {
    panel._busy = false;
    panel._render();
  }
}

/* Envelope-Fehler der Batch-Kommandos (§3): `panel._ws` löst bei
 * {"ok": false} nicht ab. */
function resultError(result) {
  if (!result || result.ok !== false) return "";
  const error = result.error && typeof result.error === "object" ? result.error : {};
  return error.message || error.code || t("ui_panel_lab_report_empty", "Fehler");
}
```

(c) `labsTab` (`Zeile 1066-1117`): Fehlerbanner aus dem `<details>` herausziehen und den
Bericht-Abschnitt anhängen. Den Block ab `const formError = ...` bis zum `return`
ersetzen durch:

```js
  const formError = panel._formError
    ? `<div class="msg error">${escapeHtml(panel._formError)}</div>`
    : "";
  const disabled = panel._busy ? " disabled" : "";
  const entryForm = `<details class="lab-entry-form">
      <summary>${escapeHtml(t("ui_panel_lab_add_value", "Neuen Wert erfassen"))}</summary>
      <label class="field">${escapeHtml(t("ui_panel_lab_marker", "Marker"))}
        <select data-field="lab-add-marker">${labMarkerOptionsHtml(labs.markers, null)}</select>
      </label>
      <label class="field">${escapeHtml(t("ui_panel_lab_value_field", "Wert"))}
        <input type="number" step="any" data-field="lab-add-value" />
      </label>
      <label class="field">${escapeHtml(t("ui_panel_lab_unit_field", "Einheit (optional)"))}
        <input type="text" data-field="lab-add-unit" placeholder="${escapeHtml(
          t("ui_common_optional", "optional")
        )}" autocomplete="off" />
      </label>
      <label class="field">${escapeHtml(t("ui_panel_lab_report_ref", "Bericht-Link/ID (optional)"))}
        <input type="text" data-field="lab-add-report-ref" placeholder="${escapeHtml(
          t("ui_common_optional", "optional")
        )}" autocomplete="off" />
      </label>
      <button class="btn" type="button" data-action="lab-add-value" data-entry="${escapeHtml(
        entryId
      )}"${disabled}>\u{1F4BE} ${escapeHtml(t("ui_panel_lab_save", "Speichern"))}</button>
    </details>`;
  const reportForm = labReportForm(panel, labs, entryId);

  return `${labCategoryBar(labs, active)}<div class="lab-rows">${rows}</div>${formError}${entryForm}${reportForm}`;
```

(d) Klick-Delegation in `ensureLabGestures` (`Zeile 1040-1064`) vor dem
`lab-add-value`-Zweig:

```js
    const fillVisibleEl = target.closest('[data-action="lab-report-fill-visible"]');
    if (fillVisibleEl) {
      fillLabReportDraft(panel, fillVisibleEl.getAttribute("data-entry") || "", "visible");
      return;
    }
    const fillLastEl = target.closest('[data-action="lab-report-fill-last"]');
    if (fillLastEl) {
      fillLabReportDraft(panel, fillLastEl.getAttribute("data-entry") || "", "last");
      return;
    }
    const reportAddEl = target.closest('[data-action="lab-report-add"]');
    if (reportAddEl) {
      addLabReportRow(panel, reportAddEl.getAttribute("data-entry") || "");
      return;
    }
    const reportRemoveEl = target.closest('[data-action="lab-report-remove"]');
    if (reportRemoveEl) {
      removeLabReportRow(
        panel,
        reportRemoveEl.getAttribute("data-entry") || "",
        Number(reportRemoveEl.getAttribute("data-index"))
      );
      return;
    }
    const reportSaveEl = target.closest('[data-action="lab-report-save"]');
    if (reportSaveEl) {
      submitLabReport(panel, reportSaveEl.getAttribute("data-entry") || "");
      return;
    }
```

> Die Zeilen-Buttons (remove) liegen innerhalb des Formulars und bekommen die
> `data-entry`-ID direkt in `labReportRowHtml(markers, row, index, entryId)` — der
> Klick-Handler kann sie also ohne DOM-Suche auslesen.

- [ ] **Step 6: Implement — i18n (10 Keys)**

`strings.json` (`common`):

```json
    "ui_panel_lab_report_title": "Record lab report",
    "ui_panel_lab_report_add_row": "Row",
    "ui_panel_lab_report_remove_row": "Remove row",
    "ui_panel_lab_report_save": "Save report",
    "ui_panel_lab_report_ts": "Timestamp",
    "ui_panel_lab_marker_choose": "— choose —",
    "ui_panel_lab_fill_visible": "Fill all visible markers",
    "ui_panel_lab_fill_last": "Fill last used markers",
    "ui_panel_lab_report_limit": "At most 60 rows per report.",
    "ui_panel_lab_report_empty": "Record at least one value.",
```

`translations/de.json`:

```json
    "ui_panel_lab_report_title": "Laborbericht erfassen",
    "ui_panel_lab_report_add_row": "Zeile",
    "ui_panel_lab_report_remove_row": "Zeile entfernen",
    "ui_panel_lab_report_save": "Bericht speichern",
    "ui_panel_lab_report_ts": "Zeitpunkt",
    "ui_panel_lab_marker_choose": "— bitte wählen —",
    "ui_panel_lab_fill_visible": "Alle sichtbaren Marker anlegen",
    "ui_panel_lab_fill_last": "Zuletzt verwendete Marker anlegen",
    "ui_panel_lab_report_limit": "Höchstens 60 Zeilen pro Bericht.",
    "ui_panel_lab_report_empty": "Bitte mindestens einen Wert erfassen.",
```

`translations/en.json`: identisch zu `strings.json`.

- [ ] **Step 7: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_panel_js.py -k req_hom_123 -q && python3 -m pytest tests/test_translations.py -k req_hom_122_common_ui_keys -q`
Expected: all PASS.

- [ ] **Step 8: Regression**

Run: `python3 -m pytest tests/test_panel_js.py tests/test_translations.py tests/test_frontend.py -q && ruff check . && ruff format --check .`
Expected: grün/clean.

- [ ] **Step 9: Commit**

```bash
git add custom_components/health_o_mat/www/health-o-mat-panel-base.js custom_components/health_o_mat/www/health-o-mat-panel-views.js custom_components/health_o_mat/www/health-o-mat-panel.js custom_components/health_o_mat/strings.json custom_components/health_o_mat/translations/de.json custom_components/health_o_mat/translations/en.json tests/test_panel_js.py tests/test_translations.py
git commit -m "feat: add multi-row lab report dialog to panel"
```

---

### Task 13: „Diesen Bericht verwerfen" in Card + Panel (`remove_lab_report`)

**Files:**
- Modify: `custom_components/health_o_mat/www/health-o-mat-labs-card.js`
- Modify: `custom_components/health_o_mat/www/health-o-mat-panel-views.js`
- Modify: `custom_components/health_o_mat/www/health-o-mat-panel-base.js` (`WS.removeLabReport`)
- Modify: `custom_components/health_o_mat/strings.json`, `translations/{de,en}.json` (2 Keys)
- Test: `tests/test_card_js.py`, `tests/test_panel_js.py`, `tests/test_translations.py`

**Interfaces:**
- Consumes: `panel_data.labs.last_report` (`{ts, marker_keys, report_ref}` aus Task 10),
  `panel._ws`, `this._hass.connection.sendMessagePromise`, `resultError`.
- Produces:
  - Card: `_discardReportBar()` + `_discardReport()`; Aktion
    `data-action="lab-report-discard"`.
  - Panel: `labReportDiscardHtml(panel, labs, entryId)` + `discardLabReport(panel,
    entryId)`; `WS.removeLabReport = "health_o_mat/remove_lab_report"`.
  - i18n: `ui_panel_lab_report_discard` ("Diesen Bericht verwerfen"),
    `ui_panel_lab_report_discard_confirm` ("Diesen Bericht mit {count} Werten verwerfen?").
- Sichtbarkeit: nur wenn `last_report.ts` gesetzt ist; `confirm()` vor dem Senden; sendet
  `ts` und — nur wenn vorhanden — `report_ref` (§6.5).

**Spec-Bezug:** §6.5 (Aktion, Sicherheitsabfrage, `no_active_report`-Pfad), §2.13.

- [ ] **Step 1: Write the failing tests**

(a) `tests/test_card_js.py` ans Ende:

```python
def test_req_hom_128_labs_card_discard_only_with_last_report():
    source = _labs_card_source()

    assert '_discardReport(' in source
    assert 'data-action="lab-report-discard"' in source
    assert "_labs().last_report" in source
    assert "health_o_mat/remove_lab_report" in source
    assert "window.confirm" in source


_NODE_LABS_DISCARD_RUNNER = """import { readFileSync } from "node:fs";
import vm from "node:vm";

const source = readFileSync(process.argv[2], "utf8");
const confirmed = process.argv[3] === "yes";

class FakeShadowRoot {
  constructor() { this.innerHTML = ""; }
  addEventListener() {}
  removeEventListener() {}
  querySelector() { return null; }
  querySelectorAll() { return []; }
}
class FakeHTMLElement {
  constructor() { this._shadow = new FakeShadowRoot(); }
  attachShadow() { return this._shadow; }
  get shadowRoot() { return this._shadow; }
}
const context = {
  HTMLElement: FakeHTMLElement,
  customElements: {
    _classes: {},
    get() { return undefined; },
    define(tag, cls) { this._classes[tag] = cls; },
  },
  window: { confirm: () => confirmed },
  document: { createElement: () => ({}) },
  console: { info: () => {}, log: () => {}, warn: () => {}, error: () => {} },
};
vm.createContext(context);
vm.runInContext(source, context, { filename: "health-o-mat-labs-card.js" });

const CardClass = context.customElements._classes["health-o-mat-labs-card"];
const card = new CardClass();
card._config = { entry_id: "entry-1", person_mode: "fixed" };
card._normalized = null;
card._activeEntry = "entry-1";
card._saving = false;
card._data = {
  person: "Alex",
  labs: {
    categories: [],
    markers: {},
    last_report: {
      ts: "2026-10-30T09:15:00+01:00",
      marker_keys: ["alt", "crp"],
      report_ref: "Labor A",
    },
  },
};
card._loadData = async () => {};
card._render = () => {};
const sent = [];
card._hass = {
  connection: {
    sendMessagePromise: async (payload) => {
      sent.push(payload);
      return { ok: true, voided: 2 };
    },
  },
};
await card._discardReport();
process.stdout.write(JSON.stringify({ payload: sent[0] || null, calls: sent.length }));
"""


@pytest.mark.skipif(shutil.which("node") is None, reason="node nicht verfügbar")
def test_req_hom_128_labs_card_discard_confirmation_and_payload(tmp_path):
    def run(confirmed: str) -> dict:
        return json.loads(
            _run_node(
                tmp_path,
                _NODE_LABS_DISCARD_RUNNER,
                [str(Path(_LABS_CARD_JS)), confirmed],
                f"runner_labs_discard_{confirmed}",
            )
        )

    cancelled = run("no")
    assert cancelled == {"payload": None, "calls": 0}

    confirmed = run("yes")
    assert confirmed["calls"] == 1
    assert confirmed["payload"] == {
        "type": "health_o_mat/remove_lab_report",
        "entry_id": "entry-1",
        "ts": "2026-10-30T09:15:00+01:00",
        "report_ref": "Labor A",
    }
```

(b) `tests/test_panel_js.py` ans Ende:

```python
def test_req_hom_128_panel_discard_action_guarded_by_last_report():
    views = (_WWW_DIR / "health-o-mat-panel-views.js").read_text(encoding="utf-8")
    source = _panel_base_source()

    assert "ui_panel_lab_report_discard_confirm" in views
    assert 'data-action="lab-report-discard"' in views
    assert "window.confirm" in views
    assert 'removeLabReport: "health_o_mat/remove_lab_report",' in source


def test_req_hom_128_panel_discard_sends_ts_and_optional_ref():
    views = (_WWW_DIR / "health-o-mat-panel-views.js").read_text(encoding="utf-8")
    body = _js_function_block(views, "discardLabReport")

    assert "last_report" in body
    assert "ts: last.ts" in body or "ts: latest.ts" in body
    assert "report_ref" in body
    assert "WS.removeLabReport" in body
    assert "resultError(result)" in body
```

(c) `tests/test_translations.py`: beide Keys in `_REQ_HOM_122_UI_KEYS` aufnehmen.

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_card_js.py -k req_hom_128 tests/test_panel_js.py -k req_hom_128 -q`
Expected: FAIL — Aktion/WS-Konstante fehlen.

- [ ] **Step 3: Implement — Card**

(a) CSS in `CARD_CSS` nach `.labs-report-actions`:

```css
  .labs-report-discard { display: flex; justify-content: flex-end; margin-top: 8px; }
```

(b) Methode vor `/* ---- Events ---` (nach `_saveReport`):

```js
  _discardReportBar() {
    const last = this._labs().last_report;
    if (!last || !last.ts) return "";
    const count = Array.isArray(last.marker_keys) ? last.marker_keys.length : 0;
    return `<div class="labs-report-discard">
      <button type="button" class="labs-tab" data-action="lab-report-discard"${
        this._saving ? " disabled" : ""
      }>Diesen Bericht verwerfen (${count})</button>
    </div>`;
  }

  async _discardReport() {
    if (this._saving) return;
    const last = this._labs().last_report;
    if (!last || !last.ts) return;
    const count = Array.isArray(last.marker_keys) ? last.marker_keys.length : 0;
    const confirmed =
      typeof window !== "undefined" && typeof window.confirm === "function"
        ? window.confirm(`Diesen Bericht mit ${count} Werten verwerfen?`)
        : true;
    if (!confirmed) return;
    if (!this._activeEntry) return;
    const payload = {
      type: "health_o_mat/remove_lab_report",
      entry_id: this._activeEntry,
      ts: last.ts,
    };
    if (last.report_ref) payload.report_ref = last.report_ref;
    this._saving = true;
    this._actionError = "";
    this._render();
    try {
      const result = await this._hass.connection.sendMessagePromise(payload);
      const failure = resultError(result);
      if (failure) {
        this._actionError = failure;
        return;
      }
      await this._loadData(true);
    } catch (err) {
      this._actionError = reportErrorMessage(err);
    } finally {
      this._saving = false;
      this._render();
    }
  }
```

(c) `_render`: nach `${body}` (vor `${entryForm}`) `${this._discardReportBar()}` einsetzen.

(d) `_onClick`: `if (action === "lab-report-discard") { this._discardReport(); return; }`.

- [ ] **Step 4: Implement — Panel**

(a) `panel-base.js` nach `addLabReport`:

```js
  removeLabReport: "health_o_mat/remove_lab_report",
```

(b) `panel-views.js`: Funktionen vor `labsTab`:

```js
export function labReportDiscardHtml(panel, labs, entryId) {
  const last = labs && labs.last_report;
  if (!last || !last.ts) return "";
  const count = Array.isArray(last.marker_keys) ? last.marker_keys.length : 0;
  return `<div class="lab-report-discard">
      <button class="btn ghost" type="button" data-action="lab-report-discard"
        data-entry="${escapeHtml(entryId)}"${panel._busy ? " disabled" : ""}>${escapeHtml(
          `${t("ui_panel_lab_report_discard", "Diesen Bericht verwerfen")} (${count})`
        )}</button>
    </div>`;
}

async function discardLabReport(panel, entryId) {
  if (!panel || !entryId || panel._busy || typeof panel._ws !== "function") return;
  const last = (((panel._data || {})[entryId] || {}).labs || {}).last_report;
  if (!last || !last.ts) return;
  const count = Array.isArray(last.marker_keys) ? last.marker_keys.length : 0;
  const confirmed =
    typeof window !== "undefined" && typeof window.confirm === "function"
      ? window.confirm(
          t(
            "ui_panel_lab_report_discard_confirm",
            "Diesen Bericht mit {count} Werten verwerfen?",
            { count }
          )
        )
      : true;
  if (!confirmed) return;
  const message = { type: WS.removeLabReport, entry_id: entryId, ts: last.ts };
  if (last.report_ref) message.report_ref = last.report_ref;

  panel._busy = true;
  panel._actionError = null;
  panel._formError = null;
  panel._render();
  try {
    const result = await panel._ws(message);
    const failure = resultError(result);
    if (failure) {
      panel._formError = failure;
      return;
    }
    await panel._reloadEntry(entryId);
  } catch (err) {
    panel._formError = errMsg(err);
  } finally {
    panel._busy = false;
    panel._render();
  }
}
```

(c) `labsTab`-Return: `${labReportDiscardHtml(panel, labs, entryId)}` direkt nach der
Kategorie-Leiste einsetzen:

```js
  return `${labCategoryBar(labs, active)}${labReportDiscardHtml(
    panel,
    labs,
    entryId
  )}<div class="lab-rows">${rows}</div>${formError}${entryForm}${reportForm}`;
```

(d) Klick-Delegation: vor dem Report-Save-Zweig

```js
    const discardEl = target.closest('[data-action="lab-report-discard"]');
    if (discardEl) {
      discardLabReport(panel, discardEl.getAttribute("data-entry") || "");
      return;
    }
```

(e) CSS in `PANEL_CSS`:

```css
  .lab-report-discard { display: flex; justify-content: flex-end; margin: 8px 0; }
```

- [ ] **Step 5: Implement — i18n (2 Keys)**

`strings.json`:

```json
    "ui_panel_lab_report_discard": "Discard this report",
    "ui_panel_lab_report_discard_confirm": "Discard this report with {count} values?",
```

`translations/de.json`:

```json
    "ui_panel_lab_report_discard": "Diesen Bericht verwerfen",
    "ui_panel_lab_report_discard_confirm": "Diesen Bericht mit {count} Werten verwerfen?",
```

`translations/en.json`: identisch zu `strings.json`.

- [ ] **Step 6: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_card_js.py -k req_hom_128 tests/test_panel_js.py -k req_hom_128 tests/test_translations.py -k req_hom_122_common_ui_keys -q`
Expected: all PASS.

- [ ] **Step 7: Regression**

Run: `python3 -m pytest tests/test_card_js.py tests/test_panel_js.py tests/test_translations.py -q && ruff check . && ruff format --check .`
Expected: grün/clean.

- [ ] **Step 8: Commit**

```bash
git add custom_components/health_o_mat/www/health-o-mat-labs-card.js custom_components/health_o_mat/www/health-o-mat-panel-views.js custom_components/health_o_mat/www/health-o-mat-panel-base.js custom_components/health_o_mat/strings.json custom_components/health_o_mat/translations/de.json custom_components/health_o_mat/translations/en.json tests/test_card_js.py tests/test_panel_js.py tests/test_translations.py
git commit -m "feat: add discard report action to card and panel"
```

---

## Wave 5 — Disclaimer & Admin-Sichtbarkeit

### Task 14: Panel-Disclaimer + Leerzustand + Admin-Checkbox

**Files:**
- Modify: `custom_components/health_o_mat/www/health-o-mat-panel-views.js`
- Modify: `custom_components/health_o_mat/www/health-o-mat-panel-admin.js`
- Modify: `custom_components/health_o_mat/www/health-o-mat-panel-base.js` (`PANEL_CSS`)
- Modify: `custom_components/health_o_mat/www/health-o-mat-panel.js` (Settings-Collect/PATCH)
- Modify: `custom_components/health_o_mat/strings.json`, `translations/{de,en}.json` (3 Keys)
- Test: `tests/test_panel_js.py`, `tests/test_translations.py`

**Interfaces:**
- Consumes: `data.lab_hide_panel_disclaimer` aus `panel_data` (Task 10),
  `settings.lab_hide_panel_disclaimer` (Admin), `panel._settings` (nur Admin-Formular),
  `escapeHtml`, `messageHtml`, `t`.
- Produces:
  - `labDisclaimerHtml()` in `panel-views.js`; `labsTab` rendert ihn **vor** jeder
    Leerzustandsprüfung, sichtbar wenn `!data.lab_hide_panel_disclaimer`
    (fehlend = `false` = sichtbar).
  - Leerzustand: `labs.categories.length` > 0 → `ui_panel_lab_all_hidden`
    („Alle Kategorien ausgeblendet"), sonst `ui_panel_lab_no_categories`.
  - Admin-Checkbox `data-field="lab-hide-panel-disclaimer"` im Karten-Block
    „Laborwerte" (neben den Kategorie-Checkboxen).
  - `panel.js`: Payload-Key + PATCH-Vergleich.
  - `.labs-disclaimer` in `PANEL_CSS`.
- **Nie** `panel._settings`/`isAdmin` im Lab-Tab (statischer Test).

**Spec-Bezug:** §8 (Default sichtbar, Abschaltbarkeit nur im Admin, Transport via
`panel_data`, Leerfall, CSS, Nicht-Admin-Absicherung), §7.4, REQ-HOM-125.

- [ ] **Step 1: Write the failing tests** (`tests/test_panel_js.py`, ans Ende)

```python
# --- REQ-HOM-125: Panel-Disclaimer + Admin-Schalter -------------------------


def test_req_hom_125_panel_labs_tab_renders_disclaimer_before_empty_state():
    views = (_WWW_DIR / "health-o-mat-panel-views.js").read_text(encoding="utf-8")
    body = _js_function_block(views, "labsTab")
    disclaimer = _js_function_block(views, "labDisclaimerHtml")

    assert "ui_panel_lab_disclaimer" in disclaimer
    assert "labs-disclaimer" in disclaimer
    assert 'role="note"' in disclaimer
    assert "lab_hide_panel_disclaimer" in body
    assert "labDisclaimerHtml()" in body
    assert body.index("labDisclaimerHtml()") < body.index("labCategoryBar")


def test_req_hom_125_panel_empty_state_distinguishes_all_hidden():
    views = (_WWW_DIR / "health-o-mat-panel-views.js").read_text(encoding="utf-8")
    body = _js_function_block(views, "labsTab")

    assert "ui_panel_lab_all_hidden" in body
    assert "ui_panel_lab_no_categories" in body


def test_req_hom_125_panel_lab_tab_never_reads_admin_settings():
    views = (_WWW_DIR / "health-o-mat-panel-views.js").read_text(encoding="utf-8")
    body = _js_function_block(views, "labsTab")

    for forbidden in ("_settings", "isAdmin", "is_admin", "getSettings"):
        assert forbidden not in body, f"Lab-Tab darf {forbidden} nicht lesen (§8)"


def test_req_hom_125_panel_css_defines_labs_disclaimer():
    source = _panel_base_source()
    match = re.search(r"export const PANEL_CSS = `(.*?)`;", source, re.S)
    assert match is not None
    assert ".labs-disclaimer" in match.group(1)
    assert "--warning-color" in match.group(1)


def test_req_hom_125_admin_has_disclaimer_checkbox_and_entry_collects_it():
    admin = (_WWW_DIR / "health-o-mat-panel-admin.js").read_text(encoding="utf-8")
    entry = (_WWW_DIR / "health-o-mat-panel.js").read_text(encoding="utf-8")

    assert 'data-field="lab-hide-panel-disclaimer"' in admin
    assert 't("ui_admin_lab_hide_disclaimer"' in admin
    assert "lab-hide-panel-disclaimer" in entry
    assert "lab_hide_panel_disclaimer" in entry
```

Zusätzlich in `tests/test_translations.py` die drei Keys in `_REQ_HOM_122_UI_KEYS`
aufnehmen: `ui_panel_lab_disclaimer`, `ui_panel_lab_all_hidden`,
`ui_admin_lab_hide_disclaimer`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_panel_js.py -k req_hom_125 -q`
Expected: FAIL — `labDisclaimerHtml`/Checkbox fehlen; i18n-Test meldet Keys.

- [ ] **Step 3: Implement — `panel-views.js`**

(a) Vor `labsTab`:

```js
/* Kontextbezogener Medizin-Hinweis (§8, REQ-HOM-125). Zustand kommt
 * ausschließlich aus `panel_data` — `get_settings` ist admin-only und wäre für
 * Nicht-Admins leer. Fehlendes Feld = sichtbar. */
function labDisclaimerHtml() {
  return `<div class="labs-disclaimer" role="note">${escapeHtml(
    t(
      "ui_panel_lab_disclaimer",
      "⚠️ Hinweis: keine medizinische Beratung — Richtwerte, keine Diagnose. Referenzbereiche in den Einstellungen anpassen."
    )
  )}</div>`;
}
```

(b) `labsTab`: nach `const categories = visibleLabCategories(labs);`

```js
  const disclaimer =
    data && data.lab_hide_panel_disclaimer === true ? "" : labDisclaimerHtml();
```

Leerfall ersetzen:

```js
  if (!categories.length) {
    const allHidden =
      Array.isArray(labs.categories) && labs.categories.length > 0;
    const emptyText = allHidden
      ? t("ui_panel_lab_all_hidden", "Alle Kategorien ausgeblendet")
      : t("ui_panel_lab_no_categories", "Keine Laborwert-Kategorie sichtbar.");
    return `${disclaimer}${messageHtml(emptyText, false)}`;
  }
```

Return-Präfix:

```js
  return `${disclaimer}${labCategoryBar(labs, active)}${labReportDiscardHtml(
    panel,
    labs,
    entryId
  )}<div class="lab-rows">${rows}</div>${formError}${entryForm}${reportForm}`;
```

- [ ] **Step 4: Implement — `panel-base.js` CSS**

Bei den `.lab-*`-Regeln:

```css
  .labs-disclaimer {
    padding: 8px 10px; border-radius: 8px; font-size: .9rem; margin-bottom: 8px;
    background: var(--warning-color, #ff9800); color: #fff;
  }
```

- [ ] **Step 5: Implement — `panel-admin.js` Checkbox**

Im Karten-Block „Kategorien ausblenden" (`health-o-mat-panel-admin.js:429-440`) nach
`<div class="settings-grid">${hideCheckboxes}</div>`:

```js
      <div class="settings-grid">
        <label class="check">
          <input type="checkbox" data-field="lab-hide-panel-disclaimer"${
            s.lab_hide_panel_disclaimer === true ? " checked" : ""
          } />
          <span>${escapeHtml(
            t("ui_admin_lab_hide_disclaimer", "Medizin-Hinweis im Panel ausblenden")
          )}</span>
        </label>
      </div>
```

- [ ] **Step 6: Implement — `panel.js` Collect/PATCH**

(a) In `_collectSettingsPayload` nach dem `labHiddenCategories`-Block (`Zeile 1147-1153`):

```js
    const hideDisclaimerEl = this.shadowRoot.querySelector(
      '[data-field="lab-hide-panel-disclaimer"]'
    );
    const labHidePanelDisclaimer = !!(hideDisclaimerEl && hideDisclaimerEl.checked);
```

(b) Payload (`Zeile 1178`) um den Key ergänzen:

```js
        lab_hide_panel_disclaimer: labHidePanelDisclaimer,
```

(c) `_changedSettings` nach dem `lab_custom_markers`-Vergleich (`Zeile 1243`):

```js
    if (!!current.lab_hide_panel_disclaimer !== payload.lab_hide_panel_disclaimer) {
      out.lab_hide_panel_disclaimer = payload.lab_hide_panel_disclaimer;
    }
```

- [ ] **Step 7: Implement — i18n (3 Keys)**

`strings.json`:

```json
    "ui_panel_lab_disclaimer": "⚠️ Note: not medical advice — reference values, not a diagnosis. Adjust reference ranges in the settings.",
    "ui_panel_lab_all_hidden": "All categories hidden",
    "ui_admin_lab_hide_disclaimer": "Hide the medical note in the panel",
```

`translations/de.json`:

```json
    "ui_panel_lab_disclaimer": "⚠️ Hinweis: keine medizinische Beratung — Richtwerte, keine Diagnose. Referenzbereiche in den Einstellungen anpassen.",
    "ui_panel_lab_all_hidden": "Alle Kategorien ausgeblendet",
    "ui_admin_lab_hide_disclaimer": "Medizin-Hinweis im Panel ausblenden",
```

`translations/en.json`: identisch zu `strings.json`.

- [ ] **Step 8: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_panel_js.py -k req_hom_125 -q && python3 -m pytest tests/test_translations.py -k req_hom_122_common_ui_keys -q`
Expected: all PASS.

- [ ] **Step 9: Regression**

Run: `python3 -m pytest tests/test_panel_js.py tests/test_translations.py -q && ruff check . && ruff format --check .`
Expected: grün/clean.

- [ ] **Step 10: Commit**

```bash
git add custom_components/health_o_mat/www/health-o-mat-panel-views.js custom_components/health_o_mat/www/health-o-mat-panel-admin.js custom_components/health_o_mat/www/health-o-mat-panel-base.js custom_components/health_o_mat/www/health-o-mat-panel.js custom_components/health_o_mat/strings.json custom_components/health_o_mat/translations/de.json custom_components/health_o_mat/translations/en.json tests/test_panel_js.py tests/test_translations.py
git commit -m "feat: add panel lab disclaimer and admin toggle"
```

---

### Task 15: Admin-Faktorspalte + „Einheit Pflicht"-Badge

**Files:**
- Modify: `custom_components/health_o_mat/www/health-o-mat-panel-admin.js`
- Modify: `custom_components/health_o_mat/strings.json`, `translations/{de,en}.json` (3 Keys)
- Test: `tests/test_panel_js.py`, `tests/test_translations.py`

**Interfaces:**
- Consumes: `settings.lab_catalog.markers[*].alt_units` (`{unit: factor_to_canonical}`),
  `.require_explicit_unit`, `.canonical_unit` (verbatim aus `build_settings`,
  `ws_api.py:1659`); `formatNumber(value)` aus `panel-base.js` (`Zeile 752`, locale via
  `Intl.NumberFormat(intlLocale())`); `t`, `escapeHtml`, `labDisplayName`.
- Produces: `conversionText(marker)`, `requiredBadge(marker)` in `labSettingsSection`;
  neue Spalte „Umrechnung" zwischen „Einheit" und „Referenz"; `altUnitText` erweitert um
  den Faktor (`alt: <Einh.> × {formatNumber(factor)}`). **Keine** Server-/WS-Änderung.
- i18n: `ui_admin_lab_conversion`, `ui_admin_lab_conversion_required`,
  `ui_admin_lab_conversion_none`.

**Spec-Bezug:** §7.1–§7.3, REQ-HOM-124 (DE `88,4` / EN `88.4`, `—`, Badge, keine API).

- [ ] **Step 1: Write the failing tests** (`tests/test_panel_js.py`, ans Ende)

```python
# --- REQ-HOM-124: Admin-Umrechnungsspalte -----------------------------------


_NODE_ADMIN_CONVERSION_RUNNER = """import { pathToFileURL } from "node:url";

const base = await import(pathToFileURL(process.argv[2]).href);
const admin = await import(pathToFileURL(process.argv[3]).href);
const settings = {
  lab_catalog: {
    categories: [{ key: "kidney", name: "Niere", name_de: "Niere", name_en: "Kidney" }],
    markers: {
      creatinine: {
        category: "kidney", name_de: "Kreatinin", name_en: "Creatinine",
        canonical_unit: "µmol/L", alt_units: { "mg/dL": 88.4 },
        require_explicit_unit: false, ref_min: 53, ref_max: 106,
      },
      egfr: {
        category: "kidney", name_de: "eGFR", name_en: "eGFR",
        canonical_unit: "mL/min/1.73m²", alt_units: {},
        require_explicit_unit: false, ref_min: 90, ref_max: null,
      },
      urine_protein_creatinine_ratio: {
        category: "kidney",
        name_de: "Protein/Kreatinin-Quotient (Urin)",
        name_en: "Urine protein/creatinine ratio",
        canonical_unit: "mg/g", alt_units: { "g/g": 1000 },
        require_explicit_unit: true, ref_min: null, ref_max: 15,
      },
    },
  },
};
const out = {};
for (const language of ["de", "en"]) {
  base.setUiLanguage(language);
  out[language] = admin.labSettingsSection({}, settings, "entry-1");
}
process.stdout.write(JSON.stringify(out));
"""


def _render_admin_with_node(tmp_path) -> dict:
    (tmp_path / "package.json").write_text('{"type": "module"}', encoding="utf-8")
    (tmp_path / "health-o-mat-panel-base.js").write_bytes(
        (_WWW_DIR / "health-o-mat-panel-base.js").read_bytes()
    )
    admin_path = tmp_path / "health-o-mat-panel-admin.js"
    admin_path.write_bytes((_WWW_DIR / "health-o-mat-panel-admin.js").read_bytes())
    out = _run_node(
        tmp_path,
        _NODE_ADMIN_CONVERSION_RUNNER,
        [str(tmp_path / "health-o-mat-panel-base.js"), str(admin_path)],
        "runner_admin_conversion",
    )
    return json.loads(out)


@pytest.mark.skipif(shutil.which("node") is None, reason="node nicht verfügbar")
def test_req_hom_124_admin_conversion_column_is_locale_aware(tmp_path):
    rendered = _render_admin_with_node(tmp_path)

    assert "mg/dL × 88,4 → µmol/L" in rendered["de"]
    assert "mg/dL × 88.4 → µmol/L" in rendered["en"]
    assert "g/g × 1.000 → mg/g" in rendered["de"]
    assert "—" in rendered["de"]
    assert "Einheit Pflicht" in rendered["de"]


def test_req_hom_124_admin_conversion_uses_format_number():
    admin = (_WWW_DIR / "health-o-mat-panel-admin.js").read_text(encoding="utf-8")
    body = _js_function_block(admin, "labSettingsSection")
    imports = admin.split('} from "./health-o-mat-panel-base.js', 1)[0]

    assert "formatNumber(factor)" in body
    assert "ui_admin_lab_conversion" in body
    assert "ui_admin_lab_conversion_required" in body
    assert "ui_admin_lab_conversion_none" in body
    assert "toFixed(" not in body
    assert "formatNumber" in imports
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_panel_js.py -k req_hom_124 -q`
Expected: FAIL — `formatNumber` nicht importiert, Spalte/Keys fehlen.

- [ ] **Step 3: Implement — Import**

Im Import-Block (`panel-admin.js:15-31`) `formatNumber,` ergänzen (z. B. nach
`escapeHtml,`).

- [ ] **Step 4: Implement — Helfer in `labSettingsSection`**

Nach `altUnitText` (`Zeile 360-363`):

```js
  // Umrechnung je Alt-Einheit: "Alt × Faktor → kanonisch". Der Faktor kommt
  // aus `formatNumber` (locale-fähig) — kein hartkodiertes Komma, keine
  // String-Konkatenation des Rohwerts (§7.1).
  const conversionText = (marker) => {
    const altUnits =
      marker && typeof marker.alt_units === "object" ? marker.alt_units : {};
    const pairs = Object.entries(altUnits).filter(
      ([unit, factor]) => unit && factor != null && Number.isFinite(Number(factor))
    );
    if (!pairs.length) {
      return `<span class="muted">${escapeHtml(
        t("ui_admin_lab_conversion_none", "—")
      )}</span>`;
    }
    const canonical = String(marker.canonical_unit || "");
    return pairs
      .map(
        ([unit, factor]) =>
          `${escapeHtml(unit)} × ${escapeHtml(formatNumber(factor))} → ${escapeHtml(
            canonical
          )}`
      )
      .join("<br>");
  };
  const requiredBadge = (marker) =>
    marker && marker.require_explicit_unit
      ? `<div class="chip">${escapeHtml(
          t("ui_admin_lab_conversion_required", "Einheit Pflicht")
        )}</div>`
      : "";
```

`altUnitText` (Zeile 360) ersetzen:

```js
  const altUnitText = (marker) => {
    const altUnit = marker && marker.alt_unit;
    if (!altUnit || !altUnit.unit) return "";
    const factor = altUnit.factor_to_canonical;
    return factor == null
      ? String(altUnit.unit)
      : `${String(altUnit.unit)} × ${formatNumber(factor)}`;
  };
```

- [ ] **Step 5: Implement — Tabelle**

(a) In `refRows` nach der Einheiten-Zelle:

```js
          <td>${escapeHtml(definition.canonical_unit || "")}</td>
          <td>${conversionText(definition)}${requiredBadge(definition)}</td>
```

(b) Header (`Zeile 429-438`) zwischen „Einheit" und „Referenz":

```js
          <th>${escapeHtml(t("ui_admin_lab_unit", "Einheit"))}</th>
          <th>${escapeHtml(t("ui_admin_lab_conversion", "Umrechnung"))}</th>
          <th>${escapeHtml(t("ui_admin_lab_range", "Referenz"))}</th>
```

(c) Custom-Zeile (`Zeile 402-413`): `· ${escapeHtml(altUnitText(marker))}` →
`· alt: ${escapeHtml(altUnitText(marker))}`.

- [ ] **Step 6: Implement — i18n (3 Keys)**

`strings.json`:

```json
    "ui_admin_lab_conversion": "Conversion",
    "ui_admin_lab_conversion_required": "Unit required",
    "ui_admin_lab_conversion_none": "—",
```

`translations/de.json`:

```json
    "ui_admin_lab_conversion": "Umrechnung",
    "ui_admin_lab_conversion_required": "Einheit Pflicht",
    "ui_admin_lab_conversion_none": "—",
```

`translations/en.json`: identisch zu `strings.json`. Die drei Keys in
`tests/test_translations.py` → `_REQ_HOM_122_UI_KEYS` aufnehmen.

- [ ] **Step 7: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_panel_js.py -k req_hom_124 -q && python3 -m pytest tests/test_translations.py -k req_hom_122_common_ui_keys -q`
Expected: all PASS.

- [ ] **Step 8: Regression**

Run: `python3 -m pytest tests/test_panel_js.py tests/test_translations.py tests/test_ws_api.py -q && ruff check . && ruff format --check .`
Expected: grün/clean (bestehender Escape-Test bleibt grün: weiterhin `escapeHtml`/
`attrValue`).

- [ ] **Step 9: Commit**

```bash
git add custom_components/health_o_mat/www/health-o-mat-panel-admin.js custom_components/health_o_mat/strings.json custom_components/health_o_mat/translations/de.json custom_components/health_o_mat/translations/en.json tests/test_panel_js.py tests/test_translations.py
git commit -m "feat: show lab unit conversions in admin settings"
```

---

### Task 16: Karten-Disclaimer lokalisieren (`ui_card_lab_disclaimer`)

**Files:**
- Modify: `custom_components/health_o_mat/www/health-o-mat-labs-card.js`
- Modify: `custom_components/health_o_mat/strings.json`, `translations/{de,en}.json`
- Test: `tests/test_card_js.py`, `tests/test_translations.py`

**Interfaces:**
- Consumes: `_language` + `setCardLanguage(hass)` (`health-o-mat-labs-card.js:73-78`) —
  die Karte lädt **keine** HA-Übersetzungsressourcen, sie hält ihren Text lokal.
- Produces: `CARD_TEXT`-Map + `cardText(key)`; `_render` nutzt
  `cardText("ui_card_lab_disclaimer")` statt des Literals. `de` = exakt der bisherige
  Wortlaut, `en` sinngemäß; derselbe Key liegt in `strings.json`/`de`/`en` (Paritäts- und
  Whitelist-Test) — die Übereinstimmung Karte ↔ Übersetzungsdatei pinnt ein Test.
- Übrige Kartentexte bleiben deutsch (bewusste Scope-Grenze, §10).

**Spec-Bezug:** §8.5, REQ-HOM-125 (Karten-Disclaimer lokalisiert), §10 (Scope-Grenze).

- [ ] **Step 1: Write the failing tests** (`tests/test_card_js.py`, ans Ende)

```python
# --- REQ-HOM-125: Karten-Disclaimer lokalisiert -----------------------------


def test_req_hom_125_labs_card_disclaimer_uses_localized_text():
    source = _labs_card_source()

    assert "ui_card_lab_disclaimer" in source
    assert "CARD_TEXT" in source
    assert "cardText(" in source
    assert "setCardLanguage" in source


_NODE_LABS_DISCLAIMER_RUNNER = """import { readFileSync } from "node:fs";
import vm from "node:vm";

const source = readFileSync(process.argv[2], "utf8");

class FakeShadowRoot {
  constructor() { this.innerHTML = ""; }
  addEventListener() {}
  removeEventListener() {}
  querySelector() { return null; }
  querySelectorAll() { return []; }
}
class FakeHTMLElement {
  constructor() { this._shadow = new FakeShadowRoot(); }
  attachShadow() { return this._shadow; }
  get shadowRoot() { return this._shadow; }
}
const context = {
  HTMLElement: FakeHTMLElement,
  customElements: {
    _classes: {},
    get() { return undefined; },
    define(tag, cls) { this._classes[tag] = cls; },
  },
  window: {},
  document: { createElement: () => ({}) },
  console: { info: () => {}, log: () => {}, warn: () => {}, error: () => {} },
};
vm.createContext(context);
vm.runInContext(source, context, { filename: "health-o-mat-labs-card.js" });

const CardClass = context.customElements._classes["health-o-mat-labs-card"];
function render(language) {
  const card = new CardClass();
  card._config = {
    entry_id: "entry-1",
    person_mode: "fixed",
    show_disclaimer: true,
    allow_manual_entry: false,
    show_trend: false,
  };
  card._normalized = null;
  card._data = {
    person: "Alex",
    labs: {
      categories: [{ key: "liver", name: "Leber", hidden: false }],
      markers: {
        alt: {
          category: "liver", name: "ALT", name_de: "ALT", name_en: "ALT",
          unit: "U/L", value: null, history: [],
        },
      },
    },
  };
  card.hass = { language };
  card._render();
  return card.shadowRoot.innerHTML;
}
process.stdout.write(JSON.stringify({ de: render("de"), en: render("en-US") }));
"""


@pytest.mark.skipif(shutil.which("node") is None, reason="node nicht verfügbar")
def test_req_hom_125_labs_card_disclaimer_follows_card_language(tmp_path):
    out = json.loads(
        _run_node(
            tmp_path,
            _NODE_LABS_DISCLAIMER_RUNNER,
            [str(Path(_LABS_CARD_JS))],
            "runner_labs_disclaimer_i18n",
        )
    )

    assert "keine medizinische Beratung" in out["de"]
    assert "Hinweis" in out["de"]
    assert "not medical advice" in out["en"]
    assert "Hinweis" not in out["en"]
```

`tests/test_translations.py`: `"ui_card_lab_disclaimer"` in `_REQ_HOM_122_UI_KEYS`
aufnehmen.

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_card_js.py -k req_hom_125 -q`
Expected: FAIL — `CARD_TEXT`/`ui_card_lab_disclaimer` fehlen.

- [ ] **Step 3: Implement — `labs-card.js`**

Nach `labDisplayName` (`Zeile 80-88`):

```js
/* Kartenlokale Übersetzungen: die Karte lädt keine HA-Ressourcen, braucht aber
 * den Disclaimer sprachabhängig. Die Keys sind identisch zu `common` in
 * strings.json; ein Test pinnt die Gleichheit der Texte. */
const CARD_TEXT = {
  de: {
    ui_card_lab_disclaimer:
      "⚠️ Hinweis: keine medizinische Beratung — Richtwerte, keine Diagnose. Referenzbereiche in den Einstellungen anpassen.",
  },
  en: {
    ui_card_lab_disclaimer:
      "⚠️ Note: not medical advice — reference values, not a diagnosis. Adjust reference ranges in the settings.",
  },
};

function cardText(key) {
  const language = _language === "en" ? "en" : "de";
  return (CARD_TEXT[language] && CARD_TEXT[language][key]) || CARD_TEXT.de[key] || "";
}
```

`_render` (`Zeile 864-866`) ersetzen:

```js
    const disclaimer = cfg.showDisclaimer
      ? `<div class="labs-disclaimer" role="note">${escapeHtml(
          cardText("ui_card_lab_disclaimer")
        )}</div>`
      : "";
```

- [ ] **Step 4: Implement — i18n (1 Key)**

`strings.json`:

```json
    "ui_card_lab_disclaimer": "⚠️ Note: not medical advice — reference values, not a diagnosis. Adjust reference ranges in the settings.",
```

`translations/de.json`:

```json
    "ui_card_lab_disclaimer": "⚠️ Hinweis: keine medizinische Beratung — Richtwerte, keine Diagnose. Referenzbereiche in den Einstellungen anpassen.",
```

`translations/en.json`: identisch zu `strings.json`.

- [ ] **Step 5: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_card_js.py -k req_hom_125 -q && python3 -m pytest tests/test_translations.py -k req_hom_122_common_ui_keys -q`
Expected: all PASS.

- [ ] **Step 6: Regression**

Run: `python3 -m pytest tests/test_card_js.py tests/test_translations.py -q && ruff check . && ruff format --check .`
Expected: grün/clean.

- [ ] **Step 7: Commit**

```bash
git add custom_components/health_o_mat/www/health-o-mat-labs-card.js custom_components/health_o_mat/strings.json custom_components/health_o_mat/translations/de.json custom_components/health_o_mat/translations/en.json tests/test_card_js.py tests/test_translations.py
git commit -m "feat: localize the labs card disclaimer"
```

---

## Wave 6 — Export & Import

### Task 17: `exporter.py` — voidete Laborzeilen mit `voided_at`/`void_reason` (+ Import-Test)

**Files:**
- Modify: `custom_components/health_o_mat/exporter.py`
- Test: `tests/test_import_backup.py`
- **Keine** Logikänderung in `importer.py` (§2.15: die neuen Spalten werden vom toleranten
  Parser ignoriert; voidete Zeilen sind über die Dedupe-Schlüssel gegen die **rohen**
  Listen bereits `skipped`).

**Interfaces:**
- Consumes: `store.entry(eid).get("lab_readings")` (roh, inkl. voided),
  `_LAB_VALUES_HEADER` (`exporter.py:15`), `rows_to_csv_string`.
- Produces: `lab_values.csv` enthält **aktive und voidete** Zeilen, Header erweitert um
  `voided_at;void_reason`. `drinks.csv`/`readings.csv` bleiben unverändert „nur aktive"
  (`_combined`-Getränke/readings-Zweig bleibt `active_*`).
- Import: keine Codeänderung; Test beweist `skipped` für exportierte voidete Zeilen.

**Spec-Bezug:** §2.14 (Export enthält voidete Zeilen), §2.15 (nur `lab_values`, Import
überspringt), REQ-HOM-129.

- [ ] **Step 1: Write the failing tests** (`tests/test_import_backup.py`)

(a) `_LAB_CSV_HEADER` (`Zeile 1057`) ersetzen:

```python
_LAB_CSV_HEADER = (
    "zeitstempel;person;marker;kategorie;wert;einheit;"
    "eingegeben_als_wert;eingegeben_als_einheit;berichts_referenz;"
    "voided_at;void_reason"
)
```

(b) Ans Dateiende:

```python
def test_req_hom_129_export_csv_includes_voided_lab_rows_with_reason(tmp_path):
    """[REQ-HOM-129] lab_values.csv enthält voidete Zeilen inkl. Grund."""
    exporter = _load("exporter")
    store = _fresh_store()
    _run(store.set_person("e1", "Caro"))
    _run(
        store.add_lab_reading(
            "e1", "2026-10-31T09:00:00+01:00", "alt", 32.0, "U/L", 32.0, "U/L"
        )
    )
    _run(
        store.add_lab_reading(
            "e1", "2026-01-01T09:00:00+01:00", "crp", 4.8, "mg/L", 4.8, "mg/L"
        )
    )
    old = next(
        reading
        for reading in store.entry("e1")["lab_readings"]
        if reading["marker_key"] == "crp"
    )
    _run(store.void_lab_reading("e1", old["id"], reason="retention"))

    hass = MagicMock()
    hass.config.path = MagicMock(return_value=str(tmp_path))
    hass.async_add_executor_job = AsyncMock(side_effect=lambda fn: fn())
    hass.services.async_call = AsyncMock()

    _run(exporter.async_export_csv(hass, store, _call({"dataset": "lab_values"})))

    written = list(tmp_path.glob("*lab*"))
    assert written
    content = written[0].read_text(encoding="utf-8-sig")
    assert content.splitlines()[0] == _LAB_CSV_HEADER
    assert "crp" in content
    assert "retention" in content
    assert "alt" in content
    # Genau eine Zeile ohne voided_at (der aktive alt-Wert) + Header.
    assert len(content.splitlines()) == 3


def test_req_hom_129_import_skips_exported_voided_rows():
    """[REQ-HOM-129] Re-Import der voideten Export-Zeile zählt als skipped."""
    importer = _load("importer")
    text = (
        "zeitstempel;person;marker;kategorie;wert;einheit;"
        "eingegeben_als_wert;eingegeben_als_einheit;berichts_referenz;"
        "voided_at;void_reason\n"
        "2026-01-01T09:00:00+01:00;Caro;crp;inflammation;4.8;mg/L;4.8;mg/L;;"
        "2026-02-01T00:00:00+01:00;retention\n"
    )
    existing = [
        {
            "ts": "2026-01-01T09:00:00+01:00",
            "marker_key": "crp",
            "value": 4.8,
            "voided_at": "2026-02-01T00:00:00+01:00",
            "void_reason": "retention",
        }
    ]

    plan = importer.plan_import(
        text, "lab_values", existing_lab_readings=existing, lab_custom_markers=[]
    )

    assert plan.skipped == 1
    assert plan.rejected == 0
    assert plan.lab_readings == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_import_backup.py -k req_hom_129 -q`
Expected: FAIL — Export-Header weicht ab / die voidete Zeile fehlt (der Import-Test ist
heute schon grün, bleibt als Regressionsschutz).

> Hinweis: `test_req_hom_129_import_skips_exported_voided_rows` ist bewusst ein
> **Bestätigungstest** der bestehenden Semantik (§2.15: keine Logikänderung). Er darf im
> Red-Schritt bereits grün sein — der Task ändert `importer.py` nicht.

- [ ] **Step 3: Implement — `exporter.py`**

(a) Header (`Zeile 15-25`) erweitern:

```python
_LAB_VALUES_HEADER = [
    "zeitstempel",
    "person",
    "marker",
    "kategorie",
    "wert",
    "einheit",
    "eingegeben_als_wert",
    "eingegeben_als_einheit",
    "berichts_referenz",
    "voided_at",
    "void_reason",
]
```

(b) In `_combined` (`Zeile 75`): Laborwerte **roh** lesen (inkl. voided):

```python
        # REQ-HOM-129: Laborwerte werden inkl. voideter Zeilen exportiert
        # (Retention/Grund nachvollziehbar). Getränke/BD bleiben "nur aktive".
        lab_readings = list(store.entry(eid).get("lab_readings") or [])
```

(c) In der Labor-Zeile (`Zeile 141-156`) zwei Spalten anhängen:

```python
                            reading.get("report_ref") or "",
                            reading.get("voided_at") or "",
                            reading.get("void_reason") or "",
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_import_backup.py -k "req_hom_129 or export_csv" -q`
Expected: all PASS (inkl. bestehender `test_export_csv_excludes_voided_entries` für
Getränke/BD).

- [ ] **Step 5: Regression**

Run: `python3 -m pytest tests/test_import_backup.py tests/test_restore.py -q && ruff check custom_components/health_o_mat/exporter.py tests/test_import_backup.py && ruff format --check custom_components/health_o_mat/exporter.py tests/test_import_backup.py`
Expected: grün/clean.

- [ ] **Step 6: Commit**

```bash
git add custom_components/health_o_mat/exporter.py tests/test_import_backup.py
git commit -m "feat: export voided lab values with void metadata"
```

---

## Wave 7 — Beispiel, E2E, Doku

### Task 18: Beispiel-Dashboard + `tests/test_dashboards.py` + README

**Files:**
- Create: `examples/dashboard-labs-card.yaml`
- Modify: `tests/test_dashboards.py`
- Modify: `README.md`
- Test: `tests/test_dashboards.py`

**Interfaces:**
- Consumes: `custom:health-o-mat-labs-card` + Schlüsselsatz aus `normalizeCardConfig`
  (`health-o-mat-labs-card.js:234-252`).
- Produces: Beispiel-Datei **ohne** Entity-Referenzen; `LABS_CARD_TYPE`/`LABS_CARD_KEYS` +
  erweiterte Sammel-/Key-Prüfung; README-Bullet inkl. Hinweis
  „Personenfilter anpassen oder entfernen".

**Spec-Bezug:** §9 (YAML, Filter auskommentiert, §9.1 Testanpassung), REQ-HOM-126 (P3).

- [ ] **Step 1: Write the failing tests** — `tests/test_dashboards.py`

(a) Nach `CARD_KEYS` (`Zeile 108-131`):

```python
# Laborwerte-Karte (REQ-HOM-122/126): eigener Typ + Schlüsselsatz.
# Spiegel von `normalizeCardConfig` in `www/health-o-mat-labs-card.js`.
LABS_CARD_TYPE = "custom:health-o-mat-labs-card"
LABS_CARD_KEYS = {
    "type",
    "entry_id",
    "person_mode",
    "person_filter",
    "default_person",
    "show_categories",
    "show_trend",
    "allow_manual_entry",
    "show_disclaimer",
}
```

(b) `extract_card_configs` (`Zeile 134-143`):

```python
def extract_card_configs(node, out):
    """Sammle alle Konfigurationen der mitgelieferten Karten."""
    if isinstance(node, dict):
        if node.get("type") in (CARD_TYPE, LABS_CARD_TYPE):
            out.append(node)
        for value in node.values():
            extract_card_configs(value, out)
    elif isinstance(node, list):
        for item in node:
            extract_card_configs(item, out)
```

(c) Im Sammeltest (`Zeile 162-166`):

```python
        for card in card_configs:
            allowed = LABS_CARD_KEYS if card.get("type") == LABS_CARD_TYPE else CARD_KEYS
            unknown = set(card) - allowed
            assert not unknown, f"{path}: unbekannte Karten-Keys {sorted(unknown)}"
```

(d) Neuer Test am Dateiende:

```python
def test_req_hom_126_labs_card_example_exists_and_uses_only_labs_keys():
    """[REQ-HOM-126] Das Labs-Card-Beispiel parst und nutzt nur erlaubte Keys."""
    path = os.path.join(
        os.path.dirname(__file__), "..", "examples", "dashboard-labs-card.yaml"
    )
    assert os.path.exists(path), "examples/dashboard-labs-card.yaml fehlt"
    with open(path) as fh:
        data = yaml.safe_load(fh)

    assert isinstance(data, dict)
    configs: list[dict] = []
    extract_card_configs(data, configs)
    assert len(configs) == 2, "das Beispiel zeigt zwei Ansichten der Labs-Card"
    for card in configs:
        assert card["type"] == LABS_CARD_TYPE
        assert set(card) <= LABS_CARD_KEYS
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_dashboards.py -q`
Expected: FAIL — `AssertionError: examples/dashboard-labs-card.yaml fehlt`.

- [ ] **Step 3: Create `examples/dashboard-labs-card.yaml`**

```yaml
# HA Health-O-Mat — Beispiel-Dashboard für die Laborwerte-Karte
# Import: Einstellungen → Dashboards → Dashboard hinzufügen → "Neues Dashboard aus YAML"
#
# Voraussetzung: die Integration ist installiert (die Karte wird beim Setup
# automatisch als Lovelace-Ressource registriert).
title: Health-O-Mat (Laborwerte)
views:
  - title: Laborwerte            # alle Defaults (Trend, Eingabe, Disclaimer an)
    path: laborwerte
    icon: mdi:flask-outline
    cards:
      - type: custom:health-o-mat-labs-card

  - title: Anzeige               # reine Anzeige, Personen-Dropdown
    path: anzeige
    icon: mdi:eye-outline
    cards:
      - type: custom:health-o-mat-labs-card
        person_mode: selector             # Dropdown (kein fest verdrahteter Entry)
        # person_filter: ["max"]          # optional: Whitelist (entry_id/Slug/Name) —
        #                                 # anpassen oder auskommentiert lassen
        # default_person: "max"           # optional: Vorauswahl im Dropdown
        show_trend: true
        allow_manual_entry: false
        show_categories: ["liver", "kidney", "lipids"]   # Tab-Reihenfolge
        # show_disclaimer: false          # nur bewusst abschalten
```

- [ ] **Step 4: README-Verweis**

(a) Im Abschnitt „Dashboard-Beispiele" (`README.md:806-820`) als letzten Bullet:

```markdown
- [`examples/dashboard-labs-card.yaml`](examples/dashboard-labs-card.yaml) — zeigt die
  **Laborwerte-Karte** (`custom:health-o-mat-labs-card`) in zwei Ansichten (alle Defaults,
  reine Anzeige mit Personen-Dropdown); Personenfilter anpassen oder entfernen — ohne
  Filter zeigt die Karte alle Personen
```

(b) Im Labs-Card-Abschnitt (`README.md:557-578`) am Absatzende:

```markdown
Ein vollständiges Beispiel-Dashboard mit beiden Ansichten liegt unter
[`examples/dashboard-labs-card.yaml`](examples/dashboard-labs-card.yaml).
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_dashboards.py -q`
Expected: all PASS, keine Ausnahme-Regel für die neue Datei.

- [ ] **Step 6: Regression**

Run: `python3 -m pytest tests/test_dashboards.py tests/test_card_js.py tests/test_frontend.py -q && ruff check . && ruff format --check .`
Expected: grün/clean.

- [ ] **Step 7: Commit**

```bash
git add examples/dashboard-labs-card.yaml tests/test_dashboards.py README.md
git commit -m "docs: add lab values card dashboard example"
```

---

### Task 19: E2E — vier Szenarien (`tests_e2e/test_lab_values_e2e.py`)

**Files:**
- Modify: `tests_e2e/test_lab_values_e2e.py`
- Modify: `tests_e2e/conftest.py` **nur falls** ein Fixture fehlt (die vorhandenen
  `logged_in_page`, `hass_base_url`, `hass_bearer_token`, `panel_person` genügen)

**Interfaces:**
- Consumes: `open_panel`, `wait_for_detail`, `wait_for_overview`, `tile`, `tab_keys`,
  `_panel_data`, `_wait_for`, `_settings`, `CARD_TIMEOUT`, `_ws_command`,
  `restore_lab_options` (Fixture).
- Produces: vier Tests — (a) Batch-Dialog schreibt zwei Zeilen + Duplikat-Fehler behält
  Eingaben und Payload, (b) Disclaimer sichtbar/abschaltbar + Leerfall, (c)
  Admin-Faktorspalte, (d) Beispiel-Dashboard rendert die Labs-Card.
- Fixture `restore_lab_options` wird um `lab_hide_panel_disclaimer` erweitert, damit der
  Disclaimer-Test die geteilte Instanz sauber hinterlässt.

**Spec-Bezug:** §12 (E2E-Zeile), REQ-HOM-123/124/125/126, §8.7 (echter Nicht-Admin-E2E
bleibt Folge-Task).

- [ ] **Step 1: Selectors + Imports ergänzen**

Imports (Dateikopf): `import yaml` und `from pathlib import Path` ergänzen.

Selectors bei den bestehenden Labor-Selectoren (`Zeile 75-90`):

```python
LAB_REPORT_FORM = "details.lab-report-form"
LAB_REPORT_FILL_VISIBLE = "[data-action='lab-report-fill-visible']"
LAB_REPORT_ADD = "[data-action='lab-report-add']"
LAB_REPORT_SAVE = "[data-action='lab-report-save']"
LAB_REPORT_DISCARD = "[data-action='lab-report-discard']"
LAB_REPORT_MARKER = "[data-field='lab-report-marker-%d']"
LAB_REPORT_VALUE = "[data-field='lab-report-value-%d']"
LAB_REPORT_UNIT = "[data-field='lab-report-unit-%d']"
LAB_REPORT_ERROR = ".msg.error"
LAB_DISCLAIMER = ".labs-disclaimer"
DASH_DISCLAIMER_CHECKBOX = "[data-field='lab-hide-panel-disclaimer']"
```

- [ ] **Step 2: Fixture erweitern** (`restore_lab_options`, `Zeile 245`)

Snapshot um den Disclaimer-Schalter erweitern und im Restore mit zurückschreiben:

```python
    snapshot = {
        "lab_custom_markers": before.get("lab_custom_markers") or [],
        "lab_ref_overrides": before.get("lab_ref_overrides") or {},
        "lab_hidden_categories": before.get("lab_hidden_categories") or [],
        "lab_hide_panel_disclaimer": before.get("lab_hide_panel_disclaimer") is True,
    }
```

(Die bestehende `changed`-Prüfung und der `set_settings`-Restore funktionieren unverändert,
weil `lab_hide_panel_disclaimer` ab Task 10 ein gültiger Settings-Key ist.)

- [ ] **Step 3: Write the four failing tests** (ans Dateiende)

```python
# --- REQ-HOM-123…126: Batch, Disclaimer, Admin-Faktoren, Beispiel-Dashboard --


def _open_labs_tab(page, base_url: str, person: str):
    panel = open_panel(page, base_url, person=person)
    wait_for_detail(panel)
    panel.locator(LAB_TAB).click()
    panel.locator(LAB_CATEGORY_BAR).wait_for(state="visible", timeout=CARD_TIMEOUT)
    return panel


def _open_report_form(panel):
    form = panel.locator(LAB_REPORT_FORM)
    form.wait_for(state="attached", timeout=CARD_TIMEOUT)
    if not form.evaluate("(el) => el.open"):
        form.locator("summary").click()
    panel.locator(LAB_REPORT_ADD).wait_for(state="visible", timeout=CARD_TIMEOUT)
    return form


def test_req_hom_123_lab_report_dialog_writes_and_rejects_duplicates(
    logged_in_page, hass_base_url, hass_bearer_token, panel_person
):
    """[REQ-HOM-123] Zwei Zeilen in einem Vorgang; Duplikat behält Eingaben."""
    page = logged_in_page
    entry_id = panel_person["entry_id"]
    alt_value = round(100 + (uuid.uuid4().int % 90) / 10, 1)
    crp_value = round(10 + (uuid.uuid4().int % 90) / 10, 1)

    panel = _open_labs_tab(page, hass_base_url, panel_person["slug"])
    _open_report_form(panel)
    panel.locator(LAB_REPORT_ADD).click()
    panel.locator(LAB_REPORT_MARKER % 0).select_option("alt")
    panel.locator(LAB_REPORT_VALUE % 0).fill(str(alt_value))
    panel.locator(LAB_REPORT_MARKER % 1).select_option("crp")
    panel.locator(LAB_REPORT_VALUE % 1).fill(str(crp_value))
    panel.locator(LAB_REPORT_UNIT % 1).fill("mg/L")
    panel.locator(LAB_REPORT_SAVE).click()

    after = _wait_for(
        lambda: _panel_data(hass_base_url, hass_bearer_token, entry_id),
        lambda value: value["labs"]["markers"]["crp"].get("reported_value") == crp_value,
        "the report values to reach the store",
    )
    assert after["labs"]["markers"]["alt"]["reported_value"] == alt_value
    assert after["labs"]["markers"]["crp"]["unit"] == "mg/L"

    # Duplikat: derselbe aufgelöste Marker zweimal → Serverfehler, kein Write.
    before = after["labs"]["markers"]["alt"].get("reported_value")
    _open_report_form(panel)
    panel.locator(LAB_REPORT_ADD).click()
    panel.locator(LAB_REPORT_MARKER % 0).select_option("alt")
    panel.locator(LAB_REPORT_VALUE % 0).fill("33")
    panel.locator(LAB_REPORT_MARKER % 1).select_option("alt")
    panel.locator(LAB_REPORT_VALUE % 1).fill("34")
    panel.locator(LAB_REPORT_SAVE).click()

    error = panel.locator(LAB_REPORT_ERROR).first
    error.wait_for(state="visible", timeout=CARD_TIMEOUT)
    assert "Zeile 2" in error.inner_text()
    assert panel.locator(LAB_REPORT_VALUE % 0).input_value() == "33"

    unchanged = _panel_data(hass_base_url, hass_bearer_token, entry_id)
    assert unchanged["labs"]["markers"]["alt"].get("reported_value") == before


def test_req_hom_125_panel_disclaimer_visibility_and_empty_state(
    logged_in_page, hass_base_url, hass_bearer_token, panel_person, restore_lab_options
):
    """[REQ-HOM-125] Sichtbar ohne Settings-Load, abschaltbar, auch im Leerfall."""
    page = logged_in_page
    entry_id = panel_person["entry_id"]
    settings = _settings(hass_base_url, hass_bearer_token, entry_id)

    panel = _open_labs_tab(page, hass_base_url, panel_person["slug"])
    disclaimer = panel.locator(LAB_DISCLAIMER)
    disclaimer.wait_for(state="visible", timeout=CARD_TIMEOUT)
    assert "medical" in disclaimer.inner_text().lower()

    # Admin: Hinweis ausblenden.
    panel.locator(SETTINGS_GEAR).click()
    panel.locator(SETTINGS_FORM).wait_for(state="visible", timeout=CARD_TIMEOUT)
    checkbox = panel.locator(DASH_DISCLAIMER_CHECKBOX)
    checkbox.wait_for(state="visible", timeout=CARD_TIMEOUT)
    checkbox.set_checked(True)
    panel.locator(SAVE_BUTTON).click()
    _wait_for(
        lambda: _settings(hass_base_url, hass_bearer_token, entry_id),
        lambda value: value.get("lab_hide_panel_disclaimer") is True,
        "the disclaimer option to be persisted",
    )

    panel.locator(BACK).click()
    wait_for_overview(panel)
    tile(panel, entry_id).click()
    wait_for_detail(panel)
    panel.locator(LAB_TAB).click()
    panel.locator(LAB_CATEGORY_BAR).wait_for(state="visible", timeout=CARD_TIMEOUT)
    assert panel.locator(LAB_DISCLAIMER).count() == 0

    # Alle Kategorien ausblenden → Leerzustand, Hinweis wieder sichtbar.
    panel.locator(SETTINGS_GEAR).click()
    panel.locator(SETTINGS_FORM).wait_for(state="visible", timeout=CARD_TIMEOUT)
    panel.locator(DASH_DISCLAIMER_CHECKBOX).set_checked(False)
    for category in settings["lab_catalog"]["categories"]:
        box = panel.locator(f"[data-field='lab-hide-{category['key']}']")
        if box.count():
            box.set_checked(False)
    panel.locator(SAVE_BUTTON).click()
    _wait_for(
        lambda: _settings(hass_base_url, hass_bearer_token, entry_id),
        lambda value: bool(value.get("lab_hidden_categories")),
        "all categories to be hidden",
    )
    panel.locator(BACK).click()
    wait_for_overview(panel)
    tile(panel, entry_id).click()
    wait_for_detail(panel)
    panel.locator(LAB_TAB).click()
    empty_disclaimer = panel.locator(LAB_DISCLAIMER)
    empty_disclaimer.wait_for(state="visible", timeout=CARD_TIMEOUT)
    assert "medical" in empty_disclaimer.inner_text().lower()
    assert "hidden" in panel.locator(".msg").first.inner_text().lower()


def test_req_hom_124_admin_conversion_column_visible(
    logged_in_page, hass_base_url, panel_person
):
    """[REQ-HOM-124] Katalog-Tabelle zeigt Alt-Einheit × Faktor → kanonisch."""
    page = logged_in_page
    panel = open_panel(page, hass_base_url, person=panel_person["slug"])
    wait_for_detail(panel)
    panel.locator(SETTINGS_GEAR).click()
    panel.locator(LAB_REF_TABLE).wait_for(state="visible", timeout=CARD_TIMEOUT)

    table = panel.locator(LAB_REF_TABLE)
    text = table.inner_text()
    assert "mg/dL" in text
    assert "→ µmol/L" in text
    assert "Unit required" in text


def test_req_hom_126_labs_card_example_dashboard_renders(
    logged_in_page, hass_base_url, hass_bearer_token
):
    """[REQ-HOM-126] Die Beispiel-Dashboard-YAML rendert die Labs-Card."""
    page = logged_in_page
    url_path = f"e2e-labs-{uuid.uuid4().hex[:8]}"
    config = yaml.safe_load(
        Path(__file__).resolve().parents[1].joinpath(
            "examples", "dashboard-labs-card.yaml"
        ).read_text(encoding="utf-8")
    )
    created = _ws_command(
        hass_base_url,
        hass_bearer_token,
        {
            "type": "lovelace/dashboards/create",
            "url_path": url_path,
            "title": "E2E Labs",
            "mode": "storage",
            "show_in_sidebar": False,
            "require_admin": False,
            "icon": "mdi:flask-outline",
        },
    )
    dashboard_id = (created or {}).get("id")
    try:
        _ws_command(
            hass_base_url,
            hass_bearer_token,
            {"type": "lovelace/config/save", "url_path": url_path, "config": config},
        )
        page.goto(f"{hass_base_url}/{url_path}/laborwerte")
        card = page.locator("health-o-mat-labs-card").first
        card.wait_for(state="attached", timeout=60000)
        card.locator("ha-card").wait_for(state="visible", timeout=60000)
    finally:
        if dashboard_id:
            _ws_command(
                hass_base_url,
                hass_bearer_token,
                {"type": "lovelace/dashboards/delete", "dashboard_id": dashboard_id},
            )
```

- [ ] **Step 4: Run the E2E suite locally**

Run: `cd tests_e2e && python3 -m pytest test_lab_values_e2e.py -q` (E2E-Instanz muss
laufen; siehe `tests_e2e/pytest.ini` und `.github/workflows/e2e.yaml`)
Expected: alle Tests dieser Datei PASS. Bricht ein Selector, ist die
`data-field`/`data-action`-Benennung aus Task 11/12/13/14 nicht eingehalten — dort
korrigieren, nicht den Test.

- [ ] **Step 5: Regression (ohne E2E)**

Run: `python3 -m pytest -q`
Expected: all PASS (die Wurzel-`pytest.ini` schließt `tests_e2e/` aus).

- [ ] **Step 6: Commit**

```bash
git add tests_e2e/test_lab_values_e2e.py
git commit -m "test: cover lab report, disclaimer and admin conversions in e2e"
```

---

### Task 20: Doku — README + `docs/REQUIREMENTS.md`

**Files:**
- Modify: `README.md`
- Modify: `docs/REQUIREMENTS.md`

**Interfaces:**
- Consumes: die finalen Testergebnisse aus dem Final Integration Check (Testzahl,
  E2E-Zahl, ruff-Status) — dieser Task läuft **zuletzt**.
- Produces: dokumentierte Services `add_lab_report`/`remove_lab_report`, Optionen
  (`lab_retention_months`, `lab_hide_panel_disclaimer`), Retention-/Export-Verhalten,
  REQ-Status „Erledigt" (123, 124, 125, 126, 128, 129 — **127 bleibt offen**, eigener
  Plan) inkl. Belege.

**Spec-Bezug:** §11 (Auswirkungen, REQ-IDs), §2.14/§2.15 (Retention/Export), §8
(Disclaimer), §6.5 (Verwerfen).

- [ ] **Step 1: README — Services ergänzen**

Im Abschnitt „Services: Laborwerte erfassen und korrigieren" (`README.md:522-555`) **vor**
`remove_last_lab_value` einfügen:

````markdown
```yaml
action: health_o_mat.add_lab_report
data:
  person: "Caro"                                   # optional — einzige Person, wenn leer
  ts: "2026-11-01T09:15:00+01:00"                  # ein Zeitpunkt für den ganzen Bericht
  report_ref: "https://example.com/laborbericht/123"
  values:
    - {marker: alt, value: 32, unit: U/L}
    - {marker: creatinine, value: 1.1, unit: mg/dL}
    - {marker: crp, value: 4.8, unit: mg/L}
    - {marker: tsh, value: 1.9}                    # ohne unit = kanonische Einheit
```

- `add_lab_report` erfasst **einen Bericht als einen Vorgang**: ein Zeitpunkt, eine
  Berichts-Referenz, **alles-oder-nichts** (eine ungültige Zeile lehnt den gesamten
  Bericht ab), genau ein Store-Write und **ein** Audit-Eintrag (`lab_values_added`).
- Leere Zeilen werden ignoriert; höchstens **200** befüllte Zeilen pro Aufruf (der Dialog
  hat einen UI-Soft-Cap von **60**); derselbe Marker darf im selben Bericht nur einmal
  vorkommen (Alias-Kollision zählt: `gpt` + `alt` → `duplicate_marker`).
- Fehler nennen Code **und** Originalzeile, z. B.
  `Zeile 3 (kreatinin): unknown_marker` (Leerzeilen zählen mit). Die WS-Antwort liefert
  dasselbe strukturiert als `{"ok": false, "error": {code, params, message}}`.
- Der Aufruf ist **nicht** idempotent: zweimal gesendet = zweimal gespeichert. Vor einem
  Retry `panel_data.labs.last_report` prüfen; einen versehentlich doppelten Bericht
  entfernt `remove_lab_report` in einem Schritt.
````

Nach `remove_last_lab_value`:

````markdown
```yaml
action: health_o_mat.remove_lab_report
data:
  person: "Caro"                                   # optional
  ts: "2026-11-01T09:15:00+01:00"                  # Pflicht — z. B. aus last_report.ts
  report_ref: "https://example.com/laborbericht/123"   # optional: nur dieser Bericht
```

- Verwirft **alle aktiven** Werte dieses Zeitpunkts (mit `report_ref`: nur Einträge mit
  exakt diesem Tag). Ohne Treffer: `no_active_report`; ungültiges `ts`: `invalid_ts`.
- Das Verwerfen **voidet** (kein Hard-Delete) mit `void_reason = "report_discarded"`;
  einzeln wiederherstellbar über `restore_entry` (`kind: lab_values`). Die UI bietet
  „Diesen Bericht verwerfen" mit Sicherheitsabfrage, sichtbar nur bei aktivem
  `labs.last_report`.
````

- [ ] **Step 2: README — Optionen/Verhalten ergänzen**

- **Options-Wizard „Grundlagen"**: `lab_retention_months` (0 = aus, 0…120) — eigene
  Labor-Retention, **unabhängig** von der Getränke-/BD-Retention. Bei `> 0` werden beim
  Setup Laborwerte älter als N Monate **voidet** (`void_reason = "retention"`, ein Audit
  `lab_values_retention`), kein Archiv, über `restore_entry` rückholbar.
- **Admin „Laborwerte"**: Spalte „Umrechnung" (`mg/dL × 88,4 → µmol/L`, Faktor
  sprachabhängig formatiert) + Badge „Einheit Pflicht"; Checkbox „Medizin-Hinweis im Panel
  ausblenden" (`lab_hide_panel_disclaimer`, Default aus = Hinweis sichtbar).
- **Panel-Lab-Tab**: Hinweis oberhalb der Kategorie-Leiste; Leerzustand
  „Alle Kategorien ausgeblendet" bzw. „Keine Laborwert-Kategorie sichtbar".
- **Karte**: Disclaimer folgt der Karten-/HA-Sprache (`ui_card_lab_disclaimer`).
- **CSV-Export** `lab_values.csv` enthält jetzt **auch voidete** Zeilen inkl.
  `voided_at`/`void_reason`; `drinks.csv`/Blutdruck-CSV bleiben „nur aktive". Re-Import
  voideter Zeilen zählt sie als `skipped`.

- [ ] **Step 3: `docs/REQUIREMENTS.md` — Status/Belege**

(a) In den Kapiteln REQ-HOM-123, 124, 125, 126, 128, 129:

- `**Status: Offen — geplant …**` → `**Status: Erledigt (Datum des Abschlusses, Branch
  `feat/lab-batch-visibility`)**` (konkretes Datum, kein Platzhalter).
- Alle `- [ ]`-Akzeptanzkriterien → `- [x]`.
- `**Belege:**` durch die tatsächlichen Testnamen + Zahlen ersetzen (aus dem Final
  Integration Check), z. B.:
  `tests/test_logic.py::test_req_hom_123_validate_rows_*` /
  `::test_req_hom_128_lab_report_matches_*`,
  `tests/test_store.py::test_req_hom_123_add_lab_readings_*` /
  `::test_req_hom_128_void_lab_report_*` / `::test_req_hom_129_void_lab_readings_before_*`,
  `tests/test_lab_services.py`, `tests/test_ws_api.py`, `tests/test_card_js.py`,
  `tests/test_panel_js.py`, `tests/test_import_backup.py`, `tests/test_dashboards.py`,
  `tests_e2e/test_lab_values_e2e.py`; dazu die im Final Integration Check gemessene
  Testzahl als konkrete Zahl (kein Platzhalter), `ruff check .` +
  `ruff format --check .` clean und die gemessene E2E-Testzahl.
- **REQ-HOM-127 bleibt unverändert offen** (eigener Plan; Spec §14.3).

(b) Kopfzeile `**Stand:**` auf den Abschlussdatensatz umstellen (REQ-HOM-123…126/128/129
**umgesetzt**, 127 separat, Branch `feat/lab-batch-visibility`, noch kein Release).

(c) Die `**REQ-HOM-123…129 geplant**`-Zeile (Zeile 20-23) durch einen
`**REQ-HOM-123…126/128/129 umgesetzt**`-Block ersetzen.

(d) Im „Changelog der Anforderungen" (Tabelle ab Zeile 1575) eine neue Zeile **oben**
einfügen:

```markdown
| Datum des Abschlusses | **REQ-HOM-123…126/128/129 umgesetzt — Laborwerte: Batch, Undo, Retention & Sichtbarkeit** (Branch `feat/lab-batch-visibility`; Spec `docs/superpowers/specs/2026-11-01-lab-values-batch-and-visibility-design.md`, Plan `docs/superpowers/plans/2026-11-01-lab-values-batch-and-visibility.md`): Service + WS `add_lab_report` (ein `ts`/`report_ref`, Leerzeilen ignoriert, Limits 60/200, strukturierte Fehler `{code, params, message}`, ein Store-Write/ein Audit `lab_values_added` mit Rollback), symmetrisches `remove_lab_report` (voidet alle aktiven Werte eines Zeitpunkts, optional per `report_ref`, Audit `lab_report_voided`, UI-Aktion mit Sicherheitsabfrage), Mehrzeilen-Dialog in Card und Panel (Hybrid-Füllung, Einheiten-Dropdown aus `alt_units`, Single-Flight), Admin-Spalte „Umrechnung" + Badge „Einheit Pflicht", Panel-Medizin-Hinweis (Default sichtbar, abschaltbar über `lab_hide_panel_disclaimer`, Transport via `panel_data`), Karten-Disclaimer lokalisiert, Labor-Retention `lab_retention_months` (Default 0, voidet statt Archiv, ein Audit `lab_values_retention`), `lab_values.csv` inkl. voideter Zeilen + `voided_at`/`void_reason` (Import: `skipped`), Beispiel-Dashboard `examples/dashboard-labs-card.yaml`. Kein neues Datenmodell (Store v5, `unique_id`s unverändert, Backup/Restore-Format unberührt; Backup-Options additiv). **Belege:** `pytest -q` → alle Tests grün (gemessene Testzahl als konkrete Zahl), E2E → alle vier neuen Tests grün (gemessene Zahl), ruff clean. **Kein Release/Tag in diesem Schritt.** |
```

- [ ] **Step 4: Verify no placeholder remains**

Run: `grep -n "eintragen\|2026-11-XX\|<N>\|<M>" docs/REQUIREMENTS.md`
Expected: keine Ausgabe (das Abschlussdatum und beide Testzahlen sind vor dem Commit als
konkrete Werte eingetragen).

- [ ] **Step 5: Regression**

Run: `python3 -m pytest tests/test_dashboards.py tests/test_translations.py -q && ruff check .`
Expected: grün/clean (Doku ändert keinen Code).

- [ ] **Step 6: Commit**

```bash
git add README.md docs/REQUIREMENTS.md
git commit -m "docs: document lab report batch, undo and retention"
```

---

## Final Integration Check

- [ ] **Volle Unit-/JS-Suite:** `python3 -m pytest -q` — alle bestehenden Tests plus
  `test_req_hom_123_*`/`128_*`/`129_*`/`124_*`/`125_*`/`126_*` grün, keine Regression.
  Testzahl notieren (für Task 20).
- [ ] **CI-äquivalent ohne Home Assistant (Fake-HA-Pfad):**

  ```bash
  mkdir -p .tmp/venv-no-ha
  python3 -m venv .tmp/venv-no-ha
  . .tmp/venv-no-ha/bin/activate
  pip install -r tests/requirements.txt
  python3 -m pytest -q
  deactivate
  ```

  Expected: grün — beweist, dass die Suite auch ohne installiertes HA-Paket läuft
  (`tests/conftest.py` Fake-Paket).
- [ ] **Lint/Format:** `ruff check .` und `ruff format --check .` — clean
  (`line-length = 100`, `docs/` ausgenommen).
- [ ] **Compile-Check:** `python3 -m compileall -q custom_components/health_o_mat`.
- [ ] **E2E:** `cd tests_e2e && python3 -m pytest -q` gegen die geteilte Instanz
  (`/home/hermes/ha-test`): die vier neuen Tests grün; E2E-Zahl notieren. Die Fixture
  `restore_lab_options` stellt die Personen-Optionen (inkl. `lab_hide_panel_disclaimer`
  und `lab_hidden_categories`) wieder her; das temporäre Lovelace-Dashboard wird im
  `finally` gelöscht.
- [ ] **hassfest/HACS:** `.github/workflows/validate.yml` läuft bei Push/PR — keine neuen
  Fehler (`hacs/action` Kategorie `integration`, hassfest). Lokal optional:
  `/home/hermes/ha-test/bin/ha core check` nach
  `/home/hermes/ha-test/bin/sync /home/hermes/repos/ha-health-o-mat`.
- [ ] **Manuelle Prüfung der vier Punkte** auf der Dev-Instanz
  (`http://127.0.0.1:8123`):
  1. **Batch:** YAML-Beispiel aus §2.11 als Service → `lab_readings` wächst um 4 mit
     gemeinsamem `ts`/`report_ref`, genau ein Audit `lab_values_added`; derselbe Aufruf
     über `POST /api/services/health_o_mat/add_lab_report`; `add_lab_value` mit
     `NaN`/`inf` → `invalid_value`.
  2. **Dialog + Undo:** In Card **und** Panel zwei Zeilen speichern (Hybrid-Knöpfe,
     Einheiten-Dropdown), `ts`/`report_ref` bleiben nach Erfolg stehen; Duplikat →
     Fehlerbanner `Zeile 2 (…): duplicate_marker`, Eingaben bleiben; „Diesen Bericht
     verwerfen" fragt nach, voidet den Bericht, Aktion verschwindet nach Refresh;
     `restore_entry` holt einen Wert zurück.
  3. **Disclaimer/Admin:** frischer Lab-Tab (ohne Settings-Load) zeigt den Hinweis;
     Admin-Checkbox blendet ihn aus/ein; alle Kategorien ausgeblendet → Hinweis +
     „Alle Kategorien ausgeblendet"; Katalog-Tabelle zeigt `mg/dL × 88,4 → µmol/L`
     (DE) bzw. `88.4` (EN) und „Einheit Pflicht"; Karten-Disclaimer folgt der
     HA-Sprache.
  4. **Retention/Export/Beispiel:** `lab_retention_months = 12` beim Setup → alte aktive
     Werte sind voided (`retention`), ein Audit `lab_values_retention`, Getränke/BD
     unberührt; `lab_values.csv` enthält die voideten Zeilen mit `voided_at`/
     `void_reason`, `drinks.csv` unverändert; Re-Import zählt sie als `skipped`;
     `examples/dashboard-labs-card.yaml` rendert beide Ansichten.
- [ ] **Doku-Check:** README listet `examples/dashboard-labs-card.yaml`; die REQ-Kapitel
  123/124/125/126/128/129 sind `[x]` mit Belegen; 127 ist unverändert offen; Abschlussdatum
  und beide Testzahlen sind konkret eingetragen (`grep` aus Task 20 Step 4).
- [ ] **Kein Release in diesem Plan:** Version-Bump (`manifest.json` + alle
  `?v=`-Cache-Buster), Tag `v0.16.2` und GitHub-Release (Release-Dreiklang) sind **nicht**
  Teil dieses Plans. Sie laufen als eigener, nachgelagerter Schritt über den
  `release`-Agenten, sobald der Branch nach `main` gemerged ist
  (`.claude/rules/integration-development.md`, Schritte 6–7). Bis dahin bleibt
  `manifest.version` auf `0.16.1`.

---

*(End of plan.)*




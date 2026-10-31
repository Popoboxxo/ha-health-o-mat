# Laborwerte — Batch-Erfassung & Sichtbarkeit: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task.
> Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Vier Lücken der Laborwerte-Domäne schließen: (1) einen Laborbericht als **einen**
Vorgang erfassen (`add_lab_report` als Service + WS-Kommando + Mehrzeilen-Dialog in Card und
Panel, Alles-oder-nichts, ein Store-Write/ein Refresh/ein Audit-Eintrag), (2) die
Umrechnungsfaktoren der Katalog-Marker im Admin sichtbar machen, (3) den Medizin-Hinweis
kontextbezogen in den Panel-Lab-Tab bringen und (4) ein Beispiel-Dashboard für die
Labs-Card liefern — ohne neues Datenmodell, ohne `unique_id`-Änderung, ohne Store-Schema-Bump.

**Architecture:** Bleibt 1:1 in der bestehenden Per-Person-Config-Entry-Architektur. Der
Batch ist **nur eine andere Schreibweise** über der bestehenden `lab_readings[]`-Liste
(Store-Schema bleibt **v5**): ein neuer HA-freier Validator
(`logic.validate_lab_report_rows`) filtert Leerzeilen, löst Marker auf (Alias → Katalog →
Custom), konvertiert Einheiten und prüft Duplikate; ein neuer Store-Writer
(`store.add_lab_readings`) schreibt **einmal** mit Listen-Snapshot-Rollback; Service
(`__init__.py`) und WS-Kommando (`ws_api.py`) rufen denselben Validator, keiner den anderen.
Card und Panel bekommen je **eine** lokale Dialog-Implementierung (bewusst kein
Shared-Modul, Parität per Test). Admin-Umrechnungen und Panel-Disclaimer sind reine
Frontend-Änderungen auf bereits vorhandenen Server-Payloads (`settings.lab_catalog`,
`panel_data`); das Beispiel-Dashboard referenziert keine Entities.

**Tech Stack:** Python 3.13 (Home Assistant Custom Component, bestehende Konventionen),
vanilla JS (kein Framework, ES-Module für das Panel, klassisches Script für die Karte),
pytest mit der Fake-HA-Technik aus `tests/conftest.py`, voluptuous für Service-/WS-Schemata.

**Spec:** `docs/superpowers/specs/2026-11-01-lab-values-batch-and-visibility-design.md`
(approved, 838 Zeilen). Dieser Plan setzt §1–§14 um; §14.1 (Editor-Darstellung des
`object`-Selectors) ist ein Umsetzungs-Hinweis, kein Blocker — YAML- und REST-Aufruf sind
davon unabhängig. Ergänzende Domänen-Spec: `docs/superpowers/specs/2026-10-30-lab-values-design.md`.

**Branch:** Ein einziger Feature-Branch **`feat/lab-batch-visibility`**, von aktuellem
`main` (`7738d07`, Release 0.16.1) abgezweigt, gemäß `.claude/rules/branch-guard.md`
(keine direkten Commits auf `main`). Git-Mutationen (Branch, Commit, Push) laufen über den
`git`-Agenten; die Commit-Zeilen unten sind die exakten Befehle/Nachrichten für ihn.

**Pre-flight (vor dem Branch, vom `git`-Agenten):** Im lokalen Klon kann `main` hinter
`origin/main` (`7738d07`, Merge PR #56 aus `chore/release-0.16.1`) zurückliegen — erst
aktualisieren. Der Arbeitsbaum enthält die bereits freigegebene Spec plus die
REQUIREMENTS-Ergänzung als uncommittete Änderungen; diese gehören als Basis in `main`,
sonst wandert die Spec in den Feature-Branch:

```bash
git fetch origin
git switch main
git pull --ff-only
git add docs/REQUIREMENTS.md docs/superpowers/specs/2026-11-01-lab-values-batch-and-visibility-design.md
git commit -m "docs: specify lab report batch capture and visibility"
git switch -c feat/lab-batch-visibility
```

## Global Constraints

- Commit messages: Conventional Commits, English, imperative, first line ≤ 72 chars
  (`.claude/rules/commit-conventions.md`). Jeder Commit-Schritt unten nennt die exakte
  Nachricht; kein Commit enthält eine führende UTF-8-BOM.
- `from __future__ import annotations` + vollständige Type-Hints in jeder neuen/berührten
  Python-Datei (Projektkonvention).
- **`unique_id`s bleiben unverändert.** Dieser Plan legt keine Entity an, benennt keine um
  und ändert kein `device_info`. `{entry_id}_{key}` ist und bleibt der einzige Schlüssel.
- **Ein Store-Write pro Bericht:** `_async_save()` wird im Batch-Pfad genau einmal
  aufgerufen (Test: Call-Count 1), bei Fehler greift der Rollback (§2.7 der Spec). Es gibt
  keinen zweiten Persistenzpunkt.
- **`ServiceValidationError`** für Service-Fehler, `connection.send_error(..., 
  ERR_INVALID_FORMAT, "<code>…")` für WS-Fehler — die bestehenden Pfade, kein neues
  Fehlerformat. Meldungsformat exakt `"<code>"` bzw. `"<code>: Zeile <n> (<detail>)"`.
- **Kein neues Datenmodell:** `STORE_SCHEMA_VERSION` bleibt **5**; `lab_readings[]` behält
  `{id, ts, marker_key, value, unit, reported_value, reported_unit, report_ref, created_at,
  voided_at, voided_by, void_reason}`. `report_ref` bleibt ein freier, gekappter Tag
  (`LAB_REPORT_REF_MAX_LEN = 500`) — kein `LabReport`-Aggregat, keine neue Entität.
- **Backup/Restore/CSV bleiben unberührt** (`backup.py`, `restore.py`, `exporter.py`,
  `importer.py` werden in diesem Plan nicht angefasst). `REQ-HOM-123` schreibt
  ausschließlich in die bestehende Liste.
- **YAGNI:** kein `alt_units`/`require_explicit_unit` im `panel_data`-Payload (§6.2 der
  Spec), kein UI-Toggle für den Panel-Disclaimer (§8), kein Service-Response
  (`SupportsResponse`), kein neuer HTTP-Endpunkt, keine Shared-JS-Bibliothek für den
  Dialog (§6.3).
- Tests: `pytest -q` und `ruff check .` / `ruff format --check .` sind nach **jedem** Task
  grün. Neue Tests tragen das Muster `test_req_hom_123_*` / `test_req_hom_124_*` /
  `test_req_hom_125_*` / `test_req_hom_126_*` (bestehende Konvention).
- Sprache: Plan/README/Doku deutsch, Code, Kommentare, Commit-Messages und Testnamen
  englisch (Projektregel).

## Wellen- und Task-Übersicht

| Wave | REQ | Tasks | Schwerpunkt |
|---|---|---|---|
| 1 | REQ-HOM-123 | 1–7 | Batch: Validator, Store, Service + i18n, WS, Card-Dialog, Panel-Dialog |
| 2 | REQ-HOM-125 | 8 | Panel-Disclaimer (Frontend + i18n) |
| 3 | REQ-HOM-124 | 9 | Admin-Umrechnungsspalte + Badge + Locale |
| 4 | REQ-HOM-126 | 10 | Beispiel-Dashboard + `test_dashboards.py` |
| 5 | — | 11–12 | E2E-Erweiterung, Doku/REQUIREMENTS |

**Reihenfolge ist verbindlich** (Spec §11: 123 → 125 → 124 → 126). Innerhalb von Wave 1
sind Tasks 1 → 2 → 3 → 4 → 5 → 6 → 7 sequenziell; Details siehe
„Dependency- & Parallelisierungs-Hinweise".

---

## Wave 1 — REQ-HOM-123: Batch-Check-in eines Laborberichts

### Task 1: `logic.py` — `coerce_lab_number` + `validate_lab_report_rows`

**Files:**
- Modify: `custom_components/health_o_mat/logic.py`
- Test: `tests/test_logic.py`

**Interfaces:**
- Consumes: `resolve_lab_marker(raw_key, custom_markers) -> tuple[str, dict] | None`
  (`logic.py:1076`), `convert_lab_value(marker_def, value, unit) -> tuple[float, str]`
  (`logic.py:1091`, wirft `ValueError("unsupported_unit")`), `Mapping` (bereits importiert),
  `math` (neuer Import).
- Produces:
  - `LAB_REPORT_MAX_ROWS: int = 200` (Server-Limit, §2.4)
  - `coerce_lab_number(value: Any) -> float | None` — `None` bei `bool`, Nicht-Zahl,
    `NaN`/`±inf`
  - `_lab_row_is_empty(row: Mapping[str, Any]) -> bool`
  - `validate_lab_report_rows(values: Any, custom_markers: Any = None) -> tuple[list[dict], str | None]`
    — Zeilenform `{marker_key, value, unit, reported_value, reported_unit}`; Fehler als
    `"<code>"` / `"<code>: Zeile <n> (<detail>)"`, erster Fehler gewinnt.
- Verbraucher: Task 2 (nur indirekt), Task 4 (Service), Task 5 (WS), Task 9 der
  Vorgänger-Spec (`add_lab_value`-Härtung in Task 4/5).

**Spec-Bezug:** §2.3 (Zeilenform/Leerzeilen), §2.4 (Reihenfolge/Fehlercodes),
§12 (HA-freie Logiktests). `invalid_ts` und Personenauflösung sind **nicht** Teil dieser
Funktion (§2.3).

- [ ] **Step 1: Write the failing tests** (ans Ende von `tests/test_logic.py` anhängen)

```python
# --- REQ-HOM-123: Laborbericht-Batch (HA-frei) ------------------------------


def test_req_hom_123_coerce_lab_number_rejects_bool_nan_inf_and_non_numbers():
    from custom_components.health_o_mat import logic

    assert logic.coerce_lab_number(32) == 32.0
    assert logic.coerce_lab_number("32.5") == 32.5
    assert logic.coerce_lab_number(0) == 0.0
    for rejected in (True, False, float("nan"), float("inf"), float("-inf"), "abc", None):
        assert logic.coerce_lab_number(rejected) is None, rejected


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
    # Fehlende Einheit = kanonische Einheit (auch als reported_unit).
    assert rows[1]["reported_unit"] == "mIU/L"


def test_req_hom_123_validate_rows_resolves_alias_and_custom_marker():
    from custom_components.health_o_mat import logic

    custom = [
        {"key": "vitamin_d", "name": "Vitamin D", "category": "other", "unit": "ng/mL"}
    ]
    rows, error = logic.validate_lab_report_rows(
        [
            {"marker": "gpt", "value": 32},
            {"marker": "vitamin_d", "value": 42},
        ],
        custom,
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

    assert logic.validate_lab_report_rows([{}, {"marker": " ", "value": " "}]) == (
        [],
        "empty_report",
    )
    assert logic.validate_lab_report_rows(None) == ([], "empty_report")
    assert logic.validate_lab_report_rows([]) == ([], "empty_report")


def test_req_hom_123_validate_rows_rejects_more_than_200_filled_rows():
    from custom_components.health_o_mat import logic

    values = [{"marker": "alt", "value": index} for index in range(201)]

    assert logic.validate_lab_report_rows(values) == ([], "too_many_rows")


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


def test_req_hom_123_validate_rows_reports_unknown_marker_with_line():
    from custom_components.health_o_mat import logic

    rows, error = logic.validate_lab_report_rows(
        [{"marker": "alt", "value": 32}, {"marker": "gptx", "value": 1}]
    )

    assert rows == []
    assert error == "unknown_marker: Zeile 2 (gptx)"


def test_req_hom_123_validate_rows_requires_explicit_unit():
    from custom_components.health_o_mat import logic

    rows, error = logic.validate_lab_report_rows(
        [{"marker": "urine_protein_creatinine_ratio", "value": 10}]
    )

    assert rows == []
    assert error == "unit_required: Zeile 1 (urine_protein_creatinine_ratio)"


def test_req_hom_123_validate_rows_reports_invalid_value_before_unsupported_unit():
    from custom_components.health_o_mat import logic

    # `convert_lab_value` würde bei "abc" ebenfalls ValueError werfen; die
    # Zahlenprüfung steht davor (§2.4), damit `unsupported_unit` exakt der
    # Einheiten-Fall bleibt.
    rows, error = logic.validate_lab_report_rows(
        [{"marker": "alt", "value": "abc", "unit": "mg/dL"}]
    )

    assert rows == []
    assert error == "invalid_value: Zeile 1 (alt)"


def test_req_hom_123_validate_rows_rejects_bool_and_nan_values():
    from custom_components.health_o_mat import logic

    assert logic.validate_lab_report_rows([{"marker": "alt", "value": True}]) == (
        [],
        "invalid_value: Zeile 1 (alt)",
    )
    assert logic.validate_lab_report_rows(
        [{"marker": "alt", "value": float("nan")}]
    ) == ([], "invalid_value: Zeile 1 (alt)")


def test_req_hom_123_validate_rows_reports_unsupported_unit():
    from custom_components.health_o_mat import logic

    rows, error = logic.validate_lab_report_rows(
        [{"marker": "alt", "value": 32, "unit": "mg/dL"}]
    )

    assert rows == []
    assert error == "unsupported_unit: Zeile 1 (alt)"


def test_req_hom_123_validate_rows_reports_alias_duplicate_on_second_row():
    from custom_components.health_o_mat import logic

    rows, error = logic.validate_lab_report_rows(
        [{"marker": "alt", "value": 32}, {"marker": "gpt", "value": 30}]
    )

    assert rows == []
    assert error == "duplicate_marker: Zeile 2 (alt)"


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
    assert error == "unknown_marker: Zeile 3 (gptx)"


def test_req_hom_123_validate_rows_line_numbers_count_original_rows():
    from custom_components.health_o_mat import logic

    rows, error = logic.validate_lab_report_rows(
        [{}, {"marker": "alt", "value": 32}, {"marker": "gptx", "value": 1}]
    )

    assert rows == []
    assert error == "unknown_marker: Zeile 3 (gptx)"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_logic.py -k req_hom_123 -q`
Expected: FAIL — `AttributeError: module 'custom_components.health_o_mat.logic' has no
attribute 'coerce_lab_number'` (bzw. `validate_lab_report_rows`).

- [ ] **Step 3: Implement** — `import math` ergänzen und die Funktionen nach
  `convert_lab_value` (`logic.py:1108`) einfügen

Import-Block (alphabetisch, ruff-isort-konform):

```python
import calendar
import csv
import io
import math
import re
import unicodedata
```

```python
# --- Laborbericht-Batch (REQ-HOM-123) ---------------------------------------

# Server-Limit je Bericht (§2.4). Unabhängig von der UI-Grenze (60 Zeilen).
LAB_REPORT_MAX_ROWS = 200


def coerce_lab_number(value: Any) -> float | None:
    """Messwert zu ``float`` — ``None`` bei bool, Nicht-Zahl, NaN/±inf (§2.4).

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
) -> tuple[list[dict], str | None]:
    """Leerzeilen filtern, Zeilen validieren, in kanonische Einheiten konvertieren.

    Rückgabe: (konvertierte Zeilen, Fehlermeldung oder None). Die Fehlermeldung
    ist bereits im Vertragsformat "<code>" bzw. "<code>: Zeile <n> (<detail>)"
    (§2.4) — der Aufrufer reicht sie nur noch weiter.
    """
    if isinstance(values, Mapping):
        values = [values]
    if not isinstance(values, list):
        return [], "empty_report"

    # Der Originalindex bleibt die Zeilennummer in der Meldung (die UI zeigt
    # genau diese Zeilen); gezählt/grenzgeprüft werden nur befüllte Zeilen.
    filled = [
        (index, row)
        for index, row in enumerate(values, start=1)
        if isinstance(row, Mapping) and not _lab_row_is_empty(row)
    ]
    if not filled:
        return [], "empty_report"
    if len(filled) > LAB_REPORT_MAX_ROWS:
        return [], "too_many_rows"

    converted: list[dict] = []
    for index, row in filled:
        raw_marker = str(row.get("marker") or "").strip()
        resolved = resolve_lab_marker(raw_marker, custom_markers) if raw_marker else None
        if resolved is None:
            return [], f"unknown_marker: Zeile {index} ({raw_marker})"
        marker_key, marker_def = resolved
        raw_unit = row.get("unit")
        unit = str(raw_unit).strip() if raw_unit is not None else ""
        if not unit and marker_def.get("require_explicit_unit"):
            return [], f"unit_required: Zeile {index} ({marker_key})"
        # Zahlenprüfung VOR der Einheitenprüfung: `convert_lab_value` beginnt mit
        # `float(value)` und würde "abc" sonst als `unsupported_unit` melden.
        reported_value = coerce_lab_number(row.get("value"))
        if reported_value is None:
            return [], f"invalid_value: Zeile {index} ({marker_key})"
        try:
            canonical_value, canonical_unit = convert_lab_value(
                marker_def, reported_value, unit or None
            )
        except ValueError:
            return [], f"unsupported_unit: Zeile {index} ({marker_key})"
        converted.append(
            {
                "marker_key": marker_key,
                "value": canonical_value,
                "unit": canonical_unit,
                "reported_value": reported_value,
                "reported_unit": unit or canonical_unit,
            }
        )

    # Duplikate erst nach der Zeilenvalidierung (§2.4: Schritt 4 vor Schritt 5) —
    # ein Zeilenfehler weiter unten gewinnt gegen ein Duplikat weiter oben.
    seen: set[str] = set()
    for position, (index, _row) in enumerate(filled):
        marker_key = converted[position]["marker_key"]
        if marker_key in seen:
            return [], f"duplicate_marker: Zeile {index} ({marker_key})"
        seen.add(marker_key)
    return converted, None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_logic.py -k req_hom_123 -q`
Expected: all PASS.

- [ ] **Step 5: Regression**

Run: `python3 -m pytest tests/test_logic.py -q && ruff check custom_components/health_o_mat/logic.py tests/test_logic.py && ruff format --check custom_components/health_o_mat/logic.py tests/test_logic.py`
Expected: bestehende Logiktests grün, ruff clean.

- [ ] **Step 6: Commit**

```bash
git add custom_components/health_o_mat/logic.py tests/test_logic.py
git commit -m "feat: add lab report row validation to logic"
```

---

### Task 2: `store.py` — `add_lab_readings` (ein Save, ein Audit, Rollback)

**Files:**
- Modify: `custom_components/health_o_mat/store.py`
- Test: `tests/test_store.py`

**Interfaces:**
- Consumes: `self.entry(...)`, `self._append_audit(...)` (`store.py:334`, wendet den
  Audit-Cap an), `self._async_save()` (`store.py:1007`), `_now_iso()`,
  `DEFAULT_AUDIT_LIMIT`, `uuid`.
- Produces: `HealthOMatStore.add_lab_readings(entry_id: str, ts_iso: str, rows: list[dict],
  report_ref: str | None = None, created_ts_iso: str | None = None, actor: str | None =
  None, audit_limit: int = DEFAULT_AUDIT_LIMIT) -> list[str]`
  (Rückgabe: geschriebene Reading-IDs) — verbraucht von Task 4 (Service) und Task 5 (WS).
  `add_lab_reading` (Singular) bleibt unverändert für den Einzelpfad.

**Spec-Bezug:** §2.7 (Store-API + Rollback), §2.8 (ein Audit-Eintrag, Datenminimierung),
§12 (Store-Tests inkl. Rollback mit gekapptem Ring).

- [ ] **Step 1: Write the failing tests** (ans Ende von `tests/test_store.py` anhängen;
  `mock_store_fixture`, `_async_test` und `pytest` sind dort bereits vorhanden)

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
    rows = _lab_rows(2)

    ids = _async_test(
        store.add_lab_readings(
            "e1",
            "2026-11-01T09:15:00+01:00",
            rows,
            report_ref="https://example.com/1",
            created_ts_iso="2026-11-01T10:00:00+01:00",
        )
    )

    readings = store.entry("e1")["lab_readings"]
    assert [reading["marker_key"] for reading in readings] == ["marker_0", "marker_1"]
    assert all(reading["ts"] == "2026-11-01T09:15:00+01:00" for reading in readings)
    assert all(reading["report_ref"] == "https://example.com/1" for reading in readings)
    assert all(reading["voided_at"] is None for reading in readings)
    assert len(ids) == 2
    assert {reading["id"] for reading in readings} == set(ids)
    mock_save.async_save.assert_awaited_once()


def test_req_hom_123_add_lab_readings_writes_one_privacy_safe_audit_entry(mock_store_fixture):
    store, _mock_save = mock_store_fixture
    rows = _lab_rows(2)

    ids = _async_test(
        store.add_lab_readings(
            "e1", "2026-11-01T09:15:00+01:00", rows, report_ref="Labor 10/2026"
        )
    )

    audit = store.entry("e1")["audit_log"]
    assert len(audit) == 1
    event = audit[0]
    assert event["action"] == "lab_values_added"
    assert event["kind"] == "lab_readings"
    assert event["target_id"] is None
    assert event["details"] == {
        "count": 2,
        "marker_keys": ["marker_0", "marker_1"],
        "reading_ids": ids,
    }
    assert "report_ref" not in event["details"]
    assert "Labor 10/2026" not in repr(event)


def test_req_hom_123_add_lab_readings_caps_id_lists_at_20(mock_store_fixture):
    store, _mock_save = mock_store_fixture
    rows = _lab_rows(25)

    ids = _async_test(store.add_lab_readings("e1", "2026-11-01T09:15:00+01:00", rows))

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
    # `audit_pruned`-Summary). Ein Slice-Rollback würde die gekappten Einträge
    # NICHT wiederherstellen — der Test pinnt den Listen-Snapshot (§2.7).
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


def test_req_hom_123_add_lab_readings_reraises_after_rollback(mock_store_fixture, monkeypatch):
    store, mock_save = mock_store_fixture
    calls: list[int] = []

    async def _fail_save() -> None:
        calls.append(1)
        raise ValueError("boom")

    monkeypatch.setattr(store, "_async_save", _fail_save)

    with pytest.raises(ValueError, match="boom"):
        _async_test(store.add_lab_readings("e1", "2026-11-01T09:15:00+01:00", _lab_rows(3)))

    assert calls == [1]
    assert store.entry("e1")["lab_readings"] == []
    assert store.entry("e1")["audit_log"] == []
    mock_save.async_save.assert_not_awaited()
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
        """Mehrere Laborwerte eines Berichts als EIN Vorgang schreiben (§2.7).

        ``rows`` sind bereits validierte, kanonisch konvertierte Zeilen
        (``{marker_key, value, unit, reported_value, reported_unit}``). Es gibt
        genau einen Save und genau einen Audit-Eintrag; schlägt der Save fehl,
        wird der In-Memory-Zustand exakt auf den Vorzustand zurückgesetzt und
        der Fehler weitergereicht ("Alles-oder-nichts" auch für die Persistenz).
        """
        created = created_ts_iso or _now_iso()
        entry = self.entry(entry_id)
        # Vollständige Listenkopien (kein Slice): `_append_audit` kappt den Ring,
        # ein Slice-Rollback ließe gekappte Alt-Einträge verloren.
        readings_before = list(entry.get("lab_readings") or [])
        audit_before = list(entry.get("audit_log") or [])
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

Run: `python3 -m pytest tests/test_store.py -q && python3 -m pytest tests/test_import_backup.py tests/test_restore.py -q && ruff check custom_components/health_o_mat/store.py tests/test_store.py`
Expected: alles grün; Backup/Restore unberührt (nur additive Methode).

- [ ] **Step 6: Commit**

```bash
git add custom_components/health_o_mat/store.py tests/test_store.py
git commit -m "feat: add atomic lab report batch writer to store"
```

---

### Task 3: `services.yaml` + Service-i18n — `add_lab_report`-Metadaten + Marker-Mirror-Test

**Files:**
- Modify: `custom_components/health_o_mat/services.yaml`
- Modify: `custom_components/health_o_mat/strings.json`
- Modify: `custom_components/health_o_mat/translations/de.json`
- Modify: `custom_components/health_o_mat/translations/en.json`
- Test: `tests/test_translations.py`, `tests/test_lab_services.py`

**Interfaces:**
- Consumes: nichts aus dem Code (reine Deklaration); der 29er-Optionssatz ist
  1:1 aus `add_lab_value` (`services.yaml:337-405`).
- Produces: Service-Block `add_lab_report` in `services.yaml` (Felder `person`, `values`,
  `ts`, `report_ref`; `values` = `object`-Selector mit `multiple: true`,
  `label_field: marker` und drei Unterfeldern) + `services.add_lab_report` in allen drei
  i18n-Dateien (Name, Description, Felder `values`/`ts`/`report_ref`).
- Der Handler folgt in Task 4; dieser Task ist reine Metadaten-/Paritätsarbeit
  (Tests in `tests/test_translations.py` laufen ohne HA-Import).

**Spec-Bezug:** §2.2 (Feldtabelle + YAML-Block), §2.11 (Nicht-Idempotenz in der
Description), §11 (i18n-Zeile), §12 (Service-Schema-Mirror).

- [ ] **Step 1: Write the failing tests**

(a) In `tests/test_translations.py` die beiden Labor-Dicts erweitern
(`tests/test_translations.py:392-403`):

```python
_LAB_SERVICE_FIELDS = {
    "add_lab_value": {"person", "marker", "value", "unit", "ts", "report_ref"},
    "add_lab_report": {"person", "values", "ts", "report_ref"},
    "remove_last_lab_value": {"person", "marker"},
}

# Minimal-Override-Konvention (wie `add_blood_pressure`): in den JSON-Dateien
# stehen nur die Felder, deren Text übersetzt wird — nicht zwingend alle
# Felder aus `services.yaml`.
_LAB_TRANSLATED_FIELDS = {
    "add_lab_value": {"marker", "unit", "ts", "report_ref"},
    "add_lab_report": {"values", "ts", "report_ref"},
    "remove_last_lab_value": {"marker"},
}
```

(b) In `tests/test_lab_services.py` `import yaml` ergänzen und ans Dateiende den
Mirror-Test anhängen:

```python
# ---------------------------------------------------------------------------
# Service-Schema-Mirror (REQ-HOM-123)
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_translations.py -k "lab_services_have_translation_parity" tests/test_lab_services.py -k "req_hom_123" -q`
Expected: FAIL — `AssertionError: services.yaml: add_lab_report fehlt` und
`KeyError: 'add_lab_report'` im Mirror-Test.

- [ ] **Step 3: Implement** — `services.yaml`-Block direkt nach `add_lab_value`
  (vor `remove_last_lab_value`) einfügen

```yaml
add_lab_report:
  name: Laborbericht erfassen
  description: >-
    Erfasst mehrere Laborwerte eines Berichts in einem Vorgang — gleicher
    Zeitpunkt, gleiche Berichts-Referenz, Alles-oder-nichts: eine ungültige
    Zeile lehnt den gesamten Bericht ab. Leere Zeilen werden ignoriert. Ein
    erneuter Aufruf schreibt die Werte erneut (kein Dedupe).
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

- [ ] **Step 4: Implement i18n** — `services.add_lab_report` in allen drei Dateien
  (Schlüssel exakt `name`, `description`, `fields.{values,ts,report_ref}.{name,description}`;
  `person` bleibt wie bei `add_lab_value` unübersetzt)

`custom_components/health_o_mat/strings.json` (`services`-Objekt, direkt nach
`add_lab_value` und vor `remove_last_lab_value`):

```json
"add_lab_report": {
  "name": "Record lab report",
  "description": "Records several lab values of one report in a single operation — same timestamp, same report reference, all-or-nothing: one invalid row rejects the whole report. Empty rows are ignored. Calling it again writes the values again (no dedupe).",
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
}
```

`translations/de.json`:

```json
"add_lab_report": {
  "name": "Laborbericht erfassen",
  "description": "Erfasst mehrere Laborwerte eines Berichts in einem Vorgang — gleicher Zeitpunkt, gleiche Berichts-Referenz, Alles-oder-nichts: eine ungültige Zeile lehnt den gesamten Bericht ab. Leere Zeilen werden ignoriert. Ein erneuter Aufruf schreibt die Werte erneut (kein Dedupe).",
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
}
```

`translations/en.json`: identisch zu `strings.json` (Master ist englisch; die
Paritätstests vergleichen Schlüsselbäume, nicht Werte).

- [ ] **Step 5: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_translations.py -q && python3 -m pytest tests/test_lab_services.py -k req_hom_123 -q`
Expected: alle PASS (inkl. bestehendem `test_req_hom_122_lab_services_have_translation_parity`).

- [ ] **Step 6: Regression**

Run: `python3 -m pytest tests/test_translations.py tests/test_lab_services.py tests/test_ws_api.py -q && ruff check . && ruff format --check .`
Expected: grün/clean. (Der Handler fehlt noch — `_register_services` registriert den Service
erst in Task 4; die Schema-/Mirror-Tests dieses Tasks brauchen ihn nicht.)

- [ ] **Step 7: Commit**

```bash
git add custom_components/health_o_mat/services.yaml custom_components/health_o_mat/strings.json custom_components/health_o_mat/translations/de.json custom_components/health_o_mat/translations/en.json tests/test_translations.py tests/test_lab_services.py
git commit -m "feat: declare add_lab_report service and translations"
```

---

### Task 4: `__init__.py` — Service-Handler `add_lab_report` + `add_lab_value`-Härtung

**Files:**
- Modify: `custom_components/health_o_mat/__init__.py`
- Test: `tests/test_lab_services.py`

**Interfaces:**
- Consumes: `logic.validate_lab_report_rows` / `logic.coerce_lab_number` (Task 1),
  `store.add_lab_readings` (Task 2), `get_runtime_data` (`__init__.py:485`),
  `_service_entry_ts` (`__init__.py:592`), `_entry_options` (`__init__.py:583`),
  `_entry_audit_limit`, `_service_actor`, `signal_refresh`, `LAB_REPORT_REF_MAX_LEN`,
  `OPTION_LAB_CUSTOM_MARKERS`, neu `homeassistant.helpers.config_validation as cv`.
- Produces: registrierter Service `health_o_mat.add_lab_report` (Schema mit
  `values`-Liste, Zeilenfelder `vol.Optional`), Eintrag `"add_lab_report"` in
  `_SERVICE_NAMES` (`__init__.py:73-87`); gehärteter `add_lab_value`-Handler
  (`invalid_value` statt `float()`-Exception bei `NaN`/`inf`).

**Spec-Bezug:** §2.2 (Voluptuous), §2.4 (Reihenfolge: Person → `invalid_ts` →
`empty_report`/`too_many_rows`/Zeilen), §2.6 (kein Rückgabewert), §2.9 (`report_ref`-Cap),
§12 (Service-Tests).

- [ ] **Step 1: Write the failing tests** (ans Ende von `tests/test_lab_services.py`;
  `_wire_services`, `_wire_services_and_schemas`, `_make_call`, `_run` existieren bereits)

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
    rows = args[2]
    assert [row["marker_key"] for row in rows] == ["alt", "creatinine"]
    assert rows[1]["unit"] == "µmol/L"
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

    with pytest.raises(ServiceValidationError, match=r"unknown_marker: Zeile 3 \(gptx\)"):
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
    """Ein unbekannter Entry meldet den Entry-Fehler, nicht `invalid_ts` (§2.4)."""
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
Expected: FAIL — `KeyError: 'add_lab_report'` (Service nicht registriert); der
`NaN`-Test scheitert mit einer `float`-bzw. `ServiceValidationError`-Meldung, die nicht
`invalid_value` enthält.

- [ ] **Step 3: Implement**

(a) Import ergänzen (alphabetisch vor `update_coordinator`):

```python
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
```

(b) `_SERVICE_NAMES` (`__init__.py:73-87`) um `"add_lab_report"` erweitern (nach
`"add_lab_value"`).

(c) Handler direkt nach `add_lab_value` (`__init__.py:783`) einfügen:

```python
    async def add_lab_report(call: ServiceCall) -> None:
        """Laborbericht (mehrere Werte) als EINEN Vorgang erfassen (REQ-HOM-123).

        Reihenfolge ist Vertrag (§2.4): Person → Zeitpunkt → Zeilen. Eine
        ungültige Zeile lehnt den gesamten Bericht ab; es wird nichts
        geschrieben. Leere Zeilen werden ignoriert.
        """
        entry_id, _info = get_runtime_data(hass, call)
        options = _entry_options(hass, entry_id)
        now = dt_util.now()
        try:
            ts_iso = _service_entry_ts(call, now) or now.isoformat()
        except ServiceValidationError as err:
            # Code-Präfix ist Batch-Aufrufer-Sache; die Prosa aus
            # `ENTRY_TS_INVALID_MESSAGE` bleibt unverändert (§2.4).
            raise ServiceValidationError(f"invalid_ts: {err}") from err
        rows, error = logic.validate_lab_report_rows(
            call.data.get("values"), options.get(OPTION_LAB_CUSTOM_MARKERS)
        )
        if error is not None:
            raise ServiceValidationError(error)
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

(e) Registrierung nach dem `add_lab_value`-Block (`__init__.py:1012`) einfügen:

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
                                # ein `{}`-Eintrag ist eine ignorierte Leerzeile —
                                # "Pflicht" ist eine Handler-Regel (§2.2).
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
Expected: grün/clean (bestehende `add_lab_value`-Tests bleiben unverändert grün).

- [ ] **Step 6: Commit**

```bash
git add custom_components/health_o_mat/__init__.py tests/test_lab_services.py
git commit -m "feat: add add_lab_report service handler"
```

---

### Task 5: `ws_api.py` — Kommando `health_o_mat/add_lab_report` + `invalid_ts`-Präfix + Zahlen-Härtung

**Files:**
- Modify: `custom_components/health_o_mat/ws_api.py`
- Test: `tests/test_ws_api.py`

**Interfaces:**
- Consumes: `logic.validate_lab_report_rows` (Task 1), `store.add_lab_readings` (Task 2),
  `_store`, `_runtime_entry`, `_entry_ready`, `_send_entry_error`, `parse_entry_ts`
  (`ws_api.py:806`), `_resolve_lab_marker_or_error`, `signal_refresh`, `user_id_of`,
  `_audit_limit`.
- Produces: `COMMAND_ADD_LAB_REPORT = "health_o_mat/add_lab_report"` (`ws_api.py:107`
  Nachbar), registriertes Kommando mit `values`-Listenschema, Handler
  `websocket_add_lab_report`; `send_result({"written": n, "ts": ts_iso})`; Fehler als
  `send_error(ERR_INVALID_FORMAT, "<code>…")`. Zusätzlich: der Einzelpfad
  `websocket_add_lab_value` nutzt `coerce_lab_number` (`invalid_value`).

**Spec-Bezug:** §3 (WS-Vertrag, `PREVENT_EXTRA`, `entry_id` Pflicht vor `invalid_ts`),
§2.6 (Antwortform), §2.4 (Härtung des Einzelpfads).

- [ ] **Step 1: Write the failing tests** (ans Ende von `tests/test_ws_api.py`)

```python
# --- REQ-HOM-123: WS-Batch ------------------------------------------------


def test_req_hom_123_websocket_add_lab_report_writes_and_returns_written(monkeypatch):
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
    assert connection.results == [(21, {"written": 2, "ts": "2026-10-14T09:15:00+02:00"})]
    store.add_lab_readings.assert_awaited_once()
    args, kwargs = store.add_lab_readings.call_args
    assert args[0] == "e1"
    assert args[1] == "2026-10-14T09:15:00+02:00"
    assert [row["marker_key"] for row in args[2]] == ["alt", "creatinine"]
    assert kwargs["report_ref"] == "Labor 10/2026"


def test_req_hom_123_websocket_add_lab_report_sends_line_error(monkeypatch):
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

    assert connection.results == []
    assert connection.errors == [
        (22, ws_api.ERR_INVALID_FORMAT, "unknown_marker: Zeile 2 (gptx)")
    ]
    store.add_lab_readings.assert_not_awaited()


def test_req_hom_123_websocket_add_lab_report_prefixes_invalid_ts(monkeypatch):
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

    assert connection.results == []
    assert len(connection.errors) == 1
    assert connection.errors[0][1] == ws_api.ERR_INVALID_FORMAT
    assert connection.errors[0][2].startswith("invalid_ts: ")
    store.add_lab_readings.assert_not_awaited()


def test_req_hom_123_websocket_add_lab_report_checks_entry_before_ts(monkeypatch):
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

    assert connection.errors[0][1] == ws_api.ERR_NOT_FOUND


def test_req_hom_123_websocket_add_lab_report_rejects_empty_report(monkeypatch):
    _now(monkeypatch)
    store = _write_store()
    hass = _write_hass(store, [_entry("e1")])
    connection = FakeConnection()

    asyncio.run(
        ws_api.websocket_add_lab_report(
            hass,
            connection,
            {
                "id": 25,
                "type": ws_api.COMMAND_ADD_LAB_REPORT,
                "entry_id": "e1",
                "values": [{}],
            },
        )
    )

    assert connection.errors == [(25, ws_api.ERR_INVALID_FORMAT, "empty_report")]


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
                "id": 26,
                "type": ws_api.COMMAND_ADD_LAB_VALUE,
                "entry_id": "e1",
                "marker": "alt",
                "value": float("nan"),
            },
        )
    )

    assert connection.errors == [(26, ws_api.ERR_INVALID_FORMAT, "invalid_value")]
    store.add_lab_reading.assert_not_awaited()


def test_req_hom_123_lab_report_command_schema_is_strict(monkeypatch):
    registered: list[tuple] = []
    hass = FakeHass()
    monkeypatch.setattr(
        ws_api.websocket_api,
        "async_register_command",
        lambda *args: registered.append(args),
    )

    asyncio.run(ws_api.async_register_ws_api(hass))

    schemas = {args[1]: args[3] for args in registered}
    schema = schemas[ws_api.COMMAND_ADD_LAB_REPORT]
    parsed = schema(
        {
            "id": 1,
            "type": ws_api.COMMAND_ADD_LAB_REPORT,
            "entry_id": "e1",
            "values": [{"marker": "alt", "value": "32.5"}, {}],
        }
    )
    # Kein Coerce im Schema: die Zahlprüfung passiert im Handler (§2.2).
    assert parsed["values"][0]["value"] == "32.5"
    assert parsed["values"][1] == {}

    with pytest.raises(vol.Invalid):
        schema(
            {
                "id": 2,
                "type": ws_api.COMMAND_ADD_LAB_REPORT,
                "entry_id": "e1",
                "values": [{"marker": "alt", "value": 1, "bogus": 2}],
            }
        )
    with pytest.raises(vol.Invalid):
        schema({"id": 3, "type": ws_api.COMMAND_ADD_LAB_REPORT, "values": []})
```

`_write_store()` (`tests/test_ws_api.py:197`) in derselben Änderung um
`store.add_lab_readings = AsyncMock()` ergänzen.

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_ws_api.py -k req_hom_123 -q`
Expected: FAIL — `AttributeError: module 'ws_api' has no attribute
'COMMAND_ADD_LAB_REPORT'` bzw. `websocket_add_lab_report`.

- [ ] **Step 3: Implement**

(a) Konstante nach `COMMAND_ADD_LAB_VALUE` (`ws_api.py:107`):

```python
COMMAND_ADD_LAB_REPORT = "health_o_mat/add_lab_report"
```

(b) Registrierungs-Tupel direkt nach dem `COMMAND_ADD_LAB_VALUE`-Eintrag
(`ws_api.py:987`):

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
```

(c) Handler direkt nach `websocket_add_lab_value` (`ws_api.py:1365`) einfügen:

```python
async def websocket_add_lab_report(
    hass: HomeAssistant, connection: Any, msg: dict[str, Any]
) -> None:
    """`health_o_mat/add_lab_report` → Laborbericht als EINEN Vorgang (REQ-HOM-123).

    Reihenfolge wie beim Service (§2.4): Entry → Zeitpunkt → Zeilen. Fehler
    kommen als `send_error` mit Code-Prefix, damit die Karte/das Panel sie als
    Karten-Fehlermeldung zeigt (bestehendes Muster, `add_lab_value`).
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
    except ValueError as err:
        connection.send_error(msg["id"], ERR_INVALID_FORMAT, f"invalid_ts: {err}")
        return
    rows, error = logic.validate_lab_report_rows(
        msg.get("values"), options.get(OPTION_LAB_CUSTOM_MARKERS)
    )
    if error is not None:
        connection.send_error(msg["id"], ERR_INVALID_FORMAT, error)
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
    connection.send_result(msg["id"], {"written": len(rows), "ts": ts_iso})
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

Run: `python3 -m pytest tests/test_ws_api.py -k req_hom_123 -q`
Expected: all PASS (`test_req_hom_123_lab_report_command_schema_is_strict` eingeschlossen).

- [ ] **Step 5: Regression**

Run: `python3 -m pytest tests/test_ws_api.py tests/test_lab_services.py -q && ruff check custom_components/health_o_mat/ws_api.py tests/test_ws_api.py && ruff format --check custom_components/health_o_mat/ws_api.py tests/test_ws_api.py`
Expected: grün/clean.

- [ ] **Step 6: Commit**

```bash
git add custom_components/health_o_mat/ws_api.py tests/test_ws_api.py
git commit -m "feat: add add_lab_report websocket command"
```

---

### Task 6: `www/health-o-mat-labs-card.js` — Mehrzeilen-Dialog (Card)

**Files:**
- Modify: `custom_components/health_o_mat/www/health-o-mat-labs-card.js`
- Test: `tests/test_card_js.py`

**Interfaces:**
- Consumes (innerhalb der Datei): `_markers()`, `labMarkerOptionsHtml(markers, selectedKey)`,
  `escapeHtml`, `attrValue`? (die Karte hat kein `attrValue` — sie nutzt
  `escapeHtml` direkt), `TS_FUTURE_TOLERANCE_MS`, `_saving`, `_actionError`, `_render`,
  `_loadData(true)`, `this._hass.connection.sendMessagePromise`.
- Produces (dateiintern, keine Exporte — die Karte ist ein klassisches Script):
  `LAB_REPORT_MAX_ROWS_UI = 60`, `EMPTY_REPORT_ROW()`, `EMPTY_REPORT_DRAFT()`,
  `LAB_ERROR_TEXT`, `errorCode(text)`, `errorMessage(err)` (Prefix-Mapping),
  `_reportMarkerOptions()`, `_reportRow()`, `_reportForm()`,
  `_collectReportDraftFromDom()`, `_validateTs()`, `_readEntryTs()`, `_readReportTs()`,
  `_addReportRow()`, `_removeReportRow()`, `_onReportField()`, `_saveReport()`.
  State: `this._reportDraft = {ts, reportRef, rows: [{marker, value, unit}]}`.
- WS-Nachricht: `{type: "health_o_mat/add_lab_report", entry_id, values, ts?, report_ref?}`.

**Spec-Bezug:** §6.1 (Aufbau, Start = 1 Zeile, UI-Cap 60, Placeholder = kanonische
Einheit), §6.2 (Client prüft nur Bericht/Zeit/Wert), §6.4 (Single-Flight, Reset-Semantik:
Werte+Zeilen leeren, `ts`/`report_ref` behalten; Fehler behält alles),
§2.4 (Prefix-Mapping), §10 (Card-Disclaimer bleibt hartkodiert deutsch).

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


def test_req_hom_123_labs_card_has_report_dialog_and_state():
    source = _labs_card_source()

    assert "const LAB_REPORT_MAX_ROWS_UI = 60;" in source
    for name in (
        "_reportForm",
        "_collectReportDraftFromDom",
        "_addReportRow",
        "_removeReportRow",
        "_saveReport",
    ):
        assert re.search(rf"(?:async\s+)?{name}\s*\(", source), f"{name}() fehlt"
    assert "this._reportDraft = EMPTY_REPORT_DRAFT();" in source
    assert 'data-action="lab-report-add"' in source
    assert 'data-action="lab-report-remove"' in source
    assert 'data-action="lab-report-save"' in source
    assert "health_o_mat/add_lab_report" in source


def test_req_hom_123_labs_card_report_marker_has_placeholder_option():
    """Ohne Platzhalter würde eine leere Zeile den ersten Marker senden."""
    source = _labs_card_source()

    assert "_reportMarkerOptions(" in source
    assert 'placeholder = selectedKey' in source
    assert '<option value="" selected>' in source


def test_req_hom_123_labs_card_error_message_uses_code_prefix():
    source = _labs_card_source()

    for code in (
        "empty_report",
        "too_many_rows",
        "unknown_marker",
        "unit_required",
        "invalid_value",
        "unsupported_unit",
        "duplicate_marker",
        "invalid_ts",
    ):
        assert code in source, code
    assert "errorCode(" in source
    assert "text.slice(code.length)" in source


def test_req_hom_123_labs_card_report_is_single_flight():
    block = _js_method_text(_labs_card_source(), "_saveReport")

    assert "if (this._saving) return;" in block
    assert "this._saving = true;" in block
    assert "this._saving = false;" in block
    assert "disabled" in _labs_card_source()


@pytest.mark.skipif(shutil.which("node") is None, reason="node nicht verfügbar")
def test_req_hom_123_labs_card_report_reset_semantics(tmp_path):
    """Erfolg leert Werte+Zeilen und BEHÄLT ts/reportRef; Fehler behält alles."""
    outcomes = {}
    for outcome in ("ok", "fail"):
        outcomes[outcome] = json.loads(
            _run_node(
                tmp_path,
                _NODE_LABS_REPORT_RUNNER,
                [str(Path(_LABS_CARD_JS)), outcome],
                f"runner_labs_report_{outcome}",
            )
        )

    ok = outcomes["ok"]
    assert ok["payload"]["type"] == "health_o_mat/add_lab_report"
    assert ok["payload"]["values"] == [{"marker": "alt", "value": 32, "unit": "U/L"}]
    assert ok["draft"]["ts"] == "2026-10-30T09:15"
    assert ok["draft"]["reportRef"] == "Labor 10/2026"
    assert ok["draft"]["rows"] == [{"marker": "", "value": "", "unit": ""}]
    assert ok["error"] == ""
    assert ok["saving"] is False

    failed = outcomes["fail"]
    assert failed["error"].startswith("Unbekannter Marker.")
    assert "Zeile 1 (gptx)" in failed["error"]
    assert failed["draft"]["rows"] == [{"marker": "alt", "value": "32", "unit": "U/L"}]
    assert failed["draft"]["ts"] == "2026-10-30T09:15"
    assert failed["payload"]["values"] == [{"marker": "alt", "value": 32, "unit": "U/L"}]
```

Der Node-Runner kommt direkt über den Tests (die Karte ist ein klassisches Script, wird
also per `vm` geladen — wie `_NODE_LABS_CARD_I18N_RUNNER`):

```python
_NODE_LABS_REPORT_RUNNER = """import { readFileSync } from "node:fs";
import vm from "node:vm";

const source = readFileSync(process.argv[2], "utf8");
const outcome = process.argv[3];

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
    categories: [{ key: "liver", name: "Leber", hidden: false }],
    markers: {
      alt: {
        category: "liver", name: "ALT", name_de: "ALT", name_en: "ALT",
        unit: "U/L", value: null, history: [],
      },
    },
  },
};
card._reportDraft = {
  ts: "2026-10-30T09:15",
  reportRef: "Labor 10/2026",
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
      if (outcome === "fail") throw new Error("unknown_marker: Zeile 1 (gptx)");
      return { written: 1 };
    },
  },
};

await card._saveReport();
process.stdout.write(
  JSON.stringify({
    payload: sent[0],
    draft: card._reportDraft,
    error: card._actionError,
    saving: card._saving,
  })
);
"""
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_card_js.py -k req_hom_123 -q`
Expected: FAIL — `AssertionError` (kein `LAB_REPORT_MAX_ROWS_UI`, keine
`_reportForm`-Methode) bzw. `Node-Runner ... fehlgeschlagen` wegen fehlender
`_saveReport`-Methode.

- [ ] **Step 3: Implement** — Änderungen in `health-o-mat-labs-card.js`

(a) Nach `const TS_FUTURE_TOLERANCE_MS = 5 * 60 * 1000;` (`Zeile 31`):

```js
// UI-Soft-Cap des Bericht-Dialogs (Render-Schutz). Server-Limit bleibt 200 (§2.4).
const LAB_REPORT_MAX_ROWS_UI = 60;
```

(b) `EMPTY_DRAFT` (`Zeile 254`) um den Berichtsentwurf ergänzen:

```js
const EMPTY_DRAFT = () => ({ marker: "", value: "", unit: "", ts: "", reportRef: "" });

const EMPTY_REPORT_ROW = () => ({ marker: "", value: "", unit: "" });
const EMPTY_REPORT_DRAFT = () => ({
  ts: "",
  reportRef: "",
  rows: [EMPTY_REPORT_ROW()],
});
```

(c) `errorMessage()` (`Zeile 202-212`) vollständig ersetzen:

```js
/* Fehlercode-Tabelle des Laborbereichs. Der Code-Prefix (alles vor dem ersten
 * `:` bzw. Whitespace) ist der stabile Maschinenteil (§2.4); der Rest der
 * Meldung (z. B. "Zeile 3 (gptx)") bleibt für den Nutzer sichtbar. */
const LAB_ERROR_TEXT = {
  empty_report: "Bitte mindestens einen Wert erfassen.",
  too_many_rows: "Zu viele Zeilen (höchstens 200).",
  unknown_marker: "Unbekannter Marker.",
  unit_required: "Für diesen Marker ist eine Einheit erforderlich.",
  invalid_value: "Ungültiger Wert.",
  unsupported_unit: "Diese Einheit wird für den Marker nicht unterstützt.",
  duplicate_marker: "Dieser Marker kommt im Bericht doppelt vor.",
  invalid_ts: "Ungültiger Zeitpunkt.",
};

function errorCode(text) {
  return String(text || "").trim().split(/[:\s]/)[0];
}

function errorMessage(err) {
  const raw = err && err.message ? String(err.message) : String(err == null ? "" : err);
  const text = raw.trim();
  if (!text) return "Speichern fehlgeschlagen.";
  const code = errorCode(text);
  const known = LAB_ERROR_TEXT[code];
  if (!known) return text;
  const detail = text.slice(code.length).replace(/^:\s*/, "");
  return detail ? `${known} ${detail}` : known;
}
```

(d) CSS in `CARD_CSS` nach dem `.labs-form-grid`-Block ergänzen:

```css
  .labs-report { border-top: 1px solid var(--divider-color, rgba(0,0,0,.08)); padding-top: 8px; }
  .labs-report summary { cursor: pointer; font-weight: 600; }
  .labs-report-rows { display: flex; flex-direction: column; gap: 8px; margin-top: 8px; }
  .labs-report-row {
    display: grid; grid-template-columns: minmax(0, 2fr) minmax(0, 1fr) minmax(0, 1fr) auto;
    gap: 8px; align-items: center;
  }
  .labs-report-actions {
    display: flex; justify-content: space-between; gap: 8px;
    margin-top: 8px; flex-wrap: wrap;
  }
```

(e) Konstruktor (`Zeile 344-348`): direkt nach `this._draft = EMPTY_DRAFT();`

```js
    this._reportDraft = EMPTY_REPORT_DRAFT();
```

(f) `_selectPerson` (`Zeile 382-386`): nach `this._draft = EMPTY_DRAFT();`

```js
    this._reportDraft = EMPTY_REPORT_DRAFT();
```

(g) Neue Methoden vor `/* ---- Events ---` (nach `_saveValue`) einfügen:

```js
  /* ---- Mehrzeilen-Dialog: Laborbericht (REQ-HOM-123) ---------------------- */

  _reportMarkerOptions(markers, selectedKey) {
    const placeholder = selectedKey
      ? ""
      : '<option value="" selected>— bitte wählen —</option>';
    return `${placeholder}${labMarkerOptionsHtml(markers, selectedKey)}`;
  }

  _reportRow(row, index, markers) {
    const disabled = this._saving ? " disabled" : "";
    return `<div class="labs-report-row" data-role="lab-report-row">
      <select data-field="lab-report-marker-${index}" aria-label="Marker"${disabled}>${this._reportMarkerOptions(
        markers,
        row.marker
      )}</select>
      <input type="number" step="any" inputmode="decimal" data-field="lab-report-value-${index}"
        aria-label="Wert" value="${escapeHtml(row.value)}" placeholder="Wert"${disabled} />
      <input type="text" data-field="lab-report-unit-${index}" aria-label="Einheit"
        value="${escapeHtml(row.unit)}" placeholder="Einheit (optional)" autocomplete="off"${disabled} />
      <button type="button" class="labs-tab" data-action="lab-report-remove" data-index="${index}"
        aria-label="Zeile entfernen"${disabled}>✕</button>
    </div>`;
  }

  _reportForm() {
    const markers = this._markers();
    if (!Object.keys(markers).length) return "";
    const draft = this._reportDraft;
    const disabled = this._saving ? " disabled" : "";
    const rows = draft.rows
      .map((row, index) => this._reportRow(row, index, markers))
      .join("");
    return `<details class="labs-report">
      <summary>Laborbericht erfassen</summary>
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
      <div class="labs-report-actions">
        <button type="button" class="labs-tab" data-action="lab-report-add"${disabled}>＋ Zeile</button>
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
      await this._hass.connection.sendMessagePromise(payload);
      this._actionError = "";
      // Bericht-Kontext (ts/reportRef) bleibt für Nachtrag-Korrekturen stehen
      // (§6.4) — geleert werden nur Wert-Felder und die Zeilenliste.
      this._reportDraft = { ...this._reportDraft, rows: [EMPTY_REPORT_ROW()] };
      await this._loadData(true);
    } catch (err) {
      this._actionError = errorMessage(err);
    } finally {
      this._saving = false;
      this._render();
    }
  }
```

(h) `_readEntryTs` (`Zeile 730-744`) auf den gemeinsamen Validator umstellen (Verhalten
  unverändert):

```js
  _readEntryTs() {
    return this._validateTs(this._draft.ts);
  }
```

(i) `_render` (`Zeile 864-866`): nach `const entryForm = ...` ergänzen und im Template
  einsetzen:

```js
    const reportForm = hasData && cfg.allowManualEntry ? this._reportForm() : "";
```

```js
          ${body}
          ${entryForm}
          ${reportForm}
```

(j) `_onClick` (`Zeile 809-823`) erweitern:

```js
    if (action === "lab-report-add") {
      this._addReportRow();
      return;
    }
    if (action === "lab-report-remove") {
      this._removeReportRow(Number(el.getAttribute("data-index")));
      return;
    }
    if (action === "lab-report-save") this._saveReport();
```

(k) `_onInput`/`_onChange` (`Zeile 825-860`): jeweils am Anfang nach dem
  `data-field`-Lookup:

```js
    if (field && field.startsWith("lab-report-")) {
      this._onReportField(field, String(el.value || ""));
      return;
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_card_js.py -k req_hom_123 -q`
Expected: all PASS (der Node-Test wird ohne `node` sauber übersprungen).

- [ ] **Step 5: Regression**

Run: `python3 -m pytest tests/test_card_js.py -q && python3 -m pytest tests/test_frontend.py -q && ruff check .`
Expected: grün/clean. Bestehende `test_req_hom_122_labs_card_*` bleiben grün
(kein Export, kein neuer Import, Karte bleibt standalone).

- [ ] **Step 6: Commit**

```bash
git add custom_components/health_o_mat/www/health-o-mat-labs-card.js tests/test_card_js.py
git commit -m "feat: add multi-row lab report dialog to labs card"
```

---

### Task 7: Panel — Mehrzeilen-Dialog (`panel-base` WS-Name, `panel-views` Formular, `panel` Draft-State) + i18n

**Files:**
- Modify: `custom_components/health_o_mat/www/health-o-mat-panel-base.js` (WS-Konstante)
- Modify: `custom_components/health_o_mat/www/health-o-mat-panel-views.js` (Dialog + Absende-Pfad)
- Modify: `custom_components/health_o_mat/www/health-o-mat-panel.js` (`_labReportDraft`)
- Modify: `custom_components/health_o_mat/strings.json`, `translations/de.json`,
  `translations/en.json` (15 UI-Keys)
- Test: `tests/test_panel_js.py`, `tests/test_translations.py`

**Interfaces:**
- Consumes: `escapeHtml`, `attrValue`, `toNumber`? (nicht nötig), `labMarkerOptionsHtml`,
  `t`, `WS`, `errMsg` (bestehende Importe in `panel-views.js`), `panel._ws`,
  `panel._busy`, `panel._formError`, `panel._reloadEntry(entryId)`.
- Produces: `WS.addLabReport = "health_o_mat/add_lab_report"` (panel-base);
  in `panel-views.js`: `LAB_REPORT_MAX_ROWS_UI = 60`, `LAB_REPORT_ERROR_KEYS`,
  `emptyLabReportRow()`, `labReportErrorText(err)`, `labReportDraft(panel, entryId)`,
  `collectLabReportDraft(panel, entryId)`, `addLabReportRow`, `removeLabReportRow`,
  `validReportTs(raw)`, `reportMarkerOptions()`, `labReportRowHtml()`,
  `labReportForm(panel, labs, entryId)`, `submitLabReport(panel, entryId)`;
  in `panel.js`: `this._labReportDraft = {}` im Konstruktor.
- i18n-Keys (neu, in `common`): `ui_panel_lab_report_title`,
  `ui_panel_lab_report_add_row`, `ui_panel_lab_report_remove_row`,
  `ui_panel_lab_report_save`, `ui_panel_lab_report_ts`, `ui_panel_lab_marker_choose`,
  `ui_panel_lab_err_generic`, `ui_panel_lab_err_empty_report`,
  `ui_panel_lab_err_too_many_rows`, `ui_panel_lab_err_unknown_marker`,
  `ui_panel_lab_err_unit_required`, `ui_panel_lab_err_invalid_value`,
  `ui_panel_lab_err_unsupported_unit`, `ui_panel_lab_err_duplicate_marker`,
  `ui_panel_lab_err_invalid_ts`.
  (`ui_panel_lab_report_ref`, `ui_panel_lab_marker`, `ui_panel_lab_value_field`,
  `ui_panel_lab_unit_field`, `ui_common_optional` existieren bereits.)

**Spec-Bezug:** §6.1–§6.4 (Dialog, Single-Flight, Reset-Semantik), §6.3 (Panel-Draft
defensiv lesen), §2.4 (Prefix-Mapping), §11 (i18n in `_REQ_HOM_122_UI_KEYS`), §12
(Paritätstest Card ↔ Panel).

- [ ] **Step 1: Write the failing tests**

(a) `tests/test_panel_js.py`: ans Ende anhängen

```python
# --- REQ-HOM-123: Panel-Mehrzeilen-Dialog -----------------------------------


def test_req_hom_123_panel_base_ws_knows_add_lab_report():
    source = _panel_base_source()

    assert 'addLabReport: "health_o_mat/add_lab_report",' in source


def test_req_hom_123_panel_views_renders_report_form():
    views = (_WWW_DIR / "health-o-mat-panel-views.js").read_text(encoding="utf-8")
    body = _js_function_block(views, "labReportForm")

    for needle in (
        "lab-report-ts",
        "lab-report-ref",
        "lab-report-marker-",
        "lab-report-value-",
        'data-action="lab-report-add"',
        'data-action="lab-report-remove"',
        'data-action="lab-report-save"',
        "labMarkerOptionsHtml(",
        "escapeHtml(",
        "attrValue(",
    ):
        assert needle in body, needle
    assert "LAB_REPORT_MAX_ROWS_UI" in views


def test_req_hom_123_panel_entry_module_initialises_report_draft():
    entry = (_WWW_DIR / "health-o-mat-panel.js").read_text(encoding="utf-8")

    assert re.search(r"this\._labReportDraft\s*=\s*\{\s*\}", entry), (
        "der Bericht-Draft wird nicht initialisiert"
    )


def test_req_hom_123_panel_report_draft_is_read_defensively():
    views = (_WWW_DIR / "health-o-mat-panel-views.js").read_text(encoding="utf-8")

    assert "panel._labReportDraft && panel._labReportDraft[entryId]" in views


def test_req_hom_123_panel_report_single_flight_and_context_reset():
    views = (_WWW_DIR / "health-o-mat-panel-views.js").read_text(encoding="utf-8")
    body = _js_function_block(views, "submitLabReport")

    assert "panel._busy" in body
    assert "WS.addLabReport" in body
    assert "rows: [emptyLabReportRow()]" in body
    # ts/reportRef werden NICHT geleert (§6.4).
    assert 'ts: ""' not in body
    assert 'reportRef: ""' not in body


def test_req_hom_123_error_code_table_parity_card_and_panel():
    """Beide Dateien mappen exakt dieselben acht Fehlercodes (§12)."""
    pattern = re.compile(r"^\s*([a-z_]+):", re.M)

    card = re.search(
        r"const LAB_ERROR_TEXT = \{(.*?)\n\};",
        (_WWW_DIR / "health-o-mat-labs-card.js").read_text(encoding="utf-8"),
        re.S,
    )
    panel = re.search(
        r"const LAB_REPORT_ERROR_KEYS = \{(.*?)\n\};",
        (_WWW_DIR / "health-o-mat-panel-views.js").read_text(encoding="utf-8"),
        re.S,
    )
    assert card is not None and panel is not None

    expected = {
        "empty_report",
        "too_many_rows",
        "unknown_marker",
        "unit_required",
        "invalid_value",
        "unsupported_unit",
        "duplicate_marker",
        "invalid_ts",
    }
    assert set(pattern.findall(card.group(1))) == expected
    assert set(pattern.findall(panel.group(1))) == expected
```

(b) `tests/test_translations.py`: die 15 Keys in `_REQ_HOM_122_UI_KEYS` aufnehmen
(`tests/test_translations.py:506-541`, Liste alphabetisch nicht zwingend — ans Ende):

```python
    "ui_panel_lab_report_title",
    "ui_panel_lab_report_add_row",
    "ui_panel_lab_report_remove_row",
    "ui_panel_lab_report_save",
    "ui_panel_lab_report_ts",
    "ui_panel_lab_marker_choose",
    "ui_panel_lab_err_generic",
    "ui_panel_lab_err_empty_report",
    "ui_panel_lab_err_too_many_rows",
    "ui_panel_lab_err_unknown_marker",
    "ui_panel_lab_err_unit_required",
    "ui_panel_lab_err_invalid_value",
    "ui_panel_lab_err_unsupported_unit",
    "ui_panel_lab_err_duplicate_marker",
    "ui_panel_lab_err_invalid_ts",
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_panel_js.py -k req_hom_123 -q && python3 -m pytest tests/test_translations.py -k req_hom_122_common_ui_keys -q`
Expected: FAIL — fehlende `labReportForm`-Funktion / `addLabReport`-Konstante; der
i18n-Test meldet `fehlende Laborwert-UI-Keys`.

- [ ] **Step 3: Implement — `panel-base.js`**

Nach `addLabValue: "health_o_mat/add_lab_value",` (Zeile 135):

```js
  addLabReport: "health_o_mat/add_lab_report",
```

- [ ] **Step 4: Implement — `panel.js`**

Nach `this._labCustomDraft = {};` (`Zeile 138`):

```js
    this._labReportDraft = {}; // entry_id -> working copy of a lab report dialog
```

- [ ] **Step 5: Implement — `panel-views.js`**

(a) Import-Block (`Zeile 13-43`) um `attrValue,` erweitern (neben `escapeHtml,`) — der
Bericht-Dialog schreibt Werte/Einheiten als Attribut-Inhalte.

(b) Block „Laborbericht" vor `function stepLabCategory` (nach `submitLabValue`, Zeile 977)
einfügen:

```js
/* ---- Laborbericht (REQ-HOM-123) ------------------------------------------
 *
 * Bewusst eine zweite, panel-lokale Implementierung des Dialogs (§6.3): die
 * Karte ist standalone, ein Shared-Modul lohnte erst beim dritten Konsumenten.
 * Die Parität sichern Tests (gleiche Fehlercode-Tabelle, gleiche Regeln).
 */

const LAB_REPORT_MAX_ROWS_UI = 60;
const TS_FUTURE_TOLERANCE_MS = 5 * 60 * 1000;

const LAB_REPORT_ERROR_KEYS = {
  empty_report: ["ui_panel_lab_err_empty_report", "Bitte mindestens einen Wert erfassen."],
  too_many_rows: ["ui_panel_lab_err_too_many_rows", "Zu viele Zeilen (höchstens 200)."],
  unknown_marker: ["ui_panel_lab_err_unknown_marker", "Unbekannter Marker."],
  unit_required: [
    "ui_panel_lab_err_unit_required",
    "Für diesen Marker ist eine Einheit erforderlich.",
  ],
  invalid_value: ["ui_panel_lab_err_invalid_value", "Ungültiger Wert."],
  unsupported_unit: [
    "ui_panel_lab_err_unsupported_unit",
    "Diese Einheit wird für den Marker nicht unterstützt.",
  ],
  duplicate_marker: [
    "ui_panel_lab_err_duplicate_marker",
    "Dieser Marker kommt im Bericht doppelt vor.",
  ],
  invalid_ts: ["ui_panel_lab_err_invalid_ts", "Ungültiger Zeitpunkt."],
};

function emptyLabReportRow() {
  return { marker: "", value: "", unit: "" };
}

function labReportErrorText(err) {
  const raw = err && err.message ? String(err.message) : String(err == null ? "" : err);
  const text = raw.trim();
  if (!text) return t("ui_panel_lab_err_generic", "Speichern fehlgeschlagen.");
  const code = text.split(/[:\s]/)[0];
  const entry = LAB_REPORT_ERROR_KEYS[code];
  if (!entry) return text;
  const detail = text.slice(code.length).replace(/^:\s*/, "");
  const base = t(entry[0], entry[1]);
  return detail ? `${base} ${detail}` : base;
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

function validReportTs(raw) {
  const value = String(raw || "").trim();
  if (!value) return { iso: "" };
  const parsed = new Date(value);
  if (!Number.isFinite(parsed.getTime())) {
    return { error: t("ui_panel_lab_err_invalid_ts", "Ungültiger Zeitpunkt.") };
  }
  if (parsed.getTime() > Date.now() + TS_FUTURE_TOLERANCE_MS) {
    return { error: t("ui_panel_lab_err_invalid_ts", "Ungültiger Zeitpunkt.") };
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

function labReportRowHtml(markers, row, index, entryId, disabled) {
  return `<div class="lab-report-row">
      <select data-field="lab-report-marker-${index}" aria-label="${escapeHtml(
        t("ui_panel_lab_marker", "Marker")
      )}"${disabled}>${reportMarkerOptions(markers, row.marker)}</select>
      <input type="number" step="any" inputmode="decimal"
        data-field="lab-report-value-${index}" aria-label="${escapeHtml(
          t("ui_panel_lab_value_field", "Wert")
        )}" value="${attrValue(row.value)}" placeholder="${escapeHtml(
          t("ui_panel_lab_value_field", "Wert")
        )}"${disabled} />
      <input type="text" data-field="lab-report-unit-${index}" aria-label="${escapeHtml(
        t("ui_panel_lab_unit_field", "Einheit (optional)")
      )}" value="${attrValue(row.unit)}" placeholder="${escapeHtml(
        t("ui_common_optional", "optional")
      )}" autocomplete="off"${disabled} />
      <button class="btn ghost" type="button" data-action="lab-report-remove"
        data-entry="${escapeHtml(entryId)}" data-index="${index}" aria-label="${escapeHtml(
          t("ui_panel_lab_report_remove_row", "Zeile entfernen")
        )}"${disabled}>\u2715</button>
    </div>`;
}

function labReportForm(panel, labs, entryId) {
  const draft = labReportDraft(panel, entryId);
  const disabled = panel._busy ? " disabled" : "";
  const rows = draft.rows
    .map((row, index) => labReportRowHtml(labs.markers || {}, row, index, entryId, disabled))
    .join("");
  return `<details class="lab-report-form">
      <summary>${escapeHtml(t("ui_panel_lab_report_title", "Laborbericht erfassen"))}</summary>
      <label class="field">${escapeHtml(t("ui_panel_lab_report_ts", "Zeitpunkt"))}
        <input type="datetime-local" data-field="lab-report-ts" value="${attrValue(
          draft.ts
        )}" />
      </label>
      <label class="field">${escapeHtml(
        t("ui_panel_lab_report_ref", "Bericht-Link/ID (optional)")
      )}
        <input type="text" data-field="lab-report-ref" value="${attrValue(
          draft.reportRef
        )}" placeholder="${escapeHtml(t("ui_common_optional", "optional"))}"
          autocomplete="off" />
      </label>
      <div class="lab-report-rows">${rows}</div>
      <div class="lab-report-actions">
        <button class="btn ghost" type="button" data-action="lab-report-add"
          data-entry="${escapeHtml(entryId)}"${disabled}>＋ ${escapeHtml(
            t("ui_panel_lab_report_add_row", "Zeile")
          )}</button>
        <button class="btn" type="button" data-action="lab-report-save"
          data-entry="${escapeHtml(entryId)}"${disabled}>\u{1F4BE} ${escapeHtml(
            t("ui_panel_lab_report_save", "Bericht speichern")
          )}</button>
      </div>
    </details>`;
}

function addLabReportRow(panel, entryId) {
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

async function submitLabReport(panel, entryId) {
  if (!panel || !entryId || panel._busy || typeof panel._ws !== "function") return;
  const draft = collectLabReportDraft(panel, entryId);
  const ts = validReportTs(draft.ts);
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
    if (!marker) {
      panel._formError = t("ui_panel_lab_err_unknown_marker", "Unbekannter Marker.");
      panel._render();
      return;
    }
    if (!/^-?\d+(\.\d+)?$/.test(rawValue)) {
      panel._formError = t("ui_panel_lab_err_invalid_value", "Ungültiger Wert.");
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
      "ui_panel_lab_err_empty_report",
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
    await panel._ws(message);
    // ts/reportRef bleiben stehen (§6.4) — nur Werte + Zeilen werden geleert.
    panel._labReportDraft[entryId] = { ...draft, rows: [emptyLabReportRow()] };
    await panel._reloadEntry(entryId);
  } catch (err) {
    panel._formError = labReportErrorText(err);
  } finally {
    panel._busy = false;
    panel._render();
  }
}
```

(b) `labsTab` (`Zeile 1066-1117`): Fehlerbanner aus dem `<details>` herausziehen und den
Bericht-Dialog anhängen. Den Block ab `const formError = ...` bis zum `return` ersetzen
durch:

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

(c) Klick-Delegation in `ensureLabGestures` (`Zeile 1040-1064`) vor dem `lab-add-value`-
  Zweig ergänzen:

```js
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

(d) `PANEL_CSS` (`panel-base.js`, bei den bestehenden `.lab-*`-Regeln ab Zeile 674):

```css
  .lab-report-form { margin-top: 8px; }
  .lab-report-form summary { cursor: pointer; font-weight: 600; }
  .lab-report-rows { display: flex; flex-direction: column; gap: 8px; margin-top: 8px; }
  .lab-report-row {
    display: grid; grid-template-columns: minmax(0, 2fr) minmax(0, 1fr) minmax(0, 1fr) auto;
    gap: 8px; align-items: center;
  }
  .lab-report-actions {
    display: flex; justify-content: space-between; gap: 8px;
    margin-top: 8px; flex-wrap: wrap;
  }
```

- [ ] **Step 6: Implement — i18n (15 Keys in `common`)**

`strings.json` (Master, englisch):

```json
    "ui_panel_lab_report_title": "Record lab report",
    "ui_panel_lab_report_add_row": "Row",
    "ui_panel_lab_report_remove_row": "Remove row",
    "ui_panel_lab_report_save": "Save report",
    "ui_panel_lab_report_ts": "Timestamp",
    "ui_panel_lab_marker_choose": "— choose —",
    "ui_panel_lab_err_generic": "Saving failed.",
    "ui_panel_lab_err_empty_report": "Record at least one value.",
    "ui_panel_lab_err_too_many_rows": "Too many rows (at most 200).",
    "ui_panel_lab_err_unknown_marker": "Unknown marker.",
    "ui_panel_lab_err_unit_required": "This marker requires a unit.",
    "ui_panel_lab_err_invalid_value": "Invalid value.",
    "ui_panel_lab_err_unsupported_unit": "This unit is not supported for the marker.",
    "ui_panel_lab_err_duplicate_marker": "This marker appears twice in the report.",
    "ui_panel_lab_err_invalid_ts": "Invalid timestamp.",
```

`translations/de.json`:

```json
    "ui_panel_lab_report_title": "Laborbericht erfassen",
    "ui_panel_lab_report_add_row": "Zeile",
    "ui_panel_lab_report_remove_row": "Zeile entfernen",
    "ui_panel_lab_report_save": "Bericht speichern",
    "ui_panel_lab_report_ts": "Zeitpunkt",
    "ui_panel_lab_marker_choose": "— bitte wählen —",
    "ui_panel_lab_err_generic": "Speichern fehlgeschlagen.",
    "ui_panel_lab_err_empty_report": "Bitte mindestens einen Wert erfassen.",
    "ui_panel_lab_err_too_many_rows": "Zu viele Zeilen (höchstens 200).",
    "ui_panel_lab_err_unknown_marker": "Unbekannter Marker.",
    "ui_panel_lab_err_unit_required": "Für diesen Marker ist eine Einheit erforderlich.",
    "ui_panel_lab_err_invalid_value": "Ungültiger Wert.",
    "ui_panel_lab_err_unsupported_unit": "Diese Einheit wird für den Marker nicht unterstützt.",
    "ui_panel_lab_err_duplicate_marker": "Dieser Marker kommt im Bericht doppelt vor.",
    "ui_panel_lab_err_invalid_ts": "Ungültiger Zeitpunkt.",
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

## Wave 2 — REQ-HOM-125: Medizin-Hinweis im Panel-Lab-Tab

### Task 8: Panel-Disclaimer (immer sichtbar, ohne Settings/Admin-Abhängigkeit)

**Files:**
- Modify: `custom_components/health_o_mat/www/health-o-mat-panel-views.js`
- Modify: `custom_components/health_o_mat/www/health-o-mat-panel-base.js` (`PANEL_CSS`)
- Modify: `custom_components/health_o_mat/strings.json`, `translations/de.json`,
  `translations/en.json` (`ui_panel_lab_disclaimer`)
- Test: `tests/test_panel_js.py`, `tests/test_translations.py`

**Interfaces:**
- Consumes: `t(key, fallback)`, `escapeHtml`, `messageHtml`.
- Produces: `labDisclaimerHtml()` in `panel-views.js`; `labsTab` rendert
  `<div class="labs-disclaimer" role="note">` **vor** der Kategorie-Leiste (und auch im
  Leerfall „keine Kategorien sichtbar"); `.labs-disclaimer` in `PANEL_CSS`. Kein neuer
  Request, kein Settings-Feld, keine Backup-Änderung.

**Spec-Bezug:** §8 (v1 ohne Toggle, identischer Wortlaut zur Card, eigenes CSS),
REQ-HOM-125-Akzeptanz (ohne Admin/`get_settings`, Grep-Beleg, CSS-Klasse, frischer Tab).

- [ ] **Step 1: Write the failing tests**

(a) `tests/test_panel_js.py` ans Ende:

```python
# --- REQ-HOM-125: Panel-Disclaimer ------------------------------------------


def test_req_hom_125_panel_labs_tab_renders_disclaimer_before_category_bar():
    views = (_WWW_DIR / "health-o-mat-panel-views.js").read_text(encoding="utf-8")
    body = _js_function_block(views, "labsTab")
    disclaimer = _js_function_block(views, "labDisclaimerHtml")

    assert "ui_panel_lab_disclaimer" in disclaimer
    assert "labs-disclaimer" in disclaimer
    assert 'role="note"' in disclaimer
    assert "labDisclaimerHtml()" in body
    # Der Hinweis steht vor der Kategorie-Leiste im gerenderten String.
    assert body.index("labDisclaimerHtml()") < body.index("labCategoryBar")


def test_req_hom_125_panel_disclaimer_does_not_depend_on_settings_or_admin():
    views = (_WWW_DIR / "health-o-mat-panel-views.js").read_text(encoding="utf-8")
    body = _js_function_block(views, "labsTab")

    assert "_settings" not in body
    assert "getSettings" not in body
    assert "isAdmin" not in body
    assert "is_admin" not in body


def test_req_hom_125_panel_css_defines_labs_disclaimer():
    source = _panel_base_source()
    match = re.search(r"export const PANEL_CSS = `(.*?)`;", source, re.S)
    assert match is not None
    css = match.group(1)

    assert ".labs-disclaimer" in css
    assert "--warning-color" in css


def test_req_hom_125_no_panel_disclaimer_setting_identifier():
    """Kein Toggle-/Settings-Bezeichner im Code (Grep-Beleg, auf custom_components gescoped)."""
    forbidden = (
        "lab_hide_panel_disclaimer",
        "hide_panel_disclaimer",
        "panel_lab_disclaimer_option",
    )
    hits: list[str] = []
    for path in Path(_COMPONENT_DIR).rglob("*"):
        if not path.is_file() or path.suffix not in {".py", ".js", ".json", ".yaml"}:
            continue
        text = path.read_text(encoding="utf-8")
        hits.extend(f"{path.relative_to(_COMPONENT_DIR)}:{name}" for name in forbidden if name in text)
    assert hits == [], f"verbotene Disclaimer-Settings-Bezeichner: {hits}"
```

(b) `tests/test_translations.py`: `"ui_panel_lab_disclaimer"` in `_REQ_HOM_122_UI_KEYS`
aufnehmen.

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_panel_js.py -k req_hom_125 -q`
Expected: FAIL — `ui_panel_lab_disclaimer`/`labs-disclaimer` fehlen; i18n-Test meldet den
fehlenden Key.

- [ ] **Step 3: Implement — `panel-views.js`**

Vor `labsTab` einfügen:

```js
/* Kontextbezogener Medizin-Hinweis (§8, REQ-HOM-125). v1 bewusst IMMER sichtbar:
 * ein Toggle müsste den Zustand im Nicht-Admin-Kontext kennen, und `get_settings`
 * ist admin-only — ein darauf gestütztes Flag wäre für normale Nutzer wirkungslos. */
function labDisclaimerHtml() {
  return `<div class="labs-disclaimer" role="note">${escapeHtml(
    t(
      "ui_panel_lab_disclaimer",
      "⚠️ Hinweis: keine medizinische Beratung — Richtwerte, keine Diagnose. Referenzbereiche in den Einstellungen anpassen."
    )
  )}</div>`;
}
```

In `labsTab` nach `const categories = visibleLabCategories(labs);`:

```js
  const disclaimer = labDisclaimerHtml();
```

und den Leerfall sowie den Rückgabestring anpassen:

```js
  if (!categories.length) {
    return `${disclaimer}${messageHtml(
      t("ui_panel_lab_no_categories", "Keine Laborwert-Kategorie sichtbar."),
      false
    )}`;
  }
```

```js
  return `${disclaimer}${labCategoryBar(labs, active)}<div class="lab-rows">${rows}</div>${formError}${entryForm}${reportForm}`;
```

(Im Leerfall steht der Hinweis ebenfalls — „immer sichtbar" gilt auch ohne Kategorien.)

- [ ] **Step 4: Implement — `PANEL_CSS`**

Bei den `.lab-*`-Regeln (`panel-base.js`, Zeile 674 ff.):

```css
  .labs-disclaimer {
    padding: 8px 10px; border-radius: 8px; font-size: .9rem; margin-bottom: 8px;
    background: var(--warning-color, #ff9800); color: #fff;
  }
```

- [ ] **Step 5: Implement — i18n**

`strings.json`:

```json
    "ui_panel_lab_disclaimer": "⚠️ Note: not medical advice — reference values, not a diagnosis. Adjust reference ranges in the settings.",
```

`translations/de.json`:

```json
    "ui_panel_lab_disclaimer": "⚠️ Hinweis: keine medizinische Beratung — Richtwerte, keine Diagnose. Referenzbereiche in den Einstellungen anpassen.",
```

`translations/en.json`: identisch zu `strings.json`.

- [ ] **Step 6: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_panel_js.py -k req_hom_125 -q && python3 -m pytest tests/test_translations.py -k req_hom_122_common_ui_keys -q`
Expected: all PASS.

- [ ] **Step 7: Regression**

Run: `python3 -m pytest tests/test_panel_js.py tests/test_translations.py -q && ruff check . && ruff format --check .`
Expected: grün/clean.

- [ ] **Step 8: Commit**

```bash
git add custom_components/health_o_mat/www/health-o-mat-panel-views.js custom_components/health_o_mat/www/health-o-mat-panel-base.js custom_components/health_o_mat/strings.json custom_components/health_o_mat/translations/de.json custom_components/health_o_mat/translations/en.json tests/test_panel_js.py tests/test_translations.py
git commit -m "feat: show medical disclaimer in the panel lab tab"
```

---

## Wave 3 — REQ-HOM-124: Admin-Sichtbarkeit der Umrechnungen

### Task 9: `panel-admin.js` — Spalte „Umrechnung" + „Einheit Pflicht"-Badge + Locale-Faktor

**Files:**
- Modify: `custom_components/health_o_mat/www/health-o-mat-panel-admin.js`
- Modify: `custom_components/health_o_mat/strings.json`, `translations/de.json`,
  `translations/en.json` (`ui_admin_lab_conversion`, `_required`, `_none`)
- Test: `tests/test_panel_js.py`, `tests/test_translations.py`

**Interfaces:**
- Consumes: `settings.lab_catalog.markers[*].alt_units` (`{unit: factor_to_canonical}`),
  `.require_explicit_unit`, `.canonical_unit` (verbatim aus `build_settings`,
  `ws_api.py:1659`); `formatNumber(value)` aus `panel-base.js` (`Zeile 752`) —
  locale-fähig über `Intl.NumberFormat(intlLocale())`; `t`, `escapeHtml`,
  `labDisplayName`.
- Produces: `conversionText(marker)`, `requiredBadge(marker)` innerhalb
  `labSettingsSection`; neue Tabellenspalte zwischen „Einheit" und „Referenz"; das
  Nice-to-have erweitert `altUnitText` um den Faktor. **Keine** Server-/WS-Änderung.

**Spec-Bezug:** §7 (Pflicht: Spalte, locale-Faktor, Badge; Nice-to-have: Custom-Faktor),
REQ-HOM-124-Akzeptanz (DE `88,4` / EN `88.4`, `—` bei leerem `alt_units`,
`urine_protein_creatinine_ratio` mit Badge, keine API-Änderung, neue Keys + Whitelist).

- [ ] **Step 1: Write the failing tests**

(a) `tests/test_panel_js.py` ans Ende:

```python
# --- REQ-HOM-124: Admin-Umrechnungsspalte -----------------------------------


_NODE_ADMIN_CONVERSION_RUNNER = """import { pathToFileURL } from "node:url";

const base = await import(pathToFileURL(process.argv[2]).href);
const admin = await import(pathToFileURL(process.argv[3]).href);
const markers = {
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
};
const settings = {
  lab_catalog: {
    categories: [{ key: "kidney", name: "Niere", name_de: "Niere", name_en: "Kidney" }],
    markers,
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
    """Rendert `labSettingsSection` als echtes ES-Modul (Panels teilen kein CSS/JS)."""
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
    # Leeres alt_units -> Platzhalter.
    assert "—" in rendered["de"]
    # Pflicht-Einheit-Marker traegt das Badge.
    assert "Einheit Pflicht" in rendered["de"]


def test_req_hom_124_admin_conversion_uses_format_number():
    admin = (_WWW_DIR / "health-o-mat-panel-admin.js").read_text(encoding="utf-8")
    body = _js_function_block(admin, "labSettingsSection")

    assert "formatNumber(factor)" in body
    assert "ui_admin_lab_conversion_required" in body
    assert "ui_admin_lab_conversion_none" in body
    # Kein hartkodiertes Trennzeichen / keine Rohwert-Konkatenation.
    assert "toFixed(" not in body
    assert "× ${factor}" not in body


def test_req_hom_124_admin_conversion_imports_format_number():
    admin = (_WWW_DIR / "health-o-mat-panel-admin.js").read_text(encoding="utf-8")

    assert re.search(r"import \{[^}]*\bformatNumber\b[^}]*\} from \"./health-o-mat-panel-base\.js", admin, re.S)


def test_req_hom_124_admin_conversion_header_exists():
    admin = (_WWW_DIR / "health-o-mat-panel-admin.js").read_text(encoding="utf-8")

    assert 't("ui_admin_lab_conversion", "Umrechnung")' in admin
```

(b) `tests/test_translations.py`: die drei Keys in `_REQ_HOM_122_UI_KEYS` aufnehmen:

```python
    "ui_admin_lab_conversion",
    "ui_admin_lab_conversion_required",
    "ui_admin_lab_conversion_none",
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_panel_js.py -k req_hom_124 -q`
Expected: FAIL — `formatNumber` wird nicht importiert, `ui_admin_lab_conversion` fehlt in
der Tabelle; der Node-Test findet den Faktor nicht im gerenderten HTML.

- [ ] **Step 3: Implement — Import in `panel-admin.js`**

Im Import-Block (`Zeile 15-31`) `formatNumber,` ergänzen (z. B. nach `escapeHtml,`).

- [ ] **Step 4: Implement — Helfer in `labSettingsSection`**

Direkt nach `altUnitText` (`Zeile 360-363`) einfügen:

```js
  // Umrechnung je Alt-Einheit: "Alt × Faktor → kanonisch". Der Faktor kommt
  // aus `formatNumber` (locale-fähig, Intl.NumberFormat) — kein hartkodiertes
  // Komma, keine String-Konkatenation des Rohwerts (§7).
  const conversionText = (marker) => {
    const altUnits = marker && typeof marker.alt_units === "object" ? marker.alt_units : {};
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
          `${escapeHtml(unit)} × ${escapeHtml(formatNumber(factor))} → ${escapeHtml(canonical)}`
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

- [ ] **Step 5: Implement — Tabelle**

(a) Zellen in `refRows` (`Zeile 365-389`): nach der Einheiten-Zelle

```js
          <td>${escapeHtml(definition.canonical_unit || "")}</td>
          <td>${conversionText(definition)}${requiredBadge(definition)}</td>
```

(b) Header (`Zeile 429-438`): zwischen „Einheit" und „Referenz"

```js
          <th>${escapeHtml(t("ui_admin_lab_unit", "Einheit"))}</th>
          <th>${escapeHtml(t("ui_admin_lab_conversion", "Umrechnung"))}</th>
          <th>${escapeHtml(t("ui_admin_lab_range", "Referenz"))}</th>
```

- [ ] **Step 6 (Nice-to-have): Custom-Marker-Faktor** — nur wenn die Pflichtteile grün
  sind; darf bei Zeitdruck entfallen, ohne die Pflichtteile zu berühren.

`altUnitText` (`Zeile 360-363`) ersetzen durch:

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

und in der Custom-Zeile (`Zeile 402-413`) den Zusatz auf `· alt: ${altUnitText(marker)}`
ändern.

- [ ] **Step 7: Implement — i18n**

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

`translations/en.json`: identisch zu `strings.json`.

- [ ] **Step 8: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_panel_js.py -k req_hom_124 -q && python3 -m pytest tests/test_translations.py -k req_hom_122_common_ui_keys -q`
Expected: all PASS (Node-Test ggf. übersprungen, die Quelltext-Tests decken dieselben
Invarianten).

- [ ] **Step 9: Regression**

Run: `python3 -m pytest tests/test_panel_js.py tests/test_translations.py tests/test_ws_api.py -q && ruff check . && ruff format --check .`
Expected: grün/clean — `test_req_hom_122_panel_admin_lab_section_escapes_dynamic_values`
bleibt grün (weiterhin `escapeHtml`/`attrValue`).

- [ ] **Step 10: Commit**

```bash
git add custom_components/health_o_mat/www/health-o-mat-panel-admin.js custom_components/health_o_mat/strings.json custom_components/health_o_mat/translations/de.json custom_components/health_o_mat/translations/en.json tests/test_panel_js.py tests/test_translations.py
git commit -m "feat: show lab unit conversions in admin settings"
```

---

## Wave 4 — REQ-HOM-126: Beispiel-Dashboard für die Labs-Card

### Task 10: `examples/dashboard-labs-card.yaml` + `test_dashboards.py` + README-Verweis

**Files:**
- Create: `examples/dashboard-labs-card.yaml`
- Modify: `tests/test_dashboards.py`
- Modify: `README.md`
- Test: `tests/test_dashboards.py`

**Interfaces:**
- Consumes: `custom:health-o-mat-labs-card` + den Schlüsselsatz aus `normalizeCardConfig`
  (`health-o-mat-labs-card.js:234-252`).
- Produces: neue Beispiel-Datei ohne Entity-Referenzen; `LABS_CARD_TYPE` /
  `LABS_CARD_KEYS` + erweiterte Sammel-/Key-Prüfung in `test_dashboards.py`.
- Die Datei bindet **keine** Person fest (`person_mode: selector`), damit Copy-Paste auf
  jeder Instanz funktioniert.

**Spec-Bezug:** §9 (YAML-Inhalt, Filter auskommentiert, Testanpassung §9.1),
REQ-HOM-126-Akzeptanz.

- [ ] **Step 1: Write the failing tests** — `tests/test_dashboards.py` anpassen

(a) Nach `CARD_KEYS` (`Zeile 108-131`) ergänzen:

```python
# Laborwerte-Karte (REQ-HOM-122/126): eigener Typ und eigener Schlüsselsatz.
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

(b) `extract_card_configs` (`Zeile 134-143`) auf beide Typen erweitern:

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

(c) Im Sammeltest (`Zeile 162-166`) die Key-Prüfung je Typ machen:

```python
        for card in card_configs:
            allowed = LABS_CARD_KEYS if card.get("type") == LABS_CARD_TYPE else CARD_KEYS
            unknown = set(card) - allowed
            assert not unknown, f"{path}: unbekannte Karten-Keys {sorted(unknown)}"
```

(d) Neuen Test am Dateiende ergänzen:

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

  - title: Anzeige               # reine Anzeige, Personen-Dropdown gefiltert
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

- [ ] **Step 4: README-Verweis ergänzen**

(a) Im Abschnitt „Dashboard-Beispiele" (`README.md:806-820`) als letzten Bullet:

```markdown
- [`examples/dashboard-labs-card.yaml`](examples/dashboard-labs-card.yaml) — zeigt die
  **Laborwerte-Karte** (`custom:health-o-mat-labs-card`) in zwei Ansichten (alle Defaults,
  reine Anzeige mit Personen-Dropdown); Personenfilter anpassen oder entfernen — ohne
  Filter zeigt die Karte alle Personen
```

(b) Im Labs-Card-Abschnitt (`README.md:557-578`) am Absatzende ergänzen:

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

## Wave 5 — E2E + Doku

### Task 11: E2E-Erweiterung (`tests_e2e/test_lab_values_e2e.py`)

**Files:**
- Modify: `tests_e2e/test_lab_values_e2e.py`
- Modify: `tests_e2e/conftest.py` **nur falls** ein Fixture fehlt (prüfen; die
  vorhandenen `logged_in_page`, `hass_base_url`, `hass_bearer_token`, `panel_person`
  genügen für alle drei Szenarien)

**Interfaces:**
- Consumes: bestehende Helfer `open_panel`, `wait_for_detail`, `_panel_data`,
  `_wait_for`, `_settings`, `CARD_TIMEOUT`, `LAB_TAB`, `LAB_CATEGORY_BAR`,
  `scripts.e2e_bootstrap._ws_command`.
- Produces: drei Tests — (a) Bericht mit zwei Zeilen über den Panel-Dialog, (b) Duplikat
  → Fehler mit Zeilenbezug, Eingaben bleiben, Server-Payload unverändert, (c) Disclaimer
  im frisch geöffneten Lab-Tab. Kein Non-Admin-Fixture nötig: die Admin-Unabhängigkeit
  ist bereits durch `test_req_hom_125_panel_disclaimer_does_not_depend_on_settings_or_admin`
  (Task 8) statisch gepinnt; E2E prüft die Sichtbarkeit im echten Render.

**Spec-Bezug:** §12 (E2E-Zeile), §11-REQ-HOM-123/125-Akzeptanz.

- [ ] **Step 1: Add selectors** (bei den bestehenden Labor-Selectoren, `Zeile 75-90`)

```python
LAB_REPORT_ADD = "[data-action='lab-report-add']"
LAB_REPORT_SAVE = "[data-action='lab-report-save']"
LAB_REPORT_MARKER = "[data-field='lab-report-marker-%d']"
LAB_REPORT_VALUE = "[data-field='lab-report-value-%d']"
LAB_REPORT_UNIT = "[data-field='lab-report-unit-%d']"
LAB_REPORT_FORM_ERROR = ".msg.error"
LAB_DISCLAIMER = ".labs-disclaimer"
```

- [ ] **Step 2: Write the failing tests** (ans Dateiende)

```python
# --- REQ-HOM-123/125: Bericht-Dialog + Panel-Disclaimer ---------------------


def test_req_hom_123_lab_report_dialog_writes_all_rows(
    logged_in_page, hass_base_url, hass_bearer_token, panel_person
):
    """[REQ-HOM-123] Zwei Zeilen, ein Speichern → beide Werte im Server-Payload."""
    page = logged_in_page
    entry_id = panel_person["entry_id"]
    # Eindeutige Werte je Lauf: die geteilte Instanz behält Lab-Lesungen, ein
    # fester Wert könnte von einem früheren Lauf stammen (REQ-122-Muster).
    alt_value = round(100 + (uuid.uuid4().int % 90) / 10, 1)   # 100.0 … 108.9
    crp_value = round(10 + (uuid.uuid4().int % 90) / 10, 1)    # 10.0 … 18.9

    panel = open_panel(page, hass_base_url, person=panel_person["slug"])
    wait_for_detail(panel)
    panel.locator(LAB_TAB).click()
    panel.locator(LAB_CATEGORY_BAR).wait_for(state="visible", timeout=CARD_TIMEOUT)

    panel.locator(LAB_REPORT_ADD).click()
    panel.locator(LAB_REPORT_MARKER % 0).select_option("alt")
    panel.locator(LAB_REPORT_VALUE % 0).fill(str(alt_value))
    panel.locator(LAB_REPORT_UNIT % 0).fill("U/L")
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
    assert after["labs"]["markers"]["crp"]["reported_value"] == crp_value
    assert after["labs"]["markers"]["crp"]["unit"] == "mg/L"


def test_req_hom_123_lab_report_duplicate_keeps_input_and_writes_nothing(
    logged_in_page, hass_base_url, hass_bearer_token, panel_person
):
    """[REQ-HOM-123] Duplikat → Zeilenbezug, Draft bleibt, Payload unverändert."""
    page = logged_in_page
    entry_id = panel_person["entry_id"]
    before = _panel_data(hass_base_url, hass_bearer_token, entry_id)
    before_alt = before["labs"]["markers"]["alt"].get("reported_value")

    panel = open_panel(page, hass_base_url, person=panel_person["slug"])
    wait_for_detail(panel)
    panel.locator(LAB_TAB).click()
    panel.locator(LAB_CATEGORY_BAR).wait_for(state="visible", timeout=CARD_TIMEOUT)

    panel.locator(LAB_REPORT_ADD).click()
    panel.locator(LAB_REPORT_MARKER % 0).select_option("alt")
    panel.locator(LAB_REPORT_VALUE % 0).fill("33")
    panel.locator(LAB_REPORT_MARKER % 1).select_option("alt")
    panel.locator(LAB_REPORT_VALUE % 1).fill("34")
    panel.locator(LAB_REPORT_SAVE).click()

    error = panel.locator(LAB_REPORT_FORM_ERROR)
    error.wait_for(state="visible", timeout=CARD_TIMEOUT)
    message = error.inner_text()
    assert "Zeile 2" in message
    assert panel.locator(LAB_REPORT_VALUE % 0).input_value() == "33"

    after = _panel_data(hass_base_url, hass_bearer_token, entry_id)
    assert after["labs"]["markers"]["alt"].get("reported_value") == before_alt


def test_req_hom_125_panel_labs_tab_shows_disclaimer(
    logged_in_page, hass_base_url, panel_person
):
    """[REQ-HOM-125] Der Hinweis steht im Lab-Tab ohne Settings-Ladevorgang."""
    page = logged_in_page
    panel = open_panel(page, hass_base_url, person=panel_person["slug"])
    wait_for_detail(panel)
    panel.locator(LAB_TAB).click()

    disclaimer = panel.locator(LAB_DISCLAIMER)
    disclaimer.wait_for(state="visible", timeout=CARD_TIMEOUT)
    assert "medical" in disclaimer.inner_text().lower()
```

- [ ] **Step 3: Run the E2E suite locally**

Run: `cd tests_e2e && python3 -m pytest test_lab_values_e2e.py -q` (E2E-Instanz muss
laufen; siehe `tests_e2e/pytest.ini` und `.github/workflows/e2e.yaml`)
Expected: alle Tests dieser Datei PASS (inkl. der drei neuen). Bricht ein Selector, ist die
`data-field`/`data-action`-Benennung aus Task 7 nicht eingehalten — Task 7 korrigieren,
nicht den Test.

- [ ] **Step 4: Regression (ohne E2E)**

Run: `python3 -m pytest -q`
Expected: all PASS (E2E wird von `pytest.ini` der Wurzel ausgeschlossen; nur die
Unit-/JS-Suite läuft).

- [ ] **Step 5: Commit**

```bash
git add tests_e2e/test_lab_values_e2e.py
git commit -m "test: cover lab report dialog and panel disclaimer in e2e"
```

---

### Task 12: Doku — README, `docs/CONCEPT-UI.md`, `docs/REQUIREMENTS.md`

**Files:**
- Modify: `README.md`
- Modify: `docs/CONCEPT-UI.md`
- Modify: `docs/REQUIREMENTS.md`

**Interfaces:**
- Consumes: die finalen Testergebnisse aus dem Final Integration Check (Testzahl,
  ruff-Status, E2E-Zahl) — dieser Task wird **zuletzt** ausgeführt.
- Produces: dokumentierter Service `add_lab_report` inkl. YAML-Beispiel, Hinweis auf
  Admin-Umrechnungsspalte und Panel-Hinweis, neue REQ-Kapitel als **erledigt** mit Belegen.

**Spec-Bezug:** §11 (Doku-Zeile), REQ-Akzeptanz (README-Beispiel, REQUIREMENTS-Status).

- [ ] **Step 1: README — Service-Beispiel ergänzen**

Im Abschnitt „Services: Laborwerte erfassen und korrigieren" (`README.md:522`) **vor**
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
- Leere Zeilen werden ignoriert; höchstens 200 befüllte Zeilen pro Aufruf; derselbe Marker
  darf im selben Bericht nur einmal vorkommen (Alias-Kollision zählt:
  `gpt` + `alt` → `duplicate_marker`).
- Der Aufruf ist **nicht** idempotent: zweimal gesendet = zweimal gespeichert (kein
  Dedupe). Korrektur über `remove_last_lab_value` / `void_entry` / `restore_entry`.
- Fehler nennen den Code mit Zeilenbezug, z. B. `unknown_marker: Zeile 3 (gptx)`.
````

- [ ] **Step 2: README — Admin + Panel ergänzen**

- Im Admin-Abschnitt (Labor-Referenzbereiche) einen Satz ergänzen: „Die Tabelle zeigt je
  Marker die **Umrechnung** (`mg/dL × 88,4 → µmol/L`, Faktor sprachabhängig formatiert)
  und markiert Marker mit Pflicht-Einheit (`Einheit Pflicht`)."
- Im Panel-Abschnitt (Labor-Tab) ergänzen: „Der Tab trägt einen kontextbezogenen
  Medizin-Hinweis; er ist bewusst immer sichtbar (kein Schalter)."
- Den Batch-Dialog erwähnen: „Laborbericht erfassen" (mehrere Zeilen, gemeinsamer
  Zeitpunkt/Berichts-Referenz) in Card und Panel.

- [ ] **Step 3: `docs/CONCEPT-UI.md`**

Nach §4.4 (Wohlbefinden) einen Abschnitt `### 4.4a Person-Detail — Tab „Laborwerte"`
einfügen (Struktur wie 4.2–4.4):

```markdown
### 4.4a Person-Detail — Tab „Laborwerte"

- **Kategorie-Leiste** mit Wischgeste; je Marker Wert, Badge, Sparkline, Zeitpunkt.
- **Medizin-Hinweis** oberhalb der Kategorie-Leiste, immer sichtbar (REQ-HOM-125).
- **Einzelwert-Formular** (`add_lab_value`) bleibt der schnelle Tagespfad.
- **„Laborbericht erfassen"**: Mehrzeilen-Dialog mit gemeinsamem Zeitpunkt und
  Berichts-Referenz, Alles-oder-nichts (REQ-HOM-123). Nach Erfolg bleiben `ts` und
  `report_ref` stehen, nur Werte und Zeilen werden geleert.
- **Admin/Settings:** Katalog-Tabelle mit Spalte „Umrechnung" (Alt-Einheit × Faktor →
  kanonisch, `formatNumber`) und Badge „Einheit Pflicht" (REQ-HOM-124).
```

- [ ] **Step 4: `docs/REQUIREMENTS.md`**

(a) In den vier REQ-Kapiteln (`REQ-HOM-123` ab Zeile 1246, `-124`, `-125`, `-126`):

- `**Status: Offen — geplant …**` → `**Status: Erledigt (2026-11-XX, Branch `feat/lab-batch-visibility`)**`
  (Datum = Abschlussdatum).
- Alle `- [ ]`-Akzeptanzkriterien → `- [x]`.
- `**Belege:**`-Zeile durch die tatsächlichen Testnamen + Zahlen ersetzen (aus dem Final
  Integration Check): z. B. `tests/test_logic.py::test_req_hom_123_validate_rows_*`,
  `tests/test_store.py::test_req_hom_123_add_lab_readings_rolls_back_on_save_error`,
  `tests/test_lab_services.py::test_req_hom_123_*`, `tests/test_ws_api.py::test_req_hom_123_*`,
  `tests/test_card_js.py::test_req_hom_123_*`, `tests/test_panel_js.py::test_req_hom_123_*`,
  `tests/test_dashboards.py::test_req_hom_126_*`, `tests_e2e/test_lab_values_e2e.py`;
  `pytest -q` → **<N> passed**; `ruff check .` + `ruff format --check .` clean;
  E2E **<M> passed**.

(b) Kopfzeile `**Stand:**` auf den Abschlussdatensatz umstellen (REQ-HOM-123…126
**umgesetzt**, Branch `feat/lab-batch-visibility`, noch kein Release) und die
`**REQ-HOM-123…126 geplant**`-Zeile (Zeile 20-23) durch einen
`**REQ-HOM-123…126 umgesetzt**`-Block ersetzen.

(c) Im „Changelog der Anforderungen" (Tabelle ab Zeile 1425) eine neue Zeile **oben**
einfügen:

```markdown
| 2026-11-XX | **REQ-HOM-123…126 umgesetzt — Laborwerte: Batch-Erfassung & Sichtbarkeit** (Branch `feat/lab-batch-visibility`, Spec `docs/superpowers/specs/2026-11-01-lab-values-batch-and-visibility-design.md`, Plan `docs/superpowers/plans/2026-11-01-lab-values-batch-and-visibility.md`): Service + WS-Kommando `add_lab_report` (ein `ts`/`report_ref`, Leerzeilen ignoriert, alles-oder-nichts, ein Store-Write/ein Audit `lab_values_added`, Rollback bei Save-Fehler), Mehrzeilen-Dialog in Card und Panel, Admin-Spalte „Umrechnung" + Badge „Einheit Pflicht" (Faktor via `formatNumber`, DE/EN), Panel-Medizin-Hinweis (immer sichtbar, ohne Settings/Admin-Abhängigkeit), Beispiel-Dashboard `examples/dashboard-labs-card.yaml` + `tests/test_dashboards.py`-Erweiterung. Kein neues Datenmodell (Store v5, `unique_id`s unverändert, Backup/Restore/CSV unberührt). **Belege:** `pytest -q` → **<N> passed**, E2E → **<M> passed**, ruff clean. **Kein Release/Tag in diesem Schritt.** |
```

- [ ] **Step 5: Verify no placeholder remains**

Run: `grep -n "<N>\|<M>\|2026-11-XX" docs/REQUIREMENTS.md`
Expected: keine Ausgabe (Datums- und Zahlen-Platzhalter sind vor dem Commit ersetzt).

- [ ] **Step 6: Regression**

Run: `python3 -m pytest tests/test_dashboards.py tests/test_translations.py -q && ruff check .`
Expected: grün/clean (Doku ändert keinen Code).

- [ ] **Step 7: Commit**

```bash
git add README.md docs/CONCEPT-UI.md docs/REQUIREMENTS.md
git commit -m "docs: document lab report batch capture and visibility"
```

---

## Dependency- & Parallelisierungs-Hinweise

### Sequenzielle Ketten (gleiche Datei oder harte Abhängigkeit)

| Kette | Grund |
|---|---|
| Task 1 → 4, 5 | Service/WS importieren `logic.validate_lab_report_rows` / `coerce_lab_number` |
| Task 2 → 4, 5 | Handler rufen `store.add_lab_readings` |
| Task 3 → 4 | `_SERVICE_NAMES`/Registrierung und YAML-Metadaten gehören zum selben Service; Task 4 setzt den Handler voraus, Task 3 die Deklaration |
| Task 5 → 6, 7 | UI sendet das WS-Kommando; ohne Handler ist der Dialog nicht Ende-zu-Ende prüfbar |
| Task 6 → 7 (nur `strings.json`/translations/test_translations.py) | Beide erweitern `_REQ_HOM_122_UI_KEYS`; Task 7 bringt die Panel-i18n-Keys, Task 6 keine (Card ist hartkodiert deutsch) |
| Task 7 → 8 | Beide editieren `labsTab`/`panel-base.js` (Task 8 fügt Disclaimer + CSS hinzu) |
| Task 8 → 9 (nur i18n-Dreiklang) | `strings.json` + `de`/`en` + `_REQ_HOM_122_UI_KEYS` sind gemeinsame Engpässe |
| Task 10 → Final | Beispiel-Dashboard ist unabhängig, aber README-Änderung kollidiert mit Task 12 (deshalb vor Task 12) |
| Task 11 → 12 | E2E-Zahlen fließen in die REQUIREMENTS-Belege |

**Regel:** `strings.json`, `translations/de.json`, `translations/en.json` und
`tests/test_translations.py` werden in Tasks **3, 7, 8, 9** berührt — diese vier Tasks
niemals parallel starten, sondern in Wellenreihenfolge committen.

### Parallelisierbar (disjunkte Dateien)

| Parallel | Bedingung |
|---|---|
| **Task 1 ‖ Task 2** | `logic.py` vs. `store.py`; Task 2 importiert nichts aus Task 1 |
| **Task 5 ‖ Task 10** | `ws_api.py` vs. `examples/`+`test_dashboards.py`; Task 10 ist von der gesamten Batch-Kette unabhängig |
| **Task 9 ‖ Task 11** | `panel-admin.js` (+i18n) vs. `tests_e2e/`; Task 9 braucht Task 5 nicht, Task 11 schon |
| **Task 6 ‖ Task 5** | nur wenn der Node-/Statik-Test des Dialogs noch nicht gegen den Server laufen muss — empfohlen ist sequenziell (Task 5 zuerst), weil Task 11 den echten Pfad prüft |

**Nicht parallel:** Task 6 ‖ Task 7 (beide definieren dieselbe Fehlercode-Tabelle; der
Paritätstest in Task 7 setzt `LAB_ERROR_TEXT` der Karte voraus), Task 8 ‖ Task 9
(i18n-Dreiklang), Task 4 ‖ Task 5 (beide hängen an Task 1/2, unterschiedliche Dateien —
formal parallel möglich, aber die Fehlersemantik wird zuerst im Service gepinnt; WS kopiert
sie nur).

---

## Final Integration Check

- [ ] **Volle Unit-/JS-Suite:** `python3 -m pytest -q` — alle bestehenden Tests plus
  `test_req_hom_123_*`/`124_*`/`125_*`/`126_*` grün, keine Regression. Testzahl notieren
  (für Task 12).
- [ ] **Lint/Format:** `ruff check .` und `ruff format --check .` — clean (Projekt nutzt
  `line-length = 100`, `docs/` ist ausgenommen).
- [ ] **Compile-Check:** `python3 -m compileall -q custom_components/health_o_mat`.
- [ ] **E2E:** `cd tests_e2e && python3 -m pytest -q` gegen die geteilte Instanz
  (`/home/hermes/ha-test`): 3 neue Tests grün; E2E-Zahl notieren.
- [ ] **hassfest/HACS:** `validate.yml` läuft bei Push/PR — keine neuen Fehler. Lokal
  optional `/home/hermes/ha-test/bin/ha core check` (Dev-Instanz) nach
  `/home/hermes/ha-test/bin/sync /home/hermes/repos/ha-health-o-mat`.
- [ ] **Manuelle Prüfung der vier Punkte** auf der Dev-Instanz
  (`http://127.0.0.1:8123`, `bin/sync <repo>`):
  1. **Batch:** YAML-Beispiel aus §2.10 der Spec als Service aufrufen → `lab_readings`
     wächst um 4, alle mit demselben `ts`/`report_ref`, genau **ein** Audit-Eintrag
     `lab_values_added`; derselbe Aufruf über `POST /api/services/health_o_mat/add_lab_report`
     funktioniert ebenfalls.
  2. **Alles-oder-nichts:** Zeile mit `gptx` → `ServiceValidationError` mit
     `unknown_marker: Zeile 3 (gptx)`, Lesungen/Audit unverändert; Dialog in Card **und**
     Panel: zwei Zeilen speichern, `ts`/`report_ref` bleiben nach Erfolg stehen, Fehler
     behält alle Eingaben.
  3. **Admin:** Katalog-Tabelle zeigt `mg/dL × 88,4 → µmol/L` (DE) bzw. `88.4` (EN),
     `—` bei Markern ohne Alt-Einheit, Badge „Einheit Pflicht" bei
     `urine_protein_creatinine_ratio`; kein neuer WS-Request im Netzwerk-Panel.
  4. **Panel-Hinweis:** frisch geöffnete Panel-Session → Lab-Tab zeigt den Hinweis
     (auch ohne Admin-Settings-Load); `.labs-disclaimer` ist im Panel-Stylesheet, die
     Karte ist unverändert.
- [ ] **Doku-Check:** `README.md` listet `examples/dashboard-labs-card.yaml`;
  `docs/REQUIREMENTS.md` REQ-HOM-123…126 sind `[x]` mit Belegen; keine
  `<N>`/`<M>`/`2026-11-XX`-Platzhalter mehr (`grep` aus Task 12 Step 5).
- [ ] **Kein Release in diesem Plan:** Version-Bump (`manifest.json` + alle
  `?v=`-Cache-Buster), Tag und GitHub-Release (Release-Dreiklang) sind **nicht** Teil
  dieses Plans. Sie laufen als eigener, nachgelagerter Schritt über den `release`-Agenten,
  sobald der Branch nach `main` gemerged und der HACS-Update-Test möglich ist
  (`.claude/rules/integration-development.md`, Schritte 6–7). Bis dahin bleibt
  `manifest.version` auf `0.16.1`.

---

*(End of plan.)*

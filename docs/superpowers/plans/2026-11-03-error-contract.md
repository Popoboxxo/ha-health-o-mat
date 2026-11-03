---
pipeline_stages:
  implement: 1
---

# Fehlercode-/i18n-Vertrag (REQ-HOM-127, WP-A) Implementation Plan
> Status: geplant

**Goal:** Alle 29 fachlichen Service-Exception-Stellen (`__init__.py`) und alle 32
migrierbaren `send_error`-Stellen (`ws_api.py`) liefern ihren Fehler als **Code +
Params** über HA-native Übersetzungsfelder (`translation_domain`/`translation_key`/
`translation_placeholders`), der Labor-Batch behält unverändert
`{code, params, message}` — mit einem Katalog von **35 Codes**, de/en-Texten in
`strings.json`/`translations/{de,en}.json` und Frontend-Parsern, die
`translation_key || code` vor `message` auswerten. Kein neuer Pflicht-Key, keine
Änderung an `unique_id`, Store-Schema oder REQ-HOM-132-Kontrakten.

**Architecture:** **Ein** HA-freier Katalog (`logic.ERROR_SPECS` +
`logic.build_error`) ist die einzige Quelle; drei dünne Projektionen zeigen
darauf: Service-Exception (`errors.validation_error`), WS-Fehler
(`errors.send_ws_error`, Fachcode in `translation_key`, HAs Transportcode
unverändert in `code`) und Batch-Envelope (`logic.lab_report_error`, Form
unverändert). `code == translation_key` **immer**; `params` bleiben typisiert,
nur die HA-Projektion stringifiziert (`{k: str(v)}`). `message` wird
ausschließlich aus dem per-Code-Template gerendert (sprachneutral, ASCII), nie
durch freie Interpolation. `errors.py` importiert nur
`homeassistant.exceptions` + `logic` (kein Zyklus mit `__init__`), und
`send_ws_error` ist signatur-fail-open (3-Arg-Fallback ohne
`translation_*`-Kwargs).

**Tech Stack:** Python 3.13 / Home Assistant Custom Component (`ServiceValidationError`
mit `translation_*`, `ActiveConnection.send_error` mit `translation_*`), pytest mit
der Fake-HA-Technik aus `tests/conftest.py`, Node 22 (Text-/Subprozess-Assertions
der `www/*.js`), Playwright-E2E gegen die geteilte Instanz (`hass.language = en`).

**Spec:** docs/superpowers/specs/2026-11-03-error-contract-design.md
(APPROVED 2026-11-03, concept-reviewer) — **verbindlich**; dieser Plan setzt
§5–§11 um.

**Plan-Rolle:** Die Rolle `planner` ist in diesem Projekt **nicht aktiv**
(`docs/PLAN-BACKLOG-2026-11-02.md:387-393`); dokumentierter Fallback ist
`documenter` (`docs/PLAN-AUDIT-2026-11-03.md` §10 / **D-4**, `:174` und `:690`).
Dieser Plan wurde in dieser Fallback-Rolle geschrieben; `pipeline_stages.implement: 1`
verweist auf **Task 1** als ersten Implementierungs-Task.

**REQ:** **REQ-HOM-127** (`docs/REQUIREMENTS.md:1577-1600`), Rahmen **WP-A**
(`docs/PLAN-AUDIT-2026-11-03.md:72-175`), Entscheidungen **D-3** (Transport) und
**D-4** (Planrolle).

---

## Anker-Status (re-anchored gegen `ef0405f`)

Das Konzept wurde bei `main@79349db` geschrieben; der Baum steht heute auf
`ef0405f` (Mess-Notiz, IO-/Diagnostics-Härtungen). **Jede** hier genutzte
Zeilenangabe wurde gegen `ef0405f` nachgeprüft:

| Bereich | Ergebnis |
|---|---|
| `__init__.py` §7.1-WT-Spalte (alle 29 + 3 T-Stellen) | **driftfrei** — die „WT"-Werte des Konzepts sind die heutigen Zeilen; nur die historische Spalte `79349db` (`→`-linke Seite) ist überholt |
| `ws_api.py` §7.2/§7.3 | **driftfrei** — 42 Texttreffer auf `send_error`, davon 2 Docstrings (`:1584`, `:1657`) = **40 Aufrufe** |
| `logic.py` (`:160`, `:1184`, `:1195`) | **driftfrei** |
| `www/*.js`, `tests/*.py` | Angaben des Konzepts `:615` (ASCII) und `:117` (Placeholders) übernommen; die *Frontend*-Zeilen des Konzepts (§7.5) waren teils ungenau und sind hier durch gemessene Zeilen ersetzt (siehe Task 6) |

Kritische, hier verwendete Zeilen: `__init__.py:1048/1052/1059/1141/1198/1203/1215/1234/1284/1291/1294/1298/1320/1337/1350/1364/1380/1384/1399/1411/1415/1419/1444/1452/1463/1483/1493/1597/1608` (29 migriert) · `:1169/1172/1570` (3 `T`) · `:1409`/`:1416` (`len(allowed)` = `len(WELLBEING_STATES)`) · `ws_api.py:802/1280/1889/1930` (4 `T`) · `:2212/2295/2381/2404` (4 Relais) · `:1646` (Batch-Builder) · `:1673/1680/1694/1727/1741` (5 Batch-Stellen) · `:885` (`parse_entry_ts`) · `:2047-2059` (`parse_settings_message`) · `logic.py:160/1184/1195` · `const.py:115` · `tests/conftest.py:362-366` · `tests/test_ws_api.py:129` (`FakeConnection.send_error`) · `tests/test_translations.py:75/372` · `tests_e2e/test_lab_values_e2e.py:757-762`.

## Global Constraints

- `code` ist die Identität: snake_case, stabil, **nie umbenennen**. `translation_key == code`
  an jeder Service-/WS-Stelle — per Test erzwungen.
- `code` des WS-Envelopes bleibt **HAs Transportcode** (`invalid_format`, `not_found`,
  `unauthorized`, `export_failed`, …). Kein Overload mit dem Fachcode.
- Batch-Envelope bleibt `{"ok": false, "error": {code, params, message}}` — **ohne**
  `translation_*` (REQ-HOM-123 §2.4, REQ-HOM-132).
- `message` ist immer nicht-leer, sprachneutral, aus dem per-Code-Template; `{value}`
  **nur** bei `invalid_ts`; `invalid_value.value` wird in **keinem** Text gerendert.
- `params`-Whitelist pro Code (Katalog unten). Keine Store-Werte, keine
  Personennamen, keine Notiz-/Freitextfelder. Roh-Echo nur für
  `RAW_ECHO_CODES = frozenset({"invalid_ts", "invalid_value"})`, ≤ 64 Zeichen.
- `row`/`first_row` erscheinen **nur** in `params`, **nicht** in Texten (HA ersetzt
  gelieferte Platzhalter; ein nicht gelieferter Platzhalter bliebe literal stehen —
  der Service-Pfad hat keine Zeile). Die Zeilenangabe für die Labs-UI liefert der
  neue `common`-Key `ui_panel_lab_report_row_hint`.
- `unique_id`, `manifest.version`, `ConfigFlow.VERSION`, `STORE_SCHEMA_VERSION`
  bleiben in **allen** Tasks unverändert. Kein Migrator.
- `REQ-HOM-132` unverändert: exakte Key-Mengen der fünf Verwaltungs-Services,
  `errors` ≤ 20, Fachfehler bleiben Exceptions.
- `from __future__ import annotations` + vollständige Type-Hints in jeder berührten
  Python-Datei. Code/Kommentare/Tests/Commits **Englisch**, Plan/Prosa Deutsch.
- Conventional Commits, Englisch, Imperativ, erste Zeile ≤ 72 Zeichen, **keine
  führende UTF-8-BOM**. Die Commit-Nachricht steht in jedem Task.
- Nach jedem Task: `python3 -m pytest -q` sowie `ruff check .` und
  `ruff format --check .` grün; zusätzlich `python3 -m compileall -q custom_components/health_o_mat`.
- Nach jedem `__init__.py`/`ws_api.py`-Task: `python3 -m compileall` + Import-Smoke,
  weil ein Syntaxfehler in einer Plattform-Datei die **ganze** Integration killt.
- Testinstanz-Etikette: nur die eigene Domain syncen
  (`/home/hermes/ha-test/bin/sync <repo-dir>`), **kein** `bin/reset`, **kein**
  Sprachwechsel der Instanz (`hass.language` bleibt `en`), Tokens nie kopieren.
- Release-Schnitt: **0.21.0, MINOR + 💥** (Fehlertexte ändern sich). Kein
  Version-Bump in diesem Plan — das macht `release`.

## File Structure

- Modify: `custom_components/health_o_mat/logic.py` — Katalog `ERROR_SPECS`,
  `RAW_ECHO_CODES`, `build_error`, `lab_report_error` delegiert; `_LAB_ROW_ERROR_CODES`
  geht im Katalog auf; `ENTRY_TS_INVALID_MESSAGE` wird **in Task 4** gelöscht.
- Create: `custom_components/health_o_mat/errors.py` — HA-Adapter
  `validation_error`, `send_ws_error`, `relay_error`.
- Modify: `custom_components/health_o_mat/__init__.py` — 29 Service-Stellen.
- Modify: `custom_components/health_o_mat/ws_api.py` — 32 `send_error`-Stellen,
  4 Relais-Stellen, `parse_settings_message`, `parse_entry_ts`.
- Modify: `custom_components/health_o_mat/strings.json` — `exceptions`-Sektion
  (englischer Master) + `common.ui_panel_lab_report_row_hint`.
- Modify: `custom_components/health_o_mat/translations/en.json` — dito (Fallback,
  vollständig).
- Modify: `custom_components/health_o_mat/translations/de.json` — deutsche Texte.
- Modify: `custom_components/health_o_mat/www/health-o-mat-i18n.js` — zweite
  Ressourcen-Kategorie `exceptions`, `tError`, `loadExceptionTranslations`,
  `resetUiTranslations` erweitert.
- Modify: `custom_components/health_o_mat/www/health-o-mat-card.js` — eigener
  Inline-Loader für `exceptions`, neues `_errorText(err)`, 11 Anzeigestellen.
- Modify: `custom_components/health_o_mat/www/health-o-mat-labs-card.js` —
  `errorMessage()`, `resultError()`, `reportErrorMessage()`.
- Modify: `custom_components/health_o_mat/www/health-o-mat-panel-base.js` —
  `setUiErrorTranslator`, `wsErrorText` lokalisiert, `rowHint`.
- Modify: `custom_components/health_o_mat/www/health-o-mat-panel-views.js` —
  `resultError()` + Zeilen-Hinweis.
- Modify: `custom_components/health_o_mat/www/health-o-mat-panel.js` —
  `setUiErrorTranslator(uiErrorTranslate)` verdrahten.
- Modify: `tests/conftest.py` — Fake-`HomeAssistantError`/`ServiceValidationError`
  akzeptiert und speichert `translation_*`-Kwargs.
- Modify: `tests/test_ws_api.py` — `FakeConnection.send_error(**kwargs)` +
  `error_kwargs`-Liste; 48 bestehende `connection.errors`-Assertions bleiben.
- Create: `tests/test_error_contract.py` — Katalogtests (HA-frei).
- Create: `tests/test_errors.py` — HA-Adaptertests (Fake-HA-Technik).
- Modify: `tests/test_logic.py` — Batch-`message`-Assertions (7 Stellen).
- Modify: `tests/test_lab_services.py` — Service-Stellen + `message`-Assertions.
- Modify: `tests/test_wave_a.py` — Service-Stellen (Personenauflösung, Undo, Trinken).
- Modify: `tests/test_import_backup.py` — REQ-HOM-132-Regression unverändert grün.
- Modify: `tests/test_translations.py` — kataloggetriebene i18n-Parität + Guards.
- Modify: `tests/test_card_js.py`, `tests/test_panel_js.py` — Fehleranzeige-Parser.
- Modify: `tests_e2e/test_i18n_e2e.py` — repräsentativer Fehlerpfad, de/en.
- Modify: `tests_e2e/test_lab_values_e2e.py` — gerenderte Batch-Meldung.
- Modify: `docs/SERVICE-RESPONSES.md` — Transport gemäß D-3.
- Modify: `docs/REQUIREMENTS.md` — REQ-HOM-127-AKs (via `requirements`).

## Task-Abhängigkeiten

```
Task 1 ──┬── Task 2 ── Task 3 ── Task 4 ──┬── Task 6 ── Task 7 ── Task 8
         │                                │
         └───────── Task 5 ───────────────┘
```

- **Task 1 → Task 2 → Task 3 → Task 4** sind **strikt sequenziell**:
  Task 4 löscht `logic.ENTRY_TS_INVALID_MESSAGE`, dessen letzten beiden Konsumenten
  Task 3 (`__init__.py:1141`) und Task 4 (`ws_api.py:885`) entfernen; Task 3 und 4
  teilen sich den Katalog aus Task 1 und den Adapter aus Task 2.
- **Task 5** (Übersetzungen) braucht nur Task 1 (Katalog) und darf parallel zu
  Task 3/4 laufen, ist aber dateidisjunkt.
- **Task 6** braucht Task 4 (Drahtformat) **und** Task 5 (Textschlüssel).
- **Task 7** (E2E) braucht Task 4 + Task 6. **Task 8** ist Dokumentation und läuft
  zuletzt.
- Zwischen Task 4 und Task 6 ist der Baum **nicht releasefähig** (Backend spricht
  neutral, Frontend parst noch deutsche Prosatexte). Der Schnitt ist ein
  zusammenhängender Release (0.21.0); die Tasks dürfen einzeln committet, aber nur
  gemeinsam ausgeliefert werden.

---

## Katalog (verbindlich, ein einziger Ort: `logic.ERROR_SPECS`)

Typ:

```python
ERROR_SPECS: dict[str, dict[str, Any]] = {code: {"params": tuple[str, ...],
                                                 "template": str,
                                                 "row_template": str | None}}
RAW_ECHO_CODES: frozenset[str] = frozenset({"invalid_ts", "invalid_value"})
```

Rendering-Regel (`logic.build_error`):
`row_template` wird genutzt, **wenn** `"row"` in `params` enthalten ist, sonst
`template`; fehlende deklarierte Params werden als `-` eingesetzt (nur optional
deklarierte können fehlen). `value` wird bei Codes außerhalb `RAW_ECHO_CODES`
verworfen, Roh-Echo-Werte werden auf 64 Zeichen gekürzt. `params`-Schlüssel
außerhalb von `spec["params"]` werden **entfernt** (Whitelist).

### A - Codes, Params, Templates (ASCII, sprachneutral)

| # | Code | params (`*` = optional) | template | row_template |
|---|---|---|---|---|
| 1 | `no_person_configured` | - | `no_person_configured` | - |
| 2 | `person_ambiguous` | `count` | `person_ambiguous (count={count})` | - |
| 3 | `person_not_found` | - | `person_not_found` | - |
| 4 | `invalid_ts` | `value` | `invalid_ts (value={value})` | - |
| 5 | `invalid_history_kind` | `kind`, `allowed` | `invalid_history_kind (kind={kind}, allowed={allowed})` | - |
| 6 | `missing_item_id` | - | `missing_item_id` | - |
| 7 | `entry_not_found` | `kind` | `entry_not_found (kind={kind})` | - |
| 8 | `invalid_undo_kind` | `kind`, `allowed` | `invalid_undo_kind (kind={kind}, allowed={allowed})` | - |
| 9 | `undo_not_supported` | `kind`, `allowed` | `undo_not_supported (kind={kind}, allowed={allowed})` | - |
| 10 | `nothing_to_remove` | `kind` | `nothing_to_remove (kind={kind})` | - |
| 11 | `limit_out_of_range` | `min`, `max` | `limit_out_of_range (min={min}, max={max})` | - |
| 12 | `offset_invalid` | - | `offset_invalid` | - |
| 13 | `invalid_since` | `expected` | `invalid_since (expected={expected})` | - |
| 14 | `amount_out_of_range` | `min`, `max` | `amount_out_of_range (min={min}, max={max})` | - |
| 15 | `bp_out_of_range` | `min`, `max` | `bp_out_of_range (min={min}, max={max})` | - |
| 16 | `wellbeing_target_missing` | `max` | `wellbeing_target_missing (max={max})` | - |
| 17 | `wellbeing_score_invalid` | `min`, `max` | `wellbeing_score_invalid (min={min}, max={max})` | - |
| 18 | `wellbeing_key_unknown` | `allowed` | `wellbeing_key_unknown (allowed={allowed})` | - |
| 19 | `unknown_marker` | `row*`, `marker` | `unknown_marker (marker={marker})` | `unknown_marker (row={row}, marker={marker})` |
| 20 | `unit_required` | `row*`, `marker` | `unit_required (marker={marker})` | `unit_required (row={row}, marker={marker})` |
| 21 | `invalid_value` | `row*`, `marker`, `value*` | `invalid_value (marker={marker})` | `invalid_value (row={row}, marker={marker})` |
| 22 | `unsupported_unit` | `row*`, `marker`, `unit` | `unsupported_unit (marker={marker}, unit={unit})` | `unsupported_unit (row={row}, marker={marker}, unit={unit})` |
| 23 | `duplicate_marker` | `row*`, `marker`, `first_row*` | `duplicate_marker (marker={marker})` | `duplicate_marker (row={row}, marker={marker}, first_row={first_row})` |
| 24 | `empty_report` | - | `empty_report` | - |
| 25 | `too_many_rows` | `count`, `limit` | `too_many_rows (count={count}, limit={limit})` | - |
| 26 | `no_active_report` | `ts` | `no_active_report (ts={ts})` | - |
| 27 | `no_active_value` | `marker` | `no_active_value (marker={marker})` | - |
| 28 | `invalid_setting` | `field` | `invalid_setting (field={field})` | - |
| 29 | `unknown_dataset` | `allowed` | `unknown_dataset (allowed={allowed})` | - |
| 30 | `confirm_mismatch` | - | `confirm_mismatch` | - |
| 31 | `invalid_import_source` | - | `invalid_import_source` | - |
| 32 | `content_not_utf8` | - | `content_not_utf8` | - |
| 33 | `content_too_large` | `max` | `content_too_large (max={max})` | - |
| 34 | `config_flow_unavailable` | - | `config_flow_unavailable` | - |
| 35 | `config_flow_failed` | - | `config_flow_failed` | - |

`config_flow_failed` trägt **keine** Roh-Exception: `ws_api.py:2244` loggt sie
bereits (`_LOGGER.exception`), `message`/`params` bleiben frei davon (§14).

### B — Übersetzungstexte (`exceptions.<code>.message`)

Platzhalter-Menge je Code ist in `strings.json`, `translations/de.json` und
`translations/en.json` **identisch** (§9.2 Regel 5). Keine einfachen
Anführungszeichen um Platzhalter (hassfest). Kein `{row}`/`{first_row}`.

| Code | en (`strings.json` = `translations/en.json`) | de (`translations/de.json`) |
|---|---|---|
| `no_person_configured` | No Health-O-Mat person is set up. | Keine Health-O-Mat-Person eingerichtet. |
| `person_ambiguous` | Several people are set up. Select one of them. | Mehrere Personen sind eingerichtet. Bitte eine davon auswählen. |
| `person_not_found` | This person is not set up. | Diese Person ist nicht eingerichtet. |
| `invalid_ts` | Invalid timestamp {value}. Expected ISO 8601, at most 5 minutes in the future and not before 1900. | Ungültiger Zeitpunkt {value}. Erwartet ISO 8601, höchstens 5 Minuten in der Zukunft und nicht vor 1900. |
| `invalid_history_kind` | Unknown type {kind}. Allowed: {allowed}. | Unbekannter Typ {kind}. Erlaubt: {allowed}. |
| `missing_item_id` | The entry to change is missing an id. | Beim zu ändernden Eintrag fehlt die id. |
| `entry_not_found` | The entry was not found or is already in the requested state. | Der Eintrag wurde nicht gefunden oder ist bereits im gewünschten Zustand. |
| `invalid_undo_kind` | Undo is not available for type {kind}. Allowed: {allowed}. | Für den Typ {kind} gibt es kein Rückgängig. Erlaubt: {allowed}. |
| `undo_not_supported` | Undo is not available for {kind}. | Rückgängig ist für {kind} nicht verfügbar. |
| `nothing_to_remove` | There is nothing to remove for {kind}. | Für {kind} gibt es nichts zu entfernen. |
| `limit_out_of_range` | Limit must be between {min} and {max}. | Das Limit muss zwischen {min} und {max} liegen. |
| `offset_invalid` | Offset must be 0 or greater. | Der Offset muss 0 oder größer sein. |
| `invalid_since` | Since must be an ISO 8601 timestamp. | Since muss ein ISO-8601-Zeitpunkt sein. |
| `amount_out_of_range` | Amount must be between {min} and {max} ml. | Die Menge muss zwischen {min} und {max} ml liegen. |
| `bp_out_of_range` | Systolic and diastolic must be between {min} and {max}. | Systolisch und diastolisch müssen zwischen {min} und {max} liegen. |
| `wellbeing_target_missing` | Provide either a status or a score between 1 and {max}. | Bitte entweder einen Status oder einen Score zwischen 1 und {max} angeben. |
| `wellbeing_score_invalid` | The score must be between {min} and {max}. | Der Score muss zwischen {min} und {max} liegen. |
| `wellbeing_key_unknown` | Unknown wellbeing status. Allowed: {allowed}. | Unbekannter Wohlbefinden-Status. Erlaubt: {allowed}. |
| `unknown_marker` | Unknown marker {marker}. | Unbekannter Marker {marker}. |
| `unit_required` | A unit is required for marker {marker}. | Für den Marker {marker} ist eine Einheit erforderlich. |
| `invalid_value` | The value for marker {marker} is not a valid number. | Der Wert für den Marker {marker} ist keine gültige Zahl. |
| `unsupported_unit` | Unit {unit} is not supported for marker {marker}. | Die Einheit {unit} wird für den Marker {marker} nicht unterstützt. |
| `duplicate_marker` | Marker {marker} appears more than once in this report. | Der Marker {marker} kommt in diesem Bericht mehrfach vor. |
| `empty_report` | The report has no values. | Der Bericht enthält keine Werte. |
| `too_many_rows` | The report has {count} rows; at most {limit} are allowed. | Der Bericht hat {count} Zeilen; höchstens {limit} sind erlaubt. |
| `no_active_report` | There is no active report at this time. | Zu diesem Zeitpunkt gibt es keinen aktiven Bericht. |
| `no_active_value` | There is no active value for marker {marker}. | Für den Marker {marker} gibt es keinen aktiven Wert. |
| `invalid_setting` | Invalid setting {field}. | Ungültige Einstellung {field}. |
| `unknown_dataset` | Unknown dataset. Allowed: {allowed}. | Unbekannter Datensatz. Erlaubt: {allowed}. |
| `confirm_mismatch` | The confirmation does not match the person key. | Die Bestätigung stimmt nicht mit dem Personen-Schlüssel überein. |
| `invalid_import_source` | Provide exactly one of filename or content. | Genau eines von filename oder content angeben. |
| `content_not_utf8` | The content is not valid UTF-8. | Der Inhalt ist kein gültiges UTF-8. |
| `content_too_large` | The content exceeds {max} bytes. | Der Inhalt überschreitet {max} Bytes. |
| `config_flow_unavailable` | This Home Assistant version cannot start a config flow. | Diese Home-Assistant-Version kann keinen Einrichtungsdialog starten. |
| `config_flow_failed` | The config flow could not be started. | Der Einrichtungsdialog konnte nicht gestartet werden. |

---

### Task 1: Katalog und `build_error` in `logic.py`

**Agent:** senior-developer
**Depends on:** none

**Files:**
- Modify: `custom_components/health_o_mat/logic.py` — `ERROR_SPECS`,
  `RAW_ECHO_CODES`, `build_error`, `lab_report_error` (Delegation),
  `_LAB_ROW_ERROR_CODES` (geht auf), `__all__`-Nähe der `lab_report_error`-Sektion
  (`logic.py:1182-1218`).
- Create: `tests/test_error_contract.py` — Katalogtests, **HA-frei** (importiert
  `logic` direkt; `logic` importiert selbst kein `homeassistant`, nur
  `const`/`parser`).
- Modify: `tests/test_logic.py` — die sieben Batch-`message`-Assertions
  (`:1749`, `:1755`, `:1878`, `:1892`, `:1907`, `:1941`, `:1956`).

**Interfaces:**
- Produces:
  - `logic.ERROR_SPECS: dict[str, dict[str, Any]]` — 35 Codes, Typ
    `{"params": tuple[str, ...], "template": str, "row_template": str | None}`.
  - `logic.RAW_ECHO_CODES: frozenset[str]` = `{"invalid_ts", "invalid_value"}`.
  - `logic.build_error(code: str, params: Mapping[str, Any] | None = None) -> dict[str, Any]`
    — Rückgabe `{"code": str, "params": dict[str, str | int | bool | None],
    "message": str}`; unbekannter Code → `params == {}`, `message == code` (nie
    leer); Whitelist + 64-Zeichen-Kürzung + Roh-Echo-Regel.
  - `logic.lab_report_error(code, params=None) -> dict` — **unverändert** in
    Signatur und Vertrag, delegiert an `build_error`.
- Consumes:
  - `logic.WELLBEING_STATES` (Re-Export aus `const.py:115`) als Quelle für
    `wellbeing_target_missing.params.max` — der **Katalog** trägt den Param, den
    **Wert** setzt der Aufrufer (Task 3/4) aus `len(allowed)`.
  - `logic.ENTRY_TS_INVALID_MESSAGE` (`logic.py:160`) bleibt in diesem Task
    **bestehen** (Konsumenten: `__init__.py:1141`, `ws_api.py:885`) und wird erst in
    Task 4 gelöscht.

**Steps:**
- [ ] **Step 1: Test schreiben (fail)** — `tests/test_error_contract.py`:
  - `test_catalog_has_35_unique_snake_case_codes` — `len(ERROR_SPECS) == 35`, jeder
    Code matcht `^[a-z][a-z0-9_]*$`.
  - `test_catalog_params_are_declared_tuples` — `params` ist ein `tuple[str, ...]`,
    jeder Name matcht `^[a-z][a-z0-9_]*$`.
  - `test_message_template_is_ascii` — **Review-Auflage 2**: nur
    `spec["template"]` und `spec["row_template"]` werden geprüft
    (`template.encode("ascii")` darf nicht werfen), **nicht** der gerenderte
    String; zusätzlich kein Umlaut/`ß` im Template.
  - `test_message_template_placeholders_are_declared` — jede `{...}`-Referenz in
    `template`/`row_template` steht in `spec["params"]`; jedes `row_template`
    deklariert `row`.
  - `test_message_template_value_scope` — `{value}` kommt **nur** in
    `ERROR_SPECS["invalid_ts"]["template"]` vor; kein anderes Template enthält
    `value`.
  - `test_build_error_returns_all_three_fields` — für **alle** 35 Codes:
    `set(result) == {"code", "params", "message"}`, `message` nicht leer,
    `result["code"] == code`.
  - `test_build_error_uses_row_template_when_row_present` —
    `build_error("unknown_marker", {"row": 3, "marker": "kreatinin"})["message"] ==
    "unknown_marker (row=3, marker=kreatinin)"`; ohne `row` ==
    `"unknown_marker (marker=kreatinin)"`.
  - `test_build_error_unknown_code_falls_back_to_code` —
    `build_error("does_not_exist", {"x": 1})` → `code == "does_not_exist"`,
    `params == {}`, `message == "does_not_exist"`.
  - `test_error_contract_no_pii_params` — kein `params`-Schlüssel heißt
    `person`/`note`/`comment`/`name`; `value` tritt nur bei Codes aus
    `RAW_ECHO_CODES` auf; jeder andere Schlüssel steht in `spec["params"]`.
  - `test_raw_echo_truncated_to_64_chars` —
    `build_error("invalid_ts", {"value": "x" * 200})["params"]["value"]` hat
    `len(...) == 64`.
  - `test_params_stringified_projection` — `{k: str(v) for k, v in
    result["params"].items()}` liefert nur `str` (Review-Auflage 1, Grundlage für
    §5.2:117).
  - `test_lab_report_error_delegates_to_build_error` — `lab_report_error("unknown_marker",
    {"row": 3, "marker": "gptx"}) == build_error("unknown_marker", {"row": 3,
    "marker": "gptx"})`.
  - `tests/test_logic.py`: die sieben `message`-Assertions auf die neutralen
    Templates umstellen (`:1749` → `"unknown_marker (row=3, marker=kreatinin)"`,
    `:1755` → `"duplicate_marker (row=2, marker=gpt, first_row=1)"`, `:1878`,
    `:1892` → `"unknown_marker (row=1, marker=-)"`, `:1907`, `:1941`, `:1956`).
  Alle Tests scheitern vor der Implementierung mit `KeyError`/`AttributeError`.
- [ ] **Step 2: implementieren** — `ERROR_SPECS`/`RAW_ECHO_CODES`/`build_error` in
  der Laborbericht-Sektion von `logic.py` (vor `lab_report_error`); `lab_report_error`
  wird zum Delegator (`return build_error(code, params)`); `_LAB_ROW_ERROR_CODES`
  wird gelöscht (der Katalog deklariert `row` je Code); `ENTRY_TS_INVALID_MESSAGE`
  bleibt.
- [ ] **Step 3: Test (pass)** — `python3 -m pytest -q tests/test_error_contract.py
  tests/test_logic.py`; danach `python3 -m pytest -q`, `ruff check .`,
  `ruff format --check .`.
- [ ] **Step 4: commit** — `feat(logic): add the error catalog and build_error`

---

### Task 2: HA-Adaptermodul `errors.py` (+ Test-Fakes für `translation_*`)

**Agent:** senior-developer
**Depends on:** Task 1

**Files:**
- Create: `custom_components/health_o_mat/errors.py`.
- Modify: `tests/conftest.py` — Fake-`HomeAssistantError` (`:362`) und
  `ServiceValidationError` (`:365`) nehmen `translation_domain`,
  `translation_key`, `translation_placeholders` als Keyword-Argumente an und
  speichern sie als Attribute.
- Modify: `tests/test_ws_api.py` — `FakeConnection.send_error` (`:129`) bekommt
  `**kwargs` und zeichnet sie in einer **neuen** Liste `self.error_kwargs` auf;
  `self.errors` bleibt eine 3-Tupel-Liste (48 bestehende Assertions bleiben gültig).
- Create: `tests/test_errors.py` — Adaptertests mit der Fake-HA-Technik.

**Interfaces:**
- Produces:
  - `errors.validation_error(code: str, params: Mapping[str, Any] | None = None) -> ServiceValidationError`
    — `ServiceValidationError(build_error(...)["message"], translation_domain="health_o_mat",
    translation_key=code, translation_placeholders={k: str(v) for k, v in params.items()})`.
  - `errors.send_ws_error(connection: Any, msg_id: Any, ha_code: str, code: str,
    params: Mapping[str, Any] | None = None) -> None` — ruft
    `connection.send_error(msg_id, ha_code, message, translation_domain="health_o_mat",
    translation_key=code, translation_placeholders=...)`; **signatur-fail-open**:
    fehlt `translation_domain` in `inspect.signature(connection.send_error).parameters`
    (oder wirft der Aufruf `TypeError`), wird `connection.send_error(msg_id, ha_code, message)`
    ohne Kwargs gesendet (`TRANSLATION_KWARGS_SUPPORTED`-Cache pro Klasse).
  - `errors.relay_error(connection: Any, msg_id: Any, ha_code: str, err: BaseException) -> None`
    — für die vier Relais-Stellen (§7.7): sendet `str(err)` und reicht
    `translation_domain`/`translation_key`/`translation_placeholders` **durch, wenn
    vorhanden**; sonst 3-Arg-Fallback. Kein Katalogcode.
  - `errors.TRANSLATION_DOMAIN: str = "health_o_mat"`.
- Consumes:
  - Task 1: `logic.build_error`.
  - `homeassistant.exceptions.ServiceValidationError` (`__init__.py:17` importiert
    dieselbe Klasse — identische Kategorie, REQ-HOM-132-Vertrag bleibt).
  - Fake-Signaturquelle: `tests/conftest.py:362-366`, `tests/test_ws_api.py:129`.

**Steps:**
- [ ] **Step 1: Test schreiben (fail)** — `tests/test_errors.py`:
  - `test_validation_error_carries_code_params_and_fallback` — Rückgabe ist
    `ServiceValidationError`; `str(err) == build_error("amount_out_of_range", {"min": 1,
    "max": 10000})["message"]`; `err.translation_domain == "health_o_mat"`;
    `err.translation_key == "amount_out_of_range"`;
    `err.translation_placeholders == {"min": "1", "max": "10000"}`.
  - `test_validation_error_placeholders_are_str` — `{"min": 1}` → `"1"` (nicht `1`).
  - `test_send_ws_error_keeps_transport_code` — Fake-Connection mit
    `send_error(self, msg_id, code, message, **kwargs)`: `errors.send_ws_error(conn,
    7, "invalid_format", "unknown_marker", {"marker": "x"})` → `conn.errors ==
    [(7, "invalid_format", "unknown_marker (marker=x)")]` und
    `conn.error_kwargs == [(7, {"translation_domain": "health_o_mat",
    "translation_key": "unknown_marker", "translation_placeholders": {"marker": "x"}})]`.
  - `test_send_ws_error_falls_back_without_kwargs` — Fake-Connection mit
    **3-Arg-Signatur** (`def send_error(self, msg_id, code, message)`): Aufruf darf
    nicht werfen, `errors` enthält das 3-Tupel, `error_kwargs` bleibt leer.
  - `test_relay_error_forwards_translation_fields` — `HomeAssistantError("boom",
    translation_domain="health_o_mat", translation_key="restore_failed",
    translation_placeholders={"detail": "x"})` → Kwargs werden durchgereicht.
  - `test_relay_error_plain_exception_has_no_kwargs` — `RuntimeError("boom")` →
    3-Arg-Versand.
  - `tests/test_ws_api.py`-Fixture-Änderung zuerst (Step 2a), damit die Suite grün
    bleibt: der `FakeConnection` bekommt `**kwargs` + `self.error_kwargs`; alle 48
    `connection.errors ==`-Assertions bleiben unverändert.
  Vor der Implementierung: `ModuleNotFoundError: custom_components.health_o_mat.errors`.
- [ ] **Step 2: implementieren** — `errors.py` neu (nur
  `from __future__ import annotations`, `inspect`, `typing`, `homeassistant.exceptions`,
  `from . import logic`); `tests/conftest.py`-Fakes erweitern;
  `tests/test_ws_api.py:121-133` `FakeConnection` erweitern.
- [ ] **Step 3: Test (pass)** — `python3 -m pytest -q tests/test_errors.py
  tests/test_ws_api.py`; `python3 -m pytest -q`; `ruff check .`;
  `ruff format --check .`; `python3 -m compileall -q custom_components/health_o_mat`.
- [ ] **Step 4: commit** — `feat(errors): add HA error adapters for code and params`

---

### Task 3: Service-Stellen in `__init__.py` (29 Stellen)

**Agent:** senior-developer
**Depends on:** Task 2

**Files:**
- Modify: `custom_components/health_o_mat/__init__.py` — 29 migrierte Stellen (Liste
  unten), `_KIND_LABELS` (`:1176`) entfällt als Textquelle und wird durch `kind`-Params
  ersetzt; `from . import errors` ergänzen.
- Modify: `tests/test_lab_services.py` — Service-Stellen + `message`-Assertions
  (`:572` `Zeile 3 \(gptx\)`, `:585`/`:715` `^invalid_ts: `, `:384`/`:600`
  `nicht gefunden` bleibt `T`-frei, siehe unten).
- Modify: `tests/test_wave_a.py` — `:760` `"Mehrere Personen"` →
  `translation_key`/`count`.
- Modify: `tests/test_import_backup.py` — nur Regression (REQ-HOM-132), keine
  Erwartungsänderung; `:1915` `Administratoren` und `:1968` `UTF-8`-Importe bleiben
  unberührt (Importer-eigene Prosa, §5.7).

**Interfaces:**
- Produces: jede fachliche Service-Stelle wirft
  `errors.validation_error(code, params)` — `translation_key == code`,
  `translation_domain == "health_o_mat"`, `translation_placeholders == {k: str(v)}`,
  Positions-Argument = neutraler `message`-Fallback.
- Consumes: `errors.validation_error` (Task 2), `logic.build_error` (Task 1),
  `logic.HISTORY_KINDS`, `logic.VOID/RESTORE-Kind-Mengen` für `allowed`,
  `len(allowed)` für `wellbeing_*`.

**Stellen → Code (Zeilen `@ef0405f`, verifiziert):**

| Zeile | Stelle | Aufruf |
|---|---|---|
| 1048 | `get_runtime_data` — keine Person | `errors.validation_error("no_person_configured")` |
| 1052 | `get_runtime_data` — mehrere Personen | `("person_ambiguous", {"count": len(...)})` |
| 1059 | `get_runtime_data` — Person unbekannt | `("person_not_found")` |
| 1141 | `_service_entry_ts` | `("invalid_ts", {"value": raw})` |
| 1198 | `_set_entry_state` — kind unbekannt | `("invalid_history_kind", {"kind": raw_kind, "allowed": ", ".join(logic.HISTORY_KINDS)})` |
| 1203 | `_set_entry_state` — id fehlt | `("missing_item_id")` |
| 1215 | `_set_entry_state` — kein Treffer | `("entry_not_found", {"kind": kind})` |
| 1234 | `add_drink` — Menge | `("amount_out_of_range", {"min": 1, "max": DRINK_AMOUNT_MAX})` |
| 1284 | `add_lab_value` — Marker | `("unknown_marker", {"marker": raw_marker})` |
| 1291 | `add_lab_value` — Pflicht-Einheit | `("unit_required", {"marker": raw_marker})` |
| 1294 | `add_lab_value` — Wert | `("invalid_value", {"marker": raw_marker})` |
| 1298 | `add_lab_value` — Einheit | `("unsupported_unit", {"marker": raw_marker, "unit": raw_unit})` |
| 1320 | `add_lab_value` — Dedupe | `("duplicate_marker", {"marker": raw_marker})` |
| 1337 | `add_lab_report` — ts (Wrapper) | `("invalid_ts", {"value": raw_ts})` |
| 1350 | `add_lab_report` — Zeilenfehler | `errors.validation_error(error["code"], error["params"])` |
| 1364 | `add_lab_report` — Dedupe | `("duplicate_marker", {"marker": ...})` |
| 1380 | `remove_lab_report` — ts (Wrapper) | `("invalid_ts", {"value": raw_ts})` |
| 1384 | `remove_lab_report` — ts fehlt | `("invalid_ts", {"value": raw_ts})` |
| 1399 | `remove_lab_report` — kein Treffer | `("no_active_report", {"ts": ts_iso})` |
| 1411 | `set_wellbeing` — status/score fehlen | `("wellbeing_target_missing", {"max": len(allowed)})` |
| 1415 | `set_wellbeing` — Score | `("wellbeing_score_invalid", {"min": 1, "max": len(allowed)})` |
| 1419 | `set_wellbeing` — Status | `("wellbeing_key_unknown", {"allowed": ", ".join(allowed)})` |
| 1444 | `remove_last_entry` — kind | `("invalid_undo_kind", {"kind": raw_kind, "allowed": ", ".join(...)})` |
| 1452 | `remove_last_entry` — kein Undo | `("undo_not_supported", {"kind": kind, "allowed": ", ".join(...)})` |
| 1463 | `remove_last_entry` — nichts zu entfernen | `("nothing_to_remove", {"kind": kind})` |
| 1483 | `remove_last_lab_value` — Marker | `("unknown_marker", {"marker": raw_marker})` |
| 1493 | `remove_last_lab_value` — kein Wert | `("no_active_value", {"marker": marker})` |
| 1597 | `weekly_report` — kein Store | `("no_person_configured")` |
| 1608 | `weekly_report` — keine Ziele | `("no_person_configured")` |

`wellbeing_target_missing.params.max`-Quelle (**Review-Auflage 3**):
`allowed = [state["key"] for state in WELLBEING_STATES]` (`__init__.py:1409`,
Konstante `const.py:115`), heute als `len(allowed)` in `:1416` gerendert — der Wert
ist damit `len(WELLBEING_STATES)`; der Katalogtest
(`test_catalog_params_are_declared_tuples`) und der Service-Test
(`test_set_wellbeing_target_missing_reports_scale_max`) pinnen ihn.

**Nicht migriert (`T`):** `:1169`, `:1172` (Berechtigung), `:1570`
(`RestoreError`-Wrapper) — unverändert.

**Steps:**
- [ ] **Step 1: Test schreiben (fail)** — in `tests/test_lab_services.py`,
  `tests/test_wave_a.py` je Stelle eine Assertion auf das Objekt statt auf den Text:
  - `tests/test_lab_services.py::test_req_hom_127_unknown_marker_service_error_carries_code`
    — `exc.value.translation_key == "unknown_marker"`,
    `exc.value.translation_placeholders == {"marker": "gptx"}`, `str(exc.value)` ohne
    Umlaute/„Zeile".
  - `test_req_hom_127_lab_report_row_error_keeps_batch_code` — Batch-Wrapper
    (`:1350`) trägt `translation_key == "duplicate_marker"` und
    `translation_placeholders["row"] == "2"`.
  - `test_req_hom_127_invalid_ts_service_error_carries_value` — `:1141`/`:1337`/`:1384`
    → `translation_key == "invalid_ts"`, `placeholders["value"] == raw`.
  - `test_req_hom_127_amount_out_of_range_service_error_carries_bounds` — `:1234`.
  - `test_req_hom_127_set_wellbeing_target_missing_reports_scale_max` — `:1411`,
    `placeholders["max"] == str(len(WELLBEING_STATES))`.
  - `test_req_hom_127_set_wellbeing_unknown_key_lists_allowed` — `:1419`.
  - `test_req_hom_127_undo_and_remove_codes` — `:1444`/`:1452`/`:1463`/`:1493`.
  - `tests/test_wave_a.py::test_req_hom_127_ambiguous_person_reports_count` — `:1052`,
    `placeholders == {"count": "2"}`, `str(exc.value)` enthält **keinen** Namen
    (PII-Guard).
  - `tests/test_wave_a.py::test_req_hom_127_missing_person_reports_code` — `:1059`,
    kein Name im Text.
  - `tests/test_lab_services.py::test_req_hom_127_weekly_report_codes` — `:1597`/`:1608`.
  - Bestehende Text-Assertions anpassen: `:572` (`Zeile 3 (gptx)`) →
    `translation_key`/`placeholders`; `:585`, `:715` (`^invalid_ts: `) →
    `translation_key == "invalid_ts"` + `placeholders["value"]`.
  - `tests/test_import_backup.py` bleibt unverändert und muss grün bleiben
    (REQ-HOM-132-Regression).
  Alle neuen Tests scheitern vor der Implementierung (`AttributeError:
  translation_key`).
- [ ] **Step 2: implementieren** — die 29 Stellen auf
  `errors.validation_error(...)` umstellen; `str(err) or "…"`-Wrappers
  (`:1320`, `:1364`) auf den Code-Pfad ziehen (der Fallback-Text kommt aus dem
  Template); `_KIND_LABELS` (`:1176`) entfernen, weil `kind` jetzt als Param
  transportiert wird (der Übersetzungstext beschreibt die Kategorie).
- [ ] **Step 3: Test (pass)** — `python3 -m pytest -q tests/test_lab_services.py
  tests/test_wave_a.py tests/test_import_backup.py`; `python3 -m pytest -q`;
  `ruff check .`; `ruff format --check .`; `python3 -m compileall -q custom_components/health_o_mat`.
- [ ] **Step 4: commit** — `feat(services): emit error codes and params`

---

### Task 4: WS-Stellen in `ws_api.py` (32 migriert + 4 Relais), `parse_entry_ts`, `parse_settings_message`

**Agent:** senior-developer
**Depends on:** Task 3

**Files:**
- Modify: `custom_components/health_o_mat/ws_api.py` — 32 `send_error`-Stellen
  (Tabelle unten), 4 Relais-Stellen, `parse_entry_ts` (`:875-887`),
  `parse_settings_message` (`:2047-2059`), `from . import errors`.
- Modify: `custom_components/health_o_mat/logic.py` — `ENTRY_TS_INVALID_MESSAGE`
  (`:160-163`) **löschen** (letzter Konsument entfällt hier);
  `ENTRY_TS_MIN`/Docstrings anpassen.
- Modify: `tests/test_ws_api.py` — 32 Stellen + `parse_settings_message`-Rückgabetyp
  (`:4214`, `:4623`), keine `message`-/`errors`-Tupel-Änderung (48 Assertions bleiben).
- Modify: `tests/test_logic.py` — falls ein Test `ENTRY_TS_INVALID_MESSAGE`
  referenziert, auf `build_error("invalid_ts", ...)` umstellen.

**Interfaces:**
- Produces:
  - `parse_entry_ts` wirft weiterhin `ValueError`, aber mit dem **neutralen**
    `build_error("invalid_ts", {"value": value})["message"]` (kein `ENTRY_TS_INVALID_MESSAGE`
    mehr).
  - `parse_settings_message(msg, *, previous_markers=None) -> tuple[dict[str, Any],
    dict[str, Any] | None]` — das zweite Element ist jetzt das **strukturierte**
    `logic.build_error("invalid_setting", {"field": <settings-key>})`-Objekt statt
    eines Prosa-Strings; `field` ist der erste abgelehnte Top-Level-Schlüssel
    (`areas`, `audit_limit`, `wellbeing_confirm`, `wellbeing_images`,
    `lab_custom_markers`, `lab_hidden_categories`, `drink_lexicon`).
  - `websocket_set_settings` sendet `errors.send_ws_error(connection, msg["id"],
    ERR_INVALID_FORMAT, error["code"], error["params"])`.
- Consumes: `errors.send_ws_error`, `errors.relay_error` (Task 2),
  `logic.build_error` (Task 1).

**Stellen → Code (Zeilen `@ef0405f`, verifiziert):**

| Zeile | Stelle | Code |
|---|---|---|
| 1303 | `book_drink` — ml | `amount_out_of_range` `{min,max}` |
| 1313 | `book_drink` — ts | `invalid_ts` `{value: msg.get("ts")}` |
| 1338 | `undo_last` — kind | `invalid_undo_kind` `{kind,allowed}` |
| 1351 | `undo_last` — nichts zu entfernen | `nothing_to_remove` `{kind}` |
| 1375 | `list_history` — kind | `invalid_history_kind` `{kind,allowed}` |
| 1388 | `list_history` — limit | `limit_out_of_range` `{min,max}` |
| 1398 | `list_history` — offset | `offset_invalid` |
| 1407 | `list_history` — since-Typ | `invalid_since` `{expected}` |
| 1417 | `list_history` — since-Wert | `invalid_since` `{expected}` |
| 1468 | `void/restore_entry` — kind | `invalid_history_kind` `{kind,allowed}` |
| 1484 | `void/restore_entry` — kein Treffer | `entry_not_found` `{kind}` |
| 1534 | `save_measurement` — sys/dia | `bp_out_of_range` `{min,max}` |
| 1545 | `save_measurement` — ts | `invalid_ts` `{value}` |
| 1574 | `_resolve_lab_marker_or_error` | `unknown_marker` `{marker}` |
| 1603 | `add_lab_value` — Einheit | `unit_required` `{marker}` |
| 1608 | `add_lab_value` — Wert | `invalid_value` `{marker}` |
| 1614 | `add_lab_value` — Einheit unbekannt | `unsupported_unit` `{marker,unit}` |
| 1621 | `add_lab_value` — ts | `invalid_ts` `{value}` |
| 1640 | `add_lab_value` — Dedupe | `duplicate_marker` `{marker}` |
| 1776 | `remove_last_lab_value` | `no_active_value` `{marker}` |
| 1794 | `set_wellbeing` — target | `wellbeing_target_missing` `{max: len(WELLBEING_STATES)}` |
| 1799 | `set_wellbeing` — score | `wellbeing_score_invalid` `{min:1,max:len(WELLBEING_STATES)}` |
| 1806 | `set_wellbeing` — key | `wellbeing_key_unknown` `{allowed}` |
| 1812 | `set_wellbeing` — ts | `invalid_ts` `{value}` |
| 2163 | `set_settings` — Validierung | `error["code"]` aus `parse_settings_message` |
| 2188 | `export_csv` — Datensatz | `unknown_dataset` `{allowed}` |
| 2235 | `start_person_flow` — kein `async_init` | `config_flow_unavailable` |
| 2245 | `start_person_flow` — Flow-Start geworfen | `config_flow_failed` (Roh-Exception nur im Log `:2244`) |
| 2274 | `delete_person` — Bestätigung | `confirm_mismatch` |
| 2343 | `import_csv` — Quelle | `invalid_import_source` |
| 2353 | `import_csv` — UTF-8 | `content_not_utf8` |
| 2358 | `import_csv` — Größe | `content_too_large` `{max: MAX_IMPORT_CONTENT_BYTES}` |

**Batch (`send_result`, nicht `send_error`; Form unverändert):** `:1646`
(`_lab_error_result`, unverändert), `:1673`, `:1680`, `:1727`, `:1741` ziehen ihr
`message` automatisch aus dem neuen Builder; `:1694` (handgebautes
`{"code": "duplicate_marker", "params": {}, "message": …}`) wird auf
`logic.lab_report_error("duplicate_marker", {"marker": …})` vereinheitlicht.

**Relais (code-unverändert, §7.7):** `:2212` (`ERR_EXPORT_FAILED`), `:2295`
(`ERR_BACKUP_FAILED`), `:2381` (`ERR_IMPORT_FAILED`), `:2404` (`ERR_RESTORE_FAILED`)
→ `errors.relay_error(connection, msg["id"], <ERR_…>, err)`.

**Unverändert (`T`):** `:802`, `:1280`, `:1889`, `:1930`.

**Steps:**
- [ ] **Step 1: Test schreiben (fail)** — in `tests/test_ws_api.py` (jede der 32
  Stellen bekommt eine Assertion auf `connection.error_kwargs`):
  - `test_req_hom_127_book_drink_amount_error_carries_code` — `error_kwargs[-1] ==
    (msg_id, {"translation_domain": "health_o_mat", "translation_key":
    "amount_out_of_range", "translation_placeholders": {"min": "1", "max": "10000"}})`
    und `connection.errors[-1][1] == "invalid_format"`.
  - `test_req_hom_127_history_errors_code_matrix` — parametrisiert über
    `list_history` (`kind`/`limit`/`offset`/`since`), prüft `translation_key` und
    Placeholder-Projektion.
  - `test_req_hom_127_measurement_and_wellbeing_codes` — `:1534`, `:1545`, `:1794`,
    `:1799`, `:1806`, `:1812`; `:1794` prüft `placeholders["max"] ==
    str(len(WELLBEING_STATES))`.
  - `test_req_hom_127_lab_value_ws_codes` — `:1574`, `:1603`, `:1608`, `:1614`,
    `:1621`, `:1640`, `:1776`.
  - `test_req_hom_127_admin_codes` — `:2163` (`invalid_setting`, `field`), `:2188`,
    `:2235`, `:2245` (kein Roh-Exception-Text in `errors`/`error_kwargs`), `:2274`,
    `:2343`, `:2353`, `:2358`.
  - `test_req_hom_127_transport_errors_unchanged` — `:802`, `:1280`, `:1889`,
    `:1930` erzeugen **keine** `error_kwargs`-Einträge.
  - `test_req_hom_127_relay_sites_forward_translation_fields` — die vier Relais
    reichen bei einem `HomeAssistantError` mit `translation_*` genau diese durch.
  - `test_req_hom_127_batch_envelope_has_no_translation_keys` — `add_lab_report`/
    `remove_lab_report` liefern `{"ok": false, "error": {code, params, message}}`
    mit **exakt** diesen drei Keys.
  - `tests/test_ws_api.py:4214` → `error["code"] == "invalid_setting"` /
    `error["params"]["field"] == "audit_limit"`; `:4623` → `error["code"] ==
    "invalid_setting"` statt `startswith("Ungültige Einstellung '")`.
  - `tests/test_logic.py`: falls `ENTRY_TS_INVALID_MESSAGE` referenziert wird,
    `build_error("invalid_ts", {"value": raw})["message"]` prüfen.
  Alle neuen Tests scheitern vor der Implementierung (`error_kwargs` bleibt leer /
  `TypeError` beim String-Zugriff).
- [ ] **Step 2: implementieren** — 32 Stellen auf `errors.send_ws_error`,
  4 Relais auf `errors.relay_error`, `parse_settings_message` auf das
  strukturierte Fehlerobjekt, `parse_entry_ts` auf den neutralen Text;
  `ENTRY_TS_INVALID_MESSAGE` in `logic.py` löschen (Konzept O-7).
- [ ] **Step 3: Test (pass)** — `python3 -m pytest -q tests/test_ws_api.py
  tests/test_logic.py tests/test_import_backup.py`; `python3 -m pytest -q`;
  `ruff check .`; `ruff format --check .`; `python3 -m compileall -q custom_components/health_o_mat`.
- [ ] **Step 4: commit** — `feat(ws): emit error codes and localize ws errors`

---

### Task 5: Übersetzungskatalog (Master + en + de) und i18n-Guards

**Agent:** developer
**Depends on:** Task 1

**Files:**
- Modify: `custom_components/health_o_mat/strings.json` — neue Sektion
  `exceptions` mit **35** Einträgen (Tabelle B) + `common.ui_panel_lab_report_row_hint`.
- Modify: `custom_components/health_o_mat/translations/en.json` — identische
  Schlüssel/Platzhalter (Pflicht-Fallback für Custom-Integrationen).
- Modify: `custom_components/health_o_mat/translations/de.json` — deutsche Texte.
- Modify: `tests/test_translations.py` — kataloggetriebene Tests.

**Interfaces:**
- Produces: `exceptions.<code>.message` in allen drei Dateien für **jeden** Code aus
  `logic.ERROR_SPECS` (35), Platzhalter-Mengen je Code **identisch**; kein
  `exceptions`-Key ohne Katalogcode (kein toter Text).
- Consumes: `logic.ERROR_SPECS` (Task 1); bestehende Tests
  `test_req_hom_107_key_tree_parity` (`:75`) und
  `test_translation_placeholders_match_across_languages` (`:372`) decken die neue
  Sektion automatisch mit ab.

**Steps:**
- [ ] **Step 1: Test schreiben (fail)** — `tests/test_translations.py`:
  - `test_req_hom_127_every_catalog_code_has_a_translation` — für alle 35 Codes:
    `exceptions[code]["message"]` nicht leer in `strings.json`, `de.json`, `en.json`.
  - `test_req_hom_127_no_orphan_exception_translation` — jeder
    `exceptions`-Schlüssel steht in `logic.ERROR_SPECS`.
  - `test_req_hom_127_exception_placeholders_match_across_languages` — für **jeden**
    Code ist die Platzhalter-Menge in Master/de/en **gleich** (Mengengleichheit,
    nicht Teilmenge) — die Konkretisierung von `:372` auf die neue Sektion.
  - `test_req_hom_127_exception_placeholders_are_declared_params` — jeder
    Platzhalter steht in `ERROR_SPECS[code]["params"]`; `{row}`/`{first_row}`
    kommen in **keinem** Text vor.
  - `test_req_hom_127_invalid_value_never_renders_value` — **Review-Auflage 1,
    expliziter Guard**: `"{value}" not in
    exceptions["invalid_value"]["message"]` in allen drei Dateien; zusätzlich
    `"{value}" only in exceptions["invalid_ts"]["message"]` für die ganze Sektion.
  - `test_req_hom_127_no_single_quotes_around_placeholders` — kein
    `'{...}'`-Muster (hassfest-Regel §9.2.2).
  - `test_req_hom_127_german_and_english_texts_differ` — `de != en` für jeden Code.
  - `test_req_hom_127_lab_report_row_hint_exists` —
    `common.ui_panel_lab_report_row_hint` in allen drei Dateien mit identischem
    Platzhalter `{row}`.
  Vor der Implementierung: `KeyError: 'exceptions'`.
- [ ] **Step 2: implementieren** — die Sektion mit den Texten aus Tabelle B in alle
  drei Dateien; Schlüsselreihenfolge je Datei identisch zur Katalogreihenfolge
  (diff-bare Pflege); `ui_panel_lab_report_row_hint`: en `Row {row}`, de
  `Zeile {row}`.
- [ ] **Step 3: Test (pass)** — `python3 -m pytest -q tests/test_translations.py`;
  `python3 -m pytest -q`; `ruff check .`; `ruff format --check .`.
- [ ] **Step 4: commit** — `feat(i18n): add exception translations for error codes`

---

### Task 6: Frontend-Parser auf `translation_key || code`

**Agent:** senior-developer
**Depends on:** Task 4, Task 5

**Files:**
- Modify: `custom_components/health_o_mat/www/health-o-mat-i18n.js` — zweite
  Ressourcen-Kategorie `exceptions` (`ERROR_KEY_PREFIX =
  "component.health_o_mat.exceptions."`, eigener `_errorCache`/`_errorInflight` pro
  Sprache neben `_cache` `:32`), `loadExceptionTranslations(hass)` (parallel zu
  `loadUiTranslations` `:92`, gemeinsame In-Flight-Karte), `tError(err)` und
  `resetUiTranslations` (`:55`) leert beide Caches.
- Modify: `custom_components/health_o_mat/www/health-o-mat-labs-card.js` —
  `errorMessage()` (`:227-237`), `resultError()` (`:241-245`),
  `reportErrorMessage()` (`:247-250`); Aufrufstelle `:868`.
- Modify: `custom_components/health_o_mat/www/health-o-mat-card.js` — Inline-Loader
  (`:194-228`) um `exceptions` erweitern (`_uiErrorCache`, `_tError`), neues
  `_errorText(err)`, alle 11 `err.message`-Anzeigestellen (`:1192`, `:1298`,
  `:1453`, `:1551`, `:1596`, `:1624`, `:1666`, `:1716`, `:2019`) darauf umstellen.
- Modify: `custom_components/health_o_mat/www/health-o-mat-panel-base.js` —
  `setUiErrorTranslator(fn)` neben `setUiTranslator` (`:723`), `wsErrorText`
  (`:828`) lokalisiert zuerst, `rowHint(err)` liefert
  `ui_panel_lab_report_row_hint` aus `err.params.row` (leer ohne `row`).
- Modify: `custom_components/health_o_mat/www/health-o-mat-panel-views.js` —
  `resultError()` (`:1320`) lokalisiert + Zeilen-Hinweis; `_formError = errMsg(err)`
  (`:1308`) auf `wsErrorText`.
- Modify: `custom_components/health_o_mat/www/health-o-mat-panel.js` —
  `setUiErrorTranslator(uiErrorTranslate)` neben `:100`, `uiErrorTranslate` aus
  `health-o-mat-i18n.js` importieren; die 11 `wsErrorText`-Stellen bleiben
  unverändert (der Parser wird zentral lokalisiert).
- Modify: `tests/test_card_js.py` — Fehleranzeige-Tests (Node-Subprozess,
  `:2350-2425`).
- Modify: `tests/test_panel_js.py` — `resultError`-Stellen (`:3782`, `:3913`) +
  `wsErrorText`-Test.

**Interfaces:**
- Produces:
  - `tError(err) -> str` (i18n.js, exportiert):
    `key = err.translation_key || err.code`; `vars = err.translation_placeholders ||
    err.params || {}`; `text = _errorCache[lang][key + ".message"]`; Rückgabe
    `interpolateUi(text, vars)` sonst `err.message` sonst `key` sonst `""` —
    **nie** eine leere Zeile.
  - `card._errorText(err)` — identische Regel, Inline (die Karte hat keine Imports).
  - `labs.errorMessage(err)` — Map-Key ist jetzt `err.code`, Werte sind `common`-Keys
    (`ui_labs_error_unknown_marker` …) mit `_t`; `resultError(result)` nutzt
    `tError(result.error)`; `reportErrorMessage(err)` nutzt `tError(err)`.
  - `panelBase.wsErrorText(err)` — Priorität: `tError(err)` → `errMsg(err)` +
    optionaler Zeilen-Hinweis; der bisherige `translation_placeholders`-Anhang
    entfällt.
  - `panelViews.resultError(result)` — `tError(result.error)` + `rowHint`.
- Consumes: Drahtformat aus Task 4 (`translation_key`/`translation_placeholders`),
  Katalogtexte aus Task 5, `interpolateUi` (`i18n.js:74`), `_uiInterpolate`
  (`card.js:167`), `t` (`panel-base.js:749`).

**Steps:**
- [ ] **Step 1: Test schreiben (fail)** — Text-/Subprozess-Assertions im Stil der
  bestehenden Dateien:
  - `tests/test_card_js.py::test_req_hom_127_labs_error_message_prefers_code` —
    Node-Lauf mit `{ok: false, error: {code: "unknown_marker", params: {row: 1,
    marker: "alt"}, message: "unknown_marker (marker=alt)"}}` → `error` ist **nicht**
    mehr der rohe `message`, sondern der lokalisierte Text aus dem `exceptions`-Katalog
    (Fixture injiziert die Ressourcen direkt).
  - `test_req_hom_127_card_error_text_uses_translation_key` — Objekt mit
    `translation_key`/`translation_placeholders` → gerenderter Text; ohne Katalog →
    `message`-Fallback; ohne beides → `code`.
  - `test_req_hom_127_labs_card_renders_row_hint` — `params.row == 2` →
    der Zeilen-Hinweis erscheint, ohne den Platzhalter `{row}` im Text zu lassen.
  - `tests/test_panel_js.py::test_req_hom_127_ws_error_text_localizes` — Quelltext-
    und Subprozess-Assertion: `wsErrorText` liest `translation_key` **vor**
    `message`; `translation_placeholders`-Anhang ist entfernt.
  - `test_req_hom_127_panel_result_error_localizes` — `resultError` in
    `panel-views.js`.
  - `test_req_hom_127_i18n_loads_exceptions_category` — `health-o-mat-i18n.js`
    enthält `category: "exceptions"` und einen zweiten, pro Sprache gecachten Satz;
    `resetUiTranslations` leert beide.
  - `tests/test_card_js.py:2421` (`failed["error"] == "Zeile 1 (alt): unknown_marker"`)
    auf den neuen Erwartungswert umstellen.
  Alle scheitern vor der Implementierung.
- [ ] **Step 2: implementieren** — in der Reihenfolge `i18n.js` → `panel-base.js` →
  `panel.js` → `panel-views.js` → `labs-card.js` → `card.js`; jeder Parser behält
  den `message`-Fallback (der Backend-Rollback bleibt lesbar), rendert aber nie
  einen rohen `ui_…`-Key.
- [ ] **Step 3: Test (pass)** — `python3 -m pytest -q tests/test_card_js.py
  tests/test_panel_js.py`; `python3 -m pytest -q`; `ruff check .`;
  `ruff format --check .`.
- [ ] **Step 4: commit** — `feat(ui): localize error codes from the catalog`

---

### Task 7: E2E — Fehlerobjekt **und** gerenderte Meldung (de/en)

**Agent:** tester
**Depends on:** Task 4, Task 6

**Files:**
- Modify: `tests_e2e/test_i18n_e2e.py` — neuer Test
  `test_req_hom_127_error_codes_are_localized`, nutzt `hass_base_url`,
  `hass_bearer_token`, `panel_person` und `e2e_helpers.ws_command`.
- Modify: `tests_e2e/test_lab_values_e2e.py` — `:757-762` (gerenderte
  Batch-Meldung im Panel) auf den lokalisierten Text + Zeilen-Hinweis umstellen.

**Interfaces:**
- Produces: E2E-Beleg, dass (a) das Fehlerobjekt `translation_domain`/
  `translation_key`/`translation_placeholders` trägt, (b) der **interpolierte**
  Text in beiden Sprachen der erwartete Satz ist, (c) das Panel die **gerenderte**
  Meldung zeigt (nicht den Code, nicht den neutralen Fallback).
- Consumes: `ws_command` (`e2e_helpers.py:111`), `open_panel`/`wait_for_detail`
  (`test_panel_deeplink_e2e.py`), `LAB_REPORT_*`-Selektoren
  (`test_lab_values_e2e.py:100-125`), `call_service`-Verhalten (HTTP-Status des
  `ServiceValidationError`).

**Steps:**
- [ ] **Step 1: Test schreiben (fail)**
  - Fehlerobjekt: `health_o_mat/book_drink` mit `ml: 0` über
    `ws_command(..., {"type": "health_o_mat/book_drink", "entry_id": ...,
    "ml": 0})` — der `BootstrapError` trägt `code == "invalid_format"`,
    `translation_key == "amount_out_of_range"`,
    `translation_placeholders == {"min": "1", "max": "10000"}`.
  - Gerenderter Text: `frontend/get_translations` mit
    `{"type": "frontend/get_translations", "language": L, "category": "exceptions",
    "integration": ["health_o_mat"]}` für `L in ("de", "en")`; für
    `amount_out_of_range` ist der Ressourcen-Text vorhanden, de ≠ en, und nach
    Ersetzen von `{min}`/`{max}` steht genau
    `"Die Menge muss zwischen 1 und 10000 ml liegen."` bzw.
    `"Amount must be between 1 and 10000 ml."` da. **Kein** Sprachwechsel der
    Instanz (`hass.language` bleibt `en`).
  - Panel-gerendert: `test_lab_values_e2e.py` — nach dem doppelten Marker steht im
    `.msg.error`-Element der englische Satz
    `"Marker gptx appears more than once in this report."` **plus** `Row 2`
    (Zeilen-Hinweis) und **nicht** `duplicate_marker`.
  - Der Test nutzt `pytest.mark.e2e` und keinen `bin/reset`.
- [ ] **Step 2: Sync + Lauf** — `/home/hermes/ha-test/bin/sync
  /home/hermes/repos/ha-health-o-mat` (nur die eigene Domain), dann
  `python3 -m pytest -q tests_e2e/test_i18n_e2e.py tests_e2e/test_lab_values_e2e.py`;
  zusätzlich `python3 -m pytest -q`, `ruff check .`, `ruff format --check .`.
- [ ] **Step 3: commit** — `test(e2e): prove localized error messages end to end`

---

### Task 8: Dokumentation (Transport gemäß D-3)

**Agent:** documenter (+ `requirements` für REQ-HOM-127)
**Depends on:** Task 7

> Kein TDD-Schritt: Task 8 ändert ausschließlich Prosa-Dokumente (kein
> ausführbarer Code). Akzeptanz ist `pytest -q` grün **plus** die Prüfung, dass
> jede im Dokument genannte Zeile/Datei existiert.

**Files:**
- Modify: `docs/SERVICE-RESPONSES.md` — Abschnitt „Fehler": `code ==
  translation_key`, `params` = typisierte/`translation_placeholders` = stringifizierte
  Projektion, Batch bleibt `{code, params, message}`, Relay-Verhalten, 35-Code-Katalog
  (Verweis auf `logic.ERROR_SPECS`), Client-Regel „`translation_key` vor `code`".
- Modify: `docs/REQUIREMENTS.md` — REQ-HOM-127-AKs (`:1591-1598`) abhaken, Belege
  (`pytest`-Zahl, E2E-Namen, Plan-Pfad) eintragen, Status auf „Umgesetzt
  (2026-11-03)".
- Modify: `docs/superpowers/specs/2026-11-03-error-contract-design.md` — Umsetzungs-
  verweis auf diesen Plan (keine inhaltliche Änderung).
- Modify: `docs/PLAN-AUDIT-2026-11-03.md` — F-08 als erledigt markieren (WP-A).

**Interfaces:**
- Produces: nachvollziehbare Traceability REQ-HOM-127 ↔ Plan ↔ Tests.
- Consumes: Task-Ergebnisse 1–7.

**Steps:**
- [ ] **Step 1: `docs/SERVICE-RESPONSES.md`** und `docs/REQUIREMENTS.md` schreiben.- [ ] **Step 2: `python3 -m pytest -q` grün; `docs/`-Links prüfen** (relative Pfade).
- [ ] **Step 3: commit** — `docs: document the error code contract`

---

## Review-Auflagen (Konzept §16) → Task-Mapping

| Auflage | Task / Akzeptanzkriterium |
|---|---|
| 1 — `{value}` in `translation_placeholders` (§5.2:117) nur sicher, weil `invalid_value` kein `{value}` im Text hat | **Task 5**, `test_req_hom_127_invalid_value_never_renders_value` (expliziter Guard, nicht Nebenbedingung) + **Task 1**, `test_params_stringified_projection` |
| 2 — „ASCII" gilt nur fürs Template, nicht für gerenderte Werte (§11:615) | **Task 1**, `test_message_template_is_ascii` prüft `template`/`row_template`, nicht `build_error(...)["message"]` |
| 3 — `wellbeing_target_missing.params.max` ohne Quelle | **Task 1** (Katalog deklariert `max`), **Task 3** (`:1411` aus `len(allowed)` mit `allowed` aus `WELLBEING_STATES`, `:1409`/`:1416`), **Task 4** (`:1794` aus `len(WELLBEING_STATES)`), Test `test_req_hom_127_set_wellbeing_target_missing_reports_scale_max` |

## Nicht umgesetzt (bewusst, mit Begründung)

- **`invalid_setting` verliert den Voluptuous-Detailtext.** Das heutige WS-Ergebnis
  hängt die Validator-Meldung (inkl. Lexikon-Zeilennummer) an; §6 deklariert nur
  `field`, §14 verbietet Freitext in `params`. Der Detailtext bleibt im Log
  (`_LOGGER.debug`), die UI nennt nur das Feld. **Offener Punkt für `validator`**:
  falls die Lexikon-Zeile in der UI gebraucht wird, braucht §6 einen optionalen
  `line`-Param (Konzeptänderung, nicht in diesem Plan).
- **`button.py:112,131,150` / `text.py:51`** (deutsche `HomeAssistantError` aus
  Entity-Aktionen) — kein Service-/WS-Pfad (§7.6, O-6), Folgekandidat.
- **`RestoreError`/`restore.py`/`exporter.py`/`importer.py`/`backup.py`-Prosa** —
  eigener Grundkatalog (§5.7, O-5, REQ-HOM-132).
- **`add_blood_pressure` (Service) ohne Bereichsprüfung** — O-3: keine
  Verhaltensänderung; wird hier nur als Beobachtung geführt.
- **`errors_detail`** (Backlog-Name des Transports) ist mit D-3 **verworfen** —
  der Transport sind die HA-`translation_*`-Felder; Batch bleibt
  `{code, params, message}`.

## Verifikation (nach jedem Task, final in Task 7/8)

```bash
python3 -m pytest -q
ruff check .
ruff format --check .
python3 -m compileall -q custom_components/health_o_mat
/home/hermes/ha-test/bin/sync /home/hermes/repos/ha-health-o-mat
python3 -m pytest -q tests_e2e/test_i18n_e2e.py tests_e2e/test_lab_values_e2e.py
```

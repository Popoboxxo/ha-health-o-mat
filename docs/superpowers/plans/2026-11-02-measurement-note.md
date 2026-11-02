---
pipeline_stages:
  implement: 1
---

# Mess-Notiz-Eingabe (REQ-HOM-010) Implementation Plan
> Status: umgesetzt

**Goal:** Die fehlende Text-Entity `measurement_note` pro Person ergänzen, sodass eine
angefangene Notiz neustartfest neben den Blutdruck-Eingabefeldern liegt, beim Speichern
als `note` in die Messung fließt, danach geleert wird und in `history_json` sowie im
Blutdruck-CSV sichtbar ist — ohne bestehende `unique_id`s, Store-Schemata oder
CSV-Importe zu brechen.

**Architecture:** Die Notiz ist ein **Eingabefeld der Blutdruck-Erfassung**, kein neues
Datenobjekt. Sie liegt deshalb im bereits persistierten `store.inputs`-Dict der Person
(REQ-HOM-104, Store-Schema v2) unter dem Schlüssel `"note"` — genau dort, wo
`InputNumber` bereits `sys`/`dia`/`pulse` hält. Die neue Entity
`MeasurementNoteEntity` schreibt ausschließlich in diesen Store-Pfad und liest von dort.
Geleert wird zentral in `HealthOMatStore.add_reading`: das ist der einzige Schreibpfad
für Messungen (Service `add_blood_pressure`, WS-Kommando `health_o_mat/save_measurement`,
`SaveReadingButton`, CSV-Import). Der `SaveReadingButton` liest die angefangene Notiz und
übergibt sie als `note`; die bestehenden Service-/WS-Parameter bleiben unverändert.

**Tech Stack:** Python 3.13 / Home Assistant Custom Component (`TextEntity`,
`CoordinatorEntity`), pytest mit der Fake-HA-Technik aus `tests/conftest.py`
(importlib-Laden der Module, echte `HealthOMatStore`-Instanz mit gemocktem
HA-`Store`-Backend), voluptuous nur im bestehenden Service-Schema.

**Spec:** docs/REQUIREMENTS.md
**Spec-Anker:** §REQ-HOM-010 (Zeilen 325–335) — es existiert **keine separate Spec**;
die REQ in `docs/REQUIREMENTS.md` ist der verbindliche Anker. Der Portfolio-Plan
`docs/PLAN-BACKLOG-2026-11-02.md` §3 Welle 2 ist die Umsetzungsvorgabe.

**Ausgangslage (am Code belegt, `main` @ `46c4513`, Release 0.19.0):**

- Der `note`-Parameter fließt bereits durch Service (`__init__.py:1204-1220`), Store
  (`store.py:575-594`), WS (`ws_api.py:1506-1542`), Export (`exporter.py:142`) und
  Import (`importer.py:387`). Es fehlt ausschließlich die Text-Entity.
- `text.py` kennt nur `FreeTextDrinkEntity` (`text_freetext`, Getränke-Bereich).
- `store.inputs(entry_id)` (`store.py:1112`) ist der persistierte Eingabebereich der
  Person; `clear_inputs` (`store.py:1121`) leert ihn nach dem Button-Save.
- `SaveReadingButton` (`button.py:135-163`) übergibt aktuell `""` als `note` und ruft
  danach `clear_inputs` — die angefangene Notiz ginge ohne diese Änderung verloren.
- `BloodPressureHistorySensor` (`sensor.py:233-255`) schreibt die vollen Mess-Dicts nach
  `history_json`; das CSV schreibt `r.get("note", "")` in Spalte 6 (`notiz`).

**Nicht-Ziele:** Keine Notiz für Wohlbefinden oder Trinken (deren Store-Methoden haben
keinen `note`-Parameter). Keine neue Store-Schema-Version, keine Änderung an
`manifest.version`, `ConfigFlow.VERSION` oder bestehenden `unique_id`s. Keine neuen
CSV-Spalten und kein neuer Service.

## Global Constraints

- `unique_id` wird **nie** geändert. Die neue Entity bekommt die additive, stabile ID
  `{entry_id}_text_measurement_note` (Plattform-Präfix wie `text_freetext`); bestehende
  IDs bleiben unangetastet.
- Kein Namens-Literal: `_attr_has_entity_name = True` (geerbt von `HealthOMatEntity`) +
  `_attr_translation_key = "measurement_note"`. Kein `_attr_name`, kein `name`-Override.
- Die Notiz liegt in `store.inputs[entry_id]["note"]`; `STORE_SCHEMA_VERSION` bleibt
  unverändert (Feld ist Teil des seit v2 existierenden `inputs`-Dicts). Kein Migrator.
- Leeren ausschließlich zentral in `HealthOMatStore.add_reading` — nicht in den einzelnen
  Handlern duplizieren. Damit leeren Service, WS, Button und Import die angefangene
  Notiz; der Handler `add_blood_pressure` und das WS-Kommando
  `health_o_mat/save_measurement` bleiben unverändert.
- CSV bleibt additiv und rückwärtskompatibel: bestehende Spaltenreihenfolge
  `zeitstempel;person;systolisch;diastolisch;puls;notiz` bleibt; der Importer akzeptiert
  weiterhin Zeilen ohne sechste Spalte (`len(cells) > 5`).
- Keine Änderung an `manifest.version`, `ConfigFlow.VERSION` oder `unique_id`s in diesem
  Plan. Der Release ist **MINOR (0.20.0)**, weil eine neue Entity entsteht — nicht wegen
  eines Versions-Bumps im Plan.
- Conventional Commits, Englisch, Imperativ, erste Zeile ≤ 72 Zeichen, **keine führende
  UTF-8-BOM**. Jede Commit-Nachricht steht exakt im Task.
- `from __future__ import annotations` + vollständige Type-Hints in jeder berührten
  Python-Datei. Code/Kommentare/Tests/Commits Englisch, Plan/Prosa Deutsch.
- Nach jedem Task: `python3 -m pytest -q` und `ruff check .` +
  `ruff format --check .` grün.
- Testinstanz-Etikette: nur die eigene Domain syncen (`/home/hermes/ha-test/bin/sync
  <repo-dir>`), kein `bin/reset`, keine Sprachumschaltung, keine fremden Domains
  anfassen, Tokens nie kopieren.

## File Structure

- Modify: `custom_components/health_o_mat/store.py` — `pending_note`/`set_pending_note`
  plus zentrales Leeren in `add_reading`.
- Modify: `custom_components/health_o_mat/text.py` — `MeasurementNoteEntity` und
  Bereichs-Gating `AREA_BP` in `async_setup_entry`.
- Modify: `custom_components/health_o_mat/button.py` — `SaveReadingButton` übergibt die
  angefangene Notiz als `note`.
- Modify: `custom_components/health_o_mat/strings.json` — Master-Name der Entity.
- Modify: `custom_components/health_o_mat/translations/de.json` — deutscher Anzeigename.
- Modify: `custom_components/health_o_mat/translations/en.json` — englischer Anzeigename.
- Modify: `tests/test_store.py` — Store-API und Leeren in `add_reading`.
- Modify: `tests/test_wave_a.py` — Service `add_blood_pressure` leert die Notiz.
- Modify: `tests/test_ws_api.py` — WS `save_measurement` leert die Notiz.
- Modify: `tests/test_text.py` — Entity-Aufbau, Bereichs-Gating, Store-Anbindung.
- Modify: `tests/test_button.py` — Button übergibt die Notiz; `history_json`/CSV-Nachweis.
- Modify: `tests/test_translations.py` — Übersetzungs-Key in Master + de/en.
- Modify: `README.md` — Entity dokumentieren (documenter, nach Task 5).
- Modify: `docs/REQUIREMENTS.md` — REQ-HOM-010-AKs abhaken und Beleg eintragen
  (documenter, nach Task 5).
- Create: `tests_e2e/test_measurement_note_e2e.py` — Compose-/Dev-Instanz-Smoke
  (tester, Final Integration Check).

## Task-Abhängigkeiten

```
Task 1 ──┬── Task 2 ── Task 4
         └── Task 3 ── Task 5
```

Task 1 ist Voraussetzung für alle weiteren Tasks. Task 2 und Task 3 sind dateidisjunkt
und dürfen parallel laufen. Task 4 setzt Task 2 voraus (Leeren in `add_reading`), Task 5
setzt Task 3 voraus (Translation-Key). Keine Zyklen.

---

### Task 1: Store-API für die angefangene Notiz

**Agent:** developer
**Depends on:** none

**Files:**
- Modify: `custom_components/health_o_mat/store.py` — zwei Methoden neben
  `inputs`/`set_inputs` (`store.py:1112-1123`).
- Modify: `tests/test_store.py` — Roundtrip- und Leer-Tests.

**Interfaces:**
- Produces:
  - `HealthOMatStore.pending_note(self, entry_id: str) -> str` — liest
    `inputs(entry_id).get("note")`, gibt bei fehlendem/`None`-Wert `""` zurück.
  - `HealthOMatStore.set_pending_note(self, entry_id: str, value: str | None) -> None` —
    speichert `value.strip()` unter `"note"`, entfernt den Schlüssel bei leerem/`None`-Wert
    und ruft `await self._async_save()`.
- Consumes:
  - `HealthOMatStore.inputs(self, entry_id: str) -> dict` (`store.py:1112`).
  - `HealthOMatStore._async_save(self) -> Awaitable[None]` (bestehender Persistenzpfad).

- [x] **Step 1: Test schreiben (fail)** — in `tests/test_store.py`:
  `test_pending_note_roundtrip` (leer → `""`; `"  morgens  "` → `"morgens"`;
  `pending_note` liefert den Wert) und `test_set_pending_note_empty_removes_key`
  (`set_pending_note("e1", None)` und `set_pending_note("e1", "   ")` entfernen `"note"`
  aus `store.inputs("e1")`). Beide scheitern vor der Implementierung mit
  `AttributeError`.
- [x] **Step 2: implementieren** — die beiden Methoden in `store.py` direkt unter
  `clear_inputs` ergänzen; Docstrings erklären die Wiederverwendung des bestehenden
  `inputs`-Dicts und den fehlenden Schema-Bump.
- [x] **Step 3: Test (pass)** — `python3 -m pytest -q tests/test_store.py -k
  "pending_note or set_pending_note"`; danach `python3 -m pytest -q` und `ruff check .`.
- [x] **Step 4: commit** — `feat(store): add pending measurement note accessors`

---

### Task 2: Messung speichern leert die angefangene Notiz zentral

**Agent:** developer
**Depends on:** Task 1

**Files:**
- Modify: `custom_components/health_o_mat/store.py` — `add_reading` (`store.py:575-609`).
- Modify: `tests/test_store.py` — Leeren und Erhalt der übrigen Eingaben.
- Modify: `tests/test_wave_a.py` — Service-Pfad `add_blood_pressure`.
- Modify: `tests/test_ws_api.py` — WS-Pfad `health_o_mat/save_measurement`.

**Interfaces:**
- Produces: Invariante in `HealthOMatStore.add_reading(...)` — nach dem Anhängen der
  Messung wird `inputs(entry_id).pop("note", None)` ausgeführt, bevor `_async_save()`
  persistiert. Jede gespeicherte Messung konsumiert damit die angefangene Notiz.
- Consumes:
  - Task 1: `HealthOMatStore.set_pending_note`/`pending_note`.
  - Bestehende Aufrufer von `add_reading`: `__init__.py:1210` (Service),
    `ws_api.py:1533` (WS), `button.py:151` (Button), `importer.py:794` (CSV-Import).
  - `tests/test_wave_a.py::_services_hass` und `tests/test_ws_api.py::_write_hass`
    als bestehende Test-Harnesses.

- [x] **Step 1: Test schreiben (fail)**:
  - `tests/test_store.py::test_add_reading_clears_pending_note` — `set_pending_note`
    mit `"morgens"`, `add_reading(..., note="morgens")`, danach
    `pending_note("e1") == ""` und `"note" not in inputs("e1")`.
  - `tests/test_store.py::test_add_reading_preserves_other_inputs` — `sys`/`dia` bleiben
    nach `add_reading` erhalten.
  - `tests/test_wave_a.py::test_req_hom_010_add_blood_pressure_service_clears_pending_note`
    — echte `HealthOMatStore`-Instanz, Notiz setzen, Service mit `note="morgens"` rufen,
    Messung trägt `"morgens"`, `pending_note` ist leer.
  - `tests/test_ws_api.py::test_req_hom_010_save_measurement_clears_pending_note` — echte
    `HealthOMatStore`-Instanz im `_write_hass`-Harness, Notiz setzen, WS-Nachricht mit
    `note="morgens"` senden, Messung trägt `"morgens"`, `pending_note` ist leer.
  Alle vier scheitern vor der Implementierung, weil die Notiz im `inputs`-Dict bleibt.
- [x] **Step 2: implementieren** — in `add_reading` nach
  `self.entry(entry_id)["readings"].append(reading)` und vor `_append_audit`/`_async_save`
  `self.inputs(entry_id).pop("note", None)` einfügen. Kommentar: zentraler Choke-Point,
  damit Service, WS, Button und Import nicht drei separate Leer-Pfade brauchen; der
  CSV-Import konsumiert die Notiz bewusst mit.
- [x] **Step 3: Test (pass)** — `python3 -m pytest -q tests/test_store.py
  tests/test_wave_a.py tests/test_ws_api.py`; danach `python3 -m pytest -q` und
  `ruff check .`.
- [x] **Step 4: commit** — `feat(store): clear pending measurement note on save`

---

### Task 3: Text-Entity `measurement_note` mit Blutdruck-Gating

**Agent:** developer
**Depends on:** Task 1

**Files:**
- Modify: `custom_components/health_o_mat/text.py` — `MeasurementNoteEntity` plus
  `AREA_BP`-Zweig in `async_setup_entry`.
- Modify: `tests/test_text.py` — Setup-, Identitäts- und Store-Tests.

**Interfaces:**
- Produces:
  - `class MeasurementNoteEntity(HealthOMatEntity, TextEntity)` mit
    `__init__(self, coordinator, entry, store) -> None` (speichert `self._store = store`
    und ruft `super().__init__(coordinator, entry, "text_measurement_note")`),
    `_attr_translation_key = "measurement_note"`,
    `_attr_icon = "mdi:note-text-outline"`, `_attr_native_max = 255`,
    `_attr_mode = "text"` ⇒ `unique_id = f"{entry.entry_id}_text_measurement_note"`.
  - `native_value(self) -> str` — `self._store.pending_note(self._entry.entry_id)`.
  - `async_set_value(self, value: str) -> None` —
    `await self._store.set_pending_note(self._entry.entry_id, value)`.
  - `async_setup_entry` fügt die Entity nur hinzu, wenn
    `areas.active_areas(entry.options)[areas.AREA_BP]` wahr ist; der bestehende
    `AREA_DRINK`-Zweig bleibt unverändert.
- Consumes:
  - Task 1: `HealthOMatStore.pending_note`/`set_pending_note`.
  - `HealthOMatEntity` (`entity.py:14-70`) für `unique_id`, `device_info`,
    `has_entity_name` und `suggested_object_id`-Pinning.
  - `areas.active_areas`/`areas.AREA_BP` (`areas.py:21-33`).

- [x] **Step 1: Test schreiben (fail)** — in `tests/test_text.py`:
  - `test_measurement_note_entity_created_when_bp_active` — `_text_setup({})` enthält
    `"test-entry-1_text_measurement_note"` zusätzlich zu `text_freetext`.
  - `test_measurement_note_entity_absent_when_bp_disabled` — `{"areas": {"bp": False}}`
    liefert nur `text_freetext`.
  - `test_measurement_note_unique_id_is_stable` — De-/Reaktivieren von `bp` erzeugt
    dieselbe `unique_id`.
  - `test_measurement_note_native_value_reads_store` — Store-Fake mit
    `pending_note.return_value = "morgens"` ⇒ `native_value == "morgens"`.
  - `test_measurement_note_async_set_value_writes_store` — `async_set_value("abends")`
    ruft `store.set_pending_note("e1", "abends")` awaitet auf.
  - `test_measurement_note_has_translation_key_and_no_name_literal` —
    `_attr_translation_key == "measurement_note"`, `_attr_has_entity_name is True`,
    kein `_attr_name`/`name`-Literal in der Klasse.
  - **Bestehende Setup-Tests anpassen**, weil `text.py` künftig zwei Entities kennt:
    `test_text_setup_old_entry_without_options_has_drink_area` erwartet
    `{_FREETEXT_ID, _NOTE_ID}`; `test_text_setup_drink_disabled_creates_no_entity` wird
    zu `test_text_setup_drink_disabled_creates_no_freetext_entity` und erwartet
    `{_NOTE_ID}` (BP bleibt aktiv); `test_text_setup_only_drink_when_bp_and_wellbeing_disabled`
    bleibt bei `{_FREETEXT_ID}`; `test_text_unique_ids_stable_across_area_toggle` bleibt
    gültig, weil beide Sets die Notiz-Entity enthalten.
  Alle neuen Tests scheitern vor der Implementierung (Klasse/Setup-Zweig fehlt); die
  angepassten Bestandstests werden mit der Implementierung grün.
- [x] **Step 2: implementieren** — in `text.py`:
  `active = areas.active_areas(entry.options)` einmal berechnen, Entity-Liste aufbauen,
  `FreeTextDrinkEntity` bei `AREA_DRINK`, `MeasurementNoteEntity` bei `AREA_BP`,
  `async_add_entities(entities)` einmal aufrufen. Die neue Klasse unter
  `FreeTextDrinkEntity` einfügen; `native_value`/`async_set_value` exakt wie oben.
  Kein `signal_refresh` im Setter nötig: HA schreibt den Entity-State nach
  `async_set_value`; das Leeren durch Service/WS löst bereits `signal_refresh` aus.
- [x] **Step 3: Test (pass)** — `python3 -m pytest -q tests/test_text.py`; danach
  `python3 -m pytest -q` und `ruff check .`.
- [x] **Step 4: commit** — `feat(text): add measurement note entity`

---

### Task 4: Button übergibt die Notiz; Nachweis in `history_json` und CSV

**Agent:** developer
**Depends on:** Task 2

**Files:**
- Modify: `custom_components/health_o_mat/button.py` — `SaveReadingButton.async_press`
  (`button.py:135-163`).
- Modify: `tests/test_button.py` — Button-Übergabe plus `history_json`/CSV-Nachweis mit
  echter `HealthOMatStore`-Instanz.

**Interfaces:**
- Produces:
  - `SaveReadingButton.async_press` liest
    `note = self._store.pending_note(self._entry.entry_id)` und übergibt `note` als
    sechstes Positionsargument an `add_reading` (statt `""`); danach bleibt
    `await self._store.clear_inputs(...)` bestehen.
  - Regressionstests, die belegen: die Notiz steht im Mess-Dict, in
    `BloodPressureHistorySensor.extra_state_attributes["history_json"]` und in der
    CSV-Zeile `health_o_mat_bloodpressure_*.csv` (Spalte `notiz`).
- Consumes:
  - Task 1: `HealthOMatStore.pending_note`.
  - Task 2: `add_reading` leert die Notiz.
  - `sensor.BloodPressureHistorySensor` (`sensor.py:233-255`) und
    `exporter.async_export_csv` (`exporter.py:51-150`) nur im Test.

- [x] **Step 1: Test schreiben (fail)** — in `tests/test_button.py`:
  - `test_save_reading_consumes_pending_note_and_clears_it` — echte
    `HealthOMatStore`-Instanz (gemocktes HA-`Store`-Backend), `sys=120`/`dia=80` und
    `pending_note="morgens"` setzen, `SaveReadingButton.async_press()` ausführen;
    `store.entry("e1")["readings"][0]["note"] == "morgens"` und
    `store.pending_note("e1") == ""`.
  - `test_save_reading_note_visible_in_history_json_and_csv` — nach demselben Press
    `BloodPressureHistorySensor` mit dem Store bauen und `"morgens"` in
    `extra_state_attributes["history_json"]` prüfen; `exporter.async_export_csv` mit
    einem `ServiceCall`-Fake (`_call({"dataset": "blood_pressure"})`, wie in
    `tests/test_import_backup.py`) und `tmp_path` aufrufen und `"morgens"` in der
    CSV-Zeile prüfen. Vor der Implementierung ist die Notiz `""`, beide Assertions
    scheitern.
- [x] **Step 2: implementieren** — in `SaveReadingButton.async_press` die Zeile
  `note = self._store.pending_note(self._entry.entry_id)` vor `add_reading` einfügen und
  `""` durch `note` ersetzen. `clear_inputs` bleibt unverändert (leert `sys`/`dia`/
  `pulse`; `note` wurde bereits in `add_reading` entfernt).
- [x] **Step 3: Test (pass)** — `python3 -m pytest -q tests/test_button.py`; danach
  `python3 -m pytest -q` und `ruff check .`.
- [x] **Step 4: commit** — `feat(button): save pending measurement note with reading`

---

### Task 5: Übersetzungen für `measurement_note`

**Agent:** developer
**Depends on:** Task 3

**Files:**
- Modify: `custom_components/health_o_mat/strings.json` — Master
  `entity.text.measurement_note.name`.
- Modify: `custom_components/health_o_mat/translations/de.json` — deutscher Name.
- Modify: `custom_components/health_o_mat/translations/en.json` — englischer Name.
- Modify: `tests/test_translations.py` — expliziter Key-Test zusätzlich zur
  bestehenden Paritätsprüfung.

**Interfaces:**
- Produces: `entity.text.measurement_note.name` in allen drei Dateien; Master/Englisch
  `"Measurement note"`, Deutsch `"Mess-Notiz"`. Der Key entspricht exakt
  `MeasurementNoteEntity._attr_translation_key`.
- Consumes:
  - Task 3: `_attr_translation_key = "measurement_note"`.
  - `tests/test_translations.py::_load`/`_all_paths` und
    `test_req_hom_107_key_tree_parity`.

- [x] **Step 1: Test schreiben (fail)** — in `tests/test_translations.py`:
  `test_req_hom_010_measurement_note_translation_present` lädt alle drei Dateien, prüft
  `entity.text.measurement_note.name` vorhanden und nicht leer, und dass der deutsche
  Wert vom englischen abweicht. Scheitert vor der Implementierung mit `KeyError`.
- [x] **Step 2: implementieren** — den Key in `strings.json`, `translations/de.json` und
  `translations/en.json` unter dem bestehenden `"text"`-Block ergänzen (neben
  `"freetext"`).
- [x] **Step 3: Test (pass)** — `python3 -m pytest -q tests/test_translations.py`;
  insbesondere bleibt `test_req_hom_107_key_tree_parity` für `de` und `en` grün.
- [x] **Step 4: commit** — `feat(i18n): add measurement note entity name`

---

## Final Integration Check

- [x] `python3 -m pytest -q` — alle bestehenden Tests plus die neuen
  `test_req_hom_010_*`/`test_measurement_note_*`-Tests grün, keine Regression.
- [x] `ruff check .` und `ruff format --check .` — clean.
- [ ] `python3 -m compileall -q custom_components/health_o_mat` — ohne Fehler.
- [ ] Dev-Instanz (`/home/hermes/ha-test`): `/home/hermes/ha-test/bin/sync <repo-dir>`,
  danach pro Person prüfen: `text.*_measurement_note` existiert nur bei aktivem
  Blutdruck-Bereich; Notiz setzen → `save_reading` drücken → Feld ist leer, Notiz steht
  in `sensor.*_blood_pressure_history` (`history_json`) und im Blutdruck-CSV. Nur die
  eigene Domain syncen, kein `bin/reset`, keine Sprachumschaltung.
- [x] `tester`: Compose-/Dev-Instanz-Smoke in
  `tests_e2e/test_measurement_note_e2e.py` (Create) — Entity anlegen, Notiz setzen,
  Speichern, Leerung und CSV-Sichtbarkeit prüfen. **7 E2E-Tests, 7 passed**
  (Compose-Stack 8124, inkl. Service-Pfad).
- [x] `documenter`: `README.md` um die Entity ergänzen; in `docs/REQUIREMENTS.md`
  REQ-HOM-010 auf **Erledigt** ziehen, beide AKs abhaken und die Belege
  (`store.py`, `text.py`, `button.py`, Testnamen) eintragen.
- [ ] Release: **MINOR 0.20.0** durch den `release`-Agenten (Tag `v0.20.0` + echtes
  GitHub-Release). Kein `manifest.version`-Bump in diesem Plan; kein
  `async_migrate_entry`, kein Config-Entry-Versionswechsel, keine `unique_id`-Änderung.

## Self-Review

**AK → Task → Test:**

| Akzeptanzkriterium | Task | Test |
|---|---|---|
| Feld nach Speichern geleert | 1 (API), 2 (zentrales Leeren), 4 (Button-Pfad) | `test_add_reading_clears_pending_note`, `test_req_hom_010_add_blood_pressure_service_clears_pending_note`, `test_req_hom_010_save_measurement_clears_pending_note`, `test_save_reading_consumes_pending_note_and_clears_it` |
| Notiz in `history_json` sichtbar | 4 | `test_save_reading_note_visible_in_history_json_and_csv`; Beleg `sensor.py:255` |
| Notiz im CSV sichtbar | 4 | `test_save_reading_note_visible_in_history_json_and_csv`; Beleg `exporter.py:142` |
| Entity pro Person, stabile `unique_id`, `device_info` | 3 | `test_measurement_note_entity_created_when_bp_active`, `test_measurement_note_unique_id_is_stable` |
| Kein Namens-Literal, `has_entity_name`/`translation_key` | 3, 5 | `test_measurement_note_has_translation_key_and_no_name_literal`, `test_req_hom_010_measurement_note_translation_present` |

**Task-Vollständigkeit:** Jeder Task hat `**Files:**` (Modify/Create + Test) und
`**Interfaces:**` mit nicht-leeren `Produces`/`Consumes`-Angaben. Jeder Task folgt dem
TDD-Zyklus Test (fail) → implementieren → Test (pass) → commit.

**Graph/Overlap:** Task 1 → Task 2 → Task 4 und Task 1 → Task 3 → Task 5; keine Zyklen.
Task 2 und Task 3 sind parallelisierbar (disjunkte Dateien: `store.py`/`test_store.py`/
`test_wave_a.py`/`test_ws_api.py` vs. `text.py`/`test_text.py`). Task 4 und Task 5 sind
parallelisierbar (disjunkte Dateien: `button.py`/`test_button.py` vs. drei JSON-Dateien/
`test_translations.py`). Task 1 und Task 2 teilen `store.py` und `test_store.py` und
müssen sequenziell laufen.

**Bewusste Entscheidungen und Belege:**

1. **Ablage:** `store.inputs["note"]` statt In-Memory. Beleg: `InputNumber` persistiert
   `sys`/`dia`/`pulse` bereits dort (`number.py:164-215`, `store.py:1112-1123`); das
   `inputs`-Dict existiert seit Store-Schema v2 (`store.py:1-5`), also kein Migrator.
   Ein In-Memory-Feld wie `FreeTextDrinkEntity._native_value` würde die Notiz bei
   Neustart verlieren und wäre für den Button nicht lesbar.
2. **Leeren:** zentral in `add_reading` (`store.py:575-609`), nicht in den Handlern.
   Beleg: genau vier Aufrufer (`__init__.py:1210`, `ws_api.py:1533`, `button.py:151`,
   `importer.py:794`) — ein Choke-Point deckt Service, WS, Button und Import ab.
3. **Bereich:** `AREA_BP`. Beleg: `note` ist ein Feld von `readings`
   (`store.py:582-594`), `save_measurement` ist Blutdruck (`ws_api.py:1506-1542`), und
   `set_wellbeing` hat keinen `note`-Parameter. Bei inaktivem BP-Bereich wird keine
   Entity angelegt; die Notiz bleibt im Store und erscheint beim Reaktivieren wieder.
4. **Identität:** `{entry_id}_text_measurement_note`, `translation_key
   "measurement_note"`, `has_entity_name` geerbt, Icon `mdi:note-text-outline`,
   `native_max = 255`, `mode = "text"`. Beleg für das Plattform-Präfix:
   `text_freetext` (`text.py:20-31`) und `_FREETEXT_ID = "test-entry-1_text_freetext"`
   (`tests/test_text.py:70-72`).
5. **CSV/History:** bereits vorhanden — `sensor.py:255` dumpt die Mess-Dicts inkl.
   `note`; `exporter.py:142` schreibt `r.get("note", "")`; `importer.py:387` liest
   `cells[5]` und akzeptiert fehlende Spalte. Keine Spalte wird geändert; Task 4 pinnt
   den Ist-Zustand mit Regressionstests.
6. **Migration:** keine. `manifest.version` bleibt in diesem Plan unverändert (Release
   0.20.0 MINOR durch den `release`-Agenten), `ConfigFlow.VERSION = 3` bleibt
   (`config_flow.py:251`), `STORE_SCHEMA_VERSION` bleibt, bestehende `unique_id`s
   bleiben. Die neue `unique_id` ist additiv. Klassifikation: **MINOR**, kein PATCH,
   weil eine neue Entity entsteht.

**Ambiguitäten/Widersprüche in der Vorlage (aufgelöst):**

- Der Welle-2-AK in `docs/PLAN-BACKLOG-2026-11-02.md:175` nennt
  `unique_id = {entry_id}_measurement_note`; die Code-Konvention lautet
  `{entry_id}_text_<translation_key>` (`text_freetext`). Dieser Plan folgt der
  Code-Konvention (`text_measurement_note`), weil sie die bestehende Identitätsform
  wahrt und die Backlog-Zeile die einzige abweichende Stelle ist.
- Der Welle-2-Zieltext nennt „BP- und Wohlbefinden-Erfassung"; Wohlbefinden hat im Code
  keinen `note`-Parameter. Dieser Plan gated die Entity ausschließlich auf `AREA_BP`.
- Die REQ-Zeilenanker sind gegen `46c4513` verschoben: `__init__.py:1092` →
  `add_blood_pressure` bei `1204`; `store.py:582-594` → `575-609`; `ws_api.py:1124` →
  `1127`. Kein Widerspruch, nur Drift.
- „`save_measurement`" ist das WS-Kommando; der HA-Service heißt `add_blood_pressure`.
  Beide rufen `add_reading` auf und werden durch Task 2 abgedeckt.
- „Feld nach Speichern geleert" wird bewusst auf **jede** gespeicherte Messung
  ausgedehnt (auch Service/Import mit expliziter Notiz), weil `add_reading` der einzige
  Choke-Point ist. Wer nur den UI-Button leeren will, müsste die Leerung in die Handler
  verschieben — dann entstünde genau die Duplikation, die Task 2 vermeidet.
- Die Text-Entity begrenzt die UI-Eingabe auf 255 Zeichen; der Service `note`-Parameter
  bleibt unbegrenzt (kein Breaking Change, keine neue Validierung).

**Nachtrag:** Nach dem Validator-Befund ist die Entscheidung „nur der Button liest die angefangene Notiz" überholt — Service `add_blood_pressure` und WS-Kommando `health_o_mat/save_measurement` lösen sie jetzt ebenfalls über `resolve_reading_note` auf (explizite Notiz gewinnt, sonst die angefangene), der Button übergibt sie weiterhin explizit, und das Leeren bleibt allein in `HealthOMatStore.add_reading`; offen sind nur noch der `compileall`-Nachweis und der Release 0.20.0 — der E2E-Lauf ist erledigt (5 → 7 Szenarien, **7 E2E-Tests, 7 passed** (Compose-Stack 8124, inkl. Service-Pfad)).

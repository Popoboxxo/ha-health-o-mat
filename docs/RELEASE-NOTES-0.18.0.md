# v0.18.0 — Service-Antworten, WS-CSV-Import und strengerer Import

## Zusammenfassung

Minor-Release mit zwei neuen Schnittstellen und drei bewussten
Verhaltensänderungen. **Neu:** `export_csv`, `import_csv`, `backup`,
`restore_backup` und `weekly_report` können auf Wunsch eine maschinenlesbare
Antwort zurückgeben (opt-in), und der WebSocket-Command
`health_o_mat/import_csv` importiert CSV-Inhalte direkt — aus einer Datei oder
aus einem String. **Geändert:** Der Import ist jetzt admin-only, die
Blutdruck-Warnschwelle ist inklusiv (`>= 140/90`), und eine Korrekturzeile mit
identischem Zeitstempel und Marker gilt als Duplikat statt als zusätzlicher
Eintrag.

> ⚠️ **Handlungshinweis — bitte vor dem Update lesen.** 0.18.0 ändert das
> Verhalten bestehender Aufrufe (Abschnitt „💥 Breaking changes"). Es gibt
> **keine Datenmigration**: `unique_id`s, Entity-IDs, Store-Schema
> (`schema: 5`) und `config entry`-Version (3) bleiben unverändert. Wer den
> CSV-Import aus einer Automation oder einem Skript ohne `user_id` aufruft,
> muss diesen Aufruf nach dem Update anpassen.

## ✨ New features

### Service-Antworten (opt-in) — REQ-HOM-132, Issue #71

`export_csv`, `import_csv`, `backup`, `restore_backup` und `weekly_report`
liefern auf Wunsch ein Ergebnis an den Aufrufer zurück (`supports_response`).
Die Antwort ist flach gehalten (keine verschachtelten Objekte) und bleibt damit
direkt in Templates/Automationen auswertbar. Die Fehlerliste ist auf **20
Einträge** gedeckelt, damit eine kaputte CSV die Antwort nicht unbegrenzt
aufbläht; **Fehler bleiben Exceptions** — ein Service-Aufruf, der scheitert,
scheitert weiterhin sichtbar und wird nicht zu einer stillen Antwort mit
`errors`. Bestehende Aufrufe ohne Antwort-Auswertung verhalten sich unverändert.

### WebSocket-Command `health_o_mat/import_csv` — Issue #72

Der Import läuft jetzt auch über einen WS-Command und akzeptiert wahlweise
`filename` (Datei im Import-Ordner) **oder** `content` (CSV-Text, UTF-8, max.
**2 MiB**). Der Export-Ordner ist zusätzlich als CSV-Quelle freigegeben, sodass
eine zuvor exportierte Datei ohne Umkopieren wieder eingelesen werden kann.
`filename` und `content` schließen sich gegenseitig aus.

### Labor-Import atomar je Bericht

Ein Labor-Bericht wird als Ganzes gespeichert: ein Speichervorgang je Dataset
und ein Rollback über **alle** Gruppen des Berichts. Ein fehlerhafter Wert in
Zeile n kann damit keinen halb geschriebenen Bericht mehr hinterlassen.

### Kanonische Dedupe über `(ts, marker_key)`

Store, Import und Einzel-Add benutzen dieselbe Regel für die Duplikaterkennung:
`(ts, marker_key)` ist der Schlüssel. Damit ist „ist der Wert schon da?"
unabhängig davon, über welchen Weg er hereinkommt.

## 💥 Breaking changes

### 1. Import ist admin-only

Sowohl der Service `health_o_mat.import_csv` als auch der WS-Command
`health_o_mat/import_csv` verlangen jetzt einen Admin-User.

- **Betroffen:** Automationen, Skripte und Dashboards, die den Import bisher
  als normaler Nutzer oder in einem Kontext **ohne `user_id`** aufgerufen haben.
  Diese Aufrufe importieren **nicht mehr stillschweigend**.
- **Handlung:** Import-Aufrufe von einem Admin-Konto ausführen (bzw.
  `user_id` eines Admin-Users mitgeben). Fehlt der Admin-Kontext, meldet der
  Aufruf einen Berechtigungsfehler, statt Daten zu schreiben.
- **Nicht betroffen:** Export, Backup, Restore und alle Erfassungs-Services —
  ihr Berechtigungsverhalten ist unverändert.

### 2. Blutdruck-Warnschwelle ist inklusiv (`>= 140/90`)

Bisher war das Panel bei **exakt** 140/90 still, während der Binary Sensor
bereits warnte. Ab 0.18.0 gilt die Schwelle einschließlich des Grenzwerts:
Panel/Kachel und Binary Sensor liefern dasselbe Ergebnis.

- **Handlung:** Wer sich auf „140/90 ist noch normal" verlassen hat (z. B. in
  einer Automation auf den Panel-Zustand), bekommt dort jetzt eine Warnung.
  Die Grenzwerte selbst sind unverändert konfigurierbar.

### 3. Korrekturzeile mit gleichem `(ts, marker_key)` wird abgelehnt

Eine CSV-Zeile mit identischem Zeitstempel und Marker, aber **anderem Wert**,
gilt künftig als `skipped` mit Grund `duplicate_marker`; vorher konnte sie
zusätzlich angelegt werden.

- **Handlung:** Soll ein bereits importierter Wert korrigiert werden, muss der
  alte Eintrag zuerst über `void_entry` (bzw. `void` im Panel) entfernt werden —
  dann greift der Import. Import-Ergebnisse auf `skipped`/`duplicate_marker`
  prüfen, wenn bisher mit „zweiten Zeilen" korrigiert wurde.

### 4. `scripts/e2e_bootstrap.py` gibt keine Geheimnisse mehr aus

Das Bootstrap-Skript schreibt in `--json-out` und auf stdout keine Passwörter
oder Tokens mehr. Nur relevant, wenn das Skript außerhalb der E2E-Kette
verwendet wird; innerhalb der Test-Suite ändert sich nichts.

### Was unverändert bleibt

- **`unique_id`s und Entity-IDs** — unverändert; keine Entity-Registry-Migration
- **Store-Schema** — `schema: 5`; bestehende Getränke-, Blutdruck-, Wohlbefinden-
  und Labordaten werden nicht angefasst
- **`config entry`-Version** — 3, kein `async_migrate_entry`-Schritt nötig
- **Panel-/Card-Registrierung** — Versions-Query (`?v=0.18.0`),
  `PANEL_VERSION` und `CARD_VERSION` sind mitgezogen

## Upgrade

1. Update über HACS installieren.
2. Home Assistant neu starten (ein Reload genügt der Integration; der Neustart
   ist für das Frontend-Caching der Panel-Module der sichere Weg).
3. Import-Aufrufe prüfen: Admin-Kontext sicherstellen (Punkt 1), Grenzwert-
   Erwartung bei 140/90 anpassen (Punkt 2), Korrektur-Workflow auf
   `void` + Re-Import umstellen (Punkt 3).
4. Es gibt nichts zu migrieren.

## Kompatibilität

- `manifest.version` 0.18.0; `config entry`-Version 3 (unverändert).
- Store-Schema 5 (unverändert) — Bestandsdaten bleiben unberührt.
- Die neuen Service-Antworten sind opt-in; Aufrufe ohne Antwort-Auswertung
  sehen keinen Unterschied.

## Vollständiger Changelog

https://github.com/Popoboxxo/ha-health-o-mat/compare/v0.17.3...v0.18.0

---

# v0.18.0 — Service responses, WS CSV import and a stricter import

## Summary

Minor release with two new interfaces and three deliberate behaviour changes.
**New:** `export_csv`, `import_csv`, `backup`, `restore_backup` and
`weekly_report` can return a machine-readable response (opt-in), and the
WebSocket command `health_o_mat/import_csv` imports CSV content directly —
either from a file or from a string. **Changed:** the import is admin-only now,
the blood-pressure warning threshold is inclusive (`>= 140/90`), and a
correction row with an identical timestamp and marker counts as a duplicate
instead of an additional entry.

> ⚠️ **Action required — please read before updating.** 0.18.0 changes the
> behaviour of existing calls (see "💥 Breaking changes"). There is **no data
> migration**: `unique_id`s, entity ids, the store schema (`schema: 5`) and the
> `config entry` version (3) stay unchanged. Anyone calling the CSV import from
> an automation or script without a `user_id` must adjust that call after the
> update.

## ✨ New features

### Service responses (opt-in) — REQ-HOM-132, issue #71

`export_csv`, `import_csv`, `backup`, `restore_backup` and `weekly_report`
return a result to the caller on request (`supports_response`). The response is
flat (no nested objects), so it can be consumed directly in templates and
automations. The error list is capped at **20 entries** so a broken CSV cannot
bloat the response without bound; **errors stay exceptions** — a service call
that fails still fails visibly instead of turning into a quiet response with
`errors`. Existing calls that do not evaluate a response behave unchanged.

### WebSocket command `health_o_mat/import_csv` — issue #72

The import is also available as a WS command and accepts either `filename`
(a file in the import folder) **or** `content` (CSV text, UTF-8, max. **2 MiB**).
The export folder is additionally allowed as a CSV source, so a previously
exported file can be re-read without copying it. `filename` and `content` are
mutually exclusive.

### Lab import atomic per report

A lab report is stored as a whole: one write per dataset and a rollback across
**all** groups of the report. A faulty value in row n can no longer leave a
half-written report behind.

### Canonical dedupe on `(ts, marker_key)`

Store, import and single-add use the same duplicate rule: `(ts, marker_key)` is
the key. "Is this value already there?" no longer depends on the path it came
in through.

## 💥 Breaking changes

### 1. Import is admin-only

Both the `health_o_mat.import_csv` service and the
`health_o_mat/import_csv` WS command now require an admin user.

- **Affected:** automations, scripts and dashboards that called the import as a
  regular user or in a context **without a `user_id`**. Those calls no longer
  import silently.
- **Action:** run import calls from an admin account (or pass an admin
  `user_id`). Without admin context the call reports a permission error instead
  of writing data.
- **Not affected:** export, backup, restore and all capture services — their
  permission behaviour is unchanged.

### 2. Blood-pressure warning threshold is inclusive (`>= 140/90`)

Previously the panel stayed quiet at **exactly** 140/90 while the binary sensor
already warned. From 0.18.0 the threshold includes the limit value: panel/tile
and binary sensor now agree.

- **Action:** if you relied on "140/90 is still normal" (e.g. an automation
  watching the panel state), you get a warning there now. The thresholds
  themselves stay configurable.

### 3. A correction row with the same `(ts, marker_key)` is rejected

A CSV row with an identical timestamp and marker but a **different value** now
counts as `skipped` with reason `duplicate_marker`; previously it could be
added on top.

- **Action:** to correct an already imported value, void the old entry first
  (`void_entry`, or `void` in the panel) — then the import applies. Watch import
  results for `skipped`/`duplicate_marker` if you used to correct via a second
  row.

### 4. `scripts/e2e_bootstrap.py` no longer prints secrets

The bootstrap script writes no passwords or tokens to `--json-out` or stdout.
Only relevant when the script is used outside the E2E chain; nothing changes
inside the test suite.

### What stays

- **`unique_id`s and entity ids** — unchanged; no entity-registry migration
- **Store schema** — `schema: 5`; existing drink, blood-pressure, wellbeing and
  lab data is untouched
- **`config entry` version** — 3, no `async_migrate_entry` step required
- **Panel/card registration** — the version query (`?v=0.18.0`), `PANEL_VERSION`
  and `CARD_VERSION` are bumped along

## Upgrade

1. Install the update via HACS.
2. Restart Home Assistant (a reload is enough for the integration; the restart
   is the safe route for the panel module caching).
3. Review import calls: ensure admin context (point 1), adjust the expectation
   at 140/90 (point 2), move corrections to `void` + re-import (point 3).
4. There is nothing to migrate.

## Compatibility

- `manifest.version` 0.18.0; `config entry` version 3 (unchanged).
- Store schema 5 (unchanged) — existing data is untouched.
- The new service responses are opt-in; calls that ignore the response see no
  difference.

## Full changelog

https://github.com/Popoboxxo/ha-health-o-mat/compare/v0.17.3...v0.18.0

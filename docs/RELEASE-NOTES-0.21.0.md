# v0.21.0 — Mess-Notiz, Ziel-Blueprint, strukturierter Fehler-Katalog

## Zusammenfassung

Minor-Release mit drei Schwerpunkten: eine **Mess-Notiz-Entity** pro Person
(REQ-HOM-010), ein **vierter Blueprint** für das Tagesziel (`goal_reached`) und
ein **strukturierter Fehler-Katalog** mit **35 stabilen Codes** (REQ-HOM-127),
der freie deutsche Fehlertexte ersetzt und Service-, WebSocket- und
Frontend-Fehler lokalisierbar macht. Dazu kommen Härtungen: blockierendes I/O
in Import, Restore, WebSocket-API und Diagnostics läuft jetzt im Executor,
Änderungen an den Quick-Drink-Optionen greifen sofort, und der `goal_reached`-
Blueprint rendert den Personennamen korrekt.

> ⚠️ **Handlungshinweis — bitte vor dem Update lesen.** Wer Fehlertexte in
> Automationen, Skripten oder Templates auswertet, muss auf `code`/`params`
> umstellen (siehe „💥 Breaking changes"). Es gibt **keine** Datenmigration:
> `unique_id`s, Entity-IDs, Store-Schema (`5`) und Config-Entry-Version (`3`)
> bleiben unverändert.

## ✨ New features

### Mess-Notiz-Entity — REQ-HOM-010

Pro Person mit aktivem Blutdruck-Bereich entsteht eine Text-Entity
`text.<person>_measurement_note`. Sie hält eine Notiz für die **nächste**
Blutdruck-Messung:

- Die angefangene Notiz überlebt einen Neustart (sie liegt im bereits
  persistierten `store.inputs` — **kein** Schema-Bump, kein Migrator).
- Sie wird zentral beim Speichern einer Messung geleert und von **allen**
  Schreibpfaden verwendet: Speichern-Button, Service `add_blood_pressure`,
  WebSocket-Kommando `health_o_mat/save_measurement` und CSV-Import.
- Die Notiz erscheint in `history_json` und in der Blutdruck-CSV-Spalte
  `notiz` (Spalte additiv, Bestandsimporte unverändert).
- Scope: nur Blutdruck (`set_wellbeing` hat keinen `note`-Parameter).

### Blueprint `goal_reached`

Der vierte Blueprint (`blueprints/automation/health_o_mat/goal_reached.yaml`)
benachrichtigt einmal pro Zustandswechsel (`aus` → `ein`) des Binärsensors
„Tagesziel erreicht". Er benötigt **keinen Helfer**: fällt der Sensor kurz
zurück und wird das Ziel erneut überschritten, kommt eine weitere Meldung.

### Strukturierter Fehler-Katalog — REQ-HOM-127

Fehler sind keine freien Prosa-Texte mehr, sondern ein Katalog mit **35
stabilen Codes**:

- **29 Service-** und **32 WebSocket-Aufrufstellen** sowie **4 Relay-Helfer**
  liefern `code` + typisierte `params`.
- **35 deutsche und 35 englische Übersetzungen** liegen vor; das Frontend löst
  Fehler über den `code` auf, nicht über Textvergleich.
- Das **Batch-Envelope bleibt unverändert**.

## 💥 Breaking changes / Aktionshinweise

Es gibt **keine** Änderung an `unique_id`s, Entity-IDs, Store-Schema
(`schema: 5`) oder Config-Entry-Version (`3`). Die folgenden Punkte sind
trotzdem vor dem Update zu lesen.

### 1. Fehlertexte sind neutral und lokalisiert

Die Meldungstexte sind nicht mehr die bisherigen deutschen Prosa-Sätze,
sondern werden aus Code und Parametern erzeugt.

- **Betroffen:** Automationen, Skripte und Templates, die deutsche Fehlertexte
  parsen oder auf Teilstrings prüfen (z. B. `unit_required`-Meldungen,
  Import-Fehlerlisten).
- **Handlung:** Auf `code` (und `params`) umstellen. Die Codes sind stabil und
  dokumentiert; sie ändern sich nicht mit der Systemsprache.
- **Nicht betroffen:** Aufrufer, die nur auf Erfolg/Fehler als solches
  reagieren.

### 2. Zusätzliche `translation_*`-Felder in Fehlerobjekten

Service- und WebSocket-Fehlerobjekte tragen jetzt zusätzlich
`translation_domain`, `translation_key` und `translation_placeholders`. Das
**Batch-Envelope ist unverändert**.

- **Betroffen:** Clients mit striktem Schema über Fehlerobjekte.
- **Handlung:** Die zusätzlichen Felder im Schema zulassen oder ignorieren.

### 3. Neue Text-Entity pro Person

Mit aktivem Blutdruck-Bereich erscheint `text.<person>_measurement_note`.

- **Betroffen:** Dashboards, die Entitäten automatisch einbinden
  (z. B. Auto-Entities), und Automationen, die über alle Text-Entitäten laufen.
- **Handlung:** Keine Migration nötig — die Entity erscheint einfach. Wer sie
  nutzen will, nimmt sie ins Dashboard auf.

### Was unverändert bleibt

- **`unique_id`s und Entity-IDs** — unverändert; keine Entity-Registry-Migration
- **Store-Schema** — `5`; Bestandsdaten werden nicht angefasst, keine
  Store-Migration
- **Config-Entry-Version** — `3`; kein `async_migrate_entry`-Schritt nötig
- **Batch-Envelope** — unverändert

## 🔧 Fixes

- **Blockierendes I/O vom Event-Loop genommen:** `list_import_files`,
  `safe_import_path` (Pfadvalidierung beim Import), `safe_restore_path`
  (Pfadvalidierung beim Restore) und das Lesen der Manifest-Version in den
  Diagnostics laufen jetzt im Executor.
- **Quick-Drink-Optionen greifen sofort:** Eine Änderung der Mengen lädt die
  Buttons neu — vorher wurde bis zum manuellen Reload der alte Betrag gebucht.
- **`goal_reached`: `person_name` wurde nie gerendert.** Blueprint-Inputs sind
  in Templates nicht automatisch als Variable verfügbar; der Name ist jetzt
  explizit über einen `variables:`-Block gebunden.
- **E2E-Stack:** Das E2E-Image enthält `blueprints/`, und der E2E-Workflow
  triggert auch bei Blueprint-Änderungen.

## Verifikation

| Prüfung | Ergebnis |
|---|---|
| Unit-Tests (`pytest`) | **1865 passed** |
| E2E-Tests | **73 passed** |
| `ruff check` / `ruff format --check` | clean |
| `compileall` | clean |

> Hinweis: Der reale **HACS-Update-Test** (Update von 0.19.0 auf 0.21.0 über
> HACS auf einer bestehenden Installation) ist **manuell** und nicht Teil dieser
> Verifikation.

## Upgrade

1. Update über HACS installieren.
2. Home Assistant neu starten (für das Frontend-Caching der Panel-Module der
   sichere Weg).
3. Fehlertext-Auswerter auf `code`/`params` umstellen (Punkt 1), strikte
   Fehler-Schemata um die `translation_*`-Felder ergänzen (Punkt 2),
   Mess-Notiz-Entity bei Bedarf ins Dashboard aufnehmen (Punkt 3).
4. Es gibt nichts zu migrieren.

## Vollständiger Changelog

https://github.com/Popoboxxo/ha-health-o-mat/compare/v0.19.0...v0.21.0

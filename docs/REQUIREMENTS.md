# Requirements & Roadmap — ha-health-o-mat

**Stand:** 2026-09-06 · **Quelle:** Detailliertes System-Review v0.4.0 (+ Vorbefunde AUDIT-2026-09-04)
**Status:** Neue Reqs dokumentiert (Kapitel 1) · Funde & Risiken priorisiert (Kapitel 2/3) ·
Umsetzungsplan in **`plan-funde-risiken.md`** (eigenes Plan-Dokument, Per Planner-Konvention)

**Zwei getrennte Tracks:**

1. **Neue Anforderungen (Features)** — Kapitel 1, REQ-HOM-001…010: dokumentiert,
   Umsetzung in eigener Reihe (nicht Bestandteil des Fix-Plans).
2. **Funde & Risiken** — Kapitel 2, REQ-HOM-101…110: Bugfix-/Qualitätsanforderungen
   aus dem Review; deren priorisierter Umsetzungsplan liegt in
   **`plan-funde-risiken.md`** und ist das jetzt aktuelle Arbeitsprogramm.

**Legende:** Priorität P1 (muss bald) / P2 (soll) / P3 (nice-to-have) ·
Aufwand S (< ½ Tag) / M (1–2 Tage) / L (> 2 Tage)

---

## 1. Neue Anforderungen (Features) — dokumentiert

### REQ-HOM-001 — WHO-Blutdruck-Klassifikationssensor
- **Priorität:** P2 · **Aufwand:** S
- **Beschreibung:** Sensor ordnet die letzte Messung einer WHO-Kategorie zu:
  optimal / normal / hoch-normal / Grad-1 / Grad-2 / Grad-3 / hypertensive Krise.
- **Akzeptanzkriterien:**
  - [ ] Reine Klassifikationslogik in logic.py (testbar), Sensor `blood_pressure_category`
  - [ ] Zustands-Übersetzung de/en (state-Objekt-Form)
  - [ ] Keine Messung → `unknown`; Puls optional unabhängig
  - [ ] README-Disclaimer (keine medizinische Beratung) bleibt prominent

### REQ-HOM-002 — Trend-Sensoren (Trinken & Blutdruck)
- **Priorität:** P2 · **Aufwand:** M
- **Beschreibung:** `drinks_trend` (± % heute vs. Vorwoche-Ø) und `bp_trend`
  (steigend/fallend/stabil, Delta über 7-Tage-Mittelwerte).
- **Akzeptanzkriterien:**
  - [ ] Logik HA-frei; Mindestdatenschutz (≥ 3 Messungen sonst `unknown`)
  - [ ] Numerische Deltas als Attribute; Unit-Tests inkl. Grenzfälle

### REQ-HOM-003 — Streak-Sensor (Tagesziel)
- **Priorität:** P2 · **Aufwand:** S–M
- **Beschreibung:** `goal_streak` = Tage in Folge mit erreichtem Tagesziel, on-read.
- **Akzeptanzkriterien:**
  - [ ] On-read, kein Reset-Job; Attribut `best_streak`
  - [ ] Unit-Tests (Lücken, Randtage, Tagesgrenzen-Verschiebung)

### REQ-HOM-004 — Koffein-Tagessensor
- **Priorität:** P3 · **Aufwand:** S–M
- **Beschreibung:** Geschätzte Koffeinzufuhr heute in mg (mg-Tabelle je Getränketyp).
- **Akzeptanzkriterien:**
  - [ ] mg-Tabelle in const.py (als „Schätzwerte" kommentiert)
  - [ ] Sensor `caffeine_today` + Breakdown-Attribut; Unit-Tests

### REQ-HOM-005 — Tagesgrenze als Option
- **Priorität:** P1 · **Aufwand:** S
- **Status: Erledigt (v0.6.0)** — mit einer bewussten Design-Vereinfachung, siehe
  Akzeptanzkriterien.
- **Beschreibung:** Tagesgrenze (0:00 / 22:00 / 04:00 / benutzerdefiniert hh:mm) als
  Option; `logic.day_start(hour, minute)` ist bereits parametrisiert.
  **Behebt Fund F2 vollständig** (schränkt REQ-HOM-110 zur Übergangslösung ein).
- **Akzeptanzkriterien:**
  - [x] Options-Feld — **erledigt mit vereinfachtem Design:** ein einzelnes
    Ganzzahl-Feld `daily_reset_hour` (0–23, Options-Schritt „init", Default 0)
    statt 4 Voreinstellungen + benutzerdefiniertem hh:mm. Minuten-Granularität
    wurde als YAGNI bewertet (Aufwand/Nutzen) — `logic.day_start(hour, minute)`
    bleibt intern parametrisiert und könnte eine Minute-Option später ohne
    Breaking Change ergänzen.
  - [x] On-read-Fenster respektieren die Grenze — **„heute" und „gestern"**:
    ja, verdrahtet in `sensor.py` (`TodaySensor._today_sums`, `yesterday_ml`-
    Attribut) und `binary_sensor.py` (`GoalReachedEntity._today_ml`), beide lesen
    `entry.options["daily_reset_hour"]`. **`avg_7d`** (Blutdruck-Mittelwert,
    `logic.avg_over_window`) ist bewusst **nicht betroffen**: es ist ein
    rollierendes 7-Tage-Fenster (`now - 7 Tage` bis `now`), kein Tages-Bucket —
    die Tagesgrenze ist darauf konzeptionell nicht anwendbar.
  - [x] Unit-Tests — äquivalent abgedeckt (andere konkrete Uhrzeiten als im
    Kriterium genannt, gleiches Szenario „Buchung kurz vor der Grenze zählt zum
    Vortag"): `tests/test_logic.py::test_today_sums_with_custom_hour_shifts_window`
    (05:00-Buchung bei `hour=6`), `::test_yesterday_window_with_custom_hour_matches_today_sums_boundary`,
    plus Wiring-Regressionstests
    `tests/test_sensor.py::test_today_sensor_uses_daily_reset_hour_from_options`
    (+ `..._yesterday_ml_attribute_uses_same_daily_reset_hour`) und
    `tests/test_binary_sensor.py::test_goal_reached_uses_daily_reset_hour_from_options`.

### REQ-HOM-006 — Automation-Blueprints
- **Priorität:** P2 · **Aufwand:** S
- **Beschreibung:** Blueprints unter `blueprints/automation/health_o_mat/`:
  Abend-Erinnerung (Ziel < 100 %), Blutdruck-Warnung, optional Ziel-erreicht.
- **Akzeptanzkriterien:**
  - [ ] Validieren gegen HA-Schema (E2E: Import auf ha-test)
  - [ ] de/en Beschreibungstexte; Person frei wählbar

### REQ-HOM-007 — CSV-Import-Service
- **Priorität:** P3 · **Aufwand:** M
- **Beschreibung:** `health_o_mat.import_csv` — Übernahme Getränke-/Mess-Historie
  (Export-Format, tolerant).
- **Akzeptanzkriterien:**
  - [ ] Nur aus `/config/health_o_mat_import/` (Datenschutzregel, kein WWW)
  - [ ] Duplikat-Schutz (ts+ml); Ergebnis-Notification (übernommen/skipped/rejected)
  - [ ] Rundreise-Tests Export → Import

### REQ-HOM-008 — Wochenbericht-Service
- **Priorität:** P3 · **Aufwand:** M
- **Beschreibung:** `health_o_mat.weekly_report` → Markdown-Bericht (Ziel-Ø, Streak,
  BP-Ø/Trend, Wohlbefinden-Histogramm) als Notification.
- **Akzeptanzkriterien:**
  - [ ] Report-Logik HA-frei testbar; de/en Textbausteine

### REQ-HOM-009 — Pro-Person Feature-Toggles
- **Priorität:** P3 · **Aufwand:** L
- **Beschreibung:** Trinken/Blutdruck/Wohlbefinden pro Person an/aus → Entities nur
  für aktive Bereiche.
- **Akzeptanzkriterien:**
  - [ ] De-/Aktivieren ändert KEINE unique_ids (Entities laden/entladen nur)
  - [ ] Migrationspfad: Alt-Entries = alle aktiv

### REQ-HOM-010 — Mess-Notiz-Eingabe
- **Priorität:** P3 · **Aufwand:** S
- **Beschreibung:** Text-Entity `measurement_note`; Wert fließt beim
  `save_measurement` als `note` mit (Service-Parameter existiert schon).
- **Akzeptanzkriterien:**
  - [ ] Feld nach Speichern geleert; Note in history_json + CSV sichtbar

---

## 2. Funde & Risiken (priorisiert)

**Quelle:** System-Review 2026-09-06 · Sortierung nach Risiko, Fundorte im Code.

| # | Risiko | Schwere | REQ | Kurzfix-Ansatz |
|---|---|---|---|---|
| F1 | Quick-Drinks in `entry.data` → Ändern = Integration löschen = **Datenverlust** | 🔴 | 101 | Verlagerung nach Options + Migrator |
| F3 | Store ohne Migrationsroutine → Schema-Wachstum gefährdet Alt-Bestände | 🟡 | 102 | minor_version + Migratoren |
| F2 | README verspricht Tagesgrenze-Feature, das nicht existiert | 🔴 (Doku) | 110 + 005 | Sofort: README-Korrektur; vollständig: Feature 005 |
| F7 | BP-Eingaben nur im RAM → Neustart wirft halbfüllte Messung weg | 🟢 | 104 | Inputs in Store |
| F5 | Service-Übersetzungen fehlen in de/en.json | 🟡 | 107 | Sektionen + Paritätstest |
| F8 | Kein Linting in CI | 🟢 | 106 | ruff + CI-Job |
| F9 | Kein Diagnostics (Support-Pfad) | 🟢 | 105 | diagnostics.py (redacted) |
| F6 | Toter Code `csv_header_footer` | 🟢 | 108 | Entfernen |
| F4 | Store wächst unbegrenzt; linearer Scan je Refresh; Full-Dump je Klick | 🟡 (heute unkritisch) | 109 | Retention/Archiv als Option |

### Die zugehörigen Anforderungen

#### REQ-HOM-101 — Quick-Drinks & Anzeigename nach Options (Fix F1)
- **Priorität:** P1 · **Aufwand:** M
- **Anforderung:** Quick-Drink-Slots (Label/ml/Icon) und optionaler Anzeige-Name im
  Options-Flow editierbar; `entry.data` behält nur strukturelle Felder (person-Slug,
  lifetime_start_ml). ConfigFlow.VERSION 1→2 mit `async_migrate_entry` verlagert
  bestehende Werte bei Update (kein Datenverlust).
- **Akzeptanzkriterien:**
  - [ ] Quick-Drink ändern ohne Neu-Anlegen der Integration
  - [ ] Migration Unit-getestet (v0.4.0-Alt-Entry → Options gefüllt, data bereinigt)
  - [ ] `options.person` überschreibt Device-/Store-Anzeige ohne `entry.data`-Änderung
  - [ ] E2E: Update mit Alt-Bestand, Button-Änderung wirksam nach Reload

#### REQ-HOM-102 — Store-Migrationspfad (Fix F3)
- **Priorität:** P1 · **Aufwand:** S
- **Anforderung:** `minor_version` + Migrationsfunktionen je Stufe, idempotent.
- **Akzeptanzkriterien:**
  - [ ] Alt-JSON v1 lädt unverändert; Migrationstests für jede Stufe
  - [ ] Vorbereitung für kommende Schemafelder (siehe 104, 109)

#### REQ-HOM-103 — Store-Reparaturpfad (Risiko aus F3)
- **Priorität:** P1 · **Aufwand:** S
- **Befund Live-Test (2026-09-06):** Home Assistant sichert kaputtes JSON **selbst**
  (Backup `*.corrupt.<isotime>` + Repairs-Eintrag `storage_corruption_*` im UI) —
  `_store.async_load()` liefert dann einfach None. Eigene Backup-Schicht dafür wäre
  redundant und würde nie feuern.
- **Anforderung:** Nur der Fall „valides JSON, falsches Schema“ bekommt eigene
  Recovery: Datei sichern als `*.invalid-schema-<ts>`, Notification, definierter
  leerer Start.
- **Akzeptanzkriterien:**
  - [x] Schema-Invalid-Unit-Test (Backup-Pfad + Notification); Erstanlage (None) still
  - [x] E2E bewiesen: HA-Backup + Repairs-Issue bei kaputtem JSON, Restore funktioniert

#### REQ-HOM-104 — BP-Eingaben persistieren (Fix F7)
- **Priorität:** P2 · **Aufwand:** S
- **Anforderung:** `inputs`-Dict je Person im Store (Schema via 102), Laden beim Setup,
  Schreiben bei `InputNumber._apply`, Leeren beim Save.
- **Akzeptanzkriterien:**
  - [ ] Halbfüllte Eingabe überlebt Neustart (E2E); Save leert Store + Entities

#### REQ-HOM-105 — Diagnostics-Plattform (Fix F9)
- **Priorität:** P2 · **Aufwand:** S
- **Anforderung:** `async_get_config_entry_diagnostics`: Versionen, Entity-IDs, Options,
  Zähler — KEINE Gesundheitswerte, keine Personennamen (maskiert), keine Rohzeitstempel.
- **Akzeptanzkriterien:**
  - [ ] Redact-Unit-Test; E2E: Download liefert valides JSON

#### REQ-HOM-106 — ruff-Linting in CI (Fix F8)
- **Priorität:** P2 · **Aufwand:** S
- **Akzeptanzkriterien:**
  - [ ] `pyproject.toml` ruff-Konfig; CI-Job `lint`; Codebase ruff-clean (Aufräum-Commit)

#### REQ-HOM-107 — Service-Übersetzungen de/en (Fix F5)
- **Priorität:** P2 · **Aufwand:** S
- **Akzeptanzkriterien:**
  - [ ] `services`-Sektion in de.json (übersetzt) + en.json (= strings.json)
  - [ ] Paritätstest: Key-Bäume strings↔de↔en identisch

#### REQ-HOM-108 — Toter Code entfernen (Fix F6)
- **Priorität:** P3 · **Aufwand:** S
- **Akzeptanzkriterien:**
  - [ ] `logic.csv_header_footer` entfernt; Tests grün, grep-clean

#### REQ-HOM-109 — Daten-Retention/Archiv (Fix F4)
- **Priorität:** P3 · **Aufwand:** M
- **Anforderung:** Optionale Retention (Monate, Default „aus“): ältere Einträge beim
  Start ins Archiv (`health_o_mat_archive`-Store) verschieben; Export umfasst Archiv.
- **Akzeptanzkriterien:**
  - [ ] Default aus = exakt heutiges Verhalten; Summen unverändert; Archiv-Export

#### REQ-HOM-110 — README-Korrektur Tagesgrenze (Fix F2, Übergangslösung)
- **Priorität:** P1 · **Aufwand:** S
- **Status: Erledigt** — mit REQ-HOM-005 (v0.6.0) hinfällig geworden: die
  Übergangslösung (README als "geplant" korrigieren) wurde durch die
  README-Aktualisierung auf den tatsächlich fertigen Feature-Stand ersetzt.
- **Anforderung:** README:25–26 korrigieren (Feature existiert nicht; Verweis auf
  REQ-HOM-005 als geplant). Vollständige Behebung durch 005.
- **Akzeptanzkriterien:**
  - [x] README-Aussage stimmt wieder — README beschreibt jetzt die
    einstellbare Reset-Uhrzeit als fertiges Feature (kein REQ-Verweis mehr,
    analog zu den übrigen fertigen Features im selben Abschnitt).

---

## 3. Mapping Funde → Anforderungen

| Fund | Schwere | REQ (Fix) | Vollständige Lösung |
|---|---|---|---|
| F1 Quick-Drinks in entry.data | 🔴 | 101 | — |
| F2 README-Tagesgrenze | 🔴 (Doku) | 110 | 005 (Feature) |
| F3 Store-Migration fehlt | 🟡 | 102 + 103 | — |
| F4 Wachstum/Performance | 🟡 | 109 | — |
| F5 services-i18n | 🟡 | 107 | — |
| F6 Toter Code | 🟢 | 108 | — |
| F7 BP-Inputs nur RAM | 🟢 | 104 | — |
| F8 Kein Linting | 🟢 | 106 | — |
| F9 Kein Diagnostics | 🟢 | 105 | — |

---

## 4. Changelog der Anforderungen

| Datum | Änderung |
|---|---|
| 2026-09-06 | Initiale Anlage; nach Review-Feedback in zwei Tracks getrennt: Features (001–010) dokumentiert, Funde & Risiken (101–110) priorisiert; **Umsetzungsplan ausgelagert nach `plan-funde-risiken.md`** (Planner-Konvention: Pläne = eigene Dokumente) |

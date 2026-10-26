# Requirements & Roadmap — ha-health-o-mat

**Stand:** 2026-10-26 (UX-P1: **REQ-HOM-115…120 umgesetzt** — Branch `feat/ux-p1`, **Release 0.14.0 veröffentlicht (2026-10-26)** (Version-Bump/Tag/GitHub-Release), Plan `docs/PLAN-UX-P1.md`; zuvor 2026-10-24 Wohlbefinden-Bestätigung vor Übernahme, REQ-HOM-114, `feat/wellbeing-confirm`; 2026-10-21 Konfigurierbare Karte, REQ-HOM-113, `feat/configurable-card`; 2026-10-19 Wohlbefinden-Score & Score-Chart, REQ-HOM-112, `feat/wellbeing-score` + Recorder-Einheiten-Fix `fix/recorder-unit-migration`; 2026-10-18 UI-Ausbau, `feat/ui-pro`) · **Quelle:** Detailliertes System-Review v0.4.0 (+ Vorbefunde AUDIT-2026-09-04), UI-Ausbau `docs/IDEATION-UI-PRO.md`, UX-P1 `docs/PLAN-UX-P1.md`
**Status:** Neue Reqs dokumentiert (Kapitel 1) · Funde & Risiken priorisiert (Kapitel 2/3) ·
**REQ-HOM-111** erledigt (Fix F10, Recorder-Statistik-Einheit „ml" → „mL") ·
**REQ-HOM-112** erledigt (Feature, Wohlbefinden-Score & Score-Chart) ·
**REQ-HOM-113** erledigt (Feature, Konfigurierbare Health-O-Mat-Karte) ·
**REQ-HOM-114** erledigt (Wohlbefinden-Bestätigung vor Übernahme) ·
**REQ-HOM-115…120 umgesetzt** (UX-P1, P1, Branch `feat/ux-p1`, 2026-10-26;
**Release 0.14.0 veröffentlicht (2026-10-26)** — Version-Bump/Tag/GitHub-Release):
Korrigierbarkeit/Verlauf/Void-Restore/Audit-Log (115), Backup-Restore inkl. Teil-Restore
und Dry-Run (116), UI-Internationalisierung de/en (117), Erinnerungen/Wochenbericht/
Blueprints (118), Onboarding-/Options-Wizard (119), unbegrenztes Rückdatieren (120) ·
**REQ-HOM-121** erledigt und mit **Release 0.15.0 veröffentlicht (2026-10-26)** (Wohlbefinden-Zahleneingabe als Number-Entity, Branch `feat/wellbeing-number-entity`) ·
Belege: **1159 Unit-Tests**, **18 E2E-Tests** (realer HA-Docker-Stack),
`ruff check .` + `ruff format --check .` clean ·
Umsetzungsplan Funde/Risiken in **`plan-funde-risiken.md`**, UX-P1 in
**`docs/PLAN-UX-P1.md`** (eigene Plan-Dokumente, Per Planner-Konvention)

**Zwei getrennte Tracks:**

1. **Neue Anforderungen (Features)** — Kapitel 1, REQ-HOM-001…014: dokumentiert,
   Umsetzung in eigener Reihe (nicht Bestandteil des Fix-Plans).
2. **Funde & Risiken** — Kapitel 2, REQ-HOM-101…120: Bugfix-/Qualitätsanforderungen
   aus dem Review; deren priorisierter Umsetzungsplan liegt in
   **`plan-funde-risiken.md`** und ist das jetzt aktuelle Arbeitsprogramm.
   Ergänzt: **REQ-HOM-112** (Wohlbefinden-Score & Score-Chart) — ein Feature-
   Requirement; am Ende von Kapitel 2 (nach REQ-HOM-111) abgelegt
   (Branch `feat/wellbeing-score`) — sowie **REQ-HOM-113** (Konfigurierbare
   Karte, Branch `feat/configurable-card`) nach REQ-HOM-112 und
   **REQ-HOM-114** (Wohlbefinden-Bestätigung vor Übernahme, Branch
   `feat/wellbeing-confirm`) nach REQ-HOM-113. Nach REQ-HOM-114 folgen
   **REQ-HOM-115…120** (UX-P1, Branch `feat/ux-p1`) — der Arbeitsplan dazu liegt
   in **`docs/PLAN-UX-P1.md`** und ist der Release-Schnitt **0.14.0**.

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
- **Status: Erledigt (Branch `feat/import-backup`)** — alle Akzeptanzkriterien
  umgesetzt; siehe zusätzlich die Notiz zu Backup/Restore am Ende dieses Eintrags.
- **Beschreibung:** `health_o_mat.import_csv` — Übernahme Getränke-/Mess-Historie
  (Export-Format, tolerant).
- **Akzeptanzkriterien:**
  - [x] Nur aus `/config/health_o_mat_import/` (Datenschutzregel, kein WWW) —
    Pfad-Whitelist in `importer.safe_import_path`: nur relative Namen unterhalb
    `<config_dir>/health_o_mat_import/`; absolute Pfade, `..`-Traversal,
    Symlink-Escapes und leere Namen werden abgewiesen. Gelesen wird ausschließlich
    aus dem privaten Import-Verzeichnis, **nie** aus `/config/www`
    (`importer.py`, `tests/test_import_backup.py`).
  - [x] Duplikat-Schutz (ts+ml); Ergebnis-Notification (übernommen/skipped/rejected) —
    Getränke werden über `(ts, ml)`, Blutdruck über `(ts, sys, dia)` dedupliziert
    (`plan_import`); der Service gibt `imported/skipped/rejected` (+ `errors`)
    zurück und erzeugt eine `persistent_notification` mit der Zusammenfassung.
    Toleranz: Semikolon-getrennt, UTF-8 mit/ohne BOM, `#`-Kommentare, fehlender/
    abweichender Header (`importer.parse_csv_text`).
  - [x] Rundreise-Tests Export → Import — `tests/test_import_backup.py`
    (`test_plan_import_roundtrip_drinks` sowie Toleranz-, Duplikat- und
    Pfad-Whitelist-Tests).
- **Notiz (über REQ-HOM-007 hinaus):** Zusätzlich existiert ein
  **`health_o_mat.backup`-Service** (JSON-Voll-Export aller Personen/Datensätze/
  Zeiträume, versioniertes Dokument `format`/`version`) nach
  `/config/health_o_mat_export/` (`backup.py`). **Restore ist weiterhin offen** —
  das Backup-Dokument ist auf einen späteren Restore vorbereitet, kann aber noch
  nicht automatisch zurückgespielt werden.

### REQ-HOM-008 — Wochenbericht-Service
- **Priorität:** P3 · **Aufwand:** M
- **Beschreibung:** `health_o_mat.weekly_report` → Markdown-Bericht (Ziel-Ø, Streak,
  BP-Ø/Trend, Wohlbefinden-Histogramm) als Notification.
- **Akzeptanzkriterien:**
  - [ ] Report-Logik HA-frei testbar; de/en Textbausteine

### REQ-HOM-009 — Pro-Person Feature-Toggles
- **Priorität:** P3 · **Aufwand:** L
- **Status: Erledigt (Branch `feat/ui-pro`)** — alle Akzeptanzkriterien mit Beleg;
  auf `ha-test` E2E-verifiziert (Reload **und** Neustart).
- **Beschreibung:** Trinken/Blutdruck/Wohlbefinden pro Person an/aus → Entities nur
  für aktive Bereiche.
- **Design:** Toggles in `entry.options["areas"] = {drink, bp, wellbeing}`
  (HA-freie Logik in `areas.py`); fehlender Schlüssel — `areas` selbst oder ein
  einzelner Unter-Schlüssel — bedeutet **aktiv** (Alt-Entry-Migrationspfad).
  Die Plattformen (`sensor.py`, `button.py`, `number.py`, `select.py`, `text.py`,
  `binary_sensor.py`) erzeugen Entities nur für aktive Bereiche; eine
  Options-Änderung löst `async_reload(entry)` aus (`__init__.py::_options_updated`).
  Zusätzlich in der Options-Maske (Schritt „init", Felder `area_drink`/`area_bp`/
  `area_wellbeing`) und in der Admin-Settings-Ansicht des Panels.
- **Akzeptanzkriterien:**
  - [x] De-/Aktivieren ändert KEINE unique_ids (Entities laden/entladen nur) —
    E2E belegt: Registry-Einträge byte-identisch, Reaktivierung = identische
    `entity_id`, Store unverändert (`tests/test_areas.py`,
    `tests/test_areas_wiring.py`).
  - [x] Migrationspfad: Alt-Entries = alle aktiv — `areas.active_areas` behandelt
    fehlende/ungültige Angaben als „alle aktiv" (`tests/test_areas.py`); E2E mit
    frischem Entry ohne `areas`-Schlüssel bestätigt.
  - [x] Regression-Schutz: Ein Bereichs-Toggle (Reload) setzt den Lebenszähler
    **nicht** zurück (`tests/test_areas_wiring.py::test_apply_options_does_not_touch_lifetime`).

### REQ-HOM-011 — Card-Ausbau (kompakt, L1)
- **Priorität:** P3 · **Aufwand:** S–M
- **Status: Erledigt (Branch `feat/ui-pro`)** — kompakte Lese-Zusätze + Editor-Komfort
  (D9).
- **Beschreibung:** Die mitgelieferte Lovelace-Karte (`health-o-mat-card`) um
  kompakte Lese-Mehrwerte ergänzen, ohne sie zum Panel-Ersatz zu machen; **kein**
  Admin/Settings in der Karte.
- **Akzeptanzkriterien:**
  - [x] Hydration-Pace-Badge, Serie (`goal_streak`), Koffein (`caffeine_today`)
    und freundliches WHO-Kategorie-Label (`logic.bp_category`-Schlüssel) angezeigt
  - [x] Editor-Komfort: Personenauswahl via `list_persons` (statt manueller
    `entry_id`-Eingabe), weiterhin Abwärtskompatibilität
  - [x] Bereiche mit Toggle aus werden in der Karte ausgeblendet (REQ-HOM-009)

### REQ-HOM-012 — Person-Ansicht + Deep-Link
- **Priorität:** P3 · **Aufwand:** M
- **Status: Erledigt** — Deep-Link-Mechanik E2E auf
  Registrierungs-/Auslieferungsebene geprüft (Branch `feat/ui-pro`); echte
  Browser-Verifikation (`tests_e2e/`, Playwright) ergänzt und grün
  (Branch `feat/e2e-playwright`, 2026-10-18).
- **Beschreibung:** Adressierbare, vollwertige Person-Seite im Panel mit stabilem
  Deep-Link.
- **Akzeptanzkriterien:**
  - [x] URL-Query `?person=<kennung>` adressiert die Person-Seite
    (`history.pushState` + `popstate`); Tabs (Trinken/BD/Wohlbefinden) bleiben,
    Bereiche mit Toggle aus werden ausgeblendet
  - [x] Kennung = **stabiler Slug** `entry.data["person"]` (nie Anzeigename);
    `list_persons`/`panel_data` liefern `person_slug` + `areas` additiv
  - [x] Browser-Smoke (Playwright) — `tests_e2e/` (6 Tests, realer Browser gegen
    echte HA-Instanz): Panel-Mount, Deep-Link öffnet direkt die Detailansicht,
    Kachel-Klick = `pushState`, Browser-Zurück = `popstate` → Übersicht,
    unbekannter Parameter → sichere Übersicht, abgeschalteter Bereich blendet
    seinen Tab aus. **Beleg (reproduzierbar):** gegen den Docker-HA-Stack aus
    `docker-compose.e2e.yml`
    (`docker compose -f docker-compose.e2e.yml up -d homeassistant`)
    `HASS_BASE_URL=http://localhost:8124 python3 -m pytest tests_e2e/ -v`
    → 6 passed; alternativ gegen die geteilte Instanz `ha-test`
    (`HASS_BASE_URL=http://localhost:8123`). Die Roh-Logs liegen nur flüchtig
    unter `test-results/` (gitignored, wird von Playwright zu Beginn jedes Laufs
    geleert) und taugen daher nicht als Beleg; dauerhafter Beleg ist das
    CI-Artefakt `e2e-test-results` aus `.github/workflows/e2e.yaml`

### REQ-HOM-013 — Admin-/Instanzverwaltung (L3)
- **Priorität:** P3 · **Aufwand:** M–L
- **Status: Erledigt (Branch `feat/ui-pro`)** — E2E: gated Löschen entfernt die
  freischaltende Person und meldet das Panel ohne Neustart ab.
- **Beschreibung:** Verwaltung an einem Ort (admin-gated): Rename/Anzeigename,
  bestehende Per-Person-Settings, Backup-Trigger, Person anlegen, Person löschen.
- **Akzeptanzkriterien:**
  - [x] Rename/Anzeigename + alle bestehenden Settings im Admin-Formular (bereits)
  - [x] **Backup-Trigger** aus dem Panel (`health_o_mat/backup` → ruft genau den
    `health_o_mat.backup`-Service auf, kein Zweitweg)
  - [x] **Person anlegen** via Flow-Verweis/-Start
    (`health_o_mat/start_person_flow` → `config_entries.async_init`), kein
    eigenes WS-CRUD
  - [x] **Person löschen** nur admin-gated + **Doppelbestätigung** (Bestätigung
    muss exakt dem Personen-Slug entsprechen) + Hinweis auf offenen Restore
    (`health_o_mat/delete_person`)
  - [x] Domain-weite Richtigstellung: das Panel wird abgemeldet, wenn die letzte
    freischaltende Person entfernt wurde (vorher erst nach HA-Neustart)

### REQ-HOM-014 — Frontend-Struktur (NFA)
- **Priorität:** P3 · **Aufwand:** S
- **Status: Erledigt (Branch `feat/ui-pro`)**
- **Beschreibung:** Wartbare Frontend-Struktur ohne Bundler-Pflicht.
- **Akzeptanzkriterien:**
  - [x] Panel in native ES-Module gegliedert (Entry + `-base`/`-views`/`-admin`),
    kein npm/esbuild
  - [x] Cache-Busting `?v=<manifest.version>` für Card und Panel-Module;
    JS-Analyse-Test (`tests/test_panel_js.py`) erzwingt die Kopplung an
    `manifest.version`; Bestands-Card-Ressource wird beim Setup auf die
    versionierte URL nachgezogen

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
| F10 | Recorder-Metadaten der Volumen-Sensoren mit Legacy-Einheit „ml" → HA unterdrückt die **Langzeitstatistik** | 🔴 | 111 | Metadaten-Migration beim Setup (ml → mL) |
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

#### REQ-HOM-111 — Recorder-Statistik-Einheit „ml" → „mL" (Fix F10)
- **Priorität:** P1 · **Aufwand:** S
- **Status: Erledigt (Branch `fix/recorder-unit-migration`)** — E2E auf `ha-test`
  (HA 2026.9.1) verifiziert; kein Versions-Bump in `manifest.json` (Release
  folgt separat).
- **Befund (Live-Test auf `ha-test`, 2026-10-17 → 2026-10-19):** Ältere
  Installationen haben Recorder-Statistik-Metadaten mit der Legacy-Einheit „ml"
  (`unit_class` = NULL). Die Volumen-Sensoren melden die HA-kanonische Einheit
  „mL" (`SensorDeviceClass.VOLUME`) — Home Assistant verweigert deshalb die
  Fortsetzung der Langzeitstatistik:
  `The unit of ... (mL) cannot be converted to the unit of previously compiled
  statistics (ml). Generation of long term statistics will be suppressed`.
  Der HA-Kern heilt das nicht (er migriert nur bei `entity_id`-Änderungen).
  Betroffen sind je Person ausschließlich die beiden Volumen-Sensoren mit
  `state_class` (`sensor_drinks_today` = TOTAL, `sensor_lifetime_total` =
  TOTAL_INCREASING); alle übrigen Sensoren (%, mmHg, mg, d, BPM) haben ihre
  Einheit nie geändert, und number/text/button/select/binary_sensor erzeugen
  per HA-Regel KEINE Recorder-Statistik.
- **Anforderung:** Beim Setup des Config-Entries migriert die Integration die
  Recorder-Metadaten der beiden Volumen-Sensoren je Person von „ml" auf „mL"
  (`async_update_statistics_metadata(..., new_unit_of_measurement="mL",
  new_unit_class="volume")`). Die Migration ist idempotent und verlustfrei
  („ml" ≡ „mL") und **nie setup-kritisch** — Fehler werden geloggt, nicht
  geworfen. Ergänzend melden die beiden Number-Entities
  (`number.…_daily_goal`, `number.…_custom_drink_amount`) ebenfalls „mL"
  (Konsistenz zu den Volumen-Sensoren); die Datenfelder (`daily_goal_ml`,
  `ml` in JSON/CSV) bleiben unverändert. Kein Eingriff in die Health-Daten im
  Store, keine Änderung an `unique_id`/`entity_id`.
- **Akzeptanzkriterien:**
  - [x] Nur die eigenen Volumen-Sensoren werden angefasst — Zuordnung über die
    stabile `unique_id` (`{entry_id}_{key}`) aus der Entity-Registry, KEINE
    `entity_id`-Konstruktion aus dem Person-Slug; Fremd-Domains und
    Nicht-Volume-Einheiten (%, mmHg, mg, d, BPM) bleiben unangetastet
    (`tests/test_statistics.py::test_migration_updates_only_own_legacy_statistics`,
    `::test_fallback_ignores_foreign_units_even_with_legacy_suffix`).
  - [x] Idempotent und verlustfrei — ein zweiter Lauf migriert nichts mehr
    (`::test_migration_is_idempotent`,
    `::test_migration_leaves_canonical_units_untouched`); historische Werte
    bleiben gültig, es wird nichts gelöscht oder umgerechnet.
  - [x] Recorder nicht eingerichtet → Migration wird übersprungen und beim
    nächsten Setup (HA-Neustart/Entry-Reload) nachgeholt; bewusst KEIN
    Start-Event-Retry (der Recorder ist Bootstrap-STAGE_0 und steht damit immer
    bereit, bevor ein Config-Entry-Setup läuft)
    (`::test_migration_is_noop_when_recorder_not_configured`,
    `::test_migration_creates_no_pending_container`).
  - [x] Nie setup-kritisch — Fehler werden geloggt, das Setup läuft weiter
    (`::test_migration_swallows_recorder_errors`,
    `::test_setup_entry_survives_failing_statistics_migration`).
  - [x] Einheiten-Konsistenz: die Volumen-Sensoren melden bereits die
    kanonische Einheit „mL" (`::test_legacy_volume_sensor_keys_match_sensor_unique_ids`),
    die beiden Number-Entities melden jetzt ebenfalls „mL".
  - [x] E2E-Beleg (`ha-test`, HA 2026.9.1): **vorher** 4 `statistic_id`s
    (`sensor.health_o_mat_{max,e2e}_{drinks_today,lifetime_total}`) mit
    Metadaten `ml` (`unit_class` NULL), 24 Recorder-Warnungen über 6 Starts und
    seit 2026-10-17 eingefrorene Kurzzeit-/Langzeitstatistik; **nachher**
    Metadaten `mL` + `unit_class` `volume`, 0 Warnungen nach dem Fix-Restart,
    Kurzzeitstatistik ab 22:05 und Langzeitstatistik ab 2026-10-19 22:00 wieder
    laufend, Kontroll-IDs unverändert, Store-Daten unverändert.
  - [x] Unit-Test-Beleg: `pytest -q` → **580 passed**; `ruff` clean.
  - [x] README dokumentiert die Einheit „mL" (Volumen-Sensoren + Number-Entities)
    sowie den Migrations-Hinweis für Alt-Installationen: Ursache der Legacy-
    Metadaten, automatische Migration beim Setup, Gültigkeit der historischen
    Werte, Verhalten bei deaktiviertem Recorder, Sichtbarkeit der
    Migrationszeile (Log-Level **INFO** für `custom_components.health_o_mat`) und
    die bewusste Entscheidung, **keinen** Lösch-Service für Statistiken
    anzubieten (HA bietet „Statistiken löschen" bereits in der UI).

#### REQ-HOM-112 — Wohlbefinden-Score & Verlaufs-Chart
- **Priorität:** P2 · **Aufwand:** M
- **Status: Implementiert und verifiziert (Branch `feat/wellbeing-score`)** —
  Backend (Logik, Sensor, WebSocket-Payload) und Frontend (Card, Panel) sind
  umgesetzt; die **dedizierte Testabdeckung ist fertig** (Logik, Sensor,
  WS-Payload, Card, Panel — siehe Akzeptanzkriterien) und die Verifikation auf
  `ha-test` ist erfolgt (E2E-Beleg: `docs/e2e-2026-10-19-wellbeing-score/`).
  **Offen:** allein der **Release** (Versions-Bump `manifest.version` + `?v=`-
  Cache-Buster zusammen, Tag, GitHub-Release).
- **Anforderung:** Das Wohlbefinden bekommt eine **korrespondierende numerische
  Darstellung 1 … 10** (1 = „Sehr schlecht" = schlechtester Wert … 10 =
  „Ausgezeichnet" = bester Wert). Die Skala ist **reihenfolgetreu aus den zehn
  Wohlbefinden-Zuständen abgeleitet** (Index + 1) und **wächst automatisch mit**,
  wenn ein neuer Zustand hinzukommt. Die bestehenden Keys bleiben auf den
  ungeraden Stufen 1/3/5/7/9 erhalten. Zusätzlich kann je Key ein eigenes
  PNG/JPG/WebP-Bild in den Options hinterlegt werden (Karte + Panel zeigen es
  statt des Emojis). Der Score ist **rein abgeleitet und on-read**: keine
  eigene Persistenz, kein eigener Store, keine Migration des Datenbestands —
  100 % an die Rohdaten gekoppelt. Sensor `wellbeing_score` (`state_class:
  measurement`, **ohne** Einheit, **ohne** `device_class`; ohne Meldung `unknown`,
  nie 0). Der WebSocket-Payload `health_o_mat/panel_data` wird **additiv** um
  `score` erweitert (aktueller Score im `wellbeing`-Block, Score je Eintrag in
  `wellbeing.history`; bestehende Schlüssel unverändert). Score-Chart in der
  **Card** (kompakt: Badge + Sparkline der letzten 14 Meldungen) und im
  **Panel** (vollständiger SVG-Chart des Verlaufs) — beide **ohne externe
  Bibliothek**, Farben ausschließlich über HA-CSS-Variablen.
- **Akzeptanzkriterien:**
  - [x] Score-Ableitung **reihenfolgetreu** und HA-frei — `logic.wellbeing_score`
    (Index + 1 über `const.WELLBEING_STATES`, zur Aufrufzeit gelesen, damit die
    Liste wachsen kann); unbekannter/fehlender Key → `None` (Sensor: `unknown`),
    **nie 0**. **Beleg:** `tests/test_logic.py::test_req_hom_112_wellbeing_score_maps_every_state_to_index_plus_one`
    (jeder Zustand ⇒ Index + 1) und
    `::test_req_hom_112_wellbeing_score_scale_follows_wellbeing_states`
    (Skala wächst automatisch mit der Zustandsliste); die Randfälle
    (unbekannter Key, fehlender Wert, leerer String, Nicht-String) und die
    Zusage „nie 0" sind ebenfalls in `tests/test_logic.py` abgedeckt
    (`::test_req_hom_112_wellbeing_score_never_returns_zero`).
  - [x] Sensor `wellbeing_score` gehört zum Bereich **Wohlbefinden** — er wird
    nur erzeugt, wenn der Wohlbefinden-Toggle aktiv ist (analog
    `wellbeing_last_reported`); `state_class: measurement`, keine Einheit, kein
    `device_class`; ohne Meldung `unknown`; Attribute `reported_at` (Zeitpunkt
    der Meldung) und `scale_max` (5) — `sensor.py` (`WellbeingScoreSensor`).
    **Beleg:** `tests/test_sensor.py::test_req_hom_112_wellbeing_score_sensor_registered_with_stable_unique_id`
    (stabile `unique_id` `{entry_id}_sensor_wellbeing_score`),
    `::test_req_hom_112_wellbeing_score_sensor_native_value_matches_status`
    (Wert = Score des aktuellen Status) und
    `::test_req_hom_112_wellbeing_score_sensor_follows_area_toggle`
    (Wohlbefinden aus → keine Score-Entity, `unique_id` bleibt unverändert);
    `state_class`, fehlende Einheit/`device_class`, `translation_key`/`icon`,
    `reported_at` und `scale_max` sind ebendort abgedeckt.
  - [x] **Rein abgeleitet:** keine eigene Datenhaltung, keine Store-Erweiterung,
    keine Migration des Datenbestands — der Wert wird on-read aus der letzten
    Rohmeldung berechnet; Ändern/Löschen der Rohmeldung ändert den Score
    automatisch.
  - [x] WS-Payload **additiv** — `score` im `wellbeing`-Block und je Eintrag in
    `wellbeing.history`; bestehende Schlüssel unverändert (rückwärtskompatibel).
    **Beleg:** `tests/test_ws_api.py::test_req_hom_112_wellbeing_block_contains_current_score`
    (aktueller Score im `wellbeing`-Block),
    `::test_req_hom_112_wellbeing_history_entries_contain_score` (Score je
    Verlaufseintrag) und
    `::test_req_hom_112_entity_suffixes_extension_is_additive` (Alt-Schlüssel
    unverändert); Leerfall `tests/test_ws_api.py::test_panel_data_without_store_or_readings`.
  - [x] **Card:** Score-Badge (z. B. „4 / 5") + **kleine Sparkline** der letzten
    14 Meldungen; die Card bleibt einbettbare Kompaktanzeige (kein
    Panel-Ersatz). **Beleg:** `tests/test_card_js.py::test_card_wellbeing_score_and_sparkline_helpers_exist`
    (Score-/Sparkline-Helfer vorhanden) und
    `::test_card_wellbeing_trend_uses_last_14_reports` (Trend = letzte 14
    Meldungen); Badge/Skalenmaximum, Zugänglichkeit und Leerfall sind in
    `tests/test_card_js.py` abgedeckt.
  - [x] **Panel:** vollständiger SVG-Score-Chart (Zeit auf X, Score 1…5 auf Y,
    Y-Achse mit den Extremwerten 1 und 5, Zeitachse, hervorgehobener Marker für
    den aktuellen Wert, Tooltip je Punkt mit Zeitpunkt + Label + Score,
    `aria-label`); **Leerfall** = verständlicher Hinweis statt leerem Chart.
    **Beleg:** `tests/test_panel_js.py::test_panel_base_exposes_wellbeing_chart_helpers`
    (geteilte Chart-Logik im Basis-Modul) und
    `::test_panel_base_wellbeing_chart_marks_current_value_and_axis_extremes`
    (aktueller Wert und Achsen-Extremwerte hervorgehoben); Zeitachse,
    Skalenkonstanten, Leerfall, Theme-Variablen und die Einbindung in den
    Wohlbefinden-Tab sind ebendort abgedeckt.
  - [x] Beide Charts **ohne externe Bibliothek** (Vanilla-SVG), Farben
    ausschließlich über HA-CSS-Variablen (`--primary-color`,
    `--card-background-color`, `--divider-color`, `--secondary-text-color`) →
    light/dark-fähig und mobiltauglich (SVG skaliert, keine feste Pixelbreite).
    **Beleg:** `tests/test_card_js.py::test_card_wellbeing_chart_needs_no_external_library`
    und `tests/test_panel_js.py::test_panel_base_wellbeing_chart_uses_ha_theme_variables`.
  - [x] **Score-Auflösung: der Server ist die Wahrheit** — ist das Feld `score`
    im Objekt vorhanden (auch bei `null`), gilt der **Serverwert** (`null` ⇒
    **kein** Score, keine clientseitige Ersatzableitung); nur bei einem
    **älteren** Server, der das Feld noch nicht kennt, wird der Score
    clientseitig aus dem **kanonischen** Key abgeleitet — exakter Match,
    **case-sensitiv**, wie `logic.wellbeing_score` (Index + 1). Card und Panel
    lösen **identisch** auf (keine zweite Wahrheit, keine Alias-/Case-Divergenz
    zwischen Client und Server). **Beleg:**
    `tests/test_panel_js.py::test_req_hom_112_panel_base_wellbeing_score_follows_server_truth_rule`,
    `::test_req_hom_112_card_wellbeing_score_follows_server_truth_rule`,
    `::test_req_hom_112_card_and_panel_resolve_the_same_wellbeing_score` und
    `::test_req_hom_112_panel_chart_derives_score_from_key_for_legacy_payloads`.
  - [x] **Panel-Kopfzeile und Chart nutzen denselben aufgelösten Score**
    (live-first: Live-Entity, sonst Server-Feld, sonst kanonischer Key) — sie
    können sich deshalb **nicht widersprechen**. **Beleg:**
    `tests/test_panel_js.py::test_req_hom_112_panel_wellbeing_tab_shows_live_score_in_header_and_chart`
    und `::test_req_hom_112_panel_views_passes_current_wellbeing_block_to_chart`.
  - [x] **Der „aktuell"-Marker hängt am aktuellen Wert** — hervorgehoben wird
    ausschließlich der Punkt mit dem **aktuellen** Score (`point-current`); ein
    abgelooster letzter Historienpunkt wird **nicht** markiert. Gibt es keinen
    aktuellen Wert (keine Meldung), wird **kein** Punkt hervorgehoben und die
    Zusammenfassung nennt „letzter Wert" statt „aktuell" — Kopfzeile und Chart
    können sich nicht widersprechen. **Beleg:**
    `tests/test_panel_js.py::test_req_hom_112_panel_chart_marks_exactly_one_current_point`
    (genau ein Marker auf dem aktuellen Wert, der abgeloeste Punkt bleibt
    unmarkiert),
    `::test_req_hom_112_panel_chart_without_current_score_marks_nothing`,
    `::test_req_hom_112_card_without_current_score_has_no_badge_and_no_current_point`
    und
    `::test_req_hom_112_card_with_current_score_shows_badge_and_one_current_point`.
  - [x] **Historie-Semantik (Store), korrigiert in v0.10.1** — ein
    Historieneintrag `{ts, status}` bedeutet „dieser Status wurde zu `ts`
    gemeldet"; der **abgelöste** Status trägt seinen **eigenen Meldezeitpunkt**
    (nicht den Zeitpunkt des Wechsels). Der **aktuelle** Wert steht
    ausschließlich in `wellbeing`. Das Frontend hängt den aktuellen Wert deshalb
    selbst als **letzten** Serienpunkt an (Marker = aktueller Wert); kein
    Schema-Umbau, keine Migration. **Beleg:**
    `tests/test_store.py::test_req_hom_112_wellbeing_history_records_replaced_status_with_report_timestamp`,
    `tests/test_card_js.py::test_req_hom_112_card_wellbeing_series_appends_current_value`
    und `tests/test_panel_js.py::test_req_hom_112_panel_base_exports_wellbeing_series_with_current_point`.
  - [x] **Frontend-Spiegel der Zustandsliste an `const.WELLBEING_STATES`
    gepinnt** — Keys, **Reihenfolge** und **Länge** der JS-Spiegel (Panel:
    `WELLBEING_STATES`, Karte: `WELLBEING_SCALE`) müssen der Server-Skala
    entsprechen; eine neue serverseitige Stufe schlägt damit automatisch
    durch und der Frontend-Spiegel kann nicht still veralten. **Beleg:**
    `tests/test_logic.py::test_req_hom_112_frontend_wellbeing_mirrors_match_server_scale`
    und `::test_req_hom_112_frontend_wellbeing_mirror_check_detects_deviation`.
  - [x] **E2E-Verifikation auf `ha-test` (HA 2026.9.1)** — Kriterium erfüllt:
    Entity `wellbeing_score` existiert und liefert die Werte **1–10**; ohne
    Meldung `unknown` (kein Meldungs-/Fehlertext); `state_class: measurement`
    **ohne** Einheit und **ohne** `device_class`; die Recorder-Statistik läuft
    **ohne** Einheiten-Warnung; der WS-Payload `panel_data` enthält den
    **additiven** `score`-Key (aktueller Wert + je Verlaufseintrag); der
    Score-Chart rendert im **Panel** **und** in der **Card**. **Beleg:** Report
    + Screenshots unter `docs/e2e-2026-10-19-wellbeing-score/`.
  - [x] Unit-Test-Beleg: `pytest -q` → **666 passed**; `ruff` clean.

#### REQ-HOM-113 — Konfigurierbare Health-O-Mat-Karte
- **Priorität:** P2 · **Aufwand:** M
- **Status: Erledigt (Branch `feat/configurable-card`, 2026-10-21)** — umgesetzt
  und getestet. **Kein Versions-Bump:** `manifest.json` und die
  `?v=`-Cache-Buster bleiben unverändert; der Release (v0.10.0) folgt separat.
- **Anforderung:** Die mitgelieferte Lovelace-Karte (`custom:health-o-mat-card`)
  wird über den **Karten-Editor** bzw. YAML konfigurierbar — flaches Schema,
  **alle Schlüssel optional**. Die Defaults sind bewusst **nicht** durchgehend
  „Verhalten unverändert": die **Anzeige-Blöcke bleiben unverändert**, die **neuen
  Eingabe-Blöcke** (manuelle Mengen, Blutdruck-Eingabe, Wohlbefinden-Eingabe)
  sind **per Default aktiv** — bestehende Karten erhalten sie beim Update. Das
  ist eine bewusste neue Funktion (im Release v0.10.0 unter „✨ New features"
  gelistet; der Release-Eintrag folgt separat, die Funktion ist in diesem
  Branch implementiert). Fünf Ziele:
  (1) Auswahl der Quick-Drinks aus den in der Integration konfigurierten
  Getränken (Referenz per Key, keine kartenlokale Zweitliste), (2) konfigurierbare
  manuelle ml-Presets plus optionales freies Zahlenfeld, (3) Blutdruck-Eingabe
  (Systolisch/Diastolisch/Puls + optionale Notiz) ein-/ausschaltbar,
  (4) Wohlbefinden-Eingabe (zehn Zustände + Zahleneingabe) ein-/ausschaltbar, (5) alle
  Anzeige-Blöcke (Personenwahl, Hydration, letzter Blutdruck, letztes
  Wohlbefinden, Undo) einzeln ein-/ausschaltbar. Das Wohlbefinden schreibt über
  den neuen öffentlichen Service `health_o_mat.set_wellbeing` (`person`
  optional, `status` Pflicht); die bestehenden `button.*_report_*`-Entities
  bleiben unverändert. Im Panel erscheint unter dem unveränderten Score-Chart
  zusätzlich die Verlaufsliste (Zeitpunkt + Emoji + Label + Score).
  **Nicht-Ziel:** Panel-Konfiguration, Dashboard-Builder, neue Persistenz von
  Gesundheitsdaten, Änderung von `unique_id`s.
- **Akzeptanzkriterien:**
  - [x] Schema vollständig und flach: `entry_id`, `person`, neun `show_*`-Schalter,
    `drinks`, `manual_amounts`, `allow_custom_amount` sowie der Legacy-Override
    `quick_drinks`; alle optional, unbekannte Werte fallen auf den Default
    zurück (kein Render-Crash). **Default-Semantik:** Anzeige-Blöcke unverändert,
    die drei neuen Eingabe-Blöcke (manuelle Mengen, BD-Eingabe,
    Wohlbefinden-Eingabe) **an** — für Bestandskarten eine bewusste
    Verhaltensänderung (neue Funktion, v0.10.0). **Beleg (Default-Mechanik):**
    `tests/test_card_js.py::test_card_show_flag_list_covers_exactly_the_nine_schema_keys`,
    `::test_card_config_defaults_and_backward_compatibility`.
  - [x] `show_*=false` blendet den Block aus; jeder Block ist ein AND aus
    Integrations-Bereich (`areas`) und Karten-Flag. **Beleg:**
    `::test_card_body_gates_every_block_with_its_flag_and_the_area`.
  - [x] `show_blood_pressure_input: true` **explizit** gewinnt gegen
    `show_blood_pressure: false`; ohne expliziten Wert folgt die Eingabe der
    Anzeige. **Beleg:**
    `::test_card_explicit_bp_input_flag_overrides_display_flag`; E2E
    `tests_e2e/test_card_config_e2e.py::test_req_hom_011_card_explicit_bp_input_overrides_hidden_display`.
  - [x] `show_person: false` ohne `entry_id` → erste Person, kein Dropdown.
    **Beleg:** `::test_card_head_respects_show_person`.
  - [x] `drinks` filtert die Integrations-Quick-Drinks
    (`panel_data.quick_drinks`) nach Key; unbekannte Keys werden ignoriert,
    leer/fehlend = alle (nie ein leerer Zustand). **Beleg:**
    `tests/test_ws_api.py::test_panel_data_quick_drinks_from_options`,
    `::test_panel_data_quick_drinks_default_fallback`,
    `tests/test_card_js.py::test_card_drinks_filter_by_key_and_never_empty`.
  - [x] Legacy-Override `quick_drinks` gewinnt gegenüber `drinks` und der
    Integrationsliste. **Beleg:**
    `::test_card_legacy_quick_drinks_override_wins_over_drinks_filter`.
  - [x] `manual_amounts` (Default `[200, 500]`) und `allow_custom_amount`
    (Default `true`): Preset-Buttons + freies Feld, Ganzzahl-Validierung
    1…10000, Fehler inline. **Beleg:**
    `::test_card_manual_amounts_presets_custom_field_and_bounds`.
  - [x] Blutdruck-Eingabe nutzt `health_o_mat.add_blood_pressure` inkl.
    `note` (einklappbares Feld, Default zu) und Bereichsgrenzen
    (Sys/Dia 40–260, Puls 20–250). **Beleg:**
    `::test_card_bp_input_uses_service_with_note_and_bounds`.
  - [x] Wohlbefinden-Eingabe: zehn Buttons aus der (server-gelieferten) Skala,
    aktiver Zustand markiert (`aria-pressed`), Aufruf von
    `health_o_mat.set_wellbeing`. **Beleg:**
    `::test_card_wellbeing_input_service_scale_and_active_state`.
  - [x] Neuer Service `health_o_mat.set_wellbeing` (`person` optional,
    `status` Pflicht, gültig: `very_bad`/`bad`/`okay`/`good`/`great`);
    ungültiger Status → `ServiceValidationError`; derselbe Store-/Refresh-Pfad
    wie das WS-Kommando. `services.yaml` und
    `strings.json`/`de.json`/`en.json` dokumentieren ihn. **Beleg:**
    `tests/test_wave_a.py::test_set_wellbeing_service_registered_with_schema`,
    `::test_set_wellbeing_service_persists_and_refreshes`,
    `::test_set_wellbeing_service_rejects_unknown_status`,
    `tests/test_translations.py::test_set_wellbeing_service_documented_in_all_translations`.
  - [x] Buchung sendet den Getränketyp (`drink_type` = Label) statt immer
    „Eigen" — Breakdown nach Getränketyp wieder korrekt; manuelle Mengen senden
    „Eigen". **Beleg:**
    `::test_card_drink_booking_sends_the_label_as_drink_type`.
  - [x] Alle Blöcke aus → lesbarer Hinweis statt leerer Karte. **Beleg:**
    `::test_card_all_blocks_off_renders_readable_hint`; E2E
    `tests_e2e/test_card_config_e2e.py::test_req_hom_011_card_all_blocks_off_shows_the_hint`.
  - [x] Editor gruppiert alle neun `show_*`-Schalter als „Anzeige" (4) und
    „Eingabe & Aktionen" (5), lädt die Getränke der Person (lesend) und bietet
    Mehrfachauswahl + Mengenliste + Schalter „freies Feld"; jede Änderung feuert
    `config-changed`. Ohne Personendaten bleibt der Editor bedienbar
    (Hinweis, Auswahl „alle"). **Beleg:**
    `::test_card_editor_renders_all_nine_flags_in_two_groups`,
    `::test_card_editor_loads_drinks_and_renders_selection_and_amounts`,
    `::test_card_editor_dispatches_full_config_with_real_booleans`.
  - [x] Panel: Verlaufsliste unter dem **unveränderten** Score-Chart (letzte 20
    Meldungen) mit Zeitpunkt, Emoji, Label und Score; reine Anzeige, alle Texte
    escaped; der aktuelle Live-Wert bleibt in Kopfzeile/Chart-Marker. **Beleg:**
    `tests/test_panel_js.py::test_panel_wellbeing_history_lists_time_emoji_label_and_score`,
    `::test_panel_wellbeing_history_renders_escaped_entries`.
  - [x] Browser-E2E (Playwright): `tests_e2e/test_card_config_e2e.py` mit
    **7 Tests** — alle Blöcke aus, BD-Anzeige aus, explizite BD-Eingabe,
    Hydration aus, Konfigurations-Neuspeichern, BD-Eingabe schreibt,
    Wohlbefinden-Eingabe schreibt und aktualisiert die UI. **Live-Beleg
    (geteilte Instanz `ha-test`):** Card-E2E **7/7** grün, Panel-E2E **6/6**
    grün (ein HA-Neustart; die deployte Card-JS wurde byte-identisch zum Repo
    verifiziert). Der Live-Lauf deckte einen **Listener-Lifecycle-Defekt** auf
    (Listener waren nur im Konstruktor registriert und gingen beim
    Detach/Re-Attach der Karte verloren) — behoben durch Registrierung in
    `connectedCallback` mit Cleanup in `disconnectedCallback`; **vor** dem
    Release gefunden, kein ausgelieferter Bug.
  - [x] **Datenintegrität beim Personenwechsel:** Ein echter Wechsel der Person
    (nicht das erneute Wählen derselben) verwirft die personenbezogenen
    Blutdruck-/Mengen-Entwürfe und die Inline-Fehler (`_bpDraft`,
    `_amountDraft`, `_bpError`, `_amountError`, `_wbError`, `_actionError`) —
    ein für Person A getippter Entwurf kann damit nie unter Person B gespeichert
    werden. **Beleg:**
    `tests/test_card_js.py::test_card_person_switch_resets_person_scoped_state`
    (statischer Struktur-Pin: Aufräumen ausschließlich hinter der
    Wechsel-Prüfung, damit das erneute Wählen derselben Person nichts löscht) und
    `::test_card_person_switch_drops_person_scoped_drafts` (Node-Verhaltenstest
    inkl. Kontrollfall „dieselbe Person erneut gewählt").
  - [x] Unit-Test-Beleg: `pytest -q` → **733 passed**; `ruff` clean. Die **+3**
    gegenüber dem zuvor dokumentierten Stand stammen aus dem F3-Follow-up
    (Struktur-Pins + Node-Verhaltenstest, siehe Kriterium oben).

#### REQ-HOM-114 — Wohlbefinden-Bestätigung vor Übernahme
- **Priorität:** P2 · **Aufwand:** M (Backend-Option inklusive striktem
  WS-Schema, Panel-Admin-Maske und Detail-Tab, Karten-Option inklusive Editor,
  Unit-/Node-Tests und README)
- **Status: Erledigt (Branch `feat/wellbeing-confirm`, 2026-10-24)** — im
  **Working Tree** implementiert und getestet, **noch nicht committet**, kein
  Release. **Kein Versions-Bump:** `manifest.json` und die `?v=`-Cache-Buster
  bleiben unverändert; der Release folgt separat.
- **Anforderung:** Die Wohlbefindens-Meldung kann optional eine **Bestätigung
  vor der Übernahme** verlangen. Dafür existieren **zwei unabhängige Schalter**
  mit demselben Namen `wellbeing_confirm` (bool, **Default `false`**). Die
  Default-Semantik ist bewusst **kein Verhaltenswechsel**: ohne explizite
  Aktivierung meldet ein Klick/Absenden weiterhin sofort.
  **Teil A — Panel-/Server-Option pro Config-Entry:** Die Option wird pro
  Config-Entry in `entry.options` persistiert und ausschließlich über das
  bestehende WebSocket-Kommando `health_o_mat/set_settings` gelesen/geschrieben
  (Schlüssel in `SETTINGS_KEYS`/`SETTINGS_SCHEMA`, `build_settings`,
  `parse_settings_message`; `get_settings` liefert den Wert). Die Validierung ist
  **strikt bool**: nur echte JSON-Booleans werden akzeptiert; `"true"`,
  `"false"`, `1` und `0` werden mit `invalid_format` und einer präzisen
  Feldmeldung (Schlüsselname + „Boolean") abgelehnt, ohne Teil-Update. Die
  Panel-Admin-Maske bietet eine Checkbox; der Detail-Tab kennt die Option über
  den `panel_data`-Payload und **merkt eine Auswahl vor**, statt sie sofort zu
  melden — erst ein expliziter Bestätigungsbutton übernimmt sie. Die Option ist
  **kein Formularfeld** des Options-Flows und muss dort unverändert erhalten
  bleiben.
  **Teil B — Karten-Option:** Die Lovelace-Karte erhält eine **eigene**
  Konfigurationsoption `wellbeing_confirm` (bool, Default `false`), die der
  Karten-Editor als Checkbox anbietet. Sie ist **nicht an die Server-Option
  gekoppelt**: weder aktiviert die Server-Option die Karte, noch umgekehrt; die
  Karte liest ausschließlich ihre eigene Konfiguration. Bei aktivierter Option
  wird die gewählte Wohlbefindens-Stufe (Key oder numerischer Score)
  **vorgemerkt** und als solche markiert („noch nicht gemeldet"); der
  Bestätigungsbutton erscheint **nur bei aktiver Option und vorhandener
  Vormerkung** und ruft erst dann `health_o_mat.set_wellbeing` auf.
  **Vormerkung (Pending):** Eine Vormerkung ist **personenbezogen** und wird bei
  einem echten Personenwechsel sowie bei einer Neukonfiguration der Karte
  (`setConfig`) beziehungsweise einem Wechsel zur Übersicht oder einem Reload
  des Panels **verworfen** — sie darf nie unter einer anderen Person oder mit
  veralteter Konfiguration übernommen werden. Schlägt die Übernahme fehl, bleibt
  die Vormerkung für einen erneuten Versuch erhalten. **Nicht-Ziel:** Änderung
  von `unique_id`s, neue Persistenz von Gesundheitsdaten, neue Entity-Typen.
- **Akzeptanzkriterien:**
  - [x] Teil A — **Persistenz und Default:** Ohne Option liefert `get_settings`
    `false`; eine gesetzte Option kommt als `true` zurück; `set_settings`
    persistiert echte Booleans über den Options-Pfad und **merged** mit
    bestehenden Optionen (kein Ersetzen). **Beleg:**
    `tests/test_ws_api.py::test_req_hom_114_get_settings_wellbeing_confirm_defaults_false`,
    `::test_req_hom_114_get_settings_returns_configured_wellbeing_confirm`,
    `::test_req_hom_114_set_settings_accepts_bool_and_persists_options`.
  - [x] Teil A — **Strikte bool-Validierung:** `"true"`, `"false"`, `1` und `0`
    werden abgelehnt (`invalid_format`, Feldname und „Boolean" in der Meldung),
    es wird nichts persistiert; derselbe Vertrag gilt für
    `parse_settings_message` (Roundtrip `true` → Options → `build_settings`,
    `"false"` → Feldmeldung). **Beleg:**
    `::test_req_hom_114_set_settings_rejects_non_boolean_wellbeing_confirm`
    (parametrisiert über alle vier Unfug-Werte),
    `::test_req_hom_114_parse_settings_message_roundtrip`,
    `::test_req_hom_114_parse_settings_message_rejects_string_bool`.
  - [x] Teil A — **Detail-Tab kennt die Option ohne `get_settings`:** Der
    `panel_data`-Payload enthält `wellbeing_confirm` als echtes Boolean
    (`isinstance(..., bool)`), Default `false`, gesetzte Option `true`. **Beleg:**
    `::test_req_hom_114_panel_data_carries_wellbeing_confirm`.
  - [x] Teil A — **Admin-Maske:** Checkbox im Wohlbefinden-Bereich
    (`data-field="wellbeing_confirm"`, Label „Wohlbefinden: Bestätigung vor
    Übernahme"), Fallback `false` im Basis-Modul, Sammeln und PATCH-Vergleich im
    Entry-Modul über denselben `set_settings`-Pfad. **Beleg:**
    `tests/test_panel_js.py::test_req_hom_114_panel_admin_has_wellbeing_confirm_checkbox`.
  - [x] Teil A — **Detail-Tab merkt vor statt sofort zu melden:** Die
    vorgemerkte Stufe ist als `pending` markiert, der gespeicherte Zustand bleibt
    `active`, der Bestätigungsbutton („Übernehmen") erscheint nur mit Vormerkung
    und nur bei aktiver Option. **Beleg:**
    `tests/test_panel_js.py::test_req_hom_114_panel_views_show_pending_selection_and_confirm_button`,
    `::test_req_hom_114_panel_views_confirm_button_only_with_pending`,
    `::test_req_hom_114_panel_defers_wellbeing_report_until_confirmation`
    (Kontrollfall `false` meldet sofort; Personenwechsel, Übersicht und Reload
    verwerfen die Vormerkung).
  - [x] Teil A — **Options-Flow erhält die Option:** Obwohl
    `wellbeing_confirm` kein Formularfeld hat, bleibt ein gesetzter Wert nach
    dem Durchlaufen des Options-Flows in `entry.options` erhalten. **Beleg:**
    `tests/test_config_flow.py::test_req_hom_114_options_flow_preserves_wellbeing_confirm`.
  - [x] Teil B — **Karten-Verhalten:** Normalizer-Default `false`, explizit
    `true`/`false` werden übernommen; bei `true` werden Key- und
    Score-Auswahl vorgemerkt (keine Service-Aufrufe im Klickpfad), als `pending`
    markiert und mit Hinweis „noch nicht gemeldet" plus Bestätigungsbutton
    versehen; erst die Bestätigung meldet. Kontrollfall `false`: die Meldung geht
    sofort raus (bisheriges Verhalten). **Beleg:**
    `tests/test_card_js.py::test_req_hom_114_card_defers_wellbeing_report_until_confirmation`,
    `::test_req_hom_114_card_confirm_button_needs_pending_selection`
    (Button hängt an Vormerkung **und** Option, nicht am Modus allein).
  - [x] Teil B — **Pending-Reset und Fehlerfall (Karte):** Personenwechsel und
    `setConfig` verwerfen die Vormerkung; nach einem Fehler bleibt sie für einen
    erneuten Versuch erhalten und die Fehlermeldung ist gesetzt. **Beleg:**
    `::test_req_hom_114_card_defers_wellbeing_report_until_confirmation`
    (Abschnitte `switched`, `reconfigured`, `failed`).
  - [x] Teil B — **Editor:** eigener Schalter „Wohlbefinden: Bestätigung vor
    Übernahme" (`data-key="wellbeing_confirm"`), Default `false`; Einschalten
    setzt explizit `true`, Ausschalten entfernt den Key; der Schalter ist
    **nicht** Teil der auf neun Einträge gepinnten `show_*`-Liste. **Beleg:**
    `::test_req_hom_114_card_editor_has_wellbeing_confirm_checkbox`.
  - [x] **Unabhängigkeit der beiden Optionen:** Karte und Panel beziehen den
    Schalter aus **getrennten** Quellen (Karten-Konfiguration vs.
    `entry.options`/`panel_data`); die jeweiligen Tests setzen bewusst nur eine
    Quelle und belegen das Verhalten der anderen Seite unabhängig davon
    (`::test_req_hom_114_card_defers_wellbeing_report_until_confirmation` vs.
    `tests/test_panel_js.py::test_req_hom_114_panel_defers_wellbeing_report_until_confirmation`).
  - [x] **Doku:** README beschreibt die Karten-Option (Abschnitt
    „Karten-Konfiguration", Default `false`, ausdrücklich unabhängig von der
    Panel-/Server-Option) und die Admin-Option (Abschnitt
    „Admin-/Settings-Ansicht").
  - [x] **Unit-Test-Beleg:** `pytest -q` → **812 passed**; `ruff check .` clean.
  - [x] **E2E-Beleg:** `pytest tests_e2e/ -v` gegen eine reale HA-Instanz
    (Docker, HA `stable`) → **15 passed**, davon **2 neue** Fälle in
    `tests_e2e/test_wellbeing_confirm_e2e.py`: Karten-Option (Vormerkung,
    kein Server-Write vor Bestätigung, Übernahme per Button) und Panel-Admin-
    Option (Checkbox speichert, Panel meldet erst nach Bestätigung).

#### REQ-HOM-115 — Korrigierbarkeit: Verlauf, Void/Restore, Audit-Log
- **Priorität:** P1 · **Aufwand:** L (6–8 Tage)
- **Status: Erledigt (Branch `feat/ux-p1`, 2026-10-26)** — umgesetzt und getestet;
  **Release 0.14.0 veröffentlicht (2026-10-26)** (Version-Bump/Tag/GitHub-Release).
- **Plan:** `docs/PLAN-UX-P1.md`, WS1
- **Anforderung:** Getränke, Blutdruck und Wohlbefinden sind nachträglich
  korrigierbar: je Datentyp gibt es einen **Verlauf** (aktiv/gelöscht), **Löschen
  (Void)**, **Wiederherstellen (Restore)** und **Undo**. Ein **Hard-Delete in der
  UI ist dauerhaft ausgeschlossen** — Löschen bedeutet Void, Wiederherstellen
  bedeutet Restore; vollständige Datenentfernung bleibt ein manueller Vorgang
  außerhalb der UI (dokumentiertes Restrisiko). Jede Änderung erzeugt ein
  **Audit-Ereignis** (wer/was/wann), das Audit-Log ist append-only und enthält
  keine vollen Gesundheitswerte. Der **Audit-Cap** liegt per Default bei **1000
  Ereignissen pro Person**; im Admin ist `0` = **unbegrenzt** einstellbar.
- **Akzeptanzkriterien:**
  - [x] Kein stilles Überschreiben/Entfernen; jede Änderung hat ein Audit-Event —
    Store-Schema **v4** (`STORE_SCHEMA_VERSION = 4`) ergänzt `id`/`created_at`/
    `voided_at`; Add, Void und Restore schreiben je ein Audit-Event.
    **Beleg:** `tests/test_store.py::test_store_migration_to_v4_adds_ids_and_void_fields`,
    `::test_audit_log_records_add_void_restore`,
    `::test_audit_log_covers_reading_and_wellbeing`.
  - [x] Gelöschte Einträge sind in allen abgeleiteten Werten nicht enthalten
    (heute/gestern/Prozent, Trends, Streak, BD-Ø, Koffein, Lifetime,
    Panel-Payload, Sensoren, Export, Import) — aktive Views/`active_entries`
    filtern Voided konsistent in Store, Sensoren, Binary-Sensoren, Select,
    WS-Payload, Export und Import. **Beleg:**
    `tests/test_store.py::test_active_helpers_filter_voided_entries`,
    `::test_active_entry_filters_voided_lists_and_rebuilds_wellbeing`,
    `tests/test_sensor.py::test_m2a_voided_drink_excluded_from_today_percent_yesterday_history`,
    `::test_m2a_voided_reading_excluded_from_bp_sensors`,
    `::test_m2a_voided_wellbeing_excluded_from_since_and_score`,
    `tests/test_binary_sensor.py::test_m2a_goal_reached_ignores_voided_drink`,
    `tests/test_ws_api.py::test_m2a_panel_data_excludes_voided_entries`,
    `tests/test_import_backup.py::test_export_csv_excludes_voided_entries`.
  - [x] Restore stellt den exakten Vorher-Zustand wieder her — `store.restore_*`
    macht Void rückgängig (inkl. Lifetime-Symmetrie und Wohlbefinden-Spiegel).
    **Beleg:** `tests/test_store.py::test_void_and_restore_drink_updates_lifetime`,
    `::test_void_and_restore_reading`,
    `::test_void_and_restore_wellbeing_falls_back_to_predecessor`,
    `tests/test_ws_api.py::test_restore_entry_calls_store_restore`.
  - [x] `remove_last_entry` verliert keine Daten (Void statt Pop) —
    `tests/test_store.py::test_remove_last_drink_voids_entry`,
    `::test_remove_last_drink_skips_already_voided_tail`,
    `::test_remove_last_wellbeing_voids_last_active_event`;
    `tests/test_wave_a.py::test_remove_last_entry_default_kind_removes_drink`,
    `::test_remove_last_entry_kind_blood_pressure_removes_reading`,
    `::test_remove_last_entry_kind_wellbeing_voids_last_report`.
  - [x] Backup enthält Audit- und voided Einträge; CSV exportiert standardmäßig
    nur aktive Einträge (dokumentiert) —
    `tests/test_import_backup.py::test_backup_contains_voided_entries_and_audit`,
    `::test_build_backup_document_counts_voided_separately`,
    `::test_export_csv_excludes_voided_entries`,
    `::test_export_csv_excludes_voided_entries_from_archive`.
  - [x] Kein Hard-Delete in der UI; Audit-Cap wirkt (Default 1000, `0` =
    unbegrenzt); voided Einträge bleiben erhalten — `DEFAULT_AUDIT_LIMIT = 1000`,
    `0` = unbegrenzt. **Beleg:**
    `tests/test_store.py::test_audit_log_cap_prunes_oldest_with_summary`,
    `::test_audit_log_cap_zero_means_unlimited`,
    `::test_audit_log_default_cap_from_const`,
    `tests/test_ws_api.py::test_settings_audit_limit_default_zero_and_validation`.
  - [x] Verlauf/Undo in Panel und Karte; mobil bedienbar; de/en —
    History-API (`list_history` default nur aktiv, `include_voided` additiv),
    Panel-Filter/Inline-Bestätigung + mobile CSS, Karten-Undo für alle Typen.
    **Beleg:** `tests/test_ws_api.py::test_list_history_defaults_to_active_entries_only`,
    `::test_list_history_include_voided_sorted_desc_and_normalized`,
    `::test_list_history_wellbeing_kind`,
    `tests/test_panel_js.py::test_req_hom_115_panel_history_flow`,
    `::test_panel_history_renders_kinds_filter_and_inline_confirm`,
    `::test_panel_history_css_is_mobile_readable`,
    `tests/test_card_js.py::test_card_history_and_undo_for_all_kinds`,
    `tests_e2e/test_history_e2e.py::test_req_hom_115_120_panel_backdates_then_voids_and_restores`.
  - **Beleg:** Unit **1159 passed**, `ruff check .` + `ruff format --check .` clean;
    E2E **18 passed** (realer HA-Docker-Stack).

#### REQ-HOM-116 — Backup-Restore inkl. Teil-Restore und Dry-Run
- **Priorität:** P1 · **Aufwand:** L (5–7 Tage)
- **Status: Erledigt (Branch `feat/ux-p1`, 2026-10-26)** — umgesetzt und getestet;
  **Release 0.14.0 veröffentlicht (2026-10-26)** (Version-Bump/Tag/GitHub-Release).
- **Plan:** `docs/PLAN-UX-P1.md`, WS2
- **Anforderung:** Backups lassen sich validiert und kontrolliert zurückspielen —
  **Merge (Default) und Replace**, zusätzlich **Teil-Restore** nach Person,
  Datensatz (Getränke/Blutdruck/Wohlbefinden) und Zeitraum, immer mit
  **Dry-Run** und **Pre-Restore-Sicherheitsbackup**. Mehrere Personen werden über
  ein explizites **Personen-Mapping** zugeordnet; unbekannte Personen werden
  **nie stillschweigend angelegt**. V1-Backups bleiben lesbar, neuere Versionen
  werden klar abgelehnt.
- **Akzeptanzkriterien:**
  - [x] Restore ist ohne Datenverlust möglich; Dry-Run zeigt die Wahrheit und
    schreibt nichts — Planung HA-frei (`parse_backup_document`/`plan_restore`),
    Apply in genau einem Save. **Beleg:**
    `tests/test_restore.py::test_apply_dry_run_writes_nothing`.
  - [x] Replace ist auf den gewählten Scope begrenzt und doppelt bestätigt —
    Scope nach Person/Datensatz/Zeitraum, `REPLACE_CONFIRM` erzwungen.
    **Beleg:** `tests/test_restore.py::test_replace_full_person_uses_backup_lifetime`,
    `::test_replace_dataset_keeps_other_datasets`,
    `::test_replace_time_range_only_replaces_window`,
    `::test_replace_with_explicit_all_datasets_is_full_scope`,
    `::test_apply_replace_requires_confirm`.
  - [x] Unbekannte Personen werden nie stillschweigend angelegt (Mapping oder
    Fehler/Skip) — **Beleg:**
    `tests/test_restore.py::test_mapping_missing_person_is_an_error`,
    `::test_mapping_ambiguous_slug_is_an_error`,
    `::test_mapping_person_map_accepts_slug_and_source_id`,
    `::test_mapping_by_slug_case_insensitive`.
  - [x] V1-Backups funktionieren; kaputte/neuere Backups werden klar abgelehnt —
    v1 wird auf v4 migriert, unbekannte/zu neue Schemata und ungültige Dokumente
    werden mit `RestoreError` abgewiesen. **Beleg:**
    `tests/test_restore.py::test_apply_v1_backup_end_to_end`,
    `::test_parse_v1_migrates_entries_to_v4`,
    `::test_validate_rejects_invalid_documents`,
    `::test_parse_v2_without_schema_treats_entries_as_legacy`.
  - [x] Vor jedem echten Restore existiert ein Sicherheitsbackup —
    Pre-Restore-Backup im privaten Export-Verzeichnis.
    **Beleg:** `tests/test_restore.py::test_apply_writes_pre_restore_backup_and_audit_event`.
  - [x] Restore ist atomar (Rollback bei Fehler) und admin-only —
    In-Memory-Rollback bei Save-Fehler; Service/WS admin-gated.
    **Beleg:** `tests/test_restore.py::test_apply_rolls_back_in_memory_on_save_failure`,
    `tests/test_wave_a.py::test_restore_backup_service_rejects_non_admin`,
    `tests/test_ws_api.py::test_restore_backup_requires_admin`.
  - [x] Teil-Restore nach Person, Datensatz und Zeitraum —
    `tests/test_restore.py::test_person_filter_accepts_source_slug_source_id_and_target_id`,
    `::test_dataset_filter_limits_changes`,
    `::test_time_filter_is_inclusive_on_ts`.
  - [x] Backup **v2 inklusive Archiv** und Restore des Archivs —
    `tests/test_import_backup.py::test_build_backup_document_includes_archive_additively`,
    `::test_async_backup_includes_archive_store`,
    `tests/test_restore.py::test_parse_v2_keeps_archive`,
    `::test_merge_imports_archive_and_adds_lifetime`,
    `::test_apply_archive_replace_is_persisted`.
  - [x] Admin-Service, WebSocket-Kommando und Panel-/Admin-UI —
    Service `health_o_mat.restore_backup`, WS `health_o_mat/restore_backup`
    (Dry-Run + Apply), Admin-Maske im Panel.
    **Beleg:** `tests/test_wave_a.py::test_restore_backup_service_registered_with_schema`,
    `tests/test_ws_api.py::test_restore_backup_dry_run_returns_plan`,
    `::test_restore_backup_error_is_structured`,
    `tests/test_panel_js.py::test_req_hom_116_panel_restore_flow`.
  - **Beleg:** Unit **1159 passed**, `ruff check .` + `ruff format --check .` clean;
    E2E **18 passed** (realer HA-Docker-Stack).

#### REQ-HOM-117 — UI-Internationalisierung de/en über HA-Translations
- **Priorität:** P1 · **Aufwand:** L (4–6 Tage)
- **Status: Erledigt (Branch `feat/ux-p1`, 2026-10-26)** — umgesetzt und getestet;
  **Release 0.14.0 veröffentlicht (2026-10-26)** (Version-Bump/Tag/GitHub-Release).
- **Plan:** `docs/PLAN-UX-P1.md`, WS3
- **Anforderung:** Panel, Karte und Editor folgen der HA-Sprache — **nur
  HA-nativ de/en**, kein eigenes i18n-Framework. Die UI-Texte liegen als flache
  Schlüssel im von `hassfest` erlaubten `common`-Bereich und werden im Frontend
  über `frontend/get_translations` geladen (mit eingebetteter de/en-Fallback-Map,
  nie rohe Keys). **Entity- und Service-Übersetzungen bleiben unverändert**
  HA-nativ. Datum/Zahlen/relative Zeit laufen über `Intl`/`hass.locale`; ein
  Sprachwechsel zur Laufzeit rendert neu.
- **Akzeptanzkriterien:**
  - [x] Englische HA-Instanz zeigt englische UI; Deutsch bleibt vollständig —
    `common`-Translations in `translations/de.json`/`en.json`, Frontend-Loader
    über `frontend/get_translations`. **Beleg:**
    `tests_e2e/test_i18n_e2e.py::test_req_hom_117_panel_renders_english_labels`,
    `::test_req_hom_117_card_renders_english_labels`.
  - [x] Fehlende Übersetzung fällt sauber zurück und zeigt nie `ui_...`-Rohkeys —
    eingebettete de/en-Fallback-Map in Panel und Karte, Sprachwechsel rendert neu.
    **Beleg:** `tests/test_panel_js.py::test_req_hom_117_panel_translations_load_fallback_and_language_switch`,
    `tests/test_card_js.py::test_req_hom_117_card_inline_translations_and_language_switch`.
  - [x] `hassfest` bleibt grün (nur erlaubte `common`-Struktur) — flache
    Schlüssel im `common`-Bereich, Parität und Platzhalter geprüft. **Beleg:**
    `tests/test_translations.py::test_req_hom_117_common_keys_parity_and_non_empty`,
    `::test_req_hom_117_placeholders_match_between_languages`.
  - [x] Entity-/Service-Übersetzungen unverändert; Paritätstest de/en —
    `tests/test_translations.py::test_req_hom_107_key_tree_parity`,
    `::test_req_hom_117_every_js_key_exists_in_both_languages`.
  - [x] Keine nutzersichtbaren hartkodierten deutschen Strings in Render-Pfaden
    (Logs/Testdaten ausgenommen) — jeder im JS verwendete Key existiert in beiden
    Sprachen (`tests/test_translations.py::test_req_hom_117_every_js_key_exists_in_both_languages`).
  - [x] Sprachwechsel zur Laufzeit wird ohne Reload sichtbar (Neu-Rendern) —
    `tests/test_panel_js.py::test_req_hom_117_panel_translations_load_fallback_and_language_switch`,
    `tests/test_card_js.py::test_req_hom_117_card_inline_translations_and_language_switch`.
  - **Beleg:** Unit **1159 passed**, `ruff check .` + `ruff format --check .` clean;
    E2E **18 passed** (realer HA-Docker-Stack, inkl. `test_i18n_e2e.py` in en-US).

#### REQ-HOM-118 — Erinnerungen, Wochenbericht und Blueprints
- **Priorität:** P1 · **Aufwand:** M–L (5–7 Tage)
- **Status: Erledigt (Branch `feat/ux-p1`, 2026-10-26)** — umgesetzt und getestet;
  **Release 0.14.0 veröffentlicht (2026-10-26)** (Version-Bump/Tag/GitHub-Release).
- **Plan:** `docs/PLAN-UX-P1.md`, WS4
- **Anforderung:** Die Integration erinnert aktiv und liefert einen
  Wochenbericht. **Eingebaute Reminder** laufen über einen beliebigen
  `notify.*`-Service mit **Fallback `persistent_notification`** (Dedup pro Tag,
  Quiet Hours). Der **Wochenbericht wird ausschließlich als Notification**
  (Markdown) versendet — **keine Datei**. Erweiterbare Automationen stehen als
  **Blueprints** (Abend-Erinnerung, BD-Warnung, Wochenbericht) mit frei wählbarer
  Person bereit. Alle Einstellungen sind de/en, Defaults aus, ohne
  Setup-Blockade.
- **Akzeptanzkriterien:**
  - [x] Reminder feuern nur bei erfüllter Bedingung, zur richtigen Zeit, ohne
    Duplikate; Quiet Hours werden respektiert — Scheduler-Timer je Config-Entry,
    Dedup pro Tag, Quiet-Hours-Fenster inkl. Mitternachts-Rollover. **Beleg:**
    `tests/test_reminders.py::test_callback_dedup_same_day`,
    `::test_callback_sends_again_next_day`,
    `::test_callback_skips_quiet_hours`,
    `::test_quiet_hours_midnight_rollover`,
    `::test_setup_registers_both_timers`.
  - [x] Bedingungen abgedeckt: Ziel nicht erreicht, keine Buchung seit X Stunden,
    keine BD-Messung seit X Tagen, keine Wohlbefindens-Meldung seit X Tagen —
    `tests/test_reminders.py::test_reminder_due_goal_and_no_drink`,
    `::test_reminder_due_goal_reached_and_recent_drink`,
    `::test_reminder_due_bp_and_wellbeing_staleness`,
    `::test_reminder_due_voided_drink_does_not_count`.
  - [x] Wochenbericht als Service und optional geplant; Inhalt korrekt;
    Zustellung **nur als Notification** (keine Datei) —
    `tests/test_report.py::test_collect_weekly_metrics_core_numbers`,
    `::test_render_weekly_report_markdown_german_golden`,
    `::test_render_weekly_report_markdown_english`,
    `tests/test_wave_a.py::test_weekly_report_service_sends_one_notification_per_person`,
    `tests/test_reminders.py::test_weekly_callback_sends_report_and_dedups`.
  - [x] Zustellfehler sind sichtbar, aber nicht setup-kritisch — Log statt
    Setup-Abbruch, Fallback auf `persistent_notification`. **Beleg:**
    `tests/test_reminders.py::test_callback_error_is_swallowed`,
    `::test_setup_failure_never_raises`,
    `::test_send_notification_failing_notify_falls_back`.
  - [x] Blueprints sind importierbar und valide; Person frei wählbar — drei
    Blueprints (`evening_reminder`, `blood_pressure_warning`, `weekly_report`),
    Inputs dokumentiert und zweisprachig. **Beleg:**
    `tests/test_blueprints.py::test_blueprint_has_valid_structure`,
    `::test_blueprint_inputs_are_documented_and_bilingual`,
    `::test_weekly_report_blueprint_calls_the_registered_service`.
  - [x] Alle Einstellungen de/en; Defaults aus; keine Setup-Blockade —
    Options-Schritt „Benachrichtigungen" (Defaults alle aus), Timer nur bei
    aktivierter Option. **Beleg:**
    `tests/test_config_flow.py::test_notifications_step_defaults_are_all_off`,
    `tests/test_translations.py::test_m3d_notifications_options_step_documented_in_all_translations`,
    `tests/test_reminders.py::test_setup_disabled_registers_no_timer`.
  - [x] `notify.*`-Service mit Fallback `persistent_notification` —
    `tests/test_reminders.py::test_send_notification_prefers_configured_notify_service`,
    `::test_send_notification_falls_back_to_persistent`,
    `::test_send_notification_empty_service_uses_persistent`.
  - **Beleg:** Unit **1159 passed**, `ruff check .` + `ruff format --check .` clean;
    E2E **18 passed** (realer HA-Docker-Stack).

#### REQ-HOM-119 — Onboarding/Options-Wizard mit optionalen Schritten
- **Priorität:** P1 · **Aufwand:** M (3–4 Tage)
- **Status: Erledigt (Branch `feat/ux-p1`, 2026-10-26)** — umgesetzt und getestet;
  **Release 0.14.0 veröffentlicht (2026-10-26)** (Version-Bump/Tag/GitHub-Release).
- **Plan:** `docs/PLAN-UX-P1.md`, WS5
- **Anforderung:** Der Options-Flow wird ein **Menü mit optionalen Schritten**
  (Grundlagen · Getränke · Wohlbefinden · Benachrichtigungen · Zusammenfassung).
  Jeder Abschnitt ist überspringbar bzw. übernimmt **Defaults**; Änderungen werden
  vorgemerkt und erst in der **Zusammenfassung** gespeichert. Nicht angezeigte
  Optionen bleiben erhalten — **keine Datenverluste**, bestehende Entries
  funktionieren unverändert.
- **Akzeptanzkriterien:**
  - [x] Neuer Nutzer kann mit Defaults in ≤ 2 Schritten abschließen — Menü →
    „Defaults anwenden" springt direkt zur Zusammenfassung. **Beleg:**
    `tests/test_config_flow.py::test_defaults_step_sets_defaults_and_jumps_to_summary`,
    `::test_init_step_shows_menu_with_all_sections`.
  - [x] Jeder optionale Schritt ist überspringbar; Defaults werden angewandt —
    Skip kehrt ohne Änderung ins Menü zurück, Defaults überschreiben nur
    Default-Keys. **Beleg:**
    `tests/test_config_flow.py::test_basics_skip_returns_to_menu_without_changes`,
    `::test_drinks_skip_returns_to_menu_without_changes`,
    `::test_notifications_skip_returns_to_menu_without_changes`,
    `::test_defaults_do_not_drop_previous_pending_changes`.
  - [x] Bestehende Optionen (inkl. `wellbeing_confirm`) bleiben unverändert —
    Merge-Pfad erhält fremde/nicht angezeigte Options-Keys. **Beleg:**
    `tests/test_config_flow.py::test_summary_save_merges_pending_and_preserves_foreign_options`,
    `::test_full_flow_with_skipped_sections_keeps_existing_options`.
  - [x] Nicht angezeigte Options-Keys bleiben beim Speichern erhalten (Merge) —
    `tests/test_config_flow.py::test_summary_save_merges_pending_and_preserves_foreign_options`,
    `::test_defaults_flow_overwrites_default_keys_but_keeps_foreign_options`.
  - [x] Zusammenfassung vor dem Speichern; Abbrechen ändert nichts —
    `tests/test_config_flow.py::test_summary_shows_changed_keys_and_values`,
    `::test_summary_without_changes_shows_placeholder`,
    `::test_cancel_without_save_does_not_create_entry`.
  - [x] Bestehende Entries funktionieren unverändert —
    `tests/test_config_flow.py::test_summary_save_without_changes_keeps_options_identical`,
    `::test_full_flow_with_skipped_sections_keeps_existing_options`.
  - [x] Menü und Schritttexte de/en dokumentiert; README zeigt den Schnellstart
    („Schnellstart: Person anlegen, Defaults nutzen", Options-Wizard).
    **Beleg:** `tests/test_translations.py::test_m3e_options_menu_steps_documented_in_all_translations`,
    `::test_m3e_skip_documented_for_optional_sections`,
    `::test_m3e_summary_documents_changes_placeholder`,
    `::test_m3e_defaults_step_has_description_in_all_translations`.
  - **Beleg:** Unit **1159 passed**, `ruff check .` + `ruff format --check .` clean;
    E2E **18 passed** (realer HA-Docker-Stack).

#### REQ-HOM-120 — Rückdatierte Einträge (unbegrenzt)
- **Priorität:** P1 · **Aufwand:** M (3–4 Tage)
- **Status: Erledigt (Branch `feat/ux-p1`, 2026-10-26)** — umgesetzt und getestet;
  **Release 0.14.0 veröffentlicht (2026-10-26)** (Version-Bump/Tag/GitHub-Release).
- **Plan:** `docs/PLAN-UX-P1.md`, WS6
- **Anforderung:** Getränke, Blutdruck und Wohlbefinden lassen sich mit
  **beliebig weit zurückliegendem Datum/Zeitpunkt** erfassen — **keine
  Zukunft**. Der Erfassungszeitpunkt (`created_at`) wird getrennt vom
  Mess-/Buchungszeitpunkt (`ts`) gespeichert; alle Tages-/Wochen-/Streak-Aggregate
  und Reports verwenden `ts`. **Undo** bezieht sich auf den **zuletzt erfassten**
  Eintrag (Insertion Order), nicht auf den zeitlich größten `ts`.
- **Akzeptanzkriterien:**
  - [x] Rückdatieren funktioniert für alle drei Datentypen, unbegrenzt zurück —
    Service- und WS-Parameter `ts` für Getränk, Blutdruck und Wohlbefinden.
    **Beleg:** `tests/test_wave_a.py::test_req_hom_120_add_drink_service_accepts_ts`,
    `::test_req_hom_120_add_blood_pressure_service_accepts_ts`,
    `::test_req_hom_120_set_wellbeing_service_accepts_ts`,
    `tests/test_ws_api.py::test_req_hom_120_book_drink_sends_backdated_ts`,
    `::test_req_hom_120_save_measurement_sends_backdated_ts`,
    `::test_req_hom_120_set_wellbeing_sends_backdated_ts`.
  - [x] Zukunft wird verständlich abgelehnt — Parser mit Toleranz, Services/WS/
    Panel/Karte validieren und lehnen ab. **Beleg:**
    `tests/test_logic.py::test_req_hom_120_parse_entry_timestamp_rejects_future_with_tolerance`,
    `tests/test_wave_a.py::test_req_hom_120_services_reject_invalid_ts`,
    `tests/test_ws_api.py::test_req_hom_120_ws_rejects_invalid_ts`,
    `tests/test_panel_js.py::test_req_hom_120_panel_sends_ts_and_validates_future`,
    `tests/test_card_js.py::test_req_hom_120_card_sends_ts_and_validates_future`.
  - [x] `created_at` (Erfassung) und `ts` (Messung) sind getrennt gespeichert —
    Store-v4-Felder je Eintrag. **Beleg:**
    `tests/test_store.py::test_add_drink_sets_v4_fields`,
    `::test_add_reading_and_set_wellbeing_set_v4_fields`,
    `tests/test_logic.py::test_req_hom_120_parse_entry_timestamp_accepts_z_and_offsets`.
  - [x] Aggregate, Charts und Reports verwenden den gewählten Zeitpunkt (`ts`) —
    Wohlbefinden-Chronologie/Spiegel folgt `ts`, nicht der Erfassungsreihenfolge.
    **Beleg:** `tests/test_store.py::test_req_hom_120_backdated_wellbeing_current_follows_ts_not_capture_order`,
    `::test_req_hom_120_legacy_mirrors_follow_chronology_after_rebuild`,
    `tests/test_report.py::test_collect_weekly_metrics_ignores_invalid_and_future_timestamps`.
  - [x] Undo entfernt den zuletzt **erfassten**, nicht den zeitlich letzten
    Eintrag; Semantik dokumentiert und getestet —
    `tests/test_store.py::test_req_hom_120_remove_last_wellbeing_uses_capture_order`,
    `::test_req_hom_120_wellbeing_sort_tiebreak_is_created_at_then_insertion`.
  - [x] Ungültige/naive Zeitstempel werden klar abgelehnt bzw. dokumentiert lokal
    interpretiert — **Beleg:**
    `tests/test_logic.py::test_req_hom_120_parse_entry_timestamp_naive_is_local_time`,
    `::test_req_hom_120_parse_entry_timestamp_rejects_garbage`,
    `::test_req_hom_120_parse_entry_timestamp_rejects_too_old_values`,
    `::test_req_hom_120_parse_entry_timestamp_defaults_to_local_reference`.
  - [x] UI bleibt mobil bedienbar; de/en — Panel-/Karten-Zeitfelder mit
    Schnellbuttons, relative-dann-absolute Zeitlabels.
    **Beleg:** `tests/test_panel_js.py::test_req_hom_120_panel_views_render_ts_fields_and_quick_buttons`,
    `::test_req_hom_120_panel_entry_time_is_relative_then_absolute`,
    `tests/test_card_js.py::test_req_hom_120_card_renders_ts_fields_in_all_three_blocks`,
    `::test_req_hom_120_card_payloads_carry_ts`,
    `tests_e2e/test_history_e2e.py::test_req_hom_115_120_panel_backdates_then_voids_and_restores`.
  - **Beleg:** Unit **1159 passed**, `ruff check .` + `ruff format --check .` clean;
    E2E **18 passed** (realer HA-Docker-Stack).

#### REQ-HOM-121 — Wohlbefinden-Zahleneingabe als Number-Entity
- **Priorität:** P2 · **Aufwand:** S
- **Status: Erledigt (Branch `feat/wellbeing-number-entity`, 2026-10-26)** —
  umgesetzt und getestet; **Release 0.15.0 veröffentlicht (2026-10-26)**.
- **Anforderung:** Das Wohlbefinden lässt sich nicht nur über den Select
  (Status-Dropdown) und die Melden-Buttons setzen, sondern auch über eine
  **Number-Entity mit der Score-Skala 1 … N** (N = Anzahl der
  `WELLBEING_STATES`). Die Eingabe bildet den Score über
  `logic.wellbeing_key_for_score` auf den Status-Key ab und meldet ihn über
  denselben Store-Pfad wie Select/Buttons — Verlauf, Score-Sensor und
  Wellbeing-Chronologie bleiben damit konsistent. Die Entity folgt dem
  `areas`-Schalter `wellbeing` (kein Entity bei deaktiviertem Bereich).
- **Akzeptanzkriterien:**
  - [x] Number-Entity `number.…_wellbeing_input` mit `min=1`, `max=N`,
    `step=1`, `mode=BOX`; `native_value` ist der aktuelle Score (bzw.
    `unknown` ohne Meldung). **Beleg:**
    `tests/test_number.py::test_wellbeing_input_native_value_maps_status_to_score`,
    `::test_wellbeing_input_native_value_is_none_without_status`,
    `::test_wellbeing_input_attributes_and_translation_key`.
  - [x] Eine Eingabe meldet den zugehörigen Status über `store.set_wellbeing`
    (inkl. Audit-Limit); ungültige Scores werden ignoriert. **Beleg:**
    `tests/test_number.py::test_wellbeing_input_apply_maps_score_to_status_and_reports`,
    `::test_wellbeing_input_apply_ignores_invalid_score`.
  - [x] Bereichs-Filter: `wellbeing: false` erzeugt keine Number-Entity;
    bestehende Entries ohne `areas` behalten sie. **Beleg:**
    `tests/test_number.py::test_number_setup_wellbeing_disabled_creates_no_wellbeing_number`,
    `::test_number_setup_old_entry_without_options_has_all_areas`.
  - [x] de/en-Übersetzungen (Name „Wohlbefinden-Eingabe" / „Wellbeing input")
    und README/Entity-Tabelle aktualisiert.

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
| F10 Recorder-Metadaten „ml" ≠ Sensor-Einheit „mL" | 🔴 | 111 | — |

---

## 4. Changelog der Anforderungen

| Datum | Änderung |
|---|---|
| 2026-09-06 | Initiale Anlage; nach Review-Feedback in zwei Tracks getrennt: Features (001–010) dokumentiert, Funde & Risiken (101–110) priorisiert; **Umsetzungsplan ausgelagert nach `plan-funde-risiken.md`** (Planner-Konvention: Pläne = eigene Dokumente) |
| 2026-10-15 | REQ-HOM-007 (CSV-Import) als **erledigt** markiert (Branch `feat/import-backup`, alle Akzeptanzkriterien [x] mit Beleg); Notiz ergänzt: `backup`-Service als JSON-Voll-Export existiert, **Restore weiterhin offen** |
| 2026-10-18 | UI-Ausbau (Branch `feat/ui-pro`): **REQ-HOM-009** (Pro-Person Feature-Toggles) **erledigt** (Options `areas`, bedingtes Entity-Setup, E2E auf `ha-test`); **neu angelegt** REQ-HOM-011 (Card-Ausbau), **012** (Person-Ansicht + Deep-Link), **013** (Admin-/Instanzverwaltung), **014** (Frontend-Struktur, NFA) — alle erledigt. Nebenfixes gegen durch die Toggles ausgelöste Reloads: Lebenszähler wird im Reload-Pfad nicht mehr zurückgesetzt, Panel wird beim Entfernen der letzten freischaltenden Person abgemeldet, Bestands-Card-Ressource auf den Cache-Buster nachgezogen. **Offen:** Browser-Smoke (Playwright) für den Deep-Link (REQ-HOM-012) |
| 2026-10-19 | **Recorder-Einheiten-Fix** (Branch `fix/recorder-unit-migration`): **neu angelegt** REQ-HOM-111 (Fix F10, P1, Aufwand S) — **erledigt**. Die Integration migriert beim Config-Entry-Setup die Recorder-Statistik-Metadaten der beiden Volumen-Sensoren je Person von der Legacy-Einheit „ml" auf die HA-kanonische Einheit „mL" (`new_unit_of_measurement="mL"`, `new_unit_class="volume"`); bislang unterdrückte HA die Langzeitstatistik komplett („Generation of long term statistics will be suppressed"). Migration ist idempotent und verlustfrei, läuft bei deaktiviertem Recorder erst beim nächsten Setup (HA-Neustart/Entry-Reload) und ist nie setup-kritisch; die beiden Number-Entities melden nun ebenfalls „mL" (Datenfelder `daily_goal_ml` / `ml` in JSON/CSV unverändert), `unique_id`/`entity_id` und `manifest.json` unangetastet. E2E auf `ha-test` (HA 2026.9.1): vorher 4 `statistic_id`s mit `ml` (`unit_class` NULL) + 24 Recorder-Warnungen über 6 Starts + eingefrorene Statistik seit 2026-10-17, nachher `mL` + `unit_class` `volume`, 0 Warnungen, Kurzzeit-/Langzeitstatistik wieder laufend (ab 22:05 bzw. 2026-10-19 22:00), Kontroll-IDs und Store-Daten unverändert; `pytest -q` 580 passed, ruff clean. README: Einheiten-Angaben auf „mL" vereinheitlicht + Migrations-Hinweis für Alt-Installationen ergänzt |
| 2026-10-19 | **Neu angelegt: REQ-HOM-112 — Wohlbefinden-Score & Verlaufs-Chart** (Branch `feat/wellbeing-score`): numerische Darstellung des Wohlbefindens **1…5**, reihenfolgetreu aus den fünf Zuständen abgeleitet und **rein abgeleitet/on-read** (keine eigene Persistenz, keine Migration); Sensor `wellbeing_score` (`measurement`, ohne Einheit/`device_class`, `unknown` ohne Meldung, Attribute `reported_at`/`scale_max`); **additiver** `score`-Key im WS-Payload `health_o_mat/panel_data` (aktueller Wert + je `wellbeing.history`-Eintrag, bestehende Schlüssel unverändert); Score-Chart in der **Card** (Badge + kompakte Sparkline der letzten 14 Meldungen) und im **Panel** (vollständiger SVG-Chart, Y-Achse 1–5, aktueller Wert als Marker, Leerfall mit Hinweis) — beide ohne externe Bibliothek, Farben nur über HA-CSS-Variablen. **Belege:** `tests/test_logic.py::test_req_hom_112_wellbeing_score_maps_every_state_to_index_plus_one`, `tests/test_sensor.py::test_req_hom_112_wellbeing_score_sensor_native_value_matches_status`, `tests/test_ws_api.py::test_req_hom_112_wellbeing_block_contains_current_score`, `tests/test_card_js.py::test_card_wellbeing_score_and_sparkline_helpers_exist`, `tests/test_panel_js.py::test_panel_base_exposes_wellbeing_chart_helpers` (weitere Fälle in den jeweiligen Dateien); `pytest -q` → **666 passed**; `ruff` clean. **E2E-Beleg:** Verifikation auf `ha-test` (HA 2026.9.1) — Report + Screenshots unter `docs/e2e-2026-10-19-wellbeing-score/`. **Code-Review:** durch, keine Blocker — der 🟡-Befund (Panel löste den Score für Kopfzeile und Chart aus zwei Quellen auf) und die 🟢-Befunde (Alias-/Case-Divergenz zwischen Client und Server, undokumentierte dritte Skala-Kopie) sind behoben; der Frontend-Spiegel ist per Mirror-Pinning-Test an `const.WELLBEING_STATES` gebunden (Keys + Reihenfolge + Länge). **Marker-Semantik:** der „aktuell"-Marker hängt am aktuellen Wert (ohne Meldung wird kein Punkt hervorgehoben, die Zusammenfassung nennt „letzter Wert" statt „aktuell"); **Label/Emoji** werden **live-first** aufgelöst (Live-Entity vor veraltetem `panel_data`-Snapshot). **Offen:** der **Release** (Versions-Bump `manifest.version` + `?v=`-Cache-Buster zusammen, Tag, GitHub-Release) |
| 2026-10-18 | **REQ-HOM-012 vollständig erledigt** (Branch `feat/e2e-playwright`): echter Browser-Smoke ergänzt — `tests_e2e/` (Playwright + pytest, 6 Tests) gegen eine reale HA-Instanz plus `scripts/e2e_bootstrap.py` (idempotentes Onboarding/Config-/Options-Flow-Bootstrap), Docker-Stack (`docker-compose.e2e.yml`, `Dockerfile.e2e`, `docker/ha_config_e2e/`) und CI-Workflow `.github/workflows/e2e.yaml` (workflow_dispatch + wöchentlich + PR-Pfadfilter). Unit-Suite unverändert HA-frei (`pytest -q` → 552 passed), E2E nur bei explizitem Aufruf (eigene `tests_e2e/pytest.ini`) |
| 2026-10-21 | **Neu angelegt: REQ-HOM-113 — Konfigurierbare Health-O-Mat-Karte** (Branch `feat/configurable-card`) — **erledigt**. Flaches Schema, alle Schlüssel optional; **Default-Semantik:** die Anzeige-Blöcke bleiben unverändert, die drei neuen Eingabe-Blöcke (manuelle Mengen, BD-Eingabe, Wohlbefinden-Eingabe) sind **per Default aktiv** — bestehende Karten erhalten sie beim Update (bewusste neue Funktion, veröffentlicht in v0.10.0 unter „✨ New features"): neun `show_*`-Schalter (4 Anzeige + 5 Eingabe/Aktionen), `drinks` (Keys aus `panel_data.quick_drinks`, unbekannte ignoriert, leer = alle), `manual_amounts` (Default `[200, 500]`), `allow_custom_amount` (Default `true`), Legacy-Override `quick_drinks` (gewinnt); `show_blood_pressure_input: true` explizit gewinnt gegen `show_blood_pressure: false`; `show_person: false` ohne `entry_id` → erste Person ohne Dropdown; alle Blöcke aus → lesbarer Hinweis. **Backend:** `panel_data.quick_drinks` additiv; neuer öffentlicher Service `health_o_mat.set_wellbeing` (`person` optional, `status` Pflicht, fünf Keys, `ServiceValidationError` bei Unfug, gleicher Store-/Refresh-Pfad) — `button.*_report_*` unverändert; Kartenbuchung sendet `drink_type` (Label) statt „Eigen". **Panel:** Verlaufsliste (Zeitpunkt + Emoji + Label + Score, letzte 20) unter dem unveränderten Score-Chart. **Editor:** gruppiert alle neun Schalter als „Anzeige" (4) und „Eingabe & Aktionen" (5) — Abweichung vom Plan („6/5"). **Belege:** `tests/test_card_js.py` (u. a. `test_card_show_flag_list_covers_exactly_the_nine_schema_keys`, `test_card_explicit_bp_input_flag_overrides_display_flag`, `test_card_drinks_filter_by_key_and_never_empty`, `test_card_editor_renders_all_nine_flags_in_two_groups`), `tests/test_wave_a.py::test_set_wellbeing_service_*`, `tests/test_panel_js.py::test_panel_wellbeing_history_lists_time_emoji_label_and_score`, E2E `tests_e2e/test_card_config_e2e.py` (**7 Tests**; Live-Lauf auf der geteilten Instanz `ha-test`: Card-E2E **7/7**, Panel-E2E **6/6** grün, ein HA-Neustart, deployte Card-JS byte-identisch verifiziert; der Lauf fand vor dem Release einen Listener-Lifecycle-Defekt — Listener waren nur im Konstruktor registriert, behoben durch `connectedCallback`-Registrierung mit `disconnectedCallback`-Cleanup); `pytest -q` → **733 passed**; `ruff` clean. **Release:** v0.10.0 veröffentlicht (`manifest.version` + alle `?v=`-Cache-Buster gemeinsam gebumpt). |
| 2026-10-21 | **v0.10.1 — Fix: Wohlbefinden-Verlauf stempelt den abgelösten Status mit seinem eigenen Meldezeitpunkt** (Branch `fix/wellbeing-history-timestamp`): `store.set_wellbeing` archiviert den abgelösten Status jetzt mit `wb["ts"]` (Meldezeitpunkt) statt mit dem Zeitstempel der ablösenden Meldung. Dadurch zeigt die Verlaufsliste im Panel/der Card den Vorgänger nicht mehr fälschlich als „vor 2 min", direkt nachdem ein neuer Zustand gemeldet wurde. Kein Schema-Umbau, keine Migration. Tests: `tests/test_store.py::test_req_hom_112_wellbeing_history_records_replaced_status_with_report_timestamp` (umbenannt/angepasst) sowie `STORE-017`; `pytest -q` → 733 passed; `ruff` clean. Release v0.10.1 (Patch). |
| 2026-10-23 | **Wellbeing-Ausbau** (Branch `feat/wellbeing-10-scale-images`): Skala auf **1–10** erweitert (bestehende Keys auf 1/3/5/7/9), numerischer Service-/WS-Input (`score`) zusätzlich zum Key, konfigurierbare eigene Bilder je Key (Options-Schritt „Wohlbefinden-Bilder", PNG/JPG/WebP), Wohlbefinden-Zahleneingabe in Card und Panel, Blutdruck-Verlaufsgraph (sys/dia) in Card und Panel sowie Personen-Modus/Filter (`person_mode`, `person_filter`, `default_person`) in der Karte. `pytest -q` → 778 passed. |
| 2026-10-23 | **v0.12.0 — Undo-/Personenfilter-/Admin-Bild-Fixes** (Branch `fix/undo-person-filter-images-admin`): Undo-Button in Card und Panel wird ohne vorhandene Getränkebuchung deaktiviert (`panel_data.undo.drink`) statt einen Service-/WS-Fehler auszulösen; Personen-Filter im Karten-Editor hat einen expliziten Bearbeitungsmodus („Alle Personen“ abwählen → Einzelauswahl), im Modus `fixed` werden die Filter-Checkboxen ausgeblendet; der Panel-Admin-Dialog bietet jetzt Bildfelder für alle zehn Wellbeing-Keys (`set_settings`/`get_settings` um `wellbeing_images` erweitert, serverseitig normalisiert). `pytest -q` → 787 passed; `ruff` clean. |
| 2026-10-24 | **Neu angelegt: REQ-HOM-114 — Wohlbefinden-Bestätigung vor Übernahme** (Branch `feat/wellbeing-confirm`) — **erledigt im Working Tree**, noch kein Commit/Release und **kein Versions-Bump**. Zwei **unabhängige** Schalter `wellbeing_confirm` (bool, Default `false` → kein Verhaltenswechsel): **Teil A** als Panel-/Server-Option pro Config-Entry in `entry.options` über `health_o_mat/set_settings` (`SETTINGS_KEYS`/`SETTINGS_SCHEMA`, `build_settings`, `parse_settings_message`; **strikt bool** — `"true"`/`"false"`/`1`/`0` → `invalid_format`, ohne Teil-Update), Checkbox in der Admin-Maske, `panel_data` liefert den Wert als echtes Boolean, Detail-Tab merkt die Auswahl vor (eigene `pending`-Markierung) und meldet erst per Bestätigungsbutton; **Teil B** als eigenständige Karten-Option mit Editor-Checkbox, Vormerkung (Key oder Score) + Bestätigungsbutton, **nicht** an die Server-Option gekoppelt; Vormerkung wird bei Personenwechsel, `setConfig`, Wechsel zur Übersicht und Reload verworfen, bleibt bei einem Fehler für den erneuten Versuch erhalten. **Belege:** `tests/test_ws_api.py` (7 Testfunktionen `test_req_hom_114_*`, u. a. `::test_req_hom_114_set_settings_rejects_non_boolean_wellbeing_confirm`, `::test_req_hom_114_panel_data_carries_wellbeing_confirm`), `tests/test_panel_js.py::test_req_hom_114_panel_admin_has_wellbeing_confirm_checkbox`, `::test_req_hom_114_panel_defers_wellbeing_report_until_confirmation`, `tests/test_card_js.py::test_req_hom_114_card_defers_wellbeing_report_until_confirmation`, `::test_req_hom_114_card_editor_has_wellbeing_confirm_checkbox`, `tests/test_config_flow.py::test_req_hom_114_options_flow_preserves_wellbeing_confirm`; `pytest -q` → **807 passed**, `ruff check .` clean (**Implementierer-Angabe**; die parallel laufende Tester-Verifikation bleibt abzuwarten). README („Karten-Konfiguration" + Admin-Abschnitt) aktualisiert. |
| 2026-10-25 | **v0.13.0 — Wohlbefinden-Bestätigung vor Übernahme (REQ-HOM-114)** (Branch `feat/wellbeing-confirm`): zwei unabhängige Optionen `wellbeing_confirm` (Default `false`) — pro Person in der Panel-Admin-Maske und als eigene Karten-Option; Auswahl wird vorgemerkt, erst der Bestätigungsbutton meldet. Options-Flow erhält nicht gezeigte Optionen. Unit `812 passed`, E2E `15 passed` (2 neue), ruff check/format clean. Release v0.13.0 (MINOR). |
| 2026-10-25 | **Neu aufgenommen: REQ-HOM-115…120 — UX-P1 / Release 0.14.0** (Branch `feat/ux-p1`): sechs P1-Anforderungen aus `docs/PLAN-UX-P1.md` (WS1–WS6) in Kapitel 2 nach REQ-HOM-114 eingetragen, **Status: Offen — geplant für 0.14.0**, Akzeptanzkriterien als offene Checkboxen. Inhalt: **115** Korrigierbarkeit (Verlauf, Void/Restore, Audit-Log; kein Hard-Delete in der UI; Audit-Cap Default 1000 Ereignisse/Person, Admin `0` = unbegrenzt), **116** Backup-Restore (Merge/Replace + Teil-Restore nach Person/Datensatz/Zeitraum, Dry-Run, Pre-Restore-Backup, Personen-Mapping), **117** UI-i18n **nur HA-nativ de/en** über `common`-Translations/`frontend/get_translations` (Entity-/Service-Translations unverändert), **118** Reminder (`notify.*` + persistenter Fallback), Wochenbericht **nur als Notification** (Markdown, keine Datei) und Blueprints, **119** Options-Wizard mit optionalen Schritten/Defaults und Zusammenfassung ohne Datenverluste, **120** unbegrenzt rückdatierte Einträge (keine Zukunft, `created_at` vs. `ts`, Undo = zuletzt erfasst). Keine bestehenden REQ-IDs umnummeriert; Umsetzung/Belege stehen aus. |
| 2026-10-26 | **REQ-HOM-115…120 umgesetzt (Branch `feat/ux-p1`, Release 0.14.0 veröffentlicht (2026-10-26)):** Void/Restore + Audit-Log (Store v4, Cap Default 1000/`0` = unbegrenzt, kein Hard-Delete in der UI, History-API/-UI, Undo für alle Typen) (115); Backup-Restore mit Merge/Replace, Teil-Restore nach Person/Datensatz/Zeitraum, Dry-Run, Personen-Mapping und Pre-Restore-Backup, Backup v2 inkl. Archiv, Admin-Service/WS/UI (116); HA-native UI-i18n de/en über `common`-Translations mit Loader, Fallback und Laufzeit-Sprachwechsel (117); Reminder/Scheduler mit Quiet Hours und Dedup, `notify.*`-Fallback, Wochenbericht nur als Notification, drei Blueprints, Options-Schritt (118); Options-Wizard mit Menü, optionalen/überspringbaren Schritten, Defaults, Zusammenfassung und Merge-Erhalt (119); unbegrenztes Rückdatieren über `ts` getrennt von `created_at`, Wellbeing-Chronologie, Panel-/Karten-Zeitfelder, Undo = zuletzt erfasst (120). **Belege:** 1159 Unit-Tests, 18 E2E-Tests (realer HA-Docker-Stack, inkl. `test_history_e2e.py` und `test_i18n_e2e.py`), `ruff check .` + `ruff format --check .` clean. |
| 2026-10-26 | **Code-Review-Fixes vor dem 0.14.0-Release (Branch `feat/ux-p1`):** B-1 many-to-one Replace aggregiert Quellrecords pro Ziel/Datensatz, dedupliziert und leert den Scope einmal (Drinks/Readings/Wellbeing/Archiv; Dry-Run == Apply); B-2 Archiv-Store wird beim Setup unabhängig von `retention_months` geladen (nur bei vorhandener Datei) und beim Restore on demand; S-1 naive Restore-Zeitfenster gelten als lokale HA-Zeitzone (UI sendet UTC-ISO); S-2 Dedup normalisiert auf UTC; S-3 `notify.*` mit `blocking=True` + persistent-Fallback bei Handler-Fehlern; S-4 `set_lifetime_ml` nur bei expliziter Änderung (Dirty-Tracking, Wizard-Save nach Buchungen sicher); S-5 Retention schreibt erst Archiv, dann Haupt-Store (Rollback bei Fehler); S-6 Replace validiert Records wie Merge; S-9 Audit-Details ohne Gesundheitswerte (nur `src`/`reason`); S-11 Restore-Liste/Pfad-Whitelist um `health_o_mat_export/*.json` erweitert; S-13 partielles `areas`-Update reaktiviert keine deaktivierten Bereiche; S-14 Export-/Backup-Services admin-gated; N-1 E2E-Docstrings korrigiert; N-7 Replace-Dry-Run ohne `REPLACE`-Bestätigung. **Belege:** `pytest -q` → **1159 passed**, `ruff check .` + `ruff format --check .` clean (kein Live-E2E, Stack gestoppt). |
| 2026-10-26 | **v0.14.0 veröffentlicht** (PR #44, Merge-Commit `618bda8`, Tag `v0.14.0`): Release-Dreiklang abgeschlossen; Tag ↔ `manifest.version` 0.14.0 synchron, alle `?v=`-Cache-Buster auf 0.14.0. CI auf dem Branch-Head: lint, tests, validate (hassfest/HACS) und E2E grün; 1159 Unit-Tests, 18 E2E-Tests, ruff clean. Release-Notes (de/en) unter `docs/RELEASE-NOTES-0.14.0.md`, GitHub-Release: <https://github.com/Popoboxxo/ha-health-o-mat/releases/tag/v0.14.0>. Feature-Branch `feat/ux-p1` bleibt erhalten; HACS-Update-Test und Alt-Entity-Cleanup auf der Dev-Instanz stehen als Betriebs-Follow-up aus. |
| 2026-10-26 | **Neu angelegt: REQ-HOM-121 — Wohlbefinden-Zahleneingabe als Number-Entity** (Branch `feat/wellbeing-number-entity`) — **erledigt und mit Release 0.15.0 veröffentlicht (2026-10-26)**. Neue Number-Entity `number.…_wellbeing_input` (1…10, `step=1`, `mode=BOX`) als UI-loser Gegenpart zu Select und Melden-Buttons: `native_value` liefert den aktuellen Score, eine Eingabe wird über `logic.wellbeing_key_for_score` auf den Status-Key abgebildet und über `store.set_wellbeing` (inkl. Audit-Limit) gemeldet. Bereichs-Filter `wellbeing: false` erzeugt keine Entity; de/en-Übersetzungen und README ergänzt. **Belege:** `tests/test_number.py` (Wellbeing-Input-Fälle + Bereichs-Filter), `pytest -q` → **1167 passed**, `ruff check .` + `ruff format --check .` clean. **Release:** v0.15.0 veröffentlicht (MINOR, keine Migration; Release-Notes: `docs/RELEASE-NOTES-0.15.0.md`). |
| 2026-10-26 | **v0.14.1 — Übersetzungs-Platzhalter-Fix + Dev-Instanz-Upgrade-Test:** Auf `ha-test` (HA 2026.9.1) wurde **HACS 2.0.5 temporär installiert**, `Popoboxxo/ha-health-o-mat` als Custom-Repository (`integration`) registriert und der echte **HACS-Install/Update-Pfad** getestet: Installation **v0.14.0** (HACS `installed_version=v0.14.0`, `pending_upgrade=true`) → Update **v0.14.1** (`pending_upgrade=false`), jeweils mit Neustart/Verifikation; danach HACS + GitHub-Token wieder entfernt. Zusätzlich Upgrade **0.10.2 → 0.14.0** per `bin/sync`: Store-Schema **v3 → v4** migriert (17 Einträge, keine Datenverluste), 4 Config-Entries geladen, **172 Entities** vollständig vorhanden, **keine verwaisten Entities/Devices** (Registry vs. States und Device-Registry geprüft); HACS-Test-Entities nach Entfernen ebenfalls bereinigt. Im Setup-Log fiel ein HA-Übersetzungsfehler auf: `restore_backup.fields.person_map.description` enthielt `{Quelle: Ziel-Entry-ID}` bzw. `{source: target entry ID}` und wurde als ungültiger Platzhalter validiert. **Fix:** Beschreibungen in `services.yaml`, `strings.json`, `de.json`, `en.json` ohne Platzhalter-Klammern; neue Tests für gültige Platzhalter und sprachübergreifende Platzhalter-Parität. **Belege:** `pytest -q` → **1161 passed**, `ruff check .` + `ruff format --check .` clean; Dev-Instanz nach Sync auf 0.14.1 ohne den Übersetzungsfehler. Patch-Release v0.14.1 (keine Migration, keine Entity-Änderungen). |

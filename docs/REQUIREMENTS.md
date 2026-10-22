# Requirements & Roadmap — ha-health-o-mat

**Stand:** 2026-10-21 (Konfigurierbare Karte, REQ-HOM-113, `feat/configurable-card`; zuvor 2026-10-19 Wohlbefinden-Score & Score-Chart, REQ-HOM-112, `feat/wellbeing-score` + Recorder-Einheiten-Fix `fix/recorder-unit-migration`; 2026-10-18 UI-Ausbau, `feat/ui-pro`) · **Quelle:** Detailliertes System-Review v0.4.0 (+ Vorbefunde AUDIT-2026-09-04), UI-Ausbau `docs/IDEATION-UI-PRO.md`
**Status:** Neue Reqs dokumentiert (Kapitel 1) · Funde & Risiken priorisiert (Kapitel 2/3) ·
**REQ-HOM-111** neu aufgenommen (Fund F10, Recorder-Statistik-Einheit „ml" → „mL") ·
**REQ-HOM-112** neu aufgenommen (Feature, Wohlbefinden-Score & Score-Chart) ·
**REQ-HOM-113** neu aufgenommen (Feature, Konfigurierbare Health-O-Mat-Karte) ·
Umsetzungsplan in **`plan-funde-risiken.md`** (eigenes Plan-Dokument, Per Planner-Konvention)

**Zwei getrennte Tracks:**

1. **Neue Anforderungen (Features)** — Kapitel 1, REQ-HOM-001…014: dokumentiert,
   Umsetzung in eigener Reihe (nicht Bestandteil des Fix-Plans).
2. **Funde & Risiken** — Kapitel 2, REQ-HOM-101…113: Bugfix-/Qualitätsanforderungen
   aus dem Review; deren priorisierter Umsetzungsplan liegt in
   **`plan-funde-risiken.md`** und ist das jetzt aktuelle Arbeitsprogramm.
   Ergänzt: **REQ-HOM-112** (Wohlbefinden-Score & Score-Chart) — ein Feature-
   Requirement; am Ende von Kapitel 2 (nach REQ-HOM-111) abgelegt
   (Branch `feat/wellbeing-score`) — sowie **REQ-HOM-113** (Konfigurierbare
   Karte, Branch `feat/configurable-card`) nach REQ-HOM-112.

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
  Darstellung 1 … 5** (1 = „Sehr schlecht" = schlechtester Wert … 5 = „Super" =
  bester Wert). Die Skala ist **reihenfolgetreu aus den fünf Wohlbefinden-
  Zuständen abgeleitet** (Index + 1) und **wächst automatisch mit**, wenn ein
  neuer Zustand hinzukommt. Der Score ist **rein abgeleitet und on-read**: keine
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
    Entity `wellbeing_score` existiert und liefert die Werte **1–5**; ohne
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
  (4) Wohlbefinden-Eingabe (fünf Zustände) ein-/ausschaltbar, (5) alle
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
  - [x] Wohlbefinden-Eingabe: fünf Buttons aus der (server-gelieferten) Skala,
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

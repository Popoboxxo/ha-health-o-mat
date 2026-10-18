# Requirements & Roadmap — ha-health-o-mat

**Stand:** 2026-10-18 (UI-Ausbau, Branch `feat/ui-pro`; Browser-Smoke REQ-HOM-012, Branch `feat/e2e-playwright`) · **Quelle:** Detailliertes System-Review v0.4.0 (+ Vorbefunde AUDIT-2026-09-04), UI-Ausbau `docs/IDEATION-UI-PRO.md`
**Status:** Neue Reqs dokumentiert (Kapitel 1) · Funde & Risiken priorisiert (Kapitel 2/3) ·
Umsetzungsplan in **`plan-funde-risiken.md`** (eigenes Plan-Dokument, Per Planner-Konvention)

**Zwei getrennte Tracks:**

1. **Neue Anforderungen (Features)** — Kapitel 1, REQ-HOM-001…014: dokumentiert,
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
| 2026-10-15 | REQ-HOM-007 (CSV-Import) als **erledigt** markiert (Branch `feat/import-backup`, alle Akzeptanzkriterien [x] mit Beleg); Notiz ergänzt: `backup`-Service als JSON-Voll-Export existiert, **Restore weiterhin offen** |
| 2026-10-18 | UI-Ausbau (Branch `feat/ui-pro`): **REQ-HOM-009** (Pro-Person Feature-Toggles) **erledigt** (Options `areas`, bedingtes Entity-Setup, E2E auf `ha-test`); **neu angelegt** REQ-HOM-011 (Card-Ausbau), **012** (Person-Ansicht + Deep-Link), **013** (Admin-/Instanzverwaltung), **014** (Frontend-Struktur, NFA) — alle erledigt. Nebenfixes gegen durch die Toggles ausgelöste Reloads: Lebenszähler wird im Reload-Pfad nicht mehr zurückgesetzt, Panel wird beim Entfernen der letzten freischaltenden Person abgemeldet, Bestands-Card-Ressource auf den Cache-Buster nachgezogen. **Offen:** Browser-Smoke (Playwright) für den Deep-Link (REQ-HOM-012) |
| 2026-10-18 | **REQ-HOM-012 vollständig erledigt** (Branch `feat/e2e-playwright`): echter Browser-Smoke ergänzt — `tests_e2e/` (Playwright + pytest, 6 Tests) gegen eine reale HA-Instanz plus `scripts/e2e_bootstrap.py` (idempotentes Onboarding/Config-/Options-Flow-Bootstrap), Docker-Stack (`docker-compose.e2e.yml`, `Dockerfile.e2e`, `docker/ha_config_e2e/`) und CI-Workflow `.github/workflows/e2e.yaml` (workflow_dispatch + wöchentlich + PR-Pfadfilter). Unit-Suite unverändert HA-frei (`pytest -q` → 552 passed), E2E nur bei explizitem Aufruf (eigene `tests_e2e/pytest.ini`) |

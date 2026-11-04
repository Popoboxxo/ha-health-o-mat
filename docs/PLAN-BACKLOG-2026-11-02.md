# Backlog-Umsetzungsplan — 0.21.0 (0.19.1 / 0.20.0 übersprungen)

**Status:** Wellen 0–4 als **0.21.0** veröffentlicht (Tag `v0.21.0`, `manifest.version = 0.21.0`, echtes GitHub-Release, `main` @ `640c94d`) — Welle 0 (PR #74), Welle 1, Wellen 2/3 und Welle 4 (PR #84) sind darin enthalten; **0.19.1 und 0.20.0 bewusst übersprungen** · Welle 5 geschlossen: B5 bewusst nicht unterstützt, B6/B7 gestrichen, B9 erledigt, Vision E2–E6 bewusst geparkt · **Datum:** 2026-11-02, Fortschreibung 2026-11-04
**Basis (Planstand):** `manifest.version = 0.19.0` (`custom_components/health_o_mat/manifest.json:22`), `main` @ `2f78dfc`, Tag `v0.19.0`, Arbeitsbaum clean · **Release-Stand heute:** `manifest.version = 0.21.0`, `main` @ `640c94d`, Tag `v0.21.0`
**Vorgänger:** `docs/PLAN-OPEN-ISSUES.md` — abgeschlossen (alle drei Releases veröffentlicht)
**Quellen:** GitHub (`gh issue list`/`gh pr list` = 0 offen, Stand 2026-11-02), `docs/REQUIREMENTS.md`, `docs/REVIEW-2026-10-14.md`, `docs/CONCEPT-UI.md`, `docs/IDEATION-UI-PRO.md`, `docs/IDEATION-VISION.md`, `docs/superpowers/specs/2026-11-02-entity-id-migration-design.md`

**Legende:** `—` in einer Prio-Spalte bedeutet bewusst „keine Priorisierung", nicht „unbekannt". `file:line`-Angaben sind gegen den Stand `2f78dfc` geprüft; Verschiebungen sind bei der Umsetzung erneut zu prüfen.

> **Kein `plan_ref`:** Dieses Dokument ist ein Portfolio-Plan über mehrere Releases. Für Wellen, die durch die `feature-lifecycle`-Pipeline laufen (Welle 2, Welle 4), ist ein eigener Task-Plan mit `pipeline_stages`-Frontmatter zu erstellen und als `payload.plan_ref` zu übergeben.

---

## 1. Ausgangslage

- **GitHub-Backlog leer heißt nicht dokumentierter Backlog leer.** `gh issue list` und `gh pr list` melden am 2026-11-02 jeweils 0 offene Einträge. Insgesamt sind 10 Issues geschlossen: #28, #29, #30, #31, #32, #33, #70, #71, #72, #73.
- **Der Vorgängerplan ist abgearbeitet:** `docs/PLAN-OPEN-ISSUES.md` führte 0.17.3, 0.18.0 und 0.19.0; alle drei Releases sind veröffentlicht; `manifest.version` stand zum Planaufstellungszeitpunkt auf 0.19.0.
- **Was der Vorgängerplan bewusst zurückgelassen hat:** B1 (REQ-HOM-127), B5, B6/B7 und B9 aus `docs/PLAN-OPEN-ISSUES.md:444-451`. B2, B3, B4, B8 und B10 sind dagegen erledigt.
- **Was zusätzlich offen ist:** von REQ-HOM-130 nur noch der reale HACS-Update-Test — Repair-Issue und Erfolgs-Notification sind in Welle 1 umgesetzt. REQ-HOM-010 (Text-Entity `measurement_note`) war bei Planaufstellung offen und ist inzwischen in Welle 2 umgesetzt, REQ-HOM-006 AK 1 (Blueprint-E2E) in Welle 3 (beide mit 0.21.0 veröffentlicht; 0.20.0 übersprungen).
- **Was den Blick verstellt:** Die Dokumentation nennt an mehreren Stellen Release-Stände und Erledigungsgrade, die seit 0.14.0 bis 0.19.0 überholt sind. Solange das so bleibt, ist jede Priorisierung auf falschem Status gebaut — deshalb steht Welle 0 vor allem anderen.

---

## 2. Backlog-Inventar

### 2.1 Echt offen

> **Stand 2026-11-04:** REQ-HOM-127 ist umgesetzt (PR #84), B5/B6/B7/B9 sind entschieden. Die Zeilen bleiben als Beleg stehen; alle Releases sind mit **0.21.0** erfolgt (0.19.1/0.20.0 bewusst übersprungen und gebündelt).

| Item | Inhalt | Prio | Beleg |
|---|---|---|---|
| REQ-HOM-127 | ~~Fehlercode-/i18n-Umbau der Services/WS auf strukturierte `{code, params}` plus lokalisierte Meldungen~~ — **umgesetzt (PR #84) und mit 0.21.0 veröffentlicht** (MINOR + 💥) | P2 | `docs/REQUIREMENTS.md:1516-1538`, `docs/PLAN-AUDIT-2026-11-03.md` WP-A |
| REQ-HOM-006 | ~~Blueprint-E2E-Import auf `ha-test` (AK1) und optionaler Blueprint „Ziel erreicht"~~ — **in Welle 3 umgesetzt** (vierter Blueprint, Personen-Bindungs-Fix, Compose-E2E 19/19); der Import auf der geteilten Instanz bleibt manuelle Abnahme; **mit 0.21.0 veröffentlicht** (0.20.0 übersprungen) | P2 | `docs/REQUIREMENTS.md:172-211` |
| REQ-HOM-010 | ~~Text-Entity `measurement_note` fehlt (`text.py` kennt nur `freetext`)~~ — **in Welle 2 umgesetzt** (Entity, zentrales Leeren, History-/CSV-Beleg); **mit 0.21.0 veröffentlicht** (0.20.0 übersprungen) | P3 | `docs/REQUIREMENTS.md:325-364` |
| REQ-HOM-130 Rest | HACS-Update-Test v0.16.2 nach v0.17.x; Repair-Issue und Erfolgs-Notification (Spec §9 O-1) | P1 | `docs/REQUIREMENTS.md:1766-1772`, `docs/superpowers/specs/2026-11-02-entity-id-migration-design.md:1246-1254` |
| B5 | **geschlossen — bewusst nicht unterstützt:** HbA1c in `%` (DCCT) verlangt eine nicht-lineare Umrechnung aus IFCC; das Risiko einer klinisch falschen Anzeige wiegt schwerer als der Nutzen. `unsupported_unit` bleibt das dokumentierte Verhalten. Reversibel: eigenes Issue bei Bedarf. | — | `docs/PLAN-OPEN-ISSUES.md:449` |
| B6/B7 | **geschlossen — gestrichen:** nie mit Inhalt benannt; ohne belastbare Beschreibung wird nichts rekonstruiert. | — | `docs/PLAN-OPEN-ISSUES.md:450` |
| B9 | **geschlossen — erledigt:** Beobachtung ist über den Audit-Nachtrag abgesetzt; Framework-Thema, nicht Repo-Scope. | — | `docs/PLAN-OPEN-ISSUES.md:452` |

### 2.2 Doku-Drift (kein Backlog, aber Arbeit)

| Stelle | Widerspruch | Korrektur |
|---|---|---|
| `docs/REQUIREMENTS.md:3,36` | Release-Kopf nennt als jüngsten Stand nur 0.17.2; 0.18.0 und 0.19.0 fehlen | Kopf auf 0.19.0 ziehen, 0.18.0/0.19.0 als veröffentlicht führen |
| `docs/REQUIREMENTS.md:42` | REQ-HOM-132 „noch kein Release/Tag" | mit 0.18.0 veröffentlicht |
| `docs/REQUIREMENTS.md:1847` | REQ-HOM-132 Statuszeile wiederholt „noch kein Release/Tag" | wie `:42` korrigieren (zusätzlich gefundene Stelle) |
| `docs/REQUIREMENTS.md:1891-1892` | REQ-HOM-133 „noch kein Release/Tag" | mit 0.19.0 veröffentlicht |
| `docs/REQUIREMENTS.md:211-213,1977` | „Restore ist weiterhin offen" in REQ-HOM-007 und in der Changelog-Zeile | auf REQ-HOM-116 (`:966-1029`) verweisen: seit 0.14.0 erledigt; historische Zeile als „seinerzeit offen" formulieren |
| `docs/REQUIREMENTS.md:417-420` | REQ-HOM-108 „noch nicht veröffentlicht" | mit 0.18.0 veröffentlicht |
| `docs/REQUIREMENTS.md:517-518` | REQ-HOM-112 „Offen: allein der Release" | spätestens mit 0.10.0/0.10.1 ausgeliefert (`CHANGELOG.md:479-495`) |
| `docs/REQUIREMENTS.md:654-656` | REQ-HOM-113 „der Release (v0.10.0) folgt separat" | v0.10.0 ist veröffentlicht (`CHANGELOG.md:487-495`) |
| `docs/REQUIREMENTS.md:779-782` | REQ-HOM-114 „noch nicht committet, kein Release" | v0.13.0 ist veröffentlicht (`docs/REQUIREMENTS.md:1987`) |
| `docs/REQUIREMENTS.md:359-368,371-375,398-413,425-429` | REQ-HOM-101/102/105/106/107/109 führen Akzeptanzkriterien als `[ ]`, obwohl N-2/N-5/N-6 und der Paritätstest erledigt sind | AK mit Beleg abhaken: N-2 (`docs/REVIEW-2026-10-14.md:235`), N-5 (`:238`), N-6 (`:239`), Paritätstest (`docs/REQUIREMENTS.md:1058`, `tests/test_translations.py:75`); REQ-HOM-101/102 nur abhaken, wenn der Code-Beleg (`config_flow.py:251`, `store.py:204-230`) die AK einzeln deckt, sonst Status präzisieren |
| `docs/PLAN-OPEN-ISSUES.md:3-4` | Status „Umsetzung nicht begonnen", Basis 0.17.2 | Statuskopf „abgeschlossen 2026-11-02", Basis 0.19.0 |
| `docs/REVIEW-2026-10-14.md:110-121` | „Restore ist weiterhin offen" | als historischen Stand vom 2026-10-15 kennzeichnen, Verweis auf REQ-HOM-116 |
| `docs/REVIEW-2026-10-14.md:256` | N-10 „Paritätstest offen" | Paritätstest existiert (`tests/test_translations.py:75`) |
| `docs/REVIEW-2026-10-14.md:300-305` | Phase 4 „Backup ist nicht gebaut", CSV-Import offen | durch REQ-HOM-007/116 überholt; Stand vermerken |
| `docs/CONCEPT-UI.md:10-15` | Status „Backup und CSV-Import bleiben offen" | beide erledigt (REQ-HOM-007, REQ-HOM-116) |
| `docs/CONCEPT-UI.md:24-27` | REQ-HOM-112 nennt als Skala-Obergrenze 5 | Skala ist 1–10 (`docs/REQUIREMENTS.md:519-521`) |
| `docs/CONCEPT-UI.md:456,485-488` | Phase 4/5 „offen" inklusive `hydration_pace`, Backup, CSV-Import | auf Ist-Stand ziehen; `hydration_pace` ist implementiert (`docs/REVIEW-2026-10-14.md:98-108`) |
| `docs/IDEATION-UI-PRO.md:7` | „Ist-Stand verifiziert gegen Code @ v0.7.0" | als historischen Recherchestand kennzeichnen, nicht als aktuellen Stand lesen |
| `docs/IDEATION-UI-PRO.md:91-92` | „Restore des JSON-Backups (offen)" | erledigt (REQ-HOM-116) |
| `docs/IDEATION-UI-PRO.md:171-186` | REQ-HOM-001 bis 004 offen, REQ-HOM-009 „nicht implementiert" | REQ-HOM-009 ist implementiert (`docs/REQUIREMENTS.md:227-250`, `areas.py`); Passage als historisch markieren |
| `docs/IDEATION-VISION.md:184` | „Now — 0.14" | erreicht: 0.14.0 veröffentlicht |
| `docs/IDEATION-VISION.md:193` | „Next — 0.15–0.17" | erreicht: 0.15.0 bis 0.17.2 veröffentlicht, aktueller Stand 0.19.0 |
| `docs/IDEATION-VISION.md:255-262` | E2–E6 als offene Punkte | bleiben fachlich offen, gehören nach §2.4 und Welle 5 |

Drift ist kein Backlog-Item im engeren Sinn, blockiert aber jede Priorisierung — deshalb Welle 0.

### 2.3 Bereits erledigt (nicht wieder aufnehmen)

| Punkt | Erledigt durch | Beleg |
|---|---|---|
| B2 | Doku-/REQ-Statusdrift und REQ-HOM-131 nachgetragen (0.18.0) | `docs/PLAN-OPEN-ISSUES.md:445` |
| B3 | Custom-Marker-`require_explicit_unit` in REQ-HOM-133 umgesetzt (0.19.0) | `docs/PLAN-OPEN-ISSUES.md:446` |
| B4 | O-5, BP-Schwelle `>=` (0.18.0) | `docs/PLAN-OPEN-ISSUES.md:447` |
| B8 | `;`/UTF-8-Dokumentation in REQ-HOM-132 (0.18.0) | `docs/PLAN-OPEN-ISSUES.md:450` |
| B10 | Abgleich mit #31 im Frontend-Smoke (WP2) | `docs/PLAN-OPEN-ISSUES.md:452` |

### 2.4 Ideen ohne REQ

| Idee | Umfang | Beleg |
|---|---|---|
| Vision E2–E6 | Mehrbenutzer/ACL, Geräte-Reihenfolge, KI-Opt-in, Mobile, Arzt-Export | `docs/IDEATION-VISION.md:255-262` |
| Lab-Entity-Surface | Optionskatalog A1–A9/B1–B5/C1–C4/R1–R3 mit offenen Fragen an den Nutzer | `docs/superpowers/specs/2026-11-01-lab-entity-surface-options.md:581-593` |
| Spec-Restpunkte O-2/O-3/O-4 | Pre-Pinning-Bestand, übersetzbare Default-Labels, veraltetes Migrations-Rezept in der Doku | `docs/superpowers/specs/2026-11-02-entity-id-migration-design.md:1255-1267` |

---

## 3. Umsetzungswellen

### Welle 0 — Doku-Wahrheit (ausgeliefert in 0.21.0, ohne Produktionscode)

**Ziel:** Die Dokumentation spiegelt 0.19.0. Danach bedeutet „offen" wieder „offen", und „erledigt" ist mit einem Beleg versehen.

**Scope/Dateien:** `docs/REQUIREMENTS.md`, `docs/PLAN-OPEN-ISSUES.md`, `docs/REVIEW-2026-10-14.md`, `docs/CONCEPT-UI.md`, `docs/IDEATION-UI-PRO.md`, `docs/IDEATION-VISION.md`. Kein Produktionscode, keine Tests.

**Agent(en):** `requirements` (ausschließlich `docs/REQUIREMENTS.md`) und `documenter` (alle übrigen Doku-Dateien) arbeiten parallel auf disjunkten Dateien; danach `git`.

**Schritte**

1. `docs/REQUIREMENTS.md`-Kopf auf 0.19.0 ziehen; 0.18.0 und 0.19.0 als veröffentlicht führen (`manifest.json:22`).
2. REQ-HOM-132 (`:42`, `:1847`) und REQ-HOM-133 (`:1891-1892`) auf Release-Status ziehen.
3. REQ-HOM-101/102/105/106/107/109 Akzeptanzkriterien abhaken — nur mit Beleg; REQ-HOM-101/102 gegen `config_flow.py:251` und `store.py:204-230` einzeln prüfen, sonst offen lassen.
4. „Restore weiterhin offen" in `:211-213` und `:1977` durch den Verweis auf REQ-HOM-116 ersetzen.
5. Übrige Release-/Statusaussagen korrigieren: REQ-HOM-108/112/113/114 sowie die Changelog-Zeile.
6. `docs/PLAN-OPEN-ISSUES.md`-Statuskopf auf „abgeschlossen 2026-11-02", Basis 0.19.0.
7. CONCEPT-UI, IDEATION-UI-PRO, IDEATION-VISION und REVIEW auf Ist-Stand ziehen; historische Passagen als historisch kennzeichnen statt sie zu löschen.

**Akzeptanzkriterien**

- `grep -rn --exclude=PLAN-BACKLOG-2026-11-02.md "Restore ist weiterhin offen\|Restore weiterhin offen" docs/` liefert 0 Treffer (auch historische Zeilen umformuliert).
- `grep -rn "noch kein Release" docs/REQUIREMENTS.md` liefert 0 Treffer bei REQ-HOM-132/133.
- Kein Dokument in `docs/` und nicht `README.md` nennt 0.17.2 als aktuellen Stand (historische Release Notes und `CHANGELOG.md` bleiben unangetastet).
- Jede abgehakte AK trägt einen konkreten Beleg (Datei/Test/Commit), keine Sammelbegründung.

**Tests:** Doku-grep plus Gegenprüfung durch `requirements`; kein Code, `python3 -m pytest -q` muss unverändert grün bleiben.

**Risiken:** Versehentliches Abhaken einer echt offenen AK. Gegenmaßnahme: Gegenprüfung gegen Code oder Review-Beleg, im Zweifel offen lassen und den Status präzisieren.

**DoD:** Ein Commit `docs: reconcile backlog and release status` (Englisch, max. 72 Zeichen, BOM-frei), Secret-Scan vor dem Commit.

---

### Welle 1 — REQ-HOM-130 Restpunkte (ausgeliefert in 0.21.0)

**Ziel:** Die Migration meldet sich (Repair-Issue bei Skip, Erfolgs-Notification) und der HACS-Update-Pfad ist belegt.

**Stand Welle 1:** umgesetzt (Branch `feat/130-migration-repairs`, Commit `4d32166`, PR #75) — Repair-Issue (`migration_blocked_<entry_id>`, skalares `data`, Löschung bei sauberem Pass und in `async_remove_entry`), einmalige Erfolgs-Notification (`entity_id_migration_<entry_id>`) und Übersetzungen de/en (Belege: `custom_components/health_o_mat/__init__.py`, `migration.py`, `strings.json`, `translations/{de,en}.json`, `tests/test_entry_migration.py`, `tests/test_remove_entry.py`; **1719 passed**, ruff clean); Update-Pfad 0.16.2 → 0.19.0 auf dem Compose-Stack (8124) **simuliert** belegt (Entry v2→v3, 4 Quick-Drink-Renames, 82 alte `unique_id`s erhalten, 95 Entities, Daten unverändert, eine Notification, kein Repair-Issue, kein `Migration handler not found`, zweiter Neustart idempotent) — die **HACS-Mechanik selbst ist nicht geprüft** (kein HACS im E2E-Image, Bind-Mount read-only, interaktiver Device-Flow).

**Scope/Dateien:** `custom_components/health_o_mat/__init__.py` (`async_migrate_entry`, `:324`), ggf. neues `custom_components/health_o_mat/repairs.py`, `strings.json`, `translations/de.json`, `translations/en.json`, `tests/test_entity_id_migration.py`, `tests/test_entry_migration.py`; HACS-Test auf dem Compose-Stack (Port 8124), **nicht** auf der geteilten Instanz.

**Agent(en):** `developer`, danach `tester`.

**Schritte**

1. Repair-Issue bei `target_occupied`, `device_slug_ambiguous` und `device_slug_unresolved` gemäß Spec §9 O-1 (`docs/superpowers/specs/2026-11-02-entity-id-migration-design.md:1246-1254`).
2. Erfolgs-Notification nach vollständiger Migration — einmalig und idempotent.
3. Übersetzungen in `strings.json`, `translations/de.json`, `translations/en.json` ergänzen (Parität wahren).
4. Unit-Tests für Erzeugung und Auflösung des Repair-Issues sowie für die einmalige Notification.
5. HACS-Update-Test 0.16.2 nach 0.19.0 auf Compose (REQ-HOM-130 nennt v0.17.x als damaliges Ziel): Migration v2 nach v3, Entities und Historie prüfen, Ergebnis dokumentieren.

**Akzeptanzkriterien**

- Bei simulierter Kollision erscheint genau ein Repair-Issue mit den betroffenen Entity-Paaren.
- Nach Auflösung der Kollision verschwindet das Issue.
- Eine erfolgreiche Migration erzeugt genau eine Notification.
- Der Update-Test ist dokumentiert und zeigt keinen Datenverlust.

**Tests:** `tests/test_entry_migration.py` (Issue-Erzeugung/-Auflösung, Idempotenz), `tests/test_entity_id_migration.py`, `tests/test_translations.py` (Parität), Compose-E2E; `python3 -m pytest -q` und `ruff` grün.

**Risiken:** Repair-Issue-Spam bei jedem Start. Gegenmaßnahme: `issue_id` an `entry_id` binden, Issue nur bei Abweichung erzeugen; Notification nur bei echtem Versionswechsel.

**DoD:** `pytest -q` grün, `ruff check .` und `ruff format --check .` clean, REQUIREMENTS.md-Beleg ergänzt, Release-Ziel 0.19.1 (PATCH) — ausgeliefert in 0.21.0.

---

### Welle 2 — REQ-HOM-010 Mess-Notiz (ausgeliefert in 0.21.0)

**Ziel:** Die Text-Entity `measurement_note` ergänzt die BP- und Wohlbefinden-Erfassung, ohne Bestandsdaten zu brechen.

**Stand Welle 2:** umgesetzt (Branch `feat/010-measurement-note`, Plan `docs/superpowers/plans/2026-11-02-measurement-note.md`) — Text-Entity `{entry_id}_text_measurement_note` (`translation_key = "measurement_note"`, `has_entity_name`, max. 255 Zeichen, Gate `AREA_BP`), angefangene Notiz im bereits persistierten `store.inputs["note"]` (Store-Schema v2, kein Bump/Migrator), Leerung zentral in `HealthOMatStore.add_reading`, `SaveReadingButton` reicht die Notiz mit, nach dem Validator-Befund fließt die angefangene Notiz auch über Service `add_blood_pressure` und WS `health_o_mat/save_measurement` (`resolve_reading_note`: explizite Notiz gewinnt, sonst die angefangene), Note in `history_json` und in der Blutdruck-CSV-Spalte `notiz` (additiv). Der E2E-Lauf deckte einen Defekt auf: `async_set_value` stieß den Entity-State nicht — behoben via `async_write_ha_state()`, per Unit-Regressionstest gepinnt. **Belege:** `pytest -q` → **1741 passed**, `ruff check .` + `ruff format --check .` clean, `tests_e2e/test_measurement_note_e2e.py` um den Service-Pfad erweitert (**5 → 7 Szenarien**, **7 E2E-Tests, 7 passed** (Compose-Stack 8124, inkl. Service-Pfad)). **Scope:** nur Blutdruck — `set_wellbeing` hat keinen `note`-Parameter, Wohlbefinden ist bewusst nicht abgedeckt (das ursprüngliche Welle-Ziel nannte Wohlbefinden; die Anforderung selbst nur `save_measurement`). **Ausgeliefert:** mit **0.21.0** (0.20.0 bewusst übersprungen; Welle 3 gehört zum selben Release).

**Scope/Dateien:** `text.py` (neue Entity), `const.py` (Key), `store.py`/`logic.py` (Persistenz und History), `sensor.py`/`binary_sensor.py` nur falls nötig, `strings.json`, `translations/de.json`, `translations/en.json`, `README.md`, `tests/test_text.py`, `tests/test_store.py`, `tests/test_import_backup.py`.

**Agent(en):** Plan zuerst (`planner`, siehe §10; Fallback `documenter`), dann `feature-lifecycle`: `developer`, danach `validator` und `documenter`, danach `git`.

**Schritte**

1. Task-Plan mit `pipeline_stages`-Frontmatter erstellen und als `plan_ref` übergeben.
2. Text-Entity `measurement_note` mit `_attr_has_entity_name = True` und `_attr_translation_key` anlegen (kein Namens-Literal).
3. Key in `const.py` ergänzen, Persistenz und History-Eintrag im Store-Pfad nachziehen, Note beim Speichern als `note` mitführen.
4. Feld nach dem Speichern leeren.
5. Übersetzungen und README ergänzen.
6. Unit- und Compose-E2E-Tests für Erfassung, Leerung, History und CSV ergänzen.

**Akzeptanzkriterien**

- Die Entity existiert pro Person mit `unique_id = {entry_id}_measurement_note` und `device_info`.
- `has_entity_name`/`translation_key` gesetzt, kein Namens-Literal im Code.
- Das Feld wird nach dem Speichern geleert.
- Die Notiz erscheint in `history_json` und im CSV-Export.

**Tests:** Unit (Entity-Aufbau, Persistenz, History, CSV) plus E2E-Erfassung auf Compose; `pytest -q`, `ruff` clean.

**Risiken:** `unique_id`-Disziplin (nie ändern), Namens-Literal verboten, CSV-Spalten nur additiv ergänzen, damit Bestandsimporte nicht brechen.

**DoD:** `pytest`/`ruff` grün, REQUIREMENTS.md aktualisiert, Release-Ziel 0.20.0 (MINOR) — ausgeliefert in 0.21.0.

---

### Welle 3 — REQ-HOM-006 Blueprint-E2E (ausgeliefert in 0.21.0)

**Ziel:** Der Blueprint-Import auf `ha-test` ist automatisiert belegt; der optionale Blueprint „Ziel erreicht" ist ergänzt.

**Stand Welle 3:** umgesetzt — vierter Blueprint `blueprints/automation/health_o_mat/goal_reached.yaml` (Trigger `off → on` des Binärsensors `…_daily_goal_reached`, kein Helfer), `tests/test_blueprints.py` um die Personen-Bindungs-Regression erweitert, `README.md`-Liste drei → vier, neues `tests_e2e/test_blueprints_e2e.py`. Der E2E-Lauf deckte einen echten Defekt auf: `evening_reminder` und `blood_pressure_warning` referenzierten `person_name` im Jinja-Template ohne Bindung (HA substituiert nur `!input`), der Personenname rendete nie — behoben via `variables: {person: !input person_name}` (`weekly_report` braucht das nicht, kein Template). **Belege:** `pytest -q` → **1751 passed**; E2E **19 Tests, 19 passed** (Compose-Stack 8124) — Import via Admin-WS `blueprint/save` → `automation.reload` → `blueprint/list` (alle vier mit Metadaten, Domain, exaktem Input-Set), HA-eigene Validierung (`POST /api/config/automation/config/<id>`, `async_validate_config_item`) akzeptiert `goal_reached` und `evening_reminder` mit konkreten Inputs und liest sie zurück, Negativfälle abgewiesen (`invalid_format` / `Invalid blueprint`, fehlender Input → 400), `blueprint/substitute` + `POST /api/template` rendern den Personennamen (Vorher-Variante ohne). **Abweichung bei AK 1:** der automatisierte Import läuft per Entscheidung D8 (`docs/PLAN-OPEN-ISSUES.md:40`) auf Compose (8124), nicht auf der geteilten Instanz; dort bleibt der Import manuelle Abnahme. **Nicht belegt:** keine Automation feuert tatsächlich (kein `automation:`-Include in der Seed-Konfiguration → keine auslösbare Entity), also kein realer Notify-Aufruf. **Ausgeliefert:** mit **0.21.0** (0.20.0 bewusst übersprungen; gemeinsam mit Welle 2).

**Scope/Dateien:** `tests_e2e/` (neues Blueprint-E2E), `blueprints/automation/health_o_mat/` (optionaler Blueprint), `README.md` und Blueprint-Doku. Bestand: `weekly_report.yaml`, `evening_reminder.yaml`, `blood_pressure_warning.yaml`.

**Agent(en):** `tester`, danach `documenter`.

**Schritte**

1. E2E-Skript für Blueprint-Import und Schema-Validierung schreiben.
2. Optionalen Blueprint „Ziel erreicht" in `blueprints/automation/health_o_mat/` anlegen, inklusive README-Eintrag.
3. Abgrenzung zu REQ-HOM-118 dokumentieren: 118 liefert die vier Blueprints, 006 schließt nur die E2E-Lücke.
4. Negativtest: Import mit Schema-Verstoß muss fehlschlagen.

**Akzeptanzkriterien**

- REQ-HOM-006 AK 1 (`docs/REQUIREMENTS.md:183`) ist erfüllt und mit Testpfad belegt.
- Der Import schlägt bei Schema-Verstoß fehl (Negativtest).
- Der optionale Blueprint ist dokumentiert und in der README gelistet.

**Tests:** E2E auf Compose gegen die gepinnte HA-Version; Negativtest im selben Lauf.

**Risiken:** Geteilte Instanz — daher ausschließlich Compose. Blueprint-Format ist HA-versionsabhängig; gegen die gepinnte E2E-Version testen.

**DoD:** E2E grün, README/REQUIREMENTS aktualisiert, Release-Ziel 0.20.0 (gemeinsam mit Welle 2) — ausgeliefert in 0.21.0.

---

### Welle 4 — REQ-HOM-127 Fehlercode-/i18n-Umbau (0.21.0)

**Ziel:** Strukturierte Fehlercodes `{code, params}` plus lokalisierte Meldungen, additiv via `errors_detail`, ohne Bruch des D6-Vertrags aus REQ-HOM-132.

**Stand Welle 4:** umgesetzt (PR #84) — Konzept APPROVED (`docs/superpowers/specs/2026-11-03-error-contract-design.md`), Transport per D-3 auf HA-native `translation_*` festgelegt (`errors_detail` verworfen), 35 Codes in `logic.ERROR_SPECS`, 29 Service- und 32 WS-Stellen migriert, 4 Relais, `exceptions`-Übersetzungen de/en; Belege `tests/test_error_contract.py`, `tests/test_errors.py`, `docs/SERVICE-RESPONSES.md`. **Ausgeliefert:** mit **0.21.0** veröffentlicht (MINOR + 💥).

**Scope/Dateien:** `custom_components/health_o_mat/__init__.py`, `ws_api.py`, `logic.py`, `strings.json`, `translations/de.json`, `translations/en.json`, betroffene Tests.

**Agent(en):** `concept-development` (`ideation` mit `concept-reviewer`, maximal 3 Iterationen), danach Task-Plan (`planner`), danach `feature-lifecycle`.

**Schritte**

1. Konzept für den Fehlervertrag erstellen und durch `concept-reviewer` freigeben lassen (APPROVED vor Implementierung).
2. Task-Plan mit `pipeline_stages`-Frontmatter erstellen und als `plan_ref` übergeben.
3. Bestehende Service- und WS-Fehler auf `{code, params}` migrieren, `message` als Fallback erhalten.
4. Meldungstexte in `strings.json`, `translations/de.json` und `translations/en.json` lokalisieren (Parität).
5. Tests für Codes, Params, Lokalisierung, `errors`-Cap und Exception-Verhalten ergänzen.

**Akzeptanzkriterien**

- Bestehende Response-Keys aus REQ-HOM-132 bleiben gültig (`docs/REQUIREMENTS.md:1844-1885`).
- Fehler tragen `code` und `params`.
- Meldungen sind de/en lokalisiert.
- Der `errors`-Cap von 20 bleibt bestehen.
- Keine Exception-Regression: Fachfehler bleiben Exceptions, wo REQ-HOM-132 sie als Exception definiert.

**Tests:** bestehende Service-/WS-Tests plus neue Fälle für Code, Params, Lokalisierung und Cap; `pytest -q`, `ruff` clean.

**Risiken:** Vertragsbruch für Panel, Card und Automationen — daher nur additiv. i18n-Parität zwischen `strings.json`, `de.json` und `en.json` muss getestet sein.

**DoD:** Konzept APPROVED vor Implementierung; 💥-Hinweis in den Release Notes, falls Meldungstexte wechseln; Release 0.21.0 (MINOR) — veröffentlicht.

---

### Welle 5 — Entscheidungen und Ideen (kein Release)

**Ziel:** Die zurückgestellten Punkte bekommen eine Entscheidung oder werden bewusst geparkt — ohne Produktionscode.

**Stand Welle 5:** geschlossen (2026-11-04), kein Produktionscode. **B5** bewusst nicht unterstützt (`unsupported_unit` bleibt das Verhalten; die IFCC↔DCCT-Umrechnung ist nicht linear, klinisches Fehlerrisiko), **B6/B7** gestrichen (kein Inhalt dokumentiert), **B9** erledigt (über den Audit-Nachtrag abgesetzt). **Vision E2–E6** bleibt bewusst geparkt — kein Roadmap-Schnitt für 1.x. Die Schritte unten sind damit beantwortet.

**Scope/Dateien:** GitHub-Issues, `docs/REQUIREMENTS.md` (nur durch `requirements`), Meldung an `agent-meta-manager`.

**Agent(en):** `requirements` für B5/B6/B7, `orchestrator` für die B9-Meldung, `ideation` für die Vision-Priorisierung.

**Schritte**

1. B5: **entschieden** — kein Issue; `unsupported_unit` bleibt das Verhalten, ein Issue entsteht nur bei Bedarf (reversibel).
2. B6/B7: **entschieden** — gestrichen (kein Inhalt dokumentiert, `docs/PLAN-OPEN-ISSUES.md:450`).
3. B9: **erledigt** — über den Audit-Nachtrag abgesetzt; Framework-Thema, nicht Repo-Scope.
4. Vision E2–E6: **geparkt**; die Lab-Entity-Surface liegt bei WP-C (D-1 = B4).

**Akzeptanzkriterien**

- B5 ist als „bewusst nicht unterstützt" mit Begründung dokumentiert (Issue nur bei Bedarf).
- B6/B7 sind als „gestrichen" dokumentiert.
- B9 ist als erledigt nachvollziehbar.
- Vision-Punkte tragen den Status „geparkt".

**Tests:** Keine Code-Tests; Prüfung über Issue-Liste und Doku-Diff.

**Risiken:** Entscheidungen ohne Code-Beleg werden zu Wunschlisten. Gegenmaßnahme: jede Entscheidung nennt Scope, Aufwand und betroffene Dateien.

**DoD:** Entscheidungsstand in `docs/REQUIREMENTS.md` beziehungsweise in den Issues nachvollziehbar; kein Release.

---

## 4. Release-Plan

| Release | Inhalt | Typ | Tag | `manifest.version` | Status |
|---|---|---|---|---|---|
| 0.19.1 | Welle 0 und Welle 1 | PATCH | — | — | **übersprungen** (in 0.21.0 enthalten) |
| 0.20.0 | Welle 2 und Welle 3 | MINOR | — | — | **übersprungen** (in 0.21.0 enthalten) |
| 0.21.0 | Wellen 0–4 (0.19.1/0.20.0 gebündelt) | MINOR + 💥 | `v0.21.0` | `0.21.0` | **veröffentlicht** (`main` @ `640c94d`) |
| kein Release | Welle 5 | — | — | — | geschlossen |

`v` nur im Tag, Manifest ohne `v`, zeichenidentisch; Promotion ist ein neuer Tag, nie eine Verschiebung; Tags und Releases sind unveränderlich. Release-Notes: Zusammenfassung, ✨ New features, 💥 Breaking/Verhaltensänderungen mit Migrationshinweis, Full-Changelog-Link. HACS-Update-Test jeweils **nach** dem Release-Dreiklang. **Stand 2026-11-04:** Der Release-Dreiklang für 0.21.0 ist abgeschlossen; der reale HACS-Update-Test bleibt als manuelle Abnahme offen (`docs/PLAN-AUDIT-2026-11-03.md` WP-E) und ist nicht durch diesen Plan belegt.

---

## 5. Reihenfolge und Abhängigkeiten

```
Welle 0 ──► Welle 1 ──► Welle 2 ──► Welle 3 ──► Welle 4
                │                         ▲
                └── planner-Rolle (§10) ──┘   (Welle 2 und 4 brauchen plan_ref)
```

- **Welle 0 zuerst:** Ohne korrigierten Status würde jede Priorisierung auf veralteten Aussagen aufsetzen.
- **Welle 1 nach Welle 0:** Welle 1 ergänzt REQUIREMENTS.md-Belege; das setzt den bereinigten Stand voraus und vermeidet doppelte Doku-Commits.
- **Welle 2 und Welle 4 sind plan-driven:** Beide brauchen einen Task-Plan mit `pipeline_stages`-Frontmatter, sonst kann das Plan-driven Gate nicht sauber erfüllt werden.
- **Welle 4 zuletzt:** Der Vertragsummbau berührt dieselben Response-Pfade, die Welle 2/3 als Konsumenten nutzen; er ist nur additiv tragfähig, wenn die vorherigen Releases stabil sind.
- **Welle 5 ist unabhängig:** Sie kann jederzeit laufen, liefert aber keinen Code und blockiert keinen Release.

---

## 6. Offene Entscheidungen

| # | Entscheidung | Optionen | Wirkung |
|---|---|---|---|
| E-1 | HbA1c in `%` (B5) | **entschieden (2026-11-04):** bei `unsupported_unit` bleiben; reversibel über ein eigenes Issue bei Bedarf | kein Release-Blocker, kein Issue vorerst |
| E-2 | B6/B7 | **entschieden (2026-11-04):** streichen | Backlog-Bereinigung erledigt |
| E-3 | Vision E2–E6 | **entschieden (2026-11-04):** parken | kein Roadmap-Schnitt für 1.x |
| E-4 | `planner`-Rolle aktivieren | Rolle in `.meta-config/project.yaml` aufnehmen / projektlokale Extension | Voraussetzung für plan-driven Wellen (§10) |

---

## 7. Verifikation

| Prüfung | Wo | Wie |
|---|---|---|
| Unit | lokal/CI | `python3 -m pytest -q` |
| Lint/Format | lokal/CI | `ruff check .` und `ruff format --check .` |
| Syntax | lokal/CI | `python3 -m compileall -q custom_components/health_o_mat` |
| HA-Config | Dev-Instanz | `/home/hermes/ha-test/bin/ha core check` |
| E2E | Compose 8124 | `tests_e2e/` gegen den gepinnten Stack, nie gegen die geteilte Instanz schreibend |
| Manuelle Abnahme | geteilte Instanz | nur lesend nach `bin/sync`: Entities, `friendly_name`, `entity_id` sichten |

**Nicht testbar in diesem Plan:** reale HACS-Nutzerpfade außerhalb des Compose-Update-Tests (die manuelle Betreiber-Prozedur steht in `docs/PLAN-AUDIT-2026-11-03.md` WP-E und ist bis zu ihrem Lauf unbelegt), Produktionsdatenmengen, HA-Versionen außerhalb der gepinnten E2E-Version, Sprachumschaltung auf der geteilten Instanz (instanzweiter Blast-Radius).

---

## 8. Traceability

| AK-ID | REQ/Issue | Test |
|---|---|---|
| W0-1 | REQ-HOM-132/133 | `grep` auf `docs/REQUIREMENTS.md`, Gegenprüfung `requirements` |
| W0-2 | REQ-HOM-007, REQ-HOM-116 | `grep -rn --exclude=PLAN-BACKLOG-2026-11-02.md "Restore ist weiterhin offen\|Restore weiterhin offen" docs/` → 0 |
| W0-3 | REQ-HOM-132/133 | `grep -rn "noch kein Release" docs/REQUIREMENTS.md` → 0 |
| W0-4 | Release-Stand 0.19.0 | `grep` auf 0.17.2 als aktuellen Stand in `docs/` und `README.md` |
| W0-5 | alle abgehakten AK | Stichprobe je AK gegen Datei/Test-Beleg |
| W1-1 | REQ-HOM-130, Spec §9 O-1 | `tests/test_entry_migration.py` (Issue-Erzeugung) |
| W1-2 | REQ-HOM-130 | `tests/test_entry_migration.py` (Issue-Auflösung) |
| W1-3 | REQ-HOM-130 | `tests/test_entry_migration.py` (Notification einmalig) |
| W1-4 | REQ-HOM-130 | `tests_e2e/` beziehungsweise HACS-Update-Report auf Compose |
| W2-1 | REQ-HOM-010 | `tests/test_text.py` (Entity pro Person, `unique_id`, `device_info`) |
| W2-2 | REQ-HOM-010 | `tests/test_text.py` (Transformation, kein Namens-Literal) |
| W2-3 | REQ-HOM-010 | `tests/test_text.py` (Feld nach Speichern leer) |
| W2-4 | REQ-HOM-010 | `tests/test_store.py` (History-Eintrag) |
| W2-5 | REQ-HOM-010 | `tests/test_import_backup.py` (CSV-Spalte) |
| W3-1 | REQ-HOM-006 AK 1 | `tests_e2e/` (Blueprint-Import) |
| W3-2 | REQ-HOM-006 | `tests_e2e/` (Negativtest Schema-Verstoß) |
| W3-3 | REQ-HOM-006/118 | `tests/test_blueprints.py`, README-Diff |
| W4-1 | REQ-HOM-127, REQ-HOM-132 | bestehende Service-/WS-Tests (Response-Keys unverändert) |
| W4-2 | REQ-HOM-127 | neue Tests auf `code` und `params` |
| W4-3 | REQ-HOM-127 | `tests/test_translations.py` (Parität de/en) |
| W4-4 | REQ-HOM-127 | Tests auf `errors`-Cap 20 |
| W4-5 | REQ-HOM-127 | bestehende Exception-Tests unverändert grün |
| W5-1 | B5 (HbA1c) | **geschlossen 2026-11-04:** bewusst nicht unterstützt; `unsupported_unit` bleibt das Verhalten, eigenes Issue nur bei Bedarf |
| W5-2 | B6/B7 | **geschlossen 2026-11-04:** gestrichen, kein Inhalt dokumentiert |
| W5-3 | B9 | **geschlossen 2026-11-04:** über den Audit-Nachtrag abgesetzt (Framework-Thema) |
| W5-4 | Vision E2–E6, Lab-Entity-Surface | **Vision geparkt** (kein 1.x-Schnitt); Lab-Surface-Entscheidung liegt bei WP-C (`docs/PLAN-AUDIT-2026-11-03.md`) |

---

## 9. Branch-Namen und DoD je Welle

| Welle | Branch | Commit-Typ |
|---|---|---|
| 0 | `chore/backlog-reconcile` | `docs:` |
| 1 | `feat/130-migration-repairs` | `feat:` |
| 2 | `feat/010-measurement-note` | `feat:` |
| 3 | `test/006-blueprint-e2e` | `test:` beziehungsweise `feat:` für den optionalen Blueprint |
| 4 | `feat/127-error-codes-i18n` | `feat:` beziehungsweise `refactor:` |

Conventional Commits, Englisch, max. 72 Zeichen, BOM-frei (Subject beginnt an Byte 0 mit dem Typ). Vor jedem Commit Secret-Scan der gestagten Änderungen; ein Befund blockiert den Commit. Push, Tag und Release ausschließlich durch `git`.

**DoD je Welle:** Akzeptanzkriterien erfüllt, Tests grün, `ruff` clean, betroffene Doku aktualisiert, Release nur nach erfüllter DoD und freigegebenem Release-Dreiklang.

---

## 10. Prozess-Hinweis: `planner`-Rolle nicht aktiv

- `agent-meta` stellt die Rolle `planner` („Umsetzungsplanung") bereit; `config/role-defaults.yaml:224` deklariert sie, `config/role-defaults.yaml:247-249` setzt `produces.plan.pipeline: feature-lifecycle`.
- Dieses Projekt aktiviert sie nicht: `.meta-config/project.yaml:19-37` listet 18 Rollen ohne `planner`.
- Das Orchestrator-Template verweist im Plan-driven Gate trotzdem auf `planner` (`.opencode/agents/orchestrator.md:129`, `:749`) — ein toter Verweis. Features mit mehr als zwei Dateien können das Gate dadurch nicht sauber erfüllen.
- Vorschlag (HITL): `planner` in `roles` aufnehmen, `python3 scripts/sync.py` ausführen und die Agenten-Registrierung neu starten. Alternative: projektlokaler Plan-Agent als Extension.
- Bis dahin: Task-Pläne für Welle 2 und Welle 4 durch `documenter` schreiben lassen und als `plan_ref` übergeben (Fallback, im Status-Payload dokumentieren).

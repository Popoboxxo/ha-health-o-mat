# Umsetzungsplan aus dem System-Audit (2026-11-03)

**Status:** WP-A umgesetzt (PR #84, Release 0.21.0 offen), WP-B umgesetzt (PR #82),
WP-C entschieden (D-1 = B4, reversibel), WP-D Trigger T-1…T-5 definiert,
WP-F abgeschlossen (reauth gehärtet, Auth wiederhergestellt) — **WP-E ist dokumentiert,
aber manuell offen** (keine HACS-Verifikation) · **Datum:** 2026-11-03,
Fortschreibung 2026-11-04 · **Basis:** `main` @ `184272e`; der Zahlenstand in §6 stammt
weiterhin aus der Messung @ `1d6f832`
**Quelle:** `docs/reviews/2026-11-03-system-audit.md` (+ Nachtrag 2026-11-03)
**Abgrenzung:** `docs/PLAN-BACKLOG-2026-11-02.md` (Wellen 0–4 umgesetzt; Welle 5
geschlossen)

> **Kein `plan_ref`.** Dieses Dokument ist ein Portfolio-Plan über mehrere Arbeitspakete
> und Releases. Es enthält bewusst **keine** `pipeline_stages`-Frontmatter und ist nicht
> als `payload.plan_ref` für die `feature-lifecycle`-Pipeline geeignet. Einzelne Features
> (WP-A, ggf. die B1-Umsetzung aus WP-C) brauchen je einen eigenen Task-Plan. Die Rolle
> `planner` ist in diesem Projekt nicht aktiv (`docs/PLAN-BACKLOG-2026-11-02.md:387-393`);
> Fallback für diese Task-Pläne ist `documenter`, der den Plan als `plan_ref` liefert.
>
> **Der Nachtrag 2026-11-03 liegt im Audit-Dokument vor** (Stand `1d6f832`) und ergänzt
> die Befunde, die der Haupt-Audit übersehen hat (u. a. die Klasse „blockierendes I/O in
> `async`-Pfaden"). Wo dieser Plan auf den Nachtrag verweist, ist der Befund zusätzlich
> mit dem heutigen Code-Stand belegt, nicht aus dem Nachtrag abgeschrieben.

**Zahlenstand (heute gemessen, `1d6f832`):** `python3 -m pytest -q --collect-only` →
**1754** Unit-Tests. E2E sind **65 Tests** — reproduzierbar mit laufendem Compose-Stack
(`HASS_BASE_URL=http://127.0.0.1:8124`, zweimal 65 passed / 0 skipped). Die Zahl **46**
entsteht nur, wenn `HASS_BASE_URL` auf die geteilte Instanz zeigt (Default `:8123`):
dann überspringt `tests_e2e/test_blueprints_e2e.py:83-92` per Modul-Guard
(`pytest.skip(allow_module_level=True)`) das ganze Blueprint-Modul (19 Tests), und die
Collection zeigt 46. Beide Zahlen sind korrekt — sie beschreiben zwei Messmodi, keinen
Widerspruch. Als E2E-Baseline für einen vollen Lauf gilt **65 (Compose-Stack)**; 46 ist
nur der Zählstand ohne erreichbaren Stack. Die im Audit genannten Funktionszahlen
(1497/39) sind überholt.

**Was neu ist gegenüber dem Backlog-Plan:**

| Thema | Backlog-Plan | Dieser Plan |
|---|---|---|
| REQ-HOM-127 | Welle 4, bereits geplant | **kein Duplikat:** WP-A übernimmt Welle 4 als Rahmen (inkl. des dort genannten additiven Transports `errors_detail`) und ergänzt nur Konzept-Gate, Datei-Anker und Release-Schnitt. **D-3 hat den Transport festgelegt:** HA-native `translation_*` mit `code == translation_key`; `errors_detail` ist verworfen (Konzept §8) |
| E2E-Lücken | nicht als Welle geführt | **neu:** WP-B (vier Szenarien, konkrete Testdateien) |
| Labor-Eingabe | §2.4 „Idee ohne REQ", Welle 5 Schritt 4 | **neu:** WP-C mit Zahlenkorrektur **vor** der Entscheidung, B1-vs-B4 als Nutzerentscheidung |
| Datei-Wachstum | nur als Beobachtung im Audit | **neu:** WP-D mit messbaren Triggern statt Refactor |
| HACS-Mechanik | Welle 1 Schritt 5 (nur simuliert belegt) | **neu:** WP-E mit realem HACS-Update auf isolierter Instanz — seit D-5 als manuelle Betreiber-Prozedur, nicht automatisiert |
| `bin/reauth`-Race | nicht enthalten (fremdes Repo) | **neu:** WP-F, Befund + Fix-Form, kein Code hier |

---

## 1. Befund-Triage

| ID | Befund (Audit/Nachtrag) | Stand heute | Beleg | WP |
|---|---|---|---|---|
| F-01 | Keine `TODO`/`FIXME`/`XXX` in `custom_components/**` | **erledigt** (Status) | Audit §1; `grep -rn "TODO\|FIXME\|XXX" custom_components/health_o_mat` → 0 | — |
| F-02 | `hacs.json` ohne `iot_class` | **erledigt** (Status) | Audit §1; `hacs.json` | — |
| F-03 | Testzahlen: Audit 1497 Unit / 39 E2E, Nachtrag 1754 Unit / 65 E2E | **erklärt (zwei Messmodi, kein Widerspruch)** | heute: 1754 Unit-Tests; E2E 65 mit laufendem Compose-Stack (`HASS_BASE_URL=…:8124`) bzw. 46 + übersprungenes Blueprint-Modul, wenn die Instanz-Adresse auf die geteilte Instanz zeigt (Modul-Guard, `tests_e2e/test_blueprints_e2e.py:83-92`) | — |
| F-04 | Entity-ID-Stabilität REQ-HOM-130/131 released | **erledigt** (Status) | Audit §1; 0.17.0–0.17.2, `docs/REQUIREMENTS.md:1766-1772` | — |
| F-05 | Bewusste `_attr_name`-Ausnahmen (M-8) dokumentiert | **erledigt** (Status) | Audit §1; `button.py:67,83` | — |
| F-06 | Kern-Dateien wachsen (`ws_api.py` 2406, `__init__.py` 1809, `store.py` 1582, `logic.py` 1422, `restore.py` 1266, `const.py` 658) | **entschieden** (Trigger T-1/T-2/T-5 definiert; kein Refactor) | `wc -l` @ `1d6f832` | WP-D |
| F-07 | Frontend-Einzeldateien (`card.js` 3362, `panel.js` 2362, `labs-card.js` 1791) | **entschieden** (Trigger T-4 definiert; kein Refactor) | `wc -l custom_components/health_o_mat/www/*.js` | WP-D |
| F-08 | Zwei-Klassen-Fehlerbehandlung = REQ-HOM-127 | **erledigt** (WP-A, PR #84; Release offen) | Umsetzung: `logic.ERROR_SPECS` (35 Codes), `errors.py`, 29 Service- + 32 WS-Stellen, 4 Relais, `exceptions`-Übersetzungen in `strings.json`/`de`/`en`; Beleg `tests/test_error_contract.py`, `tests/test_errors.py`; Doku `docs/SERVICE-RESPONSES.md` | WP-A |
| F-09 | Labor-Eingabe: Options-Doc mit veralteter Zahlenbasis (29 Marker, 9 Kategorien, 38 Entities), B1-vs-B4 unbeantwortet | **entschieden** (D-1 = B4, reversibel; Zahlenkorrektur Teil des WP) | `docs/superpowers/specs/2026-11-01-lab-entity-surface-options.md:20-54`; heute 41 Marker / 10 Kategorien / 51 Labor-Entities | WP-C |
| F-10 | HACS-Update-Test nur simuliert, HACS-Mechanik ungeprüft | **dokumentiert, manuell offen** (Prozedur in WP-E; keine HACS-Verifikation) | `docs/REQUIREMENTS.md:1830-1841`; Simulation 0.16.2→0.19.0, kein HACS im gepinnten E2E-Image | WP-E |
| F-11 | Spec §9 O-1 (Repair-Issue + Erfolgs-Notification) | **erledigt** (Audit-Aussage überholt) | PR #75; `__init__.py:235-236`, `tests/test_entry_migration.py` | — |
| F-12 | Vier E2E-Lücken (REQ-HOM-101 AK4, Button nach Reload, REQ-HOM-105 Diagnostics-Download, Update mit Alt-Bestand) | **erledigt** (WP-B, PR #82); zwei Paare waren dasselbe Szenario, REQ-HOM-104 ergänzt | `docs/REQUIREMENTS.md:429,456,463`; `tests_e2e/` | WP-B |
| F-13 | **Vom Audit übersehen:** blockierendes I/O in `async`-Pfaden | **erledigt** (Nachtrag) | PR #79; `importer.py:746`, `restore.py:1170`, `ws_api.py:2316`; Regressionstests in `tests/test_import_backup.py`, `tests/test_restore.py`, `tests/test_ws_api.py` | — |
| F-14 | **Nicht im Audit:** `bin/reauth`-Race in der geteilten Testinstanz | **erledigt** (extern; `reauth` gehärtet, Auth wiederhergestellt) | `/home/hermes/ha-test/bin/reauth:49`, `bin/ha:43,51` | WP-F |
| F-15 | Blueprint-Defekt (fehlende Personenbindung) | **erledigt** (nach Audit-Basis) | PR #77; `blueprints/automation/health_o_mat/*.yaml` | — |
| F-16 | Audit-Aussage „kein funktionaler Fehler gefunden" | **nicht belastbar** | Read-only-Statik; F-13 zeigt eine Klasse, die nur zur Laufzeit auffällt → als Scope-Aussage lesen, nicht als Beweis | — |
| F-17 | **Nachtrag:** `README.md:1300` nennt „25 E2E-Tests" und „1563 Unit-Tests" | **erledigt (in diesem Änderungssatz)** | `README.md:1300` ist in diesem Änderungssatz auf 1754 Unit / 65 E2E (Compose) korrigiert | — |

**Bereits geschlossen und deshalb nur Status:** F-01, F-02, F-04, F-05, F-11, F-13, F-15, F-17.
Sie bekommen kein eigenes Arbeitspaket; F-03 und F-16 sind Aussagen-Korrekturen, keine Arbeit.

---

## 2. Arbeitspakete

### WP-A — REQ-HOM-127: Fehlercode-/i18n-Vertrag — **umgesetzt, Release offen**

**Stand (2026-11-04):** Schritte 1–6 sind abgeschlossen — Konzept APPROVED
(`docs/superpowers/specs/2026-11-03-error-contract-design.md`), Task-Plan
(`docs/superpowers/plans/2026-11-03-error-contract.md`), Katalog mit 35 Codes,
29 Service- und 32 WS-Stellen migriert, 4 Relais, `exceptions`-Übersetzungen in
`strings.json`/`de`/`en`; Schritt 7 (Frontend lokalisiert über `translation_key`)
ist implementiert. Der E2E-Beleg (Task 7) läuft parallel und wird nach seinem
Ergebnis hier nachgetragen; `docs/SERVICE-RESPONSES.md` ist aktualisiert,
`docs/REQUIREMENTS.md` folgt über `requirements`. **Offen ist nur die
Release-Entscheidung** (0.21.0, MINOR + 💥, §4) — dieser Branch hebt keine
Version und erzeugt kein Release.

**Ziel:** Die bestehenden Services und WS-Kommandos liefern Fehler strukturiert als
`{code, params}` und lokalisieren die Meldungstexte de/en — **additiv**, ohne den
Response-Vertrag aus REQ-HOM-132 zu brechen. Die Labor-Batch-Pfade bleiben das
Referenzformat; sie werden nicht neu erfunden.

**Transport (entschieden, D-3):** Backlog (`docs/PLAN-BACKLOG-2026-11-02.md:223`)
und offene Punkte (`docs/PLAN-OPEN-ISSUES.md:445`) nannten `errors_detail` als
additiven Transport. **D-3 ist im Konzept entschieden:** Transport sind die
HA-nativen `translation_domain`/`translation_key`/`translation_placeholders`
(`code == translation_key`); der Labor-Batch bleibt `{code, params, message}`.
`errors_detail` ist damit **verworfen** (Konzept §8, Umsetzung `errors.py`).

**Scope/Dateien (Anker @ `1d6f832`)**

- `custom_components/health_o_mat/__init__.py` — alle fachlichen
  `ServiceValidationError`-Stellen: `:1002, 1006, 1013, 1095, 1123, 1126, 1152, 1157,
  1169, 1188, 1238, 1245, 1248, 1252, 1274, 1291, 1304, 1318, 1334, 1338, 1353, 1365,
  1369, 1373, 1398, 1406, 1417, 1437, 1447, 1524, 1551`; Transport-/Entry-Fehler
  bleiben unverändert.
- `custom_components/health_o_mat/ws_api.py` — `connection.send_error`-Stellen:
  `:802, 1280, 1303, 1313, 1338, 1351, 1375, 1388, 1398, 1407, 1417, 1468, 1484, 1534,
  1545, 1574, 1603, 1608, 1614, 1621, 1640, 1776, 1794, 1799, 1806, 1812, 1889`;
  Fachfehler-Envelope `_lab_error_result` (`:1646`) als Vorlage.
- `custom_components/health_o_mat/logic.py` — `lab_report_error` (`:1195`) zu einem
  allgemeinen Code-/Params-Builder verallgemeinern; `_LAB_ROW_ERROR_CODES` (`:1184`)
  und `ENTRY_TS_INVALID_MESSAGE` (`:160`) als Katalog prüfen.
- `strings.json` (1113 Zeilen, **keine** `exceptions`-Sektion vorhanden) sowie
  `translations/de.json` und `translations/en.json`.
- Frontend-Fehleranzeigen: `www/health-o-mat-card.js`, `www/health-o-mat-labs-card.js`,
  `www/health-o-mat-panel-*.js` — sie müssen den neuen Code lokalisieren bzw. den
  HA-übersetzten Text anzeigen.
- Tests: `tests/test_ws_api.py`, `tests/test_lab_services.py`,
  `tests/test_import_backup.py`, `tests/test_translations.py`, `tests/test_wave_a.py`,
  neu `tests/test_error_contract.py`; E2E `tests_e2e/test_i18n_e2e.py`.

**Agent(en):** `concept-development` (`ideation` ↔ `concept-reviewer`, maximal drei
Iterationen, APPROVED vor Implementierung) → Task-Plan (`documenter` als Fallback, weil
`planner` inaktiv ist) → `feature-lifecycle`: `senior-developer` (öffentlicher Vertrag,
viele Dateien), `tester`, `validator`, `documenter`, `git`.

**Schritte**

1. Konzept schreiben: Code-Katalog (eine Quelle), Transport pro Kanal
   (`ServiceValidationError` mit `translation_domain`/`translation_key`/
   `translation_placeholders` vs. WS-Envelope `{ok: false, error: {code, params,
   message}}`), Fallback-Verhalten bei unbekanntem Code, Abgrenzung Fach- vs.
   Transportfehler.
2. Im Konzept gegen die gepinnte HA-Version prüfen, welche Übersetzungsfelder
   `connection.send_error` und `ServiceValidationError` tatsächlich tragen
   (`docker-compose.e2e.yml:62` = HA `2026.9.1`, `hacs.json` = min. `2026.8.0`).
   Ergebnis ist eine Konzept-Entscheidung, keine Annahme.
3. `concept-reviewer` muss APPROVED liefern; bei Ablehnung maximal drei Runden, danach
   Eskalation an `principal-developer` über den Orchestrator.
4. Task-Plan mit `pipeline_stages` als `plan_ref` erstellen (Fallback `documenter`);
   darin jede der oben gelisteten Stellen einzeln einem Code zuordnen.
5. Implementieren: Codes + Params an allen fachlichen Stellen, `message` bleibt als
   nicht-leerer Fallback; Transportfehler (`invalid_format`, unbekannte Entry-ID,
   fehlende Berechtigung) behalten ihre bisherige Form.
6. Übersetzungen in `strings.json` (Master, englisch), `de.json` und `en.json`
   ergänzen; Parität sichern.
7. Frontend-Konsumenten anpassen: Code → lokalisierter Text, unbekannter Code →
   `message`-Fallback, kein roher Code in der UI.
8. Tests und Doku (`docs/SERVICE-RESPONSES.md`, `docs/REQUIREMENTS.md` via
   `requirements`).

**Akzeptanzkriterien**

- Jede fachliche Fehlerstelle liefert `code` und `params`; `code` ist stabil und
  snake_case.
- `message` bleibt als Fallback erhalten und ist nie leer.
- `strings.json`, `de.json`, `en.json` sind paritätisch; jeder verwendete Code hat
  einen de- und einen en-Text.
- REQ-HOM-132 bleibt unverändert: exakte Key-Mengen der fünf Verwaltungs-Services,
  `errors` ≤ 20, Fachfehler bleiben Exceptions (`docs/REQUIREMENTS.md:1946-1962`).
- Keine neuen Pflicht-Keys in bestehenden Antworten; bestehende Consumer laufen ohne
  Anpassung weiter (nur additive Felder).
- Der Transport-Key ist gemäß **D-3** festgelegt und in `docs/SERVICE-RESPONSES.md`
  dokumentiert: entweder `errors_detail` (so benannt in
  `docs/PLAN-BACKLOG-2026-11-02.md:223`) oder die begründete Abweichung davon.
- Kein deutscher Prosa-Fehlertext mehr im Produktionscode der migrierten Pfade.
- Ein Test enumeriert alle definierten Codes gegen die Übersetzungen (kein toter Code,
  keine fehlende Übersetzung).

**Tests**

- Unit: `tests/test_error_contract.py` (Tabelle Code → Params → de/en-Text,
  unbekannter Code, `message`-Fallback), `tests/test_ws_api.py` (Envelope-Form,
  Transportfehler unverändert), `tests/test_lab_services.py` und
  `tests/test_import_backup.py` (REQ-HOM-132-Regression), `tests/test_translations.py`
  (Parität), `tests/test_wave_a.py` (Exception-Verhalten).
- E2E: `tests_e2e/test_i18n_e2e.py` um einen repräsentativen Fachfehler erweitern
  (z. B. ungültige Menge bei `add_drink`) und de/en-Anzeige prüfen.
- `python3 -m pytest -q`, `ruff check .`, `ruff format --check .` grün.

**Risiken**

- Vertragsbruch für Panel, Card und Automationen → nur additive Felder, bestehende
  Keys und Exception-Klassen unverändert.
- HA-Versionsabhängige Übersetzungsfelder → im Konzept gegen `2026.9.1` prüfen, nicht
  raten.
- i18n-Parität driftet → Paritätstest plus Code-Enumerationstest.
- Rolle `planner` fehlt → Fallback `documenter`, im Status-Payload dokumentieren.

**DoD:** Konzept APPROVED, Task-Plan als `plan_ref`, Tests grün (laut
`tester`-Lauf: 1865+ Unit-Tests, `ruff` clean), Akzeptanzkriterien unten erfüllt;
`docs/SERVICE-RESPONSES.md` aktualisiert. **Offen:** Abhaken der
REQ-HOM-127-AKs in `docs/REQUIREMENTS.md` (über `requirements`) und die
**Release-Entscheidung 0.21.0 mit 💥-Hinweis** (§4).

---

### WP-B — E2E-Lücken schließen

**Ziel:** Die vier offenen E2E-Akzeptanzkriterien sind auf dem isolierten Compose-Stack
gegen die gepinnte HA-Version belegt. Keine Produktionscode-Änderung, außer ein Test
deckt einen echten Defekt auf — dann Fix plus Regressionstest im selben Branch.

**Scope/Dateien**

- Neu `tests_e2e/test_config_migration_e2e.py` — B-1 und B-2.
- Neu `tests_e2e/test_diagnostics_e2e.py` — B-3.
- Neu `tests_e2e/test_input_persistence_e2e.py` — B-4.
- `tests_e2e/e2e_helpers.py` — Helfer für Entry-Reload und kontrollierten Neustart.
- `scripts/e2e_bootstrap.py` — Fixture für einen v1-Alt-Entry (nur Compose-Volume).
- `docs/REQUIREMENTS.md` — AK-Belege (`:429`, `:456`, `:463`) via `requirements`.
- `README.md:1300` — **erledigt:** F-17 ist in diesem Änderungssatz auf 1754 Unit /
  65 E2E (Compose) korrigiert; nach WP-B den Stand erneut prüfen.

**Die vier Lücken**

| ID | Lücke | Szenario |
|---|---|---|
| B-1 | REQ-HOM-101 AK4, Teil 1: Update mit Alt-Bestand | v1-Entry (Quick-Drinks in `data`, `options` leer) im Compose-Volume anlegen, HA starten, Migration v1→v3 prüfen: `options` gefüllt, `data` bereinigt, keine Datenverluste |
| B-2 | REQ-HOM-101 AK4, Teil 2: Button-Änderung nach Reload | Quick-Drink-Label/ml über den Options-Flow ändern, Entry reloaden, Button drücken, Store-Wert und Entity-Name prüfen |
| B-3 | REQ-HOM-105: Diagnostics-Download | Admin `GET /api/diagnostics/config_entry/<entry_id>` → 200, valides JSON, nur Versionen/Counts/Entity-IDs, **keine** Gesundheitswerte, kein Personenname, keine Rohzeitstempel; Non-Admin-Token wird abgewiesen |
| B-4 | REQ-HOM-104: halbfüllte Eingabe überlebt Neustart | Number-Entities (`sys`/`dia`/`pulse`) setzen, Instanz neu starten, Werte aus Store und Entity-States prüfen; Speichern leert Store und Entities |

> **Korrektur zur Audit-Liste:** Audit §3.5 nennt vier Punkte, davon sind
> „REQ-HOM-101 AK 4" und „E2E für Update mit Alt-Bestand + Button-Änderung nach Reload"
> dasselbe Szenario (B-1 + B-2). REQ-HOM-105 und „E2E für Diagnostics-Download" sind
> ebenfalls dasselbe Szenario (B-3). Der vierte echte Gap ist REQ-HOM-104 (B-4), den
> weder Audit noch Nachtrag nennen; er steht offen in `docs/REQUIREMENTS.md:456`.

**Agent(en):** `tester` (Szenarien), `documenter` (Belege), `git`.

**Schritte**

1. Fixture für den v1-Alt-Entry bauen: `.storage/core.config_entries` im
   Compose-Volume vor dem Start auf Version 1 zurückschreiben, `quick_drinks` aus
   `data` nach `options`-frei; nach dem Test Reset auf den Ausgangszustand.
2. B-1/B-2 als eine Szenariokette implementieren (Migration → Options-Flow →
   Reload → Button-Press → Store-Assertion).
3. Diagnostics-E2E: Admin- und Non-Admin-Pfad, Redaction-Assertions aus
   `tests/test_diagnostics.py:101-711` spiegeln.
4. Neustart-Helfer in `e2e_helpers.py`: `docker restart` + Polling auf `/api/` und
   Config-Entry-Ready, mit Timeout und klarer Fehlermeldung.
5. Bei Defekt: Repro-Test zuerst, dann Fix, dann Regressionstest (Vorbild:
   `async_set_value`-Defekt bei REQ-HOM-010, Blueprint-Personenbindung).
6. Belege in `docs/REQUIREMENTS.md` und in `docs/E2E-REPORT-WP-B.md` eintragen.
   Pfadregel für Belegdokumente: `docs/E2E-REPORT-<WP>-<THEMA>.md`, datumsfrei und
   ohne Platzhalter (`XX`, `*`); Datum und Commit stehen im Dokumentkopf.

**Akzeptanzkriterien**

- Alle vier Szenarien sind auf Compose (nicht auf der geteilten Instanz) grün.
- Jede der vier AK-Zeilen in `docs/REQUIREMENTS.md` ist mit Testpfad abgehakt.
- Kein Schreibzugriff auf `/home/hermes/ha-test`; Reset des Compose-Volumes ist
  idempotent.
- Wird ein Defekt gefunden, existiert ein fehlschlagender Test vor dem Fix.
- `README.md:1300` ist nach dem Lauf gegen den neuen E2E-Stand erneut geprüft
  (F-17 selbst ist in diesem Änderungssatz erledigt).

**Tests:** `tests_e2e/` gesamt (heute 65 auf dem Compose-Stack; 46 ist nur der
Zählstand ohne erreichbaren Stack) plus vier neue Szenarien; Unit-Suite unverändert grün.

**Risiken**

- Neustart-Timing ist flaky → Polling mit Timeout, ein Retry, keine festen `sleep`s.
- Storage-Manipulation im Compose-Volume kann den Stack verstimmen → Fixture sichert
  die Originaldatei und stellt sie im `finally` wieder her.
- E2E-Image ist read-only für die Integration → kein HACS in WP-B (das ist WP-E).

**DoD:** E2E-Lauf dokumentiert, AKs abgehakt, Release 0.20.0 (Testbeleg, kein eigener
Versionsgrund).

---

### WP-C — Labor-Eingabe: Zahlenbasis + Entscheidung

**Ziel:** Die Options-Doc rechnet wieder mit dem echten Katalog, danach ist die
B1-vs-B4-Frage entscheidbar. **Keine Umsetzung** von B1 in diesem Plan.

**Scope/Dateien**

- `docs/superpowers/specs/2026-11-01-lab-entity-surface-options.md` — §1.1
  Entity-Tabelle (`:20-35`), §1.2 LTS (`:37-46`), §1.3 (`:47-56`), alle
  Options-/Empfehlungstabellen mit Entity-Zahlen (A1–A9, B1–B5, C1–C4, R1–R3).
- `docs/REQUIREMENTS.md` nur über `requirements`, falls B1 eine neue Anforderung
  bekommt (REQ-ID wird dort vergeben und hier bewusst nicht vorweggenommen).
- `README.md` nur, falls B4 gewählt wird und die Service-/WS-Pfade dort fehlen.

**Zahlenkorrektur (heute aus dem Code belegt)**

| Größe | Doc (Stand 0.16.x) | Heute |
|---|---:|---:|
| Labor-Marker (`LAB_MARKERS`, `const.py:196`) | 29 | **41** |
| Warn-Kategorien ohne `other` (`LAB_CATEGORIES`, `const.py:175`) | 9 | **10** (neu: `metabolism`) |
| Labor-Entities je Person (41 Sensoren + 10 Binaries) | 38 | **51** |
| LTS-Streams je Person | 29 | **41** |
| Gesamt-Entities je Person, Defaults | 82 | **95** (0.19.0) bzw. **96** (heute, inkl. `measurement_note`) |

Die 95 deckt sich mit dem Simulationsbeleg in `docs/REQUIREMENTS.md:1832-1835`
(„95 Entities danach, +13 gegenüber 0.19.0"); die 96 entsteht durch die in Welle 2
zusätzlich gemergte Text-Entity `measurement_note`. Vor der Entscheidung ist die Zahl
per `python3`-Auszählung aus `const.py` erneut zu bestätigen, nicht aus diesem Plan
abzuschreiben.

**Agent(en):** `documenter` (Zahlen + Doc), `requirements` (Decision Record, ggf. neue
REQ), Nutzer via `main_chat` (Entscheidung B1/B4).

**Schritte**

1. Zahlen aus `const.py` und den Plattform-Setups (`sensor.py:31-59`,
   `binary_sensor.py:27-41`, `text.py:19-20`) neu erheben und die Tabelle in §1.1
   ersetzen.
2. Alle abgeleiteten Stellen im Dokument nachrechnen: Entity-Deltas je Option,
   LTS-Aussagen, „82"/„38"/„29"/„9" ersetzen (grep über das Dokument).
3. Die Trade-off-Texte **nicht** neu schreiben — sie bleiben strukturell gültig
   (Audit §3.2); nur die Zahlen und die daraus abgeleiteten Deltas ändern sich.
4. Entscheidungsvorlage an den Nutzer: B1 (vier neue Eingabe-Entities nach BP-Vorbild)
   vs. B4 (Status quo, nur Doku). Dabei explizit nennen: **B1 erhöht die Entity-Zahl um
   vier pro Person**, es senkt sie nicht; der Entity-Druck aus F-06/F-09 wird durch B1
   nicht gelöst, sondern um vier verstärkt. Die Empfehlung R1 im Dokument kombiniert B1
   mit A2/A7 — genau diese Kombination ist die eigentliche Entscheidung, nicht B1 allein.
5. Entscheidung mit Datum und Begründung im Dokumentkopf festhalten.
6. Bei B1: `requirements` legt die Anforderung an, danach eigener Task-Plan
   (`documenter`-Fallback) und `feature-lifecycle` — nicht Teil dieses Plans.
   Bei B4: Dokument schließen, Service-/WS-Eingabewege in der README als offiziellen
   Weg benennen, kein Code.

**Akzeptanzkriterien**

- Die Options-Doc nennt 41 Marker, 10 Kategorien, 51 Labor-Entities und 41 LTS-Streams;
  `grep` auf 29/38/82 im Fließtext liefert nur noch historische, ausdrücklich markierte
  Stellen.
- Jede Optionsbewertung, die eine Entity-Zahl nennt, ist auf die neue Basis gerechnet.
- B1-vs-B4 ist mit Datum, Begründung und Entscheider dokumentiert.
- Bei B1 existiert eine REQ-ID von `requirements` und ein separater Task-Plan; bei B4
  existiert kein neuer Code.

**Tests:** Doku-Grep und Gegenrechnung; keine Code-Tests. Bei einer späteren
B1-Umsetzung: Unit-Tests für die vier Entities (unique_id, device_info,
translation_key, Persistenz) plus E2E.

**Risiken**

- Entscheidung auf alter Zahlenbasis → Schritt 1 vor Schritt 4, hart.
- B1 wird als Entity-Reduktion missverstanden → Trade-off in der Vorlage explizit.
- Doc und Code driften erneut → die Zahlenkorrektur nennt ihre Quelle
  (`const.py`-Auszählung), damit die nächste Runde prüfbar bleibt.

**DoD:** Zahlen aktualisiert, Entscheidung dokumentiert, kein Release, kein Code.

**Blockiert:** ab Schritt 4 durch die Nutzerentscheidung (`main_chat`).

---

### WP-D — Datei-Wachstum: Trigger statt Refactor

**Ziel:** Das Wachstum bekommt messbare Auslöser. **Heute wird nicht refactored.**

**Scope/Dateien:** dieses Dokument (Trigger + Baseline) und die Release-Checkliste;
kein Produktionscode.

**Baseline @ `1d6f832`**

| Datei | Zeilen |
|---|---:|
| `ws_api.py` | 2406 |
| `__init__.py` | 1809 |
| `store.py` | 1582 |
| `logic.py` | 1422 |
| `restore.py` | 1266 |
| `const.py` | 658 |
| `www/health-o-mat-card.js` | 3362 |
| `www/health-o-mat-panel.js` | 2362 |
| `www/health-o-mat-panel-views.js` | 1574 |
| `www/health-o-mat-panel-base.js` | 1568 |
| `www/health-o-mat-panel-admin.js` | 1081 |
| `www/health-o-mat-labs-card.js` | 1791 |

**Trigger (wer zuerst greift, löst aus)**

| ID | Messbarer Auslöser | Was dann passiert |
|---|---|---|
| T-1 | Bei einem Release-Schnitt: `ws_api.py` ≥ 3000 **oder** `__init__.py`/`store.py`/`logic.py`/`restore.py` ≥ 2500 Zeilen | Vor der nächsten Feature-Welle ein verhaltensneutraler Domänen-Split (`services/<domain>.py`, `storage/<domain>.py`, `logic/<domain>.py`); öffentliche Verträge, `unique_id`s und Store-Schema unverändert; volle Unit-/E2E-Suite als Netz |
| T-2 | Eine **fünfte** Datendomäne (nach Trinken, Blutdruck, Wohlbefinden, Labor) wird geplant | Split **vor** der Feature-Arbeit; die neue Domäne darf nicht wieder > 200 Zeilen in jede der vier Kerndateien schreiben |
| T-3 | `const.py` ≥ 1200 Zeilen **oder** Labor-Marker ≥ 80 | `LAB_MARKERS`/`LAB_CATEGORIES` in ein reines Datenmodul `lab_catalog.py` auslagern; Keys und Anzeigenamen bleiben zeichenidentisch |
| T-4 | `www/health-o-mat-card.js` ≥ 4000 Zeilen **oder** ein dritter Konsument von `panel-base.js` | Split in ES-Module (kein Bundler); Importgraph muss ohne Build-Schritt von HA ladbar bleiben |
| T-5 | Zwei aufeinanderfolgende Releases fügen derselben Kerndatei je > 200 Zeilen hinzu | Refactor im nächsten Release **einplanen** (nicht automatisch starten); Entscheidung im Release-Review dokumentieren |

**Agent(en):** `orchestrator` (Prüfung im Release-Review), `documenter` (Baseline und
Entscheidung), bei ausgelöstem Refactor `senior-developer` + `tester`.

**Schritte**

1. Baseline in diesem Dokument führen (erledigt, Tabelle oben).
2. Bei jedem Release-Schnitt `wc -l` über `custom_components/health_o_mat/*.py` und
   `www/*.js` laufen lassen und gegen die Trigger prüfen; Ergebnis im Release-Review
   notieren.
3. Bei Auslösung: eigenes Refactor-Vorhaben mit Task-Plan, **vor** der nächsten
   Feature-Welle; keine Feature- und Refactor-Änderung im selben Commit.
4. Nach einem Refactor: Baseline neu setzen und die Trigger-Schwellen im selben
   Dokument fortschreiben.

**Akzeptanzkriterien**

- Die fünf Trigger sind messbar formuliert (Datei + Zahl + Konsequenz).
- Die Baseline ist mit Datum und Commit festgehalten.
- Jeder Release-Review enthält die Messung und die Aussage „kein Trigger" oder den
  Verweis auf das Refactor-Vorhaben.

**Tests:** keine jetzt; nach einem ausgelösten Refactor müssen 1754 Unit-Tests und die
E2E-Suite unverändert grün sein (Verhaltensneutralität).

**Risiken**

- Refactor ohne Auslöser erzeugt Churn → Trigger sind die einzige Legitimation.
- Trigger wird im Release-Stress übersehen → Messung ist ein Checklisten-Punkt, kein
  Ermessenspunkt.
- Schwellen sind zu niedrig/hoch → nach dem ersten ausgelösten Fall kalibrieren, nicht
  vorher.

**DoD:** Trigger + Baseline stehen; kein Code, kein Release.

---

### WP-E — HACS-Update-Mechanik — **manuell offen (dokumentiert)**

**Ziel:** Der echte HACS-Update-Pfad (Vorgängerversion → aktuelle Version über HACS
selbst) ist einmal auf einer **isolierten** Instanz belegt — nicht auf der geteilten
Instanz und nicht per Bind-Mount-Kopie.

**Stand (2026-11-04):** Die Mechanik ist auf dem aktuellen Stack **nicht automatisierbar**
und wird deshalb als manuelle Betreiber-Prozedur dokumentiert. Belegt ist nur der
**Upgrade-Pfad selbst** (Simulation 0.16.2 → 0.19.0 in Welle 1: Entry v2 → v3,
`unique_id`s erhalten, Daten unverändert, eine Notification, idempotenter Neustart).
**Nicht belegt ist die HACS-Mechanik** — dieser Abschnitt behauptet keine
HACS-Verifikation.

**Entscheidung D-5 — entschieden (2026-11-04):** kein neuer Container. Begründung: HACS
fehlt im gepinnten E2E-Image, die Integration liegt dort als Read-only-Bind-Mount, und
die HACS-Einrichtung verlangt einen interaktiven GitHub-Device-Flow. Ein eigener Container
würde die Mechanik nicht ohne denselben interaktiven Schritt belegen. Stattdessen gilt die
Prozedur unten, ausgeführt von einem Betreiber auf einer von ihm bereitgestellten
isolierten Instanz.

**Scope/Dateien:** Belegdokument `docs/E2E-REPORT-WP-E-HACS-UPDATE.md` (Pfadregel wie in
WP-B: `docs/E2E-REPORT-<WP>-<THEMA>.md`, datumsfrei, keine Platzhalter — Datum und Commit
stehen im Dokumentkopf); `docs/REQUIREMENTS.md` (REQ-HOM-130-Rest-AK, `:1830-1841`);
keine Produktionscode-Änderung, kein Container in diesem Repo.

**Voraussetzungen (durch den Betreiber)**

- Eine isolierte HA-Instanz, die **nicht** `127.0.0.1:8123` und **nicht** der
  Compose-E2E-Stack mit Read-only-Bind-Mount ist; HA-Version `2026.9.1` wie im E2E-Stack
  (`docker-compose.e2e.yml:62`).
- HACS in dieser Instanz installiert (Release entpacken, Neustart, Integration
  einrichten); die HACS-Version wird im Beleg festgehalten.
- Ein veröffentlichtes `v0.16.2` als Ausgangsversion und das aktuelle Release als Ziel.

**Schritte (manuelle Prozedur, 8 Schritte)**

1. Isolierte HA-Instanz provisionieren und HACS installieren; HA- und HACS-Version
   notieren.
2. In HACS das Custom-Repository `Popoboxxo/ha-health-o-mat` hinzufügen.
3. Über die HACS-UI `v0.16.2` installieren und HA neu starten.
4. Eine Person anlegen (ein Config-Entry) und Bestand erzeugen: eigene Quick-Drinks,
   Blutdruck-Messung, Wohlbefinden, Laborwert inkl. Custom-Marker.
5. Snapshot vor dem Update: Entry-Version, `unique_id`s, Entity-Anzahl, Stichprobenwerte,
   `/api/states`, `.storage/health_o_mat*`.
6. In HACS den Update-Check auslösen und **über die HACS-UI** auf das aktuelle Release
   aktualisieren; HA neu starten.
7. Prüfpunkte abarbeiten: `manifest.version` entspricht dem Release, Entry lädt, kein
   `Migration handler not found`, Entry-Version korrekt migriert, `unique_id`s unverändert,
   Quick-Drink-Entity-IDs stabil, Datenwerte unverändert, höchstens eine
   Migrations-Notification, kein Repair-Issue; zweiter Neustart idempotent.
8. Beleg in `docs/E2E-REPORT-WP-E-HACS-UPDATE.md` schreiben: HA-/HACS-Version,
   Von-/Nach-Version, Entry-Versionen, Entity-Zahlen vorher/nachher,
   Storage-Zusammenfassung, relevante Logzeilen (ohne Tokens), Ergebnis je Prüfpunkt.

**Abschlusskriterium:** WP-E gilt als **geschlossen**, wenn ein Betreiber den Lauf nach
dieser Prozedur ausgeführt und das Belegdokument committed hat und **alle** Prüfpunkte aus
Schritt 7 grün sind. Bis dahin bleibt WP-E **manuell offen**; die Existenz dieser Prozedur
ist kein Beleg. Schlägt ein Prüfpunkt fehl: Issue mit Repro, Fix, PATCH-Release, Lauf
wiederholen — der Punkt bleibt bis zum grünen Lauf offen.

**Akzeptanzkriterien**

- Das Update wurde über die HACS-UI ausgeführt, nicht durch Kopieren von Dateien und
  nicht durch einen bloßen Tag.
- Der Beleg enthält alle Prüfpunkte aus Schritt 7 mit Ergebnis.
- Kein Datenverlust, keine verwaisten oder duplizierten Entities.
- REQ-HOM-130-Rest-AK ist mit Belegpfad abgehakt.
- Bei einem Fehlschlag: Issue mit Repro, Fix, Patch-Release, Lauf wiederholen — der AK
  bleibt bis zum grünen Lauf offen.

**Tests:** manueller HACS-Update-Lauf plus Verifikation über HA-API/Storage; kein
pytest-Szenario (HACS ist nicht im E2E-Image, `docs/REQUIREMENTS.md:1836-1840`).

**Risiken**

- GitHub-Rate-Limit/Device-Flow → HACS-Version und Fehlerbild dokumentieren; Lauf
  wiederholen, nicht auf die geteilte Instanz ausweichen.
- HACS-Version driftet → Version im Beleg pinnen; HA-Version bleibt `2026.9.1`.
- Versehentlicher Schreibzugriff auf die geteilte Instanz → Instanz-URL vor jedem
  Schritt prüfen, kein `bin/sync` gegen `8123`.

**DoD:** Belegdokument committed, REQUIREMENTS-AK abgehakt, kein Release durch dieses
WP selbst. **Bis dahin: WP-E manuell offen.**

**Abhängigkeit:** braucht ein veröffentlichtes Ziel-Release (aktuell 0.20.0/0.21.0) und
einen Betreiber, der den Lauf ausführt. Der Lauf nach 0.21.0 entfällt nicht: WP-A ändert
die Fehlertexte, deshalb ist er Teil der 0.21.0-Abnahme, sobald 0.21.0 veröffentlicht ist.

---

### WP-F — `bin/reauth`-Race (anderes Repo)

**Ziel:** Den Defekt exakt festhalten und die Fix-Form vorgeben. **Kein Code in diesem
Repository.**

**Befund (belegt in `/home/hermes/ha-test/bin/`)**

- `bin/reauth:49` schreibt `.ha-state/token.json` **in place** über
  `json.dump(tok, open(path, "w"))`; `chmod 600` folgt erst danach (`:52`). Der
  Schreibvorgang ist nicht atomar: Leser sehen ein gekürztes/leeres JSON, und zwischen
  `open("w")` und `chmod` ist die Datei kurz mit weiterreichenden Rechten sichtbar.
- `bin/reauth` nimmt **nicht** `$STATE_DIR/refresh.lock`. `bin/ha:51` serialisiert
  Refresh-Aufrufe genau über diesen Lock und schreibt ebenfalls in place
  (`bin/ha:43`). `bin/provision:61` hat dasselbe Schreibmuster.
- Interleaving-Folgen: (a) `bin/ha` liest während des Schreibens ein kaputtes JSON;
  (b) ein Refresh, der mit dem alten Refresh-Token begann, landet **nach** `reauth` und
  überschreibt das frisch rotierte Token → später `invalid_request`, erneutes `reauth`
  nötig; (c) ein zweiter `reauth`-Lauf kann das Ergebnis des ersten überschreiben.

**Fix-Form (Vorgabe, keine Umsetzung hier)**

1. Gemeinsamen Helfer `write_token_atomic` in den drei Skripten verwenden:
   Lock `refresh.lock` (gleiche `mkdir`-Schleife inkl. Stale-Übernahme wie
   `bin/ha:51-85`) nehmen, Temp-Datei im selben Verzeichnis mit Modus `600` schreiben,
   dann `os.replace` auf `token.json`.
2. `bin/reauth` liest das Token **unter dem Lock** neu ein, bevor es schreibt, damit ein
   zwischenzeitlich erfolgter Refresh nicht überschrieben wird.
3. `bin/ha`-Refresh benutzt denselben Helfer; der Lock bleibt um den gesamten
   Read-Modify-Write-Zyklus.
4. Verifikation: Stresslauf — `bin/ha GET /api/` in einer Schleife parallel zu
   `bin/reauth`; nach jedem Lauf `python3 -m json.tool .ha-state/token.json` und
   `bin/ha GET /api/` grün; 50 Iterationen ohne `invalid_request`, ohne
   Parse-Fehler, ohne Rechte-Abweichung.

**Agent(en):** `devops-engineer` bzw. Betreiber der Testinstanz; Koordination über den
`orchestrator`. Dieses Repo liefert nur den Befund.

**Schritte**

1. Befund gegen die aktuellen Skripte erneut prüfen (Zeilen können sich verschieben).
2. Issue/Notiz im Tooling-Repo der Testinstanz anlegen (falls nicht versioniert: im
   README der Instanz dokumentieren).
3. Fix nach obiger Form umsetzen und Stresslauf fahren.
4. Ergebnis (Commit/PR-Link oder README-Abschnitt) im Audit-Nachtrag referenzieren.

**Akzeptanzkriterien**

- Der Defekt ist mit Datei/Zeile und Interleaving-Folge dokumentiert.
- Der Fix verwendet Lock + atomisches Replace + Modus 600.
- Der Stresslauf ist dokumentiert und grün.
- Kein Commit in `ha-health-o-mat`.

**Tests:** Shell-Stresslauf (50 Iterationen) plus `json.tool` nach jedem Lauf; kein
pytest.

**Risiken**

- Fix im falschen Repo → ausdrücklich extern; dieses Repo bleibt unberührt.
- Lock-Übernahme weicht von `bin/ha` ab → dieselbe Implementierung wiederverwenden,
  nicht nachbauen.
- Stresslauf trifft die geteilte Instanz nur lesend (`GET /api/`) → kein Reset, keine
  schreibenden Aufrufe.

**DoD:** externer Fix + Beleg, Verweis im Audit-Nachtrag; kein Release hier.

---

## 3. Reihenfolge und Abhängigkeiten

```
WP-C Schritt 1-3 (Zahlen) ──► Nutzerentscheidung ──► ggf. B1-Plan (eigenes Feature)
WP-B ──► Release 0.20.0 ──► WP-E (0.19.0 → 0.20.0)
                              │
WP-A Konzept ──► Task-Plan ──► Implementierung ──► Release 0.21.0 ──► WP-E (0.20.0 → 0.21.0)
WP-D: parallel, nur Messung im Release-Review
WP-F: unabhängig, extern
```

- **WP-B vor WP-A:** Die E2E-Lücken sind das Sicherheitsnetz für den Vertragsummbau;
  WP-A ändert dieselben Pfade, die danach in der E2E-Suite hängen. Außerdem berühren
  beide `tests_e2e/` — erst B, dann A vermeidet Konflikte.
- **WP-C ist unabhängig, aber nutzerblockiert.** Die Zahlenkorrektur (Schritte 1–3)
  kann sofort laufen; die Entscheidung wartet auf `main_chat`.
- **WP-E nach dem jeweiligen Release:** Der reale Update-Pfad soll einmal belegt sein,
  bevor die nächste verhaltensändernde Version ausgeliefert wird (Audit §4.4). Nach D-5
  ist das kein Automatikschritt mehr: der Lauf erfolgt manuell durch einen Betreiber und
  ist für 0.21.0 Teil der Abnahme — bis dahin bleibt WP-E offen.
- **WP-D blockiert nichts.** Es ist eine Release-Review-Messung; ein ausgelöster
  Refactor würde die Reihenfolge brechen und vor der nächsten Feature-Welle laufen.
- **WP-F blockiert nichts in diesem Repo**, wohl aber die Reproduzierbarkeit von
  E2E-Läufen auf der geteilten Instanz.

---

## 4. Release-Schnitt

| Release | Inhalt | Typ | Begründung |
|---|---|---|---|
| **0.20.0** | Backlog-Wellen 2/3 (bereits gemergt: `measurement_note`, Blueprints) + WP-B-Belege | MINOR | Die Features sind ohne Versionsbump auf `main`; WP-B ändert keinen Produktionscode |
| **0.21.0** | WP-A (Fehlercode-/i18n-Vertrag) | MINOR + 💥 | Verhaltensänderung: Fehlertexte und -codes ändern sich, Antwort-Keys bleiben; 💥-Hinweis mit Migrationshinweis für Panel-/Card-Konsumenten |
| **0.22.0** | nur falls B1 entschieden wird (WP-C) | MINOR | eigenes Feature, eigener Plan; hier nicht terminiert |
| **kein Release** | WP-C (Doku/Entscheidung), WP-D, WP-E, WP-F | — | keine Produktionsänderung in diesem Repo |
| **PATCH nach Bedarf** | Defekt aus WP-B/WP-E | PATCH | nur wenn ein Beleg einen echten Fehler zeigt; Fix + Regressionstest |

**Abweichung vom Backlog-Plan:** `docs/PLAN-BACKLOG-2026-11-02.md:285-292` plante
0.19.1 für Wellen 0/1 und 0.20.0 für Wellen 2/3. Welle 0 ist Doku, Welle 1 ist
gemergt, aber nicht released; da 0.20.0 ohnehin MINOR-Inhalt trägt, entfällt 0.19.1 und
0.20.0 bündelt beides. Diese Abweichung ist eine Entscheidung (§5, D-2), keine stille
Änderung.

**Release-Dreiklang:** Commit → Tag → echtes GitHub-Release mit Changelog; `v` nur im
Tag, `manifest.version` zeichenidentisch ohne `v`; Tag/Release unveränderlich;
HACS-Update-Test **nach** dem Release. Für 0.21.0 enthält die Release-Notes-Struktur
Summary, ✨ New features, 💥 Breaking/Verhaltensänderung mit Hinweis für
Automationen/Panel und den Full-Changelog-Link.

---

## 5. Offene Entscheidungen

| ID | Entscheidung | Optionen | Entscheider | Wirkung/Blockade |
|---|---|---|---|---|
| D-1 | B1 (vier Eingabe-Entities) vs. B4 (Status quo + Doku) | **entschieden (2026-11-04): B4** (Status quo + Doku), reversibel | Nutzer (`main_chat`) | erledigt; ein B1-Feature bräuchte einen neuen Beschluss |
| D-2 | 0.19.1 streichen und in 0.20.0 bündeln | bündeln / separates 0.19.1 | `orchestrator` mit Nutzer | bestimmt den Release-Schnitt in §4 |
| D-3 | Fehler-Transport: HA-native Übersetzungsfelder vs. eigenes Envelope | **entschieden (2026-11-03, Konzept §8):** HA-native `translation_*` (`code == translation_key`), Batch bleibt `{code, params, message}` | `concept-reviewer` im WP-A-Konzept | erledigt; blockiert nicht mehr |
| D-4 | `planner`-Rolle aktivieren | aktivieren / Fallback `documenter` beibehalten | Nutzer (Backlog §10, E-4) | beeinflusst nur den Prozess, nicht den Inhalt |
| D-5 | HACS-Testinstanz provisionieren | **entschieden (2026-11-04):** kein neuer Container; manuelle Betreiber-Prozedur statt Automatisierung | `orchestrator` | erledigt; WP-E bleibt manuell offen, blockiert kein Release |
| D-6 | Wo der `bin/reauth`-Fix landet | Tooling-Repo / direkt auf der Instanz | Betreiber der Testinstanz | blockiert nur WP-F |

---

## 6. Verifikation

| Prüfung | Wo | Wie |
|---|---|---|
| Unit | lokal/CI | `python3 -m pytest -q` — Baseline 1754 collected (`1d6f832`); nach WP-A auf dem Feature-Branch 1865+ (`tester`-Lauf) |
| Lint/Format | lokal/CI | `ruff check .` und `ruff format --check .` |
| Syntax | lokal/CI | `python3 -m compileall -q custom_components/health_o_mat` |
| HA-Config | Dev-Instanz | `/home/hermes/ha-test/bin/ha core check` (nur lesend) |
| E2E | Compose, gepinnt `2026.9.1` | `pytest -q tests_e2e` — Baseline 65 (Compose-Stack, `HASS_BASE_URL=…:8124`); 46 nur ohne erreichbaren Stack (Blueprint-Modul-Guard); nie schreibend gegen `8123` |
| HACS-Update | isolierte Instanz (Betreiber) | WP-E-Prozedur (8 Schritte); Belegdokument erst nach dem manuellen Lauf — bis dahin WP-E offen |
| Doku-Wahrheit | lokal | gezielte `grep`-Prüfungen je WP (Zahlen, Codes, AK-Belege) |
| Secret-Scan | vor jedem Commit | Scan der gestagten Änderungen; Befund blockiert den Commit |

**Zahlenhinweis:** Die E2E-Zahl 65 ist reproduzierbar — vorausgesetzt, `HASS_BASE_URL`
zeigt auf den Compose-Stack (`http://127.0.0.1:8124`): dann laufen 65 Tests, 0 skipped.
Ohne gesetzte Variable zeigt die Adresse per Default auf die geteilte Instanz
(`loopback:8123`), und `tests_e2e/test_blueprints_e2e.py:83-92` überspringt per
Modul-Guard (`pytest.skip(allow_module_level=True)`) das gesamte Blueprint-Modul; die
Collection zeigt dann 46. Die Differenz 65 − 46 = 19 ist genau dieses Modul — kein
Widerspruch, sondern ein Schutz gegen schreibende Blueprint-Tests auf der geteilten
Instanz. Baseline für einen vollen E2E-Lauf ist **65 (Compose-Stack)**; 46 ist nur der
Zählstand ohne erreichbaren Stack.

---

## 7. Traceability (Audit-Befund → WP → Test/Beleg)

| Befund | WP | Test/Beleg |
|---|---|---|
| F-01 keine `TODO`/`FIXME` | — (erledigt) | `grep` → 0 |
| F-02 `hacs.json` sauber | — (erledigt) | `hacs.json` |
| F-03 Testzahlen | — (Korrektur) | `pytest --collect-only`: 1754 Unit / 65 E2E (Compose, `HASS_BASE_URL=…:8124`); 46 nur ohne erreichbaren Stack (Blueprint-Modul-Guard) |
| F-04 Entity-ID-Stabilität | — (erledigt) | 0.17.x-Releases, `tests_e2e/test_entity_ids_e2e.py` |
| F-05 `_attr_name`-Ausnahmen | — (erledigt) | `button.py:67,83` |
| F-06 Kern-Dateien wachsen | WP-D | Baseline + Trigger T-1/T-2/T-5; kein Refactor ausgelöst |
| F-07 Frontend-Größe | WP-D | Trigger T-4; kein Refactor ausgelöst |
| F-08 Zwei-Klassen-Fehler (REQ-HOM-127) | WP-A (PR #84, Release offen) | `tests/test_error_contract.py`, `tests/test_errors.py`, `tests_e2e/test_i18n_e2e.py`, REQ-HOM-132-Regression; `docs/SERVICE-RESPONSES.md` |
| F-09 Labor-Eingabe/Zahlen | WP-C | Doc-Grep (41/10/51/41), Entscheidungsrecord D-1 = B4 |
| F-10 HACS-Mechanik | WP-E (**manuell offen**) | Prozedur in WP-E (8 Schritte) + Abschlusskriterium; Belegdokument erst nach dem Lauf |
| F-11 Spec §9 O-1 | — (erledigt) | PR #75, `tests/test_entry_migration.py` |
| F-12 vier E2E-Lücken | WP-B (PR #82) | `tests_e2e/test_config_migration_e2e.py`, `test_diagnostics_e2e.py`, `test_input_persistence_e2e.py` |
| F-13 blockierendes I/O | — (erledigt) | PR #79 + drei Executor-Regressionstests |
| F-14 `bin/reauth`-Race | WP-F (extern erledigt) | Befund hier + Fix-Form (Lock, atomisches Replace, Modus 600); Stresslauf im Tooling-Repo |
| F-15 Blueprint-Personenbindung | — (erledigt) | PR #77, `tests_e2e/test_blueprints_e2e.py` |
| F-16 „kein funktionaler Fehler" | — (Scope-Korrektur) | F-13 als Gegenbeispiel; Aussage nur als statischer Befund lesen |
| F-17 README-Testzahlen | — (erledigt, dieser Änderungssatz) | `README.md:1300` → 1754 Unit / 65 E2E (Compose); nach WP-B erneut prüfen |

---

## 8. Nicht im Scope

- **Produktionscode für B1** — WP-C endet mit der Entscheidung; eine B1-Umsetzung ist
  ein eigenes Feature mit eigenem Task-Plan und eigener REQ.
- **Refactor der Kerndateien** — WP-D definiert nur Trigger; ohne Auslösung kein Split.
- **Vision E2–E6, B5/B6/B7** — in `docs/PLAN-BACKLOG-2026-11-02.md` Welle 5 entschieden:
  B5 nicht unterstützt, B6/B7 gestrichen, Vision geparkt; hier nicht umgesetzt.
- **Spec-Restpunkte O-2/O-3/O-4** — Pre-Pinning-Bestand, übersetzbare Default-Labels,
  veraltetes Migrations-Rezept; separater Umgang, nicht Teil dieses Plans.
- **HACS-/Frontend-Änderungen in diesem Repo** — WP-E prüft nur den Update-Pfad.
- **Änderungen an der geteilten Testinstanz** — WP-F dokumentiert nur; `bin/reset`,
  `bin/set-language` und schreibende E2E-Läufe bleiben untersagt bzw. koordiniert.
- **Audit-Nachtrag verfassen** — liegt vor (im Audit-Dokument); dieser Plan bewertet
  ihn nur, er ist nicht Teil der Arbeit.

---

## 9. Selbst-Review

- **Jeder Audit-Befund ist abgedeckt:** F-01 bis F-17 in §1 und §7; keiner ohne
  Einstufung. F-13/F-14 sind die zwei Befunde, die der Haupt-Audit nicht hatte
  (Nachtrag/Auftrag), F-17 stammt aus dem Nachtrag; alle drei stehen ausdrücklich in
  der Triage.
- **Kein WP ohne Akzeptanzkriterien:** WP-A bis WP-F haben je Ziel, Scope mit
  Datei-Ankern, Agenten, Schritte, AK, Tests, Risiken und DoD.
- **Kein stilles Duplikat:** WP-A ist ausdrücklich Welle 4 des Backlog-Plans; WP-E
  überschneidet Welle 1 Schritt 5, geht aber über die Simulation hinaus; WP-C
  überschneidet §2.4/Welle 5 und liefert die dort fehlende Zahlenkorrektur. Alles
  andere ist als neu markiert.
- **Entscheidungen sind von Arbeit getrennt:** §5 sammelt die sechs offenen
  Entscheidungen mit Entscheider und Blockadewirkung; §2 beschreibt nur Arbeit.
- **Keine Platzhalter/erfundenen IDs:** Offene Punkte sind als Entscheidungen mit
  Optionen formuliert; neue REQ-IDs vergibt ausschließlich `requirements`.
- **Prozess-Grenze respektiert:** kein `plan_ref`, keine `pipeline_stages`; der
  `planner`-Fallback (`documenter`) ist benannt.

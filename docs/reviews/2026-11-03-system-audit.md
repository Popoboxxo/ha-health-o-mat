# System-Audit — ha-health-o-mat (2026-11-03)

> **Nachtrag 2026-11-03 (Stand `1d6f832`):** Der Audit oben bleibt als Momentaufnahme zu
> `3d769d7` **unverändert** stehen. Dieser Nachtrag ergänzt ihn um den Stand nach den PRs
> #75, #77 und #79. Die Zeilenangaben in Klammern beziehen sich auf das Original **vor**
> diesem Nachtrag; überholte Aussagen sind dort nicht umgeschrieben, sondern hier als
> „superseded" ausgewiesen.
>
> | Thema | Original | Stand `1d6f832` |
> |---|---|---|
> | Spec §9 O-1 — Repair-Issue + Erfolgs-Notification | offen (Z. 122–123) | **umgesetzt** (PR #75), inkl. `async_remove_entry`-Cleanup |
> | HACS-Update-Test | offen (Z. 118–121) | **teilweise**: Update-Pfad 0.16.2 → 0.19.0 belegt; HACS-Mechanik **nicht geprüft** |
> | Blueprints | im Audit nicht erfasst | **vier** (`goal_reached`); `person_name`-Bindungsdefekt behoben (PR #77) |
> | Blocking I/O im Event-Loop | keine Befunde (Z. 132–134) | **superseded**: drei Blocking-Calls gefunden, im Executor behoben (PR #79) |
> | Testumfang | 1497 Unit / 39 E2E (Z. 29–30) | **superseded**: 1754 Unit / 65 E2E |
>
> **Als superseded markiert** (Originaltext bleibt wörtlich stehen): Z. 29–30
> (Testzahlen), Z. 118–123 (HACS-Update-Test offen; Spec §9 O-1 offen), Z. 132–134
> („Keine Korrektheits-, Sicherheits- oder Datenschutz-Befunde"), Z. 148–150
> (P3: HACS-Update-Test + Spec-§9-O-1-Folgepunkt) und Z. 152–154 („Nicht gefunden" mit
> der Pauschalaussage „keine unentdeckte Doku/Code-Abweichung") — diese Pauschalaussage
> war zu stark: die Testzahl-Drift an `README.md:1300` (in diesem Nachtrag gefunden,
> inzwischen korrigiert, s. u.) ist genau eine solche unentdeckte Doku/Code-Abweichung.
>
> **Erledigt seit dem Audit:**
>
> 1. **Spec §9 O-1 (PR #75).** Repair-Issue im blockierten Migrationsfall (stabile ID
>    `migration_blocked_<entry_id>`, `is_fixable=False`, skalares `data` mit Paarliste,
>    Löschung bei sauberem Pass **und** in `async_remove_entry`) plus genau eine
>    Erfolgs-Notification nach echten Renames (`entity_id_migration_<entry_id>`, nie
>    setup-kritisch). Belege: `__init__.py`/`migration.py`,
>    `tests/test_entry_migration.py`, `tests/test_remove_entry.py`,
>    `docs/REQUIREMENTS.md:2072`.
> 2. **HACS-Update-Test — teilweise.** Der Update-Pfad 0.16.2 → 0.19.0 ist auf dem
>    Compose-Stack **simuliert** belegt: Entry v2 → v3, 82 alte `unique_id`s erhalten,
>    95 Entities, Daten unverändert, eine Notification, kein Repair-Issue, zweiter
>    Neustart idempotent. **Nicht belegt:** die HACS-Mechanik selbst (kein HACS im
>    gepinnten E2E-Image, Read-only-Bind-Mount, interaktiver Device-Flow) — REQ-HOM-130
>    bleibt deshalb „teilweise".
> 3. **Blueprints (PR #77).** Vierter Blueprint `goal_reached.yaml`; in
>    `evening_reminder`/`blood_pressure_warning` war `person_name` im Jinja-Template
>    referenziert, aber nie gebunden (HA substituiert nur `!input`) — behoben über
>    `variables: {person: !input person_name}`; Regression in `tests/test_blueprints.py`,
>    neuer 19-Test-E2E (`tests_e2e/test_blueprints_e2e.py`).
> 4. **Blocking I/O (PR #79).** Die Aussage „keine Befunde" (Z. 132–134) hat eine ganze
>    Fehlerklasse übersehen: `list_import_files`/`os.listdir`, `safe_import_path` und
>    `safe_restore_path` liefen im Event-Loop. Gefunden über das E2E-HA-Log (1 Warnung
>    vorher, 0 nachher), behoben per Executor. Belege im Code: `ws_api.py:2316`,
>    `importer.py:747`, `restore.py:1171`; Tests: `tests/test_ws_api.py:4502`,
>    `tests/test_restore.py:852`.
> 5. **Teststand.** 1754 Unit-Tests, 65 E2E-Tests; die vollständige Suite lief zweimal
>    grün. Die E2E-Zahl ist nachgezählt: 65 E2E-Tests, wenn `HASS_BASE_URL` auf den
>    Compose-Stack zeigt (46 + 19 Blueprint-Tests). Ohne erreichbare Instanz überspringt
>    `tests_e2e/test_blueprints_e2e.py:83-92` das Modul (`allow_module_level`), dann sind
>    es 46 Tests plus ein übersprungenes Modul. (Die 1754 stammen aus dem letzten
>    vollständigen `pytest -q`-Lauf, nicht aus einem neuen Lauf für diesen Nachtrag.)
>
> **Weiterhin offen (unverändert):**
>
> - **REQ-HOM-127** — Fehlercode-/i18n-Umbau der Alt-Pfade (Zwei-Klassen-Fehlerbehandlung,
>   Z. 65–72).
> - **E2E-Lücken** — REQ-HOM-101 AK4, REQ-HOM-105 (Diagnostics-E2E), „Update mit
>   Alt-Bestand + Button-Änderung nach Reload".
> - **Entscheidung Eingabe-Vereinfachung Laborwerte** — Options-Doc-Zahlen weiterhin
>   veraltet (29 → 41 Marker, 9 → 10 Kategorien, Z. 110–115).
> - **Datei-Wachstumstrend** (Z. 42–57) und **HACS-Mechanik selbst** (s. o.).
> - **Doku-Drift — erledigt (2026-11-03):** `README.md:1300` nannte „25 E2E-Tests" und
>   „1563 Unit-Tests"; korrigiert auf **1754 Unit- / 65 E2E-Tests**, dazu die veraltete
>   Parenthese „CI-äquivalent 1562 passed, 1 skipped" entfernt. Bleibt als Beleg stehen,
>   ist aber kein offener Punkt mehr.
>
> **Neuer Befund außerhalb dieses Repos (nicht hier zu fixen):**
> `/home/hermes/ha-test/bin/reauth:49` schreibt `token.json` in place und nimmt **nicht**
> das `refresh.lock`, das `bin/ha` (Z. 51–95) für die Token-Rotation nutzt — derselbe
> Rotation-Race kann erneut auftreten, wenn `reauth` parallel zu einem `bin/ha`-Refresh
> läuft.
>
> **Quelle des Nachtrags:** Repo-Stand `main` @ `1d6f832` (2026-11-03), die genannten PRs,
> `docs/REQUIREMENTS.md` (Changelog-Einträge 2026-11-02/03), die Blueprint-/Test-Dateien
> im Repo sowie ein Blick in `/home/hermes/ha-test/bin/{ha,reauth}`.

---

> **Methode:** Read-only, im Main Chat, ohne GitHub-Funktion (kein Issue/PR).
> Scope: `custom_components/health_o_mat/**` (Python + `www/*.js`) und
> `tests/`/`tests_e2e/`. Agenten-Tooling (`.claude/**`, `.agent-meta/**`) und
> reine Planungsdokumente (`docs/superpowers/**`) sind ausgeschlossen, außer
> wo ein Fund die Doku-Genauigkeit selbst betrifft.
> **Basis:** `main` = `3d769d7` (synchron mit `origin/main`), 2026-11-03.
> **Hinweis:** Diese Datei wird während der Arbeit mehrfach nachgespeichert
> (Kontingent-Schutz) — Abschnitte können zunächst als Gerüst stehen und
> später befüllt werden.

---

## 0. Status dieses Dokuments

- [x] 1. Code-Qualität
- [x] 2. Feature-Qualität
- [x] 3. Offene Features
- [x] 4. Priorisierte Zusammenfassung

---

## 1. Code-Qualität

**Positiv:**
- Keine einzige `TODO`/`FIXME`/`XXX`-Markierung im gesamten `custom_components/health_o_mat/**`.
- `hacs.json` saubet (kein `iot_class`-Leak in die falsche Datei — eiserne Regel eingehalten).
- Testabdeckung ungewöhnlich hoch für die Projektgröße: **1497** Unit-Test-Funktionen
  (33 Dateien unter `tests/`) + **39** E2E-Test-Funktionen (10 Dateien unter `tests_e2e/`).
  REQUIREMENTS.md dokumentiert als letzten belegten Lauf 1566 passed — grob konsistent,
  Wachstum seither plausibel.
- Entity-ID-Stabilität (Thema aus dieser Session): **REQ-HOM-130 + REQ-HOM-131**
  vollständig umgesetzt und released (0.17.0–0.17.2), inkl. Live-Migrationstest auf der
  Testinstanz mit Kollisions-/Retry-Probe. Die vorher offene Frage „Englisch/stabil über
  alle Plattformen" ist damit **erledigt**, nicht mehr offen.
- Bereits bekannte, bewusste Ausnahmen vom „kein `_attr_name`-Literal"-Grundsatz sind
  dokumentiert, nicht übersehen: `QuickDrinkButton._attr_name` (`button.py:83`, Audit-Finding
  M-8 — Freitext-Label aus Nutzerkonfiguration, nichts zu übersetzen) und Custom-Lab-Marker
  (gleiche Begründungsklasse). Keine neuen, unbegründeten Literale gefunden.

**Beobachtung — wachsende Kern-Dateien (kein Blocker, aber Trend):**

| Datei | Zeilen | Trend |
|---|---:|---|
| `ws_api.py` | 2402 | größte Python-Datei; jede neue Service-/Panel-Fläche landet hier |
| `__init__.py` | 1809 | Service-Handler aller Domänen in einer Datei |
| `store.py` | 1582 | CRUD aller vier Datendomänen in einer Klasse |
| `logic.py` | 1422 | HA-freie Logik aller Domänen gebündelt |
| `restore.py` | 1262 | |
| `const.py` | 658 | v. a. durch den 41-Marker-Laborkatalog |

Jede neue Feature-Welle (Trinken → BD → Wohlbefinden → Labor-Batch → Labor-Katalog →
Entity-ID-Migration) hat bisher in dieselben sechs Dateien geschrieben, nie gesplittet.
Noch kein akutes Problem (Dateien sind intern klar in Abschnitte gegliedert, Tests bleiben
grün), aber der Trend verschärft sich mit jeder weiteren Domäne — ein Kandidat für
„bei der nächsten großen Erweiterung mitdenken", kein Befund, der heute Handlung braucht.

**Beobachtung — Frontend-Dateigröße:** `health-o-mat-card.js` (3362 Zeilen),
`health-o-mat-panel.js` (2362), `health-o-mat-labs-card.js` (1791),
`health-o-mat-panel-views.js`/`-base.js` (je ~1570) sind für HA-Custom-Cards
architekturbedingt Einzeldateien (kein Bundler) — die Größe selbst ist also kein
vermeidbarer Fehler, aber Navigierbarkeit/Review-Aufwand steigt mit jeder Karte.

**Zwei-Klassen-Fehlerbehandlung (echter, benannter Befund):** Die Labor-Batch-Services
(`add_lab_report`/`remove_lab_report`, seit 0.16.2) antworten bereits mit strukturierten
Fehlern (`{code, params, message}`). Die älteren Services/WS-Pfade (Trinken, Blutdruck,
Wohlbefinden, der ursprüngliche `add_lab_value`) werfen weiterhin Prosa-Exceptions
(`ServiceValidationError`/`HomeAssistantError` mit freiem Text, nicht lokalisiert). Das ist
**kein neuer Fund** — exakt **REQ-HOM-127**, bereits zweimal explizit als offen vermerkt
(2026-11-01, 2026-11-02) — aber diese Session bestätigt: der Codebase trägt jetzt
tatsächlich beide Stile parallel, nicht nur in der Doku vorgemerkt.

---

## 2. Feature-Qualität

Vier Datendomänen, alle mit Status „Umgesetzt" und Beleg in `docs/REQUIREMENTS.md`:

- **Trinken** — REQ-HOM-001 ff., Quick-Drinks jetzt mit stabilen englischen
  `object_id`s (`quick_drink_<n>`, REQ-HOM-130).
- **Blutdruck** — inkl. Messnotiz-Entity (REQ-HOM-010, zuletzt gemergt, PR #76).
- **Wohlbefinden** — Score + Bestätigung + Chart (REQ-HOM-112/114/120).
- **Laborwerte** — von REQ-HOM-122 (Basis, 29 Marker) über REQ-HOM-123–129
  (Batch-Check-in `add_lab_report`, Batch-Undo `remove_lab_report`, Admin-
  Umrechnungsspalte, Panel-Disclaimer, Retention, Beispiel-Dashboard) bis
  **REQ-HOM-133** (12 weitere Marker + neue Kategorie `metabolism` → **41 Marker,
  10 Kategorien**, Release 0.19.0). Jede Welle in README/REQUIREMENTS.md
  gegengeprüft (diese und vorherige Session) — keine Abweichung zwischen Doku und
  Code gefunden.

**Querschnitts-Feature REQ-HOM-132** (optionale Service-Antworten, CSV-Upload,
atomarer Import, Release 0.18.0) — admin-only CSV-Pfad auf Service **und**
WebSocket konsistent, Fehler bleiben Exceptions statt stiller Teilerfolge.

**Kein funktionaler Fehler gefunden.** Die einzigen Lücken sind bereits selbst
dokumentierte, bewusst aufgeschobene Punkte (REQ-HOM-127, s. o.) und ein paar
einzelne E2E-Akzeptanzkriterien (s. Abschnitt 3) — keine stillen, unentdeckten
Abweichungen zwischen Anspruch und Code.

---

## 3. Offene Features

1. **REQ-HOM-127 — Fehlercode-/i18n-Umbau** (eigener Plan, zweimal explizit
   aufgeschoben). Siehe Abschnitt 1, „Zwei-Klassen-Fehlerbehandlung".
2. **„Eingabe-Vereinfachung" Laborwerte** — `docs/superpowers/specs/2026-11-01-lab-entity-surface-options.md`,
   Status weiterhin **BRAINSTORM, NICHT BESCHLOSSEN** (verifiziert: keine
   REQ-HOM-134+, keine Lab-Referenz in `select.py`/`number.py`/`text.py`/`button.py`).
   **Wichtig für die nächste Entscheidungsrunde:** die Zahlenbasis des Dokuments
   (§1.1: 29 Marker, 9 Warn-Kategorien, 38 Labor-Entities) ist jetzt **veraltet** —
   der Katalog ist seit REQ-HOM-133 auf **41 Marker / 10 Kategorien** gewachsen
   (neue Kategorie `metabolism`). Die Tabelle und alle daraus abgeleiteten
   Optionsbewertungen (A1–A9, B1–B5, R1–R3) müssten vor einer Entscheidung neu
   gerechnet werden — die Kernaussagen/Trade-offs bleiben aber strukturell gültig.
   Aus dieser Session weiterhin offen: deine Antwort auf „B1 (4 neue Eingabe-
   Entities nach BP-Vorbild) vs. B4 (Status quo, nur Doku)" steht noch aus.
3. **HACS-Update-Test nach der Entity-ID-Migration** — laut REQUIREMENTS.md
   (REQ-HOM-130-Eintrag) explizit noch offen: der echte HACS-Store-Update-Pfad
   (Vorgängerversion → aktuelle Version über HACS selbst, nicht nur die
   Live-Migration auf der Testinstanz) ist noch nicht durchgeführt.
4. **Spec §9 O-1 (Entity-ID-Migration)** — Repair-Issue + Erfolgs-Notification nach
   der Migration; laut Doku als Folge-Punkt vermerkt, noch nicht umgesetzt.
5. Vereinzelte offene Akzeptanzkriterien (E2E-Lücken, keine Funktionsfehler):
   REQ-HOM-101 AK4, REQ-HOM-105 (E2E), E2E für Diagnostics-Download, E2E für
   „Update mit Alt-Bestand + Button-Änderung nach Reload".

---

## 4. Priorisierte Zusammenfassung

**Gesamtbild: sehr gesund.** Keine Korrektheits-, Sicherheits- oder
Datenschutz-Befunde. Alles was in `docs/REQUIREMENTS.md` als „umgesetzt"
markiert ist, hält auch im Code und in der README.

**Priorisiert, was als Nächstes sinnvoll wäre (keine davon ist dringend):**

1. **P2 — Eingabe-Vereinfachung entscheiden** (offene Frage aus dieser Session):
   erst Zahlenbasis der Options-Doc aktualisieren (41 statt 29 Marker), dann
   B1 vs. B4 entscheiden — das ist der einzige Punkt, der konkret auf deine
   Antwort wartet.
2. **P2 — REQ-HOM-127 einplanen**, sobald eine ruhige Welle kommt: der
   Stil-Bruch (strukturierte Fehler nur bei Labor-Batch, Prosa sonst) wird mit
   jeder weiteren Domäne, die neu dazukommt, teurer nachzuziehen.
3. **P3 — Datei-Wachstum im Blick behalten:** `ws_api.py`/`__init__.py`/`store.py`/
   `logic.py` nicht aktiv splitten, aber beim nächsten großen Feature prüfen, ob
   eine Trennung (z. B. nach Domäne) fällig ist.
4. **P3 — HACS-Update-Test + Spec-§9-O-1-Folgepunkt** nachholen, bevor das nächste
   Breaking-Change-Feature kommt (Entity-ID-Migration war MINOR, nicht MAJOR —
   die Update-Erfahrung sollte einmal real verifiziert sein).

**Nicht gefunden:** keine Sicherheitslücken, keine Datenverlust-Pfade, keine
unentdeckte Doku/Code-Abweichung, keine verbotenen Literale ohne Begründung,
kein `iot_class`-Platzierungsfehler, keine fehlenden `unique_id`s.

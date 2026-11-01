# Umsetzungsplan offene Issues — 0.17.3 / 0.18.0 / 0.19.0

**Status:** geplant (Umsetzung nicht begonnen) · **Datum:** 2026-11-01
**Basis:** `manifest.version = 0.17.2` (`manifest.json:22`), `main` sauber (`ad78b5a`)
**Bezug:** Issues #28, #31, #33, #70, #71, #72, #73 · REQ-HOM-122…131
**Instanzen:** `ha-test` (HA 2026.9.1, `de`, manuelle Abnahme) · Compose-E2E Port 8124
**Vorgänger:** `docs/superpowers/specs/2026-11-01-lab-values-batch-and-visibility-design.md`

---

## 1. Ziel und Ausgangslage

| Release | Inhalt | Ergebnis |
|---|---|---|
| 0.17.3 | #70 | Laborwerte im Verlauf sichtbar/korrigierbar, paginierbar |
| 0.18.0 | #71, #72, #28, #31, #33, Infra, B4, B2 | Service-Antworten, WS+Admin-Import, E2E-Härtung |
| 0.19.0 | #73, Katalog/Einheiten, B3 | 12 Marker, `metabolism`, robustere Einheiten |

Verifiziert: `LAB_CATEGORIES` = 10 Einträge (9 Kategorien + `other`, `const.py:175–185`),
`LAB_MARKERS` = **29** (`const.py:192–485`); `HISTORY_KINDS` (`logic.py:919`) kennt kein
`lab_values`, obwohl `void_entry`/`restore_entry` es akzeptieren (`__init__.py:1538–1560`).
Kein `SupportsResponse`; Handler verwerfen ihre Ergebnisse. `import_csv` ist **nicht**
admin-gegated (`__init__.py:1334`), die drei anderen schon (`1324, 1350, 1361`) — Baseline
**1605** Unit-Tests.

---

## 2. Entscheidungsprotokoll (vom Nutzer beschlossen)

| # | Entscheidung | Begründung | Stellen |
|---|---|---|---|
| **D1** | HbA1c → Kategorie `metabolism`, **vor** `other`. | Ehrlicher als „Sonstige“; additiv, `other` bleibt Fallback → MINOR, kein Migrator. | `const.py:175–185`, `strings.json`, `binary_sensor.py:36–41` |
| **D2** | Alle 12 Marker aus #73 in **einem** Release. | Ein Katalogschnitt pro Release hält Docs/CSV/Tests konsistent. | `const.py:192–485`, `sensor.py:58` |
| **D3** | **Option B**: `alt_units` laut Issue; `require_explicit_unit: true` für `mchc`, `hematocrit`, `albumin`, `alkaline_phosphatase`, `phosphate`, `uric_acid`, `hba1c`; Härtung in `_norm_unit` (`u`→`µ`, Superscripts, `Prozent`→`%`); Leerstring → `unit_required`; Flag an die Eingabe-UI. | Diese sieben Werte sind ohne Einheit nicht eindeutig; stille Annahme wäre eine falsche Gesundheitszahl. | `logic.py:982–991, 1122–1139, 1244`; `__init__.py:1125`; `ws_api.py:713, 1413` |
| **D4** | #70 über `list_history` `kind=lab_values` (inkl. `include_voided`) **plus** `lab_values` in Void/Restore-Zuordnung; **kein** Admin-Gate. | Verlauf ist Alltagswerkzeug; ein Gate verhinderte die Korrektur eigener Werte. | `logic.py:919–938`; `ws_api.py:875–906, 985–1000, 1236–1263` |
| **D5** | `limit`/`offset`/`has_more` (Labor-Default **200**) **und** `since`; `report_ref` nur bei `include_report_ref: true` (Default `false`). Bestands-Kinds bleiben „unbegrenzt“. | Labor-Verlauf wächst mit jedem Bericht; Bestands-Clients dürfen sich nicht ändern. | `ws_api.py:985–1000, 1236–1263` |
| **D6** | `SupportsResponse.OPTIONAL` für `export_csv`, `import_csv`, `backup`, `restore_backup`, `weekly_report` — **nie** `ONLY`; flache Keys; Fehler = Exceptions, Teilausfälle = Daten; `errors` ≤ 20. | `ONLY` bräche Aufrufe ohne `return_response` (Automationen, WS-Brücke `ws_api.py:1968–2013`); Responses landen im Trace → nur Counts/Dateinamen. | `__init__.py:1322–1417, 1562–1620`; `services.yaml:171–330`; **überholt:** Spec `…lab-values-batch-and-visibility-design.md:326, 331, 919` |
| **D7** | WS `health_o_mat/import_csv`: **entweder** `filename` **oder** `content` (genau eines), Cap **2 MiB**, **admin-only** (Service + WS); Export-Ordner zusätzlich für CSV lesbar; **nur `;` und UTF-8**. D7b: atomar via `add_lab_readings`; Dedupe-Lücke schließen. | Upload ist der einzige Weg ohne Dateisystemzugriff; ohne Gate könnte jeder Haushaltsnutzer Daten fluten; `;`/UTF-8-only verhindert stille Fehlinterpretation. | `ws_api.py:132–143`; `importer.py:41, 109–135, 625–732`; `__init__.py:1334` |
| **D8** | I3: Compose (8124) für #28/#31; geteilte Instanz nur manuelle Abnahme. Voraussetzung: HA-Image `2026.9.1`, `playwright==1.47.0`, Bootstrap-Nicht-Admin. | Geteilte Instanz darf nicht durch Testnutzer leiden; Compose ist reproduzierbar. | `docker-compose.e2e.yml:35`, `requirements_e2e.txt:8`, `Dockerfile.e2e:9`, `scripts/e2e_bootstrap.py:169–188` |
| **D9** | Releases **0.17.3** (#70) · **0.18.0** (#71+#72+#28+#31+#33+Infra) · **0.19.0** (#73+Einheiten). Kein MAJOR. | Keine `unique_id`-, Store-Schema- oder Entry-Version-Änderung → keine Migrator-Pflicht. | `manifest.json:22` |
| **D10** | Backlog B1–B10 gemäß §7. | Verschiebt Punkte mit eigenem Entscheidungsbedarf. | §7 |

> **D9-Abweichung:** D7 macht den Import admin-only — nach Repo-Regel „Breaking = MAJOR“ ein
> MAJOR-Kandidat. Beschlossen ist MINOR **mit 💥-Hinweis** (§4); die Abweichung wird dokumentiert.
>
> **D3-Interpretation (RVW-11):** „Leerstring → `unit_required`“ gilt nur für Marker mit
> `require_explicit_unit` (konsistent zum Batch-Pfad `logic.py:1244`); bei optionalen Markern
> bleibt die leere Einheit „keine Angabe“ → kanonische Einheit.
>
> **O-2 (Erweiterung von D6):** `export_csv → {filename: str, filenames: list[str], rows: int,
> dataset: str}`; `filename` = erste Datei, `rows` = Summe über alle Dateien. Rein additiv, die
> D6-Keys bleiben gültig — `exporter.py:171–183` schreibt bei `dataset: all` mehrere Dateien
> und verwirft heute alles außer `paths[0]`.
>
> **O-3 (D7b-Interpretation):** „atomar“ heißt **je Bericht + Batch-Save**, nicht dateiweit
> transaktional. Je `(ts, report_ref)`-Gruppe ein Audit, je **Labor-Dataset ein**
> Speichervorgang (`add_lab_readings_bulk`); der Restfall (Abbruch mitten in der Datei) wird
> über den wiederholbaren Import abgefangen (Dedupe `importer.py:573–605`).
>
> **O-4 (Erweiterung von D5):** jedes **explizit gesetzte** `limit` ist auf 1000 gedeckelt und
> wird darüber als `invalid_format` abgelehnt (nie still gekappt); der Default der drei
> Bestands-Kinds bleibt „unbegrenzt“.
>
> **O-5 (B4):** `>=` ist führend (Hypertonie ab ≥140/90). `binary_sensor.py:89` bleibt,
> `ws_api.py:545` (Call-Site) und `_is_above` (`559–566`, inkl. Docstring) werden auf `>=`
> gezogen; Verhaltensänderung in den 0.18.0-Notes.

---

## 3. Arbeitspakete

### WP0 → 0.17.3 — Issue #70: Laborwerte im Verlauf

**Ziel:** Laborwerte über denselben WS-Verlauf sichtbar/löschbar/wiederherstellbar wie die
übrigen Domänen — ohne neues Gate (D4).

| Datei | Stelle | Änderung |
|---|---|---|
| `logic.py` | `919`, `922–926`, `929–938` | `lab_values` in `HISTORY_KINDS`, `HISTORY_LIST_BY_KIND` (→ `lab_readings`), `VOID_/RESTORE_METHOD_BY_KIND` (→ `void_lab_reading`/`restore_lab_reading`) |
| `logic.py` | `945–954` | `_KIND_ALIASES` um `lab_values`/`lab_value`/`lab_readings` erweitern — `normalize_history_kind()` löst **ausschließlich** über dieses Literal-Dict auf, ohne Alias bleibt `kind=lab_values` unbekannt (RVW-01) |
| `__init__.py` | `1000–1053` | `_LAB_STATE_KINDS`/`_LAB_STATE_ALIASES`/`_normalize_state_kind` entfernen und `allowed = (*HISTORY_KINDS, *_LAB_STATE_KINDS)` auf `HISTORY_KINDS` reduzieren — sonst steht `lab_values` doppelt im Fehlertext und der Lab-Sonderweg wird toter Code (RVW-05) |
| `ws_api.py` | `875–906` | `_history_item`: `lab_values`-Zweig (`marker_key`, `value`, `unit`, `reported_value`, `reported_unit`, `report_ref`) **vor** dem Wellbeing-`else` |
| `ws_api.py` | `985–1000`, `1236–1263` | Schema + Filter/Sortierung/Pagination, `has_more` |

**Schritte**

1. Zuordnungstabellen **und** `_KIND_ALIASES` (`logic.py:945–954`) erweitern; `HISTORY_KINDS`
   bleibt alleinige Fehlertextquelle (`ws_api.py:1256`). Den Service-Sonderweg
   (`__init__.py:1000–1053`) auf `logic.normalize_history_kind` + die Tabellen konsolidieren,
   damit `lab_values` nicht doppelt in `allowed` steht.
2. `build_history` (`ws_api.py:909–940`): `since` über `logic.parse_entry_timestamp`
   (`logic.py:166`) zum UTC-Instant normalisieren und **auf dem Instant** vergleichen
   (inklusive, nicht lexikografisch — DST-/Offset-sicher, RVW-08) → sortieren → `offset` →
   `limit`; `has_more = limit is not None and len(gefiltert) > offset + limit`, sonst `False`
   (RVW-10).
3. `limit` nur für `lab_values` = 200, sonst `None`; `offset` 0. `report_ref` nur bei
   `include_report_ref` ausgeben; `include_voided` nutzt den bestehenden Filter. **Cap (O-4):**
   jedes explizit gesetzte `limit` > 1000 → Schema-Fehler `invalid_format` (Ablehnung, kein
   stilles Kappen) — auch bei den drei Bestands-Kinds.
4. `void_entry`/`restore_entry` laufen über die Tabellen (`ws_api.py:1288–1331`);
   `signal_refresh` bleibt unverändert.

**Akzeptanzkriterien**

1. `kind=lab_values` (auch `lab_value`/`lab_readings`) liefert Einträge, neueste zuerst, mit
   `id, ts, created_at, marker_key, value, unit, reported_value, reported_unit, voided_at,
   voided_by, void_reason`; `include_voided=false` (Default) filtert voided, `true` enthält
   sie; ohne `include_report_ref` fehlt `report_ref` in **jedem** Eintrag.
2. `limit`/`offset` liefern ein deterministisches Fenster; `has_more` ist `false`, wenn `limit`
   fehlt, sonst genau dann `true`, wenn danach Einträge folgen; Labor-Default 200;
   Bestands-Kinds liefern ohne `limit` weiterhin **alle** Einträge.
3. `since` filtert offset-sicher: ein Eintrag mit `ts="…+02:00"` relativ zu `since="…Z"` wird
   korrekt ein-/ausgeschlossen (Negativtest `+02:00` vs. `Z`).
4. `limit=1000` wird angenommen; `limit=1001` wird mit `invalid_format` abgelehnt (auch für
   `drinks`/`blood_pressure`/`wellbeing`); ohne `limit` bleiben diese drei unbegrenzt.
5. `void_entry`/`restore_entry` (`kind=lab_values`) rufen `signal_refresh`, und der
   `coordinator.data`-Stand der Marker-Entities wechselt von aktiv zu voided und zurück.
6. Unbekanntes `kind` nennt `lab_values` **genau einmal** in der erlaubten Liste;
   `pytest -q` grün, `ruff` clean.

**Tests:** Unit (Sortierung, `include_voided`, `report_ref`, Pagination, Bestands-Regression,
Void/Restore); E2E auf 8124 (anlegen → Verlauf → voiden → `include_voided=true` → restoren).
**Risiken:** Labor fällt in den Wellbeing-`else`-Zweig → expliziter `elif` vor `else` +
`assert "marker_key"`; Pagination bricht Bestands-Clients → kein Default-`limit` für die drei
Kinds + Regressionstest. **DoD:** AK 1–6; `REQUIREMENTS.md` ergänzt; Notes 0.17.3.

---

### WP1 → 0.18.0 — Issues #71/#72: Responses, Import, Admin-Gate, Atomarität

**Ziel:** Services antworten optional strukturiert (D6); CSV-Import ohne Dateisystem und
admin-only (D7); Labor-Import atomar und dedupliziert (D7b).

| Datei | Stelle | Änderung |
|---|---|---|
| `__init__.py` | `1322–1417`, `1562–1620` | Handler geben Ergebnisse zurück; `supports_response=SupportsResponse.OPTIONAL` (5 Services) |
| `__init__.py` | `1334` | `await _async_require_admin(hass, call)` vor dem Import |
| `exporter.py`/`backup.py`/`restore.py` | `50–183`/`154–197`/`1135–1145` | `{filename, filenames, rows, dataset}` / `{filename, datasets, rows}` / `+ filename` |
| `__init__.py` | `1369–1413` | `weekly_report` → `{reports, delivered, failed}` |
| `ws_api.py` | neu + `132–143` | `health_o_mat/import_csv`, in `ADMIN_ONLY_COMMANDS` |
| `importer.py` | `41, 87–125` | `safe_import_path` zusätzlich Export-Ordner; `content` ohne Datei-I/O |
| `store.py` | `642–790` (neu) | Dedupe `(ts, marker_key)`; Mehrgruppen-Save über N `(ts, report_ref)`-Gruppen in **einer** Persistenz (Vertrag unten) — `add_lab_readings` speichert heute je Aufruf |

**Schritte**

1. **D6:** `from homeassistant.core import SupportsResponse`; Handler geben exakt zurück:
   `export_csv → {filename, filenames, rows, dataset}` (O-2; `rows` = Summe aller Dateien,
   `filename` = `filenames[0]`), `import_csv → {imported, skipped, rejected,
   errors}`, `backup → {filename, datasets, rows}`, `restore_backup → {filename, applied,
   dry_run, counts, totals, warnings}`, `weekly_report → {reports: [{person,
   notify_service, delivered}], delivered, failed}`; Fehler bleiben Exceptions.
   `weekly_report` bekommt ein `try/except` **je Person** im Loop — heute fängt zentral
   `__init__.py:1410–1413` und bricht beim ersten Notify-Fehler ab, `failed` wäre immer 0
   (RVW-07); `delivered`/`failed` bilden die Einzelergebnisse ab.
2. **D7:** Schema erzwingt „genau eines“ von `filename`/`content`; `content` ≤
   `2 * 1024 * 1024` (neue `const.py`-Konstante), sonst `content_too_large`; `filename`
   durch `safe_import_path`, erweitert um `BACKUP_DIR_NAME`. Format: nur `;` + UTF-8
   (`utf-8-sig`, BOM-tolerant), keine Auto-Erkennung, kein `cp1252`; Doku in `README.md` +
   `services.yaml` („Nur für Administratoren“).
3. **D7 Gate:** Service nutzt `_async_require_admin` (`__init__.py:974–991`); WS-Kommando
   in `ADMIN_ONLY_COMMANDS` (`ws_api.py:1136–1143`) **und** `is_admin_connection`
   (`ws_api.py:1700–1714`, fail-closed).
4. **D7b (O-3 = B):** Labor-Zeilen nach `(ts, report_ref)` gruppieren und **je Labor-Dataset**
   über die neue Store-Methode `add_lab_readings_bulk` (Vertrag unten) in **einem**
   `_async_save` schreiben — nicht zeilenweise und nicht ein Save je Gruppe (heute speichert
   `add_lab_readings` je Aufruf, `store.py:683–770`). Keine dateiweite Transaktion: bricht der Lauf
   mitten in der Datei ab, holt ein **zweiter Import** die fehlenden Zeilen nach — die
   Dedupe-Logik verhindert Duplikate. Getränke/BD behalten den Zeilenpfad.
5. **Dedupe-Regel (RVW2-02):** kanonisch ist **`(ts, marker_key)`** — der Store-Guard führt;
   der Importer wird von `(ts, marker_key, value)` (`importer.py:482, 573`) darauf angeglichen.
   Eine Zeile mit gleichem `ts`/Marker, aber **neuem** Wert ist damit ein Duplikat und wird
   **nicht** geschrieben: im Import `skipped` (kein Abbruch), im Einzel-Add
   `duplicate_marker` (Fehler nur für diesen Aufruf). `add_lab_value`/`add_lab_report`
   (Service **und** WS) lehnen `(ts, marker_key)` ab, das im Store liegt (auch voided).

**Store-Vertrag (neu, RVW2-01)**

- **Signatur:** `async def add_lab_readings_bulk(self, entry_id: str, groups: list[dict], *,
  actor: str | None = None, audit_limit: int = DEFAULT_AUDIT_LIMIT) -> list[str]`; je Gruppe
  `{"ts_iso": str, "report_ref": str | None, "rows": list[dict]}` (Rows wie `add_lab_readings`).
  Rückgabe: alle geschriebenen Reading-IDs in Gruppen-/Zeilenreihenfolge.
- **Rollback über N Gruppen:** vor dem ersten Append `deepcopy`-Snapshot von
  `entry["lab_readings"]` **und** `entry["audit_log"]` (Muster `store.py:704–745`); bei jeder
  Exception werden beide vollständig zurückgesetzt, dann wird der Fehler weitergereicht — kein
  Teilzustand im Speicher.
- **Audit-Kardinalität:** **ein** `lab_values_added` je Gruppe (= je Bericht), alle im selben
  Save persistiert; die Anzahl der Audit-Einträge ist `len(groups)` — konsistent zu AK 5.
- **Persistenz:** genau **ein** `_async_save()` für den gesamten Aufruf.

**Akzeptanzkriterien**

1. Aufruf **ohne** `return_response` funktioniert unverändert (kein `ONLY`); mit
   `return_response=True` exakt die D6-Keys; `import_csv` nutzt `imported`, **nicht** `added`;
   `export_csv` liefert `filenames` mit **allen** geschriebenen Dateien und `filename` =
   `filenames[0]` (O-2).
2. `errors` ≤ 20; `rejected` zählt weiterhin alle; Fachfehler (z. B. „Keine Daten“) kommen
   als Exception, nicht als Response-Feld.
3. WS akzeptiert **genau eines** von `filename`/`content`; beide/keines → Fehler;
   `content` > 2 MiB → `content_too_large`, kein Schreibzugriff; Nicht-Admin (Service **und**
   WS) → `Unauthorized`/`ServiceValidationError`, Admin importiert erfolgreich.
4. CSV aus dem Export-Ordner importierbar; `,`-Trenner oder `cp1252` → abgelehnt bzw.
   `rejected` (kein stilles Uminterpretieren).
5. **Importpfad (O-3):** ein Bericht ist **nie halb** geschrieben (Fehler in Zeile 3
   hinterlässt keine Zeilen 1–2); ein Dataset bekommt **einen** Speichervorgang, ein Bericht
   **ein** Audit; ein zweiter Import derselben Datei ergänzt fehlende Zeilen ohne Duplikate
   (`skipped` > 0, keine neuen Einträge); eine Zeile mit gleichem `(ts, marker_key)`, aber
   neuem Wert, zählt als `skipped` und bricht den Import **nicht** ab.
6. **Einzel-Add-Pfad:** `add_lab_value`/`add_lab_report` (Service **und** WS) schreiben ein
   Duplikat `(ts, marker_key)` nie; sie melden `duplicate_marker`, auch wenn der Wert abweicht
   (kanonische Regel aus Schritt 5), und der Aufruf endet ohne Teilzustand.
7. `weekly_report` mit zwei Personen und fehlschlagendem Notify bei Person B: Person A wird
   zugestellt (`delivered:true`), Person B erscheint mit `delivered:false`, `failed ≥ 1` — und
   die Response kommt trotzdem zurück.
8. `pytest -q` grün, `ruff` clean, `REQUIREMENTS.md` + `services.yaml` aktualisiert.

**Tests:** Unit (exakte Key-Mengen, `errors`-Cap, „genau eines“, 2-MiB-Grenze ok/+1 Byte,
Gate beider Pfade, Atomarität über Save-/Audit-Zähler, Dedupe). E2E auf 8124: Admin-Import
per `content`, Nicht-Admin-Fehler (setzt WP2-Infra voraus). Service-Responses selbst nur per
Unit — Automationen sind kein Testsubjekt.
**Risiken:** `ONLY` bricht Automationen → nur `OPTIONAL` + Test ohne Response; Response im
Trace → nur Counts/Dateinamen; 2 MiB blockiert Event-Loop → Längenprüfung vor dem Parsen,
Parsen im Executor; Traversal → Whitelist erweitern statt ersetzen; dateiweite Atomarität
gibt es bewusst nicht (O-3) → wiederholbarer Import + Dedupe als Gegenmaßnahme. **Store-Konsistenz
bei Mehrgruppen-Save:** ohne äquivalenten Snapshot bleiben bei einem Save-Fehler Teilgruppen im
In-Memory-Store und werden beim nächsten erfolgreichen Save persistiert — deshalb Snapshot über
alle N Gruppen (Store-Vertrag). **DoD:** AK 1–8; **REQ-HOM-132** (Service-Responses)
angelegt — 131 ist bereits durch die Migrations-Härtungen A-1…A-4 belegt (RVW-06); Notes 0.18.0
mit 💥-Hinweis.

---

### WP2 → 0.18.0 — Issues #28/#31/#33, Infra-Pin, B4, B2

**Ziel:** Nicht-Admin- und Frontend-Verhalten automatisiert geprüft, E2E reproduzierbar,
toter Code und BP-Schwellen-Inkonsistenz beseitigt.

| Datei | Stelle | Änderung |
|---|---|---|
| `docker-compose.e2e.yml` | `35` | `image: ghcr.io/home-assistant/home-assistant:2026.9.1` |
| `requirements_e2e.txt` | `8` | `playwright==1.47.0` (deckungsgleich mit `Dockerfile.e2e:9`) |
| `scripts/e2e_bootstrap.py` | `169–188` | Nicht-Admin `e2e-viewer` via WS `config/auth/create`, `group_ids: ["system-users"]` |
| `tests_e2e/` | neu | `test_permissions_e2e.py` (#28), `test_frontend_smoke_e2e.py` (#31) |
| `logic.py` | `337` | N-12: `csv_header_footer` entfernen (Review nennt `149–155` — veraltet) |
| `ws_api.py` (`binary_sensor.py` bleibt) | `545`, `559–566` (`89`) | B4/O-5: `_is_above` auf `>=` ziehen **und** Docstring korrigieren; `binary_sensor.py:89` unverändert |
| `README.md`, `docs/REQUIREMENTS.md` | — | B2: Statusdrift korrigieren; REQ-HOM-131 nachtragen |

**Schritte**

1. Infra-Pin: HA `2026.9.1` (nicht `stable`), `playwright==1.47.0`.
2. Bootstrap: nach dem Admin-Onboarding `e2e-viewer` per WS `config/auth/create` anlegen;
   idempotent (existiert → Login); Token weiter als Geheimnis behandeln.
3. #28: Login als `e2e-viewer`; `panel_data`/`list_history` funktionieren,
   `get_settings`/`export_csv`/`backup`/`restore_backup`/`import_csv` → `Unauthorized`.
4. #31: Playwright lädt Panel, Karte, Labs-Card; keine Console-Errors, Personenwahl sichtbar,
   Labor-Tab und Karte rendern. Smoke, keine Screenshot-Baselines.
5. N-12: `logic.csv_header_footer` entfernen (grep: 0 Referenzen). B4 (O-5 entschieden):
   `>=` ist führend — `binary_sensor.py:89` bleibt, `_is_above` (`ws_api.py:559–566`) wird von
   `>` auf `>=` gezogen und der Docstring („`>`-Vergleich“) angepasst; Call-Site `ws_api.py:545`
   bleibt; gemeinsamer Grenztest `sys == 140` / `dia == 90`.
6. B2: `REQUIREMENTS.md:3` („0.17.0 noch nicht veröffentlicht“, tatsächlich 0.17.2)
   korrigieren und **REQ-HOM-131 nachtragen** (A-1…A-4; belegt in
   `docs/superpowers/plans/2026-11-02-entity-id-migration.md:37, 3701`; `REQUIREMENTS.md`
   hat 0 Treffer). #71 nutzt **REQ-HOM-132**.

**Akzeptanzkriterien**

1. Compose referenziert exakt `2026.9.1`; E2E-Image zeigt `playwright==1.47.0`; der
   Bootstrap legt auf frischer Instanz Admin **und** `e2e-viewer` an (zweiter Lauf idempotent).
2. #28: admin-only WS-Kommandos → `Unauthorized`; Lese-Kommandos liefern Daten. #31: Panel,
   Karte, Labs-Card laden ohne Console-Error.
3. `grep -r csv_header_footer custom_components/ tests/` → 0; `pytest -q` grün. O-5: bei
   140/90 (`sys == sys_threshold` bzw. `dia == dia_threshold`) liefern Binary Sensor und
   Panel/WS **denselben** Wahrheitswert `true` (Test für `sys` und `dia`).
4. `REQUIREMENTS.md` nennt 0.17.2 als released und enthält REQ-HOM-131 (A-1…A-4); die
   Service-Responses stehen unter **REQ-HOM-132** und sind verlinkt.

**Tests:** E2E auf 8124 (#28, #31, Bootstrap-Idempotenz); Unit für N-12 und B4-Grenzfall —
auf der geteilten Instanz **keine** Automatisierung.
**Risiken:** Image-Pin veraltet → eigener Chore-Commit statt `stable`; `config/auth/create` ist
internes API → REST-Onboarding bleibt für Admin, WS mit klarer Fehlermeldung; Smoke flaky →
keine Screenshot-Baselines, Timeouts; N-12 bricht externen Import → vorher grep, kein
öffentliches API. **DoD:** AK 1–4; CI nutzt den gepinnten Stack.

---

### WP3 → 0.19.0 — Issue #73: 12 Marker, `metabolism`, Einheiten (D3), B3

**Ziel:** Katalog deckt die 12 Marker ab; Einheiten werden tolerant normalisiert, aber nie
stillschweigend falsch angenommen.

**Katalog (verbindlich, wörtlich aus Issue #73 — O-1 geschlossen):**

| key | Einheit (kanonisch) | Referenz | Kategorie | Alt-Einheit / Faktor |
|---|---|---|---|---|
| `mch` | pg | 27,0–33,5 | blood_count | – |
| `erythrocytes` | 10^12/L | 3,9–5,2 | blood_count | – |
| `hematocrit` | L/L | 0,355–0,455 | blood_count | % ×0,01 |
| `mchc` | g/dL | 31,5–36,0 | blood_count | – |
| `albumin` | g/L | 35–52 | liver | g/dL ×10 |
| `phosphate` | mmol/L | 0,87–1,45 | electrolytes | mg/dL ×0,3229 |
| `mcv` | fl | 80,0–99,0 | blood_count | – |
| `uric_acid` | mg/dL | 2,3–6,1 | kidney | µmol/L ×0,01681 |
| `alkaline_phosphatase` | U/L | 35–105 | liver | µkat/L ×60 |
| `ciclosporin` | ng/mL | laborabhängig (`ref_min`/`ref_max` = None) | drug_levels | – |
| `everolimus` | ng/mL | laborabhängig (`ref_min`/`ref_max` = None) | drug_levels | – |
| `hba1c` | mmol/mol | 29–42 | metabolism (neu, D1) | – |

Kanonisch ist **immer** die Spalte „Einheit (kanonisch)“; `alt_units` hält den Faktor
**gemeldet → kanonisch** (Beispiel: Hämatokrit 42 % → `42 × 0,01 = 0,42 L/L`). Frühere
Planstände führten `hematocrit`, `albumin`, `phosphate`, `uric_acid`,
`alkaline_phosphatase` mit umgekehrter Richtung (z. B. `hematocrit` kanonisch als `%`) —
das ist hiermit korrigiert.

| Datei | Stelle | Änderung |
|---|---|---|
| `const.py` | `175–185`, `192–485` | `metabolism` **vor** `other`; 12 `LAB_MARKERS` inkl. `alt_units`/`require_explicit_unit` |
| `logic.py` | `982–991` | `_norm_unit`-Härtung |
| `logic.py` | `1009–1073`, `1076–1109` | B3: `require_explicit_unit` aus den Options übernehmen (hart `False` in `1101`) |
| `__init__.py` / `ws_api.py` | `1125` / `1413` | Leerstring → `unit_required` |
| `ws_api.py` | `713` | Flag in den Panel-Payload |
| `www/*.js` | Karte/Panel | Vorwarnung; `health-o-mat-panel-admin.js:394–399, 410–411` **unverändert** |
| `strings.json`, `translations/de.json`, `translations/en.json` | — | `lab_<key>` (12), `lab_warning_metabolism` (alle drei Dateien) |

**Schritte**

1. **D1:** `metabolism` einfügen (`Metabolism`/`Stoffwechsel`).
2. **D2:** alle 12 Marker aus der Katalogtabelle in **einem** Commit-Satz anlegen — Werte
   wörtlich übernehmen (keine eigene Ableitung). `require_explicit_unit: true` für die sieben
   Marker aus D3 (`mchc`, `hematocrit`, `albumin`, `alkaline_phosphatase`, `phosphate`,
   `uric_acid`, `hba1c`); `ciclosporin`/`everolimus` bleiben ohne feste Referenz
   (`ref_min`/`ref_max` = None).
3. **D3 `alt_units`/`require_explicit_unit`:** Semantik wie `logic.py:1122–1139`
   (`canonical = reported * factor`); `true` für die sieben Marker, fehlt die Einheit →
   `unit_required` in Service **und** WS.
4. **D3 `_norm_unit`:** ASCII `u`→`µ` **nur** gegen ein µ-haltiges Ziel (schützt `U/l`);
   Superscript-Ziffern → ASCII, `10^12/l` == `10¹²/l`; `prozent` → `%`; `NFKC` + `strip` +
   `lower` bleiben.
5. **D3 Leerstring/UI:** zuerst `raw_unit = (raw_unit or "").strip() or None`, dann die
   bestehende `require_explicit_unit`-Prüfung (Pflicht-Marker → `unit_required`, optionale →
   kanonisch, konsistent zu `logic.py:1244`); Flag in `ws_api.py:713`; Karte/Panel warnen vor
   dem Absenden, Admin-UI unverändert.
6. **B3:** Custom-Marker dürfen `require_explicit_unit` setzen (Normalisierung,
   `effective_lab_markers`, Admin-Checkbox); Default `False`.

**Akzeptanzkriterien**

1. `LAB_CATEGORIES` enthält `metabolism` direkt vor `other`; `other` bleibt Fallback. Alle 12
   Marker sind auflösbar, haben `canonical_unit` und erscheinen als Sensor
   (`unique_id = {entry_id}_lab_{key}`, `sensor.py:510`).
2. `alt_units` rechnet `reported * factor` in die **kanonische** Einheit der Tabelle; geprüft
   wird gegen `round(..., 6)` mit Toleranz `1e-6` (`pytest.approx(..., abs=1e-6)`), nicht per
   Gleichheit auf Kurzwerte: `hematocrit` 42 % → 0,42 L/L · `albumin` 4,5 g/dL → 45 g/L ·
   `phosphate` 3,5 mg/dL → **1,13015** mmol/L · `uric_acid` 350 µmol/L → **5,8835** mg/dL ·
   `alkaline_phosphatase` 1,2 µkat/L → 72 U/L; `reported_value`/`reported_unit` bleiben; `unit=""` bei den sieben Pflicht-Markern
   → `unit_required`, bei optionalen → kanonische Einheit, kein Fehler.
3. `_norm_unit`: `umol/l` == `µmol/l`, `10¹²/L` == `10^12/L`, `Prozent` == `%`; `U/l` wird
   **nicht** zu `µ/l`. DOM-Assertion im Eingabe-Dialog: bei einem Pflicht-Marker ist der
   Warntext sichtbar (nicht nur der Payload-Key vorhanden); Custom-Marker mit
   `require_explicit_unit: true` erzwingt die Einheit (B3).
4. 29 Bestands-Keys unverändert **plus** 12 neue = **41 Keys** (Snapshot-Test); `pytest -q` grün,
   `ruff` clean, README-Katalogtabelle aktualisiert.

**Tests:** Unit-Tabelle `_norm_unit` (inkl. `U/l`-Negativfall), `convert_lab_value` je neuem
`alt_unit`, `require_explicit_unit` in Service/WS/Batch, Kategorie-Fallback,
29-Marker-Snapshot. E2E auf 8124: neuer Marker über Karte/Panel → Verlauf (WP0). Manuell:
deutsche Namen und `entity_id`-Pinning.
**Risiken:** `u`→`µ` verfälscht `U/l` → nur gegen µ-haltige Ziele falten + Negativtest;
Superscript vs. `^` → eine kanonische Vergleichsform; 12 Marker = viele Entities → `+12`
Sensoren und `+1` Binary pro Person in den Notes; falsche Referenzbereiche → 1:1 aus #73; B3
bricht Bestands-Importe → Default `False`. **DoD:** AK 1–4; Katalog-Doku + Übersetzungen;
Notes 0.19.0.

---

## 4. Release-Plan

| Release | Inhalt | Tag | `manifest.version` |
|---|---|---|---|
| 0.17.3 | WP0 (#70) | `v0.17.3` | `0.17.3` |
| 0.18.0 | WP1 + WP2 | `v0.18.0` | `0.18.0` |
| 0.19.0 | WP3 | `v0.19.0` | `0.19.0` |

`v` nur im Tag, Manifest ohne `v`, zeichenidentisch; Promotion = neuer Tag, nie verschieben;
kein MAJOR, kein `async_migrate_entry`-Bump (keine Entry-Daten-Migration).

**Notes:** Zusammenfassung (de/en) → ✨ New features → 💥 Breaking/Verhaltensänderungen →
Full-Changelog; zusätzlich `docs/RELEASE-NOTES-<version>.md`. **💥 0.18.0:** CSV-Import nur
noch für Administratoren (Service **und** WS) — Nicht-Admin-Automationen müssen auf einen
Admin-Kontext umstellen; `import_csv` antwortet neu mit `imported`. **Verhaltensänderung
0.18.0 (B4/O-5):** Die BP-Warnung greift künftig **ab Erreichen** der eingestellten Schwelle
(Default 140/90) — wer exakt auf der Schwelle misst, sieht jetzt eine Warnung; Binary Sensor
und Panel/WS liefern dasselbe Ergebnis. **💥 0.19.0:** 12 Sensoren + 1 Binary (`lab_warning_metabolism`) pro Person; keine
`unique_id`-Änderung.

Ablauf: Bump → Notes → Commit → Tag → **echtes GitHub Release** (`gh release create`); der HACS-Update-Test erst **nach** dem Release.

---

## 5. Reihenfolge und Abhängigkeiten

```
WP0 (0.17.3) ──► WP1 (0.18.0) ──► WP2 (0.18.0) ──► WP3 (0.19.0)
                     └── #28 braucht WP2-Infra (Schritte 1–2)
```

- **WP0 vor WP1:** beide ändern `ws_api.py`/`logic.py`; getrennte Releases vermeiden einen
  Misch-Diff. **WP1 vor WP2:** der #28-Test prüft das Import-Gate aus WP1; WP2-Infra
  (Schritte 1–2) muss vor dem #28-Test stehen.
- **WP3 zuletzt:** unabhängig, profitiert aber vom Verlauf (WP0) für den E2E-Beleg.
- **Keine sachlichen Blocker mehr** (O-1…O-5 sind entschieden, §7); die Reihenfolge bleibt
  allein wegen der `ws_api.py`/`logic.py`-Affinität sequenziell.
- **Datei-Affinitäten** (nie parallel): `ws_api.py` (WP0 `875–906`/`985–1000`/`1236–1263`,
  WP1 `132–143`, WP2 `559–566`, WP3 `713`/`1413`); `logic.py` (WP0 `919–938`, WP1
  `_LAB_ROW_ERROR_CODES`, WP3 `982–991`/`1009–1073`/`1101`/`1122–1139`); `__init__.py` (WP1
  `1322–1417`/`1562–1620`, WP3 `1125`); `const.py` nur WP3; `store.py` nur WP1.
- **Parallelisierbar:** WP2-Infra (`docker-compose.e2e.yml`, `requirements_e2e.txt`,
  `scripts/e2e_bootstrap.py`) berührt keinen Produktionscode.

---

## 6. Verifikation (I3-Strategie)

| Prüfung | Wo | Wie |
|---|---|---|
| Unit | lokal/CI | `python3 -m pytest -q` (Baseline 1605) |
| Lint/Syntax | lokal/CI | `ruff check .` + `ruff format --check .`; `compileall -q custom_components/health_o_mat` |
| HA-Config | Dev-Instanz | `/home/hermes/ha-test/bin/ha core check` |
| #28/#31, #70 | Compose 8124 | Playwright (`e2e-viewer`, Smoke Panel/Karte/Labs-Card); E2E `test_history_e2e.py` |
| Katalog/Einheiten | Compose + Unit | E2E-Erfassung + Unit-Tabelle |
| Manuelle Abnahme | geteilte Instanz | `bin/sync`, Panel/Card im Browser, deutsche Namen, `entity_id`-Pinning |

**Geteilte Instanz:** nur manuelle Abnahme nach `bin/sync` — Sichtprüfung von Entities,
`friendly_name`s und `entity_id`s; keine Schreib-Tests, keine Sprachumschaltung
(instanzweiter Blast-Radius), kein `bin/reset`. **Nicht testbar:** HACS-Update-Pfad (erst
nach dem Release) · reale Nicht-Admin-Nutzer auf der geteilten Instanz ·
Produktionsdatenmengen (nur synthetisch) · HA-Versionen außer 2026.9.1.

---

## 7. Offene und zurückgestellte Punkte (D10)

| # | Punkt | Status | Grund | Wiederaufnahme |
|---|---|---|---|---|
| B1 | REQ-HOM-127 | zurückgestellt | eigener Plan; berührt den D6-Vertrag | später **additiv** via `errors_detail` |
| B2 | Doku-Statusdrift + REQ-HOM-131 | **0.18.0** | `REQUIREMENTS.md:3` nennt 0.17.0 als nicht released; REQ-HOM-131 ist im Migrationsplan (`docs/superpowers/plans/2026-11-02-entity-id-migration.md:37, 3701`) A-1…A-4 zugeordnet, in `REQUIREMENTS.md` aber mit 0 Treffern | mit WP2: Status korrigieren, REQ-HOM-131 nachtragen |
| B3 | Custom-Marker-`require_explicit_unit` | **0.19.0** | gehört zur Einheiten-Härtung | mit WP3 |
| B4 | BP-Schwellen `>=`/`>` | **Fix 0.18.0 (O-5 entschieden)** | zwei Pfade warnten an der Grenze unterschiedlich | `>=` führend; Panel/WS zieht nach (§3 WP2) |
| B5 | HbA1c in `%` (DCCT) | **nur Issue** | eigenständige Alt-Einheiten-Entscheidung | eigenes Issue nach stabilem 0.19.0 |
| B6/B7 | — | zurückgestellt | ohne Inhalt benannt | **offen: Konkretisierung** |
| B8 | `;`/UTF-8 | **dokumentieren 0.18.0** | Nutzer muss wissen, warum `cp1252`/`,` scheitert | mit WP1 |
| B9 | Beobachtung an `agent-meta-manager` | **melden, nicht patchen** | Framework-Thema, nicht Repo-Scope | Meldung durch den Orchestrator |
| B10 | Abgleich mit #31 | **0.18.0** | Überschneidung der Frontend-Prüfungen | mit WP2 |

**Entschiedene Punkte O-1…O-5 — alle geschlossen, keine Blocker:**

| # | Entscheidung | Umsetzung / Beleg |
|---|---|---|
| O-1 | **geschlossen** — die 12 Marker sind in Issue #73 vollständig belegt | Tabelle 1:1 in WP3 übernommen (kanonische Einheit = linke Spalte, `alt_units` = gemeldet→kanonisch) |
| O-2 | **A** — `export_csv` liefert `{filename, filenames, rows, dataset}`; `filename` = erste Datei, `rows` = Summe | WP1 Schritt 1 + AK 1; `exporter.py:171–183` |
| O-3 | **B** — atomar je Bericht + ein Speichervorgang je Dataset; Restfall über wiederholbaren Import | WP1 Schritt 4 + AK 5; Dedupe `importer.py:573–605` |
| O-4 | **A** — Cap 1000 für jedes explizit gesetzte `limit`, darüber `invalid_format` (kein stilles Kappen) | WP0 Schritt 3 + AK 4 |
| O-5 | **A** — `>=` ist führend; `binary_sensor.py:89` bleibt, Panel/WS zieht nach | WP2 Schritt 5 + AK 3; Verhaltensänderung in §4 |

---

## 8. Risiko- und Threat-Model

**1. Was baust du?** Gesundheitsdaten (Labor, BD, Wohlbefinden, Trinkmengen) pro Person im
HA-Store, erreichbar über Services, WebSocket-API und Web-Panel; neu: optionale
Service-Antworten, WS-CSV-Upload (`filename`/`content`, 2 MiB), admin-gegateter Import.

**2. Was kann schiefgehen?**

| Risiko | Szenario |
|---|---|
| Ungeschützter **Service**-Zugriff | `import_csv` ist heute **nicht** admin-gegated (`__init__.py:1334`) — ein WS-Import existiert noch nicht; `include_voided`/`report_ref` legen zudem gelöschte Werte für alle Angemeldeten offen |
| Upload-DoS | 2 MiB `content` wird im Event-Loop geparst und blockiert HA |
| Pfad-Escape | `filename` mit `../`/Symlink liest/schreibt außerhalb der privaten Ordner |
| Stille Fehlinterpretation | `,`/`cp1252`-CSV wird als `;`/UTF-8 gelesen → falsche Werte; `mchc`/`hba1c` ohne Einheit stillschweigend kanonisch |
| Trace-Offenlegung | Response mit Messwerten landet im Automation-Trace/Log |

**2a. Akzeptiertes Restrisiko:** 0.17.3 geht **ohne** Import-Gate raus (WP0 enthält nur #70).
Gegenmaßnahme bis 0.18.0: Warnhinweis in `README.md`/`services.yaml`, dass `import_csv` bis
dahin von jedem HA-Nutzer aufrufbar ist; das Gate folgt in WP1.

**3. Was tust du dagegen?** Import admin-only auf beiden Pfaden (Service +
`ADMIN_ONLY_COMMANDS` + `is_admin_connection` fail-closed) · Längenprüfung vor dem Parsen,
Parsen im Executor · `safe_import_path`-Whitelist (Import-/Export-Ordner) mit
Traversal-Tests · nur `;` und UTF-8 (BOM-tolerant), kein `cp1252` · Responses nur mit
Counts/Dateinamen · `require_explicit_unit`, Leerstring → `unit_required` · Pagination
(Labor 200), `report_ref` nur auf Anfrage · keine Exporte nach `/config/www`.

**4. Konsequenzen.** Ein Leck gibt Gesundheitsdaten im eigenen Haushalt preis (Vertrauens-,
kein externer Dienstleister-Schaden). Ein Upload-DoS legt HA für alle Integrationen lahm;
falsche Einheiten erzeugen falsche Langzeitstatistiken. Die Maßnahmen sind fail-closed und an
den Grenzen getestet (2 MiB, `;`/`,`, `U/l`, `threshold`).

---

## 9. Traceability

Jede Zeile ist ein Akzeptanzkriterium (§3), nicht ein Arbeitspaket (RVW-12).

| AK-ID | Issue / REQ | Test |
|---|---|---|
| WP0-1 | #70 | `tests/test_ws_api.py` (Felder, `include_voided`, `report_ref`), `tests/test_logic.py` (Alias) |
| WP0-2 | #70 | `tests/test_ws_api.py` (`limit`/`offset`/`has_more`, `limit=None` → `false`) |
| WP0-3 | #70 | `tests/test_logic.py` (Instant-Vergleich), `tests/test_ws_api.py` (`since` `+02:00` vs. `Z`) |
| WP0-4 | #70 / **O-4** | `tests/test_ws_api.py` (Cap 1000: `1000` ok, `1001` → `invalid_format`, alle vier Kinds) |
| WP0-5 | #70 | `tests/test_ws_api.py`, `tests/test_lab_services.py` (`void`/`restore`, `coordinator.data`) |
| WP0-6 | #70 | `tests/test_lab_services.py` (`allowed` ohne Doppelnennung); `pytest`/`ruff` |
| WP1-1 | #71 / **REQ-HOM-132**, **O-2** | `tests/test_import_backup.py` + `tests/test_wave_a.py` (Response-Keys inkl. `filenames`, `filename == filenames[0]`, `rows` = Summe) |
| WP1-2 | #71 / REQ-HOM-132 | `tests/test_import_backup.py` (`errors`-Cap, Exceptions) |
| WP1-3 | #72 | `tests/test_ws_api.py` („genau eines“, 2 MiB, Gate) |
| WP1-4 | #72 | `tests/test_import_backup.py` (Export-Ordner, `;`/UTF-8) |
| WP1-5 | #72, **O-3** | `tests/test_import_backup.py` (Bericht nie halb geschrieben, zweiter Lauf ohne Duplikate), `tests/test_store.py` (ein Save je Dataset, Snapshot-Rollback über N Gruppen) |
| WP1-6 | #72, **RVW2-02** | `tests/test_lab_services.py` (Einzel-Add: gleiches `ts`/Marker, neuer Wert → `duplicate_marker`, kein Teilzustand) |
| WP1-7 | #71 / REQ-HOM-132 | `tests/test_report.py` (`weekly_report` je Person: A `true`, B `false`) |
| WP1-8 | alle | CI (`pytest`, `ruff`, `REQUIREMENTS.md`/`services.yaml`) |
| WP2-1 | #28, #31 | `tests_e2e/test_permissions_e2e.py`, `scripts/e2e_bootstrap.py` (Idempotenz) |
| WP2-2 | #28, #31 | `tests_e2e/test_permissions_e2e.py`, `tests_e2e/test_frontend_smoke_e2e.py` |
| WP2-3 | #33 / N-12, B4 / **O-5** | `tests/test_logic.py` (Import schlägt fehl, wenn Funktion zurückkehrt), `test_binary_sensor.py` + `test_ws_api.py` (140/90 → beide `true`) |
| WP2-4 | B2 / REQ-HOM-131 | Doku-grep auf `0.17.2` und `REQ-HOM-131` |
| WP3-1 | #73 / REQ-HOM-122 | `tests/test_logic.py` (Katalog, `unique_id`-Schema), `tests/test_sensor.py` |
| WP3-2 | #73 / REQ-HOM-122 | `tests/test_logic.py` (`alt_units`, `unit=""`) |
| WP3-3 | REQ-HOM-122 | `tests/test_logic.py` (`_norm_unit`, `U/l`), `tests_e2e/test_lab_values_e2e.py` (DOM-Warnung) |
| WP3-4 | REQ-HOM-122/123/124/125 | `tests/test_sensor.py` (29 Bestands-Keys + 12 neue = 41), `pytest`/`ruff`; REQ-HOM-127 → B1, REQ-HOM-129/130 bleiben grün |

---

## 10. Branch-Namen

`fix/70-lab-values-void-id` (WP0, Basis `main`) · `chore/28-31-ci-and-e2e-hardening` (WP2) ·
`feat/71-72-service-responses-and-import-upload` (WP1) · `feat/73-lab-catalog-and-units`
(WP3) · `refactor/33-n12-dead-code` (N-12, kann in WP2 aufgehen). Jeder Branch basiert auf
dem Merge des Vorgängers. Conventional Commits, Englisch, max. 72 Zeichen in Zeile 1.

**DoD je WP (RVW-12):** vor dem Commit Secret-Scan der gestagten Änderungen (Befund blockiert
den Commit); Commit-Subject **BOM-frei**, beginnt an Byte 0 mit dem Conventional-Commit-Typ.
Push, Tag und Release bleiben beim `git`-Agenten.

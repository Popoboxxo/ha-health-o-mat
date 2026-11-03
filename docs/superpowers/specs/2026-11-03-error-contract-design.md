# Design: Fehlercode-/i18n-Vertrag für Services und WS (REQ-HOM-127)

**Status:** APPROVED (2026-11-03, concept-reviewer) · **Datum:** 2026-11-03 · **Anker-Basis:** `main` @ `79349db`
**Zeilenanker dieses Dokuments:** Arbeitsbaum-Stand 2026-11-03. Der Statistik-
Cleanup (`__init__.py:879-1005`) verschiebt jede `__init__.py`-Zeile hinter 1005
um **netto +46** (an allen 29 Service-Ankern gemessen). §7.1 nennt deshalb
`Anker → WT`; alle übrigen `__init__.py`-Angaben sind bereits WT-Zeilen.
`ws_api.py` und `logic.py` sind **nicht** gedriftet.
**Bezug:** `docs/PLAN-AUDIT-2026-11-03.md` §WP-A (inkl. Entscheidung **D-3**),
`docs/REQUIREMENTS.md` REQ-HOM-127 (`:1577-1600`) und REQ-HOM-132,
`docs/SERVICE-RESPONSES.md`, `docs/PLAN-OPEN-ISSUES.md:445`,
`docs/superpowers/specs/2026-11-01-lab-values-batch-and-visibility-design.md` §2.4
**Gate:** Dieses Dokument ist der Konzept-Gate-Beitrag zu WP-A; es enthält **keinen**
Task-Plan, keine `pipeline_stages` und keine Implementierung.

---

## 1. Kontext

Zwei Fehlerklassen im selben Produkt (Audit-Befund **F-08**):

- Die **Labor-Batch-Pfade** (REQ-HOM-123) liefern bereits strukturiert
  `{code, params, message}` — gebaut von `logic.lab_report_error`
  (`logic.py:1195`), transportiert von `ws_api._lab_error_result`
  (`ws_api.py:1646`) als Ergebnis-Envelope `{"ok": false, "error": …}`.
- Die **älteren Pfade** (Trinken, Blutdruck, Wohlbefinden, Einzel-Laborwert,
  Historie/Undo, Personenauflösung) werfen deutsche Prosa:
  `ServiceValidationError("amount_ml muss zwischen 1 und 10000 liegen")`
  (`__init__.py:1234`) bzw. `connection.send_error(msg_id, "invalid_format",
  "unit_required")` (`ws_api.py:1603`). Der Code steckt dort bestenfalls im
  Meldungstext, nie in einem Feld.

Damit gibt es heute **keinen** maschinenlesbaren Fehlercode außerhalb des
Batches und **keine** Lokalisierung der Meldungstexte: die deutsche Prosa steht
im Produktionscode und wird auch auf einer englischen Instanz deutsch angezeigt.

---

## 2. Problem

1. **Nicht unterscheidbar:** Ein Client kann `unknown_marker` nicht von
   `unit_required` trennen, ohne deutsche/englische Teilstrings zu matchen.
   Ein `send_error`-`code` ist immer `invalid_format` — die Fachursache fehlt.
2. **Nicht lokalisierbar:** Die Texte liegen als Literale im Code; `strings.json`
   und `translations/{de,en}.json` kennen keine `exceptions`-Sektion.
3. **Zwei Formate:** Batch-Envelope vs. Prosa-Exception — jede UI-Stelle braucht
   einen Sonderfall, jede neue Fehlerstelle erfindet ihren Text neu.
4. **PII/Log-Risiko:** Freitext-Meldungen enthalten Personen-/Eingabewerte
   (`Person 'Caro' nicht gefunden`, `__init__.py:1059`), die so in HA-Logs und
   in Issue-Anhänge wandern.

---

## 3. Ziel

Ein **Katalog** von stabilen, snake_case-Fehlercodes mit deklarierten `params`
und einer de/en-Übersetzung — ausgeliefert über **drei Projektionen desselben
Objekts**: Service-Exception, WS-Fehler, Batch-Envelope. `code` ist die
Identität; die vorhandenen Antwort-Verträge (REQ-HOM-132, REQ-HOM-123) bleiben
**additiv** unverändert.

---

## 4. Nicht-Ziele

- **Kein** Umbau von Transport-/Entry-/Berechtigungsfehlern (§5.7).
- **Keine** Änderung an REQ-HOM-132: die fünf Verwaltungs-Services behalten
  exakte Key-Mengen, `errors` ≤ 20, Fachfehler bleiben Exceptions.
- **Keine** neuen Services, WS-Kommandos oder Antwort-Keys.
- **Keine** Neu-Übersetzung von Entity-Namen, Service-Beschreibungen oder
  Config-Flow-Texten (REQ-HOM-107/122 bleiben unberührt).
- **Kein** Umbau der Fehlertexte von `button.py`/`text.py` (kein Service-/WS-
  Pfad, §7.6) und von `restore.py`/`exporter.py`/`importer.py` (§5.7, §13 O-5).
- **Kein** Verhaltensumbau der Validierung selbst: welcher Fehler wann gewinnt,
  bleibt exakt wie heute.

---

## 5. Der Vertrag

### 5.1 Kanonisches Fehlerobjekt (HA-frei, eine Quelle)

`logic.build_error(code, params) -> {"code": str, "params": dict, "message": str}`

```python
{"code": "unit_required",
 "params": {"row": 3, "marker": "kreatinin"},
 "message": "unit_required (row=3, marker=kreatinin)"}
```

Regeln:

| Feld | Regel |
|---|---|
| `code` | snake_case, stabil, **nie umbenennen** (gleiche Regel wie `unique_id`). Ein Rename ist ein Breaking Change. |
| `params` | JSON-fähig (`str`/`int`/`bool`/`None`), Schlüssel pro Code im Katalog deklariert; Roh-Echos auf 64 Zeichen gekürzt. |
| `message` | Wird **ausschließlich aus dem per-Code-Template** `ERROR_SPECS[code]["message"]` gerendert (sprachneutral, ASCII) — **nie** durch Laufzeit-Interpolation aller `params`. Das Template enthält den Code und optional `{platzhalter}` nur für dort deklarierte `params`. **`{value}` ist ausschließlich für `invalid_ts` erlaubt** (aufruferseitiger Zeitstempel). Für `invalid_value` benennt der Text das Problem **ohne** den Wert (z. B. `invalid_value (row=3, marker=kreatinin)`); `params.value` bleibt als Maschinen-Feld erhalten (`RAW_ECHO_CODES`), wird aber **weder** im Template **noch** im Übersetzungstext gerendert. Nie leer, nie deutsche/englische Prosa, nie ein Messwert aus dem Store. |
| `value` (Roh-Echo) | **Nur** für die Codes in `RAW_ECHO_CODES` = {`invalid_ts`, `invalid_value`} — eine Konstante im Katalog, sonst kein `params`-Schlüssel. `invalid_ts.value` ist der **aufruferseitige Zeitstempel** (kein Gesundheitswert, im `message`-Template **und** im Übersetzungstext erlaubt); `invalid_value.value` ist der bereits ausgelieferte Roh-Echo von REQ-HOM-123 §2.4 (Messwert, **weder** im `message`-Template **noch** im Übersetzungstext **gerendert**). Beide ≤ 64 Zeichen (§9.2 Regel 4). |

`logic.lab_report_error` (`logic.py:1195`) bleibt als öffentlicher Name
bestehen und delegiert an `build_error`; `_LAB_ROW_ERROR_CODES` (`logic.py:1184`)
geht im Katalog auf. Der Katalog ist eine **HA-freie** Konstante in `logic.py`
(damit ohne HA-Paket testbar); die zwei dünnen HA-Adapter liegen in einem neuen
Modul `errors.py` (§5.2/§5.3). `errors.py` hält `__init__.py`/`ws_api.py` klein
(WP-D-Trigger T-1).

### 5.2 Kanal A — Service (`ServiceValidationError`)

```python
raise errors.validation_error("amount_out_of_range", {"min": 1, "max": 10000})

# entspricht:
raise ServiceValidationError(
    build_error(...)["message"],                      # sprachneutraler Fallback
    translation_domain="health_o_mat",
    translation_key=code,                             # == code
    translation_placeholders={k: str(v) for k, v in params.items()},
)
```

- **Beide** Angaben: der Positions-Parameter hält `str(err)` auch ohne geladene
  Übersetzung lesbar (Logs, sehr frühe Fehler); `translation_*` macht den Fehler
  für die HA-**Anzeige** lokalisierbar (Logs bleiben beim Fallback, §8).
- HA 2026.9.1 (`homeassistant/exceptions.py`) akzeptiert
  `translation_domain`/`translation_key`/`translation_placeholders`; der
  generische `call_service`-Kommando-Pfad gibt sie im Fehlerobjekt mit aus
  (`homeassistant/components/websocket_api/commands.py`, `handle_call_service`).
  Quellenlage im Anhang §12.1.

### 5.3 Kanal B — eigenes WS-Kommando (`connection.send_error`)

```python
errors.send_ws_error(connection, msg["id"], "invalid_format", "unknown_marker", {"marker": raw})

# entspricht:
connection.send_error(
    msg_id,
    "invalid_format",                 # HA-Transportcode — UNVERÄNDERT
    "unknown_marker (marker=…)",      # sprachneutraler Fallback
    translation_domain="health_o_mat",
    translation_key="unknown_marker", # == code
    translation_placeholders={"marker": "…"},
)
```

- Der `code` des Envelopes bleibt der **HA-Fehlercode** (`invalid_format`,
  `not_found`, …). Er wird **nicht** mit dem Fachcode überladen: HA und das
  Frontend behandeln ihn als Fehlerklasse, und ein Overload würde die
  Kompatibilität der bestehenden Clients brechen.
- Der Fachcode landet in `translation_key` — das ist derselbe Wert wie `code`
  im kanonischen Objekt.
- `connection.send_error(..., translation_domain=, translation_key=,
  translation_placeholders=)` existiert in HA 2026.9.1 (§12.1) und ist für
  abweichende Signaturen fail-open zu wrappen: kennt die installierte Version
  die Kwargs nicht, sendet `errors.send_ws_error` den Fallback ohne sie.

### 5.4 Kanal C — Batch-Envelope (Referenz, unverändert)

```python
connection.send_result(msg["id"], {"ok": False, "error": {"code", "params", "message"}})
```

- Form und Keys bleiben **exakt** wie in REQ-HOM-123 §2.4 dokumentiert und in
  0.18/0.19 ausgeliefert. Kein neues Pflichtfeld, keine Umbenennung.
- **Entschieden:** Die Envelope bleibt `{code, params, message}` und bekommt
  **keine** `translation_*`-Keys (§4: keine neuen Antwort-Keys; §7.3). Die
  Lokalisierung des Batches passiert ausschließlich clientseitig aus
  `code` + `params` (§5.6).
- Der Batch ist damit die **strukturierte** Projektion; Service/WS sind die
  **HA-native** Projektion. Beide tragen denselben `code` und dieselben `params`.

### 5.5 Autorität

| Frage | Antwort |
|---|---|
| Was ist der Code? | `code`. Er ist die Katalog-Identität und wird nirgends abgeleitet. |
| Wo steht er im Service-/WS-Pfad? | In `translation_key` (identischer String). |
| Was sind die Params? | `params`; `translation_placeholders` ist die String-Projektion davon (`str(v)`), weil HA `dict[str, str]` erwartet. |
| Was ist `message`? | Nur Fallback. Nie autoritativ, nie die einzige Information. |

Konvention für Clients: **`translation_key` hat Vorrang vor `code`**, wenn beide
vorhanden sind (Service-/WS-Pfad); im Batch gibt es nur `code`.

### 5.6 Client-Lokalisierung (Card/Panel)

```
tError(err):
  key  = err.translation_key || err.code
  vars = err.translation_placeholders || err.params || {}
  text = catalog[key].message            # HA-Übersetzung, §9
  return text ? interpolate(text, vars) : (err.message || key)
```

- Ein unbekannter Code fällt auf `message` zurück, danach auf den Code — nie
  eine leere Zeile, nie ein roher `ui_…`-Key.
- Der Katalog wird über `frontend/get_translations` mit
  `category: "exceptions"` geladen (Kategorie ist in HA dokumentiert, §12.1).
  Der bestehende Loader `www/health-o-mat-i18n.js` (aktuell nur
  `category: "common"`, `:28`, `:107-112`) bekommt einen zweiten, pro Sprache
  gecachten Ressourcen-Satz; die Card hat ihren eigenen Inline-Loader
  (`www/health-o-mat-card.js:150-260`) und wird identisch erweitert.
- `interpolateUi` (`health-o-mat-i18n.js:74-84`) wird wiederverwendet; die
  Platzhalter-Syntax ist absichtlich identisch zu HA (`{name}`).

### 5.7 Abgrenzung: was **nicht** migriert wird

| Klasse | Beispiele | Bleibt |
|---|---|---|
| Transport/Format am WS-Rand | voluptuous-Schemafehler, unbekannte Message-ID | unverändert |
| Entry/Person nicht geladen | `_send_entry_error` (`ws_api.py:800-806`), `panel_data` (`:1280`) | unverändert |
| Berechtigung | `_send_unauthorized` (`ws_api.py:1928-1934`), kein angemeldeter Benutzer (`ws_api.py:1889`), `__init__.py:1169/1172` | unverändert |
| Umgebung/I/O | `export_failed`, `backup_failed`, `restore_failed`, `import_failed` | unverändert (nur Relais, §7.7) |
| Verwaltungs-Fachfehler mit eigenem Grundkatalog | `RestoreError` (`__init__.py:1569-1570`), `exporter.py:112,185`, `importer.py:731,750,759,761,766`, `backup.py:211` | unverändert (REQ-HOM-132) |
| Entity-Aktionen | `button.py:112,131,150`, `text.py:51` | unverändert (§13 O-6) |

---

## 6. Code-Katalog (Vorschlag, eine Quelle)

`params`-Spalte: **fett** = Pflicht, *kursiv* = optional (nur im Batch bzw. nur
im Einzelpfad).

| # | Code | params | Kanäle | ersetzt (heute) |
|---|---|---|---|---|
| 1 | `no_person_configured` | — | S, W | „Keine Health-O-Mat-Person eingerichtet" |
| 2 | `person_ambiguous` | **count** | S, W | „Mehrere Personen vorhanden (…) — bitte 'person' angeben" |
| 3 | `person_not_found` | — | S, W | „Person '…' nicht gefunden" |
| 4 | `invalid_ts` | **value** | S, W, B | `ENTRY_TS_INVALID_MESSAGE` |
| 5 | `invalid_history_kind` | **kind**, **allowed** | S, W | „Unbekannter kind '…'" |
| 6 | `missing_item_id` | — | S | „id fehlt" |
| 7 | `entry_not_found` | **kind** | S, W | „Eintrag '…' nicht gefunden oder …" |
| 8 | `invalid_undo_kind` | **kind**, **allowed** | S, W | „Unbekannter kind '…' — erlaubt: …" (Undo) |
| 9 | `undo_not_supported` | **kind**, **allowed** | S | „Undo ist für '…' nicht verfügbar" |
| 10 | `nothing_to_remove` | **kind** | S, W | „Keine … zum Entfernen" |
| 11 | `limit_out_of_range` | **min**, **max** | W | „limit muss zwischen 1 und 1000 liegen" |
| 12 | `offset_invalid` | — | W | „offset muss >= 0 sein" |
| 13 | `invalid_since` | **expected** | W | „since muss ein ISO-Zeitpunkt … sein" |
| 14 | `amount_out_of_range` | **min**, **max** | S, W | „amount_ml muss zwischen 1 und 10000 liegen" |
| 15 | `bp_out_of_range` | **min**, **max** | W | „sys/dia müssen zwischen 40 und 260 liegen" |
| 16 | `wellbeing_target_missing` | **max** | S, W | „Entweder 'status' oder 'score' angeben" |
| 17 | `wellbeing_score_invalid` | **min**, **max** | S, W | „Ungültiger Wohlbefinden-Score '…'" |
| 18 | `wellbeing_key_unknown` | **allowed** | S, W | „Ungültiger Wohlbefinden-Status/Key" |
| 19 | `unknown_marker` | ***row***, **marker** | S, W, B | „unknown_marker" (Batch: identisch) |
| 20 | `unit_required` | ***row***, **marker** | S, W, B | „unit_required" |
| 21 | `invalid_value` | ***row***, **marker**, *value* | S, W, B | „invalid_value" |
| 22 | `unsupported_unit` | ***row***, **marker**, **unit** | S, W, B | „unsupported_unit" |
| 23 | `duplicate_marker` | ***row***, **marker**, *first_row* | S, W, B | „duplicate_marker …" |
| 24 | `empty_report` | — | S, B | „empty_report" |
| 25 | `too_many_rows` | **count**, **limit** | S, B | „too_many_rows (201 > 200)" |
| 26 | `no_active_report` | **ts** | S, W, B | „no_active_report" |
| 27 | `no_active_value` | **marker** | S, W | „Kein aktiver Wert für Marker '…'" (WS-Draht: `no_active_value`, `ws_api.py:1776`) |
| 28 | `invalid_setting` | **field** | W (Rand) | „Ungültige Einstellung '…': …" |
| 29 | `unknown_dataset` | **allowed** | W (Rand) | „Unbekannter Datensatz: …" |
| 30 | `confirm_mismatch` | — | W (Rand) | „Die Bestätigung stimmt nicht …" |
| 31 | `invalid_import_source` | — | W (Rand) | „Genau eines von 'filename' oder 'content'" |
| 32 | `content_not_utf8` | — | W (Rand) | „content ist kein gültiges UTF-8" |
| 33 | `content_too_large` | **max** | W (Rand) | `ERR_CONTENT_TOO_LARGE` (`ws_api.py:191`) |
| 34 | `config_flow_unavailable` | — | W (Rand) | „Config-Flow-Start wird von dieser Home-Assistant-Version nicht unterstützt" (`ws_api.py:2238`) |
| 35 | `config_flow_failed` | — | W (Rand) | „Config-Flow konnte nicht gestartet werden: {err}" (`ws_api.py:2248`) — die Roh-Exception bleibt im Log (`:2244`), **nicht** in `params` (§14) |

Kanäle: **S** = Service, **W** = eigenes WS-Kommando, **B** = Batch-Envelope.
„Rand" = Verwaltungs-/Admin-Pfad (§13 O-1).

`value` (Zeile 4 und 21) ist das einzige Roh-Echo (`RAW_ECHO_CODES`, §5.1). Nur
`invalid_ts` darf `{value}` im `message`-Template und im Übersetzungstext
referenzieren; `invalid_value` führt `value` ausschließlich als Maschinen-Feld,
ohne Textbezug. Alle übrigen `params` sind strukturell (`row`, `first_row`,
`count`, `limit`, `min`, `max`, `marker`, `unit`, `kind`, `ts`, `expected`,
`field`, `allowed`).

---

## 7. Bestandsaufnahme (Implementierungsfläche)

Alle Zeilen sind **Arbeitsbaum**-Zeilen (2026-11-03). **Kern** = 0.21.0, **Rand** =
gleicher Katalog, separate Testzeile (§13 O-1), **T** = unverändert.

Zählbasis `send_error`: **40** Aufrufstellen in `ws_api.py` (42 Texttreffer,
davon zwei Docstring-Nennungen `:1584` und `:1657`) — **32 migriert** (§7.2),
**8 code-unverändert** (§5.7): `:802`, `:1280`, `:1889`, `:1930` bleiben
vollständig unverändert; `:2212`, `:2295`, `:2381`, `:2404` bleiben **code-
unverändert**, bekommen aber das Transport-Relais (§7.7). `__init__.py` hat
**29** migrierte Service-Exceptions plus **3** unveränderte (`T` unten).

### 7.1 Service (`custom_components/health_o_mat/__init__.py`) — 29 Stellen

`Anker → WT` = Zeile in `main@79349db` → Zeile im Arbeitsbaum (Drift +46).

| Zeile (Anker → WT) | Stelle | Code |
|---|---|---|
| 1002 → 1048 | `get_runtime_data` — keine Person | `no_person_configured` |
| 1006 → 1052 | `get_runtime_data` — mehrere Personen | `person_ambiguous` |
| 1013 → 1059 | `get_runtime_data` — Person unbekannt | `person_not_found` |
| 1095 → 1141 | `_service_entry_ts` (add_drink, add_blood_pressure, add_lab_value, add_lab_report, remove_lab_report, set_wellbeing) | `invalid_ts` |
| 1152 → 1198 | `_set_entry_state` — kind unbekannt | `invalid_history_kind` |
| 1157 → 1203 | `_set_entry_state` — id fehlt | `missing_item_id` |
| 1169 → 1215 | `_set_entry_state` — kein Treffer | `entry_not_found` |
| 1188 → 1234 | `add_drink` — Menge | `amount_out_of_range` |
| 1238 → 1284 | `add_lab_value` — Marker | `unknown_marker` |
| 1245 → 1291 | `add_lab_value` — Pflicht-Einheit | `unit_required` |
| 1248 → 1294 | `add_lab_value` — Wert | `invalid_value` |
| 1252 → 1298 | `add_lab_value` — Einheit | `unsupported_unit` |
| 1274 → 1320 | `add_lab_value` — Dedupe | `duplicate_marker` |
| 1291 → 1337 | `add_lab_report` — ts (Wrapper) | `invalid_ts` |
| 1304 → 1350 | `add_lab_report` — Zeilenfehler, **heute nur `error["message"]`** | Code aus `validate_lab_report_rows` |
| 1318 → 1364 | `add_lab_report` — Dedupe | `duplicate_marker` |
| 1334 → 1380 | `remove_lab_report` — ts (Wrapper) | `invalid_ts` |
| 1338 → 1384 | `remove_lab_report` — ts fehlt | `invalid_ts` |
| 1353 → 1399 | `remove_lab_report` — kein Treffer | `no_active_report` |
| 1365 → 1411 | `set_wellbeing` — status/score fehlen | `wellbeing_target_missing` |
| 1369 → 1415 | `set_wellbeing` — Score | `wellbeing_score_invalid` |
| 1373 → 1419 | `set_wellbeing` — Status | `wellbeing_key_unknown` |
| 1398 → 1444 | `remove_last_entry` — kind | `invalid_undo_kind` |
| 1406 → 1452 | `remove_last_entry` — kein Undo | `undo_not_supported` |
| 1417 → 1463 | `remove_last_entry` — nichts zu entfernen | `nothing_to_remove` |
| 1437 → 1483 | `remove_last_lab_value` — Marker | `unknown_marker` |
| 1447 → 1493 | `remove_last_lab_value` — kein Wert | `no_active_value` |
| 1551 → 1597 | `weekly_report` — kein Store | `no_person_configured` |
| 1562 → 1608 | `weekly_report` — keine Ziele | `no_person_configured` |

**T (unverändert):** `1123 → 1169`, `1126 → 1172` (Berechtigung),
`1524 → 1569-1570` (`RestoreError`).
Sie stehen in der WP-A-Zeilenliste, fallen aber unter die AK „fehlende
Berechtigung behält ihre bisherige Form" (`PLAN-AUDIT §WP-A Schritt 5`).

### 7.2 Eigenes WS-Kommando (`custom_components/health_o_mat/ws_api.py`) — 32 Stellen (von 40 `send_error`-Aufrufen)

| Zeile | Stelle | Code | Klasse |
|---|---|---|---|
| 1303 | `book_drink` — ml | `amount_out_of_range` | Kern |
| 1313 | `book_drink` — ts | `invalid_ts` | Kern |
| 1338 | `undo_last` — kind | `invalid_undo_kind` | Kern |
| 1351 | `undo_last` — nichts zu entfernen | `nothing_to_remove` | Kern |
| 1375 | `list_history` — kind | `invalid_history_kind` | Kern |
| 1388 | `list_history` — limit | `limit_out_of_range` | Kern |
| 1398 | `list_history` — offset | `offset_invalid` | Kern |
| 1407 | `list_history` — since-Typ | `invalid_since` | Kern |
| 1417 | `list_history` — since-Wert | `invalid_since` | Kern |
| 1468 | `void/restore_entry` — kind | `invalid_history_kind` | Kern |
| 1484 | `void/restore_entry` — kein Treffer | `entry_not_found` | Kern |
| 1534 | `save_measurement` — sys/dia | `bp_out_of_range` | Kern |
| 1545 | `save_measurement` — ts | `invalid_ts` | Kern |
| 1574 | `_resolve_lab_marker_or_error` | `unknown_marker` | Kern |
| 1603 | `add_lab_value` — Einheit | `unit_required` | Kern |
| 1608 | `add_lab_value` — Wert | `invalid_value` | Kern |
| 1614 | `add_lab_value` — Einheit unbekannt | `unsupported_unit` | Kern |
| 1621 | `add_lab_value` — ts | `invalid_ts` | Kern |
| 1640 | `add_lab_value` — Dedupe | `duplicate_marker` | Kern |
| 1776 | `remove_last_lab_value` | `no_active_value` (Draht-Name, §10.2) | Kern |
| 1794 | `set_wellbeing` — target | `wellbeing_target_missing` | Kern |
| 1799 | `set_wellbeing` — score | `wellbeing_score_invalid` | Kern |
| 1806 | `set_wellbeing` — key | `wellbeing_key_unknown` | Kern |
| 1812 | `set_wellbeing` — ts | `invalid_ts` | Kern |
| 2163 | `set_settings` — Validierung | `invalid_setting` | Rand |
| 2188 | `export_csv` — Datensatz | `unknown_dataset` | Rand |
| 2235-2239 | `start_person_flow` — kein `async_init` (alte HA-Version) | `config_flow_unavailable` | Rand |
| 2245-2249 | `start_person_flow` — Flow-Start hat geworfen (deutsche Prosa + Roh-Exception `{err}`) | `config_flow_failed` | Rand |
| 2274 | `delete_person` — Bestätigung | `confirm_mismatch` | Rand |
| 2343 | `import_csv` — Quelle | `invalid_import_source` | Rand |
| 2353 | `import_csv` — UTF-8 | `content_not_utf8` | Rand |
| 2358 | `import_csv` — Größe | `content_too_large` | Rand |

### 7.3 Batch (`ws_api.py`, bereits strukturiert) — 5 Aufrufstellen + Builder

| Zeile | Stelle | Änderung |
|---|---|---|
| 1646 | `_lab_error_result` (Builder) | **unverändert** — Envelope bleibt `{"ok": false, "error": {code, params, message}}`, **ohne** `translation_*` |
| 1673 | `add_lab_report` — `invalid_ts` | `message` wird sprachneutral (§10.3) |
| 1680 | `add_lab_report` — Zeilenfehler | dito |
| 1694 | `add_lab_report` — Dedupe (**handgebautes Dict statt Builder**) | auf `lab_report_error` vereinheitlichen |
| 1727 | `remove_lab_report` — `invalid_ts` | `message` sprachneutral |
| 1741 | `remove_lab_report` — `no_active_report` | dito |

**Entschieden (§5.4, keine Alternative mehr):** Der Batch-Envelope bleibt
`{code, params, message}`; `translation_domain`/`translation_key`/
`translation_placeholders` werden **nicht** ergänzt. REQ-HOM-123 §2.4 und
REQ-HOM-132 legen Form und Keys exakt fest (§4: keine neuen Antwort-Keys), und
die Card lokalisiert clientseitig aus `code` + `params` (§5.6). Der Batch ist
damit die **strukturierte**, Service/WS die **HA-native** Projektion desselben
Objekts — kein Kanal trägt beide Formen.

### 7.4 Katalog-/Message-Builder (`logic.py`)

`lab_report_error` (`:1195`), `_LAB_ROW_ERROR_CODES` (`:1184`),
`ENTRY_TS_INVALID_MESSAGE` (`:160`): der Prosa-String wird durch den Code-Pfad
ersetzt und die Konstante **gelöscht** (§13 O-7) — sie ist auch als Log-Hilfe
unnötig, weil HA `str(err)` loggt und das der sprachneutrale Fallback ist (§8).
Betroffen: `__init__.py:1141` und `ws_api.py:885` (dort wird der Prosa-String
heute als `ValueError` geworfen und über `str(err)` an mehrere
`send_error`-Stellen weitergereicht). Neue Konstante: `ERROR_SPECS` +
`RAW_ECHO_CODES` (§5.1).

### 7.5 Frontend

`www/health-o-mat-i18n.js` (Kategorie `exceptions`, §5.6), `www/health-o-mat-card.js`
(`:150-260` Loader, `:2033`/`:2128` Fehleranzeige), `www/health-o-mat-labs-card.js`,
`www/health-o-mat-panel-views.js` (`:1320`), `www/health-o-mat-panel-base.js`
(`:713` UI-Translations).
Heute zeigen alle `message` zuerst — nach der Migration muss `translation_key`
zuerst kommen.

**Der brechende Parser ist `errorMessage()`** (`www/health-o-mat-labs-card.js:227-237`):
eine **Exact-Match-Map** auf den rohen `message`-String
(`unknown_marker`/`unit_required`/`unsupported_unit`/`invalid_value` → deutscher
Satz, sonst `raw`). Sobald `message` sprachneutral wird, greift die Map nicht
mehr und der Fallback zeigt den technischen String. `errorMessage()` muss
deshalb auf `code`/`params` umgestellt werden (Map-Key = `code`, nicht der
Text). Dieselbe Datei hat zwei weitere Anzeigen: `resultError()`
(`:241-245`, Batch-Envelope, `error.message || error.code`) und
`reportErrorMessage()` (`:247-250`, Freitext-Exception) — beide prüfen und
gegebenenfalls auf `translation_key || code` heben.

### 7.6 Angrenzend, nicht im Scope

`button.py:112,131,150` und `text.py:51` werfen deutsche `HomeAssistantError` aus
Entity-Aktionen (kein Service-/WS-Aufruf). Sie sind Kandidaten für denselben
Katalog, aber nicht Teil von REQ-HOM-127 (§13 O-6).

### 7.7 Code unverändert, Transport angepasst (Relais-Pflicht)

`ws_api.py:2208-2212` (`export_failed`), `:2292-2295` (`backup_failed`),
`:2381` (`import_failed`), `:2404` (`restore_failed`) fangen
`HomeAssistantError` und senden `str(err)` — sie **verlieren heute** die
`translation_*`-Felder. Nach der Migration müssen sie sie durchreichen
(`send_error(..., translation_domain=err.translation_domain, …)`), sonst ist der
Service-Fehler im Panel unübersetzt.

Diese vier Stellen bleiben in der Zählung von §7 unter den **8
code-unveränderten** Aufrufen (`32 migriert + 8 code-unverändert = 40`): kein
Katalogcode, kein `message`-Umbau — geändert wird ausschließlich die
Transport-Schicht.

---

## 8. Entscheidung D-3

**Frage:** Fehler-Transport — HA-native Übersetzungsfelder oder ein eigenes
Code-Envelope?

| | A — reines Code-Envelope | B — nur HA-native Felder | **C — Code als Identität, native Felder als Transport** |
|---|---|---|---|
| Form | überall `{code, params, message}` | `translation_key`/`translation_domain`/`translation_placeholders` | `code == translation_key`, `params == translation_placeholders`; Batch behält `{code, params, message}` |
| Service-Kanal | kann nur `message` senden → `params` gehen verloren | vollständig; Felder im Fehlerobjekt, Anzeige-Lokalisierung unbelegt (s. Zeile „HA-Lokalisierung") | vollständig |
| WS-Kanal | eigener Envelope-Vertrag nötig | `send_error` trägt die Felder (2026.9.1) | dito |
| HA-Lokalisierung | **nein** — nur eigene JS-i18n | **Fehlerobjekt ja, Anzeige ungeprüft:** HA loggt `str(err)`, also den sprachneutralen Fallback — **nicht** die Übersetzung; `call_service` liefert `translation_*` im Fehlerobjekt aus; ob der Service-Toast den Text tatsächlich lokalisiert rendert, ist **unbelegt** und im E2E zu verifizieren (§11) | wie B |
| Batch-Vertrag (REQ-HOM-123) | bleibt | müsste auf `translation_key` umbenannt werden | bleibt |
| Wörtliche REQ-HOM-127-Form `{code, params}` | ja | nein (nur Synonyme) | ja (Batch) bzw. als `translation_key` (Service/WS) |
| Quellen der Wahrheit | 1 (eigener Katalog) + 1 (JS-Texte) | 1 (HA-Übersetzungen) | **1** (Katalog; HA-Übersetzungen sind die Textablage) |
| Aufwand | mittel; neue JS-i18n, kein HA-Support | klein, aber Vertragsbruch | klein–mittel; zwei Namen für dasselbe |

**Empfehlung: C.** Begründung in einem Satz: HA 2026.9.1 liefert den
Lokalisierungs-Transport bereits mit (`translation_*` an `HomeAssistantError`
**und** an `send_error`), sodass ein einziger Katalog genügt, während die
ausgelieferten Antwort-Verträge von REQ-HOM-132/123 unangetastet bleiben.

**Klarstellung zur Lokalisierung:** lokalisiert wird die **Anzeige** (Client bzw.
`translation_*` im Fehlerobjekt). HA-Logs behalten den sprachneutralen
`str(err)`-Fallback — gewollt, weil Logs sprachneutral und PII-frei bleiben
sollen (§14) und `str(err)` nie einen Messwert enthält. Das ist keine Zusage,
sondern folgt aus der Template-Regel in §5.1: `message` wird aus dem per-Code-
Template gerendert, `{value}` steht nur bei `invalid_ts` im Template, und
`invalid_value` wird ohne Wert formuliert.

**Verworfen innerhalb von C:** den Fachcode in das `code`-Feld von
`send_error` zu schreiben. `code` ist HAs Fehlerklasse (`invalid_format`,
`not_found`, `service_validation_error`); ein Overload bricht die bestehende
Fehlerbehandlung von Frontend und Dritt-Clients und würde trotzdem ein zweites
Feld für den Fachcode brauchen.

**Konsequenz:** `translation_key` und `code` sind **immer** identisch. Das ist
per Test abgesichert (§11) und in `docs/SERVICE-RESPONSES.md` zu dokumentieren.

---

## 9. i18n

### 9.1 Dateien

`strings.json` (englischer Master), `translations/en.json` (Fallback, laut HA-Doku
für Custom-Integrationen **verpflichtend und vollständig**) und
`translations/de.json`. Struktur:

```json
{
  "exceptions": {
    "amount_out_of_range": {
      "message": "Amount must be between {min} and {max} ml."
    },
    "invalid_ts": {
      "message": "Invalid timestamp {value}. Expected ISO 8601, at most 5 minutes in the future and not before 1900."
    }
  }
}
```

de:

```json
{
  "exceptions": {
    "amount_out_of_range": {
      "message": "Die Menge muss zwischen {min} und {max} ml liegen."
    }
  }
}
```

### 9.2 Platzhalter-Regeln (hassfest-konform)

1. Platzhalter-Namen sind gültige Python-Identifier und **exakt** die
   `params`-Schlüssel.
2. **Keine einfachen Anführungszeichen um einen Platzhalter** (`'{value}'` wird
   von hassfest abgelehnt) — der Alt-Text `ENTRY_TS_INVALID_MESSAGE` verletzt das
   heute und ist deshalb kein 1:1-Muster.
3. Kein HTML, keine URL, keine führenden/abschließenden Leerzeichen.
4. Ein deklarierter Param **muss nicht** im Text vorkommen; jeder Platzhalter im
   Text **muss** deklariert sein. Das gilt für das `message`-Template (§5.1)
   **und** für `exceptions.<code>.message`. Einzige Roh-Echo-Ausnahme:
   `invalid_ts.value` (aufruferseitiger Zeitstempel) **darf** in beiden
   erscheinen; `invalid_value.value` (Messwert-Roh-Echo) wird in **keinem** Text
   gerendert und steht nur als Maschinen-Param im Objekt (§5.1, §6).
5. **Die Platzhalter-Menge ist je Code in `strings.json`, `translations/de.json`
   und `translations/en.json` identisch.** HA verwirft eine Übersetzung, deren
   Platzhalter-Menge vom Master abweicht, und fällt dann auf Englisch zurück —
   „Teilmenge genügt" ist falsch (`test_translation_placeholders_match_across_languages`,
   `tests/test_translations.py:372`, prüft bereits Mengengleichheit gegen den Master).
6. Fehlt eine Sprache ganz, fällt HA auf Englisch zurück — die UI zeigt nie
   einen rohen Key.

### 9.3 Parität

- `test_req_hom_107_key_tree_parity` (`tests/test_translations.py:75`) deckt die
  neue Sektion automatisch ab, sobald sie in allen drei Dateien existiert.
- Zusätzlich kataloggetrieben: jeder Code aus `logic.ERROR_SPECS` hat
  `exceptions.<code>.message` in allen drei Dateien; kein `exceptions`-Key ohne
  Katalog-Eintrag (kein toter Text).
- **Platzhalter-Parität je Code** (nicht nur „⊆ `params`"): die Menge der
  Platzhalter in `strings.json`, `de` und `en` ist für **jeden** Code gleich;
  ein `{min}` in de und `{min} {max}` in en lässt HA die Übersetzung verwerfen.
- **grep-Test „keine deutsche Prosa in migrierten Pfaden"**
  (`test_no_german_prose_in_migrated_paths`): scannt die `message`-Argumente
  aller `send_error`/`ServiceValidationError`-Aufrufe in `ws_api.py` und
  `__init__.py` gegen eine explizite Allowlist der `T`-Stellen (§5.7/§7.1) und
  schlägt bei deutschen Prosa-Markern an (Umlaute sowie `nicht`, `keine`,
  `konnte`, `muss`, `ungültig`, `zwischen`).

---

## 10. Migration & Kompatibilität

### 10.1 Grundsatz

Es gibt **keine** Pflicht-Keys und keine geänderten Keys. `message` bleibt
dauerhaft als Fallback erhalten (keine Deprecation). Entfernt wird nur die
deutsche Prosa **im Code**.

### 10.2 Alt → Neu (Prosa-Mapping)

| Alt (Zeile) | Neu |
|---|---|
| „Keine Health-O-Mat-Person eingerichtet" (`__init__.py:1048,1597,1608`) | `no_person_configured` |
| „Mehrere Personen vorhanden (A, B) …" (`__init__.py:1052`) | `person_ambiguous` / `{count}` (Namen entfallen, §13 O-4) |
| „Person 'X' nicht gefunden" (`__init__.py:1059`) | `person_not_found` (kein Name im Text, §13 O-4) |
| `ENTRY_TS_INVALID_MESSAGE` (`__init__.py:1141`, `ws_api.py:885`) | `invalid_ts` / `{value}` |
| „amount_ml muss zwischen 1 und 10000 liegen" (`__init__.py:1234`) | `amount_out_of_range` / `{min, max}` |
| „ml muss zwischen 1 und 10000 liegen" (`ws_api.py:1303`) | `amount_out_of_range` / `{min, max}` |
| „sys/dia müssen zwischen 40 und 260 liegen" (`ws_api.py:1534`) | `bp_out_of_range` / `{min, max}` |
| „Entweder 'status' oder 'score' angeben" (`__init__.py:1411`, `ws_api.py:1794`) | `wellbeing_target_missing` / `{max}` |
| „Ungültiger Wohlbefinden-Score 'X' …" (`__init__.py:1415`, `ws_api.py:1799`) | `wellbeing_score_invalid` / `{min, max}` |
| „Ungültiger Wohlbefinden-Status/Key …" (`__init__.py:1419`, `ws_api.py:1806`) | `wellbeing_key_unknown` / `{allowed}` |
| „Unbekannter kind …" (`__init__.py:1198,1444`, `ws_api.py:1338,1375,1468`) | `invalid_history_kind` / `invalid_undo_kind` |
| „Eintrag 'X' nicht gefunden oder …" (`__init__.py:1215`, `ws_api.py:1484`) | `entry_not_found` / `{kind}` |
| „Keine … zum Entfernen" (`__init__.py:1463`, `ws_api.py:1351`) | `nothing_to_remove` / `{kind}` |
| `unknown_marker`/`unit_required`/`invalid_value`/`unsupported_unit`/`duplicate_marker` (`__init__.py:1284-1320`, `ws_api.py:1574-1640`) | gleiche Codes, jetzt mit `params` |
| „Kein aktiver Wert für Marker 'X'" (`__init__.py:1493`) | **`no_active_value`** / `{marker}` — Name ist bereits auf dem Draht (`ws_api.py:1776`, `tests/test_ws_api.py:5148`), **keine** Umbenennung (§10.4) |
| „Ungültige Einstellung 'X': …" (`ws_api.py:2163`) | `invalid_setting` / `{field}` |
| „Config-Flow-Start wird … nicht unterstützt" (`ws_api.py:2238`) | `config_flow_unavailable` |
| „Config-Flow konnte nicht gestartet werden: …" (`ws_api.py:2248`) | `config_flow_failed` (Roh-Exception nur ins Log, `:2244`) |
| übrige WS-Texte (§7.2) | Codes der Tabelle §6 |

### 10.3 Batch-Verhalten

- **Form unverändert und entschieden**: `{"ok": false, "error": {code, params,
  message}}`, **keine** `translation_*`-Keys (§5.4, §7.3). `params` unverändert
  (inklusive `invalid_ts.value` und `invalid_value.value` als Roh-Echo — die
  beiden einzigen Codes in `RAW_ECHO_CODES`, §5.1/§13 O-2).
- `message` wechselt von deutscher Prosa (`Zeile 3 (kreatinin): unknown_marker`)
  auf den sprachneutralen Fallback aus dem per-Code-Template (§5.1), z. B.
  `unknown_marker (row=3, marker=kreatinin)`. Die UI dürfte damit **nicht** mehr
  `message` rendern, sondern `code`/`params` lokalisieren — das passiert im
  **selben** Release (WP-A Schritt 7), sonst zeigt die Labs-Card kurzzeitig
  Englisch/Technik.

### 10.4 Kompatibilitätsaussagen (Release 0.21.0, MINOR + 💥)

| Verbraucher | Impact |
|---|---|
| Automatisierung, die `ServiceValidationError` fängt | unverändert (Klasse, `code: service_validation_error`) |
| Automatisierung, die auf `message`-Text matcht | **bricht** — `message` ist jetzt sprachneutral (`code` + Params) statt deutscher Prosa. 💥-Hinweis mit Beispiel. |
| WS-Client, der `error.code === "invalid_format"` prüft | unverändert |
| WS-Client, der deutsche Fehlertexte anzeigt | zeigt nach Update den sprachneutralen Fallback, bis er `translation_key` auswertet (additiv) |
| Batch-Client (Labs-Card) | Form stabil; `message` technisch → `code`/`params` nutzen (im selben Release angepasst) |
| REQ-HOM-132-Kontrakte | unverändert (exakte Keys, `errors` ≤ 20, Exceptions) |

Deprecation-Politik: Codes werden **nie** umbenannt; ein entfallender Code
bleibt mindestens eine MINOR-Periode als Alias im Katalog, damit alte Clients
weiter auflösen.

---

## 11. Teststrategie

| Ebene | Datei | Inhalt |
|---|---|---|
| Katalog (HA-frei) | neu `tests/test_error_contract.py` | Codes snake_case + eindeutig; jeder Code deklariert seine `params`; `build_error` liefert alle drei Felder; `message` nicht leer, ASCII/sprachneutral, ohne deutsche Umlaute/Prosa; `message` stammt aus dem per-Code-Template und referenziert nur dort deklarierte Params — `{value}` **nur** bei `invalid_ts` (`test_message_template_value_scope`, `invalid_value` nie mit Wert); `params`→`translation_placeholders` ist `str`-Projektion; unbekannter Code → nicht-leerer Fallback; **PII-Guard `test_error_contract_no_pii_params`**: kein `params`-Schlüssel `person`/`note`/`comment`, Roh-Echo `value` **nur** bei den Codes in `RAW_ECHO_CODES` (`invalid_ts`, `invalid_value`), Roh-Echo ≤ 64 Zeichen, jeder andere Schlüssel steht in `ERROR_SPECS[code]` als strukturell |
| Service-Pfade | `tests/test_lab_services.py`, `tests/test_wave_a.py`, `tests/test_import_backup.py` | je migrierter Stelle: `ServiceValidationError.translation_key == code`, `translation_domain == "health_o_mat"`, `translation_placeholders` == erwartete Strings, Positions-Args nicht leer; REQ-HOM-132-Regression (Keys, `errors`-Cap, Exceptions) |
| WS-Pfade | `tests/test_ws_api.py` | Fake-Connection zeichnet `send_error`-Kwargs auf: `code` bleibt `invalid_format`, `translation_key` == Fachcode, Placeholder-Projektion; Transport-/Entry-Fehler (`:802`, `:1280`, `:1889`, `:1930`) unverändert; die vier Relais-Stellen (`:2212`, `:2295`, `:2381`, `:2404`) gehören zu den 8 code-unveränderten Aufrufen (§7.7) und werden nur auf das Durchreichen der `translation_*`-Felder geprüft — kein Katalogcode, keine `message`-Änderung |
| i18n | `tests/test_translations.py` | Parität (bestehender Key-Tree-Test) + kataloggetrieben: jeder Code in Master/`de`/`en`, kein toter `exceptions`-Key, **Platzhalter-Menge je Code in allen drei Dateien identisch** (nicht nur ⊆ `params`), keine einfachen Anführungszeichen um Platzhalter, `{value}` steht in `exceptions.<code>.message` **nur** bei `invalid_ts`; `test_no_german_prose_in_migrated_paths` (grep, Allowlist = `T`-Stellen §5.7) |
| JS | `tests/test_card_js.py`, `tests/test_panel_js.py` | Fehleranzeige nutzt `translation_key || code` und `translation_placeholders || params`; i18n-Loader lädt `category: "exceptions"`; unbekannter Code → `message`-Fallback; kein roher Code im DOM |
| E2E | `tests_e2e/test_i18n_e2e.py` | ein repräsentativer Pfad: `health_o_mat/book_drink` mit `ml: 0` → Fehlerobjekt mit `translation_domain`/`translation_key=amount_out_of_range`/Placeholders; `str(err)` ist der **sprachneutrale** Fallback (nicht der deutsche Satz). Danach `frontend/get_translations` mit `language: "de"` **und** `"en"`, `category: "exceptions"` → je Code Text vorhanden, de ≠ en, und der **interpolierte** Text (`{min}`/`{max}` ersetzt) ist der erwartete Satz. **Kein** Sprachwechsel der Instanz (Etikette). |

**Auflage für den Task-Plan:** Die Verifikation prüft die **gerenderte** Meldung
(Text nach Platzhalter-Interpolation in beiden Sprachen), nicht nur die Existenz
von `translation_key`/`translation_placeholders`. Die Lokalisierung des
Anzeige-Pfads ist bisher **unbelegt** (§8) — ein grüner Objekt-Test beweist sie
nicht.

Zusätzlich: `python3 -m pytest -q`, `ruff check .`, `ruff format --check .`,
`python3 -m compileall -q custom_components/health_o_mat`.

---

## 12. Risiken

| Risiko | Wirkung | Gegenmaßnahme |
|---|---|---|
| Automatisierungen matchen `message`-Text | stille Fehlfunktion nach 0.21.0 | 💥-Hinweis mit Vorher/Nachher-Beispiel; `code` bleibt konstant; `message` bleibt nicht-leer |
| HA-Version trägt die Felder nicht | `send_error`-Kwargs → `TypeError` | `errors.send_ws_error` prüft die Signatur und fällt auf 3 Argumente zurück; gepinnte Version 2026.9.1, Minimum 2026.8.0 (§12.1) |
| Zwei Namen für eine Sache (`code` / `translation_key`) | Clients greifen mal so, mal so zu | ein Test erzwingt Gleichheit; Doku in `docs/SERVICE-RESPONSES.md`; Client-Regel „`translation_key` vor `code`" |
| `params` zu `str` projiziert | Verlust von Typen für Clients | `params` bleibt typisiert im Batch/kanonischen Objekt; nur die HA-Projektion stringifiziert |
| Übersetzungsdrift de/en | eine Sprache zeigt Englisch (HA verwirft die Übersetzung bei abweichender Platzhalter-Menge) | Key-Tree-Parität + **Mengengleichheit der Platzhalter je Code** + kataloggetriebener Test + E2E mit beiden Sprachen (gerenderter Text) |
| Doppelter WS-Request pro Sprache (`exceptions`) | +1 Roundtrip beim ersten Panel-/Card-Paint | pro Sprache gecacht (`_cache`/`_inflight` im i18n-Modul); Loader lädt beide Kategorien parallel |
| Text-Rendering von Nutzereingaben | Platzhalter-Injektion/XSS | Werte werden als Platzhalter **eingesetzt**, nie als Template geparst; JS rendert über `escapeHtml` (bestehend) |
| Katalog wächst unkontrolliert | tote/doppelte Codes | Test „kein Code ohne Übersetzung, kein `exceptions`-Key ohne Code" |
| `errors.py` ist neues Modul | Import-Zyklus mit `__init__` | `errors.py` importiert nur `homeassistant.exceptions` + `logic`; `__init__`/`ws_api` importieren `errors` |

### 12.1 Verifikation gegen die gepinnte HA-Version

Belegt (nicht angenommen):

- `HomeAssistantError.__init__(*args, translation_domain=None,
  translation_key=None, translation_placeholders=None)` — HA `2026.9.1`,
  `homeassistant/exceptions.py` (Rohquelle des Release-Tags).
- `handle_call_service` gibt `translation_domain`/`translation_key`/
  `translation_placeholders` im Fehlerobjekt aus — HA `2026.9.1`,
  `homeassistant/components/websocket_api/commands.py`.
- `getHassTranslations(..., category)` kennt `"exceptions"` — HA-Frontend
  `src/data/translation.ts`; Doku „Integration translations“ (Sektion
  `exceptions`) und „WebSocket API“ (Fehlerobjekt-Beispiel).
- `hacs.json` verlangt HA ≥ `2026.8.0`; E2E pinnt `2026.9.1`
  (`docker-compose.e2e.yml:62`). Alle genutzten Felder existieren damit in
  beiden Grenzen.
- **Offen für die Implementierung:** die exakte Signatur von
  `ActiveConnection.send_error` in `2026.8.0` (nicht separat geprüft) — deshalb
  der Signatur-Fallback in §5.3.

---

## 13. Offene Punkte (Empfehlung, kein Blocker)

| # | Punkt | Empfehlung |
|---|---|---|
| O-1 | Gehören die acht „Rand"-Stellen (`ws_api.py:2163,2188,2235-2239,2245-2249,2274,2343,2353,2358`) in 0.21.0? Sie fehlen in der WP-A-Zeilenliste. | **Ja** — gleicher Katalog, acht zusätzliche Testzeilen; sonst bleiben genau dort deutsche Prosa und fehlende Codes stehen. |
| O-2 | `invalid_value.params.value` behalten? | **Behalten** (REQ-HOM-123-Vertrag, Roh-Echo der aufrufenden Eingabe), aber **weder** im `message`-Template **noch** im Übersetzungstext rendern. Zusammen mit `invalid_ts.value` ist das die **vollständige** Roh-Echo-Allowlist (`RAW_ECHO_CODES`, §5.1) — mehr nicht. |
| O-3 | `add_blood_pressure` (Service) hat keine Bereichsprüfung, `save_measurement` (WS) schon. | **Nicht** in WP-A ändern (wäre eine Verhaltensänderung); als Beobachtung im Task-Plan führen. |
| O-4 | `person_ambiguous`/`person_not_found` verlieren die Namen aus dem Text. | Akzeptieren: `person_ambiguous.count` + `list_persons` liefern die Namen bereits; der Fehlertext bleibt PII-frei. |
| O-5 | `RestoreError`-Prosa (`__init__.py:1569-1570`, `restore.py`) und Export-/Import-Prosa. | Außerhalb 0.21.0 (REQ-HOM-132-Vertrag); eigener Katalog erst, wenn Restore eigene Codes bekommt. |
| O-6 | `button.py:112,131,150`, `text.py:51` (Entity-Aktionen, deutsche Prosa). | Nicht in REQ-HOM-127 (kein Service/WS); im Task-Plan als Folgekandidat nennen, ohne neue REQ. |
| O-7 | `ENTRY_TS_INVALID_MESSAGE` (`logic.py:160`) ist der einzige geteilte Prosa-String. | Nach der Migration löschen; `message`/`str(err)` laufen dann über den Code-Pfad und bleiben sprachneutral (§8). |

---

## 14. Threat Model (4 Fragen, Kurzform)

1. **Was baust du?** Fehlerantworten über Services, eigene WS-Kommandos und den
   Batch, jetzt mit Codes/Params und de/en-Texten aus den Integrations-
   Übersetzungen.
2. **Was kann schiefgehen?** (a) `params`/Texte tragen Gesundheitswerte oder
   Personennamen in WS-Antworten und HA-Logs; (b) Fehlertexte werden in
   Diagnostics/Issue-Anhänge kopiert; (c) `person_not_found` wirkt als Existenz-
   Orakel; (d) Übersetzungs-Platzhalter rendern Nutzereingaben unescaped.
3. **Was tust du dagegen?** Param-Whitelist pro Code (vollständige Menge = §6;
   strukturelle Werte: `row`, `first_row`, `count`, `limit`, `min`, `max`,
   `marker`, `unit`, `kind`, `ts`, `expected`, `field`, `allowed`); **keine**
   Store-Werte, **keine** Personennamen, **keine** Notiz-/Freitextfelder in
   `params` oder im Text; Roh-Echo (`value`) ≤ 64 Zeichen und **ausschließlich**
   für die Codes in `RAW_ECHO_CODES` (`invalid_ts` = Zeitstempel-Eingabe, nur
   dort im `message`-Template und Übersetzungstext erlaubt; `invalid_value` =
   bereits ausgelieferter Batch-Roh-Echo eines Messwerts, **weder** im
   `message`-Template **noch** im Übersetzungstext gerendert); `message` ist
   template-gerendert und sprachneutral; Test
   `test_error_contract_no_pii_params` + `test_message_template_value_scope`;
   UI rendert Platzhalter über `escapeHtml`.
4. **Was sind die Konsequenzen?** Ein Leck wäre eine Personen-/Gesundheits-
   angabe in einem geteilten Log oder öffentlichen Issue — dieselbe Schadens-
   klasse wie der bestehende Diagnostics-Grundsatz („keine Gesundheitsdaten").

---

## 15. Traceability

| Anforderung | Design-Abschnitt |
|---|---|
| **REQ-HOM-127 AK 1** — bestehende Services/WS-Fehler auf strukturiert `{code, params}` migrieren, Texte lokalisieren | §5.1–5.5, §6, §7.1–7.2, §9, §10 |
| **REQ-HOM-127 AK 2** — die Batch-Spec liefert nur Referenzformat | §5.4, §7.3 (Form unverändert, **ohne** `translation_*`) |
| WP-A AK „jede fachliche Stelle liefert `code` und `params`, `code` stabil snake_case" | §5.1, §6, §11 (Katalogtest) |
| WP-A AK „`message` bleibt, nie leer" | §5.1, §10.1, §11 |
| WP-A AK „`strings.json`/`de`/`en` paritätisch, jeder Code in beiden Sprachen" | §9.1–9.3 |
| WP-A AK „REQ-HOM-132 unverändert (Key-Mengen, `errors` ≤ 20, Exceptions)" | §4, §10.4, §11 |
| WP-A AK „keine neuen Pflicht-Keys, bestehende Consumer laufen weiter" | §10.1, §10.4 |
| WP-A AK „Transport-Key gemäß D-3" | §8, §5.5 |
| WP-A AK „kein deutscher Prosa-Fehlertext in migrierten Pfaden" | §6, §7.1–7.2, §10.2, §11 |
| WP-A AK „Test enumeriert alle Codes gegen die Übersetzungen" | §9.3, §11 |
| **REQ-HOM-123 §2.4** (Batch-Fehlervertrag) | §5.4, §7.3 |
| **REQ-HOM-132** (Service-Antworten) | §4, §7.7, §10.4 |
| **REQ-HOM-107** (Übersetzungs-Parität) | §9.3 |
| **Entscheidung D-3** (`PLAN-AUDIT` §5) | §8 |

---

## 16. Review-Auflagen (Task-Plan)

Concept-Review **APPROVED** (2026-11-03, `concept-reviewer`): 0 kritisch, 0 major,
3 minor. Die drei Punkte sind **Auflagen an den Task-Plan**
(`docs/superpowers/plans/2026-11-03-error-contract.md`) und dort als eigene
Tasks/Akzeptanzkriterien hinterlegt:

1. **`{value}` in `translation_placeholders` (§5.2:117).** Die Zeile
   `translation_placeholders={k: str(v) for k, v in params.items()}` projiziert
   **alle** Params — auch `invalid_value.value` (Messwert-Roh-Echo). Das ist nur
   deshalb sicher, weil der i18n-Test `{value}` in
   `exceptions.invalid_value.message` verbietet (§9.2 Regel 4). Auflage: der Plan
   muss diesen Test als **expliziten Guard** führen (nicht als Nebenbedingung) und
   die Projektion `params → translation_placeholders` zusätzlich am Guard
   `RAW_ECHO_CODES` testen.
2. **ASCII-Aussage in §11:615.** Dort steht `message` sei „ASCII/sprachneutral";
   ASCII-garantiert ist aber nur das **Template** — `params.marker`/`params.value`
   können Nicht-ASCII-Zeichen tragen und werden in den Text eingesetzt. Auflage:
   der Test prüft **Template-ASCII** (`ERROR_SPECS[code]["message"]`), nicht den
   gerenderten String; der gerenderte String wird separat auf „keine deutsche
   Prosa" geprüft.
3. **`wellbeing_target_missing.params.max` ohne Quelle (§6 Zeile 16).** Der Wert
   ist ableitbar als `len(WELLBEING_STATES)` (`const.py:115`), im Service aus
   `len(allowed)` mit `allowed = [state["key"] for state in WELLBEING_STATES]`
   (`__init__.py:1409`, gerendert `:1416`). Auflage: der Plan benennt diese Quelle
   explizit an der Fundstelle und im Katalogtest.

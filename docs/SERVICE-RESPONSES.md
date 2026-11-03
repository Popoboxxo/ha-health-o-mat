# Service-Antworten (REQ-HOM-132, Issues #71/#72)

Stand: 0.18.0 (Antwortkontrakte) · Entscheidung **D6** aus
`docs/PLAN-OPEN-ISSUES.md` §2. Der Fehler-Vertrag aus **REQ-HOM-127** ist
zusätzlich unten dokumentiert; er ist auf dem Branch `feat/127-error-contract-impl`
implementiert und **noch nicht released** (geplant für 0.21.0).

## Warum `OPTIONAL` und nie `ONLY`

Die fünf Verwaltungs-Services sind mit `SupportsResponse.OPTIONAL` registriert.
`ONLY` würde jeden Aufruf **ohne** `return_response` (Automationen, Skripte,
interne Aufrufe, die WS-Brücke) mit einem Fehler beenden. Mit `OPTIONAL` gilt:

- ohne `return_response` → Handler führen die Arbeit aus und geben `None` zurück;
- mit `return_response: true` → exakt der unten dokumentierte Kontrakt.

Fehler bleiben **Exceptions** (`ServiceValidationError`/`HomeAssistantError`);
Teilausfälle stehen als Daten in der Antwort (z. B. `weekly_report`).
Antworten enthalten nur Zähler, Status und Dateinamen — nie Messwerte, nie
absolute Pfade (Automation-Traces sind einsehbar).

## Kontrakte

Flache snake_case-Schlüssel, Zähler als `int`.

| Service | Antwort |
|---|---|
| `export_csv` | `{filename: str, filenames: list[str], rows: int, dataset: str}` — `filename` = erste Datei, `filenames` = alle geschriebenen Dateien (Basenamen), `rows` = Summe der Datenzeilen über alle Dateien (O-2) |
| `import_csv` | `{imported: int, skipped: int, rejected: int, errors: list[str]}` — `errors` auf **20** Texte gedeckelt, die Zähler bleiben maßgeblich. Jeder Text hat die Form `Zeile <N>: <Grund>` und enthält **keine** Zellinhalte/Messwerte (z. B. `Zeile 2: ungültiger Laborwert`); `imported`/`skipped` zählen die vom Store tatsächlich geschriebenen bzw. verworfenen Zeilen |
| `backup` | `{filename: str, datasets: list[str], rows: int}` — `filename` = Basename, `datasets` in fester Reihenfolge (`drinks`, `blood_pressure`, `wellbeing`, `lab_values`) |
| `restore_backup` | `{filename: str, applied: bool, dry_run: bool, counts: dict, totals: dict, warnings: list[str]}` — durchgereichtes Restore-Ergebnis, `filename` = Basename; im Dry-Run stammen `counts`/`totals`/`warnings` aus dem Plan |
| `weekly_report` | `{reports: [{person: str, notify_service: str, delivered: bool}], delivered: int, failed: int}` — ein Eintrag je Person; ein fehlschlagender Versand bricht die übrigen Personen nicht ab |

`health_o_mat/import_csv` (WebSocket, admin-only) liefert **denselben**
`import_csv`-Kontrakt. Es akzeptiert genau **eine** Quelle: `filename`
(Whitelist: Import-/privater Export-Ordner, `safe_import_path`) **oder**
`content` (UTF-8-Text, maximal 2 MiB, nie auf Platte geschrieben). Beides oder
keines → `invalid_format`; zu großer Inhalt → `content_too_large` (Ablehnung,
kein Abschneiden).

## Fehler (REQ-HOM-127)

Mit dem Fehler-Vertrag tragen fachliche Service- und WS-Fehler **einen Code
statt deutscher Prosa**. Einzige Quelle ist der Katalog
`logic.ERROR_SPECS` (35 Codes) mit dem Builder
`logic.build_error(code, params)`; die drei Kanäle sind Projektionen desselben
Objekts:

| Kanal | Adapter | Form |
|---|---|---|
| Service (`ServiceValidationError`) | `errors.validation_error` (`errors.py:41`) | Positions-Argument = neutraler `message`; `translation_domain="health_o_mat"`, `translation_key=code`, `translation_placeholders={k: str(v)}` |
| Eigenes WS-Kommando (`connection.send_error`) | `errors.send_ws_error` (`errors.py:101`) | `code` bleibt HAs Transportcode (`invalid_format`, `not_found`, …); der Fachcode liegt in `translation_key`; dieselben `translation_*`-Felder |
| Labor-Batch (`send_result`) | `logic.lab_report_error` (`logic.py:1420`) | **unverändert** `{"ok": false, "error": {code, params, message}}` — **ohne** `translation_*` |

Ältere HA-Versionen ohne `translation_*`-Kwargs an `send_error` bekommen
automatisch die 3-Argumente-Form (fail-open, `errors.py:57`).

### Autorität und Projektion

- **`code` ist die Identität.** snake_case, stabil, wird **nie** umbenannt
  (gleiche Regel wie `unique_id`); ein Rename wäre ein Breaking Change. Auf dem
  Service-/WS-Kanal steht derselbe String in `translation_key`.
- **`params` sind die Maschinenfelder.** Typisiert (`str`/`int`/`bool`/`None`),
  pro Code im Katalog deklariert (Whitelist). `translation_placeholders` ist
  nur die HA-Projektion davon: dieselben Schlüssel, Werte als `str` (HA
  verlangt `dict[str, str]`).
- **`message` ist nur Fallback.** Aus dem per-Code-Template gerendert,
  sprachneutral/ASCII, nie leer; ein unbekannter Code fällt auf sich selbst
  zurück (`message == code`). `message` ist **nie** autoritativ und enthält
  keine Store- oder Gesundheitswerte.
- **`translation_key` == `code` immer** (per Test erzwungen). Die Texte liegen
  unter `exceptions.<code>.message` in `strings.json` (englischer Master) sowie
  `translations/de.json` und `translations/en.json`.

### Abgrenzung zu Antwortfeldern

Fehler sind **keine** Antwortfelder: Fachfehler bleiben Exceptions
(`ServiceValidationError`/`HomeAssistantError`), der WS-Envelope bleibt ein
Fehler (`ok: false`). Die fünf Verwaltungs-Services aus REQ-HOM-132 behalten
ihre Antwortkontrakte unverändert — insbesondere `errors` ≤ 20 bleibt eine
Liste von Textzeilen, kein Code-Array.

### Roh-Echo: `RAW_ECHO_CODES`

Genau zwei Codes tragen einen Rohwert des Aufrufers im `params`-Feld `value`
(`logic.RAW_ECHO_CODES`, `logic.py:1370`), gekürzt auf 64 Zeichen:

- `invalid_ts` — der **aufruferseitige** Zeitstempel; der einzige Code, der
  `{value}` im `message`-Template **und** im Übersetzungstext referenzieren darf.
- `invalid_value` — der bereits ausgelieferte Messwert-Roh-Echo des Batches;
  er bleibt **nur** Maschinenfeld und wird in **keinem** Text gerendert.

Alle übrigen `params` sind strukturell (`row`, `first_row`, `count`, `limit`,
`min`, `max`, `marker`, `unit`, `kind`, `ts`, `expected`, `field`, `allowed`).
Keine Personennamen, Notizen oder Freitexte in `params` oder im Text
(PII-Guard `test_error_contract_no_pii_params`).

### Client-Lokalisierung

Die Anzeige-Lokalisierung erfolgt ausschließlich über `translation_key` (bzw. `code` im Batch) und `translation_placeholders` (bzw. `params`); `message` wird nie geparst.

Konkret in Card/Panel (`tError`):

1. `key = err.translation_key || err.code`
2. `vars = err.translation_placeholders || err.params || {}`
3. Text = `exceptions.<key>.message` aus `frontend/get_translations`
   (`category: "exceptions"`), Platzhalter `{name}` interpolieren.
4. Unbekannter Code → `err.message`; ohne beides → der Code selbst. Nie eine
   leere Zeile, nie ein roher `ui_…`-Key.

`translation_key` hat Vorrang vor `code`, wenn beide vorhanden sind. Den
Zeilen-Hinweis für den Batch (`row`) liefert `common.ui_panel_lab_report_row_hint`;
`row` steht bewusst nicht im Fehlertext.

## Beispiel

```yaml
action: health_o_mat.import_csv
data: { person: "Caro", filename: "health_o_mat_labvalues_Caro_20261101-0900.csv" }
response_variable: import_result
# import_result == {"imported": 4, "skipped": 0, "rejected": 0, "errors": []}
```

## Abgrenzung

- **Kein** `SupportsResponse` bei den Alltags-Services (`add_drink`,
  `add_lab_value`, `void_entry`, …) — dort bleibt es beim bisherigen Verhalten.
- Der CSV-Import bleibt auf `;` und UTF-8 festgelegt (kein Sniffing, kein
  `cp1252`); Komma-Dateien laufen als `rejected`, cp1252-Bytes werden mit einer
  klaren Meldung abgelehnt.

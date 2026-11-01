# Service-Antworten (REQ-HOM-132, Issues #71/#72)

Stand: 0.18.0 · Entscheidung **D6** aus `docs/PLAN-OPEN-ISSUES.md` §2.

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

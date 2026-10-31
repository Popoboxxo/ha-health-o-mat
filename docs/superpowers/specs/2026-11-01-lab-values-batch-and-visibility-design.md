# Konzept: Laborwerte — Batch-Erfassung & Sichtbarkeit (Erweiterung zu REQ-HOM-122)

**Status:** Entwurf (2026-11-01), Review-Nachbesserung · **Basis:**
`docs/superpowers/specs/2026-10-30-lab-values-design.md` (REQ-HOM-122, umgesetzt in 0.16.x)
· **Verwandt:** `docs/REQUIREMENTS.md` REQ-HOM-122, `docs/CONCEPT-UI.md`,
`docs/IDEATION-VISION.md` §4.2

> Vier Lücken der bestehenden Domäne: (1) ein Laborbericht ist nur als N Einzelaufrufe
> erfassbar, (2) die Umrechnungsfaktoren der 29 Katalog-Marker sind im Admin unsichtbar,
> (3) der Laborwerte-Tab im Panel hat keinen kontextbezogenen Medizin-Hinweis im Sinne
> der Spec §1, (4) es gibt kein Beispiel-Dashboard für die Labs-Card. Alle Aussagen sind
> gegen `main` @ `7738d07` (Release 0.16.1) verifiziert.
>
> **Kein neues Datenmodell:** Store-Schema bleibt v5, `unique_id`s unverändert,
> `report_ref` bleibt ein freier Tag — kein `LabReport`-Aggregat, keine neue Entität,
> keine Änderung an Backup/Restore/CSV.

---

## 1. Ziel & Nutzen

Ein Laborbefund kommt als **ein Dokument mit 10–30 Werten zu einem Zeitpunkt aus einer
Quelle**. Heute kostet das 10–30 Service-Aufrufe (`add_lab_value` nimmt genau einen
Marker: `__init__.py:1001-1011`, `services.yaml:329-429`), jeder mit eigenem
Store-Write, eigenem Coordinator-Refresh und eigenem Audit-Eintrag. Card und Panel haben
nur ein Einzelwert-Formular (`health-o-mat-labs-card.js:663-706`,
`health-o-mat-panel-views.js:1093-1115`).

| Aspekt | n Einzel-Calls | ein `add_lab_report` |
|---|---|---|
| Tippfehler in Zeile 7 | 6 Werte geschrieben, 4 fehlen → manuelles Aufräumen | nichts geschrieben (Alles-oder-nichts) |
| `ts` / `report_ref` | n-mal wiederholen, Abweichungen möglich | einmal gesetzt, gilt für alle Zeilen |
| Store-Write / Refresh / Audit | n Writes, n Refreshes, n Audit-Einträge (Cap-Ring wird geflutet) | 1 Write, 1 Refresh, 1 Audit-Eintrag |
| Externe Systeme | n HTTP-Calls mit Fehler-Matrix | 1 Call, 1 Ergebnis |

**Zielgruppe:** derselbe Nutzer wie REQ-HOM-122 (eine Person pro Config-Entry) plus
externe Skripte/Systeme, die einen Befund in einem Rutsch pushen.

**Leitplanke (unverändert, Vision §4.2):** keine medizinische Klassifikation, keine
Diagnose. §8 schließt die Lücke, dass der Panel-Lab-Tab diesen Vorbehalt nur im globalen
Footer trägt (`health-o-mat-panel.js:1983-1987`, immer gerendert ab Zeile 1953).
Datenschutz unverändert: `diagnostics.py` bleibt redigiert, Export nie nach `/config/www`.

---

## 2. Datenmodell & Service-Vertrag

### 2.1 Kein Schema-Wechsel

`lab_readings[]` bleibt **exakt** das heutige Format (`store.py:641-680`): `{id, ts,
marker_key, value, unit, reported_value, reported_unit, report_ref, created_at,
voided_at, voided_by, void_reason}`. Batch-Schreiben ist nur eine andere Schreibweise
über derselben Liste — kein neues Feld, keine Migration, `STORE_SCHEMA_VERSION` bleibt
**5** (Backup/Restore/CSV bleiben unberührt, §10).

### 2.2 Service `health_o_mat.add_lab_report`

| Feld | voluptuous | services.yaml | Pflicht | Semantik |
|---|---|---|---|---|
| `person` | `vol.Optional("person"): str` | Textfeld | nein | leer = einzige konfigurierte Person (`get_runtime_data`) |
| `ts` | `vol.Optional("ts"): str` | **Textfeld mit `example`** (kein Selector — Angleich an `add_lab_value`, `services.yaml:418-423`) | nein | **ein** Zeitpunkt für den ganzen Bericht; Regeln unverändert (≤ 5 Min Zukunft, ≥ 1900) |
| `report_ref` | `vol.Optional("report_ref"): str` | Textfeld | nein | freier Tag, `.strip()[:500] or None` — identisch zu `__init__.py:766` |
| `values` | `vol.Required("values"): vol.All(cv.ensure_list, [vol.Schema({...})])` | `object` **mit `fields`** + `multiple: true` (siehe unten) | **ja** | Liste aus `{marker, value, unit}` |

Service-Name **`add_lab_report`** (ein Bericht = ein Vorgang). `add_lab_value` bleibt
unverändert der schnelle Tagespfad.

```yaml
# services.yaml — `fields` macht den Object-Selector im Editor überhaupt erst bedienbar
add_lab_report:
  name: Laborbericht erfassen
  description: >-
    Erfasst mehrere Laborwerte eines Berichts in einem Vorgang — gleicher Zeitpunkt,
    gleiche Berichts-Referenz, Alles-oder-nichts (eine ungültige Zeile lehnt den
    gesamten Bericht ab). Leere Zeilen werden ignoriert.
  fields:
    person:
      name: Person
      description: Name der Person (leer = einzige konfigurierte Person).
    ts:
      name: Zeitpunkt
      description: >-
        Zeitpunkt des Berichts als ISO 8601 (z. B. 2026-11-01T09:15 oder mit Offset).
        Leer = jetzt. Höchstens 5 Minuten in der Zukunft, nicht vor 1900.
      example: "2026-11-01T09:15:00+01:00"
    report_ref:
      name: Berichts-Referenz
      description: >-
        Optionaler Link oder externe ID des Laborberichts (max. 500 Zeichen).
        Nur Referenz, Health-O-Mat ruft die URL nie selbst auf.
      example: "https://example.com/laborbericht/123"
    values:
      name: Werte
      description: Zeilen aus Marker, Wert und (optionaler) Einheit.
      required: true
      selector:
        object:
          multiple: true
          label_field: marker
          fields:
            marker:
              label: Marker
              required: true
              selector:
                select:
                  custom_value: true
                  options:
                    - {label: "ALT (GPT)", value: "alt"}
                    - {label: "AST (GOT)", value: "ast"}
                    - {label: "GGT (Gamma-GT)", value: "ggt"}
                    - {label: "Bilirubin gesamt", value: "bilirubin_total"}
                    - {label: "Gesamteiweiß", value: "total_protein"}
                    - {label: "Kreatinin", value: "creatinine"}
                    - {label: "eGFR", value: "egfr"}
                    - {label: "Harnstoff", value: "urea"}
                    - {label: "Protein/Kreatinin-Quotient (Urin)", value: "urine_protein_creatinine_ratio"}
                    - {label: "Natrium", value: "sodium"}
                    - {label: "Kalium", value: "potassium"}
                    - {label: "Calcium gesamt", value: "calcium"}
                    - {label: "Magnesium", value: "magnesium"}
                    - {label: "Chlorid", value: "chloride"}
                    - {label: "Gesamtcholesterin", value: "cholesterol_total"}
                    - {label: LDL, value: "ldl"}
                    - {label: HDL, value: "hdl"}
                    - {label: Triglyceride, value: "triglycerides"}
                    - {label: TSH, value: "tsh"}
                    - {label: fT4, value: "ft4"}
                    - {label: fT3, value: "ft3"}
                    - {label: Hämoglobin, value: "hemoglobin"}
                    - {label: Leukozyten, value: "leukocytes"}
                    - {label: Thrombozyten, value: "platelets"}
                    - {label: CRP, value: "crp"}
                    - {label: BSG, value: "esr"}
                    - {label: Lipase, value: "lipase"}
                    - {label: Amylase, value: "amylase"}
                    - {label: "Tacrolimus (Talspiegel)", value: "tacrolimus"}
            value:
              label: Wert
              required: true
              selector:
                number: {step: any, mode: box}   # UI-Komfort; keine Server-Bereichsprüfung
            unit:
              label: Einheit
              selector:
                text:
```

Die 29 `options` der Marker-Auswahl sind 1:1 aus `add_lab_value`
(`services.yaml:337-405`) übernommen; `custom_value: true` hält Custom-Marker-Keys und
Aliase (`gpt`/`got`/`gamma_gt`) als Freitext gültig (Auflösung wie dort, §2.4).

Voluptuous (Handler prüft fein, siehe unten):

```python
vol.Required("values"): vol.All(
    cv.ensure_list,
    [
        vol.Schema(
            {
                # BEWUSST Optional: die UI sendet auch leere Zeilen ("＋ Zeile"),
                # und ein `{}`-Eintrag darf NICHT am Transportrand scheitern —
                # er ist eine ignorierte Leerzeile (§2.3). "Pflicht" ist eine
                # Handler-Regel für NICHT-leere Zeilen, keine Schema-Regel.
                vol.Optional("marker"): str,                      # strikt String, kein Coerce
                vol.Optional("value"): vol.Any(str, int, float),  # Coerce erst im Handler
                vol.Optional("unit"): vol.Any(str, None),
            }
        )
    ],
),
```

`marker: str` (kein Coerce), `value` wird **im Handler** zu Zahl geprüft — inklusive
`bool`-Ablehnung (`True`/`False` sind in Python `int`, aber kein Messwert), `unit: str|None`.
Der Grund: Schema-Fehler liefern generische HA-Meldungen ohne Zeilenbezug; gefordert sind
präzise Codes pro Zeile (§2.4). Dasselbe Muster nutzt der WS-Pfad bereits
(`ws_api.py:1336-1342`).

**Warum `Optional` und nicht `Required`:** Mit `vol.Required` würde ein `{}`-Eintrag (oder
eine Zeile mit ausschließlich leeren Strings) schon vom Schema abgewiesen — das widerspricht
dem Versprechen „leere Zeilen werden ignoriert". Die Pflicht-Semantik ist deshalb bewusst in
den Handler verlagert (§2.3). Der `required: true`-Marker in den services.yaml-`fields`
(§2.2) ist reiner **Editor-Komfort** für manuelle YAML-/Formular-Nutzung und hat auf den
Service-Aufruf keine Wirkung.

### 2.3 Zeilen-Form

```yaml
values:
  - marker: alt          # Pflicht; Alias/Katalog/Custom wie add_lab_value
    value: 32            # Pflicht; Zahl oder numerischer String, kein bool
    unit: U/L            # optional; kanonische ODER Alt-Einheit
```

**Leer-Zeilen-Regel:** Eine Zeile ist *leer*, wenn `marker` leer/whitespace **und** `value`
leer/whitespace **und** `unit` leer ist. Das gilt ausdrücklich auch für `{}` und für Zeilen,
in denen alle drei Werte `""` sind (beide werden vom Schema durchgelassen, §2.2). Leere
Zeilen werden **ignoriert** (Teilmenge ist erlaubt). Jede *nicht* leere Zeile muss
vollständig valide sein: fehlender `marker` → `unknown_marker`, fehlender/nicht numerischer
`value` → `invalid_value`.

**Zuständigkeit der HA-freien Prüffunktion** (ein Pfad für Service und WS):

```python
def validate_lab_report_rows(
    values: Any, custom_markers: Any = None
) -> tuple[list[dict], str | None]:
    """Leerzeilen filtern, Zeilen validieren, in kanonische Einheiten konvertieren.

    Rückgabe: (konvertierte Zeilen, Fehlermeldung oder None). Die Fehlermeldung ist
    bereits im Vertragsformat "<code>" bzw. "<code>: Zeile <n> (<detail>)" (§2.4) —
    der Aufrufer reicht sie nur noch weiter (ServiceValidationError / send_error).
    """
```

- **In der Funktion:** `empty_report`, `too_many_rows`, `unknown_marker`, `unit_required`,
  `invalid_value`, `unsupported_unit`, `duplicate_marker`.
- **Nicht in der Funktion:** `invalid_ts` (Zeitpunkt ist ein Batch-weites Feld außerhalb der
  Zeilenliste; Aufrufer prüft ihn) und die Personenauflösung (`get_runtime_data` bzw.
  `_runtime_entry` — HA-gebunden, nicht HA-frei).
- **Rückgabe statt Exception:** `tuple[..., str | None]` folgt dem Haus-Muster
  `resolve_lab_marker → None bei kein Treffer`; der Aufrufer entscheidet, ob daraus ein
  `ServiceValidationError` oder ein `send_error` wird. Erster Fehler gewinnt, keine
  Fehlerliste (ein Bericht wird als Ganzes korrigiert).

### 2.4 Validierungsreihenfolge & Fehlercodes

Alle Prüfungen laufen **vor** jedem Schreibzugriff; die Reihenfolge ist deterministisch:

0. **Person-Auflösung (zuerst, kein neuer Code):** Service `get_runtime_data(hass, call)`,
   WS `_runtime_entry` + `_entry_ready` (`ws_api.py:1320-1325`, Fehler via
   `_send_entry_error`). Das läuft zwangsläufig vor allem anderen — ohne `entry_id` gibt es
   weder `entry.options` (Custom-Marker) noch eine Person. Ein unbekannter/nicht geladener
   Entry meldet also den bestehenden Entry-Fehler, **nicht** `invalid_ts`.
1. **`invalid_ts`** — `ts` nicht ISO-8601 / > 5 Min Zukunft / < 1900. Eigener Code, weil
   der Zeitpunktfehler den ganzen Batch betrifft und für Aufrufer klar von Zeilenfehlern
   trennbar sein muss.
   - **Herkunft der Meldung:** `ws_api.parse_entry_ts` (`ws_api.py:806-817`) und
     `_service_entry_ts` (`__init__.py:592-605`) liefern heute **Prosa ohne Code**
     (`logic.ENTRY_TS_INVALID_MESSAGE`, `logic.py:158-161`; Grenze `logic.ENTRY_TS_MIN`,
     `logic.py:155`) — der Service wrappt sie als `ServiceValidationError`, der WS-Pfad als
     `send_error` (`ws_api.py:1345-1349`).
   - **Batch-Regel:** Beide Aufrufer wrappen die Meldung als
     `f"invalid_ts: {message}"` (Code-Prefix + unveränderte Prosa). Kein Umbau von
     `parse_entry_ts`/`ENTRY_TS_INVALID_MESSAGE` (deren Vertrag gilt für alle Services) —
     das Präfix ist Batch-Aufrufer-Sache.
2. **`empty_report`** — `values` leer **oder** alle Zeilen leer.
3. **`too_many_rows`** — mehr als **200** nicht-leere Zeilen (Server-Limit, unabhängig
   von der UI-Grenze). Zählt nur befüllte Zeilen.
4. **Zeilen in Listenreihenfolge** (erste fehlerhafte Zeile gewinnt):
   1. **`unknown_marker`** — Alias → Katalog → Custom ohne Treffer
      (`logic.resolve_lab_marker`, `logic.py:1076-1089`).
   2. **`unit_required`** — `require_explicit_unit` gesetzt und `unit` fehlt/leer
      (heute nur `urine_protein_creatinine_ratio`, Katalog in `const.py`).
   3. **`invalid_value`** — `value` nicht numerisch (inkl. `bool`), nicht endlich
      (`NaN`/`±inf`) oder nicht castbar.
   4. **`unsupported_unit`** — `logic.convert_lab_value` wirft `ValueError`
      (`logic.py:1091-1112`).
5. **`duplicate_marker`** — derselbe *aufgelöste* `marker_key` mehrfach im Batch
   (Alias-Kollision zählt: `gpt` + `alt` = Duplikat); gemeldet auf der zweiten
   Vorkommnis-Zeile.
6. **Schreiben** — alle Zeilen konvertiert (kanonischer Wert + `reported_*`), dann **ein**
   Store-Write, **ein** Audit-Eintrag, **ein** `signal_refresh`.

> **Numerische Prüfung ist Vorbedingung der Einheitenprüfung:** `convert_lab_value`
> beginnt mit `float(value)` und würde bei `"abc"` einen `ValueError` werfen, der sonst
> fälschlich als `unsupported_unit` klassifiziert würde. Deshalb steht `invalid_value`
> **vor** `unsupported_unit` — so bleibt `unsupported_unit` exakt der Einheiten-Fall.
>
> **Ein Helper für beide Pfade:** `logic.coerce_lab_number(value)` (HA-frei) prüft
> „Zahl, kein `bool`, endlich" und liefert `float` oder `None`. Batch **und** der
> bestehende Einzelpfad (`add_lab_value` Service + WS) nutzen ihn — der Einzelpfad wird
> damit ebenfalls `NaN`/`inf`-fest und meldet `invalid_value` statt einer
> `float()`-Exception (`__init__.py:761-765`, `ws_api.py:1336-1342`).

**Meldungsformat:** `"<code>"` ohne Zeilenbezug (`invalid_ts`, `empty_report`,
`too_many_rows`) bzw. `"<code>: Zeile <n> (<detail>)"` mit 1-basierter Zeile, z. B.
`unknown_marker: Zeile 3 (gptx)`. Der **Code-Prefix** (alles vor dem ersten `:` bzw.
Whitespace) ist der stabile Maschinenteil; die UI mappt darauf (heutige
`errorMessage()`-Tabelle matcht exakte Strings und wird auf Prefix umgestellt,
`health-o-mat-labs-card.js:202-212`).

**Kein Teilzustand:** Ein Fehler hinterlässt weder Lesungen noch Audit-Einträge.

### 2.5 Duplikate im Batch

**Ganzer Batch abgelehnt (`duplicate_marker`).** Alle Zeilen teilen `ts` und `report_ref`;
zwei Werte desselben Markers zum selben Zeitpunkt aus demselben Bericht sind ein
Eingabefehler (doppelt eingefügt), kein Datenzustand. „Last wins" würde stillschweigend
Daten verschlucken — gegen die Grundhaltung von REQ-HOM-122. Ein echter Zweitwert ist ein
separater Aufruf/Bericht.

### 2.6 Antwort / Ergebnis

| Aufrufer | Ergebnis |
|---|---|
| Service | **kein** Rückgabewert — konsistent zu allen bestehenden Services (kein `SupportsResponse`/`ServiceResponse` im Repo). Fehler = `ServiceValidationError`. |
| WS | `connection.send_result(msg["id"], {"written": n, "ts": ts_iso})` |

`n` = Anzahl tatsächlich geschriebener Werte (ohne ignorierte Leerzeilen). Ein
Service-Response wird **nicht** eingeführt (neues Muster, kein Bedarf).

### 2.7 Store-API

```python
async def add_lab_readings(
    self, entry_id: str, ts_iso: str, rows: list[dict], report_ref: str | None = None,
    created_ts_iso: str | None = None, actor: str | None = None,
    audit_limit: int = DEFAULT_AUDIT_LIMIT,
) -> list[str]:  # -> geschriebene Reading-IDs (für den Audit-Eintrag)
```

`rows` = bereits konvertierte, validierte Zeilen (`{marker_key, value, unit,
reported_value, reported_unit}`). Ablauf: **einmal** `_append_audit`, **einmal**
`_async_save()` — mit **Rollback** (siehe unten). `add_lab_reading` (Singular,
`store.py:641-680`) bleibt für den Einzelpfad.

**Rollback bei Save-Fehler (damit „Alles-oder-nichts" auch für den Persistenzschritt gilt):**

```python
entry = self.entry(entry_id)
readings_before = list(entry.get("lab_readings") or [])   # flache Kopie reicht
audit_before = list(entry.get("audit_log") or [])
try:
    append_rows(entry, rows)          # in-memory ergänzen
    self._append_audit(...)           # ein Eintrag (kann den Cap anwenden!)
    await self._async_save()
except Exception:
    entry["lab_readings"] = readings_before   # exakt der Vorzustand
    entry["audit_log"] = audit_before         # auch gekappte Alt-Einträge zurück
    raise
```

- Vollständige **Listenkopien** statt Längen-Slices: `_append_audit` kann den Audit-Ring
  kappen (`_prune_audit`, `store.py:385-394`) — ein Slice-Rollback würde gekappte
  Alt-Einträge nicht wiederherstellen.
- Flache Kopie genügt: der Batch fügt nur Dict-Referenzen hinzu/entfernt sie, mutiert keine
  bestehenden Einträge.
- Nach dem Rollback ist der In-Memory-Zustand identisch zum Zustand vor dem Aufruf; der
  Fehler wird weitergereicht (Service: `ServiceValidationError`, WS: `send_error`).

### 2.8 Audit-Log: ein Eintrag pro Batch

```
action = "lab_values_added", kind = "lab_readings", target_id = None,
details = {"count": n, "marker_keys": [...], "reading_ids": [...]}
```

- **Ein** Eintrag, weil (a) `audit_log` ein gekappter Ring ist (`_prune_audit`,
  `store.py:385-394`) — 29 Einträge würden unbeteiligte Historie verdrängen, (b) der
  Vorgang fachlich ein Ereignis ist, (c) einzelne Löschungen granular bleiben
  (`void_lab_reading` → `entry_voided` mit Reading-ID, `store.py:727-754`).
- **Datenminimierung:** `report_ref` steht **nicht** in den Details (Freitext, potenziell
  ein Cloud-Link). Anker sind `reading_ids` (Nachvollziehbarkeit/Batch-Zusammenhang via
  `created_at` der Einträge) — beide Listen auf je **20** Einträge gekappt; `count` trägt
  die volle Zahl. Keine Messwerte in `details` (bestehende Regel,
  `_append_audit`-Docstring `store.py:344-348`).
- Aktionsname **`lab_values_added`** (Plural = Batch); der Einzelpfad behält
  `lab_value_added` (`store.py:671-679`). Service-Name bleibt `add_lab_report`.

### 2.9 `report_ref` / `ts`

Identisch zu `add_lab_value`: `report_ref` getrimmt auf
`LAB_REPORT_REF_MAX_LEN = 500` (`const.py:501`), rein referenzierend, wird nie
abgerufen; `ts` ein Wert für den ganzen Bericht mit denselben Grenzen.

### 2.10 YAML-Aufrufbeispiel (Hauptnutzen für externe Systeme)

```yaml
action: health_o_mat.add_lab_report
data:
  person: "Caro"
  ts: "2026-11-01T09:15:00+01:00"
  report_ref: "https://example.com/laborbericht/123"
  values:
    - {marker: alt, value: 32, unit: U/L}
    - {marker: creatinine, value: 1.1, unit: mg/dL}
    - {marker: crp, value: 4.8, unit: mg/L}
    - {marker: tsh, value: 1.9}            # unit fehlt = kanonische Einheit
```

Ein Aufruf = ein Bericht. Über die bestehende REST-API
(`POST /api/services/health_o_mat/add_lab_report`) genauso nutzbar — kein neuer
Webhook/Endpunkt. Zwei Werte desselben Markers im selben Aufruf → `duplicate_marker`.

### 2.11 Idempotenz — dokumentierte Grenze

Der Service ist **nicht** idempotent: derselbe Aufruf zweimal erzeugt zweimal dieselben
Lesungen (kein Dedupe über `ts`+`marker`+`value`, konsistent zu `add_lab_value` und zum
CSV-Import-Verhalten). Begründung: ein impliziter Dedupe-Schlüssel würde echte
Wiederholungsmessungen verschlucken. **Mitigation:** (a) UI nutzt Single-Flight
(`_saving`-Muster wie `health-o-mat-labs-card.js:746-748, 786-801`), (b) Aufrufer
schickt den Bericht nur einmal, (c) Korrektur über die bestehenden Wege
`void_entry`/`restore_entry` bzw. `remove_last_lab_value`. Diese Grenze gehört in die
Service-`description` („erneuter Aufruf schreibt erneut").

---

## 3. WS-Request-Vertrag

Neues Kommando `health_o_mat/add_lab_report` (registriert neben `COMMAND_ADD_LAB_VALUE`,
`ws_api.py:107, 978`), damit die UI Karten-Fehlermeldungen statt Service-Toasts bekommt —
gleiche Begründung wie `add_lab_value` (`ws_api.py:1313-1318`).

```jsonc
{
  "id": 12,
  "type": "health_o_mat/add_lab_report",
  "entry_id": "<config-entry-id>",        // Pflicht (string)
  "ts": "2026-11-01T09:15:00+01:00",      // optional
  "report_ref": "https://…",              // optional, max. 500 Zeichen
  "values": [                             // Pflicht; Zeilenfelder sind Optional (§2.2)
    {"marker": "alt", "value": 32, "unit": "U/L"},
    {"marker": "crp", "value": 4.8},
    {}                                    // erlaubt = ignorierte Leerzeile
  ]
}
```

- Schema `PREVENT_EXTRA`: innere Objekte listen **nur** `marker`/`value`/`unit` —
  unbekannte Felder werden am Transportrand abgewiesen (wie
  `health_o_mat/add_lab_value`). Die drei Felder sind **optional** (Leerzeilen-Regel
  §2.3), `values` selbst ist Pflicht.
- `entry_id` ist **Pflicht** und muss eine geladene Person sein; sonst
  `_send_entry_error` (bestehender Pfad, `ws_api.py:1320-1325`).
- Fehler-Transport: `connection.send_error(msg["id"], ERR_INVALID_FORMAT, "<code>[: Zeile n (detail)]")`
  — Codes exakt wie §2.4, transportiert als Nachrichtentext (bestehendes Muster,
  `ws_api.py:1304-1307`).
- Erfolg: `send_result(msg["id"], {"written": n, "ts": ts_iso})`.
- `signal_refresh(hass, entry_id)` vor dem Result (bestehendes Muster).

---

## 4. Datenfluss

```
Service add_lab_report ─┐
                        ├─► get_runtime_data(hass, call)                 # 0) entry_id + Person
WS add_lab_report ──────┘   │                                             (WS: _runtime_entry)
                            ▼
                     options = entry.options                          # lab_custom_markers
                            │
                            ▼
             ts prüfen ( Aufrufer, NICHT der Helper )                  # 1) invalid_ts
                            │
                            ▼
   rows, error = logic.validate_lab_report_rows(values, custom_markers)  # HA-frei
        ├── Leerzeilen filtern, empty_report / too_many_rows
        ├── resolve_lab_marker(alias → Katalog → Custom)               # logic.py:1076
        ├── unit_required / invalid_value / unsupported_unit
        ├── convert_lab_value → (canonical value, canonical unit)      # logic.py:1091
        └── duplicate_marker                                            # aufgelöste Keys
                            │  error != None → Abbruch, KEIN Write
                            ▼
        store.add_lab_readings(entry_id, ts_iso, rows, report_ref=…)
        ├── Listen-Snapshot (readings/audit)
        ├── append aller Lesungen + _append_audit("lab_values_added", …)
        ├── genau ein _async_save()
        └── Exception → Snapshot zurückrollen, re-raise                  # §2.7
                            │
                            ▼
                 signal_refresh(hass, entry_id)                        # 1 Coordinator-Refresh
```

- **Ein** Prüfpfad für beide Aufrufer (`logic.validate_lab_report_rows`) — Service und WS
  können nicht auseinanderlaufen. Signatur/Rückgabe: §2.3, Fehlercodes: §2.4.
- Der Helper prüft **nicht** `ts` und löst **keine** Person auf (HA-gebunden bzw.
  Batch-weites Feld) — beides macht der Aufrufer davor.
- Custom-Marker kommen aus `entry.options[OPTION_LAB_CUSTOM_MARKERS]`
  (`logic.effective_lab_markers` → `normalize_lab_custom_markers`).
- Keine Store-Änderung ohne vollständig validierten Batch; `_async_save()` wird genau
  einmal aufgerufen (Test: Call-Count 1), bei Fehler greift der Rollback (§2.7).

---

## 5. Alternativen & Trade-off

| Ansatz | Vorteil | Nachteil / Grund der Ablehnung |
|---|---|---|
| **Neu: `add_lab_report`** (gewählt) | atomar, ein `ts`/`report_ref`, ein Write/Refresh/Audit; sauberer Vertrag für externe Systeme | dritter Schreibpfad neben `add_lab_value` und CSV-Import (gemeinsame HA-freie Validierung begrenzt die Duplikation) |
| `add_lab_value` um eine Liste erweitern (Union-Typ) | nur ein Service | bricht den klaren Einwert-Vertrag; `vol.Schema`-Union wird unlesbar, die Pflicht-Semantik von `marker`/`value` müsste je Variante unterschiedlich sein (Einwert: `Required`, Batch: `Optional` + Leerzeilen-Regel); UI-Automation-Editor zeigt dann Mischformulare |
| Nur CSV-Import-Weg (`lab_values.csv` hochladen) | kein neuer Service | verlangt Datei-Handling, keinen Zeitstempel je Bericht, keine sofortige Validierungsrückmeldung, kein Live-Push für Skripte; außerdem war der Import bewusst tolerant (rejected-Zeilen) — Batch muss streng sein |
| Automation-Loop über `add_lab_value` (n Aufrufe) | kein Code | Teilzustand bei Zeilenfehler, n Writes/Refreshes/Audits, `ts`/`report_ref` je Zeile zu wiederholen — genau das Problem aus §1 |
| UI-seitig sequenziell mehrere WS-Calls | kein neues Backend-Kommando | gleiche Teilzustands-/Refresh-Probleme, Fehlerzuordnung über mehrere Antworten |

---

## 6. UI: Mehrzeilen-Dialog

### 6.1 Aufbau

Karte/Abschnitt **„Laborbericht erfassen"** — zusätzlich zum bestehenden Einzelformular,
das unverändert bleibt:

```
▸ Laborbericht erfassen
  Zeitpunkt: [ 2026-11-01 09:15 ]   Bericht-Link/ID: [ https://…        ]
  ┌──────────────────────────────────────────────────────────────┐
  │ Marker [ ALT (GPT)      ▾ ]  Wert [ 32   ]  Einheit [ U/L  ] ✕ │
  │ Marker [ Kreatinin      ▾ ]  Wert [ 1.1  ]  Einheit [mg/dL ] ✕ │
  │ Marker [ — bitte wählen ▾ ]  Wert [      ]  Einheit [      ] ✕ │
  └──────────────────────────────────────────────────────────────┘
  [ ＋ Zeile ]                                   [ Bericht speichern ]
```

- Gemeinsame Felder: `ts` (`datetime-local`, leer = jetzt), `report_ref` (Text).
- Zeile: Marker-Select (Katalog + Custom, nach Kategorie gruppiert), Wert, Einheit
  (Placeholder = kanonische Einheit, wie `_updateUnitPlaceholder()`,
  `health-o-mat-labs-card.js:721-728`), Entfernen.
- `＋ Zeile` fügt eine leere Zeile hinzu; Start = 1 Zeile; UI-Soft-Cap **60**
  (Render-Schutz). Server-Limit bleibt 200 (§2.4).
- Leere Zeilen werden beim Absenden übersprungen (Server-Regel §2.3).

### 6.2 Client- vs. Server-Validierung

| Prüfung | Client | Server | Begründung |
|---|---|---|---|
| mind. eine befüllte Zeile | ✅ | ✅ | sofortiges Feedback (`empty_report`) |
| Wert numerisch & endlich | ✅ | ✅ | `invalid_value` |
| Zeitpunkt plausibel | ✅ | ✅ | bestehende `_readEntryTs`-Logik (`…labs-card.js:730-744`) |
| Marker auflösbar | ❌ | ✅ | Client kennt die Alias-Tabelle nicht (`LAB_MARKER_ALIASES` ist nicht im `panel_data`-Payload, `ws_api.py:660-678`) |
| Einheit unterstützt | ❌ | ✅ | `panel_data` liefert je Marker nur `unit` (kanonisch), **kein** `alt_units` (`ws_api.py:665`) |
| `require_explicit_unit` beachtet | ❌ | ✅ | Flag nur in `settings.lab_catalog` (`ws_api.py:1659`), nicht in `panel_data` |
| Duplikat | ⚠️ optional | ✅ | Client kennt nur Select-Werte, keine aufgelösten Keys (Alias/Custom) |

**Bewusst:** `panel_data` wird **nicht** um `alt_units`/`require_explicit_unit` erweitert
(Payload-Wachstum für eine Komfortprüfung, die der Server abschließend macht — YAGNI).

### 6.3 Card vs. Panel — Duplikations-Entscheidung

Die Labs-Card ist **standalone** (eigene `escapeHtml`/`t`/`labDisplayName`-Kopien, keine
Imports aus `health-o-mat-panel-*.js`), das Panel nutzt `health-o-mat-panel-base.js`.
Wie bei den bestehenden Rendering-Helfern wird der Dialog **je Datei einmal**
implementiert, nicht in ein neues Shared-Modul extrahiert:

- Card: `_reportForm()` + `_reportDraft` + `_saveReport()`.
- Panel: `labsReportForm(panel, …)`; Draft **defensiv** lesen —
  `panel._labReportDraft && panel._labReportDraft[entryId]` (Muster wie
  `panel._labCustomDraft`, `health-o-mat-panel.js:1155-1159`; nie auf existierendes Feld
  vertrauen, Panel-Instanzen überleben Hot-Reloads nicht garantiert).
- Parität sichern **Tests**, die beide Dateien auf dieselben Regeln und dieselbe
  Fehlercode-Tabelle prüfen (§12) — nicht ein Shared-Modul. Ein Extrakt lohnt erst beim
  dritten Konsumenten.

### 6.4 Absende-Pfad, Reset-Semantik, Single-Flight

- Card und Panel senden über WS `health_o_mat/add_lab_report` (§3), **nicht** über den
  Service.
- **Single-Flight:** `_saving`-Flag blockiert Doppel-Submit (Muster
  `…labs-card.js:746-748, 786-789`); Button ist während des Sendens disabled.
- **Reset bei Erfolg (bewusste Abweichung vom Einzelformular):**
  - **geleert:** alle Wert-Felder und die Zeilenliste (auf eine leere Zeile zurück)
  - **bleiben stehen:** `ts` und `report_ref` — der Bericht-Kontext gilt für
    Folgekorrekturen (z. B. Nachtrag eines vergessenen Markers aus demselben Befund).
  - Begründung der Abweichung: das Einzelformular leert `value`, `ts` und `reportRef`
    (`…labs-card.js:790-795`), weil dort jeder Wert ein eigener Vorgang mit eigenem
    Zeitpunkt ist. Beim Bericht ist genau das Gegenteil richtig — der Zeitpunkt gehört
    zum Dokument, nicht zur Zeile; ihn zu leeren würde beim Nachtrag einen falschen
    (neuen) Zeitpunkt erzeugen.
- **Ablehnung:** Fehlerbanner mit Code + Zeilenbezug; **alle** Eingaben bleiben erhalten
  (Draft wird nicht geleert), keine Daten-Reload-Nebenwirkung.
- Nach Erfolg: `_loadData(true)` / Panel-Refresh (Server hat bereits `signal_refresh`
  gefeuert).

---

## 7. Admin-UI: Umrechnungen sichtbar

**Ist (verifiziert):** Die Referenztabelle rendert Kategorie, Name, `canonical_unit`,
Referenzbereich, Reset (`health-o-mat-panel-admin.js:365-389`, Kopf 429-438) — `alt_units`
wird nicht genutzt, obwohl der Kommentar es nennt (354-355). Custom-Marker zeigen ihre
Alt-Einheit (`altUnitText`, 360-363, 402-413), aber ohne Faktor.

**Änderung (reines Frontend, keine neue Server-API):**

1. **Pflicht:** neue Spalte **„Umrechnung"** in der Katalog-Tabelle. Je `alt_units`-Paar:
   `{Alt-Einheit} × {factorText} → {canonical_unit}` — `factorText` ist **immer** das
   Ergebnis von `formatNumber(factor)`, nie ein Literal. Ergebnis z. B. de: `mg/dL × 17,1 →
   µmol/L`, en: `mg/dL × 17.1 → µmol/L`. Leeres `alt_units` → `—`.
   - **Faktor locale-fähig** über den vorhandenen Formatter
     `formatNumber` (`health-o-mat-panel-base.js:752-759`, `Intl.NumberFormat(intlLocale())`)
     — kein hartkodiertes Komma, keine String-Konkatenation des Rohwerts.
   - Richtung ist immer „Alt-Einheit → kanonische Einheit" (so ist `alt_units` definiert:
     `{unit: factor_to_canonical}`).
2. **Pflicht:** Marker mit `require_explicit_unit: true` bekommen in derselben Spalte ein
   Badge **„Einheit Pflicht"** (dort ist die Verwechslungsgefahr g/g vs. mg/g am größten).
3. **Nice-to-have, zuletzt:** Custom-Marker-Zeile um den Faktor ergänzen —
   `Vitamin D (vitamin_d) — ng/mL · alt: nmol/L × {formatNumber(factor)}`, gleiche
   Code-Stelle (`altUnitText`); kein hartkodiertes Komma. Fällt bei Zeitdruck weg, ohne die
   Pflichtteile zu berühren.

**Nachweis „keine Server-API nötig":** `build_settings()` liefert
`"lab_catalog": {"categories": LAB_CATEGORIES, "markers": LAB_MARKERS}`
(`ws_api.py:1655-1659`) — verbatim inkl. `alt_units` und `require_explicit_unit`.

**Neue i18n-Keys** (de/en in `strings.json` + `translations/{de,en}.json`, Paritätstest
N-10): `ui_admin_lab_conversion`, `ui_admin_lab_conversion_required`,
`ui_admin_lab_conversion_none`. Aufnahme in die Whitelist
`_REQ_HOM_122_UI_KEYS` (`tests/test_translations.py:506-541`, geprüft von
`test_req_hom_122_common_ui_keys_exist_in_all_three_files`, 544-551).

---

## 8. Medizin-Hinweis im Panel (v1: immer sichtbar)

**Ist (verifiziert):**

- Card: Disclaimer vorhanden, Default **an**, per Editor-Checkbox bzw.
  `show_disclaimer: false` abschaltbar (`health-o-mat-labs-card.js:250, 363, 864-866,
  1289`). Text (hartkodiert deutsch): `⚠️ Hinweis: keine medizinische Beratung —
  Richtwerte, keine Diagnose. Referenzbereiche in den Einstellungen anpassen.`
- Panel: Der Lab-Tab (`labsTab`, `health-o-mat-panel-views.js:1066-1117`) rendert keinen
  Hinweis; nur der globale Footer `Health-O-Mat · keine medizinische Beratung`
  (`health-o-mat-panel.js:1983-1987`) — kontextlos, ohne den „Referenzbereiche
  anpassen"-Teil, den Spec §1 für den Lab-Kontext verlangt.

**Änderung (v1, ohne Toggle):**

- Der Lab-Tab rendert **oberhalb** der Kategorie-Leiste eine Hinweiszeile mit
  **identischem Wortlaut** zur Card über den i18n-Key `ui_panel_lab_disclaimer`
  (`de` = exakt obiger Card-Text, `en` = sinngemäße Übersetzung; Aufnahme in
  `_REQ_HOM_122_UI_KEYS`).
- **Immer sichtbar** — keine Option, kein `panel_data`-Feld, kein Backup-Eintrag, keine
  Änderung an `SETTINGS_KEYS` (`ws_api.py:192-209`), `SETTINGS_SCHEMA`, `build_settings`
  oder `restore.py`.
- **CSS:** Die Klasse `.labs-disclaimer` existiert nur in `CARD_CSS` der Labs-Card
  (`health-o-mat-labs-card.js:276-279`). Für das Panel wird sie in `PANEL_CSS`
  (`health-o-mat-panel-base.js:275 ff.`) neu angelegt — gleiche Optik, getrennte
  Stylesheets (Card und Panel teilen kein CSS).

**Warum kein Toggle in v1 (bewusste Entscheidung):** Ein Panel-seitiger Schalter müsste
den Zustand im Nicht-Admin-Kontext kennen. `get_settings` ist **admin-only**
(`ADMIN_ONLY_COMMANDS`, `ws_api.py:129-131`; `is_admin_connection`-Check
`ws_api.py:1736-1738`), `panel._settings` ist im Lab-Tab normaler Nutzer also leer —
ein darauf gestütztes Flag wäre für Nicht-Admins wirkungslos oder würde still auf
„versteckt" fallen. Eine spätere additive Nachrüstung (falls gewünscht) läuft über ein
Feld im `panel_data`-Payload, nicht über `get_settings`; das ist ausdrücklich **nicht**
Teil dieses Konzepts (§14.4).

---

## 9. Beispiel-Dashboard `examples/dashboard-labs-card.yaml`

Im Stil von `examples/dashboard-card.yaml` (Kommentar-Kopf, Import-Hinweis, mehrere
Ansichten). **Wichtig:** `tests/test_dashboards.py` sammelt **alle** `examples/*.yaml` und
verlangt je Datei Entity-Refs **oder** eine bekannte Karten-Konfiguration
(`test_dashboards.py:146-170`, `CARD_TYPE = "custom:health-o-mat-card"`, 108). Eine reine
Labs-Card-Datei fällt heute durch — daher §9.1 Testanpassung. Die Datei referenziert
**keine** Entities (die Labs-Card liest `panel_data`), sie muss über die erweiterte
Karten-Prüfung bestehen.

```yaml
# HA Health-O-Mat — Beispiel-Dashboard für die Laborwerte-Karte
# Import: Einstellungen → Dashboards → Dashboard hinzufügen → "Neues Dashboard aus YAML"
title: Health-O-Mat (Laborwerte)
views:
  - title: Laborwerte            # alle Defaults (Trend, Eingabe, Disclaimer an)
    path: laborwerte
    icon: mdi:flask-outline
    cards:
      - type: custom:health-o-mat-labs-card

  - title: Anzeige               # reine Anzeige, Personen-Dropdown gefiltert
    path: anzeige
    icon: mdi:eye-outline
    cards:
      - type: custom:health-o-mat-labs-card
        person_mode: selector             # Dropdown (kein fest verdrahteter Entry)
        # person_filter: ["max"]          # optional: Whitelist (entry_id/Slug/Name) —
        #                                 # anpassen oder auskommentiert lassen
        # default_person: "max"           # optional: Vorauswahl im Dropdown
        show_trend: true
        allow_manual_entry: false
        show_categories: ["liver", "kidney", "lipids"]   # Tab-Reihenfolge
        # show_disclaimer: false          # nur bewusst abschalten
```

`person_mode: selector` + `person_filter` statt `fixed` mit leerer `entry_id`: eine leere
`entry_id` bei `fixed` würde die Karte auf einen ungültigen Entry binden; das Dropdown ist
für ein Copy-Paste-Beispiel der robustere Default (`normalizeCardConfig`,
`health-o-mat-labs-card.js:234-252`).

**`person_filter`/`default_person` sind im Beispiel auskommentiert** — ein aktiver Filter auf
eine nicht existierende Person („max") würde die Karte in den Zustand „Keine Person passt zum
konfigurierten Personen-Filter."
(`health-o-mat-labs-card.js:462`) bringen. Der README-Hinweis zum Beispiel lautet deshalb:
„Personenfilter anpassen oder entfernen — ohne Filter zeigt die Karte alle Personen."

**§9.1 Testanpassung `tests/test_dashboards.py`:**

- `LABS_CARD_TYPE = "custom:health-o-mat-labs-card"` neben `CARD_TYPE` (Zeile 108).
- `LABS_CARD_KEYS = {"type", "entry_id", "person_mode", "person_filter",
  "default_person", "show_categories", "show_trend", "allow_manual_entry",
  "show_disclaimer"}` (Spiegel von `normalizeCardConfig`).
- `extract_card_configs` um den Labs-Typ erweitern bzw. eine zweite Sammel-Funktion;
  Key-Prüfung je Kartentyp gegen den passenden Key-Set.
- Die Assertion „Entity-Refs **oder** Karte" (Zeile 162) ist damit auch für
  Labs-Card-Dateien erfüllt.

Zusätzlich: Bullet in `README.md` (Beispiel-Liste `808-815`) und Verweis im
Labs-Card-Abschnitt (README 576-577).

---

## 10. Nicht-Ziele

- **Kein OCR-/Text-Parser** für Laborberichte („PDF reinwerfen" ist nicht Teil davon).
- **Kein `LabReport`-Aggregat**, keine Report-Entität, keine neue Tabelle, keine
  Gruppierungs-ID außer dem freien `report_ref`.
- **Kein Multi-Unit-Framework** — weiterhin genau ein optionales Alt-Einheit-Paar pro
  Custom-Marker; `alt_units` im Katalog unverändert.
- **Keine Änderung** an `unique_id`s, Entitäten oder Store-Schema (bleibt v5).
- **Batch-Daten verändern Backup/Restore/CSV nicht:** keine neuen Felder, kein neues
  Datensatz-Format, `lab_options`/`lab_values.csv`/Restore-Validierung bleiben
  unangetastet (nur §7-Admin und §8-Panel sind Frontend; §2 schreibt ausschließlich in
  die bestehende `lab_readings[]`-Liste).
- **Kein Service-Response** (`SupportsResponse`) und kein neuer Webhook/HTTP-Endpunkt.
- **Kein Panel-Disclaimer-Toggle in v1** (§8; spätere Nachrüstung über `panel_data`).
- `panel_data` wird **nicht** um `alt_units`/`require_explicit_unit` erweitert (§6.2).
- Card-Disclaimer-Umbau auf i18n ist **nicht** Teil (Bestand: hartkodiert deutsch).

---

## 11. Auswirkungen, REQ-IDs & Acceptance Criteria

| Artefakt | Auswirkung |
|---|---|
| REQ-HOM-122 | bleibt gültig; Kriterium „Medizin-Disclaimer in Card/Panel/README" (`REQUIREMENTS.md:1213`) wird durch REQ-HOM-125 präzisiert, nicht rückwirkend umformuliert |
| `services.yaml` | neuer Block `add_lab_report` mit `object`-Selector inkl. `fields` + `multiple` |
| `__init__.py` | Service-Handler + Registrierung; nutzt `logic.validate_lab_report_rows`; `add_lab_value` auf den gehärteten Zahlen-Helper umgestellt |
| `store.py` | `add_lab_readings` (ein Save, ein Audit-Eintrag, Reading-IDs, **Rollback** bei Save-Fehler) |
| `logic.py` | `validate_lab_report_rows(values, custom_markers) -> tuple[list[dict], str \| None]` + `coerce_lab_number(value)` (HA-frei; **kein** `ts`, **keine** Person) |
| `ws_api.py` | neues Kommando `health_o_mat/add_lab_report` (Zeilen-Schema mit `vol.Optional`); `invalid_ts:`-Präfix; **keine** Settings-Änderung (§8) |
| `backup.py` / `restore.py` / `exporter.py` / `importer.py` | **unverändert** |
| JS | `health-o-mat-labs-card.js` (Dialog, Prefix-Fehler-Mapping, Single-Flight), `health-o-mat-panel-views.js` (Dialog + Disclaimer), `health-o-mat-panel-admin.js` (Umrechnungs-Spalte), `health-o-mat-panel-base.js` (WS-Kommando-Name, `.labs-disclaimer` in `PANEL_CSS`) |
| i18n | UI-Keys in `strings.json`/`{de,en}.json` + `_REQ_HOM_122_UI_KEYS`; **zusätzlich** Service-Block `services.add_lab_report` in allen drei Dateien |
| Tests | `tests/test_dashboards.py` (§9.1), `tests/test_translations.py` (`_LAB_SERVICE_FIELDS`/`_LAB_TRANSLATED_FIELDS`), Marker-Options-Mirror in `tests/test_lab_services.py` (§12) |
| Doku | `README.md`, `docs/CONCEPT-UI.md`, `docs/REQUIREMENTS.md` |
| Store-Schema / Entities | **unverändert** |

**Vorgeschlagene REQ-IDs** (Requirements-Agent vergibt final). Reihenfolge:
123 → 125 → 124 → 126.

### REQ-HOM-123 — Batch-Erfassung (`add_lab_report`)
- [ ] Service: YAML-Beispiel aus §2.10 → `lab_readings` wächst um **4** Einträge, alle mit
      demselben `ts`/`report_ref`; der Service gibt **nichts** zurück (Vertrag §2.6).
- [ ] WS: derselbe Bericht liefert `send_result {"written": 4, "ts": …}`.
- [ ] Ungültige Zeile 3 (unbekannter Marker) → `ServiceValidationError` mit
      `unknown_marker: Zeile 3 (...)`; `lab_readings` **und** `audit_log` unverändert.
- [ ] Leerzeilen werden ignoriert: 3 Zeilen davon 1 leer → 2 Werte, kein Fehler.
- [ ] Fehlercodes in genau dieser Reihenfolge: `invalid_ts`, `empty_report`,
      `too_many_rows` (201 befüllte Zeilen), `unknown_marker`, `unit_required`,
      `invalid_value`, `unsupported_unit`, `duplicate_marker`.
- [ ] `gpt` + `alt` im selben Batch → `duplicate_marker` (Alias-Kollision).
- [ ] Genau **ein** `_async_save`, genau **ein** `signal_refresh`, genau **ein**
      Audit-Eintrag `lab_values_added` (ohne `report_ref`, `marker_keys`/`reading_ids`
      ≤ 20, `count` = volle Zahl).
- [ ] `add_lab_value` mit `NaN`/`inf` → `invalid_value` (gehärtet, gleicher Helper).
- [ ] WS: `send_result` mit `{"written": n, "ts": …}`; Fehler als `send_error` mit
      Code-Prefix; fehlendes `entry_id` → bestehender Entry-Fehler.

### REQ-HOM-124 — Admin-Sichtbarkeit der Umrechnungen
- [ ] Katalog-Tabelle zeigt für `creatinine` mit **Systemsprache DE** `mg/dL × 88,4 →
      µmol/L` und mit **EN** `mg/dL × 88.4 → µmol/L` (Test setzt die Sprache explizit;
      Faktor kommt aus `formatNumber`, kein hartkodiertes Trennzeichen).
- [ ] Marker mit leerem `alt_units` zeigen `—`.
- [ ] `urine_protein_creatinine_ratio` zeigt Badge „Einheit Pflicht" + Alt-Einheit.
- [ ] Kein neuer WS-Request/keine API-Änderung (Werte stammen aus `settings.lab_catalog`).
- [ ] Neue Keys in `strings.json`/`de`/`en` und in `_REQ_HOM_122_UI_KEYS`.
- [ ] (Nice-to-have) Custom-Marker-Zeile zeigt `alt: nmol/L × 0,4`.

### REQ-HOM-125 — Medizin-Hinweis im Panel-Lab-Tab
- [ ] Lab-Tab zeigt den Hinweis mit dem Card-Wortlaut (de) und einer englischen Fassung,
      **ohne** Admin-Rechte und ohne `get_settings`-Aufruf.
- [ ] Keine neue Option/Settings-Key/Backup-Feld vorhanden (Grep-Beleg, **auf
      `custom_components/` gescoped** — die Spec selbst enthält den String
      `lab_hide_panel_disclaimer` als Nicht-Ziel): kein solcher Bezeichner im Code.
- [ ] `.labs-disclaimer` in `PANEL_CSS` definiert (Panel-Rendering nutzt sie, Card unberührt).
- [ ] Hinweis erscheint auch bei aktivem `areas.labs` in einer frisch geöffneten
      Panel-Session ohne Settings-Load.

### REQ-HOM-126 — Beispiel-Dashboard
- [ ] `examples/dashboard-labs-card.yaml` existiert, parst, nutzt nur
      `custom:health-o-mat-labs-card`-Keys aus `LABS_CARD_KEYS`.
- [ ] `pytest tests/test_dashboards.py` grün ohne Ausnahme-Regel für die neue Datei.
- [ ] README listet das neue Beispiel.

---

## 12. Teststrategie

| Ebene | Datei | Inhalt |
|---|---|---|
| HA-freie Logik | `tests/test_logic.py` | `validate_lab_report_rows`: Leerzeilen (`{}`, `""`-Zeilen, gemischt mit echten Werten), alle **sieben** Codes der Funktion (`invalid_ts` liegt beim Aufrufer, §2.3), Reihenfolge (`invalid_value` vor `unsupported_unit`, z. B. `value: "abc"` + `unit: "mg/dL"` bei `alt` → `invalid_value`), `bool`-Wert, `NaN`/`inf`, 200/201-Zeilen-Grenze, Alias-Kollision, 1-basierte Zeilennummern, Erfolgspfad (kanonisch + `reported_*`), Rückgabe `(rows, None)` bzw. `([], "<code>…")`; `coerce_lab_number` separat |
| Store | `tests/test_store.py` | `add_lab_readings`: n Einträge, **ein** `_async_save` (Call-Count), **ein** Audit-Eintrag `lab_values_added`, `details` ohne `report_ref`, Listen ≤ 20, `count` voll; **Rollback-Test**: `_async_save` wirft → `lab_readings`/`audit_log` exakt wie vorher (inkl. eines zuvor gekappten Audit-Rings), Exception propagiert |
| Service | `tests/test_lab_services.py` | Erfolg (2 Marker, gemeinsames `ts`/`report_ref`), Alles-oder-nichts (Zeile 3 ungültig → Store/Audit unverändert), jeder Code mit Zeilenbezug, `invalid_ts: <Prosa>`-Präfix (Meldung aus `_service_entry_ts` gewrappt, `__init__.py:592-605`), Personenauflösung **vor** `invalid_ts` (unbekannte Person + kaputter `ts` → Entry-Fehler), `report_ref`-Cap 500, `add_lab_value`-Härtung (`NaN`/`inf`) |
| WS | `tests/test_ws_api.py` | Kommando registriert, `send_result {"written": n, "ts": …}`, `send_error` mit Code-Prefix (auch `invalid_ts: …` aus `parse_entry_ts`, `ws_api.py:1345-1349`), `entry_id`-Pflicht **vor** `invalid_ts`, `PREVENT_EXTRA` für unbekannte Zeilenfelder, `{}`-Zeile wird ignoriert statt abgewiesen |
| Panel-/Card-JS | `tests/test_panel_js.py`, `tests/test_card_js.py` | Dialog rendert Startzeile + Add/Remove; Client-Validierung (leerer Bericht, nicht-numerisch); **Prefix-Mapping** identisch in beiden Dateien; Draft bleibt bei Fehler; Erfolg leert Wert-Felder + Zeilen, **behält** `ts`/`report_ref`; Single-Flight (`_saving` blockt Doppel-Submit); Panel-Draft defensiv (`_labReportDraft` undefined ohne Crash); Admin: Umrechnungs-Spalte, `—`, Badge, `formatNumber`-Nutzung; Panel: Disclaimer immer gerendert |
| i18n (UI) | `tests/test_translations.py` | neue Keys in `_REQ_HOM_122_UI_KEYS` (506-541) → Master/de/en vorhanden und nicht leer (Test 544-551) |
| i18n (Service) | `tests/test_translations.py` | `services.add_lab_report` mit `name`, `description` und übersetzten Feldern in `strings.json`/`de`/`en`; `_LAB_SERVICE_FIELDS` (392-395) um `"add_lab_report": {"person", "values", "ts", "report_ref"}` und `_LAB_TRANSLATED_FIELDS` (400-403) um `{"values", "ts", "report_ref"}` erweitern → Paritätstest (406-425) prüft Feldsatz, `name`/`description` und je Feld `name`/`description` |
| Service-Schema-Mirror | `tests/test_lab_services.py` | Neuer Test: die `selector.select.options`-Werte von `add_lab_value` **und** `add_lab_report` in `services.yaml` entsprechen exakt `set(LAB_MARKERS)` (kein vergessener/erfundener Marker, keine Drift zwischen den beiden Blöcken) |
| Dashboards | `tests/test_dashboards.py` | §9.1: Labs-Card-Typ + Key-Set; neue Datei besteht die Sammelprüfung |
| Unverändert | `tests/test_import_backup.py`, `tests/test_restore.py` | Regressionslauf bestätigt: Batch berührt Backup/Restore/CSV nicht |
| E2E | `tests_e2e/test_lab_values_e2e.py` (Erweiterung) | Bericht mit 2 Zeilen über den Panel-Dialog → beide Werte im `panel_data`-Payload; Zeile mit unbekanntem Marker → Fehler mit Zeilenbezug, Eingaben bleiben, Server-Payload unverändert; Person ohne Admin sieht den Disclaimer |

---

## 13. Risiken

| Risiko | Wirkung | Gegenmaßnahme |
|---|---|---|
| **Teil-Write bei Save-Fehler** | `_async_save()` schlägt nach dem Append fehl → RAM und Disk divergieren | **Rollback** (§2.7): Listen-Snapshot (readings + audit) vor dem Append, bei Exception exakt zurücksetzen und re-raisen. Damit gilt „Alles-oder-nichts" auch für den Persistenzschritt — kein Teil-Batch bleibt im RAM, und der Aufrufer bekommt einen Fehler, obwohl nichts geschrieben wurde. Der Save ist der **einzige** Persistenzpunkt; ein Prozess-Absturz davor hinterlässt keinen Disk-Teilzustand (es gilt der letzte erfolgreiche Save). Kein zweiter Save-Punkt |
| **Unbegrenztes Wachstum** (keine Lab-Retention) | Batch macht es trivial, viele Werte anzulegen; `lab_readings` wächst unbegrenzt (`_apply_retention` umfasst nur `drinks`/`readings`, dokumentiert in `REQUIREMENTS.md:1225-1230`) | Bewusst akzeptiert (Laborwerte sind klein und sollen vollständig erhalten bleiben); Server-Limit 200 Zeilen pro Vorgang; Korrektur über `void_entry`; Retention für Labs ist ein separates Vorhaben |
| **Replay / Doppel-Submit** | doppelte Lesungen, verfälschte Verläufe | Keine Idempotenz (§2.11) — UI Single-Flight (`_saving`), Aufrufer-Verantwortung dokumentiert; Korrektur über bestehende Void/Restore-Wege |
| **Datenminimierung `report_ref`** | Freitext/Cloud-Link könnte in Audit, Diagnostics oder Export lecken | `report_ref` **nicht** in Audit-Details (§2.8); Diagnostics bleiben redigiert (Zahlen/Konfiguration); keine Änderung an Export (bestehende Spalte, unverändert) |
| **Nicht-atomar über zwei Systeme** (Service + WS) | zwei Prüfpfade könnten auseinanderlaufen | Beide rufen `logic.validate_lab_report_rows`; WS ruft **nicht** den Service (kein verschachtelter Service-Call) |
| **`duplicate_marker` blockiert legitime Fälle** | Bericht mit zwei Werten desselben Markers (z. B. vor/nach Belastung) nicht in einem Aufruf möglich | Zwei Aufrufe mit unterschiedlichem `ts`/`report_ref` — bewusster Trade-off, dokumentiert in §2.5 und in der Fehlermeldung („zweiten Wert separat erfassen") |
| **UI-Duplikation Card/Panel** | Regeln driften auseinander | Paritätstests über beide Dateien (§12); bewusst kein Shared-Modul (§6.3) |

---

## 14. Offene Punkte

1. **Editor-Darstellung des `object`-Selectors:** Die `fields`-Variante (§2.2) ist der
   vorgesehene Weg; wie komfortabel der HA-Service-Editor Listen von Objekten rendert,
   ist bei der Umsetzung zu prüfen. Das Schema bleibt in jedem Fall gültig — YAML-Aufruf
   (§2.10) und REST funktionieren unabhängig davon.
2. **Card-Disclaimer-Hartkodierung:** Der Card-Text ist ein deutscher Literal
   (`health-o-mat-labs-card.js:865`). Für §8 wird nur der Panel-Key eingeführt; die
   nachträgliche Angleichung der Card (gleicher Key, `de` wortgleich) ist optionaler
   Folgeschritt, nicht Teil dieses Konzepts.
3. **`formatLabValue` in der Card** nutzt hartkodiert `de-DE`
   (`health-o-mat-labs-card.js:131-135`) — vorbestehend, nicht in diesem Scope; der neue
   Admin-Formatter (§7) nutzt die locale-fähige Panel-Variante.
4. **Panel-Disclaimer-Abschaltbarkeit:** bewusst verworfen für v1 (§8). Falls später
   gewünscht: additiv über ein Feld im `panel_data`-Payload (nicht über das admin-only
   `get_settings`) und dann mit eigenem REQ; ein dann nötiger Options-Bool läuft über den
   strikten Validator `_strict_bool` (`ws_api.py:230-242`).

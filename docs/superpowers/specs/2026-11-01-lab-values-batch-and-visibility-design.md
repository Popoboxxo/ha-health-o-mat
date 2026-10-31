# Konzept: Laborwerte — Batch-Erfassung & Sichtbarkeit (Erweiterung zu REQ-HOM-122)

**Status:** Entwurf (2026-11-01) · **Basis:**
`docs/superpowers/specs/2026-10-30-lab-values-design.md` (REQ-HOM-122, umgesetzt in 0.16.x)
· **Verwandt:** `docs/REQUIREMENTS.md` REQ-HOM-122, `docs/CONCEPT-UI.md`,
`docs/IDEATION-VISION.md` §4.2

> Vier Lücken der bestehenden Domäne plus drei Härtungen: (1) ein Laborbericht ist nur als N
> Einzelaufrufe erfassbar (und nur einzeln verwerfbar), (2) die Umrechnungsfaktoren der 29
> Katalog-Marker sind im Admin unsichtbar, (3) der Laborwerte-Tab im Panel hat keinen
> kontextbezogenen Medizin-Hinweis, (4) es gibt kein Beispiel-Dashboard für die Labs-Card.
> Dazu: Batch-Fehlervertrag, `NaN`/`inf`-Härtung und eine eigene Labor-Retention.
>
> **Kein Schema-Wechsel:** `lab_readings[]` bleibt strukturell unverändert, Store-Schema
> bleibt **v5**, `unique_id`s unverändert. Retention **voidet** (kein Archiv, kein
> Listen-Umbau). `report_ref` bleibt ein freier Tag — kein `LabReport`-Aggregat, keine
> Report-Entität, kein `batch_id`.
>
> **Release:** 0.16.2 (**PATCH** — additive Services/UI, keine Breaking Entity-/Schema-
> Änderung). Der Release selbst ist **nicht** Teil der Umsetzungstasks.

---

## 1. Ziel & Nutzen

Ein Laborbefund kommt als **ein Dokument mit 10–30 Werten zu einem Zeitpunkt aus einer
Quelle**. Heute kostet das 10–30 Service-Aufrufe (`add_lab_value` nimmt genau einen Marker:
`__init__.py:1001-1011`, `services.yaml:329-429`), jeder mit eigenem Store-Write, eigenem
Coordinator-Refresh und eigenem Audit-Eintrag. Card und Panel haben nur ein Einzelwert-
Formular (`health-o-mat-labs-card.js:663-706`, `health-o-mat-panel-views.js:1093-1115`);
ein falsch erfasster Bericht lässt sich nur Wert für Wert zurücknehmen.

| Aspekt | n Einzel-Calls | ein `add_lab_report` |
|---|---|---|
| Tippfehler in Zeile 7 | 6 Werte geschrieben, 4 fehlen → manuelles Aufräumen | nichts geschrieben (Alles-oder-nichts) |
| `ts` / `report_ref` | n-mal wiederholen, Abweichungen möglich | einmal gesetzt, gilt für alle Zeilen |
| Store-Write / Refresh / Audit | n Writes, n Refreshes, n Audit-Einträge (Cap-Ring wird geflutet) | 1 Write, 1 Refresh, 1 Audit-Eintrag |
| Bericht verwerfen | n × `remove_last_lab_value`/`void_entry` | ein `remove_lab_report` |
| Externe Systeme | n HTTP-Calls mit Fehler-Matrix | 1 Call, 1 strukturierter Fehler |

**Zielgruppe:** derselbe Nutzer wie REQ-HOM-122 (eine Person pro Config-Entry) plus externe
Skripte/Systeme, die einen Befund in einem Rutsch pushen.

**Leitplanke (unverändert, Vision §4.2):** keine medizinische Klassifikation, keine
Diagnose. §8 schließt die Lücke, dass der Panel-Lab-Tab diesen Vorbehalt nur im globalen
Footer trägt (`health-o-mat-panel.js:1983-1987`, immer gerendert ab Zeile 1953).
Datenschutz unverändert: `diagnostics.py` bleibt redigiert, Export nie nach `/config/www`.

---

## 2. Datenmodell & Service-Vertrag

### 2.1 Kein Schema-Wechsel

`lab_readings[]` behält **exakt** das heutige Format (`store.py:641-680`): `{id, ts,
marker_key, value, unit, reported_value, reported_unit, report_ref, created_at, voided_at,
voided_by, void_reason}`. Batch-Schreiben, Batch-Verwerfen und Retention sind nur andere
Schreibweisen über derselben Liste — **kein neues Feld**, keine Migration,
`STORE_SCHEMA_VERSION` bleibt **5**, kein `batch_id`.

### 2.2 Service `health_o_mat.add_lab_report`

| Feld | voluptuous | services.yaml | Pflicht | Semantik |
|---|---|---|---|---|
| `person` | `vol.Optional("person"): str` | Textfeld | nein | leer = einzige konfigurierte Person (`get_runtime_data`) |
| `ts` | `vol.Optional("ts"): str` | **Textfeld mit `example`** (kein Selector — Angleich an `add_lab_value`, `services.yaml:418-423`) | nein | **ein** gemeinsames `ts` für den ganzen Bericht; Regeln unverändert (≤ 5 Min Zukunft, ≥ 1900). **Kein Per-Zeile-`ts`** (später additiv möglich, §14) |
| `report_ref` | `vol.Optional("report_ref"): str` | Textfeld | nein | freier Tag, `.strip()[:500] or None` — identisch zu `__init__.py:766` |
| `values` | `vol.Required("values"): vol.All(cv.ensure_list, [vol.Schema({...})])` | `object` **mit `fields`** + `multiple: true` (siehe unten) | **ja** | Liste aus `{marker, value, unit}` (max. **200** nicht-leere Zeilen, §2.5) |

Service-Name **`add_lab_report`** (ein Bericht = ein Vorgang). `add_lab_value` bleibt
unverändert der schnelle Tagespfad.

```yaml
# services.yaml — `fields` macht den Object-Selector im Editor überhaupt erst bedienbar
add_lab_report:
  name: Laborbericht erfassen
  description: >-
    Erfasst mehrere Laborwerte eines Berichts in einem Vorgang — gleicher Zeitpunkt,
    gleiche Berichts-Referenz, Alles-oder-nichts (eine ungültige Zeile lehnt den
    gesamten Bericht ab). Leere Zeilen werden ignoriert. Ein erneuter Aufruf schreibt
    erneut (nicht idempotent).
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
                    - {label: "LDL", value: "ldl"}
                    - {label: "HDL", value: "hdl"}
                    - {label: "Triglyceride", value: "triglycerides"}
                    - {label: "TSH", value: "tsh"}
                    - {label: "fT4", value: "ft4"}
                    - {label: "fT3", value: "ft3"}
                    - {label: "Hämoglobin", value: "hemoglobin"}
                    - {label: "Leukozyten", value: "leukocytes"}
                    - {label: "Thrombozyten", value: "platelets"}
                    - {label: "CRP", value: "crp"}
                    - {label: "BSG", value: "esr"}
                    - {label: "Lipase", value: "lipase"}
                    - {label: "Amylase", value: "amylase"}
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
Aliase (`gpt`/`got`/`gamma_gt`) als Freitext gültig (Auflösung wie dort, §2.5).

Voluptuous (Handler prüft fein):

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

`marker: str` (kein Coerce), `value` wird **im Handler** zu Zahl geprüft (inkl.
`bool`-Ablehnung: `True`/`False` sind in Python `int`, aber kein Messwert), `unit: str|None`.
Grund: Schema-Fehler liefern generische HA-Meldungen ohne Zeilenbezug; gefordert sind
präzise Codes pro Zeile (§2.4/§2.5). Dasselbe Muster nutzt der WS-Pfad bereits
(`ws_api.py:1336-1342`).

**Warum `Optional` und nicht `Required`:** Mit `vol.Required` würde ein `{}`-Eintrag (oder
eine Zeile mit ausschließlich leeren Strings) schon vom Schema abgewiesen — das widerspricht
dem Versprechen „leere Zeilen werden ignoriert". Der `required: true`-Marker in den
services.yaml-`fields` ist reiner **Editor-Komfort** für manuelle Formularnutzung und hat
auf den Service-Aufruf keine Wirkung.

### 2.3 Zeilen-Form

```yaml
values:
  - marker: alt          # Pflicht für nicht-leere Zeilen; Alias/Katalog/Custom
    value: 32            # Pflicht für nicht-leere Zeilen; Zahl oder numerischer String, kein bool
    unit: U/L            # optional; kanonische ODER Alt-Einheit
  - {}                   # Leerzeile = wird ignoriert
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
) -> tuple[list[dict], dict | None]:
    """Leerzeilen filtern, Zeilen validieren, in kanonische Einheiten konvertieren.

    Rückgabe: (konvertierte Zeilen, Fehlerobjekt oder None). Das Fehlerobjekt ist
    {"code": str, "params": {...}, "message": str} — params/message bereits im
    Vertragsformat (§2.4), der Aufrufer reicht sie nur noch weiter.
    """
```

- **In der Funktion:** `empty_report`, `too_many_rows`, `unknown_marker`, `unit_required`,
  `invalid_value`, `unsupported_unit`, `duplicate_marker`.
- **Nicht in der Funktion:** `invalid_ts` (Batch-weites Feld außerhalb der Zeilenliste;
  Aufrufer prüft) und die Personenauflösung (`get_runtime_data` bzw. `_runtime_entry` —
  HA-gebunden, nicht HA-frei).
- **Rückgabe statt Exception:** `tuple[..., dict | None]` folgt dem Haus-Muster
  `resolve_lab_marker → None bei kein Treffer`; der Aufrufer entscheidet, ob daraus ein
  `ServiceValidationError` oder die WS-Fehler-Envelope wird. Erster Fehler gewinnt, keine
  Fehlerliste (ein Bericht wird als Ganzes korrigiert).

### 2.4 Fehlervertrag (strukturiert)

Der Batch liefert Fehler **strukturiert** — zukunftssicher für UI/API-Konsumenten:

```python
{"code": "unknown_marker",
 "params": {"row": 3, "marker": "kreatinin"},
 "message": "Zeile 3 (kreatinin): unknown_marker"}
```

| Code | `params` | `message` (Service + UI) |
|---|---|---|
| `invalid_ts` | `{"value": <roh>}` | `invalid_ts: <Prosa aus ENTRY_TS_INVALID_MESSAGE>` |
| `empty_report` | `{}` | `empty_report` |
| `too_many_rows` | `{"count": n, "limit": 200}` | `too_many_rows (201 > 200)` |
| `unknown_marker` | `{"row": n, "marker": <roh>}` | `Zeile n (<roh>): unknown_marker` |
| `unit_required` | `{"row": n, "marker": <roh>}` | `Zeile n (<roh>): unit_required` |
| `invalid_value` | `{"row": n, "marker": <roh>, "value": <roh>}` | `Zeile n (<roh>): invalid_value` |
| `unsupported_unit` | `{"row": n, "marker": <roh>, "unit": <roh>}` | `Zeile n (<roh>): unsupported_unit` |
| `duplicate_marker` | `{"row": n, "marker": <roh>, "first_row": m}` | `Zeile n (<roh>): duplicate_marker (schon in Zeile m)` |
| `no_active_report` | `{"ts": <iso>}` | `no_active_report` (nur `remove_lab_report`) |

- **`row` = Originalzeile der eingegebenen Liste, 1-basiert, inklusive leerer Zeilen**
  (eine Leerzeile in Position 2 verschiebt die Zählung der dritten Zeile auf 3). So findet
  der Nutzer die Zeile in seinem Eingabefeld wieder, auch wenn Leerzeilen dazwischen stehen.
- **`marker` ist immer der eingegebene Rohwert** (nicht der aufgelöste Key); bei leerem
  Marker im Feld `message` als `-` gerendert: `Zeile 3 (-): invalid_value`.
- **Zwei Transportwege, ein Objekt:** Der Service kann nur Text transportieren → er wirft
  `ServiceValidationError(error["message"])`. Die WS-Batch-Kommandos liefern das volle
  Objekt (§3). Die **Migration der bestehenden** Services/WS-Fehler auf code-only ist
  ausdrücklich **nicht** Teil dieses Konzepts → REQ-HOM-127 (§11).

### 2.5 Validierungsreihenfolge & Fehlercodes

Alle Prüfungen laufen **vor** jedem Schreibzugriff; die Reihenfolge ist deterministisch:

0. **Person-Auflösung (zuerst, kein neuer Code):** Service `get_runtime_data(hass, call)`,
   WS `_runtime_entry` + `_entry_ready` (`ws_api.py:1320-1325`, Fehler via
   `_send_entry_error`). Das läuft zwangsläufig vor allem anderen — ohne `entry_id` gibt es
   weder `entry.options` (Custom-Marker) noch eine Person. Ein unbekannter/nicht geladener
   Entry meldet also den bestehenden Entry-Fehler, **nicht** `invalid_ts`.
1. **`invalid_ts`** — `ts` nicht ISO-8601 / > 5 Min Zukunft / < 1900.
   - **Herkunft der Meldung:** `ws_api.parse_entry_ts` (`ws_api.py:806-817`) und
     `_service_entry_ts` (`__init__.py:592-605`) liefern heute **Prosa ohne Code**
     (`logic.ENTRY_TS_INVALID_MESSAGE`, `logic.py:158-161`; Grenze `logic.ENTRY_TS_MIN`,
     `logic.py:155`) — der Service wrappt sie als `ServiceValidationError`, der WS-Pfad als
     `send_error` (`ws_api.py:1345-1349`).
   - **Batch-Regel:** Beide Aufrufer erzeugen daraus das Fehlerobjekt
     `{"code": "invalid_ts", "params": {"value": <roh>}, "message": "invalid_ts: <Prosa>"}`.
     Kein Umbau von `parse_entry_ts`/`ENTRY_TS_INVALID_MESSAGE` (deren Vertrag gilt für alle
     Services) — die Code-Verpackung ist Batch-Aufrufer-Sache.
2. **`empty_report`** — `values` leer **oder** alle Zeilen leer.
3. **`too_many_rows`** — mehr als **200** nicht-leere Zeilen (Server-Limit, unabhängig von
   der UI-Grenze von **60**, §6.1). Zählt nur befüllte Zeilen.
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
   Vorkommnis-Zeile mit `first_row` der ersten.
6. **Schreiben** — alle Zeilen konvertiert (kanonischer Wert + `reported_*`), dann **ein**
   Store-Write, **ein** Audit-Eintrag, **ein** `signal_refresh`.

> **Numerische Prüfung ist Vorbedingung der Einheitenprüfung:** `convert_lab_value` beginnt
> mit `float(value)` und würde bei `"abc"` einen `ValueError` werfen, der sonst fälschlich
> als `unsupported_unit` klassifiziert würde. Deshalb steht `invalid_value` **vor**
> `unsupported_unit`.
>
> **Fixed in dieser Erweiterung — `NaN`/`inf`:** `logic.coerce_lab_number(value)` (HA-frei)
> prüft „Zahl, kein `bool`, endlich" und liefert `float` oder `None`. Batch **und** der
> bestehende Einzelpfad (`add_lab_value` Service + WS) nutzen ihn; damit meldet auch
> `add_lab_value` `invalid_value` statt `NaN`/`inf` stillschweigend zu speichern
> (`__init__.py:761-765`, `ws_api.py:1336-1342`). **Status: behoben (nicht „offen").**

**Kein Teilzustand:** Ein Fehler hinterlässt weder Lesungen noch Audit-Einträge.

### 2.6 Duplikate im Batch

**Ganzer Batch abgelehnt (`duplicate_marker`), kein „last wins".** Alle Zeilen teilen `ts`
und `report_ref`; zwei Werte desselben Markers zum selben Zeitpunkt aus demselben Bericht
sind ein Eingabefehler (doppelt eingefügt), kein Datenzustand. „Last wins" würde
stillschweigend Daten verschlucken — gegen die Grundhaltung von REQ-HOM-122. Ein echter
Zweitwert (vor/nach Belastung) ist ein separater Aufruf mit eigenem `ts`/`report_ref`.

### 2.7 Antwort / Ergebnis

| Aufrufer | Erfolg | Fachfehler |
|---|---|---|
| Service | **kein** Rückgabewert (konsistent zu allen bestehenden Services; kein `SupportsResponse` im Repo) | `ServiceValidationError(error["message"])` |
| WS `add_lab_report` | `send_result(id, {"ok": true, "written": n, "ts": ts_iso})` | `send_result(id, {"ok": false, "error": {...}})` (§3) |
| WS `remove_lab_report` | `send_result(id, {"ok": true, "voided": n})` | `send_result(id, {"ok": false, "error": {...}})` (§3) |

`n` = Anzahl tatsächlich geschriebener Werte (ohne ignorierte Leerzeilen). Ein
Service-Response (`SupportsResponse`) wird **nicht** eingeführt — neues Muster, kein Bedarf.

### 2.8 Store-API

```python
async def add_lab_readings(
    self, entry_id: str, ts_iso: str, rows: list[dict], report_ref: str | None = None,
    created_ts_iso: str | None = None, actor: str | None = None,
    audit_limit: int = DEFAULT_AUDIT_LIMIT,
) -> list[str]:  # -> geschriebene Reading-IDs (für den Audit-Eintrag)

async def void_lab_report(
    self, entry_id: str, ts_iso: str, report_ref: str | None = None,
    actor: str | None = None, reason: str = "report_discarded",
    audit_limit: int = DEFAULT_AUDIT_LIMIT,
) -> list[str]:  # -> voidete Reading-IDs (leer = kein Treffer)

async def void_lab_readings_before(
    self, entry_id: str, cutoff_iso: str, actor: str | None = None,
    audit_limit: int = DEFAULT_AUDIT_LIMIT,
) -> list[str]:  # -> voidete Reading-IDs (Retention)
```

`rows` = bereits konvertierte, validierte Zeilen (`{marker_key, value, unit, reported_value,
reported_unit}`). Alle drei Methoden: **ein** `_append_audit`, **ein** `_async_save()`, mit
**Rollback**. `add_lab_reading` (Singular, `store.py:641-680`) bleibt für den Einzelpfad.

**Rollback bei Save-Fehler (damit „Alles-oder-nichts" auch für den Persistenzschritt gilt):**

```python
entry = self.entry(entry_id)
readings_before = list(entry.get("lab_readings") or [])   # flache Kopie reicht
audit_before = list(entry.get("audit_log") or [])
try:
    mutiere(entry)                    # append / voiden
    self._append_audit(...)           # ein Eintrag (kann den Cap anwenden!)
    await self._async_save()
except Exception:
    entry["lab_readings"] = readings_before   # exakt der Vorzustand
    entry["audit_log"] = audit_before         # auch gekappte Alt-Einträge zurück
    raise
```

- Vorbild ist `apply_retention` (`store.py:956-969`, S-5): Snapshot vor der Mutation,
  Restore im `except`, dann `raise`.
- Vollständige **Listenkopien** statt Längen-Slices: `_append_audit` kann den Audit-Ring
  kappen (`_prune_audit`, `store.py:385-394`) — ein Slice-Rollback würde gekappte
  Alt-Einträge nicht wiederherstellen.
- Flache Kopie genügt: die Operationen fügen Dict-Referenzen hinzu/ändern nur
  `voided_*`-Felder der betroffenen Einträge — dafür ist eine tiefe Kopie der **betroffenen**
  Einträge nötig. Umsetzung: Snapshot als `copy.deepcopy` der beiden Listen (gleiches Muster
  wie `apply_retention`), damit ein Rollback auch `voided_at` zurücksetzt.
- Nach dem Rollback ist der In-Memory-Zustand identisch zum Zustand vor dem Aufruf; der
  Fehler wird weitergereicht (Service: `ServiceValidationError`, WS: Fehler-Envelope).

### 2.9 Audit-Log

| Aktion | Auslöser | `target_id` | `details` |
|---|---|---|---|
| `lab_values_added` | `add_lab_report` | `None` | `{"count": n, "marker_keys": [...], "reading_ids": [...], "created_at": <iso>}` |
| `lab_report_voided` | `remove_lab_report` | `None` | `{"count": n, "reading_ids": [...], "created_at": <iso>}` |
| `lab_values_retention` | Retention beim Setup | `None` | `{"count": n, "months": N, "cutoff": <iso>, "reading_ids": [...], "created_at": <iso>}` |
| `entry_voided` | `void_entry`/`restore_entry` | Reading-ID | `{"reason": ...}` (bestehend) |

- **Ein** Eintrag pro Vorgang/Lauf: `audit_log` ist ein gekappter Ring (`_prune_audit`,
  `store.py:385-394`) — 29 Zeilen-Einträge würden unbeteiligte Historie verdrängen; fachlich
  ist „Bericht erfasst/verworfen/retained" je ein Ereignis.
- **`reading_ids` auf 20 gekappt**; `count` trägt die volle Zahl, `created_at` ist der
  Anker (die Reading-Einträge selbst tragen ihr eigenes `created_at`). **Kein `batch_id`**,
  kein Schema-Umbau.
- **Datenminimierung:** `report_ref` steht **nicht** in den Details (Freitext, potenziell ein
  Cloud-Link); keine Messwerte (bestehende Regel, `_append_audit`-Docstring
  `store.py:344-348`). `marker_keys` ebenfalls auf 20 gekappt.
- Einzel-Löschungen bleiben granular: `void_lab_reading` schreibt `entry_voided` mit der
  jeweiligen Reading-ID (`store.py:727-754`).

### 2.10 `report_ref` / `ts`

Identisch zu `add_lab_value`: `report_ref` getrimmt auf `LAB_REPORT_REF_MAX_LEN = 500`
(`const.py:501`), rein referenzierend, wird nie abgerufen; **ein** `ts` für den ganzen
Bericht mit denselben Grenzen (`≤ 5 Min Zukunft`, `≥ 1900`). Kein Per-Zeile-Zeitpunkt in v1.

### 2.11 YAML-Aufrufbeispiel (Hauptnutzen für externe Systeme)

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

Ein Aufruf = ein Bericht, über die bestehende REST-API
(`POST /api/services/health_o_mat/add_lab_report`) genauso nutzbar — kein neuer
Webhook/Endpunkt. Zwei Werte desselben Markers im selben Aufruf → `duplicate_marker`.
Fehlerbeispiel: `ServiceValidationError("Zeile 3 (kreatinin): unknown_marker")`.

### 2.12 Idempotenz / Replay — dokumentierte Grenze

Der Service ist **nicht** idempotent: derselbe Aufruf zweimal erzeugt zweimal dieselben
Lesungen (kein Dedupe über `ts`+`marker`+`value`, konsistent zu `add_lab_value`). Begründung:
ein impliziter Dedupe-Schlüssel würde echte Wiederholungsmessungen verschlucken.

- **Retry-Hinweis für externe Systeme:** Vor einem Retry nach Timeout zuerst
  `panel_data.labs.last_report` prüfen (oder `get_settings`/Export) — ist der Bericht schon
  da, **nicht** erneut senden. Einen versehentlich doppelten Bericht entfernt
  `remove_lab_report` (§2.13) in einem Schritt.
- **UI:** Single-Flight (`_saving`-Muster), Button während des Sendens disabled
  (`health-o-mat-labs-card.js:746-748, 786-789`).
- Die Grenze steht in der Service-`description` („Ein erneuter Aufruf schreibt erneut").

### 2.13 Service `health_o_mat.remove_lab_report` (Batch-Undo)

| Feld | voluptuous | services.yaml | Pflicht | Semantik |
|---|---|---|---|---|
| `person` | `vol.Optional("person"): str` | Textfeld | nein | wie überall |
| `ts` | `vol.Required("ts"): str` | Textfeld mit `example` | **ja** | Zeitpunkt des Berichts (aus `panel_data.labs.last_report.ts` oder eigener Aufzeichnung) |
| `report_ref` | `vol.Optional("report_ref"): str` | Textfeld | nein | wenn gesetzt, müssen `ts` **und** `report_ref` übereinstimmen |

- **Semantik:** voidet **alle aktiven** Laborwerte mit demselben Zeitpunkt — und, falls
  `report_ref` gesetzt ist, zusätzlich demselben `report_ref`. Voiden = `voided_at`/
  `voided_by`/`void_reason="report_discarded"` setzen (kein Hard-Delete, `store.py:727-754`).
  `report_ref` wird wie beim Erfassen behandelt (trimmen, `[:500]`, leer → `None`).

```python
vol.Schema({
    vol.Optional("person"): str,
    vol.Required("ts"): str,
    vol.Optional("report_ref"): str,
})
```

- **Grenzfall „mehrere Berichte mit identischem `ts`":** **ohne** `report_ref` werden **alle**
  aktiven Werte dieses Zeitpunkts verworfen (bewusste, dokumentierte Regel — der Aufrufer
  grenzt mit `report_ref` ein, wenn er nur einen Bericht treffen will). Mit `report_ref`
  werden nur Einträge mit exakt diesem Tag getroffen (`report_ref IS NULL` zählt nicht als
  Treffer für einen gesetzten Filter).
- **Zeitvergleich:** `ts` wird geparst (`logic.parse_entry_timestamp`) und **als Instant**
  gegen die geparsten `ts` der Einträge verglichen — Offset-Schreibweisen derselben Zeit
  treffen sich, kein String-Vergleich. Ungültig → `invalid_ts`.
- **Fehlercodes:** `invalid_ts`, `no_active_report` (kein aktiver Treffer).
- **Ergebnis:** Service ohne Rückgabe (bei `no_active_report` → `ServiceValidationError`);
  WS `{"ok": true, "voided": n}`.
- **Audit:** **ein** Eintrag `lab_report_voided` (§2.9).
- **Restore:** einzeln über den bestehenden `restore_entry` (`kind: lab_values`, `id`);
  es gibt bewusst **kein** Gruppen-Restore (kein `batch_id`).
- **UI:** Aktion „Diesen Bericht verwerfen" im Labs-Tab/Card mit **Sicherheitsabfrage**
  (`confirm()`-Muster wie bestehende destruktive UI-Aktionen), sichtbar nur wenn
  `labs.last_report` aktiv ist; sendet `ts` (+ `report_ref` des letzten Berichts, falls
  gesetzt). §6.5.

### 2.14 Retention: `lab_retention_months`

**Eigene Option, unabhängig von `retention_months` (Getränke/BD).**

| Aspekt | Festlegung |
|---|---|
| Optionsschlüssel | `lab_retention_months` (`const.py`, bei den `OPTION_LAB_*`) |
| Typ / Default | `int`, **`0` = aus** (Default; exakt bisheriges Verhalten) |
| Bereich | `0 … MAX_RETENTION_MONTHS` (`const.py:34`, = 120) |
| Ort der Eingabe | Options-Wizard Schritt **„Grundlagen"** (`async_step_basics`, `config_flow.py:411-433`) — direkt neben `retention_months`, gleiche `vol.All(vol.Coerce(int), vol.Range(...))`-Form |
| Laufzeitpunkt | (a) beim **Setup** des Entries (`__init__.py:227`) und (b) nach einer **Options-Änderung** (`__init__.py:444`) — jeweils als eigener Schritt `_apply_lab_retention` neben dem bestehenden `_apply_retention` (Getränke/BD), nie darin. Beide Läufe sind idempotent |
| Wirkung | **voidet** aktive Laborwerte mit `ts < cutoff` (`cutoff = logic.months_ago(now, N)`, bestehender Helfer `__init__.py:298`); `void_reason = "retention"`. **Kein Archiv, kein Verschieben, keine Listenkürzung** |
| Audit | genau **ein** Eintrag `lab_values_retention` pro Lauf — nur wenn `count > 0` |
| Wiederherstellbar | ja, einzeln über `restore_entry` (`kind: lab_values`) — wie jeder voidete Eintrag |
| Idempotenz | ja, voidete Einträge werden bei Folgeläufen ignoriert (nicht erneut gezählt/geauditet) |
| Export | `lab_values.csv` enthält **auch voidete** Zeilen inkl. `voided_at`/`void_reason` (§2.15) — Retention ist damit im Export nachvollziehbar |
| Backup/Restore | Option landet in `backup.lab_options`; `restore.py` merged — wie die anderen Lab-Options — nur `lab_custom_markers` (nicht restauriert, §2.16) |
| Diagnostics | Optionsschlüssel wird redigiert wie die übrigen Lab-Options (`diagnostics.py:57-63`) |

**Beide Options-Schreibpfade mergen** (`websocket_set_settings`: `{**current_options,
**updates}`, `ws_api.py:1774`; Options-Flow: `config_flow.py:548-550`) — `lab_retention_months`
überlebt also Admin-Saves und der Disclaimer-Schalter überlebt Options-Flow-Saves.

**Neue Store-Methode:** `void_lab_readings_before(entry_id, cutoff_iso, …)` → ein
Snapshot-Rollback, ein Save, ein Audit (Signatur §2.8). `apply_retention` (Getränke/BD,
Archiv) bleibt unberührt.

### 2.15 Export / Import-Folgen (nur `lab_values`)

- **Export:** `lab_values.csv` enthält **aktive und voidete** Zeilen; Header erweitert um
  `voided_at`, `void_reason` (bisher nur aktive Zeilen: `exporter.py:75, 141-156`,
  Header `exporter.py:15-25`). Sortierung bleibt nach `ts`. **Nur** das Lab-CSV ändert sich —
  `drinks.csv`/`readings.csv` bleiben „nur aktive" (`exporter.py:60-61`, M2a).
- **Import:** voidete Zeilen werden **übersprungen** und als `skipped` gezählt (keine
  Wiederbelebung). Das ist heute schon so, weil die Dedupe-Schlüssel gegen die **rohen**
  Listen inkl. voided laufen (`importer.py:443, 478-482, 545-548`) — die neuen Spalten
  werden vom toleranten Parser ignoriert. Kein Verhaltenswechsel nötig, nur Doku + Test.

### 2.16 Backup / Restore

- `backup.lab_options` (`backup.py:167-171`) bekommt zwei Schlüssel:
  `lab_hide_panel_disclaimer`, `lab_retention_months`. **Kein** Format-Bump (additiv).
- `lab_readings[]` bleibt unverändert im Backup (Format-Version unberührt).
- `restore.py` bleibt beim bisherigen Lab-Verhalten: nur `lab_custom_markers` wird gemerged
  (`restore.py:1010-1028`); Lesungen einzeln/Datensatz-weit wie heute.

---

## 3. WS-Request-Vertrag

Zwei neue Kommandos, registriert neben `COMMAND_ADD_LAB_VALUE` (`ws_api.py:107, 978`),
damit die UI Karten-Fehlermeldungen statt Service-Toasts bekommt — gleiche Begründung wie
`add_lab_value` (`ws_api.py:1313-1318`).

### 3.1 `health_o_mat/add_lab_report`

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

### 3.2 `health_o_mat/remove_lab_report`

```jsonc
{"id": 13, "type": "health_o_mat/remove_lab_report",
 "entry_id": "<id>", "ts": "2026-11-01T09:15:00+01:00", "report_ref": "https://…"}
```

### 3.3 Gemeinsame Regeln

- Schema `PREVENT_EXTRA`: innere Zeilen listen **nur** `marker`/`value`/`unit`; unbekannte
  Felder werden am Transportrand abgewiesen (wie `health_o_mat/add_lab_value`).
- `entry_id` ist **Pflicht** und muss eine geladene Person sein; sonst `_send_entry_error`
  (bestehender Pfad, `ws_api.py:1320-1325`) — **vor** jeder Fachprüfung.
- **Fachfehler als Ergebnis-Envelope** (nicht `send_error`):
  `send_result(msg["id"], {"ok": false, "error": {"code": …, "params": …, "message": …}})`
  — strukturiert, zukunftssicher (REQ-HOM-127 vereinheitlicht später die Alt-Pfade).
  `send_error` bleibt ausschließlich für Entry-/Transportfehler.
- Erfolg: `{"ok": true, "written": n, "ts": ts_iso}` bzw. `{"ok": true, "voided": n}`.
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
        ├── Leerzeilen filtern, empty_report / too_many_rows (200)
        ├── resolve_lab_marker(alias → Katalog → Custom)               # logic.py:1076
        ├── unit_required / invalid_value / unsupported_unit
        ├── convert_lab_value → (canonical value, canonical unit)      # logic.py:1091
        └── duplicate_marker                                            # aufgelöste Keys
                            │  error != None → Fehlerobjekt, KEIN Write
                            ▼
        store.add_lab_readings(entry_id, ts_iso, rows, report_ref=…)
        ├── Snapshot (readings/audit, deepcopy)
        ├── append aller Lesungen + _append_audit("lab_values_added", …)
        ├── genau ein _async_save()
        └── Exception → Snapshot zurückrollen, re-raise                  # §2.8
                            │
                            ▼
                 signal_refresh(hass, entry_id)                        # 1 Coordinator-Refresh
```

**Batch-Undo (`remove_lab_report`):** `entry_id` → `ts` parsen (`invalid_ts`) →
`store.void_lab_report(ts, report_ref?)` (Snapshot, voiden, ein Audit
`lab_report_voided`, ein Save, Rollback) → `[]` = `no_active_report` →
`signal_refresh`.

**Retention (Setup und Options-Änderung):** `lab_retention_months > 0` →
`cutoff = logic.months_ago(now, N)` → `store.void_lab_readings_before(entry_id, cutoff)`
(Snapshot, voiden mit `void_reason="retention"`, ein Audit `lab_values_retention`, ein Save,
Rollback) → `signal_refresh`. Reihenfolge: nach dem Store-Load, **neben** dem bestehenden
`_apply_retention` (Getränke/BD), unabhängig von dessen Ergebnis.

- **Ein** Prüfpfad für beide Aufrufer (`logic.validate_lab_report_rows`) — Service und WS
  können nicht auseinanderlaufen. Signatur: §2.3, Codes: §2.4/§2.5.
- Der Helper prüft **nicht** `ts` und löst **keine** Person auf — beides macht der Aufrufer
  davor.
- Custom-Marker kommen aus `entry.options[OPTION_LAB_CUSTOM_MARKERS]`
  (`logic.effective_lab_markers` → `normalize_lab_custom_markers`).
- Keine Store-Änderung ohne vollständig validierten Batch; `_async_save()` genau einmal
  (Test: Call-Count 1), bei Fehler greift der Rollback (§2.8).

---

## 5. Alternativen & Trade-off

| Ansatz | Vorteil | Nachteil / Grund der Ablehnung |
|---|---|---|
| **Neu: `add_lab_report` + `remove_lab_report`** (gewählt) | atomar, ein `ts`/`report_ref`, ein Write/Refresh/Audit; symmetrisches Undo | zwei weitere Schreibpfade (gemeinsame HA-freie Validierung begrenzt Duplikation) |
| `add_lab_value` um eine Liste erweitern | nur ein Service | bricht den Einwert-Vertrag; Pflicht-Semantik müsste je Variante differieren (Einwert `Required`, Batch `Optional` + Leerzeilen); Editor zeigt Mischformulare |
| Nur CSV-Import | kein neuer Service | Datei-Handling, kein Live-Push, Import ist bewusst tolerant (`rejected`) — Batch muss streng sein |
| Automation-Loop über `add_lab_value` | kein Code | Teilzustand, n Writes/Refreshes/Audits, `ts`/`report_ref` je Zeile |
| Batch-Undo als Schleife über `void_entry` | kein neuer Service | UI müsste erst alle IDs laden; Retry/Teilfehler; unklarer Zeitstempel-Bezug |
| Retention wie Getränke/BD (**Archiv**) | Historie bleibt vollständig | Laborwerte sind klein und sollen im Haupt-Store bleiben; das Archiv kennt keine Labs (`exporter.py:79`); **Voiden** ist einfacher, exportierbar und über `restore_entry` rückholbar |
| Retention gar nicht | kein Code | unbegrenztes Wachstum (bisher dokumentierte Grenze, `REQUIREMENTS.md:1225-1230`) |

---

## 6. UI: Mehrzeilen-Dialog

### 6.1 Aufbau

**Karte: inline aufklappbarer Bereich** (kein Overlay/Modal) — `<details>` „Laborbericht
erfassen" unterhalb des Einzelformulars. **Panel: eigener Abschnitt** im Lab-Tab (wie das
bestehende `<details class="lab-entry-form">`, `health-o-mat-panel-views.js:1093`).

```
▸ Laborbericht erfassen
  [ Alle sichtbaren Marker anlegen ] [ Zuletzt verwendete Marker anlegen ]
  Zeitpunkt: [ 2026-11-01 09:15 ]   Bericht-Link/ID: [ https://…        ]
  ┌──────────────────────────────────────────────────────────────────────┐
  │ Marker [ ALT (GPT)       ▾ ] Wert [ 32  ] Einheit [ U/L      ▾ ] ✕  │
  │ Marker [ Kreatinin       ▾ ] Wert [ 1.1 ] Einheit [ mg/dL    ▾ ] ✕  │
  │ Marker [ — bitte wählen  ▾ ] Wert [     ] Einheit [ U/L      ▾ ] ✕  │
  └──────────────────────────────────────────────────────────────────────┘
  [ ＋ Zeile ]                                     [ Bericht speichern ]
```

- Gemeinsame Felder: `ts` (`datetime-local`, leer = jetzt), `report_ref` (Text).
- **Zeilenlimit im Dialog: 60** (Soft-Cap, Button ausgrauen + Hinweis); **Server-Limit: 200**
  (§2.5).
- `＋ Zeile` fügt eine leere Zeile hinzu, Start = **1 leere Zeile**.
- **Hybrid-Füllung:**
  - **„Alle sichtbaren Marker anlegen"** — eine Zeile je Marker der sichtbaren Kategorien
    (`labs.categories[*].hidden == false`, §6.2), leere Werte; bestehende Zeilen bleiben.
  - **„Zuletzt verwendete Marker anlegen"** — die Marker des Berichts mit dem **neuesten
    gemeinsamen `ts`** aus `panel_data.labs.last_report` (§6.2); leer, wenn kein Bericht da.
  - Beide Aktionen deduplizieren gegen bereits vorhandene Zeilen und respektieren das
    60er-Limit (Rest-Zeilen werden nicht angelegt, kurzer Hinweis).
- **Einheiten-Eingabe je Zeile: Dropdown** mit
  `[kanonische Einheit, …alt_units des Markers]` + Freitext-Option („Andere …");
  Vorbelegung kanonisch. Die Alt-Einheiten kommen aus `panel_data`
  (`labs.markers[key].alt_units`, §6.2) — kein zusätzlicher Request.

### 6.2 Client- vs. Server-Validierung

| Prüfung | Client | Server | Begründung |
|---|---|---|---|
| mind. eine befüllte Zeile | ✅ | ✅ | sofortiges Feedback (`empty_report`) |
| Wert numerisch & endlich | ✅ | ✅ | `invalid_value` |
| Zeitpunkt plausibel | ✅ | ✅ | bestehende `_readEntryTs`-Logik (`…labs-card.js:730-744`) |
| Zeilenlimit | ✅ 60 | ✅ 200 | UI-Soft-Cap vs. Server-Hartgrenze |
| Marker auflösbar | ❌ | ✅ | Client kennt die Alias-Tabelle nicht (`LAB_MARKER_ALIASES` ist nicht im `panel_data`-Payload) |
| Einheit unterstützt | teilweise | ✅ | Dropdown bietet nur kanonisch + `alt_units`; Freitext bleibt möglich → Server entscheidet (`unsupported_unit`) |
| `require_explicit_unit` beachtet | ❌ | ✅ | Flag wird **nicht** ausgeliefert (bewusst: nur `alt_units` neu im Payload); Server entscheidet |
| Duplikat im Batch | ⚠️ exakte Select-Werte | ✅ | Client kennt keine aufgelösten Keys (Alias/Custom) |

**`panel_data` wird additiv erweitert** — drei Felder, kein
Zweit-Datenmodell:

| Feld | Inhalt | Warum |
|---|---|---|
| `labs.markers[key].alt_units` | `{unit: factor}` des Markers (Custom: das eine Alt-Paar; Katalog: `alt_units`) | Einheiten-Dropdown je Zeile (§6.1) |
| `labs.last_report` | `{"ts": <iso>\|null, "marker_keys": [...]}` — Bericht mit dem **neuesten gemeinsamen `ts`**: alle aktiven Marker, deren neuester aktiver Wert genau diesen `ts` trägt | „Zuletzt verwendete Marker anlegen" + „Diesen Bericht verwerfen" |
| `lab_hide_panel_disclaimer` | `bool` (Default `false`) | Disclaimer-Zustand im Lab-Tab **ohne** admin-only `get_settings` (§8) |

Präzedenz: `quick_drinks` und `wellbeing_confirm` werden genau deshalb über `panel_data`
transportiert (`ws_api.py:504-513`).

### 6.3 Card vs. Panel — Duplikations-Entscheidung

Die Labs-Card ist **standalone** (eigene `escapeHtml`/`t`/`labDisplayName`-Kopien, keine
Imports aus `health-o-mat-panel-*.js`), das Panel nutzt `health-o-mat-panel-base.js`.
Wie bei den bestehenden Rendering-Helfern wird der Dialog **je Datei einmal** implementiert:

- Card: `_reportForm()` + `_reportDraft` + `_saveReport()` + `_discardReport()`.
- Panel: `labsReportForm(panel, …)`; Draft **defensiv** lesen —
  `panel._labReportDraft && panel._labReportDraft[entryId]` (Muster wie
  `panel._labCustomDraft`, `health-o-mat-panel.js:1155-1159`).
- Parität sichern **Tests** über beide Dateien (§12), nicht ein Shared-Modul. Ein Extrakt
  lohnt erst beim dritten Konsumenten.

### 6.4 Absende-Pfad, Reset-Semantik, Single-Flight

- Card und Panel senden über WS `health_o_mat/add_lab_report` (§3), **nicht** über den
  Service.
- **Single-Flight:** `_saving`-Flag blockiert Doppel-Submit (Muster
  `…labs-card.js:746-748, 786-789`); Button disabled während des Sendens. Das ist die
  UI-Mitigation gegen Replay (§2.12) — keine Idempotenz im Server.
- **Reset bei Erfolg (bewusste Abweichung vom Einzelformular):**
  - **geleert:** alle Wert-Felder und die Zeilenliste (zurück auf eine leere Zeile)
  - **bleiben stehen:** `ts` und `report_ref` — Bericht-Kontext für Folgekorrekturen
    (z. B. Nachtrag eines vergessenen Markers aus demselben Befund).
  - Begründung: das Einzelformular leert `value`, `ts` und `reportRef`
    (`…labs-card.js:790-795`), weil dort jeder Wert ein eigener Vorgang mit eigenem
    Zeitpunkt ist. Beim Bericht gehört der Zeitpunkt zum Dokument, nicht zur Zeile.
- **Ablehnung:** Fehlerbanner aus `error.message` (Server rendert
  `Zeile 3 (kreatinin): unknown_marker`, §2.4); **alle** Eingaben bleiben erhalten, keine
  Daten-Reload-Nebenwirkung.
- Nach Erfolg: `_loadData(true)` / Panel-Refresh (Server hat `signal_refresh` gefeuert).

### 6.5 „Diesen Bericht verwerfen"

- Aktion neben `labs.last_report` (Karte: Button im Bericht-Kopf; Panel: Button unter der
  Kategorie-Leiste), **nur sichtbar/aktiv wenn `last_report.ts` gesetzt ist**.
- **Sicherheitsabfrage** vor dem Senden (`confirm()` mit Anzahl der betroffenen Werte aus
  `last_report.marker_keys`), dann WS `health_o_mat/remove_lab_report` mit
  `ts` (+ `report_ref` des letzten Berichts, **nur wenn** der Bericht eines trägt).
- Bei `no_active_report` (parallele Änderung): Fehlerbanner, Refresh — Aktion verschwindet.
- Kein Gruppen-Restore in der UI; Wiederherstellung bleibt beim bestehenden
  Restore/Verlauf-Pfad (`restore_entry`, `kind: lab_values`).

---

## 7. Admin-UI: Umrechnungen & Disclaimer-Schalter

**Ist (verifiziert):** Die Referenztabelle rendert Kategorie, Name, `canonical_unit`,
Referenzbereich, Reset (`health-o-mat-panel-admin.js:365-389`, Kopf 429-438) — `alt_units`
wird nicht genutzt, obwohl der Kommentar es nennt (354-355). Custom-Marker zeigen ihre
Alt-Einheit (`altUnitText`, 360-363, 402-413), aber ohne Faktor.

**Änderungen (Frontend + ein Settings-Feld):**

1. **Pflicht:** neue Spalte **„Umrechnung"** in der Katalog-Tabelle. Je `alt_units`-Paar:
   `{Alt-Einheit} × {factorText} → {canonical_unit}` — `factorText` ist **immer** das
   Ergebnis von `formatNumber(factor)` (`health-o-mat-panel-base.js:752-759`,
   `Intl.NumberFormat(intlLocale())`), nie ein Literal. Ergebnis z. B. de: `mg/dL × 17,1 →
   µmol/L`, en: `mg/dL × 17.1 → µmol/L`. Leeres `alt_units` → `—`.
   Richtung ist immer „Alt-Einheit → kanonische Einheit" (`alt_units` =
   `{unit: factor_to_canonical}`).
2. **Pflicht:** Marker mit `require_explicit_unit: true` bekommen zusätzlich das Badge
   **„Einheit Pflicht"** (dort ist die Verwechslungsgefahr g/g vs. mg/g am größten).
3. **Nice-to-have, zuletzt:** Custom-Marker-Zeile um den Faktor ergänzen —
   `Vitamin D (vitamin_d) — ng/mL · alt: nmol/L × {formatNumber(factor)}`, gleiche
   Code-Stelle (`altUnitText`).
4. **Pflicht:** In der Karte „Kategorien ausblenden"
   (`health-o-mat-panel-admin.js:441-446`) kommt unter einem Trenner die Checkbox
   **„Medizin-Hinweis im Panel ausblenden"** → schreibt `lab_hide_panel_disclaimer`
   (Default `false` = sichtbar). Gespeichert über den bestehenden Settings-Pfad
   (`SETTINGS_KEYS`, strikter Bool `_strict_bool`, `ws_api.py:230-242`); der **Lab-Tab**
   liest den Zustand ausschließlich aus `panel_data` (§8).

**Nachweis „keine neue Server-API für die Umrechnung":** `build_settings()` liefert
`"lab_catalog": {"categories": LAB_CATEGORIES, "markers": LAB_MARKERS}`
(`ws_api.py:1655-1659`) — verbatim inkl. `alt_units` und `require_explicit_unit`.

**Neue i18n-Keys** (de/en in `strings.json` + `translations/{de,en}.json`, Paritätstest
N-10): `ui_admin_lab_conversion`, `ui_admin_lab_conversion_required`,
`ui_admin_lab_conversion_none`, `ui_admin_lab_hide_disclaimer`. Aufnahme in die Whitelist
`_REQ_HOM_122_UI_KEYS` (`tests/test_translations.py:506-541`, geprüft von
`test_req_hom_122_common_ui_keys_exist_in_all_three_files`, 544-551).

---

## 8. Medizin-Hinweis im Panel

**Ist (verifiziert):**

- Card: Disclaimer vorhanden, Default **an**, per Editor-Checkbox bzw.
  `show_disclaimer: false` abschaltbar (`health-o-mat-labs-card.js:250, 363, 864-866,
  1289`) — Text heute **hartkodiert deutsch**.
- Panel: Der Lab-Tab (`labsTab`, `health-o-mat-panel-views.js:1066-1117`) rendert keinen
  kontextbezogenen Hinweis; nur der globale Footer (`health-o-mat-panel.js:1983-1987`).
- **`get_settings` ist admin-only** (`ADMIN_ONLY_COMMANDS`, `ws_api.py:129-131`,
  `is_admin_connection`-Check `ws_api.py:1736-1738`) → der Lab-Tab darf niemals
  `panel._settings` lesen (wäre für Nicht-Admins leer/schlicht falsch).

**Änderungen:**

1. **Panel-Hinweis, Default sichtbar:** Der Lab-Tab rendert oberhalb der Kategorie-Leiste
   die Hinweiszeile mit demselben Wortlaut wie die Card, i18n-Key
   `ui_panel_lab_disclaimer`. Sichtbar, wenn
   `panel_data.lab_hide_panel_disclaimer === false` (fehlend = `false` = sichtbar).
2. **Auch im Leerfall sichtbar:** Der Hinweis erscheint **vor** jeder Leerzustandsprüfung —
   also auch, wenn keine Kategorie sichtbar ist. Der Leerzustand wird präzisiert:
   - Kategorien existieren, sind aber **alle ausgeblendet** → neuer Text
     `ui_panel_lab_all_hidden` = „Alle Kategorien ausgeblendet".
   - Es gibt überhaupt keine Kategorie/Marker (z. B. `areas.labs` gerade aktiviert) →
     bestehender Text `ui_panel_lab_no_categories`.
3. **Abschaltbar nur im Admin:** Checkbox `lab_hide_panel_disclaimer`
   (`entry.options`, strikter Bool, Default `false`) in der Admin-Karte „Laborwerte" (§7.4).
   **Transport in den Lab-Tab: `panel_data`**, nicht `get_settings`. Der Wert überlebt beide
   Options-Schreibpfade (Merge, `ws_api.py:1774`; `config_flow.py:548-550`).
4. **CSS:** `.labs-disclaimer` existiert nur in `CARD_CSS` der Labs-Card
   (`health-o-mat-labs-card.js:276-279`) — für das Panel neu in `PANEL_CSS`
   (`health-o-mat-panel-base.js:275 ff.`) anlegen (gleiche Optik, getrennte Stylesheets).
5. **Karten-Disclaimer wird in dieser Erweiterung lokalisiert:** neue Keys
   `ui_card_lab_disclaimer` (de = exakt heutiger Text, en = sinngemäß) über die bestehende
   `setCardLanguage`-Logik der Karte; Paritätstest in `tests/test_translations.py`.
   Der übrige (nicht-Disclaimer-)Text der Karte bleibt unverändert deutsch — bewusste
   Scope-Grenze.
6. **Backup + Diagnostics:** `lab_hide_panel_disclaimer` in `backup.lab_options` (§2.16) und
   in die Redaktionsliste der Lab-Options (`diagnostics.py:57-63`).
7. **Nicht-Admin-Absicherung:** **statischer JS-Test** pinnt, dass
   `labsTab`/Panel-Lab-Rendering weder `_settings` noch `isAdmin` referenziert. Ein echter
   Nicht-Admin-E2E (eigener HA-User ohne Admin-Rechte) ist ein **dokumentierter
   Folge-Task** (§14), kein Blocker dieser Erweiterung.

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

  - title: Anzeige               # reine Anzeige, Personen-Dropdown
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

`person_mode: selector` + auskommentierter Filter statt `fixed` mit leerer `entry_id`: eine
leere `entry_id` bei `fixed` würde die Karte auf einen ungültigen Entry binden; das Dropdown
ist für ein Copy-Paste-Beispiel der robustere Default (`normalizeCardConfig`,
`health-o-mat-labs-card.js:234-252`).

**`person_filter`/`default_person` sind auskommentiert** — ein aktiver Filter auf eine nicht
existierende Person („max") würde die Karte in den Zustand „Keine Person passt zum
konfigurierten Personen-Filter." (`health-o-mat-labs-card.js:462`) bringen. Der
README-Hinweis lautet deshalb: „Personenfilter anpassen oder entfernen — ohne Filter zeigt
die Karte alle Personen."

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
- **Kein `LabReport`-Aggregat**, keine Report-Entität, keine neue Tabelle, **kein
  `batch_id`** — Gruppierung bleibt `ts` (+ optional `report_ref`).
- **Kein Per-Zeile-`ts`** im Batch (später additiv möglich, §14).
- **Kein Multi-Unit-Framework** — weiterhin genau ein optionales Alt-Einheit-Paar pro
  Custom-Marker; `alt_units` im Katalog unverändert.
- **Keine Änderung** an `unique_id`s, Entitäten oder Store-Schema (bleibt v5); Retention
  voidet statt zu archivieren.
- **Kein Archiv für Laborwerte** (im Gegensatz zu Getränken/BD).
- **Batch-Daten ändern das Backup-Format nicht:** nur zwei additive Optionsschlüssel
  (§2.16); `lab_readings[]` bleibt unverändert. Das **Lab-CSV** ändert sich (§2.15, bewusst).
- **Kein Service-Response** (`SupportsResponse`) und kein neuer Webhook/HTTP-Endpunkt.
- **Keine Migration der bestehenden Fehlerpfade** auf code-only/strukturiert — das ist
  REQ-HOM-127 mit eigenem Plan.
- **Kein Gruppen-Restore** eines Berichts (nur einzeln über `restore_entry`).
- `panel_data` wächst nur um die drei Felder aus §6.2 (`alt_units`, `last_report`,
  `lab_hide_panel_disclaimer`).
- Der restliche Karten-Text (außer dem Disclaimer) wird **nicht** lokalisiert.

---

## 11. Auswirkungen, REQ-IDs & Acceptance Criteria

**Prioritäten:** REQ-HOM-123/124/125 = **P2**, REQ-HOM-126 = **P3**.
**Release:** 0.16.2 (**PATCH**), Release/Tag/Notes sind nicht Teil der Tasks.

| Artefakt | Auswirkung |
|---|---|
| REQ-HOM-122 | bleibt gültig; Kriterium „Medizin-Disclaimer in Card/Panel/README" (`REQUIREMENTS.md:1213`) wird durch REQ-HOM-125 präzisiert, nicht rückwirkend umformuliert |
| `const.py` | `OPTION_LAB_HIDE_PANEL_DISCLAIMER`, `OPTION_LAB_RETENTION_MONTHS`, `LAB_REPORT_MAX_ROWS = 200` |
| `services.yaml` | `add_lab_report` (object+fields+multiple), `remove_lab_report` |
| `__init__.py` | Service-Handler `add_lab_report`/`remove_lab_report`; `_apply_lab_retention` im Setup neben `_apply_retention`; `add_lab_value` auf `coerce_lab_number` umgestellt |
| `store.py` | `add_lab_readings`, `void_lab_report`, `void_lab_readings_before` (je 1 Save, 1 Audit, Rollback) |
| `logic.py` | `validate_lab_report_rows(...) -> tuple[list[dict], dict \| None]`, `coerce_lab_number(value)`; `lab_report_matches(reading, ts, report_ref)` (HA-frei, fürs Undo) |
| `ws_api.py` | zwei neue Kommandos + Fehler-Envelope; `panel_data` +3 Felder; Settings um `lab_hide_panel_disclaimer` (Admin-Schreibpfad) |
| `config_flow.py` | `lab_retention_months` im Schritt `basics` neben `retention_months` |
| `exporter.py` | `lab_values.csv`: alle Zeilen (inkl. voided) + `voided_at`/`void_reason` |
| `importer.py` | **keine** Logikänderung; neue Spalten ignoriert, voidete Zeilen = `skipped` |
| `backup.py` | `lab_options` + `lab_hide_panel_disclaimer` + `lab_retention_months` |
| `restore.py` | unverändert (Lab-Options-Merge bleibt nur `lab_custom_markers`) |
| `diagnostics.py` | zwei neue Optionsschlüssel in die Redaktionsliste |
| JS | `health-o-mat-labs-card.js` (Dialog, Füllknöpfe, Einheiten-Dropdown, Verwerfen, lokalisierter Disclaimer, Fehler-Envelope), `health-o-mat-panel-views.js` (Dialog + Disclaimer + Leerzustand + Verwerfen), `health-o-mat-panel-admin.js` (Umrechnungs-Spalte, Disclaimer-Checkbox), `health-o-mat-panel.js` (Settings-Collect/PATCH), `health-o-mat-panel-base.js` (WS-Kommandos, `.labs-disclaimer` in `PANEL_CSS`) |
| i18n | UI-Keys + Admin-Keys + `ui_card_lab_disclaimer` + `ui_panel_lab_all_hidden` in `strings.json`/`{de,en}.json`; **Service-Block** `services.add_lab_report`/`services.remove_lab_report` |
| Tests | `test_dashboards.py` (§9.1), `test_translations.py` (Service-Parität + Karten-Disclaimer-Keys), Marker-Options-Mirror, Retention-/Undo-Suites (§12) |
| Store-Schema / Entities | **unverändert** |

**REQ-Vorschläge** (Requirements-Agent vergibt final). Reihenfolge:
123 → 128 → 129 (Retention) → 125 → 124 → 126 → (127 separat geplant).

### REQ-HOM-123 — Batch-Erfassung (`add_lab_report`) · P2
- [ ] Service: YAML-Beispiel aus §2.11 → `lab_readings` wächst um **4** Einträge, alle mit
      demselben `ts`/`report_ref`; der Service gibt **nichts** zurück.
- [ ] WS: derselbe Bericht liefert `{"ok": true, "written": 4, "ts": …}`.
- [ ] Ungültige Zeile 3 (unbekannter Marker) → Service: `ServiceValidationError` mit
      `Zeile 3 (kreatinin): unknown_marker`; WS: `{"ok": false, "error": {"code":
      "unknown_marker", "params": {"row": 3, "marker": "kreatinin"}}}`; `lab_readings`
      **und** `audit_log` unverändert.
- [ ] Zeilennummer = Originalzeile inkl. Leerzeilen (Leerzeile in Position 2 → Fehler in
      Zeile 3 meldet `row: 3`).
- [ ] Leerzeilen werden ignoriert: 3 Zeilen, davon 1 leer bzw. `{}` → 2 Werte, kein Fehler.
- [ ] Fehlercodes in genau dieser Reihenfolge: `invalid_ts`, `empty_report`,
      `too_many_rows` (201 befüllte Zeilen, `limit: 200`), `unknown_marker`,
      `unit_required`, `invalid_value`, `unsupported_unit`, `duplicate_marker`.
- [ ] Personenauflösung **vor** `invalid_ts`: unbekannte Person + kaputter `ts` → Entry-Fehler.
- [ ] `gpt` + `alt` im selben Batch → `duplicate_marker` mit `first_row`.
- [ ] Genau **ein** `_async_save`, **ein** `signal_refresh`, **ein** Audit-Eintrag
      `lab_values_added` (`count`, `marker_keys`/`reading_ids` ≤ 20, `created_at`, kein
      `report_ref`).
- [ ] `add_lab_value` mit `NaN`/`inf` → `invalid_value` (**Fixed**, gleicher Helper).
- [ ] Dialog: Start 1 leere Zeile, **60er**-Cap, Knöpfe „Alle sichtbaren Marker anlegen" und
      „Zuletzt verwendete Marker anlegen" (dedupe, Cap beachtet), Einheiten-Dropdown je Zeile
      mit kanonisch + `alt_units` + Freitext.

### REQ-HOM-124 — Admin-Sichtbarkeit der Umrechnungen · P2
- [ ] Katalog-Tabelle zeigt für `creatinine` mit **Systemsprache DE** `mg/dL × 88,4 →
      µmol/L` und mit **EN** `mg/dL × 88.4 → µmol/L` (Sprache im Test gesetzt; Faktor aus
      `formatNumber`).
- [ ] Marker mit leerem `alt_units` zeigen `—`.
- [ ] `urine_protein_creatinine_ratio` zeigt Badge „Einheit Pflicht" + Alt-Einheit.
- [ ] Kein neuer WS-Request/keine API-Änderung (Werte aus `settings.lab_catalog`).
- [ ] Neue Keys in `strings.json`/`de`/`en` und in `_REQ_HOM_122_UI_KEYS`.
- [ ] (Nice-to-have) Custom-Marker-Zeile zeigt `alt: <Einh.> × {formatNumber(factor)}`.

### REQ-HOM-125 — Medizin-Hinweis im Panel-Lab-Tab · P2
- [ ] Lab-Tab zeigt den Hinweis ohne Admin-Rechte und **ohne** `get_settings`; Quelle ist
      `panel_data.lab_hide_panel_disclaimer`.
- [ ] Hinweis ist **auch im Leerfall** sichtbar (alle Kategorien ausgeblendet) und der
      Leerzustand textet „Alle Kategorien ausgeblendet".
- [ ] Admin-Checkbox „Medizin-Hinweis im Panel ausblenden" schreibt
      `lab_hide_panel_disclaimer`; nach `true` ist der Hinweis im Tab weg, nach `false`
      wieder da (ohne Reload-Sonderweg).
- [ ] Statischer JS-Test: Lab-Tab-Quelle referenziert weder `_settings` noch `isAdmin`.
- [ ] Karten-Disclaimer nutzt `ui_card_lab_disclaimer` (de wortgleich zum bisherigen Text,
      en übersetzt) und folgt `setCardLanguage`; Paritätstest grün.
- [ ] `.labs-disclaimer` in `PANEL_CSS` definiert.
- [ ] `lab_hide_panel_disclaimer` in Backup und Diagnostics-Redaktion.

### REQ-HOM-126 — Beispiel-Dashboard · P3
- [ ] `examples/dashboard-labs-card.yaml` existiert, parst, nutzt nur
      `custom:health-o-mat-labs-card`-Keys aus `LABS_CARD_KEYS`.
- [ ] `pytest tests/test_dashboards.py` grün ohne Ausnahme-Regel für die neue Datei.
- [ ] README listet das neue Beispiel inkl. Hinweis „Personenfilter anpassen/entfernen".

### REQ-HOM-127 — Fehlercode-/i18n-Umbau der bestehenden Pfade (eigener Plan)
- [ ] **Nicht** Teil dieser Erweiterung. Ziel: bestehende Services/WS-Fehler auf
      code-only/strukturiert (`{code, params}`) migrieren und die Meldungstexte lokalisieren.
- [ ] Diese Spec liefert dafür nur das Referenzformat (§2.4) und die Werte-Tabelle.

### REQ-HOM-128 — Batch-Undo (`remove_lab_report`) · P2
- [ ] Service `remove_lab_report` mit `ts` (Pflicht) + `report_ref` (optional) voidet **alle**
      aktiven Werte dieses Zeitpunkts (mit `report_ref`: nur passende).
- [ ] Grenzfall dokumentiert + getestet: ohne `report_ref` werden bei mehreren Berichten mit
      identischem `ts` **alle** verworfen; mit `report_ref` nur der passende.
- [ ] Zeitvergleich über Instant (Offset-Varianten derselben Zeit treffen).
- [ ] Kein Treffer → `no_active_report`; ungültiges `ts` → `invalid_ts`.
- [ ] Ein Audit-Eintrag `lab_report_voided` (`count`, `reading_ids` ≤ 20, `created_at`),
      `void_reason = "report_discarded"`, ein Save, Rollback bei Save-Fehler.
- [ ] UI: „Diesen Bericht verwerfen" nur bei aktivem `labs.last_report`, mit
      Sicherheitsabfrage; nach Erfolg verschwindet die Aktion nach Refresh.
- [ ] Wiederherstellung einzeln über `restore_entry` (`kind: lab_values`) funktioniert.

### REQ-HOM-129 (Vorschlag, in REQ-123 enthalten falls nicht separat gewünscht) — Labor-Retention
> Kann als eigenes REQ geführt werden; hier als Kriterien dokumentiert, damit der Plan sie
> nicht vergisst.
- [ ] `lab_retention_months` (Default `0` = aus) im Options-Wizard „Grundlagen" neben
      `retention_months`, Bereich 0…120.
- [ ] Bei `> 0` werden beim Setup **nur** aktive Laborwerte älter als N Monate **voidet**
      (`void_reason = "retention"`), kein Archiv, keine Listenkürzung, keine Änderung an
      Getränken/BD.
- [ ] Genau **ein** Audit-Eintrag `lab_values_retention` pro Lauf, nur wenn `count > 0`;
      Wiederholungslauf ohne neue alte Werte erzeugt keinen Eintrag.
- [ ] `restore_entry` (`kind: lab_values`) macht einen retention-voideten Wert wieder aktiv.
- [ ] `lab_values.csv` enthält voidete Zeilen inkl. `voided_at`/`void_reason`; `drinks.csv`
      und Blutdruck-CSV bleiben unverändert (nur aktive).
- [ ] Re-Import der exportierten voideten Zeilen zählt sie als `skipped`, nicht als neu.

---

## 12. Teststrategie

| Ebene | Datei | Inhalt |
|---|---|---|
| HA-freie Logik | `tests/test_logic.py` | `validate_lab_report_rows`: Leerzeilen (`{}`, `""`-Zeilen, gemischt), alle **sieben** Codes der Funktion (`invalid_ts` liegt beim Aufrufer), Reihenfolge (`invalid_value` vor `unsupported_unit`), `bool`-Wert, `NaN`/`inf`, 200/201-Grenze, Alias-Kollision mit `first_row`, **Originalzeilen-Nummerierung inkl. Leerzeilen**, Rückgabe `(rows, None)` / `(rows, {code, params, message})`; `coerce_lab_number`; `lab_report_matches` (Instant-Vergleich, `report_ref`-Filter, `None`-Tag) |
| Store | `tests/test_store.py` | `add_lab_readings` (n Einträge, **ein** `_async_save`, **ein** Audit `lab_values_added`, Details ohne `report_ref`, Listen ≤ 20, `count` voll); `void_lab_report` (nur passende, `void_reason`, ein Audit `lab_report_voided`, `[]` bei keinem Treffer); `void_lab_readings_before` (nur `ts < cutoff`, nur aktive, ein Audit `lab_values_retention`, Idempotenz); **Rollback-Test für alle drei** (`_async_save` wirft → Listen inkl. `voided_*` exakt wie vorher, Exception propagiert) |
| Service | `tests/test_lab_services.py` | Erfolg (2 Marker, gemeinsames `ts`/`report_ref`), Alles-oder-nichts, jeder Code mit Originalzeile+Marker, `invalid_ts`-Härtung (Prosa gewrappt), Personenauflösung vor `invalid_ts`, `report_ref`-Cap 500, `add_lab_value`-Härtung (`NaN`/`inf` → `invalid_value`), `remove_lab_report` (Erfolg, `report_ref`-Filter, Grenzfall gleicher `ts`, `no_active_report`), Retention-Hook über `entry.options` |
| WS | `tests/test_ws_api.py` | beide Kommandos registriert; Erfolgs-Envelopes (`written`/`voided`); **Fehler-Envelope** `{"ok": false, "error": {code, params, message}}` statt `send_error`; `send_error` nur für unbekannten Entry; `entry_id`-Pflicht vor Fachprüfung; `PREVENT_EXTRA`; `{}`-Zeile ignoriert; `panel_data` liefert `alt_units` (Katalog + Custom), `last_report` und `lab_hide_panel_disclaimer` |
| Panel-/Card-JS | `tests/test_panel_js.py`, `tests/test_card_js.py` | Dialog: Startzeile, Add/Remove, 60er-Cap, Füllknöpfe (alle sichtbaren / zuletzt verwendet inkl. Dedupe), Einheiten-Dropdown aus `alt_units` + Freitext; Client-Validierung; Fehlerbanner aus `error.message`; Draft bleibt bei Fehler; Erfolg leert Werte + Zeilen, **behält** `ts`/`report_ref`; Single-Flight; Verwerfen nur bei `last_report` + `confirm()`; **statisch: Lab-Tab ohne `_settings`/`isAdmin`**; Disclaimer immer sichtbar (auch Leerfall, mit „Alle Kategorien ausgeblendet"), weg bei `lab_hide_panel_disclaimer`; Admin: Umrechnungs-Spalte (`formatNumber`), `—`, Badge, Disclaimer-Checkbox |
| i18n | `tests/test_translations.py` | UI-Keys in `_REQ_HOM_122_UI_KEYS` (506-541) inkl. `ui_panel_lab_disclaimer`, `ui_panel_lab_all_hidden`, `ui_card_lab_disclaimer`, Admin-Keys; `services.add_lab_report` + `services.remove_lab_report` in `strings.json`/`de`/`en`; `_LAB_SERVICE_FIELDS` (392-395) + `_LAB_TRANSLATED_FIELDS` (400-403) erweitert → Paritätstest (406-425) |
| Service-Schema-Mirror | `tests/test_lab_services.py` | `selector.select.options`-Werte von `add_lab_value` **und** `add_lab_report` == `set(LAB_MARKERS)`; `remove_lab_report`-Feldsatz wie spezifiziert |
| Dashboards | `tests/test_dashboards.py` | §9.1: Labs-Card-Typ + Key-Set; neue Datei besteht die Sammelprüfung |
| Export/Import | `tests/test_import_backup.py` | `lab_values.csv` enthält voidete Zeilen mit `voided_at`/`void_reason`; `drinks`/`bp` unverändert; Round-Trip: exportierte voidete Zeilen werden beim Import `skipped`, nicht neu angelegt; Backup enthält `lab_hide_panel_disclaimer`/`lab_retention_months` |
| Unverändert | `tests/test_restore.py` | Regressionslauf: Restore/Schema unberührt; `restore_entry` macht retention-voideten Wert aktiv |
| E2E | `tests_e2e/test_lab_values_e2e.py` (Erweiterung) | **(a) Batch:** 2 Zeilen über den Panel-Dialog → beide im `panel_data`-Payload; ungültige Zeile → Fehlerbanner mit Zeilenbezug, Eingaben bleiben, Payload unverändert. **(b) Disclaimer:** sichtbar ohne Admin-Settings-Load, nach Admin-Checkbox ausgeblendet, im Leerfall sichtbar. **(c) Admin-Faktorspalte:** `mg/dL × … → µmol/L` sichtbar. **(d) Beispiel-Dashboard:** Labs-Card aus `examples/dashboard-labs-card.yaml` rendert im Dashboard |

---

## 13. Risiken

| Risiko | Wirkung | Gegenmaßnahme |
|---|---|---|
| **Teil-Write bei Save-Fehler** | `_async_save()` schlägt nach der Mutation fehl → RAM und Disk divergieren | **Rollback** (§2.8): `deepcopy`-Snapshot von `lab_readings` + `audit_log` vor der Mutation, bei Exception exakt zurücksetzen und re-raisen (Vorbild `apply_retention`, `store.py:956-969`). Ein Save = der einzige Persistenzpunkt; ein Prozess-Absturz davor hinterlässt keinen Disk-Teilzustand |
| **Replay / Doppel-Submit** | doppelte Lesungen, verfälschte Verläufe | Keine Idempotenz (§2.12) — UI Single-Flight, **Retry-Hinweis** für externe Systeme (`last_report` prüfen), `remove_lab_report` als Ein-Schritt-Korrektur |
| **Retention löscht zu viel** | Nutzer verliert (scheinbar) Laborhistorie | Default `0` = aus; **voiden statt löschen** (über `restore_entry` rückholbar); Export enthält voidete Zeilen inkl. Grund; ein Audit-Eintrag pro Lauf macht die Wirkung nachvollziehbar |
| **Retention überrascht Bestandsnutzer** | plötzlich verschwundene Werte nach Options-Änderung | Wirkung nur bei explizit gesetztem `> 0`; unabhängig von `retention_months`; Werte bleiben im Export/Backup; Doku in README + Options-Beschreibung |
| **`remove_lab_report` trifft mehrere Berichte** | ein Bericht mit gleichem `ts` wird mitverworfen | Grenzfall dokumentiert (§2.13); UI sendet bei vorhandenem Tag immer `report_ref` mit; Sicherheitsabfrage nennt die Anzahl betroffener Werte |
| **Datenminimierung `report_ref`** | Freitext/Cloud-Link könnte in Audit, Diagnostics oder Export lecken | `report_ref` **nicht** in Audit-Details (§2.9); Diagnostics redigiert; Export enthält das Feld wie bisher (bestehende Spalte, bewusst) |
| **Nicht-atomar über zwei Systeme** (Service + WS) | zwei Prüfpfade könnten auseinanderlaufen | Beide rufen `logic.validate_lab_report_rows`; WS ruft **nicht** den Service (kein verschachtelter Service-Call) |
| **Panel liest Admin-Settings** | Nicht-Admins sähen einen falschen/zufälligen Disclaimer-Zustand | Zustand ausschließlich über `panel_data`; **statischer JS-Test** pinnt das (§8.7) |
| **UI-Duplikation Card/Panel** | Regeln driften auseinander | Paritätstests über beide Dateien (§12); bewusst kein Shared-Modul (§6.3) |
| **`panel_data`-Wachstum** | Payload größer, Performance | Nur drei additive Felder (kein Verlauf, keine Referenzdaten-Duplizierung); `alt_units` ist klein (max. 1–2 Paare je Marker) |
| **Nicht-Admin-E2E fehlt** | Regressionsrisiko beim `get_settings`-Zugriff | Als dokumentierte Lücke + Folge-Task (§14), statischer Test deckt die Klasse heute ab |

---

## 14. Offene Punkte

1. **Editor-Darstellung des `object`-Selectors:** Die `fields`-Variante (§2.2) ist der
   vorgesehene Weg; wie komfortabel der HA-Service-Editor Listen von Objekten rendert, ist
   bei der Umsetzung zu prüfen. Schema, YAML- und REST-Aufruf sind davon unabhängig gültig.
2. **Nicht-Admin-E2E:** Ein echter Test mit einem HA-Benutzer ohne Admin-Rechte (Disclaimer
   + Batch-Dialog ohne `get_settings`) ist ein **Folge-Task**; heute sichert der statische
   JS-Test nur die Zugriffsklasse ab.
3. **REQ-HOM-127 (Fehlercode-/i18n-Umbau):** Die bestehenden Services/WS-Fehler bleiben
   Prosa/`send_error`; die Migration auf `{code, params}` und lokalisierte Meldungen ist ein
   eigener Plan. Bis dahin sind Batch-Fehlertexte deutsch (Server-`message`).
4. **`formatLabValue`-Hardcoding in der Card:** Die Karte formatiert Werte hartkodiert mit
   `de-DE` (`health-o-mat-labs-card.js:131-135`) — vorbestehend, außerhalb dieses Scopes;
   der neue Admin-Formatter nutzt die locale-fähige Panel-Variante, der neue
   Disclaimer-Text nutzt `setCardLanguage`.
5. **Retention-REQ-Zuordnung:** Die Kriterien stehen in §11 als REQ-HOM-129-Vorschlag (bzw.
   als Teil von REQ-HOM-123) — finale Zuordnung durch den Requirements-Agent.

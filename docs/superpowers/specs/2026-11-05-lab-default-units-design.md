# Design: Anzeige-Einheiten für Laborwerte — Werkseinstellungen + pro Person (MINOR 0.22.0)

**Status:** ENTWURF (Review-Runde 2 eingearbeitet — abnahmereif) · **Datum:** 2026-11-05 · **Branch:** `feat/lab-default-units`
**Bezug:** REQ-HOM-122 (Laborwerte), REQ-HOM-133 (12 Marker + `require_explicit_unit`),
`docs/superpowers/specs/2026-10-30-lab-values-design.md` §3 (Einheiten-Konvertierung).
**Gate:** Dieses Dokument ist ein Konzept-/Design-Beitrag. Es enthält **keinen** Task-Plan,
keine `pipeline_stages` und keine Implementierung.

## 1. Kontext

Laborwerte werden heute **kanonisch** gespeichert und angezeigt: `convert_lab_value`
(`logic.py:1159`) rechnet die vom Nutzer gemeldete Einheit über
`LAB_MARKERS[*].alt_units` (Faktor = *gemeldet → kanonisch*) in die kanonische Einheit um;
danach rechnet niemand mehr zurück. Ergebnis: Ein deutscher Befund in `mg/dL` erscheint im
Panel dauerhaft als `µmol/L` (Kreatinin, Bilirubin, Lipide, Hämoglobin, …), obwohl der
Nutzer die Zahl in seiner gewohnten Einheit liest.

Bestehende Bausteine, auf denen dieses Design aufsetzt (verifiziert):

| Anker | Inhalt |
|---|---|
| `const.py:196-621` | `LAB_MARKERS`: 41 Marker, `canonical_unit` + `alt_units{unit: factor}` |
| `logic.py:998` | `_norm_unit`: case-/whitespace-/NFKC-/µ-toleranter Einheitenvergleich |
| `logic.py:1040/1113/1159` | Custom-Marker-Normalisierung, effektive Marker, Konvertierung |
| `ws_api.py:668-742` | `_labs_block`: `panel_data.labs.markers[*]` inkl. `unit`, `alt_units` |
| `ws_api.py:195-213/262-322` | `SETTINGS_KEYS`, `SETTINGS_SCHEMA` |
| `ws_api.py:2060/2116` | `build_settings`, `parse_settings_message` |
| `ws_api.py:505-524` | `labs`-Block + `lab_hide_panel_disclaimer` in `panel_data` |
| `backup.py:214-227`, `restore.py:615/1001/1015` | `lab_options`-Sektion und bestehender Options-Merge (Custom-Marker; `lab_default_units` **nicht** zurückgespielt, F14) |
| `sensor.py:495-513` | `LabValueSensor`, `native_unit_of_measurement = canonical_unit` |

**Entscheidungen, die als gesetzt gelten (D1–D4, nicht Gegenstand dieses Dokuments):**
D1 Anzeige-Konvertierung **nur** in der UI; D2 Custom-Marker erhalten eine optionale
`alt_units`-Map (Legacy-`alt_unit` bleibt lesbar); D3 Default-Einheit je Person in
`entry.options`; D4 Werkseinstellungen, pro Person übersteuerbar, ungültige Einheit →
kanonisch, nie ein Fehler.

## 2. Problem

| # | Problem | Auswirkung |
|---|---|---|
| P1 | Anzeige ist immer kanonisch, unabhängig von der Laborquelle | Nutzer muss bei jedem Wert im Kopf umrechnen (Faktor 17,1 / 88,4 / 0,0259 …) |
| P2 | Die Eingabe-Einheit ist ein Freitextfeld (`panel-views.js:1560`, `labs-card.js:883`) | Tippfehler/andere Schreibweise → `unsupported_unit` oder falsche Zahl; jeder Marker verlangt Wissen über die erlaubte Schreibweise |
| P3 | Custom-Marker können genau **eine** Alt-Einheit abbilden (`logic.py:1090-1102`) | Reale Befunde liefern mehrere Schreibweisen (z. B. `g/dL` **und** `g/L`); die zweite ist nicht eingebbar |
| P4 | Kein Ort für „ich lese Kreatinin immer in mg/dL" | Die Information lebt nur im Kopf des Nutzers, nicht in der Integration |

## 3. Ziel

1. Ein **pro Person** einstellbares Anzeige-Einheiten-Set: Werkseinstellung (sinnvolle
   Labor-Alltagseinheit) gilt automatisch, ist pro Marker übersteuerbar.
2. **Eingabe- und Anzeige-Einheit sind dieselbe** Auswahl: Das Einheitenfeld wird zum
   Dropdown mit dem Default vorausgewählt; ein Wert wird in der angezeigten Einheit
   eingegeben und **immer** mit expliziter Einheit gesendet.
3. Custom-Marker akzeptieren **mehrere** Alt-Einheiten (additive `alt_units`-Map).
4. Sensor-Entities, `unique_id`s, Store-Schema und CSV bleiben **unverändert kanonisch**.

## 4. Nicht-Ziele (verbindlich)

| Nicht-Ziel | Begründung |
|---|---|
| Keine Änderung an `native_unit_of_measurement` oder am Sensor-`state` | D1; Langzeitstatistik bleibt kanonisch, keine Statistik-Migration |
| Keine Änderung an `unique_id`, `object_id`, `translation_key`, Entity-Menge | HACS-Regel „`unique_id` nie ändern"; kein MAJOR, kein Migrations-Handler |
| Kein Store-Schema-Bump (`STORE_SCHEMA_VERSION` bleibt 5) | Es wird nichts Neues gespeichert |
| Kein `BACKUP_VERSION`-Bump | `lab_options` ist eine offene Map, das neue Feld ist additiv |
| Kein Config-Entry-Versions-Bump / `async_migrate_entry` | Optionen sind schemafrei; Normalisierung ist der Vertrag |
| Keine Änderung an `config_flow.py` (Options-Flow) | Labor-Optionen werden ausschließlich über die Admin-Maske (`get_settings`/`set_settings`) gepflegt — wie heute |
| CSV-Export und Import bleiben kanonisch | `exporter.py`/`importer.py` unangetastet; Rundung ist reine Anzeige |
| Keine Vereinheitlichung des Zahlen-Locales | Die Karte formatiert heute hart `de-DE` (`labs-card.js:288`), das Panel `intlLocale()`; das bleibt so (separates Issue) |
| Keine neuen Services / WS-Kommandos | Nur additive Felder in bestehenden Antworten |

## 5. Datenmodell

### 5.1 Werkseinstellungen — `LAB_DEFAULT_UNITS` (neu, `const.py`)

`dict[str, str]` — `marker_key -> anzeige_unit`. Jeder Wert **muss** `canonical_unit`
oder ein Key von `alt_units` sein (Testpflicht §12). Faktoren werden **unverändert** aus
`LAB_MARKERS` übernommen; diese Spec führt keine neuen Faktoren ein.

| Marker | `canonical_unit` | Default | Faktor `alt→canonical` |
|---|---|---|---|
| `bilirubin_total` | µmol/L | **mg/dL** | 17.1 |
| `creatinine` | µmol/L | **mg/dL** | 88.4 |
| `urea` | mmol/L | **mmol/L** (kanonisch) | 0.357 |
| `cholesterol_total` | mmol/L | **mg/dL** | 0.0259 |
| `ldl` | mmol/L | **mg/dL** | 0.0259 |
| `hdl` | mmol/L | **mg/dL** | 0.0259 |
| `triglycerides` | mmol/L | **mg/dL** | 0.0113 |
| `ft4` | pmol/L | **ng/dL** | 12.87 |
| `ft3` | pmol/L | **pg/mL** | 1.536 |
| `hemoglobin` | g/L | **g/dL** | 10 |
| `albumin` | g/L | **g/dL** | 10 |
| `hematocrit` | L/L | **%** | 0.01 |

Alle übrigen Marker: kein Eintrag → Default ist `canonical_unit`. Marker mit leerem
`alt_units` (z. B. `alt`, `tsh`, `crp`, `hba1c`) haben damit zwangsläufig nur eine
Anzeige-Einheit.

**F12 — warum `urea` den Werksdefault `mmol/L` (kanonisch) hat:** Der Katalogfaktor
`0.357` (`const.py:296`, `mg/dL → mmol/L`) ist die **BUN-Skala** (Stickstoff), nicht die
Harnstoff-Skala (`≈ 0.1665`). Eine Anzeige in `mg/dL` würde jeden Harnstoff-Befund um
Faktor ≈ 2,1 verzerren (30 mg/dL Harnstoff → 10,7 statt 5,0 mmol/L). Bis zur
Katalogkorrektur (eigenes Issue, §15 O-1) bleibt die Anzeige deshalb kanonisch; **der
Faktor wird nicht angefasst** — gemeldete `mg/dL`-Werte werden exakt wie heute
umgerechnet. Das ist eine Default-Wahl, keine neue Medizinlogik (§4).

### 5.2 Options-Schlüssel — `OPTION_LAB_DEFAULT_UNITS` (neu, `const.py`)

```python
OPTION_LAB_DEFAULT_UNITS = "lab_default_units"   # {marker_key: unit}
```

- **Persistenz:** `entry.options[OPTION_LAB_DEFAULT_UNITS]`, ein Objekt pro Person.
- **Bedeutung:** *Overrides* — nur was hier steht, übersteuert die Werkseinstellung.
  Ein fehlender Marker-Key bedeutet „Werkseinstellung gilt".
- **Explizit kanonisch:** Der Nutzer kann `{"creatinine": "µmol/L"}` speichern; das ist ein
  bewusster Override gegen den Werksdefault (nicht „kein Override").
- **Kein Eintrag in `_lab_options_snapshot`** (`__init__.py:132-152`): Die Option ist reine
  Anzeige, darf **keinen** Entry-Reload auslösen (Testpflicht §12).
- **Diagnostics — nur Zähler (F1):** `OPTION_LAB_DEFAULT_UNITS` kommt in
  `diagnostics._LAB_OPTION_KEYS` (`diagnostics.py:97-105`) und wird wie die übrigen
  Lab-Optionen **count-only** exportiert (`{"count": n}`). Ein verbatim-Export würde die
  Marker-Keys — inklusive Custom-Slugs aus Nutzer-Freitext, potenziell Diagnosen — in den
  öffentlich teilbaren Diagnostics-Download schreiben (§10/§12.4).

### 5.3 Auflösungs-Präzedenz (normativ)

| Stufe | Bedingung | Ergebnis |
|---|---|---|
| 1 | `options.lab_default_units[key]` vorhanden und (nach `_norm_unit`) eine erlaubte Einheit | Override, **in Katalogschreibweise** |
| 2 | sonst `LAB_DEFAULT_UNITS[key]` vorhanden und erlaubte Einheit | Werksdefault |
| 3 | sonst | `canonical_unit` |
| 4 | Defensive (Einheit erreicht den Konverter, ist aber weder kanonisch noch `alt_units`-Key) | `canonical_unit`, Faktor 1 — **nie** ein Fehler |

Gespeichert/ausgeliefert wird immer die **Katalogschreibweise** (`alt_units`-Key bzw.
`canonical_unit`), nie die Nutzereingabe. Das ist die Voraussetzung dafür, dass die UI
`default_unit`/`allowed_units` per String-Gleichheit prüfen kann (µ/μ-/`u`-Varianten aus
CSV sind damit eingeebnet). **Ausnahme:** `reported_unit` wird roh gespeichert
(`logic.py:1520`, `importer.py:472/619`) und deshalb **normalisiert** verglichen (F8, §8.1).

### 5.4 Custom-Marker: `alt_units`-Map (D2, additiv)

| Shape | Status | Normalisierung |
|---|---|---|
| `{"alt_unit": {"unit": "nmol/L", "factor_to_canonical": 2.5}}` | **Legacy, bleibt lesbar** | wird in `alt_units: {"nmol/L": 2.5}` überführt |
| `{"alt_units": {"nmol/L": 2.5, "µg/L": 0.4}}` | neu, kanonisch gespeichert | validiert |
| beide gleichzeitig | Mischer | Map gewinnt pro Einheit; Legacy füllt nur fehlende Keys |

Regeln der Normalisierung (`normalize_lab_custom_markers`):

1. `alt_units` muss ein Objekt sein; jeder Key ist eine nicht-leere Einheit, jeder Wert ein
   **positiver, endlicher** `float`. Ungültige Paare fallen einzeln weg (kein Abbruch).
2. Ein Key, dessen normalisierte Form `canonical_unit` entspricht, wird verworfen
   (Selbstumrechnung mit Faktor 1 ist kein Alt-Paar).
3. Duplikate nach `_norm_unit` kollabieren auf den **ersten** Key (Reihenfolge stabil).
4. Gespeichert wird ausschließlich `alt_units`; `alt_unit` wird **nicht** mehr geschrieben.
   **Nur `set_settings` schreibt** (über die Normalisierung in `parse_settings_message`);
   `build_settings` **liest** ausschließlich und normalisiert lediglich die Antwort — es
   persistiert nichts (F13). Bestehende Einträge werden damit beim nächsten Speichern
   idempotent umgeformt — kein Migrations-Handler.

### 5.5 Kuratierte Einheitenliste — `LAB_UNITS` (neu, `const.py`)

`tuple[str, ...]` — feste, deduplizierte Menge **aller** in `LAB_MARKERS` vorkommenden
Schreibweisen (`canonical_unit` ∪ `alt_units`-Keys); die Reihenfolge ist die Dropdown-Reihenfolge
und nicht normativ. Kein erfundenes Unit-Vokabular.

```
"%", "10^12/L", "10^9/L", "10⁶/µL", "fl", "g/dL", "g/L", "g/g", "L/L", "mIU/L",
"mg/dL", "mg/L", "mg/g", "mL/min/1.73m²", "mm/h", "mmol/L", "mmol/mol", "ng/dL",
"ng/mL", "pg", "pg/mL", "pmol/L", "U/L", "µg/L", "µkat/L", "µmol/L", "µm³"
```

Verwendung: Dropdown im Custom-Marker-Formular (Haupt- und Zusatz-Einheiten) mit
Fallback „Andere …" (Freitext). Die Liste ist eine **UI-Komfortliste**, keine Validierung:
Der Server akzeptiert weiterhin jede vom Nutzer definierte Einheit als `canonical_unit`.

## 6. HA-freie Logik (`logic.py`)

Alle Funktionen importieren kein `homeassistant` und sind ohne HA-Paket testbar.

```python
def lab_allowed_units(marker_def: dict) -> list[str]: ...
def resolve_lab_display_unit(
    marker_key: str, marker_def: dict, defaults: Any
) -> str: ...
def normalize_lab_default_units(
    raw: Any, custom_markers: Any = None
) -> dict[str, str]: ...
def convert_lab_display_value(
    marker_def: dict, value: Any, unit: str | None
) -> tuple[float, str] | None: ...
def lab_display_decimals(value: float) -> int: ...
```

| Funktion | Vertrag |
|---|---|
| `lab_allowed_units` | `[canonical_unit]` + `alt_units`-Keys, dedupliziert über `_norm_unit`, **kanonisch zuerst**, danach Einfügereihenfolge der Map. Leere/fehlende `canonical_unit` → `[]`. Enthält kanonisch **und** alle Alt-Einheiten, also jeden gültigen Default. |
| `normalize_lab_default_units` | `raw` kein Objekt → `{}`. Marker-Key: `str().strip().lower()` + `LAB_MARKER_ALIASES` (wie `resolve_lab_marker`); unbekannter Marker (nicht in `effective_lab_markers(custom_markers)`) → Eintrag **verwerfen**. Einheit: über `_norm_unit` gegen `lab_allowed_units` auflösen → **Katalogschreibweise**; nicht auflösbar → `canonical_unit` (D4, kein Fehler). Deterministische Key-Reihenfolge (Eingabereihenfolge). |
| `resolve_lab_display_unit` | Präzedenz §5.3. `defaults` darf roh/`None` sein; defensiv, wirft nie. |
| `convert_lab_display_value` | `factor = alt_units[unit]` (bzw. 1 bei kanonisch/`None`); `display = canonical_value / factor`, `round(…, 6)`. Nicht-numerischer Wert → `None`. Unbekannte Einheit → `(value, canonical_unit)` (Faktor 1). **Kein Produktionsaufrufer** (D1): Referenz-Oracle für die zwei JS-Implementierungen und für die Tests (§12). |
| `lab_display_decimals` | Siehe §8 (Dezimal-Policy), Rückgabe 0–3. Ebenfalls Oracle, kein Produktionsaufrufer. |
| `normalize_lab_custom_markers` (geändert) | §5.4; zusätzlich `require_explicit_unit` unverändert. |
| `effective_lab_markers` (geändert) | Custom-Marker übernimmt die **Map** (`alt_units`), nicht mehr das Einzelpaar; das Ergebnis trägt weiterhin einheitlich `canonical_unit` (= Custom-`unit`) + `alt_units`, damit `lab_allowed_units` und `resolve_lab_display_unit` für Katalog und Custom identisch arbeiten. `convert_lab_value` bleibt unverändert (gemeldet → kanonisch). |

**Begründung „Oracle ohne Produktionsaufrufer":** Panel (`panel-base.js`/`views`) und
Karte (`labs-card.js`) sind bewusst getrennte Modul-Graphen; die Karte darf nicht aus dem
Panel importieren (`labs-card.js:10-15`) und dupliziert die Helfer. Ohne sprachneutralen
Oracle driften die zwei Kopien. Ein Node-Runner-Test vergleicht beide JS-Helfer gegen
`convert_lab_display_value`/`lab_display_decimals` über eine feste Wertetabelle (§12).

## 7. Wire-Vertrag

### 7.1 `panel_data.labs.markers[*]` (additiv)

```json
"creatinine": {
  "unit": "µmol/L",                 // unverändert: kanonisch
  "alt_units": {"mg/dL": 88.4},     // unverändert (bereits ausgeliefert)
  "default_unit": "mg/dL",          // NEU: aufgelöste Anzeige-Einheit
  "allowed_units": ["µmol/L", "mg/dL"]  // NEU: kanonisch zuerst, deterministisch
}
```

- `default_unit` = Ergebnis von `resolve_lab_display_unit` (§5.3) — **nicht** die rohe Option.
- `allowed_units` = `lab_allowed_units`; enthält `default_unit` garantiert.
- Kein bestehender Key wird umbenannt oder entfernt; ältere Karten ignorieren die neuen Keys.
- `_labs_block` berechnet `defaults = normalize_lab_default_units(options.get(…), custom_markers)`
  **einmal** vor der Marker-Schleife (`ws_api.py:695`).

### 7.2 `get_settings` / `set_settings`

| Key | Richtung | Inhalt |
|---|---|---|
| `lab_default_units` | lesen + schreiben | normalisierte Override-Map (§6) |
| `lab_default_units_factory` | **nur lesen** | `dict(LAB_DEFAULT_UNITS)` — damit die Admin-Maske „Standard (mg/dL)" rendern kann, ohne die Konstante zu duplizieren |
| `lab_allowed_units` | **nur lesen** | `{marker_key: list[str]}` aus `lab_allowed_units()` über **alle effektiven** Marker (`effective_lab_markers`, Katalog **und** Custom inkl. deren `alt_units`). **Einzige** Quelle für die Anzeige-Selects (§9.1) — JS baut die Auflösung nicht nach (F11). |
| `lab_units` | **nur lesen** | `list(LAB_UNITS)` — **ausschließlich** die Einheiten-Dropdowns des Custom-Marker-**Formulars** (§9.2), nie die Anzeige-Selects (F11) |

- `SETTINGS_KEYS` (`ws_api.py:195`) erhält `OPTION_LAB_DEFAULT_UNITS`.
- `SETTINGS_SCHEMA` (`ws_api.py:262`) behält `vol.Optional(OPTION_LAB_DEFAULT_UNITS): dict`
  **nur als Typ-Dokumentation** (Muster der übrigen Lab-Keys). Der Wert darf das Schema
  **nie** erreichen: `vol.Schema` ist `PREVENT_EXTRA`, und ein schema-akzeptierter Rohwert
  würde die normalisierte Map überschreiben (F7).
- `parse_settings_message` (`ws_api.py:2116`): eigener Block **nach** dem
  `OPTION_LAB_CUSTOM_MARKERS`-Block. **Pflicht (F7):** der Key wird dort zuerst
  `raw.pop(OPTION_LAB_DEFAULT_UNITS)` — exakt wie `OPTION_LAB_REF_OVERRIDES`
  (`ws_api.py:2187`) — **vor** `updates.update(SETTINGS_SCHEMA(raw))` (`ws_api.py:2210`);
  danach schreibt nur die normalisierte Map in `updates`. Die Defaults werden gegen den
  **neuen** Marker-Satz validiert (`updates.get(OPTION_LAB_CUSTOM_MARKERS)`, nicht
  `previous_markers`) — dasselbe Payload kann Marker und Defaults ändern. Kein Objekt →
  `invalid_setting("lab_default_units")`; unbekannte Marker/Units sind **kein** Fehler
  (Normalisierung verwirft bzw. fällt auf kanonisch zurück).
- `build_settings` (`ws_api.py:2060`) **liest** nur (§5.4 Nr. 4) und liefert
  `lab_default_units` normalisiert (gegen die gespeicherten Custom-Marker) plus die drei
  Read-only-Keys. `set_settings` antwortet weiterhin mit dem vollständigen
  `build_settings`-Payload.

### 7.3 Backup / Restore

| Ort | Änderung |
|---|---|
| `backup.py:214` | `lab_options[entry_id]` erhält `OPTION_LAB_DEFAULT_UNITS: entry.options.get(…, {})`; Docstring `backup.py:122` nachziehen. `BACKUP_VERSION` bleibt 3. |
| `restore.py:615` (`plan_restore`) | **Keine Änderung in v1** (F14): kein Parameter, kein `RestorePlan`-Feld. |
| Merge / Apply | **Kein Restore-Pfad in v1** (F14). Der Key wird wie `lab_ref_overrides`, `lab_hidden_categories` und `lab_hide_panel_disclaimer` behandelt: **Backup enthält ihn, Restore wendet ihn nicht an.** |

**F14 — bewusste YAGNI-Kürzung:** Ein Restore von Anzeige-Präferenzen ist nicht Teil
dieses Changesets. Backup enthält den Key (Datenvollständigkeit), aber `plan_restore` /
`apply_restore` ignorieren ihn — genau wie die drei anderen Lab-Optionen. Das hält den
Restore-Pfad frei von einer zweiten Marker-abhängigen Validierung und vermeidet eine
stille Options-Mutation beim Einspielen fremder Backups. Der vollständige Restore/Apply
ist als explizites Follow-up-Issue in §15 (O-4) festgehalten.

## 8. Anzeige-Konvertierung (UI) + Dezimal-Policy

### 8.1 Regeln

| Größe | Regel |
|---|---|
| Anzeigewert | `faktor = marker.alt_units[display_unit]`; `anzeige = kanonischer_wert / faktor`. `display_unit == marker.unit` → Faktor 1, keine Änderung. Fehlt der Faktor (defensiv) → kanonisch. |
| Referenz `ref_min`/`ref_max` | Mit **demselben** Faktor **und demselben** `d` wie der Messwert formatiert (§8.2 N4) — es gibt keinen `d+1`-Sonderpfad für Grenzen (F4/N1); `null` bleibt `null`. |
| Chart-Band/-Linie | Der Chart-Helper (`panel-base.js:1539`) bleibt einheitenblind; der Aufrufer übergibt bereits konvertierte `history[*].value` **und** `refMin`/`refMax`. Achsen-/Tooltip-Einheitenlabel ist **`default_unit`** (nicht `marker.unit`/kanonisch — F15). Sparkline (`panel-base.js:1512`) ist relativ → unverändert. |
| `in_range` / Badge | **Unverändert kanonisch** (Server, `ws_api.py:729`). Keine Neuberechnung in der UI, unabhängig von Anzeige-Rundung (F4). |
| `reported_unit`-Subzeile | Vergleich **normalisiert** gegen die **Anzeige**-Einheit (F8): `reported_unit` wird roh gespeichert (`logic.py:1520`, `importer.py:472/619`), deshalb JS-Pendant von `_norm_unit` — NFKC + Mikro-/Case-Faltung + ASCII-`u`-Präfix — statt `===`. Gleichheit → keine Subzeile (kein Rauschen, wenn in der Default-Einheit eingegeben wurde). |
| Eingabe | Die UI sendet die gewählte Einheit **immer explizit** (nie leer), sonst interpretiert der Server den Wert als kanonisch. Clientseitig erzwungen (F10): im „Andere …"-Zweig blockiert ein **leeres** Freitextfeld den Submit mit sichtbarer Fehlermeldung (`ui_panel_lab_unit_required`), statt eine leere Einheit zu senden. |

### 8.2 Dezimal-Policy (normativ)

**Gewählt: betragsbasiertes Maximum der Nachkommastellen, keine Marker-Tabelle.**

| Regel | Inhalt |
|---|---|
| N1 | Rundung ausschließlich bei der Formatierung — nie im Store, nie im WS-Payload, nie in `in_range`. |
| N2 | `base_d` nach Betrag des **konvertierten Anzeigewerts**: `abs(v) >= 100 → 0`, `abs(v) >= 10 → 1`, `abs(v) >= 1 → 2`, sonst `3`. |
| N3 | Das finale `d` (N4) ist eine **Obergrenze** (`Intl.NumberFormat(..., {maximumFractionDigits: d})`), keine feste Stellenzahl: `0,9` bleibt `0,9`, nicht `0,900` → **keine erfundene Präzision**. |
| N3a | `abs(v) > 0` und `abs(v) < 0.1`: `maximumSignificantDigits: 2` statt fester Nachkommastellen — verhindert die Anzeige `0` nach extremer Umrechnung (z. B. Custom-Faktor 1e6). |
| N4 | **Eine Quelle (F9, F4/N1):** `base_d` nach N2 aus dem **konvertierten Anzeigewert**, dann **einmal** `d = min(base_d + 1, 3)`. Dieses `d` gilt **identisch** für (a) den angezeigten Wert, (b) `ref_min`/`ref_max`, (c) Chart-Band und Chart-Achse/-Tooltip. Keine zweite Dezimalberechnung, **kein `d+1` nur für Grenzen**. Wegen des gemeinsamen, monotonen Rundungsrasters kann ein kanonisch `in_range`-Wert nie über seiner angezeigten Obergrenze erscheinen, ein Ausreißer nie unter seiner angezeigten Untergrenze. |
| N5 | `in_range` bleibt **kanonisch** berechnet (Server, `logic.lab_marker_in_range`); die Anzeige-Rundung beeinflusst den Badge nie (F4). |
| N6 | Identische Implementierung in `panel-base.js` (exportiert) und `labs-card.js` (Kopie); Oracle: `logic.lab_display_decimals`. |

**Warum Wert und Grenzen dasselbe `d` teilen (F4/N1):** Die frühere Regel „Grenzen `d+1`, Wert `d`"
war einseitig: sie schützte nur den Fall, dass eine Grenze auf denselben gerundeten Wert wie der
Messwert fällt, und ließ zu, dass der gerundete Messwert über seiner eigenen angezeigten Grenze
stand. Mit gemeinsamem `d` liegen Wert, Grenzen und Band auf derselben Rasterskala; die Monotonie
folgt direkt aus der monotonen Rundung (N4). **Bewusster, akzeptierter Preis:** eine
Nachkommastelle mehr optisches Rauschen — Kreatinin `106` µmol/L zeigt `1,199` statt `1,2`,
Kreatinin `106,1` zeigt `1,2` gegen die Grenze `1,199` (numerisch 1,200 bzw. 1,199 auf `d = 3`;
N3 trimmt die abschließende Null).

**Warum nicht `display_decimals` pro Marker?** Zweiter Pflegekatalog (41 Marker + jeder
Custom-Marker + Admin-UI + Backup-Feld) für einen reinen Formatierungswert. Die Betragsregel
ist zustandsfrei, unit-unabhängig und mit `maximumFractionDigits` nicht präzisionserfindend;
Nachteil (bewusst): sehr kleine/large Werte verlieren Stellen — akzeptiert, weil die kanonische
Zahl unangetastet bleibt.

Beispiele (Faktoren aus §5.1, `d = min(base_d + 1, 3)`):

| Eingabe (kanonisch) | Anzeige (konvertiert) | `base_d` | `d` | Ergebnis |
|---|---|---|---|---|
| Kreatinin 79.6 µmol/L | 0.900453 mg/dL | 3 | 3 | `0,9` |
| Bilirubin 15 µmol/L | 0.877193 mg/dL | 3 | 3 | `0,877` |
| Hämoglobin 145 g/L | 14.5000 g/dL | 1 | 2 | `14,5` |
| Cholesterin 5.2 mmol/L | 200.7722 mg/dL | 0 | 1 | `200,8` |
| Triglyceride 1.7 mmol/L | 150.4425 mg/dL | 0 | 1 | `150,4` |
| fT4 15 pmol/L | 1.165501 ng/dL | 2 | 3 | `1,166` |
| fT3 5 pmol/L | 3.255208 pg/mL | 2 | 3 | `3,255` |
| Hämatokrit 0.42 L/L | 42.0000 % | 1 | 2 | `42` |

Grenzfälle der **gemeinsamen** Präzision (F4/N1, Testpflicht §12.2): Messwert **knapp über**
dem Katalog-`ref_max` (kanonisch `in_range = false`, Badge „high") bzw. **exakt auf**
`ref_max` (kanonisch `in_range = true`, Badge „normal"). Wert und Grenze nutzen dasselbe `d`;
`base_d` bezieht sich in beiden Zeilen auf den konvertierten Messwert:

| Marker (kanonisch) | Anzeige-Wert | `base_d` | `d` | Wert | Grenze (gleiches `d`) | Badge |
|---|---|---|---|---|---|---|
| Kreatinin 106.1 µmol/L | 1.200226 mg/dL (`ref_max` 1.199095) | 2 | 3 | `1,2` | `1,199` | high |
| Kreatinin 106.0 µmol/L | 1.199095 mg/dL (`ref_max` 1.199095) | 2 | 3 | `1,199` | `1,199` | normal |
| Cholesterin 5.21 mmol/L | 201.1583 mg/dL (`ref_max` 200.7722) | 0 | 1 | `201,2` | `200,8` | high |
| Cholesterin 5.2 mmol/L | 200.7722 mg/dL (`ref_max` 200.7722) | 0 | 1 | `200,8` | `200,8` | normal |
| Bilirubin 21.1 µmol/L | 1.233918 mg/dL (`ref_max` 1.228070) | 2 | 3 | `1,234` | `1,228` | high |
| Bilirubin 21.0 µmol/L | 1.228070 mg/dL (`ref_max` 1.228070) | 2 | 3 | `1,228` | `1,228` | normal |
| fT4 23.1 pmol/L | 1.794872 ng/dL (`ref_max` 1.787102) | 2 | 3 | `1,795` | `1,787` | high |
| fT4 23.0 pmol/L | 1.787102 ng/dL (`ref_max` 1.787102) | 2 | 3 | `1,787` | `1,787` | normal |

Hinweis zur Kreatinin-Zeile `106,1`: der Wert rundet bei `d = 3` numerisch auf `1,200`; N3
(`maximumFractionDigits`, keine Mindeststellen) zeigt ihn als `1,2` — die Grenze `1,199` bleibt
sichtbar darunter, Anzeige und Badge „high" stimmen überein. Der Zwilling `106,0` zeigt `1,199`
und steht **nicht** über der Grenze (Badge „normal").

## 9. UI

### 9.1 Admin: Anzeige-Spalte (zwei Orte, `panel-admin.js:339-450`)

Die Anzeige-Einheit wird an **zwei konkreten Stellen** gerendert, nicht „je Marker"
irgendwo (F5) — beide nutzen dasselbe Feld-Namensschema und denselben Collector:

| Ort | Anker | Rendering |
|---|---|---|
| **Katalog-Marker** | `refRows` (`panel-admin.js:401-426`) | Neue Spalte **„Anzeige"** in der Referenztabelle: pro `<tr>` ein `<select data-field="lab-default-unit-<key>">` mit `<option value="">Standard (<factory-default>)</option>` + allen `allowed_units` des Markers. |
| **Gespeicherte Custom-Marker** | `customRows` (`panel-admin.js:439-450`) | Die bisherige `<li>`-Textzeile erhält zusätzlich dasselbe `<select data-field="lab-default-unit-<key>">` (Key = `marker.key`; bei noch nicht gespeicherten Draft-Markern ohne Key nicht gerendert — bekannte Grenze unten). Optionen aus `allowed_units` des Custom-Markers (= `unit` + `alt_units`-Keys). Die leere Option heißt hier „Standard (<`marker.unit`>)": `LAB_DEFAULT_UNITS` hat keinen Custom-Eintrag, Werksdefault ist die kanonische Einheit (§5.3 Stufe 3). |

- **Optionsquelle (F11):** ausschließlich `settings.lab_allowed_units[key]`. `lab_units`
  ist **nur** für die Einheiten-Dropdowns des Custom-Marker-Formulars (§9.2) — die
  Anzeige-Selects dürfen daraus **nicht** befüllt werden (sonst fehlen Custom-Alt-Einheiten
  und die Kuration würde zur Validierung). Standard-Text aus `lab_default_units_factory`.
  Kein zweites Unit-Vokabular im JS, keine Nachbildung von `lab_allowed_units`.
- Sammeln: `_collectSettingsPayload` (`panel.js:1003`, Rückgabe `:1176`) baut `lab_default_units` nur aus
  Selects mit nicht-leerem Wert (leer = Override entfernen). `_changedSettings`
  (`panel.js:1202`) vergleicht per `stableJson`; nur Änderungen werden gesendet (PATCH).
- Bekannte Grenze: Ein **neu** angelegter Custom-Marker hat bis zum ersten Speichern
  keinen `key` (`key` entsteht serverseitig, `logic.py:1072`) → Anzeige-Einheit erst nach
  dem ersten Speichern wählbar. Dokumentiert, kein Workaround.

### 9.2 Admin: Custom-Marker-Formular (`panel-admin.js:496-533`)

| Feld | Vorher | Nachher |
|---|---|---|
| Haupt-Einheit | Text-Input `lab-custom-unit` (`panel-admin.js:503`) | `<select data-field="lab-custom-unit">` aus `lab_units` + „Andere …" → Freitext `lab-custom-unit-custom` |
| Zusatz-Einheiten | ein Paar (`lab-custom-alt-unit`/`-factor`, `panel-admin.js:520`) | N Zeilen `lab-custom-alt-unit-<i>`/`lab-custom-alt-factor-<i>` (Select + Faktor), „Weitere Einheit hinzufügen" (`data-action="lab-custom-alt-add"`), Entfernen (`…-remove`); UI-Cap 4, Default 1 Zeile |
| Payload | `marker.alt_unit = {unit, factor_to_canonical}` (`panel.js:2095`) | `marker.alt_units = {unit: factor, …}` aus allen nicht-leeren Zeilen |

**Einheiten-Identität (F3):** `LAB_UNITS` (§5.5) ist eine Komfortliste, keine Validierung.
Ist die gespeicherte `marker.unit` **nicht** in `LAB_UNITS` (real: `nmol/L` bei einem
Custom-Marker, vgl. `tests/test_logic.py:1590-1605`), darf das Select die Einheit nicht
still auf den ersten Eintrag setzen:

- `__custom__` ist vorausgewählt und das Freitextfeld `lab-custom-unit-custom` ist mit dem
  **gespeicherten** Wert vorbefüllt (kein Datenverlust beim bloßen Öffnen/Speichern).
- Dasselbe gilt pro Zusatzzeile, deren gespeicherter `alt_units`-Key nicht in `LAB_UNITS`
  steht: Zeile auf `__custom__` + Freitext vorbefüllt.
- Der Vergleich läuft über die normalisierte Form (JS-Pendant von `_norm_unit`: NFKC +
  Case-/Whitespace-/µ-Faltung), damit `µmol/L` nicht wegen einer Schreibweise als „custom"
  gilt.

**Referenz-Umrechnungsspalte (F6):** `customRows` rendert heute `altUnitText`
(`panel-admin.js:361-368`, Aufruf `:444`) und liest ausschließlich `marker.alt_unit`. Nach
der Shape-Umstellung (D2) muss die Zeile auf den bestehenden `conversionText`-Helper
(`panel-admin.js:373-393`) wechseln — **erweitert** um Legacy-Unterstützung: `alt_units`-Map
gewinnt, ein vorhandenes `alt_unit` wird als Ein-Paar-Map gelesen (`{unit: factor}`); die
kanonische Ziel-Einheit ist `marker.canonical_unit || marker.unit` (Custom-Marker tragen
`unit`, Katalog-Marker `canonical_unit`). Ohne das ist die REQ-HOM-124-Umrechnungsspalte
bei Custom-Markern leer.

State: `panel._labCustomAltRows[entryId]` (Integer, Default 1) — kein Objekt-Draft, damit
das bestehende `_labCustomDraft`-Muster unangetastet bleibt.

### 9.3 Einzel-Erfassung — Panel **und** Karte

| Ort | Änderung |
|---|---|
| `panel-views.js:1551-1572` | `<select data-field="lab-add-unit">` (Optionen aus `allowed_units`, vorausgewählt `default_unit`) + `<input data-field="lab-add-unit-custom" hidden>` (Freitext für „Andere …"). Beide stehen immer im DOM; `hidden` wird umgeschaltet. `submitLabValue` (`:957`) liest bei `__custom__` den Freitext, sonst den Select und sendet **immer** eine Einheit. |
| `labs-card.js:856-903` | dito: `_entryForm` rendert Select + verstecktes Freitextfeld; `_draft.unit` wird beim Markerwechsel auf `marker.default_unit` gesetzt. `_collectDraftFromDom`/`_onFieldChange` lösen `__custom__` auf. |
| `panel-views.js:1051` / `labs-card.js:1005` | `unitOptions(marker, selectedUnit)` / `_unitOptions`: `current = selectedUnit || marker.default_unit || marker.unit`; Optionen aus `marker.allowed_units` (Fallback: `[unit, ...Object.keys(alt_units)]`). `require_explicit_unit`-Hinweis bleibt unverändert. |
| Markerwechsel | Panel: Fall in `panel.js::_onChange` (`:2238`, neben `handleLabReportChange`) — Unit-Select auf `marker.default_unit` neu aufbauen. Karte: `_updateUnitPlaceholder` (`labs-card.js:918`) bleibt für das Freitextfeld erhalten (Test-Vertrag), zusätzlich Select-/Draft-Reset. |
| „Andere …" leer (F10) | `__custom__` mit leerem Freitext blockiert den Submit (sichtbarer Fehler, `ui_panel_lab_unit_required`) — keine leere Einheit an den Server. Gilt für Panel- und Karten-Formular sowie für Berichtszeilen (§9.4). |

### 9.4 Berichts-Dialog (Panel + Karte)

- `emptyLabReportRow(unit)` → `{marker: "", value: "", unit}`; „Zeile hinzufügen" und
  `fillLabReportDraft`/`_fillReportDraft` setzen `unit = markers[key].default_unit`.
- Markerwechsel in einer Zeile: `row.unit = markers[neuer_key].default_unit`
  (`panel-views.js:1181`, `labs-card.js:1408`).
- **Wichtig (F2):** Die „leere Zeile"-Erkennung darf nicht mehr `!row.unit` verwenden —
  **in beiden Dateien**: `panel-views.js:1238` und `labs-card.js:1137`, sonst gilt jede
  vorausgewählte Zeile als belegt und die Fill-Buttons legen keine Zeilen mehr an.
  Neue Bedingung für **beide**: `!row.marker && !row.value`.
- **Zeilen-Wiederverwendung — Einheit mitziehen (N2):** Beide Pfade (`panel-views.js:1239`,
  `labs-card.js:1139`) setzen beim Wiederverwenden **beides**: `empty.marker = key` **und**
  `empty.unit = markers[key].default_unit`. Sonst erbt die Zeile die Default-Einheit des
  vorherigen Markers und der Wert wird still in einer Fremdeinheit konvertiert. Die neu
  angelegte Zeile setzt `unit: markers[key].default_unit` ebenfalls.
- „Andere …" setzt `row.unit = ""` und zeigt den Freitext (bestehendes Verhalten,
  `panel-views.js:1188`).
- **Einheit nie leer (F10):** Ist `row.unit === ""` („Andere …") und das Freitextfeld
  `lab-report-unit-custom-<i>` leer, blockiert `submitLabReport` (`panel-views.js:1251`)
  bzw. das Karten-Pendant den Submit mit sichtbarer Fehlermeldung
  (`ui_panel_lab_unit_required`) — identisch für die Einzel-Erfassung (§9.3). Es wird
  **keine** leere Einheit gesendet.

### 9.5 Anzeige der Werte

| Ort | Änderung |
|---|---|
| `labs-card.js:251` (`labReportedSubline`) | Signatur `(marker, displayUnit)`; Vergleich **normalisiert** (NFKC + Mikro-/Case-Faltung, JS-Pendant `_norm_unit`) gegen `displayUnit` — `reported_unit` ist roh gespeichert (F8). |
| `panel-base.js:1497` | dito (Panel-Pendant, dieselbe Normalisierung). |
| `labs-card.js:284-305` | `formatLabValue` → Politik §8.2; `referenceText(marker, displayUnit)` konvertiert Grenzen und nutzt `displayUnit` mit **demselben `d`** wie der Wert (F4/N1). |
| `labs-card.js:787-812` | Zeile zeigt `anzeige = wert / faktor` + `default_unit`. |
| `panel-views.js:934-951` (`labMarkerRow`) | dito; Chart bekommt konvertierte History + Grenzen, Achsen-/Tooltip-Einheitenlabel = `default_unit` (F15). `panel-base.js` erhält dafür `labDisplayValue(marker, unit)`, `labDisplayDecimals(value)` und `labFormatDisplayValue(value)`. |

## 10. Betroffene Dateien

| Datei | Änderung |
|---|---|
| `custom_components/health_o_mat/const.py` | `OPTION_LAB_DEFAULT_UNITS`, `LAB_DEFAULT_UNITS`, `LAB_UNITS` |
| `.../logic.py` | 5 neue Funktionen (§6); `normalize_lab_custom_markers` + `effective_lab_markers` erweitert |
| `.../ws_api.py` | `SETTINGS_KEYS`, `SETTINGS_SCHEMA`, `build_settings`, `parse_settings_message`, `_labs_block` |
| `.../backup.py` | `lab_options`-Sektion + Docstring (nur Sektion, **kein** Restore-Pfad — F14) |
| `.../restore.py` | **keine Änderung** (F14: `lab_default_units` wird wie `lab_ref_overrides` gesichert, nicht zurückgespielt) |
| `.../diagnostics.py` | `OPTION_LAB_DEFAULT_UNITS` in `_LAB_OPTION_KEYS` (`diagnostics.py:97-105`) → count-only (F1) |
| `.../www/health-o-mat-panel-admin.js` | Anzeige-Select in `refRows` **und** `customRows` (`:339-450`, F5), `conversionText` um Legacy `alt_unit` erweitern (F6), Custom-Einheiten-Selects + `__custom__`-Prefill (F3), N Zusatzzeilen |
| `.../www/health-o-mat-panel-views.js` | `unitOptions`, Einzel-Formular, Berichtszeilen (leere Zeile `!row.marker && !row.value`, `:1238`, F2; Wiederverwendung setzt Marker **und** `default_unit`, `:1239`, N2), Leer-Einheit-Block (F10), Anzeige-Konvertierung |
| `.../www/health-o-mat-panel-base.js` | `labDisplayValue`, `labDisplayDecimals`, `labFormatDisplayValue`, `labReportedSubline` (normalisiert, F8), Chart-Einheitenlabel `default_unit` (F15) |
| `.../www/health-o-mat-panel.js` | `lab-custom-add` (alt_units), `lab-custom-alt-add/remove`, Settings-Collect/Changed |
| `.../www/health-o-mat-labs-card.js` | `_unitOptions`, `_entryForm`, `_markerRow`, `referenceText` (gemeinsames `d`, F4/N1), Subline (normalisiert, F8), Leer-Einheit-Block (F10), leere Zeile `!row.marker && !row.value` (`:1137`, F2), Zeilen-Wiederverwendung Marker **+** `default_unit` (`:1139`, N2), `CARD_TEXT` |
| `.../strings.json` + `translations/de.json` + `translations/en.json` | neue Keys (§11) |
| `manifest.json` + alle `?v=`-Specifier + `CARD_VERSION`/`PANEL_VERSION` | Versions-Bump 0.22.0 (Cache-Buster, von `tests/test_panel_js.py` erzwungen) |
| `tests/test_logic.py`, `test_ws_api.py`, `test_import_backup.py`, `test_restore.py`, `test_panel_js.py`, `test_card_js.py`, `test_translations.py`, `test_areas_wiring.py`, `test_diagnostics.py` | §12 (F1, F2, F3, F4, F6–F11, F14) |
| `tests_e2e/test_lab_values_e2e.py`, `tests_e2e/test_diagnostics_e2e.py` | §12.3/§12.4 |
| `docs/REQUIREMENTS.md` | neuer REQ-Vorschlag **REQ-HOM-134** (nächste freie Nummer) |
| `README.md:734` | Doku-Nachzug (nicht Teil dieses Changesets): `alt_unit` → `alt_units` in der Restore-Zeile (F13) |

## 11. i18n-Keys

`common` in `strings.json` (englischer Master) + `translations/{de,en}.json`; die Karte
führt ihre Mini-Kopie `CARD_TEXT` (`labs-card.js:95-107`) für Keys, die sie selbst rendert.

| Key | de | en |
|---|---|---|
| `ui_admin_lab_default_unit` | `Anzeige-Einheit` | `Display unit` |
| `ui_admin_lab_default_unit_standard` | `Standard ({unit})` | `Default ({unit})` |
| `ui_admin_lab_unit_other` | `Andere …` | `Other …` |
| `ui_admin_lab_custom_unit_add` | `Weitere Einheit hinzufügen` | `Add another unit` |
| `ui_admin_lab_custom_unit_remove` | `Einheit entfernen` | `Remove unit` |
| `ui_panel_lab_unit_label` | `Einheit` | `Unit` |

Wiederverwendet (keine Neuanlage): `ui_panel_lab_unit_custom` („Andere …", bereits
vorhanden, wird auch in `CARD_TEXT` aufgenommen), `ui_panel_lab_unit_required` („Einheit
erforderlich", bereits vorhanden — Fehlermeldung für den F10-Block),
`ui_admin_lab_custom_alt_unit` / `..._alt_factor` (Beschriftung der Zusatzzeilen),
`ui_admin_lab_unit` (Tabellenkopf).

## 12. Test-Obligationen

### 12.1 Unit (HA-frei)

| Testdatei | Fälle |
|---|---|
| `tests/test_logic.py` | `LAB_DEFAULT_UNITS`: jeder Wert ist `canonical_unit` oder `alt_units`-Key; jeder Key existiert in `LAB_MARKERS`; **`LAB_DEFAULT_UNITS["urea"] == "mmol/L"`** (F12, kanonisch — nicht `mg/dL`). `LAB_UNITS` ≡ Katalog-Schreibweisen (Vergleich über `_norm_unit`). `lab_allowed_units` (kanonisch zuerst, Dedupe, Custom). `resolve_lab_display_unit`: Override > Factory > kanonisch; falsche Schreibweise → Katalogschreibweise; Defensive → kanonisch. `normalize_lab_default_units`: Alias-Key, unbekannter Marker → weg, ungültige Unit → kanonisch, Nicht-Objekt → `{}`, Idempotenz. `convert_lab_display_value`: alle Defaults + Custom + unbekannte Unit; Round-Trip `convert_lab_value` → `convert_lab_display_value` ≈ Eingabe (±1e-6). `lab_display_decimals`: `base_d`-Grenzen 1/10/100 **und** Cap `d = min(base_d + 1, 3)` (Werte 0.09/0.9/1/9.9/10/99/100/999). Custom-Marker: Legacy `alt_unit` → Map, neue Map, beide gleichzeitig, ungültiger Faktor, Kanonisch-Duplikat, Idempotenz, `effective_lab_markers` liefert die Map. |
| `tests/test_ws_api.py` | `build_settings` enthält `lab_default_units` (normalisiert), `lab_default_units_factory`, `lab_allowed_units` (Katalog **und** Custom, Kanonisch zuerst) und `lab_units` (F11). `parse_settings_message`: Akzeptanz/Normalisierung; Marker + Defaults im **selben** Payload gegen den neuen Marker-Satz; falscher Typ → `invalid_setting("lab_default_units")`; `SETTINGS_KEYS` enthält den Key; `set → get`-Round-Trip. **F7-Pop:** Payload `{"lab_default_units": {"creatinine": "MG/DL"}}` → gespeichert/antwortet `mg/dL` (Katalogschreibweise), d. h. der normalisierte Wert überlebt `SETTINGS_SCHEMA(raw)`. `_labs_block`: `default_unit` + `allowed_units` für Katalog/Custom, kanonisch zuerst. |
| `tests/test_import_backup.py` | `async_backup` schreibt `lab_default_units` je Entry (bestehender Exact-Dict-Test `:1087` wird um den Key erweitert); Alt-Backup ohne Key bleibt lesbar. |
| `tests/test_restore.py` | **F14:** ein Backup mit `lab_default_units` ändert die Ziel-Options **nicht** (Restore ignoriert den Key wie `lab_ref_overrides`/`lab_hidden_categories`); kein `async_update_entry` durch diesen Key, kein Listener-Feuer. Kein Merge-/Apply-Test mehr in v1. |
| `tests/test_areas_wiring.py` | Änderung von `lab_default_units` löst **keinen** Entry-Reload aus (Snapshot unverändert). |
| `tests/test_diagnostics.py` | **F1:** `redact_diagnostics` mit gesetztem `lab_default_units` (inkl. Custom-Slug) → Output ist `{"count": n}`; der Slug/Marker-Key erscheint **nirgends** im serialisierten Ergebnis (`json.dumps`). `OPTION_LAB_DEFAULT_UNITS in _LAB_OPTION_KEYS`. Muster: bestehender Test `test_diagnostics.py:421-431`. |
| `tests/test_translations.py` | Neue Keys in `_REQ_HOM_122_UI_KEYS`; Key-Baum-Parität (`strings.json` ↔ `de`/`en`, automatisch); Platzhalter-Parität für `{unit}`. |

### 12.2 JS-Quell-/Runner-Tests

| Testdatei | Fälle |
|---|---|
| `tests/test_panel_js.py` | Admin: Anzeige-Select **an beiden Orten** — Katalogzeile in `refRows` **und** gespeicherter Custom-Marker in `customRows` (F5), Optionen aus `lab_allowed_units` + „Standard (…)"; Sammeln erzeugt `lab_default_units`; Custom-Formular: Select + „Andere …" + Add/Remove; **F3:** Custom-Marker mit `unit: "nmol/L"` (nicht in `LAB_UNITS`) → `__custom__` vorausgewählt und Freitext mit `nmol/L` vorbefüllt; **F6:** `customRows` rendert die Umrechnungsspalte (REQ-HOM-124) für `alt_units` **und** Legacy `alt_unit` (bestehende REQ-HOM-124-Runner `:4096` erweitern, nicht duplizieren); Einzel-Formular: Select preselektiert `default_unit`, verstecktes Freitextfeld; Berichtszeile: `default_unit` vorausgewählt; Source-Assertions für `labDisplayValue`; **N2:** Source-Assertion in `panel-views.js:1239`, dass die Zeilen-Wiederverwendung **beides** setzt (`empty.marker = key` **und** `empty.unit = markers[key].default_unit`). Bestehende REQ-HOM-133-Tests bleiben gültig (hba1c hat keinen Werksdefault → kanonisch bleibt vorausgewählt). |
| `tests/test_card_js.py` | Node-Runner: `_unitOptions(marker, "")` wählt `default_unit` (z. B. Kreatinin → `mg/dL selected`); `_entryForm` rendert Select + Freitext; `_markerRow` zeigt konvertierten Wert + Anzeige-Einheit; `referenceText` konvertiert Grenzen; Subline entfällt bei **normalisiert** gleicher `reported_unit` (F8: `"µmol/L"` vs. Anzeige `"µmol/L"`/`"umol/L"` → keine Subzeile, `"mg/dL"` → Subzeile); **F2:** Source-Assertion `!row.marker && !row.value` in `labs-card.js` (leere Zeile, `:1137`); **N2:** Zeilen-Wiederverwendung setzt Marker **und** `default_unit` — funktionaler Runner: leere Zeile mit Marker A (Default `mg/dL`) füllen mit Marker B (Default `µmol/L`) → die wiederverwendete Zeile trägt `µmol/L`, **nicht** die geerbte `mg/dL` (zusätzlich Source-Assertion zu `labs-card.js:1139`); **F10:** `__custom__` + leerer Freitext → Submit blockiert + Fehlertext; **F4/N1:** die acht Grenzfall-Paare aus §8.2 — Kreatinin `1,2`/`1,199` (high) und `1,199`/`1,199` (normal); Cholesterin `201,2`/`200,8` und `200,8`/`200,8`; Bilirubin `1,234`/`1,228` und `1,228`/`1,228`; fT4 `1,795`/`1,787` und `1,787`/`1,787` — jeweils Wert **und** Grenze aus demselben `d`, Badge kanonisch. `CARD_TEXT`-Parität für die neuen Keys (bestehender Wortlaut-Test `:2978` als Muster). |
| `tests/test_panel_js.py` (F2, N2) | Source-Assertion: `!row.marker && !row.value` in `panel-views.js:1238` (kein `!row.unit` mehr in der Leer-Erkennung); Source-Assertion für die Wiederverwendung in `panel-views.js:1239` (`empty.marker = key` **und** `empty.unit = markers[key].default_unit`). |
| Oracle-Parität (F9) | Node-Runner-Vergleich `labDisplayDecimals`/Anzeigewert (Panel **und** Karte) gegen `logic.lab_display_decimals`/`convert_lab_display_value` über eine feste Wertetabelle (mind. die Beispiele aus §8.2 **und** die acht Grenzfall-Paare). Zusätzlich: Wert, Grenze und Chart-Band werden **innerhalb einer Oberfläche** aus demselben `d` abgeleitet (keine zweite Dezimalberechnung, kein `d+1`). |

### 12.3 E2E (`tests_e2e/test_lab_values_e2e.py`)

1. `set_settings` mit `lab_default_units: {"creatinine": "mg/dL"}` → Panel-Zeile zeigt
   `mg/dL`, das Einheiten-Select des Formulars ist vorausgewählt.
2. Wert `0.9` in `mg/dL` erfassen → **Sensor-State bleibt kanonisch** (≈ `79.6`,
   `native_unit_of_measurement == "µmol/L"`), Panel/Karte zeigen `0,9 mg/dL`.
3. CSV-Export desselben Eintrags enthält den kanonischen Wert und `µmol/L`.
4. `in_range`-Badge unverändert (kanonisch berechnet); der Test stellt die
   Personen-Optionen am Ende wieder her (bestehendes Snapshot-Muster).
5. **F4/N1:** Wert `106.1` µmol/L (Kreatinin, knapp über `ref_max`) → Panel/Karte zeigen
   `1,2 mg/dL`, die Referenzgrenze `1,199 mg/dL` (gleiches `d`), und der Badge bleibt `high`;
   `in_range` im WS-Payload ist unverändert `false`. Der in-range-Zwilling `106.0` →
   `1,199`/`1,199` mit Badge `normal` ist in §12.2 abgedeckt (kein Widerspruch zwischen
   Anzeige und Grenze).
6. **F10:** Einzel-Erfassung mit „Andere …" + leerem Freitext → sichtbarer Fehler, kein
   neuer Laborwert im Store (kein `add_lab_value`-Roundtrip).

### 12.4 Diagnostics (`tests_e2e/test_diagnostics_e2e.py`, F1)

1. `lab_default_units` mit Katalog-Marker und Custom-Slug setzen → Diagnostics-Download
   über die bestehende E2E-Hilfe; `options.lab_default_units == {"count": n}` und der
   Custom-Slug ist im serialisierten Payload nicht enthalten.
2. Alt-Entry **ohne** den Key → Diagnostics liefert `{"count": 0}` (kein Fehler).

## 13. Risiken & Gegenmaßnahmen

| Risiko | Wirkung | Gegenmaßnahme |
|---|---|---|
| Wert in Anzeige-Einheit eingegeben, Einheit **nicht** gesendet | Faktor-Fehler im Store (z. B. 0.9 statt 79.6) | Select ist immer vorbelegt und wird **immer** mitgesendet; E2E prüft den kanonischen Sensor-State. Ein leerer „Andere …"-Freitext **blockiert den Submit** mit sichtbarem Fehler (F10, §9.3/§9.4) — keine leere Einheit mehr auf dem Draht |
| Schreibweisen-Drift (µ/μ/u, Groß-/Kleinschreibung) | Konvertierung wird übersprungen, Wert bleibt scheinbar kanonisch | Normalisierung speichert Katalogschreibweise; `_norm_unit` bei Auflösung; UI bekommt `allowed_units` aus derselben Quelle |
| Zwei JS-Kopien driften (Panel vs. Karte) | Unterschiedliche Anzeige je Oberfläche | Python-Oracle + Node-Paritätstest (§12.2) |
| Werksdefault wird durch Katalogänderung ungültig | Anzeige bricht | `resolve_lab_display_unit` validiert jeden Aufruf; ungültig → kanonisch |
| Invalid gesendete Default-Einheit pinnt kanonisch | Werksdefault greift nicht mehr | Bewusste D4-Auslegung (nie Fehler, deterministisch); Admin-Select zeigt „Standard" zum Zurücksetzen |
| Restore spielt `lab_default_units` **nicht** zurück (v1) | Nach einem Restore gilt weiterhin die lokale Option/Werkseinstellung — kein „Restore bringt meine Anzeige zurück" | Bewusst (F14, §7.3): wie `lab_ref_overrides`/`lab_hidden_categories`; Follow-up-Issue §15 O-4 |
| Wert und Grenze verschieden gerundet (frühere `d+1`-Regel: Wert `1,2` gegen Grenze `1,199`, Badge aber „high") | Anzeige wirkt widersprüchlich; in-range-Werte konnten über ihrer eigenen Grenze erscheinen | **Ein** gemeinsames `d = min(base_d + 1, 3)` für Wert, Grenzen und Band (F4/N1, §8.2 N4); `in_range` bleibt kanonisch; acht Grenzfall-Paare §12.2 |
| Zeilen-Wiederverwendung erbt die Default-Einheit des vorherigen Markers (nur `empty.marker` gesetzt) | Wert wird still in einer Fremdeinheit konvertiert (falsche Zahl) | **N2:** `empty.unit = markers[key].default_unit` zusätzlich setzen — in **beiden** Pfaden (`panel-views.js:1239`, `labs-card.js:1139`, §9.4), mit Source- und Funktions-Test (§12.2) |
| `!row.unit` als „leere Zeile"-Kriterium | Fill-Buttons legen keine Zeilen mehr an | Bedingung in **beiden** Dateien auf `!row.marker && !row.value` ändern (`panel-views.js:1238`, `labs-card.js:1137`, §9.4) |

## 14. Kompatibilität & Release

| Aspekt | Aussage |
|---|---|
| Entity-Identität | unverändert (`{entry_id}_lab_{key}`, `object_id`-Pinning); Sensor-State/-Einheit kanonisch, Langzeitstatistik unberührt |
| Store | kein Schema-Bump, keine Migration |
| Backup / Optionen | additiver Key; alte Backups restorebar, neue in alten Versionen ignorierbar; alte Clients senden den Key nicht → Werksdefaults gelten automatisch. **Restore wendet den Key in v1 nicht an** (F14, §7.3) — Backup enthält ihn, `plan_restore`/`apply_restore` ignorieren ihn |
| Werksdefault `urea` | `mmol/L` (kanonisch) statt `mg/dL`, weil der Katalogfaktor 0.357 die BUN-Skala abbildet (F12, §5.1); Faktor unverändert |
| Custom-Marker-Shape | Legacy `alt_unit` bleibt dauerhaft lesbar; Schreibweise wechselt zu `alt_units` |
| **Release** | **MINOR 0.22.0**, kein 💥, kein Migrations-Handler. Tag `v0.22.0` ↔ `manifest.version`; Release-Notes: „Neue Anzeige-Einheiten (Werkseinstellungen, pro Person übersteuerbar), Einheiten-Dropdowns, mehrere Alt-Einheiten für eigene Marker". |
| REQ-Vorschlag | **REQ-HOM-134** — Anzeige-Einheiten für Laborwerte (Werkseinstellungen + Personen-Override) |

## 15. Offene Punkte

| # | Punkt | Empfehlung |
|---|---|---|
| O-1 | Werksdefaults sind fachlich „typische Alltagseinheiten", keine klinische Norm. `urea` erbt den Katalogfaktor 0.357, der auf der **BUN-Skala** beruht (Harnstoff-Skala ≈ 0.1665). | Faktoren unverändert übernehmen (keine neue Medizinlogik in dieser Spec); `urea` bleibt deshalb auf `mmol/L` (F12, §5.1). Katalogkorrektur = eigenes Issue. |
| O-2 | `get_settings` liefert die Werksdefaults als eigenen Read-only-Key (`lab_default_units_factory`) statt sie in `lab_catalog` einzubetten. | Beibehalten: `lab_catalog` bleibt die unveränderte `const.py`-Projektion; ein zweiter Key ist expliziter und testbar. |
| O-3 | Anzeige-Einheit für einen neu angelegten Custom-Marker erst nach dem ersten Speichern wählbar (kein `key` vorher). | Akzeptieren; ein clientseitiges Slugging würde die serverseitige Key-Hoheit (`logic.py:1072`) brechen. |
| O-4 | **Follow-up-Issue (F14):** Restore/Apply für `lab_default_units` fehlt in v1 — der Key wird gesichert, aber nicht zurückgespielt (wie `lab_ref_overrides`, `lab_hidden_categories`, `lab_hide_panel_disclaimer`). | Eigenes Issue nach 0.22.0: `plan_restore`-Parameter + `RestorePlan`-Feld, Merge mit lokalem Vorrang, Validierung gegen die gemergten Custom-Marker, eigene Apply-Funktion (No-op-Guard) — Details im verworfenen Entwurf dieser Spec (Review-Runde 1, F14). |

## 16. Änderungsprotokoll Review-Runde 1

Verdikt war **APPROVE_WITH_CHANGES**; D1–D4 bleiben unverändert gesetzt. Alle Findings
sind eingearbeitet, keines zurückgestellt.

| # | Prio | Finding | Status | Ort im Dokument |
|---|---|---|---|---|
| F1 | P1 | Diagnostics-Leak durch verbatim `lab_default_units` | eingearbeitet | §5.2, §10, §12.4 |
| F2 | P1 | Leere-Zeile-Erkennung nur für `panel-views.js` adressiert | eingearbeitet | §9.4, §10, §12.2 |
| F3 | P1 | Custom-Einheit nicht in `LAB_UNITS` → Select verliert Wert | eingearbeitet | §9.2 (+ Test §12.2) |
| F4 | P1 | Anzeige-Grenze kollidiert mit gerundetem Wert/Badge | eingearbeitet · in Runde 2 durch F4/N1 ersetzt (gemeinsames `d`) | §8.1, §8.2 (N4–N6), §12.2, §13 |
| F5 | P2 | „Anzeige"-Spalte nur unspezifisch verortet | eingearbeitet | §9.1 |
| F6 | P2 | `customRows`/`altUnitText` bricht REQ-HOM-124 nach Shape-Wechsel | eingearbeitet | §9.2, §12.2 |
| F7 | P2 | `SETTINGS_SCHEMA`-Lauf überschreibt normalisierte Map | eingearbeitet | §7.2 |
| F8 | P2 | `reported_unit` roh gespeichert → `===` falsch | eingearbeitet | §8.1, §9.5 |
| F9 | P2 | Dezimalquelle doppeldeutig (`d` vs. Grenzen/Band) | eingearbeitet | §8.2 (N4) |
| F10 | P2 | „Einheit immer explizit" nur serverseitig | eingearbeitet | §8.1, §9.3, §9.4, §11, §13 |
| F11 | P2 | JS müsste `lab_allowed_units` nachbilden | eingearbeitet | §7.2, §9.1 |
| F12 | P2 | `urea`-Default auf BUN-Faktor | eingearbeitet | §5.1, §14, §15 (O-1) |
| F13 | P3 | Formulierungs-/Anker-Korrekturen (`build_settings` schreibt nicht; `README.md:734`; `restore.py:615`; `panel-views.js:1560`) | eingearbeitet | §1, §2, §5.4, §7.2, §10 |
| F14 | P3 | YAGNI: Restore-Pfad für `lab_default_units` | eingearbeitet (entfernt) | §7.3, §10, §12.1, §13, §14, §15 (O-4) |
| F15 | P3 | Chart-Einheitenlabel | eingearbeitet | §8.1, §9.5 |

**Konsistenz-Nachprüfung nach der Einarbeitung:** `urea` steht in allen Abschnitten auf
`mmol/L` (§5.1, §14, §15 O-1); kein Restore-Pfad mehr (§1, §7.3, §10, §12.1, §13, §14,
§15 O-4); `d` nur noch aus dem konvertierten Anzeigewert (§8.1, §8.2 N4); die
Leere-Zeile-Regel nennt beide Dateien (§9.4, §10, §13). D1–D4 sind unverändert.

## 17. Änderungsprotokoll Review-Runde 2 (Delta)

Delta-Verdikt war **APPROVE_WITH_CHANGES**; nur F4 bleibt P1-Klasse, N1 hat dieselbe Wurzel,
N2 ist minor. D1–D4 bleiben unverändert, alle drei Punkte sind eingearbeitet.

| # | Prio | Finding | Status | Ort im Dokument |
|---|---|---|---|---|
| F4/N1 | P1 | Grenzen nutzten `min(d(value)+1, 3)`, der Wert `d` — einseitige Regel mit Umkehr-Fall (in-range-Wert konnte über seiner angezeigten Grenze stehen); N4a/N4b-Split und die alte 106,0-Erklärung in §12.3 waren falsch bzw. überflüssig | eingearbeitet: **ein** gemeinsames `d = min(base_d + 1, 3)` für Wert, Grenzen und Chart-Band/Achse; Monotonie-Begründung + akzeptierter Trade-off (eine Nachkommastelle Rauschen); N4a/N4b-Split und `d+1`-Formulierung entfernt; acht Grenzfall-Paare (in/out je Marker) in §8.2/§12.2 | §8.1, §8.2 (N2–N6, Beispiele, Grenzfälle), §9.5, §10, §12.2, §12.3, §13 |
| N2 | P2 | Zeilen-Wiederverwendung in beiden Fill-Pfaden setzte nur `empty.marker = key` — die Zeile erbte die Default-Einheit des vorherigen Markers | eingearbeitet: **beides** setzen (`empty.marker = key` **und** `empty.unit = markers[key].default_unit`) in `panel-views.js:1239` und `labs-card.js:1139`; Source- und Funktions-Test in §12.2 | §9.4, §10, §12.2, §13 |
| — | P3 | Statuszeile + Änderungsprotokoll nachziehen | eingearbeitet: Status „Review-Runde 2 eingearbeitet — abnahmereif", dieser Abschnitt | Kopfzeile, §17 |

**Konsistenz-Nachprüfung nach Runde 2:** Wert, Grenzen und Chart-Band nennen überall dasselbe
`d` (§8.1, §8.2 N4, §9.5, §12.2, §13); keine `d+1`-Formulierung, kein N4a/N4b-Split; acht
in/out-Grenzfälle; beide Wiederverwendungspfade setzen Marker **und** `default_unit`. D1–D4 unverändert.

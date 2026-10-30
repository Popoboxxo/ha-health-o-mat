# Konzept: Laborwerte (Blutwerte) — HA Health-O-Mat

**Status:** Entwurf (2026-10-30) · **Verwandt:** `docs/IDEATION-VISION.md` §5.1,
`docs/REQUIREMENTS.md`, `docs/CONCEPT-UI.md`

> Erfassung von Laborwerten (Blutwerte) als vierte Datendomäne neben
> Trinken/Blutdruck/Wohlbefinden. Entstanden aus Brainstorming mit dem
> Maintainer (2026-10-30). Dieses Dokument ist die Design-Spec vor dem
> Implementierungsplan — verbindliche Anforderungen entstehen erst als
> REQ-HOM-xxx in `docs/REQUIREMENTS.md`.

---

## 1. Ausgangslage & Ziel

Health-O-Mat deckt heute Trinken, Blutdruck und Wohlbefinden ab. Laborwerte
(aus Arztbesuchen/Laborberichten) sind der nächste Baustein der
Vision (§5.1 „Erfassen — breiter und reibungsloser"). Anders als die
bestehenden Datentypen sind Laborwerte **kategorisiert** (Leber, Niere, ...),
**erweiterbar** (Nutzer wollen eigene Marker anlegen) und **einheitenkritisch**
(ein Wert kann in mg/dL oder mmol/L vorliegen, je nach Labor/Land).

**Nicht-funktionale Leitplanke (Vision §4.2 „Keine medizinische Beratung"):**
Die Integration **klassifiziert nicht medizinisch** und **diagnostiziert
nicht** — sie zeigt nur an, ob ein Wert außerhalb des (vom Nutzer
kontrollierten) Referenzbereichs liegt. Jede Default-Referenz ist ein
**typischer Erwachsenen-Richtwert**, keine klinische Norm — Referenzbereiche
unterscheiden sich real nach Labor, Methode, Alter und Geschlecht (siehe
Recherche Kapitel 3). Das Feature **muss** diesen Vorbehalt in UI/Doku
sichtbar machen (Disclaimer in Card/Panel, README).

**Datenschutz (bestehende Regel, gilt unverändert):** Laborwerte sind
Gesundheitsdaten — genau wie Blutdruck/Wohlbefinden heute. `diagnostics.py`
bleibt strikt redigiert (keine Werte, nur Zähler/Konfiguration). Export nie
nach `/config/www`.

---

## 2. Datenmodell

### 2.1 Kategorien & Katalog-Marker

Neun Default-Kategorien (`const.py: LAB_CATEGORIES`), aus der Recherche
(Kapitel 3) destilliert — Kategorie 9 kam aus dem Abgleich mit realen
Laborbefunden des Maintainers (2026-10-30) hinzu:

| Kategorie-Key | Name (de) | Marker (Katalog) |
|---|---|---|
| `liver` | Leber | `alt`, `ast`, `ggt`, `bilirubin_total`, `total_protein` |
| `kidney` | Niere | `creatinine`, `egfr`, `urea`, `urine_protein_creatinine_ratio` |
| `electrolytes` | Elektrolyte | `sodium`, `potassium`, `calcium`, `magnesium`, `chloride` |
| `lipids` | Lipide | `cholesterol_total`, `ldl`, `hdl`, `triglycerides` |
| `thyroid` | Schilddrüse | `tsh`, `ft4`, `ft3` |
| `blood_count` | Blutbild | `hemoglobin`, `leukocytes`, `platelets` |
| `inflammation` | Entzündung/Immunsystem | `crp`, `esr` |
| `digestion` | Verdauung | `lipase`, `amylase` |
| `drug_levels` | Medikamentenspiegel | `tacrolimus` |

**Abgrenzung `drug_levels` vs. Vision §5.1 „Medikamente/Supplements":** Diese
Kategorie bildet **Blutspiegel** eines Medikaments ab (Therapeutic Drug
Monitoring, z. B. Tacrolimus nach Organtransplantation) — ein Laborwert wie
jeder andere. Das separate Vision-Themenfeld „Medikamente/Supplements"
(Einnahme-Tracking: Dosis, Einnahmezeit, Adhärenz) ist ein **anderes**,
zukünftiges Feature und bleibt unberührt — beide können später unabhängig
voneinander existieren, ohne sich zu überlappen.

Jeder Katalog-Marker (`const.py: LAB_MARKERS[key]`) trägt:

```python
{
    "category": "liver",
    "name_de": "ALT (GPT)", "name_en": "ALT (ALT/GPT)",
    "canonical_unit": "U/L",
    "ref_min": 10, "ref_max": 50,          # None erlaubt (nur eine Grenze)
    "alt_units": {},                        # {"unit": factor_to_canonical} falls nötig
}
```

### 2.1a Namens-Aliase (deutsche Laborsynonyme)

Deutsche Laborbefunde nutzen teils andere Bezeichnungen für denselben Wert:
**GPT = ALT**, **GOT = AST**, **Gamma-GT = GGT**. Das ist ein **Namens**-,
kein Einheiten-Problem — `const.py: LAB_MARKER_ALIASES` ist eine kleine
feste Lookup-Tabelle (`{"gpt": "alt", "got": "ast", "gamma_gt": "ggt"}`),
die der Service (`add_lab_value`, §5.1) **vor** dem Katalog-/Custom-Abgleich
auflöst — ein Laborgerät/-skript, das „GPT" statt „ALT" sendet, bekommt
keinen `unknown_marker`-Fehler mehr. Anzeige in UI/Doku bleibt wie bisher
unter dem primären Namen mit Synonym in Klammern (z. B. „ALT (GPT)").
Gespeichert wird immer unter dem **primären** `marker_key` (`alt`, nicht
`gpt`) — kein Doppel-Eintrag, kein zweiter Marker.

### 2.2 Custom-Marker (pro Person)

`entry.options["lab_custom_markers"]: list[dict]`:

```python
{"key": "vitamin_d", "name": "Vitamin D", "category": "other",
 "unit": "ng/mL", "ref_min": 30, "ref_max": 100}
```

- `key` wird beim Anlegen aus `name` generiert (slugify) und gegen
  Katalog-Keys **und** bereits vorhandene Custom-Keys der Person geprüft
  (Kollision → Suffix `_2`, `_3`, ... oder Fehlermeldung im Admin-Formular).
- Kategorie `other` ("Sonstige") ist immer wählbar zusätzlich zu den 8
  Default-Kategorien — freie Marker ohne Themenbezug landen dort.
- **Optionales Alt-Unit-Paar** (`alt_unit: {"unit": ..., "factor_to_canonical":
  ...} | None`): deckt den üblichen Fall „zwei Labore berichten in zwei
  Einheiten" ab, ohne ein offenes Mehrfach-Einheiten-Framework zu bauen —
  bewusst **genau ein** Paar pro Custom-Marker, kein Katalog-Umfang
  (begrenzt, YAGNI). Service/Card/Admin akzeptieren dann sowohl `unit`
  als auch `alt_unit.unit` für diesen Marker, rechnen beim Schreiben in
  die Haupt-`unit` um (gleicher `convert_lab_value`-Pfad wie Katalog-Marker,
  §3). Ohne gesetztes `alt_unit` bleibt der Marker einheitig wie bisher.

### 2.3 Referenzbereich-Overrides (pro Person, nur Katalog)

`entry.options["lab_ref_overrides"]: dict[marker_key, {"ref_min": ..., "ref_max": ...}]`

Auflösung beim Lesen (`logic.resolve_lab_reference(marker_key, options)`):
1. Override aus `lab_ref_overrides[marker_key]`, falls vorhanden.
2. Sonst Katalog-Default `LAB_MARKERS[marker_key]`.
3. Custom-Marker: immer ihre eigene Definition (kein Override-Layer nötig,
   sie *sind* schon personenspezifisch).

Nur geänderte Felder werden gespeichert (kein Override-Eintrag ohne
tatsächliche Abweichung) — Backup/Diagnostics bleiben schlank.

### 2.4 Store (Schema v5)

Neue Liste je Person-Entry, analog zu `readings[]`:

```python
entry["lab_readings"]: list[dict]
# {"id": "...", "marker_key": "alt", "value": 32.0, "unit": "U/L",
#  "ts": "...", "created_at": "...", "report_ref": None,
#  "voided_at": None, "voided_by": None, "void_reason": None}
```

**`report_ref` (optional, §2.4a):** freier String — eine URL (eigenes
Dokumentenablage-System, Cloud-Link zum Laborbericht) **oder** eine ID aus
einem externen System (z. B. Praxis-/LIMS-Fallnummer). Rein referenzierend:
**keine Dokumentinhalte, keine Dateien, kein Upload** — nur ein Verweis, den
der Nutzer selbst auflösen kann. Länge gecappt (z. B. 500 Zeichen) wie andere
Freitextfelder, keine Format-/Erreichbarkeitsprüfung (Health-O-Mat ruft die
URL nie selbst auf — kein SSRF-Risiko, kein Tracking-Call). Mehrere Marker
desselben Laborberichts teilen einfach denselben `report_ref`-Wert — es gibt
bewusst **keine eigene „LabReport"-Entität/Aggregat**, das wäre für den
Zweck „ein Tag, das Werte einem Dokument zuordnet" überdimensioniert (YAGNI).

`value`/`unit` sind **immer im `canonical_unit`** des Markers gespeichert —
Konvertierung passiert beim Schreiben (Service/Card/Admin liefern Rohwert +
Ursprungseinheit, `logic.convert_lab_value()` rechnet um, bevor der Store
geschrieben wird). Das Original (`value`, `unit` wie eingegeben) wird
**zusätzlich** als `reported_value`/`reported_unit` mitgespeichert — rein
informativ, für Nachvollziehbarkeit im Verlauf/CSV, keine zweite
Wahrheitsquelle.

Store-Funktionen (folgen 1:1 dem `readings[]`-Muster in `store.py`):
`add_lab_reading`, `active_lab_readings`, `last_active_lab_reading`,
`void_lab_reading`, `restore_lab_reading`, `remove_last_lab_reading`.

**Migration `_migrate_v4_to_v5`:** ergänzt `lab_readings: []` je Entry,
idempotent (prüft Existenz vor dem Setzen) wie alle bisherigen Migrationen.

### 2.5 Kategorie-Sichtbarkeit (pro Person)

`entry.options["lab_hidden_categories"]: list[str]` — Liste ausgeblendeter
Kategorie-Keys (z. B. `["thyroid"]`, wenn Schilddrüse für diese Person nie
relevant ist). Gilt **für jeden Betrachter** von Panel/Card dieser Person
(Admin-Setting, nicht Viewer-individuell — konsistent mit dem bestehenden
`areas`-Muster, nur eine Ebene feinkörniger: `areas.labs` schaltet die ganze
Domäne ab, `lab_hidden_categories` blendet einzelne Kategorien innerhalb der
Domäne aus). Ausblenden entfernt nur die Anzeige in Panel/Card/Tab-Navigation
— Entities, Store-Werte und Referenzbereiche bleiben unverändert; Reaktivieren
zeigt dieselben Daten wieder. Marker der ausgeblendeten Kategorie sind über
den Service weiterhin buchbar (z. B. Backdating eines alten Laborberichts
nach Reaktivierung) — nur die UI blendet aus, keine Schreibsperre.

---

## 3. Recherche: Referenzbereiche & Einheiten-Konvertierung

**Wichtiger Vorbehalt (siehe Kapitel 1):** Die folgenden Werte sind
**typische Erwachsenen-Richtwerte** aus mehreren frei zugänglichen
Quellen (Labor-Testkataloge, Klinikseiten, PMC-Tabellen) — sie **streuen
nach Quelle, Geschlecht, Alter und Messmethode** teils erheblich (z. B. ALT
10–50 U/L je nach Quelle, GGT geschlechtsabhängig fast Faktor 2). Genau
deshalb existiert der Per-Person-Override (§2.3) — die Integration liefert
einen vernünftigen Startwert, **nicht** die Wahrheit für jede Person.

| Marker | Default-Referenz | Kanon. Einheit | Alt.-Einheit + Faktor | Quelle (Kurzbeleg) |
|---|---|---|---|---|
| ALT (Syn. GPT) | 10–50 U/L | U/L | — | Klinische Studienprotokolle, Laborkataloge |
| AST (Syn. GOT) | 10–50 U/L | U/L | — | dto. |
| GGT (Syn. Gamma-GT) | 10–60 U/L | U/L | — | dto. (geschlechtsabhängig, Override empfohlen) |
| Bilirubin gesamt | 5–21 µmol/L | µmol/L | mg/dL × 17.1 → µmol/L | PMC-Tabellen, UK-Kidney-Appendix |
| Kreatinin | 53–106 µmol/L | µmol/L | mg/dL × 88.4 → µmol/L | Laborkataloge |
| eGFR | ≥ 90 mL/min/1.73m² | mL/min/1.73m² | — (keine Umrechnung) | KDIGO-Staging-Quellen |
| Harnstoff (Urea) | 2.5–7.5 mmol/L | mmol/L | mg/dL × 0.357 → mmol/L | HL7-Wiki CMP-Referenztabelle |
| Natrium | 135–145 mmol/L | mmol/L | — (bereits SI) | Laborkataloge |
| Kalium | 3.5–5.0 mmol/L | mmol/L | — | dto. |
| Calcium gesamt | 2.10–2.60 mmol/L | mmol/L | mg/dL × 0.25 → mmol/L | dto. |
| Magnesium | 0.70–1.00 mmol/L | mmol/L | mg/dL × 0.411 → mmol/L | dto. |
| Chlorid | 98–107 mmol/L | mmol/L | — | dto. |
| Gesamtcholesterin | ≤ 5.2 mmol/L | mmol/L | mg/dL × 0.0259 → mmol/L | ATP-III-Kategorien |
| LDL | ≤ 2.6 mmol/L (optimal) | mmol/L | mg/dL × 0.0259 → mmol/L | dto. |
| HDL | ≥ 1.0 mmol/L | mmol/L | mg/dL × 0.0259 → mmol/L | dto. (geschlechtsabhängig, Override empfohlen) |
| Triglyceride | ≤ 1.7 mmol/L | mmol/L | mg/dL × 0.0113 → mmol/L | dto. |
| TSH | 0.4–4.0 mIU/L | mIU/L | — (bereits SI) | Laborkataloge |
| fT4 | 10–23 pmol/L | pmol/L | ng/dL × 12.87 → pmol/L (Näherung) | Umrechnungstabellen Schilddrüse |
| fT3 | 3–8 pmol/L | pmol/L | pg/mL × 1.536 → pmol/L (Näherung) | dto. |
| Hämoglobin | 120–170 g/L | g/L | g/dL × 10 → g/L | NHS-Haematology-Referenztabelle |
| Leukozyten | 3.6–11.0 ×10⁹/L | ×10⁹/L | — | dto. |
| Thrombozyten | 140–400 ×10⁹/L | ×10⁹/L | — | dto. |
| CRP | ≤ 5 mg/L | mg/L | — | Laborkataloge (hs-CRP-Varianten abweichend) |
| BSG/ESR | ≤ 20 mm/h | mm/h | — (keine Umrechnung) | Haematology-Quellen |
| Lipase | 13–60 U/L | U/L | — | Laborkataloge |
| Amylase | 30–110 U/L | U/L | — | dto. |
| Gesamteiweiß | 64–83 g/L | g/L | — (bereits SI) | Klinische Chemie-Referenztabellen |
| Protein/Kreatinin-Quotient (Urin) | < 15 mg/g | mg/g | g/g × 1000 → mg/g | Nephrologie-Referenzwerte — **⚠ bekannte Verwechslungsgefahr:** reale Befunde beschriften den Wert oft als „g/g", meinen aber „mg/g" (Faktor 1000). Deshalb **kein** automatischer Default — Einheit muss bei jeder Eingabe explizit gewählt werden (§5.1). |
| Tacrolimus (Talspiegel) | 5–15 ng/mL (Richtwert, stark indikationsabhängig) | ng/mL | — | Transplantationsmedizin-Referenzwerte — Override hier **besonders** wichtig: der Zielbereich hängt von Zeit seit Transplantation und Organ ab, keine sinnvolle „Standard"-Zahl |

**Bidirektional, nie eine „richtige" Eingabe-Einheit:** Der Anwender trägt
die Einheit ein, die auf seinem Laborbericht steht — Haupt-Einheit **oder**
Alt-Einheit, beides ist gültige Eingabe. `convert_lab_value()` erkennt die
mitgeschickte `unit` und rechnet die jeweils andere automatisch korrekt aus;
gespeichert/als Sensor-Einheit angezeigt wird immer die kanonische Form, die
Original-Eingabe bleibt zusätzlich als `reported_value`/`reported_unit`
erhalten und erscheint als Subzeile in Card/Panel (§7). Niemand muss sich
merken, welche Einheit „die richtige" ist.

**Konvertierungstabelle** (`logic.py: LAB_UNIT_CONVERSIONS`) ist eine simple
Lookup-Struktur `{marker_key: {unit: factor_to_canonical}}` — nur für die
oben mit Faktor markierten Marker. Alles ohne Eintrag + abweichende `unit`
im Service/Card-Input → `ServiceValidationError("unsupported_unit")` statt
stillschweigend falsch zu rechnen.

---

## 4. Entities

- **`sensor.<person>_lab_<marker_key>`** — ein Sensor je Marker (Katalog
  **und** Custom, dynamisch aus `LAB_MARKERS` + `lab_custom_markers`
  aufgebaut). `state_class: measurement`, `native_unit_of_measurement` =
  canonical/eigene Einheit, `native_value` = letzter aktiver Wert (`unknown`
  ohne Meldung). Attribute: `ts`, `category`, `ref_min`, `ref_max`,
  `in_range` (`True`/`False`/`None`). `has_entity_name=True` +
  `translation_key` für Katalog-Marker (de/en in `strings.json`); Custom-Marker
  nutzen den vom Nutzer vergebenen `name` direkt (bewusst einsprachig).
  Neuer Custom-Marker → Options-Update → bestehender Reload-Pfad
  (`_options_updated` → `async_reload`) erzeugt die Entity, kein neuer
  Mechanismus.
- **`binary_sensor.<person>_lab_<category>_warning`** — ein Warn-Sensor je
  **Kategorie** (`device_class: problem`), an wenn ≥ 1 Marker der Kategorie
  einen aktiven Wert außerhalb `ref_min`/`ref_max` hat. Custom-Marker der
  Kategorie `other` bekommen **keinen** eigenen Warn-Sensor (zu heterogen);
  wer das braucht, nutzt eine eigene Automation auf die Sensor-Attribute.
- **Area-Schalter `areas.labs`** (Default aktiv, bestehende Semantik:
  fehlender Schlüssel = aktiv) — deaktiviert alle Lab-Entities einer Person,
  Store/Optionen bleiben unangetastet (Re-Aktivierung reproduziert dieselben
  Entities).

---

## 5. Services

### 5.1 `health_o_mat.add_lab_value`

| Feld | Typ | Pflicht | Hinweis |
|---|---|---|---|
| `person` | string | optional (leer = einzige Person) | wie bei allen bestehenden Services |
| `marker` | string | **ja** | stabiler Key (`alt`, `creatinine`, ...; Custom-Keys stehen im Admin-Panel). `selector: select` mit den Katalog-Keys als feste Optionen (übersetztes Label) für den UI-Automation-Editor; Freitext-Key bleibt gültig für Custom-Marker und externe Systeme. |
| `value` | float | **ja** | Rohwert in `unit` |
| `unit` | string | optional | Default = canonical/eigene Einheit des Markers |
| `ts` | datetime | optional | wie bestehend: ≤ 5 Min Zukunft, nicht vor 1900 |
| `report_ref` | string | optional | Link oder externe ID des Laborberichts (§2.4a), max. 500 Zeichen |

Auflösungsreihenfolge für `marker`: **(1)** `LAB_MARKER_ALIASES`-Lookup
(§2.1a, z. B. `gpt` → `alt`), **(2)** Katalog-Key, **(3)** Custom-Key der
Person. Kein Treffer in allen drei Schritten → `ServiceValidationError
("unknown_marker")` — **kein** automatisches Anlegen (verhindert
Tippfehler-Entity-Müll; Custom-Marker entstehen bewusst nur über das
Admin-Formular, §6.2).

**Marker ohne Einheiten-Default:** Für Marker mit bekannter
Verwechslungsgefahr zwischen zwei Einheiten (aktuell nur
`urine_protein_creatinine_ratio`, §3) ist `unit` **Pflichtfeld** — kein
impliziter Fallback auf `canonical_unit`. Fehlt `unit` bei einem solchen
Marker → `ServiceValidationError("unit_required")`. Das Flag
(`LAB_MARKERS[key]["require_explicit_unit"]: bool`) ist eine Katalog-
Eigenschaft, kein Sonderfall im Service-Code — jeder künftige Marker mit
derselben Gefahrenklasse (z. B. ein weiterer g/g-vs-mg/g-Quotient) setzt
einfach dasselbe Flag.

Extern erreichbar über HAs bestehende REST-API (`POST
/api/services/health_o_mat/add_lab_value`) + Long-Lived-Token — **kein**
neuer Webhook/HTTP-Endpunkt nötig, deckt den „Push vom Labor-Skript"-Use-Case
exakt wie `add_drink`/`add_blood_pressure` heute.

### 5.2 `health_o_mat.remove_last_lab_value`

Wie `remove_last_reading`, aber `marker` ist **Pflichtfeld** (da pro Person
viele Marker parallel offen sein können, anders als bei BD/Trinken).

---

## 6. UI-Erweiterung (Admin-Panel)

Neuer Abschnitt **„Laborwerte"** im bestehenden Admin-/Settings-Bereich
(`health-o-mat-panel-admin.js`), zwischen den bestehenden Personen-Settings
und dem Export-Block:

```
┌─ Admin: <Person> ──────────────────────────────────────────┐
│ ... (bestehende Settings: Ziel, Reset-Uhrzeit, Quick-Drinks,│
│      Lexikon, BD-Schwellen, Wellbeing-Bilder, Retention) ...│
│                                                              │
│ ▸ Laborwerte                                                │
│ ┌──────────────────────────────────────────────────────┐   │
│ │ Referenzbereiche anpassen                              │   │
│ │ Kategorie │ Marker │ Einheit │ Default │ Eigener Wert  │   │
│ │ Leber     │ ALT    │ U/L     │ 10–50   │ [___]–[___] ⟲│   │
│ │ Leber     │ AST    │ U/L     │ 10–50   │ [___]–[___] ⟲│   │
│ │ Niere     │ Kreat. │ µmol/L  │ 53–106  │ [___]–[___] ⟲│   │
│ │ ...                                    (scrollbar)     │   │
│ └──────────────────────────────────────────────────────┘   │
│                                                              │
│ ┌──────────────────────────────────────────────────────┐   │
│ │ Kategorien ausblenden                                  │   │
│ │ ☑ Leber        ☑ Niere         ☑ Elektrolyte           │   │
│ │ ☑ Lipide       ☐ Schilddrüse   ☑ Blutbild              │   │
│ │ ☑ Entzündung   ☑ Verdauung     ☑ Sonstige (Custom)      │   │
│ │ (abgewählt = in Panel-Tab/Card für diese Person         │   │
│ │  unsichtbar; Werte/Entities bleiben erhalten)           │   │
│ └──────────────────────────────────────────────────────┘   │
│                                                              │
│ ┌──────────────────────────────────────────────────────┐   │
│ │ Eigene Marker                                          │   │
│ │ Name:      [Vitamin D                              ]  │   │
│ │ Einheit:   [ng/mL                                  ]  │   │
│ │ Kategorie: [Sonstige                             ▾ ]  │   │
│ │ Referenz:  [30     ] bis [100                      ]  │   │
│ │ ▸ Alternative Einheit (optional)                        │   │
│ │   Einheit: [nmol/L  ]  Faktor → ng/mL: [ 0.4        ]  │   │
│ │                                   [ + Hinzufügen    ]  │   │
│ │ ──────────────────────────────────────────────────    │   │
│ │ • Vitamin D (vitamin_d) — ng/mL (alt: nmol/L)    [✕]  │   │
│ └──────────────────────────────────────────────────────┘   │
│                                                              │
│ ┌──────────────────────────────────────────────────────┐   │
│ │ Fehlt eine Kategorie oder ein Marker?                   │   │
│ │           [ Vorschlag / Feedback auf GitHub → ]         │   │
│ └──────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────┘
```

- „⟲" setzt das Feld auf den Katalog-Default zurück (löscht den Override-
  Eintrag statt ihn auf den Default-Wert zu setzen — hält `lab_ref_overrides`
  schlank, §2.3).
- „+ Hinzufügen" validiert client- **und** serverseitig (WS-Handler
  `health_o_mat/set_settings`, erweitert um `lab_custom_markers`/
  `lab_ref_overrides`/`lab_hidden_categories`, gleiches Muster wie
  `wellbeing_images` heute).
- Checkbox-Raster „Kategorien ausblenden" schreibt direkt
  `lab_hidden_categories` — kein Submit-Button nötig, Checkbox-Toggle löst
  wie andere Settings-Felder sofort `set_settings` aus (Debounce wie
  bestehend).
- Feedback-Button: `<a>`-Link, URL-encodiert vorausgefüllt
  (`.../issues/new?title=Lab-Kategorie%2FMarker-Vorschlag&body=...`), öffnet
  in neuem Tab — keine eigene Feedback-Speicherung/Backend.

---

### 7.1 Lovelace-Card (`health-o-mat-labs-card`)

Eigene, neue Custom-Card (nicht die bestehende `health-o-mat-card` erweitert
— die hat schon 9 `show_*`-Flags, ein zehntes Themenfeld würde den Editor
überladen). Folgt denselben Grundmustern wie die bestehende Card
(`person_mode`/`person_filter`/`default_person`, `?v=`-Cache-Buster,
HA-CSS-Variablen statt eigener Farben, kein externes Chart-Framework).

```
┌─ Laborwerte — Person ──────────────────────────── ⚠ 2 ──┐
│ ⚠ Hinweis: keine medizinische Beratung — Richtwerte,     │
│   keine Diagnose. Referenzbereiche in den Settings       │
│   anpassen.                                               │
│                                                            │
│ [ Leber ] [ Niere ] [ Lipide ] [ Schilddrüse ] [ ... ▾ ] │ ← Kategorie-Tabs
│ ┌────────────────────────────────────────────────────┐   │
│ │ ALT         32 U/L   ✓     ▁▂▃▂▁  vor 3 Tagen        │   │
│ │ AST         28 U/L   ✓     ▁▁▂▂▁  vor 3 Tagen        │   │
│ │ GGT         71 U/L   ⚠     ▂▃▅▇█  vor 3 Tagen        │   │
│ │ Kreatinin   97 µmol/L ✓    ▁▂▁▁▁  vor 3 Tagen        │   │
│ │   ⤷ eingegeben als 1.1 mg/dL                          │   │ ← NEU: Subzeile bei abweichender Eingabe-Einheit
│ │ Bilirubin   —        –     –      noch nie erfasst   │   │
│ └────────────────────────────────────────────────────┘   │
│                                                            │
│ ▸ Neuen Wert erfassen                                     │
│ ┌────────────────────────────────────────────────────┐   │
│ │ Marker:  [ GGT (Leber)                          ▾ ]  │   │
│ │ Wert:    [ 71        ]  Einheit: [ U/L          ▾ ]  │   │
│ │ Zeitpunkt: [ 2026-10-28  09:15 ]  (Default: jetzt)   │   │
│ │ Bericht-Link/ID (optional): [ https://...        ]  │   │
│ │                                   [ Speichern      ]  │   │
│ └────────────────────────────────────────────────────┘   │
└────────────────────────────────────────────────────────────┘
```

**`report_ref`-Anzeige:** In Zeilen/Verlaufslisten mit gesetztem
`report_ref` erscheint ein kleines 🔗-Icon. Sieht der Wert wie eine URL aus
(`http(s)://`-Präfix) → klickbarer Link, öffnet in neuem Tab (`target="_blank"
rel="noopener"`); sonst Klartext-Tooltip „Quelle: `<report_ref>`". Rein
clientseitige Fallunterscheidung, keine Validierung/Normalisierung im
Backend nötig.

**Editor-Schema** (`lab-values-card-editor`, analog zur bestehenden Card):

| Key | Typ | Default | Bedeutung |
|---|---|---|---|
| `entry_id` | string | — | wie bestehende Card |
| `person_mode`/`person_filter`/`default_person` | wie bestehend | wie bestehend | Personen-Auswahl |
| `show_categories` | list[string] | leer = alle aktiven | Kategorie-Filter (Tab-Reihenfolge) |
| `show_trend` | bool | `true` | Sparkline-Spalte je Marker |
| `allow_manual_entry` | bool | `true` | „Neuen Wert erfassen"-Block ein-/ausblenden |
| `show_disclaimer` | bool | `true` | Medizin-Hinweiszeile (bewusst abschaltbar, aber Default an) |

- **Badge-Logik:** ✓ (im Referenzbereich), ⚠ (außerhalb), – (kein Referenzbereich
  hinterlegt), „noch nie erfasst" ohne Badge.
- **Eingabe-Einheit-Subzeile:** weicht `reported_unit` vom kanonischen
  `unit` ab (§2.4, §3), erscheint unter der Marker-Zeile dezent „⤷
  eingegeben als `<reported_value> <reported_unit>`" (Card) bzw. als
  Tooltip auf dem Wert (Panel, Platz ist dort knapper). Stimmen beide
  Einheiten überein (Normalfall ohne Umrechnung), entfällt die Subzeile
  komplett — kein Rauschen bei jedem Wert.
- **Sparkline:** letzte 14 aktive Werte je Marker, reine SVG-Pfad-Berechnung
  wie beim bestehenden Wellbeing-/BD-Chart (kein neues Rendering-Konzept).
- **Panel-Pendant:** vollwertiger SVG-Chart je Marker (Y-Achse = Referenz-
  bereich ± Puffer) im Sidebar-Panel, analog zum bestehenden BD-Verlaufsgraph
  — kein neues Chart-Pattern, Wiederverwendung der vorhandenen Panel-Chart-
  Helfer.
- **Eingabe-Block ruft** `health_o_mat/add_lab_value` über den bestehenden
  WS-Schreibpfad auf (wie `book_drink`/`save_measurement` heute) — **nicht**
  den Service direkt, damit UI-Fehler (z. B. `unknown_marker`) als
  Karten-Fehlermeldung statt HA-Service-Fehler-Toast erscheinen.

### 7.2 Panel-Integration

Die Person-Detail-Ansicht im Sidebar-Panel hat heute eine Tab-Leiste
(`renderDetail`/`enabledTabs` in `health-o-mat-panel-views.js`): **Trinken |
Blutdruck | Wohlbefinden**, gefiltert über die bestehenden `areas`-Toggle. Das
ist exakt der Mechanismus, in den sich Laborwerte einfügen — **kein neues
Navigationskonzept**, sondern ein vierter Eintrag:

```
┌─ Person ───────────────────────────────────────────────────┐
│ [ Trinken ] [ Blutdruck ] [ Wohlbefinden ] [ Laborwerte ] │ ← bestehende Tab-Leiste, +1 Tab
├────────────────────────────────────────────────────────────┤
│  ‹  [ Leber ]  [ Niere ]  [ Lipide ]  [ Blutbild ]  ›      │ ← Kategorie-Leiste, swipebar
│                                                              │
│     ALT          32 U/L   ✓   SVG-Chart (Referenzband)     │
│     AST          28 U/L   ✓   SVG-Chart (Referenzband)     │
│     GGT          71 U/L   ⚠   SVG-Chart (Referenzband)     │
│     Bilirubin    —        –   noch nie erfasst             │
│                                                              │
│     ▸ Neuen Wert erfassen  (wie Card, §7.1)                │
└────────────────────────────────────────────────────────────┘
```

- **Tab „Laborwerte"** erscheint nur bei `areas.labs` aktiv (`enabledTabs`
  bekommt den vierten Eintrag genauso wie die bestehenden drei — gleicher
  Filter-Mechanismus, keine Parallelstruktur).
- **Kategorie-Leiste** zeigt nur Kategorien, die (a) für die Person mindestens
  einen Marker mit Daten/Katalog-Eintrag haben **und** (b) nicht in
  `lab_hidden_categories` stehen (§2.5). Pfeile `‹`/`›` sind der Fallback für
  Maus/Tastatur; **Swipe** (Touch: `touchstart`/`touchend`, Delta-X über
  Schwellwert → vorherige/nächste sichtbare Kategorie) ist die primäre
  mobile Interaktion — reines Vanilla-JS wie der Rest des Panels, keine
  Geste-Bibliothek. Gleicher Aufbau wie die bestehende Tab-Leiste
  (`data-action`-Delegation), nur zusätzlich mit Touch-Listener.
  Zustand (aktive Kategorie) lebt wie `panel._tab` als Panel-internes Feld
  (`panel._labCategory`), kein Server-Store nötig (reine Darstellung).
- **Inhalt je Kategorie:** Marker-Zeilen mit Wert/Badge + vollwertigem
  SVG-Chart (Referenzbereich als Band, wie der bestehende BD-Verlaufsgraph)
  — Wiederverwendung der vorhandenen Panel-Chart-Helfer, kein neues
  Rendering-Pattern.
- **Eingabe-Block** ist identisch zum Card-Pendant (§7.1), gleicher
  WS-Aufruf (`health_o_mat/add_lab_value`), einmal implementiert in einem
  gemeinsamen Helper-Modul (vermeidet Card/Panel-Duplikat-Logik, wie es
  `health-o-mat-panel-base.js` heute schon für geteilte Helfer tut).

### 7.3 Overview-Tile (Personen-Dashboard-Grid)

Die Panel-Startseite (`renderOverview`/`renderTile` in
`health-o-mat-panel-views.js`) zeigt eine Kachel je Person mit kompakten
Zeilen pro aktivem Bereich — heute Trinken (Ring+Ziel), Blutdruck
(Wert + ⚠-Badge bei Schwellenüberschreitung), Wohlbefinden (Emoji+Label).
Laborwerte fügen sich als **vierte Zeile** nach demselben Muster ein, **kein**
neues Kachel-Layout:

```
┌─ Person ──────────────────────────── ⚠ ─┐
│ ● Person                                 │
│  ◔ 1200 ml        Ziel 2000 ml · Rest 800│  ← Trinken (bestehend)
│  🩸 128/82 · 68                          │  ← Blutdruck (bestehend)
│  🙂 Gut · vor 2 h                        │  ← Wohlbefinden (bestehend)
│  🧪 2 Marker außerhalb Referenz  ⚠       │  ← NEU: Laborwerte-Zeile
└───────────────────────────────────────────┘
```

- **Lab-Zeile** (`labRow`, gated by `areas.labs`): zeigt die Anzahl Marker
  außerhalb des Referenzbereichs über alle **sichtbaren** Kategorien
  (`lab_hidden_categories` ausgenommen) — `"🧪 Alles im Bereich"` (kein
  Badge) oder `"🧪 N Marker außerhalb Referenz"` (mit ⚠-Badge). Keine
  Einzelwerte in der Kachel (zu klein/zu viele Marker) — Tap öffnet wie
  gewohnt die Detail-Ansicht → Tab „Laborwerte" (§7.2).
- **Tile-Head-Warnbadge:** das bestehende ⚠-Badge neben dem Personennamen
  (heute nur BD-Schwellenüberschreitung) wird **additiv** um „≥ 1
  Lab-Marker außerhalb Referenz" erweitert — ein Tooltip-Text listet beide
  Ursachen, falls beide zutreffen (z. B. „Blutdruck oberhalb der Schwellen;
  2 Laborwerte außerhalb Referenz"), kein zweites Badge-Icon (Kachel bleibt
  aufgeräumt).
- Berechnung (`panel._labWarningCount(data)`) ist reine Darstellungslogik
  auf den schon geladenen `panel_data`-Attributen der Lab-Sensoren
  (`in_range`-Attribut, §4) — kein zusätzlicher WS-Request je Kachel.

---

## 8. Backup / Export / Import

- **Backup (`backup.py`, Format-Version +1):** `lab_readings[]` je Person
  sowie `lab_custom_markers`/`lab_ref_overrides`/`lab_hidden_categories`
  (aus `entry.options`) zusätzlich im JSON-Dump. Additive Felder — alte
  Backups bleiben lesbar, `format`/`version`-Check bleibt wie bisher.
- **Restore (`restore.py`):** `lab_readings` wird als weiterer Datensatz-Typ
  neben `drinks`/`readings`/`wellbeing_entries` registriert (Merge/Replace +
  Teil-Restore nach Person/Datensatz/Zeitraum gelten automatisch mit).
  **Custom-Marker-Definitionen werden mitgemerged** (nicht nur die
  Messwerte) — sonst würde ein Restore auf eine andere/leere Installation
  Werte mit unbekanntem `marker_key` referenzieren. Validierung: jeder
  restaurierte `lab_readings`-Eintrag muss nach dem Merge einen bekannten
  Marker (Katalog oder gerade mitrestaurierter Custom-Marker) haben, sonst
  Restore-Validierungsfehler (wie bestehende Restore-Validierung heute).
- **CSV-Export (`exporter.py`):** neue Datei `lab_values.csv` im Export-
  Verzeichnis (`ts, marker_key, category, value, unit, reported_value,
  reported_unit, report_ref`), zusätzlich zu `drinks.csv`/`readings.csv`.
  Nur aktive (nicht-voided) Einträge, wie bestehend.
- **CSV-Import (`importer.py`):** `lab_values.csv` wird erkannt (gleicher
  tolerante Parser: Semikolon, UTF-8-BOM, abweichender Header), Dedup-
  Schlüssel `ts`+`marker_key`+`value` (analog `ts`+`sys`+`dia` bei BD).
  Unbekannter `marker_key` beim Import → Zeile wird als `rejected` gemeldet
  (gleiche Notification-Struktur `imported/skipped/rejected` wie heute),
  **kein** automatisches Anlegen eines Custom-Markers beim Import (konsistent
  zu §5.1).

---

## 9. Tests & Migration

- **HA-freie Logik** (`logic.py`): `convert_lab_value`,
  `resolve_lab_reference`, `lab_marker_in_range` — vollständig unit-testbar
  ohne Fake-HA, wie der Rest von `logic.py`.
- **Store:** neue Tests analog zu `test_store.py`s Reading-Tests (add/void/
  restore/remove_last, Migration v4→v5 idempotent).
- **Services:** `ServiceValidationError`-Pfade (`unknown_marker`,
  `unsupported_unit`, `unit_required`, ungültige `ts`) + Erfolgspfad inkl.
  Store-Audit-Limit. Alias-Auflösung (`gpt`/`got`/`gamma_gt` → `alt`/`ast`/
  `ggt`) landet unter demselben `marker_key` wie der Primärname.
- **Entities:** dynamische Erzeugung (Katalog + Custom + Area-Filter),
  Übersetzungs-Parität de/en für Katalog-Marker-Namen (Paritätstest wie
  bestehend für Services, N-10).
- **Card/Panel (JS):** Editor-Flags, Badge-/Sparkline-Helfer, Eingabe-Block-
  Fehlerpfad (`unknown_marker` → Karten-Fehlermeldung statt Toast),
  Laborwerte-Tab nur bei `areas.labs` aktiv (analog bestehendem
  `enabledTabs`-Test), Kategorie-Leiste respektiert `lab_hidden_categories`,
  Swipe-Geste wechselt zur nächsten/vorherigen **sichtbaren** Kategorie
  (Grenzfall: erste/letzte Kategorie, nur eine sichtbare Kategorie),
  Eingabe-Einheit-Subzeile erscheint nur bei `reported_unit != unit` und
  verschwindet bei Gleichheit.
- **Konvertierung (Katalog + Custom):** `convert_lab_value` rundtrip-getestet
  in beide Richtungen je Alt-Unit-Paar (Haupt→kanonisch **und**
  Alt-Einheit→kanonisch liefern denselben kanonischen Wert), inkl. der
  Custom-Marker-Variante mit nutzerdefiniertem `alt_unit`-Faktor.
- **Backup/Restore/Export/Import:** Round-Trip-Test (Backup → Restore auf
  leere Installation → Custom-Marker + Werte vollständig da), CSV-Round-Trip.
- **Migration:** `_migrate_v4_to_v5` auf Alt-Store-Fixture, idempotent bei
  doppeltem Aufruf.
- **E2E (`tests_e2e/`):** ein neuer Smoke-Test (Marker anlegen, Wert erfassen,
  Referenz-Override setzen, Card/Panel zeigen ihn an) — ergänzt die
  bestehende Playwright-Suite, kein neues Test-Framework.

---

## 10. Offene Punkte für den Implementierungsplan

- Reihenfolge der Umsetzung (Welle-Vorschlag): (1) Store+Logik+Migration,
  (2) Services, (3) Entities (Sensor+Binary-Sensor+Area-Schalter),
  (4) Admin-UI, (5) Card+Panel, (6) Backup/Export/Import, (7) E2E.
- Genaue `translation_key`-Namen für die 28 Katalog-Marker (de/en) —
  Detailarbeit im Implementierungsplan, nicht hier.
- Ob der Feedback-Issue-Link ein GitHub-Issue-Template nutzt (falls das
  Repo eins hat) — im Implementierungsplan prüfen.

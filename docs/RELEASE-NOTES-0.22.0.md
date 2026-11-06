# v0.22.0 — Anzeige-Einheiten für Laborwerte, Einheiten-Dropdowns, mehrere Alt-Einheiten

## Zusammenfassung

Minor-Release mit einem reinen **Anzeige-Feature** für Laborwerte (REQ-HOM-134):
Jeder Marker zeigt seinen Wert künftig in einer **typischen Labor-Alltagseinheit**
(Werkseinstellung) an, die **pro Person** übersteuerbar ist
(Override > Werkseinstellung > kanonisch). Die Einheiten-Eingabe wird vom
Freitextfeld zum **Dropdown** mit „Andere …"-Zweig, und eigene Marker können
**mehrere** Alt-Einheiten über eine additive `alt_units`-Map abbilden. Der
Release ist **rein additiv und ohne Breaking Changes**: Sensoren, Store und CSV
bleiben kanonisch, es gibt keine Migration und keinen `async_migrate_entry`-
Schritt.

> ℹ️ **Hinweis — bitte vor dem Update lesen.** Nach dem Update erscheinen
> Laborwerte in Panel und Karte in der jeweiligen **Anzeige-Einheit** (z. B.
> Kreatinin in `mg/dL` statt `µmol/L`). Das ist gewollt und ändert **keine**
> Daten: Sensor-State, `native_unit_of_measurement`, Langzeitstatistik und
> CSV-Export/-Import bleiben kanonisch. Wer die kanonische Anzeige bevorzugt,
> setzt in der Admin-Maske pro Marker die kanonische Einheit als Override.
> Es gibt **nichts zu migrieren**.

## ✨ New features

### Anzeige-Einheiten mit Werkseinstellung und Personen-Override — REQ-HOM-134

Die Anzeige-Einheit wird in drei Stufen aufgelöst:

| Stufe | Bedingung | Ergebnis |
|---|---|---|
| 1 | `entry.options["lab_default_units"][marker]` gesetzt und gültig | Personen-Override (Katalogschreibweise) |
| 2 | `LAB_DEFAULT_UNITS[marker]` gesetzt und gültig | Werkseinstellung |
| 3 | sonst | kanonische Einheit |
| 4 | ungültige/unbekannte Einheit (defensiv) | kanonische Einheit — **nie** ein Fehler |

**Werkseinstellungen** (`LAB_DEFAULT_UNITS`) für zwölf Marker:

| Marker | Kanonisch | Werkseinstellung |
|---|---|---|
| `bilirubin_total` | `µmol/L` | `mg/dL` |
| `creatinine` | `µmol/L` | `mg/dL` |
| `urea` | `mmol/L` | `mmol/L` (kanonisch, F12) |
| `cholesterol_total` | `mmol/L` | `mg/dL` |
| `ldl` | `mmol/L` | `mg/dL` |
| `hdl` | `mmol/L` | `mg/dL` |
| `triglycerides` | `mmol/L` | `mg/dL` |
| `ft4` | `pmol/L` | `ng/dL` |
| `ft3` | `pmol/L` | `pg/mL` |
| `hemoglobin` | `g/L` | `g/dL` |
| `albumin` | `g/L` | `g/dL` |
| `hematocrit` | `L/L` | `%` |

Alle übrigen Marker zeigen weiterhin ihre kanonische Einheit. Ein **explizit
kanonischer Override** (z. B. `{"creatinine": "µmol/L"}`) ist gültig und
übersteuert den Werksdefault bewusst. Gespeicherte Schreibweisen werden auf die
**Katalogschreibweise** normalisiert (`MG/DL` → `mg/dL`).

Die Overrides werden ausschließlich über die **Admin-Maske**
(`get_settings`/`set_settings`) gepflegt — wie die übrigen Labor-Optionen. Eine
Änderung ist reine Anzeige und löst **keinen** Config-Entry-Reload aus.

### Einheiten-Dropdowns in Panel und Karte

Das Einheitenfeld ist kein Freitextfeld mehr:

- Das **Dropdown** wird je Marker aus `allowed_units` gefüllt (kanonische
  Einheit zuerst, danach alle Alt-Einheiten; Custom-Marker inklusive).
- Einzel- und Berichts-Formular **wählen die Anzeige-Einheit vor**; der Wert
  wird in dieser Einheit eingegeben und **immer mit expliziter Einheit**
  gesendet.
- „Andere …" öffnet weiterhin ein Freitextfeld. Ein **leerer** Freitext
  blockiert den Submit mit sichtbarer Fehlermeldung, statt eine leere Einheit
  zu senden.
- Wird eine Formularzeile mit einem anderen Marker wiederverwendet, werden
  **Marker und Anzeige-Einheit** gemeinsam gesetzt — die Zeile erbt keine
  fremde Einheit.
- Die Admin-Maske bietet je Marker ein Anzeige-Select mit
  „Standard (`mg/dL`)"-Option (setzt auf die Werkseinstellung zurück) — in den
  Katalog- **und** den Custom-Zeilen.

### Mehrere Alt-Einheiten für eigene Marker

Custom-Marker akzeptieren jetzt eine additive **`alt_units`-Map**
(`{einheit: faktor_nach_kanonisch}`), z. B.
`{"nmol/L": 2.5, "µg/L": 0.4}`. Die bisherige Einzelform `alt_unit` bleibt
**dauerhaft lesbar** (Legacy) und wird beim nächsten Speichern idempotent in
die Map überführt. Ungültige Paare (kein positiver, endlicher Faktor) fallen
einzeln weg; ein Duplikat der kanonischen Einheit wird verworfen. Die
Admin-Maske kann weitere Einheiten hinzufügen und entfernen; die kuratierte
Liste `LAB_UNITS` speist die Dropdowns, Freitext-Einheiten bleiben weiterhin
erlaubt.

### Einheitliche Dezimalableitung für Wert, Grenze und Chart

Panel und Karte leiten die Nachkommastellen aus **einer** Quelle ab:
`base_d` nach Betrag des konvertierten Anzeigewerts, dann einmalig
`d = min(base_d + 1, 3)`. Dieses `d` gilt identisch für den angezeigten Wert,
`ref_min`/`ref_max` und das Chart-Band. Ein kanonisch `in_range`-Wert kann
damit nicht über seiner eigenen angezeigten Grenze erscheinen.

### Additive Wire-Felder

- `panel_data.labs.markers[*]` erhält `default_unit` (aufgelöste Anzeige-Einheit)
  und `allowed_units` (kanonisch zuerst). Bestehende Keys bleiben unverändert;
  ältere Karten ignorieren die neuen Felder.
- `get_settings` liefert zusätzlich `lab_default_units` (normalisiert),
  `lab_default_units_factory` (nur lesen), `lab_allowed_units` (nur lesen) und
  `lab_units` (nur lesen, Einheiten-Dropdowns des Custom-Formulars).

## Kompatibilität & Aktionshinweise

Es gibt **keine Breaking Changes** und **keine Migration**.

### Was unverändert bleibt

- **Sensoren, Store und CSV bleiben kanonisch:** `native_unit_of_measurement`,
  Entity-State, Langzeitstatistik sowie CSV-Export/-Import sind unberührt; die
  Konvertierung findet ausschließlich in der UI statt.
- **`in_range` und Badge** werden weiterhin kanonisch auf dem Server berechnet;
  die Anzeige-Rundung beeinflusst sie nie.
- **`unique_id`s, Entity-IDs, `translation_key` und Entity-Menge** — unverändert;
  keine Entity-Registry-Migration.
- **Store-Schema** — `5`; **Config-Entry-Version** — `3`; **`BACKUP_VERSION`** —
  `3`. Kein `async_migrate_entry`-Schritt.
- **Panel-/Card-Registrierung** — der Cache-Buster (`?v=0.22.0`),
  `PANEL_VERSION` und `CARD_VERSION` sind auf `0.22.0` gezogen.

### Backup, Restore und Diagnostics

- **Backup enthält `lab_default_units`** additiv je Entry
  (Datenvollständigkeit); alte Backups ohne den Key bleiben lesbar.
- **Restore spielt `lab_default_units` in v1 bewusst nicht zurück (F14):** der
  Key wird wie `lab_ref_overrides` behandelt — `plan_restore`/`apply_restore`
  ignorieren ihn. Nach einem Restore gilt weiterhin die lokale Option bzw. die
  Werkseinstellung. Ein vollständiger Restore/Apply-Pfad ist als Follow-up-Issue
  vorgemerkt.
- **Diagnostics exportiert den Key count-only** (`{"count": n}`); Marker-Keys
  und Custom-Slugs erscheinen nicht im serialisierten Ergebnis.

### `urea` bleibt kanonisch (F12)

Der Katalogfaktor `0.357` bildet die **BUN-Skala** ab, nicht die
Harnstoff-Skala (≈ `0.1665`). Eine Anzeige in `mg/dL` würde jeden
Harnstoff-Befund um Faktor ≈ 2,1 verzerren. Deshalb bleibt der Werksdefault
`mmol/L`; **der Faktor wird nicht angefasst** — gemeldete `mg/dL`-Werte werden
exakt wie bisher umgerechnet. Eine Katalogkorrektur ist ein eigenes Issue.

## Verifikation

| Prüfung | Ergebnis |
|---|---|
| Unit-/JS-Tests (`pytest`) | **1936 passed** |
| E2E (REQ-HOM-134: Laborwerte + Diagnostics) | **14 passed** |
| `ruff check` / `ruff format --check` | clean |

> Hinweis: Der reale **HACS-Update-Test** (Update von 0.21.0 auf 0.22.0 über
> HACS auf einer bestehenden Installation) und der
> **Post-Release-Orphan-Cleanup** sind **manuell** und nicht Teil dieser
> Verifikation. Da keine Entity-Identität geändert wurde, sind keine
> verwaisten Entities zu erwarten.

## Upgrade

1. Update über HACS installieren.
2. Home Assistant neu starten (für das Frontend-Caching der Panel-Module der
   sichere Weg).
3. Optional: In der Admin-Maske je Person die Anzeige-Einheiten prüfen und
   übersteuern; „Standard (…)" setzt auf die Werkseinstellung zurück.
4. Es gibt nichts zu migrieren.

## Vollständiger Changelog

https://github.com/Popoboxxo/ha-health-o-mat/compare/v0.21.0...v0.22.0

---

# v0.22.0 — Lab display units, unit dropdowns, multiple alternative units

## Summary

Minor release with a display-only feature for lab values (REQ-HOM-134): every
marker now renders in a **typical laboratory unit** (factory default) that can
be **overridden per person** (override > factory default > canonical). The unit
input becomes a **dropdown** with an "Other …" branch, and custom markers can
carry **multiple** alternative units via an additive `alt_units` map. The
release is **purely additive with no breaking changes**: sensors, store and CSV
stay canonical, and there is no migration or `async_migrate_entry` step.

> ℹ️ **Note — please read before updating.** After the update lab values in the
> panel and card render in their **display unit** (e.g. creatinine in `mg/dL`
> instead of `µmol/L`). This is intended and changes **no** data: the sensor
> state, `native_unit_of_measurement`, long-term statistics and CSV
> export/import stay canonical. If you prefer the canonical display, set the
> canonical unit as a per-marker override in the admin mask. There is
> **nothing to migrate**.

## ✨ New features

### Display units with factory defaults and per-person overrides — REQ-HOM-134

The display unit is resolved in three stages:

| Stage | Condition | Result |
|---|---|---|
| 1 | `entry.options["lab_default_units"][marker]` set and valid | per-person override (catalog spelling) |
| 2 | `LAB_DEFAULT_UNITS[marker]` set and valid | factory default |
| 3 | otherwise | canonical unit |
| 4 | invalid/unknown unit (defensive) | canonical unit — **never** an error |

**Factory defaults** (`LAB_DEFAULT_UNITS`) for twelve markers:

| Marker | Canonical | Factory default |
|---|---|---|
| `bilirubin_total` | `µmol/L` | `mg/dL` |
| `creatinine` | `µmol/L` | `mg/dL` |
| `urea` | `mmol/L` | `mmol/L` (canonical, F12) |
| `cholesterol_total` | `mmol/L` | `mg/dL` |
| `ldl` | `mmol/L` | `mg/dL` |
| `hdl` | `mmol/L` | `mg/dL` |
| `triglycerides` | `mmol/L` | `mg/dL` |
| `ft4` | `pmol/L` | `ng/dL` |
| `ft3` | `pmol/L` | `pg/mL` |
| `hemoglobin` | `g/L` | `g/dL` |
| `albumin` | `g/L` | `g/dL` |
| `hematocrit` | `L/L` | `%` |

All other markers keep their canonical unit. An **explicitly canonical
override** (e.g. `{"creatinine": "µmol/L"}`) is valid and deliberately
overrides the factory default. Stored spellings are normalised to the
**catalog spelling** (`MG/DL` → `mg/dL`).

Overrides are managed exclusively through the **admin mask**
(`get_settings`/`set_settings`), like the other lab options. A change is
display-only and triggers **no** config-entry reload.

### Unit dropdowns in panel and card

The unit input is no longer free text:

- The **dropdown** is built per marker from `allowed_units` (canonical unit
  first, then all alternative units, custom markers included).
- The single-entry and report forms **preselect the display unit**; the value
  is entered in that unit and **always sent with an explicit unit**.
- "Other …" still opens a free-text field. An **empty** free text blocks the
  submit with a visible error instead of sending an empty unit.
- When a form row is reused for a different marker, **marker and display unit**
  are set together — the row never inherits a foreign unit.
- The admin mask offers a display select per marker including a
  "Default (`mg/dL`)" option (resets to the factory default) — in both catalog
  and custom rows.

### Multiple alternative units for custom markers

Custom markers now accept an additive **`alt_units` map**
(`{unit: factor_to_canonical}`), e.g. `{"nmol/L": 2.5, "µg/L": 0.4}`. The
previous single form `alt_unit` remains **permanently readable** (legacy) and
is converted idempotently into the map on the next save. Invalid pairs (not a
positive, finite factor) are dropped individually; a duplicate of the canonical
unit is discarded. The admin mask can add and remove additional units; the
curated `LAB_UNITS` list feeds the dropdowns, and free-text units are still
accepted.

### One decimal source for value, bounds and chart

Panel and card derive the decimal places from **one** source: `base_d` by the
magnitude of the converted display value, then once
`d = min(base_d + 1, 3)`. The same `d` applies to the displayed value,
`ref_min`/`ref_max` and the chart band. A canonically `in_range` value can
therefore never appear above its own displayed bound.

### Additive wire fields

- `panel_data.labs.markers[*]` gains `default_unit` (resolved display unit) and
  `allowed_units` (canonical first). Existing keys are unchanged; older cards
  ignore the new fields.
- `get_settings` additionally returns `lab_default_units` (normalised),
  `lab_default_units_factory` (read-only), `lab_allowed_units` (read-only) and
  `lab_units` (read-only, unit dropdowns of the custom form).

## Compatibility & action items

There are **no breaking changes** and **no migration**.

### What stays

- **Sensors, store and CSV stay canonical:** `native_unit_of_measurement`, the
  entity state, long-term statistics and CSV export/import are untouched; the
  conversion happens in the UI only.
- **`in_range` and the badge** are still computed canonically on the server;
  display rounding never affects them.
- **`unique_id`s, entity ids, `translation_key` and the entity set** —
  unchanged; no entity-registry migration.
- **Store schema** — `5`; **config-entry version** — `3`; **`BACKUP_VERSION`** —
  `3`. No `async_migrate_entry` step.
- **Panel/card registration** — the cache buster (`?v=0.22.0`),
  `PANEL_VERSION` and `CARD_VERSION` are bumped to `0.22.0`.

### Backup, restore and diagnostics

- **The backup includes `lab_default_units`** additively per entry (data
  completeness); old backups without the key stay readable.
- **Restore deliberately does not apply `lab_default_units` in v1 (F14):** the
  key is treated like `lab_ref_overrides` — `plan_restore`/`apply_restore`
  ignore it. After a restore the local option or the factory default still
  applies. A full restore/apply path is tracked as a follow-up issue.
- **Diagnostics exports the key count-only** (`{"count": n}`); marker keys and
  custom slugs never appear in the serialised result.

### `urea` stays canonical (F12)

The catalog factor `0.357` represents the **BUN scale**, not the urea scale
(≈ `0.1665`). Displaying `mg/dL` would distort every urea reading by a factor
of ≈ 2.1. The factory default therefore stays `mmol/L`; **the factor is not
touched** — reported `mg/dL` values are converted exactly as before. A catalog
correction is a separate issue.

## Verification

| Check | Result |
|---|---|
| Unit/JS tests (`pytest`) | **1936 passed** |
| E2E (REQ-HOM-134: lab values + diagnostics) | **14 passed** |
| `ruff check` / `ruff format --check` | clean |

> Note: the real **HACS update test** (updating from 0.21.0 to 0.22.0 via HACS
> on an existing installation) and the **post-release orphan cleanup** are
> **manual** and not part of this verification. Since no entity identity
> changed, no orphaned entities are expected.

## Upgrade

1. Install the update via HACS.
2. Restart Home Assistant (the safe route for the panel module caching).
3. Optional: review and override the display units per person in the admin
   mask; "Default (…)" resets to the factory default.
4. There is nothing to migrate.

## Full changelog

https://github.com/Popoboxxo/ha-health-o-mat/compare/v0.21.0...v0.22.0

# v0.19.0 — Labor-Katalog erweitert, Einheiten-Härtung

## Zusammenfassung

Minor-Release mit einem deutlich größeren Laborwert-Katalog: **12 neue Marker**
(Blutbild, Leber, Elektrolyte, Niere, Medikamentenspiegel, Stoffwechsel) heben
den Katalog von **29 auf 41** Einträge, dazu kommt die neue Kategorie
**`metabolism`** („Stoffwechsel") mit eigener Warn-Entity. Für sieben Marker ist
eine Einheit jetzt Pflicht, und die Einheiten-Erkennung akzeptiert gängige
Schreibvarianten (`umol/L`, `10¹²/L`, `Prozent`). Der Release ist **rein
additiv**: keine Datenmigration, keine `unique_id`-Änderung, keine
Entity-Registry-Migration.

> ⚠️ **Handlungshinweis — bitte vor dem Update lesen.** Nach dem Update legt die
> Integration **12 neue Sensoren und 1 neue Warn-Binary pro Person** an. Das ist
> gewollt und erfordert **keine Migration**; bestehende Entitäten und
> Automationen bleiben unverändert. Wer `panel_data` auswertet, bekommt dort
> jetzt zusätzlich `require_explicit_unit` (siehe „💥 Breaking changes").

## ✨ New features

### 12 neue Labor-Marker — REQ-HOM-133, Issue #73

Der Katalog `LAB_MARKERS` wächst von **29 auf 41** Einträge (Bestand
unverändert):

| Bereich | Neue Marker |
|---|---|
| Blutbild | `mch`, `erythrocytes`, `hematocrit`, `mchc`, `mcv` |
| Leber | `albumin`, `alkaline_phosphatase` |
| Elektrolyte | `phosphate` |
| Niere | `uric_acid` |
| Medikamentenspiegel | `ciclosporin`, `everolimus` |
| Stoffwechsel | `hba1c` |

Pro Person entstehen daraus `sensor.<person>_lab_*`-Entities sowie — durch die
neue Kategorie — `binary_sensor.<person>_lab_warning_metabolism`.

### Neue Kategorie `metabolism` („Stoffwechsel")

`metabolism` ist eine eigene Kategorie mit eigener Warn-Entity und wird in
Panel und Karte wie die bestehenden Kategorien angezeigt (Reihenfolge: vor
`other`).

### Einheiten-Pflicht für sieben Marker

Für `mchc`, `hematocrit`, `albumin`, `alkaline_phosphatase`, `phosphate`,
`uric_acid` und `hba1c` ist eine Einheit jetzt verpflichtend: fehlt sie oder ist
sie leer, antworten Service, WebSocket-Command und Batch-Import mit
`unit_required`, statt den Wert ohne Einheit zu speichern. Custom-Marker können
das Flag (`require_explicit_unit`) ebenfalls tragen.

### Tolerantere Einheiten-Erkennung

Gängige Schreibvarianten werden jetzt erkannt:

| Eingabe | Canonical |
|---|---|
| `umol/L` | `µmol/L` |
| `10¹²/L` (Superscript) | `10^12/L` |
| `Prozent` | `%` |

Die Normalisierung betrifft **nur den Vergleich** — gespeichert wird weiterhin
die kanonische Einheit.

### Hinweis auf die Einheiten-Pflicht in der UI

Der Panel-Berichtsdialog und die Labs-Card zeigen an, wenn für einen Marker eine
Einheit erforderlich ist, und markieren das Feld entsprechend.

## 💥 Breaking changes / Aktionshinweise

Es gibt **keine** Änderung an `unique_id`s, Entity-IDs, Store-Schema
(`schema: 5`) oder `config entry`-Version (3). Die folgenden Punkte sind
trotzdem vor dem Update zu lesen.

### 1. 12 neue Sensoren + 1 neue Warn-Binary pro Person

Durch den erweiterten Katalog registriert jede konfigurierte Person zusätzliche
Entities.

- **Betroffen:** Dashboards, die Entitäten automatisch einbinden (z. B.
  Auto-Entities), und Automationen, die auf „alle Labor-Sensoren" filtern.
- **Handlung:** Keine Migration nötig — neue Entitäten erscheinen einfach.
  Dashboards/Automationen, die mit dem Katalog mitwachsen sollen, prüfen.
- **Nicht betroffen:** Alle bestehenden Entitäten, `unique_id`s und der Verlauf.

### 2. HbA1c in `%` wird bewusst nicht unterstützt

`hba1c` akzeptiert `mmol/mol`. Die Angabe in **`%`** führt zu
`unsupported_unit` — die nichtlineare Umrechnung (IFCC ↔ DCCT) ist nicht Teil
dieses Releases.

- **Handlung:** HbA1c-Werte in `mmol/mol` erfassen. Wer `%`-Werte importiert,
  sieht `unsupported_unit` in der Import-Antwort und muss die Zeile umrechnen
  oder entfernen.

### 3. `require_explicit_unit` erscheint im Panel-Payload

Das Flag wird jetzt in `panel_data` ausgeliefert (vorher bewusst nicht).

- **Betroffen:** ausschließlich Clients, die `panel_data` selbst auswerten
  (eigene Templates, Skripte, Custom-Cards gegen den Panel-Datenpfad).
- **Handlung:** Wenn ein striktes Schema über die Payload läuft, das Feld
  ergänzen. Das eingebaute Panel und die Karten sind bereits angepasst.

### Was unverändert bleibt

- **`unique_id`s und Entity-IDs** — unverändert; keine Entity-Registry-Migration
- **Store-Schema** — `schema: 5`; Bestandsdaten werden nicht angefasst
- **`config entry`-Version** — 3, kein `async_migrate_entry`-Schritt nötig
- **Panel-/Card-Registrierung** — Versions-Query (`?v=0.19.0`), `PANEL_VERSION`
  und `CARD_VERSION` sind mitgezogen

## Intern

- Tote Code-Reste entfernt (kein Verhaltensunterschied).
- Requirements-/Spec-Status nachgezogen (REQ-HOM-133 dokumentiert, Doku-Drift
  bereinigt).

## Upgrade

1. Update über HACS installieren.
2. Home Assistant neu starten (ein Reload genügt der Integration; der Neustart
   ist für das Frontend-Caching der Panel-Module der sichere Weg).
3. Neue Labor-Entities in Dashboards aufnehmen (Punkt 1), HbA1c-Werte in
   `mmol/mol` erfassen (Punkt 2), eigene `panel_data`-Auswerter prüfen
   (Punkt 3).
4. Es gibt nichts zu migrieren.

## Kompatibilität

- `manifest.version` 0.19.0; `config entry`-Version 3 (unverändert).
- Store-Schema 5 (unverändert) — Bestandsdaten bleiben unberührt.
- Der Katalog ist rein additiv; bestehende Marker-Keys und ihre Einheiten sind
  unverändert.

## Vollständiger Changelog

https://github.com/Popoboxxo/ha-health-o-mat/compare/v0.18.0...v0.19.0

---

# v0.19.0 — Larger lab catalog, stricter unit handling

## Summary

Minor release with a considerably larger lab marker catalog: **12 new markers**
(blood count, liver, electrolytes, kidney, drug levels, metabolism) raise the
catalog from **29 to 41** entries, and the new category **`metabolism`** comes
with its own warning entity. Seven markers now require a unit, and unit
detection accepts common spellings (`umol/L`, `10¹²/L`, `Prozent`). The release
is **purely additive**: no data migration, no `unique_id` change, no entity
registry migration.

> ⚠️ **Action required — please read before updating.** After the update the
> integration creates **12 new sensors and 1 new warning binary per person**.
> That is intended and needs **no migration**; existing entities and automations
> stay unchanged. Anyone evaluating `panel_data` now also receives
> `require_explicit_unit` (see "💥 Breaking changes").

## ✨ New features

### 12 new lab markers — REQ-HOM-133, issue #73

`LAB_MARKERS` grows from **29 to 41** entries (existing entries unchanged):

| Area | New markers |
|---|---|
| Blood count | `mch`, `erythrocytes`, `hematocrit`, `mchc`, `mcv` |
| Liver | `albumin`, `alkaline_phosphatase` |
| Electrolytes | `phosphate` |
| Kidney | `uric_acid` |
| Drug levels | `ciclosporin`, `everolimus` |
| Metabolism | `hba1c` |

Per person this yields `sensor.<person>_lab_*` entities plus — through the new
category — `binary_sensor.<person>_lab_warning_metabolism`.

### New category `metabolism`

`metabolism` is its own category with a dedicated warning entity and is
displayed in panel and card like the existing categories (ordered before
`other`).

### Unit required for seven markers

`mchc`, `hematocrit`, `albumin`, `alkaline_phosphatase`, `phosphate`,
`uric_acid` and `hba1c` now require a unit: if it is missing or empty, service,
WebSocket command and batch import answer with `unit_required` instead of
storing the value without a unit. Custom markers can carry the flag
(`require_explicit_unit`) as well.

### More tolerant unit detection

Common spellings are recognised:

| Input | Canonical |
|---|---|
| `umol/L` | `µmol/L` |
| `10¹²/L` (superscript) | `10^12/L` |
| `Prozent` | `%` |

Normalisation affects **comparison only** — the canonical unit is still what
gets stored.

### Unit-requirement hint in the UI

The panel report dialog and the labs card indicate when a marker requires a
unit and mark the field accordingly.

## 💥 Breaking changes / action items

There is **no** change to `unique_id`s, entity ids, the store schema
(`schema: 5`) or the `config entry` version (3). The following points are still
worth reading before updating.

### 1. 12 new sensors + 1 new warning binary per person

The extended catalog registers additional entities for every configured person.

- **Affected:** dashboards that include entities automatically (e.g.
  auto-entities) and automations filtering "all lab sensors".
- **Action:** no migration needed — the new entities simply appear. Review
  dashboards/automations that should grow with the catalog.
- **Not affected:** all existing entities, `unique_id`s and history.

### 2. HbA1c in `%` is deliberately unsupported

`hba1c` accepts `mmol/mol`. Providing **`%`** results in `unsupported_unit` —
the non-linear conversion (IFCC ↔ DCCT) is not part of this release.

- **Action:** record HbA1c in `mmol/mol`. Importing `%` values surfaces
  `unsupported_unit` in the import response, and the row must be converted or
  removed.

### 3. `require_explicit_unit` is part of the panel payload

The flag is delivered in `panel_data` now (previously deliberately not).

- **Affected:** only clients that evaluate `panel_data` themselves (custom
  templates, scripts, custom cards against the panel data path).
- **Action:** if a strict schema runs over the payload, add the field. The
  built-in panel and cards are already adapted.

### What stays

- **`unique_id`s and entity ids** — unchanged; no entity-registry migration
- **Store schema** — `schema: 5`; existing data is untouched
- **`config entry` version** — 3, no `async_migrate_entry` step required
- **Panel/card registration** — the version query (`?v=0.19.0`), `PANEL_VERSION`
  and `CARD_VERSION` are bumped along

## Internal

- Removed dead code leftovers (no behaviour change).
- Requirement/spec status brought up to date (REQ-HOM-133 documented,
  documentation drift cleaned up).

## Upgrade

1. Install the update via HACS.
2. Restart Home Assistant (a reload is enough for the integration; the restart
   is the safe route for the panel module caching).
3. Add the new lab entities to dashboards (point 1), record HbA1c in `mmol/mol`
   (point 2), check custom `panel_data` consumers (point 3).
4. There is nothing to migrate.

## Compatibility

- `manifest.version` 0.19.0; `config entry` version 3 (unchanged).
- Store schema 5 (unchanged) — existing data is untouched.
- The catalog is purely additive; existing marker keys and their units are
  unchanged.

## Full changelog

https://github.com/Popoboxxo/ha-health-o-mat/compare/v0.18.0...v0.19.0

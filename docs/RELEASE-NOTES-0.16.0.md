# v0.16.0 — Laborwerte

## Zusammenfassung

Minor-Release: führt **Laborwerte als vierte Datendomäne** ein (neben Trinken,
Blutdruck und Wohlbefinden). Erfasst werden Messwerte in neun medizinischen
Kategorien — Leber, Niere, Elektrolyte, Lipide, Schilddrüse, Blutbild,
Entzündung, Verdauung und Medikamentenspiegel — plus „Sonstige" für eigene
Marker. Der Katalog liefert 29 Marker mit typischen Erwachsenen-Richtwerten,
pro Person anpassbaren Referenzbereichen und bidirektionaler Einheiten-
Umrechnung. Werte stehen als native HA-Entities zur Verfügung, sind über
Services schreibbar und werden über Backup und CSV exportiert/importiert.

> ⚠️ Die Integration klassifiziert nicht medizinisch und diagnostiziert nicht.
> Referenzbereiche sind Richtwerte, keine klinische Norm.

## ✨ New features

- **Laborwerte-Domäne** — 29 Marker in neun Kategorien plus „Sonstige" für
  eigene Marker, je mit Referenzbereich (min/max, auch einseitig), optionalen
  Per-Person-Overrides und per-Kategorie-Sichtbarkeit. Deutsche Labor-
  synonyme werden aufgelöst (`gpt` → `alt`, `got` → `ast`, `gamma_gt` → `ggt`).
- **Einheiten-Umrechnung in beide Richtungen** — Katalog-Einheit plus optionales
  Alt-Einheiten-Paar je Custom-Marker (z. B. `mg/dL` ↔ `µmol/L`). Werte werden
  kanonisch gespeichert; der eingegebene Wert bleibt als
  `reported_value`/`reported_unit` nachvollziehbar. Bei verwechslungs-
  gefährlichen Markern ist `unit` Pflicht.
- **`report_ref`** — optionaler Verweis auf den Laborbericht (Link oder externe
  ID, max. 500 Zeichen); die Integration ruft die Referenz nie selbst auf.
- **Entities** — ein Sensor je Marker (State = zeitlich neuester aktiver Wert,
  `state_class: measurement`, Attribute `ts`, `category`, `ref_min`, `ref_max`,
  `in_range`; stabiler `unique_id`-Suffix `lab_<marker>`) und ein
  Warn-Binary-Sensor je Kategorie (`device_class: problem`). Beide folgen dem
  neuen Bereichs-Schalter `areas.labs`.
- **Services** — `health_o_mat.add_lab_value` und
  `health_o_mat.remove_last_lab_value` (voidet den zeitlich neuesten aktiven
  Wert, kein Hard-Delete) mit `unknown_marker`-, `unit_required`- und
  `unsupported_unit`-Validierung.
- **UI** — eigene Lovelace-Karte `custom:health-o-mat-labs-card` (Kategorie-
  Reiter, In-Range-Badge, optionaler Trend, Bericht-Link, Eingabeformular;
  wird idempotent als Ressource registriert), ein vierter Panel-Tab mit
  Kategorie-Wischgeste, eine Übersichts-Kachelreihe und ein Admin-Bereich für
  Referenz-Overrides, ausgeblendete Kategorien, Custom-Marker und
  Feedback-Link. Katalog- und Kartentexte sind zweisprachig
  (`name_de`/`name_en`), inklusive medizinischem Disclaimer.
- **Datenportabilität** — Backup-Format **v3** mit Laborwerten und
  Labor-Optionen, Restore-Datensatz `lab_values` (inkl. First-wins-Merge von
  Custom-Markern und Validierung unbekannter Marker), CSV-Austausch als
  `lab_values.csv` sowie `lab_values` in Service-Schemas, WS-Export und
  Dataset-Auswahl der UI.

## 💥 Breaking changes

Keine. Der Release ist rein additiv: Store-Schema **v4 → v5** ergänzt
`lab_readings[]` und migriert beim Laden automatisch und idempotent, ohne
Datenverlust. Es gibt **keine** Config-Entry-Migration, und bestehende
`unique_id`s, Entity-IDs, Service-Payloads und Backup-Formate bleiben
unverändert (v1-/v2-Backups bleiben lesbar).

## Migration

1. Update über HACS installieren und Home Assistant neu starten.
2. Das Store-Schema migriert automatisch auf v5 — kein manueller Schritt.
   Ein Backup vor dem Update ist trotzdem empfohlen.
3. Laborwerte bei Bedarf über den Bereichs-Schalter `labs` (Options-Flow bzw.
   Admin-Bereich) aktivieren; die Entities entstehen danach automatisch.
4. Die optionale Aufbewahrung/Archivierung gilt bewusst **nicht** für
   Laborwerte (v1-Scope): `lab_readings` bleibt vollständig erhalten.
5. Wird ein Custom-Marker entfernt oder umbenannt, bleibt sein Entity-
   Registry-Eintrag als `unavailable` stehen und muss bei Bedarf manuell
   entfernt werden — Home Assistant löscht Entities nicht automatisch.

## Vollständiger Changelog

https://github.com/Popoboxxo/ha-health-o-mat/compare/v0.15.0...v0.16.0

---

# v0.16.0 — Lab values

## Summary

Minor release: adds **lab values as a fourth data domain** (alongside drinks,
blood pressure and wellbeing). Readings are captured in nine medical
categories — liver, kidney, electrolytes, lipids, thyroid, blood count,
inflammation, digestion and drug levels — plus "other" for custom markers. The
catalog ships 29 markers with typical adult guide ranges, per-person reference
overrides and bidirectional unit conversion. Values are available as native HA
entities, writable through services and portable via backup and CSV.

> ⚠️ The integration does not classify or diagnose medically. Reference ranges
> are guide values, not a clinical norm.

## ✨ New features

- **Lab values domain** — 29 markers across nine categories plus "other" for
  custom markers, each with a reference range (min/max, possibly one-sided),
  optional per-person overrides and per-category visibility. German lab aliases
  are resolved (`gpt` → `alt`, `got` → `ast`, `gamma_gt` → `ggt`).
- **Bidirectional unit conversion** — catalog unit plus one optional legacy
  unit pair per custom marker (e.g. `mg/dL` ↔ `µmol/L`). Values are stored
  canonically; the reported value and unit stay available as
  `reported_value`/`reported_unit`. `unit` is mandatory for markers prone to
  unit confusion.
- **`report_ref`** — optional link or external ID of the lab report (max. 500
  characters); the integration never calls the reference itself.
- **Entities** — one sensor per marker (state = most recent active value,
  `state_class: measurement`, attributes `ts`, `category`, `ref_min`,
  `ref_max`, `in_range`; stable `unique_id` suffix `lab_<marker>`) and one
  warning binary sensor per category (`device_class: problem`). Both follow the
  new `areas.labs` toggle.
- **Services** — `health_o_mat.add_lab_value` and
  `health_o_mat.remove_last_lab_value` (voids the most recent active reading,
  no hard delete) with `unknown_marker`, `unit_required` and
  `unsupported_unit` validation.
- **UI** — a dedicated `custom:health-o-mat-labs-card` (category tabs,
  in-range badge, optional trend, report link, entry form; registered as a
  Lovelace resource idempotently), a fourth panel tab with category swipe, an
  overview tile row and an admin section for reference overrides, hidden
  categories, custom markers and the feedback link. Catalog and card texts are
  bilingual (`name_de`/`name_en`), including the medical disclaimer.
- **Data portability** — backup format **v3** with lab values and lab options,
  restore dataset `lab_values` (including first-wins merge of custom markers
  and validation of unknown markers), CSV exchange as `lab_values.csv`, and
  `lab_values` in service schemas, WS export and the UI dataset selector.

## 💥 Breaking changes

None. The release is purely additive: store schema **v4 → v5** adds
`lab_readings[]` and migrates automatically and idempotently on load without
data loss. There is **no** config-entry migration, and existing `unique_id`s,
entity IDs, service payloads and backup formats are unchanged (v1/v2 backups
remain readable).

## Migration

1. Install the update via HACS and restart Home Assistant.
2. The store schema migrates automatically to v5 — no manual step. A backup
   before updating is still recommended.
3. Enable labs with the `labs` area toggle (options flow or admin area) if
   needed; entities are created afterwards automatically.
4. Retention/archiving deliberately does **not** apply to lab values (v1
   scope): `lab_readings` is kept in full.
5. If a custom marker is removed or renamed, its entity registry entry remains
   as `unavailable` and must be removed manually if desired — Home Assistant
   does not delete entities automatically.

## Full changelog

https://github.com/Popoboxxo/ha-health-o-mat/compare/v0.15.0...v0.16.0

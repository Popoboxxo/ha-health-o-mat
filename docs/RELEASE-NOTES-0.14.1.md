# v0.14.1 — Übersetzungs-Platzhalter-Fix

## Zusammenfassung

Patch-Release: behebt einen Übersetzungsfehler in der Service-Beschreibung
`restore_backup` (Personen-Zuordnung), den Home Assistant als ungültigen
Platzhalter validiert. Keine funktionalen Änderungen, keine Migration.

## 🐛 Fixed

- Die Service-Beschreibung `restore_backup.fields.person_map` enthält keine
  Platzhalter-Klammern mehr (`{Quelle: Ziel-Entry-ID}` /
  `{source: target entry ID}`). HA interpretierte sie als Platzhalter und
  meldete beim Setup einen Validierungsfehler im Log.
- Deutsche und englische Beschreibung sind wieder konsistent.
- Neue Tests prüfen, dass alle Übersetzungen nur gültige `{identifier}`-
  Platzhalter enthalten und dass die Platzhalter-Mengen zwischen
  `strings.json`, `de.json` und `en.json` übereinstimmen.

## 💥 Breaking changes

Keine. `unique_id`s, Entity-IDs, Store-Schema und Backup-Format bleiben
unverändert.

## Migration

Update über HACS installieren und Home Assistant neu starten. Kein weiterer
Schritt erforderlich. Der Versions-Bump dient nur der Cache-Busting- und
Release-Konsistenz.

## Vollständiger Changelog

https://github.com/Popoboxxo/ha-health-o-mat/compare/v0.14.0...v0.14.1

---

# v0.14.1 — Translation placeholder fix (English)

## Summary

Patch release: fixes a translation error in the `restore_backup` service
description (person mapping) that Home Assistant validated as an invalid
placeholder. No functional changes, no migration.

## 🐛 Fixed

- The `restore_backup.fields.person_map` service description no longer contains
  placeholder-like braces (`{Quelle: Ziel-Entry-ID}` /
  `{source: target entry ID}`). HA interpreted them as placeholders and logged
  a validation error during setup.
- German and English descriptions are consistent again.
- New tests ensure every translation only contains valid `{identifier}`
  placeholders and that placeholder sets match across `strings.json`, `de.json`
  and `en.json`.

## 💥 Breaking changes

None. `unique_id`s, entity IDs, store schema and backup format are unchanged.

## Migration

Install the update via HACS and restart Home Assistant. No further steps are
required; the version bump only keeps cache busting and release data in sync.

## Full changelog

https://github.com/Popoboxxo/ha-health-o-mat/compare/v0.14.0...v0.14.1

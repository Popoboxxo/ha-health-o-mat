# Changelog

All notable changes to HA Health-O-Mat are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/). Older releases are available on the
[GitHub releases page](https://github.com/Popoboxxo/ha-health-o-mat/releases).

## [0.17.1] — 2026-11-02

### Fixed

- **Quick-drink migration no longer fails on hand-renamed entities:** a single
  manually renamed entity (for example `sensor.caro_gewicht`) no longer collapses the
  shared device-anchor prefix. The prefix is now derived from tokens supported by at
  least two anchors and trimmed over the majority of the candidates, so a person whose
  entry stayed on `config entry v2` after `device_slug_ambiguous` migrates on the next
  start. All quick-drink buttons are migrated again instead of being skipped.
- **`custom_entity_id` is a warning, not a failure:** an entity whose id was renamed by
  hand keeps its id on purpose. It is reported in the migration summary as a warning and
  no longer blocks the pass (`recoverable` stays `True`, no `MIGRATION_ERROR`).
- **Diagnostics report orphaned lab entities:** the diagnostics download now compares the
  expected lab-marker `unique_id`s against the entity registry and lists entities that are
  no longer created (`lab_entity_orphans`, count plus items). The report is masked — the
  person and custom marker keys are redacted, values are never included.
- **Long-term statistics are cleared when a person is removed:** `async_remove_entry`
  removes the entry's entities' long-term statistics through the recorder API, so
  statistics of a deleted person no longer linger. When the recorder is not available the
  cleanup is skipped silently.

[0.17.1]: https://github.com/Popoboxxo/ha-health-o-mat/compare/v0.17.0...v0.17.1

## [0.17.0] — 2026-11-02

### 💥 Breaking changes — entity ids of quick-drink buttons and custom lab markers

- **Quick-drink buttons** are now registered by slot index instead of their label:
  `button.<device>_glas_wasser` → `button.<device>_quick_drink_1`,
  `…_flasche_wasser` → `…_quick_drink_2`, `…_tasse_kaffee` → `…_quick_drink_3`,
  `…_glas_saft` → `…_quick_drink_4` (1-based, order of the configured quick drinks).
- **Custom lab markers** are now registered from their stable key instead of the user
  text: `sensor.<device>_vitamin_d` → `sensor.<device>_lab_vitamin_d`,
  `…_hamoglobin` → `…_lab_h_moglobin` (the key is an ASCII slug).
- **You must update** automations, scripts, dashboards, scenes, helpers and template
  sensors that reference the old ids — Home Assistant does **not** rename references.
- **What stays:** `unique_id`, display names, device assignment, stored measurements and
  history. Recorder metadata (`states_meta`, `statistics_meta`) is rewritten to the new
  `entity_id`; the historical state rows themselves are untouched.
- **Automatic migration:** runs on the first start after the update (`config entry v2 → v3`).
  On an id collision the person is **not loaded** and the log lists the pairs; rename or
  remove the colliding entity and **restart Home Assistant completely** (a reload is
  blocked, the entry is marked unrecoverable).
- **Why a MINOR?** Deliberate decision: the migration is automatic and lossless and
  touches only two entity classes — but the break is real, so treat this section as
  mandatory reading.

### Added

- **Category validation for custom lab markers (REQ-HOM-130, A-1):** a category outside
  `LAB_CATEGORIES` falls back to `other` instead of producing an untranslated warning
  entity with a localized object id.
- **Marker key preservation (REQ-HOM-130, A-2):** a client that re-sends markers without a
  `key` now inherits the stored key when the name matches, so the `unique_id` cannot drift.
- **Drift regression test (REQ-HOM-130, A-3):** every wellbeing state's report-button
  translation is guarded in the master strings and both translations.

### Changed

- **English, language-independent `object_id`s (REQ-HOM-130):** quick-drink buttons and
  custom lab markers now derive their `entity_id` from the stable `unique_id` instead of the
  localized display name, so the ids no longer change with the Home Assistant system
  language. Existing persons are migrated by `async_migrate_entry` (`v2 → v3`) and freshly
  registered persons are pinned via `suggested_object_id`.
- **E2E regression for English object ids (REQ-HOM-130, A-4):** a live test asserts English
  object ids for a freshly registered person on a German-language instance, including the
  area-prefix case.

### Fixed

- **Mixed-language entity ids:** with a German system language, quick-drink buttons and
  custom lab markers could previously be registered with German label slugs; the migration
  resolves the divergence between fresh and migrated installations.

### Migration

1. Install the update via HACS and restart Home Assistant.
2. The config entry migrates automatically from `v2` to `v3` on the first start.
3. Update automations, scripts, dashboards, scenes, helpers and template sensors that use
   the old entity ids (see the table above). A backup before updating is recommended.
4. If the log reports an id collision, the person is not loaded: rename or remove the
   colliding entity and restart Home Assistant completely — a reload is blocked
   (`MIGRATION_ERROR`, `recoverable = False`).
5. After the release, check the device view for orphaned entities that are no longer
   created (for example warning entities for foreign categories, see A-1) and remove them
   manually — never by changing `unique_id`s.

[0.17.0]: https://github.com/Popoboxxo/ha-health-o-mat/compare/v0.16.2...v0.17.0

## [0.16.2] — 2026-10-31

### Added

- **Batch lab report check-in (REQ-HOM-123):** new `add_lab_report` service and
  WebSocket command record several lab values of one report in a single
  operation — one shared timestamp, one optional `report_ref`, all-or-nothing
  (one invalid row rejects the whole report, empty rows are ignored), tiered
  limits of 60 rows in the UI and 200 on the server, with row-level structured
  errors (`{code, params, message}`), duplicate-marker detection and
  `NaN`/`inf` hardening that also covers the single-value `add_lab_value` path.
- **Multi-row report dialog (REQ-HOM-123):** both the card and the panel lab
  tab gained a dialog that adds, edits and removes rows with hybrid filling
  ("all visible markers" / "recently used markers"), per-row unit dropdowns
  from `alt_units`, and a single-flight submit.
- **Batch undo (REQ-HOM-128):** symmetric `remove_lab_report` service and WS
  command void all active values of one timestamp (optionally narrowed by
  `report_ref`), with a separate audit entry, a confirmation step in the UI and
  individual restores via `restore_entry`.
- **Lab unit conversion column (REQ-HOM-124):** the admin lab section lists the
  legacy-unit × factor → canonical-unit conversion per marker (including custom
  markers), formats the factor through `formatNumber` and flags markers that
  require a unit with an "unit required" badge.
- **Panel disclaimer toggle (REQ-HOM-125):** the medical note in the panel lab
  tab is visible by default and can be hidden through the new
  `lab_hide_panel_disclaimer` option, transported via `panel_data`; an empty
  state covers the "all categories hidden" case and the card disclaimer is now
  localised (German/English).
- **Lab retention (REQ-HOM-129):** new independent `lab_retention_months`
  option (0–120, default 0 = off, keeps the previous behaviour) that voids lab
  readings older than the configured window on setup with
  `void_reason: retention`, without an archive and without touching the
  drink/blood-pressure retention.
- **Example labs dashboard (REQ-HOM-126):** `examples/dashboard-labs-card.yaml`
  shows the labs card in a ready-to-use dashboard, referenced from the README
  and covered by the dashboard tests.
- **Voided lab rows in export/import (REQ-HOM-129):** `lab_values.csv` now
  includes voided rows with `voided_at`/`void_reason`; re-import skips them
  explicitly, header-based, so older files without these columns keep the
  positional behaviour.

### Fixed

- **Hybrid report buttons:** the card and panel report buttons now pass the
  config-entry id and the report dialog stays open after a validation error
  instead of closing and discarding the entered rows.

### Changed

- Documentation covers the batch extension: the README, the service reference,
  the options wizard (lab retention) and the admin section now describe the
  report services, the conversion column, the disclaimer toggle and the voided
  export rows, and the stated unit test count is 1500.
- No breaking changes: data model stays at store schema v5, no config-entry
  migration, no changes to `unique_id`s or entity IDs, and backup/restore
  compatibility is unchanged (backup options are additive).

[0.16.2]: https://github.com/Popoboxxo/ha-health-o-mat/compare/v0.16.1...v0.16.2

## [0.16.1] — 2026-10-31

### Added

- **`lab_values` in the void and restore services (REQ-HOM-122):** `void_entry`
  and `restore_entry` accept `kind: lab_values`, so the last lab reading of a
  person can be voided and lab datasets can be restored through the services
  instead of the UI only.

### Fixed

- **Lab values missing from the restore selectors:** the `restore_backup`
  dataset selector, the service schema and the panel restore list now offer
  `lab_values`, matching the dataset set the backup format, CSV export and UI
  already used.

### Changed

- Documentation aligned with the four data domains: the README hero, feature
  list, options wizard, entity tables, dashboard examples, card, panel, admin,
  backup/import and E2E chapters now cover lab values, and the unit test count
  is stated as 1395.

[0.16.1]: https://github.com/Popoboxxo/ha-health-o-mat/compare/v0.16.0...v0.16.1

## [0.16.0] — 2026-10-31

### Added

- **Lab values as a fourth data domain (REQ-HOM-122):** lab readings in nine
  medical categories (liver, kidney, electrolytes, lipids, thyroid, blood
  count, inflammation, digestion, drug levels) plus "other" for custom markers.
  The catalog ships 29 markers with default reference ranges (typical adult
  guide values, not a clinical norm), per-person reference overrides,
  per-category visibility, German name aliases (GPT/GOT/Gamma-GT) and
  bidirectional unit conversion (catalog units plus one optional legacy unit
  pair per custom marker). Values are stored canonically, the reported value
  and unit are kept as `reported_value`/`reported_unit`. An optional
  `report_ref` links a reading to a lab report.
- **Lab entities:** one sensor per marker and one warning binary sensor per
  category. Both are controlled by the new `areas.labs` toggle (options flow
  and admin area checkbox).
- **Lab services:** `add_lab_value` and `remove_last_lab_value`, including
  alias resolution and `unknown_marker` / `unit_required` /
  `unsupported_unit` validation.
- **Lab UI:** a dedicated `health-o-mat-labs-card`, a panel tab with a
  category swipe bar, an overview tile row, an admin section for reference
  overrides, hidden categories, custom markers and the feedback link, plus
  bilingual catalog names (`name_de`/`name_en`) and a medical disclaimer in
  card, panel and README.
- **Lab data portability:** backup format v3, restore dataset `lab_values`
  (including first-wins merge of custom markers and per-record validation on
  unknown markers), CSV export/import as `lab_values.csv`, and `lab_values`
  in the service schemas, WS export and UI dataset selector.

### Changed

- Store schema v4 → v5 (additive `lab_readings[]`); existing data is migrated
  on load without loss. No config-entry migration and no changes to existing
  `unique_id`s, entity IDs or backup compatibility (v1/v2 backups remain
  readable).

[0.16.0]: https://github.com/Popoboxxo/ha-health-o-mat/compare/v0.15.0...v0.16.0

## [0.15.0] — 2026-10-26

### Added

- **Wellbeing number input:** new `number.…_wellbeing_input` entity (1–10,
  step 1) that reports the same status as the wellbeing select and the report
  buttons, so the history and `wellbeing_score` stay consistent when the value
  is entered numerically.

[0.15.0]: https://github.com/Popoboxxo/ha-health-o-mat/compare/v0.14.1...v0.15.0

## [0.14.1] — 2026-10-26

### Fixed

- Removed placeholder-like braces from the `restore_backup` person-mapping
  service description (German and English), which Home Assistant validated as
  invalid placeholders and logged during setup.
- Added tests for valid placeholders and cross-language placeholder parity.

[0.14.1]: https://github.com/Popoboxxo/ha-health-o-mat/compare/v0.14.0...v0.14.1

## [0.14.0] — 2026-10-26

### Added

- **History, corrections and audit:** per-person history for drinks, blood
  pressure and wellbeing; filter active/deleted; inline delete confirmation;
  restore; undo for all three types. Deletions are voided (never hard-deleted
  in the UI) and recorded in an append-only audit log. Audit cap defaults to
  1000 events per person and can be set to unlimited in the admin settings.
- **Backup restore:** merge (default) or replace, partial restore by person,
  dataset and date range, dry-run, person mapping, automatic pre-restore
  backup. Backup v2 includes the retention archive; v1 backups remain readable.
- **German/English UI:** panel, card, editor and admin follow `hass.language`
  via HA-native `common` translations, with a German fallback.
- **Reminders, weekly report and blueprints:** configurable reminders (time,
  days, notify service, quiet hours, conditions), weekly report as a Markdown
  notification (no file), `notify.*` with persistent fallback, and three
  automation blueprints.
- **Options wizard:** menu with optional sections (basics, drinks, wellbeing,
  notifications), skip, defaults and a merge-preserving summary.
- **Backdating:** drinks, blood pressure and wellbeing with a freely chosen
  timestamp (unlimited past, never future), plus “Now/Yesterday” presets.
- **Admin UI:** restore card with dry-run/`REPLACE` confirmation and an
  `audit_limit` field.

### Changed

- Deleting an entry now means **void**; `remove_last_entry` voids the last
  active entry instead of removing it (and supports `wellbeing`).
- CSV export contains active entries by default.
- Backup format v2 (additive); v1 backups are still read.
- Store schema v4 is migrated automatically on startup (IDs, `created_at`,
  void fields, audit log, wellbeing event list).

### Fixed

- Multi-source replace restores aggregate all sources per target and keep
  dry-run counts truthful.
- The archive store is loaded independently of retention, so backups,
  exports and restores include archived periods.
- Restore timestamps, deduplication and range filters are normalised to UTC;
  naive values use the local HA timezone.
- Notify delivery failure falls back to persistent notifications.
- Lifetime and retention writes are protected against partial failures.
- Replace validates records like merge; audit details no longer contain health
  values.
- Restore accepts JSON files from both the import and export folders.
- Partial `areas` updates no longer reactivate disabled areas.
- Export and backup services are admin-gated.

### Migration

1. Install the update via HACS and restart Home Assistant.
2. The store schema migrates automatically and idempotently to v4; create a
   backup first.
3. Existing v1 backups remain importable; new backups are written as v2.
4. Blueprints are not installed by HACS and must be imported manually if needed.
5. Recorder long-term statistics are not adjusted retroactively for corrections
   (documented limitation).

[0.14.0]: https://github.com/Popoboxxo/ha-health-o-mat/compare/v0.13.0...v0.14.0

## [0.13.0] — 2026-10-25

### Added

- Optional confirmation before a wellbeing report: a per-person panel/server
  option and an independent card option, both defaulting to off.
- The confirmation button only appears while a selection is staged.

[0.13.0]: https://github.com/Popoboxxo/ha-health-o-mat/releases/tag/v0.13.0

## [0.12.0] — 2026-10-23

### Fixed

- Undo is disabled when no drink booking exists.
- Card editor person filter has an explicit edit mode.
- Panel admin offers custom images for all ten wellbeing keys.

[0.12.0]: https://github.com/Popoboxxo/ha-health-o-mat/releases/tag/v0.12.0

## [0.10.1] — 2026-10-21

### Fixed

- Wellbeing history stamps the replaced status with its own report timestamp.

[0.10.1]: https://github.com/Popoboxxo/ha-health-o-mat/releases/tag/v0.10.1

## [0.10.0] — 2026-10-21

### Added

- Configurable Lovelace card with display/input flags, drink filters, manual
  amounts and person modes.
- Public `health_o_mat.set_wellbeing` service.

[0.10.0]: https://github.com/Popoboxxo/ha-health-o-mat/releases/tag/v0.10.0

## Older releases

See the [GitHub releases page](https://github.com/Popoboxxo/ha-health-o-mat/releases).

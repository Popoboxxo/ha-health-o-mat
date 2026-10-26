# Changelog

All notable changes to HA Health-O-Mat are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/). Older releases are available on the
[GitHub releases page](https://github.com/Popoboxxo/ha-health-o-mat/releases).

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

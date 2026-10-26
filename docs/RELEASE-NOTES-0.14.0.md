# v0.14.0 — Korrigierbarkeit, Restore & mehr

## Zusammenfassung

0.14.0 macht das Gesundheits-Tagebuch korrigierbar und vertrauenswürdiger:
Einträge lassen sich im Verlauf löschen (Void) und wiederherstellen, Backups
können validiert zurückgespielt werden, die UI folgt der HA-Sprache (de/en),
und Erinnerungen, Wochenbericht, ein Options-Wizard sowie Rückdatieren sind
neu. Bestehende Daten und Entity-IDs bleiben unverändert.

## ✨ New features

- **Verlauf & Korrekturen** — Verlauf je Person/Tab, Filter „Nur aktive/Auch
  gelöscht“, Löschen mit Inline-Bestätigung, Wiederherstellen; Undo für
  Getränke, Blutdruck und Wohlbefinden.
- **Audit-Log** — append-only Ereignisse (wer/was/wann), Default-Cap 1000
  Ereignisse pro Person; im Admin auf `0` = unbegrenzt stellbar.
- **Backup-Restore** — Merge (Default) oder Replace, Teil-Restore nach Person,
  Datensatz und Zeitraum, Dry-Run, Personen-Mapping, automatisches
  Pre-Restore-Backup. Backup v2 enthält jetzt auch das Retention-Archiv;
  v1-Backups bleiben lesbar.
- **Deutsch/Englisch** — Panel, Karte, Editor und Admin folgen
  `hass.language`; HA-native `common`-Translations, deutscher Fallback.
- **Erinnerungen & Wochenbericht** — konfigurierbare Reminder (Zeit, Tage,
  Notify-Service, Quiet Hours, Bedingungen), Wochenbericht als
  Markdown-Notification (keine Datei), `notify.*` mit persistentem Fallback.
- **Blueprints** — Abend-Erinnerung, Blutdruck-Warnung, Wochenbericht unter
  `blueprints/automation/health_o_mat/`.
- **Options-Wizard** — Menü mit optionalen Schritten (Grundlagen, Getränke,
  Wohlbefinden, Benachrichtigungen), Skip, Defaults und Zusammenfassung.
- **Rückdatieren** — Getränke, Blutdruck und Wohlbefinden mit frei wählbarem
  Zeitpunkt (unbegrenzt zurück, nie in die Zukunft); „Jetzt/Gestern“ als
  Schnellwahl.
- **Admin-UI** — Restore-Karte mit Dry-Run/REPLACE-Bestätigung und
  `audit_limit`-Feld.

## 💥 Breaking changes

- **Löschen ist jetzt „Void“**, kein Hard-Delete in der UI: Der Eintrag bleibt
  im Store/Audit/Backup erhalten, zählt aber nicht mehr in Auswertungen.
  Wiederherstellen ist jederzeit möglich.
- **`remove_last_entry` voidet** den letzten aktiven Eintrag, statt ihn zu
  entfernen (Semantikänderung; `kind` unterstützt jetzt auch `wellbeing`).
- **CSV-Export** enthält standardmäßig nur aktive (nicht gelöschte) Einträge.
- **Backup-Format v2** (additiv). v1-Backups werden weiterhin gelesen.
- **Store-Schema v4** wird beim Start automatisch migriert (IDs,
  `created_at`, Void-Felder, Audit-Log, Wellbeing-Ereignisliste).
- **Recorder-Langzeitstatistik** wird bei Korrekturen nicht rückwirkend
  angepasst (dokumentierte Grenze).
- **Keine Änderung** an `unique_id`s, Entity-IDs oder Config-Entry-Daten.

## Migration

1. Update über HACS installieren und Home Assistant neu starten.
2. Das Store-Schema wird automatisch und idempotent auf v4 migriert; vorher
   ein Backup erstellen.
3. Bestehende Backups (v1) bleiben importierbar; neue Backups werden als v2
   geschrieben.
4. Blueprints sind nicht Teil der HACS-Installation und müssen bei Bedarf
   manuell importiert werden.

## Vollständiger Changelog

https://github.com/Popoboxxo/ha-health-o-mat/compare/v0.13.0...v0.14.0

---

# v0.14.0 — Corrections, restore & more (English)

## Summary

0.14.0 makes the health diary correctable and more trustworthy: entries can be
voided and restored from the history, backups can be restored with validation,
the UI follows the HA language (de/en), and reminders, a weekly report, an
options wizard and backdating are new. Existing data and entity IDs stay
unchanged.

## ✨ New features

- **History & corrections** — per-person history, “active only / include
  deleted” filter, inline delete confirmation, restore; undo for drinks,
  blood pressure and wellbeing.
- **Audit log** — append-only events (who/what/when), default cap of 1000
  events per person; admins can set `0` for unlimited.
- **Backup restore** — merge (default) or replace, partial restore by person,
  dataset and date range, dry-run, person mapping, automatic pre-restore
  backup. Backup v2 now includes the retention archive; v1 backups remain
  readable.
- **German/English** — panel, card, editor and admin follow `hass.language`;
  HA-native `common` translations with a German fallback.
- **Reminders & weekly report** — configurable reminders (time, days, notify
  service, quiet hours, conditions), weekly report as a Markdown notification
  (no file), `notify.*` with persistent fallback.
- **Blueprints** — evening reminder, blood pressure warning, weekly report in
  `blueprints/automation/health_o_mat/`.
- **Options wizard** — menu with optional sections (basics, drinks, wellbeing,
  notifications), skip, defaults and a summary.
- **Backdating** — drinks, blood pressure and wellbeing with a freely chosen
  timestamp (unlimited past, never future); “Now/Yesterday” quick presets.
- **Admin UI** — restore card with dry-run/REPLACE confirmation and an
  `audit_limit` field.

## 💥 Breaking changes

- **Deleting now means “void”**, no hard delete in the UI: the entry remains in
  the store/audit/backup but no longer counts in derived values. It can be
  restored at any time.
- **`remove_last_entry` voids** the last active entry instead of removing it
  (semantic change; `kind` now also supports `wellbeing`).
- **CSV export** contains active (non-voided) entries by default.
- **Backup format v2** (additive). v1 backups are still read.
- **Store schema v4** is migrated automatically on startup (IDs,
  `created_at`, void fields, audit log, wellbeing event list).
- **Recorder long-term statistics** are not adjusted retroactively for
  corrections (documented limitation).
- **No changes** to `unique_id`s, entity IDs or config-entry data.

## Migration

1. Install the update via HACS and restart Home Assistant.
2. The store schema is migrated automatically and idempotently to v4; create a
   backup first.
3. Existing v1 backups remain importable; new backups are written as v2.
4. Blueprints are not installed by HACS and must be imported manually if
   needed.

## Full changelog

https://github.com/Popoboxxo/ha-health-o-mat/compare/v0.13.0...v0.14.0

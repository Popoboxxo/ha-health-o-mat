# v0.17.1 — Migrationsfehler behoben, Orphan-Diagnose

## Zusammenfassung

Patch-Release: Es behebt den produktiven Migrationsfehler aus 0.17.0, bei dem eine
einzige manuell umbenannte Entity das gemeinsame Anker-Präfix der Person leerte.
Dadurch wurden **alle Quick-Drink-Buttons übersprungen** (`device_slug_ambiguous`)
und der Config-Entry blieb auf Version 2 stehen. Zusätzlich meldet die
Diagnostics-Download-Datei verwaiste Labor-Entities und das Entfernen einer Person
räumt deren Langzeitstatistiken auf.

> ✅ **Handlungshinweis — nur für Betroffene:** Wer nach dem Update auf 0.17.0 im
> Log `device_slug_ambiguous` gesehen hat (typischer Fall: eine Entity wie
> `sensor.caro_gewicht` wurde von Hand umbenannt), muss **nichts weiter tun**, als
> auf 0.17.1 zu updaten und Home Assistant **neu zu starten**. Die betroffenen
> Config-Entries stehen noch auf **Version 2** — sie migrieren beim nächsten Start
> automatisch auf Version 3, und die Quick-Drink-Buttons werden angelegt.

## Fixed

### Migrationsfehler bei manuell umbenannten Entities

Das Anker-Präfix des Geräts (z. B. `health_o_mat_caro`) wurde bisher aus **allen**
Ankern gebildet. Eine einzige von Hand umbenannte Entity (etwa
`sensor.caro_gewicht` statt `sensor.health_o_mat_caro_gewicht`) leerte das
gemeinsame Präfix; die Migration brach mit `device_slug_ambiguous` ab und
übersprang **jeden** Quick-Drink-Button. Der Entry fiel auf
`state.recoverable = False` und blieb auf Version 2 (`MIGRATION_ERROR`).

Der Fix leitet das Präfix jetzt aus den Token ab, die von **mindestens zwei
Ankern** gestützt werden, und trimmt die Präfix-Grenze über die **Mehrheit** der
relevanten Kandidaten. Eine einzelne Ausnahme kippt die Auflösung damit nicht
mehr.

### `custom_entity_id` ist eine Warnung, kein Fehlschlag

Eine Entity, deren `entity_id` von Hand umbenannt wurde, behält ihre ID — das ist
eine bewusste Nutzerentscheidung. Sie wird im Migrations-Ergebnis als **Warnung**
gemeldet und blockiert den Durchlauf nicht mehr. Es gibt keinen
`MIGRATION_ERROR` und `recoverable` bleibt `True`.

### Orphan-Diagnose für Labor-Entities

Der Diagnostics-Download enthält jetzt die Sektion `lab_entity_orphans`: Die
erwarteten `unique_id`s der Labor-Marker werden gegen die Entity-Registry
verglichen; Entities, die nicht mehr erzeugt werden, erscheinen mit Anzahl und
Einträgen. Der Bericht ist **maskiert** — Personen- und Marker-Schlüssel sind
unkenntlich gemacht, Messwerte sind nie enthalten. Damit lassen sich
Alt-Entities aus 0.17.0 finden, bevor sie manuell entfernt werden.

### Langzeitstatistiken beim Entfernen einer Person

`async_remove_entry` löscht die Langzeitstatistiken der Entities des Entrys über
die Recorder-API. Wird eine Person entfernt, bleiben keine verwaisten
Statistiken zurück. Ist der Recorder nicht verfügbar, wird der Cleanup still
übersprungen.

## Upgrade

1. Update über HACS installieren.
2. Home Assistant **vollständig neu starten** (ein Reload reicht nicht).
3. Betroffene Entries migrieren automatisch von Version 2 auf Version 3.
4. Im Log prüfen: `custom_entity_id`-Warnungen sind erwartbar und harmlos —
   die betroffene Entity behält ihre manuell vergebene ID.
5. Optional: Diagnostics herunterladen und `lab_entity_orphans` prüfen; verwaiste
   Entities in der **Geräteansicht** entfernen — nie durch Ändern der `unique_id`.

## Kompatibilität

- Keine Änderung an `unique_id`s, am Store-Schema oder an Entity-IDs.
- Keine neuen Pflichtschritte für Installationen, die 0.17.0 fehlerfrei
  migriert haben.
- `config entry v2 → v3` bleibt der einzige Migrationsschritt.

## Vollständiger Changelog

https://github.com/Popoboxxo/ha-health-o-mat/compare/v0.17.0...v0.17.1

---

# v0.17.1 — Migration failure fixed, orphan diagnostics

## Summary

Patch release: it fixes the production migration failure from 0.17.0 where a
single hand-renamed entity collapsed the person's shared anchor prefix. As a
result **all quick-drink buttons were skipped** (`device_slug_ambiguous`) and the
config entry stayed on version 2. In addition, the diagnostics download now
reports orphaned lab entities, and removing a person clears their long-term
statistics.

> ✅ **Action required — only if affected:** if you saw `device_slug_ambiguous` in
> the log after updating to 0.17.0 (typical case: an entity such as
> `sensor.caro_gewicht` was renamed by hand), you do **not** need to do anything
> else but update to 0.17.1 and **restart Home Assistant**. The affected config
> entries are still on **version 2** — they migrate to version 3 automatically on
> the next start, and the quick-drink buttons are created.

## Fixed

### Migration failure on hand-renamed entities

The device anchor prefix (e.g. `health_o_mat_caro`) used to be derived from
**all** anchors. A single hand-renamed entity (for example
`sensor.caro_gewicht` instead of `sensor.health_o_mat_caro_gewicht`) emptied the
shared prefix; the migration aborted with `device_slug_ambiguous` and skipped
**every** quick-drink button. The entry ended up with
`state.recoverable = False` and stayed on version 2 (`MIGRATION_ERROR`).

The fix now derives the prefix from the tokens supported by **at least two
anchors** and trims the prefix boundary over the **majority** of the relevant
candidates. A single outlier therefore no longer breaks the resolution.

### `custom_entity_id` is a warning, not a failure

An entity whose `entity_id` was renamed by hand keeps its id — that is a
deliberate user decision. It is reported as a **warning** in the migration result
and no longer blocks the pass. There is no `MIGRATION_ERROR` and `recoverable`
stays `True`.

### Orphan diagnostics for lab entities

The diagnostics download now contains the `lab_entity_orphans` section: the
expected lab-marker `unique_id`s are compared against the entity registry;
entities that are no longer created are listed with a count and their items. The
report is **masked** — person and marker keys are redacted, measured values are
never included. This makes old entities from 0.17.0 findable before they are
removed manually.

### Long-term statistics cleared when a person is removed

`async_remove_entry` deletes the entry's entities' long-term statistics through
the recorder API. Removing a person therefore leaves no orphaned statistics
behind. If the recorder is not available, the cleanup is skipped silently.

## Upgrade

1. Install the update via HACS.
2. **Restart Home Assistant completely** (a reload is not enough).
3. Affected entries migrate from version 2 to version 3 automatically.
4. Check the log: `custom_entity_id` warnings are expected and harmless — the
   affected entity keeps the id you assigned manually.
5. Optional: download diagnostics and check `lab_entity_orphans`; remove orphaned
   entities in the **device view** — never by changing `unique_id`s.

## Compatibility

- No change to `unique_id`s, the store schema or entity ids.
- No mandatory extra steps for installations that migrated to 0.17.0 without
  errors.
- `config entry v2 → v3` remains the only migration step.

## Full changelog

https://github.com/Popoboxxo/ha-health-o-mat/compare/v0.17.0...v0.17.1

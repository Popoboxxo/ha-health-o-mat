# v0.17.0 — Sprachunabhängige Entity-IDs

## Zusammenfassung

Minor-Release: Quick-Drink-Buttons und Custom-Labor-Marker werden ab dieser
Version aus ihrer stabilen `unique_id` abgeleitet statt aus dem (lokalisierten)
Anzeigenamen. Dadurch wechselt die `entity_id` nicht mehr mit der
Home-Assistant-Systemsprache und ist für frisch angelegte wie für migrierte
Personen identisch. Bestehende Installationen werden beim ersten Start
automatisch migriert.

> ⚠️ **Das ist ein Bruch, obwohl es ein Minor-Sprung ist.** Die Migration läuft
> automatisch und verlustfrei, ändert aber `entity_id`s. Lies den Abschnitt
> „💥 Breaking changes" vollständig, bevor du aktualisierst.

## 💥 Breaking changes

Die `entity_id` zweier Entity-Klassen ändert sich. Home Assistant benennt
Verweise in Automationen, Skripten, Dashboards, Szenen und Helfern **nicht**
automatisch um — diese musst du selbst anpassen.

### Was sich ändert

**Standard-Quick-Drinks** (1-basiert, in der Reihenfolge der konfigurierten
Quick-Drinks):

| Bisherige ID (Beispiel) | Neue ID (Beispiel) |
|---|---|
| `button.health_o_mat_max_glas_wasser` | `button.health_o_mat_max_quick_drink_1` |
| `button.health_o_mat_max_flasche_wasser` | `button.health_o_mat_max_quick_drink_2` |
| `button.health_o_mat_max_tasse_kaffee` | `button.health_o_mat_max_quick_drink_3` |
| `button.health_o_mat_max_glas_saft` | `button.health_o_mat_max_quick_drink_4` |

Die alte ID hing am **Label** des Buttons; nach einer Label-Änderung blieb sie
stehen. Deshalb leitet die Migration das neue Suffix ausschließlich aus dem
Index in der `unique_id` (`{entry_id}_button_quick_{index}`, 0-basiert) ab:
`quick_drink_{index + 1}`.

**Custom-Labor-Marker** werden künftig aus ihrem stabilen `key` statt aus dem
Nutzertext gebildet: `sensor.<device>_<name-slug>` → `sensor.<device>_lab_<key>`.
Der `key` ist ein ASCII-Slug, kann also vom Anzeigenamen abweichen:

| Anzeigename | Neuer Key / neue ID |
|---|---|
| „Vitamin D" | `vitamin_d` → `sensor.…_lab_vitamin_d` |
| „Ferritin gesamt" | `ferritin_gesamt` → `sensor.…_lab_ferritin_gesamt` |
| „Hämoglobin" | `h_moglobin` → `sensor.…_lab_h_moglobin` |

Ist der `key` nicht slug-sicher (z. B. ein Fremd-Client sendet explizit
`"key": "Vitamin D"`), wird die Entity **nicht** migriert (`skip`, Grund
`invalid_key`) — eine stille Umformung des Keys ist verboten, weil die
`unique_id` unverändert bleiben muss.

### Was Nutzer anpassen müssen

- **Automationen** und **Skripte**, die die alten `entity_id`s auslösen oder
  auslesen
- **Dashboards** (Lovelace-Karten, Entitäten-Karten, Template-Karten)
- **Szenen**, **Helfer** (z. B. Gruppen, Template-Sensoren) und
  **Template-Sensoren**, die alte IDs referenzieren

Suche am besten projektweit nach den alten Suffixen (`glas_wasser`,
`flasche_wasser`, `tasse_kaffee`, `glas_saft`) bzw. nach
`sensor.<device>_<name-slug>` bei Custom-Markern und ersetze sie durch die
neuen IDs.

### Was erhalten bleibt

- **`unique_id`** — unverändert (die Identität der Entity)
- **Anzeigename** (`original_name`) und Gerätezuordnung — unverändert
- **Verlauf und Statistik** — die Recorder-Metadaten (`states_meta`,
  `statistics_meta`) werden auf die neue `entity_id` umgeschrieben, die
  historischen Zustandszeilen selbst bleiben unverändert
- **Store und Messdaten** — unberührt (keine Datenmigration, keine Änderung
  der Store-Schema-Version)
- Bereits konforme IDs (Katalog-Labor-Marker, Kategorie-Warnungen,
  Wellbeing-Buttons) bleiben unverändert

## Migrationsmechanik

Die Migration läuft automatisch beim ersten Start nach dem Update
(`config entry v2 → v3`). Es gibt keinen manuellen Schritt.

Bei einer **ID-Kollision** (die Ziel-ID ist bereits von einer anderen Entity
belegt) wird die betroffene Person **nicht geladen**. Das Log nennt die
kollidierenden Paare. Auflösung:

1. Die kollidierende Entity umbenennen oder entfernen.
2. Home Assistant **vollständig neu starten** — ein Reload reicht nicht.

### `MIGRATION_ERROR` ist nicht wiederherstellbar

Weil der Release bewusst als MINOR erscheint, hier explizit: Nach einer
Kollision steht der Config-Entry auf `state.recoverable = False`; Reload und
Unload sind gesperrt. **Nur ein vollständiger Home-Assistant-Neustart**
wiederholt die Migration. Die Migration ist idempotent — ein zweiter Lauf ohne
Änderungen erzeugt keinen Diff.

## Post-Release-Cleanup

Durch die Kategorie-Validierung (A-1) werden Warn-Entities für Kategorien
außerhalb von `LAB_CATEGORIES` nicht mehr angelegt. Bereits registrierte
Alt-Entities können dadurch als **Orphans** zurückbleiben.

Nach dem Release in der **Geräteansicht** prüfen (nicht nur in der
Entitäten-Liste) und nicht mehr erzeugte Entities manuell entfernen. `unique_id`s
werden dabei **nie** geändert — verwaiste Entities werden entfernt, nicht
umgebogen.

## Weitere Änderungen

- **A-1 — Kategorie-Validierung (REQ-HOM-130):** Unbekannte Kategorien bei
  Custom-Labor-Markern fallen auf `other` zurück.
- **A-2 — Key-Erhalt (REQ-HOM-130):** Keylose Marker-Einträge erben den gespeicherten Key,
  wenn der Name exakt übereinstimmt; der `unique_id` kann nicht mehr driften.
- **A-3 — Drift-Test (REQ-HOM-130):** Für jeden Wellbeing-State wird die
  `report_*`-Übersetzung in Master, `de` und `en` abgesichert.
- **A-4 — E2E-Regression (REQ-HOM-130):** Ein Live-Test prüft englische `object_id`s bei
  Systemsprache `de` inklusive Area-Präfix-Fall.

## Vollständiger Changelog

https://github.com/Popoboxxo/ha-health-o-mat/compare/v0.16.2...v0.17.0

---

# v0.17.0 — Language-independent entity ids

## Summary

Minor release: quick-drink buttons and custom lab markers are now derived from
their stable `unique_id` instead of the (localized) display name. Their
`entity_id` therefore no longer changes with the Home Assistant system
language and is identical for freshly created and migrated persons. Existing
installations migrate automatically on the first start.

> ⚠️ **This is a break, even though it is a minor bump.** The migration runs
> automatically and losslessly but changes `entity_id`s. Read the
> "💥 Breaking changes" section in full before updating.

## 💥 Breaking changes

The `entity_id` of two entity classes changes. Home Assistant does **not**
rename references in automations, scripts, dashboards, scenes or helpers —
you have to update them yourself.

### What changes

**Standard quick drinks** (1-based, in the order of the configured quick
drinks):

| Previous id (example) | New id (example) |
|---|---|
| `button.health_o_mat_max_glas_wasser` | `button.health_o_mat_max_quick_drink_1` |
| `button.health_o_mat_max_flasche_wasser` | `button.health_o_mat_max_quick_drink_2` |
| `button.health_o_mat_max_tasse_kaffee` | `button.health_o_mat_max_quick_drink_3` |
| `button.health_o_mat_max_glas_saft` | `button.health_o_mat_max_quick_drink_4` |

The previous id was tied to the button **label**; it stayed put after a label
change. The migration therefore derives the new suffix only from the index in
the `unique_id` (`{entry_id}_button_quick_{index}`, 0-based):
`quick_drink_{index + 1}`.

**Custom lab markers** are now built from their stable `key` instead of the
user text: `sensor.<device>_<name-slug>` → `sensor.<device>_lab_<key>`. The
`key` is an ASCII slug and may differ from the display name:

| Display name | New key / new id |
|---|---|
| "Vitamin D" | `vitamin_d` → `sensor.…_lab_vitamin_d` |
| "Ferritin gesamt" | `ferritin_gesamt` → `sensor.…_lab_ferritin_gesamt` |
| "Hämoglobin" | `h_moglobin` → `sensor.…_lab_h_moglobin` |

If the `key` is not slug-safe (e.g. a foreign client explicitly sends
`"key": "Vitamin D"`), the entity is **not** migrated (`skip`, reason
`invalid_key`) — silently reshaping the key is forbidden because the
`unique_id` must stay unchanged.

### What you must update

- **Automations** and **scripts** that trigger or read the old `entity_id`s
- **Dashboards** (Lovelace entity cards, template cards)
- **Scenes**, **helpers** (e.g. groups, template sensors) and **template
  sensors** that reference the old ids

Search your configuration for the old suffixes (`glas_wasser`,
`flasche_wasser`, `tasse_kaffee`, `glas_saft`) and for
`sensor.<device>_<name-slug>` on custom markers, and replace them with the new
ids.

### What stays

- **`unique_id`** — unchanged (the identity of the entity)
- **Display name** (`original_name`) and device assignment — unchanged
- **History and statistics** — recorder metadata (`states_meta`,
  `statistics_meta`) is rewritten to the new `entity_id`, while the historical
  state rows themselves stay unchanged
- **Store and measurements** — untouched (no data migration, no store schema
  change)
- Already conformant ids (catalog lab markers, category warnings, wellbeing
  buttons) stay unchanged

## Migration mechanics

The migration runs automatically on the first start after the update
(`config entry v2 → v3`). There is no manual step.

On an **id collision** (the target id is already taken by another entity) the
affected person is **not loaded**. The log lists the colliding pairs.
Resolution:

1. Rename or remove the colliding entity.
2. **Restart Home Assistant completely** — a reload is not enough.

### `MIGRATION_ERROR` is not recoverable

Because the release deliberately ships as a MINOR, to be explicit: after a
collision the config entry has `state.recoverable = False`; reload and unload
are blocked. **Only a full Home Assistant restart** retries the migration. The
migration is idempotent — a second run without changes produces no diff.

## Post-release cleanup

Category validation (A-1) no longer creates warning entities for categories
outside `LAB_CATEGORIES`. Previously registered old entities may therefore
remain as **orphans**.

After the release, check the **device view** (not just the entity list) and
remove entities that are no longer created. `unique_id`s are **never** changed
in the process — orphaned entities are removed, not repointed.

## Other changes

- **A-1 — Category validation (REQ-HOM-130):** unknown categories on custom lab markers fall
  back to `other`.
- **A-2 — Key preservation (REQ-HOM-130):** keyless marker entries inherit the stored key
  when the name matches exactly, so the `unique_id` can no longer drift.
- **A-3 — Drift test (REQ-HOM-130):** every wellbeing state's `report_*` translation is
  guarded in the master, `de` and `en`.
- **A-4 — E2E regression (REQ-HOM-130):** a live test asserts English `object_id`s on a
  German-language instance, including the area-prefix case.

## Full changelog

https://github.com/Popoboxxo/ha-health-o-mat/compare/v0.16.2...v0.17.0

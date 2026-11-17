# v0.22.1 — Panel-Performance, „Zurück zu Home Assistant"-Button, E2E-CSV-Export

## Zusammenfassung

Patch-Release mit Bugfixes und Verbesserungen, die im Panel und im E2E-Stack
anfallen. Das Panel rendert deutlich schneller (HTML-Memoisierung statt
DOM-Neuaufbau), ein neuer Topbar-Button führt zurück zu Home Assistant, und der
E2E-Runner mountet jetzt den HA-Config-Ordner, damit die CSV-Export-Tests im
Container die Datei lesen können. Der Release ist **ohne Breaking Changes**: es
gibt keine Migration, keinen `async_migrate_entry`-Schritt und keinen
Store-/Backup-Schema-Bump.

> ℹ️ **Hinweis — bitte nach dem Update lesen.** Panel und Karte werden mit einem
> neuen Cache-Buster (`?v=0.22.1`, `PANEL_VERSION`/`CARD_VERSION` = `0.22.1`)
> ausgeliefert. **Starten Sie Home Assistant nach dem Update neu**, damit die
> gecachten Frontend-JS-Module neu geladen werden und die Änderungen sichtbar
> sind. Es gibt **nichts zu migrieren**.

## 🐛 Behoben

### Panel-Performance

- **HTML-Memoisierung statt DOM-Neuaufbau:** bei jedem `hass`-Update wird das
  bereits gerenderte HTML wiederverwendet, statt den DOM-Baum neu aufzubauen.
- **Personenwechsel auf einen Render gebündelt:** ein Wechsel der aktiven Person
  löst nur noch einen einzigen Render aus.
- **Bootstrap parallelisiert:** die sichtbare Person wird zuerst geladen, der
  Rest läuft parallel — das Panel ist schneller interaktiv.
- **Refresh-Debounce 150 → 400 ms:** schnelle aufeinanderfolgende Updates werden
  stärker gebündelt.
- **`panel_data`-Aggregation im Executor:** die Aggregation läuft außerhalb des
  Event-Loops, sodass dieser nicht mehr blockiert wird.

### Neuer Topbar-Button „Zurück zu Home Assistant"

- Ein same-origin Referrer führt zu `history.back()`, sonst zur HA-Übersicht.
- Deutsche und englische Übersetzungen sind enthalten.

### E2E-Stack: CSV-Export lesbar

- Der Home-Assistant-Config-Ordner wird in den E2E-Runner gemountet, damit die
  CSV-Export-Tests im Container die exportierte Datei lesen können (vorher auf
  `main` rot).

## Kompatibilität & Aktionshinweise

Es gibt **keine Breaking Changes**, **keine Migration** und **keinen
Schema-Bump**.

### Was unverändert bleibt

- **`unique_id`s, Entity-IDs, `translation_key` und Entity-Menge** —
  unverändert; keine Entity-Registry-Migration.
- **Kein `async_migrate_entry`**, kein Store-Schema-Bump, kein
  Backup-Schema-Bump.
- **Panel-/Card-Registrierung** — der Cache-Buster (`?v=0.22.1`),
  `PANEL_VERSION` und `CARD_VERSION` sind auf `0.22.1` gezogen.

## Upgrade

1. Update über HACS installieren.
2. **Home Assistant neu starten** (Frontend-JS-Cache).
3. Es gibt nichts zu migrieren.

## Vollständiger Changelog

https://github.com/Popoboxxo/ha-health-o-mat/compare/v0.22.0...v0.22.1

---

# v0.22.1 — Panel performance, "Back to Home Assistant" button, E2E CSV export

## Summary

Patch release with bug fixes and improvements affecting the panel and the E2E
stack. The panel renders significantly faster (HTML memoisation instead of DOM
rebuild), a new topbar button takes you back to Home Assistant, and the E2E
runner now mounts the HA config folder so CSV export tests inside the container
can read the exported file. The release has **no breaking changes**: there is no
migration, no `async_migrate_entry` step and no store/backup schema bump.

> ℹ️ **Note — please read after updating.** The panel and card ship with a new
> cache buster (`?v=0.22.1`, `PANEL_VERSION`/`CARD_VERSION` = `0.22.1`).
> **Restart Home Assistant after the update** so the cached frontend JS modules
> are reloaded and the changes become visible. There is **nothing to migrate**.

## 🐛 Fixed

### Panel performance

- **HTML memoisation instead of DOM rebuild:** on every `hass` update the
  already rendered HTML is reused instead of rebuilding the DOM tree.
- **Person switch coalesced into a single render:** switching the active person
  now triggers only one render.
- **Parallelised bootstrap:** the visible person is loaded first, the rest runs
  in parallel — the panel becomes interactive faster.
- **Refresh debounce 150 → 400 ms:** rapid successive updates are coalesced more
  strongly.
- **`panel_data` aggregation in the executor:** aggregation runs off the event
  loop, so the loop is no longer blocked.

### New topbar button "Back to Home Assistant"

- A same-origin referrer uses `history.back()`, otherwise the button falls back
  to the HA overview.
- German and English translations are included.

### E2E stack: CSV export readable

- The Home Assistant config folder is now mounted into the E2E runner so CSV
  export tests inside the container can read the exported file (previously red
  on `main`).

## Compatibility & action items

There are **no breaking changes**, **no migration** and **no schema bump**.

### What stays

- **`unique_id`s, entity ids, `translation_key` and the entity set** —
  unchanged; no entity-registry migration.
- **No `async_migrate_entry`**, no store schema bump, no backup schema bump.
- **Panel/card registration** — the cache buster (`?v=0.22.1`), `PANEL_VERSION`
  and `CARD_VERSION` are bumped to `0.22.1`.

## Upgrade

1. Install the update via HACS.
2. **Restart Home Assistant** (frontend JS cache).
3. There is nothing to migrate.

## Full changelog

https://github.com/Popoboxxo/ha-health-o-mat/compare/v0.22.0...v0.22.1

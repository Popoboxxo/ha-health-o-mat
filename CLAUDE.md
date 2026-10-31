# ha-health-o-mat

> Projektbeschreibung für Claude-Agenten. Diese Datei ist die **einzige Quelle**
> für projektspezifischen Kontext — Agenten lesen sie, statt eigenen Kontext zu haben.
>
> Generiert von agent-meta v2.0.0-beta.5 — `2026-10-30`
>
> **Längenempfehlung:** 200–500 Zeilen optimal. Über 500 Zeilen → Detailwissen in
> `docs/ARCHITECTURE.md`, `docs/API.md` o.ä. auslagern und manuell verlinken.
> Agent-spezifisches Wissen → `.claude/3-project/<rolle>-ext.md` (Extension).
>
> **CLAUDE.md Hierarchie (Claude Code lädt in dieser Reihenfolge):**
> 1. `~/.claude/CLAUDE.md` — global, alle Projekte (~50 Zeilen max, persönliche Präferenzen)
> 2. `<projekt>/CLAUDE.md` — diese Datei, projektspezifisch (von agent-meta verwaltet)
> 3. `<ordner>/CLAUDE.md` — optional in Unterordnern (z.B. `src/backend/CLAUDE.md`)

---

## Eigene Notizen

Hier kannst du eigene, projektspezifische Notizen eintragen. Dieser Bereich wird von `agent-meta` nicht überschrieben!

---

## Projekt

**Name:** ha-health-o-mat
**Präfix:** hom
**Plattform:** Home Assistant (HACS Custom Integration)
**Beschreibung:** Home Assistant HACS Custom Integration für Getränke-Tracking, Blutdruck-Messwerte und Wohlbefinden-Erfassung pro Person — ein Config-Entry pro Person, dynamisch beliebig oft anlegbar.

> Struktur: siehe Verzeichnisstruktur im Repo (`ls`/`find`); deklarativ: `.meta-config/project.yaml` → `variables.PROJECT_STRUCTURE`.

**Verzeichnisstruktur:**
```
custom_components/health_o_mat/   # Integration (HA-frei: logic.py, parser.py)
tests/                            # Unit-Tests ohne HA-Paket (Fake-Package in conftest.py)
tests_e2e/                        # E2E-Tests gegen die HA-Testinstanz
scripts/                          # E2E-/Bootstrap-Hilfsskripte
docs/                             # Konzepte, Pläne, Requirement-Traceability
.meta-config/project.yaml         # deklarative Projekt-Konfiguration (agent-meta)
```

> Runtime & Abhängigkeiten: siehe Projekt-Manifest (`pyproject.toml` / `requirements.txt` / `package.json` / `manifest.json`).

**Entry-Point:** `custom_components/health_o_mat/__init__.py — async_setup_entry/async_unload_entry, Services, Entry-Registry unter hass.data[DOMAIN][entry_id]`

**Besondere Patterns:**
- Ein Config-Entry = eine Person (kein Singleton, dynamisch beliebig viele Entries; Duplikat-Schutz über async_set_unique_id + _abort_if_unique_id_configured)
- Gemeinsamer Store unter hass.data[DOMAIN]["shared"]["store"]; Runtime-/Coordinator-Daten pro Entry unter hass.data[DOMAIN][entry_id]
- Ein DataUpdateCoordinator pro Config-Entry mit update_interval=None; Refresh via async_set_updated_data() bei Events statt Polling
- Heute-Fenster und Summen on-read berechnen — kein Reset-Job (neustart- und DST-fest)
- unique_id = f"{entry_id}_{key}" stabil + device_info ab Entity #1; has_entity_name + translation_key, keine Namens-Literale
- Plattform-Name == Dateiname (sensor.py, binary_sensor.py, button.py, number.py, select.py, text.py)
- Options-Flow für nachträglich Korrigierbares; strukturelle Daten explizit in entry.data

## Code-Konventionen

- `from __future__ import annotations` + vollständige Type-Hints
- unique_id + device_info ab Entity #1; unique_id stabil & entry-spezifisch ({entry_id}_{key}), NIE nachträglich ändern
- Store liegt unter hass.data[DOMAIN]["shared"]["store"]; Runtime-Daten pro Entry unter hass.data[DOMAIN][entry_id]
- Domain snake_case ohne Bindestriche (health_o_mat)
- iot_class nur in manifest.json, nie in hacs.json
- Plattform-Name == Dateiname (z.B. "select" in PLATFORMS braucht select.py) — sonst ModuleNotFoundError beim Setup
- has_entity_name = True + translation_key statt hartkodierter Entity-Namen
- state_class setzen (measurement/total) wo sinnvoll, für Langzeitstatistik
- Zeitstempel-Entities mit device_class: timestamp
- Nachträglich Korrigierbares gehört in Options, nicht ins initiale Setup
- Config-Flow muss strukturelle Daten explizit in entry.data schreiben, nicht nur als Default annehmen
- Services mit voluptuous-Schema + ServiceValidationError, danach Refresh via async_set_updated_data()
- Zeitfenster ("heute") on-read berechnen statt Reset-Job — neustart- und DST-fest

## Build & Development

```bash
# Build


# Tests
pytest

# Dev-Stack starten


# Nach Änderungen neu laden
/home/hermes/ha-test/bin/sync <repo-dir>
/home/hermes/ha-test/bin/ha GET /api/states
```

## Anforderungs-Kategorien

Kategorien für `docs/REQUIREMENTS.md`:

- **Kernfunktionalität** — Kernfeatures des Projekts
- **Lifecycle** — Startup, Shutdown, Fehlerbehandlung
- **Nichtfunktionale Anforderungen** — Performance, Sicherheit, Wartbarkeit


## Agenten-Konfiguration

<!-- agent-meta:managed-begin -->
<!-- Dieser Block wird von sync.py bei jedem sync automatisch aktualisiert. -->
<!-- Manuelle Änderungen hier werden überschrieben. -->

> **AI ROUTING:** Claude -> CLAUDE.md | Gemini, Opencode -> AGENTS.md

Generiert von agent-meta v2.0.0-beta.5 — `2026-10-30`
DoD-Preset: **rapid-prototyping** | REQ-Traceability: false | Tests: false | Codebase-Overview: false | Security-Audit: false
> **Einstiegspunkt:** Starte mit dem `orchestrator`-Agenten für alle Entwicklungsaufgaben — Ausnahmen siehe Abschnitt »Orchestrator — Universal Router«.
<!-- agent-meta:managed-end -->

# ha-health-o-mat

> Projektbeschreibung für Claude-Agenten. Diese Datei ist die **einzige Quelle**
> für projektspezifischen Kontext — Agenten lesen sie, statt eigenen Kontext zu haben.
>
> Generiert von agent-meta v0.101.0-beta.3 — `2026-08-30`
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

## Tech-Stack

- **Runtime:** Home Assistant Core
- **Sprache:** {{LANGUAGE}}
- **Key-Dependencies:** {{SYSTEM_DEPENDENCIES}}

## Architektur

```
{{PROJECT_STRUCTURE}}
```

**Entry-Point:**
```
{{ENTRY_POINT_PATTERN}}
```

**Besondere Patterns:**
{{KEY_PATTERNS}}

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
{{DEV_STACK_RELOAD}}
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

Generiert von agent-meta v0.101.0-beta.3 — `2026-08-30`
DoD-Preset: **rapid-prototyping** | REQ-Traceability: false | Tests: false | Codebase-Overview: false | Security-Audit: false
> **Einstiegspunkt:** Starte mit dem `orchestrator`-Agenten für alle Entwicklungsaufgaben — Ausnahmen siehe Abschnitt »Orchestrator — Universal Router«.
<!-- agent-meta:managed-end -->

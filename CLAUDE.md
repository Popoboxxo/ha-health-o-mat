# ha-health-o-mat

> Projektbeschreibung für Claude-Agenten. Diese Datei ist die **einzige Quelle**
> für projektspezifischen Kontext — Agenten lesen sie, statt eigenen Kontext zu haben.
>
> Generiert von agent-meta v0.100.0 — `2026-08-24`
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
**Beschreibung:** Home Assistant HACS Custom Integration für Getränke-Tracking, Blutdruck- Messwerte und Wohlbefinden-Erfassung pro Person.

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
- unique_id + device_info ab Entity #1
- Store liegt unter hass.data[DOMAIN]["shared"]["store"]
- Domain snake_case ohne Bindestriche (health_o_mat)
- iot_class nur in manifest.json, nie in hacs.json


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

> **AI ROUTING:** Claude -> CLAUDE.md

Generiert von agent-meta v0.100.0 — `2026-08-24`
DoD-Preset: **rapid-prototyping** | REQ-Traceability: false | Tests: false | Codebase-Overview: false | Security-Audit: false
> **Einstiegspunkt:** Starte mit dem `orchestrator`-Agenten für alle Entwicklungsaufgaben — Ausnahmen siehe Abschnitt »Orchestrator — Universal Router«.
<!-- agent-meta:managed-end -->

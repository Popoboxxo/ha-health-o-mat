---
type: Plan
title: Umsetzungsplan — Funde & Risiken (System-Review v0.4.0)
created: 2026-09-06
source: docs/REQUIREMENTS.md (REQ-HOM-101…110) + Review 2026-09-06
pipeline_stages:
  implement: 4
---

# Umsetzungsplan: Funde & Risiken (nur Fixes)

**Scope:** ausschließlich Bugfix-/Qualitätsanforderungen (F1–F9 → REQ-HOM-101…110).
**Features (REQ-HOM-001…010) laufen bewusst NICHT in diesen Wellen** — eigener Track.

**Prinzipien für alle Wellen:** Branch je Welle (`fix/…`) · Conventional Commits ·
Tests grün · E2E auf ha-test (`bin/sync`, Config-Flow, englische IDs,
`bin/check-dashboards`) · Release-Dreiklang pro Welle · **keine unique_id-Änderungen**
→ keine Breaking-Notes erwartet; Update-Tests mit v0.4.0-Bestand sind Pflicht, sobald
Migration im Spiel ist.

---

## Welle 0 — Sofort (Doku-Wahrheit, ohne Release) ✅ erledigt 2026-09-06
| REQ | Arbeitsschritte | DoD |
|---|---|---|
| 110 | README:25–26 umformulieren: Tagesgrenze fix = 0 Uhr; „umstellbar" als geplant (→ REQ-HOM-005) markieren | README stimmt; kein Code-Change; Tests unverändert grün |

## Welle A — Datenverlust-Sicherheit (P1) → Ziel v0.5.0 ✅ erledigt 2026-09-06

| REQ | Arbeitsschritte | Test-Plan |
|---|---|---|
| 102 | `minor_version=1` in const/Store; Migratoren-Scaffold `_migrations: dict[int, callable]`; `async_load` ruft Kette | Migrations-Unit-Tests (Alt-JSON-Fixtures v1) |
| 103 | Corrupt-Handling: try/except um Load → Backup-Datei `health_o_mat.corrupt-<ts>`, Notification, leerer Start | Corrupt-Unit-Test, Notification-Aufruf verifiziert |
| 101 | Options-Flow: 4 Quick-Drink-Slots (label/ml/icon) + optionaler Anzeigename; ConfigFlow.VERSION 1→2 + `async_migrate_entry` (data→options); Button/Entity-Lesepfade auf options umstellen; `options.person`-Override in entity.py/device name + store.set_person | Migration-Tests (Alt-Entry), Options-Flow-Tests, E2E: v0.4.0-Entry updaten, Quick-Drink ändern, Reload, Buttons neu |
| 104 | Store-`inputs` je Person (Schema 102); `InputNumber._apply` → Store; Setup lädt; Save leert | Unit-Tests, E2E: halbfüllte Eingabe überlebt Neustart |

**DoD Welle A:** Update-Test v0.4.0 → neuer Stand auf ha-test ohne Datenverlust
(Getränke/BP/Wellbeing/Inputs intakt), README-Migrationsabschnitt ergänzt,
Release v0.5.0 (kein Breaking: entry.data bleibt für Nutzer sichtbar unverändert).

**Verifikation (2026-09-06):** Tiefen-Live-Test `scripts/e2e-live-test.sh`
**88/88 Checks** auf der geteilten Instanz (Systemsprache de) — 32 Entities
(englische IDs, deutsche Namen), Getränke/BP/Wohlbefinden-Batterien,
Multi-Person, Export, Update-Migration v0.4.0→neu (Worktree), Corrupt-Recovery
(HA-nativ: Backup + Repairs-Issue), Dashboards live + Lovelace-Save/Load
(33/41 Karten). Unit: **99/99**. Ergebnisse in PR #8 dokumentiert.

## Welle B — Qualität & Support (P2) → Ziel v0.5.1

| REQ | Arbeitsschritte | Test-Plan |
|---|---|---|
| 107 | `services` in de.json (übersetzt) + en.json (= strings.json); services.yaml-Feldbeschreibungen | Neuer Paritätstest (strings↔de↔en Key-Bäume) |
| 106 | pyproject ruff-Konfig + CI-Job `lint`; Aufräum-Commit | ruff lokal+CI grün |
| 105 | diagnostics.py (redacted: Zähler, IDs, Options, Versionen) + strings für diagnostics | Redact-Unit-Test, E2E-Download auf ha-test |

## Welle C — Backlog (P3) → Ziel v0.5.2 oder später

| REQ | Arbeitsschritte | Test-Plan |
|---|---|---|
| 108 | `csv_header_footer` entfernen | grep-clean, Tests |
| 109 | Retention-Option + Archiv-Store + Export-Integration | Default-aus-Verhaltenstest, Archiv-Unit-Tests, E2E |

## Danach — Feature-Reihe (eigener Track)

Reihenfolge: REQ-HOM-001 → 002 → 003 → 010 (pure-logic-lastig, schnell testbar),
danach 004/006, zuletzt 007/008/009. Tagesgrenze REQ-HOM-005 kann jederzeit
einspringen (löst REQ-HOM-110 dauerhaft ab).

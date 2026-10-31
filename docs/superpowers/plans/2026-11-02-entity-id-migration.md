# Entity-ID-Migration auf sprachunabhängige `object_id`s: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task.
> Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Den **Bestand** der beiden nicht konformen Entity-Klassen auf das einheitliche,
sprachunabhängige Schema umstellen — Quick-Drink-Buttons `{device_slug}_quick_drink_<n>`
(1-basiert) und Custom-Labor-Marker `{device_slug}_lab_<key>` — über einen
`async_migrate_entry`-Pass (`ConfigFlow VERSION 2 → 3`), ohne `unique_id`, `original_name`,
`device_id`, Store oder Verlauf anzufassen; dazu die vier Härtungen A-1…A-4 und das
Pinning für Neuregistrierungen (A-5), damit ein frisch aufgesetztes System dieselben IDs
erzeugt wie ein migriertes.

**Architecture:** Die Ziel-ID wird **deterministisch aus der `unique_id`** abgeleitet
(`{entry_id}_button_quick_<index>` → `quick_drink_<index+1>`, `{entry_id}_lab_<key>` →
`lab_<key>`), nie aus einem Anzeigenamen-Slug. Die gesamte Planungslogik lebt in einem
**HA-freien** Modul `custom_components/health_o_mat/migration.py` (reine Funktionen über
Registry-Mappings, kein `homeassistant`-Import, kein Paket-Import). `__init__.py` ist nur
die dünne HA-Anbindung: Registry/Device-Registry/States lesen, `build_migration_plan`
aufrufen, `await er.async_migrate_entries(...)` mit einem Callback, der ausschließlich
`new_entity_id` setzt, danach Drift-Diagnose und — nur bei vollem Erfolg — **ein**
`async_update_entry(data=…, options=…, version=3)`. Kollisionen und nicht auflösbare
`device_slug`-Fälle sind **fail-closed**: Skip + Warnung mit Paarliste, Version bleibt
stehen, HA wiederholt den Pass beim nächsten Start.

**Tech Stack:** Python 3.13 (bestehende Konventionen, `from __future__ import annotations`,
vollständige Type-Hints), pytest mit der Fake-HA-Technik aus `tests/conftest.py`
(importlib-Laden von `__init__.py` wie in `tests/test_wave_a.py:166-176`), Playwright-E2E
gegen die geteilte Instanz.

**Spec:** `docs/superpowers/specs/2026-11-02-entity-id-migration-design.md`
(APPROVED 2026-11-02, 1167 Zeilen) — **verbindlich**. Dieser Plan setzt §2–§6 um.

**Audit:** `docs/reviews/entity-id-stability-audit.md` (F-1/F-2, A-1…A-5, B-1).

**REQ:** **REQ-HOM-130 (Migration)** und **REQ-HOM-131 (Härtungen A-1…A-4)**. Der
Requirements-Agent arbeitet parallel an `docs/REQUIREMENTS.md`; solange die IDs dort noch
nicht existieren, gilt diese Referenz und Task 18 trägt sie nach.

**Basis / Zeilenanker:** `main` @ `d86b247` (Release 0.16.2), `config_flow.py:250`
(`VERSION = 2`), `__init__.py:149-174` (`async_migrate_entry`), Arbeitsbaum sauber außer
den beiden untracked Doku-Dateien (Spec + Audit). **Vor Task 1 prüfen:**

```bash
git rev-parse --short HEAD            # erwartet: d86b247
git status --short                    # erwartet: nur ?? docs/reviews/, ?? docs/superpowers/specs/2026-11-02-...
sed -n '250p' custom_components/health_o_mat/config_flow.py   # erwartet: "    VERSION = 2"
sed -n '149,174p' custom_components/health_o_mat/__init__.py  # erwartet: async_migrate_entry v1->v2
```

Weicht ein Anker ab: **anhalten** und die betroffenen Task-Zeilen vor dem Start
nachziehen (die Ableitung ist an `unique_id`-Formate gebunden, nicht an Zeilennummern).

**Branch:** Ein einziger Feature-Branch **`feat/entity-id-migration`**, von `main`
abgezweigt (`.claude/rules/branch-guard.md`). Git-Mutationen (Branch, Commit, Push) laufen
über den `git`-Agenten; die Commit-Zeilen unten sind die exakten Nachrichten.

**Pre-flight (vom `git`-Agenten):**

```bash
git switch main
git pull --ff-only
git add docs/superpowers/specs/2026-11-02-entity-id-migration-design.md \
        docs/reviews/entity-id-stability-audit.md \
        docs/superpowers/plans/2026-11-02-entity-id-migration.md
git commit -m "docs: plan entity id migration to stable object ids"
git switch -c feat/entity-id-migration
```

**Release:** Ziel ist **MINOR `0.17.0`** — bewusste, vom Nutzer freigegebene Abweichung von
der Projektregel „`entity_id`-Änderung = MAJOR" (Spec §5.4). Die Vorbereitung (Manifest,
Cache-Buster, `CHANGELOG`, Release-Notes) ist Task 19; **Tag und GitHub-Release sind nicht
Teil dieses Plans** (Final Integration Check).

## Global Constraints

- Conventional Commits, English, imperative, erste Zeile ≤ 72 Zeichen, **keine führende
  UTF-8-BOM**; jede Commit-Nachricht steht exakt im Task.
- `from __future__ import annotations` + vollständige Type-Hints in jeder neuen/berührten
  Python-Datei.
- **`unique_id` wird nie geändert.** Geändert wird ausschließlich `entity_id`
  (`new_entity_id`). Der Callback liefert **nur** `{"new_entity_id": …}` — kein
  `new_unique_id`, kein `original_name`. Dadurch bleiben `entity_category`, `labels`,
  `aliases`, `area_id`, `hidden_by`, `disabled_by` erhalten (Spec §3.2, AK 7).
- **Kein Store-Eingriff:** `STORE_SCHEMA_VERSION` bleibt, `lab_readings[]`/`drinks[]`
  unverändert, keine Backup-/CSV-/Diagnostics-Änderung.
- **Nur zwei Klassen migrieren** (F-1, F-2). Katalog-Marker, Kategorie-Warnungen,
  Wellbeing-Buttons und alle übrigen translation-key-Entities bleiben unangetastet.
- **HA-frei bleibt HA-frei:** `migration.py` importiert nichts aus `homeassistant` und
  nichts aus dem eigenen Paket (auch nicht `.const`) — der Unit-Test lädt die Datei direkt
  per `importlib.util.spec_from_file_location`, ein relativer Import würde ihn sofort
  brechen (gewollte Doppelwache).
- **Fail-closed:** Skip oder Drift ⇒ `False`, **kein** `async_update_entry`, Version bleibt
  stehen. Behebung durch den Nutzer (Entity entflechten, Gerätename/Area bereinigen) +
  Neustart.
- **Idempotent:** zweiter Lauf mit `version == 3` macht keine Registry-Aufrufe und kein
  `async_update_entry`. Ein Teil-Lauf wiederholt nur den offenen Rest (`target == source`
  ist kein Rename und kein Skip).
- **`er.async_migrate_entries` ist eine Coroutine** (HA 2026.8/2026.9) und wird `await`ed.
  In Tests **niemals** `MagicMock` dafür (schluckt die Coroutine und maskiert genau diesen
  Fehler) — immer `AsyncMock` + `assert_awaited_once()`.
- **`dr.async_get_device(identifiers=…)` ist deprecated.** Verwende
  `async_get_device_by_identifier((DOMAIN, entry.entry_id), entry.entry_id)`
  (Verankerung wie `entity.py:26-31`), Fallback: erste nicht-`None`-`device_id` über
  **alle** Registry-Entities des Entrys.
- **Testinstanz-Etikette:** nur die eigene Domain syncen, **kein** `bin/reset`, **keine**
  Sprachumschaltung, keine fremden Domains/Entries anfassen, Snapshots nur lesend nach
  `.tmp/` (nie committen), Tokens nie kopieren.
- **Doku/Sprache:** Plan/README/Release-Notes deutsch, Code/Kommentare/Commits/Testnamen
  englisch. Testnamen tragen `test_req_hom_130_*` (Migration, A-1/A-2) bzw.
  `test_req_hom_131_*` (A-3/A-4).
- Nach **jedem** Task: `python3 -m pytest -q` und `ruff check .` +
  `ruff format --check .` grün (Details je Task).

## Wellen- und Task-Übersicht (19 Tasks, 6 Wellen)

| Wave | Tasks | Inhalt | REQ |
|---|---|---|---|
| 1 | 1–3 | HA-freie Migrationslogik: Primitiven (`quick_drink_target`, `custom_lab_target`, Parser), `resolve_device_slug`, `build_migration_plan` | 130 |
| 2 | 4–7 | Test-Fakes, `suggested_object_id`-Pinning (A-5), `async_migrate_entry` + `VERSION 3`, vollständige Registry-Tests | 130 |
| 3 | 8–11 | Härtungen A-1 (Kategorie-Validierung), A-2 (Key-Erhalt inkl. Aufrufstellen), A-3 (`WELLBEING_STATES`-Drift), A-4 (E2E-Regression) | 131 |
| 4 | 12–13 | E2E-Labor-Assertion `_lab_<key>`, Beispiele/Dashboards-Test/`e2e-live-test.sh` auf neue IDs | 130 |
| 5 | 14–17 | Live-Migrationstest auf `/home/hermes/ha-test` (Betriebsprozedur, **kein Code**): Baseline/Snapshots, Erstlauf + Verifikation, Negativprobe/Retry/Idempotenz, Cleanup + Restore-Pfad | 130 |
| 6 | 18–19 | README-Kasten + REQUIREMENTS, Release-Vorbereitung `0.17.0` | 130/131 |

Reihenfolge ist verbindlich; Details siehe „Dependency- & Parallelisierungs-Hinweise".

### Dependency- & Parallelisierungs-Hinweise (Kurzfassung)

**Gemeinsame Engpässe — nie parallel starten:**

| Engpass | Tasks | Grund |
|---|---|---|
| `custom_components/health_o_mat/migration.py` | 1, 2, 3 | eine Datei, aufeinander aufbauend (Dataclasses → Resolver → Plan) |
| `tests/conftest.py` | 4 | einmalige Fake-Härtung; alle späteren Tests hängen daran |
| `custom_components/health_o_mat/__init__.py` | 6, 7 | Imports + Handler; Task 7 fixt nur Lücken aus Task 6 |
| `tests/test_entry_migration.py` | 6, 7 | Happy-Path (6) → Negativ-/Randfälle (7) in derselben Datei |
| `custom_components/health_o_mat/logic.py` | 8 | A-1 und A-2 im selben Normalisierer |
| `custom_components/health_o_mat/ws_api.py` | 9 | Signatur + Aufrufstelle derselben Funktion |
| `tests/test_wave_a.py` | 4, 6 | `_load_init` (4) und Migrations-Erwartungen v1→v3 (6) |
| `/home/hermes/ha-test` (geteilte Instanz) | 11, 14–17 | Live-Läufe serialisieren; `bin/sync` startet HA neu |

**Harte Abhängigkeiten (Kette):** 1 → 2 → 3; 3 → 6; 4 → 5/6/7; 5 → 6 (Pinning vor
Migration, sonst divergieren Bestand und Neuinstallation); 6 → 7 → 14; 8 → 9 → 18;
5 → 11; 5/6 → 12; 13 → 15 (Beispiele/`e2e-live-test.sh` vor dem Live-Lauf);
14/15/16/17 → 18/19.

**Parallelisierbar (disjunkte Dateien):**

| Parallel | Bedingung |
|---|---|
| 8 ‖ 5/6/7 | `logic.py` vs. `button.py`/`sensor.py`/`__init__.py`/`tests/test_entry_migration.py` — disjunkt; 9 erst nach 8 |
| 10 ‖ 5/6/7/8 | nur `tests/test_translations.py` |
| 11 ‖ 8/9/10 | neues `tests_e2e/test_entity_ids_e2e.py`; benötigt Task 5 + Instanz-Zugriff |
| 13 ‖ 10/11 | `examples/`, `tests/test_dashboards.py`, `scripts/e2e-live-test.sh` |
| 18 ‖ 19 | `README.md` + `docs/REQUIREMENTS.md` vs. `manifest.json`/JS/`CHANGELOG.md` |

**Nicht parallel:** 1 ‖ 2 ‖ 3 (`migration.py`), 6 ‖ 7 (`tests/test_entry_migration.py`),
8 ‖ 9 (A-2-Aufrufstellen lesen die neue Signatur), 11 und 14–17 (geteilte Instanz, ein
Neustart-Fenster).

### Präzisierungen (bindend ist die Spec; Abweichungen vom Task-Text sind hier begründet)

1. **`stale_marker_key` und `schema_drift` sind keine Skip-Gründe.** Spec §3.2/§3.5 legt
   fest: `stale_marker_key` ist eine **Warnung** (Rename läuft weiter), `schema_drift` ist
   die **Post-Pass-Diagnose** (führt zum Fehlschlag, ist aber kein Plan-Skip). Es gibt
   daher genau **vier** `SKIP_*`-Konstanten; `build_migration_plan` erzeugt nur diese vier.
   Beide Warnungen entstehen in der HA-Anbindung (Task 6).
2. **Testdateinamen nach Spec §6.1/§6.2:** `tests/test_entity_id_migration.py` (HA-frei)
   und `tests/test_entry_migration.py` (Fake-Registry). Ein einzelnes
   `tests/test_migration.py` gibt es nicht.
3. **`resolve_device_slug` ohne Kandidaten** liefert `device_slug_unresolved` (die Spec
   regelt den Fall nicht). Begründung: ohne Kandidaten gibt es nichts aufzulösen; der Plan
   bleibt dadurch skip-frei und `test_no_entities_still_bumps_version` wird erfüllbar.
4. **A-4 schaltet die Systemsprache nicht um** (Spec §1.4: „keine Sprachumschaltung auf
   der Testinstanz"). Der Test liest `hass.config.language` und prüft denselben
   sprachunabhängigen Vertrag in beiden Fällen; unter `de` ist er die scharfe Regression,
   unter `en` pinnt er die Erstregistrierungs-IDs. Die „Rot-Probe" erfolgt per Mutation
   (Pinning temporär entfernen), nicht per Sprachwechsel.
5. **Drift-Diagnose prüft die ganze Registry**, auch Entities, die im selben Pass als
   `target_occupied` geskippt wurden (Spec §3.2, Code wie dort). Doppelmeldung
   (Skip-Warnung + Drift-Warnung) ist gewollt: der Pass scheitert in beiden Fällen.

---

## Wave 1 — HA-freie Migrationslogik

### Task 1: `migration.py` — Konstanten, Dataclasses, Ziel-/Parse-Funktionen

**Files:**
- Create: `custom_components/health_o_mat/migration.py`
- Test: `tests/test_entity_id_migration.py`

**Interfaces:**
- Produces:
  - `migration.SKIP_DEVICE_SLUG_UNRESOLVED = "device_slug_unresolved"`
  - `migration.SKIP_DEVICE_SLUG_AMBIGUOUS = "device_slug_ambiguous"`
  - `migration.SKIP_TARGET_OCCUPIED = "target_occupied"`
  - `migration.SKIP_INVALID_KEY = "invalid_key"`
  - `@dataclass(frozen=True) DeviceSlugResolution(slug: str | None, reason: str | None)`
  - `@dataclass(frozen=True) MigrationRename(unique_id, source_entity_id, target_entity_id)`
  - `@dataclass(frozen=True) MigrationSkip(unique_id, source_entity_id, target_entity_id, reason)`
  - `@dataclass(frozen=True) MigrationPlan(device_slug, renames, skipped)`
  - `quick_drink_target(device_slug: str, index: int) -> str`
  - `custom_lab_target(device_slug: str, key: str) -> str`
  - `parse_quick_drink_index(unique_id: str, entry_id: str) -> int | None`
  - `parse_custom_lab_key(unique_id: str, entry_id: str, catalog_keys: Collection[str]) -> str | None`
  - `is_safe_key(key: str) -> bool`
- Verbraucher: Task 2 (`resolve_device_slug`), Task 3 (`build_migration_plan`), Task 6
  (`__init__.py`), Task 7 (Registry-Tests).

**Spec-Bezug:** §2.1 (Indexbasis 1-basiert), §2.2 (`lab_<key>`, Slug-Sicherheit), §2.5
(Ableitung aus `unique_id`), §3.1 (öffentlicher Vertrag), §6.1 (Unit-Testliste).

- [ ] **Step 1: Write the failing tests**

`tests/test_entity_id_migration.py` — Kopf der Datei (lädt `migration.py` **ohne**
Paket-/HA-Import; das ist die HA-Freiheits-Wache):

```python
"""Tests: HA-free entity id migration logic (REQ-HOM-130, Spec §6.1).

`migration.py` is loaded by file path on purpose (no `custom_components`
import, no fake HA package): the module must import neither `homeassistant`
nor the surrounding package. A relative import would fail right here with
`ImportError: attempted relative import with no known parent package`.
"""

from __future__ import annotations

import importlib.util
import os

import pytest

_COMPONENT_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "custom_components", "health_o_mat")
)


def _load_migration():
    spec = importlib.util.spec_from_file_location(
        "_hom_migration", os.path.join(_COMPONENT_DIR, "migration.py")
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


migration = _load_migration()

ENTRY = "01JABCDEF"
CATALOG = ("alt", "crp", "creatinine", "h_moglobin")


def test_req_hom_130_quick_drink_target_is_one_based():
    assert migration.quick_drink_target("health_o_mat_max", 0) == (
        "health_o_mat_max_quick_drink_1"
    )
    assert migration.quick_drink_target("health_o_mat_max", 3) == (
        "health_o_mat_max_quick_drink_4"
    )


@pytest.mark.parametrize(
    ("unique_id", "expected"),
    [
        (f"{ENTRY}_button_quick_0", 0),
        (f"{ENTRY}_button_quick_10", 10),
        ("other_entry_button_quick_0", None),
        (f"{ENTRY}_button_quick_", None),
        (f"{ENTRY}_button_quick_01", None),
        (f"{ENTRY}_button_quick_x", None),
        (f"{ENTRY}_button_quick_-1", None),
        (f"{ENTRY}_button_quick_0_extra", None),
        (f"{ENTRY}_button_book_custom", None),
    ],
)
def test_req_hom_130_parse_quick_drink_index(unique_id, expected):
    assert migration.parse_quick_drink_index(unique_id, ENTRY) == expected


def test_req_hom_130_custom_lab_target_uses_key():
    assert migration.custom_lab_target("health_o_mat_max", "vitamin_d") == (
        "health_o_mat_max_lab_vitamin_d"
    )
    assert migration.custom_lab_target("health_o_mat_max", "h_moglobin") == (
        "health_o_mat_max_lab_h_moglobin"
    )


def test_req_hom_130_parse_custom_lab_key_skips_catalog():
    assert migration.parse_custom_lab_key(f"{ENTRY}_lab_crp", ENTRY, CATALOG) is None
    assert migration.parse_custom_lab_key(f"{ENTRY}_lab_vitamin_d", ENTRY, CATALOG) == (
        "vitamin_d"
    )
    assert migration.parse_custom_lab_key(
        "other_entry_lab_vitamin_d", ENTRY, CATALOG
    ) is None
    assert migration.parse_custom_lab_key(f"{ENTRY}_lab_", ENTRY, CATALOG) is None
    assert migration.parse_custom_lab_key(
        f"{ENTRY}_binary_lab_warning_liver", ENTRY, CATALOG
    ) is None


def test_req_hom_130_is_safe_key_accepts_slugs_only():
    assert migration.is_safe_key("vitamin_d")
    assert migration.is_safe_key("h_moglobin")
    assert migration.is_safe_key("d3")
    for unsafe in ("Vitamin D", "vitamin-d", "vitamin__d", "_vitamin", "vitamin_", ""):
        assert not migration.is_safe_key(unsafe), unsafe
```

- [ ] **Step 2: Run the red command**

```bash
python3 -m pytest tests/test_entity_id_migration.py -q
```

Expected: collection error / `FileNotFoundError` for
`custom_components/health_o_mat/migration.py` (die Datei existiert noch nicht).

- [ ] **Step 3: Implement**

`custom_components/health_o_mat/migration.py`:

```python
"""HA-free migration logic for the entity id switch (REQ-HOM-130).

Nothing in here imports ``homeassistant`` or the surrounding package: every
function is a pure function over registry data that the caller
(``__init__._async_migrate_entity_ids``) passes in as plain mappings. That keeps
the whole plan unit-testable without a Home Assistant installation (Spec §3.1).

Contract (Spec §3.1): target object ids are derived from the ``unique_id`` only —
never from a display-name slug, never from the system language.
"""

from __future__ import annotations

import re
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass

SKIP_DEVICE_SLUG_UNRESOLVED = "device_slug_unresolved"
SKIP_DEVICE_SLUG_AMBIGUOUS = "device_slug_ambiguous"
SKIP_TARGET_OCCUPIED = "target_occupied"
SKIP_INVALID_KEY = "invalid_key"

# ``{entry_id}_button_quick_<index>`` — index is 0-based and canonical: no
# leading zeros, no sign, no trailing noise (Spec §2.1).
_QUICK_DRINK_UNIQUE_ID_INFIX = "_button_quick_"
# ``{entry_id}_lab_<key>`` — the key is the whole remainder (it may contain
# characters that are not slug-safe; the plan rejects those explicitly).
_LAB_UNIQUE_ID_INFIX = "_lab_"
_QUICK_INDEX_RE = re.compile(r"(?:0|[1-9][0-9]*)\Z")
_SAFE_KEY_RE = re.compile(r"[a-z0-9]+(?:_[a-z0-9]+)*\Z")
_SAFE_SLUG_RE = re.compile(r"[a-z0-9]+(?:_[a-z0-9]+)*\Z")


@dataclass(frozen=True)
class DeviceSlugResolution:
    """Resolved object-id prefix of the person device, or a skip reason."""

    slug: str | None
    reason: str | None


@dataclass(frozen=True)
class MigrationRename:
    """One entity id rename; ``unique_id`` is carried for logging/tests only."""

    unique_id: str
    source_entity_id: str
    target_entity_id: str


@dataclass(frozen=True)
class MigrationSkip:
    """One entity that stays as it is; ``reason`` is a ``SKIP_*`` constant."""

    unique_id: str
    source_entity_id: str
    target_entity_id: str | None
    reason: str


@dataclass(frozen=True)
class MigrationPlan:
    """Deterministic, side-effect-free result of one planning pass."""

    device_slug: str | None
    renames: tuple[MigrationRename, ...]
    skipped: tuple[MigrationSkip, ...]


def quick_drink_target(device_slug: str, index: int) -> str:
    """Object-id stem (without domain) of quick-drink slot ``index`` (0-based)."""
    return f"{device_slug}_quick_drink_{index + 1}"


def custom_lab_target(device_slug: str, key: str) -> str:
    """Object-id stem (without domain) of a custom lab marker."""
    return f"{device_slug}_lab_{key}"


def is_safe_key(key: str) -> bool:
    """True when ``key`` can be used verbatim as an object-id suffix."""
    return bool(_SAFE_KEY_RE.fullmatch(key))


def parse_quick_drink_index(unique_id: str, entry_id: str) -> int | None:
    """Index of ``{entry_id}_button_quick_<n>``, else ``None``."""
    prefix = f"{entry_id}{_QUICK_DRINK_UNIQUE_ID_INFIX}"
    if not unique_id.startswith(prefix):
        return None
    suffix = unique_id[len(prefix) :]
    if not _QUICK_INDEX_RE.fullmatch(suffix):
        return None
    return int(suffix)


def parse_custom_lab_key(
    unique_id: str, entry_id: str, catalog_keys: Collection[str]
) -> str | None:
    """Key of ``{entry_id}_lab_<key>`` when it is NOT a catalog marker, else ``None``."""
    prefix = f"{entry_id}{_LAB_UNIQUE_ID_INFIX}"
    if not unique_id.startswith(prefix):
        return None
    key = unique_id[len(prefix) :]
    if not key or key in catalog_keys:
        return None
    return key
```

- [ ] **Step 4: Run the green command**

```bash
python3 -m pytest tests/test_entity_id_migration.py -q
ruff check custom_components/health_o_mat/migration.py tests/test_entity_id_migration.py
ruff format --check custom_components/health_o_mat/migration.py tests/test_entity_id_migration.py
```

Expected: alle Tests grün, `ruff` clean.

- [ ] **Step 5: Commit**

```bash
git add custom_components/health_o_mat/migration.py tests/test_entity_id_migration.py
git commit -m "feat: add HA-free entity id migration primitives"
```

---

### Task 2: `migration.py` — `resolve_device_slug` (Token-/Boundary-/Hint-Logik)

**Files:**
- Modify: `custom_components/health_o_mat/migration.py`
- Test: `tests/test_entity_id_migration.py`

**Interfaces:**
- Consumes: `DeviceSlugResolution`, `SKIP_DEVICE_SLUG_*`, `_SAFE_SLUG_RE` (Task 1).
- Produces:
  - `resolve_device_slug(candidates, anchors, *, hint, device_id) -> DeviceSlugResolution`
  - intern: `_object_part(entity_id)`, `_tokens(object_part)`,
    `_common_prefix_sequence(sequences)`, `_boundary_prefix(candidate_parts, common_tokens)`,
    `_apply_hint(prefix, hint)`
- Verbraucher: Task 3.

**Spec-Bezug:** §2.3 vollständig (Anker, Token-Ebene, Divergenz-Test, Hint-Auflösung,
Akzeptanz), §6.1 (Resolver-Testliste), R-11.

**Regel in einem Satz:** Das Ergebnis ist das **aktuell für die Entity-Registrierung
verwendete object-id-Präfix** — ermittelt aus Translation-Ankern (nie aus Nutzer-Labels),
bestätigt durch Token-Divergenz oder den Device-Namen-Hint, sonst fail-closed.

- [ ] **Step 1: Write the failing tests**

Ans Ende von `tests/test_entity_id_migration.py`:

```python
# --- resolve_device_slug (Spec §2.3 / §6.1) --------------------------------


def _candidate(entity_id: str, device_id: str | None = "dev1") -> dict:
    return {"entity_id": entity_id, "device_id": device_id}


def _anchor(
    entity_id: str, translation_key: str | None, device_id: str | None = "dev1"
) -> dict:
    return {
        "entity_id": entity_id,
        "translation_key": translation_key,
        "device_id": device_id,
    }


def test_req_hom_130_resolve_accepts_hint_with_matching_anchors():
    resolution = migration.resolve_device_slug(
        [_candidate("button.health_o_mat_max_quick_drink_1")],
        [
            _anchor("sensor.health_o_mat_max_drinks_today", "today"),
            _anchor("sensor.health_o_mat_max_daily_goal_progress", "goal_percent"),
        ],
        hint="health_o_mat_max",
        device_id="dev1",
    )
    assert resolution == migration.DeviceSlugResolution("health_o_mat_max", None)


def test_req_hom_130_resolve_falls_back_to_translation_anchors():
    resolution = migration.resolve_device_slug(
        [_candidate("button.health_o_mat_dana_quick_drink_1")],
        [
            _anchor("sensor.health_o_mat_dana_drinks_today", "today"),
            _anchor("sensor.health_o_mat_dana_daily_goal_progress", "goal_percent"),
        ],
        hint=None,
        device_id="dev1",
    )
    assert resolution == migration.DeviceSlugResolution("health_o_mat_dana", None)


def test_req_hom_130_resolve_ignores_user_labels():
    """B-2 counter-example: four drink labels must never yield `..._glas`."""
    resolution = migration.resolve_device_slug(
        [
            _candidate("button.health_o_mat_max_glas_wasser"),
            _candidate("button.health_o_mat_max_glas_saft"),
            _candidate("button.health_o_mat_max_glas_tee"),
            _candidate("button.health_o_mat_max_glas_kaffee"),
        ],
        [],
        hint=None,
        device_id="dev1",
    )
    assert resolution == migration.DeviceSlugResolution(
        None, migration.SKIP_DEVICE_SLUG_UNRESOLVED
    )


def test_req_hom_130_resolve_hint_conflict_is_ambiguous():
    resolution = migration.resolve_device_slug(
        [_candidate("button.health_o_mat_alt_quick_drink_1")],
        [
            _anchor("sensor.health_o_mat_alt_drinks_today", "today"),
            _anchor("sensor.health_o_mat_alt_daily_goal_progress", "goal_percent"),
        ],
        hint="health_o_mat_neu",
        device_id="dev1",
    )
    assert resolution == migration.DeviceSlugResolution(
        None, migration.SKIP_DEVICE_SLUG_AMBIGUOUS
    )


def test_req_hom_130_resolve_area_prefix_matches_hint():
    """The area segment stays part of the ids (P.endswith("_" + hint))."""
    resolution = migration.resolve_device_slug(
        [_candidate("button.wohnzimmer_health_o_mat_max_quick_drink_1")],
        [
            _anchor("sensor.wohnzimmer_health_o_mat_max_drinks_today", "today"),
            _anchor(
                "sensor.wohnzimmer_health_o_mat_max_daily_goal_progress", "goal_percent"
            ),
        ],
        hint="health_o_mat_max",
        device_id="dev1",
    )
    assert resolution == migration.DeviceSlugResolution(
        "wohnzimmer_health_o_mat_max", None
    )


def test_req_hom_130_resolve_lab_only_with_hint_uses_hint():
    resolution = migration.resolve_device_slug(
        [_candidate("sensor.health_o_mat_max_vitamin_d")],
        [
            _anchor("sensor.health_o_mat_max_lab_crp", "lab_crp"),
            _anchor("sensor.health_o_mat_max_lab_creatinine", "lab_creatinine"),
        ],
        hint="health_o_mat_max",
        device_id="dev1",
    )
    assert resolution == migration.DeviceSlugResolution("health_o_mat_max", None)


def test_req_hom_130_resolve_lab_only_without_hint_is_unresolved():
    resolution = migration.resolve_device_slug(
        [_candidate("sensor.health_o_mat_max_vitamin_d")],
        [
            _anchor("sensor.health_o_mat_max_lab_crp", "lab_crp"),
            _anchor("sensor.health_o_mat_max_lab_creatinine", "lab_creatinine"),
        ],
        hint=None,
        device_id="dev1",
    )
    assert resolution == migration.DeviceSlugResolution(
        None, migration.SKIP_DEVICE_SLUG_UNRESOLVED
    )


def test_req_hom_130_resolve_single_anchor_is_unresolved():
    resolution = migration.resolve_device_slug(
        [_candidate("button.health_o_mat_max_quick_drink_1")],
        [_anchor("sensor.health_o_mat_max_drinks_today", "today")],
        hint="health_o_mat_max",
        device_id="dev1",
    )
    assert resolution == migration.DeviceSlugResolution(
        None, migration.SKIP_DEVICE_SLUG_UNRESOLVED
    )


def test_req_hom_130_resolve_rejects_candidate_outside_prefix():
    resolution = migration.resolve_device_slug(
        [
            _candidate("button.health_o_mat_max_quick_drink_1"),
            _candidate("button.garden_light_quick_drink_2"),
        ],
        [
            _anchor("sensor.health_o_mat_max_drinks_today", "today"),
            _anchor("sensor.health_o_mat_max_daily_goal_progress", "goal_percent"),
        ],
        hint="health_o_mat_max",
        device_id="dev1",
    )
    assert resolution == migration.DeviceSlugResolution(
        None, migration.SKIP_DEVICE_SLUG_AMBIGUOUS
    )


def test_req_hom_130_resolve_rejects_foreign_device():
    """Acceptance demands: every candidate belongs to the anchor device."""
    resolution = migration.resolve_device_slug(
        [
            _candidate("button.health_o_mat_max_quick_drink_1"),
            _candidate("button.health_o_mat_max_quick_drink_2", device_id="dev2"),
        ],
        [
            _anchor("sensor.health_o_mat_max_drinks_today", "today"),
            _anchor("sensor.health_o_mat_max_daily_goal_progress", "goal_percent"),
        ],
        hint="health_o_mat_max",
        device_id="dev1",
    )
    assert resolution == migration.DeviceSlugResolution(
        None, migration.SKIP_DEVICE_SLUG_AMBIGUOUS
    )


def test_req_hom_130_resolve_without_candidates_is_unresolved():
    resolution = migration.resolve_device_slug(
        [],
        [
            _anchor("sensor.health_o_mat_max_drinks_today", "today"),
            _anchor("sensor.health_o_mat_max_daily_goal_progress", "goal_percent"),
        ],
        hint="health_o_mat_max",
        device_id="dev1",
    )
    assert resolution == migration.DeviceSlugResolution(
        None, migration.SKIP_DEVICE_SLUG_UNRESOLVED
    )
```

- [ ] **Step 2: Run the red command**

```bash
python3 -m pytest tests/test_entity_id_migration.py -q
```

Expected: `AttributeError: module '_hom_migration' has no attribute 'resolve_device_slug'`.

- [ ] **Step 3: Implement**

Ans Ende von `custom_components/health_o_mat/migration.py`:

```python
def _object_part(entity_id: str) -> str:
    """``button.health_o_mat_max_quick_drink_1`` -> ``health_o_mat_max_quick_drink_1``."""
    _domain, _, object_part = entity_id.partition(".")
    return object_part


def _tokens(object_part: str) -> list[str]:
    return [token for token in object_part.split("_") if token]


def _common_prefix_sequence(sequences: Sequence[Sequence[str]]) -> list[str]:
    """Longest common leading token sequence (``[]`` when nothing is common)."""
    if not sequences:
        return []
    common = list(sequences[0])
    for sequence in sequences[1:]:
        limit = 0
        for left, right in zip(common, sequence):
            if left != right:
                break
            limit += 1
        common = common[:limit]
    return common


def _boundary_prefix(candidate_parts: Sequence[str], common_tokens: Sequence[str]) -> str:
    """Longest leading token prefix of ``common_tokens`` every candidate extends."""
    for length in range(len(common_tokens), 0, -1):
        prefix = "_".join(common_tokens[:length])
        if all(part.startswith(prefix + "_") for part in candidate_parts):
            return prefix
    return ""


def _apply_hint(prefix: str, hint: str) -> str | None:
    """Resolve ``prefix`` against the device-name hint (Spec §2.3), or ``None``."""
    if prefix == hint:
        return hint
    if prefix.startswith(hint + "_"):
        # Shared entity tokens (e.g. ``lab``) are cut off: the hint is the device.
        return hint
    if prefix.endswith("_" + hint):
        # An area segment in front of the device segment stays part of the ids.
        return prefix
    return None


def resolve_device_slug(
    candidates: Sequence[Mapping[str, object]],
    anchors: Sequence[Mapping[str, object]],
    *,
    hint: str | None,
    device_id: str | None,
) -> DeviceSlugResolution:
    """Resolve the object-id prefix currently used for this person's device.

    ``candidates`` are the entities that will be renamed (F-1/F-2); ``anchors``
    are the remaining entities that carry a ``translation_key`` (their
    object-id suffix is English and language independent, Spec §2.3). Object
    parts only — user labels never influence the result.
    """
    if not candidates:
        return DeviceSlugResolution(None, SKIP_DEVICE_SLUG_UNRESOLVED)

    anchor_parts = [
        _object_part(str(anchor["entity_id"]))
        for anchor in anchors
        if anchor.get("translation_key") is not None
    ]
    # A single anchor cannot prove where the device segment ends.
    if len(anchor_parts) < 2:
        return DeviceSlugResolution(None, SKIP_DEVICE_SLUG_UNRESOLVED)

    candidate_parts = [_object_part(str(candidate["entity_id"])) for candidate in candidates]
    common = _common_prefix_sequence([_tokens(part) for part in anchor_parts])
    if not common:
        return DeviceSlugResolution(None, SKIP_DEVICE_SLUG_AMBIGUOUS)

    prefix = _boundary_prefix(candidate_parts, common)
    if not prefix:
        return DeviceSlugResolution(None, SKIP_DEVICE_SLUG_AMBIGUOUS)

    # Divergence test: the token right after the prefix over ALL anchors.
    depth = len(_tokens(prefix))
    suffixes = {(_tokens(part) + [""])[depth] for part in anchor_parts}
    diverges = len(suffixes) > 1

    slug: str | None
    if diverges:
        # ``drinks_today`` vs ``daily_goal_progress``: the prefix is the boundary.
        slug = _apply_hint(prefix, hint) if hint else prefix
        if slug is None:
            return DeviceSlugResolution(None, SKIP_DEVICE_SLUG_AMBIGUOUS)
    elif hint:
        # ``lab_crp``/``lab_creatinine``: the suffix token does not diverge, so
        # only the hint can prove the boundary (Spec §2.3).
        slug = _apply_hint(prefix, hint)
        if slug is None:
            return DeviceSlugResolution(None, SKIP_DEVICE_SLUG_AMBIGUOUS)
    else:
        # Never guess a device boundary from shared entity tokens.
        return DeviceSlugResolution(None, SKIP_DEVICE_SLUG_UNRESOLVED)

    if not _SAFE_SLUG_RE.fullmatch(slug):
        return DeviceSlugResolution(None, SKIP_DEVICE_SLUG_AMBIGUOUS)
    if not all(part.startswith(slug + "_") for part in candidate_parts):
        return DeviceSlugResolution(None, SKIP_DEVICE_SLUG_AMBIGUOUS)
    if device_id is not None and any(
        candidate.get("device_id") != device_id for candidate in candidates
    ):
        return DeviceSlugResolution(None, SKIP_DEVICE_SLUG_AMBIGUOUS)
    return DeviceSlugResolution(slug, None)
```

- [ ] **Step 4: Run the green command**

```bash
python3 -m pytest tests/test_entity_id_migration.py -q
ruff check custom_components/health_o_mat/migration.py tests/test_entity_id_migration.py
ruff format --check custom_components/health_o_mat/migration.py tests/test_entity_id_migration.py
```

Expected: alle Tests grün. Schlüssel-Assertions: das Gegenbeispiel „vier
Getränke-Labels" liefert **nie** `…_glas`, sondern `device_slug_unresolved`; Lab-only
**mit** Hint liefert den Hint, **ohne** Hint `unresolved`; der Area-Fall behält das
Area-Segment.

- [ ] **Step 5: Commit**

```bash
git add custom_components/health_o_mat/migration.py tests/test_entity_id_migration.py
git commit -m "feat: resolve device slug from translation anchors"
```

---

### Task 3: `migration.py` — `build_migration_plan`

**Files:**
- Modify: `custom_components/health_o_mat/migration.py`
- Test: `tests/test_entity_id_migration.py`

**Interfaces:**
- Consumes: `parse_quick_drink_index`, `parse_custom_lab_key`, `is_safe_key`,
  `quick_drink_target`, `custom_lab_target`, `resolve_device_slug`, Dataclasses
  (Tasks 1/2).
- Produces:
  - `build_migration_plan(entry_id, entities, *, device_slug_hint, device_id, catalog_keys, occupied_entity_ids) -> MigrationPlan`
- Verbraucher: Task 6 (`__init__.py`).

**Spec-Bezug:** §3.1 (Regeln 1–7), §3.4 (nur `target_occupied`, Ziele sind injektiv),
§3.5 (Katalog-Key, entfernter Slot, deaktivierte Entities), §6.1 (`test_plan_*`-Liste).

- [ ] **Step 1: Write the failing tests**

Ans Ende von `tests/test_entity_id_migration.py`:

```python
# --- build_migration_plan (Spec §3.1 / §6.1) -------------------------------

_SLUG = "health_o_mat_max"


def _entity(
    entity_id: str,
    unique_id: str,
    *,
    translation_key: str | None = None,
    device_id: str | None = "dev1",
) -> dict:
    return {
        "entity_id": entity_id,
        "unique_id": unique_id,
        "translation_key": translation_key,
        "device_id": device_id,
    }


def _mixed_entities() -> list[dict]:
    return [
        _entity(f"button.{_SLUG}_glas_wasser", f"{ENTRY}_button_quick_0"),
        _entity(f"button.{_SLUG}_tasse_kaffee", f"{ENTRY}_button_quick_2"),
        _entity(f"sensor.{_SLUG}_vitamin_d", f"{ENTRY}_lab_vitamin_d"),
        _entity(f"sensor.{_SLUG}_crp", f"{ENTRY}_lab_crp", translation_key="lab_crp"),
        _entity(f"sensor.{_SLUG}_drinks_today", f"{ENTRY}_today", translation_key="today"),
        _entity(
            f"sensor.{_SLUG}_daily_goal_progress",
            f"{ENTRY}_goal_percent",
            translation_key="goal_percent",
        ),
        _entity(
            f"button.{_SLUG}_book_custom_amount",
            f"{ENTRY}_button_book_custom",
            translation_key="book_custom",
        ),
    ]


def _plan(entities, *, hint=_SLUG, occupied=()):
    return migration.build_migration_plan(
        ENTRY,
        entities,
        device_slug_hint=hint,
        device_id="dev1",
        catalog_keys=CATALOG,
        occupied_entity_ids=occupied,
    )


def test_req_hom_130_plan_renames_only_f1_f2():
    plan = _plan(_mixed_entities())
    assert plan.device_slug == _SLUG
    assert plan.skipped == ()
    assert {(item.source_entity_id, item.target_entity_id) for item in plan.renames} == {
        (f"button.{_SLUG}_glas_wasser", f"button.{_SLUG}_quick_drink_1"),
        (f"button.{_SLUG}_tasse_kaffee", f"button.{_SLUG}_quick_drink_3"),
        (f"sensor.{_SLUG}_vitamin_d", f"sensor.{_SLUG}_lab_vitamin_d"),
    }


def test_req_hom_130_plan_is_noop_at_target():
    plan = _plan(
        [
            _entity(f"button.{_SLUG}_quick_drink_1", f"{ENTRY}_button_quick_0"),
            _entity(f"sensor.{_SLUG}_lab_vitamin_d", f"{ENTRY}_lab_vitamin_d"),
            _entity(f"sensor.{_SLUG}_drinks_today", f"{ENTRY}_today", translation_key="today"),
            _entity(
                f"sensor.{_SLUG}_daily_goal_progress",
                f"{ENTRY}_goal_percent",
                translation_key="goal_percent",
            ),
        ],
        occupied=(f"button.{_SLUG}_quick_drink_1", f"sensor.{_SLUG}_lab_vitamin_d"),
    )
    assert plan.renames == ()
    assert plan.skipped == ()


def test_req_hom_130_plan_skips_occupied_target():
    plan = _plan(_mixed_entities(), occupied=(f"button.{_SLUG}_quick_drink_1",))
    assert [item.reason for item in plan.skipped] == [migration.SKIP_TARGET_OCCUPIED]
    assert plan.skipped[0].source_entity_id == f"button.{_SLUG}_glas_wasser"
    assert plan.skipped[0].target_entity_id == f"button.{_SLUG}_quick_drink_1"
    # The rest of the plan is unaffected — a collision never blocks other renames.
    assert len(plan.renames) == 2


def test_req_hom_130_plan_skips_invalid_custom_key():
    plan = _plan(
        [
            _entity(f"sensor.{_SLUG}_vitamin d", f"{ENTRY}_lab_vitamin d"),
            _entity(f"sensor.{_SLUG}_drinks_today", f"{ENTRY}_today", translation_key="today"),
            _entity(
                f"sensor.{_SLUG}_daily_goal_progress",
                f"{ENTRY}_goal_percent",
                translation_key="goal_percent",
            ),
        ]
    )
    assert [item.reason for item in plan.skipped] == [migration.SKIP_INVALID_KEY]
    assert plan.skipped[0].target_entity_id is None


def _lab_only_entities() -> list[dict]:
    """Only lab anchors: the suffix token (`lab`) does not diverge (Spec §2.3)."""
    return [
        _entity(f"sensor.{_SLUG}_vitamin_d", f"{ENTRY}_lab_vitamin_d"),
        _entity(f"sensor.{_SLUG}_lab_crp", f"{ENTRY}_lab_crp", translation_key="lab_crp"),
        _entity(
            f"sensor.{_SLUG}_lab_creatinine",
            f"{ENTRY}_lab_creatinine",
            translation_key="lab_creatinine",
        ),
    ]


def test_req_hom_130_plan_propagates_device_slug_reasons():
    # No hint + non-diverging anchors -> unresolved (never a guessed `..._lab`).
    unresolved = _plan(_lab_only_entities(), hint=None)
    assert {item.reason for item in unresolved.skipped} == {
        migration.SKIP_DEVICE_SLUG_UNRESOLVED
    }
    assert unresolved.device_slug is None
    assert unresolved.renames == ()

    # Hint present but in no boundary relation to the anchor prefix -> ambiguous.
    ambiguous = _plan(_lab_only_entities(), hint="health_o_mat_neu")
    assert {item.reason for item in ambiguous.skipped} == {
        migration.SKIP_DEVICE_SLUG_AMBIGUOUS
    }
    assert ambiguous.renames == ()


def test_req_hom_130_plan_deterministic_order():
    first = _plan(_mixed_entities())
    second = _plan(_mixed_entities())
    assert first == second
    assert [item.source_entity_id for item in first.renames] == [
        f"button.{_SLUG}_glas_wasser",
        f"button.{_SLUG}_tasse_kaffee",
        f"sensor.{_SLUG}_vitamin_d",
    ]


def test_req_hom_130_plan_ignores_catalog_and_translation_entities():
    plan = _plan(_mixed_entities())
    touched = {item.source_entity_id for item in plan.renames} | {
        item.source_entity_id for item in plan.skipped
    }
    assert f"sensor.{_SLUG}_crp" not in touched
    assert f"sensor.{_SLUG}_drinks_today" not in touched
    assert f"button.{_SLUG}_book_custom_amount" not in touched


def test_req_hom_130_plan_is_idempotent_for_a_second_pass():
    """After applying the first plan, a second pass over the new ids is empty."""
    first = _plan(_mixed_entities())
    renamed = {item.source_entity_id: item.target_entity_id for item in first.renames}
    second_entities = [
        {**entity, "entity_id": renamed.get(entity["entity_id"], entity["entity_id"])}
        for entity in _mixed_entities()
    ]
    second = _plan(second_entities)
    assert second.renames == ()
    assert second.skipped == ()
```

- [ ] **Step 2: Run the red command**

```bash
python3 -m pytest tests/test_entity_id_migration.py -q
```

Expected: `AttributeError: module '_hom_migration' has no attribute 'build_migration_plan'`.

- [ ] **Step 3: Implement**

Ans Ende von `custom_components/health_o_mat/migration.py`:

```python
def build_migration_plan(
    entry_id: str,
    entities: Sequence[Mapping[str, object]],
    *,
    device_slug_hint: str | None,
    device_id: str | None,
    catalog_keys: Collection[str],
    occupied_entity_ids: Collection[str],
) -> MigrationPlan:
    """Pure planning pass: no HA calls, no side effects, stable order.

    ``entities`` are the registry entries of ONE config entry (Spec §3.1);
    ``occupied_entity_ids`` is the global collision set (registry + states).
    """
    materialized = list(entities)
    occupied = set(occupied_entity_ids)

    candidates: list[tuple[Mapping[str, object], int | None, str | None]] = []
    anchors: list[Mapping[str, object]] = []
    for entity in materialized:
        unique_id = str(entity.get("unique_id") or "")
        index = parse_quick_drink_index(unique_id, entry_id)
        key = (
            None
            if index is not None
            else parse_custom_lab_key(unique_id, entry_id, catalog_keys)
        )
        if index is None and key is None:
            if entity.get("translation_key") is not None:
                anchors.append(entity)
            continue
        candidates.append((entity, index, key))

    resolution = resolve_device_slug(
        [
            {"entity_id": entity["entity_id"], "device_id": entity.get("device_id")}
            for entity, _index, _key in candidates
        ],
        [
            {
                "entity_id": anchor["entity_id"],
                "translation_key": anchor.get("translation_key"),
                "device_id": anchor.get("device_id"),
            }
            for anchor in anchors
        ],
        hint=device_slug_hint,
        device_id=device_id,
    )

    renames: list[MigrationRename] = []
    skipped: list[MigrationSkip] = []

    if resolution.slug is None:
        reason = resolution.reason or SKIP_DEVICE_SLUG_UNRESOLVED
        for entity, _index, _key in candidates:
            skipped.append(
                MigrationSkip(
                    str(entity.get("unique_id") or ""),
                    str(entity["entity_id"]),
                    None,
                    reason,
                )
            )
        return MigrationPlan(None, tuple(renames), tuple(skipped))

    for entity, index, key in candidates:
        source = str(entity["entity_id"])
        unique_id = str(entity.get("unique_id") or "")
        if index is not None:
            target = f"button.{quick_drink_target(resolution.slug, index)}"
        else:
            if not is_safe_key(key or ""):
                # Never rewrite the key silently: it is part of the unique_id.
                skipped.append(MigrationSkip(unique_id, source, None, SKIP_INVALID_KEY))
                continue
            target = f"sensor.{custom_lab_target(resolution.slug, key or '')}"

        # Checked BEFORE the collision test: `occupied` contains the source id,
        # so an already-migrated entity would otherwise report target_occupied.
        if target == source:
            continue
        if target in occupied:
            skipped.append(MigrationSkip(unique_id, source, target, SKIP_TARGET_OCCUPIED))
            continue
        renames.append(MigrationRename(unique_id, source, target))

    return MigrationPlan(resolution.slug, tuple(renames), tuple(skipped))
```

- [ ] **Step 4: Run the green command**

```bash
python3 -m pytest tests/test_entity_id_migration.py -q
ruff check custom_components/health_o_mat/migration.py tests/test_entity_id_migration.py
ruff format --check custom_components/health_o_mat/migration.py tests/test_entity_id_migration.py
```

Expected: alle Tests grün — 24 Testfunktionen (32 Test-Items inkl. der
`parse_quick_drink_index`-Parametrisierung).

- [ ] **Step 5: Commit**

```bash
git add custom_components/health_o_mat/migration.py tests/test_entity_id_migration.py
git commit -m "feat: build deterministic entity id migration plan"
```

---

## Wave 2 — Test-Fakes, Pinning, `async_migrate_entry`

### Task 4: `tests/conftest.py` — Fake-HA für Registry-Migration härten

**Files:**
- Modify: `tests/conftest.py`
- Modify: `tests/test_wave_a.py`

**Interfaces:**
- Consumes: nichts aus Wave 1.
- Produces (für Task 5/6/7):
  - `homeassistant.util.slugify(value) -> str` (echte, deterministische Funktion, **kein**
    `MagicMock` — der Device-Hint muss wie in HA aussehen)
  - `homeassistant.helpers.entity_registry.async_migrate_entries` als `AsyncMock`
    (coroutine-fähig; Tests ersetzen ihn mit eigenem `side_effect`)
  - Fake-`Entity` erhält `platform_data = None` und eine `suggested_object_id`-Property
    (→ `None`), damit der `super()`-Fallback von `HealthOMatEntity` ohne HA-Core läuft
  - `tests/test_wave_a.py::_load_init` lädt zusätzlich das Modul `migration`

**Spec-Bezug:** §5.2 („`hass = MagicMock()` um echte Fakes für `hass.states.async_all()`
ergänzen; `er` ist das Fake-Modul … und braucht `async_get`/Registry-Stub;
`async_migrate_entries` **nicht** als MagicMock"), §6.2 (Fake-Modul-Liste), §7 R-12.

- [ ] **Step 1: Write the failing test**

In `tests/test_wave_a.py` (direkt nach dem Import-Block, vor `_load_init`):

```python
def test_fake_ha_provides_registry_migration_hooks():
    """[REQ-HOM-130] Fake-HA covers the building blocks of the entity id migration."""
    import homeassistant.helpers.device_registry as dr
    import homeassistant.helpers.entity_registry as er
    from homeassistant.util import slugify

    assert slugify("Health-O-Mat Max") == "health_o_mat_max"
    assert slugify("Grüner Tee") == "gruner_tee"
    # Must be awaitable: a MagicMock here would swallow the missing `await`.
    assert hasattr(er.async_migrate_entries, "assert_awaited")
    assert callable(dr.async_get)
```

- [ ] **Step 2: Run the red command**

```bash
python3 -m pytest tests/test_wave_a.py -q -k fake_ha_provides
```

Expected: `ImportError: cannot import name 'slugify' from 'homeassistant.util'`
(oder `AttributeError: … has no attribute 'assert_awaited'`).

- [ ] **Step 3: Implement**

(a) `tests/conftest.py` — Imports ergänzen: `import re`, `import unicodedata`,
`from unittest.mock import AsyncMock`. Im Fake-Zweig (nach den Klassen-Definitionen, vor
`_FAKE_MODULES`) die Slug-Funktion:

```python
    def _slugify(value: Any) -> str:
        """Stand-in for ``homeassistant.util.slugify`` (ASCII, lower, `_`)."""
        text = unicodedata.normalize("NFKD", str(value))
        text = text.encode("ascii", "ignore").decode("ascii").lower()
        text = re.sub(r"[^a-z0-9]+", "_", text).strip("_")
        return text
```

(b) In `_FAKE_MODULES` die beiden Einträge ersetzen/erweitern:

```python
        "homeassistant.util": _module("homeassistant.util", slugify=_slugify),
        "homeassistant.helpers.entity_registry": _module(
            "homeassistant.helpers.entity_registry",
            async_get=MagicMock(),
            async_entries_for_config_entry=MagicMock(),
            # Coroutine-capable on purpose: a MagicMock would swallow a missing
            # `await` and mask exactly the B-1 bug (Spec §6.2).
            async_migrate_entries=AsyncMock(),
        ),
```

(c) In der Fake-`Entity`-Klasse (nach der `translation_key`-Property):

```python
        platform_data: Any = None

        @property
        def suggested_object_id(self) -> str | None:
            return None
```

(d) In `tests/test_wave_a.py::_load_init` die Modulliste erweitern:

```python
    for name in ("store", "entity", "const", "parser", "logic", "exporter", "migration"):
        _load(name)
```

- [ ] **Step 4: Run the green command**

```bash
python3 -m pytest tests/test_wave_a.py -q
python3 -m pytest -q
ruff check tests/conftest.py tests/test_wave_a.py
ruff format --check tests/conftest.py tests/test_wave_a.py
```

Expected: grün, keine Regression in der restlichen Suite.

- [ ] **Step 5: Commit**

```bash
git add tests/conftest.py tests/test_wave_a.py
git commit -m "test: extend fake HA modules for registry migration"
```

---

### Task 5: `button.py` + `sensor.py` — `suggested_object_id`-Pinning (A-5)

**Files:**
- Modify: `custom_components/health_o_mat/button.py`
- Modify: `custom_components/health_o_mat/sensor.py`
- Test: `tests/test_button.py`, `tests/test_sensor.py`

**Interfaces:**
- Consumes: `HealthOMatEntity.suggested_object_id` (`entity.py:34-54`).
- Produces:
  - `QuickDrinkButton.suggested_object_id -> f"quick_drink_{self._index + 1}"`
  - `LabValueSensor.suggested_object_id -> f"lab_{self._marker_key}"` (nur `is_custom`),
    sonst `super().suggested_object_id`
  - `QuickDrinkButton._index` (neues Attribut, zusätzlich zu `_ml`/`_label`/`_icon`)
- Verbraucher: Task 6 (Bestand und Neuinstallation müssen dasselbe Schema erzeugen),
  Task 11 (E2E-Regression), Task 12.

**Spec-Bezug:** §2.4 (Pinning für Neuregistrierungen, „Voraussetzung, nicht optional"),
Audit A-5, R-2.

> **Nur der Entity-Teil** wird geliefert — kein Device-Präfix (HA präfixt bei
> `has_entity_name = True` selbst). `_attr_name` bleibt unverändert (Anzeige).

- [ ] **Step 1: Write the failing tests**

In `tests/test_button.py` (nutzt die vorhandenen Helfer der Datei für `entry`/`store`):

```python
def test_req_hom_130_quick_drink_suggested_object_id_is_one_based():
    """[REQ-HOM-130] New quick drinks register as `quick_drink_<n>` (A-5)."""
    entry = _make_entry()
    button = button_module.QuickDrinkButton(MagicMock(), entry, MagicMock(), 2)

    assert button.suggested_object_id == "quick_drink_3"
    # The display name stays the user label — no literal name in the id.
    assert button.name == "Tasse Kaffee"
```

In `tests/test_sensor.py`:

```python
def test_req_hom_130_custom_lab_suggested_object_id_uses_key():
    """[REQ-HOM-130] Custom markers register as `lab_<key>` (A-5)."""
    sensor = _make_lab_sensor("vitamin_d", is_custom=True)
    assert sensor.suggested_object_id == "lab_vitamin_d"


def test_req_hom_130_catalog_lab_suggested_object_id_falls_back_to_base():
    """[REQ-HOM-130] Catalog markers keep the central English pinning."""
    sensor = _make_lab_sensor("crp", is_custom=False)
    assert sensor.suggested_object_id is None  # fake base -> no literal id
```

`_make_lab_sensor` folgt `tests/test_sensor.py:1176-1190` (baut `LabValueSensor` bereits
mit gemocktem Coordinator/Entry/Store); `_make_entry` folgt dem Muster der
`tests/test_button.py`-Setup-Tests (`entry.options["quick_drinks"]` mit den vier
Default-Labels, Index 2 = „Tasse Kaffee").

- [ ] **Step 2: Run the red command**

```bash
python3 -m pytest tests/test_button.py tests/test_sensor.py -q -k suggested_object_id
```

Expected: `AttributeError: 'QuickDrinkButton' object has no attribute 'platform_data'`
(der Basis-Override greift, weil kein Klassen-Override existiert) bzw.
`AssertionError: 'vitamin_d' != 'lab_vitamin_d'`.

- [ ] **Step 3: Implement**

`custom_components/health_o_mat/button.py` — `QuickDrinkButton.__init__` und neue Property:

```python
    def __init__(self, coordinator, entry, store, index: int) -> None:
        super().__init__(coordinator, entry, store, f"button_quick_{index}")
        quick_drinks = entry.options.get("quick_drinks") or DEFAULT_QUICK_DRINKS
        qd = quick_drinks[index]
        self._index = index  # slot index; stable, already part of the unique_id
        self._ml = int(qd.get("ml", 200))
        self._label = str(qd.get("label") or f"Quick {index + 1}")
        self._icon = str(qd.get("icon") or "mdi:cup-water")
        self._attr_name = self._label
        self._attr_icon = self._icon

    @property
    def suggested_object_id(self) -> str | None:
        """Object-id stem for new registrations (REQ-HOM-130, A-5).

        Only the entity part: HA still prefixes the device name because
        `has_entity_name = True`. Fresh installs therefore register the same
        ids the migration produces for existing ones.
        """
        return f"quick_drink_{self._index + 1}"
```

`custom_components/health_o_mat/sensor.py` — in `LabValueSensor` (nach `__init__`):

```python
    @property
    def suggested_object_id(self) -> str | None:
        """Custom markers register as `lab_<key>` (REQ-HOM-130, A-5).

        The catalog path keeps the central English pinning from
        `HealthOMatEntity.suggested_object_id`.
        """
        if self._marker_def.get("is_custom"):
            return f"lab_{self._marker_key}"
        return super().suggested_object_id
```

- [ ] **Step 4: Run the green command**

```bash
python3 -m pytest tests/test_button.py tests/test_sensor.py -q
python3 -m pytest -q
ruff check custom_components/health_o_mat/button.py custom_components/health_o_mat/sensor.py
ruff format --check custom_components/health_o_mat/button.py \
        custom_components/health_o_mat/sensor.py
```

Expected: grün, keine Regression (bestehende Setup-Tests prüfen die `unique_id`-Menge,
nicht `suggested_object_id`).

- [ ] **Step 5: Commit**

```bash
git add custom_components/health_o_mat/button.py custom_components/health_o_mat/sensor.py \
        tests/test_button.py tests/test_sensor.py
git commit -m "feat: pin quick drink and custom lab object ids"
```

---

### Task 6: `__init__.py` + `config_flow.py` — `async_migrate_entry` v3

**Files:**
- Modify: `custom_components/health_o_mat/__init__.py`
- Modify: `custom_components/health_o_mat/config_flow.py`
- Modify: `tests/test_config_flow.py`
- Modify: `tests/test_wave_a.py`
- Test: `tests/test_entry_migration.py` (neu, Happy-Path)

**Interfaces:**
- Consumes: `build_migration_plan`, `parse_custom_lab_key`, `quick_drink_target`,
  `custom_lab_target` (Tasks 1–3); `LAB_MARKERS`, `DEFAULT_QUICK_DRINKS`,
  `OPTION_LAB_CUSTOM_MARKERS`, `DOMAIN` (`const.py`); `logic.normalize_lab_custom_markers`.
- Produces:
  - `__init__.ENTITY_ID_MIGRATION_VERSION = 3`
  - `__init__._async_migrate_entity_ids(hass, entry) -> bool` (intern)
  - `__init__.async_migrate_entry(hass, entry) -> bool` (v1-Daten **und** v2→v3-Entity-IDs
    in **einem** `async_update_entry`)
  - `HealthOMatConfigFlow.VERSION = 3`
- Verbraucher: Task 7 (Negativfälle), Task 14–17 (Live-Lauf), Task 19 (Release).

**Spec-Bezug:** §3.2 (HA-Anbindung, Callback nur `new_entity_id`, Device-Anker,
State-Check best-effort, `ValueError`-Vertrag, `stale_marker_key`-Warnung,
`schema_drift`-Diagnose), §3.3 (`async_migrate_entry`-Verträge), §3.4
(Kollisionsverhalten), §3.5 (Randfälle), §5.2 (Test-Erwartungen `VERSION == 3`,
`test_wave_a`-Anpassung), §6.2 (Happy-Path-Tests).

- [ ] **Step 1: Write the failing tests**

(a) `tests/test_config_flow.py` — bestehende Erwartung anpassen:

```python
def test_config_flow_version():
    """ConfigFlow VERSION 3 (v1->v2 data, v2->v3 entity ids; REQ-HOM-101/130)."""
    config_flow = config_flow_module.HealthOMatConfigFlow()
    assert config_flow.VERSION == 3
```

(b) `tests/test_wave_a.py` — drei bestehende Tests anpassen (Spec §5.2):

```python
def test_config_entry_migration_v1_moves_quick_drinks_to_options():
    """[REQ-HOM-101/130] v1 entry: quick_drinks data -> options, version 3."""
    entry = MagicMock()
    entry.version = 1
    entry.title = "Health-O-Mat · Max"
    entry.data = {
        "person": "Max",
        "quick_drinks": [
            {"key": "glas_wasser", "label": "Glas Wasser", "ml": 200, "icon": "mdi:glass-water"}
        ],
    }
    entry.options = {}
    hass = MagicMock()
    hass.config_entries.async_update_entry = MagicMock()
    hass.states.async_all = MagicMock(return_value=[])
    _patch_empty_registries()  # siehe Hinweis unten

    ok = _run(_migrate_entry(entry, hass))

    assert ok is True
    updated = hass.config_entries.async_update_entry.call_args
    assert updated[1]["version"] == 3
    assert "quick_drinks" not in updated[1]["data"]
    assert updated[1]["options"]["quick_drinks"][0]["label"] == "Glas Wasser"


def test_config_entry_migration_v3_is_noop():
    """[REQ-HOM-101/130] A v3 entry is not touched again."""
    entry = MagicMock()
    entry.version = 3
    entry.data = {"person": "Max"}
    entry.options = {}
    hass = MagicMock()
    hass.config_entries.async_update_entry = MagicMock()

    ok = _run(_migrate_entry(entry, hass))

    assert ok is True
    hass.config_entries.async_update_entry.assert_not_called()


def test_config_entry_migration_rejects_downgrade():
    """[REQ-HOM-101/130] Version > 3 -> False (no downgrade)."""
    entry = MagicMock()
    entry.version = 4
    hass = MagicMock()
    ok = _run(_migrate_entry(entry, hass))
    assert ok is False
```

`_patch_empty_registries()` (Helfer am Ende von `tests/test_wave_a.py`) monkeypatcht
`homeassistant.helpers.entity_registry.async_get`/`async_entries_for_config_entry` und
`homeassistant.helpers.device_registry.async_get` auf leere Fakes — identisch zu
`tests/test_entry_migration.py` (Step 1c, `_install`). Die leere Registry macht den
v1-Test unabhängig von Entity-Daten und hält ihn auf seinem ursprünglichen Prüfziel
(„Datenmigration"), während die Entity-Renames in `tests/test_entry_migration.py`
vollständig abgedeckt sind.

(c) `tests/test_entry_migration.py` (neu) — Gerüst + Happy-Path:

```python
"""Tests: `async_migrate_entry` v2->v3 against a fake registry (REQ-HOM-130).

`__init__.py` is loaded via importlib like in `tests/test_wave_a.py` (own package
prefix so the two modules do not collide in the `sys.modules` cache).
`er.async_migrate_entries` is an `AsyncMock` whose side effect actually applies
the callback dicts — only then do the mapping and the drift diagnosis get
exercised instead of just the `await` (Spec §6.2).
"""

from __future__ import annotations

import asyncio
import importlib.util
import os
import sys
import types
from dataclasses import dataclass, field
from unittest.mock import AsyncMock, MagicMock

import homeassistant.helpers.device_registry as dr
import homeassistant.helpers.entity_registry as er

_COMPONENT_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "custom_components", "health_o_mat")
)
_PKG = "_hom_entry_migration_pkg"
_pkg = types.ModuleType(_PKG)
_pkg.__path__ = [_COMPONENT_DIR]
sys.modules.setdefault(_PKG, _pkg)

ENTRY_ID = "01JENTRY"
SLUG = "health_o_mat_max"
DEVICE_ID = "dev1"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(
        f"{_PKG}.{name}", os.path.join(_COMPONENT_DIR, f"{name}.py")
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[f"{_PKG}.{name}"] = module
    spec.loader.exec_module(module)
    return module


def _load_init():
    for name in ("store", "entity", "const", "parser", "logic", "exporter", "migration"):
        _load(name)
    spec = importlib.util.spec_from_file_location(
        f"{_PKG}.init", os.path.join(_COMPONENT_DIR, "__init__.py")
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[f"{_PKG}.init"] = module
    spec.loader.exec_module(module)
    return module


@dataclass
class _RegEntry:
    entity_id: str
    unique_id: str
    translation_key: str | None = None
    device_id: str | None = DEVICE_ID
    config_entry_id: str = ENTRY_ID
    original_name: str | None = None
    entity_category: str | None = None
    labels: set[str] = field(default_factory=set)
    aliases: list[str] = field(default_factory=list)
    area_id: str | None = None
    hidden_by: str | None = None
    disabled_by: str | None = None


class _FakeRegistry:
    def __init__(self, entries: list[_RegEntry]) -> None:
        self.entities = {entry.entity_id: entry for entry in entries}

    def async_get(self, entity_id: str) -> _RegEntry | None:
        return self.entities.get(entity_id)


class _FakeDevice:
    def __init__(self, name: str, name_by_user: str | None = None) -> None:
        self.id = DEVICE_ID
        self.name = name
        self.name_by_user = name_by_user
        self.identifiers = {("health_o_mat", ENTRY_ID)}


class _FakeDeviceRegistry:
    def __init__(self, device: _FakeDevice | None) -> None:
        self._device = device

    def async_get_device_by_identifier(self, identifiers, config_entry_id):
        if self._device is not None and ("health_o_mat", config_entry_id) in self._device.identifiers:
            return self._device
        return None

    def async_get(self, device_id: str | None):
        if self._device is not None and device_id == self._device.id:
            return self._device
        return None


def _make_hass(*, states: list | None = None) -> MagicMock:
    hass = MagicMock()
    hass.states.async_all = MagicMock(return_value=list(states or []))
    hass.config_entries.async_update_entry = MagicMock()
    return hass


def _make_entry(*, version: int = 2, data: dict | None = None, options: dict | None = None):
    entry = MagicMock()
    entry.entry_id = ENTRY_ID
    entry.version = version
    entry.title = "Health-O-Mat · Max"
    entry.data = data if data is not None else {"person": "Max"}
    entry.options = options if options is not None else {}
    return entry


def _install(monkeypatch, registry: _FakeRegistry, device: _FakeDevice | None):
    """Wire the fake registries into the fake HA modules; return the AsyncMock."""
    migrate = AsyncMock()

    async def _apply(hass, config_entry_id, update_callback):
        for reg in list(registry.entities.values()):
            if reg.config_entry_id != config_entry_id:
                continue
            changes = update_callback(reg)
            if not changes:
                continue
            new_id = changes["new_entity_id"]
            registry.entities.pop(reg.entity_id)
            reg.entity_id = new_id
            registry.entities[new_id] = reg

    migrate.side_effect = _apply
    monkeypatch.setattr(er, "async_migrate_entries", migrate)
    monkeypatch.setattr(
        er,
        "async_entries_for_config_entry",
        lambda reg, config_entry_id: [
            item
            for item in reg.entities.values()
            if item.config_entry_id == config_entry_id
        ],
    )
    monkeypatch.setattr(er, "async_get", lambda hass: registry)
    monkeypatch.setattr(dr, "async_get", lambda hass: _FakeDeviceRegistry(device))
    return migrate


def _standard_entries() -> list[_RegEntry]:
    return [
        _RegEntry(
            f"button.{SLUG}_glas_wasser",
            f"{ENTRY_ID}_button_quick_0",
            original_name="Glas Wasser",
        ),
        _RegEntry(
            f"button.{SLUG}_tasse_kaffee",
            f"{ENTRY_ID}_button_quick_2",
            original_name="Kaffee",
        ),
        _RegEntry(
            f"sensor.{SLUG}_vitamin_d",
            f"{ENTRY_ID}_lab_vitamin_d",
            original_name="Vitamin D",
        ),
        _RegEntry(f"sensor.{SLUG}_crp", f"{ENTRY_ID}_lab_crp", "lab_crp", original_name="CRP"),
        _RegEntry(
            f"sensor.{SLUG}_drinks_today",
            f"{ENTRY_ID}_today",
            "today",
            original_name="Heute getrunken",
        ),
        _RegEntry(
            f"sensor.{SLUG}_daily_goal_progress",
            f"{ENTRY_ID}_goal_percent",
            "goal_percent",
            original_name="Tagesziel",
        ),
        _RegEntry(
            f"button.{SLUG}_book_custom_amount",
            f"{ENTRY_ID}_button_book_custom",
            "book_custom",
            original_name="Eigene Menge",
        ),
    ]


def test_req_hom_130_migrates_quick_and_custom_only(monkeypatch):
    registry = _FakeRegistry(_standard_entries())
    migrate = _install(monkeypatch, registry, _FakeDevice("Health-O-Mat Max"))
    init = _load_init()
    hass = _make_hass()

    assert asyncio.run(init.async_migrate_entry(hass, _make_entry())) is True

    assert migrate.await_count == 1
    callback = migrate.call_args.args[2]
    applied = {}
    for reg in _standard_entries():
        changes = callback(reg)
        if changes:
            applied[reg.entity_id] = changes["new_entity_id"]
    assert applied == {
        f"button.{SLUG}_glas_wasser": f"button.{SLUG}_quick_drink_1",
        f"button.{SLUG}_tasse_kaffee": f"button.{SLUG}_quick_drink_3",
        f"sensor.{SLUG}_vitamin_d": f"sensor.{SLUG}_lab_vitamin_d",
    }


def test_req_hom_130_callback_sets_only_new_entity_id(monkeypatch):
    registry = _FakeRegistry(_standard_entries())
    migrate = _install(monkeypatch, registry, _FakeDevice("Health-O-Mat Max"))
    init = _load_init()

    assert asyncio.run(init.async_migrate_entry(_make_hass(), _make_entry())) is True

    callback = migrate.call_args.args[2]
    for reg in _standard_entries():
        changes = callback(reg)
        if changes:
            assert set(changes) == {"new_entity_id"}


def test_req_hom_130_awaits_async_migrate_entries(monkeypatch):
    """B-1 regression: a non-awaited call fails this test."""
    registry = _FakeRegistry(_standard_entries())
    migrate = _install(monkeypatch, registry, _FakeDevice("Health-O-Mat Max"))
    init = _load_init()

    asyncio.run(init.async_migrate_entry(_make_hass(), _make_entry()))

    migrate.assert_awaited_once()


def test_req_hom_130_bumps_to_version_3_on_success(monkeypatch):
    registry = _FakeRegistry(_standard_entries())
    _install(monkeypatch, registry, _FakeDevice("Health-O-Mat Max"))
    init = _load_init()
    hass = _make_hass()
    entry = _make_entry(
        options={"lab_custom_markers": [{"name": "Vitamin D", "unit": "ng/mL"}]}
    )

    assert asyncio.run(init.async_migrate_entry(hass, entry)) is True

    hass.config_entries.async_update_entry.assert_called_once()
    _args, kwargs = hass.config_entries.async_update_entry.call_args
    assert kwargs["version"] == 3
    assert kwargs["data"] == {"person": "Max"}
    assert "lab_custom_markers" in kwargs["options"]


def test_req_hom_130_downgrade_guard_v4(monkeypatch):
    _install(monkeypatch, _FakeRegistry(_standard_entries()), _FakeDevice("Health-O-Mat Max"))
    init = _load_init()
    hass = _make_hass()

    assert asyncio.run(init.async_migrate_entry(hass, _make_entry(version=4))) is False
    hass.config_entries.async_update_entry.assert_not_called()
```

- [ ] **Step 2: Run the red command**

```bash
python3 -m pytest tests/test_entry_migration.py tests/test_config_flow.py tests/test_wave_a.py -q
```

Expected: `assert 2 == 3` (`test_config_flow_version`); der Handler läuft noch ohne
Registry-Pass (`migrate.await_count == 0` / `assert_awaited_once` schlägt fehl).

- [ ] **Step 3: Implement**

(a) `custom_components/health_o_mat/config_flow.py:250`:

```python
    # v3: entity ids of quick-drink buttons and custom lab markers (REQ-HOM-130).
    VERSION = 3
```

(b) `custom_components/health_o_mat/__init__.py` — Imports ergänzen:

```python
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.util import slugify

from .const import LAB_MARKERS
from .migration import (
    build_migration_plan,
    custom_lab_target,
    parse_custom_lab_key,
    parse_quick_drink_index,
    quick_drink_target,
)
```

(c) Modulkonstante direkt vor `type HealthOMatConfigEntry`:

```python
# Config entry version that carries the entity id migration (REQ-HOM-130).
# Kept next to the handler so `tests/test_entry_migration.py` can assert it
# equals `HealthOMatConfigFlow.VERSION` (drift guard).
ENTITY_ID_MIGRATION_VERSION = 3
```

(d) `async_migrate_entry` durch `_async_migrate_entity_ids` + neuen Handler ersetzen:

```python
async def _async_migrate_entity_ids(hass: HomeAssistant, entry: HealthOMatConfigEntry) -> bool:
    """Rename F-1/F-2 entities to the language-independent scheme (REQ-HOM-130).

    Returns True only when nothing was skipped and no schema drift remains.
    Fail-closed: the caller keeps the entry version untouched on False, so HA
    retries the whole pass on the next start.
    """
    registry = er.async_get(hass)
    entries = er.async_entries_for_config_entry(registry, entry.entry_id)

    device_registry = dr.async_get(hass)
    # HA 2026.9: `async_get_device(identifiers=...)` is deprecated.
    device = device_registry.async_get_device_by_identifier(
        (DOMAIN, entry.entry_id), entry.entry_id
    )
    if device is None:
        fallback_id = next((reg.device_id for reg in entries if reg.device_id), None)
        device = device_registry.async_get(fallback_id) if fallback_id else None
    hint = slugify(device.name_by_user or device.name) if device is not None else None

    # The registry is authoritative; the state check is best effort (restored
    # states only exist after EVENT_HOMEASSISTANT_START).
    occupied = {reg.entity_id for reg in registry.entities.values()}
    occupied.update(state.entity_id for state in hass.states.async_all())

    plan = build_migration_plan(
        entry.entry_id,
        [
            {
                "entity_id": reg.entity_id,
                "unique_id": reg.unique_id,
                "translation_key": reg.translation_key,
                "device_id": reg.device_id,
            }
            for reg in entries
        ],
        device_slug_hint=hint,
        device_id=device.id if device is not None else None,
        catalog_keys=LAB_MARKERS,
        occupied_entity_ids=occupied,
    )

    known_marker_keys = {
        marker["key"]
        for marker in logic.normalize_lab_custom_markers(
            entry.options.get(OPTION_LAB_CUSTOM_MARKERS)
        )
    }
    for rename in plan.renames:
        key = parse_custom_lab_key(rename.unique_id, entry.entry_id, LAB_MARKERS)
        if key is not None and key not in known_marker_keys:
            _LOGGER.warning(
                "Entity-ID-Migration %s: stale_marker_key %s (%s) — Entity wird "
                "umbenannt, der Key fehlt in den Options",
                entry.title,
                key,
                rename.source_entity_id,
            )

    mapping = {item.source_entity_id: item.target_entity_id for item in plan.renames}
    if mapping:
        try:
            # Coroutine since HA 2026.8 — must be awaited (B-1).
            await er.async_migrate_entries(
                hass,
                entry.entry_id,
                lambda reg: (
                    {"new_entity_id": mapping[reg.entity_id]}
                    if reg.entity_id in mapping
                    else None
                ),
            )
        except ValueError as err:
            # Race with a parallel registry write: HA would turn this into
            # MIGRATION_ERROR; we treat it as a failed pass with a clear cause.
            _LOGGER.error("Entity-ID-Migration %s abgebrochen: %s", entry.title, err)
            return False

    # Drift diagnosis: every F-1/F-2 entity must now sit on its expected id.
    drift: list[tuple[str, str]] = []
    if plan.device_slug is not None:
        for reg in er.async_entries_for_config_entry(registry, entry.entry_id):
            index = parse_quick_drink_index(reg.unique_id, entry.entry_id)
            key = parse_custom_lab_key(reg.unique_id, entry.entry_id, LAB_MARKERS)
            if index is not None:
                expected = f"button.{quick_drink_target(plan.device_slug, index)}"
            elif key is not None:
                expected = f"sensor.{custom_lab_target(plan.device_slug, key)}"
            else:
                continue
            if reg.entity_id != expected:
                drift.append((reg.entity_id, expected))
    if drift:
        _LOGGER.warning(
            "Entity-ID-Migration %s: schema_drift %d — %s",
            entry.title,
            len(drift),
            drift,
        )

    for skip in plan.skipped:
        _LOGGER.warning(
            "Entity-ID-Migration %s: %s (%s) übersprungen — Ziel %s, Grund %s",
            entry.title,
            skip.source_entity_id,
            skip.unique_id,
            skip.target_entity_id,
            skip.reason,
        )
    return not plan.skipped and not drift


async def async_migrate_entry(hass: HomeAssistant, entry: HealthOMatConfigEntry) -> bool:
    """Config entry migration: v1 quick_drinks -> options, v2 -> v3 entity ids.

    v1 (<= v0.4.0) kept `quick_drinks` in entry.data (only removable by
    re-creating the entry = data loss). v2 (<= v0.16.2) still registered
    quick-drink buttons and custom lab markers from user text; v3 renames them
    to `quick_drink_<n>` / `lab_<key>` (REQ-HOM-130).

    All-or-nothing: data, options and version are written in exactly ONE
    `async_update_entry` call, and only when the entity pass fully succeeded.
    """
    if entry.version > ENTITY_ID_MIGRATION_VERSION:
        # Defensive: HA only calls the handler for entry.version < flow.VERSION.
        _LOGGER.error(
            "Config entry %s hat Version %s > %s — Downgrade nicht unterstützt",
            entry.title,
            entry.version,
            ENTITY_ID_MIGRATION_VERSION,
        )
        return False

    data = dict(entry.data)
    options = dict(entry.options)

    if entry.version == 1:
        options.setdefault("quick_drinks", [dict(qd) for qd in DEFAULT_QUICK_DRINKS])
        data = {k: v for k, v in data.items() if k != "quick_drinks"}

    if entry.version < ENTITY_ID_MIGRATION_VERSION and not await _async_migrate_entity_ids(
        hass, entry
    ):
        # No async_update_entry: the version stays, HA retries on the next setup
        # and the v1 data step is not half-written either.
        return False

    if entry.version < ENTITY_ID_MIGRATION_VERSION:
        hass.config_entries.async_update_entry(
            entry, data=data, options=options, version=ENTITY_ID_MIGRATION_VERSION
        )
        _LOGGER.info(
            "Config entry %s: auf Version %s migriert",
            entry.title,
            ENTITY_ID_MIGRATION_VERSION,
        )
    return True
```

- [ ] **Step 4: Run the green command**

```bash
python3 -m pytest tests/test_entry_migration.py tests/test_config_flow.py tests/test_wave_a.py -q
python3 -m pytest -q
ruff check custom_components/health_o_mat/__init__.py custom_components/health_o_mat/config_flow.py \
        tests/test_entry_migration.py tests/test_wave_a.py tests/test_config_flow.py
ruff format --check custom_components/health_o_mat/__init__.py \
        custom_components/health_o_mat/config_flow.py tests/test_entry_migration.py
```

Expected: grün. Insbesondere `migrate.await_count == 1`, `{"new_entity_id"}` als einziger
Callback-Key, genau ein `async_update_entry` mit `version=3`.

- [ ] **Step 5: Commit**

```bash
git add custom_components/health_o_mat/__init__.py custom_components/health_o_mat/config_flow.py \
        tests/test_entry_migration.py tests/test_wave_a.py tests/test_config_flow.py
git commit -m "feat: migrate entity ids on config entry version 3"
```

---

### Task 7: `tests/test_entry_migration.py` — Negativ-, Retry- und Drift-Fälle

**Files:**
- Test: `tests/test_entry_migration.py`
- Modify (nur falls ein Test eine echte Lücke zeigt): `custom_components/health_o_mat/__init__.py`

**Interfaces:**
- Consumes: Helfer aus Task 6 (`_load_init`, `_FakeRegistry`, `_install`, `_make_hass`,
  `_make_entry`, `_standard_entries`, `_RegEntry`).
- Produces: vollständige Abdeckung der Spec-Tabelle §6.2.

**Spec-Bezug:** §6.2 (restliche Tests), §3.3 (Idempotenz, Atomarität, Fehler), §3.4
(Kollision/Retry), §3.5 (`stale_marker_key`, Race-`ValueError`, deaktivierte Entities),
§6.5 AK 4/7.

- [ ] **Step 1: Write the failing tests**

Ans Ende von `tests/test_entry_migration.py`:

```python
def test_req_hom_130_collision_skips_and_keeps_version(monkeypatch, caplog):
    registry = _FakeRegistry(_standard_entries())
    _install(monkeypatch, registry, _FakeDevice("Health-O-Mat Max"))
    init = _load_init()
    hass = _make_hass(states=[MagicMock(entity_id=f"button.{SLUG}_quick_drink_1")])

    with caplog.at_level("WARNING"):
        ok = asyncio.run(init.async_migrate_entry(hass, _make_entry()))

    assert ok is False
    hass.config_entries.async_update_entry.assert_not_called()
    assert "target_occupied" in caplog.text
    # Pair list, not just a count.
    assert f"button.{SLUG}_glas_wasser" in caplog.text


def test_req_hom_130_collision_retry_after_fix(monkeypatch):
    registry = _FakeRegistry(_standard_entries())
    _install(monkeypatch, registry, _FakeDevice("Health-O-Mat Max"))
    init = _load_init()
    entry = _make_entry()

    first_hass = _make_hass(states=[MagicMock(entity_id=f"button.{SLUG}_quick_drink_1")])
    assert asyncio.run(init.async_migrate_entry(first_hass, entry)) is False
    first_hass.config_entries.async_update_entry.assert_not_called()
    # Everything else was renamed — the retry only has the collision left.
    assert registry.async_get(f"button.{SLUG}_quick_drink_3") is not None
    assert registry.async_get(f"sensor.{SLUG}_lab_vitamin_d") is not None

    second_hass = _make_hass(states=[])
    assert asyncio.run(init.async_migrate_entry(second_hass, entry)) is True
    second_hass.config_entries.async_update_entry.assert_called_once()
    assert registry.async_get(f"button.{SLUG}_quick_drink_1") is not None


def test_req_hom_130_value_error_fails_closed(monkeypatch, caplog):
    registry = _FakeRegistry(_standard_entries())
    migrate = _install(monkeypatch, registry, _FakeDevice("Health-O-Mat Max"))
    migrate.side_effect = ValueError("Entity id already exists")
    init = _load_init()
    hass = _make_hass()

    with caplog.at_level("ERROR"):
        ok = asyncio.run(init.async_migrate_entry(hass, _make_entry()))

    assert ok is False
    hass.config_entries.async_update_entry.assert_not_called()
    assert "abgebrochen" in caplog.text


def test_req_hom_130_stale_marker_key_warns_but_renames(monkeypatch, caplog):
    registry = _FakeRegistry(_standard_entries())
    _install(monkeypatch, registry, _FakeDevice("Health-O-Mat Max"))
    init = _load_init()
    hass = _make_hass()

    with caplog.at_level("WARNING"):
        # Options do NOT list vitamin_d -> registry wins, rename still happens.
        ok = asyncio.run(
            init.async_migrate_entry(
                hass, _make_entry(options={"lab_custom_markers": []})
            )
        )

    assert ok is True
    assert "stale_marker_key vitamin_d" in caplog.text
    assert registry.async_get(f"sensor.{SLUG}_lab_vitamin_d") is not None


def test_req_hom_130_schema_drift_warns_and_fails(monkeypatch, caplog):
    registry = _FakeRegistry(_standard_entries())
    migrate = _install(monkeypatch, registry, _FakeDevice("Health-O-Mat Max"))
    # Simulate a silently broken pass: the callback is never applied.
    migrate.side_effect = None
    migrate.return_value = None
    init = _load_init()
    hass = _make_hass()

    with caplog.at_level("WARNING"):
        ok = asyncio.run(init.async_migrate_entry(hass, _make_entry()))

    assert ok is False
    hass.config_entries.async_update_entry.assert_not_called()
    assert "schema_drift" in caplog.text


def test_req_hom_130_second_run_is_noop(monkeypatch):
    registry = _FakeRegistry(_standard_entries())
    migrate = _install(monkeypatch, registry, _FakeDevice("Health-O-Mat Max"))
    init = _load_init()
    hass = _make_hass()

    assert asyncio.run(init.async_migrate_entry(hass, _make_entry(version=3))) is True

    migrate.assert_not_awaited()
    hass.config_entries.async_update_entry.assert_not_called()


def test_req_hom_130_v1_entry_is_migrated_to_v3_in_one_update(monkeypatch):
    registry = _FakeRegistry(_standard_entries())
    _install(monkeypatch, registry, _FakeDevice("Health-O-Mat Max"))
    init = _load_init()
    hass = _make_hass()
    entry = _make_entry(
        version=1,
        data={
            "person": "Max",
            "quick_drinks": [{"key": "glas_wasser", "label": "Glas Wasser", "ml": 200}],
        },
    )

    assert asyncio.run(init.async_migrate_entry(hass, entry)) is True

    hass.config_entries.async_update_entry.assert_called_once()
    _args, kwargs = hass.config_entries.async_update_entry.call_args
    assert kwargs["version"] == 3
    assert "quick_drinks" not in kwargs["data"]
    assert kwargs["options"]["quick_drinks"][0]["label"] == "Glas Wasser"
    assert registry.async_get(f"button.{SLUG}_quick_drink_1") is not None


def test_req_hom_130_v1_entity_failure_does_not_write_data(monkeypatch):
    registry = _FakeRegistry(_standard_entries())
    _install(monkeypatch, registry, _FakeDevice("Health-O-Mat Max"))
    init = _load_init()
    hass = _make_hass(states=[MagicMock(entity_id=f"button.{SLUG}_quick_drink_1")])
    entry = _make_entry(
        version=1,
        data={"person": "Max", "quick_drinks": [{"label": "Glas Wasser", "ml": 200}]},
    )

    assert asyncio.run(init.async_migrate_entry(hass, entry)) is False
    hass.config_entries.async_update_entry.assert_not_called()


def test_req_hom_130_no_entities_still_bumps_version(monkeypatch):
    _install(monkeypatch, _FakeRegistry([]), _FakeDevice("Health-O-Mat Max"))
    init = _load_init()
    hass = _make_hass()

    assert asyncio.run(init.async_migrate_entry(hass, _make_entry())) is True
    hass.config_entries.async_update_entry.assert_called_once()


def test_req_hom_130_state_machine_target_counts_as_occupied(monkeypatch):
    registry = _FakeRegistry(_standard_entries())
    _install(monkeypatch, registry, _FakeDevice("Health-O-Mat Max"))
    init = _load_init()
    # Target exists only in the state machine (no registry entry).
    hass = _make_hass(states=[MagicMock(entity_id=f"sensor.{SLUG}_lab_vitamin_d")])

    assert asyncio.run(init.async_migrate_entry(hass, _make_entry())) is False
    hass.config_entries.async_update_entry.assert_not_called()


def test_req_hom_130_migration_version_matches_config_flow():
    init = _load_init()
    config_flow = _load("config_flow")
    assert init.ENTITY_ID_MIGRATION_VERSION == config_flow.HealthOMatConfigFlow.VERSION


def test_req_hom_130_registry_fields_survive_the_rename(monkeypatch):
    quick = _RegEntry(
        f"button.{SLUG}_glas_wasser",
        f"{ENTRY_ID}_button_quick_0",
        original_name="Glas Wasser",
        entity_category="config",
        labels={"quick"},
        aliases=["button.glas_wasser"],
        area_id="kitchen",
        hidden_by="user",
        disabled_by=None,
    )
    today = _RegEntry(
        f"sensor.{SLUG}_drinks_today", f"{ENTRY_ID}_today", "today", original_name="Heute"
    )
    goal = _RegEntry(
        f"sensor.{SLUG}_daily_goal_progress",
        f"{ENTRY_ID}_goal_percent",
        "goal_percent",
        original_name="Ziel",
    )
    registry = _FakeRegistry([quick, today, goal])
    _install(monkeypatch, registry, _FakeDevice("Health-O-Mat Max"))
    init = _load_init()

    assert asyncio.run(init.async_migrate_entry(_make_hass(), _make_entry())) is True

    migrated = registry.async_get(f"button.{SLUG}_quick_drink_1")
    assert migrated is quick  # same registry record, only entity_id changed
    assert migrated.unique_id == f"{ENTRY_ID}_button_quick_0"
    assert migrated.original_name == "Glas Wasser"
    assert migrated.entity_category == "config"
    assert migrated.labels == {"quick"}
    assert migrated.aliases == ["button.glas_wasser"]
    assert migrated.area_id == "kitchen"
    assert migrated.hidden_by == "user"
    assert migrated.disabled_by is None
```

- [ ] **Step 2: Run the red command**

```bash
python3 -m pytest tests/test_entry_migration.py -q
```

Expected: die neuen Fälle scheitern zuerst dort, wo Task 6 eine Lücke lässt — typisch
`assert 'schema_drift' in caplog.text` (Drift-Zweig fehlt) oder
`assert registry.async_get(...) is not None` (Callback filtert falsch). Jeder rote Fall
wird **in `__init__.py`** behoben, nicht durch Aufweichen des Tests.

- [ ] **Step 3: Implement (nur falls rot)**

| Rot | Ursache | Behebung in `__init__.py` |
|---|---|---|
| `schema_drift` fehlt | Drift-Block nicht übernommen | Drift-Block aus Task 6 Step 3 (d) unverändert einsetzen |
| `await_count == 0` | `async_migrate_entries` nicht awaited | `await` vor den Aufruf |
| Retry benennt den Rest nicht | `mapping` nach dem Pass gebildet | Reihenfolge beibehalten: Plan → Mapping → Pass |
| `assert_called_once` schlägt fehl | `async_update_entry` auch im Fehlerpfad | nur im Erfolgszweig schreiben |

- [ ] **Step 4: Run the green command**

```bash
python3 -m pytest tests/test_entry_migration.py -q
python3 -m pytest -q
ruff check tests/test_entry_migration.py custom_components/health_o_mat/__init__.py
ruff format --check tests/test_entry_migration.py custom_components/health_o_mat/__init__.py
```

Expected: **17 Tests** in `tests/test_entry_migration.py` grün (5 aus Task 6 + 12 hier),
volle Suite grün.

- [ ] **Step 5: Commit**

```bash
git add tests/test_entry_migration.py custom_components/health_o_mat/__init__.py
git commit -m "test: cover migration collisions retries and drift"
```

---

## Wave 3 — Härtungen A-1…A-4

### Task 8: `logic.py` — A-1 Kategorie-Validierung + A-2 Key-Erhalt

**Files:**
- Modify: `custom_components/health_o_mat/logic.py`
- Test: `tests/test_logic.py`

**Interfaces:**
- Consumes: `LAB_CATEGORIES`, `LAB_CATEGORY_OTHER`, `LAB_MARKERS`,
  `_slugify_lab_marker_name`.
- Produces:
  - `normalize_lab_custom_markers(raw: Any, previous: Any = None) -> list[dict]`
    (rückwärtskompatibel; `previous=None` = bisheriges Verhalten)
  - intern: `_previous_marker_keys(previous: Any) -> dict[str, str]`
- Verbraucher: Task 9 (`ws_api.parse_settings_message`, `restore.merge_lab_custom_markers`);
  `__init__._lab_options_snapshot` und `logic.effective_lab_markers` bleiben **unverändert**.

**Spec-Bezug:** §4 A-1, §4 A-2, §6.1 (`test_req_hom_130_normalize_*`), Audit F-3/R-5,
R-6 (bekannte Grenze, kein Fix in diesem Scope).

- [ ] **Step 1: Write the failing tests**

Ans Ende von `tests/test_logic.py`:

```python
# --- REQ-HOM-130/131: custom marker hardening (A-1/A-2) --------------------


def test_req_hom_130_normalize_rejects_unknown_category():
    from custom_components.health_o_mat import logic

    normalized = logic.normalize_lab_custom_markers(
        [
            {"name": "Vitamin D", "unit": "ng/mL", "category": "vitamins"},
            {"name": "CRP", "unit": "mg/L", "category": "inflammation"},
            {"name": "Ferritin", "unit": "µg/L", "category": ""},
            {"name": "Hämoglobin", "unit": "g/dL", "category": "Blood_Count"},
        ]
    )
    assert [item["category"] for item in normalized] == [
        "other",
        "inflammation",
        "other",
        "blood_count",
    ]


def test_req_hom_130_normalize_keeps_key_for_previous_name():
    from custom_components.health_o_mat import logic

    previous = [{"key": "vitamin_d", "name": "Vitamin D", "unit": "ng/mL"}]
    normalized = logic.normalize_lab_custom_markers(
        [{"name": "Vitamin D", "unit": "ng/mL", "category": "other"}], previous
    )
    assert normalized[0]["key"] == "vitamin_d"


def test_req_hom_130_normalize_explicit_key_wins():
    from custom_components.health_o_mat import logic

    previous = [{"key": "vitamin_d", "name": "Vitamin D", "unit": "ng/mL"}]
    normalized = logic.normalize_lab_custom_markers(
        [{"name": "Vitamin D", "unit": "ng/mL", "key": "vit_d3"}], previous
    )
    assert normalized[0]["key"] == "vit_d3"


def test_req_hom_130_normalize_new_name_gets_new_key():
    from custom_components.health_o_mat import logic

    previous = [{"key": "vitamin_d", "name": "Vitamin D", "unit": "ng/mL"}]
    normalized = logic.normalize_lab_custom_markers(
        [{"name": "Ferritin gesamt", "unit": "µg/L"}], previous
    )
    assert normalized[0]["key"] == "ferritin_gesamt"


def test_req_hom_130_normalize_without_previous_unchanged():
    from custom_components.health_o_mat import logic

    raw = [{"name": "Vitamin D", "unit": "ng/mL", "category": "vitamins"}]
    assert logic.normalize_lab_custom_markers(raw) == [
        {"key": "vitamin_d", "name": "Vitamin D", "category": "other", "unit": "ng/mL"}
    ]
```

- [ ] **Step 2: Run the red command**

```bash
python3 -m pytest tests/test_logic.py -q -k "req_hom_130_normalize"
```

Expected: `TypeError: normalize_lab_custom_markers() takes 1 positional argument but 2 were
given` und `AssertionError: 'vitamins' != 'other'`.

- [ ] **Step 3: Implement**

`custom_components/health_o_mat/logic.py` — neuen Helfer vor den Normalisierer setzen und
den Body anpassen:

```python
def _previous_marker_keys(previous: Any) -> dict[str, str]:
    """``stripped name -> key`` from already persisted markers (first hit wins)."""
    keys: dict[str, str] = {}
    if not isinstance(previous, list):
        return keys
    for item in previous:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        key = str(item.get("key") or "").strip().lower()
        if name and key:
            keys.setdefault(name, key)
    return keys


def normalize_lab_custom_markers(raw: Any, previous: Any = None) -> list[dict]:
    """`entry.options["lab_custom_markers"]` normalisieren (HA-frei, §2.2).

    Jeder Eintrag erhält einen stabilen `key` (slugify aus `name`, bei
    Kollision mit einem Katalog-Key ODER einem bereits vergebenen Custom-Key
    dieses Aufrufs mit `_2`/`_3`/... suffixiert — Reihenfolge bleibt stabil).
    Unbrauchbare Einträge (kein `name`/`unit`) werden übersprungen, kein
    Absturz bei Teil-Murks aus altem Options-Bestand.

    REQ-HOM-130: `previous` schützt den `key` gegen Fremd-Client-Drift (A-2) —
    ein Eintrag ohne `key`, dessen `name` exakt einem gespeicherten Marker
    entspricht, erbt dessen `key` statt neu geslugt zu werden (der `key` ist
    Teil der `unique_id`). Ein explizit gesendeter `key` gewinnt immer.
    A-1: eine `category` außerhalb von `LAB_CATEGORIES` fällt auf `other`.
    """
    if not isinstance(raw, list):
        return []
    inherited = _previous_marker_keys(previous)
    known_categories = {category["key"] for category in LAB_CATEGORIES}
    used_keys: set[str] = set(LAB_MARKERS.keys())
    result: list[dict] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        unit = str(item.get("unit") or "").strip()
        if not name or not unit:
            continue
        explicit_key = str(item.get("key") or "").strip().lower()
        if explicit_key:
            base_key = explicit_key
        else:
            base_key = inherited.get(name) or _slugify_lab_marker_name(name)
        key = base_key
        suffix = 2
        while key in used_keys:
            key = f"{base_key}_{suffix}"
            suffix += 1
        used_keys.add(key)

        category = str(item.get("category") or "").strip().lower()
        if category not in known_categories:
            category = LAB_CATEGORY_OTHER
        entry: dict[str, Any] = {
            "key": key,
            "name": name,
            "category": category,
            "unit": unit,
        }
        # ref_min / ref_max / alt_unit: unverändert aus dem bisherigen Body
        # übernehmen (keine inhaltliche Änderung in diesem Task).
        result.append(entry)
    return result
```

- [ ] **Step 4: Run the green command**

```bash
python3 -m pytest tests/test_logic.py -q
python3 -m pytest -q
ruff check custom_components/health_o_mat/logic.py tests/test_logic.py
ruff format --check custom_components/health_o_mat/logic.py tests/test_logic.py
```

Expected: grün. **Regressionswächter:** alle bestehenden
`normalize_lab_custom_markers`-Tests (`tests/test_logic.py`, `tests/test_ws_api.py`,
`tests/test_restore.py`, `tests/test_import_backup.py`) bleiben unverändert grün —
`previous=None` darf das Altverhalten nicht verschieben.

- [ ] **Step 5: Commit**

```bash
git add custom_components/health_o_mat/logic.py tests/test_logic.py
git commit -m "feat: validate lab marker category and keep marker keys"
```

---

### Task 9: A-2-Aufrufstellen — `ws_api.parse_settings_message` + `restore`

**Files:**
- Modify: `custom_components/health_o_mat/ws_api.py`
- Modify: `custom_components/health_o_mat/restore.py`
- Test: `tests/test_ws_api.py`, `tests/test_restore.py`

**Interfaces:**
- Consumes: `logic.normalize_lab_custom_markers(raw, previous)` (Task 8),
  `OPTION_LAB_CUSTOM_MARKERS`.
- Produces:
  - `ws_api.parse_settings_message(msg, *, previous_markers=None) -> tuple[dict, str | None]`
  - `ws_api.websocket_set_settings` übergibt `entry.options.get(OPTION_LAB_CUSTOM_MARKERS)`
  - `restore.merge_lab_custom_markers` übergibt `previous=current`
- Verbraucher: keine (Blatt).

**Spec-Bezug:** §4 A-2 (Aufrufstellen-Tabelle), R-5.

- [ ] **Step 1: Write the failing tests**

In `tests/test_ws_api.py`:

```python
def test_req_hom_130_set_settings_keeps_key_for_previous_name():
    """[REQ-HOM-130] A keyless re-save inherits the stored marker key (A-2)."""
    previous = [
        {"key": "vitamin_d", "name": "Vitamin D", "unit": "ng/mL", "category": "other"}
    ]
    updates, error = ws_api.parse_settings_message(
        {
            "lab_custom_markers": [
                {"name": "Vitamin D", "unit": "ng/mL", "category": "other"}
            ]
        },
        previous_markers=previous,
    )
    assert error is None
    assert updates["lab_custom_markers"][0]["key"] == "vitamin_d"
```

In `tests/test_restore.py`:

```python
def test_req_hom_130_restore_inherits_key_from_current():
    """[REQ-HOM-130] A keyless backup never shifts existing keys (A-2)."""
    current = [{"key": "vitamin_d", "name": "Vitamin D", "unit": "ng/mL"}]
    incoming = [{"name": "Vitamin D", "unit": "ng/mL"}]
    merged = restore_module.merge_lab_custom_markers(current, incoming)
    assert [marker["key"] for marker in merged] == ["vitamin_d"]
```

- [ ] **Step 2: Run the red command**

```bash
python3 -m pytest tests/test_ws_api.py tests/test_restore.py -q -k req_hom_130
```

Expected: `TypeError: parse_settings_message() got an unexpected keyword argument
'previous_markers'` und `AssertionError: ['vitamin_d_2'] == ['vitamin_d']`.

- [ ] **Step 3: Implement**

(a) `ws_api.py:1839` — Signatur:

```python
def parse_settings_message(
    msg: Mapping[str, Any], *, previous_markers: Any = None
) -> tuple[dict[str, Any], str | None]:
```

und in der `OPTION_LAB_CUSTOM_MARKERS`-Verzweigung (`ws_api.py:1874-1883`):

```python
        updates[OPTION_LAB_CUSTOM_MARKERS] = logic.normalize_lab_custom_markers(
            raw_markers, previous_markers
        )
```

(b) `ws_api.py:1940` — Aufrufstelle:

```python
    updates, error = parse_settings_message(
        msg,
        previous_markers=(getattr(entry, "options", None) or {}).get(
            OPTION_LAB_CUSTOM_MARKERS
        ),
    )
```

(c) `restore.py:361-364`:

```python
    normalized_current = normalize_lab_custom_markers(current)
    existing_keys = {marker["key"] for marker in normalized_current}
    merged = list(normalized_current)
    # A-2: keyless backup entries inherit the local key instead of shifting it.
    for marker in normalize_lab_custom_markers(incoming, previous=current):
```

- [ ] **Step 4: Run the green command**

```bash
python3 -m pytest tests/test_ws_api.py tests/test_restore.py -q
python3 -m pytest -q
ruff check custom_components/health_o_mat/ws_api.py custom_components/health_o_mat/restore.py
ruff format --check custom_components/health_o_mat/ws_api.py \
        custom_components/health_o_mat/restore.py
```

Expected: grün; alle bestehenden `set_settings`-/Restore-Tests unverändert grün (der neue
Parameter ist keyword-only und optional).

- [ ] **Step 5: Commit**

```bash
git add custom_components/health_o_mat/ws_api.py custom_components/health_o_mat/restore.py \
        tests/test_ws_api.py tests/test_restore.py
git commit -m "feat: inherit marker keys in settings and restore"
```

---

### Task 10: A-3 — Drift-Test `WELLBEING_STATES` → `report_*`

**Files:**
- Test: `tests/test_translations.py`

**Interfaces:**
- Consumes: `const.WELLBEING_STATES`, `_LAB_NAME_FIELDS`, `_load_const`, `_load`.
- Produces: `test_req_hom_131_wellbeing_report_buttons_cover_every_state`.

**Spec-Bezug:** §4 A-3, §0 (Audit-Korrektur: `LAB_CATEGORIES` ist bereits durch
`tests/test_translations.py:478-501` abgedeckt — **nicht** duplizieren), Audit §3a.

> **Kein TDD-Rot möglich:** Der Test ist ein Drift-Wächter und heute grün. Die „Rot-Probe"
> ist deshalb eine **Mutation** (Step 2): Key temporär entfernen → Test muss rot werden →
> Änderung zurücknehmen.

- [ ] **Step 1: Write the test**

Ans Ende von `tests/test_translations.py`:

```python
def test_req_hom_131_wellbeing_report_buttons_cover_every_state() -> None:
    """[REQ-HOM-131] Every wellbeing state has its report-button name.

    Analogous to `test_req_hom_122_lab_warnings_cover_every_non_other_category`:
    the dynamic `report_{key}` key comes from `const.WELLBEING_STATES`; if it is
    missing in one of the three files, HA registers the button through the
    device-class fallback (localized object_id). A-3 closes that gap.
    """
    const = _load_const()
    expected = {f"report_{state['key']}" for state in const.WELLBEING_STATES}

    for path, _name_field in _LAB_NAME_FIELDS:
        button = _load(path)["entity"]["button"]
        actual = {key for key in button if key.startswith("report_")}
        assert actual == expected, (
            f"{path}: report keys diverge from WELLBEING_STATES "
            f"(missing: {sorted(expected - actual)}, extra: {sorted(actual - expected)})"
        )
        for key in sorted(expected):
            assert button[key]["name"].strip(), f"{path}: {key}.name is empty"
```

- [ ] **Step 2: Rot-Probe per Mutation (Pflichtnachweis)**

```bash
# 1) remove one key from the master (local only, never committed)
python3 - <<'PY'
import json, pathlib
p = pathlib.Path("custom_components/health_o_mat/strings.json")
data = json.loads(p.read_text())
data["entity"]["button"].pop("report_excellent")
p.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
PY
python3 -m pytest tests/test_translations.py -q -k req_hom_131   # expect: FAILED
git checkout -- custom_components/health_o_mat/strings.json      # revert the mutation
python3 -m pytest tests/test_translations.py -q -k req_hom_131   # expect: 1 passed
```

Expected: erst `AssertionError` mit `missing: ['report_excellent']`, nach dem Revert grün.
Beide Ausgaben im Task-Protokoll notieren.

- [ ] **Step 3: Run the green command**

```bash
python3 -m pytest tests/test_translations.py -q
python3 -m pytest -q
ruff check tests/test_translations.py
ruff format --check tests/test_translations.py
```

- [ ] **Step 4: Commit**

```bash
git add tests/test_translations.py
git commit -m "test: guard wellbeing report button translations"
```

---

### Task 11: A-4 — E2E-Regression „englische `object_id`s bei Erstregistrierung"

**Files:**
- Create: `tests_e2e/test_entity_ids_e2e.py`

**Interfaces:**
- Consumes: `scripts.e2e_bootstrap` (`ensure_person`, `_headers`), `e2e_helpers.ws_command`,
  Fixtures `hass_base_url`, `hass_bearer_token`.
- Produces: `test_req_hom_131_fresh_person_gets_language_independent_entity_ids`,
  Helfer `_ws_result`, `_delete_entry`.

**Spec-Bezug:** §4 A-4, §2.3 (Area-Fall), §6.4 (E2E-Ablauf), R-2, R-11.

> **Keine Sprachumschaltung** (Spec §1.4). Der Test liest `hass.config.language` und prüft
> denselben Vertrag in beiden Fällen; unter `de` ist er die scharfe Regression
> (HA ≥ 2026.9 würde sonst deutsche `object_id`s erzeugen), unter `en` pinnt er die
> Erstregistrierungs-IDs.

- [ ] **Step 1: Write the failing test**

`tests_e2e/test_entity_ids_e2e.py`:

```python
"""E2E: entity ids of a freshly registered person (REQ-HOM-131, A-4).

A-4 is the regression net for the `suggested_object_id` override: HA's
`platform_data` / `_name_internal` / `default_language_platform_translations`
are internal API, so only a real registration against a real instance proves
that object ids stay English/ASCII. The test never switches the instance
language (Spec §1.4) — it reads `hass.config.language` and asserts the same
language-independent contract either way.
"""

from __future__ import annotations

import pytest
import requests

from e2e_helpers import ws_command
from scripts.e2e_bootstrap import _headers, ensure_person

pytestmark = pytest.mark.e2e

PERSON = "E2E-EntityIds"
PREFIX = "health_o_mat_e2e_entityids"

# Old, user-text derived ids that must never come back.
OLD_IDS = (
    f"button.{PREFIX}_glas_wasser",
    f"button.{PREFIX}_flasche_wasser",
    f"button.{PREFIX}_tasse_kaffee",
    f"button.{PREFIX}_glas_saft",
)


def _ws_result(base_url: str, token: str, payload: dict) -> object:
    return ws_command(base_url, token, payload)


def _delete_entry(base_url: str, token: str, entry_id: str) -> None:
    """Remove one config entry (and its entities/device).

    The store record of the entry survives (Spec §6.3 Phase 0c) — one small,
    empty record per run on the shared test instance, cleaned up by the next
    `bin/reset`/provision.
    """
    response = requests.delete(
        f"{base_url}/api/config/config_entries/entry/{entry_id}",
        headers=_headers(token),
        timeout=30,
    )
    if response.status_code not in (200, 404):
        response.raise_for_status()


def test_req_hom_131_fresh_person_gets_language_independent_entity_ids(
    hass_base_url, hass_bearer_token
):
    person = ensure_person(hass_base_url, hass_bearer_token, PERSON, enable_panel=False)
    entry_id = str(person["entry_id"])
    try:
        registry = _ws_result(
            hass_base_url, hass_bearer_token, {"type": "config/entity_registry/list"}
        )
        entries = [item for item in registry or [] if item.get("config_entry_id") == entry_id]
        by_unique = {item["unique_id"]: item["entity_id"] for item in entries}
        language = _ws_result(hass_base_url, hass_bearer_token, {"type": "config"}).get(
            "language"
        )

        # 1) Language independent, English/ASCII ids (the actual A-4 assertion).
        assert by_unique[f"{entry_id}_today"] == f"sensor.{PREFIX}_drinks_today", language
        assert (
            by_unique[f"{entry_id}_bp_warning"]
            == f"binary_sensor.{PREFIX}_blood_pressure_warning"
        ), language
        # 2) Quick drinks are pinned to the slot index (A-5 + REQ-HOM-130).
        assert (
            by_unique[f"{entry_id}_button_quick_0"] == f"button.{PREFIX}_quick_drink_1"
        ), language
        assert (
            by_unique[f"{entry_id}_button_quick_3"] == f"button.{PREFIX}_quick_drink_4"
        ), language
        # 3) No localized / label-derived ids exist for this person.
        existing = {item["entity_id"] for item in entries}
        assert not existing.intersection(OLD_IDS), sorted(existing.intersection(OLD_IDS))
        assert not any(
            entity_id.endswith(("_heute_getrunken", "_blutdruck_warnung"))
            for entity_id in existing
        )
    finally:
        _delete_entry(hass_base_url, hass_bearer_token, entry_id)
```

- [ ] **Step 2: Run the red command (Rot-Probe per Mutation)**

```bash
# Disable the pinning temporarily (local only, never committed)
python3 - <<'PY'
import pathlib
p = pathlib.Path("custom_components/health_o_mat/button.py")
text = p.read_text()
text = text.replace(
    'return f"quick_drink_{self._index + 1}"',
    "return super().suggested_object_id",
)
p.write_text(text)
PY
/home/hermes/ha-test/bin/sync /home/hermes/repos/ha-health-o-mat
cd tests_e2e && HASS_BASE_URL=http://127.0.0.1:8123 python3 -m pytest test_entity_ids_e2e.py -q
# expect: FAILED (quick_drink_1 missing, _glas_wasser instead)
git checkout -- custom_components/health_o_mat/button.py
/home/hermes/ha-test/bin/sync /home/hermes/repos/ha-health-o-mat
```

Expected: `AssertionError` mit `button.health_o_mat_e2e_entityids_quick_drink_1` und
`language='de'` (bzw. `'en'`, je nach Instanz). Nach Revert + Sync muss der Test grün
sein. **Wichtig:** Jeder Sync ist ein HA-Neustart (~10–30 s) — mit den anderen Agenten auf
der geteilten Instanz abstimmen; **nicht** parallel zu Task 14–17.

- [ ] **Step 3: Run the green command**

```bash
cd tests_e2e && HASS_BASE_URL=http://127.0.0.1:8123 python3 -m pytest test_entity_ids_e2e.py -v
cd .. && ruff check tests_e2e/test_entity_ids_e2e.py
ruff format --check tests_e2e/test_entity_ids_e2e.py
```

Expected: `1 passed`; die temporäre Person ist wieder entfernt (`_delete_entry` im
`finally`), die beiden Fixture-Personen unberührt.

- [ ] **Step 4: Commit**

```bash
git add tests_e2e/test_entity_ids_e2e.py
git commit -m "test: assert english entity ids on a live instance"
```

---

## Wave 4 — E2E/Regression der bestehenden Suiten

### Task 12: `tests_e2e/test_lab_values_e2e.py` — `_lab_<key>`-Assertion

**Files:**
- Modify: `tests_e2e/test_lab_values_e2e.py`

**Interfaces:**
- Consumes: `_lab_entity` (`tests_e2e/test_lab_values_e2e.py:218-232`), Task 5 (Pinning).
- Produces: verschärfte Assertion `entity_id.endswith(f"_lab_{marker_key}")`.

**Spec-Bezug:** §6.4 („dort zusätzlich asserten, dass die Custom-Marker-`entity_id` auf
`_lab_<key>` endet — verschärft die Aussage, ohne neue Kopplung an Labels").

- [ ] **Step 0: Verify the spec claim (kein Code)**

```bash
grep -rn "glas_wasser\|tasse_kaffee\|vitamin_d" tests_e2e/ || echo "no old ids in tests_e2e (confirmed)"
```

Expected: `no old ids in tests_e2e (confirmed)` — deckt sich mit Spec §6.4. Weicht das ab:
betroffene Stelle **zusätzlich** in diesem Task auf `unique_id`-Auflösung umstellen.

- [ ] **Step 1: Write the failing assertion**

In `tests_e2e/test_lab_values_e2e.py`, im Custom-Marker-Block (nach der bestehenden
`unique_id`-Assertion, `:400-404`):

```python
    lab_entity_id = str(entity["registry"]["entity_id"])
    registry_entry = entity["registry"]
    assert lab_entity_id.startswith("sensor."), f"unexpected domain: {lab_entity_id!r}"
    # REQ-HOM-130/A-5: the object id is derived from the stable marker key, not
    # from the user text (a rename of the marker must not move the id).
    assert lab_entity_id.endswith(f"_lab_{marker_key}"), lab_entity_id
    assert registry_entry["platform"] == "health_o_mat"
    assert registry_entry["unique_id"] == _lab_unique_id(entry_id, marker_key)
```

- [ ] **Step 2: Run the red command (Rot-Probe per Mutation)**

```bash
# Temporarily disable the custom-marker pinning (local only)
python3 - <<'PY'
import pathlib
p = pathlib.Path("custom_components/health_o_mat/sensor.py")
text = p.read_text()
text = text.replace(
    'return f"lab_{self._marker_key}"',
    "return super().suggested_object_id",
)
p.write_text(text)
PY
/home/hermes/ha-test/bin/sync /home/hermes/repos/ha-health-o-mat
cd tests_e2e && HASS_BASE_URL=http://127.0.0.1:8123 python3 -m pytest test_lab_values_e2e.py -q -k custom
git checkout -- custom_components/health_o_mat/sensor.py
/home/hermes/ha-test/bin/sync /home/hermes/repos/ha-health-o-mat
```

Expected: `AssertionError: sensor.health_o_mat_e2e_deep_<name-slug>` (kein `_lab_`-Suffix).
Nach Revert + Sync grün.

- [ ] **Step 3: Run the green command**

```bash
cd tests_e2e && HASS_BASE_URL=http://127.0.0.1:8123 python3 -m pytest test_lab_values_e2e.py -q
cd .. && ruff check tests_e2e/test_lab_values_e2e.py
ruff format --check tests_e2e/test_lab_values_e2e.py
```

Expected: grün (die Datei liest die `entity_id` weiterhin über die `unique_id` aus der
Registry — kein Label-Bezug).

- [ ] **Step 4: Commit**

```bash
git add tests_e2e/test_lab_values_e2e.py
git commit -m "test: assert lab entity ids use the marker key"
```

---

### Task 13: Beispiele, `test_dashboards.py` und `scripts/e2e-live-test.sh`

**Files:**
- Modify: `examples/dashboard.yaml`
- Modify: `examples/dashboard-mini.yaml`
- Modify: `examples/dashboard-mushroom.yaml`
- Modify: `tests/test_dashboards.py`
- Modify: `scripts/e2e-live-test.sh`

**Interfaces:**
- Consumes: neue IDs aus Task 5/6 (`…_quick_drink_1` … `…_quick_drink_4`).
- Produces: konsistente Beispiele/Tests/Skripte mit dem neuen Schema.

**Spec-Bezug:** §5.2 (Tabelle: `examples/*.yaml`, `tests/test_dashboards.py:19-68`,
`scripts/e2e-live-test.sh`).

> **Nicht anfassen:** `const.DEFAULT_QUICK_DRINKS[*].key` (`glas_wasser` …) und
> `www/health-o-mat-card.js:62-63` — das sind **Konfigurations-Keys** bzw. Karten-Labels,
> keine Entity-IDs. Sie bleiben unverändert.

- [ ] **Step 1: Write the failing test**

`tests/test_dashboards.py:52-55` — alte Suffixe entfernen, neue ergänzen:

```python
    "button": {
        "book_custom_amount",
        "undo_last_drink",
        "save_measurement",
        "quick_drink_1",
        "quick_drink_2",
        "quick_drink_3",
        "quick_drink_4",
        "report_very_bad",
        "report_awful",
        "report_bad",
        "report_poor",
        "report_okay",
        "report_mixed",
        "report_good",
        "report_very_good",
        "report_great",
        "report_excellent",
    },
```

- [ ] **Step 2: Run the red command**

```bash
python3 -m pytest tests/test_dashboards.py -q
```

Expected: mehrere Fehlschläge `unbekanntes Suffix … _glas_wasser` (die Beispiele nutzen
noch die alten IDs) — genau der gewünschte Rot-Zustand.

- [ ] **Step 3: Implement**

(a) `examples/dashboard.yaml:41-47` — die vier IDs ersetzen:

```yaml
          - type: button
            entity: button.health_o_mat_max_quick_drink_1
          - type: button
            entity: button.health_o_mat_max_quick_drink_2
          - type: button
            entity: button.health_o_mat_max_quick_drink_3
          - type: button
            entity: button.health_o_mat_max_quick_drink_4
```

(b) `examples/dashboard-mini.yaml:37-39`:

```yaml
      - type: button
        entity: button.health_o_mat_max_quick_drink_1
      - type: button
        entity: button.health_o_mat_max_quick_drink_2
```

(c) `examples/dashboard-mushroom.yaml:43-49`:

```yaml
          - type: custom:mushroom-button-card
            entity: button.health_o_mat_max_quick_drink_1
          - type: custom:mushroom-button-card
            entity: button.health_o_mat_max_quick_drink_2
          - type: custom:mushroom-button-card
            entity: button.health_o_mat_max_quick_drink_3
          - type: custom:mushroom-button-card
            entity: button.health_o_mat_max_quick_drink_4
```

(d) `scripts/e2e-live-test.sh:122-133`:

```bash
# Quick-Drinks aus Default-Konfiguration (REQ-HOM-130: slot-basierte IDs)
for e in "button:${P}_quick_drink_1" "button:${P}_quick_drink_2" "button:${P}_quick_drink_3" "button:${P}_quick_drink_4"; do
  eid="${e#*:}"
  "$HA_TEST/bin/ha" GET "/api/states/$eid" >/dev/null 2>&1 && pass "quick: $eid" || fail "quick: $eid"
done
```

und in der Getränke-Batterie (`:130`):

```bash
"$HA_TEST/bin/ha" POST /api/services/button/press "{\"entity_id\": \"button.${P}_quick_drink_1\"}" >/dev/null
```

- [ ] **Step 4: Run the green command**

```bash
python3 -m pytest tests/test_dashboards.py -q
python3 -m pytest -q
bash -n scripts/e2e-live-test.sh
grep -rn "glas_wasser\|flasche_wasser\|tasse_kaffee\|glas_saft" examples/ scripts/ tests/ \
  | grep -v "const.py" || echo "no old entity ids left in examples/scripts/tests"
ruff check tests/test_dashboards.py
```

Expected: grün; `bash -n` ohne Ausgabe; keine alten **Entity-IDs** mehr in
`examples/`/`scripts/`/`tests/` (Treffer in `const.py`-Fixtures sind Konfigurations-Keys
und bleiben).

- [ ] **Step 5: Commit**

```bash
git add examples/dashboard.yaml examples/dashboard-mini.yaml examples/dashboard-mushroom.yaml \
        tests/test_dashboards.py scripts/e2e-live-test.sh
git commit -m "chore: update dashboards and live test to new entity ids"
```

---

## Wave 5 — Live-Migrationstest auf `/home/hermes/ha-test`

> **Betriebsprozedur, kein Anwendungscode.** Kein `bin/reset`, keine Sprachumschaltung,
> nur die eigene Domain syncen, fremde Domains/Entries unberührt, Snapshots ausschließlich
> lesend nach `.tmp/` (nie committen). Ein Neustart-Fenster für die ganze Welle
> abstimmen — Task 11 und 12 nutzen dieselbe Instanz.

### Task 14: Phase 0/0b/0c — Baseline, zwei Test-Personen, Kollisionen, Isolation, Snapshots

**Files:** keine (nur `.tmp/`-Artefakte).

**Spec-Bezug:** §6.3 Phase 0, 0b, 0c; §6.5 AK 1–3.

- [ ] **Step 1: Baseline prüfen (0.16.2)**

```bash
docker exec ha-test cat /config/custom_components/health_o_mat/manifest.json | grep version
# erwartet: "version": "0.16.2"
```

Weicht die Version ab: Baseline **ohne Eingriff in den Arbeitsbaum** erzeugen und syncen —
kein `git checkout`/`stash`:

```bash
mkdir -p .tmp/baseline-0162
git archive d86b247 | tar -x -C .tmp/baseline-0162
/home/hermes/ha-test/bin/sync .tmp/baseline-0162
```

- [ ] **Step 2: Zwei Test-Personen über den echten Config-Flow anlegen**

```bash
HA=/home/hermes/ha-test/bin/ha
flow=$($HA POST /api/config/config_entries/flow \
  '{"handler":"health_o_mat","show_advanced_options":false}' \
  | python3 -c "import json,sys;print(json.load(sys.stdin)['flow_id'])")
$HA POST "/api/config/config_entries/flow/${flow}" '{"person":"Migrationstest"}'
flow=$($HA POST /api/config/config_entries/flow \
  '{"handler":"health_o_mat","show_advanced_options":false}' \
  | python3 -c "import json,sys;print(json.load(sys.stdin)['flow_id'])")
$HA POST "/api/config/config_entries/flow/${flow}" '{"person":"Migrationstest-Kollision"}'
```

Entry-IDs notieren (aus `GET /api/config/config_entries/entry` bzw. `health_o_mat/list_persons`):

```bash
$HA GET /api/config/config_entries/entry | python3 -c "
import json,sys
for e in json.load(sys.stdin):
    if e['domain']=='health_o_mat' and 'Migrationstest' in e['title']:
        print(e['entry_id'], e['title'], 'version=', e['version'])
"
```

Expected: zwei Entries (`A` = „Migrationstest", `B` = „Migrationstest-Kollision"), je
`version=2`.

- [ ] **Step 3: A konfigurieren (vier Quick-Slots + drei Custom-Marker)**

```bash
python3 - <<'PY'
from scripts.e2e_bootstrap import bootstrap, _ws_command, list_persons

BASE = "http://127.0.0.1:8123"
token = bootstrap(BASE)
persons = {p["person"]: p for p in list_persons(BASE, token)}
entry_a = persons["Migrationstest"]["entry_id"]

_ws_command(BASE, token, {
    "type": "health_o_mat/set_settings",
    "entry_id": entry_a,
    "quick_drinks": [
        {"label": "Glas Wasser", "ml": 200, "icon": "mdi:glass-water"},
        {"label": "Grüner Tee", "ml": 200, "icon": "mdi:tea"},
        {"label": "Tasse Kaffee", "ml": 250, "icon": "mdi:coffee"},
        {"label": "Glas Saft", "ml": 200, "icon": "mdi:fruit-citrus"},
    ],
    "lab_custom_markers": [
        {"name": "Vitamin D", "unit": "ng/mL", "category": "other"},
        {"name": "Ferritin gesamt", "unit": "µg/L", "category": "other"},
        {"name": "Hämoglobin", "unit": "g/dL", "category": "blood_count"},
    ],
})
print("A configured:", entry_a)
PY
```

> Enthält bewusst Nicht-ASCII („Grüner Tee", „Hämoglobin") und ein Label, das von der ID
> abweicht (Spec §6.3 Phase 0 Schritt 3).

- [ ] **Step 4: A-Verlauf erzeugen (2 Getränke, 2 Laborwerte)**

```bash
HA=/home/hermes/ha-test/bin/ha
$HA POST /api/services/health_o_mat/add_drink '{"person":"Migrationstest","ml":200,"drink_type":"Wasser"}'
$HA POST /api/services/health_o_mat/add_drink '{"person":"Migrationstest","ml":250,"drink_type":"Kaffee"}'
$HA POST /api/services/health_o_mat/add_lab_value '{"person":"Migrationstest","marker":"vitamin_d","value":32}'
$HA POST /api/services/health_o_mat/add_lab_value '{"person":"Migrationstest","marker":"ferritin_gesamt","value":180}'
```

- [ ] **Step 5: B konfigurieren (Default-Quick-Drinks + ein Custom-Marker)**

```bash
python3 - <<'PY'
from scripts.e2e_bootstrap import bootstrap, _ws_command, list_persons

BASE = "http://127.0.0.1:8123"
token = bootstrap(BASE)
persons = {p["person"]: p for p in list_persons(BASE, token)}
entry_b = persons["Migrationstest-Kollision"]["entry_id"]

_ws_command(BASE, token, {
    "type": "health_o_mat/set_settings",
    "entry_id": entry_b,
    "lab_custom_markers": [
        {"name": "Vitamin D", "unit": "ng/mL", "category": "other"}
    ],
})
print("B configured:", entry_b)
PY
```

- [ ] **Step 6: Konsistenten Snapshot ziehen**

```bash
mkdir -p .tmp
# mindestens 10 s nach der letzten Options-/Entity-Änderung warten (SAVE_DELAY),
# dann Entity-Anzahl gegen die Registry abgleichen:
sleep 12
python3 - <<'PY'
from scripts.e2e_bootstrap import bootstrap, _ws_command
BASE = "http://127.0.0.1:8123"
token = bootstrap(BASE)
entries = _ws_command(BASE, token, {"type": "config/entity_registry/list"}) or []
counts = {}
for item in entries:
    if item.get("platform") == "health_o_mat":
        counts[item["config_entry_id"]] = counts.get(item["config_entry_id"], 0) + 1
print(counts)
PY

cp /home/hermes/ha-test/config/.storage/core.entity_registry        .tmp/registry.before.json
cp /home/hermes/ha-test/config/.storage/core.device_registry        .tmp/device_registry.before.json
cp /home/hermes/ha-test/config/.storage/core.config_entries         .tmp/config_entries.before.json
cp /home/hermes/ha-test/config/.storage/health_o_mat                .tmp/health_o_mat_store.before.json
```

Mapping extrahieren und ablegen (Basis für den Mengen-Diff in Task 15):

```bash
python3 - <<'PY'
import json, pathlib
data = json.loads(pathlib.Path(".tmp/registry.before.json").read_text())["data"]["entities"]
rows = [
    {
        "unique_id": item["unique_id"],
        "entity_id": item["entity_id"],
        "original_name": item.get("original_name"),
        "device_id": item.get("device_id"),
        "config_entry_id": item.get("config_entry_id"),
    }
    for item in data
    if item.get("platform") == "health_o_mat"
]
pathlib.Path(".tmp/registry.before.mapped.json").write_text(json.dumps(rows, indent=2))
print(len(rows), "health_o_mat entities snapshotted")
PY
```

- [ ] **Step 7: Erwartete alte IDs dokumentieren**

In `.tmp/expected-old-ids.txt` festhalten (Spec §6.3 Phase 0 Schritt 7):

```
button.<prefixA>_glas_wasser
button.<prefixA>_gruner_tee        # HA-slugify transliteriert ü -> u
button.<prefixA>_tasse_kaffee
button.<prefixA>_glas_saft
sensor.<prefixA>_vitamin_d
sensor.<prefixA>_ferritin_gesamt
sensor.<prefixA>_hamoglobin        # HA transliteriert Hämoglobin
```

`<prefixA>` aus `health_o_mat/list_persons` (`person_slug`) einsetzen.

- [ ] **Step 8: Kollisionen für B präparieren (Phase 0b)**

```bash
python3 - <<'PY'
from scripts.e2e_bootstrap import bootstrap, _ws_command, list_persons

BASE = "http://127.0.0.1:8123"
token = bootstrap(BASE)
persons = {p["person"]: p for p in list_persons(BASE, token)}
entry_b = persons["Migrationstest-Kollision"]["entry_id"]
prefix_b = f"health_o_mat_{persons['Migrationstest-Kollision']['person_slug']}"

# Quick collision: book_custom_amount occupies quick_drink_1 (unique_id stays).
_ws_command(BASE, token, {
    "type": "config/entity_registry/update",
    "entity_id": f"button.{prefix_b}_book_custom_amount",
    "new_entity_id": f"button.{prefix_b}_quick_drink_1",
})
# Lab collision: catalog CRP occupies the custom marker's target.
_ws_command(BASE, token, {
    "type": "config/entity_registry/update",
    "entity_id": f"sensor.{prefix_b}_crp",
    "new_entity_id": f"sensor.{prefix_b}_lab_vitamin_d",
})
print("collisions prepared for", entry_b)
PY
```

- [ ] **Step 9: Erstlauf isolieren (Phase 0c)**

```bash
# Alle übrigen health_o_mat-Entries dokumentieren ...
/home/hermes/ha-test/bin/ha GET /api/config/config_entries/entry | python3 -c "
import json,sys
for e in json.load(sys.stdin):
    if e['domain']=='health_o_mat':
        print(e['entry_id'], e['title'], 'version=', e['version'])
" | tee .tmp/other-entries.before.txt
```

... und für den Erstlauf entfernen (nur die anderen, **nicht** A und B):

```bash
python3 - <<'PY'
from scripts.e2e_bootstrap import bootstrap, list_persons
import requests

BASE = "http://127.0.0.1:8123"
token = bootstrap(BASE)
keep = {"Migrationstest", "Migrationstest-Kollision"}
for person in list_persons(BASE, token):
    if person["person"] in keep:
        continue
    entry_id = person["entry_id"]
    response = requests.delete(
        f"{BASE}/api/config/config_entries/entry/{entry_id}",
        headers={"Authorization": f"Bearer {token}"},
        timeout=30,
    )
    print("removed", person["person"], entry_id, response.status_code)
PY
```

> **Achtung:** `DELETE` entfernt Config-Entry, Registry-Entities und Device — **nicht** die
> Store-Daten (Spec §6.3 Phase 0c). Historie ist nur über den Snapshot-Pfad (Task 17)
> wiederherstellbar, nicht über „neu anlegen". Die E2E-Fixture-Personen werden erst nach
> dem Release per `scripts/e2e_bootstrap.py` (`VERSION = 3`) neu angelegt.

- [ ] **Step 10: Abschluss Phase 0**

- [ ] Snapshot-Dateien vorhanden (`ls -l .tmp/*.before.json`) und nicht committet
      (`git status --short .tmp` → leer).
- [ ] Ausschließlich A und B sind noch als `health_o_mat`-Entries vorhanden.
- [ ] `.tmp/registry.before.mapped.json` enthält die `unique_id`-Menge beider Personen.

### Task 15: Phase 1/2 — Migrationslauf und Verifikation Entry A

**Files:** keine.

**Spec-Bezug:** §6.3 Phase 1/2; §6.5 AK 1–5, 7.

- [ ] **Step 1: Branch syncen (löst `async_migrate_entry` für A und B aus)**

```bash
/home/hermes/ha-test/bin/sync /home/hermes/repos/ha-health-o-mat
```

- [ ] **Step 2: Log prüfen**

```bash
/home/hermes/ha-test/bin/logs --since 5m \
  | grep -iE "migrat|Entity-ID|error|schema_drift|stale_marker"
```

Expected (Spec §6.3 Phase 1):
- **A**: `Config entry … auf Version 3 migriert`, keine Warnung.
- **B**: genau **zwei** Warnungen mit Paarliste (`target_occupied` für `…_quick_drink_1`
  und `…_lab_vitamin_d`); `core.config_entries` zeigt für **B** weiter `version: 2`;
  **B** ist nicht geladen.
- Bereits angewendete, nicht kollidierende Renames von **B** (Quick-Slots 2–4) sind der
  definierte Teil-Zustand für den Retry.

- [ ] **Step 3: Soll/Ist-Prüfung Entry A**

```bash
HA=/home/hermes/ha-test/bin/ha
PREFIX_A=health_o_mat_<slugA>

for eid in \
  "button.${PREFIX_A}_quick_drink_1" "button.${PREFIX_A}_quick_drink_2" \
  "button.${PREFIX_A}_quick_drink_3" "button.${PREFIX_A}_quick_drink_4" \
  "sensor.${PREFIX_A}_lab_vitamin_d" "sensor.${PREFIX_A}_lab_ferritin_gesamt" \
  "sensor.${PREFIX_A}_lab_h_moglobin"; do
  $HA GET "/api/states/${eid}" >/dev/null 2>&1 && echo "OK   ${eid}" || echo "FAIL ${eid}"
done

# Alte IDs müssen weg sein (404)
for eid in \
  "button.${PREFIX_A}_glas_wasser" "button.${PREFIX_A}_gruner_tee" \
  "button.${PREFIX_A}_tasse_kaffee" "button.${PREFIX_A}_glas_saft" \
  "sensor.${PREFIX_A}_vitamin_d" "sensor.${PREFIX_A}_ferritin_gesamt" \
  "sensor.${PREFIX_A}_hamoglobin"; do
  $HA GET "/api/states/${eid}" >/dev/null 2>&1 && echo "FAIL still there ${eid}" || echo "OK   gone ${eid}"
done
```

Prüftabelle (Spec §6.3 Phase 2) — jede Zeile mit Beleg abhaken:

- [ ] **Neue IDs vorhanden:** `…_quick_drink_1…4`, `…_lab_vitamin_d`,
      `…_lab_ferritin_gesamt`, `…_lab_h_moglobin`.
- [ ] **Alte IDs weg:** obige alte IDs nicht mehr in der Registry,
      `GET /api/states/<alte_id>` → 404.
- [ ] **`unique_id` unverändert:** Mengendifferenz der `unique_id`s vor/nach = **leer**:

```bash
python3 - <<'PY'
import json, pathlib
from scripts.e2e_bootstrap import bootstrap, _ws_command

BASE = "http://127.0.0.1:8123"
token = bootstrap(BASE)
before = {row["unique_id"] for row in json.loads(
    pathlib.Path(".tmp/registry.before.mapped.json").read_text())}
after = {item["unique_id"] for item in _ws_command(
    BASE, token, {"type": "config/entity_registry/list"}) or []
    if item.get("platform") == "health_o_mat"}
print("missing:", sorted(before - after))
print("added:  ", sorted(after - before))
PY
```

Expected: `missing: []` (keine Entity verschwunden) — `added` kann durch das erneute
Setup leer sein; jede Differenz ist ein Blocker.

- [ ] **`original_name` unverändert:** Diff der Paare `(unique_id, original_name)` leer:

```bash
python3 - <<'PY'
import json, pathlib
from scripts.e2e_bootstrap import bootstrap, _ws_command

BASE = "http://127.0.0.1:8123"
token = bootstrap(BASE)
before = {row["unique_id"]: row["original_name"] for row in json.loads(
    pathlib.Path(".tmp/registry.before.mapped.json").read_text())}
after = {item["unique_id"]: item.get("original_name") for item in _ws_command(
    BASE, token, {"type": "config/entity_registry/list"}) or []
    if item.get("platform") == "health_o_mat"}
diff = {uid: (before[uid], after.get(uid)) for uid in before if before[uid] != after.get(uid)}
print("original_name diff:", diff)
PY
```

- [ ] **`device_id`/Registry-Anzahl unverändert**, keine neuen/doppelten Einträge:

```bash
python3 - <<'PY'
import json, pathlib
from scripts.e2e_bootstrap import bootstrap, _ws_command

BASE = "http://127.0.0.1:8123"
token = bootstrap(BASE)
before = {row["unique_id"]: row["device_id"] for row in json.loads(
    pathlib.Path(".tmp/registry.before.mapped.json").read_text())}
after_rows = [item for item in _ws_command(
    BASE, token, {"type": "config/entity_registry/list"}) or []
    if item.get("platform") == "health_o_mat"]
after = {item["unique_id"]: item.get("device_id") for item in after_rows}
print("count before/after:", len(before), len(after))
print("device_id diff:", {k: (before[k], after.get(k)) for k in before if before[k] != after.get(k)})
PY
```

- [ ] **Registry-Metadaten** (`entity_category`, `labels`, `aliases`, `area_id`,
      `hidden_by`, `disabled_by`) unverändert — gleicher Vergleich wie oben, ein
      `fields`-Dict je `unique_id`; erwartet: leerer Diff (nur `entity_id` ändert sich).
- [ ] **Config-Entry-Version:** A = `3`, B = `2`.
- [ ] **Store/Historie:** Store-Datei byte-identisch zum Snapshot
      (`cmp .tmp/health_o_mat_store.before.json /home/hermes/ha-test/config/.storage/health_o_mat`),
      Summen/Laborwerte identisch; Recorder: Statistik unter der **neuen** `entity_id`
      vorhanden (`GET /api/states` + `history/history_during_period` über die neue ID
      liefert die alten Zustände; `states_meta`/`statistics_meta` sind umgeschrieben, die
      Rohzeilen in `states` **nicht**).
- [ ] **States:** neue IDs liefern Werte, keine `unavailable`-Häufung.
- [ ] **Multi-Entry:** A migriert, B bleibt kollisionsbedingt auf Version 2 — keine
      Vermischung der Präfixe.

- [ ] **Step 4: Idempotenz (zweiter Neustart)**

```bash
python3 - <<'PY'
import json, pathlib
from scripts.e2e_bootstrap import bootstrap, _ws_command
BASE = "http://127.0.0.1:8123"
token = bootstrap(BASE)
rows = [item for item in _ws_command(BASE, token, {"type": "config/entity_registry/list"}) or []
        if item.get("platform") == "health_o_mat"]
pathlib.Path(".tmp/registry.after-run1.json").write_text(json.dumps(
    {item["unique_id"]: item["entity_id"] for item in rows}, indent=2))
print(len(rows), "entities recorded")
PY
/home/hermes/ha-test/bin/sync /home/hermes/repos/ha-health-o-mat
python3 - <<'PY'
import json, pathlib
from scripts.e2e_bootstrap import bootstrap, _ws_command
BASE = "http://127.0.0.1:8123"
token = bootstrap(BASE)
rows = [item for item in _ws_command(BASE, token, {"type": "config/entity_registry/list"}) or []
        if item.get("platform") == "health_o_mat"]
now = {item["unique_id"]: item["entity_id"] for item in rows}
before = json.loads(pathlib.Path(".tmp/registry.after-run1.json").read_text())
print("registry diff:", {k: (before[k], now.get(k)) for k in before if before[k] != now.get(k)})
PY
```

Expected: `registry diff: {}`; Version von A bleibt `3`.

- [ ] **Step 5: Ergebnis protokollieren**

Alle Soll/Ist-Zeilen mit Kommando + Ausgabe in `.tmp/live-run-1.log` sammeln (Grundlage für
die Belege in Task 18). Kein Commit in diesem Task.

### Task 16: Phase 3 — Negativprobe auflösen, Retry, Idempotenz

**Files:** keine.

**Spec-Bezug:** §6.3 Phase 3; §3.4 (Retry-Verhalten); §6.5 AK 4.

- [ ] **Step 1: Quick-Kollision von B auflösen**

```bash
python3 - <<'PY'
from scripts.e2e_bootstrap import bootstrap, _ws_command, list_persons
BASE = "http://127.0.0.1:8123"
token = bootstrap(BASE)
persons = {p["person"]: p for p in list_persons(BASE, token)}
prefix_b = f"health_o_mat_{persons['Migrationstest-Kollision']['person_slug']}"
_ws_command(BASE, token, {
    "type": "config/entity_registry/update",
    "entity_id": f"button.{prefix_b}_quick_drink_1",
    "new_entity_id": f"button.{prefix_b}_book_custom_amount",
})
print("quick collision released")
PY
/home/hermes/ha-test/bin/sync /home/hermes/repos/ha-health-o-mat
/home/hermes/ha-test/bin/logs --since 3m \
  | grep -iE "Entity-ID-Migration|migrat"
```

Expected: **B** scheitert weiterhin, aber **nur** wegen der Lab-Kollision (eine Warnung);
die Quick-Slots 1–4 sind jetzt umbenannt (der Retry hat den offenen Rest nachgeholt);
Version bleibt `2`.

- [ ] **Step 2: Lab-Kollision von B auflösen**

```bash
python3 - <<'PY'
from scripts.e2e_bootstrap import bootstrap, _ws_command, list_persons
BASE = "http://127.0.0.1:8123"
token = bootstrap(BASE)
persons = {p["person"]: p for p in list_persons(BASE, token)}
prefix_b = f"health_o_mat_{persons['Migrationstest-Kollision']['person_slug']}"
_ws_command(BASE, token, {
    "type": "config/entity_registry/update",
    "entity_id": f"sensor.{prefix_b}_lab_vitamin_d",
    "new_entity_id": f"sensor.{prefix_b}_crp",
})
print("lab collision released")
PY
/home/hermes/ha-test/bin/sync /home/hermes/repos/ha-health-o-mat
```

Expected: **B** migriert vollständig, `version: 3`, `sensor.<prefixB>_lab_vitamin_d`
vorhanden, alle `unique_id`s stabil.

- [ ] **Step 3: Idempotenz nach Teil-Lauf**

```bash
/home/hermes/ha-test/bin/sync /home/hermes/repos/ha-health-o-mat
/home/hermes/ha-test/bin/logs --since 2m \
  | grep -iE "Entity-ID-Migration|schema_drift|target_occupied" || echo "no migration activity (idempotent)"
```

Expected: keine Migrations-Warnung, kein Registry-Diff, Version bleibt `3` für A und B.

- [ ] **Step 4: Ergebnis protokollieren**

Ausgaben in `.tmp/live-run-2.log`. Kein Commit.

### Task 17: Phase 4 — Aufräumen und Restore-Pfad

**Files:** keine (Snapshot-Aufbewahrung, ggf. Restore).

**Spec-Bezug:** §6.3 Phase 4 (Schritte 15–18); §6.5 AK 1/3.

- [ ] **Step 1: Beide Test-Personen entfernen**

```bash
python3 - <<'PY'
from scripts.e2e_bootstrap import bootstrap, list_persons
import requests

BASE = "http://127.0.0.1:8123"
token = bootstrap(BASE)
for person in list_persons(BASE, token):
    if person["person"] not in {"Migrationstest", "Migrationstest-Kollision"}:
        continue
    response = requests.delete(
        f"{BASE}/api/config/config_entries/entry/{person['entry_id']}",
        headers={"Authorization": f"Bearer {token}"},
        timeout=30,
    )
    print("removed", person["person"], response.status_code)
PY
```

- [ ] Prüfen: Registry-Entities/Devices von A und B verschwinden, **fremde** Entries
      unberührt (`GET /api/config/config_entries/entry`).
- [ ] **Snapshots aufbewahren** bis nach dem Post-Release-HACS-Update-Test:
      `.tmp/registry.before.json`, `.tmp/device_registry.before.json`,
      `.tmp/config_entries.before.json`, `.tmp/health_o_mat_store.before.json`,
      `.tmp/registry.before.mapped.json` — erst danach löschen, **nie committen**.
- [ ] **Kein `bin/reset`.** Fremde Domains/Entries unberührt.

- [ ] **Step 2: Restore-Prozedur (nur bei Bedarf — exakt Spec §6.3 Phase 4 Schritt 17)**

```bash
# 1. HA stoppen (docker compose down entfernt den Container; Daten liegen im Bind-Mount)
/home/hermes/ha-test/bin/down

# 2. IMMER alle drei Dateien gemeinsam zurückholen — sonst steht der Entry auf
#    Version 3 bei alten IDs und der Handler laeuft nie wieder (version < VERSION
#    ist dann falsch):
cp .tmp/registry.before.json        /home/hermes/ha-test/config/.storage/core.entity_registry
cp .tmp/device_registry.before.json /home/hermes/ha-test/config/.storage/core.device_registry
cp .tmp/config_entries.before.json  /home/hermes/ha-test/config/.storage/core.config_entries

# 3. Die health_o_mat-Store-Datei nur zurueckspielen, wenn Daten beschaedigt wurden
#    (die Migration aendert sie nicht):
# cp .tmp/health_o_mat_store.before.json /home/hermes/ha-test/config/.storage/health_o_mat

# 4. HA starten
/home/hermes/ha-test/bin/up
```

- [ ] **Acceptance nach Restore:** `version == 2` für A und B, `unique_id`-Menge ==
      Snapshot, Registry-Anzahl == Snapshot.

```bash
python3 - <<'PY'
import json, pathlib
from scripts.e2e_bootstrap import bootstrap, _ws_command

BASE = "http://127.0.0.1:8123"
token = bootstrap(BASE)
before = json.loads(pathlib.Path(".tmp/registry.before.mapped.json").read_text())
snapshot = {row["unique_id"] for row in before}
rows = [item for item in _ws_command(BASE, token, {"type": "config/entity_registry/list"}) or []
        if item.get("platform") == "health_o_mat"]
now = {item["unique_id"] for item in rows}
print("unique_id set equal:", now == snapshot, len(now), len(snapshot))
for entry in _ws_command(BASE, token, {"type": "config_entries/get"}) or []:
    if entry.get("domain") == "health_o_mat" and "Migrationstest" in entry.get("title", ""):
        print(entry["title"], "version =", entry.get("version"))
PY
```

Expected: `unique_id set equal: True`; beide Entries `version = 2`.

> Der Restore überschreibt **alle** Änderungen seit dem Snapshot — nur auf der
> Testinstanz und nur für die eigene Domain anwenden, und nur nach Abstimmung.

- [ ] **Step 3: Ergebnis protokollieren**

Ausgaben in `.tmp/live-run-3.log`; Kurzfassung (Phase, Soll/Ist, Kommandos) für Task 18
ablegen. Kein Commit in Wave 5.

---

## Wave 6 — Doku & Release-Vorbereitung

### Task 18: README, REQUIREMENTS, Belege

**Files:**
- Modify: `README.md`
- Modify: `docs/REQUIREMENTS.md`

**Interfaces:**
- Consumes: Belege aus Task 15–17 (`.tmp/live-run-*.log`), Testergebnisse aus dem Final
  Integration Check.
- Produces: dokumentierte Alt→Neu-Regel, REQ-HOM-130/131 mit Status und Belegen.

**Spec-Bezug:** §5.2 (README-Zeile), §5.3 (Migrationshinweis-Inhalte), §5.4
(💥-Prominenz), §8.2 (REQ-Vorschlag).

- [ ] **Step 1: README — Button-Beispiel korrigieren**

`README.md:335` ersetzen:

```markdown
- **Quick-Drinks** — je konfiguriertem Quick-Drink ein Button (Label, mL und
  Icon kommen aus der Integration-Konfiguration; der **Anzeigename** ist
  nutzerdefiniert, die **Entity-ID** dagegen slot-basiert und stabil:
  `button.…_quick_drink_1` … `…_quick_drink_4`).
```

- [ ] **Step 2: README — Kasten „Entity-IDs ab 0.17.0"**

**An den Anfang** von `### Migration (Entity-IDs & Konfiguration)` (Zeile 398) setzen —
bewusst vor der chronologischen Liste, weil dieser Punkt bricht:

```markdown
> ### ⚠️ Entity-IDs ab 0.17.0 (bewusst als MINOR veröffentlicht)
>
> Quick-Drink-Buttons und eigene Laborwert-Marker bekommen **neue, sprachunabhängige
> Entity-IDs**. Die Migration läuft beim ersten Start nach dem Update automatisch,
> verlustfrei und ohne Zutun; `unique_id`, Anzeigename, Gerätezuordnung, Messdaten und
> Verlauf bleiben erhalten.
>
> | vorher (Beispiel) | nachher |
> |---|---|
> | `button.…_glas_wasser` | `button.…_quick_drink_1` |
> | `button.…_flasche_wasser` | `button.…_quick_drink_2` |
> | `button.…_tasse_kaffee` | `button.…_quick_drink_3` |
> | `button.…_glas_saft` | `button.…_quick_drink_4` |
> | `sensor.…_vitamin_d` (eigener Marker) | `sensor.…_lab_vitamin_d` |
>
> **Was du anpassen musst:** Automationen, Skripte, Dashboards, Szenen, Helfer und
> Template-Sensoren, die die alten IDs referenzieren — Home Assistant benennt sie **nicht**
> automatisch um. Die Regel ist mechanisch: Quick-Drink-Slot *n* (in der
> Options-Reihenfolge, ab 1) → `…_quick_drink_n`; eigene Laborwert-Marker → `…_lab_<key>`
> (der `key` ist ein ASCII-Slug, z. B. `h_moglobin`).
>
> **Bei einer ID-Kollision** (z. B. eine manuell umbenannte Entity belegt die Ziel-ID)
> wird die Person nicht geladen und das Log nennt die Paare (Quelle, `unique_id`, Ziel,
> Grund). Auflösung: kollidierende Entity umbenennen oder entfernen, dann Home Assistant
> **vollständig neu starten** (Reload genügt nicht, der Eintrag gilt als nicht
> wiederherstellbar). Durch die Härtung der Marker-Kategorien können außerdem verwaiste
> Warn-Entities für früher frei wählbare Kategorien übrig bleiben — in der Geräteansicht
> prüfen und löschen (nie die `unique_id` ändern).
```

- [ ] **Step 3: REQUIREMENTS — REQ-HOM-130/131 prüfen und ergänzen**

```bash
grep -n "REQ-HOM-130\|REQ-HOM-131" docs/REQUIREMENTS.md
```

- Sind beide Kapitel vorhanden (Requirements-Agent war schneller): **nur** Status/Belege
  aktualisieren.
- Stand beim Schreiben dieses Plans: **REQ-HOM-130 ist bereits aufgenommen** (paralleler
  Requirements-Agent, Status „Offen — geplant"); **REQ-HOM-131 fehlt in der Regel noch.**
  Dann nur `131` als eigenes Kapitel ergänzen („Härtungen A-1…A-4" mit den vier
  Unterpunkten, Priorität P1, Beleg-Testnamen `test_req_hom_131_*`) und `130` auf
  „Umgesetzt" setzen.
- Fehlen beide: die Kapitel aus Spec §8.2 wörtlich übernehmen (Titel, Priorität P1/L,
  Problem, Ziel, sechs Akzeptanzkriterien als Checkboxen, Bezug).

- [ ] **Step 4: Status + Belege eintragen**

```markdown
- [x] Nach Migration sind die IDs der Standard-Quick-Drinks `…_quick_drink_1…4` und
      Custom-Marker `…_lab_<key>`; alte IDs existieren nicht mehr.
      *Beleg:* `tests/test_entry_migration.py` (17 Tests), Live-Lauf Task 15
      (`.tmp/live-run-1.log`), `tests_e2e/test_entity_ids_e2e.py`.
- [x] `unique_id`s vor/nach identisch; `original_name` und `device_id` unverändert.
      *Beleg:* `test_req_hom_130_registry_fields_survive_the_rename`, Live-Diff Task 15
      (`missing: []`, `original_name diff: {}`).
- [x] Verlauf/Statistik unter der neuen `entity_id`; Store unverändert.
      *Beleg:* `cmp` der Store-Datei + Statistik-Check Task 15.
- [x] Zweiter Start ändert nichts; Kollision/`device_slug` → Version bleibt, Warnung mit
      Paarliste, Retry beim nächsten Start.
      *Beleg:* `test_req_hom_130_collision_*`, `test_req_hom_130_schema_drift_warns_and_fails`,
      Live-Negativprobe Task 16.
- [x] `LAB_CATEGORIES`-Fremdwerte → `other`; keylose Marker erben den Key.
      *Beleg:* `test_req_hom_130_normalize_*`, `test_req_hom_131_wellbeing_*`.
- [x] `pytest -q`, `ruff`, `pytest tests_e2e/` grün; Live-Migration inkl. Negativprobe
      dokumentiert.
      *Beleg:* Final Integration Check + `.tmp/live-run-{1,2,3}.log`.
```

Zusätzlich eine Zeile in der History-Tabelle (`docs/REQUIREMENTS.md`, Ende der Tabelle):

```markdown
| 2026-11-02 | **Neu angelegt und umgesetzt: REQ-HOM-130 — Entity-ID-Migration auf sprachunabhängige `object_id`s** (Branch `feat/entity-id-migration`; Spec `docs/superpowers/specs/2026-11-02-entity-id-migration-design.md`, Plan `docs/superpowers/plans/2026-11-02-entity-id-migration.md`): Quick-Drinks `{device_slug}_quick_drink_<n>` (1-basiert), Custom-Marker `{device_slug}_lab_<key>`, Migration über `async_migrate_entry` (`ConfigFlow VERSION 2 → 3`, HA-freies `migration.py`, Callback setzt nur `new_entity_id`, Drift-Diagnose, fail-closed bei Kollision), Pinning für Neuregistrierungen; Härtungen **REQ-HOM-131**: A-1 Kategorie-Validierung (`other`-Fallback), A-2 Key-Erhalt (WS + Restore), A-3 `WELLBEING_STATES`-Drift-Test, A-4 E2E-Regression englische IDs. `unique_id`s, Store und Verlauf unverändert. Bewusst **MINOR 0.17.0** (Nutzerentscheidung, Spec §5.4). **Belege:** siehe Akzeptanzkriterien. |
```

- [ ] **Step 5: Prüfen und committen**

```bash
grep -n "Entity-IDs ab 0.17.0" README.md
grep -c "quick_drink_1" README.md
grep -n "REQ-HOM-130\|REQ-HOM-131" docs/REQUIREMENTS.md | head
git add README.md docs/REQUIREMENTS.md
git commit -m "docs: document entity id migration in readme and requirements"
```

---

### Task 19: Release-Vorbereitung `0.17.0`

**Files:**
- Modify: `custom_components/health_o_mat/manifest.json`
- Modify: `custom_components/health_o_mat/www/health-o-mat-card.js`
- Modify: `custom_components/health_o_mat/www/health-o-mat-labs-card.js`
- Modify: `custom_components/health_o_mat/www/health-o-mat-panel.js`
- Modify: `custom_components/health_o_mat/www/health-o-mat-panel-views.js`
- Modify: `custom_components/health_o_mat/www/health-o-mat-panel-admin.js`
- Modify: `CHANGELOG.md`
- Create: `docs/RELEASE-NOTES-0.17.0.md`

**Spec-Bezug:** §5.1 (Version + Cache-Buster), §5.3 (CHANGELOG/Release-Notes-Inhalte),
§5.4 (MINOR-Abweichung), Workflow-Schritte 5–6 (Tag/Release sind **nicht** Teil dieses
Plans).

- [ ] **Step 1: Version und Cache-Buster (9 Stellen in 6 Dateien)**

`manifest.json:22` → `"version": "0.17.0"` (bare SemVer, kein `v`).

Alle `0.16.2`-Vorkommen in `www/` ersetzen (3 JS-Konstanten + 6 `?v=`-Cache-Buster):

```bash
grep -n "0\.16\.2" custom_components/health_o_mat/www/*.js
# erwartet: card.js:55 (CARD_VERSION), labs-card.js:26 (CARD_VERSION),
#           panel.js:75,80,85,92 (?v=), panel.js:95 (PANEL_VERSION),
#           panel-views.js:45 (?v=), panel-admin.js:33 (?v=)
sed -i 's/0\.16\.2/0.17.0/g' custom_components/health_o_mat/www/*.js
grep -rn "0\.16\.2" custom_components/health_o_mat/ || echo "no stale version left"
grep -rn "0\.17\.0" custom_components/health_o_mat/www/*.js | wc -l   # erwartet: 9
```

`frontend.py:74-75` liest die Version aus dem Manifest — **keine** Änderung dort.

- [ ] **Step 2: CHANGELOG `[0.17.0]` — 💥 an erster Stelle**

Direkt unter dem Intro (vor `## [0.16.2]`) einfügen:

```markdown
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

- **Category validation for custom lab markers (REQ-HOM-131):** a category outside
  `LAB_CATEGORIES` falls back to `other` instead of producing an untranslated warning
  entity with a localized object id.
- **Marker key preservation (REQ-HOM-131):** a client that re-sends markers without a
  `key` now inherits the stored key when the name matches, so the `unique_id` cannot drift.
- **Drift and pinning regression tests:** every wellbeing state's report-button
  translation is guarded, and a live E2E test asserts English object ids on a freshly
  registered person.
```

- [ ] **Step 3: `docs/RELEASE-NOTES-0.17.0.md`**

Die sechs Pflichtinhalte aus Spec §5.3 als eigenes Dokument (Projektmuster):

1. **Was sich ändert** — Alt→Neu-Tabelle (Standard-Quick-Drinks) + Regel für
   Custom-Marker inkl. `h_moglobin`-Beispiel.
2. **Was Nutzer anpassen müssen** — Automationen, Skripte, Dashboards, Szenen, Helfer,
   Template-Sensoren.
3. **Was erhalten bleibt** — `unique_id`, Recorder-Metadaten (`states_meta`,
   `statistics_meta` werden umgeschrieben, historische `states`-Zeilen nicht),
   Store-/Messdaten, `original_name`.
4. **Migrationsmechanik** — automatisch beim ersten Start; Kollision → Entry wird nicht
   geladen, Log nennt die Paare; Auflösung: Entity umbenennen/entfernen + Neustart.
5. **`MIGRATION_ERROR` ist nicht wiederherstellbar (MINOR-Konsequenz)** — `state.recoverable
   = False`, Reload/Unload gesperrt, **nur ein vollständiger HA-Neustart** wiederholt die
   Migration.
6. **Post-Release-Cleanup** — durch A-1 können Warn-Entities für Fremd-Kategorien aus dem
   Setup verschwinden (Orphans); nach dem Release in der Geräteansicht prüfen und
   entfernen, nie durch Ändern von `unique_id`s.

- [ ] **Step 4: Konsistenz prüfen**

```bash
python3 -c "import json;print(json.load(open('custom_components/health_o_mat/manifest.json'))['version'])"
# erwartet: 0.17.0
grep -n "^## \[0.17.0\]" CHANGELOG.md
grep -n "Breaking" CHANGELOG.md | head -3
grep -c "0.16.2" custom_components/health_o_mat/www/*.js || true
python3 -m pytest -q
ruff check . && ruff format --check .
```

Expected: `0.17.0` überall, `0.16.2` in `www/` **nirgends**, Suite und Lint grün.

- [ ] **Step 5: Commit**

```bash
git add custom_components/health_o_mat/manifest.json \
        custom_components/health_o_mat/www/health-o-mat-card.js \
        custom_components/health_o_mat/www/health-o-mat-labs-card.js \
        custom_components/health_o_mat/www/health-o-mat-panel.js \
        custom_components/health_o_mat/www/health-o-mat-panel-views.js \
        custom_components/health_o_mat/www/health-o-mat-panel-admin.js \
        CHANGELOG.md docs/RELEASE-NOTES-0.17.0.md
git commit -m "chore(release): prepare 0.17.0"
```

---

## Final Integration Check

- [ ] **Volle Unit-Suite:** `python3 -m pytest -q` — alle bestehenden Tests plus
  `test_req_hom_130_*`/`test_req_hom_131_*` grün, keine Regression. Testzahl notieren
  (für Task 18).
- [ ] **CI-äquivalent ohne Home Assistant (Fake-HA-Pfad):**

  ```bash
  mkdir -p .tmp/venv-no-ha
  python3 -m venv .tmp/venv-no-ha
  . .tmp/venv-no-ha/bin/activate
  pip install -r tests/requirements.txt
  python3 -m pytest -q
  deactivate
  ```

  Expected: grün — beweist, dass die Suite auch ohne installiertes HA-Paket läuft
  (`tests/conftest.py` Fake-Paket). Insbesondere `tests/test_entity_id_migration.py`
  braucht **kein** Fake-Paket (lädt `migration.py` per Dateipfad).
- [ ] **Lint/Format:** `ruff check .` und `ruff format --check .` — clean
  (`line-length = 100`, `docs/` ausgenommen).
- [ ] **Compile-Check:** `python3 -m compileall -q custom_components/health_o_mat`.
- [ ] **E2E:** `cd tests_e2e && HASS_BASE_URL=http://127.0.0.1:8123 python3 -m pytest -q`
  gegen die migrierte Instanz — alle Tests grün, inklusive `test_entity_ids_e2e.py` und der
  verschärften `_lab_<key>`-Assertion. **Beide Pfade prüfen:** (a) migrierte Instanz
  (Task 15–17), (b) frisch angelegte Fixture-Personen (Bootstrap mit `VERSION = 3`).
- [ ] **hassfest/HACS:** `.github/workflows/validate.yml` läuft bei Push/PR — keine neuen
  Fehler (`hacs/action` Kategorie `integration`, hassfest). Lokal:
  `/home/hermes/ha-test/bin/sync /home/hermes/repos/ha-health-o-mat` und
  `/home/hermes/ha-test/bin/ha core check` — `core check` muss ohne
  `Integration error` durchlaufen.
- [ ] **Live-Test auf dem Testsystem (Pflicht, Spec §6.3):** Wave 5 vollständig abgehakt —
  Positivfall A (neue IDs, unveränderte `unique_id`/`original_name`/`device_id`,
  Version 3, Store/Historie intakt, keine Orphans), Negativfall B (Version 2 + Warnung mit
  Paarliste), Retry (stufenweise Auflösung bis Version 3), Idempotenz (kein Diff),
  Restore-Prozedur dokumentiert und bei Bedarf verifiziert (`version == 2`,
  `unique_id`-Menge == Snapshot).
- [ ] **Doku-Check:** README enthält den Kasten „Entity-IDs ab 0.17.0" und das
  `…_quick_drink_1`-Button-Beispiel; REQ-HOM-130/131 sind `[x]` mit Belegen; Testzahlen
  konkret eingetragen.
- [ ] **Kein Release in diesem Plan:** Tag `v0.17.0` und das **echte** GitHub-Release
  (`gh release create v0.17.0 --latest`, kein Pre-Release) laufen als eigener,
  nachgelagerter Schritt über den `release`-Agenten, sobald der Branch nach `main`
  gemerged ist (`.claude/rules/integration-development.md`, Schritte 5–7; Tag ↔
  `manifest.version` müssen zeichenidentisch sein). Der **Post-Release HACS-Update-Test**
  (0.16.2 → 0.17.0) und der **Post-Release-Orphan-Cleanup** folgen erst danach.

---

*(End of plan.)*

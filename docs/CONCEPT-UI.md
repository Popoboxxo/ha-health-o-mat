# UI-Konzept: Health-O-Mat Oberfläche

**Vorbild:** [`m3tac0de/home-assistant-sofabaton-x1s`](https://github.com/m3tac0de/home-assistant-sofabaton-x1s)
— eine Integration, die ihre **eigene Frontend-Ebene mitliefert** (Sidebar-Panel,
Custom-Cards, WebSocket-API, Per-User-Settings) statt den Nutzer mit YAML zu
allein zu lassen.
**Grundlage:** [`REVIEW-2026-10-14.md`](REVIEW-2026-10-14.md) (Ist-Zustand + Findings).
**Use-Case:** Getränke-Tracking, Blutdruck, Wohlbefinden — pro Person, mehrere
Personen parallel.
**Status:** Konzept — Phase 1 (L1 Card + WS-Basis) umgesetzt (Branch
`feat/ui-card`, 2026-10-15), Phase 3 (L2 Panel + `ui_store` +
WS-Schreibpfad/`subscribe`) umgesetzt (Branch `feat/ui-panel`, 2026-10-15) und
Phase 4 (L3) **teilweise** umgesetzt: Admin-/Settings-Ansicht + CSV-Export
(Branch `feat/ui-admin`, 2026-10-15) — **Backup und CSV-Import
(REQ-HOM-007) bleiben offen**. Datum 2026-10-14.
**Nachtrag 2026-10-18 (Branch `feat/ui-pro`):** UI-Ausbau gemäß
[`IDEATION-UI-PRO.md`](IDEATION-UI-PRO.md) umgesetzt — **REQ-HOM-009**
(Pro-Person Feature-Toggles), adressierbare Person-Seite mit Deep-Link
(`?person=<slug>`, REQ-HOM-012), Admin-/Instanzverwaltung (Rename, Backup-Trigger,
Person anlegen via Flow-Verweis, admin-gated Löschen mit Doppelbestätigung,
REQ-HOM-013), Card-Ausbau (Pace/Serie/Koffein/WHO-Label, Editor-Komfort,
REQ-HOM-011) und Frontend-Struktur (native ES-Module + Cache-Buster,
REQ-HOM-014). Details/Entscheidungen: `IDEATION-UI-PRO.md` §7a.
**Nachtrag 2026-10-19 (Branch `feat/wellbeing-score`):** **Wohlbefinden-Score &
Score-Chart** (REQ-HOM-112) — numerische Skala 1…5 (rein abgeleitet, on-read)
plus Verlaufs-Chart in der Card (kompakt) und im Panel (vollständig). Details:
`docs/REQUIREMENTS.md` REQ-HOM-112.
**Nachtrag 2026-10-21 (Branch `feat/configurable-card`):** **Konfigurierbare
Karte** (REQ-HOM-113) — die L1-Karte ist per Karten-Editor bzw. YAML in
Anzeige- und Eingabe-Blöcken, Getränkeauswahl und manuellen Mengen einstellbar.
Default-Semantik: die **Anzeige-Blöcke bleiben unverändert**, die **neuen
Eingabe-Blöcke** (manuelle Mengen, Blutdruck-Eingabe, Wohlbefinden-Eingabe) sind
**per Default aktiv** — bestehende Karten erhalten sie beim Update (bewusste neue
Funktion; der Release-Eintrag v0.10.0 inkl. „✨ New features"-Nennung folgt
separat, die Funktion ist in diesem Branch implementiert).
Zusätzlich: Wohlbefindens-Verlaufsliste unter dem
unveränderten Score-Chart im Panel. Details: §4.6,
`docs/PLAN-CARD-CONFIG.md`.

---

## 1. Ausgangslage & Ziel

Heute liefert die Integration **ausschließlich native Entities** und ein
Beispiel-Dashboard aus Standard-Karten (`examples/dashboard*.yaml`). Es gibt:

- **kein** eigenes Panel, **keine** Custom-Card, **keine** Frontend-Ressourcen,
- **keinen** automatischen Einbindungsweg (Nutzer muss YAML finden, kopieren,
  Entity-IDs pro Person anpassen),
- **keine** Wohlbefinden-Karte im Beispiel,
- **manuelle, fragile** Bindung an `entity_id`s.

**Ziel:** Eine **mitgelieferte, app-artige Oberfläche**, die sich wie eine
Integration „von der Stange" anfühlt — einbettbar ins Dashboard, ohne
Pflicht-HACS-Frontend-Abhängigkeiten, mit Mehr-Personen-Übersicht und einer
Schreib-Interaktion (buchen/messen/melden), die sofort aktualisiert.

**Nicht-Ziel:** Medizinische Auswertung/Beratung; die UI zeigt Daten und
Orientierung, keine Diagnosen (Disclaimer bleibt prominent).

---

## 2. Vorbild Sofabaton X — was übernehmen, was nicht

| Sofabaton-Muster | Datei (Vorbild) | Übernehmen? | Begründung für Health-O-Mat |
|---|---|---|---|
| Bundled Frontend in `www/` + **automatische Lovelace-Ressourcen-Registrierung** | `frontend_resources.py` | ✅ | Card ohne manuelles Hinzufügen der Ressource nutzbar |
| **Sidebar-Panel** (`panel_custom`), default aktiv, Vollbild-App | `sidebar_panel.py` | ✅ (Phase 3) | Gesundheits-Tagebuch ist „app-artig", ideal für Full-Page |
| **Control-Panel-Card** (admin) für Config/Backup | `server-panel/` | 🟡 (Phase 4: Settings + Export; **Backup offen**) | Zentrale Verwaltung: Ziele, Lexikon, Schwellen, Export |
| **WebSocket-API** Panel↔Backend (`ws_*.py`) | `ws_panel.py`, `ws_editor.py` | ✅ | Sofort-Refresh, Schreibvorgänge, Person-/Entity-Auflösung |
| **Persistent Cache** für schnelle Reads | `cache_store.py` | 🟡 | health-o-mat liest live (klein) — Cache erst bei N-1/N-2 nötig |
| **Per-User UI-Settings** | `ui_settings_store.py` | ✅ | Merkt sich gewählte Person, Einheiten, Layout je HA-Nutzer |
| **Brand-Assets** (`brand/`, `icon.png`) | `brand/` | ✅ (klein) | Wiedererkennung im Integrations-/Panel-Kontext |
| Lokaler Proxy, Hub-Sync, MQTT, IR | `hub.py`, `wifi_*` | ❌ | domainspezifisch, hier irrelevant |

**Lehre aus `ha-go-gauge`** (Dashboard-Doku): `entity_id` ist **nicht stabil**
(Name-/Sprachänderung ⇒ Slug ändert sich). Deshalb bindet die UI **nie** über
geratene `entity_id`s, sondern löst über den **`unique_id`-Suffix** auf
(`{entry_id}_{key}`), den health-o-mat bereits stabil vergibt.

---

## 3. Zielbild — drei Ebenen

```
┌──────────────────────────────────────────────────────────────────┐
│ L3  Admin-/Settings-Ansicht      (Verwalten einer Person)        │
│     Ziel, Reset-Uhrzeit, Quick-Drinks, Lexikon, Schwellen,        │
│     Retention, Export/Backup                                     │
├──────────────────────────────────────────────────────────────────┤
│ L2  Sidebar-Panel „Health-O-Mat" (Vollbild, Mehr-Personen)       │
│     Übersicht · je Person: Trinken | Blutdruck | Wohlbefinden    │
├──────────────────────────────────────────────────────────────────┤
│ L1  Custom-Dashboard-Card „health-o-mat-card" (einbettbar)       │
│     kompakt: Ring + letzte Werte + Quick-Aktionen                │
├──────────────────────────────────────────────────────────────────┤
│ L0  Native Entities + YAML-Beispiele  (bleibt, unverändert)      │
└──────────────────────────────────────────────────────────────────┘
```

- **L0 bleibt das Fundament** — alle UI-Ebenen lesen/schreiben dieselben Entities
  bzw. denselben Store. Kein Parallel-Datenmodell.
- **L1** ist der niedrigschwellige Einstieg (eine Karte ins bestehende Dashboard).
- **L2** ist der eigentliche Mehrwert (die „App").
- **L3** bündelt, was heute über den 3-stufigen Options-Flow verstreut ist.
- YAML-Fallback bleibt: Wer keine Custom-Ressourcen will, nutzt weiter L0.

---

## 4. Informationsarchitektur & Screens

### 4.1 Person-Übersicht (L2 Start)

Adaption der go-gauge „Matrix": responsives Grid, eine Kachel je Person.

```
╔════════════════════════════════════════════════════════════╗
║  Health-O-Mat                          [+ Person]   ⚙️     ║
╠════════════════════════════════════════════════════════════╣
║  ┌── Caro ──────────────────┐  ┌── Max ───────────────────┐ ║
║  │  ◕  68 %        340 ml   │  │  ◕ 100 %  ✓   2000 ml    │ ║
║  │  Ziel 2000 ml · Rest 660 │  │  Ziel 2000 ml            │ ║
║  │  🩸 124/82 · 64          │  │  🩸 131/88 · 71  ⚠️      │ ║
║  │  🙂 Gut · vor 2 h        │  │  😄 Super · vor 20 min   │ ║
║  │  [🖱 öffnen]             │  │  [🖱 öffnen]             │ ║
║  └──────────────────────────┘  └──────────────────────────┘ ║
╚════════════════════════════════════════════════════════════╝
```

- Ampel/Status je Person aus abgeleiteten Metriken (Ziel-Pace, BP-Warnung).
- Tap auf Kachel → Person-Detail (4.2).

### 4.2 Person-Detail — Tab „Trinken"

```
┌────────────────────────────────────────────────────────────┐
│  ◕  Hydration-Ring            Heute 1360 ml / 2000 ml (68 %)│
│     68 %                      Gestern 1750 ml · Ø 7 T 1600  │
│     Rest 640 ml               Pace: +140 ml vs. Ø-Zeitpunkt │
├────────────────────────────────────────────────────────────┤
│  Quick:  [💧 Glas 200] [🍶 Flasche 500] [☕ Kaffee 250]     │
│          [🥤 Saft 200]  [＋ Eigene Menge]  [↩ Undo]          │
├────────────────────────────────────────────────────────────┤
│  Freitext:  ┌──────────────────────────────┐ [Buchen]       │
│             │ Kaffee 300ml                 │                │
│             └──────────────────────────────┘                │
├────────────────────────────────────────────────────────────┤
│  Verlauf heute (Balken je Buchung, Tagesgrenze berücksichtigt)│
│  ▁ ▃ ▂ ▅ █ ▃   …   breakdown: Wasser 800 · Kaffee 560        │
└────────────────────────────────────────────────────────────┘
```

- **Hydration-Ring** = `drinks_today` / `daily_goal` (sekundär `daily_goal_progress`).
- **Pace/Prognose** (go-gauge-Lehre): Ist-Stand vs. linearem Tagesverlauf →
  „auf Kurs / zu langsam". **Umgesetzt** (2026-10-15, Branch `feat/hydration-pace`):
  `logic.hydration_pace` berechnet den linearen Soll-Stand echt (siehe 6.3). Der
  Panel-Vertrag `today.pace` bleibt ein **String-Label**
  (`goal_reached`/`ahead`/`on_track`/`behind`) — die Detailwerte `expected_ml`/
  `delta_ml`/`forecast_ml` kommen **additiv** hinzu (nichts Bestehendes umbenannt).
- **Quick-Buttons** als große Touch-Flächen (heute `button.*_<quick>`).
- **Freitext** = `text.log_drink_free_text` (Parser bleibt).
- **Undo** = `button.undo_last_drink`.

### 4.3 Person-Detail — Tab „Blutdruck"

```
┌────────────────────────────────────────────────────────────┐
│   124 / 82        64 bpm         WHO: Normal / Optimal 🟢    │
│   systolisch      Puls           vor 3 h gemessen           │
├────────────────────────────────────────────────────────────┤
│  7-Tage-Verlauf (sys/dia Linien + Puls)   Ø 126/84 · 66     │
├────────────────────────────────────────────────────────────┤
│  Neue Messung:  [Systolisch] [Diastolisch] [Puls] [Notiz]   │
│                 [💾 Speichern]                              │
├────────────────────────────────────────────────────────────┤
│  ⚠️ Letzte Messung oberhalb der Schwellen (140/90)          │
│  Schwellen anpassen:  sys [140]  dia [90]                   │
└────────────────────────────────────────────────────────────┘
```

- Große letzte Messung, `device_class: pressure` (N-9) ⇒ korrekte Einheiten.
- **WHO-Kategorie-Badge** ← REQ-HOM-001 (Farbcodierung, kein Diagnose-Anspruch).
- Eingabezeile = `number.*_new_reading_*` + `button.save_measurement` + (neu) Notiz
  (REQ-HOM-010).
- Trend ← REQ-HOM-002.
- Warnhinweis aus `binary_sensor.*_blood_pressure_warning`.

### 4.4 Person-Detail — Tab „Wohlbefinden"

```
┌────────────────────────────────────────────────────────────┐
│  Wie geht es dir?                                           │
│   😵   🙁   😐   🙂   😄      ← große Tap-Flächen            │
├────────────────────────────────────────────────────────────┤
│  Zuletzt: 🙂 Gut · 4 / 5 · vor 2 h                          │
│  30-Tage-Timeline: ▓░░▓▓█▒ …  (Verteilung + Verlauf)         │
├────────────────────────────────────────────────────────────┤
│  Score-Verlauf                                              │
│  5 ┤ · · · · · · ·                                         │
│  4 ┤ · · · · · · ●                                         │
│  3 ┤ · · ╱ ╲ · · ·                                         │
│  2 ┤ · ╱ · · · · ·                                         │
│  1 ┤ · · · · · · ·                                         │
│    └──────────────                                          │
│      14.10.             19.10.                              │
│  1 = Sehr schlecht · 5 = Super                              │
└────────────────────────────────────────────────────────────┘
```

- Buttons = `button.*_report_*`, Zustand aus `select.*_wellbeing`.
- Timeline/Häufigkeit als einfache Auswertung (HA-History bleibt Quelle).
- **Score-Chart** (REQ-HOM-112) — der Verlauf als **SVG-Linienchart**: Zeit auf
  der X-Achse, Score 1…5 auf der Y-Achse (Extremwerte **1** und **5**
  hervorgehoben), Zeitachse (erstes/letztes Datum), der aktuelle Wert als
  hervorgehobener Marker, Tooltip je Punkt (Zeitpunkt + Label + Score) und
  `aria-label`. **Leerfall:** ohne Meldung/Verlauf erscheint ein verständlicher
  Hinweis statt eines leeren Charts.
- **Score = rein abgeleitet** — die Skala 1…5 ist reihenfolgetreu aus den fünf
  Wohlbefinden-Zuständen abgeleitet (Index + 1, wächst automatisch mit einem
  neuen Zustand); der Wert wird on-read aus den Rohmeldungen berechnet — keine
  eigene Persistenz, keine Migration.
- Chart **ohne externe Bibliothek** (Vanilla-SVG), Farben ausschließlich über
  HA-CSS-Variablen → light/dark-fähig und mobiltauglich.

### 4.5 Admin/Settings (L3)

Pro Person: Ziel, Reset-Uhrzeit, Quick-Drinks (4 Slots), Getränke-Lexikon,
BP-Schwellen, Retention, **Export** (CSV-Service-Trigger), ggf. Import
(REQ-HOM-007). = heutiger Options-Flow, aber als eine scrollbare Maske statt
3 erzwungener Schritte (vergleiche Review N-13).

### 4.6 Konfigurierbare Karte (L1, REQ-HOM-113)

**Ziel:** Die mitgelieferte Karte (`custom:health-o-mat-card`) wird über den
Karten-Editor bzw. YAML an das jeweilige Dashboard anpassbar — ohne
Zweitkonfiguration im Backend. Die **Anzeige-Blöcke** bleiben per Default
unverändert; die **neuen Eingabe-Blöcke** sind per Default **aktiv** (siehe
Semantik unten). Fünf Ziele:

1. **Getränkeauswahl** — welche Quick-Drinks als Buttons erscheinen (Referenz
   auf die in der Integration konfigurierten Getränke, keine kartenlokale
   Zweitliste).
2. **Manuelle Mengen** — welche ml-Presets es gibt und ob ein freies Zahlenfeld
   angeboten wird.
3. **Blutdruck-Eingabe** (Systolisch/Diastolisch/Puls + optionale Notiz)
   ein-/ausschaltbar.
4. **Wohlbefinden-Eingabe** (fünf Zustände) ein-/ausschaltbar.
5. **Anzeige-Blöcke** (Personenwahl, Hydration, letzter Blutdruck, letztes
   Wohlbefinden, Undo) einzeln ein-/ausschaltbar.

**Schema** (flach, alle Schlüssel optional; die gezeigten booleschen Werte
entsprechen den Defaults):

```yaml
type: custom:health-o-mat-card
entry_id: <optional>
person: <optional>
show_person: true
show_hydration: true
show_blood_pressure: true
show_wellbeing: true
show_drinks: true
show_manual_amounts: true
show_blood_pressure_input: true
show_wellbeing_input: true
show_undo: true
drinks: ["slot_0", "kaffee"]     # Keys aus panel_data.quick_drinks; leer/fehlt = alle
manual_amounts: [200, 500]       # ml-Presets; leer/fehlt = Default
allow_custom_amount: true        # freies Zahlenfeld
# Legacy-Override (gewinnt gegenüber `drinks`):
# quick_drinks: [{label: "Kaffee", ml: 250, emoji: "☕"}]
```

**Semantik** (defensiv, nie Render-Crash):

- Defaults: die **Anzeige-Blöcke bleiben unverändert** (an); die **neuen
  Eingabe-Blöcke** (manuelle Mengen, Blutdruck-Eingabe, Wohlbefinden-Eingabe)
  sind **an** — bestehende Karten erhalten sie beim Update. Das ist eine
  **bewusste Abweichung** von „Verhalten unverändert" und wird im Release
  v0.10.0 unter „✨ New features" geführt. Unbekannte Werte fallen auf den
  Default zurück.
- `show_*=false` blendet den Block samt zugehöriger Eingaben aus.
- Ein **explizit** gesetztes `show_blood_pressure_input: true` gewinnt gegen
  `show_blood_pressure: false`; ohne expliziten Wert folgt die Eingabe der Anzeige.
- `show_person: false` ohne `entry_id` → erste Person, ohne Dropdown.
- `drinks` referenziert die **Keys** der Integrations-Quick-Drinks
  (`panel_data.quick_drinks`, additiv im WS-Payload). Unbekannte Keys werden
  ignoriert; eine leere Schnittmenge (oder keine Auswahl) bedeutet „alle" —
  kein leerer Zustand.
- `manual_amounts` = positive Ganzzahlen 1…10000; leere Liste/fehlend →
  `[200, 500]`.
- Sind alle Blöcke aus, erscheint ein lesbarer Hinweis („Keine Blöcke
  aktiviert — Karten-Konfiguration prüfen.").
- Die Integrations-Feature-Toggles bleiben ein **AND**: ein abgeschalteter
  Bereich bleibt aus, auch wenn die Karte den Block anzeigen will.

**Editor** (`HealthOMatCardEditor`): lädt Personen und — für die gewählte
Person — die Quick-Drinks (lesend über `panel_data`). Er gruppiert alle neun
`show_*`-Schalter als **„Anzeige"** (4: Person, Hydration, letzter Blutdruck,
letztes Wohlbefinden) und **„Eingabe & Aktionen"** (5: Getränke, manuelle
Mengen, Blutdruck-Eingabe, Wohlbefinden-Eingabe, Undo) — das ist die Abweichung
vom ursprünglichen Plan („6/5"). Dazu kommen Getränke-Mehrfachauswahl („Alle
Getränke" als Default-Zustand) und die Mengenliste mit Hinzufügen/Entfernen plus
Schalter „Freies Zahlenfeld erlauben". Jede Änderung feuert `config-changed`;
fehlende Personendaten/Getränkelisten lassen den Editor bedienbar (Hinweis,
Auswahl „alle").

**Legacy-`quick_drinks`:** Das frühere kartenlokale Getränke-Override bleibt als
Escape-Hatch erhalten und gewinnt immer — vor der Integrationsliste und vor dem
`drinks`-Filter. Ohne Backend-Daten fällt die Karte auf die eingebauten
Standard-Getränke zurück.

**Panel-Verlaufsliste:** Unter dem unveränderten Score-Chart (REQ-HOM-112)
listet der Wohlbefinden-Tab zusätzlich die letzten 20 Meldungen als kompakte
Liste — pro Eintrag **Zeitpunkt (relativ), Emoji, Label und Score** („3 / 5").
Reine Anzeige aus `wellbeing.history`, alle Texte escaped. Der aktuelle
Live-Wert erscheint weiterhin in der Kopfzeile und im Chart-Marker, nicht in der
Verlaufsliste. Keine neuen Panel-Konfigurationsschalter.

**Tests:** Quelltext-Analyse der Karte/des Editors (`tests/test_card_js.py`),
der Panel-Verlaufsliste (`tests/test_panel_js.py`) und ein Browser-E2E
(`tests_e2e/test_card_config_e2e.py`, 7 Tests: alle Blöcke aus, BD-Anzeige aus,
explizite BD-Eingabe, Hydration aus, Konfigurations-Neuspeichern, BD-Eingabe
schreibt, Wohlbefinden-Eingabe schreibt und aktualisiert die UI).

---

## 5. Technische Architektur

### 5.1 Backend (Python, bestehende Struktur erweitern)

Neue/erweiterte Module unter `custom_components/health_o_mat/`:

| Modul | Aufgabe | Vorbild |
|---|---|---|
| `panel.py` | registriert das Sidebar-Panel via `panel_custom.async_register_panel(..., webcomponent_name=..., js_url=...)`; Unregister bei Entry-Unload | `sidebar_panel.py` |
| `frontend.py` | `async_register_static_paths` für `www/` + Auto-Registrierung der Custom-Card als Lovelace-Ressource (`/health_o_mat/health-o-mat-card.js`), idempotent | `frontend_resources.py` |
| `ws_api.py` | WebSocket-Handler (`websocket_api.async_register_command`) | `ws_panel.py` |
| `ui_store.py` | Per-User-Settings (`Store`, keyed `user_id`) | `ui_settings_store.py` |
| `www/` | ausgelieferte JS/CSS/Assets | `www/` |

**Kernprinzip:** Die Frontend-Schicht ruft **keine** geratenen `entity_id`s auf.
Ein WS-Resolver liefert die echte Bindung.

### 5.2 WebSocket-API (Entwurf)

```text
health_o_mat/list_persons
  → [{ entry_id, display_name, device_id }]

health_o_mat/panel_data          { entry_id }
  → { person, goal_ml, reset_hour,
      today: { ml, percent, count, breakdown, yesterday_ml, pace,
               expected_ml, delta_ml, forecast_ml },
      bp:    { sys, dia, pulse, at, avg7: {sys,dia,pulse},
               category, warning, entries: [...] },
      wellbeing: { key, label, emoji, score, at,
                   history: [{ key, label, emoji, score, ts }, …] },
      quick_drinks: [{ key, label, ml, icon }, …],   # additiv (REQ-HOM-113)
      entities: { drinks_today: "sensor.…", percent: "sensor.…", … } }

health_o_mat/subscribe           { entry_id }
  → event stream: { type: "refresh", entry_id, payload }   (push statt Poll)

health_o_mat/book_drink          { entry_id, ml, drink_type?, free_text? }
health_o_mat/undo_last           { entry_id }
health_o_mat/save_measurement    { entry_id, sys, dia, pulse?, note? }
health_o_mat/set_wellbeing       { entry_id, key }
health_o_mat/search_persons      { references }   # optional, unique_id-Suffix-Match
```

- Schreib-Kommandos delegieren an dieselben Store-/`signal_refresh`-Pfade wie die
  Services (kein Zweitweg).
- Der `entities`-Block wird über den **`unique_id`-Suffix** aufgelöst
  (`{entry_id}_{key}`) — robust gegen Slug-/Sprachdrift (go-gauge-Lehre).
- `today.pace` bleibt ein **String-Label** (`goal_reached` | `ahead` | `on_track` |
  `behind`, `null` ohne positives Ziel); `expected_ml`/`delta_ml`/`forecast_ml`
  sind **additive** Detailwerte aus `logic.hydration_pace` (stabiler Vertrag,
  nichts Bestehendes umbenannt).
- Optional `ws_register`/`require_admin` für Admin-Kommandos.

### 5.3 Frontend (Lit + TypeScript, gebündelt)

- **Custom Element** `health-o-mat-card` (L1) und `health-o-mat-panel` (L2/L3).
- Genau **eine** Bundling-Stufe (`rollup`/`esbuild`) → je eine `.js` in `www/`.
- Ressourcen-Registrierung:
  1. `async_register_static_paths([StaticPathConfig("/health_o_mat", www_dir, cache_headers=...)])`
  2. Lovelace-Ressource automatisch anlegen (in `lovelace.resources`), idempotent,
     mit `frontend.add_extra_js_url` als Fallback — im Sofabaton-Stil.
- **Keine Pflicht-HACS-Frontend-Abhängigkeit** (kein Mushroom/card-mod nötig).
- Styling über HA-CSS-Variablen (`--primary-color`, `--card-background-color`) →
  Themes/Light-Dark automatisch.
- Mobile-first (Sidebar-Panel ist primär mobil).

### 5.4 Entity-Auflösung & Mehr-Person-Robustheit

- Panel merkt sich gewählte Person in `ui_store` (je HA-User).
- Personenliste kommt aus der Domain-Registry (`hass.data[DOMAIN]`), nicht aus
  geratenen Slugs.
- Falls eine Person umbenannt wird, bleibt sie über `entry_id` stabil gebunden.

### 5.5 Schreib- & Refresh-Pfad

```text
Card/Panel  ──(WS command)──▶  backend handler
                                   │  store.add_drink(...) / add_reading(...)
                                   ▼
                              signal_refresh(entry_id)
                                   │
                                   ▼
                          WS event "refresh"  ──▶  alle offenen UIs
```

- Sofortiges UI-Update ohne Polling; Entities und Panel bleiben konsistent.

---

## 6. Voraussetzungen & Abhängigkeiten

### 6.1 Muss die Integration zuerst liefern (aus dem Review)
- N-1 (Historie-Cap/kein Riesen-Attribut) — sonst überträgt das Panel große Payloads.
- N-3/N-4 (korrekte `state_class`) — sonst zeigen Verlaufsgraphen Müll.
- N-9 (`volume`/`pressure` device_class) — Einheiten/Formatierung.
- N-2 (Retention) — Dauerbetrieb.
- N-5 (Diagnostics) — Support bei „Panel zeigt nichts".

### 6.2 Feature-Sensoren, die die UI sichtbar macht
- REQ-HOM-001 (WHO-Kategorie) → Badge in 4.3.
- REQ-HOM-002 (Trends) → Pace/Trend in 4.2/4.3.
- REQ-HOM-003 (Streak) → Kachel in 4.1/4.2.
- REQ-HOM-004 (Koffein) → optionaler Chips-Wert in 4.2.
- REQ-HOM-010 (Notiz) → Feld in 4.3.

Die UI **konsumiert** diese; sie implementiert sie nicht selbst.

### 6.3 Kleine neue Logik (HA-frei, testbar)
- ✅ `hydration_pace(drinks, now, goal_ml, hour=0, minute=0)` → Ist vs. linearer
  Soll-Verlauf. Liefert `status` (`ahead`/`on_track`/`behind`), `actual_ml`,
  `expected_ml`, `delta_ml`, `forecast_ml`, `percent` (lineare Erwartung,
  Toleranzband ±10 % des Ziels; Tagesgrenze = `daily_reset_hour`/`-minute`).
  **Umgesetzt** 2026-10-15, Branch `feat/hydration-pace`; Tests
  `tests/test_logic.py::test_hydration_pace_*`.
- `who_category(sys, dia)` → Enum (REQ-HOM-001).
- `bp_trend(readings, now)` → steigend/fallend/stabil (REQ-HOM-002).
→ in `logic.py`, Unit-Tests wie bestehend (Muster `tests/test_logic.py`).

---

## 7. Phasing / Roadmap

| Phase | Inhalt | Nutzen | Abhängig |
|---|---|---|---|
| **0** | Backend-Hygiene (Review Welle 1: N-1, N-3/4, N-9, N-2, N-5, N-6, N-7, N-8) | bessere Graphen/Support/Stabilität — **für jedes** Dashboard | — |
| **1** ✅ | `frontend.py` + `www/health-o-mat-card.js` (L1): Hydration-Ring, letzte BP-Werte, Wellbeing, Quick-Aktionen. Vanilla-Web-Component, keine Build-Toolchain | sofort sichtbarer Mehrwert, einbettbar | Phase 0 (device_class, state_class) |
| **2** | Feature-Sensoren 001/002/003 + `logic.py`-Erweiterung; Karte zeigt Badge/Trend/Streak | entscheidungsrelevante Metriken | — (parallel zu 1) |
| **3** ✅ | `panel.py` + `ws_api.py` + `ui_store.py` (L2/L3): Sidebar-Panel, Mehr-Personen, Tabs, Per-User-Settings, WS-Schreibpfad + `subscribe` | „die App" | Phase 1; WS-Schreibpfad braucht saubere Refresh-Events |
| **4** | 🟡 teilweise: Admin-/Settings-Ansicht **+ CSV-Export** (L3) umgesetzt; **Backup** und optionaler CSV-**Import** (REQ-HOM-007) **offen** | Verwaltung an einem Ort | Phase 3 |
| **5** | 🟡 teilweise: Release-Härtung (`release-check.yml`) ✅; **Frontend-Browser-Smoke des Panels** ✅ (`tests_e2e/`, Playwright/Chromium gegen eine echte HA-Instanz, CI via `.github/workflows/e2e.yaml`); Karten-Konfiguration per Browser-E2E abgedeckt (`tests_e2e/test_card_config_e2e.py`, 7 Tests, REQ-HOM-113); Score-/Chart-Umfang per Live-E2E auf `ha-test` verifiziert (Screenshots: `docs/e2e-2026-10-19-wellbeing-score/`) | sichere Releases | — |

**Nachtrag (2026-10-19, Branch `feat/wellbeing-score`):** Phase 5 🟡 — neben der
Release-Härtung: **Wohlbefinden-Score & Score-Chart** (REQ-HOM-112) umgesetzt
(Skala 1…5, rein abgeleitet; Chart in Card und Panel) **und verifiziert** —
dedizierte Unit-/JS-Tests sind vorhanden (`pytest -q` grün, `ruff` clean), die
Browser-/E2E-Verifikation auf `ha-test` ist mit Screenshots erfolgt (Beleg:
`docs/e2e-2026-10-19-wellbeing-score/`). **Offen:** nur noch der **Release**
(Versions-Bump `manifest.version` + `?v=`-Cache-Buster zusammen, Tag,
GitHub-Release).

**Empfehlung:** Phase 0 strikt zuerst. Die UI auf unbounded Attributen und falschen
`state_class` aufzusetzen erzeugt sichtbare Fehler, die man später teuer nachzieht.

**Stand (2026-10-15, Branch `feat/ui-admin`):** Phase 0 ✅ (Review-Welle 1),
Phase 1 ✅ (L1-Card `www/health-o-mat-card.js` + WS-Basis `list_persons`/
`panel_data` + automatische Lovelace-Ressourcen-Registrierung), Phase 3 ✅
(L2-Panel `www/health-o-mat-panel.js` + `panel.py` + `ui_store.py` +
WS-Schreibpfad `book_drink`/`undo_last`/`save_measurement`/`set_wellbeing` +
`subscribe`-Refresh-Stream + `get/set_ui_settings`; opt-in über
`enable_sidebar_panel`, Default aus) und Phase 4 🟡 (Teilstand — Admin/Settings
im Panel: admin-gated `get_settings`/`set_settings`/`export_csv`; pro Person
Tagesziel, Reset-Uhrzeit, Anzeigename, Quick-Drinks, Getränke-Lexikon,
BP-Schwellen, Retention, Sidebar-Toggle; CSV-Export über den bestehenden
`export_csv`-Service) umgesetzt. Zu diesem Stand hatten die JS-Card **und das
Panel** keine CI-Tests und ein Live-E2E auf `ha-test` stand aus; **inzwischen**
sind dedizierte Unit-/JS-Tests vorhanden (`tests/test_card_js.py`,
`tests/test_panel_js.py`; `pytest -q` grün, `ruff` clean) und der
Score-/Chart-Umfang ist per Live-E2E auf `ha-test` mit Screenshots verifiziert
(Beleg: `docs/e2e-2026-10-19-wellbeing-score/`). Weiterhin offen:
`logic.hydration_pace` (nur Platzhalter `ws_api.compute_pace`), **eine
Backup-Funktion (nicht gebaut)**, der optionale CSV-Import (REQ-HOM-007) und
Phase 5 (Release-Härtung).

**Stand (2026-10-18, Branch `feat/e2e-playwright`):** Phase 5 🟡 — der optionale
Frontend-Smoke ist **umgesetzt und grün**. `tests_e2e/` fährt mit Playwright
(Chromium) gegen eine echte Home-Assistant-Instanz (Docker-Stack
`docker-compose.e2e.yml` + `Dockerfile.e2e`, alternativ gegen das geteilte
`ha-test`) und prüft: Panel-Mount unter `/health-o-mat`, Deep-Link
`?person=<slug>` öffnet direkt die Person-Detailansicht, Kachel-Klick setzt den
Parameter per `history.pushState`, Browser-Zurück stellt die Übersicht wieder
her (`popstate`), ein unbekannter Parameter fällt sicher auf die Übersicht
zurück, und ein per Feature-Toggle abgeschalteter Bereich blendet seinen Tab
aus (REQ-HOM-012). Die Vorbereitung (Onboarding bzw. Login, Test-Personen über
den echten Config-/Options-Flow inklusive `enable_sidebar_panel`) ist
idempotent in `scripts/e2e_bootstrap.py`; die Unit-Suite bleibt HA-frei und
sammelt die Browser-Suite nicht mit ein. Damit ist die Aussage „die JS-Card
**und das Panel** haben keine CI-Tests" oben **für das Panel überholt** — für
die **Karte** (L1) existiert weiterhin kein Browser-Test. Zu den übrigen offenen
Punkten des Stands vom 2026-10-15 siehe den aktuellen Stand in
`docs/REQUIREMENTS.md`.

---

## 8. Offene Entscheidungen

1. **Build-Werkzeug:** TypeScript+Bundling (wie Sofabaton, wartungsintensiver) vs.
   **Vanilla-Web-Component** ohne Build (leichter, sofort im Repo lesbar). →
   Vorschlag: mit Vanilla starten (Phase 1), erst bei Panel-Komplexität (Phase 3)
   auf TS/Bundling wechseln.
2. **Verteilweg der Card:** im Integrations-`www/` gebündelt + auto-registriert
   (Sofabaton-Stil) vs. separates HACS-Frontend-Plugin. → Vorschlag: gebündelt,
   mit Erkennung eines separat via HACS installierten Plugins (Dedupe), wie Sofabaton.
3. **Panel-Default:** Sidebar automatisch aktivieren (Sofabaton) vs. opt-in per
   Option. → Vorschlag: opt-in über Device-/Options-Schalter (weniger Überraschung).
   **✅ umgesetzt (opt-in, Option `enable_sidebar_panel`, Default aus; Branch
   `feat/ui-panel`, 2026-10-15)** — die Entscheidung selbst bleibt unverändert.
4. **Schreibrechte:** Panel-Schreibzugriffe für alle HA-User vs. nur Admin? →
   Vorschlag: Buchen/Melden für alle (Alltag), Settings/Export admin-only.
   **✅ umgesetzt (Settings/Export admin-gated, Alltag für alle; Branch
   `feat/ui-admin`, 2026-10-15)** — die Entscheidung selbst bleibt unverändert.
5. **Datenschutz:** Panel zeigt Gesundheitsdaten im Browser-Cache des Users. →
   Kein Server-Side-Caching personenbezogener Daten; Diagnostics strikt redigiert.

## 9. Risiken

| Risiko | Wirkung | Gegenmaßnahme |
|---|---|---|
| `entity_id`-Drift / Sprachwechsel | Karte findet Entities nicht | Bindung nur über `unique_id`-Suffix + WS-Resolver (5.2) |
| Unbounded Attribute (N-1) | große WS-Payloads, träge UI | Phase 0 zuerst; Payloads begrenzen |
| Frontend-Drift HA-Versionen | Panel/Card brechen | Vanilla-Component + HA-CSS-Variablen, Test auf `ha-test` |
| Doppelte Card-Registrierung (HACS + bundled) | Konflikte | Dedupe wie Sofabaton (Version erkennen) |
| Scope-Creep „Dashboard-Builder" | endet in einer halben HA-Kopie | strikt 3 Ansichten × 4 Tabs; kein Custom-Grid |

## 10. Referenzen

- UI-Vorbild: <https://github.com/m3tac0de/home-assistant-sofabaton-x1s>
  (`frontend_resources.py`, `sidebar_panel.py`, `ws_*.py`, `ui_settings_store.py`, `www/`).
- Dashboard-Lehren (Entity-ID-Bindung, unique_id-Suffix): <https://github.com/Popoboxxo/ha-go-gauge>
  → `docs/dashboards/README.md`.
- HA-Entwickler-Doku: `panel_custom`, `async_register_static_paths`,
  `websocket_api`, `lovelace.resources`.
